"""Tests for the Methods API endpoints.

Focused regression coverage for name-only `/api/v1/methods/?q=...` search.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import create_app
from backend.models.database import (
    Base,
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
)
from backend.database.connection import get_database_session
from backend.config import get_settings


# Trending scores older than 24h are treated as missing, so test repos/papers
# stamp a fresh timestamp to be eligible for the trending sort.
_FRESH = datetime.now(timezone.utc)
_STALE = datetime.now(timezone.utc) - timedelta(hours=48)


def _pin_trending_mode(monkeypatch, mode: str) -> None:
    """Force the active trending ranking mode for a test, regardless of env."""
    monkeypatch.setattr(get_settings(), "trending_ranking_mode", mode)


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def register_jsonb_typeof(dbapi_connection, _connection_record):
    """Let SQLite create PostgreSQL JSONB check constraints in this test DB."""
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
def methods_with_image_keyword():
    """Methods where 'image' appears in different fields.

    Layout:
      - Image GPT: name prefix match
      - Image Transformer: name prefix match
      - DALL-E: full_name contains "image" ("Discrete VAE for image generation")
      - Convolutional Network: description-only match ("operates on images")
      - Transformer: no match at all
    """
    db = TestingSessionLocal()

    methods = [
        DBMethod(
            id=1,
            name="Image GPT",
            slug="image-gpt",
            full_name="Image Generative Pretraining",
            description="Autoregressive pixel modeling.",
        ),
        DBMethod(
            id=2,
            name="Image Transformer",
            slug="image-transformer",
            full_name=None,
            description="Self-attention over pixel grids.",
        ),
        DBMethod(
            id=3,
            name="DALL-E",
            slug="dall-e",
            full_name="Discrete VAE for image generation",
            description="Text-to-art generative model.",
        ),
        DBMethod(
            id=4,
            name="Convolutional Network",
            slug="convolutional-network",
            full_name=None,
            description="Operates on images using shared filters.",
        ),
        DBMethod(
            id=5,
            name="Transformer",
            slug="transformer",
            full_name="Self-Attention Transformer",
            description="Sequence-to-sequence with self-attention.",
        ),
    ]
    db.add_all(methods)
    db.commit()
    db.close()


def test_methods_search_uses_displayed_name_only(client, methods_with_image_keyword):
    """Partial queries do not retrieve full-name or description-only matches."""
    response = client.get("/api/v1/methods/?q=image&page_size=20")

    assert response.status_code == 200
    data = response.json()

    names = [m["name"] for m in data["results"]]

    assert names[:2] == ["Image GPT", "Image Transformer"]

    assert "DALL-E" not in names
    assert "Convolutional Network" not in names
    assert "Transformer" not in names


def test_methods_expose_recent_usage_trend_score(client):
    """Method activity mirrors benchmark trends using paper publication dates."""
    db = TestingSessionLocal()
    today = datetime.now(timezone.utc).date()
    methods = [
        DBMethod(id=20, name="Rising Method", slug="rising-method"),
        DBMethod(id=21, name="Quiet Method", slug="quiet-method"),
    ]
    papers = [
        DBPaper(
            id=100 + index,
            title=f"Method usage {index}",
            abstract="Abstract",
            arxiv_id=f"2607.{index:05d}",
            version="v1",
            is_latest_version=is_latest,
            date_published=today - timedelta(days=days_ago),
        )
        for index, (days_ago, is_latest) in enumerate(
            [
                (10, True),
                (30, True),
                (80, True),
                (100, True),
                (200, True),
                (20, False),
                (15, True),
            ],
            start=1,
        )
    ]
    db.add_all(methods)
    db.add_all(papers)
    db.flush()
    db.add_all(
        [PaperMethod(paper_id=paper.id, method_id=20) for paper in papers[:6]]
        + [PaperMethod(paper_id=papers[6].id, method_id=21)]
    )
    db.commit()
    db.close()

    response = client.get("/api/v1/methods/?ordering=-trend_score&page_size=20")

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["name"] for item in results[:2]] == [
        "Rising Method",
        "Quiet Method",
    ]
    rising = results[0]
    assert rising["recent_paper_count"] == 3
    assert rising["baseline_paper_count"] == 2
    assert rising["trend_score"] == 1.0
    assert rising["rate_change"] == 3.0

    trend_response = client.get("/api/v1/methods/rising-method/trend?history_months=12")
    assert trend_response.status_code == 200
    trend = trend_response.json()
    assert trend["signal"] == "paper_method_links"
    assert trend["recent_paper_count"] == 3
    assert trend["baseline_paper_count"] == 2
    assert trend["trend_score"] == 1.0
    assert trend["rate_change"] == 3.0
    assert len(trend["history"]) == 12
    assert "catalog_paper_count" in trend["history"][0]
    assert "catalog_share" in trend["history"][0]
    assert trend["undated_paper_count"] == 0
    assert trend["history_complete"] is True
    assert trend["comparison_complete"] is True
    assert sum(point["paper_count"] for point in trend["history"]) == 5

    index_response = client.get("/api/v1/methods/index/cards")
    assert index_response.status_code == 200
    index_results = index_response.json()["results"]
    assert [item["name"] for item in index_results[:2]] == [
        "Rising Method",
        "Quiet Method",
    ]
    assert index_results[0] == {
        "id": "20",
        "name": "Rising Method",
        "slug": "rising-method",
        "area_id": None,
        "introduced_year": None,
        "paper_count": 6,
        "trend_score": 1.0,
    }


@pytest.fixture
def method_with_trending_papers():
    """Create one method with papers covering each trending edge case.

    Layout (all linked to method `transformer`):
      - Paper 1: official repo, trending_score=10.0 (highest score)
      - Paper 2: official repo, trending_score=2.5
      - Paper 3: official repo, trending_score=NULL (no fresh score)
      - Paper 4: non-official repo with trending_score=99.0 (must NOT win;
                 only official repos contribute to trending sort)
      - Paper 5: no repository at all
    """
    db = TestingSessionLocal()

    method = DBMethod(
        id=1,
        name="Transformer",
        slug="transformer",
        full_name="Self-Attention Transformer",
    )
    db.add(method)

    papers = [
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2025.0{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 6)
    ]
    db.add_all(papers)

    repositories = [
        DBRepository(
            id=1,
            url="https://github.com/owner/repo-1",
            owner="owner",
            name="repo-1",
            num_stars=500,
            trending_score=10.0,
            trending_score_updated_at=_FRESH,
        ),
        DBRepository(
            id=2,
            url="https://github.com/owner/repo-2",
            owner="owner",
            name="repo-2",
            num_stars=200,
            trending_score=2.5,
            trending_score_updated_at=_FRESH,
        ),
        DBRepository(
            id=3,
            url="https://github.com/owner/repo-3",
            owner="owner",
            name="repo-3",
            num_stars=50,
            trending_score=None,
        ),
        DBRepository(
            id=4,
            url="https://github.com/owner/repo-4",
            owner="owner",
            name="repo-4",
            num_stars=10000,
            trending_score=99.0,
            trending_score_updated_at=_FRESH,
        ),
    ]
    db.add_all(repositories)
    db.commit()

    db.add_all(
        [PaperMethod(paper_id=i, method_id=1) for i in range(1, 6)]
        + [
            DBPaperRepository(paper_id=1, repository_id=1, is_official=True),
            DBPaperRepository(paper_id=2, repository_id=2, is_official=True),
            DBPaperRepository(paper_id=3, repository_id=3, is_official=True),
            DBPaperRepository(paper_id=4, repository_id=4, is_official=False),
        ]
    )
    db.commit()
    db.close()


def test_method_papers_trending_orders_by_official_repo_trending_score(
    client, method_with_trending_papers, monkeypatch
):
    """`order_by=trending` ranks method papers by their best official repo score."""
    _pin_trending_mode(monkeypatch, "github")
    response = client.get(
        "/api/v1/methods/transformer/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200
    data = response.json()

    titles = [paper["title"] for paper in data["results"]]

    # Papers 1 and 2 have official trending scores (10.0 and 2.5) and must
    # come first, in that order. The remaining three papers have no
    # qualifying official trending score and follow.
    assert titles[:2] == ["Paper 1", "Paper 2"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4", "Paper 5"}
    assert data["count"] == 5


def test_method_papers_trending_ignores_non_official_repos(
    client, method_with_trending_papers, monkeypatch
):
    """A non-official repository's trending score must not influence ordering.

    Paper 4's only repo has `trending_score=99.0` but is not official, so it
    must not outrank Paper 1 (`trending_score=10.0` via official repo).
    """
    _pin_trending_mode(monkeypatch, "github")
    response = client.get(
        "/api/v1/methods/transformer/papers?order_by=trending&page_size=10"
    )

    titles = [paper["title"] for paper in response.json()["results"]]

    assert titles.index("Paper 1") < titles.index("Paper 4")


def test_method_papers_default_ordering_unchanged(client, method_with_trending_papers):
    """Default ordering (date_published desc) is unaffected by trending logic."""
    response = client.get("/api/v1/methods/transformer/papers?page_size=10")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert {paper["title"] for paper in data["results"]} == {
        f"Paper {i}" for i in range(1, 6)
    }


@pytest.fixture
def method_with_composite_trending_papers():
    """Papers exercising composite (paper-level) trending for a single method.

    All linked to method `transformer`:
      - Paper 1: papers.trending_score=80 (fresh), official repo velocity 1.0
      - Paper 2: papers.trending_score=40 (fresh), official repo velocity 50.0
      - Paper 3: papers.trending_score=99 but STALE (must be ignored)
      - Paper 4: no paper-level trending_score

    Paper 1 must outrank Paper 2 by its higher *paper* score even though
    Paper 2's repo velocity is far higher, proving composite mode ranks by
    `papers.trending_score`, not official-repo velocity.
    """
    db = TestingSessionLocal()

    method = DBMethod(id=1, name="Transformer", slug="transformer")
    db.add(method)

    paper_scores = {1: (80.0, _FRESH), 2: (40.0, _FRESH), 3: (99.0, _STALE), 4: None}
    papers = []
    for i in range(1, 5):
        score = paper_scores[i]
        papers.append(
            DBPaper(
                id=i,
                title=f"Paper {i}",
                abstract=f"Abstract {i}",
                arxiv_id=f"2025.1{i:04d}",
                version="v1",
                is_latest_version=True,
                trending_score=score[0] if score else None,
                trending_score_updated_at=score[1] if score else None,
            )
        )
    db.add_all(papers)

    repositories = [
        DBRepository(
            id=1,
            url="https://github.com/owner/repo-1",
            owner="owner",
            name="repo-1",
            num_stars=100,
            trending_score=1.0,
            trending_score_updated_at=_FRESH,
        ),
        DBRepository(
            id=2,
            url="https://github.com/owner/repo-2",
            owner="owner",
            name="repo-2",
            num_stars=100,
            trending_score=50.0,
            trending_score_updated_at=_FRESH,
        ),
    ]
    db.add_all(repositories)
    db.commit()

    db.add_all(
        [PaperMethod(paper_id=i, method_id=1) for i in range(1, 5)]
        + [
            DBPaperRepository(paper_id=1, repository_id=1, is_official=True),
            DBPaperRepository(paper_id=2, repository_id=2, is_official=True),
        ]
    )
    db.commit()
    db.close()


def test_method_papers_trending_composite_ranks_by_paper_score(
    client, method_with_composite_trending_papers, monkeypatch
):
    """In composite mode, method papers rank by `papers.trending_score`."""
    _pin_trending_mode(monkeypatch, "composite")
    response = client.get(
        "/api/v1/methods/transformer/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200
    data = response.json()
    titles = [paper["title"] for paper in data["results"]]

    # Paper 1 (score 80) and Paper 2 (score 40) lead in that order; the stale
    # and unscored papers follow without being dropped.
    assert titles[:2] == ["Paper 1", "Paper 2"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4"}
    assert data["count"] == 4


if __name__ == "__main__":
    pytest.main([__file__])
