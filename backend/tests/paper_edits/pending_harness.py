"""Database session and paper fixtures shared by pending-edit tests."""

import json

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.services.hf_organization_service import (
    HFOrganizationClient,
    HFOrganizationProfile,
)
from backend.models.database import (
    Base,
    PaperMethod,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
)
from backend.models.database import (
    Method as DBMethod,
)
from backend.models.database import (
    Paper as DBPaper,
)
from backend.models.database import (
    ProjectPage as DBProjectPage,
)
from backend.models.database import (
    Repository as DBRepository,
)
from backend.models.database import (
    Task as DBTask,
)


# SQLite stand-ins for PostgreSQL types, registered for every importer.
@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"


engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _register_jsonb_typeof(connection, _record):
    def jsonb_typeof(value):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        return "array" if isinstance(parsed, list) else "object"

    connection.create_function("jsonb_typeof", 1, jsonb_typeof)


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def paper_fixture(db_session):
    """Paper #1 with two tasks, one method, one repo, one project page, and an
    external source URL — enough state to exercise every edit_type."""

    db_session.add(
        DBPaper(
            id=1,
            title="Paper",
            abstract="Abstract",
            source="external",
            source_url="https://example.com/paper",
            arxiv_id=None,
        )
    )
    db_session.add_all(
        [
            DBTask(id=1, name="Task A", slug="task-a", level=0),
            DBTask(id=2, name="Task B", slug="task-b", level=0),
            DBTask(id=3, name="Task C", slug="task-c", level=0),
            DBMethod(id=10, name="Method X", slug="method-x"),
            DBMethod(id=11, name="Method Y", slug="method-y"),
            DBRepository(id=100, url="https://github.com/owner/repo"),
            # `is_official` lives on ProjectPage itself (not the junction),
            # so the snapshot reads it from this column.
            DBProjectPage(id=200, url="https://example.com/project", is_official=False),
        ]
    )
    db_session.add_all(
        [
            PaperTask(paper_id=1, task_id=1),
            PaperTask(paper_id=1, task_id=2),
            PaperMethod(paper_id=1, method_id=10),
            PaperRepository(paper_id=1, repository_id=100, is_official=True),
            PaperProjectPage(paper_id=1, project_page_id=200),
        ]
    )
    db_session.commit()


@pytest.fixture(autouse=True)
def hf_organizations(monkeypatch):
    """Hugging Face organization profiles by lowercase handle; none by default."""
    profiles: dict[str, HFOrganizationProfile] = {}
    monkeypatch.setattr(
        HFOrganizationClient,
        "fetch_profile",
        lambda self, hf_slug: profiles.get(hf_slug.lower()),
    )
    monkeypatch.setattr(
        HFOrganizationClient,
        "fetch_logo",
        lambda self, url: (b"\x89PNG hf avatar", "image/png"),
    )
    return profiles
