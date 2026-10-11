"""Chat harness transcript and session-summary persistence models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from backend.models.database.base import Base


class ChatSDKTranscriptEntry(Base):
    __tablename__ = "chat_sdk_transcript_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_key: Mapped[str] = mapped_column(Text, nullable=False)
    sdk_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    subpath: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    entry_uuid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry: Mapped[dict] = mapped_column(JSONB, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        Index(
            "idx_chat_sdk_entries_load",
            "project_key",
            "sdk_session_id",
            "subpath",
            "id",
        ),
        Index(
            "idx_chat_sdk_entries_uuid",
            "project_key",
            "sdk_session_id",
            "subpath",
            "entry_uuid",
            unique=True,
            postgresql_where=text("entry_uuid IS NOT NULL"),
        ),
    )


class ChatSDKSessionSummary(Base):
    __tablename__ = "chat_sdk_session_summaries"

    project_key: Mapped[str] = mapped_column(Text, primary_key=True)
    sdk_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    mtime: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ChatPiSession(Base):
    """Server-owned index for one opaque native Pi JSONL session."""

    __tablename__ = "chat_pi_sessions"

    agent_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    current_leaf_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    byte_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    format_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "entry_count >= 0 AND byte_size >= 0",
            name="chat_pi_sessions_nonnegative_check",
        ),
        CheckConstraint(
            "format_version = 1", name="chat_pi_sessions_format_version_check"
        ),
    )


class ChatPiTranscriptEntry(Base):
    """One ordered, otherwise opaque Pi session record."""

    __tablename__ = "chat_pi_transcript_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_pi_sessions.agent_session_id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entry_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_entry_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entry: Mapped[dict] = mapped_column(JSONB, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "ordinal >= 0 AND byte_size >= 2 AND byte_size <= 1048576",
            name="chat_pi_transcript_entries_bounds_check",
        ),
        UniqueConstraint(
            "agent_session_id",
            "ordinal",
            name="uq_chat_pi_transcript_entries_ordinal",
        ),
        Index(
            "idx_chat_pi_transcript_entries_entry_id",
            "agent_session_id",
            "entry_id",
            unique=True,
            postgresql_where=text("entry_id IS NOT NULL"),
        ),
    )


class ChatPiPreparedFork(Base):
    """Inactive native Pi branch awaiting transactional edit activation."""

    __tablename__ = "chat_pi_prepared_forks"

    fork_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    boundary_entry_id: Mapped[str] = mapped_column(Text, nullable=False)
    entries: Mapped[list] = mapped_column(JSONB, nullable=False)
    entry_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    format_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "entry_count >= 1 AND byte_size >= 2 AND format_version = 1",
            name="chat_pi_prepared_forks_bounds_check",
        ),
        Index("idx_chat_pi_prepared_forks_chat", "chat_session_id"),
    )


class ChatHarnessAssignmentAudit(Base):
    """Content-free audit of protected harness overrides and cutover assignment."""

    __tablename__ = "chat_harness_assignment_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    agent_harness: Mapped[str] = mapped_column(String(16), nullable=False)
    assignment_source: Mapped[str] = mapped_column(String(24), nullable=False)
    operator_subject_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "agent_harness IN ('claude','pi')",
            name="chat_harness_assignment_audit_harness_check",
        ),
        CheckConstraint(
            "assignment_source IN ('default','cutover','admin_override')",
            name="chat_harness_assignment_audit_source_check",
        ),
    )
