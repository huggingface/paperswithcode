from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    ChatTitleBudgetEvent,
    ChatTitleBudgetState,
    ChatTitleProviderCall,
)
from backend.services.chat_title_budget_service import (
    ChatTitleBudgetService,
    ChatTitleBudgetUnavailable,
)


def _settings(environment: str) -> Settings:
    return Settings(
        _env_file=None,
        environment=environment,
        release_id=f"title-{environment}",
        chat_title_monthly_cap_microusd=25_000,
        chat_title_warning_microusd=20_000,
        chat_title_max_call_microusd=10_000,
        chat_title_input_microusd_per_token=1,
        chat_title_output_microusd_per_token=2,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    for table in (
        ChatTitleBudgetState.__table__,
        ChatTitleProviderCall.__table__,
        ChatTitleBudgetEvent.__table__,
    ):
        table.create(engine)
    with Session(engine) as session:
        yield session


def test_title_reservation_is_idempotent_and_settles_provider_usage(db: Session):
    service = ChatTitleBudgetService(db, _settings("staging"))
    call_id = uuid.uuid4()
    first = service.reserve_call(call_id)
    replay = service.reserve_call(call_id)

    assert first.reserved_microusd == 10_000
    assert replay.idempotent_replay is True
    state = db.scalar(select(ChatTitleBudgetState))
    assert state.reserved_microusd == 10_000

    service.mark_dispatched(call_id)
    assert (
        service.settle_call(
            call_id,
            input_tokens=10,
            output_tokens=5,
            provider_generation_id="generation-1",
        )
        == 20
    )

    db.refresh(state)
    call = db.get(ChatTitleProviderCall, call_id)
    assert state.reserved_microusd == 0
    assert state.spent_microusd == 20
    assert call.state == "settled"
    assert call.provider_generation_id == "generation-1"


def test_unknown_title_usage_charges_the_full_conservative_reservation(db: Session):
    service = ChatTitleBudgetService(db, _settings("staging"))
    call_id = uuid.uuid4()
    service.reserve_call(call_id)
    service.mark_dispatched(call_id)

    assert service.settle_call(call_id, input_tokens=None, output_tokens=None) == 10_000


def test_title_circuit_warns_then_fails_closed_before_exceeding_cap(db: Session):
    service = ChatTitleBudgetService(db, _settings("staging"))
    first = uuid.uuid4()
    second = uuid.uuid4()
    service.reserve_call(first)
    service.reserve_call(second)

    state = db.scalar(select(ChatTitleBudgetState))
    assert state.circuit_state == "warning"
    assert (
        db.scalar(
            select(ChatTitleBudgetEvent.event_type).where(
                ChatTitleBudgetEvent.budget_state_id == state.id
            )
        )
        == "warning"
    )

    with pytest.raises(ChatTitleBudgetUnavailable, match="exhausted"):
        service.reserve_call(uuid.uuid4())

    assert state.circuit_state == "warning"
    assert set(db.scalars(select(ChatTitleBudgetEvent.event_type))) == {"warning"}

    service.mark_dispatched(first)
    service.mark_dispatched(second)
    service.settle_call(first, input_tokens=None, output_tokens=None)
    service.settle_call(second, input_tokens=None, output_tokens=None)
    with pytest.raises(ChatTitleBudgetUnavailable, match="exhausted"):
        service.reserve_call(uuid.uuid4())

    assert state.circuit_state == "tripped"
    assert set(db.scalars(select(ChatTitleBudgetEvent.event_type))) == {
        "warning",
        "exhausted",
    }


def test_staging_and_production_title_ledgers_are_independent(db: Session):
    now = datetime(2026, 8, 5, tzinfo=UTC)
    ChatTitleBudgetService(db, _settings("staging")).reserve_call(uuid.uuid4(), now=now)
    ChatTitleBudgetService(db, _settings("production")).reserve_call(
        uuid.uuid4(), now=now
    )

    states = list(
        db.scalars(
            select(ChatTitleBudgetState).order_by(ChatTitleBudgetState.environment)
        )
    )
    assert [state.environment for state in states] == ["production", "staging"]
    assert [state.reserved_microusd for state in states] == [10_000, 10_000]


def test_call_identifier_cannot_cross_title_environment_boundary(db: Session):
    call_id = uuid.uuid4()
    ChatTitleBudgetService(db, _settings("staging")).reserve_call(call_id)

    with pytest.raises(ChatTitleBudgetUnavailable, match="crossed an environment"):
        ChatTitleBudgetService(db, _settings("production")).reserve_call(call_id)


def test_stale_title_calls_release_or_conservatively_settle(db: Session):
    settings = _settings("staging")
    settings.chat_title_monthly_cap_microusd = 40_000
    settings.chat_title_warning_microusd = 30_000
    service = ChatTitleBudgetService(db, settings)
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    reserved = uuid.uuid4()
    dispatched = uuid.uuid4()
    recent = uuid.uuid4()
    service.reserve_call(reserved, now=now - timedelta(minutes=10))
    service.reserve_call(dispatched, now=now - timedelta(minutes=10))
    service.mark_dispatched(dispatched, now=now - timedelta(minutes=9))
    service.reserve_call(recent, now=now - timedelta(seconds=30))

    assert service.reconcile_stale_calls(now=now) == {
        "released": 1,
        "conservatively_settled": 1,
    }

    assert db.get(ChatTitleProviderCall, reserved).state == "released"
    assert db.get(ChatTitleProviderCall, dispatched).state == "settled"
    assert db.get(ChatTitleProviderCall, dispatched).actual_microusd == 10_000
    assert db.get(ChatTitleProviderCall, recent).state == "reserved"
