"""Typed chat sandbox turn orchestration and cancellation."""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.chat_sandbox_worker.protocol import ProtocolError
from backend.config import Settings
from backend.services.chat_sandbox_acquisition_coordinator import (
    ChatSandboxAcquisitionCoordinator,
    LeaseReused,
    PoolAcquired,
    SandboxAcquisitionOutcome,
    SandboxCreated,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    ChatSandboxLeaseLifecycleCoordinator,
)
from backend.services.chat_sandbox_lease_maintenance_coordinator import (
    ChatSandboxLeaseMaintenanceCoordinator,
)
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_spend_access import (
    assert_chat_sandbox_spend_available,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    LeaseUnavailable,
    WorkerClaim,
    WorkerGenerationUnavailable,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    WorkerCancelStatus,
    WorkerTurnDispatchOutcome,
    WorkerTurnExecution,
    WorkerTurnMilestone,
    WorkerTurnMode,
    WorkerTurnRequest,
)

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
UtcClock = Callable[[], datetime]
FloatClock = Callable[[], float]
TokenFactory = Callable[[], str]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatSandboxTurnRequest:
    chat_session_id: uuid.UUID
    turn_id: uuid.UUID
    request_id: str
    prompt: str = field(repr=False)
    model: str
    resume: str | None
    capability_token: str = field(repr=False)
    provider_protocol: str = "anthropic-messages"
    provider_model: str | None = None
    agent_harness: str = "claude"
    web_search_enabled: bool = False
    reader_mode: bool = False
    poster_mode: bool = False
    paper_artifacts_enabled: bool = False
    paper_descriptor: dict[str, object] | None = None
    reasoning_effort: str = "high"
    fetchable_urls: tuple[str, ...] = ()
    hf_username: str = "unknown"


class ChatSandboxTurnCoordinator:
    """Run one worker turn while preserving durable lease ownership."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        state_repository: ChatSandboxStateRepository,
        acquisition: ChatSandboxAcquisitionCoordinator,
        transport: ChatSandboxWorkerTransport,
        lifecycle: ChatSandboxLeaseLifecycleCoordinator,
        maintenance: ChatSandboxLeaseMaintenanceCoordinator,
        spend_factory: SpendFactory | None = None,
        utcnow: UtcClock | None = None,
        perf_counter: FloatClock = time.perf_counter,
        assignment_token_factory: TokenFactory | None = None,
    ) -> None:
        if state_repository.settings is not settings:
            raise ValueError("Turn state settings must be shared")
        if (
            acquisition.settings is not settings
            or lifecycle.settings is not settings
            or maintenance.settings is not settings
        ):
            raise ValueError("Turn component settings must be shared")
        if (
            acquisition.session_factory is not session_factory
            or lifecycle.session_factory is not session_factory
            or maintenance.session_factory is not session_factory
        ):
            raise ValueError("Turn component sessions must be shared")
        if (
            acquisition.state_repository is not state_repository
            or lifecycle.repository is not state_repository
            or maintenance.repository is not state_repository
        ):
            raise ValueError("Turn state repositories must be shared")
        if (
            acquisition.transport is not transport
            or lifecycle.transport is not transport
        ):
            raise ValueError("Turn worker transport must be shared")
        if (
            acquisition.provider is not transport.provider
            or lifecycle.provider is not transport.provider
            or maintenance.provider is not transport.provider
        ):
            raise ValueError("Turn provider must be shared")
        if acquisition.lease_maintenance is not maintenance:
            raise ValueError("Turn acquisition maintenance must be shared")
        if maintenance.lifecycle is not lifecycle:
            raise ValueError("Turn lease lifecycle must be shared")
        if lifecycle.idle_eviction is not acquisition.pool.lease_eviction:
            raise ValueError("Turn idle eviction must be shared")
        capacity_locker = acquisition.capacity_repository.capacity_locker
        if (
            lifecycle.capacity_locker is not capacity_locker
            or maintenance.capacity_locker is not capacity_locker
        ):
            raise ValueError("Turn capacity lock must be shared")

        self.settings = settings
        self.session_factory = session_factory
        self.state_repository = state_repository
        self.acquisition = acquisition
        self.transport = transport
        self.lifecycle = lifecycle
        self.maintenance = maintenance
        self.spend_factory = spend_factory or (
            lambda db: ChatSandboxSpendService(db, settings)
        )
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.perf_counter = perf_counter
        self.assignment_token_factory = assignment_token_factory or (
            lambda: secrets.token_urlsafe(24)
        )

    @property
    def persistent_enabled(self) -> bool:
        return bool(getattr(self.settings, "chat_persistent_worker_enabled", False))

    @property
    def spend_enforced(self) -> bool:
        return bool(
            getattr(
                self.settings,
                "chat_sandbox_spend_enforcement_enabled",
                False,
            )
        )

    async def run(self, request: ChatSandboxTurnRequest) -> AsyncIterator[dict]:
        """Stream one turn, retrying one failed reusable assignment at most once."""

        try:
            async for event in self._run(request):
                yield event
        finally:
            self.transport.clear_deferred_cancel(request.turn_id)

    async def _run(self, request: ChatSandboxTurnRequest) -> AsyncIterator[dict]:
        """Run one turn behind its pre-registration cancellation fence."""

        if self.spend_enforced:
            try:
                assert_chat_sandbox_spend_available(
                    self.settings,
                    session_factory=self.session_factory,
                    spend_factory=self.spend_factory,
                )
            except ChatComputeDisabled as error:
                raise SandboxError(error.code, str(error)) from error
        retrying_assignment = False
        while True:
            try:
                async for event in self._run_once(
                    request,
                    allow_pool=not retrying_assignment,
                    forced_pool_miss=retrying_assignment,
                ):
                    if retrying_assignment and event.get("type") == "sandbox_start":
                        continue
                    yield event
                return
            except SandboxError as error:
                if error.code != "pool_assignment_failed" or retrying_assignment:
                    raise
                failed_at = error.failure_monotonic
                retry_overhead_ms = (
                    0
                    if failed_at is None
                    else round(max(0.0, self.perf_counter() - failed_at) * 1000)
                )
                logger.warning(
                    "chat warm assignment fallback request_id=%s turn_id=%s "
                    "sandbox_id=%s release_id=%s image_version=%s contract=%s "
                    "failure_stage=%s failure_class=%s retry_overhead_ms=%s",
                    request.request_id,
                    request.turn_id,
                    error.sandbox_id,
                    self.settings.release_id,
                    self.settings.chat_modal_image_version,
                    self.settings.chat_worker_contract_version,
                    error.failure_stage,
                    error.failure_class,
                    retry_overhead_ms,
                )
                yield {
                    "type": "_latency",
                    "phase": "assignment_fallback",
                    "elapsed_ms": retry_overhead_ms,
                    "failure_stage": error.failure_stage,
                    "failure_class": error.failure_class,
                    "attempt_kind": error.attempt_kind,
                }
                retrying_assignment = True

    async def _run_once(
        self,
        request: ChatSandboxTurnRequest,
        *,
        allow_pool: bool,
        forced_pool_miss: bool,
    ) -> AsyncIterator[dict]:
        turn_started = self.perf_counter()
        yield {
            "type": "sandbox_start",
            "session_id": str(request.chat_session_id),
        }
        yield {"type": "lifecycle", "phase": "preparing_workspace"}
        acquisition = await self._acquire_for_turn(
            request,
            allow_pool=allow_pool,
            forced_pool_miss=forced_pool_miss,
        )
        sandbox = acquisition.sandbox
        acquisition_label = acquisition.public_label
        cold_start_ms = acquisition.elapsed_ms

        if acquisition.pool_lookup_ms is not None:
            yield {
                "type": "_latency",
                "phase": "pool_lookup_completed",
                "elapsed_ms": acquisition.pool_lookup_ms,
            }
        yield {
            "type": "_latency",
            "phase": "sandbox_acquisition_ms",
            "elapsed_ms": self._elapsed_ms(turn_started),
            "acquisition_outcome": acquisition_label,
            "pool_miss_reason": getattr(acquisition, "pool_miss_reason", None),
            "session_reuse_cohort": getattr(acquisition, "reuse_cohort", None),
        }
        if isinstance(acquisition, PoolAcquired):
            yield {
                "type": "_latency",
                "phase": "session_assignment_completed",
                "elapsed_ms": self._elapsed_ms(turn_started),
            }
        if isinstance(acquisition, SandboxCreated):
            yield {
                "type": "_latency",
                "phase": "modal_create_ms",
                "elapsed_ms": cold_start_ms,
            }
        yield {
            "type": "sandbox_ready",
            "session_id": str(request.chat_session_id),
            "cold_start_ms": cold_start_ms,
        }
        yield {"type": "lifecycle", "phase": "starting_agent"}

        claim: WorkerClaim | None = None
        execution: WorkerTurnExecution | None = None
        try:
            first_semantic_recorded = False
            turn_timeout = (
                self.settings.chat_posterly_timeout_seconds
                if request.poster_mode
                else self.settings.chat_agent_timeout_seconds
            )
            if request.paper_artifacts_enabled:
                # The worker still starts under normal limits and extends only
                # after a successful authenticated paper command. The process
                # needs enough headroom to receive that in-turn extension.
                turn_timeout = max(
                    turn_timeout, self.settings.chat_latex_paper_timeout_seconds
                )
            claim = self._claim_worker(request.chat_session_id, sandbox.object_id)
            execution = self.transport.create_execution(
                sandbox,
                claim,
                WorkerTurnRequest(
                    chat_session_id=request.chat_session_id,
                    turn_id=request.turn_id,
                    request_id=request.request_id,
                    prompt=request.prompt,
                    model=request.provider_model or request.model,
                    provider_protocol=request.provider_protocol,
                    resume=request.resume,
                    capability_token=request.capability_token,
                    agent_harness=request.agent_harness,
                    gateway_url=self.settings.chat_gateway_url,
                    web_search_enabled=request.web_search_enabled,
                    reader_mode=request.reader_mode,
                    poster_mode=request.poster_mode,
                    paper_artifacts_enabled=request.paper_artifacts_enabled,
                    paper_descriptor=request.paper_descriptor,
                    reasoning_effort=request.reasoning_effort,
                    fetchable_urls=request.fetchable_urls,
                    hf_username=request.hf_username,
                ),
                (
                    WorkerTurnMode.PERSISTENT
                    if self.persistent_enabled
                    else WorkerTurnMode.ONE_SHOT
                ),
                process_timeout_seconds=round(turn_timeout + 15),
            )
            dispatch = await execution.dispatch()
            if dispatch is WorkerTurnDispatchOutcome.CANCELLED:
                yield {"type": "_cancelled"}
                return
            if getattr(execution, "control_connection_opened", False):
                yield {
                    "type": "_latency",
                    "phase": "control_connection",
                    "elapsed_ms": self._elapsed_ms(turn_started),
                }
            if getattr(execution, "agent_spawned", False):
                yield {
                    "type": "_latency",
                    "phase": "agent_spawn",
                    "elapsed_ms": self._elapsed_ms(turn_started),
                }
            yield {
                "type": "_latency",
                "phase": "capability_install_ms",
                "elapsed_ms": self._elapsed_ms(turn_started),
            }
            async for output in execution.events(timeout_seconds=turn_timeout):
                if output is WorkerTurnMilestone.AGENT_READY:
                    elapsed_ms = self._elapsed_ms(turn_started)
                    yield {
                        "type": "_latency",
                        "phase": "worker_ready_ms",
                        "elapsed_ms": elapsed_ms,
                    }
                    yield {
                        "type": "_latency",
                        "phase": "agent_startup_ready",
                        "elapsed_ms": elapsed_ms,
                    }
                elif output is WorkerTurnMilestone.SDK_DISPATCHED:
                    elapsed_ms = self._elapsed_ms(turn_started)
                    yield {
                        "type": "_latency",
                        "phase": "sdk_dispatch_ms",
                        "elapsed_ms": elapsed_ms,
                    }
                elif output is WorkerTurnMilestone.FIRST_DELTA:
                    yield {
                        "type": "_latency",
                        "phase": "first_worker_delta",
                        "elapsed_ms": self._elapsed_ms(turn_started),
                    }
                elif output is WorkerTurnMilestone.CANCELLED:
                    yield {"type": "_cancelled"}
                else:
                    if output.get("type") == "_latency":
                        yield {
                            **output,
                            "elapsed_ms": self._elapsed_ms(turn_started),
                        }
                        continue
                    if not first_semantic_recorded and output.get("type") in {
                        "reasoning_delta",
                        "tool_call",
                        "tool_call_start",
                        "answer_delta",
                    }:
                        first_semantic_recorded = True
                        yield {
                            "type": "_latency",
                            "phase": "first_semantic_event",
                            "elapsed_ms": self._elapsed_ms(turn_started),
                            "first_semantic_event_class": {
                                "reasoning_delta": "reasoning",
                                "tool_call": "tool",
                                "tool_call_start": "tool",
                                "answer_delta": "answer",
                            }[output["type"]],
                        }
                    if output.get("type") == "workspace_ready":
                        yield {"type": "lifecycle", "phase": "connecting_model"}
                    yield output
        except (TimeoutError, ProtocolError, SandboxError) as error:
            if self._retryable_assignment_failure(acquisition, execution):
                raise self._assignment_failure(acquisition, error) from error
            if isinstance(error, TimeoutError):
                raise SandboxError(
                    "sandbox_timeout",
                    "The research run timed out",
                    uncertain=True,
                ) from error
            if isinstance(error, ProtocolError):
                raise SandboxError(
                    "sandbox_worker_failed",
                    "The worker protocol failed",
                    uncertain=True,
                ) from error
            raise
        except Exception as error:
            if self._retryable_assignment_failure(acquisition, execution):
                raise self._assignment_failure(acquisition, error) from error
            raise
        finally:
            if execution is not None:
                await execution.close()
            if execution is None or not execution.terminal:
                if claim is not None:
                    await self.lifecycle.terminate_worker(
                        request.chat_session_id,
                        claim,
                        failure_code=(
                            "cancelled"
                            if execution is not None and execution.cancel_requested
                            else "sandbox_worker_failed"
                        ),
                    )
                elif isinstance(acquisition, PoolAcquired):
                    await self.lifecycle.terminate(
                        request.chat_session_id,
                        failure_code="pool_assignment_failed",
                    )
            elif claim is not None and self._release_worker(
                request.chat_session_id,
                claim,
            ):
                await self.maintenance.enforce_warm_cap()

    async def _acquire_for_turn(
        self,
        request: ChatSandboxTurnRequest,
        *,
        allow_pool: bool,
        forced_pool_miss: bool,
    ) -> SandboxAcquisitionOutcome:
        # A retry reaches this path only after the existing control failed before
        # SDK dispatch. Do not select that same in-memory control again even if
        # lifecycle cleanup has not removed it from the transport yet.
        if self.persistent_enabled and not forced_pool_miss:
            reusable = self.transport.reusable_sandbox(
                request.chat_session_id,
                request.resume,
            )
            if reusable is not None:
                return LeaseReused(
                    sandbox=reusable,
                    elapsed_ms=0,
                    pool_lookup_ms=None,
                    reuse_cohort="fully_in_memory",
                )
        prewarm_incompatible = bool(
            self.settings.chat_pi_prewarm_enabled
            and request.resume is None
            and (
                request.agent_harness != "pi"
                or request.model != self.settings.chat_effective_pi_prewarm_model
                or request.reasoning_effort
                != self.settings.chat_pi_prewarm_reasoning_effort
            )
        )
        return await self.acquisition.acquire(
            request.chat_session_id,
            pool_miss=forced_pool_miss or prewarm_incompatible,
            pool_miss_reason=(
                "incompatible_profile"
                if prewarm_incompatible
                else (
                    "unhealthy_blank"
                    if forced_pool_miss and request.resume is None
                    else None
                )
            ),
            budget_prechecked=True,
            allow_pool=bool(
                allow_pool
                and self.persistent_enabled
                and self.acquisition.blank_pool_enabled
                and request.resume is None
                and not prewarm_incompatible
            ),
        )

    @staticmethod
    def _retryable_assignment_failure(
        acquisition: SandboxAcquisitionOutcome,
        execution: WorkerTurnExecution | None,
    ) -> bool:
        return isinstance(acquisition, (PoolAcquired, LeaseReused)) and not (
            execution is not None and execution.sdk_dispatched
        )

    def _claim_worker(
        self,
        chat_session_id: uuid.UUID,
        sandbox_id: str,
    ) -> WorkerClaim:
        assignment_token = self.assignment_token_factory()
        with self.session_factory() as db, db.begin():
            lease = self.state_repository.load_lease(
                db,
                chat_session_id,
                lock=True,
            )
            try:
                return self.state_repository.claim_worker(
                    lease,
                    sandbox_id=sandbox_id,
                    assignment_token=assignment_token,
                    now=self.utcnow(),
                )
            except LeaseUnavailable as error:
                raise SandboxError(
                    "sandbox_lost",
                    "Secure workspace is unavailable",
                    failure_stage="claim_worker",
                    failure_class=type(error).__name__,
                ) from error
            except WorkerGenerationUnavailable as error:
                raise SandboxError(
                    "sandbox_lost",
                    "Secure workspace generation is unavailable",
                    failure_stage="claim_worker",
                    failure_class=type(error).__name__,
                ) from error

    def _assignment_failure(
        self,
        acquisition: SandboxAcquisitionOutcome,
        error: BaseException,
    ) -> SandboxError:
        attempt_kind = (
            "pool"
            if isinstance(acquisition, PoolAcquired)
            else "reused"
            if isinstance(acquisition, LeaseReused)
            else "direct"
        )
        return SandboxError(
            "pool_assignment_failed",
            "The secure workspace assignment failed",
            uncertain=True,
            failure_stage=(
                getattr(error, "failure_stage", None)
                if getattr(error, "failure_stage", None)
                else "agent_stream"
            ),
            failure_class=(
                getattr(error, "failure_class", None)
                if getattr(error, "failure_class", None)
                else type(error).__name__
            ),
            attempt_kind=attempt_kind,
            sandbox_id=str(acquisition.sandbox.object_id),
            failure_monotonic=self.perf_counter(),
        )

    def _release_worker(
        self,
        chat_session_id: uuid.UUID,
        claim: WorkerClaim,
    ) -> bool:
        with self.session_factory() as db, db.begin():
            lease = self.state_repository.load_lease(
                db,
                chat_session_id,
                lock=True,
            )
            return self.state_repository.release_worker(
                lease,
                claim=claim,
                now=self.utcnow(),
            )

    async def cancel(
        self,
        chat_session_id: uuid.UUID,
        turn_id: uuid.UUID,
    ) -> WorkerCancelStatus:
        outcome = await self.transport.cancel(
            turn_id,
            grace_seconds=self.settings.chat_cancel_grace_seconds,
        )
        if outcome.status is WorkerCancelStatus.NOT_FOUND:
            self.transport.defer_cancel(turn_id)
            return WorkerCancelStatus.PENDING
        if outcome.status is WorkerCancelStatus.CONTROL_LOST:
            assert outcome.claim is not None
            await self.lifecycle.terminate_worker(
                chat_session_id,
                outcome.claim,
                failure_code="cancel_control_lost",
            )
            self.transport.complete_control_loss(outcome)
        elif outcome.status is WorkerCancelStatus.TIMED_OUT:
            assert outcome.claim is not None
            await self.lifecycle.terminate_worker(
                chat_session_id,
                outcome.claim,
                failure_code="cancel_timeout",
            )
        return outcome.status

    def _elapsed_ms(self, started: float) -> int:
        return round((self.perf_counter() - started) * 1000)
