from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.config import get_settings
from backend.services import chat_session_service as module
from backend.services.chat_session_service import (
    ChatOwner,
    ChatSessionService,
    ChatServiceError,
)
from backend.services.chat_turn_mode import resolve_turn_mode
from backend.tests.chat.admission_harness import (
    _Result,
    _ScriptedDB,
    _session,
)


@pytest.mark.parametrize("reader", [False, True])
@pytest.mark.parametrize("poster", [False, True])
@pytest.mark.parametrize("artifacts", [False, True])
@pytest.mark.parametrize("latex", [False, True])
def test_capabilities_and_lease_share_effective_mode(reader, poster, artifacts, latex):
    settings = get_settings().model_copy(
        update={
            "chat_artifacts_enabled": artifacts,
            "chat_posterly_enabled": True,
            "chat_latex_paper_enabled": latex,
            "chat_latex_compiler_jobs_enabled": True,
        }
    )
    mode = resolve_turn_mode(
        settings, primary_paper_id=42 if reader else None, poster_intent=poster
    )
    assert mode.reader_mode is reader
    assert mode.poster_mode is (artifacts and poster)
    assert mode.paper_artifacts_enabled is (artifacts and latex and not reader)
    assert mode.ordinary_research is not (
        mode.poster_mode or mode.paper_artifacts_enabled
    )
    assert mode.lease_seconds == 30 + (
        settings.chat_posterly_timeout_seconds
        if artifacts and poster
        else settings.chat_timeout_seconds
    )


@pytest.mark.parametrize("new_session", [False, True])
@pytest.mark.parametrize(
    "reader,latex", [(True, True), (True, False), (False, False), (False, True)]
)
def test_external_admission_and_transport_use_requested_identity(
    monkeypatch,
    new_session,
    reader,
    latex,
):
    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": True,
            "chat_external_pi_admission_enabled": True,
            "chat_default_agent_harness": "pi",
            "chat_executor_remote_transport_enabled": True,
            "chat_artifacts_enabled": True,
            "chat_latex_paper_enabled": latex,
            "chat_latex_compiler_jobs_enabled": True,
        }
    )
    paper_id = 42 if reader else None
    session = _session(settings, primary_paper_id=paper_id, agent_harness="pi")
    calls = []

    class Coordinator:
        def __init__(self, *args, **kwargs):
            pass

        def preflight(self, **kwargs):
            return SimpleNamespace(
                existing_job=None, reconciled_expired_count=0, external_reservation=None
            )

        def reserve_external_capacity(self, preflight, **kwargs):
            calls.append((kwargs["poster_mode"], kwargs["paper_artifacts_enabled"]))
            return preflight

        def admit(self, *args, **kwargs):
            pass

    class Executor:
        def __init__(self, *args):
            pass

        def reserve(self, *args, **kwargs):
            calls.append("transport")
            return SimpleNamespace(transport="persistent", revision=7)

    monkeypatch.setattr(module, "ChatTurnAdmissionCoordinator", Coordinator)
    monkeypatch.setattr(module, "ChatExecutorTurnAdmission", Executor)
    db = _ScriptedDB(execute_results=(_Result(),) * 8, scalar_results=(0,) * 8)
    service = ChatSessionService(db, settings)
    service._owned = lambda *args, **kwargs: session

    def create(*args, **kwargs):
        assert kwargs.get("primary_paper_id") == paper_id
        return session

    service.create_session = create
    service.fetchable_url_seed = lambda *args, **kwargs: []
    if latex and not reader:
        with pytest.raises(ChatServiceError) as error:
            service.begin_turn(
                ChatOwner("owner-1", "owner"),
                session_id=None if new_session else session.id,
                client_message_id="request",
                text="Explain this paper",
            )
        assert error.value.code == "unsupported_chat_mode"
        assert calls == []
        assert db.added == []
        return
    before = datetime.now(UTC)
    admission = service.begin_turn(
        ChatOwner("owner-1", "owner"),
        session_id=None if new_session else session.id,
        client_message_id="request",
        text="Explain this paper",
        primary_paper_id=paper_id,
    )
    assert calls == [(False, False), "transport"]
    assert admission.reader_mode is reader
    assert admission.paper_artifacts_enabled is False
    assert admission.executor_transport == "persistent"
    assert admission.executor_reservation_revision == 7
    assert (
        before + timedelta(seconds=settings.chat_timeout_seconds + 30)
        <= session.active_turn_expires_at
    )
    assert len(db.added) == 1


@pytest.mark.parametrize("reader", [False, True])
@pytest.mark.parametrize("poster", [False, True])
def test_replay_mode_uses_persisted_request_and_bound_paper(reader, poster):
    import uuid

    settings = get_settings().model_copy(
        update={
            "chat_artifacts_enabled": True,
            "chat_posterly_enabled": True,
            "chat_latex_paper_enabled": True,
            "chat_latex_compiler_jobs_enabled": True,
            "chat_executor_remote_transport_enabled": False,
        }
    )
    session = _session(settings, primary_paper_id=42 if reader else None)
    existing = SimpleNamespace(
        sandbox_image_version="image-7",
        pwc_cli_version="cli-3",
        system_prompt_sha256="prompt-sha",
        id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        status="complete",
        model=None,
        model_route=None,
        sequence=1,
        revision=1,
        content="make a poster" if poster else "explain attention",
    )
    db = _ScriptedDB(
        execute_results=(
            _Result(one=existing),
            _Result(one=SimpleNamespace(content="saved answer", followups=[])),
        )
    )
    service = ChatSessionService(db, settings)
    service._owned = lambda *args, **kwargs: session
    admission = service.begin_turn(
        ChatOwner("owner-1", "owner"),
        session_id=session.id,
        client_message_id="same-request",
        text="different caller text",
        primary_paper_id=42 if reader else None,
    )
    assert admission.reader_mode is reader
    assert admission.poster_mode is poster
    # Replays share the fresh turn's paper policy, so redaction stays on.
    assert admission.paper_artifacts_enabled is not reader
    assert admission.image_version == "image-7"
    assert admission.pwc_cli_version == "cli-3"
    assert admission.system_prompt_sha256 == "prompt-sha"
    assert admission.replay_assistant.content == "saved answer"
    assert db.added == []
