"""External Pi turn transport with lazy, fenced sandbox tool execution."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import WebSocketException

from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRepository,
    ExternalWorkerClaim,
    StaleWorkerClaim,
    WorkerLeaseUnavailable,
)
from backend.services.chat_external_worker_capacity import (
    ChatExternalWorkerCapacityRepository,
    ExternalWorkerEndpoint,
    external_worker_endpoints,
    require_ordinary_research_mode,
)
from backend.services.chat_external_pi_shadow import (
    ExternalPiWorkerControlClient,
    ExternalPiWorkerControlRejected,
    ExternalPiWorkerStatus,
    ExternalPiWorkerUnavailable,
)
from backend.services.chat_external_executor_workspace import (
    ChatExternalExecutorWorkspaceManager,
)
from backend.services.chat_external_pi_tool_executor import (
    ChannelFactory,
    ExternalPiToolWorkspaceExecutor,
)
from backend.services.chat_external_pi_lifecycle import ExternalPiTurnLifecycle
from backend.services.chat_sandbox_executor import (
    ExecutorContext,
    ExecutorExecutionLost,
    SandboxExecutorClient,
)
from backend.services.chat_sandbox_provider import ModalSandboxProviderAdapter
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_turn_job_repository import TurnLeaseClaim
from backend.services.chat_turn_cancel_control import CancelControlResult
from backend.services.chat_qualification_stale_boundary import (
    QUALIFIED_OWNERSHIP_REJECTIONS,
    QualificationStaleFenceBoundary,
)

from backend.services.chat_worker_event_checkpoint import CheckpointedWorkerEvent

MAX_EXTERNAL_TURN_FRAME_BYTES = 2 * 1024 * 1024 + 256 * 1024
type LifecycleObserver = Callable[[str, str | None, int], None]
logger = logging.getLogger("uvicorn.error")


def _worker_websocket_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit(
        (scheme, parsed.netloc, f"{parsed.path.rstrip('/')}/v1/turn", "", "")
    )


class ExternalPiChatTurnRunner:
    """Run Pi on the trusted host and create a Modal executor only on tool use."""

    sdk_directory = "/workspace"

    def __init__(
        self,
        *,
        settings: Settings,
        admission: TurnAdmission,
        prompt: str,
        request_id: str,
        resume_id: uuid.UUID | None,
        capability: IssuedCapability,
        hf_username: str,
        provider: Any | None = None,
        executor: SandboxExecutorClient | Any | None = None,
        workspace_manager: ChatExternalExecutorWorkspaceManager | Any | None = None,
        websocket_connector: Callable[..., Any] = websocket_connect,
        worker_repository: ChatExternalWorkerRepository | Any | None = None,
        worker_capacity_repository: ChatExternalWorkerCapacityRepository
        | Any
        | None = None,
        worker_status_resolver: Callable[[], Awaitable[ExternalPiWorkerStatus]]
        | None = None,
        session_factory: Callable[[], AbstractContextManager[Any]] | None = None,
        now: Callable[[], datetime] | None = None,
        turn_state_transition: Callable[[str], Awaitable[None]] | None = None,
        observe: LifecycleObserver | None = None,
        cancel_timeout_seconds: float = 5.0,
        channel_factory: ChannelFactory | None = None,
    ) -> None:
        require_ordinary_research_mode(
            poster_mode=admission.poster_mode,
            paper_artifacts_enabled=admission.paper_artifacts_enabled,
        )
        self.settings = settings
        self.admission = admission
        self.prompt = prompt
        self.request_id = request_id
        self.resume_id = resume_id
        self.capability = capability
        self.capability_id: uuid.UUID | None = capability.capability_id
        self.hf_username = hf_username
        self.provider = provider or ModalSandboxProviderAdapter(settings)
        self.executor = executor or SandboxExecutorClient(self.provider)
        self.workspace_manager = workspace_manager
        self.websocket_connector = websocket_connector
        self.worker_repository = worker_repository or ChatExternalWorkerRepository(
            environment=settings.environment
        )
        self.worker_capacity_repository = worker_capacity_repository
        self.worker_status_resolver = worker_status_resolver
        self.session_factory = session_factory or db_manager.session_local
        self.now = now or (lambda: datetime.now(UTC))
        self.observe = observe or (lambda _event, _code, _value: None)
        from backend.services.chat_durable_qualification_evidence import (
            record_qualification_event_safely,
        )

        self.record_evidence = record_qualification_event_safely

        self.tool_executor = ExternalPiToolWorkspaceExecutor(
            settings=settings,
            admission=admission,
            capability=capability,
            provider=self.provider,
            executor=self.executor,
            workspace_manager=workspace_manager,
            transition=lambda state: self.turn_state_transition(state),
            observe=lambda event, code, value: self.observe(event, code, value),
            record_evidence=self.record_evidence,
            channel_factory=channel_factory,
        )
        self.lifecycle = ExternalPiTurnLifecycle(
            capability_id=self.capability_id,
            turn_claim=self._durable_turn_claim,
            session_factory=self.session_factory,
            now=self.now,
        )
        self.turn_state_transition = turn_state_transition or self._persist_turn_state
        if not 0 < cancel_timeout_seconds <= 30:
            raise ValueError("External cancellation timeout is invalid")
        self.cancel_timeout_seconds = cancel_timeout_seconds
        self.socket: Any | None = None
        self.external_worker_claim: ExternalWorkerClaim | None = None
        self.external_worker_endpoint: ExternalWorkerEndpoint | None = None
        self.execution_loss_cancelled = False

    async def events(self) -> AsyncIterator[dict]:
        boundary = QualificationStaleFenceBoundary(
            turn_id=self.admission.turn_id,
            chat_session_id=self.admission.session_id,
            recorder=self.record_evidence,
        )
        self.tool_executor.begin_turn()
        primary_exception_active = True
        try:
            async for event in self._events(boundary):
                if event.get("type") == "done":
                    # Completion lets the stream consumer cancel the producer.
                    # Release the retained workspace before that boundary.
                    await self.tool_executor.settle_turn()
                yield event
            primary_exception_active = False
        except QUALIFIED_OWNERSHIP_REJECTIONS:
            boundary.reject()
            raise
        finally:
            try:
                await self.tool_executor.settle_turn()
            except asyncio.CancelledError:
                raise
            except Exception:
                if not primary_exception_active:
                    raise

    async def _events(
        self, stale_boundary: QualificationStaleFenceBoundary
    ) -> AsyncIterator[dict]:
        worker_claim = await self._select_worker_claim()
        self.external_worker_claim = worker_claim
        acknowledged_sequence = 0
        durable_sequence = 0
        supports_durable_ack = False
        terminal_sequence: int | None = None
        terminal_acknowledged = False

        async def acknowledge_persisted(sequence: int) -> None:
            nonlocal durable_sequence, terminal_acknowledged
            durable_sequence = max(durable_sequence, sequence)
            socket = self.socket
            try:
                if terminal_acknowledged:
                    return
                if (
                    terminal_sequence is not None
                    and durable_sequence >= terminal_sequence - 1
                ):
                    # The producer may finish before its queued terminal commits.
                    # The fenced terminal-control channel releases that retained
                    # run without keeping the producer alive during persistence.
                    async with asyncio.timeout(2):
                        async with self._external_worker_socket(
                            worker_claim
                        ) as control:
                            await control.send(
                                json.dumps(
                                    self._terminal_ack_frame(terminal_sequence),
                                    separators=(",", ":"),
                                )
                            )
                    terminal_acknowledged = True
                elif socket is not None:
                    frame = {
                        **self._terminal_ack_frame(durable_sequence),
                        "type": "ack_events",
                    }
                    await socket.send(json.dumps(frame, separators=(",", ":")))
            except (OSError, TimeoutError, WebSocketException):
                # Lost receipts retain replay frames. Later cumulative receipts
                # retry progress; terminal grace bounds failed terminal cleanup.
                pass

        seen_sequence = 0
        started = False
        tool_results: dict[str, dict[str, object]] = {}
        pending_tool: tuple[int, str] | None = None
        for _attempt in range(3):
            if started:
                self.observe("turn_state", "reconnecting", 1)
                try:
                    await self._require_same_external_worker_claim(worker_claim)
                except (
                    StaleWorkerClaim,
                    WorkerLeaseUnavailable,
                    ExternalPiWorkerUnavailable,
                    ExternalPiWorkerControlRejected,
                    httpx.HTTPError,
                    ValueError,
                ) as error:
                    if isinstance(error, QUALIFIED_OWNERSHIP_REJECTIONS):
                        stale_boundary.reject()
                    self.observe("typed_failure", "external_worker_lost", 1)
                    yield self._worker_lost_event()
                    return
            try:
                async with self._external_worker_socket(worker_claim) as socket:
                    self.socket = socket
                    await socket.send(
                        json.dumps(
                            self._run_frame()
                            if not started
                            else self._attach_frame(acknowledged_sequence),
                            separators=(",", ":"),
                        )
                    )
                    if _attempt:
                        self.observe("worker_reconnect", None, 1)
                        self.observe("turn_state", "running", 1)
                    started = True
                    async for raw in socket:
                        event = self._decode(raw)
                        sequence = event.pop("worker_sequence", None)
                        if (
                            not isinstance(sequence, int)
                            or isinstance(sequence, bool)
                            or sequence < 1
                            or sequence > 2**53 - 1
                        ):
                            raise RuntimeError("External Pi frame sequence is invalid")
                        if sequence <= seen_sequence:
                            if event.get("type") == "tool_request":
                                operation_id = str(event.get("operation_id") or "")
                                result = tool_results.get(operation_id)
                                if result is None:
                                    raise RuntimeError(
                                        "External Pi replayed an unknown tool request"
                                    )
                                await socket.send(
                                    json.dumps(result, separators=(",", ":"))
                                )
                            continue
                        if sequence != seen_sequence + 1:
                            raise RuntimeError(
                                "External Pi frame sequence is discontinuous"
                            )
                        if pending_tool is not None:
                            tool_sequence, operation_id = pending_tool
                            acknowledged_sequence = tool_sequence
                            tool_results.pop(operation_id, None)
                            pending_tool = None
                        seen_sequence = sequence
                        if event.get("type") == "tool_request":
                            operation_id = str(event.get("operation_id") or "")
                            result = tool_results.get(operation_id)
                            if result is None:
                                try:
                                    result = await self._tool_result(event)
                                except ExecutorExecutionLost:
                                    try:
                                        await self.cancel()
                                    except Exception:
                                        self.execution_loss_cancelled = False
                                    else:
                                        self.execution_loss_cancelled = True
                                    raise
                                tool_results[operation_id] = result
                            await socket.send(json.dumps(result, separators=(",", ":")))
                            pending_tool = (sequence, operation_id)
                            continue
                        if event.get("type") == "worker_done":
                            terminal_sequence = sequence
                            # Old workers retain their existing protocol. New
                            # workers may release only a durably consumed prefix;
                            # otherwise their bounded terminal grace owns cleanup.
                            if supports_durable_ack and durable_sequence < sequence - 1:
                                return
                            await socket.send(
                                json.dumps(
                                    self._terminal_ack_frame(sequence),
                                    separators=(",", ":"),
                                )
                            )
                            terminal_acknowledged = True
                            return
                        if event.get("type") == "worker_ready":
                            # Readiness proves that the trusted harness accepted
                            # the run, but it is not part of the browser SSE
                            # contract.
                            supports_durable_ack = (
                                event.get("durable_event_ack") is True
                            )
                            acknowledged_sequence = sequence
                            continue
                        if supports_durable_ack:

                            async def receipt(sequence: int = sequence) -> None:
                                await acknowledge_persisted(sequence)

                            yield CheckpointedWorkerEvent(event, receipt)
                        else:
                            yield event
                        acknowledged_sequence = sequence
                    raise OSError("External Pi transport ended before terminal")
            except (OSError, TimeoutError, WebSocketException) as error:
                received = getattr(error, "rcvd", None)
                close_code = getattr(received, "code", None)
                close_reason = getattr(received, "reason", None)
                logger.warning(
                    "external Pi transport ended: error=%s code=%s reason=%s",
                    type(error).__name__,
                    close_code if isinstance(close_code, int) else "unknown",
                    close_reason
                    if isinstance(close_reason, str) and len(close_reason) <= 64
                    else "unknown",
                )
                if not started:
                    raise
            finally:
                self.socket = None
        yield self._worker_lost_event()
        self.observe("typed_failure", "external_worker_lost", 1)

    async def _endpoint_status(self) -> ExternalPiWorkerStatus:
        if self.worker_status_resolver is not None:
            return await self.worker_status_resolver()
        endpoint = self.external_worker_endpoint
        base_url = (
            endpoint.base_url
            if endpoint is not None
            else self.settings.chat_external_pi_worker_url
        )
        token = (
            endpoint.token
            if endpoint is not None
            else self.settings.chat_external_pi_worker_token
        )
        async with httpx.AsyncClient() as http:
            return await ExternalPiWorkerControlClient(
                base_url=base_url,
                token=token,
                http=http,
            ).status()

    def _external_worker_socket(self, claim: ExternalWorkerClaim):
        """Build the shared fenced transport for run, attach, and cancel."""
        endpoint = self.external_worker_endpoint
        base_url = (
            endpoint.base_url
            if endpoint is not None
            else self.settings.chat_external_pi_worker_url
        )
        token = (
            endpoint.token
            if endpoint is not None
            else self.settings.chat_external_pi_worker_token
        )
        return self.websocket_connector(
            _worker_websocket_url(base_url),
            additional_headers={
                "Authorization": f"Bearer {token}",
                "X-PWC-Worker-Generation": str(claim.generation),
            },
            max_size=MAX_EXTERNAL_TURN_FRAME_BYTES,
            open_timeout=self.settings.chat_external_pi_startup_timeout_seconds,
            ping_interval=20,
            ping_timeout=20,
        )

    async def _select_worker_claim(self) -> ExternalWorkerClaim:
        try:
            endpoints = external_worker_endpoints(self.settings)
        except ValueError:
            endpoints = ()
        admission_reservation = self.admission.external_worker_reservation
        if admission_reservation is not None:
            if (
                admission_reservation.turn_id != self.admission.turn_id
                or admission_reservation.endpoint not in endpoints
                or admission_reservation.worker_claim.worker_id
                != admission_reservation.endpoint.worker_id
            ):
                raise StaleWorkerClaim(
                    "External worker admission reservation mismatches"
                )
            self.external_worker_endpoint = admission_reservation.endpoint
            return admission_reservation.worker_claim
        if endpoints:
            capacity = (
                self.worker_capacity_repository
                or ChatExternalWorkerCapacityRepository(
                    environment=self.settings.environment
                )
            )
            reservation = await asyncio.to_thread(
                self._require_reserved_worker, capacity, endpoints
            )
            self.worker_capacity_repository = capacity
            self.external_worker_endpoint = reservation.endpoint
            status = await self._endpoint_status()
            status_claim = ExternalWorkerClaim(
                worker_id=status.worker_id,
                instance_id=status.instance_id,
                generation=status.worker_generation or 0,
                release_id=status.release_id,
                contract_version=status.protocol,
            )
            if (
                status_claim != reservation.worker_claim
                or status.state != "ready"
                or status.maximum_sessions != reservation.maximum_sessions
            ):
                raise StaleWorkerClaim("External worker endpoint identity mismatches")
            await asyncio.to_thread(
                self._require_live_worker_claim, reservation.worker_claim
            )
            return reservation.worker_claim
        status = await self._endpoint_status()
        if status.active_sessions >= status.maximum_sessions:
            self.observe("capacity_saturation", None, 1)
        if (
            status.worker_generation is None
            or status.state != "ready"
            or status.active_sessions >= status.maximum_sessions
        ):
            raise WorkerLeaseUnavailable("External worker is not ready")
        endpoint_claim = ExternalWorkerClaim(
            worker_id=status.worker_id,
            instance_id=status.instance_id,
            generation=status.worker_generation,
            release_id=status.release_id,
            contract_version=status.protocol,
        )
        return await asyncio.to_thread(self._select_ready_worker_claim, endpoint_claim)

    async def _require_same_external_worker_claim(
        self, claim: ExternalWorkerClaim
    ) -> None:
        status = await self._endpoint_status()
        endpoint_claim = ExternalWorkerClaim(
            worker_id=status.worker_id,
            instance_id=status.instance_id,
            generation=status.worker_generation or 0,
            release_id=status.release_id,
            contract_version=status.protocol,
        )
        if endpoint_claim != claim or status.state not in {"ready", "draining"}:
            raise StaleWorkerClaim("External worker claim was fenced")
        await asyncio.to_thread(self._require_live_worker_claim, claim)

    def _require_reserved_worker(
        self,
        capacity: ChatExternalWorkerCapacityRepository | Any,
        endpoints: tuple[ExternalWorkerEndpoint, ...],
    ):
        with self.session_factory() as db:
            return capacity.require_turn(
                db,
                turn_id=self.admission.turn_id,
                endpoints=endpoints,
                now=self.now(),
            )

    def _require_live_worker_claim(self, claim: ExternalWorkerClaim) -> None:
        with self.session_factory() as db:
            self.worker_repository.require_live_claim(
                db,
                claim=claim,
                now=self.now(),
            )

    def _select_ready_worker_claim(
        self, endpoint_claim: ExternalWorkerClaim
    ) -> ExternalWorkerClaim:
        with self.session_factory() as db:
            claim = self.worker_repository.select_ready_claim(
                db,
                claim=endpoint_claim,
                now=self.now(),
            )
            self.worker_repository.require_ready_claim(
                db,
                claim=claim,
                now=self.now(),
            )
            return claim

    @staticmethod
    def _worker_lost_event() -> dict[str, object]:
        return {
            "type": "error",
            "code": "external_worker_lost",
            "message": "The research run was interrupted.",
        }

    def _turn_claim_frame(self) -> dict[str, object]:
        durable_claim = self.admission.durable_claim
        if (
            durable_claim is None
            or durable_claim.turn_id != self.admission.turn_id
            or self.external_worker_claim is None
        ):
            raise RuntimeError("External Pi turn requires the durable turn claim")
        return {
            "turnId": str(durable_claim.turn_id),
            "workerId": durable_claim.worker_id,
            "workerGeneration": str(durable_claim.worker_generation),
            "leaseGeneration": str(durable_claim.lease_generation),
        }

    def _attach_frame(self, after_sequence: int) -> dict[str, object]:
        return {
            "v": 1,
            "type": "attach_turn",
            "request_id": self.request_id,
            "turnClaim": self._turn_claim_frame(),
            "afterSequence": after_sequence,
        }

    def _terminal_ack_frame(self, sequence: int) -> dict[str, object]:
        return {
            "v": 1,
            "type": "ack_terminal",
            "request_id": self.request_id,
            "turnClaim": self._turn_claim_frame(),
            "sequence": sequence,
        }

    def _run_frame(self) -> dict[str, object]:
        prebound_agent_session_id = (
            self.admission.sdk_session_id
            if self.admission.is_first_turn
            and not self.admission.is_replacement
            and self.resume_id in {None, self.admission.sdk_session_id}
            else None
        )
        frame = {
            "v": 1,
            "type": "run_turn",
            "request_id": self.request_id,
            "chat_session_id": str(self.admission.session_id),
            "turn_id": str(self.admission.turn_id),
            "turnClaim": self._turn_claim_frame(),
            "prompt": self.prompt,
            "model": self.settings.chat_route_provider_models[
                self.admission.model_route
            ],
            "provider_protocol": self.settings.chat_route_protocols[
                self.admission.model_route
            ],
            "resume": (
                None
                if prebound_agent_session_id is not None
                else str(self.resume_id)
                if self.resume_id
                else None
            ),
            "web_search_enabled": self.admission.web_search_enabled,
            "excalidraw_enabled": (
                self.settings.chat_excalidraw_enabled
                and self.settings.chat_mcp_apps_host_enabled
            ),
            "reader_mode": self.admission.reader_mode,
            "poster_mode": self.admission.poster_mode,
            "paper_artifacts_enabled": self.admission.paper_artifacts_enabled,
            "reasoning_effort": self.admission.reasoning_effort,
            "fetchable_urls": list(self.admission.fetchable_urls),
            "hf_username": self.hf_username,
            "agent_harness": "pi",
            "capability": self.capability.token,
            "gateway_url": self.settings.chat_gateway_url,
        }
        if self.admission.paper_descriptor is not None:
            frame["paper_descriptor"] = self.admission.paper_descriptor
        if prebound_agent_session_id is not None:
            frame["agent_session_id"] = str(prebound_agent_session_id)
        return frame

    @staticmethod
    def _decode(raw: str | bytes) -> dict[str, object]:
        if isinstance(raw, bytes):
            if len(raw) > MAX_EXTERNAL_TURN_FRAME_BYTES:
                raise RuntimeError("External Pi frame is too large")
            raw = raw.decode("utf-8")
        elif len(raw.encode("utf-8")) > MAX_EXTERNAL_TURN_FRAME_BYTES:
            raise RuntimeError("External Pi frame is too large")
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise RuntimeError("External Pi frame is invalid")
        return value

    async def _tool_result(self, request: dict[str, object]) -> dict[str, object]:
        return await self.tool_executor.tool_result(request)

    async def _execute_tool_result(
        self,
        request: dict[str, object],
        *,
        operation_id: str,
        operation: str,
    ) -> dict[str, object]:
        stale_boundary = QualificationStaleFenceBoundary(
            turn_id=self.admission.turn_id,
            chat_session_id=self.admission.session_id,
            recorder=self.record_evidence,
        )
        return await stale_boundary.call(
            self.tool_executor._execute(
                request,
                operation_id=operation_id,
                operation=operation,
                stale_boundary=stale_boundary,
            )
        )

    async def _persist_turn_state(self, state: str) -> None:
        await self.lifecycle.persist_turn_state(state)

    async def _cancel_executor(self, context: ExecutorContext) -> bool:
        binding = self.tool_executor._binding
        return await self.tool_executor.cancel_executor(
            context,
            channel=binding.channel if binding is not None else None,
        )

    def _durable_turn_claim(self) -> TurnLeaseClaim:
        return self.tool_executor._durable_turn_claim()

    @property
    def active_context(self):
        return self.tool_executor.active_context

    @active_context.setter
    def active_context(self, value) -> None:
        self.tool_executor.active_context = value

    def _revoke(self) -> None:
        self.lifecycle.capability_id = self.capability_id
        self.lifecycle.revoke()
        self.capability_id = self.lifecycle.capability_id

    async def cancel(self) -> CancelControlResult:
        cancel_frame = {
            "v": 1,
            "type": "cancel_turn",
            "request_id": self.request_id,
            "turnClaim": self._turn_claim_frame(),
        }
        socket = self.socket
        context = self.active_context

        async def cancel_worker() -> bool:
            try:
                async with asyncio.timeout(self.cancel_timeout_seconds):
                    if socket is not None:
                        await socket.send(
                            json.dumps(cancel_frame, separators=(",", ":"))
                        )
                        return True
                    if self.external_worker_claim is not None:
                        await self._require_same_external_worker_claim(
                            self.external_worker_claim
                        )
                        async with self._external_worker_socket(
                            self.external_worker_claim
                        ) as detached_socket:
                            await detached_socket.send(
                                json.dumps(cancel_frame, separators=(",", ":"))
                            )
                            return True
            except (OSError, TimeoutError, WebSocketException):
                return False
            except (
                StaleWorkerClaim,
                WorkerLeaseUnavailable,
                ExternalPiWorkerUnavailable,
                ExternalPiWorkerControlRejected,
                httpx.HTTPError,
            ):
                return False
            return False

        async def cancel_executor() -> None:
            if context is None and self.tool_executor._binding is None:
                return
            try:
                async with asyncio.timeout(self.cancel_timeout_seconds):
                    if self.tool_executor._binding is not None:
                        await self.tool_executor.cancel_active()
                    elif context is not None:
                        await self._cancel_executor(context)
            except TimeoutError:
                return

        worker_result, executor_result = await asyncio.gather(
            cancel_worker(), cancel_executor(), return_exceptions=True
        )
        if isinstance(executor_result, Exception):
            raise executor_result
        if isinstance(worker_result, Exception):
            raise worker_result
        return (
            CancelControlResult.REQUESTED
            if worker_result is True
            else CancelControlResult.MISSING
        )

    async def close(self) -> None:
        self._revoke()
