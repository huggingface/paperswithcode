"""Durable journal replay, reconnect, and spooled transcript recovery."""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from backend.config import get_settings
from backend.routers import chat as chat_router
from backend.services.chat_session_service import (
    ReplayAssistant,
    TurnAdmission,
)
from backend.services.chat_stream_service import (
    encode_journal_frame,
)


from backend.services.chat_turn_event_repository import JournalFrame
from backend.services.chat_transcript_recovery import reconcile_spooled_session


def test_journal_sse_serializer_adds_sequence_without_changing_event_payload():
    encoded = encode_journal_frame(JournalFrame(8, "answer_delta", {"text": "héllo"}))

    assert encoded == (
        'id: 8\nevent: answer_delta\ndata: {"type":"answer_delta","text":"héllo"}\n\n'.encode()
    )


def test_journal_sse_serializer_preserves_browser_data_type_contract():
    encoded = encode_journal_frame(
        JournalFrame(4, "done", {"followups": [], "finish_reason": "success"})
    ).decode()
    data = next(
        json.loads(line.removeprefix("data: "))
        for line in encoded.splitlines()
        if line.startswith("data: ")
    )

    assert data == {
        "type": "done",
        "followups": [],
        "finish_reason": "success",
    }


def _completed_durable_admission(*, event_sequence: int = 8) -> TurnAdmission:
    return TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="model",
        model_route="route",
        sdk_session_id=None,
        sdk_project_key=None,
        replay_assistant=ReplayAssistant("canonical answer", ["next"]),
        attach_only=True,
        durable_event_sequence=event_sequence,
    )


def test_completed_durable_replay_uses_full_terminal_journal(monkeypatch):
    admission = _completed_durable_admission()

    class Coordinator:
        async def subscribe(self, *, turn_id, after_sequence):
            assert (turn_id, after_sequence) == (admission.turn_id, 4)
            yield JournalFrame(5, "stream_start", {"request_id": "original"})
            yield JournalFrame(6, "answer_delta", {"text": "stored"})
            yield JournalFrame(8, "done", {"finish_reason": "success"})

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect():
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=4
            )
        ]

    assert [(frame.sequence, frame.event) for frame in asyncio.run(collect())] == [
        (5, "stream_start"),
        (6, "answer_delta"),
        (8, "done"),
    ]


def test_completed_durable_replay_suppresses_fallback_at_acknowledged_cursor(
    monkeypatch,
):
    admission = _completed_durable_admission()

    class Coordinator:
        async def subscribe(self, *, turn_id, after_sequence):
            assert turn_id == admission.turn_id
            if False:
                yield

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect(cursor):
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=cursor
            )
        ]

    assert [frame.sequence for frame in asyncio.run(collect(7))] == [9, 10, 11]
    assert asyncio.run(collect(8)) == []
    assert asyncio.run(collect(9)) == []
    assert asyncio.run(collect(11)) == []


def test_completed_durable_replay_falls_back_after_job_sequence(monkeypatch):
    admission = _completed_durable_admission(event_sequence=8)

    class Coordinator:
        async def subscribe(self, **_kwargs):
            if False:
                yield

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect(cursor):
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=cursor
            )
        ]

    all_frames = asyncio.run(collect(7))
    acknowledged = asyncio.run(collect(8))
    assert [(frame.sequence, frame.event) for frame in all_frames] == [
        (9, "stream_start"),
        (10, "answer_delta"),
        (11, "done"),
    ]
    assert acknowledged == []


def test_completed_durable_replay_preserves_nonterminal_journal_before_fallback(
    monkeypatch,
):
    admission = _completed_durable_admission(event_sequence=8)

    class Coordinator:
        async def subscribe(self, **_kwargs):
            yield JournalFrame(8, "answer_delta", {"text": "partial"})

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect():
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=0
            )
        ]

    frames = asyncio.run(collect())
    assert [(frame.sequence, frame.event) for frame in frames] == [
        (8, "answer_delta"),
        (9, "stream_start"),
        (10, "answer_delta"),
        (11, "done"),
    ]
    assert frames[0].payload == {"text": "partial"}
    assert frames[2].payload == {"text": "canonical answer"}


@pytest.mark.parametrize("cursor", [8, 9])
def test_completed_durable_replay_partial_journal_at_acknowledged_cursor_emits_nothing(
    monkeypatch, cursor
):
    admission = _completed_durable_admission(event_sequence=8)

    class Coordinator:
        async def subscribe(self, **_kwargs):
            if 8 > cursor:
                yield JournalFrame(8, "answer_delta", {"text": "partial"})

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect():
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=cursor
            )
        ]

    assert asyncio.run(collect()) == []


def test_completed_durable_replay_falls_back_if_chunks_disappear_mid_replay(
    monkeypatch,
):
    admission = _completed_durable_admission(event_sequence=8)
    replay_steps = []

    class Coordinator:
        async def subscribe(self, **_kwargs):
            yield JournalFrame(7, "answer_delta", {"text": "partial"})
            replay_steps.append("terminal chunk deleted")

    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())

    async def collect():
        return [
            frame
            async for frame in chat_router._durable_replay_frames(
                admission, request_id="request-1", after_sequence=0
            )
        ]

    frames = asyncio.run(collect())
    assert replay_steps == ["terminal chunk deleted"]
    assert [(frame.sequence, frame.event) for frame in frames] == [
        (7, "answer_delta"),
        (9, "stream_start"),
        (10, "answer_delta"),
        (11, "done"),
    ]


def test_reconnect_stream_resumes_after_last_event_id(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    cursors = []

    class Service:
        def __init__(self, *_args):
            pass

        def get_session(self, owner, requested_session_id):
            assert owner.hf_user_id == "owner-1"
            assert requested_session_id == session_id
            return SimpleNamespace(active_turn_id=turn_id), []

    class Coordinator:
        async def subscribe(self, *, turn_id: uuid.UUID, after_sequence: int):
            cursors.append(after_sequence)
            for sequence in (7, 8):
                if sequence > after_sequence:
                    yield JournalFrame(
                        sequence, "answer_delta", {"text": str(sequence)}
                    )

    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "detached_turn_coordinator", lambda: Coordinator())
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/chat/sessions/{session_id}/stream",
            "headers": [(b"last-event-id", b"7")],
        }
    )
    response = chat_router.reconnect_active_stream(
        session_id,
        request,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=settings,
    )

    async def collect_body():
        return b"".join([chunk async for chunk in response.body_iterator]).decode()

    body = asyncio.run(collect_body())
    assert "id: 7\n" not in body
    assert "id: 8\n" in body
    assert cursors == [7]


def test_legacy_reconnect_ignores_malformed_last_event_id(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()

    class Service:
        def __init__(self, *_args):
            pass

        def get_session(self, *_args):
            return SimpleNamespace(active_turn_id=turn_id), []

    class Stream:
        async def subscribe(self):
            yield SimpleNamespace(
                event="done",
                payload={"followups": [], "finish_reason": "success"},
            )

    class Registry:
        def get(self, *_args):
            return Stream()

    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": False}
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "live_chat_stream_registry", lambda: Registry())
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/chat/sessions/{session_id}/stream",
            "headers": [(b"last-event-id", b"not-a-cursor")],
        }
    )

    response = chat_router.reconnect_active_stream(
        session_id,
        request,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=settings,
    )

    async def collect_body():
        return b"".join([chunk async for chunk in response.body_iterator]).decode()

    assert 'data: {"type":"done"' in asyncio.run(collect_body())


@pytest.mark.parametrize("cursor", ["-1", "nope", "1.5"])
def test_reconnect_stream_rejects_invalid_last_event_id(monkeypatch, cursor):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()

    class Service:
        def __init__(self, *_args):
            pass

        def get_session(self, *_args):
            return SimpleNamespace(active_turn_id=turn_id), []

    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )
    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/chat/sessions/{session_id}/stream",
            "headers": [(b"last-event-id", cursor.encode())],
        }
    )
    with pytest.raises(Exception) as exc_info:
        chat_router.reconnect_active_stream(
            session_id,
            request,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=object(),
            settings=settings,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "chat_stream_cursor_invalid"


def test_spooled_transcript_recovery_replays_main_and_subpaths(tmp_path):
    session_id = "00000000-0000-0000-0000-000000000123"
    recovery = tmp_path / "pwc-chat-recovery"
    project = recovery / "attempt" / "projects" / "project-key"
    project.mkdir(parents=True)
    main_entries = [{"type": "user", "uuid": "u1"}]
    (project / f"{session_id}.jsonl").write_text(
        json.dumps(main_entries[0]) + "\n", encoding="utf-8"
    )
    subpath = project / session_id / "subagents"
    subpath.mkdir(parents=True)
    (subpath / "agent-one.jsonl").write_text(
        json.dumps({"type": "assistant", "uuid": "u2"}) + "\n",
        encoding="utf-8",
    )

    class FakeStore:
        def __init__(self):
            self.rows = {}

        async def append(self, key, entries):
            self.rows[(key["session_id"], key.get("subpath"))] = entries

        async def load(self, key):
            return self.rows.get((key["session_id"], key.get("subpath")))

    store = FakeStore()
    settings = get_settings().model_copy(
        update={"chat_recovery_spool_dir": str(recovery)}
    )
    recovered = asyncio.run(
        reconcile_spooled_session(
            settings,
            store,
            project_key="project-key",
            sdk_session_id=uuid.UUID(session_id),
        )
    )
    assert recovered is True
    assert store.rows[(session_id, None)] == main_entries
    assert store.rows[(session_id, "subagents/agent-one")][0]["uuid"] == "u2"
    assert not (recovery / "attempt").exists()
