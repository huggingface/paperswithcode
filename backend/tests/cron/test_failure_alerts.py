from backend.services.cron_health import failure_alert_status
from backend.services.cron_registry import get_cron_job

JOB = get_cron_job("refresh_paper_embeddings")


def _runs(streak: int) -> dict:
    return {
        "window_hours": 24,
        "runs": 24,
        "failures": streak,
        "consecutive_failures": streak,
        "last_failure_at": "2026-11-19T11:15:54+00:00" if streak else None,
    }


def test_embedding_refresh_opts_in_after_three_failures():
    assert JOB.failure_alert_after == 3


def test_alert_opens_at_threshold_and_closes_on_success():
    assert failure_alert_status(JOB, _runs(2))["alerting"] is False
    assert failure_alert_status(JOB, _runs(3)) == {
        "after_consecutive_failures": 3,
        "consecutive_failures": 3,
        "alerting": True,
        "last_failure_at": "2026-11-19T11:15:54+00:00",
    }
    assert failure_alert_status(JOB, _runs(0))["alerting"] is False


def test_missing_history_is_not_alerting():
    assert failure_alert_status(JOB, None)["alerting"] is False


def test_jobs_without_threshold_have_no_alert():
    other = get_cron_job("update_citations")
    assert other.failure_alert_after is None
    assert failure_alert_status(other, _runs(10)) is None
