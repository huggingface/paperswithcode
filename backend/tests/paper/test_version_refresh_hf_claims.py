import asyncio
from datetime import datetime, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.models.database import (
    Author,
    Base,
    Evaluation,
    Metric,
    Paper,
    PaperAuthor,
    PaperConference,
    PaperDataset,
    PaperHfArtifact,
    PaperMethod,
    PaperOrganization,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
)
from backend.services.arxiv_service import ArxivPaperMetadata
from backend.services.paper_version_refresh_service import PaperVersionRefreshService


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _compile_postgres_container_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


def _session(tmp_path, author_name: str):
    """v1 of a paper whose first author claimed it on HF as ``author_name``."""
    engine = create_engine(f"sqlite:///{tmp_path / 'refresh.db'}")
    models = (
        Paper,
        Author,
        PaperAuthor,
        PaperTask,
        PaperMethod,
        PaperRepository,
        PaperProjectPage,
        PaperHfArtifact,
        PaperConference,
        PaperOrganization,
        PaperDataset,
        Evaluation,
        Metric,
    )
    Base.metadata.create_all(bind=engine, tables=[m.__table__ for m in models])
    # Like production sessions, which never autoflush.
    db = sessionmaker(bind=engine, autoflush=False)()
    db.add_all(
        [
            Paper(
                id=1,
                title="Old",
                arxiv_id="2605.18736",
                version="v1",
                is_latest_version=True,
            ),
            Author(id=1, name=author_name, hf_username="ada", hf_id="hf-ada"),
            Author(id=2, name="Grace Hopper"),
        ]
    )
    db.add_all(
        [
            PaperAuthor(paper_id=1, author_id=1, author_order=1, claimed=True),
            PaperAuthor(paper_id=1, author_id=2, author_order=2),
        ]
    )
    db.commit()
    return db


def _patch(monkeypatch, fetch):
    class FakeArxivService:
        async def get_paper_metadata(self, arxiv_id: str):
            return ArxivPaperMetadata(
                arxiv_id=arxiv_id,
                version="v2",
                title="New",
                abstract="",
                authors=["Ada Lovelace", "Grace Hopper"],
                published=datetime(2026, 5, 20, tzinfo=timezone.utc),
                updated=datetime(2026, 5, 21, tzinfo=timezone.utc),
                pdf_url=f"https://arxiv.org/pdf/{arxiv_id}v2",
                abs_url=f"https://arxiv.org/abs/{arxiv_id}",
                categories=None,
                primary_category="cs.LG",
            )

    monkeypatch.setattr("backend.services.arxiv_service.ArxivService", FakeArxivService)
    monkeypatch.setattr(
        "backend.services.paper_version_refresh_service._fetch_hf_paper", fetch
    )


def _refresh_links(db):
    asyncio.run(
        PaperVersionRefreshService(
            db, paper_factory=lambda _paper_id: None
        ).refresh_arxiv_paper("2605.18736")
    )
    return [
        tuple(row)
        for row in db.query(
            Author.id, Author.name, PaperAuthor.author_order, PaperAuthor.claimed
        )
        .join(PaperAuthor, PaperAuthor.author_id == Author.id)
        .join(Paper, Paper.id == PaperAuthor.paper_id)
        .filter(Paper.version == "v2")
        .order_by(PaperAuthor.author_order)
    ]


def test_refresh_keeps_a_claim_under_the_authors_former_name(
    monkeypatch, tmp_path
) -> None:
    # Ada's row took her new HF full name; arXiv still prints the former one.
    db = _session(tmp_path, "Ada King")
    fetched = []

    async def fetch(arxiv_id):
        fetched.append(arxiv_id)
        return {
            "id": arxiv_id,
            "authors": [
                {
                    "name": "Ada Lovelace",
                    "status": "claimed_verified",
                    "user": {"_id": "hf-ada", "user": "ada", "fullname": "Ada King"},
                },
                {"name": "Grace Hopper"},
            ],
        }

    _patch(monkeypatch, fetch)

    assert _refresh_links(db) == [
        (1, "Ada King", 1, True),
        (2, "Grace Hopper", 2, False),
    ]
    assert fetched == ["2605.18736"]


def test_refresh_skips_hf_when_every_claim_keeps_its_name(
    monkeypatch, tmp_path
) -> None:
    db = _session(tmp_path, "Ada Lovelace")

    async def fetch(_arxiv_id):
        raise AssertionError("no claim was dropped")

    _patch(monkeypatch, fetch)

    assert _refresh_links(db) == [
        (1, "Ada Lovelace", 1, True),
        (2, "Grace Hopper", 2, False),
    ]


def test_refresh_without_hf_drops_only_the_unmatched_claim(
    monkeypatch, tmp_path
) -> None:
    db = _session(tmp_path, "Ada King")

    async def fetch(_arxiv_id):
        return None

    _patch(monkeypatch, fetch)

    links = _refresh_links(db)
    assert [(name, order, claimed) for _id, name, order, claimed in links] == [
        ("Ada Lovelace", 1, False),
        ("Grace Hopper", 2, False),
    ]
