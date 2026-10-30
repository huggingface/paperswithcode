from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.models.database import Author, Base, Paper, PaperAuthor
from backend.routers import papers as papers_router
from backend.services.paper_citation_refresh_service import (
    PaperCitationRefreshService,
)
from backend.services.paper_service import PaperService
from backend.services.semantic_scholar_service import SemanticScholarService
from backend.utils.exceptions import DatabaseError


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


def _session_factory(tmp_path, name: str):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(
        bind=engine,
        tables=[Paper.__table__, Author.__table__, PaperAuthor.__table__],
    )
    return sessionmaker(bind=engine)


def _paper(
    paper_id: int,
    *,
    citation_count: int,
    citation_updated_at: datetime | None,
    published: date,
    latest: bool = True,
    arxiv_id: str | None = None,
) -> Paper:
    arxiv_id = arxiv_id if arxiv_id is not None else f"2601.{paper_id:05d}"
    return Paper(
        id=paper_id,
        title=f"Paper {paper_id}",
        abstract="Abstract",
        source="arxiv",
        arxiv_id=arxiv_id,
        version="v1",
        is_latest_version=latest,
        citation_count=citation_count,
        citation_updated_at=citation_updated_at,
        date_published=published,
    )


def test_citation_refresh_route_preserves_success_and_error_contract(monkeypatch):
    db = object()

    class SuccessfulPaperService:
        def __init__(self, received_db):
            assert received_db is db

        async def update_citation_counts(self, limit):
            assert limit == 17
            return {"updated_count": 4, "limit": 17, "status": "completed"}

    monkeypatch.setattr(papers_router, "PaperService", SuccessfulPaperService)
    assert asyncio.run(papers_router.update_citation_counts(limit=17, db=db)) == {
        "updated_count": 4,
        "limit": 17,
        "status": "completed",
    }

    class FailingPaperService:
        def __init__(self, received_db):
            assert received_db is db

        async def update_citation_counts(self, limit):
            raise DatabaseError(f"refresh failed at limit {limit}")

    monkeypatch.setattr(papers_router, "PaperService", FailingPaperService)
    with pytest.raises(DatabaseError, match="refresh failed at limit 17"):
        asyncio.run(papers_router.update_citation_counts(limit=17, db=db))


def test_paper_service_refreshes_before_building_the_public_result(monkeypatch):
    db = object()
    calls = []

    async def batch_update(service, limit):
        calls.append((service.db, limit))
        return 4

    monkeypatch.setattr(
        SemanticScholarService, "batch_update_citation_counts", batch_update
    )

    result = asyncio.run(PaperService(db).update_citation_counts(limit=17))

    assert calls == [(db, 17)]
    assert result == {"updated_count": 4, "limit": 17, "status": "completed"}


def test_paper_service_refresh_wraps_provider_failures(monkeypatch):
    async def fail(_service, _limit):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(SemanticScholarService, "batch_update_citation_counts", fail)

    with pytest.raises(
        DatabaseError,
        match="^Error updating citation counts: provider unavailable$",
    ):
        asyncio.run(PaperService(object()).update_citation_counts(limit=3))


def test_cron_selection_projection_and_statistics_contract(tmp_path):
    session_factory = _session_factory(tmp_path, "citation-selection.db")
    now = datetime.now(UTC).replace(tzinfo=None)
    stale = now - timedelta(days=30)
    fresh = now - timedelta(days=1)
    with session_factory() as db:
        db.add_all(
            [
                _paper(
                    1,
                    citation_count=5,
                    citation_updated_at=None,
                    published=date(2025, 1, 1),
                ),
                _paper(
                    2,
                    citation_count=0,
                    citation_updated_at=stale,
                    published=date(2020, 1, 1),
                ),
                _paper(
                    3,
                    citation_count=0,
                    citation_updated_at=stale,
                    published=date(2017, 1, 1),
                ),
                _paper(
                    4,
                    citation_count=10,
                    citation_updated_at=stale,
                    published=date(2020, 1, 1),
                ),
                _paper(
                    5,
                    citation_count=10,
                    citation_updated_at=stale,
                    published=date(2020, 1, 1),
                    latest=False,
                ),
                Paper(
                    id=6,
                    title="External paper",
                    source="external",
                    source_url="https://example.com/paper",
                    is_latest_version=True,
                    citation_count=0,
                    citation_updated_at=None,
                    date_published=date(2020, 1, 1),
                ),
                _paper(
                    7,
                    citation_count=1,
                    citation_updated_at=fresh,
                    published=date(2020, 1, 1),
                ),
            ]
        )
        db.commit()
        service = PaperCitationRefreshService(db)

        assert service.count_pending(7) == 4
        rows = service.pending_chunk(0, 4, 7)
        assert [row["id"] for row in rows] == [1, 2, 3, 4]
        assert rows[0] == {
            "id": 1,
            "arxiv_id": "2601.00001",
            "title": "Paper 1",
            "citation_count": 5,
            "citation_updated_at": None,
            "date_published": date(2025, 1, 1),
            "priority_type": "NEVER_UPDATED",
        }
        assert [row["priority_type"] for row in rows] == [
            "NEVER_UPDATED",
            "ZERO_CITATIONS",
            "ZERO_CITATIONS",
            "REFRESH",
        ]
        assert service.statistics() == {
            "total_papers": 6,
            "papers_processed": 4,
            "papers_with_citations": 3,
            "processed_percentage": 66.7,
            "citations_percentage": 50.0,
        }


def test_due_selection_refreshes_recent_papers_before_older_ones(tmp_path):
    session_factory = _session_factory(tmp_path, "citation-recent.db")
    now = datetime.now(UTC).replace(tzinfo=None)
    today = now.date()
    with session_factory() as db:
        db.add_all(
            [
                # Old paper, zero citations, refreshed longest ago.
                _paper(
                    1,
                    citation_count=0,
                    citation_updated_at=now - timedelta(days=60),
                    published=date(2020, 1, 1),
                ),
                _paper(
                    2,
                    citation_count=9,
                    citation_updated_at=now - timedelta(days=8),
                    published=today - timedelta(days=30),
                ),
                _paper(
                    3,
                    citation_count=4,
                    citation_updated_at=now - timedelta(days=20),
                    published=today - timedelta(days=200),
                ),
                _paper(
                    4,
                    citation_count=0,
                    citation_updated_at=None,
                    published=date(2019, 1, 1),
                ),
                _paper(
                    5,
                    citation_count=7,
                    citation_updated_at=now - timedelta(days=9),
                    published=today - timedelta(days=400),
                ),
            ]
        )
        db.commit()

        rows = PaperCitationRefreshService(db).pending_chunk(0, 5, 7)

    # Never refreshed, then the last year oldest-refresh first, then the rest.
    assert [row["id"] for row in rows] == [4, 3, 2, 1, 5]


def test_early_refresh_picks_oldest_not_yet_due_arxiv_papers(tmp_path):
    session_factory = _session_factory(tmp_path, "citation-early.db")
    now = datetime.now(UTC).replace(tzinfo=None)
    with session_factory() as db:
        db.add_all(
            [
                _paper(
                    1,
                    citation_count=3,
                    citation_updated_at=now - timedelta(days=30),
                    published=date(2025, 1, 1),
                ),
                _paper(
                    2,
                    citation_count=3,
                    citation_updated_at=now - timedelta(days=2),
                    published=date(2025, 1, 1),
                ),
                _paper(
                    3,
                    citation_count=3,
                    citation_updated_at=now - timedelta(days=6),
                    published=date(2025, 1, 1),
                ),
                _paper(
                    4,
                    citation_count=3,
                    citation_updated_at=now - timedelta(days=5),
                    published=date(2025, 1, 1),
                    latest=False,
                ),
                _paper(
                    5,
                    citation_count=3,
                    citation_updated_at=None,
                    published=date(2025, 1, 1),
                ),
            ]
        )
        db.commit()
        service = PaperCitationRefreshService(db)

        assert service.count_refreshable() == 4
        rows = service.refresh_ahead_chunk(5, 7)
        # Due and never-refreshed papers belong to the regular pending set.
        assert [row["id"] for row in rows] == [3, 2]


def test_cron_batch_persists_successes_and_marks_failures_processed(tmp_path):
    session_factory = _session_factory(tmp_path, "citation-update.db")
    with session_factory() as db:
        db.add_all(
            [
                _paper(
                    1,
                    citation_count=1,
                    citation_updated_at=None,
                    published=date(2025, 1, 1),
                ),
                _paper(
                    2,
                    citation_count=2,
                    citation_updated_at=None,
                    published=date(2025, 1, 1),
                ),
            ]
        )
        db.commit()
        result = PaperCitationRefreshService(db).update_batch(
            [
                {
                    "paper_id": 1,
                    "citation_count": 42,
                    "semantic_scholar_id": "ss-1",
                    "success": True,
                },
                {
                    "paper_id": 2,
                    "citation_count": 99,
                    "semantic_scholar_id": None,
                    "success": False,
                },
                {
                    "paper_id": 999,
                    "citation_count": 5,
                    "semantic_scholar_id": "ss-missing",
                    "success": True,
                },
            ]
        )

    assert result == {"updated": 1, "failed": 2}
    with session_factory() as persisted_db:
        success = persisted_db.get(Paper, 1)
        failure = persisted_db.get(Paper, 2)
        assert (success.citation_count, success.semantic_scholar_id) == (42, "ss-1")
        assert (failure.citation_count, failure.semantic_scholar_id) == (2, None)
        assert success.citation_updated_at is not None
        assert failure.citation_updated_at is not None


def test_cron_batch_rolls_back_when_commit_fails():
    events = []

    class FailingSession:
        def commit(self):
            events.append("commit")
            raise RuntimeError("commit failed")

        def rollback(self):
            events.append("rollback")

    with pytest.raises(
        DatabaseError,
        match="^Error updating citation counts batch: commit failed$",
    ):
        PaperCitationRefreshService(FailingSession()).update_batch([])
    assert events == ["commit", "rollback"]


def test_semantic_scholar_outage_keeps_existing_identity(tmp_path, monkeypatch):
    from backend.services import semantic_scholar_service as s2

    Session = _session_factory(tmp_path, "s2-outage.db")
    db = Session()
    db.add(
        Paper(
            id=1,
            title="Attention Is All You Need",
            arxiv_id="1706.03762",
            version="v1",
            is_latest_version=True,
            semantic_scholar_id="s2-attention",
            citation_count=10,
        )
    )
    db.commit()

    responses = iter([httpx.Response(429), httpx.Response(503)])
    transport = httpx.MockTransport(lambda _request: next(responses))
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        s2.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    monkeypatch.setattr(s2, "RATE_LIMIT_DELAY", 0)

    service = SemanticScholarService(db)
    assert asyncio.run(service.batch_update_citation_counts(limit=10)) == 0
    with pytest.raises(s2.SemanticScholarUnavailableError):
        asyncio.run(service.get_paper_by_semantic_scholar_id("s2-attention"))

    paper = db.get(Paper, 1)
    assert paper.semantic_scholar_id == "s2-attention"
    assert paper.citation_updated_at is None
    assert paper.citation_count == 10
    db.close()


def test_semantic_scholar_not_found_marks_paper_processed(tmp_path, monkeypatch):
    from backend.services import semantic_scholar_service as s2

    Session = _session_factory(tmp_path, "s2-missing.db")
    db = Session()
    db.add(
        Paper(
            id=1,
            title="Unknown Paper",
            arxiv_id="2601.00001",
            version="v1",
            is_latest_version=True,
        )
    )
    db.commit()

    def respond(request):
        if request.url.path.endswith("/paper/search"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(respond)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        s2.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    monkeypatch.setattr(s2, "RATE_LIMIT_DELAY", 0)

    assert asyncio.run(SemanticScholarService(db).batch_update_citation_counts()) == 0
    assert db.get(Paper, 1).citation_updated_at is not None
    db.close()
