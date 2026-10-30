"""Paper, author, relation, and paper-taxonomy association persistence models."""

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from backend.models.database.base import Base

if TYPE_CHECKING:
    from backend.models.database.conferences import Conference
    from backend.models.database.evaluations import Dataset, Evaluation
    from backend.models.database.organizations import Organization
    from backend.models.database.resources import HfArtifact, ProjectPage, Repository
    from backend.models.database.taxonomy import Method, Task


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

    # Hugging Face artifact URLs explicitly linked to this paper. External rows
    # need these because they have no reliable arxiv_id. ArXiv rows usually
    # derive artifacts from arxiv_id, but retain curated URLs when an external
    # release is later canonicalized onto an ArXiv paper.
    hf_models: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text).with_variant(JSON(), "sqlite"), nullable=True
    )
    hf_datasets: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text).with_variant(JSON(), "sqlite"), nullable=True
    )
    hf_spaces: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text).with_variant(JSON(), "sqlite"), nullable=True
    )

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

    # Durable membership in HF daily papers, independent of conference metadata.
    hf_daily_featured_on: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
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
        Index(
            "idx_papers_date_published_desc_nulls_last",
            date_published.desc().nullslast(),
        ).ddl_if(dialect="postgresql"),
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
        Index("idx_authors_lower_name", func.lower(name)),
    )

    def __repr__(self) -> str:
        return f"<Author(id={self.id}, name='{self.name}', hf_username='{self.hf_username}')>"


class AuthorAlias(Base):
    """Former author ID merged into another author, kept so old URLs resolve."""

    __tablename__ = "author_aliases"

    alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("authors.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (Index("idx_author_aliases_author_id", "author_id"),)


class AuthorGoogleScholarProfile(Base):
    """An author's Google Scholar profile, linked only when papers prove it."""

    __tablename__ = "author_google_scholar_profiles"

    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True
    )
    scholar_id: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    wikidata_qid: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    evidence_source: Mapped[str] = mapped_column(String(30), nullable=False)
    matched_papers: Mapped[int] = mapped_column(Integer, nullable=False)
    considered_papers: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_paper_ids: Mapped[List[int]] = mapped_column(
        ARRAY(BigInteger).with_variant(JSON(), "sqlite"), nullable=False
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuthorPhoto(Base):
    """A freely licensed portrait for an author without an uploaded HF avatar."""

    __tablename__ = "author_photos"

    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True
    )
    image_data: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, deferred=True
    )
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Licenses like CC BY require crediting the photographer next to the photo.
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    credit: Mapped[str] = mapped_column(String(500), nullable=False)
    license: Mapped[str] = mapped_column(String(100), nullable=False)
    license_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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
    # The author claimed this paper on Hugging Face. Authors linked to an HF
    # account list only claimed papers; everyone else is matched by name.
    claimed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

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


class PaperMethodEvidence(Base):
    """Auditable evidence for one paper-method association."""

    __tablename__ = "paper_method_evidence"

    paper_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    method_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    evidence_type: Mapped[str] = mapped_column(String(24), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["paper_id", "method_id"],
            ["paper_methods.paper_id", "paper_methods.method_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "evidence_type IN "
            "('source', 'keyword', 'reference', 'curation', 'manual', 'legacy_unknown')",
            name="paper_method_evidence_type_check",
        ),
        Index("idx_paper_method_evidence_method_type", "method_id", "evidence_type"),
    )


class PaperMethodExclusion(Base):
    """Durable curator veto against automated paper-method linking."""

    __tablename__ = "paper_method_exclusions"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    method_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("methods.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_paper_method_exclusions_method", "method_id", "paper_id"),
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


class PaperSuggestedQuestions(Base):
    """Three Luna-generated starter questions shown on a paper page."""

    __tablename__ = "paper_suggested_questions"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    questions: Mapped[List[str]] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PaperAbstractMention(Base):
    """A literal catalog name in a paper abstract, and whether it is linked."""

    __tablename__ = "paper_abstract_mentions"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    entity_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    start_offset: Mapped[int] = mapped_column(Integer, primary_key=True)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    surface: Mapped[str] = mapped_column(Text, nullable=False)
    abstract_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    linked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    judge: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('method', 'dataset', 'framework')",
            name="paper_abstract_mentions_entity_type_check",
        ),
        Index("idx_paper_abstract_mentions_entity", "entity_type", "entity_id"),
    )
