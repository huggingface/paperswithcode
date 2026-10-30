"""Durable priority membership controls admission and background dispatch.

HF daily papers and papers trending on X (the daily "AI Papers on X" sheet)
jump the curation queue; X-trending papers go first.
"""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from backend.models.database import (
    Paper,
    PaperCurationJob,
    PaperCurationWorkflow,
    PaperXTrending,
)

# Lower runs first. Unprioritized backlog uses 100.
X_TRENDING_PRIORITY = 5
DAILY_PRIORITY = 10


def _x_trending_by_arxiv_id():
    """Shared arXiv ids with their last shared day and best sheet rank.

    Keyed by arXiv id so a newer version keeps priority, and limited to
    arXiv papers: external ones keep their own auto-curation path.
    """
    shared = aliased(Paper)
    return (
        select(
            shared.arxiv_id,
            func.max(PaperXTrending.shared_on).label("shared_on"),
            func.min(PaperXTrending.rank).label("rank"),
        )
        .join(shared, shared.id == PaperXTrending.paper_id)
        .where(shared.arxiv_id.isnot(None))
        .group_by(shared.arxiv_id)
    )


def is_priority_paper():
    """SQL clause: the paper is an HF daily paper or an arXiv paper trending on X."""
    x_trending = _x_trending_by_arxiv_id().subquery()
    return or_(
        Paper.hf_daily_featured_on.isnot(None),
        and_(
            Paper.arxiv_id.isnot(None),
            Paper.arxiv_id.in_(select(x_trending.c.arxiv_id)),
        ),
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
    shared = _x_trending_by_arxiv_id().subquery()
    return (
        pending_daily_papers(db)
        .join(shared, shared.c.arxiv_id == Paper.arxiv_id)
        .order_by(shared.c.shared_on.desc(), shared.c.rank, Paper.id)
        .with_entities(Paper, shared.c.shared_on)
    )


def has_pending_daily_papers(db: Session) -> bool:
    return pending_daily_papers(db).with_entities(Paper.id).first() is not None
