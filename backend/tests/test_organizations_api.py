"""Tests for the Organizations API papers endpoint.

Focused coverage for `order_by=trending` on `/api/v1/organizations/{slug}/papers`,
ensuring organization feeds rank by the same active trending metric as the home
feed (composite paper-level score or official-repo velocity).
"""

import hashlib
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import (
    Area,
    Base,
    Organization,
    Paper as DBPaper,
    PaperOrganization,
    PaperRepository as DBPaperRepository,
    PaperTask,
    Repository as DBRepository,
    Task,
)
from backend.utils.auth import catalog_mutation_context


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
def _sqlite_jsonb_typeof(dbapi_connection, _connection_record):
    dbapi_connection.create_function(
        "jsonb_typeof",
        1,
        lambda value: "array" if str(value).lstrip().startswith("[") else "object",
    )


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Trending scores older than 24h are treated as missing, so test rows stamp a
# fresh timestamp to be eligible for the trending sort.
_FRESH = datetime.now(timezone.utc)
_STALE = datetime.now(timezone.utc) - timedelta(hours=48)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _pin_trending_mode(monkeypatch, mode: str) -> None:
    """Force the active trending ranking mode for a test, regardless of env."""
    monkeypatch.setattr(get_settings(), "trending_ranking_mode", mode)


@pytest.fixture
def org_client():
    """Organization `acme` whose papers carry both repo velocity and composite
    paper-level trending scores.

      - Paper 1: papers.trending_score=80 (fresh), official repo velocity 1.0
      - Paper 2: papers.trending_score=40 (fresh), official repo velocity 50.0
      - Paper 3: papers.trending_score=99 but STALE (must be ignored)
      - Paper 4: no paper-level trending_score, no repo
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    org = Organization(
        id=1,
        name="Acme",
        slug="acme",
        hf_slug="acme",
        is_featured=True,
        display_order=1,
        logo_data=b"fake-png",
        logo_mime_type="image/png",
        logo_sha256=hashlib.sha256(b"fake-png").hexdigest(),
    )
    db.add(org)
    db.add(Area(id=1, name="Vision"))
    db.add(
        Task(id=1, name="Image Classification", slug="image-classification", area_id=1)
    )

    specs = {
        1: (80.0, _FRESH),
        2: (40.0, _FRESH),
        3: (99.0, _STALE),
        4: (None, None),
    }
    for paper_id, (score, stamp) in specs.items():
        db.add(
            DBPaper(
                id=paper_id,
                title=f"Paper {paper_id}",
                abstract=f"Abstract {paper_id}",
                arxiv_id=f"2025.2{paper_id:04d}",
                version="v1",
                is_latest_version=True,
                source="arxiv",
                trending_score=score,
                trending_score_updated_at=stamp,
            )
        )
        db.add(
            PaperOrganization(
                paper_id=paper_id,
                organization_id=1,
                source="hf_org_papers",
            )
        )
        if paper_id in {1, 3}:
            db.add(PaperTask(paper_id=paper_id, task_id=1, source="manual"))

    repos = [
        DBRepository(
            id=1,
            url="https://github.com/owner/repo-1",
            owner="owner",
            name="repo-1",
            num_stars=100,
            trending_score=1.0,
            trending_score_updated_at=_FRESH,
            source="test",
        ),
        DBRepository(
            id=2,
            url="https://github.com/owner/repo-2",
            owner="owner",
            name="repo-2",
            num_stars=100,
            trending_score=50.0,
            trending_score_updated_at=_FRESH,
            source="test",
        ),
    ]
    db.add_all(repos)
    db.commit()
    db.add_all(
        [
            DBPaperRepository(paper_id=1, repository_id=1, is_official=True),
            DBPaperRepository(paper_id=2, repository_id=2, is_official=True),
        ]
    )
    db.commit()
    db.close()

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


def test_organization_papers_trending_composite_ranks_by_paper_score(
    org_client, monkeypatch
):
    """In composite mode, organization papers rank by `papers.trending_score`.

    Paper 1 (score 80) beats Paper 2 (score 40) despite Paper 2's much higher
    repo velocity, proving the paper-level score drives the order.
    """
    _pin_trending_mode(monkeypatch, "composite")
    response = org_client.get(
        "/api/v1/organizations/acme/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200, response.text
    data = response.json()
    titles = [paper["title"] for paper in data["results"]]

    assert titles[:2] == ["Paper 1", "Paper 2"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4"}
    assert data["count"] == 4


def test_paper_detail_includes_manually_curated_organization(org_client):
    db = TestingSessionLocal()
    try:
        link = (
            db.query(PaperOrganization)
            .filter(
                PaperOrganization.paper_id == 1,
                PaperOrganization.organization_id == 1,
            )
            .one()
        )
        link.source = "manual"
        db.commit()
    finally:
        db.close()

    response = org_client.get("/api/v1/papers/2025.20001")

    assert response.status_code == 200, response.text
    organizations = response.json()["organizations"]
    assert len(organizations) == 1
    assert organizations[0]["id"] == "1"
    assert organizations[0]["name"] == "Acme"
    assert organizations[0]["slug"] == "acme"
    assert organizations[0]["source"] == "manual"
    assert organizations[0]["added_by_hf_username"] is None

    organization = org_client.get("/api/v1/organizations/acme")
    assert organization.status_code == 200
    assert organization.json()["paper_count"] == 4
    feed = org_client.get("/api/v1/organizations/acme/papers?page_size=10")
    assert feed.status_code == 200
    assert feed.json()["count"] == 4
    assert feed.json()["results"][0]["organizations"][0]["slug"] == "acme"


def test_organization_update_preserves_hf_source_and_attributes_new_manual_link(
    org_client,
):
    db = TestingSessionLocal()
    try:
        db.add(Organization(id=2, name="Manual Lab", slug="manual-lab"))
        db.commit()
    finally:
        db.close()

    actor = {
        "source": "cookie",
        "hf_subject": "hf-user-123",
        "username": "curator",
        "role": "admin",
    }
    org_client.app.dependency_overrides[catalog_mutation_context] = lambda: {
        "actor": actor,
        "idempotency_key": None,
        "expected_version": None,
        "request_id": "organization-provenance-test",
    }
    try:
        response = org_client.put(
            "/api/v1/papers/1/organizations?organization_ids=1&organization_ids=2"
        )
    finally:
        org_client.app.dependency_overrides.pop(catalog_mutation_context, None)

    assert response.status_code == 200, response.text
    associations = {
        organization["slug"]: organization
        for organization in response.json()["organizations"]
    }
    assert associations["acme"]["source"] == "hf_org_papers"
    assert associations["acme"]["added_by_hf_username"] is None
    assert associations["manual-lab"]["source"] == "manual"
    assert associations["manual-lab"]["added_by_hf_username"] == "curator"

    db = TestingSessionLocal()
    try:
        acme = db.get(PaperOrganization, (1, 1))
        manual = db.get(PaperOrganization, (1, 2))
        assert acme.source == "hf_org_papers"
        assert manual.source == "manual"
        assert manual.added_by_hf_subject == "hf-user-123"
        assert manual.added_by_hf_username == "curator"
    finally:
        db.close()

    manual_feed = org_client.get("/api/v1/organizations/manual-lab/papers")
    assert manual_feed.status_code == 200
    assert manual_feed.json()["count"] == 1
    assert manual_feed.json()["results"][0]["title"] == "Paper 1"


def test_organization_papers_trending_github_ranks_by_repo_velocity(
    org_client, monkeypatch
):
    """In github mode, organization papers rank by official-repo velocity.

    Paper 2's repo velocity (50.0) now outranks Paper 1's (1.0), the inverse of
    composite mode.
    """
    _pin_trending_mode(monkeypatch, "github")
    response = org_client.get(
        "/api/v1/organizations/acme/papers?order_by=trending&page_size=10"
    )

    assert response.status_code == 200
    data = response.json()
    titles = [paper["title"] for paper in data["results"]]

    assert titles[:2] == ["Paper 2", "Paper 1"]
    assert set(titles[2:]) == {"Paper 3", "Paper 4"}
    assert data["count"] == 4


def test_featured_list_uses_all_associations_and_card_projection(
    org_client, monkeypatch
):
    _pin_trending_mode(monkeypatch, "composite")
    response = org_client.get("/api/v1/organizations/?featured_only=true")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    organization = data["results"][0]
    assert organization["slug"] == "acme"
    assert organization["paper_count"] == 4
    assert organization["trending_rank"] == 1
    assert organization["top_trending_paper"]["title"] == "Paper 1"
    digest = hashlib.sha256(b"fake-png").hexdigest()
    assert organization["logo_url"] == (f"/api/v1/organizations/acme/logo/{digest}.png")


def test_curated_index_ignores_rows_outside_reviewed_manifest(org_client, monkeypatch):
    db = TestingSessionLocal()
    try:
        db.add(
            Organization(
                id=2,
                name="Imported Lab",
                slug="imported-lab",
                is_featured=True,
                display_order=2,
            )
        )
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "backend.services.organization_service.BY_PWC_SLUG", {"acme": object()}
    )
    response = org_client.get("/api/v1/organizations/index/cards")

    assert response.status_code == 200
    assert [item["slug"] for item in response.json()["results"]] == ["acme"]


def test_cached_logo_supports_edge_and_conditional_caching(org_client):
    digest = hashlib.sha256(b"fake-png").hexdigest()
    first = org_client.get(f"/api/v1/organizations/acme/logo/{digest}.png")
    assert first.status_code == 200
    assert first.content == b"fake-png"
    assert "max-age=31536000" in first.headers["cache-control"]
    assert "immutable" in first.headers["cache-control"]
    assert "immutable" in first.headers["cdn-cache-control"]
    second = org_client.get(
        f"/api/v1/organizations/acme/logo/{digest}.png",
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert second.status_code == 304
    wrong_digest = "0" * 64
    assert (
        org_client.get(
            f"/api/v1/organizations/acme/logo/{wrong_digest}.png"
        ).status_code
        == 404
    )
    assert org_client.get("/api/v1/organizations/acme/logo.webp").status_code == 404
    for compatibility_path in (
        "/api/v1/organizations/acme/logo.png",
        "/api/v1/organizations/acme/logo",
    ):
        compatibility = org_client.get(compatibility_path)
        assert compatibility.status_code == 200
        assert "max-age=0" in compatibility.headers["cache-control"]


def test_organization_detail_matches_featured_card_projection(org_client, monkeypatch):
    _pin_trending_mode(monkeypatch, "composite")
    listed = org_client.get("/api/v1/organizations/?featured_only=true").json()
    detail = org_client.get("/api/v1/organizations/acme")
    taxonomy = org_client.get("/api/v1/organizations/acme/areas-with-tasks")

    assert detail.status_code == 200
    assert detail.json() == listed["results"][0]
    assert taxonomy.json()["organization"] == listed["results"][0]
    assert detail.json()["trending_rank"] == 1
    assert detail.json()["top_trending_paper"]["title"] == "Paper 1"
    assert detail.json()["first_paper_year"] is None


def test_featured_detail_rank_matches_list_order_including_ties(
    org_client, monkeypatch
):
    _pin_trending_mode(monkeypatch, "composite")
    db = TestingSessionLocal()
    try:
        db.add_all(
            [
                Organization(
                    id=2,
                    name="Beta",
                    slug="beta",
                    is_featured=True,
                    display_order=5,
                    trending_score=5.0,
                ),
                # Tied with acme on (missing) trending score; fewer papers.
                Organization(
                    id=3, name="Gamma", slug="gamma", is_featured=True, display_order=2
                ),
                # Tied with gamma on score and paper count; later display order.
                Organization(
                    id=4, name="Delta", slug="delta", is_featured=True, display_order=3
                ),
                Organization(id=5, name="Plain", slug="plain", is_featured=False),
            ]
        )
        db.commit()
    finally:
        db.close()

    listed = org_client.get("/api/v1/organizations/?featured_only=true").json()
    assert [item["slug"] for item in listed["results"]] == [
        "beta",
        "acme",
        "gamma",
        "delta",
    ]
    for expected in listed["results"]:
        detail = org_client.get(f"/api/v1/organizations/{expected['slug']}")
        assert detail.status_code == 200
        assert detail.json() == expected

    plain = org_client.get("/api/v1/organizations/plain").json()
    assert plain["trending_rank"] is None
    assert plain["top_trending_paper"] is None
    assert plain["paper_count"] == 0


def test_organization_task_taxonomy_and_paper_filter(org_client, monkeypatch):
    _pin_trending_mode(monkeypatch, "composite")
    taxonomy = org_client.get("/api/v1/organizations/acme/areas-with-tasks")
    assert taxonomy.status_code == 200
    tasks = [task for area in taxonomy.json()["results"] for task in area["tasks"]]
    assert tasks == [
        {
            "id": "1",
            "name": "Image Classification",
            "slug": "image-classification",
            "paper_count": 2,
        }
    ]

    filtered = org_client.get(
        "/api/v1/organizations/acme/papers"
        "?task=image-classification&order_by=trending&page_size=10"
    )
    assert filtered.status_code == 200
    assert filtered.json()["count"] == 2
    assert {paper["title"] for paper in filtered.json()["results"]} == {
        "Paper 1",
        "Paper 3",
    }
    assert (
        org_client.get("/api/v1/organizations/acme/papers?task=missing").status_code
        == 404
    )


def test_organization_contributions_groups_recent_papers_by_date(org_client):
    today = date.today()
    db = TestingSessionLocal()
    try:
        dates = {
            1: today,
            2: today,
            3: today - timedelta(days=1),
            4: today - timedelta(days=365),
        }
        for paper_id, published_date in dates.items():
            db.get(DBPaper, paper_id).date_published = published_date
        db.commit()
    finally:
        db.close()

    response = org_client.get("/api/v1/organizations/acme/contributions")

    assert response.status_code == 200
    assert response.json() == {
        "start_date": (today - timedelta(days=364)).isoformat(),
        "end_date": today.isoformat(),
        "total_count": 3,
        "results": [
            {
                "date": (today - timedelta(days=1)).isoformat(),
                "paper_count": 1,
            },
            {"date": today.isoformat(), "paper_count": 2},
        ],
    }


if __name__ == "__main__":
    pytest.main([__file__])
