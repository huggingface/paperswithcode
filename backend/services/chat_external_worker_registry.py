"""Fenced lifecycle for trusted external Pi worker replicas."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.database import ChatExternalWorker

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class WorkerLeaseUnavailable(RuntimeError):
    """A live worker instance already owns the logical worker identity."""


class StaleWorkerClaim(RuntimeError):
    """A replaced worker instance attempted to mutate durable state."""


@dataclass(frozen=True, slots=True)
class ExternalWorkerClaim:
    worker_id: str
    instance_id: uuid.UUID
    generation: int
    release_id: str
    contract_version: str


@dataclass(slots=True)
class ExternalWorkerRecord:
    worker_id: str
    instance_id: uuid.UUID
    environment: str
    release_id: str
    contract_version: str
    generation: int
    state: str
    maximum_sessions: int
    active_sessions: int
    heartbeat_at: datetime
    lease_expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ChatExternalWorkerRegistry:
    def __init__(self, *, environment: str):
        if environment not in {"staging", "production"}:
            raise ValueError("External worker environment is invalid")
        self.environment = environment

    def register(
        self,
        row: ExternalWorkerRecord | None,
        *,
        worker_id: str,
        instance_id: uuid.UUID,
        release_id: str,
        contract_version: str,
        maximum_sessions: int,
        now: datetime,
        lease_seconds: int,
    ) -> tuple[ExternalWorkerRecord, ExternalWorkerClaim]:
        if (
            _IDENTIFIER.fullmatch(worker_id) is None
            or not release_id
            or len(release_id) > 255
            or _IDENTIFIER.fullmatch(contract_version) is None
            or not 1 <= maximum_sessions <= 32
            or not 5 <= lease_seconds <= 60
            or now.tzinfo is None
        ):
            raise ValueError("External worker registration is invalid")
        if row is not None and (
            row.worker_id != worker_id or row.environment != self.environment
        ):
            raise ValueError("External worker durable identity mismatches")
        expires_at = now + timedelta(seconds=lease_seconds)
        if row is None:
            generation = 1
            row = ExternalWorkerRecord(
                worker_id=worker_id,
                instance_id=instance_id,
                environment=self.environment,
                release_id=release_id,
                contract_version=contract_version,
                generation=generation,
                state="ready",
                maximum_sessions=maximum_sessions,
                active_sessions=0,
                heartbeat_at=now,
                lease_expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            return row, ExternalWorkerClaim(
                worker_id,
                instance_id,
                generation,
                release_id,
                contract_version,
            )

        lease_is_live = row.lease_expires_at > now and row.state != "offline"
        if lease_is_live:
            if row.instance_id != instance_id or row.state != "ready":
                raise WorkerLeaseUnavailable("External worker lease is still active")
            if (
                row.release_id != release_id
                or row.contract_version != contract_version
                or row.maximum_sessions != maximum_sessions
            ):
                raise ValueError("Live worker registration changed immutable metadata")
            row.heartbeat_at = now
            row.lease_expires_at = expires_at
            row.updated_at = now
            return row, ExternalWorkerClaim(
                worker_id,
                instance_id,
                row.generation,
                release_id,
                contract_version,
            )

        row.instance_id = instance_id
        row.release_id = release_id
        row.contract_version = contract_version
        row.generation += 1
        row.state = "ready"
        row.maximum_sessions = maximum_sessions
        row.active_sessions = 0
        row.heartbeat_at = now
        row.lease_expires_at = expires_at
        row.updated_at = now
        return row, ExternalWorkerClaim(
            worker_id,
            instance_id,
            row.generation,
            release_id,
            contract_version,
        )

    @staticmethod
    def require_claim(row: ExternalWorkerRecord, claim: ExternalWorkerClaim) -> None:
        if (
            row.worker_id != claim.worker_id
            or row.instance_id != claim.instance_id
            or row.generation != claim.generation
            or row.release_id != claim.release_id
            or row.contract_version != claim.contract_version
        ):
            raise StaleWorkerClaim("External worker claim was fenced")

    def heartbeat(
        self,
        row: ExternalWorkerRecord,
        *,
        claim: ExternalWorkerClaim,
        active_sessions: int,
        now: datetime,
        lease_seconds: int,
    ) -> None:
        self.require_claim(row, claim)
        if (
            not 0 <= active_sessions <= row.maximum_sessions
            or not 5 <= lease_seconds <= 60
            or now.tzinfo is None
        ):
            raise ValueError("External worker heartbeat is invalid")
        if row.environment != self.environment or row.lease_expires_at <= now:
            raise WorkerLeaseUnavailable("External worker is not ready")
        if row.state == "draining" and active_sessions > row.active_sessions:
            raise WorkerLeaseUnavailable("Draining worker cannot accept sessions")
        if row.state not in {"ready", "draining"}:
            raise WorkerLeaseUnavailable("External worker is not ready")

        row.active_sessions = active_sessions
        row.heartbeat_at = now
        if row.state == "ready":
            row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        row.updated_at = now

    def begin_drain(
        self,
        row: ExternalWorkerRecord,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
        drain_seconds: int,
    ) -> None:
        self.require_claim(row, claim)
        if not 5 <= drain_seconds <= 300 or now.tzinfo is None:
            raise ValueError("External worker drain deadline is invalid")
        if (
            row.environment != self.environment
            or row.state != "ready"
            or row.lease_expires_at <= now
        ):
            raise WorkerLeaseUnavailable("External worker cannot begin draining")
        row.state = "draining"
        row.heartbeat_at = now
        row.lease_expires_at = now + timedelta(seconds=drain_seconds)
        row.updated_at = now

    def mark_offline(
        self,
        row: ExternalWorkerRecord,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
    ) -> None:
        self.require_claim(row, claim)
        if now.tzinfo is None:
            raise ValueError("External worker offline timestamp is invalid")
        if (
            row.environment != self.environment
            or row.state != "draining"
            or row.active_sessions != 0
            or row.lease_expires_at <= now
        ):
            raise WorkerLeaseUnavailable("External worker has not finished draining")
        row.state = "offline"
        row.heartbeat_at = now
        row.lease_expires_at = now
        row.updated_at = now


class ChatExternalWorkerRepository:
    """Serialize worker registration and persist its fencing generation."""

    def __init__(self, *, environment: str):
        self.registry = ChatExternalWorkerRegistry(environment=environment)
        self.environment = environment

    def load(
        self, db: Session, worker_id: str, *, lock: bool = True
    ) -> ChatExternalWorker | None:
        query = select(ChatExternalWorker).where(
            ChatExternalWorker.worker_id == worker_id,
            ChatExternalWorker.environment == self.environment,
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return db.execute(query).scalar_one_or_none()

    def _lock_identity(self, db: Session, worker_id: str) -> None:
        db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(
                        f"chat-external-worker:{self.environment}:{worker_id}", 0
                    )
                )
            )
        )

    def register(
        self,
        db: Session,
        *,
        worker_id: str,
        instance_id: uuid.UUID,
        release_id: str,
        contract_version: str,
        maximum_sessions: int,
        now: datetime,
        lease_seconds: int,
    ) -> ExternalWorkerClaim:
        self._lock_identity(db, worker_id)
        persisted = self.load(db, worker_id)
        row, claim = self.registry.register(
            persisted,
            worker_id=worker_id,
            instance_id=instance_id,
            release_id=release_id,
            contract_version=contract_version,
            maximum_sessions=maximum_sessions,
            now=now,
            lease_seconds=lease_seconds,
        )
        if persisted is None:
            db.add(
                ChatExternalWorker(
                    worker_id=row.worker_id,
                    instance_id=row.instance_id,
                    environment=row.environment,
                    release_id=row.release_id,
                    contract_version=row.contract_version,
                    generation=row.generation,
                    state=row.state,
                    maximum_sessions=row.maximum_sessions,
                    active_sessions=row.active_sessions,
                    heartbeat_at=row.heartbeat_at,
                    lease_expires_at=row.lease_expires_at,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        db.flush()
        return claim

    def _load_claimed(
        self, db: Session, claim: ExternalWorkerClaim
    ) -> ChatExternalWorker:
        row = self.load(db, claim.worker_id)
        if row is None:
            raise StaleWorkerClaim("External worker claim was fenced")
        return row

    @staticmethod
    def _require_ready(
        row: ExternalWorkerRecord,
        claim: ExternalWorkerClaim,
        *,
        environment: str,
        now: datetime,
    ) -> None:
        ChatExternalWorkerRegistry.require_claim(row, claim)
        if (
            now.tzinfo is None
            or row.environment != environment
            or row.state != "ready"
            or row.lease_expires_at <= now
            or row.active_sessions >= row.maximum_sessions
        ):
            raise WorkerLeaseUnavailable("External worker is not ready")

    def select_ready_claim(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
    ) -> ExternalWorkerClaim:
        if now.tzinfo is None:
            raise ValueError("External worker selection timestamp is invalid")
        row = self.load(db, claim.worker_id, lock=False)
        if row is None:
            raise StaleWorkerClaim("External worker claim was fenced")
        self._require_ready(row, claim, environment=self.environment, now=now)
        return claim

    def require_ready_claim(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
    ) -> None:
        row = self._load_claimed(db, claim)
        self._require_ready(row, claim, environment=self.environment, now=now)

    def require_endpoint_ready(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        active_sessions: int,
        maximum_sessions: int,
        configured_maximum_sessions: int,
        now: datetime,
    ) -> None:
        """Prove the authenticated endpoint and durable registry are identical."""
        row = self.load(db, claim.worker_id, lock=False)
        if row is None:
            raise WorkerLeaseUnavailable("External worker is not ready")
        self._require_ready(row, claim, environment=self.environment, now=now)
        if (
            claim.release_id != row.release_id
            or claim.contract_version != row.contract_version
            or maximum_sessions != configured_maximum_sessions
            or row.maximum_sessions != configured_maximum_sessions
            or active_sessions != row.active_sessions
        ):
            raise WorkerLeaseUnavailable("External worker is not ready")

    def require_live_claim(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
    ) -> None:
        """Fence reattachment to an existing run without applying new-run capacity."""
        row = self._load_claimed(db, claim)
        ChatExternalWorkerRegistry.require_claim(row, claim)
        if (
            now.tzinfo is None
            or row.environment != self.environment
            or row.state not in {"ready", "draining"}
            or row.lease_expires_at <= now
        ):
            raise WorkerLeaseUnavailable("External worker is not live")

    def heartbeat(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        active_sessions: int,
        now: datetime,
        lease_seconds: int,
    ) -> None:
        row = self._load_claimed(db, claim)
        self.registry.heartbeat(
            row,
            claim=claim,
            active_sessions=active_sessions,
            now=now,
            lease_seconds=lease_seconds,
        )
        db.flush()

    def begin_drain(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
        drain_seconds: int,
    ) -> None:
        row = self._load_claimed(db, claim)
        self.registry.begin_drain(
            row,
            claim=claim,
            now=now,
            drain_seconds=drain_seconds,
        )
        db.flush()

    def mark_offline(
        self,
        db: Session,
        *,
        claim: ExternalWorkerClaim,
        now: datetime,
    ) -> None:
        row = self._load_claimed(db, claim)
        self.registry.mark_offline(row, claim=claim, now=now)
        db.flush()
