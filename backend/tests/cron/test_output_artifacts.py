import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from backend.services import cron_health
from backend.services.cron_artifact_health import enrichment_snapshot_metrics


def test_mirror_counts_served_cache_not_render_scratch(tmp_path, monkeypatch):
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "image.jpg").write_bytes(b"image")
    monkeypatch.setattr(
        cron_health,
        "get_settings",
        lambda: SimpleNamespace(
            thumbnail_cache_dir=str(mirror),
            thumbnail_temp_cache_dir=str(tmp_path / "scratch"),
        ),
    )
    assert cron_health.fetch_thumbnail_cache_freshness()["file_count"] == 1


def context(db=None, work=None, **overrides):
    now = datetime.now(timezone.utc)
    values = dict(
        work=work or {},
        db=db or {},
        workflow={},
        systemd={
            "service_result": "success",
            "exec_main_status": 0,
            "last_completed_at": now - timedelta(minutes=5),
        },
        now=now,
        running=False,
        recent_log_success=False,
        db_reason="old writes",
        dependency_status=None,
    )
    values.update(overrides)
    return cron_health.OutputEvaluationContext(**values)


@pytest.mark.parametrize(
    "changed",
    [
        {},
        {"incomplete_partitions": 1},
        {"unaccounted_partitions": 1},
        {"retryable_failures": 1},
        {"total_partitions": 0},
    ],
)
def test_completed_reference_backfill_requires_accounted_partitions(changed):
    db = dict(
        total_partitions=20,
        incomplete_partitions=0,
        unaccounted_partitions=0,
        retryable_failures=0,
    )
    db.update(changed)
    status, _ = cron_health._backfill_contract(
        "degraded", ["old writes"], context(db=db)
    )
    assert status == ("healthy" if not changed else "degraded")


def test_completed_backfill_does_not_hide_other_failures():
    db = dict(
        total_partitions=20,
        incomplete_partitions=0,
        unaccounted_partitions=0,
        retryable_failures=0,
    )
    status, _ = cron_health._backfill_contract(
        "broken", ["provider failed"], context(db=db)
    )
    assert status == "broken"


def test_snapshot_validates_structure_without_exposing_contents(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(
        json.dumps(
            dict(
                schema_version=1,
                generated_at="2026-10-04T03:10:00Z",
                daily=[{}],
                papers=[{"private": "value"}],
                evaluations=[],
            )
        )
    )
    result = enrichment_snapshot_metrics(path)
    assert result["snapshot_valid"] is True
    assert result["snapshot_papers"] == 1
    assert "private" not in str(result)
    path.write_text("{}")
    assert enrichment_snapshot_metrics(path) == {"snapshot_valid": False}


def test_snapshot_needs_matching_export_completion():
    c = context()
    c.work.update(
        snapshot_valid=True, snapshot_generated_at=c.now - timedelta(minutes=6)
    )
    assert cron_health._enrichment_snapshot_contract("unknown", [], c)[0] == "healthy"
    c.work["snapshot_generated_at"] = c.now - timedelta(minutes=4)
    assert cron_health._enrichment_snapshot_contract("unknown", [], c)[0] == "unknown"
    c.work["snapshot_generated_at"] = c.now - timedelta(hours=40)
    assert cron_health._enrichment_snapshot_contract("unknown", [], c)[0] == "degraded"
