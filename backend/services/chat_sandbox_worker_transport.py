"""In-process worker controls and process registries for chat sandboxes."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Protocol

from backend.chat_sandbox_worker.protocol import (
    FRAME_PREFIX,
    MAX_WIRE_FRAME_BYTES,
    ProtocolError,
    WorkerEventValidator,
    decode_frame,
    encode_frame,
)
from backend.chat_sandbox_worker.supervisor import SUPERVISOR_PREFIX
from backend.services.chat_sandbox_provider import (
    SandboxError,
    sanitized_failure_class,
    sanitized_failure_stage,
)
from backend.services.chat_sandbox_state_repository import WorkerClaim

logger = logging.getLogger(__name__)


class _SandboxIdentity(Protocol):
    object_id: str


class WorkerTransportProvider(Protocol):
    async def open_persistent_connection(
        self, sandbox: object, worker_generation: str
    ) -> object: ...

    async def open_turn_process(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object: ...


class WorkerTurnMode(StrEnum):
    PERSISTENT = "persistent"
    ONE_SHOT = "one_shot"


class WorkerTurnMilestone(Enum):
    AGENT_READY = "agent_ready"
    SDK_DISPATCHED = "sdk_dispatched"
    FIRST_DELTA = "first_delta"
    CANCELLED = "cancelled"


class WorkerTurnDispatchOutcome(StrEnum):
    DISPATCHED = "dispatched"
    CANCELLED = "cancelled"


class WorkerCancelStatus(StrEnum):
    NOT_FOUND = "not_found"
    PENDING = "pending"
    COMPLETED = "completed"
    CONTROL_LOST = "control_lost"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class WorkerTurnRequest:
    chat_session_id: uuid.UUID
    turn_id: uuid.UUID
    request_id: str
    prompt: str = field(repr=False)
    model: str
    resume: str | None
    capability_token: str = field(repr=False)
    gateway_url: str
    provider_protocol: str = "anthropic-messages"
    agent_harness: str = "claude"
    web_search_enabled: bool = False
    reader_mode: bool = False
    poster_mode: bool = False
    paper_artifacts_enabled: bool = False
    paper_descriptor: dict[str, object] | None = None
    reasoning_effort: str = "high"
    fetchable_urls: tuple[str, ...] = ()
    hf_username: str = "unknown"


@dataclass
class RunningWorker:
    process: object
    request_id: str
    claim: WorkerClaim = field(repr=False)
    cancel_requested: bool = False
    done: asyncio.Event | None = None


@dataclass(frozen=True)
class WorkerCancelOutcome:
    status: WorkerCancelStatus
    turn_id: uuid.UUID
    request_id: str | None
    claim: WorkerClaim | None = field(repr=False)
    _running: RunningWorker | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class BlankStartupMetrics:
    broker_ready_ms: int
    control_ready_ms: int
    agent_spawn_ms: int | None
    agent_startup_ready_ms: int | None
    agent_prestarted: bool


@dataclass
class SessionControl:
    process: object
    sandbox: object
    sandbox_id: str
    stderr_task: asyncio.Task | None
    reader_task: asyncio.Task | None
    queues: dict[str, asyncio.Queue]
    resume_id: str | None
    close_scheduled: bool = False


class _WebSocketDrain:
    def __init__(self, writer: _WebSocketWriter):
        self._writer = writer

    async def aio(self) -> None:
        await self._writer.flush()


class _WebSocketWriter:
    def __init__(self, connection: object):
        self._connection = connection
        self._pending = bytearray()
        self.drain = _WebSocketDrain(self)

    def write(self, data: bytes) -> None:
        self._pending.extend(data)

    async def flush(self) -> None:
        if not self._pending:
            return
        payload = bytes(self._pending)
        self._pending.clear()
        await self._connection.send(payload)


class _WebSocketProcess:
    def __init__(self, connection: object):
        self._connection = connection
        self.stdin = _WebSocketWriter(connection)
        self.stdout = connection

    async def aclose(self) -> None:
        await self._connection.close()


async def _framed_events(stream: object) -> AsyncIterator[dict]:
    buffer = b""
    async for chunk in stream:
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if not line or not line.startswith(FRAME_PREFIX.encode()):
                continue
            yield decode_frame(line)
        if len(buffer) > MAX_WIRE_FRAME_BYTES:
            raise ProtocolError("Worker stream frame is too large")


class ChatSandboxWorkerTransport:
    """Own live worker controls without owning provider or persistence policy."""

    def __init__(
        self,
        provider: WorkerTransportProvider,
        *,
        clock=time.monotonic,
    ):
        self.provider = provider
        self.clock = clock
        self.processes: dict[uuid.UUID, RunningWorker] = {}
        self.deferred_cancellations: set[uuid.UUID] = set()
        self.session_controls: dict[uuid.UUID, SessionControl] = {}
        self.blank_controls: dict[str, SessionControl] = {}
        self.blank_health_at: dict[str, float] = {}
        self.blank_startup: dict[str, BlankStartupMetrics] = {}
        self.close_tasks: set[asyncio.Task] = set()

    async def open_persistent_control(
        self, sandbox: _SandboxIdentity, worker_generation: str
    ) -> SessionControl:
        connection = await self.provider.open_persistent_connection(
            sandbox, worker_generation
        )
        process = _WebSocketProcess(connection)
        control = SessionControl(
            process=process,
            sandbox=sandbox,
            sandbox_id=sandbox.object_id,
            stderr_task=None,
            reader_task=None,
            queues={},
            resume_id=None,
        )
        control.reader_task = asyncio.create_task(self.read_control(control))
        return control

    async def open_turn_process(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object:
        return await self.provider.open_turn_process(
            sandbox, timeout_seconds=timeout_seconds
        )

    async def ping(self, control: SessionControl, worker_generation: str) -> bool:
        request_id = f"health-{uuid.uuid4()}"
        queue: asyncio.Queue = asyncio.Queue()
        control.queues[request_id] = queue
        try:
            control.process.stdin.write(
                SUPERVISOR_PREFIX
                + json.dumps(
                    {
                        "operation": "ping",
                        "worker_generation": worker_generation,
                        "request_id": request_id,
                    },
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )
            await control.process.stdin.drain.aio()
            async with asyncio.timeout(5):
                response = await queue.get()
            healthy = bool(
                isinstance(response, dict)
                and response.get("type") == "worker_health"
                and response.get("request_id") == request_id
                and response.get("assigned") is False
            )
            if not healthy:
                return False
            startup = response.get("startup_metrics")
            if startup is None:
                return True
            metrics = self._startup_metrics(
                startup,
                agent_prestarted=response.get("agent_prestarted"),
            )
            if metrics is None:
                return False
            self.blank_startup[control.sandbox_id] = metrics
            return True
        except Exception:
            return False
        finally:
            control.queues.pop(request_id, None)

    @staticmethod
    def _startup_metrics(
        value: object, *, agent_prestarted: object
    ) -> BlankStartupMetrics | None:
        if not isinstance(value, dict) or set(value) != {
            "broker_ready_ms",
            "control_ready_ms",
            "agent_spawn_ms",
            "agent_startup_ready_ms",
        }:
            return None
        if not isinstance(agent_prestarted, bool):
            return None
        required = (value["broker_ready_ms"], value["control_ready_ms"])
        optional = (value["agent_spawn_ms"], value["agent_startup_ready_ms"])
        if any(
            isinstance(item, bool)
            or not isinstance(item, int)
            or not 0 <= item <= 3_600_000
            for item in required
        ):
            return None
        if any(
            item is not None
            and (
                isinstance(item, bool)
                or not isinstance(item, int)
                or not 0 <= item <= 3_600_000
            )
            for item in optional
        ):
            return None
        broker_ready_ms, control_ready_ms = required
        agent_spawn_ms, agent_startup_ready_ms = optional
        if broker_ready_ms > control_ready_ms:
            return None
        if agent_prestarted:
            if agent_spawn_ms is None or agent_startup_ready_ms is None:
                return None
            if not control_ready_ms <= agent_spawn_ms <= agent_startup_ready_ms:
                return None
        elif agent_spawn_ms is not None or agent_startup_ready_ms is not None:
            return None
        return BlankStartupMetrics(
            broker_ready_ms=broker_ready_ms,
            control_ready_ms=control_ready_ms,
            agent_spawn_ms=agent_spawn_ms,
            agent_startup_ready_ms=agent_startup_ready_ms,
            agent_prestarted=agent_prestarted,
        )

    def blank_startup_metrics(self, sandbox_id: str) -> BlankStartupMetrics | None:
        return self.blank_startup.get(sandbox_id)

    async def read_control(self, control: SessionControl) -> None:
        failure: BaseException | None = None
        try:
            async for event in _framed_events(control.process.stdout):
                request_id = str(event.get("request_id") or "")
                queue = control.queues.get(request_id)
                if queue is None:
                    raise ProtocolError("Uncorrelated persistent worker frame")
                await queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failure = error
        finally:
            if failure is None:
                failure = SandboxError(
                    "sandbox_worker_failed",
                    "The persistent worker control stream ended",
                    uncertain=True,
                    failure_stage="agent_stream",
                    failure_class="ControlStreamEnded",
                )
            for queue in list(control.queues.values()):
                await queue.put(failure)

    def reusable_sandbox(
        self, chat_session_id: uuid.UUID, resume_id: str | None
    ) -> object | None:
        control = self.session_control(chat_session_id)
        if control is None:
            return None
        if (
            resume_id is not None
            and control.resume_id is not None
            and control.resume_id != resume_id
        ):
            control.resume_id = None
        return control.sandbox

    def create_execution(
        self,
        sandbox: object,
        claim: WorkerClaim,
        request: WorkerTurnRequest,
        mode: WorkerTurnMode,
        *,
        process_timeout_seconds: int,
    ) -> WorkerTurnExecution:
        return WorkerTurnExecution(
            self,
            sandbox=sandbox,
            claim=claim,
            request=request,
            mode=mode,
            process_timeout_seconds=process_timeout_seconds,
        )

    async def signal_cancel(self, running: RunningWorker) -> None:
        running.cancel_requested = True
        running.process.stdin.write(
            encode_frame(
                {
                    "v": 1,
                    "type": "cancel",
                    "request_id": running.request_id,
                }
            )
        )
        await running.process.stdin.drain.aio()

    async def cancel(
        self, turn_id: uuid.UUID, *, grace_seconds: float
    ) -> WorkerCancelOutcome:
        running = self.running_worker(turn_id)
        if running is None:
            return WorkerCancelOutcome(
                WorkerCancelStatus.NOT_FOUND,
                turn_id,
                None,
                None,
            )
        try:
            await self.signal_cancel(running)
        except Exception:
            return WorkerCancelOutcome(
                WorkerCancelStatus.CONTROL_LOST,
                turn_id,
                running.request_id,
                running.claim,
                running,
            )
        try:
            async with asyncio.timeout(grace_seconds):
                if running.done is not None:
                    await running.done.wait()
                else:
                    await running.process.wait.aio()
        except TimeoutError:
            return WorkerCancelOutcome(
                WorkerCancelStatus.TIMED_OUT,
                turn_id,
                running.request_id,
                running.claim,
                running,
            )
        return WorkerCancelOutcome(
            WorkerCancelStatus.COMPLETED,
            turn_id,
            running.request_id,
            running.claim,
            running,
        )

    @staticmethod
    def complete_control_loss(outcome: WorkerCancelOutcome) -> None:
        if outcome.status is not WorkerCancelStatus.CONTROL_LOST:
            raise ValueError("Only a lost cancellation control can be completed")
        running = outcome._running
        if running is not None and running.done is not None:
            running.done.set()

    def running_workers(self) -> tuple[RunningWorker, ...]:
        return tuple(self.processes.values())

    def running_worker(self, turn_id: uuid.UUID) -> RunningWorker | None:
        return self.processes.get(turn_id)

    def register_running_worker(
        self, turn_id: uuid.UUID, running: RunningWorker
    ) -> None:
        if turn_id in self.deferred_cancellations:
            self.deferred_cancellations.remove(turn_id)
            running.cancel_requested = True
        self.processes[turn_id] = running

    def defer_cancel(self, turn_id: uuid.UUID) -> None:
        """Fence a turn that has not registered worker control yet."""
        running = self.processes.get(turn_id)
        if running is not None:
            running.cancel_requested = True
            return
        self.deferred_cancellations.add(turn_id)

    def clear_deferred_cancel(self, turn_id: uuid.UUID) -> None:
        self.deferred_cancellations.discard(turn_id)

    def remove_running_worker(
        self, turn_id: uuid.UUID, *, expected: RunningWorker
    ) -> RunningWorker | None:
        running = self.processes.get(turn_id)
        if running is not expected:
            return None
        return self.processes.pop(turn_id)

    def session_control(self, chat_session_id: uuid.UUID) -> SessionControl | None:
        return self.session_controls.get(chat_session_id)

    def register_session_control(
        self, chat_session_id: uuid.UUID, control: SessionControl
    ) -> None:
        self.session_controls[chat_session_id] = control

    def blank_control(self, sandbox_id: str) -> SessionControl | None:
        return self.blank_controls.get(sandbox_id)

    def register_blank_control(
        self,
        sandbox_id: str,
        control: SessionControl,
        *,
        checked_at: float | None = None,
    ) -> None:
        self.blank_controls[sandbox_id] = control
        self.blank_health_at[sandbox_id] = (
            self.clock() if checked_at is None else checked_at
        )

    def blank_health_checked_at(self, sandbox_id: str) -> float | None:
        return self.blank_health_at.get(sandbox_id)

    def mark_blank_healthy(
        self,
        sandbox_id: str,
        *,
        expected: SessionControl,
        checked_at: float | None = None,
    ) -> bool:
        control = self.blank_controls.get(sandbox_id)
        if control is not expected:
            return False
        self.blank_health_at[sandbox_id] = (
            self.clock() if checked_at is None else checked_at
        )
        return True

    def promote_blank_control(
        self,
        sandbox_id: str,
        chat_session_id: uuid.UUID,
        *,
        expected: SessionControl,
    ) -> SessionControl | None:
        control = self.blank_controls.get(sandbox_id)
        if control is None or control is not expected:
            return None
        self.blank_controls.pop(sandbox_id)
        self.blank_health_at.pop(sandbox_id, None)
        self.blank_startup.pop(sandbox_id, None)
        if control is not None:
            self.session_controls[chat_session_id] = control
        return control

    def drop_session_control(
        self,
        chat_session_id: uuid.UUID,
        *,
        expected: SessionControl | None = None,
    ) -> SessionControl | None:
        control = self.session_controls.get(chat_session_id)
        if control is None or (expected is not None and control is not expected):
            return None
        self.session_controls.pop(chat_session_id)
        self._close_control(control)
        return control

    def drop_session_controls_by_sandbox(self, sandbox_id: str) -> int:
        removed = 0
        for session_id, control in list(self.session_controls.items()):
            if control.sandbox_id != sandbox_id:
                continue
            removed += (
                self.drop_session_control(session_id, expected=control) is not None
            )
        return removed

    def drop_blank_control(
        self,
        sandbox_id: str,
        *,
        expected: SessionControl | None = None,
    ) -> SessionControl | None:
        control = self.blank_controls.get(sandbox_id)
        if control is None or (expected is not None and control is not expected):
            return None
        self.blank_controls.pop(sandbox_id)
        self.blank_health_at.pop(sandbox_id, None)
        self.blank_startup.pop(sandbox_id, None)
        self._close_control(control)
        return control

    def schedule_close(self, control: SessionControl) -> None:
        if control.close_scheduled:
            return
        close = getattr(control.process, "aclose", None)
        if close is None:
            return
        control.close_scheduled = True
        task = asyncio.create_task(close())
        self.close_tasks.add(task)

        def finished(completed: asyncio.Task) -> None:
            self.close_tasks.discard(completed)

        task.add_done_callback(finished)

    def _close_control(self, control: SessionControl) -> None:
        if control.stderr_task is not None:
            control.stderr_task.cancel()
        if control.reader_task is not None:
            control.reader_task.cancel()
        self.schedule_close(control)


class WorkerTurnExecution:
    """One validated worker request from dispatch through exact cleanup."""

    def __init__(
        self,
        transport: ChatSandboxWorkerTransport,
        *,
        sandbox: object,
        claim: WorkerClaim,
        request: WorkerTurnRequest,
        mode: WorkerTurnMode,
        process_timeout_seconds: int,
    ):
        self.transport = transport
        self.sandbox = sandbox
        self.claim = claim
        self.request = request
        self.mode = mode
        self.process_timeout_seconds = process_timeout_seconds
        self.control: SessionControl | None = None
        self.process: object | None = None
        self.queue: asyncio.Queue | None = None
        self.running: RunningWorker | None = None
        self.stderr_task: asyncio.Task | None = None
        self.terminal = False
        self.sdk_dispatched = False
        self.control_connection_opened = False
        self.agent_spawned = False
        self._dispatch_started = False
        self._dispatched = False
        self._closed = False
        self._public_tool_ids: dict[str, str] = {}
        self._next_public_tool_id = 1

    @property
    def cancel_requested(self) -> bool:
        return self.running is not None and self.running.cancel_requested

    async def dispatch(self) -> WorkerTurnDispatchOutcome:
        if self._dispatch_started:
            raise RuntimeError("Worker turn dispatch already started")
        if self._closed:
            raise RuntimeError("Worker turn execution is closed")
        self._dispatch_started = True
        try:
            outcome = await self._dispatch()
        except Exception:
            if self._accept_cancelled_failure():
                return WorkerTurnDispatchOutcome.CANCELLED
            raise
        if outcome is WorkerTurnDispatchOutcome.CANCELLED:
            return outcome
        self._dispatched = True
        return WorkerTurnDispatchOutcome.DISPATCHED

    async def _dispatch(self) -> WorkerTurnDispatchOutcome:
        if self.mode is WorkerTurnMode.PERSISTENT:
            self.control = self.transport.session_control(self.request.chat_session_id)
            if (
                self.control is not None
                and self.control.sandbox_id != self.claim.sandbox_id
            ):
                self.transport.drop_session_control(
                    self.request.chat_session_id,
                    expected=self.control,
                )
                self.control = None
            if self.control is None:
                try:
                    self.control = await self.transport.open_persistent_control(
                        self.sandbox,
                        self.claim.worker_generation,
                    )
                except Exception as error:
                    raise SandboxError(
                        "sandbox_worker_failed",
                        "The persistent worker control could not be opened",
                        uncertain=True,
                        failure_stage="control_open",
                        failure_class=type(error).__name__,
                    ) from error
                self.control_connection_opened = True
                self.transport.register_session_control(
                    self.request.chat_session_id,
                    self.control,
                )
            self.process = self.control.process
            self.stderr_task = self.control.stderr_task
        else:
            self.process = await self.transport.open_turn_process(
                self.sandbox,
                timeout_seconds=self.process_timeout_seconds,
            )
            self.agent_spawned = True
            self.stderr_task = asyncio.create_task(
                self._drain_stderr(self.process.stderr)
            )

        self.running = RunningWorker(
            self.process,
            self.request.request_id,
            self.claim,
            done=asyncio.Event(),
        )
        self.transport.register_running_worker(
            self.request.turn_id,
            self.running,
        )
        if self.mode is WorkerTurnMode.PERSISTENT:
            assert self.control is not None
            if self.request.request_id in self.control.queues:
                error = ProtocolError("Duplicate persistent request identifier")
                error.failure_stage = "queue_registration"
                error.failure_class = "ProtocolError"
                raise error
            self.queue = asyncio.Queue()
            self.control.queues[self.request.request_id] = self.queue

        if self.running.cancel_requested:
            self.running.done.set()
            return WorkerTurnDispatchOutcome.CANCELLED
        try:
            self.process.stdin.write(self._request_frame())
            await self.process.stdin.drain.aio()
        except Exception as error:
            raise SandboxError(
                "sandbox_worker_failed",
                "The persistent worker request could not be dispatched",
                uncertain=True,
                failure_stage="dispatch_write",
                failure_class=type(error).__name__,
            ) from error
        return WorkerTurnDispatchOutcome.DISPATCHED

    def _request_frame(self) -> bytes:
        launch = {
            "capability": self.request.capability_token,
            "gateway_url": self.request.gateway_url,
            "session_id": str(self.request.chat_session_id),
            "turn_id": str(self.request.turn_id),
            "agent_harness": self.request.agent_harness,
        }
        run = {
            "v": 1,
            "type": "run_turn",
            "request_id": self.request.request_id,
            "chat_session_id": str(self.request.chat_session_id),
            "prompt": self.request.prompt,
            "model": self.request.model,
            "resume": self.request.resume,
            "web_search_enabled": self.request.web_search_enabled,
            "reasoning_effort": self.request.reasoning_effort,
            "fetchable_urls": list(self.request.fetchable_urls),
            "hf_username": self.request.hf_username,
            "agent_harness": self.request.agent_harness,
        }
        if self.request.reader_mode:
            # Contract-80 workers reject unknown frame keys. Reader mode was
            # added in contract 81, so omit its false/default value to keep
            # non-reader production turns compatible during image rotation.
            run["reader_mode"] = True
        if (
            self.request.agent_harness == "pi"
            and self.request.provider_protocol != "anthropic-messages"
        ):
            # Contract-90 Pi workers reject unknown frame keys. The default
            # Anthropic-compatible protocol predates this field, so omit it
            # while production drains the older immutable worker image.
            run["provider_protocol"] = self.request.provider_protocol
        if self.request.poster_mode:
            run["poster_mode"] = True
        if self.request.paper_artifacts_enabled:
            run["paper_artifacts_enabled"] = True
            if self.request.paper_descriptor is not None:
                run["paper_descriptor"] = self.request.paper_descriptor
        if self.mode is WorkerTurnMode.PERSISTENT:
            identity = {
                "assignment_token": self.claim.assignment_token,
                "worker_generation": self.claim.worker_generation,
            }
            launch.update(identity)
            run.update(
                {
                    "turn_id": str(self.request.turn_id),
                    **identity,
                }
            )
        return (
            SUPERVISOR_PREFIX
            + json.dumps(launch, separators=(",", ":")).encode()
            + b"\n"
            + encode_frame(run)
        )

    async def events(
        self, *, timeout_seconds: float
    ) -> AsyncIterator[WorkerTurnMilestone | dict]:
        if not self._dispatched:
            raise RuntimeError("Worker turn was not dispatched")
        if self._closed:
            raise RuntimeError("Worker turn execution is closed")
        pending_terminal_event: dict | None = None
        first_worker_delta_recorded = False
        validator = WorkerEventValidator()
        try:
            async with asyncio.timeout(timeout_seconds):
                events = (
                    self._persistent_events()
                    if self.mode is WorkerTurnMode.PERSISTENT
                    else _framed_events(self.process.stdout)
                )
                async for event in events:
                    if event.get("request_id") != self.request.request_id:
                        raise ProtocolError("Uncorrelated worker frame")
                    assert self.running is not None
                    validator.accept(
                        event,
                        allow_terminal_less_stop=self.running.cancel_requested,
                    )
                    if event["type"] == "worker_done":
                        self.terminal = True
                        if self.running.done is not None:
                            self.running.done.set()
                        if event.get("status") == "stopped":
                            yield WorkerTurnMilestone.CANCELLED
                        elif pending_terminal_event is not None:
                            yield self._public_event(pending_terminal_event)
                        break
                    if (
                        self.mode is WorkerTurnMode.PERSISTENT
                        and event["type"] == "_sdk_session"
                    ):
                        assert self.control is not None
                        sdk_session_id = str(event.get("session_id") or "")
                        if (
                            self.control.resume_id is not None
                            and self.control.resume_id != sdk_session_id
                        ):
                            raise ProtocolError(
                                "SDK session changed inside persistent control"
                            )
                        self.control.resume_id = sdk_session_id
                    if self.running.cancel_requested:
                        continue
                    if event["type"] == "worker_ready":
                        # Persistent Pi controls emit readiness for every run so
                        # dispatch can prove that the harness accepted the
                        # correlated request. It is transport-only and must
                        # never reach the browser event schema.
                        yield WorkerTurnMilestone.AGENT_READY
                        continue
                    if event["type"] == "workspace_ready":
                        self.sdk_dispatched = True
                        yield WorkerTurnMilestone.SDK_DISPATCHED
                    if not first_worker_delta_recorded and event["type"] in {
                        "reasoning_delta",
                        "tool_call",
                        "tool_call_start",
                        "answer_delta",
                    }:
                        first_worker_delta_recorded = True
                        yield WorkerTurnMilestone.FIRST_DELTA
                    if event["type"] in {"done", "error", "_mirror_error"}:
                        pending_terminal_event = event
                        continue
                    yield self._public_event(event)
                if self.mode is WorkerTurnMode.ONE_SHOT:
                    await self.process.wait.aio()
            if not self.terminal:
                raise SandboxError(
                    "sandbox_worker_failed",
                    "The secure workspace worker ended unexpectedly",
                    uncertain=True,
                    failure_stage="agent_stream",
                    failure_class="WorkerStreamEnded",
                )
        except Exception:
            if self._accept_cancelled_failure():
                yield WorkerTurnMilestone.CANCELLED
                return
            raise

    async def _persistent_events(self) -> AsyncIterator[dict]:
        assert self.queue is not None
        while True:
            item = await self.queue.get()
            if isinstance(item, BaseException):
                raise item
            if item.get("type") == "_control_failure":
                logger.warning(
                    "persistent worker control failed stage=%s error_class=%s",
                    item.get("stage"),
                    item.get("error_class"),
                )
                raise SandboxError(
                    "sandbox_worker_failed",
                    "The persistent worker control failed",
                    uncertain=True,
                    failure_stage=sanitized_failure_stage(item.get("stage")),
                    failure_class=sanitized_failure_class(item.get("error_class")),
                )
            yield item
            if item.get("type") == "worker_done":
                return

    def _accept_cancelled_failure(self) -> bool:
        if not self.cancel_requested:
            return False
        assert self.running is not None
        if self.running.done is not None:
            self.running.done.set()
        return True

    @staticmethod
    async def _drain_stderr(stream: object) -> None:
        async for _chunk in stream:
            pass

    def _public_event(self, event: dict) -> dict:
        public = {
            key: value for key, value in event.items() if key not in {"v", "request_id"}
        }
        if event.get("type") in {
            "tool_call",
            "tool_call_start",
            "tool_call_arguments_delta",
            "tool_call_arguments_done",
            "tool_result",
            "app_start",
            "app_result",
        }:
            provider_id = str(event.get("id") or "")
            public_id = self._public_tool_ids.get(provider_id)
            if public_id is None:
                public_id = f"tool-{self._next_public_tool_id}"
                self._next_public_tool_id += 1
                self._public_tool_ids[provider_id] = public_id
            public["id"] = public_id
            if event.get("type") == "app_start":
                public["instance_id"] = public_id
        return public

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if (
            self.control is not None
            and self.queue is not None
            and self.control.queues.get(self.request.request_id) is self.queue
        ):
            self.control.queues.pop(self.request.request_id)
        if self.mode is WorkerTurnMode.ONE_SHOT and self.stderr_task is not None:
            self.stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.stderr_task
        if self.running is not None:
            self.transport.remove_running_worker(
                self.request.turn_id,
                expected=self.running,
            )
