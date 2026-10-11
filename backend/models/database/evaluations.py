"""Benchmark dataset, metric, and evaluation persistence models."""

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base

if TYPE_CHECKING:
    from backend.models.database.papers import Paper
    from backend.models.database.taxonomy import Task


class Dataset(Base):
    """
    Benchmark datasets.
    """

    __tablename__ = "datasets"

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
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Additional metadata from PapersWithCode
    short_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    homepage: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Dataset hierarchy and variants
    parent_dataset_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    variant_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    split_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Image/media URLs
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verified_image_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    # Paper reference (the paper that introduced this dataset)
    introducing_paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    introducing_paper_title: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    paper_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Licensing information
    license_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    license_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Introduction date/year
    introduced_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    introduced_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # JSONB fields for arrays
    modalities: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # e.g., ["Images", "Videos"]
    languages: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # e.g., ["English", "Chinese"]
    variants: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # e.g., ["COCO test-dev", "COCO 2017"]

    # Usage count
    num_papers: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Warning/notes
    warning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # PWC source URL
    pwc_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_datasets", back_populates="datasets"
    )
    tasks: Mapped[List["Task"]] = relationship(
        "Task", secondary="task_datasets", back_populates="datasets"
    )
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation", back_populates="dataset"
    )

    # Self-referential relationship for parent datasets
    parent_dataset: Mapped[Optional["Dataset"]] = relationship(
        "Dataset", remote_side=[id], foreign_keys=[parent_dataset_id]
    )

    def __repr__(self) -> str:
        return f"<Dataset(id={self.id}, name='{self.name}')>"


class Evaluation(Base):
    """
    Benchmark evaluation results.
    """

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )

    model_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Optional harness/runtime used to evaluate the model (e.g. "Claude Code",
    # "Terminus"). Some benchmarks like Terminal-Bench are effectively
    # model+harness combinations; this column lets us render them separately
    # from `model_name` instead of cramming both into the model column.
    harness: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    methodology: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)  # JSONB field
    uses_additional_data: Mapped[bool] = mapped_column(Boolean, default=False)
    # Whether the evaluated model is open-source. Defaults to True; closed-source
    # models (proprietary APIs, unreleased flagship LLMs) set this to False so the
    # frontend can optionally hide them based on a per-user preference.
    is_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    best_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    best_metric: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    evaluated_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    external_source_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    # Raw number of model parameters for this evaluation row (e.g. 7000000000
    # for a 7B model). Kept on the evaluation rather than baked into
    # `model_name` so future leaderboards can filter / sort by size.
    num_parameters: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Optional link to the Hugging Face model page for the evaluated model
    # (e.g. https://huggingface.co/MiniMaxAI/MiniMax-M3). Stored per evaluation
    # so each leaderboard row can link the model name directly to its HF page.
    hf_model_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    paper: Mapped["Paper"] = relationship("Paper", back_populates="evaluations")
    task: Mapped["Task"] = relationship("Task", back_populates="evaluations")
    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="evaluations")

    # Indexes
    __table_args__ = (
        Index(
            "idx_evaluations_paper_task_dataset", "paper_id", "task_id", "dataset_id"
        ),
        Index("idx_evaluations_best_rank", "best_rank"),
        Index("idx_evaluations_external", "external"),
        Index("idx_evaluations_source_url", "source_url"),
    )

    def __repr__(self) -> str:
        return f"<Evaluation(id={self.id}, paper_id={self.paper_id}, task_id={self.task_id}, dataset_id={self.dataset_id})>"


class EvaluationBadgeTombstone(Base):
    """Durable lookup data for leaderboard badges after an evaluation is deleted."""

    __tablename__ = "evaluation_badge_tombstones"

    evaluation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paper_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dataset_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    task_slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dataset_slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_evaluation_badge_tombstones_paper_id", "paper_id"),
        Index(
            "idx_evaluation_badge_tombstones_target",
            "paper_id",
            "task_id",
            "dataset_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            "<EvaluationBadgeTombstone("
            f"evaluation_id={self.evaluation_id}, paper_id={self.paper_id})>"
        )


class Metric(Base):
    """
    Metric definitions with ranking direction and scale.

    Defines evaluation metrics and whether they should rank with higher or lower values as better.
    Also tracks the canonical scale for metric values to help normalize them correctly.

    Examples:
    - Higher is better: AP, accuracy, F1, BLEU
    - Lower is better: WER, error rates, perplexity
    - Scale examples: "0-1" (ratios/decimals), "0-100" (percentages), "unbounded" (loss functions)
    """

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "higher_is_better" or "lower_is_better"
    scale: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # e.g., "0-1", "0-100", "percentage", "milliseconds", "unbounded"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Indexes
    __table_args__ = (Index("idx_metrics_name", "name"),)

    def __repr__(self) -> str:
        return f"<Metric(id={self.id}, name={self.name}, direction={self.direction})>"


class TaskDataset(Base):
    """
    Task-specific dataset membership and display metadata.

    Leaderboard metric definitions remain in TaskDatasetMetric; this table stores
    one row per task-benchmark pair so display metadata cannot conflict across
    multiple metrics.
    """

    __tablename__ = "task_datasets"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True
    )
    supports_harness: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_task_datasets_task_id", "task_id"),
        Index("idx_task_datasets_dataset_id", "dataset_id"),
    )


class TaskDatasetMetric(Base):
    """
    Junction table for task-dataset-metric triples (leaderboard definitions).

    Each triple (task, dataset, metric) defines a unique leaderboard.
    For example: (Image Classification, ImageNet, Top-1 Accuracy)
    """

    __tablename__ = "task_dataset_metrics"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True
    )
    metric_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("metrics.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Indexes
    __table_args__ = (
        Index("idx_task_dataset_metrics_task_id", "task_id"),
        Index("idx_task_dataset_metrics_dataset_id", "dataset_id"),
        Index("idx_task_dataset_metrics_metric_id", "metric_id"),
        Index("idx_task_dataset_metrics_task_dataset", "task_id", "dataset_id"),
    )
