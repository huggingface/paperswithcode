import threading
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.models.papers import Paper
from backend.services.paper_service import PaperService

TRENDING_RANK_LIMIT = 25
TRENDING_WINDOW_DAYS = 7
CACHE_TTL_SECONDS = 300

_lock = threading.Lock()
_cache: dict[str, object] = {"day": None, "expires_at": 0.0, "ranks": {}}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def trending_ranks(db: Session) -> dict[int, int]:
    today = _today()
    with _lock:
        if _cache["day"] == today and _cache["expires_at"] > time.monotonic():
            return _cache["ranks"]
        paper_ids = PaperService(db).trending_paper_ids(
            TRENDING_RANK_LIMIT,
            published_after=today - timedelta(days=TRENDING_WINDOW_DAYS - 1),
            published_before=today,
        )
        ranks = {paper_id: rank for rank, paper_id in enumerate(paper_ids, start=1)}
        _cache.update(
            day=today, expires_at=time.monotonic() + CACHE_TTL_SECONDS, ranks=ranks
        )
        return ranks


def with_trending_rank(db: Session, paper: Paper) -> Paper:
    if paper.is_latest_version:
        paper.trending_rank = trending_ranks(db).get(int(paper.id))
    return paper


def reset_trending_rank_cache() -> None:
    with _lock:
        _cache.update(day=None, expires_at=0.0, ranks={})
