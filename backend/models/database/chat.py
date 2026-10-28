"""Chat session, turn, message, share, feedback, and latency persistence models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base

if TYPE_CHECKING:
    from backend.models.database.chat_artifacts import ChatArtifact, ChatArtifactVersion
    from backend.models.database.chat_sandbox import ChatSandboxLease
    from backend.models.database.papers import Paper


class ChatSession(Base):
    """Durable user-owned research chat metadata and generation lease."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    hf_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    hf_username: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="New chat"
    )
    title_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    title_source: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    title_generation_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    title_prompt_revision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    selected_model: Mapped[str] = mapped_column(String(255), nullable=False)
    execution_backend: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="local_mcp"
    )
    agent_harness: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="claude"
    )
    web_search_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="high"
    )
    primary_paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("papers.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    active_turn_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    active_turn_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sdk_session_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True, unique=True
    )
    sdk_project_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    transcript_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    projection_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )

    messages: Mapped[list["ChatMessageRecord"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
    primary_paper: Mapped[Optional["Paper"]] = relationship(
        "Paper", foreign_keys=[primary_paper_id], lazy="selectin"
    )
    share: Mapped[Optional["ChatShare"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    artifacts: Mapped[list["ChatArtifact"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
    sandbox_lease: Mapped[Optional["ChatSandboxLease"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    __table_args__ = (
        CheckConstraint(
            "execution_backend IN ('local_mcp', 'modal_cli')",
            name="chat_sessions_execution_backend_check",
        ),
        CheckConstraint(
            "agent_harness IN ('claude', 'pi')",
            name="chat_sessions_agent_harness_check",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low','medium','high','max')",
            name="chat_sessions_reasoning_effort_check",
        ),
        Index(
            "idx_chat_sessions_owner_updated",
            "hf_user_id",
            text("updated_at DESC"),
            text("id DESC"),
        ),
        Index(
            "idx_chat_sessions_owner_active_updated",
            "hf_user_id",
            text("updated_at DESC"),
            text("id DESC"),
            postgresql_where=text("archived_at IS NULL"),
        ),
    )


class ChatTurnJob(Base):
    """Content-free durable ownership and fencing for one research chat turn."""

    __tablename__ = "chat_turn_jobs"

    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    hf_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    dispatch_class: Mapped[str] = mapped_column(String(32), nullable=False)
    dispatch_route: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    worker_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    worker_generation: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    lease_generation: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_contract_version: Mapped[str] = mapped_column(String(128), nullable=False)
    admitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminal_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_agent_session_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    last_resume_boundary_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    event_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    __table_args__ = (
        CheckConstraint("revision > 0", name="chat_turn_jobs_revision_check"),
        CheckConstraint(
            "worker_generation IS NULL OR worker_generation > 0",
            name="chat_turn_jobs_worker_generation_check",
        ),
        CheckConstraint(
            "lease_generation IS NULL OR lease_generation > 0",
            name="chat_turn_jobs_lease_generation_check",
        ),
        CheckConstraint(
            "state IN ('admitted', 'leased', 'running', 'waiting_model', "
            "'waiting_tool', 'cancelling', 'completed', 'failed', 'interrupted')",
            name="chat_turn_jobs_state_check",
        ),
        CheckConstraint(
            "(state = 'admitted' AND worker_id IS NULL "
            "AND worker_generation IS NULL AND lease_generation IS NULL "
            "AND lease_expires_at IS NULL) OR "
            "(state IN "
            "('leased','running','waiting_model','waiting_tool','cancelling') "
            "AND worker_id IS NOT NULL AND worker_generation IS NOT NULL "
            "AND lease_generation IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(state IN ('completed','failed','interrupted') "
            "AND worker_id IS NOT NULL AND worker_generation IS NOT NULL "
            "AND lease_generation IS NOT NULL AND lease_expires_at IS NULL)",
            name="chat_turn_jobs_lease_fields_check",
        ),
        CheckConstraint(
            "(state IN ('completed','failed','interrupted')) "
            "= (terminal_at IS NOT NULL)",
            name="chat_turn_jobs_terminal_timestamp_check",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code ~ '^[a-z0-9][a-z0-9_]{0,63}$'",
            name="chat_turn_jobs_failure_code_check",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "failure_code IS NULL OR (length(failure_code) BETWEEN 1 AND 64 "
            "AND failure_code NOT GLOB '*[^a-z0-9_]*' "
            "AND substr(failure_code, 1, 1) GLOB '[a-z0-9]')",
            name="chat_turn_jobs_failure_code_check",
        ).ddl_if(dialect="sqlite"),
        Index("idx_chat_turn_jobs_claim", "state", "admitted_at", "turn_id"),
        Index("idx_chat_turn_jobs_expiry", "state", "lease_expires_at"),
        Index(
            "idx_chat_turn_jobs_terminal_cleanup",
            "terminal_at",
            "turn_id",
            postgresql_where=text("state IN ('completed','failed','interrupted')"),
            sqlite_where=text("state IN ('completed','failed','interrupted')"),
        ),
        Index(
            "uq_chat_turn_jobs_nonterminal_owner",
            "hf_user_id",
            unique=True,
            postgresql_where=text(
                "state IN "
                "('admitted','leased','running','waiting_model','waiting_tool','cancelling')"
            ),
            sqlite_where=text(
                "state IN "
                "('admitted','leased','running','waiting_model','waiting_tool','cancelling')"
            ),
        ),
    )


class ChatTurnAdmissionBudget(Base):
    """Environment-wide capacity and incremental-spend reservation totals."""

    __tablename__ = "chat_turn_admission_budgets"

    environment: Mapped[str] = mapped_column(String(16), primary_key=True)
    turn_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    environment_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    spend_limit_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    active_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_environments: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    reserved_operations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    spent_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "environment IN ('staging','production')",
            name="chat_turn_admission_budget_environment_check",
        ),
        CheckConstraint(
            "turn_limit = 32 AND environment_limit = 32 AND operation_limit = 128",
            name="chat_turn_admission_budget_limits_check",
        ),
        CheckConstraint(
            "spend_limit_microusd > 0 AND active_turns >= 0 AND "
            "reserved_environments >= 0 AND reserved_operations >= 0 AND "
            "reserved_microusd >= 0 AND spent_microusd >= 0",
            name="chat_turn_admission_budget_nonnegative_check",
        ),
    )


class ChatTurnReservation(Base):
    """Exactly-once capacity and spend ownership for one admitted turn."""

    __tablename__ = "chat_turn_reservations"

    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("chat_turn_admission_budgets.environment", ondelete="RESTRICT"),
        nullable=False,
    )
    transport: Mapped[str] = mapped_column(String(16), nullable=False, default="legacy")
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reserved_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reserved_environments: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    reserved_operations: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    reserved_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_microusd: Mapped[Optional[int]] = mapped_column(BigInteger)
    terminal_outcome: Mapped[Optional[str]] = mapped_column(String(16))
    resource_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    resource_ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "state IN ('reserved','dispatched','completed','failed','cancelled','cost_unknown')",
            name="chat_turn_reservations_state_check",
        ),
        CheckConstraint(
            "transport IN ('legacy','persistent')",
            name="chat_turn_reservations_transport_check",
        ),
        CheckConstraint(
            "terminal_outcome IS NULL OR "
            "terminal_outcome IN ('completed','failed','cancelled')",
            name="chat_turn_reservations_outcome_check",
        ),
        CheckConstraint(
            "resource_ended_at IS NULL OR "
            "(resource_started_at IS NOT NULL AND resource_ended_at >= resource_started_at)",
            name="chat_turn_reservations_resource_window_check",
        ),
        CheckConstraint(
            "revision > 0 AND reserved_turns = 1 AND reserved_environments = 1 "
            "AND reserved_operations = 4 AND reserved_microusd >= 0 AND "
            "(actual_microusd IS NULL OR actual_microusd >= 0)",
            name="chat_turn_reservations_bounds_check",
        ),
        Index(
            "uq_chat_turn_reservations_active_owner",
            "environment",
            "owner_id",
            unique=True,
            postgresql_where=text("state IN ('reserved','dispatched')"),
            sqlite_where=text("state IN ('reserved','dispatched')"),
        ),
        Index("idx_chat_turn_reservations_state", "environment", "state"),
    )


class ChatTurnEventChunk(Base):
    """A bounded contiguous batch of public stream events for one turn."""

    __tablename__ = "chat_turn_event_chunks"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    turn_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_turn_jobs.turn_id", ondelete="CASCADE"),
        nullable=False,
    )
    first_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    events: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    payload_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "turn_id",
            "first_sequence",
            name="uq_chat_turn_event_chunk_start",
        ),
        CheckConstraint(
            "last_sequence >= first_sequence",
            name="ck_chat_turn_event_chunk_range",
        ),
        Index("idx_chat_turn_event_chunks_after", "turn_id", "last_sequence"),
    )


class ChatMessageRecord(Base):
    """Sanitized UI projection for one durable user or assistant message."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    paper_mentions: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    primary_paper_context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    viewer_context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    paper_selection: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    effective_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    langfuse_trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    client_message_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    web_search_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="high"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    supersedes_message_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    sdk_resume_boundary_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    agent_resume_boundary_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_harness: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    followups: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    display_blocks: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    model_route: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    app_release_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sandbox_image_version: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    worker_contract_version: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    pwc_cli_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    system_prompt_sha256: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    finish_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prepared_fork_sdk_session_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    prepared_fork_sdk_project_key: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    last_attempted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")
    artifact_versions: Mapped[list["ChatArtifactVersion"]] = relationship(
        back_populates="message", passive_deletes=True
    )
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')", name="chat_messages_role_check"
        ),
        CheckConstraint(
            "agent_harness IS NULL OR agent_harness IN ('claude', 'pi')",
            name="chat_messages_agent_harness_check",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low','medium','high','max')",
            name="chat_messages_reasoning_effort_check",
        ),
        CheckConstraint(
            "(prepared_fork_sdk_session_id IS NULL) = "
            "(prepared_fork_sdk_project_key IS NULL)",
            name="chat_messages_prepared_fork_pair_check",
        ),
        UniqueConstraint(
            "session_id", "sequence", name="uq_chat_messages_session_sequence"
        ),
        Index("idx_chat_messages_session_turn", "session_id", "turn_id"),
        Index(
            "idx_chat_messages_client_id",
            "session_id",
            "client_message_id",
            unique=True,
            postgresql_where=text("client_message_id IS NOT NULL"),
        ),
        Index(
            "idx_chat_messages_current_revision",
            "session_id",
            "turn_id",
            unique=True,
            postgresql_where=text("role = 'user' AND status <> 'superseded'"),
        ),
    )


class ChatShare(Base):
    """Stable public capability and self-contained public transcript snapshot."""

    __tablename__ = "chat_shares"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    snapshot_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="1"
    )
    messages: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[ChatSession] = relationship(back_populates="share")
    shared_artifacts: Mapped[list["ChatSharedArtifact"]] = relationship(
        back_populates="share", cascade="all, delete-orphan", passive_deletes=True
    )
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(messages) = 'array'",
            name="chat_shares_messages_array_check",
        ),
    )


class ChatSharedArtifact(Base):
    """Share-scoped immutable PNG/PDF snapshot with an unrelated capability."""

    __tablename__ = "chat_shared_artifacts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    share_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_shares.id", ondelete="CASCADE"),
        nullable=False,
    )
    capability_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    source_version_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    identifier: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    canvas: Mapped[dict] = mapped_column(JSONB, nullable=False)
    gate_status: Mapped[str] = mapped_column(String(16), nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    preview_path: Mapped[str] = mapped_column(String(300), nullable=False)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    share: Mapped[ChatShare] = relationship(back_populates="shared_artifacts")
    __table_args__ = (
        CheckConstraint(
            "gate_status IN ('passed','warnings','failed')",
            name="chat_shared_artifacts_gate_check",
        ),
        CheckConstraint(
            "gate_status <> 'failed' OR pdf_path IS NULL",
            name="chat_shared_artifacts_failed_pdf_check",
        ),
        UniqueConstraint(
            "share_id", "identifier", name="uq_chat_shared_artifacts_identifier"
        ),
        Index("idx_chat_shared_artifacts_share", "share_id"),
    )


class ChatFeedback(Base):
    """One end-user thumbs rating for a completed assistant response.

    Feedback used to be forwarded straight to the trace store and was lost
    whenever that store changed; the catalog database is now the record and
    the trace export is a best-effort mirror.
    """

    __tablename__ = "chat_feedback"

    assistant_message_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    exported_to: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    exported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_chat_feedback_created_at", "created_at"),
        Index("idx_chat_feedback_session_id", "session_id"),
    )


class ChatTurnLatency(Base):
    """Content-free latency telemetry for one admitted staging chat turn."""

    __tablename__ = "chat_turn_latency"

    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    traffic_class: Mapped[str] = mapped_column(String(24), nullable=False)
    execution_backend: Mapped[str] = mapped_column(String(24), nullable=False)
    agent_harness: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="claude"
    )
    pi_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_semantic_event_class: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True
    )
    acquisition_outcome: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    model_route: Mapped[str] = mapped_column(String(255), nullable=False)
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sandbox_image_version: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    worker_contract_version: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    pwc_cli_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    system_prompt_sha256: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    qualification_run_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    qualification_scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chat_qualification_scopes.id",
            ondelete="SET NULL",
            name="chat_turn_latency_qualification_scope_fkey",
        ),
        nullable=True,
    )
    qualification_profile: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    qualification_workload: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True
    )
    qualification_scenario: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    sandbox_cpu_request: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 3), nullable=True
    )
    sandbox_memory_request_mib: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    estimated_active_cost_usd: Mapped[Optional[float]] = mapped_column(
        Numeric(14, 8), nullable=True
    )

    acquisition_started_ms: Mapped[Optional[int]] = mapped_column(Integer)
    pool_lookup_completed_ms: Mapped[Optional[int]] = mapped_column(Integer)
    modal_sandbox_created_ms: Mapped[Optional[int]] = mapped_column(Integer)
    worker_control_ready_ms: Mapped[Optional[int]] = mapped_column(Integer)
    session_assignment_completed_ms: Mapped[Optional[int]] = mapped_column(Integer)
    broker_capability_installed_ms: Mapped[Optional[int]] = mapped_column(Integer)
    sdk_query_dispatched_ms: Mapped[Optional[int]] = mapped_column(Integer)
    provider_gateway_received_ms: Mapped[Optional[int]] = mapped_column(Integer)
    control_connection_ms: Mapped[Optional[int]] = mapped_column(Integer)
    agent_spawn_ms: Mapped[Optional[int]] = mapped_column(Integer)
    agent_startup_ready_ms: Mapped[Optional[int]] = mapped_column(Integer)
    session_bind_restore_ms: Mapped[Optional[int]] = mapped_column(Integer)
    resource_loading_ms: Mapped[Optional[int]] = mapped_column(Integer)
    agent_session_ready_ms: Mapped[Optional[int]] = mapped_column(Integer)
    upstream_response_headers_ms: Mapped[Optional[int]] = mapped_column(Integer)
    upstream_first_body_byte_ms: Mapped[Optional[int]] = mapped_column(Integer)
    first_worker_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    first_application_sse_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    first_semantic_event_ms: Mapped[Optional[int]] = mapped_column(Integer)
    pool_miss_reason: Mapped[Optional[str]] = mapped_column(String(32))
    session_reuse_cohort: Mapped[Optional[str]] = mapped_column(String(32))
    failure_stage: Mapped[Optional[str]] = mapped_column(String(32))
    failure_class: Mapped[Optional[str]] = mapped_column(String(128))
    attempt_kind: Mapped[Optional[str]] = mapped_column(String(16))
    retry_overhead_ms: Mapped[Optional[int]] = mapped_column(Integer)
    total_ms: Mapped[Optional[int]] = mapped_column(Integer)

    browser_stream_start_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_first_visible_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_first_reasoning_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_first_tool_call_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_first_answer_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_terminal_classification: Mapped[Optional[str]] = mapped_column(
        String(24), nullable=True
    )
    terminal_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="running"
    )
    admitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "traffic_class IN ('new_chat','followup')",
            name="chat_turn_latency_traffic_class_check",
        ),
        CheckConstraint(
            "execution_backend IN ('local_mcp','modal_cli','external_pi')",
            name="chat_turn_latency_backend_check",
        ),
        CheckConstraint(
            "agent_harness IN ('claude','pi')",
            name="chat_turn_latency_agent_harness_check",
        ),
        CheckConstraint(
            "first_semantic_event_class IS NULL OR "
            "first_semantic_event_class IN ('reasoning','tool','answer')",
            name="chat_turn_latency_semantic_event_check",
        ),
        CheckConstraint(
            "acquisition_outcome IN "
            "('pending','created','reused_session','pool_hit','pool_miss')",
            name="chat_turn_latency_acquisition_check",
        ),
        CheckConstraint(
            "terminal_status IN ('running','complete','stopped','error','interrupted')",
            name="chat_turn_latency_terminal_check",
        ),
        CheckConstraint(
            "browser_terminal_classification IS NULL OR "
            "browser_terminal_classification IN "
            "('complete','stopped','error','network_error','aborted')",
            name="chat_turn_latency_browser_terminal_check",
        ),
        CheckConstraint(
            "qualification_scenario IS NULL OR qualification_scenario IN "
            "('focused_latency','reliability','clean_cancel','forced_failure')",
            name="chat_turn_latency_qualification_scenario_check",
        ),
        CheckConstraint(
            "qualification_profile IS NULL OR qualification_profile IN "
            "('32-functional-turns','100-immediate-admission')",
            name="chat_turn_latency_qualification_profile_check",
        ),
        CheckConstraint(
            "qualification_workload IS NULL OR qualification_workload IN "
            "('no_tool','read','bash')",
            name="chat_turn_latency_qualification_workload_check",
        ),
        CheckConstraint(
            "attempt_kind IS NULL OR attempt_kind IN ('pool','reused','direct')",
            name="chat_turn_latency_attempt_kind_check",
        ),
        CheckConstraint(
            "retry_overhead_ms IS NULL OR retry_overhead_ms BETWEEN 0 AND 3600000",
            name="chat_turn_latency_retry_overhead_check",
        ),
        Index("idx_chat_turn_latency_admitted", "admitted_at", "turn_id"),
        Index("idx_chat_turn_latency_session", "chat_session_id"),
        Index(
            "idx_chat_turn_latency_qualification_scope",
            "qualification_scope_id",
            "admitted_at",
        ),
    )


class ChatTurnCapability(Base):
    """Short-lived authorization and encrypted provider credential."""

    __tablename__ = "chat_turn_capabilities"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_harness: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="claude"
    )
    sdk_session_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    owner_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="high"
    )
    provider_credential_revision: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    provider_error_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    artifact_paper_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    provider_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    gateway_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    catalog_search_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    web_search_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    web_search_failed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    hf_catalog_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    hf_recursive_list_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "agent_harness IN ('claude','pi')",
            name="chat_turn_capabilities_agent_harness_check",
        ),
        CheckConstraint(
            "provider_mode IS NULL OR provider_mode IN "
            "('huggingface','openrouter_funded','openrouter_byok','openai_funded')",
            name="chat_turn_capabilities_provider_mode_check",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low','medium','high','max')",
            name="chat_turn_capabilities_reasoning_effort_check",
        ),
        Index(
            "idx_chat_turn_capabilities_scope",
            "chat_session_id",
            "turn_id",
            "expires_at",
        ),
    )
