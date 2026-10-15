"""Area, method, task, framework, and keyword API contracts."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.tasks import Task
from backend.models.evaluations import Dataset
from backend.utils.public_urls import normalize_optional_public_url


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


class RelatedMethod(BaseModel):
    """Compact projection of a method listed as related to another method."""

    id: str
    name: str
    slug: str

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, value):
        return str(value)


class RelatedMethods(BaseModel):
    results: List[RelatedMethod]


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


class KeywordUpdate(BaseModel):
    """
    Request model for updating keywords on tasks or methods.
    """

    model_config = ConfigDict(from_attributes=True)

    keywords: List[str] = Field(
        ..., description="List of keywords to add, remove, or replace"
    )


__all__ = [
    "Area",
    "Areas",
    "Method",
    "Methods",
    "MethodIndexEntry",
    "MethodIndex",
    "MethodTrendPoint",
    "MethodTrend",
    "Tasks",
    "TrendingTask",
    "TrendingTasks",
    "BenchmarkTrendPoint",
    "TrendingBenchmark",
    "TrendingBenchmarks",
    "AreaWithTasks",
    "AreasWithTasks",
    "TaskBenchmarkListItem",
    "TaskWithBenchmarks",
    "AreaWithTaskBenchmarks",
    "AreasWithTaskBenchmarks",
    "TaskCreateRequest",
    "TaskSubtaskBenchmarks",
    "RecommendedFramework",
    "FrameworkCatalogItem",
    "FrameworkCatalogCategory",
    "FrameworkCatalogDomain",
    "FrameworkCatalog",
    "TaskPage",
    "KeywordUpdate",
]
