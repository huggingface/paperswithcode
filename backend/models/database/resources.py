"""Repository, Hugging Face artifact, project page, and model release persistence models."""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base

if TYPE_CHECKING:
    from backend.models.database.papers import Paper


class Repository(Base):
    """
    GitHub repositories (normalized, no direct paper relationship).

    This table stores unique repositories. The relationship to papers
    is handled through the PaperRepository junction table.

    Note: is_official is now stored in the PaperRepository junction table
    since repositories can have different official status for different papers.
    """

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    num_stars: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(50), default="unknown")

    # Trending metrics (EMA-based)
    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, comment="EMA trending score (stars/hour)"
    )
    trending_score_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    num_stars_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Many-to-many relationship with papers through PaperRepository
    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_repositories", back_populates="repositories"
    )

    # One-to-many relationship with star history
    star_history: Mapped[List["RepositoryStarHistory"]] = relationship(
        "RepositoryStarHistory",
        back_populates="repository",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("idx_repositories_url", "url"),
        Index("idx_repositories_stars", "num_stars"),
        Index("idx_repositories_owner", "owner"),
        Index("idx_repositories_name", "name"),
        Index("idx_repositories_source", "source"),
        Index("idx_repositories_num_stars_updated_at", "num_stars_updated_at"),
        Index("idx_repositories_trending_score", "trending_score"),
        Index(
            "idx_repositories_trending_score_updated_at", "trending_score_updated_at"
        ),
        Index("idx_repositories_created_at", "created_at"),
        Index("idx_repositories_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<Repository(id={self.id}, url='{self.url}', stars={self.num_stars})>"


class RepositoryStarHistory(Base):
    """
    Repository star history model for tracking GitHub star counts over time.

    This enables trending metrics by storing historical snapshots of star counts.
    """

    __tablename__ = "repository_star_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    num_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository", back_populates="star_history"
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("repository_id", "snapshot_at", name="uq_repo_snapshot_time"),
        Index("idx_star_history_repository_id", "repository_id"),
        Index("idx_star_history_snapshot_at", "snapshot_at"),
        Index("idx_star_history_repo_time", "repository_id", "snapshot_at"),
    )

    def __repr__(self) -> str:
        return f"<RepositoryStarHistory(id={self.id}, repository_id={self.repository_id}, stars={self.num_stars}, snapshot_at='{self.snapshot_at}')>"


class HfArtifact(Base):
    """
    Normalized Hugging Face artifact (model, dataset, or space) with Hub
    popularity metrics. The relationship to papers is handled through the
    PaperHfArtifact junction table.

    `trending_score` is the Hugging Face Hub trendingScore (fetched via the
    `expand[]=trendingScore` parameter). These rows feed the composite paper
    trending score; they do not affect the GitHub-only ranking.
    """

    __tablename__ = "hf_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # One of: 'model', 'dataset', 'space'.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Hugging Face repo id, e.g. 'deepseek-ai/DeepSeek-V4-Pro'.
    repo_id: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    likes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    downloads: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_hf_artifacts", back_populates="hf_artifacts"
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('model', 'dataset', 'space')",
            name="hf_artifacts_kind_check",
        ),
        UniqueConstraint("kind", "repo_id", name="uq_hf_artifacts_kind_repo"),
        Index("idx_hf_artifacts_trending_score", "trending_score"),
        Index("idx_hf_artifacts_fetched_at", "fetched_at"),
        Index("idx_hf_artifacts_kind", "kind"),
    )

    def __repr__(self) -> str:
        return (
            f"<HfArtifact(id={self.id}, kind='{self.kind}', "
            f"repo_id='{self.repo_id}', trending_score={self.trending_score})>"
        )


class PaperHfArtifact(Base):
    """Junction table linking papers to Hugging Face artifacts."""

    __tablename__ = "paper_hf_artifacts"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    hf_artifact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hf_artifacts.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_paper_hf_artifacts_paper", "paper_id"),
        Index("idx_paper_hf_artifacts_artifact", "hf_artifact_id"),
    )


class ModelRelease(Base):
    """Canonical model identity shared by papers, Hub artifacts, and providers."""

    __tablename__ = "model_releases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=True
    )
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    canonical_source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "paper_id", "canonical_name", name="uq_model_release_paper_name"
        ),
        Index("idx_model_releases_paper", "paper_id"),
        Index("idx_model_releases_publisher", "publisher"),
    )


class ModelReleaseArtifact(Base):
    """Attach all official Hub repositories for a canonical model release."""

    __tablename__ = "model_release_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_release_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("model_releases.id", ondelete="CASCADE"),
        nullable=False,
    )
    hf_artifact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("hf_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "model_release_id",
            "hf_artifact_id",
            name="uq_model_release_artifact",
        ),
        Index("idx_model_release_artifacts_hf", "hf_artifact_id"),
    )


class ModelProviderAlias(Base):
    """Provider-specific model IDs resolved onto canonical releases."""

    __tablename__ = "model_provider_aliases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_release_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("model_releases.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    alias: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("provider", "alias", name="uq_model_provider_alias"),
        Index("idx_model_provider_alias_release", "model_release_id"),
    )


class ProjectPage(Base):
    """
    Project pages showcasing paper work - normalized without direct paper reference.
    """

    __tablename__ = "project_pages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_official: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # Use paper_project_pages.is_official for relationship-specific data
    source: Mapped[str] = mapped_column(String(50), default="unknown")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_project_pages", back_populates="project_pages"
    )

    # Indexes
    __table_args__ = (
        Index("idx_project_pages_url", "url"),
        Index("idx_project_pages_source", "source"),
        Index("idx_project_pages_is_official", "is_official"),
    )

    def __repr__(self) -> str:
        return f"<ProjectPage(id={self.id}, url='{self.url}', official={self.is_official})>"


class PaperProjectPage(Base):
    """
    Junction table for many-to-many relationship between papers and project pages.
    Simplified to only contain the two ID columns as requested.
    """

    __tablename__ = "paper_project_pages"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    project_page_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("project_pages.id", ondelete="CASCADE"), primary_key=True
    )

    # Relationships
    paper: Mapped["Paper"] = relationship("Paper", overlaps="project_pages,papers")
    project_page: Mapped["ProjectPage"] = relationship(
        "ProjectPage", overlaps="papers,project_pages"
    )

    # Indexes
    __table_args__ = (
        Index("idx_paper_project_pages_paper_id", "paper_id"),
        Index("idx_paper_project_pages_project_page_id", "project_page_id"),
    )

    def __repr__(self) -> str:
        return f"<PaperProjectPage(paper_id={self.paper_id}, project_page_id={self.project_page_id})>"


class PaperXThread(Base):
    """An X post introducing a paper, with the preview captured when linked."""

    __tablename__ = "paper_x_threads"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    tweet_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author_handle: Mapped[str] = mapped_column(String(64), nullable=False)
    author_avatar_url: Mapped[Optional[str]] = mapped_column(String(1000))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    like_count: Mapped[Optional[int]] = mapped_column(Integer)
    reply_count: Mapped[Optional[int]] = mapped_column(Integer)
    media_url: Mapped[Optional[str]] = mapped_column(String(1000))
    media_type: Mapped[Optional[str]] = mapped_column(String(16))
    video_url: Mapped[Optional[str]] = mapped_column(String(1000))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PaperXTrending(Base):
    """A paper on one day's "AI Papers on X" sheet, with its top post's reach."""

    __tablename__ = "paper_x_trending"

    shared_on: Mapped[date] = mapped_column(Date, primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("papers.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    post_url: Mapped[Optional[str]] = mapped_column(String(500))
    post_author: Mapped[Optional[str]] = mapped_column(String(64))
    like_count: Mapped[Optional[int]] = mapped_column(Integer)
    repost_count: Mapped[Optional[int]] = mapped_column(Integer)
    view_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PaperXThreadScan(Base):
    """Bounded X search state for one paper, kept by the discovery CRON."""

    __tablename__ = "paper_x_thread_scans"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    scan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    candidates: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PaperXPost(Base):
    """A post on the Papers with Code X account featuring one paper."""

    __tablename__ = "paper_x_posts"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[str] = mapped_column(Text, nullable=False)
    reply_id: Mapped[Optional[str]] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class XInsightPost(Base):
    """An insight post (SOTA, trends, roundups) on the Papers with Code X account."""

    __tablename__ = "x_insight_posts"
    __table_args__ = (Index("idx_x_insight_posts_kind_subject", "kind", "subject_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    post_id: Mapped[str] = mapped_column(Text, nullable=False)
    reply_id: Mapped[Optional[str]] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaperRepository(Base):
    """Junction table for papers and repositories (many-to-many relationship)."""

    __tablename__ = "paper_repositories"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)

    # Indexes
    __table_args__ = (
        Index("idx_paper_repositories_paper_id", "paper_id"),
        Index("idx_paper_repositories_repository_id", "repository_id"),
    )
