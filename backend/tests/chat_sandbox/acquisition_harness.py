"""Acquisition coordinator builder shared by sandbox and executor tests."""

from __future__ import annotations


from backend.services.chat_sandbox_acquisition_coordinator import (
    ChatSandboxAcquisitionCoordinator,
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
from backend.services.chat_sandbox_state_repository import ChatSandboxStateRepository
from backend.services.chat_sandbox_worker_transport import ChatSandboxWorkerTransport


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
