"""Run the bounded production synthetic chat independently of minute polling."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.scripts.monitor_chat_operational_alerts import (
    _timestamp,
    append_event,
    collect_synthetic_events,
    deliver_pending,
    load_state,
    release_probe_triggers,
    write_health_record,
    write_state,
)
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
)

HEALTH_RECORD = "chat-synthetic-probe-health.json"


def synthetic_mutation_pause_reason() -> str | None:
    """Return the autonomous control that currently blocks paid probe mutation."""
    with db_manager.session_local() as db:
        control = AutonomousOperationsRepository().get_control_state(db)
    if control.manual_mode:
        return "manual_mode"
    if not control.enabled[Operator.CHAT_RELIABILITY]:
        return "operator_disabled"
    return None


def _critical_alert_after(state: dict[str, Any], previous: datetime | None) -> bool:
    for event in state.get("events", []):
        if not isinstance(event, dict) or event.get("severity") != "critical":
            continue
        created_at = _timestamp(event.get("created_at"))
        if created_at is not None and (previous is None or created_at > previous):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-file",
        type=Path,
        help="Override the protected synthetic state path for qualification",
    )
    parser.add_argument(
        "--operational-state-file",
        type=Path,
        help="Override the content-free operational state path for qualification",
    )
    args = parser.parse_args()
    settings = get_settings()
    completed_at = datetime.now(UTC).isoformat()
    if settings.environment != "production":
        parser.error("the synthetic chat probe is production-only")
    if not settings.chat_enabled:
        result = {
            "environment": "production",
            "status": "dormant",
            "completed_at": completed_at,
            "pending": 0,
            "new_events": 0,
            "delivered": 0,
            "release_id": os.environ.get("PWC_RELEASE_ID"),
        }
        write_health_record(Path(settings.cron_log_dir), result, filename=HEALTH_RECORD)
        print(json.dumps(result, sort_keys=True))
        return 0
    if not settings.chat_operational_alerts_enabled:
        parser.error("PWC_CHAT_OPERATIONAL_ALERTS_ENABLED is required")

    pause_reason = synthetic_mutation_pause_reason()
    if pause_reason is not None:
        result = {
            "environment": "production",
            "status": "paused",
            "reason_code": pause_reason,
            "completed_at": completed_at,
            "pending": 0,
            "new_events": 0,
            "delivered": 0,
            "release_id": settings.release_id,
        }
        write_health_record(Path(settings.cron_log_dir), result, filename=HEALTH_RECORD)
        print(json.dumps(result, sort_keys=True))
        return 0

    state_path = args.state_file or Path(settings.cron_log_dir).joinpath(
        "chat-synthetic-probe-state.json"
    )
    operational_state_path = args.operational_state_file or Path(
        settings.cron_log_dir
    ).joinpath("chat-operational-alert-state.json")
    state = load_state(state_path)
    now = datetime.now(UTC)
    previous = _timestamp(state.get("last_synthetic_probe_at"))
    _force_aggregate, force_release = release_probe_triggers(state, settings)
    operational_state = load_state(operational_state_path)
    force_alert = _critical_alert_after(operational_state, previous)
    events = asyncio.run(
        collect_synthetic_events(
            state,
            settings.environment,
            now,
            force=force_release or force_alert,
        )
    )
    for event in events:
        append_event(state, event)
    write_state(state_path, state)
    delivered = asyncio.run(deliver_pending(state, settings))
    write_state(state_path, state)
    pending = sum(
        event["primary_delivery_state"] != "delivered"
        and event["fallback_delivery_state"] != "delivered"
        for event in state["events"]
    )
    degraded = pending > 0 or state.get("synthetic_active") is not None
    result = {
        "environment": "production",
        "status": "degraded" if degraded else "healthy",
        "completed_at": datetime.now(UTC).isoformat(),
        "new_events": len(events),
        "delivered": delivered,
        "pending": pending,
        "release_id": os.environ.get("PWC_RELEASE_ID"),
    }
    write_health_record(Path(settings.cron_log_dir), result, filename=HEALTH_RECORD)
    print(json.dumps(result, sort_keys=True))
    return 1 if degraded else 0


if __name__ == "__main__":
    raise SystemExit(main())
