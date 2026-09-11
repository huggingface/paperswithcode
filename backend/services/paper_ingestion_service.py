"""Canonical ArXiv fetch-and-persist path shared by HTTP and sync jobs."""

from __future__ import annotations

import logging
import re
import time

from sqlalchemy.orm import Session

from backend.models.papers import Paper as ApiPaper
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.author_service import normalize_arxiv_author_name
from backend.services.paper_service import PaperService


class PaperIngestionError(RuntimeError):
    def __init__(self, arxiv_id: str, error_type: str | None):
        super().__init__(
            f"Could not import ArXiv paper {arxiv_id}: {error_type or 'unknown'}"
        )
        self.arxiv_id = arxiv_id
        self.error_type = error_type


def canonical_arxiv_id(value: str) -> str:
    return re.sub(r"v\d+$", "", value.strip(), flags=re.IGNORECASE)


class PaperIngestionService:
    def __init__(self, db: Session, arxiv_service: ArxivService | None = None):
        self.db = db
        self.arxiv_service = arxiv_service or ArxivService()

    async def get_or_import_arxiv_paper(
        self, arxiv_id: str, *, commit: bool = True
    ) -> tuple[Paper, bool]:
        arxiv_id = canonical_arxiv_id(arxiv_id)
        existing = (
            self.db.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
            .order_by(Paper.id.desc())
            .first()
        )
        if existing is not None:
            return existing, False

        metadata = await self.arxiv_service.get_paper_metadata(arxiv_id)
        if not metadata.success:
            raise PaperIngestionError(arxiv_id, metadata.error_type)
        paper_id = PaperService(self.db).add_paper(
            {
                "arxiv_id": metadata.arxiv_id,
                "title": metadata.title,
                "abstract": metadata.abstract,
                "version": metadata.version,
                "date_published": (
                    metadata.published.date() if metadata.published else None
                ),
                "primary_category": metadata.primary_category,
                "all_categories": metadata.categories,
                "is_latest_version": True,
            },
            commit=commit,
        )
        if not paper_id:
            raise PaperIngestionError(arxiv_id, "db_error")
        paper = self.db.query(Paper).filter(Paper.id == paper_id).one()
        for order, full_name in enumerate(metadata.authors or (), start=1):
            name = normalize_arxiv_author_name(full_name)
            author = self.db.query(Author).filter(Author.name == name).first()
            if author is None:
                author = Author(name=name)
                self.db.add(author)
                self.db.flush()
            if (
                self.db.query(PaperAuthor)
                .filter(
                    PaperAuthor.paper_id == paper.id,
                    PaperAuthor.author_id == author.id,
                )
                .first()
                is None
            ):
                self.db.add(
                    PaperAuthor(
                        paper_id=paper.id,
                        author_id=author.id,
                        author_order=order,
                    )
                )
        if commit:
            self.db.commit()
            self.db.refresh(paper)
        else:
            self.db.flush()
        return paper, True

    async def get_or_import_api_paper(
        self,
        arxiv_id: str,
        *,
        source_endpoint: str,
        indexing_logger: logging.Logger,
    ) -> ApiPaper:
        """Import and hydrate one paper while recording the HTTP workflow result."""
        started_at = time.monotonic()
        try:
            db_paper, _ = await self.get_or_import_arxiv_paper(arxiv_id)
        except PaperIngestionError as exc:
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            indexing_logger.info(
                "arxiv_indexing_result arxiv_id=%s source_endpoint=%s result=%s elapsed_ms=%d fallback_used=%s",
                arxiv_id,
                source_endpoint,
                exc.error_type or "upstream_error",
                elapsed_ms,
                False,
            )
            raise

        paper = PaperService(self.db).get_paper_by_id(
            db_paper.id, include_resources=True
        )
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        indexing_logger.info(
            "arxiv_indexing_result arxiv_id=%s source_endpoint=%s result=success elapsed_ms=%d fallback_used=%s",
            arxiv_id,
            source_endpoint,
            elapsed_ms,
            False,
        )
        return paper
