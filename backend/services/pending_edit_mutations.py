"""Application of normalized pending-edit payloads through canonical services."""

from __future__ import annotations

import base64
import hashlib
import logging
from datetime import date
from typing import Any, Callable

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.taxonomy import TaskCreateRequest
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import (
    Dataset,
    Evaluation,
    Method,
    Metric,
    Organization,
    Paper,
    PaperOrganization,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.conference_service import ConferenceService
from backend.services.curation_organization_service import CurationOrganizationService
from backend.services.hf_organization_service import (
    HFOrganizationError,
    HFOrganizationProfile,
)
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
    organization_slug,
    validate_payload,
)
from backend.services.task_service import TaskService
from backend.services.catalog_errors import CatalogNotFoundError, CatalogValidationError
from backend.services.evaluation_commands import (
    apply_evaluation_command,
    evaluation_command,
    validate_evaluation_scope,
)

logger = logging.getLogger(__name__)

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
            "x_threads": self._paper_x_threads,
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
        if edit_type == "new_organization":
            return self._new_organization(
                paper_id,
                payload,
                actor_hf_subject=actor_hf_subject,
                actor_username=actor_username,
            )
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

    def unresolved_evaluation_resources(self, payload: Payload) -> list[str]:
        """Evaluation targets that are missing or not configured for the benchmark."""
        return [
            f"{resource.kind.value} {resource.identifier}"
            for resource in self._evaluation_resources(payload)
            if not resource.exists
        ]

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

    @staticmethod
    def _hf_organization_profile(
        curation: CurationOrganizationService, hf_slug: str | None
    ) -> HFOrganizationProfile | None:
        """Hugging Face profile for a suggestion; None when absent or unreachable."""
        if not hf_slug:
            return None
        try:
            return curation.hf_client.fetch_profile(hf_slug)
        except (HFOrganizationError, httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "organization_suggestion_profile_failed hf_slug=%s error=%s",
                hf_slug,
                exc,
            )
            return None

    def _new_organization(
        self,
        paper_id: int | None,
        payload: Payload,
        *,
        actor_hf_subject: str | None,
        actor_username: str | None,
    ) -> tuple[str, str]:
        slug = organization_slug(payload)
        hf_slug = payload.get("hf_slug")
        website_url = payload.get("website_url")
        curation = CurationOrganizationService(self.db)
        try:
            profile = self._hf_organization_profile(curation, hf_slug)
            if profile is not None:
                hf_slug = profile.hf_slug
                # The profile's website and avatar replace submitted ones below.
                if profile.website_url:
                    website_url = None
            duplicate = Organization.slug == slug
            if hf_slug:
                duplicate = duplicate | (
                    func.lower(Organization.hf_slug) == hf_slug.lower()
                )
            existing = self.db.query(Organization.slug).filter(duplicate).first()
            if existing is not None:
                raise PendingEditError(
                    f"Organization already exists as /organizations/{existing.slug}"
                )
            logo_data, logo_mime_type = self._decode_image(payload.get("image"))
            entity = Organization(
                name=payload["name"],
                slug=slug,
                hf_slug=hf_slug,
                hf_url=f"https://huggingface.co/{hf_slug}" if hf_slug else None,
                website_url=website_url,
                description=payload.get("description"),
                logo_data=logo_data,
                logo_mime_type=logo_mime_type,
                logo_sha256=(
                    hashlib.sha256(logo_data).hexdigest() if logo_data else None
                ),
            )
            if profile is not None:
                curation.apply_profile(entity, profile)
        finally:
            curation.close()
        self.db.add(entity)
        self.db.flush()
        if paper_id is not None:
            # Suggestions made from a paper page also tag that paper.
            current_ids = [
                row[0]
                for row in self.db.query(PaperOrganization.organization_id).filter(
                    PaperOrganization.paper_id == paper_id
                )
            ]
            self.paper_associations.update_organizations(
                paper_id,
                [*current_ids, entity.id],
                manual_added_by_hf_subject=actor_hf_subject,
                manual_added_by_hf_username=actor_username,
                commit=False,
            )
        return "organization", str(entity.id)

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

    def _paper_x_threads(
        self, paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        self.paper_associations.update_x_threads(
            paper_id, list(payload["x_threads"]), commit=False
        )
        return "paper", str(paper_id)

    def _paper_evaluations(
        self, paper_id: int | None, payload: Payload
    ) -> tuple[str, str]:
        paper_id = self._require_paper(paper_id)
        # Revalidate stored proposals before the first write, including proposals
        # persisted before canonical command validation was introduced.
        normalized = validate_payload("evaluations", payload)
        commands = [
            evaluation_command(
                operation["op"],
                {**operation["data"], "paper_id": paper_id}
                if operation["op"] == "create"
                else operation.get("data", {}),
                operation.get("evaluation_id"),
            )
            for operation in normalized["operations"]
        ]
        service = EvaluationService(self.db)
        for index, command in enumerate(commands):
            try:
                validate_evaluation_scope(service, command, paper_id)
            except (CatalogValidationError, CatalogNotFoundError) as exc:
                raise PendingEditError(f"operations[{index}]: {exc}") from exc
        rank_scopes = set()
        for index, command in enumerate(commands):
            try:
                apply_evaluation_command(
                    service, command, paper_id=paper_id, rank_scopes=rank_scopes
                )
            except (CatalogValidationError, CatalogNotFoundError) as exc:
                raise PendingEditError(f"operations[{index}]: {exc}") from exc
        service.refresh_rank_scopes(rank_scopes)
        return "paper", str(paper_id)
