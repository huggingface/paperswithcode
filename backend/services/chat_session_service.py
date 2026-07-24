"""Transactional ownership, idempotency, leases, and projections for chat."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER, CitationSnapshot
from backend.models.database import (
    ChatMessageRecord,
    ChatSDKSessionSummary,
    ChatSDKTranscriptEntry,
    ChatSession,
)
from backend.services.chat_title_service import normalize_title


class ChatServiceError(Exception):
    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        commit_changes: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.commit_changes = commit_changes


@dataclass(frozen=True)
class ChatOwner:
    hf_user_id: str
    hf_username: str


@dataclass(frozen=True)
class ReplayAssistant:
    content: str
    followups: list[str]


@dataclass(frozen=True)
class TurnAdmission:
    session_id: uuid.UUID
    turn_id: uuid.UUID
    user_message_id: uuid.UUID
    selected_model: str
    model_route: str
    sdk_session_id: uuid.UUID | None
    sdk_project_key: str | None
    is_first_turn: bool
    replay_assistant: ReplayAssistant | None = None
    resume_boundary_id: uuid.UUID | None = None
    is_replacement: bool = False
    prompt_revision: int = 1
    title_should_generate: bool = False
    execution_backend: str = "local_mcp"
    app_release_id: str = ""
    image_version: str = ""
    worker_contract_version: str = ""
    pwc_cli_version: str = ""
    system_prompt_sha256: str = ""


def owner_from_user(user: dict) -> ChatOwner:
    return ChatOwner(hf_user_id=user["hf_user_id"], hf_username=user["username"])


def _now() -> datetime:
    return datetime.now(UTC)


def _normalized(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def _payload_bytes(*values: object) -> int:
    return sum(
        len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        for value in values
    )


class ChatSessionService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def _owned(
        self, owner: ChatOwner, session_id: uuid.UUID, *, lock: bool = False
    ) -> ChatSession:
        query = select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.hf_user_id == owner.hf_user_id
        )
        if lock:
            query = query.with_for_update()
        session = self.db.execute(query).scalar_one_or_none()
        if session is None:
            raise ChatServiceError("session_not_found", 404, "Chat session not found")
        return session

    def _validate_model(self, model: str | None) -> tuple[str, str]:
        selected = model or self.settings.chat_model_choices[0]["id"]
        route = self.settings.chat_model_routes.get(selected)
        if route is None:
            raise ChatServiceError(
                "invalid_chat_model", 422, "Unsupported research model"
            )
        return selected, route

    def create_session(
        self, owner: ChatOwner, selected_model: str | None = None
    ) -> ChatSession:
        model, _ = self._validate_model(selected_model)
        self.db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtextextended(owner.hf_user_id, 0))
            )
        )
        count = (
            self.db.scalar(
                select(func.count())
                .select_from(ChatSession)
                .where(ChatSession.hf_user_id == owner.hf_user_id)
            )
            or 0
        )
        if count >= self.settings.chat_session_limit:
            raise ChatServiceError(
                "chat_session_quota_exceeded",
                409,
                "Delete a chat before creating another",
            )
        session_id = uuid.uuid4()
        allocation_bucket = (
            int.from_bytes(hashlib.sha256(session_id.bytes).digest()[:4], "big") % 100
        )
        if self.settings.chat_new_chat_modal_percentage == 0:
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
            execution_backend=execution_backend,
            updated_at=_now(),
        )
        self.db.add(session)
        self.db.flush()
        return session

    def list_sessions(
        self, owner: ChatOwner, cursor: str | None, limit: int
    ) -> tuple[list[ChatSession], str | None]:
        query = select(ChatSession).where(ChatSession.hf_user_id == owner.hf_user_id)
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

    def get_session(
        self, owner: ChatOwner, session_id: uuid.UUID
    ) -> tuple[ChatSession, list[ChatMessageRecord]]:
        session = self._owned(owner, session_id)
        messages = list(
            self.db.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.status != "superseded",
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
        session.hf_username = owner.hf_username
        session.updated_at = _now()
        self.db.flush()
        return session

    def begin_turn(
        self,
        owner: ChatOwner,
        *,
        session_id: uuid.UUID | None,
        client_message_id: str,
        text: str,
        initial_model: str | None = None,
        replace_message_id: uuid.UUID | None = None,
        prior_revision: int | None = None,
    ) -> TurnAdmission:
        if session_id is None:
            session = self.create_session(owner, initial_model)
        else:
            session = self._owned(owner, session_id, lock=True)
        now = _now()
        existing = self.db.execute(
            select(ChatMessageRecord).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.client_message_id == client_message_id,
            )
        ).scalar_one_or_none()
        if existing:
            assistant = self.db.execute(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.turn_id == existing.turn_id,
                    ChatMessageRecord.role == "assistant",
                )
            ).scalar_one_or_none()
            if assistant:
                return TurnAdmission(
                    session.id,
                    existing.turn_id,
                    existing.id,
                    existing.model or session.selected_model,
                    existing.model_route
                    or self._validate_model(session.selected_model)[1],
                    session.sdk_session_id,
                    session.sdk_project_key,
                    existing.sequence == 1,
                    ReplayAssistant(
                        content=assistant.content,
                        followups=list(assistant.followups or []),
                    ),
                    prompt_revision=existing.revision,
                    execution_backend=session.execution_backend,
                )
            if (
                existing.status == "generating"
                and session.active_turn_expires_at
                and session.active_turn_expires_at <= now
            ):
                existing.status = "interrupted"
                existing.error_code = "lease_expired"
                if session.active_turn_id == existing.turn_id:
                    session.active_turn_id = None
                    session.active_turn_expires_at = None
                raise ChatServiceError(
                    "turn_requires_retry",
                    409,
                    "Retry or edit the interrupted prompt with a new request ID",
                    commit_changes=True,
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

        if session.transcript_status == "degraded":
            raise ChatServiceError(
                "chat_transcript_degraded",
                409,
                "This chat is awaiting transcript recovery and cannot be resumed",
            )

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
        other_active = self.db.scalar(
            select(func.count())
            .select_from(ChatSession)
            .where(
                ChatSession.hf_user_id == owner.hf_user_id,
                ChatSession.id != session.id,
                ChatSession.active_turn_id.is_not(None),
                ChatSession.active_turn_expires_at > func.now(),
            )
        )
        if other_active:
            raise ChatServiceError(
                "chat_capacity", 429, "Another research response is already running"
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
        if active_total >= self.settings.chat_max_concurrency:
            raise ChatServiceError(
                "chat_capacity", 429, "Research capacity is currently occupied"
            )

        recovered_expired_lease = False
        if (
            session.active_turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > now
        ):
            raise ChatServiceError(
                "session_busy", 409, "This chat is generating a response"
            )
        if session.active_turn_id:
            stale = self.db.execute(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.turn_id == session.active_turn_id,
                    ChatMessageRecord.role == "user",
                    ChatMessageRecord.status == "generating",
                )
            ).scalar_one_or_none()
            if stale and stale.status == "generating":
                stale.status = "interrupted"
                stale.error_code = "lease_expired"
            session.active_turn_id = None
            session.active_turn_expires_at = None
            recovered_expired_lease = True

        unresolved = self.db.execute(
            select(ChatMessageRecord.id).where(
                ChatMessageRecord.session_id == session.id,
                ChatMessageRecord.role == "user",
                ChatMessageRecord.status.in_(["interrupted", "error"]),
            )
        ).first()
        if unresolved and replace_message_id is None:
            raise ChatServiceError(
                "turn_requires_retry",
                409,
                "Retry or edit the interrupted prompt first",
                commit_changes=recovered_expired_lease,
            )
        total = (
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
        if (
            session.transcript_bytes + session.projection_bytes
            >= self.settings.chat_session_byte_limit
            or total >= self.settings.chat_user_byte_limit
        ):
            raise ChatServiceError(
                "chat_storage_quota_exceeded", 409, "Chat storage quota exceeded"
            )

        model, route = self._validate_model(session.selected_model)
        prior: ChatMessageRecord | None = None
        if replace_message_id is not None:
            prior = self.db.execute(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.id == replace_message_id,
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.role == "user",
                    ChatMessageRecord.revision == prior_revision,
                    ChatMessageRecord.status.in_(["interrupted", "error"]),
                )
            ).scalar_one_or_none()
            if prior is None:
                raise ChatServiceError(
                    "invalid_replacement", 409, "This prompt can no longer be edited"
                )
            later = self.db.execute(
                select(ChatMessageRecord.id).where(
                    ChatMessageRecord.session_id == session.id,
                    ChatMessageRecord.sequence > prior.sequence,
                    ChatMessageRecord.status != "superseded",
                )
            ).first()
            if later:
                raise ChatServiceError(
                    "invalid_replacement",
                    409,
                    "Only the latest failed prompt can be edited",
                )
            prior.status = "superseded"
            turn_id = prior.turn_id
            revision = prior.revision + 1
        else:
            turn_id = uuid.uuid4()
            revision = 1
        messages_added = 1 if prior is not None else 2
        if (
            session.message_count + messages_added
            > self.settings.chat_session_message_limit
        ):
            raise ChatServiceError(
                "chat_message_quota_exceeded",
                409,
                "This chat has reached its message limit; start a new chat",
            )
        resume_boundary: uuid.UUID | None = None
        if prior is not None:
            resume_boundary = prior.sdk_resume_boundary_id
        elif session.sdk_session_id and session.sdk_project_key:
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
        message_id = uuid.uuid4()
        session.last_sequence += 1
        if prior is None:
            session.message_count += 1
        session.active_turn_id = turn_id
        session.active_turn_expires_at = now + timedelta(
            seconds=self.settings.chat_timeout_seconds + 30
        )
        session.hf_username = owner.hf_username
        session.updated_at = now
        session.projection_bytes += len(text.strip().encode())
        message = ChatMessageRecord(
            id=message_id,
            session_id=session.id,
            turn_id=turn_id,
            sequence=session.last_sequence,
            role="user",
            content=text.strip(),
            client_message_id=client_message_id,
            revision=revision,
            supersedes_message_id=prior.id if prior else None,
            sdk_resume_boundary_id=resume_boundary,
            status="generating",
            model=model,
            model_route=route,
            app_release_id=self.settings.release_id,
            sandbox_image_version=(
                self.settings.chat_modal_image_version
                if session.execution_backend == "modal_cli"
                else None
            ),
            worker_contract_version=(
                self.settings.chat_worker_contract_version
                if session.execution_backend == "modal_cli"
                else None
            ),
            pwc_cli_version=(
                self.settings.chat_pwc_cli_version
                if session.execution_backend == "modal_cli"
                else None
            ),
            system_prompt_sha256=(
                self.settings.chat_system_prompt_sha256
                if session.execution_backend == "modal_cli"
                else None
            ),
            last_attempted_at=now,
        )
        self.db.add(message)
        self.db.flush()
        return TurnAdmission(
            session.id,
            turn_id,
            message_id,
            model,
            route,
            session.sdk_session_id,
            session.sdk_project_key,
            session.message_count == 1,
            resume_boundary_id=resume_boundary,
            is_replacement=prior is not None,
            prompt_revision=revision,
            title_should_generate=(
                session.message_count == 1
                and session.title_source != "user"
                and (prior is None or prior.content.strip() != text.strip())
            ),
            execution_backend=session.execution_backend,
            app_release_id=self.settings.release_id,
            image_version=self.settings.chat_modal_image_version,
            worker_contract_version=self.settings.chat_worker_contract_version,
            pwc_cli_version=self.settings.chat_pwc_cli_version,
            system_prompt_sha256=self.settings.chat_system_prompt_sha256,
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

    def rebind_sdk_session(
        self,
        owner: ChatOwner,
        session_id: uuid.UUID,
        turn_id: uuid.UUID,
        expected_sdk_session_id: uuid.UUID,
        replacement_sdk_session_id: uuid.UUID | None,
        project_key: str,
    ) -> bool:
        session = self._owned(owner, session_id, lock=True)
        if (
            session.active_turn_id != turn_id
            or session.sdk_session_id != expected_sdk_session_id
        ):
            return False
        session.sdk_session_id = replacement_sdk_session_id
        session.sdk_project_key = project_key if replacement_sdk_session_id else None
        session.transcript_status = "ready" if replacement_sdk_session_id else "pending"
        session.transcript_bytes = 0
        if replacement_sdk_session_id:
            session.transcript_bytes = (
                self.db.scalar(
                    select(
                        func.coalesce(func.sum(ChatSDKTranscriptEntry.byte_size), 0)
                    ).where(
                        ChatSDKTranscriptEntry.project_key == project_key,
                        ChatSDKTranscriptEntry.sdk_session_id
                        == replacement_sdk_session_id,
                    )
                )
                or 0
            )
        return True

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
        validated_blocks = [
            block.model_dump(mode="json", exclude_defaults=True)
            for block in DISPLAY_BLOCKS_ADAPTER.validate_python(display_blocks)
        ]
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
            content=answer,
            citations=validated_citations,
            followups=followups[:5],
            display_blocks=validated_blocks,
            status="complete",
            model=admission.selected_model,
            model_route=admission.model_route,
            app_release_id=admission.app_release_id or None,
            sandbox_image_version=admission.image_version or None,
            worker_contract_version=admission.worker_contract_version or None,
            pwc_cli_version=admission.pwc_cli_version or None,
            system_prompt_sha256=admission.system_prompt_sha256 or None,
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
        message = self.db.get(ChatMessageRecord, admission.user_message_id)
        if message:
            message.status = "interrupted" if interrupted else "error"
            message.error_code = code
            if display_blocks:
                validated_blocks = [
                    block.model_dump(mode="json", exclude_defaults=True)
                    for block in DISPLAY_BLOCKS_ADAPTER.validate_python(display_blocks)
                ]
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

    def delete_session(
        self, owner: ChatOwner, session_id: uuid.UUID
    ) -> tuple[str | None, str | None]:
        session = self.db.execute(
            select(ChatSession)
            .where(
                ChatSession.id == session_id, ChatSession.hf_user_id == owner.hf_user_id
            )
            .with_for_update()
        ).scalar_one_or_none()
        if session is None:
            return None, None
        if (
            session.active_turn_id
            and session.active_turn_expires_at
            and session.active_turn_expires_at > _now()
        ):
            raise ChatServiceError(
                "session_busy", 409, "Stop generation before deleting this chat"
            )
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
        self.db.delete(session)
        return sandbox_id, snapshot_id
