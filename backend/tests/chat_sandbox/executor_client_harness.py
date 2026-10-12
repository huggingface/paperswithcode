"""Fake broker, process, and providers for executor client tests."""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path


from backend.chat_sandbox_worker.executor_protocol import (
    encode_response,
)


class _AsyncCall:
    def __init__(self, function):
        self.aio = function


class _Input:
    def __init__(
        self,
        *,
        write_error: Exception | None = None,
        drain_error: Exception | None = None,
        partial_write_bytes: int = 0,
    ):
        self.writes: list[bytes] = []
        self.write_attempts = 0
        self.eof_writes = 0
        self.write_error = write_error
        self.drain_error = drain_error
        self.partial_write_bytes = partial_write_bytes
        self.drain = _AsyncCall(self._drain)

    def write(self, value: bytes) -> None:
        self.write_attempts += 1
        if self.write_error is not None:
            if self.partial_write_bytes:
                self.writes.append(value[: self.partial_write_bytes])
            raise self.write_error
        self.writes.append(value)

    def write_eof(self) -> None:
        self.eof_writes += 1

    async def _drain(self) -> None:
        if self.drain_error is not None:
            raise self.drain_error
        return None


class _Output:
    def __init__(self, chunks: list[bytes], error: Exception | None = None):
        self.chunks = chunks
        self.error = error

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error


class _Process:
    def __init__(
        self,
        frames: list[dict],
        *,
        error: Exception | None = None,
        trailing: bytes = b"",
        stdin: _Input | None = None,
    ):
        self.stdin = stdin or _Input()
        self.stdout = _Output(
            [encode_response(frame) for frame in frames] + [trailing], error
        )
        self.returncode = 0
        self.wait = _AsyncCall(self._wait)

    async def _wait(self) -> None:
        return None


class _Provider:
    def __init__(self, processes: list[_Process]):
        self.processes = processes
        self.calls: list[tuple[object, int]] = []

    async def open_executor_relay(self, sandbox, *, timeout_seconds):
        self.calls.append((sandbox, timeout_seconds))
        return self.processes.pop(0)


class _SocketProcess:
    def __init__(self, connection: socket.socket):
        self.connection = connection
        self.stdin = _SocketInput(connection)
        self.stdout = _SocketOutput(connection)
        self.wait = _AsyncCall(self._wait)

    async def _wait(self) -> None:
        self.connection.close()


class _SocketInput:
    def __init__(self, connection: socket.socket):
        self.connection = connection
        self.writes = []
        self.drain = _AsyncCall(self._drain)

    def write(self, value: bytes) -> None:
        self.writes.append(value)
        self.connection.sendall(value)

    def write_eof(self) -> None:
        self.connection.shutdown(socket.SHUT_WR)

    async def _drain(self) -> None:
        return None


class _SocketOutput:
    def __init__(self, connection: socket.socket):
        self.connection = connection

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        while data := await asyncio.to_thread(self.connection.recv, 64 * 1024):
            yield data


class _SocketProvider:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self.calls = 0
        self.processes = []

    async def open_executor_relay(self, _sandbox, *, timeout_seconds):
        assert timeout_seconds in {1, 6, 10, 15, 30}
        self.calls += 1
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.connect(str(self.socket_path))
        process = _SocketProcess(connection)
        self.processes.append(process)
        return process


class _DropAfterFramesOutput:
    def __init__(self, connection: socket.socket, frame_count: int):
        self.connection = connection
        self.frame_count = frame_count

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        buffer = b""
        for _index in range(self.frame_count):
            while b"\n" not in buffer:
                chunk = await asyncio.to_thread(self.connection.recv, 64 * 1024)
                if not chunk:
                    raise ConnectionResetError("executor response ended before fault")
                buffer += chunk
            line, buffer = buffer.split(b"\n", 1)
            yield line + b"\n"
        self.connection.close()
        raise ConnectionResetError("executor response fault injected")


class _DropAfterFramesProcess(_SocketProcess):
    def __init__(self, connection: socket.socket, frame_count: int):
        super().__init__(connection)
        self.stdout = _DropAfterFramesOutput(connection, frame_count)


class _DropFirstResponseSocketProvider(_SocketProvider):
    def __init__(
        self, socket_path: Path, *, drop_after_frames: int, drop_on_call: int = 1
    ):
        super().__init__(socket_path)
        self.drop_after_frames = drop_after_frames
        self.drop_on_call = drop_on_call

    async def open_executor_relay(self, _sandbox, *, timeout_seconds):
        assert timeout_seconds in {1, 6, 10, 15, 30}
        self.calls += 1
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.connect(str(self.socket_path))
        if self.calls == self.drop_on_call:
            process = _DropAfterFramesProcess(connection, self.drop_after_frames)
        else:
            process = _SocketProcess(connection)
        self.processes.append(process)
        return process


class _Broker:
    def __init__(self):
        self.active = False

    def __call__(self, request):
        if request["operation"] == "install":
            self.active = True
        elif request["operation"] == "clear":
            self.active = False
        return {"ok": True, "active": self.active}
