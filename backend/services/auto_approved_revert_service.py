"""Bulk revert of one account's auto-applied paper edits."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.models.database import CatalogMutationEvent
from backend.services.catalog_errors import CatalogError
from backend.services.contribution_audit_service import (
    ContributionAuditRollbackError,
    ContributionAuditService,
)
from backend.utils.exceptions import DatabaseError


class AutoApprovedRevertService:
    def __init__(self, db: Session):
        self.db = db

    def _events(self, hf_subject: str, since: datetime) -> list[CatalogMutationEvent]:
        reverted = self.db.query(CatalogMutationEvent.rollback_of_event_id).filter(
            CatalogMutationEvent.rollback_of_event_id.isnot(None)
        )
        return (
            self.db.query(CatalogMutationEvent)
            .filter(
                CatalogMutationEvent.actor_hf_subject == hf_subject,
                CatalogMutationEvent.operation == "approve_submission",
                CatalogMutationEvent.request_id.like("submission-auto:%"),
                CatalogMutationEvent.created_at >= since,
                CatalogMutationEvent.id.notin_(reverted),
            )
            .order_by(CatalogMutationEvent.created_at.desc())
            .all()
        )

    def revert(
        self, *, hf_subject: str, since: datetime, actor: dict, request_id: str
    ) -> dict:
        """Roll back newest first; edits changed since are skipped and reported."""
        audit = ContributionAuditService(self.db)
        reverted = 0
        skipped = []
        for event in self._events(hf_subject, since):
            event_id = event.id
            try:
                audit.rollback_event(
                    event_id=event_id,
                    actor=actor,
                    request_id=f"{request_id}:{event_id}",
                )
            except (CatalogError, ContributionAuditRollbackError, DatabaseError) as exc:
                self.db.rollback()
                skipped.append({"event_id": str(event_id), "reason": str(exc)})
            else:
                reverted += 1
        return {"reverted": reverted, "skipped": skipped}
