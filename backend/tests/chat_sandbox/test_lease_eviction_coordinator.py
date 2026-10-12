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
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSession,
)
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    ChatSandboxLeaseEvictionCoordinator,
    LeaseEvictionOutcome,
)
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
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
        ChatSandboxBudgetState.__table__,
        ChatSandboxComputeInterval.__table__,
        ChatSandboxCircuitEvent.__table__,
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
        self.resolve_calls: list[str] = []
        self.termination_calls: list[str] = []
        self.confirmed = True
        self.termination_error: Exception | None = None
        self.termination_started: asyncio.Event | None = None
        self.allow_termination: asyncio.Event | None = None

    async def resolve(self, sandbox_id: str):
        self.probe.outside_transaction("provider.resolve")
        self.resolve_calls.append(sandbox_id)
        return SimpleNamespace(object_id=sandbox_id)

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


class _Snapshots:
    supported = True

    def __init__(self, probe: _TransactionProbe) -> None:
        self.probe = probe
        self.calls: list[tuple[str, uuid.UUID]] = []
        self.error: Exception | None = None
        self.started: asyncio.Event | None = None
        self.allow_save: asyncio.Event | None = None

    async def save(self, sandbox, chat_session_id: uuid.UUID) -> str:
        self.probe.outside_transaction("snapshot.save")
        self.calls.append((sandbox.object_id, chat_session_id))
        if self.started is not None:
            self.started.set()
        if self.allow_save is not None:
            await self.allow_save.wait()
        if self.error is not None:
            raise self.error
        return "snapshot-new"


class _Harness:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or _settings()
        self.now = datetime(2026, 8, 10, 12, tzinfo=UTC)
        self.probe = _TransactionProbe()
        self.sessions = _database(self.probe)
        self.repository = ChatSandboxStateRepository(self.settings)
        self.provider = _Provider(self.probe)
        self.transport = ChatSandboxWorkerTransport(self.provider)
        self.snapshots = _Snapshots(self.probe)
        self.coordinator = ChatSandboxLeaseEvictionCoordinator(
            self.settings,
            session_factory=self.sessions,
            repository=self.repository,
            provider=self.provider,
            transport=self.transport,
            snapshots=self.snapshots,
            capacity_locker=lambda _db: True,
            utcnow=lambda: self.now,
            token_factory=lambda: "termination-token",
        )

    def add_lease(
        self,
        *,
        state: str = "idle",
        sandbox_id: str | None = "sb-idle",
        workspace_dirty: bool = False,
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
                        worker_generation="generation-idle",
                        state=state,
                        last_activity_at=self.now,
                        workspace_dirty=workspace_dirty,
                        created_at=self.now,
                        updated_at=self.now,
                    ),
                ]
            )
        return session_id

    def register_control(self, session_id: uuid.UUID, sandbox_id: str) -> None:
        self.transport.register_session_control(
            session_id,
            SessionControl(
                process=object(),
                sandbox=SimpleNamespace(object_id=sandbox_id),
                sandbox_id=sandbox_id,
                stderr_task=None,
                reader_task=None,
                queues={},
                resume_id=None,
            ),
        )

    def add_interval(self, session_id: uuid.UUID, sandbox_id: str = "sb-idle") -> None:
        with self.sessions() as db, db.begin():
            db.add(
                ChatSandboxComputeInterval(
                    id=uuid.uuid4(),
                    modal_sandbox_id=sandbox_id,
                    environment=self.settings.environment,
                    modal_app="pwc-chat-sandbox",
                    app_release_id=self.settings.release_id,
                    image_version=self.settings.chat_modal_image_version,
                    worker_generation="generation-idle",
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


@pytest.mark.parametrize(
    ("state", "sandbox_id"),
    [("ready", "sb-idle"), ("idle", None)],
)
def test_ineligible_lease_has_a_typed_noop_outcome(state, sandbox_id):
    harness = _Harness()
    session_id = harness.add_lease(state=state, sandbox_id=sandbox_id)

    outcome = asyncio.run(harness.coordinator.evict_idle(session_id))

    assert outcome is LeaseEvictionOutcome.NOT_IDLE
    assert outcome.acquired is False
    assert harness.probe.io_calls == []
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == state
    assert lease.modal_sandbox_id == sandbox_id
    assert lease.lease_token_hash is None


def test_missing_lease_has_a_typed_noop_outcome():
    harness = _Harness()

    outcome = asyncio.run(harness.coordinator.evict_idle(uuid.uuid4()))

    assert outcome is LeaseEvictionOutcome.NOT_IDLE
    assert outcome.acquired is False
    assert harness.probe.io_calls == []


def test_coordinator_requires_provider_and_transport_identity():
    harness = _Harness()

    with pytest.raises(ValueError, match="provider and transport must be shared"):
        ChatSandboxLeaseEvictionCoordinator(
            harness.settings,
            session_factory=harness.sessions,
            repository=harness.repository,
            provider=_Provider(harness.probe),
            transport=harness.transport,
            snapshots=harness.snapshots,
        )


def test_snapshot_termination_finishes_the_exact_lease_and_spend_interval():
    settings = _settings(
        chat_workspace_snapshots_enabled=True,
        chat_sandbox_spend_enforcement_enabled=True,
    )
    harness = _Harness(settings)
    session_id = harness.add_lease(workspace_dirty=True)
    harness.register_control(session_id, "sb-idle")
    harness.add_interval(session_id)

    outcome = asyncio.run(harness.coordinator.evict_idle(session_id))

    assert outcome is LeaseEvictionOutcome.EVICTED
    assert outcome.acquired is True
    assert harness.probe.io_calls == [
        "provider.resolve",
        "snapshot.save",
        "provider.terminate",
    ]
    assert harness.transport.session_control(session_id) is None
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
        interval = db.execute(
            select(ChatSandboxComputeInterval).where(
                ChatSandboxComputeInterval.modal_sandbox_id == "sb-idle"
            )
        ).scalar_one()
    assert lease.state == "terminated"
    assert lease.modal_sandbox_id is None
    assert lease.lease_token_hash is None
    assert lease.workspace_snapshot_id == "snapshot-new"
    assert lease.snapshot_image_version == settings.chat_modal_image_version
    assert lease.workspace_dirty is False
    assert interval.terminal_reason == "snapshot_complete"
    assert interval.terminal_at.replace(tzinfo=UTC) == harness.now
    assert interval.reserved_microusd == 0
    assert interval.reconciliation_state == "confirmed"


@pytest.mark.parametrize("failure_stage", ["save", "record"])
def test_snapshot_failure_is_recoverable_and_does_not_block_termination(
    failure_stage,
):
    harness = _Harness(_settings(chat_workspace_snapshots_enabled=True))
    if failure_stage == "save":
        harness.snapshots.error = RuntimeError("snapshot unavailable")
    else:

        def fail_record(*_args, **_kwargs):
            raise RuntimeError("snapshot record unavailable")

        harness.repository.record_snapshot = fail_record
    session_id = harness.add_lease(workspace_dirty=True)

    outcome = asyncio.run(harness.coordinator.evict_idle(session_id))

    assert outcome is LeaseEvictionOutcome.EVICTED
    assert harness.provider.termination_calls == ["sb-idle"]
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == "terminated"
    assert lease.workspace_snapshot_id is None
    assert lease.workspace_dirty is True


def test_snapshot_io_cannot_overwrite_or_terminate_a_successor_generation():
    async def scenario():
        harness = _Harness(
            _settings(
                chat_workspace_snapshots_enabled=True,
                chat_sandbox_spend_enforcement_enabled=True,
            )
        )
        harness.snapshots.started = asyncio.Event()
        harness.snapshots.allow_save = asyncio.Event()
        session_id = harness.add_lease(workspace_dirty=True)
        harness.add_interval(session_id)
        harness.register_control(session_id, "sb-idle")
        original_control = harness.transport.session_control(session_id)

        eviction = asyncio.create_task(harness.coordinator.evict_idle(session_id))
        await harness.snapshots.started.wait()
        with harness.sessions() as db, db.begin():
            lease = db.get(ChatSandboxLease, session_id)
            lease.state = "idle"
            lease.modal_sandbox_id = "sb-successor"
            lease.worker_generation = "generation-successor"
            lease.lease_token_hash = None
            lease.lease_expires_at = None
            lease.workspace_snapshot_id = "snapshot-successor"
            lease.snapshot_image_version = "im-current"
            lease.workspace_dirty = False
        harness.register_control(session_id, "sb-successor")
        successor_control = harness.transport.session_control(session_id)
        assert successor_control is not original_control
        harness.snapshots.allow_save.set()

        assert await eviction is LeaseEvictionOutcome.OWNERSHIP_CHANGED
        assert harness.provider.termination_calls == ["sb-idle"]
        with harness.sessions() as db:
            lease = db.get(ChatSandboxLease, session_id)
        assert lease.state == "idle"
        assert lease.modal_sandbox_id == "sb-successor"
        assert lease.worker_generation == "generation-successor"
        assert lease.workspace_snapshot_id == "snapshot-successor"
        assert lease.lease_token_hash is None
        assert harness.transport.session_control(session_id) is successor_control
        with harness.sessions() as db:
            interval = db.execute(
                select(ChatSandboxComputeInterval).where(
                    ChatSandboxComputeInterval.modal_sandbox_id == "sb-idle"
                )
            ).scalar_one()
        assert interval.terminal_reason == "snapshot_complete"
        assert interval.reconciliation_state == "confirmed"

    asyncio.run(scenario())


def test_unconfirmed_provider_termination_preserves_legacy_lease_and_spend_state():
    harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
    harness.provider.confirmed = False
    session_id = harness.add_lease()
    harness.add_interval(session_id)

    outcome = asyncio.run(harness.coordinator.evict_idle(session_id))

    assert outcome is LeaseEvictionOutcome.EVICTED
    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
        interval = db.execute(
            select(ChatSandboxComputeInterval).where(
                ChatSandboxComputeInterval.modal_sandbox_id == "sb-idle"
            )
        ).scalar_one()
    assert lease.state == "terminated"
    assert lease.modal_sandbox_id is None
    assert lease.failure_code is None
    assert interval.terminal_reason == "snapshot_complete"
    assert interval.terminal_at is None
    assert interval.reserved_microusd == 100
    assert interval.reconciliation_state == "termination_uncertain"


def test_spend_only_finalization_uses_capacity_lease_spend_lock_order():
    harness = _Harness(
        _settings(
            chat_blank_pool_enabled=False,
            chat_sandbox_spend_enforcement_enabled=True,
        )
    )
    session_id = harness.add_lease()
    order: list[str] = []

    def capacity_locker(db):
        order.append("capacity")
        db.info["finalizing"] = True
        return True

    original_load = harness.repository.load_lease

    def load_lease(db, candidate_session_id, *, lock):
        if db.info.get("finalizing"):
            order.append("lease")
        return original_load(db, candidate_session_id, lock=lock)

    class Spend:
        def terminate(self, *_args, **_kwargs):
            order.append("spend")

    harness.coordinator.capacity_locker = capacity_locker
    harness.repository.load_lease = load_lease
    harness.coordinator.spend_factory = lambda _db: Spend()

    assert (
        asyncio.run(harness.coordinator.evict_idle(session_id))
        is LeaseEvictionOutcome.EVICTED
    )
    assert order == ["capacity", "lease", "spend"]


def test_spend_failure_rolls_back_lease_finish_and_leaves_the_claim_recoverable():
    harness = _Harness(_settings(chat_sandbox_spend_enforcement_enabled=True))
    session_id = harness.add_lease()

    class Spend:
        def terminate(self, *_args, **_kwargs):
            raise RuntimeError("spend unavailable")

    harness.coordinator.spend_factory = lambda _db: Spend()

    with pytest.raises(RuntimeError, match="spend unavailable"):
        asyncio.run(harness.coordinator.evict_idle(session_id))

    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert harness.provider.termination_calls == ["sb-idle"]
    assert lease.state == "terminating"
    assert lease.modal_sandbox_id == "sb-idle"
    assert lease.lease_token_hash == harness.repository.token_hash("termination-token")


def test_cancellation_during_snapshot_leaves_the_durable_claim_for_recovery():
    async def scenario():
        harness = _Harness(_settings(chat_workspace_snapshots_enabled=True))
        harness.snapshots.started = asyncio.Event()
        harness.snapshots.allow_save = asyncio.Event()
        session_id = harness.add_lease(workspace_dirty=True)

        eviction = asyncio.create_task(harness.coordinator.evict_idle(session_id))
        await harness.snapshots.started.wait()
        eviction.cancel()
        with pytest.raises(asyncio.CancelledError):
            await eviction

        with harness.sessions() as db:
            lease = db.get(ChatSandboxLease, session_id)
        assert lease.state == "terminating"
        assert lease.modal_sandbox_id == "sb-idle"
        assert lease.worker_generation == "generation-idle"
        assert lease.lease_token_hash == harness.repository.token_hash(
            "termination-token"
        )
        assert harness.provider.termination_calls == []

    asyncio.run(scenario())


def test_cancellation_during_provider_termination_keeps_the_claim_and_drops_control():
    async def scenario():
        harness = _Harness()
        harness.provider.termination_started = asyncio.Event()
        harness.provider.allow_termination = asyncio.Event()
        session_id = harness.add_lease()
        harness.register_control(session_id, "sb-idle")

        eviction = asyncio.create_task(harness.coordinator.evict_idle(session_id))
        await harness.provider.termination_started.wait()
        eviction.cancel()
        with pytest.raises(asyncio.CancelledError):
            await eviction

        with harness.sessions() as db:
            lease = db.get(ChatSandboxLease, session_id)
        assert lease.state == "terminating"
        assert lease.modal_sandbox_id == "sb-idle"
        assert lease.lease_token_hash == harness.repository.token_hash(
            "termination-token"
        )
        assert harness.transport.session_control(session_id) is None

    asyncio.run(scenario())


def test_provider_termination_failure_leaves_the_durable_claim_for_reconciliation():
    harness = _Harness()
    harness.provider.termination_error = RuntimeError("provider unavailable")
    session_id = harness.add_lease()

    with pytest.raises(RuntimeError, match="provider unavailable"):
        asyncio.run(harness.coordinator.evict_idle(session_id))

    with harness.sessions() as db:
        lease = db.get(ChatSandboxLease, session_id)
    assert lease.state == "terminating"
    assert lease.modal_sandbox_id == "sb-idle"
    assert lease.lease_token_hash == harness.repository.token_hash("termination-token")


def test_manager_snapshot_facade_preserves_the_legacy_boolean_contract():
    session_id = uuid.uuid4()

    class Eviction:
        def __init__(self) -> None:
            self.outcomes = iter(
                [
                    LeaseEvictionOutcome.EVICTED,
                    LeaseEvictionOutcome.OWNERSHIP_CHANGED,
                    LeaseEvictionOutcome.NOT_IDLE,
                ]
            )
            self.calls: list[uuid.UUID] = []

        async def evict_idle(self, candidate_session_id):
            self.calls.append(candidate_session_id)
            return next(self.outcomes)

    eviction = Eviction()
    manager = SandboxSessionManager(
        _settings(),
        sandbox_provider=_Provider(_TransactionProbe()),
        lease_eviction_coordinator=eviction,
    )

    async def run():
        return [
            await manager.snapshot_and_terminate(session_id),
            await manager.snapshot_and_terminate(session_id),
            await manager.snapshot_and_terminate(session_id),
        ]

    assert asyncio.run(run()) == [True, True, False]
    assert eviction.calls == [session_id, session_id, session_id]
