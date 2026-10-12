"""Catalog mutation audit and method backfill progress persistence models."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from backend.models.database.base import Base


class CatalogMutationEvent(Base):
    """Append-only audit ledger for covered paper-page catalog mutations."""

    __tablename__ = "catalog_mutation_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_hf_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_username: Mapped[Optional[str]] = mapped_column(String(255))
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    paper_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    before_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    after_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    request_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_environment: Mapped[str] = mapped_column(String(32), nullable=False)
    release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rollback_of_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_mutation_events.id", ondelete="RESTRICT"),
    )
    schema_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "actor_role IN ('admin', 'contributor')",
            name="catalog_mutation_events_actor_role_check",
        ),
        Index("idx_catalog_mutation_events_actor", "actor_hf_subject", "created_at"),
        Index("idx_catalog_mutation_events_created", "created_at", "id"),
    )


class CatalogMutationIdempotency(Base):
    __tablename__ = "catalog_mutation_idempotency"

    actor_hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_mutation_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CatalogAuditReadProgress(Base):
    __tablename__ = "catalog_audit_read_progress"

    admin_hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    read_through_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MethodReferenceBackfillMonth(Base):
    """Resumable reference-scan coverage for one method and publication month."""

    __tablename__ = "method_reference_backfill_months"

    method_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("methods.id", ondelete="CASCADE"), primary_key=True
    )
    month_start: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    eligible_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolvable_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retryable_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cursor_published_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    cursor_paper_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'complete', 'failed')",
            name="method_reference_backfill_months_status_check",
        ),
        Index("idx_method_reference_backfill_status", "status", "updated_at"),
    )


class MethodKeywordBackfillRun(Base):
    """Versioned, resumable cursor for catalog-wide keyword matching."""

    __tablename__ = "method_keyword_backfill_runs"

    keyword_catalog_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    eligible_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cursor_paper_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'complete', 'failed')",
            name="method_keyword_backfill_runs_status_check",
        ),
        Index(
            "uq_method_keyword_backfill_one_running",
            "status",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )
