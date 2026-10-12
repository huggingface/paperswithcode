"""GET /papers/{id}/repositories serializes the declared Repository contract."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.main import create_app


class _FakeQuery:
    def __init__(self, first=None, rows=()):
        self._first = first
        self._rows = list(rows)

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, paper_exists, rows=()):
        self._queries = [
            _FakeQuery(first=(109353,) if paper_exists else None),
            _FakeQuery(rows=rows),
        ]

    def query(self, *_args, **_kwargs):
        return self._queries.pop(0)


def _client(session):
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: session
    return TestClient(app)


def test_paper_repositories_returns_repository_objects():
    stamp = datetime(2026, 10, 12, 14, 17, tzinfo=timezone.utc)
    repository = SimpleNamespace(
        id=175516,
        url="https://github.com/zero-4869/confidencemattersgs",
        owner="Zero-4869",
        name="ConfidenceMattersGS",
        num_stars=11,
        source="ai_extraction",
        trending_score=Decimal("0.2500"),
        trending_score_updated_at=stamp,
        created_at=stamp,
        updated_at=stamp,
    )

    with _client(_FakeSession(True, rows=[(True, repository)])) as client:
        response = client.get("/api/v1/papers/109353/repositories")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "175516",
            "url": "https://github.com/zero-4869/confidencemattersgs",
            "owner": "Zero-4869",
            "name": "ConfidenceMattersGS",
            "num_stars": 11,
            "is_official": True,
            "source": "ai_extraction",
            "trending_score": 0.25,
            "trending_score_updated_at": "2026-10-12T14:17:00Z",
            "created_at": "2026-10-12",
            "updated_at": "2026-10-12",
        }
    ]


def test_paper_repositories_missing_paper_is_404():
    with _client(_FakeSession(False)) as client:
        response = client.get("/api/v1/papers/999999999/repositories")

    assert response.status_code == 404
