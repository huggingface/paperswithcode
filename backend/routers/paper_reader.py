"""Reader content for external papers that are web pages rather than PDFs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.models.database import Paper as DBPaper
from backend.services.external_page_markdown_service import (
    PAGE_MARKDOWN_MAX_BYTES,
    ExternalPageMarkdownError,
    external_page_url,
    prepare_external_page_markdown,
)
from backend.services.paper_markdown_service import (
    PaperMarkdownStorageError,
    read_paper_markdown_bounded,
)

router = APIRouter()
# Bounded so a reader's first open stays inside the browser's patience.
ON_DEMAND_SCRAPE_TIMEOUT_SECONDS = 30
_NO_STORE = {"Cache-Control": "no-store"}


def _error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail, headers=_NO_STORE)


def _read(paper_id: str, settings: Settings) -> str:
    markdown, _ = read_paper_markdown_bounded(
        paper_id,
        source="external",
        bucket_id=settings.paper_markdown_hf_bucket_id,
        token=settings.hf_token or None,
        max_bytes=PAGE_MARKDOWN_MAX_BYTES,
    )
    return markdown


@router.get("/papers/{paper_id}/web-markdown", response_class=PlainTextResponse)
def get_paper_web_markdown(
    paper_id: str = Path(pattern=r"^[1-9]\d{0,18}$"),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    """Return an HTML-only external paper's page as Markdown, preparing it once."""
    paper = db.get(DBPaper, int(paper_id))
    page_url = paper and external_page_url(
        source=paper.source,
        source_url=paper.source_url,
        conference_url_pdf=paper.conference_url_pdf,
    )
    if not paper or not page_url:
        raise _error(404, "This paper has no web page to read")
    try:
        markdown = _read(paper_id, settings)
    except PaperMarkdownStorageError as error:
        raise _error(503, "Paper content storage is temporarily unavailable") from error
    except ValueError:
        try:
            prepare_external_page_markdown(
                paper_id=paper_id,
                title=paper.title,
                page_url=page_url,
                api_key=settings.firecrawl_api_key,
                bucket_id=settings.paper_markdown_hf_bucket_id,
                token=settings.hf_token or None,
                timeout_seconds=ON_DEMAND_SCRAPE_TIMEOUT_SECONDS,
            )
        except ExternalPageMarkdownError as error:
            if error.retryable or error.code == "firecrawl_not_configured":
                raise _error(503, "Paper content is still being prepared") from error
            raise _error(422, f"This page could not be read: {error.code}") from error
        markdown = _read(paper_id, settings)
    return PlainTextResponse(markdown, headers={"Cache-Control": "public, max-age=300"})
