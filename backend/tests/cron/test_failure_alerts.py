import json

from datetime import UTC, datetime, timedelta

import pytest

from backend.services.cron_failure_alerts import (
    dashboard_status,
    load_state,
    plan_alerts,
    save_state,
)
from backend.services.cron_registry import get_cron_job

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
JOB = get_cron_job("refresh_paper_embeddings")


def _runs(streak: int, runs: int = 24) -> dict:
    return {
        "window_hours": 24,
        "runs": runs,
        "failures": streak,
        "consecutive_failures": streak,
        "last_failure_at": "2026-11-19T11:15:54+00:00" if streak else None,
    }


def test_embedding_refresh_opts_in_after_three_failures():
    assert JOB.failure_alert_after == 3


def test_alerts_once_when_streak_reaches_threshold():
    alerts, state = plan_alerts([JOB], {JOB.id: _runs(2)}, {}, NOW)
    assert alerts == [] and state == {}

    alerts, state = plan_alerts([JOB], {JOB.id: _runs(3)}, {}, NOW)
    assert [a.kind for a in alerts] == ["failing"]
    assert "Refresh Paper Embeddings" in alerts[0].text
    assert "The last 3 production runs failed" in alerts[0].text
    assert state[JOB.id]["since"] == NOW.isoformat()

    later = NOW + timedelta(hours=1)
    alerts, state = plan_alerts([JOB], {JOB.id: _runs(4)}, state, later)
    assert alerts == []
    assert state[JOB.id]["since"] == NOW.isoformat()
    assert state[JOB.id]["consecutive_failures"] == 4


def test_reminds_daily_while_still_failing():
    _, state = plan_alerts([JOB], {JOB.id: _runs(3)}, {}, NOW)
    alerts, state = plan_alerts(
        [JOB], {JOB.id: _runs(27)}, state, NOW + timedelta(hours=24)
    )
    assert [a.kind for a in alerts] == ["failing"]
    assert alerts[0].text.startswith(":rotating_light: *Still failing")
    assert state[JOB.id]["since"] == NOW.isoformat()


def test_recovery_closes_the_alert():
    _, state = plan_alerts([JOB], {JOB.id: _runs(3)}, {}, NOW)
    alerts, state = plan_alerts([JOB], {JOB.id: _runs(0)}, state, NOW)
    assert [a.kind for a in alerts] == ["recovered"]
    assert state == {}


def test_failures_aging_out_of_the_window_are_not_a_recovery():
    _, state = plan_alerts([JOB], {JOB.id: _runs(3)}, {}, NOW)
    alerts, kept = plan_alerts(
        [JOB], {JOB.id: _runs(2, runs=2)}, state, NOW + timedelta(hours=2)
    )
    assert alerts == [] and kept == state


def test_state_file_is_readable_by_the_web_app(tmp_path):
    path = tmp_path / "alerts.json"
    save_state(path, {}, NOW)
    assert path.stat().st_mode & 0o777 == 0o644


def test_missing_history_keeps_open_alert_without_posting():
    _, state = plan_alerts([JOB], {JOB.id: _runs(3)}, {}, NOW)
    alerts, kept = plan_alerts([JOB], {}, state, NOW + timedelta(hours=30))
    assert alerts == [] and kept == state


def test_jobs_without_threshold_never_alert():
    other = get_cron_job("update_citations")
    assert other.failure_alert_after is None
    alerts, state = plan_alerts([other], {other.id: _runs(10)}, {}, NOW)
    assert alerts == [] and state == {}
    assert dashboard_status(other, _runs(10), {}) is None


def test_state_round_trip_and_dashboard_status(tmp_path):
    path = tmp_path / "alerts.json"
    assert load_state(path) == {}
    _, state = plan_alerts([JOB], {JOB.id: _runs(5)}, {}, NOW)
    save_state(path, state, NOW)
    loaded = load_state(path)
    assert loaded == state
    status = dashboard_status(JOB, _runs(5), loaded)
    assert status == {
        "after_consecutive_failures": 3,
        "consecutive_failures": 5,
        "alerting": True,
        "since": NOW.isoformat(),
        "notified_at": NOW.isoformat(),
    }


def test_corrupt_state_surfaces_instead_of_resetting_open_alerts(tmp_path):
    path = tmp_path / "alerts.json"
    path.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        load_state(path)
