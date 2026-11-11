"""The trace-upload breaker counts failing jobs, not a job's retries."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers import codex_curation_callbacks as callbacks


class _FakeDb:
    def __init__(self, state):
        self.state = state
        self.commits = 0

    def get(self, _model, _key):
        return self.state

    def commit(self):
        self.commits += 1


class _FailingTraceService:
    def __init__(self, *_args):
        pass

    def finalize(self, _row, _payload):
        raise RuntimeError("bucket returned 500")


def _scheduler():
    return SimpleNamespace(
        consecutive_trace_failures=0,
        paused_at=None,
        pause_condition=None,
        pause_reason=None,
    )


def _job():
    return SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-daily-cron",
        runner="codex",
        trace_status="pending",
        trace_attempt_count=0,
    )


def _finalize(monkeypatch, db, row):
    monkeypatch.setattr(callbacks, "_callback_job", lambda *_args: row)
    monkeypatch.setattr(callbacks, "CurationTraceService", _FailingTraceService)
    body = SimpleNamespace(model_dump=lambda: {})
    settings = SimpleNamespace(codex_jobs_enabled=True)
    with pytest.raises(HTTPException) as raised:
        callbacks.finalize_trace(row.id, body, "Bearer token", db, settings)
    assert raised.value.status_code == 503


def test_one_jobs_retries_do_not_pause_scheduled_dispatch(monkeypatch):
    state = _scheduler()
    db = _FakeDb(state)
    row = _job()

    for _ in range(5):
        _finalize(monkeypatch, db, row)

    assert row.trace_status == "finalize_failed"
    assert row.trace_attempt_count == 5
    assert state.consecutive_trace_failures == 1
    assert state.paused_at is None
    assert db.commits == 5


def test_three_failing_jobs_pause_scheduled_dispatch(monkeypatch):
    state = _scheduler()
    db = _FakeDb(state)

    for _ in range(3):
        row = _job()
        _finalize(monkeypatch, db, row)
        _finalize(monkeypatch, db, row)

    assert state.consecutive_trace_failures == 3
    assert state.paused_at is not None
    assert state.pause_condition == "trace_upload_failures"


def test_admin_trace_failures_never_count(monkeypatch):
    state = _scheduler()
    row = _job()
    row.trigger = "admin"

    _finalize(monkeypatch, _FakeDb(state), row)

    assert row.trace_status == "finalize_failed"
    assert state.consecutive_trace_failures == 0


def test_trace_failure_is_logged_with_its_error(monkeypatch, caplog):
    row = _job()

    with caplog.at_level("WARNING", logger=callbacks.logger.name):
        _finalize(monkeypatch, _FakeDb(_scheduler()), row)

    assert f"job={row.id} stage=finalize_failed" in caplog.text
    assert "RuntimeError: bucket returned 500" in caplog.text
