from __future__ import annotations

import json
import re
from datetime import date

import pytest

from backend.models.papers import (
    AuthorLink,
    MethodSummary,
    Paper,
    ProjectPage,
    Repository,
    TaskSummary,
)
from backend.services.paper_seo_service import (
    build_paper_seo_document,
    build_scholarly_json_ld,
    inject_initial_document,
    render_bibliographic_meta,
    render_initial_paper_document,
)


def _paper(**overrides) -> Paper:
    data = {
        "id": "42",
        "arxiv_id": "2607.24653",
        "source": "arxiv",
        "url_abs": "https://arxiv.org/abs/2607.24653",
        "url_pdf": "https://arxiv.org/pdf/2607.24653.pdf",
        "thumbnail_url": "/api/thumbnails/2607_24653_v1.jpg",
        "title": r"Kimi K3: Open Frontier Intelligence",
        "abstract": "A complete abstract with <markup> & evidence.",
        "authors": ["Kimi Team", "A. Researcher"],
        "author_links": [
            AuthorLink(id="7", name="Kimi Team"),
            AuthorLink(id="8", name="A. Researcher"),
        ],
        "published": date(2026, 7, 27),
        "tldr": "The technical report introduces Kimi K3.",
        "repositories": [
            Repository(
                id="1",
                url="https://github.com/moonshotai/kimi-k3",
                owner="moonshotai",
                name="kimi-k3",
                is_official=True,
            )
        ],
        "project_pages": [
            ProjectPage(
                id="1",
                url="https://www.kimi.com/blog/kimi-k3",
                is_official=True,
            )
        ],
        "hf_models": ["https://huggingface.co/moonshotai/Kimi-K3"],
        "tasks": [TaskSummary(id="1", name="Agents", slug="agents")],
        "methods": [
            MethodSummary(id="2", name="Mixture-of-Experts", slug="mixture-of-experts")
        ],
    }
    data.update(overrides)
    return Paper(**data)


def test_initial_document_keeps_bibliography_and_resources_in_hidden_source():
    document = build_paper_seo_document(_paper(), "2607.24653")
    rendered = render_initial_paper_document(document)

    assert '<main hidden class="initial-paper"' in rendered
    assert "<h1>Kimi K3: Open Frontier Intelligence</h1>" in rendered
    assert 'href="/authors/7">Kimi Team</a>' in rendered
    assert 'href="/authors/8">A. Researcher</a>' in rendered
    assert "arXiv:2607.24653" in rendered
    assert "Kimi K3 technical report · arXiv:2607.24653" in rendered
    assert "A complete abstract with &lt;markup&gt; &amp; evidence." in rendered
    assert 'href="https://github.com/moonshotai/kimi-k3"' in rendered
    assert 'href="https://huggingface.co/moonshotai/Kimi-K3"' in rendered
    assert 'href="/tasks/agents"' in rendered
    assert 'target="_blank" rel="noopener noreferrer"' in rendered


def test_hostile_values_are_escaped_in_html_and_json_ld():
    hostile = '</script><img src=x onerror="alert(1)">'
    document = build_paper_seo_document(
        _paper(title=hostile, abstract=hostile, authors=[hostile]), "2607.24653"
    )
    rendered = render_initial_paper_document(document)
    json_ld = build_scholarly_json_ld(document)

    assert hostile not in rendered
    assert "&lt;/script&gt;" in rendered
    assert "</script>" not in json_ld
    parsed = json.loads(json_ld)
    assert parsed["@graph"][0]["headline"] == hostile


def test_highwire_and_json_ld_are_factual_and_parseable():
    document = build_paper_seo_document(_paper(), "2607.24653")
    metadata = render_bibliographic_meta(document)

    assert metadata.count('name="citation_author"') == 2
    assert 'content="2026/07/27"' in metadata
    assert 'name="citation_arxiv_id" content="2607.24653"' in metadata
    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', metadata, re.DOTALL
    )
    assert match
    payload = json.loads(match.group(1))
    article = payload["@graph"][0]
    assert article["@type"] == "ScholarlyArticle"
    assert article["@id"] == "https://paperswithcode.co/paper/2607.24653#paper"
    assert article["codeRepository"] == ["https://github.com/moonshotai/kimi-k3"]


def test_search_description_prefers_tldr_and_title_has_arxiv_id():
    document = build_paper_seo_document(_paper(), "2607.24653")
    assert document.description == "The technical report introduces Kimi K3."
    assert (
        document.search_title
        == "Kimi K3 Technical Report (arXiv:2607.24653) | Papers with Code"
    )


def test_papers_with_results_get_a_benchmark_title():
    paper = _paper(
        id="124110",
        arxiv_id=None,
        source="external",
        title="Introducing Kimi K3.1 Pro: Advancing Open Intelligence",
        evaluated_benchmarks=[
            "GPQA Diamond",
            "Humanity's Last Exam (HLE)",
            "LIBERO",
            "LIBERO-Long",
            "MMMU-Pro",
            "BrowseComp",
        ],
    )
    document = build_paper_seo_document(paper, "124110")
    assert document.search_title == (
        "Kimi K3.1 Pro benchmarks: GPQA Diamond, Humanity's Last Exam, LIBERO"
        " | Papers with Code"
    )


def test_benchmark_title_keeps_curated_type_and_skips_long_names():
    with_type = build_paper_seo_document(
        _paper(evaluated_benchmarks=["GPQA Diamond"]), "2607.24653"
    )
    assert with_type.search_title.startswith("Kimi K3 Technical Report (arXiv:")

    long_name = build_paper_seo_document(
        _paper(
            arxiv_id="2610.22471",
            title="Has GPT-6-Astra Achieved Embodied Intelligence in the Real World?",
            evaluated_benchmarks=["RoboMME"],
        ),
        "2610.22471",
    )
    assert long_name.search_title.endswith("(arXiv:2610.22471) | Papers with Code")


def test_unknown_bibliographic_fields_are_omitted():
    document = build_paper_seo_document(
        _paper(arxiv_id=None, source="external", published=None, conference=None),
        "42",
    )
    metadata = render_bibliographic_meta(document)
    assert "citation_publication_date" not in metadata
    assert "citation_arxiv_id" not in metadata
    assert "citation_conference_title" not in metadata


def test_initial_document_injection_requires_empty_root():
    with pytest.raises(ValueError, match="empty #root"):
        inject_initial_document('<html><body><div id="app"></div></body></html>', "x")


def test_initial_document_injection_preserves_latex_backslashes():
    shell = '<html><body><div id="root"></div></body></html>'
    document_html = r"<p>$\pi_{0.5}$ and $\hat{x}$</p>"

    assert inject_initial_document(shell, document_html) == (
        f'<html><body><div id="root">{document_html}</div></body></html>'
    )
