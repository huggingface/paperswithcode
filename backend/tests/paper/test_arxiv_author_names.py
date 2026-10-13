from __future__ import annotations

import asyncio
import builtins
from datetime import UTC, datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.models.database import Author, AuthorAlias, Base, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivPaperMetadata
from backend.services.author_service import (
    AuthorService,
    get_or_create_author_by_name,
    normalize_arxiv_author_name,
)
from backend.services.paper_ingestion_service import PaperIngestionService
from backend.services.paper_version_refresh_service import PaperVersionRefreshService


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


def test_author_lookup_ignores_case_and_prefers_hf_linked_row(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'authors.db'}")
    Base.metadata.create_all(bind=engine, tables=[Author.__table__])
    with sessionmaker(bind=engine)() as db:
        unlinked = Author(name="Tom AARSEN")
        linked = Author(name="Tom Aarsen", hf_username="tomaarsen")
        db.add_all([unlinked, linked])
        db.flush()

        assert get_or_create_author_by_name(db, "TOM AARSEN").id == linked.id
        assert get_or_create_author_by_name(db, "tom aarsen").id == linked.id

        created = get_or_create_author_by_name(db, "Grace Hopper")
        assert created.id not in {unlinked.id, linked.id}
        assert get_or_create_author_by_name(db, "GRACE HOPPER").id == created.id
        assert db.query(Author).count() == 3


def test_author_lookup_keeps_exact_spelling_of_distinct_hf_accounts(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'authors.db'}")
    Base.metadata.create_all(bind=engine, tables=[Author.__table__])
    with sessionmaker(bind=engine)() as db:
        first = Author(name="Wei Li", hf_username="weili")
        second = Author(name="WEI LI", hf_username="wei-li-2")
        db.add_all([first, second])
        db.flush()

        assert get_or_create_author_by_name(db, "Wei Li").id == first.id
        assert get_or_create_author_by_name(db, "WEI LI").id == second.id


def test_merged_author_id_resolves_to_surviving_author(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'aliases.db'}")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Paper.__table__,
            Author.__table__,
            PaperAuthor.__table__,
            AuthorAlias.__table__,
        ],
    )
    with sessionmaker(bind=engine)() as db:
        db.add(Author(id=1, name="Tom Aarsen", hf_username="tomaarsen"))
        db.add(
            Paper(
                id=1,
                arxiv_id="2605.00001",
                version="v1",
                title="Sentence Embeddings",
                abstract="",
                is_latest_version=True,
            )
        )
        db.flush()
        db.add_all(
            [PaperAuthor(paper_id=1, author_id=1), AuthorAlias(alias_id=2, author_id=1)]
        )
        db.commit()

        author = AuthorService(db).get_author_by_id("2")
        assert (author.id, author.full_name, author.paper_count) == (
            "1",
            "Tom Aarsen",
            1,
        )


def test_version_refresh_links_case_variant_names_once(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'refresh.db'}")
    Base.metadata.create_all(
        bind=engine,
        tables=[Paper.__table__, Author.__table__, PaperAuthor.__table__],
    )
    with sessionmaker(bind=engine)() as db:
        db.add(
            Paper(
                id=1,
                arxiv_id="2605.00002",
                version="v2",
                title="Refreshed",
                abstract="",
                is_latest_version=True,
            )
        )
        db.flush()

        PaperVersionRefreshService(
            db, paper_factory=lambda _paper_id: None
        )._replace_paper_authors(1, ["Tom Aarsen", "Grace Hopper", "TOM AARSEN"])
        db.flush()

        links = (
            db.query(Author.name, PaperAuthor.author_order)
            .join(PaperAuthor, PaperAuthor.author_id == Author.id)
            .order_by(PaperAuthor.author_order)
            .all()
        )
        assert links == [("Tom Aarsen", 1), ("Grace Hopper", 2)]
