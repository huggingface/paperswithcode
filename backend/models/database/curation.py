"""Paper, benchmark, trending-model, and release-radar curation persistence models."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base

if TYPE_CHECKING:
    from backend.models.database.papers import Paper


class TrendingModelCandidate(Base):
    """Latest discovery and curation state for one Hugging Face model repo."""

    __tablename__ = "trending_model_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    readme_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    readme_revision: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="discovered", server_default="discovered"
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    featured_publisher: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    model_release_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("model_releases.id", ondelete="SET NULL"),
        nullable=True,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('discovered', 'rejected', 'queued', 'resolving', 'resolved', 'failed')",
            name="trending_model_candidates_status_check",
        ),
        Index("idx_trending_model_candidates_status", "status", "last_seen_at"),
        Index("idx_trending_model_candidates_release", "model_release_id"),
    )


class TrendingModelCurationState(Base):
    """Durable rollout gate for autonomous trending-model curation."""

    __tablename__ = "trending_model_curation_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    discovery_dry_run_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    canary_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    canary_candidate_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    canary_released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ModelReleaseSignal(Base):
    """One model release the release radar reported with no covering paper.

    ``signal_key`` is the normalized lab and model name, so repeated radar
    runs update one row. A ``resolve-model-paper`` job scoped to the signal
    finds the lab's own announcement and resolves it to a paper.
    """

    __tablename__ = "model_release_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    signal_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    lab: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    lead_url: Mapped[str] = mapped_column(Text, nullable=False)
    # Feed URL of a vendor source, or "web-search".
    source: Mapped[str] = mapped_column(Text, nullable=False)
    # The lead is the lab's own page (a vendor feed, or a web hit the
    # extractor cited as official), not a news article.
    lead_is_official: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    published: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    sightings: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="discovered", server_default="discovered"
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('discovered', 'queued', 'resolving', 'resolved', 'rejected', 'failed')",
            name="model_release_signals_status_check",
        ),
        Index("idx_model_release_signals_status", "status", "last_seen_at"),
    )


class PaperCurationBootstrapBundle(Base):
    """One immutable remote-worker bootstrap snapshot, shared by every job bound to it."""

    __tablename__ = "paper_curation_bootstrap_bundles"

    # SHA-256 of the bundle's canonical JSON (sorted keys, compact separators).
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    bundle: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PaperCurationJob(Base):
    """Durable request for a remote Codex paper-curation Job."""

    __tablename__ = "paper_curation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=True
    )
    candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trending_model_candidates.id", ondelete="CASCADE"),
        nullable=True,
    )
    benchmark_candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("benchmark_curation_candidates.id", ondelete="CASCADE"),
        nullable=True,
    )
    release_signal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_release_signals.id", ondelete="CASCADE"),
        nullable=True,
    )
    paper_route: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    paper_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Candidate ids a review-benchmark-gaps job was served; it must decide each.
    review_scope: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "paper_curation_workflows.id",
            name="fk_paper_curation_jobs_parent_workflow",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    trigger: Mapped[str] = mapped_column(
        String(24), nullable=False, default="admin", server_default="admin"
    )
    cohort_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    policy_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="admin-v1", server_default="admin-v1"
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    repository_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    skill_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prompt_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reasoning_effort: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    codex_cli_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    validator_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trace_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    trace_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trace_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trace_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proposal: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    bootstrap_bundle_sha256: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("paper_curation_bootstrap_bundles.sha256"),
        nullable=True,
    )
    stored_bootstrap_bundle: Mapped[Optional["PaperCurationBootstrapBundle"]] = (
        relationship()
    )
    validation_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    mutation_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    url_candidates: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    taxonomy_query_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    leaderboard_query_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    retry_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_curation_jobs.id"), nullable=True
    )
    audit_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unreviewed", server_default="unreviewed"
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    hf_job_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True
    )
    callback_token_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    thumbnail_status: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    thumbnail_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    thumbnail_claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    thumbnail_finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    thumbnail_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_previous_width: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    thumbnail_previous_height: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    thumbnail_generated_width: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    thumbnail_generated_height: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    thumbnail_warnings: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    thumbnail_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    paper: Mapped["Paper"] = relationship("Paper")
    parent_workflow: Mapped[Optional["PaperCurationWorkflow"]] = relationship(
        "PaperCurationWorkflow",
        back_populates="jobs",
        foreign_keys=[parent_workflow_id],
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('add-evals', 'enrich-paper', 'resolve-model-paper', "
            "'review-benchmark-gaps', 'add-benchmark')",
            name="paper_curation_jobs_kind_check",
        ),
        CheckConstraint(
            "(kind = 'resolve-model-paper' AND paper_id IS NULL "
            "AND benchmark_candidate_id IS NULL "
            "AND (candidate_id IS NULL) <> (release_signal_id IS NULL)) "
            "OR (kind = 'add-benchmark' AND benchmark_candidate_id IS NOT NULL "
            "AND paper_id IS NULL AND candidate_id IS NULL "
            "AND release_signal_id IS NULL) "
            "OR (kind = 'review-benchmark-gaps' AND paper_id IS NULL "
            "AND candidate_id IS NULL AND benchmark_candidate_id IS NULL "
            "AND release_signal_id IS NULL) "
            "OR (kind IN ('add-evals', 'enrich-paper') AND paper_id IS NOT NULL "
            "AND candidate_id IS NULL AND benchmark_candidate_id IS NULL "
            "AND release_signal_id IS NULL)",
            name="paper_curation_jobs_scope_check",
        ),
        CheckConstraint(
            "status IN ('queued', 'dispatching', 'running', 'completed', 'failed', "
            "'canceled', 'awaiting_markdown')",
            name="paper_curation_jobs_status_check",
        ),
        CheckConstraint(
            "thumbnail_status IS NULL OR thumbnail_status IN ('queued', 'processing', 'succeeded', 'failed')",
            name="paper_curation_jobs_thumbnail_status_check",
        ),
        CheckConstraint(
            "trigger IN ('admin', 'hf-daily-cron', 'hf-trending-cron', "
            "'benchmark-promotion', 'benchmark-gap-cron', 'model-release-radar')",
            name="paper_curation_jobs_trigger_check",
        ),
        Index("idx_paper_curation_jobs_queue", "status", "created_at"),
        Index("idx_paper_curation_jobs_paper", "paper_id", "created_at"),
        Index("idx_paper_curation_jobs_candidate", "candidate_id", "created_at"),
        Index("idx_paper_curation_jobs_workflow", "parent_workflow_id", "created_at"),
        Index(
            "idx_paper_curation_jobs_benchmark_candidate",
            "benchmark_candidate_id",
            "created_at",
        ),
        Index(
            "idx_paper_curation_jobs_dispatch",
            "status",
            "priority",
            "cohort_date",
            "created_at",
        ),
        Index(
            "uq_active_scheduled_paper_curation_stage",
            "paper_id",
            "kind",
            "policy_version",
            unique=True,
            postgresql_where=text(
                "trigger <> 'admin' AND status IN ('queued', 'dispatching', 'running')"
            ),
        ),
        Index(
            "idx_paper_curation_jobs_thumbnail_queue",
            "thumbnail_status",
            "thumbnail_requested_at",
        ),
        Index(
            "uq_active_trending_model_resolution",
            "candidate_id",
            "policy_version",
            unique=True,
            postgresql_where=text(
                "kind = 'resolve-model-paper' AND status IN ('queued', 'dispatching', 'running')"
            ),
            sqlite_where=text(
                "kind = 'resolve-model-paper' AND status IN ('queued', 'dispatching', 'running')"
            ),
        ),
        Index(
            "idx_paper_curation_jobs_release_signal",
            "release_signal_id",
            "created_at",
        ),
        Index(
            "uq_active_release_signal_resolution",
            "release_signal_id",
            unique=True,
            postgresql_where=text(
                "kind = 'resolve-model-paper' AND status IN ('queued', 'dispatching', 'running')"
            ),
            sqlite_where=text(
                "kind = 'resolve-model-paper' AND status IN ('queued', 'dispatching', 'running')"
            ),
        ),
        Index(
            "uq_active_benchmark_candidate_job",
            "benchmark_candidate_id",
            unique=True,
            postgresql_where=text(
                "kind = 'add-benchmark' AND status IN ('queued', 'dispatching', 'running')"
            ),
            sqlite_where=text(
                "kind = 'add-benchmark' AND status IN ('queued', 'dispatching', 'running')"
            ),
        ),
        Index(
            "uq_active_benchmark_gap_review",
            "kind",
            unique=True,
            postgresql_where=text(
                "kind = 'review-benchmark-gaps' "
                "AND status IN ('queued', 'dispatching', 'running')"
            ),
            sqlite_where=text(
                "kind = 'review-benchmark-gaps' "
                "AND status IN ('queued', 'dispatching', 'running')"
            ),
        ),
    )


class PaperCurationWorkflow(Base):
    """One durable two-stage scheduled curation workflow for a paper."""

    __tablename__ = "paper_curation_workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source_candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trending_model_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_revision: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    cohort_date: Mapped[date] = mapped_column(Date, nullable=False)
    cohort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unreviewed"
    )
    enrich_satisfied_by_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "paper_curation_jobs.id",
            name="fk_paper_curation_workflows_enrich_satisfied_by_job",
        ),
        nullable=True,
    )
    evals_satisfied_by_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "paper_curation_jobs.id",
            name="fk_paper_curation_workflows_evals_satisfied_by_job",
        ),
        nullable=True,
    )
    dependency_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    deferred_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    paper: Mapped["Paper"] = relationship("Paper")
    jobs: Mapped[List[PaperCurationJob]] = relationship(
        "PaperCurationJob",
        back_populates="parent_workflow",
        foreign_keys=[PaperCurationJob.parent_workflow_id],
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'partial', 'deferred', 'canceled', 'satisfied')",
            name="paper_curation_workflows_status_check",
        ),
        Index(
            "idx_paper_curation_workflows_queue",
            "status",
            "cohort_date",
            "cohort_order",
        ),
        Index(
            "uq_active_paper_curation_workflow",
            "paper_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'deferred')"),
        ),
        Index(
            "uq_paper_curation_workflow_candidate_revision",
            "source_candidate_id",
            "source_revision",
            "policy_version",
            unique=True,
            postgresql_where=text("source_candidate_id IS NOT NULL"),
        ),
    )


class BenchmarkCurationCandidate(Base):
    """Queryable aggregate of benchmark gaps reported by scheduled add-evals.

    Status moves from ``candidate`` through the daily review to ``approved``,
    ``rejected``, or ``merged``; an approved candidate becomes ``promoted``
    once its benchmark is configured.
    """

    __tablename__ = "benchmark_curation_candidates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    identity_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    gap_type: Mapped[str] = mapped_column(String(48), nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="candidate")
    distinct_paper_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    confidence: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    promoted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Paper count when last rejected; new evidence doubling it reopens review.
    reviewed_paper_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deferred_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    merged_into_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("benchmark_curation_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Catalog rows the creation job used or created, for audit and rollback.
    resolution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'approved', 'promoted', 'rejected', 'merged')",
            name="benchmark_curation_candidates_status_check",
        ),
        Index(
            "idx_benchmark_curation_candidates_review",
            "status",
            "distinct_paper_count",
        ),
    )


class BenchmarkCurationEvidence(Base):
    __tablename__ = "benchmark_curation_evidence"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("benchmark_curation_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paper_curation_jobs.id"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "paper_id", "job_id", name="uq_benchmark_gap_evidence_job"
        ),
        Index("idx_benchmark_curation_evidence_paper", "paper_id", "candidate_id"),
    )


class PaperCurationSchedulerState(Base):
    __tablename__ = "paper_curation_scheduler_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    dispatch_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pause_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pause_condition: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    canary_released: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    first_enabled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_trace_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    consecutive_apply_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
