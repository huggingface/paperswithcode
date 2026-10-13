"""Safe semantic HTML rendering for discovery-page view models."""

from __future__ import annotations

import re
from html import escape

from backend.services.discovery_page_service import DiscoveryLeaderboard, DiscoveryPage
from backend.services.discovery_text_service import (
    markdown_html,
    markdown_inline_html,
)
from backend.services.spa_shell_service import (
    inject_root_document,
    replace_document_head,
)

# Site-wide social tags in the SPA shell that each discovery page replaces.
_SOCIAL_META_RE = re.compile(
    r'<meta\b[^>]*\b(?:property=["\']og:(?:title|description|url)["\']'
    r'|name=["\']twitter:(?:title|description)["\'])[^>]*>\s*',
    re.IGNORECASE,
)


def _link(href: str, label: str) -> str:
    return f'<a href="{escape(href, quote=True)}">{escape(label)}</a>'


def _leaderboard_section(page: DiscoveryPage, board: DiscoveryLeaderboard) -> str:
    direction = "lower" if board.lower_is_better else "higher"
    scope = f" for {escape(board.task_name)}" if board.task_name else ""
    shown = (
        f" Showing the top {len(board.rows)} of {board.total_rows} results."
        if len(board.rows) < board.total_rows
        else ""
    )
    rows = "".join(
        "<tr>"
        f"<td>{row.rank if row.rank is not None else '—'}</td>"
        f"<td>{escape(row.model)}</td>"
        f"<td>{escape(row.score) if row.score is not None else '—'}</td>"
        "<td>"
        + (
            _link(f"/paper/{row.paper_route_identifier}", row.paper_title or "")
            if row.paper_route_identifier
            else escape(row.paper_title or "")
        )
        + "</td>"
        f"<td>{row.published.isoformat() if row.published else ''}</td>"
        "</tr>"
        for row in board.rows
    )
    return (
        '<section aria-labelledby="leaderboard-heading">'
        f'<h2 id="leaderboard-heading">{escape(page.heading)} leaderboard</h2>'
        f"<p>Ranked by {escape(board.metric)} ({direction} is better){scope}."
        f"{shown}</p>"
        "<table><thead><tr>"
        '<th scope="col">Rank</th><th scope="col">Model</th>'
        f'<th scope="col">{escape(board.metric)}</th>'
        '<th scope="col">Paper</th><th scope="col">Date</th>'
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _top_models_section(page: DiscoveryPage) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{_link(top.benchmark.href, top.benchmark.label)}</td>"
        f"<td>{escape(top.model)}</td>"
        f"<td>{escape(top.open_model) if top.open_model else '—'}</td>"
        "</tr>"
        for top in page.top_models
    )
    as_of = (
        f" as of {page.top_models_as_of.strftime('%B %Y')}"
        if page.top_models_as_of
        else ""
    )
    return (
        '<section aria-labelledby="top-models-heading">'
        f'<h2 id="top-models-heading">Best {escape(page.heading)} models</h2>'
        f"<p>The top-ranked model on each of the most-evaluated "
        f"{escape(page.heading)} benchmarks{as_of}.</p>"
        "<table><thead><tr>"
        '<th scope="col">Benchmark</th><th scope="col">Best model</th>'
        '<th scope="col">Best open model</th>'
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )


def render_discovery_document(page: DiscoveryPage) -> str:
    breadcrumbs = "".join(_link(link.href, link.label) for link in page.breadcrumbs)
    entity_links = "".join(
        f"<li>{_link(link.href, link.label)}</li>" for link in page.entity_links
    )
    benchmark_links = "".join(
        f"<li>{_link(link.href, link.label)}</li>" for link in page.benchmark_links
    )
    trends = "".join(
        f"<li>{markdown_inline_html(item)}</li>" for item in page.trends_markdown
    )
    paper_links = "".join(
        "<li><article><h3>"
        f'<a href="/paper/{escape(paper.route_identifier, quote=True)}">'
        f"{escape(paper.title)}</a></h3><p>"
        f"{escape(paper.context_label)}"
        + (f" · {paper.published.isoformat()}" if paper.published else "")
        + "</p></article></li>"
        for paper in page.paper_links
    )
    empty = "<p>No eligible public papers are currently linked to this page.</p>"
    return (
        '<main hidden data-pwc-initial-document="discovery">'
        + (f'<nav aria-label="Breadcrumb">{breadcrumbs}</nav>' if breadcrumbs else "")
        + f"<header><p>{escape(page.kind)}</p><h1>{escape(page.heading)}</h1>"
        + markdown_html(page.body_markdown or page.description)
        + "</header>"
        + (_top_models_section(page) if page.top_models else "")
        + (
            '<section aria-labelledby="trends-heading">'
            '<h2 id="trends-heading">Current research directions</h2>'
            f"<ul>{trends}</ul></section>"
            if trends
            else ""
        )
        + (
            _leaderboard_section(page, page.leaderboard)
            if page.leaderboard is not None
            else ""
        )
        + (
            '<nav aria-labelledby="benchmarks-heading">'
            f'<h2 id="benchmarks-heading">{escape(page.heading)} benchmarks</h2>'
            f"<ul>{benchmark_links}</ul></nav>"
            if benchmark_links
            else ""
        )
        + (
            f'<nav aria-label="Related research topics"><ul>{entity_links}</ul></nav>'
            if entity_links
            else ""
        )
        + (
            ""
            if page.leaderboard is not None
            else '<section aria-labelledby="papers-heading">'
            '<h2 id="papers-heading">Relevant papers</h2>'
            + (f"<ol>{paper_links}</ol>" if paper_links else empty)
            + "</section>"
        )
        + "</main>"
    )


def render_discovery_shell(shell: str, page: DiscoveryPage) -> str:
    title = escape(page.title, quote=True)
    description = escape(page.description, quote=True)
    head = (
        f"<title>{escape(page.title)}</title>"
        f'<meta name="description" content="{description}">'
        f'<meta name="robots" content="{escape(page.robots, quote=True)}">'
        f'<link rel="canonical" href="{escape(page.canonical_url, quote=True)}">'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{description}">'
        f'<meta property="og:url" content="{escape(page.canonical_url, quote=True)}">'
        f'<meta name="twitter:title" content="{title}">'
        f'<meta name="twitter:description" content="{description}">'
    )
    return inject_root_document(
        replace_document_head(_SOCIAL_META_RE.sub("", shell), head),
        render_discovery_document(page),
    )
