"""Transactional refresh of indexed ArXiv versions and their curated links."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.models.papers import Paper
from backend.services.evaluation_service import EvaluationService
from backend.services.author_hf_profile_sync_service import (
    HF_PAPERS_URL,
    AuthorHfProfileSyncService,
)
from backend.services.author_service import (
    get_or_create_author_by_name,
    normalize_arxiv_author_name,
)
from backend.models.database import (
    Author as DBAuthor,
    Paper as DBPaper,
    PaperAuthor,
    PaperConference as DBPaperConference,
    PaperDataset,
    PaperHfArtifact as DBPaperHfArtifact,
    PaperMethod,
    PaperOrganization as DBPaperOrganization,
    PaperProjectPage as DBPaperProjectPage,
    PaperRepository as DBPaperRepository,
    PaperTask,
)
from backend.utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArxivPaperRefreshResult:
    paper: Paper
    created: bool
    refreshed: bool
    previous_version: Optional[str]
    latest_version: str


class PaperVersionRefreshService:
    """Refresh one ArXiv identity and migrate curated state atomically."""

    def __init__(
        self,
        db: Session,
        *,
        paper_factory: Callable[[int], Paper],
    ) -> None:
        self.db = db
        self._paper_factory = paper_factory

    async def refresh_arxiv_paper(self, arxiv_id: str) -> ArxivPaperRefreshResult:
        """Refresh an indexed ArXiv paper from arXiv's current metadata."""
        from backend.services.arxiv_service import ArxivService

        previous_latest = (
            self.db.query(DBPaper)
            .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version)
            .order_by(desc(DBPaper.id))
            .first()
        )
        previous_version = previous_latest.version if previous_latest else None

        metadata = await ArxivService().get_paper_metadata(arxiv_id)
        if not metadata.success:
            error_type = metadata.error_type or "temporary_failure"
            raise DatabaseError(f"arxiv_metadata_error:{error_type}")

        target = (
            self.db.query(DBPaper)
            .filter(
                DBPaper.arxiv_id == metadata.arxiv_id,
                DBPaper.version == metadata.version,
            )
            .first()
        )
        created = target is None
        claim_sources = {
            paper.id for paper in (previous_latest, target) if paper is not None
        }
        hf_paper = None
        if self._claimed_authors(claim_sources).keys() - _name_keys(metadata.authors):
            # A claimed author is no longer on the byline under their row's
            # name, usually because the row took a new name from Hugging Face.
            # Re-apply the claim from HF's verified claims instead.
            hf_paper = await _fetch_hf_paper(metadata.arxiv_id)

        try:
            if target is None:
                target = DBPaper(
                    arxiv_id=metadata.arxiv_id,
                    title=metadata.title,
                    abstract=metadata.abstract,
                    version=metadata.version,
                    date_published=metadata.published.date()
                    if metadata.published
                    else None,
                    primary_category=metadata.primary_category,
                    all_categories=metadata.categories,
                    is_latest_version=True,
                    citation_count=previous_latest.citation_count
                    if previous_latest
                    else 0,
                    semantic_scholar_id=previous_latest.semantic_scholar_id
                    if previous_latest
                    else None,
                    citation_updated_at=previous_latest.citation_updated_at
                    if previous_latest
                    else None,
                    urls_extracted=previous_latest.urls_extracted
                    if previous_latest
                    else False,
                    methods_scanned_at=previous_latest.methods_scanned_at
                    if previous_latest
                    else None,
                    thumbnail_url=previous_latest.thumbnail_url
                    if previous_latest
                    else None,
                    tldr=previous_latest.tldr if previous_latest else None,
                    num_pages=previous_latest.num_pages if previous_latest else None,
                    hf_models=list(previous_latest.hf_models)
                    if previous_latest and previous_latest.hf_models is not None
                    else None,
                    hf_datasets=list(previous_latest.hf_datasets)
                    if previous_latest and previous_latest.hf_datasets is not None
                    else None,
                    hf_spaces=list(previous_latest.hf_spaces)
                    if previous_latest and previous_latest.hf_spaces is not None
                    else None,
                    trending_score=previous_latest.trending_score
                    if previous_latest
                    else None,
                    trending_score_updated_at=previous_latest.trending_score_updated_at
                    if previous_latest
                    else None,
                    github_trending_component=previous_latest.github_trending_component
                    if previous_latest
                    else None,
                    hf_trending_component=previous_latest.hf_trending_component
                    if previous_latest
                    else None,
                    hf_artifacts_scanned_at=previous_latest.hf_artifacts_scanned_at
                    if previous_latest
                    else None,
                )
                self.db.add(target)
                self.db.flush()
            else:
                target.title = metadata.title
                target.abstract = metadata.abstract
                target.date_published = (
                    metadata.published.date() if metadata.published else None
                )
                target.primary_category = metadata.primary_category
                target.all_categories = metadata.categories

            if previous_latest and previous_latest.id != target.id:
                self._copy_curated_links(previous_latest.id, target.id)

            self._replace_paper_authors(
                target.id,
                metadata.authors,
                previous_latest.id if previous_latest else None,
            )

            (
                self.db.query(DBPaper)
                .filter(DBPaper.arxiv_id == metadata.arxiv_id, DBPaper.id != target.id)
                .update({DBPaper.is_latest_version: False}, synchronize_session=False)
            )
            target.is_latest_version = True
            self.db.add(target)
            if hf_paper is not None:
                # The sync queries the new links and latest version.
                self.db.flush()
                AuthorHfProfileSyncService(self.db).sync_paper(hf_paper)
            self.db.commit()
            self.db.refresh(target)
        except Exception as exc:
            self.db.rollback()
            raise DatabaseError(
                f"Error refreshing ArXiv paper {arxiv_id}: {exc}"
            ) from exc

        paper = self._paper_factory(target.id)
        return ArxivPaperRefreshResult(
            paper=paper,
            created=created,
            refreshed=created or previous_version != metadata.version,
            previous_version=previous_version,
            latest_version=metadata.version,
        )

    def _copy_curated_links(self, source_paper_id: int, target_paper_id: int) -> None:
        if source_paper_id == target_paper_id:
            return

        for link in (
            self.db.query(PaperTask).filter(PaperTask.paper_id == source_paper_id).all()
        ):
            self._add_if_missing(
                PaperTask,
                paper_id=target_paper_id,
                task_id=link.task_id,
                defaults={"source": link.source},
            )

        for link in (
            self.db.query(PaperMethod)
            .filter(PaperMethod.paper_id == source_paper_id)
            .all()
        ):
            self._add_if_missing(
                PaperMethod,
                paper_id=target_paper_id,
                method_id=link.method_id,
            )

        for link in (
            self.db.query(DBPaperRepository)
            .filter(DBPaperRepository.paper_id == source_paper_id)
            .all()
        ):
            self._add_if_missing(
                DBPaperRepository,
                paper_id=target_paper_id,
                repository_id=link.repository_id,
                defaults={"is_official": link.is_official},
            )

        for link in (
            self.db.query(DBPaperProjectPage)
            .filter(DBPaperProjectPage.paper_id == source_paper_id)
            .all()
        ):
            self._add_if_missing(
                DBPaperProjectPage,
                paper_id=target_paper_id,
                project_page_id=link.project_page_id,
            )

        for link in (
            self.db.query(DBPaperHfArtifact)
            .filter(DBPaperHfArtifact.paper_id == source_paper_id)
            .all()
        ):
            self._add_if_missing(
                DBPaperHfArtifact,
                paper_id=target_paper_id,
                hf_artifact_id=link.hf_artifact_id,
            )

        for link in (
            self.db.query(DBPaperConference)
            .filter(DBPaperConference.paper_id == source_paper_id)
            .all()
        ):
            self._add_if_missing(
                DBPaperConference,
                paper_id=target_paper_id,
                conference_id=link.conference_id,
                defaults={"source": link.source, "award": link.award},
            )

        for link in (
            self.db.query(DBPaperOrganization)
            .filter(DBPaperOrganization.paper_id == source_paper_id)
            .all()
        ):
            self._add_if_missing(
                DBPaperOrganization,
                paper_id=target_paper_id,
                organization_id=link.organization_id,
                defaults={"source": link.source},
            )

        for link in (
            self.db.query(PaperDataset)
            .filter(PaperDataset.paper_id == source_paper_id)
            .all()
        ):
            self._add_if_missing(
                PaperDataset,
                paper_id=target_paper_id,
                dataset_id=link.dataset_id,
            )

        # Leaderboards list every version's rows, so results move to the new
        # version rather than being copied; the old version keeps none.
        EvaluationService(self.db).move_paper_evaluations(
            source_paper_id, target_paper_id
        )

    def _add_if_missing(
        self, model: Any, defaults: Optional[Dict[str, Any]] = None, **keys: Any
    ) -> None:
        exists = self.db.query(model).filter_by(**keys).first()
        if exists:
            return
        values = dict(keys)
        values.update(defaults or {})
        self.db.add(model(**values))

    def _claimed_authors(self, paper_ids: set[int]) -> Dict[str, DBAuthor]:
        return {
            normalize_arxiv_author_name(author.name).casefold(): author
            for author in (
                self.db.query(DBAuthor)
                .join(PaperAuthor, PaperAuthor.author_id == DBAuthor.id)
                .filter(PaperAuthor.paper_id.in_(paper_ids), PaperAuthor.claimed)
            )
        }

    def _replace_paper_authors(
        self, paper_id: int, author_names: List[str], claims_from: Optional[int]
    ) -> None:
        # Keep Hugging Face claims (on this version or the previous latest one)
        # attached to the claiming author instead of re-matching it by name. A
        # claim follows its author's exact name (any case); if arXiv now spells
        # the name differently, guessing could hand it to a namesake, so the
        # claim is dropped here and refresh_arxiv_paper re-applies it from HF.
        names = [normalize_arxiv_author_name(full_name) for full_name in author_names]
        claimed_authors = self._claimed_authors({paper_id, claims_from or paper_id})
        self.db.query(PaperAuthor).filter(PaperAuthor.paper_id == paper_id).delete()

        linked_ids: set[int] = set()
        for order, name in enumerate(names, start=1):
            author = claimed_authors.get(name.casefold())
            claimed = author is not None
            if author is None:
                author = get_or_create_author_by_name(self.db, name)
            if author.id in linked_ids:
                continue
            linked_ids.add(author.id)
            self.db.add(
                PaperAuthor(
                    paper_id=paper_id,
                    author_id=author.id,
                    author_order=order,
                    claimed=claimed,
                )
            )


def _name_keys(author_names: List[str]) -> set[str]:
    return {normalize_arxiv_author_name(name).casefold() for name in author_names}


async def _fetch_hf_paper(arxiv_id: str) -> Optional[Dict[str, Any]]:
    """Return the HF paper with its authorship claims, or None if unavailable."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5)) as client:
            response = await client.get(f"{HF_PAPERS_URL}/{arxiv_id}")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        # The claim stays dropped until sync_hf_author_profiles sees the paper.
        logger.warning("hf_paper_claims_unavailable %s: %s", arxiv_id, exc)
        return None
    return response.json()
