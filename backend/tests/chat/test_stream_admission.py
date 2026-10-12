"""Stream admission, spend rejection, reservations, capacity, and qualification scope."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.config import Settings, get_settings
from backend.main import create_app
from backend.models.chat import (
    ChatRequest,
)
from backend.routers import chat as chat_router
from backend.services import chat_application_service as chat_application
from backend.services import chat_admission_service as chat_admission
from backend.services.chat_sandbox_spend_service import ChatComputeDisabled
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    TurnAdmission,
)


from backend.services.chat_turn_event_repository import JournalFrame
from backend.utils.auth import require_user
from backend.tests.chat.endpoint_harness import (
    _cookie_request,
)


def test_stream_spend_rejection_preserves_exact_503_before_admission(monkeypatch):
    settings = Settings(
        _env_file=None,
        chat_enabled=True,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        chat_default_backend="modal_cli",
        chat_sandbox_spend_enforcement_enabled=True,
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)

    def reject(*_args, **_kwargs):
        raise ChatComputeDisabled("Chat is temporarily disabled")

    monkeypatch.setattr(chat_application, "assert_chat_sandbox_spend_available", reject)
    body = ChatRequest(message="hello", client_message_id="message-a")

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            chat_router.stream_chat(
                body,
                _cookie_request(),
                {"hf_user_id": "owner-1", "username": "owner"},
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "code": "chat_temporarily_disabled",
        "message": "Chat is temporarily disabled",
    }


def test_duplicate_durable_post_attaches_without_preparation_or_source(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="zai-org/GLM-5.2",
        model_route="zai-org/GLM-5.2:together",
        sdk_session_id=None,
        sdk_project_key=None,
        attach_only=True,
    )
    settings = get_settings().model_copy(
        update={
            "chat_enabled": True,
            "chat_public_admission_enabled": True,
            "chat_sandbox_admission_enabled": True,
            "chat_durable_turn_dispatch_enabled": True,
        }
    )
    calls = {"begin": 0}

    class DB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    class Service:
        def __init__(self, *_args):
            pass

        def existing_effective_prompt(self, owner, requested_session, request_id):
            assert (owner.hf_user_id, requested_session, request_id) == (
                "owner-1",
                session_id,
                "stable-request",
            )
            return "persisted prompt"

        def begin_turn(self, *_args, **_kwargs):
            calls["begin"] += 1
            return admission

    class Coordinator:
        async def subscribe(self, *, turn_id, after_sequence):
            assert (turn_id, after_sequence) == (admission.turn_id, 3)
            yield JournalFrame(4, "answer_delta", {"text": "attached"})

    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_application, "web_search_available", lambda *_args: True)
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="token", bill_to=None),
    )
    monkeypatch.setattr(
        chat_application.deployment_lifecycle,
        "status",
        lambda: SimpleNamespace(accepting_chat_turns=True),
    )
    monkeypatch.setattr(chat_admission, "ChatSessionService", Service)
    monkeypatch.setattr(chat_application, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router.db_manager, "_session_local", DB)
    monkeypatch.setattr(
        chat_application,
        "_prepare_paper_turn",
        lambda *_args: pytest.fail("duplicate prompt was prepared"),
    )
    monkeypatch.setattr(
        chat_application,
        "ChatStreamOrchestrator",
        lambda **_kwargs: pytest.fail("duplicate model source was created"),
    )
    monkeypatch.setattr(
        chat_application,
        "detached_chat_runtime",
        lambda: SimpleNamespace(coordinator=Coordinator()),
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [(b"last-event-id", b"3")],
        }
    )

    async def exercise():
        response = await chat_router.stream_chat(
            ChatRequest(
                message="retry",
                session_id=session_id,
                client_message_id="stable-request",
            ),
            request,
            {"hf_user_id": "owner-1", "username": "owner"},
        )
        return b"".join([chunk async for chunk in response.body_iterator]).decode()

    body = asyncio.run(exercise())

    assert "id: 4\n" in body
    assert calls == {"begin": 1}


def test_failed_detached_terminal_callback_keeps_orchestrator_and_releases_reservation():
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    claim = SimpleNamespace(turn_id=turn_id)

    class Orchestrator:
        async def persist_detached_terminal(self, *_args):
            raise RuntimeError("ambiguous terminal")

    orchestrator = Orchestrator()
    released = []
    runtime = runtime_module.ChatDetachedRuntime(get_settings())
    runtime._orchestrators[turn_id] = orchestrator

    async def transaction(operation):
        operation(SimpleNamespace())

    runtime._transaction = transaction
    original_release = runtime_module.ChatExternalWorkerCapacityRepository.release_turn
    runtime_module.ChatExternalWorkerCapacityRepository.release_turn = (
        lambda _db, *, turn_id: released.append(turn_id)
    )
    try:
        with pytest.raises(RuntimeError, match="ambiguous terminal"):
            asyncio.run(runtime._persist_terminal(claim, "failed", "turn_failed"))
        assert runtime._orchestrators[turn_id] is orchestrator
        assert released == [turn_id]
    finally:
        runtime_module.ChatExternalWorkerCapacityRepository.release_turn = (
            original_release
        )
        runtime._orchestrators.pop(turn_id, None)


def test_process_loss_terminal_cleanup_releases_persisted_reservation():
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    released = []
    runtime = runtime_module.ChatDetachedRuntime(get_settings())

    async def transaction(operation):
        operation(SimpleNamespace())

    runtime._transaction = transaction
    original_release = runtime_module.ChatExternalWorkerCapacityRepository.release_turn
    runtime_module.ChatExternalWorkerCapacityRepository.release_turn = (
        lambda _db, *, turn_id: released.append(turn_id)
    )
    try:
        with pytest.raises(RuntimeError, match="owner is unavailable"):
            asyncio.run(
                runtime._persist_terminal(
                    SimpleNamespace(turn_id=turn_id), "failed", "process_lost"
                )
            )
    finally:
        runtime_module.ChatExternalWorkerCapacityRepository.release_turn = (
            original_release
        )

    assert released == [turn_id]


def test_terminal_release_failure_does_not_mask_persistence_failure(
    monkeypatch,
):
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    claim = SimpleNamespace(turn_id=turn_id)

    class Orchestrator:
        async def persist_detached_terminal(self, *_args):
            raise RuntimeError("primary persistence failure")

    orchestrator = Orchestrator()
    runtime = runtime_module.ChatDetachedRuntime(get_settings())
    runtime._orchestrators[turn_id] = orchestrator
    cleanup_attempted = []

    async def transaction(operation):
        cleanup_attempted.append(True)
        raise OSError("cleanup database unavailable")

    runtime._transaction = transaction
    monkeypatch.setattr(
        runtime_module.ChatExternalWorkerCapacityRepository,
        "release_turn",
        lambda _db, *, turn_id: None,
    )

    with pytest.raises(RuntimeError, match="primary persistence failure"):
        asyncio.run(runtime._persist_terminal(claim, "failed", "turn_failed"))
    assert cleanup_attempted == [True]
    assert runtime._orchestrators[turn_id] is orchestrator


def test_detached_start_failure_releases_reservation_without_masking_primary_error(
    monkeypatch,
):
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    admission = SimpleNamespace(turn_id=turn_id, session_id=uuid.uuid4())
    released = []
    abandoned = []

    class Registry:
        async def start_detached(self, **_kwargs):
            raise RuntimeError("primary detached start failure")

    class Orchestrator:
        def events(self):
            return None

        async def abandon_detached_start(self):
            abandoned.append(True)

    runtime = runtime_module.ChatDetachedRuntime(get_settings())
    runtime.registry = Registry()

    async def transaction(operation):
        operation(SimpleNamespace())

    runtime._transaction = transaction
    monkeypatch.setattr(
        runtime_module.ChatExternalWorkerCapacityRepository,
        "release_turn",
        lambda _db, *, turn_id: released.append(turn_id),
    )

    with pytest.raises(RuntimeError, match="primary detached start failure"):
        asyncio.run(
            runtime.start(
                admission=admission,
                owner_id="owner",
                claim=SimpleNamespace(turn_id=turn_id),
                orchestrator=Orchestrator(),
            )
        )

    assert abandoned == [True]
    assert released == [turn_id]
    assert turn_id not in runtime._orchestrators


def test_detached_start_cleanup_failures_preserve_original_start_error():
    from backend.services import chat_detached_runtime as runtime_module

    turn_id = uuid.uuid4()
    admission = SimpleNamespace(turn_id=turn_id, session_id=uuid.uuid4())
    cleanup_attempted = []

    class Registry:
        async def start_detached(self, **_kwargs):
            raise RuntimeError("original start error")

    class Orchestrator:
        def events(self):
            return None

        async def abandon_detached_start(self):
            raise OSError("abandonment unavailable")

    runtime = runtime_module.ChatDetachedRuntime(get_settings())
    runtime.registry = Registry()

    async def transaction(_operation):
        cleanup_attempted.append(True)
        raise OSError("reservation cleanup unavailable")

    runtime._transaction = transaction

    with pytest.raises(RuntimeError, match="original start error"):
        asyncio.run(
            runtime.start(
                admission=admission,
                owner_id="owner",
                claim=SimpleNamespace(turn_id=turn_id),
                orchestrator=Orchestrator(),
            )
        )

    assert cleanup_attempted == [True]


def test_stream_rejects_paper_selection_when_flag_is_off(monkeypatch):
    settings = Settings(
        _env_file=None,
        chat_enabled=True,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        paper_reader_chat_enabled=True,
        paper_reader_selection_enabled=False,
        environment="staging",
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    body = ChatRequest(
        message="Explain this",
        client_message_id="selection-disabled",
        primary_paper_route_id="2501.00001",
        paper_selection={
            "route_id": "2501.00001",
            "paper_version": "v1",
            "page": 4,
            "text": "quoted evidence",
        },
    )

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            chat_router.stream_chat(
                body,
                _cookie_request(),
                {"hf_user_id": "owner-1", "username": "owner", "role": "admin"},
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "paper_selection_disabled"


def test_stream_gates_selection_follow_ups_to_staging_reviewers(monkeypatch):
    settings = Settings(
        _env_file=None,
        chat_enabled=True,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        paper_reader_chat_enabled=True,
        paper_reader_selection_enabled=True,
        environment="staging",
    )
    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    body = ChatRequest(
        message="Explain this",
        client_message_id="selection-follow-up",
        session_id=uuid.uuid4(),
        paper_selection={
            "route_id": "2501.00001",
            "paper_version": "v1",
            "page": 4,
            "text": "quoted evidence",
        },
    )

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            chat_router.stream_chat(
                body,
                _cookie_request(),
                {"hf_user_id": "owner-1", "username": "owner"},
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "staging_access_required"


def test_chat_endpoint_rejects_when_capacity_is_occupied(monkeypatch, caplog):
    from backend.routers import chat as chat_router

    calls = {"begin_turn": 0, "runner": 0}

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def rollback(self):
            return None

    class NoCapacity:
        def __init__(self, *_args):
            pass

        def begin_turn(self, *_args, **_kwargs):
            calls["begin_turn"] += 1
            raise ChatServiceError(
                "chat_capacity",
                429,
                "Research capacity is currently occupied",
                active_count=2,
            )

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-inference-token", bill_to=None),
    )
    monkeypatch.setattr(chat_admission, "ChatSessionService", NoCapacity)
    monkeypatch.setattr(chat_application, "ChatSessionService", NoCapacity)
    monkeypatch.setattr(chat_router.db_manager, "_session_local", FakeDB)
    monkeypatch.setattr(
        chat_application,
        "ChatStreamOrchestrator",
        lambda **_kwargs: calls.__setitem__("runner", calls["runner"] + 1),
    )
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "hello", "client_message_id": "id"},
        )
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "chat_capacity"
    assert response.headers["retry-after"] == "5"
    assert calls == {"begin_turn": 1, "runner": 0}
    assert "chat capacity denied environment=" in caplog.text
    assert "ceiling=" in caplog.text
    assert "denial_count=" in caplog.text
    assert "hello" not in caplog.text


def test_stream_endpoint_rejects_forged_qualification_scope_header(monkeypatch):
    settings = Settings(
        _env_file=None,
        environment="staging",
        release_id="0123456789ab-staging",
        chat_durable_turn_dispatch_enabled=True,
    )
    monkeypatch.setattr(
        chat_router, "has_valid_non_cookie_admin_credential", lambda *_args: True
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [
                (b"x-pwc-qualification-scope-id", b"forged-not-a-uuid"),
                (b"x-pwc-qualification-workload", b"no_tool"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        chat_router._durable_qualification_scope(request, settings)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {"code": "qualification_scope_rejected"}


def test_stream_endpoint_rejects_nonexistent_active_qualification_scope(
    monkeypatch,
):
    from backend.services.chat_durable_qualification_evidence import (
        QualificationEvidenceUnavailable,
    )

    scope_id = uuid.uuid4()
    settings = Settings(
        _env_file=None,
        environment="staging",
        release_id="0123456789ab-staging",
        chat_enabled=True,
        chat_public_admission_enabled=True,
        chat_sandbox_admission_enabled=True,
        chat_durable_turn_dispatch_enabled=True,
        hf_token="test-token",
    )

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def rollback(self):
            return None

    class MissingScope:
        def __init__(self, _db):
            pass

        def require_active_context(self, *_args, **_kwargs):
            raise QualificationEvidenceUnavailable("scope does not exist")

    monkeypatch.setattr(chat_router, "get_settings", lambda: settings)
    monkeypatch.setattr(
        chat_router, "has_valid_non_cookie_admin_credential", lambda *_args: True
    )
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-token", bill_to=None),
    )
    monkeypatch.setattr(
        chat_application.deployment_lifecycle,
        "status",
        lambda: SimpleNamespace(accepting_chat_turns=True),
    )
    monkeypatch.setattr(
        chat_application,
        "_prepare_paper_turn",
        lambda *_args: chat_application.PreparedPaperTurn(
            "hello", "hello", [], 0, 0, 0
        ),
    )
    monkeypatch.setattr(
        chat_admission, "ChatDurableQualificationEvidenceService", MissingScope
    )
    monkeypatch.setattr(chat_router.db_manager, "_session_local", FakeDB)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat/stream",
            "headers": [
                (b"x-pwc-qualification-scope-id", str(scope_id).encode()),
                (b"x-pwc-qualification-workload", b"no_tool"),
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            chat_router.stream_chat(
                ChatRequest(message="hello", client_message_id="qualified-request"),
                request,
                {"hf_user_id": "operator", "username": "operator"},
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "qualification_scope_unavailable"}


def test_paper_hydration_failure_precedes_turn_admission_and_runner(monkeypatch):
    from backend.routers import chat as chat_router

    calls = {"begin_turn": 0, "runner": 0}

    class NoAdmission:
        def __init__(self, *_args):
            pass

        def begin_turn(self, *_args, **_kwargs):
            calls["begin_turn"] += 1
            raise AssertionError("turn admission must not run")

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "chat_default_backend", "local_mcp")
    monkeypatch.setattr(settings, "chat_paper_mentions_enabled", True)
    monkeypatch.setattr(
        chat_router,
        "inference_credential_for_request",
        lambda *_args: SimpleNamespace(token="user-inference-token", bill_to=None),
    )

    def fail_preparation(*_args):
        raise ChatServiceError(
            "paper_context_unavailable",
            503,
            "Attached paper context could not be prepared.",
        )

    monkeypatch.setattr(
        chat_application,
        "_prepare_paper_turn",
        fail_preparation,
    )
    monkeypatch.setattr(chat_admission, "ChatSessionService", NoAdmission)
    monkeypatch.setattr(chat_application, "ChatSessionService", NoAdmission)
    monkeypatch.setattr(
        chat_application,
        "ChatStreamOrchestrator",
        lambda **_kwargs: calls.__setitem__("runner", calls["runner"] + 1),
    )
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "message": "Read Paper",
                "client_message_id": "paper-client-id",
                "paper_mentions": [
                    {
                        "route_id": "2501.00001",
                        "title": "Paper",
                        "start": 5,
                        "end": 10,
                    }
                ],
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "paper_context_unavailable"
    assert calls == {"begin_turn": 0, "runner": 0}


def test_new_chat_capacity_rejection_precedes_session_creation(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.counts = iter((0, 2))

        def execute(self, _query):
            return None

        def scalar(self, _query):
            return next(self.counts)

    settings = get_settings().model_copy(update={"chat_max_concurrency": 2})
    service = ChatSessionService(FakeDB(), settings)
    created = []
    monkeypatch.setattr(
        service,
        "create_session",
        lambda *_args, **_kwargs: created.append(True),
    )

    with pytest.raises(ChatServiceError) as error:
        service.begin_turn(
            ChatOwner(hf_user_id="third-user", hf_username="third"),
            session_id=None,
            client_message_id="third-request",
            text="This content must not be stored",
        )

    assert error.value.code == "chat_capacity"
    assert error.value.active_count == 2
    assert created == []


def test_one_user_can_admit_two_concurrent_active_turns(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.counts = iter((1, 1))

        def execute(self, _query):
            return None

        def scalar(self, _query):
            return next(self.counts)

    class ReachedSessionCreation(Exception):
        pass

    def reached_creation(*_args, **_kwargs):
        raise ReachedSessionCreation

    settings = get_settings().model_copy(
        update={"chat_max_concurrency": 2, "chat_user_max_concurrency": 2}
    )
    service = ChatSessionService(FakeDB(), settings)
    monkeypatch.setattr(
        service,
        "create_session",
        reached_creation,
    )

    with pytest.raises(ReachedSessionCreation):
        service.begin_turn(
            ChatOwner(hf_user_id="same-user", hf_username="same"),
            session_id=None,
            client_message_id="second-request",
            text="A second concurrent turn is allowed",
        )
