"""Durable HF daily membership controls admission and background dispatch."""

from sqlalchemy.orm import Session

from backend.models.database import Paper, PaperCurationJob, PaperCurationWorkflow


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
        Paper.hf_daily_featured_on.isnot(None),
        ~completed_workflow,
        ~(stages[0] & stages[1]),
    )


def has_pending_daily_papers(db: Session) -> bool:
    return pending_daily_papers(db).with_entities(Paper.id).first() is not None
