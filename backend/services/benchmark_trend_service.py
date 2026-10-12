"""Task-scoped benchmark trends derived from evaluation-reporting papers."""

import math
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from backend.models.taxonomy import (
    BenchmarkTrendPoint,
    TrendingBenchmark,
    TrendingBenchmarks,
)
from backend.models.database import (
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    Task as DBTask,
    TaskDataset,
)
from backend.services.dataset_service import DatasetService
from backend.services.catalog_errors import CatalogNotFoundError
from backend.utils.task_hierarchy import collect_descendant_task_ids
from backend.utils.task_slugs import task_slug_candidates

_SUPPORT_PRIOR_PAPERS = 2.0


def _support_weighted_score(
    recent: int,
    baseline: int,
    *,
    recent_days: int,
    baseline_days: int,
) -> float:
    baseline_equivalent = baseline * recent_days / baseline_days
    smoothed_lift = (recent + _SUPPORT_PRIOR_PAPERS) / (
        baseline_equivalent + _SUPPORT_PRIOR_PAPERS
    )
    return math.log1p(recent) * smoothed_lift


class BenchmarkTrendService:
    """Rank benchmarks by support-weighted reporting-velocity changes."""

    def __init__(self, db: Session):
        self.db = db

    def get_trending_benchmarks(
        self,
        task_id: str,
        *,
        limit: int = 20,
        recent_days: int = 90,
        baseline_days: int = 180,
        min_recent_papers: int = 1,
        include_descendants: bool = False,
        bucket_days: int = 30,
        history_buckets: int = 6,
        is_open: bool | None = None,
        today: date | None = None,
    ) -> TrendingBenchmarks:
        """Return recent benchmark reporting activity for one task.

        A paper counts once per benchmark regardless of how many models,
        harnesses, or metric rows it reports. Publication dates, rather than
        evaluation-row creation timestamps, keep backfilled historical results
        from looking newly trendy.

        The ranking score weights a smoothed rate change by recent evidence::

            baseline_equivalent = baseline * recent_days / baseline_days
            smoothed_lift = (recent + 2) / (baseline_equivalent + 2)
            support_weighted_score = ln(1 + recent) * smoothed_lift

        The raw rate change remains available for display. The two-paper neutral
        prior keeps sparse and no-baseline benchmarks finite, while ``ln(1 +
        recent)`` rewards trends supported by more recent reporting papers.

        The database currently has evaluation evidence but no paper-reference
        edge table. The response therefore identifies its signal as
        ``evaluation_reports`` and does not infer citations to introducing
        papers.
        """
        task = self._resolve_task(task_id)
        generated_on = today or datetime.now(UTC).date()
        recent_start = generated_on - timedelta(days=recent_days)
        baseline_start = recent_start - timedelta(days=baseline_days)
        scoped_task_ids = (
            collect_descendant_task_ids(self.db, task.id)
            if include_descendants
            else [task.id]
        )

        in_recent = and_(
            DBPaper.date_published > recent_start,
            DBPaper.date_published <= generated_on,
        )
        in_baseline = and_(
            DBPaper.date_published > baseline_start,
            DBPaper.date_published <= recent_start,
        )
        recent_count = func.count(
            func.distinct(case((in_recent, DBPaper.id), else_=None))
        )
        baseline_count = func.count(
            func.distinct(case((in_baseline, DBPaper.id), else_=None))
        )

        rows = (
            self.db.query(
                DBDataset,
                recent_count.label("recent_count"),
                baseline_count.label("baseline_count"),
                func.count(func.distinct(DBPaper.id)).label("all_time_count"),
                func.max(DBPaper.date_published).label("latest_reported_on"),
            )
            .join(TaskDataset, TaskDataset.dataset_id == DBDataset.id)
            .outerjoin(
                DBEvaluation,
                and_(
                    DBEvaluation.dataset_id == DBDataset.id,
                    DBEvaluation.task_id.in_(scoped_task_ids),
                ),
            )
            .outerjoin(
                DBPaper,
                and_(
                    DBPaper.id == DBEvaluation.paper_id,
                    DBPaper.is_latest_version,
                ),
            )
            .filter(TaskDataset.task_id.in_(scoped_task_ids))
            .group_by(DBDataset.id)
            .having(recent_count >= min_recent_papers)
            .all()
        )

        history = self._history_by_dataset(
            scoped_task_ids=scoped_task_ids,
            dataset_ids=[row[0].id for row in rows],
            generated_on=generated_on,
            bucket_days=bucket_days,
            history_buckets=history_buckets,
        )
        best_results = DatasetService(self.db)._best_results_for_datasets(
            [row[0].id for row in rows],
            scoped_task_ids,
            is_open=is_open,
        )

        results = []
        for (
            dataset,
            recent,
            baseline,
            all_time,
            latest_reported_on,
        ) in rows:
            recent = int(recent or 0)
            baseline = int(baseline or 0)
            recent_velocity = recent * 30.0 / recent_days
            baseline_velocity = baseline * 30.0 / baseline_days
            support_weighted_score = _support_weighted_score(
                recent,
                baseline,
                recent_days=recent_days,
                baseline_days=baseline_days,
            )
            best_result = best_results.get(dataset.id, {})
            results.append(
                TrendingBenchmark(
                    id=dataset.id,
                    name=dataset.name,
                    slug=dataset.slug,
                    full_name=dataset.full_name,
                    description=dataset.description,
                    hf_url=dataset.hf_url,
                    recent_paper_count=recent,
                    baseline_paper_count=baseline,
                    all_time_paper_count=int(all_time or 0),
                    trend_score=round(recent_velocity, 4),
                    support_weighted_score=round(support_weighted_score, 4),
                    rate_change=(
                        round(recent_velocity / baseline_velocity, 4)
                        if baseline_velocity
                        else None
                    ),
                    latest_reported_on=latest_reported_on,
                    best_model_name=best_result.get("model_name"),
                    best_paper_route=best_result.get("paper_route"),
                    best_paper_title=best_result.get("paper_title"),
                    best_code_url=best_result.get("code_url"),
                    history=history.get(dataset.id, []),
                )
            )

        def ranking_key(item: TrendingBenchmark) -> tuple:
            latest_ordinal = (item.latest_reported_on or date.min).toordinal()
            return (
                -item.support_weighted_score,
                -item.recent_paper_count,
                -latest_ordinal,
                -item.all_time_paper_count,
                item.name.casefold(),
            )

        results.sort(key=ranking_key)

        return TrendingBenchmarks(
            task_id=task.id,
            task_slug=task.slug,
            recent_days=recent_days,
            baseline_days=baseline_days,
            bucket_days=bucket_days,
            support_prior_papers=_SUPPORT_PRIOR_PAPERS,
            generated_on=generated_on,
            results=results[:limit],
        )

    def _resolve_task(self, task_id: str) -> DBTask:
        if str(task_id).isdigit():
            task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
        else:
            task = None
            for candidate in task_slug_candidates(str(task_id)):
                task = (
                    self.db.query(DBTask)
                    .filter(func.lower(DBTask.slug) == candidate.lower())
                    .order_by(DBTask.id)
                    .first()
                )
                if task is not None:
                    break
            if task is None:
                task = (
                    self.db.query(DBTask)
                    .filter(func.lower(DBTask.name) == str(task_id).lower())
                    .order_by(DBTask.id)
                    .first()
                )
        if task is None:
            raise CatalogNotFoundError(
                f"Task with ID, slug, or name '{task_id}' not found"
            )
        return task

    def _history_by_dataset(
        self,
        *,
        scoped_task_ids: list[int],
        dataset_ids: list[int],
        generated_on: date,
        bucket_days: int,
        history_buckets: int,
    ) -> dict[int, list[BenchmarkTrendPoint]]:
        if not dataset_ids:
            return {}

        history_start = generated_on - timedelta(days=bucket_days * history_buckets)
        reporting_rows = (
            self.db.query(
                DBEvaluation.dataset_id,
                DBPaper.id,
                DBPaper.date_published,
            )
            .join(
                DBPaper,
                and_(
                    DBPaper.id == DBEvaluation.paper_id,
                    DBPaper.is_latest_version,
                ),
            )
            .filter(
                DBEvaluation.task_id.in_(scoped_task_ids),
                DBEvaluation.dataset_id.in_(dataset_ids),
                DBPaper.date_published > history_start,
                DBPaper.date_published <= generated_on,
            )
            .distinct()
            .all()
        )

        counts = {
            dataset_id: [0 for _ in range(history_buckets)]
            for dataset_id in dataset_ids
        }
        for dataset_id, _paper_id, published_on in reporting_rows:
            days_ago = (generated_on - published_on).days
            bucket_index = history_buckets - 1 - (days_ago // bucket_days)
            if 0 <= bucket_index < history_buckets:
                counts[dataset_id][bucket_index] += 1

        histories = {}
        for dataset_id, bucket_counts in counts.items():
            points = []
            for index, paper_count in enumerate(bucket_counts):
                buckets_ago = history_buckets - index
                start = generated_on - timedelta(days=bucket_days * buckets_ago)
                end = generated_on - timedelta(days=bucket_days * (buckets_ago - 1))
                points.append(
                    BenchmarkTrendPoint(
                        start_date=start,
                        end_date=end,
                        paper_count=paper_count,
                    )
                )
            histories[dataset_id] = points
        return histories
