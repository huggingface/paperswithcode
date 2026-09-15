"""Typed payload policy for pending paper edits.

Each edit type has one registry entry describing whether it targets a paper,
how its JSON payload is normalized, and how no-op detection works. This keeps
submission and approval on exactly the same validation path without a central
condition chain.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Any, Callable

from PIL import Image, UnidentifiedImageError

from backend.services.pending_edit_errors import PendingEditError
from backend.utils.public_urls import PublicUrlValidationError, normalize_public_url

Payload = dict[str, Any]
Validator = Callable[[Payload], Payload]
NoopCheck = Callable[[Payload, Payload], bool]

SUGGESTION_IMAGE_MAX_BYTES = 2 * 1024 * 1024
SUGGESTION_IMAGE_FORMATS = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


@dataclass(frozen=True)
class EditSpec:
    validate: Validator
    requires_paper: bool
    is_noop: NoopCheck = lambda _proposed, _current: False


def _public_url(value: Any, message: str) -> str:
    if not isinstance(value, str):
        raise PendingEditError(message)
    try:
        return normalize_public_url(value)
    except PublicUrlValidationError as exc:
        raise PendingEditError(str(exc)) from exc


def _id_list(payload: Payload, *, key: str, label: str) -> Payload:
    values = payload.get(key)
    if not isinstance(values, list) or not all(
        isinstance(value, int) for value in values
    ):
        raise PendingEditError(f'{label} payload must be {{"{key}": [int, ...]}}')
    return {key: list(values)}


def _validate_tasks(payload: Payload) -> Payload:
    return _id_list(payload, key="task_ids", label="Tasks")


def _validate_methods(payload: Payload) -> Payload:
    return _id_list(payload, key="method_ids", label="Methods")


def _validate_url_rows(payload: Payload, *, key: str, label: str) -> Payload:
    rows = payload.get(key)
    if not isinstance(rows, list):
        raise PendingEditError(
            f'{label} payload must be {{"{key}": '
            '[{"url": str, "is_official": bool}, ...]}'
        )
    normalized = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("url"), str)
            or not isinstance(row.get("is_official"), bool)
        ):
            raise PendingEditError(
                f"Each {label.lower().removesuffix('s')} must have a string 'url' "
                "and bool 'is_official'"
            )
        normalized.append(
            {
                "url": _public_url(row["url"], f"{label} URL must be a string"),
                "is_official": row["is_official"],
            }
        )
    return {key: normalized}


def _validate_repositories(payload: Payload) -> Payload:
    return _validate_url_rows(payload, key="repositories", label="Repositories")


def _validate_project_pages(payload: Payload) -> Payload:
    return _validate_url_rows(payload, key="project_pages", label="Project pages")


def _validate_organizations(payload: Payload) -> Payload:
    values = payload.get("organization_ids")
    if not isinstance(values, list) or not all(
        isinstance(value, int) for value in values
    ):
        raise PendingEditError(
            "Organizations payload must be {'organization_ids': [int, ...]}"
        )
    return {"organization_ids": sorted(set(values))}


def _validate_source_url(payload: Payload) -> Payload:
    return {
        "source_url": _public_url(
            payload.get("source_url"), 'Source URL payload must be {"source_url": str}'
        )
    }


def _validate_hf_artifacts(payload: Payload) -> Payload:
    from backend.utils.hf_utils import normalize_hf_artifact_payload

    for key in ("hf_models", "hf_datasets", "hf_spaces"):
        values = payload.get(key)
        if not isinstance(values, list) or not all(
            isinstance(item, str) for item in values
        ):
            raise PendingEditError(
                "HF artifacts payload must be "
                '{"hf_models": [str, ...], "hf_datasets": [str, ...], '
                '"hf_spaces": [str, ...]}'
            )
    try:
        models, datasets, spaces = normalize_hf_artifact_payload(
            list(payload["hf_models"]),
            list(payload["hf_datasets"]),
            list(payload["hf_spaces"]),
        )
    except ValueError as exc:
        raise PendingEditError(str(exc)) from exc
    return {"hf_models": models, "hf_datasets": datasets, "hf_spaces": spaces}


def _optional_text(payload: Payload, output: Payload, field: str, limit: int) -> None:
    value = payload.get(field)
    if value is None:
        return
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise PendingEditError(f"Suggestion '{field}' is invalid")
    if value.strip():
        output[field] = value.strip()


def _optional_id(payload: Payload, output: Payload, field: str) -> None:
    value = payload.get(field)
    if value is None:
        return
    if not isinstance(value, int) or value <= 0:
        raise PendingEditError(f"Suggestion '{field}' must be a positive integer")
    output[field] = value


def _suggestion_base(payload: Payload) -> Payload:
    name = payload.get("name")
    if not isinstance(name, str):
        raise PendingEditError("Suggestion 'name' must be a string")
    name = name.strip()
    if not name:
        raise PendingEditError("Suggestion 'name' must be a non-empty string")
    if len(name) > 200:
        raise PendingEditError("Suggestion 'name' must be at most 200 characters")
    output: Payload = {"name": name}
    _optional_text(payload, output, "description", 2000)
    return output


def _normalize_suggestion_image(image: Any) -> dict[str, str]:
    if not isinstance(image, dict):
        raise PendingEditError("Suggestion 'image' must be an object")
    file_name = image.get("file_name")
    mime_type = image.get("mime_type")
    data_url = image.get("data_url")
    if not isinstance(file_name, str) or not file_name.strip():
        raise PendingEditError("Suggestion image file name must be a non-empty string")
    file_name = file_name.strip()
    if len(file_name) > 255:
        raise PendingEditError(
            "Suggestion image file name must be at most 255 characters"
        )
    if mime_type not in SUGGESTION_IMAGE_FORMATS.values():
        raise PendingEditError("Suggestion image must be a JPEG, PNG, WebP, or GIF")
    if not isinstance(data_url, str):
        raise PendingEditError("Suggestion image data must be a string")
    prefix = f"data:{mime_type};base64,"
    if not data_url.startswith(prefix):
        raise PendingEditError("Suggestion image data does not match its MIME type")
    try:
        content = base64.b64decode(data_url[len(prefix) :], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PendingEditError("Suggestion image data is not valid base64") from exc
    if not content:
        raise PendingEditError("Suggestion image must not be empty")
    if len(content) > SUGGESTION_IMAGE_MAX_BYTES:
        raise PendingEditError("Suggestion image must be 2 MB or smaller")
    try:
        with Image.open(BytesIO(content)) as opened_image:
            detected_mime = SUGGESTION_IMAGE_FORMATS.get(opened_image.format or "")
            opened_image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise PendingEditError(
            "Suggestion image is not a valid supported image"
        ) from exc
    if detected_mime != mime_type:
        raise PendingEditError("Suggestion image data does not match its MIME type")
    return {"file_name": file_name, "mime_type": mime_type, "data_url": data_url}


def _add_image_fields(payload: Payload, output: Payload) -> None:
    if payload.get("image") is not None:
        output["image"] = _normalize_suggestion_image(payload["image"])
    _optional_text(payload, output, "image_credit", 1000)


def _validate_new_task(payload: Payload) -> Payload:
    output = _suggestion_base(payload)
    _add_image_fields(payload, output)
    _optional_id(payload, output, "parent_id")
    _optional_id(payload, output, "area_id")
    _optional_text(payload, output, "keywords", 2000)
    return output


def _validate_new_method(payload: Payload) -> Payload:
    output = _suggestion_base(payload)
    _add_image_fields(payload, output)
    _optional_id(payload, output, "source_paper_id")
    _optional_text(payload, output, "source_url", 500)
    _optional_text(payload, output, "source_title", 500)
    if output.get("source_url"):
        output["source_url"] = _public_url(
            output["source_url"], "Method source URL is invalid"
        )
    if "source_paper_id" not in output and "source_url" not in output:
        raise PendingEditError("Method source_paper_id or source_url is required")
    return output


def _validate_new_benchmark(payload: Payload) -> Payload:
    if "benchmark" in payload or "task" in payload:
        output = {}
        for field in ("benchmark", "task"):
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip():
                raise PendingEditError(
                    f"Benchmark '{field}' must be a non-empty string"
                )
            value = value.strip()
            if len(value) > 200:
                raise PendingEditError(
                    f"Benchmark '{field}' must be at most 200 characters"
                )
            output[field] = value
        _optional_text(payload, output, "description", 2000)
        if "description" not in output:
            raise PendingEditError("Benchmark 'description' is required")
        return output

    # Preserve review compatibility for submissions created before benchmark
    # and task names became free-text administrative fields.
    output = _suggestion_base(payload)
    if "description" not in output:
        raise PendingEditError("Benchmark 'description' is required")
    task_ids = payload.get("task_ids")
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or not all(isinstance(item, int) and item > 0 for item in task_ids)
    ):
        raise PendingEditError("Benchmark 'task_ids' must contain positive integers")
    output["task_ids"] = sorted(set(task_ids))
    for field, limit in (
        ("full_name", 500),
        ("url", 500),
        ("hf_url", 500),
        ("paper_url", 500),
        ("license_name", 255),
        ("license_url", 500),
    ):
        _optional_text(payload, output, field, limit)
    for field in ("url", "hf_url", "paper_url", "license_url"):
        if output.get(field):
            output[field] = _public_url(output[field], f"Benchmark {field} is invalid")
    return output


def _validate_new_metric(payload: Payload) -> Payload:
    output = _suggestion_base(payload)
    if "description" not in output:
        raise PendingEditError("Metric 'description' is required")
    direction = payload.get("direction")
    if direction not in ("higher_is_better", "lower_is_better"):
        raise PendingEditError("Metric 'direction' is required")
    output["direction"] = direction
    _optional_text(payload, output, "full_name", 255)
    _optional_text(payload, output, "scale", 50)
    _optional_id(payload, output, "task_id")
    _optional_id(payload, output, "dataset_id")
    if "task_id" not in output or "dataset_id" not in output:
        raise PendingEditError("Metric leaderboard needs both task_id and dataset_id")
    return output


def _validate_new_conference(payload: Payload) -> Payload:
    output = _suggestion_base(payload)
    for field, limit in (
        ("short_name", 50),
        ("venue", 300),
        ("location", 300),
        ("url", 500),
    ):
        _optional_text(payload, output, field, limit)
    year = payload.get("year")
    if not isinstance(year, int) or not 1900 <= year <= 2200:
        raise PendingEditError("Conference 'year' is required")
    output["year"] = year
    for field in ("start_date", "end_date"):
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise PendingEditError(f"Conference '{field}' must be an ISO date")
        try:
            output[field] = date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise PendingEditError(f"Conference '{field}' must be an ISO date") from exc
    if not output.get("url"):
        raise PendingEditError("Conference source URL is required")
    output["url"] = _public_url(output["url"], "Conference source URL is invalid")
    return output


def _validate_new_external_paper(payload: Payload) -> Payload:
    output: Payload = {
        "source_url": _public_url(
            payload.get("source_url"), "External paper source_url must be a string"
        )
    }
    for field, limit in (("title", 500), ("abstract", 20_000)):
        value = payload.get(field)
        if value is not None:
            if not isinstance(value, str) or len(value.strip()) > limit:
                raise PendingEditError(f"External paper {field} is invalid")
            if value.strip():
                output[field] = value.strip()
    authors = payload.get("authors") or []
    if not isinstance(authors, list) or not all(
        isinstance(author, str) and author.strip() for author in authors
    ):
        raise PendingEditError("External paper authors must be a list of names")
    output["authors"] = [author.strip() for author in authors]
    published = payload.get("date_published")
    if published is not None:
        if not isinstance(published, str):
            raise PendingEditError("External paper date_published must be ISO text")
        try:
            output["date_published"] = date.fromisoformat(published).isoformat()
        except ValueError as exc:
            raise PendingEditError("External paper date_published is invalid") from exc
    return output


def is_valid_evaluation_create_data(data: Payload) -> bool:
    if not isinstance(data.get("task_id"), int) or data["task_id"] <= 0:
        return False
    if not isinstance(data.get("dataset_id"), int) or data["dataset_id"] <= 0:
        return False
    if not isinstance(data.get("best_metric"), str) or not data["best_metric"].strip():
        return False
    metrics = data.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return False
    return all(
        isinstance(name, str)
        and name.strip()
        and value is not None
        and (not isinstance(value, str) or bool(value.strip()))
        for name, value in metrics.items()
    )


def _normalize_evaluation_urls(data: Payload) -> Payload:
    output = dict(data)
    for field in ("external_source_url", "source_url", "hf_model_url"):
        if output.get(field) is not None:
            try:
                output[field] = normalize_public_url(output[field])
            except (PublicUrlValidationError, TypeError) as exc:
                raise PendingEditError(str(exc)) from exc
    return output


def _validate_evaluations(payload: Payload) -> Payload:
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise PendingEditError(
            "Evaluations payload must be "
            '{"operations": [{"op": ..., ...}, ...]} with at least one operation'
        )
    output = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise PendingEditError("Each evaluation operation must be an object")
        kind = operation.get("op")
        if kind not in {"create", "update", "delete"}:
            raise PendingEditError(
                "Evaluation op must be one of: 'create', 'update', 'delete'"
            )
        if kind == "create":
            data = operation.get("data")
            if not isinstance(data, dict):
                raise PendingEditError("Evaluation create op needs a 'data' object")
            if is_valid_evaluation_create_data(data):
                output.append(
                    {"op": "create", "data": _normalize_evaluation_urls(data)}
                )
        elif kind == "update":
            evaluation_id = operation.get("evaluation_id")
            data = operation.get("data")
            if not isinstance(evaluation_id, int) or not isinstance(data, dict):
                raise PendingEditError(
                    "Evaluation update op needs int 'evaluation_id' and 'data' object"
                )
            output.append(
                {
                    "op": "update",
                    "evaluation_id": evaluation_id,
                    "data": _normalize_evaluation_urls(data),
                }
            )
        else:
            evaluation_id = operation.get("evaluation_id")
            if not isinstance(evaluation_id, int):
                raise PendingEditError("Evaluation delete op needs int 'evaluation_id'")
            output.append({"op": "delete", "evaluation_id": evaluation_id})
    if not output:
        raise PendingEditError(
            "Evaluations payload must include at least one valid operation"
        )
    return {"operations": output}


def _ids_noop(proposed_key: str, current_key: str) -> NoopCheck:
    return lambda proposed, current: (
        set(proposed.get(proposed_key, []))
        == {int(item["id"]) for item in current.get(current_key, [])}
    )


def _url_rows_noop(key: str) -> NoopCheck:
    def compare(proposed: Payload, current: Payload) -> bool:
        def normalize(rows: list[dict[str, Any]]) -> set[tuple[str, bool]]:
            return {(item["url"].strip(), bool(item["is_official"])) for item in rows}

        return normalize(proposed.get(key, [])) == normalize(current.get(key, []))

    return compare


def _hf_artifacts_noop(proposed: Payload, current: Payload) -> bool:
    return all(
        sorted(proposed.get(key) or []) == sorted(current.get(key) or [])
        for key in ("hf_models", "hf_datasets", "hf_spaces")
    )


EDIT_SPECS: dict[str, EditSpec] = {
    "tasks": EditSpec(_validate_tasks, True, _ids_noop("task_ids", "tasks")),
    "methods": EditSpec(_validate_methods, True, _ids_noop("method_ids", "methods")),
    "repositories": EditSpec(
        _validate_repositories, True, _url_rows_noop("repositories")
    ),
    "project_pages": EditSpec(
        _validate_project_pages, True, _url_rows_noop("project_pages")
    ),
    "organizations": EditSpec(
        _validate_organizations, True, _ids_noop("organization_ids", "organizations")
    ),
    "source_url": EditSpec(
        _validate_source_url,
        True,
        lambda proposed, current: (
            (proposed.get("source_url") or "").strip()
            == (current.get("source_url") or "").strip()
        ),
    ),
    "hf_artifacts": EditSpec(_validate_hf_artifacts, True, _hf_artifacts_noop),
    "evaluations": EditSpec(_validate_evaluations, True),
    "new_task": EditSpec(_validate_new_task, False),
    "new_method": EditSpec(_validate_new_method, False),
    "new_benchmark": EditSpec(_validate_new_benchmark, False),
    "new_metric": EditSpec(_validate_new_metric, False),
    "new_conference": EditSpec(_validate_new_conference, False),
    "new_external_paper": EditSpec(_validate_new_external_paper, False),
}
EDIT_TYPES = frozenset(EDIT_SPECS)


def edit_spec(edit_type: str) -> EditSpec:
    try:
        return EDIT_SPECS[edit_type]
    except KeyError:
        raise PendingEditError(f"Unsupported edit_type: {edit_type}") from None


def validate_payload(edit_type: str, payload: Any) -> Payload:
    if not isinstance(payload, dict):
        raise PendingEditError("proposed_payload must be a JSON object")
    return edit_spec(edit_type).validate(payload)


def payload_is_noop(edit_type: str, proposed: Payload, current: Payload) -> bool:
    return edit_spec(edit_type).is_noop(proposed, current)
