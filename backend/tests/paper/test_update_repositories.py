"""Tests for paper-association repository deduplication."""

import pytest
from sqlalchemy import BigInteger, create_engine, create_mock_engine, inspect
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    PaperRepository,
)
from backend.models.database import (
    Paper as DBPaper,
)
from backend.models.database import (
    Repository as DBRepository,
)
from backend.services.paper_association_service import PaperAssociationService
from backend.services.repository_service import RepositoryService
from backend.utils.exceptions import PaperNotFoundError


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    tables = [
        DBPaper.__table__,
        DBRepository.__table__,
        PaperRepository.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=reversed(tables))


@pytest.fixture
def paper_with_duplicate_repo_urls(db_session):
    db_session.add(
        DBPaper(
            id=1,
            title="Paper",
            abstract="Abstract",
            arxiv_id="2104.01778",
        )
    )
    db_session.add_all(
        [
            DBRepository(
                id=10,
                url="https://github.com/pwc-1/Paper-8",
                owner="pwc-1",
                name="Paper-8",
            ),
            DBRepository(
                id=11,
                url="https://github.com/pwc-1/Paper-8/tree/main/audio_spectrogram",
                owner="pwc-1",
                name="Paper-8",
            ),
            DBRepository(
                id=12,
                url="https://github.com/huggingface/transformers",
                owner="huggingface",
                name="transformers",
            ),
        ]
    )
    db_session.add_all(
        [
            PaperRepository(paper_id=1, repository_id=10, is_official=True),
            PaperRepository(paper_id=1, repository_id=11, is_official=False),
        ]
    )
    db_session.commit()


def test_update_paper_repositories_dedupes_same_github_repo(
    db_session, paper_with_duplicate_repo_urls, monkeypatch
):
    service = PaperAssociationService(db_session, lambda *_args, **_kw: None)
    service.update_repositories(
        1,
        [
            {"url": "https://github.com/pwc-1/Paper-8", "is_official": True},
            {
                "url": "https://github.com/pwc-1/Paper-8/tree/main/audio_spectrogram",
                "is_official": False,
            },
            {
                "url": "https://github.com/huggingface/transformers",
                "is_official": False,
            },
        ],
    )

    links = (
        db_session.query(PaperRepository)
        .filter(PaperRepository.paper_id == 1)
        .order_by(PaperRepository.repository_id)
        .all()
    )
    assert len(links) == 2
    assert links[0].repository_id == 10
    assert links[0].is_official is True
    assert links[1].repository_id == 12
    assert links[1].is_official is False


def test_update_paper_repositories_marks_lone_repository_official(
    db_session, paper_with_duplicate_repo_urls, monkeypatch
):
    PaperAssociationService(db_session, lambda *_args, **_kw: None).update_repositories(
        1,
        [
            {
                "url": "https://github.com/huggingface/transformers",
                "is_official": False,
            }
        ],
    )

    link = db_session.query(PaperRepository).filter(PaperRepository.paper_id == 1).one()
    assert link.repository_id == 12
    assert link.is_official is True


def test_update_paper_repositories_can_keep_lone_repository_unofficial(
    db_session, paper_with_duplicate_repo_urls
):
    PaperAssociationService(db_session, lambda *_args, **_kw: None).update_repositories(
        1,
        [
            {
                "url": "https://github.com/huggingface/transformers",
                "is_official": False,
            }
        ],
        promote_lone_repository=False,
    )

    link = db_session.query(PaperRepository).filter(PaperRepository.paper_id == 1).one()
    assert link.repository_id == 12
    assert link.is_official is False


def test_update_paper_repositories_supports_outer_transaction_rollback(
    db_session, paper_with_duplicate_repo_urls
):
    PaperAssociationService(db_session, lambda *_args, **_kw: None).update_repositories(
        1,
        [
            {
                "url": "https://github.com/huggingface/transformers",
                "is_official": True,
            }
        ],
        commit=False,
    )

    db_session.rollback()

    repository_ids = {
        link.repository_id
        for link in db_session.query(PaperRepository)
        .filter(PaperRepository.paper_id == 1)
        .all()
    }
    assert repository_ids == {10, 11}


def test_first_repository_association_is_official_by_default(db_session):
    paper = DBPaper(
        id=2,
        title="Single Repository Paper",
        abstract="Abstract",
        arxiv_id="2601.00001",
    )
    repository = DBRepository(
        id=20,
        url="https://github.com/example/single-repository",
        owner="example",
        name="single-repository",
    )
    db_session.add_all([paper, repository])
    db_session.commit()

    RepositoryService(db_session).associate_repository_with_paper(
        paper_id="2",
        repository_id="20",
        is_official=False,
    )

    link = db_session.query(PaperRepository).filter(PaperRepository.paper_id == 2).one()
    assert link.is_official is True


def test_repository_for_missing_paper_leaves_no_orphan(db_session):
    with pytest.raises(PaperNotFoundError):
        RepositoryService(db_session).create_repository_for_paper(
            paper_id="404",
            url="https://github.com/example/orphan",
            skip_if_official_exists=False,
        )

    assert db_session.query(DBRepository).count() == 0


def test_repository_for_paper_is_created_and_linked(db_session):
    db_session.add(
        DBPaper(id=3, title="Linked Paper", abstract="Abstract", arxiv_id="2601.00003")
    )
    db_session.commit()

    repository = RepositoryService(db_session).create_repository_for_paper(
        paper_id="3",
        url="https://github.com/Example/Linked",
        is_official=False,
    )

    link = db_session.query(PaperRepository).filter(PaperRepository.paper_id == 3).one()
    assert link.repository_id == int(repository.id)
    assert link.is_official is True
    assert repository.url == "https://github.com/example/linked"


def test_date_order_index_keeps_sqlite_schema_creation_compatible(db_session):
    index_name = "idx_papers_date_published_desc_nulls_last"
    assert index_name not in {
        index["name"] for index in inspect(db_session.bind).get_indexes("papers")
    }

    statements = []
    postgres = create_mock_engine(
        "postgresql://",
        lambda statement, *args, **kwargs: statements.append(
            str(statement.compile(dialect=postgres.dialect))
        ),
    )
    DBPaper.__table__.create(postgres)
    assert (
        f"CREATE INDEX {index_name} ON papers (date_published DESC NULLS LAST)"
        in statements
    )
