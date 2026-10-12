from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.papers import Paper, PaperLookupResponse, PaperReferenceQuery
from backend.services.paper_reference_service import (
    PaperReferenceService,
    title_fingerprint,
)


def db_paper(id, title, arxiv_id=None, citation_count=0):
    return SimpleNamespace(
        id=id, title=title, arxiv_id=arxiv_id, citation_count=citation_count
    )


def api_paper(paper):
    return Paper(
        id=str(paper.id),
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        authors=[],
        source="arxiv" if paper.arxiv_id else "external",
    )


@pytest.mark.parametrize(
    ("title", "fingerprint"),
    [
        (
            "Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
            "mambalineartimesequencemodelingwithselectivestatespaces",
        ),
        (
            "Mamba: Linear-time sequence mod- eling with selective state spaces.",
            "mambalineartimesequencemodelingwithselectivestatespaces",
        ),
        ("Eﬃcient ﬁne-tuning", "efficientfinetuning"),
        ("  GPT-4   Technical Report ", "gpt4technicalreport"),
    ],
)
def test_title_fingerprint_ignores_pdf_text_noise(title, fingerprint):
    assert title_fingerprint(title) == fingerprint


class FakeCatalog(PaperReferenceService):
    def __init__(self, papers):
        super().__init__(db=None)
        self.papers = papers
        self.arxiv_queries = []
        self.title_queries = []

    def _latest_papers_by_arxiv_id(self, arxiv_ids):
        if arxiv_ids:
            self.arxiv_queries.append(arxiv_ids)
        return {p.arxiv_id: p for p in self.papers if p.arxiv_id in arxiv_ids}

    def _latest_papers_by_title_fingerprint(self, fingerprints):
        if fingerprints:
            self.title_queries.append(fingerprints)
        grouped = {}
        for paper in self.papers:
            fingerprint = title_fingerprint(paper.title)
            if fingerprint in fingerprints:
                grouped.setdefault(fingerprint, []).append(paper)
        return grouped

    def _hydrate(self, papers):
        return {int(p.id): api_paper(p) for p in papers}


def test_resolve_prefers_arxiv_ids_then_exact_title_fingerprints():
    mamba = db_paper(
        13,
        "Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
        "2312.00752",
    )
    lora = db_paper(
        15, "LoRA: Low-Rank Adaptation of Large Language Models", "2106.09685"
    )
    service = FakeCatalog([mamba, lora])

    response = service.resolve(
        [
            PaperReferenceQuery(
                key="cite.hu2022", arxiv_id="2106.09685v2", titles=["Anything"]
            ),
            PaperReferenceQuery(
                key="cite.gu2024",
                titles=[
                    "Albert Gu and Tri Dao",
                    "Mamba: Linear-time sequence mod- eling with selective state spaces",
                    "In Conference on Language Modeling (COLM), 2024",
                ],
            ),
            PaperReferenceQuery(
                key="cite.unknown",
                arxiv_id="not-an-id",
                titles=["Something else entirely"],
            ),
            PaperReferenceQuery(key="cite.short", titles=["GPT-4"]),
        ]
    )

    by_key = {entry.key: entry for entry in response.references}
    assert by_key["cite.hu2022"].matched_by == "arxiv_id"
    assert by_key["cite.hu2022"].paper.arxiv_id == "2106.09685"
    assert by_key["cite.gu2024"].matched_by == "title"
    assert by_key["cite.gu2024"].paper.id == "13"
    assert by_key["cite.unknown"].paper is None
    assert by_key["cite.short"].paper is None
    # One batched query per evidence kind, and no title lookup for entries
    # already matched by arXiv ID or with fingerprints below the length floor.
    assert service.arxiv_queries == [{"2106.09685"}]
    assert service.title_queries == [
        {
            "albertguandtridao",
            "mambalineartimesequencemodelingwithselectivestatespaces",
            "inconferenceonlanguagemodelingcolm2024",
            "somethingelseentirely",
        }
    ]


def test_resolve_prefers_the_longest_candidate_and_arxiv_duplicates():
    fragment = db_paper(1, "Selective State Spaces", "2401.00001")
    external = db_paper(
        2, "Mamba: Linear-Time Sequence Modeling with Selective State Spaces", None, 900
    )
    canonical = db_paper(
        3,
        "Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
        "2312.00752",
        10,
    )
    service = FakeCatalog([fragment, external, canonical])

    response = service.resolve(
        [
            PaperReferenceQuery(
                key="a",
                titles=[
                    "Selective state spaces",
                    "Mamba: linear-time sequence modeling with selective state spaces",
                ],
            ),
        ]
    )

    assert response.references[0].paper.id == "3"


def test_resolve_skips_queries_without_evidence():
    service = FakeCatalog([])
    response = service.resolve([PaperReferenceQuery(key="a")])
    assert response.references[0].paper is None
    assert service.arxiv_queries == []
    assert service.title_queries == []


@pytest.fixture
def client():
    app = create_app()

    def override_get_database_session():
        yield object()

    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_lookup_route_resolves_batches(client, monkeypatch):
    captured = {}

    def fake_resolve(self, references):
        captured["references"] = references
        return PaperLookupResponse(references=[])

    monkeypatch.setattr(PaperReferenceService, "resolve", fake_resolve)
    response = client.post(
        "/api/v1/papers/lookup",
        json={
            "references": [
                {"key": "cite.a", "arxiv_id": "2312.00752", "titles": ["x" * 400]}
            ],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"references": []}
    assert captured["references"][0].key == "cite.a"
    assert len(captured["references"][0].titles[0]) == 300


@pytest.mark.parametrize(
    "payload",
    [
        {"references": []},
        {"references": [{"key": "a"} for _ in range(501)]},
        {"references": [{"key": "a", "titles": ["t"] * 9}]},
        {"references": [{"key": "a", "unexpected": True}]},
    ],
)
def test_lookup_route_rejects_oversized_or_malformed_batches(client, payload):
    assert client.post("/api/v1/papers/lookup", json=payload).status_code == 422
