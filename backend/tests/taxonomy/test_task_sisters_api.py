"""
Tests for explicit, ordered sister tasks on the bundled task page.

The "Sister Tasks" sidebar is driven by the `task_sister_tasks` table, not by
`area_id`. A task page returns exactly the sisters configured for it, in
ascending `display_order`, even when other visible tasks share its area.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import create_app
from backend.database.connection import get_database_session
from backend.models.database import (
    Base,
    Area as DBArea,
    Task as DBTask,
    TaskSisterTask as DBTaskSisterTask,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    """SQLite cannot autoincrement BIGINT; rewrite to INTEGER for tests."""
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
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as test_client:
        seed_agents_with_sisters(TestingSessionLocal())
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def seed_agents_with_sisters(db):
    """Seed an `agents` page with three explicit, ordered sisters.

    `agents` shares an area with a distractor task (`other-general`) that is
    NOT a configured sister, while two of its configured sisters live in a
    different area entirely. The page must return only the configured sisters,
    in display_order, regardless of area.
    """
    general = DBArea(id=1, name="General")
    language = DBArea(id=2, name="Language")
    db.add_all([general, language])

    agents = DBTask(id=10, name="Agents", slug="agents", area_id=1, level=0)
    coding_agents = DBTask(
        id=11, name="Coding Agents", slug="coding-agents", area_id=1, level=0
    )
    computer_use = DBTask(
        id=12,
        name="Computer Use Agents",
        slug="computer-use-agents",
        area_id=1,
        level=0,
    )
    language_modeling = DBTask(
        id=13,
        name="Language Modeling",
        slug="language-modeling",
        area_id=2,
        level=0,
    )
    # Same area as agents but deliberately NOT a configured sister.
    distractor = DBTask(
        id=14, name="Other General", slug="other-general", area_id=1, level=0
    )
    db.add_all([agents, coding_agents, computer_use, language_modeling, distractor])

    # Insert sister rows out of display_order to prove the API sorts them.
    db.add_all(
        [
            DBTaskSisterTask(task_id=10, sister_task_id=13, display_order=2),
            DBTaskSisterTask(task_id=10, sister_task_id=11, display_order=0),
            DBTaskSisterTask(task_id=10, sister_task_id=12, display_order=1),
        ]
    )
    db.commit()
    db.close()


def test_agents_page_returns_explicit_sisters_in_order(client):
    response = client.get("/api/v1/tasks/agents/page")

    assert response.status_code == 200
    data = response.json()

    sister_slugs = [s["slug"] for s in data["sisters"]]
    assert sister_slugs == [
        "coding-agents",
        "computer-use-agents",
        "language-modeling",
    ]

    # The same-area distractor must NOT appear just because it shares an area.
    assert "other-general" not in sister_slugs


def test_task_without_sisters_returns_empty(client):
    """A task with no configured sisters returns an empty sister list, even
    though it shares an area with other tasks."""
    response = client.get("/api/v1/tasks/other-general/page")

    assert response.status_code == 200
    assert response.json()["sisters"] == []


if __name__ == "__main__":
    pytest.main([__file__])
