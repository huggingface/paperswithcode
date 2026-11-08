"""Public free-text topics: topic pages, their papers, and homepage bubbles.

A topic's creator decides whether it is public. Public topics show the
creator's Hugging Face username, a follower count and the avatars of followers
who allow it. Homepage bubbles rank eligible public topics by followers. An
admin can hide a topic, which removes it from the bubbles and search engines
without touching anyone's follow.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy import Integer, column, desc, func, select, text
from sqlalchemy.orm import Session

from backend.models.database import Paper as DBPaper
from backend.models.database import UserProfile
from backend.models.database.research import (
    ResearchSubscription,
    ResearchTopic,
    ResearchTopicFollow,
)
from backend.models.papers import Paper
from backend.models.research import PublicTopicView, TopicBubble, TopicPerson
from backend.services.research_topic_service import THRESHOLD

BUBBLE_LIMIT = 8
BUBBLE_MIN_RECENT_PAPERS = 5
RECENT_DAYS = 30
INDEX_MIN_FOLLOWERS = 3
AVATAR_LIMIT = 8

# Verdicts at the threshold, plus the embedding preview until the backfill is
# done, mapped to each paper's latest version (as the following feed does).
TOPIC_PAPERS_SQL = """
WITH hits AS (
 SELECT v.paper_id FROM research_topic_verdicts v
 WHERE v.topic_id=:topic_id AND v.score>=:threshold
 UNION
 SELECT pv.paper_id FROM research_topic_previews pv
 JOIN research_topics t ON t.id=pv.topic_id AND t.backfill_status<>'done'
 WHERE pv.topic_id=:topic_id
)
SELECT p.id FROM hits h JOIN papers source ON source.id=h.paper_id
JOIN papers p ON (source.arxiv_id IS NOT NULL AND p.arxiv_id=source.arxiv_id AND p.is_latest_version)
 OR (source.arxiv_id IS NULL AND p.id=source.id)
"""

BUBBLES_SQL = """
SELECT * FROM (
 SELECT t.id, t.text, t.label, u.current_username creator,
  (SELECT count(*) FROM research_topic_follows f WHERE f.topic_id=t.id) followers,
  (SELECT count(*) FROM research_topic_verdicts v JOIN papers p ON p.id=v.paper_id
   WHERE v.topic_id=t.id AND v.score>=:threshold AND p.date_published>=:recent) recent
 FROM research_topics t
 LEFT JOIN user_profiles u ON u.hf_subject=t.created_by_hf_subject
 WHERE t.is_public AND t.hidden_at IS NULL AND t.backfill_status='done'
) ranked
WHERE followers>0 AND recent>=:min_recent
ORDER BY followers DESC, recent DESC, id
LIMIT :limit
"""


def person(username: str | None) -> TopicPerson | None:
    if not username:
        return None
    return TopicPerson(
        username=username,
        avatar_url=f"https://huggingface.co/api/users/{username}/avatar?redirect=true",
    )


def visible_topic(
    db: Session, topic_id: int, viewer: str | None
) -> tuple[ResearchTopic, bool]:
    """The topic and whether ``viewer`` follows it.

    Raises ``LookupError`` for a missing topic, or a private one the viewer
    neither created nor follows.
    """
    topic = db.get(ResearchTopic, topic_id)
    following = viewer is not None and (
        db.get(ResearchTopicFollow, (viewer, topic_id)) is not None
    )
    if topic is None or not (
        topic.is_public
        or following
        or (viewer is not None and topic.created_by_hf_subject == viewer)
    ):
        raise LookupError(topic_id)
    return topic, following


def topic_view(db: Session, topic_id: int, viewer: str | None) -> PublicTopicView:
    topic, following = visible_topic(db, topic_id, viewer)
    creator = db.scalar(
        select(UserProfile.current_username).where(
            UserProfile.hf_subject == topic.created_by_hf_subject
        )
    )
    followers = db.scalar(
        select(func.count()).where(ResearchTopicFollow.topic_id == topic_id)
    )
    avatars = db.scalars(
        select(UserProfile.current_username)
        .join(
            ResearchTopicFollow,
            ResearchTopicFollow.hf_subject == UserProfile.hf_subject,
        )
        .join(
            ResearchSubscription,
            ResearchSubscription.hf_subject == UserProfile.hf_subject,
        )
        .where(
            ResearchTopicFollow.topic_id == topic_id,
            ResearchSubscription.show_as_follower,
            UserProfile.hf_subject != func.coalesce(topic.created_by_hf_subject, ""),
        )
        .order_by(ResearchTopicFollow.created_at)
        .limit(AVATAR_LIMIT)
    ).all()
    return PublicTopicView(
        id=topic.id,
        text=topic.text,
        label=topic.label,
        status=topic.backfill_status,
        creator=person(creator),
        is_public=topic.is_public,
        indexable=topic.is_public
        and topic.hidden_at is None
        and followers >= INDEX_MIN_FOLLOWERS,
        followers=followers,
        follower_avatars=[person(name) for name in avatars],
        following=following,
        is_creator=viewer is not None and topic.created_by_hf_subject == viewer,
    )


def topic_papers(
    db: Session,
    topic_id: int,
    viewer: str | None,
    *,
    order: Literal["trending", "newest"],
    offset: int,
    limit: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Paper]:
    """Papers matching a visible topic, ranked like the home feed or newest first.

    ``start_date``/``end_date`` bound the publication date, inclusive.
    """
    from backend.services.paper_service import PaperService

    visible_topic(db, topic_id, viewer)
    matched = (
        text(TOPIC_PAPERS_SQL)
        .bindparams(topic_id=topic_id, threshold=THRESHOLD)
        .columns(column("id", Integer))
        .subquery("matched")
    )
    service = PaperService(db)
    query = db.query(DBPaper).filter(DBPaper.id.in_(select(matched.c.id)))
    if start_date is not None:
        query = query.filter(DBPaper.date_published >= start_date)
    if end_date is not None:
        query = query.filter(DBPaper.date_published <= end_date)
    if order == "newest":
        query = query.order_by(desc(DBPaper.date_published), desc(DBPaper.id))
    else:
        query = service.apply_scoped_trending_order(query)
    rows = query.offset(offset).limit(limit).all()
    return service.hydrate_cards(rows, include_resources=True)


def bubbles(db: Session, now: datetime) -> list[TopicBubble]:
    """Popular public topics for the homepage, most followed first."""
    recent: date = (now - timedelta(days=RECENT_DAYS)).date()
    rows = db.execute(
        text(BUBBLES_SQL),
        {
            "threshold": THRESHOLD,
            "recent": recent,
            "min_recent": BUBBLE_MIN_RECENT_PAPERS,
            "limit": BUBBLE_LIMIT,
        },
    ).mappings()
    return [
        TopicBubble(
            id=row["id"],
            text=row["text"],
            label=row["label"],
            creator=person(row["creator"]),
            followers=row["followers"],
        )
        for row in rows
    ]


def set_hidden(db: Session, topic_id: int, hidden: bool, now: datetime) -> None:
    """Admin moderation: hide a topic from bubbles and search engines, or restore it."""
    topic = db.get(ResearchTopic, topic_id, with_for_update=True)
    if topic is None:
        raise LookupError(topic_id)
    topic.hidden_at = now if hidden else None
    db.commit()


def set_show_as_follower(db: Session, subject: str, value: bool) -> None:
    from backend.services.research_follow_service import subscription

    subscription(db, subject).show_as_follower = value
    db.commit()
