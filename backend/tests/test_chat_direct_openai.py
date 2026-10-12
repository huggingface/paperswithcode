from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_CEILING
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatOpenAIMonthlyUsage,
    ChatOpenAIProviderCall,
    ChatTurnJob,
)
from backend.services.chat_capability_service import ChatCapabilityService
from backend.services.chat_openai_budget_service import (
    MAX_BILLABLE_INPUT_TOKENS,
    MAX_REQUEST_BYTES,
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
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "jwt_secret": "test-secret-not-for-production",
        "chat_openai_pricing_verified_at": "2026-09-20",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_direct_openai_pricing_uses_per_million_rates_and_fails_stale():
    settings = _settings()
    usage = ExtractedOpenAIUsage(
        input_tokens=1_000_000,
        cached_input_tokens=100_000,
        cache_write_tokens=100_000,
        output_tokens=1_000_000,
    )
    # Long context: 2x input (including cache categories), 1.5x output.
    assert actual_usage_microusd(settings, usage) == 2_174_000
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


def test_direct_openai_accepts_broker_sized_payload_without_reserving_bytes_as_tokens():
    settings = _settings()

    assert MAX_REQUEST_BYTES == 8 * 1024 * 1024
    maximum = safe_maximum_microusd(
        settings,
        OpenAIRequestBounds(
            request_bytes=MAX_REQUEST_BYTES,
            maximum_output_tokens=8_000,
        ),
        now=datetime(2026, 8, 20, tzinfo=UTC),
    )
    token_bounded = safe_maximum_microusd(
        settings,
        OpenAIRequestBounds(
            request_bytes=MAX_BILLABLE_INPUT_TOKENS,
            maximum_output_tokens=8_000,
        ),
        now=datetime(2026, 8, 20, tzinfo=UTC),
    )

    assert maximum == token_bounded


@pytest.mark.parametrize(
    "input_tokens,multiplier", [(272_000, 1), (272_001, 2), (1_000_000, 2)]
)
def test_long_context_accounting_and_reservations(input_tokens, multiplier):
    settings = _settings()
    usage = ExtractedOpenAIUsage(
        input_tokens=input_tokens,
        output_tokens=1000,
        cached_input_tokens=0,
        cache_write_tokens=0,
    )
    actual = actual_usage_microusd(settings, usage)
    expected_input = int(
        (Decimal(input_tokens) * Decimal("0.2") * multiplier).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    assert actual == expected_input + (1800 if multiplier == 2 else 1200)
    assert (
        safe_maximum_microusd(
            settings,
            OpenAIRequestBounds(
                request_bytes=input_tokens * 4, maximum_output_tokens=1000
            ),
            now=datetime(2026, 8, 20, tzinfo=UTC),
        )
        >= actual
    )


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


@pytest.mark.parametrize(
    "age_minutes,turn_state,terminal_age_seconds,expected",
    [
        (16, None, None, 1),
        (2, "interrupted", 90, 1),
        (2, "failed", 90, 1),
        (2, "completed", 90, 1),
        (2, "running", None, 0),
        (2, "interrupted", 10, 0),
    ],
)
def test_stale_dispatch_is_marked_unknown_once_before_ceiling_settlement(
    age_minutes, turn_state, terminal_age_seconds, expected
):
    engine = create_engine("sqlite://")
    ChatOpenAIMonthlyUsage.__table__.create(engine)
    ChatOpenAIProviderCall.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    turn_id = uuid.uuid4()
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
                turn_id=turn_id,
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
        later = now + timedelta(minutes=age_minutes)
        if turn_state:
            db.add(
                ChatTurnJob(
                    turn_id=turn_id,
                    chat_session_id=uuid.uuid4(),
                    hf_user_id="owner",
                    request_id=str(uuid.uuid4()),
                    revision=1,
                    dispatch_class="local",
                    dispatch_route="local",
                    state=turn_state,
                    worker_id="worker",
                    worker_generation=1,
                    lease_generation=1,
                    app_release_id="test",
                    worker_contract_version="test",
                    admitted_at=now,
                    lease_expires_at=later if turn_state == "running" else None,
                    terminal_at=(
                        later - timedelta(seconds=terminal_age_seconds)
                        if terminal_age_seconds is not None
                        else None
                    ),
                )
            )
        db.commit()
        service = ChatOpenAIBudgetService(db, _settings())
        assert service.mark_stale_dispatched_unknown(now=later) == expected
        db.commit()
        assert service.mark_stale_dispatched_unknown(now=later) == 0
        aggregate = db.get(ChatOpenAIMonthlyUsage, ("owner", now.date().replace(day=1)))
        assert aggregate.unknown_cost_calls == expected
        assert aggregate.reserved_microusd == 50_000
        assert aggregate.spent_microusd == 0


class _ConcurrencyDB:
    def __init__(self, values):
        self.values = iter(values)
        self.queries = []

    def scalar(self, query):
        self.queries.append(query)
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


def test_qualification_openai_rate_allows_exact_fixed_workload_per_scope():
    scope_id = uuid.uuid4()
    now = datetime(2026, 8, 31, tzinfo=UTC)
    database = _ConcurrencyDB((63, 63))

    ChatOpenAIBudgetService(database, _settings())._enforce_rate_limits(
        "owner", scope_id, now
    )

    assert all(
        scope_id in query.compile().params.values() for query in database.queries
    )
    with pytest.raises(OpenAILimitExceeded, match="user_rate"):
        ChatOpenAIBudgetService(
            _ConcurrencyDB((64, 0)), _settings()
        )._enforce_rate_limits("owner", scope_id, now)
    with pytest.raises(OpenAILimitExceeded, match="global_rate"):
        ChatOpenAIBudgetService(
            _ConcurrencyDB((63, 64)), _settings()
        )._enforce_rate_limits("owner", scope_id, now)


def test_ordinary_openai_rate_limits_remain_configured():
    now = datetime(2026, 8, 31, tzinfo=UTC)
    settings = _settings(
        chat_openai_user_rate_limit_calls=30,
        chat_openai_global_rate_limit_calls=80,
    )

    with pytest.raises(OpenAILimitExceeded, match="user_rate"):
        ChatOpenAIBudgetService(_ConcurrencyDB((30, 0)), settings)._enforce_rate_limits(
            "owner", None, now
        )
    with pytest.raises(OpenAILimitExceeded, match="global_rate"):
        ChatOpenAIBudgetService(
            _ConcurrencyDB((29, 80)), settings
        )._enforce_rate_limits("owner", None, now)


def test_status_percentage_reports_remaining_monthly_share():
    engine = create_engine("sqlite://")
    ChatOpenAIMonthlyUsage.__table__.create(engine)
    now = datetime(2026, 9, 19, 12, tzinfo=UTC)
    settings = _settings(chat_openai_direct_enabled=True)
    with Session(engine) as db:
        db.add(
            ChatOpenAIMonthlyUsage(
                owner_id="owner",
                month_start=now.date().replace(day=1),
                limit_microusd=1_000_000,
                reserved_microusd=10_000,
                spent_microusd=930_000,
                unknown_cost_calls=0,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        service = ChatOpenAIBudgetService(db, settings)

        status = service.status_percentage("owner", now=now)
        assert status.public_dict() == {
            "used_percent": 94,
            "remaining_percent": 6,
            "resets_at": datetime(2026, 10, 1, tzinfo=UTC),
            "available": True,
            "as_of": now,
        }

        fresh = service.status_percentage("newcomer", now=now)
        assert (fresh.used_percent, fresh.remaining_percent) == (0, 100)

        db.get(
            ChatOpenAIMonthlyUsage, ("owner", now.date().replace(day=1))
        ).spent_microusd = 995_000
        db.commit()
        depleted = service.status_percentage("owner", now=now)
        assert (depleted.remaining_percent, depleted.available) == (0, False)


def test_openai_usage_route_requires_the_direct_route():
    from backend.routers.chat import get_openai_usage

    engine = create_engine("sqlite://")
    ChatOpenAIMonthlyUsage.__table__.create(engine)
    with Session(engine) as db:
        with pytest.raises(HTTPException) as denied:
            get_openai_usage(
                user={"hf_user_id": "owner"},
                db=db,
                settings=_settings(chat_enabled=True, chat_openai_direct_enabled=False),
            )
        assert denied.value.status_code == 404

        payload = get_openai_usage(
            user={"hf_user_id": "owner"},
            db=db,
            settings=_settings(chat_enabled=True, chat_openai_direct_enabled=True),
        )
        assert payload["remaining_percent"] == 100
        assert payload["available"] is True
