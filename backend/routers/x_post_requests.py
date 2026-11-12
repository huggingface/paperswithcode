"""Admin "Tweet it" button: ask the X agent to post about a paper next."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.services.x_post_requests import (
    AlreadyPostedError,
    PaperNotFoundError,
    RequestStatus,
    request_post,
    request_status,
    resolve_request,
)
from backend.utils.auth import require_admin, require_hf_admin

router = APIRouter(prefix="/admin/papers/{paper_id}/x-post-request", tags=["admin"])


class XPostRequestStatus(BaseModel):
    state: Literal["none", "requested", "posted"]
    position: Optional[int] = None
    requested_at: Optional[datetime] = None
    post_url: Optional[str] = None


def _response(result: RequestStatus) -> XPostRequestStatus:
    return XPostRequestStatus(**result.__dict__)


@router.get("", response_model=XPostRequestStatus)
def get_request(
    paper_id: int,
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
):
    return _response(request_status(db, paper_id))


@router.post("", response_model=XPostRequestStatus)
def create_request(
    paper_id: int,
    admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
):
    try:
        result = request_post(db, paper_id, requested_by=admin.get("username"))
    except PaperNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except AlreadyPostedError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return _response(result)


@router.delete("", response_model=XPostRequestStatus)
def cancel_request(
    paper_id: int,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
):
    resolve_request(db, paper_id, "cancelled")
    return _response(request_status(db, paper_id))
