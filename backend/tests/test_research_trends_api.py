"""Tests for the public research trends API."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.api import TrendPoint, TrendsResponse
from backend.services.research_trends_service import ResearchTrendsService
from backend.utils.exceptions import DatabaseError


class FakeMappings:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.params = None

    def execute(self, _query, params):
        if self.error:
            raise self.error
        self.params = params
        return FakeMappings(self.rows)


def test_service_builds_ordered_series_with_separate_start_dates():
    db = FakeSession(
        [
            {
                "month": date(2019, 1, 1),
                "paper_count": 3,
                "official_code_count": 1,
                "hf_artifact_count": 2,
            },
            {
                "month": date(2021, 1, 1),
                "paper_count": 8,
                "official_code_count": 3,
                "hf_artifact_count": 1,
            },
        ]
    )

    result = ResearchTrendsService(db).get_trends(today=date(2026, 7, 26))

    assert result == TrendsResponse(
        code_availability=[
            TrendPoint(month="2019-01", percent=33.3),
            TrendPoint(month="2021-01", percent=37.5),
        ],
        hf_artifacts=[TrendPoint(month="2021-01", percent=12.5)],
    )
    assert db.params == {
        "start_date": date(2019, 1, 1),
        "end_date": date(2026, 7, 1),
    }


def test_service_skips_empty_months():
    db = FakeSession(
        [
            {
                "month": date(2022, 2, 1),
                "paper_count": 0,
                "official_code_count": 0,
                "hf_artifact_count": 0,
            }
        ]
    )

    assert ResearchTrendsService(db).get_trends(
        today=date(2026, 7, 26)
    ) == TrendsResponse(code_availability=[], hf_artifacts=[])


def test_service_wraps_database_errors():
    with pytest.raises(DatabaseError, match="Failed to calculate research trends"):
        ResearchTrendsService(
            FakeSession(
                error=OperationalError("SELECT", {}, RuntimeError("unavailable"))
            )
        ).get_trends()


def test_trend_point_validates_public_contract():
    with pytest.raises(ValidationError):
        TrendPoint(month="2026-7", percent=10)
    with pytest.raises(ValidationError):
        TrendPoint(month="2026-07", percent=100.1)


def test_trends_endpoint_returns_typed_payload_and_cache_header(monkeypatch):
    expected = TrendsResponse(
        code_availability=[TrendPoint(month="2026-06", percent=61.2)],
        hf_artifacts=[TrendPoint(month="2026-06", percent=32.8)],
    )

    monkeypatch.setattr(
        ResearchTrendsService,
        "get_trends",
        lambda self: expected,
    )

    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: object()
    with TestClient(app) as client:
        response = client.get("/api/v1/stats/trends")

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    assert response.headers["cache-control"] == (
        "public, max-age=3600, stale-while-revalidate=86400"
    )
