from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from backend.services.chat_detached_turn_service import DetachedTurn
from backend.services.chat_live_stream_service import (
    DurableLiveChatStream,
    LiveChatStreamRegistry,
)
from backend.services.chat_stream_service import ChatStreamFrame
from backend.services.chat_turn_event_repository import JournalFrame
from backend.services.chat_turn_job_repository import TurnLeaseClaim


def test_stream_survives_subscriber_disconnect_and_replays_to_reconnect() -> None:
    async def scenario() -> list[str | None]:
        release_second = asyncio.Event()

        async def source():
            yield ChatStreamFrame("stream_start", {"request_id": "r1"})
            await release_second.wait()
            yield ChatStreamFrame("answer_delta", {"text": "Recovered"})
            yield ChatStreamFrame("done", {"finish_reason": "success"})

        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        registry = LiveChatStreamRegistry()
        stream = registry.start(
            session_id=session_id,
            turn_id=turn_id,
            owner_id="owner-1",
            source=source(),
        )

        first_subscription = stream.subscribe()
        first = await anext(first_subscription)
        await first_subscription.aclose()
        assert first.event == "stream_start"
        assert not stream.task.done()

        release_second.set()
        recovered = [frame.event async for frame in stream.subscribe()]
        await stream.task
        return recovered

    assert asyncio.run(scenario()) == ["stream_start", "answer_delta", "done"]


def test_registry_requires_matching_owner_and_turn() -> None:
    async def scenario() -> None:
        async def source():
            if False:
                yield ChatStreamFrame.heartbeat()

        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        registry = LiveChatStreamRegistry()
        stream = registry.start(
            session_id=session_id,
            turn_id=turn_id,
            owner_id="owner-1",
            source=source(),
        )
        assert registry.get(session_id, turn_id, "owner-1") is stream
        assert registry.get(session_id, uuid.uuid4(), "owner-1") is None
        assert registry.get(session_id, turn_id, "owner-2") is None
        await stream.task

    asyncio.run(scenario())


def test_registry_delegates_durable_streams_to_detached_coordinator() -> None:
    async def scenario() -> None:
        turn_id = uuid.uuid4()
        session_id = uuid.uuid4()
        turn = DetachedTurn(
            turn_id=turn_id,
            claim=TurnLeaseClaim(turn_id, "worker-a", 1, 1),
        )
        source_task = asyncio.create_task(asyncio.sleep(0))
        calls = []

        class Coordinator:
            async def start(self, *, turn, source, stale_boundary):
                calls.append((turn, source))
                return SimpleNamespace(turn=turn, source_task=source_task)

            async def subscribe(self, *, turn_id, after_sequence):
                calls.append((turn_id, after_sequence))
                yield JournalFrame(2, "answer_delta", {"text": "replayed"})

        async def source():
            if False:
                yield ChatStreamFrame.heartbeat()

        iterator = source()
        registry = LiveChatStreamRegistry(detached_coordinator=Coordinator())
        stream = await registry.start_detached(
            session_id=session_id,
            owner_id="owner-1",
            turn=turn,
            source=iterator,
        )

        assert isinstance(stream, DurableLiveChatStream)
        assert registry.get(session_id, turn_id, "owner-1") is stream
        assert [frame.sequence async for frame in stream.subscribe(1)] == [2]
        assert calls == [(turn, iterator), (turn_id, 1)]
        await source_task

    asyncio.run(scenario())
