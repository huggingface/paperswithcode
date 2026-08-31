"""Durable state and capability lifecycle for an external Pi turn."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any

from backend.services.chat_capability_service import ChatCapabilityService
from backend.services.chat_turn_job_repository import (
    ChatTurnJobRepository,
    TurnLeaseClaim,
)


class ExternalPiTurnLifecycle:
    """Own durable transition persistence and one-shot capability revocation."""

    def __init__(
        self,
        *,
        capability_id: uuid.UUID | None,
        turn_claim: Callable[[], TurnLeaseClaim],
        session_factory: Callable[[], AbstractContextManager[Any]],
        now: Callable[[], datetime],
    ) -> None:
        self.capability_id = capability_id
        self.turn_claim = turn_claim
        self.session_factory = session_factory
        self.now = now

    async def persist_turn_state(self, state: str) -> None:
        claim = self.turn_claim()

        def transition() -> None:
            with self.session_factory() as db:
                ChatTurnJobRepository().transition(
                    db, claim=claim, state=state, now=self.now()
                )
                db.commit()

        await asyncio.to_thread(transition)

    def revoke(self) -> None:
        if self.capability_id is None:
            return
        with self.session_factory() as db:
            ChatCapabilityService(db).revoke(self.capability_id)
            db.commit()
        self.capability_id = None
