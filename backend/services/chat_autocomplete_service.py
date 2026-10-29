"""Catalog names that chat composers complete as visitors type."""

from __future__ import annotations

import threading
import time

from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Method,
    PaperMethod,
    PaperTask,
    Task,
)

_VOCABULARY_TTL_SECONDS = 3600
_VOCABULARY_LIMIT = 5000
_cache_lock = threading.Lock()
_cached: tuple[float, list[str]] | None = None


def _load_vocabulary(db: Session) -> list[str]:
    task_papers = (
        select(PaperTask.task_id, func.count().label("uses"))
        .group_by(PaperTask.task_id)
        .subquery()
    )
    method_papers = (
        select(PaperMethod.method_id, func.count().label("uses"))
        .group_by(PaperMethod.method_id)
        .subquery()
    )
    benchmark_rows = (
        select(Evaluation.dataset_id, func.count().label("uses"))
        .group_by(Evaluation.dataset_id)
        .subquery()
    )
    names = union_all(
        select(Task.name, task_papers.c.uses).join(
            task_papers, task_papers.c.task_id == Task.id
        ),
        *(
            select(name, method_papers.c.uses).join(
                method_papers, method_papers.c.method_id == Method.id
            )
            for name in (Method.name, Method.full_name)
        ),
        *(
            select(name, benchmark_rows.c.uses).join(
                benchmark_rows, benchmark_rows.c.dataset_id == Dataset.id
            )
            for name in (Dataset.name, Dataset.full_name)
        ),
    ).subquery()
    rows = db.execute(
        select(names.c.name).order_by(names.c.uses.desc(), names.c.name)
    ).scalars()

    seen: set[str] = set()
    vocabulary: list[str] = []
    for raw in rows:
        if not raw:
            continue
        name = " ".join(raw.split())
        if len(name) < 2 or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        vocabulary.append(name)
        if len(vocabulary) == _VOCABULARY_LIMIT:
            break
    return vocabulary


def get_autocomplete_vocabulary(db: Session) -> list[str]:
    """Task, method, and benchmark names (and full names) in use, most used first."""
    global _cached
    with _cache_lock:
        if _cached and time.monotonic() - _cached[0] < _VOCABULARY_TTL_SECONDS:
            return _cached[1]
    vocabulary = _load_vocabulary(db)
    with _cache_lock:
        _cached = (time.monotonic(), vocabulary)
    return vocabulary
