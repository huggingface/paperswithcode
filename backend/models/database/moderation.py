"""Pending paper edit and paper-edit authorization persistence models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from backend.models.database.base import Base


class PendingPaperEdit(Base):
    """Edit submissions from non-admin Hugging Face users.

    Each row records a proposed change to one of the paper-page edit surfaces
    (tasks, methods, evaluation results, GitHub repositories, project pages),
    or an unscoped taxonomy suggestion submitted from a directory page.
    Admin direct edits bypass this table and continue to mutate live data
    through the existing admin endpoints. Approval of a pending row replays
    ``proposed_payload`` through the same backend mutation services.

    ``is_author`` is true when the submitting HF username matched a linked
    author of the paper at submit time. It is informational today and used to
    surface author-originated edits in review; a future change can use it to
    auto-approve without going through admin review.
    """

    __tablename__ = "pending_paper_edits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=True,
    )
    hf_username: Mapped[str] = mapped_column(String(255), nullable=False)
    hf_subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_author: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    edit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    current_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    applied_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    result_entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    result_entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    catalog_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_mutation_events.id", ondelete="RESTRICT"),
        nullable=True,
    )
    conflict_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_review_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_by_kind: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reviewed_by_hf_subject: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    review_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    review_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    review_evidence: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "edit_type IN ('tasks', 'methods', 'evaluations', 'repositories', 'project_pages', 'source_url', 'hf_artifacts', 'organizations', 'x_threads', 'new_task', 'new_method', 'new_benchmark', 'new_metric', 'new_conference', 'new_organization', 'new_external_paper')",
            name="pending_paper_edits_edit_type_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="pending_paper_edits_status_check",
        ),
        CheckConstraint(
            "reviewed_by_kind IS NULL OR reviewed_by_kind IN ('human', 'codex', 'auto')",
            name="pending_paper_edits_reviewed_by_kind_check",
        ),
        Index(
            "idx_pending_paper_edits_status_created_at",
            "status",
            "created_at",
        ),
        Index(
            "idx_pending_paper_edits_paper_edit_type",
            "paper_id",
            "edit_type",
        ),
        Index("idx_pending_paper_edits_hf_username", "hf_username"),
        Index("idx_pending_paper_edits_hf_subject", "hf_subject", "created_at"),
        Index("idx_pending_paper_edits_source_ip", "source_ip", "created_at"),
        Index(
            "uq_pending_paper_edits_subject_idempotency",
            "hf_subject",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "idx_pending_paper_edits_author_pending",
            "is_author",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PendingPaperEdit(id={self.id}, paper_id={self.paper_id}, "
            f"hf_username='{self.hf_username}', edit_type='{self.edit_type}', "
            f"status='{self.status}')>"
        )


class PaperEditAccount(Base):
    """Shared suspension state; account locks serialize limits and suspension."""

    __tablename__ = "paper_edit_accounts"
    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PaperEditAuthorization(Base):
    """Short-lived device authorization. Only hashes of secrets are persisted."""

    __tablename__ = "paper_edit_authorizations"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paper_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_key: Mapped[Optional[str]] = mapped_column(String(64))
    device_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_hash: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    hf_subject: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
