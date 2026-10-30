"""Evaluation rows that contributors added through the paper-page editor."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models.database import CatalogMutationEvent, PendingPaperEdit


def snapshot_evaluation_ids(snapshot) -> set[int]:
    """Evaluation ids in a catalog mutation snapshot of any recorded shape.

    Paper edit batches nest rows under ``evaluations``, paper-scoped evaluation
    events store a list, and single-row update/delete events store one object.
    """
    if isinstance(snapshot, dict):
        snapshot = snapshot.get("evaluations", [snapshot])
    return {int(row["id"]) for row in snapshot or [] if row.get("id") is not None}


def contributor_evaluation_ids(db: Session) -> set[int]:
    """Ids of evaluations created by a contributor edit or an approved queued edit.

    Not filtered by paper: rows can move to another paper after the edit, and
    approval events do not always record a paper id.
    """
    approved_edits = select(PendingPaperEdit.catalog_event_id).where(
        PendingPaperEdit.edit_type == "evaluations",
        PendingPaperEdit.status == "approved",
        PendingPaperEdit.catalog_event_id.is_not(None),
    )
    statement = select(
        CatalogMutationEvent.before_snapshot, CatalogMutationEvent.after_snapshot
    ).where(
        CatalogMutationEvent.entity_type.in_(("paper_edit_batch", "evaluation")),
        or_(
            CatalogMutationEvent.actor_role == "contributor",
            CatalogMutationEvent.id.in_(approved_edits),
        ),
    )
    return {
        evaluation_id
        for before, after in db.execute(statement)
        for evaluation_id in snapshot_evaluation_ids(after)
        - snapshot_evaluation_ids(before)
    }
