"""Papers trending on X: day replacement and the shared-date trending feed."""

import asyncio
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    HfArtifact,
    Paper,
    PaperHfArtifact,
    PaperRepository,
    PaperXTrending,
    Repository,
)
from backend.models.papers import Paper as PaperCard
from backend.models.x_trending import XTrendingPaperInput
from backend.services.paper_ingestion_service import PaperIngestionError
from backend.services.paper_service import PaperService
from backend.services.x_trending_service import XTrendingService


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _sqlite_json(_type, _compiler, **_kwargs):
    return "TEXT"


def paper(ident, *, score=None, arxiv_id=None, source="arxiv", source_url=None):
    return Paper(
        id=ident,
        title=f"Paper {ident}",
        abstract="",
        source=source,
        source_url=source_url,
        arxiv_id=arxiv_id,
        version="v1",
        date_published=date(2026, 9, 1),
        is_latest_version=True,
        trending_score=score,
        trending_score_updated_at=datetime.now(timezone.utc) if score else None,
    )


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                Paper,
                PaperXTrending,
                Repository,
                PaperRepository,
                HfArtifact,
                PaperHfArtifact,
            )
        ],
    )
    monkeypatch.setattr(
        PaperService,
        "hydrate_cards",
        lambda self, rows, **_: [
            PaperCard.model_construct(id=str(row.id)) for row in rows
        ],
    )
    with Session(engine) as session:
        monkeypatch.setattr(
            PaperService(session).settings, "trending_ranking_mode", "composite"
        )
        session.add_all(
            [
                paper(1, score=5.0, arxiv_id="2610.00001"),
                paper(2, score=9.0, arxiv_id="2610.00002"),
                paper(3, arxiv_id="2610.00003"),
                paper(4, score=50.0, arxiv_id="2610.00004"),
                paper(
                    5,
                    source="external",
                    source_url="https://example.com/blog",
                ),
            ]
        )
        session.commit()
        yield session
    engine.dispose()


class FakeIngestion:
    def __init__(self, db):
        self.db = db

    async def get_or_import_arxiv_paper(self, arxiv_id):
        existing = self.db.query(Paper).filter(Paper.arxiv_id == arxiv_id).first()
        if existing:
            return existing, False
        if arxiv_id == "2610.99999":
            raise PaperIngestionError(arxiv_id, "not_found")
        created = paper(6, arxiv_id=arxiv_id)
        self.db.add(created)
        self.db.flush()
        return created, True


def row(rank, **fields):
    return XTrendingPaperInput(rank=rank, **fields)


def replace(db, day, rows):
    return asyncio.run(XTrendingService(db, FakeIngestion(db)).replace_day(day, rows))


def feed(db, **window):
    response = XTrendingService(db).feed(
        page=1,
        page_size=10,
        start_date=window.get("start_date"),
        end_date=window.get("end_date"),
        include_resources=False,
        has_code=False,
        has_hf_artifacts=False,
    )
    return [card.id for card in response.results]


def test_replace_day_imports_matches_and_reports_unresolved(db):
    result = replace(
        db,
        date(2026, 10, 30),
        [
            row(1, arxiv_id="2610.00001", post_url="https://x.com/a/status/1"),
            row(2, source_url="https://example.com/blog"),
            row(3, arxiv_id="2610.55555", like_count=10, view_count=3_000_000_000),
            row(4, source_url="https://example.com/unknown", title="Blog"),
            row(5, arxiv_id="2610.99999"),
            row(6, arxiv_id="2610.00001"),
        ],
    )
    assert result.linked == 3
    assert result.imported == ["2610.55555"]
    assert [(item.rank, item.reason) for item in result.unresolved] == [
        (4, "no external paper with this source URL"),
        (5, "arxiv import failed: not_found"),
    ]
    stored = {entry.paper_id: entry.rank for entry in db.query(PaperXTrending).all()}
    assert stored == {1: 1, 5: 2, 6: 3}

    # Re-running a day replaces its rows instead of accumulating them.
    replace(db, date(2026, 10, 30), [row(1, arxiv_id="2610.00002")])
    assert [entry.paper_id for entry in db.query(PaperXTrending).all()] == [2]


def test_feed_orders_by_trending_score_within_publication_window(db):
    replace(
        db,
        date(2026, 10, 29),
        [row(1, arxiv_id="2610.00001"), row(2, arxiv_id="2610.00003")],
    )
    replace(
        db,
        date(2026, 10, 30),
        [row(1, arxiv_id="2610.00002"), row(2, arxiv_id="2610.00004")],
    )
    # Paper 4 has the top score and was shared this week, but was published
    # in August, outside the window.
    db.get(Paper, 4).date_published = date(2026, 8, 1)
    db.commit()

    window = {"start_date": date(2026, 8, 25), "end_date": date(2026, 9, 1)}
    # Unscored paper 3 stays listed after the scored ones.
    assert feed(db, **window) == ["2", "1", "3"]
    assert feed(db) == ["4", "2", "1", "3"]


def test_input_needs_an_identifier():
    with pytest.raises(ValueError):
        XTrendingPaperInput(rank=1, title="No link")


def test_feed_follows_a_newer_version_of_a_shared_paper(db):
    replace(db, date(2026, 10, 30), [row(1, arxiv_id="2610.00001")])
    db.get(Paper, 1).is_latest_version = False
    newer = paper(7, score=5.0, arxiv_id="2610.00001")
    newer.version = "v2"
    db.add(newer)
    db.commit()
    assert feed(db) == ["7"]
