from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models.database import (
    ChatExecutorTransportAlert,
    ChatExecutorTransportCircuit,
    ChatTurnAdmissionBudget,
    ChatTurnReservation,
)
from backend.config import Settings
from backend.services.chat_executor_turn_admission import (
    ChatExecutorTurnAdmission,
    maximum_provider_turn_microusd,
)
from backend.services.chat_executor_transport_circuit import (
    ChatTransportUnavailable,
    ExecutorTransportCircuit,
)
from backend.services.chat_turn_admission import ChatTurnAdmissionService

NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)


def test_transport_circuit_migration_sets_environment_role_boundaries():
    migration = (
        Path(__file__).parents[2]
        / "database/migrations/add_chat_executor_transport_circuit.sql"
    ).read_text()
    lowered = migration.lower()

    assert "if current_schema() = 'staging'" in lowered
    assert "elsif current_schema() = 'public'" in lowered
    assert (
        "alter table chat_executor_transport_circuits owner to pwc_staging_owner"
        in lowered
    )
    assert (
        "alter table chat_executor_transport_alerts owner to pwc_staging_owner"
        in lowered
    )
    assert "grant select,insert,update,delete on" in lowered
    assert "to pwc_staging" in lowered
    assert "from paperswithcode_user" in lowered
    assert "transport circuit migration requires staging or public schema" in lowered


def test_provider_turn_reserve_prices_the_full_selected_model_envelope():
    settings = Settings(_env_file=None, environment="staging")
    assert (
        maximum_provider_turn_microusd(
            settings, model_route=settings.chat_luna_route, now=NOW
        )
        == 36_160_000
    )

    direct = Settings(
        _env_file=None,
        environment="staging",
        chat_openai_direct_enabled=True,
    )
    assert (
        maximum_provider_turn_microusd(
            direct, model_route=direct.chat_openai_luna_route, now=NOW
        )
        == 8_000_000
    )


def test_live_turn_admission_persists_the_route_health_decision():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (
        ChatTurnAdmissionBudget,
        ChatTurnReservation,
        ChatExecutorTransportCircuit,
        ChatExecutorTransportAlert,
    ):
        model.__table__.create(engine)
    settings = Settings(
        _env_file=None,
        environment="staging",
        chat_executor_remote_transport_enabled=True,
    )

    def runtime_factory(_settings, _sessions):
        return SimpleNamespace(route_health_seconds=lambda _db: 0.125)

    with Session(engine, expire_on_commit=False) as session:
        reservation = ChatExecutorTurnAdmission(
            settings, runtime_factory=runtime_factory
        ).reserve(
            session,
            turn_id=uuid.uuid4(),
            request_id="live-route-request",
            owner_id="owner-live-route",
            model_route=settings.chat_model_routes[
                settings.chat_model_choices[0]["id"]
            ],
            now=NOW,
        )

        assert reservation.transport == "persistent"
        assert session.get(ChatTurnReservation, reservation.turn_id).transport == (
            "persistent"
        )


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatExecutorTransportCircuit.__table__.create(engine)
    ChatExecutorTransportAlert.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        circuit = ExecutorTransportCircuit(environment="staging")
        circuit.initialize(session, now=NOW)
        yield session, circuit


def test_default_off_and_exact_five_second_route_health(db):
    session, circuit = db
    assert (
        circuit.choose(
            session,
            remote_enabled=False,
            route_health_seconds=0,
            canary_owner="worker-a",
            now=NOW,
        ).transport
        == "legacy"
    )
    assert (
        circuit.choose(
            session,
            remote_enabled=True,
            route_health_seconds=5,
            canary_owner="worker-a",
            now=NOW,
        ).transport
        == "persistent"
    )
    assert (
        circuit.choose(
            session,
            remote_enabled=True,
            route_health_seconds=5.001,
            canary_owner="worker-a",
            now=NOW,
        ).transport
        == "legacy"
    )


def test_both_paths_unavailable_returns_typed_prework_rejection(db):
    session, circuit = db

    with pytest.raises(ChatTransportUnavailable) as exc_info:
        circuit.choose(
            session,
            remote_enabled=True,
            route_health_seconds=None,
            canary_owner="worker-a",
            now=NOW,
            legacy_available=False,
        )

    assert exc_info.value.code == "chat_unavailable"
    assert session.query(ChatExecutorTransportAlert).count() == 0


def test_three_failures_inside_sixty_seconds_open_for_thirty(db):
    session, circuit = db
    assert not circuit.record_attach_failure(session, now=NOW)
    assert not circuit.record_attach_failure(session, now=NOW + timedelta(seconds=59))
    assert circuit.record_attach_failure(session, now=NOW + timedelta(seconds=60))

    blocked = circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=1,
        canary_owner="worker-a",
        now=NOW + timedelta(seconds=89.999),
    )
    canary = circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=1,
        canary_owner="worker-a",
        now=NOW + timedelta(seconds=90),
    )
    other = circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=1,
        canary_owner="worker-b",
        now=NOW + timedelta(seconds=90),
    )
    assert blocked.transport == "legacy"
    assert canary.transport == "persistent" and canary.canary
    assert other.transport == "legacy"


def test_failure_outside_window_resets_and_success_resets_closed_counter(db):
    session, circuit = db
    circuit.record_attach_failure(session, now=NOW)
    circuit.record_attach_failure(session, now=NOW + timedelta(seconds=61))
    row = session.get(ChatExecutorTransportCircuit, "staging")
    assert row.consecutive_failures == 1
    circuit.record_success(session, now=NOW + timedelta(seconds=62))
    assert row.consecutive_failures == 0


def test_failed_canary_reopens_and_three_successes_close(db):
    session, circuit = db
    for offset in range(3):
        circuit.record_attach_failure(session, now=NOW + timedelta(seconds=offset))
    circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=1,
        canary_owner="worker-a",
        now=NOW + timedelta(seconds=32),
    )
    assert circuit.record_attach_failure(
        session, now=NOW + timedelta(seconds=32), canary_owner="worker-a"
    )
    circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=1,
        canary_owner="worker-a",
        now=NOW + timedelta(seconds=63),
    )
    assert not circuit.record_success(
        session, now=NOW + timedelta(seconds=63), canary_owner="worker-a"
    )
    assert not circuit.record_success(
        session, now=NOW + timedelta(seconds=64), canary_owner="worker-a"
    )
    assert circuit.record_success(
        session, now=NOW + timedelta(seconds=65), canary_owner="worker-a"
    )
    assert session.get(ChatExecutorTransportCircuit, "staging").state == "closed"


def test_security_hold_bypasses_half_open_and_requires_proven_clear(db):
    session, circuit = db
    epoch = circuit.security_hold(session, reason="key_compromise", now=NOW)
    assert epoch == 1
    decision = circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=0,
        canary_owner="worker-a",
        now=NOW + timedelta(hours=1),
    )
    assert decision.state == "security_hold" and decision.transport == "legacy"
    assert not circuit.clear_security_hold(
        session,
        replacement_credentials_proven=True,
        affected_live_generations=1,
        now=NOW,
    )
    assert circuit.clear_security_hold(
        session,
        replacement_credentials_proven=True,
        affected_live_generations=0,
        now=NOW,
    )


def test_state_survives_service_restart(db):
    session, circuit = db
    for offset in range(3):
        circuit.record_attach_failure(session, now=NOW + timedelta(seconds=offset))
    restarted = ExecutorTransportCircuit(environment="staging")
    assert (
        restarted.choose(
            session,
            remote_enabled=True,
            route_health_seconds=1,
            canary_owner="worker-a",
            now=NOW + timedelta(seconds=3),
        ).transport
        == "legacy"
    )


def test_open_and_recovery_alerts_are_persisted_once_per_durable_epoch(db):
    session, circuit = db
    for offset in range(3):
        circuit.record_attach_failure(session, now=NOW + timedelta(seconds=offset))

    assert (
        session.get(
            ChatExecutorTransportAlert, "executor-circuit:staging:1:open"
        ).delivery_state
        == "pending"
    )

    circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=1,
        canary_owner="worker-a",
        now=NOW + timedelta(seconds=32),
    )
    for offset in range(3):
        circuit.record_success(
            session,
            now=NOW + timedelta(seconds=32 + offset),
            canary_owner="worker-a",
        )
    assert (
        session.get(
            ChatExecutorTransportAlert, "executor-circuit:staging:1:recovered"
        ).delivery_state
        == "pending"
    )
    assert (
        session.query(ChatExecutorTransportAlert)
        .filter(ChatExecutorTransportAlert.epoch == 1)
        .count()
        == 2
    )


def test_expired_half_open_lease_moves_to_one_new_canary(db):
    session, circuit = db
    for offset in range(3):
        circuit.record_attach_failure(session, now=NOW + timedelta(seconds=offset))
    first = circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=1,
        canary_owner="worker-a",
        now=NOW + timedelta(seconds=32),
    )
    blocked = circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=1,
        canary_owner="worker-b",
        now=NOW + timedelta(seconds=61),
    )
    replacement = circuit.choose(
        session,
        remote_enabled=True,
        route_health_seconds=1,
        canary_owner="worker-b",
        now=NOW + timedelta(seconds=62),
    )

    assert first.canary
    assert blocked.transport == "legacy"
    assert replacement.transport == "persistent" and replacement.canary


def test_half_open_canary_is_visible_across_api_worker_sessions(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'circuit.db'}")
    ChatExecutorTransportCircuit.__table__.create(engine)
    ChatExecutorTransportAlert.__table__.create(engine)
    with Session(engine) as setup:
        circuit = ExecutorTransportCircuit(environment="staging")
        circuit.initialize(setup, now=NOW)
        for offset in range(3):
            circuit.record_attach_failure(setup, now=NOW + timedelta(seconds=offset))
        setup.commit()
    with Session(engine) as worker_a:
        chosen = circuit.choose(
            worker_a,
            remote_enabled=True,
            route_health_seconds=1,
            canary_owner="worker-a",
            now=NOW + timedelta(seconds=32),
        )
        worker_a.commit()
    with Session(engine) as worker_b:
        blocked = circuit.choose(
            worker_b,
            remote_enabled=True,
            route_health_seconds=1,
            canary_owner="worker-b",
            now=NOW + timedelta(seconds=32),
        )

    assert chosen.transport == "persistent" and chosen.canary
    assert blocked.transport == "legacy" and not blocked.canary


def test_transport_is_selected_once_before_reservation_and_never_mutated():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatTurnAdmissionBudget.__table__.create(engine)
    ChatTurnReservation.__table__.create(engine)
    ChatExecutorTransportCircuit.__table__.create(engine)
    ChatExecutorTransportAlert.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        circuit = ExecutorTransportCircuit(environment="staging")
        admission = ChatTurnAdmissionService(
            environment="staging", spend_limit_microusd=1_000_000
        )
        circuit.initialize(session, now=NOW)
        admission.initialize(session, now=NOW)
        selected = circuit.choose(
            session,
            remote_enabled=True,
            route_health_seconds=1,
            canary_owner="worker-a",
            now=NOW,
        )
        first = admission.reserve(
            session,
            turn_id=uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001"),
            request_id="request-1",
            owner_id="owner-1",
            reserve_microusd=100,
            transport=selected.transport,
            now=NOW,
        )
        for offset in range(3):
            circuit.record_attach_failure(session, now=NOW + timedelta(seconds=offset))
        fallback = circuit.choose(
            session,
            remote_enabled=True,
            route_health_seconds=1,
            canary_owner="worker-b",
            now=NOW + timedelta(seconds=3),
        )
        second = admission.reserve(
            session,
            turn_id=uuid.UUID("aaaaaaaa-0000-4000-8000-000000000002"),
            request_id="request-2",
            owner_id="owner-2",
            reserve_microusd=100,
            transport=fallback.transport,
            now=NOW + timedelta(seconds=3),
        )

        assert first.transport == "persistent"
        assert second.transport == "legacy"
        assert session.get(ChatTurnReservation, first.turn_id).transport == "persistent"
