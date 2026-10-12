from __future__ import annotations

import asyncio
import base64
import os
import stat
from pathlib import Path

import pytest

import backend.services.chat_sandbox_executor_channel as channel_module
from backend.chat_sandbox_worker.executor_daemon import EXECUTOR_BOOTSTRAP_PREFIX
from backend.chat_sandbox_worker.executor_protocol import (
    PROTOCOL,
    ProtocolError,
    decode_request,
    encode_response,
)
from backend.services.chat_sandbox_executor_channel import (
    ExecutorAttachment,
    PersistentSandboxExecutorChannel,
)
from backend.tests.chat_sandbox.executor_channel_harness import (
    _context,
    _operation_response,
    _read_frame,
    _write_frame,
)


async def _exercise_one_attached_channel_serves_all_operations_without_modal_exec(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "harness.sock"
    connection_count = 0
    attach_count = 0
    open_count = 0
    open_streams: set[str] = set()
    concurrent_execs: set[str] = set()
    overlap = asyncio.Event()
    large_file = b"a" * (1024 * 1024) + b"tail"

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal connection_count, attach_count, open_count
        connection_count += 1
        try:
            while True:
                frame = await _read_frame(reader)
                kind = frame["kind"]
                if kind == "attach":
                    attach_count += 1
                    await _write_frame(
                        writer,
                        {
                            "kind": "attached",
                            "request_id": frame["request_id"],
                            "stream_id": frame["stream_id"],
                            "harness_key_id": "harness-v1",
                            "authorization_key_id": "authorization-v1",
                        },
                    )
                    continue
                stream_id = str(frame["stream_id"])
                if kind == "open":
                    open_count += 1
                    open_streams.add(stream_id)
                    await _write_frame(
                        writer, {"kind": "opened", "stream_id": stream_id}
                    )
                    continue
                if kind == "close":
                    open_streams.discard(stream_id)
                    continue
                assert kind == "data"
                payload = base64.b64decode(frame["payload"], validate=True)
                request_frame = payload.splitlines(keepends=True)[-1]
                if payload.startswith(EXECUTOR_BOOTSTRAP_PREFIX):
                    assert b"capability-secret" in payload
                request = decode_request(request_frame)
                if request["type"] == "health":
                    response = encode_response(
                        {
                            "protocol": PROTOCOL,
                            "type": "health_result",
                            "request_id": request["request_id"],
                            "execution_id": request["execution_id"],
                            "status": "ok",
                        }
                    )
                elif request["type"] == "ensure_workspace":
                    response = _operation_response(
                        request, "acknowledged", operation="ensure_workspace"
                    )
                elif request["type"] == "read_file":
                    contents = (
                        large_file if request["path"] == "large.bin" else b"paper"
                    )
                    offset = int(request["offset"])
                    maximum = int(request["max_bytes"])
                    chunk = contents[offset : offset + maximum]
                    response = b"".join(
                        (
                            _operation_response(
                                request, "acknowledged", operation="read_file"
                            ),
                            _operation_response(
                                request,
                                "read_result",
                                path=request["path"],
                                offset=request["offset"],
                                data_base64=base64.b64encode(chunk).decode(),
                                eof=offset + len(chunk) >= len(contents),
                            ),
                        )
                    )
                elif request["type"] == "cancel_execution":
                    response = b"".join(
                        (
                            _operation_response(
                                request,
                                "acknowledged",
                                operation="cancel_execution",
                            ),
                            _operation_response(
                                request,
                                "terminal",
                                status="cancelled",
                                exit_code=None,
                                error=None,
                            ),
                        )
                    )
                else:
                    assert request["type"] == "exec"

                    async def finish_exec(
                        request: dict[str, object] = request,
                        stream_id: str = stream_id,
                    ) -> None:
                        await asyncio.wait_for(overlap.wait(), timeout=1)
                        response = b"".join(
                            (
                                _operation_response(
                                    request, "acknowledged", operation="exec"
                                ),
                                _operation_response(
                                    request,
                                    "terminal",
                                    status="completed",
                                    exit_code=0,
                                    error=None,
                                ),
                            )
                        )
                        await _write_frame(
                            writer,
                            {
                                "kind": "data",
                                "stream_id": stream_id,
                                "payload": base64.b64encode(response).decode(),
                            },
                        )
                        await _write_frame(
                            writer, {"kind": "closed", "stream_id": stream_id}
                        )
                        open_streams.discard(stream_id)

                    if request["command"] == "overlap":
                        concurrent_execs.add(str(request["execution_id"]))
                        if len(concurrent_execs) == 4:
                            overlap.set()
                        asyncio.create_task(finish_exec())
                        continue
                    response = b"".join(
                        (
                            _operation_response(
                                request, "acknowledged", operation="exec"
                            ),
                            _operation_response(
                                request,
                                "terminal",
                                status="completed",
                                exit_code=0,
                                error=None,
                            ),
                        )
                    )
                await _write_frame(
                    writer,
                    {
                        "kind": "data",
                        "stream_id": stream_id,
                        "payload": base64.b64encode(response).decode(),
                    },
                )
                await _write_frame(writer, {"kind": "closed", "stream_id": stream_id})
                open_streams.discard(stream_id)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(serve, path=socket_path)
    os.chmod(socket_path, 0o660)
    channel = PersistentSandboxExecutorChannel(socket_path)
    try:
        await channel.attach_environment(
            ExecutorAttachment(
                environment_id="environment-v1",
                environment_generation=3,
                registration_id="registration-v1",
                shard_generation=5,
                stream_id="33" * 16,
                protocol_version=1,
                schema_digest="11" * 32,
                authorization_id="22" * 16,
                expires_at=2_000_000_000,
                harness_key_id="harness-v1",
                authorization_key_id="authorization-v1",
                environment_noise_key_id="44" * 32,
                environment_public_key={
                    "suite": "Noise_hybridIK_X25519+MLKEM768_AESGCM_SHA256",
                    "x25519_public_key": "public-x25519",
                    "mlkem768_public_key": "public-mlkem",
                },
            )
        )
        assert await channel.health() == "ok"
        context = _context("ensure-v1", "ensure-v1")
        await channel.ensure_workspace(context)
        read = await channel.read_file(
            _context("read-v1", "read-v1"),
            path="/workspace/paper.txt",
            offset=0,
            max_bytes=16,
        )
        assert read.data == b"paper"
        first = await channel.read_file(
            _context("large-v1", "large-v1"),
            path="large.bin",
            offset=0,
            max_bytes=1024 * 1024,
        )
        second = await channel.read_file(
            _context("large-v2", "large-v2"),
            path="large.bin",
            offset=len(first.data),
            max_bytes=1024 * 1024,
        )
        assert first.eof is False
        assert second.eof is True
        assert first.data + second.data == large_file
        for index in range(10):
            sequential = await channel.exec_resumable(
                _context(f"sequential-{index}", f"sequential-{index}"),
                command="true",
                timeout_ms=1_000,
            )
            assert sequential.terminal["status"] == "completed"
        results = await asyncio.gather(
            *(
                channel.exec_resumable(
                    _context(f"exec-{index}", f"exec-{index}"),
                    command="overlap",
                    timeout_ms=1_000,
                )
                for index in range(4)
            )
        )
        assert [result.terminal["status"] for result in results] == ["completed"] * 4
        assert await channel.cancel(_context("cancel-v1", "cancel-v1")) is True
        previous_open_count = open_count
        with pytest.raises(ProtocolError):
            await channel.exec_resumable(
                _context("invalid-v1", "invalid-v1"),
                command="x" * (64 * 1024 + 1),
                timeout_ms=1_000,
            )
        with pytest.raises(ProtocolError):
            await channel.read_file(
                _context("invalid-v2", "invalid-v2"),
                path="../credential",
                offset=0,
                max_bytes=1,
            )
        assert open_count == previous_open_count
        assert connection_count == 1
        assert attach_count == 1
        assert not open_streams
    finally:
        await channel.aclose()
        server.close()
        await server.wait_closed()


def test_one_attached_channel_serves_all_operations_without_modal_exec(
    tmp_path: Path,
) -> None:
    asyncio.run(
        _exercise_one_attached_channel_serves_all_operations_without_modal_exec(
            tmp_path
        )
    )


async def _exercise_channel_rejects_unprotected_or_non_socket_paths(
    tmp_path: Path,
) -> None:
    ordinary_file = tmp_path / "harness.sock"
    ordinary_file.write_bytes(b"")
    channel = PersistentSandboxExecutorChannel(ordinary_file)
    with pytest.raises(PermissionError, match="protected Unix socket"):
        await channel.connect()

    ordinary_file.unlink()
    server = await asyncio.start_unix_server(
        lambda _reader, _writer: None, path=ordinary_file
    )
    os.chmod(ordinary_file, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
    try:
        with pytest.raises(PermissionError, match="protected Unix socket"):
            await channel.connect()
    finally:
        server.close()
        await server.wait_closed()


def test_channel_rejects_unprotected_or_non_socket_paths(tmp_path: Path) -> None:
    asyncio.run(_exercise_channel_rejects_unprotected_or_non_socket_paths(tmp_path))


async def _exercise_channel_accepts_protected_backend_group_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_path = tmp_path / "harness.sock"
    server = await asyncio.start_unix_server(
        lambda _reader, _writer: None, path=socket_path
    )
    os.chmod(socket_path, 0o660)
    socket_group = socket_path.stat().st_gid
    monkeypatch.setattr(channel_module.os, "geteuid", lambda: os.getuid() + 1)
    monkeypatch.setattr(channel_module.os, "getegid", lambda: socket_group)
    monkeypatch.setattr(channel_module.os, "getgroups", lambda: [])
    try:
        PersistentSandboxExecutorChannel(socket_path)._validate_socket()
    finally:
        server.close()
        await server.wait_closed()


def test_channel_accepts_protected_backend_group_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(
        _exercise_channel_accepts_protected_backend_group_socket(tmp_path, monkeypatch)
    )
