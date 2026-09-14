"""Monitor production chat provider health and content-free journal signals."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.exc import SQLAlchemyError

from backend.config import Settings, get_settings
from backend.database.connection import db_manager
from backend.services.chat_operational_alert_service import (
    LIFECYCLE_ALERT_NAMES,
    claim_executor_transport_alert,
    executor_transport_alert_event,
    lifecycle_window_alerts,
    post_operational_alert,
    provider_health,
    provider_runtime_revision,
    provider_transition,
    reliability_alert_classifications,
    runtime_failure_counts,
    settle_executor_transport_alert,
)
from backend.services.autonomous_cron_probe import FindingState
from backend.services.chat_reliability_service import (
    probe_chat_aggregates,
    release_probe_triggers,
)
from backend.services.chat_synthetic_service import run_synthetic_chat

PRODUCTION_JOURNAL_UNITS = (
    "paperswithcode-backend@production",
    "paperswithcode-production-backend@blue",
    "paperswithcode-production-backend@green",
)
STATE_VERSION = 1
HISTORY_LIMIT = 100
HEALTH_RECORD = "chat-operational-alert-health.json"
MAX_RELIABILITY_FINDINGS = 32
EXECUTOR_ALERT_OWNER = "chat-operational-monitor"


def empty_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "journal_cursor": None,
        "provider_active": False,
        "journal_monitor_failed": False,
        "provider_monitor_failed": False,
        "lifecycle_active": [],
        "reliability_active": [],
        "reliability_monitor_failed": False,
        "last_reliability_probe_at": None,
        "last_synthetic_probe_at": None,
        "synthetic_active": None,
        "observed_release_id": None,
        "observed_provider_digest": None,
        "observed_provider_runtime_revision": None,
        "operational_counts": {},
        "events": [],
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return empty_state()
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        raise ValueError("chat operational alert state has an unsupported version")
    if not isinstance(state.get("events"), list):
        raise TypeError("chat operational alert state has invalid events")
    state.setdefault("lifecycle_active", [])
    state.setdefault("reliability_active", [])
    state.setdefault("reliability_monitor_failed", False)
    state.setdefault("last_reliability_probe_at", None)
    state.setdefault("last_synthetic_probe_at", None)
    state.setdefault("synthetic_active", None)
    state.setdefault("observed_release_id", None)
    state.setdefault("observed_provider_digest", None)
    state.setdefault("observed_provider_runtime_revision", None)
    state.setdefault("operational_counts", {})
    if (
        not isinstance(state["lifecycle_active"], list)
        or len(state["lifecycle_active"]) > len(LIFECYCLE_ALERT_NAMES)
        or not all(isinstance(name, str) for name in state["lifecycle_active"])
        or len(set(state["lifecycle_active"])) != len(state["lifecycle_active"])
        or not set(state["lifecycle_active"]).issubset(LIFECYCLE_ALERT_NAMES)
    ):
        raise TypeError("chat operational alert state has invalid lifecycle state")
    if (
        not isinstance(state["reliability_active"], list)
        or len(state["reliability_active"]) > MAX_RELIABILITY_FINDINGS
        or not all(
            isinstance(name, str) and len(name) <= 160
            for name in state["reliability_active"]
        )
        or len(set(state["reliability_active"])) != len(state["reliability_active"])
    ):
        raise TypeError("chat operational alert state has invalid reliability state")
    if not isinstance(state["reliability_monitor_failed"], bool):
        raise TypeError("chat operational alert state has invalid reliability status")
    if state["synthetic_active"] is not None and (
        not isinstance(state["synthetic_active"], str)
        or len(state["synthetic_active"]) > 160
        or not state["synthetic_active"].startswith("chat:")
    ):
        raise TypeError("chat operational alert state has invalid synthetic state")
    if not isinstance(state["operational_counts"], dict) or any(
        not isinstance(key, str)
        or len(key) > 64
        or not isinstance(value, int)
        or value < 0
        for key, value in state["operational_counts"].items()
    ):
        raise TypeError("chat operational alert state has invalid aggregate counts")
    provider_digest = state["observed_provider_digest"]
    if provider_digest is not None and (
        not isinstance(provider_digest, str)
        or len(provider_digest) != 64
        or any(character not in "0123456789abcdef" for character in provider_digest)
    ):
        raise TypeError("chat operational alert state has invalid provider digest")
    provider_revision = state["observed_provider_runtime_revision"]
    if provider_revision is not None and (
        not isinstance(provider_revision, str) or len(provider_revision) > 320
    ):
        raise TypeError("chat operational alert state has invalid provider revision")
    return state


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def current_provider_runtime_revision(environment: str) -> str | None:
    try:
        with db_manager.session_local() as db:
            return provider_runtime_revision(db, environment)
    except SQLAlchemyError:
        return None


def collect_reliability_events(
    state: dict[str, Any],
    settings: Settings,
    now: datetime,
    operational_counts: dict[str, int],
    trigger_events: list[dict[str, Any]],
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Run the 15-minute aggregate probe, with immediate post-alert checks."""

    previous = _timestamp(state.get("last_reliability_probe_at"))
    critical_trigger = any(
        event.get("severity") == "critical" for event in trigger_events
    )
    due = previous is None or now - previous >= timedelta(minutes=15)
    if not (due or force or critical_trigger):
        return []
    findings = probe_chat_aggregates(
        timedelta(minutes=15),
        settings=settings,
        now=now,
        operational_counts=operational_counts,
    )
    state["last_reliability_probe_at"] = now.isoformat()
    source_unknown = any(
        finding.state == FindingState.UNKNOWN
        and finding.evidence.get("incident_signature")
        == "chat:aggregate_source:incomplete"
        for finding in findings
    )
    source_was_unknown = state.get("reliability_monitor_failed") is True
    active = set(state.get("reliability_active", []))
    projected = reliability_alert_classifications(findings)
    current = set(projected)
    known_contracts = {
        finding.contract
        for finding in findings
        if finding.state != FindingState.UNKNOWN
    }
    recovered = {
        key for key in active - current if key.split("|", 1)[0] in known_contracts
    }
    entered = current - active
    events: list[dict[str, Any]] = []
    if source_unknown and not source_was_unknown:
        events.append(
            new_event(
                "chat_reliability_monitor_unavailable",
                now=now,
                count=sum(
                    finding.state == FindingState.UNKNOWN
                    and finding.evidence.get("incident_signature")
                    == "chat:aggregate_source:incomplete"
                    for finding in findings
                ),
                classifications={"chat:aggregate_source:incomplete": 1},
                window_start=now - timedelta(minutes=15),
            )
        )
    elif not source_unknown and source_was_unknown:
        events.append(
            new_event(
                "chat_reliability_monitor_recovered",
                now=now,
                classifications={"chat:aggregate_source:incomplete": 1},
                window_start=now - timedelta(minutes=15),
            )
        )
    if entered:
        events.append(
            new_event(
                "chat_reliability_threshold",
                now=now,
                count=len(entered),
                classifications={key: projected[key] for key in sorted(entered)},
                window_start=now - timedelta(minutes=15),
            )
        )
    if recovered:
        events.append(
            new_event(
                "chat_reliability_threshold_recovered",
                now=now,
                count=len(recovered),
                classifications={key: 1 for key in sorted(recovered)},
                window_start=now - timedelta(minutes=15),
            )
        )
    state["reliability_active"] = sorted((active - recovered) | current)
    state["reliability_monitor_failed"] = source_unknown
    return events


async def collect_synthetic_events(
    state: dict[str, Any],
    environment: str,
    now: datetime,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Run one paid synthetic turn at most four-hourly, plus forced checks."""

    previous = _timestamp(state.get("last_synthetic_probe_at"))
    if not force and previous is not None and now - previous < timedelta(hours=4):
        return []
    result = await run_synthetic_chat(environment, now=now)
    state["last_synthetic_probe_at"] = now.isoformat()
    prior = state.get("synthetic_active")
    current = (
        result.incident_signature
        if result.state in {FindingState.DEGRADED, FindingState.UNKNOWN}
        else None
    )
    events: list[dict[str, Any]] = []
    if current is not None and current != prior:
        events.append(
            new_event(
                "chat_synthetic_failure",
                now=now,
                classifications={current: 1},
            )
        )
    elif current is None and prior is not None:
        events.append(
            new_event(
                "chat_synthetic_recovered",
                now=now,
                classifications={prior: 1},
            )
        )
    state["synthetic_active"] = current
    return events


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.chmod(0o600)
    os.replace(temporary, path)


def write_health_record(
    directory: Path, payload: dict[str, Any], *, filename: str = HEALTH_RECORD
) -> None:
    """Persist only bounded, content-free output evidence for the dashboard."""

    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    # The parent directory is traversable only by the production service group.
    temporary.chmod(0o644)
    os.replace(temporary, path)


def read_journal(
    cursor: str | None, now: datetime
) -> tuple[list[str], str | None, bool]:
    def command_for(active_cursor: str | None) -> list[str]:
        command = ["journalctl"]
        for unit in PRODUCTION_JOURNAL_UNITS:
            command.extend(("--unit", unit))
        if active_cursor:
            command.extend(("--after-cursor", active_cursor))
        else:
            command.extend(("--since", (now - timedelta(minutes=2)).isoformat()))
        command.extend(("--output=json", "--show-cursor", "--no-pager", "--quiet"))
        return command

    reset = False
    try:
        result = subprocess.run(
            command_for(cursor), check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError:
        if not cursor:
            raise
        result = subprocess.run(
            command_for(None), check=True, capture_output=True, text=True
        )
        reset = True
    messages: list[str] = []
    latest_cursor = cursor
    for line in result.stdout.splitlines():
        if line.startswith("-- cursor: "):
            latest_cursor = line.removeprefix("-- cursor: ")
            continue
        record = json.loads(line)
        message = record.get("MESSAGE")
        record_cursor = record.get("__CURSOR")
        if isinstance(message, str):
            messages.append(message)
        if isinstance(record_cursor, str):
            latest_cursor = record_cursor
    return messages, latest_cursor, reset


def read_lifecycle_window(now: datetime, window_seconds: int) -> list[str]:
    command = ["journalctl"]
    for unit in PRODUCTION_JOURNAL_UNITS:
        command.extend(("--unit", unit))
    command.extend(
        (
            "--since",
            (now - timedelta(seconds=window_seconds)).isoformat(),
            "--grep",
            "chat durable lifecycle event=",
            "--output=json",
            "--no-pager",
            "--quiet",
        )
    )
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if getattr(result, "returncode", 0) not in (0, 1):
        raise subprocess.CalledProcessError(result.returncode, command)
    messages: list[str] = []
    for line in result.stdout.splitlines():
        message = json.loads(line).get("MESSAGE")
        if isinstance(message, str):
            messages.append(message)
    return messages


def new_event(
    signal: str,
    *,
    now: datetime,
    count: int = 1,
    classifications: dict[str, int] | None = None,
    window_start: datetime | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "signal": signal,
        "severity": "recovery" if signal.endswith("_recovered") else "critical",
        "count": count,
        "classifications": classifications or {},
        "window_start": (window_start or now).isoformat(),
        "window_end": now.isoformat(),
        "primary_delivery_state": "pending",
        "fallback_delivery_state": "pending",
        "primary_attempts": 0,
        "fallback_attempts": 0,
        "created_at": now.isoformat(),
    }


def append_event(state: dict[str, Any], event: dict[str, Any]) -> None:
    for existing in state["events"]:
        if existing["id"] == event["id"]:
            return
        if event["id"].startswith("executor-circuit:") or existing["id"].startswith(
            "executor-circuit:"
        ):
            continue
        pending = (
            existing["primary_delivery_state"] != "delivered"
            and existing["fallback_delivery_state"] != "delivered"
        )
        if pending and existing["signal"] == event["signal"]:
            existing["count"] += event["count"]
            for name, count in event["classifications"].items():
                existing["classifications"][name] = (
                    existing["classifications"].get(name, 0) + count
                )
            existing["window_end"] = event["window_end"]
            return
    state["events"].append(event)
    pending = [
        item
        for item in state["events"]
        if item["primary_delivery_state"] != "delivered"
        and item["fallback_delivery_state"] != "delivered"
    ]
    delivered = [item for item in state["events"] if item not in pending]
    state["events"] = [*pending, *delivered[-HISTORY_LIMIT:]]


def collect_executor_transport_events(now: datetime) -> list[dict[str, Any]]:
    """Claim at most one content-free durable circuit event per monitor minute."""

    with db_manager.session_local() as db:
        row = claim_executor_transport_alert(db, owner=EXECUTOR_ALERT_OWNER, now=now)
        if row is None:
            return []
        event = executor_transport_alert_event(
            environment=row.environment,
            epoch=row.epoch,
            transition=row.transition,
            now=row.created_at,
        )
        db.commit()
        return [event]


def settle_executor_transport_events(state: dict[str, Any], *, now: datetime) -> None:
    """Reflect primary/fallback delivery back to the durable outbox."""

    for event in state["events"]:
        if not event["id"].startswith("executor-circuit:"):
            continue
        delivered = (
            event["primary_delivery_state"] == "delivered"
            or event["fallback_delivery_state"] == "delivered"
        )
        with db_manager.session_local() as db:
            try:
                changed = settle_executor_transport_alert(
                    db,
                    event_id=event["id"],
                    owner=EXECUTOR_ALERT_OWNER,
                    acknowledged=delivered,
                    now=now,
                )
            except RuntimeError:
                db.rollback()
                continue
            if changed:
                db.commit()


async def deliver_pending(state: dict[str, Any], settings: Settings) -> int:
    delivered = 0
    for event in state["events"]:
        if (
            event["primary_delivery_state"] == "delivered"
            or event["fallback_delivery_state"] == "delivered"
        ):
            continue
        event["primary_attempts"] += 1
        try:
            await post_operational_alert(
                settings.chat_sandbox_slack_webhook_url, event, settings
            )
        except httpx.HTTPError:
            event["primary_delivery_state"] = "failed"
        else:
            event["primary_delivery_state"] = "delivered"
            event["fallback_delivery_state"] = "not_needed"
            delivered += 1
            continue
        event["fallback_attempts"] += 1
        try:
            await post_operational_alert(
                settings.chat_sandbox_alert_fallback_webhook_url, event, settings
            )
        except httpx.HTTPError:
            event["fallback_delivery_state"] = "failed"
        else:
            event["fallback_delivery_state"] = "delivered"
            delivered += 1
    return delivered


def collect_events(
    state: dict[str, Any], settings: Settings, now: datetime
) -> tuple[list[dict[str, Any]], bool]:
    events: list[dict[str, Any]] = []
    collection_failed = False
    try:
        messages, cursor, cursor_reset = read_journal(state.get("journal_cursor"), now)
        lifecycle_messages = read_lifecycle_window(
            now, settings.chat_lifecycle_alert_window_seconds
        )
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        collection_failed = True
        if not state["journal_monitor_failed"]:
            events.append(new_event("journal_monitor_unavailable", now=now))
        state["journal_monitor_failed"] = True
    else:
        state["journal_cursor"] = cursor
        if cursor_reset:
            events.append(new_event("journal_cursor_reset", now=now))
        failures = runtime_failure_counts(messages)
        if failures:
            events.append(
                new_event(
                    "chat_runtime_critical",
                    now=now,
                    count=sum(failures.values()),
                    classifications=failures,
                )
            )
        lifecycle_alerts = lifecycle_window_alerts(lifecycle_messages, settings)
        state["operational_counts"] = {**failures, **lifecycle_alerts}
        active = set(state["lifecycle_active"])
        current = set(lifecycle_alerts)
        entered = current - active
        recovered = active - current
        if entered:
            classifications = {name: lifecycle_alerts[name] for name in sorted(entered)}
            events.append(
                new_event(
                    "chat_lifecycle_threshold",
                    now=now,
                    count=sum(classifications.values()),
                    classifications=classifications,
                    window_start=now
                    - timedelta(seconds=settings.chat_lifecycle_alert_window_seconds),
                )
            )
        if recovered:
            events.append(
                new_event(
                    "chat_lifecycle_threshold_recovered",
                    now=now,
                    count=len(recovered),
                    classifications={name: 1 for name in sorted(recovered)},
                    window_start=now
                    - timedelta(seconds=settings.chat_lifecycle_alert_window_seconds),
                )
            )
        state["lifecycle_active"] = sorted(current)
        if state["journal_monitor_failed"]:
            events.append(new_event("journal_monitor_recovered", now=now))
        state["journal_monitor_failed"] = False

    try:
        with db_manager.session_local() as db:
            health = provider_health(db, settings, now)
    except SQLAlchemyError:
        collection_failed = True
        if not state["provider_monitor_failed"]:
            events.append(new_event("provider_monitor_unavailable", now=now))
        state["provider_monitor_failed"] = True
    else:
        transition = provider_transition(
            active=state["provider_active"], health=health, settings=settings
        )
        if transition:
            events.append(
                new_event(
                    transition,
                    now=now,
                    count=health.failed_turns,
                    classifications={
                        "failed_turns": health.failed_turns,
                        "total_turns": health.total_turns,
                        "failure_percent": health.failure_percent,
                    },
                    window_start=health.window_start,
                )
            )
        if transition == "hf_provider_sustained_failure":
            state["provider_active"] = True
        elif transition == "hf_provider_recovered":
            state["provider_active"] = False
        if state["provider_monitor_failed"]:
            events.append(new_event("provider_monitor_recovered", now=now))
        state["provider_monitor_failed"] = False
    return events, collection_failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-file",
        type=Path,
        help="Override the protected content-free state path for qualification",
    )
    args = parser.parse_args()
    settings = get_settings()
    completed_at = datetime.now(UTC).isoformat()
    if settings.environment != "production":
        parser.error("the operational alert monitor is production-only")
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
        write_health_record(Path(settings.cron_log_dir), result)
        print(json.dumps(result, sort_keys=True))
        return 0
    if not settings.chat_operational_alerts_enabled:
        parser.error("PWC_CHAT_OPERATIONAL_ALERTS_ENABLED is required")
    state_path = args.state_file or Path(settings.cron_log_dir).joinpath(
        "chat-operational-alert-state.json"
    )
    state = load_state(state_path)
    now = datetime.now(UTC)
    force_aggregate, _force_synthetic = release_probe_triggers(
        state,
        settings,
        provider_runtime_revision=current_provider_runtime_revision(
            settings.environment
        ),
    )
    events, collection_failed = collect_events(state, settings, now)
    if settings.chat_executor_remote_transport_enabled:
        try:
            events.extend(collect_executor_transport_events(now))
        except SQLAlchemyError:
            collection_failed = True
    events.extend(
        collect_reliability_events(
            state,
            settings,
            now,
            state.get("operational_counts", {}),
            events,
            force=force_aggregate,
        )
    )
    collection_failed = collection_failed or bool(
        state.get("reliability_monitor_failed")
    )
    for event in events:
        append_event(state, event)
    # Persist cursor and pending events before any network side effect.
    write_state(state_path, state)
    delivered = asyncio.run(deliver_pending(state, settings))
    if settings.chat_executor_remote_transport_enabled:
        try:
            settle_executor_transport_events(state, now=datetime.now(UTC))
        except SQLAlchemyError:
            collection_failed = True
    write_state(state_path, state)
    pending = sum(
        event["primary_delivery_state"] != "delivered"
        and event["fallback_delivery_state"] != "delivered"
        for event in state["events"]
    )
    result = {
        "environment": "production",
        "status": "degraded" if collection_failed or pending else "healthy",
        "completed_at": datetime.now(UTC).isoformat(),
        "new_events": len(events),
        "delivered": delivered,
        "pending": pending,
        "release_id": os.environ.get("PWC_RELEASE_ID"),
    }
    write_health_record(Path(settings.cron_log_dir), result)
    print(json.dumps(result, sort_keys=True))
    return 1 if collection_failed or pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
