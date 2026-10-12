from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from backend.chat_sandbox_worker.executor_protocol import decode_request
from backend.services.chat_sandbox_executor import (
    ExecutorExecutionLost,
    ExecutorTransportError,
)
from backend.services.chat_sandbox_executor_channel import (
    PersistentSandboxExecutorChannel,
)
from backend.tests.chat_sandbox.executor_channel_harness import (
    _context,
    _operation_response,
    _read_frame,
    _write_frame,
)


async def _exercise(tmp_path: Path, mode: str) -> None:
    path = tmp_path / "pipeline.sock"
    received = asyncio.Event()
    allow_ack = asyncio.Event()
    finished = asyncio.Event()
    requests = []
    errors = []

    async def serve(reader, writer):
        try:
            while True:
                opened = await _read_frame(reader)
                assert opened["kind"] == "open"
                # Deliberately withhold opened until the payload is received:
                # the former serial implementation cannot pass this exchange.
                data = await _read_frame(reader)
                assert data["kind"] == "data"
                assert data["stream_id"] == opened["stream_id"]
                request = decode_request(
                    base64.b64decode(data["payload"]).splitlines(keepends=True)[-1]
                )
                requests.append(request)
                received.set()
                if mode == "disconnect":
                    return
                if mode in {"timeout", "cancel"}:
                    await reader.read()
                    return
                if mode == "delayed":
                    await allow_ack.wait()
                if mode == "lost" and request["type"] == "exec":
                    # The command may already have executed, but opened was lost.
                    await _write_frame(
                        writer, {"kind": "closed", "stream_id": opened["stream_id"]}
                    )
                    continue
                await _write_frame(
                    writer, {"kind": "opened", "stream_id": opened["stream_id"]}
                )
                response = b"".join(
                    [
                        _operation_response(
                            request, "acknowledged", operation=request["type"]
                        ),
                        _operation_response(
                            request,
                            "terminal",
                            status="completed",
                            exit_code=0,
                            error=None,
                        ),
                    ]
                )
                await _write_frame(
                    writer,
                    {
                        "kind": "data",
                        "stream_id": opened["stream_id"],
                        "payload": base64.b64encode(response).decode(),
                    },
                )
                await _write_frame(
                    writer, {"kind": "closed", "stream_id": opened["stream_id"]}
                )
        except asyncio.IncompleteReadError:
            pass
        except BaseException as error:
            errors.append(error)
        finally:
            writer.close()
            await writer.wait_closed()
            finished.set()

    server = await asyncio.start_unix_server(serve, path=path)
    path.chmod(0o600)
    channel = PersistentSandboxExecutorChannel(path)
    task = None
    try:
        await channel.connect()
        # Attachment authentication is covered by the existing channel suite.
        channel._attachment = object()
        context = _context("same-execution", "one-command")
        if mode in {"disconnect", "timeout", "cancel"}:
            operation = channel._client.exec(context, command="true", timeout_ms=1000)
        else:
            operation = channel.exec_resumable(context, command="true", timeout_ms=1000)
        task = asyncio.create_task(operation)
        await asyncio.wait_for(received.wait(), 1)
        if mode == "delayed":
            assert not task.done(), "acknowledgement is still mandatory"
            allow_ack.set()
        if mode == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif mode in {"disconnect", "timeout"}:
            with pytest.raises(ExecutorExecutionLost):
                await asyncio.wait_for(task, 3)
        else:
            result = await asyncio.wait_for(task, 3)
            assert result.terminal["exit_code"] == 0
            assert result.recovered is (mode == "lost")
        assert [r["type"] for r in requests] == (
            ["exec", "attach_execution"] if mode == "lost" else ["exec"]
        )
        assert all(r["execution_id"] == "same-execution" for r in requests)
        assert not channel._open_pending
        assert not channel._streams
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await channel.aclose()
        server.close()
        await server.wait_closed()
        await asyncio.wait_for(finished.wait(), 1)
    assert not errors


@pytest.mark.parametrize("mode", ["delayed", "lost", "disconnect", "timeout", "cancel"])
def test_stream_pipeline_retains_ack_and_execution_recovery(tmp_path, mode):
    asyncio.run(_exercise(tmp_path, mode))


@pytest.mark.parametrize("fail_kind", ["open", "data"])
def test_send_failure_preserves_attempted_delivery_classification(tmp_path, fail_kind):
    async def exercise():
        channel = PersistentSandboxExecutorChannel(tmp_path / "unused.sock")
        channel._attachment = object()
        sent = []

        async def send(frame):
            sent.append(frame["kind"])
            if frame["kind"] == fail_kind:
                raise ConnectionError("injected send failure")

        channel._send = send
        expected = (
            ExecutorTransportError if fail_kind == "open" else ExecutorExecutionLost
        )
        with pytest.raises(expected) as caught:
            await channel._client.exec(
                _context("one", "one"), command="true", timeout_ms=1000
            )
        if fail_kind == "open":
            assert caught.value.payload_delivery_attempted is False
        assert sent == (["open"] if fail_kind == "open" else ["open", "data"])
        assert not channel._streams and not channel._open_pending

    asyncio.run(exercise())


def test_four_streams_can_send_before_individually_correlated_acknowledgements(
    tmp_path,
):
    async def exercise():
        channel = PersistentSandboxExecutorChannel(tmp_path / "unused.sock")
        channel._attachment = object()
        sent = []
        all_data = asyncio.Event()

        async def send(frame):
            sent.append(frame)
            if sum(f["kind"] == "data" for f in sent) == 4:
                all_data.set()

        channel._send = send
        relays = [await channel._open_stream() for _ in range(4)]
        for relay in relays:
            relay.stdin.write(b"request")
        tasks = [asyncio.create_task(relay.stdin.flush()) for relay in relays]
        try:
            await asyncio.wait_for(all_data.wait(), 1)
            assert not any(task.done() for task in tasks)
            for relay in reversed(relays):
                await channel._dispatch(
                    {"kind": "opened", "stream_id": relay.stream_id}
                )
            await asyncio.wait_for(asyncio.gather(*tasks), 1)
            assert not channel._open_pending
            for relay in relays:
                await channel._dispatch(
                    {"kind": "closed", "stream_id": relay.stream_id}
                )
            assert not channel._streams
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await channel.aclose()

    asyncio.run(exercise())


def test_late_ack_is_rejected_even_while_payload_drain_is_blocked(tmp_path):
    async def exercise():
        channel = PersistentSandboxExecutorChannel(tmp_path / "unused.sock")
        channel._attachment = object()
        sending = asyncio.Event()
        drained = asyncio.Event()

        async def send(frame):
            if frame["kind"] == "data":
                sending.set()
                await drained.wait()

        channel._send = send
        relay = await channel._open_stream()
        relay.stdin.write(b"request")
        task = asyncio.create_task(relay.stdin.flush())
        try:
            await asyncio.wait_for(sending.wait(), 1)
            relay._open_deadline = asyncio.get_running_loop().time() - 1
            await channel._dispatch({"kind": "opened", "stream_id": relay.stream_id})
            drained.set()
            with pytest.raises(TimeoutError):
                await task
            assert not channel._streams and not channel._open_pending
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await channel.aclose()

    asyncio.run(exercise())


@pytest.mark.parametrize("acknowledge", [False, True])
def test_ack_deadline_runs_during_payload_backpressure(tmp_path, acknowledge):
    async def exercise():
        channel = PersistentSandboxExecutorChannel(tmp_path / "unused.sock")
        channel._attachment = object()
        sending = asyncio.Event()
        drain = asyncio.Event()
        cancelled = asyncio.Event()

        async def send(frame):
            if frame["kind"] == "data":
                sending.set()
                try:
                    await drain.wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        channel._send = send
        relay = await channel._open_stream()
        relay._open_deadline = asyncio.get_running_loop().time() + 0.1
        relay.stdin.write(b"request")
        task = asyncio.create_task(relay.stdin.flush())
        try:
            await asyncio.wait_for(sending.wait(), 1)
            if acknowledge:
                await channel._dispatch(
                    {"kind": "opened", "stream_id": relay.stream_id}
                )
                await asyncio.sleep(0.15)
                assert not task.done() and not cancelled.is_set()
                drain.set()
                await task
                await channel._dispatch(
                    {"kind": "closed", "stream_id": relay.stream_id}
                )
            else:
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(task, 1)
                assert cancelled.is_set()
            assert not channel._streams and not channel._open_pending
            assert relay._opening_timeout is None
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await channel.aclose()

    asyncio.run(exercise())
