from datetime import date
from types import SimpleNamespace

import pytest

from backend.models.chat import CitationSnapshot
from backend.chat_sandbox_worker.prompt import TEMPLATE
from backend.services import chat_citation_service
from backend.services.chat_stream_service import ChatTurnProjection
from backend.services.paper_service import PaperNotFoundError


def test_citation_snapshot_remains_compatible_with_legacy_rows():
    snapshot = CitationSnapshot.model_validate(
        {
            "position": 0,
            "route_id": "2501.00001",
            "title": "Legacy citation",
            "source_url": "https://arxiv.org/abs/2501.00001",
        }
    )

    assert snapshot.kind == "catalog_paper"
    assert snapshot.thumbnail_url is None
    assert snapshot.arxiv_id is None
    assert snapshot.citation_count is None


def test_external_paper_snapshot_requires_external_identity_and_metadata():
    snapshot = CitationSnapshot.model_validate(
        {
            "kind": "external_source",
            "position": 0,
            "route_id": None,
            "url": "https://arxiv.org/abs/2608.01234",
            "source_type": "paper",
            "provider": "semantic_scholar",
            "title": "External paper",
            "source_url": "https://www.semanticscholar.org/paper/s2-id",
            "arxiv_id": "2608.01234",
            "semantic_scholar_id": "s2-id",
            "authors": ["Ada Lovelace"],
        }
    )

    assert snapshot.kind == "external_source"
    assert snapshot.source_type == "paper"
    assert snapshot.provider == "semantic_scholar"
    assert snapshot.semantic_scholar_id == "s2-id"


def test_system_prompt_requires_machine_readable_s2_results_and_linked_titles():
    assert "use `--jsonl`" in TEMPLATE
    assert "Never leave a paper title as unlinked plain text" in TEMPLATE


def test_resolve_citations_includes_hover_preview_metadata(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="2501.00001",
        title="Previewable paper",
        source_url=None,
        url_abs="https://arxiv.org/abs/2501.00001",
        thumbnail_url="/api/thumbnails/2501_00001_v1.jpg",
        authors=["Ada Lovelace"],
        published=date(2025, 1, 2),
        conference_name="ICLR 2025",
        conference=None,
        citation_count=42,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            assert route_id == "2501.00001"
            return paper

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)

    citations = chat_citation_service.resolve_citations(
        object(), "[paper](paper:2501.00001)"
    )

    assert citations == [
        {
            "position": 0,
            "route_id": "2501.00001",
            "title": "Previewable paper",
            "source_url": "https://arxiv.org/abs/2501.00001",
            "thumbnail_url": "/api/thumbnails/2501_00001_v1.jpg",
            "arxiv_id": "2501.00001",
            "authors": ["Ada Lovelace"],
            "published": "2025-01-02",
            "conference": "ICLR 2025",
            "citation_count": 42,
        }
    ]


def test_resolution_tracks_requested_aliases_and_strips_unresolved_links(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="2501.00001",
        title="Previewable paper",
        source_url=None,
        url_abs="https://arxiv.org/abs/2501.00001",
        thumbnail_url=None,
        authors=[],
        published=None,
        conference_name=None,
        conference=None,
        citation_count=0,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            if route_id == "9":
                return paper
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    text = "[valid alias](paper:9) and [placeholder](paper:<cfg>)"

    citations, targets = chat_citation_service.resolve_citation_targets(object(), text)

    assert [item["route_id"] for item in citations] == ["2501.00001"]
    assert targets == {"9": "2501.00001"}
    assert chat_citation_service.normalize_paper_links(text, targets) == (
        "[valid alias](paper:2501.00001) and placeholder"
    )


def test_arxiv_urls_resolve_and_normalize_to_native_paper_links(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="2501.00001",
        title="Previewable paper",
        source_url=None,
        url_abs="https://arxiv.org/abs/2501.00001",
        thumbnail_url=None,
        authors=[],
        published=None,
        conference_name=None,
        conference=None,
        citation_count=0,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            if route_id == "2501.00001":
                return paper
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    text = (
        "[Paper](https://arxiv.org/abs/2501.00001) "
        "<https://arxiv.org/pdf/2501.00001v2.pdf> "
        "https://www.arxiv.org/html/2501.00001v3"
    )

    citations, targets = chat_citation_service.resolve_citation_targets(object(), text)

    assert [item["route_id"] for item in citations] == ["2501.00001"]
    assert targets == {"2501.00001": "2501.00001"}
    assert chat_citation_service.normalize_paper_links(text, targets) == (
        "[Paper](paper:2501.00001) "
        "[https://arxiv.org/pdf/2501.00001v2.pdf](paper:2501.00001) "
        "[https://www.arxiv.org/html/2501.00001v3](paper:2501.00001)"
    )


def test_unresolved_and_lookalike_arxiv_urls_remain_unchanged(monkeypatch):
    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    text = (
        "[Missing](https://arxiv.org/abs/2501.99999) and "
        "[lookalike](https://arxiv.org.example.com/abs/2501.00001)"
    )

    citations, targets = chat_citation_service.resolve_citation_targets(object(), text)

    assert citations == []
    assert targets == {}
    assert chat_citation_service.normalize_paper_links(text, targets) == text


def test_native_paper_link_with_arxiv_url_label_is_not_nested():
    text = "[https://arxiv.org/abs/2501.00001](paper:2501.00001)"

    assert (
        chat_citation_service.normalize_paper_links(text, {"2501.00001": "2501.00001"})
        == text
    )


def test_completed_answer_repairs_exact_s2_title_to_catalog_paper(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="1706.03762",
        title="Attention Is All You Need",
        source_url=None,
        url_abs="https://arxiv.org/abs/1706.03762",
        thumbnail_url="https://paperswithcode.co/thumbnails/1706.03762.png",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        published=None,
        conference_name="NeurIPS",
        conference=None,
        citation_count=100,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            if route_id == "1706.03762":
                return paper
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    projection = ChatTurnProjection()
    projection.apply(
        "tool_call",
        {
            "id": "s2-1",
            "name": "Bash",
            "args": {"command": "s2 search 'transformers' --limit 1 --jsonl"},
        },
    )
    projection.apply(
        "tool_result",
        {
            "id": "s2-1",
            "status": "success",
            "took_ms": 10,
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"paperId":"s2-id","externalIds":{"ArXiv":"1706.03762v7"},'
                        '"url":"https://www.semanticscholar.org/paper/s2-id",'
                        '"title":"Attention Is All You Need","year":2017,'
                        '"citationCount":100,"authors":[{"name":"Ashish Vaswani"}],'
                        '"abstract":"Introduces the Transformer."}'
                    ),
                    "truncated": False,
                }
            ],
            "metadata": {"exit_code": 0, "output_truncated": False},
        },
    )
    projection.apply(
        "answer_delta",
        {"text": "Start with Attention Is All You Need for the Transformer."},
    )

    answer, citations = projection.finalize(object())

    assert answer == (
        "Start with [Attention Is All You Need](paper:1706.03762) for the Transformer."
    )
    assert citations == [
        {
            "kind": "catalog_paper",
            "position": 0,
            "route_id": "1706.03762",
            "url": None,
            "source_type": None,
            "provider": "paperswithcode",
            "title": "Attention Is All You Need",
            "excerpt": None,
            "source_url": "https://arxiv.org/abs/1706.03762",
            "thumbnail_url": "https://paperswithcode.co/thumbnails/1706.03762.png",
            "favicon_url": None,
            "arxiv_id": "1706.03762",
            "semantic_scholar_id": "s2-id",
            "authors": ["Ashish Vaswani", "Noam Shazeer"],
            "published": None,
            "conference": "NeurIPS",
            "citation_count": 100,
        }
    ]


def test_completed_answer_repairs_missing_s2_paper_to_external_source(monkeypatch):
    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    projection = ChatTurnProjection()
    projection.apply(
        "tool_call",
        {
            "id": "s2-1",
            "name": "Bash",
            "args": {"command": "s2 search 'new paper' --jsonl"},
        },
    )
    projection.apply(
        "tool_result",
        {
            "id": "s2-1",
            "status": "success",
            "took_ms": 10,
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"paperId":"external-id","externalIds":{"ArXiv":"2608.01234"},'
                        '"url":"https://www.semanticscholar.org/paper/external-id",'
                        '"title":"A Brand New Paper","year":2026,"citationCount":3,'
                        '"authors":[{"name":"Ada Lovelace"}],'
                        '"abstract":"A concise external abstract."}'
                    ),
                    "truncated": False,
                }
            ],
            "metadata": {"exit_code": 0, "output_truncated": False},
        },
    )
    projection.apply("answer_delta", {"text": "Read A Brand New Paper next."})

    answer, citations = projection.finalize(object())

    assert answer == (
        "Read [A Brand New Paper](https://arxiv.org/abs/2608.01234) next."
    )
    assert citations == [
        {
            "kind": "external_source",
            "position": 0,
            "route_id": None,
            "url": "https://arxiv.org/abs/2608.01234",
            "source_type": "paper",
            "provider": "semantic_scholar",
            "title": "A Brand New Paper",
            "excerpt": "A concise external abstract.",
            "source_url": "https://www.semanticscholar.org/paper/external-id",
            "thumbnail_url": None,
            "favicon_url": None,
            "arxiv_id": "2608.01234",
            "semantic_scholar_id": "external-id",
            "authors": ["Ada Lovelace"],
            "published": "2026",
            "conference": None,
            "citation_count": 3,
        }
    ]
    assert projection.citation_metrics == {
        "paper_references": 1,
        "authored_correctly": 0,
        "repaired": 1,
        "unresolved": 0,
        "catalog_papers": 0,
        "external_papers": 1,
        "compliance_rate": 0.0,
    }


def test_exact_title_repair_skips_markdown_exclusion_zones(monkeypatch):
    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    projection = ChatTurnProjection(
        paper_candidates=[
            chat_citation_service.PaperCitationCandidate(
                title="A Brand New Paper",
                arxiv_id="2608.01234",
                semantic_scholar_id="external-id",
                semantic_scholar_url=(
                    "https://www.semanticscholar.org/paper/external-id"
                ),
            )
        ]
    )
    projection.apply(
        "answer_delta",
        {
            "text": (
                "# A Brand New Paper\n\n"
                "A Brand New Paper\n-----------------\n\n"
                "`A Brand New Paper` and "
                "[A Brand New Paper](https://example.com/existing).\n\n"
                "[A Brand New Paper][paper-ref]\n\n"
                "[A Brand New Paper]\n\n"
                "[A Brand New Paper]: https://example.com/reference\n\n"
                "~~~~md\n~~~\nA Brand New Paper\n~~~~\n\n"
                "```md\n```not-a-close\nA Brand New Paper\n```\n\n"
                "Read A Brand New Paper, then revisit A Brand New Paper."
            )
        },
    )

    answer, _citations = projection.finalize(object())

    assert answer == (
        "# A Brand New Paper\n\n"
        "A Brand New Paper\n-----------------\n\n"
        "`A Brand New Paper` and "
        "[A Brand New Paper](https://example.com/existing).\n\n"
        "[A Brand New Paper][paper-ref]\n\n"
        "[A Brand New Paper]\n\n"
        "[A Brand New Paper]: https://example.com/reference\n\n"
        "~~~~md\n~~~\nA Brand New Paper\n~~~~\n\n"
        "```md\n```not-a-close\nA Brand New Paper\n```\n\n"
        "Read [A Brand New Paper](https://arxiv.org/abs/2608.01234), "
        "then revisit A Brand New Paper."
    )


def test_s2_catalog_link_normalization_skips_inline_and_fenced_code(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="2501.00001",
        title="Catalogued S2 Paper",
        source_url=None,
        url_abs="https://arxiv.org/abs/2501.00001",
        thumbnail_url=None,
        authors=[],
        published=None,
        conference_name=None,
        conference=None,
        citation_count=0,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            assert route_id == "2501.00001"
            return paper

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    url = "https://www.semanticscholar.org/paper/catalogued-id"
    candidate = chat_citation_service.PaperCitationCandidate(
        title="Catalogued S2 Paper",
        arxiv_id="2501.00001",
        semantic_scholar_id="catalogued-id",
        semantic_scholar_url=url,
    )
    projection = ChatTurnProjection(paper_candidates=[candidate])
    projection.apply(
        "answer_delta",
        {
            "text": (
                f"`[Catalogued S2 Paper]({url})\ncontinued code span`\n\n"
                f"```md\n[Catalogued S2 Paper]({url})\n```\n\n"
                f"Read [Catalogued S2 Paper]({url})."
            )
        },
    )

    answer, _citations = projection.finalize(object())

    assert answer == (
        f"`[Catalogued S2 Paper]({url})\ncontinued code span`\n\n"
        f"```md\n[Catalogued S2 Paper]({url})\n```\n\n"
        "Read [Catalogued S2 Paper](paper:2501.00001)."
    )


def test_completed_answer_preserves_authored_s2_link_and_adds_preview(monkeypatch):
    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    candidate = chat_citation_service.PaperCitationCandidate(
        title="Journal Paper Without ArXiv",
        arxiv_id=None,
        semantic_scholar_id="journal-id",
        semantic_scholar_url="https://www.semanticscholar.org/paper/journal-id",
        authors=("Grace Hopper",),
        published="2024",
        excerpt="An external journal abstract.",
    )
    projection = ChatTurnProjection(paper_candidates=[candidate])
    projection.apply(
        "answer_delta",
        {
            "text": (
                "Read [Journal Paper Without ArXiv]"
                "(https://www.semanticscholar.org/paper/journal-id)."
            )
        },
    )

    answer, citations = projection.finalize(object())

    assert answer == (
        "Read [Journal Paper Without ArXiv]"
        "(https://www.semanticscholar.org/paper/journal-id)."
    )
    assert citations[0]["kind"] == "external_source"
    assert citations[0]["source_type"] == "paper"
    assert citations[0]["authors"] == ["Grace Hopper"]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.arxiv.org/abs/2608.01234v2",
        "https://arxiv.org/pdf/2608.01234v2.pdf",
        "https://arxiv.org/html/2608.01234v2?ref=chat#section",
    ],
)
def test_authored_arxiv_url_variants_keep_external_paper_preview(monkeypatch, url):
    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    candidate = chat_citation_service.PaperCitationCandidate(
        title="A Brand New Paper",
        arxiv_id="2608.01234",
        semantic_scholar_id="external-id",
        semantic_scholar_url="https://www.semanticscholar.org/paper/external-id",
        excerpt="A concise external abstract.",
    )
    projection = ChatTurnProjection(paper_candidates=[candidate])
    projection.apply("answer_delta", {"text": f"Read [A Brand New Paper]({url})."})

    answer, citations = projection.finalize(object())

    assert answer == f"Read [A Brand New Paper]({url})."
    assert citations[0]["kind"] == "external_source"
    assert citations[0]["source_type"] == "paper"
    assert citations[0]["url"] == url
    assert citations[0]["arxiv_id"] == "2608.01234"


def test_authored_s2_link_upgrades_to_catalog_paper_by_exact_arxiv(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="2501.00001",
        title="Catalogued S2 Paper",
        source_url=None,
        url_abs="https://arxiv.org/abs/2501.00001",
        thumbnail_url=None,
        authors=["Ada Lovelace"],
        published=None,
        conference_name=None,
        conference=None,
        citation_count=7,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            if route_id == "2501.00001":
                return paper
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    url = "https://www.semanticscholar.org/paper/catalogued-id"
    projection = ChatTurnProjection(
        paper_candidates=[
            chat_citation_service.PaperCitationCandidate(
                title="Catalogued S2 Paper",
                arxiv_id="2501.00001",
                semantic_scholar_id="catalogued-id",
                semantic_scholar_url=url,
            )
        ]
    )
    projection.apply("answer_delta", {"text": f"Read [Catalogued S2 Paper]({url})."})

    answer, citations = projection.finalize(object())

    assert answer == "Read [Catalogued S2 Paper](paper:2501.00001)."
    assert citations[0]["kind"] == "catalog_paper"
    assert citations[0]["semantic_scholar_id"] == "catalogued-id"


def test_completed_answer_repairs_titles_from_default_s2_tsv(monkeypatch):
    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    projection = ChatTurnProjection()
    projection.apply(
        "tool_call",
        {
            "id": "s2-tsv",
            "name": "Bash",
            "args": {"command": "s2 search 'compact output' --limit 1"},
        },
    )
    projection.apply(
        "tool_result",
        {
            "id": "s2-tsv",
            "status": "success",
            "took_ms": 10,
            "content": [
                {
                    "type": "text",
                    "text": (
                        "paperId\tyear\tcites\tarxiv\ttitle\n"
                        "tsv-id\t2025\t12\t2501.12345v2\tA TSV Paper\n"
                    ),
                    "truncated": False,
                }
            ],
            "metadata": {"exit_code": 0, "output_truncated": False},
        },
    )
    projection.apply("answer_delta", {"text": "Read A TSV Paper."})

    answer, citations = projection.finalize(object())

    assert answer == "Read [A TSV Paper](https://arxiv.org/abs/2501.12345)."
    assert citations[0]["semantic_scholar_id"] == "tsv-id"
    assert citations[0]["published"] == "2025"
    assert citations[0]["citation_count"] == 12


def test_completed_answer_repairs_exact_title_from_session_history(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="1706.03762",
        title="Attention Is All You Need",
        source_url=None,
        url_abs="https://arxiv.org/abs/1706.03762",
        thumbnail_url=None,
        authors=["Ashish Vaswani"],
        published=None,
        conference_name=None,
        conference=None,
        citation_count=100,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            if route_id == "1706.03762":
                return paper
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    projection = ChatTurnProjection()
    projection.apply(
        "answer_delta",
        {"text": "How does Attention Is All You Need handle recurrence?"},
    )

    answer, citations = projection.finalize(
        object(),
        prior_citations=[
            {
                "kind": "catalog_paper",
                "position": 0,
                "route_id": "1706.03762",
                "title": "Attention Is All You Need",
                "arxiv_id": "1706.03762",
                "authors": ["Ashish Vaswani"],
                "source_url": "https://arxiv.org/abs/1706.03762",
            }
        ],
    )

    assert answer == (
        "How does [Attention Is All You Need](paper:1706.03762) handle recurrence?"
    )
    assert citations[0]["kind"] == "catalog_paper"


def test_completed_answer_repairs_exact_title_from_pwc_search(monkeypatch):
    paper = SimpleNamespace(
        id="9",
        arxiv_id="2501.00001",
        title="Native Search Paper",
        source_url=None,
        url_abs="https://arxiv.org/abs/2501.00001",
        thumbnail_url=None,
        authors=["Ada Lovelace"],
        published=None,
        conference_name=None,
        conference=None,
        citation_count=7,
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def get_paper_by_id_or_arxiv(self, route_id):
            if route_id == "2501.00001":
                return paper
            raise PaperNotFoundError(route_id)

    monkeypatch.setattr(chat_citation_service, "PaperService", FakePaperService)
    projection = ChatTurnProjection()
    projection.apply(
        "tool_call",
        {"id": "pwc-1", "name": "search_papers", "args": {"query": "native"}},
    )
    projection.apply(
        "tool_result",
        {
            "id": "pwc-1",
            "hits": 1,
            "took_ms": 5,
            "results": [
                {
                    "route_id": "2501.00001",
                    "title": "Native Search Paper",
                    "metadata": {
                        "arxiv_id": "2501.00001",
                        "authors": [{"name": "Ada Lovelace"}],
                        "published": "2025-01-01",
                    },
                }
            ],
        },
    )
    projection.apply("answer_delta", {"text": "Read Native Search Paper."})

    answer, citations = projection.finalize(object())

    assert answer == "Read [Native Search Paper](paper:2501.00001)."
    assert citations[0]["kind"] == "catalog_paper"
