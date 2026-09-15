"""Typed sandbox acquisition, recovery, and provider-start orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatTurnLatency
from backend.chat_sandbox_worker.mcp_app_registry import egress_policy_digest
from backend.services.chat_sandbox_capacity_repository import (
    CapacityUnavailable,
    ChatSandboxCapacityRepository,
    EvictionRequired,
    LeaseDecisionChanged,
    RecoveryRequired,
    ReuseLease,
    StartAcquired,
    WaitForLease,
)
from backend.services.chat_sandbox_lease_maintenance_coordinator import (
    ChatSandboxLeaseMaintenanceCoordinator,
)
from backend.services.chat_sandbox_pool_coordinator import ChatSandboxPoolCoordinator
from backend.services.chat_sandbox_provider import (
    ExecutorLaunchBundle,
    SandboxError,
    SandboxLaunchMode,
    SandboxProvider,
)
from backend.services.chat_sandbox_spend_access import (
    assert_chat_sandbox_spend_available,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    StartClaim,
)
from backend.services.chat_sandbox_worker_transport import ChatSandboxWorkerTransport

type AcquisitionLabel = Literal[
    "pool_hit",
    "pool_miss",
    "reused_session",
    "created",
]
type ExecutorLaunchFactory = Callable[[str], Awaitable[ExecutorLaunchBundle]]
type LegacyEnsureReadyResult = tuple[
    object,
    int,
    bool,
    AcquisitionLabel,
    int | None,
]
SessionFactory = Callable[[], Session]
LiveCapResolver = Callable[[Session], int]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
UtcClock = Callable[[], datetime]
FloatClock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]
TokenFactory = Callable[[], str]


class SnapshotRestorer(Protocol):
    async def restore(self, sandbox: object, snapshot_id: str) -> None: ...


@dataclass(frozen=True)
class PoolAcquired:
    sandbox: object
    elapsed_ms: int
    pool_lookup_ms: int

    @property
    def public_label(self) -> Literal["pool_hit"]:
        return "pool_hit"

    @property
    def created(self) -> Literal[False]:
        return False


@dataclass(frozen=True)
class LeaseReused:
    sandbox: object
    elapsed_ms: int
    pool_lookup_ms: int | None
    reuse_cohort: str = "rediscovered"

    @property
    def public_label(self) -> Literal["reused_session"]:
        return "reused_session"

    @property
    def created(self) -> Literal[False]:
        return False


@dataclass(frozen=True)
class SandboxCreated:
    sandbox: object
    elapsed_ms: int
    after_pool_miss: bool
    pool_lookup_ms: int | None
    pool_miss_reason: str | None = None
    reuse_cohort: str | None = None

    @property
    def public_label(self) -> Literal["pool_miss", "created"]:
        return "pool_miss" if self.after_pool_miss else "created"

    @property
    def created(self) -> Literal[True]:
        return True


type SandboxAcquisitionOutcome = PoolAcquired | LeaseReused | SandboxCreated


@dataclass(frozen=True)
class StartSelected:
    acquired: StartAcquired
    reuse_cohort: str | None = None


def legacy_ensure_ready_result(
    outcome: SandboxAcquisitionOutcome,
) -> LegacyEnsureReadyResult:
    """Preserve the manager's positional result while callers migrate."""

    return (
        outcome.sandbox,
        outcome.elapsed_ms,
        outcome.created,
        outcome.public_label,
        outcome.pool_lookup_ms,
    )


class ChatSandboxAcquisitionCoordinator:
    """Acquire or create one sandbox without holding transactions over I/O."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        state_repository: ChatSandboxStateRepository,
        capacity_repository: ChatSandboxCapacityRepository,
        pool: ChatSandboxPoolCoordinator,
        provider: SandboxProvider,
        transport: ChatSandboxWorkerTransport,
        snapshots: SnapshotRestorer,
        lease_maintenance: ChatSandboxLeaseMaintenanceCoordinator,
        spend_factory: SpendFactory | None = None,
        utcnow: UtcClock | None = None,
        monotonic: FloatClock = time.monotonic,
        perf_counter: FloatClock = time.perf_counter,
        sleeper: Sleeper = asyncio.sleep,
        creation_token_factory: TokenFactory | None = None,
        generation_factory: TokenFactory | None = None,
        executor_launch_factory: ExecutorLaunchFactory | None = None,
    ) -> None:
        eviction = pool.lease_eviction
        lifecycle = lease_maintenance.lifecycle
        if state_repository.settings is not settings:
            raise ValueError("Acquisition state settings must be shared")
        if capacity_repository.settings is not settings:
            raise ValueError("Acquisition capacity settings must be shared")
        if capacity_repository.state_repository is not state_repository:
            raise ValueError("Acquisition state repositories must be shared")
        if pool.settings is not settings or lease_maintenance.settings is not settings:
            raise ValueError("Acquisition component settings must be shared")
        if pool.repository.settings is not settings:
            raise ValueError("Acquisition pool repository settings must be shared")
        if eviction.settings is not settings or lifecycle.settings is not settings:
            raise ValueError("Acquisition lifecycle settings must be shared")
        if pool.session_factory is not session_factory:
            raise ValueError("Acquisition and pool sessions must be shared")
        if lease_maintenance.session_factory is not session_factory:
            raise ValueError("Acquisition and maintenance sessions must be shared")
        if eviction.session_factory is not session_factory:
            raise ValueError("Acquisition and eviction sessions must be shared")
        if lifecycle.session_factory is not session_factory:
            raise ValueError("Acquisition and lifecycle sessions must be shared")
        if transport.provider is not provider:
            raise ValueError("Acquisition provider and transport must be shared")
        if pool.provider is not provider or pool.transport is not transport:
            raise ValueError("Acquisition and pool transports must be shared")
        if eviction.provider is not provider or eviction.transport is not transport:
            raise ValueError("Acquisition and eviction transports must be shared")
        if lifecycle.provider is not provider or lifecycle.transport is not transport:
            raise ValueError("Acquisition and lifecycle transports must be shared")
        if lease_maintenance.provider is not provider:
            raise ValueError("Acquisition and maintenance providers must be shared")
        if eviction.repository is not state_repository:
            raise ValueError("Acquisition and eviction repositories must be shared")
        if lifecycle.repository is not state_repository:
            raise ValueError("Acquisition and lifecycle repositories must be shared")
        if lease_maintenance.repository is not state_repository:
            raise ValueError("Acquisition and maintenance repositories must be shared")
        if lifecycle.idle_eviction is not eviction:
            raise ValueError("Acquisition eviction ownership must be shared")
        if eviction.snapshots is not snapshots:
            raise ValueError("Acquisition and eviction snapshots must be shared")
        if lifecycle.snapshots is not snapshots:
            raise ValueError("Acquisition and lifecycle snapshots must be shared")
        if lease_maintenance.snapshots is not snapshots:
            raise ValueError("Acquisition and maintenance snapshots must be shared")
        locker = capacity_repository.capacity_locker
        if pool.repository.capacity_locker is not locker:
            raise ValueError("Acquisition and pool capacity locks must be shared")
        if eviction.capacity_locker is not locker:
            raise ValueError("Acquisition and eviction capacity locks must be shared")
        if lifecycle.capacity_locker is not locker:
            raise ValueError("Acquisition and lifecycle capacity locks must be shared")
        if lease_maintenance.capacity_locker is not locker:
            raise ValueError(
                "Acquisition and maintenance capacity locks must be shared"
            )

        self.settings = settings
        self.session_factory = session_factory
        self.state_repository = state_repository
        self.capacity_repository = capacity_repository
        self.pool = pool
        self.provider = provider
        self.transport = transport
        self.snapshots = snapshots
        self.lease_maintenance = lease_maintenance
        self.spend_factory = spend_factory or (
            lambda db: ChatSandboxSpendService(db, settings)
        )
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self.perf_counter = perf_counter
        self.sleeper = sleeper
        self.creation_token_factory = creation_token_factory or (
            lambda: secrets.token_urlsafe(24)
        )
        self.generation_factory = generation_factory or (lambda: secrets.token_hex(16))
        self.executor_launch_factory = executor_launch_factory

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
    def blank_pool_enabled(self) -> bool:
        return bool(
            getattr(self.settings, "chat_blank_pool_enabled", False)
            and getattr(self.settings, "chat_sandbox_admission_enabled", True)
        )

    @property
    def spend_enforced(self) -> bool:
        return bool(
            getattr(
                self.settings,
                "chat_sandbox_spend_enforcement_enabled",
                False,
            )
        )

    async def acquire(
        self,
        chat_session_id: uuid.UUID,
        *,
        launch_mode: SandboxLaunchMode = SandboxLaunchMode.LEGACY,
        allow_pool: bool = False,
        pool_miss: bool = False,
        pool_lookup_ms: int | None = None,
        budget_prechecked: bool = False,
        pool_miss_reason: str | None = None,
        live_cap_resolver: LiveCapResolver | None = None,
    ) -> SandboxAcquisitionOutcome:
        started = self.perf_counter()
        if not budget_prechecked and self.spend_enforced:
            try:
                assert_chat_sandbox_spend_available(
                    self.settings,
                    session_factory=self.session_factory,
                    spend_factory=self.spend_factory,
                )
            except ChatComputeDisabled as error:
                raise SandboxError(error.code, str(error)) from error

        if allow_pool and (
            (launch_mode is SandboxLaunchMode.EXECUTOR)
            == self.settings.chat_executor_remote_transport_enabled
        ):
            lookup_started = self.perf_counter()
            claimed = await self.pool.claim_blank(chat_session_id)
            pool_lookup_ms = round((self.perf_counter() - lookup_started) * 1000)
            if claimed is not None:
                sandbox, _claim_ms = claimed
                return PoolAcquired(
                    sandbox=sandbox,
                    elapsed_ms=self._elapsed_ms(started),
                    pool_lookup_ms=pool_lookup_ms,
                )
            pool_miss = True
            pool_miss_reason = "empty_pool"

        deadline = self.monotonic() + self.ready_timeout_seconds
        selected = await self._claim_start_or_reuse(
            chat_session_id,
            deadline=deadline,
            started=started,
            pool_lookup_ms=pool_lookup_ms,
            live_cap_resolver=live_cap_resolver,
            launch_mode=launch_mode,
        )
        if isinstance(selected, LeaseReused):
            return selected
        return await self._create_and_land(
            chat_session_id,
            selected.acquired,
            started=started,
            after_pool_miss=pool_miss,
            pool_lookup_ms=pool_lookup_ms,
            pool_miss_reason=pool_miss_reason,
            reuse_cohort=selected.reuse_cohort,
            launch_mode=launch_mode,
        )

    async def _claim_start_or_reuse(
        self,
        chat_session_id: uuid.UUID,
        *,
        deadline: float,
        started: float,
        pool_lookup_ms: int | None,
        live_cap_resolver: LiveCapResolver | None,
        launch_mode: SandboxLaunchMode,
    ) -> StartSelected | LeaseReused:
        restarted = False
        while True:
            try:
                acquisition = self._acquire_once(
                    chat_session_id, live_cap_resolver=live_cap_resolver
                )
            except LeaseDecisionChanged:
                continue

            if isinstance(acquisition, ReuseLease):
                sandbox, cohort = await self._reuse_or_recover(
                    chat_session_id,
                    acquisition,
                    deadline=deadline,
                    launch_mode=launch_mode,
                )
                if sandbox is None:
                    restarted = restarted or cohort == "restarted"
                    continue
                return LeaseReused(
                    sandbox=sandbox,
                    elapsed_ms=self._elapsed_ms(started),
                    pool_lookup_ms=pool_lookup_ms,
                    reuse_cohort=cohort or "rediscovered",
                )
            if isinstance(acquisition, StartAcquired):
                return StartSelected(
                    acquisition,
                    reuse_cohort="restarted" if restarted else None,
                )
            if isinstance(acquisition, EvictionRequired):
                eviction = await self.pool.lease_eviction.evict_idle(
                    acquisition.chat_session_id
                )
                if eviction.acquired:
                    continue
                if self.monotonic() >= deadline:
                    self._raise_capacity()
                await self.sleeper(0.05)
                continue
            if isinstance(acquisition, WaitForLease):
                if self.monotonic() >= deadline:
                    if acquisition.state == "terminating":
                        self._raise_capacity()
                    raise SandboxError(
                        "sandbox_timeout",
                        "Secure workspace startup timed out",
                    )
                await self.sleeper(0.05)
                continue
            if isinstance(acquisition, RecoveryRequired):
                if await self._recover_claim(chat_session_id, acquisition):
                    continue
                await self._wait_until(deadline)
                self._raise_capacity()
            if isinstance(acquisition, CapacityUnavailable):
                self._raise_capacity()
            raise AssertionError("Unhandled sandbox acquisition outcome")

    def _acquire_once(
        self,
        chat_session_id: uuid.UUID,
        *,
        live_cap_resolver: LiveCapResolver | None = None,
    ):
        creation_token = self.creation_token_factory()
        worker_generation = self.generation_factory()
        now = self.utcnow()
        acquisition = None
        budget_rejection: ChatComputeDisabled | None = None
        with self.session_factory() as db, db.begin():
            reserve_interval: Callable[[str], uuid.UUID] | None = None
            if self.spend_enforced:
                spend = self.spend_factory(db)

                def reserve_direct_interval(generation: str) -> uuid.UUID:
                    return spend.reserve_interval(
                        origin="direct",
                        worker_generation=generation,
                        chat_session_id=chat_session_id,
                        now=now,
                        capacity_locked=True,
                    )

                reserve_interval = reserve_direct_interval

            try:
                acquisition = self.capacity_repository.acquire(
                    db,
                    chat_session_id,
                    creation_token=creation_token,
                    worker_generation=worker_generation,
                    now=now,
                    ready_timeout_seconds=self.ready_timeout_seconds,
                    reserve_interval=reserve_interval,
                    total_live_cap=(
                        live_cap_resolver(db) if live_cap_resolver is not None else None
                    ),
                )
            except ChatComputeDisabled as error:
                # Exiting the transaction normally preserves the durable trip.
                budget_rejection = error
        if budget_rejection is not None:
            raise SandboxError(
                budget_rejection.code,
                str(budget_rejection),
            ) from budget_rejection
        assert acquisition is not None
        return acquisition

    async def _reuse_or_recover(
        self,
        chat_session_id: uuid.UUID,
        acquisition: ReuseLease,
        *,
        deadline: float,
        launch_mode: SandboxLaunchMode,
    ) -> tuple[object | None, str | None]:
        await self.lease_maintenance.enforce_warm_cap()
        persistent = bool(
            getattr(self.settings, "chat_persistent_worker_enabled", False)
        )
        control = self.transport.session_control(chat_session_id)
        if (
            persistent
            and control is not None
            and control.sandbox_id == acquisition.sandbox_id
        ):
            return control.sandbox, "fully_in_memory"

        sandbox = None
        try:
            sandbox = await self.provider.resolve(acquisition.sandbox_id)
            if await self.provider.poll(sandbox) is None and await self.provider.health(
                sandbox,
                persistent=persistent,
                worker_generation=acquisition.worker_generation,
                launch_mode=launch_mode,
            ):
                return sandbox, (
                    "control_reconnected" if persistent else "rediscovered"
                )
        except Exception:  # noqa: BLE001,S110 - exact recovery follows below
            pass

        try:
            with self.session_factory() as db, db.begin():
                recovery = self.capacity_repository.claim_reuse_recovery(
                    db,
                    chat_session_id,
                    acquisition,
                    now=self.utcnow(),
                    ready_timeout_seconds=self.ready_timeout_seconds,
                )
        except LeaseDecisionChanged:
            return None, None
        if await self._recover_claim(chat_session_id, recovery, sandbox=sandbox):
            return None, "restarted"
        await self._wait_until(deadline)
        self._raise_capacity()

    async def _recover_claim(
        self,
        chat_session_id: uuid.UUID,
        recovery: RecoveryRequired,
        *,
        sandbox: object | None = None,
    ) -> bool:
        claim = recovery.claim
        if claim.sandbox_id is None:  # pragma: no cover - recovery requires an ID
            raise LeaseDecisionChanged
        self.transport.drop_session_control(chat_session_id)
        confirmed = await self.provider.terminate(claim.sandbox_id, sandbox)
        if self.spend_enforced:
            with self.session_factory() as db, db.begin():
                self.spend_factory(db).terminate(
                    claim.sandbox_id,
                    claim.failure_code,
                    confirmed=confirmed,
                )
        if not confirmed:
            return False
        with self.session_factory() as db, db.begin():
            self.capacity_repository.finish_recovery(
                db,
                chat_session_id,
                claim=claim,
                now=self.utcnow(),
            )
        return True

    async def _create_and_land(
        self,
        chat_session_id: uuid.UUID,
        acquired: StartAcquired,
        *,
        started: float,
        after_pool_miss: bool,
        pool_lookup_ms: int | None,
        pool_miss_reason: str | None,
        reuse_cohort: str | None,
        launch_mode: SandboxLaunchMode,
    ) -> SandboxCreated:
        claim = acquired.claim
        interval_id = acquired.interval_id
        try:
            await self.lease_maintenance.enforce_warm_cap()
        except (asyncio.CancelledError, Exception):
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=None,
                failure_code="sandbox_start_failed",
            )
            raise

        sandbox = None
        try:
            qualification_profile = None
            if self.settings.environment == "staging":
                with self.session_factory() as evidence_db:
                    qualification_profile = evidence_db.scalar(
                        select(ChatTurnLatency.qualification_profile)
                        .where(
                            ChatTurnLatency.chat_session_id == chat_session_id,
                            ChatTurnLatency.terminal_status == "running",
                        )
                        .order_by(ChatTurnLatency.admitted_at.desc())
                        .limit(1)
                    )
            async with asyncio.timeout(self.ready_timeout_seconds):
                executor_launch = (
                    await self.executor_launch_factory(claim.worker_generation)
                    if launch_mode is SandboxLaunchMode.EXECUTOR
                    and self.executor_launch_factory is not None
                    else None
                )
                if (
                    launch_mode is SandboxLaunchMode.EXECUTOR
                    and self.settings.chat_executor_remote_transport_enabled
                    and executor_launch is None
                ):
                    raise SandboxError(
                        "sandbox_executor_admission_missing",
                        "Sandbox executor admission is unavailable",
                    )
                sandbox = await self.provider.create(
                    name=f"chat-{chat_session_id}",
                    tags={
                        "service": "pwc-chat",
                        "environment": getattr(
                            self.settings,
                            "environment",
                            "staging",
                        ),
                        "chat_session_hash": hashlib.sha256(
                            str(chat_session_id).encode()
                        ).hexdigest()[:16],
                        "release": self.settings.release_id,
                        "image": self.settings.chat_modal_image_version,
                        "egress": egress_policy_digest(self.settings),
                        **(
                            {"qualification_profile": qualification_profile}
                            if qualification_profile == "32-functional-turns"
                            else {}
                        ),
                    },
                    worker_generation=claim.worker_generation,
                    launch_mode=launch_mode,
                    executor_launch=executor_launch,
                )
                if claim.snapshot_id and launch_mode is SandboxLaunchMode.LEGACY:
                    try:
                        await self.snapshots.restore(sandbox, claim.snapshot_id)
                    except Exception:  # noqa: BLE001 - snapshot loss is recoverable
                        with self.session_factory() as db, db.begin():
                            lease = self.state_repository.load_lease(
                                db,
                                chat_session_id,
                                lock=True,
                            )
                            self.state_repository.clear_start_snapshot(
                                lease,
                                claim=claim,
                            )
        except asyncio.CancelledError:
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=sandbox,
                failure_code="sandbox_start_failed",
            )
            raise
        except TimeoutError as error:
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=sandbox,
                failure_code="sandbox_timeout",
            )
            raise SandboxError(
                "sandbox_timeout",
                "Secure workspace startup timed out",
            ) from error
        except Exception as error:
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=sandbox,
                failure_code="sandbox_start_failed",
            )
            raise SandboxError(
                "sandbox_start_failed",
                "Secure workspace startup failed",
            ) from error

        sandbox_id = sandbox.object_id
        landed = False
        try:
            with self.session_factory() as db, db.begin():
                lease = self.state_repository.load_lease(
                    db,
                    chat_session_id,
                    lock=True,
                )
                landed = self.state_repository.land_start(
                    lease,
                    claim=claim,
                    sandbox_id=sandbox_id,
                    now=self.utcnow(),
                )
                if landed and interval_id is not None:
                    self.spend_factory(db).provider_created(
                        interval_id,
                        sandbox_id,
                    )
        except Exception:
            await self._cleanup_failed_start(
                chat_session_id,
                claim,
                interval_id=interval_id,
                sandbox=sandbox,
                failure_code="sandbox_start_failed",
            )
            raise
        if not landed:
            confirmed = await self.provider.terminate(sandbox_id, sandbox)
            if interval_id is not None:
                with self.session_factory() as db, db.begin():
                    spend = self.spend_factory(db)
                    spend.provider_created(interval_id, sandbox_id)
                    spend.terminate(
                        sandbox_id,
                        "ownership_changed",
                        confirmed=confirmed,
                    )
            raise SandboxError(
                "sandbox_start_failed",
                "Secure workspace ownership changed",
            )
        return SandboxCreated(
            sandbox=sandbox,
            elapsed_ms=self._elapsed_ms(started),
            after_pool_miss=after_pool_miss,
            pool_lookup_ms=pool_lookup_ms,
            pool_miss_reason=pool_miss_reason,
            reuse_cohort=reuse_cohort,
        )

    async def _cleanup_failed_start(
        self,
        chat_session_id: uuid.UUID,
        claim: StartClaim,
        *,
        interval_id: uuid.UUID | None,
        sandbox: object | None,
        failure_code: str,
    ) -> None:
        self._fail_start_claim(chat_session_id, claim, failure_code)
        if sandbox is None:
            if interval_id is not None:
                with self.session_factory() as db, db.begin():
                    self.spend_factory(db).abort_reservation(
                        interval_id,
                        failure_code,
                    )
            return

        sandbox_id = sandbox.object_id
        confirmed = await self.provider.terminate(sandbox_id, sandbox)
        if interval_id is not None:
            with self.session_factory() as db, db.begin():
                spend = self.spend_factory(db)
                spend.provider_created(interval_id, sandbox_id)
                spend.terminate(
                    sandbox_id,
                    failure_code,
                    confirmed=confirmed,
                )

    def _fail_start_claim(
        self,
        chat_session_id: uuid.UUID,
        claim: StartClaim,
        failure_code: str,
    ) -> bool:
        with self.session_factory() as db, db.begin():
            if self.blank_pool_enabled:
                self.capacity_repository.acquire_capacity_lock(db)
            lease = self.state_repository.load_lease(
                db,
                chat_session_id,
                lock=True,
            )
            return self.state_repository.fail_start(
                lease,
                claim=claim,
                code=failure_code,
                now=self.utcnow(),
            )

    async def _wait_until(self, deadline: float) -> None:
        while self.monotonic() < deadline:
            await self.sleeper(min(0.05, max(0, deadline - self.monotonic())))

    def _elapsed_ms(self, started: float) -> int:
        return round((self.perf_counter() - started) * 1000)

    @staticmethod
    def _raise_capacity() -> None:
        raise SandboxError(
            "sandbox_capacity",
            "Secure workspace capacity is temporarily full",
        )
