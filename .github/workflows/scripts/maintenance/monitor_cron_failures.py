"""Post Slack alerts for opted-in CRON jobs that keep failing."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.config import get_settings
from backend.services.cron_failure_alerts import (
    STATE_FILE,
    load_state,
    plan_alerts,
    post_slack,
    save_state,
)
from backend.services.cron_health import fetch_launcher_history
from backend.services.cron_registry import list_cron_jobs
from scripts.utils.cron_helpers import CronJobBase


class MonitorCronFailuresJob(CronJobBase):
    def __init__(self) -> None:
        super().__init__(job_name="monitor_cron_failures", log_level="INFO")

    def run(self) -> None:
        settings = get_settings()
        if not settings.cron_alert_slack_webhook_url:
            raise RuntimeError("PWC_CRON_ALERT_SLACK_WEBHOOK_URL is not configured")
        now = datetime.now(timezone.utc)
        state_path = Path(settings.cron_log_dir) / STATE_FILE
        alerts, next_state = plan_alerts(
            list(list_cron_jobs()),
            fetch_launcher_history(now=now),
            load_state(state_path),
            now,
        )
        # Post before saving, so a failed post is retried on the next run.
        for alert in alerts:
            post_slack(settings.cron_alert_slack_webhook_url, alert.text)
            self.logger.info("Posted %s alert for %s", alert.kind, alert.job_id)
        save_state(state_path, next_state, now)
        self.logger.info(
            "CRON_FAILURE_ALERTS_SUMMARY open=%d posted=%d",
            len(next_state),
            len(alerts),
        )


def main() -> int:
    return 0 if MonitorCronFailuresJob().execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
