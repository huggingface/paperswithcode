"""Tests for the task "Start here" reading path endpoint."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import create_app
from backend.database.connection import get_database_session
from backend.models.database import (
    Base,
    Paper as DBPaper,
    PaperTask,
    Task as DBTask,
    TaskReadingPathPaper,
)
from backend.services import reading_path_service


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


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
def register_jsonb_typeof(dbapi_connection, _connection_record):
    dbapi_connection.create_function("jsonb_typeof", 1, lambda _value: "array")


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TODAY = date.today()


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    reading_path_service._cache.clear()
    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as test_client:
        seed(TestingSessionLocal())
        yield test_client
    app.dependency_overrides.clear()
    reading_path_service._cache.clear()
    Base.metadata.drop_all(bind=engine)


def paper(paper_id, title, *, age_days, citations, task_id, latest=True, arxiv_id=None):
    return [
        DBPaper(
            id=paper_id,
            arxiv_id=arxiv_id or f"2401.{paper_id:05d}",
            version="v2" if latest else "v1",
            title=title,
            abstract="Abstract.",
            date_published=TODAY - timedelta(days=age_days),
            citation_count=citations,
            is_latest_version=latest,
        ),
        PaperTask(paper_id=paper_id, task_id=task_id),
    ]


def seed(db):
    db.add_all(
        [
            DBTask(id=1, name="Object Detection", slug="object-detection", level=0),
            DBTask(id=2, name="Point Tracking", slug="point-tracking", level=0),
            DBTask(id=3, name="Empty Task", slug="empty-task", level=0),
        ]
    )
    rows = [
        *paper(1, "A Survey of Image Models", age_days=2000, citations=900, task_id=1),
        *paper(2, "Object Detection: A Review", age_days=1500, citations=50, task_id=1),
        *paper(3, "Old Detector", age_days=4000, citations=5000, task_id=1),
        *paper(4, "Older Detector", age_days=4500, citations=4000, task_id=1),
        *paper(5, "Preview Detector", age_days=3000, citations=3000, task_id=1),
        *paper(6, "Small Detector", age_days=3500, citations=10, task_id=1),
        *paper(7, "New Detector", age_days=30, citations=1, task_id=1),
        *paper(
            8,
            "Superseded Survey",
            age_days=2000,
            citations=9999,
            task_id=1,
            latest=False,
        ),
        *paper(20, "Tracker Foundations", age_days=2000, citations=300, task_id=2),
        *paper(21, "Tracker Classic", age_days=20, citations=200, task_id=2),
        *paper(
            23,
            "Tracker Classic (old version)",
            age_days=20,
            citations=200,
            task_id=2,
            latest=False,
            arxiv_id="2401.00021",
        ),
        *paper(22, "Tracker Now", age_days=10, citations=0, task_id=2),
    ]
    db.add_all(rows)
    db.flush()
    db.add_all(
        [
            TaskReadingPathPaper(
                task_id=2, paper_id=23, step="foundations", position=1, note="Second."
            ),
            TaskReadingPathPaper(
                task_id=2, paper_id=20, step="foundations", position=0, note="First."
            ),
        ]
    )
    db.commit()
    db.close()


def titles(step):
    return [entry["paper"]["title"] for entry in step["papers"]]


def test_automatic_path_picks_survey_foundations_and_recent(client):
    response = client.get("/api/v1/tasks/object-detection/reading-path")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "automatic"
    assert body["task_slug"] == "object-detection"
    steps = {step["kind"]: step for step in body["steps"]}
    assert [step["kind"] for step in body["steps"]] == [
        "overview",
        "foundations",
        "recent",
    ]
    assert titles(steps["overview"]) == ["Object Detection: A Review"]
    assert titles(steps["foundations"]) == [
        "Old Detector",
        "Older Detector",
        "Preview Detector",
    ]
    assert titles(steps["recent"]) == ["New Detector"]
    assert all(step["source"] == "automatic" for step in body["steps"])
    assert steps["foundations"]["papers"][0]["paper"]["arxiv_id"] == "2401.00003"
    assert steps["foundations"]["papers"][0]["note"] is None


def test_curated_steps_keep_order_and_notes_and_fill_the_rest(client):
    """Paper 23 is a superseded version of 21: show 21 once, never again in recent."""
    response = client.get("/api/v1/tasks/2/reading-path")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "curated"
    steps = {step["kind"]: step for step in body["steps"]}
    assert "overview" not in steps
    assert steps["foundations"]["source"] == "curated"
    assert titles(steps["foundations"]) == ["Tracker Foundations", "Tracker Classic"]
    assert [entry["note"] for entry in steps["foundations"]["papers"]] == [
        "First.",
        "Second.",
    ]
    assert steps["recent"]["source"] == "automatic"
    assert titles(steps["recent"]) == ["Tracker Now"]


def test_task_without_papers_has_no_steps(client):
    response = client.get("/api/v1/tasks/empty-task/reading-path")

    assert response.status_code == 200
    assert response.json()["steps"] == []


def test_unknown_task_is_not_found(client):
    response = client.get("/api/v1/tasks/no-such-task/reading-path")

    assert response.status_code == 404
