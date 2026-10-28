"""Anthropic Messages gateway contract: provider routing, credentials, payload policy, and errors."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.services.chat_provider_gateway.anthropic_messages import (
    AnthropicMessagesProtocol,
    apply_openrouter_reasoning_policy as _apply_openrouter_reasoning_policy,
    byok_provider_error_code as _byok_provider_error_code,
    huggingface_provider_error_code as _huggingface_provider_error_code,
    keep_anthropic_request_fields as _keep_anthropic_request_fields,
    optimize_initial_deepseek_payload as _optimize_initial_deepseek_payload,
    payload_contains_tool_use as _payload_contains_tool_use,
    prefer_fastest_openrouter_provider as _prefer_fastest_openrouter_provider,
    provider_headers as _provider_headers,
    provider_target as _provider_target,
    user_provider_credential as _user_provider_credential,
    user_provider_token as _user_provider_token,
)
from backend.services.chat_provider_gateway.lifecycle import (
    offered_tool_inventory as _offered_tool_inventory,
)
from backend.config import Settings
from backend.services.hf_inference_billing_service import (
    HfInferenceCredential,
    encrypt_credential,
    encrypt_token,
)


def _request(*headers: tuple[bytes, bytes]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/messages",
            "headers": list(headers),
        }
    )


def test_gateway_uses_connected_user_token_without_bill_to_header():
    settings = Settings(_env_file=None, jwt_secret="x" * 32, hf_token="nielsr-token")
    owner_hash = "a" * 64
    row = SimpleNamespace(
        owner_hash=owner_hash,
        provider_token_encrypted=encrypt_token(
            "connected-user-token", owner_hash, settings
        ),
    )

    token = _user_provider_token(row, settings)
    headers = _provider_headers(
        token,
        _request(
            (b"accept", b"text/event-stream"),
            (b"anthropic-beta", b"test-beta"),
        ),
    )

    assert headers["Authorization"] == "Bearer connected-user-token"
    assert headers["Accept"] == "text/event-stream"
    assert headers["Anthropic-Beta"] == "test-beta"
    assert "nielsr-token" not in headers.values()
    assert "X-HF-Bill-To" not in headers


def test_gateway_forwards_validated_organization_billing_target():
    settings = Settings(_env_file=None, jwt_secret="x" * 32)
    owner_hash = "a" * 64
    row = SimpleNamespace(
        owner_hash=owner_hash,
        provider_token_encrypted=encrypt_credential(
            HfInferenceCredential("connected-user-token", "huggingface"),
            owner_hash,
            settings,
        ),
    )

    credential = _user_provider_credential(row, settings)
    headers = _provider_headers(
        credential.token,
        _request((b"accept", b"text/event-stream")),
        bill_to=credential.bill_to,
    )

    assert headers["X-HF-Bill-To"] == "huggingface"


def test_gateway_fails_closed_instead_of_using_shared_token():
    settings = Settings(_env_file=None, jwt_secret="x" * 32, hf_token="nielsr-token")
    row = SimpleNamespace(owner_hash="a" * 64, provider_token_encrypted=None)

    with pytest.raises(HTTPException) as error:
        _user_provider_token(row, settings)

    assert error.value.status_code == 402
    assert error.value.detail == "Authorize Hugging Face inference"


def test_gateway_routes_deepseek_to_server_funded_openrouter():
    settings = Settings(
        _env_file=None,
        environment="staging",
        chat_openrouter_api_key="openrouter-token",
        chat_openrouter_server_funded_enabled=True,
    )
    row = SimpleNamespace(
        model=settings.chat_deepseek_v4_flash_openrouter_route,
        owner_hash="a" * 64,
        provider_token_encrypted=None,
    )

    assert _provider_target(row, settings) == (
        "https://openrouter.ai/api/v1/messages",
        "openrouter-token",
        None,
    )


def test_gateway_uses_openrouter_nitro_routing():
    payload = {"provider": {"only": ["baseten"]}}

    _prefer_fastest_openrouter_provider(payload)

    assert payload["provider"] == {"sort": "throughput"}


def test_gateway_latency_routing_is_independently_gated():
    payload = {}
    settings = Settings(
        _env_file=None,
        chat_openrouter_routing_enabled=True,
        chat_openrouter_routing_policy="latency",
    )

    _prefer_fastest_openrouter_provider(payload, settings)

    assert payload["provider"] == {"sort": "latency"}


def test_gateway_preferred_provider_bounds_fallbacks_parameters_and_price():
    payload = {}
    settings = Settings(
        _env_file=None,
        chat_openrouter_routing_enabled=True,
        chat_openrouter_routing_policy="preferred_provider",
        chat_openrouter_preferred_providers="fireworks, baseten/fp8",
    )

    _prefer_fastest_openrouter_provider(payload, settings)

    assert payload["provider"] == {
        "allow_fallbacks": True,
        "require_parameters": True,
        "max_price": {"prompt": 0.28, "completion": 0.56},
        "order": ["fireworks", "baseten/fp8"],
        "only": ["fireworks", "baseten/fp8"],
    }


def test_gateway_preferred_provider_requires_configured_order():
    settings = Settings(
        _env_file=None,
        chat_openrouter_routing_enabled=True,
        chat_openrouter_routing_policy="preferred_provider",
    )

    with pytest.raises(RuntimeError, match="requires provider slugs"):
        _prefer_fastest_openrouter_provider({}, settings)


def test_gateway_price_performance_routing_preserves_fallbacks_and_price():
    payload = {}
    settings = Settings(
        _env_file=None,
        chat_openrouter_routing_enabled=True,
        chat_openrouter_routing_policy="price_performance",
    )

    _prefer_fastest_openrouter_provider(payload, settings)

    assert payload["provider"] == {
        "allow_fallbacks": True,
        "require_parameters": True,
        "max_price": {"prompt": 0.28, "completion": 0.56},
        "sort": "price",
        "preferred_max_latency": {"p90": 3.0},
        "preferred_min_throughput": {"p90": 50.0},
    }


@pytest.mark.parametrize(
    ("candidate", "expected", "system_count", "tool_count"),
    [
        ("system_duplicates", {"system_blocks": 1, "tools": 0}, 1, 3),
        ("tool_duplicates", {"system_blocks": 0, "tools": 1}, 2, 2),
    ],
)
def test_initial_payload_optimization_removes_one_exact_candidate_at_a_time(
    candidate, expected, system_count, tool_count
):
    tool = {"name": "search", "description": "Search", "input_schema": {}}
    payload = {
        "system": [{"type": "text", "text": "stable"}] * 2,
        "tools": [tool, dict(tool), {**tool, "description": "Different"}],
    }

    removed = _optimize_initial_deepseek_payload(payload, candidate)

    assert removed == expected
    assert len(payload["system"]) == system_count
    assert len(payload["tools"]) == tool_count


@pytest.mark.parametrize("provider_mode", ["huggingface", "openrouter_funded"])
def test_gateway_inventory_offers_excalidraw_tools_without_capturing_schemas(
    provider_mode,
):
    del provider_mode
    payload = {
        "tools": [
            {
                "name": "create_view",
                "description": "secret diagram schema",
                "input_schema": {"secret": True},
            },
            {"name": "read", "input_schema": {}},
            {"name": "read_me", "input_schema": {"html": "<iframe>"}},
            {"name": "search_web", "input_schema": {}},
        ]
    }

    inventory = _offered_tool_inventory(payload)

    assert inventory["offered_tool_names"] == [
        "create_view",
        "read",
        "read_me",
        "search_web",
    ]
    assert inventory["offered_tool_count"] == 4
    assert "secret" not in str(inventory)
    assert "iframe" not in str(inventory)
    unique = _optimize_initial_deepseek_payload(
        {
            "tools": [
                {"name": "read_me", "input_schema": {}},
                {"name": "create_view", "input_schema": {}},
            ]
        },
        "tool_duplicates",
    )
    assert unique == {"system_blocks": 0, "tools": 0}


def test_gateway_detects_tool_use_without_retaining_payload_text():
    assert _payload_contains_tool_use(
        b'{"content":[{"type":"tool_use","name":"read_me"}]}'
    )
    assert not _payload_contains_tool_use(
        b'{"content":[{"type":"text","text":"hello"}]}'
    )


def test_gateway_enforces_reasoning_effort_and_hides_reasoning():
    payload = {"reasoning": {"effort": "high", "exclude": False}}

    _apply_openrouter_reasoning_policy(payload, "low", show_reasoning=False)

    assert payload["reasoning"] == {"effort": "low", "exclude": True}
    with pytest.raises(ValueError):
        _apply_openrouter_reasoning_policy(payload, "xhigh", show_reasoning=False)


def test_gateway_rejects_shared_openrouter_when_preview_is_disabled():
    settings = Settings(
        _env_file=None,
        environment="staging",
        chat_openrouter_api_key="openrouter-token",
        chat_openrouter_server_funded_enabled=False,
    )
    row = SimpleNamespace(
        model=settings.chat_deepseek_v4_flash_openrouter_route,
        owner_hash="a" * 64,
        provider_token_encrypted=None,
    )

    with pytest.raises(HTTPException) as error:
        _provider_target(row, settings)

    assert error.value.status_code == 503


def test_gateway_keeps_hugging_face_models_on_user_billing():
    settings = Settings(_env_file=None, jwt_secret="x" * 32)
    owner_hash = "a" * 64
    row = SimpleNamespace(
        model=settings.chat_deepseek_v4_flash_route,
        owner_hash=owner_hash,
        provider_token_encrypted=encrypt_credential(
            HfInferenceCredential("connected-user-token", "huggingface"),
            owner_hash,
            settings,
        ),
    )

    assert _provider_target(row, settings) == (
        "https://router.huggingface.co/v1/messages",
        "connected-user-token",
        "huggingface",
    )


@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [
        (402, "openrouter_byok_billing_error"),
        (429, "openrouter_byok_rate_limit"),
        (400, None),
        (500, None),
    ],
)
def test_gateway_keeps_byok_billing_and_rate_limit_errors_distinct(
    status_code, error_code
):
    assert _byok_provider_error_code(status_code) == error_code


@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [(402, "hf_inference_billing_exhausted"), (401, None), (429, None)],
)
def test_gateway_classifies_hugging_face_billing_errors(status_code, error_code):
    assert _huggingface_provider_error_code(status_code) == error_code


def _sponsored_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret="x" * 32,
        environment="production",
        chat_openai_direct_enabled=True,
        chat_sponsored_deepseek_enabled=True,
        chat_title_hf_token="org-title-token",
        chat_title_bill_to="huggingface",
    )


def test_gateway_bills_sponsored_model_to_the_organization():
    settings = _sponsored_settings()
    # A connected user credential is never used for the sponsored route.
    row = SimpleNamespace(
        model=settings.chat_sponsored_deepseek_route,
        owner_hash="a" * 64,
        provider_token_encrypted=None,
    )

    assert _provider_target(row, settings) == (
        "https://router.huggingface.co/v1/messages",
        "org-title-token",
        "huggingface",
    )


def test_gateway_refuses_sponsored_model_without_organization_credential():
    settings = _sponsored_settings().model_copy(update={"chat_title_hf_token": ""})
    row = SimpleNamespace(model=settings.chat_sponsored_deepseek_route)

    with pytest.raises(HTTPException) as error:
        _provider_target(row, settings)
    assert error.value.status_code == 503


def test_gateway_reports_exhausted_sponsorship_not_user_billing():
    protocol = AnthropicMessagesProtocol(_sponsored_settings())

    def mapped(mode: str, status_code: int):
        result = asyncio.run(
            protocol.map_provider_status(
                SimpleNamespace(status_code=status_code),
                SimpleNamespace(provider_mode=mode),
            )
        )
        return None if result is None else result.code

    assert mapped("hf_org_funded", 402) == "hf_sponsored_unavailable"
    assert mapped("hf_org_funded", 429) is None
    assert mapped("huggingface", 402) == "hf_inference_billing_exhausted"


def test_openrouter_extensions_are_dropped_from_caller_payloads():
    payload = {
        "model": "deepseek/deepseek-v4",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1024,
        "thinking": {"type": "enabled", "budget_tokens": 512},
        "tools": [],
        # OpenRouter extensions a funded turn must not choose for itself.
        "models": ["openai/o9-pro"],
        "route": "fallback",
        "plugins": [{"id": "web"}],
        "transforms": ["middle-out"],
        "provider": {"only": ["expensive"]},
    }

    dropped = _keep_anthropic_request_fields(payload)

    assert dropped == ["models", "plugins", "provider", "route", "transforms"]
    assert set(payload) == {"model", "messages", "max_tokens", "thinking", "tools"}
