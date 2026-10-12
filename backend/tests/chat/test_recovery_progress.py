"""Recovery preserves saved work and cancellation wins over late failures."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from backend.config import get_settings
from backend.models.chat import ChatRequest
from backend.services import chat_stream_service as streams
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    TurnAdmission,
)
from backend.services.chat_turn_job_repository import StaleTurnClaim


def orchestrator():
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route="test",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=True,
        agent_harness="pi",
    )
    return streams.ChatStreamOrchestrator(
        settings=get_settings().model_copy(
            update={"chat_durable_turn_dispatch_enabled": True}
        ),
        owner=ChatOwner("owner", "owner"),
        admission=admission,
        prompt="Research",
        request_id="test",
        title_token=None,
        is_disconnected=lambda: asyncio.sleep(0, result=False),
        release_admission=lambda: asyncio.sleep(0),
    )


def test_stop_wins_over_lost_lease_and_queued_provider_error():
    async def scenario():
        stream = orchestrator()
        stream._detached_cancel_requested = True
        stream.lease_heartbeat_error = StaleTurnClaim("cancelled lease")
        stream.projection.apply("answer_delta", {"text": "Useful partial answer"})
        queue = asyncio.Queue()
        await queue.put(
            {"type": "error", "code": "provider_error", "message": "late error"}
        )
        frames = [frame async for frame in stream._consume(queue)]
        assert [frame.event for frame in frames] == ["done"]
        assert frames[0].payload["finish_reason"] == "stopped"
        assert "Useful partial answer" in "".join(stream.projection.answer_parts)

    asyncio.run(scenario())


@pytest.mark.parametrize("cancelled", [True, False])
def test_producer_claim_failure_uses_durable_cancellation_evidence(
    monkeypatch, cancelled
):
    stream = orchestrator()
    monkeypatch.setattr(streams, "_durable_turn_cancelled", lambda *_: cancelled)

    class Runner:
        async def events(self):
            raise StaleTurnClaim("claim invalidated")
            yield

        async def cancel(self):
            pass

    stream.runner = Runner()

    async def scenario():
        queue = asyncio.Queue()
        await stream._produce_research(queue)
        event = await queue.get()
        assert event["type"] == ("_cancelled" if cancelled else "error")
        assert (await queue.get())["type"] == "_research_finished"

    asyncio.run(scenario())


def test_retry_request_cannot_rewind_or_create_a_session():
    target = uuid.uuid4()
    for extra in [
        {},
        {"session_id": uuid.uuid4(), "replace_message_id": target, "prior_revision": 1},
    ]:
        with pytest.raises(ValidationError):
            ChatRequest(
                message="Continue",
                client_message_id="new",
                retry_message_id=target,
                **extra,
            )
    request = ChatRequest(
        message="Continue",
        client_message_id="new",
        session_id=uuid.uuid4(),
        retry_message_id=target,
    )
    assert request.replace_message_id is None


@pytest.mark.parametrize(
    "status,matches,leaf",
    [("complete", True, "leaf"), ("error", False, "leaf"), ("error", True, None)],
)
def test_retry_rejects_stale_targets_and_missing_saved_history(status, matches, leaf):
    service = ChatSessionService(Mock(), get_settings())
    target = uuid.uuid4()
    service._latest_user_message = lambda _: SimpleNamespace(
        id=target if matches else uuid.uuid4(), status=status
    )
    service.db.scalar.return_value = leaf
    session = SimpleNamespace(
        id=uuid.uuid4(), agent_harness="pi", sdk_session_id="native"
    )
    with pytest.raises(ChatServiceError):
        service._validate_saved_progress_retry(session, target)


def test_saved_progress_retry_keeps_native_leaf_and_prior_failure():
    service = ChatSessionService(Mock(), get_settings())
    target = SimpleNamespace(id=uuid.uuid4(), status="error")
    service._latest_user_message = lambda _: target
    service.db.scalar.return_value = "last-completed-tool"
    session = SimpleNamespace(
        id=uuid.uuid4(), agent_harness="pi", sdk_session_id="native"
    )
    service._validate_saved_progress_retry(session, target.id)
    assert target.status == "error"
    boundary = service._resolve_transcript_resume_boundary(
        session, SimpleNamespace(prior=None)
    )
    assert boundary.agent_id == "last-completed-tool"
    service._latest_user_message = lambda _: SimpleNamespace(status="complete")
    assert not service._has_unresolved_turn(session)


@pytest.mark.parametrize("expired", [False, True])
def test_poster_retry_preserves_mode_lease_and_persisted_request(monkeypatch, expired):
    from datetime import timedelta
    from backend.tests.chat.admission_harness import (
        _Result,
        _ScriptedDB,
        _owned_service,
        _session,
    )

    settings = get_settings().model_copy(
        update={
            "chat_durable_turn_dispatch_enabled": False,
            "chat_artifacts_enabled": True,
            "chat_posterly_enabled": True,
            "chat_executor_remote_transport_enabled": True,
        }
    )
    session = _session(
        settings,
        agent_harness="pi",
        sdk_session_id="native",
        message_count=2,
        last_sequence=2,
    )
    target = SimpleNamespace(
        id=uuid.uuid4(),
        status="generating" if expired else "error",
        content="Make a poster about attention",
        effective_prompt="Make a poster about attention. Use source:123.",
    )
    if expired:
        session.active_turn_id = uuid.uuid4()
        session.active_turn_expires_at = session.updated_at - timedelta(seconds=1)
    db = _ScriptedDB(
        execute_results=(
            _Result(),
            *([_Result(one=target)] if expired else []),
            _Result(),
            _Result(),
        ),
        scalar_results=("saved-leaf", 0, 0, 0, "saved-leaf"),
    )
    service = _owned_service(db, settings, session)
    service._latest_user_message = lambda _: target
    monkeypatch.setattr(service, "fetchable_url_seed", lambda *_args, **_kwargs: [])
    admission = service.begin_turn(
        ChatOwner("owner-1", "owner"),
        session_id=session.id,
        client_message_id="retry",
        text="Continue from saved progress",
        retry_message_id=target.id,
    )
    assert admission.poster_mode
    assert target.status == ("interrupted" if expired else "error")
    assert admission.executor_transport == "legacy"
    assert session.active_turn_expires_at - session.updated_at == timedelta(
        seconds=settings.chat_posterly_timeout_seconds + 30
    )
    assert db.added[0].content == target.content
    assert db.added[0].effective_prompt.startswith(target.effective_prompt)
    assert "Do not repeat completed edits" in db.added[0].effective_prompt
