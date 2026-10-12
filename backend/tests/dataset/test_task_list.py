"""Focused contracts for the dataset task-list projection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import (
    Area,
    Base,
    Dataset,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.utils.auth import require_catalog_mutator, require_fresh_catalog_mutator
from backend.utils.exceptions import DatabaseError


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _register_jsonb_typeof(dbapi_connection, _connection_record):
    dbapi_connection.create_function("jsonb_typeof", 1, lambda _value: "array")


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _database_override():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add(Area(id=7, name="Vision"))
    db.add_all(
        [
            Dataset(id=10, name="Mixed Dataset", slug="Mixed-Slug"),
            Dataset(id=11, name="Empty Dataset", slug="empty-dataset"),
        ]
    )
    db.add(Metric(id=1, name="Accuracy", direction="higher_is_better"))
    db.add(TaskDatasetMetric(task_id=1, dataset_id=10, metric_id=1))
    db.add_all(
        [
            Task(id=90, name="Parent Task", slug="parent-task", level=0),
            Task(
                id=1,
                name="Alpha Task",
                slug="alpha-task",
                description="Alpha description",
                keywords="alpha,task",
                level=0,
                image_url="https://example.test/alpha.png",
                image_credit="Example",
            ),
            Task(
                id=2,
                name="Zulu Task",
                slug="zulu-task",
                parent_id=90,
                area_id=7,
                level=1,
                research_trends=["This field used to default in this response."],
            ),
            Task(id=3, name="Paper Only Task", slug="paper-only", level=0),
        ]
    )
    db.add_all(
        Paper(
            id=paper_id,
            title=f"Paper {paper_id}",
            arxiv_id=f"2608.{paper_id:05d}",
            version="v1",
            is_latest_version=True,
        )
        for paper_id in range(1, 4)
    )
    db.add_all(
        [
            TaskDataset(task_id=1, dataset_id=10),
            TaskDataset(task_id=2, dataset_id=10),
            PaperTask(paper_id=1, task_id=1),
            PaperTask(paper_id=2, task_id=1),
            PaperTask(paper_id=3, task_id=3),
        ]
    )
    db.commit()
    db.close()

    app = create_app()
    app.dependency_overrides[get_database_session] = _database_override
    app.dependency_overrides[require_catalog_mutator] = lambda: {"role": "admin"}
    app.dependency_overrides[require_fresh_catalog_mutator] = lambda: {"role": "admin"}
    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


def _selects_during(request):
    statements: list[str] = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = request()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return response, statements


def test_numeric_dataset_task_list_is_one_grouped_query(client):
    response, statements = _selects_during(
        lambda: client.get("/api/v1/datasets/10/tasks/")
    )

    assert response.status_code == 200
    assert len(statements) == 1
    assert response.json()["count"] == 2
    assert [task["name"] for task in response.json()["results"]] == [
        "Alpha Task",
        "Zulu Task",
    ]
    assert [task["paper_count"] for task in response.json()["results"]] == [2, 0]


def test_dataset_task_list_preserves_fields_defaults_and_membership(client):
    response = client.get("/api/v1/datasets/10/tasks/")

    assert response.status_code == 200
    alpha, zulu = response.json()["results"]
    assert set(zulu) == {
        "id",
        "name",
        "description",
        "research_trends",
        "slug",
        "keywords",
        "parent_id",
        "area_id",
        "level",
        "paper_count",
        "benchmark_count",
        "evaluation_count",
        "image_url",
        "image_credit",
        "created_at",
        "updated_at",
    }
    assert alpha | {"created_at": None, "updated_at": None} == {
        "id": "1",
        "name": "Alpha Task",
        "description": "Alpha description",
        "research_trends": [],
        "slug": "alpha-task",
        "keywords": "alpha,task",
        "parent_id": None,
        "area_id": None,
        "level": 0,
        "paper_count": 2,
        "benchmark_count": None,
        "evaluation_count": None,
        "image_url": "https://example.test/alpha.png",
        "image_credit": "Example",
        "created_at": None,
        "updated_at": None,
    }
    assert zulu["id"] == "2"
    assert zulu["parent_id"] == "90"
    assert zulu["area_id"] == "7"
    assert zulu["paper_count"] == 0
    assert zulu["research_trends"] == []
    assert all(task["name"] != "Paper Only Task" for task in (alpha, zulu))
    assert isinstance(alpha["paper_count"], int)
    assert isinstance(alpha["created_at"], str)
    assert isinstance(alpha["updated_at"], str)


def test_dataset_slug_resolution_is_case_insensitive_and_bounded(client):
    response, statements = _selects_during(
        lambda: client.get("/api/v1/datasets/mIxEd-sLuG/tasks/")
    )

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert len(statements) == 2


def test_missing_slug_and_numeric_id_preserve_distinct_behavior(client):
    missing_slug = client.get("/api/v1/datasets/not-a-dataset/tasks/")
    missing_numeric = client.get("/api/v1/datasets/999/tasks/")

    assert missing_slug.status_code == 404
    assert missing_slug.json() == {
        "detail": "Dataset with slug 'not-a-dataset' not found"
    }
    assert missing_numeric.status_code == 200
    assert missing_numeric.json() == {"count": 0, "results": []}


def test_existing_dataset_without_task_membership_returns_empty_list(client):
    response = client.get("/api/v1/datasets/empty-dataset/tasks/")

    assert response.status_code == 200
    assert response.json() == {"count": 0, "results": []}


def test_legacy_dataset_task_id_contract_remains_a_list_of_ints(client):
    with TestingSessionLocal() as db:
        task_ids = DatasetService(db).get_dataset_tasks(10)

    assert set(task_ids) == {1, 2}
    assert all(isinstance(task_id, int) for task_id in task_ids)


def test_leaderboard_metric_route_preserves_success_validation_and_not_found_contracts(
    client,
):
    success = client.get("/api/v1/datasets/10/tasks/1/metrics")
    invalid = client.get("/api/v1/datasets/not-an-id/tasks/1/metrics")
    missing = client.get("/api/v1/datasets/10/tasks/999/metrics")

    assert success.status_code == 200
    assert success.json()["metrics"][0]["metric_name"] == "Accuracy"
    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "Invalid dataset or task ID. Must be integers."}
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Task with ID 999 not found"}


def test_leaderboard_metric_duplicate_preserves_conflict_contract(client):
    response = client.post(
        "/api/v1/datasets/10/tasks/1/metrics", json={"metric_name": "Accuracy"}
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Metric 'Accuracy' is already linked to leaderboard (task 1, dataset 10)"
    }


def test_dataset_persistence_error_uses_central_error_translation(client, monkeypatch):
    def fail(*_args, **_kwargs):
        raise SQLAlchemyError("unavailable")

    monkeypatch.setattr(Session, "query", fail)

    response = client.get("/api/v1/datasets/10")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def test_dataset_evaluation_persistence_error_preserves_detail_only_contract(
    client, monkeypatch
):
    def fail(*_args, **_kwargs):
        raise DatabaseError("Failed to retrieve evaluations: unavailable")

    monkeypatch.setattr(EvaluationService, "get_evaluations", fail)

    response = client.get("/api/v1/datasets/10/evaluations/")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
