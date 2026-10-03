"""Validated evaluation commands and application without transaction ownership.

Request models carry patch presence. The legacy service's ``*_set`` arguments
for direct and paper edits are produced here; presence is never inferred from truthiness.
"""

from dataclasses import dataclass
from typing import Literal

from backend.models.database import Evaluation as DBEvaluation
from backend.models.evaluations import (
    Evaluation,
    EvaluationCreateRequest,
    EvaluationUpdateRequest,
)
from backend.services.catalog_errors import CatalogNotFoundError, CatalogValidationError
from backend.services.evaluation_service import EvaluationService

CLEARABLE_FIELDS = ("harness", "source_url", "num_parameters", "hf_model_url")


def update_payload(request: EvaluationUpdateRequest) -> dict:
    """Retain the existing audit/service payload, including explicit null flags."""
    return {
        **request.model_dump(),
        **{
            f"{field}_set": field in request.model_fields_set
            for field in CLEARABLE_FIELDS
        },
    }


@dataclass(frozen=True)
class CreateEvaluation:
    payload: EvaluationCreateRequest


@dataclass(frozen=True)
class UpdateEvaluation:
    evaluation_id: int
    payload: EvaluationUpdateRequest


@dataclass(frozen=True)
class DeleteEvaluation:
    evaluation_id: int


EvaluationCommand = CreateEvaluation | UpdateEvaluation | DeleteEvaluation


def evaluation_command(
    operation: Literal["create", "update", "delete"],
    payload: dict,
    evaluation_id: int | None = None,
) -> EvaluationCommand:
    """Adapt trusted application/audit payloads into commands.

    External adapters must validate request models first: client-supplied internal
    flags must not override patch presence. Legacy flags take precedence over
    dumped default nulls so existing audit payloads retain their interpretation.
    """
    if operation == "create":
        return CreateEvaluation(EvaluationCreateRequest.model_validate(payload))
    if evaluation_id is None:
        raise ValueError(f"evaluation_id is required for {operation}")
    if operation == "delete":
        if payload:
            raise ValueError("delete operations do not accept a payload")
        return DeleteEvaluation(evaluation_id)
    if operation != "update":
        raise ValueError(f"Unsupported evaluation operation: {operation}")
    values = dict(payload)
    for field in CLEARABLE_FIELDS:
        present = values.pop(f"{field}_set", None)
        if present is False:
            values.pop(field, None)
    return UpdateEvaluation(
        evaluation_id, EvaluationUpdateRequest.model_validate(values)
    )


def apply_evaluation_command(
    service: EvaluationService,
    command: EvaluationCommand,
    *,
    paper_id: int | None = None,
) -> Evaluation | None:
    """Apply one command, leaving commit and rollback to the application boundary."""
    if isinstance(command, CreateEvaluation):
        if paper_id is not None and command.payload.paper_id != paper_id:
            raise CatalogValidationError(
                "Every batch operation must target the same paper"
            )
        return service.create_evaluation(**command.payload.model_dump(), commit=False)
    if paper_id is not None:
        row = service.db.get(DBEvaluation, command.evaluation_id)
        if row is None or int(row.paper_id) != paper_id:
            raise CatalogNotFoundError(
                f"Evaluation {command.evaluation_id} is not on paper {paper_id}"
            )
    if isinstance(command, UpdateEvaluation):
        return service.update_evaluation(
            evaluation_id=command.evaluation_id,
            **update_payload(command.payload),
            commit=False,
        )
    service.delete_evaluation(command.evaluation_id, commit=False)
    return None
