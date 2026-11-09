"""The admin list route serves the /submissions dashboard in one request."""

from __future__ import annotations

from backend.models.database import PendingPaperEdit
from backend.routers.pending_edits import list_pending_paper_edits
from backend.tests.paper_edits import pending_harness

db_session = pending_harness.db_session
paper_fixture = pending_harness.paper_fixture


def _row(
    status: str, edit_type: str = "tasks", paper_id: int | None = 1
) -> PendingPaperEdit:
    return PendingPaperEdit(
        paper_id=paper_id,
        hf_username="alice",
        is_author=False,
        edit_type=edit_type,
        proposed_payload={"task_ids": [1]} if edit_type == "tasks" else {"name": "New"},
        status=status,
    )


def _list(db, **overrides):
    params = dict(
        status_filter="pending",
        edit_type=None,
        paper_id=None,
        reviewed_by_kind=None,
        hf_username=None,
        limit=100,
        offset=0,
        _admin={},
        db=db,
    )
    return list_pending_paper_edits(**{**params, **overrides})


def test_all_statuses_newest_first_with_counts_and_paper(db_session, paper_fixture):
    db_session.add_all(
        [
            _row("approved"),
            _row("pending"),
            _row("rejected", edit_type="new_task", paper_id=None),
            _row("pending"),
        ]
    )
    db_session.commit()

    response = _list(db_session, status_filter="all", limit=3)

    assert response.count == 4
    assert [row.id for row in response.results] == [4, 3, 2]
    assert response.status_counts == {"approved": 1, "pending": 2, "rejected": 1}
    assert response.results[0].paper.title == "Paper"
    assert response.results[1].paper is None


def test_counts_follow_every_filter_but_status(db_session, paper_fixture):
    db_session.add_all(
        [
            _row("pending"),
            _row("approved"),
            _row("pending", edit_type="new_task", paper_id=None),
        ]
    )
    db_session.commit()

    response = _list(db_session, status_filter="approved", edit_type="tasks")

    assert [row.status for row in response.results] == ["approved"]
    assert response.status_counts == {"approved": 1, "pending": 1, "rejected": 0}
