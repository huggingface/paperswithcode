"""Transactional mutations for paper associations and explicit resource links."""

from __future__ import annotations

import re
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.papers import Paper
from backend.models.database import Method as DBMethod
from backend.models.database import Organization as DBOrganization
from backend.models.database import Paper as DBPaper
from backend.models.database import PaperOrganization as DBPaperOrganization
from backend.models.database import PaperProjectPage as DBPaperProjectPage
from backend.models.database import PaperRepository, PaperTask, PaperXThread
from backend.models.database import ProjectPage as DBProjectPage
from backend.models.database import Repository as DBRepository
from backend.models.database import Task as DBTask
from backend.services.catalog_errors import CatalogValidationError
from backend.services.hf_artifact_service import (
    sync_explicit_hf_artifact_links,
    unlink_replaced_hf_artifact_links,
)
from backend.services.paper_method_link_service import replace_manual_links
from backend.services.repository_service import find_repository_by_url
from backend.services import x_thread_service
from backend.services.x_thread_service import (
    MAX_X_THREADS_PER_PAPER,
    X_THREAD_FIELDS,
    parse_x_post_id,
)
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.github_utils import normalize_github_url, parse_github_url
from backend.utils.hf_utils import normalize_hf_artifact_payload


class PaperHydrator(Protocol):
    def __call__(self, paper_id: int, include_resources: bool = False) -> Paper: ...


class PaperAssociationHydrationError(Exception):
    """Expected failure from the injected paper hydration collaborator."""


class PaperAssociationService:
    """Own association replacement, provenance, normalization, and transactions."""

    def __init__(self, db: Session, hydrate_paper: PaperHydrator):
        self.db = db
        self._hydrate_paper = hydrate_paper

    def _paper(self, paper_id: int) -> DBPaper:
        paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
        if paper is None:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")
        return paper

    def _finish(
        self, paper_id: int, paper: DBPaper, *, commit: bool
    ) -> Paper | DBPaper:
        if not commit:
            self.db.flush()
            return paper
        self.db.commit()
        return self._hydrate(paper_id)

    def _hydrate(self, paper_id: int) -> Paper:
        """Call the injected hydrator with its explicit failure contract."""
        try:
            return self._hydrate_paper(paper_id, include_resources=True)
        except RuntimeError as error:
            raise PaperAssociationHydrationError(str(error)) from error

    def _raise_mutation_error(
        self, operation: str, error: Exception, *, commit: bool
    ) -> None:
        if commit:
            self.db.rollback()
        if isinstance(
            error, (PaperNotFoundError, DatabaseError, CatalogValidationError)
        ):
            raise error
        raise DatabaseError(f"Error updating paper {operation}: {error}") from error

    def update_tasks(
        self, paper_id: int, task_ids: list[int], *, commit: bool = True
    ) -> Paper | DBPaper:
        try:
            paper = self._paper(paper_id)
            existing_tasks = self.db.query(DBTask).filter(DBTask.id.in_(task_ids)).all()
            existing_task_ids = {task.id for task in existing_tasks}
            invalid_task_ids = set(task_ids) - existing_task_ids
            if invalid_task_ids:
                raise CatalogValidationError(f"Invalid task IDs: {invalid_task_ids}")

            self.db.query(PaperTask).filter(PaperTask.paper_id == paper_id).delete()
            for task_id in task_ids:
                self.db.add(
                    PaperTask(paper_id=paper_id, task_id=task_id, source="manual")
                )
            return self._finish(paper_id, paper, commit=commit)
        except (PaperNotFoundError, DatabaseError, CatalogValidationError) as error:
            self._raise_mutation_error("tasks", error, commit=commit)
        except (SQLAlchemyError, PaperAssociationHydrationError) as error:
            self._raise_mutation_error("tasks", error, commit=commit)

    def update_organizations(
        self,
        paper_id: int,
        organization_ids: list[int],
        *,
        manual_added_by_hf_subject: str | None = None,
        manual_added_by_hf_username: str | None = None,
        commit: bool = True,
    ) -> Paper | DBPaper:
        try:
            paper = self._paper(paper_id)
            existing_organizations = (
                self.db.query(DBOrganization)
                .filter(DBOrganization.id.in_(organization_ids))
                .all()
            )
            existing_ids = {organization.id for organization in existing_organizations}
            invalid_ids = set(organization_ids) - existing_ids
            if invalid_ids:
                raise CatalogValidationError(f"Invalid organization IDs: {invalid_ids}")

            links = (
                self.db.query(DBPaperOrganization)
                .filter(DBPaperOrganization.paper_id == paper_id)
                .all()
            )
            links_by_organization = {link.organization_id: link for link in links}
            requested_ids = set(organization_ids)

            for organization_id, link in links_by_organization.items():
                if organization_id not in requested_ids:
                    self.db.delete(link)

            for organization_id in requested_ids - links_by_organization.keys():
                self.db.add(
                    DBPaperOrganization(
                        paper_id=paper_id,
                        organization_id=organization_id,
                        source="manual",
                        added_by_hf_subject=manual_added_by_hf_subject,
                        added_by_hf_username=manual_added_by_hf_username,
                    )
                )
            return self._finish(paper_id, paper, commit=commit)
        except (PaperNotFoundError, DatabaseError, CatalogValidationError) as error:
            self._raise_mutation_error("organizations", error, commit=commit)
        except (SQLAlchemyError, PaperAssociationHydrationError) as error:
            self._raise_mutation_error("organizations", error, commit=commit)

    def update_methods(
        self, paper_id: int, method_ids: list[int], *, commit: bool = True
    ) -> Paper | DBPaper:
        try:
            paper = self._paper(paper_id)
            existing_methods = (
                self.db.query(DBMethod).filter(DBMethod.id.in_(method_ids)).all()
            )
            existing_ids = {method.id for method in existing_methods}
            invalid_ids = set(method_ids) - existing_ids
            if invalid_ids:
                raise CatalogValidationError(f"Invalid method IDs: {invalid_ids}")

            replace_manual_links(self.db, paper_id=paper_id, method_ids=method_ids)
            return self._finish(paper_id, paper, commit=commit)
        except (PaperNotFoundError, DatabaseError, CatalogValidationError) as error:
            self._raise_mutation_error("methods", error, commit=commit)
        except (SQLAlchemyError, PaperAssociationHydrationError) as error:
            self._raise_mutation_error("methods", error, commit=commit)

    def update_repositories(
        self,
        paper_id: int,
        repositories: list[dict[str, Any]],
        *,
        commit: bool = True,
        promote_lone_repository: bool = True,
    ) -> Paper | DBPaper:
        """Replace the paper's repositories.

        A lone repository is marked official unless ``promote_lone_repository``
        is false, for callers whose ``is_official=False`` is an explicit choice.
        """
        try:
            paper = self._paper(paper_id)
            self.db.query(PaperRepository).filter(
                PaperRepository.paper_id == paper_id
            ).delete()

            associations: dict[int, bool] = {}
            for repository_data in repositories:
                url = repository_data.get("url", "").strip()
                is_official = repository_data.get("is_official", False)
                if not url:
                    continue

                normalized = normalize_github_url(url)
                if normalized:
                    url = normalized
                repository = find_repository_by_url(self.db, url)
                if repository is not None:
                    repository_id = repository.id
                else:
                    owner, name = parse_github_url(url) if normalized else (None, None)
                    if not owner or not name:
                        github_match = re.match(
                            r"https?://github\.com/([^/]+)/([^/]+)(?:/.*)?", url
                        )
                        if github_match:
                            owner = github_match.group(1)
                            name = github_match.group(2)
                            name = name.removesuffix(".git")
                    repository = DBRepository(
                        url=url,
                        owner=owner,
                        name=name,
                        num_stars=0,
                        source="manual",
                    )
                    self.db.add(repository)
                    self.db.flush()
                    repository_id = repository.id

                associations[repository_id] = (
                    associations.get(repository_id, False) or is_official
                )

            if promote_lone_repository and len(associations) == 1:
                only_repository_id = next(iter(associations))
                associations[only_repository_id] = True

            for repository_id, is_official in associations.items():
                self.db.add(
                    PaperRepository(
                        paper_id=paper_id,
                        repository_id=repository_id,
                        is_official=is_official,
                    )
                )
            return self._finish(paper_id, paper, commit=commit)
        except (PaperNotFoundError, DatabaseError, CatalogValidationError) as error:
            self._raise_mutation_error("repositories", error, commit=commit)
        except (SQLAlchemyError, PaperAssociationHydrationError) as error:
            self._raise_mutation_error("repositories", error, commit=commit)

    def update_project_pages(
        self,
        paper_id: int,
        project_pages: list[dict[str, Any]],
        *,
        commit: bool = True,
        paper_scoped: bool = False,
    ) -> Paper | DBPaper:
        try:
            paper = self._paper(paper_id)
            self.db.query(DBPaperProjectPage).filter(
                DBPaperProjectPage.paper_id == paper_id
            ).delete()

            for page_data in project_pages:
                url = page_data.get("url", "").strip()
                is_official = page_data.get("is_official", False)
                if not url:
                    continue

                project_page = (
                    self.db.query(DBProjectPage)
                    .filter(DBProjectPage.url == url)
                    .with_for_update()
                    .first()
                )
                if project_page is not None:
                    if (is_official and not project_page.is_official) or (
                        paper_scoped and is_official != project_page.is_official
                    ):
                        if (
                            paper_scoped
                            and self.db.query(DBPaperProjectPage)
                            .filter(
                                DBPaperProjectPage.project_page_id == project_page.id,
                                DBPaperProjectPage.paper_id != paper_id,
                            )
                            .first()
                        ):
                            raise CatalogValidationError(
                                "Changing official status on a shared project page requires an administrator"
                            )
                        project_page.is_official = is_official
                else:
                    project_page = DBProjectPage(
                        url=url,
                        is_official=is_official,
                        source="manual",
                    )
                    self.db.add(project_page)
                    self.db.flush()

                self.db.add(
                    DBPaperProjectPage(
                        paper_id=paper_id,
                        project_page_id=project_page.id,
                    )
                )
            return self._finish(paper_id, paper, commit=commit)
        except (PaperNotFoundError, DatabaseError, CatalogValidationError) as error:
            self._raise_mutation_error("project pages", error, commit=commit)
        except (SQLAlchemyError, PaperAssociationHydrationError) as error:
            self._raise_mutation_error("project pages", error, commit=commit)

    def update_source_url(
        self, paper_id: int, source_url: str, *, commit: bool = True
    ) -> Paper | DBPaper:
        try:
            normalized = (source_url or "").strip()
            if not normalized:
                raise CatalogValidationError("source_url must be a non-empty string")
            if len(normalized) > 2000:
                raise CatalogValidationError(
                    "source_url must be at most 2000 characters"
                )

            paper = self._paper(paper_id)
            if paper.source != "external":
                raise CatalogValidationError(
                    "source_url can only be edited on external papers; "
                    "ArXiv rows derive their URL from arxiv_id"
                )
            if normalized == paper.source_url:
                return self._hydrate(paper_id)

            collision = (
                self.db.query(DBPaper.id)
                .filter(
                    DBPaper.source == "external",
                    DBPaper.source_url == normalized,
                    DBPaper.id != paper_id,
                )
                .first()
            )
            if collision is not None:
                raise CatalogValidationError(
                    f"Another external paper already uses source_url={normalized!r}"
                )

            paper.source_url = normalized
            return self._finish(paper_id, paper, commit=commit)
        except (PaperNotFoundError, DatabaseError, CatalogValidationError) as error:
            self._raise_mutation_error("source URL", error, commit=commit)
        except (SQLAlchemyError, PaperAssociationHydrationError) as error:
            self._raise_mutation_error("source URL", error, commit=commit)

    def update_x_threads(
        self, paper_id: int, x_threads: list[str], *, commit: bool = True
    ) -> Paper | DBPaper:
        """Replace a paper's X threads, previewing only newly linked posts."""
        try:
            paper = self._paper(paper_id)
            tweet_ids = list(dict.fromkeys(parse_x_post_id(url) for url in x_threads))
            if len(tweet_ids) > MAX_X_THREADS_PER_PAPER:
                raise CatalogValidationError(
                    f"A paper can link at most {MAX_X_THREADS_PER_PAPER} X threads"
                )
            existing = {
                row.tweet_id: {field: getattr(row, field) for field in X_THREAD_FIELDS}
                for row in self.db.query(PaperXThread).filter(
                    PaperXThread.paper_id == paper_id
                )
            }
            rows = [
                existing.get(tweet_id) or x_thread_service.fetch_x_post_row(tweet_id)
                for tweet_id in tweet_ids
            ]
            self.replace_x_threads(paper_id, rows)
            return self._finish(paper_id, paper, commit=commit)
        except (PaperNotFoundError, DatabaseError, CatalogValidationError) as error:
            self._raise_mutation_error("X threads", error, commit=commit)
        except (SQLAlchemyError, PaperAssociationHydrationError) as error:
            self._raise_mutation_error("X threads", error, commit=commit)

    def replace_x_threads(self, paper_id: int, rows: list[dict[str, Any]]) -> None:
        """Write already-previewed X thread rows in display order."""
        self.db.query(PaperXThread).filter(PaperXThread.paper_id == paper_id).delete()
        for position, row in enumerate(rows):
            self.db.add(
                PaperXThread(
                    paper_id=paper_id,
                    position=position,
                    **{field: row[field] for field in X_THREAD_FIELDS},
                )
            )
        self.db.flush()

    def update_hf_artifacts(
        self,
        paper_id: int,
        hf_models: list[str],
        hf_datasets: list[str],
        hf_spaces: list[str],
        *,
        commit: bool = True,
    ) -> Paper | DBPaper:
        try:
            paper = self._paper(paper_id)
            models, datasets, spaces = normalize_hf_artifact_payload(
                hf_models, hf_datasets, hf_spaces
            )
            unlink_replaced_hf_artifact_links(
                self.db,
                paper.id,
                previous=(paper.hf_models, paper.hf_datasets, paper.hf_spaces),
                current=(models, datasets, spaces),
            )
            paper.hf_models = models or None
            paper.hf_datasets = datasets or None
            paper.hf_spaces = spaces or None
            sync_explicit_hf_artifact_links(
                self.db,
                paper.id,
                paper.hf_models,
                paper.hf_datasets,
                paper.hf_spaces,
            )
            paper.hf_artifacts_scanned_at = None
            return self._finish(paper_id, paper, commit=commit)
        except ValueError as error:
            if commit:
                self.db.rollback()
            raise CatalogValidationError(str(error))
        except (PaperNotFoundError, DatabaseError, CatalogValidationError) as error:
            self._raise_mutation_error("HF artifacts", error, commit=commit)
        except (SQLAlchemyError, PaperAssociationHydrationError) as error:
            self._raise_mutation_error("HF artifacts", error, commit=commit)
