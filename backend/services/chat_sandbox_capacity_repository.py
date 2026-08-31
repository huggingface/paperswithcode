"""Transaction-scoped chat sandbox acquisition and capacity decisions."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, TypeAlias

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.chat_sandbox_worker.mcp_app_registry import (
    EMPTY_EGRESS_POLICY_DIGEST,
    egress_policy_digest,
)
from backend.models.database import ChatSandboxLease, ChatSandboxPool
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    LeaseStateClaim,
    StartClaim,
    TerminationClaim,
)

CAPACITY_LOCK_NAME = "chat-sandbox-capacity-v1"
LIVE_LEASE_STATES = ("starting", "ready", "busy", "idle", "terminating")
LIVE_POOL_STATES = ("starting", "blank_ready", "draining")


def lock_capacity(db: Session, *, wait: bool = True) -> bool:
    """Acquire the shared sandbox/spend capacity lock on PostgreSQL."""

    get_bind = getattr(db, "get_bind", None)
    if get_bind is not None and get_bind().dialect.name != "postgresql":
        return True
    function = func.pg_advisory_xact_lock if wait else func.pg_try_advisory_xact_lock
    result = db.scalar(select(function(func.hashtextextended(CAPACITY_LOCK_NAME, 0))))
    return True if wait else bool(result)


@dataclass(frozen=True)
class ReuseLease:
    sandbox_id: str
    worker_generation: str
    expected: LeaseStateClaim


@dataclass(frozen=True)
class WaitForLease:
    state: Literal["starting", "terminating"]
    expected: LeaseStateClaim


@dataclass(frozen=True)
class StartEligible:
    expected: LeaseStateClaim | None


@dataclass(frozen=True)
class RecoveryRequired:
    claim: TerminationClaim


@dataclass(frozen=True)
class EvictionRequired:
    chat_session_id: uuid.UUID


@dataclass(frozen=True)
class CapacityUnavailable:
    pass


AcquisitionDecision: TypeAlias = (
    ReuseLease
    | WaitForLease
    | StartEligible
    | RecoveryRequired
    | EvictionRequired
    | CapacityUnavailable
)

CapacityLocker = Callable[..., bool]
StartLocker = Callable[[Session, uuid.UUID], None]
LeaseLoader = Callable[..., ChatSandboxLease | None]
ReserveInterval = Callable[[str], uuid.UUID]


class LeaseDecisionChanged(RuntimeError):
    """The locked lease no longer matches its acquisition decision."""


@dataclass(frozen=True)
class StartAcquired:
    claim: StartClaim
    interval_id: uuid.UUID | None


AcquisitionOutcome: TypeAlias = (
    ReuseLease
    | WaitForLease
    | StartAcquired
    | RecoveryRequired
    | EvictionRequired
    | CapacityUnavailable
)


class ChatSandboxCapacityRepository:
    """Select and claim acquisition state without committing transactions."""

    def __init__(
        self,
        settings: Settings,
        state_repository: ChatSandboxStateRepository,
        *,
        capacity_locker: CapacityLocker = lock_capacity,
        start_locker: StartLocker | None = None,
        lease_loader: LeaseLoader | None = None,
    ):
        self.settings = settings
        self.state_repository = state_repository
        self._capacity_locker = capacity_locker
        self._start_locker = start_locker or state_repository.lock_start_claim
        self._lease_loader = lease_loader or state_repository.load_lease

    @property
    def capacity_locker(self) -> CapacityLocker:
        """Expose the exact shared capacity lock dependency to coordinators."""

        return self._capacity_locker

    def acquire_capacity_lock(self, db: Session, *, wait: bool = True) -> bool:
        """Acquire the configured capacity lock without exposing private state."""

        return self._capacity_locker(db, wait=wait)

    def select(
        self,
        db: Session,
        chat_session_id: uuid.UUID,
        *,
        now: datetime,
        ready_timeout_seconds: float,
    ) -> AcquisitionDecision:
        """Lock in global-to-local order and return one exhaustive outcome."""

        lease = self._lock_lease(db, chat_session_id)
        return self._select_locked(
            db,
            chat_session_id,
            lease=lease,
            now=now,
            ready_timeout_seconds=ready_timeout_seconds,
        )

    def acquire(
        self,
        db: Session,
        chat_session_id: uuid.UUID,
        *,
        creation_token: str,
        worker_generation: str,
        now: datetime,
        ready_timeout_seconds: float,
        reserve_interval: ReserveInterval | None = None,
        total_live_cap: int | None = None,
    ) -> AcquisitionOutcome:
        """Select and claim a start while retaining every database lock."""

        lease = self._lock_lease(db, chat_session_id)
        decision = self._select_locked(
            db,
            chat_session_id,
            lease=lease,
            now=now,
            ready_timeout_seconds=ready_timeout_seconds,
            total_live_cap=total_live_cap,
        )
        if not isinstance(decision, StartEligible):
            return decision

        # Spend reservation deliberately precedes lease mutation. A rejected
        # reservation may trip the durable circuit but must leave the lease exact.
        interval_id = (
            reserve_interval(worker_generation)
            if reserve_interval is not None
            else None
        )
        claim = self._claim_loaded_start(
            db,
            lease,
            decision,
            chat_session_id=chat_session_id,
            creation_token=creation_token,
            worker_generation=worker_generation,
            now=now,
            ready_timeout_seconds=ready_timeout_seconds,
        )
        return StartAcquired(claim=claim, interval_id=interval_id)

    def _lock_lease(
        self, db: Session, chat_session_id: uuid.UUID
    ) -> ChatSandboxLease | None:
        if self._capacity_lock_required:
            self._capacity_locker(db, wait=True)
        self._start_locker(db, chat_session_id)
        return self._lease_loader(db, chat_session_id, lock=True)

    def _select_locked(
        self,
        db: Session,
        chat_session_id: uuid.UUID,
        *,
        lease: ChatSandboxLease | None,
        now: datetime,
        ready_timeout_seconds: float,
        total_live_cap: int | None = None,
    ) -> AcquisitionDecision:
        compatible = bool(
            lease
            and lease.image_version == self.settings.chat_modal_image_version
            and lease.worker_contract_version
            == self.settings.chat_worker_contract_version
            and (lease.egress_policy_digest or EMPTY_EGRESS_POLICY_DIGEST)
            == egress_policy_digest(self.settings)
            and lease.worker_generation is not None
        )

        if (
            lease
            and compatible
            and lease.modal_sandbox_id
            and lease.state in {"ready", "idle", "busy"}
        ):
            return ReuseLease(
                sandbox_id=lease.modal_sandbox_id,
                worker_generation=lease.worker_generation or "",
                expected=self._state_claim(lease),
            )

        # A start owner may still be between the database claim and provider
        # creation. With no provider ID there is nothing safe to recover yet,
        # even when that owner's target image has since become incompatible.
        if (
            lease
            and lease.state == "starting"
            and lease.lease_token_hash
            and self.state_repository.unexpired(lease, now)
            and (lease.modal_sandbox_id is None or compatible)
        ):
            return WaitForLease(
                state="starting",
                expected=self._state_claim(lease),
            )

        if (
            lease
            and compatible
            and lease.state == "terminating"
            and lease.modal_sandbox_id
            and lease.lease_token_hash
            and self.state_repository.unexpired(lease, now)
        ):
            return WaitForLease(
                state="terminating",
                expected=self._state_claim(lease),
            )

        if lease is not None and lease.modal_sandbox_id:
            failure_code = (
                lease.failure_code if lease.state == "terminating" else "stale_replaced"
            )
            claim = self.state_repository.claim_termination(
                lease,
                termination_token=secrets.token_urlsafe(24),
                failure_code=failure_code,
                expires_at=now + timedelta(seconds=ready_timeout_seconds + 15),
            )
            if claim is None:  # pragma: no cover - the row is locked and non-null
                raise LeaseDecisionChanged
            return RecoveryRequired(claim=claim)

        if self._capacity_enabled:
            live_assigned = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxLease)
                    .where(
                        ChatSandboxLease.chat_session_id != chat_session_id,
                        ChatSandboxLease.state.in_(LIVE_LEASE_STATES),
                    )
                )
                or 0
            )
            live_pool = (
                db.scalar(
                    select(func.count())
                    .select_from(ChatSandboxPool)
                    .where(ChatSandboxPool.state.in_(LIVE_POOL_STATES))
                )
                or 0
            )
            capacity = (
                total_live_cap
                if total_live_cap is not None
                else self.settings.chat_sandbox_total_live_cap
            )
            if live_assigned + live_pool >= capacity:
                evict_session_id = db.execute(
                    select(ChatSandboxLease.chat_session_id)
                    .where(
                        ChatSandboxLease.chat_session_id != chat_session_id,
                        ChatSandboxLease.state == "idle",
                        ChatSandboxLease.modal_sandbox_id.is_not(None),
                    )
                    .order_by(ChatSandboxLease.last_activity_at)
                    .limit(1)
                ).scalar_one_or_none()
                if evict_session_id is None:
                    return CapacityUnavailable()
                return EvictionRequired(chat_session_id=evict_session_id)

        return StartEligible(
            expected=self._state_claim(lease) if lease is not None else None
        )

    def finish_recovery(
        self,
        db: Session,
        chat_session_id: uuid.UUID,
        *,
        claim: TerminationClaim,
        now: datetime,
    ) -> bool:
        """Finish only the exact recovery claim after provider confirmation."""

        lease = self._lock_lease(db, chat_session_id)
        return self.state_repository.finish_termination(
            lease,
            claim=claim,
            state="failed" if claim.failure_code else "terminated",
            failure_code=claim.failure_code,
            clear_sandbox=True,
            now=now,
        )

    def claim_reuse_recovery(
        self,
        db: Session,
        chat_session_id: uuid.UUID,
        candidate: ReuseLease,
        *,
        now: datetime,
        ready_timeout_seconds: float,
    ) -> RecoveryRequired:
        """Claim cleanup only while the exact reused lease is still current."""

        lease = self._lock_lease(db, chat_session_id)
        if (
            lease is None
            or candidate.expected.sandbox_id != candidate.sandbox_id
            or candidate.expected.worker_generation != candidate.worker_generation
            or self._state_claim(lease) != candidate.expected
        ):
            raise LeaseDecisionChanged
        claim = self.state_repository.claim_termination(
            lease,
            termination_token=secrets.token_urlsafe(24),
            failure_code="stale_replaced",
            expires_at=now + timedelta(seconds=ready_timeout_seconds + 15),
        )
        if claim is None:  # pragma: no cover - the exact locked lease exists
            raise LeaseDecisionChanged
        return RecoveryRequired(claim=claim)

    def _claim_loaded_start(
        self,
        db: Session,
        lease: ChatSandboxLease | None,
        decision: StartEligible,
        *,
        chat_session_id: uuid.UUID,
        creation_token: str,
        worker_generation: str,
        now: datetime,
        ready_timeout_seconds: float,
    ) -> StartClaim:
        if decision.expected is None:
            if lease is not None:
                raise LeaseDecisionChanged
            token_hash = self.state_repository.token_hash(creation_token)
            lease = ChatSandboxLease(
                chat_session_id=chat_session_id,
                app_release_id=self.settings.release_id,
                image_version=self.settings.chat_modal_image_version,
                worker_contract_version=self.settings.chat_worker_contract_version,
                egress_policy_digest=egress_policy_digest(self.settings),
                worker_generation=worker_generation,
                state="starting",
                lease_token_hash=token_hash,
                lease_expires_at=now + timedelta(seconds=ready_timeout_seconds + 15),
                last_activity_at=now,
            )
            db.add(lease)
            return StartClaim(
                token_hash=token_hash,
                stale_sandbox_id=None,
                snapshot_id=None,
                worker_generation=worker_generation,
            )

        if lease is None or self._state_claim(lease) != decision.expected:
            raise LeaseDecisionChanged
        self._repair_missing_active_lease(lease, decision.expected, now=now)
        return self.state_repository.claim_start(
            lease,
            creation_token=creation_token,
            now=now,
            ready_timeout_seconds=ready_timeout_seconds,
            worker_generation=worker_generation,
        )

    @staticmethod
    def _repair_missing_active_lease(
        lease: ChatSandboxLease,
        expected: LeaseStateClaim,
        *,
        now: datetime,
    ) -> None:
        """Repair an exact active row that cannot own a provider sandbox."""

        if expected.sandbox_id is not None or expected.state not in {
            "ready",
            "busy",
            "idle",
            "terminating",
        }:
            return
        if ChatSandboxCapacityRepository._state_claim(lease) != expected:
            raise LeaseDecisionChanged
        lease.state = "failed"
        lease.failure_code = "sandbox_lost"
        lease.lease_token_hash = None
        lease.lease_expires_at = None
        lease.updated_at = now

    @property
    def _capacity_enabled(self) -> bool:
        return bool(
            getattr(self.settings, "chat_blank_pool_enabled", False)
            and getattr(self.settings, "chat_sandbox_admission_enabled", True)
        )

    @property
    def _capacity_lock_required(self) -> bool:
        return bool(
            self._capacity_enabled
            or getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False)
        )

    @staticmethod
    def _state_claim(lease: ChatSandboxLease) -> LeaseStateClaim:
        return LeaseStateClaim(
            state=lease.state,
            sandbox_id=lease.modal_sandbox_id,
            token_hash=lease.lease_token_hash,
            worker_generation=lease.worker_generation,
        )
