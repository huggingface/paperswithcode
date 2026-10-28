"""Paper curation mutation and job callback API contracts."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models.evaluations import (
    EvaluationCreateRequest,
    EvaluationRemovalRequest,
    EvaluationScoreEvidence,
)
from backend.utils.public_urls import (
    normalize_optional_public_url,
    normalize_public_url,
)


class CurationLink(BaseModel):
    url: str
    is_official: bool = True

    _normalize_url = field_validator("url", mode="before")(
        normalize_optional_public_url
    )


class CurationOrganization(BaseModel):
    """One paper affiliation: an existing catalog organization or an HF org."""

    model_config = ConfigDict(extra="forbid")

    organization_id: int | None = None
    hf_slug: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$"
    )
    name: str = Field(min_length=1, max_length=200)
    evidence: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def _one_target(self) -> "CurationOrganization":
        if (self.organization_id is None) == (self.hf_slug is None):
            raise ValueError("Give exactly one of organization_id or hf_slug")
        return self


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
    organizations: list[CurationOrganization] | None = Field(
        default=None, max_length=10
    )
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


class BenchmarkGapReviewDecision(BaseModel):
    """One overseer decision about a reported benchmark-gap candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: uuid.UUID
    decision: Literal["approve", "merge", "reject", "defer"]
    reason: str = Field(min_length=1, max_length=2_000)
    merge_into_candidate_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_merge_target(self):
        if (self.decision == "merge") != (self.merge_into_candidate_id is not None):
            raise ValueError("merge_into_candidate_id is required only for merge")
        if self.merge_into_candidate_id == self.candidate_id:
            raise ValueError("a candidate cannot merge into itself")
        return self


class ReviewBenchmarkGapsMutation(BaseModel):
    """The daily overseer's decisions across the eligible gap backlog."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4_000)
    decisions: list[BenchmarkGapReviewDecision] = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_unique_candidates(self):
        ids = [item.candidate_id for item in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("each candidate may have only one decision")
        return self


class BenchmarkSourcePaper(BaseModel):
    """The paper that introduced the benchmark, never a later result paper."""

    model_config = ConfigDict(extra="forbid")

    existing_paper_id: int | None = Field(default=None, gt=0)
    arxiv_id: str | None = Field(default=None, pattern=r"^\d{4}\.\d{4,5}(?:v\d+)?$")
    external_paper: ExternalPaperProposal | None = None

    @model_validator(mode="after")
    def validate_one_identity(self):
        identities = (self.existing_paper_id, self.arxiv_id, self.external_paper)
        if sum(value is not None for value in identities) != 1:
            raise ValueError("source_paper requires exactly one paper identity")
        return self


class NewBenchmarkDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    full_name: str | None = Field(default=None, max_length=500)
    description: str = Field(min_length=1, max_length=4_000)
    homepage: str | None = None
    hf_url: str | None = None

    _normalize_urls = field_validator("homepage", "hf_url", mode="before")(
        normalize_optional_public_url
    )


class NewBenchmarkTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=4_000)
    keywords: str = Field(min_length=1, max_length=1_000)
    parent_task_id: int = Field(gt=0)


class NewBenchmarkMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=1, max_length=255)
    direction: Literal["higher_is_better", "lower_is_better"]
    scale: str | None = Field(default=None, max_length=50)
    description: str = Field(min_length=1, max_length=2_000)


class BenchmarkMetricChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    existing_metric_id: int | None = Field(default=None, gt=0)
    new_metric: NewBenchmarkMetric | None = None

    @model_validator(mode="after")
    def validate_one_metric(self):
        if (self.existing_metric_id is None) == (self.new_metric is None):
            raise ValueError("choose exactly one of existing_metric_id or new_metric")
        return self


class AddBenchmarkMutation(BaseModel):
    """Typed result from one scoped benchmark-creation job.

    ``metrics[0]`` is the leaderboard's primary metric.
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["create", "map_existing", "reject", "defer"]
    reason: str = Field(min_length=1, max_length=4_000)
    evidence_urls: list[str] = Field(min_length=1, max_length=20)
    existing_dataset_id: int | None = Field(default=None, gt=0)
    new_dataset: NewBenchmarkDataset | None = None
    source_paper: BenchmarkSourcePaper | None = None
    existing_task_id: int | None = Field(default=None, gt=0)
    new_task: NewBenchmarkTask | None = None
    metrics: list[BenchmarkMetricChoice] = Field(default_factory=list, max_length=3)
    supports_harness: bool = False
    # Justify a task or primary metric the reporting papers do not mostly use.
    task_choice_reason: str | None = Field(default=None, min_length=1, max_length=2_000)
    metric_choice_reason: str | None = Field(
        default=None, min_length=1, max_length=2_000
    )

    @field_validator("evidence_urls", mode="before")
    @classmethod
    def normalize_evidence_urls(cls, values):
        return [normalize_public_url(value) for value in values]

    @model_validator(mode="after")
    def validate_decision_shape(self):
        catalog_fields = (
            self.existing_dataset_id,
            self.new_dataset,
            self.source_paper,
            self.existing_task_id,
            self.new_task,
        )
        if self.decision in {"reject", "defer"}:
            if any(value is not None for value in catalog_fields) or self.metrics:
                raise ValueError(f"{self.decision} cannot include catalog changes")
            return self
        if (self.existing_task_id is None) == (self.new_task is None):
            raise ValueError("choose exactly one of existing_task_id or new_task")
        if not self.metrics:
            raise ValueError("a leaderboard needs at least one metric")
        if self.decision == "create":
            if self.new_dataset is None or self.existing_dataset_id is not None:
                raise ValueError(
                    "create requires new_dataset and no existing_dataset_id"
                )
            if self.source_paper is None:
                raise ValueError("create requires the benchmark's source_paper")
        elif self.existing_dataset_id is None or self.new_dataset is not None:
            raise ValueError("map_existing requires existing_dataset_id only")
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
    review_benchmark_gaps: ReviewBenchmarkGapsMutation | None = None
    add_benchmark: AddBenchmarkMutation | None = None

    @model_validator(mode="before")
    @classmethod
    def lift_nested_score_evidence(cls, data):
        """Accept score evidence nested in its evaluation as if it were top-level.

        Curators often attach each row's source cells to that row. The
        evaluation model would silently drop the key, so move it to the
        proposal-level list the scheduled validator reads.
        """
        if not isinstance(data, dict) or not isinstance(data.get("evaluations"), list):
            return data
        lifted = []
        evaluations = []
        for item in data["evaluations"]:
            if isinstance(item, dict) and "score_evidence" in item:
                item = dict(item)
                nested = item.pop("score_evidence")
                lifted.extend(nested if isinstance(nested, list) else [nested])
            evaluations.append(item)
        if not lifted:
            return data
        return {
            **data,
            "evaluations": evaluations,
            "score_evidence": [*(data.get("score_evidence") or []), *lifted],
        }


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


__all__ = [
    "CurationLink",
    "EnrichPaperMutation",
    "ExternalPaperProposal",
    "ModelReleaseProposal",
    "ResolveModelPaperMutation",
    "BenchmarkGapReviewDecision",
    "ReviewBenchmarkGapsMutation",
    "BenchmarkSourcePaper",
    "NewBenchmarkDataset",
    "NewBenchmarkTask",
    "NewBenchmarkMetric",
    "BenchmarkMetricChoice",
    "AddBenchmarkMutation",
    "ApplyMutationRequest",
    "PromoteBenchmarkCandidateRequest",
    "CurationTracePreapplyRequest",
    "CurationTraceFinalizeRequest",
    "CompleteJobRequest",
]
