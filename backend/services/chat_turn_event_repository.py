"""Bounded durable replay journal for public research-chat turn events."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from backend.models.database import ChatTurnEventChunk, ChatTurnJob
from backend.services.chat_turn_job_repository import (
    TERMINAL_STATES,
    ChatTurnJobRepository,
    TurnLeaseClaim,
)


@dataclass(frozen=True)
class UnsequencedJournalEvent:
    event: str
    payload: dict[str, object]


@dataclass(frozen=True)
class JournalFrame:
    sequence: int
    event: str
    payload: dict[str, object]


class JournalLimitExceeded(RuntimeError):
    def __init__(self, *, code: str):
        self.code = code
        super().__init__(code)


class TurnEventJournal:
    MAX_FRAME_BYTES = 256 * 1024
    MAX_TURN_BYTES = 8 * 1024 * 1024
    MAX_TURN_EVENTS = 4_096

    def __init__(self, *, jobs: ChatTurnJobRepository | None = None):
        self._jobs = jobs or ChatTurnJobRepository()

    @staticmethod
    def _frame_dict(frame: JournalFrame) -> dict[str, object]:
        return {
            "sequence": frame.sequence,
            "event": frame.event,
            "payload": frame.payload,
        }

    @classmethod
    def _frame_bytes(cls, frame: JournalFrame) -> bytes:
        return json.dumps(
            cls._frame_dict(frame),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def append(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        events: Sequence[UnsequencedJournalEvent],
        now: datetime,
    ) -> Sequence[JournalFrame]:
        job = self._jobs.require_live_claim(db, claim=claim, now=now)
        if not events:
            return ()

        frames = tuple(
            JournalFrame(
                sequence=job.event_sequence + offset,
                event=unsequenced.event,
                payload=unsequenced.payload,
            )
            for offset, unsequenced in enumerate(events, start=1)
        )
        encoded = tuple(self._frame_bytes(frame) for frame in frames)
        payload_bytes = sum(map(len, encoded))
        if (
            any(len(frame_bytes) > self.MAX_FRAME_BYTES for frame_bytes in encoded)
            or frames[-1].sequence > self.MAX_TURN_EVENTS
            or job.event_bytes + payload_bytes > self.MAX_TURN_BYTES
        ):
            raise JournalLimitExceeded(code="event_journal_exhausted")

        db.add(
            ChatTurnEventChunk(
                turn_id=claim.turn_id,
                first_sequence=frames[0].sequence,
                last_sequence=frames[-1].sequence,
                events=[self._frame_dict(frame) for frame in frames],
                payload_bytes=payload_bytes,
                created_at=now,
            )
        )
        job.event_sequence = frames[-1].sequence
        job.event_bytes += payload_bytes
        db.flush()
        return frames

    def read_after(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        after_sequence: int,
        limit: int,
    ) -> Sequence[JournalFrame]:
        if after_sequence < 0 or limit <= 0 or limit > self.MAX_TURN_EVENTS:
            raise ValueError("Journal replay cursor or limit is invalid")
        chunks = db.execute(
            select(ChatTurnEventChunk)
            .where(
                ChatTurnEventChunk.turn_id == turn_id,
                ChatTurnEventChunk.last_sequence > after_sequence,
            )
            .order_by(ChatTurnEventChunk.first_sequence)
            .limit(limit)
        ).scalars()
        frames: list[JournalFrame] = []
        for chunk in chunks:
            for stored in chunk.events:
                sequence = int(stored["sequence"])
                if sequence > after_sequence:
                    frames.append(
                        JournalFrame(
                            sequence=sequence,
                            event=str(stored["event"]),
                            payload=stored["payload"],
                        )
                    )
                    if len(frames) == limit:
                        return tuple(frames)
        return tuple(frames)

    def cleanup_due_terminal(
        self,
        db: Session,
        *,
        now: datetime,
        replay_grace_seconds: int,
        limit: int,
    ) -> int:
        """Delete a bounded durable batch only after the replay grace expires."""
        if (
            now.tzinfo is None
            or replay_grace_seconds < 30
            or replay_grace_seconds > 3600
            or limit <= 0
            or limit > 100
        ):
            raise ValueError("Terminal journal cleanup bound is invalid")
        cutoff = now - timedelta(seconds=replay_grace_seconds)
        due_jobs = tuple(
            db.execute(
                select(ChatTurnJob)
                .where(
                    ChatTurnJob.state.in_(TERMINAL_STATES),
                    ChatTurnJob.terminal_at <= cutoff,
                    exists(
                        select(ChatTurnEventChunk.id).where(
                            ChatTurnEventChunk.turn_id == ChatTurnJob.turn_id
                        )
                    ),
                )
                .order_by(ChatTurnJob.terminal_at, ChatTurnJob.turn_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).scalars()
        )
        if not due_jobs:
            return 0
        result = db.execute(
            delete(ChatTurnEventChunk).where(
                ChatTurnEventChunk.turn_id.in_(job.turn_id for job in due_jobs)
            )
        )
        db.flush()
        return max(result.rowcount or 0, 0)
