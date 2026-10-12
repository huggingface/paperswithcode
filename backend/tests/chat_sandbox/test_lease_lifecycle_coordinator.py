from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import (
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSession,
)
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    ChatSandboxLeaseEvictionCoordinator,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    MAX_LEASE_TERMINATION_CONCURRENCY,
    ChatSandboxLeaseLifecycleCoordinator,
    LeaseTerminationOutcome,
    SandboxCleanupUnverified,
)
from backend.services.chat_sandbox_service import (
    SandboxCleanupUnverified as LegacySandboxCleanupUnverified,
)
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    WorkerClaim,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    SessionControl,
)


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-current",
        "chat_modal_image_version": "im-current",
        "chat_worker_contract_version": "worker-v1",
        "chat_persistent_worker_enabled": True,
        "chat_blank_pool_enabled": True,
        "chat_sandbox_admission_enabled": True,
        "chat_workspace_snapshots_enabled": False,
        "chat_sandbox_spend_enforcement_enabled": False,
        "chat_sandbox_budget_attestation": "attested",
        "chat_sandbox_cpu": 0.125,
        "chat_sandbox_cpu_limit": 1,
        "chat_sandbox_memory_mib": 512,
        "chat_sandbox_memory_limit_mib": 2048,
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
    for table in (
        ChatSession.__table__,
        ChatSandboxLease.__table__,
        ChatSandboxComputeInterval.__table__,
    ):
        table.create(engine)
    sessions = sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=_TrackedSession,
    )
    probe.attach(sessions)
    return sessions


class _Provider:
    def __init__(self, probe: _TransactionProbe) -> None:
        self.probe = probe
        self.confirmed = True
        self.termination_calls: list[str] = []
        self.termination_started: asyncio.Event | None = None
        self.allow_termination: asyncio.Event | None = None
        self.termination_error: Exception | None = None

    async def terminate(self, sandbox_id: str, _sandbox=None) -> bool:
        self.probe.outside_transaction("provider.terminate")
        self.termination_calls.append(sandbox_id)
        if self.termination_started is not None:
            self.termination_started.set()
        if self.allow_termination is not None:
            await self.allow_termination.wait()
        if self.termination_error is not None:
            raise self.termination_error
        return self.confirmed

    async def resolve(self, sandbox_id: str):
        self.probe.outside_transaction("provider.resolve")
        return SimpleNamespace(object_id=sandbox_id)


class _Snapshots:
    supported = True

    def __init__(self, probe: _TransactionProbe) -> None:
        self.probe = probe
        self.deleted: list[str] = []
        self.delete_error: Exception | None = None
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


class _Harness:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        termination_concurrency: int = MAX_LEASE_TERMINATION_CONCURRENCY,
    ) -> None:
        self.settings = settings or _settings()
        self.now = datetime(2026, 8, 10, 12, tzinfo=UTC)
        self.probe = _TransactionProbe()
        self.sessions = _database(self.probe)
        self.repository = ChatSandboxStateRepository(self.settings)
        self.provider = _Provider(self.probe)
        self.transport = ChatSandboxWorkerTransport(self.provider)
        self.snapshots = _Snapshots(self.probe)
        self.idle_eviction = ChatSandboxLeaseEvictionCoordinator(
            self.settings,
            session_factory=self.sessions,
            repository=self.repository,
            provider=self.provider,
            transport=self.transport,
            snapshots=self.snapshots,
            capacity_locker=lambda _db: True,
            utcnow=lambda: self.now,
            token_factory=lambda: "idle-termination-token",
        )
        self.coordinator = ChatSandboxLeaseLifecycleCoordinator(
            self.settings,
            session_factory=self.sessions,
            repository=self.repository,
            provider=self.provider,
            transport=self.transport,
            snapshots=self.snapshots,
            idle_eviction=self.idle_eviction,
            capacity_locker=lambda _db: True,
            utcnow=lambda: self.now,
            token_factory=lambda: "termination-token",
            termination_concurrency=termination_concurrency,
        )

    def add_lease(
        self,
        *,
        state: str = "ready",
        sandbox_id: str | None = "sb-current",
        worker_generation: str = "generation-current",
        token_hash: str | None = None,
    ) -> uuid.UUID:
        session_id = uuid.uuid4()
        with self.sessions() as db, db.begin():
            db.add_all(
                [
                    ChatSession(
                        id=session_id,
                        hf_user_id=f"owner-{session_id}",
                        hf_username=f"owner-{session_id}",
                        selected_model="google/gemma-4-31B-it",
                        execution_backend="modal_cli",
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
                        last_activity_at=self.now,
                        workspace_dirty=False,
                        created_at=self.now,
                        updated_at=self.now,
                    ),
                ]
            )
        return session_id

    def add_interval(
        self,
        session_id: uuid.UUID,
        sandbox_id: str = "sb-current",
    ) -> None:
        with self.sessions() as db, db.begin():
            db.add(
                ChatSandboxComputeInterval(
                    id=uuid.uuid4(),
                    modal_sandbox_id=sandbox_id,
                    environment=self.settings.environment,
                    modal_app="pwc-chat-sandbox",
                    app_release_id=self.settings.release_id,
                    image_version=self.settings.chat_modal_image_version,
                    worker_generation="generation-current",
                    origin="direct",
                    chat_session_id=session_id,
                    cpu_request_millicores=125,
                    cpu_limit_millicores=1000,
                    memory_request_mib=512,
                    memory_limit_mib=2048,
                    reserved_at=self.now,
                    provider_created_at=self.now,
                    claimed_at=self.now,
                    billing_cycle=self.now.date().replace(day=1),
                    reserved_microusd=100,
                    updated_at=self.now,
                )
            )

    def register_control(
        self, session_id: uuid.UUID, sandbox_id: str
    ) -> SessionControl:
        control = SessionControl(
            process=object(),
            sandbox=SimpleNamespace(object_id=sandbox_id),
            sandbox_id=sandbox_id,
            stderr_task=None,
            reader_task=None,
            queues={},
            resume_id=None,
        )
        self.transport.register_session_control(session_id, control)
        return control


def _interval(harness: _Harness, sandbox_id: str = "sb-current"):
    with harness.sessions() as db:
        return db.execute(
            select(ChatSandboxComputeInterval).where(
                ChatSandboxComputeInterval.modal_sandbox_id == sandbox_id
            )
        ).scalar_one()


def test_missing_lease_has_a_typed_not_claimed_outcome():
    harness = _Harness()

    outcome = asyncio.run(harness.coordinator.terminate(uuid.uuid4()))

    assert outcome is LeaseTerminationOutcome.NOT_CLAIMED
    assert outcome.acquired is False
    assert harness.probe.io_calls == []


@pytest.mark.parametrize(
    ("failure_code", "expected_state"),
    [(None, "terminated"), ("session_deleted_elsewhere", "failed")],
)
def test_assigned_termination_preserves_failure_and_spend_contracts(
    failure_code,
    expected_state,
):
    harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
    session_id = harness.add_lease()
    harness.add_interval(session_id)
    harness.register_control(session_id, "sb-current")

    outcome = asyncio.run(
        harness.coordinator.terminate(session_id, failure_code=failure_code)
    )

    assert outcome is LeaseTerminationOutcome.FINISHED
    assert harness.probe.io_calls == ["provider.terminate"]
    assert harness.transport.session_control(session_id) is None
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    interval = _interval(harness)
    assert lease.state == expected_state
    assert lease.modal_sandbox_id is None
    assert lease.failure_code == failure_code
    assert lease.lease_token_hash is None
    assert interval.terminal_reason == failure_code
    assert interval.reconciliation_state == "confirmed"
    assert interval.reserved_microusd == 0


def test_unconfirmed_provider_termination_marks_only_the_lease_uncertain():
    harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
    harness.provider.confirmed = False
    session_id = harness.add_lease()
    harness.add_interval(session_id)

    outcome = asyncio.run(
        harness.coordinator.terminate(session_id, failure_code="requested_failure")
    )

    assert outcome is LeaseTerminationOutcome.FINISHED
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    interval = _interval(harness)
    assert lease.state == "failed"
    assert lease.modal_sandbox_id is None
    assert lease.failure_code == "termination_uncertain"
    assert interval.terminal_reason == "requested_failure"
    assert interval.terminal_at is None
    assert interval.reserved_microusd == 100
    assert interval.reconciliation_state == "termination_uncertain"


def test_assigned_termination_preserves_a_mismatched_successor_control():
    harness = _Harness()
    session_id = harness.add_lease()
    successor_control = harness.register_control(session_id, "sb-successor")

    assert (
        asyncio.run(harness.coordinator.terminate(session_id))
        is LeaseTerminationOutcome.FINISHED
    )
    assert harness.provider.termination_calls == ["sb-current"]
    assert harness.transport.session_control(session_id) is successor_control


def test_assigned_termination_cannot_overwrite_a_successor_generation():
    async def scenario():
        harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
        harness.provider.termination_started = asyncio.Event()
        harness.provider.allow_termination = asyncio.Event()
        session_id = harness.add_lease()
        harness.add_interval(session_id)
        harness.register_control(session_id, "sb-current")

        termination = asyncio.create_task(harness.coordinator.terminate(session_id))
        await asyncio.wait_for(
            harness.provider.termination_started.wait(),
            timeout=1,
        )
        with harness.sessions() as db, db.begin():
            lease = db.get(ChatSandboxLease, session_id)
            lease.state = "ready"
            lease.modal_sandbox_id = "sb-successor"
            lease.worker_generation = "generation-successor"
            lease.lease_token_hash = "successor-token"
            lease.lease_expires_at = None
            lease.failure_code = None
        successor_control = harness.register_control(session_id, "sb-successor")
        harness.provider.allow_termination.set()

        assert await termination is LeaseTerminationOutcome.OWNERSHIP_CHANGED
        with harness.sessions() as db:
            lease = db.get(ChatSandboxLease, session_id)
        assert lease.state == "ready"
        assert lease.modal_sandbox_id == "sb-successor"
        assert lease.worker_generation == "generation-successor"
        assert lease.lease_token_hash == "successor-token"
        assert harness.transport.session_control(session_id) is successor_control
        interval = _interval(harness)
        assert interval.terminal_reason is None
        assert interval.reconciliation_state == "confirmed"

    asyncio.run(scenario())


def test_spend_policy_locks_capacity_before_a_no_sandbox_lease_finish():
    harness = _Harness(
        _settings(
            chat_blank_pool_enabled=False,
            chat_sandbox_spend_enforcement_enabled=True,
        )
    )
    session_id = harness.add_lease(sandbox_id=None)
    order: list[str] = []
    original_load = harness.repository.load_lease

    def capacity_locker(db):
        order.append("capacity")
        db.info["finalizing"] = True
        return True

    def load_lease(db, candidate_session_id, *, lock):
        if db.info.get("finalizing"):
            order.append("lease")
        return original_load(db, candidate_session_id, lock=lock)

    harness.coordinator.capacity_locker = capacity_locker
    harness.repository.load_lease = load_lease

    assert (
        asyncio.run(harness.coordinator.terminate(session_id))
        is LeaseTerminationOutcome.FINISHED
    )
    assert order == ["capacity", "lease"]
    assert harness.provider.termination_calls == []


def test_finalization_orders_capacity_lease_spend_and_rolls_back_on_spend_failure():
    harness = _Harness(
        _settings(
            chat_blank_pool_enabled=False,
            chat_sandbox_spend_enforcement_enabled=True,
        )
    )
    session_id = harness.add_lease()
    order: list[str] = []
    original_load = harness.repository.load_lease

    def capacity_locker(db):
        order.append("capacity")
        db.info["finalizing"] = True
        return True

    def load_lease(db, candidate_session_id, *, lock):
        if db.info.get("finalizing"):
            order.append("lease")
        return original_load(db, candidate_session_id, lock=lock)

    class Spend:
        def terminate(self, *_args, **_kwargs):
            order.append("spend")
            raise RuntimeError("spend unavailable")

    harness.coordinator.capacity_locker = capacity_locker
    harness.repository.load_lease = load_lease
    harness.coordinator.spend_factory = lambda _db: Spend()

    with pytest.raises(RuntimeError, match="spend unavailable"):
        asyncio.run(harness.coordinator.terminate(session_id))

    assert order == ["capacity", "lease", "spend"]
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == "terminating"
    assert lease.modal_sandbox_id == "sb-current"
    assert lease.lease_token_hash == harness.repository.token_hash("termination-token")


def test_database_finish_failure_leaves_claim_and_spend_open_for_reconciliation():
    harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
    session_id = harness.add_lease()
    harness.add_interval(session_id)

    def fail_finish(*_args, **_kwargs):
        raise RuntimeError("lease finish unavailable")

    harness.repository.finish_termination = fail_finish

    with pytest.raises(RuntimeError, match="lease finish unavailable"):
        asyncio.run(harness.coordinator.terminate(session_id))

    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    interval = _interval(harness)
    assert harness.provider.termination_calls == ["sb-current"]
    assert lease.state == "terminating"
    assert lease.modal_sandbox_id == "sb-current"
    assert lease.lease_token_hash == harness.repository.token_hash("termination-token")
    assert interval.terminal_at is None
    assert interval.reconciliation_state == "local"


def test_worker_termination_requires_the_exact_token_and_generation():
    harness = _Harness()
    session_id = harness.add_lease(
        state="busy",
        token_hash="worker-token",
    )
    stale = WorkerClaim(
        sandbox_id="sb-current",
        token_hash="worker-token",
        assignment_token="assignment",
        worker_generation="generation-successor",
    )

    outcome = asyncio.run(
        harness.coordinator.terminate_worker(
            session_id,
            stale,
            failure_code="sandbox_worker_failed",
        )
    )

    assert outcome is LeaseTerminationOutcome.NOT_CLAIMED
    assert harness.provider.termination_calls == []
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == "busy"
    assert lease.lease_token_hash == "worker-token"


def test_exact_worker_claim_termination_preserves_failure_and_boolean_semantics():
    harness = _Harness()
    session_id = harness.add_lease(
        state="busy",
        token_hash="worker-token",
    )
    harness.register_control(session_id, "sb-current")
    claim = WorkerClaim(
        sandbox_id="sb-current",
        token_hash="worker-token",
        assignment_token="assignment",
        worker_generation="generation-current",
    )

    outcome = asyncio.run(
        harness.coordinator.terminate_worker(
            session_id,
            claim,
            failure_code="cancel_timeout",
        )
    )

    assert outcome is LeaseTerminationOutcome.FINISHED
    assert outcome.acquired is True
    assert harness.provider.termination_calls == ["sb-current"]
    assert harness.transport.session_control(session_id) is None
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == "failed"
    assert lease.modal_sandbox_id is None
    assert lease.failure_code == "cancel_timeout"


def test_worker_termination_cannot_overwrite_a_successor_or_drop_its_control():
    async def scenario():
        harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
        harness.provider.termination_started = asyncio.Event()
        harness.provider.allow_termination = asyncio.Event()
        session_id = harness.add_lease(
            state="busy",
            token_hash="worker-token",
        )
        harness.add_interval(session_id)
        harness.register_control(session_id, "sb-current")
        claim = WorkerClaim(
            sandbox_id="sb-current",
            token_hash="worker-token",
            assignment_token="assignment",
            worker_generation="generation-current",
        )

        termination = asyncio.create_task(
            harness.coordinator.terminate_worker(
                session_id,
                claim,
                failure_code="sandbox_worker_failed",
            )
        )
        await asyncio.wait_for(
            harness.provider.termination_started.wait(),
            timeout=1,
        )
        with harness.sessions() as db, db.begin():
            lease = db.get(ChatSandboxLease, session_id)
            lease.state = "ready"
            lease.modal_sandbox_id = "sb-successor"
            lease.worker_generation = "generation-successor"
            lease.lease_token_hash = None
            lease.lease_expires_at = None
            lease.failure_code = None
        successor_control = harness.register_control(session_id, "sb-successor")
        harness.provider.allow_termination.set()

        assert await termination is LeaseTerminationOutcome.OWNERSHIP_CHANGED
        with harness.sessions() as db:
            lease = db.get(ChatSandboxLease, session_id)
        assert lease.state == "ready"
        assert lease.modal_sandbox_id == "sb-successor"
        assert lease.worker_generation == "generation-successor"
        assert harness.transport.session_control(session_id) is successor_control
        interval = _interval(harness)
        assert interval.terminal_reason == "sandbox_worker_failed"
        assert interval.reconciliation_state == "confirmed"

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_provider_failure_or_cancellation_leaves_a_durable_termination_claim(cancel):
    async def scenario():
        harness = _Harness()
        session_id = harness.add_lease()
        if cancel:
            harness.provider.termination_started = asyncio.Event()
            harness.provider.allow_termination = asyncio.Event()
            operation = asyncio.create_task(harness.coordinator.terminate(session_id))
            await asyncio.wait_for(
                harness.provider.termination_started.wait(),
                timeout=1,
            )
            operation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await operation
        else:
            harness.provider.termination_error = RuntimeError("provider unavailable")
            with pytest.raises(RuntimeError, match="provider unavailable"):
                await harness.coordinator.terminate(session_id)

        with harness.sessions() as db:
            lease = db.get(ChatSandboxLease, session_id)
        assert lease.state == "terminating"
        assert lease.modal_sandbox_id == "sb-current"
        assert lease.lease_token_hash == harness.repository.token_hash(
            "termination-token"
        )

    asyncio.run(scenario())


def test_cleanup_deleted_removes_exact_controls_spend_and_snapshot():
    harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
    session_id = harness.add_lease()
    other_session_id = harness.add_lease(sandbox_id="sb-other")
    harness.add_interval(session_id)
    harness.register_control(session_id, "sb-current")
    other_control = harness.register_control(other_session_id, "sb-other")

    assert (
        asyncio.run(
            harness.coordinator.cleanup_deleted("sb-current", "snapshot-current")
        )
        is None
    )

    assert harness.transport.session_control(session_id) is None
    assert harness.transport.session_control(other_session_id) is other_control
    assert harness.snapshots.deleted == ["snapshot-current"]
    interval = _interval(harness)
    assert interval.terminal_reason == "session_deleted"
    assert interval.reconciliation_state == "confirmed"


def test_unconfirmed_deleted_cleanup_settles_spend_deletes_snapshot_then_raises():
    harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
    harness.provider.confirmed = False
    session_id = harness.add_lease()
    harness.add_interval(session_id)

    with pytest.raises(
        SandboxCleanupUnverified,
        match="could not be confirmed",
    ):
        asyncio.run(
            harness.coordinator.cleanup_deleted("sb-current", "snapshot-current")
        )

    assert harness.snapshots.deleted == ["snapshot-current"]
    interval = _interval(harness)
    assert interval.terminal_reason == "session_deleted"
    assert interval.reconciliation_state == "termination_uncertain"


def test_blank_deleted_identifiers_preserve_the_legacy_noop_contract():
    harness = _Harness()

    assert asyncio.run(harness.coordinator.cleanup_deleted("", "")) is None
    assert harness.probe.io_calls == []


def test_cancellation_during_snapshot_deletion_propagates_after_provider_cleanup():
    async def scenario():
        harness = _Harness()
        harness.snapshots.delete_started = asyncio.Event()
        harness.snapshots.allow_delete = asyncio.Event()
        operation = asyncio.create_task(
            harness.coordinator.cleanup_deleted("sb-current", "snapshot-current")
        )
        await asyncio.wait_for(harness.snapshots.delete_started.wait(), timeout=1)
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation

        assert harness.provider.termination_calls == ["sb-current"]
        assert harness.snapshots.deleted == ["snapshot-current"]

    asyncio.run(scenario())


@pytest.mark.parametrize("failure_stage", ["provider", "spend", "snapshot"])
def test_deleted_cleanup_failure_stops_at_the_exact_operational_boundary(
    failure_stage,
):
    harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
    if failure_stage == "provider":
        harness.provider.termination_error = RuntimeError("provider unavailable")
    elif failure_stage == "spend":

        class Spend:
            def terminate(self, *_args, **_kwargs):
                raise RuntimeError("spend unavailable")

        harness.coordinator.spend_factory = lambda _db: Spend()
    else:
        harness.snapshots.delete_error = RuntimeError("snapshot unavailable")

    with pytest.raises(RuntimeError, match=f"{failure_stage} unavailable"):
        asyncio.run(
            harness.coordinator.cleanup_deleted("sb-current", "snapshot-current")
        )

    if failure_stage in {"provider", "spend"}:
        assert harness.snapshots.deleted == []
    else:
        assert harness.snapshots.deleted == ["snapshot-current"]


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(0, 1), (99, MAX_LEASE_TERMINATION_CONCURRENCY)],
)
def test_termination_concurrency_is_clamped_to_the_safe_bound(configured, expected):
    harness = _Harness(termination_concurrency=configured)

    assert harness.coordinator.termination_concurrency == expected


def test_coordinator_rejects_mismatched_provider_transport_and_idle_eviction():
    harness = _Harness()
    other_provider = _Provider(harness.probe)

    with pytest.raises(ValueError, match="provider and transport must be shared"):
        ChatSandboxLeaseLifecycleCoordinator(
            harness.settings,
            session_factory=harness.sessions,
            repository=harness.repository,
            provider=other_provider,
            transport=harness.transport,
            snapshots=harness.snapshots,
            idle_eviction=harness.idle_eviction,
        )

    other_transport = ChatSandboxWorkerTransport(harness.provider)
    other_idle_eviction = ChatSandboxLeaseEvictionCoordinator(
        harness.settings,
        session_factory=harness.sessions,
        repository=harness.repository,
        provider=harness.provider,
        transport=other_transport,
        snapshots=harness.snapshots,
    )
    with pytest.raises(ValueError, match="idle eviction transports must be shared"):
        ChatSandboxLeaseLifecycleCoordinator(
            harness.settings,
            session_factory=harness.sessions,
            repository=harness.repository,
            provider=harness.provider,
            transport=harness.transport,
            snapshots=harness.snapshots,
            idle_eviction=other_idle_eviction,
        )


def test_manager_lifecycle_facades_preserve_void_contracts():
    session_id = uuid.uuid4()

    class Lifecycle:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def terminate(self, candidate_session_id, *, failure_code):
            self.calls.append(("terminate", candidate_session_id, failure_code))
            return LeaseTerminationOutcome.FINISHED

        async def cleanup_deleted(self, sandbox_id, snapshot_id):
            self.calls.append(("cleanup", sandbox_id, snapshot_id))

    lifecycle = Lifecycle()
    provider = _Provider(_TransactionProbe())
    manager = SandboxSessionManager(
        _settings(),
        sandbox_provider=provider,
        lease_lifecycle_coordinator=lifecycle,
    )

    async def run():
        return (
            await manager.terminate(session_id, failure_code="requested"),
            await manager.cleanup_deleted("sb-current", "snapshot-current"),
        )

    assert asyncio.run(run()) == (None, None)
    assert lifecycle.calls[0] == ("terminate", session_id, "requested")
    assert lifecycle.calls[-1] == ("cleanup", "sb-current", "snapshot-current")
    assert LegacySandboxCleanupUnverified is SandboxCleanupUnverified
