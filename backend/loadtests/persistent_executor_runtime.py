"""Real-process Task 0 fixture for turn-scoped capability and cancellation.

This is deliberately a bounded feasibility seam.  It executes real process
groups and proves the locking/capability lifetime before the same contract is
integrated into the sandbox daemon in Task 7.
"""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

MAX_PARALLEL_OPERATIONS = 4
MAX_CAPTURE_BYTES_PER_OPERATION = 64 * 1024


class TurnRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OperationResult:
    operation_id: str
    status: str
    exit_code: int | None
    output: bytes
    started_at: float | None
    terminal_at: float
    cancellation_observed_at: float | None
    process_contained_at: float | None


@dataclass(frozen=True, slots=True)
class TurnContainmentEvidence:
    cancellation_requested_at: float
    capability_revoked_at: float | None
    sandbox_termination_requested_at: float | None
    sandbox_termination_confirmed_at: float | None
    reservation_retained: bool
    unknown_outcome: bool


@dataclass(slots=True)
class _Operation:
    operation_id: str
    process: subprocess.Popen[bytes] | None = None
    started_at: float | None = None
    cancellation_observed_at: float | None = None
    process_contained_at: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    termination_lock: threading.Lock = field(default_factory=threading.Lock)


class TurnExecutionRuntime:
    """One exclusive turn binding with four independently executed processes."""

    def __init__(
        self,
        *,
        broker: Callable[[str, str], bool],
        sandbox_terminator: Callable[[], bool],
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        terminate_grace_seconds: float = 0.05,
    ) -> None:
        self._broker = broker
        self._sandbox_terminator = sandbox_terminator
        self._wall_clock = wall_clock
        self._monotonic = monotonic_clock
        self._terminate_grace = terminate_grace_seconds
        self._condition = threading.Condition()
        self._watchdog_wakeup = threading.Event()
        self._capability: str | None = None
        self._deadline_monotonic: float | None = None
        self._active: dict[str, _Operation] = {}
        self._terminal_ids: set[str] = set()
        self._accepting = False
        self._teardown_started = False
        self._revoked = False
        self._watchdog: threading.Thread | None = None
        self._containment: TurnContainmentEvidence | None = None

    def authorize(self, capability: str, *, absolute_deadline_unix: float) -> None:
        if not capability or absolute_deadline_unix <= self._wall_clock():
            raise TurnRuntimeError("turn authorization is invalid")
        # Converting once prevents later wall-clock movement from extending the
        # authorization. Subtracting elapsed conversion time is conservative.
        monotonic_deadline = self._monotonic() + max(
            0.0, absolute_deadline_unix - self._wall_clock()
        )
        with self._condition:
            if self._capability is not None:
                raise TurnRuntimeError("turn is already authorized")
            if not self._broker("install", capability):
                raise TurnRuntimeError("capability installation failed")
            self._capability = capability
            self._deadline_monotonic = monotonic_deadline
            self._accepting = True
            self._watchdog = threading.Thread(
                target=self._watch_deadline,
                name="executor-turn-deadline-watchdog",
                daemon=True,
            )
            self._watchdog.start()

    def execute(
        self, operation_id: str, command: str, *, timeout_seconds: float = 30
    ) -> OperationResult:
        operation = _Operation(operation_id=operation_id)
        with self._condition:
            if operation_id in self._active or operation_id in self._terminal_ids:
                raise TurnRuntimeError("operation identity was already used")
            while self._accepting and len(self._active) >= MAX_PARALLEL_OPERATIONS:
                self._condition.wait(timeout=0.01)
            if not self._accepting:
                return OperationResult(
                    operation_id=operation_id,
                    status="cancelled",
                    exit_code=None,
                    output=b"",
                    started_at=None,
                    terminal_at=self._monotonic(),
                    cancellation_observed_at=self._monotonic(),
                    process_contained_at=None,
                )
            self._active[operation_id] = operation

        result: OperationResult
        try:
            process = subprocess.Popen(
                ["/bin/bash", "-lc", command],
                env={
                    "HOME": "/tmp",
                    "LANG": "C.UTF-8",
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                },
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                bufsize=0,
            )
            with self._condition:
                operation.process = process
                operation.started_at = self._monotonic()
                self._condition.notify_all()
            if operation.cancel.is_set():
                operation.cancellation_observed_at = self._monotonic()
                self._terminate(operation)
            output = self._drain(operation, timeout_seconds)
            if operation.cancel.is_set():
                # Synchronize with a concurrent cancel thread before publishing
                # the result so containment proof cannot lag terminal state.
                self._terminate(operation)
                status = "cancelled"
                exit_code = None
            elif process.returncode == 0:
                status = "completed"
                exit_code = 0
            else:
                status = "failed"
                exit_code = process.returncode
            result = OperationResult(
                operation_id=operation_id,
                status=status,
                exit_code=exit_code,
                output=output,
                started_at=operation.started_at,
                terminal_at=self._monotonic(),
                cancellation_observed_at=operation.cancellation_observed_at,
                process_contained_at=operation.process_contained_at,
            )
        except OSError:
            if operation.process is not None:
                self._terminate(operation)
            result = OperationResult(
                operation_id=operation_id,
                status="failed",
                exit_code=None,
                output=b"",
                started_at=operation.started_at,
                terminal_at=self._monotonic(),
                cancellation_observed_at=operation.cancellation_observed_at,
                process_contained_at=operation.process_contained_at,
            )
        finally:
            with self._condition:
                self._active.pop(operation_id, None)
                self._terminal_ids.add(operation_id)
                self._condition.notify_all()
        return result

    def cancel(
        self, *, transport_connected: bool, remote_acknowledged: bool
    ) -> TurnContainmentEvidence:
        requested_at = self._monotonic()
        with self._condition:
            if self._teardown_started:
                while self._containment is None:
                    self._condition.wait(timeout=0.01)
                return self._containment
            self._accepting = False
            self._teardown_started = True
            operations = tuple(self._active.values())
            for operation in operations:
                operation.cancel.set()
            self._condition.notify_all()
        termination_requested_at: float | None = None
        termination_confirmed_at: float | None = None
        unknown = False
        reservation_retained = False
        revoked_at: float | None = None
        try:
            for operation in operations:
                if operation.process is not None:
                    if operation.cancellation_observed_at is None:
                        operation.cancellation_observed_at = self._monotonic()
                    self._terminate(operation)
            if not transport_connected or not remote_acknowledged:
                termination_requested_at = self._monotonic()
                if self._sandbox_terminator():
                    termination_confirmed_at = self._monotonic()
                else:
                    unknown = True
                    reservation_retained = True
            revoked_at = self._finish_teardown()
            if revoked_at is None:
                unknown = True
                reservation_retained = True
        except Exception:
            # Teardown is an external-failure boundary. Publish fail-closed
            # evidence so concurrent callers cannot wait forever.
            unknown = True
            reservation_retained = True
        finally:
            evidence = TurnContainmentEvidence(
                cancellation_requested_at=requested_at,
                capability_revoked_at=revoked_at,
                sandbox_termination_requested_at=termination_requested_at,
                sandbox_termination_confirmed_at=termination_confirmed_at,
                reservation_retained=reservation_retained,
                unknown_outcome=unknown,
            )
            with self._condition:
                self._containment = evidence
                self._condition.notify_all()
        return evidence

    def close(self) -> TurnContainmentEvidence:
        return self.cancel(transport_connected=True, remote_acknowledged=True)

    def wait_until_running(self, count: int, *, timeout_seconds: float) -> bool:
        if not 0 < count <= MAX_PARALLEL_OPERATIONS:
            raise ValueError("running operation count is out of range")
        deadline = self._monotonic() + timeout_seconds
        with self._condition:
            while (
                sum(item.process is not None for item in self._active.values()) < count
            ):
                remaining = deadline - self._monotonic()
                if remaining <= 0 or not self._accepting:
                    return False
                self._condition.wait(timeout=min(remaining, 0.01))
            return True

    def _watch_deadline(self) -> None:
        while True:
            with self._condition:
                deadline = self._deadline_monotonic
                if deadline is None or self._teardown_started:
                    return
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                self.cancel(transport_connected=False, remote_acknowledged=False)
                return
            self._watchdog_wakeup.wait(timeout=min(remaining, 0.05))
            self._watchdog_wakeup.clear()

    def _finish_teardown(self) -> float | None:
        with self._condition:
            while self._active:
                self._condition.wait(timeout=0.01)
            capability = self._capability
            if capability is None or self._revoked:
                return None
            if not self._broker("clear", capability):
                return None
            self._revoked = True
            revoked_at = self._monotonic()
            self._watchdog_wakeup.set()
            return revoked_at

    def _drain(self, operation: _Operation, timeout_seconds: float) -> bytes:
        process = operation.process
        assert process is not None and process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        captured = bytearray()
        operation_deadline = self._monotonic() + timeout_seconds
        try:
            while True:
                if operation.cancel.is_set() or self._monotonic() >= operation_deadline:
                    if operation.cancellation_observed_at is None:
                        operation.cancellation_observed_at = self._monotonic()
                    operation.cancel.set()
                    self._terminate(operation)
                for key, _ in selector.select(0.01):
                    chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                    if chunk:
                        remaining = MAX_CAPTURE_BYTES_PER_OPERATION - len(captured)
                        captured.extend(chunk[:remaining])
                    else:
                        selector.unregister(key.fileobj)
                if process.poll() is not None and not selector.get_map():
                    break
            return bytes(captured)
        finally:
            selector.close()
            process.stdout.close()

    def _terminate(self, operation: _Operation) -> None:
        with operation.termination_lock:
            process = operation.process
            if process is None or process.poll() is not None:
                if operation.process_contained_at is None:
                    operation.process_contained_at = self._monotonic()
                return
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = self._monotonic() + self._terminate_grace
            while process.poll() is None and self._monotonic() < deadline:
                time.sleep(0.001)
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=max(1.0, self._terminate_grace * 4))
            operation.process_contained_at = self._monotonic()
