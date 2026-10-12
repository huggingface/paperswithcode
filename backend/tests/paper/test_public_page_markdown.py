from __future__ import annotations

from datetime import date

import pytest

from backend.services.content_negotiation_service import (
    merge_vary,
    prefers_markdown,
)
from backend.services.discovery_page_service import (
    DiscoveryLink,
    DiscoveryPage,
    DiscoveryPaperLink,
)
from backend.services.paper_seo_service import NamedLink, PaperSeoDocument
from backend.services.public_page_markdown_service import (
    render_archive_markdown,
    render_discovery_markdown,
    render_paper_markdown,
)
from backend.services.sitemap_service import ArchivePage, ArchivePaper


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        (None, False),
        ("*/*", False),
        ("text/html", False),
        ("text/markdown", True),
        ("text/markdown, text/html;q=0.9", True),
        ("text/html, text/markdown;q=0.5", False),
        ("text/markdown;q=0, text/html", False),
        ("application/json, text/markdown;q=0.8", True),
        ("text/markdown;q=0.8, text/html;q=0.8", True),
        ("text/html;q=0.8, text/markdown;q=0.8", False),
        ("text/*", False),
        ("text/*;q=0.5, text/markdown;q=0.8", True),
        ("garbage, text/markdown;q=oops, text/html", False),
        ("text/markdown/extra, text/html", False),
        ("*/markdown, text/html", False),
        ("text/markdown;q=2", False),
    ],
)
def test_prefers_markdown(accept, expected):
    assert prefers_markdown(accept) is expected


def test_merge_vary_is_case_insensitive_and_preserves_values():
    headers = {"vary": "Origin, Accept-Encoding"}
    merge_vary(headers, "Accept")
    merge_vary(headers, "accept")
    assert headers == {"vary": "Origin, Accept-Encoding, Accept"}


def _paper_document(**overrides) -> PaperSeoDocument:
    values = dict(
        route_identifier="2607.00001",
        title="A # title <script>",
        document_type=None,
        search_title='A "quoted": title\ncontinued',
        description='Description: "quoted"\ncontinued ☃',
        social_description="Description",
        abstract="<b>Abstract</b> with [brackets].",
        authors=tuple(f"Author {index}" for index in range(22)),
        author_links=(),
        published=date(2026, 7, 28),
        arxiv_id="2607.00001",
        source="arxiv",
        source_url="https://arxiv.org/abs/2607.00001",
        url_abs="https://arxiv.org/abs/2607.00001",
        url_pdf="https://arxiv.org/pdf/2607.00001.pdf",
        thumbnail=None,
        tldr="A concise <em>summary</em>.",
        conference="SafeConf",
        repositories=(NamedLink("repo [unsafe]", "https://example.com/a(b)"),),
        project_pages=(NamedLink("bad", "https://example.com/\n# injected"),),
        hf_models=(),
        hf_datasets=(),
        hf_spaces=(),
        tasks=(NamedLink("Task #1", "/tasks/task-one"),),
        methods=(),
        organizations=(),
        introduced_benchmarks=(),
        introduced_frameworks=(),
    )
    values.update(overrides)
    return PaperSeoDocument(**values)


def test_paper_markdown_is_safe_bounded_and_deterministic():
    first = render_paper_markdown(_paper_document())
    second = render_paper_markdown(_paper_document())
    assert first == second
    assert first.endswith("\n") and not first.endswith("\n\n")
    assert 'title: "A \\"quoted\\": title continued"' in first
    assert 'description: "Description: \\"quoted\\" continued ☃"' in first
    assert "<script" not in first and "<b>" not in first and "<em>" not in first
    assert "# A \\# title" in first
    assert "… and 2 more authors" in first
    assert "Author 20" not in first
    assert "https://example.com/a%28b%29" in first
    assert "# injected" not in first
    assert first.count("## Abstract") == 1


def test_discovery_markdown_uses_absolute_links_and_omits_empty_sections():
    page = DiscoveryPage(
        kind="Task",
        canonical_path="/tasks/a-safe-task",
        title="Safe: task",
        description="<p>Useful & concise.</p>",
        heading="Safe # task",
        breadcrumbs=(),
        entity_links=(DiscoveryLink("/benchmark/test", "Test [benchmark]"),),
        paper_links=(
            DiscoveryPaperLink(
                "2607.00001",
                "Paper *one*",
                date(2026, 7, 28),
                "Tagged with Safe",
            ),
        ),
    )
    markdown = render_discovery_markdown(page)
    assert "# Safe \\# task" in markdown
    assert "https://paperswithcode.co/benchmark/test" in markdown
    assert "https://paperswithcode.co/paper/2607.00001" in markdown
    assert "<p>" not in markdown


def test_archive_markdown_keeps_all_100_rows_and_pagination():
    document = ArchivePage(
        title="Archive",
        description="Archive description",
        heading="Archive heading",
        canonical_path="/papers/archive/2026",
        papers=tuple(
            ArchivePaper(f"paper-{index}", f"Paper {index}", date(2026, 1, 1))
            for index in range(100)
        ),
        page=2,
        has_next=True,
    )
    markdown = render_archive_markdown(document)
    assert markdown.count("https://paperswithcode.co/paper/paper\\-") == 0
    assert markdown.count("https://paperswithcode.co/paper/paper-") == 100
    assert "[Newer papers](https://paperswithcode.co/papers/archive/2026)" in markdown
    assert (
        "[Older papers](https://paperswithcode.co/papers/archive/2026?page=3)"
        in markdown
    )
