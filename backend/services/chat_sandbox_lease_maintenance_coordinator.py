"""Bounded maintenance for assigned sandbox leases and snapshots."""

from __future__ import annotations

import secrets
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend.config import Settings
from backend.services.chat_sandbox_capacity_repository import lock_capacity
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    ChatSandboxLeaseLifecycleCoordinator,
)
from backend.services.chat_sandbox_provider import SandboxProvider
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    LeaseReconciliationCandidate,
)

SessionFactory = Callable[[], Session]
CapacityLocker = Callable[[Session], bool]
UtcClock = Callable[[], datetime]
TokenFactory = Callable[[], str]
QualificationCleanup = Callable[[], int]
logger = logging.getLogger(__name__)


class MaintenanceSnapshotStore(Protocol):
    async def delete(self, snapshot_id: str) -> None: ...


class ChatSandboxLeaseMaintenanceCoordinator:
    """Compose typed lease maintenance transitions with provider I/O."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        repository: ChatSandboxStateRepository,
        provider: SandboxProvider,
        lifecycle: ChatSandboxLeaseLifecycleCoordinator,
        snapshots: MaintenanceSnapshotStore,
        capacity_locker: CapacityLocker = lock_capacity,
        utcnow: UtcClock | None = None,
        token_factory: TokenFactory | None = None,
        qualification_cleanup: QualificationCleanup | None = None,
    ) -> None:
        idle_eviction = lifecycle.idle_eviction
        if lifecycle.settings is not settings or idle_eviction.settings is not settings:
            raise ValueError("Lease maintenance component settings must be shared")
        if lifecycle.session_factory is not session_factory:
            raise ValueError("Lease maintenance and lifecycle sessions must be shared")
        if idle_eviction.session_factory is not session_factory:
            raise ValueError(
                "Lease maintenance and idle eviction sessions must be shared"
            )
        if lifecycle.repository is not repository:
            raise ValueError(
                "Lease maintenance and lifecycle repositories must be shared"
            )
        if idle_eviction.repository is not repository:
            raise ValueError(
                "Lease maintenance and idle eviction repositories must be shared"
            )
        if lifecycle.provider is not provider:
            raise ValueError("Lease maintenance and lifecycle providers must be shared")
        if lifecycle.snapshots is not snapshots:
            raise ValueError("Lease maintenance and lifecycle snapshots must be shared")
        if idle_eviction.snapshots is not snapshots:
            raise ValueError(
                "Lease maintenance and idle eviction snapshots must be shared"
            )
        if lifecycle.capacity_locker is not capacity_locker:
            raise ValueError(
                "Lease maintenance and lifecycle capacity locks must be shared"
            )
        if idle_eviction.capacity_locker is not capacity_locker:
            raise ValueError(
                "Lease maintenance and idle eviction capacity locks must be shared"
            )
        self.settings = settings
        self.session_factory = session_factory
        self.repository = repository
        self.provider = provider
        self.lifecycle = lifecycle
        self.snapshots = snapshots
        self.capacity_locker = capacity_locker
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self.qualification_cleanup = qualification_cleanup or (lambda: 0)

    @property
    def ready_timeout_seconds(self) -> float:
        if getattr(self.settings, "chat_persistent_worker_enabled", False):
            return getattr(
                self.settings,
                "chat_worker_ready_timeout_seconds",
                self.settings.chat_sandbox_ready_timeout_seconds,
            )
        return self.settings.chat_sandbox_ready_timeout_seconds

    @property
    def capacity_lock_required(self) -> bool:
        blank_pool_enabled = bool(
            getattr(self.settings, "chat_blank_pool_enabled", False)
            and getattr(self.settings, "chat_sandbox_admission_enabled", True)
        )
        spend_policy_enabled = bool(
            getattr(
                self.settings,
                "chat_sandbox_spend_enforcement_enabled",
                False,
            )
        )
        return blank_pool_enabled or spend_policy_enabled

    async def reap_idle(self) -> int:
        cutoff = self.utcnow() - timedelta(
            seconds=self.settings.chat_sandbox_warm_seconds
        )
        with self.session_factory() as db:
            candidates = self.repository.list_idle_before(db, cutoff=cutoff)
        return await self.lifecycle.terminate_idle_candidates(
            candidates,
            cutoff=cutoff,
        )

    async def enforce_warm_cap(self) -> int:
        with self.session_factory() as db:
            plan = self.repository.plan_warm_cap(
                db,
                max_warm=self.settings.chat_sandbox_max_warm,
            )
        return await self.lifecycle.terminate_idle_candidates(plan.candidates)

    async def reconcile(self) -> int:
        primary_error: BaseException | None = None
        try:
            return await self._reconcile_sandboxes()
        except BaseException as error:
            primary_error = error
            raise
        finally:
            if self.settings.environment == "staging":
                try:
                    self.qualification_cleanup()
                except (OSError, SQLAlchemyError) as error:
                    logger.warning(
                        "chat qualification evidence_missing operation=retention error=%s",
                        type(error).__name__,
                    )
                except BaseException:
                    if primary_error is None:
                        raise

    async def _reconcile_sandboxes(self) -> int:
        stale_cutoff = self.utcnow()
        with self.session_factory() as db:
            stale_operations = self.repository.list_stale_operations(
                db,
                cutoff=stale_cutoff,
            )

        repaired = 0
        for candidate in stale_operations:
            with self.session_factory() as db, db.begin():
                claim = self.repository.claim_stale_candidate(
                    db,
                    candidate,
                    termination_token=self.token_factory(),
                    ready_timeout_seconds=self.ready_timeout_seconds,
                    utcnow=self.utcnow,
                )
            if claim is None:
                continue
            await self.lifecycle.terminate_claimed(
                candidate.chat_session_id,
                claim,
            )
            repaired += 1

        candidate_cutoff = self.utcnow()
        with self.session_factory() as db:
            candidates = self.repository.list_reconciliation_candidates(
                db,
                cutoff=candidate_cutoff,
            )
        for candidate in candidates:
            expected = candidate.expected
            if expected.state == "starting":
                if not expected.token_hash:
                    continue
                with self.session_factory() as db, db.begin():
                    if self.capacity_lock_required:
                        self.capacity_locker(db)
                    repaired += self.repository.fail_expired_start_candidate(
                        db,
                        candidate,
                        utcnow=self.utcnow,
                    )
                continue
            if not expected.sandbox_id:
                repaired += self._mark_lost(candidate)
                continue
            try:
                sandbox = await self.provider.resolve(expected.sandbox_id)
                alive = await self.provider.poll(sandbox) is None
            except Exception:
                alive = False
            if not alive:
                repaired += self._mark_lost(candidate)
        return repaired

    async def expire_inactive_snapshots(self) -> int:
        cutoff = self.utcnow() - timedelta(
            days=self.settings.chat_workspace_snapshot_inactivity_days
        )
        with self.session_factory() as db:
            candidates = self.repository.list_inactive_snapshots(
                db,
                cutoff=cutoff,
            )

        expired = 0
        for candidate in candidates:
            await self.snapshots.delete(candidate.claim.snapshot_id)
            with self.session_factory() as db, db.begin():
                expired += self.repository.clear_inactive_snapshot_candidate(
                    db,
                    candidate,
                )
        return expired

    def _mark_lost(self, candidate: LeaseReconciliationCandidate) -> bool:
        with self.session_factory() as db, db.begin():
            if self.capacity_lock_required:
                self.capacity_locker(db)
            return self.repository.mark_lost_candidate(
                db,
                candidate,
                utcnow=self.utcnow,
            )
