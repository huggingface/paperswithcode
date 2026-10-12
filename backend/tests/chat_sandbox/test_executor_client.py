from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import replace

import pytest
from grpclib import GRPCError, Status
from modal.exception import ConnectionError as ModalConnectionError

from backend.chat_sandbox_worker.executor_daemon import (
    EXECUTOR_BOOTSTRAP_PREFIX,
    ExecutorServer,
)
from backend.chat_sandbox_worker.executor_protocol import (
    MAX_EXECUTION_OUTPUT_FRAMES,
    MAX_EXECUTION_RESPONSE_FRAMES,
    PROTOCOL,
    ProtocolError,
    decode_request,
    encode_response,
)
from backend.services.chat_sandbox_executor import (
    MAX_EXECUTOR_RESPONSE_FRAMES,
    ExecutorContext,
    ExecutorExecutionLost,
    ExecutorTransportError,
    SandboxExecutorClient,
)
from backend.tests.chat_sandbox.executor_client_harness import (
    _AsyncCall,
    _Broker,
    _DropFirstResponseSocketProvider,
    _Input,
    _Output,
    _Process,
    _Provider,
    _SocketProvider,
)


IDENTITY = {
    "workspace_id": "workspace-a",
    "workspace_generation": 7,
    "session_id": "session-a",
    "turn_id": "turn-a",
    "execution_id": "execution-a",
    "tool_call_id": "tool-a",
}


class _StallingProcess(_Process):
    def __init__(self, frames: list[dict]):
        super().__init__(frames)
        self.stdout = _StallingOutput([encode_response(frame) for frame in frames])


class _WaitFailureProcess(_Process):
    def __init__(self, frames: list[dict], error: BaseException):
        super().__init__(frames)
        self.wait = _AsyncCall(self._failed_wait)
        self.wait_error = error

    async def _failed_wait(self):
        raise self.wait_error


class _StallingWaitProcess(_Process):
    def __init__(self, frames: list[dict]):
        super().__init__(frames)
        self.wait = _AsyncCall(self._stall_wait)

    async def _stall_wait(self):
        await asyncio.Event().wait()


class _StallingOutput(_Output):
    async def _iterate(self):
        for chunk in self.chunks:
            yield chunk
        await asyncio.Event().wait()


class _FailingProvider:
    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0

    async def open_executor_relay(self, _sandbox, *, timeout_seconds):
        self.calls += 1
        raise self.error


class _PreWriteFailureProcess:
    def __init__(self):
        self.stdin_lookups = 0

    @property
    def stdin(self):
        self.stdin_lookups += 1
        raise ConnectionError("synthetic pre-write failure")


def _context() -> ExecutorContext:
    return ExecutorContext(
        sandbox=object(),
        worker_generation="worker-a",
        capability="synthetic-capability",
        turn_worker_id="production-green-00",
        turn_worker_generation="4",
        turn_lease_generation="9",
        turn_deadline_unix_ms=4_000_000_000_000,
        **IDENTITY,
    )


def _response(kind: str, **fields) -> dict:
    return {
        "protocol": PROTOCOL,
        "type": kind,
        "request_id": "request-a",
        **IDENTITY,
        **fields,
    }


def test_exec_sends_fenced_bootstrap_and_returns_validated_output():
    process = _Process(
        [
            _response("acknowledged", operation="exec"),
            _response("output", sequence=1, stream="stdout", data="synthetic\n"),
            _response("terminal", status="completed", exit_code=0, error=None),
        ]
    )
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")
    context = _context()

    result = asyncio.run(
        client.exec(context, command="pwc paper list", timeout_ms=9000)
    )

    assert result.outputs == (
        {"sequence": 1, "stream": "stdout", "data": "synthetic\n"},
    )
    assert result.terminal == {
        "status": "completed",
        "exit_code": 0,
        "error": None,
    }
    bootstrap_line, request_line = process.stdin.writes[0].splitlines(keepends=True)
    assert bootstrap_line.startswith(EXECUTOR_BOOTSTRAP_PREFIX)
    assert json.loads(bootstrap_line[len(EXECUTOR_BOOTSTRAP_PREFIX) :]) == {
        "operation": "executor_connect",
        "capability": "synthetic-capability",
        "workspace_id": "workspace-a",
        "workspace_generation": 7,
        "session_id": "session-a",
        "turn_id": "turn-a",
        "worker_generation": "worker-a",
        "turn_worker_id": "production-green-00",
        "turn_worker_generation": "4",
        "turn_lease_generation": "9",
        "turn_deadline_unix_ms": 4_000_000_000_000,
    }
    assert decode_request(request_line) == {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-a",
        **IDENTITY,
        "command": "pwc paper list",
        "timeout_ms": 9000,
    }
    assert process.stdin.eof_writes == 1
    assert provider.calls == [(context.sandbox, 14)]


def test_exec_disconnect_after_ack_is_typed_lost_and_is_not_retried():
    process = _Process(
        [_response("acknowledged", operation="exec")],
        error=ConnectionResetError("synthetic disconnect"),
    )
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert exc_info.value.code == "execution_lost"
    assert (
        str(exc_info.value) == "Sandbox execution delivery or completion is uncertain"
    )
    assert len(provider.calls) == 1
    assert len(process.stdin.writes) == 1


def test_exec_lost_exposes_stable_identity_cursor_and_received_output():
    process = _Process(
        [
            _response("acknowledged", operation="exec"),
            _response("output", sequence=1, stream="stdout", data="partial"),
        ],
        error=ConnectionResetError("synthetic disconnect"),
    )
    client = SandboxExecutorClient(
        _Provider([process]), request_id_factory=lambda: "request-a"
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(client.exec(_context(), command="true", timeout_ms=1000))

    assert exc_info.value.execution_id == "execution-a"
    assert exc_info.value.last_sequence == 1
    assert exc_info.value.outputs == (
        {"sequence": 1, "stream": "stdout", "data": "partial"},
    )
    with pytest.raises(AttributeError):
        exc_info.value.execution_id = "replacement"
    with pytest.raises(AttributeError):
        exc_info.value.last_sequence = 99


def test_exec_resumable_does_not_attach_when_payload_was_proven_unsent():
    process = _PreWriteFailureProcess()
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorTransportError):
        asyncio.run(client.exec_resumable(_context(), command="true", timeout_ms=1000))

    assert len(provider.calls) == 1


def test_exec_resumable_accepts_proven_terminal_despite_later_response_loss():
    process = _Process(
        [
            _response("acknowledged", operation="exec"),
            _response("output", sequence=1, stream="stdout", data="complete"),
            _response("terminal", status="completed", exit_code=0, error=None),
        ],
        error=ConnectionResetError("response stream failed after terminal"),
    )
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    result = asyncio.run(
        client.exec_resumable(_context(), command="true", timeout_ms=1000)
    )

    assert result.outputs[0]["data"] == "complete"
    assert result.terminal["status"] == "completed"
    assert len(provider.calls) == 1


def test_exec_resumable_promotes_daemon_execution_lost_terminal_to_exception():
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="exec"),
                    _response(
                        "terminal",
                        status="failed",
                        exit_code=None,
                        error="execution_lost",
                    ),
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(client.exec_resumable(_context(), command="true", timeout_ms=1000))

    assert exc_info.value.code == "execution_lost"
    assert [frame["type"] for frame in exc_info.value.responses] == [
        "acknowledged",
        "terminal",
    ]
    assert len(provider.calls) == 1


def test_exec_resumable_updates_cursor_across_bounded_attachment_losses():
    request_ids = iter(["exec-request", "attach-one", "attach-two"])

    def response(request_id, kind, **fields):
        return {**_response(kind, **fields), "request_id": request_id}

    processes = [
        _Process(
            [
                response("exec-request", "acknowledged", operation="exec"),
                response(
                    "exec-request",
                    "output",
                    sequence=1,
                    stream="stdout",
                    data="one",
                ),
            ],
            error=ConnectionResetError("lost exec response"),
        ),
        _Process(
            [
                response("attach-one", "acknowledged", operation="attach_execution"),
                response(
                    "attach-one",
                    "output",
                    sequence=2,
                    stream="stderr",
                    data="two",
                ),
            ],
            error=ConnectionResetError("lost attach response"),
        ),
        _Process(
            [
                response("attach-two", "acknowledged", operation="attach_execution"),
                response(
                    "attach-two",
                    "terminal",
                    status="completed",
                    exit_code=0,
                    error=None,
                ),
            ]
        ),
    ]
    provider = _Provider(processes.copy())
    client = SandboxExecutorClient(
        provider, request_id_factory=lambda: next(request_ids)
    )

    result = asyncio.run(
        client.exec_resumable(
            _context(), command="printf one", timeout_ms=1000, max_attach_attempts=2
        )
    )

    assert result.outputs == (
        {"sequence": 1, "stream": "stdout", "data": "one"},
        {"sequence": 2, "stream": "stderr", "data": "two"},
    )
    requests = [
        decode_request(process.stdin.writes[0].splitlines(keepends=True)[1])
        for process in processes
    ]
    assert [request["type"] for request in requests] == [
        "exec",
        "attach_execution",
        "attach_execution",
    ]
    assert [request.get("offset") for request in requests] == [None, 1, 2]
    assert {request["execution_id"] for request in requests} == {"execution-a"}
    assert len(provider.calls) == 3


def test_exec_resumable_exhaustion_fails_closed_with_latest_cursor():
    request_ids = iter(["exec-request", "attach-one", "attach-two"])

    def acknowledged(request_id, operation):
        return {
            **_response("acknowledged", operation=operation),
            "request_id": request_id,
        }

    processes = [
        _Process(
            [acknowledged("exec-request", "exec")],
            error=ConnectionResetError("lost exec response"),
        ),
        _Process(
            [acknowledged("attach-one", "attach_execution")],
            error=ConnectionResetError("lost first attach"),
        ),
        _Process(
            [acknowledged("attach-two", "attach_execution")],
            error=ConnectionResetError("lost second attach"),
        ),
    ]
    provider = _Provider(processes)
    client = SandboxExecutorClient(
        provider, request_id_factory=lambda: next(request_ids)
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(
            client.exec_resumable(
                _context(), command="true", timeout_ms=1000, max_attach_attempts=2
            )
        )

    assert exc_info.value.code == "executor_transport_unavailable"
    assert exc_info.value.execution_id == "execution-a"
    assert exc_info.value.last_sequence == 0
    assert [frame["request_id"] for frame in exc_info.value.responses] == [
        "exec-request",
        "attach-one",
        "attach-two",
    ]
    assert len(provider.calls) == 3


def test_exec_resumable_retries_transient_not_found_then_fails_transport_unavailable():
    request_ids = iter(["exec-request", "attach-one", "attach-two"])

    def response(request_id, kind, **fields):
        return {**_response(kind, **fields), "request_id": request_id}

    provider = _Provider(
        [
            _Process([], error=ConnectionResetError("lost before acknowledgement")),
            _Process(
                [
                    response(
                        "attach-one", "acknowledged", operation="attach_execution"
                    ),
                    response(
                        "attach-one",
                        "terminal",
                        status="failed",
                        exit_code=None,
                        error="execution_not_found",
                    ),
                ]
            ),
            _Process(
                [
                    response(
                        "attach-two", "acknowledged", operation="attach_execution"
                    ),
                    response(
                        "attach-two",
                        "terminal",
                        status="failed",
                        exit_code=None,
                        error="execution_not_found",
                    ),
                ]
            ),
        ]
    )
    client = SandboxExecutorClient(
        provider, request_id_factory=lambda: next(request_ids)
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(
            client.exec_resumable(
                _context(), command="true", timeout_ms=1000, max_attach_attempts=2
            )
        )

    assert exc_info.value.code == "executor_transport_unavailable"
    assert len(provider.calls) == 3


@pytest.mark.parametrize(
    "frames",
    [
        [_response("acknowledged", operation="attach_execution")],
        [
            _response("acknowledged", operation="attach_execution"),
            _response("output", sequence=1, stream="stdout", data="partial"),
        ],
    ],
)
def test_attach_clean_eof_without_terminal_is_execution_lost(frames):
    client = SandboxExecutorClient(
        _Provider([_Process(frames)]), request_id_factory=lambda: "request-a"
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(client.attach_execution(_context(), offset=0, timeout_ms=1000))

    assert exc_info.value.last_sequence == (1 if len(frames) == 2 else 0)
    assert len(exc_info.value.responses) == len(frames)


@pytest.mark.parametrize("include_output", [False, True])
def test_exec_resumable_recovers_after_attach_clean_eof_prefix(include_output):
    request_ids = iter(["exec-request", "attach-one", "attach-two"])

    def response(request_id, kind, **fields):
        return {**_response(kind, **fields), "request_id": request_id}

    first_attach = [
        response("attach-one", "acknowledged", operation="attach_execution")
    ]
    if include_output:
        first_attach.append(
            response(
                "attach-one",
                "output",
                sequence=1,
                stream="stdout",
                data="partial",
            )
        )
    processes = [
        _Process([], error=ConnectionResetError("ambiguous exec")),
        _Process(first_attach),
        _Process(
            [
                response("attach-two", "acknowledged", operation="attach_execution"),
                response(
                    "attach-two",
                    "terminal",
                    status="completed",
                    exit_code=0,
                    error=None,
                ),
            ]
        ),
    ]
    client = SandboxExecutorClient(
        _Provider(processes.copy()), request_id_factory=lambda: next(request_ids)
    )

    result = asyncio.run(
        client.exec_resumable(
            _context(), command="true", timeout_ms=1000, max_attach_attempts=2
        )
    )

    requests = [
        decode_request(process.stdin.writes[0].splitlines(keepends=True)[1])
        for process in processes
    ]
    assert [request.get("offset") for request in requests] == [
        None,
        0,
        1 if include_output else 0,
    ]
    assert [output["data"] for output in result.outputs] == (
        ["partial"] if include_output else []
    )


def test_exec_resumable_uses_one_monotonic_deadline_for_all_attachments():
    clock = [10.0]

    class RecoveryClient(SandboxExecutorClient):
        def __init__(self):
            super().__init__(_Provider([]), monotonic=lambda: clock[0])
            self.timeouts = []

        async def exec(self, context, *, command, timeout_ms):
            raise ExecutorExecutionLost(
                execution_id=context.execution_id,
                last_sequence=0,
                responses=(),
            )

        async def attach_execution(
            self,
            context,
            *,
            offset,
            timeout_ms=30_000,
            recovery=False,
            wall_timeout_seconds=None,
        ):
            self.timeouts.append(timeout_ms)
            clock[0] += 0.4
            raise ExecutorExecutionLost(
                execution_id=context.execution_id,
                last_sequence=offset,
                responses=(),
            )

    client = RecoveryClient()

    with pytest.raises(ExecutorExecutionLost):
        asyncio.run(
            client.exec_resumable(
                _context(), command="true", timeout_ms=1000, max_attach_attempts=4
            )
        )

    assert client.timeouts == [1000, 600, 200]
    assert all(timeout > 0 for timeout in client.timeouts)


def test_recovery_timeout_preserves_ack_output_and_latest_cursor():
    request_ids = iter(["exec-request", "attach-request"])

    def response(request_id, kind, **fields):
        return {**_response(kind, **fields), "request_id": request_id}

    client = SandboxExecutorClient(
        _Provider(
            [
                _Process([], error=ConnectionResetError("ambiguous exec")),
                _StallingProcess(
                    [
                        response(
                            "attach-request",
                            "acknowledged",
                            operation="attach_execution",
                        ),
                        response(
                            "attach-request",
                            "output",
                            sequence=1,
                            stream="stdout",
                            data="partial",
                        ),
                    ]
                ),
            ]
        ),
        request_id_factory=lambda: next(request_ids),
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(
            client.exec_resumable(
                _context(), command="true", timeout_ms=20, max_attach_attempts=1
            )
        )

    assert exc_info.value.last_sequence == 1
    assert [frame["type"] for frame in exc_info.value.responses] == [
        "acknowledged",
        "output",
    ]
    assert exc_info.value.outputs == (
        {"sequence": 1, "stream": "stdout", "data": "partial"},
    )
    with pytest.raises(TypeError):
        exc_info.value.responses[1]["data"] = "mutated"


def test_recovery_accepts_proven_terminal_before_process_wait_transport_failure():
    frames = [
        _response("acknowledged", operation="attach_execution"),
        _response("output", sequence=1, stream="stdout", data="complete"),
        _response("terminal", status="completed", exit_code=0, error=None),
    ]
    client = SandboxExecutorClient(
        _Provider(
            [_WaitFailureProcess(frames, ConnectionResetError("wait relay lost"))]
        ),
        request_id_factory=lambda: "request-a",
    )

    result = asyncio.run(
        client.attach_execution(
            _context(),
            offset=0,
            timeout_ms=1000,
            recovery=True,
            wall_timeout_seconds=1,
        )
    )

    assert result.outputs == ({"sequence": 1, "stream": "stdout", "data": "complete"},)
    assert result.terminal == {"status": "completed", "exit_code": 0, "error": None}


def test_recovery_accepts_proven_terminal_before_owned_wait_timeout():
    frames = [
        _response("acknowledged", operation="attach_execution"),
        _response("output", sequence=1, stream="stdout", data="complete"),
        _response("terminal", status="completed", exit_code=0, error=None),
    ]
    client = SandboxExecutorClient(
        _Provider([_StallingWaitProcess(frames)]),
        request_id_factory=lambda: "request-a",
    )

    result = asyncio.run(
        client.attach_execution(
            _context(),
            offset=0,
            timeout_ms=20,
            recovery=True,
            wall_timeout_seconds=0.02,
        )
    )

    assert result.terminal["status"] == "completed"
    assert result.outputs[0]["sequence"] == 1


def test_recovery_does_not_convert_external_asyncio_cancellation():
    frames = [_response("acknowledged", operation="attach_execution")]
    client = SandboxExecutorClient(
        _Provider([_Process(frames, error=asyncio.CancelledError())]),
        request_id_factory=lambda: "request-a",
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            client.attach_execution(
                _context(),
                offset=0,
                timeout_ms=1000,
                recovery=True,
                wall_timeout_seconds=1,
            )
        )


def test_attach_rejects_a_gap_after_the_recovery_cursor():
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="attach_execution"),
                    _response("output", sequence=3, stream="stdout", data="gap"),
                    _response("terminal", status="completed", exit_code=0, error=None),
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="contiguous"):
        asyncio.run(client.attach_execution(_context(), offset=1, timeout_ms=1000))


def test_exec_resumable_converts_attach_cursor_gap_to_execution_lost_prefix():
    request_ids = iter(["exec-request", "attach-request"])

    def response(request_id, kind, **fields):
        return {**_response(kind, **fields), "request_id": request_id}

    client = SandboxExecutorClient(
        _Provider(
            [
                _Process(
                    [
                        response("exec-request", "acknowledged", operation="exec"),
                        response(
                            "exec-request",
                            "output",
                            sequence=1,
                            stream="stdout",
                            data="safe",
                        ),
                    ],
                    error=ConnectionResetError("ambiguous exec"),
                ),
                _Process(
                    [
                        response(
                            "attach-request",
                            "acknowledged",
                            operation="attach_execution",
                        ),
                        response(
                            "attach-request",
                            "output",
                            sequence=3,
                            stream="stdout",
                            data="invalid-gap",
                        ),
                    ]
                ),
            ]
        ),
        request_id_factory=lambda: next(request_ids),
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(
            client.exec_resumable(
                _context(), command="true", timeout_ms=1000, max_attach_attempts=1
            )
        )

    assert exc_info.value.last_sequence == 1
    assert [frame["type"] for frame in exc_info.value.responses] == [
        "acknowledged",
        "output",
        "acknowledged",
    ]
    assert all(frame.get("data") != "invalid-gap" for frame in exc_info.value.responses)


@pytest.mark.parametrize("failure", ["uncorrelated", "malformed"])
def test_exec_resumable_excludes_invalid_attach_frame_from_lost_prefix(failure):
    request_ids = iter(["exec-request", "attach-request"])

    def response(request_id, kind, **fields):
        return {**_response(kind, **fields), "request_id": request_id}

    attach_frames = [
        response("attach-request", "acknowledged", operation="attach_execution")
    ]
    trailing = b""
    if failure == "uncorrelated":
        invalid = response(
            "attach-request",
            "output",
            sequence=1,
            stream="stdout",
            data="invalid",
        )
        invalid["execution_id"] = "other-execution"
        attach_frames.append(invalid)
    else:
        trailing = b'{"protocol":"sandbox-executor-v1"'
    client = SandboxExecutorClient(
        _Provider(
            [
                _Process([], error=ConnectionResetError("ambiguous exec")),
                _Process(attach_frames, trailing=trailing),
            ]
        ),
        request_id_factory=lambda: next(request_ids),
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(
            client.exec_resumable(
                _context(), command="true", timeout_ms=1000, max_attach_attempts=1
            )
        )

    assert exc_info.value.last_sequence == 0
    assert [frame["type"] for frame in exc_info.value.responses] == ["acknowledged"]


def test_exec_resumable_bounds_aggregate_frames_across_losses(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chat_sandbox_executor.MAX_EXECUTOR_RESPONSE_FRAMES", 3
    )
    request_ids = iter(["exec-request", "attach-request"])

    def response(request_id, kind, **fields):
        return {**_response(kind, **fields), "request_id": request_id}

    client = SandboxExecutorClient(
        _Provider(
            [
                _Process(
                    [
                        response("exec-request", "acknowledged", operation="exec"),
                        response(
                            "exec-request",
                            "output",
                            sequence=1,
                            stream="stdout",
                            data="one",
                        ),
                    ],
                    error=ConnectionResetError("lost exec"),
                ),
                _Process(
                    [
                        response(
                            "attach-request",
                            "acknowledged",
                            operation="attach_execution",
                        ),
                        response(
                            "attach-request",
                            "output",
                            sequence=2,
                            stream="stdout",
                            data="two",
                        ),
                    ],
                    error=ConnectionResetError("lost attach"),
                ),
            ]
        ),
        request_id_factory=lambda: next(request_ids),
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(
            client.exec_resumable(
                _context(), command="true", timeout_ms=1000, max_attach_attempts=1
            )
        )
    assert len(exc_info.value.responses) == 3


def test_exec_resumable_bounds_aggregate_bytes_across_losses(monkeypatch):
    request_ids = iter(["exec-request", "attach-request"])

    def response(request_id, kind, **fields):
        return {**_response(kind, **fields), "request_id": request_id}

    exec_frames = [
        response("exec-request", "acknowledged", operation="exec"),
        response(
            "exec-request",
            "output",
            sequence=1,
            stream="stdout",
            data="one",
        ),
    ]
    attach_frames = [
        response("attach-request", "acknowledged", operation="attach_execution"),
        response(
            "attach-request",
            "output",
            sequence=2,
            stream="stdout",
            data="two",
        ),
    ]
    first_bytes = sum(len(encode_response(frame)) for frame in exec_frames)
    total_bytes = first_bytes + sum(
        len(encode_response(frame)) for frame in attach_frames
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_executor.MAX_EXECUTOR_RESPONSE_BYTES",
        (first_bytes + total_bytes) // 2,
    )
    client = SandboxExecutorClient(
        _Provider(
            [
                _Process(
                    exec_frames,
                    error=ConnectionResetError("lost exec"),
                ),
                _Process(
                    attach_frames,
                    error=ConnectionResetError("lost attach"),
                ),
            ]
        ),
        request_id_factory=lambda: next(request_ids),
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(
            client.exec_resumable(
                _context(), command="true", timeout_ms=1000, max_attach_attempts=1
            )
        )
    assert len(exc_info.value.responses) >= 2


def test_execution_lost_preserves_immutable_cumulative_validated_frames():
    process = _Process(
        [
            _response("acknowledged", operation="exec"),
            _response("output", sequence=1, stream="stdout", data="partial"),
        ],
        error=ConnectionResetError("lost"),
    )
    client = SandboxExecutorClient(
        _Provider([process]), request_id_factory=lambda: "request-a"
    )

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(client.exec(_context(), command="true", timeout_ms=1000))

    assert [frame["type"] for frame in exc_info.value.responses] == [
        "acknowledged",
        "output",
    ]
    with pytest.raises(TypeError):
        exc_info.value.responses[0]["type"] = "mutated"


def test_exec_disconnect_before_ack_is_typed_lost_and_is_not_retried():
    process = _Process([], error=ConnectionResetError("synthetic disconnect"))
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost) as exc_info:
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert exc_info.value.code == "execution_lost"
    assert len(provider.calls) == 1
    assert process.stdin.write_attempts == 1


def test_exec_authoritative_pre_write_failure_remains_transport_failure():
    process = _PreWriteFailureProcess()
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorTransportError):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert len(provider.calls) == 1
    assert process.stdin_lookups == 1


def test_exec_write_failure_is_conservatively_lost_without_zero_delivery_proof():
    stdin = _Input(write_error=ConnectionResetError("synthetic write failure"))
    process = _Process([], stdin=stdin)
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert len(provider.calls) == 1
    assert stdin.write_attempts == 1
    assert stdin.writes == []


def test_exec_partial_write_failure_is_typed_lost_and_is_not_retried():
    stdin = _Input(
        write_error=ConnectionResetError("synthetic partial write"),
        partial_write_bytes=17,
    )
    process = _Process([], stdin=stdin)
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert len(provider.calls) == 1
    assert stdin.write_attempts == 1
    assert len(stdin.writes) == 1
    assert len(stdin.writes[0]) == 17


def test_exec_clean_eof_before_ack_after_full_write_is_typed_lost():
    process = _Process([])
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert len(provider.calls) == 1
    assert process.stdin.write_attempts == 1
    assert len(process.stdin.writes) == 1


def test_exec_drain_failure_after_full_write_is_typed_lost():
    stdin = _Input(drain_error=ConnectionResetError("synthetic drain failure"))
    process = _Process([], stdin=stdin)
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert len(provider.calls) == 1
    assert stdin.write_attempts == 1
    assert len(stdin.writes) == 1


@pytest.mark.parametrize(
    "failure",
    [
        ConnectionError("synthetic provider failure"),
        ModalConnectionError("synthetic Modal failure"),
        GRPCError(Status.UNAVAILABLE, "synthetic relay failure"),
    ],
)
def test_exec_provider_connection_failure_is_typed_transport_failure(failure):
    provider = _FailingProvider(failure)
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorTransportError) as exc_info:
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert exc_info.value.payload_delivery_attempted is False
    assert provider.calls == 1


def test_non_exec_write_failure_retains_transport_semantics():
    stdin = _Input(write_error=ConnectionResetError("synthetic write failure"))
    process = _Process([], stdin=stdin)
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorTransportError) as exc_info:
        asyncio.run(client.health(object()))

    assert exc_info.value.payload_delivery_attempted is True
    assert len(provider.calls) == 1
    assert stdin.write_attempts == 1


@pytest.mark.parametrize(
    "defect",
    [
        AssertionError("synthetic invariant defect"),
        TypeError("synthetic programming defect"),
    ],
)
def test_exec_does_not_reclassify_unexpected_client_defects_after_ack(defect):
    process = _Process(
        [_response("acknowledged", operation="exec")],
        error=defect,
    )
    provider = _Provider([process])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(type(defect), match="synthetic"):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert len(provider.calls) == 1


def test_exec_truncated_frame_after_ack_is_typed_lost():
    provider = _Provider(
        [
            _Process(
                [_response("acknowledged", operation="exec")],
                trailing=b'{"protocol":"sandbox-executor-v1"',
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ExecutorExecutionLost):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))

    assert len(provider.calls) == 1


def test_exec_rejects_uncorrelated_response():
    response = _response("acknowledged", operation="exec")
    response["workspace_generation"] = 8
    provider = _Provider([_Process([response])])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="Uncorrelated"):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))


def test_exec_rejects_uncorrelated_output_instead_of_classifying_it_lost():
    output = _response("output", sequence=1, stream="stdout", data="synthetic")
    output["workspace_generation"] = 8
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="exec"),
                    output,
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="Uncorrelated"):
        asyncio.run(client.exec(_context(), command="pwc task list", timeout_ms=1000))


def test_executor_client_exposes_health_ensure_attach_cancel_and_read():
    operation_frames = [
        [
            {
                "protocol": PROTOCOL,
                "type": "health_result",
                "request_id": "request-a",
                "execution_id": "request-a",
                "status": "ok",
            }
        ],
        [_response("acknowledged", operation="ensure_workspace")],
        [_response("acknowledged", operation="release_workspace")],
        [
            _response("acknowledged", operation="attach_execution"),
            _response("terminal", status="completed", exit_code=0, error=None),
        ],
        [
            _response("acknowledged", operation="cancel_execution"),
            _response("terminal", status="cancelled", exit_code=None, error=None),
        ],
        [
            _response("acknowledged", operation="read_file"),
            _response(
                "read_result",
                path="notes.txt",
                offset=3,
                data_base64="c2FmZSB0ZXh0",
                eof=True,
            ),
        ],
    ]
    processes = [_Process(frames) for frames in operation_frames]
    provider = _Provider(processes.copy())
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")
    context = _context()

    assert asyncio.run(client.health(context.sandbox)) == "ok"
    asyncio.run(client.ensure_workspace(context))
    asyncio.run(client.release_workspace(context))
    attached = asyncio.run(client.attach_execution(context, offset=4))
    cancelled = asyncio.run(client.cancel_execution(context))
    read = asyncio.run(
        client.read_file(context, path="notes.txt", offset=3, max_bytes=20)
    )

    assert attached.terminal["status"] == "completed"
    assert cancelled.terminal["status"] == "cancelled"

    assert read.path == "notes.txt"
    assert read.offset == 3
    assert read.data == b"safe text"
    assert read.eof is True
    request_types = []
    for index, process in enumerate(processes):
        wire = process.stdin.writes[0]
        if index == 0:
            request_types.append(decode_request(wire)["type"])
        else:
            request_types.append(
                decode_request(wire.splitlines(keepends=True)[1])["type"]
            )
    assert request_types == [
        "health",
        "ensure_workspace",
        "release_workspace",
        "attach_execution",
        "cancel_execution",
        "read_file",
    ]


def test_attach_rejects_output_that_does_not_advance_requested_cursor():
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="attach_execution"),
                    _response("output", sequence=4, stream="stdout", data="synthetic"),
                    _response("terminal", status="completed", exit_code=0, error=None),
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="contiguous"):
        asyncio.run(client.attach_execution(_context(), offset=4))


def test_executor_client_bounds_the_complete_response_stream():
    frame = {
        "protocol": PROTOCOL,
        "type": "health_result",
        "request_id": "request-a",
        "execution_id": "request-a",
        "status": "ok",
    }
    provider = _Provider([_Process([frame] * (MAX_EXECUTOR_RESPONSE_FRAMES + 1))])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="too many frames"):
        asyncio.run(client.health(object()))


def test_daemon_tiny_chunks_fit_shared_client_frame_budget_end_to_end(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-a",
        broker_control=_Broker(),
        command_preexec=None,
        read_chunk_size=1,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    provider = _SocketProvider(server.socket_path)
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    # This stress case verifies frame accounting, not a two-second latency SLO.
    result = asyncio.run(
        client.exec(
            _context(),
            command="for ((i=0; i<1023; i++)); do printf x; done",
            timeout_ms=10_000,
        )
    )

    assert MAX_EXECUTION_OUTPUT_FRAMES == MAX_EXECUTION_RESPONSE_FRAMES - 2
    assert len(result.outputs) == MAX_EXECUTION_OUTPUT_FRAMES
    assert "".join(str(output["data"]) for output in result.outputs) == (
        "x" * MAX_EXECUTION_OUTPUT_FRAMES
    )
    assert result.terminal == {"status": "completed", "exit_code": 0, "error": None}
    assert provider.calls == 1
    server.shutdown()
    thread.join(timeout=2)


def test_binary_read_round_trips_through_daemon_socket_and_client(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "bytes.bin").write_bytes(b"\xff\xc3\xa9\x00Z")
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-a",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    provider = _SocketProvider(server.socket_path)
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    result = asyncio.run(
        client.read_file(_context(), path="bytes.bin", offset=0, max_bytes=4)
    )

    assert result.data == b"\xff\xc3\xa9\x00"
    assert result.offset == 0
    assert result.eof is False
    assert provider.calls == 1
    server.shutdown()
    thread.join(timeout=2)


@pytest.mark.parametrize(
    ("command", "drop_after_frames", "expected_relay_calls"),
    [
        ("printf x >> marker", 1, 2),
        ("printf partial; sleep .05; printf x >> marker", 2, 2),
        ("printf x >> marker", 2, 1),
    ],
    ids=["after-acceptance", "mid-output", "after-terminal"],
)
def test_exec_resumable_real_daemon_faults_never_repeat_side_effect(
    tmp_path, command, drop_after_frames, expected_relay_calls
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = ExecutorServer(
        socket_path=tmp_path / "private" / "executor.sock",
        state_path=tmp_path / "state",
        workspace_root=workspace,
        worker_generation="worker-a",
        broker_control=_Broker(),
        command_preexec=None,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    assert server.wait_until_ready(2)
    provider = _DropFirstResponseSocketProvider(
        server.socket_path, drop_after_frames=drop_after_frames
    )
    request_number = iter(range(10))
    client = SandboxExecutorClient(
        provider, request_id_factory=lambda: f"request-{next(request_number)}"
    )

    try:
        result = asyncio.run(
            client.exec_resumable(_context(), command=command, timeout_ms=1000)
        )

        assert (workspace / "marker").read_text() == "x"
        request_types = [
            decode_request(process.stdin.writes[0].splitlines(keepends=True)[1])["type"]
            for process in provider.processes
        ]
        assert request_types.count("exec") == 1
        assert request_types[0] == "exec"
        assert set(request_types[1:]) <= {"attach_execution"}
        assert provider.calls == expected_relay_calls
        assert result.terminal == {
            "status": "completed",
            "exit_code": 0,
            "error": None,
        }
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_read_rejects_decoded_data_larger_than_the_requested_byte_limit():
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="read_file"),
                    _response(
                        "read_result",
                        path="notes.txt",
                        offset=0,
                        data_base64="YWJjZA==",
                        eof=False,
                    ),
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    with pytest.raises(ProtocolError, match="requested byte limit"):
        asyncio.run(
            client.read_file(_context(), path="notes.txt", offset=0, max_bytes=3)
        )


@pytest.mark.parametrize(
    ("data_base64", "expected", "max_bytes"),
    [("YWJj", b"abc", 3), ("/8OpAA==", b"\xff\xc3\xa9\x00", 4)],
)
def test_read_accepts_exact_binary_data_at_the_requested_byte_limit(
    data_base64, expected, max_bytes
):
    provider = _Provider(
        [
            _Process(
                [
                    _response("acknowledged", operation="read_file"),
                    _response(
                        "read_result",
                        path="notes.txt",
                        offset=0,
                        data_base64=data_base64,
                        eof=True,
                    ),
                ]
            )
        ]
    )
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")

    result = asyncio.run(
        client.read_file(_context(), path="notes.txt", offset=0, max_bytes=max_bytes)
    )

    assert result.data == expected


@pytest.mark.parametrize("capability", ["", "x" * (64 * 1024)])
def test_invalid_bootstrap_is_rejected_before_opening_provider_relay(capability):
    provider = _Provider([])
    client = SandboxExecutorClient(provider, request_id_factory=lambda: "request-a")
    context = replace(_context(), capability=capability)

    with pytest.raises(ProtocolError, match="Invalid executor bootstrap"):
        asyncio.run(client.exec(context, command="true", timeout_ms=1000))

    assert provider.calls == []
