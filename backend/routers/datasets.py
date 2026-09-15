"""
Datasets API router.

Provides endpoints for accessing benchmark dataset data, including filtering by task,
paper associations, and evaluation data.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.public_api import DatasetTasks, LeaderboardMetrics
from backend.models.evaluations import (
    Dataset,
    DatasetCreateRequest,
    DatasetMetricAddRequest,
    DatasetMetricSetRequest,
    Datasets,
    DatasetUpdateRequest,
)
from backend.services.dataset_service import DatasetService
from backend.services.leaderboard_metric_service import LeaderboardMetricService
from backend.utils.auth import require_catalog_mutator, require_fresh_catalog_mutator

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/", response_model=Datasets)
def list_datasets(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of datasets per page (max 100)"
    ),
    q: Optional[str] = Query(
        None,
        description=(
            "Name-only benchmark search with exact slug/name/full-name identity, "
            "all-token prefixes, full-text relevance, and conservative typo recovery"
        ),
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

    Datasets can be filtered by name or task. `q` searches displayed names only;
    an exact full name remains an identity lookup.
    Supports ordering and pagination.

    **Example queries:**
    - `/api/v1/datasets/` - Get all datasets
    - `/api/v1/datasets/?task=123` - Get datasets for task ID 123
    - `/api/v1/datasets/?q=imagenet` - Search for datasets containing "imagenet"
    - `/api/v1/datasets/?name=COCO` - Filter datasets by name containing "COCO"
    - `/api/v1/datasets/?ordering=-name` - Order by name descending
    """
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

    task_id = service.resolve_task_id(task, case_sensitive_slug=True) if task else None

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
    service = DatasetService(db)
    task_id = service.resolve_task_id(task, case_sensitive_slug=False) if task else None
    return service.get_dataset_by_identifier(
        dataset_id, include_paper=include_paper, task_id=task_id, is_open=is_open
    )


@router.get("/{dataset_id}/tasks/", response_model=DatasetTasks)
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
    tasks = DatasetService(db).list_task_summaries_by_dataset_identifier(dataset_id)
    return {"count": len(tasks), "results": tasks}


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
    dataset_service = DatasetService(db)
    dataset_id_int = dataset_service.require_numeric_dataset_id(dataset_id)

    # Parse ordering
    order_dir = "asc"
    order_by = "created_at"
    if ordering:
        if ordering.startswith("-"):
            order_dir = "desc"
            order_by = ordering[1:]
        else:
            order_by = ordering

    evaluations_response = dataset_service.get_dataset_evaluations(
        page=page,
        page_size=page_size,
        dataset_id=dataset_id_int,
        is_open=is_open,
        order_by=order_by,
        order_dir=order_dir,
    )

    return {
        "count": evaluations_response.count,
        "next_page": evaluations_response.next_page,
        "previous_page": evaluations_response.previous_page,
        "results": [eval.model_dump() for eval in evaluations_response.results],
    }


@router.post(
    "/",
    response_model=Dataset,
    status_code=201,
    dependencies=[Depends(require_catalog_mutator)],
)
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
    return DatasetService(db).create_dataset(request)


@router.put(
    "/{dataset_id}",
    response_model=Dataset,
    dependencies=[Depends(require_catalog_mutator)],
)
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
    return DatasetService(db).update_dataset_by_identifier(dataset_id, request)


# Leaderboard-Metric Management Endpoints (New: task-dataset-metric triples)


@router.get("/{dataset_id}/tasks/{task_id}/metrics", response_model=LeaderboardMetrics)
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
    service = LeaderboardMetricService(db)
    task_id_int, dataset_id_int = service.resolve_leaderboard_identifiers(
        task_id, dataset_id
    )
    return service.get_leaderboard_metrics(task_id_int, dataset_id_int)


@router.post(
    "/{dataset_id}/tasks/{task_id}/metrics",
    response_model=dict,
    status_code=201,
    dependencies=[Depends(require_catalog_mutator)],
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
    service = LeaderboardMetricService(db)
    task_id_int, dataset_id_int = service.resolve_leaderboard_identifiers(
        task_id, dataset_id
    )
    return service.add_metric_to_leaderboard(
        task_id_int, dataset_id_int, request.metric_name
    )


@router.put(
    "/{dataset_id}/tasks/{task_id}/metrics",
    response_model=dict,
    dependencies=[Depends(require_fresh_catalog_mutator)],
)
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
    service = LeaderboardMetricService(db)
    task_id_int, dataset_id_int = service.resolve_leaderboard_identifiers(
        task_id, dataset_id
    )
    return service.set_leaderboard_metrics(
        task_id_int, dataset_id_int, request.metric_names
    )


@router.delete(
    "/{dataset_id}/tasks/{task_id}/metrics/{metric_name}",
    status_code=204,
    dependencies=[Depends(require_fresh_catalog_mutator)],
)
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
    service = LeaderboardMetricService(db)
    task_id_int, dataset_id_int = service.resolve_leaderboard_identifiers(
        task_id, dataset_id
    )
    service.remove_metric_from_leaderboard(task_id_int, dataset_id_int, metric_name)
    return None
