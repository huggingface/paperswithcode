"""Validator replay, operator retry, and canary dispatch CLI."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.config import get_settings
from backend.scripts import enqueue_hf_daily_paper_curation as curation_cli
from backend.models.database import (
    PaperCurationSchedulerState,
)
from backend.services.codex_add_evals_service import (
    CanaryDispatchFailed,
)
from backend.services.hf_daily_curation_service import (
    HFDailyCurationService,
)


@pytest.mark.parametrize("rejected", [False, True])
def test_validator_replay_uses_saved_proposal_without_writes(monkeypatch, rejected):
    from backend.services import hf_daily_curation_service

    job_id = uuid.uuid4()
    row = SimpleNamespace(
        id=job_id,
        kind="add-evals",
        paper_id=42,
        trigger="hf-daily-cron",
        url_candidates={
            "source_documents": [
                {"url": "https://example.com/paper", "kind": "paper_source"}
            ]
        },
        proposal={
            "evaluations": [],
            "evaluation_removals": [],
            "benchmark_gaps": [],
            "validation_evidence": [],
        },
    )
    paper = SimpleNamespace(id=42)

    class Database:
        def get(self, model, key):
            if model is hf_daily_curation_service.PaperCurationJob and key == job_id:
                return row
            if model is hf_daily_curation_service.Paper and key == 42:
                return paper
            return None

    class Gaps:
        def __init__(self, db):
            assert isinstance(db, Database)

        def validate(self, gaps, *, paper, source_documents):
            assert gaps == []
            assert paper is None
            assert source_documents == row.url_candidates["source_documents"]
            return [], [{"index": 0, "error": "bad evidence"}] if rejected else []

    class Callback:
        def __init__(self, db):
            assert isinstance(db, Database)

        def _validate_mutation(self, replay_row, body):
            assert replay_row.status == "running"
            assert replay_row.trace_status == "disabled"
            assert body.evaluations == []

        def _validate_scheduled_policy(self, _replay_row, _body):
            return {"policy": "scheduled-add-evals-v1", "evaluations": 0}

    monkeypatch.setattr(hf_daily_curation_service, "BenchmarkGapService", Gaps)
    monkeypatch.setattr(
        hf_daily_curation_service, "CodexCurationCallbackService", Callback
    )

    result = HFDailyCurationService(
        Database(), SimpleNamespace(), job_service=SimpleNamespace()
    ).validator_replay(job_id)

    if rejected:
        assert result["valid"] is False
        assert "Scheduled benchmark gap validation failed" in result["error"]
        return

    assert result == {
        "job_id": str(job_id),
        "valid": True,
        "validation": {"policy": "scheduled-add-evals-v1", "evaluations": 0},
        "benchmark_gaps_accepted": 0,
        "benchmark_gaps_rejected": [],
    }


@pytest.mark.parametrize(
    ("trigger", "kind"),
    [
        ("hf-daily-cron", "add-evals"),
        ("hf-trending-cron", "enrich-paper"),
        ("benchmark-gap-cron", "add-evals"),
    ],
)
def test_queued_operator_retry_is_prioritized_without_duplication(trigger, kind):
    job_id = uuid.uuid4()
    row = SimpleNamespace(
        id=job_id,
        trigger=trigger,
        kind=kind,
        status="queued",
        priority=100,
    )

    class Database:
        committed = False

        def get(self, _model, _key):
            return row

        def query(self, *_args):
            return SimpleNamespace(
                filter=lambda *_args: SimpleNamespace(
                    order_by=lambda *_args: SimpleNamespace(first=lambda: None)
                )
            )

        def commit(self):
            self.committed = True

    class JobService:
        dispatched = False

        def dispatch_next(self, *_args):
            self.dispatched = True

        def serialize(self, selected, _settings):
            assert selected is row
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {
                    "id": str(job_id),
                    "priority": row.priority,
                }
            )

        def retry(self, *_args, **_kwargs):
            raise AssertionError("queued jobs must not be duplicated")

    database = Database()
    jobs = JobService()
    result = HFDailyCurationService(
        database,
        SimpleNamespace(),
        job_service=jobs,
    ).retry_scheduled_job(job_id)

    assert result == {"id": str(job_id), "priority": 50}
    assert database.committed is True
    assert jobs.dispatched is True


def test_canary_dispatch_launches_only_selected_job_while_normal_dispatch_is_paused():
    selected = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-daily-cron",
        status="queued",
    )
    other = SimpleNamespace(
        id=uuid.uuid4(),
        trigger="hf-trending-cron",
        status="queued",
    )
    scheduler = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=datetime.now(UTC),
        pause_condition="operator",
        first_enabled_at=None,
    )

    class Database:
        def get(self, model, key):
            if model is PaperCurationSchedulerState:
                return scheduler
            if key == selected.id:
                return selected
            return None

    class Jobs:
        launched = []

        def dispatch_canary(self, _db, _settings, row):
            self.launched.append(row)
            row.status = "running"
            return row

        def serialize(self, row, _settings):
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {
                    "id": str(row.id),
                    "status": row.status,
                }
            )

    jobs = Jobs()
    result = HFDailyCurationService(
        Database(), SimpleNamespace(), job_service=jobs
    ).dispatch_canary_job(selected.id)

    assert result == {"id": str(selected.id), "status": "running"}
    assert jobs.launched == [selected]
    assert other.status == "queued"
    assert scheduler.dispatch_enabled is False
    assert scheduler.paused_at is not None


def test_daily_curation_cli_dispatches_one_explicit_canary_job(monkeypatch, capsys):
    job_id = uuid.uuid4()
    calls = []

    def session():
        yield object()

    class Service:
        def __init__(self, db, settings):
            calls.append((db, settings))

        def dispatch_canary_job(self, selected_job_id):
            calls.append(selected_job_id)
            return {"id": str(selected_job_id), "status": "running"}

    settings = object()
    monkeypatch.setattr(curation_cli, "get_database_session", session)
    monkeypatch.setattr(curation_cli, "get_settings", lambda: settings)
    monkeypatch.setattr(curation_cli, "HFDailyCurationService", Service)
    monkeypatch.setattr(
        sys,
        "argv",
        ["enqueue_hf_daily_paper_curation", "--canary-job", str(job_id)],
    )

    assert curation_cli.main() == 0
    assert calls[1] == job_id
    assert json.loads(capsys.readouterr().out) == {
        "id": str(job_id),
        "status": "running",
    }


def test_daily_curation_cli_exits_nonzero_when_canary_does_not_launch(
    monkeypatch, capsys
):
    job_id = uuid.uuid4()

    def session():
        yield object()

    class Service:
        def __init__(self, _db, _settings):
            pass

        def dispatch_canary_job(self, _selected_job_id):
            raise CanaryDispatchFailed("Canary job did not launch")

    monkeypatch.setattr(curation_cli, "get_database_session", session)
    monkeypatch.setattr(curation_cli, "get_settings", object)
    monkeypatch.setattr(curation_cli, "HFDailyCurationService", Service)
    monkeypatch.setattr(
        sys,
        "argv",
        ["enqueue_hf_daily_paper_curation", "--canary-job", str(job_id)],
    )

    assert curation_cli.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": "Canary job did not launch",
        "job_id": str(job_id),
        "launched": False,
    }


@pytest.mark.parametrize(
    ("trigger", "status", "dispatch_enabled", "paused_at", "message"),
    (
        ("admin", "queued", False, datetime.now(UTC), "Only scheduled"),
        (
            "hf-daily-cron",
            "running",
            False,
            datetime.now(UTC),
            "requires a queued",
        ),
        (
            "hf-trending-cron",
            "queued",
            True,
            None,
            "normal dispatch to be paused",
        ),
    ),
)
def test_canary_dispatch_rejects_unsafe_selection_or_scheduler_state(
    trigger, status, dispatch_enabled, paused_at, message
):
    row = SimpleNamespace(id=uuid.uuid4(), trigger=trigger, status=status)
    scheduler = SimpleNamespace(
        dispatch_enabled=dispatch_enabled,
        paused_at=paused_at,
    )

    class Database:
        def get(self, model, _key):
            return scheduler if model is PaperCurationSchedulerState else row

    class Jobs:
        def dispatch_canary(self, *_args):
            raise AssertionError("unsafe canary must not reach the dispatcher")

    with pytest.raises(ValueError, match=message):
        HFDailyCurationService(
            Database(), SimpleNamespace(), job_service=Jobs()
        ).dispatch_canary_job(row.id)


@pytest.mark.parametrize("trigger", ["hf-daily-cron", "hf-trending-cron"])
def test_repeating_operator_retry_returns_active_child_attempt(trigger):
    job_id = uuid.uuid4()
    failed = SimpleNamespace(id=job_id, trigger=trigger, status="failed")
    active = SimpleNamespace(id=uuid.uuid4(), status="running", priority=100)

    class Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def first(self):
            return active

    class Database:
        committed = False

        def get(self, *_args):
            return failed

        def query(self, *_args):
            return Query()

        def commit(self):
            self.committed = True

    class Jobs:
        dispatched = False

        def dispatch_next(self, *_args):
            self.dispatched = True

        def serialize(self, row, _settings):
            assert row is active
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {
                    "id": str(active.id),
                    "status": active.status,
                    "priority": active.priority,
                }
            )

        def retry(self, *_args, **_kwargs):
            raise AssertionError("an active child retry must be reused")

    database = Database()
    jobs = Jobs()
    result = HFDailyCurationService(
        database, SimpleNamespace(), job_service=jobs
    ).retry_scheduled_job(job_id)

    assert result == {"id": str(active.id), "status": "running", "priority": 50}
    assert database.committed is True
    assert jobs.dispatched is True


@pytest.mark.parametrize(
    "row",
    [
        SimpleNamespace(trigger="admin", kind="add-evals"),
        SimpleNamespace(trigger="benchmark-gap-cron", kind="add-benchmark"),
    ],
)
def test_operator_retry_rejects_admin_and_benchmark_creation_jobs(row):
    job_id = uuid.uuid4()

    class Database:
        def get(self, _model, _key):
            return row

    with pytest.raises(ValueError, match="Only scheduled HF daily"):
        HFDailyCurationService(
            Database(),
            SimpleNamespace(),
            job_service=SimpleNamespace(),
        ).retry_scheduled_job(job_id)


def test_dispatch_acknowledgement_starts_a_fresh_failure_window():
    state = SimpleNamespace(
        dispatch_enabled=True,
        paused_at=datetime.now(UTC),
        pause_reason="Historical failures",
        pause_condition="terminal_failure_rate",
        acknowledged_at=None,
        first_enabled_at=datetime.now(UTC),
        consecutive_trace_failures=3,
        consecutive_apply_failures=3,
        canary_released=True,
    )

    class Query:
        def filter(self, *_args):
            return self

        def scalar(self):
            return None

    class Database:
        def get(self, *_args):
            return state

        def query(self, *_args):
            return Query()

        def commit(self):
            pass

    jobs = SimpleNamespace(dispatch_next=lambda *_args: None)
    result = HFDailyCurationService(
        Database(),
        get_settings(),
        job_service=jobs,
    ).set_dispatch(True)

    assert result["paused_at"] is None
    assert state.acknowledged_at is not None
    assert state.consecutive_trace_failures == 0
    assert state.consecutive_apply_failures == 0


def test_daily_curation_cli_reports_retry_workflow_conflict(monkeypatch, capsys):
    job_id = uuid.uuid4()

    def session():
        yield object()

    class Service:
        def __init__(self, _db, _settings):
            pass

        def retry_scheduled_job(self, _job_id):
            raise curation_cli.CurationRetryConflict("Paper has active workflow newer")

    monkeypatch.setattr(curation_cli, "get_database_session", session)
    monkeypatch.setattr(curation_cli, "get_settings", object)
    monkeypatch.setattr(curation_cli, "HFDailyCurationService", Service)
    monkeypatch.setattr(sys, "argv", ["curation", "--retry-job", str(job_id)])
    assert curation_cli.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "error": "Paper has active workflow newer",
        "job_id": str(job_id),
        "retry_conflict": True,
    }
