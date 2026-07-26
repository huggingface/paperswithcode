"""Admin endpoints for paper evaluation curation jobs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.models.database import Paper, PaperCurationJob
from backend.services.codex_add_evals_service import (
    CodexPaperJob,
    codex_paper_job_service,
)
from backend.utils.auth import require_hf_admin
from backend.utils.urls import get_paper_route_identifier

router = APIRouter(prefix="/admin/codex-add-evals", tags=["admin"])


class StartCodexAddEvalsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: int


def _require_enabled(settings: Settings) -> None:
    if not settings.codex_jobs_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.post("/jobs", response_model=CodexPaperJob, status_code=202)
async def start_job(
    body: StartCodexAddEvalsRequest,
    admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    paper = db.query(Paper).filter(Paper.id == body.paper_id).one_or_none()
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    route = get_paper_route_identifier(paper.source, paper.arxiv_id, paper.id)
    return codex_paper_job_service.enqueue(
        db,
        kind="add-evals",
        paper_id=paper.id,
        paper_route=route,
        paper_title=paper.title,
        requested_by=admin["username"],
        settings=settings,
    )


@router.get("/jobs/{job_id}", response_model=CodexPaperJob)
async def get_job(
    job_id: uuid.UUID,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    job = codex_paper_job_service.get(db, job_id, settings)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/jobs/{job_id}", response_model=CodexPaperJob)
async def cancel_job(
    job_id: uuid.UUID,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = db.get(PaperCurationJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return codex_paper_job_service.cancel(db, row, settings)
