import uuid
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models.database import ChatTurnAdmissionBudget, ChatTurnReservation
from backend.services.chat_turn_admission import (
    AccountBusy,
    CapacityOverloaded,
    ChatTurnAdmissionService,
    SpendUnavailable,
)

NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatTurnAdmissionBudget.__table__.create(engine)
    ChatTurnReservation.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def service(db):
    value = ChatTurnAdmissionService(
        environment="staging", spend_limit_microusd=1_000_000
    )
    value.initialize(db, now=NOW)
    return value


def _reserve(service, db, ordinal, *, owner=None, amount=10_000):
    return service.reserve(
        db,
        turn_id=uuid.UUID(f"aaaaaaaa-0000-4000-8000-{ordinal:012x}"),
        request_id=f"request-{ordinal}",
        owner_id=owner or f"owner-{ordinal}",
        reserve_microusd=amount,
        now=NOW,
    )


def test_same_account_contention_and_idempotent_request(service, db):
    first = _reserve(service, db, 1, owner="same-owner")

    assert _reserve(service, db, 1, owner="same-owner") == first
    with pytest.raises(AccountBusy) as exc_info:
        _reserve(service, db, 2, owner="same-owner")
    assert exc_info.value.code == "account_busy"


def test_concurrent_same_account_has_one_database_winner(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'turn-admission.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    ChatTurnAdmissionBudget.__table__.create(engine)
    ChatTurnReservation.__table__.create(engine)
    service = ChatTurnAdmissionService(
        environment="staging", spend_limit_microusd=1_000_000
    )
    with Session(engine) as session:
        service.initialize(session, now=NOW)
        session.commit()
    barrier = threading.Barrier(2)
    outcomes = []

    def compete(ordinal):
        with Session(engine) as session:
            barrier.wait()
            try:
                _reserve(service, session, ordinal, owner="same-owner")
                session.commit()
            except AccountBusy:
                session.rollback()
                outcomes.append("busy")
            else:
                outcomes.append("reserved")

    threads = [threading.Thread(target=compete, args=(ordinal,)) for ordinal in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["busy", "reserved"]


def test_exact_32nd_33rd_capacity_boundary_reserves_four_operations(service, db):
    reservations = [_reserve(service, db, ordinal) for ordinal in range(1, 33)]

    with pytest.raises(CapacityOverloaded) as exc_info:
        _reserve(service, db, 33)
    budget = db.get(ChatTurnAdmissionBudget, "staging")
    assert exc_info.value.code == "capacity_overloaded"
    assert budget.active_turns == budget.reserved_environments == 32
    assert budget.reserved_operations == 128
    assert all(item.state == "reserved" for item in reservations)


def test_model_only_turn_reserves_potential_capacity_without_provider_work(service, db):
    provider_calls = []

    reservation = _reserve(service, db, 1)

    row = db.get(ChatTurnReservation, reservation.turn_id)
    assert provider_calls == []
    assert row.reserved_environments == 1
    assert row.reserved_operations == 4


def test_transport_choice_is_persisted_once_at_turn_boundary(service, db):
    turn_id = uuid.uuid4()
    persistent = service.reserve(
        db,
        turn_id=turn_id,
        request_id="transport-choice",
        owner_id="owner-choice",
        reserve_microusd=1,
        now=NOW,
        transport="persistent",
    )

    assert persistent.transport == "persistent"
    with pytest.raises(ValueError, match="identity was reused"):
        service.reserve(
            db,
            turn_id=turn_id,
            request_id="transport-choice",
            owner_id="owner-choice",
            reserve_microusd=1,
            now=NOW,
            transport="legacy",
        )


def test_spend_exhaustion_rejects_unreserved_work(service, db):
    _reserve(service, db, 1, amount=1_000_000)

    with pytest.raises(SpendUnavailable) as exc_info:
        _reserve(service, db, 2, amount=1)
    assert exc_info.value.code == "spend_unavailable"
    assert db.query(ChatTurnReservation).count() == 1


def test_incremental_budget_exhaustion_does_not_abandon_covered_turn(service, db):
    reservation = _reserve(service, db, 1, amount=900_000)
    dispatched = service.mark_dispatched(
        db, turn_id=reservation.turn_id, revision=reservation.revision, now=NOW
    )
    extended = service.reserve_increment(
        db,
        turn_id=reservation.turn_id,
        revision=dispatched.revision,
        amount_microusd=100_000,
        now=NOW,
    )

    with pytest.raises(SpendUnavailable):
        service.reserve_increment(
            db,
            turn_id=reservation.turn_id,
            revision=extended.revision,
            amount_microusd=1,
            now=NOW,
        )
    assert service.settle(
        db,
        turn_id=reservation.turn_id,
        revision=extended.revision,
        outcome="completed",
        actual_microusd=950_000,
        now=NOW + timedelta(seconds=1),
    )
    budget = db.get(ChatTurnAdmissionBudget, "staging")
    assert budget.reserved_microusd == 0
    assert budget.spent_microusd == 950_000
    with pytest.raises(SpendUnavailable):
        _reserve(service, db, 2, amount=50_001)


def test_cancellation_returns_capacity_and_unused_spend_once(service, db):
    reservation = _reserve(service, db, 1, amount=50_000)

    assert service.settle(
        db,
        turn_id=reservation.turn_id,
        revision=reservation.revision,
        outcome="cancelled",
        actual_microusd=0,
        now=NOW,
    )
    assert not service.settle(
        db,
        turn_id=reservation.turn_id,
        revision=reservation.revision,
        outcome="cancelled",
        actual_microusd=0,
        now=NOW,
    )
    budget = db.get(ChatTurnAdmissionBudget, "staging")
    assert budget.active_turns == budget.reserved_environments == 0
    assert budget.reserved_operations == budget.reserved_microusd == 0


def test_process_restart_settles_existing_reservation(service, db):
    reservation = _reserve(service, db, 1, amount=50_000)
    restarted = ChatTurnAdmissionService(
        environment="staging", spend_limit_microusd=1_000_000
    )

    assert restarted.settle(
        db,
        turn_id=reservation.turn_id,
        revision=reservation.revision,
        outcome="failed",
        actual_microusd=25_000,
        now=NOW + timedelta(seconds=1),
    )


def test_stale_settlement_cannot_mutate_successor_revision(service, db):
    reservation = _reserve(service, db, 1)
    dispatched = service.mark_dispatched(
        db, turn_id=reservation.turn_id, revision=reservation.revision, now=NOW
    )

    assert not service.settle(
        db,
        turn_id=reservation.turn_id,
        revision=reservation.revision,
        outcome="failed",
        actual_microusd=0,
        now=NOW,
    )
    assert (
        db.get(ChatTurnReservation, reservation.turn_id).revision == dispatched.revision
    )


def test_unknown_worker_loss_releases_capacity_but_retains_spend_until_reconciled(
    service, db
):
    reservation = _reserve(service, db, 1, amount=50_000)
    assert service.settle(
        db,
        turn_id=reservation.turn_id,
        revision=reservation.revision,
        outcome="failed",
        actual_microusd=None,
        now=NOW,
    )
    unknown = db.get(ChatTurnReservation, reservation.turn_id)
    budget = db.get(ChatTurnAdmissionBudget, "staging")
    assert unknown.state == "cost_unknown"
    assert budget.active_turns == 0
    assert budget.reserved_microusd == 50_000

    assert service.settle(
        db,
        turn_id=reservation.turn_id,
        revision=unknown.revision,
        outcome="failed",
        actual_microusd=40_000,
        now=NOW + timedelta(seconds=1),
    )
    assert budget.reserved_microusd == 0
    assert budget.spent_microusd == 40_000


def test_migration_pins_capacity_spend_and_owner_guards():
    migration = (
        Path(__file__).parents[1] / "database/migrations/add_chat_turn_reservations.sql"
    ).read_text()

    assert "turn_limit = 32" in migration
    assert "operation_limit = 128" in migration
    assert "uq_chat_turn_reservations_active_owner" in migration
    assert "reserved_microusd" in migration
