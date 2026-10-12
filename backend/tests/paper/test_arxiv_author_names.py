from __future__ import annotations

import asyncio
import builtins
from datetime import UTC, datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.models.database import Author, Base, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivPaperMetadata
from backend.services.author_service import normalize_arxiv_author_name
from backend.services.paper_ingestion_service import PaperIngestionService


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


class _ArxivService:
    async def get_paper_metadata(self, arxiv_id: str) -> ArxivPaperMetadata:
        assert arxiv_id == "2605.18736"
        return ArxivPaperMetadata(
            arxiv_id=arxiv_id,
            version="v2",
            title="Analytical Engines",
            abstract="A paper about computing.",
            authors=[
                "(0000-0001) Ada   Lovelace (Analytical Engine)",
                " Grace   Hopper ",
                "Ada Lovelace",
            ],
            published=datetime(2026, 5, 20, tzinfo=UTC),
            updated=datetime(2026, 5, 21, tzinfo=UTC),
            pdf_url="https://arxiv.org/pdf/2605.18736v2",
            abs_url="https://arxiv.org/abs/2605.18736",
            categories=None,
            primary_category="cs.LG",
        )


def test_normalize_arxiv_author_name() -> None:
    assert normalize_arxiv_author_name("  Jane   Doe  ") == "Jane Doe"
    assert normalize_arxiv_author_name("(0000-0001) Jane Doe (MIT)") == "Jane Doe"
    assert normalize_arxiv_author_name("  ") == "Unknown Author"


def test_ingestion_normalizes_deduplicates_orders_and_commits_authors(
    monkeypatch, tmp_path
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'ingestion.db'}")
    Base.metadata.create_all(
        bind=engine,
        tables=[Paper.__table__, Author.__table__, PaperAuthor.__table__],
    )
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        db.add(Author(name="Ada Lovelace"))
        db.commit()

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == (
            "backend.database.authors_setup.populate_missing_authors_from_arxiv"
        ):
            raise AssertionError(
                "request path imported a file-logging maintenance script"
            )
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with session_factory() as request_db:
        paper, created = asyncio.run(
            PaperIngestionService(
                request_db, arxiv_service=_ArxivService()
            ).get_or_import_arxiv_paper(" 2605.18736v2 ")
        )
        paper_id = paper.id

    assert created is True
    with session_factory() as persisted_db:
        links = (
            persisted_db.query(Author.name, PaperAuthor.author_order)
            .join(PaperAuthor, PaperAuthor.author_id == Author.id)
            .filter(PaperAuthor.paper_id == paper_id)
            .order_by(PaperAuthor.author_order)
            .all()
        )
        assert links == [("Ada Lovelace", 1), ("Grace Hopper", 2)]
        assert persisted_db.query(Author).count() == 2
        assert persisted_db.query(PaperAuthor).count() == 2
