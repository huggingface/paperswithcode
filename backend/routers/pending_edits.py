"""
Pending paper edit endpoints.

User submission (`require_user`, lives under ``/me``) and admin review
(`require_admin`, lives under ``/admin``). See
``backend.services.pending_edit_service`` for the underlying logic.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.database import PendingPaperEdit
from backend.services.pending_edit_service import (
    PendingEditAlreadyReviewedError,
    PendingEditError,
    PendingEditNotFoundError,
    PendingEditService,
)
from backend.utils.auth import require_admin, require_user
from backend.utils.exceptions import (
    DatabaseError,
    PaperNotFoundError,
)


EditType = Literal[
    "tasks",
    "methods",
    "evaluations",
    "repositories",
    "project_pages",
    "source_url",
    "hf_artifacts",
    "new_task",
    "new_method",
    "new_benchmark",
    "new_metric",
    "new_conference",
]
StatusLiteral = Literal["pending", "approved", "rejected"]


router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PendingEditSubmitRequest(BaseModel):
    paper_id: Optional[int] = Field(
        default=None,
        description=(
            "Database paper ID being edited. May be omitted only for "
            "directory-level taxonomy suggestions."
        ),
    )
    edit_type: EditType = Field(
        ..., description="Which paper-page surface the edit targets"
    )
    proposed_payload: Dict[str, Any] = Field(
        ...,
        description=(
            "Proposed change. Shape matches the equivalent admin mutation "
            'endpoint, e.g. {"task_ids": [1, 2]} for tasks, '
            '{"repositories": [{"url": ..., "is_official": ...}, ...]} for '
            'repositories, {"operations": [{"op": "create"|"update"|"delete", ...}]} '
            "for evaluations."
        ),
    )


class PendingEditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paper_id: Optional[int]
    hf_username: str
    is_author: bool
    edit_type: EditType
    proposed_payload: Dict[str, Any]
    current_payload: Optional[Dict[str, Any]] = None
    status: StatusLiteral
    admin_note: Optional[str] = None
    reviewed_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    reviewed_at: Optional[datetime] = None


class PendingEditListResponse(BaseModel):
    count: int
    results: List[PendingEditResponse]


class PendingEditReviewRequest(BaseModel):
    admin_note: Optional[str] = Field(
        default=None,
        description="Optional note recorded alongside the approval or rejection",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(row: PendingPaperEdit) -> PendingEditResponse:
    response = PendingEditResponse.model_validate(row)
    image = response.proposed_payload.get("image")
    if not isinstance(image, dict) or "data_url" not in image:
        return response

    safe_payload = dict(response.proposed_payload)
    safe_payload["image"] = {
        "file_name": image.get("file_name"),
        "mime_type": image.get("mime_type"),
        "url": f"/api/v1/admin/paper-edits/{row.id}/image",
    }
    return response.model_copy(update={"proposed_payload": safe_payload})


# ---------------------------------------------------------------------------
# User submission endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/me/paper-edits",
    response_model=PendingEditResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a paper-page edit or taxonomy suggestion for admin review",
    tags=["pending_edits"],
)
def submit_pending_paper_edit(
    request: PendingEditSubmitRequest,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> PendingEditResponse:
    service = PendingEditService(db)
    try:
        row = service.submit(
            paper_id=request.paper_id,
            hf_username=user["username"],
            edit_type=request.edit_type,
            proposed_payload=request.proposed_payload,
        )
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PendingEditError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return _to_response(row)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/admin/paper-edits",
    response_model=PendingEditListResponse,
    summary="List paper-page edit submissions",
    tags=["pending_edits"],
)
def list_pending_paper_edits(
    status_filter: Optional[StatusLiteral] = Query(
        default="pending",
        alias="status",
        description="Filter by row status (default: pending)",
    ),
    edit_type: Optional[EditType] = Query(default=None),
    paper_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
) -> PendingEditListResponse:
    service = PendingEditService(db)
    try:
        rows, total = service.list_edits(
            status=status_filter,
            edit_type=edit_type,
            paper_id=paper_id,
            limit=limit,
            offset=offset,
        )
    except PendingEditError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PendingEditListResponse(
        count=total, results=[_to_response(row) for row in rows]
    )


@router.get(
    "/admin/paper-edits/{edit_id}",
    response_model=PendingEditResponse,
    summary="Fetch a single paper-page edit submission",
    tags=["pending_edits"],
)
def get_pending_paper_edit(
    edit_id: int = Path(..., ge=1),
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
) -> PendingEditResponse:
    service = PendingEditService(db)
    try:
        row = service.get(edit_id)
    except PendingEditNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _to_response(row)


@router.get(
    "/admin/paper-edits/{edit_id}/image",
    summary="View an uploaded taxonomy-suggestion image",
    tags=["pending_edits"],
)
def get_pending_paper_edit_image(
    edit_id: int = Path(..., ge=1),
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
) -> Response:
    try:
        row = PendingEditService(db).get(edit_id)
    except PendingEditNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    image = row.proposed_payload.get("image")
    if not isinstance(image, dict):
        raise HTTPException(status_code=404, detail="Suggestion image not found")
    mime_type = image.get("mime_type")
    data_url = image.get("data_url")
    prefix = f"data:{mime_type};base64,"
    if not isinstance(data_url, str) or not data_url.startswith(prefix):
        raise HTTPException(status_code=404, detail="Suggestion image not found")
    return Response(
        content=base64.b64decode(data_url[len(prefix) :]),
        media_type=mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post(
    "/admin/paper-edits/{edit_id}/approve",
    response_model=PendingEditResponse,
    summary="Apply a pending paper-page edit",
    tags=["pending_edits"],
)
def approve_pending_paper_edit(
    edit_id: int = Path(..., ge=1),
    body: Optional[PendingEditReviewRequest] = None,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
) -> PendingEditResponse:
    service = PendingEditService(db)
    review = body or PendingEditReviewRequest()
    try:
        row = service.approve(
            edit_id=edit_id,
            reviewer_username=admin.get("username"),
            admin_note=review.admin_note,
        )
    except PendingEditNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PendingEditAlreadyReviewedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PendingEditError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return _to_response(row)


@router.post(
    "/admin/paper-edits/{edit_id}/reject",
    response_model=PendingEditResponse,
    summary="Reject a pending paper-page edit",
    tags=["pending_edits"],
)
def reject_pending_paper_edit(
    edit_id: int = Path(..., ge=1),
    body: Optional[PendingEditReviewRequest] = None,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_database_session),
) -> PendingEditResponse:
    service = PendingEditService(db)
    review = body or PendingEditReviewRequest()
    try:
        row = service.reject(
            edit_id=edit_id,
            reviewer_username=admin.get("username"),
            admin_note=review.admin_note,
        )
    except PendingEditNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PendingEditAlreadyReviewedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _to_response(row)
