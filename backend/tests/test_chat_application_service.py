"""Application outcomes and transaction boundaries without an HTTP adapter."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.chat import ChatRequest
from backend.models.database import ChatMessageRecord, ChatSession
from backend.services import chat_admission_service as admission_module
from backend.services import chat_application_service as application
from backend.services.chat_admission_service import (
    PreparedAdmission,
    admit_prepared_turn,
)
from backend.services.chat_paper_context_service import PreparedPaperTurn
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ReplayAssistant,
    TurnAdmission,
)
from backend.services.chat_stream_service import ChatStreamFrame
from backend.services.chat_turn_event_repository import JournalFrame


@compiles(JSONB, "sqlite")
def compile_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


OWNER = ChatOwner("owner", "owner")
BODY = ChatRequest(message="hello", client_message_id="request")
PREPARED = PreparedPaperTurn("hello", "paper context hello", [], 0, 0, 0)


def settings(**updates):
    return get_settings().model_copy(
        update={
            "chat_enabled": True,
            "chat_public_admission_enabled": True,
            "chat_sandbox_admission_enabled": True,
            "chat_scope_guardrail_enabled": False,
            "chat_sandbox_spend_enforcement_enabled": False,
            **updates,
        }
    )


def turn(**updates):
    return replace(
        TurnAdmission(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            selected_model="model",
            model_route=next(
                route
                for route, provider in settings().chat_route_providers.items()
                if provider == "huggingface"
            ),
            sdk_session_id=None,
            sdk_project_key=None,
        ),
        **updates,
    )


@pytest.mark.parametrize(
    "kind,durable",
    [("execute", False), ("execute", True), ("replay", True), ("attach", True)],
)
def test_application_outcomes_select_single_source_without_rebilling_duplicates(
    monkeypatch, kind, durable
):
    events = []
    admission = turn(
        attach_only=kind == "attach",
        replay_assistant=ReplayAssistant("saved", []) if kind == "replay" else None,
    )
    prepared = PreparedAdmission(admission, "openrouter", None, [], False)
    service = application.ChatApplicationService(
        settings(chat_durable_turn_dispatch_enabled=durable)
    )
    monkeypatch.setattr(
        application.deployment_lifecycle,
        "status",
        lambda: SimpleNamespace(accepting_chat_turns=True),
    )
    monkeypatch.setattr(application, "web_search_available", lambda _: False)
    monkeypatch.setattr(service, "_prepare", AsyncMock(return_value=PREPARED))

    def admit(**_):
        events.append("admit")
        return prepared

    monkeypatch.setattr(application, "admit_prepared_turn", admit)

    @contextmanager
    def db():
        yield object()

    monkeypatch.setattr(application.db_manager, "_session_local", db)

    async def authorize(*_):
        events.append("bill")
        return SimpleNamespace(
            mode="openrouter_funded", token=None, credential_revision=None
        )

    monkeypatch.setattr(application, "authorize_openrouter", authorize)

    async def frames():
        yield ChatStreamFrame("answer_delta", {"text": "hello"})

    class Orchestrator:
        def __init__(self, **kwargs):
            events.append("orchestrator")
            assert kwargs["prompt"] == PREPARED.effective_prompt
            assert kwargs["admission"] is admission

        async def claim_durable_turn(self):
            events.append("claim")
            return "claim"

        def events(self):
            return frames()

    def live_start(**kwargs):
        events.append("live")
        return SimpleNamespace(subscribe=lambda: kwargs["source"])

    async def durable_start(**kwargs):
        assert kwargs["claim"] == "claim"
        events.append("durable")
        return SimpleNamespace(subscribe=lambda cursor: frames())

    async def replay(*args, **kwargs):
        events.append("attach")
        assert kwargs["after_sequence"] == 7
        yield JournalFrame(8, "answer_delta", {"text": "saved"})

    monkeypatch.setattr(application, "ChatStreamOrchestrator", Orchestrator)
    monkeypatch.setattr(
        application,
        "live_chat_stream_registry",
        lambda: SimpleNamespace(start=live_start),
    )
    monkeypatch.setattr(
        application,
        "detached_chat_runtime",
        lambda *_: SimpleNamespace(start=durable_start, coordinator=object()),
    )
    monkeypatch.setattr(application, "replay_detached_frames", replay)

    async def run():
        result = await service.start_turn(
            body=BODY,
            owner=OWNER,
            user_role=None,
            inference_credential_present=False,
            after_sequence=7,
        )
        assert result.kind == kind
        assert len([frame async for frame in result.frames]) == 1

    asyncio.run(run())
    expected = {
        ("execute", False): ["admit", "bill", "orchestrator", "live"],
        ("execute", True): ["admit", "bill", "orchestrator", "claim", "durable"],
        ("replay", True): ["admit", "orchestrator", "live"],
        ("attach", True): ["admit", "attach"],
    }
    assert events == expected[kind, durable]


@pytest.mark.parametrize(
    "failure",
    [TimeoutError(), ChatServiceError("paper_context_unavailable", 503, "unavailable")],
)
def test_preparation_failure_never_admits_and_preserves_retry_header(
    monkeypatch, failure
):
    def prepare(*_):
        raise failure

    monkeypatch.setattr(application, "_prepare_paper_turn", prepare)
    monkeypatch.setattr(
        application,
        "admit_prepared_turn",
        lambda **_: pytest.fail("admitted before preparation"),
    )
    monkeypatch.setattr(application, "web_search_available", lambda _: False)
    monkeypatch.setattr(
        application.deployment_lifecycle,
        "status",
        lambda: SimpleNamespace(accepting_chat_turns=True),
    )
    with pytest.raises(application.ChatApplicationError) as error:
        asyncio.run(
            application.ChatApplicationService(settings()).start_turn(
                body=BODY,
                owner=OWNER,
                user_role=None,
                inference_credential_present=True,
            )
        )
    assert error.value.status_code == 503
    assert error.value.headers == {"Retry-After": "2"}


@pytest.fixture
def admission_db(monkeypatch):
    engine = create_engine("sqlite://")
    ChatSession.__table__.create(engine)
    ChatMessageRecord.__table__.create(engine)
    with Session(engine) as db:

        @contextmanager
        def session():
            yield db

        monkeypatch.setattr(admission_module.db_manager, "_session_local", session)
        yield db
    engine.dispose()


def admit(**kwargs):
    return admit_prepared_turn(
        settings=settings(),
        owner=OWNER,
        body=BODY,
        prepared=PREPARED,
        request_id="request",
        search_is_available=False,
        qualification_scope=None,
        **kwargs,
    )


@pytest.mark.parametrize("kind", ["execute", "replay", "attach"])
@pytest.mark.parametrize("credential", [False, True])
def test_hf_credential_requirement_preserves_attach_and_replay_behavior(
    monkeypatch, admission_db, kind, credential
):
    admission = turn(
        attach_only=kind == "attach",
        replay_assistant=ReplayAssistant("saved", []) if kind == "replay" else None,
    )

    class Service:
        def __init__(self, db, _settings):
            self.db = db

        def begin_turn(self, *_args, **_kwargs):
            self.db.add(
                ChatSession(
                    id=admission.session_id,
                    hf_user_id="owner",
                    hf_username="owner",
                    selected_model="model",
                )
            )
            self.db.flush()
            return admission

    monkeypatch.setattr(admission_module, "ChatSessionService", Service)
    monkeypatch.setattr(
        admission_module,
        "ChatLatencyService",
        lambda _: SimpleNamespace(admit=lambda **_: None),
    )
    if not credential and kind != "attach":
        with pytest.raises(ChatServiceError, match="authorization") as error:
            admit(inference_credential_present=credential)
        assert error.value.code == "hf_inference_billing_required"
        assert admission_db.get(ChatSession, admission.session_id) is None
    else:
        assert admit(inference_credential_present=credential).admission is admission
        assert admission_db.get(ChatSession, admission.session_id) is not None


@pytest.mark.parametrize("commit_changes", [False, True])
def test_admission_recovery_error_owns_commit_or_rollback(
    monkeypatch, admission_db, commit_changes
):
    admission = turn()
    error = ChatServiceError(
        "turn_requires_retry", 409, "retry", commit_changes=commit_changes
    )

    class Service:
        def __init__(self, db, _settings):
            self.db = db

        def begin_turn(self, *_args, **_kwargs):
            self.db.add(
                ChatSession(
                    id=admission.session_id,
                    hf_user_id="owner",
                    hf_username="owner",
                    selected_model="model",
                )
            )
            self.db.flush()
            raise error

    monkeypatch.setattr(admission_module, "ChatSessionService", Service)
    with pytest.raises(ChatServiceError) as caught:
        admit(inference_credential_present=True)
    assert caught.value is error
    assert (
        admission_db.get(ChatSession, admission.session_id) is not None
    ) is commit_changes


def test_latency_failure_rolls_back_title_and_new_session(monkeypatch, admission_db):
    admission = turn(title_should_generate=True)

    class Service:
        def __init__(self, db, _settings):
            self.db = db

        def begin_turn(self, *_args, **_kwargs):
            self.db.add(
                ChatSession(
                    id=admission.session_id,
                    hf_user_id="owner",
                    hf_username="owner",
                    selected_model="model",
                )
            )
            self.db.flush()
            return admission

        def begin_title(self, *_args, **_kwargs):
            self.db.get(ChatSession, admission.session_id).title = "reserved"
            self.db.flush()
            return uuid.uuid4()

    def fail(**_kwargs):
        assert admission_db.get(ChatSession, admission.session_id).title == "reserved"
        raise RuntimeError("latency failed")

    monkeypatch.setattr(admission_module, "ChatSessionService", Service)
    monkeypatch.setattr(
        admission_module, "ChatLatencyService", lambda _: SimpleNamespace(admit=fail)
    )
    with pytest.raises(RuntimeError, match="latency failed"):
        admit(inference_credential_present=True)
    assert admission_db.get(ChatSession, admission.session_id) is None


def test_post_commit_billing_failure_compensates_before_start(
    monkeypatch, admission_db
):
    admission = turn()
    admission_db.add(
        ChatSession(
            id=admission.session_id,
            hf_user_id="owner",
            hf_username="owner",
            selected_model="model",
            active_turn_id=admission.turn_id,
        )
    )
    admission_db.add(
        ChatMessageRecord(
            id=admission.user_message_id,
            session_id=admission.session_id,
            turn_id=admission.turn_id,
            sequence=1,
            role="user",
            content="hello",
            status="generating",
            model="model",
        )
    )
    admission_db.commit()
    service = application.ChatApplicationService(settings())
    prepared = PreparedAdmission(admission, "openrouter", None, [], False)
    monkeypatch.setattr(service, "_check_available", lambda *_: False)
    monkeypatch.setattr(service, "_prepare", AsyncMock(return_value=PREPARED))
    monkeypatch.setattr(application, "admit_prepared_turn", lambda **_: prepared)
    start = AsyncMock(side_effect=AssertionError("started after rejected billing"))
    monkeypatch.setattr(service, "_start", start)
    billing_error = ChatServiceError("openrouter_unavailable", 503, "unavailable")
    monkeypatch.setattr(
        application, "authorize_openrouter", AsyncMock(side_effect=billing_error)
    )
    with pytest.raises(ChatServiceError) as caught:
        asyncio.run(
            service.start_turn(
                body=BODY,
                owner=OWNER,
                user_role=None,
                inference_credential_present=True,
            )
        )
    assert caught.value is billing_error
    start.assert_not_awaited()
    admission_db.rollback()
    admission_db.expire_all()
    assert admission_db.get(ChatSession, admission.session_id).active_turn_id is None
    assert (
        admission_db.get(ChatMessageRecord, admission.user_message_id).error_code
        == "openrouter_unavailable"
    )
