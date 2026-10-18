"""Queue enrich-paper then add-evals for every newly created external paper.

External papers (model cards, release blogs, vendor reports) are created by
admins, agents, and leaderboard syncs. None of the scheduled curation paths
(HF daily papers, top HF trending models, benchmark gaps) reach them, so each
new row gets one admin-lane workflow under its own policy version.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.models.database import Paper, PaperCurationJob, PaperCurationWorkflow
from backend.services.codex_add_evals_service import (
    EXTERNAL_PAPER_POLICY_VERSION,
    CodexPaperJobService,
    codex_paper_job_service,
)
from backend.utils.urls import get_paper_route_identifier

EXTERNAL_PAPER_REQUESTED_BY = "external-paper-created"
EXTERNAL_PAPER_BACKFILL_REQUESTED_BY = "external-paper-backfill"
# Behind interactive admin jobs (priority 0) in the shared admin lane.
EXTERNAL_PAPER_PRIORITY = 50
_LIVE_JOB_STATUSES = {"queued", "dispatching", "running", "awaiting_markdown"}


def enqueue_external_paper_curation(
    db: Session,
    paper: Paper,
    *,
    settings: Settings | None = None,
    requested_by: str = EXTERNAL_PAPER_REQUESTED_BY,
    jobs: CodexPaperJobService = codex_paper_job_service,
) -> bool:
    """Add one queued enrich -> add-evals workflow (flush only, no dispatch).

    The caller's transaction commits it; the hourly curation reconcile and
    every job completion dispatch queued admin-lane work. Returns False when
    the paper is not external, already had this workflow, or already has live
    curation work.
    """
    if paper.source != "external":
        return False
    already_curated = (
        db.query(PaperCurationWorkflow.id)
        .filter(
            PaperCurationWorkflow.paper_id == paper.id,
            (PaperCurationWorkflow.policy_version == EXTERNAL_PAPER_POLICY_VERSION)
            | PaperCurationWorkflow.status.in_({"queued", "running", "deferred"}),
        )
        .first()
    )
    live_job = (
        db.query(PaperCurationJob.id)
        .filter(
            PaperCurationJob.paper_id == paper.id,
            PaperCurationJob.kind.in_({"enrich-paper", "add-evals"}),
            PaperCurationJob.status.in_(_LIVE_JOB_STATUSES),
        )
        .first()
    )
    if already_curated is not None or live_job is not None:
        return False
    workflow = PaperCurationWorkflow(
        id=uuid.uuid4(),
        paper_id=paper.id,
        cohort_date=datetime.now(UTC).date(),
        cohort_order=0,
        policy_version=EXTERNAL_PAPER_POLICY_VERSION,
        status="queued",
    )
    db.add(workflow)
    db.flush()
    jobs.enqueue(
        db,
        kind="enrich-paper",
        paper_id=paper.id,
        paper_route=get_paper_route_identifier(paper.source, paper.arxiv_id, paper.id),
        paper_title=paper.title,
        requested_by=requested_by,
        settings=settings or get_settings(),
        trigger="admin",
        parent_workflow_id=workflow.id,
        cohort_date=workflow.cohort_date,
        policy_version=EXTERNAL_PAPER_POLICY_VERSION,
        priority=EXTERNAL_PAPER_PRIORITY,
        dispatch=False,
        commit=False,
    )
    return True


def backfill_external_paper_curation(
    db: Session,
    *,
    days: int,
    limit: int,
    dry_run: bool = False,
    settings: Settings | None = None,
    jobs: CodexPaperJobService = codex_paper_job_service,
) -> dict:
    """Queue recent external papers that never had any curation job.

    Papers with Hugging Face models go first, newest first within each group.
    """
    has_job = (
        db.query(PaperCurationJob.id)
        .filter(PaperCurationJob.paper_id == Paper.id)
        .exists()
    )
    candidates = (
        db.query(Paper)
        .filter(
            Paper.source == "external",
            Paper.created_at >= datetime.now(UTC) - timedelta(days=days),
            ~has_job,
        )
        .all()
    )
    candidates.sort(key=lambda paper: paper.created_at, reverse=True)
    candidates.sort(key=lambda paper: not paper.hf_models)
    queued: list[int] = []
    for paper in candidates[:limit]:
        if dry_run or enqueue_external_paper_curation(
            db,
            paper,
            settings=settings,
            requested_by=EXTERNAL_PAPER_BACKFILL_REQUESTED_BY,
            jobs=jobs,
        ):
            queued.append(paper.id)
    if not dry_run:
        db.commit()
    return {
        "dry_run": dry_run,
        "eligible": len(candidates),
        "eligible_with_hf_models": sum(bool(paper.hf_models) for paper in candidates),
        "queued": len(queued),
        "queued_paper_ids": queued,
    }
