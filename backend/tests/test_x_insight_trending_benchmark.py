"""Characterize the trending-benchmark X insight's 90 vs. 180 day windows."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import Base, Dataset, Evaluation, Paper, XInsightPost
from backend.services import x_insight_post_service as insights


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _compile_postgres_container_sqlite(_element, _compiler, **_kw):
    return "TEXT"


NOW = datetime(2026, 11, 21, 9, tzinfo=UTC)
TODAY = NOW.date()
RECENT_START = TODAY - timedelta(days=90)
BASELINE_START = RECENT_START - timedelta(days=180)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Dataset.__table__,
            Paper.__table__,
            Evaluation.__table__,
            XInsightPost.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _report(db, dataset_id: int, published: date, *, latest: bool = True, rows=1):
    paper_id = db.query(Paper).count() + 1
    db.add(
        Paper(
            id=paper_id,
            title=f"Paper {paper_id}",
            abstract="Abstract",
            arxiv_id=f"2611.{paper_id:05d}",
            version="v1",
            is_latest_version=latest,
            date_published=published,
        )
    )
    for _ in range(rows):
        db.add(
            Evaluation(
                paper_id=paper_id, task_id=1, dataset_id=dataset_id, metrics={"A": 1}
            )
        )


def test_trending_benchmark_counts_exclusive_window_starts(db, monkeypatch):
    db.add_all(
        [
            Dataset(id=1, name="Alpha", slug="alpha"),
            Dataset(id=2, name="Beta", slug="beta"),
            Dataset(id=3, name="Gamma", slug="gamma"),
        ]
    )
    for offset in range(4):
        _report(db, 1, TODAY - timedelta(days=offset), rows=2)
    _report(db, 1, RECENT_START + timedelta(days=1))
    _report(db, 1, RECENT_START)
    _report(db, 1, BASELINE_START + timedelta(days=1))
    _report(db, 1, BASELINE_START)
    _report(db, 1, TODAY + timedelta(days=1))
    _report(db, 1, TODAY, latest=False)
    for offset in range(6):
        _report(db, 2, TODAY - timedelta(days=10 + offset))
    for offset in range(4):
        _report(db, 3, TODAY - timedelta(days=offset))
    db.commit()
    cards = []
    monkeypatch.setattr(
        insights, "render_bar_card", lambda *args, **kwargs: cards.append(args) or b""
    )

    insight = insights.trending_benchmark(db, now=NOW)

    assert insight.subject_key == "beta"
    assert insight.facts["papers_last_90_days"] == 6
    assert insight.facts["papers_previous_180_days"] == 0
    assert "6 papers reported results on it in the last 90 days" in insight.text
    assert "after none in the 180 days before." in insight.text
    assert [(bar.label, bar.value) for bar in cards[0][2]] == [
        ("Beta", 6),
        ("Alpha", 5),
    ]
    assert cards[0][2][1].value_label == "5 · " + insights.benchmark_growth(5, 2)
