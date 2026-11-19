"""Slack alerts for CRON jobs that keep failing.

The dashboard already marks a job broken after repeated failures, but nobody
looks at it while the job fails quietly (the query-embedding endpoint was in
error for 2.5 days in November 2026 before anyone noticed). Jobs opt in with
``CronJobDefinition.failure_alert_after``; the monitor posts once when a job's
consecutive launcher failures reach that count, repeats daily while the streak
lasts, and posts again when the job recovers.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import httpx

from backend.services.cron_registry import CronJobDefinition

STATE_FILE = "cron-failure-alerts.json"
REMIND_AFTER = timedelta(hours=24)
DASHBOARD_URL = "https://paperswithcode.co/admin-dashboard"


@dataclass(frozen=True)
class FailureAlert:
    job_id: str
    kind: str  # "failing" or "recovered"
    text: str


def load_state(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        # Missing before the first run, or unreadable from the web app user.
        return {}
    alerts = payload.get("alerts") if isinstance(payload, dict) else None
    return alerts if isinstance(alerts, dict) else {}


def save_state(
    path: Path, alerts: Mapping[str, Mapping[str, Any]], now: datetime
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"checked_at": now.isoformat(), "alerts": dict(alerts)}
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, sort_keys=True)
    os.replace(handle.name, path)


def plan_alerts(
    jobs: list[CronJobDefinition],
    history: Mapping[str, Mapping[str, Any]],
    state: Mapping[str, Mapping[str, Any]],
    now: datetime,
) -> tuple[list[FailureAlert], dict[str, dict[str, Any]]]:
    """Return the alerts to send and the open-alert state after sending them.

    ``history`` is ``cron_health.fetch_launcher_history()``; a job with no
    recent launcher exits keeps its open alert unchanged rather than counting
    as recovered.
    """

    alerts: list[FailureAlert] = []
    next_state: dict[str, dict[str, Any]] = {}
    for job in jobs:
        threshold = job.failure_alert_after
        if not threshold:
            continue
        open_alert = state.get(job.id)
        runs = history.get(job.id)
        if runs is None or not runs.get("runs"):
            if open_alert:
                next_state[job.id] = dict(open_alert)
            continue
        streak = int(runs.get("consecutive_failures") or 0)
        if streak >= threshold:
            notified_at = _parse(open_alert.get("notified_at")) if open_alert else None
            first = notified_at is None
            if first or now - notified_at >= REMIND_AFTER:
                alerts.append(
                    FailureAlert(
                        job.id,
                        "failing",
                        _failing_text(job, streak, runs, reminder=not first),
                    )
                )
                notified_at = now
            next_state[job.id] = {
                "since": (open_alert or {}).get("since") or now.isoformat(),
                "notified_at": notified_at.isoformat(),
                "consecutive_failures": streak,
                "last_failure_at": runs.get("last_failure_at"),
            }
        elif open_alert:
            # A streak below the threshold means a run succeeded since the alert.
            alerts.append(
                FailureAlert(
                    job.id,
                    "recovered",
                    f":white_check_mark: *{job.display_name}* (`{job.id}`) "
                    "succeeded again after the failures reported since "
                    f"{open_alert.get('since', 'earlier')}.",
                )
            )
    return alerts, next_state


def dashboard_status(
    job: CronJobDefinition,
    runs: Mapping[str, Any] | None,
    state: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    """The alert threshold and open alert shown on the job's dashboard card."""

    if not job.failure_alert_after:
        return None
    open_alert = state.get(job.id) or {}
    return {
        "after_consecutive_failures": job.failure_alert_after,
        "consecutive_failures": int((runs or {}).get("consecutive_failures") or 0),
        "alerting": bool(open_alert),
        "since": open_alert.get("since"),
        "notified_at": open_alert.get("notified_at"),
    }


def post_slack(webhook_url: str, text: str, *, timeout: float = 10.0) -> None:
    response = httpx.post(webhook_url, json={"text": text}, timeout=timeout)
    response.raise_for_status()


def _failing_text(
    job: CronJobDefinition,
    streak: int,
    runs: Mapping[str, Any],
    *,
    reminder: bool,
) -> str:
    prefix = "Still failing" if reminder else "CRON job keeps failing"
    return (
        f":rotating_light: *{prefix}: {job.display_name}* (`{job.id}`)\n"
        f"The last {streak} production runs failed "
        f"({runs.get('failures', streak)} of {runs.get('runs', streak)} in the "
        f"last {runs.get('window_hours', 24)}h; latest failure "
        f"{runs.get('last_failure_at') or 'unknown'}).\n"
        f"Log: `/var/lib/paperswithcode/production/cron-logs/{job.log_name}_*.log` "
        f"· Dashboard: {DASHBOARD_URL}"
    )


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
