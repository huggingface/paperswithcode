from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import ChatSandboxLease, ChatSession
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    ChatSandboxLeaseEvictionCoordinator,
    LeaseEvictionOutcome,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    ChatSandboxLeaseLifecycleCoordinator,
)
from backend.services.chat_sandbox_lease_maintenance_coordinator import (
    ChatSandboxLeaseMaintenanceCoordinator,
)
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_state_repository import (
    LEASE_MAINTENANCE_BATCH_SIZE,
    ChatSandboxStateRepository,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-current",
        "chat_modal_image_version": "im-current",
        "chat_worker_contract_version": "worker-v1",
        "chat_persistent_worker_enabled": True,
        "chat_blank_pool_enabled": False,
        "chat_sandbox_admission_enabled": True,
        "chat_workspace_snapshots_enabled": False,
        "chat_sandbox_spend_enforcement_enabled": False,
        "chat_sandbox_warm_seconds": 60,
        "chat_sandbox_max_warm": 4,
        "chat_workspace_snapshot_inactivity_days": 7,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _TrackedSession(Session):
    pass


class _TransactionProbe:
    def __init__(self) -> None:
        self.active = 0
        self.io_calls: list[str] = []

    def attach(self, sessions) -> None:
        def after_begin(db, transaction, _connection):
            if transaction.parent is None and not db.info.get("probe_active"):
                db.info["probe_active"] = True
                self.active += 1

        def after_transaction_end(db, transaction):
            if transaction.parent is None and db.info.pop("probe_active", False):
                self.active -= 1

        event.listen(sessions.class_, "after_begin", after_begin)
        event.listen(sessions.class_, "after_transaction_end", after_transaction_end)

    def outside_transaction(self, operation: str) -> None:
        assert self.active == 0, f"{operation} ran inside a database transaction"
        self.io_calls.append(operation)


def _database(probe: _TransactionProbe):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ChatSession.__table__.create(engine)
    ChatSandboxLease.__table__.create(engine)
    sessions = sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=_TrackedSession,
    )
    probe.attach(sessions)
    return sessions


class _CapacityLocker:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, db: Session) -> bool:
        self.calls += 1
        db.info["capacity_locked"] = True
        return True


class _Provider:
    def __init__(self, probe: _TransactionProbe) -> None:
        self.probe = probe
        self.poll_results: dict[str, object | None] = {}
        self.resolve_errors: dict[str, BaseException] = {}
        self.poll_errors: dict[str, BaseException] = {}
        self.resolved: list[str] = []
        self.polled: list[str] = []
        self.terminated: list[str] = []
        self.termination_started: asyncio.Event | None = None
        self.allow_termination: asyncio.Event | None = None
        self.poll_started: asyncio.Event | None = None
        self.allow_poll: asyncio.Event | None = None

    async def resolve(self, sandbox_id: str):
        self.probe.outside_transaction("provider.resolve")
        self.resolved.append(sandbox_id)
        error = self.resolve_errors.get(sandbox_id)
        if error is not None:
            raise error
        return SimpleNamespace(object_id=sandbox_id)

    async def poll(self, sandbox) -> object | None:
        self.probe.outside_transaction("provider.poll")
        sandbox_id = sandbox.object_id
        self.polled.append(sandbox_id)
        if self.poll_started is not None:
            self.poll_started.set()
        if self.allow_poll is not None:
            await self.allow_poll.wait()
        error = self.poll_errors.get(sandbox_id)
        if error is not None:
            raise error
        return self.poll_results.get(sandbox_id)

    async def terminate(self, sandbox_id: str, _sandbox=None) -> bool:
        self.probe.outside_transaction("provider.terminate")
        self.terminated.append(sandbox_id)
        if self.termination_started is not None:
            self.termination_started.set()
        if self.allow_termination is not None:
            await self.allow_termination.wait()
        return True


class _Snapshots:
    supported = True

    def __init__(self, probe: _TransactionProbe) -> None:
        self.probe = probe
        self.deleted: list[str] = []
        self.delete_error: BaseException | None = None
        self.delete_started: asyncio.Event | None = None
        self.allow_delete: asyncio.Event | None = None

    async def save(self, _sandbox, _chat_session_id: uuid.UUID) -> str:
        self.probe.outside_transaction("snapshot.save")
        return "snapshot-new"

    async def delete(self, snapshot_id: str) -> None:
        self.probe.outside_transaction("snapshot.delete")
        self.deleted.append(snapshot_id)
        if self.delete_started is not None:
            self.delete_started.set()
        if self.allow_delete is not None:
            await self.allow_delete.wait()
        if self.delete_error is not None:
            raise self.delete_error


_DEFAULT_SANDBOX = object()


class _Harness:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        repository: ChatSandboxStateRepository | None = None,
    ) -> None:
        self.settings = settings or _settings()
        self.now = datetime(2026, 8, 10, 12, tzinfo=UTC)
        self.probe = _TransactionProbe()
        self.sessions = _database(self.probe)
        self.repository = repository or ChatSandboxStateRepository(self.settings)
        self.provider = _Provider(self.probe)
        self.transport = ChatSandboxWorkerTransport(self.provider)
        self.snapshots = _Snapshots(self.probe)
        self.capacity_locker = _CapacityLocker()
        self.idle_eviction = ChatSandboxLeaseEvictionCoordinator(
            self.settings,
            session_factory=self.sessions,
            repository=self.repository,
            provider=self.provider,
            transport=self.transport,
            snapshots=self.snapshots,
            capacity_locker=self.capacity_locker,
            utcnow=lambda: self.now,
            token_factory=lambda: "idle-termination-token",
        )
        self.lifecycle = ChatSandboxLeaseLifecycleCoordinator(
            self.settings,
            session_factory=self.sessions,
            repository=self.repository,
            provider=self.provider,
            transport=self.transport,
            snapshots=self.snapshots,
            idle_eviction=self.idle_eviction,
            capacity_locker=self.capacity_locker,
            utcnow=lambda: self.now,
            token_factory=lambda: "termination-token",
        )
        self.coordinator = ChatSandboxLeaseMaintenanceCoordinator(
            self.settings,
            session_factory=self.sessions,
            repository=self.repository,
            provider=self.provider,
            lifecycle=self.lifecycle,
            snapshots=self.snapshots,
            capacity_locker=self.capacity_locker,
            utcnow=lambda: self.now,
            token_factory=lambda: "maintenance-termination-token",
        )

    def add_lease(
        self,
        *,
        state: str = "idle",
        sandbox_id: str | None | object = _DEFAULT_SANDBOX,
        token_hash: str | None = None,
        worker_generation: str = "generation-current",
        lease_expires_at: datetime | None = None,
        last_activity_at: datetime | None = None,
        active_turn_expires_at: datetime | None = None,
        session_updated_at: datetime | None = None,
        snapshot_id: str | None = None,
    ) -> uuid.UUID:
        session_id = uuid.uuid4()
        if sandbox_id is _DEFAULT_SANDBOX:
            sandbox_id = f"sb-{session_id}"
        activity = last_activity_at or self.now
        updated = session_updated_at or self.now
        with self.sessions() as db, db.begin():
            db.add_all(
                [
                    ChatSession(
                        id=session_id,
                        hf_user_id=f"owner-{session_id}",
                        hf_username=f"owner-{session_id}",
                        selected_model="google/gemma-4-31B-it",
                        execution_backend="modal_cli",
                        active_turn_expires_at=active_turn_expires_at,
                        created_at=updated,
                        updated_at=updated,
                    ),
                    ChatSandboxLease(
                        chat_session_id=session_id,
                        modal_sandbox_id=sandbox_id,
                        app_release_id=self.settings.release_id,
                        image_version=self.settings.chat_modal_image_version,
                        worker_contract_version=(
                            self.settings.chat_worker_contract_version
                        ),
                        worker_generation=worker_generation,
                        state=state,
                        lease_token_hash=token_hash,
                        lease_expires_at=lease_expires_at,
                        last_activity_at=activity,
                        workspace_snapshot_id=snapshot_id,
                        snapshot_image_version="im-current" if snapshot_id else None,
                        snapshot_updated_at=updated if snapshot_id else None,
                        workspace_dirty=False,
                        created_at=updated,
                        updated_at=updated,
                    ),
                ]
            )
        return session_id

    def lease(self, session_id: uuid.UUID) -> ChatSandboxLease:
        with self.sessions() as db:
            return db.get(ChatSandboxLease, session_id)


def test_repository_projects_strict_idle_order_and_legacy_warm_count():
    harness = _Harness()
    cutoff = harness.now - timedelta(seconds=60)
    oldest = harness.add_lease(last_activity_at=cutoff - timedelta(seconds=30))
    middle = harness.add_lease(last_activity_at=cutoff - timedelta(seconds=10))
    harness.add_lease(last_activity_at=cutoff)
    harness.add_lease(last_activity_at=cutoff + timedelta(seconds=1))
    harness.add_lease(state="starting", token_hash="start")
    harness.add_lease(state="ready")
    harness.add_lease(state="terminating")
    harness.add_lease(state="busy")
    harness.add_lease(state="failed")

    with harness.sessions() as db:
        idle = harness.repository.list_idle_before(db, cutoff=cutoff)
        plan = harness.repository.plan_warm_cap(db, max_warm=5)

    assert [candidate.chat_session_id for candidate in idle] == [oldest, middle]
    assert plan.warm_count == 7
    assert [candidate.chat_session_id for candidate in plan.candidates] == [
        oldest,
        middle,
    ]


def test_repository_stale_cutoff_is_inclusive_for_busy_and_terminating():
    harness = _Harness()
    busy_exact = harness.add_lease(
        state="busy",
        token_hash="busy-exact",
        active_turn_expires_at=harness.now,
    )
    harness.add_lease(
        state="busy",
        token_hash="busy-future",
        active_turn_expires_at=harness.now + timedelta(microseconds=1),
    )
    terminating_exact = harness.add_lease(
        state="terminating",
        token_hash="terminating-exact",
        lease_expires_at=harness.now,
    )
    harness.add_lease(
        state="terminating",
        token_hash="terminating-future",
        lease_expires_at=harness.now + timedelta(microseconds=1),
    )

    with harness.sessions() as db:
        candidates = harness.repository.list_stale_operations(db, cutoff=harness.now)

    assert {candidate.chat_session_id for candidate in candidates} == {
        busy_exact,
        terminating_exact,
    }


def test_repository_inactive_snapshot_cutoff_is_strict():
    harness = _Harness()
    cutoff = harness.now - timedelta(days=7)
    inactive = harness.add_lease(
        state="terminated",
        sandbox_id=None,
        snapshot_id="snapshot-inactive",
        session_updated_at=cutoff - timedelta(microseconds=1),
    )
    harness.add_lease(
        state="terminated",
        sandbox_id=None,
        snapshot_id="snapshot-exact",
        session_updated_at=cutoff,
    )

    with harness.sessions() as db:
        candidates = harness.repository.list_inactive_snapshots(db, cutoff=cutoff)

    assert [candidate.chat_session_id for candidate in candidates] == [inactive]


@pytest.mark.parametrize(
    "replacement", ["state", "sandbox", "activity", "generation", "token"]
)
def test_idle_candidate_fence_refuses_changed_lease(replacement):
    harness = _Harness()
    cutoff = harness.now - timedelta(seconds=60)
    session_id = harness.add_lease(last_activity_at=cutoff - timedelta(seconds=1))
    with harness.sessions() as db:
        candidate = harness.repository.list_idle_before(db, cutoff=cutoff)[0]
    with harness.sessions() as db, db.begin():
        lease = db.get(ChatSandboxLease, session_id)
        if replacement == "state":
            lease.state = "busy"
        elif replacement == "sandbox":
            lease.modal_sandbox_id = "sb-successor"
        elif replacement == "activity":
            lease.last_activity_at = cutoff + timedelta(seconds=1)
        elif replacement == "generation":
            lease.worker_generation = "generation-successor"
        else:
            lease.lease_token_hash = "successor-token"

    result = asyncio.run(
        harness.lifecycle.terminate_idle_candidates((candidate,), cutoff=cutoff)
    )

    assert result == 0
    assert harness.provider.terminated == []


def test_reap_idle_rechecks_strict_cutoff_and_terminates_only_selected_lease():
    harness = _Harness()
    cutoff = harness.now - timedelta(seconds=60)
    expired = harness.add_lease(last_activity_at=cutoff - timedelta(seconds=1))
    current = harness.add_lease(last_activity_at=cutoff)

    assert asyncio.run(harness.coordinator.reap_idle()) == 1
    assert harness.lease(expired).state == "terminated"
    assert harness.lease(current).state == "idle"
    assert len(harness.provider.terminated) == 1


def test_terminate_idle_candidates_is_bounded_and_counts_changed_ownership():
    async def scenario():
        harness = _Harness()
        harness.lifecycle.termination_concurrency = 2
        cutoff = harness.now - timedelta(seconds=60)
        for index in range(5):
            harness.add_lease(last_activity_at=cutoff - timedelta(seconds=index + 1))
        with harness.sessions() as db:
            candidates = list(harness.repository.list_idle_before(db, cutoff=cutoff))

        active = 0
        maximum_active = 0

        async def evict_candidate(candidate, *, cutoff=None):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0)
            active -= 1
            index = candidates.index(candidate)
            if index == 0:
                return LeaseEvictionOutcome.NOT_IDLE
            if index == 1:
                return LeaseEvictionOutcome.OWNERSHIP_CHANGED
            return LeaseEvictionOutcome.EVICTED

        harness.idle_eviction.evict_candidate = evict_candidate
        count = await harness.lifecycle.terminate_idle_candidates(candidates)
        assert count == 4
        assert maximum_active == 2

    asyncio.run(scenario())


def test_reconcile_preserves_cutoffs_counts_and_provider_failure_contracts():
    harness = _Harness()
    expired_start = harness.add_lease(
        state="starting",
        sandbox_id=None,
        token_hash="start-token",
        lease_expires_at=harness.now - timedelta(microseconds=1),
    )
    exact_start = harness.add_lease(
        state="starting",
        sandbox_id=None,
        token_hash="exact-token",
        lease_expires_at=harness.now,
    )
    missing_id = harness.add_lease(state="ready", sandbox_id=None)
    running = harness.add_lease(state="ready", sandbox_id="sb-running")
    exited = harness.add_lease(state="idle", sandbox_id="sb-exited")
    errored = harness.add_lease(state="ready", sandbox_id="sb-error")
    resolve_errored = harness.add_lease(state="ready", sandbox_id="sb-resolve-error")
    harness.provider.poll_results["sb-exited"] = object()
    harness.provider.poll_errors["sb-error"] = RuntimeError("provider unavailable")
    harness.provider.resolve_errors["sb-resolve-error"] = RuntimeError(
        "provider unavailable"
    )

    assert asyncio.run(harness.coordinator.reconcile()) == 5

    assert harness.lease(expired_start).failure_code == "sandbox_start_failed"
    assert harness.lease(exact_start).state == "starting"
    assert harness.lease(missing_id).failure_code == "sandbox_lost"
    assert harness.lease(running).state == "ready"
    assert harness.lease(exited).failure_code == "sandbox_lost"
    assert harness.lease(errored).failure_code == "sandbox_lost"
    assert harness.lease(resolve_errored).failure_code == "sandbox_lost"
    assert set(harness.provider.polled) == {
        "sb-running",
        "sb-exited",
        "sb-error",
    }


def test_reconcile_propagates_poll_cancellation_without_marking_lost():
    harness = _Harness()
    session_id = harness.add_lease(state="ready", sandbox_id="sb-cancelled")
    harness.provider.poll_errors["sb-cancelled"] = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(harness.coordinator.reconcile())

    assert harness.lease(session_id).state == "ready"


def test_expired_start_candidate_refuses_a_renewed_token_and_generation():
    harness = _Harness()
    session_id = harness.add_lease(
        state="starting",
        sandbox_id=None,
        token_hash="start-token",
        lease_expires_at=harness.now - timedelta(seconds=1),
    )
    with harness.sessions() as db:
        candidate = harness.repository.list_reconciliation_candidates(
            db, cutoff=harness.now
        )[0]
    with harness.sessions() as db, db.begin():
        lease = db.get(ChatSandboxLease, session_id)
        lease.lease_token_hash = "renewed-token"
        lease.worker_generation = "generation-successor"
        lease.lease_expires_at = harness.now + timedelta(minutes=1)
    with harness.sessions() as db, db.begin():
        changed = harness.repository.fail_expired_start_candidate(
            db,
            candidate,
            utcnow=lambda: harness.now,
        )

    assert not changed
    assert harness.lease(session_id).state == "starting"


def test_stale_busy_claim_rechecks_a_renewed_active_turn():
    harness = _Harness()
    session_id = harness.add_lease(
        state="busy",
        token_hash="worker-token",
        active_turn_expires_at=harness.now - timedelta(seconds=1),
    )
    with harness.sessions() as db:
        candidate = harness.repository.list_stale_operations(db, cutoff=harness.now)[0]
    with harness.sessions() as db, db.begin():
        session = db.get(ChatSession, session_id)
        session.active_turn_expires_at = harness.now + timedelta(minutes=1)
    with harness.sessions() as db, db.begin():
        claim = harness.repository.claim_stale_candidate(
            db,
            candidate,
            termination_token="stale-token",
            ready_timeout_seconds=10,
            utcnow=lambda: harness.now,
        )

    assert claim is None
    assert harness.lease(session_id).state == "busy"
    assert harness.provider.terminated == []


def test_stale_termination_does_not_finalize_over_a_successor_generation():
    async def scenario():
        harness = _Harness()
        session_id = harness.add_lease(
            state="busy",
            sandbox_id="sb-stale",
            token_hash="worker-token",
            active_turn_expires_at=harness.now - timedelta(seconds=1),
        )
        harness.provider.termination_started = asyncio.Event()
        harness.provider.allow_termination = asyncio.Event()
        operation = asyncio.create_task(harness.coordinator.reconcile())
        await asyncio.wait_for(
            harness.provider.termination_started.wait(),
            timeout=1,
        )
        with harness.sessions() as db, db.begin():
            lease = db.get(ChatSandboxLease, session_id)
            lease.state = "idle"
            lease.modal_sandbox_id = "sb-successor"
            lease.worker_generation = "generation-successor"
            lease.lease_token_hash = None
            lease.last_activity_at = harness.now
        harness.provider.allow_termination.set()

        assert await asyncio.wait_for(operation, timeout=1) == 1
        successor = harness.lease(session_id)
        assert successor.state == "idle"
        assert successor.modal_sandbox_id == "sb-successor"
        assert successor.worker_generation == "generation-successor"
        assert harness.provider.terminated == ["sb-stale"]

    asyncio.run(scenario())


def test_lost_poll_does_not_mark_a_successor_generation_lost():
    async def scenario():
        harness = _Harness()
        session_id = harness.add_lease(state="ready", sandbox_id="sb-old")
        harness.provider.poll_results["sb-old"] = object()
        harness.provider.poll_started = asyncio.Event()
        harness.provider.allow_poll = asyncio.Event()
        operation = asyncio.create_task(harness.coordinator.reconcile())
        await asyncio.wait_for(harness.provider.poll_started.wait(), timeout=1)
        with harness.sessions() as db, db.begin():
            lease = db.get(ChatSandboxLease, session_id)
            lease.modal_sandbox_id = "sb-successor"
            lease.worker_generation = "generation-successor"
        harness.provider.allow_poll.set()

        assert await asyncio.wait_for(operation, timeout=1) == 0
        successor = harness.lease(session_id)
        assert successor.state == "ready"
        assert successor.modal_sandbox_id == "sb-successor"
        assert successor.worker_generation == "generation-successor"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("blank_pool_enabled", "spend_policy_enabled"),
    [(True, False), (False, True)],
)
def test_live_count_decreases_lock_capacity_before_the_lease_row(
    blank_pool_enabled,
    spend_policy_enabled,
):
    settings = _settings(
        chat_blank_pool_enabled=blank_pool_enabled,
        chat_sandbox_spend_enforcement_enabled=spend_policy_enabled,
    )

    class OrderingRepository(ChatSandboxStateRepository):
        def fail_expired_start_candidate(self, db, candidate, *, utcnow):
            assert db.info.get("capacity_locked")
            return super().fail_expired_start_candidate(db, candidate, utcnow=utcnow)

        def mark_lost_candidate(self, db, candidate, *, utcnow):
            assert db.info.get("capacity_locked")
            return super().mark_lost_candidate(db, candidate, utcnow=utcnow)

    harness = _Harness(settings, repository=OrderingRepository(settings))
    harness.add_lease(
        state="starting",
        sandbox_id=None,
        token_hash="start-token",
        lease_expires_at=harness.now - timedelta(seconds=1),
    )
    harness.add_lease(state="idle", sandbox_id=None)

    assert asyncio.run(harness.coordinator.reconcile()) == 2
    assert harness.capacity_locker.calls == 2


def test_snapshot_replacement_during_delete_is_preserved():
    async def scenario():
        harness = _Harness()
        session_id = harness.add_lease(
            state="terminated",
            sandbox_id=None,
            snapshot_id="snapshot-old",
            session_updated_at=harness.now - timedelta(days=8),
        )
        harness.snapshots.delete_started = asyncio.Event()
        harness.snapshots.allow_delete = asyncio.Event()
        operation = asyncio.create_task(harness.coordinator.expire_inactive_snapshots())
        await asyncio.wait_for(harness.snapshots.delete_started.wait(), timeout=1)
        with harness.sessions() as db, db.begin():
            lease = db.get(ChatSandboxLease, session_id)
            lease.workspace_snapshot_id = "snapshot-successor"
            lease.snapshot_image_version = "im-successor"
        harness.snapshots.allow_delete.set()

        assert await asyncio.wait_for(operation, timeout=1) == 0
        lease = harness.lease(session_id)
        assert lease.workspace_snapshot_id == "snapshot-successor"
        assert lease.snapshot_image_version == "im-successor"
        assert harness.snapshots.deleted == ["snapshot-old"]

    asyncio.run(scenario())


def test_snapshot_delete_failure_and_cancellation_leave_the_claimed_id():
    harness = _Harness()
    failed = harness.add_lease(
        state="terminated",
        sandbox_id=None,
        snapshot_id="snapshot-failed",
        session_updated_at=harness.now - timedelta(days=8),
    )
    harness.snapshots.delete_error = RuntimeError("snapshot unavailable")
    with pytest.raises(RuntimeError, match="snapshot unavailable"):
        asyncio.run(harness.coordinator.expire_inactive_snapshots())
    assert harness.lease(failed).workspace_snapshot_id == "snapshot-failed"

    async def cancellation_scenario():
        second = _Harness()
        session_id = second.add_lease(
            state="terminated",
            sandbox_id=None,
            snapshot_id="snapshot-cancelled",
            session_updated_at=second.now - timedelta(days=8),
        )
        second.snapshots.delete_started = asyncio.Event()
        second.snapshots.allow_delete = asyncio.Event()
        operation = asyncio.create_task(second.coordinator.expire_inactive_snapshots())
        await asyncio.wait_for(second.snapshots.delete_started.wait(), timeout=1)
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation
        assert second.lease(session_id).workspace_snapshot_id == ("snapshot-cancelled")

    asyncio.run(cancellation_scenario())


def test_inactive_snapshot_batch_is_deterministic_and_empty_ids_do_not_starve():
    harness = _Harness()
    inactive_at = harness.now - timedelta(days=8)
    for _ in range(LEASE_MAINTENANCE_BATCH_SIZE):
        harness.add_lease(
            state="terminated",
            sandbox_id=None,
            snapshot_id="",
            session_updated_at=inactive_at,
        )
    expected = {f"snapshot-{index}" for index in range(101)}
    for snapshot_id in expected:
        harness.add_lease(
            state="terminated",
            sandbox_id=None,
            snapshot_id=snapshot_id,
            session_updated_at=inactive_at,
        )

    first = asyncio.run(harness.coordinator.expire_inactive_snapshots())
    second = asyncio.run(harness.coordinator.expire_inactive_snapshots())

    assert (first, second) == (100, 1)
    assert set(harness.snapshots.deleted) == expected
    assert len(harness.snapshots.deleted) == 101


def test_maintenance_rejects_a_dependency_chain_with_a_different_capacity_lock():
    harness = _Harness()

    with pytest.raises(ValueError, match="capacity locks must be shared"):
        ChatSandboxLeaseMaintenanceCoordinator(
            harness.settings,
            session_factory=harness.sessions,
            repository=harness.repository,
            provider=harness.provider,
            lifecycle=harness.lifecycle,
            snapshots=harness.snapshots,
            capacity_locker=_CapacityLocker(),
        )


def test_manager_reuses_an_injected_lifecycle_capacity_lock():
    harness = _Harness()
    manager = SandboxSessionManager(
        harness.settings,
        session_factory=harness.sessions,
        snapshot_provider=harness.snapshots,
        sandbox_provider=harness.provider,
        state_repository=harness.repository,
        lease_eviction_coordinator=harness.idle_eviction,
        lease_lifecycle_coordinator=harness.lifecycle,
    )

    maintenance = manager._lease_maintenance_coordinator()

    assert maintenance.lifecycle is harness.lifecycle
    assert maintenance.capacity_locker is harness.capacity_locker


def test_manager_maintenance_methods_are_thin_count_preserving_delegates():
    class Maintenance:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def reap_idle(self):
            self.calls.append("reap")
            return 1

        async def enforce_warm_cap(self):
            self.calls.append("warm")
            return 2

        async def reconcile(self):
            self.calls.append("reconcile")
            return 3

        async def expire_inactive_snapshots(self):
            self.calls.append("snapshots")
            return 4

    maintenance = Maintenance()
    manager = SandboxSessionManager(
        _settings(),
        lease_maintenance_coordinator=maintenance,
    )

    async def run():
        return (
            await manager.reap_idle(),
            await manager.enforce_warm_cap(),
            await manager.reconcile(),
            await manager.expire_inactive_snapshots(),
        )

    assert asyncio.run(run()) == (1, 2, 3, 4)
    assert maintenance.calls == ["reap", "warm", "reconcile", "snapshots"]


def test_periodic_reconcile_runs_restart_safe_qualification_retention_without_issuance():
    harness = _Harness()
    cleanup_results = iter((2, 0))
    cleanup_calls = []

    def cleanup():
        result = next(cleanup_results)
        cleanup_calls.append(result)
        return result

    coordinator = ChatSandboxLeaseMaintenanceCoordinator(
        harness.settings,
        session_factory=harness.sessions,
        repository=harness.repository,
        provider=harness.provider,
        lifecycle=harness.lifecycle,
        snapshots=harness.snapshots,
        capacity_locker=harness.capacity_locker,
        qualification_cleanup=cleanup,
    )

    assert asyncio.run(coordinator.reconcile()) == 0
    assert asyncio.run(coordinator.reconcile()) == 0
    assert cleanup_calls == [2, 0]


def test_periodic_reconcile_skips_staging_only_qualification_retention_in_production():
    harness = _Harness(_settings(environment="production"))
    cleanup_calls = []
    coordinator = ChatSandboxLeaseMaintenanceCoordinator(
        harness.settings,
        session_factory=harness.sessions,
        repository=harness.repository,
        provider=harness.provider,
        lifecycle=harness.lifecycle,
        snapshots=harness.snapshots,
        capacity_locker=harness.capacity_locker,
        qualification_cleanup=lambda: cleanup_calls.append("cleanup") or 0,
    )

    assert asyncio.run(coordinator.reconcile()) == 0
    assert cleanup_calls == []


def test_qualification_retention_runs_after_reconcile_failure_without_masking_primary():
    harness = _Harness()
    primary = RuntimeError("sandbox reconcile failed")
    cleanup_calls = []
    harness.repository.list_stale_operations = lambda *_args, **_kwargs: (
        _ for _ in ()
    ).throw(primary)
    coordinator = ChatSandboxLeaseMaintenanceCoordinator(
        harness.settings,
        session_factory=harness.sessions,
        repository=harness.repository,
        provider=harness.provider,
        lifecycle=harness.lifecycle,
        snapshots=harness.snapshots,
        capacity_locker=harness.capacity_locker,
        qualification_cleanup=lambda: cleanup_calls.append("cleanup") or 0,
    )

    with pytest.raises(RuntimeError) as caught:
        asyncio.run(coordinator.reconcile())
    assert caught.value is primary
    assert cleanup_calls == ["cleanup"]


def test_expected_qualification_retention_failure_does_not_change_reconcile_result():
    harness = _Harness()
    coordinator = ChatSandboxLeaseMaintenanceCoordinator(
        harness.settings,
        session_factory=harness.sessions,
        repository=harness.repository,
        provider=harness.provider,
        lifecycle=harness.lifecycle,
        snapshots=harness.snapshots,
        capacity_locker=harness.capacity_locker,
        qualification_cleanup=lambda: (_ for _ in ()).throw(OSError("db unavailable")),
    )

    assert asyncio.run(coordinator.reconcile()) == 0


def test_unexpected_retention_error_is_visible_only_without_primary_reconcile_error():
    harness = _Harness()
    programming_error = ValueError("programming defect")
    coordinator = ChatSandboxLeaseMaintenanceCoordinator(
        harness.settings,
        session_factory=harness.sessions,
        repository=harness.repository,
        provider=harness.provider,
        lifecycle=harness.lifecycle,
        snapshots=harness.snapshots,
        capacity_locker=harness.capacity_locker,
        qualification_cleanup=lambda: (_ for _ in ()).throw(programming_error),
    )
    with pytest.raises(ValueError) as caught:
        asyncio.run(coordinator.reconcile())
    assert caught.value is programming_error

    primary = RuntimeError("sandbox reconcile failed")
    harness.repository.list_stale_operations = lambda *_args, **_kwargs: (
        _ for _ in ()
    ).throw(primary)
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(coordinator.reconcile())
    assert caught.value is primary
