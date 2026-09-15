"""Admin catalog-audit reads, eligibility checks, and rollback dispatch."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.models.database import CatalogMutationEvent, PaperEditAccount
from backend.services.catalog_mutation_service import (
    CatalogMutationService,
    canonical_hash,
    json_safe,
)
from backend.services.evaluation_curation_service import EvaluationCurationService
from backend.services.paper_curation_service import PaperCurationService
from backend.services.submission_rollback_service import SubmissionRollbackService
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


class ContributionAuditEventNotFoundError(LookupError):
    """The requested audit event does not exist."""


class ContributionAuditRollbackError(ValueError):
    """The requested event cannot be rolled back."""


class ContributionAuditService:
    """Own the admin audit page and its compensating rollback workflow."""

    def __init__(self, db: Session):
        self.db = db

    def list_admin_audit(
        self, *, admin_subject: str, cursor: str | None, limit: int
    ) -> dict:
        mutation_service = CatalogMutationService(self.db)
        page = mutation_service.list_events(
            actor_subject=None, cursor=cursor, limit=limit
        )
        events_by_id = {
            str(row.id): row
            for row in self.db.query(CatalogMutationEvent)
            .filter(
                CatalogMutationEvent.id.in_(
                    [uuid.UUID(item["id"]) for item in page["events"]]
                )
            )
            .all()
        }
        subjects = {row.actor_hf_subject for row in events_by_id.values()}
        suspended = (
            {
                row.hf_subject
                for row in self.db.query(PaperEditAccount)
                .filter(
                    PaperEditAccount.hf_subject.in_(subjects),
                    PaperEditAccount.suspended,
                )
                .all()
            }
            if subjects
            else set()
        )
        for item in page["events"]:
            event = events_by_id[item["id"]]
            item["actor_hf_subject"] = event.actor_hf_subject
            item["editing_suspended"] = event.actor_hf_subject in suspended
            item["paper_id"] = event.paper_id
            item["rollback_eligible"] = self.is_rollback_eligible(
                events_by_id[item["id"]]
            )
        page["unread_contributor_count"] = mutation_service.unread_count(admin_subject)
        return page

    def is_rollback_eligible(self, event: CatalogMutationEvent) -> bool:
        if event.operation == "rollback":
            return False
        try:
            if event.entity_type == "paper_edit_batch":
                from backend.services.paper_edit_service import PaperEditService

                current = PaperEditService(self.db).rollback_snapshot(event)
            elif event.entity_type.startswith("paper_"):
                section = event.entity_type.removeprefix("paper_")
                current = PaperCurationService(self.db).snapshot(
                    int(event.entity_id), section
                )
            elif event.entity_type == "evaluation":
                service = EvaluationCurationService(self.db)
                if event.entity_id.startswith("paper:"):
                    current = service.paper_evaluations(
                        int(event.entity_id.split(":", 1)[1])
                    )
                else:
                    current = service.snapshot(int(event.entity_id))
            elif event.entity_type.startswith("submission_created_"):
                current = SubmissionRollbackService(self.db).snapshot(event)
            else:
                return False
        except (ValueError, PaperNotFoundError, DatabaseError):
            return False
        return canonical_hash(json_safe(current)) == canonical_hash(
            event.after_snapshot
        )

    def acknowledge(self, admin_subject: str) -> None:
        CatalogMutationService(self.db).acknowledge(admin_subject)

    def rollback_event(
        self,
        *,
        event_id: uuid.UUID,
        actor: dict,
        request_id: str,
    ) -> dict:
        event = self.db.get(CatalogMutationEvent, event_id)
        if event is None:
            raise ContributionAuditEventNotFoundError("Audit event not found")
        if event.operation == "rollback":
            raise ContributionAuditRollbackError(
                "Rollback events cannot be rolled back"
            )
        if event.entity_type == "paper_edit_batch":
            from backend.services.paper_edit_service import PaperEditService

            rollback = PaperEditService(self.db).rollback(
                event=event, actor=actor, request_id=request_id
            )
        elif event.entity_type == "evaluation":
            rollback = EvaluationCurationService(self.db).rollback(
                event=event, actor=actor, request_id=request_id
            )
        elif event.entity_type.startswith("paper_"):
            rollback = PaperCurationService(self.db).rollback(
                event=event, actor=actor, request_id=request_id
            )
        elif event.entity_type.startswith("submission_created_"):
            rollback = SubmissionRollbackService(self.db).rollback(
                event=event, actor=actor, request_id=request_id
            )
        else:
            raise ContributionAuditRollbackError(
                "This event type is not rollback eligible"
            )
        return CatalogMutationService.serialize_event(rollback)
