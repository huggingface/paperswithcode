from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.models.database import PendingPaperEdit
from backend.routers import profiles
from backend.services.user_profile_service import (
    PrivateSubmissionProjection,
    ProfilePrivateView,
    UserProfileError,
    UserProfileService,
)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/profiles/alice",
            "headers": [],
            "query_string": b"",
            "scheme": "https",
            "server": ("paperswithcode.co", 443),
            "client": ("127.0.0.1", 1234),
        }
    )


class _PendingSubmissionQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.ordering = []
        self.limit_value = None

    def filter(self, *criteria):
        self.filters.extend(criteria)
        return self

    def order_by(self, *ordering):
        self.ordering.extend(ordering)
        return self

    def limit(self, limit):
        self.limit_value = limit
        return self

    def all(self):
        return self.rows[: self.limit_value]


class _PrivateViewDb:
    def __init__(self, rows):
        self.query_calls = 0
        self.query_result = _PendingSubmissionQuery(rows)

    def query(self, entity):
        assert entity is PendingPaperEdit
        self.query_calls += 1
        return self.query_result


def _submission_row(
    row_id: int,
    *,
    status: str = "pending",
    proposed_payload: dict | None = None,
):
    created_at = datetime(2026, 8, 11, tzinfo=UTC) - timedelta(minutes=row_id)
    return SimpleNamespace(
        id=row_id,
        edit_type="tasks",
        status=status,
        proposed_payload=proposed_payload or {"task_ids": [row_id]},
        applied_payload={"task_ids": [row_id]} if status == "approved" else None,
        result_entity_type="paper" if status == "approved" else None,
        result_entity_id=str(row_id) if status == "approved" else None,
        user_review_reason="Reviewed" if status != "pending" else None,
        created_at=created_at,
        reviewed_at=created_at if status != "pending" else None,
        source_ip="192.0.2.1",
        admin_note="internal-only",
        reviewed_by="admin",
        conflict_payload={"secret": True},
    )


@pytest.mark.parametrize("viewer_hf_subject", [None, "hf-bob"])
def test_private_view_does_not_query_or_disclose_for_non_owner(viewer_hf_subject):
    class NoQueryDb:
        def query(self, *_args):
            raise AssertionError("non-owner profile views must not query submissions")

    view = UserProfileService(NoQueryDb()).private_view(
        profile_hf_subject="hf-alice",
        viewer_hf_subject=viewer_hf_subject,
    )

    assert view == ProfilePrivateView(is_owner=False, submissions=())


def test_private_view_is_bounded_ordered_and_preserves_exact_owner_projection():
    raw_payload = {
        "image": {
            "file_name": "private.png",
            "mime_type": "image/png",
            "data_url": "data:image/png;base64,cHJpdmF0ZQ==",
        }
    }
    rows = [
        _submission_row(201, status="pending", proposed_payload=raw_payload),
        _submission_row(200, status="approved"),
        _submission_row(199, status="rejected"),
        *[_submission_row(row_id) for row_id in range(198, 0, -1)],
    ]
    db = _PrivateViewDb(rows)

    view = UserProfileService(db).private_view(
        profile_hf_subject="hf-alice",
        viewer_hf_subject="hf-alice",
    )

    assert view.is_owner is True
    assert db.query_calls == 1
    assert db.query_result.limit_value == 200
    assert len(db.query_result.filters) == 1
    assert str(db.query_result.filters[0].left) == "pending_paper_edits.hf_subject"
    assert db.query_result.filters[0].right.value == "hf-alice"
    assert [str(value) for value in db.query_result.ordering] == [
        "pending_paper_edits.created_at DESC"
    ]
    assert len(view.submissions) == 200
    assert [row.id for row in view.submissions[:3]] == [201, 200, 199]
    assert [row.status for row in view.submissions[:3]] == [
        "pending",
        "approved",
        "rejected",
    ]
    assert view.submissions[0].proposed_payload is raw_payload
    assert [field.name for field in fields(PrivateSubmissionProjection)] == [
        "id",
        "edit_type",
        "status",
        "proposed_payload",
        "applied_payload",
        "result_entity_type",
        "result_entity_id",
        "review_reason",
        "created_at",
        "reviewed_at",
    ]
    with pytest.raises(FrozenInstanceError):
        view.submissions[0].status = "approved"


def test_profile_router_maps_exact_owner_response_without_rewriting_payload(
    monkeypatch,
):
    created_at = datetime(2026, 8, 11, tzinfo=UTC)
    raw_payload = {"image": {"data_url": "data:image/png;base64,cHJpdmF0ZQ=="}}
    submission = PrivateSubmissionProjection(
        id=42,
        edit_type="new_task",
        status="approved",
        proposed_payload=raw_payload,
        applied_payload={"name": "Task"},
        result_entity_type="task",
        result_entity_id="7",
        review_reason="Accepted",
        created_at=created_at,
        reviewed_at=created_at,
    )
    calls = []

    class Service:
        def resolve(self, username):
            calls.append(("resolve", username))
            return SimpleNamespace(
                hf_subject="hf-alice", current_username="alice"
            ), False

        def private_view(self, **kwargs):
            calls.append(("private", kwargs))
            return ProfilePrivateView(True, (submission,))

        def contribution_calendar(self, hf_subject):
            calls.append(("calendar", hf_subject))
            return {
                "start_date": "2025-08-12",
                "end_date": "2026-08-11",
                "total_count": 0,
                "results": [],
            }

    service = Service()
    monkeypatch.setattr(profiles, "UserProfileService", lambda _db: service)
    monkeypatch.setattr(
        profiles,
        "decode_request_session",
        lambda _request: {"sub": "hf-alice", "username": "renamed-alice"},
    )

    response = profiles.get_profile("Alice", _request(), object())

    assert list(response) == [
        "username",
        "redirected_from_alias",
        "calendar",
        "is_owner",
        "submissions",
    ]
    assert response["username"] == "alice"
    assert response["redirected_from_alias"] is False
    assert response["is_owner"] is True
    assert response["submissions"] == [
        {
            "id": 42,
            "edit_type": "new_task",
            "status": "approved",
            "proposed_payload": raw_payload,
            "applied_payload": {"name": "Task"},
            "result_entity_type": "task",
            "result_entity_id": "7",
            "review_reason": "Accepted",
            "created_at": created_at,
            "reviewed_at": created_at,
        }
    ]
    assert response["submissions"][0]["proposed_payload"] is raw_payload
    assert calls == [
        ("resolve", "Alice"),
        (
            "private",
            {
                "profile_hf_subject": "hf-alice",
                "viewer_hf_subject": "hf-alice",
            },
        ),
        ("calendar", "hf-alice"),
    ]


def test_profile_router_keeps_calendar_public_and_private_rows_empty(monkeypatch):
    class Service:
        def resolve(self, _username):
            return SimpleNamespace(
                hf_subject="hf-alice", current_username="alice"
            ), False

        def private_view(self, **kwargs):
            assert kwargs == {
                "profile_hf_subject": "hf-alice",
                "viewer_hf_subject": None,
            }
            return ProfilePrivateView(False, ())

        def contribution_calendar(self, hf_subject):
            assert hf_subject == "hf-alice"
            return {
                "total_count": 3,
                "results": [{"date": "2026-08-11", "paper_count": 3}],
            }

    monkeypatch.setattr(profiles, "UserProfileService", lambda _db: Service())
    monkeypatch.setattr(
        profiles, "decode_request_session", lambda _request: {"sub": 123}
    )

    response = profiles.get_profile("alice", _request(), object())

    assert response["calendar"]["total_count"] == 3
    assert response["is_owner"] is False
    assert response["submissions"] == []


def test_profile_alias_redirects_before_session_or_private_work(monkeypatch):
    class Service:
        def resolve(self, username):
            assert username == "old-alice"
            return SimpleNamespace(
                hf_subject="hf-alice", current_username="alice"
            ), True

        def private_view(self, **_kwargs):
            pytest.fail("alias redirect must not build the private view")

        def contribution_calendar(self, _hf_subject):
            pytest.fail("alias redirect must not query the calendar")

    monkeypatch.setattr(profiles, "UserProfileService", lambda _db: Service())
    monkeypatch.setattr(
        profiles,
        "decode_request_session",
        lambda _request: pytest.fail("alias redirect must not decode the session"),
    )

    response = profiles.get_profile("old-alice", _request(), object())

    assert response.status_code == 308
    assert response.headers["location"] == "/api/v1/profiles/alice"


@pytest.mark.parametrize(
    "message",
    [
        "Invalid Hugging Face username",
        "Reserved profile route",
        "Profile not found",
    ],
)
def test_profile_resolution_errors_keep_exact_404_details(monkeypatch, message):
    class Service:
        def resolve(self, _username):
            raise UserProfileError(message)

    monkeypatch.setattr(profiles, "UserProfileService", lambda _db: Service())

    with pytest.raises(HTTPException) as exc_info:
        profiles.get_profile("missing", _request(), object())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == message
