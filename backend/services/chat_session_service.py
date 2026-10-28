"""Transactional ownership, idempotency, leases, and projections for chat."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.chat_configuration import registry
from backend.chat_execution_policy import bounded_url_seed
from backend.config import Settings
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER, CitationSnapshot
from backend.models.database import (
    ChatArtifact,
    ChatArtifactVersion,
    ChatHarnessAssignmentAudit,
    ChatMessageRecord,
    ChatPiSession,
    ChatSandboxLease,
    ChatSDKSessionSummary,
    ChatSDKTranscriptEntry,
    ChatSession,
    ChatShare,
    ChatSharedArtifact,
    ChatTurnReservation,
)
from backend.services.chat_turn_mode import TurnMode, resolve_turn_mode
from backend.services.chat_executor_turn_admission import ChatExecutorTurnAdmission
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.services.chat_edit_service import (
    INACTIVE_STATUSES,
    PREPARING_STATUS,
    ChatEditService,
    user_message_projection_bytes,
)
from backend.services.chat_external_worker_capacity import (
    UnsupportedChatMode,
    require_ordinary_research_mode,
)
from backend.services.chat_local_turn_lease import ChatLocalTurnLeaseService
from backend.services.chat_pi_transcript_service import ChatPiTranscriptService
from backend.services.chat_durable_qualification_evidence import QualificationContext
from backend.services.chat_title_service import normalize_title
from backend.services.chat_turn_admission_coordinator import (
    ChatTurnAdmissionCoordinator,
    DurableAdmissionPreflight,
)
from backend.services.chat_turn_job_repository import (
    AccountBusy,
    ChatOverload,
    ChatTurnJobRepository,
    IdempotencyMismatch,
    InvalidTurnTransition,
    StaleTurnClaim,
    TurnJobError,
    TurnLeaseClaim,
    TurnNotClaimable,
)
from backend.services.chat_turn_admission import (
    ChatTurnAdmissionService,
    TurnReservationError,
)
from backend.services.chat_turn_lifecycle import CLAIMED_STATES
from backend.services.latex_paper_service import LatexPaperService

if TYPE_CHECKING:
    from backend.services.chat_external_worker_capacity import (
        ExternalWorkerReservation,
    )


def _bound_external_worker_reservation(
    preflight: DurableAdmissionPreflight | None, turn_id: uuid.UUID
) -> ExternalWorkerReservation | None:
    reservation = preflight.external_reservation if preflight is not None else None
    if reservation is None:
        return None
    if reservation.turn_id not in {None, turn_id}:
        raise RuntimeError("External worker reservation turn mismatches")
    return replace(reservation, turn_id=turn_id)


class ChatServiceError(Exception):
    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        commit_changes: bool = False,
        active_count: int | None = None,
        details: dict[str, object] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.commit_changes = commit_changes
        self.active_count = active_count
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class CancelTurnRequest:
    session_id: uuid.UUID
    turn_id: uuid.UUID
    claim: TurnLeaseClaim


@dataclass(frozen=True)
class ChatOwner:
    hf_user_id: str
    hf_username: str
    hf_inference_token: str | None = None
    hf_inference_bill_to: str | None = None
    openrouter_mode: str | None = None
    openrouter_token: str | None = None
    openrouter_credential_revision: uuid.UUID | None = None


@dataclass(frozen=True)
class ReplayAssistant:
    content: str
    followups: list[str]
    finish_reason: str = "success"


@dataclass(frozen=True)
class TurnAdmission:
    session_id: uuid.UUID
    turn_id: uuid.UUID
    user_message_id: uuid.UUID
    selected_model: str
    model_route: str
    sdk_session_id: uuid.UUID | None
    sdk_project_key: str | None
    agent_harness: str = "claude"
    is_first_turn: bool = False
    replay_assistant: ReplayAssistant | None = None
    resume_boundary_id: uuid.UUID | None = None
    agent_resume_boundary_id: str | None = None
    is_replacement: bool = False
    replacement_target_id: uuid.UUID | None = None
    replacement_target_sequence: int | None = None
    replacement_target_revision: int | None = None
    replacement_active_suffix_ids: tuple[uuid.UUID, ...] = ()
    prompt_revision: int = 1
    title_should_generate: bool = False
    execution_backend: str = "local_mcp"
    app_release_id: str = ""
    image_version: str = ""
    worker_contract_version: str = ""
    pwc_cli_version: str = ""
    system_prompt_sha256: str = ""
    web_search_enabled: bool = False
    reasoning_effort: str = "high"
    reader_mode: bool = False
    poster_mode: bool = False
    paper_artifacts_enabled: bool = False
    paper_descriptor: dict[str, object] | None = None
    fetchable_urls: tuple[str, ...] = ()
    durable_claim: TurnLeaseClaim | None = None
    external_worker_reservation: ExternalWorkerReservation | None = None
    attach_only: bool = False
    durable_event_sequence: int = 0
    executor_transport: Literal["legacy", "persistent"] = "legacy"
    executor_reservation_revision: int | None = None


@dataclass(frozen=True, slots=True)
class _ReplayOutcome:
    kind: Literal["continue", "admitted", "expired"]
    admission: TurnAdmission | None = None
    expired_message: ChatMessageRecord | None = None


@dataclass(frozen=True, slots=True)
class _CapacitySnapshot:
    other_active: int
    active_total: int


@dataclass(frozen=True, slots=True)
class _ReplacementPlan:
    prior: ChatMessageRecord | None
    active_suffix_ids: tuple[uuid.UUID, ...]
    turn_id: uuid.UUID
    revision: int
    is_first_prompt: bool


@dataclass(frozen=True, slots=True)
class _QuotaCalculation:
    new_projection_bytes: int
    reclaimed_projection_bytes: int
    resulting_session_bytes: int
    resulting_owner_bytes: int
    resulting_message_count: int


@dataclass(frozen=True, slots=True)
class _TranscriptResumeBoundary:
    id: uuid.UUID | None
    agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class _TurnRuntimeDescriptor:
    execution_backend: str
    app_release_id: str
    image_version: str
    worker_contract_version: str
    pwc_cli_version: str
    system_prompt_sha256: str

    def persisted(self, value: str) -> str | None:
        return value if self.execution_backend == "modal_cli" else None


@dataclass(frozen=True, slots=True)
class _TurnCreationPlan:
    message_id: uuid.UUID
    replacement: _ReplacementPlan
    quota: _QuotaCalculation
    resume_boundary: _TranscriptResumeBoundary
    runtime: _TurnRuntimeDescriptor
    model: str
    model_route: str
    effective_prompt: str
    paper_mentions: list[dict]
    primary_paper_context: dict | None
    viewer_context: dict | None
    paper_selection: dict | None
    is_first_turn: bool
    title_should_generate: bool


@dataclass(frozen=True)
class ChatDeletionReceipt:
    session_id: uuid.UUID
    sandbox_id: str | None
    snapshot_id: str | None
    sdk_session_id: uuid.UUID | None
    sdk_project_key: str | None
    artifact_prefixes: tuple[str, ...] = ()


def owner_from_user(
    user: dict,
    *,
    inference_token: str | None = None,
    inference_bill_to: str | None = None,
    openrouter_mode: str | None = None,
    openrouter_token: str | None = None,
    openrouter_credential_revision: uuid.UUID | None = None,
) -> ChatOwner:
    return ChatOwner(
        hf_user_id=user["hf_user_id"],
        hf_username=user["username"],
        hf_inference_token=inference_token,
        hf_inference_bill_to=inference_bill_to,
        openrouter_mode=openrouter_mode,
        openrouter_token=openrouter_token,
        openrouter_credential_revision=openrouter_credential_revision,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _normalized(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


_POSTER_INTENT = re.compile(r"\b(?:poster|posterly)\b", re.IGNORECASE)


def detect_poster_intent(text: str) -> bool:
    """Select artifact budgets only for an explicit current-turn poster request."""
    return bool(_POSTER_INTENT.search(text))


def _payload_bytes(*values: object) -> int:
    return sum(
        len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        for value in values
    )


def _dump_display_blocks(display_blocks: list[dict]) -> list[dict]:
    dumped: list[dict] = []
    for block in DISPLAY_BLOCKS_ADAPTER.validate_python(display_blocks):
        payload = block.model_dump(mode="json", exclude_defaults=True)
        if payload.get("kind") == "app":
            payload = block.model_dump(mode="json")
        dumped.append(payload)
    return dumped


def _message_projection_bytes(message: ChatMessageRecord) -> int:
    if message.role == "user":
        return user_message_projection_bytes(message)
    return len(message.content.encode())


def _reclaimed_projection_bytes(messages: list[ChatMessageRecord]) -> int:
    return sum(
        _message_projection_bytes(message)
        + _payload_bytes(
            message.display_blocks or [],
            message.citations or [],
            message.followups or [],
        )
        for message in messages
    )


def _calculate_turn_quota(
    *,
    session_transcript_bytes: int,
    session_projection_bytes: int,
    owner_total_bytes: int,
    reclaimed_projection_bytes: int,
    new_projection_bytes: int,
    current_message_count: int,
    replacement_prefix_count: int | None,
) -> _QuotaCalculation:
    resulting_message_count = (
        current_message_count + 2
        if replacement_prefix_count is None
        else replacement_prefix_count + 2
    )
    return _QuotaCalculation(
        new_projection_bytes=new_projection_bytes,
        reclaimed_projection_bytes=reclaimed_projection_bytes,
        resulting_session_bytes=(
            session_transcript_bytes
            + session_projection_bytes
            - reclaimed_projection_bytes
            + new_projection_bytes
        ),
        resulting_owner_bytes=(
            owner_total_bytes - reclaimed_projection_bytes + new_projection_bytes
        ),
        resulting_message_count=resulting_message_count,
    )


def _build_replacement_plan(
    *,
    replacement_requested: bool,
    prior: ChatMessageRecord | None,
    active_suffix_ids: tuple[uuid.UUID, ...],
    sdk_session_id: uuid.UUID | None,
    sdk_project_key: str | None,
    agent_harness: str = "claude",
    is_first_prompt: bool | None = None,
) -> _ReplacementPlan:
    if not replacement_requested:
        return _ReplacementPlan(
            prior=None,
            active_suffix_ids=(),
            turn_id=uuid.uuid4(),
            revision=1,
            is_first_prompt=False,
        )
    if prior is None:
        raise ChatServiceError(
            "invalid_replacement", 409, "This prompt can no longer be edited"
        )
    logical_first_prompt = (
        prior.sequence == 1 if is_first_prompt is None else is_first_prompt
    )
    transcript_unavailable = (
        sdk_session_id is None
        or (agent_harness == "pi" and prior.agent_resume_boundary_id is None)
        or (
            agent_harness == "claude"
            and (not sdk_project_key or prior.sdk_resume_boundary_id is None)
        )
    )
    if not logical_first_prompt and transcript_unavailable:
        raise ChatServiceError(
            "chat_transcript_unavailable",
            409,
            "This prompt cannot be edited because its transcript boundary is unavailable",
        )
    return _ReplacementPlan(
        prior=prior,
        active_suffix_ids=active_suffix_ids,
        turn_id=uuid.uuid4(),
        revision=prior.revision + 1,
        is_first_prompt=logical_first_prompt,
    )


class ChatSessionService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.edits = ChatEditService(db)

    @staticmethod
    def _durable_admission_error(error: Exception) -> ChatServiceError:
        if isinstance(error, AccountBusy):
            return ChatServiceError(
                "account_busy", 429, "This account already has an active turn"
            )
        if isinstance(error, ChatOverload):
            return ChatServiceError(
                "chat_overload", 429, "Research chat is temporarily at capacity"
            )
        if isinstance(error, IdempotencyMismatch):
            return ChatServiceError(
                "idempotency_conflict",
                409,
                "This request ID was already used by another turn",
            )
        return ChatServiceError(
            "durable_admission_failed",
            503,
            "Research chat admission could not be persisted",
        )

    @staticmethod
    def _durable_dispatch_route(agent_harness: str) -> str:
        return f"legacy-{agent_harness}"

    @staticmethod
    def _durable_worker_contract(worker_contract_version: str | None) -> str:
        return worker_contract_version or "legacy-local-v1"

    def _owned(
        self, owner: ChatOwner, session_id: uuid.UUID, *, lock: bool = False
    ) -> ChatSession:
        query = select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.hf_user_id == owner.hf_user_id
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        session = self.db.execute(query).scalar_one_or_none()
        if session is None:
            raise ChatServiceError("session_not_found", 404, "Chat session not found")
        return session

    @staticmethod
    def _turn_job_repository() -> ChatTurnJobRepository:
        return ChatTurnJobRepository()

    @staticmethod
    def _durable_control_error() -> ChatServiceError:
        return ChatServiceError(
            "durable_control_conflict",
            503,
            "The durable turn could not be safely reconciled",
        )

    def request_cancel(
        self, owner: ChatOwner, session_id: uuid.UUID
    ) -> CancelTurnRequest | None:
        """Persist an exact cancellation request before the async signal."""
        if not self.settings.chat_durable_turn_dispatch_enabled:
            raise RuntimeError("Durable turn dispatch is disabled")
        session = self._owned(owner, session_id, lock=True)
        if session.active_turn_id is None:
            return None
        turn_id = session.active_turn_id
        repository = self._turn_job_repository()
        job = repository.load_by_turn(self.db, turn_id, lock=True)
        if (
            job is None
            or job.chat_session_id != session.id
            or job.hf_user_id != owner.hf_user_id
        ):
            raise self._durable_control_error()
        if job.state in ("completed", "failed", "interrupted"):
            return None
        try:
            claim = ChatLocalTurnLeaseService(
                self.db, self.settings, repository=repository
            ).request_cancelling(turn_id, now=_now())
        except (StaleTurnClaim, InvalidTurnTransition, TurnNotClaimable):
            return None
        except (TurnJobError, ValueError, SQLAlchemyError) as error:
            raise self._durable_control_error() from error
        if claim is None:
            return None
        return CancelTurnRequest(session.id, turn_id, claim)

    def request_legacy_cancel(
        self, owner: ChatOwner, session_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Fence a legacy turn durably before process-local cancellation."""
        if self.settings.chat_durable_turn_dispatch_enabled:
            raise RuntimeError("Legacy turn cancellation is disabled")
        session = self._owned(owner, session_id, lock=True)
        turn_id = session.active_turn_id
        if turn_id is None:
            return None
        message = self.db.scalar(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.turn_id == turn_id,
                ChatMessageRecord.role == "user",
            )
        )
        if message is not None and message.status in ("generating", PREPARING_STATUS):
            if not self.edits.fail_preparation(session, message, "cancelled"):
                message.status = "interrupted"
                message.error_code = "cancelled"
        session.updated_at = _now()
        return turn_id

    def turn_is_active(
        self, owner: ChatOwner, session_id: uuid.UUID, turn_id: uuid.UUID
    ) -> bool:
        return (
            self.db.scalar(
                select(ChatSession.id)
                .join(
                    ChatMessageRecord,
                    ChatMessageRecord.session_id == ChatSession.id,
                )
                .where(
                    ChatSession.id == session_id,
                    ChatSession.hf_user_id == owner.hf_user_id,
                    ChatSession.active_turn_id == turn_id,
                    ChatMessageRecord.turn_id == turn_id,
                    ChatMessageRecord.role == "user",
                    ChatMessageRecord.status.in_(("generating", PREPARING_STATUS)),
                )
            )
            is not None
        )

    def interrupt_cancel_without_control(
        self, owner: ChatOwner, request: CancelTurnRequest
    ) -> None:
        session = self._owned(owner, request.session_id, lock=True)
        if session.active_turn_id != request.turn_id:
            return
        repository = self._turn_job_repository()
        job = repository.load_by_turn(self.db, request.turn_id, lock=True)
        if (
            job is None
            or job.chat_session_id != session.id
            or job.hf_user_id != owner.hf_user_id
        ):
            raise self._durable_control_error()
        try:
            repository.interrupt_control_missing(
                self.db, claim=request.claim, now=_now()
            )
        except InvalidTurnTransition:
            return
        except (TurnJobError, ValueError, SQLAlchemyError) as error:
            raise self._durable_control_error() from error
        message = self.db.scalar(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.turn_id == request.turn_id,
                ChatMessageRecord.role == "user",
            )
        )
        if message is not None and message.status in ("generating", PREPARING_STATUS):
            if message.status == PREPARING_STATUS:
                self.edits.expire_preparation(session, message)
            else:
                message.status = "interrupted"
                message.error_code = "cancel_control_missing"
        session.active_turn_id = None
        session.active_turn_expires_at = None
        session.updated_at = _now()

    def finalize_cancel(self, owner: ChatOwner, request: CancelTurnRequest) -> None:
        """Persist the canonical cancelled projection for the exact live claim."""
        session = self._owned(owner, request.session_id, lock=True)
        if session.active_turn_id != request.turn_id:
            return
        repository = self._turn_job_repository()
        job = repository.load_by_turn(self.db, request.turn_id, lock=True)
        if (
            job is None
            or job.chat_session_id != session.id
            or job.hf_user_id != owner.hf_user_id
        ):
            raise self._durable_control_error()
        try:
            repository.write_terminal(
                self.db,
                claim=request.claim,
                state="interrupted",
                failure_code="cancelled",
                now=_now(),
            )
        except InvalidTurnTransition:
            return
        except (TurnJobError, ValueError, SQLAlchemyError) as error:
            raise self._durable_control_error() from error
        message = self.db.scalar(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.turn_id == request.turn_id,
                ChatMessageRecord.role == "user",
            )
        )
        if message is not None and message.status in ("generating", PREPARING_STATUS):
            if message.status == PREPARING_STATUS:
                self.edits.expire_preparation(session, message)
            else:
                message.status = "interrupted"
                message.error_code = "cancelled"
        session.active_turn_id = None
        session.active_turn_expires_at = None
        session.updated_at = _now()

    def _reconcile_durable_expiry(
        self, session: ChatSession, turn_id: uuid.UUID, now: datetime
    ) -> None:
        if not self.settings.chat_durable_turn_dispatch_enabled:
            return
        repository = self._turn_job_repository()
        job = repository.load_by_turn(self.db, turn_id, lock=True)
        if (
            job is None
            or job.chat_session_id != session.id
            or job.hf_user_id != session.hf_user_id
        ):
            raise self._durable_control_error()
        if job.state in CLAIMED_STATES and not repository.is_expired_claim(
            job, now=now
        ):
            raise self._durable_admission_error(AccountBusy("The worker lease is live"))
        try:
            ChatLocalTurnLeaseService(
                self.db, self.settings, repository=repository
            ).interrupt_expired(turn_id, now=now)
        except (TurnJobError, ValueError, SQLAlchemyError) as error:
            raise self._durable_control_error() from error

    def existing_effective_prompt(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID | None,
        client_message_id: str,
    ) -> str | None:
        """Return an already-admitted turn input without preparing it again."""
        if session_id is None:
            return None
        return self.db.scalar(
            select(ChatMessageRecord.effective_prompt)
            .join(ChatSession, ChatSession.id == ChatMessageRecord.session_id)
            .where(
                ChatMessageRecord.session_id == session_id,
                ChatMessageRecord.client_message_id == client_message_id,
                ChatSession.hf_user_id == owner.hf_user_id,
            )
        )

    def fetchable_url_seed(
        self,
        session_id: uuid.UUID,
        *,
        current_message_id: uuid.UUID | None = None,
        replacement_target_sequence: int | None = None,
    ) -> list[str]:
        """Derive URL authorization only from the active application lineage."""

        active_status = ChatMessageRecord.status.notin_(INACTIVE_STATUSES)
        if current_message_id is not None:
            active_status = or_(
                active_status, ChatMessageRecord.id == current_message_id
            )
        query = select(ChatMessageRecord).where(
            ChatMessageRecord.session_id == session_id, active_status
        )
        if replacement_target_sequence is not None:
            boundary = ChatMessageRecord.sequence < replacement_target_sequence
            if current_message_id is not None:
                query = query.where(
                    or_(boundary, ChatMessageRecord.id == current_message_id)
                )
            else:
                query = query.where(boundary)
        rows = self.db.execute(query.order_by(ChatMessageRecord.sequence)).scalars()
        payloads: list[str] = []
        for row in rows:
            if row.status in INACTIVE_STATUSES and row.id != current_message_id:
                continue
            if (
                replacement_target_sequence is not None
                and row.sequence >= replacement_target_sequence
                and row.id != current_message_id
            ):
                continue
            if row.role == "user":
                payloads.append(row.effective_prompt or row.content)
                continue
            if row.role != "assistant":
                continue
            for block in row.display_blocks or []:
                if not isinstance(block, dict) or block.get("kind") != "tool":
                    continue
                if block.get("status") not in {"done", "success"}:
                    continue
                name = block.get("name")
                if name in {"Bash", "Read", "Grep"}:
                    for item in block.get("content") or []:
                        if isinstance(item, dict) and isinstance(item.get("text"), str):
                            payloads.append(item["text"])
                elif name == "search_papers":
                    # The validated legacy catalog projection is an explicitly
                    # approved source. WebFetch/search_web blocks are excluded.
                    payloads.append(
                        json.dumps(
                            block.get("results") or [],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
        return bounded_url_seed(payloads)

    def citation_history(
        self,
        session_id: uuid.UUID,
        *,
        before_sequence: int | None = None,
        maximum: int = 100,
    ) -> list[dict]:
        """Return bounded, canonical citation evidence from the active lineage."""
        query = (
            select(ChatMessageRecord.citations)
            .where(
                ChatMessageRecord.session_id == session_id,
                ChatMessageRecord.role == "assistant",
                ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
            )
            .order_by(ChatMessageRecord.sequence.desc())
        )
        if before_sequence is not None:
            query = query.where(ChatMessageRecord.sequence < before_sequence)
        history: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for citations in self.db.scalars(query):
            for value in citations or []:
                snapshot = CitationSnapshot.model_validate(value).model_dump(
                    mode="json"
                )
                identity = (
                    snapshot["kind"],
                    str(snapshot.get("route_id") or snapshot.get("url") or ""),
                )
                if not identity[1] or identity in seen:
                    continue
                seen.add(identity)
                history.append(snapshot)
                if len(history) >= maximum:
                    return history
        return history

    def record_langfuse_trace_id(
        self, owner: ChatOwner, admission: TurnAdmission, trace_id: str
    ) -> None:
        if not trace_id:
            return
        session = self._owned(owner, admission.session_id, lock=True)
        message = self.db.get(ChatMessageRecord, admission.user_message_id)
        if (
            message
            and message.session_id == session.id
            and message.turn_id == admission.turn_id
        ):
            message.langfuse_trace_id = trace_id

    def _validate_model(self, model: str | None) -> tuple[str, str]:
        selected = registry.canonical_model_id(
            self.settings, model or self.settings.chat_model_choices[0]["id"]
        )
        route = self.settings.chat_model_routes.get(selected)
        if route is None:
            raise ChatServiceError(
                "invalid_chat_model", 422, "Unsupported research model"
            )
        return selected, route

    @staticmethod
    def _validate_reasoning_effort(effort: str) -> str:
        if effort not in {"low", "medium", "high", "max"}:
            raise ChatServiceError(
                "invalid_reasoning_effort", 422, "Unsupported reasoning effort"
            )
        return effort

    def create_session(
        self,
        owner: ChatOwner,
        selected_model: str | None = None,
        reasoning_effort: str = "medium",
        *,
        primary_paper_id: int | None = None,
        agent_harness_override: Literal["claude", "pi"] | None = None,
        operator_subject: str | None = None,
    ) -> ChatSession:
        model, _ = self._validate_model(selected_model)
        effort = self._validate_reasoning_effort(reasoning_effort)
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtextextended(owner.hf_user_id, 0))
            )
        )
        count = (
            self.db.scalar(
                select(func.count())
                .select_from(ChatSession)
                .where(
                    ChatSession.hf_user_id == owner.hf_user_id,
                    ChatSession.archived_at.is_(None),
                )
            )
            or 0
        )
        if count >= self.settings.chat_session_limit:
            raise ChatServiceError(
                "chat_session_quota_exceeded",
                409,
                f"You can have at most {self.settings.chat_session_limit} chats. "
                "Archive old chats or delete a chat to create another.",
            )
        session_id = uuid.uuid4()
        if agent_harness_override is not None:
            agent_harness = agent_harness_override
            assignment_source = "admin_override"
        elif self.settings.chat_new_session_pi_percentage == 100:
            agent_harness = "pi"
            assignment_source = "cutover"
        else:
            agent_harness = self.settings.chat_default_agent_harness
            assignment_source = "default"
        allocation_bucket = (
            int.from_bytes(hashlib.sha256(session_id.bytes).digest()[:4], "big") % 100
        )
        transport = self.settings.chat_route_providers[
            self.settings.chat_model_routes[model]
        ]
        if agent_harness == "pi" or transport == "openrouter":
            # Trusted cost extraction and per-call reservation live at the
            # private gateway. Funded OpenRouter must never use local_mcp.
            execution_backend = "modal_cli"
        elif self.settings.chat_new_chat_modal_percentage == 0:
            execution_backend = self.settings.chat_default_backend
        else:
            execution_backend = (
                "modal_cli"
                if allocation_bucket < self.settings.chat_new_chat_modal_percentage
                else "local_mcp"
            )
        session = ChatSession(
            id=session_id,
            hf_user_id=owner.hf_user_id,
            hf_username=owner.hf_username,
            title="New chat",
            title_status="pending",
            selected_model=model,
            reasoning_effort=effort,
            primary_paper_id=primary_paper_id,
            execution_backend=execution_backend,
            agent_harness=agent_harness,
            updated_at=_now(),
        )
        self.db.add(session)
        self.db.flush()
        self.db.add(
            ChatHarnessAssignmentAudit(
                chat_session_id=session.id,
                agent_harness=agent_harness,
                assignment_source=assignment_source,
                operator_subject_hash=(
                    hashlib.sha256(operator_subject.encode()).hexdigest()
                    if assignment_source == "admin_override" and operator_subject
                    else None
                ),
                app_release_id=self.settings.release_id,
            )
        )
        return session

    def list_sessions(
        self, owner: ChatOwner, cursor: str | None, limit: int
    ) -> tuple[list[ChatSession], str | None]:
        query = select(ChatSession).where(
            ChatSession.hf_user_id == owner.hf_user_id,
            ChatSession.archived_at.is_(None),
        )
        if cursor:
            try:
                raw = base64.urlsafe_b64decode(
                    cursor + "=" * (-len(cursor) % 4)
                ).decode()
                timestamp, row_id = raw.rsplit("|", 1)
                before = datetime.fromisoformat(timestamp)
                cursor_id = uuid.UUID(row_id)
            except (ValueError, UnicodeDecodeError):
                raise ChatServiceError(
                    "invalid_cursor", 422, "Invalid session cursor"
                ) from None
            query = query.where(
                or_(
                    ChatSession.updated_at < before,
                    (ChatSession.updated_at == before) & (ChatSession.id < cursor_id),
                )
            )
        rows = list(
            self.db.execute(
                query.order_by(
                    ChatSession.updated_at.desc(), ChatSession.id.desc()
                ).limit(limit + 1)
            ).scalars()
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            token = f"{rows[-1].updated_at.isoformat()}|{rows[-1].id}".encode()
            next_cursor = base64.urlsafe_b64encode(token).decode().rstrip("=")
        return rows, next_cursor

    def archive_old_sessions(self, owner: ChatOwner, *, days: int = 30) -> int:
        """Hide inactive old chats from history and the active-session quota."""
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtextextended(owner.hf_user_id, 0))
            )
        )
        now = _now()
        rows = list(
            self.db.execute(
                select(ChatSession)
                .where(
                    ChatSession.hf_user_id == owner.hf_user_id,
                    ChatSession.archived_at.is_(None),
                    ChatSession.updated_at < now - timedelta(days=days),
                    or_(
                        ChatSession.active_turn_id.is_(None),
                        ChatSession.active_turn_expires_at.is_(None),
                        ChatSession.active_turn_expires_at <= now,
                    ),
                )
                .with_for_update()
            ).scalars()
        )
        for session in rows:
            session.archived_at = now
        self.db.flush()
        return len(rows)

    def archive_oldest_sessions(self, owner: ChatOwner, *, limit: int = 50) -> int:
        """Hide up to ``limit`` least-recently-updated inactive chats."""
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtextextended(owner.hf_user_id, 0))
            )
        )
        now = _now()
        rows = list(
            self.db.execute(
                select(ChatSession)
                .where(
                    ChatSession.hf_user_id == owner.hf_user_id,
                    ChatSession.archived_at.is_(None),
                    or_(
                        ChatSession.active_turn_id.is_(None),
                        ChatSession.active_turn_expires_at.is_(None),
                        ChatSession.active_turn_expires_at <= now,
                    ),
                )
                .order_by(ChatSession.updated_at.asc(), ChatSession.id.asc())
                .limit(limit)
                .with_for_update()
            ).scalars()
        )
        for session in rows:
            session.archived_at = now
        self.db.flush()
        return len(rows)

    def get_session(
        self, owner: ChatOwner, session_id: uuid.UUID
    ) -> tuple[ChatSession, list[ChatMessageRecord]]:
        session = self._owned(owner, session_id)
        messages = list(
            self.db.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
                )
                .order_by(ChatMessageRecord.sequence)
            ).scalars()
        )
        return session, messages

    def rename_session(
        self, owner: ChatOwner, session_id: uuid.UUID, title: str
    ) -> ChatSession:
        session = self._owned(owner, session_id, lock=True)
        normalized = _normalized(title, 80)
        if not normalized:
            raise ChatServiceError("invalid_title", 422, "Title must not be empty")
        session.title = normalized
        session.title_source = "user"
        session.title_status = "complete"
        session.title_generation_id = None
        session.hf_username = owner.hf_username
        session.updated_at = _now()
        self.db.flush()
        return session

    def select_model(
        self, owner: ChatOwner, session_id: uuid.UUID, model: str
    ) -> ChatSession:
        selected, _ = self._validate_model(model)
        session = self._owned(owner, session_id, lock=True)
        if (
            session.active_turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > _now()
        ):
            raise ChatServiceError(
                "session_busy", 409, "This chat is generating a response"
            )
        session.selected_model = selected
        if (
            self.settings.chat_route_providers[
                self.settings.chat_model_routes[selected]
            ]
            == "openrouter"
        ):
            if session.execution_backend != "modal_cli":
                raise ChatServiceError(
                    "openrouter_gateway_required",
                    409,
                    "Start a new chat to use this OpenRouter model securely.",
                )
        session.hf_username = owner.hf_username
        session.updated_at = _now()
        self.db.flush()
        return session

    def select_reasoning_effort(
        self, owner: ChatOwner, session_id: uuid.UUID, reasoning_effort: str
    ) -> ChatSession:
        effort = self._validate_reasoning_effort(reasoning_effort)
        session = self._owned(owner, session_id, lock=True)
        if (
            session.active_turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > _now()
        ):
            raise ChatServiceError(
                "session_busy", 409, "This chat is generating a response"
            )
        session.reasoning_effort = effort
        session.hf_username = owner.hf_username
        session.updated_at = _now()
        self.db.flush()
        return session

    def _resolve_replay(
        self,
        session: ChatSession | None,
        *,
        client_message_id: str,
        web_search_enabled: bool,
        reasoning_effort: str,
        now: datetime,
    ) -> _ReplayOutcome:
        if session is None:
            return _ReplayOutcome(kind="continue")
        existing = self.db.execute(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.client_message_id == client_message_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            return _ReplayOutcome(kind="continue")
        mode = resolve_turn_mode(
            self.settings,
            primary_paper_id=getattr(session, "primary_paper_id", None),
            poster_intent=detect_poster_intent(getattr(existing, "content", "")),
        )
        executor_reservation = (
            self.db.scalar(
                select(ChatTurnReservation).where(
                    ChatTurnReservation.turn_id == existing.turn_id
                )
            )
            if self.settings.chat_executor_remote_transport_enabled
            else None
        )

        existing_web_search_enabled = getattr(existing, "web_search_enabled", False)
        if existing_web_search_enabled != web_search_enabled:
            raise ChatServiceError(
                "idempotency_conflict",
                409,
                "This request ID was already used with different Search permission",
            )
        existing_reasoning_effort = getattr(existing, "reasoning_effort", "high")
        if existing_reasoning_effort != reasoning_effort:
            raise ChatServiceError(
                "idempotency_conflict",
                409,
                "This request ID was already used with different reasoning effort",
            )
        if (
            self.settings.chat_durable_turn_dispatch_enabled
            and existing.status in ("generating", PREPARING_STATUS)
            and session.active_turn_id == existing.turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > now
        ):
            return _ReplayOutcome(
                kind="admitted",
                admission=TurnAdmission(
                    session_id=session.id,
                    turn_id=existing.turn_id,
                    user_message_id=existing.id,
                    selected_model=existing.model or session.selected_model,
                    model_route=(
                        existing.model_route
                        or self._validate_model(session.selected_model)[1]
                    ),
                    sdk_session_id=session.sdk_session_id,
                    sdk_project_key=session.sdk_project_key,
                    agent_harness=getattr(session, "agent_harness", "claude"),
                    is_first_turn=existing.sequence == 1,
                    prompt_revision=existing.revision,
                    execution_backend=session.execution_backend,
                    app_release_id=(
                        getattr(existing, "app_release_id", None)
                        or self.settings.release_id
                    ),
                    worker_contract_version=self._durable_worker_contract(
                        getattr(existing, "worker_contract_version", None)
                    ),
                    web_search_enabled=existing_web_search_enabled,
                    reasoning_effort=existing_reasoning_effort,
                    reader_mode=mode.reader_mode,
                    poster_mode=mode.poster_mode,
                    attach_only=True,
                    executor_transport=(
                        executor_reservation.transport
                        if executor_reservation is not None
                        else "legacy"
                    ),
                    executor_reservation_revision=(
                        executor_reservation.revision
                        if executor_reservation is not None
                        else None
                    ),
                ),
            )
        assistant = self.db.execute(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.turn_id == existing.turn_id,
                ChatMessageRecord.role == "assistant",
            )
        ).scalar_one_or_none()
        if assistant:
            return _ReplayOutcome(
                kind="admitted",
                admission=TurnAdmission(
                    session_id=session.id,
                    turn_id=existing.turn_id,
                    user_message_id=existing.id,
                    selected_model=existing.model or session.selected_model,
                    model_route=(
                        existing.model_route
                        or self._validate_model(session.selected_model)[1]
                    ),
                    sdk_session_id=session.sdk_session_id,
                    sdk_project_key=session.sdk_project_key,
                    agent_harness=getattr(session, "agent_harness", "claude"),
                    is_first_turn=existing.sequence == 1,
                    replay_assistant=ReplayAssistant(
                        content=assistant.content,
                        followups=list(assistant.followups or []),
                        finish_reason=(
                            getattr(assistant, "finish_reason", None) or "success"
                        ),
                    ),
                    prompt_revision=existing.revision,
                    execution_backend=session.execution_backend,
                    app_release_id=(
                        getattr(existing, "app_release_id", None)
                        or self.settings.release_id
                    ),
                    worker_contract_version=self._durable_worker_contract(
                        getattr(existing, "worker_contract_version", None)
                    ),
                    web_search_enabled=existing_web_search_enabled,
                    reasoning_effort=existing_reasoning_effort,
                    reader_mode=mode.reader_mode,
                    poster_mode=mode.poster_mode,
                    attach_only=self.settings.chat_durable_turn_dispatch_enabled,
                    executor_transport=(
                        executor_reservation.transport
                        if executor_reservation is not None
                        else "legacy"
                    ),
                    executor_reservation_revision=(
                        executor_reservation.revision
                        if executor_reservation is not None
                        else None
                    ),
                ),
            )
        if (
            existing.status in ("generating", PREPARING_STATUS)
            and session.active_turn_expires_at
            and session.active_turn_expires_at <= now
        ):
            return _ReplayOutcome(
                kind="expired",
                expired_message=existing,
            )
        if existing.status in ("interrupted", "error", "superseded"):
            raise ChatServiceError(
                "turn_requires_retry",
                409,
                "Retry or edit this prompt with a new request ID",
            )
        raise ChatServiceError(
            "turn_in_progress", 409, "This turn is already in progress"
        )

    def _apply_expired_replay(
        self, session: ChatSession, existing: ChatMessageRecord
    ) -> None:
        self._reconcile_durable_expiry(session, existing.turn_id, _now())
        if existing.status == PREPARING_STATUS:
            self.edits.expire_preparation(session, existing)
        else:
            existing.status = "interrupted"
            existing.error_code = "lease_expired"
        if session.active_turn_id == existing.turn_id:
            session.active_turn_id = None
            session.active_turn_expires_at = None

    def _lock_admission_keys(self, owner: ChatOwner) -> None:
        """Lock the user admission key before the global capacity key."""
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"chat-user:{owner.hf_user_id}", 0)
                )
            )
        )
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended("chat-global-active-turns", 0)
                )
            )
        )

    def _load_capacity_snapshot(
        self, owner: ChatOwner, session: ChatSession | None
    ) -> _CapacitySnapshot:
        other_active = self.db.scalar(
            select(func.count())
            .select_from(ChatSession)
            .where(
                ChatSession.hf_user_id == owner.hf_user_id,
                *((ChatSession.id != session.id,) if session is not None else ()),
                ChatSession.active_turn_id.is_not(None),
                ChatSession.active_turn_expires_at > func.now(),
            )
        )
        active_total = (
            self.db.scalar(
                select(func.count())
                .select_from(ChatSession)
                .where(
                    ChatSession.active_turn_id.is_not(None),
                    ChatSession.active_turn_expires_at > func.now(),
                )
            )
            or 0
        )
        return _CapacitySnapshot(
            other_active=other_active,
            active_total=active_total,
        )

    def _validate_capacity(self, capacity: _CapacitySnapshot) -> None:
        if capacity.other_active >= self.settings.chat_user_max_concurrency:
            raise ChatServiceError(
                "chat_capacity",
                429,
                "This account already has the maximum active research responses",
                active_count=capacity.active_total,
            )
        if capacity.active_total >= self.settings.chat_max_concurrency:
            raise ChatServiceError(
                "chat_capacity",
                429,
                "Research capacity is currently occupied",
                active_count=capacity.active_total,
            )

    def _load_expired_active_message(
        self, session: ChatSession, now: datetime
    ) -> ChatMessageRecord | None:
        if (
            session.active_turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > now
        ):
            raise ChatServiceError(
                "session_busy", 409, "This chat is generating a response"
            )
        if not session.active_turn_id:
            return None
        return self.db.execute(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.turn_id == session.active_turn_id,
                ChatMessageRecord.role == "user",
                ChatMessageRecord.status.in_(["generating", PREPARING_STATUS]),
            )
        ).scalar_one_or_none()

    def _apply_expired_active_turn(
        self, session: ChatSession, stale: ChatMessageRecord | None
    ) -> bool:
        if not session.active_turn_id:
            return False
        self._reconcile_durable_expiry(session, session.active_turn_id, _now())
        if stale:
            if stale.status == PREPARING_STATUS:
                self.edits.expire_preparation(session, stale)
            else:
                stale.status = "interrupted"
                stale.error_code = "lease_expired"
        session.active_turn_id = None
        session.active_turn_expires_at = None
        return True

    def _latest_user_message(self, session: ChatSession) -> ChatMessageRecord | None:
        return self.db.execute(
            select(ChatMessageRecord)
            .where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.role == "user",
                ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
            )
            .order_by(ChatMessageRecord.sequence.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _has_unresolved_turn(self, session: ChatSession) -> bool:
        # A continuation preserves earlier failures as history. Only the latest
        # user turn can require recovery; completed continuations unblock chat.
        latest = self._latest_user_message(session)
        return latest is not None and latest.status in {"interrupted", "error"}

    def _validate_saved_progress_retry(
        self, session: ChatSession, message_id: uuid.UUID
    ) -> ChatMessageRecord:
        latest = self._latest_user_message(session)
        if (
            latest is None
            or latest.id != message_id
            or latest.status not in {"error", "interrupted"}
            or session.agent_harness != "pi"
            or not session.sdk_session_id
        ):
            raise ChatServiceError(
                "invalid_retry", 409, "Only the latest failed turn can be continued"
            )
        leaf = self.db.scalar(
            select(ChatPiSession.current_leaf_id).where(
                ChatPiSession.chat_session_id == session.id,
                ChatPiSession.agent_session_id == session.sdk_session_id,
            )
        )
        if not leaf:
            raise ChatServiceError(
                "retry_history_unavailable",
                409,
                "Saved research is unavailable; edit the request or start a new conversation",
            )
        return latest

    def _load_owner_storage_bytes(self, owner: ChatOwner) -> int:
        return (
            self.db.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            ChatSession.transcript_bytes + ChatSession.projection_bytes
                        ),
                        0,
                    )
                ).where(ChatSession.hf_user_id == owner.hf_user_id)
            )
            or 0
        )

    def _load_replacement_plan(
        self,
        session: ChatSession,
        *,
        replace_message_id: uuid.UUID | None,
        prior_revision: int | None,
    ) -> _ReplacementPlan:
        if replace_message_id is None:
            return _build_replacement_plan(
                replacement_requested=False,
                prior=None,
                active_suffix_ids=(),
                sdk_session_id=session.sdk_session_id,
                sdk_project_key=session.sdk_project_key,
                agent_harness=getattr(session, "agent_harness", "claude"),
            )
        prior = self.db.execute(
            select(ChatMessageRecord).where(
                ChatMessageRecord.id == replace_message_id,
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.role == "user",
                ChatMessageRecord.revision == prior_revision,
                ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
            )
        ).scalar_one_or_none()
        if prior is None:
            return _build_replacement_plan(
                replacement_requested=True,
                prior=None,
                active_suffix_ids=(),
                sdk_session_id=session.sdk_session_id,
                sdk_project_key=session.sdk_project_key,
                agent_harness=getattr(session, "agent_harness", "claude"),
            )
        active_suffix_ids = tuple(
            self.db.execute(
                select(ChatMessageRecord.id)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.sequence >= prior.sequence,
                    ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
                )
                .order_by(ChatMessageRecord.sequence)
            ).scalars()
        )
        return _build_replacement_plan(
            replacement_requested=True,
            prior=prior,
            active_suffix_ids=active_suffix_ids,
            sdk_session_id=session.sdk_session_id,
            sdk_project_key=session.sdk_project_key,
            agent_harness=getattr(session, "agent_harness", "claude"),
            is_first_prompt=(
                prior.sequence == 1 or len(active_suffix_ids) == session.message_count
            ),
        )

    def _load_reclaimed_projection_bytes(self, replacement: _ReplacementPlan) -> int:
        if not replacement.active_suffix_ids or not isinstance(self.db, Session):
            return 0
        suffix_rows = list(
            self.db.execute(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.id.in_(replacement.active_suffix_ids)
                )
            ).scalars()
        )
        return _reclaimed_projection_bytes(suffix_rows)

    def _load_replacement_prefix_count(
        self, session: ChatSession, replacement: _ReplacementPlan
    ) -> int | None:
        if replacement.prior is None:
            return None
        return (
            self.db.scalar(
                select(func.count())
                .select_from(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.sequence < replacement.prior.sequence,
                    ChatMessageRecord.status.notin_(INACTIVE_STATUSES),
                )
            )
            or 0
        )

    def _validate_turn_storage_quota(self, quota: _QuotaCalculation) -> None:
        if (
            quota.resulting_session_bytes > self.settings.chat_session_byte_limit
            or quota.resulting_owner_bytes > self.settings.chat_user_byte_limit
        ):
            raise ChatServiceError(
                "chat_storage_quota_exceeded", 409, "Chat storage quota exceeded"
            )

    def _validate_turn_message_quota(self, quota: _QuotaCalculation) -> None:
        if quota.resulting_message_count > self.settings.chat_session_message_limit:
            raise ChatServiceError(
                "chat_message_quota_exceeded",
                409,
                "This chat has reached its message limit; start a new chat",
            )

    def _resolve_transcript_resume_boundary(
        self, session: ChatSession, replacement: _ReplacementPlan
    ) -> _TranscriptResumeBoundary:
        if replacement.prior is not None:
            agent_boundary = getattr(
                replacement.prior,
                "agent_resume_boundary_id",
                (
                    str(replacement.prior.sdk_resume_boundary_id)
                    if replacement.prior.sdk_resume_boundary_id
                    else None
                ),
            )
            return _TranscriptResumeBoundary(
                id=replacement.prior.sdk_resume_boundary_id,
                agent_id=agent_boundary,
            )
        if getattr(session, "agent_harness", "claude") == "pi":
            leaf = self.db.scalar(
                select(ChatPiSession.current_leaf_id).where(
                    ChatPiSession.chat_session_id == session.id,
                    ChatPiSession.agent_session_id == session.sdk_session_id,
                )
            )
            return _TranscriptResumeBoundary(id=None, agent_id=leaf)
        resume_boundary: uuid.UUID | None = None
        if session.sdk_session_id and session.sdk_project_key:
            boundary = self.db.scalar(
                select(ChatSDKTranscriptEntry.entry_uuid)
                .where(
                    ChatSDKTranscriptEntry.project_key == session.sdk_project_key,
                    ChatSDKTranscriptEntry.sdk_session_id == session.sdk_session_id,
                    ChatSDKTranscriptEntry.subpath == "",
                    ChatSDKTranscriptEntry.entry_uuid.is_not(None),
                    ChatSDKTranscriptEntry.entry["type"].astext.in_(
                        ["user", "assistant"]
                    ),
                )
                .order_by(ChatSDKTranscriptEntry.id.desc())
                .limit(1)
            )
            with contextlib.suppress(ValueError):
                resume_boundary = uuid.UUID(boundary) if boundary else None
        return _TranscriptResumeBoundary(
            id=resume_boundary,
            agent_id=str(resume_boundary) if resume_boundary else None,
        )

    def _turn_runtime_descriptor(self, session: ChatSession) -> _TurnRuntimeDescriptor:
        return _TurnRuntimeDescriptor(
            execution_backend=session.execution_backend,
            app_release_id=self.settings.release_id,
            image_version=self.settings.chat_modal_image_version,
            worker_contract_version=self.settings.chat_worker_contract_version,
            pwc_cli_version=self.settings.chat_pwc_cli_version,
            system_prompt_sha256=self.settings.chat_system_prompt_sha256,
        )

    def _build_turn_creation_plan(
        self,
        session: ChatSession,
        *,
        replacement: _ReplacementPlan,
        quota: _QuotaCalculation,
        resume_boundary: _TranscriptResumeBoundary,
        model: str,
        model_route: str,
        effective_prompt: str,
        paper_mentions: list[dict],
        primary_paper_context: dict | None = None,
        viewer_context: dict | None = None,
        paper_selection: dict | None = None,
    ) -> _TurnCreationPlan:
        is_first_turn = (
            replacement.is_first_prompt
            if replacement.prior is not None
            else session.message_count == 0
        )
        return _TurnCreationPlan(
            message_id=uuid.uuid4(),
            replacement=replacement,
            quota=quota,
            resume_boundary=resume_boundary,
            runtime=self._turn_runtime_descriptor(session),
            model=model,
            model_route=model_route,
            effective_prompt=effective_prompt,
            paper_mentions=paper_mentions,
            primary_paper_context=primary_paper_context,
            viewer_context=viewer_context,
            paper_selection=paper_selection,
            is_first_turn=is_first_turn,
            title_should_generate=(is_first_turn and session.title_source != "user"),
        )

    def _apply_turn_creation(
        self,
        session: ChatSession,
        owner: ChatOwner,
        plan: _TurnCreationPlan,
        *,
        client_message_id: str,
        text: str,
        web_search_enabled: bool,
        reasoning_effort: str,
        update_web_search_preference: bool,
        mode: TurnMode,
        now: datetime,
    ) -> ChatMessageRecord:
        prior = plan.replacement.prior
        session.last_sequence += 1
        if prior is None:
            session.message_count += 1
        session.active_turn_id = plan.replacement.turn_id
        session.active_turn_expires_at = now + timedelta(seconds=mode.lease_seconds)
        session.hf_username = owner.hf_username
        if update_web_search_preference:
            session.web_search_enabled = web_search_enabled
        session.reasoning_effort = reasoning_effort
        session.updated_at = now
        session.projection_bytes += plan.quota.new_projection_bytes
        message = ChatMessageRecord(
            id=plan.message_id,
            session_id=session.id,
            turn_id=plan.replacement.turn_id,
            sequence=session.last_sequence,
            role="user",
            content=text,
            paper_mentions=plan.paper_mentions,
            primary_paper_context=plan.primary_paper_context,
            viewer_context=plan.viewer_context,
            paper_selection=plan.paper_selection,
            effective_prompt=plan.effective_prompt,
            client_message_id=client_message_id,
            web_search_enabled=web_search_enabled,
            reasoning_effort=reasoning_effort,
            revision=plan.replacement.revision,
            supersedes_message_id=prior.id if prior else None,
            sdk_resume_boundary_id=plan.resume_boundary.id,
            agent_resume_boundary_id=plan.resume_boundary.agent_id,
            agent_harness=getattr(session, "agent_harness", "claude"),
            status=PREPARING_STATUS if prior is not None else "generating",
            model=plan.model,
            model_route=plan.model_route,
            app_release_id=plan.runtime.app_release_id,
            sandbox_image_version=plan.runtime.persisted(plan.runtime.image_version),
            worker_contract_version=plan.runtime.persisted(
                plan.runtime.worker_contract_version
            ),
            pwc_cli_version=plan.runtime.persisted(plan.runtime.pwc_cli_version),
            system_prompt_sha256=plan.runtime.persisted(
                plan.runtime.system_prompt_sha256
            ),
            last_attempted_at=now,
        )
        self.db.add(message)
        self.db.flush()
        return message

    def _turn_admission(
        self,
        session: ChatSession,
        plan: _TurnCreationPlan,
        fetchable_urls: tuple[str, ...],
        *,
        external_worker_reservation: ExternalWorkerReservation | None,
        web_search_enabled: bool,
        reasoning_effort: str,
        mode: TurnMode,
        executor_transport: Literal["legacy", "persistent"] = "legacy",
        executor_reservation_revision: int | None = None,
    ) -> TurnAdmission:
        prior = plan.replacement.prior
        paper_descriptor: dict[str, object] | None = None
        if mode.paper_artifacts_enabled:
            artifact = self.db.scalar(
                select(ChatArtifact).where(
                    ChatArtifact.session_id == session.id,
                    ChatArtifact.kind == "latex_paper",
                )
            )
            if artifact is not None:
                paper_descriptor = {
                    "artifact_id": str(artifact.id),
                    "title": artifact.title,
                    "source_head_version_id": (
                        str(artifact.source_head_version_id)
                        if artifact.source_head_version_id
                        else None
                    ),
                    "preview_head_version_id": (
                        str(artifact.preview_head_version_id)
                        if artifact.preview_head_version_id
                        else None
                    ),
                }
        return TurnAdmission(
            session_id=session.id,
            turn_id=plan.replacement.turn_id,
            user_message_id=plan.message_id,
            selected_model=plan.model,
            model_route=plan.model_route,
            sdk_session_id=session.sdk_session_id,
            sdk_project_key=session.sdk_project_key,
            agent_harness=getattr(session, "agent_harness", "claude"),
            is_first_turn=plan.is_first_turn,
            resume_boundary_id=plan.resume_boundary.id,
            agent_resume_boundary_id=plan.resume_boundary.agent_id,
            is_replacement=prior is not None,
            replacement_target_id=prior.id if prior else None,
            replacement_target_sequence=prior.sequence if prior else None,
            replacement_target_revision=prior.revision if prior else None,
            replacement_active_suffix_ids=plan.replacement.active_suffix_ids,
            prompt_revision=plan.replacement.revision,
            title_should_generate=plan.title_should_generate,
            execution_backend=plan.runtime.execution_backend,
            app_release_id=plan.runtime.app_release_id,
            image_version=plan.runtime.image_version,
            worker_contract_version=plan.runtime.worker_contract_version,
            pwc_cli_version=plan.runtime.pwc_cli_version,
            system_prompt_sha256=plan.runtime.system_prompt_sha256,
            web_search_enabled=web_search_enabled,
            reasoning_effort=reasoning_effort,
            reader_mode=mode.reader_mode,
            poster_mode=mode.poster_mode,
            paper_artifacts_enabled=mode.paper_artifacts_enabled,
            paper_descriptor=paper_descriptor,
            executor_transport=executor_transport,
            executor_reservation_revision=executor_reservation_revision,
            fetchable_urls=fetchable_urls,
            external_worker_reservation=external_worker_reservation,
        )

    def begin_turn(
        self,
        owner: ChatOwner,
        *,
        session_id: uuid.UUID | None,
        client_message_id: str,
        text: str,
        effective_prompt: str | None = None,
        paper_mentions: list[dict] | None = None,
        primary_paper_id: int | None = None,
        primary_paper_context: dict | None = None,
        viewer_context: dict | None = None,
        paper_selection: dict | None = None,
        initial_model: str | None = None,
        replace_message_id: uuid.UUID | None = None,
        prior_revision: int | None = None,
        retry_message_id: uuid.UUID | None = None,
        web_search_enabled: bool = False,
        reasoning_effort: str | None = None,
        update_web_search_preference: bool = True,
        qualification: QualificationContext | None = None,
    ) -> TurnAdmission:
        if retry_message_id is not None and (
            session_id is None or replace_message_id is not None
        ):
            raise ChatServiceError(
                "invalid_retry",
                409,
                "Retry requires an existing session without replacement",
            )
        durable_coordinator: ChatTurnAdmissionCoordinator | None = None
        durable_preflight: DurableAdmissionPreflight | None = None
        session: ChatSession | None = None
        recovered_durable_preflight_expiry = False
        if self.settings.chat_durable_turn_dispatch_enabled:
            durable_coordinator = ChatTurnAdmissionCoordinator(self.db, self.settings)
            try:
                durable_preflight = durable_coordinator.preflight(
                    hf_user_id=owner.hf_user_id,
                    request_id=client_message_id,
                    requested_session_id=session_id,
                    qualification=qualification,
                )
                recovered_durable_preflight_expiry = (
                    durable_preflight.reconciled_expired_count > 0
                )
            except AccountBusy as error:
                if session_id is None:
                    raise self._durable_admission_error(error) from error
                session = self._owned(owner, session_id, lock=True)
                now = _now()
                stale = self._load_expired_active_message(session, now)
                if not session.active_turn_id:
                    raise self._durable_admission_error(error) from error
                recovered_durable_preflight_expiry = self._apply_expired_active_turn(
                    session, stale
                )
                try:
                    durable_preflight = durable_coordinator.preflight(
                        hf_user_id=owner.hf_user_id,
                        request_id=client_message_id,
                        requested_session_id=session_id,
                        qualification=qualification,
                    )
                except (TurnJobError, ValueError, SQLAlchemyError) as retry_error:
                    raise self._durable_admission_error(retry_error) from retry_error
                recovered_durable_preflight_expiry = (
                    recovered_durable_preflight_expiry
                    or durable_preflight.reconciled_expired_count > 0
                )
            except (TurnJobError, ValueError, SQLAlchemyError) as error:
                raise self._durable_admission_error(error) from error
            if durable_preflight.existing_job is not None:
                session_id = durable_preflight.existing_job.chat_session_id
        if session is None:
            session = (
                None
                if session_id is None
                else self._owned(owner, session_id, lock=True)
            )
        if (
            qualification is not None
            and session is not None
            and getattr(session, "agent_harness", "claude") != "pi"
        ):
            raise ChatServiceError(
                "qualification_session_harness_mismatch",
                409,
                "Qualification sessions must already use the Pi harness",
            )
        effective_reasoning_effort = self._validate_reasoning_effort(
            reasoning_effort
            or (
                getattr(session, "reasoning_effort", None) or "high"
                if session is not None
                else "low"
            )
        )
        now = _now()
        try:
            replay = self._resolve_replay(
                session,
                client_message_id=client_message_id,
                web_search_enabled=web_search_enabled,
                reasoning_effort=effective_reasoning_effort,
                now=now,
            )
        except ChatServiceError as error:
            if (
                recovered_durable_preflight_expiry
                and error.code == "turn_requires_retry"
            ):
                error.commit_changes = True
            raise
        if replay.kind == "admitted":
            assert replay.admission is not None
            admission = replay.admission
            if durable_coordinator is not None:
                assert durable_preflight is not None
                try:
                    durable_coordinator.validate_replay(
                        durable_preflight,
                        turn_id=admission.turn_id,
                        chat_session_id=admission.session_id,
                        hf_user_id=owner.hf_user_id,
                        revision=admission.prompt_revision,
                        dispatch_route=self._durable_dispatch_route(
                            admission.agent_harness
                        ),
                        app_release_id=admission.app_release_id,
                        worker_contract_version=self._durable_worker_contract(
                            admission.worker_contract_version
                        ),
                        now=now,
                    )
                except (TurnJobError, ValueError, SQLAlchemyError) as error:
                    raise self._durable_admission_error(error) from error
                admission = replace(
                    admission,
                    durable_event_sequence=int(
                        getattr(durable_preflight.existing_job, "event_sequence", 0)
                    ),
                )
            return admission
        if (
            durable_preflight is not None
            and durable_preflight.existing_job is not None
            and replay.kind == "continue"
        ):
            raise ChatServiceError(
                "durable_admission_failed",
                503,
                "The durable turn is missing its chat projection",
            )
        if replay.kind == "expired":
            assert session is not None
            assert replay.expired_message is not None
            self._apply_expired_replay(session, replay.expired_message)
            raise ChatServiceError(
                "turn_requires_retry",
                409,
                "Retry or edit the interrupted prompt with a new request ID",
                commit_changes=True,
            )

        if session is not None and session.transcript_status == "degraded":
            raise ChatServiceError(
                "chat_transcript_degraded",
                409,
                "This chat is awaiting transcript recovery and cannot be resumed",
            )
        session_primary_paper_id = (
            getattr(session, "primary_paper_id", None) if session is not None else None
        )
        if session is not None and primary_paper_id != session_primary_paper_id:
            if primary_paper_id is not None or session_primary_paper_id is not None:
                raise ChatServiceError(
                    "primary_paper_mismatch",
                    409,
                    "This conversation belongs to a different paper.",
                )

        recovered_retry_expiry = False
        if retry_message_id is not None:
            assert session is not None
            stale = self._load_expired_active_message(session, now)
            recovered_retry_expiry = self._apply_expired_active_turn(session, stale)
            retry_target = self._validate_saved_progress_retry(
                session, retry_message_id
            )
            # Keep the original display request as well as its effective context.
            # Mode selection, lease duration, and idempotent replays all use it.
            text = retry_target.content
            effective_prompt = (
                (retry_target.effective_prompt or retry_target.content)
                + "\n\n"
                + (
                    "Continue the last failed request from the saved research and completed tool results. "
                    "Preserve the original request and constraints. Do not repeat completed edits, "
                    "publications, or artifact creation. Verify uncertain action outcomes before proceeding. "
                    "If the saved context cannot be recovered safely, report the failure explicitly."
                )
            )

        mode = resolve_turn_mode(
            self.settings,
            primary_paper_id=(
                session_primary_paper_id if session is not None else primary_paper_id
            ),
            poster_intent=detect_poster_intent(text),
        )
        target_harness = (
            getattr(session, "agent_harness", "claude")
            if session is not None
            else (
                "pi"
                if qualification is not None
                or self.settings.chat_new_session_pi_percentage == 100
                else self.settings.chat_default_agent_harness
            )
        )
        if (
            durable_coordinator is not None
            and durable_preflight is not None
            and (
                self.settings.chat_external_pi_admission_enabled
                or qualification is not None
            )
            and target_harness == "pi"
        ):
            try:
                require_ordinary_research_mode(
                    poster_mode=mode.poster_mode,
                    paper_artifacts_enabled=mode.paper_artifacts_enabled,
                )
            except UnsupportedChatMode as error:
                raise ChatServiceError(
                    error.code,
                    422,
                    "Persistent executor v1 supports ordinary research only",
                ) from error
            try:
                durable_preflight = durable_coordinator.reserve_external_capacity(
                    durable_preflight,
                    now=now,
                    poster_mode=mode.poster_mode,
                    paper_artifacts_enabled=mode.paper_artifacts_enabled,
                )
            except (TurnJobError, ValueError, SQLAlchemyError) as error:
                raise self._durable_admission_error(error) from error
        elif durable_coordinator is not None and durable_preflight is not None:
            try:
                durable_preflight = durable_coordinator.authorize_global_capacity(
                    durable_preflight, now=now
                )
            except (TurnJobError, ValueError, SQLAlchemyError) as error:
                raise self._durable_admission_error(error) from error

        if durable_coordinator is None:
            self._lock_admission_keys(owner)
            capacity = self._load_capacity_snapshot(owner, session)
            self._validate_capacity(capacity)

        created_session = session is None
        # Capacity admission precedes creation so a rejected new-chat request
        # cannot leave behind a session or any message state.
        if session is None:
            session = self.create_session(
                owner,
                initial_model,
                effective_reasoning_effort,
                **(
                    {"primary_paper_id": primary_paper_id}
                    if primary_paper_id is not None
                    else {}
                ),
                agent_harness_override=("pi" if qualification is not None else None),
            )

        stale = self._load_expired_active_message(session, now)
        recovered_expired_lease = self._apply_expired_active_turn(session, stale)
        recovered_expired_lease = (
            recovered_expired_lease
            or recovered_durable_preflight_expiry
            or recovered_retry_expiry
        )
        if (
            self._has_unresolved_turn(session)
            and replace_message_id is None
            and retry_message_id is None
        ):
            raise ChatServiceError(
                "turn_requires_retry",
                409,
                "Retry or edit the interrupted prompt first",
                commit_changes=recovered_expired_lease,
            )
        effective_prompt = effective_prompt if effective_prompt is not None else text
        paper_mentions = paper_mentions or []
        new_projection_bytes = (
            len(text.encode())
            + len(effective_prompt.encode())
            + _payload_bytes(paper_mentions)
            + (_payload_bytes(primary_paper_context) if primary_paper_context else 0)
            + (_payload_bytes(viewer_context) if viewer_context else 0)
            + (_payload_bytes(paper_selection) if paper_selection else 0)
        )
        owner_total_bytes = self._load_owner_storage_bytes(owner)
        model, model_route = self._validate_model(session.selected_model)
        session.selected_model = model
        replacement = self._load_replacement_plan(
            session,
            replace_message_id=replace_message_id,
            prior_revision=prior_revision,
        )
        reclaimed_projection_bytes = self._load_reclaimed_projection_bytes(replacement)
        quota = _calculate_turn_quota(
            session_transcript_bytes=session.transcript_bytes,
            session_projection_bytes=session.projection_bytes,
            owner_total_bytes=owner_total_bytes,
            reclaimed_projection_bytes=reclaimed_projection_bytes,
            new_projection_bytes=new_projection_bytes,
            current_message_count=session.message_count,
            replacement_prefix_count=None,
        )
        self._validate_turn_storage_quota(quota)
        replacement_prefix_count = self._load_replacement_prefix_count(
            session, replacement
        )
        quota = _calculate_turn_quota(
            session_transcript_bytes=session.transcript_bytes,
            session_projection_bytes=session.projection_bytes,
            owner_total_bytes=owner_total_bytes,
            reclaimed_projection_bytes=reclaimed_projection_bytes,
            new_projection_bytes=new_projection_bytes,
            current_message_count=session.message_count,
            replacement_prefix_count=replacement_prefix_count,
        )
        self._validate_turn_message_quota(quota)
        resume_boundary = self._resolve_transcript_resume_boundary(session, replacement)
        plan = self._build_turn_creation_plan(
            session,
            replacement=replacement,
            quota=quota,
            resume_boundary=resume_boundary,
            model=model,
            model_route=model_route,
            effective_prompt=effective_prompt,
            paper_mentions=paper_mentions,
            primary_paper_context=primary_paper_context,
            viewer_context=viewer_context,
            paper_selection=paper_selection,
        )
        executor_transport: Literal["legacy", "persistent"] = "legacy"
        executor_reservation_revision: int | None = None
        if (
            self.settings.chat_executor_remote_transport_enabled
            and target_harness == "pi"
            and mode.ordinary_research
        ):
            try:
                reservation = ChatExecutorTurnAdmission(self.settings).reserve(
                    self.db,
                    turn_id=plan.replacement.turn_id,
                    request_id=client_message_id,
                    owner_id=owner.hf_user_id,
                    model_route=plan.model_route,
                    now=now,
                )
            except (TurnReservationError, RuntimeError, SQLAlchemyError) as error:
                raise ChatServiceError(
                    "chat_capacity",
                    429,
                    "Research capacity is currently occupied",
                ) from error
            executor_transport = reservation.transport
            executor_reservation_revision = reservation.revision
        message = self._apply_turn_creation(
            session,
            owner,
            plan,
            client_message_id=client_message_id,
            text=text,
            web_search_enabled=web_search_enabled,
            reasoning_effort=effective_reasoning_effort,
            update_web_search_preference=update_web_search_preference,
            mode=mode,
            now=now,
        )
        if (
            created_session
            and target_harness == "pi"
            and durable_preflight is not None
            and durable_preflight.external_reservation is not None
        ):
            ChatPiTranscriptService(self.db, self.settings).prebind_new_session(session)
        if durable_coordinator is not None:
            assert durable_preflight is not None
            try:
                durable_coordinator.admit(
                    durable_preflight,
                    turn_id=plan.replacement.turn_id,
                    chat_session_id=session.id,
                    hf_user_id=owner.hf_user_id,
                    revision=plan.replacement.revision,
                    dispatch_route=self._durable_dispatch_route(
                        getattr(message, "agent_harness", None)
                        or getattr(session, "agent_harness", "claude")
                    ),
                    app_release_id=message.app_release_id,
                    worker_contract_version=self._durable_worker_contract(
                        message.worker_contract_version
                    ),
                    now=now,
                )
            except (TurnJobError, ValueError, SQLAlchemyError) as error:
                raise self._durable_admission_error(error) from error
        fetchable_urls = tuple(
            self.fetchable_url_seed(
                session.id,
                current_message_id=message.id,
                replacement_target_sequence=(
                    replacement.prior.sequence if replacement.prior else None
                ),
            )
        )
        return self._turn_admission(
            session,
            plan,
            fetchable_urls,
            external_worker_reservation=(
                _bound_external_worker_reservation(
                    durable_preflight, plan.replacement.turn_id
                )
            ),
            web_search_enabled=web_search_enabled,
            reasoning_effort=effective_reasoning_effort,
            mode=mode,
            executor_transport=executor_transport,
            executor_reservation_revision=executor_reservation_revision,
        )

    def bind_sdk_session(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID,
        turn_id: uuid.UUID,
        sdk_session_id: uuid.UUID,
        project_key: str,
    ) -> bool:
        session = self._owned(owner, session_id, lock=True)
        if session.active_turn_id != turn_id:
            return False
        if session.sdk_session_id is None:
            session.sdk_session_id = sdk_session_id
            session.sdk_project_key = project_key
            session.transcript_status = "ready"
            session.transcript_bytes = (
                self.db.scalar(
                    select(
                        func.coalesce(func.sum(ChatSDKTranscriptEntry.byte_size), 0)
                    ).where(
                        ChatSDKTranscriptEntry.project_key == project_key,
                        ChatSDKTranscriptEntry.sdk_session_id == sdk_session_id,
                    )
                )
                or 0
            )
        return session.sdk_session_id == sdk_session_id

    def activate_edit(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        replacement_sdk_session_id: uuid.UUID | None,
        project_key: str,
    ) -> bool:
        session = self._owned(owner, admission.session_id, lock=True)
        return self.edits.activate(
            session,
            admission,
            replacement_sdk_session_id,
            project_key,
        )

    def record_prepared_fork(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        fork_sdk_session_id: uuid.UUID,
        project_key: str,
    ) -> bool:
        session = self._owned(owner, admission.session_id, lock=True)
        return self.edits.record_fork(
            session, admission, fork_sdk_session_id, project_key
        )

    def abort_prepared_edit(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        code: str = "edit_prepare_failed",
    ) -> None:
        session = self._owned(owner, admission.session_id, lock=True)
        self._write_durable_terminal(
            admission,
            state="interrupted" if code == "interrupted" else "failed",
            failure_code=code,
        )
        self._settle_executor_reservation(
            admission, outcome="cancelled" if code == "interrupted" else "failed"
        )
        self.edits.abort(session, admission, code)

    def complete_turn(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        answer: str,
        citations: list[dict],
        followups: list[str],
        display_blocks: list[dict],
        finish_reason: str,
    ) -> ChatMessageRecord:
        session = self._owned(owner, admission.session_id, lock=True)
        user_message = self.db.get(ChatMessageRecord, admission.user_message_id)
        if not user_message or session.active_turn_id != admission.turn_id:
            raise ChatServiceError("stale_turn", 409, "The chat turn lease changed")
        if finish_reason not in {
            "success",
            "max_turns",
            "tool_limit",
            "scope_blocked",
        }:
            raise ChatServiceError(
                "invalid_finish_reason", 422, "Unsupported completion state"
            )
        validated_blocks = _dump_display_blocks(display_blocks)
        validated_citations = [
            CitationSnapshot.model_validate(item).model_dump(mode="json")
            for item in citations[:20]
        ]
        if _payload_bytes(validated_blocks) > 256_000:
            raise ChatServiceError(
                "projection_too_large", 422, "The assistant projection is too large"
            )
        if _payload_bytes(validated_citations) > 64_000:
            raise ChatServiceError(
                "citations_too_large", 422, "The citation projection is too large"
            )
        self._write_durable_terminal(admission, state="completed")
        self._settle_executor_reservation(admission, outcome="completed")
        followups = [
            _normalized(value, 500) for value in followups[:5] if value.strip()
        ]
        projection_bytes = len(answer.encode()) + _payload_bytes(
            validated_blocks, validated_citations, followups
        )
        session.last_sequence += 1
        assistant = ChatMessageRecord(
            id=uuid.uuid4(),
            session_id=session.id,
            turn_id=admission.turn_id,
            sequence=session.last_sequence,
            role="assistant",
            agent_harness=admission.agent_harness,
            content=answer,
            citations=validated_citations,
            followups=followups[:5],
            display_blocks=validated_blocks,
            status="complete",
            model=admission.selected_model,
            model_route=admission.model_route,
            reasoning_effort=admission.reasoning_effort,
            app_release_id=admission.app_release_id or None,
            sandbox_image_version=admission.image_version or None,
            worker_contract_version=admission.worker_contract_version or None,
            pwc_cli_version=admission.pwc_cli_version or None,
            system_prompt_sha256=admission.system_prompt_sha256 or None,
            finish_reason=finish_reason,
        )
        self.db.add(assistant)
        user_message.status = "complete"
        session.message_count += 1
        session.projection_bytes += projection_bytes
        session.active_turn_id = None
        session.active_turn_expires_at = None
        session.updated_at = _now()
        self.db.flush()
        return assistant

    def fail_turn(
        self,
        owner: ChatOwner,
        admission: TurnAdmission,
        code: str,
        interrupted: bool = False,
        display_blocks: list[dict] | None = None,
    ) -> None:
        session = self._owned(owner, admission.session_id, lock=True)
        if session.active_turn_id != admission.turn_id:
            return
        self._write_durable_terminal(
            admission,
            state="interrupted" if interrupted else "failed",
            failure_code=code,
        )
        self._settle_executor_reservation(
            admission, outcome="cancelled" if interrupted else "failed"
        )
        message = self.db.get(ChatMessageRecord, admission.user_message_id)
        if message:
            if self.edits.fail_preparation(session, message, code):
                return
            message.status = "interrupted" if interrupted else "error"
            message.error_code = code
            if display_blocks:
                validated_blocks = _dump_display_blocks(display_blocks)
                if _payload_bytes(validated_blocks) > 256_000:
                    raise ChatServiceError(
                        "projection_too_large",
                        422,
                        "The partial assistant projection is too large",
                    )
                message.display_blocks = validated_blocks
                session.projection_bytes += _payload_bytes(validated_blocks)
        session.active_turn_id = None
        session.active_turn_expires_at = None
        session.updated_at = _now()

    def _write_durable_terminal(
        self,
        admission: TurnAdmission,
        *,
        state: str,
        failure_code: str | None = None,
    ) -> None:
        if not self.settings.chat_durable_turn_dispatch_enabled:
            return
        if admission.durable_claim is None:
            raise ChatServiceError(
                "durable_claim_missing",
                503,
                "The durable chat turn claim is missing",
            )
        sanitized_code = failure_code
        if sanitized_code is not None and not re.fullmatch(
            r"[a-z0-9][a-z0-9_]{0,63}", sanitized_code
        ):
            sanitized_code = "turn_failed"
        ChatLocalTurnLeaseService(self.db, self.settings).write_terminal(
            admission.durable_claim,
            state=state,
            now=_now(),
            failure_code=sanitized_code,
        )

    def _settle_executor_reservation(
        self,
        admission: TurnAdmission,
        *,
        outcome: Literal["completed", "failed", "cancelled"],
    ) -> None:
        revision = getattr(admission, "executor_reservation_revision", None)
        if revision is None:
            return
        service = ChatTurnAdmissionService(
            environment=self.settings.environment,
            spend_limit_microusd=self.settings.chat_sandbox_application_cap_microusd,
        )
        service.settle_terminal(
            self.db,
            turn_id=admission.turn_id,
            revision=revision,
            outcome=outcome,
            cost_per_second_microusd=ChatSandboxSpendService(
                self.db, self.settings
            ).cost_per_second(),
            now=_now(),
        )

    def mark_transcript_degraded(
        self, owner: ChatOwner, session_id: uuid.UUID, turn_id: uuid.UUID
    ) -> None:
        session = self._owned(owner, session_id, lock=True)
        if session.active_turn_id == turn_id:
            session.transcript_status = "degraded"

    def mark_transcript_ready(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID,
        sdk_session_id: uuid.UUID,
    ) -> bool:
        session = self._owned(owner, session_id, lock=True)
        if session.sdk_session_id != sdk_session_id:
            return False
        session.transcript_status = "ready"
        return True

    def begin_title(
        self, owner: ChatOwner, session_id: uuid.UUID, revision: int = 1
    ) -> uuid.UUID | None:
        session = self._owned(owner, session_id, lock=True)
        if session.title_source == "user" or (
            session.title_prompt_revision == revision
            and session.title_status in ("generating", "complete", "fallback")
        ):
            return None
        token = uuid.uuid4()
        session.title_generation_id = token
        session.title_prompt_revision = revision
        session.title_status = "generating"
        return token

    def complete_title(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID,
        token: uuid.UUID,
        title: str,
        *,
        fallback: bool,
    ) -> str | None:
        session = self._owned(owner, session_id, lock=True)
        if session.title_generation_id != token or session.title_source == "user":
            return None
        normalized = normalize_title(title) or "New chat"
        session.title = normalized
        session.title_source = "fallback" if fallback else "llm"
        session.title_status = "fallback" if fallback else "complete"
        session.title_model = self.settings.chat_title_model
        session.title_generated_at = _now()
        session.title_generation_id = None
        session.updated_at = _now()
        return normalized

    def cancel_title(
        self, owner: ChatOwner, session_id: uuid.UUID, token: uuid.UUID
    ) -> bool:
        session = self._owned(owner, session_id, lock=True)
        if session.title_generation_id != token or session.title_source == "user":
            return False
        session.title_generation_id = None
        session.title_status = "pending"
        session.updated_at = _now()
        return True

    def delete_session(
        self, owner: ChatOwner, session_id: uuid.UUID
    ) -> ChatDeletionReceipt:
        session = self.db.execute(
            select(ChatSession)
            .where(
                ChatSession.id == session_id, ChatSession.hf_user_id == owner.hf_user_id
            )
            .with_for_update()
        ).scalar_one_or_none()
        if session is None:
            return ChatDeletionReceipt(session_id, None, None, None, None)
        if (
            session.active_turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > _now()
        ):
            raise ChatServiceError(
                "session_busy", 409, "Stop generation before deleting this chat"
            )
        paper_artifact_ids = list(
            self.db.scalars(
                select(ChatArtifact.id).where(
                    ChatArtifact.session_id == session.id,
                    ChatArtifact.kind == "latex_paper",
                )
            )
        )
        if paper_artifact_ids:
            paper_service = LatexPaperService(self.db, self.settings)
            for artifact_id in paper_artifact_ids:
                paper_service.delete_project(owner.hf_user_id, artifact_id)
        if session.sdk_session_id and session.sdk_project_key:
            self.db.execute(
                delete(ChatSDKTranscriptEntry).where(
                    ChatSDKTranscriptEntry.project_key == session.sdk_project_key,
                    ChatSDKTranscriptEntry.sdk_session_id == session.sdk_session_id,
                )
            )
            self.db.execute(
                delete(ChatSDKSessionSummary).where(
                    ChatSDKSessionSummary.project_key == session.sdk_project_key,
                    ChatSDKSessionSummary.sdk_session_id == session.sdk_session_id,
                )
            )
        sandbox_id = (
            session.sandbox_lease.modal_sandbox_id if session.sandbox_lease else None
        )
        snapshot_id = (
            session.sandbox_lease.workspace_snapshot_id
            if session.sandbox_lease
            else None
        )
        receipt = ChatDeletionReceipt(
            session_id=session.id,
            sandbox_id=sandbox_id,
            snapshot_id=snapshot_id,
            sdk_session_id=session.sdk_session_id,
            sdk_project_key=session.sdk_project_key,
            artifact_prefixes=tuple(
                self.db.scalars(
                    select(ChatArtifactVersion.storage_key)
                    .join(ChatArtifact)
                    .where(ChatArtifact.session_id == session.id)
                    .union(
                        select(ChatSharedArtifact.storage_key)
                        .join(ChatShare)
                        .where(ChatShare.chat_session_id == session.id)
                    )
                )
            ),
        )
        self.db.delete(session)
        return receipt

    def deletion_complete(self, receipt: ChatDeletionReceipt) -> bool:
        """Verify durable transcript, share, lease, and SDK state disappeared."""
        checks = [
            select(ChatSession.id).where(ChatSession.id == receipt.session_id),
            select(ChatMessageRecord.id).where(
                ChatMessageRecord.session_id == receipt.session_id
            ),
            select(ChatShare.id).where(ChatShare.chat_session_id == receipt.session_id),
            select(ChatArtifact.id).where(
                ChatArtifact.session_id == receipt.session_id
            ),
            select(ChatSandboxLease.chat_session_id).where(
                ChatSandboxLease.chat_session_id == receipt.session_id
            ),
        ]
        if receipt.sdk_session_id and receipt.sdk_project_key:
            checks.extend(
                [
                    select(ChatSDKTranscriptEntry.id).where(
                        ChatSDKTranscriptEntry.project_key == receipt.sdk_project_key,
                        ChatSDKTranscriptEntry.sdk_session_id == receipt.sdk_session_id,
                    ),
                    select(ChatSDKSessionSummary.id).where(
                        ChatSDKSessionSummary.project_key == receipt.sdk_project_key,
                        ChatSDKSessionSummary.sdk_session_id == receipt.sdk_session_id,
                    ),
                ]
            )
        return all(self.db.execute(query).first() is None for query in checks)
