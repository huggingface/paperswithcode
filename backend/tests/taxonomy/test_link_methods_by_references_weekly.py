"""Tests for the weekly references-based method tagging cron."""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# The weekly cron lives under .github/workflows/scripts/, which is added to
# PYTHONPATH at runtime via the wrapper shell. Mirror that for tests so we can
# import `scripts.weekly.link_methods_by_references` directly.
WORKFLOWS_SCRIPTS_PATH = Path(__file__).resolve().parents[3] / ".github" / "workflows"
if str(WORKFLOWS_SCRIPTS_PATH) not in sys.path:
    sys.path.insert(0, str(WORKFLOWS_SCRIPTS_PATH))

from backend.database.methods_setup.link_papers_by_source_citations import (  # noqa: E402
    CitedPaper,
    SemanticScholarClient,
)
from backend.models.database import (  # noqa: E402
    Base,
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
)
from scripts.weekly.link_methods_by_references import (  # noqa: E402
    build_method_source_index,
    count_unscanned_papers,
    link_methods_by_references,
    select_unscanned_papers,
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
    """Two source papers (Transformer + ResNet), three citing papers."""

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
                semantic_scholar_id="ss-attention",
            ),
            DBPaper(
                id=2,
                title="Deep Residual Learning",
                abstract="Source paper.",
                arxiv_id="1512.03385",
                version="v1",
                is_latest_version=True,
                date_published=date(2015, 12, 10),
                # Intentionally no semantic_scholar_id; matches via arxiv_id only.
            ),
            DBPaper(
                id=10,
                title="Citing Paper A",
                abstract="Cites Transformer (via SS) and ResNet (via arxiv).",
                arxiv_id="2401.00001",
                version="v1",
                is_latest_version=True,
                date_published=date(2024, 1, 5),
                semantic_scholar_id="ss-citing-a",
            ),
            DBPaper(
                id=11,
                title="Citing Paper B",
                abstract="Cites only Transformer (via SS).",
                arxiv_id="2401.00002",
                version="v1",
                is_latest_version=True,
                date_published=date(2024, 1, 6),
                semantic_scholar_id="ss-citing-b",
                methods_scanned_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ),
            DBPaper(
                id=12,
                title="Citing Paper C",
                abstract="Has neither SS id nor arxiv id; cannot be resolved.",
                source="external",
                source_url="https://example.com/paper-c",
                version=None,
                is_latest_version=True,
                date_published=date(2024, 1, 7),
            ),
            DBMethod(id=100, name="Transformer", slug="transformer", source_paper_id=1),
            DBMethod(
                id=101,
                name="Multi-Head Attention",
                slug="multi-head-attention",
                source_paper_id=1,
            ),
            DBMethod(id=200, name="ResNet", slug="resnet", source_paper_id=2),
            PaperMethod(paper_id=1, method_id=100),
            PaperMethod(paper_id=1, method_id=101),
            PaperMethod(paper_id=2, method_id=200),
        ]
    )
    db.commit()


class FakeReferencesClient:
    """Mimics SemanticScholarClient's references contract."""

    def __init__(self, references_by_paper, *, fail_429: int = 0):
        self._refs = references_by_paper
        self.api_calls = 0
        self.rate_limit_hits = fail_429
        self.api_errors = 0
        self.requested = []

    def iter_references(self, paper_id, page_size=1000, max_references=None):
        self.requested.append(paper_id)
        for cited in self._refs.get(paper_id, []):
            self.api_calls += 1
            yield cited

    def close(self):
        pass


def _no_log(*_args, **_kwargs):
    return None


def test_iter_references_paginates_and_respects_caps():
    pages = [
        {
            "data": [
                {
                    "citedPaper": {
                        "paperId": "ss-attention",
                        "externalIds": {"ArXiv": "1706.03762"},
                        "title": "Attention",
                    }
                },
                {
                    "citedPaper": {
                        "paperId": "ss-resnet",
                        "externalIds": {"ArXiv": "1512.03385"},
                        "title": "ResNet",
                    }
                },
            ],
            "next": 2,
        },
        {
            "data": [
                {
                    "citedPaper": {
                        "paperId": "ss-extra",
                        "externalIds": {},
                        "title": "Extra",
                    }
                }
            ],
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

    refs = list(client.iter_references("ss-paper", page_size=2))
    assert [r.semantic_scholar_id for r in refs] == [
        "ss-attention",
        "ss-resnet",
        "ss-extra",
    ]
    assert [r.arxiv_id for r in refs] == ["1706.03762", "1512.03385", None]
    assert len(requests_seen) == 2
    assert requests_seen[0]["offset"] == "0"
    assert requests_seen[1]["offset"] == "2"

    requests_seen.clear()
    capped = list(client.iter_references("ss-paper", page_size=2, max_references=1))
    assert len(capped) == 1
    assert len(requests_seen) == 1


def test_iter_references_respects_offset_limit_cap():
    requests_seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requests_seen.append(params)
        offset = int(params["offset"])
        limit = int(params["limit"])
        if offset + limit >= 10000:
            return httpx.Response(400, json={"error": "offset + limit must be < 10000"})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citedPaper": {
                            "paperId": f"ss-{offset + i}",
                            "externalIds": {},
                            "title": f"Ref {offset + i}",
                        }
                    }
                    for i in range(limit)
                ],
                "next": offset + limit,
            },
        )

    transport = httpx.MockTransport(handler)
    httpx_client = httpx.Client(transport=transport, base_url="https://test")
    client = SemanticScholarClient(
        client=httpx_client, request_delay=0, sleep=lambda _seconds: None
    )

    refs = list(client.iter_references("ss-huge", page_size=1000))
    assert len(refs) == 9999
    for params in requests_seen:
        assert int(params["offset"]) + int(params["limit"]) < 10000
    assert client.api_errors == 0


def test_build_method_source_index_groups_methods_per_source():
    db = _build_in_memory_session()
    _seed_corpus(db)

    by_ss, by_arxiv, names = build_method_source_index(db)

    assert by_ss == {"ss-attention": [100, 101]} or sorted(by_ss["ss-attention"]) == [
        100,
        101,
    ]
    # ResNet has no SS id but does have an arxiv id.
    assert by_arxiv["1706.03762"] == [100, 101] or sorted(by_arxiv["1706.03762"]) == [
        100,
        101,
    ]
    assert by_arxiv["1512.03385"] == [200]
    assert names == {100: "Transformer", 101: "Multi-Head Attention", 200: "ResNet"}


def test_select_unscanned_papers_skips_already_scanned_and_orders_newest_first():
    db = _build_in_memory_session()
    _seed_corpus(db)

    rows = select_unscanned_papers(db, limit=10)
    ids_in_order = [r["id"] for r in rows]
    # 11 has methods_scanned_at set, so it must be excluded.
    assert 11 not in ids_in_order
    # 12 (newest) > 10 > 1/2 (source papers, also unscanned)
    assert ids_in_order[0] == 12
    assert ids_in_order[1] == 10
    # All four unscanned papers selected (1, 2 are unscanned source papers).
    assert sorted(ids_in_order) == [1, 2, 10, 12]

    # --rescan should also include paper 11.
    rows_with_rescan = select_unscanned_papers(db, limit=10, rescan=True)
    assert 11 in [r["id"] for r in rows_with_rescan]


def test_select_unscanned_papers_limit_respected():
    db = _build_in_memory_session()
    _seed_corpus(db)

    rows = select_unscanned_papers(db, limit=2)
    assert len(rows) == 2


def test_count_unscanned_papers():
    db = _build_in_memory_session()
    _seed_corpus(db)
    # 1, 2, 10, 12 are unscanned; 11 is scanned.
    assert count_unscanned_papers(db) == 4


def test_dry_run_does_not_write_links_or_mark_scanned():
    db = _build_in_memory_session()
    _seed_corpus(db)

    client = FakeReferencesClient(
        references_by_paper={
            "ss-citing-a": [
                CitedPaper(
                    semantic_scholar_id="ss-attention",
                    arxiv_id="1706.03762",
                    title="Attention",
                ),
                CitedPaper(
                    semantic_scholar_id=None,
                    arxiv_id="1512.03385",
                    title="ResNet (arxiv only)",
                ),
            ],
            "arXiv:2401.00002": [],
            "arXiv:1706.03762": [],
            "arXiv:1512.03385": [],
        }
    )

    stats = link_methods_by_references(db, client, limit=10, write=False, log=_no_log)

    # Citing Paper A would have matched 3 methods: Transformer (100), MHA (101) via SS,
    # and ResNet (200) via arxiv id.
    assert stats.method_matches_found >= 3
    assert stats.links_inserted == 0

    # No paper_methods rows added beyond the 3 seeded source-paper links.
    assert db.query(PaperMethod).count() == 3

    # Nothing should be marked as scanned.
    unscanned = db.execute(
        text("SELECT id FROM papers WHERE methods_scanned_at IS NULL ORDER BY id")
    ).all()
    assert {row[0] for row in unscanned} == {1, 2, 10, 12}


def test_write_mode_inserts_links_dedupes_and_marks_scanned():
    db = _build_in_memory_session()
    _seed_corpus(db)

    client = FakeReferencesClient(
        references_by_paper={
            "ss-citing-a": [
                CitedPaper(
                    semantic_scholar_id="ss-attention",
                    arxiv_id="1706.03762",
                    title="Attention",
                ),
                CitedPaper(
                    semantic_scholar_id=None,
                    arxiv_id="1512.03385",
                    title="ResNet",
                ),
            ],
            "arXiv:1706.03762": [],
            "arXiv:1512.03385": [],
        }
    )

    stats = link_methods_by_references(db, client, limit=10, write=True, log=_no_log)

    # 12 is unresolvable (no SS id, no arxiv id) — must still be marked scanned.
    rows = {
        row[0]: row[1]
        for row in db.execute(
            text("SELECT id, methods_scanned_at FROM papers WHERE id IN (1,2,10,12)")
        ).all()
    }
    for paper_id in (1, 2, 10, 12):
        assert rows[paper_id] is not None, f"paper {paper_id} should be marked scanned"

    # Citing Paper A picked up 3 method links (100, 101, 200).
    pm_pairs = {(row.paper_id, row.method_id) for row in db.query(PaperMethod).all()}
    assert (10, 100) in pm_pairs
    assert (10, 101) in pm_pairs
    assert (10, 200) in pm_pairs

    assert stats.papers_skipped_no_ss_id == 1  # paper 12
    assert stats.papers_processed >= 3  # 1, 2, 10 were resolvable
    assert stats.links_inserted == 3


def test_write_mode_is_idempotent_when_rerun():
    db = _build_in_memory_session()
    _seed_corpus(db)

    refs = {
        "ss-citing-a": [
            CitedPaper(
                semantic_scholar_id="ss-attention",
                arxiv_id="1706.03762",
                title="Attention",
            ),
        ],
        "arXiv:1706.03762": [],
        "arXiv:1512.03385": [],
    }
    client_first = FakeReferencesClient(references_by_paper=refs)
    link_methods_by_references(db, client_first, limit=10, write=True, log=_no_log)

    pm_after_first = {
        (row.paper_id, row.method_id) for row in db.query(PaperMethod).all()
    }

    # Re-run: every paper is now scanned, so the second run should select 0 papers.
    client_second = FakeReferencesClient(references_by_paper=refs)
    stats_second = link_methods_by_references(
        db, client_second, limit=10, write=True, log=_no_log
    )
    assert stats_second.papers_eligible == 0
    assert stats_second.links_inserted == 0
    assert client_second.api_calls == 0

    pm_after_second = {
        (row.paper_id, row.method_id) for row in db.query(PaperMethod).all()
    }
    assert pm_after_first == pm_after_second


def test_failed_or_partial_lookup_is_left_unscanned_without_links():
    db = _build_in_memory_session()
    _seed_corpus(db)

    class PartialFailureClient(FakeReferencesClient):
        def iter_references(self, paper_id, page_size=1000, max_references=None):
            self.requested.append(paper_id)
            if paper_id == "ss-citing-a":
                yield CitedPaper(
                    semantic_scholar_id="ss-attention",
                    arxiv_id="1706.03762",
                    title="Attention",
                )
                self.api_errors += 1
                return

    stats = link_methods_by_references(
        db,
        PartialFailureClient(references_by_paper={}),
        limit=10,
        write=True,
        log=_no_log,
    )

    assert stats.papers_lookup_failed == 1
    assert db.get(DBPaper, 10).methods_scanned_at is None
    assert db.get(PaperMethod, (10, 100)) is None
    assert db.get(PaperMethod, (10, 101)) is None


def test_no_transaction_is_open_during_reference_lookups():
    db = _build_in_memory_session()
    _seed_corpus(db)
    db.commit()

    class TransactionCheckingClient(FakeReferencesClient):
        def iter_references(self, paper_id, page_size=1000, max_references=None):
            assert not db.in_transaction()
            yield from super().iter_references(paper_id, page_size, max_references)

    stats = link_methods_by_references(
        db,
        TransactionCheckingClient(references_by_paper={}),
        limit=10,
        write=True,
        log=_no_log,
    )

    assert stats.papers_processed > 0


def test_paper_with_only_arxiv_id_uses_arxiv_form_for_lookup():
    db = _build_in_memory_session()
    _seed_corpus(db)

    captured: list[str] = []

    class CapturingClient(FakeReferencesClient):
        def iter_references(self, paper_id, page_size=1000, max_references=None):
            captured.append(paper_id)
            return iter([])

    client = CapturingClient(references_by_paper={})

    link_methods_by_references(db, client, limit=10, write=True, log=_no_log)

    # Paper 2 has arxiv_id but no SS id, so it should be queried as arXiv:1512.03385.
    assert "arXiv:1512.03385" in captured
    # Paper 10 has SS id and should be queried directly.
    assert "ss-citing-a" in captured


def test_targeted_paper_id_overrides_unscanned_filter():
    db = _build_in_memory_session()
    _seed_corpus(db)

    # Paper 11 is scanned, but explicit --paper-id should still pick it up.
    client = FakeReferencesClient(
        references_by_paper={
            "ss-citing-b": [
                CitedPaper(
                    semantic_scholar_id="ss-attention",
                    arxiv_id="1706.03762",
                    title="Attention",
                )
            ]
        }
    )

    stats = link_methods_by_references(
        db, client, limit=10, paper_id=11, write=True, log=_no_log
    )

    assert stats.papers_processed == 1
    pm_pairs = {(row.paper_id, row.method_id) for row in db.query(PaperMethod).all()}
    assert (11, 100) in pm_pairs
    assert (11, 101) in pm_pairs


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
