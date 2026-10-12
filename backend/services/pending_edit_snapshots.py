"""Canonical snapshots for pending edits and submission-created entities."""

from __future__ import annotations

import base64
from datetime import date, datetime
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.models.database import (
    Conference,
    Dataset,
    Evaluation,
    Method,
    Metric,
    Organization,
    Paper,
    PaperAuthor,
    PaperConference,
    PaperMethod,
    PaperOrganization,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    PaperXThread,
    ProjectPage,
    Repository,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.evaluation_curation_service import EvaluationCurationService
from backend.services.paper_curation_service import PaperCurationService
from backend.services.pending_edit_errors import PendingEditError
from backend.utils.exceptions import PaperNotFoundError

CREATED_ENTITY_MODELS = {
    "paper": Paper,
    "task": Task,
    "method": Method,
    "dataset": Dataset,
    "metric": Metric,
    "conference": Conference,
}


class PendingEditSnapshotService:
    """Own every snapshot used by submission conflict and rollback flows."""

    def __init__(self, db: Session):
        self.db = db

    def paper_edit(self, paper_id: int, edit_type: str) -> dict[str, Any]:
        builders = {
            "tasks": self._tasks,
            "methods": self._methods,
            "repositories": self._repositories,
            "project_pages": self._project_pages,
            "organizations": self._organizations,
            "evaluations": self._evaluations,
            "source_url": self._source_url,
            "hf_artifacts": self._hf_artifacts,
            "x_threads": self._x_threads,
        }
        builder = builders.get(edit_type)
        if builder is not None:
            return builder(paper_id)
        if edit_type.startswith("new_"):
            return {}
        raise PendingEditError(f"Unsupported edit_type: {edit_type}")

    def approval_event(
        self,
        edit_type: str,
        paper_id: int | None,
        *,
        result_type: str | None = None,
        result_id: str | None = None,
    ) -> Any:
        if edit_type.startswith("new_"):
            if result_type is None or result_id is None:
                return {}
            return self.created_entity(result_type, int(result_id))
        if paper_id is not None:
            if edit_type == "evaluations":
                return EvaluationCurationService(self.db).paper_evaluations(paper_id)
            return PaperCurationService(self.db).snapshot(paper_id, edit_type)
        if result_type is None or result_id is None:
            return {}
        return self.created_entity(result_type, int(result_id))

    def created_entity(self, entity_type: str, entity_id: int) -> dict[str, Any]:
        try:
            model = CREATED_ENTITY_MODELS[entity_type]
        except KeyError:
            raise PendingEditError(
                f"Unsupported created entity type: {entity_type}"
            ) from None
        entity = self.db.get(model, entity_id)
        if entity is None:
            return {}
        values: dict[str, Any] = {}
        for column in model.__table__.columns:
            value = getattr(entity, column.name)
            if isinstance(value, bytes):
                value = {"base64": base64.b64encode(value).decode()}
            elif isinstance(value, (datetime, date)):
                value = value.isoformat()
            values[column.name] = value
        snapshot: dict[str, Any] = {"entity": values}
        self._add_created_associations(snapshot, entity_type, entity_id)
        return snapshot

    def _tasks(self, paper_id: int) -> dict[str, Any]:
        rows = (
            self.db.query(Task.id, Task.name, Task.slug)
            .join(PaperTask, PaperTask.task_id == Task.id)
            .filter(PaperTask.paper_id == paper_id)
            .order_by(Task.name)
            .all()
        )
        return {
            "tasks": [{"id": row[0], "name": row[1], "slug": row[2]} for row in rows]
        }

    def _methods(self, paper_id: int) -> dict[str, Any]:
        rows = (
            self.db.query(Method.id, Method.name, Method.slug)
            .join(PaperMethod, PaperMethod.method_id == Method.id)
            .filter(PaperMethod.paper_id == paper_id)
            .order_by(Method.name)
            .all()
        )
        return {
            "methods": [{"id": row[0], "name": row[1], "slug": row[2]} for row in rows]
        }

    def _repositories(self, paper_id: int) -> dict[str, Any]:
        rows = (
            self.db.query(Repository.url, PaperRepository.is_official)
            .join(PaperRepository, PaperRepository.repository_id == Repository.id)
            .filter(PaperRepository.paper_id == paper_id)
            .order_by(desc(PaperRepository.is_official), Repository.url)
            .all()
        )
        return {
            "repositories": [
                {"url": row[0], "is_official": bool(row[1])} for row in rows
            ]
        }

    def _project_pages(self, paper_id: int) -> dict[str, Any]:
        rows = (
            self.db.query(ProjectPage.url, ProjectPage.is_official)
            .join(PaperProjectPage, PaperProjectPage.project_page_id == ProjectPage.id)
            .filter(PaperProjectPage.paper_id == paper_id)
            .order_by(ProjectPage.url)
            .all()
        )
        return {
            "project_pages": [
                {"url": row[0], "is_official": bool(row[1])} for row in rows
            ]
        }

    def _x_threads(self, paper_id: int) -> dict[str, Any]:
        rows = (
            self.db.query(PaperXThread.url)
            .filter(PaperXThread.paper_id == paper_id)
            .order_by(PaperXThread.position)
            .all()
        )
        return {"x_threads": [{"url": row[0]} for row in rows]}

    def _organizations(self, paper_id: int) -> dict[str, Any]:
        rows = (
            self.db.query(Organization.id, Organization.name, Organization.slug)
            .join(
                PaperOrganization, PaperOrganization.organization_id == Organization.id
            )
            .filter(PaperOrganization.paper_id == paper_id)
            .order_by(Organization.name)
            .all()
        )
        return {
            "organizations": [
                {"id": row[0], "name": row[1], "slug": row[2]} for row in rows
            ]
        }

    def _source_url(self, paper_id: int) -> dict[str, Any]:
        row = (
            self.db.query(Paper.source, Paper.source_url)
            .filter(Paper.id == paper_id)
            .first()
        )
        if row is None:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")
        return {"source_url": row[1], "source": row[0]}

    def _evaluations(self, paper_id: int) -> dict[str, Any]:
        rows = (
            self.db.query(Evaluation)
            .filter(Evaluation.paper_id == paper_id)
            .order_by(Evaluation.id)
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

    def _hf_artifacts(self, paper_id: int) -> dict[str, Any]:
        row = (
            self.db.query(Paper.hf_models, Paper.hf_datasets, Paper.hf_spaces)
            .filter(Paper.id == paper_id)
            .first()
        )
        if row is None:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")
        return {
            "hf_models": list(row[0] or []),
            "hf_datasets": list(row[1] or []),
            "hf_spaces": list(row[2] or []),
        }

    def _add_created_associations(
        self, snapshot: dict[str, Any], entity_type: str, entity_id: int
    ) -> None:
        if entity_type == "paper":
            snapshot["associations"] = {
                "author_ids": self._ids(
                    PaperAuthor.author_id, PaperAuthor.paper_id, entity_id
                ),
                "task_ids": self._ids(PaperTask.task_id, PaperTask.paper_id, entity_id),
                "method_ids": self._ids(
                    PaperMethod.method_id, PaperMethod.paper_id, entity_id
                ),
                "organization_ids": self._ids(
                    PaperOrganization.organization_id,
                    PaperOrganization.paper_id,
                    entity_id,
                ),
                "repository_ids": self._ids(
                    PaperRepository.repository_id, PaperRepository.paper_id, entity_id
                ),
                "project_page_ids": self._ids(
                    PaperProjectPage.project_page_id,
                    PaperProjectPage.paper_id,
                    entity_id,
                ),
                "conference_ids": self._ids(
                    PaperConference.conference_id, PaperConference.paper_id, entity_id
                ),
                "evaluation_ids": self._ids(
                    Evaluation.id, Evaluation.paper_id, entity_id
                ),
            }
        elif entity_type == "task":
            snapshot["associations"] = {
                "child_ids": self._ids(Task.id, Task.parent_id, entity_id),
                "paper_ids": self._ids(
                    PaperTask.paper_id, PaperTask.task_id, entity_id
                ),
                "dataset_ids": self._ids(
                    TaskDataset.dataset_id, TaskDataset.task_id, entity_id
                ),
                "evaluation_ids": self._ids(
                    Evaluation.id, Evaluation.task_id, entity_id
                ),
            }
        elif entity_type == "method":
            snapshot["paper_ids"] = self._ids(
                PaperMethod.paper_id, PaperMethod.method_id, entity_id
            )
        elif entity_type == "dataset":
            snapshot["task_ids"] = self._ids(
                TaskDataset.task_id, TaskDataset.dataset_id, entity_id
            )
            snapshot["evaluation_ids"] = self._ids(
                Evaluation.id, Evaluation.dataset_id, entity_id
            )
            snapshot["leaderboards"] = [
                {"task_id": row.task_id, "metric_id": row.metric_id}
                for row in self.db.query(TaskDatasetMetric)
                .filter(TaskDatasetMetric.dataset_id == entity_id)
                .all()
            ]
        elif entity_type == "metric":
            snapshot["leaderboards"] = [
                {"task_id": row.task_id, "dataset_id": row.dataset_id}
                for row in self.db.query(TaskDatasetMetric)
                .filter(TaskDatasetMetric.metric_id == entity_id)
                .all()
            ]
        elif entity_type == "conference":
            snapshot["paper_ids"] = self._ids(
                PaperConference.paper_id, PaperConference.conference_id, entity_id
            )

    def _ids(self, selected, foreign_key, entity_id: int) -> list[int]:
        return sorted(
            row[0]
            for row in self.db.query(selected).filter(foreign_key == entity_id).all()
        )
