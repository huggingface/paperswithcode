"""Persistent agent reconnect, preflight, and resume contracts."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from backend.chat_sandbox_worker import (
    agent,
)


def test_persistent_agent_reconnects_client_to_apply_model_metadata(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            calls.append(("init", options.model, options.resume))
            self._query = SimpleNamespace(
                _transcript_mirror_batcher=SimpleNamespace(
                    _flush_task=SimpleNamespace(wait=self.wait_for_flush),
                    flush=self.flush,
                )
            )

        async def connect(self, prompt):
            calls.append(("connect", prompt))

        async def query(self, prompt):
            calls.append(("query", prompt))

        async def receive_messages(self):
            yield ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id="session-a",
            )

        async def flush(self):
            calls.append(("flush",))

        async def wait_for_flush(self):
            calls.append(("wait_for_flush",))

        async def set_model(self, model):
            calls.append(("model", model))

        async def disconnect(self):
            calls.append(("disconnect",))

        async def interrupt(self):
            calls.append(("interrupt",))

    async def adapted(messages, *, request_id, **_kwargs):
        async for _message in messages:
            pass
        yield {"v": 1, "type": "done", "request_id": request_id}

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    monkeypatch.setattr(agent, "_adapt_messages", adapted)
    settings = agent.WorkerSettings.from_environment()
    worker = agent.PersistentAgent(settings)

    async def run():
        first = [
            event
            async for event in worker.stream(
                {
                    "type": "run_turn",
                    "request_id": "request-1",
                    "prompt": "first",
                    "model": "model-a",
                    "resume": "session-a",
                }
            )
        ]
        second = [
            event
            async for event in worker.stream(
                {
                    "type": "run_turn",
                    "request_id": "request-2",
                    "prompt": "second",
                    "model": "model-b",
                    "resume": "session-a",
                }
            )
        ]
        await worker.close()
        return first, second

    first, second = asyncio.run(run())
    assert [event["type"] for event in first] == [
        "workspace_ready",
        "_execution_telemetry",
        "done",
    ]
    assert [event["type"] for event in second] == [
        "workspace_ready",
        "_execution_telemetry",
        "done",
    ]
    assert [call[0] for call in calls].count("init") == 2
    assert ("model", "model-b") not in calls
    assert calls.count(("connect", None)) == 2
    assert calls.count(("wait_for_flush",)) == 2
    assert calls.count(("flush",)) == 2
    assert calls[-1] == ("disconnect",)


def test_persistent_agent_recovers_max_turns_with_tool_free_same_session(monkeypatch):
    created = []
    monkeypatch.setattr(
        agent, "GUIDE", Path(agent.__file__).with_name("PWC_CLI_SKILL.md")
    )

    class Client:
        def __init__(self, options):
            self.options = options
            created.append(self)
            self._query = SimpleNamespace(
                _transcript_mirror_batcher=SimpleNamespace(
                    _flush_task=SimpleNamespace(wait=self.wait), flush=self.flush
                )
            )

        async def connect(self, prompt):
            return None

        async def query(self, prompt):
            self.prompt = prompt

        async def receive_messages(self):
            if len(created) == 1:
                yield ResultMessage(
                    subtype="error_max_turns",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=True,
                    num_turns=9,
                    session_id="session-a",
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
                )

        async def wait(self):
            return None

        async def flush(self):
            return None

        async def disconnect(self):
            return None

        async def interrupt(self):
            return None

        async def set_model(self, _model):
            return None

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def collect():
        events = [
            event
            async for event in worker.stream(
                {
                    "type": "run_turn",
                    "request_id": "request-1",
                    "prompt": "research",
                    "model": "model-a",
                    "fetchable_urls": [],
                }
            )
        ]
        await worker.close()
        return events

    events = asyncio.run(collect())
    assert len(created) == 2
    assert created[1].options.resume == "session-a"
    assert created[1].options.tools == []
    assert created[1].options.allowed_tools == []
    assert created[1].prompt == agent.FINALIZER_PROMPT
    assert [event["type"] for event in events] == [
        "workspace_ready",
        "_sdk_session",
        "usage",
        "answer_delta",
        "usage",
        "_execution_telemetry",
        "done",
    ]
    assert events[-1]["finish_reason"] == "success"


def test_persistent_agent_preflight_keeps_initialized_client(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            calls.append(("init", options.model, options.resume))

        async def connect(self, prompt):
            calls.append(("connect", prompt))

        async def disconnect(self):
            calls.append(("disconnect",))

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def run():
        await worker.preflight("model-a")
        assert worker.client is not None
        await worker.connect(model="model-a", resume=None)
        await worker.close()

    asyncio.run(run())
    assert [call[0] for call in calls].count("init") == 1
    assert calls.count(("connect", None)) == 1
    assert calls[-1] == ("disconnect",)


def test_persistent_agent_preflight_reconnects_to_resume_session(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            calls.append(("init", options.model, options.resume))

        async def connect(self, prompt):
            calls.append(("connect", prompt))

        async def disconnect(self):
            calls.append(("disconnect",))

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def run():
        await worker.preflight("model-a")
        await worker.connect(model="model-a", resume="session-a")
        await worker.close()

    asyncio.run(run())
    assert calls == [
        ("init", "model-a", None),
        ("connect", None),
        ("disconnect",),
        ("init", "model-a", "session-a"),
        ("connect", None),
        ("disconnect",),
    ]


def test_persistent_agent_reconnects_when_turn_metadata_changes(monkeypatch):
    created = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            self.options = options
            created.append(self)

        async def connect(self, prompt):
            return None

        async def disconnect(self):
            return None

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def run():
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=False,
            hf_username="user-a",
            current_date=date(2026, 8, 10),
        )
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=True,
            hf_username="user-a",
            current_date=date(2026, 8, 10),
        )
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=True,
            hf_username="user-b",
            current_date=date(2026, 8, 10),
        )
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=True,
            hf_username="user-b",
            current_date=date(2026, 8, 11),
        )
        await worker.connect(
            model="model-a",
            resume=None,
            web_search_enabled=True,
            hf_username="user-b",
            current_date=date(2026, 8, 11),
            task_catalog_text="## Complete live task lookup index\n\n- `new` — New",
        )
        await worker.close()

    asyncio.run(run())

    assert len(created) == 5
    metadata = [
        client.options.system_prompt.rsplit("# Turn metadata", 1)[1]
        for client in created
    ]
    assert '"web_search_enabled":false' in metadata[0]
    assert '"web_search_enabled":true' in metadata[1]
    assert '"hf_username":"user-b"' in metadata[2]
    assert '"current_date_utc":"2026-08-11"' in metadata[3]
    assert "`new` — New" in created[4].options.system_prompt


def test_persistent_agent_accepts_resume_hint_before_sdk_session(monkeypatch):
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, _options):
            pass

        async def connect(self, prompt):
            pass

        async def disconnect(self):
            pass

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())

    async def run():
        await worker.connect(model="model-a", resume="session-a")
        await worker.connect(model="model-a", resume="session-b")
        await worker.close()

    asyncio.run(run())


def test_persistent_agent_reconnects_when_durable_resume_moves_back(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        agent,
        "GUIDE",
        Path(agent.__file__).with_name("PWC_CLI_SKILL.md"),
    )

    class Client:
        def __init__(self, options):
            calls.append(("init", options.resume))

        async def connect(self, prompt):
            calls.append(("connect", prompt))

        async def disconnect(self):
            calls.append(("disconnect",))

    monkeypatch.setattr(agent, "ClaudeSDKClient", Client)
    worker = agent.PersistentAgent(agent.WorkerSettings.from_environment())
    worker.client = Client(SimpleNamespace(resume="session-a"))
    worker.model = "model-a"
    worker._record_session_id("session-a")

    asyncio.run(worker.connect(model="model-a", resume="session-b"))

    assert worker.sdk_session_id is None
    assert calls[-3:] == [
        ("disconnect",),
        ("init", "session-b"),
        ("connect", None),
    ]
