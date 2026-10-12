"""Deterministic, bounded Markdown renderers for canonical public pages."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from backend.services.discovery_page_service import DiscoveryPage
from backend.services.discovery_text_service import markdown_plain_text
from backend.services.paper_seo_service import NamedLink, PaperSeoDocument
from backend.services.sitemap_service import PRODUCTION_ORIGIN, ArchivePage

_MARKDOWN_CONTROL_RE = re.compile(r"([\\`*_{}\[\]()#+.!>|~-])")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: object) -> str:
    parser = _TextExtractor()
    parser.feed(html.unescape(str(value or "")))
    parser.close()
    return " ".join(" ".join(parser.parts).split())


def _markdown_text(value: object) -> str:
    return _MARKDOWN_CONTROL_RE.sub(r"\\\1", _plain_text(value))


def _safe_url(value: str) -> str | None:
    if "\r" in value or "\n" in value:
        return None
    absolute = urljoin(f"{PRODUCTION_ORIGIN}/", value)
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    path = quote(parts.path, safe="/:@-._~!$&'*,;=")
    query = quote(parts.query, safe="=&:@/?-._~!$'*,;+")
    fragment = quote(parts.fragment, safe="-._~!$&'*,;=:@/?+")
    return urlunsplit((parts.scheme, parts.netloc, path, query, fragment))


def _link(label: object, destination: str) -> str | None:
    safe_destination = _safe_url(destination)
    if safe_destination is None:
        return None
    return f"[{_markdown_text(label)}]({safe_destination})"


def _frontmatter(
    *, title: object, description: object, canonical: str, document_type: str
) -> list[str]:
    fields = (
        ("title", _plain_text(title)),
        ("description", _plain_text(description)),
        ("canonical", canonical),
        ("type", document_type.lower()),
    )
    return [
        "---",
        *(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields),
        "---",
        "",
    ]


def _finish(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def _link_section(lines: list[str], heading: str, links: tuple[NamedLink, ...]) -> None:
    items = [
        rendered
        for item in links[:20]
        if (rendered := _link(item.name, item.url)) is not None
    ]
    if not items:
        return
    lines.extend(["", f"## {heading}", "", *(f"- {item}" for item in items)])


def render_discovery_markdown(page: DiscoveryPage) -> str:
    lines = _frontmatter(
        title=page.title,
        description=page.description,
        canonical=page.canonical_url,
        document_type=page.kind,
    )
    lines.extend(
        [
            f"# {_markdown_text(page.heading)}",
            "",
            _markdown_text(markdown_plain_text(page.body_markdown or page.description)),
        ]
    )
    if page.trends_markdown:
        lines.extend(["", "## Current research directions", ""])
        lines.extend(
            f"- {_markdown_text(markdown_plain_text(item))}"
            for item in page.trends_markdown
        )
    board = page.leaderboard
    if board is not None:
        metric = _markdown_text(board.metric)
        lines.extend(
            [
                "",
                f"## {_markdown_text(page.heading)} leaderboard",
                "",
                f"| Rank | Model | {metric} | Paper | Date |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in board.rows:
            paper = _markdown_text(row.paper_title or "")
            if row.paper_route_identifier:
                paper = (
                    _link(row.paper_title, f"/paper/{row.paper_route_identifier}")
                    or paper
                )
            cells = (
                str(row.rank) if row.rank is not None else "—",
                _markdown_text(row.model),
                _markdown_text(row.score) if row.score is not None else "—",
                paper,
                row.published.isoformat() if row.published else "",
            )
            lines.append(f"| {' | '.join(cells)} |")
    benchmarks = [
        rendered
        for item in page.benchmark_links
        if (rendered := _link(item.label, item.href)) is not None
    ]
    if benchmarks:
        lines.extend(["", "## Benchmarks", "", *(f"- {item}" for item in benchmarks)])
    related = [
        rendered
        for item in page.entity_links
        if (rendered := _link(item.label, item.href)) is not None
    ]
    if related:
        lines.extend(
            ["", "## Related research", "", *(f"- {item}" for item in related)]
        )
    if page.paper_links:
        lines.extend(["", "## Relevant papers", ""])
        for index, paper in enumerate(page.paper_links[:20], start=1):
            rendered = _link(paper.title, f"/paper/{paper.route_identifier}")
            if rendered is None:
                continue
            details = [_markdown_text(paper.context_label)]
            if paper.published:
                details.append(paper.published.isoformat())
            suffix = (
                f" — {' · '.join(value for value in details if value)}"
                if any(details)
                else ""
            )
            lines.append(f"{index}. {rendered}{suffix}")
    return _finish(lines)


def render_paper_markdown(document: PaperSeoDocument) -> str:
    lines = _frontmatter(
        title=document.search_title,
        description=document.description,
        canonical=document.canonical_url,
        document_type="paper",
    )
    lines.append(f"# {_markdown_text(document.title)}")
    facts: list[str] = []
    identifier = (
        f"arXiv:{document.arxiv_id}"
        if document.arxiv_id
        else f"External resource · {document.route_identifier}"
    )
    facts.append(_markdown_text(identifier))
    if document.published:
        facts.append(document.published.isoformat())
    if document.conference:
        facts.append(_markdown_text(document.conference))
    lines.extend(["", " · ".join(facts)])
    if document.authors:
        shown = ", ".join(_markdown_text(author) for author in document.authors[:20])
        if len(document.authors) > 20:
            shown += f" · … and {len(document.authors) - 20} more authors"
        lines.extend(["", f"Authors: {shown}"])
    if document.tldr:
        lines.extend(["", "## TL;DR", "", _markdown_text(document.tldr)])
    if document.abstract:
        lines.extend(["", "## Abstract", "", _markdown_text(document.abstract)])
    for heading, links in (
        ("Tasks", document.tasks),
        ("Methods", document.methods),
        ("Organizations", document.organizations),
        ("Introduced benchmarks", document.introduced_benchmarks),
        ("Introduced frameworks", document.introduced_frameworks),
        ("Code repositories", document.repositories),
        ("Project pages", document.project_pages),
        ("Hugging Face models", document.hf_models),
        ("Hugging Face datasets", document.hf_datasets),
        ("Hugging Face Spaces", document.hf_spaces),
    ):
        _link_section(lines, heading, links)
    sources: list[NamedLink] = []
    if document.source_url:
        sources.append(NamedLink("Source", document.source_url))
    if document.url_abs and document.url_abs != document.source_url:
        sources.append(NamedLink("Abstract page", document.url_abs))
    if document.url_pdf:
        sources.append(NamedLink("PDF", document.url_pdf))
    _link_section(lines, "Paper resources", tuple(sources))
    return _finish(lines)


def render_archive_markdown(document: ArchivePage) -> str:
    lines = _frontmatter(
        title=document.title,
        description=document.description,
        canonical=document.canonical_url,
        document_type="archive",
    )
    lines.extend(
        [
            f"# {_markdown_text(document.heading)}",
            "",
            _markdown_text(document.description),
        ]
    )
    if document.navigation:
        lines.extend(["", "## Browse archive", ""])
        for item in document.navigation:
            rendered = _link(item.label, item.href)
            if rendered is not None:
                lines.append(f"- {rendered}{_markdown_text(item.suffix)}")
    if document.papers:
        lines.extend(["", "## Papers", ""])
        for index, paper in enumerate(document.papers, start=1):
            rendered = _link(paper.title, f"/paper/{paper.route_identifier}")
            if rendered is None:
                continue
            date_suffix = f" — {paper.published.isoformat()}" if paper.published else ""
            lines.append(f"{index}. {rendered}{date_suffix}")
    if document.page > 1 or document.has_next:
        lines.extend(["", "## Pagination", ""])
        if document.page > 1:
            previous = document.page - 1
            href = document.canonical_path + (
                f"?page={previous}" if previous > 1 else ""
            )
            rendered = _link("Newer papers", href)
            if rendered:
                lines.append(f"- {rendered}")
        if document.has_next:
            rendered = _link(
                "Older papers", f"{document.canonical_path}?page={document.page + 1}"
            )
            if rendered:
                lines.append(f"- {rendered}")
    return _finish(lines)
