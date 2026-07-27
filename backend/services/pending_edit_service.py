"""
Service for non-admin paper edit submissions.

Backs the `/api/v1/me/paper-edits` (user submit) and `/api/v1/admin/paper-edits`
(admin list / approve / reject) endpoints. Edit application is delegated to the
existing mutation services (``PaperService`` and ``EvaluationService``) so admin
direct edits and approved submissions go through the same code path.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, UnidentifiedImageError
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.models.database import (
    Author as DBAuthor,
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    PaperAuthor,
    PaperMethod,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    PendingPaperEdit,
    ProjectPage as DBProjectPage,
    Repository as DBRepository,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


EDIT_TYPES = frozenset(
    {
        "tasks",
        "methods",
        "evaluations",
        "repositories",
        "project_pages",
        "source_url",
        "hf_artifacts",
        "new_task",
        "new_method",
        "new_benchmark",
        "new_metric",
        "new_conference",
    }
)
STATUSES = frozenset({"pending", "approved", "rejected"})
SUGGESTION_IMAGE_MAX_BYTES = 2 * 1024 * 1024
SUGGESTION_IMAGE_FORMATS = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class PendingEditError(Exception):
    """Raised for validation problems with pending edit submissions or reviews."""


class PendingEditNotFoundError(PendingEditError):
    """Raised when a pending edit row cannot be found."""


class PendingEditAlreadyReviewedError(PendingEditError):
    """Raised when an admin tries to approve or reject a non-pending row."""


class PendingEditService:
    """Submission and review of non-admin paper edits."""

    def __init__(self, db: Session):
        self.db = db

    # ----------------------------------------------------------------
    # Author resolution
    # ----------------------------------------------------------------

    def is_linked_author(self, paper_id: int, hf_username: str) -> bool:
        """
        Return True if ``hf_username`` matches a linked author of the paper.

        Uses the canonical ``papers`` -> ``paper_authors`` -> ``authors`` chain
        and a case-insensitive comparison on ``authors.hf_username``. Returns
        False for empty usernames or papers with no linked authors.
        """

        if not hf_username:
            return False

        normalized = hf_username.strip().lower()
        if not normalized:
            return False

        match = (
            self.db.query(PaperAuthor.paper_id)
            .join(DBAuthor, PaperAuthor.author_id == DBAuthor.id)
            .filter(
                PaperAuthor.paper_id == paper_id,
                DBAuthor.hf_username.isnot(None),
                # `LOWER(authors.hf_username) = :normalized` is portable; the
                # column is `String(255)` so this remains cheap even without
                # a functional index.
                DBAuthor.hf_username.ilike(normalized),
            )
            .first()
        )
        return match is not None

    # ----------------------------------------------------------------
    # Snapshot helpers (current_payload at submit time)
    # ----------------------------------------------------------------

    def _snapshot_tasks(self, paper_id: int) -> Dict[str, Any]:
        from backend.models.database import Task as DBTask

        rows = (
            self.db.query(DBTask.id, DBTask.name, DBTask.slug)
            .join(PaperTask, PaperTask.task_id == DBTask.id)
            .filter(PaperTask.paper_id == paper_id)
            .order_by(DBTask.name)
            .all()
        )
        return {
            "tasks": [{"id": row[0], "name": row[1], "slug": row[2]} for row in rows]
        }

    def _snapshot_methods(self, paper_id: int) -> Dict[str, Any]:
        from backend.models.database import Method as DBMethod

        rows = (
            self.db.query(DBMethod.id, DBMethod.name, DBMethod.slug)
            .join(PaperMethod, PaperMethod.method_id == DBMethod.id)
            .filter(PaperMethod.paper_id == paper_id)
            .order_by(DBMethod.name)
            .all()
        )
        return {
            "methods": [{"id": row[0], "name": row[1], "slug": row[2]} for row in rows]
        }

    def _snapshot_repositories(self, paper_id: int) -> Dict[str, Any]:
        rows = (
            self.db.query(DBRepository.url, PaperRepository.is_official)
            .join(PaperRepository, PaperRepository.repository_id == DBRepository.id)
            .filter(PaperRepository.paper_id == paper_id)
            .order_by(desc(PaperRepository.is_official), DBRepository.url)
            .all()
        )
        return {
            "repositories": [
                {"url": row[0], "is_official": bool(row[1])} for row in rows
            ]
        }

    def _snapshot_project_pages(self, paper_id: int) -> Dict[str, Any]:
        rows = (
            self.db.query(DBProjectPage.url, DBProjectPage.is_official)
            .join(
                PaperProjectPage,
                PaperProjectPage.project_page_id == DBProjectPage.id,
            )
            .filter(PaperProjectPage.paper_id == paper_id)
            .order_by(DBProjectPage.url)
            .all()
        )
        return {
            "project_pages": [
                {"url": row[0], "is_official": bool(row[1])} for row in rows
            ]
        }

    def _snapshot_source_url(self, paper_id: int) -> Dict[str, Any]:
        row = (
            self.db.query(DBPaper.source, DBPaper.source_url)
            .filter(DBPaper.id == paper_id)
            .first()
        )
        if row is None:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")
        return {"source_url": row[1], "source": row[0]}

    def _snapshot_evaluations(self, paper_id: int) -> Dict[str, Any]:
        rows = (
            self.db.query(DBEvaluation)
            .filter(DBEvaluation.paper_id == paper_id)
            .order_by(DBEvaluation.id)
            .all()
        )
        return {
            "evaluations": [
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "dataset_id": row.dataset_id,
                    "model_name": row.model_name,
                    "harness": row.harness,
                    "methodology": row.methodology,
                    "metrics": row.metrics,
                    "uses_additional_data": row.uses_additional_data,
                    "is_open": row.is_open,
                    "best_rank": row.best_rank,
                    "best_metric": row.best_metric,
                    "evaluated_on": row.evaluated_on.isoformat()
                    if row.evaluated_on
                    else None,
                    "external_source_url": row.external_source_url,
                    "num_parameters": row.num_parameters,
                    "hf_model_url": row.hf_model_url,
                }
                for row in rows
            ]
        }

    def _snapshot_hf_artifacts(self, paper_id: int) -> Dict[str, Any]:
        row = (
            self.db.query(
                DBPaper.hf_models,
                DBPaper.hf_datasets,
                DBPaper.hf_spaces,
            )
            .filter(DBPaper.id == paper_id)
            .first()
        )
        if row is None:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")
        return {
            "hf_models": list(row[0] or []),
            "hf_datasets": list(row[1] or []),
            "hf_spaces": list(row[2] or []),
        }

    def _build_snapshot(self, paper_id: int, edit_type: str) -> Dict[str, Any]:
        if edit_type == "tasks":
            return self._snapshot_tasks(paper_id)
        if edit_type == "methods":
            return self._snapshot_methods(paper_id)
        if edit_type == "repositories":
            return self._snapshot_repositories(paper_id)
        if edit_type == "project_pages":
            return self._snapshot_project_pages(paper_id)
        if edit_type == "evaluations":
            return self._snapshot_evaluations(paper_id)
        if edit_type == "source_url":
            return self._snapshot_source_url(paper_id)
        if edit_type == "hf_artifacts":
            return self._snapshot_hf_artifacts(paper_id)
        if edit_type in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
        ):
            # Suggestions for brand-new taxonomy entries have no existing live
            # state to diff against.
            return {}
        raise PendingEditError(f"Unsupported edit_type: {edit_type}")

    # ----------------------------------------------------------------
    # Payload validation
    # ----------------------------------------------------------------

    @staticmethod
    def _normalize_suggestion_image(image: Any) -> Dict[str, str]:
        if not isinstance(image, dict):
            raise PendingEditError("Suggestion 'image' must be an object")

        file_name = image.get("file_name")
        mime_type = image.get("mime_type")
        data_url = image.get("data_url")
        if not isinstance(file_name, str) or not file_name.strip():
            raise PendingEditError(
                "Suggestion image file name must be a non-empty string"
            )
        normalized_file_name = file_name.strip()
        if len(normalized_file_name) > 255:
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

        return {
            "file_name": normalized_file_name,
            "mime_type": mime_type,
            "data_url": data_url,
        }

    @staticmethod
    def _is_valid_evaluation_create_data(data: Dict[str, Any]) -> bool:
        task_id = data.get("task_id")
        dataset_id = data.get("dataset_id")
        if not isinstance(task_id, int) or task_id <= 0:
            return False
        if not isinstance(dataset_id, int) or dataset_id <= 0:
            return False

        best_metric = data.get("best_metric")
        if not isinstance(best_metric, str) or not best_metric.strip():
            return False

        metrics = data.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            return False
        for name, value in metrics.items():
            if not isinstance(name, str) or not name.strip():
                return False
            if value is None:
                return False
            if isinstance(value, str) and not value.strip():
                return False
        return True

    @staticmethod
    def _validate_payload(edit_type: str, payload: Any) -> Dict[str, Any]:
        """Shape-check ``proposed_payload`` for the given ``edit_type``.

        Raises ``PendingEditError`` with a user-readable message if the shape
        is wrong. Approval will re-validate against the underlying mutation
        services (which already do their own validation), so this method only
        rejects payloads that the approval step would not understand at all.
        """

        if not isinstance(payload, dict):
            raise PendingEditError("proposed_payload must be a JSON object")

        if edit_type == "tasks":
            task_ids = payload.get("task_ids")
            if not isinstance(task_ids, list) or not all(
                isinstance(t, int) for t in task_ids
            ):
                raise PendingEditError('Tasks payload must be {"task_ids": [int, ...]}')
            return {"task_ids": list(task_ids)}

        if edit_type == "methods":
            method_ids = payload.get("method_ids")
            if not isinstance(method_ids, list) or not all(
                isinstance(m, int) for m in method_ids
            ):
                raise PendingEditError(
                    'Methods payload must be {"method_ids": [int, ...]}'
                )
            return {"method_ids": list(method_ids)}

        if edit_type == "repositories":
            repos = payload.get("repositories")
            if not isinstance(repos, list):
                raise PendingEditError(
                    "Repositories payload must be "
                    '{"repositories": [{"url": str, "is_official": bool}, ...]}'
                )
            out: List[Dict[str, Any]] = []
            for repo in repos:
                if (
                    not isinstance(repo, dict)
                    or not isinstance(repo.get("url"), str)
                    or not isinstance(repo.get("is_official"), bool)
                ):
                    raise PendingEditError(
                        "Each repository must have a string 'url' and bool 'is_official'"
                    )
                out.append({"url": repo["url"], "is_official": repo["is_official"]})
            return {"repositories": out}

        if edit_type == "project_pages":
            pages = payload.get("project_pages")
            if not isinstance(pages, list):
                raise PendingEditError(
                    "Project pages payload must be "
                    '{"project_pages": [{"url": str, "is_official": bool}, ...]}'
                )
            out = []
            for page in pages:
                if (
                    not isinstance(page, dict)
                    or not isinstance(page.get("url"), str)
                    or not isinstance(page.get("is_official"), bool)
                ):
                    raise PendingEditError(
                        "Each project page must have a string 'url' and bool 'is_official'"
                    )
                out.append({"url": page["url"], "is_official": page["is_official"]})
            return {"project_pages": out}

        if edit_type == "source_url":
            source_url = payload.get("source_url")
            if not isinstance(source_url, str):
                raise PendingEditError('Source URL payload must be {"source_url": str}')
            normalized = source_url.strip()
            if not normalized:
                raise PendingEditError("source_url must be a non-empty string")
            if len(normalized) > 2000:
                raise PendingEditError("source_url must be at most 2000 characters")
            if not (
                normalized.startswith("http://") or normalized.startswith("https://")
            ):
                raise PendingEditError("source_url must start with http:// or https://")
            return {"source_url": normalized}

        if edit_type == "hf_artifacts":
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
                    list(payload.get("hf_models", [])),
                    list(payload.get("hf_datasets", [])),
                    list(payload.get("hf_spaces", [])),
                )
            except ValueError as exc:
                raise PendingEditError(str(exc)) from exc
            return {
                "hf_models": models,
                "hf_datasets": datasets,
                "hf_spaces": spaces,
            }

        if edit_type in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
        ):
            name = payload.get("name")
            description = payload.get("description")
            if not isinstance(name, str):
                raise PendingEditError("Suggestion 'name' must be a string")
            normalized_name = name.strip()
            if not normalized_name:
                raise PendingEditError("Suggestion 'name' must be a non-empty string")
            if len(normalized_name) > 200:
                raise PendingEditError(
                    "Suggestion 'name' must be at most 200 characters"
                )

            if edit_type == "new_conference":
                normalized_payload = {"name": normalized_name}
                optional_limits = {
                    "description": 2000,
                    "dates": 200,
                    "venue": 300,
                    "url": 500,
                }
                for field, max_length in optional_limits.items():
                    value = payload.get(field)
                    if value is None:
                        continue
                    if not isinstance(value, str):
                        raise PendingEditError(f"Suggestion '{field}' must be a string")
                    normalized_value = value.strip()
                    if not normalized_value:
                        continue
                    if len(normalized_value) > max_length:
                        raise PendingEditError(
                            f"Suggestion '{field}' must be at most "
                            f"{max_length} characters"
                        )
                    normalized_payload[field] = normalized_value
                url = normalized_payload.get("url")
                if url and not (
                    url.startswith("http://") or url.startswith("https://")
                ):
                    raise PendingEditError(
                        "Suggestion 'url' must start with http:// or https://"
                    )
                return normalized_payload

            normalized_payload = {"name": normalized_name}
            if description is not None:
                if not isinstance(description, str):
                    raise PendingEditError("Suggestion 'description' must be a string")
                normalized_description = description.strip()
                if normalized_description:
                    if len(normalized_description) > 2000:
                        raise PendingEditError(
                            "Suggestion 'description' must be at most 2000 characters"
                        )
                    normalized_payload["description"] = normalized_description

            if edit_type in ("new_benchmark", "new_metric"):
                if "description" not in normalized_payload:
                    raise PendingEditError(
                        "Suggestion 'description' must be a non-empty string"
                    )
                return normalized_payload

            image = payload.get("image")
            if image is not None:
                normalized_payload["image"] = (
                    PendingEditService._normalize_suggestion_image(image)
                )

            image_credit = payload.get("image_credit")
            if image_credit is not None:
                if not isinstance(image_credit, str):
                    raise PendingEditError("Suggestion 'image_credit' must be a string")
                normalized_image_credit = image_credit.strip()
                if normalized_image_credit:
                    if len(normalized_image_credit) > 1000:
                        raise PendingEditError(
                            "Suggestion 'image_credit' must be at most 1000 characters"
                        )
                    normalized_payload["image_credit"] = normalized_image_credit

            if edit_type == "new_method":
                source = payload.get("source")
                if source is not None:
                    if not isinstance(source, str):
                        raise PendingEditError("Suggestion 'source' must be a string")
                    normalized_source = source.strip()
                    if normalized_source:
                        if len(normalized_source) > 1000:
                            raise PendingEditError(
                                "Suggestion 'source' must be at most 1000 characters"
                            )
                        normalized_payload["source"] = normalized_source

            return normalized_payload

        if edit_type == "evaluations":
            operations = payload.get("operations")
            if not isinstance(operations, list) or not operations:
                raise PendingEditError(
                    "Evaluations payload must be "
                    '{"operations": [{"op": ..., ...}, ...]} with at least one operation'
                )
            out_ops: List[Dict[str, Any]] = []
            for op in operations:
                if not isinstance(op, dict):
                    raise PendingEditError(
                        "Each evaluation operation must be an object"
                    )
                kind = op.get("op")
                if kind not in {"create", "update", "delete"}:
                    raise PendingEditError(
                        "Evaluation op must be one of: 'create', 'update', 'delete'"
                    )
                if kind == "create":
                    data = op.get("data")
                    if not isinstance(data, dict):
                        raise PendingEditError(
                            "Evaluation create op needs a 'data' object"
                        )
                    if not PendingEditService._is_valid_evaluation_create_data(data):
                        continue
                    out_ops.append({"op": "create", "data": data})
                elif kind == "update":
                    evaluation_id = op.get("evaluation_id")
                    data = op.get("data")
                    if not isinstance(evaluation_id, int) or not isinstance(data, dict):
                        raise PendingEditError(
                            "Evaluation update op needs int 'evaluation_id' and 'data' object"
                        )
                    out_ops.append(
                        {"op": "update", "evaluation_id": evaluation_id, "data": data}
                    )
                else:  # delete
                    evaluation_id = op.get("evaluation_id")
                    if not isinstance(evaluation_id, int):
                        raise PendingEditError(
                            "Evaluation delete op needs int 'evaluation_id'"
                        )
                    out_ops.append({"op": "delete", "evaluation_id": evaluation_id})
            if not out_ops:
                raise PendingEditError(
                    "Evaluations payload must include at least one valid operation"
                )
            return {"operations": out_ops}

        raise PendingEditError(f"Unsupported edit_type: {edit_type}")

    # ----------------------------------------------------------------
    # No-op detection
    # ----------------------------------------------------------------

    @staticmethod
    def _is_noop(
        edit_type: str,
        normalized_payload: Dict[str, Any],
        current_payload: Dict[str, Any],
    ) -> bool:
        """Return True when the normalized payload matches the current state.

        Prevents submissions that would not change anything from creating
        review rows on the submissions dashboard. Evaluation operations are
        already required to be non-empty by ``_validate_payload``; we don't
        replay them here because that would duplicate the approval logic.
        """

        if edit_type == "tasks":
            current_ids = {int(item["id"]) for item in current_payload.get("tasks", [])}
            proposed_ids = set(normalized_payload.get("task_ids", []))
            return current_ids == proposed_ids

        if edit_type == "methods":
            current_ids = {
                int(item["id"]) for item in current_payload.get("methods", [])
            }
            proposed_ids = set(normalized_payload.get("method_ids", []))
            return current_ids == proposed_ids

        if edit_type == "repositories":
            current = {
                (item["url"].strip(), bool(item["is_official"]))
                for item in current_payload.get("repositories", [])
            }
            proposed = {
                (item["url"].strip(), bool(item["is_official"]))
                for item in normalized_payload.get("repositories", [])
            }
            return current == proposed

        if edit_type == "project_pages":
            current = {
                (item["url"].strip(), bool(item["is_official"]))
                for item in current_payload.get("project_pages", [])
            }
            proposed = {
                (item["url"].strip(), bool(item["is_official"]))
                for item in normalized_payload.get("project_pages", [])
            }
            return current == proposed

        if edit_type == "source_url":
            current = (current_payload.get("source_url") or "").strip()
            proposed = (normalized_payload.get("source_url") or "").strip()
            return current == proposed

        if edit_type == "hf_artifacts":
            for key in ("hf_models", "hf_datasets", "hf_spaces"):
                current = sorted(current_payload.get(key) or [])
                proposed = sorted(normalized_payload.get(key) or [])
                if current != proposed:
                    return False
            return True

        if edit_type in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
        ):
            # Suggestions for new taxonomy entries are never a no-op; there is
            # no existing entry to compare against.
            return False

        # `evaluations` already requires at least one operation; treat any
        # well-formed operation list as a real change for now.
        return False

    # ----------------------------------------------------------------
    # Submission
    # ----------------------------------------------------------------

    def submit(
        self,
        *,
        paper_id: Optional[int],
        hf_username: str,
        edit_type: str,
        proposed_payload: Any,
    ) -> PendingPaperEdit:
        if edit_type not in EDIT_TYPES:
            raise PendingEditError(
                f"Unsupported edit_type: {edit_type}. Allowed: {sorted(EDIT_TYPES)}"
            )

        is_taxonomy_suggestion = edit_type in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
        )
        if paper_id is None and not is_taxonomy_suggestion:
            raise PendingEditError(
                "paper_id is required unless submitting a taxonomy suggestion"
            )
        if paper_id is not None:
            paper_exists = (
                self.db.query(DBPaper.id).filter(DBPaper.id == paper_id).first()
            )
            if not paper_exists:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

        normalized_payload = self._validate_payload(edit_type, proposed_payload)
        current_payload = (
            {} if paper_id is None else self._build_snapshot(paper_id, edit_type)
        )

        if self._is_noop(edit_type, normalized_payload, current_payload):
            raise PendingEditError("Submission does not contain any changes.")

        is_author = (
            self.is_linked_author(paper_id, hf_username)
            if paper_id is not None
            else False
        )

        row = PendingPaperEdit(
            paper_id=paper_id,
            hf_username=hf_username,
            is_author=is_author,
            edit_type=edit_type,
            proposed_payload=normalized_payload,
            current_payload=current_payload,
            status="pending",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    # ----------------------------------------------------------------
    # Listing
    # ----------------------------------------------------------------

    def list_edits(
        self,
        *,
        status: Optional[str] = None,
        edit_type: Optional[str] = None,
        paper_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[PendingPaperEdit], int]:
        if status is not None and status not in STATUSES:
            raise PendingEditError(
                f"Unsupported status: {status}. Allowed: {sorted(STATUSES)}"
            )
        if edit_type is not None and edit_type not in EDIT_TYPES:
            raise PendingEditError(
                f"Unsupported edit_type: {edit_type}. Allowed: {sorted(EDIT_TYPES)}"
            )

        query = self.db.query(PendingPaperEdit)
        if status:
            query = query.filter(PendingPaperEdit.status == status)
        if edit_type:
            query = query.filter(PendingPaperEdit.edit_type == edit_type)
        if paper_id is not None:
            query = query.filter(PendingPaperEdit.paper_id == paper_id)

        total = query.count()

        rows = (
            query.order_by(desc(PendingPaperEdit.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return rows, total

    def get(self, edit_id: int) -> PendingPaperEdit:
        row = (
            self.db.query(PendingPaperEdit)
            .filter(PendingPaperEdit.id == edit_id)
            .first()
        )
        if not row:
            raise PendingEditNotFoundError(f"Pending edit with ID {edit_id} not found")
        return row

    # ----------------------------------------------------------------
    # Approval / rejection
    # ----------------------------------------------------------------

    def approve(
        self,
        *,
        edit_id: int,
        reviewer_username: Optional[str],
        admin_note: Optional[str] = None,
    ) -> PendingPaperEdit:
        row = self.get(edit_id)
        if row.status != "pending":
            raise PendingEditAlreadyReviewedError(
                f"Pending edit {edit_id} is already {row.status}"
            )

        if row.paper_id is None and row.edit_type not in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
        ):
            raise PendingEditError("This edit is missing its paper_id")
        self._apply_payload(row.edit_type, row.paper_id, row.proposed_payload)

        row.status = "approved"
        row.reviewed_by = reviewer_username
        row.admin_note = admin_note
        row.reviewed_at = datetime.now(timezone.utc)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def reject(
        self,
        *,
        edit_id: int,
        reviewer_username: Optional[str],
        admin_note: Optional[str] = None,
    ) -> PendingPaperEdit:
        row = self.get(edit_id)
        if row.status != "pending":
            raise PendingEditAlreadyReviewedError(
                f"Pending edit {edit_id} is already {row.status}"
            )

        row.status = "rejected"
        row.reviewed_by = reviewer_username
        row.admin_note = admin_note
        row.reviewed_at = datetime.now(timezone.utc)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    # ----------------------------------------------------------------
    # Apply proposed payload through existing mutation services
    # ----------------------------------------------------------------

    def _apply_payload(
        self, edit_type: str, paper_id: Optional[int], payload: Dict[str, Any]
    ) -> None:
        if edit_type in (
            "new_task",
            "new_method",
            "new_benchmark",
            "new_metric",
            "new_conference",
        ):
            # Taxonomy suggestions are informational. Approving simply marks the
            # row reviewed; an admin creates the actual entry (task, method,
            # benchmark, metric, or conference) by hand.
            return
        if paper_id is None:
            raise PendingEditError("This edit is missing its paper_id")
        if edit_type == "tasks":
            PaperService(self.db).update_paper_tasks(
                paper_id, list(payload.get("task_ids", []))
            )
            return
        if edit_type == "methods":
            PaperService(self.db).update_paper_methods(
                paper_id, list(payload.get("method_ids", []))
            )
            return
        if edit_type == "repositories":
            PaperService(self.db).update_paper_repositories(
                paper_id, list(payload.get("repositories", []))
            )
            return
        if edit_type == "project_pages":
            PaperService(self.db).update_paper_project_pages(
                paper_id, list(payload.get("project_pages", []))
            )
            return
        if edit_type == "source_url":
            PaperService(self.db).update_paper_source_url(
                paper_id, str(payload.get("source_url", ""))
            )
            return
        if edit_type == "hf_artifacts":
            PaperService(self.db).update_paper_hf_artifacts(
                paper_id,
                list(payload.get("hf_models", [])),
                list(payload.get("hf_datasets", [])),
                list(payload.get("hf_spaces", [])),
            )
            return
        if edit_type == "evaluations":
            self._apply_evaluations(paper_id, payload)
            return
        raise PendingEditError(f"Unsupported edit_type: {edit_type}")

    def _apply_evaluations(self, paper_id: int, payload: Dict[str, Any]) -> None:
        operations: List[Dict[str, Any]] = payload.get("operations", [])
        service = EvaluationService(self.db)

        for op in operations:
            kind = op.get("op")
            if kind == "delete":
                evaluation_id = int(op["evaluation_id"])
                self._ensure_evaluation_paper_match(evaluation_id, paper_id)
                service.delete_evaluation(evaluation_id)
                continue

            if kind == "update":
                evaluation_id = int(op["evaluation_id"])
                self._ensure_evaluation_paper_match(evaluation_id, paper_id)
                data = dict(op["data"])
                # Honor "field was explicitly set in the source dialog" semantics
                # the same way the EvaluationUpdateRequest handler does, so
                # clearing harness/num_parameters still works after approval.
                harness_set = "harness" in data
                source_url_set = "source_url" in data
                num_parameters_set = "num_parameters" in data
                hf_model_url_set = "hf_model_url" in data
                service.update_evaluation(
                    evaluation_id=evaluation_id,
                    task_id=data.get("task_id"),
                    dataset_id=data.get("dataset_id"),
                    model_name=data.get("model_name"),
                    harness=data.get("harness"),
                    methodology=data.get("methodology"),
                    metrics=data.get("metrics"),
                    uses_additional_data=data.get("uses_additional_data"),
                    is_open=data.get("is_open"),
                    best_rank=data.get("best_rank"),
                    best_metric=data.get("best_metric"),
                    evaluated_on=data.get("evaluated_on"),
                    external_source_url=data.get("external_source_url"),
                    source_url=data.get("source_url"),
                    num_parameters=data.get("num_parameters"),
                    hf_model_url=data.get("hf_model_url"),
                    harness_set=harness_set,
                    source_url_set=source_url_set,
                    num_parameters_set=num_parameters_set,
                    hf_model_url_set=hf_model_url_set,
                )
                continue

            if kind == "create":
                data = dict(op["data"])
                if not PendingEditService._is_valid_evaluation_create_data(data):
                    continue
                # Force the create to target the paper this edit was submitted
                # against; submitters cannot reroute the row to another paper
                # at approval time.
                data["paper_id"] = paper_id
                service.create_evaluation(
                    paper_id=paper_id,
                    task_id=data["task_id"],
                    dataset_id=data["dataset_id"],
                    metrics=data.get("metrics") or {},
                    model_name=data.get("model_name"),
                    harness=data.get("harness"),
                    methodology=data.get("methodology"),
                    uses_additional_data=bool(data.get("uses_additional_data", False)),
                    is_open=bool(data.get("is_open", True)),
                    best_rank=data.get("best_rank"),
                    best_metric=data.get("best_metric"),
                    evaluated_on=data.get("evaluated_on"),
                    external_source_url=data.get("external_source_url"),
                    source_url=data.get("source_url"),
                    num_parameters=data.get("num_parameters"),
                    hf_model_url=data.get("hf_model_url"),
                )
                continue

            raise PendingEditError(f"Unsupported evaluation op: {kind}")

    def _ensure_evaluation_paper_match(
        self, evaluation_id: int, expected_paper_id: int
    ) -> None:
        row = (
            self.db.query(DBEvaluation.paper_id)
            .filter(DBEvaluation.id == evaluation_id)
            .first()
        )
        if row is None:
            raise DatabaseError(f"Evaluation {evaluation_id} not found")
        if int(row[0]) != int(expected_paper_id):
            raise PendingEditError(
                f"Evaluation {evaluation_id} does not belong to paper {expected_paper_id}"
            )
