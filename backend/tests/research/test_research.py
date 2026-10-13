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
    assert client.get("/me/research-email").json()["enabled"] is False
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
