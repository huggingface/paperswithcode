"""Trusted backend client for the isolated sandbox executor relay."""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from grpclib import GRPCError
from grpclib.exceptions import StreamTerminatedError
from modal.exception import (
    ConnectionError as ModalConnectionError,
    ExecTimeoutError,
    ExecutionError,
    SandboxTerminatedError,
)

from backend.chat_sandbox_worker.executor_daemon import EXECUTOR_BOOTSTRAP_PREFIX
from backend.chat_sandbox_worker.executor_protocol import (
    MAX_EXECUTION_RESPONSE_FRAMES,
    MAX_FRAME_BYTES,
    PROTOCOL,
    ProtocolError,
    ResponseSequenceValidator,
    decode_read_result_data,
    decode_response,
    encode_response,
    encode_request,
)

MAX_EXECUTOR_RESPONSE_BYTES = 2 * MAX_FRAME_BYTES
MAX_EXECUTOR_RESPONSE_FRAMES = MAX_EXECUTION_RESPONSE_FRAMES


class ExecutorRelayProvider(Protocol):
    async def open_executor_relay(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object: ...


@dataclass(frozen=True)
class ExecutorContext:
    sandbox: object = field(repr=False, compare=False)
    workspace_id: str
    workspace_generation: int
    session_id: str
    turn_id: str
    execution_id: str
    tool_call_id: str
    worker_generation: str
    capability: str = field(repr=False)
    turn_worker_id: str
    turn_worker_generation: str
    turn_lease_generation: str

    @property
    def operation_identity(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_generation": self.workspace_generation,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "execution_id": self.execution_id,
            "tool_call_id": self.tool_call_id,
        }


@dataclass(frozen=True)
class ExecutorExecutionResult:
    outputs: tuple[dict[str, object], ...]
    terminal: dict[str, object]
    responses: tuple[Mapping[str, object], ...] = ()
    recovered: bool = False


@dataclass(frozen=True)
class ExecutorReadResult:
    path: str
    offset: int
    data: bytes
    eof: bool


class PersistentExecutorChannel(Protocol):
    """Task-scoped executor operations over one already attached stream."""

    async def health(self) -> str: ...

    async def ensure_workspace(self, context: ExecutorContext) -> None: ...

    async def exec_resumable(
        self,
        context: ExecutorContext,
        *,
        command: str,
        timeout_ms: int,
        max_attach_attempts: int = 2,
    ) -> ExecutorExecutionResult: ...

    async def read_file(
        self,
        context: ExecutorContext,
        *,
        path: str,
        offset: int,
        max_bytes: int,
    ) -> ExecutorReadResult: ...

    async def cancel(self, context: ExecutorContext) -> bool: ...


class ExecutorTransportError(RuntimeError):
    """The trusted client could not prove a complete relay exchange."""

    def __init__(
        self,
        responses: tuple[dict[str, object], ...] = (),
        *,
        payload_delivery_attempted: bool = False,
    ) -> None:
        super().__init__("Sandbox executor transport was lost")
        self.responses = responses
        self.payload_delivery_attempted = payload_delivery_attempted


class ExecutorExecutionLost(RuntimeError):
    """An Exec with uncertain delivery or completion must never be retried."""

    code = "execution_lost"

    def __init__(
        self,
        *,
        execution_id: str,
        last_sequence: int,
        responses: tuple[Mapping[str, object], ...],
        outputs: tuple[dict[str, object], ...] = (),
    ) -> None:
        super().__init__("Sandbox execution delivery or completion is uncertain")
        self._execution_id = execution_id
        self._last_sequence = last_sequence
        self._responses = tuple(
            MappingProxyType(dict(response)) for response in responses
        )
        self.outputs = outputs

    @property
    def execution_id(self) -> str:
        return self._execution_id

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    @property
    def responses(self) -> tuple[Mapping[str, object], ...]:
        return self._responses


class ExecutorOperationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__("Sandbox executor operation failed")
        self.code = code


class _ExecutorDisconnect(RuntimeError):
    pass


class SandboxExecutorClient:
    """Execute one strictly correlated request through a fresh sandbox relay."""

    def __init__(
        self,
        provider: ExecutorRelayProvider,
        *,
        request_id_factory: Callable[[], str] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.provider = provider
        self.request_id_factory = request_id_factory or (lambda: uuid.uuid4().hex)
        self.monotonic = monotonic or time.monotonic

    async def health(self, sandbox: object) -> str:
        request_id = self.request_id_factory()
        request = {
            "protocol": PROTOCOL,
            "type": "health",
            "request_id": request_id,
            "execution_id": request_id,
        }
        responses = await self._exchange(
            sandbox,
            request,
            context=None,
            timeout_seconds=5,
        )
        if len(responses) != 1:
            raise ProtocolError("Invalid executor health response sequence")
        response = responses[0]
        if (
            response["type"] != "health_result"
            or response["request_id"] != request_id
            or response["execution_id"] != request_id
        ):
            raise ProtocolError("Uncorrelated executor health response")
        return str(response["status"])

    async def ensure_workspace(self, context: ExecutorContext) -> None:
        request = self._request(context, "ensure_workspace")
        responses = await self._exchange(
            context.sandbox, request, context=context, timeout_seconds=10
        )
        if len(responses) != 1:
            raise ProtocolError("Invalid ensure-workspace response sequence")
        self._validate_ack(responses[0], request, "ensure_workspace")

    async def exec(
        self,
        context: ExecutorContext,
        *,
        command: str,
        timeout_ms: int,
    ) -> ExecutorExecutionResult:
        request = self._request(
            context,
            "exec",
            command=command,
            timeout_ms=timeout_ms,
        )
        timeout_seconds = max(5, (timeout_ms + 999) // 1000 + 5)
        try:
            responses = await self._exchange(
                context.sandbox,
                request,
                context=context,
                timeout_seconds=timeout_seconds,
            )
        except ExecutorTransportError as error:
            if self._valid_execution_prefix(error.responses, request, "exec"):
                if error.responses[-1]["type"] == "terminal":
                    return self._execution_result(error.responses, request, "exec")
                raise self._execution_lost(error.responses, request, "exec") from error
            if error.payload_delivery_attempted:
                raise ExecutorExecutionLost(
                    execution_id=context.execution_id,
                    last_sequence=0,
                    responses=(),
                ) from error
            raise
        if self._valid_execution_prefix(responses, request, "exec") and (
            not responses or responses[-1]["type"] != "terminal"
        ):
            raise self._execution_lost(responses, request, "exec")
        return self._execution_result(responses, request, "exec")

    async def exec_resumable(
        self,
        context: ExecutorContext,
        *,
        command: str,
        timeout_ms: int,
        max_attach_attempts: int = 2,
    ) -> ExecutorExecutionResult:
        if max_attach_attempts < 0:
            raise ValueError("max_attach_attempts must not be negative")
        try:
            result = await self.exec(context, command=command, timeout_ms=timeout_ms)
        except ExecutorExecutionLost as lost:
            outputs = lost.outputs
            cursor = lost.last_sequence
            responses = lost.responses
        else:
            if result.terminal.get("error") == "execution_lost":
                raise ExecutorExecutionLost(
                    execution_id=context.execution_id,
                    last_sequence=max(
                        (int(output["sequence"]) for output in result.outputs),
                        default=0,
                    ),
                    responses=result.responses,
                    outputs=result.outputs,
                )
            return result
        self._validate_recovery_bounds(responses)
        deadline = self.monotonic() + timeout_ms / 1000

        for _attempt in range(max_attach_attempts):
            remaining_seconds = deadline - self.monotonic()
            if remaining_seconds <= 0:
                break
            remaining_ms = max(1, math.ceil(remaining_seconds * 1000))
            try:
                attached = await self.attach_execution(
                    context,
                    offset=cursor,
                    timeout_ms=remaining_ms,
                    recovery=True,
                    wall_timeout_seconds=remaining_seconds,
                )
            except ExecutorExecutionLost as lost:
                if lost.execution_id != context.execution_id:
                    raise ExecutorExecutionLost(
                        execution_id=context.execution_id,
                        last_sequence=cursor,
                        responses=responses,
                        outputs=outputs,
                    ) from lost
                responses, outputs, cursor = self._merge_recovery_frames(
                    context,
                    responses,
                    outputs,
                    cursor,
                    lost.responses,
                )
                continue
            responses, outputs, cursor = self._merge_recovery_frames(
                context,
                responses,
                outputs,
                cursor,
                attached.responses,
            )
            if self.monotonic() > deadline:
                break
            if attached.terminal.get("error") == "execution_not_found":
                continue
            if attached.terminal.get("error") == "execution_lost":
                raise ExecutorExecutionLost(
                    execution_id=context.execution_id,
                    last_sequence=max(
                        (int(output["sequence"]) for output in outputs),
                        default=cursor,
                    ),
                    responses=responses,
                    outputs=outputs,
                )
            return ExecutorExecutionResult(
                outputs=outputs,
                terminal=attached.terminal,
                responses=responses,
                recovered=True,
            )
        raise ExecutorExecutionLost(
            execution_id=context.execution_id,
            last_sequence=cursor,
            responses=responses,
            outputs=outputs,
        )

    async def attach_execution(
        self,
        context: ExecutorContext,
        *,
        offset: int,
        timeout_ms: int = 30_000,
        recovery: bool = False,
        wall_timeout_seconds: float | None = None,
    ) -> ExecutorExecutionResult:
        request = self._request(context, "attach_execution", offset=offset)
        timeout_seconds = max(1, math.ceil(timeout_ms / 1000))
        try:
            responses = await self._exchange(
                context.sandbox,
                request,
                context=context,
                timeout_seconds=timeout_seconds,
                wall_timeout_seconds=wall_timeout_seconds,
                preserve_partial_protocol=recovery,
            )
        except ExecutorTransportError as error:
            if recovery:
                try:
                    result = self._execution_result(
                        error.responses, request, "attach_execution"
                    )
                    self._validate_output_cursor(result.outputs, offset)
                except ProtocolError:
                    raise self._recovery_execution_lost(
                        error.responses,
                        request,
                        "attach_execution",
                        previous_cursor=offset,
                    ) from error
                return result
            if self._valid_execution_prefix(
                error.responses, request, "attach_execution"
            ):
                if error.responses[-1]["type"] == "terminal":
                    return self._execution_result(
                        error.responses, request, "attach_execution"
                    )
                raise self._execution_lost(
                    error.responses,
                    request,
                    "attach_execution",
                    previous_cursor=offset,
                ) from error
            raise ExecutorExecutionLost(
                execution_id=context.execution_id,
                last_sequence=offset,
                responses=(),
            ) from error
        try:
            if self._valid_execution_prefix(
                responses, request, "attach_execution"
            ) and (responses[-1]["type"] != "terminal"):
                raise self._execution_lost(
                    responses,
                    request,
                    "attach_execution",
                    previous_cursor=offset,
                )
            result = self._execution_result(responses, request, "attach_execution")
            self._validate_output_cursor(result.outputs, offset)
        except ProtocolError as error:
            if not recovery:
                raise
            raise self._recovery_execution_lost(
                responses,
                request,
                "attach_execution",
                previous_cursor=offset,
            ) from error
        return result

    async def cancel_execution(
        self, context: ExecutorContext
    ) -> ExecutorExecutionResult:
        request = self._request(context, "cancel_execution")
        responses = await self._exchange(
            context.sandbox, request, context=context, timeout_seconds=35
        )
        return self._execution_result(responses, request, "cancel_execution")

    async def read_file(
        self,
        context: ExecutorContext,
        *,
        path: str,
        offset: int,
        max_bytes: int,
    ) -> ExecutorReadResult:
        request = self._request(
            context,
            "read_file",
            path=path,
            offset=offset,
            max_bytes=max_bytes,
        )
        responses = await self._exchange(
            context.sandbox, request, context=context, timeout_seconds=10
        )
        if len(responses) != 2:
            raise ProtocolError("Invalid read response sequence")
        self._validate_ack(responses[0], request, "read_file")
        response = responses[1]
        self._validate_correlation(response, request)
        if response["type"] == "terminal":
            raise ExecutorOperationError(str(response["error"]))
        if response["type"] != "read_result":
            raise ProtocolError("Invalid read response sequence")
        if response["path"] != path or response["offset"] != offset:
            raise ProtocolError("Uncorrelated executor read response")
        data = decode_read_result_data(response["data_base64"])
        if len(data) > max_bytes:
            raise ProtocolError("Executor read exceeded the requested byte limit")
        return ExecutorReadResult(
            path=str(response["path"]),
            offset=int(response["offset"]),
            data=data,
            eof=bool(response["eof"]),
        )

    def _request(
        self, context: ExecutorContext, operation: str, **fields: object
    ) -> dict[str, object]:
        return {
            "protocol": PROTOCOL,
            "type": operation,
            "request_id": self.request_id_factory(),
            **context.operation_identity,
            **fields,
        }

    async def _exchange(
        self,
        sandbox: object,
        request: dict[str, object],
        *,
        context: ExecutorContext | None,
        timeout_seconds: int,
        wall_timeout_seconds: float | None = None,
        preserve_partial_protocol: bool = False,
    ) -> tuple[dict[str, object], ...]:
        request_frame = encode_request(request)
        payload = request_frame
        if context is not None:
            payload = self._bootstrap(context) + request_frame
        responses: list[dict[str, object]] = []
        payload_delivery_attempted = False
        try:
            process = await self.provider.open_executor_relay(
                sandbox, timeout_seconds=timeout_seconds
            )
            write = process.stdin.write
            payload_delivery_attempted = True
            write(payload)
            process.stdin.write_eof()
            await process.stdin.drain.aio()

            async def receive() -> None:
                async for response in self._responses(process.stdout):
                    responses.append(response)
                await process.wait.aio()

            if wall_timeout_seconds is None:
                await receive()
            else:
                async with asyncio.timeout(wall_timeout_seconds):
                    await receive()
            if not responses:
                raise _ExecutorDisconnect(
                    "Executor response stream ended before its first frame"
                )
        except ProtocolError as error:
            if not preserve_partial_protocol:
                raise
            raise ExecutorTransportError(
                tuple(responses),
                payload_delivery_attempted=payload_delivery_attempted,
            ) from error
        except TimeoutError as error:
            raise ExecutorTransportError(
                tuple(responses),
                payload_delivery_attempted=payload_delivery_attempted,
            ) from error
        except (
            OSError,
            EOFError,
            GRPCError,
            StreamTerminatedError,
            ModalConnectionError,
            ExecTimeoutError,
            ExecutionError,
            SandboxTerminatedError,
            _ExecutorDisconnect,
        ) as error:
            raise ExecutorTransportError(
                tuple(responses),
                payload_delivery_attempted=payload_delivery_attempted,
            ) from error
        return tuple(responses)

    @staticmethod
    def _bootstrap(context: ExecutorContext) -> bytes:
        if (
            not isinstance(context.capability, str)
            or not context.capability
            or not isinstance(context.worker_generation, str)
            or not context.worker_generation
            or not isinstance(context.turn_worker_id, str)
            or not context.turn_worker_id
            or not isinstance(context.turn_worker_generation, str)
            or not context.turn_worker_generation
            or not isinstance(context.turn_lease_generation, str)
            or not context.turn_lease_generation
        ):
            raise ProtocolError("Invalid executor bootstrap")
        value = {
            "operation": "executor_connect",
            "capability": context.capability,
            "workspace_id": context.workspace_id,
            "workspace_generation": context.workspace_generation,
            "session_id": context.session_id,
            "turn_id": context.turn_id,
            "worker_generation": context.worker_generation,
            "turn_worker_id": context.turn_worker_id,
            "turn_worker_generation": context.turn_worker_generation,
            "turn_lease_generation": context.turn_lease_generation,
        }
        try:
            encoded = (
                EXECUTOR_BOOTSTRAP_PREFIX
                + json.dumps(value, separators=(",", ":")).encode("utf-8")
                + b"\n"
            )
        except (TypeError, UnicodeEncodeError) as error:
            raise ProtocolError("Invalid executor bootstrap") from error
        if len(encoded) > 64 * 1024:
            raise ProtocolError("Invalid executor bootstrap")
        return encoded

    @staticmethod
    async def _responses(stream: object) -> AsyncIterator[dict[str, object]]:
        buffer = b""
        received_bytes = 0
        received_frames = 0
        async for chunk in stream:
            if not isinstance(chunk, bytes):
                raise ProtocolError("Executor response stream must be bytes")
            received_bytes += len(chunk)
            if received_bytes > MAX_EXECUTOR_RESPONSE_BYTES:
                raise ProtocolError("Executor response stream is too large")
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                received_frames += 1
                if received_frames > MAX_EXECUTOR_RESPONSE_FRAMES:
                    raise ProtocolError("Executor response stream has too many frames")
                yield decode_response(line + b"\n")
            if len(buffer) > MAX_FRAME_BYTES:
                raise ProtocolError("Executor response frame is too large")
        if buffer:
            raise _ExecutorDisconnect("Executor response stream ended mid-frame")

    @staticmethod
    def _validate_correlation(
        response: dict[str, object], request: dict[str, object]
    ) -> None:
        for identity_field in (
            "request_id",
            "workspace_id",
            "workspace_generation",
            "session_id",
            "turn_id",
            "execution_id",
            "tool_call_id",
        ):
            if response[identity_field] != request[identity_field]:
                raise ProtocolError("Uncorrelated executor response")

    @classmethod
    def _validate_ack(
        cls,
        response: dict[str, object],
        request: dict[str, object],
        operation: str,
    ) -> None:
        cls._validate_correlation(response, request)
        if response["type"] != "acknowledged" or response["operation"] != operation:
            raise ProtocolError("Invalid executor acknowledgement")

    @classmethod
    def _valid_execution_prefix(
        cls,
        responses: tuple[dict[str, object], ...],
        request: dict[str, object],
        operation: str,
    ) -> bool:
        if not responses:
            return False
        cls._validate_ack(responses[0], request, operation)
        validator = ResponseSequenceValidator(
            str(request["request_id"]),
            workspace_id=str(request["workspace_id"]),
            workspace_generation=int(request["workspace_generation"]),
            session_id=str(request["session_id"]),
            turn_id=str(request["turn_id"]),
            execution_id=str(request["execution_id"]),
            tool_call_id=str(request["tool_call_id"]),
        )
        for response in responses:
            validator.accept(response)
        return True

    @classmethod
    def _execution_result(
        cls,
        responses: tuple[dict[str, object], ...],
        request: dict[str, object],
        operation: str,
    ) -> ExecutorExecutionResult:
        validator = ResponseSequenceValidator(
            str(request["request_id"]),
            workspace_id=str(request["workspace_id"]),
            workspace_generation=int(request["workspace_generation"]),
            session_id=str(request["session_id"]),
            turn_id=str(request["turn_id"]),
            execution_id=str(request["execution_id"]),
            tool_call_id=str(request["tool_call_id"]),
        )
        for response in responses:
            validator.accept(response)
        validator.finish()
        cls._validate_ack(responses[0], request, operation)
        outputs = tuple(
            {
                "sequence": response["sequence"],
                "stream": response["stream"],
                "data": response["data"],
            }
            for response in responses
            if response["type"] == "output"
        )
        terminal = responses[-1]
        return ExecutorExecutionResult(
            outputs=outputs,
            terminal={
                "status": terminal["status"],
                "exit_code": terminal["exit_code"],
                "error": terminal["error"],
            },
            responses=tuple(MappingProxyType(dict(response)) for response in responses),
        )

    @classmethod
    def _execution_lost(
        cls,
        responses: tuple[dict[str, object], ...],
        request: dict[str, object],
        operation: str,
        *,
        previous_cursor: int = 0,
    ) -> ExecutorExecutionLost:
        cls._valid_execution_prefix(responses, request, operation)
        outputs = tuple(
            {
                "sequence": response["sequence"],
                "stream": response["stream"],
                "data": response["data"],
            }
            for response in responses
            if response["type"] == "output"
        )
        cls._validate_output_cursor(outputs, previous_cursor)
        last_sequence = max(
            (int(output["sequence"]) for output in outputs),
            default=previous_cursor,
        )
        return ExecutorExecutionLost(
            execution_id=str(request["execution_id"]),
            last_sequence=last_sequence,
            responses=responses,
            outputs=outputs,
        )

    @classmethod
    def _recovery_execution_lost(
        cls,
        responses: tuple[dict[str, object], ...],
        request: dict[str, object],
        operation: str,
        *,
        previous_cursor: int,
    ) -> ExecutorExecutionLost:
        prefix: list[dict[str, object]] = []
        expected_sequence = previous_cursor + 1
        validator = ResponseSequenceValidator(
            str(request["request_id"]),
            workspace_id=str(request["workspace_id"]),
            workspace_generation=int(request["workspace_generation"]),
            session_id=str(request["session_id"]),
            turn_id=str(request["turn_id"]),
            execution_id=str(request["execution_id"]),
            tool_call_id=str(request["tool_call_id"]),
        )
        for response in responses:
            try:
                validator.accept(response)
                if not prefix:
                    cls._validate_ack(response, request, operation)
                elif response["type"] == "output":
                    if int(response["sequence"]) != expected_sequence:
                        break
                    expected_sequence += 1
            except ProtocolError:
                break
            prefix.append(response)
        outputs = tuple(
            {
                "sequence": response["sequence"],
                "stream": response["stream"],
                "data": response["data"],
            }
            for response in prefix
            if response["type"] == "output"
        )
        return ExecutorExecutionLost(
            execution_id=str(request["execution_id"]),
            last_sequence=max(
                (int(output["sequence"]) for output in outputs),
                default=previous_cursor,
            ),
            responses=tuple(prefix),
            outputs=outputs,
        )

    @staticmethod
    def _merge_recovery_frames(
        context: ExecutorContext,
        responses: tuple[Mapping[str, object], ...],
        outputs: tuple[dict[str, object], ...],
        cursor: int,
        incoming: tuple[Mapping[str, object], ...],
    ) -> tuple[
        tuple[Mapping[str, object], ...],
        tuple[dict[str, object], ...],
        int,
    ]:
        merged_responses = list(responses)
        merged_outputs = list(outputs)
        encoded_bytes = sum(
            len(encode_response(dict(response))) for response in merged_responses
        )
        for response in incoming:
            frame_bytes = len(encode_response(dict(response)))
            if (
                len(merged_responses) >= MAX_EXECUTOR_RESPONSE_FRAMES
                or encoded_bytes + frame_bytes > MAX_EXECUTOR_RESPONSE_BYTES
            ):
                raise ExecutorExecutionLost(
                    execution_id=context.execution_id,
                    last_sequence=cursor,
                    responses=tuple(merged_responses),
                    outputs=tuple(merged_outputs),
                )
            merged_responses.append(response)
            encoded_bytes += frame_bytes
            if response["type"] == "output":
                cursor = int(response["sequence"])
                merged_outputs.append(
                    {
                        "sequence": response["sequence"],
                        "stream": response["stream"],
                        "data": response["data"],
                    }
                )
        return tuple(merged_responses), tuple(merged_outputs), cursor

    @staticmethod
    def _validate_output_cursor(
        outputs: tuple[dict[str, object], ...], previous_cursor: int
    ) -> None:
        expected = previous_cursor + 1
        for output in outputs:
            if int(output["sequence"]) != expected:
                raise ProtocolError("Executor output cursor is not contiguous")
            expected += 1

    @staticmethod
    def _validate_recovery_bounds(
        responses: tuple[Mapping[str, object], ...],
    ) -> None:
        if len(responses) > MAX_EXECUTOR_RESPONSE_FRAMES:
            raise ProtocolError("Executor aggregate recovery has too many frames")
        if (
            sum(len(encode_response(dict(response))) for response in responses)
            > MAX_EXECUTOR_RESPONSE_BYTES
        ):
            raise ProtocolError("Executor aggregate recovery is too large")
