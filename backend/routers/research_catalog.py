"""Bounded read-only contracts consumed by the standalone ``pwc`` client."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.services.paper_lineage_service import get_paper_lineage
from backend.services.paper_markdown_service import read_paper_markdown_bounded
from backend.utils.auth import require_user

router = APIRouter(prefix="/research", tags=["research"])
_MARKDOWN_MAX_BYTES = 256 * 1024


@router.get("/papers/{paper_id}/read", response_class=PlainTextResponse)
def read_paper(
    paper_id: str = Path(min_length=1, max_length=64),
    user: dict = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    del user
    try:
        markdown, truncated = read_paper_markdown_bounded(
            paper_id,
            bucket_id=settings.paper_markdown_hf_bucket_id,
            token=settings.hf_token or None,
            max_bytes=_MARKDOWN_MAX_BYTES,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if truncated:
        markdown += "\n\n[document truncated; request a narrower catalog view]\n"
    return PlainTextResponse(
        markdown,
        headers={
            "Cache-Control": "private, no-store",
            "X-PWC-Truncated": "1" if truncated else "0",
        },
    )


@router.get("/papers/{paper_id}/lineage")
def paper_lineage(
    paper_id: str = Path(min_length=1, max_length=200),
    db: Session = Depends(get_database_session),
) -> dict:
    try:
        return get_paper_lineage(db, paper_id).to_dict()
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
