"""Job-scoped reads and transactional mutations for Codex curation callbacks."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.models.curation import ApplyMutationRequest
from backend.models.database import (
    BenchmarkCurationCandidate,
    Dataset,
    Evaluation,
    HfArtifact,
    Method,
    Metric,
    ModelProviderAlias,
    Organization,
    ModelRelease,
    ModelReleaseSignal,
    Paper,
    PaperCurationJob,
    PaperCurationWorkflow,
    PaperHfArtifact,
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
    PaperOrganization,
    PaperRepository,
    PaperTask,
    Repository,
    Task,
    TaskDataset,
    TaskDatasetMetric,
    TrendingModelCandidate,
)
from backend.services.evaluation_scale_service import (
    metric_scale_bounds,
    validate_board_scale,
    validate_source_score,
)
from backend.services.benchmark_gap_review_service import BenchmarkGapReviewService
from backend.services.benchmark_gap_service import BenchmarkGapService
from backend.services.autonomous_capabilities import (
    CAPABILITY_RESOURCE_KINDS,
    AutonomousCapabilityDenied,
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_operations_repository import RunContext
from backend.services.autonomous_policy import AutonomousPolicy
from backend.services.catalog_errors import CatalogValidationError
from backend.services.codex_add_evals_service import (
    BENCHMARK_GAP_KINDS,
    CodexPaperJobService,
    codex_paper_job_service,
)
from backend.services.model_release_signal_service import (
    ReleaseSignalResolutionService,
    signal_paper_candidates,
)
from backend.services.curation_organization_service import (
    CurationOrganizationService,
)
from backend.services.curation_thumbnail_queue_service import (
    queue_missing_paper_thumbnail,
    queue_thumbnail,
    serialize_thumbnail,
)
from backend.services.curation_autonomy import curation_primary_authorization
from backend.services.evaluation_service import EvaluationService
from backend.services.external_page_markdown_service import web_markdown_pending
from backend.services.leaderboard_ranking_service import parse_metric_value
from backend.services.leaderboard_sync_ownership import is_sync_managed
from backend.services.paper_association_service import PaperAssociationService
from backend.services.paper_method_link_service import upsert_evidence_links
from backend.services.paper_service import PaperService
from backend.services.trending_model_resolution_service import (
    TrendingModelResolutionService,
    model_family_key,
)
from backend.utils.source_urls import source_url_identity


class CodexCurationPaperNotFoundError(LookupError):
    """The paper attached to a curation job no longer exists."""


class CodexCurationMutationClosedError(RuntimeError):
    """The durable job state no longer permits a callback mutation."""


class CodexCurationEnrichmentNotAllowedError(ValueError):
    """An evaluation job received an enrichment payload."""


class CodexCurationEvaluationPaperMismatchError(ValueError):
    """An evaluation payload targets a paper outside the scoped job."""


class CodexCurationEvaluationsNotAllowedError(ValueError):
    """An enrichment job received evaluation rows."""


class CodexCurationEnrichmentRequiredError(ValueError):
    """An enrichment job did not receive its mutation payload."""


def _evaluation_harness_clause(harness: str | None):
    if harness is None:
        return Evaluation.harness.is_(None)
    return Evaluation.harness == harness


def _requires_scheduled_dispatch_pause(_exc: Exception) -> bool:
    """Never halt the daily queue because one paper's apply failed."""
    return False


def _retryable_validation(row, exc: Exception) -> bool:
    """Allow one correction only for ordinary, proposal-fixable validation."""
    prior_rejection = (getattr(row, "validation_summary", None) or {}).get(
        "status"
    ) == "rejected"
    return bool(
        not prior_rejection
        and (
            type(exc) is ValueError
            or isinstance(
                exc,
                (CatalogValidationError, CodexCurationEvaluationsNotAllowedError),
            )
        )
    )


class CodexCurationCallbackService:
    """Own callback projections and the single-apply mutation transaction."""

    def __init__(
        self,
        db: Session,
        *,
        job_service: CodexPaperJobService = codex_paper_job_service,
        evaluation_service: EvaluationService | None = None,
        association_service: PaperAssociationService | None = None,
        autonomous_policy: AutonomousPolicy | None = None,
        markdown_pending=web_markdown_pending,
    ) -> None:
        self.db = db
        self.markdown_pending = markdown_pending
        self.job_service = job_service
        self.evaluation_service = evaluation_service or EvaluationService(db)
        self.autonomous_policy = autonomous_policy or AutonomousPolicy()
        paper_service = PaperService(db)
        self.paper_associations = association_service or PaperAssociationService(
            db, paper_service.get_paper_by_id
        )

    def authorize_autonomous_callback(
        self,
        row,
        body: ApplyMutationRequest,
        *,
        context: RunContext,
    ) -> None:
        """Authorize the authenticated scheduled callback before any write."""
        if getattr(row, "trigger", "admin") == "admin":
            raise AutonomousCapabilityDenied("admin_callback_is_not_autonomous")
        for capability, resource in self._validate_scheduled_capability_boundary(
            row, body
        ):
            decision = self.autonomous_policy.authorize(
                self.db, context, capability, resource
            )
            if not decision.allowed:
                raise AutonomousCapabilityDenied(decision.reason_code)

    def _resolution_candidates(
        self, candidate: TrendingModelCandidate
    ) -> tuple[list[Paper], set[int]]:
        exact_candidates = (
            self.db.query(Paper)
            .join(PaperHfArtifact, PaperHfArtifact.paper_id == Paper.id)
            .join(HfArtifact, HfArtifact.id == PaperHfArtifact.hf_artifact_id)
            .filter(
                HfArtifact.kind == "model",
                HfArtifact.repo_id == candidate.repo_id,
                Paper.is_latest_version,
            )
            .order_by(Paper.id)
            .all()
        )
        family_candidates: list[Paper] = []
        publisher_candidates: list[Paper] = []
        if candidate.author:
            candidate_family = model_family_key(candidate.repo_id)
            releases = (
                self.db.query(ModelRelease)
                .filter(
                    func.lower(ModelRelease.publisher) == candidate.author.casefold()
                )
                .order_by(ModelRelease.id.desc())
                .yield_per(100)
            )
            for release in releases:
                if candidate_family not in {
                    model_family_key(identity)
                    for identity in [release.canonical_name, *(release.aliases or [])]
                }:
                    continue
                paper = self.db.get(Paper, release.paper_id)
                if paper is not None and paper.is_latest_version:
                    family_candidates.append(paper)
                if len(family_candidates) == 20:
                    break
            publisher_candidates = (
                self.db.query(Paper)
                .join(ModelRelease, ModelRelease.paper_id == Paper.id)
                .filter(
                    func.lower(ModelRelease.publisher) == candidate.author.casefold(),
                    Paper.is_latest_version,
                )
                .order_by(Paper.id.desc())
                .limit(20)
                .all()
            )

        candidates = list(exact_candidates)
        seen_paper_ids = {paper.id for paper in candidates}
        for paper in [*family_candidates, *publisher_candidates]:
            if paper.id not in seen_paper_ids:
                candidates.append(paper)
                seen_paper_ids.add(paper.id)
        return candidates, {
            paper.id for paper in [*exact_candidates, *family_candidates]
        }

    def _resolution_paper_candidates(
        self, candidate: TrendingModelCandidate
    ) -> list[Paper]:
        candidates, allowed_ids = self._resolution_candidates(candidate)
        return [paper for paper in candidates if paper.id in allowed_ids]

    def _allowed_resolution_paper_ids(
        self, candidate: TrendingModelCandidate
    ) -> set[int]:
        """Allow exact and same-family matches, never publisher-only siblings."""
        return self._resolution_candidates(candidate)[1]

    def _retry_feedback(self, row) -> dict[str, Any] | None:
        retry_id = getattr(row, "retry_of_id", None)
        if retry_id is None:
            return None
        previous = self.db.get(PaperCurationJob, retry_id)
        if (
            previous is None
            or previous.kind != row.kind
            or (
                previous.paper_id != row.paper_id
                or previous.candidate_id != getattr(row, "candidate_id", None)
                or getattr(previous, "release_signal_id", None)
                != getattr(row, "release_signal_id", None)
            )
        ):
            return None
        validation = previous.validation_summary or {}
        return {
            "job_id": str(previous.id),
            "error": previous.error,
            "validation_error": validation.get("error"),
            "benchmark_gaps_rejected": validation.get("benchmark_gaps_rejected", []),
            "instruction": "Correct this rejection using fresh context and primary sources; do not repeat the rejected proposal or bypass validation.",
        }

    def _release_signal_context(self, row, settings: Settings) -> dict[str, Any]:
        signal = self.db.get(ModelReleaseSignal, row.release_signal_id)
        if signal is None:
            raise CodexCurationPaperNotFoundError("Release signal not found")
        return {
            "job": self.job_service.serialize(row, settings).model_dump(mode="json"),
            "retry_feedback": self._retry_feedback(row),
            # The pinned runner reads these candidate fields for every
            # resolution job; a radar lead is a page about the release, not
            # a model card.
            "candidate": {
                "id": str(signal.id),
                "repo_id": f"{signal.lab}: {signal.model_name}",
                "readme_sha": None,
                "model_card_url": signal.lead_url,
            },
            "release_signal": {
                "id": str(signal.id),
                "lab": signal.lab,
                "model_name": signal.model_name,
                "title": signal.title,
                "lead_url": signal.lead_url,
                "lead_is_first_party": signal.lead_is_official,
                "published": (
                    signal.published.isoformat() if signal.published else None
                ),
                "sightings": signal.sightings,
            },
            "paper_candidates": [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "arxiv_id": paper.arxiv_id,
                    "source_url": paper.source_url,
                }
                for paper in signal_paper_candidates(self.db, signal)
            ],
        }

    def context(self, row, settings: Settings) -> dict[str, Any]:
        if getattr(row, "kind", None) in BENCHMARK_GAP_KINDS:
            review = BenchmarkGapReviewService(self.db, settings, self.job_service)
            try:
                scope = (
                    {"review": review.review_context(row)}
                    if row.kind == "review-benchmark-gaps"
                    else {"benchmark": review.creation_context(row)}
                )
            except LookupError as error:
                raise CodexCurationPaperNotFoundError(str(error)) from error
            return {
                "job": self.job_service.serialize(row, settings).model_dump(
                    mode="json"
                ),
                "retry_feedback": self._retry_feedback(row),
                # The pinned runner prints paper.id; these jobs have no paper.
                "paper": {"id": None},
                **scope,
            }
        if (
            getattr(row, "kind", None) == "resolve-model-paper"
            and getattr(row, "release_signal_id", None) is not None
        ):
            return self._release_signal_context(row, settings)
        if getattr(row, "kind", None) == "resolve-model-paper":
            candidate = self.db.get(TrendingModelCandidate, row.candidate_id)
            if candidate is None:
                raise CodexCurationPaperNotFoundError(
                    "Trending model candidate not found"
                )
            paper_candidates = self._resolution_paper_candidates(candidate)
            revision = candidate.readme_revision or "main"
            return {
                "job": self.job_service.serialize(row, settings).model_dump(
                    mode="json"
                ),
                "retry_feedback": self._retry_feedback(row),
                "candidate": {
                    "id": str(candidate.id),
                    "repo_id": candidate.repo_id,
                    "author": candidate.author,
                    "featured_publisher": candidate.featured_publisher,
                    "trending_score": float(candidate.trending_score or 0),
                    "readme_sha": candidate.readme_sha,
                    "readme_revision": candidate.readme_revision,
                    "model_url": f"https://huggingface.co/{candidate.repo_id}",
                    "model_card_url": (
                        f"https://huggingface.co/{candidate.repo_id}/raw/"
                        f"{revision}/README.md"
                    ),
                },
                "paper_candidates": [
                    {
                        "id": paper.id,
                        "title": paper.title,
                        "arxiv_id": paper.arxiv_id,
                        "source_url": paper.source_url,
                    }
                    for paper in paper_candidates
                ],
            }
        paper = self.db.get(Paper, row.paper_id)
        if paper is None:
            raise CodexCurationPaperNotFoundError("Paper not found")
        source_candidate = None
        if getattr(row, "parent_workflow_id", None) is not None:
            workflow = self.db.get(PaperCurationWorkflow, row.parent_workflow_id)
            if workflow is not None and workflow.source_candidate_id is not None:
                candidate = self.db.get(
                    TrendingModelCandidate, workflow.source_candidate_id
                )
                if candidate is not None:
                    revision = candidate.readme_revision or "main"
                    release = (
                        self.db.get(ModelRelease, candidate.model_release_id)
                        if candidate.model_release_id is not None
                        else None
                    )
                    source_candidate = {
                        "id": str(candidate.id),
                        "repo_id": candidate.repo_id,
                        "readme_sha": candidate.readme_sha,
                        "readme_revision": candidate.readme_revision,
                        "model_card_url": (
                            f"https://huggingface.co/{candidate.repo_id}/raw/"
                            f"{revision}/README.md"
                        ),
                        "model_release": (
                            {
                                "id": int(release.id),
                                "paper_id": int(release.paper_id),
                                "canonical_name": release.canonical_name,
                                "aliases": list(release.aliases or []),
                            }
                            if release is not None and release.paper_id is not None
                            else None
                        ),
                    }
        repository_rows = (
            self.db.query(Repository, PaperRepository.is_official, Repository.source)
            .join(PaperRepository, PaperRepository.repository_id == Repository.id)
            .filter(PaperRepository.paper_id == paper.id)
            .all()
        )
        repositories = [
            (
                values[0],
                values[1],
                values[2] if len(values) > 2 else getattr(values[0], "source", None),
            )
            for values in repository_rows
        ]
        task_rows = (
            self.db.query(Task, PaperTask.source)
            .join(PaperTask, PaperTask.task_id == Task.id)
            .filter(PaperTask.paper_id == paper.id)
            .all()
        )
        if task_rows and not all(
            isinstance(values, (tuple, list))
            and len(values) == 2
            and hasattr(values[0], "id")
            for values in task_rows
        ):
            task_rows = [(task, "unknown") for task in getattr(paper, "tasks", [])]

        def method_evidence(method_id: int) -> list:
            values = (
                self.db.query(PaperMethodEvidence)
                .filter(
                    PaperMethodEvidence.paper_id == paper.id,
                    PaperMethodEvidence.method_id == method_id,
                )
                .all()
            )
            return [value for value in values if hasattr(value, "evidence_type")]

        exclusions = [
            value
            for value in self.db.query(PaperMethodExclusion)
            .filter(PaperMethodExclusion.paper_id == paper.id)
            .all()
            if hasattr(value, "method_id")
        ]
        # An external release page is read from its prepared Markdown copy;
        # first-party sites often refuse the runner's own fetch.
        markdown_expected = bool(
            getattr(row, "kind", None) == "add-evals"
            and paper.source == "external"
            and not paper.arxiv_id
            and self.markdown_pending(
                paper,
                bucket_id=settings.paper_markdown_hf_bucket_id,
                token=settings.hf_token or None,
            )
        )
        return {
            "job": self.job_service.serialize(row, settings).model_dump(mode="json"),
            "source_candidate": source_candidate,
            "retry_feedback": self._retry_feedback(row),
            "paper": {
                "id": paper.id,
                "title": paper.title,
                "abstract": paper.abstract,
                "arxiv_id": paper.arxiv_id,
                "source": paper.source,
                "source_url": paper.source_url,
                "markdown_expected": markdown_expected,
                "date_published": paper.date_published,
                "urls_extracted": paper.urls_extracted,
                "thumbnail_url": paper.thumbnail_url,
                "tasks": [
                    {
                        "id": task.id,
                        "name": task.name,
                        "slug": task.slug,
                        "source": source,
                    }
                    for task, source in task_rows
                ],
                "methods": [
                    {
                        "id": method.id,
                        "name": method.name,
                        "slug": method.slug,
                        "evidence": [
                            {
                                "type": evidence.evidence_type,
                                "details": evidence.details,
                            }
                            for evidence in method_evidence(method.id)
                        ],
                    }
                    for method in paper.methods
                ],
                "repositories": [
                    {
                        "url": repository.url,
                        "is_official": is_official,
                        "source": source,
                    }
                    for repository, is_official, source in repositories
                ],
                "project_pages": [
                    {
                        "url": page.url,
                        "is_official": page.is_official,
                        "source": getattr(page, "source", None),
                    }
                    for page in paper.project_pages
                ],
                "hf_models": getattr(paper, "hf_models", None) or [],
                "hf_datasets": getattr(paper, "hf_datasets", None) or [],
                "hf_spaces": getattr(paper, "hf_spaces", None) or [],
                "organizations": [
                    {
                        "id": organization.id,
                        "name": organization.name,
                        "slug": organization.slug,
                        "hf_slug": organization.hf_slug,
                    }
                    for organization in getattr(paper, "organizations", None) or []
                ],
                "method_exclusions": [
                    {"method_id": item.method_id, "reason": item.reason}
                    for item in exclusions
                ],
                "evaluations": [
                    self._evaluation_state(item)
                    for item in getattr(paper, "evaluations", [])
                ],
            },
        }

    def search_taxonomy(self, query: str) -> dict[str, list[dict[str, Any]]]:
        pattern = f"%{query}%"
        return {
            "tasks": [
                {"id": task.id, "name": task.name, "slug": task.slug}
                for task in self.db.query(Task)
                .filter(or_(Task.name.ilike(pattern), Task.slug.ilike(pattern)))
                .limit(30)
            ],
            "methods": [
                {"id": method.id, "name": method.name, "slug": method.slug}
                for method in self.db.query(Method)
                .filter(or_(Method.name.ilike(pattern), Method.slug.ilike(pattern)))
                .limit(30)
            ],
            "organizations": [
                {
                    "id": organization.id,
                    "name": organization.name,
                    "slug": organization.slug,
                    "hf_slug": organization.hf_slug,
                }
                for organization in self.db.query(Organization)
                .filter(
                    or_(
                        Organization.name.ilike(pattern),
                        Organization.slug.ilike(pattern),
                        Organization.hf_slug.ilike(pattern),
                    )
                )
                .limit(30)
            ],
        }

    def leaderboard_inventory(self, query: str) -> list[dict[str, Any]]:
        """Return configured leaderboard IDs and score-scale evidence."""
        normalized_query = re.sub(r"[^a-z0-9]", "", query.lower())

        def match_quality(dataset: Dataset) -> str:
            names = [dataset.name, dataset.slug or "", dataset.full_name or ""]
            normalized_names = [
                re.sub(r"[^a-z0-9]", "", name.lower()) for name in names
            ]
            if normalized_query in normalized_names:
                return "exact"
            if any(
                name.startswith(normalized_query) or normalized_query.startswith(name)
                for name in normalized_names
            ):
                return "close"
            return "fuzzy"

        flexible = (
            "%" + "%".join(query.replace("_", "-").replace("-", " ").split()) + "%"
        )
        matches = (
            self.db.query(Dataset, Task, TaskDataset, Metric)
            .join(TaskDataset, TaskDataset.dataset_id == Dataset.id)
            .join(Task, Task.id == TaskDataset.task_id)
            .join(
                TaskDatasetMetric,
                (TaskDatasetMetric.task_id == Task.id)
                & (TaskDatasetMetric.dataset_id == Dataset.id),
            )
            .join(Metric, Metric.id == TaskDatasetMetric.metric_id)
            .filter(
                or_(
                    Dataset.name.ilike(f"%{query}%"),
                    Dataset.full_name.ilike(f"%{query}%"),
                    Dataset.slug.ilike(flexible),
                    Dataset.name.ilike(flexible),
                )
            )
            .order_by(Dataset.name, Task.name, Metric.name)
            .limit(200)
            .all()
        )
        matches.sort(
            key=lambda row: (
                {"exact": 0, "close": 1, "fuzzy": 2}[match_quality(row[0])],
                row[0].name,
                row[1].name,
                row[3].name,
            )
        )

        grouped: dict[tuple[int, int], dict[str, Any]] = {}
        for dataset, task, task_dataset, metric in matches:
            key = (int(task.id), int(dataset.id))
            if key not in grouped:
                if len(grouped) == 30:
                    continue
                grouped[key] = {
                    "dataset": {
                        "id": int(dataset.id),
                        "name": dataset.name,
                        "slug": dataset.slug,
                        "full_name": dataset.full_name,
                        "split_name": dataset.split_name,
                        "variant_type": dataset.variant_type,
                        "description": (
                            dataset.short_description or dataset.description or ""
                        )[:1_000]
                        or None,
                        "warning": dataset.warning,
                    },
                    "task": {
                        "id": int(task.id),
                        "name": task.name,
                        "slug": task.slug,
                    },
                    "match_quality": match_quality(dataset),
                    "supports_harness": bool(task_dataset.supports_harness),
                    "metrics": [],
                }
            if key not in grouped:
                continue

            examples = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                    Evaluation.best_metric == metric.name,
                )
                .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
                .limit(5)
                .all()
            )
            grouped[key]["metrics"].append(
                {
                    "id": int(metric.id),
                    "name": metric.name,
                    "direction": metric.direction,
                    "scale": metric.scale,
                    "recent_values": [
                        {
                            "model_name": example.model_name,
                            "value": example.metrics.get(metric.name),
                        }
                        for example in examples
                        if metric.name in example.metrics
                    ],
                }
            )
        return list(grouped.values())

    def apply(
        self,
        row,
        body: ApplyMutationRequest,
        *,
        autonomous_context: RunContext | None = None,
    ) -> dict[str, Any]:
        if getattr(row, "trigger", "admin") != "admin":
            if autonomous_context is None:
                raise AutonomousCapabilityDenied("autonomous_run_context_required")
            self.authorize_autonomous_callback(row, body, context=autonomous_context)
        return self._apply_authorized(row, body)

    def _apply_authorized(self, row, body: ApplyMutationRequest) -> dict[str, Any]:
        if row.kind in BENCHMARK_GAP_KINDS:
            return self._apply_benchmark_gap(row, body)
        if row.kind == "resolve-model-paper":
            try:
                if hasattr(self.db, "refresh"):
                    self.db.refresh(row, with_for_update=True)
                self._validate_mutation(row, body)
                assert body.resolve_model_paper is not None
                if getattr(row, "release_signal_id", None) is not None:
                    validator_version = "release-radar-policy-v1"
                    result = ReleaseSignalResolutionService(self.db).apply(
                        row.release_signal_id,
                        body.resolve_model_paper,
                        commit=False,
                    )
                else:
                    validator_version = "trending-model-policy-v1"
                    allowed_paper_ids = None
                    if body.resolve_model_paper.decision == "accept":
                        candidate = self.db.get(
                            TrendingModelCandidate, row.candidate_id
                        )
                        if candidate is None:
                            raise CodexCurationPaperNotFoundError(
                                "Trending model candidate not found"
                            )
                        allowed_paper_ids = self._allowed_resolution_paper_ids(
                            candidate
                        )
                    result = TrendingModelResolutionService(self.db).apply(
                        row.candidate_id,
                        body.resolve_model_paper,
                        allowed_paper_ids=allowed_paper_ids,
                        commit=False,
                    )
                now = datetime.now(UTC)
                row.submitted_at = now
                row.applied_at = now
                row.proposal = body.model_dump(mode="json")
                row.validation_summary = {
                    "status": "accepted",
                    "validator_version": validator_version,
                    "post_write_verification": "passed",
                }
                row.mutation_result = result
                if result["status"] == "resolved":
                    paper = self.db.get(Paper, result["paper_id"])
                    queue_missing_paper_thumbnail(self.db, row, paper)
                self.db.commit()
                return dict(result)
            except Exception as exc:
                self.db.rollback()
                mutation_closed = isinstance(exc, CodexCurationMutationClosedError)
                rejected = (
                    self.db.get(type(row), row.id) if not mutation_closed else None
                )
                if rejected is not None:
                    retryable_validation = _retryable_validation(rejected, exc)
                    rejected.proposal = body.model_dump(mode="json")
                    rejected.validation_summary = {
                        "status": "rejected",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:2_000],
                        "retryable": retryable_validation,
                    }
                    if not retryable_validation:
                        rejected.submitted_at = datetime.now(UTC)
                    self.db.commit()
                raise
        gap_service = BenchmarkGapService(self.db)
        accepted_gaps: list[dict] = []
        rejected_gaps: list[dict] = []
        before_state: dict[str, Any] = {"paper_id": row.paper_id}
        try:
            gap_paper = (
                self.db.get(Paper, row.paper_id) if body.benchmark_gaps else None
            )
            source_documents = (getattr(row, "url_candidates", None) or {}).get(
                "source_documents"
            ) or []
            accepted_gaps, rejected_gaps = gap_service.validate(
                body.benchmark_gaps,
                paper=gap_paper,
                source_documents=source_documents,
            )
            if rejected_gaps and getattr(row, "trigger", "admin") != "admin":
                details = "; ".join(
                    f"#{item['index']}: {item['error']}" for item in rejected_gaps
                )
                raise ValueError(
                    f"Scheduled benchmark gap validation failed: {details}"
                )
            if hasattr(self.db, "refresh"):
                self.db.refresh(row, with_for_update=True)
            self._validate_mutation(row, body)
            before_state = self._mutation_projection(row, body)
            validation = self._validate_scheduled_policy(row, body)
            created = 0
            updated = 0
            removed = 0
            organization_links = None
            if row.kind == "add-evals":
                created, updated = self._apply_evaluations(body)
                removed = self._apply_evaluation_removals(row, body)
            else:
                organization_links = self._apply_enrichment(row, body)

            if hasattr(self.db, "flush"):
                self.db.flush()
            after_state = self._mutation_projection(row, body)
            self._verify_after_state(row, body, after_state)

            before_evaluations = {
                int(item["id"]): item for item in before_state.get("evaluations", [])
            }
            after_evaluations = {
                int(item["id"]): item for item in after_state.get("evaluations", [])
            }
            changed_existing_evaluations = sorted(
                evaluation_id
                for evaluation_id, before in before_evaluations.items()
                if after_evaluations.get(evaluation_id) != before
            )
            flagged_existing_evaluations = (
                changed_existing_evaluations
                if getattr(row, "trigger", "admin") != "admin"
                else []
            )

            gap_results = (
                gap_service.persist(
                    paper_id=row.paper_id, job_id=row.id, gaps=accepted_gaps
                )
                if accepted_gaps
                else []
            )

            changed = before_state != after_state or created + updated + removed > 0
            row.submitted_at = datetime.now(UTC)
            # Enrichment can enqueue thumbnail work or use adapters whose fake
            # test/session projection cannot observe the relation write. Keep
            # its accepted-apply lifecycle, while a true add-evals no-op remains
            # distinguishable from a catalog mutation.
            if changed or row.kind == "enrich-paper":
                row.applied_at = row.submitted_at
            row.proposal = body.model_dump(mode="json")
            row.validation_summary = {
                **validation,
                "post_write_verification": "passed",
                "existing_evaluation_rows_affected": sorted(
                    {int(item["id"]) for item in before_state.get("evaluations", [])}
                ),
                # Historical evaluation rows have no trustworthy author/source
                # provenance column. Conservatively flag every changed existing
                # row as manual-or-legacy so automatic corrections are prominent
                # in the dashboard and trace instead of assuming automation.
                "manual_or_legacy_evaluation_rows_affected": (
                    flagged_existing_evaluations
                ),
                "requires_prominent_review": bool(flagged_existing_evaluations),
                "benchmark_gaps_accepted": len(accepted_gaps),
                "benchmark_gaps_rejected": rejected_gaps,
            }
            row.mutation_result = {
                "status": "applied" if changed else "no_changes",
                "evaluations_created": created,
                "evaluations_updated": updated,
            }
            if getattr(row, "trigger", "admin") != "admin":
                row.mutation_result.update(
                    before_state=before_state,
                    after_state=after_state,
                )
            if body.benchmark_gaps or getattr(row, "trigger", "admin") != "admin":
                row.mutation_result.update(
                    benchmark_gap_candidates=gap_results,
                    benchmark_gaps_rejected=rejected_gaps,
                )
            if removed:
                row.mutation_result["evaluations_removed"] = removed
            if organization_links:
                row.mutation_result["organizations"] = organization_links
            if row.kind == "add-evals":
                skipped = self._skipped_configured_leaderboards(body)
                if skipped:
                    row.mutation_result["skipped_configured_leaderboards"] = skipped
            self.db.commit()
        except Exception as exc:
            from backend.models.database import PaperCurationSchedulerState

            if hasattr(self.db, "rollback"):
                self.db.rollback()
            mutation_closed = isinstance(exc, CodexCurationMutationClosedError)
            rejected_row = (
                self.db.get(type(row), row.id)
                if not mutation_closed
                and hasattr(self.db, "get")
                and hasattr(row, "id")
                else None
            )
            should_commit = False
            if rejected_row is not None:
                retryable_validation = _retryable_validation(rejected_row, exc)
                rejected_row.proposal = body.model_dump(mode="json")
                rejected_row.validation_summary = {
                    "status": "rejected",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:2_000],
                    "before_state": before_state,
                    "benchmark_gaps_rejected": rejected_gaps,
                    "retryable": retryable_validation,
                }
                # A scheduled worker gets one opportunity to correct an ordinary
                # proposal-validation error. Keep the mutation open after the
                # first rejection; a second rejected proposal closes the job.
                if not retryable_validation:
                    rejected_row.submitted_at = datetime.now(UTC)
                should_commit = True
            if (
                not mutation_closed
                and getattr(row, "trigger", "admin") != "admin"
                and _requires_scheduled_dispatch_pause(exc)
            ):
                state = self.db.get(PaperCurationSchedulerState, 1)
                if state is not None:
                    state.paused_at = datetime.now(UTC)
                    state.pause_condition = "server_invariant"
                    state.pause_reason = (
                        "Scheduled callback proposal breached a server-side invariant"
                    )
                    should_commit = True
            if should_commit:
                self.db.commit()
            raise

        response: dict[str, Any] = dict(row.mutation_result)
        if body.benchmark_gaps or getattr(row, "trigger", "admin") != "admin":
            response["benchmark_gap_candidates"] = gap_results
            response["benchmark_gaps_rejected"] = rejected_gaps
        if getattr(row, "thumbnail_requested_at", None) is not None:
            response["thumbnail"] = serialize_thumbnail(row)
        return response

    @staticmethod
    def _review_scope(row) -> list[str]:
        if row.review_scope is None:
            raise ValueError("Read the review context before applying decisions")
        return row.review_scope

    def _apply_benchmark_gap(self, row, body: ApplyMutationRequest) -> dict[str, Any]:
        """Apply one overseer review or one benchmark creation in a transaction."""
        try:
            if hasattr(self.db, "refresh"):
                self.db.refresh(row, with_for_update=True)
            self._validate_mutation(row, body)
            validation = self._validate_scheduled_policy(row, body)
            review = BenchmarkGapReviewService(
                self.db, get_settings(), self.job_service
            )
            result = (
                review.apply_review(
                    body.review_benchmark_gaps, scope=self._review_scope(row)
                )
                if row.kind == "review-benchmark-gaps"
                else review.apply_add_benchmark(row, body.add_benchmark)
            )
            now = datetime.now(UTC)
            row.submitted_at = now
            row.applied_at = now
            row.proposal = body.model_dump(mode="json")
            row.validation_summary = {
                **validation,
                "status": "accepted",
                "validator_version": "benchmark-gap-policy-v1",
                "post_write_verification": "passed",
            }
            row.mutation_result = result
            self.db.commit()
            return dict(result)
        except Exception as exc:
            self.db.rollback()
            if not isinstance(exc, CodexCurationMutationClosedError):
                rejected = self.db.get(type(row), row.id)
                if rejected is not None:
                    retryable_validation = _retryable_validation(rejected, exc)
                    rejected.proposal = body.model_dump(mode="json")
                    rejected.validation_summary = {
                        "status": "rejected",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:2_000],
                        "retryable": retryable_validation,
                    }
                    if not retryable_validation:
                        rejected.submitted_at = datetime.now(UTC)
                    self.db.commit()
            raise

    def _mutation_projection(self, row, body: ApplyMutationRequest) -> dict[str, Any]:
        """Bound the durable before/after trace to relations touched by this stage."""
        if not hasattr(self.db, "flush"):
            return {"paper_id": row.paper_id, "evaluations": []}
        if row.kind == "enrich-paper":
            paper = self.db.get(Paper, row.paper_id)
            task_links = (
                self.db.query(PaperTask)
                .filter(PaperTask.paper_id == row.paper_id)
                .all()
            )
            method_links = (
                self.db.query(PaperMethod)
                .filter(PaperMethod.paper_id == row.paper_id)
                .all()
            )
            evidence = (
                self.db.query(PaperMethodEvidence)
                .filter(PaperMethodEvidence.paper_id == row.paper_id)
                .all()
            )
            evidence_by_method: dict[int, list[str]] = {}
            for item in evidence:
                evidence_by_method.setdefault(int(item.method_id), []).append(
                    item.evidence_type
                )
            repository_rows = (
                self.db.query(Repository, PaperRepository.is_official)
                .join(PaperRepository, PaperRepository.repository_id == Repository.id)
                .filter(PaperRepository.paper_id == row.paper_id)
                .all()
            )
            return {
                "paper_id": row.paper_id,
                "urls_extracted": bool(paper.urls_extracted),
                "tasks": [
                    {"id": int(item.task_id), "source": item.source}
                    for item in sorted(task_links, key=lambda value: value.task_id)
                ],
                "methods": [
                    {
                        "id": int(item.method_id),
                        "evidence_types": sorted(
                            evidence_by_method.get(int(item.method_id), [])
                        ),
                    }
                    for item in sorted(method_links, key=lambda value: value.method_id)
                ],
                "repositories": [
                    {
                        "url": repository.url,
                        "is_official": bool(is_official),
                        "source": repository.source,
                    }
                    for repository, is_official in sorted(
                        repository_rows, key=lambda value: value[0].url
                    )
                ],
                "project_pages": [
                    {
                        "url": page.url,
                        "is_official": bool(page.is_official),
                        "source": getattr(page, "source", None),
                    }
                    for page in sorted(paper.project_pages, key=lambda value: value.url)
                ],
                "hf_models": sorted(paper.hf_models or []),
                "hf_datasets": sorted(paper.hf_datasets or []),
                "hf_spaces": sorted(paper.hf_spaces or []),
                "organizations": sorted(
                    int(link.organization_id)
                    for link in self.db.query(PaperOrganization).filter(
                        PaperOrganization.paper_id == row.paper_id
                    )
                ),
            }

        identities = {
            (
                item.task_id,
                item.dataset_id,
                item.model_name,
                item.harness,
                item.best_metric,
            )
            for item in body.evaluations
        }
        removal_ids = {item.evaluation_id for item in body.evaluation_removals}
        evaluations = (
            self.db.query(Evaluation).filter(Evaluation.paper_id == row.paper_id).all()
        )
        selected = [
            item
            for item in evaluations
            if item.id in removal_ids
            or (
                item.task_id,
                item.dataset_id,
                item.model_name,
                item.harness,
                item.best_metric,
            )
            in identities
        ]
        return {
            "paper_id": row.paper_id,
            "evaluations": [
                self._evaluation_state(item)
                for item in sorted(selected, key=lambda value: value.id)
            ][:200],
        }

    def _verify_after_state(
        self, row, body: ApplyMutationRequest, after_state: dict[str, Any]
    ) -> None:
        if not hasattr(self.db, "flush"):
            return
        if row.kind == "enrich-paper":
            mutation = body.enrich
            assert mutation is not None
            if mutation.task_ids is not None and {
                item["id"] for item in after_state["tasks"]
            } != set(mutation.task_ids):
                raise ValueError("Post-write task verification failed")
            if mutation.method_ids is not None and {
                item["id"] for item in after_state["methods"]
            } != set(mutation.method_ids):
                raise ValueError("Post-write method verification failed")
            if (
                mutation.urls_extracted is not None
                and after_state["urls_extracted"] != mutation.urls_extracted
            ):
                raise ValueError("Post-write URL extraction verification failed")
            return

        states = {item["id"]: item for item in after_state["evaluations"]}
        for removal in body.evaluation_removals:
            if removal.evaluation_id in states:
                raise ValueError("Post-write evaluation removal verification failed")
        all_rows = (
            self.db.query(Evaluation).filter(Evaluation.paper_id == row.paper_id).all()
        )
        for proposal in body.evaluations:
            matches = [
                item
                for item in all_rows
                if (
                    item.task_id,
                    item.dataset_id,
                    item.model_name,
                    item.harness,
                    item.best_metric,
                )
                == (
                    proposal.task_id,
                    proposal.dataset_id,
                    proposal.model_name,
                    proposal.harness,
                    proposal.best_metric,
                )
            ]
            changes = self._evaluation_changes(matches[0], proposal) if matches else {}
            if len(matches) != 1 or changes:
                raise ValueError(
                    "Post-write evaluation verification failed"
                    + (
                        f": {len(matches)} matching rows"
                        if len(matches) != 1
                        else f": {sorted(changes)}"
                    )
                )

        for task_id, dataset_id, best_metric in {
            (item.task_id, item.dataset_id, item.best_metric)
            for item in body.evaluations
        }:
            leaderboard_rows = [
                item
                for item in all_rows
                if item.task_id == task_id
                and item.dataset_id == dataset_id
                and item.best_metric == best_metric
            ]
            if len(leaderboard_rows) > 1:
                raise ValueError(
                    "Scheduled curation must keep one paper-native result per leaderboard; "
                    f"paper {row.paper_id}, task {task_id}, dataset {dataset_id}, "
                    f"metric {best_metric!r} already contains "
                    f"{[(item.id, item.model_name) for item in leaderboard_rows]}. "
                    "Omit a weaker/equal variant; replacing the current best requires "
                    "evidence-backed removal of the superseded row."
                )

    def _validate_mutation(self, row, body: ApplyMutationRequest) -> None:
        if (
            row.status in {"completed", "failed", "canceled"}
            or getattr(row, "submitted_at", None) is not None
            or row.applied_at is not None
        ):
            raise CodexCurationMutationClosedError(
                "This job may no longer apply mutations"
            )
        if row.kind in BENCHMARK_GAP_KINDS:
            expected = (
                "review_benchmark_gaps"
                if row.kind == "review-benchmark-gaps"
                else "add_benchmark"
            )
            unexpected = (
                body.enrich,
                body.resolve_model_paper,
                body.review_benchmark_gaps if expected == "add_benchmark" else None,
                body.add_benchmark if expected == "review_benchmark_gaps" else None,
            )
            if (
                getattr(body, expected) is None
                or any(value is not None for value in unexpected)
                or any(
                    (
                        body.evaluations,
                        body.evaluation_removals,
                        body.benchmark_gaps,
                        body.validation_evidence,
                        body.score_evidence,
                        body.source_coverage,
                    )
                )
            ):
                raise ValueError(f"{row.kind} jobs accept only {expected} payloads")
            return
        if body.review_benchmark_gaps is not None or body.add_benchmark is not None:
            raise ValueError("Benchmark-gap payloads are allowed only for their jobs")
        if row.kind == "resolve-model-paper":
            if (
                body.resolve_model_paper is None
                or body.enrich is not None
                or body.evaluations
                or body.evaluation_removals
                or body.benchmark_gaps
                or body.validation_evidence
                or body.score_evidence
            ):
                raise ValueError(
                    "Resolution jobs accept only model resolution payloads"
                )
            if (
                getattr(row, "trigger", None) == "hf-trending-cron"
                and body.resolve_model_paper.external_paper is not None
            ):
                raise ValueError(
                    "The trending-model cron cannot create external papers; "
                    "resolve to an existing paper or arXiv paper, or reject the candidate"
                )
            return
        if body.resolve_model_paper is not None:
            raise ValueError("Model resolution is allowed only for resolution jobs")
        if row.kind == "add-evals":
            if body.enrich is not None:
                raise CodexCurationEnrichmentNotAllowedError(
                    "Enrichment is not allowed for this job"
                )
            if any(item.paper_id != row.paper_id for item in body.evaluations):
                raise CodexCurationEvaluationPaperMismatchError(
                    "Evaluation paper does not match job"
                )
            self._validate_trending_model_ownership(row, body)
            self._validate_trending_source_coverage(row, body)
            for removal in body.evaluation_removals:
                existing = self.db.get(Evaluation, removal.evaluation_id)
                if existing is None or existing.paper_id != row.paper_id:
                    raise CodexCurationEvaluationPaperMismatchError(
                        "Evaluation removal does not match job paper"
                    )
            self._validate_already_present_outcomes(row, body)
            return
        if body.benchmark_gaps:
            raise CodexCurationEvaluationsNotAllowedError(
                "Benchmark gaps are allowed only for add-evals jobs"
            )
        if body.evaluations:
            raise CodexCurationEvaluationsNotAllowedError(
                "Evaluations are not allowed for this job"
            )
        if body.enrich is None:
            raise CodexCurationEnrichmentRequiredError("Enrichment payload is required")

    @staticmethod
    def _model_identity_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.rsplit("/", 1)[-1].casefold())

    def _validate_trending_model_ownership(
        self, row, body: ApplyMutationRequest
    ) -> None:
        """Keep one trending release's model lanes on its canonical paper."""
        if getattr(row, "parent_workflow_id", None) is None:
            return
        workflow = self.db.get(PaperCurationWorkflow, row.parent_workflow_id)
        if workflow is None or workflow.source_candidate_id is None:
            if getattr(row, "trigger", None) == "hf-trending-cron":
                raise ValueError(
                    "Trending evaluation job has no source model candidate"
                )
            return
        candidate = self.db.get(TrendingModelCandidate, workflow.source_candidate_id)
        if candidate is None or candidate.model_release_id is None:
            raise ValueError("Trending evaluation job has no resolved model release")
        release = self.db.get(ModelRelease, candidate.model_release_id)
        if release is None or release.paper_id != row.paper_id:
            raise ValueError("Resolved model release does not belong to the job paper")
        provider_aliases = (
            self.db.query(ModelProviderAlias)
            .filter(ModelProviderAlias.model_release_id == release.id)
            .all()
        )
        identities = {
            self._model_identity_key(value)
            for value in (
                release.canonical_name,
                *(release.aliases or []),
                candidate.repo_id,
                *(alias.alias for alias in provider_aliases),
            )
            if value
        }
        identities.discard("")
        for evaluation in body.evaluations:
            model_key = self._model_identity_key(evaluation.model_name)
            if not any(
                model_key == identity or model_key.startswith(identity)
                for identity in identities
            ):
                raise ValueError(
                    f"Evaluation model {evaluation.model_name!r} does not belong "
                    "to the resolved model release"
                )

    @staticmethod
    def _validate_trending_source_coverage(row, body: ApplyMutationRequest) -> None:
        if getattr(row, "trigger", None) != "hf-trending-cron":
            return
        documents = (getattr(row, "url_candidates", None) or {}).get(
            "source_documents"
        ) or []
        expected = {
            source_url_identity(item.get("url"))
            for item in documents
            if isinstance(item, dict) and item.get("url")
        }
        if not expected:
            return
        supplied = {
            source_url_identity(item.get("url"))
            for item in body.source_coverage
            if isinstance(item, dict) and item.get("url")
        }
        missing = sorted(expected - supplied)
        if missing:
            raise ValueError(
                "Evaluation proposal did not account for every authoritative "
                f"source: {', '.join(missing)}"
            )
        for item in body.source_coverage:
            if source_url_identity(item.get("url")) not in expected:
                continue
            if item.get("status") not in {"inspected", "unavailable"}:
                raise ValueError("Source coverage has an invalid inspection status")
            if not isinstance(item.get("benchmark_outcomes"), list):
                raise ValueError("Source coverage must include benchmark outcomes")

    @staticmethod
    def _benchmark_outcomes(body: ApplyMutationRequest, dispositions: set[str]):
        for source in body.source_coverage:
            outcomes = (
                source.get("benchmark_outcomes") if isinstance(source, dict) else None
            )
            for outcome in outcomes if isinstance(outcomes, list) else []:
                if (
                    isinstance(outcome, dict)
                    and outcome.get("disposition") in dispositions
                ):
                    yield source.get("url"), outcome

    def _validate_already_present_outcomes(
        self, row, body: ApplyMutationRequest
    ) -> None:
        """Allow an ``already_present`` skip only when this paper's own row is at least as good.

        Higher-ranked rows from other papers never make a paper-native result
        redundant, so the outcome must name the exact leaderboard and the
        paper's best eligible score, and an existing row of this paper on that
        leaderboard must be equal or better under the metric direction.
        """
        removed_ids = {item.evaluation_id for item in body.evaluation_removals}
        for _url, outcome in self._benchmark_outcomes(body, {"already_present"}):
            label = outcome.get("benchmark")
            task_id = outcome.get("task_id")
            dataset_id = outcome.get("dataset_id")
            metric_name = outcome.get("metric")
            value = parse_metric_value(outcome.get("value"))
            if (
                not isinstance(task_id, int)
                or not isinstance(dataset_id, int)
                or not isinstance(metric_name, str)
                or not metric_name
                or value is None
            ):
                raise ValueError(
                    f"already_present outcome {label!r} must name task_id, "
                    "dataset_id, metric, and value (this paper's best eligible "
                    "score on that leaderboard's scale)"
                )
            metric = (
                self.db.query(Metric)
                .join(TaskDatasetMetric, TaskDatasetMetric.metric_id == Metric.id)
                .filter(
                    TaskDatasetMetric.task_id == task_id,
                    TaskDatasetMetric.dataset_id == dataset_id,
                    Metric.name == metric_name,
                )
                .one_or_none()
            )
            if metric is None:
                raise ValueError(
                    f"already_present outcome {label!r} names metric "
                    f"{metric_name!r} that is not configured for task {task_id} "
                    f"and dataset {dataset_id}"
                )
            existing = [
                (evaluation, score)
                for evaluation in self.db.query(Evaluation)
                .filter(
                    Evaluation.paper_id == row.paper_id,
                    Evaluation.task_id == task_id,
                    Evaluation.dataset_id == dataset_id,
                )
                .all()
                if evaluation.id not in removed_ids
                and (
                    score := parse_metric_value(
                        (evaluation.metrics or {}).get(metric_name)
                    )
                )
                is not None
            ]
            lower_is_better = metric.direction == "lower_is_better"
            if not any(
                math.isclose(score, value, rel_tol=1e-9, abs_tol=1e-9)
                or (score < value if lower_is_better else score > value)
                for _evaluation, score in existing
            ):
                stored = ", ".join(
                    f"evaluation {evaluation.id} {evaluation.model_name!r} = {score:g}"
                    for evaluation, score in existing
                )
                raise ValueError(
                    f"Benchmark {label!r} is not already_present: this paper has "
                    f"no row on task {task_id} / dataset {dataset_id} / "
                    f"{metric_name} that is equal to or better than {value:g}. "
                    f"This paper's stored rows there: {stored or 'none'}. "
                    "Recheck the source table column for this benchmark; if the "
                    "stored row matches the paper's best eligible result, report "
                    "that value. Rows from other papers ranking higher never "
                    "justify a skip; otherwise submit the paper's best eligible "
                    "result as an evaluation."
                )

    def _skipped_configured_leaderboards(
        self, body: ApplyMutationRequest
    ) -> list[dict[str, Any]]:
        """List skips that name a configured leaderboard so losses stay auditable."""
        skipped = []
        for url, outcome in self._benchmark_outcomes(
            body, {"already_present", "not_applicable"}
        ):
            task_id = outcome.get("task_id")
            dataset_id = outcome.get("dataset_id")
            if not isinstance(task_id, int) or not isinstance(dataset_id, int):
                continue
            configured = (
                self.db.query(TaskDataset)
                .filter(
                    TaskDataset.task_id == task_id,
                    TaskDataset.dataset_id == dataset_id,
                )
                .one_or_none()
            )
            if configured is None:
                continue
            skipped.append(
                {
                    "source_url": url,
                    "benchmark": outcome.get("benchmark"),
                    "disposition": outcome.get("disposition"),
                    "task_id": task_id,
                    "dataset_id": dataset_id,
                    "metric": outcome.get("metric"),
                    "value": outcome.get("value"),
                    "detail": outcome.get("detail"),
                }
            )
        return skipped

    @staticmethod
    def _preapply_proposal(row) -> dict[str, Any] | None:
        try:
            proposal = ApplyMutationRequest.model_validate(row.proposal or {})
        except ValidationError:
            return None
        return proposal.model_dump(mode="json")

    def _validate_scheduled_policy(
        self, row, body: ApplyMutationRequest
    ) -> dict[str, Any]:
        if getattr(row, "trigger", "admin") == "admin":
            return {"policy": "admin"}
        self._validate_scheduled_capability_boundary(row, body)
        if row.trace_status not in {"preapply_stored", "disabled"}:
            raise CodexCurationMutationClosedError(
                "Scheduled mutation requires a durable pre-apply trace"
            )
        # The pre-apply trace is the reviewable record of what a scheduled job
        # intends to change, so the apply must be exactly that proposal.
        if self._preapply_proposal(row) != body.model_dump(mode="json"):
            raise CodexCurationMutationClosedError(
                "Scheduled mutation does not match its pre-apply proposal"
            )
        if row.kind in BENCHMARK_GAP_KINDS:
            return {"policy": "benchmark-gap-v1"}
        if row.kind == "enrich-paper":
            mutation = body.enrich
            if mutation is None:
                raise CodexCurationEnrichmentRequiredError(
                    "Enrichment payload is required"
                )
            if mutation.regenerate_thumbnail:
                raise ValueError("Scheduled enrichment must not request thumbnail work")
            if (
                mutation.urls_extracted is True
                and row.url_candidates
                and not row.url_candidates.get("complete", False)
            ):
                raise ValueError(
                    "urls_extracted cannot be set after an incomplete evidence search"
                )
            task_ids = set(mutation.task_ids or [])
            method_ids = set(mutation.method_ids or [])
            if task_ids and self.db.query(Task).filter(
                Task.id.in_(task_ids)
            ).count() != len(task_ids):
                raise ValueError("Unknown task ID in enrichment proposal")
            if method_ids and self.db.query(Method).filter(
                Method.id.in_(method_ids)
            ).count() != len(method_ids):
                raise ValueError("Unknown method ID in enrichment proposal")
            current_tasks = (
                self.db.query(PaperTask)
                .filter(PaperTask.paper_id == row.paper_id)
                .all()
            )
            protected_tasks = {
                item.task_id for item in current_tasks if item.source != "auto"
            }
            if not protected_tasks <= task_ids:
                raise ValueError("Scheduled enrichment cannot remove manual task links")
            removed_auto_tasks = {
                item.task_id for item in current_tasks if item.source == "auto"
            } - task_ids
            if removed_auto_tasks - set(mutation.task_removal_reasons):
                raise ValueError("Every automated task removal requires a reason")
            evidence = (
                self.db.query(PaperMethodEvidence)
                .filter(PaperMethodEvidence.paper_id == row.paper_id)
                .all()
            )
            protected_methods = {
                item.method_id
                for item in evidence
                if item.evidence_type in {"manual", "source", "legacy_unknown"}
            }
            if not protected_methods <= method_ids:
                raise ValueError(
                    "Scheduled enrichment cannot remove protected method links"
                )
            current_methods = {
                item.method_id
                for item in self.db.query(PaperMethod).filter(
                    PaperMethod.paper_id == row.paper_id
                )
            }
            removed_methods = current_methods - method_ids
            if removed_methods - set(mutation.method_removal_reasons):
                raise ValueError("Every automated method removal requires a reason")
            for link in mutation.repositories or []:
                parsed = urlsplit(link.url)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname != "github.com"
                    or len(parsed.path.strip("/").split("/")) < 2
                ):
                    raise ValueError(
                        "Repository links must be public GitHub repository URLs"
                    )
            if mutation.repositories is not None:
                current_urls = {
                    repository.url
                    for repository, _is_official in self.db.query(
                        Repository, PaperRepository.is_official
                    )
                    .join(
                        PaperRepository,
                        PaperRepository.repository_id == Repository.id,
                    )
                    .filter(PaperRepository.paper_id == row.paper_id)
                }
                if not current_urls <= {link.url for link in mutation.repositories}:
                    raise ValueError(
                        "Scheduled enrichment cannot remove an existing repository"
                    )
            removed_pages: set[str] = set()
            if mutation.project_pages is not None:
                current_pages = {
                    page.url: getattr(page, "source", "unknown")
                    for page in self.db.get(Paper, row.paper_id).project_pages
                }
                # Legacy imported HTTP pages may be retained unchanged. New
                # project links still require HTTPS.
                for link in mutation.project_pages:
                    if (
                        link.url not in current_pages
                        and urlsplit(link.url).scheme != "https"
                    ):
                        raise ValueError("Project page links must use HTTPS")
                removed_pages = set(current_pages) - {
                    link.url for link in mutation.project_pages
                }
                protected_pages = {
                    url for url in removed_pages if current_pages[url] != "hf_api"
                }
                if protected_pages:
                    raise ValueError(
                        "Scheduled enrichment cannot remove a non-HF-imported project page"
                    )
                if removed_pages and mutation.urls_extracted is not True:
                    raise ValueError(
                        "Scheduled project-page removal requires a complete URL search"
                    )
                missing_reasons = {
                    url
                    for url in removed_pages
                    if not mutation.project_page_removal_reasons.get(url, "").strip()
                }
                if missing_reasons:
                    raise ValueError(
                        "Every HF-imported project-page removal requires a reason"
                    )
                if any(
                    len(reason) > 2_000
                    for url, reason in mutation.project_page_removal_reasons.items()
                    if url in removed_pages
                ):
                    raise ValueError("Project-page removal reason is too long")
            return {
                "policy": "scheduled-enrich-v1",
                "removed_auto_tasks": sorted(removed_auto_tasks),
                "removed_methods": sorted(removed_methods),
                "removed_hf_api_project_pages": sorted(removed_pages),
            }

        paper = self.db.get(Paper, row.paper_id)
        paper_route = paper.arxiv_id if paper.source != "external" else paper.id
        expected_source = f"https://paperswithcode.co/paper/{paper_route}"
        leaderboard_keys = [
            (item.task_id, item.dataset_id, item.best_metric)
            for item in body.evaluations
        ]
        if len(leaderboard_keys) != len(set(leaderboard_keys)):
            raise ValueError(
                "Scheduled curation accepts only the best eligible target result "
                "per leaderboard"
            )
        evidence_by_id = {
            int(item["evaluation_id"]): item
            for item in body.validation_evidence
            if isinstance(item, dict) and str(item.get("evaluation_id", "")).isdigit()
        }
        # Identical repeats and entries for rows the curator dropped are
        # harmless; only conflicting or missing source cells are rejected.
        score_evidence = {}
        for entry in body.score_evidence:
            key = (entry.task_id, entry.dataset_id, entry.metric)
            if score_evidence.setdefault(key, entry) != entry:
                raise ValueError(
                    "Scheduled evaluations require exactly one score_evidence entry "
                    f"per task/dataset/metric; conflicting entries for {list(key)}"
                )
        missing_score_keys = sorted(
            {
                (item.task_id, item.dataset_id, metric)
                for item in body.evaluations
                for metric in item.metrics
            }
            - set(score_evidence)
        )
        if missing_score_keys:
            raise ValueError(
                "Scheduled evaluations require exactly one score_evidence entry "
                "per task/dataset/metric with source_value, source_scale, source_url, "
                "and table_reference in the top-level score_evidence array; copy the "
                "original source cell before conversion. Missing [task_id, "
                f"dataset_id, metric]: {[list(key) for key in missing_score_keys]}"
            )
        for item in body.evaluations:
            leaderboard = (
                self.db.query(TaskDataset)
                .filter(
                    TaskDataset.task_id == item.task_id,
                    TaskDataset.dataset_id == item.dataset_id,
                )
                .one_or_none()
            )
            if leaderboard is None:
                raise ValueError(
                    "Evaluation targets an unconfigured task/dataset leaderboard"
                )
            configured_rows = (
                self.db.query(Metric)
                .join(TaskDatasetMetric, TaskDatasetMetric.metric_id == Metric.id)
                .filter(
                    TaskDatasetMetric.task_id == item.task_id,
                    TaskDatasetMetric.dataset_id == item.dataset_id,
                )
                .all()
            )
            configured = {metric.name: metric for metric in configured_rows}
            if item.best_metric not in configured or set(item.metrics) - set(
                configured
            ):
                raise ValueError("Evaluation contains an unconfigured metric")
            if item.harness and not leaderboard.supports_harness:
                raise ValueError("Harness is not supported by this leaderboard")
            # Scheduled jobs do not get to choose the catalog source URL.  The
            # paper route is already known and is the only accepted value, so
            # canonicalize it deterministically instead of turning a harmless
            # agent formatting mistake into a circuit-breaker event.  Primary
            # arXiv/HF URLs remain available in validation evidence and traces.
            item.source_url = expected_source
            # EvaluationService keeps both legacy source columns synchronized.
            item.external_source_url = expected_source
            for metric_name, value in item.metrics.items():
                try:
                    numeric = float(str(value).rstrip("%"))
                except ValueError as exc:
                    raise ValueError("Evaluation metric must be numeric") from exc
                if not math.isfinite(numeric):
                    raise ValueError("Evaluation metric must be finite")
                self._validate_metric_scale(configured[metric_name].scale, numeric)
                evidence = score_evidence[(item.task_id, item.dataset_id, metric_name)]
                validate_source_score(configured[metric_name].scale, numeric, evidence)
                validate_board_scale(
                    configured[metric_name].scale,
                    evidence,
                    lambda: self._board_metric_values(item, metric_name),
                )
            matches = self._matching_evaluations(item)
            if matches:
                canonical = self._canonical_evaluation(matches)
                changes = self._evaluation_changes(canonical, item)
                if not changes and len(matches) == 1:
                    continue
                audit = evidence_by_id.get(canonical.id)
                if not audit:
                    raise ValueError(
                        "Existing evaluation updates require matched-row evidence"
                    )
                before = audit.get("before_state")
                if before != self._evaluation_state(canonical):
                    raise ValueError(
                        "Existing evaluation changed after proposal context was read"
                    )
                supplied_diff = dict(audit.get("field_diff") or {})
                for field in ("source_url", "external_source_url"):
                    if field in changes:
                        supplied_diff[field] = changes[field]
                audit["field_diff"] = supplied_diff
                if audit.get("field_diff") != changes or not audit.get("evidence"):
                    raise ValueError(
                        "Evaluation update requires the exact field diff and primary evidence"
                    )
                if len(matches) > 1:
                    duplicate_ids = sorted(
                        int(value)
                        for value in audit.get("duplicate_evaluation_ids", [])
                    )
                    if duplicate_ids != sorted(value.id for value in matches):
                        raise ValueError(
                            "Duplicate consolidation requires every matched row ID"
                        )
                    if not audit.get("canonical_selection_reason"):
                        raise ValueError(
                            "Duplicate consolidation requires a selection reason"
                        )
                    duplicate_states = audit.get("duplicate_before_states")
                    if not isinstance(duplicate_states, list):
                        raise ValueError(
                            "Duplicate consolidation requires every before-state"
                        )
                    states_by_id = {
                        value.get("id"): value
                        for value in duplicate_states
                        if isinstance(value, dict)
                    }
                    if states_by_id != {
                        value.id: self._evaluation_state(value) for value in matches
                    }:
                        raise ValueError(
                            "Duplicate consolidation before-states are incomplete or stale"
                        )
        for removal in body.evaluation_removals:
            existing = self.db.get(Evaluation, removal.evaluation_id)
            if removal.before_state != self._evaluation_state(existing):
                raise ValueError(
                    "Evaluation removal target changed after context was read"
                )
            if not removal.evidence:
                raise ValueError("Evaluation removal requires primary-source evidence")
        return {
            "policy": "scheduled-add-evals-v1",
            "evaluations": len(body.evaluations),
        }

    def _validate_scheduled_capability_boundary(
        self, row, body: ApplyMutationRequest
    ) -> tuple[tuple[Capability, ResourceRef], ...]:
        """Resolve the callback's closed mutation surface from catalog state."""
        capability, primary_resource = curation_primary_authorization(self.db, row)
        if row.kind == "review-benchmark-gaps" and body.review_benchmark_gaps:
            # A mistyped id is a fixable proposal error, not a capability denial.
            scope = set(self._review_scope(row))
            outside = [
                str(decision.candidate_id)
                for decision in body.review_benchmark_gaps.decisions
                if str(decision.candidate_id) not in scope
            ]
            if outside:
                raise ValueError(
                    "Candidates outside this review's batch: "
                    f"{', '.join(outside[:20])}. Copy each candidate_id exactly "
                    "from context.review.candidates"
                )
            return tuple(
                (
                    capability,
                    ResourceRef(
                        ResourceKind.BENCHMARK_CANDIDATE,
                        str(decision.candidate_id),
                        self.db.get(BenchmarkCurationCandidate, decision.candidate_id)
                        is not None,
                    ),
                )
                for decision in body.review_benchmark_gaps.decisions
            )
        if row.kind in {"resolve-model-paper", *BENCHMARK_GAP_KINDS}:
            return ((capability, primary_resource),)
        resources: list[ResourceRef] = [primary_resource]
        if body.enrich is not None:
            resources.extend(
                ResourceRef(
                    ResourceKind.TASK,
                    str(task_id),
                    self.db.get(Task, task_id) is not None,
                )
                for task_id in body.enrich.task_ids or []
            )
            resources.extend(
                ResourceRef(
                    ResourceKind.METHOD,
                    str(method_id),
                    self.db.get(Method, method_id) is not None,
                )
                for method_id in body.enrich.method_ids or []
            )
        # Evaluation task/dataset/metric references are resolved against the
        # configured TaskDataset and TaskDatasetMetric rows immediately below.
        for resource in resources:
            if resource.kind not in CAPABILITY_RESOURCE_KINDS[capability]:
                raise AutonomousCapabilityDenied("resource_kind_not_allowed")
            if not resource.exists:
                raise AutonomousCapabilityDenied("resource_not_found")
        return tuple((capability, resource) for resource in resources)

    @staticmethod
    def _validate_metric_scale(scale: str | None, value: float) -> None:
        """Enforce explicit finite numeric ranges without guessing missing metadata."""
        bounds = metric_scale_bounds(scale)
        if bounds is not None and not bounds[0] <= value <= bounds[1]:
            raise ValueError(
                f"Evaluation metric value {value:g} is outside configured scale {scale}"
            )

    def _board_metric_values(self, item, metric_name: str) -> list[float]:
        """Numeric values of one metric on a leaderboard, excluding this paper."""
        rows = (
            self.db.query(Evaluation.metrics)
            .filter(
                Evaluation.task_id == item.task_id,
                Evaluation.dataset_id == item.dataset_id,
                Evaluation.paper_id != item.paper_id,
                Evaluation.metrics.has_key(metric_name),
            )
            .all()
        )
        values = (parse_metric_value(metrics[metric_name]) for (metrics,) in rows)
        return [value for value in values if value is not None]

    def _matching_evaluations(self, item) -> list[Evaluation]:
        return (
            self.db.query(Evaluation)
            .filter(
                Evaluation.paper_id == item.paper_id,
                Evaluation.task_id == item.task_id,
                Evaluation.dataset_id == item.dataset_id,
                Evaluation.model_name == item.model_name,
                _evaluation_harness_clause(item.harness),
                Evaluation.best_metric == item.best_metric,
            )
            .all()
        )

    @staticmethod
    def _canonical_evaluation(matches: list[Evaluation]) -> Evaluation:
        return max(
            matches,
            key=lambda value: (
                sum(
                    field is not None
                    for field in (
                        getattr(value, "methodology", None),
                        getattr(value, "source_url", None),
                        getattr(value, "external_source_url", None),
                        getattr(value, "num_parameters", None),
                        getattr(value, "hf_model_url", None),
                    )
                ),
                -value.id,
            ),
        )

    @staticmethod
    def _evaluation_state(value: Evaluation) -> dict[str, Any]:
        return {
            "id": value.id,
            "paper_id": value.paper_id,
            "task_id": value.task_id,
            "dataset_id": value.dataset_id,
            "model_name": value.model_name,
            "harness": value.harness,
            "methodology": value.methodology,
            "metrics": value.metrics,
            "uses_additional_data": value.uses_additional_data,
            "is_open": value.is_open,
            "best_metric": value.best_metric,
            "source_url": value.source_url,
            "external_source_url": value.external_source_url,
            "best_rank": value.best_rank,
            "evaluated_on": value.evaluated_on.isoformat()
            if value.evaluated_on
            else None,
            "num_parameters": value.num_parameters,
            "hf_model_url": value.hf_model_url,
        }

    @classmethod
    def _evaluation_changes(cls, existing: Evaluation, item) -> dict[str, dict]:
        before = cls._evaluation_state(existing)
        proposed = item.model_dump()
        if proposed.get("evaluated_on") is not None:
            proposed["evaluated_on"] = proposed["evaluated_on"].isoformat()
        # These legacy update fields have no explicit "set" sentinel in
        # EvaluationService: None means omitted, not clear.  best_rank is also
        # recalculated after writes, so an omitted rank must accept the derived
        # catalog value during post-write verification. create_evaluation also
        # copies a paper-native source_url onto external_source_url.
        for field in (
            "methodology",
            "best_rank",
            "evaluated_on",
            "source_url",
            "external_source_url",
        ):
            if proposed.get(field) is None:
                proposed[field] = before[field]
        fields = (
            "methodology",
            "metrics",
            "uses_additional_data",
            "is_open",
            "best_rank",
            "evaluated_on",
            "source_url",
            "external_source_url",
            "num_parameters",
            "hf_model_url",
        )
        return {
            field: {"before": before[field], "after": proposed[field]}
            for field in fields
            if before[field] != proposed[field]
        }

    @staticmethod
    def _reject_sync_managed(existing: Evaluation, action: str) -> None:
        """Keep curators off rows owned by a live leaderboard sync.

        The sync rewrites its rows on every run, so a curator edit would be
        reverted at best and would corrupt the sync's methodology at worst.
        """
        if not is_sync_managed(existing.methodology):
            return
        raise ValueError(
            f"Evaluation {existing.id} ({existing.model_name!r} on task "
            f"{existing.task_id} / dataset {existing.dataset_id}) is managed by a "
            f"live leaderboard sync and cannot be {action} by curation. Leave that "
            "row unchanged: drop this item and report the benchmark as a "
            "not_applicable outcome with task_id, dataset_id, metric, and a detail "
            "saying the leaderboard row is managed by a live sync."
        )

    def _apply_evaluations(self, body: ApplyMutationRequest) -> tuple[int, int]:
        created = 0
        updated = 0
        for item in body.evaluations:
            query = self.db.query(Evaluation).filter(
                Evaluation.paper_id == item.paper_id,
                Evaluation.task_id == item.task_id,
                Evaluation.dataset_id == item.dataset_id,
                Evaluation.model_name == item.model_name,
                _evaluation_harness_clause(item.harness),
                Evaluation.best_metric == item.best_metric,
            )
            if hasattr(query, "with_for_update"):
                query = query.with_for_update()
            if hasattr(query, "all"):
                matches = query.all()
            else:
                value = query.one_or_none()
                matches = [value] if value is not None else []
            existing = self._canonical_evaluation(matches) if matches else None
            values = item.model_dump()
            if existing is None:
                self.evaluation_service.create_evaluation(**values, commit=False)
                created += 1
            else:
                changes = self._evaluation_changes(existing, item)
                if not changes and len(matches) == 1:
                    continue
                for match in matches:
                    self._reject_sync_managed(match, "updated")
                values.pop("paper_id")
                self.evaluation_service.update_evaluation(
                    existing.id,
                    **values,
                    harness_set=True,
                    source_url_set=True,
                    num_parameters_set=True,
                    hf_model_url_set=True,
                    commit=False,
                )
                updated += 1
                for duplicate in matches:
                    if duplicate.id != existing.id:
                        self.db.delete(duplicate)
        return created, updated

    def _apply_evaluation_removals(self, row, body: ApplyMutationRequest) -> int:
        removed = 0
        for removal in body.evaluation_removals:
            existing = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.id == removal.evaluation_id,
                    Evaluation.paper_id == row.paper_id,
                )
                .with_for_update()
                .one()
            )
            self._reject_sync_managed(existing, "removed")
            self.db.delete(existing)
            removed += 1
        return removed

    def _apply_enrichment(self, row, body: ApplyMutationRequest) -> dict | None:
        mutation = body.enrich
        if mutation is None:
            raise AssertionError("validated enrichment payload is missing")
        scheduled = getattr(row, "trigger", "admin") != "admin"
        if mutation.task_ids is not None and scheduled:
            desired_tasks = set(mutation.task_ids)
            current_tasks = (
                self.db.query(PaperTask)
                .filter(PaperTask.paper_id == row.paper_id)
                .all()
            )
            for link in current_tasks:
                if link.task_id not in desired_tasks:
                    self.db.delete(link)
                else:
                    desired_tasks.discard(link.task_id)
            for task_id in desired_tasks:
                self.db.add(
                    PaperTask(paper_id=row.paper_id, task_id=task_id, source="auto")
                )
        elif mutation.task_ids is not None:
            self.paper_associations.update_tasks(
                row.paper_id, mutation.task_ids, commit=False
            )
        if mutation.method_ids is not None and scheduled:
            desired_methods = set(mutation.method_ids)
            current_methods = {
                item.method_id
                for item in self.db.query(PaperMethod).filter(
                    PaperMethod.paper_id == row.paper_id
                )
            }
            for method_id in current_methods - desired_methods:
                self.db.query(PaperMethodEvidence).filter(
                    PaperMethodEvidence.paper_id == row.paper_id,
                    PaperMethodEvidence.method_id == method_id,
                ).delete(synchronize_session=False)
                link = self.db.get(PaperMethod, (row.paper_id, method_id))
                if link is not None:
                    self.db.delete(link)
            for method_id in desired_methods:
                exclusion = self.db.get(PaperMethodExclusion, (row.paper_id, method_id))
                if exclusion is not None:
                    self.db.delete(exclusion)
            self.db.flush()
            upsert_evidence_links(
                self.db,
                (
                    {"paper_id": row.paper_id, "method_id": method_id}
                    for method_id in desired_methods
                ),
                evidence_type="curation",
                details={"job_id": str(row.id), "policy_version": row.policy_version},
            )
        elif mutation.method_ids is not None:
            self.paper_associations.update_methods(
                row.paper_id, mutation.method_ids, commit=False
            )
        if mutation.method_ids is not None:
            for method_id, reason in mutation.method_removal_reasons.items():
                exclusion = self.db.get(PaperMethodExclusion, (row.paper_id, method_id))
                if exclusion is None:
                    self.db.add(
                        PaperMethodExclusion(
                            paper_id=row.paper_id,
                            method_id=method_id,
                            reason=reason[:2_000],
                        )
                    )
                else:
                    exclusion.reason = reason[:2_000]
                    exclusion.updated_at = datetime.now(UTC)
        if mutation.repositories is not None:
            self.paper_associations.update_repositories(
                row.paper_id,
                [item.model_dump() for item in mutation.repositories],
                commit=False,
            )
        if mutation.project_pages is not None:
            self.paper_associations.update_project_pages(
                row.paper_id,
                [item.model_dump() for item in mutation.project_pages],
                commit=False,
            )
        paper = self.db.get(Paper, row.paper_id)
        if mutation.thumbnail_url is not None:
            paper.thumbnail_url = mutation.thumbnail_url
        if mutation.urls_extracted is not None:
            paper.urls_extracted = mutation.urls_extracted
        if any(
            value is not None
            for value in (mutation.hf_models, mutation.hf_datasets, mutation.hf_spaces)
        ):
            self.paper_associations.update_hf_artifacts(
                row.paper_id,
                mutation.hf_models
                if mutation.hf_models is not None
                else (paper.hf_models or []),
                mutation.hf_datasets
                if mutation.hf_datasets is not None
                else (paper.hf_datasets or []),
                mutation.hf_spaces
                if mutation.hf_spaces is not None
                else (paper.hf_spaces or []),
                commit=False,
            )
        if mutation.regenerate_thumbnail:
            queue_thumbnail(row)
        if not mutation.organizations:
            return None
        organizations = CurationOrganizationService(self.db)
        try:
            return organizations.link(row.paper_id, mutation.organizations).to_dict()
        finally:
            organizations.close()
