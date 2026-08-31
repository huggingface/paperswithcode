from __future__ import annotations

import asyncio
import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from backend.config import Settings
from backend.scripts import monitor_chat_operational_alerts as monitor
from backend.services.chat_operational_alert_service import (
    ProviderHealth,
    lifecycle_window_alerts,
    operational_alert_payload,
    provider_health,
    provider_transition,
    runtime_failure_counts,
)


def test_runtime_failure_counts_never_return_raw_journal_content():
    messages = [
        "chat stream persistence failed session_id=secret-session prompt=private",
        "chat transcript mirror failed session_id=another-private-id",
        "chat research producer failed error=ConnectionClosedError",
        "POST /api/internal/chat-gateway/session-store 403 Forbidden",
        "chat Excalidraw MCP registration failed failure_class=configured_not_connected",
    ]

    assert runtime_failure_counts(messages) == {
        "stream_persistence_failure": 1,
        "transcript_mirror_failure": 1,
        "session_store_forbidden": 1,
        "excalidraw_mcp_unready": 1,
    }


def test_runtime_failure_counts_does_not_page_on_routine_lifecycle_success():
    messages = [
        "chat durable lifecycle event=worker_reconnect code=none value=1",
        "chat durable lifecycle event=executor_recovery code=succeeded value=1",
        "chat durable lifecycle event=workspace_state code=created value=1",
        "chat durable lifecycle event=workspace_state code=reused value=1",
        "chat durable lifecycle event=ttft_ms code=none value=12000",
    ]

    assert runtime_failure_counts(messages) == {}
    assert lifecycle_window_alerts(messages, Settings()) == {}


def test_lifecycle_window_alerts_require_configured_rate_or_ratio_breaches():
    settings = Settings(
        chat_lifecycle_alert_min_samples=5,
        chat_lifecycle_alert_failure_percent=50,
        chat_lifecycle_capacity_saturation_count=3,
        chat_lifecycle_workspace_create_percent=75,
        chat_lifecycle_ttft_threshold_ms=1_000,
        chat_lifecycle_ttft_regression_percent=50,
    )
    messages = [
        *[
            "chat durable lifecycle event=worker_reconnect code=none value=1"
            for _ in range(2)
        ],
        *[
            (
                "chat durable lifecycle event=typed_failure "
                "code=external_worker_lost value=1"
            )
            for _ in range(3)
        ],
        *[
            "chat durable lifecycle event=executor_recovery code=succeeded value=1"
            for _ in range(2)
        ],
        *[
            "chat durable lifecycle event=turn_state code=waiting_tool value=1"
            for _ in range(5)
        ],
        *[
            "chat durable lifecycle event=typed_failure code=execution_lost value=1"
            for _ in range(3)
        ],
        *[
            "chat durable lifecycle event=capacity_saturation code=none value=1"
            for _ in range(3)
        ],
        *[
            "chat durable lifecycle event=workspace_state code=created value=1"
            for _ in range(4)
        ],
        "chat durable lifecycle event=workspace_state code=reused value=1",
        *[
            "chat durable lifecycle event=ttft_ms code=none value=1000"
            for _ in range(3)
        ],
        *["chat durable lifecycle event=ttft_ms code=none value=999" for _ in range(2)],
    ]

    assert lifecycle_window_alerts(messages, settings) == {
        "worker_reattach_failure_rate": 3,
        "executor_lost_rate": 3,
        "capacity_saturation": 3,
        "workspace_create_ratio": 4,
        "ttft_regression_rate": 3,
    }


def test_lifecycle_window_alerts_count_reconciled_execution_loss():
    settings = Settings(
        chat_lifecycle_alert_min_samples=5,
        chat_lifecycle_alert_failure_percent=50,
    )
    messages = [
        *[
            "chat durable lifecycle event=turn_state code=waiting_tool value=1"
            for _ in range(5)
        ],
        *[
            "chat durable lifecycle event=typed_failure code=execution_lost value=1"
            for _ in range(3)
        ],
    ]

    assert lifecycle_window_alerts(messages, settings) == {"executor_lost_rate": 3}


def test_lifecycle_window_alerts_ignore_early_executor_recovery_failure():
    settings = Settings(
        chat_lifecycle_alert_min_samples=5,
        chat_lifecycle_alert_failure_percent=50,
    )
    messages = [
        *[
            "chat durable lifecycle event=turn_state code=waiting_tool value=1"
            for _ in range(5)
        ],
        *[
            "chat durable lifecycle event=executor_recovery code=failed value=1"
            for _ in range(2)
        ],
        *[
            "chat durable lifecycle event=typed_failure code=execution_lost value=1"
            for _ in range(2)
        ],
    ]

    assert lifecycle_window_alerts(messages, settings) == {}


def test_lifecycle_window_alerts_canonical_loss_cannot_exceed_attempts():
    settings = Settings(
        chat_lifecycle_alert_min_samples=5,
        chat_lifecycle_alert_failure_percent=50,
    )
    messages = [
        "chat durable lifecycle event=turn_state code=waiting_tool value=5",
        "chat durable lifecycle event=executor_recovery code=failed value=6",
        "chat durable lifecycle event=typed_failure code=execution_lost value=3",
    ]

    alerts = lifecycle_window_alerts(messages, settings)

    assert alerts == {"executor_lost_rate": 3}
    assert alerts["executor_lost_rate"] <= 5


def test_event_journal_bound_remains_an_explicit_runtime_failure():
    assert runtime_failure_counts(
        [
            "chat durable lifecycle event=typed_failure "
            "code=event_journal_exhausted value=1"
        ]
    ) == {"event_journal_bound": 1}


def test_stale_fence_and_expired_lease_page_immediately_without_content():
    messages = [
        "chat durable lifecycle event=stale_fence_rejection code=stale value=1",
        "chat durable lifecycle event=expired_turn_lease code=expired value=2",
    ]

    assert runtime_failure_counts(messages) == {
        "stale_fence_rejection": 1,
        "expired_turn_lease": 1,
    }
    assert lifecycle_window_alerts(messages, Settings()) == {
        "stale_fence_rejection": 1,
        "expired_turn_lease": 2,
    }


def test_monitor_pages_once_on_window_breach_and_recovers_once(monkeypatch):
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    settings = Settings(
        chat_lifecycle_alert_min_samples=2,
        chat_lifecycle_alert_failure_percent=50,
    )
    failed_window = [
        "chat durable lifecycle event=turn_state code=waiting_tool value=2",
        "chat durable lifecycle event=typed_failure code=execution_lost value=1",
    ]
    current_window = [
        "chat durable lifecycle event=worker_reconnect code=none value=1",
        "chat durable lifecycle event=executor_recovery code=succeeded value=1",
        "chat durable lifecycle event=workspace_state code=created value=1",
    ]
    monkeypatch.setattr(
        monitor,
        "read_journal",
        lambda _cursor, _now: ([], "cursor-next", False),
    )
    monkeypatch.setattr(
        monitor, "read_lifecycle_window", lambda _now, _seconds: current_window
    )
    monkeypatch.setattr(
        monitor,
        "db_manager",
        SimpleNamespace(session_local=lambda: nullcontext(None)),
    )
    monkeypatch.setattr(
        monitor,
        "provider_health",
        lambda _db, _settings, observed_now: ProviderHealth(
            0,
            0,
            observed_now - timedelta(minutes=5),
            observed_now,
        ),
    )
    state = monitor.empty_state()

    events, failed = monitor.collect_events(state, settings, now)
    assert failed is False
    assert events == []

    current_window = failed_window
    events, failed = monitor.collect_events(state, settings, now)
    assert failed is False
    assert [event["signal"] for event in events] == ["chat_lifecycle_threshold"]
    assert events[0]["classifications"] == {"executor_lost_rate": 1}

    events, failed = monitor.collect_events(state, settings, now)
    assert failed is False
    assert events == []

    current_window = []
    events, failed = monitor.collect_events(state, settings, now)
    assert failed is False
    assert [event["signal"] for event in events] == [
        "chat_lifecycle_threshold_recovered"
    ]
    assert events[0]["classifications"] == {"executor_lost_rate": 1}


def test_reliability_probe_runs_every_fifteen_minutes_and_after_alerts(monkeypatch):
    now = datetime(2026, 8, 31, 12, tzinfo=UTC)
    state = monitor.empty_state()
    calls = []
    monkeypatch.setattr(
        monitor,
        "probe_chat_aggregates",
        lambda window, **kwargs: calls.append((window, kwargs)) or (),
    )

    assert monitor.collect_reliability_events(state, Settings(), now, {}, []) == []
    assert len(calls) == 1
    assert calls[0][0] == timedelta(minutes=15)

    assert (
        monitor.collect_reliability_events(
            state, Settings(), now + timedelta(minutes=14), {}, []
        )
        == []
    )
    assert len(calls) == 1

    alert = monitor.new_event("chat_runtime_critical", now=now + timedelta(minutes=14))
    assert (
        monitor.collect_reliability_events(
            state, Settings(), now + timedelta(minutes=14), {}, [alert]
        )
        == []
    )
    assert len(calls) == 2


def test_release_change_forces_extra_reliability_and_synthetic_checks():
    state = monitor.empty_state()
    settings = Settings(release_id="new-release")

    aggregate, synthetic = monitor.release_probe_triggers(state, settings)

    assert aggregate is True
    assert synthetic is True
    assert state["observed_release_id"] == "new-release"

    assert monitor.release_probe_triggers(state, settings) == (False, False)

    changed_provider = Settings(
        release_id="new-release",
        chat_glm_5_3_flash_route="zai-org/GLM-5.3-Flash:alternate",
    )
    assert monitor.release_probe_triggers(state, changed_provider) == (True, True)


def test_provider_health_counts_only_content_free_aggregates():
    class FakeSession:
        values = iter((10, 5))

        def scalar(self, _statement):
            return next(self.values)

    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    settings = Settings(chat_provider_alert_window_seconds=300)

    assert provider_health(FakeSession(), settings, now) == ProviderHealth(
        total_turns=10,
        failed_turns=5,
        window_start=now - timedelta(minutes=5),
        window_end=now,
    )


def test_production_provider_health_scopes_the_discovered_glm_route():
    class FakeSession:
        statements = []

        def scalar(self, statement):
            self.statements.append(
                str(statement.compile(compile_kwargs={"literal_binds": True}))
            )
            return 0

    db = FakeSession()
    settings = Settings(environment="production")

    provider_health(db, settings, datetime(2026, 8, 27, 12, tzinfo=UTC))

    assert len(db.statements) == 2
    assert all("zai-org/GLM-5.3-Flash:fastest" in sql for sql in db.statements)
    assert all("DeepSeek-V4-Flash" not in sql for sql in db.statements)


def test_provider_transition_requires_sustained_failure_and_clean_recovery():
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    settings = Settings(
        chat_provider_alert_min_failures=5,
        chat_provider_alert_failure_percent=50,
    )

    assert (
        provider_transition(
            active=False,
            health=ProviderHealth(10, 5, now - timedelta(minutes=5), now),
            settings=settings,
        )
        == "hf_provider_sustained_failure"
    )
    assert (
        provider_transition(
            active=True,
            health=ProviderHealth(10, 1, now - timedelta(minutes=5), now),
            settings=settings,
        )
        is None
    )
    assert (
        provider_transition(
            active=True,
            health=ProviderHealth(8, 0, now - timedelta(minutes=5), now),
            settings=settings,
        )
        == "hf_provider_recovered"
    )


def test_operational_payload_is_content_free():
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    event = monitor.new_event(
        "chat_runtime_critical",
        now=now,
        classifications={"stream_persistence_failure": 2},
    )
    settings = Settings(
        environment="production",
        release_id="release-test",
        chat_sandbox_runbook_url="https://runbook.test/chat",
    )

    payload = operational_alert_payload(event, settings)["text"]

    assert "stream_persistence_failure" in payload
    assert "release-test" in payload
    assert "prompt" not in payload
    assert "answer" not in payload
    assert "credential" not in payload


def test_pending_runtime_events_are_bounded_by_coalescing():
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    state = monitor.empty_state()
    first = monitor.new_event(
        "chat_runtime_critical",
        now=now,
        count=1,
        classifications={"turn_cleanup_failure": 1},
    )
    second = monitor.new_event(
        "chat_runtime_critical",
        now=now + timedelta(minutes=1),
        count=2,
        classifications={"turn_cleanup_failure": 1, "latency_phase_failure": 1},
    )

    monitor.append_event(state, first)
    monitor.append_event(state, second)

    assert len(state["events"]) == 1
    assert state["events"][0]["count"] == 3
    assert state["events"][0]["classifications"] == {
        "turn_cleanup_failure": 2,
        "latency_phase_failure": 1,
    }


def test_state_round_trip_is_private_and_atomic(tmp_path):
    path = tmp_path / "state.json"
    state = monitor.empty_state()
    state["journal_cursor"] = "content-free-cursor"

    monitor.write_state(path, state)

    assert monitor.load_state(path) == state
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".state.json.new-*"))


@pytest.mark.parametrize("active", [["user-controlled-label"], [{"bad": "shape"}]])
def test_state_rejects_unbounded_lifecycle_labels(tmp_path, active):
    path = tmp_path / "state.json"
    state = monitor.empty_state()
    state["lifecycle_active"] = active
    path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(TypeError, match="invalid lifecycle state"):
        monitor.load_state(path)


def test_dashboard_health_record_is_content_free_and_group_readable(tmp_path):
    monitor.write_health_record(
        tmp_path,
        {
            "status": "healthy",
            "completed_at": "2026-08-14T12:00:00Z",
            "pending": 0,
            "delivered": 1,
        },
    )
    path = tmp_path / monitor.HEALTH_RECORD
    assert json.loads(path.read_text()) == {
        "status": "healthy",
        "completed_at": "2026-08-14T12:00:00Z",
        "pending": 0,
        "delivered": 1,
    }
    assert path.stat().st_mode & 0o777 == 0o644


def test_journal_reader_advances_cursor_without_returning_records(monkeypatch):
    output = "\n".join(
        (
            json.dumps({"MESSAGE": "first", "__CURSOR": "cursor-1"}),
            json.dumps({"MESSAGE": "second", "__CURSOR": "cursor-2"}),
        )
    )
    observed = []

    def fake_run(command, **_kwargs):
        observed.append(command)
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)

    messages, cursor, reset = monitor.read_journal(
        "previous-cursor", datetime(2026, 8, 6, 12, tzinfo=UTC)
    )

    assert messages == ["first", "second"]
    assert cursor == "cursor-2"
    assert reset is False
    assert "--after-cursor" in observed[0]
    assert "previous-cursor" in observed[0]


def test_journal_reader_advances_to_reported_tail_when_no_unit_record_matches(
    monkeypatch,
):
    observed = []

    def fake_run(command, **_kwargs):
        observed.append(command)
        return SimpleNamespace(stdout="-- cursor: journal-tail-cursor\n")

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)

    messages, cursor, reset = monitor.read_journal(
        "previous-cursor", datetime(2026, 8, 6, 12, tzinfo=UTC)
    )

    assert messages == []
    assert cursor == "journal-tail-cursor"
    assert reset is False
    assert "--show-cursor" in observed[0]


def test_journal_reader_recovers_from_a_vacuumed_cursor(monkeypatch):
    calls = 0

    def fake_run(_command, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise monitor.subprocess.CalledProcessError(1, "journalctl")
        return SimpleNamespace(
            stdout=json.dumps({"MESSAGE": "recent", "__CURSOR": "fresh-cursor"})
        )

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)

    messages, cursor, reset = monitor.read_journal(
        "vacuumed-cursor", datetime(2026, 8, 6, 12, tzinfo=UTC)
    )

    assert messages == ["recent"]
    assert cursor == "fresh-cursor"
    assert reset is True


def test_lifecycle_window_reader_uses_configured_window(monkeypatch):
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    observed = []

    def fake_run(command, **_kwargs):
        observed.append(command)
        return SimpleNamespace(
            stdout=json.dumps(
                {
                    "MESSAGE": (
                        "chat durable lifecycle event=worker_reconnect "
                        "code=none value=1"
                    )
                }
            )
        )

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)

    assert monitor.read_lifecycle_window(now, 300) == [
        "chat durable lifecycle event=worker_reconnect code=none value=1"
    ]
    assert "--after-cursor" not in observed[0]
    assert (now - timedelta(seconds=300)).isoformat() in observed[0]
    assert observed[0][observed[0].index("--grep") + 1] == (
        "chat durable lifecycle event="
    )


def test_lifecycle_window_reader_treats_no_grep_match_as_an_empty_window(
    monkeypatch,
):
    def fake_run(_command, **kwargs):
        assert kwargs["check"] is False
        return SimpleNamespace(stdout="", returncode=1)

    monkeypatch.setattr(monitor.subprocess, "run", fake_run)

    assert (
        monitor.read_lifecycle_window(datetime(2026, 8, 6, 12, tzinfo=UTC), 300) == []
    )


def test_delivery_uses_primary_then_fallback(monkeypatch):
    settings = Settings(
        environment="production",
        chat_sandbox_slack_webhook_url="https://primary.test/hook",
        chat_sandbox_alert_fallback_webhook_url="https://fallback.test/hook",
    )
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    primary = monitor.new_event("hf_provider_sustained_failure", now=now)
    fallback = monitor.new_event("chat_runtime_critical", now=now)
    calls = []

    async def fake_post(url, event, _settings):
        calls.append((url, event["signal"]))
        if event["signal"] == "chat_runtime_critical" and "primary" in url:
            raise httpx.ConnectError("synthetic failure")

    monkeypatch.setattr(monitor, "post_operational_alert", fake_post)
    state = {"events": [primary, fallback]}

    assert asyncio.run(monitor.deliver_pending(state, settings)) == 2
    assert primary["primary_delivery_state"] == "delivered"
    assert primary["fallback_delivery_state"] == "not_needed"
    assert fallback["primary_delivery_state"] == "failed"
    assert fallback["fallback_delivery_state"] == "delivered"
    assert calls == [
        ("https://primary.test/hook", "hf_provider_sustained_failure"),
        ("https://primary.test/hook", "chat_runtime_critical"),
        ("https://fallback.test/hook", "chat_runtime_critical"),
    ]
