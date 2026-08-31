"""Fenced durable ownership for the current in-process chat runner."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatTurnJob
from backend.services.chat_turn_job_repository import (
    ChatTurnJobRepository,
    TurnLeaseClaim,
)


@dataclass(frozen=True, slots=True)
class LocalTurnLeaseOwner:
    worker_id: str
    worker_generation: int

    @classmethod
    def create(cls) -> LocalTurnLeaseOwner:
        return cls(
            worker_id=f"local-runner:{uuid.uuid4().hex}",
            worker_generation=secrets.randbelow(2**63 - 1) + 1,
        )


LOCAL_TURN_LEASE_OWNER = LocalTurnLeaseOwner.create()


class ChatLocalTurnLeaseService:
    """Apply the protected local-runner fence through repository public seams."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        repository: ChatTurnJobRepository | None = None,
        owner: LocalTurnLeaseOwner = LOCAL_TURN_LEASE_OWNER,
    ) -> None:
        self.db = db
        self.settings = settings
        self.repository = repository or ChatTurnJobRepository()
        self.owner = owner

    def _require_enabled(self) -> None:
        if not self.settings.chat_durable_turn_dispatch_enabled:
            raise RuntimeError("Durable turn dispatch is disabled")

    def claim(self, turn_id: uuid.UUID, *, now: datetime) -> TurnLeaseClaim:
        self._require_enabled()
        return self.repository.claim(
            self.db,
            turn_id=turn_id,
            worker_id=self.owner.worker_id,
            worker_generation=self.owner.worker_generation,
            now=now,
            lease_seconds=self.settings.chat_external_pi_lease_seconds,
        )

    def heartbeat(self, claim: TurnLeaseClaim, *, now: datetime) -> ChatTurnJob:
        self._require_enabled()
        return self.repository.heartbeat(
            self.db,
            claim=claim,
            now=now,
            lease_seconds=self.settings.chat_external_pi_lease_seconds,
        )

    def transition_running(
        self, claim: TurnLeaseClaim, *, now: datetime
    ) -> ChatTurnJob:
        self._require_enabled()
        return self.repository.transition(
            self.db,
            claim=claim,
            state="running",
            now=now,
        )

    def request_cancelling(
        self, turn_id: uuid.UUID, *, now: datetime
    ) -> TurnLeaseClaim | None:
        self._require_enabled()
        return self.repository.request_cancelling(
            self.db,
            turn_id=turn_id,
            worker_id=self.owner.worker_id,
            worker_generation=self.owner.worker_generation,
            now=now,
            lease_seconds=self.settings.chat_external_pi_lease_seconds,
        )

    def interrupt_expired(self, turn_id: uuid.UUID, *, now: datetime) -> ChatTurnJob:
        self._require_enabled()
        return self.repository.interrupt_exact_expired(
            self.db,
            turn_id=turn_id,
            now=now,
            admitted_worker_id=self.owner.worker_id,
            admitted_worker_generation=self.owner.worker_generation,
            lease_seconds=self.settings.chat_external_pi_lease_seconds,
        )

    def write_terminal(
        self,
        claim: TurnLeaseClaim,
        *,
        state: str,
        now: datetime,
        failure_code: str | None = None,
    ) -> ChatTurnJob:
        self._require_enabled()
        return self.repository.write_terminal(
            self.db,
            claim=claim,
            state=state,
            now=now,
            failure_code=failure_code,
        )
