from datetime import date
from decimal import Decimal
from typing import get_args, get_origin

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.routers import papers as papers_router
from backend.services.paper_service import PaperService
from backend.services.thumbnail_service import ThumbnailService
from backend.utils.exceptions import DatabaseError


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _RepositoryTrendingDatabase:
    def __init__(self):
        self.executions = []

    def execute(self, statement, parameters):
        sql = str(statement)
        self.executions.append((sql, dict(parameters)))
        if "FROM paper_tasks" in sql:
            return _Rows(
                [
                    (501, "Image Classification", "image-classification"),
                    (501, "Representation Learning", "representation-learning"),
                ]
            )
        if "FROM paper_authors" in sql:
            return _Rows([(501, "Ada Lovelace"), (501, "Grace Hopper")])
        return _Rows(
            [
                (
                    501,
                    None,
                    "Typed repository trending paper",
                    date(2026, 8, 9),
                    601,
                    "https://github.com/example/typed",
                    "example",
                    "typed",
                    900,
                    Decimal("1.5"),
                    Decimal("3.25"),
                    36,
                    Decimal("1"),
                    "Typed abstract",
                    "external",
                    "https://example.com/typed-report",
                    "https://cdn.example.com/typed-thumbnail.jpg",
                    "v7",
                    True,
                    3,
                )
            ]
        )


@pytest.fixture
def trending_client():
    app = create_app()
    state = {}

    def override_get_database_session():
        yield state["db"]

    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as client:
        yield app, client, state
    app.dependency_overrides.clear()


def _route(app):
    return next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/papers/trending"
    )


def _response_row():
    return {
        "paper_id": "701",
        "arxiv_id": None,
        "source": "external",
        "source_url": "https://example.com/router-paper",
        "title": "Router paper",
        "abstract": None,
        "authors": [],
        "date_published": date(2026, 8, 10),
        "thumbnail_url": None,
        "tasks": [],
        "repository": {
            "id": "801",
            "url": "https://github.com/example/router-paper",
            "owner": "example",
            "name": "router-paper",
            "num_stars": 10,
        },
        "trending": {
            "velocity_24h": 1.0,
            "trending_score": 2.0,
            "stars_gained_24h": 24,
        },
        "paper_age_days": 0.0,
        "has_official_implementation": True,
        "code_repository_count": 1,
    }


def test_trending_route_declares_exact_typed_response_shape():
    app = create_app()
    route = _route(app)

    assert get_origin(route.response_model) is list
    response_model = get_args(route.response_model)[0]
    assert issubclass(response_model, BaseModel)
    assert list(response_model.model_fields) == [
        "paper_id",
        "arxiv_id",
        "source",
        "source_url",
        "title",
        "abstract",
        "authors",
        "date_published",
        "thumbnail_url",
        "tasks",
        "repository",
        "trending",
        "paper_age_days",
        "has_official_implementation",
        "code_repository_count",
    ]
    assert all(field.is_required() for field in response_model.model_fields.values())

    task_model = get_args(response_model.model_fields["tasks"].annotation)[0]
    repository_model = response_model.model_fields["repository"].annotation
    score_model = response_model.model_fields["trending"].annotation
    assert list(task_model.model_fields) == ["name", "slug"]
    assert list(repository_model.model_fields) == [
        "id",
        "url",
        "owner",
        "name",
        "num_stars",
    ]
    assert list(score_model.model_fields) == [
        "velocity_24h",
        "trending_score",
        "stars_gained_24h",
    ]
    for nested_model in (task_model, repository_model, score_model):
        assert all(field.is_required() for field in nested_model.model_fields.values())


def test_repository_trending_service_owns_query_policy_and_returns_models(monkeypatch):
    db = _RepositoryTrendingDatabase()

    def unexpected_external_lookup(_service, _paper_id):
        pytest.fail("an explicit thumbnail must bypass external thumbnail lookup")

    monkeypatch.setattr(
        ThumbnailService,
        "get_external_thumbnail_url",
        unexpected_external_lookup,
    )

    result = PaperService(db).get_repository_trending_papers(
        limit=7,
        max_age_days=42,
        min_velocity=1.5,
    )

    assert len(result) == 1
    assert isinstance(result[0], BaseModel)
    assert result[0].model_dump(mode="json") == {
        "paper_id": "501",
        "arxiv_id": None,
        "source": "external",
        "source_url": "https://example.com/typed-report",
        "title": "Typed repository trending paper",
        "abstract": "Typed abstract",
        "authors": ["Ada Lovelace", "Grace Hopper"],
        "date_published": "2026-08-09",
        "thumbnail_url": "https://cdn.example.com/typed-thumbnail.jpg",
        "tasks": [
            {"name": "Image Classification", "slug": "image-classification"},
            {
                "name": "Representation Learning",
                "slug": "representation-learning",
            },
        ],
        "repository": {
            "id": "601",
            "url": "https://github.com/example/typed",
            "owner": "example",
            "name": "typed",
            "num_stars": 900,
        },
        "trending": {
            "velocity_24h": 1.5,
            "trending_score": 3.25,
            "stars_gained_24h": 36,
        },
        "paper_age_days": 1.0,
        "has_official_implementation": True,
        "code_repository_count": 3,
    }

    assert len(db.executions) == 3
    assert db.executions[0][1] == {
        "limit": 7,
        "max_age_days": 42,
        "min_velocity": 1.5,
    }
    assert db.executions[1][1] == {"paper_ids": [501]}
    assert db.executions[2][1] == {"paper_ids": [501]}

    ranked_sql = " ".join(db.executions[0][0].split())
    assert "FROM trending_papers_24h tp" in ranked_sql
    assert "JOIN papers p ON p.id = tp.paper_id" in ranked_sql
    assert "tp.paper_age_days <= :max_age_days" in ranked_sql
    assert "COALESCE(tp.velocity_24h, 0) >= :min_velocity" in ranked_sql
    assert "PARTITION BY tp.paper_id" in ranked_sql
    assert "paper_repo_rank = 1" in ranked_sql
    assert "PARTITION BY repository_id" in ranked_sql
    assert "repo_paper_rank = 1" in ranked_sql
    assert "p.version" in ranked_sql
    assert (
        "ORDER BY trending_score DESC NULLS LAST, current_stars DESC LIMIT :limit"
        in ranked_sql
    )


def test_trending_router_delegates_filters_and_serializes_typed_result(
    trending_client, monkeypatch
):
    _app, client, state = trending_client
    state["db"] = database = object()
    calls = []

    class FakePaperService:
        def __init__(self, db):
            assert db is database

        def get_repository_trending_papers(
            self,
            limit,
            max_age_days,
            min_velocity,
        ):
            calls.append((limit, max_age_days, min_velocity))
            return [_response_row()]

    monkeypatch.setattr(papers_router, "PaperService", FakePaperService)

    response = client.get(
        "/api/v1/papers/trending",
        params={"limit": 7, "max_age_days": 42, "min_velocity": 1.25},
    )

    assert response.status_code == 200
    assert calls == [(7, 42, 1.25)]
    expected = _response_row()
    expected["date_published"] = "2026-08-10"
    assert response.json() == [expected]


def test_trending_router_translates_database_error(trending_client, monkeypatch):
    _app, client, state = trending_client
    state["db"] = object()

    class FailingPaperService:
        def __init__(self, _db):
            pass

        def get_repository_trending_papers(self, **_kwargs):
            raise DatabaseError("database unavailable")

    monkeypatch.setattr(papers_router, "PaperService", FailingPaperService)

    response = client.get("/api/v1/papers/trending")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
