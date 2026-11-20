"""Admins can see one paper's curation jobs and why queued ones have not run."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.main import create_app
from backend.services.codex_add_evals_service import (
    CodexPaperJobService,
    PaperCurationHistoryResponse,
)
from backend.utils.auth import require_hf_admin

PAUSED_AT = datetime(2026, 11, 20, 3, 6, tzinfo=UTC)


def _row(
    status: str, kind: str = "enrich-paper", trigger: str = "hf-daily-cron"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        paper_id=133629,
        paper_route="2611.26603",
        paper_title="Depth Pro 2",
        requested_by="hf-daily-cron",
        kind=kind,
        status=status,
        hf_job_id=None,
        created_at=datetime(2026, 11, 19, tzinfo=UTC),
        started_at=None,
        finished_at=None,
        applied_at=None,
        report=None,
        error=None,
        attempt_count=0,
        thumbnail_requested_at=None,
        trigger=trigger,
        trace_status="pending",
    )


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def order_by(self, *_args):
        return self

    def limit(self, limit):
        self.limit_value = limit
        return self

    def all(self):
        return self.rows


class _Database:
    def __init__(self, rows, state):
        self.query_obj = _Query(rows)
        self.state = state

    def query(self, _model):
        return self.query_obj

    def get(self, _model, _key):
        return self.state


def _paused_state():
    return SimpleNamespace(
        dispatch_enabled=True,
        paused_at=PAUSED_AT,
        pause_reason="trace upload failures",
        pause_condition="trace_upload_failures",
    )


def _history(
    rows, state, *, scheduler_enabled: bool = True
) -> tuple[PaperCurationHistoryResponse, _Database]:
    db = _Database(rows, state)
    service = CodexPaperJobService()
    reconciled = []
    service.reconcile_if_due = lambda db, settings: reconciled.append(db)
    settings = get_settings().model_copy(
        update={"codex_curation_scheduler_enabled": scheduler_enabled}
    )
    result = service.paper_history(db, settings, 133629, limit=20)
    assert reconciled == [db]
    return result, db


def test_history_includes_workflow_stages_for_the_paper():
    _result, db = _history([_row("completed")], None)
    sql = str(
        db.query_obj.criteria[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "paper_curation_jobs.paper_id = 133629" in sql
    assert "paper_curation_jobs.parent_workflow_id IN" in sql
    assert "paper_curation_workflows.paper_id = 133629" in sql
    assert db.query_obj.limit_value == 20


def test_queued_job_reports_scheduler_pause():
    queued = _row("queued")
    result, _db = _history([queued, _row("completed")], _paused_state())
    assert [job.status for job in result.jobs] == ["queued", "completed"]
    assert result.scheduler_pause == {
        "dispatch_enabled": True,
        "paused_at": PAUSED_AT.isoformat(),
        "pause_reason": "trace upload failures",
        "pause_condition": "trace_upload_failures",
        "job_ids": [str(queued.id)],
    }


def test_pause_does_not_hold_admin_jobs():
    result, _db = _history([_row("queued", trigger="admin")], _paused_state())
    assert result.scheduler_pause is None


def test_scheduler_disabled_in_settings_holds_scheduled_jobs():
    running_state = SimpleNamespace(
        dispatch_enabled=True,
        paused_at=None,
        pause_reason=None,
        pause_condition=None,
    )
    result, _db = _history([_row("queued")], running_state, scheduler_enabled=False)
    assert result.scheduler_pause["dispatch_enabled"] is False
    assert result.scheduler_pause["pause_reason"] == "scheduler disabled in settings"


def test_pause_is_omitted_without_a_queued_job_or_pause():
    result, _db = _history([_row("completed")], _paused_state())
    assert result.scheduler_pause is None
    running_state = SimpleNamespace(
        dispatch_enabled=True,
        paused_at=None,
        pause_reason=None,
        pause_condition=None,
    )
    result, _db = _history([_row("queued")], running_state)
    assert result.scheduler_pause is None


def test_dispatch_disabled_counts_as_paused():
    state = SimpleNamespace(
        dispatch_enabled=False,
        paused_at=None,
        pause_reason=None,
        pause_condition=None,
    )
    result, _db = _history([_row("queued")], state)
    assert result.scheduler_pause["dispatch_enabled"] is False


def test_paper_history_route_is_admin_scoped(monkeypatch):
    from backend.routers import codex_curation_callbacks

    settings = get_settings().model_copy(update={"codex_jobs_enabled": True})
    calls = []

    def fake_history(db, settings, paper_id, *, limit):
        calls.append((paper_id, limit))
        return PaperCurationHistoryResponse(paper_id=paper_id, jobs=[])

    monkeypatch.setattr(
        codex_curation_callbacks.codex_paper_job_service,
        "paper_history",
        fake_history,
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_hf_admin] = lambda: {"username": "niels"}
    app.dependency_overrides[get_database_session] = lambda: SimpleNamespace()
    with TestClient(app) as client:
        response = client.get("/api/v1/admin/codex-curation/jobs/papers/133629")
    assert response.status_code == 200
    assert response.json() == {
        "paper_id": 133629,
        "jobs": [],
        "scheduler_pause": None,
    }
    assert calls == [(133629, 50)]
