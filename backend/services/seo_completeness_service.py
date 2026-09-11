"""Read-only factual completeness scoring for public paper records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.papers import Paper
from backend.models.database import Evaluation, Paper as DBPaper
from backend.services.paper_service import PaperService
from backend.utils.urls import get_paper_route_identifier


MAX_REPORT_LIMIT = 1_000


@dataclass(frozen=True)
class CompletenessResult:
    route_identifier: str
    title: str
    required: dict[str, bool]
    valuable: dict[str, bool]

    @property
    def required_complete(self) -> bool:
        return all(self.required.values())

    @property
    def score(self) -> int:
        return sum(self.required.values()) + sum(self.valuable.values())

    @property
    def possible_score(self) -> int:
        return len(self.required) + len(self.valuable)

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["required_complete"] = self.required_complete
        payload["score"] = self.score
        payload["possible_score"] = self.possible_score
        return payload


def score_paper(paper: Paper, *, has_evaluations: bool) -> CompletenessResult:
    route_identifier = get_paper_route_identifier(
        paper.source, paper.arxiv_id, int(paper.id)
    )
    required = {
        "canonical_identifier": bool(
            paper.arxiv_id if paper.source == "arxiv" else paper.id
        ),
        "title": bool((paper.title or "").strip()),
        "authors": bool(paper.authors),
        "publication_date_or_year": paper.published is not None,
        "abstract_or_authoritative_summary": bool((paper.abstract or "").strip()),
    }
    valuable = {
        "tldr": bool((paper.tldr or "").strip()),
        "official_repository": any(
            repository.is_official for repository in (paper.repositories or [])
        ),
        "project_page": bool(paper.project_pages),
        "hugging_face_artifacts": bool(
            paper.hf_models or paper.hf_datasets or paper.hf_spaces
        ),
        "task_tags": bool(paper.tasks),
        "method_tags": bool(paper.methods),
        "benchmark_or_evaluations": bool(
            paper.introduced_benchmarks or has_evaluations
        ),
        "organization": bool(paper.organizations),
        "thumbnail": bool(paper.thumbnail_url),
    }
    return CompletenessResult(
        route_identifier=route_identifier,
        title=paper.title,
        required=required,
        valuable=valuable,
    )


class SeoCompletenessService:
    def __init__(self, db: Session):
        self.db = db
        self.paper_service = PaperService(db)

    def _evaluation_ids(self, paper_ids: list[int]) -> set[int]:
        if not paper_ids:
            return set()
        return {
            int(row.paper_id)
            for row in (
                self.db.query(Evaluation.paper_id)
                .filter(Evaluation.paper_id.in_(paper_ids))
                .distinct()
                .all()
            )
        }

    def report_one(self, identifier: str) -> CompletenessResult:
        paper = self.paper_service.get_paper_by_id_or_arxiv(
            identifier, include_resources=True
        )
        evaluated = self._evaluation_ids([int(paper.id)])
        return score_paper(paper, has_evaluations=int(paper.id) in evaluated)

    def report_window(
        self,
        *,
        published_since: Optional[date],
        published_until: Optional[date],
        limit: int,
    ) -> list[CompletenessResult]:
        if not 1 <= limit <= MAX_REPORT_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_REPORT_LIMIT}")
        query = self.db.query(DBPaper).filter(
            DBPaper.is_latest_version,
            DBPaper.source.in_(("arxiv", "external")),
        )
        if published_since:
            query = query.filter(DBPaper.date_published >= published_since)
        if published_until:
            query = query.filter(DBPaper.date_published <= published_until)
        rows = (
            query.order_by(DBPaper.date_published.desc().nullslast(), DBPaper.id.desc())
            .limit(limit)
            .all()
        )
        ids = [paper.id for paper in rows]
        papers = self.paper_service.hydrate_details(rows, include_resources=True)
        evaluated = self._evaluation_ids(ids)
        return [
            score_paper(
                paper,
                has_evaluations=int(paper.id) in evaluated,
            )
            for paper in papers
        ]
