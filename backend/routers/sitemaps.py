"""XML sitemap and crawlable, user-facing paper archive routes."""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Iterable, Iterator, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.services.content_negotiation_service import (
    prefers_markdown,
    public_page_headers,
)
from backend.services.public_page_markdown_service import render_archive_markdown
from backend.services.sitemap_service import (
    PRODUCTION_ORIGIN,
    ArchiveLink,
    ArchivePage,
    SitemapService,
    SitemapShard,
)

router = APIRouter()
SITEMAP_HEADERS = {
    "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"
}
ARCHIVE_HEADERS = {"Cache-Control": "public, max-age=300, stale-while-revalidate=3600"}
_SHARD_RE = re.compile(r"^(?P<year>\d{4})-(?P<bucket>\d+)$")


def _xml_response(content: Iterable[str] | str) -> Response:
    # Render the whole document inside the request. Streaming it kept a pooled
    # database connection and a server-side cursor open for as long as a
    # crawler took to download the shard, and the request-scoped session could
    # close underneath the cursor ("named cursor isn't valid anymore"). A shard
    # of lightweight rows is a few megabytes of XML, so build it, release the
    # connection, then send.
    if not isinstance(content, str):
        content = "".join(content)
    return Response(
        content=content,
        media_type="application/xml",
        headers=SITEMAP_HEADERS,
    )


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
def sitemap_index(db: Session = Depends(get_database_session)) -> Response:
    service = SitemapService(db)
    entries = [f"<sitemap><loc>{PRODUCTION_ORIGIN}/sitemaps/static.xml</loc></sitemap>"]
    entries.extend(
        f"<sitemap><loc>{PRODUCTION_ORIGIN}/sitemaps/{kind}.xml</loc></sitemap>"
        for kind in (
            "tasks",
            "methods",
            "benchmarks",
            "conferences",
            "organizations",
        )
    )
    entries.extend(
        f"<sitemap><loc>{PRODUCTION_ORIGIN}/sitemaps/authors-{bucket}.xml</loc></sitemap>"
        for bucket in service.list_author_shards()
    )
    entries.extend(
        "<sitemap><loc>"
        f"{PRODUCTION_ORIGIN}/sitemaps/papers-{shard.name}.xml"
        "</loc></sitemap>"
        for shard in service.list_shards()
    )
    return _xml_response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(entries)
        + "</sitemapindex>"
    )


@router.api_route(
    "/sitemaps/static.xml", methods=["GET", "HEAD"], include_in_schema=False
)
def static_sitemap() -> Response:
    paths = ("/", "/papers/recent", "/papers/archive", "/astra-for-robotics")
    urls = "".join(f"<url><loc>{PRODUCTION_ORIGIN}{path}</loc></url>" for path in paths)
    return _xml_response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>"
    )


def _paper_sitemap_xml(service: SitemapService, shard: SitemapShard) -> Iterator[str]:
    yield (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    )
    for paper in service.iter_shard(shard):
        location = html.escape(
            f"{PRODUCTION_ORIGIN}/paper/{paper.route_identifier}", quote=True
        )
        yield (
            f"<url><loc>{location}</loc>"
            f"<lastmod>{paper.lastmod.isoformat()}</lastmod></url>"
        )
    yield "</urlset>"


def _entity_sitemap_xml(entities) -> Iterator[str]:
    yield (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    )
    for entity in entities:
        location = html.escape(f"{PRODUCTION_ORIGIN}{entity.path}", quote=True)
        yield (
            f"<url><loc>{location}</loc>"
            f"<lastmod>{entity.lastmod.isoformat()}</lastmod></url>"
        )
    yield "</urlset>"


@router.api_route(
    "/sitemaps/papers-{shard_name}.xml",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def paper_sitemap(
    shard_name: str,
    db: Session = Depends(get_database_session),
) -> Response:
    match = _SHARD_RE.fullmatch(shard_name)
    if not match:
        return Response(status_code=404)
    shard = SitemapShard(
        year=int(match.group("year")), bucket=int(match.group("bucket"))
    )
    return _xml_response(_paper_sitemap_xml(SitemapService(db), shard))


@router.api_route(
    "/sitemaps/{kind}.xml", methods=["GET", "HEAD"], include_in_schema=False
)
def entity_sitemap(kind: str, db: Session = Depends(get_database_session)) -> Response:
    author_match = re.fullmatch(r"authors-(\d+)", kind)
    if author_match:
        return _xml_response(
            _entity_sitemap_xml(
                SitemapService(db).iter_author_shard(int(author_match.group(1)))
            )
        )
    if kind not in {"tasks", "methods", "benchmarks", "conferences", "organizations"}:
        return Response(status_code=404)
    return _xml_response(_entity_sitemap_xml(SitemapService(db).iter_entities(kind)))


def _archive_html(document: ArchivePage) -> str:
    links = []
    if document.page > 1:
        previous = document.page - 1
        href = document.canonical_path + (f"?page={previous}" if previous > 1 else "")
        links.append(f'<a rel="prev" href="{href}">Newer papers</a>')
    if document.has_next:
        links.append(
            f'<a rel="next" href="{document.canonical_path}?page={document.page + 1}">'
            "Older papers</a>"
        )
    items = "".join(
        "<li>"
        f'<a href="/paper/{html.escape(paper.route_identifier, quote=True)}">'
        f"{html.escape(paper.title)}</a>"
        + (
            f' <time datetime="{paper.published.isoformat()}">'
            f"{paper.published.strftime('%-d %B %Y')}</time>"
            if paper.published
            else ""
        )
        + "</li>"
        for paper in document.papers
    )
    empty = (
        "<p>No eligible papers were published in this period.</p>"
        if not document.papers and document.canonical_path != "/papers/archive"
        else ""
    )
    navigation = ""
    if document.navigation:
        anchors = [
            f'<a href="{html.escape(item.href, quote=True)}">'
            f"{html.escape(item.label)}</a>{html.escape(item.suffix)}"
            for item in document.navigation
        ]
        if document.canonical_path == "/papers/archive":
            navigation = (
                "<main><ul>"
                + "".join(f"<li>{anchor}</li>" for anchor in anchors)
                + "</ul></main>"
            )
        elif re.fullmatch(r"/papers/archive/\d{4}", document.canonical_path):
            navigation = '<nav aria-label="Months">' + " ".join(anchors) + "</nav>"
        else:
            navigation = "<nav>" + " ".join(anchors) + "</nav>"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(document.title)}</title>"
        f'<meta name="description" content="{html.escape(document.description, quote=True)}">'
        f'<link rel="canonical" href="{html.escape(document.canonical_url, quote=True)}">'
        "<style>body{max-width:920px;margin:auto;padding:24px;font:16px/1.55 system-ui,sans-serif}"
        "li{margin:.65rem 0}time{color:#666;font-size:.9rem}nav{display:flex;gap:1rem;flex-wrap:wrap}"
        '</style></head><body><header><a href="/">Papers with Code</a>'
        f"<h1>{html.escape(document.heading)}</h1>"
        f"<p>{html.escape(document.description)}</p>"
        f"</header>{navigation}<main><ol>{items}</ol>{empty}</main>"
        f'<nav aria-label="Pagination">{" ".join(links)}</nav>'
        '<footer><p><a href="/papers/recent">Recent papers</a> · '
        '<a href="/papers/archive">Paper archive</a></p></footer></body></html>'
    )


def _archive_response(document: ArchivePage, request: Request) -> Response:
    headers = public_page_headers(
        document.canonical_url,
        cache_control=ARCHIVE_HEADERS["Cache-Control"],
    )
    if prefers_markdown(request.headers.get("accept")):
        return Response(
            render_archive_markdown(document),
            media_type="text/markdown",
            headers=headers,
        )
    return HTMLResponse(_archive_html(document), headers=headers)


def _page_number(page: int) -> Optional[Response]:
    if page < 1 or page > 10_000:
        return HTMLResponse("Not found", status_code=404)
    return None


@router.api_route("/papers/recent", methods=["GET", "HEAD"], include_in_schema=False)
def recent_papers(
    request: Request,
    page: int = Query(1),
    db: Session = Depends(get_database_session),
) -> Response:
    invalid = _page_number(page)
    if invalid:
        return invalid
    papers, has_next = SitemapService(db).archive_page(page=page, recent=True)
    return _archive_response(
        ArchivePage(
            title="Recent AI research papers | Papers with Code",
            description="Canonical AI research papers added or published in the last fourteen days.",
            heading="Recent AI research papers",
            canonical_path="/papers/recent",
            papers=tuple(papers),
            page=page,
            has_next=has_next,
        ),
        request,
    )


@router.api_route("/papers/archive", methods=["GET", "HEAD"], include_in_schema=False)
def paper_archive(
    request: Request, db: Session = Depends(get_database_session)
) -> Response:
    years = SitemapService(db).archive_years()
    return _archive_response(
        ArchivePage(
            title="AI research paper archive | Papers with Code",
            description="Browse canonical AI research papers by publication year.",
            heading="AI research paper archive",
            canonical_path="/papers/archive",
            navigation=tuple(
                ArchiveLink(
                    f"/papers/archive/{year}",
                    str(year),
                    f" ({count:,} papers)",
                )
                for year, count in years
            ),
        ),
        request,
    )


def _valid_period(year: int, month: Optional[int] = None) -> bool:
    current_year = date.today().year
    return 1990 <= year <= current_year + 1 and (month is None or 1 <= month <= 12)


@router.api_route(
    "/papers/archive/{year}", methods=["GET", "HEAD"], include_in_schema=False
)
def paper_archive_year(
    year: int,
    request: Request,
    page: int = Query(1),
    db: Session = Depends(get_database_session),
) -> Response:
    if not _valid_period(year):
        return HTMLResponse("Not found", status_code=404)
    invalid = _page_number(page)
    if invalid:
        return invalid
    service = SitemapService(db)
    papers, has_next = service.archive_page(page=page, year=year)
    return _archive_response(
        ArchivePage(
            title=f"AI research papers published in {year} | Papers with Code",
            description=f"Browse canonical AI research papers published in {year}.",
            heading=f"AI research papers published in {year}",
            canonical_path=f"/papers/archive/{year}",
            papers=tuple(papers),
            page=page,
            has_next=has_next,
            navigation=tuple(
                ArchiveLink(
                    f"/papers/archive/{year}/{month:02d}",
                    date(year, month, 1).strftime("%B"),
                )
                for month in range(1, 13)
            ),
        ),
        request,
    )


@router.api_route(
    "/papers/archive/{year}/{month}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def paper_archive_month(
    year: int,
    month: str,
    request: Request,
    page: int = Query(1),
    db: Session = Depends(get_database_session),
) -> Response:
    if not re.fullmatch(r"(0[1-9]|1[0-2])", month):
        return HTMLResponse("Not found", status_code=404)
    month_number = int(month)
    if not _valid_period(year, month_number):
        return HTMLResponse("Not found", status_code=404)
    invalid = _page_number(page)
    if invalid:
        return invalid
    papers, has_next = SitemapService(db).archive_page(
        page=page, year=year, month=month_number
    )
    month_name = date(year, month_number, 1).strftime("%B")
    return _archive_response(
        ArchivePage(
            title=f"AI research papers published in {month_name} {year} | Papers with Code",
            description=f"Browse canonical AI research papers published in {month_name} {year}.",
            heading=f"AI research papers published in {month_name} {year}",
            canonical_path=f"/papers/archive/{year}/{month}",
            papers=tuple(papers),
            page=page,
            has_next=has_next,
            navigation=(ArchiveLink(f"/papers/archive/{year}", f"All {year} papers"),),
        ),
        request,
    )
