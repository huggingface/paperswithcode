from __future__ import annotations

import asyncio
import importlib
import json
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from backend.config import Settings
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


class HangingSyntheticTransport(FakeSyntheticTransport):
    async def stream_turn(self, session_id):
        self.calls.append("stream")
        assert session_id == "synthetic-session"
        await asyncio.sleep(1)
        if False:
            yield {}


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


def test_synthetic_probe_bounds_lifecycle_and_still_cleans_up():
    transport = HangingSyntheticTransport()

    result = asyncio.run(
        run_synthetic_chat(
            "production",
            transport=transport,
            now=NOW,
            lifecycle_timeout_seconds=0.001,
        )
    )

    assert result.state == FindingState.DEGRADED
    assert result.incident_signature == "chat:synthetic:timeout"
    assert transport.deleted is True
    assert transport.calls[-3:] == ["delete", "absent", "close"]


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


def test_critical_alert_forces_at_most_once_per_four_hours():
    job = importlib.import_module("backend.scripts.run_chat_synthetic_probe")
    operational_state = monitor.empty_state()
    operational_state["events"] = [
        monitor.new_event(
            "chat_runtime_critical",
            now=NOW + timedelta(minutes=1),
        ),
        monitor.new_event(
            "chat_runtime_critical",
            now=NOW + timedelta(minutes=2),
        ),
    ]

    assert job._critical_alert_after(
        operational_state,
        NOW,
        None,
        NOW + timedelta(minutes=1),
    )
    assert not job._critical_alert_after(
        operational_state,
        NOW,
        NOW + timedelta(minutes=1),
        NOW + timedelta(minutes=2),
    )
    assert job._critical_alert_after(
        operational_state,
        NOW,
        NOW + timedelta(minutes=1),
        NOW + timedelta(hours=4, minutes=1),
    )


def test_separate_synthetic_job_runs_release_trigger_and_persists_before_delivery(
    monkeypatch, tmp_path, capsys
):
    job = importlib.import_module("backend.scripts.run_chat_synthetic_probe")
    settings = Settings(
        environment="production",
        release_id="new-release",
        chat_enabled=True,
        chat_operational_alerts_enabled=True,
        cron_log_dir=str(tmp_path),
    )
    state = monitor.empty_state()
    calls = []

    async def collect(active_state, environment, now, *, force=False):
        calls.append((environment, force))
        active_state["last_synthetic_probe_at"] = now.isoformat()
        return []

    async def deliver(active_state, _settings):
        assert active_state["last_synthetic_probe_at"] == NOW.isoformat()
        assert calls == [("production", True)]
        return 0

    monkeypatch.setattr(job, "get_settings", lambda: settings)
    monkeypatch.setattr(job, "synthetic_mutation_pause_reason", lambda: None)
    monkeypatch.setattr(job, "load_state", lambda _path: state)
    monkeypatch.setattr(job, "collect_synthetic_events", collect)
    monkeypatch.setattr(job, "deliver_pending", deliver)
    monkeypatch.setattr(job, "datetime", SimpleNamespace(now=lambda _tz: NOW))
    writes = []
    monkeypatch.setattr(
        job,
        "write_state",
        lambda path, payload: writes.append((path.name, dict(payload))),
    )
    health = []
    monkeypatch.setattr(
        job,
        "write_health_record",
        lambda _directory, payload, **_kwargs: health.append(payload),
    )
    monkeypatch.setattr(sys, "argv", ["run_chat_synthetic_probe"])

    assert job.main() == 0
    assert len(writes) == 2
    assert health[-1]["status"] == "healthy"
    assert json.loads(capsys.readouterr().out)["status"] == "healthy"


def test_separate_synthetic_job_pauses_paid_work_in_manual_mode(
    monkeypatch, tmp_path, capsys
):
    job = importlib.import_module("backend.scripts.run_chat_synthetic_probe")
    settings = Settings(
        environment="production",
        chat_enabled=True,
        chat_operational_alerts_enabled=True,
        cron_log_dir=str(tmp_path),
    )
    monkeypatch.setattr(job, "get_settings", lambda: settings)
    monkeypatch.setattr(job, "synthetic_mutation_pause_reason", lambda: "manual_mode")
    monkeypatch.setattr(
        job,
        "collect_synthetic_events",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("paid synthetic chat must remain paused")
        ),
    )
    health = []
    monkeypatch.setattr(
        job,
        "write_health_record",
        lambda _directory, payload, **_kwargs: health.append(payload),
    )
    monkeypatch.setattr(job, "datetime", SimpleNamespace(now=lambda _tz: NOW))
    monkeypatch.setattr(sys, "argv", ["run_chat_synthetic_probe"])

    assert job.main() == 0
    assert health == [
        {
            "environment": "production",
            "status": "paused",
            "reason_code": "manual_mode",
            "completed_at": NOW.isoformat(),
            "pending": 0,
            "new_events": 0,
            "delivered": 0,
            "release_id": settings.release_id,
        }
    ]
    assert json.loads(capsys.readouterr().out)["status"] == "paused"
