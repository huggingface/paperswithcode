"""Refresh like counts of linked X posts during their first week.

Each post linked to a paper (`paper_x_threads`) gets one `x_post_metrics` row,
read at about 1, 2, 4, 8, 12, 24, 48, 72, 120 and 144 hours after posting. Reads
use X's free embed syndication endpoint first; posts it cannot serve fall back
to paid X API lookups, which the caller caps per day. Each reading updates an
EMA of likes per hour that `calculate_paper_trending_scores` turns into the X
part of the paper trending score. Posts older than a week are never read.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import httpx
from sqlalchemy import func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.models.database import PaperXThread, XPostMetrics
from backend.services.x_thread_service import SYNDICATION_URL
from backend.utils.trending import X_POST_WINDOW_DAYS

logger = logging.getLogger(__name__)

READ_OFFSETS = tuple(
    timedelta(hours=hours) for hours in (1, 2, 4, 8, 12, 24, 48, 72, 120, 144)
)
TRACKING_WINDOW = timedelta(days=X_POST_WINDOW_DAYS)
# Same smoothing as the GitHub star velocity EMA.
ALPHA = 0.75
MIN_READING_HOURS = 0.25
X_TWEETS_URL = "https://api.x.com/2/tweets"
API_BATCH_SIZE = 100
SYNDICATION_INTERVAL_SECONDS = 0.25

# Returns the like count, or None when syndication cannot serve the post.
SyndicationRead = Callable[[str], "int | None"]
# Returns (like counts by id, ids X reports as unavailable).
ApiRead = Callable[[list[str]], "tuple[dict[str, int], set[str]]"]


class SyndicationRateLimited(Exception):
    """Syndication answered HTTP 429; stop using it for this run."""


@dataclass
class RefreshReport:
    enrolled: int = 0
    due: int = 0
    syndication_reads: int = 0
    api_reads: int = 0
    gone: int = 0
    unread: int = 0
    expired: int = 0
    api_error: str | None = None
    velocities: dict[str, float] = field(default_factory=dict)


def next_read_at(posted_at: datetime, now: datetime) -> datetime | None:
    """The first scheduled reading after ``now``, or None once the schedule ends."""
    for offset in READ_OFFSETS:
        if posted_at + offset > now:
            return posted_at + offset
    return None


def like_velocity(metrics: XPostMetrics, like_count: int, now: datetime) -> float:
    """Smoothed likes per hour after a new reading.

    The first reading has nothing to compare against, so it uses the lifetime
    average; later readings blend the rate since the previous one into the EMA.
    """
    if metrics.like_count is None or metrics.last_read_at is None:
        hours = max((now - metrics.posted_at).total_seconds() / 3600, 1.0)
        return like_count / hours
    hours = max((now - metrics.last_read_at).total_seconds() / 3600, MIN_READING_HOURS)
    raw = max(like_count - metrics.like_count, 0) / hours
    return ALPHA * raw + (1 - ALPHA) * (metrics.like_velocity or 0.0)


def enroll_posts(db: Session, now: datetime) -> int:
    """Add a due row for every linked post from the last week that has none."""
    recent = (
        select(
            PaperXThread.tweet_id,
            func.min(PaperXThread.posted_at),
            literal(now),
        )
        .where(PaperXThread.posted_at >= now - TRACKING_WINDOW)
        .group_by(PaperXThread.tweet_id)
    )
    result = db.execute(
        insert(XPostMetrics)
        .from_select(["tweet_id", "posted_at", "next_read_at"], recent)
        .on_conflict_do_nothing(index_elements=["tweet_id"])
    )
    return result.rowcount


def expire_posts(db: Session, now: datetime) -> int:
    """Stop reading posts that left the window while a reading was pending."""
    result = db.execute(
        update(XPostMetrics)
        .where(
            XPostMetrics.next_read_at.is_not(None),
            XPostMetrics.posted_at < now - TRACKING_WINDOW,
        )
        .values(next_read_at=None)
    )
    return result.rowcount


def due_posts(db: Session, now: datetime, limit: int) -> list[XPostMetrics]:
    return list(
        db.scalars(
            select(XPostMetrics)
            .where(
                XPostMetrics.next_read_at <= now,
                XPostMetrics.gone_at.is_(None),
            )
            .order_by(XPostMetrics.next_read_at, XPostMetrics.tweet_id)
            .limit(limit)
        )
    )


def record_reading(
    metrics: XPostMetrics, like_count: int, source: str, now: datetime
) -> None:
    metrics.like_velocity = like_velocity(metrics, like_count, now)
    metrics.like_count = like_count
    metrics.last_read_at = now
    metrics.last_source = source
    metrics.read_count = (metrics.read_count or 0) + 1
    metrics.next_read_at = next_read_at(metrics.posted_at, now)


def refresh_likes(
    db: Session,
    *,
    now: datetime,
    read_syndication: SyndicationRead,
    read_api: ApiRead | None,
    api_budget: int,
    max_posts: int,
) -> RefreshReport:
    """Enroll new posts and read every due post; the caller commits or rolls back."""
    report = RefreshReport(
        enrolled=enroll_posts(db, now), expired=expire_posts(db, now)
    )
    due = due_posts(db, now, max_posts)
    report.due = len(due)

    fallback: list[XPostMetrics] = []
    for index, metrics in enumerate(due):
        try:
            like_count = read_syndication(metrics.tweet_id)
        except SyndicationRateLimited:
            logger.warning("x_likes_syndication_rate_limited after=%d", index)
            fallback.extend(due[index:])
            break
        if like_count is None:
            fallback.append(metrics)
            continue
        record_reading(metrics, like_count, "syndication", now)
        report.syndication_reads += 1

    paid = fallback[:api_budget] if read_api else []
    for start in range(0, len(paid), API_BATCH_SIZE):
        batch = paid[start : start + API_BATCH_SIZE]
        try:
            counts, unavailable = read_api([metrics.tweet_id for metrics in batch])
        except httpx.HTTPError as error:
            report.api_error = str(error)
            logger.warning("x_likes_api_failed error=%s", error)
            break
        report.api_reads += len(batch)
        for metrics in batch:
            if metrics.tweet_id in counts:
                record_reading(metrics, counts[metrics.tweet_id], "api", now)
            elif metrics.tweet_id in unavailable:
                metrics.gone_at = now
                metrics.next_read_at = None
                metrics.like_velocity = 0.0
                report.gone += 1

    read = [metrics for metrics in due if metrics.last_read_at == now]
    report.unread = len(due) - len(read) - report.gone
    report.velocities = {
        metrics.tweet_id: round(metrics.like_velocity, 3) for metrics in read
    }
    db.flush()
    return report


def make_syndication_reader(client: httpx.Client) -> SyndicationRead:
    """Read like counts from the public embed endpoint, pacing requests."""

    def read(tweet_id: str) -> int | None:
        time.sleep(SYNDICATION_INTERVAL_SECONDS)
        try:
            response = client.get(
                SYNDICATION_URL,
                params={"id": tweet_id, "lang": "en", "token": "a"},
                timeout=10,
            )
        except httpx.HTTPError as error:
            logger.info("x_likes_syndication_failed id=%s error=%s", tweet_id, error)
            return None
        if response.status_code == 429:
            raise SyndicationRateLimited()
        if response.status_code != 200 or not response.headers.get(
            "content-type", ""
        ).startswith("application/json"):
            return None
        post = response.json()
        if post.get("__typename") != "Tweet" or post.get("favorite_count") is None:
            return None
        return int(post["favorite_count"])

    return read


def make_api_reader(client: httpx.Client, bearer_token: str) -> ApiRead:
    """Batch-read like counts with the X API (billed per post returned)."""

    def read(tweet_ids: list[str]) -> tuple[dict[str, int], set[str]]:
        response = client.get(
            X_TWEETS_URL,
            params={"ids": ",".join(tweet_ids), "tweet.fields": "public_metrics"},
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        counts = {
            post["id"]: int(post["public_metrics"]["like_count"])
            for post in payload.get("data", [])
        }
        # Deleted, protected, or suspended posts come back as per-id errors.
        unavailable = {
            error["resource_id"]
            for error in payload.get("errors", [])
            if error.get("resource_id")
        } - set(counts)
        return counts, unavailable

    return read
