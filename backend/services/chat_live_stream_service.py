"""In-process fan-out and replay for active research chat streams."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from backend.services.chat_detached_turn_service import (
    DetachedTurn,
    DetachedTurnCoordinator,
    DetachedTurnHandle,
)
from backend.services.chat_stream_service import ChatStreamFrame
from backend.services.chat_turn_event_repository import JournalFrame
from backend.services.chat_durable_qualification_evidence import (
    record_qualification_event_safely,
)
from backend.services.chat_qualification_stale_boundary import (
    QualificationStaleFenceBoundary,
)


class LiveChatStream:
    """Keep one turn running independently of any individual HTTP response."""

    def __init__(
        self,
        *,
        session_id: uuid.UUID,
        turn_id: uuid.UUID,
        owner_id: str,
        source: AsyncIterator[ChatStreamFrame],
    ) -> None:
        self.session_id = session_id
        self.turn_id = turn_id
        self.owner_id = owner_id
        self._source = source
        self._frames: list[ChatStreamFrame] = []
        self._condition = asyncio.Condition()
        self._finished = False
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            async for frame in self._source:
                async with self._condition:
                    self._frames.append(frame)
                    self._condition.notify_all()
        finally:
            async with self._condition:
                self._finished = True
                self._condition.notify_all()

    async def subscribe(self) -> AsyncIterator[ChatStreamFrame]:
        """Replay the turn from its first frame, then follow new frames live."""

        index = 0
        while True:
            async with self._condition:
                await self._condition.wait_for(
                    lambda: index < len(self._frames) or self._finished
                )
                if index >= len(self._frames):
                    return
                frame = self._frames[index]
                index += 1
            yield frame


class DurableLiveChatStream:
    """Compatibility view over a detached, journal-backed turn."""

    def __init__(
        self,
        *,
        session_id: uuid.UUID,
        owner_id: str,
        handle: DetachedTurnHandle,
        coordinator: DetachedTurnCoordinator,
    ) -> None:
        self.session_id = session_id
        self.turn_id = handle.turn.turn_id
        self.owner_id = owner_id
        self._coordinator = coordinator
        self._handle = handle

    @property
    def task(self) -> asyncio.Task[None]:
        return self._handle.source_task

    @property
    def source_task(self) -> asyncio.Task[None]:
        return self._handle.source_task

    def subscribe(self, after_sequence: int = 0) -> AsyncIterator[JournalFrame]:
        return self._coordinator.subscribe(
            turn_id=self.turn_id, after_sequence=after_sequence
        )


class LiveChatStreamRegistry:
    """Own active turn tasks and make them reconnectable by session."""

    def __init__(
        self, *, detached_coordinator: DetachedTurnCoordinator | None = None
    ) -> None:
        self._streams: dict[uuid.UUID, LiveChatStream | DurableLiveChatStream] = {}
        self._detached_coordinator = detached_coordinator

    def start(
        self,
        *,
        session_id: uuid.UUID,
        turn_id: uuid.UUID,
        owner_id: str,
        source: AsyncIterator[ChatStreamFrame],
    ) -> LiveChatStream:
        existing = self._streams.get(session_id)
        if existing is not None and not existing.task.done():
            raise RuntimeError("Chat session already has a live stream")
        stream = LiveChatStream(
            session_id=session_id,
            turn_id=turn_id,
            owner_id=owner_id,
            source=source,
        )
        self._streams[session_id] = stream
        stream.task.add_done_callback(
            lambda _task: asyncio.create_task(self._expire(session_id, stream))
        )
        return stream

    async def start_detached(
        self,
        *,
        session_id: uuid.UUID,
        owner_id: str,
        turn: DetachedTurn,
        source: AsyncIterator[ChatStreamFrame],
    ) -> DurableLiveChatStream:
        """Delegate a durable-dispatch stream to the detached coordinator."""
        if self._detached_coordinator is None:
            await self._close_source(source)
            raise RuntimeError("Detached turn coordinator is not configured")
        existing = self._streams.get(session_id)
        if existing is not None and not existing.task.done():
            await self._close_source(source)
            raise RuntimeError("Chat session already has a live stream")
        stale_boundary = QualificationStaleFenceBoundary(
            turn_id=turn.turn_id,
            chat_session_id=session_id,
            recorder=record_qualification_event_safely,
        )
        handle = await stale_boundary.call(
            self._detached_coordinator.start(
                turn=turn,
                source=source,
                stale_boundary=stale_boundary,
            )
        )
        stream = DurableLiveChatStream(
            session_id=session_id,
            owner_id=owner_id,
            handle=handle,
            coordinator=self._detached_coordinator,
        )
        self._streams[session_id] = stream
        stream.task.add_done_callback(
            lambda task: self._finish_detached_task(session_id, stream, task)
        )
        return stream

    def _finish_detached_task(
        self,
        session_id: uuid.UUID,
        stream: DurableLiveChatStream,
        task: asyncio.Task[None],
    ) -> None:
        if not task.cancelled():
            task.exception()
        asyncio.create_task(self._expire(session_id, stream))

    @staticmethod
    async def _close_source(source: AsyncIterator[ChatStreamFrame]) -> None:
        close = getattr(source, "aclose", None)
        if close is not None:
            await close()

    def get(
        self, session_id: uuid.UUID, turn_id: uuid.UUID, owner_id: str
    ) -> LiveChatStream | DurableLiveChatStream | None:
        stream = self._streams.get(session_id)
        if stream is None or stream.turn_id != turn_id or stream.owner_id != owner_id:
            return None
        return stream

    async def _expire(
        self,
        session_id: uuid.UUID,
        stream: LiveChatStream | DurableLiveChatStream,
    ) -> None:
        # A short grace period covers the race between the terminal SSE frame
        # and the browser's canonical session reload.
        await asyncio.sleep(30)
        if self._streams.get(session_id) is stream:
            self._streams.pop(session_id, None)


_registry = LiveChatStreamRegistry()


def live_chat_stream_registry() -> LiveChatStreamRegistry:
    return _registry
