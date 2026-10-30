"""Read-only selection of settled, paper-native evaluations and official code."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from backend.models.database import (
    Evaluation,
    Paper,
    PaperCurationJob,
    PaperCurationWorkflow,
    PaperRepository,
    Repository,
)
from backend.services.contributor_evaluations import contributor_evaluation_ids
from backend.services.github_issue_body_service import normalize_repository_url
from backend.services.github_issue_publish_service import _is_excluded_repository


@dataclass(frozen=True)
class OutreachPaper:
    id: int
    route: str
    ready: bool
    evaluated_at: float = 0


def candidates(
    db: Session, settled_before: datetime
) -> dict[str, dict[int, OutreachPaper]]:
    # Rows the paper's authors added themselves are not ours to announce.
    native = (
        select(Evaluation.paper_id, func.max(Evaluation.created_at).label("last_added"))
        .where(
            ~Evaluation.external,
            Evaluation.id.not_in(contributor_evaluation_ids(db)),
        )
        .group_by(Evaluation.paper_id)
        .subquery()
    )
    active_job = exists(
        select(PaperCurationJob.id).where(
            PaperCurationJob.paper_id == Paper.id,
            PaperCurationJob.status.in_(("queued", "dispatching", "running")),
        )
    )
    active_workflow = exists(
        select(PaperCurationWorkflow.id).where(
            PaperCurationWorkflow.paper_id == Paper.id,
            PaperCurationWorkflow.status.in_(("queued", "running", "deferred")),
        )
    )
    rows = db.execute(
        select(
            Repository.url,
            Paper.id,
            Paper.arxiv_id,
            native.c.last_added,
            active_job.label("active_job"),
            active_workflow.label("active_workflow"),
        )
        .join(PaperRepository, PaperRepository.repository_id == Repository.id)
        .join(Paper, Paper.id == PaperRepository.paper_id)
        .join(native, native.c.paper_id == Paper.id)
        .where(PaperRepository.is_official, Paper.is_latest_version)
        .order_by(Repository.id, Paper.id)
    )
    grouped = defaultdict(dict)
    for url, paper_id, arxiv_id, last_added, job_active, workflow_active in rows:
        try:
            repository = normalize_repository_url(url).lower()
        except ValueError:
            continue
        if not _is_excluded_repository(repository):
            grouped[repository][paper_id] = OutreachPaper(
                paper_id,
                arxiv_id or str(paper_id),
                last_added <= settled_before and not job_active and not workflow_active,
                last_added.timestamp(),
            )
    return dict(grouped)
