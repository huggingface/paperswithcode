"""Compatibility facade for focused blank sandbox pool coordinators."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    ChatSandboxLeaseEvictionCoordinator,
)
from backend.services.chat_sandbox_pool_acquisition_coordinator import (
    ChatSandboxPoolAcquisitionCoordinator,
)
from backend.services.chat_sandbox_pool_creation_coordinator import (
    ChatSandboxPoolCreationCoordinator,
)
from backend.services.chat_sandbox_pool_maintenance_coordinator import (
    POOL_LOCAL_HEALTH_MAX_AGE_SECONDS as POOL_LOCAL_HEALTH_MAX_AGE_SECONDS,
)
from backend.services.chat_sandbox_pool_maintenance_coordinator import (
    POOL_MAINTENANCE_BATCH_SIZE as POOL_MAINTENANCE_BATCH_SIZE,
)
from backend.services.chat_sandbox_pool_maintenance_coordinator import (
    POOL_MAINTENANCE_LOCK_NAME as POOL_MAINTENANCE_LOCK_NAME,
)
from backend.services.chat_sandbox_pool_maintenance_coordinator import (
    POOL_TERMINAL_RETENTION_DAYS as POOL_TERMINAL_RETENTION_DAYS,
)
from backend.services.chat_sandbox_pool_maintenance_coordinator import (
    ChatSandboxPoolMaintenanceCoordinator,
    PoolMaintenanceResult,
    lock_pool_maintenance,
)
from backend.services.chat_sandbox_pool_policy import (
    POOL_TERMINATION_MAX_CONCURRENCY as POOL_TERMINATION_MAX_CONCURRENCY,
)
from backend.services.chat_sandbox_pool_policy import ChatSandboxPoolPolicy
from backend.services.chat_sandbox_pool_repository import (
    ChatSandboxPoolRepository,
    PoolTerminationClaim,
)
from backend.services.chat_sandbox_provider import SandboxProvider
from backend.services.chat_sandbox_spend_service import (
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_worker_transport import ChatSandboxWorkerTransport

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
UtcClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]
MaintenanceOwner = Callable[[], bool]
MaintenanceLocker = Callable[[Session], bool]


class ChatSandboxPoolCoordinator:
    """Preserve the pool API while composing its focused owners."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        repository: ChatSandboxPoolRepository,
        provider: SandboxProvider,
        transport: ChatSandboxWorkerTransport,
        maintenance_owner: MaintenanceOwner,
        lease_eviction: ChatSandboxLeaseEvictionCoordinator,
        maintenance_locker: MaintenanceLocker = lock_pool_maintenance,
        spend_factory: SpendFactory | None = None,
        utcnow: UtcClock | None = None,
        monotonic: MonotonicClock = time.monotonic,
    ):
        if transport.provider is not provider:
            raise ValueError("Pool coordinator provider and transport must be shared")
        self.settings = settings
        self.session_factory = session_factory
        self.repository = repository
        self.provider = provider
        self.transport = transport
        self.maintenance_owner = maintenance_owner
        self.lease_eviction = lease_eviction
        self.maintenance_locker = maintenance_locker
        self.spend_factory = spend_factory or (
            lambda db: ChatSandboxSpendService(db, settings)
        )
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.monotonic = monotonic

        executor_runtime = None
        if settings.chat_executor_remote_transport_enabled:
            from backend.services.chat_executor_runtime import ChatExecutorRuntime

            executor_runtime = ChatExecutorRuntime(
                settings, session_factory=session_factory
            )
        self.policy = ChatSandboxPoolPolicy(settings)
        self.creation = ChatSandboxPoolCreationCoordinator(
            executor_runtime=executor_runtime,
            policy=self.policy,
            session_factory=session_factory,
            repository=repository,
            provider=provider,
            transport=transport,
            maintenance_owner=maintenance_owner,
            maintenance_locker=maintenance_locker,
            lease_eviction=lease_eviction,
            spend_factory=self.spend_factory,
            utcnow=self.utcnow,
            monotonic=monotonic,
        )
        self.maintenance = ChatSandboxPoolMaintenanceCoordinator(
            policy=self.policy,
            session_factory=session_factory,
            repository=repository,
            provider=provider,
            transport=transport,
            maintenance_owner=maintenance_owner,
            maintenance_locker=maintenance_locker,
            spend_factory=self.spend_factory,
            utcnow=self.utcnow,
            monotonic=monotonic,
            creation=self.creation,
        )
        self.acquisition = ChatSandboxPoolAcquisitionCoordinator(
            policy=self.policy,
            session_factory=session_factory,
            repository=repository,
            transport=transport,
            spend_factory=self.spend_factory,
            utcnow=self.utcnow,
            monotonic=monotonic,
            creation=self.creation,
            maintenance=self.maintenance,
        )

    @property
    def termination_claim_timeout_seconds(self) -> float:
        return self.policy.termination_claim_timeout_seconds

    @property
    def termination_concurrency(self) -> int:
        return self.policy.termination_concurrency

    @property
    def ready_timeout_seconds(self) -> float:
        return self.policy.ready_timeout_seconds

    def spawn_replenishment(self) -> None:
        self.creation.spawn_replenishment()

    async def pool_sandbox_health(
        self,
        sandbox_id: str,
        worker_generation: str,
    ) -> object | None:
        return await self.maintenance.pool_sandbox_health(
            sandbox_id,
            worker_generation,
        )

    async def claim_blank(
        self,
        chat_session_id: uuid.UUID,
    ) -> tuple[object, int] | None:
        return await self.acquisition.claim_blank(chat_session_id)

    async def replenish_pool(self) -> int:
        return await self.creation.replenish_count()

    async def terminate_pool_row(
        self,
        pool_id: uuid.UUID,
        sandbox_id: str | None,
        *,
        failure_code: str | None,
    ) -> bool:
        return await self.maintenance.terminate_pool_row(
            pool_id,
            sandbox_id,
            failure_code=failure_code,
        )

    async def terminate_claimed_pool_row(
        self,
        claim: PoolTerminationClaim,
    ) -> bool:
        return await self.maintenance.terminate_claimed_pool_row(claim)

    async def terminate_claimed_pool_rows(
        self,
        claims: list[PoolTerminationClaim],
    ) -> int:
        return await self.maintenance.terminate_claimed_pool_rows(claims)

    async def reconcile_pool_orphans(self) -> int:
        return await self.maintenance.reconcile_pool_orphans()

    async def maintain_pool(self) -> PoolMaintenanceResult:
        return await self.maintenance.maintain_pool()
