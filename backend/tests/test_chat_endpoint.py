from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.config import get_settings
from backend.main import create_app
from backend.models.chat import ChatRequest, sse_event
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER
from backend.services import chat_mcp
from backend.services.chat_agent_service import (
    SDKEventAdapter,
    SEARCH_TOOL_NAME,
    SearchCallLimiter,
    build_agent_options,
    stream_agent_events,
)
from backend.services.chat_session_service import ChatOwner, ChatSessionService
from backend.services.chat_title_service import fallback_title, normalize_title
from backend.services.chat_transcript_recovery import reconcile_spooled_session
from backend.utils.auth import require_user


def _cookie_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", b"pwc_session=test")],
        }
    )


def test_require_user_returns_immutable_oauth_subject(monkeypatch):
    from backend.routers import auth

    monkeypatch.setattr(
        auth,
        "decode_session_cookie",
        lambda _token: {"sub": "hf-immutable-123", "username": "Alice"},
    )
    assert require_user(_cookie_request()) == {
        "source": "cookie",
        "username": "alice",
        "hf_user_id": "hf-immutable-123",
    }


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


def test_sse_serialization_preserves_unicode_and_newlines():
    frame = sse_event("answer_delta", text="héllo\nworld")
    assert frame.startswith(b"data: ")
    assert frame.endswith(b"\n\n")
    assert json.loads(frame[6:-2])["text"] == "héllo\nworld"


def test_model_registry_exposes_stable_ids_not_provider_routes():
    settings = get_settings()
    assert [choice["id"] for choice in settings.chat_model_choices] == [
        "deepseek-ai/DeepSeek-V4-Flash",
        "zai-org/GLM-5.2",
    ]
    assert settings.chat_model_routes["deepseek-ai/DeepSeek-V4-Flash"].endswith(
        ":fastest"
    )
    assert settings.chat_model_routes["zai-org/GLM-5.2"].endswith(":together")


def test_title_and_display_projection_bounds():
    assert (
        normalize_title('  "Vision   Transformer Trends."  ')
        == "Vision Transformer Trends"
    )
    assert len(fallback_title("word " * 100)) <= 80
    with pytest.raises(ValueError):
        DISPLAY_BLOCKS_ADAPTER.validate_python(
            [
                {
                    "kind": "tool",
                    "id": "t",
                    "name": "search_papers",
                    "args": {"secret": "not allowed"},
                    "status": "done",
                    "hits": 0,
                    "took_ms": 1,
                    "results": [],
                }
            ]
        )


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


def test_search_limiter_denies_third_call():
    limiter = SearchCallLimiter(2)
    request = {"tool_name": SEARCH_TOOL_NAME}
    first = asyncio.run(limiter(request, None, None))
    second = asyncio.run(limiter(request, None, None))
    third = asyncio.run(limiter(request, None, None))
    assert first["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert second["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert third["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_sdk_adapter_streams_reasoning_tool_result_and_answer():
    adapter = SDKEventAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Search first"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={"type": "content_block_stop", "index": 0},
        ),
        StreamEvent(
            uuid="4",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": SEARCH_TOOL_NAME,
                    "input": {},
                },
            },
        ),
        StreamEvent(
            uuid="5",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 1,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": '{"query":"VLMs","top_k":3}',
                },
            },
        ),
        StreamEvent(
            uuid="6",
            session_id="s",
            event={"type": "content_block_stop", "index": 1},
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="tool-1",
                    content=json.dumps(
                        {"hits": 1, "took_ms": 9, "results": [{"route_id": "1"}]}
                    ),
                )
            ]
        ),
        StreamEvent(
            uuid="7",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 2,
                "delta": {"type": "text_delta", "text": "Answer"},
            },
        ),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=2,
            session_id="s",
        ),
    ]
    events = [event for message in messages for event in adapter.feed(message)]
    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "tool_result",
        "answer_delta",
        "done",
    ]
    assert events[3]["args"] == {"query": "VLMs", "top_k": 3}
    assert events[4]["results"] == [{"route_id": "1"}]


def test_sdk_adapter_complete_messages_do_not_need_partial_events():
    adapter = SDKEventAdapter(show_reasoning=True)
    events = adapter.feed(
        AssistantMessage(
            model="test",
            content=[
                ThinkingBlock(thinking="plan", signature="sig"),
                ToolUseBlock(id="t", name=SEARCH_TOOL_NAME, input={"query": "x"}),
                TextBlock(text="answer"),
            ],
        )
    )
    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "tool_call",
        "answer_delta",
    ]


def test_sdk_adapter_hides_leading_whitespace_and_over_budget_searches():
    adapter = SDKEventAdapter(show_reasoning=True, maximum_search_calls=2)
    events = []
    for message in [
        AssistantMessage(model="test", content=[TextBlock(text="\n\n")]),
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="t1", name=SEARCH_TOOL_NAME, input={"query": "one"})
            ],
        ),
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="t2", name=SEARCH_TOOL_NAME, input={"query": "two"})
            ],
        ),
        AssistantMessage(
            model="test",
            content=[
                ToolUseBlock(id="t3", name=SEARCH_TOOL_NAME, input={"query": "three"})
            ],
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="t3", content="The search limit was reached"
                )
            ]
        ),
        AssistantMessage(model="test", content=[TextBlock(text="Final answer")]),
    ]:
        events.extend(adapter.feed(message))

    assert [event["type"] for event in events] == [
        "tool_call",
        "tool_call",
        "answer_delta",
    ]
    assert [event.get("id") for event in events[:2]] == ["t1", "t2"]


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *_args):
        return self

    def filter(self, _condition):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self, papers):
        self.papers = papers
        self.closed = False

    def query(self, *entities):
        if len(entities) == 1 and entities[0] is chat_mcp.DBPaper:
            return _FakeQuery(self.papers)
        return _FakeQuery([])

    def close(self):
        self.closed = True


def test_search_payload_supports_external_rows_and_bounds_content(monkeypatch):
    paper = SimpleNamespace(
        id=9,
        arxiv_id=None,
        source="external",
        source_url="https://example.com/release",
        thumbnail_url="/api/thumbnails/custom/9.webp",
        title="Release",
        abstract="x" * 5_000,
        date_published=date(2026, 7, 1),
        conference=None,
        citation_count=4,
    )
    session = _FakeSession([paper])
    relation_data = {
        "authors": {9: ["Lab"]},
        "tasks": {9: [SimpleNamespace(name="Language Modeling", slug="lm")]},
        "methods": {9: [SimpleNamespace(name="Transformer", slug="transformer")]},
        "repositories": {
            9: [SimpleNamespace(url="https://github.com/acme/model", num_stars=10)]
        },
        "project_pages": {9: [SimpleNamespace(url="https://acme.example/model")]},
    }

    class FakePaperService:
        def __init__(self, _db):
            pass

        def search_papers(self, query, limit, mode):
            assert query == "model"
            assert limit == 3
            assert mode == "hybrid"
            return [SimpleNamespace(id="9")]

        def _get_paper_relation_data(self, ids, include_resources, card_view):
            assert ids == [9]
            assert include_resources and card_view
            return relation_data

        def _resolve_thumbnail_url(self, paper):
            return paper.thumbnail_url

    monkeypatch.setattr(chat_mcp, "PaperService", FakePaperService)
    payload = chat_mcp.search_papers_payload(
        "model", 3, session_factory=lambda: session
    )
    hit = payload["results"][0]
    assert session.closed
    assert hit["route_id"] == "9"
    assert hit["metadata"]["source"] == "external"
    assert hit["metadata"]["thumbnail_url"] == "/api/thumbnails/custom/9.webp"
    assert len(hit["content"]) == 4_000
    assert hit["content_truncated"] is True
    assert chat_mcp._serialized_size(payload) <= 40_000


def test_result_byte_cap_handles_multibyte_content():
    metadata = {
        "arxiv_id": None,
        "source": "external",
        "source_url": "https://example.com",
        "authors": [],
        "published": None,
        "conference": None,
        "citation_count": None,
        "tasks": [],
        "methods": [],
        "repositories": [],
        "project_pages": [],
    }
    payload = {
        "hits": 10,
        "took_ms": 1,
        "results": [
            {
                "route_id": str(index),
                "title": "paper",
                "content": "界" * 4_000,
                "content_truncated": False,
                "metadata": dict(metadata),
            }
            for index in range(10)
        ],
    }
    chat_mcp._enforce_result_bytes(payload)
    assert chat_mcp._serialized_size(payload) <= chat_mcp.MAX_RESULT_BYTES
    assert payload["results"][-1]["content_truncated"] is True


def test_agent_options_expose_only_search(tmp_path):
    settings = get_settings().model_copy(
        update={
            "hf_token": "test-token",
            "chat_max_search_calls": 2,
            "chat_hf_bill_to": "huggingface",
        }
    )
    options, _ = build_agent_options(settings, tmp_path)
    assert options.tools == []
    assert options.allowed_tools == [SEARCH_TOOL_NAME]
    assert options.setting_sources == []
    assert options.skills == []
    assert options.plugins == []
    assert options.fallback_model is None
    assert options.env["ANTHROPIC_API_KEY"] == "test-token"
    assert options.env["HF_BILL_TO"] == "huggingface"
    assert options.env["ANTHROPIC_CUSTOM_HEADERS"] == "X-HF-Bill-To: huggingface"
    assert "at most 2 times" in options.system_prompt


def test_failed_turn_keeps_partial_tool_projection():
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    message_id = uuid.uuid4()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        active_turn_id=turn_id,
        active_turn_expires_at=None,
        projection_bytes=0,
        updated_at=None,
    )
    message = SimpleNamespace(status="generating", error_code=None, display_blocks=[])

    class FakeResult:
        def scalar_one_or_none(self):
            return session

    class FakeDB:
        def execute(self, _query):
            return FakeResult()

        def get(self, _model, key):
            return message if key == message_id else None

    admission = SimpleNamespace(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=message_id,
    )
    blocks = [
        {
            "kind": "tool",
            "id": "t1",
            "name": "search_papers",
            "args": {"query": "object detection"},
            "status": "done",
            "hits": 0,
            "took_ms": 10,
            "results": [],
        }
    ]

    ChatSessionService(FakeDB(), get_settings()).fail_turn(
        ChatOwner(hf_user_id="hf-user", hf_username="tester"),
        admission,
        "provider_error",
        display_blocks=blocks,
    )

    assert message.status == "error"
    assert message.error_code == "provider_error"
    assert message.display_blocks == blocks
    assert session.active_turn_id is None
    assert session.projection_bytes > 0


def test_agent_timeout_emits_typed_error_and_closes_sdk_stream(monkeypatch):
    from backend.services import chat_agent_service

    state = {"closed": False}

    async def fake_query(**_kwargs):
        try:
            await asyncio.sleep(1)
            yield None
        finally:
            state["closed"] = True

    async def collect():
        settings = get_settings().model_copy(
            update={"hf_token": "test", "chat_timeout_seconds": 0.01}
        )
        return [
            event
            async for event in stream_agent_events(
                "hello",
                settings,
                model_route=settings.chat_glm_route,
                session_store=None,
                resume=None,
            )
        ]

    monkeypatch.setattr(chat_agent_service, "sdk_query", fake_query)
    events = asyncio.run(collect())
    assert events == [{"type": "error", "message": "The chat request timed out."}]
    assert state["closed"] is True


def test_chat_endpoint_requires_authentication(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "hello", "client_message_id": "id"},
        )
    assert response.status_code == 401


def test_chat_endpoint_stream_contract(monkeypatch):
    from backend.routers import chat as chat_router

    async def fake_stream(_prompt, _settings, **_kwargs):
        yield {"type": "answer_delta", "text": "hello"}
        yield {"type": "done", "followups": [], "finish_reason": "success"}

    async def fake_title(_prompt, _settings):
        # Let research finish first: title events must still reach the client.
        await asyncio.sleep(0.01)
        yield "Research chat"

    admission = SimpleNamespace(
        session_id="00000000-0000-0000-0000-000000000001",
        turn_id="00000000-0000-0000-0000-000000000002",
        user_message_id="00000000-0000-0000-0000-000000000003",
        selected_model="zai-org/GLM-5.2",
        model_route="zai-org/GLM-5.2:together",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=False,
        replay_assistant=None,
        is_replacement=False,
        prompt_revision=1,
        title_should_generate=True,
        execution_backend="local_mcp",
    )

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self):
            pass

    class FakeService:
        def __init__(self, *_args):
            pass

        def begin_turn(self, *_args, **_kwargs):
            return admission

        def begin_title(self, *_args, **_kwargs):
            return uuid.UUID("00000000-0000-0000-0000-000000000004")

        def complete_title(self, *_args, **_kwargs):
            return "Research chat"

        def complete_turn(self, *_args, **_kwargs):
            pass

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")

    class FakeRunner:
        sdk_directory = settings.chat_agent_cwd

        def events(self):
            return fake_stream("", settings)

        async def cancel(self):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(
        chat_router,
        "create_chat_turn_runner",
        lambda **_kwargs: FakeRunner(),
    )
    monkeypatch.setattr(chat_router, "stream_title", fake_title)
    monkeypatch.setattr(chat_router, "ChatSessionService", FakeService)
    monkeypatch.setattr(chat_router.db_manager, "_session_local", FakeDB)
    monkeypatch.setattr(chat_router, "_admission", chat_router._AdmissionControl())
    monkeypatch.setattr(
        chat_router, "_rate_limiter", chat_router._PrincipalRateLimiter()
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
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-store"
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [event["type"] for event in events] == [
        "stream_start",
        "answer_delta",
        "done",
        "session_title_start",
        "session_title_delta",
        "session_title_done",
    ]


def test_chat_endpoint_rejects_when_capacity_is_occupied(monkeypatch):
    from backend.routers import chat as chat_router

    class NoCapacity:
        async def try_acquire(self, _maximum):
            return False

        async def release(self):
            raise AssertionError("No permit was acquired")

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    monkeypatch.setattr(chat_router, "_admission", NoCapacity())
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
    assert response.headers["retry-after"] == "5"
