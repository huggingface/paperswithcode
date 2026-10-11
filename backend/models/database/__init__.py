"""
SQLAlchemy database models.

These models represent the database schema and provide ORM functionality
for interacting with the PostgreSQL database. Models are being moved into
bounded modules in this package; this module re-exports every model so
``from backend.models.database import X`` keeps working.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base
from backend.models.database.papers import (
    Paper,
    Author,
    PaperAuthor,
    PaperTask,
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
    PaperDataset,
    PaperRelation,
)
from backend.models.database.resources import (
    Repository,
    RepositoryStarHistory,
    HfArtifact,
    PaperHfArtifact,
    ModelRelease,
    ModelReleaseArtifact,
    ModelProviderAlias,
    ProjectPage,
    PaperProjectPage,
    PaperRepository,
)
from backend.models.database.evaluations import (
    Dataset,
    Evaluation,
    EvaluationBadgeTombstone,
    Metric,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.models.database.chat import (
    ChatSession,
    ChatTurnJob,
    ChatTurnAdmissionBudget,
    ChatTurnReservation,
    ChatTurnEventChunk,
    ChatMessageRecord,
    ChatShare,
    ChatSharedArtifact,
    ChatFeedback,
    ChatTurnLatency,
    ChatTurnCapability,
)
from backend.models.database.chat_artifacts import (
    ChatArtifact,
    ChatArtifactVersion,
    ChatLatexPaperVersion,
    ChatLatexPaperFigureBlob,
    ChatLatexPaperFigureReference,
    ChatLatexPaperStorageCleanup,
)
from backend.models.database.chat_sandbox import (
    ChatExecutorTransportCircuit,
    ChatExecutorTransportAlert,
    ChatSandboxLease,
    ChatExternalWorker,
    ChatExternalWorkerReservation,
    ChatExecutorManifest,
    ChatExecutorCell,
    ChatExecutorShard,
    ChatExecutorRegistration,
    ChatExecutorNonce,
    ChatExecutorClaim,
    ChatExecutorKeyRevocation,
    ChatExecutorRollbackAudit,
    ChatQualificationScope,
    ChatQualificationEvidenceEvent,
    ChatSandboxPool,
    ChatSandboxComputeInterval,
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatReliabilityBaseline,
)
from backend.models.database.chat_providers import (
    ChatTitleBudgetState,
    ChatTitleProviderCall,
    ChatTitleBudgetEvent,
    ChatWebSearchBudgetState,
    ChatWebSearchCircuitEvent,
    ChatWebSearchOwnerUsage,
    ChatOpenRouterCredential,
    ChatOpenRouterMonthlyUsage,
    ChatOpenRouterProviderCall,
    ChatOpenAIMonthlyUsage,
    ChatOpenAIProviderCall,
    ChatOpenRouterCredentialAudit,
    ChatProviderRuntimeState,
)
from backend.models.database.chat_transcripts import (
    ChatSDKTranscriptEntry,
    ChatSDKSessionSummary,
    ChatPiSession,
    ChatPiTranscriptEntry,
    ChatPiPreparedFork,
    ChatHarnessAssignmentAudit,
)
from backend.models.database.curation import (
    TrendingModelCandidate,
    TrendingModelCurationState,
    PaperCurationJob,
    PaperCurationWorkflow,
    BenchmarkCurationCandidate,
    BenchmarkCurationEvidence,
    PaperCurationSchedulerState,
)
from backend.models.database.autonomous import (
    AutonomousSubmissionClaim,
    AutonomousOperatorState,
    AutonomousExecutionIntent,
    AutonomousRun,
    AutonomousBudgetReservation,
    AutonomousAction,
    AutonomousAlertDelivery,
    AutonomousReleaseConsumption,
    AutonomousControlEvent,
    AutonomousRepairLease,
    AutonomousIncidentAttempt,
)


class Area(Base):
    """
    Research areas (Vision, Video, Language, Audio, General, Other, etc.).
    """

    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="area")

    def __repr__(self) -> str:
        return f"<Area(id={self.id}, name='{self.name}')>"


class Task(Base):
    """
    AI tasks with hierarchical structure.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_trends: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    slug: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Hierarchical structure
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("tasks.id"), nullable=True
    )
    area_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("areas.id"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata columns
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_credit: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # DB-backed hero image. `image_data` holds the raw bytes and is deferred so
    # list queries never load the (potentially large) blob; `image_mime_type`
    # is small, always loaded, and doubles as the "has a DB image" flag the API
    # layer checks to build the `/api/v1/tasks/{slug}/image` URL.
    image_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    useful_leaderboards: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    parent: Mapped[Optional["Task"]] = relationship(
        "Task", remote_side=[id], back_populates="children"
    )
    children: Mapped[List["Task"]] = relationship(
        "Task", back_populates="parent", overlaps="parent"
    )
    area: Mapped[Optional[Area]] = relationship("Area", back_populates="tasks")
    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_tasks", back_populates="tasks"
    )
    datasets: Mapped[List["Dataset"]] = relationship(
        "Dataset", secondary="task_datasets", back_populates="tasks"
    )
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation", back_populates="task"
    )

    # Indexes
    __table_args__ = (
        Index("idx_tasks_parent_id", "parent_id"),
        Index("idx_tasks_area_id", "area_id"),
        Index("idx_tasks_slug", "slug"),
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, name='{self.name}', level={self.level})>"


class Method(Base):
    """
    AI methods and techniques.
    """

    __tablename__ = "methods"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
    )
    slug: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Area assignment (methods belong to one area)
    area_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("areas.id"), nullable=True
    )

    introduced_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    code_snippet_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_credit: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # DB-backed figure (see Task.image_data for the deferred/flag rationale).
    image_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    collection_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    collection_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collection_parent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    area: Mapped[Optional[Area]] = relationship("Area")
    source_paper: Mapped[Optional["Paper"]] = relationship("Paper")
    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_methods", back_populates="methods"
    )

    __table_args__ = (Index("idx_methods_source_paper_id", "source_paper_id"),)

    def __repr__(self) -> str:
        return f"<Method(id={self.id}, name='{self.name}')>"


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


# Junction tables for many-to-many relationships


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


class Conference(Base):
    """Normalized conference metadata (CVPR, ICCV, NeurIPS, etc.)."""

    __tablename__ = "conferences"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    short_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    venue: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_credit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # DB-backed hero image (see Task.image_data for the deferred/flag rationale).
    image_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_conferences", back_populates="conferences"
    )
    deadlines: Mapped[List["ConferenceDeadline"]] = relationship(
        "ConferenceDeadline",
        back_populates="conference",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_conferences_slug", "slug"),
        Index("idx_conferences_year", "year"),
    )

    def __repr__(self) -> str:
        return f"<Conference(id={self.id}, slug='{self.slug}', name='{self.name}')>"


class ConferenceDeadline(Base):
    """A submission/abstract/rebuttal deadline for a conference instance."""

    __tablename__ = "conference_deadlines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conference_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conferences.id", ondelete="CASCADE"),
        nullable=False,
    )
    deadline_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conference: Mapped["Conference"] = relationship(
        "Conference", back_populates="deadlines"
    )

    __table_args__ = (
        Index("idx_conference_deadlines_conference_id", "conference_id"),
        Index("idx_conference_deadlines_deadline_at", "deadline_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ConferenceDeadline(id={self.id}, "
            f"conference_id={self.conference_id}, type='{self.deadline_type}')>"
        )


class PaperConference(Base):
    """Junction table linking papers to conferences."""

    __tablename__ = "paper_conferences"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    conference_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conferences.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    award: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("idx_paper_conferences_conference_id", "conference_id"),
        Index("idx_paper_conferences_paper_id", "paper_id"),
        Index(
            "idx_paper_conferences_award",
            "conference_id",
            "award",
            postgresql_where=text("award IS NOT NULL"),
        ),
    )


class Organization(Base):
    """Normalized organization metadata (NVIDIA, Google, Meta, etc.).

    Organizations are sourced primarily from Hugging Face org profiles
    (``hf_url``) and used to tag papers by the lab/company behind them.
    """

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    hf_slug: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    logo_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    logo_mime_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    logo_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    display_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_hf_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hf_paper_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    trending_score_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_organizations", back_populates="organizations"
    )

    trending_history: Mapped[List["OrganizationTrendingHistory"]] = relationship(
        "OrganizationTrendingHistory",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_organizations_slug", "slug"),
        Index(
            "uq_organizations_hf_slug",
            "hf_slug",
            unique=True,
            postgresql_where=text("hf_slug IS NOT NULL"),
        ),
        Index(
            "idx_organizations_featured_trending",
            "is_featured",
            text("trending_score DESC"),
        ),
        Index("idx_organizations_featured_order", "is_featured", "display_order"),
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug='{self.slug}', name='{self.name}')>"


class PaperOrganization(Base):
    """Junction table linking papers to organizations."""

    __tablename__ = "paper_organizations"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    added_by_hf_subject: Mapped[Optional[str]] = mapped_column(String(255))
    added_by_hf_username: Mapped[Optional[str]] = mapped_column(String(255))

    __table_args__ = (
        Index("idx_paper_organizations_organization_id", "organization_id"),
        Index("idx_paper_organizations_paper_id", "paper_id"),
    )


class OrganizationTrendingHistory(Base):
    """One raw daily organization-momentum snapshot."""

    __tablename__ = "organization_trending_history"

    organization_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    raw_score: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="trending_history"
    )


class TaskSisterTask(Base):
    """Explicit, ordered sister-task relationships for a task page.

    ``task_id`` is the task whose page renders the sister list;
    ``sister_task_id`` is a task shown in that page's sister-task sidebar,
    sorted by ``display_order``. The relation is directed and not
    automatically symmetric. A self-edge is forbidden via CHECK constraint.
    """

    __tablename__ = "task_sister_tasks"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    sister_task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "task_id <> sister_task_id",
            name="task_sister_tasks_no_self_link",
        ),
        Index("idx_task_sister_tasks_task_id", "task_id"),
        Index("idx_task_sister_tasks_sister_task_id", "sister_task_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<TaskSisterTask(task_id={self.task_id}, "
            f"sister_task_id={self.sister_task_id}, "
            f"display_order={self.display_order})>"
        )


class TaskRecommendedFramework(Base):
    """Ordered repositories recommended as starting points for a task."""

    __tablename__ = "task_recommended_frameworks"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_task_recommended_frameworks_task_id", "task_id"),
        Index(
            "idx_task_recommended_frameworks_repository_id",
            "repository_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TaskRecommendedFramework(task_id={self.task_id}, "
            f"repository_id={self.repository_id}, "
            f"display_order={self.display_order})>"
        )


class FrameworkDomain(Base):
    """Top-level grouping on the framework catalogue."""

    __tablename__ = "framework_domains"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FrameworkCategory(Base):
    """Ordered framework category within a domain."""

    __tablename__ = "framework_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    domain_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("framework_domains.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    guide_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    guide_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "domain_id", "slug", name="framework_categories_domain_slug_key"
        ),
        Index("idx_framework_categories_domain_id", "domain_id"),
    )


class Framework(Base):
    """First-class software framework with canonical paper and repository."""

    __tablename__ = "frameworks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("framework_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    repository_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    introducing_paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    when_to_use: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    docs_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_frameworks_category_id", "category_id"),
        Index("idx_frameworks_repository_id", "repository_id"),
        Index("idx_frameworks_introducing_paper_id", "introducing_paper_id"),
    )


class FrameworkPlatform(Base):
    """Hardware platform supported by a framework."""

    __tablename__ = "framework_platforms"

    framework_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("frameworks.id", ondelete="CASCADE"), primary_key=True
    )
    platform: Mapped[str] = mapped_column(String(20), primary_key=True)

    __table_args__ = (
        CheckConstraint(
            "platform IN ('gpu', 'cpu', 'apple')",
            name="framework_platforms_platform_check",
        ),
    )


class TaskFramework(Base):
    """Ordered first-class framework recommendations for a task."""

    __tablename__ = "task_frameworks"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    framework_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("frameworks.id", ondelete="CASCADE"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_task_frameworks_task_id", "task_id"),
        Index("idx_task_frameworks_framework_id", "framework_id"),
    )


class UserBookmark(Base):
    """Per-HF-user paper bookmarks.

    Keyed on the HF username carried in the ``pwc_session`` JWT (see
    ``backend.routers.auth``). Rows are removed via ``ON DELETE CASCADE`` when
    the underlying paper is deleted.
    """

    __tablename__ = "user_bookmarks"

    hf_username: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False
    )
    paper_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("papers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_user_bookmarks_user", "hf_username"),
        Index("idx_user_bookmarks_paper", "paper_id"),
    )

    def __repr__(self) -> str:
        return f"<UserBookmark(hf_username='{self.hf_username}', paper_id={self.paper_id})>"


class UserPreference(Base):
    """Per-HF-user account preferences.

    Keyed on the lowercased HF username carried in the ``pwc_session`` JWT (see
    ``backend.routers.auth``). Written exclusively through the
    ``/api/v1/me/preferences`` endpoints which require the session cookie.
    """

    __tablename__ = "user_preferences"

    hf_username: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False
    )
    # When True, the user hides closed-source model rows (Evaluation.is_open is
    # False) on benchmark leaderboards and paper evaluation tables.
    hide_closed_source_evals: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<UserPreference(hf_username='{self.hf_username}', "
            f"hide_closed_source_evals={self.hide_closed_source_evals})>"
        )


class StagingAccessRequest(Base):
    """Verified Hugging Face accounts requesting contributor access."""

    __tablename__ = "staging_access_requests"

    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    hf_username: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="staging_access_requests_status_check",
        ),
        CheckConstraint(
            "email IS NULL OR email_verified",
            name="staging_access_requests_verified_email_check",
        ),
        Index("idx_staging_access_requests_status_created", "status", "created_at"),
    )


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
            "edit_type IN ('tasks', 'methods', 'evaluations', 'repositories', 'project_pages', 'source_url', 'hf_artifacts', 'organizations', 'new_task', 'new_method', 'new_benchmark', 'new_metric', 'new_conference', 'new_external_paper')",
            name="pending_paper_edits_edit_type_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="pending_paper_edits_status_check",
        ),
        CheckConstraint(
            "reviewed_by_kind IS NULL OR reviewed_by_kind IN ('human', 'codex')",
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


class UserProfile(Base):
    """Stable Hugging Face identity and its current public username."""

    __tablename__ = "user_profiles"

    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    current_username: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    is_submission_suspended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    suspension_reason: Mapped[Optional[str]] = mapped_column(Text)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suspended_by_hf_subject: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserProfileAlias(Base):
    __tablename__ = "user_profile_aliases"

    alias: Mapped[str] = mapped_column(String(255), primary_key=True)
    hf_subject: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("user_profiles.hf_subject", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_user_profile_aliases_subject", "hf_subject"),)


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


__all__ = [
    "Base",
    "ChatSession",
    "ChatTurnJob",
    "ChatTurnAdmissionBudget",
    "ChatTurnReservation",
    "ChatTurnEventChunk",
    "ChatMessageRecord",
    "ChatShare",
    "ChatSharedArtifact",
    "ChatFeedback",
    "ChatTurnLatency",
    "ChatTurnCapability",
    "ChatArtifact",
    "ChatArtifactVersion",
    "ChatLatexPaperVersion",
    "ChatLatexPaperFigureBlob",
    "ChatLatexPaperFigureReference",
    "ChatLatexPaperStorageCleanup",
    "ChatExecutorTransportCircuit",
    "ChatExecutorTransportAlert",
    "ChatSandboxLease",
    "ChatExternalWorker",
    "ChatExternalWorkerReservation",
    "ChatExecutorManifest",
    "ChatExecutorCell",
    "ChatExecutorShard",
    "ChatExecutorRegistration",
    "ChatExecutorNonce",
    "ChatExecutorClaim",
    "ChatExecutorKeyRevocation",
    "ChatExecutorRollbackAudit",
    "ChatQualificationScope",
    "ChatQualificationEvidenceEvent",
    "ChatSandboxPool",
    "ChatSandboxComputeInterval",
    "ChatSandboxBudgetState",
    "ChatSandboxCircuitEvent",
    "ChatReliabilityBaseline",
    "ChatTitleBudgetState",
    "ChatTitleProviderCall",
    "ChatTitleBudgetEvent",
    "ChatWebSearchBudgetState",
    "ChatWebSearchCircuitEvent",
    "ChatWebSearchOwnerUsage",
    "ChatOpenRouterCredential",
    "ChatOpenRouterMonthlyUsage",
    "ChatOpenRouterProviderCall",
    "ChatOpenAIMonthlyUsage",
    "ChatOpenAIProviderCall",
    "ChatOpenRouterCredentialAudit",
    "ChatProviderRuntimeState",
    "ChatSDKTranscriptEntry",
    "ChatSDKSessionSummary",
    "ChatPiSession",
    "ChatPiTranscriptEntry",
    "ChatPiPreparedFork",
    "ChatHarnessAssignmentAudit",
    "TrendingModelCandidate",
    "TrendingModelCurationState",
    "PaperCurationJob",
    "PaperCurationWorkflow",
    "BenchmarkCurationCandidate",
    "BenchmarkCurationEvidence",
    "PaperCurationSchedulerState",
    "AutonomousSubmissionClaim",
    "AutonomousOperatorState",
    "AutonomousExecutionIntent",
    "AutonomousRun",
    "AutonomousBudgetReservation",
    "AutonomousAction",
    "AutonomousAlertDelivery",
    "AutonomousReleaseConsumption",
    "AutonomousControlEvent",
    "AutonomousRepairLease",
    "AutonomousIncidentAttempt",
    "Paper",
    "Author",
    "Area",
    "Task",
    "Method",
    "Dataset",
    "Repository",
    "RepositoryStarHistory",
    "HfArtifact",
    "PaperHfArtifact",
    "ModelRelease",
    "ModelReleaseArtifact",
    "ModelProviderAlias",
    "ProjectPage",
    "PaperProjectPage",
    "Evaluation",
    "EvaluationBadgeTombstone",
    "CatalogMutationEvent",
    "CatalogMutationIdempotency",
    "CatalogAuditReadProgress",
    "Metric",
    "PaperAuthor",
    "PaperTask",
    "PaperMethod",
    "PaperMethodEvidence",
    "PaperMethodExclusion",
    "MethodReferenceBackfillMonth",
    "MethodKeywordBackfillRun",
    "PaperDataset",
    "PaperRepository",
    "Conference",
    "ConferenceDeadline",
    "PaperConference",
    "Organization",
    "PaperOrganization",
    "OrganizationTrendingHistory",
    "PaperRelation",
    "TaskSisterTask",
    "TaskRecommendedFramework",
    "FrameworkDomain",
    "FrameworkCategory",
    "Framework",
    "FrameworkPlatform",
    "TaskFramework",
    "TaskDataset",
    "TaskDatasetMetric",
    "UserBookmark",
    "UserPreference",
    "StagingAccessRequest",
    "PendingPaperEdit",
    "UserProfile",
    "UserProfileAlias",
    "PaperEditAccount",
    "PaperEditAuthorization",
]
