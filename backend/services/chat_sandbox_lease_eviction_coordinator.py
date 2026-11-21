"""Assigned idle-lease snapshot and termination orchestration."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_sandbox_capacity_repository import lock_capacity
from backend.services.chat_sandbox_provider import SandboxProvider
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_sandbox_state_repository import (
    ChatSandboxStateRepository,
    IdleLeaseCandidate,
    TerminationClaim,
)
from backend.services.chat_sandbox_worker_transport import ChatSandboxWorkerTransport

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]
CapacityLocker = Callable[[Session], bool]
UtcClock = Callable[[], datetime]
TokenFactory = Callable[[], str]


class SnapshotWriter(Protocol):
    async def save(self, sandbox: object, chat_session_id: uuid.UUID) -> str: ...


class LeaseEvictionOutcome(StrEnum):
    EVICTED = "evicted"
    NOT_IDLE = "not_idle"
    OWNERSHIP_CHANGED = "ownership_changed"

    @property
    def acquired(self) -> bool:
        """Preserve the legacy success contract once an idle claim was acquired."""

        return self is not LeaseEvictionOutcome.NOT_IDLE


class ChatSandboxLeaseEvictionCoordinator:
    """Evict one assigned idle lease without holding a transaction over I/O."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: SessionFactory,
        repository: ChatSandboxStateRepository,
        provider: SandboxProvider,
        transport: ChatSandboxWorkerTransport,
        snapshots: SnapshotWriter,
        spend_factory: SpendFactory | None = None,
        capacity_locker: CapacityLocker = lock_capacity,
        utcnow: UtcClock | None = None,
        token_factory: TokenFactory | None = None,
    ) -> None:
        if transport.provider is not provider:
            raise ValueError("Lease eviction provider and transport must be shared")
        self.settings = settings
        self.session_factory = session_factory
        self.repository = repository
        self.provider = provider
        self.transport = transport
        self.snapshots = snapshots
        self.spend_factory = spend_factory or (
            lambda db: ChatSandboxSpendService(db, settings)
        )
        self.capacity_locker = capacity_locker
        self.utcnow = utcnow or (lambda: datetime.now(UTC))
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(24))

    @property
    def ready_timeout_seconds(self) -> float:
        if getattr(self.settings, "chat_persistent_worker_enabled", False):
            return getattr(
                self.settings,
                "chat_worker_ready_timeout_seconds",
                self.settings.chat_sandbox_ready_timeout_seconds,
            )
        return self.settings.chat_sandbox_ready_timeout_seconds

    @property
    def blank_pool_enabled(self) -> bool:
        return bool(
            getattr(self.settings, "chat_blank_pool_enabled", False)
            and getattr(self.settings, "chat_sandbox_admission_enabled", True)
        )

    async def evict_idle(
        self,
        chat_session_id: uuid.UUID,
    ) -> LeaseEvictionOutcome:
        claim = self._claim_idle(chat_session_id)
        if claim is None:
            return LeaseEvictionOutcome.NOT_IDLE
        return await self._evict_claimed(chat_session_id, claim)

    async def evict_candidate(
        self,
        candidate: IdleLeaseCandidate,
        *,
        cutoff: datetime | None = None,
    ) -> LeaseEvictionOutcome:
        claim = self._claim_candidate(candidate, cutoff=cutoff)
        if claim is None:
            return LeaseEvictionOutcome.NOT_IDLE
        return await self._evict_claimed(candidate.chat_session_id, claim)

    async def _evict_claimed(
        self,
        chat_session_id: uuid.UUID,
        claim: TerminationClaim,
    ) -> LeaseEvictionOutcome:
        sandbox_id = claim.sandbox_id
        assert sandbox_id is not None
        control = self.transport.session_control(chat_session_id)
        if control is not None and control.sandbox_id != sandbox_id:
            control = None
        if claim.should_snapshot:
            await self._save_snapshot(chat_session_id, sandbox_id, claim)

        if control is not None:
            self.transport.drop_session_control(
                chat_session_id,
                expected=control,
            )
        confirmed = await self.provider.terminate(sandbox_id)
        return self._finalize(
            chat_session_id,
            claim,
            sandbox_id=sandbox_id,
            confirmed=confirmed,
        )

    def _claim_idle(self, chat_session_id: uuid.UUID) -> TerminationClaim | None:
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            lease = self.repository.load_lease(db, chat_session_id, lock=True)
            return self.repository.claim_snapshot_termination(
                lease,
                termination_token=self.token_factory(),
                expires_at=now + timedelta(seconds=self.ready_timeout_seconds + 15),
            )

    def _claim_candidate(
        self,
        candidate: IdleLeaseCandidate,
        *,
        cutoff: datetime | None,
    ) -> TerminationClaim | None:
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            lease = self.repository.load_lease(
                db,
                candidate.chat_session_id,
                lock=True,
            )
            return self.repository.claim_idle_candidate_termination(
                lease,
                candidate=candidate,
                termination_token=self.token_factory(),
                expires_at=now + timedelta(seconds=self.ready_timeout_seconds + 15),
                cutoff=cutoff,
            )

    async def _save_snapshot(
        self,
        chat_session_id: uuid.UUID,
        sandbox_id: str,
        claim: TerminationClaim,
    ) -> None:
        try:
            sandbox = await self.provider.resolve(sandbox_id)
            snapshot_id = await self.snapshots.save(sandbox, chat_session_id)
            with self.session_factory() as db, db.begin():
                lease = self.repository.load_lease(db, chat_session_id, lock=True)
                self.repository.record_snapshot(
                    lease,
                    claim=claim,
                    snapshot_id=snapshot_id,
                    image_version=self.settings.chat_modal_image_version,
                    now=self.utcnow(),
                )
        except Exception:
            pass

    def _finalize(
        self,
        chat_session_id: uuid.UUID,
        claim: TerminationClaim,
        *,
        sandbox_id: str,
        confirmed: bool,
    ) -> LeaseEvictionOutcome:
        now = self.utcnow()
        with self.session_factory() as db, db.begin():
            spend_enforced = getattr(
                self.settings,
                "chat_sandbox_spend_enforcement_enabled",
                False,
            )
            if self.blank_pool_enabled or spend_enforced:
                self.capacity_locker(db)
            lease = self.repository.load_lease(db, chat_session_id, lock=True)
            finished = self.repository.finish_termination(
                lease,
                claim=claim,
                state="terminated",
                failure_code=None,
                clear_sandbox=True,
                now=now,
            )
            if spend_enforced:
                self.spend_factory(db).terminate(
                    sandbox_id,
                    "snapshot_complete",
                    confirmed=confirmed,
                    now=now,
                )
        if finished:
            return LeaseEvictionOutcome.EVICTED
        return LeaseEvictionOutcome.OWNERSHIP_CHANGED
