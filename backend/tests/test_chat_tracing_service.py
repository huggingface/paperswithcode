from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.config import Settings
from backend.services import chat_tracing_service as tracing


class Observation:
    def __init__(self, name: str, **fields):
        self.name = name
        self.fields = fields
        self.children: list[Observation] = []
        self.ended = False
        self.trace_id = "a" * 32

    def start_observation(self, *, name: str, **fields):
        child = Observation(name, **fields)
        self.children.append(child)
        return child

    def update(self, **fields):
        self.fields.update(fields)
        return self

    def end(self):
        self.ended = True
        return self


class Client:
    def __init__(self):
        self.root: Observation | None = None

    def create_trace_id(self, *, seed: str):
        assert seed == "request-1"
        return "b" * 32

    def start_observation(self, *, name: str, **fields):
        self.root = Observation(name, **fields)
        return self.root


def test_chat_trace_captures_hierarchy_usage_and_context(monkeypatch):
    client = Client()
    propagated = {}

    @contextmanager
    def attributes(**values):
        propagated.update(values)
        yield

    monkeypatch.setattr(tracing, "_configured_client", lambda _settings: client)
    monkeypatch.setattr(tracing, "propagate_attributes", attributes)
    settings = Settings(
        environment="staging",
        release_id="release-1",
        chat_langfuse_enabled=True,
    )

    effective_prompt = "<paper_context>exact context</paper_context>\nFind papers"
    with tracing.trace_chat_turn(
        settings=settings,
        request_id="request-1",
        session_id="session-1",
        user_id="private-user",
        prompt=effective_prompt,
        display_prompt="Find papers",
        model="provider/model",
        execution_backend="modal_cli",
        is_replacement=False,
    ) as trace:
        trace.record_event("sandbox_start", {"session_id": "session-1"})
        trace.record_event(
            "_latency",
            {
                "phase": "sandbox_acquisition_ms",
                "elapsed_ms": 40,
                "acquisition_outcome": "pool_hit",
            },
        )
        trace.record_event("sandbox_ready", {"cold_start_ms": 0})
        trace.record_event(
            "_latency", {"phase": "capability_install_ms", "elapsed_ms": 55}
        )
        trace.record_event("_latency", {"phase": "sdk_dispatch_ms", "elapsed_ms": 60})
        trace.record_event(
            "_latency", {"phase": "first_worker_delta", "elapsed_ms": 100}
        )
        trace.start_title("title-model")
        trace.finish_title("Paper search", fallback=False)
        trace.start_tool(
            {"id": "tool-1", "name": "Bash", "args": {"command": "pwc search"}}
        )
        trace.finish_tool(
            {
                "id": "tool-1",
                "status": "success",
                "took_ms": 12,
                "content": [{"type": "text", "text": "result"}],
            }
        )
        trace.start_tool(
            {
                "id": "tool-2",
                "name": "WebFetch",
                "args": {"url": "https://example.com"},
            }
        )
        trace.finish_tool(
            {
                "id": "tool-2",
                "status": "success",
                "took_ms": 20,
                "content": [{"type": "text", "text": "page"}],
            }
        )
        trace.record_usage(
            {
                "usage": {"input_tokens": 10, "output_tokens": 4},
                "total_cost_usd": 0.02,
            }
        )
        trace.finish("Here are the papers", "success")

    assert client.root is not None and client.root.ended
    children = {child.name: child for child in client.root.children}
    assert set(children) == {
        "acquire-sandbox",
        "install-sandbox-capability",
        "dispatch-model-request",
        "generate-research-response",
        "generate-session-title",
        "run-bash-command",
        "fetch-web-page",
    }
    generation = children["generate-research-response"]
    expected_effective_input = [{"role": "user", "content": effective_prompt}]
    assert client.root.fields["input"] == expected_effective_input
    assert generation.fields["input"] == expected_effective_input
    assert children["generate-session-title"].fields["input"] == [
        {"role": "user", "content": "Find papers"}
    ]
    assert generation.fields["usage_details"] == {"input": 10, "output": 4}
    assert generation.fields["cost_details"] == {"total": 0.02}
    assert generation.fields["model"] == "provider/model"
    assert generation.fields["completion_start_time"].tzinfo is UTC
    assert children["acquire-sandbox"].fields["output"] == {
        "acquisition_outcome": "pool_hit",
        "elapsed_ms": 40,
    }
    assert children["install-sandbox-capability"].ended
    assert children["dispatch-model-request"].ended
    assert children["run-bash-command"].fields["as_type"] == "tool"
    assert children["fetch-web-page"].fields["as_type"] == "tool"
    assert propagated["session_id"] == "session-1"
    assert propagated["environment"] == "staging"
    assert propagated["user_id"] != "private-user"


def test_langfuse_client_exports_trace_content_without_a_mask(monkeypatch):
    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(tracing, "Langfuse", client)
    tracing._client.cache_clear()
    try:
        tracing._client(
            "staging",
            "release-1",
            "pk-test",
            "sk-test",
            "https://example.com",
        )
    finally:
        tracing._client.cache_clear()

    assert "mask_otel_spans" not in captured


def test_private_paper_trace_never_exports_manuscript_or_tool_content(monkeypatch):
    client = Client()

    @contextmanager
    def attributes(**_values):
        yield

    monkeypatch.setattr(tracing, "_configured_client", lambda _settings: client)
    monkeypatch.setattr(tracing, "propagate_attributes", attributes)
    settings = Settings(environment="staging", chat_langfuse_enabled=True)
    manuscript = "MANUSCRIPT-CANARY: theorem proof and unpublished result"

    with tracing.trace_chat_turn(
        settings=settings,
        request_id="request-1",
        session_id="session-1",
        user_id="private-user",
        prompt=manuscript,
        display_prompt=manuscript,
        model="gpt-5.6-luna@openai",
        execution_backend="pi",
        is_replacement=False,
        content_free=True,
    ) as trace:
        trace.start_title("title-model")
        trace.finish_title(manuscript, fallback=False)
        trace.start_tool(
            {
                "id": "tool-1",
                "name": "Bash",
                "args": {"command": f"printf '%s' '{manuscript}'"},
            }
        )
        trace.finish_tool(
            {
                "id": "tool-1",
                "status": "success",
                "content": [{"type": "text", "text": manuscript}],
            }
        )
        trace.finish(manuscript, "success")

    assert client.root is not None
    serialized = repr(client.root.fields) + repr(
        [(child.name, child.fields) for child in client.root.children]
    )
    assert manuscript not in serialized
    assert client.root.fields["metadata"]["content_policy"] == "content-free"
    assert all(child.name != "generate-session-title" for child in client.root.children)


def test_tracing_supports_production_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.com")
    monkeypatch.setattr(tracing, "_client", lambda *_args: object())
    settings = Settings(environment="production", chat_langfuse_enabled=True)
    assert tracing._configured_client(settings) is not None


def test_provider_request_trace_is_content_free_and_records_usage(monkeypatch):
    client = Client()
    monkeypatch.setattr(tracing, "_configured_client", lambda _settings: client)
    settings = Settings(environment="staging", chat_langfuse_enabled=True)

    trace = tracing.start_provider_request_trace(
        settings=settings,
        trace_id="b" * 32,
        turn_id="turn-1",
        call_sequence=2,
        model="provider/model",
        provider_mode="openrouter_funded",
        reasoning_effort="low",
        offered_tool_count=4,
        offered_tool_names=["create_view", "read", "read_me", "search_web"],
        offered_tool_digest="a" * 64,
        mcp_provider_states={"excalidraw": "ready"},
    )
    trace.first_byte(125)
    trace.finish(
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=40,
            cache_read_tokens=75,
            cache_creation_tokens=None,
            reasoning_tokens=30,
            cost_microusd=2500,
            generation_id="gen-1",
            provider="Baseten",
        ),
        status_code=200,
        tool_call_returned=True,
    )

    assert client.root is not None and client.root.ended
    assert client.root.fields["metadata"]["offered_tool_names"] == [
        "create_view",
        "read",
        "read_me",
        "search_web",
    ]
    assert client.root.fields["metadata"]["tool_call_returned"] is True
    assert "input" not in client.root.fields
    assert "output" not in client.root.fields
    assert client.root.fields["trace_context"] == {"trace_id": "b" * 32}
    assert client.root.fields["metadata"]["reasoning_effort"] == "low"
    assert client.root.fields["metadata"]["ttft_ms"] == 125
    assert client.root.fields["metadata"]["upstream_provider"] == "Baseten"
    assert client.root.fields["usage_details"] == {
        "input": 100,
        "output": 40,
        "cache_read_input": 75,
        "reasoning": 30,
    }
    assert client.root.fields["cost_details"] == {"total": 0.0025}
    assert isinstance(client.root.fields["completion_start_time"], datetime)


def test_unfinished_operational_spans_close_as_warnings():
    root = Observation("root")
    trace = tracing.ChatTurnTrace(
        root,
        prompt="Find papers",
        model="provider/model",
        execution_backend="modal_cli",
    )

    trace.record_event("sandbox_start", {})
    acquisition = trace.sandbox_acquisition
    trace.close()

    assert acquisition is not None and acquisition.ended
    assert acquisition.fields["level"] == "WARNING"


def test_warm_assignment_diagnostics_survive_in_terminal_metadata():
    root = Observation("root")
    trace = tracing.ChatTurnTrace(
        root,
        prompt="Find papers",
        model="provider/model",
        execution_backend="modal_cli",
    )
    trace.record_event(
        "_latency",
        {
            "phase": "assignment_fallback",
            "elapsed_ms": 37,
            "failure_stage": "dispatch_write",
            "failure_class": "BrokenPipeError",
            "attempt_kind": "pool",
        },
    )
    trace.finish("Recovered answer", "success")
    trace.close()

    assert root.fields["metadata"] == {
        "warm_assignment_failure_stage": "dispatch_write",
        "warm_assignment_failure_class": "BrokenPipeError",
        "warm_assignment_attempt_kind": "pool",
        "warm_assignment_retry_overhead_ms": 37,
        "terminal_status": "success",
    }


def test_error_trace_records_sanitized_terminal_code():
    root = Observation("root")
    trace = tracing.ChatTurnTrace(
        root,
        prompt="Find papers",
        model="provider/model",
        execution_backend="modal_cli",
    )

    trace.finish(
        "Partial answer",
        "error",
        terminal_code="hf_inference_billing_exhausted",
    )
    trace.close()

    generation = root.children[0]
    expected_metadata = {
        "terminal_status": "error",
        "terminal_code": "hf_inference_billing_exhausted",
    }
    assert generation.fields["level"] == "ERROR"
    assert generation.fields["status_message"] == "hf_inference_billing_exhausted"
    assert generation.fields["metadata"] == expected_metadata
    assert root.fields["metadata"] == expected_metadata


def test_interrupted_trace_is_warning_with_reason():
    root = Observation("root")
    trace = tracing.ChatTurnTrace(
        root,
        prompt="Find papers",
        model="provider/model",
        execution_backend="modal_cli",
    )

    trace.finish(
        "",
        "interrupted",
        interruption_reason="client_disconnect",
    )
    trace.close()

    generation = root.children[0]
    expected_metadata = {
        "terminal_status": "interrupted",
        "interruption_reason": "client_disconnect",
    }
    assert generation.fields["level"] == "WARNING"
    assert generation.fields["status_message"] == "client_disconnect"
    assert generation.fields["metadata"] == expected_metadata
    assert root.fields["level"] == "WARNING"
    assert root.fields["metadata"] == expected_metadata
