"""Private contributor history and admin audit endpoints."""

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.models.paper_edits import EditingSuspension
from backend.database.connection import get_database_session
from backend.services.catalog_mutation_service import CatalogMutationService
from backend.services.contribution_audit_service import (
    ContributionAuditEventNotFoundError,
    ContributionAuditRollbackError,
    ContributionAuditService,
)
from backend.utils.auth import require_admin, require_contributor_role

router = APIRouter()


@router.get("/contributions")
def own_contributions(
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    actor: dict = Depends(require_contributor_role),
    db: Session = Depends(get_database_session),
):
    return CatalogMutationService(db).list_events(
        actor_subject=actor["hf_subject"], cursor=cursor, limit=limit
    )


@router.get("/admin/catalog-audit")
def catalog_audit(
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    return ContributionAuditService(db).list_admin_audit(
        admin_subject=actor["hf_subject"], cursor=cursor, limit=limit
    )


@router.post("/admin/catalog-audit/acknowledge", status_code=204)
def acknowledge_catalog_audit(
    actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    ContributionAuditService(db).acknowledge(actor["hf_subject"])


@router.post("/admin/catalog-audit/{event_id}/rollback")
def rollback_catalog_event(
    event_id: uuid.UUID,
    request: Request,
    actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    request_id = request.headers.get("X-Request-ID") or str(id(request))
    try:
        return ContributionAuditService(db).rollback_event(
            event_id=event_id,
            actor=actor,
            request_id=request_id,
        )
    except ContributionAuditEventNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ContributionAuditRollbackError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/papers/{paper_id}/edit-history")
def paper_edit_history(
    paper_id: int,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_database_session),
):
    from backend.services.paper_edit_history import PaperEditHistory

    return PaperEditHistory(db).paper(paper_id, cursor, limit)


@router.get("/admin/paper-edit-digest")
def paper_edit_digest(
    day: date | None = None,
    page: int = Query(1, ge=1, le=10000),
    _actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    from backend.services.paper_edit_history import PaperEditHistory

    return PaperEditHistory(db).digest(day or datetime.now(UTC).date(), page)


@router.post("/admin/paper-edit-suspension")
def suspend_editing(
    body: EditingSuspension,
    actor: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    from backend.services.paper_edit_access import PaperEditAccess
    from backend.utils.auth import role_for_hf_subject

    if (
        body.hf_subject == actor["hf_subject"]
        or role_for_hf_subject(body.hf_subject) == "admin"
    ):
        raise HTTPException(
            status_code=400,
            detail="Administrator editing access cannot be suspended here",
        )
    return PaperEditAccess(db).suspend(
        body.hf_subject, body.suspended, actor["hf_subject"]
    )
