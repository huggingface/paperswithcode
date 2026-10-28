"""OpenAI Responses gateway contract: protocol dispatch, payload trust, streams, and turn limits."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import backend.chat_gateway_app as gateway_app
import anyio
import pytest
from fastapi import HTTPException

from backend.services.chat_provider_gateway import lifecycle
from backend.services.chat_provider_gateway.openai_responses import (
    openai_stream_error_code,
    safe_openai_request_id as _safe_openai_request_id,
    trusted_openai_payload as _trusted_openai_payload,
)
from backend.config import Settings
from backend.services.chat_openai_budget_service import (
    MAX_REQUEST_BYTES,
)
from backend.services.chat_openai_usage_extractor import (
    OpenAIResponsesUsageExtractor,
    classify_openai_error,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "jwt_secret": "test-secret-not-for-production",
        "chat_openai_pricing_verified_at": "2026-09-20",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _capability(**overrides):
    values = {
        "owner_hash": "owner-hash-must-not-leave-the-gateway",
        "chat_session_id": uuid.uuid4(),
        "reasoning_effort": "low",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_existing_gateway_path_dispatches_explicit_responses_protocol(monkeypatch):
    sentinel = object()
    captured = {}

    async def fake_responses(*args):
        captured["args"] = args
        return sentinel

    monkeypatch.setattr(gateway_app, "responses", fake_responses)
    request = SimpleNamespace(headers={"x-pwc-provider-protocol": "openai-responses"})
    db = object()
    settings = _settings()

    result = asyncio.run(
        gateway_app.messages(
            request,
            "Bearer capability",
            "session-id",
            "turn-id",
            None,
            db,
            settings,
        )
    )

    assert result is sentinel
    assert captured["args"] == (
        request,
        "Bearer capability",
        "session-id",
        "turn-id",
        None,
        db,
        settings,
    )


def test_trusted_responses_payload_overwrites_every_security_boundary_field():
    settings = _settings()
    capability = _capability()
    payload, maximum = _trusted_openai_payload(
        {
            "model": "gpt-6-luna",
            "input": [{"role": "user", "content": "hello"}],
            "max_output_tokens": 1000,
            "stream": False,
            "store": True,
            "service_tier": "priority",
            "prompt_cache_key": "worker-controlled-key",
            "prompt_cache_retention": "24h",
            "prompt_cache_options": {"breakpoints": [1]},
            "reasoning": {"effort": "max", "summary": "auto"},
        },
        capability,
        settings,
    )

    assert maximum == 1000
    assert payload["model"] == "gpt-6-luna"
    assert payload["stream"] is True
    assert payload["store"] is False
    assert payload["service_tier"] == "default"
    assert payload["reasoning"] == {"effort": "low", "summary": "auto"}
    assert payload["include"] == ["reasoning.encrypted_content"]
    assert payload["prompt_cache_key"].startswith("pwc_")
    assert payload["safety_identifier"].startswith("pwc_")
    assert "owner-hash" not in str(payload)
    assert "prompt_cache_retention" not in payload
    assert "prompt_cache_options" not in payload


@pytest.mark.parametrize(
    ("granted", "reasoning", "expected"),
    [
        ("max", {"effort": "high"}, "high"),
        ("max", {"effort": "low"}, "low"),
        ("high", {"effort": "max"}, "high"),
        ("max", {"effort": "medium"}, "medium"),
        ("high", {"effort": "medium"}, "medium"),
        ("medium", {"effort": "high"}, "medium"),
        ("max", {"effort": "xhigh"}, "max"),
        ("max", None, "max"),
    ],
)
def test_trusted_responses_payload_only_lowers_reasoning_effort(
    granted, reasoning, expected
):
    request = {"model": "gpt-6-luna", "max_output_tokens": 1000}
    if reasoning is not None:
        request["reasoning"] = reasoning
    payload, _ = _trusted_openai_payload(
        request, _capability(reasoning_effort=granted), _settings()
    )

    assert payload["reasoning"]["effort"] == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "gpt-5.6-terra", "max_output_tokens": 100},
        {"model": "gpt-6-luna", "max_output_tokens": 100, "metadata": {}},
        {
            "model": "gpt-6-luna",
            "max_output_tokens": 100,
            "include": ["file_search_call.results"],
        },
        {
            "model": "gpt-6-luna",
            "max_output_tokens": 100,
            "tools": [{"type": "web_search"}],
        },
    ],
)
def test_trusted_responses_payload_rejects_substitution_and_unsupported_fields(payload):
    with pytest.raises(HTTPException):
        _trusted_openai_payload(payload, _capability(), _settings())


def test_openai_usage_stream_extracts_terminal_exact_categories_across_chunks():
    raw = (
        b"event: response.created\n"
        b'data: {"type":"response.created","response":{"id":"resp_123"}}\n\n'
        b"event: response.function_call_arguments.delta\n"
        b'data: {"type":"response.function_call_arguments.delta","delta":"{\\""}\n\n'
        b"event: response.completed\n"
        b'data: {"type":"response.completed","response":{"id":"resp_123",'
        b'"service_tier":"default","usage":{"input_tokens":100,'
        b'"input_tokens_details":{"cached_tokens":40,"cache_write_tokens":10},'
        b'"output_tokens":20,"output_tokens_details":{"reasoning_tokens":8}}}}\n\n'
    )
    extractor = OpenAIResponsesUsageExtractor()
    for start in range(0, len(raw), 11):
        extractor.feed(raw[start : start + 11])

    result = extractor.result()
    assert result.response_id == "resp_123"
    assert result.service_tier == "default"
    assert result.input_tokens == 100
    assert result.cached_input_tokens == 40
    assert result.cache_write_tokens == 10
    assert result.output_tokens == 20
    assert result.reasoning_tokens == 8
    assert result.outcome == "completed"
    assert extractor.saw_token_delta is True
    assert extractor.saw_tool_call is True
    assert result.tool_call_count == 1


@pytest.mark.parametrize(
    ("outcome", "cancelled", "expected"),
    [
        ("completed", False, None),
        ("incomplete", False, "openai_incomplete"),
        ("failed", False, "openai_unavailable"),
        (None, True, "openai_stream_cancelled"),
        (None, False, "openai_unavailable"),
    ],
)
def test_openai_stream_terminal_classification(outcome, cancelled, expected):
    assert openai_stream_error_code(outcome, cancelled=cancelled) == expected


def test_openai_stream_closes_inside_an_already_cancelled_anyio_scope():
    class Closeable:
        closed = False

        async def aclose(self):
            await anyio.sleep(0)
            self.closed = True

    upstream = Closeable()
    client = Closeable()

    async def cancel_during_stream():
        with anyio.CancelScope() as scope:
            scope.cancel()
            await lifecycle.close_upstream(upstream, client)

    asyncio.run(cancel_during_stream())

    assert upstream.closed is True
    assert client.closed is True


def test_oversized_openai_request_returns_a_typed_public_error(monkeypatch):
    # The gateway authorizes the turn before it reads the body; a capable
    # worker that sends too much gets the protocol's typed error.
    monkeypatch.setattr(
        gateway_app, "_scope", lambda *_args, **_kwargs: SimpleNamespace(scopes=[])
    )

    class OversizedRequest:
        async def body(self):
            return b"x" * (MAX_REQUEST_BYTES + 1)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            gateway_app.responses(
                OversizedRequest(),
                "Bearer capability",
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                None,
                object(),
                _settings(
                    chat_openai_direct_enabled=True,
                    openai_api_key="test-openai-key",
                ),
            )
        )

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == "request_too_large: Model request is too large"


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, b'{"error":{"message":"secret provider detail"}}', "openai_unavailable"),
        (403, b"", "openai_unavailable"),
        (429, b'{"error":{"type":"rate_limit_error"}}', "openai_rate_limited"),
        (
            429,
            b'{"error":{"code":"insufficient_quota"}}',
            "openai_budget_exhausted",
        ),
        (400, b'{"error":{"type":"invalid_request_error"}}', "openai_invalid_request"),
        (500, b"", "openai_unavailable"),
    ],
)
def test_openai_error_classification_uses_structured_429(status, body, expected):
    assert classify_openai_error(status, body) == expected


def test_provider_request_id_is_bounded_and_content_safe():
    assert _safe_openai_request_id("req_abc-123") == "req_abc-123"
    assert _safe_openai_request_id("Authorization: Bearer secret") is None
    assert _safe_openai_request_id("x" * 256) is None


def test_qualification_provider_limit_covers_two_tools_and_final_answer():
    from backend.services.chat_provider_gateway.lifecycle import (
        QUALIFICATION_PROVIDER_REQUESTS,
        QUALIFICATION_PROVIDER_TURN_TOKENS,
    )
    from backend.services.chat_provider_gateway.lifecycle import (
        provider_turn_limits as _provider_turn_limits,
    )

    database = SimpleNamespace(scalar=lambda _query: "32-functional-turns")
    limits = _provider_turn_limits(
        SimpleNamespace(turn_id=object(), scopes=[]),
        database,
        SimpleNamespace(environment="staging"),
    )

    assert limits == (
        QUALIFICATION_PROVIDER_REQUESTS,
        QUALIFICATION_PROVIDER_TURN_TOKENS,
    )
    assert limits[0] == 3
    assert limits[1] == 3 * (MAX_REQUEST_BYTES // 4 + 8_000)


def test_production_provider_limits_never_query_staging_qualification_tables():
    from backend.chat_execution_policy import MAX_PROVIDER_REQUESTS
    from backend.services.chat_provider_gateway.lifecycle import (
        provider_turn_limits as _provider_turn_limits,
    )

    def unexpected_query(_query):
        raise AssertionError("production queried staging qualification state")

    limits = _provider_turn_limits(
        SimpleNamespace(turn_id=object(), scopes=[]),
        SimpleNamespace(scalar=unexpected_query),
        SimpleNamespace(environment="production"),
    )

    assert limits[0] == MAX_PROVIDER_REQUESTS
