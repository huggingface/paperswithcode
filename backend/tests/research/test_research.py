"""Research privacy, discovery, ranking and delivery contracts.

Postgres cases run only against an explicitly disposable test database with the
research migration installed. Provider calls are always mocked.
"""

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager, get_database_session
from backend.models.database import (
    Paper,
    Task,
    Method,
    Dataset,
    Author,
    Organization,
    Evaluation,
)
from backend.models.database.resources import HfArtifact, PaperRepository, Repository
from backend.models.database.identity import UserProfile
from backend.models.database.research import (
    ResearchFollow,
    ResearchSubscription,
    ResearchDigest,
)
from backend.models.research import ResearchEntry
from backend.routers import research
from backend.services import research_follow_service as follows
from backend.services import research_delivery_service as delivery
from backend.utils.auth import require_user

UTC = timezone.utc


@pytest.fixture
def db():
    if os.environ.get("PWC_TEST_DATABASE") != "1":
        pytest.skip("Requires explicit disposable PostgreSQL database")
    assert "test" in db_manager.settings.db_name
    with db_manager.engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        transaction.rollback()


@pytest.fixture
def now():
    return datetime.now(UTC)


def paper(db, now, suffix="1", days=1, **kwargs):
    row = Paper(
        title="Research " + suffix,
        arxiv_id="9912." + suffix,
        date_published=(now - timedelta(days=days)).date(),
        is_latest_version=True,
        abstract="An abstract.",
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def follow(db, kind, entity, when, subject="alice"):
    db.add(
        ResearchFollow(
            hf_subject=subject, kind=kind, entity_id=entity.id, created_at=when
        )
    )
    db.flush()


def tagged(db, p, t):
    db.execute(
        text(
            "INSERT INTO paper_tasks(paper_id,task_id,source) VALUES (:p,:t,'manual')"
        ),
        {"p": p.id, "t": t.id},
    )


def entry(key, interests, strength=2, published="2026-10-10"):
    return ResearchEntry(
        paper_key=key,
        title=key,
        url="/paper/1",
        summary="",
        published=published,
        interests=interests,
        strength=strength,
    )


def test_summary_fallback_sentence_boundary_and_cap():
    assert follows.short_summary(None, "Abstract fallback.") == "Abstract fallback."
    assert follows.short_summary("TLDR.", "abstract") == "TLDR."
    summary = " ".join(["word"] * 40) + ". " + " ".join(["rest"] * 40)
    assert follows.short_summary(summary, None).endswith(".")
    assert len(follows.short_summary(summary, None).split()) == 40
    assert len(follows.short_summary(" ".join(["word"] * 80), None).split()) == 60


def test_diversity_strength_dedup_and_weekly_rotation():
    rows = [entry("multi", ["a", "b"], 4), entry("a", ["a"]), entry("b", ["b"])]
    assert [e.paper_key for e in follows.diverse(rows, 3)] == ["multi", "b", "a"]
    rows = [entry(str(i), [str(i)]) for i in range(25)]
    first = {e.paper_key for e in follows.diverse(rows, 20, 0)}
    second = {e.paper_key for e in follows.diverse(rows, 20, 20)}
    assert len(first) == 20 and len(first | second) == 25
    assert (
        follows.diverse([entry("inherited", ["x"], 1), entry("direct", ["x"], 2)], 1)[
            0
        ].paper_key
        == "direct"
    )


def test_weekly_window_is_monday_eight_utc():
    start, end = delivery.weekly_window(datetime(2026, 10, 12, 8, tzinfo=UTC))
    assert end == datetime(2026, 10, 12, 8, tzinfo=UTC)
    assert end - start == timedelta(days=7)
    assert delivery.weekly_window(end - timedelta(seconds=1))[1] == start


def test_delivery_requires_all_gates(monkeypatch):
    settings = dict(
        research_email_enabled=True,
        resend_api_key="test",
        resend_from="test@example.com",
        resend_domain_verified=True,
        resend_webhook_secret="test",
        resend_webhooks_ready=True,
        environment="production",
    )
    for gate in list(settings):
        values = settings | {gate: False if isinstance(settings[gate], bool) else ""}
        monkeypatch.setattr(delivery, "get_settings", lambda: SimpleNamespace(**values))
        assert not delivery.delivery_ready()
    monkeypatch.setattr(delivery, "get_settings", lambda: SimpleNamespace(**settings))
    assert delivery.delivery_ready()


def test_webhook_signatures_and_replays():
    body = json.dumps(
        {"type": "email.bounced", "data": {"to": ["a@example.com"]}}
    ).encode()
    key = b"a secret key"
    stamp = "1000"
    signature = base64.b64encode(
        hmac.new(key, b"id.1000." + body, hashlib.sha256).digest()
    ).decode()
    headers = {
        "svix-id": "id",
        "svix-timestamp": stamp,
        "svix-signature": "v1," + signature,
    }
    secret = "whsec_" + base64.b64encode(key).decode()
    assert (
        delivery.verify_webhook(body, headers, secret, now=1000)["type"]
        == "email.bounced"
    )
    with pytest.raises(ValueError):
        delivery.verify_webhook(body + b" ", headers, secret, now=1000)
    with pytest.raises(ValueError):
        delivery.verify_webhook(body, headers, secret, now=1400)


def test_html_escapes_catalog_content():
    e = entry("x", ["a"])
    e.title = "<script>bad</script>"
    e.summary = "<img src=x>"
    rendered = delivery.render_digest([e], "safe-token")
    assert "<script>" not in rendered["html"]
    assert "&lt;script&gt;" in rendered["html"]
    assert rendered["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_digest_template_summarizes_the_week_and_links_settings():
    e = entry("x", ["a"])
    e.title, e.url, e.summary, e.reasons = "A paper", "/paper/1", "Short.", ["Agents"]
    e.scores = [{"benchmark": "SWE-bench", "model": "M", "metrics": {"Accuracy": 71.2}}]
    start = datetime(2026, 10, 5, 8, tzinfo=UTC)
    rendered = delivery.render_digest([e], "tok", start, start + timedelta(days=7))
    assert rendered["subject"] == "Your weekly research digest: 1 new paper"
    assert "1 new paper from what you follow, Oct 5 – Oct 11, 2026." in rendered["text"]
    assert "Matched: Agents" in rendered["text"]
    assert "SWE-bench · M: Accuracy 71.2" in rendered["html"]
    assert 'href="https://paperswithcode.co/settings"' in rendered["html"]
    assert "/api/v1/research/unsubscribe/tok" in rendered["html"]


def test_descendants_privacy_methods_and_canonical_versions(db, now):
    parent = Task(name="Parent")
    db.add(parent)
    db.flush()
    child = Task(name="Child", parent_id=parent.id)
    method = Method(name="Method")
    db.add_all([child, method])
    db.flush()
    p = paper(db, now, version="v1")
    tagged(db, p, child)
    db.execute(
        text("INSERT INTO paper_methods(paper_id,method_id) VALUES (:p,:m)"),
        {"p": p.id, "m": method.id},
    )
    p.is_latest_version = False
    db.flush()
    latest = paper(db, now, version="v2")
    tagged(db, latest, parent)
    follow(db, "task", parent, now - timedelta(days=2))
    follow(db, "method", method, now - timedelta(days=2))
    matches = follows.matching_entries(db, "alice", now)
    assert len(matches) == 1 and matches[0].strength == 4
    assert set(matches[0].reasons) == {"Parent", "Method"}
    assert follows.matching_entries(db, "bob", now) == []
    assert (
        len(
            db.execute(
                text("SELECT * FROM research_events WHERE paper_key=:k"),
                {"k": matches[0].paper_key},
            ).all()
        )
        == 1
    )


def test_all_entity_types_and_feed_backfill_not_email(db, now):
    p = paper(db, now)
    author = Author(name="Author")
    org = Organization(name="Org", slug="org")
    task = Task(name="Task")
    dataset = Dataset(name="Benchmark")
    db.add_all([author, org, task, dataset])
    db.flush()
    db.execute(
        text(
            "INSERT INTO paper_authors(paper_id,author_id,author_order) VALUES (:p,:a,1)"
        ),
        {"p": p.id, "a": author.id},
    )
    db.execute(
        text(
            "INSERT INTO paper_organizations(paper_id,organization_id,source) VALUES (:p,:o,'manual')"
        ),
        {"p": p.id, "o": org.id},
    )
    db.add(
        Evaluation(
            paper_id=p.id,
            task_id=task.id,
            dataset_id=dataset.id,
            metrics={"Accuracy": 90},
            model_name="M",
        )
    )
    db.flush()
    for kind, obj in [
        ("author", author),
        ("organization", org),
        ("benchmark", dataset),
    ]:
        follow(db, kind, obj, now + timedelta(minutes=1))
    matches = follows.matching_entries(db, "alice", now + timedelta(minutes=2))
    assert (
        len(matches) == 1 and matches[0].strength == 6 and len(matches[0].scores) == 1
    )
    assert (
        follows.matching_entries(
            db,
            "alice",
            now + timedelta(minutes=2),
            window_start=now - timedelta(days=7),
            window_end=now + timedelta(minutes=2),
        )
        == []
    )


def test_cutoffs_unknown_future_and_old_revision(db, now):
    t = Task(name="Task")
    db.add(t)
    db.flush()
    follow(db, "task", t, now - timedelta(days=40))
    for suffix, days in [("1", 30), ("2", 31), ("3", -1)]:
        tagged(db, paper(db, now, suffix, days=days), t)
    unknown = Paper(title="Unknown", arxiv_id="9912.unknown", is_latest_version=True)
    db.add(unknown)
    db.flush()
    tagged(db, unknown, t)
    old = paper(db, now, "4", days=50, version="v1")
    old.is_latest_version = False
    db.flush()
    tagged(db, paper(db, now, "4", days=0, version="v2"), t)
    matches = follows.matching_entries(db, "alice", now)
    assert [m.paper_key for m in matches] == ["arxiv:9912.1"]


def test_new_results_not_corrections_or_reinsertions(db, now):
    t = Task(name="Task")
    d = Dataset(name="Benchmark")
    db.add_all([t, d])
    db.flush()
    follow(db, "benchmark", d, now - timedelta(days=3))
    p = paper(db, now)
    db.execute(
        text("UPDATE research_events SET discovered_at=:old WHERE paper_id=:p"),
        {"old": now - timedelta(days=8), "p": p.id},
    )
    e = Evaluation(
        paper_id=p.id,
        task_id=t.id,
        dataset_id=d.id,
        model_name="M",
        metrics={"Accuracy": 25},
    )
    db.add(e)
    db.flush()
    end = now + timedelta(minutes=1)
    matches = follows.matching_entries(
        db, "alice", end, window_start=now - timedelta(days=7), window_end=end
    )
    assert len(matches) == 1 and matches[0].scores[0]["metrics"] == {"Accuracy": 25}
    count = db.scalar(text("SELECT count(*) FROM research_events"))
    e.metrics = {"Accuracy": 26}
    db.flush()
    assert db.scalar(text("SELECT count(*) FROM research_events")) == count
    db.delete(e)
    db.flush()
    db.add(
        Evaluation(
            paper_id=p.id,
            task_id=t.id,
            dataset_id=d.id,
            model_name="M",
            metrics={"Accuracy": 27},
        )
    )
    db.flush()
    assert db.scalar(text("SELECT count(*) FROM research_events")) == count
    corrected = follows.matching_entries(
        db, "alice", end, window_start=now - timedelta(days=7), window_end=end
    )
    assert corrected[0].scores[0]["metrics"] == {"Accuracy": 27}
    assert (
        follows.matching_entries(
            db,
            "alice",
            end + timedelta(days=7),
            window_start=end,
            window_end=end + timedelta(days=7),
        )
        == []
    )


def test_api_ownership_optin_and_unsubscribe(db, now, monkeypatch):
    app = FastAPI()
    app.include_router(research.router)
    app.dependency_overrides[get_database_session] = lambda: db
    app.dependency_overrides[require_user] = lambda: {"hf_subject": "alice"}
    monkeypatch.setattr(
        research,
        "decode_request_session",
        lambda request: {
            "sub": "alice",
            "email": "Alice@example.com",
            "email_verified": True,
        },
    )
    t = Task(name="Task")
    db.add(t)
    db.flush()
    follow(db, "task", t, now, "bob")
    client = TestClient(app)
    assert client.get("/me/follows").json() == []
    assert client.put(f"/me/follows/task/{t.id}").status_code == 204
    assert len(client.get("/me/follows").json()) == 1
    assert client.delete(f"/me/follows/task/{t.id}").status_code == 204
    assert db.get(ResearchFollow, ("bob", "task", t.id)) is not None
    # The follow turned the weekly email on by default; unfollowing keeps it.
    assert client.get("/me/research-email").json()["enabled"] is True
    assert (
        client.put("/me/research-email", json={"enabled": True}).json()["email"]
        == "alice@example.com"
    )
    sub = db.get(ResearchSubscription, "alice")
    assert (
        client.get("/research/unsubscribe/" + sub.unsubscribe_token).status_code == 200
    )
    assert sub.enabled
    client.post("/research/unsubscribe/" + sub.unsubscribe_token)
    assert not sub.enabled
    monkeypatch.setattr(
        research,
        "decode_request_session",
        lambda request: {"email": "spoof@example.com", "email_verified": False},
    )
    assert client.put("/me/research-email", json={"enabled": True}).status_code == 409


def test_weekly_email_defaults_on_once_and_respects_opt_out(db, monkeypatch):
    app = FastAPI()
    app.include_router(research.router)
    app.dependency_overrides[get_database_session] = lambda: db
    user = {"hf_subject": "alice"}
    app.dependency_overrides[require_user] = lambda: user
    session = {"email": "Alice@example.com", "email_verified": True}
    monkeypatch.setattr(research, "decode_request_session", lambda request: session)
    first, second = Task(name="First"), Task(name="Second")
    db.add_all([first, second])
    db.flush()
    client = TestClient(app)
    assert client.get("/me/research-email").json()["enabled"] is False
    assert client.put(f"/me/follows/task/{first.id}").status_code == 204
    prefs = client.get("/me/research-email").json()
    assert prefs["enabled"] is True and prefs["email"] == "alice@example.com"
    assert db.get(ResearchSubscription, "alice").opted_in_at is not None
    client.put("/me/research-email", json={"enabled": False})
    assert client.put(f"/me/follows/task/{second.id}").status_code == 204
    assert client.get("/me/following").status_code == 200
    assert client.get("/me/research-email").json()["enabled"] is False
    user["hf_subject"] = "bob"
    session = {"email": "bob@example.com", "email_verified": False}
    assert client.put(f"/me/follows/task/{first.id}").status_code == 204
    assert client.get("/me/research-email").json()["enabled"] is False


def test_retry_outbox_payload_suppression_and_expiry(db, now, monkeypatch):
    monkeypatch.setattr(delivery, "delivery_ready", lambda: True)
    monkeypatch.setattr(
        delivery, "get_settings", lambda: SimpleNamespace(resend_api_key="test")
    )
    _, end = delivery.weekly_window(now)
    db.add(
        ResearchSubscription(
            hf_subject="alice",
            email="a@example.com",
            enabled=True,
            unsubscribe_token="token",
            opted_in_at=end - timedelta(days=20),
        )
    )
    db.add(
        ResearchDigest(
            hf_subject="alice",
            window_end=end,
            status="pending",
            payload={"to": ["a@example.com"], "subject": "unchanged"},
        )
    )
    db.commit()
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise httpx.ReadTimeout("ambiguous")
        return SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: {"id": "provider-id"}
        )

    monkeypatch.setattr(delivery.httpx, "post", post)
    assert delivery.deliver_digest(db, "alice", end, now) == "retry"
    assert (
        delivery.deliver_digest(db, "alice", end, now + timedelta(minutes=10)) == "sent"
    )
    assert calls[0] == calls[1]
    assert (
        delivery.deliver_digest(db, "alice", end, now + timedelta(minutes=20)) == "sent"
    )
    assert len(calls) == 2
    digest = db.get(ResearchDigest, ("alice", end))
    digest.status = "pending"
    db.commit()
    assert (
        delivery.deliver_digest(db, "alice", end, now + timedelta(hours=24))
        == "uncertain"
    )
    assert len(calls) == 2
    delivery.record_suppression(
        db, {"type": "email.complained", "data": {"to": ["a@example.com"]}}
    )
    assert not db.get(ResearchSubscription, "alice").enabled
    assert follows.suppressed(db, "a@example.com")


def test_empty_week_and_no_carryover(db, now, monkeypatch):
    monkeypatch.setattr(
        delivery,
        "get_settings",
        lambda: SimpleNamespace(resend_from="test@example.com"),
    )
    _, end = delivery.weekly_window(now)
    db.add(
        ResearchSubscription(
            hf_subject="alice",
            email="a@example.com",
            enabled=True,
            unsubscribe_token="token",
            opted_in_at=end - timedelta(days=20),
        )
    )
    db.commit()
    assert delivery.prepare_digest(db, "alice", end).status == "empty"
    assert (
        delivery.prepare_digest(db, "alice", end + timedelta(days=7)).status == "empty"
    )
    assert delivery.prepare_digest(db, "alice", end + timedelta(days=8)) is None


def test_hourly_job_closes_pending_outboxes_after_window_even_for_opted_out_users(
    db, now, monkeypatch
):
    from contextlib import nullcontext
    from backend.scripts import send_research_digests as job

    _, end = delivery.weekly_window(now)
    after_window = end + timedelta(hours=24)
    db.add_all(
        [
            ResearchDigest(
                hf_subject="attempted",
                window_end=end,
                status="pending",
                payload={},
                first_attempt_at=end,
            ),
            ResearchDigest(
                hf_subject="unattempted", window_end=end, status="pending", payload={}
            ),
            ResearchDigest(
                hf_subject="sent",
                window_end=end,
                status="sent",
                payload={},
                first_attempt_at=end,
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(job, "delivery_ready", lambda: True)
    monkeypatch.setattr(job, "datetime", SimpleNamespace(now=lambda tz: after_window))
    monkeypatch.setattr(
        job, "db_manager", SimpleNamespace(session_local=lambda: nullcontext(db))
    )
    monkeypatch.setattr(
        job,
        "deliver_digest",
        lambda *args: pytest.fail("Outside-window job must not send"),
    )
    job.main()
    assert db.get(ResearchDigest, ("attempted", end)).status == "uncertain"
    assert db.get(ResearchDigest, ("unattempted", end)).status == "expired"
    assert db.get(ResearchDigest, ("sent", end)).status == "sent"
    assert delivery.expire_pending_digests(db, after_window) == 0


@pytest.mark.parametrize("method", ["get", "head"])
def test_following_direct_navigation_serves_spa_without_catalog_lookup(
    monkeypatch, method
):
    from backend.routers import discovery_pages

    app = FastAPI()
    app.include_router(discovery_pages.router)
    # A private client route must not fall through to an organization lookup.
    app.dependency_overrides[get_database_session] = lambda: object()
    monkeypatch.setattr(
        discovery_pages, "load_index_html", lambda: "<!doctype html><html>app</html>"
    )
    response = getattr(TestClient(app), method)("/following")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_feed_hydrates_standard_cards_in_ranked_order(db, now, monkeypatch):
    from backend.services.paper_service import PaperService

    task = Task(name="Card task", slug="card-task")
    db.add(task)
    db.flush()
    older = paper(db, now, "card-old", days=2)
    newer = paper(db, now, "card-new", days=1)
    external = Paper(
        title="External",
        source="external",
        source_url="https://example.com/report",
        date_published=now.date(),
        is_latest_version=True,
        abstract="External abstract",
    )
    db.add(external)
    db.flush()
    for row in [older, newer, external]:
        tagged(db, row, task)
    follow(db, "task", task, now)
    monkeypatch.setattr(
        PaperService,
        "_resolve_thumbnail_url",
        lambda self, row: f"/api/thumbnails/{row.id}.png",
    )
    entries = follows.feed_entries(db, "alice", now, 0, 2)
    assert [e.paper.id for e in entries] == [str(external.id), str(newer.id)]
    assert entries[0].paper.source == "external"
    assert entries[1].paper.thumbnail_url == f"/api/thumbnails/{newer.id}.png"
    assert entries[1].paper.abstract == newer.abstract
    assert entries[1].paper.tasks[0].slug == task.slug
    assert [e.paper.id for e in follows.feed_entries(db, "alice", now, 2, 2)] == [
        str(older.id)
    ]
    assert follows.feed_entries(db, "bob", now, 0, 2) == []


def test_feed_uses_home_feed_trending_order(db, now, monkeypatch):
    from backend.config import get_settings

    monkeypatch.setattr(get_settings(), "trending_ranking_mode", "composite")
    task = Task(name="Trend task", slug="trend-task")
    method = Method(name="Trend method")
    db.add_all([task, method])
    db.flush()
    stale = paper(db, now, "trend-stale", days=1)
    hot = paper(db, now, "trend-hot", days=3)
    multi = paper(db, now, "trend-multi", days=2)
    hot.trending_score, hot.trending_score_updated_at = 5.0, now
    stale.trending_score = 9.0
    stale.trending_score_updated_at = now - timedelta(days=2)
    for row in [stale, hot, multi]:
        tagged(db, row, task)
    db.execute(
        text("INSERT INTO paper_methods(paper_id,method_id) VALUES (:p,:m)"),
        {"p": multi.id, "m": method.id},
    )
    follow(db, "task", task, now)
    follow(db, "method", method, now)
    db.flush()
    # Trending wins over match strength; stale scores fall back to recency.
    assert [e.paper.id for e in follows.feed_entries(db, "alice", now, 0, 3)] == [
        str(hot.id),
        str(stale.id),
        str(multi.id),
    ]


def test_feed_filters_match_the_home_feed(db, now):
    task = Task(name="Filter task", slug="filter-task")
    db.add(task)
    db.flush()
    recent = paper(db, now, "filter-recent", days=1)
    old = paper(db, now, "filter-old", days=60)
    for row in [recent, old]:
        tagged(db, row, task)
    follow(db, "task", task, now)
    repo = Repository(url="https://github.com/example/filter-old")
    db.add(repo)
    db.flush()
    db.add(PaperRepository(paper_id=old.id, repository_id=repo.id))
    recent.hf_artifacts.append(
        HfArtifact(
            kind="model",
            repo_id="example/filter-recent",
            url="https://huggingface.co/example/filter-recent",
        )
    )
    db.flush()

    def ids(**filters):
        return [
            e.paper.id for e in follows.feed_entries(db, "alice", now, 0, 10, **filters)
        ]

    # The default window stays 30 days; explicit and all-time ranges widen it.
    assert ids() == [str(recent.id)]
    assert set(ids(all_time=True)) == {str(recent.id), str(old.id)}
    window = {
        "start_date": (now - timedelta(days=90)).date(),
        "end_date": (now - timedelta(days=30)).date(),
    }
    assert ids(**window) == [str(old.id)]
    assert ids(all_time=True, has_code=True) == [str(old.id)]
    assert ids(all_time=True, has_hf_artifacts=True) == [str(recent.id)]
    assert ids(has_code=True) == []
    entry = follows.feed_entries(db, "alice", now, 0, 10, **window)[0]
    assert entry.reasons == ["Filter task"]


def test_preview_and_test_send_never_touch_the_outbox(db, now, monkeypatch):
    task = Task(name="Preview task", slug="preview-task")
    db.add(task)
    db.flush()
    tagged(db, paper(db, now, "preview", days=2), task)
    follow(db, "task", task, now)
    db.add(UserProfile(hf_subject="alice", current_username="alice-hf"))
    db.add(
        ResearchSubscription(
            hf_subject="alice",
            email="a@example.com",
            enabled=False,
            unsubscribe_token="t",
        )
    )
    db.flush()
    assert delivery.subject_for_username(db, "alice-hf") == "alice"
    preview = delivery.sample_digest(db, "alice", now)
    assert preview["to"] == ["a@example.com"]
    assert "Research preview" in preview["text"]
    assert f"{now:%b} {now.day}, {now:%Y}." in preview["text"]

    calls = []
    monkeypatch.setattr(
        delivery.httpx,
        "post",
        lambda *a, **kw: calls.append(kw)
        or SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"id": "p1"}),
    )
    monkeypatch.setattr(delivery, "delivery_ready", lambda: False)
    assert delivery.send_test_digest(db, "alice", now) == "disabled"
    monkeypatch.setattr(delivery, "delivery_ready", lambda: True)
    monkeypatch.setattr(
        delivery,
        "get_settings",
        lambda: SimpleNamespace(resend_api_key="k", resend_from="PwC <d@example.com>"),
    )
    assert delivery.send_test_digest(db, "alice", now) == "not-opted-in"
    db.get(ResearchSubscription, "alice").enabled = True
    db.flush()
    assert delivery.send_test_digest(db, "alice", now) == "sent p1 to a@example.com"
    assert calls[0]["json"]["to"] == ["a@example.com"]
    assert calls[0]["json"]["subject"].startswith("[Test] ")
    assert db.scalar(text("SELECT count(*) FROM research_digests")) == 0


def test_webhook_body_limit_refuses_declared_and_streamed_oversize():
    import asyncio

    from fastapi import HTTPException

    from backend.routers.research import _bounded_body

    class Request:
        def __init__(self, chunks, declared=None):
            self.headers = {"content-length": declared} if declared else {}
            self._chunks = chunks

        async def stream(self):
            for chunk in self._chunks:
                yield chunk

    def read(request):
        return asyncio.run(_bounded_body(request, 10))

    assert read(Request([b"12345", b"678"])) == b"12345678"
    for request in (
        Request([b"x" * 4] * 5),  # chunked, no Content-Length
        Request([pytest.fail], declared="11"),  # refused before reading
    ):
        with pytest.raises(HTTPException) as error:
            read(request)
        assert error.value.status_code == 413
