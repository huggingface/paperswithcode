import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.api import ChatSandboxSpendResponse
from backend.models.chat import ChatSandboxSpendResponse as CanonicalSpendResponse
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
    ChatSession,
    ChatTurnLatency,
)
from backend.scripts.manage_chat_sandbox_circuit import (
    operator_identity,
    reviewed_higher_caps_allowed,
)
from backend.scripts.manage_chat_sandbox_circuit import (
    parser as circuit_parser,
)
from backend.services import chat_sandbox_service
from backend.services.chat_sandbox_capacity_repository import (
    ChatSandboxCapacityRepository,
)
from backend.services.chat_sandbox_service import SandboxError, SandboxSessionManager
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
    billing_cycle,
)
from backend.services.chat_sandbox_state_repository import ChatSandboxStateRepository


def factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for table in (
        ChatSession.__table__,
        ChatSandboxLease.__table__,
        ChatSandboxPool.__table__,
        ChatSandboxBudgetState.__table__,
        ChatSandboxComputeInterval.__table__,
        ChatSandboxCircuitEvent.__table__,
        ChatTurnLatency.__table__,
    ):
        table.create(engine, checkfirst=True)
    return sessionmaker(engine, expire_on_commit=False)


def settings(**values):
    return Settings(
        **{
            "environment": "staging",
            "release_id": "release",
            "chat_modal_image_version": "im-test",
            "chat_sandbox_spend_enforcement_enabled": True,
            "chat_sandbox_budget_attestation": "attested",
            "chat_sandbox_warning_microusd": 75_000_000,
            "chat_sandbox_application_cap_microusd": 100_000_000,
            "chat_sandbox_environment_cap_microusd": 125_000_000,
            "chat_sandbox_workspace_cap_microusd": 250_000_000,
            "chat_sandbox_cpu": 1,
            "chat_sandbox_cpu_limit": 1,
            "chat_sandbox_memory_mib": 2048,
            "chat_sandbox_memory_limit_mib": 2048,
            **values,
        }
    )


def test_lifecycle_meter_includes_reservation_to_confirmed_termination():
    sessions = factory()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        interval_id = service.reserve_interval(
            origin="direct", worker_generation="generation", now=start
        )
        service.provider_created(interval_id, "sb-1", start + timedelta(seconds=5))
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        state = service.refresh(start + timedelta(seconds=65))
        assert state.estimated_accrued_microusd == 65 * service.cost_per_second()
        service.terminate(
            "sb-1", "complete", confirmed=True, now=start + timedelta(seconds=70)
        )
        state = service.refresh(start + timedelta(seconds=90))
        assert state.estimated_accrued_microusd == 70 * service.cost_per_second()
        assert state.outstanding_reservation_microusd == 0


def test_lifecycle_meter_uses_requests_not_burst_limits():
    sessions = factory()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    configured = settings(
        chat_sandbox_cpu=0.5,
        chat_sandbox_cpu_limit=1,
        chat_sandbox_memory_mib=512,
        chat_sandbox_memory_limit_mib=2048,
    )
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        interval_id = service.reserve_interval(
            origin="direct", worker_generation="requested", now=start
        )
        service.provider_created(interval_id, "sb-requested", start)
        service.terminate(
            "sb-requested",
            "complete",
            confirmed=True,
            now=start + timedelta(seconds=10),
        )
        state = service.refresh(start + timedelta(seconds=20))
        interval = db.get(ChatSandboxComputeInterval, interval_id)
        assert service._interval_rate(interval) == 24
        assert state.estimated_accrued_microusd == 240


def test_refresh_reconciles_open_interval_for_terminal_lease():
    sessions = factory()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    terminal_at = start + timedelta(seconds=90)
    session_id = uuid.uuid4()
    configured = settings()
    with sessions() as db, db.begin():
        db.add(
            ChatSession(
                id=session_id,
                hf_user_id="terminal-owner",
                hf_username="terminal-owner",
                selected_model="google/gemma-4-31B-it",
                execution_backend="modal_cli",
            )
        )
        service = ChatSandboxSpendService(db, configured)
        interval_id = service.reserve_interval(
            origin="blank_pool", worker_generation="terminal", now=start
        )
        service.provider_created(interval_id, "sb-terminal", start)
        service.claim("sb-terminal", session_id, start + timedelta(seconds=10))
        db.add(
            ChatSandboxLease(
                chat_session_id=session_id,
                modal_sandbox_id=None,
                app_release_id=configured.release_id,
                image_version=configured.chat_modal_image_version,
                worker_contract_version=configured.chat_worker_contract_version,
                worker_generation="terminal",
                state="failed",
                last_activity_at=terminal_at,
                updated_at=terminal_at,
            )
        )

    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        state = service.refresh(start + timedelta(days=2))
        interval = db.get(ChatSandboxComputeInterval, interval_id)
        assert service._aware(interval.terminal_at) == terminal_at
        assert interval.terminal_reason == "lease_terminal_reconciled"
        assert interval.reconciliation_state == "confirmed"
        assert interval.reserved_microusd == 0
        assert state.estimated_accrued_microusd == 90 * service.cost_per_second()


def test_exact_terminal_lease_reconciliation_does_not_touch_other_sessions():
    sessions = factory()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    terminal_at = start + timedelta(seconds=90)
    targeted_session_id = uuid.uuid4()
    unrelated_session_id = uuid.uuid4()
    configured = settings()
    interval_ids = {}
    with sessions() as db, db.begin():
        leases = []
        for label, session_id in (
            ("targeted", targeted_session_id),
            ("unrelated", unrelated_session_id),
        ):
            db.add(
                ChatSession(
                    id=session_id,
                    hf_user_id=f"{label}-owner",
                    hf_username=f"{label}-owner",
                    selected_model="google/gemma-4-31B-it",
                    execution_backend="modal_cli",
                )
            )
            service = ChatSandboxSpendService(db, configured)
            interval_id = service.reserve_interval(
                origin="blank_pool", worker_generation=label, now=start
            )
            interval_ids[label] = interval_id
            service.provider_created(interval_id, f"sb-{label}", start)
            service.claim(f"sb-{label}", session_id, start + timedelta(seconds=10))
            leases.append(
                ChatSandboxLease(
                    chat_session_id=session_id,
                    modal_sandbox_id=None,
                    app_release_id=configured.release_id,
                    image_version=configured.chat_modal_image_version,
                    worker_contract_version=configured.chat_worker_contract_version,
                    worker_generation=label,
                    state="failed",
                    last_activity_at=terminal_at,
                    updated_at=terminal_at,
                )
            )
        db.add_all(leases)

    with sessions() as db, db.begin():
        settled = ChatSandboxSpendService(db, configured).reconcile_terminal_sessions(
            (targeted_session_id,), now=start + timedelta(minutes=2)
        )
        targeted = db.get(ChatSandboxComputeInterval, interval_ids["targeted"])
        unrelated = db.get(ChatSandboxComputeInterval, interval_ids["unrelated"])

    assert settled == 1
    assert targeted.terminal_at.replace(tzinfo=UTC) == terminal_at
    assert targeted.terminal_reason == "lease_terminal_reconciled"
    assert unrelated.terminal_at is None


def test_refresh_reconciles_interval_superseded_by_later_session_worker():
    sessions = factory()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    successor_at = start + timedelta(minutes=5)
    session_id = uuid.uuid4()
    configured = settings()
    with sessions() as db, db.begin():
        db.add(
            ChatSession(
                id=session_id,
                hf_user_id="superseded-owner",
                hf_username="superseded-owner",
                selected_model="google/gemma-4-31B-it",
                execution_backend="modal_cli",
            )
        )
        service = ChatSandboxSpendService(db, configured)
        old_id = service.reserve_interval(
            origin="blank_pool", worker_generation="old", now=start
        )
        service.provider_created(old_id, "sb-old", start)
        service.claim("sb-old", session_id, start + timedelta(seconds=10))
        new_id = service.reserve_interval(
            origin="direct", worker_generation="new", now=successor_at
        )
        service.provider_created(new_id, "sb-new", successor_at)
        service.claim("sb-new", session_id, successor_at)
        db.add(
            ChatSandboxLease(
                chat_session_id=session_id,
                modal_sandbox_id="sb-new",
                app_release_id=configured.release_id,
                image_version=configured.chat_modal_image_version,
                worker_contract_version=configured.chat_worker_contract_version,
                worker_generation="new",
                state="idle",
                last_activity_at=successor_at,
                updated_at=successor_at,
            )
        )

    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        service.refresh(successor_at + timedelta(minutes=1))
        old = db.get(ChatSandboxComputeInterval, old_id)
        new = db.get(ChatSandboxComputeInterval, new_id)
        assert service._aware(old.terminal_at) == successor_at
        assert old.terminal_reason == "lease_superseded_reconciled"
        assert old.reserved_microusd == 0
        assert new.terminal_at is None


def test_cancelled_start_releases_pre_provider_reservation():
    sessions = factory()
    configured = settings()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(
            ChatSession(
                id=session_id,
                hf_user_id="cancelled-start-owner",
                hf_username="cancelled-start-owner",
                selected_model="google/gemma-4-31B-it",
                execution_backend="modal_cli",
            )
        )

    async def enforce_warm_cap():
        return 0

    class Provider:
        async def create(self, **_options):
            raise asyncio.CancelledError

    state_repository = ChatSandboxStateRepository(configured)
    manager = SandboxSessionManager(
        configured,
        session_factory=sessions,
        sandbox_provider=Provider(),
        state_repository=state_repository,
        capacity_repository=ChatSandboxCapacityRepository(
            configured,
            state_repository,
            start_locker=lambda *_args: None,
        ),
    )
    manager._acquisition_coordinator().lease_maintenance.enforce_warm_cap = (
        enforce_warm_cap
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(manager.ensure_ready(session_id))

    with sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
        interval = db.execute(select(ChatSandboxComputeInterval)).scalar_one()
    assert lease.state == "failed"
    assert lease.failure_code == "sandbox_start_failed"
    assert interval.provider_created_at is None
    assert interval.terminal_at is not None
    assert interval.reserved_microusd == 0
    assert interval.reconciliation_state == "creation_failed"


def test_terminal_pool_owner_releases_abandoned_pre_provider_reservation():
    sessions = factory()
    configured = settings()
    now = datetime(2026, 8, 4, 7, 25, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        abandoned_id = service.reserve_interval(
            origin="blank_pool", worker_generation="abandoned", now=now
        )
        active_id = service.reserve_interval(
            origin="blank_pool", worker_generation="active", now=now
        )
        db.add_all(
            [
                ChatSandboxPool(
                    id=uuid.uuid4(),
                    state="terminated",
                    image_version=configured.chat_modal_image_version,
                    worker_contract_version=configured.chat_worker_contract_version,
                    worker_generation="abandoned",
                    app_release_id="prior-release",
                    created_at=now,
                    expires_at=now + timedelta(hours=1),
                    terminated_at=now,
                    updated_at=now,
                    cpu_request=1,
                    cpu_limit=1,
                    memory_request_mib=2048,
                    memory_limit_mib=2048,
                    billing_month=now.date().replace(day=1),
                ),
                ChatSandboxPool(
                    id=uuid.uuid4(),
                    state="starting",
                    image_version=configured.chat_modal_image_version,
                    worker_contract_version=configured.chat_worker_contract_version,
                    worker_generation="active",
                    app_release_id=configured.release_id,
                    created_at=now,
                    expires_at=now + timedelta(hours=1),
                    updated_at=now,
                    cpu_request=1,
                    cpu_limit=1,
                    memory_request_mib=2048,
                    memory_limit_mib=2048,
                    billing_month=now.date().replace(day=1),
                ),
            ]
        )

    with sessions() as db, db.begin():
        released = ChatSandboxSpendService(
            db, configured
        ).abort_abandoned_pool_reservations(now + timedelta(seconds=1))

    with sessions() as db:
        abandoned = db.get(ChatSandboxComputeInterval, abandoned_id)
        active = db.get(ChatSandboxComputeInterval, active_id)
    assert released == 1
    assert abandoned.terminal_at is not None
    assert abandoned.reserved_microusd == 0
    assert abandoned.reconciliation_state == "creation_failed"
    assert active.terminal_at is None
    assert active.reserved_microusd > 0


def test_creation_failed_interval_without_provider_has_no_compute_cost():
    sessions = factory()
    configured = settings()
    started_at = datetime(2026, 8, 4, tzinfo=UTC)
    failed_at = started_at + timedelta(days=3)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        interval_id = service.reserve_interval(
            origin="direct",
            worker_generation="never-created",
            now=started_at,
        )
        service.abort_reservation(
            interval_id,
            "lease_owner_terminated",
            failed_at,
        )

    with sessions() as db, db.begin():
        status = ChatSandboxSpendService(db, configured).status(
            failed_at + timedelta(hours=1)
        )
        interval = db.get(ChatSandboxComputeInterval, interval_id)

    assert interval.provider_created_at is None
    assert interval.reconciliation_state == "creation_failed"
    assert status["estimated_microusd"] == 0
    assert status["daily_spend"] == []


def test_late_provider_reopens_creation_failed_reservation_until_confirmed():
    sessions = factory()
    configured = settings()
    started_at = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        interval_id = service.reserve_interval(
            origin="blank_pool",
            worker_generation="late-provider",
            now=started_at,
        )
        service.abort_reservation(
            interval_id,
            "pool_owner_terminated",
            started_at + timedelta(seconds=1),
        )

    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, configured)
        service.provider_created(
            interval_id,
            "sb-late-provider",
            started_at + timedelta(seconds=2),
        )
        service.terminate(
            "sb-late-provider",
            "termination_uncertain",
            confirmed=False,
            now=started_at + timedelta(seconds=3),
        )

    with sessions() as db:
        interval = db.get(ChatSandboxComputeInterval, interval_id)
    assert interval.modal_sandbox_id == "sb-late-provider"
    assert interval.provider_created_at == (started_at + timedelta(seconds=2)).replace(
        tzinfo=None
    )
    assert interval.terminal_at is None
    assert interval.terminal_reason == "termination_uncertain"
    assert interval.reconciliation_state == "termination_uncertain"
    assert interval.reserved_microusd > 0


def test_trip_provider_sweep_preserves_busy_worker_during_grace(monkeypatch):
    sessions = factory()
    configured = settings()
    session_id = uuid.uuid4()
    now = datetime.now(UTC)
    with sessions() as db, db.begin():
        db.add(
            ChatSession(
                id=session_id,
                hf_user_id="grace-owner",
                hf_username="grace-owner",
                selected_model="google/gemma-4-31B-it",
                execution_backend="modal_cli",
            )
        )
        service = ChatSandboxSpendService(db, configured)
        interval_id = service.reserve_interval(
            origin="qualification", worker_generation="grace-worker", now=now
        )
        service.provider_created(interval_id, "sb-busy", now)
        db.add(
            ChatSandboxLease(
                chat_session_id=session_id,
                modal_sandbox_id="sb-busy",
                app_release_id=configured.release_id,
                image_version=configured.chat_modal_image_version,
                worker_contract_version=configured.chat_worker_contract_version,
                worker_generation="grace-worker",
                state="busy",
                last_activity_at=now,
                updated_at=now,
            )
        )
        service.trip("qualification_trip", now)

    async def no_wait(_seconds):
        return None

    async def listed(*_args, **_kwargs):
        yield type("Sandbox", (), {"object_id": "sb-busy"})()

    class ListCall:
        aio = staticmethod(listed)

    monkeypatch.setattr(chat_sandbox_service.modal.Sandbox, "list", ListCall())
    manager = SandboxSessionManager(configured, session_factory=sessions)
    manager._spend_cap_coordinator().sleeper = no_wait

    result = asyncio.run(manager.enforce_spend_cap())

    with sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert result == {"state": "tripped", "terminated": 0, "uncertain": 0}
    assert lease.state == "busy"
    assert lease.modal_sandbox_id == "sb-busy"


def test_claim_preserves_one_continuous_pool_interval():
    sessions = factory()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        interval_id = service.reserve_interval(
            origin="blank_pool", worker_generation="generation", now=start
        )
        service.provider_created(interval_id, "sb-pool", start)
        import uuid

        session_id = uuid.uuid4()
        service.claim("sb-pool", session_id, start + timedelta(seconds=20))
        service.claim("sb-pool", session_id, start + timedelta(seconds=30))
        rows = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
        assert len(rows) == 1
        assert rows[0].reserved_at.replace(tzinfo=UTC) == start
        assert rows[0].claimed_at.replace(tzinfo=UTC) == start + timedelta(seconds=20)


def test_provider_floor_is_monotonic_and_trips_at_cap():
    sessions = factory()
    now = datetime(2026, 8, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        state = service.reconcile_provider_floor(100_000_000, now)
        assert state.provider_floor_microusd == 100_000_000
        assert state.circuit_state == "tripped"
        with pytest.raises(ChatComputeDisabled):
            service.assert_available(now)


def test_reservations_trip_before_aggregate_headroom_is_oversubscribed():
    sessions = factory()
    now = datetime(2026, 8, 1, tzinfo=UTC)
    constrained = settings(
        chat_sandbox_warning_microusd=100_000,
        chat_sandbox_application_cap_microusd=1_500_000,
        chat_sandbox_environment_cap_microusd=2_000_000,
        chat_sandbox_workspace_cap_microusd=3_000_000,
    )
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, constrained)
        service.reserve_interval(origin="direct", worker_generation="first", now=now)
        with pytest.raises(ChatComputeDisabled):
            service.reserve_interval(
                origin="direct", worker_generation="second", now=now
            )
        assert service.refresh(now).circuit_state == "tripped"


def test_spend_trip_rearms_once_after_provider_confirms_new_utc_cycle():
    sessions = factory()
    august = datetime(2026, 8, 31, 23, 59, tzinfo=UTC)
    september = datetime(2026, 9, 1, 0, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        service.reconcile_provider_floor(100_000_000, august)
    with sessions() as db, db.begin():
        with pytest.raises(ChatComputeDisabled):
            ChatSandboxSpendService(db, settings()).reconcile_provider_floor(
                0, september
            )
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, settings()).record_kill_sweep(
            complete=True, now=august
        )
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        state = service.reconcile_provider_floor(0, september)
        assert state.billing_cycle.isoformat() == "2026-09-01"
        assert state.circuit_state == "armed"
        events = list(
            db.execute(
                select(ChatSandboxCircuitEvent).where(
                    ChatSandboxCircuitEvent.budget_state_id == state.id,
                    ChatSandboxCircuitEvent.event_type == "cycle_rearmed",
                )
            ).scalars()
        )
        assert len(events) == 1


def test_kill_sweep_events_are_deduplicated_per_trip_not_per_cycle():
    sessions = factory()
    first = datetime(2026, 8, 1, tzinfo=UTC)
    second = first + timedelta(hours=1)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        service.record_kill_sweep(complete=True, now=first)
        state = service.refresh(second)
        state.circuit_state = "tripped"
        state.tripped_at = second
        service.record_kill_sweep(complete=True, now=second)
        service.record_kill_sweep(complete=True, now=second + timedelta(minutes=1))
    with sessions() as db:
        events = db.execute(
            select(ChatSandboxCircuitEvent)
            .where(ChatSandboxCircuitEvent.event_type == "kill_sweep_complete")
            .order_by(ChatSandboxCircuitEvent.created_at)
        ).scalars()
        assert [event.created_at for event in events] == [
            first.replace(tzinfo=None),
            second.replace(tzinfo=None),
        ]


def test_tagged_provider_orphan_is_conservatively_added_to_ledger():
    sessions = factory()
    now = datetime(2026, 8, 3, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        service.terminate(
            "sb-orphan", "termination_uncertain", confirmed=False, now=now
        )
        row = db.execute(
            select(ChatSandboxComputeInterval).where(
                ChatSandboxComputeInterval.modal_sandbox_id == "sb-orphan"
            )
        ).scalar_one()
        assert row.origin == "reconciled_orphan"
        assert row.terminal_at is None
        assert row.reserved_microusd == service.reservation_amount()
        assert row.reconciliation_state == "termination_uncertain"


def test_provider_floor_replaces_confirmed_orphan_after_closed_billing_hour():
    sessions = factory()
    terminal_at = datetime(2026, 8, 3, 7, 30, tzinfo=UTC)
    reported_at = datetime(2026, 8, 3, 8, 15, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        service.terminate(
            "sb-confirmed-orphan",
            "pool_orphan_reconciled",
            confirmed=True,
            now=terminal_at,
        )
        before = service.refresh(reported_at)
        assert before.estimated_accrued_microusd > 0
        after = service.reconcile_provider_floor(123_456, reported_at)
        assert after.estimated_accrued_microusd == 0
        assert after.provider_floor_microusd == 123_456


def test_provider_floor_keeps_current_hour_orphan_estimate():
    sessions = factory()
    terminal_at = datetime(2026, 8, 3, 8, 5, tzinfo=UTC)
    reported_at = datetime(2026, 8, 3, 8, 15, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        service.terminate(
            "sb-current-hour-orphan",
            "pool_orphan_reconciled",
            confirmed=True,
            now=terminal_at,
        )
        state = service.reconcile_provider_floor(123_456, reported_at)
        assert state.estimated_accrued_microusd > 0


def test_live_interval_crossing_month_is_metered_in_each_utc_cycle():
    sessions = factory()
    start = datetime(2026, 8, 31, 23, 59, tzinfo=UTC)
    september = datetime(2026, 9, 1, 0, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        interval_id = service.reserve_interval(
            origin="direct", worker_generation="cross-month", now=start
        )
        service.provider_created(interval_id, "sb-cross-month", start)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        state = service.refresh(september)
        assert state.billing_cycle.isoformat() == "2026-09-01"
        assert state.estimated_accrued_microusd == 60 * service.cost_per_second()
        row = db.get(ChatSandboxComputeInterval, interval_id)
        assert row.accrued_microusd == 120 * service.cost_per_second()


def test_daily_spend_splits_one_pool_interval_at_claim_time():
    sessions = factory()
    start = datetime(2026, 8, 3, 12, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        interval_id = service.reserve_interval(
            origin="blank_pool", worker_generation="split", now=start
        )
        service.provider_created(interval_id, "sb-split", start)
        service.claim(
            "sb-split", __import__("uuid").uuid4(), start + timedelta(seconds=20)
        )
        service.terminate(
            "sb-split", "complete", confirmed=True, now=start + timedelta(seconds=70)
        )
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        status = service.status(start + timedelta(seconds=90))
        assert status["daily_spend"] == [
            {
                "date": "2026-08-03",
                "blank_pool_microusd": 20 * service.cost_per_second(),
                "assigned_microusd": 50 * service.cost_per_second(),
            }
        ]


def test_uncertain_interval_metering_stops_at_configured_maximum_lifetime():
    sessions = factory()
    start = datetime(2026, 8, 3, tzinfo=UTC)
    short = settings(chat_persistent_sandbox_lifetime_seconds=300)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, short)
        interval_id = service.reserve_interval(
            origin="direct", worker_generation="uncertain", now=start
        )
        service.provider_created(interval_id, "sb-uncertain", start)
        service.terminate(
            "sb-uncertain", "termination_uncertain", confirmed=False, now=start
        )
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, short)
        state = service.refresh(start + timedelta(hours=1))
        assert state.estimated_accrued_microusd == 300 * service.cost_per_second()


def test_provider_reconciliation_claim_is_durable_across_workers():
    sessions = factory()
    now = datetime(2026, 8, 3, tzinfo=UTC)
    with sessions() as db, db.begin():
        assert ChatSandboxSpendService(db, settings()).claim_provider_reconciliation(
            now
        )
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        assert not service.claim_provider_reconciliation(now + timedelta(minutes=59))
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        assert service.claim_provider_reconciliation(now + timedelta(hours=1))


def test_circuit_operator_must_be_root_and_allowlisted(monkeypatch):
    configured = settings(chat_sandbox_operator_usernames="alice")
    monkeypatch.setattr(
        "backend.scripts.manage_chat_sandbox_circuit.os.geteuid", lambda: 0
    )
    monkeypatch.setenv("SUDO_USER", "Alice")
    assert operator_identity(configured) == "alice"
    monkeypatch.setattr(
        "backend.scripts.manage_chat_sandbox_circuit.os.geteuid", lambda: 1000
    )
    with pytest.raises(SystemExit, match="must run as root"):
        operator_identity(configured)


def test_circuit_rearm_accepts_reviewed_provider_cap_basis():
    args = circuit_parser().parse_args(
        [
            "rearm",
            "--environment",
            "production",
            "--cycle",
            "2026-08-01",
            "--reason",
            "provider cap raised",
            "--evidence",
            "Modal environment budget verified",
            "--basis",
            "reviewed-provider-cap",
            "--orphan-sweep-event-id",
            str(uuid.uuid4()),
        ]
    )
    assert args.basis == "reviewed-provider-cap"


def test_reviewed_higher_caps_preserve_provider_caps():
    current = SimpleNamespace(
        warning_microusd=75_000_000,
        application_cap_microusd=100_000_000,
        environment_cap_microusd=250_000_000,
        workspace_cap_microusd=250_000_000,
        policy_attestation="policy-v2",
    )
    raised = settings(
        chat_sandbox_warning_microusd=200_000_000,
        chat_sandbox_application_cap_microusd=225_000_000,
        chat_sandbox_environment_cap_microusd=250_000_000,
        chat_sandbox_workspace_cap_microusd=250_000_000,
        chat_sandbox_budget_attestation="policy-v3",
    )

    assert reviewed_higher_caps_allowed(current, raised)
    assert not reviewed_higher_caps_allowed(
        current,
        raised.model_copy(
            update={"chat_sandbox_environment_cap_microusd": 200_000_000}
        ),
    )


def test_policy_change_without_new_attestation_trips_accounting_integrity():
    sessions = factory()
    now = datetime(2026, 8, 3, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, settings()).refresh(now)
    with sessions() as db, db.begin():
        changed = settings(chat_sandbox_application_cap_microusd=110_000_000)
        state = ChatSandboxSpendService(db, changed).refresh(now + timedelta(seconds=1))
        assert state.circuit_state == "tripped"
        assert state.trip_reason == "accounting_integrity"


def test_lock_wait_does_not_treat_a_newer_committed_meter_as_clock_corruption():
    sessions = factory()
    captured_at = datetime(2026, 8, 3, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, settings()).refresh(
            captured_at + timedelta(seconds=10)
        )
    with sessions() as db, db.begin():
        state = ChatSandboxSpendService(
            db,
            settings(),
            utcnow=lambda: captured_at + timedelta(seconds=11),
        ).refresh(captured_at, capacity_locked=True)

    assert state.circuit_state == "armed"
    assert state.last_metered_at == captured_at + timedelta(seconds=11)


def test_meter_timestamp_ahead_of_the_post_lock_clock_trips_degraded():
    sessions = factory()
    captured_at = datetime(2026, 8, 3, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, settings()).refresh(
            captured_at + timedelta(seconds=10)
        )
    with sessions() as db, db.begin():
        state = ChatSandboxSpendService(
            db,
            settings(),
            utcnow=lambda: captured_at,
        ).refresh(captured_at, capacity_locked=True)

    assert state.circuit_state == "tripped"
    assert state.trip_reason == "metering_degraded"


def test_invalid_lifecycle_timestamp_trips_metering_degraded():
    sessions = factory()
    now = datetime(2026, 8, 3, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        interval_id = service.reserve_interval(
            origin="direct", worker_generation="bad-clock", now=now
        )
        row = db.get(ChatSandboxComputeInterval, interval_id)
        row.provider_created_at = now - timedelta(seconds=1)
    with sessions() as db, db.begin():
        state = ChatSandboxSpendService(db, settings()).refresh(
            now + timedelta(seconds=1)
        )
        assert state.circuit_state == "tripped"
        assert state.trip_reason == "metering_degraded"


def test_abandoned_direct_reservations_release_only_terminal_lease_owners():
    sessions = factory()
    now = datetime(2026, 8, 3, tzinfo=UTC)
    configured = settings()
    abandoned_session_id = uuid.uuid4()
    active_session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        for session_id, owner in (
            (abandoned_session_id, "abandoned-owner"),
            (active_session_id, "active-owner"),
        ):
            db.add(
                ChatSession(
                    id=session_id,
                    hf_user_id=owner,
                    hf_username=owner,
                    selected_model="google/gemma-4-31B-it",
                    execution_backend="modal_cli",
                )
            )
        db.flush()
        db.add_all(
            [
                ChatSandboxLease(
                    chat_session_id=abandoned_session_id,
                    app_release_id=configured.release_id,
                    image_version=configured.chat_modal_image_version,
                    worker_contract_version=configured.chat_worker_contract_version,
                    state="failed",
                    worker_generation="abandoned-generation",
                ),
                ChatSandboxLease(
                    chat_session_id=active_session_id,
                    app_release_id=configured.release_id,
                    image_version=configured.chat_modal_image_version,
                    worker_contract_version=configured.chat_worker_contract_version,
                    state="starting",
                    worker_generation="active-generation",
                ),
            ]
        )
        service = ChatSandboxSpendService(db, configured)
        abandoned_interval_id = service.reserve_interval(
            origin="direct",
            worker_generation="abandoned-generation",
            chat_session_id=abandoned_session_id,
            now=now,
        )
        active_interval_id = service.reserve_interval(
            origin="direct",
            worker_generation="active-generation",
            chat_session_id=active_session_id,
            now=now,
        )

    with sessions() as db, db.begin():
        released = ChatSandboxSpendService(
            db, configured
        ).abort_abandoned_direct_reservations(now + timedelta(minutes=1))

    assert released == 1
    with sessions() as db:
        abandoned = db.get(ChatSandboxComputeInterval, abandoned_interval_id)
        active = db.get(ChatSandboxComputeInterval, active_interval_id)
        assert abandoned.terminal_reason == "lease_owner_terminated"
        assert abandoned.reserved_microusd == 0
        assert active.terminal_at is None
        assert active.reserved_microusd > 0


def test_admin_spend_status_matches_the_typed_api_contract():
    sessions = factory()
    now = datetime(2026, 8, 3, tzinfo=UTC)
    with sessions() as db, db.begin():
        payload = ChatSandboxSpendService(db, settings()).status(now)
        response = ChatSandboxSpendResponse.model_validate(payload)
        assert response.environment == "staging"
        assert response.reconciliation_state == "unavailable"


def test_startup_rejects_interactive_provider_token(monkeypatch):
    configured = settings(
        chat_sandbox_provider_mode="team_environments",
        chat_sandbox_modal_environment="pwc-chat-staging",
    )
    monkeypatch.setenv("MODAL_ENVIRONMENT", "pwc-chat-staging")

    class Token:
        def WhichOneof(self, _name):
            return "user_identity"

    class Stub:
        async def TokenInfoGet(self, _request):
            return Token()

    class Client:
        stub = Stub()

        async def _close(self):
            return None

    async def from_env():
        return Client()

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service._Client.from_env", from_env
    )
    manager = SandboxSessionManager(configured, session_factory=factory())
    with pytest.raises(SandboxError, match="service identity"):
        asyncio.run(manager.validate_image_reference())


def test_startup_accepts_attested_starter_workspace_owner(monkeypatch):
    configured = settings(
        chat_sandbox_provider_mode="starter_workspace",
        chat_sandbox_modal_environment="pwc-chat-staging",
        chat_sandbox_modal_workspace="nielsrogge",
        chat_sandbox_modal_owner_username="nielsrogge",
    )
    monkeypatch.setenv("MODAL_ENVIRONMENT", "pwc-chat-staging")

    class UserIdentity:
        username = "nielsrogge"

    class Token:
        workspace_name = "nielsrogge"
        user_identity = UserIdentity()

        def WhichOneof(self, _name):
            return "user_identity"

    class Stub:
        async def TokenInfoGet(self, _request):
            return Token()

    class Client:
        stub = Stub()

        async def _close(self):
            return None

    async def from_env():
        return Client()

    async def lookup(*_args, **_kwargs):
        return object()

    async def resolve_image(_image_id):
        return object()

    class Lookup:
        aio = lookup

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service._Client.from_env", from_env
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.App.lookup", Lookup()
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.resolve_modal_image", resolve_image
    )
    manager = SandboxSessionManager(configured, session_factory=factory())
    asyncio.run(manager.validate_image_reference())


def test_startup_accepts_service_user_visible_only_in_chat_environment(monkeypatch):
    configured = settings(
        chat_sandbox_provider_mode="team_environments",
        chat_sandbox_modal_environment="pwc-chat-production",
        chat_sandbox_modal_workspace="paperswithcode",
        chat_sandbox_environment_cap_microusd=125_000_000,
    )
    monkeypatch.setenv("MODAL_ENVIRONMENT", "pwc-chat-production")

    class ServiceIdentity:
        service_user_name = "pwc-production"

    class Token:
        workspace_name = "paperswithcode"
        service_user_identity = ServiceIdentity()

        def WhichOneof(self, _name):
            return "service_user_identity"

    class Environment:
        name = "pwc-chat-production"
        environment_id = "en-production"

    class Environments:
        items = [Environment()]

    class Budget:
        cycle_budget_dollars = 125

        def HasField(self, name):
            return name == "cycle_budget_dollars"

    class Stub:
        async def TokenInfoGet(self, _request):
            return Token()

        async def EnvironmentList(self, _request):
            return Environments()

        async def EnvironmentGetBudget(self, _request):
            return Budget()

    class Client:
        stub = Stub()

        async def _close(self):
            return None

    async def from_env():
        return Client()

    async def lookup(*_args, **_kwargs):
        return object()

    async def resolve_image(_image_id):
        return object()

    class Lookup:
        aio = lookup

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service._Client.from_env", from_env
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.App.lookup", Lookup()
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.resolve_modal_image", resolve_image
    )

    manager = SandboxSessionManager(configured, session_factory=factory())
    asyncio.run(manager.validate_image_reference())


def test_billing_cycle_is_utc_and_rejects_naive_time():
    assert (
        billing_cycle(datetime(2026, 8, 31, 23, tzinfo=UTC)).isoformat() == "2026-08-01"
    )
    with pytest.raises(ValueError):
        billing_cycle(datetime(2026, 8, 1))  # noqa: DTZ001 - verifies rejection


def test_legacy_spend_schema_import_reexports_canonical_chat_contract():
    assert ChatSandboxSpendResponse is CanonicalSpendResponse
