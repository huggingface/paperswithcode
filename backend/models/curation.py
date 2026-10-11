"""Paper curation mutation and job callback API contracts."""

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


__all__ = [
    "CurationLink",
    "EnrichPaperMutation",
    "ExternalPaperProposal",
    "ModelReleaseProposal",
    "ResolveModelPaperMutation",
    "ApplyMutationRequest",
    "PromoteBenchmarkCandidateRequest",
    "CurationTracePreapplyRequest",
    "CurationTraceFinalizeRequest",
    "CompleteJobRequest",
]
