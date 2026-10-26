"""Tests for the cross-area trending task and method rankings."""

from datetime import date, timedelta
import math

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import (
    Base,
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
    PaperTask,
    Task as DBTask,
)


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def register_math_functions(dbapi_connection, _connection_record):
    dbapi_connection.create_function("ln", 1, math.log)
    dbapi_connection.create_function("jsonb_typeof", 1, lambda _value: "array")


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def trending_catalog(client):
    """Papers 1-4 are recent, 5-12 fall in the baseline window.

    - Rising (task + method): papers 1, 2, 3 recent; 5, 6 baseline → lift 3.0
    - Steady (task + method): papers 4 recent; 7, 8 baseline → lift 1.0
    - Fading (task + method): no recent papers; 9-12 baseline
    """
    today = date.today()
    db = TestingSessionLocal()
    papers = [
        DBPaper(
            id=paper_id,
            title=f"Paper {paper_id}",
            abstract="Abstract",
            arxiv_id=f"2610.{paper_id:05d}",
            version="v1",
            is_latest_version=True,
            date_published=today - timedelta(days=5 if paper_id <= 4 else 60),
        )
        for paper_id in range(1, 13)
    ]
    db.add_all(papers)
    db.add_all(
        [
            DBTask(id=1, name="Rising Task", slug="rising-task", level=0, area_id=None),
            DBTask(id=2, name="Steady Task", slug="steady-task", level=0),
            DBTask(id=3, name="Fading Task", slug="fading-task", level=1),
            DBMethod(id=1, name="Rising Method", slug="rising-method"),
            DBMethod(id=2, name="Steady Method", slug="steady-method"),
            DBMethod(id=3, name="Fading Method", slug="fading-method"),
        ]
    )
    db.commit()
    links = {1: [1, 2, 3, 5, 6], 2: [4, 7, 8], 3: [9, 10, 11, 12]}
    for entity_id, paper_ids in links.items():
        db.add_all(PaperTask(paper_id=p, task_id=entity_id) for p in paper_ids)
        db.add_all(PaperMethod(paper_id=p, method_id=entity_id) for p in paper_ids)
    db.commit()
    db.close()


LOOSE_GATES = "min_recent_papers=1&min_baseline_papers=1&min_share_lift=0"


def test_trending_methods_rank_by_share_lift(client, trending_catalog):
    response = client.get(f"/api/v1/methods/trending?{LOOSE_GATES}")

    assert response.status_code == 200
    body = response.json()
    assert (body["recent_days"], body["baseline_days"]) == (30, 180)
    assert [m["slug"] for m in body["results"]] == ["rising-method", "steady-method"]
    rising = body["results"][0]
    assert rising["id"] == "1"
    assert (rising["recent_paper_count"], rising["baseline_paper_count"]) == (3, 2)
    # (3 / 4 recent) / (2 / 8 baseline)
    assert rising["share_lift"] == pytest.approx(3.0)
    assert rising["trend_score"] == pytest.approx(3.0 * math.log(4))


def test_trending_methods_apply_default_support_gates(client, trending_catalog):
    response = client.get("/api/v1/methods/trending")

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_trending_methods_route_is_not_shadowed_by_method_lookup(
    client, trending_catalog
):
    response = client.get(f"/api/v1/methods/trending?limit=1&{LOOSE_GATES}")

    assert response.status_code == 200
    assert [m["name"] for m in response.json()["results"]] == ["Rising Method"]


def test_trending_tasks_keep_ranking_and_level_filter(client, trending_catalog):
    response = client.get(f"/api/v1/tasks/trending?{LOOSE_GATES}")

    assert response.status_code == 200
    results = response.json()["results"]
    assert [t["slug"] for t in results] == ["rising-task", "steady-task"]
    assert results[0]["paper_count"] == 5
    assert results[0]["share_lift"] == pytest.approx(3.0)

    level_one = client.get(f"/api/v1/tasks/trending?level=1&{LOOSE_GATES}")
    assert level_one.json()["results"] == []


def test_trending_ignores_external_papers(client, trending_catalog):
    # A bulk external backfill in the baseline window must not dilute shares.
    db = TestingSessionLocal()
    db.add_all(
        DBPaper(
            id=paper_id,
            title=f"External {paper_id}",
            source="external",
            source_url=f"https://example.com/{paper_id}",
            is_latest_version=True,
            date_published=date.today() - timedelta(days=60),
        )
        for paper_id in range(100, 140)
    )
    db.commit()
    db.close()

    response = client.get(f"/api/v1/tasks/trending?{LOOSE_GATES}")

    assert response.json()["results"][0]["share_lift"] == pytest.approx(3.0)
