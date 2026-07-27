"""Task-scoped benchmark trends derived from evaluation-reporting papers."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from backend.models.api import (
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
from backend.utils.exceptions import PaperNotFoundError
from backend.utils.task_hierarchy import collect_descendant_task_ids


class BenchmarkTrendService:
    """Rank benchmarks by distinct recent papers that report evaluations."""

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
                func.min(TaskDataset.featured_rank).label("featured_rank"),
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
        best_models = DatasetService(self.db)._best_models_for_datasets(
            [row[0].id for row in rows],
            scoped_task_ids,
            is_open=is_open,
        )

        results = []
        for (
            dataset,
            featured_rank,
            recent,
            baseline,
            all_time,
            latest_reported_on,
        ) in rows:
            recent = int(recent or 0)
            baseline = int(baseline or 0)
            recent_velocity = recent * 30.0 / recent_days
            baseline_velocity = baseline * 30.0 / baseline_days
            results.append(
                TrendingBenchmark(
                    id=dataset.id,
                    name=dataset.name,
                    slug=dataset.slug,
                    full_name=dataset.full_name,
                    featured_rank=featured_rank,
                    recent_paper_count=recent,
                    baseline_paper_count=baseline,
                    all_time_paper_count=int(all_time or 0),
                    trend_score=round(recent_velocity, 4),
                    rate_change=(
                        round(recent_velocity / baseline_velocity, 4)
                        if baseline_velocity
                        else None
                    ),
                    latest_reported_on=latest_reported_on,
                    best_model_name=best_models.get(dataset.id),
                    history=history.get(dataset.id, []),
                )
            )

        results.sort(
            key=lambda item: (
                -item.recent_paper_count,
                -(item.latest_reported_on or date.min).toordinal(),
                -item.all_time_paper_count,
                item.name.casefold(),
            )
        )

        return TrendingBenchmarks(
            task_id=task.id,
            task_slug=task.slug,
            recent_days=recent_days,
            baseline_days=baseline_days,
            bucket_days=bucket_days,
            generated_on=generated_on,
            results=results[:limit],
        )

    def _resolve_task(self, task_id: str) -> DBTask:
        if str(task_id).isdigit():
            task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
        else:
            task = (
                self.db.query(DBTask)
                .filter(
                    or_(
                        func.lower(DBTask.slug) == str(task_id).lower(),
                        func.lower(DBTask.name) == str(task_id).lower(),
                    )
                )
                .order_by(DBTask.id)
                .first()
            )
        if task is None:
            raise PaperNotFoundError(
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
