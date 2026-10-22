"""Funded OpenRouter dispatch through the gateway and its usage extraction."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend import chat_gateway_app as gateway
from backend.services.chat_provider_gateway import (
    anthropic_messages,
    ledgers,
    lifecycle,
)
from backend.config import Settings
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetUnavailable,
)
from backend.services.openrouter_usage_extractor import OpenRouterUsageExtractor
from backend.services.openrouter_user_budget_service import (
    OpenRouterAbuseLimitExceeded,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "chat_enabled": True,
        "chat_openrouter_credential_keyring": '{"1":"%s"}'
        % base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
        "chat_openrouter_credential_active_key_version": 1,
        "chat_openrouter_pricing_verified_at": "2026-08-02",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_streaming_usage_extraction_handles_chunks_duplicates_and_bytes():
    raw = (
        b"event: message_delta\n"
        b'data: {"type":"message_delta","id":"gen-1","usage":'
        b'{"cost":0.001234,"input_tokens":12,"output_tokens":34}}\n\n'
    )
    extractor = OpenRouterUsageExtractor()
    forwarded = []
    for index in range(0, len(raw), 7):
        chunk = raw[index : index + 7]
        forwarded.append(chunk)
        extractor.feed(chunk)
    extractor.feed(raw)
    result = extractor.result()
    assert b"".join(forwarded) == raw
    assert result.cost_microusd == 1234
    assert result.generation_id == "gen-1"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 34


def test_usage_extraction_captures_provider_reasoning_and_cache_details():
    extractor = OpenRouterUsageExtractor()
    extractor.inspect_complete_response(
        b'{"id":"gen-2","provider":"Baseten","usage":{'
        b'"prompt_tokens":100,"completion_tokens":40,'
        b'"prompt_tokens_details":{"cached_tokens":75},'
        b'"completion_tokens_details":{"reasoning_tokens":30}}}'
    )

    result = extractor.result()
    assert result.provider == "Baseten"
    assert result.cache_read_tokens == 75
    assert result.reasoning_tokens == 30


def test_gateway_releases_capability_lock_before_openrouter_budget_check(monkeypatch):
    class FakeDB:
        commits = 0

        def commit(self):
            self.commits += 1

        def rollback(self):
            return None

        def scalar(self, _query):
            return None

    class FakeCapabilityService:
        def __init__(self, _db):
            pass

        def meter_provider(self, row, **_kwargs):
            row.provider_requests += 1

    class FakeRequest:
        def __init__(self):
            self.headers = {}

        async def body(self):
            return json.dumps(
                {"model": row.model, "max_tokens": 100, "messages": []}
            ).encode()

    settings = _settings()
    row = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        model=settings.chat_deepseek_v4_flash_openrouter_route,
        provider_mode="openrouter_funded",
        provider_requests=0,
    )
    db = FakeDB()

    async def slow_budget_check(_settings):
        assert db.commits == 1
        raise OpenRouterBudgetUnavailable("provider timed out")

    monkeypatch.setattr(gateway, "_scope", lambda *_args, **_kwargs: row)
    monkeypatch.setattr(gateway, "_capability_owner", lambda *_args: "hf-user")
    monkeypatch.setattr(
        anthropic_messages,
        "provider_target",
        lambda *_args: ("https://openrouter.ai/api/v1/messages", "token", None),
    )
    monkeypatch.setattr(lifecycle, "ChatCapabilityService", FakeCapabilityService)
    monkeypatch.setattr(ledgers, "require_openrouter_budget", slow_budget_check)
    monkeypatch.setattr(lifecycle, "record_provider_error", lambda *_args: None)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            gateway.messages(
                FakeRequest(),
                "Bearer capability",
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                None,
                db,
                settings,
            )
        )

    assert error.value.status_code == 503
    assert db.commits == 1


def test_gateway_reports_funded_abuse_limit_without_dispatch(monkeypatch):
    class FakeDB:
        commits = 0
        rollbacks = 0

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def scalar(self, _query):
            return None

    class FakeCapabilityService:
        def __init__(self, _db):
            pass

        def meter_provider(self, row, **_kwargs):
            row.provider_requests += 1

    class LimitedBudgetService:
        def __init__(self, *_args):
            pass

        def reserve_call(self, *_args, **_kwargs):
            raise OpenRouterAbuseLimitExceeded("global_rate", datetime.now(UTC))

    class FakeRequest:
        def __init__(self):
            self.headers = {}

        async def body(self):
            return (
                b'{"model":"deepseek/deepseek-v4-flash-0731",'
                b'"max_tokens":100,"messages":[]}'
            )

    settings = _settings()
    row = SimpleNamespace(
        id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        model=settings.chat_deepseek_v4_flash_openrouter_route,
        provider_mode="openrouter_funded",
        provider_requests=0,
        reasoning_effort="high",
    )
    db = FakeDB()

    async def allow_budget(_settings):
        return None

    recorded = []
    monkeypatch.setattr(gateway, "_scope", lambda *_args, **_kwargs: row)
    monkeypatch.setattr(gateway, "_capability_owner", lambda *_args: "hf-user")
    monkeypatch.setattr(
        anthropic_messages,
        "provider_target",
        lambda *_args: ("https://openrouter.ai/api/v1/messages", "token", None),
    )
    monkeypatch.setattr(lifecycle, "ChatCapabilityService", FakeCapabilityService)
    monkeypatch.setattr(ledgers, "OpenRouterUserBudgetService", LimitedBudgetService)
    monkeypatch.setattr(ledgers, "require_openrouter_budget", allow_budget)
    monkeypatch.setattr(
        lifecycle, "record_provider_error", lambda *args: recorded.append(args)
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            gateway.messages(
                FakeRequest(),
                "Bearer capability",
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                None,
                db,
                settings,
            )
        )

    assert error.value.status_code == 429
    assert error.value.detail["code"] == "openrouter_global_rate_limited"
    assert error.value.detail["byok_settings_available"] is True
    assert error.value.headers == {"Retry-After": "1"}
    assert recorded[0][1] == "openrouter_global_rate_limited"
    assert db.rollbacks == 1


def test_usage_extraction_missing_malformed_or_conflicting_cost_is_unknown():
    extractor = OpenRouterUsageExtractor()
    extractor.feed(b"data: not-json\n\n")
    extractor.feed(b'data: {"usage":{"cost":0.1}}\n\n')
    extractor.feed(b'data: {"usage":{"cost":0.2}}\n\n')
    assert extractor.result().cost_microusd is None
