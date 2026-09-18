"""
Pydantic models for API responses.

These models match the original PapersWithCode API specification but are adapted
to our database schema. The main differences from the original API:
- No nips_id field (not supported in our schema)
- Added version and is_latest_version fields for ArXiv version tracking
- Enhanced URL construction based on our schema design
"""

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models.tasks import Task as Task
from backend.models.public_api import (
    DatasetTasks as DatasetTasks,
    LeaderboardMetric as LeaderboardMetric,
    LeaderboardMetrics as LeaderboardMetrics,
)

from backend.models.chat import (
    ChatAvailabilityResponse as ChatAvailabilityResponse,
    ChatSandboxDailySpendResponse as ChatSandboxDailySpendResponse,
    ChatSandboxPriorCycleResponse as ChatSandboxPriorCycleResponse,
    ChatSandboxSpendEventResponse as ChatSandboxSpendEventResponse,
    ChatSandboxSpendResponse as ChatSandboxSpendResponse,
    ChatWebSearchBudgetResponse as ChatWebSearchBudgetResponse,
    ChatWebSearchEventResponse as ChatWebSearchEventResponse,
)
from backend.models.evaluations import (
    BenchmarkSummary as BenchmarkSummary,
    Dataset as Dataset,
    DatasetCreateRequest as DatasetCreateRequest,
    DatasetLeaderboardSummary as DatasetLeaderboardSummary,
    DatasetMetricAddRequest as DatasetMetricAddRequest,
    DatasetMetricSetRequest as DatasetMetricSetRequest,
    DatasetUpdateRequest as DatasetUpdateRequest,
    Datasets as Datasets,
    Evaluation as Evaluation,
    EvaluationCreateRequest as EvaluationCreateRequest,
    EvaluationScoreEvidence as EvaluationScoreEvidence,
    EvaluationRemovalRequest as EvaluationRemovalRequest,
    EvaluationUpdateRequest as EvaluationUpdateRequest,
    Evaluations as Evaluations,
    IntroducingPaper as IntroducingPaper,
    LeaderboardRankSummary as LeaderboardRankSummary,
    Metric as Metric,
    MetricDirections as MetricDirections,
    Metrics as Metrics,
)
from backend.models.papers import (
    AppliedAuthorFilter as AppliedAuthorFilter,
    Author as Author,
    AuthorLink as AuthorLink,
    AuthorSummary as AuthorSummary,
    Authors as Authors,
    FrameworkSummary as FrameworkSummary,
    GithubRepositoryPreview as GithubRepositoryPreview,
    HfArtifactSummary as HfArtifactSummary,
    MethodSummary as MethodSummary,
    OrganizationSummary as OrganizationSummary,
    Paper as Paper,
    PaperBucketArtifact as PaperBucketArtifact,
    PaperBucketCopyError as PaperBucketCopyError,
    PaperBucketCopyRequest as PaperBucketCopyRequest,
    PaperBucketCopyResponse as PaperBucketCopyResponse,
    PaperDateRange as PaperDateRange,
    PaperFeedScope as PaperFeedScope,
    PaperProjectPage as PaperProjectPage,
    PaperRepository as PaperRepository,
    PaperSearchFeedResults as PaperSearchFeedResults,
    PaperLookupRequest as PaperLookupRequest,
    PaperLookupResponse as PaperLookupResponse,
    PaperReferenceQuery as PaperReferenceQuery,
    ResolvedPaperReference as ResolvedPaperReference,
    PaperSearchResults as PaperSearchResults,
    PaperSummary as PaperSummary,
    PaperVersion as PaperVersion,
    PaperVersions as PaperVersions,
    Papers as Papers,
    ProjectPage as ProjectPage,
    ProjectPageCreateRequest as ProjectPageCreateRequest,
    ProjectPageUpdateRequest as ProjectPageUpdateRequest,
    ProjectPageWithPapers as ProjectPageWithPapers,
    ProjectPages as ProjectPages,
    RelatedPaperRecommendation as RelatedPaperRecommendation,
    RelatedPaperSummary as RelatedPaperSummary,
    Repositories as Repositories,
    Repository as Repository,
    RepositoryStarHistory as RepositoryStarHistory,
    RepositoryStarHistoryList as RepositoryStarHistoryList,
    RepositoryTrendingPaper as RepositoryTrendingPaper,
    RepositoryTrendingRepository as RepositoryTrendingRepository,
    RepositoryTrendingScore as RepositoryTrendingScore,
    RepositoryTrendingTask as RepositoryTrendingTask,
    TaskSummary as TaskSummary,
    VersionComparison as VersionComparison,
)
from backend.utils.public_urls import (
    normalize_optional_public_url,
    normalize_public_url,
)


class StagingAccessRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hf_username: str
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    updated_at: datetime


# Error models


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    error: str = Field(default="Validation error", description="Error type")
    detail: List[dict] = Field(..., description="Validation error details")


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
    recent_paper_count: Optional[int] = Field(
        None,
        description="Distinct latest-version papers using this method in the last 90 days",
    )
    baseline_paper_count: Optional[int] = Field(
        None,
        description=(
            "Distinct latest-version papers using this method in the 180 days "
            "preceding the recent window"
        ),
    )
    trend_score: Optional[float] = Field(
        None,
        description="Recent method mention velocity normalized to papers per 30 days",
    )
    rate_change: Optional[float] = Field(
        None,
        description=(
            "Recent usage velocity divided by baseline velocity. Null when "
            "the method has no baseline papers"
        ),
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


class MethodIndexEntry(BaseModel):
    """Compact method projection used by the public methods directory."""

    id: str
    name: str
    slug: Optional[str] = None
    area_id: Optional[str] = None
    introduced_year: Optional[int] = None
    paper_count: int = 0
    trend_score: float = 0.0

    @field_validator("id", "area_id", mode="before")
    @classmethod
    def ensure_string_id(cls, value):
        return str(value) if value is not None else None


class MethodIndex(BaseModel):
    count: int
    results: List[MethodIndexEntry]


class MethodTrendPoint(BaseModel):
    """One calendar-month bucket of papers mentioning a method."""

    start_date: date = Field(..., description="First day of this month")
    end_date: date = Field(..., description="Last included day of this month")
    paper_count: int = Field(
        ..., description="Distinct latest-version papers mentioning the method"
    )
    eligible_paper_count: int = 0
    processed_paper_count: int = 0
    coverage_ratio: Optional[float] = None
    coverage_status: str = "not_applicable"
    catalog_paper_count: int = 0
    catalog_share: float = 0.0


class MethodTrend(BaseModel):
    """Paper-mention history and coverage metadata for one method."""

    method_id: str = Field(..., description="Resolved method ID")
    method_slug: Optional[str] = Field(None, description="Resolved method slug")
    signal: str = Field(
        default="paper_method_links",
        description="Association signal used to calculate method mentions",
    )
    recent_days: int = Field(..., description="Length of the recent score window")
    baseline_days: int = Field(
        ..., description="Length of the preceding comparison window"
    )
    history_months: int = Field(
        ..., description="Number of calendar-month history buckets"
    )
    generated_on: date = Field(..., description="Date used as the window endpoint")
    recent_paper_count: int = Field(
        ..., description="Papers mentioning the method in the recent window"
    )
    baseline_paper_count: int = Field(
        ..., description="Papers mentioning the method in the preceding window"
    )
    trend_score: float = Field(
        ..., description="Recent usage normalized to papers per 30 days"
    )
    rate_change: Optional[float] = Field(
        None, description="Recent usage velocity divided by baseline velocity"
    )
    history: List[MethodTrendPoint] = Field(default_factory=list)
    undated_paper_count: int = 0
    history_complete: bool = False
    comparison_complete: bool = Field(
        False,
        description=(
            "Whether recent and baseline coverage is complete enough to report velocity"
        ),
    )
    current_month_is_partial: bool = True

    @field_validator("method_id", mode="before")
    @classmethod
    def ensure_string_method_id(cls, v):
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


class BenchmarkTrendPoint(BaseModel):
    """One time bucket in a benchmark reporting-frequency sparkline."""

    start_date: date = Field(..., description="Exclusive start of this bucket")
    end_date: date = Field(..., description="Inclusive end of this bucket")
    paper_count: int = Field(
        ..., description="Distinct papers reporting an evaluation in this bucket"
    )


class TrendingBenchmark(BaseModel):
    """Recent evaluation-reporting activity for one task benchmark."""

    id: str = Field(..., description="Benchmark dataset ID")
    name: str = Field(..., description="Benchmark name")
    slug: Optional[str] = Field(None, description="Benchmark URL slug")
    full_name: Optional[str] = Field(None, description="Expanded benchmark name")
    description: Optional[str] = Field(None, description="Benchmark description")
    hf_url: Optional[str] = Field(None, description="Hugging Face dataset URL")
    recent_paper_count: int = Field(
        ..., description="Distinct reporting papers in the recent window"
    )
    baseline_paper_count: int = Field(
        ..., description="Distinct reporting papers in the preceding baseline window"
    )
    all_time_paper_count: int = Field(
        ..., description="Distinct reporting papers across all publication dates"
    )
    trend_score: float = Field(
        ...,
        description="Recent reporting velocity normalized to papers per 30 days",
    )
    support_weighted_score: float = Field(
        ...,
        description=(
            "Ranking score: ln(1 + recent papers) multiplied by the smoothed "
            "recent-to-baseline reporting lift"
        ),
    )
    rate_change: Optional[float] = Field(
        None,
        description=(
            "Recent reporting velocity divided by baseline velocity. Null when "
            "the benchmark has no baseline reports"
        ),
    )
    latest_reported_on: Optional[date] = Field(
        None, description="Publication date of the newest reporting paper"
    )
    best_model_name: Optional[str] = Field(
        None,
        description="Top-ranked model on this benchmark for the scoped task",
    )
    best_paper_route: Optional[str] = Field(
        None,
        description="Route identifier for the paper supplying the top-ranked model",
    )
    best_paper_title: Optional[str] = Field(
        None,
        description="Title of the paper supplying the top-ranked model",
    )
    best_code_url: Optional[str] = Field(
        None,
        description="Preferred code repository for the top-ranked model's paper",
    )
    history: List[BenchmarkTrendPoint] = Field(
        default_factory=list,
        description="Chronological reporting-paper counts for sparkline rendering",
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class TrendingBenchmarks(BaseModel):
    """Support-weighted benchmark trends with reproducible window metadata."""

    task_id: str = Field(..., description="Resolved task ID")
    task_slug: str = Field(..., description="Resolved task slug")
    signal: str = Field(
        default="evaluation_reports",
        description="Evidence source used to calculate the ranking",
    )
    recent_days: int = Field(..., description="Length of the recent window")
    baseline_days: int = Field(..., description="Length of the preceding window")
    bucket_days: int = Field(..., description="Length of each history bucket")
    support_prior_papers: float = Field(
        ...,
        description=(
            "Neutral paper pseudocount applied to recent and baseline-equivalent counts"
        ),
    )
    generated_on: date = Field(..., description="Date used as the window endpoint")
    results: List[TrendingBenchmark] = Field(
        default_factory=list,
        description="Benchmarks sorted by descending support-weighted score",
    )

    @field_validator("task_id", mode="before")
    @classmethod
    def ensure_string_task_id(cls, v):
        return str(v)


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


class TaskBenchmarkListItem(BaseModel):
    """Compact benchmark row for the grouped CLI taxonomy view."""

    id: str = Field(..., description="Benchmark dataset ID")
    name: str = Field(..., description="Benchmark name")
    slug: Optional[str] = Field(None, description="Benchmark URL slug")
    full_name: Optional[str] = Field(None, description="Expanded benchmark name")
    description: Optional[str] = Field(None, description="Benchmark description")
    hf_url: Optional[str] = Field(None, description="Hugging Face dataset URL")
    evaluation_count: int = Field(
        ..., description="Logical leaderboard rows for this task and benchmark"
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class TaskWithBenchmarks(BaseModel):
    """Visible top-level task with a bounded benchmark preview."""

    id: str = Field(..., description="Task ID")
    name: str = Field(..., description="Task name")
    slug: str = Field(..., description="Task URL slug")
    paper_count: int = Field(..., description="Papers linked to this task")
    benchmarks: List[TaskBenchmarkListItem] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class AreaWithTaskBenchmarks(BaseModel):
    """Research area with visible tasks and their top benchmarks."""

    id: str = Field(..., description="Area ID")
    name: str = Field(..., description="Area name")
    tasks: List[TaskWithBenchmarks] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class AreasWithTaskBenchmarks(BaseModel):
    """Container for grouped task benchmark previews."""

    results: List[AreaWithTaskBenchmarks] = Field(default_factory=list)


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


class OrganizationTopPaper(BaseModel):
    id: str
    arxiv_id: Optional[str] = None
    title: str

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
    hf_slug: Optional[str] = Field(None, description="Hugging Face namespace")
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
    is_featured: bool = False
    display_order: Optional[int] = None
    organization_trending_score: Optional[float] = None
    trending_rank: Optional[int] = None
    top_trending_paper: Optional[OrganizationTopPaper] = None
    first_paper_year: Optional[int] = None
    latest_paper_year: Optional[int] = None
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)


class OrganizationSyncRequest(BaseModel):
    """Request an idempotent synchronization from a Hugging Face namespace."""

    model_config = ConfigDict(extra="forbid")

    hf_slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    slug: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    skip_missing_papers: bool = False


class OrganizationSyncResult(BaseModel):
    organization: str
    fetched: int = 0
    existing: int = 0
    imported: int = 0
    linked: int = 0
    already_linked: int = 0
    failed: int = 0
    unknown_organizations_seen: int = 0
    upstream_local_delta: int = 0


class Organizations(BaseModel):
    """Container for a list of organizations."""

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Total number of organizations")
    results: List[Organization] = Field(..., description="Organization list")


class OrganizationContributionDay(BaseModel):
    """Paper contributions attributed to an organization on one day."""

    published_date: date = Field(
        ...,
        alias="date",
        description="Paper publication date",
    )
    paper_count: int = Field(..., ge=1, description="Papers published on this date")


class OrganizationContributions(BaseModel):
    """Daily organization paper contributions over a fixed date range."""

    start_date: date
    end_date: date
    total_count: int = Field(..., ge=0)
    results: List[OrganizationContributionDay] = Field(default_factory=list)


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

    _normalize_image_url = field_validator("image_url", mode="before")(
        normalize_optional_public_url
    )


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
    """First-class framework recommended as a starting point for a task."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Repository ID")
    framework_id: str = Field(..., description="Framework ID")
    framework_slug: str = Field(..., description="Framework page slug")
    framework_name: str = Field(..., description="Framework display name")
    url: str = Field(..., description="GitHub repository URL")
    owner: Optional[str] = Field(None, description="GitHub repository owner")
    name: Optional[str] = Field(None, description="GitHub repository name")
    num_stars: int = Field(default=0, description="Current GitHub star count")

    @field_validator("id", "framework_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        return str(v) if v is not None else v


class FrameworkCatalogItem(BaseModel):
    id: str
    slug: str
    name: str
    organization_name: Optional[str] = None
    description: str
    when_to_use: Optional[str] = None
    platforms: List[str] = Field(default_factory=list)
    github_url: Optional[str] = None
    repository: Optional[str] = None
    paper_count: int = 0
    docs_url: Optional[str] = None
    introducing_paper_arxiv_id: Optional[str] = None


class FrameworkCatalogCategory(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    guide_url: Optional[str] = None
    guide_label: Optional[str] = None
    frameworks: List[FrameworkCatalogItem] = Field(default_factory=list)


class FrameworkCatalogDomain(BaseModel):
    slug: str
    name: str
    description: str
    categories: List[FrameworkCatalogCategory] = Field(default_factory=list)


class FrameworkCatalog(BaseModel):
    domains: List[FrameworkCatalogDomain] = Field(default_factory=list)


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
    area: Optional[Area] = Field(None, description="Research area containing this task")
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
            "Ordered first-class frameworks recommended for this task, from "
            "`task_frameworks`, with repository metadata and current star counts"
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


class CurationLink(BaseModel):
    url: str
    is_official: bool = True

    _normalize_url = field_validator("url", mode="before")(
        normalize_optional_public_url
    )


class EnrichPaperMutation(BaseModel):
    task_ids: list[int] | None = None
    method_ids: list[int] | None = None
    repositories: list[CurationLink] | None = None
    project_pages: list[CurationLink] | None = None
    thumbnail_url: str | None = None
    regenerate_thumbnail: bool = False
    urls_extracted: bool | None = None
    hf_models: list[str] | None = Field(default=None, max_length=50)
    hf_datasets: list[str] | None = Field(default=None, max_length=50)
    hf_spaces: list[str] | None = Field(default=None, max_length=50)
    task_removal_reasons: dict[int, str] = Field(default_factory=dict)
    method_removal_reasons: dict[int, str] = Field(default_factory=dict)
    project_page_removal_reasons: dict[str, str] = Field(default_factory=dict)


class ExternalPaperProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str
    title: str = Field(min_length=1, max_length=1_000)
    abstract: str = Field(min_length=1, max_length=20_000)
    date_published: date

    _normalize_source_url = field_validator("source_url", mode="before")(
        normalize_public_url
    )


class ModelReleaseProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_name: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=255)
    is_open: bool
    aliases: list[str] = Field(default_factory=list, max_length=50)


class ResolveModelPaperMutation(BaseModel):
    """Typed result from an untrusted model-card resolution job."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "reject"]
    reason: str = Field(min_length=1, max_length=4_000)
    novelty_kind: Literal[
        "new_weights", "new_method", "new_release", "repackaging", "uncertain"
    ]
    evidence_urls: list[str] = Field(min_length=1, max_length=20)
    existing_paper_id: int | None = Field(default=None, gt=0)
    predecessor_paper_id: int | None = Field(default=None, gt=0)
    arxiv_id: str | None = Field(default=None, pattern=r"^\d{4}\.\d{4,5}(?:v\d+)?$")
    external_paper: ExternalPaperProposal | None = None
    model_release: ModelReleaseProposal | None = None

    @field_validator("evidence_urls", mode="before")
    @classmethod
    def normalize_evidence_urls(cls, values):
        return [normalize_public_url(value) for value in values]

    @model_validator(mode="after")
    def validate_decision_shape(self):
        identities = sum(
            value is not None
            for value in (
                self.existing_paper_id,
                self.arxiv_id,
                self.external_paper,
            )
        )
        if self.decision == "reject":
            if (
                identities
                or self.predecessor_paper_id is not None
                or self.model_release is not None
            ):
                raise ValueError("rejection cannot include a paper mutation")
            return self
        if identities != 1:
            raise ValueError("acceptance requires exactly one paper identity")
        if self.model_release is None:
            raise ValueError("acceptance requires model_release")
        if self.novelty_kind in {"repackaging", "uncertain"}:
            raise ValueError("accepted release must establish substantive novelty")
        return self


class ApplyMutationRequest(BaseModel):
    evaluations: list[EvaluationCreateRequest] = Field(default_factory=list)
    evaluation_removals: list[EvaluationRemovalRequest] = Field(
        default_factory=list, max_length=100
    )
    enrich: EnrichPaperMutation | None = None
    benchmark_gaps: list[dict] = Field(default_factory=list, max_length=30)
    validation_evidence: list[dict] = Field(default_factory=list, max_length=200)
    score_evidence: list[EvaluationScoreEvidence] = Field(
        default_factory=list, max_length=200
    )
    source_coverage: list[dict] = Field(default_factory=list, max_length=50)
    resolve_model_paper: ResolveModelPaperMutation | None = None


class PromoteBenchmarkCandidateRequest(BaseModel):
    dataset_id: int = Field(gt=0)
    task_id: int = Field(gt=0)
    best_metric: str = Field(min_length=1, max_length=200)


class CurationTracePreapplyRequest(BaseModel):
    proposal: dict
    events_gzip_b64: str = Field(max_length=12_000_000)
    prompt: str = Field(default="", max_length=80_000)
    url_candidates: dict | None = None


class CurationTraceFinalizeRequest(BaseModel):
    events_gzip_b64: str = Field(max_length=12_000_000)
    result: dict = Field(default_factory=dict)
    benchmark_gaps: dict | list = Field(default_factory=dict)
    report: str = Field(default="", max_length=40_000)
    usage: dict = Field(default_factory=dict)
    duration_ms: int | None = Field(default=None, ge=0)


class CompleteJobRequest(BaseModel):
    report: str = ""
    error: str | None = None


# Keyword management models


class KeywordUpdate(BaseModel):
    """
    Request model for updating keywords on tasks or methods.
    """

    model_config = ConfigDict(from_attributes=True)

    keywords: List[str] = Field(
        ..., description="List of keywords to add, remove, or replace"
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


AutonomousDisplayState = Literal[
    "healthy", "degraded", "repairing", "rolled-back", "manual"
]
AutonomousOperatorName = Literal[
    "submissions", "curation", "cron_health", "chat_reliability"
]


class AutonomousOperatorStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: AutonomousOperatorName
    enabled: bool
    status: AutonomousDisplayState
    monitoring_active: bool
    next_scheduled_run: datetime | None = None


class AutonomousLeaseStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str
    owner_run_id: str
    owner_operator: Literal["cron_health", "chat_reliability"]
    expires_at: datetime


class AutonomousCostSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_usd: str = Field(pattern=r"^\d+\.\d{9}$")


class AutonomousBaselineStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    revision: int = Field(ge=1)
    qualified_by: str
    qualified_at: datetime


class AutonomousProviderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: Literal["staging", "production"]
    manifest_revision: str
    state_revision: int = Field(ge=1)
    active_provider: str
    reason_code: str
    updated_at: datetime


class AutonomousRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    operator: AutonomousOperatorName
    dry_run: bool
    status: str
    exit_classification: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: str = Field(pattern=r"^\d+\.\d{9}$")
    created_at: datetime


class AutonomousActionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    run_id: str
    operator: AutonomousOperatorName
    capability: str
    reason_code: str
    resource_kind: str
    resource_identifier: str
    created_at: datetime


class AutonomousOperationsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    manual_mode: bool
    monitoring_active: bool
    display_state: AutonomousDisplayState
    operators: List[AutonomousOperatorStatus]
    active_lease: AutonomousLeaseStatus | None
    costs: AutonomousCostSummary
    baseline: AutonomousBaselineStatus | None
    provider_states: List[AutonomousProviderStatus]
    recent_runs: List[AutonomousRunSummary]
    recent_actions: List[AutonomousActionSummary]
    exclusions: List[str]


class AutonomousManualModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    expected_revision: int = Field(ge=1)
    confirmation: Literal["SET_MANUAL_MODE"]


class AutonomousOperatorStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    expected_revision: int = Field(ge=1)
    confirmation: Literal["SET_OPERATOR_STATE"]


class AutonomousBaselineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    expected_revision: int = Field(ge=0)
    confirmation: Literal["QUALIFY_CHAT_BASELINE"]


class AutonomousAcceptanceEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation: Literal["RECORD_ACCEPTANCE_EVIDENCE"]


class AutonomousAcceptanceReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: AutonomousOperatorName
    ready: bool
    passed_gates: List[str]
    missing_gates: List[str]
    shadow_days: int = Field(ge=0)
    required_shadow_days: int = Field(ge=0)


class AutonomousAcceptanceEvidenceResponse(AutonomousAcceptanceReadinessResponse):
    evidence_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
