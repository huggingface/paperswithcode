import asyncio
from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Author,
    Base,
    Method,
    Paper,
    PaperAuthor,
    PaperMethod,
    PaperRepository,
    PaperTask,
    Repository,
    Task,
)
from backend.services.arxiv_service import ArxivPaperMetadata
from backend.services.paper_service import PaperService


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


def _build_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def _metadata(version: str, title: str = "Updated Title") -> ArxivPaperMetadata:
    return ArxivPaperMetadata(
        arxiv_id="2605.18736",
        version=version,
        title=title,
        abstract="Updated abstract",
        authors=["Ada Lovelace", "Grace Hopper"],
        published=datetime(2026, 5, 20, tzinfo=timezone.utc),
        updated=datetime(2026, 5, 21, tzinfo=timezone.utc),
        pdf_url=f"https://arxiv.org/pdf/2605.18736{version}",
        abs_url="https://arxiv.org/abs/2605.18736",
        categories=None,
        primary_category="cs.LG",
    )


def _patch_arxiv(monkeypatch, metadata: ArxivPaperMetadata):
    class FakeArxivService:
        async def get_paper_metadata(self, arxiv_id: str):
            assert arxiv_id == "2605.18736"
            return metadata

    monkeypatch.setattr("backend.services.arxiv_service.ArxivService", FakeArxivService)


def test_refresh_arxiv_paper_creates_new_latest_version_and_copies_links(monkeypatch):
    db = _build_session()
    db.add_all(
        [
            Paper(
                id=1,
                title="Old Title",
                abstract="Old abstract",
                arxiv_id="2605.18736",
                version="v1",
                is_latest_version=True,
                date_published=date(2026, 5, 20),
                citation_count=7,
            ),
            Task(id=1, name="Vision-Language Models", slug="vlm"),
            Method(id=1, name="Attention", slug="attention"),
            Repository(id=1, url="https://github.com/example/repo"),
        ]
    )
    db.add_all(
        [
            PaperTask(paper_id=1, task_id=1, source="manual"),
            PaperMethod(paper_id=1, method_id=1),
            PaperRepository(paper_id=1, repository_id=1, is_official=True),
        ]
    )
    db.commit()
    _patch_arxiv(monkeypatch, _metadata("v2"))

    result = asyncio.run(PaperService(db).refresh_arxiv_paper("2605.18736"))

    old = db.get(Paper, 1)
    new = db.query(Paper).filter(Paper.version == "v2").one()
    assert old.is_latest_version is False
    assert new.is_latest_version is True
    assert new.title == "Updated Title"
    assert new.citation_count == 7
    assert result.created is True
    assert result.refreshed is True
    assert result.previous_version == "v1"
    assert result.latest_version == "v2"
    assert (
        db.query(PaperTask).filter_by(paper_id=new.id, task_id=1).one().source
        == "manual"
    )
    assert db.query(PaperMethod).filter_by(paper_id=new.id, method_id=1).one()
    assert (
        db.query(PaperRepository)
        .filter_by(paper_id=new.id, repository_id=1)
        .one()
        .is_official
        is True
    )
    authors = (
        db.query(Author.name)
        .join(PaperAuthor, PaperAuthor.author_id == Author.id)
        .filter(PaperAuthor.paper_id == new.id)
        .order_by(PaperAuthor.author_order)
        .all()
    )
    assert [row.name for row in authors] == ["Ada Lovelace", "Grace Hopper"]


def test_refresh_arxiv_paper_updates_existing_latest_without_duplicate(monkeypatch):
    db = _build_session()
    db.add(
        Paper(
            id=1,
            title="Old Title",
            abstract="Old abstract",
            arxiv_id="2605.18736",
            version="v2",
            is_latest_version=True,
            date_published=date(2026, 5, 20),
        )
    )
    db.add(Author(id=1, name="Old Author"))
    db.add(PaperAuthor(paper_id=1, author_id=1, author_order=1))
    db.commit()
    _patch_arxiv(monkeypatch, _metadata("v2", title="Retitled Paper"))

    result = asyncio.run(PaperService(db).refresh_arxiv_paper("2605.18736"))

    paper = db.get(Paper, 1)
    assert db.query(Paper).count() == 1
    assert paper.title == "Retitled Paper"
    assert paper.abstract == "Updated abstract"
    assert paper.is_latest_version is True
    assert result.created is False
    assert result.refreshed is False
    assert result.previous_version == "v2"
    assert result.latest_version == "v2"
    authors = (
        db.query(Author.name)
        .join(PaperAuthor, PaperAuthor.author_id == Author.id)
        .filter(PaperAuthor.paper_id == paper.id)
        .order_by(PaperAuthor.author_order)
        .all()
    )
    assert [row.name for row in authors] == ["Ada Lovelace", "Grace Hopper"]
