"""Public free-text topics: creators, visibility, follow by id, pages and bubbles.

Postgres cases run only against an explicitly disposable test database with the
research migrations installed.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.database.connection import db_manager, get_database_session
from backend.models.database import Paper, UserProfile
from backend.models.database.research import (
    ResearchTopic,
    ResearchTopicPreview,
    ResearchTopicVerdict,
)
from backend.routers import research
from backend.services import public_topic_service as public
from backend.services import research_follow_service as follows
from backend.services import research_topic_service as topics
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
            for name in ("alice", "bob", "carol", "dave"):
                session.add(UserProfile(hf_subject=name, current_username=name))
            session.flush()
            yield session
        transaction.rollback()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(topics, "summarize", lambda _: None)
    monkeypatch.setattr(topics, "save_preview", lambda *_: None)


@pytest.fixture
def now():
    return datetime.now(UTC)


def paper(db, now, suffix, title, days=1):
    row = Paper(
        title=title,
        arxiv_id="9912." + suffix,
        date_published=(now - timedelta(days=days)).date(),
        is_latest_version=True,
        abstract="An abstract.",
    )
    db.add(row)
    db.flush()
    return row


def verdict(db, topic_id, row, score=0.95):
    db.add(
        ResearchTopicVerdict(
            topic_id=topic_id,
            paper_id=row.id,
            score=score,
            card_sha="x",
            policy_version="v",
        )
    )
    db.flush()


def done(db, topic_id):
    db.get(ResearchTopic, topic_id).backfill_status = "done"
    db.flush()


def test_first_follower_is_the_creator_and_keeps_it(db, now):
    topic_id = topics.follow_topic(db, "alice", "OCR releases", now)
    topics.follow_topic(db, "bob", "ocr releases", now)
    topic = db.get(ResearchTopic, topic_id)
    assert topic.created_by_hf_subject == "alice"
    assert topic.is_public
    # The creator moving to other text keeps their name on the old topic.
    topics.follow_topic(db, "alice", "OCR models", now, replace=topic_id)
    assert db.get(ResearchTopic, topic_id).created_by_hf_subject == "alice"
    views = {v.text: v for v in topics.topic_views(db, "bob")}
    assert views["OCR releases"].is_creator is False


def test_creator_less_topics_go_to_their_next_follower(db, now):
    topic_id = topics.follow_topic(db, "alice", "world models", now)
    db.get(ResearchTopic, topic_id).created_by_hf_subject = None
    db.get(ResearchTopic, topic_id).is_public = True
    db.flush()
    topics.follow_existing_topic(db, "bob", topic_id, now)
    assert db.get(ResearchTopic, topic_id).created_by_hf_subject == "bob"


def test_only_the_creator_changes_visibility_and_private_topics_refuse_strangers(
    db, now
):
    topic_id = topics.follow_topic(db, "alice", "agent memory", now)
    topics.follow_existing_topic(db, "bob", topic_id, now)
    with pytest.raises(LookupError):
        topics.set_public(db, "bob", topic_id, False)
    topics.set_public(db, "alice", topic_id, False)
    with pytest.raises(LookupError):
        topics.follow_existing_topic(db, "carol", topic_id, now)
    with pytest.raises(LookupError):
        public.topic_view(db, topic_id, "carol")
    with pytest.raises(LookupError):
        public.topic_view(db, topic_id, None)
    # Existing followers keep the topic and can still open it.
    assert public.topic_view(db, topic_id, "bob").following
    assert public.topic_view(db, topic_id, "alice").is_creator
    topics.follow_existing_topic(db, "bob", topic_id, now)


def test_follow_existing_topic_respects_the_limit(db, now, monkeypatch):
    monkeypatch.setattr(topics, "MAX_TOPICS", 1)
    topic_id = topics.follow_topic(db, "alice", "speech synthesis", now)
    topics.follow_topic(db, "bob", "robot learning", now)
    with pytest.raises(OverflowError):
        topics.follow_existing_topic(db, "bob", topic_id, now)
    with pytest.raises(LookupError):
        topics.follow_existing_topic(db, "bob", 0, now)


def test_topic_view_shows_creator_followers_and_visible_avatars(db, now):
    topic_id = topics.follow_topic(db, "alice", "tokenizer-free models", now)
    for name, show in (("bob", True), ("carol", False), ("dave", True)):
        topics.follow_existing_topic(db, name, topic_id, now)
        public.set_show_as_follower(db, name, show)
    view = public.topic_view(db, topic_id, None)
    assert view.creator.username == "alice"
    assert view.creator.avatar_url.endswith("/api/users/alice/avatar?redirect=true")
    assert view.followers == 4
    assert [p.username for p in view.follower_avatars] == ["alice", "bob", "dave"]
    assert view.indexable
    assert not view.following
    public.set_hidden(db, topic_id, True, now)
    assert not public.topic_view(db, topic_id, None).indexable


def test_topic_papers_use_verdicts_or_the_preview_while_building(db, now):
    topic_id = topics.follow_topic(db, "alice", "synthetic data", now)
    old = paper(db, now, "1", "Old match", days=20)
    new = paper(db, now, "2", "New match", days=2)
    weak = paper(db, now, "3", "Weak", days=1)
    preview = paper(db, now, "4", "Preview only", days=1)
    verdict(db, topic_id, old)
    verdict(db, topic_id, new)
    verdict(db, topic_id, weak, topics.THRESHOLD - 0.01)
    db.add(ResearchTopicPreview(topic_id=topic_id, paper_id=preview.id))
    db.flush()

    def titles():
        return [
            p.title
            for p in public.topic_papers(
                db, topic_id, None, order="newest", offset=0, limit=10
            )
        ]

    assert titles() == ["Preview only", "New match", "Old match"]
    recent = public.topic_papers(
        db,
        topic_id,
        None,
        order="newest",
        offset=0,
        limit=10,
        start_date=(now - timedelta(days=7)).date(),
        end_date=now.date(),
    )
    assert [p.title for p in recent] == ["Preview only", "New match"]
    done(db, topic_id)
    assert titles() == ["New match", "Old match"]
    topics.set_public(db, "alice", topic_id, False)
    with pytest.raises(LookupError):
        titles()


def test_bubbles_rank_eligible_public_topics_by_followers(db, now, monkeypatch):
    monkeypatch.setattr(public, "BUBBLE_MIN_RECENT_PAPERS", 2)
    popular = topics.follow_topic(db, "alice", "small language models", now)
    quiet = topics.follow_topic(db, "bob", "reasoning rl", now)
    thin = topics.follow_topic(db, "carol", "biomimicry", now)
    building = topics.follow_topic(db, "dave", "agent memory", now)
    topics.follow_existing_topic(db, "bob", popular, now)
    rows = [paper(db, now, str(i), f"P{i}") for i in range(3)]
    stale = paper(db, now, "9", "Stale", days=60)
    for topic_id in (popular, quiet, building):
        for row in rows:
            verdict(db, topic_id, row)
    verdict(db, thin, rows[0])
    verdict(db, thin, stale)
    for topic_id in (popular, quiet, thin):
        done(db, topic_id)
    assert [b.id for b in public.bubbles(db, now)] == [popular, quiet]
    assert public.bubbles(db, now)[0].followers == 2
    assert public.bubbles(db, now)[0].creator.username == "alice"
    topics.set_public(db, "bob", quiet, False)
    public.set_hidden(db, popular, True, now)
    assert public.bubbles(db, now) == []


def test_public_topic_api(db, monkeypatch, now):
    app = FastAPI()
    app.include_router(research.router)
    app.dependency_overrides[get_database_session] = lambda: db
    viewer = {"hf_subject": "bob"}
    app.dependency_overrides[require_user] = lambda: viewer
    monkeypatch.setattr(
        research,
        "decode_request_session",
        lambda request: {"sub": viewer["hf_subject"]},
    )
    client = TestClient(app)
    topic_id = topics.follow_topic(db, "alice", "OCR releases", now)
    page = client.get(f"/research/topics/{topic_id}").json()
    assert page["creator"]["username"] == "alice"
    assert page["following"] is False
    followed = client.post(f"/me/topics/{topic_id}/follow")
    assert followed.status_code == 201
    assert followed.json()["is_creator"] is False
    assert client.get(f"/research/topics/{topic_id}").json()["followers"] == 2
    assert (
        client.patch(f"/me/topics/{topic_id}", json={"is_public": False}).status_code
        == 404
    )
    assert client.get(f"/research/topics/{topic_id}/papers").json() == []
    assert client.get("/research/topics/featured").json() == []
    assert (
        client.put(
            "/me/topic-follower-visibility", json={"show_as_follower": False}
        ).status_code
        == 204
    )
    assert follows.subscription(db, "bob").show_as_follower is False
    viewer["hf_subject"] = "alice"
    assert (
        client.patch(f"/me/topics/{topic_id}", json={"is_public": False}).json()[
            "is_public"
        ]
        is False
    )
    viewer["hf_subject"] = "carol"
    assert client.get(f"/research/topics/{topic_id}").status_code == 404
    assert client.post(f"/me/topics/{topic_id}/follow").status_code == 404
    assert client.get("/research/topics/0").status_code == 404


def test_accounts_reorder_topics_and_edits_keep_their_place(db, now):
    a = topics.follow_topic(db, "alice", "speech synthesis", now)
    b = topics.follow_topic(db, "alice", "robot learning", now + timedelta(seconds=1))
    c = topics.follow_topic(db, "alice", "world models", now + timedelta(seconds=2))
    ids = lambda: [t.id for t in topics.topic_views(db, "alice")]  # noqa: E731
    assert ids() == [a, b, c]
    # Before any reorder, an edit keeps its slot too.
    b = topics.follow_topic(
        db, "alice", "robot manipulation", now + timedelta(seconds=5), replace=b
    )
    assert ids() == [a, b, c]
    topics.reorder_topics(db, "alice", [c, a, b])
    assert ids() == [c, a, b]
    # Editing a topic keeps its slot; a new topic goes last.
    d = topics.follow_topic(db, "alice", "agent memory", now, replace=a)
    e = topics.follow_topic(db, "alice", "ocr releases", now + timedelta(seconds=3))
    assert ids() == [c, d, b, e]
    for bad in ([c, d, b], [c, d, b, e, e], [c, d, b, e, 0]):
        with pytest.raises(ValueError):
            topics.reorder_topics(db, "alice", bad)
    assert ids() == [c, d, b, e]


def test_reorder_api_and_capitalized_reasons(db, monkeypatch, now):
    app = FastAPI()
    app.include_router(research.router)
    app.dependency_overrides[get_database_session] = lambda: db
    app.dependency_overrides[require_user] = lambda: {"hf_subject": "alice"}
    monkeypatch.setattr(research, "decode_request_session", lambda request: {})
    client = TestClient(app)
    a = topics.follow_topic(db, "alice", "agent swarms", now)
    b = topics.follow_topic(db, "alice", "ocr releases", now + timedelta(seconds=1))
    reordered = client.put("/me/topics/order", json={"topic_ids": [b, a]})
    assert reordered.status_code == 200
    assert [t["id"] for t in reordered.json()] == [b, a]
    assert client.put("/me/topics/order", json={"topic_ids": [b]}).status_code == 409
    reasons = {i.name for i in follows.interests(db, "alice").values()}
    assert reasons == {"\u201cAgent swarms\u201d", "\u201cOcr releases\u201d"}
