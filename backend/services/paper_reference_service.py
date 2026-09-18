"""Match bibliography entries to catalog papers by arXiv ID or title."""

import re
import unicodedata
from typing import Iterable, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.database import Paper as DBPaper
from backend.models.papers import (
    Paper,
    PaperLookupResponse,
    PaperReferenceQuery,
    ResolvedPaperReference,
)
from backend.services.paper_service import PaperService
from backend.utils.urls import normalize_paper_route_identifier, validate_arxiv_id

# Short fingerprints ("gpt4", "nature") are more likely to be a venue, model
# name, or author fragment than a title, so they never count as evidence.
MIN_TITLE_FINGERPRINT_LENGTH = 12


def title_fingerprint(title: str) -> str:
    """Keep ASCII letters and digits only, matching the SQL index expression.

    PDF text differs from catalog titles in case, line-break hyphenation,
    punctuation, spacing, and typographic ligatures; none of those survive.
    """
    compatible = unicodedata.normalize("NFKC", title or "")
    return re.sub(r"[^a-z0-9]+", "", compatible.lower())


def title_fingerprint_expression():
    """SQL twin of title_fingerprint(); see add_paper_title_fingerprint_index.sql."""
    return func.regexp_replace(func.lower(DBPaper.title), "[^a-z0-9]+", "", "g")


class PaperReferenceService:
    """Resolve PDF bibliography entries to latest-version catalog papers."""

    def __init__(self, db: Session):
        self.db = db

    def resolve(self, references: Sequence[PaperReferenceQuery]) -> PaperLookupResponse:
        matches: dict[int, tuple[DBPaper, str]] = {}

        wanted_arxiv: dict[int, str] = {}
        for index, reference in enumerate(references):
            arxiv_id = normalize_paper_route_identifier(reference.arxiv_id or "")
            if arxiv_id and validate_arxiv_id(arxiv_id):
                wanted_arxiv[index] = arxiv_id
        by_arxiv = self._latest_papers_by_arxiv_id(set(wanted_arxiv.values()))
        for index, arxiv_id in wanted_arxiv.items():
            paper = by_arxiv.get(arxiv_id)
            if paper is not None:
                matches[index] = (paper, "arxiv_id")

        wanted_titles: dict[int, list[str]] = {}
        for index, reference in enumerate(references):
            if index in matches:
                continue
            fingerprints = [
                fingerprint
                for fingerprint in (
                    title_fingerprint(title) for title in reference.titles
                )
                if len(fingerprint) >= MIN_TITLE_FINGERPRINT_LENGTH
            ]
            if fingerprints:
                wanted_titles[index] = fingerprints
        by_title = self._latest_papers_by_title_fingerprint(
            {fingerprint for group in wanted_titles.values() for fingerprint in group}
        )
        for index, fingerprints in wanted_titles.items():
            # The longest matching candidate wins, so a complete title beats a
            # fragment that happens to be some other paper's title.
            for fingerprint in sorted(set(fingerprints), key=len, reverse=True):
                papers = by_title.get(fingerprint)
                if papers:
                    matches[index] = (self._preferred(papers), "title")
                    break

        hydrated = self._hydrate(paper for paper, _evidence in matches.values())
        return PaperLookupResponse(
            references=[
                ResolvedPaperReference(
                    key=reference.key,
                    matched_by=matches[index][1] if index in matches else None,
                    paper=hydrated.get(int(matches[index][0].id))
                    if index in matches
                    else None,
                )
                for index, reference in enumerate(references)
            ]
        )

    @staticmethod
    def _preferred(papers: Sequence[DBPaper]) -> DBPaper:
        """Prefer arXiv rows over external duplicates, then the most cited."""
        return min(
            papers,
            key=lambda paper: (
                paper.arxiv_id is None,
                -(paper.citation_count or 0),
                int(paper.id),
            ),
        )

    def _latest_papers_by_arxiv_id(self, arxiv_ids: set[str]) -> dict[str, DBPaper]:
        if not arxiv_ids:
            return {}
        rows = (
            self.db.query(DBPaper)
            .filter(DBPaper.is_latest_version, DBPaper.arxiv_id.in_(sorted(arxiv_ids)))
            .all()
        )
        return {paper.arxiv_id: paper for paper in rows}

    def _latest_papers_by_title_fingerprint(
        self, fingerprints: set[str]
    ) -> dict[str, list[DBPaper]]:
        if not fingerprints:
            return {}
        expression = title_fingerprint_expression()
        rows = (
            self.db.query(DBPaper, expression)
            .filter(DBPaper.is_latest_version, expression.in_(sorted(fingerprints)))
            .all()
        )
        grouped: dict[str, list[DBPaper]] = {}
        for paper, fingerprint in rows:
            grouped.setdefault(fingerprint, []).append(paper)
        return grouped

    def _hydrate(self, papers: Iterable[DBPaper]) -> dict[int, Paper]:
        unique = {int(paper.id): paper for paper in papers}
        if not unique:
            return {}
        hydrated = PaperService(self.db).hydrate_details(list(unique.values()))
        return {int(paper.id): paper for paper in hydrated}
