"""Local agent SDK adapter, tool limiters, search payloads, and finalizer."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, date, datetime
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

from backend.config import get_settings
from backend.services import chat_mcp
from backend.services.chat_agent_service import (
    SEARCH_TOOL_NAME,
    SDKEventAdapter,
    SearchCallLimiter,
    _local_tool_event_policy,
    build_agent_options,
    stream_agent_events,
)
from backend.services.chat_session_service import (
    ChatOwner,
    ChatSessionService,
    TurnAdmission,
)


def test_search_limiter_denies_third_call():
    limiter = SearchCallLimiter(2)
    request = {"tool_name": SEARCH_TOOL_NAME}
    first = asyncio.run(limiter(request, None, None))
    second = asyncio.run(limiter(request, None, None))
    third = asyncio.run(limiter(request, None, None))
    assert first["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert second["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert third["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_search_limiter_latches_failed_web_search():
    limiter = SearchCallLimiter(4, maximum_web=3, maximum_total=12)
    request = {"tool_name": "mcp__web__search_web"}

    assert (
        asyncio.run(limiter(request, None, None))["hookSpecificOutput"][
            "permissionDecision"
        ]
        == "allow"
    )
    asyncio.run(
        limiter.post({**request, "tool_response": {"is_error": True}}, None, None)
    )
    assert (
        asyncio.run(limiter(request, None, None))["hookSpecificOutput"][
            "permissionDecision"
        ]
        == "deny"
    )


def test_sdk_adapter_streams_reasoning_tool_result_and_answer():
    adapter = SDKEventAdapter(
        show_reasoning=True, policy=_local_tool_event_policy(None)
    )
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
        "usage",
        "done",
    ]
    assert events[3]["args"] == {"query": "VLMs", "top_k": 3}
    assert events[4]["results"] == [{"route_id": "1"}]


def test_local_tool_limiter_denies_seventh_parallel_batch_without_call_slots():
    limiter = SearchCallLimiter(
        maximum=12, maximum_web=12, maximum_total=12, maximum_rounds=6
    )
    for round_number in range(1, 7):
        tool_id = f"round-{round_number}"
        limiter.register_round([tool_id])
        decision = asyncio.run(
            limiter(
                {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": tool_id},
                tool_id,
                None,
            )
        )
        assert decision["hookSpecificOutput"]["permissionDecision"] == "allow"
    denied_ids = ["round-7-a", "round-7-b"]
    limiter.register_round(denied_ids)
    decisions = [
        asyncio.run(
            limiter(
                {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": tool_id},
                tool_id,
                None,
            )
        )
        for tool_id in denied_ids
    ]
    assert all(
        item["hookSpecificOutput"]["permissionDecision"] == "deny" for item in decisions
    )
    assert limiter.total_calls == 6
    assert limiter.rounds_denied == 1
    assert limiter.tooling_closed


def test_local_tool_limiter_counts_parallel_calls_as_one_round_then_sequential():
    limiter = SearchCallLimiter(
        maximum=12, maximum_web=12, maximum_total=12, maximum_rounds=1
    )

    for tool_id in ("parallel-a", "parallel-b"):
        decision = asyncio.run(
            limiter(
                {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": tool_id},
                tool_id,
                None,
            )
        )
        assert decision["hookSpecificOutput"]["permissionDecision"] == "allow"

    assert limiter.rounds_started == 1
    assert limiter.rounds_executed == 1
    for tool_id in ("parallel-a", "parallel-b"):
        asyncio.run(
            limiter.post(
                {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": tool_id},
                tool_id,
                None,
            )
        )

    decision = asyncio.run(
        limiter(
            {"tool_name": SEARCH_TOOL_NAME, "tool_use_id": "parallel-a"},
            "parallel-a",
            None,
        )
    )
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert limiter.rounds_started == 2
    assert limiter.rounds_executed == 1
    assert limiter.rounds_denied == 1


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


def test_sdk_adapter_does_not_reset_partial_flags_on_intermediate_snapshots():
    adapter = SDKEventAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1",
            session_id="s",
            event={"type": "message_start", "message": {}},
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Same plan"},
            },
        ),
        AssistantMessage(model="test", content=[]),
        AssistantMessage(
            model="test",
            content=[ThinkingBlock(thinking="Same plan", signature="sig")],
        ),
        StreamEvent(
            uuid="4",
            session_id="s",
            event={"type": "content_block_stop", "index": 0},
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert events == [
        {"type": "reasoning_start"},
        {"type": "reasoning_delta", "text": "Same plan"},
        {"type": "reasoning_end"},
    ]


def test_sdk_adapter_closes_reasoning_before_next_message_start():
    adapter = SDKEventAdapter(show_reasoning=True)
    messages = [
        StreamEvent(
            uuid="1", session_id="s", event={"type": "message_start", "message": {}}
        ),
        StreamEvent(
            uuid="2",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
        StreamEvent(
            uuid="3",
            session_id="s",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "First"},
            },
        ),
        StreamEvent(
            uuid="4", session_id="s", event={"type": "message_start", "message": {}}
        ),
        StreamEvent(
            uuid="5",
            session_id="s",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        ),
    ]

    events = [event for message in messages for event in adapter.feed(message)]

    assert [event["type"] for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "reasoning_start",
    ]


def test_sdk_adapter_surfaces_hugging_face_billing_errors():
    adapter = SDKEventAdapter(show_reasoning=False)

    events = adapter.feed(
        AssistantMessage(model="test", content=[], error="billing_error")
    )

    assert events == [
        {
            "type": "error",
            "code": "hf_inference_billing_exhausted",
            "message": (
                "Hugging Face could not bill this request. Your included credits "
                "may be exhausted; enable or review pay-as-you-go billing in Settings."
            ),
        }
    ]


@pytest.mark.parametrize(
    ("provider_error", "code"),
    [
        ("authentication_failed", "hf_inference_credential_expired"),
        ("rate_limit", "provider_rate_limit"),
        ("server_error", "provider_unavailable"),
        ("invalid_request", "provider_invalid_request"),
        ("unknown", "provider_error"),
    ],
)
def test_sdk_adapter_keeps_provider_failures_distinct(provider_error, code):
    events = SDKEventAdapter(show_reasoning=False).feed(
        AssistantMessage(model="test", content=[], error=provider_error)
    )

    assert events[0]["type"] == "error"
    assert events[0]["code"] == code


def test_sdk_adapter_hides_leading_whitespace_and_over_budget_searches():
    adapter = SDKEventAdapter(show_reasoning=True, policy=_local_tool_event_policy(2))
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
    def __init__(self, papers, conference_rows=None):
        self.papers = papers
        self.conference_rows = conference_rows or []
        self.closed = False

    def query(self, *entities):
        if len(entities) == 1 and entities[0] is chat_mcp.DBPaper:
            return _FakeQuery(self.papers)
        if len(entities) == 2 and entities[1] is chat_mcp.DBConference:
            return _FakeQuery(self.conference_rows)
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
        conference="Legacy Conference",
        citation_count=4,
    )
    session = _FakeSession(
        [paper], [(9, SimpleNamespace(name="Linked Conference", year=2026))]
    )

    class FakePaperService:
        def __init__(self, _db):
            pass

        def search_papers(self, query, limit, mode):
            assert query == "model"
            assert limit == 3
            assert mode == "keyword"
            return [SimpleNamespace(id="9")]

        def hydrate_cards(self, papers, include_resources):
            assert papers == [paper]
            assert include_resources
            return [
                SimpleNamespace(
                    id="9",
                    arxiv_id=None,
                    source="external",
                    source_url="https://example.com/release",
                    thumbnail_url="/api/thumbnails/custom/9.webp",
                    title="Release",
                    abstract="x" * 5_000,
                    authors=["Lab"],
                    published=date(2026, 7, 1),
                    conference="Legacy Conference",
                    citation_count=4,
                    tasks=[SimpleNamespace(name="Language Modeling", slug="lm")],
                    methods=[SimpleNamespace(name="Transformer", slug="transformer")],
                    repositories=[
                        SimpleNamespace(
                            url="https://github.com/acme/model", num_stars=10
                        )
                    ],
                    project_pages=[SimpleNamespace(url="https://acme.example/model")],
                )
            ]

    monkeypatch.setattr(chat_mcp, "PaperService", FakePaperService)
    payload = chat_mcp.search_papers_payload(
        "model", 3, session_factory=lambda: session
    )
    hit = payload["results"][0]
    assert session.closed
    assert hit["route_id"] == "9"
    assert hit["metadata"]["source"] == "external"
    assert hit["metadata"]["thumbnail_url"] == "/api/thumbnails/custom/9.webp"
    assert hit["metadata"]["conference"] == "Linked Conference"
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
            "hf_token": "shared-nielsr-token",
            "chat_max_search_calls": 2,
        }
    )
    options, _ = build_agent_options(
        settings, tmp_path, provider_token="connected-user-token"
    )
    assert options.tools == []
    assert options.allowed_tools == [SEARCH_TOOL_NAME]
    assert options.setting_sources == []
    assert options.skills == []
    assert options.plugins == []
    assert options.fallback_model is None
    assert options.env["ANTHROPIC_API_KEY"] == "connected-user-token"
    assert options.env["ANTHROPIC_AUTH_TOKEN"] == "connected-user-token"
    assert options.env["ANTHROPIC_BASE_URL"] == "https://router.huggingface.co"
    assert "shared-nielsr-token" not in options.env.values()
    assert "HF_BILL_TO" not in options.env
    assert "ANTHROPIC_CUSTOM_HEADERS" not in options.env
    assert "at most 2 times" in options.system_prompt
    assert "mcp__web__search_web" not in options.allowed_tools
    assert "mcp__web__search_web" in options.disallowed_tools
    assert "web" not in options.mcp_servers
    assert "search_web" not in options.system_prompt
    assert (
        "[repo_id](https://huggingface.co/datasets/<repo_id>)" in options.system_prompt
    )
    assert "[owner/repo](https://github.com/owner/repo)" in options.system_prompt
    assert "Never output a bare repository" in options.system_prompt
    assert (
        "Always favor native paper hyperlinks instead of arXiv links, unless the user "
        "explicitly asks for an arXiv link." in options.system_prompt
    )
    assert "When comparing papers, prefer a Markdown table." in options.system_prompt

    openrouter, _ = build_agent_options(
        settings,
        tmp_path,
        provider_token="openrouter-token",
        provider_base_url="https://openrouter.ai/api",
        model_route=settings.chat_deepseek_v4_flash_openrouter_route,
    )
    assert openrouter.model == "deepseek/deepseek-v4-flash-0731"
    assert openrouter.env["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"
    assert openrouter.env["ANTHROPIC_AUTH_TOKEN"] == "openrouter-token"

    web, _ = build_agent_options(
        settings,
        tmp_path,
        provider_token="connected-user-token",
        web_search_enabled=True,
        owner_hash="a" * 64,
    )
    assert "mcp__web__search_web" in web.allowed_tools
    assert "mcp__web__search_web" not in web.disallowed_tools
    assert "web" in web.mcp_servers
    assert "search_web" in web.system_prompt


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


def test_completed_turn_persists_finish_reason_in_authenticated_history():
    from backend.routers.chat import _message

    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    user_message_id = uuid.uuid4()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="hf-user",
        active_turn_id=turn_id,
        last_sequence=1,
        message_count=1,
        projection_bytes=0,
        updated_at=None,
    )
    user_message = SimpleNamespace(status="generating")

    class FakeResult:
        def scalar_one_or_none(self):
            return session

    class FakeDB:
        def __init__(self):
            self.added = []

        def execute(self, _query):
            return FakeResult()

        def get(self, _model, key):
            return user_message if key == user_message_id else None

        def add(self, value):
            self.added.append(value)

        def flush(self):
            for value in self.added:
                value.revision = 1
                value.created_at = datetime.now(UTC)

    db = FakeDB()
    admission = TurnAdmission(
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=user_message_id,
        selected_model="smoke-model",
        model_route="smoke-route",
        sdk_session_id=None,
        sdk_project_key=None,
        is_first_turn=False,
    )

    assistant = ChatSessionService(db, get_settings()).complete_turn(
        ChatOwner(hf_user_id="hf-user", hf_username="tester"),
        admission,
        answer="Bounded answer",
        citations=[],
        followups=[],
        display_blocks=[],
        finish_reason="scope_blocked",
    )

    assert assistant.finish_reason == "scope_blocked"
    assert _message(assistant).finish_reason == "scope_blocked"


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
                provider_token="connected-user-token",
                model_route=settings.chat_glm_route,
                session_store=None,
                resume=None,
            )
        ]

    monkeypatch.setattr(chat_agent_service, "sdk_query", fake_query)
    events = asyncio.run(collect())
    assert events == [
        {
            "type": "error",
            "code": "provider_timeout",
            "message": "The model provider timed out. Try again shortly.",
        }
    ]
    assert state["closed"] is True


def test_local_agent_max_turns_runs_one_same_session_tool_free_finalizer(monkeypatch):
    from backend.chat_execution_policy import FINALIZER_PROMPT
    from backend.services import chat_agent_service

    calls = []

    def fake_query(*, prompt, options):
        calls.append((prompt, options))

        async def messages():
            if len(calls) == 1:
                yield ResultMessage(
                    subtype="error_max_turns",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=True,
                    num_turns=9,
                    session_id="session-a",
                    usage={"input_tokens": 10},
                )
            else:
                yield AssistantMessage(
                    model="test", content=[TextBlock(text="Recovered answer")]
                )
                yield ResultMessage(
                    subtype="success",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=False,
                    num_turns=1,
                    session_id="session-a",
                    usage={"output_tokens": 4},
                )

        return messages()

    async def collect():
        settings = get_settings().model_copy(update={"chat_timeout_seconds": 30})
        return [
            event
            async for event in stream_agent_events(
                "Research this",
                settings,
                provider_token="connected-user-token",
                model_route=settings.chat_glm_route,
                session_store=object(),
                resume=None,
            )
        ]

    monkeypatch.setattr(chat_agent_service, "sdk_query", fake_query)
    events = asyncio.run(collect())
    assert len(calls) == 2
    assert calls[1][0] == FINALIZER_PROMPT
    assert calls[1][1].resume == "session-a"
    assert calls[1][1].max_turns == 1
    assert calls[1][1].tools == []
    assert calls[1][1].allowed_tools == []
    assert [event["type"] for event in events] == [
        "_sdk_session",
        "usage",
        "answer_delta",
        "usage",
        "_execution_telemetry",
        "done",
    ]
    assert events[-1]["finish_reason"] == "success"
    assert FINALIZER_PROMPT not in json.dumps(events)


def test_local_agent_skips_finalizer_without_minimum_deadline_window(monkeypatch):
    from backend.services import chat_agent_service

    calls = 0

    def fake_query(*, prompt, options):
        nonlocal calls
        calls += 1

        async def messages():
            yield ResultMessage(
                subtype="error_max_turns",
                duration_ms=1,
                duration_api_ms=1,
                is_error=True,
                num_turns=9,
                session_id="session-a",
            )

        return messages()

    async def collect():
        settings = get_settings().model_copy(update={"chat_timeout_seconds": 5})
        return [
            event
            async for event in stream_agent_events(
                "Research this",
                settings,
                provider_token="connected-user-token",
                model_route=settings.chat_glm_route,
                session_store=object(),
                resume=None,
            )
        ]

    monkeypatch.setattr(chat_agent_service, "sdk_query", fake_query)
    events = asyncio.run(collect())
    assert calls == 1
    assert events[-2]["type"] == "_execution_telemetry"
    assert events[-2]["finalizer_attempted"] is False
    assert events[-2]["finalizer_outcome"] == "insufficient_time"
    assert events[-1] == {
        "type": "done",
        "followups": [],
        "finish_reason": "tool_limit",
    }
