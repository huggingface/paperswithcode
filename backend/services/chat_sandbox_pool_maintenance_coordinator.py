"""Termination, health maintenance, and provider reconciliation for the pool."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.services.chat_sandbox_pool_creation_coordinator import (
    ChatSandboxPoolCreationCoordinator,
)
from backend.services.chat_sandbox_pool_policy import ChatSandboxPoolPolicy
from backend.services.chat_sandbox_pool_repository import (
    ChatSandboxPoolRepository,
    PoolHealthCheckClaim,
    PoolHealthCheckFinishOutcome,
    PoolHealthCandidate,
    PoolMaintenancePlan,
    PoolTerminationClaim,
    PoolTerminationFinishOutcome,
    ProviderPoolDisposition,
    ProviderPoolInspection,
)
from backend.services.chat_sandbox_provider import SandboxProvider
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
)

logger = logging.getLogger("backend.services.chat_sandbox_pool_coordinator")

POOL_MAINTENANCE_LOCK_NAME = "chat-sandbox-pool-maintenance-v1"
POOL_LOCAL_HEALTH_MAX_AGE_SECONDS = 15
POOL_MAINTENANCE_BATCH_SIZE = 100
POOL_TERMINAL_RETENTION_DAYS = 35
POOL_HEALTH_CLAIM_TIMEOUT_SECONDS = 30

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
UtcClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]
MaintenanceOwner = Callable[[], bool]
MaintenanceLocker = Callable[[Session], bool]


class PoolHealthUnavailable(RuntimeError):
    """A provider health check failed without proving the sandbox is dead."""


@dataclass(frozen=True)
class PoolMaintenanceResult:
    drained: int = 0
    lost: int = 0
    orphaned: int = 0
    abandoned: int = 0
    cleaned: int = 0
    replenished: int = 0


def lock_pool_maintenance(db: Session) -> bool:
    """Take the pool transaction lock; test backends use a no-op success."""

    if db.get_bind().dialect.name != "postgresql":
        return True
    return bool(
        db.scalar(
            select(
                func.pg_try_advisory_xact_lock(
                    func.hashtextextended(POOL_MAINTENANCE_LOCK_NAME, 0)
                )
            )
        )
    )


class ChatSandboxPoolMaintenanceCoordinator:
    """Own durable cleanup, health refresh, and pool reconciliation."""

    def __init__(
        self,
        *,
        policy: ChatSandboxPoolPolicy,
        session_factory: SessionFactory,
        repository: ChatSandboxPoolRepository,
        provider: SandboxProvider,
        transport: ChatSandboxWorkerTransport,
        maintenance_owner: MaintenanceOwner,
        maintenance_locker: MaintenanceLocker,
        spend_factory: SpendFactory,
        utcnow: UtcClock,
        monotonic: MonotonicClock,
        creation: ChatSandboxPoolCreationCoordinator,
    ):
        self.policy = policy
        self.settings = policy.settings
        self.session_factory = session_factory
        self.repository = repository
        self.provider = provider
        self.transport = transport
        self.maintenance_owner = maintenance_owner
        self.maintenance_locker = maintenance_locker
        self.spend_factory = spend_factory
        self.utcnow = utcnow
        self.monotonic = monotonic
        self.creation = creation
        self._lock = asyncio.Lock()

    async def pool_sandbox_health(
        self,
        sandbox_id: str,
        worker_generation: str,
    ) -> object | None:
        try:
            if self.creation.executor_runtime is not None:
                if not await self.creation.executor_runtime.pool_ready(
                    worker_generation
                ):
                    return None
                # Resolving a handle does not run a Modal command or open a
                # legacy worker control channel. Readiness came from rendezvous.
                return await self.provider.resolve(sandbox_id)
            control = self.transport.blank_control(sandbox_id)
            if control is not None:
                if control.sandbox_id != sandbox_id:
                    return None
                checked_at = self.transport.blank_health_checked_at(sandbox_id)
                if (
                    checked_at is not None
                    and self.monotonic() - checked_at
                    <= POOL_LOCAL_HEALTH_MAX_AGE_SECONDS
                ):
                    return control.sandbox
                try:
                    local_healthy = await self.transport.ping(
                        control,
                        worker_generation,
                    )
                except Exception:
                    local_healthy = False
                if local_healthy:
                    if self.transport.mark_blank_healthy(
                        sandbox_id,
                        expected=control,
                        checked_at=self.monotonic(),
                    ):
                        return control.sandbox
                    replacement = self.transport.blank_control(sandbox_id)
                    replacement_checked_at = self.transport.blank_health_checked_at(
                        sandbox_id
                    )
                    if (
                        replacement is not None
                        and replacement_checked_at is not None
                        and self.monotonic() - replacement_checked_at
                        <= POOL_LOCAL_HEALTH_MAX_AGE_SECONDS
                    ):
                        return replacement.sandbox
                self.transport.drop_blank_control(
                    sandbox_id,
                    expected=control,
                )
            sandbox = await self.provider.resolve(sandbox_id)
            if await self.provider.poll(sandbox) is not None:
                return None
            healthy = await self.provider.health(
                sandbox,
                persistent=True,
                worker_generation=worker_generation,
            )
            return sandbox if healthy else None
        except Exception as error:
            logger.warning(
                "chat blank pool health unavailable sandbox_id=%s error=%s",
                sandbox_id,
                type(error).__name__,
            )
            raise PoolHealthUnavailable from error

    async def terminate_pool_row(
        self,
        pool_id: uuid.UUID,
        sandbox_id: str | None,
        *,
        failure_code: str | None,
    ) -> bool:
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            claim = self.repository.claim_termination(
                db,
                pool_id,
                sandbox_id,
                failure_code=failure_code,
                now=now,
                stale_draining_before=now
                - timedelta(seconds=self.policy.termination_claim_timeout_seconds),
            )
        if claim is None:
            return False
        return await self.terminate_claimed_pool_row(claim)

    async def terminate_claimed_pool_row(
        self,
        claim: PoolTerminationClaim,
    ) -> bool:
        confirmed = True
        if claim.sandbox_id:
            self.transport.drop_blank_control(claim.sandbox_id)
            try:
                confirmed = await self.provider.terminate(claim.sandbox_id)
            except Exception:
                confirmed = False
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            outcome = self.repository.finish_termination(
                db,
                claim,
                confirmed=confirmed,
                now=now,
            )
            if (
                outcome is PoolTerminationFinishOutcome.FINISHED
                and claim.sandbox_id
                and self.policy.spend_enforced
                and not claim.accounting_settled
            ):
                self.spend_factory(db).terminate(
                    claim.sandbox_id,
                    claim.failure_code,
                    confirmed=confirmed,
                )
        return outcome is PoolTerminationFinishOutcome.FINISHED

    async def terminate_claimed_pool_rows(
        self,
        claims: list[PoolTerminationClaim],
    ) -> int:
        semaphore = asyncio.Semaphore(self.policy.termination_concurrency)

        async def terminate_one(claim: PoolTerminationClaim) -> bool:
            async with semaphore:
                try:
                    return await self.terminate_claimed_pool_row(claim)
                except Exception as error:
                    logger.warning(
                        "chat blank pool termination failed pool_id=%s error=%s",
                        claim.pool_id,
                        type(error).__name__,
                    )
                    return False

        results = await asyncio.gather(*(terminate_one(claim) for claim in claims))
        return sum(results)

    async def reconcile_pool_orphans(self) -> int:
        """Reconcile bounded provider-only blanks while this slot owns maintenance."""

        if not self.maintenance_owner():
            return 0
        async with self._lock:
            if not self.maintenance_owner():
                return 0
            return await self._reconcile_pool_orphans()

    async def _reconcile_pool_orphans(self) -> int:
        if not self.maintenance_owner():
            return 0
        sandboxes: list[object] = []
        try:
            async for sandbox in self.provider.iter_sandboxes(
                tags={
                    "service": "pwc-chat",
                    "environment": self.settings.environment,
                    "pool": "blank",
                }
            ):
                sandboxes.append(sandbox)
                if len(sandboxes) >= POOL_MAINTENANCE_BATCH_SIZE:
                    break
        except Exception as error:
            logger.warning(
                "chat blank pool provider listing failed error=%s",
                type(error).__name__,
            )
        semaphore = asyncio.Semaphore(self.policy.termination_concurrency)

        async def reconcile_one(sandbox: object) -> bool:
            async with semaphore:
                return await self._reconcile_provider_sandbox(sandbox)

        results = await asyncio.gather(*(reconcile_one(item) for item in sandboxes))
        return sum(results)

    async def _reconcile_provider_sandbox(self, sandbox: object) -> bool:
        if not self.maintenance_owner():
            return False
        sandbox_id = getattr(sandbox, "object_id", None)
        if not isinstance(sandbox_id, str) or not sandbox_id:
            return False
        try:
            tags = await self.provider.get_tags(sandbox)
        except Exception as error:
            logger.warning(
                "chat blank pool tag lookup failed sandbox_id=%s error=%s",
                sandbox_id,
                type(error).__name__,
            )
            return False
        if not self.maintenance_owner() or not isinstance(tags, Mapping):
            return False
        if tags.get("environment") != self.settings.environment:
            return False

        inspection = self._inspect_provider_sandbox(sandbox_id, tags)
        if inspection is None:
            return False
        if inspection.disposition is not ProviderPoolDisposition.ORPHAN:
            return False
        if inspection.termination_claim is None and not self.maintenance_owner():
            return False

        self.transport.drop_blank_control(sandbox_id)
        try:
            confirmed = await self.provider.terminate(sandbox_id, sandbox)
        except Exception:
            confirmed = False
        return self._settle_provider_orphan(
            sandbox_id,
            inspection,
            confirmed=confirmed,
        )

    def _inspect_provider_sandbox(
        self,
        sandbox_id: str,
        tags: Mapping[str, object],
    ) -> ProviderPoolInspection | None:
        now = self.utcnow()
        try:
            with self.session_factory() as db, db.begin():
                if not self.maintenance_locker(db):
                    return None
                if not self.repository.acquire_capacity_lock(db):
                    return None
                inspection = self.repository.classify_and_claim_provider_sandbox(
                    db,
                    sandbox_id,
                    tags,
                    environment=self.settings.environment,
                    fresh_start_after=now
                    - timedelta(seconds=self.policy.ready_timeout_seconds + 15),
                    stale_draining_before=now
                    - timedelta(seconds=self.policy.termination_claim_timeout_seconds),
                    now=now,
                    capacity_locked=True,
                )
                if (
                    inspection.disposition is ProviderPoolDisposition.ORPHAN
                    and inspection.interval_id is not None
                    and self.policy.spend_enforced
                ):
                    self.spend_factory(db).provider_created(
                        inspection.interval_id,
                        sandbox_id,
                        now,
                    )
            return inspection
        except Exception as error:
            logger.warning(
                "chat blank pool orphan inspection failed sandbox_id=%s error=%s",
                sandbox_id,
                type(error).__name__,
            )
            return None

    def _settle_provider_orphan(
        self,
        sandbox_id: str,
        inspection: ProviderPoolInspection,
        *,
        confirmed: bool,
    ) -> bool:
        try:
            with self.session_factory() as db, db.begin():
                if inspection.termination_claim is not None:
                    finish = self.repository.finish_termination(
                        db,
                        inspection.termination_claim,
                        confirmed=confirmed,
                        now=self.utcnow(),
                    )
                    if finish is not PoolTerminationFinishOutcome.FINISHED:
                        return False
                elif (
                    self.policy.spend_enforced
                    and not self.repository.acquire_capacity_lock(db)
                ):
                    return False
                if self.policy.spend_enforced:
                    terminal_reason = (
                        inspection.termination_claim.failure_code
                        if inspection.termination_claim is not None
                        else (
                            "pool_orphan_reconciled"
                            if confirmed
                            else "termination_uncertain"
                        )
                    )
                    self.spend_factory(db).terminate(
                        sandbox_id,
                        terminal_reason,
                        confirmed=confirmed,
                        now=self.utcnow(),
                    )
        except Exception as error:
            logger.warning(
                "chat blank pool orphan settlement failed sandbox_id=%s error=%s",
                sandbox_id,
                type(error).__name__,
            )
            return False
        return confirmed

    async def maintain_pool(self) -> PoolMaintenanceResult:
        """Drain, health-check, reconcile, clean, and refill the blank pool."""

        if not self.maintenance_owner():
            return PoolMaintenanceResult()
        async with self._lock:
            if not self.maintenance_owner():
                return PoolMaintenanceResult()
            return await self._maintain_pool()

    async def _maintain_pool(self) -> PoolMaintenanceResult:
        now = self.utcnow()
        planned = self._plan_maintenance(now)
        if planned is None:
            return PoolMaintenanceResult()
        budget_blocked, plan = planned

        drained = await self.terminate_claimed_pool_rows(list(plan.termination_claims))
        lost = await self._refresh_pool_health(plan.health_candidates)
        cleaned = self._cleanup_terminal_rows(now)
        orphaned = (
            await self._reconcile_pool_orphans() if self.maintenance_owner() else 0
        )
        abandoned = self._abort_abandoned_reservations()
        replenished = 0 if budget_blocked else await self.creation.replenish_count()
        return PoolMaintenanceResult(
            drained=drained,
            lost=lost,
            orphaned=orphaned,
            abandoned=abandoned,
            cleaned=cleaned,
            replenished=replenished,
        )

    def _plan_maintenance(
        self,
        now: datetime,
    ) -> tuple[bool, PoolMaintenancePlan] | None:
        budget_blocked = not self.policy.enabled
        with self.session_factory() as db, db.begin():
            if not self.maintenance_locker(db):
                return None
            if not self.repository.acquire_capacity_lock(db):
                return None
            if self.policy.enabled and self.policy.spend_enforced:
                try:
                    self.spend_factory(db).assert_available(
                        now,
                        capacity_locked=True,
                    )
                except ChatComputeDisabled:
                    budget_blocked = True
            stale_health_claims = self.repository.reclaim_stale_health_checks(
                db,
                cutoff=now - timedelta(seconds=POOL_HEALTH_CLAIM_TIMEOUT_SECONDS),
                now=now,
                limit=self.policy.termination_concurrency,
                capacity_locked=True,
            )
            plan = self.repository.plan_maintenance(
                db,
                now=now,
                enabled=self.policy.enabled,
                budget_blocked=budget_blocked,
                starting_expired_before=now
                - timedelta(seconds=self.policy.ready_timeout_seconds + 15),
                rotation_before=now
                + timedelta(
                    seconds=self.settings.chat_blank_pool_rotate_before_seconds
                ),
                stale_draining_before=now
                - timedelta(seconds=self.policy.termination_claim_timeout_seconds),
                # A reclaimed row is already a complete termination claim and
                # remains visible as draining in this transaction. Defer other
                # drains one cycle so planning cannot rotate its token and
                # issue duplicate provider termination I/O.
                termination_limit=(
                    0 if stale_health_claims else self.policy.termination_concurrency
                ),
                scan_limit=POOL_MAINTENANCE_BATCH_SIZE,
                capacity_locked=True,
            )
        if stale_health_claims:
            logger.warning(
                "chat blank pool stale health claims reclaimed count=%s",
                len(stale_health_claims),
            )
        return budget_blocked, PoolMaintenancePlan(
            termination_claims=stale_health_claims + plan.termination_claims,
            health_candidates=plan.health_candidates,
        )

    def _cleanup_terminal_rows(self, now: datetime) -> int:
        if not self.maintenance_owner():
            return 0
        try:
            with self.session_factory() as db, db.begin():
                if not self.maintenance_locker(db):
                    return 0
                if not self.repository.acquire_capacity_lock(db):
                    return 0
                return self.repository.cleanup_terminal(
                    db,
                    updated_before=now - timedelta(days=POOL_TERMINAL_RETENTION_DAYS),
                    limit=POOL_MAINTENANCE_BATCH_SIZE,
                )
        except Exception as error:
            logger.warning(
                "chat blank pool terminal cleanup failed error=%s",
                type(error).__name__,
            )
            return 0

    def _abort_abandoned_reservations(self) -> int:
        if not self.maintenance_owner() or not self.policy.spend_enforced:
            return 0
        try:
            with self.session_factory() as db, db.begin():
                if not self.maintenance_locker(db):
                    return 0
                if not self.repository.acquire_capacity_lock(db):
                    return 0
                abandoned = self.spend_factory(db).abort_abandoned_pool_reservations(
                    self.utcnow(),
                    limit=POOL_MAINTENANCE_BATCH_SIZE,
                )
        except Exception as error:
            logger.warning(
                "chat blank pool reservation cleanup failed error=%s",
                type(error).__name__,
            )
            return 0
        if abandoned:
            logger.info(
                "chat blank pool abandoned reservations released count=%d",
                abandoned,
            )
        return abandoned

    async def _refresh_pool_health(
        self,
        candidates: tuple[PoolHealthCandidate, ...],
    ) -> int:
        lost = 0
        for candidate in candidates:
            if not self.maintenance_owner():
                break
            claim = self._claim_health_check(candidate)
            if claim is None:
                logger.info(
                    "chat blank pool health claim skipped pool_id=%s reason=ownership_changed",
                    candidate.pool_id,
                )
                continue
            if not self._health_check_owned(claim):
                logger.error(
                    "chat blank pool health invariant violated pool_id=%s sandbox_id=%s",
                    claim.pool_id,
                    claim.sandbox_id,
                )
                continue
            logger.info(
                "chat blank pool provider health attempted pool_id=%s sandbox_id=%s",
                claim.pool_id,
                claim.sandbox_id,
            )
            try:
                sandbox = await self.pool_sandbox_health(
                    claim.sandbox_id,
                    claim.worker_generation,
                )
            except PoolHealthUnavailable:
                logger.warning(
                    "chat blank pool health unavailable pool_id=%s sandbox_id=%s",
                    claim.pool_id,
                    claim.sandbox_id,
                )
                continue
            if not self.maintenance_owner():
                break
            try:
                with self.session_factory() as db, db.begin():
                    finished = self.repository.finish_health_check(
                        db,
                        claim,
                        healthy=sandbox is not None,
                        now=self.utcnow(),
                    )
                if finished.outcome is PoolHealthCheckFinishOutcome.DEAD:
                    assert finished.termination_claim is not None
                    lost += bool(
                        await self.terminate_claimed_pool_row(
                            finished.termination_claim
                        )
                    )
                logger.info(
                    "chat blank pool health completed pool_id=%s outcome=%s",
                    claim.pool_id,
                    finished.outcome,
                )
            except Exception as error:
                logger.warning(
                    "chat blank pool health refresh failed pool_id=%s error=%s",
                    claim.pool_id,
                    type(error).__name__,
                )
        return lost

    def _claim_health_check(
        self,
        candidate: PoolHealthCandidate,
    ) -> PoolHealthCheckClaim | None:
        with self.session_factory() as db, db.begin():
            return self.repository.claim_health_check(
                db,
                candidate,
                now=self.utcnow(),
            )

    def _health_check_owned(self, claim: PoolHealthCheckClaim) -> bool:
        with self.session_factory() as db:
            return self.repository.health_check_owned(db, claim)
