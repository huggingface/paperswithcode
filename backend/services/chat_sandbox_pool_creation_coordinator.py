"""Reservation, provider creation, and durable landing for blank sandboxes."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.chat_executor_runtime import ChatExecutorRuntime

from sqlalchemy.orm import Session

from backend.services.chat_sandbox_lease_eviction_coordinator import (
    ChatSandboxLeaseEvictionCoordinator,
)
from backend.services.chat_sandbox_pool_policy import ChatSandboxPoolPolicy
from backend.services.chat_sandbox_pool_repository import (
    ChatSandboxPoolRepository,
    PoolEvictionRequired,
    PoolLandingDurability,
    PoolLandingOutcome,
    PoolReservationOutcome,
    PoolStartReservation,
    PoolTerminationClaim,
    PoolTerminationFinishOutcome,
)
from backend.services.chat_sandbox_provider import (
    SandboxError,
    SandboxLaunchMode,
    SandboxProvider,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_worker_transport import (
    BlankStartupMetrics,
    ChatSandboxWorkerTransport,
    SessionControl,
)

logger = logging.getLogger("backend.services.chat_sandbox_pool_coordinator")

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
UtcClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]
MaintenanceOwner = Callable[[], bool]
MaintenanceLocker = Callable[[Session], bool]


class PoolReplenishmentOutcome(StrEnum):
    """Typed result of one bounded replenish attempt."""

    READY = "ready"
    SKIPPED = "skipped"
    START_FAILED = "start_failed"
    OWNERSHIP_CHANGED = "ownership_changed"

    @property
    def created_count(self) -> int:
        return int(self is PoolReplenishmentOutcome.READY)


class StartedBlankOwner(StrEnum):
    """Who may dispose of a started provider after a landing attempt.

    The pool and successor states retain the provider. The creator state owns
    compensation because no landing became durable. Unknown ownership drops
    only local control and leaves provider reconciliation to maintenance.
    """

    POOL = "pool"
    SUCCESSOR = "successor"
    CREATOR = "creator"
    UNKNOWN = "unknown"


LandingCause = Exception | asyncio.CancelledError


@dataclass(frozen=True)
class StartedBlank:
    """A ready provider/control pair still governed by a start reservation."""

    reservation: PoolStartReservation
    sandbox: object
    sandbox_id: str
    control: SessionControl | None
    provider_create_ms: int
    backend_control_connect_ms: int
    startup_metrics: BlankStartupMetrics | None


@dataclass(frozen=True)
class LandingResolution:
    """Ownership classification after a landing result or ambiguous commit."""

    owner: StartedBlankOwner
    cause: LandingCause | None = None
    classification_error: Exception | None = None


class ChatSandboxPoolCreationCoordinator:
    """Own a pool reservation until its provider is landed or compensated."""

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
        lease_eviction: ChatSandboxLeaseEvictionCoordinator,
        spend_factory: SpendFactory,
        utcnow: UtcClock,
        monotonic: MonotonicClock,
        executor_runtime: ChatExecutorRuntime | None = None,
    ):
        self.executor_runtime = executor_runtime
        self.policy = policy
        self.settings = policy.settings
        self.session_factory = session_factory
        self.repository = repository
        self.provider = provider
        self.transport = transport
        self.maintenance_owner = maintenance_owner
        self.maintenance_locker = maintenance_locker
        self.lease_eviction = lease_eviction
        self.spend_factory = spend_factory
        self.utcnow = utcnow
        self.monotonic = monotonic
        self._semaphore = asyncio.Semaphore(
            self.settings.chat_blank_pool_refill_concurrency
        )
        self._tasks: set[asyncio.Task[PoolReplenishmentOutcome]] = set()

    def spawn_replenishment(self) -> None:
        if (
            not self.policy.refill_enabled
            or not self.maintenance_owner()
            or len(self._tasks) >= self.settings.chat_blank_pool_refill_concurrency
        ):
            return
        task = asyncio.create_task(self.replenish())
        self._tasks.add(task)

        def finished(completed: asyncio.Task[PoolReplenishmentOutcome]) -> None:
            self._tasks.discard(completed)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                logger.warning(
                    "chat blank pool replenishment failed error=%s",
                    type(error).__name__,
                )

        task.add_done_callback(finished)

    async def replenish_count(self) -> int:
        return (await self.replenish()).created_count

    async def replenish(self) -> PoolReplenishmentOutcome:
        """Reserve and initialize at most one blank worker per invocation."""

        if not self.policy.refill_enabled or not self.maintenance_owner():
            return PoolReplenishmentOutcome.SKIPPED
        async with self._semaphore:
            if not self.policy.refill_enabled or not self.maintenance_owner():
                return PoolReplenishmentOutcome.SKIPPED
            refill_started = self.monotonic()
            reservation = await self._reserve_with_one_eviction()
            if reservation is None:
                return PoolReplenishmentOutcome.SKIPPED
            started = await self._prepare_reserved_blank(reservation)
            if started is None:
                return PoolReplenishmentOutcome.START_FAILED
            resolution = await self._resolve_landing(started)
            outcome = await self._settle_landing(started, resolution)
            if outcome is PoolReplenishmentOutcome.READY:
                logger.info(
                    "chat blank pool refill ready pool_id=%s "
                    "sandbox_id=%s refill_ms=%d",
                    reservation.pool_id,
                    started.sandbox_id,
                    round((self.monotonic() - refill_started) * 1000),
                )
            return outcome

    async def _reserve_with_one_eviction(self) -> PoolStartReservation | None:
        outcome = self._reserve_once()
        if isinstance(outcome, PoolStartReservation):
            return outcome
        if not isinstance(outcome, PoolEvictionRequired):
            return None

        eviction = await self.lease_eviction.evict_idle(outcome.chat_session_id)
        if not eviction.acquired:
            return None
        if not self.policy.refill_enabled or not self.maintenance_owner():
            return None

        retried = self._reserve_once()
        return retried if isinstance(retried, PoolStartReservation) else None

    def _reserve_once(self) -> PoolReservationOutcome | None:
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            if not self.maintenance_locker(db):
                return None
            interval_reserver = None
            if self.policy.spend_enforced:
                spend = self.spend_factory(db)

                def interval_reserver(
                    worker_generation: str,
                    *,
                    spend_service: ChatSandboxSpendService = spend,
                    reserved_at: datetime = now,
                ) -> uuid.UUID:
                    return spend_service.reserve_interval(
                        origin="blank_pool",
                        worker_generation=worker_generation,
                        now=reserved_at,
                        capacity_locked=True,
                    )

            try:
                return self.repository.reserve_starting_blank(
                    db,
                    now=now,
                    interval_reserver=interval_reserver,
                )
            except ChatComputeDisabled:
                return None

    async def _prepare_reserved_blank(
        self,
        reservation: PoolStartReservation,
    ) -> StartedBlank | None:
        sandbox: object | None = None
        control: SessionControl | None = None
        try:
            provider_started = self.monotonic()
            launch_args = {}
            if self.executor_runtime is not None:
                launch_args = {
                    "launch_mode": SandboxLaunchMode.EXECUTOR,
                    "executor_launch": await self.executor_runtime.prepare_launch(
                        reservation.worker_generation,
                        blank_pool=True,
                    ),
                }
            sandbox = await self.provider.create(
                **launch_args,
                name=f"chat-blank-{reservation.pool_id}",
                tags=self._provider_tags(reservation),
                worker_generation=reservation.worker_generation,
            )
            provider_create_ms = round((self.monotonic() - provider_started) * 1000)
            sandbox_id: str = sandbox.object_id
            control_started = self.monotonic()
            if self.executor_runtime is not None:
                await self.executor_runtime.wait_for_pool_ready(
                    reservation.worker_generation
                )
                return StartedBlank(
                    reservation=reservation,
                    sandbox=sandbox,
                    sandbox_id=sandbox_id,
                    control=None,
                    provider_create_ms=provider_create_ms,
                    backend_control_connect_ms=round(
                        (self.monotonic() - control_started) * 1000
                    ),
                    startup_metrics=None,
                )
            control = await self.transport.open_persistent_control(
                sandbox,
                reservation.worker_generation,
            )
            backend_control_connect_ms = round(
                (self.monotonic() - control_started) * 1000
            )
            if not await self.transport.ping(control, reservation.worker_generation):
                raise SandboxError(
                    "sandbox_worker_not_ready",
                    "Persistent blank worker health check failed",
                )
            startup_metrics = self.transport.blank_startup_metrics(sandbox_id)
            if self.settings.chat_pi_prewarm_enabled and (
                startup_metrics is None or not startup_metrics.agent_prestarted
            ):
                raise SandboxError(
                    "sandbox_worker_not_ready",
                    "Persistent blank Pi worker was not prestarted",
                )
            self.transport.register_blank_control(
                sandbox_id,
                control,
                checked_at=self.monotonic(),
            )
            return StartedBlank(
                reservation=reservation,
                sandbox=sandbox,
                sandbox_id=sandbox_id,
                control=control,
                provider_create_ms=provider_create_ms,
                backend_control_connect_ms=backend_control_connect_ms,
                startup_metrics=startup_metrics,
            )
        except asyncio.CancelledError:
            try:
                await self._complete_cleanup(
                    self._compensate_start(
                        reservation,
                        sandbox=sandbox,
                        control=control,
                        failure_code="sandbox_start_failed",
                    )
                )
            except Exception as error:
                logger.warning(
                    "cancelled blank pool start cleanup failed error=%s",
                    type(error).__name__,
                )
            raise
        except Exception:
            await self._complete_cleanup(
                self._compensate_start(
                    reservation,
                    sandbox=sandbox,
                    control=control,
                    failure_code="sandbox_start_failed",
                )
            )
            return None

    def _provider_tags(self, reservation: PoolStartReservation) -> dict[str, str]:
        return {
            "service": "pwc-chat",
            "environment": getattr(self.settings, "environment", "staging"),
            "pool": "blank",
            "pool_id": str(reservation.pool_id),
            "release": self.settings.release_id,
            "image": self.settings.chat_modal_image_version,
            "contract": self.settings.chat_worker_contract_version,
            "egress": reservation.compatibility.egress_policy_digest,
        }

    async def _resolve_landing(self, started: StartedBlank) -> LandingResolution:
        try:
            landing = self._commit_landing(started)
            # Deliver cancellation requested during the synchronous landing commit.
            await asyncio.sleep(0)
        except asyncio.CancelledError as cancellation:
            return self._classify_ambiguous_landing(started, cancellation)
        except Exception as landing_error:
            return self._classify_ambiguous_landing(started, landing_error)

        owner = (
            StartedBlankOwner.POOL
            if landing is PoolLandingOutcome.LANDED
            else StartedBlankOwner.CREATOR
        )
        return LandingResolution(owner)

    def _commit_landing(self, started: StartedBlank) -> PoolLandingOutcome:
        with self.session_factory() as db, db.begin():
            landing = self.repository.land_provider_creation(
                db,
                started.reservation,
                started.sandbox_id,
                now=self.utcnow(),
                provider_create_ms=started.provider_create_ms,
                backend_control_connect_ms=started.backend_control_connect_ms,
                broker_ready_ms=(
                    started.startup_metrics.broker_ready_ms
                    if started.startup_metrics is not None
                    else None
                ),
                control_ready_ms=(
                    started.startup_metrics.control_ready_ms
                    if started.startup_metrics is not None
                    else None
                ),
                agent_spawn_ms=(
                    started.startup_metrics.agent_spawn_ms
                    if started.startup_metrics is not None
                    else None
                ),
                agent_startup_ready_ms=(
                    started.startup_metrics.agent_startup_ready_ms
                    if started.startup_metrics is not None
                    else None
                ),
            )
            if (
                landing is PoolLandingOutcome.LANDED
                and started.reservation.interval_id is not None
            ):
                self.spend_factory(db).provider_created(
                    started.reservation.interval_id,
                    started.sandbox_id,
                    self.utcnow(),
                )
        return landing

    def _classify_ambiguous_landing(
        self,
        started: StartedBlank,
        cause: LandingCause,
    ) -> LandingResolution:
        try:
            durability = self._landing_durability(
                started.reservation,
                started.sandbox_id,
            )
        except Exception as classification_error:
            return LandingResolution(
                StartedBlankOwner.UNKNOWN,
                cause,
                classification_error,
            )
        owner = {
            PoolLandingDurability.BLANK_READY: StartedBlankOwner.POOL,
            PoolLandingDurability.OWNERSHIP_MOVED: StartedBlankOwner.SUCCESSOR,
            PoolLandingDurability.NOT_DURABLE: StartedBlankOwner.CREATOR,
        }[durability]
        return LandingResolution(owner, cause)

    async def _settle_landing(
        self,
        started: StartedBlank,
        resolution: LandingResolution,
    ) -> PoolReplenishmentOutcome:
        cause = resolution.cause
        if resolution.owner is StartedBlankOwner.POOL:
            if isinstance(cause, asyncio.CancelledError):
                raise cause
            return PoolReplenishmentOutcome.READY

        if resolution.owner is StartedBlankOwner.SUCCESSOR:
            self._drop_registered_start_control(started)
            if isinstance(cause, asyncio.CancelledError):
                raise cause
            return PoolReplenishmentOutcome.OWNERSHIP_CHANGED

        if resolution.owner is StartedBlankOwner.UNKNOWN:
            self._drop_registered_start_control(started)
            assert cause is not None
            if isinstance(cause, asyncio.CancelledError):
                assert resolution.classification_error is not None
                logger.warning(
                    "cancelled blank landing durability check failed error=%s",
                    type(resolution.classification_error).__name__,
                )
            raise cause

        if cause is None:
            await self._complete_cleanup(self._settle_ownership_changed(started))
            return PoolReplenishmentOutcome.OWNERSHIP_CHANGED

        try:
            await self._complete_cleanup(
                self._compensate_start(
                    started.reservation,
                    sandbox=started.sandbox,
                    control=started.control,
                    failure_code="sandbox_start_failed",
                )
            )
        except Exception as cleanup_error:
            message = (
                "cancelled blank landing cleanup failed error=%s"
                if isinstance(cause, asyncio.CancelledError)
                else "blank landing cleanup failed error=%s"
            )
            logger.warning(message, type(cleanup_error).__name__)
        raise cause

    def _landing_durability(
        self,
        reservation: PoolStartReservation,
        sandbox_id: str,
    ) -> PoolLandingDurability:
        with self.session_factory() as db:
            return self.repository.provider_landing_durability(
                db,
                reservation,
                sandbox_id,
            )

    async def _complete_cleanup(self, cleanup: Awaitable[None]) -> None:
        task = asyncio.create_task(cleanup)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise

    async def _compensate_start(
        self,
        reservation: PoolStartReservation,
        *,
        sandbox: object | None,
        control: SessionControl | None,
        failure_code: str,
    ) -> None:
        sandbox_id = getattr(sandbox, "object_id", None)
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            claim = self.repository.claim_start_termination(
                db,
                reservation,
                None,
                failure_code=failure_code,
                now=now,
            )
        self._close_failed_start_control(sandbox_id, control)
        confirmed = True
        if sandbox_id is not None:
            try:
                confirmed = await self.provider.terminate(sandbox_id, sandbox)
            except Exception:
                confirmed = False
        self._finish_failed_start(
            reservation,
            claim=claim,
            sandbox_id=sandbox_id,
            failure_code=failure_code,
            confirmed=confirmed,
        )

    async def _settle_ownership_changed(self, started: StartedBlank) -> None:
        self._close_failed_start_control(started.sandbox_id, started.control)
        try:
            confirmed = await self.provider.terminate(
                started.sandbox_id,
                started.sandbox,
            )
        except Exception:
            confirmed = False
        self._finish_failed_start(
            started.reservation,
            claim=None,
            sandbox_id=started.sandbox_id,
            failure_code="ownership_changed",
            confirmed=confirmed,
        )

    def _finish_failed_start(
        self,
        reservation: PoolStartReservation,
        *,
        claim: PoolTerminationClaim | None,
        sandbox_id: str | None,
        failure_code: str,
        confirmed: bool,
    ) -> None:
        if claim is None and reservation.interval_id is None:
            return
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            if claim is not None:
                finish = self.repository.finish_termination(
                    db,
                    claim,
                    confirmed=confirmed,
                    now=now,
                )
                if finish is not PoolTerminationFinishOutcome.FINISHED:
                    return
            if reservation.interval_id is None:
                return
            spend = self.spend_factory(db)
            if sandbox_id is None:
                spend.abort_reservation(
                    reservation.interval_id,
                    failure_code,
                    now,
                )
            else:
                spend.provider_created(reservation.interval_id, sandbox_id, now)
                spend.terminate(
                    sandbox_id,
                    failure_code,
                    confirmed=confirmed,
                    now=now,
                )

    def _close_failed_start_control(
        self,
        sandbox_id: str | None,
        control: SessionControl | None,
    ) -> None:
        if control is None:
            return
        if (
            sandbox_id is not None
            and self.transport.drop_blank_control(
                sandbox_id,
                expected=control,
            )
            is not None
        ):
            return
        self.transport.schedule_close(control)

    def _drop_registered_start_control(self, started: StartedBlank) -> None:
        if started.control is None:
            return
        self.transport.drop_blank_control(
            started.sandbox_id,
            expected=started.control,
        )
