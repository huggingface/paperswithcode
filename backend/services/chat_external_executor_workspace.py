"""Lazy, fenced executor workspace ownership for external Pi turns."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.chat_sandbox_worker.executor_protocol import ProtocolError
from backend.config import Settings
from backend.services.chat_sandbox_acquisition_coordinator import (
    ChatSandboxAcquisitionCoordinator,
)
from backend.services.chat_sandbox_executor import (
    ExecutorContext,
    ExecutorTransportError,
    PersistentExecutorChannel,
    SandboxExecutorClient,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    ChatSandboxLeaseLifecycleCoordinator,
)
from backend.services.chat_sandbox_lease_maintenance_coordinator import (
    ChatSandboxLeaseMaintenanceCoordinator,
)
from backend.services.chat_sandbox_provider import (
    SandboxError,
    SandboxLaunchMode,
    SandboxProvider,
)
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    LeaseUnavailable,
    WorkerClaim,
    WorkerGenerationUnavailable,
)
from backend.services.chat_turn_job_repository import (
    ChatTurnJobRepository,
    StaleTurnClaim,
    TurnLeaseClaim,
)

SessionFactory = Callable[[], Session]
LifecycleObserver = Callable[[str, str | None, int], None]
QualificationEvidenceRecorder = Callable[..., bool]
QualificationCapacityResolver = Callable[..., int | None]
EXECUTOR_IDLE_RETENTION_SECONDS = 5 * 60
EXECUTOR_RETAINED_GLOBAL_CAP = 10
MIN_EXECUTOR_CLAIM_SECONDS = 240


@dataclass(frozen=True)
class ExternalExecutorWorkspace:
    """One exact busy claim on a durable session workspace."""

    session_id: uuid.UUID
    turn_id: uuid.UUID
    sandbox: object
    sandbox_id: str
    worker_generation: str
    workspace_generation: int
    claim: WorkerClaim
    acquired_monotonic: float


@dataclass(slots=True)
class ExternalExecutorTurnBinding:
    """One turn's workspace and already-authorized persistent channel."""

    workspace: ExternalExecutorWorkspace
    channel: PersistentExecutorChannel
    context: ExecutorContext
    settlement: str = "invalidate"
    settled: bool = False


def _workspace_generation(worker_generation: str) -> int:
    """Map the durable opaque generation into the executor's positive int fence."""

    value = int.from_bytes(
        hashlib.sha256(worker_generation.encode()).digest()[:8], "big"
    ) & (2**63 - 1)
    return value or 1


class ChatExternalExecutorWorkspaceManager:
    """Acquire executor-only sandboxes lazily and retain them while idle."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: SessionFactory,
        state_repository: ChatSandboxStateRepository,
        acquisition: ChatSandboxAcquisitionCoordinator,
        lifecycle: ChatSandboxLeaseLifecycleCoordinator,
        maintenance: ChatSandboxLeaseMaintenanceCoordinator,
        executor: SandboxExecutorClient,
        turn_repository: ChatTurnJobRepository | None = None,
        utcnow: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        assignment_token_factory: Callable[[], str] | None = None,
        observe: LifecycleObserver | None = None,
        record_evidence: QualificationEvidenceRecorder | None = None,
        qualification_capacity: QualificationCapacityResolver | None = None,
        executor_runtime: object | None = None,
    ) -> None:
        if settings.chat_workspace_snapshots_enabled:
            raise ValueError("External executor workspaces require snapshots disabled")
        if (
            settings.chat_sandbox_warm_seconds != EXECUTOR_IDLE_RETENTION_SECONDS
            or settings.chat_sandbox_max_warm != EXECUTOR_RETAINED_GLOBAL_CAP
        ):
            raise ValueError("External executor retention contract is invalid")
        if acquisition.settings is not settings:
            raise ValueError("Workspace acquisition settings must be shared")
        if acquisition.session_factory is not session_factory:
            raise ValueError("Workspace acquisition sessions must be shared")
        if acquisition.state_repository is not state_repository:
            raise ValueError("Workspace state repository must be shared")
        if lifecycle.repository is not state_repository:
            raise ValueError("Workspace lifecycle repository must be shared")
        if maintenance.repository is not state_repository:
            raise ValueError("Workspace maintenance repository must be shared")
        self.settings = settings
        self.session_factory = session_factory
        self.state_repository = state_repository
        self.acquisition = acquisition
        self.lifecycle = lifecycle
        self.maintenance = maintenance
        self.executor = executor
        self.turn_repository = turn_repository or ChatTurnJobRepository()
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self.sleeper = sleeper
        self.assignment_token_factory = assignment_token_factory or (
            lambda: secrets.token_urlsafe(24)
        )
        self.observe = observe or (lambda _event, _code, _value: None)
        self.record_evidence = record_evidence or (lambda **_kwargs: False)
        self.qualification_capacity = (
            qualification_capacity or self._persisted_qualification_capacity
        )
        self.executor_runtime = executor_runtime

    def _persisted_qualification_capacity(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
    ) -> int | None:
        from backend.services.chat_durable_qualification_evidence import (
            ChatDurableQualificationEvidenceService,
        )

        return ChatDurableQualificationEvidenceService(db).executor_live_cap(
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            settings=self.settings,
        )

    def _executor_live_cap(
        self, db: Session, session_id: uuid.UUID, turn_claim: TurnLeaseClaim
    ) -> int:
        qualified = self.qualification_capacity(
            db,
            turn_id=turn_claim.turn_id,
            chat_session_id=session_id,
        )
        return qualified or self.settings.chat_sandbox_total_live_cap

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        provider: SandboxProvider,
        executor: SandboxExecutorClient,
    ) -> ChatExternalExecutorWorkspaceManager:
        # Local import keeps the compatibility façade out of the domain module's
        # import graph while reusing its single, validated dependency assembly.
        from backend.services.chat_sandbox_service import SandboxSessionManager
        from backend.services.chat_durable_lifecycle_observer import (
            durable_lifecycle_observer,
        )
        from backend.services.chat_durable_qualification_evidence import (
            record_qualification_event_safely,
        )

        owner = SandboxSessionManager(settings, sandbox_provider=provider)
        executor_runtime = None
        acquisition = owner._acquisition_coordinator()
        if settings.chat_executor_remote_transport_enabled:
            from backend.services.chat_executor_runtime import ChatExecutorRuntime

            executor_runtime = ChatExecutorRuntime(
                settings, session_factory=owner.session_factory
            )
            acquisition.executor_launch_factory = executor_runtime.prepare_launch
        manager = cls(
            settings=settings,
            session_factory=owner.session_factory,
            state_repository=owner._state_repository(),
            acquisition=acquisition,
            lifecycle=owner._lease_lifecycle_coordinator(),
            maintenance=owner._lease_maintenance_coordinator(),
            executor=executor,
            observe=durable_lifecycle_observer(settings),
            record_evidence=record_qualification_event_safely,
            executor_runtime=executor_runtime,
        )
        manager._dependency_owner = owner
        return manager

    async def acquire(
        self,
        *,
        session_id: uuid.UUID,
        turn_claim: TurnLeaseClaim,
    ) -> ExternalExecutorWorkspace:
        return await self._acquire(
            session_id=session_id,
            turn_claim=turn_claim,
            verify_executor_health=True,
            launch_mode=SandboxLaunchMode.EXECUTOR,
        )

    async def acquire_for_binding(
        self,
        *,
        session_id: uuid.UUID,
        turn_claim: TurnLeaseClaim,
    ) -> ExternalExecutorWorkspace:
        """Claim lifecycle capacity without launching a legacy health relay."""

        return await self._acquire(
            session_id=session_id,
            turn_claim=turn_claim,
            verify_executor_health=False,
            launch_mode=SandboxLaunchMode.EXECUTOR,
        )

    async def acquire_legacy(
        self,
        *,
        session_id: uuid.UUID,
        turn_claim: TurnLeaseClaim,
    ) -> ExternalExecutorWorkspace:
        """Use the pre-transport Modal relay after circuit fallback."""

        return await self._acquire(
            session_id=session_id,
            turn_claim=turn_claim,
            verify_executor_health=True,
            launch_mode=SandboxLaunchMode.LEGACY,
        )

    async def _acquire(
        self,
        *,
        session_id: uuid.UUID,
        turn_claim: TurnLeaseClaim,
        verify_executor_health: bool,
        launch_mode: SandboxLaunchMode,
    ) -> ExternalExecutorWorkspace:
        deadline = self.monotonic() + self.acquisition.ready_timeout_seconds
        replacement_attempts = 0
        self._mark_executor_resource_started(turn_claim.turn_id)
        while True:
            self._require_live_turn(session_id, turn_claim)
            outcome = await self.acquisition.acquire(
                session_id,
                launch_mode=launch_mode,
                allow_pool=False,
                live_cap_resolver=lambda db: self._executor_live_cap(
                    db, session_id, turn_claim
                ),
            )
            try:
                claim = self._claim(session_id, str(outcome.sandbox.object_id))
            except (LeaseUnavailable, WorkerGenerationUnavailable):
                if self.monotonic() >= deadline:
                    raise SandboxError(
                        "sandbox_timeout", "Secure workspace startup timed out"
                    ) from None
                await self.sleeper(0.05)
                continue

            workspace = ExternalExecutorWorkspace(
                session_id=session_id,
                turn_id=turn_claim.turn_id,
                sandbox=outcome.sandbox,
                sandbox_id=claim.sandbox_id,
                worker_generation=claim.worker_generation,
                workspace_generation=_workspace_generation(claim.worker_generation),
                claim=claim,
                acquired_monotonic=self.monotonic(),
            )
            if verify_executor_health:
                try:
                    healthy = await self.executor.health(workspace.sandbox) == "ok"
                except asyncio.CancelledError:
                    await self._invalidate_preserving_primary(workspace)
                    raise
                except (ExecutorTransportError, ProtocolError, SandboxError):
                    healthy = False
                except Exception:
                    await self._invalidate_preserving_primary(workspace)
                    raise
            else:
                healthy = True
            if healthy:
                try:
                    self._require_live_turn(session_id, turn_claim)
                except StaleTurnClaim:
                    await self._release_preserving_primary(workspace)
                    raise
                self.observe(
                    "workspace_state",
                    "created" if outcome.public_label == "created" else "reused",
                    1,
                )
                self.record_evidence(
                    turn_id=turn_claim.turn_id,
                    chat_session_id=session_id,
                    event_type=(
                        "workspace_created"
                        if outcome.public_label == "created"
                        else "workspace_reused"
                    ),
                )
                return workspace

            invalidated = await self._invalidate_preserving_primary(workspace)
            if not invalidated:
                raise SandboxError(
                    "sandbox_worker_failed", "Secure workspace executor is unavailable"
                )
            replacement_attempts += 1
            if replacement_attempts >= 2 or self.monotonic() >= deadline:
                raise SandboxError(
                    "sandbox_worker_failed", "Secure workspace executor is unavailable"
                )

    async def release(self, workspace: ExternalExecutorWorkspace) -> bool:
        with self.session_factory() as db, db.begin():
            lease = self.state_repository.load_lease(
                db, workspace.session_id, lock=True
            )
            released = self.state_repository.release_worker(
                lease,
                claim=workspace.claim,
                now=self.utcnow(),
            )
            if released:
                self._mark_executor_resource_ended(workspace.turn_id, db=db)
        if released:
            self._observe_active_duration(workspace)
            self.observe("workspace_state", "released", 1)
            await self.maintenance.enforce_warm_cap()
        return released

    async def invalidate(
        self,
        workspace: ExternalExecutorWorkspace,
        *,
        failure_code: str = "sandbox_worker_failed",
    ) -> None:
        """Fence and terminate only the exact busy workspace claim."""

        await self.lifecycle.terminate_worker(
            workspace.session_id,
            workspace.claim,
            failure_code=failure_code,
        )
        self._mark_executor_resource_ended(workspace.turn_id)
        self._observe_active_duration(workspace)
        self.observe("workspace_state", "invalidated", 1)
        self.record_evidence(
            turn_id=workspace.turn_id,
            chat_session_id=workspace.session_id,
            event_type="workspace_evicted",
        )

    def _observe_active_duration(self, workspace: ExternalExecutorWorkspace) -> None:
        elapsed_ms = max(
            0,
            min(
                round((self.monotonic() - workspace.acquired_monotonic) * 1_000),
                16 * 1024 * 1024,
            ),
        )
        self.observe("workspace_active_ms", None, elapsed_ms)

    def _mark_executor_resource_started(self, turn_id: uuid.UUID) -> None:
        if self.executor_runtime is None:
            return
        from backend.services.chat_turn_admission import ChatTurnAdmissionService

        with self.session_factory() as db, db.begin():
            ChatTurnAdmissionService(
                environment=self.settings.environment,
                spend_limit_microusd=(
                    self.settings.chat_sandbox_application_cap_microusd
                ),
            ).mark_resource_started(db, turn_id=turn_id, now=self.utcnow())

    def _mark_executor_resource_ended(
        self, turn_id: uuid.UUID, *, db: Session | None = None
    ) -> None:
        if self.executor_runtime is None:
            return
        from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
        from backend.services.chat_turn_admission import ChatTurnAdmissionService

        def mark(session: Session) -> None:
            ChatTurnAdmissionService(
                environment=self.settings.environment,
                spend_limit_microusd=(
                    self.settings.chat_sandbox_application_cap_microusd
                ),
            ).mark_resource_ended_and_reconcile(
                session,
                turn_id=turn_id,
                cost_per_second_microusd=ChatSandboxSpendService(
                    session, self.settings
                ).cost_per_second(),
                now=self.utcnow(),
            )

        if db is not None:
            mark(db)
            return
        with self.session_factory() as session, session.begin():
            mark(session)

    async def _release_preserving_primary(
        self, workspace: ExternalExecutorWorkspace
    ) -> None:
        try:
            await self.release(workspace)
        except asyncio.CancelledError:
            await self._invalidate_preserving_primary(workspace)
            raise
        except Exception:
            await self._invalidate_preserving_primary(workspace)

    async def _invalidate_preserving_primary(
        self, workspace: ExternalExecutorWorkspace
    ) -> bool:
        try:
            await self.invalidate(workspace)
        except Exception:
            # The exact busy fence remains unreusable until reconciliation.
            return False
        return True

    def _claim(self, session_id: uuid.UUID, sandbox_id: str) -> WorkerClaim:
        with self.session_factory() as db, db.begin():
            lease = self.state_repository.load_lease(db, session_id, lock=True)
            return self.state_repository.claim_worker(
                lease,
                sandbox_id=sandbox_id,
                assignment_token=self.assignment_token_factory(),
                now=self.utcnow(),
            )

    def _require_live_turn(self, session_id: uuid.UUID, claim: TurnLeaseClaim) -> None:
        with self.session_factory() as db, db.begin():
            self.turn_repository.require_live_claim(
                db,
                claim=claim,
                now=self.utcnow(),
            )
