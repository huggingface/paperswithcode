"""
Evaluations API router.

Provides endpoints for accessing benchmark evaluation data, including filtering by paper,
task, and dataset.
"""

import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, ValidationError

from backend.models.evaluations import (
    Evaluation,
    Evaluations,
    EvaluationCreateRequest,
    EvaluationUpdateRequest,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.evaluation_curation_service import EvaluationCurationService
from backend.database.connection import get_database_session
from backend.utils.auth import (
    evaluation_mutation_context,
    require_admin,
    require_paper_mutator,
)
from backend.utils.exceptions import DatabaseError

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
logger = logging.getLogger(__name__)


class EvaluationBatchOperation(BaseModel):
    operation: Literal["create", "update", "delete"]
    evaluation_id: Optional[int] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EvaluationBatchRequest(BaseModel):
    paper_id: int
    operations: list[EvaluationBatchOperation] = Field(min_length=1)


@router.post("/batch")
def batch_evaluations(
    request: EvaluationBatchRequest,
    mutation: dict = Depends(evaluation_mutation_context),
    db: Session = Depends(get_database_session),
):
    actor = mutation["actor"]
    if actor["role"] == "contributor" and any(
        operation.operation == "delete" for operation in request.operations
    ):
        issued_at = actor.get("session_iat")
        if (
            not isinstance(issued_at, (int, float))
            or datetime.now(timezone.utc).timestamp() - issued_at > 15 * 60
        ):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "fresh_auth_required",
                    "message": "Sign in again before deleting catalog data",
                },
            )
    try:
        operations: list[dict] = []
        for operation in request.operations:
            if operation.operation == "create":
                payload = EvaluationCreateRequest.model_validate(
                    operation.payload
                ).model_dump()
            elif operation.operation == "update":
                if operation.evaluation_id is None:
                    raise ValueError("evaluation_id is required for update")
                model = EvaluationUpdateRequest.model_validate(operation.payload)
                payload = {
                    **model.model_dump(),
                    "harness_set": "harness" in model.model_fields_set,
                    "source_url_set": "source_url" in model.model_fields_set,
                    "num_parameters_set": "num_parameters" in model.model_fields_set,
                    "hf_model_url_set": "hf_model_url" in model.model_fields_set,
                }
            else:
                if operation.evaluation_id is None:
                    raise ValueError("evaluation_id is required for delete")
                if operation.payload:
                    raise ValueError("delete operations do not accept a payload")
                payload = {}
            operations.append(
                {
                    "operation": operation.operation,
                    "evaluation_id": operation.evaluation_id,
                    "payload": payload,
                }
            )
        return EvaluationCurationService(db).batch(
            paper_id=request.paper_id,
            operations=operations,
            mutation=mutation,
        )
    except (ValueError, ValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/curation-state")
def evaluation_collection_state(
    paper_id: int,
    _actor: dict = Depends(require_paper_mutator),
    db: Session = Depends(get_database_session),
):
    return EvaluationCurationService(db).collection_state(paper_id)


@router.get("/{evaluation_id}/curation-state")
def evaluation_curation_state(
    evaluation_id: int,
    _actor: dict = Depends(require_paper_mutator),
    db: Session = Depends(get_database_session),
):
    return EvaluationCurationService(db).state(evaluation_id)


@router.get("/", response_model=Evaluations)
def list_evaluations(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of evaluations per page (max 100)"
    ),
    q: Optional[str] = Query(
        None, description="Search query for model name and methodology"
    ),
    paper_id: Optional[int] = Query(None, description="Filter by paper ID"),
    task_id: Optional[int] = Query(None, description="Filter by task ID"),
    include_descendants: bool = Query(
        False,
        description=(
            "When `task_id` is set, also include evaluations whose task is a "
            "descendant of `task_id`. Useful for parent task pages that want "
            "to roll up evaluations from their subtasks."
        ),
    ),
    dataset_id: Optional[int] = Query(None, description="Filter by dataset ID"),
    best_metric: Optional[str] = Query(
        None, description="Filter by best metric (e.g., 'AbsRel', 'delta1')"
    ),
    is_open: Optional[bool] = Query(
        None,
        description=(
            "Filter by open-source status of the evaluated model. "
            "Pass `true` to return only open-source rows (hides closed-source)."
        ),
    ),
    external: Optional[bool] = Query(
        None,
        description="Filter by external source attribution status.",
    ),
    max_parameters_exclusive: Optional[int] = Query(
        None,
        gt=0,
        description=(
            "Return leaderboard entries with a known, consistent total parameter "
            "count strictly below this bound."
        ),
    ),
    ordering: Optional[str] = Query(
        None,
        description=(
            "Order by field: created_at, best_rank, evaluated_on, "
            "benchmark_popularity (prefix with '-' for descending). "
            "When omitted for a dataset-scoped query, defaults to best_rank "
            "so benchmark leaderboards surface the rank-1 row first. "
            "benchmark_popularity sorts each row by the total number of "
            "evaluations on its dataset across all papers, which keeps rows "
            "for the most popular benchmarks together at the top."
        ),
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of benchmark evaluations.

    Evaluations can be filtered by paper, task, dataset, or searched across model name and methodology.
    Supports ordering and pagination.

    **Example queries:**
    - `/api/v1/evaluations/` - Get all evaluations
    - `/api/v1/evaluations/?paper_id=123` - Get evaluations for paper ID 123
    - `/api/v1/evaluations/?task_id=2&dataset_id=1` - Get evaluations for task 2 on dataset 1
    - `/api/v1/evaluations/?q=DETR` - Search for evaluations containing "DETR"
    - `/api/v1/evaluations/?ordering=-best_rank` - Order by best rank descending
    - `/api/v1/evaluations/?paper_id=123&ordering=-benchmark_popularity` -
      Paper page rows grouped by most popular benchmark first
    """
    return EvaluationService(db).list_catalog_evaluations(
        page=page,
        page_size=page_size,
        search=q,
        paper_id=paper_id,
        task_id=task_id,
        include_descendants=include_descendants,
        dataset_id=dataset_id,
        best_metric=best_metric,
        is_open=is_open,
        external=external,
        max_parameters_exclusive=max_parameters_exclusive,
        ordering=ordering,
    )


@router.get("/{evaluation_id}", response_model=Evaluation)
def get_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_database_session),
):
    """
    Get a specific evaluation by ID.

    **Example:**
    - `/api/v1/evaluations/1` - Get evaluation with ID 1
    """
    return EvaluationService(db).get_catalog_evaluation(evaluation_id)


@router.post(
    "/",
    response_model=Evaluation,
    status_code=201,
)
def create_evaluation(
    request: EvaluationCreateRequest,
    mutation: dict = Depends(evaluation_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Create a new evaluation.

    Creates a new benchmark evaluation result for a paper on a specific task and dataset.

    **Metric Validation:**
    - All metrics in the `metrics` dictionary must be allowed for the specified leaderboard (task + dataset)
    - The `best_metric` must also be in the allowed metrics list
    - Use `GET /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics` to see allowed metrics for a leaderboard
    - Leaderboards are defined by (task, dataset, metric) triples in the `task_dataset_metrics` table

    **Request Body:**
    ```json
    {
        "paper_id": 123,
        "task_id": 1,
        "dataset_id": 5,
        "model_name": "DETR",
        "metrics": {"AP": "44.9", "AP50": "64.7"},
        "best_rank": 1,
        "best_metric": "AP"
    }
    ```

    **Returns:**
    - 201: Created evaluation object with ID
    - 400: Invalid metrics for the dataset (see error message for allowed metrics)
    - 500: Internal server error
    """
    return EvaluationCurationService(db).create(
        payload=request.model_dump(), mutation=mutation
    )


@router.put(
    "/{evaluation_id}",
    response_model=Evaluation,
)
def update_evaluation(
    evaluation_id: int,
    request: EvaluationUpdateRequest,
    mutation: dict = Depends(evaluation_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Update an existing evaluation.

    Updates the fields of an existing evaluation. Only provided fields will be updated.

    **Metric Validation:**
    - If updating `metrics`, `task_id`, or `dataset_id`, all metrics must be allowed for the leaderboard
    - If updating `best_metric`, it must be in the allowed metrics list
    - Use `GET /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics` to see allowed metrics for a leaderboard

    **Example:**
    ```
    PUT /api/v1/evaluations/123
    {
        "model_name": "DETR-R50",
        "metrics": {"AP": "45.2", "AP50": "65.1"},
        "best_rank": 2
    }
    ```

    **Returns:**
    - 200: Updated evaluation object
    - 400: Invalid metrics for the dataset
    - 404: Evaluation not found
    - 500: Internal server error
    """
    return EvaluationCurationService(db).update(
        evaluation_id=evaluation_id,
        payload={
            **request.model_dump(),
            "harness_set": "harness" in request.model_fields_set,
            "source_url_set": "source_url" in request.model_fields_set,
            "num_parameters_set": "num_parameters" in request.model_fields_set,
            "hf_model_url_set": "hf_model_url" in request.model_fields_set,
        },
        mutation=mutation,
    )


@router.delete(
    "/{evaluation_id}",
    status_code=204,
)
def delete_evaluation(
    evaluation_id: int,
    mutation: dict = Depends(evaluation_mutation_context),
    db: Session = Depends(get_database_session),
):
    """
    Delete an evaluation.

    Permanently deletes an evaluation by ID.

    **Example:**
    - `/api/v1/evaluations/123` - Delete evaluation with ID 123

    **Returns:**
    - 204 No Content on success
    """
    EvaluationCurationService(db).delete(evaluation_id=evaluation_id, mutation=mutation)
    return None


@router.post(
    "/recalculate-ranks",
    status_code=200,
    dependencies=[Depends(require_admin)],
)
def recalculate_ranks(
    task_id: int = Query(..., description="Task ID for the leaderboard"),
    dataset_id: int = Query(..., description="Dataset ID for the leaderboard"),
    uses_additional_data: Optional[bool] = Query(
        None,
        description="If specified, only recalculate for evaluations with this value",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Recalculate ranks for all evaluations in a specific leaderboard.

    This endpoint recalculates the best_rank field for all evaluations matching the
    specified task_id and dataset_id. Rankings are based on the best_metric value,
    with higher values receiving better (lower) ranks.

    **Example:**
    - `POST /api/v1/evaluations/recalculate-ranks?task_id=2&dataset_id=5` - Recalculate ranks for task 2 on dataset 5

    **Returns:**
    - JSON object with the number of evaluations updated
    """
    try:
        service = EvaluationService(db)
        updated_count = service.recalculate_ranks(
            task_id=task_id,
            dataset_id=dataset_id,
            uses_additional_data=uses_additional_data,
        )
        return {
            "message": f"Successfully recalculated ranks for {updated_count} evaluations",
            "task_id": task_id,
            "dataset_id": dataset_id,
            "updated_count": updated_count,
        }

    except DatabaseError:
        logger.exception("Failed to recalculate evaluation ranks")
        raise HTTPException(status_code=500, detail="Internal server error") from None
