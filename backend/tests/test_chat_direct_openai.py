from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import backend.chat_gateway_app as gateway_app
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.chat_gateway_app import _safe_openai_request_id, _trusted_openai_payload
from backend.config import Settings
from backend.models.database import ChatOpenAIMonthlyUsage, ChatOpenAIProviderCall
from backend.services.chat_capability_service import ChatCapabilityService
from backend.services.chat_openai_budget_service import (
    ChatOpenAIBudgetService,
    OpenAIAccountingInvariantError,
    OpenAILimitExceeded,
    OpenAIPricingUnavailable,
    OpenAIRequestBounds,
    actual_usage_microusd,
    safe_maximum_microusd,
)
from backend.services.chat_openai_usage_extractor import (
    ExtractedOpenAIUsage,
    OpenAIResponsesUsageExtractor,
    classify_openai_error,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "jwt_secret": "test-secret-not-for-production",
        "chat_openai_pricing_verified_at": "2026-08-20",
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
            "model": "gpt-5.6-luna",
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
    assert payload["model"] == "gpt-5.6-luna"
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
    "payload",
    [
        {"model": "gpt-5.6-terra", "max_output_tokens": 100},
        {"model": "gpt-5.6-luna", "max_output_tokens": 100, "metadata": {}},
        {
            "model": "gpt-5.6-luna",
            "max_output_tokens": 100,
            "include": ["file_search_call.results"],
        },
        {
            "model": "gpt-5.6-luna",
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


def test_direct_openai_pricing_uses_per_million_rates_and_fails_stale():
    settings = _settings()
    usage = ExtractedOpenAIUsage(
        input_tokens=1_000_000,
        cached_input_tokens=100_000,
        cache_write_tokens=100_000,
        output_tokens=1_000_000,
    )
    # 800k ordinary input + 100k cache read + 100k cache write + 1m output.
    assert actual_usage_microusd(settings, usage) == 1_387_000
    assert (
        safe_maximum_microusd(
            settings,
            OpenAIRequestBounds(request_bytes=1000, maximum_output_tokens=1000),
            now=datetime(2026, 8, 20, tzinfo=UTC),
        )
        == 1450
    )
    with pytest.raises(OpenAIPricingUnavailable):
        safe_maximum_microusd(
            _settings(chat_openai_pricing_verified_at="2026-01-01"),
            OpenAIRequestBounds(request_bytes=1000, maximum_output_tokens=1000),
            now=datetime(2026, 8, 20, tzinfo=UTC),
        )


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


def test_direct_openai_capability_refuses_every_provider_credential_field():
    service = ChatCapabilityService(SimpleNamespace())
    base = {
        "chat_session_id": uuid.uuid4(),
        "turn_id": uuid.uuid4(),
        "owner_id": "owner",
        "provider_mode": "openai_funded",
        "model": "gpt-5.6-luna@openai",
        "scopes": {"model"},
        "agent_harness": "pi",
    }
    for credential in (
        {"provider_token": "sk-must-never-enter-capability"},
        {"provider_bill_to": "billing-owner"},
        {"provider_credential_revision": uuid.uuid4()},
    ):
        with pytest.raises(ValueError, match="cannot contain credentials"):
            service.issue(**base, **credential)


def test_stale_unknown_reconciliation_is_bounded_truthful_and_idempotent():
    engine = create_engine("sqlite://")
    ChatOpenAIMonthlyUsage.__table__.create(engine)
    ChatOpenAIProviderCall.__table__.create(engine)
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    call_id = uuid.uuid4()
    with Session(engine) as db:
        db.add(
            ChatOpenAIMonthlyUsage(
                owner_id="owner",
                month_start=now.date().replace(day=1),
                limit_microusd=1_000_000,
                reserved_microusd=50_000,
                spent_microusd=0,
                unknown_cost_calls=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ChatOpenAIProviderCall(
                id=call_id,
                turn_id=uuid.uuid4(),
                call_sequence=1,
                owner_id="owner",
                environment="staging",
                month_start=now.date().replace(day=1),
                public_model_id="gpt-5.6-luna@openai",
                provider_model="gpt-5.6-luna",
                reasoning_effort="low",
                service_tier="default",
                request_bytes=100,
                state="cost_unknown",
                reserved_microusd=50_000,
                reserved_at=now,
                updated_at=now,
            )
        )
        db.commit()
        service = ChatOpenAIBudgetService(db, _settings())
        later = datetime(2026, 8, 20, 12, 16, tzinfo=UTC)
        assert service.settle_stale_unknown_at_reserved_ceiling(now=later) == 1
        db.commit()
        assert service.settle_stale_unknown_at_reserved_ceiling(now=later) == 0
        call = db.get(ChatOpenAIProviderCall, call_id)
        aggregate = db.get(ChatOpenAIMonthlyUsage, ("owner", now.date().replace(day=1)))
        assert call.state == "settled"
        assert call.actual_microusd == 50_000
        assert call.settlement_source == "reserved_ceiling"
        assert call.outcome == "reconciled_reserved_ceiling"
        assert aggregate.reserved_microusd == 0
        assert aggregate.spent_microusd == 50_000
        assert aggregate.unknown_cost_calls == 0


def test_stale_dispatch_is_marked_unknown_once_before_ceiling_settlement():
    engine = create_engine("sqlite://")
    ChatOpenAIMonthlyUsage.__table__.create(engine)
    ChatOpenAIProviderCall.__table__.create(engine)
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    with Session(engine) as db:
        db.add(
            ChatOpenAIMonthlyUsage(
                owner_id="owner",
                month_start=now.date().replace(day=1),
                limit_microusd=1_000_000,
                reserved_microusd=50_000,
                spent_microusd=0,
                unknown_cost_calls=0,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ChatOpenAIProviderCall(
                id=uuid.uuid4(),
                turn_id=uuid.uuid4(),
                call_sequence=1,
                owner_id="owner",
                environment="staging",
                month_start=now.date().replace(day=1),
                public_model_id="gpt-5.6-luna@openai",
                provider_model="gpt-5.6-luna",
                reasoning_effort="low",
                service_tier="default",
                request_bytes=100,
                state="dispatched",
                reserved_microusd=50_000,
                reserved_at=now,
                dispatched_at=now,
                updated_at=now,
            )
        )
        db.commit()
        service = ChatOpenAIBudgetService(db, _settings())
        later = datetime(2026, 8, 20, 12, 16, tzinfo=UTC)
        assert service.mark_stale_dispatched_unknown(now=later) == 1
        db.commit()
        assert service.mark_stale_dispatched_unknown(now=later) == 0
        aggregate = db.get(ChatOpenAIMonthlyUsage, ("owner", now.date().replace(day=1)))
        assert aggregate.unknown_cost_calls == 1


def test_qualification_turns_have_a_fixed_provider_request_ceiling():
    from backend.chat_gateway_app import (
        QUALIFICATION_PROVIDER_REQUESTS,
        QUALIFICATION_PROVIDER_TURN_TOKENS,
        _provider_turn_limits,
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
    assert limits[0] == 2


def test_production_provider_limits_never_query_staging_qualification_tables():
    from backend.chat_gateway_app import MAX_PROVIDER_REQUESTS, _provider_turn_limits

    def unexpected_query(_query):
        raise AssertionError("production queried staging qualification state")

    limits = _provider_turn_limits(
        SimpleNamespace(turn_id=object(), scopes=[]),
        SimpleNamespace(scalar=unexpected_query),
        SimpleNamespace(environment="production"),
    )

    assert limits[0] == MAX_PROVIDER_REQUESTS


class _ConcurrencyDB:
    def __init__(self, values):
        self.values = iter(values)

    def scalar(self, _query):
        return next(self.values)


def test_qualification_openai_concurrency_allows_32_only_for_exact_scope_claim():
    scope_id = uuid.uuid4()
    now = datetime(2026, 8, 31, tzinfo=UTC)
    service = ChatOpenAIBudgetService(_ConcurrencyDB((0, scope_id, 31)), _settings())
    service._enforce_concurrency("owner", uuid.uuid4(), scope_id, now)

    blocked = ChatOpenAIBudgetService(_ConcurrencyDB((0, scope_id, 32)), _settings())
    with pytest.raises(OpenAILimitExceeded, match="global_concurrency"):
        blocked._enforce_concurrency("owner", uuid.uuid4(), scope_id, now)

    forged = ChatOpenAIBudgetService(_ConcurrencyDB((0, uuid.uuid4())), _settings())
    with pytest.raises(OpenAIAccountingInvariantError, match="scope claim"):
        forged._enforce_concurrency("owner", uuid.uuid4(), scope_id, now)


def test_ordinary_openai_global_concurrency_remains_configured_four():
    now = datetime(2026, 8, 31, tzinfo=UTC)
    ChatOpenAIBudgetService(
        _ConcurrencyDB((0, 3)), _settings(chat_openai_global_max_concurrency=4)
    )._enforce_concurrency("owner", uuid.uuid4(), None, now)

    blocked = ChatOpenAIBudgetService(
        _ConcurrencyDB((0, 4)), _settings(chat_openai_global_max_concurrency=4)
    )
    with pytest.raises(OpenAILimitExceeded, match="global_concurrency"):
        blocked._enforce_concurrency("owner", uuid.uuid4(), None, now)
