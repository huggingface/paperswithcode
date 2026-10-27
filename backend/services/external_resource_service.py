"""
External resource ingestion service.

Creates `papers` rows with `source='external'` for vendor blog posts,
technical reports, model release pages, and similar non-ArXiv resources.

Design notes:

- External rows must have a non-null `source_url`. ArXiv rows continue to
  have `source='arxiv'` and a non-null `arxiv_id`.
- External rows are unique by `source_url` (after whitespace trimming).
- `date_published` is required: if neither the caller nor the LLM extractor
  produces a credible date, ingestion is rejected so the row does not
  contaminate trending or recent feeds with the wrong date.
- Authors are optional. Organizations are NOT stored in `paper_authors`;
  organization support arrives later as its own normalized model.
- GitHub URLs that the source page presents as its own code are linked with
  `is_official=true` on `paper_repositories`; the metadata extractor drops
  dependency, benchmark, and baseline repositories the page merely mentions.
  Hugging Face artifact URLs (models, datasets, spaces) are stored directly on the paper row in
  `papers.hf_models`, `papers.hf_datasets`, and `papers.hf_spaces` so they
  do not collide with the more generic `project_pages` table. For arXiv
  rows, those columns stay empty and clients derive HF artifacts from the
  Hugging Face arxiv filter URL (`huggingface.co/models?other=arxiv:<id>`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.paper_merge import find_arxiv_paper_for_title
from backend.models.papers import Paper
from backend.services.author_service import get_or_create_author_by_name
from backend.services.external_paper_pdf_archive_service import (
    archive_new_external_paper_pdf,
)
from backend.services.external_paper_curation_service import (
    enqueue_external_paper_curation,
)
from backend.models.database import (
    Paper as DBPaper,
    PaperAuthor as DBPaperAuthor,
    PaperRepository as DBPaperRepository,
    Repository as DBRepository,
)
from backend.services.hf_artifact_service import sync_explicit_hf_artifact_links
from backend.services.paper_service import PaperService
from backend.utils.exceptions import DatabaseError
from backend.utils.github_utils import normalize_github_url, parse_github_url
from backend.utils.hf_utils import (
    classify_hf_artifact_url,
    normalize_hf_artifact_url,
)
from backend.utils.public_urls import PublicUrlValidationError, normalize_public_url


logger = logging.getLogger(__name__)


class ExternalResourceError(Exception):
    """Raised when an external resource cannot be ingested."""


@dataclass
class ExternalResourceInput:
    """Caller-supplied data for ingesting an external resource."""

    source_url: str
    title: str
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    date_published: Optional[date] = None
    thumbnail_url: Optional[str] = None
    github_repository_urls: List[str] = field(default_factory=list)
    hf_artifact_urls: List[str] = field(default_factory=list)


@dataclass
class ExternalResourceIngestionResult:
    """Summary of what was created/linked when ingesting an external row."""

    paper: Paper
    repositories_added: int = 0
    repositories_existing: int = 0
    hf_models_added: int = 0
    hf_datasets_added: int = 0
    hf_spaces_added: int = 0
    hf_artifacts_existing: int = 0
    authors_added: int = 0
    authors_existing: int = 0


class ExternalResourceService:
    """Create and link external (non-ArXiv) paper rows."""

    EXTERNAL_SOURCE_TAG = "external_resource"

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_external_resource(
        self,
        payload: ExternalResourceInput,
        *,
        commit: bool = True,
        queue_curation: bool = True,
    ) -> ExternalResourceIngestionResult:
        """
        Insert (or update) an external resource and link its associated
        repositories, project pages, and authors.

        Required fields: `source_url`, `title`, `date_published`. Missing
        `date_published` raises `ExternalResourceError`; the plan deliberately
        rejects rows without a credible publication date.

        A newly created row also gets a queued enrich-paper -> add-evals
        curation workflow unless `queue_curation` is False (callers that start
        their own workflow, such as trending model resolution).

        A newly created, committed row whose source is a PDF also gets that
        PDF archived right away, so the reader and chat can open it before
        the OCR worker runs.
        """
        try:
            source_url = normalize_public_url(payload.source_url)
        except PublicUrlValidationError as exc:
            raise ExternalResourceError(str(exc)) from exc
        try:
            thumbnail_url = (
                normalize_public_url(payload.thumbnail_url)
                if payload.thumbnail_url
                else None
            )
        except PublicUrlValidationError as exc:
            raise ExternalResourceError(str(exc)) from exc
        if not payload.title or not payload.title.strip():
            raise ExternalResourceError("title is required")
        if payload.date_published is None:
            raise ExternalResourceError(
                "date_published is required for external resources; "
                "supply it manually if extraction failed"
            )

        arxiv_match = find_arxiv_paper_for_title(self.db, payload.title)
        if arxiv_match is not None:
            paper_id = arxiv_match.id
            authors_added, authors_existing = self._link_authors(
                paper_id, payload.authors
            )
            repos_added, repos_existing = self._link_github_repositories(
                paper_id, payload.github_repository_urls
            )
            hf_counts = self._set_hf_artifacts(paper_id, payload.hf_artifact_urls)
            if commit:
                self.db.commit()
            else:
                self.db.flush()
            paper_api = PaperService(self.db).get_paper_by_id(
                paper_id, include_resources=True
            )
            return ExternalResourceIngestionResult(
                paper=paper_api,
                repositories_added=repos_added,
                repositories_existing=repos_existing,
                hf_models_added=hf_counts["models_added"],
                hf_datasets_added=hf_counts["datasets_added"],
                hf_spaces_added=hf_counts["spaces_added"],
                hf_artifacts_existing=hf_counts["existing"],
                authors_added=authors_added,
                authors_existing=authors_existing,
            )

        try:
            existing = (
                self.db.query(DBPaper)
                .filter(
                    DBPaper.source == "external",
                    DBPaper.source_url == source_url,
                )
                .first()
            )

            if existing is None:
                db_paper = DBPaper(
                    title=payload.title.strip(),
                    abstract=(payload.abstract or None),
                    arxiv_id=None,
                    source="external",
                    source_url=source_url,
                    date_published=payload.date_published,
                    thumbnail_url=thumbnail_url,
                    is_latest_version=True,
                    version="v1",
                    urls_extracted=True,
                )
                self.db.add(db_paper)
                self.db.flush()
                paper_id = db_paper.id
            else:
                # Update mutable fields on a re-ingest; never change source/url.
                existing.title = payload.title.strip()
                if payload.abstract is not None:
                    existing.abstract = payload.abstract
                if payload.date_published is not None:
                    existing.date_published = payload.date_published
                if thumbnail_url is not None:
                    existing.thumbnail_url = thumbnail_url
                existing.urls_extracted = True
                paper_id = existing.id

            authors_added, authors_existing = self._link_authors(
                paper_id, payload.authors
            )
            repos_added, repos_existing = self._link_github_repositories(
                paper_id, payload.github_repository_urls
            )
            hf_counts = self._set_hf_artifacts(paper_id, payload.hf_artifact_urls)
            if existing is None and queue_curation:
                enqueue_external_paper_curation(self.db, db_paper)

            if commit:
                self.db.commit()
            else:
                self.db.flush()
        except ExternalResourceError:
            if commit:
                self.db.rollback()
            raise
        except Exception as exc:
            if commit:
                self.db.rollback()
            logger.exception("Failed to ingest external resource %s", source_url)
            raise DatabaseError(
                f"Failed to ingest external resource {source_url}: {exc}"
            )

        # After the commit, so the download never holds a transaction open.
        if existing is None and commit:
            settings = get_settings()
            archive_new_external_paper_pdf(
                paper_id,
                source_url,
                bucket_id=settings.paper_markdown_hf_bucket_id,
                token=settings.hf_token or None,
            )

        paper_api = PaperService(self.db).get_paper_by_id(
            paper_id, include_resources=True
        )
        return ExternalResourceIngestionResult(
            paper=paper_api,
            repositories_added=repos_added,
            repositories_existing=repos_existing,
            hf_models_added=hf_counts["models_added"],
            hf_datasets_added=hf_counts["datasets_added"],
            hf_spaces_added=hf_counts["spaces_added"],
            hf_artifacts_existing=hf_counts["existing"],
            authors_added=authors_added,
            authors_existing=authors_existing,
        )

    async def add_from_url(
        self,
        source_url: str,
        date_published: Optional[date] = None,
        title_override: Optional[str] = None,
        abstract_override: Optional[str] = None,
        authors_override: Optional[List[str]] = None,
        thumbnail_url: Optional[str] = None,
        github_repository_urls_extra: Optional[List[str]] = None,
        hf_artifact_urls_extra: Optional[List[str]] = None,
        generator=None,
    ) -> ExternalResourceIngestionResult:
        """
        Fetch the page at `source_url`, extract metadata via the LLM, and
        ingest the row.

        If automatic extraction does not produce a credible publication date
        and the caller did not supply one, ingestion is rejected with
        `ExternalResourceError`. This matches the plan's policy of holding
        external rows out of the catalog when the date is unknown.
        """
        # Imported lazily so the rest of the module can be used without the
        # GenAI dependencies installed.
        from backend.genai_steps.extract_external_resource_metadata import (
            extract_external_resource_metadata,
        )
        from backend.utils.url_fetch import fetch_html_and_text

        try:
            url = normalize_public_url(source_url)
        except PublicUrlValidationError as exc:
            raise ExternalResourceError(str(exc)) from exc

        raw_html, page_text = await fetch_html_and_text(url)
        if not page_text:
            raise ExternalResourceError(f"Could not fetch readable text from {url}")

        metadata = await extract_external_resource_metadata(
            url=url,
            page_text=page_text,
            raw_html=raw_html,
            generator=generator,
        )

        title = (title_override or metadata.title or "").strip()
        if not title:
            raise ExternalResourceError(
                f"Could not determine a title for {url}; supply title_override"
            )

        published = date_published or metadata.date_published
        if published is None:
            raise ExternalResourceError(
                f"Could not determine a publication date for {url}; "
                "supply date_published manually"
            )

        # Merge extracted URLs with caller-supplied overrides. The link
        # junction tables are deduped by URL, so duplicates here are safe.
        github_urls = list(metadata.github_repository_urls)
        if github_repository_urls_extra:
            github_urls.extend(github_repository_urls_extra)
        hf_urls = list(metadata.hf_artifact_urls)
        if hf_artifact_urls_extra:
            hf_urls.extend(hf_artifact_urls_extra)

        payload = ExternalResourceInput(
            source_url=url,
            title=title,
            abstract=abstract_override or metadata.abstract,
            authors=authors_override
            if authors_override is not None
            else metadata.authors,
            date_published=published,
            thumbnail_url=thumbnail_url,
            github_repository_urls=github_urls,
            hf_artifact_urls=hf_urls,
        )
        return self.add_external_resource(payload)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _link_authors(self, paper_id: int, author_names: List[str]) -> tuple[int, int]:
        added = 0
        existing = 0
        seen: set[str] = set()

        order = 1
        for raw_name in author_names or []:
            if not raw_name:
                continue
            name = raw_name.strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            db_author = get_or_create_author_by_name(self.db, name)

            link = (
                self.db.query(DBPaperAuthor)
                .filter(
                    DBPaperAuthor.paper_id == paper_id,
                    DBPaperAuthor.author_id == db_author.id,
                )
                .first()
            )
            if link is None:
                self.db.add(
                    DBPaperAuthor(
                        paper_id=paper_id,
                        author_id=db_author.id,
                        author_order=order,
                    )
                )
                added += 1
            else:
                existing += 1
            order += 1

        return added, existing

    def _link_github_repositories(
        self, paper_id: int, urls: List[str]
    ) -> tuple[int, int]:
        added = 0
        existing = 0
        seen: set[str] = set()

        for raw_url in urls or []:
            normalized = normalize_github_url(raw_url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            owner, name = parse_github_url(normalized)

            repo = (
                self.db.query(DBRepository)
                .filter(DBRepository.url == normalized)
                .first()
            )
            if repo is None:
                repo = DBRepository(
                    url=normalized,
                    owner=owner,
                    name=name,
                    num_stars=0,
                    source=self.EXTERNAL_SOURCE_TAG,
                )
                self.db.add(repo)
                self.db.flush()

            link = (
                self.db.query(DBPaperRepository)
                .filter(
                    DBPaperRepository.paper_id == paper_id,
                    DBPaperRepository.repository_id == repo.id,
                )
                .first()
            )
            if link is None:
                self.db.add(
                    DBPaperRepository(
                        paper_id=paper_id,
                        repository_id=repo.id,
                        # Per plan: GitHub repos linked directly from the
                        # external source page default to is_official=true.
                        is_official=True,
                    )
                )
                added += 1
            else:
                if not link.is_official:
                    link.is_official = True
                existing += 1

        return added, existing

    def _set_hf_artifacts(self, paper_id: int, urls: List[str]) -> dict[str, int]:
        """
        Merge the supplied Hugging Face artifact URLs into the paper row's
        `hf_models`, `hf_datasets`, and `hf_spaces` columns.

        URLs are normalized to canonical https://huggingface.co/<path> form,
        deduped against any existing stored URLs, and categorized via the
        URL path (`datasets/...`, `spaces/...`, otherwise model). Anything
        that does not look like an HF artifact URL is logged and skipped.
        """
        paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
        if paper is None:
            return {
                "models_added": 0,
                "datasets_added": 0,
                "spaces_added": 0,
                "existing": 0,
            }

        existing_models = list(paper.hf_models or [])
        existing_datasets = list(paper.hf_datasets or [])
        existing_spaces = list(paper.hf_spaces or [])
        # Hub repo ids are case-insensitive, so `org/Model` and `org/model`
        # are the same artifact.
        seen: set[str] = {
            url.lower() for url in existing_models + existing_datasets + existing_spaces
        }

        models_added = 0
        datasets_added = 0
        spaces_added = 0
        existing_count = 0

        for raw_url in urls or []:
            normalized = normalize_hf_artifact_url(raw_url)
            if normalized is None:
                logger.info(
                    "Skipping non-HF artifact URL while ingesting paper %s: %r",
                    paper_id,
                    raw_url,
                )
                continue
            if normalized.lower() in seen:
                existing_count += 1
                continue
            seen.add(normalized.lower())

            kind = classify_hf_artifact_url(normalized)
            if kind == "model":
                existing_models.append(normalized)
                models_added += 1
            elif kind == "dataset":
                existing_datasets.append(normalized)
                datasets_added += 1
            elif kind == "space":
                existing_spaces.append(normalized)
                spaces_added += 1
            else:
                logger.info(
                    "Could not classify HF URL while ingesting paper %s: %r",
                    paper_id,
                    raw_url,
                )

        paper.hf_models = existing_models or None
        paper.hf_datasets = existing_datasets or None
        paper.hf_spaces = existing_spaces or None
        sync_explicit_hf_artifact_links(
            self.db,
            paper.id,
            paper.hf_models,
            paper.hf_datasets,
            paper.hf_spaces,
        )
        # New explicit URLs must not inherit a previously completed empty scan.
        paper.hf_artifacts_scanned_at = None

        return {
            "models_added": models_added,
            "datasets_added": datasets_added,
            "spaces_added": spaces_added,
            "existing": existing_count,
        }
