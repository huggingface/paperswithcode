"""Safe, crawlable HTML and scholarly metadata for public paper pages."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional
from urllib.parse import urlsplit

from backend.models.papers import Paper
from backend.utils.latex_text import latex_to_plain_text


PRODUCTION_ORIGIN = "https://paperswithcode.co"
SEARCH_DESCRIPTION_CHARS = 175
SOCIAL_DESCRIPTION_CHARS = 280
# Curated classification overrides are deliberately explicit and factual.
# Move these into a normalized paper field when document types become editable.
DOCUMENT_TYPE_OVERRIDES = {
    "2607.24653": "Technical Report",
}


@dataclass(frozen=True)
class NamedLink:
    name: str
    url: str


@dataclass(frozen=True)
class PaperSeoDocument:
    route_identifier: str
    title: str
    document_type: Optional[str]
    search_title: str
    description: str
    social_description: str
    abstract: str
    authors: tuple[str, ...]
    author_links: tuple[NamedLink, ...]
    published: Optional[date]
    arxiv_id: Optional[str]
    source: str
    source_url: Optional[str]
    url_abs: Optional[str]
    url_pdf: Optional[str]
    thumbnail: Optional[str]
    tldr: Optional[str]
    conference: Optional[str]
    repositories: tuple[NamedLink, ...]
    project_pages: tuple[NamedLink, ...]
    hf_models: tuple[NamedLink, ...]
    hf_datasets: tuple[NamedLink, ...]
    hf_spaces: tuple[NamedLink, ...]
    tasks: tuple[NamedLink, ...]
    methods: tuple[NamedLink, ...]
    organizations: tuple[NamedLink, ...]
    introduced_benchmarks: tuple[NamedLink, ...]
    introduced_frameworks: tuple[NamedLink, ...]

    @property
    def canonical_url(self) -> str:
        return f"{PRODUCTION_ORIGIN}/paper/{self.route_identifier}"


def _plain(value: Optional[str]) -> str:
    return " ".join((value or "").split())


def _truncate(value: str, limit: int) -> str:
    value = _plain(value)
    if len(value) <= limit:
        return value
    cut = value[: limit - 1].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:") + "…"


def _url_label(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.strip("/")
    return path or parts.netloc or url


def _artifact_links(urls: Iterable[str]) -> tuple[NamedLink, ...]:
    return tuple(NamedLink(_url_label(url), url) for url in urls if url)


def _description_source(paper: Paper) -> str:
    if _plain(paper.tldr):
        return _plain(paper.tldr)
    if _plain(paper.abstract):
        return _plain(paper.abstract)
    authors = [name for name in paper.authors if _plain(name)]
    if authors:
        suffix = f", published {paper.published.year}" if paper.published else ""
        return f"By {', '.join(authors[:5])}{suffix}."
    return "Trending AI research papers with code, datasets, methods, and evaluation leaderboards."


def _search_title(paper: Paper, title: str, document_type: Optional[str]) -> str:
    if paper.source == "arxiv" and paper.arxiv_id:
        if document_type:
            concise_title = title.split(":", 1)[0].strip()
            return (
                f"{concise_title} {document_type} "
                f"(arXiv:{paper.arxiv_id}) | Papers with Code"
            )
        return f"{title} (arXiv:{paper.arxiv_id}) | Papers with Code"
    return f"{title} | Papers with Code"


def build_paper_seo_document(paper: Paper, route_identifier: str) -> PaperSeoDocument:
    """Build the stable initial-document projection from the canonical API model."""
    title = latex_to_plain_text(_plain(paper.title)) or "Paper"
    document_type = DOCUMENT_TYPE_OVERRIDES.get(route_identifier)
    description_source = _description_source(paper)
    return PaperSeoDocument(
        route_identifier=route_identifier,
        title=title,
        document_type=document_type,
        search_title=_search_title(paper, title, document_type),
        description=_truncate(description_source, SEARCH_DESCRIPTION_CHARS),
        social_description=_truncate(description_source, SOCIAL_DESCRIPTION_CHARS),
        abstract=_plain(paper.abstract),
        authors=tuple(_plain(name) for name in paper.authors if _plain(name)),
        author_links=tuple(
            NamedLink(author.name, f"/authors/{author.id}")
            for author in (paper.author_links or [])
            if author.id and _plain(author.name)
        ),
        published=paper.published,
        arxiv_id=paper.arxiv_id,
        source=paper.source,
        source_url=paper.source_url,
        url_abs=paper.url_abs,
        url_pdf=paper.url_pdf,
        thumbnail=paper.thumbnail_url,
        tldr=_plain(paper.tldr) or None,
        conference=paper.conference_name or paper.conference,
        repositories=tuple(
            NamedLink(
                f"{repository.owner}/{repository.name}"
                if repository.owner and repository.name
                else _url_label(repository.url),
                repository.url,
            )
            for repository in (paper.repositories or [])
            if repository.url
        ),
        project_pages=tuple(
            NamedLink(_url_label(page.url), page.url)
            for page in (paper.project_pages or [])
            if page.url
        ),
        hf_models=_artifact_links(paper.hf_models),
        hf_datasets=_artifact_links(paper.hf_datasets),
        hf_spaces=_artifact_links(paper.hf_spaces),
        tasks=tuple(
            NamedLink(task.name, f"/tasks/{task.slug}")
            for task in (paper.tasks or [])
            if task.slug and task.name
        ),
        methods=tuple(
            NamedLink(method.name, f"/methods/{method.slug}")
            for method in (paper.methods or [])
            if method.slug and method.name
        ),
        organizations=tuple(
            NamedLink(organization.name, f"/orgs/{organization.slug}")
            for organization in (paper.organizations or [])
            if organization.slug and organization.name
        ),
        introduced_benchmarks=tuple(
            NamedLink(benchmark.name, f"/benchmark/{benchmark.slug}")
            for benchmark in (paper.introduced_benchmarks or [])
            if benchmark.slug and benchmark.name
        ),
        introduced_frameworks=tuple(
            NamedLink(framework.name, f"/frameworks#framework-{framework.slug}")
            for framework in (paper.introduced_frameworks or [])
            if framework.slug and framework.name
        ),
    )


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _external_attrs(url: str) -> str:
    return (
        ' target="_blank" rel="noopener noreferrer"'
        if url.startswith(("http://", "https://"))
        else ""
    )


def _link(link: NamedLink) -> str:
    return (
        f'<a href="{_escape(link.url)}"{_external_attrs(link.url)}>'
        f"{_escape(link.name)}</a>"
    )


def _link_group(label: str, links: tuple[NamedLink, ...]) -> str:
    if not links:
        return ""
    return (
        f'<div class="initial-paper-links"><h3>{_escape(label)}</h3><ul>'
        + "".join(f"<li>{_link(link)}</li>" for link in links)
        + "</ul></div>"
    )


def render_initial_paper_document(document: PaperSeoDocument) -> str:
    """Render database-derived values only through escaped text/attributes."""
    year = document.published.year if document.published else None
    date_label = (
        document.published.strftime("%-d %B %Y")
        if document.published
        else "Publication date unavailable"
    )
    identifier = (
        f"arXiv:{document.arxiv_id}"
        if document.arxiv_id
        else f"External resource · {document.route_identifier}"
    )
    lead_type = (
        f"{document.title.split(':', 1)[0]} {document.document_type.lower()}"
        if document.document_type
        else "Paper"
    )
    author_text = ", ".join(document.authors)
    author_urls = {link.name: link.url for link in document.author_links}

    def linked_authors(names: tuple[str, ...]) -> str:
        return ", ".join(
            _link(NamedLink(name, author_urls[name]))
            if name in author_urls
            else _escape(name)
            for name in names
        )

    if len(document.authors) > 20:
        author_markup = (
            '<details class="initial-paper-authors"><summary>'
            f"{linked_authors(document.authors[:5])} and "
            f"{len(document.authors) - 5} more authors</summary>"
            f'<p class="citation_author">{linked_authors(document.authors)}</p></details>'
        )
    elif author_text:
        author_markup = (
            f'<p class="citation_author">{linked_authors(document.authors)}</p>'
        )
    else:
        author_markup = ""
    resource_links: list[NamedLink] = []
    if document.url_abs:
        resource_links.append(
            NamedLink(
                "ArXiv abstract" if document.arxiv_id else "Official source",
                document.url_abs,
            )
        )
    if document.url_pdf:
        resource_links.append(NamedLink("PDF", document.url_pdf))
    resources = tuple(resource_links)

    breadcrumb_year = (
        f'<a href="/papers/archive/{year}">{year}</a>' if year else "Archive"
    )
    optional_summary = (
        '<section aria-labelledby="tldr-heading"><h2 id="tldr-heading">TL;DR</h2>'
        f"<p>{_escape(document.tldr)}</p></section>"
        if document.tldr
        else ""
    )
    abstract = (
        '<section aria-labelledby="abstract-heading">'
        '<h2 id="abstract-heading">Abstract</h2>'
        f"<p>{_escape(document.abstract)}</p></section>"
        if document.abstract
        else ""
    )
    taxonomy = "".join(
        (
            _link_group("Tasks", document.tasks),
            _link_group("Methods", document.methods),
            _link_group("Organizations", document.organizations),
            _link_group("Introduced benchmarks", document.introduced_benchmarks),
            _link_group("Introduced frameworks", document.introduced_frameworks),
        )
    )
    artifacts = "".join(
        (
            _link_group("Code", document.repositories),
            _link_group("Project pages", document.project_pages),
            _link_group("Hugging Face models", document.hf_models),
            _link_group("Hugging Face datasets", document.hf_datasets),
            _link_group("Hugging Face Spaces", document.hf_spaces),
        )
    )

    return (
        '<main class="initial-paper" data-pwc-initial-document="paper">'
        '<nav class="initial-paper-breadcrumb" aria-label="Breadcrumb">'
        f'<a href="/papers/recent">Papers</a><span aria-hidden="true">›</span>'
        f'{breadcrumb_year}<span aria-hidden="true">›</span>'
        f"<span>{_escape(document.title)}</span></nav>"
        "<article><header>"
        f'<p class="initial-paper-kicker">{_escape(lead_type)} · '
        f"{_escape(identifier)} · {_escape(date_label)}</p>"
        f"<h1>{_escape(document.title)}</h1>"
        + author_markup
        + "</header>"
        + optional_summary
        + abstract
        + (
            '<nav aria-label="Paper resources"><h2>Paper resources</h2><ul>'
            + "".join(f"<li>{_link(link)}</li>" for link in resources)
            + "</ul></nav>"
            if resources
            else ""
        )
        + (
            f'<section aria-label="Code and artifacts">{artifacts}</section>'
            if artifacts
            else ""
        )
        + (
            f'<section aria-label="Tasks and methods">{taxonomy}</section>'
            if taxonomy
            else ""
        )
        + "</article></main>"
    )


def _json_for_script(data: object) -> str:
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_scholarly_json_ld(document: PaperSeoDocument) -> str:
    article: dict[str, object] = {
        "@type": "ScholarlyArticle",
        "@id": f"{document.canonical_url}#paper",
        "url": document.canonical_url,
        "headline": document.title,
        "author": [{"@type": "Person", "name": name} for name in document.authors],
        "isPartOf": {
            "@type": "WebSite",
            "name": "Papers with Code",
            "url": f"{PRODUCTION_ORIGIN}/",
        },
    }
    if document.abstract:
        article["abstract"] = document.abstract
    if document.published:
        article["datePublished"] = document.published.isoformat()
    if document.arxiv_id:
        article["identifier"] = [
            {
                "@type": "PropertyValue",
                "propertyID": "arXiv",
                "value": document.arxiv_id,
            }
        ]
    if document.url_abs:
        article["sameAs"] = [document.url_abs]
    if document.thumbnail:
        article["image"] = (
            document.thumbnail
            if document.thumbnail.startswith(("http://", "https://"))
            else PRODUCTION_ORIGIN + "/" + document.thumbnail.lstrip("/")
        )
    if document.repositories:
        article["codeRepository"] = [link.url for link in document.repositories]
    about = [
        {"@type": "Thing", "name": link.name}
        for link in (*document.tasks, *document.methods)
    ]
    if about:
        article["about"] = about

    year = document.published.year if document.published else None
    items: list[dict[str, object]] = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "Papers",
            "item": f"{PRODUCTION_ORIGIN}/papers/recent",
        }
    ]
    if year:
        items.append(
            {
                "@type": "ListItem",
                "position": 2,
                "name": str(year),
                "item": f"{PRODUCTION_ORIGIN}/papers/archive/{year}",
            }
        )
    items.append(
        {
            "@type": "ListItem",
            "position": len(items) + 1,
            "name": document.title,
            "item": document.canonical_url,
        }
    )
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            article,
            {"@type": "BreadcrumbList", "itemListElement": items},
        ],
    }
    return _json_for_script(payload)


def render_bibliographic_meta(document: PaperSeoDocument) -> str:
    lines = [f'<meta name="citation_title" content="{_escape(document.title)}" />']
    lines.extend(
        f'<meta name="citation_author" content="{_escape(author)}" />'
        for author in document.authors
    )
    if document.published:
        lines.append(
            '<meta name="citation_publication_date" '
            f'content="{document.published.strftime("%Y/%m/%d")}" />'
        )
    if document.arxiv_id:
        lines.append(
            f'<meta name="citation_arxiv_id" content="{_escape(document.arxiv_id)}" />'
        )
    if document.conference:
        lines.append(
            f'<meta name="citation_conference_title" content="{_escape(document.conference)}" />'
        )
    lines.append(
        '<script type="application/ld+json">'
        f"{build_scholarly_json_ld(document)}</script>"
    )
    return "\n".join(lines)


_ROOT_RE = re.compile(r'<div\s+id=["\']root["\']\s*>\s*</div>', re.IGNORECASE)


def inject_initial_document(shell_html: str, document_html: str) -> str:
    replacement = f'<div id="root">{document_html}</div>'
    rewritten, count = _ROOT_RE.subn(lambda _match: replacement, shell_html, count=1)
    if count != 1:
        raise ValueError("SPA shell must contain exactly one empty #root placeholder")
    return rewritten
