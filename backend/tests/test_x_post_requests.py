"""Admin "Tweet it" requests: queue order, resolution, and the admin API."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import Base, Paper, PaperXPost, XInsightPost, XPostRequest
from backend.services import x_post_candidates, x_post_requests
from backend.services.x_post_candidates import Candidate
from backend.utils.auth import require_admin, require_hf_admin


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _compile_postgres_container_sqlite(_element, _compiler, **_kw):
    return "TEXT"


TABLES = [table for table in Base.metadata.sorted_tables if table.name != "chat_shares"]
NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=TABLES)
    session = sessionmaker(bind=engine)()
    for paper_id in (1, 2, 3):
        session.add(
            Paper(
                id=paper_id,
                title=f"Paper {paper_id}",
                abstract="Abstract",
                arxiv_id=f"2611.0000{paper_id}",
                version="v1",
                is_latest_version=True,
            )
        )
    session.commit()
    yield session
    session.close()


def test_requests_keep_click_order_and_a_repeat_click_keeps_its_place(db):
    for minutes, paper_id in enumerate((2, 1, 3)):
        x_post_requests.request_post(
            db, paper_id, requested_by="nielsr", now=NOW + timedelta(minutes=minutes)
        )
    again = x_post_requests.request_post(
        db, 2, requested_by="nielsr", now=NOW + timedelta(hours=1)
    )
    assert (again.state, again.position) == ("requested", 1)
    assert [r.paper_id for r in x_post_requests.open_requests(db)] == [2, 1, 3]


def test_cancelled_request_rejoins_at_the_back(db):
    x_post_requests.request_post(db, 1, requested_by=None, now=NOW)
    x_post_requests.request_post(
        db, 2, requested_by=None, now=NOW + timedelta(minutes=1)
    )
    assert x_post_requests.resolve_request(db, 1, "cancelled")
    assert not x_post_requests.resolve_request(db, 1, "cancelled")
    assert x_post_requests.request_status(db, 1).state == "none"
    status = x_post_requests.request_post(
        db, 1, requested_by=None, now=NOW + timedelta(minutes=2)
    )
    assert status.position == 2


def test_recording_the_post_resolves_the_request(db):
    x_post_requests.request_post(db, 1, requested_by=None, now=NOW)
    x_post_candidates.record(
        db,
        kind="trending_paper",
        subject_key="1",
        post_id="2120900000000000000",
        now=NOW,
    )
    status = x_post_requests.request_status(db, 1)
    assert status.state == "posted"
    assert status.post_url == "https://x.com/paperswithcodee/status/2120900000000000000"
    assert db.get(XPostRequest, 1).resolution == "posted"
    with pytest.raises(x_post_requests.AlreadyPostedError):
        x_post_requests.request_post(db, 1, requested_by=None)


def test_requested_candidates_skip_papers_posted_another_way(db, monkeypatch):
    monkeypatch.setattr(
        x_post_requests,
        "paper_candidate",
        lambda _db, paper, rank: Candidate("trending_paper", str(paper.id), "", "", {}),
    )
    x_post_requests.request_post(db, 1, requested_by=None, now=NOW)
    x_post_requests.request_post(
        db, 2, requested_by=None, now=NOW + timedelta(minutes=1)
    )
    db.add(PaperXPost(paper_id=1, post_id="1", posted_at=NOW))
    db.commit()
    items = x_post_requests.requested_candidates(db)
    assert [(i["subject_key"], i["request_position"]) for i in items] == [("2", 1)]
    assert items[0]["facts"]["requested_by_admin"] is True
    assert db.get(XPostRequest, 1).resolution == "posted"


def test_admin_api(db):
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: db
    admin = {"role": "admin", "username": "nielsr"}
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[require_hf_admin] = lambda: admin
    client = TestClient(app)
    url = "/api/v1/admin/papers/{}/x-post-request"

    assert client.get(url.format(1)).json()["state"] == "none"
    first = client.post(url.format(1)).json()
    second = client.post(url.format(2)).json()
    assert (first["position"], second["position"]) == (1, 2)
    assert db.get(XPostRequest, 2).requested_by == "nielsr"
    assert client.delete(url.format(1)).json()["state"] == "none"
    assert client.get(url.format(2)).json()["position"] == 1
    assert client.post(url.format(99)).status_code == 404
    db.add(
        XInsightPost(kind="trending_paper", subject_key="3", post_id="5", posted_at=NOW)
    )
    db.commit()
    assert client.post(url.format(3)).status_code == 409


def test_admin_api_requires_an_admin(db):
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: db
    client = TestClient(app)
    assert client.get("/api/v1/admin/papers/1/x-post-request").status_code == 401
    assert client.post("/api/v1/admin/papers/1/x-post-request").status_code == 401


def test_a_sota_post_resolves_the_request_and_links_the_post(db):
    x_post_requests.request_post(db, 2, requested_by=None, now=NOW)
    x_post_candidates.record(
        db, kind="open_sota", subject_key="open:7:Accuracy:2", post_id="42", now=NOW
    )
    assert db.get(XPostRequest, 2).resolution == "posted"
    status = x_post_requests.request_status(db, 2)
    assert (status.state, status.post_url) == (
        "posted",
        "https://x.com/paperswithcodee/status/42",
    )
    assert x_post_requests.post_url(db, 12) is None  # key ends with "2", not ":12"
