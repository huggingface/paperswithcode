"""Durable persistence receipts and terminal acknowledgements."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.tests.external_pi.turn_runner.harness import (
    FakeExecutor,
    FakeProvider,
    FakeSocket,
    FakeWorkspaceManager,
    SocketContext,
    _async_value,
    _tool_runner,
)


@pytest.mark.parametrize("persist", [False, True])
def test_durable_worker_ack_requires_persistence_receipt(monkeypatch, persist):
    async def scenario():
        runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
        runner.settings.chat_durable_turn_dispatch_enabled = True
        socket = FakeSocket(
            [
                '{"type":"worker_ready","durable_event_ack":true,"worker_sequence":1}',
                '{"type":"answer_delta","text":"hello","worker_sequence":2}',
                '{"type":"worker_done","status":"complete","worker_sequence":3}',
            ]
        )
        monkeypatch.setattr(
            runner,
            "_select_worker_claim",
            lambda: _async_value(runner.external_worker_claim),
        )
        control = FakeSocket([])
        sockets = iter([socket, control])
        monkeypatch.setattr(
            runner, "_external_worker_socket", lambda _: SocketContext(next(sockets))
        )
        events = runner._events(SimpleNamespace(reject=lambda: None))
        event = await anext(events)
        assert json.loads(json.dumps(event)) == {
            "type": "answer_delta",
            "text": "hello",
        }
        assert [json.loads(frame)["type"] for frame in socket.sent] == ["run_turn"]
        if persist:
            await event.after_persist()
            assert json.loads(socket.sent[-1])["type"] == "ack_events"
            assert json.loads(socket.sent[-1])["sequence"] == 2
        with pytest.raises(StopAsyncIteration):
            await anext(events)
        assert [json.loads(frame)["type"] for frame in socket.sent] == (
            ["run_turn", "ack_events", "ack_terminal"] if persist else ["run_turn"]
        )
        # Delayed persistence after socket closure is harmless.
        await event.after_persist()
        assert [json.loads(frame)["type"] for frame in control.sent] == (
            [] if persist else ["ack_terminal"]
        )
        await event.after_persist()  # duplicate receipts do not open another socket

    asyncio.run(scenario())


@pytest.mark.parametrize("closing", [False, True])
def test_late_terminal_receipt_releases_worker_during_socket_cleanup(
    monkeypatch, closing
):
    async def scenario():
        runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
        runner.settings.chat_durable_turn_dispatch_enabled = True
        socket = FakeSocket(
            [
                '{"type":"worker_ready","durable_event_ack":true,"worker_sequence":1}',
                '{"type":"done","finish_reason":"success","worker_sequence":2}',
                '{"type":"worker_done","status":"complete","worker_sequence":3}',
            ]
        )
        control = FakeSocket([])
        entered_cleanup = asyncio.Event()
        release_cleanup = asyncio.Event()

        class ClosingContext(SocketContext):
            async def __aexit__(self, *_args):
                entered_cleanup.set()
                await release_cleanup.wait()

        contexts = iter([ClosingContext(socket), SocketContext(control)])
        monkeypatch.setattr(
            runner,
            "_select_worker_claim",
            lambda: _async_value(runner.external_worker_claim),
        )
        monkeypatch.setattr(runner, "_external_worker_socket", lambda _: next(contexts))
        events = runner._events(SimpleNamespace(reject=lambda: None))
        event = await anext(events)
        finish = asyncio.create_task(anext(events))
        await entered_cleanup.wait()
        if not closing:
            release_cleanup.set()
            with pytest.raises(StopAsyncIteration):
                await finish
        await event.after_persist()
        assert [json.loads(frame)["type"] for frame in control.sent] == ["ack_terminal"]
        assert json.loads(control.sent[0])["sequence"] == 3
        release_cleanup.set()
        if closing:
            with pytest.raises(StopAsyncIteration):
                await finish

    asyncio.run(scenario())


def test_lost_receipt_reconnects_without_duplicate_public_events(monkeypatch):
    async def scenario():
        runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
        runner.settings.chat_durable_turn_dispatch_enabled = True

        class LostReceiptSocket(FakeSocket):
            async def send(self, value):
                await super().send(value)
                if json.loads(value)["type"] == "ack_events":
                    raise OSError("receipt lost")

        first = LostReceiptSocket(
            [
                '{"type":"worker_ready","durable_event_ack":true,"worker_sequence":1}',
                '{"type":"answer_delta","text":"hello","worker_sequence":2}',
                OSError("connection lost"),
            ]
        )
        second = FakeSocket(
            [
                '{"type":"answer_delta","text":"hello","worker_sequence":2}',
                '{"type":"done","finish_reason":"success","worker_sequence":3}',
                '{"type":"worker_done","status":"complete","worker_sequence":4}',
            ]
        )
        sockets = iter([first, second])
        monkeypatch.setattr(
            runner,
            "_select_worker_claim",
            lambda: _async_value(runner.external_worker_claim),
        )
        monkeypatch.setattr(
            runner, "_require_same_external_worker_claim", lambda _: _async_value(None)
        )
        monkeypatch.setattr(
            runner, "_external_worker_socket", lambda _: SocketContext(next(sockets))
        )
        events = []
        async for event in runner._events(SimpleNamespace(reject=lambda: None)):
            events.append(event["type"])
            await event.after_persist()
        assert events == ["answer_delta", "done"]
        sent = [json.loads(frame) for frame in second.sent]
        assert sent[0]["type"] == "attach_turn"
        assert sent[0]["afterSequence"] == 2
        assert sent[1]["type"] == "ack_events"
        assert sent[1]["sequence"] == 3
        assert sent[2]["type"] == "ack_terminal"

    asyncio.run(scenario())


@pytest.mark.parametrize("durable", [False, True])
@pytest.mark.parametrize("persist_before_terminal", [False, True])
def test_terminal_ack_handles_trailing_tool_without_journal_receipt(
    monkeypatch, durable, persist_before_terminal
):
    async def scenario():
        runner = _tool_runner(FakeExecutor(), FakeWorkspaceManager(FakeProvider()))
        runner.settings.chat_durable_turn_dispatch_enabled = durable
        socket = FakeSocket(
            [
                '{"type":"worker_ready","durable_event_ack":true,"worker_sequence":1}',
                '{"type":"answer_delta","text":"working","worker_sequence":2}',
                '{"type":"tool_request","operation_id":"op","worker_sequence":3}',
                '{"type":"worker_done","status":"cancelled","worker_sequence":4}',
            ]
        )
        control = FakeSocket([])
        sockets = iter([socket, control])
        monkeypatch.setattr(
            runner,
            "_select_worker_claim",
            lambda: _async_value(runner.external_worker_claim),
        )
        monkeypatch.setattr(
            runner, "_external_worker_socket", lambda _: SocketContext(next(sockets))
        )
        monkeypatch.setattr(
            runner,
            "_tool_result",
            lambda _: _async_value(
                {
                    "type": "tool_result",
                    "operation_id": "op",
                    "ok": False,
                    "error": "turn_cancelled",
                }
            ),
        )
        events = runner._events(SimpleNamespace(reject=lambda: None))
        event = await anext(events)
        assert hasattr(event, "after_persist") is durable
        if durable and persist_before_terminal:
            await event.after_persist()
        with pytest.raises(StopAsyncIteration):
            await anext(events)
        sent = [json.loads(frame)["type"] for frame in socket.sent]
        if durable and not persist_before_terminal:
            assert "ack_terminal" not in sent
            await event.after_persist()
            assert json.loads(control.sent[0])["type"] == "ack_terminal"
            assert json.loads(control.sent[0])["sequence"] == 4
        else:
            assert sent[-1] == "ack_terminal"
            assert json.loads(socket.sent[-1])["sequence"] == 4
        if not durable:
            assert "ack_events" not in sent

    asyncio.run(scenario())
