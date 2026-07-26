"""
Pydantic models for API responses.

These models match the original PapersWithCode API specification but are adapted
to our database schema. The main differences from the original API:
- No nips_id field (not supported in our schema)
- Added version and is_latest_version fields for ArXiv version tracking
- Enhanced URL construction based on our schema design
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic import ConfigDict


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
            "Per-author entries parallel to `authors`, carrying the HF "
            "username when the author is mapped to a Hugging Face profile. "
            "Used by the frontend to link names to huggingface.co/{user}."
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

    # Associated resources (optional, populated when requested)
    repositories: Optional[List["Repository"]] = Field(
        None, description="GitHub repositories associated with this paper"
    )
    project_pages: Optional[List["ProjectPage"]] = Field(
        None, description="Project pages associated with this paper"
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
            "e.g. NVIDIA. Powers the org logo tags on the paper page."
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


# Additional models for extended functionality


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


# Error models


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    error: str = Field(default="Validation error", description="Error type")
    detail: List[dict] = Field(..., description="Validation error details")


# Author models


class AuthorLink(BaseModel):
    """Minimal author entry used inline on Paper responses.

    Parallels `Paper.authors` and carries an optional `hf_username` so the
    frontend can link author names to their Hugging Face profile.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., description="Author display name")
    hf_username: Optional[str] = Field(
        None,
        description="Hugging Face username, when the author is mapped to a HF profile",
    )


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


# Repository and Project Page models


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


class Area(BaseModel):
    """
    Research area object representing a broad field of AI/ML research.

    Examples: Vision, Video, Language, Audio, General, Other.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core area identification
    id: str = Field(..., description="Area ID")
    name: str = Field(..., description="Area name (e.g., 'Vision')")
    description: Optional[str] = Field(None, description="Area description")

    # Timestamps
    created_at: Optional[datetime] = Field(None, description="Area creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class Areas(BaseModel):
    """
    Object representing a paginated page of areas.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Area] = Field(..., description="List of areas on this page")


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


class BenchmarkSummary(BaseModel):
    """
    Lightweight benchmark/dataset summary for embedding in paper objects.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Dataset (benchmark) ID")
    name: str = Field(..., description="Dataset name")
    slug: Optional[str] = Field(None, description="URL-friendly dataset slug")
    full_name: Optional[str] = Field(None, description="Dataset full name")
    introduced_year: Optional[int] = Field(
        None, description="Year the dataset was introduced"
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is a string."""
        if v is None:
            return v
        return str(v)


class LeaderboardRankSummary(BaseModel):
    """
    Lightweight leaderboard placement used to render SOTA/#2/#3 badges on
    paper cards. One entry per benchmark (dataset) the paper ranks top-3 on.
    """

    model_config = ConfigDict(from_attributes=True)

    evaluation_id: str = Field(
        ..., description="Evaluation row used to highlight this placement"
    )
    dataset_name: str = Field(..., description="Benchmark (dataset) name")
    dataset_slug: Optional[str] = Field(
        None, description="URL-friendly dataset slug for the benchmark page link"
    )
    best_rank: int = Field(..., description="Best rank on this benchmark (1, 2, or 3)")
    best_metric: Optional[str] = Field(
        None, description="Metric the rank was computed on"
    )
    task_slug: Optional[str] = Field(
        None, description="Task slug used to select the matching leaderboard"
    )


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


class Method(BaseModel):
    """
    Method object representing an AI/ML method or technique.

    Methods are techniques, algorithms, or approaches used in machine learning
    research. Examples: ResNet, Transformer, BERT, Adam Optimizer, etc.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core method identification
    id: str = Field(..., description="Method ID")
    name: str = Field(..., description="Method short name (e.g., 'ResNet', 'BERT')")
    slug: Optional[str] = Field(
        None, description="URL-friendly slug (lowercase, hyphenated)"
    )
    full_name: Optional[str] = Field(None, description="Method full name")
    description: Optional[str] = Field(None, description="Method description")
    keywords: Optional[str] = Field(
        None, description="Comma-separated keywords for matching papers to this method"
    )

    # Area assignment (methods belong to one area, like tasks)
    area_id: Optional[str] = Field(None, description="ID of the research area")

    # Method metadata
    introduced_year: Optional[int] = Field(
        None, description="Year the method was introduced"
    )
    source_paper_id: Optional[str] = Field(
        None, description="ID of the canonical paper that introduced this method"
    )
    source_url: Optional[str] = Field(
        None, description="URL to the source that introduced the method"
    )
    source_title: Optional[str] = Field(
        None, description="Title of the source that introduced the method"
    )
    code_snippet_url: Optional[str] = Field(
        None, description="URL to a code snippet implementing the method"
    )
    image_url: Optional[str] = Field(
        None,
        description="URL to an image/diagram representing the method (e.g., architecture diagram)",
    )
    image_credit: Optional[str] = Field(
        None,
        description="Attribution/credit for the method image (e.g., paper URL, source URL)",
    )

    # Collection metadata (for grouped methods)
    collection_name: Optional[str] = Field(
        None, description="Name of the method collection"
    )
    collection_description: Optional[str] = Field(
        None, description="Description of the method collection"
    )
    collection_parent: Optional[str] = Field(None, description="Parent collection name")

    # Metadata
    paper_count: Optional[int] = Field(
        None, description="Number of papers using this method"
    )

    # Timestamps
    created_at: Optional[datetime] = Field(
        None, description="Method creation timestamp"
    )
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", "area_id", "source_paper_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure IDs are strings."""
        if v is None:
            return v
        return str(v)


class Methods(BaseModel):
    """
    Object representing a paginated page of methods.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Method] = Field(..., description="List of methods on this page")


class Task(BaseModel):
    """
    Task object representing a specific AI/ML task.

    Tasks are hierarchical and can have parent-child relationships.
    Examples: Image Classification, Object Detection, Language Modeling, etc.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core task identification
    id: str = Field(..., description="Task ID")
    name: str = Field(..., description="Task name (e.g., 'Image Classification')")
    description: Optional[str] = Field(None, description="Task description")
    research_trends: List[str] = Field(
        default_factory=list,
        description="Three editorial bullets summarizing the task's research direction",
    )
    slug: Optional[str] = Field(None, description="URL-friendly task slug")
    keywords: Optional[str] = Field(
        None, description="Comma-separated keywords for matching papers to this task"
    )

    # Hierarchical structure
    parent_id: Optional[str] = Field(None, description="ID of the parent task")
    area_id: Optional[str] = Field(None, description="ID of the research area")
    level: int = Field(default=0, description="Depth in task hierarchy (0=top-level)")

    # Metadata
    paper_count: Optional[int] = Field(
        None, description="Number of papers for this task"
    )
    image_url: Optional[str] = Field(
        None, description="URL to task image/visual representation"
    )
    image_credit: Optional[str] = Field(
        None, description="Image source/credit information"
    )

    # Visibility in user-facing pickers (the /tasks taxonomy and the paper
    # task-tagging dropdown). Hidden tasks still exist and are reachable by
    # direct slug, but are filtered out of the taxonomy index and selectors.
    is_visible: bool = Field(
        default=True,
        description=(
            "Whether this task is surfaced in user-facing pickers (the /tasks "
            "taxonomy index and the paper-tagging dropdown). False hides the "
            "task from those surfaces; it remains reachable by direct slug/id."
        ),
    )

    # Timestamps
    created_at: Optional[datetime] = Field(None, description="Task creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", "parent_id", "area_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure IDs are strings."""
        if v is None:
            return v
        return str(v)


class Tasks(BaseModel):
    """
    Object representing a paginated page of tasks.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Task] = Field(..., description="List of tasks on this page")


class TrendingTask(Task):
    """
    Task augmented with publication-rate trending metadata.

    Surfaces domains whose share of recent papers is higher than their
    historical share, i.e. domains gaining momentum rather than just
    domains with large all-time paper counts.
    """

    recent_paper_count: int = Field(
        ..., description="Distinct papers in this task within the recent window"
    )
    baseline_paper_count: int = Field(
        ..., description="Distinct papers in this task within the baseline window"
    )
    share_lift: float = Field(
        ...,
        description=(
            "Ratio of recent share to baseline share. Values > 1.0 mean the "
            "task is over-indexed in recent papers compared with its history."
        ),
    )
    trend_score: float = Field(
        ...,
        description="Composite score = share_lift * ln(1 + recent_paper_count)",
    )


class TrendingTasks(BaseModel):
    """Container for the homepage Trending Domains sidebar."""

    model_config = ConfigDict(from_attributes=True)

    results: List[TrendingTask] = Field(
        ...,
        description=("Tasks sorted by descending share lift (trend score breaks ties)"),
    )
    recent_days: int = Field(..., description="Length of the recent window (days)")
    baseline_days: int = Field(
        ...,
        description="Length of the baseline window preceding the recent window (days)",
    )


class AreaWithTasks(BaseModel):
    """
    Research area together with its tasks and aggregated paper counts.

    Used by the taxonomy index endpoint to return the entire areas-and-tasks
    tree in a single response, avoiding a fan-out of one HTTP request per area
    from the frontend.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Area ID")
    name: str = Field(..., description="Area name (e.g., 'Vision')")
    description: Optional[str] = Field(None, description="Area description")
    tasks: List[Task] = Field(
        default_factory=list,
        description="Tasks belonging to this area (with paper counts)",
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class AreasWithTasks(BaseModel):
    """Container for the full areas-with-tasks taxonomy."""

    model_config = ConfigDict(from_attributes=True)

    results: List[AreaWithTasks] = Field(
        ..., description="All research areas, each populated with its tasks"
    )


class ConferenceDeadline(BaseModel):
    """A single submission/abstract/rebuttal deadline for a conference."""

    model_config = ConfigDict(from_attributes=True)

    type: Optional[str] = Field(
        None, description="Deadline type (e.g., submission, abstract, rebuttal)"
    )
    label: Optional[str] = Field(None, description="Human-readable deadline label")
    deadline_at: datetime = Field(..., description="Absolute deadline instant (UTC)")
    timezone: Optional[str] = Field(
        None, description="Original source timezone string (e.g., AoE, UTC-8)"
    )


class Conference(BaseModel):
    """Conference object with normalized metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Conference ID")
    name: str = Field(..., description="Conference name (e.g., 'CVPR 2026')")
    slug: str = Field(..., description="URL-friendly slug (e.g., 'cvpr-2026')")
    short_name: Optional[str] = Field(None, description="Short name (e.g., 'CVPR')")
    year: Optional[int] = Field(None, description="Conference year")
    url: Optional[str] = Field(None, description="Official conference website URL")
    start_date: Optional[date] = Field(None, description="Conference start date")
    end_date: Optional[date] = Field(None, description="Conference end date")
    venue: Optional[str] = Field(None, description="Venue name")
    location: Optional[str] = Field(None, description="City / country location")
    description: Optional[str] = Field(None, description="Conference description")
    image_url: Optional[str] = Field(
        None, description="Hero image URL for the conference page"
    )
    image_credit: Optional[str] = Field(
        None, description="Markdown credit for the hero image"
    )
    hf_url: Optional[str] = Field(
        None, description="Hugging Face dataset URL for accepted papers"
    )
    paper_count: Optional[int] = Field(
        0, description="Number of papers linked to this conference"
    )
    tier: Optional[str] = Field(
        None, description="ERA conference ranking (a/b/c); a is top tier"
    )
    tags: List[str] = Field(
        default_factory=list, description="AI-domain tags for filtering"
    )
    country: Optional[str] = Field(
        None, description="Country the conference is held in"
    )
    city: Optional[str] = Field(None, description="City the conference is held in")
    deadlines: List[ConferenceDeadline] = Field(
        default_factory=list, description="Submission/abstract/rebuttal deadlines"
    )
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class Conferences(BaseModel):
    """Container for a list of conferences."""

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of conferences")
    results: List[Conference] = Field(..., description="Conference list")


class ConferenceDeadlines(BaseModel):
    """Container for conferences that have upcoming/past deadlines."""

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of conferences with deadlines")
    results: List[Conference] = Field(
        ..., description="Conferences with their deadline lists"
    )


class ConferenceTaskSummary(BaseModel):
    """Task summary with conference-scoped paper count."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Task ID")
    name: str = Field(..., description="Task name")
    slug: Optional[str] = Field(None, description="Task slug")
    paper_count: int = Field(0, description="Papers in this conference for the task")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class ConferenceAreaWithTasks(BaseModel):
    """Research area with conference-scoped task paper counts."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Area ID")
    name: str = Field(..., description="Area name")
    description: Optional[str] = Field(None, description="Area description")
    tasks: List[ConferenceTaskSummary] = Field(
        default_factory=list,
        description="Visible tasks with conference-scoped paper counts",
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class ConferenceAreasWithTasks(BaseModel):
    """Conference taxonomy: areas and tasks scoped to one conference."""

    model_config = ConfigDict(from_attributes=True)

    conference: Conference = Field(..., description="Conference metadata")
    total_paper_count: int = Field(
        ..., description="Total papers linked to this conference"
    )
    oral_paper_count: int = Field(
        0, description="Papers with an oral presentation at this conference"
    )
    spotlight_paper_count: int = Field(
        0, description="Papers with a spotlight presentation at this conference"
    )
    outstanding_paper_count: int = Field(
        0,
        description="Papers with an outstanding-paper or honorable-mention award",
    )
    best_paper_finalist_paper_count: int = Field(
        0,
        description="Papers with a best-paper-finalist award at this conference",
    )
    results: List[ConferenceAreaWithTasks] = Field(
        ..., description="Areas populated with conference-scoped task counts"
    )


class OrganizationSummary(BaseModel):
    """Lightweight organization summary embedded in paper responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Organization ID")
    name: str = Field(..., description="Organization name (e.g., 'NVIDIA')")
    slug: str = Field(..., description="URL-friendly slug (e.g., 'nvidia')")
    logo_url: Optional[str] = Field(None, description="Organization logo image URL")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class Organization(BaseModel):
    """Organization object with normalized metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Organization ID")
    name: str = Field(..., description="Organization name (e.g., 'NVIDIA')")
    slug: str = Field(..., description="URL-friendly slug (e.g., 'nvidia')")
    hf_url: Optional[str] = Field(
        None, description="Hugging Face organization URL (e.g., huggingface.co/nvidia)"
    )
    logo_url: Optional[str] = Field(None, description="Organization logo image URL")
    website_url: Optional[str] = Field(None, description="Official website URL")
    github_url: Optional[str] = Field(None, description="GitHub organization URL")
    description: Optional[str] = Field(None, description="Organization description")
    paper_count: Optional[int] = Field(
        0, description="Number of papers linked to this organization"
    )
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class Organizations(BaseModel):
    """Container for a list of organizations."""

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of organizations")
    results: List[Organization] = Field(..., description="Organization list")


class OrganizationAreaWithTasks(BaseModel):
    """Research area with organization-scoped task paper counts."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Area ID")
    name: str = Field(..., description="Area name")
    description: Optional[str] = Field(None, description="Area description")
    tasks: List[ConferenceTaskSummary] = Field(
        default_factory=list,
        description="Visible tasks with organization-scoped paper counts",
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class OrganizationAreasWithTasks(BaseModel):
    """Organization taxonomy: areas and tasks scoped to one organization."""

    model_config = ConfigDict(from_attributes=True)

    organization: Organization = Field(..., description="Organization metadata")
    total_paper_count: int = Field(
        ..., description="Total papers linked to this organization"
    )
    results: List[OrganizationAreaWithTasks] = Field(
        ..., description="Areas populated with organization-scoped task counts"
    )


class TaskCreateRequest(BaseModel):
    """
    Request model for creating a new task.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., description="Task name")
    description: Optional[str] = Field(None, description="Task description")
    keywords: Optional[str] = Field(
        None, description="Comma-separated keywords for matching papers to this task"
    )
    area_id: Optional[int] = Field(None, description="Research area ID")
    parent_id: Optional[int] = Field(None, description="Parent task ID (for subtasks)")
    image_url: Optional[str] = Field(None, description="Task image URL")
    image_credit: Optional[str] = Field(None, description="Image credit/attribution")


class Dataset(BaseModel):
    """
    Dataset object matching the original PapersWithCode API specification.

    Represents a benchmark dataset used for evaluating AI/ML models.
    Examples: ImageNet, COCO, SQuAD, GLUE
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Dataset ID")
    name: str = Field(..., description="Dataset name")
    slug: Optional[str] = Field(None, description="URL-friendly dataset slug")
    full_name: Optional[str] = Field(None, description="Dataset full name")
    description: Optional[str] = Field(None, description="Dataset description")
    url: Optional[str] = Field(
        None, description="URL for dataset download or information"
    )
    hf_url: Optional[str] = Field(None, description="Hugging Face dataset URL")

    # Additional metadata from PapersWithCode
    short_description: Optional[str] = Field(
        None, description="Short description/summary"
    )
    homepage: Optional[str] = Field(None, description="Official homepage URL")

    # Dataset hierarchy and variants
    parent_dataset_id: Optional[str] = Field(
        None, description="Parent dataset ID if this is a variant"
    )
    variant_type: Optional[str] = Field(
        None,
        description="Type of variant: split, variant, subset, derived, or augmented",
    )
    split_name: Optional[str] = Field(
        None, description="Name of the split (e.g., test-dev, minival, val2017)"
    )

    # Image URLs
    image_url: Optional[str] = Field(None, description="Main image URL for the dataset")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail image URL")
    verified_image_url: Optional[str] = Field(
        None, description="Verified image URL from PWC"
    )

    # Paper reference
    introducing_paper_id: Optional[str] = Field(
        None, description="ID of paper that introduced this dataset"
    )
    introducing_paper_title: Optional[str] = Field(
        None, description="Title of paper that introduced this dataset"
    )
    paper_url: Optional[str] = Field(
        None, description="URL to paper that introduced this dataset"
    )

    # Licensing
    license_name: Optional[str] = Field(
        None, description="License name (e.g., MIT, Apache 2.0)"
    )
    license_url: Optional[str] = Field(None, description="URL to license details")

    # Dates
    introduced_year: Optional[int] = Field(
        None, description="Year the dataset was introduced"
    )
    introduced_date: Optional[date] = Field(
        None, description="Date when dataset was introduced"
    )

    # Array fields
    modalities: Optional[List[str]] = Field(
        None, description="Data modalities (e.g., ['Images', 'Videos'])"
    )
    languages: Optional[List[str]] = Field(
        None, description="Languages (e.g., ['English', 'Chinese'])"
    )
    variants: Optional[List[str]] = Field(
        None, description="Dataset variants/splits (e.g., ['COCO test-dev'])"
    )

    # Usage and warnings
    num_papers: Optional[int] = Field(
        None, description="Number of papers using this dataset"
    )
    warning: Optional[str] = Field(
        None, description="Warning or note about the dataset"
    )

    # PWC source
    pwc_url: Optional[str] = Field(None, description="Original PapersWithCode URL")

    # Legacy fields (kept for backwards compatibility)
    paper_count: Optional[int] = Field(
        None, description="Number of papers using this dataset (alias for num_papers)"
    )
    task_count: Optional[int] = Field(
        None, description="Number of tasks associated with this dataset"
    )
    featured_rank: Optional[int] = Field(
        None,
        description="Task-specific featured ordering rank when returned for a task",
    )
    supports_harness: bool = Field(
        False,
        description="Whether this task-dataset leaderboard allows evaluation harness values",
    )
    best_model_name: Optional[str] = Field(
        None,
        description="Top-ranked model on this benchmark for the scoped task",
    )

    # Allowed metrics for this dataset
    allowed_metrics: Optional[List[str]] = Field(
        None, description="List of metric names allowed for evaluations on this dataset"
    )

    # Optionally embedded introducing paper. Populated only when the request
    # passes `?include_paper=true`. Lets the benchmark page collapse the
    # previous dataset → paper waterfall into a single round trip (PLAN.md §5).
    introducing_paper: Optional["IntroducingPaper"] = Field(
        None,
        description="Lightweight introducing-paper embed. Present only when the request asked for it.",
    )

    @field_validator("id", "parent_dataset_id", "introducing_paper_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is a string."""
        if v is None:
            return v
        return str(v)


class IntroducingPaper(BaseModel):
    """
    Minimal projection of a paper used as an embed inside `Dataset` when callers
    request `?include_paper=true`.  Only carries the fields the benchmark page
    needs (link by arxiv_id, headline, year), so we don't pay the full Paper
    serialization cost (authors, repositories, methods, …) on every benchmark
    page load.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Paper ID")
    arxiv_id: Optional[str] = Field(None, description="ArXiv ID, if any")
    title: str = Field(..., description="Paper title")
    published: Optional[date] = Field(None, description="Publication date")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        if v is None:
            return v
        return str(v)


Dataset.model_rebuild()


class Datasets(BaseModel):
    """
    Object representing a paginated page of datasets.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Dataset] = Field(..., description="List of datasets on this page")


class TaskSubtaskBenchmarks(BaseModel):
    """Benchmark preview list for a single child task on the task page."""

    model_config = ConfigDict(from_attributes=True)

    subtask_id: str = Field(..., description="Child task ID")
    benchmarks: List[Dataset] = Field(
        default_factory=list, description="Top benchmarks for the child task"
    )

    @field_validator("subtask_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v) if v is not None else v


class RecommendedFramework(BaseModel):
    """GitHub repository recommended as a starting point for a task."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Repository ID")
    url: str = Field(..., description="GitHub repository URL")
    owner: Optional[str] = Field(None, description="GitHub repository owner")
    name: Optional[str] = Field(None, description="GitHub repository name")
    num_stars: int = Field(default=0, description="Current GitHub star count")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v) if v is not None else v


class TaskPage(BaseModel):
    """
    Bundled task-page payload.

    Collapses the task-detail page's initial request fan-out (detail, parents,
    sister tasks, recommended frameworks, children, direct benchmarks, and
    per-child benchmark previews) into a single response so the frontend
    issues one round trip instead of many.
    """

    model_config = ConfigDict(from_attributes=True)

    task: Task = Field(..., description="The task this page is for")
    parents: List[Task] = Field(
        default_factory=list, description="Ancestor tasks, nearest parent first"
    )
    sisters: List[Task] = Field(
        default_factory=list,
        description=(
            "Explicitly configured sister tasks for this task, ordered by "
            "display_order (from `task_sister_tasks`). Independent of area."
        ),
    )
    recommended_frameworks: List[RecommendedFramework] = Field(
        default_factory=list,
        description=(
            "Ordered GitHub repositories recommended for this task, from "
            "`task_recommended_frameworks`, with current star counts"
        ),
    )
    children: List[Task] = Field(
        default_factory=list, description="Direct visible child tasks"
    )
    benchmarks: List[Dataset] = Field(
        default_factory=list, description="Benchmarks directly tied to this task"
    )
    subtask_benchmarks: List[TaskSubtaskBenchmarks] = Field(
        default_factory=list,
        description="Per-child benchmark previews, aligned with `children`",
    )


class DatasetCreateRequest(BaseModel):
    """
    Request model for creating a new dataset.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., description="Dataset name")
    full_name: Optional[str] = Field(None, description="Dataset full name")
    description: str = Field(..., description="Dataset description")
    url: Optional[str] = Field(None, description="Dataset URL")
    hf_url: Optional[str] = Field(None, description="Hugging Face dataset URL")
    paper_url: Optional[str] = Field(
        None, description="URL to paper that introduced this dataset"
    )
    task_ids: List[int] = Field(
        ..., description="List of task IDs to link this dataset to"
    )

    # Additional PWC fields
    short_description: Optional[str] = Field(
        None, description="Short description/summary"
    )
    homepage: Optional[str] = Field(None, description="Official homepage URL")
    image_url: Optional[str] = Field(None, description="Main image URL")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail image URL")
    verified_image_url: Optional[str] = Field(None, description="Verified image URL")
    license_name: Optional[str] = Field(None, description="License name")
    license_url: Optional[str] = Field(None, description="License URL")
    introduced_date: Optional[date] = Field(None, description="Introduction date")
    modalities: Optional[List[str]] = Field(None, description="Data modalities")
    languages: Optional[List[str]] = Field(None, description="Languages")
    variants: Optional[List[str]] = Field(None, description="Dataset variants")
    num_papers: Optional[int] = Field(None, description="Number of papers")
    warning: Optional[str] = Field(None, description="Warning/note")
    pwc_url: Optional[str] = Field(None, description="PapersWithCode URL")


class DatasetUpdateRequest(BaseModel):
    """
    Request model for updating an existing dataset.
    """

    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, description="Dataset name")
    full_name: Optional[str] = Field(None, description="Dataset full name")
    description: Optional[str] = Field(None, description="Dataset description")
    url: Optional[str] = Field(None, description="Dataset URL")
    hf_url: Optional[str] = Field(None, description="Hugging Face dataset URL")
    paper_url: Optional[str] = Field(
        None, description="URL to paper that introduced this dataset"
    )

    # Additional PWC fields
    short_description: Optional[str] = Field(
        None, description="Short description/summary"
    )
    homepage: Optional[str] = Field(None, description="Official homepage URL")
    image_url: Optional[str] = Field(None, description="Main image URL")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail image URL")
    verified_image_url: Optional[str] = Field(None, description="Verified image URL")
    license_name: Optional[str] = Field(None, description="License name")
    license_url: Optional[str] = Field(None, description="License URL")
    introduced_date: Optional[date] = Field(None, description="Introduction date")
    modalities: Optional[List[str]] = Field(None, description="Data modalities")
    languages: Optional[List[str]] = Field(None, description="Languages")
    variants: Optional[List[str]] = Field(None, description="Dataset variants")
    num_papers: Optional[int] = Field(None, description="Number of papers")
    warning: Optional[str] = Field(None, description="Warning/note")
    pwc_url: Optional[str] = Field(None, description="PapersWithCode URL")


# Evaluation models


class Evaluation(BaseModel):
    """
    Benchmark evaluation result.

    Represents a performance evaluation of a paper/model on a specific task and dataset.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Evaluation ID")
    paper_id: str = Field(..., description="Paper ID that produced this evaluation")
    task_id: str = Field(..., description="Task ID being evaluated")
    dataset_id: str = Field(..., description="Dataset ID used for evaluation")
    model_name: Optional[str] = Field(None, description="Name of the model/method used")
    harness: Optional[str] = Field(
        None,
        description=(
            "Optional harness/runtime used to evaluate the model "
            "(e.g. 'Claude Code', 'Terminus'). Benchmarks like Terminal-Bench "
            "are model+harness combinations and surface this alongside the model."
        ),
    )
    methodology: Optional[str] = Field(None, description="Methodology description")
    metrics: dict = Field(
        ...,
        description="Dictionary of metric names and values (e.g., {'AP': '44.9', 'AP50': '64.7'})",
    )
    uses_additional_data: bool = Field(
        default=False, description="Whether additional data was used beyond the dataset"
    )
    is_open: bool = Field(
        default=True,
        description=(
            "Whether the evaluated model is open-source. True by default; "
            "False for closed-source models (proprietary APIs, unreleased "
            "flagship LLMs) so the frontend can optionally hide them."
        ),
    )
    best_rank: Optional[int] = Field(
        None, description="Best rank achieved in leaderboard"
    )
    best_metric: Optional[str] = Field(
        None, description="Name of the best performing metric"
    )
    evaluated_on: Optional[date] = Field(
        None, description="Date when evaluation was performed"
    )
    external_source_url: Optional[str] = Field(
        None, description="URL to external source (e.g., competition)"
    )
    source_url: Optional[str] = Field(
        None, description="Canonical URL or paper reference where the score was found"
    )
    external: bool = Field(
        default=False,
        description="True when source_url is independent of the evaluated paper/model",
    )
    is_external: bool = Field(
        default=False,
        description=(
            "Legacy alias for external. True when source_url is independent "
            "of the evaluated paper/model."
        ),
    )
    num_parameters: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Raw number of model parameters for this evaluation row "
            "(e.g. 7000000000 for a 7B model). Optional metadata that lets "
            "future leaderboards filter and visualize by model size."
        ),
    )
    hf_model_url: Optional[str] = Field(
        None,
        description=(
            "Optional Hugging Face model page for the evaluated model "
            "(e.g. https://huggingface.co/MiniMaxAI/MiniMax-M3). When present, "
            "the frontend turns the model name into a link to this page."
        ),
    )
    created_at: datetime = Field(..., description="Timestamp when record was created")
    updated_at: datetime = Field(
        ..., description="Timestamp when record was last updated"
    )

    # Additional fields for frontend display
    paper_title: Optional[str] = Field(None, description="Title of the paper")
    paper_arxiv_id: Optional[str] = Field(None, description="ArXiv ID of the paper")
    paper_published_date: Optional[str] = Field(
        None, description="Publication date of the paper"
    )
    code_url: Optional[str] = Field(
        None, description="URL to the code repository (GitHub)"
    )
    result_url: Optional[str] = Field(None, description="URL to the result/demo page")
    task_name: Optional[str] = Field(None, description="Name of the task")
    task_slug: Optional[str] = Field(None, description="URL-friendly slug of the task")
    dataset_name: Optional[str] = Field(None, description="Name of the dataset")
    dataset_slug: Optional[str] = Field(
        None, description="URL-friendly slug of the dataset"
    )

    @field_validator("id", "paper_id", "task_id", "dataset_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is a string."""
        if v is None:
            return v
        return str(v)


class Evaluations(BaseModel):
    """
    Object representing a paginated page of evaluations.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Evaluation] = Field(
        ..., description="List of evaluations on this page"
    )


class EvaluationCreateRequest(BaseModel):
    """
    Request model for creating a new evaluation.
    """

    model_config = ConfigDict(from_attributes=True)

    paper_id: int = Field(..., description="Paper ID")
    task_id: int = Field(..., description="Task ID")
    dataset_id: int = Field(..., description="Dataset ID")
    model_name: Optional[str] = Field(None, description="Model name")
    harness: Optional[str] = Field(
        None,
        description="Optional harness/runtime used to evaluate the model",
    )
    methodology: Optional[str] = Field(None, description="Methodology description")
    metrics: dict = Field(..., description="Dictionary of metrics")
    uses_additional_data: bool = Field(
        default=False, description="Uses additional data"
    )
    is_open: bool = Field(
        default=True,
        description=(
            "Whether the evaluated model is open-source. True by default; "
            "set False for closed-source models."
        ),
    )
    best_rank: Optional[int] = Field(None, description="Best rank")
    best_metric: Optional[str] = Field(None, description="Best metric name")
    evaluated_on: Optional[date] = Field(None, description="Evaluation date")
    external_source_url: Optional[str] = Field(None, description="External source URL")
    source_url: Optional[str] = Field(
        None, description="Canonical source URL or paper reference for this score"
    )
    num_parameters: Optional[int] = Field(
        None,
        ge=0,
        description=("Raw number of model parameters (e.g. 7000000000 for a 7B model)"),
    )
    hf_model_url: Optional[str] = Field(
        None,
        description=(
            "Optional Hugging Face model page for the evaluated model "
            "(e.g. https://huggingface.co/MiniMaxAI/MiniMax-M3)"
        ),
    )


class EvaluationUpdateRequest(BaseModel):
    """
    Request model for updating an existing evaluation.
    """

    model_config = ConfigDict(from_attributes=True)

    task_id: Optional[int] = Field(None, description="Task ID")
    dataset_id: Optional[int] = Field(None, description="Dataset ID")
    model_name: Optional[str] = Field(None, description="Model name")
    harness: Optional[str] = Field(
        None,
        description="Optional harness/runtime used to evaluate the model",
    )
    methodology: Optional[str] = Field(None, description="Methodology description")
    metrics: Optional[dict] = Field(None, description="Dictionary of metrics")
    uses_additional_data: Optional[bool] = Field(
        None, description="Uses additional data"
    )
    is_open: Optional[bool] = Field(
        None,
        description="Whether the evaluated model is open-source.",
    )
    best_rank: Optional[int] = Field(None, description="Best rank")
    best_metric: Optional[str] = Field(None, description="Best metric name")
    evaluated_on: Optional[date] = Field(None, description="Evaluation date")
    external_source_url: Optional[str] = Field(None, description="External source URL")
    source_url: Optional[str] = Field(
        None, description="Canonical source URL or paper reference for this score"
    )
    num_parameters: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Raw number of model parameters (e.g. 7000000000 for a 7B model). "
            "Pass `null` to clear an existing value."
        ),
    )
    hf_model_url: Optional[str] = Field(
        None,
        description=(
            "Optional Hugging Face model page for the evaluated model "
            "(e.g. https://huggingface.co/MiniMaxAI/MiniMax-M3). "
            "Pass `null` to clear an existing value."
        ),
    )


# Metric models


class Metric(BaseModel):
    """
    Metric definition with ranking direction and scale.

    Defines evaluation metrics and whether they should rank with higher or lower values as better.
    Also includes the canonical scale for proper value normalization.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Metric ID")
    name: str = Field(..., description="Metric name (e.g., 'WER', 'AP', 'Accuracy')")
    full_name: Optional[str] = Field(None, description="Full metric name")
    direction: str = Field(
        ..., description="Ranking direction: 'higher_is_better' or 'lower_is_better'"
    )
    scale: Optional[str] = Field(
        None,
        description="Canonical scale for metric values (e.g., '0-1', '0-100', 'percentage', 'unbounded')",
    )
    description: Optional[str] = Field(None, description="Metric description")
    created_at: datetime = Field(..., description="Timestamp when record was created")
    updated_at: datetime = Field(
        ..., description="Timestamp when record was last updated"
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is a string."""
        if v is None:
            return v
        return str(v)


class Metrics(BaseModel):
    """
    Object representing a paginated page of metrics.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Metric] = Field(..., description="List of metrics on this page")


class MetricDirections(BaseModel):
    """
    Map of metric names to their ranking directions.

    Optimized response for frontend to quickly lookup metric directions.
    """

    directions: dict[str, str] = Field(
        ...,
        description="Dictionary mapping metric names to directions (e.g., {'WER': 'lower_is_better', 'AP': 'higher_is_better'})",
    )


# Keyword management models


class KeywordUpdate(BaseModel):
    """
    Request model for updating keywords on tasks or methods.
    """

    model_config = ConfigDict(from_attributes=True)

    keywords: List[str] = Field(
        ..., description="List of keywords to add, remove, or replace"
    )


class DatasetMetricAddRequest(BaseModel):
    """
    Request model for adding a metric to a dataset.
    """

    model_config = ConfigDict(from_attributes=True)

    metric_name: str = Field(
        ..., description="Name of the metric to add (e.g., 'AP', 'WER', 'Accuracy')"
    )


class DatasetMetricSetRequest(BaseModel):
    """
    Request model for setting all metrics for a dataset.
    """

    model_config = ConfigDict(from_attributes=True)

    metric_names: List[str] = Field(
        ...,
        description="List of metric names allowed for this dataset (replaces existing)",
    )


# Research trends models


class TrendPoint(BaseModel):
    """One monthly percentage point on the public research trends page."""

    month: str = Field(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Paper publication month in YYYY-MM format",
    )
    percent: float = Field(
        ...,
        ge=0,
        le=100,
        description="Share of eligible papers matching the trend, from 0 to 100",
    )


class TrendsResponse(BaseModel):
    """Monthly open-science trends for the public trends page."""

    code_availability: List[TrendPoint] = Field(
        ...,
        description="Papers with at least one official GitHub repository",
    )
    hf_artifacts: List[TrendPoint] = Field(
        ...,
        description="Papers linked to at least one Hugging Face artifact",
    )


# Resolve forward references
Paper.model_rebuild()
