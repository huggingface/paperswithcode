"""PostgreSQL-backed durable ownership and fencing for research chat turns."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, SessionTransaction

from backend.models.database import ChatMessageRecord, ChatSession, ChatTurnJob
from backend.services.chat_turn_lifecycle import (
    CLAIMED_STATES as _CLAIMED_STATES,
    FAILURE_CODE_PATTERN as _FAILURE_CODE,
    NONTERMINAL_STATES,
    RECONCILABLE_FAILURE_CODES as _RECONCILABLE_FAILURE_CODES,
    TERMINAL_STATES,
    TRANSITIONS as _TRANSITIONS,
    classify_expired_state,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def classify_expired_turn(job: ChatTurnJob) -> str:
    """Classify an expired owner from durable, content-free evidence only."""
    return classify_expired_state(job.state, job.failure_code)


class TurnJobError(RuntimeError):
    """Base class for typed durable turn-job outcomes."""


class AdmissionRejected(TurnJobError):
    code: str


class AccountBusy(AdmissionRejected):
    code = "account_busy"


class ChatOverload(AdmissionRejected):
    code = "chat_overload"


class IdempotencyMismatch(TurnJobError):
    """A turn or request identifier was reused with different identity."""


class TurnNotClaimable(TurnJobError):
    """The exact durable turn cannot be claimed from its current state."""


class StaleTurnClaim(TurnJobError):
    """A post-claim mutation did not carry the exact current fencing tuple."""


class InvalidTurnTransition(TurnJobError):
    """A claimed turn requested an invalid state transition."""


class ExpiryProjectionMismatch(TurnJobError):
    """An expired durable turn disagrees with its legacy projection."""


@dataclass(frozen=True, slots=True)
class TurnLeaseClaim:
    turn_id: uuid.UUID
    worker_id: str
    worker_generation: int
    lease_generation: int


@dataclass(frozen=True, slots=True)
class TurnAdmission:
    job: ChatTurnJob
    created: bool


@dataclass(frozen=True, slots=True)
class TurnAdmissionPreflight:
    hf_user_id: str
    request_id: str
    requested_session_id: uuid.UUID | None
    emergency_capacity: int
    existing_job: ChatTurnJob | None
    session: Session = field(repr=False, compare=False)
    transaction: SessionTransaction = field(repr=False, compare=False)


AdvisoryLocker = Callable[[Session, str], None]


class ChatTurnJobRepository:
    """Persist one content-free job per turn with PostgreSQL fencing semantics."""

    def __init__(self, *, advisory_locker: AdvisoryLocker | None = None):
        self._advisory_locker = advisory_locker or self._lock_advisory_key

    @staticmethod
    def _lock_advisory_key(db: Session, key: str) -> None:
        db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))

    def load_by_turn(
        self, db: Session, turn_id: uuid.UUID, *, lock: bool = False
    ) -> ChatTurnJob | None:
        query = select(ChatTurnJob).where(ChatTurnJob.turn_id == turn_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return db.execute(query).scalar_one_or_none()

    def load_by_request(
        self, db: Session, request_id: str, *, lock: bool = False
    ) -> ChatTurnJob | None:
        query = select(ChatTurnJob).where(ChatTurnJob.request_id == request_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return db.execute(query).scalar_one_or_none()

    def preflight_admission(
        self,
        db: Session,
        *,
        hf_user_id: str,
        request_id: str,
        chat_session_id: uuid.UUID | None,
        emergency_capacity: int,
        turn_id: uuid.UUID | None = None,
        authority_locked: bool = False,
        now: datetime | None = None,
    ) -> TurnAdmissionPreflight:
        """Lock and decide admission before any session or message is written."""
        if (
            not hf_user_id
            or len(hf_user_id) > 255
            or not request_id
            or len(request_id) > 200
            or emergency_capacity <= 0
        ):
            raise ValueError("Turn admission preflight is invalid")
        if not authority_locked:
            self.lock_admission_authority(db, hf_user_id=hf_user_id)
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("Turn admission timestamp is invalid")

        if turn_id is None:
            matches = tuple(
                job
                for job in (self.load_by_request(db, request_id, lock=True),)
                if job is not None
            )
        else:
            matches = tuple(
                db.execute(
                    select(ChatTurnJob)
                    .where(
                        or_(
                            ChatTurnJob.turn_id == turn_id,
                            ChatTurnJob.request_id == request_id,
                        )
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).scalars()
            )
        if matches:
            existing = matches[0]
            if (
                len(matches) != 1
                or existing.request_id != request_id
                or (turn_id is not None and existing.turn_id != turn_id)
                or existing.hf_user_id != hf_user_id
                or (
                    chat_session_id is not None
                    and existing.chat_session_id != chat_session_id
                )
            ):
                raise IdempotencyMismatch("Request idempotency identity mismatches")
            return TurnAdmissionPreflight(
                hf_user_id=hf_user_id,
                request_id=request_id,
                requested_session_id=chat_session_id,
                emergency_capacity=emergency_capacity,
                existing_job=existing,
                session=db,
                transaction=self._active_transaction(db),
            )

        owner_active = db.scalar(
            select(func.count())
            .select_from(ChatTurnJob)
            .where(
                ChatTurnJob.hf_user_id == hf_user_id,
                ChatTurnJob.state.in_(NONTERMINAL_STATES),
                or_(
                    ChatTurnJob.state == "admitted",
                    ChatTurnJob.lease_expires_at > now,
                ),
            )
        )
        if owner_active:
            raise AccountBusy("This account already has a nonterminal turn")
        active_total = db.scalar(
            select(func.count())
            .select_from(ChatTurnJob)
            .where(
                ChatTurnJob.state.in_(NONTERMINAL_STATES),
                or_(
                    ChatTurnJob.state == "admitted",
                    ChatTurnJob.lease_expires_at > now,
                ),
            )
        )
        if (active_total or 0) >= emergency_capacity:
            raise ChatOverload("Emergency chat capacity is full")
        return TurnAdmissionPreflight(
            hf_user_id=hf_user_id,
            request_id=request_id,
            requested_session_id=chat_session_id,
            emergency_capacity=emergency_capacity,
            existing_job=None,
            session=db,
            transaction=self._active_transaction(db),
        )

    def lock_admission_authority(self, db: Session, *, hf_user_id: str) -> None:
        """Acquire user then global admission authority for the transaction."""
        self._advisory_locker(db, f"chat-user:{hf_user_id}")
        self._advisory_locker(db, "chat-global-active-turns")

    def load_expired_claims(
        self,
        db: Session,
        *,
        now: datetime,
        hf_user_id: str,
        limit: int,
    ) -> tuple[ChatTurnJob, ...]:
        if (
            now.tzinfo is None
            or not hf_user_id
            or len(hf_user_id) > 255
            or limit <= 0
            or limit > 100
        ):
            raise ValueError("Expired turn reconciliation bound is invalid")
        return tuple(
            db.execute(
                select(ChatTurnJob)
                .where(
                    ChatTurnJob.state.in_(_CLAIMED_STATES),
                    ChatTurnJob.lease_expires_at <= now,
                )
                .order_by(
                    case((ChatTurnJob.hf_user_id == hf_user_id, 0), else_=1),
                    ChatTurnJob.lease_expires_at,
                    ChatTurnJob.turn_id,
                )
                .limit(limit)
                .execution_options(populate_existing=True)
            ).scalars()
        )

    def load_expired_candidates(
        self,
        db: Session,
        *,
        now: datetime,
        limit: int,
    ) -> tuple[tuple[uuid.UUID, uuid.UUID], ...]:
        """Scan content-free candidates; authority is locked session-first later."""
        if now.tzinfo is None or limit <= 0 or limit > 100:
            raise ValueError("Expired turn reconciliation bound is invalid")
        valid_projection = and_(
            exists(
                select(ChatSession.id).where(
                    ChatSession.id == ChatTurnJob.chat_session_id,
                    ChatSession.hf_user_id == ChatTurnJob.hf_user_id,
                    ChatSession.active_turn_id == ChatTurnJob.turn_id,
                )
            ),
            exists(
                select(ChatMessageRecord.id).where(
                    ChatMessageRecord.session_id == ChatTurnJob.chat_session_id,
                    ChatMessageRecord.turn_id == ChatTurnJob.turn_id,
                    ChatMessageRecord.role == "user",
                    ChatMessageRecord.status.in_(("generating", "preparing")),
                )
            ),
        )
        return tuple(
            db.execute(
                select(ChatTurnJob.chat_session_id, ChatTurnJob.turn_id)
                .where(
                    ChatTurnJob.state.in_(_CLAIMED_STATES),
                    ChatTurnJob.lease_expires_at <= now,
                )
                .order_by(
                    case((valid_projection, 0), else_=1),
                    ChatTurnJob.lease_expires_at,
                    ChatTurnJob.turn_id,
                )
                .limit(limit)
            ).tuples()
        )

    def is_expired_claim(self, job: ChatTurnJob, *, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("Expiry timestamp is invalid")
        return job.state in _CLAIMED_STATES and self._lease_expired(job, now)

    def admit(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        hf_user_id: str,
        request_id: str,
        revision: int,
        dispatch_class: str,
        dispatch_route: str,
        app_release_id: str,
        worker_contract_version: str,
        now: datetime,
        emergency_capacity: int,
    ) -> TurnAdmission:
        self._validate_admission(
            hf_user_id=hf_user_id,
            request_id=request_id,
            revision=revision,
            dispatch_class=dispatch_class,
            dispatch_route=dispatch_route,
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            now=now,
            emergency_capacity=emergency_capacity,
        )
        preflight = self.preflight_admission(
            db,
            hf_user_id=hf_user_id,
            request_id=request_id,
            chat_session_id=chat_session_id,
            emergency_capacity=emergency_capacity,
            turn_id=turn_id,
            now=now,
        )

        return self.admit_preflighted(
            db,
            preflight=preflight,
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            hf_user_id=hf_user_id,
            request_id=request_id,
            revision=revision,
            dispatch_class=dispatch_class,
            dispatch_route=dispatch_route,
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            now=now,
        )

    def admit_preflighted(
        self,
        db: Session,
        *,
        preflight: TurnAdmissionPreflight,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        hf_user_id: str,
        request_id: str,
        revision: int,
        dispatch_class: str,
        dispatch_route: str,
        app_release_id: str,
        worker_contract_version: str,
        now: datetime,
    ) -> TurnAdmission:
        """Finalize admission under locks already acquired by ``preflight_admission``."""
        if (
            db is not preflight.session
            or db.get_transaction() is not preflight.transaction
            or not preflight.transaction.is_active
        ):
            raise ValueError("Turn admission preflight transaction is no longer active")
        self._validate_admission(
            hf_user_id=hf_user_id,
            request_id=request_id,
            revision=revision,
            dispatch_class=dispatch_class,
            dispatch_route=dispatch_route,
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            now=now,
            emergency_capacity=preflight.emergency_capacity,
        )
        if (
            preflight.hf_user_id != hf_user_id
            or preflight.request_id != request_id
            or (
                preflight.requested_session_id is not None
                and preflight.requested_session_id != chat_session_id
            )
        ):
            raise IdempotencyMismatch("Admission does not match its preflight identity")

        expected = {
            "turn_id": turn_id,
            "chat_session_id": chat_session_id,
            "hf_user_id": hf_user_id,
            "request_id": request_id,
            "revision": revision,
            "dispatch_class": dispatch_class,
            "dispatch_route": dispatch_route,
            "app_release_id": app_release_id,
            "worker_contract_version": worker_contract_version,
        }
        if preflight.existing_job is not None:
            if not self._matches_admission(preflight.existing_job, **expected):
                raise IdempotencyMismatch(
                    "Preflight replay identity mismatches admission"
                )
            return TurnAdmission(preflight.existing_job, created=False)

        matches = list(
            db.execute(
                select(ChatTurnJob)
                .where(
                    or_(
                        ChatTurnJob.turn_id == turn_id,
                        ChatTurnJob.request_id == request_id,
                    )
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalars()
        )
        if matches:
            if len(matches) != 1 or not self._matches_admission(matches[0], **expected):
                raise IdempotencyMismatch(
                    "Turn/request idempotency identity mismatches"
                )
            return TurnAdmission(matches[0], created=False)

        job = ChatTurnJob(
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            hf_user_id=hf_user_id,
            request_id=request_id,
            revision=revision,
            dispatch_class=dispatch_class,
            dispatch_route=dispatch_route,
            state="admitted",
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            admitted_at=now,
        )
        db.add(job)
        db.flush()
        return TurnAdmission(job, created=True)

    @staticmethod
    def _active_transaction(db: Session) -> SessionTransaction:
        transaction = db.get_transaction()
        if transaction is None or not transaction.is_active:
            raise ValueError("Turn admission preflight requires an active transaction")
        return transaction

    def claim(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        worker_id: str,
        worker_generation: int,
        now: datetime,
        lease_seconds: int,
    ) -> TurnLeaseClaim:
        if (
            _IDENTIFIER.fullmatch(worker_id) is None
            or worker_generation <= 0
            or lease_seconds <= 0
            or now.tzinfo is None
        ):
            raise ValueError("Turn claim is invalid")
        job = self.load_by_turn(db, turn_id, lock=True)
        if job is None or job.state != "admitted":
            raise TurnNotClaimable("Turn is not admitted")
        job.worker_id = worker_id
        job.worker_generation = worker_generation
        job.lease_generation = (job.lease_generation or 0) + 1
        job.state = "leased"
        job.dispatched_at = now
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        db.flush()
        return self._claim_for(job)

    def heartbeat(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        now: datetime,
        lease_seconds: int,
    ) -> ChatTurnJob:
        if now.tzinfo is None or lease_seconds <= 0:
            raise ValueError("Turn heartbeat is invalid")
        job = self._load_claimed(db, claim)
        if job.state not in _CLAIMED_STATES or self._lease_expired(job, now):
            raise StaleTurnClaim("Turn lease is no longer live")
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        db.flush()
        return job

    def require_live_claim(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        now: datetime,
    ) -> ChatTurnJob:
        """Lock and return the job only while the exact claim remains live."""
        if now.tzinfo is None:
            raise ValueError("Turn claim timestamp is invalid")
        job = self._load_claimed(db, claim)
        if job.state not in _CLAIMED_STATES or self._lease_expired(job, now):
            raise StaleTurnClaim("Turn lease is no longer live")
        return job

    def transition(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        state: str,
        now: datetime,
        last_agent_session_id: uuid.UUID | None = None,
        last_resume_boundary_id: str | None = None,
    ) -> ChatTurnJob:
        if now.tzinfo is None:
            raise ValueError("Turn transition timestamp is invalid")
        job = self._load_claimed(db, claim)
        if self._lease_expired(job, now):
            raise StaleTurnClaim("Turn lease is no longer live")
        if state not in _TRANSITIONS.get(job.state, frozenset()):
            raise InvalidTurnTransition(f"Cannot transition {job.state} to {state}")
        job.state = state
        if state == "running" and job.started_at is None:
            job.started_at = now
        job.heartbeat_at = now
        if last_agent_session_id is not None:
            job.last_agent_session_id = last_agent_session_id
        if last_resume_boundary_id is not None:
            job.last_resume_boundary_id = last_resume_boundary_id
        db.flush()
        return job

    def request_cancelling(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        worker_id: str,
        worker_generation: int,
        now: datetime,
        lease_seconds: int,
    ) -> TurnLeaseClaim | None:
        """Lock the exact turn and durably request cancellation once."""
        job = self.load_by_turn(db, turn_id, lock=True)
        if job is None or job.state in TERMINAL_STATES:
            return None
        if job.state == "admitted":
            claim = self.claim(
                db,
                turn_id=turn_id,
                worker_id=worker_id,
                worker_generation=worker_generation,
                now=now,
                lease_seconds=lease_seconds,
            )
        else:
            claim = self.claim_for(job)
            if self._lease_expired(job, now):
                raise StaleTurnClaim("Turn lease is no longer live")
            if job.state == "cancelling":
                return claim
        self.transition(db, claim=claim, state="cancelling", now=now)
        return claim

    def interrupt_control_missing(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        now: datetime,
    ) -> ChatTurnJob:
        """Finish the exact cancelling claim when no runner control exists."""
        if now.tzinfo is None:
            raise ValueError("Control interruption timestamp is invalid")
        job = self._load_claimed(db, claim)
        if job.state in TERMINAL_STATES:
            if (
                job.state != "interrupted"
                or job.failure_code != "cancel_control_missing"
            ):
                raise InvalidTurnTransition("Terminal turn state is immutable")
            return job
        if job.state != "cancelling":
            raise InvalidTurnTransition("Only a cancelling turn can lose control")
        job.state = "interrupted"
        job.failure_code = "cancel_control_missing"
        job.terminal_at = now
        job.heartbeat_at = now
        job.lease_expires_at = None
        db.flush()
        return job

    def interrupt_dispatch_failed(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        worker_id: str,
        worker_generation: int,
        lease_seconds: int,
        admitted_before: datetime,
        now: datetime,
    ) -> ChatTurnJob | None:
        """Terminalize only an admission that never acquired a worker claim."""
        if (
            now.tzinfo is None
            or admitted_before.tzinfo is None
            or admitted_before > now
        ):
            raise ValueError("Dispatch failure timestamp is invalid")
        job = self.load_by_turn(db, turn_id, lock=True)
        if job is None:
            return None
        if job.state in TERMINAL_STATES:
            if job.state != "interrupted" or job.failure_code != "dispatch_failed":
                raise InvalidTurnTransition("Terminal turn state is immutable")
            return job
        if job.state != "admitted":
            return None
        admitted_at = job.admitted_at
        if admitted_at.tzinfo is None:
            admitted_at = admitted_at.replace(tzinfo=UTC)
        if admitted_at >= admitted_before:
            return None
        claim = self.claim(
            db,
            turn_id=turn_id,
            worker_id=worker_id,
            worker_generation=worker_generation,
            now=now,
            lease_seconds=lease_seconds,
        )
        return self.write_terminal(
            db,
            claim=claim,
            state="interrupted",
            failure_code="dispatch_failed",
            now=now,
        )

    def write_terminal(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        state: str,
        now: datetime,
        failure_code: str | None = None,
        last_agent_session_id: uuid.UUID | None = None,
        last_resume_boundary_id: str | None = None,
    ) -> ChatTurnJob:
        if state not in TERMINAL_STATES or now.tzinfo is None:
            raise ValueError("Terminal turn state is invalid")
        if failure_code is not None and _FAILURE_CODE.fullmatch(failure_code) is None:
            raise ValueError("Turn failure code is not sanitized")
        if state == "completed" and failure_code is not None:
            raise ValueError("Completed turn cannot have a failure code")
        job = self._load_claimed(db, claim)
        if job.state in TERMINAL_STATES:
            if job.state != state or job.failure_code != failure_code:
                raise InvalidTurnTransition("Terminal turn state is immutable")
            return job
        if job.state not in _CLAIMED_STATES:
            raise InvalidTurnTransition("Only a claimed turn can become terminal")
        if self._lease_expired(job, now):
            raise StaleTurnClaim("Turn lease is no longer live")
        job.state = state
        job.failure_code = failure_code
        job.terminal_at = now
        job.heartbeat_at = now
        job.lease_expires_at = None
        if last_agent_session_id is not None:
            job.last_agent_session_id = last_agent_session_id
        if last_resume_boundary_id is not None:
            job.last_resume_boundary_id = last_resume_boundary_id
        db.flush()
        return job

    def interrupt_expired(self, db: Session, *, now: datetime, limit: int = 100) -> int:
        if now.tzinfo is None or limit <= 0:
            raise ValueError("Expiry sweep is invalid")
        jobs = list(
            db.execute(
                select(ChatTurnJob)
                .where(
                    ChatTurnJob.state.in_(_CLAIMED_STATES),
                    ChatTurnJob.lease_expires_at <= now,
                )
                .order_by(ChatTurnJob.lease_expires_at, ChatTurnJob.turn_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).scalars()
        )
        for job in jobs:
            job.state = "interrupted"
            job.failure_code = "lease_expired"
            job.terminal_at = now
            job.heartbeat_at = now
            job.lease_expires_at = None
        db.flush()
        return len(jobs)

    def interrupt_expired_claim(
        self,
        db: Session,
        *,
        claim: TurnLeaseClaim,
        failure_code: str,
        now: datetime,
    ) -> ChatTurnJob:
        """Terminalize one exact expired owner without creating replacement work."""
        if now.tzinfo is None or failure_code not in _RECONCILABLE_FAILURE_CODES:
            raise ValueError("Expired turn outcome is invalid")
        job = self._load_claimed(db, claim)
        if job.state not in _CLAIMED_STATES or not self._lease_expired(job, now):
            raise StaleTurnClaim("Expired turn claim is no longer authoritative")
        job.state = "interrupted"
        job.failure_code = failure_code
        job.terminal_at = now
        job.heartbeat_at = now
        job.lease_expires_at = None
        db.flush()
        return job

    def interrupt_exact_expired(
        self,
        db: Session,
        *,
        turn_id: uuid.UUID,
        now: datetime,
        admitted_worker_id: str | None = None,
        admitted_worker_generation: int | None = None,
        lease_seconds: int | None = None,
    ) -> ChatTurnJob:
        """Interrupt one exact expired job without permitting redispatch."""
        if now.tzinfo is None:
            raise ValueError("Expiry timestamp is invalid")
        job = self.load_by_turn(db, turn_id, lock=True)
        if job is None:
            raise StaleTurnClaim("Durable turn is missing")
        if job.state in TERMINAL_STATES:
            if job.state != "interrupted" or job.failure_code != "lease_expired":
                raise InvalidTurnTransition("Terminal turn state is immutable")
            return job
        if job.state == "admitted":
            if (
                admitted_worker_id is None
                or admitted_worker_generation is None
                or lease_seconds is None
            ):
                raise StaleTurnClaim("Admitted turn has no expiry control claim")
            self.claim(
                db,
                turn_id=turn_id,
                worker_id=admitted_worker_id,
                worker_generation=admitted_worker_generation,
                now=now,
                lease_seconds=lease_seconds,
            )
            job = self.load_by_turn(db, turn_id, lock=True)
            assert job is not None
        elif not self._lease_expired(job, now):
            raise StaleTurnClaim("Turn lease is still live")
        job.state = "interrupted"
        job.failure_code = "lease_expired"
        job.terminal_at = now
        job.heartbeat_at = now
        job.lease_expires_at = None
        db.flush()
        return job

    def _load_claimed(self, db: Session, claim: TurnLeaseClaim) -> ChatTurnJob:
        job = self.load_by_turn(db, claim.turn_id, lock=True)
        if job is None or self._claim_for(job) != claim:
            raise StaleTurnClaim("Turn claim was fenced")
        return job

    def claim_for(self, job: ChatTurnJob) -> TurnLeaseClaim:
        """Return the exact persisted fence without creating or replacing it."""
        return self._claim_for(job)

    @staticmethod
    def _lease_expired(job: ChatTurnJob, now: datetime) -> bool:
        expires_at = job.lease_expires_at
        if expires_at is None:
            return True
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= now

    @staticmethod
    def _claim_for(job: ChatTurnJob) -> TurnLeaseClaim:
        if (
            job.worker_id is None
            or job.worker_generation is None
            or job.lease_generation is None
        ):
            raise StaleTurnClaim("Turn has no durable claim")
        return TurnLeaseClaim(
            turn_id=job.turn_id,
            worker_id=job.worker_id,
            worker_generation=job.worker_generation,
            lease_generation=job.lease_generation,
        )

    @staticmethod
    def _matches_admission(job: ChatTurnJob, **expected: object) -> bool:
        return all(getattr(job, name) == value for name, value in expected.items())

    @staticmethod
    def _validate_admission(**values: object) -> None:
        now = values["now"]
        if (
            not values["hf_user_id"]
            or len(values["hf_user_id"]) > 255
            or not values["request_id"]
            or len(values["request_id"]) > 200
            or values["revision"] <= 0
            or _IDENTIFIER.fullmatch(values["dispatch_class"]) is None
            or not values["dispatch_route"]
            or len(values["dispatch_route"]) > 255
            or not values["app_release_id"]
            or len(values["app_release_id"]) > 255
            or _IDENTIFIER.fullmatch(values["worker_contract_version"]) is None
            or not isinstance(now, datetime)
            or now.tzinfo is None
            or values["emergency_capacity"] <= 0
        ):
            raise ValueError("Turn admission is invalid")
