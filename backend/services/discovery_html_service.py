"""Safe semantic HTML rendering for discovery-page view models."""

from __future__ import annotations

from html import escape

from backend.services.discovery_page_service import DiscoveryPage
from backend.services.spa_shell_service import (
    inject_root_document,
    replace_document_head,
)


def render_discovery_document(page: DiscoveryPage) -> str:
    breadcrumbs = "".join(
        f'<a href="{escape(link.href, quote=True)}">{escape(link.label)}</a>'
        for link in page.breadcrumbs
    )
    entity_links = "".join(
        f'<li><a href="{escape(link.href, quote=True)}">{escape(link.label)}</a></li>'
        for link in page.entity_links
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
        f"<p>{escape(page.description)}</p></header>"
        + (
            f'<nav aria-label="Related research topics"><ul>{entity_links}</ul></nav>'
            if entity_links
            else ""
        )
        + '<section aria-labelledby="papers-heading">'
        '<h2 id="papers-heading">Relevant papers</h2>'
        + (f"<ol>{paper_links}</ol>" if paper_links else empty)
        + "</section></main>"
    )


def render_discovery_shell(shell: str, page: DiscoveryPage) -> str:
    head = (
        f"<title>{escape(page.title)}</title>"
        f'<meta name="description" content="{escape(page.description, quote=True)}">'
        f'<meta name="robots" content="{escape(page.robots, quote=True)}">'
        f'<link rel="canonical" href="{escape(page.canonical_url, quote=True)}">'
    )
    return inject_root_document(
        replace_document_head(shell, head), render_discovery_document(page)
    )
