from __future__ import annotations

import asyncio
import uuid

import pytest

from backend.services.chat_sandbox_acquisition_coordinator import (
    ChatSandboxAcquisitionCoordinator,
    LeaseReused,
    SandboxCreated,
)
from backend.services.chat_sandbox_capacity_repository import (
    ChatSandboxCapacityRepository,
)
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    ChatSandboxLeaseEvictionCoordinator,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    ChatSandboxLeaseLifecycleCoordinator,
)
from backend.services.chat_sandbox_lease_maintenance_coordinator import (
    ChatSandboxLeaseMaintenanceCoordinator,
)
from backend.services.chat_sandbox_pool_coordinator import ChatSandboxPoolCoordinator
from backend.services.chat_sandbox_pool_repository import ChatSandboxPoolRepository
from backend.services.chat_sandbox_provider import SandboxLaunchMode
from backend.services.chat_sandbox_state_repository import ChatSandboxStateRepository
from backend.services.chat_sandbox_worker_transport import ChatSandboxWorkerTransport
from backend.tests.test_chat_sandbox_capacity_acquisition import (
    _database,
    _lease,
    _Provider,
    _session,
    _settings,
)


class _Snapshots:
    async def save(self, _sandbox, _chat_session_id):
        return "snapshot-test"

    async def restore(self, _sandbox, _snapshot_id):
        return None

    async def delete(self, _snapshot_id):
        return None


def _coordinator(
    settings,
    sessions,
    provider,
    *,
    state_settings=None,
    pool_repository_settings=None,
):
    def session_factory():
        db = sessions()
        provider.transactions.append(db)
        return db

    def capacity_locker(*_args, **_kwargs):
        return True

    state_repository = ChatSandboxStateRepository(state_settings or settings)
    capacity_repository = ChatSandboxCapacityRepository(
        settings,
        state_repository,
        capacity_locker=capacity_locker,
        start_locker=lambda *_args: None,
    )
    snapshots = _Snapshots()
    transport = ChatSandboxWorkerTransport(provider)
    eviction = ChatSandboxLeaseEvictionCoordinator(
        settings,
        session_factory=session_factory,
        repository=state_repository,
        provider=provider,
        transport=transport,
        snapshots=snapshots,
        capacity_locker=capacity_locker,
    )
    lifecycle = ChatSandboxLeaseLifecycleCoordinator(
        settings,
        session_factory=session_factory,
        repository=state_repository,
        provider=provider,
        transport=transport,
        snapshots=snapshots,
        idle_eviction=eviction,
        capacity_locker=capacity_locker,
    )
    maintenance = ChatSandboxLeaseMaintenanceCoordinator(
        settings,
        session_factory=session_factory,
        repository=state_repository,
        provider=provider,
        lifecycle=lifecycle,
        snapshots=snapshots,
        capacity_locker=capacity_locker,
    )
    pool_repository = ChatSandboxPoolRepository(
        pool_repository_settings or settings,
        capacity_locker=capacity_locker,
    )
    pool = ChatSandboxPoolCoordinator(
        settings,
        session_factory=session_factory,
        repository=pool_repository,
        provider=provider,
        transport=transport,
        maintenance_owner=lambda: True,
        lease_eviction=eviction,
    )
    return ChatSandboxAcquisitionCoordinator(
        settings,
        session_factory=session_factory,
        state_repository=state_repository,
        capacity_repository=capacity_repository,
        pool=pool,
        provider=provider,
        transport=transport,
        snapshots=snapshots,
        lease_maintenance=maintenance,
    )


def test_direct_coordinator_creation_returns_a_typed_outcome_without_db_io_overlap():
    settings = _settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
    provider = _Provider(transactions=[])
    coordinator = _coordinator(settings, sessions, provider)

    outcome = asyncio.run(coordinator.acquire(session_id))

    assert isinstance(outcome, SandboxCreated)
    assert outcome.sandbox is provider.created
    assert outcome.public_label == "created"
    assert outcome.created is True
    assert provider.calls[0][0] == "create"


def test_direct_coordinator_forwards_executor_launch_mode_to_provider():
    settings = _settings()
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))

    class RecordingProvider(_Provider):
        async def create(self, **options):
            self.launch_mode = options["launch_mode"]
            return await super().create(**options)

    provider = RecordingProvider(transactions=[])
    coordinator = _coordinator(settings, sessions, provider)

    asyncio.run(coordinator.acquire(session_id, launch_mode=SandboxLaunchMode.EXECUTOR))

    assert provider.launch_mode is SandboxLaunchMode.EXECUTOR


@pytest.mark.parametrize(
    ("persistent", "expected_cohort"),
    [(False, "rediscovered"), (True, "control_reconnected")],
)
def test_reused_lease_records_control_reconnection_state(persistent, expected_cohort):
    settings = _settings(chat_persistent_worker_enabled=persistent)
    sessions = _database()
    session_id = uuid.uuid4()
    with sessions() as db, db.begin():
        db.add(_session(session_id))
        db.add(
            _lease(
                settings,
                session_id,
                state="idle",
                sandbox_id="sb-reused",
                worker_generation="generation-reused",
            )
        )
    provider = _Provider(transactions=[])
    coordinator = _coordinator(settings, sessions, provider)

    outcome = asyncio.run(coordinator.acquire(session_id))

    assert isinstance(outcome, LeaseReused)
    assert outcome.reuse_cohort == expected_cohort


@pytest.mark.parametrize(
    "mismatch",
    ["state_settings", "pool_repository_settings"],
)
def test_direct_coordinator_rejects_mismatched_repository_settings(mismatch):
    settings = _settings()
    sessions = _database()
    provider = _Provider(transactions=[])

    with pytest.raises(ValueError, match="settings must be shared"):
        _coordinator(
            settings,
            sessions,
            provider,
            **{mismatch: _settings()},
        )
