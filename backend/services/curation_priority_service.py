"""Durable priority membership controls admission and background dispatch.

HF daily papers and papers trending on X (the daily "AI Papers on X" sheet)
jump the curation queue; X-trending papers go first.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models.database import (
    Paper,
    PaperCurationJob,
    PaperCurationWorkflow,
    PaperXTrending,
)

# Lower runs first. Unprioritized backlog uses 100.
X_TRENDING_PRIORITY = 5
DAILY_PRIORITY = 10


def is_priority_paper():
    """SQL clause: the paper is an HF daily paper or has trended on X."""
    return or_(
        Paper.hf_daily_featured_on.isnot(None),
        Paper.id.in_(select(PaperXTrending.paper_id)),
    )


def pending_daily_papers(db: Session):
    completed_workflow = (
        db.query(PaperCurationWorkflow.id)
        .filter(
            PaperCurationWorkflow.paper_id == Paper.id,
            PaperCurationWorkflow.status.in_({"completed", "satisfied"}),
        )
        .exists()
    )
    # Also honor manual curation completed before scheduled workflows existed.
    stages = [
        db.query(PaperCurationJob.id)
        .filter(
            PaperCurationJob.paper_id == Paper.id,
            PaperCurationJob.kind == kind,
            PaperCurationJob.status == "completed",
        )
        .exists()
        for kind in ("enrich-paper", "add-evals")
    ]
    return db.query(Paper).filter(
        Paper.is_latest_version,
        is_priority_paper(),
        ~completed_workflow,
        ~(stages[0] & stages[1]),
    )


def pending_x_trending_papers(db: Session):
    """Pending arXiv papers trending on X as (paper, last shared day) rows.

    Most recently shared first, then by best sheet rank.
    """
    shared = (
        db.query(
            PaperXTrending.paper_id,
            func.max(PaperXTrending.shared_on).label("shared_on"),
            func.min(PaperXTrending.rank).label("rank"),
        )
        .group_by(PaperXTrending.paper_id)
        .subquery()
    )
    return (
        pending_daily_papers(db)
        .join(shared, shared.c.paper_id == Paper.id)
        .filter(Paper.arxiv_id.isnot(None))
        .order_by(shared.c.shared_on.desc(), shared.c.rank, Paper.id)
        .with_entities(Paper, shared.c.shared_on)
    )


def has_pending_daily_papers(db: Session) -> bool:
    return pending_daily_papers(db).with_entities(Paper.id).first() is not None
