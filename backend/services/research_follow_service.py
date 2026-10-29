"""Private follows, canonical paper matching, and deterministic diverse ranking."""

from datetime import date, datetime, timedelta
import re
import secrets
from typing import NamedTuple

from fastapi import HTTPException
from sqlalchemy import Integer, String, column, exists, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.models.database import (
    Author,
    Dataset,
    Method,
    Organization,
    Task,
    Paper as DBPaper,
)
from backend.models.database.research import (
    ResearchFollow,
    ResearchSubscription,
    ResearchSuppression,
)
from backend.models.research import FollowView, ResearchEntry, ResearchFeedEntry
from backend.models.database.research import ResearchTopic
from backend.services.research_topic_service import THRESHOLD as TOPIC_THRESHOLD

ENTITIES = {
    "task": (Task, "tasks"),
    "method": (Method, "methods"),
    "benchmark": (Dataset, "benchmark"),
    "author": (Author, "authors"),
    "organization": (Organization, "orgs"),
}


def follows(db: Session, subject: str) -> list[FollowView]:
    rows = db.scalars(
        select(ResearchFollow)
        .where(ResearchFollow.hf_subject == subject)
        .order_by(ResearchFollow.kind, ResearchFollow.entity_id)
    ).all()
    result = []
    for kind, (model, route) in ENTITIES.items():
        group = [row for row in rows if row.kind == kind]
        entities = (
            {
                e.id: e
                for e in db.scalars(
                    select(model).where(model.id.in_([r.entity_id for r in group]))
                )
            }
            if group
            else {}
        )
        for row in group:
            entity = entities.get(row.entity_id)
            if entity:
                slug = getattr(entity, "slug", None) or entity.id
                result.append(
                    FollowView(
                        kind=kind,
                        entity_id=row.entity_id,
                        name=entity.name,
                        url=f"/{route}/{slug}",
                        created_at=row.created_at,
                    )
                )
    return result


class Interest(NamedTuple):
    kind: str
    entity_id: int
    name: str


def interests(db: Session, subject: str) -> dict[tuple[str, int], Interest]:
    """Entity follows plus the account's free-text topic, named as reasons show them."""
    found = {
        (f.kind, f.entity_id): Interest(f.kind, f.entity_id, f.name)
        for f in follows(db, subject)
    }
    sub = db.get(ResearchSubscription, subject)
    topic = sub and sub.topic_id and db.get(ResearchTopic, sub.topic_id)
    if topic:
        name = topic.label or topic.text
        short = name if len(name) <= 80 else name[:79].rstrip() + "…"
        found["topic", topic.id] = Interest("topic", topic.id, f"\u201c{short}\u201d")
    return found


def set_follow(
    db: Session, subject: str, kind: str, entity_id: int, enabled: bool
) -> None:
    # Serialize mutations for the account, including the bounded follow count.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:subject, 914))"),
        {"subject": subject},
    )
    key = (subject, kind, entity_id)
    existing = db.get(ResearchFollow, key)
    if not enabled:
        if existing:
            db.delete(existing)
        db.commit()
        return
    model, _ = ENTITIES[kind]
    if db.get(model, entity_id) is None:
        raise HTTPException(404, "Interest not found")
    if existing is None:
        if len(follows(db, subject)) >= 100:
            raise HTTPException(409, "You can follow up to 100 interests")
        db.add(ResearchFollow(hf_subject=subject, kind=kind, entity_id=entity_id))
    db.commit()


def subscription(db: Session, subject: str) -> ResearchSubscription:
    db.execute(
        insert(ResearchSubscription)
        .values(
            hf_subject=subject,
            enabled=False,
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        .on_conflict_do_nothing()
    )
    db.flush()
    return db.get(ResearchSubscription, subject)


def default_email_on(
    db: Session, subject: str, email: str | None, now: datetime
) -> None:
    """Turn the weekly email on for an account that follows something and never had it on.

    Opting in sets ``opted_in_at`` and turning the email off keeps it, so an
    account that switched the email off or unsubscribed is never re-enabled.
    """
    sub = subscription(db, subject)
    db.refresh(sub, with_for_update=True)
    follows_something = sub.topic_id is not None or db.scalar(
        select(exists().where(ResearchFollow.hf_subject == subject))
    )
    if (
        email
        and not sub.enabled
        and sub.opted_in_at is None
        and follows_something
        and not suppressed(db, email)
    ):
        sub.enabled, sub.email, sub.opted_in_at = True, email, now
    db.commit()


def suppressed(db: Session, email: str | None) -> bool:
    return bool(email and db.get(ResearchSuppression, email.lower()))


def short_summary(tldr: str | None, abstract: str | None) -> str:
    words = re.sub(r"\s+", " ", tldr or abstract or "").strip().split()
    if len(words) <= 60:
        return " ".join(words)
    head = " ".join(words[:60])
    endings = list(re.finditer(r'[.!?](?:["\u201d])?(?=\s|$)', head))
    if endings and endings[-1].end() >= len(head) // 2:
        return head[: endings[-1].end()]
    return head.rstrip(".,;:") + "…"


def diverse(
    entries: list[ResearchEntry], limit: int, rotation: int | None = None
) -> list[ResearchEntry]:
    """Round-robin digest interests; within each prefer strength, date, popularity."""
    ranked = sorted(
        entries,
        key=lambda e: (
            -e.strength,
            -int(e.published.replace("-", "")),
            -e.popularity,
            e.paper_key,
        ),
    )
    interests = sorted({interest for entry in ranked for interest in entry.interests})
    if not interests:
        return []
    if rotation is None:
        positions = {entry.paper_key: index for index, entry in enumerate(ranked)}
        interests.sort(
            key=lambda interest: min(
                positions[e.paper_key] for e in ranked if interest in e.interests
            )
        )
    else:
        offset = rotation % len(interests)
        interests = interests[offset:] + interests[:offset]
    queues = {
        interest: [e for e in ranked if interest in e.interests]
        for interest in interests
    }
    selected, seen = [], set()
    while len(selected) < limit:
        progress = False
        for interest in interests:
            queue = queues[interest]
            while queue and queue[0].paper_key in seen:
                queue.pop(0)
            if queue:
                entry = queue.pop(0)
                seen.add(entry.paper_key)
                selected.append(entry)
                progress = True
                if len(selected) == limit:
                    break
        if not progress:
            break
    return selected


# Match associations on every version, display the latest version, and apply the
# earliest publication date. Recursive UNION (not UNION ALL) tolerates bad cycles.
# A topic matches its Jev verdicts, plus its embedding preview until the backfill is done.
MATCH_SQL = """
WITH RECURSIVE interests AS (
 SELECT kind,entity_id,created_at FROM research_follows WHERE hf_subject=:subject
 UNION ALL
 SELECT 'topic',topic_id,topic_set_at FROM research_subscriptions
 WHERE hf_subject=:subject AND topic_id IS NOT NULL
), descendants(root,id) AS (
 SELECT entity_id,entity_id FROM interests WHERE kind='task'
 UNION SELECT d.root,t.id FROM tasks t JOIN descendants d ON t.parent_id=d.id
), hits AS (
 SELECT 'task'::text kind,d.root entity_id,pt.paper_id,
        CASE WHEN d.root=pt.task_id THEN 2 ELSE 1 END strength
 FROM descendants d JOIN paper_tasks pt ON pt.task_id=d.id
 UNION ALL
 SELECT 'method',i.entity_id,pm.paper_id,2 FROM interests i
 JOIN paper_methods pm ON pm.method_id=i.entity_id WHERE i.kind='method'
 UNION ALL
 SELECT 'author',i.entity_id,pa.paper_id,2 FROM interests i
 JOIN paper_authors pa ON pa.author_id=i.entity_id WHERE i.kind='author'
 UNION ALL
 SELECT 'organization',i.entity_id,po.paper_id,2 FROM interests i
 JOIN paper_organizations po ON po.organization_id=i.entity_id WHERE i.kind='organization'
 UNION ALL
 SELECT 'benchmark',i.entity_id,e.paper_id,2 FROM interests i
 JOIN evaluations e ON e.dataset_id=i.entity_id WHERE i.kind='benchmark'
 UNION ALL
 SELECT 'topic',i.entity_id,v.paper_id,2 FROM interests i
 JOIN research_topic_verdicts v ON v.topic_id=i.entity_id AND v.score>=:topic_threshold
 WHERE i.kind='topic'
 UNION ALL
 SELECT 'topic',i.entity_id,pv.paper_id,2 FROM interests i
 JOIN research_topics t ON t.id=i.entity_id AND t.backfill_status<>'done'
 JOIN research_topic_previews pv ON pv.topic_id=t.id
 WHERE i.kind='topic'
)
SELECT DISTINCT h.kind,h.entity_id,h.strength,i.created_at followed_at,
 p.id,p.arxiv_id,p.title,p.abstract,p.tldr,
 COALESCE((SELECT min(v.date_published) FROM papers v WHERE v.arxiv_id=p.arxiv_id),p.date_published) date_published,
 p.trending_score,
 CASE WHEN p.arxiv_id IS NULL THEN 'paper:' || p.id ELSE 'arxiv:' || p.arxiv_id END paper_key
FROM hits h JOIN interests i USING(kind,entity_id)
JOIN papers source ON source.id=h.paper_id
JOIN papers p ON (source.arxiv_id IS NOT NULL AND p.arxiv_id=source.arxiv_id AND p.is_latest_version)
 OR (source.arxiv_id IS NULL AND p.id=source.id)
WHERE p.date_published BETWEEN :cutoff AND :today
AND NOT EXISTS (SELECT 1 FROM papers old WHERE old.arxiv_id=p.arxiv_id AND old.date_published<:cutoff)
"""


def matching_entries(
    db: Session,
    subject: str,
    now: datetime,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    opted_in_at: datetime | None = None,
    cutoff: date | None = None,
    until: date | None = None,
    paper_ids: list[int] | None = None,
) -> list[ResearchEntry]:
    """Match follows to papers published from ``cutoff`` (default 30 days ago) to ``until``."""
    cutoff = cutoff or (now - timedelta(days=30)).date()
    until = until or now.date()
    interest_map = interests(db, subject)
    if not interest_map:
        return []
    entries, strengths = {}, {}
    # Events are limited to recent discovery; initial catalog backfill is feed-only.
    events = {}
    if window_start is not None:
        for row in db.execute(
            text("""SELECT r.*, e.metrics, e.model_name, d.name dataset_name
            FROM research_events r LEFT JOIN evaluations e ON e.id=r.evaluation_id
            LEFT JOIN datasets d ON d.id=r.dataset_id
            WHERE r.discovered_at >= :start AND r.discovered_at < :end
            AND (r.evaluation_id IS NULL OR e.id IS NOT NULL)"""),
            {"start": window_start, "end": window_end},
        ).mappings():
            events.setdefault(row["paper_key"], []).append(row)
    match_sql = (
        MATCH_SQL if paper_ids is None else MATCH_SQL + "AND p.id = ANY(:paper_ids)"
    )
    for row in db.execute(
        text(match_sql),
        {
            "subject": subject,
            "today": until,
            "cutoff": cutoff,
            "paper_ids": paper_ids,
            "topic_threshold": TOPIC_THRESHOLD,
        },
    ).mappings():
        interest = interest_map.get((row["kind"], row["entity_id"]))
        if interest is None:
            continue
        key = row["paper_key"]
        eligible = []
        if window_start is not None:
            threshold = max(row["followed_at"], opted_in_at or row["followed_at"])
            eligible = [
                e
                for e in events.get(key, [])
                if e["discovered_at"] > threshold
                and (
                    e["evaluation_id"] is None
                    or (
                        row["kind"] == "benchmark"
                        and e["dataset_id"] == row["entity_id"]
                    )
                )
            ]
            if not eligible:
                continue
        entry = entries.setdefault(
            key,
            ResearchEntry(
                paper_key=key,
                title=row["title"],
                url=f"/paper/{row['arxiv_id'] or row['id']}",
                summary=short_summary(row["tldr"], row["abstract"]),
                published=row["date_published"].isoformat(),
                popularity=float(row["trending_score"] or 0),
            ),
        )
        interest_key = f"{interest.kind}:{interest.entity_id}"
        reason = interest.name + (" (subtask)" if row["strength"] == 1 else "")
        previous = strengths.get((key, interest_key), 0)
        if row["strength"] > previous:
            if previous:
                entry.reasons.remove(interest.name + " (subtask)")
            else:
                entry.interests.append(interest_key)
            entry.reasons.append(reason)
            entry.strength += row["strength"] - previous
            strengths[key, interest_key] = row["strength"]
        for event in eligible:
            if event["event_key"] not in entry.events:
                entry.events.append(event["event_key"])
                if event["evaluation_id"]:
                    entry.scores.append(
                        {
                            "benchmark": event["dataset_name"],
                            "model": event["model_name"],
                            "metrics": event["metrics"],
                        }
                    )
    # Feed benchmark scores are current, so corrections render without creating alerts.
    if window_start is None and entries:
        benchmark_ids = [i for (k, i) in interest_map if k == "benchmark"]
        if benchmark_ids:
            for row in db.execute(
                text("""SELECT e.metrics,e.model_name,d.name,
                CASE WHEN p.arxiv_id IS NULL THEN 'paper:' || p.id ELSE 'arxiv:' || p.arxiv_id END paper_key
                FROM evaluations e JOIN datasets d ON d.id=e.dataset_id JOIN papers p ON p.id=e.paper_id
                WHERE e.dataset_id=ANY(:ids) AND p.date_published BETWEEN :cutoff AND :today"""),
                {"ids": benchmark_ids, "cutoff": cutoff, "today": until},
            ).mappings():
                if row["paper_key"] in entries:
                    score = {
                        "benchmark": row["name"],
                        "model": row["model_name"],
                        "metrics": row["metrics"],
                    }
                    if score not in entries[row["paper_key"]].scores:
                        entries[row["paper_key"]].scores.append(score)
    return list(entries.values())


def feed_entries(
    db: Session,
    subject: str,
    now: datetime,
    offset: int,
    limit: int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    all_time: bool = False,
    has_code: bool = False,
    has_hf_artifacts: bool = False,
    topic_only: bool = False,
) -> list[ResearchFeedEntry]:
    """Filter and rank matches like the home feed, then explain only the returned page."""
    from backend.services.paper_service import PaperService

    cutoff = date.min if all_time else start_date or (now - timedelta(days=30)).date()
    until = min(end_date or now.date(), now.date())
    matches = (
        text(MATCH_SQL)
        .bindparams(
            subject=subject,
            today=until,
            cutoff=cutoff,
            topic_threshold=TOPIC_THRESHOLD,
        )
        .columns(column("id", Integer), column("kind", String))
        .subquery("matches")
    )
    matched_ids = select(matches.c.id)
    if topic_only:
        matched_ids = matched_ids.where(matches.c.kind == "topic")
    service = PaperService(db)
    query = db.query(DBPaper).filter(DBPaper.id.in_(matched_ids))
    if has_code:
        query = service.apply_has_code_filter(query)
    if has_hf_artifacts:
        query = service.apply_has_hf_artifacts_filter(query)
    rows = service.apply_scoped_trending_order(query).offset(offset).limit(limit).all()
    if not rows:
        return []
    entries = {
        e.paper_key: e
        for e in matching_entries(
            db, subject, now, cutoff=cutoff, until=until, paper_ids=[r.id for r in rows]
        )
    }
    papers = service.hydrate_cards(rows, include_resources=True)
    return [
        ResearchFeedEntry(
            **entries[
                f"arxiv:{p.arxiv_id}" if p.arxiv_id else f"paper:{p.id}"
            ].model_dump(),
            paper=p,
        )
        for p in papers
    ]
