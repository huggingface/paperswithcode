"""Scoped callback API used by remote Hugging Face Codex Jobs."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.models.api import EvaluationCreateRequest
from backend.models.database import (
    Dataset,
    Evaluation,
    Method,
    Metric,
    Paper,
    PaperRepository,
    Repository,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.codex_add_evals_service import (
    CodexPaperJob,
    CodexPaperJobsResponse,
    codex_paper_job_service,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_thumbnail_service import regenerate_paper_thumbnail
from backend.services.paper_service import PaperService
from backend.utils.auth import require_hf_admin

router = APIRouter(prefix="/admin/codex-curation/jobs", tags=["admin"])


class CurationLink(BaseModel):
    url: str
    is_official: bool = True


class EnrichPaperMutation(BaseModel):
    task_ids: list[int] | None = None
    method_ids: list[int] | None = None
    repositories: list[CurationLink] | None = None
    project_pages: list[CurationLink] | None = None
    thumbnail_url: str | None = None
    regenerate_thumbnail: bool = False
    urls_extracted: bool | None = None


class ApplyMutationRequest(BaseModel):
    evaluations: list[EvaluationCreateRequest] = Field(default_factory=list)
    enrich: EnrichPaperMutation | None = None


class CompleteJobRequest(BaseModel):
    report: str = ""
    error: str | None = None


def _require_enabled(settings: Settings) -> None:
    if not settings.codex_jobs_enabled:
        raise HTTPException(status_code=404, detail="Not found")


def _callback_job(
    job_id: uuid.UUID,
    authorization: str | None,
    db: Session,
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing job bearer token")
    row = codex_paper_job_service.authenticate(db, job_id, authorization[7:])
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid job bearer token")
    return row


def _leaderboard_inventory(db: Session, query: str) -> list[dict]:
    """Return configured leaderboard IDs and score-scale evidence for a benchmark name."""
    normalized_query = re.sub(r"[^a-z0-9]", "", query.lower())

    def match_quality(dataset: Dataset) -> str:
        names = [dataset.name, dataset.slug or "", dataset.full_name or ""]
        normalized_names = [re.sub(r"[^a-z0-9]", "", name.lower()) for name in names]
        if normalized_query in normalized_names:
            return "exact"
        if any(
            name.startswith(normalized_query) or normalized_query.startswith(name)
            for name in normalized_names
        ):
            return "close"
        return "fuzzy"

    flexible = "%" + "%".join(query.replace("_", "-").replace("-", " ").split()) + "%"
    matches = (
        db.query(Dataset, Task, TaskDataset, Metric)
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

    grouped: dict[tuple[int, int], dict] = {}
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
                "task": {"id": int(task.id), "name": task.name, "slug": task.slug},
                "match_quality": match_quality(dataset),
                "supports_harness": bool(task_dataset.supports_harness),
                "metrics": [],
            }
        if key not in grouped:
            continue

        examples = (
            db.query(Evaluation)
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


@router.get("", response_model=CodexPaperJobsResponse)
def list_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """List the durable paper-curation queue and recent execution history."""
    _require_enabled(settings)
    return codex_paper_job_service.list_jobs(db, settings, limit=limit)


@router.get("/{job_id}/context")
def get_context(
    job_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    paper = db.get(Paper, row.paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    repositories = (
        db.query(Repository, PaperRepository.is_official)
        .join(PaperRepository, PaperRepository.repository_id == Repository.id)
        .filter(PaperRepository.paper_id == paper.id)
        .all()
    )
    return {
        "job": codex_paper_job_service._serialize(row, settings).model_dump(
            mode="json"
        ),
        "paper": {
            "id": paper.id,
            "title": paper.title,
            "abstract": paper.abstract,
            "arxiv_id": paper.arxiv_id,
            "source": paper.source,
            "source_url": paper.source_url,
            "date_published": paper.date_published,
            "urls_extracted": paper.urls_extracted,
            "thumbnail_url": paper.thumbnail_url,
            "tasks": [
                {"id": task.id, "name": task.name, "slug": task.slug}
                for task in paper.tasks
            ],
            "methods": [
                {"id": method.id, "name": method.name, "slug": method.slug}
                for method in paper.methods
            ],
            "repositories": [
                {"url": repository.url, "is_official": is_official}
                for repository, is_official in repositories
            ],
            "project_pages": [
                {"url": page.url, "is_official": page.is_official}
                for page in paper.project_pages
            ],
        },
    }


@router.get("/{job_id}/taxonomy")
def search_taxonomy(
    job_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=120),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    _callback_job(job_id, authorization, db)
    pattern = f"%{q}%"
    return {
        "tasks": [
            {"id": task.id, "name": task.name, "slug": task.slug}
            for task in db.query(Task)
            .filter(or_(Task.name.ilike(pattern), Task.slug.ilike(pattern)))
            .limit(30)
        ],
        "methods": [
            {"id": method.id, "name": method.name, "slug": method.slug}
            for method in db.query(Method)
            .filter(or_(Method.name.ilike(pattern), Method.slug.ilike(pattern)))
            .limit(30)
        ],
    }


@router.get("/{job_id}/leaderboards")
def search_leaderboards(
    job_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=120),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Search only existing, fully configured leaderboards for a scoped worker."""
    _require_enabled(settings)
    _callback_job(job_id, authorization, db)
    return {"query": q, "leaderboards": _leaderboard_inventory(db, q)}


@router.post("/{job_id}/apply")
async def apply_mutation(
    job_id: uuid.UUID,
    body: ApplyMutationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    if row.status in {"completed", "failed", "canceled"} or row.applied_at is not None:
        raise HTTPException(
            status_code=409, detail="This job may no longer apply mutations"
        )
    created = 0
    updated = 0
    thumbnail_result = None
    if row.kind == "add-evals":
        if body.enrich is not None:
            raise HTTPException(
                status_code=422, detail="Enrichment is not allowed for this job"
            )
        evaluation_service = EvaluationService(db)
        for item in body.evaluations:
            if item.paper_id != row.paper_id:
                raise HTTPException(
                    status_code=403, detail="Evaluation paper does not match job"
                )
            existing = (
                db.query(Evaluation)
                .filter(
                    Evaluation.paper_id == item.paper_id,
                    Evaluation.task_id == item.task_id,
                    Evaluation.dataset_id == item.dataset_id,
                    Evaluation.model_name == item.model_name,
                    Evaluation.harness.is_(item.harness),
                    Evaluation.best_metric == item.best_metric,
                )
                .one_or_none()
            )
            values = item.model_dump()
            if existing is None:
                evaluation_service.create_evaluation(**values)
                created += 1
            else:
                values.pop("paper_id")
                evaluation_service.update_evaluation(
                    existing.id,
                    **values,
                    harness_set=True,
                    source_url_set=True,
                    num_parameters_set=True,
                    hf_model_url_set=True,
                )
                updated += 1
    else:
        if body.evaluations:
            raise HTTPException(
                status_code=422, detail="Evaluations are not allowed for this job"
            )
        if body.enrich is None:
            raise HTTPException(
                status_code=422, detail="Enrichment payload is required"
            )
        paper_service = PaperService(db)
        mutation = body.enrich
        if mutation.task_ids is not None:
            paper_service.update_paper_tasks(row.paper_id, mutation.task_ids)
        if mutation.method_ids is not None:
            paper_service.update_paper_methods(row.paper_id, mutation.method_ids)
        if mutation.repositories is not None:
            paper_service.update_paper_repositories(
                row.paper_id, [item.model_dump() for item in mutation.repositories]
            )
        if mutation.project_pages is not None:
            paper_service.update_paper_project_pages(
                row.paper_id, [item.model_dump() for item in mutation.project_pages]
            )
        paper = db.get(Paper, row.paper_id)
        if mutation.thumbnail_url is not None:
            paper.thumbnail_url = mutation.thumbnail_url
        if mutation.urls_extracted is not None:
            paper.urls_extracted = mutation.urls_extracted
        db.commit()
        if mutation.regenerate_thumbnail:
            thumbnail_result = await regenerate_paper_thumbnail(
                db, str(row.paper_id), force=True
            )
    changed = row.kind == "enrich-paper" or created + updated > 0
    if changed:
        row.applied_at = datetime.now(UTC)
        db.commit()
    response = {
        "status": "applied" if changed else "no_changes",
        "evaluations_created": created,
        "evaluations_updated": updated,
    }
    if thumbnail_result is not None:
        response["thumbnail"] = {
            "status": "regenerated",
            "thumbnail_url": thumbnail_result.thumbnail_url,
            "previous_dimensions": (
                [thumbnail_result.previous.width, thumbnail_result.previous.height]
                if thumbnail_result.previous
                else None
            ),
            "generated_dimensions": [
                thumbnail_result.generated.width,
                thumbnail_result.generated.height,
            ],
            "success": thumbnail_result.success,
            "warnings": list(thumbnail_result.warnings),
        }
    return response


@router.post("/{job_id}/complete", response_model=CodexPaperJob)
def complete_job(
    job_id: uuid.UUID,
    body: CompleteJobRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    return codex_paper_job_service.complete(
        db, row, report=body.report, error=body.error, settings=settings
    )
