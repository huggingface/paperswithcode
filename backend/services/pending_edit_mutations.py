"""Application of normalized pending-edit payloads through canonical services."""

from __future__ import annotations

import base64
from datetime import date
from typing import Any, Callable

from sqlalchemy.orm import Session

from backend.models.api import DatasetCreateRequest, TaskCreateRequest
from backend.models.database import (
    Dataset,
    Evaluation,
    Method,
    Metric,
    Paper,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.conference_service import ConferenceService
from backend.services.autonomous_capabilities import (
    AUTONOMOUS_PENDING_EDIT_CAPABILITIES,
    HUMAN_ONLY_EDIT_TYPES,
    AutonomousCapabilityDenied,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_operations_repository import RunContext
from backend.services.autonomous_policy import AutonomousPolicy
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.method_service import MethodService
from backend.services.metric_service import MetricService
from backend.services.paper_association_service import PaperAssociationService
from backend.services.paper_service import PaperService
from backend.services.pending_edit_errors import PendingEditError
from backend.services.pending_edit_payloads import (
    Payload,
    is_valid_evaluation_create_data,
)
from backend.services.task_service import TaskService
from backend.utils.exceptions import DatabaseError

Mutation = Callable[[int | None, Payload], tuple[str, str]]


class PendingEditMutationService:
    """Dispatch normalized payloads without mixing mutation logic into review flow."""

    def __init__(
        self, db: Session, *, autonomous_policy: AutonomousPolicy | None = None
    ):
        self.db = db
        self.autonomous_policy = autonomous_policy or AutonomousPolicy()
        paper_service = PaperService(db)
        self.paper_associations = PaperAssociationService(
            db, paper_service.get_paper_by_id
        )
        self._handlers: dict[str, Mutation] = {
            "new_external_paper": self._new_external_paper,
            "new_task": self._new_task,
            "new_method": self._new_method,
            "new_benchmark": self._new_benchmark,
            "new_metric": self._new_metric,
            "new_conference": self._new_conference,
            "tasks": self._paper_tasks,
            "methods": self._paper_methods,
            "repositories": self._paper_repositories,
            "project_pages": self._paper_project_pages,
            "source_url": self._paper_source_url,
            "hf_artifacts": self._paper_hf_artifacts,
            "evaluations": self._paper_evaluations,
        }

    def apply_human_review(
        self,
        edit_type: str,
        paper_id: int | None,
        payload: Payload,
        *,
        actor_hf_subject: str | None = None,
        actor_username: str | None = None,
    ) -> tuple[str, str]:
        """Human-review entry point; autonomous callers have no public dispatcher."""
        return self._dispatch(
            edit_type,
            paper_id,
            payload,
            actor_hf_subject=actor_hf_subject,
            actor_username=actor_username,
        )

    def apply_autonomous(
        self,
        *,
        context: RunContext,
        edit_type: str,
        paper_id: int | None,
        payload: Payload,
    ) -> tuple[str, str]:
        """Apply only the closed, server-resolved autonomous edit surface."""
        if edit_type in HUMAN_ONLY_EDIT_TYPES:
            raise AutonomousCapabilityDenied("human_only_resource")
        capability = AUTONOMOUS_PENDING_EDIT_CAPABILITIES.get(edit_type)
        if capability is None:
            raise AutonomousCapabilityDenied("capability_not_in_manifest")
        resources = self._autonomous_resources(edit_type, paper_id, payload)
        for resource in resources:
            decision = self.autonomous_policy.authorize(
                self.db, context, capability, resource
            )
            if not decision.allowed:
                raise AutonomousCapabilityDenied(decision.reason_code)
        return self._dispatch(edit_type, paper_id, payload)

    def _dispatch(
        self,
        edit_type: str,
        paper_id: int | None,
        payload: Payload,
        *,
        actor_hf_subject: str | None = None,
        actor_username: str | None = None,
    ) -> tuple[str, str]:
        if edit_type == "organizations":
            return self._paper_organizations(
                paper_id,
                payload,
                actor_hf_subject=actor_hf_subject,
                actor_username=actor_username,
            )
        try:
            handler = self._handlers[edit_type]
        except KeyError:
            raise PendingEditError(f"Unsupported edit_type: {edit_type}") from None
        return handler(paper_id, payload)

    def _autonomous_resources(
        self, edit_type: str, paper_id: int | None, payload: Payload
    ) -> list[ResourceRef]:
        if edit_type == "new_external_paper":
            return [
                ResourceRef(
                    ResourceKind.EXTERNAL_PAPER,
                    "new",
                    False,
                )
            ]
        resources = [self._resolved_resource(Paper, ResourceKind.PAPER, paper_id)]
        if edit_type == "tasks":
            resources.extend(
                self._resolved_resource(Task, ResourceKind.TASK, value)
                for value in payload["task_ids"]
            )
        elif edit_type == "methods":
            resources.extend(
                self._resolved_resource(Method, ResourceKind.METHOD, value)
                for value in payload["method_ids"]
            )
        elif edit_type == "evaluations":
            resources.extend(self._evaluation_resources(payload))
        return resources

    def _resolved_resource(
        self, model: type, kind: ResourceKind, identifier: int | None
    ) -> ResourceRef:
        value = "missing" if identifier is None else str(identifier)
        return ResourceRef(
            kind,
            value,
            identifier is not None and self.db.get(model, identifier) is not None,
        )

    def _evaluation_resources(self, payload: Payload) -> list[ResourceRef]:
        resources: list[ResourceRef] = []
        for operation in payload["operations"]:
            if operation["op"] == "delete":
                resources.append(
                    self._resolved_resource(
                        Evaluation,
                        ResourceKind.EVALUATION,
                        int(operation["evaluation_id"]),
                    )
                )
                continue
            data = operation.get("data") or {}
            existing = None
            if operation["op"] == "update":
                existing = self.db.get(Evaluation, int(operation["evaluation_id"]))
                resources.append(
                    ResourceRef(
                        ResourceKind.EVALUATION,
                        str(operation["evaluation_id"]),
                        existing is not None,
                    )
                )
            task_id = data.get("task_id") or getattr(existing, "task_id", None)
            dataset_id = data.get("dataset_id") or getattr(existing, "dataset_id", None)
            if task_id is not None:
                resources.append(
                    self._resolved_resource(Task, ResourceKind.TASK, task_id)
                )
            if dataset_id is not None:
                resources.append(
                    ResourceRef(
                        ResourceKind.BENCHMARK,
                        str(dataset_id),
                        self.db.get(Dataset, dataset_id) is not None
                        and task_id is not None
                        and self.db.get(TaskDataset, (task_id, dataset_id)) is not None,
                    )
                )
            metric_names = set((data.get("metrics") or {}).keys())
            if data.get("best_metric"):
                metric_names.add(data["best_metric"])
            if task_id is not None and dataset_id is not None and metric_names:
                configured = {
                    metric.name: metric
                    for metric in self.db.query(Metric)
                    .join(TaskDatasetMetric, TaskDatasetMetric.metric_id == Metric.id)
                    .filter(
                        TaskDatasetMetric.task_id == task_id,
                        TaskDatasetMetric.dataset_id == dataset_id,
                    )
                    .all()
                }
                resources.extend(
                    ResourceRef(
                        ResourceKind.METRIC,
                        str(configured[name].id)
                        if name in configured
                        else "unconfigured",
                        name in configured,
                    )
                    for name in metric_names
                )
        return resources

    @staticmethod
    def _require_paper(paper_id: int | None) -> int:
        if paper_id is None:
            raise PendingEditError("This edit is missing its paper_id")
        return paper_id

    @staticmethod
    def _decode_image(image: Any) -> tuple[bytes | None, str | None]:
        if not image:
            return None, None
        prefix = f"data:{image['mime_type']};base64,"
        return base64.b64decode(image["data_url"][len(prefix) :]), image["mime_type"]

    def _new_external_paper(
        self, _paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        title = payload.get("title")
        published = payload.get("date_published")
        if not title or not published:
            raise PendingEditError(
                "External-paper approval requires source_url, title, and date_published"
            )
        result = ExternalResourceService(self.db).add_external_resource(
            ExternalResourceInput(
                source_url=payload["source_url"],
                title=title,
                abstract=payload.get("abstract"),
                authors=list(payload.get("authors") or []),
                date_published=date.fromisoformat(published),
            ),
            commit=False,
        )
        return "paper", str(result.paper.id)

    def _new_task(self, _paper_id: int | None, payload: Payload) -> tuple[str, str]:
        created = TaskService(self.db).create_task(
            TaskCreateRequest(
                name=payload["name"],
                description=payload.get("description"),
                keywords=payload.get("keywords"),
                parent_id=payload.get("parent_id"),
                area_id=payload.get("area_id"),
                image_credit=payload.get("image_credit"),
            ),
            commit=False,
        )
        entity = self.db.get(Task, int(created.id))
        assert entity is not None
        entity.image_data, entity.image_mime_type = self._decode_image(
            payload.get("image")
        )
        self.db.flush()
        return "task", str(entity.id)

    def _new_method(self, _paper_id: int | None, payload: Payload) -> tuple[str, str]:
        source_paper_id = payload.get("source_paper_id")
        if source_paper_id and self.db.get(Paper, source_paper_id) is None:
            raise PendingEditError(f"Source paper {source_paper_id} does not exist")
        image_data, image_mime = self._decode_image(payload.get("image"))
        entity = MethodService(self.db).create_method(
            commit=False,
            name=payload["name"],
            description=payload.get("description"),
            source_paper_id=source_paper_id,
            source_url=payload.get("source_url"),
            source_title=payload.get("source_title"),
            image_data=image_data,
            image_mime_type=image_mime,
            image_credit=payload.get("image_credit"),
        )
        return "method", str(entity.id)

    def _new_benchmark(
        self, _paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        task_ids = payload["task_ids"]
        created = DatasetService(self.db).create_dataset(
            DatasetCreateRequest(
                name=payload["name"],
                full_name=payload.get("full_name"),
                description=payload["description"],
                url=payload.get("url"),
                hf_url=payload.get("hf_url"),
                paper_url=payload.get("paper_url"),
                license_name=payload.get("license_name"),
                license_url=payload.get("license_url"),
                task_ids=task_ids,
            ),
            commit=False,
        )
        entity = self.db.get(Dataset, int(created.id))
        assert entity is not None
        for task_id in task_ids:
            self.db.add(TaskDataset(task_id=task_id, dataset_id=entity.id))
        self.db.flush()
        return "dataset", str(entity.id)

    def _new_metric(self, _paper_id: int | None, payload: Payload) -> tuple[str, str]:
        entity = MetricService(self.db).create_metric(
            commit=False,
            name=payload["name"],
            full_name=payload.get("full_name"),
            direction=payload["direction"],
            scale=payload.get("scale"),
            description=payload["description"],
        )
        task_id = payload["task_id"]
        dataset_id = payload["dataset_id"]
        if self.db.get(TaskDataset, (task_id, dataset_id)) is None:
            raise PendingEditError(
                "The requested task/benchmark association does not exist"
            )
        self.db.add(
            TaskDatasetMetric(
                task_id=task_id, dataset_id=dataset_id, metric_id=entity.id
            )
        )
        self.db.flush()
        return "metric", str(entity.id)

    def _new_conference(
        self, _paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        entity = ConferenceService(self.db).create_conference(
            commit=False,
            name=payload["name"],
            short_name=payload.get("short_name"),
            year=payload["year"],
            url=payload["url"],
            start_date=date.fromisoformat(payload["start_date"])
            if payload.get("start_date")
            else None,
            end_date=date.fromisoformat(payload["end_date"])
            if payload.get("end_date")
            else None,
            venue=payload.get("venue"),
            location=payload.get("location"),
            description=payload.get("description"),
        )
        return "conference", str(entity.id)

    def _paper_tasks(self, paper_id: int | None, payload: Payload) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        self.paper_associations.update_tasks(
            paper_id, list(payload["task_ids"]), commit=False
        )
        return "paper", str(paper_id)

    def _paper_methods(self, paper_id: int | None, payload: Payload) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        self.paper_associations.update_methods(
            paper_id, list(payload["method_ids"]), commit=False
        )
        return "paper", str(paper_id)

    def _paper_repositories(
        self, paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        self.paper_associations.update_repositories(
            paper_id, list(payload["repositories"]), commit=False
        )
        return "paper", str(paper_id)

    def _paper_project_pages(
        self, paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        self.paper_associations.update_project_pages(
            paper_id, list(payload["project_pages"]), commit=False
        )
        return "paper", str(paper_id)

    def _paper_organizations(
        self,
        paper_id: int | None,
        payload: Payload,
        *,
        actor_hf_subject: str | None,
        actor_username: str | None,
    ) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        self.paper_associations.update_organizations(
            paper_id,
            list(payload["organization_ids"]),
            manual_added_by_hf_subject=actor_hf_subject,
            manual_added_by_hf_username=actor_username,
            commit=False,
        )
        return "paper", str(paper_id)

    def _paper_source_url(
        self, paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        self.paper_associations.update_source_url(
            paper_id, payload["source_url"], commit=False
        )
        return "paper", str(paper_id)

    def _paper_hf_artifacts(
        self, paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        self.paper_associations.update_hf_artifacts(
            paper_id,
            list(payload["hf_models"]),
            list(payload["hf_datasets"]),
            list(payload["hf_spaces"]),
            commit=False,
        )
        return "paper", str(paper_id)

    def _paper_evaluations(
        self, paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        service = EvaluationService(self.db)
        for operation in payload["operations"]:
            kind = operation["op"]
            if kind == "delete":
                evaluation_id = int(operation["evaluation_id"])
                self._ensure_evaluation_paper(evaluation_id, paper_id)
                service.delete_evaluation(evaluation_id, commit=False)
            elif kind == "update":
                evaluation_id = int(operation["evaluation_id"])
                self._ensure_evaluation_paper(evaluation_id, paper_id)
                data = dict(operation["data"])
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
                    harness_set="harness" in data,
                    source_url_set="source_url" in data,
                    num_parameters_set="num_parameters" in data,
                    hf_model_url_set="hf_model_url" in data,
                    commit=False,
                )
            elif kind == "create":
                data = dict(operation["data"])
                if not is_valid_evaluation_create_data(data):
                    continue
                service.create_evaluation(
                    paper_id=paper_id,
                    task_id=data["task_id"],
                    dataset_id=data["dataset_id"],
                    metrics=data["metrics"],
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
                    commit=False,
                )
            else:
                raise PendingEditError(f"Unsupported evaluation op: {kind}")
        return "paper", str(paper_id)

    def _ensure_evaluation_paper(self, evaluation_id: int, paper_id: int) -> None:
        row = (
            self.db.query(Evaluation.paper_id)
            .filter(Evaluation.id == evaluation_id)
            .first()
        )
        if row is None:
            raise DatabaseError(f"Evaluation {evaluation_id} not found")
        if int(row[0]) != paper_id:
            raise PendingEditError(
                f"Evaluation {evaluation_id} does not belong to paper {paper_id}"
            )
