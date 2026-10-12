from datetime import date
from typing import Optional

import httpx
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.methods_setup.link_papers_by_source_citations import (
    CitingPaper,
    SemanticScholarClient,
    link_papers_by_source_citations,
    normalize_arxiv_id,
)
from backend.models.database import (
    Base,
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
)


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


def _build_in_memory_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _record: connection.create_function(
            "jsonb_typeof", 1, lambda _value: "array"
        ),
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def _seed_corpus(db: Session) -> None:
    db.add_all(
        [
            DBPaper(
                id=1,
                title="Attention Is All You Need",
                abstract="Source paper.",
                arxiv_id="1706.03762",
                version="v5",
                is_latest_version=True,
                date_published=date(2017, 6, 12),
                semantic_scholar_id="ss-source",
            ),
            DBPaper(
                id=2,
                title="BERT",
                abstract="Cites Transformer via SS id.",
                arxiv_id="1810.04805",
                version="v2",
                is_latest_version=True,
                date_published=date(2018, 10, 11),
                semantic_scholar_id="ss-bert",
            ),
            DBPaper(
                id=3,
                title="ViT",
                abstract="Cites Transformer via arxiv id only.",
                arxiv_id="2010.11929",
                version="v2",
                is_latest_version=True,
                date_published=date(2020, 10, 22),
            ),
            DBPaper(
                id=4,
                title="An Old Version",
                abstract="Not the latest, should not be matched.",
                arxiv_id="9999.99999",
                version="v1",
                is_latest_version=False,
                date_published=date(2010, 1, 1),
                semantic_scholar_id="ss-old",
            ),
            DBMethod(
                id=10,
                name="Transformer",
                slug="transformer",
                source_paper_id=1,
            ),
            PaperMethod(paper_id=1, method_id=10),
        ]
    )
    db.commit()


# Fake client used by linking tests. Mimics the iter_citations / lookup contract.
class FakeClient:
    def __init__(self, citations_by_paper, lookups: Optional[dict] = None):
        self._citations_by_paper = citations_by_paper
        self._lookups = lookups or {}
        self.api_calls = 0
        self.rate_limit_hits = 0
        self.api_errors = 0

    def iter_citations(self, paper_id, page_size=1000, max_citations=None):
        for citing in self._citations_by_paper.get(paper_id, []):
            self.api_calls += 1
            yield citing

    def lookup_paper_by_arxiv(self, arxiv_id):
        self.api_calls += 1
        return self._lookups.get(arxiv_id)

    def close(self):
        pass


def _no_log(*_args, **_kwargs):
    return None


def test_normalize_arxiv_id_strips_version_and_whitespace():
    assert normalize_arxiv_id("2305.14314v1") == "2305.14314"
    assert normalize_arxiv_id("  1810.04805 ") == "1810.04805"
    assert normalize_arxiv_id("cs.CL/0101001v3") == "cs.CL/0101001"
    assert normalize_arxiv_id(None) is None
    assert normalize_arxiv_id("") is None


def test_iter_citations_paginates_until_no_next_and_stops_on_max():
    pages = [
        {
            "data": [
                {
                    "citingPaper": {
                        "paperId": "ss-bert",
                        "externalIds": {"ArXiv": "1810.04805"},
                        "title": "BERT",
                    }
                },
                {
                    "citingPaper": {
                        "paperId": "ss-vit",
                        "externalIds": {"ArXiv": "2010.11929"},
                        "title": "ViT",
                    }
                },
            ],
            "next": 2,
        },
        {
            "data": [
                {
                    "citingPaper": {
                        "paperId": "ss-extra",
                        "externalIds": {},
                        "title": "Extra",
                    }
                },
            ],
            # Missing `next` => last page.
        },
    ]
    requests_seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(dict(request.url.params))
        return httpx.Response(200, json=pages[len(requests_seen) - 1])

    transport = httpx.MockTransport(handler)
    httpx_client = httpx.Client(transport=transport, base_url="https://test")
    client = SemanticScholarClient(
        client=httpx_client, request_delay=0, sleep=lambda _seconds: None
    )

    citations = list(client.iter_citations("ss-source", page_size=2))
    assert [c.semantic_scholar_id for c in citations] == [
        "ss-bert",
        "ss-vit",
        "ss-extra",
    ]
    assert [c.arxiv_id for c in citations] == ["1810.04805", "2010.11929", None]
    assert len(requests_seen) == 2
    assert requests_seen[0]["offset"] == "0"
    assert requests_seen[1]["offset"] == "2"

    requests_seen.clear()
    capped = list(client.iter_citations("ss-source", page_size=2, max_citations=1))
    assert len(capped) == 1
    assert len(requests_seen) == 1


def test_iter_citations_respects_semantic_scholar_offset_limit_cap():
    """offset + limit must stay strictly below 10_000 per Semantic Scholar's docs."""
    requests_seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requests_seen.append(params)
        offset = int(params["offset"])
        limit = int(params["limit"])
        # Mimic the live API: enforce the hard cap.
        if offset + limit >= 10000:
            return httpx.Response(400, json={"error": "offset + limit must be < 10000"})
        # Return a full page until we hit the cap.
        next_offset = offset + limit
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citingPaper": {
                            "paperId": f"ss-{offset + i}",
                            "externalIds": {},
                            "title": f"Paper {offset + i}",
                        }
                    }
                    for i in range(limit)
                ],
                "next": next_offset,
            },
        )

    transport = httpx.MockTransport(handler)
    httpx_client = httpx.Client(transport=transport, base_url="https://test")
    client = SemanticScholarClient(
        client=httpx_client, request_delay=0, sleep=lambda _seconds: None
    )

    citations = list(client.iter_citations("ss-source", page_size=1000))
    assert len(citations) == 9999
    # We should never request a (offset, limit) pair where offset + limit >= 10000.
    for params in requests_seen:
        assert int(params["offset"]) + int(params["limit"]) < 10000
    # API errors counter must stay at zero because we never trigger the 400.
    assert client.api_errors == 0


def test_request_retries_on_429_then_succeeds():
    responses = [
        httpx.Response(429, json={}),
        httpx.Response(200, json={"paperId": "ss-x", "title": "ok"}),
    ]
    seen: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        idx = len(seen)
        seen.append(idx)
        return responses[idx]

    transport = httpx.MockTransport(handler)
    httpx_client = httpx.Client(transport=transport, base_url="https://test")
    client = SemanticScholarClient(
        client=httpx_client, request_delay=0, sleep=lambda _seconds: None
    )
    data = client.lookup_paper_by_arxiv("1234.5678")
    assert data == {"paperId": "ss-x", "title": "ok"}
    assert client.rate_limit_hits == 1
    assert client.retry_attempts == 1
    assert client.failed_requests == 0
    assert client.api_calls == 2


def test_dry_run_does_not_insert_paper_methods():
    db = _build_in_memory_session()
    _seed_corpus(db)
    client = FakeClient(
        citations_by_paper={
            "ss-source": [
                CitingPaper(
                    semantic_scholar_id="ss-bert", arxiv_id="1810.04805", title="BERT"
                ),
                CitingPaper(
                    semantic_scholar_id=None, arxiv_id="2010.11929", title="ViT"
                ),
            ]
        }
    )

    stats = link_papers_by_source_citations(db, client, write=False, log=_no_log)

    assert stats.methods_processed == 1
    assert stats.total_citations_fetched == 2
    assert stats.total_matched_papers == 2
    assert stats.total_new_links == 2

    pm_pairs = {(row.paper_id, row.method_id) for row in db.query(PaperMethod).all()}
    # Only the seed (1, 10) row should remain; no inserts in dry-run mode.
    assert pm_pairs == {(1, 10)}


def test_write_mode_inserts_new_links_and_skips_duplicates():
    db = _build_in_memory_session()
    _seed_corpus(db)
    db.add(PaperMethod(paper_id=2, method_id=10))  # Pre-existing duplicate for BERT.
    db.commit()

    client = FakeClient(
        citations_by_paper={
            "ss-source": [
                CitingPaper(
                    semantic_scholar_id="ss-bert", arxiv_id="1810.04805", title="BERT"
                ),
                CitingPaper(
                    semantic_scholar_id=None, arxiv_id="2010.11929", title="ViT"
                ),
                CitingPaper(
                    semantic_scholar_id="ss-bert", arxiv_id=None, title="BERT dup"
                ),
                CitingPaper(
                    semantic_scholar_id="ss-unknown",
                    arxiv_id="2099.12345",
                    title="External",
                ),
            ]
        }
    )

    stats = link_papers_by_source_citations(db, client, write=True, log=_no_log)

    assert stats.methods_processed == 1
    assert stats.total_citations_fetched == 4
    # Only BERT and ViT match local papers; BERT dup is deduped.
    assert stats.total_matched_papers == 2
    assert stats.total_new_links == 1  # ViT only; BERT was already linked.

    pm_pairs = {(row.paper_id, row.method_id) for row in db.query(PaperMethod).all()}
    assert pm_pairs == {(1, 10), (2, 10), (3, 10)}

    # Re-running should be a no-op (dedupe via existing paper_methods).
    client_rerun = FakeClient(
        citations_by_paper={
            "ss-source": [
                CitingPaper(
                    semantic_scholar_id="ss-bert", arxiv_id="1810.04805", title="BERT"
                ),
                CitingPaper(
                    semantic_scholar_id=None, arxiv_id="2010.11929", title="ViT"
                ),
            ]
        }
    )
    stats_rerun = link_papers_by_source_citations(
        db, client_rerun, write=True, log=_no_log
    )
    assert stats_rerun.total_new_links == 0
    pm_pairs_after = {
        (row.paper_id, row.method_id) for row in db.query(PaperMethod).all()
    }
    assert pm_pairs_after == pm_pairs


def test_skips_method_when_source_paper_has_no_ss_id_and_lookup_fails():
    db = _build_in_memory_session()
    db.add_all(
        [
            DBPaper(
                id=1,
                title="Unknown Source",
                abstract="No SS id and lookup will fail.",
                arxiv_id="9999.00000",
                version="v1",
                is_latest_version=True,
                date_published=date(2024, 1, 1),
            ),
            DBMethod(
                id=20,
                name="Mystery",
                slug="mystery",
                source_paper_id=1,
            ),
        ]
    )
    db.commit()

    client = FakeClient(citations_by_paper={}, lookups={})

    stats = link_papers_by_source_citations(db, client, write=True, log=_no_log)

    assert stats.methods_processed == 0
    assert stats.methods_skipped == 1
    assert stats.method_results[0].skipped_reason == "no semantic_scholar_id"
    assert db.query(PaperMethod).count() == 0


def test_lookup_backfills_source_paper_ss_id_in_write_mode():
    db = _build_in_memory_session()
    db.add_all(
        [
            DBPaper(
                id=1,
                title="Needs SS lookup",
                abstract="No SS id but lookup resolves.",
                arxiv_id="2305.14314",
                version="v1",
                is_latest_version=True,
                date_published=date(2023, 5, 23),
            ),
            DBPaper(
                id=2,
                title="Citing Paper",
                abstract="",
                arxiv_id="2401.00000",
                version="v1",
                is_latest_version=True,
                date_published=date(2024, 1, 1),
                semantic_scholar_id="ss-citing",
            ),
            DBMethod(
                id=30,
                name="QLoRA",
                slug="qlora",
                source_paper_id=1,
            ),
        ]
    )
    db.commit()

    client = FakeClient(
        citations_by_paper={
            "ss-resolved": [
                CitingPaper(
                    semantic_scholar_id="ss-citing", arxiv_id=None, title="Cite"
                )
            ]
        },
        lookups={"2305.14314": {"paperId": "ss-resolved", "title": "QLoRA"}},
    )

    stats = link_papers_by_source_citations(db, client, write=True, log=_no_log)

    refreshed_source = db.get(DBPaper, 1)
    assert refreshed_source.semantic_scholar_id == "ss-resolved"
    assert stats.methods_processed == 1
    assert stats.total_new_links == 1
    pm_pairs = {(row.paper_id, row.method_id) for row in db.query(PaperMethod).all()}
    assert pm_pairs == {(2, 30)}


def test_method_filter_selects_only_requested_method():
    db = _build_in_memory_session()
    _seed_corpus(db)
    db.add_all(
        [
            DBPaper(
                id=99,
                title="Other Source",
                abstract="",
                arxiv_id="9000.00000",
                version="v1",
                is_latest_version=True,
                date_published=date(2024, 6, 1),
                semantic_scholar_id="ss-other",
            ),
            DBMethod(
                id=99,
                name="Other",
                slug="other",
                source_paper_id=99,
            ),
        ]
    )
    db.commit()

    client = FakeClient(
        citations_by_paper={
            "ss-source": [
                CitingPaper(
                    semantic_scholar_id="ss-bert", arxiv_id="1810.04805", title="BERT"
                )
            ],
            "ss-other": [
                CitingPaper(
                    semantic_scholar_id="ss-bert", arxiv_id="1810.04805", title="BERT"
                )
            ],
        }
    )

    stats = link_papers_by_source_citations(
        db, client, write=False, log=_no_log, method_slug="transformer"
    )
    assert stats.methods_processed == 1
    assert [r.method_slug for r in stats.method_results] == ["transformer"]


@pytest.mark.parametrize(
    "kwargs, expected_skip",
    [
        ({"method_slug": "does-not-exist"}, 0),
        ({"method_id": 999}, 0),
    ],
)
def test_filters_with_no_matches_return_empty_stats(kwargs, expected_skip):
    db = _build_in_memory_session()
    _seed_corpus(db)
    client = FakeClient(citations_by_paper={})

    stats = link_papers_by_source_citations(
        db, client, write=False, log=_no_log, **kwargs
    )
    assert stats.methods_processed == 0
    assert stats.methods_skipped == expected_skip
    assert db.query(PaperMethod).count() == 1  # Seed only.


def test_paper_methods_only_inserts_for_latest_versions():
    """Citing-paper matches should not pick up non-latest version rows."""
    db = _build_in_memory_session()
    _seed_corpus(db)
    client = FakeClient(
        citations_by_paper={
            "ss-source": [
                CitingPaper(
                    semantic_scholar_id="ss-old", arxiv_id="9999.99999", title="Old"
                ),
            ]
        }
    )

    stats = link_papers_by_source_citations(db, client, write=True, log=_no_log)
    # Old version was excluded from the local index, so no match.
    assert stats.total_matched_papers == 0
    # Sanity-check we did not somehow add the non-latest paper to paper_methods.
    rows = db.execute(
        text("SELECT paper_id FROM paper_methods WHERE method_id = 10")
    ).all()
    assert {row[0] for row in rows} == {1}
