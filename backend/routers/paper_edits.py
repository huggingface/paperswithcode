"""Public paper edit documents and browser-approved CLI credentials."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.paper_edits import DeviceStart, DeviceExchange, PaperEditDocument
from backend.services.paper_edit_access import PaperEditAccess, token_hash
from backend.utils.client_ip import get_client_ip
from backend.services.paper_edit_authorization import PaperEditAuthorizationService
from backend.services.paper_edit_service import PaperEditService
from backend.utils.auth import can_directly_edit_catalog, require_paper_mutator

router = APIRouter()


def edits_available():
    if not can_directly_edit_catalog("contributor"):
        raise HTTPException(
            status_code=403, detail="Paper editing is unavailable in this environment"
        )


@router.post("/paper-edit-authorizations", dependencies=[Depends(edits_available)])
def start_authorization(
    body: DeviceStart,
    response: Response,
    request: Request,
    db: Session = Depends(get_database_session),
):
    response.headers["Cache-Control"] = "no-store"
    return PaperEditAuthorizationService(db).start(
        body.paper_id, token_hash(get_client_ip(request) or "unknown")
    )


@router.post(
    "/paper-edit-authorizations/token", dependencies=[Depends(edits_available)]
)
def exchange_authorization(
    body: DeviceExchange,
    response: Response,
    db: Session = Depends(get_database_session),
):
    response.headers["Cache-Control"] = "no-store"
    return PaperEditAuthorizationService(db).exchange(body.device_code)


@router.get(
    "/paper-edit-authorizations/{authorization_id}",
    dependencies=[Depends(edits_available)],
)
def authorization_details(
    authorization_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_database_session),
):
    response.headers["Cache-Control"] = "no-store"
    return PaperEditAuthorizationService(db).details(authorization_id)


@router.post(
    "/paper-edit-authorizations/{authorization_id}/approve",
    dependencies=[Depends(edits_available)],
)
def approve_authorization(
    authorization_id: uuid.UUID,
    actor: dict = Depends(require_paper_mutator),
    db: Session = Depends(get_database_session),
):
    return PaperEditAuthorizationService(db).approve(authorization_id, actor)


@router.post("/paper-edit-logout", status_code=204)
def revoke_authorization(
    actor: dict = Depends(require_paper_mutator),
    db: Session = Depends(get_database_session),
):
    if actor.get("source") != "paper_token":
        raise HTTPException(status_code=400, detail="Use a paper-scoped CLI credential")
    PaperEditAuthorizationService(db).revoke(actor)


@router.get("/papers/{paper_id}/edit-document")
def edit_document(
    paper_id: int,
    response: Response,
    actor: dict = Depends(require_paper_mutator),
    db: Session = Depends(get_database_session),
):
    response.headers["Cache-Control"] = "no-store"
    PaperEditAccess(db).check_write(
        actor, paper_id, "paper_edit_batch", "batch", {}, limits=False
    )
    return PaperEditService(db).export(paper_id)


@router.post("/papers/{paper_id}/edits/preview")
def preview_edits(
    paper_id: int,
    body: PaperEditDocument,
    request: Request,
    actor: dict = Depends(require_paper_mutator),
    db: Session = Depends(get_database_session),
):
    if body.paper_id != paper_id:
        raise HTTPException(
            status_code=400, detail="Document targets a different paper"
        )
    return PaperEditService(db).submit(body, actor, str(id(request)), preview=True)


@router.post("/papers/{paper_id}/edits")
def submit_edits(
    paper_id: int,
    body: PaperEditDocument,
    request: Request,
    actor: dict = Depends(require_paper_mutator),
    db: Session = Depends(get_database_session),
):
    if body.paper_id != paper_id:
        raise HTTPException(
            status_code=400, detail="Document targets a different paper"
        )
    return PaperEditService(db).submit(body, actor, str(id(request)))
