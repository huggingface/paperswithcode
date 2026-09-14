"""Multiplex executor RPCs over one protected local harness connection."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import stat
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from backend.chat_sandbox_worker.executor_protocol import (
    validate_remote_exec_request,
    validate_remote_read_request,
)
from backend.services.chat_sandbox_executor import (
    ExecutorContext,
    ExecutorExecutionResult,
    ExecutorReadResult,
    SandboxExecutorClient,
)

MAX_LOCAL_FRAME_BYTES = 2 * 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class ExecutorAttachment:
    """Content-free routing and single-use authorization identity."""

    environment_id: str
    environment_generation: int
    registration_id: str
    shard_generation: int
    stream_id: str
    protocol_version: int
    schema_digest: str
    authorization_id: str
    expires_at: int
    harness_key_id: str
    authorization_key_id: str
    environment_noise_key_id: str
    environment_public_key: Mapping[str, str]

    def frame(self, request_id: str) -> dict[str, object]:
        for value in (
            self.environment_id,
            self.registration_id,
            self.stream_id,
            self.harness_key_id,
            self.authorization_key_id,
            self.environment_noise_key_id,
        ):
            if _IDENTIFIER.fullmatch(value) is None:
                raise ValueError("Executor attachment identity is invalid")
        if (
            min(
                self.environment_generation,
                self.shard_generation,
                self.protocol_version,
                self.expires_at,
            )
            <= 0
            or not _hex(self.schema_digest, 32)
            or not _hex(self.authorization_id, 16)
            or set(self.environment_public_key)
            != {"suite", "x25519_public_key", "mlkem768_public_key"}
            or any(
                not isinstance(value, str) or not value or len(value) > 2_048
                for value in self.environment_public_key.values()
            )
        ):
            raise ValueError("Executor attachment fence is invalid")
        return {
            "kind": "attach",
            "request_id": request_id,
            "environment_id": self.environment_id,
            "environment_generation": self.environment_generation,
            "registration_id": self.registration_id,
            "shard_generation": self.shard_generation,
            "stream_id": self.stream_id,
            "protocol_version": self.protocol_version,
            "schema_digest": self.schema_digest,
            "authorization_id": self.authorization_id,
            "expires_at": self.expires_at,
            "harness_key_id": self.harness_key_id,
            "authorization_key_id": self.authorization_key_id,
            "environment_noise_key_id": self.environment_noise_key_id,
            "environment_public_key": dict(self.environment_public_key),
        }


def _hex(value: str, byte_length: int) -> bool:
    if len(value) != byte_length * 2:
        return False
    try:
        return len(bytes.fromhex(value)) == byte_length
    except ValueError:
        return False


class _Drain:
    def __init__(self, writer: _VirtualWriter) -> None:
        self._writer = writer

    async def aio(self) -> None:
        await self._writer.flush()


class _VirtualWriter:
    def __init__(self, relay: _VirtualRelay) -> None:
        self._relay = relay
        self._pending = bytearray()
        self._eof = False
        self.drain = _Drain(self)

    def write(self, value: bytes) -> None:
        if self._eof:
            raise BrokenPipeError("Executor virtual stream is closed")
        self._pending.extend(value)
        if len(self._pending) > MAX_LOCAL_FRAME_BYTES:
            raise ValueError("Executor local stream payload is too large")

    def write_eof(self) -> None:
        self._eof = True

    async def flush(self) -> None:
        if not self._pending:
            raise ValueError("Executor local stream payload is empty")
        payload = bytes(self._pending)
        self._pending.clear()
        await self._relay._channel._send(
            {
                "kind": "data",
                "stream_id": self._relay.stream_id,
                "payload": base64.b64encode(payload).decode("ascii"),
                "eof": self._eof,
            }
        )


class _VirtualStdout:
    def __init__(self, relay: _VirtualRelay) -> None:
        self._relay = relay

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        value = await self._relay._incoming.get()
        if value is None:
            raise StopAsyncIteration
        if isinstance(value, BaseException):
            raise value
        return value


class _Wait:
    def __init__(self, relay: _VirtualRelay) -> None:
        self._relay = relay

    async def aio(self) -> None:
        await self._relay._closed.wait()


class _VirtualRelay:
    def __init__(self, channel: PersistentSandboxExecutorChannel, stream_id: str):
        self._channel = channel
        self.stream_id = stream_id
        self._incoming: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue()
        self._closed = asyncio.Event()
        self.stdin = _VirtualWriter(self)
        self.stdout = _VirtualStdout(self)
        self.wait = _Wait(self)

    async def close(self) -> None:
        if not self._closed.is_set():
            await self._channel._send({"kind": "close", "stream_id": self.stream_id})
            self._finish()

    def _finish(self, error: BaseException | None = None) -> None:
        if self._closed.is_set():
            return
        if error is not None:
            self._incoming.put_nowait(error)
        self._incoming.put_nowait(None)
        self._closed.set()


class _ChannelRelayProvider:
    def __init__(self, channel: PersistentSandboxExecutorChannel) -> None:
        self._channel = channel

    async def open_executor_relay(
        self, _sandbox: object, *, timeout_seconds: int
    ) -> _VirtualRelay:
        async with asyncio.timeout(timeout_seconds):
            return await self._channel._open_stream()


class PersistentSandboxExecutorChannel:
    """One harness attachment containing many executor operation streams."""

    def __init__(self, socket_path: Path | str) -> None:
        self.socket_path = Path(socket_path)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._connect_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[dict[str, object]]] = {}
        self._open_pending: dict[str, asyncio.Future[None]] = {}
        self._streams: dict[str, _VirtualRelay] = {}
        self._counter = 0
        self._attachment: ExecutorAttachment | None = None
        self._client = SandboxExecutorClient(_ChannelRelayProvider(self))

    async def connect(self) -> None:
        async with self._connect_lock:
            if self._writer is not None:
                return
            self._validate_socket()
            reader, writer = await asyncio.open_unix_connection(self.socket_path)
            self._reader = reader
            self._writer = writer
            self._reader_task = asyncio.create_task(self._read_frames())

    def _validate_socket(self) -> None:
        metadata = self.socket_path.stat()
        parent = self.socket_path.parent.stat()
        trusted_groups = {os.getegid(), *os.getgroups()}
        if (
            not stat.S_ISSOCK(metadata.st_mode)
            or metadata.st_mode & 0o007
            or parent.st_mode & 0o022
            or (
                metadata.st_uid not in {0, os.geteuid()}
                and metadata.st_gid not in trusted_groups
            )
        ):
            raise PermissionError("Executor harness requires a protected Unix socket")

    async def attach_environment(self, attachment: ExecutorAttachment) -> None:
        if self._attachment is not None:
            if self._attachment == attachment:
                return
            raise RuntimeError("Executor channel is already attached")
        await self.connect()
        request_id = self._next_id("attach")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, object]] = loop.create_future()
        self._pending[request_id] = future
        try:
            await self._send(attachment.frame(request_id))
            async with asyncio.timeout(2):
                response = await future
        finally:
            self._pending.pop(request_id, None)
        if (
            response.get("kind") != "attached"
            or response.get("stream_id") != attachment.stream_id
            or response.get("harness_key_id") != attachment.harness_key_id
            or response.get("authorization_key_id") != attachment.authorization_key_id
        ):
            raise RuntimeError("Executor harness attachment was rejected")
        self._attachment = attachment

    async def health(self) -> str:
        self._require_attached()
        return await self._client.health(object())

    async def ensure_workspace(self, context: ExecutorContext) -> None:
        self._require_attached()
        await self._client.ensure_workspace(context)

    async def release_workspace(self, context: ExecutorContext) -> None:
        self._require_attached()
        await self._client.release_workspace(context)

    async def exec_resumable(
        self,
        context: ExecutorContext,
        *,
        command: str,
        timeout_ms: int,
        max_attach_attempts: int = 2,
    ) -> ExecutorExecutionResult:
        validate_remote_exec_request(command, timeout_ms)
        self._require_attached()
        return await self._client.exec_resumable(
            context,
            command=command,
            timeout_ms=timeout_ms,
            max_attach_attempts=max_attach_attempts,
        )

    async def read_file(
        self,
        context: ExecutorContext,
        *,
        path: str,
        offset: int,
        max_bytes: int,
    ) -> ExecutorReadResult:
        validate_remote_read_request(path, offset, max_bytes)
        self._require_attached()
        return await self._client.read_file(
            context, path=path, offset=offset, max_bytes=max_bytes
        )

    async def cancel(self, context: ExecutorContext) -> bool:
        self._require_attached()
        result = await self._client.cancel_execution(context)
        return result.terminal.get("status") == "cancelled"

    def _require_attached(self) -> None:
        if self._attachment is None:
            raise RuntimeError("Executor channel is not attached")

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"

    async def _open_stream(self) -> _VirtualRelay:
        self._require_attached()
        stream_id = self._next_id("operation")
        relay = _VirtualRelay(self, stream_id)
        loop = asyncio.get_running_loop()
        opened: asyncio.Future[None] = loop.create_future()
        self._streams[stream_id] = relay
        self._open_pending[stream_id] = opened
        try:
            await self._send({"kind": "open", "stream_id": stream_id})
            async with asyncio.timeout(2):
                await opened
            return relay
        except BaseException:
            self._streams.pop(stream_id, None)
            relay._finish()
            raise
        finally:
            self._open_pending.pop(stream_id, None)

    async def _send(self, frame: dict[str, object]) -> None:
        writer = self._writer
        if writer is None:
            raise ConnectionError("Executor harness connection is unavailable")
        encoded = json.dumps(frame, separators=(",", ":")).encode()
        if not encoded or len(encoded) > MAX_LOCAL_FRAME_BYTES:
            raise ValueError("Executor harness frame is invalid")
        async with self._write_lock:
            writer.write(len(encoded).to_bytes(4, "big") + encoded)
            await writer.drain()

    async def _read_frames(self) -> None:
        assert self._reader is not None
        error: BaseException | None = None
        try:
            while True:
                length = int.from_bytes(await self._reader.readexactly(4), "big")
                if not 0 < length <= MAX_LOCAL_FRAME_BYTES:
                    raise ValueError("Executor harness frame is invalid")
                frame = json.loads(await self._reader.readexactly(length))
                if not isinstance(frame, dict):
                    raise ValueError("Executor harness frame is invalid")
                await self._dispatch(frame)
        except asyncio.CancelledError:
            raise
        except BaseException as caught:
            error = caught
        finally:
            self._fail_pending(error or ConnectionError("Executor harness closed"))

    async def _dispatch(self, frame: dict[str, object]) -> None:
        request_id = frame.get("request_id")
        if isinstance(request_id, str) and request_id in self._pending:
            future = self._pending[request_id]
            if not future.done():
                future.set_result(frame)
            return
        stream_id = frame.get("stream_id")
        if not isinstance(stream_id, str):
            raise ValueError("Executor harness stream identity is invalid")
        if frame.get("kind") == "opened":
            future = self._open_pending.get(stream_id)
            if future is None:
                raise ValueError("Executor harness opened an unknown stream")
            if not future.done():
                future.set_result(None)
            return
        relay = self._streams.get(stream_id)
        if relay is None:
            raise ValueError("Executor harness referenced an unknown stream")
        if frame.get("kind") == "data":
            payload = frame.get("payload")
            if not isinstance(payload, str):
                raise ValueError("Executor harness data frame is invalid")
            try:
                decoded = base64.b64decode(payload, validate=True)
            except ValueError as caught:
                raise ValueError("Executor harness data frame is invalid") from caught
            if len(decoded) > MAX_LOCAL_FRAME_BYTES:
                raise ValueError("Executor harness data frame is invalid")
            relay._incoming.put_nowait(decoded)
            return
        if frame.get("kind") == "closed":
            self._streams.pop(stream_id, None)
            relay._finish()
            return
        raise ValueError("Executor harness frame kind is invalid")

    def _fail_pending(self, error: BaseException) -> None:
        for future in (*self._pending.values(), *self._open_pending.values()):
            if not future.done():
                future.set_exception(error)
        for relay in self._streams.values():
            relay._finish(error)
        self._streams.clear()

    async def aclose(self) -> None:
        for relay in tuple(self._streams.values()):
            relay._finish()
        self._streams.clear()
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
            self._writer = None
        if self._reader_task is not None:
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
            self._reader_task = None
