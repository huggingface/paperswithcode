"""
Area service for handling area-related business logic.

This service provides methods for retrieving and managing research area data,
including pagination, filtering, and task relationships.
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc, asc, or_

from backend.models.database import (
    Area as DBArea,
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    PaperTask,
    Task as DBTask,
    TaskDataset,
)
from backend.models.tasks import Task
from backend.models.taxonomy import (
    Area,
    Areas,
    AreasWithTaskBenchmarks,
    AreaWithTasks,
    AreasWithTasks,
    AreaWithTaskBenchmarks,
    TaskBenchmarkListItem,
    TaskWithBenchmarks,
)
from backend.services.dataset_service import _leaderboard_row_count
from backend.utils.entity_images import entity_image_url
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.services.catalog_errors import (
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)


class AreaService:
    """Service class for area-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_areas(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        order_by: str = "name",
        order_dir: str = "asc",
    ) -> Areas:
        """
        Get a paginated list of research areas with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of areas per page
            search: Search term for area name (full-text search)
            name: Filter by partial area name match
            order_by: Field to order by (name, created_at, task_count)
            order_dir: Order direction (asc, desc)

        Returns:
            Areas object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query
            query = self.db.query(DBArea)

            # Apply filters
            if search:
                # Use ilike for case-insensitive search
                query = query.filter(DBArea.name.ilike(f"%{search}%"))

            if name:
                query = query.filter(DBArea.name.ilike(f"%{name}%"))

            # Apply ordering
            if order_by == "name":
                order_field = DBArea.name
            elif order_by == "created_at":
                order_field = DBArea.created_at
            else:
                order_field = DBArea.name  # Default to name

            if order_dir == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            areas = []
            for db_area in results:
                area_dict = {
                    "id": str(db_area.id),
                    "name": db_area.name,
                    "description": db_area.description,
                    "created_at": db_area.created_at,
                    "updated_at": db_area.updated_at,
                }
                areas.append(Area(**area_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Areas(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=areas,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve areas: {str(e)}")

    def list_areas(self, **kwargs) -> Areas:
        try:
            return self.get_areas(**kwargs)
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    def list_areas_with_tasks(self) -> AreasWithTasks:
        try:
            return self.get_areas_with_tasks()
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    def list_areas_with_task_benchmarks(self, **kwargs) -> AreasWithTaskBenchmarks:
        try:
            return self.get_areas_with_task_benchmarks(**kwargs)
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    def lookup_area(self, area_id: str) -> Area:
        try:
            return self.get_area_by_id(area_id)
        except PaperNotFoundError as error:
            raise CatalogNotFoundError(str(error)) from error
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    def get_area_by_id(self, area_id: str) -> Area:
        """
        Get a specific research area by ID.

        Args:
            area_id: The area ID

        Returns:
            Area object

        Raises:
            PaperNotFoundError: If area not found
            DatabaseError: If database query fails
        """
        try:
            db_area = self.db.query(DBArea).filter(DBArea.id == int(area_id)).first()

            if not db_area:
                raise PaperNotFoundError(f"Area with ID {area_id} not found")

            area_dict = {
                "id": str(db_area.id),
                "name": db_area.name,
                "description": db_area.description,
                "created_at": db_area.created_at,
                "updated_at": db_area.updated_at,
            }

            return Area(**area_dict)

        except PaperNotFoundError:
            raise
        except ValueError as error:
            raise CatalogValidationError("Invalid area ID format") from error
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve area: {str(e)}")

    def search_areas(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Areas:
        """
        Search areas by name with full-text search.

        Args:
            query: Search query
            page: Page number (1-based)
            page_size: Number of areas per page

        Returns:
            Areas object with search results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Use case-insensitive search
            db_query = self.db.query(DBArea).filter(
                or_(
                    DBArea.name.ilike(f"%{query}%"),
                    DBArea.description.ilike(f"%{query}%")
                    if DBArea.description
                    else False,
                )
            )

            # Order by name
            db_query = db_query.order_by(DBArea.name)

            # Get total count
            total_count = db_query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = db_query.offset(offset).limit(page_size).all()

            # Convert to API models
            areas = []
            for db_area in results:
                area_dict = {
                    "id": str(db_area.id),
                    "name": db_area.name,
                    "description": db_area.description,
                    "created_at": db_area.created_at,
                    "updated_at": db_area.updated_at,
                }
                areas.append(Area(**area_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Areas(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=areas,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to search areas: {str(e)}")

    def get_areas_with_tasks(self) -> AreasWithTasks:
        """
        Return every area together with its tasks and direct association counts
        in a single response.

        Uses two queries:
          1. All areas, ordered by name.
          2. All top-level tasks joined to independent paper, benchmark, and
             evaluation aggregates. Subtasks stay on their parent task pages
             rather than appearing as peer domains in the top-level browse index.

        This collapses what used to be `1 + N_areas` HTTP requests from the
        frontend (one for `/areas/`, then one `/areas/{id}/tasks` per area) into
        a single backend round-trip.
        """
        try:
            area_rows = self.db.query(DBArea).order_by(DBArea.name).all()

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
            task_rows = (
                self.db.query(
                    DBTask,
                    func.coalesce(paper_counts.c.paper_count, 0),
                    func.coalesce(benchmark_counts.c.benchmark_count, 0),
                    func.coalesce(evaluation_counts.c.evaluation_count, 0),
                )
                .outerjoin(paper_counts, paper_counts.c.task_id == DBTask.id)
                .outerjoin(benchmark_counts, benchmark_counts.c.task_id == DBTask.id)
                .outerjoin(evaluation_counts, evaluation_counts.c.task_id == DBTask.id)
                .filter(DBTask.parent_id.is_(None))
                .filter(DBTask.level == 0)
                .order_by(DBTask.name)
                .all()
            )

            tasks_by_area: dict[Optional[int], list[Task]] = {}
            for db_task, paper_count, benchmark_count, evaluation_count in task_rows:
                api_task = Task(
                    id=str(db_task.id),
                    name=db_task.name,
                    description=db_task.description,
                    slug=db_task.slug,
                    keywords=db_task.keywords,
                    parent_id=str(db_task.parent_id) if db_task.parent_id else None,
                    area_id=str(db_task.area_id) if db_task.area_id else None,
                    level=db_task.level,
                    paper_count=paper_count or 0,
                    benchmark_count=benchmark_count or 0,
                    evaluation_count=evaluation_count or 0,
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
                tasks_by_area.setdefault(db_task.area_id, []).append(api_task)

            results = [
                AreaWithTasks(
                    id=str(area.id),
                    name=area.name,
                    description=area.description,
                    tasks=tasks_by_area.get(area.id, []),
                )
                for area in area_rows
            ]

            return AreasWithTasks(results=results)

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve areas with tasks: {str(e)}")

    def get_areas_with_task_benchmarks(
        self,
        benchmarks_per_task: int = 3,
        min_eval_count: int = 2,
    ) -> AreasWithTaskBenchmarks:
        """Return visible top-level tasks grouped by area with top benchmarks.

        Benchmark popularity is computed in one aggregate query, scoped to each
        task's own leaderboard, and sorted by logical evaluation-row count.
        """
        try:
            taxonomy = self.get_areas_with_tasks()
            tasks = [task for area in taxonomy.results for task in area.tasks]
            task_ids = [int(task.id) for task in tasks]
            if not task_ids:
                return AreasWithTaskBenchmarks(
                    results=[
                        AreaWithTaskBenchmarks(id=area.id, name=area.name)
                        for area in taxonomy.results
                    ]
                )

            evaluation_count = _leaderboard_row_count()
            benchmark_rows = (
                self.db.query(
                    TaskDataset.task_id,
                    DBDataset.id,
                    DBDataset.name,
                    DBDataset.slug,
                    DBDataset.full_name,
                    DBDataset.description,
                    DBDataset.hf_url,
                    evaluation_count.label("evaluation_count"),
                )
                .join(DBDataset, DBDataset.id == TaskDataset.dataset_id)
                .outerjoin(
                    DBEvaluation,
                    and_(
                        DBEvaluation.task_id == TaskDataset.task_id,
                        DBEvaluation.dataset_id == TaskDataset.dataset_id,
                    ),
                )
                .filter(TaskDataset.task_id.in_(task_ids))
                .group_by(TaskDataset.task_id, DBDataset.id)
                .all()
            )

            benchmarks_by_task: dict[int, list[TaskBenchmarkListItem]] = {}
            for (
                task_id,
                dataset_id,
                name,
                slug,
                full_name,
                description,
                hf_url,
                count,
            ) in benchmark_rows:
                count = int(count or 0)
                if count < min_eval_count:
                    continue
                benchmarks_by_task.setdefault(task_id, []).append(
                    TaskBenchmarkListItem(
                        id=dataset_id,
                        name=name,
                        slug=slug,
                        full_name=full_name,
                        description=description,
                        hf_url=hf_url,
                        evaluation_count=count,
                    )
                )

            for benchmarks in benchmarks_by_task.values():
                benchmarks.sort(
                    key=lambda benchmark: (
                        -benchmark.evaluation_count,
                        benchmark.name.casefold(),
                    )
                )
                del benchmarks[benchmarks_per_task:]

            results = []
            for area in taxonomy.results:
                area_tasks = []
                for task in area.tasks:
                    benchmarks = benchmarks_by_task.get(int(task.id), [])
                    if not benchmarks:
                        continue
                    area_tasks.append(
                        TaskWithBenchmarks(
                            id=task.id,
                            name=task.name,
                            slug=task.slug,
                            paper_count=task.paper_count or 0,
                            benchmarks=benchmarks,
                        )
                    )
                if area_tasks:
                    results.append(
                        AreaWithTaskBenchmarks(
                            id=area.id,
                            name=area.name,
                            tasks=area_tasks,
                        )
                    )

            return AreasWithTaskBenchmarks(results=results)
        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve areas with task benchmarks: {str(e)}"
            )
