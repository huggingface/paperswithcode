"""
Dataset service for handling dataset-related business logic.

This service provides methods for retrieving and managing benchmark dataset data,
including pagination, filtering, paper associations, and evaluation data.
"""

from typing import Optional, List
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, desc, asc, or_, case, cast, String

from backend.models.database import (
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Metric as DBMetric,
    TaskDataset,
    Task as DBTask,
    Paper as DBPaper,
)
from backend.models.api import (
    Dataset,
    Datasets,
    DatasetCreateRequest,
    DatasetUpdateRequest,
    DatasetLeaderboardSummary,
    IntroducingPaper,
)
from backend.utils.exceptions import DatabaseError
from backend.utils.slug_utils import slugify
from backend.utils.task_hierarchy import collect_descendant_task_ids

# Separator unlikely to collide with real data, used to build the logical
# leaderboard-row key (see `_leaderboard_row_count`).
_ROW_KEY_SEP = "\x1f"


def _parse_metric_value(raw_value) -> Optional[float]:
    """Match leaderboard rank parsing for numeric and uncertainty values."""
    if raw_value is None:
        return None
    try:
        if isinstance(raw_value, str) and "±" in raw_value:
            raw_value = raw_value.split("±", 1)[0].strip()
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _leaderboard_row_count():
    """SQL aggregate counting distinct *logical* leaderboard rows.

    The benchmark page folds separate evaluation records that describe the
    same model on the same leaderboard (differing only in `best_metric`) into
    a single display row keyed by
    `paper_id + task_id + dataset_id + model_name + harness`
    (see `mergeLeaderboardEvaluations` in `BenchmarkDetailView.tsx`). Counting
    raw evaluation rows would over-report a single multi-metric entry as N
    entries, so we count distinct row keys instead to match what users see.

    The key is wrapped in a CASE on `evaluations.id` so the outer join leaves a
    NULL key for datasets with no evaluations (count(distinct NULL) = 0),
    rather than counting the all-empty coalesced key as one phantom row.
    """
    key = (
        func.coalesce(cast(DBEvaluation.paper_id, String), "")
        + _ROW_KEY_SEP
        + func.coalesce(cast(DBEvaluation.task_id, String), "")
        + _ROW_KEY_SEP
        + func.coalesce(cast(DBEvaluation.dataset_id, String), "")
        + _ROW_KEY_SEP
        + func.coalesce(DBEvaluation.model_name, "")
        + _ROW_KEY_SEP
        + func.coalesce(DBEvaluation.harness, "")
    )
    return func.count(
        func.distinct(case((DBEvaluation.id.isnot(None), key), else_=None))
    )


class DatasetService:
    """Service class for dataset-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def _supports_harness(self, dataset_id: int, task_id: Optional[int] = None) -> bool:
        query = self.db.query(TaskDataset.supports_harness).filter(
            TaskDataset.dataset_id == dataset_id
        )
        if task_id is not None:
            query = query.filter(TaskDataset.task_id == task_id)
        return any(supports for (supports,) in query.all())

    def _supports_harness_for_datasets(
        self, dataset_ids: List[int], task_id: Optional[int] = None
    ) -> dict:
        """Batched variant of `_supports_harness`.

        Returns a `dataset_id -> bool` map computed in one query over all page
        dataset IDs, replacing the previous per-row N+1 (`_supports_harness`
        was called once per dataset on every listing). A dataset supports
        harness values when *any* of its in-scope leaderboards allow them.
        """
        if not dataset_ids:
            return {}

        query = self.db.query(
            TaskDataset.dataset_id, TaskDataset.supports_harness
        ).filter(TaskDataset.dataset_id.in_(dataset_ids))
        if task_id is not None:
            query = query.filter(TaskDataset.task_id == task_id)

        result: dict = {}
        for dataset_id, supports in query.all():
            result[dataset_id] = result.get(dataset_id, False) or bool(supports)
        return result

    def _best_models_for_datasets(
        self,
        dataset_ids: List[int],
        scoped_task_ids: List[int],
        is_open: Optional[bool] = None,
    ) -> dict:
        """Map dataset_id -> best visible model name for the scoped task(s).

        Mirrors the benchmark page's primary-metric logic: a (task, dataset)
        can host multiple metric leaderboards, so we first pick the metric the
        most evaluation rows rank on, then take that metric's top-ranked model.
        When `is_open` is set, only rows matching that source-availability
        state participate so task-page benchmark summaries match filtered
        benchmark leaderboards.
        Done in two batched queries (no N+1) since the task page renders up to
        ~100 benchmark rows.
        """
        if not dataset_ids:
            return {}

        # Step 1: per dataset, find the metric carried by the most ranked rows.
        metric_counts = self.db.query(
            DBEvaluation.dataset_id,
            DBEvaluation.best_metric,
            func.count(DBEvaluation.id).label("n"),
        ).filter(
            DBEvaluation.dataset_id.in_(dataset_ids),
            DBEvaluation.task_id.in_(scoped_task_ids),
            DBEvaluation.best_metric.isnot(None),
        )
        if is_open is not None:
            metric_counts = metric_counts.filter(DBEvaluation.is_open == is_open)
        metric_counts = metric_counts.group_by(
            DBEvaluation.dataset_id, DBEvaluation.best_metric
        ).all()
        primary_metric: dict = {}
        best_n: dict = {}
        for dataset_id, metric, n in metric_counts:
            if n > best_n.get(dataset_id, -1):
                best_n[dataset_id] = n
                primary_metric[dataset_id] = metric

        if not primary_metric:
            return {}

        # Step 2: fetch each dataset's best visible model for its primary metric.
        ranked_rows = self.db.query(
            DBEvaluation.dataset_id,
            DBEvaluation.best_metric,
            DBEvaluation.model_name,
            DBEvaluation.best_rank,
            DBEvaluation.id,
        ).filter(
            DBEvaluation.dataset_id.in_(list(primary_metric.keys())),
            DBEvaluation.task_id.in_(scoped_task_ids),
        )
        if is_open is not None:
            ranked_rows = ranked_rows.filter(DBEvaluation.is_open == is_open)
        ranked_rows = ranked_rows.order_by(
            asc(DBEvaluation.best_rank).nulls_last(),
            asc(DBEvaluation.id),
        ).all()
        best_models: dict = {}
        for dataset_id, metric, model_name, _rank, _evaluation_id in ranked_rows:
            if metric == primary_metric.get(dataset_id) and model_name:
                best_models.setdefault(dataset_id, model_name)
        return best_models

    def _leaderboard_summary_for_dataset(
        self,
        dataset_id: int,
        task_id: int,
        is_open: Optional[bool] = None,
    ) -> Optional[DatasetLeaderboardSummary]:
        """Return the small default-metric SOTA projection for one leaderboard.

        The benchmark page chooses its default metric from the metric represented
        by the most evaluation rows. Reuse that established rule, then rank the
        lightweight metric payload directly so the initial dataset response does
        not need to serialize every evaluation and its related paper metadata.
        """
        task = (
            self.db.query(DBTask.id, DBTask.slug).filter(DBTask.id == task_id).first()
        )
        if not task:
            return None

        metric_counts = self.db.query(
            DBEvaluation.best_metric,
            func.count(DBEvaluation.id).label("n"),
        ).filter(
            DBEvaluation.dataset_id == dataset_id,
            DBEvaluation.task_id == task_id,
            DBEvaluation.best_metric.isnot(None),
        )
        if is_open is not None:
            metric_counts = metric_counts.filter(DBEvaluation.is_open == is_open)
        primary_metric_row = (
            metric_counts.group_by(DBEvaluation.best_metric)
            .order_by(desc("n"), asc(DBEvaluation.best_metric))
            .first()
        )
        if not primary_metric_row:
            return None
        primary_metric = primary_metric_row[0]

        rows = (
            self.db.query(
                DBEvaluation.id,
                DBEvaluation.model_name,
                DBEvaluation.metrics,
                DBEvaluation.best_rank,
                DBPaper.title,
            )
            .join(DBPaper, DBPaper.id == DBEvaluation.paper_id)
            .filter(
                DBEvaluation.dataset_id == dataset_id,
                DBEvaluation.task_id == task_id,
            )
        )
        if is_open is not None:
            rows = rows.filter(DBEvaluation.is_open == is_open)
        rows = rows.order_by(
            asc(DBEvaluation.best_rank).nulls_last(),
            asc(DBEvaluation.id),
        ).all()

        candidates = []
        for evaluation_id, model_name, metrics, best_rank, paper_title in rows:
            raw_value = (metrics or {}).get(primary_metric)
            numeric_value = _parse_metric_value(raw_value)
            display_name = model_name or paper_title
            if numeric_value is None or raw_value is None or not display_name:
                continue
            candidates.append(
                (
                    numeric_value,
                    best_rank if best_rank is not None else float("inf"),
                    evaluation_id,
                    raw_value,
                    display_name,
                )
            )
        if not candidates:
            return None

        direction = (
            self.db.query(DBMetric.direction)
            .filter(DBMetric.name == primary_metric)
            .scalar()
            or "higher_is_better"
        )
        if direction == "lower_is_better":
            best = min(candidates, key=lambda row: (row[0], row[1], row[2]))
        else:
            best = min(candidates, key=lambda row: (-row[0], row[1], row[2]))

        return DatasetLeaderboardSummary(
            task_id=str(task.id),
            task_slug=task.slug,
            metric=primary_metric,
            value=best[3],
            model_name=best[4],
            evaluation_id=str(best[2]),
        )

    def get_datasets(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        full_name: Optional[str] = None,
        task_id: Optional[int] = None,
        include_descendants: bool = False,
        order_by: str = "name",
        order_dir: str = "asc",
        min_eval_count: Optional[int] = None,
        is_open: Optional[bool] = None,
    ) -> Datasets:
        """
        Get a paginated list of benchmark datasets with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of datasets per page
            search: Search term for dataset name and description (full-text search)
            name: Filter by partial dataset name match
            full_name: Filter by partial full name match
            task_id: Filter by associated task ID (e.g., datasets for "Image Classification")
            order_by: Field to order by (name, full_name, created_at)
            order_dir: Order direction (asc, desc)
            min_eval_count: When set, hide benchmarks whose evaluation row
                count (i.e. `paper_count`) is below this threshold. Used by
                the task page to suppress low-signal benchmarks by default.
            is_open: When set, choose `best_model_name` from only open-source
                or closed-source evaluation rows. Benchmark inclusion/counts
                remain based on all rows.

        Returns:
            Datasets object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query with paper count and task count.
            # `paper_count` here means leaderboard entry count: the number of
            # *logical* leaderboard rows on this dataset, i.e. distinct
            # (paper, task, dataset, model, harness) groups. This matches the
            # row count the benchmark page renders after merging per-metric
            # evaluation records, so a single model evaluated on four metrics
            # counts as one entry, not four.
            task_dataset_filter = aliased(TaskDataset)
            scoped_task_ids: Optional[List[int]] = None
            if task_id is not None:
                scoped_task_ids = (
                    collect_descendant_task_ids(self.db, task_id)
                    if include_descendants
                    else [task_id]
                )

            eval_join = DBDataset.id == DBEvaluation.dataset_id
            if scoped_task_ids is not None:
                # Same dataset can host separate leaderboards per task (e.g.
                # supervised Video segmentation vs unsupervised VIS). When a task
                # filter is active, count only evaluations on that task's
                # leaderboard — not every row on the shared dataset.
                eval_join = eval_join & DBEvaluation.task_id.in_(scoped_task_ids)

            query = (
                self.db.query(
                    DBDataset,
                    _leaderboard_row_count().label("paper_count"),
                    func.count(func.distinct(TaskDataset.task_id)).label("task_count"),
                )
                .outerjoin(DBEvaluation, eval_join)
                .outerjoin(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
                .group_by(DBDataset.id)
            )

            # Apply filters
            if search:
                # Use ilike for case-insensitive search in name and description
                query = query.filter(
                    or_(
                        DBDataset.name.ilike(f"%{search}%"),
                        DBDataset.full_name.ilike(f"%{search}%")
                        if DBDataset.full_name
                        else False,
                        DBDataset.description.ilike(f"%{search}%")
                        if DBDataset.description
                        else False,
                    )
                )

            if name:
                query = query.filter(DBDataset.name.ilike(f"%{name}%"))

            if full_name:
                query = query.filter(DBDataset.full_name.ilike(f"%{full_name}%"))

            if scoped_task_ids is not None:
                # Filter datasets by task association via task_datasets so display
                # metadata stays independent from per-metric leaderboard triples.
                # When `include_descendants` is true, expand the filter to all
                # subtasks under `task_id` so a parent task page can roll up
                # benchmarks from its child tasks (subtasks).
                query = (
                    query.add_columns(
                        task_dataset_filter.featured_rank.label("featured_rank")
                    )
                    .join(
                        task_dataset_filter,
                        DBDataset.id == task_dataset_filter.dataset_id,
                    )
                    .filter(task_dataset_filter.task_id.in_(scoped_task_ids))
                    .group_by(task_dataset_filter.featured_rank)
                )

            if min_eval_count is not None and min_eval_count > 0:
                # Hide sparse benchmarks. `paper_count` is the count of
                # distinct logical leaderboard rows on a dataset, so a HAVING
                # on the same aggregate suppresses low-signal benchmarks from
                # default task-page lists without touching the underlying
                # data or the dataset detail page (which loads benchmarks
                # by slug directly, bypassing this filter).
                # Apply the threshold uniformly, including to featured
                # benchmarks: pinning controls order, not visibility.
                query = query.having(_leaderboard_row_count() >= min_eval_count)

            # Get total count before pagination
            total_count = query.count()

            # Apply ordering
            if order_by == "name":
                order_field = DBDataset.name
            elif order_by == "full_name":
                order_field = DBDataset.full_name
            elif order_by == "created_at":
                order_field = DBDataset.created_at
            elif order_by == "paper_count":
                # Order by the aggregated leaderboard entry count (logical rows).
                order_field = _leaderboard_row_count()
            else:
                order_field = DBDataset.name

            order_clause = (
                desc(order_field) if order_dir == "desc" else asc(order_field)
            )
            if task_id is not None:
                # Task pages pin curated benchmarks first: any row with a
                # non-null `featured_rank` is ordered ahead of the rest by
                # ascending rank, so an admin can force e.g. SWE-Bench Pro to
                # the top regardless of evaluation count. Unranked benchmarks
                # (`featured_rank IS NULL`) fall back to the requested ordering
                # (typically -paper_count popularity), with name as the final
                # tie-breaker.
                query = query.order_by(
                    asc(task_dataset_filter.featured_rank).nulls_last(),
                    order_clause,
                    asc(DBDataset.name),
                )
            else:
                query = query.order_by(order_clause)

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            page_dataset_ids = [row[0].id for row in results]

            # Best (rank 1) model per benchmark, only when task-scoped. The
            # dataset index (no task filter) skips this so it stays untouched.
            best_models: dict = {}
            if scoped_task_ids is not None:
                best_models = self._best_models_for_datasets(
                    page_dataset_ids, scoped_task_ids, is_open=is_open
                )

            # Batched harness-support lookup for the whole page in one query.
            # When rolling up descendants, harness support belongs to the
            # owning child task, not the requested parent, so drop the task
            # scoping and reflect whether *any* leaderboard allows harness
            # values.
            harness_task_id = None if include_descendants else task_id
            supports_harness_map = self._supports_harness_for_datasets(
                page_dataset_ids, harness_task_id
            )

            # Convert to API models
            dataset_list = []
            for row in results:
                db_dataset, paper_count, task_count = row[:3]
                featured_rank = row[3] if task_id is not None else None
                supports_harness = supports_harness_map.get(db_dataset.id, False)
                dataset_dict = {
                    "id": str(db_dataset.id),
                    "name": db_dataset.name,
                    "slug": db_dataset.slug,
                    "full_name": db_dataset.full_name,
                    "description": db_dataset.description,
                    "url": db_dataset.url,
                    "hf_url": db_dataset.hf_url,
                    # PWC enriched fields
                    "short_description": db_dataset.short_description,
                    "homepage": db_dataset.homepage,
                    # Hierarchy and variant fields
                    "parent_dataset_id": str(db_dataset.parent_dataset_id)
                    if db_dataset.parent_dataset_id
                    else None,
                    "variant_type": db_dataset.variant_type,
                    "split_name": db_dataset.split_name,
                    # Images
                    "image_url": db_dataset.image_url,
                    "thumbnail_url": db_dataset.thumbnail_url,
                    "verified_image_url": db_dataset.verified_image_url,
                    # Paper reference
                    "introducing_paper_id": str(db_dataset.introducing_paper_id)
                    if db_dataset.introducing_paper_id
                    else None,
                    "introducing_paper_title": db_dataset.introducing_paper_title,
                    "paper_url": db_dataset.paper_url,
                    # Licensing
                    "license_name": db_dataset.license_name,
                    "license_url": db_dataset.license_url,
                    # Dates
                    "introduced_year": db_dataset.introduced_year,
                    "introduced_date": db_dataset.introduced_date,
                    # Metadata
                    "modalities": db_dataset.modalities,
                    "languages": db_dataset.languages,
                    "variants": db_dataset.variants,
                    "num_papers": db_dataset.num_papers,
                    "warning": db_dataset.warning,
                    "pwc_url": db_dataset.pwc_url,
                    # Legacy counts
                    "paper_count": paper_count,
                    "task_count": task_count,
                    "featured_rank": featured_rank,
                    "supports_harness": supports_harness,
                    "best_model_name": best_models.get(db_dataset.id),
                }
                dataset_list.append(Dataset(**dataset_dict))

            # Calculate pagination
            total_pages = (total_count + page_size - 1) // page_size
            next_page = page + 1 if page < total_pages else None
            previous_page = page - 1 if page > 1 else None

            return Datasets(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=dataset_list,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve datasets: {str(e)}")

    def _fetch_introducing_paper(
        self, paper_id: Optional[int]
    ) -> Optional[IntroducingPaper]:
        """Fetch the minimal introducing-paper projection in one tiny query.

        Returns None when `paper_id` is missing or the row no longer exists.
        Used by `get_dataset` / `get_dataset_by_slug` when callers pass
        `include_paper=True` so the benchmark page can avoid a follow-up
        request for the introducing paper.
        """
        if paper_id is None:
            return None
        row = (
            self.db.query(
                DBPaper.id, DBPaper.arxiv_id, DBPaper.title, DBPaper.date_published
            )
            .filter(DBPaper.id == paper_id)
            .first()
        )
        if not row:
            return None
        pid, arxiv_id, title, published = row
        return IntroducingPaper(
            id=str(pid),
            arxiv_id=arxiv_id,
            title=title,
            published=published,
        )

    def get_dataset(
        self,
        dataset_id: int,
        include_paper: bool = False,
        task_id: Optional[int] = None,
        is_open: Optional[bool] = None,
    ) -> Optional[Dataset]:
        """
        Get a specific dataset by ID.

        Args:
            dataset_id: Dataset ID
            include_paper: When True, embed a lightweight `introducing_paper`
                projection (arxiv_id, title, published) in the response.
            task_id: When set, embed a lightweight leaderboard summary for
                this task-dataset pair.
            is_open: Optional source-availability filter for the summary.

        Returns:
            Dataset object or None if not found

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Query dataset with counts. `paper_count` is the number of logical
            # leaderboard rows on the dataset (distinct paper/task/dataset/
            # model/harness groups) so it stays in sync with the benchmark page
            # leaderboard table after per-metric rows are merged.
            result = (
                self.db.query(
                    DBDataset,
                    _leaderboard_row_count().label("paper_count"),
                    func.count(func.distinct(TaskDataset.task_id)).label("task_count"),
                )
                .outerjoin(DBEvaluation, DBDataset.id == DBEvaluation.dataset_id)
                .outerjoin(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
                .filter(DBDataset.id == dataset_id)
                .group_by(DBDataset.id)
                .first()
            )

            if not result:
                return None

            db_dataset, paper_count, task_count = result
            supports_harness = self._supports_harness(db_dataset.id)

            dataset_dict = {
                "id": str(db_dataset.id),
                "name": db_dataset.name,
                "slug": db_dataset.slug,
                "full_name": db_dataset.full_name,
                "description": db_dataset.description,
                "url": db_dataset.url,
                "hf_url": db_dataset.hf_url,
                # PWC enriched fields
                "short_description": db_dataset.short_description,
                "homepage": db_dataset.homepage,
                # Hierarchy and variant fields
                "parent_dataset_id": str(db_dataset.parent_dataset_id)
                if db_dataset.parent_dataset_id
                else None,
                "variant_type": db_dataset.variant_type,
                "split_name": db_dataset.split_name,
                # Images
                "image_url": db_dataset.image_url,
                "thumbnail_url": db_dataset.thumbnail_url,
                "verified_image_url": db_dataset.verified_image_url,
                # Paper reference
                "introducing_paper_id": str(db_dataset.introducing_paper_id)
                if db_dataset.introducing_paper_id
                else None,
                "introducing_paper_title": db_dataset.introducing_paper_title,
                "paper_url": db_dataset.paper_url,
                # Licensing
                "license_name": db_dataset.license_name,
                "license_url": db_dataset.license_url,
                # Dates
                "introduced_year": db_dataset.introduced_year,
                "introduced_date": db_dataset.introduced_date,
                # Metadata
                "modalities": db_dataset.modalities,
                "languages": db_dataset.languages,
                "variants": db_dataset.variants,
                "num_papers": db_dataset.num_papers,
                "warning": db_dataset.warning,
                "pwc_url": db_dataset.pwc_url,
                # Legacy counts
                "paper_count": paper_count,
                "task_count": task_count,
                "featured_rank": None,
                "supports_harness": supports_harness,
            }

            if include_paper:
                dataset_dict["introducing_paper"] = self._fetch_introducing_paper(
                    db_dataset.introducing_paper_id
                )
            if task_id is not None:
                dataset_dict["leaderboard_summary"] = (
                    self._leaderboard_summary_for_dataset(
                        db_dataset.id,
                        task_id,
                        is_open=is_open,
                    )
                )

            return Dataset(**dataset_dict)

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve dataset: {str(e)}")

    def get_dataset_by_slug(
        self,
        slug: str,
        include_paper: bool = False,
        task_id: Optional[int] = None,
        is_open: Optional[bool] = None,
    ) -> Optional[Dataset]:
        """
        Get a specific dataset by slug.

        Args:
            slug: Dataset slug
            include_paper: When True, embed a lightweight `introducing_paper`
                projection (arxiv_id, title, published) in the response.
            task_id: When set, embed a lightweight leaderboard summary for
                this task-dataset pair.
            is_open: Optional source-availability filter for the summary.

        Returns:
            Dataset object or None if not found

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Query dataset with counts. `paper_count` mirrors the benchmark
            # leaderboard size (logical rows: distinct paper/task/dataset/
            # model/harness groups) instead of `paper_datasets`.
            result = (
                self.db.query(
                    DBDataset,
                    _leaderboard_row_count().label("paper_count"),
                    func.count(func.distinct(TaskDataset.task_id)).label("task_count"),
                )
                .outerjoin(DBEvaluation, DBDataset.id == DBEvaluation.dataset_id)
                .outerjoin(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
                .filter(func.lower(DBDataset.slug) == slug.lower())
                .group_by(DBDataset.id)
                .first()
            )

            if not result:
                return None

            db_dataset, paper_count, task_count = result
            supports_harness = self._supports_harness(db_dataset.id)

            dataset_dict = {
                "id": str(db_dataset.id),
                "name": db_dataset.name,
                "slug": db_dataset.slug,
                "full_name": db_dataset.full_name,
                "description": db_dataset.description,
                "url": db_dataset.url,
                "hf_url": db_dataset.hf_url,
                # PWC enriched fields
                "short_description": db_dataset.short_description,
                "homepage": db_dataset.homepage,
                # Hierarchy and variant fields
                "parent_dataset_id": str(db_dataset.parent_dataset_id)
                if db_dataset.parent_dataset_id
                else None,
                "variant_type": db_dataset.variant_type,
                "split_name": db_dataset.split_name,
                # Images
                "image_url": db_dataset.image_url,
                "thumbnail_url": db_dataset.thumbnail_url,
                "verified_image_url": db_dataset.verified_image_url,
                # Paper reference
                "introducing_paper_id": str(db_dataset.introducing_paper_id)
                if db_dataset.introducing_paper_id
                else None,
                "introducing_paper_title": db_dataset.introducing_paper_title,
                "paper_url": db_dataset.paper_url,
                # Licensing
                "license_name": db_dataset.license_name,
                "license_url": db_dataset.license_url,
                # Dates
                "introduced_year": db_dataset.introduced_year,
                "introduced_date": db_dataset.introduced_date,
                # Metadata
                "modalities": db_dataset.modalities,
                "languages": db_dataset.languages,
                "variants": db_dataset.variants,
                "num_papers": db_dataset.num_papers,
                "warning": db_dataset.warning,
                "pwc_url": db_dataset.pwc_url,
                # Legacy counts
                "paper_count": paper_count,
                "task_count": task_count,
                "featured_rank": None,
                "supports_harness": supports_harness,
            }

            if include_paper:
                dataset_dict["introducing_paper"] = self._fetch_introducing_paper(
                    db_dataset.introducing_paper_id
                )
            if task_id is not None:
                dataset_dict["leaderboard_summary"] = (
                    self._leaderboard_summary_for_dataset(
                        db_dataset.id,
                        task_id,
                        is_open=is_open,
                    )
                )

            return Dataset(**dataset_dict)

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve dataset by slug: {str(e)}")

    def get_dataset_tasks(self, dataset_id: int) -> List[int]:
        """
        Get tasks associated with a specific dataset via task_dataset_metrics.

        Args:
            dataset_id: Dataset ID

        Returns:
            List of unique task IDs

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Get distinct task IDs from task_datasets
            task_ids = (
                self.db.query(TaskDataset.task_id)
                .filter(TaskDataset.dataset_id == dataset_id)
                .distinct()
                .all()
            )

            return [tid[0] for tid in task_ids]

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve tasks for dataset: {str(e)}")

    def search_datasets(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
        task_id: Optional[int] = None,
        include_descendants: bool = False,
        min_eval_count: Optional[int] = None,
        is_open: Optional[bool] = None,
    ) -> Datasets:
        """
        Search datasets by name, full_name, or description.

        Args:
            query: Search query string
            page: Page number (1-based)
            page_size: Number of datasets per page
            task_id: When set, restrict results to benchmarks linked to this task
            include_descendants: Expand ``task_id`` to subtasks when filtering
            min_eval_count: Hide benchmarks below this evaluation row count
            is_open: When set, choose `best_model_name` from only matching
                evaluation rows.

        Returns:
            Datasets object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        return self.get_datasets(
            page=page,
            page_size=page_size,
            search=query,
            task_id=task_id,
            include_descendants=include_descendants,
            min_eval_count=min_eval_count,
            is_open=is_open,
            order_by="name",
            order_dir="asc",
        )

    def create_dataset(self, request: DatasetCreateRequest) -> Dataset:
        """
        Create a new dataset and link it to specified tasks.

        Args:
            request: DatasetCreateRequest with dataset data and task IDs

        Returns:
            Created Dataset object

        Raises:
            DatabaseError: If database operation fails
            ValueError: If task IDs don't exist or slug already exists
        """
        try:
            # Generate slug from name
            slug = slugify(request.name)

            # Check if slug already exists
            existing_dataset = (
                self.db.query(DBDataset).filter(DBDataset.slug == slug).first()
            )
            if existing_dataset:
                raise ValueError(f"Dataset with slug '{slug}' already exists")

            # Validate that all task IDs exist
            existing_task_ids = set(
                self.db.query(DBTask.id).filter(DBTask.id.in_(request.task_ids)).all()
            )
            existing_task_ids = {task_id[0] for task_id in existing_task_ids}

            missing_task_ids = set(request.task_ids) - existing_task_ids
            if missing_task_ids:
                raise ValueError(f"Task IDs not found: {sorted(missing_task_ids)}")

            # Create the dataset
            db_dataset = DBDataset(
                name=request.name,
                slug=slug,
                full_name=request.full_name,
                description=request.description,
                url=request.url,
                hf_url=request.hf_url,
                paper_url=request.paper_url,
                # Additional PWC fields
                short_description=request.short_description,
                homepage=request.homepage,
                image_url=request.image_url,
                thumbnail_url=request.thumbnail_url,
                verified_image_url=request.verified_image_url,
                license_name=request.license_name,
                license_url=request.license_url,
                introduced_date=request.introduced_date,
                modalities=request.modalities,
                languages=request.languages,
                variants=request.variants,
                num_papers=request.num_papers,
                warning=request.warning,
                pwc_url=request.pwc_url,
            )

            self.db.add(db_dataset)
            self.db.commit()

            # Note: Task-dataset relationships are now defined via TASK_DATASET_METRICS.
            # If task_ids were provided in the request, use the leaderboard metrics API
            # (/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics) to define metrics
            # for each task-dataset pair.

            # Return the created dataset using the existing get_dataset method
            return self.get_dataset(db_dataset.id)

        except ValueError as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create dataset: {str(e)}")

    def update_dataset(self, dataset_id: int, request: DatasetUpdateRequest) -> Dataset:
        """
        Update an existing dataset.

        Args:
            dataset_id: Dataset ID to update
            request: DatasetUpdateRequest with fields to update

        Returns:
            Updated Dataset object

        Raises:
            DatabaseError: If database operation fails
            ValueError: If dataset not found
        """
        try:
            # Get the existing dataset
            db_dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not db_dataset:
                raise ValueError(f"Dataset with ID {dataset_id} not found")

            # Update only provided fields
            if request.name is not None:
                db_dataset.name = request.name
                # Regenerate slug if name changes
                db_dataset.slug = slugify(request.name)

            if request.full_name is not None:
                db_dataset.full_name = request.full_name

            if request.description is not None:
                db_dataset.description = request.description

            if request.url is not None:
                db_dataset.url = request.url

            if request.hf_url is not None:
                db_dataset.hf_url = request.hf_url

            if request.paper_url is not None:
                db_dataset.paper_url = request.paper_url

            # Additional PWC fields
            if request.short_description is not None:
                db_dataset.short_description = request.short_description

            if request.homepage is not None:
                db_dataset.homepage = request.homepage

            if request.image_url is not None:
                db_dataset.image_url = request.image_url

            if request.thumbnail_url is not None:
                db_dataset.thumbnail_url = request.thumbnail_url

            if request.verified_image_url is not None:
                db_dataset.verified_image_url = request.verified_image_url

            if request.license_name is not None:
                db_dataset.license_name = request.license_name

            if request.license_url is not None:
                db_dataset.license_url = request.license_url

            if request.introduced_date is not None:
                db_dataset.introduced_date = request.introduced_date

            if request.modalities is not None:
                db_dataset.modalities = request.modalities

            if request.languages is not None:
                db_dataset.languages = request.languages

            if request.variants is not None:
                db_dataset.variants = request.variants

            if request.num_papers is not None:
                db_dataset.num_papers = request.num_papers

            if request.warning is not None:
                db_dataset.warning = request.warning

            if request.pwc_url is not None:
                db_dataset.pwc_url = request.pwc_url

            self.db.commit()

            # Return the updated dataset using the existing get_dataset method
            return self.get_dataset(db_dataset.id)

        except ValueError as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to update dataset: {str(e)}")
