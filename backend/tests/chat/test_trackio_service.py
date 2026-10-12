from __future__ import annotations

import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from langfuse import Langfuse
from pydantic import ValidationError

from backend.config import Settings
from backend.services import chat_trackio_service as trackio
from backend.services import chat_tracing_service as tracing


@pytest.fixture
def client(monkeypatch):
    # Exercise queueing/serialization without starting a network worker.
    with monkeypatch.context() as setup:
        setup.setattr(threading.Thread, "start", lambda self: None)
        setup.setattr(trackio.atexit, "register", lambda *args: None)
        result = trackio.TrackioClient(
            "https://test.hf.space", "secret-token", "pwc-chat", "staging", "release-1"
        )
    monkeypatch.setattr(tracing, "configured_trackio_client", lambda settings: result)
    monkeypatch.setattr(
        tracing,
        "_configured_client",
        lambda settings: pytest.fail("Langfuse should not be initialized"),
    )
    return result


def turn(**kwargs):
    return tracing.trace_chat_turn(
        settings=Settings(chat_trackio_enabled=True),
        request_id=kwargs.pop("request_id", "request-1"),
        session_id="session-1",
        user_id="private-user",
        prompt="private prompt",
        model="model-1",
        execution_backend="external_pi",
        is_replacement=False,
        **kwargs,
    )


def take(client):
    # Mirror the worker's dequeue bookkeeping without a network send.
    raw = client.pending.get_nowait()
    client.pending.task_done()
    client._pending_bytes -= len(raw)
    return raw


def payload(client):
    return json.loads(take(client))


def test_turn_span_tree_usage_status_and_content(client):
    with turn() as trace:
        assert trace.trace_id == Langfuse.create_trace_id(seed="request-1")
        trace.start_tool({"id": "tool-1", "name": "Read", "args": {"path": "file.txt"}})
        trace.finish_tool(
            {
                "id": "tool-1",
                "content": "file content",
                "status": "success",
                "took_ms": 10,
            }
        )
        trace.record_usage(
            {"usage": {"input_tokens": 10, "output_tokens": 3}, "total_cost_usd": 0.001}
        )
        trace.finish("answer", "success")
    entry = payload(client)
    data = entry["metrics"]["trace"]
    assert data["messages"] == [
        {"role": "user", "content": "private prompt"},
        {"role": "assistant", "content": "answer"},
    ]
    assert data["metadata"]["session_id"] == "session-1"
    assert data["metadata"]["user_id"] != "private-user"
    root, generation, tool = data["spans"]
    assert root["status"] == "success"
    assert "usage" not in root and "cost_usd" not in root
    assert generation["usage"] == {"input_tokens": 10, "output_tokens": 3}
    assert generation["cost_usd"] == 0.001
    assert generation["parent_id"] == tool["parent_id"] == root["id"]
    assert tool["kind"] == "tool" and tool["output"] == "file content"
    assert all(s["end_time"] >= s["start_time"] for s in data["spans"])
    assert entry["run"].startswith("staging-chat-")


def test_content_free_turn_preserves_policy(client):
    with turn(content_free=True) as trace:
        trace.start_title("title-model")
        trace.start_tool(
            {"id": "t", "name": "Read", "args": {"secret": "hidden-input"}}
        )
        trace.finish_tool({"id": "t", "content": "hidden-output", "status": "error"})
        trace.finish("hidden-answer", "error", terminal_code="worker_error")
    data = payload(client)["metrics"]["trace"]
    encoded = json.dumps(data)
    assert data["messages"] == []
    assert all("input" not in s and "output" not in s for s in data["spans"])
    assert "private prompt" not in encoded and "hidden-" not in encoded
    assert data["spans"][0]["status"] == "error"


def test_exception_and_unfinished_tool_export_once(client):
    with pytest.raises(RuntimeError, match="worker failure"):
        with turn() as trace:
            trace.start_tool({"id": "t", "name": "Bash"})
            raise RuntimeError("worker failure")
    trace.close()
    data = payload(client)["metrics"]["trace"]
    assert data["spans"][0]["status"] == "error"
    assert data["spans"][2]["status"] == "interrupted"
    assert client.pending.empty()


def test_provider_requests_separate_totals_and_preserve_correlation(client):
    trace = tracing.start_provider_request_trace(
        settings=Settings(chat_trackio_enabled=True),
        trace_id="a" * 32,
        turn_id="turn-1",
        call_sequence=2,
        model="model-1",
        provider_mode="openrouter",
        reasoning_effort="high",
    )
    trace.first_byte(50)
    trace.finish(
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=2, cost_microusd=123),
        status_code=200,
    )
    entry = payload(client)
    data = entry["metrics"]["trace"]
    assert entry["run"].startswith("staging-provider-requests-")
    assert data["metadata"]["trace_id"] == "a" * 32
    assert data["metadata"]["ttft_ms"] == 50
    assert data["messages"] == []
    assert data["spans"][0]["usage"] == {"input_tokens": 7, "output_tokens": 2}
    assert data["spans"][0]["cost_usd"] == 0.000123


def test_concurrent_turns_do_not_mix_spans(client):
    def emit(i):
        with turn(request_id=str(i)) as trace:
            trace.start_tool({"id": str(i), "name": "Read"})
            trace.finish_tool({"id": str(i), "content": str(i)})
            trace.finish(str(i), "success")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(emit, range(8)))
    entries = [payload(client)["metrics"]["trace"] for _ in range(8)]
    assert len({e["metadata"]["trace_id"] for e in entries}) == 8
    for entry in entries:
        assert entry["spans"][2]["output"] == entry["messages"][-1]["content"]


def test_queue_and_payload_limits_do_not_raise(client, caplog):
    client.pending = queue.Queue(maxsize=1)
    for _ in range(2):
        with turn() as trace:
            trace.finish("answer", "success")
    assert client.pending.qsize() == 1
    assert "queue full" in caplog.text
    payload(client)
    with turn() as trace:
        trace.finish("x" * trackio.MAX_PAYLOAD_BYTES, "success")
    assert client.pending.empty()
    assert "exceeds 2 MiB" in caplog.text


def test_http_retry_uses_identical_log_id_and_hides_credentials(
    client, monkeypatch, caplog
):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200, json={"data": None})

    real_client = httpx.Client
    monkeypatch.setattr(
        trackio.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw),
    )
    monkeypatch.setattr(trackio.time, "sleep", lambda _: None)
    with turn() as trace:
        trace.finish("answer", "success")
    raw = client.pending.get_nowait()
    client.pending.task_done()
    assert client._send(client._batch_payload([raw])) is True
    assert len(requests) == 2
    assert requests[0].content == requests[1].content
    assert json.loads(requests[0].content)["kwargs"]["logs"] == [json.loads(raw)]
    assert requests[0].headers["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in caplog.text


def test_http_auth_failure_is_not_retried_or_logged_with_body(
    client, monkeypatch, caplog
):
    real_client = httpx.Client
    count = []

    def respond(request):
        count.append(request)
        return httpx.Response(403, text="secret-token")

    monkeypatch.setattr(
        trackio.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw),
    )
    assert client._send(b"{}") is False
    assert len(count) == 1
    assert "403" in caplog.text and "secret-token" not in caplog.text


def test_settings_restrict_credentials_to_space_origin():
    for url in (
        "http://test.hf.space",
        "https://evil.com",
        "https://user:password@test.hf.space",
        "https://test.hf.space/?token=x",
    ):
        with pytest.raises(ValidationError):
            Settings(chat_trackio_url=url)
    assert (
        trackio.configured_trackio_client(
            Settings(chat_trackio_enabled=True, chat_trackio_hf_token="")
        )
        is None
    )
    assert (
        trackio.configured_trackio_client(Settings(chat_trackio_enabled=False)) is None
    )


def test_durable_lifecycle_exports_without_chat_content(client):
    from backend.services.chat_durable_lifecycle_observer import (
        DurableLifecycleObserver,
    )

    observer = DurableLifecycleObserver(Settings(chat_trackio_enabled=True))
    observer("ttft_ms", None, 123)
    observer("typed_failure", "execution_lost", 1)
    latency, failure = payload(client), payload(client)
    assert latency["run"].startswith("staging-lifecycle-")
    # Lifecycle observations are plain metrics, not single-span traces: no
    # messages, no spans, one bounded metric name per event/code pair.
    assert latency["metrics"] == {"lifecycle/ttft_ms": 123}
    assert failure["metrics"] == {"lifecycle/typed_failure/execution_lost": 1}
    assert "trace" not in json.dumps([latency, failure])


def entry_bytes(client, **fields):
    with turn(**fields) as trace:
        trace.finish("answer", "success")
    return take(client)


def test_worker_batches_pending_entries_into_one_request(client, monkeypatch):
    monkeypatch.setattr(trackio, "BATCH_LINGER_SECONDS", 0.01)
    for i in range(3):
        with turn(request_id=str(i)) as trace:
            trace.finish(str(i), "success")
    batch = client._next_batch()
    assert len(batch) == 3
    logs = json.loads(client._batch_payload(batch))["kwargs"]["logs"]
    assert [log["metrics"]["trace"]["messages"][-1]["content"] for log in logs] == [
        "0",
        "1",
        "2",
    ]
    assert client.pending.empty()


def test_worker_caps_batch_size_and_payload_bytes(client, monkeypatch):
    monkeypatch.setattr(trackio, "BATCH_LINGER_SECONDS", 0.01)
    monkeypatch.setattr(trackio, "MAX_BATCH_ENTRIES", 2)
    for i in range(3):
        with turn(request_id=str(i)) as trace:
            trace.finish(str(i), "success")
    assert len(client._next_batch()) == 2
    assert len(client._next_batch()) == 1

    small = entry_bytes(client)
    large = entry_bytes(client)
    monkeypatch.setattr(trackio, "MAX_PAYLOAD_BYTES", len(small) + len(large) - 1)
    client.pending.put_nowait(small)
    client.pending.put_nowait(large)
    assert client._next_batch() == [small]
    # The overflowing entry keeps its place for the next batch.
    assert client.pending.qsize() == 1
    assert client._next_batch() == [large]


def test_queue_byte_budget_drops_and_counts(client, monkeypatch, caplog):
    entry = entry_bytes(client)
    monkeypatch.setattr(trackio, "MAX_QUEUE_BYTES", len(entry) * 2 + 1)
    for _ in range(3):
        with turn() as trace:
            trace.finish("answer", "success")
    assert client.pending.qsize() == 2
    assert caplog.text.count("chat Trackio trace dropped") == 1
    assert "export queue full" in caplog.text
    assert "dropped_since_last_log=1" in caplog.text
    summary = client.summary()
    assert summary["submitted"] == 4 and summary["dropped"] == 1
    assert summary["queued"] == 2 and summary["queued_bytes"] == len(entry) * 2


def test_drop_warnings_are_rate_limited_with_counts(client, monkeypatch, caplog):
    client.pending = queue.Queue(maxsize=1)
    clock = [1000.0]
    monkeypatch.setattr(trackio.time, "monotonic", lambda: clock[0])
    for _ in range(5):
        with turn() as trace:
            trace.finish("answer", "success")
    assert caplog.text.count("chat Trackio trace dropped") == 1
    clock[0] += trackio.DROP_LOG_INTERVAL_SECONDS
    with turn() as trace:
        trace.finish("answer", "success")
    assert caplog.text.count("chat Trackio trace dropped") == 2
    assert "dropped_since_last_log=4" in caplog.text
    assert client.summary()["dropped"] == 5


def test_send_reports_delivery_outcome(client, monkeypatch):
    real_client = httpx.Client
    statuses = iter([200, 400])

    def respond(request):
        return httpx.Response(next(statuses), json={"data": None})

    monkeypatch.setattr(
        trackio.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw),
    )
    first, second = entry_bytes(client), entry_bytes(client)
    assert client._send(client._batch_payload([first, second])) is True
    assert client._send(client._batch_payload([first])) is False


def test_worker_thread_delivers_batches_end_to_end(monkeypatch):
    requests = []
    real_client = httpx.Client

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"data": None})

    monkeypatch.setattr(
        trackio.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw),
    )
    monkeypatch.setattr(trackio.atexit, "register", lambda *args: None)
    live = trackio.TrackioClient(
        "https://test.hf.space", "secret-token", "pwc-chat", "staging", "release-1"
    )
    monkeypatch.setattr(tracing, "configured_trackio_client", lambda settings: live)
    for i in range(5):
        with turn(request_id=str(i)) as trace:
            trace.finish(str(i), "success")
    assert live.flush(timeout=5)
    delivered = [log for request in requests for log in request["kwargs"]["logs"]]
    assert len(delivered) == 5
    assert len(requests) < 5, "entries submitted together should share a POST"
    assert all(request["kwargs"]["hf_token"] == "secret-token" for request in requests)
    summary = live.summary()
    assert summary["sent"] == 5 and summary["failed"] == 0
    assert summary["queued"] == 0 and summary["queued_bytes"] == 0
