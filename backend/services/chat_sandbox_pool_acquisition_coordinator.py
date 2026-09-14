"""Health-checked acquisition of durable blank sandbox pool workers."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.services.chat_sandbox_pool_creation_coordinator import (
    ChatSandboxPoolCreationCoordinator,
)
from backend.services.chat_sandbox_pool_maintenance_coordinator import (
    ChatSandboxPoolMaintenanceCoordinator,
    PoolHealthUnavailable,
)
from backend.services.chat_sandbox_pool_policy import ChatSandboxPoolPolicy
from backend.services.chat_sandbox_pool_repository import (
    BlankPoolCandidate,
    BlankPoolClaim,
    ChatSandboxPoolRepository,
    PoolCompatibility,
)
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
)

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
UtcClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]


class ChatSandboxPoolAcquisitionCoordinator:
    """Find, verify, and atomically bind one compatible blank worker."""

    def __init__(
        self,
        *,
        policy: ChatSandboxPoolPolicy,
        session_factory: SessionFactory,
        repository: ChatSandboxPoolRepository,
        transport: ChatSandboxWorkerTransport,
        spend_factory: SpendFactory,
        utcnow: UtcClock,
        monotonic: MonotonicClock,
        creation: ChatSandboxPoolCreationCoordinator,
        maintenance: ChatSandboxPoolMaintenanceCoordinator,
    ):
        self.policy = policy
        self.settings = policy.settings
        self.session_factory = session_factory
        self.repository = repository
        self.transport = transport
        self.spend_factory = spend_factory
        self.utcnow = utcnow
        self.monotonic = monotonic
        self.creation = creation
        self.maintenance = maintenance

    async def claim_blank(
        self,
        chat_session_id: uuid.UUID,
    ) -> tuple[object, int] | None:
        """Health-check and atomically bind one compatible blank worker."""

        if not (
            self.policy.enabled
            and getattr(self.settings, "chat_persistent_worker_enabled", False)
        ):
            return None
        started = self.monotonic()
        now = self.utcnow()
        minimum_expiry = now + timedelta(
            seconds=self.settings.chat_blank_pool_min_remaining_seconds
        )
        compatibility = self.repository.compatibility()
        # Release identifies the creator for audit; immutable worker and resource
        # compatibility determines whether an unassigned blank can be reused.
        with self.session_factory() as db:
            if (
                self.settings.chat_executor_remote_transport_enabled
                and self.repository.lease_loader(db, chat_session_id, lock=False)
                is not None
            ):
                return None
            candidates = self.repository.list_claim_candidates(
                db,
                compatibility,
                minimum_expires_at=minimum_expiry,
                limit=self.settings.chat_blank_pool_max,
            )
        for candidate in candidates:
            if not candidate.sandbox_id:
                await self.maintenance.terminate_pool_row(
                    candidate.pool_id,
                    None,
                    failure_code="sandbox_lost",
                )
                continue
            try:
                sandbox = await self.maintenance.pool_sandbox_health(
                    candidate.sandbox_id,
                    candidate.worker_generation,
                )
            except PoolHealthUnavailable:
                continue
            if sandbox is None:
                await self.maintenance.terminate_pool_row(
                    candidate.pool_id,
                    candidate.sandbox_id,
                    failure_code="sandbox_lost",
                )
                continue
            local_control = self.transport.blank_control(candidate.sandbox_id)
            claim = self._claim_candidate(
                candidate,
                chat_session_id,
                compatibility,
            )
            if claim is None:
                continue
            if local_control is not None:
                self.transport.promote_blank_control(
                    claim.sandbox_id,
                    chat_session_id,
                    expected=local_control,
                )
            self.creation.spawn_replenishment()
            return sandbox, round((self.monotonic() - started) * 1000)
        return None

    def _claim_candidate(
        self,
        candidate: BlankPoolCandidate,
        chat_session_id: uuid.UUID,
        compatibility: PoolCompatibility,
    ) -> BlankPoolClaim | None:
        now = self.utcnow()
        with self.session_factory() as db:
            spend = None
            availability_assertion = None
            if self.policy.spend_enforced:
                spend = self.spend_factory(db)

                def availability_assertion(
                    *,
                    spend_service: ChatSandboxSpendService = spend,
                    checked_at: datetime = now,
                ) -> None:
                    spend_service.assert_available(
                        checked_at,
                        capacity_locked=True,
                    )

                try:
                    claim = self.repository.claim_blank(
                        db,
                        candidate,
                        chat_session_id,
                        compatibility,
                        minimum_expires_at=now
                        + timedelta(
                            seconds=(
                                self.settings.chat_blank_pool_min_remaining_seconds
                            )
                        ),
                        now=now,
                        availability_assertion=availability_assertion,
                    )
                except ChatComputeDisabled as error:
                    # Persist the circuit event emitted by assert_available.
                    db.commit()
                    raise SandboxError(error.code, str(error)) from error
            else:
                claim = self.repository.claim_blank(
                    db,
                    candidate,
                    chat_session_id,
                    compatibility,
                    minimum_expires_at=now
                    + timedelta(
                        seconds=self.settings.chat_blank_pool_min_remaining_seconds
                    ),
                    now=now,
                )
            if claim is not None and spend is not None:
                spend.claim(
                    claim.sandbox_id,
                    chat_session_id,
                    now,
                )
            db.commit()
        return claim
