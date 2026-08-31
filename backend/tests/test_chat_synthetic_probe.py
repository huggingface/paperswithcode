from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.services.autonomous_cron_probe import FindingState
from backend.services.chat_synthetic_probe import run_synthetic_chat
from backend.scripts import monitor_chat_operational_alerts as monitor
from backend.services.chat_synthetic_probe import SyntheticChatResult


NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


class FakeSyntheticTransport:
    def __init__(self, *, terminal: str = "done", reopenable: bool = True):
        self.terminal = terminal
        self.reopenable = reopenable
        self.deleted = False
        self.calls = []

    async def verify_login(self):
        self.calls.append("login")
        return True

    async def create_session(self):
        self.calls.append("admission")
        return "synthetic-session"

    async def stream_turn(self, session_id):
        self.calls.append("stream")
        assert session_id == "synthetic-session"
        yield {"type": "stream_start"}
        yield {"type": "answer_delta"}
        yield {"type": self.terminal}

    async def session_is_reopenable(self, session_id):
        self.calls.append("reopen")
        assert session_id == "synthetic-session"
        return self.reopenable

    async def delete_session(self, session_id):
        self.calls.append("delete")
        assert session_id == "synthetic-session"
        self.deleted = True

    async def session_is_absent(self, session_id):
        self.calls.append("absent")
        return self.deleted

    async def close(self):
        self.calls.append("close")


def test_synthetic_probe_verifies_full_lifecycle_and_cleanup():
    transport = FakeSyntheticTransport()

    result = asyncio.run(run_synthetic_chat("production", transport=transport, now=NOW))

    assert result.state == FindingState.HEALTHY
    assert result.steps == {
        "login": "healthy",
        "admission": "healthy",
        "first_token": "healthy",
        "complete_stream": "healthy",
        "persistence_reopen": "healthy",
        "cleanup": "healthy",
    }
    assert transport.calls == [
        "login",
        "admission",
        "stream",
        "reopen",
        "delete",
        "absent",
        "close",
    ]
    payload = repr(result.as_dict()).lower()
    assert "prompt" not in payload
    assert "answer" not in payload
    assert "synthetic-session" not in payload


def test_synthetic_probe_classifies_stream_failure_and_still_cleans_up():
    transport = FakeSyntheticTransport(terminal="error", reopenable=False)

    result = asyncio.run(run_synthetic_chat("production", transport=transport, now=NOW))

    assert result.state == FindingState.DEGRADED
    assert result.incident_signature == "chat:stream:terminal_error"
    assert result.steps["complete_stream"] == "degraded"
    assert transport.deleted is True


def test_synthetic_probe_rejects_non_production_target():
    result = asyncio.run(
        run_synthetic_chat("staging", transport=FakeSyntheticTransport(), now=NOW)
    )

    assert result.state == FindingState.UNKNOWN
    assert result.incident_signature == "chat:synthetic:environment_refused"


def test_monitor_runs_synthetic_every_four_hours_and_after_release(monkeypatch):
    state = monitor.empty_state()
    calls = []
    healthy = SyntheticChatResult(
        "production",
        FindingState.HEALTHY,
        "chat:synthetic:healthy",
        {"cleanup": "healthy"},
        NOW.isoformat(),
    )

    async def fake_run(environment, *, now):
        calls.append((environment, now))
        return healthy

    monkeypatch.setattr(monitor, "run_synthetic_chat", fake_run)

    assert asyncio.run(monitor.collect_synthetic_events(state, "production", NOW)) == []
    assert len(calls) == 1
    assert (
        asyncio.run(
            monitor.collect_synthetic_events(
                state, "production", NOW.replace(hour=15, minute=59)
            )
        )
        == []
    )
    assert len(calls) == 1
    assert (
        asyncio.run(
            monitor.collect_synthetic_events(
                state, "production", NOW.replace(hour=16), force=True
            )
        )
        == []
    )
    assert len(calls) == 2


def test_monitor_pages_on_synthetic_failure_without_content(monkeypatch):
    state = monitor.empty_state()
    failed = SyntheticChatResult(
        "production",
        FindingState.DEGRADED,
        "chat:persistence:reopen_failed",
        {"persistence_reopen": "degraded", "cleanup": "healthy"},
        NOW.isoformat(),
    )

    async def fake_run(_environment, *, now):
        return failed

    monkeypatch.setattr(monitor, "run_synthetic_chat", fake_run)

    events = asyncio.run(monitor.collect_synthetic_events(state, "production", NOW))

    assert [event["signal"] for event in events] == ["chat_synthetic_failure"]
    assert events[0]["classifications"] == {"chat:persistence:reopen_failed": 1}
    assert "prompt" not in repr(events).lower()
    assert "answer" not in repr(events).lower()
