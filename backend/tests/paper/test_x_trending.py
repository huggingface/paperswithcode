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
from backend.models.x_trending import XTrendingPaperInput
from backend.services.paper_ingestion_service import PaperIngestionError
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
def db():
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
    with Session(engine) as session:
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


def test_input_needs_an_identifier():
    with pytest.raises(ValueError):
        XTrendingPaperInput(rank=1, title="No link")
