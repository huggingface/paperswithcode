"""Atomic paper-page edits, previews, and conflict-aware batch rollback."""

from types import SimpleNamespace
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.models.database import Evaluation as DBEvaluation
from backend.models.paper_edits import (
    ArtifactEdit,
    MethodEdit,
    PaperEditDocument,
    ProjectPageEdit,
    RepositoryEdit,
    SourceEdit,
    TaskEdit,
)
from backend.models.evaluations import EvaluationCreateRequest, EvaluationUpdateRequest
from backend.services.catalog_errors import CatalogConflictError, CatalogValidationError
from backend.services.catalog_mutation_service import (
    CatalogMutationService,
    canonical_hash,
    json_safe,
)
from backend.services.evaluation_curation_service import EvaluationCurationService
from backend.services.paper_curation_service import PaperCurationService
from backend.services.paper_edit_history import public_snapshot
from backend.services.paper_edit_access import EDIT_SECTIONS, PaperEditAccess

SECTION_MODELS = dict(
    tasks=TaskEdit,
    methods=MethodEdit,
    repositories=RepositoryEdit,
    project_pages=ProjectPageEdit,
    hf_artifacts=ArtifactEdit,
    source_url=SourceEdit,
)


class PaperEditService:
    def __init__(self, db: Session):
        self.db = db
        self.papers = PaperCurationService(db)
        self.evaluations = EvaluationCurationService(db)

    def snapshot(self, paper_id: int, *, lock=False, project_urls=()) -> dict:
        sections = {
            section: self.papers.snapshot(paper_id, section, lock=lock)
            for section in sorted(EDIT_SECTIONS)
        }
        urls = sorted(
            set(project_urls) | {r["url"] for r in sections["project_pages"]["value"]}
        )
        sections["project_pages"] = self.papers.snapshot(
            paper_id, "project_pages", lock=lock, related_project_urls=urls
        )
        return json_safe(
            {
                "sections": sections,
                "evaluations": self.evaluations.paper_evaluations(paper_id, lock=lock),
            }
        )

    def export(self, paper_id: int) -> dict:
        current = self.snapshot(paper_id)
        return {
            "schema_version": "v1",
            "paper_id": paper_id,
            "version": canonical_hash(current),
            "idempotency_key": str(uuid.uuid4()),
            "operations": [],
            "current": public_snapshot("paper_edit_batch", current),
        }

    def prepare(self, document: PaperEditDocument) -> list[dict]:
        prepared = []
        seen = set()
        errors = []
        for index, operation in enumerate(document.operations):
            try:
                section = operation.section
                payload = operation.payload
                key = (section, operation.evaluation_id)
                if (
                    section != "evaluations" or operation.evaluation_id
                ) and key in seen:
                    raise ValueError(
                        "Each section/evaluation may be edited only once per batch"
                    )
                seen.add(key)
                if section == "evaluations":
                    model_type = (
                        EvaluationUpdateRequest
                        if operation.evaluation_id
                        else EvaluationCreateRequest
                    )
                    unknown = payload.keys() - model_type.model_fields.keys()
                    if unknown or payload.get("best_rank") is not None:
                        raise ValueError(
                            "Unknown or read-only evaluation fields: "
                            + ", ".join(
                                sorted(
                                    unknown
                                    | (
                                        {"best_rank"}
                                        if payload.get("best_rank") is not None
                                        else set()
                                    )
                                )
                            )
                        )
                    if not operation.evaluation_id:
                        if (
                            payload.get("paper_id", document.paper_id)
                            != document.paper_id
                        ):
                            raise ValueError("Evaluation targets a different paper")
                        payload = {**payload, "paper_id": document.paper_id}
                    model = model_type.model_validate(payload)
                    parsed = model.model_dump()
                    if operation.evaluation_id:
                        parsed.update(
                            {
                                f"{field}_set": field in model.model_fields_set
                                for field in (
                                    "harness",
                                    "source_url",
                                    "num_parameters",
                                    "hf_model_url",
                                )
                            }
                        )
                else:
                    if operation.evaluation_id is not None:
                        raise ValueError("evaluation_id only applies to evaluations")
                    parsed = (
                        SECTION_MODELS[section].model_validate(payload).model_dump()
                    )
                prepared.append(
                    {
                        "section": section,
                        "evaluation_id": operation.evaluation_id,
                        "payload": parsed,
                    }
                )
            except (ValueError, ValidationError) as error:
                errors.append({"index": index, "message": str(error)})
        if errors:
            raise CatalogValidationError(
                {"code": "invalid_edit_batch", "errors": errors}
            )
        return prepared

    def apply(self, paper_id: int, operations: list[dict], actor: dict) -> None:
        for index, operation in enumerate(operations):
            section, payload = operation["section"], operation["payload"]
            try:
                if section == "evaluations":
                    evaluation_id = operation["evaluation_id"]
                    if evaluation_id:
                        row = self.db.get(DBEvaluation, evaluation_id)
                        if row is None or int(row.paper_id) != paper_id:
                            raise CatalogValidationError(
                                "Evaluation does not belong to this paper"
                            )
                        self.evaluations.service.update_evaluation(
                            evaluation_id=evaluation_id, **payload, commit=False
                        )
                    else:
                        self.evaluations.service.create_evaluation(
                            **payload, commit=False
                        )
                else:
                    kwargs = (
                        {"paper_scoped": actor["role"] != "admin"}
                        if section == "project_pages"
                        else {}
                    )
                    getattr(self.papers.paper_associations, f"update_{section}")(
                        paper_id, **payload, commit=False, **kwargs
                    )
            except (CatalogValidationError, ValueError) as error:
                raise CatalogValidationError(
                    {
                        "code": "invalid_edit_batch",
                        "errors": [{"index": index, "message": str(error)}],
                    }
                ) from error

    def submit(
        self,
        document: PaperEditDocument,
        actor: dict,
        request_id: str,
        *,
        preview=False,
    ) -> dict:
        if not document.operations:
            raise CatalogValidationError(
                "Add at least one operation; current is reference material only"
            )
        operations = self.prepare(document)
        urls = [
            link["url"]
            for op in operations
            if op["section"] == "project_pages"
            for link in op["payload"]["project_pages"]
        ]
        if preview:
            PaperEditAccess(self.db).check_write(
                actor, document.paper_id, "paper_edit_batch", "batch", {}, limits=False
            )
            before = self.snapshot(document.paper_id, lock=True, project_urls=urls)
            if canonical_hash(self.snapshot(document.paper_id)) != document.version:
                raise CatalogConflictError(
                    "Paper changed; export again and reconcile your edits"
                )
            savepoint = self.db.begin_nested()
            try:
                self.apply(document.paper_id, operations, actor)
                self.db.flush()
                after = self.snapshot(document.paper_id, project_urls=urls)
            finally:
                savepoint.rollback()
            return {
                "status": "preview",
                "before": public_snapshot("paper_edit_batch", before),
                "after": public_snapshot("paper_edit_batch", after),
            }
        after, event, replayed = CatalogMutationService(self.db).mutate(
            actor=actor,
            operation="batch",
            entity_type="paper_edit_batch",
            entity_id=str(document.paper_id),
            request_payload={"edits": json_safe(operations)},
            idempotency_key=str(document.idempotency_key),
            expected_version=document.version,
            snapshot=lambda: self.snapshot(
                document.paper_id, lock=True, project_urls=urls
            ),
            version_snapshot=lambda: self.snapshot(document.paper_id),
            apply=lambda: self.apply(document.paper_id, operations, actor),
            request_id=request_id,
        )
        return {
            "status": "published",
            "event_id": str(event.id),
            "replayed": replayed,
            "paper_url": f"https://paperswithcode.co/paper/{document.paper_id}#edit-history",
            "after": public_snapshot("paper_edit_batch", after),
        }

    def rollback_snapshot(self, event, *, lock=False):
        urls = {
            row["url"]
            for snapshot in (event.before_snapshot, event.after_snapshot)
            for row in snapshot["sections"]["project_pages"].get(
                "related_project_pages", []
            )
        }
        return self.snapshot(int(event.entity_id), lock=lock, project_urls=urls)

    def rollback(self, *, event, actor, request_id):
        def restore():
            for section in sorted(EDIT_SECTIONS):
                before = event.before_snapshot["sections"][section]
                after = event.after_snapshot["sections"][section]
                if before != after:
                    self.papers.restore_snapshot(
                        SimpleNamespace(
                            entity_type=f"paper_{section}",
                            entity_id=event.entity_id,
                            before_snapshot=before,
                            after_snapshot=after,
                        )
                    )
            before_evals = event.before_snapshot["evaluations"]
            after_evals = event.after_snapshot["evaluations"]
            if before_evals != after_evals:
                before_ids = {r["id"] for r in before_evals}
                for row in (
                    self.db.query(DBEvaluation)
                    .filter(DBEvaluation.paper_id == int(event.entity_id))
                    .all()
                ):
                    if row.id not in before_ids:
                        self.db.delete(row)
                self.db.flush()
                for row in before_evals:
                    self.evaluations.service.restore_evaluation_snapshot(
                        row, commit=False
                    )
                self.evaluations._recalculate_snapshots(before_evals, after_evals)

        _, rollback, _ = CatalogMutationService(self.db).mutate(
            actor=actor,
            operation="rollback",
            entity_type="paper_edit_batch",
            entity_id=event.entity_id,
            request_payload={"rollback_of": str(event.id)},
            idempotency_key=f"rollback:{event.id}",
            expected_version=canonical_hash(event.after_snapshot),
            snapshot=lambda: self.rollback_snapshot(event, lock=True),
            apply=restore,
            request_id=request_id,
            rollback_of_event_id=event.id,
        )
        return rollback
