"""Paper, author, repository, and project-page API contracts."""

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.evaluations import BenchmarkSummary, LeaderboardRankSummary

from backend.utils.public_urls import (
    normalize_optional_public_url,
    normalize_public_url,
)


class GithubRepositoryPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    stars: int = Field(ge=0)
    forks: int = Field(ge=0)
    language: str | None = None
    archived: bool
    avatar_url: str | None = None


class PaperBucketArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["model", "dataset", "space"]
    repo_id: str = Field(min_length=3, max_length=256)


class PaperBucketCopyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket_id: str = Field(min_length=3, max_length=256)
    create: bool = True
    private: bool = False
    include_pdf: bool = True
    artifacts: List[PaperBucketArtifact] = Field(default_factory=list, max_length=20)


class PaperBucketCopyError(BaseModel):
    artifact: str
    message: str


class PaperBucketCopyResponse(BaseModel):
    bucket_id: str
    copied: List[str]
    errors: List[PaperBucketCopyError]


class Paper(BaseModel):
    """
    Paper object matching the original PapersWithCode API specification.

    Represents a single research paper with all its metadata, authors, and URLs.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core paper identification
    id: str = Field(..., description="Paper ID")
    arxiv_id: Optional[str] = Field(None, description="ArXiv ID")

    # Source split: 'arxiv' for ArXiv papers, 'external' for blog posts,
    # technical reports, model release pages, etc.
    source: str = Field(
        default="arxiv",
        description="Origin of this paper row: 'arxiv' or 'external'",
    )
    source_url: Optional[str] = Field(
        None,
        description=(
            "Canonical URL for external rows. NULL for ArXiv rows; ArXiv URLs "
            "continue to be derived from arxiv_id."
        ),
    )

    # URLs - source-aware. ArXiv rows have generated abs/pdf URLs from
    # `arxiv_id`/`version`. External rows return `source_url` as `url_abs`
    # and leave `url_pdf` NULL unless an explicit PDF is known.
    url_abs: Optional[str] = Field(
        None, description="URL to the paper abstract or external source page"
    )
    url_pdf: Optional[str] = Field(
        None,
        description="URL to the paper PDF (NULL when no PDF is known, e.g. external blog posts)",
    )
    thumbnail_url: Optional[str] = Field(
        None, description="URL to the paper thumbnail image"
    )

    # Paper content
    title: str = Field(..., description="Paper title")
    abstract: Optional[str] = Field(
        default="",
        description="Paper abstract or summary (may be empty for external rows)",
    )
    authors: List[str] = Field(..., description="List of paper authors")
    author_links: List["AuthorLink"] = Field(
        default_factory=list,
        description=(
            "Per-author entries parallel to `authors`, carrying the author ID "
            "and the HF username when mapped to a Hugging Face profile. Feed "
            "card responses include only the first three authors, as displayed."
        ),
    )

    # Publication information
    published: Optional[date] = Field(None, description="Paper publication date")
    conference: Optional[str] = Field(
        None, description="ID of the conference in which the paper was published"
    )
    conference_url_abs: Optional[str] = Field(
        None, description="URL to the conference paper page"
    )
    conference_url_pdf: Optional[str] = Field(
        None, description="URL to the conference paper PDF"
    )
    proceeding: Optional[str] = Field(
        None, description="ID of the conference proceeding"
    )
    conference_slug: Optional[str] = Field(
        None,
        description=(
            "URL slug for the linked conference page (e.g. 'cvpr-2026'), "
            "from the normalized paper_conferences relation"
        ),
    )
    conference_name: Optional[str] = Field(
        None,
        description="Display name of the linked conference (e.g. 'CVPR 2026')",
    )
    conference_award: Optional[str] = Field(
        None,
        description=(
            "Award tier for this paper at the listing conference "
            "(e.g. 'outstanding', 'honorable_mention', 'best_paper_finalist')"
        ),
    )

    # Version tracking (our extension)
    version: str = Field(default="v1", description="Paper version (e.g., v1, v2, v3)")
    is_latest_version: bool = Field(
        default=True, description="Whether this is the latest version"
    )

    @field_validator("version", mode="before")
    @classmethod
    def default_missing_version(cls, value: object) -> object:
        # A NULL version column must not make the paper page fail to render.
        return "v1" if value is None else value

    # Citation and importance metrics
    citation_count: int = Field(
        default=0, description="Number of citations from Semantic Scholar"
    )
    semantic_scholar_id: Optional[str] = Field(
        None, description="Semantic Scholar paper ID"
    )
    citation_updated_at: Optional[datetime] = Field(
        None, description="Last time citations were updated"
    )

    # ArXiv category classification
    primary_category: Optional[str] = Field(
        None, description="Primary ArXiv category (e.g., cs.CV, cs.LG)"
    )
    all_categories: List[str] = Field(
        default_factory=list, description="All ArXiv categories for this paper"
    )

    # URL extraction tracking
    urls_extracted: bool = Field(
        default=False, description="Whether URLs have been extracted for this paper"
    )

    # Frontend v2 schema additions (PLAN.md §11). Schema-only; no data ingestion in this migration.
    tldr: Optional[str] = Field(
        None,
        description="AI-generated TL;DR summary (frontend v2 PaperDetailView panel)",
    )
    num_pages: Optional[int] = Field(
        None, description="Page count of the source PDF (frontend v2)"
    )
    suggested_questions: Optional[List[str]] = Field(
        None,
        description=(
            "Stored starter questions for the paper-page assistant. Detail "
            "responses return a list (empty when none are stored yet); feed "
            "cards leave it null."
        ),
    )
    evaluated_benchmarks: Optional[List[str]] = Field(
        None,
        description=(
            "Names of the benchmarks this paper reports leaderboard results "
            "on, most-populated leaderboard first. Detail responses only."
        ),
    )
    page_title: Optional[str] = Field(
        None,
        description=(
            "Search-facing HTML title of the paper page, e.g. "
            "'Kimi K3.1 Pro benchmarks: … | Papers with Code'. Detail "
            "responses only."
        ),
    )

    # Hugging Face artifact URLs explicitly linked to this paper. Populated
    # for `source='external'` rows because external rows have no reliable
    # `arxiv_id` to query the Hugging Face arxiv filter URL with. ArXiv rows
    # leave these empty and derive artifacts from `arxiv_id` at render time.
    hf_models: List[str] = Field(
        default_factory=list,
        description=(
            "Full Hugging Face model URLs explicitly linked to this paper "
            "(populated for external rows only)"
        ),
    )
    hf_datasets: List[str] = Field(
        default_factory=list,
        description=(
            "Full Hugging Face dataset URLs explicitly linked to this paper "
            "(populated for external rows only)"
        ),
    )
    hf_spaces: List[str] = Field(
        default_factory=list,
        description=(
            "Full Hugging Face Space URLs explicitly linked to this paper "
            "(populated for external rows only)"
        ),
    )
    hf_artifact_summary: Optional["HfArtifactSummary"] = Field(
        None,
        description=(
            "Compact Hugging Face artifact summary (per-kind counts plus the "
            "most popular category link) used by paper feed cards."
        ),
    )
    linked_hf_artifacts: Optional["LinkedHfArtifacts"] = Field(
        None,
        description=(
            "Hugging Face artifacts stored for this paper by the HF sync, up to "
            "100 per kind ordered by popularity. Populated only on paper detail "
            "responses with include_resources=true."
        ),
    )
    has_official_implementation: bool = Field(
        default=False,
        description=(
            "Whether the catalog links an official code repository to any "
            "version of this paper"
        ),
    )
    code_repository_count: int = Field(
        default=0,
        description=(
            "Number of distinct code repositories linked to any version of this paper"
        ),
    )

    # Associated resources (optional, populated when requested)
    repositories: Optional[List["Repository"]] = Field(
        None, description="GitHub repositories associated with this paper"
    )
    project_pages: Optional[List["ProjectPage"]] = Field(
        None, description="Project pages associated with this paper"
    )
    x_threads: Optional[List["XThread"]] = Field(
        None, description="X (formerly Twitter) posts introducing this paper"
    )
    abstract_mentions: Optional[List["AbstractMention"]] = Field(
        None,
        description=(
            "Catalog methods, benchmarks, and frameworks named in the abstract, "
            "as character spans of `abstract` (paper detail only)."
        ),
    )
    tasks: Optional[List["TaskSummary"]] = Field(
        None, description="AI/ML tasks associated with this paper"
    )
    methods: Optional[List["MethodSummary"]] = Field(
        None, description="Methods and techniques used in this paper"
    )
    introduced_benchmarks: Optional[List["BenchmarkSummary"]] = Field(
        None,
        description="Benchmarks/datasets introduced by this paper (datasets where introducing_paper_id matches)",
    )
    introduced_frameworks: Optional[List["FrameworkSummary"]] = Field(
        None,
        description="Software frameworks for which this paper is the canonical introducing source",
    )
    predecessor_papers: Optional[List["RelatedPaperSummary"]] = Field(
        None,
        description=(
            "Earlier papers that this paper is a follow-up to "
            "(e.g. DINOv2 for the DINOv3 paper)."
        ),
    )
    successor_papers: Optional[List["RelatedPaperSummary"]] = Field(
        None,
        description=(
            "Later papers that follow up on this paper "
            "(e.g. DINOv3 for the DINOv2 paper)."
        ),
    )
    organizations: Optional[List["OrganizationSummary"]] = Field(
        None,
        description=(
            "Organizations (labs/companies) this paper is attributed to, "
            "e.g. NVIDIA, including association source and manual curator. "
            "Powers the org logo tags on the paper page."
        ),
    )
    leaderboard_ranks: Optional[List["LeaderboardRankSummary"]] = Field(
        None,
        description=(
            "Top-3 leaderboard placements (best_rank <= 3) for this paper, "
            "deduped by dataset. Powers the SOTA/#2/#3 badges on paper cards."
        ),
    )

    @field_validator("authors", mode="before")
    @classmethod
    def parse_authors(cls, v):
        """Parse authors from various input formats."""
        if isinstance(v, str):
            # If authors come as a single string, split by comma
            return [author.strip() for author in v.split(",")]
        elif isinstance(v, list):
            return v
        else:
            return []

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class PaperFeedScope(BaseModel):
    """Resolved repository/framework context for a scoped paper feed."""

    kind: Literal["framework", "repository"]
    repository: Optional[str] = None
    framework_slug: Optional[str] = None
    framework_name: Optional[str] = None
    github_url: Optional[str] = None
    num_stars: Optional[int] = None
    introducing_paper_arxiv_id: Optional[str] = None
    recommended_tasks: List["TaskSummary"] = Field(
        default_factory=list,
        description="Tasks that recommend this framework",
    )


class PaperDateRange(BaseModel):
    """Inclusive publication-date bounds accepted by paper feed endpoints."""

    model_config = ConfigDict(frozen=True)

    start_date: date | None = None
    end_date: date | None = None


class AppliedAuthorFilter(BaseModel):
    """Canonical author identity resolved for a paper feed filter."""

    id: str
    name: str
    hf_username: str | None = None


class Papers(BaseModel):
    """
    Object representing a paginated page of papers.

    Matches the original PapersWithCode API pagination structure.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Paper] = Field(..., description="List of papers on this page")
    scope: Optional[PaperFeedScope] = Field(
        None, description="Resolved repository or framework feed context"
    )
    applied_filters: dict[str, str | list[AppliedAuthorFilter]] = Field(
        default_factory=dict,
        description="Exact catalog filters applied to this paper page",
    )


class PaperSummary(BaseModel):
    """
    Lightweight paper summary for list views.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Paper ID")
    title: str = Field(..., description="Paper title")
    arxiv_id: Optional[str] = Field(None, description="ArXiv ID")
    source: str = Field(
        default="arxiv",
        description="Origin of this paper row: 'arxiv' or 'external'",
    )
    source_url: Optional[str] = Field(
        None, description="Canonical URL for external rows; NULL for ArXiv rows"
    )
    authors: List[str] = Field(..., description="List of paper authors")
    published: Optional[date] = Field(None, description="Paper publication date")
    url_abs: Optional[str] = Field(
        None,
        description="URL to the paper abstract or external source page",
    )
    citation_count: int = Field(
        default=0, description="Number of citations from Semantic Scholar"
    )
    thumbnail_url: Optional[str] = Field(
        None, description="URL to the paper thumbnail image"
    )
    has_official_implementation: bool = Field(
        default=False,
        description=(
            "Whether the catalog links an official code repository to any "
            "version of this paper"
        ),
    )
    code_repository_count: int = Field(
        default=0,
        description=(
            "Number of distinct code repositories linked to any version of this paper"
        ),
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class PaperSearchResults(BaseModel):
    """One page of relevance-ranked paper search results."""

    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[PaperSummary] = Field(
        ..., description="Relevance-ranked papers on this page"
    )
    applied_filters: dict[str, str] = Field(
        default_factory=dict,
        description="Exact catalog filters applied to this search page",
    )


class PaperSearchFeedResults(BaseModel):
    """Hydrated page from one bounded, relevance-selected search pool."""

    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Paper] = Field(..., description="Hydrated papers on this page")
    applied_filters: dict[str, str] = Field(
        default_factory=dict,
        description="Exact catalog filters applied before retrieval",
    )
    requested_mode: Literal["keyword", "semantic", "hybrid"]
    applied_mode: Literal["keyword", "semantic", "hybrid"]
    order_by: Literal["relevance", "date_published", "citation_count"]
    cap: int = Field(100, description="Maximum size of the fixed candidate pool")
    cap_reached: bool = Field(
        False, description="Whether additional relevant records existed beyond the cap"
    )
    exhausted: bool = Field(
        ..., description="Whether this page is the final page in the candidate pool"
    )


class RelatedPaperRecommendation(PaperSummary):
    """Paper summary plus non-presentational retrieval diagnostics."""

    provenance: str = Field(..., description="dense, hybrid, lexical, or task_fallback")
    similarity: Optional[float] = Field(None, description="Dense cosine similarity")
    generation_id: Optional[int] = Field(None, description="Embedding generation used")
    used_stale_source_vector: bool = Field(
        False, description="A prior version supplied the source query vector"
    )


class PaperVersion(BaseModel):
    """
    Information about a specific paper version.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Paper ID")
    version: str = Field(..., description="Version identifier")
    title: str = Field(..., description="Paper title")
    is_latest: bool = Field(..., description="Whether this is the latest version")
    published: Optional[date] = Field(None, description="Publication date")
    url_abs: str = Field(..., description="URL to the paper abstract")
    paper_url: str = Field(..., description="URL to the paper on our platform")
    abstract_preview: Optional[str] = Field(None, description="Preview of the abstract")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class PaperVersions(BaseModel):
    """
    All versions of a paper.
    """

    model_config = ConfigDict(from_attributes=True)

    arxiv_id: str = Field(..., description="ArXiv ID")
    total_versions: int = Field(..., description="Total number of versions")
    versions: List[PaperVersion] = Field(..., description="List of all versions")


class VersionComparison(BaseModel):
    """
    Comparison between two paper versions.
    """

    model_config = ConfigDict(from_attributes=True)

    from_version: str = Field(..., description="Source version")
    to_version: str = Field(..., description="Target version")
    title_changed: bool = Field(..., description="Whether the title changed")
    abstract_changed: bool = Field(..., description="Whether the abstract changed")
    date_changed: bool = Field(..., description="Whether the publication date changed")
    time_between_versions: Optional[int] = Field(
        None, description="Days between versions"
    )


class AuthorLink(BaseModel):
    """Minimal author entry used inline on Paper responses.

    Parallels `Paper.authors` and carries an optional `hf_username` so the
    frontend can link author names to their Hugging Face profile.
    """

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = Field(None, description="Stable local author ID")
    name: str = Field(..., description="Author display name")
    hf_username: Optional[str] = Field(
        None,
        description="Hugging Face username, when the author is mapped to a HF profile",
    )
    hf_avatar_url: Optional[str] = Field(
        None,
        description="Hugging Face avatar URL (absolute, or relative to huggingface.co)",
    )


class AuthorPhotoInfo(BaseModel):
    """A self-hosted author portrait and the credit its license requires."""

    url: str = Field(..., description="Versioned photo URL")
    credit: str = Field(..., description="Photographer or rights holder")
    license: str = Field(..., description="License name, e.g. CC BY 4.0")
    license_url: Optional[str] = Field(None, description="License deed URL")
    source_url: str = Field(..., description="Page the photo was taken from")


class Author(BaseModel):
    """
    Author object matching the original PapersWithCode API specification.

    Represents a research paper author with optional Hugging Face integration.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core author identification
    id: str = Field(..., description="Author ID")
    full_name: str = Field(..., description="Author full name")

    # Hugging Face integration (our extension)
    hf_username: Optional[str] = Field(None, description="Hugging Face username")
    hf_id: Optional[str] = Field(None, description="Hugging Face user ID")
    hf_avatar_url: Optional[str] = Field(None, description="Hugging Face avatar URL")
    hf_status: Optional[str] = Field(None, description="Hugging Face account status")
    hf_is_pro: bool = Field(
        default=False, description="Whether user has Hugging Face Pro"
    )
    google_scholar_id: Optional[str] = Field(
        None,
        description=(
            "Google Scholar user ID, set only when the profile lists the author's "
            "papers (author detail only)"
        ),
    )
    photo: Optional[AuthorPhotoInfo] = Field(
        None,
        description=(
            "Freely licensed portrait for authors without an HF avatar "
            "(author detail only)"
        ),
    )

    organization_slug: Optional[str] = Field(
        None,
        description=(
            "Slug of the organization this author row names, such as an arXiv "
            "group author; its page lives at /orgs/{slug} (author detail only)"
        ),
    )

    # Statistics (computed fields)
    paper_count: int = Field(default=0, description="Number of papers by this author")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class Authors(BaseModel):
    """
    Object representing a paginated page of authors.

    Matches the original PapersWithCode API pagination structure.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Author] = Field(..., description="List of authors on this page")


class AuthorSummary(BaseModel):
    """
    Lightweight author summary for list views.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Author ID")
    full_name: str = Field(..., description="Author full name")
    hf_username: Optional[str] = Field(None, description="Hugging Face username")
    paper_count: int = Field(default=0, description="Number of papers by this author")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class Repository(BaseModel):
    """
    GitHub repository (normalized, without direct paper association).

    Represents a unique code repository that can be associated with multiple papers.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core repository identification
    id: str = Field(..., description="Repository ID")

    # Repository details
    url: str = Field(..., description="Full GitHub repository URL")
    owner: Optional[str] = Field(None, description="GitHub username/organization")
    name: Optional[str] = Field(None, description="Repository name")

    # Repository metadata
    num_stars: int = Field(default=0, description="Number of GitHub stars")
    is_official: bool = Field(
        default=False,
        description="Whether this repository is generally considered official",
    )
    source: str = Field(
        default="unknown",
        description="Source of the repository data (pwc_archive, ai_extraction, manual, etc.)",
    )

    # Trending metrics
    trending_score: Optional[float] = Field(
        None,
        description="EMA trending score (stars per hour) - higher means faster recent growth",
    )
    trending_score_updated_at: Optional[datetime] = Field(
        None, description="When the trending score was last calculated"
    )

    # Timestamps
    created_at: Optional[date] = Field(None, description="Repository creation date")
    updated_at: Optional[date] = Field(None, description="Repository last update date")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class RepositoryTrendingTask(BaseModel):
    """Task projection embedded in a repository-trending paper."""

    name: str
    slug: Optional[str]


class RepositoryTrendingRepository(BaseModel):
    """Repository projection embedded in a repository-trending paper."""

    id: str
    url: str
    owner: Optional[str]
    name: Optional[str]
    num_stars: int


class RepositoryTrendingScore(BaseModel):
    """GitHub activity metrics used by the repository-trending endpoint."""

    velocity_24h: float
    trending_score: float
    stars_gained_24h: int


class RepositoryTrendingPaper(BaseModel):
    """One row returned by the repository-velocity trending endpoint."""

    paper_id: str
    arxiv_id: Optional[str]
    source: str
    source_url: Optional[str]
    title: str
    abstract: Optional[str]
    authors: List[str]
    date_published: Optional[date]
    thumbnail_url: Optional[str]
    tasks: List[RepositoryTrendingTask]
    repository: RepositoryTrendingRepository
    trending: RepositoryTrendingScore
    paper_age_days: float
    has_official_implementation: bool
    code_repository_count: int


class HfArtifactSummary(BaseModel):
    """
    Compact Hugging Face artifact summary for paper cards.

    Carries the per-kind counts plus the single "best" (most populated)
    category so the feed card can render one clickable Hugging Face link
    pointing at the most popular artifact type for this paper.
    """

    model_config = ConfigDict(from_attributes=True)

    model_count: int = Field(default=0, description="Number of linked HF models")
    dataset_count: int = Field(default=0, description="Number of linked HF datasets")
    space_count: int = Field(default=0, description="Number of linked HF Spaces")
    best_kind: Optional[str] = Field(
        None,
        description="Most populated artifact kind: 'model', 'dataset', or 'space'",
    )
    best_count: int = Field(default=0, description="Artifact count for the best kind")
    best_url: Optional[str] = Field(
        None,
        description=(
            "URL to the most popular artifact category on Hugging Face. For "
            "ArXiv papers this is the arxiv-filtered listing; for external "
            "papers it is the first stored URL in the winning category."
        ),
    )


class LinkedHfArtifacts(BaseModel):
    """Stored Hugging Face artifact URLs for one paper, most popular first."""

    models: List[str] = Field(default_factory=list)
    datasets: List[str] = Field(default_factory=list)
    spaces: List[str] = Field(default_factory=list)


class RepositoryStarHistory(BaseModel):
    """
    Repository star history snapshot.

    Represents a historical snapshot of a repository's star count at a specific time.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Star history entry ID")
    repository_id: str = Field(..., description="Repository ID")
    num_stars: int = Field(..., description="Number of stars at this snapshot")
    snapshot_at: datetime = Field(..., description="When this snapshot was taken")
    created_at: Optional[datetime] = Field(
        None, description="When this entry was created"
    )

    @field_validator("id", "repository_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure IDs are always strings."""
        return str(v)


class RepositoryStarHistoryList(BaseModel):
    """
    List of repository star history snapshots with metadata.
    """

    model_config = ConfigDict(from_attributes=True)

    repository_id: str = Field(..., description="Repository ID")
    count: int = Field(..., description="Total number of snapshots")
    snapshots: List[RepositoryStarHistory] = Field(
        default_factory=list, description="List of star history snapshots"
    )


class PaperRepository(BaseModel):
    """
    Simple association between a paper and a repository.

    Represents the many-to-many relationship between papers and repositories.
    All metadata is stored in the Repository table itself.
    """

    model_config = ConfigDict(from_attributes=True)

    # Relationship identification
    paper_id: str = Field(..., description="Associated paper ID")
    repository_id: str = Field(..., description="Associated repository ID")

    # Optional embedded repository data for convenience
    repository: Optional[Repository] = Field(
        None, description="Full repository details"
    )

    @field_validator("paper_id", mode="before")
    @classmethod
    def ensure_string_paper_id(cls, v):
        """Ensure paper_id is always a string."""
        return str(v)

    @field_validator("repository_id", mode="before")
    @classmethod
    def ensure_string_repository_id(cls, v):
        """Ensure repository_id is always a string."""
        return str(v)


class Repositories(BaseModel):
    """
    Object representing a paginated page of repositories.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Repository] = Field(
        ..., description="List of repositories on this page"
    )


class ProjectPage(BaseModel):
    """
    Project page showcasing paper work - normalized without direct paper reference.

    Represents a demo site, project website, or other web resource.
    Use PaperProjectPage for relationships between papers and project pages.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core project page identification
    id: str = Field(..., description="Project page ID")

    # Project page details
    url: str = Field(..., description="Full URL to project page")
    is_official: bool = Field(
        default=False,
        description="Whether this is an official project page (use PaperProjectPage.is_official for relationship-specific data)",
    )
    source: str = Field(
        default="unknown",
        description="Source of the project page data (pwc_archive, ai_extraction, manual, etc.)",
    )

    # Timestamps
    created_at: Optional[date] = Field(None, description="Project page creation date")
    updated_at: Optional[date] = Field(
        None, description="Project page last update date"
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class PaperProjectPage(BaseModel):
    """
    Junction table model for many-to-many relationship between papers and project pages.
    Simplified to only contain the two ID columns as requested.
    """

    model_config = ConfigDict(from_attributes=True)

    # Relationship identification (only the two ID columns)
    paper_id: str = Field(..., description="Associated paper ID")
    project_page_id: str = Field(..., description="Associated project page ID")

    @field_validator("paper_id", mode="before")
    @classmethod
    def ensure_string_paper_id(cls, v):
        """Ensure paper_id is always a string."""
        return str(v)

    @field_validator("project_page_id", mode="before")
    @classmethod
    def ensure_string_project_page_id(cls, v):
        """Ensure project_page_id is always a string."""
        return str(v)


class XThread(BaseModel):
    """An X post introducing a paper, with the preview captured when linked."""

    url: str = Field(..., description="Canonical x.com URL of the post")
    tweet_id: str = Field(..., description="X post ID")
    author_name: str = Field(..., description="Display name of the post author")
    author_handle: str = Field(..., description="X handle without the leading @")
    author_avatar_url: Optional[str] = Field(None, description="Author avatar URL")
    text: str = Field(..., description="Post text with links expanded")
    posted_at: Optional[datetime] = Field(
        None, description="When the post was published"
    )
    like_count: Optional[int] = Field(None, description="Likes when previewed")
    reply_count: Optional[int] = Field(None, description="Replies when previewed")
    media_url: Optional[str] = Field(None, description="First photo or video thumbnail")
    media_type: Optional[Literal["photo", "video"]] = Field(
        None, description="Kind of the first attached media"
    )
    video_url: Optional[str] = Field(
        None, description="MP4 of the first video or GIF, for inline playback"
    )
    fetched_at: datetime = Field(..., description="When the preview was captured")


class ProjectPageWithPapers(BaseModel):
    """
    Project page with associated papers information.

    Used for API responses that need to show which papers are associated with a project page.
    """

    model_config = ConfigDict(from_attributes=True)

    # Project page details
    project_page: ProjectPage = Field(..., description="Project page information")

    # Associated papers
    papers: List[str] = Field(..., description="List of associated paper IDs")

    # Relationship metadata (if needed)
    relationships: Optional[List[PaperProjectPage]] = Field(
        None, description="Detailed relationship information"
    )


class ProjectPageCreateRequest(BaseModel):
    """
    Request model for creating a new project page.
    """

    model_config = ConfigDict(from_attributes=True)

    url: str = Field(..., description="Full URL to project page")
    is_official: bool = Field(
        default=False, description="Whether this is an official project page"
    )
    source: str = Field(
        default="manual",
        description="Source of the project page data (pwc_archive, ai_extraction, manual, etc.)",
    )

    _normalize_url = field_validator("url", mode="before")(normalize_public_url)


class ProjectPageUpdateRequest(BaseModel):
    """
    Request model for updating an existing project page.
    All fields are optional.
    """

    model_config = ConfigDict(from_attributes=True)

    url: Optional[str] = Field(None, description="Full URL to project page")
    is_official: Optional[bool] = Field(
        None, description="Whether this is an official project page"
    )
    source: Optional[str] = Field(
        None,
        description="Source of the project page data (pwc_archive, ai_extraction, manual, etc.)",
    )

    _normalize_url = field_validator("url", mode="before")(
        normalize_optional_public_url
    )


class ProjectPages(BaseModel):
    """
    Object representing a paginated page of project pages.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[ProjectPage] = Field(
        ..., description="List of project pages on this page"
    )


class TaskSummary(BaseModel):
    """
    Lightweight task summary for embedding in paper objects.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Task ID")
    name: str = Field(..., description="Task name (e.g., 'Image Classification')")
    slug: Optional[str] = Field(None, description="URL-friendly task slug")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is a string."""
        if v is None:
            return v
        return str(v)


class MethodSummary(BaseModel):
    """
    Lightweight method summary for embedding in paper objects.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Method ID")
    name: str = Field(..., description="Method name")
    slug: Optional[str] = Field(
        None, description="URL-friendly slug (lowercase, hyphenated)"
    )
    introduced_year: Optional[int] = Field(
        None, description="Year the method was introduced"
    )
    source_paper_id: Optional[str] = Field(
        None, description="ID of the canonical paper that introduced this method"
    )
    source_url: Optional[str] = Field(
        None, description="URL to the source paper/article"
    )
    source_title: Optional[str] = Field(
        None, description="Title of the source paper/article"
    )
    code_snippet_url: Optional[str] = Field(
        None, description="URL to code implementation"
    )

    @field_validator("id", "source_paper_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is a string."""
        if v is None:
            return v
        return str(v)


class AbstractMentionPreview(BaseModel):
    """Hover-card content, sent with the paper so cards open without a fetch."""

    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    count: Optional[int] = None
    detail: Optional[str] = None


class AbstractMention(BaseModel):
    """One linked catalog name in a paper abstract."""

    start: int = Field(..., description="Character offset into the abstract")
    end: int = Field(..., description="Exclusive end offset")
    surface: str = Field(..., description="The abstract text at this span")
    entity_type: Literal["method", "benchmark", "framework"]
    slug: str
    name: str
    preview: Optional[AbstractMentionPreview] = None


class FrameworkSummary(BaseModel):
    """Lightweight framework summary embedded in paper responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v) if v is not None else v


class RelatedPaperSummary(BaseModel):
    """
    Lightweight paper summary used to embed predecessor/successor papers
    inside a paper detail response (lineage banner on the frontend).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Paper ID")
    title: str = Field(..., description="Paper title")
    arxiv_id: Optional[str] = Field(None, description="ArXiv ID, if any")
    source: str = Field(
        default="arxiv",
        description="Origin of this paper row: 'arxiv' or 'external'",
    )
    source_url: Optional[str] = Field(
        None, description="Canonical URL for external rows; NULL for ArXiv rows"
    )
    published: Optional[date] = Field(None, description="Paper publication date")
    route_identifier: str = Field(
        ...,
        description=(
            "Identifier the frontend should use when building the paper detail "
            "URL: ArXiv ID for ArXiv rows, internal numeric ID otherwise."
        ),
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class OrganizationSummary(BaseModel):
    """Lightweight organization summary embedded in paper responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Organization ID")
    name: str = Field(..., description="Organization name (e.g., 'NVIDIA')")
    slug: str = Field(..., description="URL-friendly slug (e.g., 'nvidia')")
    logo_url: Optional[str] = Field(None, description="Organization logo image URL")
    source: Literal["manual", "hf_org_papers", "curation", "openalex"] = Field(
        ...,
        description=(
            "Association provenance: 'manual', 'hf_org_papers', 'curation' "
            "(read from the paper by the enrichment curator), or 'openalex' "
            "(OpenAlex author affiliations)"
        ),
    )
    added_by_hf_username: Optional[str] = Field(
        None,
        description="HF username that manually added this association, when known",
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


# Resolve the paper model's forward references within this bounded module.
Paper.model_rebuild()

__all__ = [
    "GithubRepositoryPreview",
    "PaperBucketArtifact",
    "PaperBucketCopyRequest",
    "PaperBucketCopyError",
    "PaperBucketCopyResponse",
    "Paper",
    "PaperFeedScope",
    "PaperDateRange",
    "AppliedAuthorFilter",
    "Papers",
    "PaperSummary",
    "PaperSearchResults",
    "PaperSearchFeedResults",
    "RelatedPaperRecommendation",
    "PaperVersion",
    "PaperVersions",
    "VersionComparison",
    "AuthorLink",
    "Author",
    "Authors",
    "AuthorSummary",
    "Repository",
    "RepositoryTrendingTask",
    "RepositoryTrendingRepository",
    "RepositoryTrendingScore",
    "RepositoryTrendingPaper",
    "HfArtifactSummary",
    "LinkedHfArtifacts",
    "RepositoryStarHistory",
    "RepositoryStarHistoryList",
    "PaperRepository",
    "Repositories",
    "ProjectPage",
    "PaperProjectPage",
    "ProjectPageWithPapers",
    "ProjectPageCreateRequest",
    "ProjectPageUpdateRequest",
    "ProjectPages",
    "TaskSummary",
    "MethodSummary",
    "FrameworkSummary",
    "RelatedPaperSummary",
    "OrganizationSummary",
]


class PaperReferenceQuery(BaseModel):
    """One bibliography entry a client wants matched to a catalog paper."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Client identifier echoed back on the matching result",
    )
    arxiv_id: Optional[str] = Field(
        None,
        max_length=64,
        description="Explicit arXiv identifier found in the entry, if any",
    )
    titles: List[str] = Field(
        default_factory=list,
        max_length=8,
        description="Candidate title strings extracted from the entry",
    )

    @field_validator("titles")
    @classmethod
    def _bound_title_length(cls, titles: List[str]) -> List[str]:
        return [title[:300] for title in titles]


class PaperLookupRequest(BaseModel):
    """Batch of bibliography entries to resolve in one round trip."""

    model_config = ConfigDict(extra="forbid")

    references: List[PaperReferenceQuery] = Field(..., min_length=1, max_length=500)


class ResolvedPaperReference(BaseModel):
    """A bibliography entry with the catalog paper it resolved to, if any."""

    key: str
    matched_by: Optional[Literal["arxiv_id", "title"]] = Field(
        None, description="Which evidence produced the match"
    )
    paper: Optional[Paper] = None


class PaperLookupResponse(BaseModel):
    references: List[ResolvedPaperReference]


class PaperSuggestedQuestionsResponse(BaseModel):
    questions: List[str] = Field(
        default_factory=list,
        description="Up to three starter questions to ask the assistant about the paper",
    )
