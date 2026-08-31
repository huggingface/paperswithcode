"""Trusted lifecycle coordinator for one external Pi worker replica."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.services.chat_external_pi_shadow import (
    ExternalPiWorkerControlClient,
    ExternalPiWorkerStatus,
)
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRepository,
    ExternalWorkerClaim,
)


class ExternalPiWorkerMismatch(RuntimeError):
    """The reachable worker does not match the protected deployment contract."""


class ExternalPiWorkerDrainIncomplete(RuntimeError):
    """The worker is draining but still owns active sessions."""


@dataclass(slots=True)
class ChatExternalPiSupervisor:
    client: ExternalPiWorkerControlClient
    repository: ChatExternalWorkerRepository
    expected_release_id: str
    expected_contract_version: str
    expected_maximum_sessions: int
    lease_seconds: int = 15
    drain_seconds: int = 60

    def _validate(
        self,
        status: ExternalPiWorkerStatus,
        *,
        claim: ExternalWorkerClaim | None = None,
        expected_state: str | None = None,
    ) -> None:
        if (
            status.protocol != self.expected_contract_version
            or status.release_id != self.expected_release_id
            or status.maximum_sessions != self.expected_maximum_sessions
            or (claim is not None and status.worker_id != claim.worker_id)
            or (claim is not None and status.instance_id != claim.instance_id)
            or (claim is not None and status.worker_generation != claim.generation)
            or (expected_state is not None and status.state != expected_state)
        ):
            raise ExternalPiWorkerMismatch(
                "External Pi worker identity or compatibility mismatch"
            )

    async def register(self, db: Session, *, now: datetime) -> ExternalWorkerClaim:
        status = await self.client.status()
        self._validate(status, expected_state="ready")
        claim = self.repository.register(
            db,
            worker_id=status.worker_id,
            instance_id=status.instance_id,
            release_id=status.release_id,
            contract_version=status.protocol,
            maximum_sessions=status.maximum_sessions,
            now=now,
            lease_seconds=self.lease_seconds,
        )
        claimed = await self.client.bind_claim(claim.generation)
        self._validate(claimed, claim=claim, expected_state="ready")
        return claim

    async def heartbeat(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
    ) -> ExternalPiWorkerStatus:
        status = await self.client.status()
        self._validate(status, claim=claim)
        self.repository.heartbeat(
            db,
            claim=claim,
            active_sessions=status.active_sessions,
            now=now,
            lease_seconds=self.lease_seconds,
        )
        return status

    async def begin_drain(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
    ) -> ExternalPiWorkerStatus:
        self.repository.require_ready_claim(db, claim=claim, now=now)
        status = await self.client.begin_drain(claim.generation)
        self._validate(status, claim=claim, expected_state="draining")
        self.repository.begin_drain(
            db,
            claim=claim,
            now=now,
            drain_seconds=self.drain_seconds,
        )
        return status

    async def finish_drain(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
    ) -> None:
        status = await self.client.status()
        self._validate(status, claim=claim, expected_state="draining")
        if status.active_sessions != 0:
            raise ExternalPiWorkerDrainIncomplete(
                "External Pi worker drain is incomplete"
            )
        self.repository.heartbeat(
            db,
            claim=claim,
            active_sessions=0,
            now=now,
            lease_seconds=self.lease_seconds,
        )
        self.repository.mark_offline(db, claim=claim, now=now)
