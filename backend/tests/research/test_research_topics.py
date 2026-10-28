"""Free-text research topics: Jev judging, backfill claims, and the merged feed.

Postgres cases run only against an explicitly disposable test database with the
research migrations installed. Jev is always a fake.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Paper, Task
from backend.models.database.research import (
    ResearchFollow,
    ResearchSubscription,
    ResearchTopic,
    ResearchTopicVerdict,
)
from backend.models.research import ResearchEntry
from backend.services import research_delivery_service as delivery
from backend.services import research_follow_service as follows
from backend.services import research_topic_service as topics

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


class FakeJudge:
    """Scores by keyword so each test controls relevance through titles."""

    def __init__(self, fail_titles=()):
        self.calls = []
        self.fail_titles = fail_titles

    def score(self, card, names):
        self.calls.append((card.splitlines()[0], list(names)))
        if any(title in card for title in self.fail_titles):
            raise httpx.ConnectError("down")
        return [0.95 if name.split()[0] in card.lower() else 0.1 for name in names]


def paper(db, now, suffix, title, days=1):
    row = Paper(
        title=title,
        arxiv_id="9911." + suffix,
        date_published=(now - timedelta(days=days)).date(),
        is_latest_version=True,
        abstract="An abstract.",
    )
    db.add(row)
    db.flush()
    return row


def test_normalize_collapses_case_space_and_trailing_punctuation():
    assert topics.normalize("  Real-time   Video Generation. ") == (
        "real-time video generation"
    )
    assert topics.display_text(" Real-time \n video ") == "Real-time video"


def test_jev_judge_chunks_topics_and_reads_noul_scores():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json={
                "answers": {
                    key: {"noul": 0.5 + int(key[1:]) / 100} for key in body["questions"]
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    judge = topics.JevTopicJudge("key", client)
    scores = judge.score("Title: A", [f"topic {i}" for i in range(12)])
    assert [len(r["questions"]) for r in requests] == [10, 2]
    assert requests[0]["state"] == "Title: A"
    assert '"topic 0"' in requests[0]["questions"]["t0"]["instructions"]
    assert scores[:2] == [0.5, 0.51] and scores[10:] == [0.5, 0.51]


def entry(key, interests, published="2026-10-10"):
    return ResearchEntry(
        paper_key=key,
        title=key,
        url="/paper/1",
        summary="",
        published=published,
        interests=interests,
        reasons=["“video”"] if "topic:1" in interests else ["Agents"],
        strength=2,
    )


def test_digest_leads_with_topic_section():
    entries = [
        entry("a", ["task:1"]),
        entry("b", ["topic:1"]),
        entry("c", ["topic:1", "task:1"]),
    ]
    topic_entries, rest = delivery.digest_sections(entries)
    assert {e.paper_key for e in topic_entries} == {"b", "c"}
    assert [e.paper_key for e in rest] == ["a"]
    payload = delivery.render_digest(rest, "token", topic_entries=topic_entries)
    assert payload["subject"].endswith("3 new papers")
    body = payload["text"]
    assert body.index("NEW ON YOUR TOPIC") < body.index("b")
    assert body.index("FROM WHAT YOU FOLLOW") < body.index("\na\n")
    alone = delivery.render_digest([], "token", topic_entries=topic_entries)
    assert "NEW ON YOUR TOPIC" not in alone["text"]


def test_set_topic_shares_rows_by_normalized_text(db, now):
    topics.set_topic(db, "alice", "Real-time video generation.", now)
    topics.set_topic(db, "bob", "  real-time VIDEO generation", now)
    alice = db.get(ResearchSubscription, "alice")
    bob = db.get(ResearchSubscription, "bob")
    assert alice.topic_id == bob.topic_id
    topic = db.get(ResearchTopic, alice.topic_id)
    assert topic.text == "Real-time video generation."
    assert topic.backfill_status == "pending"
    topics.set_topic(db, "alice", None, now)
    assert db.get(ResearchSubscription, "alice").topic_id is None
    assert topics.topic_view(db, "alice") is None


def test_set_topic_suggests_exact_catalog_names(db, now):
    db.add(Task(name="Speech Recognition", slug="speech-recognition-topic-test"))
    db.flush()
    topics.set_topic(db, "alice", "speech recognition", now)
    view = topics.topic_view(db, "alice")
    assert [(s.kind, s.name) for s in view.suggestions] == [
        ("task", "Speech Recognition")
    ]


def test_judge_skips_current_verdicts_and_rejudges_changed_cards(db, now):
    topics.set_topic(db, "alice", "video generation", now)
    topic_id = db.get(ResearchSubscription, "alice").topic_id
    video = paper(db, now, "1", "Video diffusion at scale")
    other = paper(db, now, "2", "Protein folding")
    judge = FakeJudge()
    assert topics.judge_papers(
        db, judge, {topic_id: "video generation"}, [video.id, other.id]
    ) == (2, 0)
    assert topics.judge_papers(
        db, judge, {topic_id: "video generation"}, [video.id, other.id]
    ) == (0, 0)
    assert len(judge.calls) == 2
    other.title = "Protein folding v2"
    db.flush()
    assert topics.judge_papers(
        db, judge, {topic_id: "video generation"}, [video.id, other.id]
    ) == (1, 0)
    verdict = db.get(ResearchTopicVerdict, (topic_id, video.id))
    assert verdict.score == pytest.approx(0.95)
    assert verdict.policy_version == topics.POLICY_VERSION


def test_judge_failures_stay_unjudged_for_the_next_run(db, now):
    topics.set_topic(db, "alice", "video generation", now)
    topic_id = db.get(ResearchSubscription, "alice").topic_id
    flaky = paper(db, now, "1", "Video flaky")
    judge = FakeJudge(fail_titles=("Video flaky",))
    assert topics.judge_papers(db, judge, {topic_id: "video"}, [flaky.id]) == (0, 1)
    assert db.get(ResearchTopicVerdict, (topic_id, flaky.id)) is None
    assert topics.judge_papers(db, FakeJudge(), {topic_id: "video"}, [flaky.id]) == (
        1,
        0,
    )


def test_claim_backfill_skips_unfollowed_recent_retries_and_live_claims(db, now):
    topics.set_topic(db, "alice", "video generation", now)
    topic = db.get(ResearchTopic, db.get(ResearchSubscription, "alice").topic_id)
    db.add(ResearchTopic(text="orphan", normalized="orphan"))
    db.flush()
    claimed = topics.claim_backfill(db, now)
    assert claimed.id == topic.id and claimed.backfill_status == "running"
    assert topics.claim_backfill(db, now) is None
    assert topics.claim_backfill(db, now + timedelta(minutes=31)).id == topic.id
    topic.backfill_status = "pending"
    topic.backfill_claimed_at = now
    db.flush()
    assert topics.claim_backfill(db, now + timedelta(minutes=5)) is None
    assert topics.claim_backfill(db, now + timedelta(minutes=11)).id == topic.id


def test_backfill_judges_window_and_recall_then_retries_failures(db, now, monkeypatch):
    topics.set_topic(db, "alice", "video generation", now)
    recent = paper(db, now, "1", "Video recent")
    old = paper(db, now, "2", "Video old", days=400)
    paper(db, now, "3", "Video unrecalled", days=400)
    monkeypatch.setattr(topics, "recall_older", lambda *_: [old.id])
    monkeypatch.setattr(topics, "window_paper_ids", lambda *_: [recent.id])
    topic = topics.claim_backfill(db, now)
    flaky = FakeJudge(fail_titles=("Video old",))
    assert topics.backfill(db, flaky, topic, now) == "pending"
    assert topic.backfill_total == 2 and topic.backfill_done == 2
    topic = topics.claim_backfill(db, now + timedelta(minutes=11))
    judge = FakeJudge()
    assert topics.backfill(db, judge, topic, now) == "done"
    assert [title for title, _ in judge.calls] == ["Title: Video old"]


def test_backfill_gives_up_after_max_attempts(db, now, monkeypatch):
    topics.set_topic(db, "alice", "video generation", now)
    monkeypatch.setattr(topics, "recall_older", lambda *_: [])
    flaky = paper(db, now, "1", "Video flaky")
    monkeypatch.setattr(topics, "window_paper_ids", lambda *_: [flaky.id])
    when = now
    for _ in range(topics.MAX_BACKFILL_ATTEMPTS):
        topic = topics.claim_backfill(db, when)
        status = topics.backfill(db, FakeJudge(("Video flaky",)), topic, when)
        when += timedelta(minutes=11)
    assert status == "failed"
    topics.set_topic(db, "bob", "video generation", now)
    assert topic.backfill_status == "pending" and topic.backfill_attempts == 0


def test_feed_merges_topic_and_entity_hits_with_reasons(db, now):
    task = Task(name="Robotics", slug="robotics-topic-test")
    db.add(task)
    db.flush()
    db.add(ResearchFollow(hf_subject="alice", kind="task", entity_id=task.id))
    topics.set_topic(db, "alice", "video generation", now)
    topic_id = db.get(ResearchSubscription, "alice").topic_id
    both = paper(db, now, "1", "Video robots")
    topic_only = paper(db, now, "2", "Video only")
    below = paper(db, now, "3", "Video weak")
    entity_only = paper(db, now, "4", "Robot only")
    for p in (both, entity_only):
        db.execute(
            text(
                "INSERT INTO paper_tasks(paper_id,task_id,source) VALUES (:p,:t,'manual')"
            ),
            {"p": p.id, "t": task.id},
        )
    scores = (
        (both, 0.9),
        (topic_only, topics.THRESHOLD + 0.01),
        (below, topics.THRESHOLD - 0.01),
    )
    for p, score in scores:
        db.add(
            ResearchTopicVerdict(
                topic_id=topic_id,
                paper_id=p.id,
                score=score,
                card_sha="0" * 64,
                policy_version=topics.POLICY_VERSION,
            )
        )
    db.flush()
    entries = {e.title: e for e in follows.feed_entries(db, "alice", now, 0, 40)}
    assert set(entries) == {"Video robots", "Video only", "Robot only"}
    assert set(entries["Video robots"].reasons) == {
        "Robotics",
        "“video generation”",
    }
    assert entries["Video only"].reasons == ["“video generation”"]
    assert entries["Robot only"].reasons == ["Robotics"]
    topic_only = {
        e.title: e
        for e in follows.feed_entries(db, "alice", now, 0, 40, topic_only=True)
    }
    assert set(topic_only) == {"Video robots", "Video only"}
    assert set(topic_only["Video robots"].reasons) == {
        "Robotics",
        "“video generation”",
    }
