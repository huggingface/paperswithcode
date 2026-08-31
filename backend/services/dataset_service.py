"""
Dataset service for handling dataset-related business logic.

This service provides methods for retrieving and managing benchmark dataset data,
including pagination, filtering, paper associations, and evaluation data.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import String, asc, case, cast, desc, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from backend.models.api import (
    Dataset,
    DatasetCreateRequest,
    DatasetLeaderboardSummary,
    Datasets,
    DatasetUpdateRequest,
    IntroducingPaper,
    Task,
)
from backend.models.database import (
    Dataset as DBDataset,
)
from backend.models.database import (
    Evaluation as DBEvaluation,
)
from backend.models.database import (
    Metric as DBMetric,
)
from backend.models.database import (
    Paper as DBPaper,
)
from backend.models.database import (
    PaperRepository as DBPaperRepository,
)
from backend.models.database import (
    PaperTask,
    TaskDataset,
)
from backend.models.database import (
    Repository as DBRepository,
)
from backend.models.database import (
    Task as DBTask,
)
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogError,
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)
from backend.services.entity_search import (
    DETERMINISTIC_CANDIDATE_LIMIT,
    FUZZY_CANDIDATE_LIMIT,
    EntitySearchCandidate,
    EntitySearchKind,
    choose_fuzzy_winner,
    deterministic_match,
    empty_page,
    postgres_fuzzy_ordering,
    postgres_search_expressions,
    prepare_entity_search,
)
from backend.services.metric_value_service import parse_metric_value
from backend.utils.slug_utils import slugify
from backend.utils.task_hierarchy import collect_descendant_task_ids
from backend.utils.task_slugs import task_slug_candidates

# Separator unlikely to collide with real data, used to build the logical
# leaderboard-row key (see `_leaderboard_row_count`).
_ROW_KEY_SEP = "\x1f"
_LIVING_EXTERNAL_WARNING_PREFIX = "Living external leaderboard:"


def _is_living_external_leaderboard():
    """Return the explicit metadata predicate for externally hosted live boards.

    These resources intentionally have no static evaluation rows, but still
    belong on task pages. The warning prefix is an opt-in catalog contract;
    ordinary empty or sparse benchmarks remain subject to ``min_eval_count``.
    """
    return DBDataset.warning.ilike(f"{_LIVING_EXTERNAL_WARNING_PREFIX}%")


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

    def resolve_task_id(
        self, identifier: str, *, case_sensitive_slug: bool
    ) -> int | None:
        """Resolve a task ID or slug without changing legacy lookup semantics."""
        try:
            return int(identifier)
        except ValueError:
            pass

        try:
            for candidate in task_slug_candidates(identifier):
                slug_filter = (
                    DBTask.slug == candidate
                    if case_sensitive_slug
                    else func.lower(DBTask.slug) == candidate.lower()
                )
                row = self.db.query(DBTask.id).filter(slug_filter).first()
                if row is not None:
                    return int(row[0])
        except SQLAlchemyError as error:
            raise CatalogPersistenceError(
                f"Failed to retrieve task by slug: {error!s}"
            ) from error
        return None

    def get_dataset_by_identifier(
        self,
        identifier: str,
        *,
        include_paper: bool = False,
        task_id: int | None = None,
        is_open: bool | None = None,
    ) -> Dataset:
        """Load one dataset by numeric ID or case-insensitive slug."""
        try:
            dataset = self.get_dataset(
                int(identifier),
                include_paper=include_paper,
                task_id=task_id,
                is_open=is_open,
            )
        except ValueError:
            dataset = self.get_dataset_by_slug(
                identifier,
                include_paper=include_paper,
                task_id=task_id,
                is_open=is_open,
            )
        if dataset is None:
            raise CatalogNotFoundError(
                f"Dataset with ID or slug '{identifier}' not found"
            )
        return dataset

    def resolve_numeric_dataset_id(self, identifier: str) -> int:
        """Resolve a numeric-only dataset route identifier."""
        try:
            return int(identifier)
        except ValueError as error:
            raise CatalogValidationError(
                "Invalid dataset ID. Must be an integer."
            ) from error

    def require_numeric_dataset_id(self, identifier: str) -> int:
        """Resolve an existing numeric dataset identifier for a dataset route."""
        dataset_id = self.resolve_numeric_dataset_id(identifier)
        if self.get_dataset(dataset_id) is None:
            raise CatalogNotFoundError(f"Dataset with ID {identifier} not found")
        return dataset_id

    def get_dataset_evaluations(
        self,
        *,
        page: int,
        page_size: int,
        dataset_id: int,
        is_open: bool | None,
        order_by: str,
        order_dir: str,
    ):
        """Load one dataset's evaluations with the dataset-route error contract."""
        from backend.services.evaluation_service import EvaluationService
        from backend.utils.exceptions import DatabaseError

        try:
            return EvaluationService(self.db).get_evaluations(
                page=page,
                page_size=page_size,
                dataset_id=dataset_id,
                is_open=is_open,
                order_by=order_by,
                order_dir=order_dir,
            )
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    def list_task_summaries_by_dataset_identifier(self, identifier: str) -> list[Task]:
        """List task summaries while preserving numeric-ID and slug behavior."""
        try:
            dataset_id = int(identifier)
        except ValueError:
            dataset_id = self.resolve_dataset_id_by_slug(identifier)
            if dataset_id is None:
                raise CatalogNotFoundError(
                    f"Dataset with slug '{identifier}' not found"
                )
        return self.list_task_summaries(dataset_id)

    def update_dataset_by_identifier(
        self, identifier: str, request: DatasetUpdateRequest
    ) -> Dataset:
        """Update one dataset selected by numeric ID or case-insensitive slug."""
        try:
            dataset_id = int(identifier)
        except ValueError:
            dataset = self.get_dataset_by_slug(identifier)
            if dataset is None:
                raise CatalogNotFoundError(
                    f"Dataset with slug '{identifier}' not found"
                )
            dataset_id = int(dataset.id)
        return self.update_dataset(dataset_id, request)

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

    def _best_results_for_datasets(
        self,
        dataset_ids: List[int],
        scoped_task_ids: List[int],
        is_open: Optional[bool] = None,
    ) -> dict:
        """Map dataset_id to its best visible model, paper, and code metadata.

        Mirrors the benchmark page's primary-metric logic: a (task, dataset)
        can host multiple metric leaderboards, so we first pick the metric the
        most evaluation rows rank on, then take that metric's top-ranked result.
        When `is_open` is set, only rows matching that source-availability
        state participate so task-page benchmark summaries match filtered
        benchmark leaderboards.
        All paper and repository metadata is loaded in batches since the task
        page renders up to ~100 benchmark rows.
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
        ranked_rows = (
            self.db.query(
                DBEvaluation.dataset_id,
                DBEvaluation.best_metric,
                DBEvaluation.model_name,
                DBEvaluation.best_rank,
                DBEvaluation.id,
                DBPaper.id,
                DBPaper.arxiv_id,
                DBPaper.title,
            )
            .join(
                DBPaper,
                DBPaper.id == DBEvaluation.paper_id,
            )
            .filter(
                DBEvaluation.dataset_id.in_(list(primary_metric.keys())),
                DBEvaluation.task_id.in_(scoped_task_ids),
            )
        )
        if is_open is not None:
            ranked_rows = ranked_rows.filter(DBEvaluation.is_open == is_open)
        ranked_rows = ranked_rows.order_by(
            asc(DBEvaluation.best_rank).nulls_last(),
            asc(DBEvaluation.id),
        ).all()
        best_results: dict = {}
        for (
            dataset_id,
            metric,
            model_name,
            _rank,
            _evaluation_id,
            paper_id,
            arxiv_id,
            paper_title,
        ) in ranked_rows:
            if metric == primary_metric.get(dataset_id) and model_name:
                best_results.setdefault(
                    dataset_id,
                    {
                        "model_name": model_name,
                        "paper_id": paper_id,
                        "paper_route": arxiv_id or str(paper_id),
                        "paper_title": paper_title,
                        "code_url": None,
                    },
                )

        paper_ids = [result["paper_id"] for result in best_results.values()]
        if paper_ids:
            repository_rows = (
                self.db.query(
                    DBPaperRepository.paper_id,
                    DBRepository.url,
                )
                .join(
                    DBRepository,
                    DBRepository.id == DBPaperRepository.repository_id,
                )
                .filter(DBPaperRepository.paper_id.in_(paper_ids))
                .order_by(
                    desc(DBPaperRepository.is_official),
                    desc(DBRepository.num_stars),
                    asc(DBRepository.url),
                )
                .all()
            )
            code_urls: dict = {}
            for paper_id, code_url in repository_rows:
                code_urls.setdefault(paper_id, code_url)
            for result in best_results.values():
                result["code_url"] = code_urls.get(result["paper_id"])

        return best_results

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
            numeric_value = parse_metric_value(raw_value)
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
        _dataset_ids: Optional[List[int]] = None,
        _count_override: Optional[int] = None,
    ) -> Datasets:
        """
        Get a paginated list of benchmark datasets with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of datasets per page
            search: Name-only navigational benchmark search
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
            CatalogPersistenceError: If database query fails
        """
        if search is not None:
            return self.search_datasets(
                query=search,
                page=page,
                page_size=page_size,
                task_id=task_id,
                include_descendants=include_descendants,
                min_eval_count=min_eval_count,
                is_open=is_open,
            )

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
            if _dataset_ids is not None:
                query = query.filter(DBDataset.id.in_(_dataset_ids))

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
                query = query.join(
                    task_dataset_filter,
                    DBDataset.id == task_dataset_filter.dataset_id,
                ).filter(task_dataset_filter.task_id.in_(scoped_task_ids))

            if min_eval_count is not None and min_eval_count > 0:
                # Hide sparse benchmarks. `paper_count` is the count of
                # distinct logical leaderboard rows on a dataset, so a HAVING
                # on the same aggregate suppresses low-signal benchmarks from
                # default task-page lists without touching the underlying
                # data or the dataset detail page (which loads benchmarks
                # by slug directly, bypassing this filter).
                query = query.having(
                    or_(
                        _leaderboard_row_count() >= min_eval_count,
                        _is_living_external_leaderboard(),
                    )
                )

            # Get total count before pagination
            total_count = (
                _count_override if _count_override is not None else query.count()
            )

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
                query = query.order_by(
                    asc(
                        case(
                            (_is_living_external_leaderboard(), 0),
                            else_=1,
                        )
                    ),
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
            best_results: dict = {}
            if scoped_task_ids is not None:
                best_results = self._best_results_for_datasets(
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
                supports_harness = supports_harness_map.get(db_dataset.id, False)
                best_result = best_results.get(db_dataset.id, {})
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
                    "supports_harness": supports_harness,
                    "best_model_name": best_result.get("model_name"),
                    "best_paper_route": best_result.get("paper_route"),
                    "best_paper_title": best_result.get("paper_title"),
                    "best_code_url": best_result.get("code_url"),
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
            raise CatalogPersistenceError(f"Failed to retrieve datasets: {e!s}")

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

    def _get_dataset_aggregate(self, identity_predicate) -> tuple | None:
        """Load the canonical dataset aggregate for either public identity."""
        return (
            self.db.query(
                DBDataset,
                _leaderboard_row_count().label("paper_count"),
                func.count(func.distinct(TaskDataset.task_id)).label("task_count"),
            )
            .outerjoin(DBEvaluation, DBDataset.id == DBEvaluation.dataset_id)
            .outerjoin(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
            .filter(identity_predicate)
            .group_by(DBDataset.id)
            .first()
        )

    def _project_dataset(
        self,
        aggregate: tuple,
        *,
        include_paper: bool,
        task_id: int | None,
        is_open: bool | None,
    ) -> Dataset:
        """Project one loaded aggregate into the stable public API contract."""
        db_dataset, paper_count, task_count = aggregate
        dataset_dict = {
            "id": str(db_dataset.id),
            "name": db_dataset.name,
            "slug": db_dataset.slug,
            "full_name": db_dataset.full_name,
            "description": db_dataset.description,
            "url": db_dataset.url,
            "hf_url": db_dataset.hf_url,
            "short_description": db_dataset.short_description,
            "homepage": db_dataset.homepage,
            "parent_dataset_id": str(db_dataset.parent_dataset_id)
            if db_dataset.parent_dataset_id
            else None,
            "variant_type": db_dataset.variant_type,
            "split_name": db_dataset.split_name,
            "image_url": db_dataset.image_url,
            "thumbnail_url": db_dataset.thumbnail_url,
            "verified_image_url": db_dataset.verified_image_url,
            "introducing_paper_id": str(db_dataset.introducing_paper_id)
            if db_dataset.introducing_paper_id
            else None,
            "introducing_paper_title": db_dataset.introducing_paper_title,
            "paper_url": db_dataset.paper_url,
            "license_name": db_dataset.license_name,
            "license_url": db_dataset.license_url,
            "introduced_year": db_dataset.introduced_year,
            "introduced_date": db_dataset.introduced_date,
            "modalities": db_dataset.modalities,
            "languages": db_dataset.languages,
            "variants": db_dataset.variants,
            "num_papers": db_dataset.num_papers,
            "warning": db_dataset.warning,
            "pwc_url": db_dataset.pwc_url,
            "paper_count": paper_count,
            "task_count": task_count,
            "supports_harness": self._supports_harness(db_dataset.id),
        }
        if include_paper:
            dataset_dict["introducing_paper"] = self._fetch_introducing_paper(
                db_dataset.introducing_paper_id
            )
        if task_id is not None:
            dataset_dict["leaderboard_summary"] = self._leaderboard_summary_for_dataset(
                db_dataset.id,
                task_id,
                is_open=is_open,
            )
        return Dataset(**dataset_dict)

    def _get_dataset(
        self,
        identity_predicate,
        *,
        include_paper: bool,
        task_id: int | None,
        is_open: bool | None,
        error_context: str,
    ) -> Dataset | None:
        try:
            aggregate = self._get_dataset_aggregate(identity_predicate)
            if aggregate is None:
                return None
            return self._project_dataset(
                aggregate,
                include_paper=include_paper,
                task_id=task_id,
                is_open=is_open,
            )
        except (SQLAlchemyError, CatalogError, ValueError) as error:
            raise CatalogPersistenceError(
                f"Failed to retrieve {error_context}: {error!s}"
            ) from error

    def get_dataset(
        self,
        dataset_id: int,
        include_paper: bool = False,
        task_id: Optional[int] = None,
        is_open: Optional[bool] = None,
    ) -> Optional[Dataset]:
        """Get a dataset by ID using the canonical aggregate projection."""
        return self._get_dataset(
            DBDataset.id == dataset_id,
            include_paper=include_paper,
            task_id=task_id,
            is_open=is_open,
            error_context="dataset",
        )

    def get_dataset_by_slug(
        self,
        slug: str,
        include_paper: bool = False,
        task_id: Optional[int] = None,
        is_open: Optional[bool] = None,
    ) -> Optional[Dataset]:
        """Get a dataset by case-insensitive slug using the canonical projection."""
        return self._get_dataset(
            func.lower(DBDataset.slug) == slug.lower(),
            include_paper=include_paper,
            task_id=task_id,
            is_open=is_open,
            error_context="dataset by slug",
        )

    def resolve_dataset_id_by_slug(self, slug: str) -> int | None:
        """Resolve one dataset slug case-insensitively without hydrating it."""
        try:
            row = (
                self.db.query(DBDataset.id)
                .filter(func.lower(DBDataset.slug) == slug.lower())
                .first()
            )
            return int(row[0]) if row is not None else None
        except Exception as e:  # noqa: BLE001
            raise CatalogPersistenceError(f"Failed to retrieve dataset by slug: {e!s}")

    def list_task_summaries(self, dataset_id: int) -> list[Task]:
        """Return task-list projections for one dataset in a grouped query."""
        try:
            rows = (
                self.db.query(
                    DBTask,
                    func.count(PaperTask.paper_id).label("paper_count"),
                )
                .join(TaskDataset, DBTask.id == TaskDataset.task_id)
                .outerjoin(PaperTask, PaperTask.task_id == DBTask.id)
                .filter(TaskDataset.dataset_id == dataset_id)
                .group_by(DBTask.id)
                .order_by(DBTask.name)
                .all()
            )
            return [
                Task(
                    id=str(task.id),
                    name=task.name,
                    description=task.description,
                    slug=task.slug,
                    keywords=task.keywords,
                    parent_id=str(task.parent_id) if task.parent_id else None,
                    area_id=str(task.area_id) if task.area_id else None,
                    level=task.level,
                    paper_count=int(paper_count or 0),
                    image_url=task.image_url,
                    image_credit=task.image_credit,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                )
                for task, paper_count in rows
            ]
        except Exception as e:  # noqa: BLE001
            raise CatalogPersistenceError(
                f"Failed to retrieve tasks for dataset: {e!s}"
            )

    def get_dataset_tasks(self, dataset_id: int) -> List[int]:
        """
        Get tasks associated with a specific dataset via task_dataset_metrics.

        Args:
            dataset_id: Dataset ID

        Returns:
            List of unique task IDs

        Raises:
            CatalogPersistenceError: If database query fails
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
            raise CatalogPersistenceError(
                f"Failed to retrieve tasks for dataset: {e!s}"
            )

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
        """Search displayed benchmark names with identity, prefix, FTS, and typo lanes.

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
            CatalogPersistenceError: If database query fails
        """
        terms = prepare_entity_search(query, EntitySearchKind.DATASET)
        if not terms.usable:
            return empty_page(Datasets)

        allowed_ids = self._eligible_search_dataset_ids(
            task_id=task_id,
            include_descendants=include_descendants,
            min_eval_count=min_eval_count,
        )
        candidates = self._dataset_search_candidates(terms, allowed_ids)
        if not candidates:
            return empty_page(Datasets)

        trend = self._dataset_search_trends(
            [candidate.entity_id for candidate in candidates]
        )
        candidates.sort(
            key=lambda candidate: (
                candidate.tier,
                -candidate.relevance,
                -trend.get(candidate.entity_id, (0.0, None, 0))[0],
                -(
                    trend.get(candidate.entity_id, (0.0, None, 0))[1].toordinal()
                    if trend.get(candidate.entity_id, (0.0, None, 0))[1]
                    else 0
                ),
                -trend.get(candidate.entity_id, (0.0, None, 0))[2],
                candidate.name.casefold(),
                candidate.entity_id,
            )
        )

        offset = (page - 1) * page_size
        page_candidates = candidates[offset : offset + page_size]
        page_ids = [candidate.entity_id for candidate in page_candidates]
        response = self.get_datasets(
            page=1,
            page_size=max(1, len(page_ids)),
            task_id=task_id,
            include_descendants=include_descendants,
            min_eval_count=min_eval_count,
            is_open=is_open,
            _dataset_ids=page_ids,
            _count_override=len(candidates),
        )
        by_id = {int(dataset.id): dataset for dataset in response.results}
        response.results = [
            by_id[entity_id] for entity_id in page_ids if entity_id in by_id
        ]
        response.next_page = page + 1 if offset + page_size < len(candidates) else None
        response.previous_page = page - 1 if page > 1 else None
        return response

    def _eligible_search_dataset_ids(
        self,
        *,
        task_id: Optional[int],
        include_descendants: bool,
        min_eval_count: Optional[int],
    ) -> Optional[List[int]]:
        if task_id is None and not min_eval_count:
            return None

        scoped_task_ids = None
        if task_id is not None:
            scoped_task_ids = (
                collect_descendant_task_ids(self.db, task_id)
                if include_descendants
                else [task_id]
            )

        query = self.db.query(DBDataset.id)
        if scoped_task_ids is not None:
            query = query.join(
                TaskDataset, TaskDataset.dataset_id == DBDataset.id
            ).filter(TaskDataset.task_id.in_(scoped_task_ids))
        if min_eval_count:
            evaluation_join = DBEvaluation.dataset_id == DBDataset.id
            if scoped_task_ids is not None:
                evaluation_join = evaluation_join & DBEvaluation.task_id.in_(
                    scoped_task_ids
                )
            query = (
                query.outerjoin(DBEvaluation, evaluation_join)
                .group_by(DBDataset.id)
                .having(
                    or_(
                        _leaderboard_row_count() >= min_eval_count,
                        _is_living_external_leaderboard(),
                    )
                )
            )
        return [int(dataset_id) for (dataset_id,) in query.distinct().all()]

    def _dataset_search_candidates(
        self, terms, allowed_ids: Optional[List[int]]
    ) -> List[EntitySearchCandidate]:
        base = self.db.query(DBDataset)
        if allowed_ids is not None:
            if not allowed_ids:
                return []
            base = base.filter(DBDataset.id.in_(allowed_ids))

        if self.db.bind.dialect.name != "postgresql":
            candidates = []
            for dataset in base.all():
                match = deterministic_match(
                    terms,
                    name=dataset.name,
                    slug=dataset.slug,
                    full_name=dataset.full_name,
                )
                if match:
                    candidates.append(
                        EntitySearchCandidate(
                            int(dataset.id), dataset.name, match[0], match[1]
                        )
                    )
            candidates.sort(
                key=lambda candidate: (
                    candidate.tier,
                    -candidate.relevance,
                    candidate.name.casefold(),
                    candidate.entity_id,
                )
            )
            if candidates:
                return candidates[:DETERMINISTIC_CANDIDATE_LIMIT]
            fuzzy_rows = [
                (int(dataset.id), dataset.name, 0.0) for dataset in base.all()
            ]
        else:
            predicate, tier, relevance = postgres_search_expressions(
                DBDataset, terms, full_name=DBDataset.full_name
            )
            rows = (
                base.with_entities(
                    DBDataset.id,
                    DBDataset.name,
                    tier.label("tier"),
                    relevance.label("relevance"),
                )
                .filter(predicate)
                .order_by(
                    asc(tier),
                    desc(relevance),
                    asc(DBDataset.name),
                    asc(DBDataset.id),
                )
                .limit(DETERMINISTIC_CANDIDATE_LIMIT)
                .all()
            )
            if rows:
                return [
                    EntitySearchCandidate(
                        int(entity_id), name, int(match_tier), float(rank or 0.0)
                    )
                    for entity_id, name, match_tier, rank in rows
                ]
            if terms.identity_only or len("".join(terms.tokens)) < 4:
                return []
            distance, similarity = postgres_fuzzy_ordering(
                DBDataset.name, terms.normalized
            )
            fuzzy_rows = (
                base.with_entities(DBDataset.id, DBDataset.name, similarity)
                .order_by(distance, asc(DBDataset.id))
                .limit(FUZZY_CANDIDATE_LIMIT)
                .all()
            )

        if terms.identity_only or len("".join(terms.tokens)) < 4:
            return []
        winner = choose_fuzzy_winner(terms.normalized, list(fuzzy_rows))
        return [winner] if winner else []

    def _dataset_search_trends(
        self, dataset_ids: List[int]
    ) -> dict[int, tuple[float, object, int]]:
        if not dataset_ids:
            return {}
        today = datetime.now(timezone.utc).date()
        recent_start = today - timedelta(days=90)
        recent_papers = func.count(
            func.distinct(
                case(
                    (
                        DBPaper.date_published > recent_start,
                        DBPaper.id,
                    ),
                    else_=None,
                )
            )
        )
        rows = (
            self.db.query(
                DBEvaluation.dataset_id,
                recent_papers,
                func.max(DBPaper.date_published),
                func.count(func.distinct(DBPaper.id)),
            )
            .join(
                DBPaper,
                (DBPaper.id == DBEvaluation.paper_id) & DBPaper.is_latest_version,
            )
            .filter(DBEvaluation.dataset_id.in_(dataset_ids))
            .group_by(DBEvaluation.dataset_id)
            .all()
        )
        return {
            int(dataset_id): (
                float(recent_count or 0) / 3.0,
                latest_date,
                int(all_time_count or 0),
            )
            for dataset_id, recent_count, latest_date, all_time_count in rows
        }

    def create_dataset(
        self, request: DatasetCreateRequest, *, commit: bool = True
    ) -> Dataset:
        """
        Create a new dataset and link it to specified tasks.

        Args:
            request: DatasetCreateRequest with dataset data and task IDs

        Returns:
            Created Dataset object

        Raises:
            CatalogPersistenceError: If database operation fails
            CatalogConflictError: If the generated slug already exists
            CatalogNotFoundError: If a requested task does not exist
        """
        try:
            # Generate slug from name
            slug = slugify(request.name)

            # Check if slug already exists
            existing_dataset = (
                self.db.query(DBDataset).filter(DBDataset.slug == slug).first()
            )
            if existing_dataset:
                raise CatalogConflictError(f"Dataset with slug '{slug}' already exists")

            # Validate that all task IDs exist
            existing_task_ids = set(
                self.db.query(DBTask.id).filter(DBTask.id.in_(request.task_ids)).all()
            )
            existing_task_ids = {task_id[0] for task_id in existing_task_ids}

            missing_task_ids = set(request.task_ids) - existing_task_ids
            if missing_task_ids:
                raise CatalogNotFoundError(
                    f"Task IDs not found: {sorted(missing_task_ids)}"
                )

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
            if commit:
                self.db.commit()
            else:
                self.db.flush()

            # Note: Task-dataset relationships are now defined via TASK_DATASET_METRICS.
            # If task_ids were provided in the request, use the leaderboard metrics API
            # (/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics) to define metrics
            # for each task-dataset pair.

            # Return the created dataset using the existing get_dataset method
            return self.get_dataset(db_dataset.id)

        except CatalogError:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise CatalogPersistenceError(f"Failed to create dataset: {e!s}")

    def update_dataset(self, dataset_id: int, request: DatasetUpdateRequest) -> Dataset:
        """
        Update an existing dataset.

        Args:
            dataset_id: Dataset ID to update
            request: DatasetUpdateRequest with fields to update

        Returns:
            Updated Dataset object

        Raises:
            CatalogPersistenceError: If database operation fails
            CatalogNotFoundError: If the dataset does not exist
        """
        try:
            # Get the existing dataset
            db_dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not db_dataset:
                raise CatalogNotFoundError(f"Dataset with ID {dataset_id} not found")

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

        except CatalogError:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            raise CatalogPersistenceError(f"Failed to update dataset: {e!s}")
