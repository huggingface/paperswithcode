import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.papers import Paper
from backend.services.paper_service import PaperService

logger = logging.getLogger(__name__)

TRENDING_RANK_LIMIT = 25
TRENDING_WINDOW_DAYS = 7
CACHE_TTL_SECONDS = 300
RETRY_AFTER_FAILURE_SECONDS = 60

_lock = threading.Lock()
_state: dict[str, object] = {
    "day": None,
    "expires_at": 0.0,
    "ranks": {},
    "refreshing": False,
}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _load_ranks(db: Session, today: date) -> dict[int, int]:
    paper_ids = PaperService(db).trending_paper_ids(
        TRENDING_RANK_LIMIT,
        published_after=today - timedelta(days=TRENDING_WINDOW_DAYS - 1),
        published_before=today,
    )
    return {paper_id: rank for rank, paper_id in enumerate(paper_ids, start=1)}


def trending_ranks(db: Session) -> dict[int, int]:
    today = _today()
    with _lock:
        current = _state["ranks"] if _state["day"] == today else {}
        if _state["refreshing"] or (
            _state["day"] == today and _state["expires_at"] > time.monotonic()
        ):
            return current
        _state["refreshing"] = True
    ranks, ttl = current, RETRY_AFTER_FAILURE_SECONDS
    try:
        ranks, ttl = _load_ranks(db, today), CACHE_TTL_SECONDS
    except SQLAlchemyError:
        db.rollback()
        logger.warning("Trending rank refresh failed", exc_info=True)
    finally:
        with _lock:
            _state.update(
                day=today,
                expires_at=time.monotonic() + ttl,
                ranks=ranks,
                refreshing=False,
            )
    return ranks


def with_trending_rank(db: Session, paper: Paper) -> Paper:
    if paper.is_latest_version:
        paper.trending_rank = trending_ranks(db).get(int(paper.id))
    return paper


def reset_trending_rank_cache() -> None:
    with _lock:
        _state.update(day=None, expires_at=0.0, ranks={}, refreshing=False)
