"""Chat request models, authentication, and admin evidence contracts."""

from __future__ import annotations

from pathlib import Path
import uuid

import pytest

from backend.config import Settings, get_settings
from backend.models.chat import (
    ChatRequest,
)
from backend.routers import chat as chat_router
from backend.routers.inference_billing import _status as inference_billing_status
from backend.services.chat_stream_service import (
    sanitized_exception_origin,
)


from backend.utils.auth import require_user
from backend.tests.chat.endpoint_harness import (
    _cookie_request,
)


def test_sanitized_exception_origin_reports_only_source_location():
    try:
        int(None)
    except TypeError as error:
        origin = sanitized_exception_origin(error)

    assert origin.startswith(
        f"{Path(__file__).name}:"
        "test_sanitized_exception_origin_reports_only_source_location:"
    )
    assert origin.rsplit(":", 1)[1].isdigit()
    assert "None" not in origin


def test_admin_qualification_evidence_is_content_free_and_bounded(monkeypatch):
    from backend.models.chat import ChatQualificationEvidenceRequest

    scope_id = uuid.uuid4()

    class EvidenceService:
        def __init__(self, db):
            assert db is not None

        def collect(self, **scope):
            assert scope["scope_id"] == scope_id
            return {
                "expected_users": 32,
                "admitted_turns": 32,
                "admission_denominator_events": 32,
                "terminal_turns": 32,
                "queued_states": 0,
                "stale_fences": 0,
                "executor_starts": 16,
                "duplicate_executor_starts": 0,
                "workspace_creates": 1,
                "workspace_reuses": 15,
                "workspace_evictions": 16,
                "billed_duration_ms": 4,
                "window_started_at_ms": 1,
                "window_ended_at_ms": 2,
                "source": "durable_qualification_records",
            }

    monkeypatch.setattr(
        chat_router, "ChatDurableQualificationEvidenceService", EvidenceService
    )

    class DB:
        def commit(self):
            pass

        def rollback(self):
            pass

    db = DB()
    response = chat_router.chat_qualification_evidence(
        ChatQualificationEvidenceRequest(scope_id=scope_id),
        db,
        Settings(environment="staging"),
    )

    assert response["executor_starts"] == 16
    assert "turn_id" not in response and "chat_session_id" not in response


def test_chat_qualification_evidence_request_accepts_json_uuid():
    from backend.models.chat import ChatQualificationEvidenceRequest

    scope_id = uuid.uuid4()

    request = ChatQualificationEvidenceRequest.model_validate(
        {"scope_id": str(scope_id)}
    )

    assert request.scope_id == scope_id


def test_chat_quota_configuration_and_billing_api_fields_are_removed():
    settings = get_settings()

    fields = type(settings).model_fields
    assert "chat_requests_per_minute" not in fields
    assert "chat_requests_per_day" not in fields
    assert "chat_openrouter_requests_per_minute" not in fields
    assert "chat_openrouter_requests_per_day" not in fields
    payload = inference_billing_status(
        settings, connected=True, is_pro=True
    ).model_dump()
    assert "requests_per_minute" not in payload
    assert "requests_per_day" not in payload


def test_reasoning_effort_request_contract_accepts_native_values_only():
    assert (
        ChatRequest(message="hello", client_message_id="request-1").reasoning_effort
        is None
    )
    assert (
        ChatRequest(
            message="hello",
            client_message_id="request-2",
            reasoning_effort="max",
        ).reasoning_effort
        == "max"
    )
    with pytest.raises(ValueError):
        ChatRequest(
            message="hello",
            client_message_id="request-3",
            reasoning_effort="xhigh",
        )


def test_require_user_returns_immutable_oauth_subject(monkeypatch, auth_sessions):
    from backend.routers import auth

    session_id = auth_sessions.issue("hf-immutable-123")
    monkeypatch.setattr(
        auth,
        "decode_session_cookie",
        lambda _token: {
            "sid": session_id,
            "sub": "hf-immutable-123",
            "username": "Alice",
        },
    )
    user = require_user(_cookie_request())
    assert user["source"] == "cookie"
    assert user["username"] == "alice"
    assert user["hf_user_id"] == "hf-immutable-123"
    assert user["hf_subject"] == "hf-immutable-123"


def test_require_user_rejects_legacy_cookie_without_subject(monkeypatch):
    from backend.routers import auth

    monkeypatch.setattr(
        auth, "decode_session_cookie", lambda _token: {"username": "alice"}
    )
    with pytest.raises(Exception) as exc_info:
        require_user(_cookie_request())
    assert exc_info.value.status_code == 401


def test_chat_request_is_strict_and_requires_message_and_client_id():
    with pytest.raises(ValueError):
        ChatRequest(message="hello")
    with pytest.raises(ValueError):
        ChatRequest(message=" ", client_message_id="id")
    with pytest.raises(ValueError):
        ChatRequest(message="hello", client_message_id="id", unknown=True)
    request = ChatRequest(message="hello", client_message_id="id")
    assert request.session_id is None
