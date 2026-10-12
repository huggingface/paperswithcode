"""Snapshot and bounded-collector tests for the CRON admin dashboard."""

from __future__ import annotations

import fcntl
import json
from datetime import UTC, datetime, timedelta

import pytest

from backend.services import cron_health
from backend.services.cron_dashboard_snapshot_service import (
    CronDashboardSnapshotService,
)
from backend.services.cron_registry import list_cron_jobs


def _payload(timestamp: str = "2026-08-14T12:00:00Z") -> dict:
    return {
        "timestamp": timestamp,
        "jobs": [{"job_name": "example"}],
        "summary": {"total_jobs": 1},
    }


def test_snapshot_is_fresh_then_stale_and_refreshes(tmp_path):
    current = [datetime(2026, 8, 14, 12, tzinfo=UTC)]
    builds = []

    def builder(previous):
        builds.append(previous)
        return _payload()

    service = CronDashboardSnapshotService(
        runtime_data_dir=tmp_path,
        builder=builder,
        now=lambda: current[0],
    )

    first, scheduled = service.get_status()
    assert scheduled is False
    assert first["snapshot_stale"] is False
    assert len(builds) == 1

    current[0] += timedelta(seconds=61)
    stale, scheduled = service.get_status()
    assert scheduled is True
    assert stale["snapshot_stale"] is True
    assert stale["refreshing"] is True

    service.refresh_in_background()
    fresh, scheduled = service.get_status()
    assert scheduled is False
    assert fresh["snapshot_stale"] is False
    assert len(builds) == 2
    assert builds[1] == _payload()


def test_corrupt_snapshot_is_replaced_atomically(tmp_path):
    service = CronDashboardSnapshotService(
        runtime_data_dir=tmp_path,
        builder=lambda _previous: _payload(),
        now=lambda: datetime(2026, 8, 14, 12, tzinfo=UTC),
    )
    service.snapshot_dir.mkdir(parents=True)
    service.snapshot_path.write_text("not-json", encoding="utf-8")

    status, scheduled = service.get_status()

    assert scheduled is False
    assert status["jobs"][0]["job_name"] == "example"
    saved = json.loads(service.snapshot_path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 1
    assert list(service.snapshot_dir.glob("*.tmp")) == []


def test_refresh_failure_preserves_last_good_snapshot(tmp_path, caplog):
    current = [datetime(2026, 8, 14, 12, tzinfo=UTC)]
    fail = [False]

    def builder(_previous):
        if fail[0]:
            raise RuntimeError("provider unavailable")
        return _payload()

    service = CronDashboardSnapshotService(
        runtime_data_dir=tmp_path,
        builder=builder,
        now=lambda: current[0],
    )
    service.get_status()
    original = service.snapshot_path.read_bytes()
    current[0] += timedelta(seconds=61)
    fail[0] = True

    service.refresh_in_background()

    assert service.snapshot_path.read_bytes() == original
    stale, scheduled = service.get_status()
    assert stale["snapshot_stale"] is True
    assert scheduled is True
    assert "refresh_failed" in caplog.text


def test_force_refresh_does_not_duplicate_locked_refresh(tmp_path):
    current = datetime(2026, 8, 14, 12, tzinfo=UTC)
    builds = []
    service = CronDashboardSnapshotService(
        runtime_data_dir=tmp_path,
        builder=lambda previous: builds.append(previous) or _payload(),
        now=lambda: current,
    )
    service.get_status()
    lock = service.lock_path.open("a+", encoding="utf-8")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        status, scheduled = service.get_status(force_refresh=True)
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()

    assert scheduled is False
    assert status["refreshing"] is True
    assert len(builds) == 1


def test_invalid_builder_payload_does_not_create_snapshot(tmp_path):
    service = CronDashboardSnapshotService(
        runtime_data_dir=tmp_path,
        builder=lambda _previous: {},
    )

    with pytest.raises(RuntimeError, match="invalid payload"):
        service.get_status()

    assert not service.snapshot_path.exists()


def test_full_collection_uses_each_bounded_probe_once(monkeypatch):
    import sys

    workflows = cron_health.WORKFLOWS_DIR
    if str(workflows) not in sys.path:
        sys.path.insert(0, str(workflows))
    from scripts.utils import cron_helpers

    calls = {"process": 0, "database": 0, "workflow": 0, "thumbnail": 0}

    def process_snapshot():
        calls["process"] += 1
        return [], set()

    def database_snapshot(_jobs):
        calls["database"] += 1
        return {}

    def workflow_snapshot(_jobs, *, previous_dashboard=None):
        calls["workflow"] += 1
        assert previous_dashboard == {"jobs": []}
        return {}

    def thumbnail_snapshot():
        calls["thumbnail"] += 1
        return {"file_count": 0, "last_write": None, "recent_writes": 0}

    monkeypatch.setattr(cron_health, "_capture_processes", process_snapshot)
    monkeypatch.setattr(cron_health, "fetch_db_freshness_batch", database_snapshot)
    monkeypatch.setattr(cron_health, "fetch_workflow_statuses", workflow_snapshot)
    monkeypatch.setattr(
        cron_health, "fetch_thumbnail_cache_freshness", thumbnail_snapshot
    )
    monkeypatch.setattr(
        cron_helpers,
        "get_cron_job_status",
        lambda _name, _date, **_kwargs: {"exists": False, "status": "unknown"},
    )

    payload = cron_health.build_cron_dashboard(previous_dashboard={"jobs": []})

    assert len(payload["jobs"]) == len(list_cron_jobs())
    assert calls == {"process": 1, "database": 1, "workflow": 1, "thumbnail": 1}


def test_database_freshness_batch_reuses_one_connection(monkeypatch):
    jobs = [job for job in list_cron_jobs() if job.db_freshness_query][:2]
    executed = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            executed.append(query)

        def fetchone(self):
            return {"last_write": None, "recent_writes": 0}

    class Connection:
        autocommit = False

        def cursor(self, **_kwargs):
            return Cursor()

        def close(self):
            return None

    connections = []

    def connect(**_kwargs):
        connection = Connection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(cron_health.psycopg2, "connect", connect)

    result = cron_health.fetch_db_freshness_batch(jobs)

    assert len(connections) == 1
    assert connections[0].autocommit is True
    assert len(executed) == 2
    assert set(result) == {job.id for job in jobs}


def test_workflow_collection_batches_recent_runs(monkeypatch):
    jobs = [job for job in list_cron_jobs() if job.workflow_file]
    runs = [
        {
            "id": index,
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-08-14T12:00:00Z",
            "updated_at": "2026-08-14T12:01:00Z",
            "event": "schedule",
            "head_branch": "main",
            "path": f".github/workflows/{job.workflow_file}",
        }
        for index, job in enumerate(jobs, start=1)
    ]
    calls = []

    def gh_json(args, timeout=10):
        calls.append((args, timeout))
        if args[:1] == ["api"]:
            return {"workflow_runs": runs}, None
        return {"jobs": []}, None

    monkeypatch.setattr(cron_health, "_gh_json", gh_json)

    statuses = cron_health.fetch_workflow_statuses(jobs)

    assert set(statuses) == {job.id for job in jobs}
    assert all(status["scheduled_run"] for status in statuses.values())
    assert sum(args[:1] == ["api"] for args, _timeout in calls) == 1
    assert len(calls) == 2  # one batch plus the one multi-job workflow detail


def test_workflow_collection_pages_until_all_workflows_are_represented(monkeypatch):
    jobs = [
        job for job in list_cron_jobs() if job.id in {"sync_3d_arena", "sync_tabarena"}
    ]

    def run(job, index):
        return {
            "id": index,
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-08-14T12:00:00Z",
            "updated_at": "2026-08-14T12:01:00Z",
            "event": "schedule",
            "head_branch": "main",
            "path": f".github/workflows/{job.workflow_file}",
        }

    calls = []

    def gh_json(args, timeout=10):
        calls.append((args, timeout))
        if "&page=1&" in args[-1]:
            return {
                "workflow_runs": [run(jobs[0], index) for index in range(100)]
            }, None
        return {"workflow_runs": [run(jobs[1], 101)]}, None

    monkeypatch.setattr(cron_health, "_gh_json", gh_json)

    statuses = cron_health.fetch_workflow_statuses(jobs)

    assert set(statuses) == {job.id for job in jobs}
    assert len(calls) == 2
    assert "page=1" in calls[0][0][-1]
    assert "page=2" in calls[1][0][-1]


def test_workflow_collection_refreshes_failed_run_outside_recent_batch(monkeypatch):
    job = next(job for job in list_cron_jobs() if job.id == "backfill_method_keywords")
    previous_run = {
        "databaseId": 17,
        "status": "completed",
        "conclusion": "failure",
        "createdAt": "2026-08-13T01:10:00Z",
        "updatedAt": "2026-08-13T01:11:00Z",
        "event": "schedule",
        "headBranch": "main",
    }
    previous_dashboard = {
        "jobs": [
            {
                "workflow_status": {
                    "available": True,
                    "workflow_file": job.workflow_file,
                    "scheduled_run": previous_run,
                }
            }
        ]
    }
    refreshed_run = {
        "id": 17,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-08-13T01:10:00Z",
        "updated_at": "2026-08-14T12:34:00Z",
        "event": "schedule",
        "head_branch": "main",
    }
    calls = []

    def gh_json(args, timeout=10):
        calls.append((args, timeout))
        if "actions/runs?" in args[-1]:
            return {"workflow_runs": []}, None
        return {"workflow_runs": [refreshed_run]}, None

    monkeypatch.setattr(cron_health, "_gh_json", gh_json)

    statuses = cron_health.fetch_workflow_statuses(
        [job], previous_dashboard=previous_dashboard
    )

    assert statuses[job.id]["scheduled_run"]["conclusion"] == "success"
    assert len(calls) == 2


def test_workflow_collection_refreshes_overdue_cached_run(monkeypatch):
    job = next(job for job in list_cron_jobs() if job.id == "sync_3d_arena")
    previous_run = {
        "databaseId": 17,
        "status": "completed",
        "conclusion": "success",
        "createdAt": "2026-08-14T12:05:00Z",
        "updatedAt": "2026-08-14T12:06:00Z",
        "event": "schedule",
        "headBranch": "main",
    }
    previous_dashboard = {
        "jobs": [
            {
                "workflow_status": {
                    "available": True,
                    "workflow_file": job.workflow_file,
                    "scheduled_run": previous_run,
                }
            }
        ]
    }
    refreshed_run = {
        "id": 18,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-08-17T14:13:00Z",
        "updated_at": "2026-08-17T14:14:00Z",
        "event": "schedule",
        "head_branch": "main",
    }
    calls = []

    def gh_json(args, timeout=10):
        calls.append((args, timeout))
        if "actions/runs?" in args[-1]:
            return {"workflow_runs": []}, None
        return {"workflow_runs": [refreshed_run]}, None

    monkeypatch.setattr(cron_health, "_gh_json", gh_json)
    monkeypatch.setattr(
        cron_health,
        "_utcnow",
        lambda: datetime(2026, 8, 17, 14, 30, tzinfo=UTC),
    )

    statuses = cron_health.fetch_workflow_statuses(
        [job], previous_dashboard=previous_dashboard
    )

    assert statuses[job.id]["scheduled_run"]["databaseId"] == 18
    assert len(calls) == 2


@pytest.mark.parametrize("enabled", [False, True, None])
def test_operator_enablement_uses_one_bounded_query_for_both_duties(
    monkeypatch, enabled
):
    jobs = [
        job
        for job in list_cron_jobs()
        if job.output_evaluator == "autonomous_cron_operator"
    ]
    queries = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, query):
            queries.append(query)

        def fetchone(self):
            return {"enabled": enabled} if enabled is not None else None

    class Connection:
        def cursor(self, **_kwargs):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(cron_health.psycopg2, "connect", lambda **_kwargs: Connection())
    result = cron_health.fetch_db_freshness_batch(jobs)
    assert len(queries) == 1
    assert "WHERE operator = 'cron_health'" in queries[0]
    assert result == {job.id: {"operator_enabled": enabled} for job in jobs}
