import asyncio
import uuid

from backend.config import get_settings
from backend.services.chat_scope_guardrail_service import (
    REFUSAL_TEXT,
    ScopeDecision,
    ScopeMessage,
)
from backend.services.chat_session_service import ChatOwner, TurnAdmission
from backend.services.chat_stream_service import ChatStreamOrchestrator


def test_scope_block_discards_speculative_events_and_cancels_runner(
    monkeypatch,
) -> None:
    from backend.services import chat_stream_service

    class Runner:
        sdk_directory = "/tmp/scope-test"

        def __init__(self) -> None:
            self.cancelled = False
            self.closed = False

        async def events(self):
            yield {"type": "reasoning_delta", "text": "private reasoning"}
            yield {"type": "answer_delta", "text": "suppressed answer"}
            yield {"type": "done", "finish_reason": "success"}

        async def cancel(self) -> None:
            self.cancelled = True

        async def close(self) -> None:
            self.closed = True

    runner = Runner()
    monkeypatch.setattr(
        chat_stream_service,
        "create_chat_turn_runner",
        lambda **_kwargs: runner,
    )

    async def classify(_self, _messages):
        await asyncio.sleep(0)
        return ScopeDecision(
            "unrelated application", "block", "huggingface-baseten", 1, False
        )

    monkeypatch.setattr(chat_stream_service.ScopeGuardrailService, "classify", classify)
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="model",
        model_route="route",
        sdk_session_id=None,
        sdk_project_key=None,
    )
    orchestrator = ChatStreamOrchestrator(
        settings=get_settings().model_copy(
            update={
                "chat_scope_guardrail_enabled": True,
                "chat_scope_guardrail_hf_token": "hf-test",
                "chat_scope_guardrail_hf_bill_to": "org",
                "chat_scope_guardrail_openai_api_key": "sk-test",
            }
        ),
        owner=ChatOwner("owner", "owner"),
        admission=admission,
        prompt="Build a miner GUI",
        request_id="request",
        title_token=uuid.uuid4(),
        is_disconnected=lambda: asyncio.sleep(0, result=False),
        release_admission=lambda: asyncio.sleep(0),
        scope_messages=[ScopeMessage(role="user", content="Build a miner GUI")],
    )

    persisted: list[tuple[str, str]] = []

    async def replacement():
        return True, None

    async def persist_block(answer: str, finish_reason: str):
        persisted.append((answer, finish_reason))

    orchestrator._replacement_or_error = replacement
    monkeypatch.setattr(
        orchestrator, "_persist_scope_block", persist_block, raising=False
    )

    async def collect():
        return [frame async for frame in orchestrator.events()]

    frames = asyncio.run(collect())
    semantic = [(frame.event, frame.payload) for frame in frames if frame.event]
    assert semantic == [
        (
            "stream_start",
            {
                "request_id": "request",
                "session_id": str(admission.session_id),
                "provider_execution": True,
            },
        ),
        ("answer_delta", {"text": REFUSAL_TEXT}),
        ("done", {"followups": [], "citations": [], "finish_reason": "scope_blocked"}),
    ]
    assert persisted == [(REFUSAL_TEXT, "scope_blocked")]
    assert runner.cancelled is True
    assert runner.closed is True
    assert "suppressed answer" not in str(semantic)
