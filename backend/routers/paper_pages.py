"""
Server-rendered paper-page HTML with crawlable content and scholarly metadata.

Paper detail pages are otherwise a pure React SPA, which means crawlers
that don't execute JavaScript (Twitterbot, Slackbot, Discord, etc.) see
the same generic Open Graph card on every URL. The routes in this module
sit in front of the SPA: they return the same Vite-built ``index.html``
but with paper-specific ``<title>``, ``description``, ``og:*`` and
``twitter:*`` tags injected, including an absolute image URL that points
at the paper's existing thumbnail when it is already on disk.

Nginx is responsible for forwarding ``/paper/{id}`` and the legacy
``/papers/{id}`` shape to the backend; all other static fall-through is
unchanged. arXiv-shaped ``/abs/{id}`` and ``/pdf/{id}.pdf`` URLs redirect to
the paper page and the PDF reader, so swapping ``arxiv.org`` for our host works.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi import Path as FastApiPath
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.services.content_negotiation_service import (
    prefers_markdown,
    public_page_headers,
)
from backend.services.default_og_image import get_default_og_image_bytes
from backend.services.paper_seo_service import (
    PRODUCTION_ORIGIN,
    build_paper_seo_document,
    inject_initial_document,
    render_initial_paper_document,
)
from backend.services.paper_service import PaperService
from backend.services.public_page_markdown_service import render_paper_markdown
from backend.services.social_meta_service import (
    build_paper_meta,
    inject_paper_meta,
)
from backend.services.spa_shell_service import (
    load_index_html,
    replace_document_head,
)
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.urls import (
    get_paper_route_identifier,
    normalize_paper_route_identifier,
    validate_arxiv_id,
)

logger = logging.getLogger(__name__)


router = APIRouter()


def _render_missing_paper() -> HTMLResponse:
    return HTMLResponse(
        content=(
            '<!doctype html><html lang="en"><head>'
            '<meta charset="utf-8"><meta name="robots" content="noindex">'
            "<title>Paper not found | Papers with Code</title></head>"
            "<body><main><h1>Paper not found</h1>"
            "<p>The requested paper is not available.</p>"
            '<p><a href="/papers/recent">Browse recent papers</a></p>'
            "</main></body></html>"
        ),
        status_code=404,
        headers={"Cache-Control": "no-store"},
    )


def _render_unindexed_arxiv_paper() -> HTMLResponse:
    index_html = load_index_html()
    if index_html is None:
        return _render_missing_paper()

    try:
        rendered = replace_document_head(
            index_html,
            (
                "    <title>Paper not indexed yet | Papers with Code</title>\n"
                '    <meta name="description" content="This arXiv paper has not '
                'been indexed by Papers with Code yet.">\n'
                '    <meta name="robots" content="noindex">'
            ),
        )
    except ValueError as exc:
        logger.error("Paper shell contract failed for unindexed paper: %s", exc)
        return _render_missing_paper()

    return HTMLResponse(
        content=rendered,
        status_code=404,
        headers={"Cache-Control": "no-store"},
    )


def _render_paper_html(
    paper_id: str,
    db: Session,
    is_legacy_path: bool,
    request: Request,
) -> Response:
    try:
        paper = PaperService(db).get_paper_by_id_or_arxiv(
            paper_id, include_resources=True
        )
    except PaperNotFoundError:
        normalized_id = normalize_paper_route_identifier(paper_id)
        if validate_arxiv_id(normalized_id):
            return _render_unindexed_arxiv_paper()
        return _render_missing_paper()
    except DatabaseError as exc:
        logger.warning("Database error rendering /paper/%s: %s", paper_id, exc)
        return HTMLResponse(
            content=(
                '<!doctype html><html lang="en"><head>'
                '<meta charset="utf-8"><meta name="robots" content="noindex">'
                "<title>Paper temporarily unavailable | Papers with Code</title>"
                "</head><body><main><h1>Paper temporarily unavailable</h1>"
                "<p>Please try again shortly.</p></main></body></html>"
            ),
            status_code=503,
            headers={"Cache-Control": "no-store", "Retry-After": "60"},
        )

    route_identifier = get_paper_route_identifier(
        paper.source, paper.arxiv_id, int(paper.id)
    )
    canonical_path = f"/paper/{route_identifier}"
    if is_legacy_path or paper_id != route_identifier:
        return RedirectResponse(
            url=canonical_path,
            status_code=301,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    document = build_paper_seo_document(paper, route_identifier)
    headers = public_page_headers(document.canonical_url)
    if prefers_markdown(request.headers.get("accept")):
        return Response(
            render_paper_markdown(document),
            media_type="text/markdown",
            headers=headers,
        )

    index_html = load_index_html()
    if index_html is None:
        return HTMLResponse(
            "<!doctype html><title>Papers with Code</title>"
            "<p>Frontend bundle is not available.</p>",
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    meta = build_paper_meta(
        paper, route_identifier=route_identifier, origin=PRODUCTION_ORIGIN
    )
    try:
        rendered = inject_paper_meta(index_html, meta, document)
        rendered = inject_initial_document(
            rendered, render_initial_paper_document(document)
        )
    except ValueError as exc:
        logger.error("Paper shell contract failed: %s", exc)
        return HTMLResponse(
            "<!doctype html><title>Papers with Code</title>"
            "<p>Frontend bundle is not available.</p>",
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    return HTMLResponse(content=rendered, status_code=200, headers=headers)


@router.api_route(
    "/paper/{paper_id}",
    methods=["GET", "HEAD"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
def get_paper_page(
    request: Request,
    paper_id: str = FastApiPath(..., description="ArXiv ID or internal paper ID"),
    db: Session = Depends(get_database_session),
) -> Response:
    """Serve the SPA shell with paper-specific social meta tags."""
    return _render_paper_html(paper_id, db, is_legacy_path=False, request=request)


@router.api_route(
    "/papers/{paper_id}",
    methods=["GET", "HEAD"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
def get_paper_page_legacy(
    request: Request,
    paper_id: str = FastApiPath(..., description="ArXiv ID or internal paper ID"),
    db: Session = Depends(get_database_session),
) -> Response:
    """
    Redirect the legacy plural shape directly to the resolved canonical route.
    """
    return _render_paper_html(paper_id, db, is_legacy_path=True, request=request)


def _arxiv_alias_redirect(path: str) -> RedirectResponse:
    return RedirectResponse(
        url=path,
        status_code=301,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.api_route(
    "/abs/{arxiv_id}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def redirect_arxiv_abstract(arxiv_id: str) -> RedirectResponse:
    """Swap ``arxiv.org`` for our host in an abstract URL to reach the paper page."""
    paper_id = normalize_paper_route_identifier(arxiv_id)
    return _arxiv_alias_redirect(f"/paper/{quote(paper_id, safe='')}")


@router.api_route(
    "/pdf/{arxiv_id}.pdf",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def redirect_arxiv_pdf(arxiv_id: str) -> RedirectResponse:
    """Swap ``arxiv.org`` for our host in a ``.pdf`` URL to reach the reader."""
    paper_id = normalize_paper_route_identifier(arxiv_id)
    return _arxiv_alias_redirect(f"/pdf/{quote(paper_id, safe='')}")


@router.get(
    "/api/og/default.png",
    include_in_schema=False,
)
def get_default_og_image() -> Response:
    """
    Serve the static fallback Open Graph image used when a paper has no
    thumbnail on disk yet.

    The bytes are generated once at first request and cached in process
    memory, so crawler fetches stay cheap.
    """
    return Response(
        content=get_default_og_image_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
