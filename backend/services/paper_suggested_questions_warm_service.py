"""Pre-generate suggested questions for the papers visitors see first.

Paper pages generate their questions on first view, which makes the first
visitor wait and drops them when the API is busy. This fills the cache ahead
of time for the first pages of the default (trending) feeds: the home feed's
past week, then every task and method page, busiest pages first.
"""

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.database import Paper as DBPaper
from backend.models.database import PaperMethod, PaperSuggestedQuestions, PaperTask
from backend.services.method_service import MethodService
from backend.services.paper_service import PaperService
from backend.services.paper_suggested_questions_service import (
    generate_suggested_questions,
    store_suggested_questions,
)
from backend.services.task_service import TaskService

logger = logging.getLogger(__name__)

# Mirrors the frontend defaults: FeedView (30 per page, past week, trending)
# and the task/method pages (20 per page, all time, trending).
HOME_PAGES = 3
HOME_PAGE_SIZE = 30
ENTITY_PAGE_SIZE = 20


def visible_paper_ids(db: Session, today: date) -> list[int]:
    """Paper IDs in the order visitors meet them, without duplicates."""
    ordered: dict[int, None] = {}
    papers = PaperService(db)
    for page in range(1, HOME_PAGES + 1):
        feed = papers.get_papers(
            page=page,
            page_size=HOME_PAGE_SIZE,
            order_by="trending",
            start_date=today - timedelta(days=6),
            end_date=today,
        )
        ordered.update((int(paper.id), None) for paper in feed.results)

    tasks, methods = TaskService(db), MethodService(db)
    feeds = {"task": tasks.get_task_papers, "method": methods.get_method_papers}
    for kind, entity_id in _entities_by_paper_count(db):
        feed = feeds[kind](
            str(entity_id), page_size=ENTITY_PAGE_SIZE, order_by="trending"
        )
        ordered.update((int(paper.id), None) for paper in feed.results)
    return list(ordered)


def _entities_by_paper_count(db: Session) -> list[tuple[str, int]]:
    """Tasks and methods with papers, most papers first."""
    counts = [
        (count, "task", task_id)
        for task_id, count in db.execute(
            select(PaperTask.task_id, func.count()).group_by(PaperTask.task_id)
        )
    ] + [
        (count, "method", method_id)
        for method_id, count in db.execute(
            select(PaperMethod.method_id, func.count()).group_by(PaperMethod.method_id)
        )
    ]
    counts.sort(key=lambda row: (-row[0], row[1], row[2]))
    return [(kind, entity_id) for _count, kind, entity_id in counts]


def warm_suggested_questions(
    db: Session,
    paper_ids: list[int],
    *,
    client: httpx.Client,
    api_key: str,
    limit: int,
    workers: int = 4,
) -> Counter:
    """Generate questions for up to `limit` papers that lack them, in order."""
    stats = Counter(candidates=len(paper_ids))
    stored = set(
        db.scalars(
            select(PaperSuggestedQuestions.paper_id).where(
                PaperSuggestedQuestions.paper_id.in_(paper_ids)
            )
        )
    )
    stats["already_stored"] = len(stored)
    rows = {
        row.id: row
        for row in db.execute(
            select(DBPaper.id, DBPaper.title, DBPaper.abstract).where(
                DBPaper.id.in_(set(paper_ids) - stored)
            )
        )
    }
    eligible = [
        rows[paper_id]
        for paper_id in paper_ids
        if paper_id in rows and (rows[paper_id].abstract or "").strip()
    ]
    todo = eligible[:limit]
    stats["remaining"] = len(eligible) - len(todo)

    def generate(row) -> tuple[int, list[str]]:
        try:
            return row.id, generate_suggested_questions(
                client, row.title, row.abstract, api_key=api_key
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("suggested_questions_failed paper_id=%s: %s", row.id, exc)
            return row.id, []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for paper_id, questions in pool.map(generate, todo):
            stored_now = store_suggested_questions(db, paper_id, questions)
            stats["generated" if stored_now else "failed"] += 1
    return stats
