"""Dataset, benchmark, evaluation, and metric API contracts."""

from datetime import date, datetime
from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.utils.public_urls import normalize_optional_public_url


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


class DatasetLeaderboardSummary(BaseModel):
    """Small task-scoped leaderboard projection for fast benchmark headers."""

    task_id: str = Field(..., description="Task ID for this leaderboard")
    task_slug: Optional[str] = Field(None, description="Task slug for this leaderboard")
    metric: str = Field(..., description="Primary metric shown by default")
    value: Union[str, int, float] = Field(..., description="Best metric value")
    model_name: str = Field(..., description="Best model or paper display name")
    evaluation_id: str = Field(..., description="Evaluation row supplying the summary")


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
    supports_harness: bool = Field(
        False,
        description="Whether this task-dataset leaderboard allows evaluation harness values",
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
    leaderboard_summary: Optional[DatasetLeaderboardSummary] = Field(
        None,
        description=(
            "Cached task-scoped best metric/value/model projection. Present only "
            "when the dataset detail request includes a resolvable task."
        ),
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

    _normalize_urls = field_validator(
        "url",
        "hf_url",
        "paper_url",
        "homepage",
        "image_url",
        "thumbnail_url",
        "verified_image_url",
        "license_url",
        "pwc_url",
        mode="before",
    )(normalize_optional_public_url)


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

    _normalize_urls = field_validator(
        "url",
        "hf_url",
        "paper_url",
        "homepage",
        "image_url",
        "thumbnail_url",
        "verified_image_url",
        "license_url",
        "pwc_url",
        mode="before",
    )(normalize_optional_public_url)


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
    parameter_coverage_known: int = Field(
        0,
        description=(
            "Number of displayed leaderboard entries with one consistent, known "
            "parameter count after the query filters are applied."
        ),
    )
    parameter_coverage_total: int = Field(
        0,
        description="Number of displayed leaderboard entries after query filters.",
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

    _normalize_urls = field_validator(
        "external_source_url", "source_url", "hf_model_url", mode="before"
    )(normalize_optional_public_url)


class EvaluationRemovalRequest(BaseModel):
    evaluation_id: int
    reason: str = Field(min_length=1, max_length=2_000)
    before_state: dict
    evidence: list[dict] = Field(min_length=1, max_length=20)


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

    _normalize_urls = field_validator(
        "external_source_url", "source_url", "hf_model_url", mode="before"
    )(normalize_optional_public_url)


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


# Resolve the dataset model's forward references within this bounded module.
Dataset.model_rebuild()

__all__ = [
    "BenchmarkSummary",
    "LeaderboardRankSummary",
    "DatasetLeaderboardSummary",
    "Dataset",
    "IntroducingPaper",
    "Datasets",
    "DatasetCreateRequest",
    "DatasetUpdateRequest",
    "Evaluation",
    "Evaluations",
    "EvaluationCreateRequest",
    "EvaluationRemovalRequest",
    "EvaluationUpdateRequest",
    "Metric",
    "Metrics",
    "MetricDirections",
    "DatasetMetricAddRequest",
    "DatasetMetricSetRequest",
]
