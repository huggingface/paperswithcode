"""Task "Start here" reading paths: curated rows first, automatic fallback."""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import desc, func
from sqlalchemy.orm import Query, Session

from backend.models.database import (
    Paper as DBPaper,
    PaperTask,
    Task as DBTask,
    TaskReadingPathPaper,
)
from backend.models.reading_paths import (
    ReadingPathPaper,
    ReadingPathStep,
    TaskReadingPath,
)
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService

SURVEY_TITLE_PATTERN = r"(^|[^a-z])(survey|review)"
OVERVIEW_LIMIT = 1
FOUNDATIONS_LIMIT = 3
RECENT_LIMIT = 3
FOUNDATIONS_MIN_AGE = timedelta(days=3 * 365)
RECENT_MAX_AGE = timedelta(days=365)
CACHE_TTL_SECONDS = 600
CACHE_MAX_ENTRIES = 512
_cache: OrderedDict[tuple[int, date], tuple[float, TaskReadingPath]] = OrderedDict()
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class StepSpec:
    kind: str
    title: str
    description: str


STEPS = (
    StepSpec(
        "overview",
        "Get an overview",
        "A survey or introduction that maps out the field.",
    ),
    StepSpec(
        "foundations",
        "Build the foundations",
        "Papers that introduced the key ideas everything else builds on.",
    ),
    StepSpec(
        "recent",
        "Explore recent work",
        "Where the field is now.",
    ),
)


class ReadingPathService:
    def __init__(self, db: Session):
        self.db = db
        self.papers = PaperService(db)

    def get_reading_path(
        self, task_identifier: str, today: date | None = None
    ) -> TaskReadingPath:
        task = TaskService(self.db).require_db_task(task_identifier)
        today = today or date.today()
        key = (task.id, today)
        with _cache_lock:
            cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        path = self._build(task, today)
        with _cache_lock:
            _cache[key] = (time.monotonic(), path)
            _cache.move_to_end(key)
            while len(_cache) > CACHE_MAX_ENTRIES:
                _cache.popitem(last=False)
        return path

    def _build(self, task: DBTask, today: date) -> TaskReadingPath:
        curated = self._curated_rows(task.id)
        chosen: set[int] = {paper.id for _, paper in curated}
        steps = []
        for spec in STEPS:
            rows = [pair for pair in curated if pair[0].step == spec.kind]
            if rows:
                papers = self.papers.hydrate_cards([paper for _, paper in rows])
                entries = [
                    ReadingPathPaper(paper=paper, note=row.note)
                    for paper, (row, _) in zip(papers, rows)
                ]
                source = "curated"
            else:
                picks = self._automatic(spec.kind, task, chosen, today)
                chosen.update(paper.id for paper in picks)
                entries = [
                    ReadingPathPaper(paper=paper)
                    for paper in self.papers.hydrate_cards(picks)
                ]
                source = "automatic"
            if entries:
                steps.append(
                    ReadingPathStep(
                        kind=spec.kind,
                        title=spec.title,
                        description=spec.description,
                        source=source,
                        papers=entries,
                    )
                )
        return TaskReadingPath(
            task_id=str(task.id),
            task_slug=task.slug,
            source="curated" if curated else "automatic",
            steps=steps,
        )

    def _curated_rows(self, task_id: int) -> list[tuple[TaskReadingPathPaper, DBPaper]]:
        return (
            self.db.query(TaskReadingPathPaper, DBPaper)
            .join(DBPaper, DBPaper.id == TaskReadingPathPaper.paper_id)
            .filter(TaskReadingPathPaper.task_id == task_id)
            .order_by(TaskReadingPathPaper.position, TaskReadingPathPaper.paper_id)
            .all()
        )

    def _task_papers(self, task_id: int, exclude: set[int]) -> Query[DBPaper]:
        query = (
            self.db.query(DBPaper)
            .join(PaperTask, PaperTask.paper_id == DBPaper.id)
            .filter(PaperTask.task_id == task_id, DBPaper.is_latest_version)
        )
        if exclude:
            query = query.filter(DBPaper.id.notin_(exclude))
        return query

    def _automatic(
        self, kind: str, task: DBTask, exclude: set[int], today: date
    ) -> list[DBPaper]:
        query = self._task_papers(task.id, exclude)
        if kind == "overview":
            names_task = DBPaper.title.ilike(f"%{task.name}%")
            return (
                query.filter(
                    func.lower(DBPaper.title).regexp_match(SURVEY_TITLE_PATTERN),
                    DBPaper.citation_count > 0,
                )
                .order_by(desc(names_task), desc(DBPaper.citation_count))
                .limit(OVERVIEW_LIMIT)
                .all()
            )
        if kind == "foundations":
            return (
                query.filter(
                    DBPaper.date_published <= today - FOUNDATIONS_MIN_AGE,
                    DBPaper.citation_count > 0,
                )
                .order_by(desc(DBPaper.citation_count), DBPaper.id)
                .limit(FOUNDATIONS_LIMIT)
                .all()
            )
        recent = query.filter(DBPaper.date_published >= today - RECENT_MAX_AGE)
        return self.papers.apply_scoped_trending_order(recent).limit(RECENT_LIMIT).all()
