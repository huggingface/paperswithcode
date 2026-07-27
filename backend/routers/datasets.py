"""
Datasets API router.

Provides endpoints for accessing benchmark dataset data, including filtering by task,
paper associations, and evaluation data.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.api import (
    Dataset,
    Datasets,
    DatasetCreateRequest,
    DatasetUpdateRequest,
    DatasetMetricAddRequest,
    DatasetMetricSetRequest,
)
from backend.services.dataset_service import DatasetService
from backend.services.leaderboard_metric_service import LeaderboardMetricService
from backend.database.connection import get_database_session
from backend.utils.exceptions import DatabaseError
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/", response_model=Datasets)
def list_datasets(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of datasets per page (max 100)"
    ),
    q: Optional[str] = Query(
        None, description="Search query for dataset name, full name, and description"
    ),
    name: Optional[str] = Query(
        None, description="Filter by partial dataset name match"
    ),
    full_name: Optional[str] = Query(
        None, description="Filter by partial full name match"
    ),
    task: Optional[str] = Query(None, description="Filter by task ID or task slug"),
    include_descendants: bool = Query(
        False,
        description=(
            "When `task` is set, also include datasets linked to subtasks "
            "(child tasks under the task hierarchy). Useful for parent task "
            "pages that want to roll up benchmarks from their subtasks."
        ),
    ),
    min_eval_count: Optional[int] = Query(
        None,
        ge=1,
        description=(
            "Hide benchmarks whose evaluation row count (`paper_count`) is "
            "below this threshold. Used by task pages to suppress sparse "
            "benchmarks (e.g. < 2 evaluations) by default."
        ),
    ),
    is_open: Optional[bool] = Query(
        None,
        description=(
            "When task-scoped, choose `best_model_name` from only open-source "
            "or only closed-source evaluation rows. Does not filter benchmark "
            "membership or paper_count."
        ),
    ),
    ordering: Optional[str] = Query(
        "name",
        description="Order by field: name, full_name, created_at, paper_count (prefix with '-' for descending)",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of benchmark datasets.

    Datasets can be filtered by name, task, or searched across name and description.
    Supports ordering and pagination.

    **Example queries:**
    - `/api/v1/datasets/` - Get all datasets
    - `/api/v1/datasets/?task=123` - Get datasets for task ID 123
    - `/api/v1/datasets/?q=imagenet` - Search for datasets containing "imagenet"
    - `/api/v1/datasets/?name=COCO` - Filter datasets by name containing "COCO"
    - `/api/v1/datasets/?ordering=-name` - Order by name descending
    """
    try:
        # Parse ordering
        order_dir = "asc"
        order_by = ordering
        if ordering and ordering.startswith("-"):
            order_dir = "desc"
            order_by = ordering[1:]

        # Validate order_by field
        valid_fields = ["name", "full_name", "created_at", "paper_count"]
        if order_by not in valid_fields:
            order_by = "name"

        service = DatasetService(db)

        # Parse task parameter (could be ID or slug)
        task_id = None
        if task:
            try:
                task_id = int(task)
            except ValueError:
                # If not an integer, treat as slug and look up task ID
                from backend.models.database import Task as DBTask

                task_obj = db.query(DBTask).filter(DBTask.slug == task).first()
                if task_obj:
                    task_id = task_obj.id

        # Search still respects task / descendant / min_eval_count filters.
        if q:
            return service.search_datasets(
                query=q,
                page=page,
                page_size=page_size,
                task_id=task_id,
                include_descendants=include_descendants,
                min_eval_count=min_eval_count,
                is_open=is_open,
            )

        return service.get_datasets(
            page=page,
            page_size=page_size,
            name=name,
            full_name=full_name,
            task_id=task_id,
            include_descendants=include_descendants,
            order_by=order_by,
            order_dir=order_dir,
            min_eval_count=min_eval_count,
            is_open=is_open,
        )

    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{dataset_id}", response_model=Dataset)
def get_dataset(
    dataset_id: str,
    include_paper: bool = Query(
        False,
        description=(
            "Embed a lightweight introducing-paper projection (arxiv_id, title, "
            "published) so callers don't need a follow-up request to GET "
            "/papers/{id}.  Used by the benchmark detail page."
        ),
    ),
    task: Optional[str] = Query(
        None,
        description=(
            "Task ID or slug used to embed a lightweight leaderboard summary."
        ),
    ),
    is_open: Optional[bool] = Query(
        None,
        description=(
            "When task-scoped, select the summary from only open-source or "
            "only closed-source evaluation rows."
        ),
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a specific dataset by its ID or slug.

    Returns detailed information about the dataset including name, description,
    URLs, and metadata about associated papers and tasks.

    **Example:**
    - `/api/v1/datasets/123` - Get dataset with ID 123
    - `/api/v1/datasets/coco` - Get dataset with slug "coco"
    - `/api/v1/datasets/coco?include_paper=true` - Also embed the introducing paper
    - `/api/v1/datasets/coco?task=object-detection` - Also embed the leaderboard summary
    """
    try:
        service = DatasetService(db)
        task_id = None
        if task:
            try:
                task_id = int(task)
            except ValueError:
                from backend.models.database import Task as DBTask

                task_obj = (
                    db.query(DBTask)
                    .filter(func.lower(DBTask.slug) == task.lower())
                    .first()
                )
                if task_obj:
                    task_id = task_obj.id

        # Try to parse as integer ID first
        try:
            dataset_id_int = int(dataset_id)
            dataset = service.get_dataset(
                dataset_id_int,
                include_paper=include_paper,
                task_id=task_id,
                is_open=is_open,
            )
        except ValueError:
            # Not an integer, treat as slug
            dataset = service.get_dataset_by_slug(
                dataset_id,
                include_paper=include_paper,
                task_id=task_id,
                is_open=is_open,
            )

        if not dataset:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset with ID or slug '{dataset_id}' not found",
            )

        return dataset

    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{dataset_id}/tasks/")
def get_dataset_tasks(
    dataset_id: str,
    db: Session = Depends(get_database_session),
):
    """
    Get tasks associated with a specific dataset.

    Returns a list of tasks that have evaluations on this dataset.

    **Example:**
    - `/api/v1/datasets/6/tasks/` - Get tasks for dataset 6
    """
    try:
        # Parse dataset_id (can be ID or slug)
        try:
            dataset_id_int = int(dataset_id)
        except ValueError:
            # Try to resolve slug to ID
            dataset_service = DatasetService(db)
            dataset = dataset_service.get_dataset_by_slug(dataset_id)
            if not dataset:
                raise HTTPException(
                    status_code=404,
                    detail=f"Dataset with slug '{dataset_id}' not found",
                )
            dataset_id_int = int(dataset.id)

        # Get tasks for this dataset via task_datasets display membership.
        from backend.models.database import Task as DBTask, TaskDataset
        from backend.models.api import Task

        tasks_query = (
            db.query(DBTask)
            .join(TaskDataset, DBTask.id == TaskDataset.task_id)
            .filter(TaskDataset.dataset_id == dataset_id_int)
            .distinct()
            .order_by(DBTask.name)
            .all()
        )

        # Convert to API models
        tasks = []
        for task in tasks_query:
            # Get paper count for this task
            from backend.models.database import PaperTask
            from sqlalchemy import func

            paper_count = (
                db.query(func.count(PaperTask.paper_id))
                .filter(PaperTask.task_id == task.id)
                .scalar()
                or 0
            )

            task_dict = {
                "id": str(task.id),
                "name": task.name,
                "description": task.description,
                "slug": task.slug,
                "keywords": task.keywords,
                "parent_id": str(task.parent_id) if task.parent_id else None,
                "area_id": str(task.area_id) if task.area_id else None,
                "level": task.level,
                "paper_count": paper_count,
                "image_url": task.image_url,
                "image_credit": task.image_credit,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
            tasks.append(Task(**task_dict))

        return {"count": len(tasks), "results": tasks}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tasks for dataset: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{dataset_id}/evaluations/", response_model=dict)
def get_dataset_evaluations(
    dataset_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of evaluations per page (max 100)"
    ),
    ordering: Optional[str] = Query(
        "-best_rank",
        description="Order by field: created_at, best_rank, evaluated_on (prefix with '-' for descending)",
    ),
    is_open: Optional[bool] = Query(
        None,
        description=(
            "Filter by open-source status of the evaluated model. "
            "Pass `true` to return only open-source rows (hides closed-source)."
        ),
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get evaluation results for a specific dataset.

    Returns paginated list of benchmark evaluation results for papers evaluated on this dataset.
    This endpoint matches the legacy PapersWithCode API pattern.

    **Example:**
    - `/api/v1/datasets/123/evaluations/` - Get evaluations for dataset 123
    """
    try:
        # Parse dataset_id
        try:
            dataset_id_int = int(dataset_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset ID. Must be an integer."
            )

        dataset_service = DatasetService(db)

        # Check if dataset exists
        dataset = dataset_service.get_dataset(dataset_id_int)
        if not dataset:
            raise HTTPException(
                status_code=404, detail=f"Dataset with ID {dataset_id} not found"
            )

        # Parse ordering
        order_dir = "asc"
        order_by = "created_at"
        if ordering:
            if ordering.startswith("-"):
                order_dir = "desc"
                order_by = ordering[1:]
            else:
                order_dir = "asc"
                order_by = ordering

        # Use EvaluationService to fetch actual evaluation data
        from backend.services.evaluation_service import EvaluationService

        evaluation_service = EvaluationService(db)
        evaluations_response = evaluation_service.get_evaluations(
            page=page,
            page_size=page_size,
            dataset_id=dataset_id_int,
            is_open=is_open,
            order_by=order_by,
            order_dir=order_dir,
        )

        # Return in the expected format
        return {
            "count": evaluations_response.count,
            "next_page": evaluations_response.next_page,
            "previous_page": evaluations_response.previous_page,
            "results": [eval.model_dump() for eval in evaluations_response.results],
        }

    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/", response_model=Dataset, status_code=201)
def create_dataset(
    request: DatasetCreateRequest,
    db: Session = Depends(get_database_session),
):
    """
    Create a new dataset and link it to specified tasks.

    Creates a new benchmark dataset with the provided information and automatically
    links it to the specified tasks. The dataset slug is auto-generated from the name.

    **Request Body:**
    ```json
    {
        "name": "Video-MMLU",
        "full_name": "Video-MMLU: A Massive Multi-Discipline Lecture Understanding Benchmark",
        "description": "A comprehensive benchmark for evaluating Large Multimodal Models",
        "url": "https://enxinsong.com/Video-MMLU-web/",
        "hf_url": "https://huggingface.co/datasets/Enxin/Video-MMLU",
        "paper_url": "https://arxiv.org/abs/2504.14693",
        "task_ids": [9],
        "modalities": ["Videos", "Text"],
        "languages": ["English"],
        "license_name": "MIT",
        "introduced_date": "2025-01-01"
    }
    ```

    **Returns:**
    - Created dataset object with auto-generated slug and task associations
    - 201 status code on success

    **Errors:**
    - 400: Invalid request data or missing required fields
    - 404: One or more task IDs not found
    - 409: Dataset with the same slug already exists
    - 500: Internal server error
    """
    try:
        service = DatasetService(db)
        return service.create_dataset(request)

    except ValueError as e:
        if "Task IDs not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        elif "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/{dataset_id}", response_model=Dataset)
def update_dataset(
    dataset_id: str,
    request: DatasetUpdateRequest,
    db: Session = Depends(get_database_session),
):
    """
    Update an existing dataset.

    Updates fields of an existing dataset. Only provided fields will be updated.
    Fields not included in the request will remain unchanged.

    **Request Body:**
    ```json
    {
        "hf_url": "https://huggingface.co/datasets/depth-anything/DA-2K",
        "description": "Updated description"
    }
    ```

    **Example:**
    - `PUT /api/v1/datasets/277` - Update dataset with ID 277
    - `PUT /api/v1/datasets/da-2k` - Update dataset with slug "da-2k"

    **Returns:**
    - Updated dataset object
    - 404 if dataset not found
    - 500 on server error
    """
    try:
        service = DatasetService(db)

        # Try to parse as integer ID first
        try:
            dataset_id_int = int(dataset_id)
        except ValueError:
            # Not an integer, treat as slug and look up dataset ID
            dataset = service.get_dataset_by_slug(dataset_id)
            if not dataset:
                raise HTTPException(
                    status_code=404,
                    detail=f"Dataset with slug '{dataset_id}' not found",
                )
            dataset_id_int = int(dataset.id)

        return service.update_dataset(dataset_id_int, request)

    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Leaderboard-Metric Management Endpoints (New: task-dataset-metric triples)


@router.get("/{dataset_id}/tasks/{task_id}/metrics", response_model=dict)
def get_leaderboard_metrics(
    dataset_id: str,
    task_id: str,
    db: Session = Depends(get_database_session),
):
    """
    Get all allowed metrics for a specific leaderboard (task + dataset).

    Leaderboards are now defined by (task, dataset, metric) triples. This endpoint
    returns the list of metrics that are valid for evaluation submissions on this
    specific leaderboard.

    **Example:**
    - `/api/v1/datasets/6/tasks/12/metrics` - Get allowed metrics for Object Detection on COCO

    **Returns:**
    ```json
    {
        "task_id": "12",
        "dataset_id": "6",
        "task_name": "Object Detection",
        "dataset_name": "COCO",
        "supports_harness": false,
        "metrics": [
            {
                "metric_id": "1",
                "metric_name": "AP",
                "metric_direction": "higher_is_better",
                "created_at": "2025-11-01T12:00:00Z"
            },
            ...
        ]
    }
    ```
    """
    try:
        # Parse IDs
        try:
            dataset_id_int = int(dataset_id)
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset or task ID. Must be integers."
            )

        service = LeaderboardMetricService(db)
        return service.get_leaderboard_metrics(task_id_int, dataset_id_int)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post(
    "/{dataset_id}/tasks/{task_id}/metrics", response_model=dict, status_code=201
)
def add_metric_to_leaderboard(
    dataset_id: str,
    task_id: str,
    request: DatasetMetricAddRequest,
    db: Session = Depends(get_database_session),
):
    """
    Add a metric to a leaderboard's allowed metrics list.

    Links a metric to a specific leaderboard (task + dataset), allowing evaluations
    to use this metric when submitting results for this leaderboard.

    **Example:**
    ```
    POST /api/v1/datasets/6/tasks/12/metrics
    {
        "metric_name": "AP50"
    }
    ```

    **Returns:**
    - 201 status with the created link
    - 400 if task, dataset, or metric not found
    - 409 if metric is already linked to this leaderboard
    """
    try:
        # Parse IDs
        try:
            dataset_id_int = int(dataset_id)
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset or task ID. Must be integers."
            )

        service = LeaderboardMetricService(db)
        return service.add_metric_to_leaderboard(
            task_id_int, dataset_id_int, request.metric_name
        )

    except ValueError as e:
        if "already linked" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        else:
            raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/{dataset_id}/tasks/{task_id}/metrics", response_model=dict)
def set_leaderboard_metrics(
    dataset_id: str,
    task_id: str,
    request: DatasetMetricSetRequest,
    db: Session = Depends(get_database_session),
):
    """
    Set all allowed metrics for a leaderboard (replaces existing).

    Replaces all existing metric links for this specific leaderboard with the
    provided list. This is useful for bulk configuration of leaderboard metrics.

    **Example:**
    ```
    PUT /api/v1/datasets/6/tasks/12/metrics
    {
        "metric_names": ["AP", "AP50", "AP75", "APs", "APm", "APl"]
    }
    ```

    **Returns:**
    - Updated leaderboard metrics object
    - 404 if task, dataset, or any metric not found
    """
    try:
        # Parse IDs
        try:
            dataset_id_int = int(dataset_id)
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset or task ID. Must be integers."
            )

        service = LeaderboardMetricService(db)
        return service.set_leaderboard_metrics(
            task_id_int, dataset_id_int, request.metric_names
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/{dataset_id}/tasks/{task_id}/metrics/{metric_name}", status_code=204)
def remove_metric_from_leaderboard(
    dataset_id: str,
    task_id: str,
    metric_name: str,
    db: Session = Depends(get_database_session),
):
    """
    Remove a metric from a leaderboard's allowed metrics list.

    Unlinks a metric from a specific leaderboard. After removal, evaluations can
    no longer use this metric when submitting results for this leaderboard.

    **Example:**
    - `DELETE /api/v1/datasets/6/tasks/12/metrics/AP50` - Remove AP50 from Object Detection on COCO

    **Returns:**
    - 204 No Content on success
    - 404 if task, dataset, metric, or link not found
    """
    try:
        # Parse IDs
        try:
            dataset_id_int = int(dataset_id)
            task_id_int = int(task_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset or task ID. Must be integers."
            )

        service = LeaderboardMetricService(db)
        service.remove_metric_from_leaderboard(task_id_int, dataset_id_int, metric_name)
        return None

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
