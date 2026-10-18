"""Reader content: PDF layout for reader chat citations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import JSONResponse

from backend.config import Settings, get_settings
from backend.services.paper_layout_service import (
    PaperLayoutNotFoundError,
    read_paper_layout,
)

router = APIRouter()
_NO_STORE = {"Cache-Control": "no-store"}


def _error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail, headers=_NO_STORE)


@router.get("/papers/{route_id}/layout")
def get_paper_layout(
    route_id: str = Path(pattern=r"^(?:\d{4}\.\d{4,5}|[1-9]\d{0,18})$"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Return the PDF layout blocks that reader chat answers cite.

    Each ``pNbM`` anchor maps to its page, label, bbox on a 0-1000 page grid,
    enclosing section anchor and a short text preview.
    """
    if not settings.paper_reader_citations_enabled:
        raise _error(404, "Paper layout is not available")
    source = "external" if route_id.isdigit() else "arxiv"
    try:
        layout = read_paper_layout(
            route_id,
            source=source,
            bucket_id=settings.paper_layout_hf_bucket_id,
            token=settings.hf_token or None,
        )
    except PaperLayoutNotFoundError as error:
        raise _error(404, "Paper layout is not available") from error
    return JSONResponse(layout, headers={"Cache-Control": "public, max-age=300"})
