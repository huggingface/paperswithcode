"""Process-local durable turn ownership behind the chat HTTP adapters."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

from backend.config import Settings, get_settings
from backend.database.connection import db_manager
from backend.services.chat_detached_turn_service import (
    DetachedTurn,
    DetachedTurnCoordinator,
)
from backend.services.chat_durable_lifecycle_observer import (
    durable_lifecycle_observer,
)
from backend.services.chat_external_worker_capacity import (
    ChatExternalWorkerCapacityRepository,
)
from backend.services.chat_live_stream_service import LiveChatStreamRegistry
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_stream_service import ChatStreamOrchestrator
from backend.services.chat_turn_cancel_control import CancelControlResult
from backend.services.chat_turn_event_repository import JournalFrame

logger = logging.getLogger(__name__)


async def replay_detached_frames(
    coordinator: DetachedTurnCoordinator,
    admission: TurnAdmission,
    *,
    request_id: str,
    after_sequence: int,
) -> AsyncIterator[JournalFrame]:
    """Replay the durable journal, then reconstruct a missing terminal projection."""
    terminal_observed = False
    last_yielded_sequence = 0
    async for frame in coordinator.subscribe(
        turn_id=admission.turn_id, after_sequence=after_sequence
    ):
        last_yielded_sequence = max(last_yielded_sequence, frame.sequence)
        terminal_observed = terminal_observed or frame.event in {"done", "error"}
        yield frame
    if (
        admission.replay_assistant is None
        or terminal_observed
        or after_sequence >= admission.durable_event_sequence
    ):
        return

    sequence = max(admission.durable_event_sequence, last_yielded_sequence)
    replay = admission.replay_assistant
    fallback = (
        JournalFrame(
            sequence + 1,
            "stream_start",
            {
                "request_id": request_id,
                "session_id": str(admission.session_id),
                "provider_execution": False,
            },
        ),
        JournalFrame(sequence + 2, "answer_delta", {"text": replay.content}),
        JournalFrame(
            sequence + 3,
            "done",
            {
                "followups": replay.followups,
                "finish_reason": replay.finish_reason,
            },
        ),
    )
    for frame in fallback:
        if frame.sequence > after_sequence:
            yield frame


class ChatDetachedRuntime:
    """Own detached coordinators, orchestrators, replay, and terminal cleanup."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._orchestrators: dict[uuid.UUID, ChatStreamOrchestrator] = {}
        self.coordinator = DetachedTurnCoordinator(
            transaction=self._transaction,
            persist_terminal=self._persist_terminal,
            observe=durable_lifecycle_observer(settings),
        )
        self.registry = LiveChatStreamRegistry(detached_coordinator=self.coordinator)

    @staticmethod
    async def _transaction(operation):
        def run():
            with db_manager.session_local() as db:
                with db.begin():
                    result = operation(db)
                return result

        return await asyncio.to_thread(run)

    async def _persist_terminal(self, claim, state, failure_code) -> None:
        orchestrator = self._orchestrators.get(claim.turn_id)
        if orchestrator is None:
            await self._release_external_reservation_after_failure(
                claim.turn_id, stage="missing_terminal_owner"
            )
            raise RuntimeError("Detached terminal owner is unavailable")
        primary_failure: BaseException | None = None
        try:
            await orchestrator.persist_detached_terminal(claim, state, failure_code)
        except BaseException as error:
            primary_failure = error
            raise
        finally:
            if primary_failure is None:
                if self._orchestrators.get(claim.turn_id) is orchestrator:
                    self._orchestrators.pop(claim.turn_id, None)
                await self._release_external_reservation(claim.turn_id)
            else:
                # Keep the orchestrator so a later persistence_error fallback
                # can still write a durable terminal for this turn.
                await self._release_external_reservation_after_failure(
                    claim.turn_id, stage="terminal_persistence"
                )

    async def _release_external_reservation(self, turn_id: uuid.UUID) -> None:
        await self._transaction(
            lambda db: ChatExternalWorkerCapacityRepository.release_turn(
                db, turn_id=turn_id
            )
        )

    async def _release_external_reservation_after_failure(
        self, turn_id: uuid.UUID, *, stage: str
    ) -> None:
        try:
            await self._release_external_reservation(turn_id)
        except BaseException as cleanup_error:
            logger.warning(
                "detached reservation cleanup failed stage=%s error=%s",
                stage,
                type(cleanup_error).__name__,
            )

    async def cancel(self, request) -> CancelControlResult:
        orchestrator = self._orchestrators.get(request.turn_id)
        if orchestrator is None:
            return CancelControlResult.MISSING
        return await orchestrator.cancel_detached_turn(request.claim)

    async def start(
        self,
        *,
        admission: TurnAdmission,
        owner_id: str,
        claim,
        orchestrator: ChatStreamOrchestrator,
    ):
        self._orchestrators[admission.turn_id] = orchestrator
        try:
            return await self.registry.start_detached(
                session_id=admission.session_id,
                owner_id=owner_id,
                turn=DetachedTurn(admission.turn_id, claim),
                source=orchestrator.events(),
            )
        except BaseException:
            self._orchestrators.pop(admission.turn_id, None)
            try:
                await orchestrator.abandon_detached_start()
            except BaseException as cleanup_error:
                logger.warning(
                    "detached start abandonment failed error=%s",
                    type(cleanup_error).__name__,
                )
            await self._release_external_reservation_after_failure(
                admission.turn_id, stage="detached_start"
            )
            raise

    async def subscribe(
        self, *, turn_id: uuid.UUID, after_sequence: int
    ) -> AsyncIterator[JournalFrame]:
        async for frame in self.coordinator.subscribe(
            turn_id=turn_id, after_sequence=after_sequence
        ):
            yield frame

    async def replay(
        self,
        admission: TurnAdmission,
        *,
        request_id: str,
        after_sequence: int,
    ) -> AsyncIterator[JournalFrame]:
        async for frame in replay_detached_frames(
            self.coordinator,
            admission,
            request_id=request_id,
            after_sequence=after_sequence,
        ):
            yield frame


_runtime: ChatDetachedRuntime | None = None


def detached_chat_runtime(settings: Settings | None = None) -> ChatDetachedRuntime:
    global _runtime
    if _runtime is None:
        _runtime = ChatDetachedRuntime(settings or get_settings())
    return _runtime
