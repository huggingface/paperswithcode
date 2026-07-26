"""
Regression tests for `PendingEditService.submit()` no-op detection.

Submissions that match the paper's current state must be rejected with a
`PendingEditError` so the /submissions admin dashboard isn't cluttered with
"empty" review cards. See `backend/services/pending_edit_service.py`.
"""

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    PendingPaperEdit,
    ProjectPage as DBProjectPage,
    Repository as DBRepository,
    Task as DBTask,
)
from backend.services.pending_edit_service import (
    PendingEditError,
    PendingEditService,
)


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


def _no_rows_created(db_session) -> None:
    assert db_session.query(PendingPaperEdit).count() == 0


def test_submit_tasks_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="tasks",
            proposed_payload={"task_ids": [2, 1]},  # same set, different order
        )
    _no_rows_created(db_session)


def test_submit_tasks_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1, 2, 3]},
    )
    assert row.id is not None
    assert row.status == "pending"
    assert row.proposed_payload == {"task_ids": [1, 2, 3]}


def test_submit_methods_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="methods",
            proposed_payload={"method_ids": [10]},
        )
    _no_rows_created(db_session)


def test_submit_methods_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="methods",
        proposed_payload={"method_ids": [10, 11]},
    )
    assert row.id is not None


def test_submit_directory_taxonomy_suggestion_without_paper_succeeds(db_session):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={
            "name": "Long-context Retrieval",
            "description": "Retrieving evidence from very long contexts.",
        },
    )

    assert row.id is not None
    assert row.paper_id is None
    assert row.is_author is False
    assert row.current_payload == {}

    reviewed = service.approve(edit_id=row.id, reviewer_username="admin")
    assert reviewed.status == "approved"


def test_submit_directory_conference_suggestion_without_paper_succeeds(db_session):
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_conference",
        proposed_payload={
            "name": "Conference on Long-context Research 2027",
            "dates": " May 3–7, 2027 ",
            "venue": " Vancouver Convention Centre ",
            "url": "https://example.org/conference",
        },
    )

    assert row.id is not None
    assert row.paper_id is None
    assert row.proposed_payload == {
        "name": "Conference on Long-context Research 2027",
        "dates": "May 3–7, 2027",
        "venue": "Vancouver Convention Centre",
        "url": "https://example.org/conference",
    }


def test_submit_directory_conference_suggestion_rejects_invalid_url(db_session):
    with pytest.raises(PendingEditError, match="must start with http"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="new_conference",
            proposed_payload={
                "name": "Conference on Long-context Research 2027",
                "url": "example.org/conference",
            },
        )
    _no_rows_created(db_session)


def test_submit_non_taxonomy_edit_without_paper_rejects(db_session):
    with pytest.raises(PendingEditError, match="paper_id is required"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="tasks",
            proposed_payload={"task_ids": [1]},
        )
    _no_rows_created(db_session)


def test_submit_repositories_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="repositories",
            proposed_payload={
                "repositories": [
                    {"url": "https://github.com/owner/repo", "is_official": True},
                ]
            },
        )
    _no_rows_created(db_session)


def test_submit_repositories_is_official_flip_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="repositories",
        proposed_payload={
            "repositories": [
                {"url": "https://github.com/owner/repo", "is_official": False},
            ]
        },
    )
    assert row.id is not None


def test_submit_project_pages_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="project_pages",
            proposed_payload={
                "project_pages": [
                    {"url": "https://example.com/project", "is_official": False},
                ]
            },
        )
    _no_rows_created(db_session)


def test_submit_source_url_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="source_url",
            # Same URL with surrounding whitespace — should still be a no-op.
            proposed_payload={"source_url": "  https://example.com/paper  "},
        )
    _no_rows_created(db_session)


def test_submit_source_url_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="source_url",
        proposed_payload={"source_url": "https://example.com/paper/v2"},
    )
    assert row.id is not None
    assert row.proposed_payload == {"source_url": "https://example.com/paper/v2"}


def test_submit_hf_artifacts_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="hf_artifacts",
            proposed_payload={
                "hf_models": [],
                "hf_datasets": [],
                "hf_spaces": [],
            },
        )
    _no_rows_created(db_session)


def test_submit_hf_artifacts_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="hf_artifacts",
        proposed_payload={
            "hf_models": ["https://huggingface.co/org/model-a"],
            "hf_datasets": ["https://huggingface.co/datasets/org/data-a"],
            "hf_spaces": ["https://huggingface.co/spaces/org/demo-a"],
        },
    )
    assert row.id is not None
    assert row.proposed_payload["hf_models"] == [
        "https://huggingface.co/org/model-a",
    ]


def test_submit_hf_artifacts_invalid_bucket_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="not a Hugging Face model"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="hf_artifacts",
            proposed_payload={
                "hf_models": ["https://huggingface.co/datasets/org/data-a"],
                "hf_datasets": [],
                "hf_spaces": [],
            },
        )
    _no_rows_created(db_session)


def test_submit_tasks_empty_against_empty_paper_rejects(db_session):
    db_session.add(
        DBPaper(
            id=2,
            title="P2",
            abstract=None,
            source="external",
            source_url="https://example.com/p2",
            arxiv_id=None,
        )
    )
    db_session.commit()

    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=2,
            hf_username="alice",
            edit_type="tasks",
            proposed_payload={"task_ids": []},
        )
    _no_rows_created(db_session)


def test_submit_evaluations_create_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="evaluations",
        proposed_payload={
            "operations": [
                {
                    "op": "create",
                    "data": {
                        "task_id": 1,
                        "dataset_id": 99,
                        "model_name": "TestModel",
                        "metrics": {"Accuracy": "91.2"},
                        "best_metric": "Accuracy",
                        "is_open": True,
                    },
                }
            ]
        },
    )
    assert row.id is not None
    assert row.status == "pending"
    assert row.proposed_payload["operations"][0]["op"] == "create"
