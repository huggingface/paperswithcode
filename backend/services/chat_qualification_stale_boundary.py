"""Closed high-level stale-fence boundary for qualified external turns."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import TypeVar

from backend.services.chat_external_worker_capacity import (
    ExternalWorkerCapacityUnavailable,
)
from backend.services.chat_external_worker_registry import (
    StaleWorkerClaim,
    WorkerLeaseUnavailable,
)
from backend.services.chat_sandbox_state_repository import (
    LeaseUnavailable,
    WorkerGenerationUnavailable,
)
from backend.services.chat_turn_job_repository import StaleTurnClaim

T = TypeVar("T")
QualificationEvidenceRecorder = Callable[..., bool]

QUALIFIED_OWNERSHIP_REJECTIONS = (
    StaleTurnClaim,
    StaleWorkerClaim,
    WorkerLeaseUnavailable,
    ExternalWorkerCapacityUnavailable,
    LeaseUnavailable,
    WorkerGenerationUnavailable,
)
_RECORDED_STALE_TURNS: ContextVar[frozenset[tuple[uuid.UUID, uuid.UUID]]] = ContextVar(
    "qualification_recorded_stale_turns", default=frozenset()
)


class QualificationStaleFenceBoundary:
    """Record at most one stale fence while preserving the rejection outcome."""

    def __init__(
        self,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        recorder: QualificationEvidenceRecorder,
    ) -> None:
        self.turn_id = turn_id
        self.chat_session_id = chat_session_id
        self.recorder = recorder
        self._recorded = False

    def reject(self) -> None:
        key = (self.turn_id, self.chat_session_id)
        recorded_turns = _RECORDED_STALE_TURNS.get()
        if self._recorded or key in recorded_turns:
            return
        self._recorded = True
        _RECORDED_STALE_TURNS.set(recorded_turns | {key})
        self.recorder(
            turn_id=self.turn_id,
            chat_session_id=self.chat_session_id,
            event_type="stale_fence",
        )

    async def call(self, operation: Awaitable[T]) -> T:
        try:
            return await operation
        except QUALIFIED_OWNERSHIP_REJECTIONS:
            self.reject()
            raise
