"""TabArena freshness must cover every evaluation owned by the sync."""

from datetime import datetime, timezone

import pytest

from backend.services.cron_health import evaluate_job_health
from backend.services.cron_registry import get_cron_job


@pytest.mark.parametrize(
    ("stale", "expected"), [(0, "healthy"), (1, "degraded"), (None, "unknown")]
)
def test_fresh_max_timestamp_does_not_hide_stale_tabarena_rows(stale, expected):
    now = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
    job = get_cron_job("sync_tabarena")
    result = evaluate_job_health(
        job,
        {"status": "success", "last_run": now},
        db_metrics={
            "last_write": now,
            "recent_writes": 73,
            "matched_evaluations": 74,
            "stale_evaluations": stale,
        },
        lock_state={"exists": False, "held": False},
        process_running=False,
        now=now,
    )
    assert result["output_health"]["status"] == expected
    if stale:
        assert (
            "1 managed TabArena evaluations are stale"
            in result["output_health"]["reason"]
        )


def test_tabarena_freshness_query_limits_counts_to_owned_rows():
    query = get_cron_job("sync_tabarena").db_freshness_query
    assert "t.slug = 'tabular-learning'" in query
    assert "d.slug = 'tabarena-v0-1'" in query
    assert "e.best_metric = 'Elo'" in query
    assert "e.external_source_url =" in query
    assert "https://huggingface.co/spaces/TabArena/leaderboard" in query
    assert "Managed by the Papers with Code TabArena live sync.%" in query
    assert "e.updated_at IS NULL" in query
    assert "AS stale_evaluations" in query
