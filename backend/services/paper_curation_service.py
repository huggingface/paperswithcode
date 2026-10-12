"""Audited mutations for the explicitly approved paper-page sections."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from backend.models.database import (
    CatalogMutationEvent,
    HfArtifact,
    PaperHfArtifact,
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
    PaperOrganization,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    PaperXThread,
    ProjectPage,
    Repository,
)
from backend.models.database import (
    Paper as DBPaper,
)
from backend.services.catalog_errors import (
    CatalogNotFoundError,
)
from backend.services.catalog_mutation_service import (
    CatalogMutationService,
    canonical_hash,
)
from backend.services.hf_artifact_service import collect_explicit_hf_artifacts
from backend.services.paper_association_service import PaperAssociationService
from backend.services.paper_service import PaperService
from backend.services.x_thread_service import X_THREAD_FIELDS, parse_x_post_id
from backend.utils.auth import ensure_fresh_contributor_actor


def _rows(values: list[tuple], keys: tuple[str, ...]) -> list[dict]:
    return [
        {key: value for key, value in zip(keys, row)}
        for row in sorted(values, key=lambda item: tuple(str(v) for v in item))
    ]


def _datetime_value(value: Any) -> Any:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


class PaperCurationService:
    SECTIONS = {
        "tasks",
        "methods",
        "organizations",
        "repositories",
        "project_pages",
        "hf_artifacts",
        "source_url",
        "x_threads",
    }

    def __init__(self, db: Session):
        self.db = db
        self.paper_service = PaperService(db)
        self.paper_associations = PaperAssociationService(
            db, self.paper_service.get_paper_by_id
        )

    def snapshot(
        self,
        paper_id: int,
        section: str,
        *,
        lock: bool = False,
        related_project_urls: list[str] | None = None,
        related_hf_keys: list[tuple[str, str]] | None = None,
    ) -> dict:
        query = self.db.query(DBPaper).filter(DBPaper.id == paper_id)
        paper = query.with_for_update().first() if lock else query.first()
        if not paper:
            raise CatalogNotFoundError(f"Paper with ID {paper_id} not found")
        if section == "tasks":
            rows = (
                self.db.query(PaperTask.task_id, PaperTask.source)
                .filter(PaperTask.paper_id == paper_id)
                .all()
            )
            value: Any = _rows(rows, ("task_id", "source"))
        elif section == "methods":
            links = (
                self.db.query(PaperMethod.method_id)
                .filter(PaperMethod.paper_id == paper_id)
                .all()
            )
            evidence = (
                self.db.query(
                    PaperMethodEvidence.method_id,
                    PaperMethodEvidence.evidence_type,
                    PaperMethodEvidence.details,
                    PaperMethodEvidence.created_at,
                    PaperMethodEvidence.last_seen_at,
                )
                .filter(PaperMethodEvidence.paper_id == paper_id)
                .all()
            )
            exclusions = (
                self.db.query(
                    PaperMethodExclusion.method_id,
                    PaperMethodExclusion.reason,
                    PaperMethodExclusion.created_at,
                    PaperMethodExclusion.updated_at,
                )
                .filter(PaperMethodExclusion.paper_id == paper_id)
                .all()
            )
            value = {
                "links": _rows(links, ("method_id",)),
                "evidence": _rows(
                    evidence,
                    (
                        "method_id",
                        "evidence_type",
                        "details",
                        "created_at",
                        "last_seen_at",
                    ),
                ),
                "exclusions": _rows(
                    exclusions,
                    (
                        "method_id",
                        "reason",
                        "created_at",
                        "updated_at",
                    ),
                ),
            }
        elif section == "organizations":
            rows = (
                self.db.query(
                    PaperOrganization.organization_id,
                    PaperOrganization.source,
                    PaperOrganization.added_by_hf_subject,
                    PaperOrganization.added_by_hf_username,
                )
                .filter(PaperOrganization.paper_id == paper_id)
                .all()
            )
            value = _rows(
                rows,
                (
                    "organization_id",
                    "source",
                    "added_by_hf_subject",
                    "added_by_hf_username",
                ),
            )
        elif section == "repositories":
            rows = (
                self.db.query(
                    Repository.id,
                    Repository.url,
                    PaperRepository.is_official,
                )
                .join(PaperRepository, PaperRepository.repository_id == Repository.id)
                .filter(PaperRepository.paper_id == paper_id)
                .all()
            )
            value = _rows(rows, ("repository_id", "url", "is_official"))
        elif section == "project_pages":
            rows = (
                self.db.query(ProjectPage.id, ProjectPage.url, ProjectPage.is_official)
                .join(
                    PaperProjectPage,
                    PaperProjectPage.project_page_id == ProjectPage.id,
                )
                .filter(PaperProjectPage.paper_id == paper_id)
                .all()
            )
            value = _rows(rows, ("project_page_id", "url", "is_official"))
        elif section == "hf_artifacts":
            links = (
                self.db.query(HfArtifact.id, HfArtifact.kind, HfArtifact.url)
                .join(
                    PaperHfArtifact,
                    PaperHfArtifact.hf_artifact_id == HfArtifact.id,
                )
                .filter(PaperHfArtifact.paper_id == paper_id)
                .all()
            )
            value = {
                "hf_models": sorted(paper.hf_models or []),
                "hf_datasets": sorted(paper.hf_datasets or []),
                "hf_spaces": sorted(paper.hf_spaces or []),
                "hf_artifacts_scanned_at": paper.hf_artifacts_scanned_at,
                "links": _rows(links, ("artifact_id", "kind", "url")),
            }
        elif section == "source_url":
            value = {"source": paper.source, "source_url": paper.source_url}
        elif section == "x_threads":
            value = [
                {field: getattr(row, field) for field in X_THREAD_FIELDS}
                for row in self.db.query(PaperXThread)
                .filter(PaperXThread.paper_id == paper_id)
                .order_by(PaperXThread.position)
            ]
        else:
            raise ValueError(f"Unsupported paper curation section: {section}")
        result = {"paper_id": paper_id, "section": section, "value": value}
        if section == "project_pages" and related_project_urls:
            page_query = self.db.query(ProjectPage).filter(
                ProjectPage.url.in_(related_project_urls)
            )
            pages = page_query.with_for_update().all() if lock else page_query.all()
            paper_ids_by_page = {
                page.id: sorted(
                    paper_id
                    for (paper_id,) in self.db.query(PaperProjectPage.paper_id)
                    .filter(PaperProjectPage.project_page_id == page.id)
                    .all()
                )
                for page in pages
            }
            result["related_project_pages"] = [
                {
                    "id": page.id,
                    "url": page.url,
                    "is_official": page.is_official,
                    "source": page.source,
                    "created_at": page.created_at,
                    "updated_at": page.updated_at,
                    "paper_ids": paper_ids_by_page[page.id],
                }
                for page in sorted(pages, key=lambda row: row.id)
            ]
        if section == "hf_artifacts" and related_hf_keys:
            artifact_query = self.db.query(HfArtifact).filter(
                tuple_(HfArtifact.kind, HfArtifact.repo_id).in_(related_hf_keys)
            )
            artifacts = (
                artifact_query.with_for_update().all() if lock else artifact_query.all()
            )
            paper_ids_by_artifact = {
                artifact.id: sorted(
                    paper_id
                    for (paper_id,) in self.db.query(PaperHfArtifact.paper_id)
                    .filter(PaperHfArtifact.hf_artifact_id == artifact.id)
                    .all()
                )
                for artifact in artifacts
            }
            result["related_hf_artifacts"] = [
                {
                    "id": artifact.id,
                    "kind": artifact.kind,
                    "repo_id": artifact.repo_id,
                    "url": artifact.url,
                    "trending_score": artifact.trending_score,
                    "likes": artifact.likes,
                    "downloads": artifact.downloads,
                    "fetched_at": artifact.fetched_at,
                    "created_at": artifact.created_at,
                    "updated_at": artifact.updated_at,
                    "paper_ids": paper_ids_by_artifact[artifact.id],
                }
                for artifact in sorted(artifacts, key=lambda row: row.id)
            ]
        return result

    def state(self, paper_id: int) -> dict:
        sections = {
            section: canonical_hash(self.snapshot(paper_id, section))
            for section in sorted(self.SECTIONS)
        }
        return {"paper_id": paper_id, "sections": sections}

    def update(
        self,
        *,
        paper_id: int,
        section: str,
        payload: dict,
        actor: dict,
        idempotency_key: str | None,
        expected_version: str | None,
        request_id: str,
    ):
        related_project_urls = (
            [
                row["url"].strip()
                for row in payload["project_pages"]
                if row.get("url", "").strip()
            ]
            if section == "project_pages"
            else None
        )
        related_hf_keys = (
            [
                (artifact.kind, artifact.repo_id)
                for artifact in collect_explicit_hf_artifacts(
                    payload["hf_models"],
                    payload["hf_datasets"],
                    payload["hf_spaces"],
                )
            ]
            if section == "hf_artifacts"
            else None
        )
        before = self.snapshot(
            paper_id,
            section,
            related_project_urls=related_project_urls,
            related_hf_keys=related_hf_keys,
        )
        if self._removes_data(section, before["value"], payload):
            ensure_fresh_contributor_actor(actor)
        callbacks = {
            "tasks": lambda: self.paper_associations.update_tasks(
                paper_id, payload["task_ids"], commit=False
            ),
            "methods": lambda: self.paper_associations.update_methods(
                paper_id, payload["method_ids"], commit=False
            ),
            "organizations": lambda: self.paper_associations.update_organizations(
                paper_id,
                payload["organization_ids"],
                manual_added_by_hf_subject=actor.get("hf_subject"),
                manual_added_by_hf_username=actor.get("username"),
                commit=False,
            ),
            "repositories": lambda: self.paper_associations.update_repositories(
                paper_id, payload["repositories"], commit=False
            ),
            "project_pages": lambda: self.paper_associations.update_project_pages(
                paper_id,
                payload["project_pages"],
                commit=False,
                paper_scoped=actor["role"] != "admin",
            ),
            "hf_artifacts": lambda: self.paper_associations.update_hf_artifacts(
                paper_id,
                payload["hf_models"],
                payload["hf_datasets"],
                payload["hf_spaces"],
                commit=False,
            ),
            "source_url": lambda: self.paper_associations.update_source_url(
                paper_id, payload["source_url"], commit=False
            ),
            "x_threads": lambda: self.paper_associations.update_x_threads(
                paper_id, payload["x_threads"], commit=False
            ),
        }
        CatalogMutationService(self.db).mutate(
            actor=actor,
            operation="update",
            entity_type=f"paper_{section}",
            entity_id=str(paper_id),
            request_payload=payload,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            snapshot=lambda: self.snapshot(
                paper_id,
                section,
                lock=True,
                related_project_urls=related_project_urls,
                related_hf_keys=related_hf_keys,
            ),
            version_snapshot=lambda: self.snapshot(paper_id, section, lock=False),
            apply=callbacks[section],
            request_id=request_id,
        )
        return self.paper_service.get_paper_by_id(paper_id, include_resources=True)

    @staticmethod
    def _removes_data(section: str, before: Any, payload: dict) -> bool:
        if section == "tasks":
            old = {row["task_id"] for row in before or []}
            return not old.issubset(set(payload["task_ids"]))
        if section == "methods":
            old = {row["method_id"] for row in (before or {}).get("links", [])}
            return not old.issubset(set(payload["method_ids"]))
        if section == "organizations":
            old = {row["organization_id"] for row in before or []}
            return not old.issubset(set(payload["organization_ids"]))
        if section == "repositories":
            old = {row["url"] for row in before or []}
            new = {row["url"].strip() for row in payload["repositories"]}
            return not old.issubset(new)
        if section == "project_pages":
            old = {row["url"] for row in before or []}
            new = {row["url"].strip() for row in payload["project_pages"]}
            return not old.issubset(new)
        if section == "hf_artifacts":
            old = set((before or {}).get("hf_models", []))
            old.update((before or {}).get("hf_datasets", []))
            old.update((before or {}).get("hf_spaces", []))
            new = set(payload["hf_models"])
            new.update(payload["hf_datasets"])
            new.update(payload["hf_spaces"])
            return not old.issubset(new)
        if section == "x_threads":
            old = {row["tweet_id"] for row in before or []}
            return not old.issubset(
                {parse_x_post_id(url) for url in payload["x_threads"]}
            )
        return False

    def restore_snapshot(self, event) -> None:
        section = event.entity_type.removeprefix("paper_")
        paper_id = int(event.entity_id)
        before = event.before_snapshot or {}
        value = before.get("value")
        if section in {"tasks", "organizations"}:
            key = "task_id" if section == "tasks" else "organization_id"
            payload = {f"{key}s": [row[key] for row in value or []]}
        elif section == "methods":
            payload = {
                "method_ids": [
                    row["method_id"] for row in (value or {}).get("links", [])
                ]
            }
        elif section in {"repositories", "project_pages"}:
            payload = {
                section: [
                    {"url": row["url"], "is_official": row["is_official"]}
                    for row in value or []
                ]
            }
        elif section == "hf_artifacts":
            payload = {
                key: (value or {}).get(key, [])
                for key in ("hf_models", "hf_datasets", "hf_spaces")
            }
        elif section == "x_threads":
            payload = {}  # Restored from captured previews below.
        else:
            payload = {"source_url": (value or {}).get("source_url")}

        callbacks = {
            "tasks": lambda: self.paper_associations.update_tasks(
                paper_id, payload["task_ids"], commit=False
            ),
            "methods": lambda: self.paper_associations.update_methods(
                paper_id, payload["method_ids"], commit=False
            ),
            "organizations": lambda: self.paper_associations.update_organizations(
                paper_id, payload["organization_ids"], commit=False
            ),
            "repositories": lambda: self.paper_associations.update_repositories(
                paper_id, payload["repositories"], commit=False
            ),
            "project_pages": lambda: self.paper_associations.update_project_pages(
                paper_id, payload["project_pages"], commit=False
            ),
            "hf_artifacts": lambda: self.paper_associations.update_hf_artifacts(
                paper_id,
                payload["hf_models"],
                payload["hf_datasets"],
                payload["hf_spaces"],
                commit=False,
            ),
            "source_url": lambda: self._restore_source_url(paper_id, value or {}),
            # Restore the captured previews rather than re-fetching from X.
            "x_threads": lambda: self.paper_associations.replace_x_threads(
                paper_id,
                [
                    {
                        **row,
                        "posted_at": _datetime_value(row["posted_at"]),
                        "fetched_at": _datetime_value(row["fetched_at"]),
                    }
                    for row in value or []
                ],
            ),
        }
        callbacks[section]()
        if section in {"tasks", "organizations"}:
            self._restore_relationship_sources(paper_id, section, value or [])
        if section == "methods":
            self._restore_method_metadata(paper_id, value or {})
        if section == "hf_artifacts":
            paper = self.db.get(DBPaper, paper_id)
            if paper is not None:
                paper.hf_artifacts_scanned_at = _datetime_value(
                    (value or {}).get("hf_artifacts_scanned_at")
                )
        self._restore_global_entities(
            section,
            before=event.before_snapshot or {},
            after=event.after_snapshot or {},
        )

    def rollback(
        self, *, event: CatalogMutationEvent, actor: dict, request_id: str
    ) -> CatalogMutationEvent:
        section = event.entity_type.removeprefix("paper_")
        paper_id = int(event.entity_id)
        related_project_urls = (
            sorted(
                {
                    row["url"]
                    for snapshot in (
                        event.before_snapshot or {},
                        event.after_snapshot or {},
                    )
                    for row in snapshot.get("related_project_pages", [])
                }
            )
            if section == "project_pages"
            else None
        )
        related_hf_keys = (
            sorted(
                {
                    (row["kind"], row["repo_id"])
                    for snapshot in (
                        event.before_snapshot or {},
                        event.after_snapshot or {},
                    )
                    for row in snapshot.get("related_hf_artifacts", [])
                }
            )
            if section == "hf_artifacts"
            else None
        )
        _, rollback_event, _ = CatalogMutationService(self.db).mutate(
            actor=actor,
            operation="rollback",
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            request_payload={"rollback_of": str(event.id)},
            idempotency_key=f"rollback:{event.id}",
            expected_version=canonical_hash(event.after_snapshot),
            snapshot=lambda: self.snapshot(
                paper_id,
                section,
                lock=True,
                related_project_urls=related_project_urls,
                related_hf_keys=related_hf_keys,
            ),
            apply=lambda: self.restore_snapshot(event),
            request_id=request_id,
            rollback_of_event_id=event.id,
        )
        return rollback_event

    def _restore_relationship_sources(
        self, paper_id: int, section: str, rows: list[dict]
    ) -> None:
        model, id_field = (
            (PaperTask, "task_id")
            if section == "tasks"
            else (PaperOrganization, "organization_id")
        )
        for row in rows:
            link = self.db.get(model, (paper_id, row[id_field]))
            if link is not None:
                link.source = row["source"]
                if section == "organizations":
                    link.added_by_hf_subject = row.get("added_by_hf_subject")
                    link.added_by_hf_username = row.get("added_by_hf_username")

    def _restore_source_url(self, paper_id: int, value: dict) -> None:
        paper = self.db.get(DBPaper, paper_id)
        if paper is None:
            raise CatalogNotFoundError(f"Paper with ID {paper_id} not found")
        paper.source = value.get("source")
        paper.source_url = value.get("source_url")
        self.db.flush()

    def _restore_method_metadata(self, paper_id: int, value: dict) -> None:
        self.db.query(PaperMethodEvidence).filter(
            PaperMethodEvidence.paper_id == paper_id
        ).delete()
        self.db.query(PaperMethodExclusion).filter(
            PaperMethodExclusion.paper_id == paper_id
        ).delete()
        for row in value.get("evidence", []):
            self.db.add(
                PaperMethodEvidence(
                    paper_id=paper_id,
                    method_id=row["method_id"],
                    evidence_type=row["evidence_type"],
                    details=row.get("details"),
                    created_at=_datetime_value(row["created_at"]),
                    last_seen_at=_datetime_value(row["last_seen_at"]),
                )
            )
        for row in value.get("exclusions", []):
            self.db.add(
                PaperMethodExclusion(
                    paper_id=paper_id,
                    method_id=row["method_id"],
                    reason=row.get("reason"),
                    created_at=_datetime_value(row["created_at"]),
                    updated_at=_datetime_value(row["updated_at"]),
                )
            )

    def _restore_global_entities(
        self, section: str, *, before: dict, after: dict
    ) -> None:
        if section == "project_pages":
            before_by_id = {
                row["id"]: row for row in before.get("related_project_pages", [])
            }
            after_ids = {row["id"] for row in after.get("related_project_pages", [])}
            for entity_id, row in before_by_id.items():
                page = self.db.get(ProjectPage, entity_id)
                if page:
                    page.is_official = row["is_official"]
                    page.source = row["source"]
                    page.created_at = _datetime_value(row["created_at"])
                    page.updated_at = _datetime_value(row["updated_at"])
            self._delete_unreferenced(
                ProjectPage,
                PaperProjectPage,
                "project_page_id",
                after_ids - set(before_by_id),
            )
        elif section == "repositories":
            before_ids = {row["repository_id"] for row in before.get("value") or []}
            after_ids = {row["repository_id"] for row in after.get("value") or []}
            self._delete_unreferenced(
                Repository,
                PaperRepository,
                "repository_id",
                after_ids - before_ids,
            )
        elif section == "hf_artifacts":
            before_link_ids = {
                row["artifact_id"]
                for row in (before.get("value") or {}).get("links", [])
            }
            after_link_ids = {
                row["artifact_id"]
                for row in (after.get("value") or {}).get("links", [])
            }
            created_link_ids = after_link_ids - before_link_ids
            if created_link_ids:
                self.db.query(PaperHfArtifact).filter(
                    PaperHfArtifact.paper_id
                    == before.get("paper_id", after.get("paper_id")),
                    PaperHfArtifact.hf_artifact_id.in_(created_link_ids),
                ).delete(synchronize_session=False)
            before_by_id = {
                row["id"]: row for row in before.get("related_hf_artifacts", [])
            }
            after_ids = {row["id"] for row in after.get("related_hf_artifacts", [])}
            for entity_id, row in before_by_id.items():
                artifact = self.db.get(HfArtifact, entity_id)
                if artifact is None:
                    continue
                for field in (
                    "kind",
                    "repo_id",
                    "url",
                    "trending_score",
                    "likes",
                    "downloads",
                ):
                    setattr(artifact, field, row[field])
                for field in ("fetched_at", "created_at", "updated_at"):
                    setattr(artifact, field, _datetime_value(row[field]))
            self.db.flush()
            self._delete_unreferenced(
                HfArtifact,
                PaperHfArtifact,
                "hf_artifact_id",
                after_ids - set(before_by_id),
            )

    def _delete_unreferenced(
        self, entity_model, link_model, link_field: str, entity_ids: set[int]
    ) -> None:
        for entity_id in entity_ids:
            linked = (
                self.db.query(link_model)
                .filter(getattr(link_model, link_field) == entity_id)
                .first()
            )
            if linked is None:
                entity = self.db.get(entity_model, entity_id)
                if entity is not None:
                    self.db.delete(entity)
