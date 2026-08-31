"""Atomic durable admission bridge for the existing chat transaction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ChatMessageRecord, ChatSession, ChatTurnJob
from backend.services.chat_edit_service import PREPARING_STATUS, ChatEditService
from backend.services.chat_external_worker_capacity import (
    ChatExternalWorkerCapacityRepository,
    ExternalWorkerCapacityUnavailable,
    ExternalWorkerReservation,
    external_worker_endpoints,
)
from backend.services.chat_durable_qualification_evidence import QualificationContext
from backend.services.chat_turn_job_repository import (
    ChatOverload,
    ChatTurnJobRepository,
    ExpiryProjectionMismatch,
    IdempotencyMismatch,
    TurnAdmissionPreflight,
)
from backend.services.chat_durable_lifecycle_observer import (
    durable_lifecycle_observer,
)


@dataclass(frozen=True, slots=True)
class DurableAdmissionPreflight:
    request_id: str
    requested_session_id: uuid.UUID | None
    reconciled_expired_count: int
    existing_job: ChatTurnJob | None
    repository_preflight: TurnAdmissionPreflight
    external_reservation: ExternalWorkerReservation | None = None


class ChatTurnAdmissionCoordinator:
    """Compose durable ownership with the caller's session transaction."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        repository: ChatTurnJobRepository | None = None,
        external_capacity: ChatExternalWorkerCapacityRepository | None = None,
        observe=None,
    ):
        self.db = db
        self.settings = settings
        self.repository = repository or ChatTurnJobRepository()
        self.external_capacity = external_capacity
        self.observe = observe or durable_lifecycle_observer(settings)

    def preflight(
        self,
        *,
        hf_user_id: str,
        request_id: str,
        requested_session_id: uuid.UUID | None,
        qualification: QualificationContext | None = None,
        now: datetime | None = None,
    ) -> DurableAdmissionPreflight:
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("Durable admission timestamp is invalid")
        self.repository.lock_admission_authority(self.db, hf_user_id=hf_user_id)
        reconciled_expired_count = self._reconcile_expired_claims(
            hf_user_id=hf_user_id, now=now
        )
        result = self.repository.preflight_admission(
            self.db,
            hf_user_id=hf_user_id,
            request_id=request_id,
            chat_session_id=requested_session_id,
            emergency_capacity=(
                qualification.turn_capacity
                if qualification is not None
                else self.settings.chat_max_concurrency
            ),
            authority_locked=True,
            now=now,
        )
        return DurableAdmissionPreflight(
            request_id=request_id,
            requested_session_id=requested_session_id,
            reconciled_expired_count=reconciled_expired_count,
            existing_job=result.existing_job,
            repository_preflight=result,
        )

    def reserve_external_capacity(
        self,
        preflight: DurableAdmissionPreflight,
        *,
        now: datetime,
    ) -> DurableAdmissionPreflight:
        if preflight.existing_job is not None:
            return preflight
        try:
            capacity = self.external_capacity or ChatExternalWorkerCapacityRepository(
                environment=self.settings.environment
            )
            reservation = capacity.reserve(
                self.db,
                request_id=preflight.request_id,
                endpoints=external_worker_endpoints(self.settings),
                contract_version=self.settings.chat_external_pi_worker_contract_version,
                now=now,
            )
        except ExternalWorkerCapacityUnavailable as error:
            self.observe("capacity_saturation", None, 1)
            raise ChatOverload("External worker capacity is full") from error
        self.external_capacity = capacity
        return replace(preflight, external_reservation=reservation)

    def _reconcile_expired_claims(self, *, hf_user_id: str, now: datetime) -> int:
        """Atomically repair bounded durable and legacy expiry projections."""
        jobs = self.repository.load_expired_claims(
            self.db,
            now=now,
            hf_user_id=hf_user_id,
            limit=min(self.settings.chat_max_concurrency, 100),
        )
        edits = ChatEditService(self.db)
        reconciled_count = 0
        for candidate in jobs:
            session = self.db.execute(
                select(ChatSession)
                .where(ChatSession.id == candidate.chat_session_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            job = self.repository.load_by_turn(self.db, candidate.turn_id, lock=True)
            if (
                session is None
                or job is None
                or job.chat_session_id != candidate.chat_session_id
                or job.hf_user_id != candidate.hf_user_id
            ):
                raise ExpiryProjectionMismatch(
                    "Expired durable turn projection mismatches"
                )
            if not self.repository.is_expired_claim(job, now=now):
                if (
                    job.state in ("completed", "failed", "interrupted")
                    and session.active_turn_id == job.turn_id
                ):
                    raise ExpiryProjectionMismatch(
                        "Terminal durable turn projection remains active"
                    )
                continue
            message = self.db.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == job.chat_session_id,
                    ChatMessageRecord.turn_id == job.turn_id,
                    ChatMessageRecord.role == "user",
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            if (
                session.hf_user_id != job.hf_user_id
                or session.active_turn_id != job.turn_id
                or message is None
                or message.status not in ("generating", PREPARING_STATUS)
            ):
                raise ExpiryProjectionMismatch(
                    "Expired durable turn projection mismatches"
                )
            self.repository.interrupt_exact_expired(
                self.db, turn_id=job.turn_id, now=now
            )
            if message.status == PREPARING_STATUS:
                edits.expire_preparation(session, message)
            message.status = "interrupted"
            message.error_code = "lease_expired"
            session.active_turn_id = None
            session.active_turn_expires_at = None
            reconciled_count += 1
        return reconciled_count

    def admit(
        self,
        preflight: DurableAdmissionPreflight,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        hf_user_id: str,
        revision: int,
        dispatch_route: str,
        app_release_id: str,
        worker_contract_version: str,
        now: datetime,
    ) -> ChatTurnJob:
        admitted = self.repository.admit_preflighted(
            self.db,
            preflight=preflight.repository_preflight,
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            hf_user_id=hf_user_id,
            request_id=preflight.request_id,
            revision=revision,
            dispatch_class="interactive",
            dispatch_route=dispatch_route,
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            now=now,
        )
        if admitted.created:
            if preflight.external_reservation is not None:
                if self.external_capacity is None:
                    raise RuntimeError("External worker capacity repository is missing")
                self.external_capacity.bind_turn(
                    self.db,
                    reservation=preflight.external_reservation,
                    turn_id=turn_id,
                    now=now,
                )
            self.observe("turn_state", "admitted", 1)
        return admitted.job

    def validate_replay(
        self,
        preflight: DurableAdmissionPreflight,
        *,
        turn_id: uuid.UUID,
        chat_session_id: uuid.UUID,
        hf_user_id: str,
        revision: int,
        dispatch_route: str,
        app_release_id: str,
        worker_contract_version: str,
        now: datetime,
    ) -> ChatTurnJob:
        if preflight.existing_job is None:
            raise IdempotencyMismatch("Durable replay has no persisted turn job")
        self.observe("turn_replay", "accepted", 1)
        return self.admit(
            preflight,
            turn_id=turn_id,
            chat_session_id=chat_session_id,
            hf_user_id=hf_user_id,
            revision=revision,
            dispatch_route=dispatch_route,
            app_release_id=app_release_id,
            worker_contract_version=worker_contract_version,
            now=now,
        )
