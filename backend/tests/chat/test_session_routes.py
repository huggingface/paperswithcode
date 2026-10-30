"""Chat session, availability, deletion, archiving, quota, and feedback routes."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import Response

from backend.config import Settings, get_settings
from backend.main import create_app
from backend.models.chat import (
    ChatBrowserLatencyRequest,
)
from backend.routers import chat as chat_router
from backend.services.chat_sandbox_service import SandboxCleanupUnverified
from backend.services.chat_session_service import (
    ChatDeletionReceipt,
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
)


from backend.utils.auth import require_user


def test_browser_latency_request_is_strict_bounded_and_nonempty():
    with pytest.raises(ValueError):
        ChatBrowserLatencyRequest()
    with pytest.raises(ValueError):
        ChatBrowserLatencyRequest(submission_to_stream_start_ms=-1)
    with pytest.raises(ValueError):
        ChatBrowserLatencyRequest(submission_to_stream_start_ms=1, unexpected="content")
    payload = ChatBrowserLatencyRequest(
        submission_to_stream_start_ms=12.5,
        terminal_classification="complete",
    )
    assert payload.submission_to_stream_start_ms == 12.5


def test_cancel_endpoint_uses_owner_checked_active_turn(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls = []

    class DB:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Service:
        def __init__(self, _db, _settings):
            pass

        def request_legacy_cancel(self, owner, requested_session_id):
            assert owner.hf_user_id == "owner-1"
            assert requested_session_id == session_id
            calls.append("fence")
            return turn_id

    class Manager:
        async def cancel(self, requested_session_id, requested_turn_id):
            calls.append((requested_session_id, requested_turn_id))
            return True

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(
        chat_router, "shared_sandbox_manager", lambda _settings: Manager()
    )
    response = asyncio.run(
        chat_router.cancel_active_turn(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=DB(),
            settings=object(),
        )
    )

    assert response.status_code == 204
    assert calls == ["fence", "commit", (session_id, turn_id)]


def test_session_detail_never_caches_private_paper_metadata(monkeypatch):
    session_id = uuid.uuid4()

    class SessionService:
        def __init__(self, *_args):
            pass

        def get_session(self, *_args):
            return SimpleNamespace(id=session_id, transcript_status="complete"), []

    class PaperService:
        def __init__(self, *_args):
            pass

        def get_descriptor(self, *_args):
            return {"artifact_id": str(uuid.uuid4())}

    class Summary:
        def model_dump(self):
            return {}

    class Detail:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(chat_router, "ChatSessionService", SessionService)
    monkeypatch.setattr(chat_router, "LatexPaperService", PaperService)
    monkeypatch.setattr(chat_router, "_summary", lambda _session: Summary())
    monkeypatch.setattr(chat_router, "ChatSessionDetail", Detail)
    response = Response()

    chat_router.get_session(
        session_id,
        response,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=object(),
    )

    assert response.headers["Cache-Control"] == "private, no-store"


def test_create_session_fails_closed_when_public_admission_is_disabled():
    settings = Settings(chat_public_admission_enabled=False)

    with pytest.raises(Exception) as exc_info:
        chat_router.create_session(
            SimpleNamespace(selected_model=None),
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=SimpleNamespace(),
            settings=settings,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "chat_temporarily_disabled"


def test_admin_harness_session_is_staging_only_and_returns_neutral_summary(
    monkeypatch,
):
    captured = {}
    session = SimpleNamespace(
        id=uuid.uuid4(),
        title="New chat",
        title_status="pending",
        selected_model="model",
        reasoning_effort="low",
        execution_backend="modal_cli",
        agent_harness="pi",
        web_search_enabled=False,
        message_count=0,
        active_turn_id=None,
        active_turn_expires_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        archived_at=None,
    )

    class Service:
        def __init__(self, _db, _settings):
            pass

        def create_session(self, owner, model, effort, **options):
            captured.update(owner=owner, model=model, effort=effort, **options)
            return session

    db = SimpleNamespace(
        commit=lambda: None, refresh=lambda _row: None, rollback=lambda: None
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "require_pi_release_window", lambda: None)
    response = chat_router.create_admin_harness_session(
        chat_router.AdminCreateHarnessSession(
            agent_harness="pi", selected_model="model", reasoning_effort="low"
        ),
        admin={"source": "cookie", "hf_subject": "admin-subject", "username": "admin"},
        db=db,
        settings=Settings(environment="staging"),
    )

    assert captured["owner"].hf_user_id == "admin-subject"
    assert captured["agent_harness_override"] == "pi"
    assert "agent_harness" not in response.model_dump()

    with pytest.raises(Exception) as exc_info:
        chat_router.create_admin_harness_session(
            chat_router.AdminCreateHarnessSession(agent_harness="pi"),
            admin={"source": "cookie", "hf_subject": "admin-subject"},
            db=db,
            settings=Settings(environment="production"),
        )
    assert exc_info.value.status_code == 404


def test_chat_availability_is_public(monkeypatch):
    settings = Settings(
        _env_file=None,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        chat_default_backend="local_mcp",
        chat_paper_mentions_enabled=True,
        native_pdf_reader_enabled=True,
        paper_reader_chat_enabled=True,
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_router, "web_search_available", lambda _settings: True)
    app = FastAPI()
    app.include_router(chat_router.router, prefix="/api/v1")

    with TestClient(app) as client:
        response = client.get("/api/v1/chat/availability")

    assert response.status_code == 200
    assert response.json()["web_search_available"] is True
    assert response.json()["native_pdf_reader_enabled"] is True
    assert response.json()["paper_reader_chat_enabled"] is True
    assert response.json()["paper_reader_selection_enabled"] is False


def test_chat_availability_maps_spend_rejection_to_content_free_paused_state(
    monkeypatch,
):
    settings = Settings(
        _env_file=None,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        chat_default_backend="modal_cli",
        chat_sandbox_spend_enforcement_enabled=True,
        chat_paper_mentions_enabled=True,
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_router, "web_search_available", lambda _settings: True)

    monkeypatch.setattr(
        chat_router, "chat_sandbox_spend_available", lambda *_a, **_k: False
    )

    assert chat_router.chat_availability() == {
        "status": "paused",
        "reason": "chat_temporarily_disabled",
        "expected_recovery_at": None,
        "paper_mentions_enabled": True,
        "web_search_available": False,
        "native_pdf_reader_enabled": False,
        "paper_reader_chat_enabled": False,
        "paper_reader_selection_enabled": False,
        "paper_reader_citations_enabled": False,
        "paper_artifacts_enabled": False,
    }


def test_sandbox_spend_admin_status_preserves_qualification_scope(monkeypatch):
    settings = Settings(_env_file=None, environment="staging")
    seen: list[str] = []
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(
        chat_router,
        "chat_sandbox_spend_status",
        lambda scoped, **_kwargs: seen.append(scoped.environment) or {"ok": True},
    )

    assert chat_router.chat_sandbox_spend("staging-q-pool") == {"ok": True}
    assert seen == ["staging-q-pool"]

    with pytest.raises(Exception) as exc_info:
        chat_router.chat_sandbox_spend("production-q-pool")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Unknown qualification"


def test_openrouter_key_api_is_absent_when_chat_is_disabled():
    with pytest.raises(Exception) as exc_info:
        chat_router.get_openrouter_key_status(
            user={"hf_user_id": "owner-1"},
            db=SimpleNamespace(),
            settings=Settings(environment="production", chat_enabled=False),
        )

    assert exc_info.value.status_code == 404


def test_production_openrouter_key_api_is_available_when_chat_is_enabled(monkeypatch):
    class FakeService:
        def __init__(self, *_args):
            pass

        def status(self, owner_id):
            assert owner_id == "owner-1"
            return SimpleNamespace(
                public_dict=lambda: {
                    "connected": False,
                    "verified_at": None,
                    "fallback_enabled": False,
                }
            )

    monkeypatch.setattr(chat_router, "OpenRouterBYOKService", FakeService)
    assert chat_router.get_openrouter_key_status(
        user={"hf_user_id": "owner-1"},
        db=SimpleNamespace(),
        settings=Settings(environment="production", chat_enabled=True),
    ) == {
        "connected": False,
        "verified_at": None,
        "fallback_enabled": False,
    }


def test_delete_session_reports_success_only_after_durable_and_workspace_verification(
    monkeypatch,
):
    session_id = uuid.uuid4()
    receipt = ChatDeletionReceipt(session_id, "sb-1", None, None, None)
    events: list[str] = []

    class DB:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def delete_session(self, *_args):
            # Paper deletion makes blocking provider calls: never on the loop.
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
            events.append("delete")
            return receipt

        def deletion_complete(self, requested):
            assert requested == receipt
            events.append("verify-db")
            return True

    class Manager:
        def __init__(self, _settings):
            pass

        async def cleanup_deleted(self, sandbox_id, snapshot_id):
            assert (sandbox_id, snapshot_id) == ("sb-1", None)
            events.append("verify-workspace")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "SandboxSessionManager", Manager)

    response = asyncio.run(
        chat_router.delete_session(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=DB(),
            settings=Settings(),
        )
    )

    assert response.status_code == 204
    assert events == ["delete", "verify-workspace", "commit", "verify-db"]


def test_deletion_verifier_uses_the_persisted_share_foreign_key():
    class EmptyResult:
        @staticmethod
        def first():
            return None

    class EmptyDB:
        @staticmethod
        def execute(_query):
            return EmptyResult()

    service = ChatSessionService(EmptyDB(), Settings())
    receipt = ChatDeletionReceipt(uuid.uuid4(), None, None, None, None)

    assert service.deletion_complete(receipt) is True


@pytest.mark.parametrize("failure", ["database", "workspace"])
def test_delete_session_never_reports_success_when_removal_is_unverified(
    monkeypatch, failure: str
):
    session_id = uuid.uuid4()
    receipt = ChatDeletionReceipt(session_id, "sb-1", None, None, None)

    class DB:
        def commit(self):
            pass

        def rollback(self):
            pass

    class Service:
        def __init__(self, *_args):
            pass

        def delete_session(self, *_args):
            return receipt

        def deletion_complete(self, _receipt):
            return failure != "database"

    class Manager:
        def __init__(self, _settings):
            pass

        async def cleanup_deleted(self, *_args):
            if failure == "workspace":
                raise SandboxCleanupUnverified("uncertain")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "SandboxSessionManager", Manager)

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            chat_router.delete_session(
                session_id,
                user={"hf_user_id": "owner-1", "username": "owner"},
                db=DB(),
                settings=Settings(),
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "chat_deletion_unverified"


def test_delete_session_workspace_failure_rolls_back_before_commit(monkeypatch):
    session_id = uuid.uuid4()
    receipt = ChatDeletionReceipt(session_id, "sb-1", None, None, None)
    events: list[str] = []

    class DB:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def delete_session(self, *_args):
            events.append("delete")
            return receipt

    class Manager:
        def __init__(self, _settings):
            pass

        async def cleanup_deleted(self, *_args):
            events.append("verify-workspace")
            raise SandboxCleanupUnverified("uncertain")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "SandboxSessionManager", Manager)

    with pytest.raises(Exception):
        asyncio.run(
            chat_router.delete_session(
                session_id,
                user={"hf_user_id": "owner-1", "username": "owner"},
                db=DB(),
                settings=Settings(),
            )
        )

    assert events == ["delete", "verify-workspace", "rollback"]


def test_archive_old_sessions_endpoint_commits_owner_scoped_archive(monkeypatch):
    calls = []

    class Service:
        def __init__(self, _db, _settings):
            pass

        def archive_old_sessions(self, owner, *, days):
            calls.append((owner.hf_user_id, days))
            return 7

    db = SimpleNamespace(commit=lambda: calls.append("commit"), rollback=lambda: None)
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)

    response = chat_router.archive_old_sessions(
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=db,
        settings=object(),
    )

    assert response.archived_count == 7
    assert calls == [("owner-1", 30), "commit"]


def test_archive_old_sessions_marks_selected_rows_without_deleting():
    rows = [SimpleNamespace(archived_at=None), SimpleNamespace(archived_at=None)]

    class Result:
        def scalars(self):
            return rows

    class FakeDB:
        def __init__(self):
            self.calls = 0
            self.flushed = False

        def execute(self, _query):
            self.calls += 1
            return None if self.calls == 1 else Result()

        def flush(self):
            self.flushed = True

    db = FakeDB()
    archived = ChatSessionService(db, object()).archive_old_sessions(
        ChatOwner(hf_user_id="owner-1", hf_username="owner")
    )

    assert archived == 2
    assert db.flushed
    assert all(row.archived_at is not None for row in rows)


def test_archive_oldest_sessions_endpoint_commits_owner_scoped_archive(monkeypatch):
    calls = []

    class Service:
        def __init__(self, _db, _settings):
            pass

        def archive_oldest_sessions(self, owner, *, limit):
            calls.append((owner.hf_user_id, limit))
            return 50

    db = SimpleNamespace(commit=lambda: calls.append("commit"), rollback=lambda: None)
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)

    response = chat_router.archive_oldest_sessions(
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=db,
        settings=object(),
    )

    assert response.archived_count == 50
    assert calls == [("owner-1", 50), "commit"]


def test_archive_oldest_sessions_marks_at_most_selected_rows_without_deleting():
    rows = [SimpleNamespace(archived_at=None) for _ in range(50)]

    class Result:
        def scalars(self):
            return rows

    class FakeDB:
        def __init__(self):
            self.calls = 0
            self.flushed = False

        def execute(self, _query):
            self.calls += 1
            return None if self.calls == 1 else Result()

        def flush(self):
            self.flushed = True

    db = FakeDB()
    archived = ChatSessionService(db, object()).archive_oldest_sessions(
        ChatOwner(hf_user_id="owner-1", hf_username="owner"), limit=50
    )

    assert archived == 50
    assert db.flushed
    assert all(row.archived_at is not None for row in rows)


def test_chat_session_quota_error_states_the_exact_limit():
    class FakeDB:
        scalar_query = ""

        def execute(self, _query):
            return None

        def scalar(self, query):
            self.scalar_query = str(query)
            return 100

    db = FakeDB()
    settings = SimpleNamespace(
        chat_model_choices=[{"id": "model"}],
        chat_model_routes={"model": "route"},
        chat_session_limit=100,
    )

    with pytest.raises(ChatServiceError) as exc_info:
        ChatSessionService(db, settings).create_session(
            ChatOwner(hf_user_id="owner-1", hf_username="owner")
        )

    assert exc_info.value.code == "chat_session_quota_exceeded"
    assert "chat_sessions.archived_at IS NULL" in db.scalar_query
    assert str(exc_info.value) == (
        "You can have at most 100 chats. Archive old chats or delete a chat to "
        "create another."
    )


@pytest.mark.parametrize(
    ("found", "status", "outcome"), [(True, 204, "commit"), (False, 404, "rollback")]
)
def test_feedback_route_commits_the_stored_rating(monkeypatch, found, status, outcome):
    from backend.database.connection import get_database_session

    calls: list[str] = []

    class FakeSession:
        def commit(self) -> None:
            calls.append("commit")

        def rollback(self) -> None:
            calls.append("rollback")

    class FakeFeedbackService:
        def __init__(self, db, settings) -> None:
            self.db = db

        def submit(self, **kwargs) -> bool:
            calls.append("submit")
            return found

    import backend.main as pwc_main

    settings = Settings(_env_file=None, chat_enabled=True)
    monkeypatch.setattr(pwc_main, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_router, "ChatFeedbackService", FakeFeedbackService)
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_database_session] = lambda: FakeSession()
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/chat/messages/{uuid.uuid4()}/feedback",
            json={"value": True, "comment": "Helpful"},
        )

    assert response.status_code == status, response.json()
    # The request session only closes at exit, so the route itself must commit
    # a stored rating and roll back when nothing was stored.
    assert calls == ["submit", outcome]
