"""
SQLAlchemy database models.

These models represent the database schema and provide ORM functionality
for interacting with the PostgreSQL database.
"""

from datetime import date, datetime
import uuid
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Integer,
    BigInteger,
    LargeBinary,
    String,
    Text,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, TSVECTOR, UUID
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy.sql import func, text

Base = declarative_base()


class Paper(Base):
    """
    Paper model representing research papers.

    Corresponds to the papers table in the database schema.
    """

    __tablename__ = "papers"

    # Primary key
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Core paper information
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Maintained by papers_search_vector_update() in PostgreSQL. Application
    # code reads this column for ranking but never constructs it in Python.
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
    )

    # Source split: `arxiv` for ArXiv papers, `external` for blog posts,
    # technical reports, model release pages, etc. Existing rows default to
    # `arxiv`. External rows must populate `source_url`; ArXiv rows leave it
    # NULL and continue to derive their URLs from `arxiv_id` + `version`.
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="arxiv", server_default="arxiv"
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # ArXiv information with versioning support. `arxiv_id` is NULL for
    # `source='external'` rows and required for `source='arxiv'` rows
    # (enforced by `papers_source_identifier_check`).
    arxiv_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    version: Mapped[str] = mapped_column(String(10), default="v1")
    is_latest_version: Mapped[bool] = mapped_column(Boolean, default=True)

    # Publication information
    date_published: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    proceeding: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    conference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    conference_url_abs: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    conference_url_pdf: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    # Citation and importance metrics
    citation_count: Mapped[int] = mapped_column(Integer, default=0)
    semantic_scholar_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    citation_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ArXiv category classification
    primary_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    all_categories: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )

    # URL extraction tracking
    urls_extracted: Mapped[bool] = mapped_column(Boolean, default=False)

    # References-based method tagging tracking. NULL means the references-based
    # cron has never processed this paper; populated rows are skipped.
    methods_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Optional explicit thumbnail URL. ArXiv rows usually leave this NULL and
    # derive thumbnails from arxiv_id/version; external rows can point at a
    # captured source-page thumbnail.
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Frontend v2 schema additions (PLAN.md §11). Schema-only; no data ingestion in this migration.
    # tldr      -> AI-generated summary surfaced in PaperDetailView "TL;DR" panel.
    # num_pages -> source PDF page count; not surfaced in UI yet.
    tldr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    num_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Hugging Face artifact URLs explicitly linked to this paper. Used for
    # `source='external'` rows because external rows have no reliable arxiv_id
    # to query the Hugging Face arxiv filter URL with. ArXiv rows leave these
    # NULL and derive artifacts from `arxiv_id` at request/render time.
    hf_models: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    hf_datasets: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    hf_spaces: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)

    # Composite trending score (GitHub star velocity + Hugging Face artifact
    # trending). Computed by the calculate_paper_trending_scores cron and only
    # consumed for ranking when PWC_TRENDING_RANKING_MODE=composite. The
    # GitHub-only path keeps reading repositories.trending_score, so this column
    # can stay populated-but-unused for an instant rollback.
    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    trending_score_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Normalized 0-1.5 components retained for debugging odd rankings.
    github_trending_component: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    hf_trending_component: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    # When this paper was last scanned for linked Hugging Face artifacts.
    hf_artifacts_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    authors: Mapped[List["Author"]] = relationship(
        "Author", secondary="paper_authors", back_populates="papers"
    )
    tasks: Mapped[List["Task"]] = relationship(
        "Task", secondary="paper_tasks", back_populates="papers"
    )
    methods: Mapped[List["Method"]] = relationship(
        "Method", secondary="paper_methods", back_populates="papers"
    )
    datasets: Mapped[List["Dataset"]] = relationship(
        "Dataset", secondary="paper_datasets", back_populates="papers"
    )
    repositories: Mapped[List["Repository"]] = relationship(
        "Repository", secondary="paper_repositories", back_populates="papers"
    )
    project_pages: Mapped[List["ProjectPage"]] = relationship(
        "ProjectPage", secondary="paper_project_pages", back_populates="papers"
    )
    conferences: Mapped[List["Conference"]] = relationship(
        "Conference", secondary="paper_conferences", back_populates="papers"
    )
    organizations: Mapped[List["Organization"]] = relationship(
        "Organization", secondary="paper_organizations", back_populates="papers"
    )
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation", back_populates="paper"
    )
    hf_artifacts: Mapped[List["HfArtifact"]] = relationship(
        "HfArtifact", secondary="paper_hf_artifacts", back_populates="papers"
    )

    # Constraints
    __table_args__ = (
        # Partial unique indexes replace the prior `(arxiv_id, version)` UNIQUE
        # constraint so external rows can omit ArXiv identifiers.
        Index(
            "uq_papers_arxiv_id_version_when_present",
            "arxiv_id",
            "version",
            unique=True,
            postgresql_where=text("arxiv_id IS NOT NULL"),
        ),
        Index(
            "uq_papers_source_url_external",
            "source_url",
            unique=True,
            postgresql_where=text("source = 'external' AND source_url IS NOT NULL"),
        ),
        CheckConstraint(
            "source IN ('arxiv', 'external')",
            name="papers_source_check",
        ),
        CheckConstraint(
            "(source = 'arxiv' AND arxiv_id IS NOT NULL) "
            "OR (source = 'external' AND source_url IS NOT NULL)",
            name="papers_source_identifier_check",
        ),
        Index("idx_papers_arxiv_id", "arxiv_id"),
        Index("idx_papers_source", "source"),
        Index("idx_papers_date_published", "date_published"),
        Index("idx_papers_conference", "conference"),
        Index("idx_papers_title_search", "title"),  # For text search
        Index("idx_papers_latest_version", "is_latest_version"),
        Index("idx_papers_citation_count", "citation_count"),
        Index("idx_papers_semantic_scholar_id", "semantic_scholar_id"),
        Index("idx_papers_primary_category", "primary_category"),
        Index("idx_papers_urls_extracted", "urls_extracted"),
        Index(
            "idx_papers_methods_scanned_at",
            "methods_scanned_at",
            postgresql_where=text("methods_scanned_at IS NULL"),
        ),
        Index("idx_papers_trending_score", "trending_score"),
        Index("idx_papers_trending_score_updated_at", "trending_score_updated_at"),
        Index("idx_papers_hf_artifacts_scanned_at", "hf_artifacts_scanned_at"),
    )

    def __repr__(self) -> str:
        return f"<Paper(id={self.id}, arxiv_id='{self.arxiv_id}', version='{self.version}', title='{self.title[:50]}...')>"


class Author(Base):
    """
    Author model with Hugging Face integration.
    """

    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Hugging Face integration
    hf_username: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    hf_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    hf_avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hf_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hf_is_pro: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    papers: Mapped[List[Paper]] = relationship(
        "Paper", secondary="paper_authors", back_populates="authors"
    )

    # Indexes
    __table_args__ = (
        Index("idx_authors_hf_username", "hf_username"),
        Index("idx_authors_hf_id", "hf_id"),
        Index("idx_authors_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Author(id={self.id}, name='{self.name}', hf_username='{self.hf_username}')>"


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

    # Visibility in user-facing pickers (the /tasks taxonomy index and the
    # paper-tagging dropdown). Hidden tasks remain reachable by direct slug.
    is_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

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
    papers: Mapped[List[Paper]] = relationship(
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
    source_paper: Mapped[Optional[Paper]] = relationship("Paper")
    papers: Mapped[List[Paper]] = relationship(
        "Paper", secondary="paper_methods", back_populates="methods"
    )

    __table_args__ = (Index("idx_methods_source_paper_id", "source_paper_id"),)

    def __repr__(self) -> str:
        return f"<Method(id={self.id}, name='{self.name}')>"


class Dataset(Base):
    """
    Benchmark datasets.
    """

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
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
    papers: Mapped[List[Paper]] = relationship(
        "Paper", secondary="paper_datasets", back_populates="datasets"
    )
    tasks: Mapped[List[Task]] = relationship(
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


class PaperCurationJob(Base):
    """Durable request for a remote Codex paper-curation Job."""

    __tablename__ = "paper_curation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    paper_route: Mapped[str] = mapped_column(String(255), nullable=False)
    paper_title: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
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
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    paper: Mapped[Paper] = relationship("Paper")

    __table_args__ = (
        CheckConstraint(
            "kind IN ('add-evals', 'enrich-paper')",
            name="paper_curation_jobs_kind_check",
        ),
        CheckConstraint(
            "status IN ('queued', 'dispatching', 'running', 'completed', 'failed', 'canceled')",
            name="paper_curation_jobs_status_check",
        ),
        Index("idx_paper_curation_jobs_queue", "status", "created_at"),
        Index("idx_paper_curation_jobs_paper", "paper_id", "created_at"),
    )


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
    paper: Mapped[Paper] = relationship("Paper", back_populates="evaluations")
    task: Mapped[Task] = relationship("Task", back_populates="evaluations")
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


# Junction tables for many-to-many relationships


class PaperAuthor(Base):
    """Junction table for papers and authors."""

    __tablename__ = "paper_authors"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True
    )
    author_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Indexes
    __table_args__ = (
        Index("idx_paper_authors_paper_id", "paper_id"),
        Index("idx_paper_authors_author_id", "author_id"),
    )


class PaperTask(Base):
    """Junction table for papers and tasks."""

    __tablename__ = "paper_tasks"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    # 'auto' = inserted by keyword matcher (rebuild may delete/re-insert).
    # 'manual' = set via admin API / one-off script (rebuild leaves alone).
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")

    __table_args__ = (
        Index("idx_paper_tasks_paper_id", "paper_id"),
        Index("idx_paper_tasks_task_id", "task_id"),
        Index("idx_paper_tasks_source", "source"),
    )


class PaperMethod(Base):
    """Junction table for papers and methods."""

    __tablename__ = "paper_methods"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    method_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("methods.id", ondelete="CASCADE"), primary_key=True
    )

    # Indexes
    __table_args__ = (
        Index("idx_paper_methods_paper_id", "paper_id"),
        Index("idx_paper_methods_method_id", "method_id"),
    )


class PaperDataset(Base):
    """Junction table for papers and datasets."""

    __tablename__ = "paper_datasets"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True
    )

    # Indexes
    __table_args__ = (
        Index("idx_paper_datasets_paper_id", "paper_id"),
        Index("idx_paper_datasets_dataset_id", "dataset_id"),
    )


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
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_organizations", back_populates="organizations"
    )

    __table_args__ = (Index("idx_organizations_slug", "slug"),)

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

    __table_args__ = (
        Index("idx_paper_organizations_organization_id", "organization_id"),
        Index("idx_paper_organizations_paper_id", "paper_id"),
    )


class PaperRelation(Base):
    """Directed lineage edges between papers.

    ``source_paper_id`` is the predecessor (earlier) paper; ``target_paper_id``
    is the successor (follow-up) paper. The relation is many-to-many in both
    directions: a paper can have multiple successors and multiple predecessors.
    """

    __tablename__ = "paper_relations"

    source_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    target_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "source_paper_id <> target_paper_id",
            name="paper_relations_no_self_link",
        ),
        Index("idx_paper_relations_source_paper_id", "source_paper_id"),
        Index("idx_paper_relations_target_paper_id", "target_paper_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<PaperRelation(source_paper_id={self.source_paper_id}, "
            f"target_paper_id={self.target_paper_id})>"
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
    featured_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
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
        Index(
            "idx_chat_sessions_owner_updated",
            "hf_user_id",
            text("updated_at DESC"),
            text("id DESC"),
        ),
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
    client_message_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    supersedes_message_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    sdk_resume_boundary_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
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
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
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
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')", name="chat_messages_role_check"
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


class ChatSandboxLease(Base):
    """Durable ownership and recoverable state for one per-chat sandbox."""

    __tablename__ = "chat_sandbox_leases"

    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    modal_sandbox_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    image_version: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="starting"
    )
    lease_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    workspace_snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    snapshot_image_version: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    snapshot_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    workspace_dirty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    session: Mapped[ChatSession] = relationship(back_populates="sandbox_lease")
    __table_args__ = (
        CheckConstraint(
            "state IN ('starting','ready','busy','idle','terminating','terminated','failed')",
            name="chat_sandbox_leases_state_check",
        ),
        Index("idx_chat_sandbox_leases_state_activity", "state", "last_activity_at"),
    )


class ChatTurnCapability(Base):
    """Hash-only, short-lived authorization held by the isolated broker."""

    __tablename__ = "chat_turn_capabilities"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    sdk_session_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    owner_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        Index(
            "idx_chat_turn_capabilities_scope",
            "chat_session_id",
            "turn_id",
            "expires_at",
        ),
    )


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
    is_author: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    edit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    current_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
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
            "edit_type IN ('tasks', 'methods', 'evaluations', 'repositories', 'project_pages', 'source_url', 'hf_artifacts', 'new_task', 'new_method', 'new_benchmark', 'new_metric', 'new_conference')",
            name="pending_paper_edits_edit_type_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="pending_paper_edits_status_check",
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
