"""
Task service for handling task-related business logic.

This service provides methods for retrieving and managing AI/ML task data,
including pagination, filtering, hierarchical relationships, and paper associations.
"""

from datetime import date, datetime, timedelta, timezone
import math
import time
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, case

from backend.models.database import (
    Task as DBTask,
    Area as DBArea,
    Paper as DBPaper,
    PaperTask,
    Repository as DBRepository,
    Evaluation as DBEvaluation,
    Framework as DBFramework,
    TaskDataset,
    TaskFramework as DBTaskFramework,
    TaskSisterTask as DBTaskSisterTask,
)
from backend.models.tasks import Task
from backend.models.taxonomy import (
    Area,
    Tasks,
    TaskCreateRequest,
    TaskPage,
    RecommendedFramework,
    TaskSubtaskBenchmarks,
    TrendingTask,
    TrendingTasks,
)
from backend.utils.entity_images import entity_image_url
from backend.utils.entity_images import load_entity_image
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.utils.slug_utils import slugify
from backend.utils.task_slugs import task_slug_candidates
from backend.services.share_lift import rank_by_share_lift
from backend.services.catalog_errors import (
    CatalogConflictError,
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


# Trending domains depend only on the date windows and the request filters,
# while the homepage asks for the same ranking on every visit. Papers arrive in
# daily imports, so a short shared cache keeps the ranking current.
TRENDING_TASKS_TTL_SECONDS = 600
_trending_tasks_cache: dict[tuple, tuple[float, TrendingTasks]] = {}


class TaskService:
    """Service class for task-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_task(self, identifier: str) -> Task:
        operation = (
            self.get_task_by_id if identifier.isdigit() else self.get_task_by_slug
        )
        return operation(identifier)

    def _require_db_task(self, identifier: str) -> DBTask:
        """Resolve a task by numeric id or slug, raising when it does not exist."""
        if str(identifier).isdigit():
            db_task = self.db.query(DBTask).filter(DBTask.id == int(identifier)).first()
        else:
            db_task = self._get_db_task_by_slug(str(identifier))
        if db_task is None:
            raise PaperNotFoundError(f"Task '{identifier}' not found")
        return db_task

    def _get_db_task_by_slug(self, slug: str) -> Optional[DBTask]:
        for candidate in task_slug_candidates(slug):
            task = self.db.query(DBTask).filter(DBTask.slug == candidate).first()
            if task is not None:
                return task
        return None

    def get_image(self, identifier: str) -> tuple[bytes, str]:
        for candidate in task_slug_candidates(identifier):
            result = load_entity_image(self.db, DBTask, candidate)
            if result is not None:
                return result
        raise CatalogNotFoundError("Image not available")

    def _build_task_model(
        self,
        db_task: DBTask,
        paper_count: int | None = None,
        benchmark_count: int | None = None,
        evaluation_count: int | None = None,
    ) -> Task:
        return Task(
            id=str(db_task.id),
            name=db_task.name,
            description=db_task.description,
            research_trends=db_task.research_trends or [],
            slug=db_task.slug,
            keywords=db_task.keywords,
            parent_id=str(db_task.parent_id) if db_task.parent_id else None,
            area_id=str(db_task.area_id) if db_task.area_id else None,
            level=db_task.level,
            paper_count=paper_count or 0,
            benchmark_count=benchmark_count,
            evaluation_count=evaluation_count,
            image_url=entity_image_url(
                "tasks",
                db_task.slug,
                db_task.image_mime_type is not None,
                db_task.image_url,
                db_task.updated_at,
            ),
            image_credit=db_task.image_credit,
            created_at=db_task.created_at,
            updated_at=db_task.updated_at,
        )

    def get_top_tasks(self, limit: int = 8) -> List[Task]:
        """
        Return the most common tasks for the homepage sidebar.

        Unlike the general paginated task listing, this deliberately skips the
        total-count query because the homepage only needs a small top-N list.
        """
        try:
            paper_count_col = func.count(PaperTask.paper_id).label("paper_count")
            results = (
                self.db.query(DBTask, paper_count_col)
                .join(PaperTask, DBTask.id == PaperTask.task_id)
                .filter(DBTask.parent_id.is_(None))
                .filter(DBTask.level == 0)
                .group_by(DBTask.id)
                .order_by(desc(paper_count_col), asc(DBTask.name))
                .limit(limit)
                .all()
            )

            return [
                self._build_task_model(db_task, int(paper_count or 0))
                for db_task, paper_count in results
            ]
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve top tasks: {str(e)}")

    def get_tasks(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        area_id: Optional[int] = None,
        parent_id: Optional[int] = None,
        level: Optional[int] = None,
        order_by: str = "name",
        order_dir: str = "asc",
        _task_ids: Optional[List[int]] = None,
        _count_override: Optional[int] = None,
    ) -> Tasks:
        """
        Get a paginated list of AI/ML tasks with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of tasks per page
            search: Name-only navigational task search
            name: Filter by partial task name match
            area_id: Filter by research area ID
            parent_id: Filter by parent task ID
            level: Filter by hierarchy level (0=top-level, 1=subtask, etc.)
            order_by: Field to order by (name, created_at, level, paper_count)
            order_dir: Order direction (asc, desc)

        Returns:
            Tasks object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        if search is not None:
            return self.search_tasks(query=search, page=page, page_size=page_size)

        try:
            # Pre-aggregate each relation independently so joining all three
            # count sources cannot multiply rows. This keeps the list endpoint
            # to one bounded query while returning exact direct-association
            # counts for papers, benchmarks, and stored evaluation rows.
            paper_counts = (
                self.db.query(
                    PaperTask.task_id.label("task_id"),
                    func.count(PaperTask.paper_id).label("paper_count"),
                )
                .group_by(PaperTask.task_id)
                .subquery()
            )
            benchmark_counts = (
                self.db.query(
                    TaskDataset.task_id.label("task_id"),
                    func.count(TaskDataset.dataset_id).label("benchmark_count"),
                )
                .group_by(TaskDataset.task_id)
                .subquery()
            )
            evaluation_counts = (
                self.db.query(
                    DBEvaluation.task_id.label("task_id"),
                    func.count(DBEvaluation.id).label("evaluation_count"),
                )
                .group_by(DBEvaluation.task_id)
                .subquery()
            )
            paper_count_col = func.coalesce(paper_counts.c.paper_count, 0).label(
                "paper_count"
            )
            benchmark_count_col = func.coalesce(
                benchmark_counts.c.benchmark_count, 0
            ).label("benchmark_count")
            evaluation_count_col = func.coalesce(
                evaluation_counts.c.evaluation_count, 0
            ).label("evaluation_count")
            query = (
                self.db.query(
                    DBTask,
                    paper_count_col,
                    benchmark_count_col,
                    evaluation_count_col,
                )
                .outerjoin(paper_counts, paper_counts.c.task_id == DBTask.id)
                .outerjoin(benchmark_counts, benchmark_counts.c.task_id == DBTask.id)
                .outerjoin(evaluation_counts, evaluation_counts.c.task_id == DBTask.id)
            )

            # Apply filters
            if _task_ids is not None:
                query = query.filter(DBTask.id.in_(_task_ids))

            if name:
                query = query.filter(DBTask.name.ilike(f"%{name}%"))

            if area_id is not None:
                query = query.filter(DBTask.area_id == area_id)

            if parent_id is not None:
                query = query.filter(DBTask.parent_id == parent_id)

            if level is not None:
                query = query.filter(DBTask.level == level)

            if order_by == "name":
                order_field = DBTask.name
            elif order_by == "created_at":
                order_field = DBTask.created_at
            elif order_by == "level":
                order_field = DBTask.level
            elif order_by == "paper_count":
                order_field = paper_count_col
            else:
                order_field = DBTask.name

            if order_dir == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Total count of distinct tasks matching filters (works with GROUP BY
            # because SQLAlchemy wraps it in a subquery).
            total_count = (
                _count_override if _count_override is not None else query.count()
            )

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            tasks = []
            for db_task, paper_count, benchmark_count, evaluation_count in results:
                tasks.append(
                    self._build_task_model(
                        db_task,
                        int(paper_count or 0),
                        int(benchmark_count or 0),
                        int(evaluation_count or 0),
                    )
                )

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Tasks(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=tasks,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve tasks: {str(e)}")

    def get_trending_tasks(
        self,
        limit: int = 8,
        recent_days: int = 30,
        baseline_days: int = 180,
        level: Optional[int] = None,
        min_recent_papers: int = 5,
        min_baseline_papers: int = 10,
        min_share_lift: float = 1.0,
        today: Optional[date] = None,
    ) -> TrendingTasks:
        """Return trending tasks, briefly cached on PostgreSQL."""
        today = today or datetime.now(timezone.utc).date()
        args = (
            limit,
            recent_days,
            baseline_days,
            level,
            min_recent_papers,
            min_baseline_papers,
            min_share_lift,
            today,
        )
        bind = self.db.get_bind()
        if bind.dialect.name != "postgresql":
            return self._compute_trending_tasks(*args)
        key = (str(bind.url), *args)
        cached = _trending_tasks_cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < TRENDING_TASKS_TTL_SECONDS:
            return cached[1]
        result = self._compute_trending_tasks(*args)
        if len(_trending_tasks_cache) >= 256:
            _trending_tasks_cache.clear()
        _trending_tasks_cache[key] = (now, result)
        return result

    def _compute_trending_tasks(
        self,
        limit: int,
        recent_days: int,
        baseline_days: int,
        level: Optional[int],
        min_recent_papers: int,
        min_baseline_papers: int,
        min_share_lift: float,
        today: date,
    ) -> TrendingTasks:
        """
        Rank tasks by how over-indexed they are in recent papers vs baseline.

        See ``backend.services.share_lift`` for the scoring. Results are
        sorted by descending ``share_lift`` so the order matches the
        multiplier shown in the UI; ``trend_score`` only breaks ties.
        """
        try:
            rows = rank_by_share_lift(
                self.db,
                DBTask,
                PaperTask.task_id,
                PaperTask.paper_id,
                limit=limit,
                recent_days=recent_days,
                baseline_days=baseline_days,
                min_recent_papers=min_recent_papers,
                min_baseline_papers=min_baseline_papers,
                min_share_lift=min_share_lift,
                today=today,
                filters=[DBTask.level == level] if level is not None else [],
            )
            results = [
                TrendingTask(
                    id=str(row.entity.id),
                    name=row.entity.name,
                    description=row.entity.description,
                    research_trends=row.entity.research_trends or [],
                    slug=row.entity.slug,
                    keywords=row.entity.keywords,
                    parent_id=str(row.entity.parent_id)
                    if row.entity.parent_id
                    else None,
                    area_id=str(row.entity.area_id) if row.entity.area_id else None,
                    level=row.entity.level,
                    paper_count=row.recent_paper_count + row.baseline_paper_count,
                    image_url=entity_image_url(
                        "tasks",
                        row.entity.slug,
                        row.entity.image_mime_type is not None,
                        row.entity.image_url,
                        row.entity.updated_at,
                    ),
                    image_credit=row.entity.image_credit,
                    created_at=row.entity.created_at,
                    updated_at=row.entity.updated_at,
                    recent_paper_count=row.recent_paper_count,
                    baseline_paper_count=row.baseline_paper_count,
                    share_lift=row.share_lift,
                    trend_score=row.trend_score,
                )
                for row in rows
            ]

            return TrendingTasks(
                results=results,
                recent_days=recent_days,
                baseline_days=baseline_days,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to compute trending tasks: {str(e)}")

    def get_task_by_id(self, task_id: str) -> Task:
        """
        Get a specific AI/ML task by ID.

        Args:
            task_id: The task ID

        Returns:
            Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database query fails
        """
        try:
            db_task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()

            if not db_task:
                raise PaperNotFoundError(f"Task with ID {task_id} not found")

            # Get paper count for this task
            paper_count = (
                self.db.query(func.count(PaperTask.paper_id))
                .filter(PaperTask.task_id == db_task.id)
                .scalar()
                or 0
            )

            return self._build_task_model(db_task, paper_count)

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve task: {str(e)}")

    def get_task_by_slug(self, slug: str) -> Task:
        """
        Get a specific AI/ML task by slug.

        Args:
            slug: The task slug

        Returns:
            Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database query fails
        """
        try:
            db_task = self._get_db_task_by_slug(slug)

            if not db_task:
                raise PaperNotFoundError(f"Task with slug '{slug}' not found")

            return self.get_task_by_id(str(db_task.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve task: {str(e)}")

    def get_task_children(
        self,
        task_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Tasks:
        """
        Get child tasks (subtasks) of a specific task.

        Args:
            task_id: The parent task ID
            page: Page number (1-based)
            page_size: Number of tasks per page
        Returns:
            Tasks object with child tasks

        Raises:
            PaperNotFoundError: If parent task not found
            DatabaseError: If database query fails
        """
        parent_task = self._require_db_task(task_id)
        return self.get_tasks(
            page=page,
            page_size=page_size,
            parent_id=parent_task.id,
            order_by="name",
            order_dir="asc",
        )

    def get_task_parents(self, task_id: str) -> List[Task]:
        """
        Get all parent tasks of a specific task (entire hierarchy up to root).

        Args:
            task_id: The task ID

        Returns:
            List of parent tasks from immediate parent to root

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database query fails
        """
        db_task = self._require_db_task(task_id)
        try:
            parents = []
            current = db_task

            # Traverse up the hierarchy
            while current.parent_id is not None:
                parent = (
                    self.db.query(DBTask).filter(DBTask.id == current.parent_id).first()
                )
                if not parent:
                    break

                # Get paper count for parent
                paper_count = (
                    self.db.query(func.count(PaperTask.paper_id))
                    .filter(PaperTask.task_id == parent.id)
                    .scalar()
                    or 0
                )

                parents.append(self._build_task_model(parent, paper_count))
                current = parent

            return parents

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve parent tasks: {str(e)}")

    def get_task_sisters(self, task_id: str) -> List[Task]:
        """
        Get the explicitly configured sister tasks for a task.

        Sister tasks are curated per task in `task_sister_tasks` and returned
        in ascending `display_order`. This is independent of the task's
        `area_id`; a task page shows exactly the sisters configured for it.

        Args:
            task_id: The task ID whose sister list to retrieve

        Returns:
            Ordered list of sister tasks (empty if none configured)

        Raises:
            DatabaseError: If database query fails
        """
        try:
            paper_count_col = func.count(PaperTask.paper_id).label("paper_count")
            rows = (
                self.db.query(DBTask, paper_count_col, DBTaskSisterTask.display_order)
                .join(
                    DBTaskSisterTask,
                    DBTaskSisterTask.sister_task_id == DBTask.id,
                )
                .outerjoin(PaperTask, PaperTask.task_id == DBTask.id)
                .filter(DBTaskSisterTask.task_id == int(task_id))
                .group_by(DBTask.id, DBTaskSisterTask.display_order)
                .order_by(asc(DBTaskSisterTask.display_order), asc(DBTask.name))
                .all()
            )

            return [
                self._build_task_model(db_task, int(paper_count or 0))
                for db_task, paper_count, _ in rows
            ]

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve sister tasks: {str(e)}")

    def get_task_recommended_frameworks(
        self, task_id: str
    ) -> List[RecommendedFramework]:
        """Return a task's curated frameworks in display order."""
        try:
            rows = (
                self.db.query(DBRepository, DBFramework)
                .join(
                    DBFramework,
                    DBFramework.repository_id == DBRepository.id,
                )
                .join(
                    DBTaskFramework,
                    DBTaskFramework.framework_id == DBFramework.id,
                )
                .filter(DBTaskFramework.task_id == int(task_id))
                .order_by(
                    asc(DBTaskFramework.display_order),
                    asc(DBRepository.owner),
                    asc(DBRepository.name),
                )
                .all()
            )
            return [
                RecommendedFramework(
                    id=repository.id,
                    framework_id=framework.id,
                    framework_slug=framework.slug,
                    framework_name=framework.name,
                    url=repository.url,
                    owner=repository.owner,
                    name=repository.name,
                    num_stars=repository.num_stars,
                )
                for repository, framework in rows
            ]
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve recommended frameworks: {str(e)}")

    def get_task_page(
        self,
        task_id: str,
        direct_benchmark_limit: int = 100,
        subtask_benchmark_limit: int = 20,
        min_eval_count: int = 2,
        is_open: Optional[bool] = None,
    ) -> TaskPage:
        """
        Build the bundled task-page payload in a single call.

        Collapses the task-detail page's initial fan-out (detail, parents,
        sister tasks, recommended frameworks, children, direct benchmarks,
        per-child benchmark previews) so the frontend makes one request.
        """
        # Import here to avoid a circular import at module load time.
        from backend.services.dataset_service import DatasetService

        # Resolve the task by numeric id or slug.
        if str(task_id).isdigit():
            task = self.get_task_by_id(str(task_id))
        else:
            task = self.get_task_by_slug(task_id)

        area = None
        if task.area_id:
            db_area = (
                self.db.query(DBArea).filter(DBArea.id == int(task.area_id)).first()
            )
            if db_area:
                area = Area.model_validate(db_area)

        parents = self.get_task_parents(task.id)

        sisters = self.get_task_sisters(task.id)
        recommended_frameworks = self.get_task_recommended_frameworks(task.id)

        children = self.get_task_children(task.id, page_size=50).results

        dataset_service = DatasetService(self.db)
        benchmarks = dataset_service.get_datasets(
            task_id=int(task.id),
            page_size=direct_benchmark_limit,
            order_by="paper_count",
            order_dir="desc",
            min_eval_count=min_eval_count,
            is_open=is_open,
        ).results

        subtask_benchmarks: List[TaskSubtaskBenchmarks] = []
        for child in children:
            child_benchmarks = dataset_service.get_datasets(
                task_id=int(child.id),
                page_size=subtask_benchmark_limit,
                order_by="paper_count",
                order_dir="desc",
                min_eval_count=min_eval_count,
                is_open=is_open,
            ).results
            subtask_benchmarks.append(
                TaskSubtaskBenchmarks(subtask_id=child.id, benchmarks=child_benchmarks)
            )

        return TaskPage(
            task=task,
            area=area,
            parents=parents,
            sisters=sisters,
            recommended_frameworks=recommended_frameworks,
            children=children,
            benchmarks=benchmarks,
            subtask_benchmarks=subtask_benchmarks,
        )

    def get_tasks_by_area(
        self,
        area_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Tasks:
        """
        Get all tasks associated with a specific research area.

        Args:
            area_id: The research area ID
            page: Page number (1-based)
            page_size: Number of tasks per page
        Returns:
            Tasks object with tasks in the area

        Raises:
            PaperNotFoundError: If area not found
            DatabaseError: If database query fails
        """
        try:
            # Verify area exists
            area = self.db.query(DBArea).filter(DBArea.id == int(area_id)).first()
            if not area:
                raise PaperNotFoundError(f"Area with ID {area_id} not found")

            # Get tasks for this area
            return self.get_tasks(
                page=page,
                page_size=page_size,
                area_id=int(area_id),
                order_by="name",
                order_dir="asc",
            )

        except PaperNotFoundError:
            raise
        except ValueError as error:
            raise CatalogValidationError("Invalid area ID format") from error
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve tasks for area: {str(e)}")

    def search_tasks(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Tasks:
        """Search displayed task names with deterministic and typo lanes.

        Args:
            query: Search query
            page: Page number (1-based)
            page_size: Number of tasks per page
        Returns:
            Tasks object with search results

        Raises:
            DatabaseError: If database query fails
        """
        terms = prepare_entity_search(query, EntitySearchKind.TASK)
        if not terms.usable:
            return empty_page(Tasks)

        candidates = self._task_search_candidates(terms)
        if not candidates:
            return empty_page(Tasks)
        trend = self._task_search_trends(
            [candidate.entity_id for candidate in candidates]
        )
        candidates.sort(
            key=lambda candidate: (
                candidate.tier,
                -candidate.relevance,
                -trend.get(candidate.entity_id, (0.0, 0))[0],
                -trend.get(candidate.entity_id, (0.0, 0))[1],
                candidate.name.casefold(),
                candidate.entity_id,
            )
        )

        offset = (page - 1) * page_size
        page_candidates = candidates[offset : offset + page_size]
        page_ids = [candidate.entity_id for candidate in page_candidates]
        response = self.get_tasks(
            page=1,
            page_size=max(1, len(page_ids)),
            _task_ids=page_ids,
            _count_override=len(candidates),
        )
        by_id = {int(task.id): task for task in response.results}
        response.results = [
            by_id[entity_id] for entity_id in page_ids if entity_id in by_id
        ]
        response.next_page = page + 1 if offset + page_size < len(candidates) else None
        response.previous_page = page - 1 if page > 1 else None
        return response

    def _task_search_candidates(self, terms) -> List[EntitySearchCandidate]:
        base = self.db.query(DBTask)
        if self.db.bind.dialect.name != "postgresql":
            tasks = base.all()
            candidates = []
            for task in tasks:
                match = deterministic_match(terms, name=task.name, slug=task.slug)
                if match:
                    candidates.append(
                        EntitySearchCandidate(
                            int(task.id), task.name, match[0], match[1]
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
            fuzzy_rows = [(int(task.id), task.name, 0.0) for task in tasks]
        else:
            predicate, tier, relevance = postgres_search_expressions(DBTask, terms)
            rows = (
                base.with_entities(
                    DBTask.id,
                    DBTask.name,
                    tier.label("tier"),
                    relevance.label("relevance"),
                )
                .filter(predicate)
                .order_by(
                    asc(tier),
                    desc(relevance),
                    asc(DBTask.name),
                    asc(DBTask.id),
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
                DBTask.name, terms.normalized
            )
            fuzzy_rows = (
                base.with_entities(DBTask.id, DBTask.name, similarity)
                .order_by(distance, asc(DBTask.id))
                .limit(FUZZY_CANDIDATE_LIMIT)
                .all()
            )

        if terms.identity_only or len("".join(terms.tokens)) < 4:
            return []
        winner = choose_fuzzy_winner(terms.normalized, list(fuzzy_rows))
        return [winner] if winner else []

    def _task_search_trends(self, task_ids: List[int]) -> dict[int, tuple[float, int]]:
        if not task_ids:
            return {}
        today = datetime.now(timezone.utc).date()
        recent_start = today - timedelta(days=30)
        baseline_start = recent_start - timedelta(days=180)

        global_recent, global_baseline = (
            self.db.query(
                func.count(
                    func.distinct(
                        case(
                            (
                                DBPaper.date_published > recent_start,
                                DBPaper.id,
                            ),
                            else_=None,
                        )
                    )
                ),
                func.count(
                    func.distinct(
                        case(
                            (
                                (DBPaper.date_published > baseline_start)
                                & (DBPaper.date_published <= recent_start),
                                DBPaper.id,
                            ),
                            else_=None,
                        )
                    )
                ),
            )
            .filter(
                DBPaper.is_latest_version,
                DBPaper.date_published > baseline_start,
                DBPaper.date_published <= today,
            )
            .one()
        )
        activity_rows = (
            self.db.query(
                PaperTask.task_id,
                func.count(
                    func.distinct(
                        case(
                            (
                                DBPaper.date_published > recent_start,
                                DBPaper.id,
                            ),
                            else_=None,
                        )
                    )
                ),
                func.count(
                    func.distinct(
                        case(
                            (
                                (DBPaper.date_published > baseline_start)
                                & (DBPaper.date_published <= recent_start),
                                DBPaper.id,
                            ),
                            else_=None,
                        )
                    )
                ),
            )
            .join(
                DBPaper,
                (DBPaper.id == PaperTask.paper_id) & DBPaper.is_latest_version,
            )
            .filter(
                PaperTask.task_id.in_(task_ids),
                DBPaper.date_published > baseline_start,
                DBPaper.date_published <= today,
            )
            .group_by(PaperTask.task_id)
            .all()
        )
        all_time_rows = (
            self.db.query(PaperTask.task_id, func.count(PaperTask.paper_id))
            .filter(PaperTask.task_id.in_(task_ids))
            .group_by(PaperTask.task_id)
            .all()
        )
        activity = {
            int(task_id): (int(recent or 0), int(baseline or 0))
            for task_id, recent, baseline in activity_rows
        }
        all_time = {int(task_id): int(count or 0) for task_id, count in all_time_rows}
        result = {}
        for task_id in task_ids:
            recent, baseline = activity.get(task_id, (0, 0))
            if recent and baseline and global_recent and global_baseline:
                share_lift = (recent / global_recent) / (baseline / global_baseline)
                trend_score = share_lift * math.log1p(recent)
            else:
                trend_score = 0.0
            result[task_id] = (trend_score, all_time.get(task_id, 0))
        return result

    def get_task_papers(
        self,
        task_id: str,
        page: int = 1,
        page_size: int = 20,
        latest_only: bool = True,
        order_by: str = "date_published",
        order_dir: str = "desc",
        include_resources: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        repository_limit: Optional[int] = None,
    ):
        """
        Get papers associated with a specific task.

        Args:
            task_id: The task ID or slug
            page: Page number (1-based)
            page_size: Number of papers per page
            latest_only: Whether to only include latest versions
            order_by: Field to order by (date_published, title, citation_count, trending)
            order_dir: Order direction (asc, desc); ignored for trending which is always desc
            include_resources: Whether to include repositories and tasks
            repository_limit: Max repositories per paper when including resources

        Returns:
            Papers object with pagination info and results

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database query fails
        """
        try:
            from backend.models.database import Paper as DBPaper

            # Get task to verify it exists (try by ID or slug)
            task = None
            if task_id.isdigit():
                task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            else:
                task = self._get_db_task_by_slug(task_id)

            if not task:
                raise PaperNotFoundError(f"Task with ID or slug '{task_id}' not found")

            # Base query for papers with this task
            query = (
                self.db.query(DBPaper)
                .join(PaperTask, DBPaper.id == PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
            )

            from backend.services.paper_feed_executor import (
                PaperFeedExecutor,
                SCOPED_ORDERING,
            )
            from backend.services.paper_service import PaperService

            return PaperFeedExecutor(PaperService(self.db)).execute(
                query,
                page=page,
                page_size=page_size,
                latest_only=latest_only,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
                start_date=start_date,
                end_date=end_date,
                order_by=order_by,
                order_dir=order_dir,
                ordering=SCOPED_ORDERING,
                deduplicate_task_id=task.id,
                include_resources=include_resources,
                repository_limit=repository_limit,
            )

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to get papers for task: {str(e)}")

    def add_keywords(self, task_id: str, keywords: List[str]) -> Task:
        """
        Add keywords to a task (appends to existing keywords).

        Args:
            task_id: The task ID or slug
            keywords: List of keywords to add

        Returns:
            Updated Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database operation fails
        """
        try:
            # Get task - try by ID or slug
            task = None
            if task_id.isdigit():
                task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            else:
                task = self._get_db_task_by_slug(task_id)

            if not task:
                raise PaperNotFoundError(f"Task with ID or slug '{task_id}' not found")

            # Parse existing keywords
            existing_keywords = []
            if task.keywords:
                existing_keywords = [kw.strip() for kw in task.keywords.split(",")]

            # Add new keywords (avoid duplicates)
            for keyword in keywords:
                keyword = keyword.strip()
                if keyword and keyword not in existing_keywords:
                    existing_keywords.append(keyword)

            # Update keywords
            task.keywords = ", ".join(existing_keywords)
            self.db.commit()
            self.db.refresh(task)

            # Return updated task
            return self.get_task_by_id(str(task.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to add keywords to task: {str(e)}")

    def remove_keywords(self, task_id: str, keywords: List[str]) -> Task:
        """
        Remove specific keywords from a task.

        Args:
            task_id: The task ID or slug
            keywords: List of keywords to remove

        Returns:
            Updated Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database operation fails
        """
        try:
            # Get task - try by ID or slug
            task = None
            if task_id.isdigit():
                task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            else:
                task = self._get_db_task_by_slug(task_id)

            if not task:
                raise PaperNotFoundError(f"Task with ID or slug '{task_id}' not found")

            # Parse existing keywords
            existing_keywords = []
            if task.keywords:
                existing_keywords = [kw.strip() for kw in task.keywords.split(",")]

            # Remove specified keywords
            keywords_to_remove = [kw.strip().lower() for kw in keywords]
            existing_keywords = [
                kw for kw in existing_keywords if kw.lower() not in keywords_to_remove
            ]

            # Update keywords
            task.keywords = ", ".join(existing_keywords) if existing_keywords else None
            self.db.commit()
            self.db.refresh(task)

            # Return updated task
            return self.get_task_by_id(str(task.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to remove keywords from task: {str(e)}")

    def replace_keywords(self, task_id: str, keywords: List[str]) -> Task:
        """
        Replace all keywords for a task.

        Args:
            task_id: The task ID or slug
            keywords: List of keywords to set (replaces all existing keywords)

        Returns:
            Updated Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database operation fails
        """
        try:
            # Get task - try by ID or slug
            task = None
            if task_id.isdigit():
                task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            else:
                task = self._get_db_task_by_slug(task_id)

            if not task:
                raise PaperNotFoundError(f"Task with ID or slug '{task_id}' not found")

            # Set new keywords
            cleaned_keywords = [kw.strip() for kw in keywords if kw.strip()]
            task.keywords = ", ".join(cleaned_keywords) if cleaned_keywords else None
            self.db.commit()
            self.db.refresh(task)

            # Return updated task
            return self.get_task_by_id(str(task.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to replace keywords for task: {str(e)}")

    def create_task(self, request: TaskCreateRequest, *, commit: bool = True) -> Task:
        """
        Create a new task.

        Args:
            request: TaskCreateRequest with task data

        Returns:
            Created Task object

        Raises:
            DatabaseError: If database operation fails
            ValueError: If area_id or parent_id don't exist, or slug already exists
        """
        try:
            # Validate area_id exists if provided
            if request.area_id is not None:
                area = (
                    self.db.query(DBArea).filter(DBArea.id == request.area_id).first()
                )
                if not area:
                    raise CatalogValidationError(
                        f"Area with ID {request.area_id} not found"
                    )

            # Validate parent_id exists if provided and calculate level
            level = 0
            if request.parent_id is not None:
                parent = (
                    self.db.query(DBTask).filter(DBTask.id == request.parent_id).first()
                )
                if not parent:
                    raise CatalogValidationError(
                        f"Parent task with ID {request.parent_id} not found"
                    )
                level = parent.level + 1

            # Generate slug from name
            slug = slugify(request.name)

            # Check if slug already exists
            existing_task = self.db.query(DBTask).filter(DBTask.slug == slug).first()
            if existing_task:
                raise CatalogConflictError(f"Task with slug '{slug}' already exists")

            # Create the task
            db_task = DBTask(
                name=request.name,
                slug=slug,
                description=request.description,
                keywords=request.keywords,
                area_id=request.area_id,
                parent_id=request.parent_id,
                level=level,
                image_url=request.image_url,
                image_credit=request.image_credit,
            )

            self.db.add(db_task)
            if commit:
                self.db.commit()
            else:
                self.db.flush()
            self.db.refresh(db_task)

            # Return the created task using the existing get_task_by_id method
            return self.get_task_by_id(str(db_task.id))

        except ValueError as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            raise CatalogPersistenceError(f"Failed to create task: {str(e)}") from e
