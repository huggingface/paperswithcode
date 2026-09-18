"""Authenticated end-user feedback for completed assistant responses.

The database row is the record. The configured trace export (Trackio today,
Langfuse before 2026-09-01) receives a best-effort mirror so dashboards can
correlate ratings with traces, but a mirror failure never loses the rating.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.chat import ChatFeedbackEntry, ChatFeedbackListResponse
from backend.models.database import ChatFeedback, ChatMessageRecord, ChatSession
from backend.services.chat_tracing_service import configured_trace_export_client
from backend.services.chat_trackio_service import TrackioClient

logger = logging.getLogger(__name__)


class ChatFeedbackUnavailable(Exception):
    """Raised when feedback cannot be stored."""


class ChatFeedbackService:
    SCORE_NAME = "user-thumbs"

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def submit(
        self,
        *,
        owner_id: str,
        assistant_message_id: uuid.UUID,
        value: bool,
        comment: str | None = None,
    ) -> bool:
        message = self.db.execute(
            select(ChatMessageRecord.turn_id, ChatMessageRecord.session_id)
            .join(ChatSession, ChatSession.id == ChatMessageRecord.session_id)
            .where(
                ChatMessageRecord.id == assistant_message_id,
                ChatMessageRecord.role == "assistant",
                ChatMessageRecord.status == "complete",
                ChatSession.hf_user_id == owner_id,
            )
        ).one_or_none()
        if message is None:
            return False

        trace_id = self.db.execute(
            select(ChatMessageRecord.langfuse_trace_id)
            .where(
                ChatMessageRecord.turn_id == message.turn_id,
                ChatMessageRecord.session_id == message.session_id,
                ChatMessageRecord.role == "user",
            )
            .order_by(ChatMessageRecord.sequence.desc())
            .limit(1)
        ).scalar_one_or_none()
        normalized_comment = None
        if comment is not None:
            normalized_comment = comment.strip() or None

        now = datetime.now(UTC)
        row = self.db.get(ChatFeedback, assistant_message_id)
        if row is None:
            row = ChatFeedback(
                assistant_message_id=assistant_message_id,
                session_id=message.session_id,
                turn_id=message.turn_id,
                value=value,
                comment=normalized_comment,
                trace_id=trace_id or None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            # A user may change their mind; the latest rating is the record.
            row.value = value
            row.comment = normalized_comment
            row.trace_id = trace_id or row.trace_id
            row.updated_at = now
        self.db.flush()

        exported_to = self._export(row)
        if exported_to is not None:
            row.exported_to = exported_to
            row.exported_at = datetime.now(UTC)
            self.db.flush()
        return True

    def _export(self, row: ChatFeedback) -> str | None:
        """Mirror the rating to the configured trace store; never raise."""
        client = configured_trace_export_client(self.settings)
        if client is None:
            return None
        score_id = hashlib.sha256(
            f"{self.settings.environment}:{self.SCORE_NAME}:{row.assistant_message_id}".encode()
        ).hexdigest()[:32]
        try:
            if isinstance(client, TrackioClient):
                client.log_metrics(
                    "feedback",
                    {"feedback/thumbs_up": 1.0 if row.value else 0.0},
                    log_id=score_id,
                )
                return "trackio"
            if not row.trace_id:
                return None
            client.create_score(
                trace_id=row.trace_id,
                score_id=score_id,
                name=self.SCORE_NAME,
                value=1.0 if row.value else 0.0,
                data_type="BOOLEAN",
                comment=row.comment,
                metadata={"assistant_message_id": str(row.assistant_message_id)},
            )
            return "langfuse"
        except Exception as exc:
            # The row is already stored; the mirror is diagnostics only.
            logger.warning(
                "chat feedback export failed backend=%s error=%s",
                type(client).__name__,
                type(exc).__name__,
            )
            return None

    def list_recent(
        self, *, limit: int = 50, value: bool | None = None
    ) -> ChatFeedbackListResponse:
        if not 1 <= limit <= 200:
            raise ValueError("feedback limit is out of range")
        filters = [] if value is None else [ChatFeedback.value.is_(value)]
        rows = self.db.execute(
            select(ChatFeedback)
            .where(*filters)
            .order_by(ChatFeedback.updated_at.desc())
            .limit(limit)
        ).scalars()
        counts = dict(
            self.db.execute(
                select(ChatFeedback.value, func.count()).group_by(ChatFeedback.value)
            ).all()
        )
        return ChatFeedbackListResponse(
            environment=self.settings.environment,
            total=sum(counts.values()),
            positive=counts.get(True, 0),
            negative=counts.get(False, 0),
            items=[
                ChatFeedbackEntry(
                    assistant_message_id=row.assistant_message_id,
                    session_id=row.session_id,
                    turn_id=row.turn_id,
                    value=row.value,
                    comment=row.comment,
                    trace_id=row.trace_id,
                    exported_to=row.exported_to,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ],
        )
