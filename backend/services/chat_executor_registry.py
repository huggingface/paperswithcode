"""Transactional metadata registry for persistent remote executor routes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from backend.models.database import (
    ChatExecutorCell,
    ChatExecutorClaim,
    ChatExecutorKeyRevocation,
    ChatExecutorManifest,
    ChatExecutorNonce,
    ChatExecutorRegistration,
    ChatExecutorRollbackAudit,
    ChatExecutorShard,
)

NONCE_TTLS = {"launch": 60, "reconnect": 45, "liveness": 2, "recovery": 10}
MAX_NONCE_RETENTION_SECONDS = 24 * 60 * 60
SHARD_DRAIN_SECONDS = 240
CANARY_DELAY_SECONDS = 30
CHECKPOINT_SECONDS = 30


class ExecutorAuthorizationRejected(RuntimeError):
    """Single-use or generation-bound authorization evidence was rejected."""


class ExecutorClaimUnavailable(RuntimeError):
    """The exact registered environment cannot accept or retain this claim."""


class ExecutorCircuitConflict(RuntimeError):
    """A circuit revision or global canary lease is stale."""


class ExecutorRollbackRejected(RuntimeError):
    """The requested manifest is not an eligible ancestor of the active image."""


class ExecutorStorageUnavailable(RuntimeError):
    """Required rollback evidence could not be persisted."""


@dataclass(frozen=True, slots=True)
class WorkspaceClaim:
    turn_id: uuid.UUID
    registration_id: uuid.UUID
    claim_generation: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CanaryLease:
    lease_id: uuid.UUID
    expires_at: datetime
    circuit_revision: int


class ChatExecutorRegistry:
    """Mutate executor metadata inside a transaction owned by the caller."""

    @staticmethod
    def _database_now(db: Session) -> datetime:
        value = db.scalar(select(func.current_timestamp()))
        if value is None:
            raise ExecutorStorageUnavailable("Executor registry clock is unavailable")
        return ChatExecutorRegistry._as_utc(value)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        """Normalize timestamps returned without tzinfo by SQLite test databases."""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    @staticmethod
    def _bounded(value: str, *, maximum: int, name: str) -> str:
        if not value or len(value) > maximum or "\x00" in value:
            raise ValueError(f"Executor {name} is invalid")
        return value

    @staticmethod
    def _digest(value: str, *, name: str) -> str:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(f"Executor {name} is invalid")
        return value

    def issue_nonce(
        self,
        db: Session,
        *,
        nonce_digest: str,
        purpose: str,
        environment_id: str,
        environment_generation: int,
        shard_id: uuid.UUID,
        shard_generation: int,
        key_epoch: int,
        ttl_seconds: int,
        retention_seconds: int,
    ) -> ChatExecutorNonce:
        self._digest(nonce_digest, name="nonce digest")
        if purpose not in NONCE_TTLS or ttl_seconds != NONCE_TTLS[purpose]:
            raise ValueError("Executor nonce lifetime is invalid")
        if not ttl_seconds <= retention_seconds <= MAX_NONCE_RETENTION_SECONDS:
            raise ValueError("Executor nonce retention is invalid")
        if min(environment_generation, shard_generation, key_epoch) <= 0:
            raise ValueError("Executor nonce generation is invalid")
        now = self._database_now(db)
        row = ChatExecutorNonce(
            nonce_digest=nonce_digest,
            purpose=purpose,
            environment_id=self._bounded(
                environment_id, maximum=64, name="environment ID"
            ),
            environment_generation=environment_generation,
            shard_id=shard_id,
            shard_generation=shard_generation,
            key_epoch=key_epoch,
            expires_at=now + timedelta(seconds=ttl_seconds),
            consumed_at=None,
            invalidated_at=None,
            retention_expires_at=now + timedelta(seconds=retention_seconds),
            created_at=now,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError as error:
            raise ExecutorAuthorizationRejected(
                "Executor authorization was rejected"
            ) from error
        return row

    @staticmethod
    def consume_nonce(
        db: Session,
        *,
        nonce_digest: str,
        purpose: str,
        environment_id: str,
        environment_generation: int,
        shard_id: uuid.UUID,
        shard_generation: int,
        key_epoch: int,
    ) -> None:
        statement = (
            update(ChatExecutorNonce)
            .where(
                ChatExecutorNonce.nonce_digest == nonce_digest,
                ChatExecutorNonce.purpose == purpose,
                ChatExecutorNonce.environment_id == environment_id,
                ChatExecutorNonce.environment_generation == environment_generation,
                ChatExecutorNonce.shard_id == shard_id,
                ChatExecutorNonce.shard_generation == shard_generation,
                ChatExecutorNonce.key_epoch == key_epoch,
                ChatExecutorNonce.consumed_at.is_(None),
                ChatExecutorNonce.invalidated_at.is_(None),
                ChatExecutorNonce.expires_at >= func.current_timestamp(),
            )
            .values(consumed_at=func.current_timestamp())
            .returning(ChatExecutorNonce.nonce_digest)
        )
        if db.scalar(statement) is None:
            raise ExecutorAuthorizationRejected("Executor authorization was rejected")

    def claim_workspace(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        registration_id: uuid.UUID,
        environment_generation: int,
        shard_generation: int,
        liveness_nonce_digest: str,
        claim_generation: int,
        ttl_seconds: int,
    ) -> WorkspaceClaim:
        if claim_generation <= 0 or not 1 <= ttl_seconds <= SHARD_DRAIN_SECONDS:
            raise ValueError("Executor claim bounds are invalid")
        existing = db.get(ChatExecutorClaim, turn_id)
        if existing is not None:
            if (
                existing.registration_id == registration_id
                and existing.claim_generation == claim_generation
                and existing.state == "active"
            ):
                claim = self._claim(existing)
                self.validate_attachment(db, claim=claim)
                return claim
            raise ExecutorClaimUnavailable("Executor turn claim is unavailable")
        registration = db.scalar(
            select(ChatExecutorRegistration)
            .where(ChatExecutorRegistration.id == registration_id)
            .with_for_update()
        )
        if registration is None:
            raise ExecutorClaimUnavailable("Executor registration is unavailable")
        cell = db.scalar(
            select(ChatExecutorCell)
            .where(ChatExecutorCell.cell_id == registration.cell_id)
            .with_for_update()
        )
        shard = db.get(ChatExecutorShard, registration.shard_id)
        now = self._database_now(db)
        if (
            cell is None
            or shard is None
            or cell.circuit_state != "closed"
            or cell.active_shard_id != registration.shard_id
            or shard.state != "ready"
            or registration.state not in {"ready", "assigned_idle"}
            or registration.environment_generation != environment_generation
            or registration.shard_generation != shard_generation
            or registration.shard_generation != shard.generation
            or registration.key_epoch != cell.key_epoch
            or self._as_utc(registration.expires_at)
            < now + timedelta(seconds=ttl_seconds)
        ):
            raise ExecutorClaimUnavailable("Executor registration fence is stale")
        self.consume_nonce(
            db,
            nonce_digest=liveness_nonce_digest,
            purpose="liveness",
            environment_id=registration.environment_id,
            environment_generation=environment_generation,
            shard_id=registration.shard_id,
            shard_generation=shard_generation,
            key_epoch=registration.key_epoch,
        )
        row = ChatExecutorClaim(
            turn_id=turn_id,
            registration_id=registration.id,
            claim_generation=claim_generation,
            cell_id=registration.cell_id,
            shard_id=registration.shard_id,
            shard_generation=registration.shard_generation,
            environment_generation=registration.environment_generation,
            state="active",
            authorized_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            settled_at=None,
            settlement_request_id=None,
            terminal_code=None,
        )
        registration.state = "claimed"
        registration.updated_at = now
        db.add(row)
        try:
            db.flush()
        except IntegrityError as error:
            raise ExecutorClaimUnavailable(
                "Executor registration is already claimed"
            ) from error
        return self._claim(row)

    @staticmethod
    def _claim(row: ChatExecutorClaim) -> WorkspaceClaim:
        return WorkspaceClaim(
            turn_id=row.turn_id,
            registration_id=row.registration_id,
            claim_generation=row.claim_generation,
            expires_at=row.expires_at,
        )

    def validate_attachment(self, db: Session, *, claim: WorkspaceClaim) -> None:
        row = db.scalar(
            select(ChatExecutorClaim)
            .where(ChatExecutorClaim.turn_id == claim.turn_id)
            .with_for_update()
        )
        registration = (
            db.get(ChatExecutorRegistration, claim.registration_id)
            if row is not None
            else None
        )
        shard = db.get(ChatExecutorShard, row.shard_id) if row is not None else None
        now = self._database_now(db)
        if (
            row is None
            or registration is None
            or shard is None
            or row.state != "active"
            or row.claim_generation != claim.claim_generation
            or self._as_utc(row.expires_at) < now
            or registration.state != "claimed"
            or registration.cell_id != row.cell_id
            or registration.shard_id != row.shard_id
            or registration.environment_generation != row.environment_generation
            or registration.shard_generation != row.shard_generation
            or shard.generation != row.shard_generation
            or shard.state not in {"ready", "draining"}
        ):
            if row is not None and row.state == "active":
                self._invalidate_claim(row, now=now, code="attachment_fence_lost")
            raise ExecutorClaimUnavailable("Executor attachment fence is stale")

    def mark_suspect(self, db: Session, *, registration_id: uuid.UUID) -> None:
        registration = db.scalar(
            select(ChatExecutorRegistration)
            .where(ChatExecutorRegistration.id == registration_id)
            .with_for_update()
        )
        if registration is None:
            return
        now = self._database_now(db)
        registration.state = "suspect"
        registration.updated_at = now
        claims = db.scalars(
            select(ChatExecutorClaim).where(
                ChatExecutorClaim.registration_id == registration_id,
                ChatExecutorClaim.state == "active",
            )
        ).all()
        for claim in claims:
            self._invalidate_claim(claim, now=now, code="registration_suspect")
        db.flush()

    @staticmethod
    def _invalidate_claim(row: ChatExecutorClaim, *, now: datetime, code: str) -> None:
        row.state = "invalidated"
        row.settled_at = now
        row.terminal_code = code

    def checkpoint_seen(self, db: Session, *, registration_id: uuid.UUID) -> bool:
        now = self._database_now(db)
        statement = (
            update(ChatExecutorRegistration)
            .where(
                ChatExecutorRegistration.id == registration_id,
                or_(
                    ChatExecutorRegistration.last_seen_at.is_(None),
                    ChatExecutorRegistration.last_seen_at
                    <= now - timedelta(seconds=CHECKPOINT_SECONDS),
                ),
            )
            .values(last_seen_at=now, updated_at=now)
            .returning(ChatExecutorRegistration.id)
        )
        return db.scalar(statement) is not None

    def activate_shard(self, db: Session, *, replacement_id: uuid.UUID) -> None:
        replacement = db.scalar(
            select(ChatExecutorShard)
            .where(ChatExecutorShard.id == replacement_id)
            .with_for_update()
        )
        if (
            replacement is None
            or replacement.state != "ready"
            or replacement.ready_capacity < 1
        ):
            raise ExecutorClaimUnavailable("Executor replacement shard is not ready")
        cell = db.scalar(
            select(ChatExecutorCell)
            .where(ChatExecutorCell.cell_id == replacement.cell_id)
            .with_for_update()
        )
        if cell is None:
            raise ExecutorClaimUnavailable("Executor cell is unavailable")
        now = self._database_now(db)
        if cell.active_shard_id is not None and cell.active_shard_id != replacement.id:
            previous = db.get(ChatExecutorShard, cell.active_shard_id)
            if previous is not None:
                if (
                    previous.shard_id != replacement.shard_id
                    or previous.generation >= replacement.generation
                ):
                    raise ExecutorClaimUnavailable(
                        "Executor replacement shard generation is stale"
                    )
                previous.state = "draining"
                previous.drain_started_at = now
                previous.drain_deadline_at = now + timedelta(
                    seconds=SHARD_DRAIN_SECONDS
                )
                previous.updated_at = now
        cell.active_shard_id = replacement.id
        cell.updated_at = now
        db.flush()

    def settle_claim(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        claim_generation: int,
        settlement_request_id: uuid.UUID,
        terminal_code: str,
    ) -> None:
        row = db.scalar(
            select(ChatExecutorClaim)
            .where(ChatExecutorClaim.turn_id == turn_id)
            .with_for_update()
        )
        if row is None or row.claim_generation != claim_generation:
            raise ExecutorClaimUnavailable("Executor claim fence is stale")
        if row.state != "active":
            if (
                row.state == "settled"
                and row.settlement_request_id == settlement_request_id
                and row.terminal_code == terminal_code
            ):
                return
            raise ExecutorClaimUnavailable("Executor claim is already terminal")
        now = self._database_now(db)
        row.state = "settled"
        row.settled_at = now
        row.settlement_request_id = settlement_request_id
        row.terminal_code = self._bounded(
            terminal_code, maximum=64, name="terminal code"
        )
        registration = db.get(ChatExecutorRegistration, row.registration_id)
        if registration is not None and registration.state == "claimed":
            registration.state = "ready"
            registration.updated_at = now
        db.flush()

    def expire_claims(self, db: Session, *, batch_size: int = 100) -> int:
        if not 1 <= batch_size <= 1000:
            raise ValueError("Executor expiry batch is invalid")
        now = self._database_now(db)
        rows = db.scalars(
            select(ChatExecutorClaim)
            .where(
                ChatExecutorClaim.state == "active", ChatExecutorClaim.expires_at < now
            )
            .order_by(ChatExecutorClaim.expires_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            self._invalidate_claim(row, now=now, code="claim_expired")
            registration = db.get(ChatExecutorRegistration, row.registration_id)
            if registration is not None:
                registration.state = "suspect"
                registration.updated_at = now
        db.flush()
        return len(rows)

    def cleanup_nonces(self, db: Session, *, batch_size: int) -> int:
        if not 1 <= batch_size <= 1000:
            raise ValueError("Executor nonce cleanup batch is invalid")
        digests = db.scalars(
            select(ChatExecutorNonce.nonce_digest)
            .where(ChatExecutorNonce.retention_expires_at < func.current_timestamp())
            .order_by(ChatExecutorNonce.retention_expires_at)
            .limit(batch_size)
        ).all()
        if digests:
            db.execute(
                delete(ChatExecutorNonce).where(
                    ChatExecutorNonce.nonce_digest.in_(digests)
                )
            )
        return len(digests)

    def revoke_key(
        self,
        db: Session,
        *,
        request_id: uuid.UUID,
        cell_id: str,
        key_id: str,
        actor: str,
        reason_class: str,
    ) -> ChatExecutorKeyRevocation:
        existing = db.scalar(
            select(ChatExecutorKeyRevocation).where(
                ChatExecutorKeyRevocation.request_id == request_id
            )
        )
        if existing is not None:
            return self._matching_revocation(
                existing,
                cell_id=cell_id,
                key_id=key_id,
                actor=actor,
                reason_class=reason_class,
            )
        cell = db.scalar(
            select(ChatExecutorCell)
            .where(ChatExecutorCell.cell_id == cell_id)
            .with_for_update()
        )
        if cell is None:
            raise ExecutorAuthorizationRejected("Executor cell is unavailable")
        # A concurrent request may have committed while this transaction waited
        # for the cell fence. Re-read after acquiring the lock before advancing
        # the epoch.
        existing = db.scalar(
            select(ChatExecutorKeyRevocation).where(
                ChatExecutorKeyRevocation.request_id == request_id
            )
        )
        if existing is not None:
            return self._matching_revocation(
                existing,
                cell_id=cell_id,
                key_id=key_id,
                actor=actor,
                reason_class=reason_class,
            )
        now = self._database_now(db)
        previous_epoch = cell.key_epoch
        revocation = ChatExecutorKeyRevocation(
            id=uuid.uuid4(),
            request_id=request_id,
            cell_id=cell_id,
            key_id=self._bounded(key_id, maximum=128, name="key ID"),
            previous_epoch=previous_epoch,
            new_epoch=previous_epoch + 1,
            actor=self._bounded(actor, maximum=128, name="revocation actor"),
            reason_class=self._bounded(
                reason_class, maximum=64, name="revocation reason"
            ),
            created_at=now,
        )
        db.add(revocation)
        affected_ids = db.scalars(
            select(ChatExecutorRegistration.id).where(
                ChatExecutorRegistration.cell_id == cell_id,
                or_(
                    ChatExecutorRegistration.authorization_key_id == key_id,
                    ChatExecutorRegistration.public_key_id == key_id,
                ),
            )
        ).all()
        if affected_ids:
            db.execute(
                update(ChatExecutorRegistration)
                .where(ChatExecutorRegistration.id.in_(affected_ids))
                .values(state="fenced", updated_at=now)
            )
            db.execute(
                update(ChatExecutorClaim)
                .where(
                    ChatExecutorClaim.registration_id.in_(affected_ids),
                    ChatExecutorClaim.state == "active",
                )
                .values(
                    state="invalidated",
                    settled_at=now,
                    terminal_code="security_revoked",
                )
            )
        cell_shard_ids = select(ChatExecutorShard.id).where(
            ChatExecutorShard.cell_id == cell_id
        )
        db.execute(
            update(ChatExecutorNonce)
            .where(
                ChatExecutorNonce.key_epoch == previous_epoch,
                ChatExecutorNonce.shard_id.in_(cell_shard_ids),
            )
            .values(invalidated_at=now)
        )
        cell.key_epoch = previous_epoch + 1
        cell.circuit_state = "security_hold"
        cell.circuit_revision += 1
        cell.canary_lease_id = None
        cell.canary_lease_expires_at = None
        cell.canary_successes = 0
        cell.updated_at = now
        db.flush()
        db.expire_all()
        return revocation

    @staticmethod
    def _matching_revocation(
        row: ChatExecutorKeyRevocation,
        *,
        cell_id: str,
        key_id: str,
        actor: str,
        reason_class: str,
    ) -> ChatExecutorKeyRevocation:
        if (row.cell_id, row.key_id, row.actor, row.reason_class) != (
            cell_id,
            key_id,
            actor,
            reason_class,
        ):
            raise ExecutorAuthorizationRejected("Executor revocation request conflicts")
        return row

    def compare_and_set_circuit(
        self,
        db: Session,
        *,
        cell_id: str,
        expected_revision: int,
        new_state: str,
    ) -> ChatExecutorCell:
        if new_state not in {"closed", "open", "half_open"}:
            raise ValueError("Executor circuit state is invalid")
        now = self._database_now(db)
        values: dict[str, object] = {
            "circuit_state": new_state,
            "circuit_revision": expected_revision + 1,
            "updated_at": now,
        }
        if new_state == "open":
            values.update(opened_at=now, canary_successes=0)
        if new_state == "closed":
            values.update(
                opened_at=None,
                canary_lease_id=None,
                canary_lease_expires_at=None,
                canary_successes=0,
                consecutive_attach_failures=0,
                failure_window_started_at=None,
            )
        statement = (
            update(ChatExecutorCell)
            .where(
                ChatExecutorCell.cell_id == cell_id,
                ChatExecutorCell.circuit_revision == expected_revision,
                ChatExecutorCell.circuit_state != "security_hold",
            )
            .values(**values)
            .returning(ChatExecutorCell.cell_id)
        )
        if db.scalar(statement) is None:
            raise ExecutorCircuitConflict("Executor circuit revision is stale")
        db.expire_all()
        row = db.get(ChatExecutorCell, cell_id)
        assert row is not None
        return row

    def acquire_canary(
        self, db: Session, *, cell_id: str, ttl_seconds: int
    ) -> CanaryLease:
        if not 1 <= ttl_seconds <= 60:
            raise ValueError("Executor canary lifetime is invalid")
        cell = db.scalar(
            select(ChatExecutorCell)
            .where(ChatExecutorCell.cell_id == cell_id)
            .with_for_update()
        )
        now = self._database_now(db)
        if (
            cell is None
            or cell.circuit_state != "open"
            or cell.opened_at is None
            or self._as_utc(cell.opened_at)
            > now - timedelta(seconds=CANARY_DELAY_SECONDS)
            or (
                cell.canary_lease_id is not None
                and cell.canary_lease_expires_at is not None
                and self._as_utc(cell.canary_lease_expires_at) >= now
            )
        ):
            raise ExecutorCircuitConflict("Executor canary lease is unavailable")
        lease_id = uuid.uuid4()
        expires_at = now + timedelta(seconds=ttl_seconds)
        cell.circuit_state = "half_open"
        cell.circuit_revision += 1
        cell.canary_lease_id = lease_id
        cell.canary_lease_expires_at = expires_at
        cell.canary_successes = 0
        cell.updated_at = now
        db.flush()
        return CanaryLease(lease_id, expires_at, cell.circuit_revision)

    def record_canary(
        self,
        db: Session,
        *,
        cell_id: str,
        lease_id: uuid.UUID,
        success: bool,
        final: bool,
    ) -> None:
        cell = db.scalar(
            select(ChatExecutorCell)
            .where(ChatExecutorCell.cell_id == cell_id)
            .with_for_update()
        )
        now = self._database_now(db)
        if (
            cell is None
            or cell.circuit_state != "half_open"
            or cell.canary_lease_id != lease_id
            or cell.canary_lease_expires_at is None
            or self._as_utc(cell.canary_lease_expires_at) < now
        ):
            raise ExecutorCircuitConflict("Executor canary fence is stale")
        if not success:
            cell.circuit_state = "open"
            cell.opened_at = now
            cell.canary_successes = 0
            cell.canary_lease_id = None
            cell.canary_lease_expires_at = None
        else:
            next_successes = cell.canary_successes + 1
            if (final and next_successes != 3) or (not final and next_successes >= 3):
                raise ExecutorCircuitConflict("Executor canary quorum is invalid")
            cell.canary_successes = next_successes
            if final:
                cell.circuit_state = "closed"
                cell.opened_at = None
                cell.canary_successes = 0
                cell.canary_lease_id = None
                cell.canary_lease_expires_at = None
        cell.circuit_revision += 1
        cell.updated_at = now
        db.flush()

    def rollback_manifest(
        self,
        db: Session,
        *,
        request_id: uuid.UUID,
        cell_id: str,
        target_digest: str,
        actor: str,
        reason_class: str,
        qualification_evidence_ref: str,
    ) -> ChatExecutorRollbackAudit:
        existing = db.get(ChatExecutorRollbackAudit, request_id)
        if existing is not None:
            return self._matching_rollback(
                db,
                existing,
                cell_id=cell_id,
                target_digest=target_digest,
                actor=actor,
                reason_class=reason_class,
                qualification_evidence_ref=qualification_evidence_ref,
            )
        cell = db.scalar(
            select(ChatExecutorCell)
            .where(ChatExecutorCell.cell_id == cell_id)
            .with_for_update()
        )
        if (
            cell is None
            or cell.selected_manifest_digest is None
            or cell.circuit_state == "security_hold"
        ):
            raise ExecutorRollbackRejected("Executor creation manifest is unavailable")
        # Reconcile a retry that waited behind the original request's cell lock.
        existing = db.get(ChatExecutorRollbackAudit, request_id)
        if existing is not None:
            return self._matching_rollback(
                db,
                existing,
                cell_id=cell_id,
                target_digest=target_digest,
                actor=actor,
                reason_class=reason_class,
                qualification_evidence_ref=qualification_evidence_ref,
            )
        source = db.get(ChatExecutorManifest, cell.selected_manifest_digest)
        target = db.get(
            ChatExecutorManifest, self._digest(target_digest, name="target digest")
        )
        now = self._database_now(db)
        if (
            source is None
            or target is None
            or target.qualification_status != "qualified"
            or target.compatibility_state == "incompatible"
            or target.revoked_at is not None
            or target.qualification_evidence_ref != qualification_evidence_ref
            or (
                target.compatibility_expires_at is not None
                and self._as_utc(target.compatibility_expires_at) < now
            )
            or not self._is_ancestor(db, source=source, target_digest=target.digest)
        ):
            raise ExecutorRollbackRejected("Executor rollback target is ineligible")
        epoch = cell.rollback_epoch + 1
        audit = ChatExecutorRollbackAudit(
            request_id=request_id,
            cell_id=cell_id,
            actor=self._bounded(actor, maximum=128, name="rollback actor"),
            reason_class=self._bounded(
                reason_class, maximum=64, name="rollback reason"
            ),
            source_digest=source.digest,
            target_digest=target.digest,
            qualification_evidence_ref=self._bounded(
                qualification_evidence_ref, maximum=255, name="qualification evidence"
            ),
            outcome="applied",
            epoch=epoch,
            created_at=now,
        )
        db.add(audit)
        try:
            db.flush()
        except DBAPIError as error:
            if audit in db:
                db.expunge(audit)
            raise ExecutorStorageUnavailable(
                "Executor rollback audit is unavailable"
            ) from error
        cell.selected_manifest_digest = target.digest
        cell.rollback_epoch = epoch
        cell.updated_at = now
        try:
            db.flush()
        except DBAPIError as error:
            raise ExecutorStorageUnavailable(
                "Executor manifest pointer is unavailable"
            ) from error
        return audit

    @staticmethod
    def _is_ancestor(
        db: Session, *, source: ChatExecutorManifest, target_digest: str
    ) -> bool:
        seen: set[str] = set()
        parent_digest = source.parent_digest
        while parent_digest is not None and parent_digest not in seen:
            if parent_digest == target_digest:
                return True
            seen.add(parent_digest)
            parent = db.get(ChatExecutorManifest, parent_digest)
            if parent is None:
                return False
            parent_digest = parent.parent_digest
        return False

    @classmethod
    def reconcile_rollback(
        cls, db: Session, *, request_id: uuid.UUID
    ) -> ChatExecutorRollbackAudit:
        row = db.get(ChatExecutorRollbackAudit, request_id)
        if row is None:
            raise ExecutorRollbackRejected("Executor rollback request is unknown")
        cell = db.get(ChatExecutorCell, row.cell_id)
        if cell is None or cell.rollback_epoch < row.epoch or row.outcome != "applied":
            raise ExecutorStorageUnavailable(
                "Executor rollback audit and manifest pointer disagree"
            )
        if (
            cell.rollback_epoch == row.epoch
            and cell.selected_manifest_digest != row.target_digest
        ):
            raise ExecutorStorageUnavailable(
                "Executor rollback audit and manifest pointer disagree"
            )
        return row

    @classmethod
    def _matching_rollback(
        cls,
        db: Session,
        row: ChatExecutorRollbackAudit,
        *,
        cell_id: str,
        target_digest: str,
        actor: str,
        reason_class: str,
        qualification_evidence_ref: str,
    ) -> ChatExecutorRollbackAudit:
        expected = (
            cell_id,
            target_digest,
            actor,
            reason_class,
            qualification_evidence_ref,
        )
        actual = (
            row.cell_id,
            row.target_digest,
            row.actor,
            row.reason_class,
            row.qualification_evidence_ref,
        )
        if actual != expected:
            raise ExecutorRollbackRejected("Executor rollback request conflicts")
        return cls.reconcile_rollback(db, request_id=row.request_id)
