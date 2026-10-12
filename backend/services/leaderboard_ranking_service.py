"""Server-side port of the benchmark page's default leaderboard ranking.

The SPA ranks leaderboards in ``frontend/src/lib/leaderboardPresentation.ts``
and ``frontend/src/lib/benchmarkLeaderboard.ts``. Crawlable benchmark HTML must
show the same order, so this module mirrors the default view of that logic (no
metric override, highlighted row, closed-source filter, or parameter filter).
Keep both implementations in step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cmp_to_key
from typing import Any, Optional, Sequence

_LEADING_FLOAT_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_MISSING_RANK = 9999


@dataclass(frozen=True)
class RankableTask:
    id: int
    slug: Optional[str]
    name: str


@dataclass(frozen=True)
class RankableEvaluation:
    """One evaluation row, in the API's ``ordering=best_rank`` order."""

    id: int
    paper_id: int
    task_id: int
    model_name: Optional[str]
    harness: Optional[str]
    metrics: dict[str, Any]
    best_metric: Optional[str]
    best_rank: Optional[int]


@dataclass
class MergedEntry:
    """Display row folding evaluations that differ only in ``best_metric``."""

    first: RankableEvaluation
    metrics: dict[str, Any]
    ranks_by_metric: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RankedEntry:
    entry: MergedEntry
    rank: Optional[int]
    value: Optional[float]
    raw_value: Any


@dataclass(frozen=True)
class RankedLeaderboard:
    task: Optional[RankableTask]
    metric: str
    lower_is_better: bool
    rows: tuple[RankedEntry, ...]


def parse_metric_value(raw: Any) -> Optional[float]:
    """Mirror the SPA's ``parseMetricValue`` (JavaScript ``parseFloat``)."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw == raw and abs(raw) != float("inf") else None
    text = str(raw)
    if "±" in text:
        text = text.split("±", 1)[0]
    match = _LEADING_FLOAT_RE.match(text.strip())
    return float(match.group()) if match else None


def resolve_task(
    tasks: Sequence[RankableTask],
    evaluations: Sequence[RankableEvaluation],
    task_slug: Optional[str] = None,
) -> Optional[RankableTask]:
    """Mirror ``resolveLeaderboardTask``; ``tasks`` are ordered by name."""
    if not tasks:
        return None
    if task_slug:
        for task in tasks:
            if task.slug == task_slug:
                return task
    if len(tasks) == 1:
        return tasks[0]
    if evaluations:
        counts: dict[int, int] = {}
        for evaluation in evaluations:
            counts[evaluation.task_id] = counts.get(evaluation.task_id, 0) + 1
        top, top_n = None, -1
        for task in tasks:
            if counts.get(task.id, 0) > top_n:
                top, top_n = task, counts.get(task.id, 0)
        return top
    return tasks[0]


def merge_evaluations(
    evaluations: Sequence[RankableEvaluation],
) -> list[MergedEntry]:
    """Mirror ``mergeLeaderboardEvaluations``."""
    groups: dict[tuple, MergedEntry] = {}
    for evaluation in evaluations:
        key = (
            evaluation.paper_id,
            evaluation.task_id,
            evaluation.model_name or "",
            evaluation.harness or "",
        )
        entry = groups.get(key)
        if entry is None:
            entry = groups[key] = MergedEntry(
                evaluation, dict(evaluation.metrics or {})
            )
        else:
            entry.metrics.update(evaluation.metrics or {})
        if evaluation.best_metric and evaluation.best_rank is not None:
            entry.ranks_by_metric[evaluation.best_metric] = evaluation.best_rank
    return list(groups.values())


def rank_leaderboard(
    *,
    tasks: Sequence[RankableTask],
    evaluations: Sequence[RankableEvaluation],
    configured_metrics: dict[int, list[str]],
    directions: dict[str, str],
    task_slug: Optional[str] = None,
) -> RankedLeaderboard:
    """Rank one benchmark exactly as the SPA's default leaderboard view does.

    ``configured_metrics`` maps task id to the leaderboard's configured metric
    names, ordered like ``GET /datasets/{id}/tasks/{task_id}/metrics``.
    """
    task = resolve_task(tasks, evaluations, task_slug)
    current = [e for e in evaluations if e.task_id == task.id] if task else evaluations
    entries = merge_evaluations(current)
    configured = configured_metrics.get(task.id, []) if task else []
    data_metrics: list[str] = []
    for entry in entries:
        for metric in (
            [entry.first.best_metric] if entry.first.best_metric else []
        ) + list(entry.metrics):
            if metric not in data_metrics:
                data_metrics.append(metric)
    allowed = configured or data_metrics
    counts: dict[str, int] = {}
    for entry in entries:
        metric = entry.first.best_metric
        if not metric or parse_metric_value(entry.metrics.get(metric)) is None:
            continue
        if configured and metric not in allowed:
            continue
        counts[metric] = counts.get(metric, 0) + 1
    metric = ""
    if counts:
        metric = max(counts, key=lambda name: counts[name])
    elif allowed:
        metric = allowed[0]
    lower_is_better = directions.get(metric) == "lower_is_better"

    def compare(a: MergedEntry, b: MergedEntry) -> float:
        va = parse_metric_value(a.metrics.get(metric))
        vb = parse_metric_value(b.metrics.get(metric))
        if va is not None and vb is not None:
            return va - vb if lower_is_better else vb - va
        if va is not None:
            return -1
        if vb is not None:
            return 1
        return _stored_rank(a, metric) - _stored_rank(b, metric)

    rows = []
    last_value: Optional[float] = None
    last_rank = 0
    for index, entry in enumerate(sorted(entries, key=cmp_to_key(compare))):
        raw = entry.metrics.get(metric)
        value = parse_metric_value(raw)
        if value is not None and value != last_value:
            last_value = value
            last_rank = index + 1
        rows.append(
            RankedEntry(entry, None if value is None else last_rank, value, raw)
        )
    return RankedLeaderboard(task, metric, lower_is_better, tuple(rows))


def _stored_rank(entry: MergedEntry, metric: str) -> int:
    rank = entry.ranks_by_metric.get(metric)
    if rank is None:
        rank = entry.first.best_rank
    return _MISSING_RANK if rank is None else rank
