"""CRON job health evaluation for the admin dashboard."""

from __future__ import annotations

import json
import logging
import os
import fcntl
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from posixpath import basename
from typing import Any, Callable, Dict, List, Literal, Optional, TypedDict

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import get_settings
from backend.services.autonomous_cron_probe import build_job_findings
from backend.services.cron_registry import CronJobDefinition, list_cron_jobs
from backend.services.cron_artifact_health import enrichment_snapshot_metrics

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
SCRIPTS_DIR = WORKFLOWS_DIR / "scripts"
GITHUB_REPOSITORY = "huggingface/paperswithcode"
WORKFLOW_STATUS_CACHE_SECONDS = 60
WORKFLOW_RUN_BATCH_PAGES = 3
MAX_LAUNCHER_EVIDENCE_BYTES = 1024 * 1024
# About a day of launcher records at today's every-minute job cadence.
MAX_LAUNCHER_HISTORY_BYTES = 4 * 1024 * 1024
LAUNCHER_HISTORY_HOURS = 24
MAX_SCHEDULE_STATE_BYTES = 4096
_WORKFLOW_STATUS_CACHE: Dict[tuple[str, str], tuple[float, Dict[str, Any]]] = {}
logger = logging.getLogger(__name__)

HealthStatus = Literal["healthy", "running", "unknown", "degraded", "broken", "stuck"]


class HealthResult(TypedDict):
    status: HealthStatus
    reason: str


class ExecutionHealthResult(HealthResult, total=False):
    scheduler: str
    applicable: bool
    last_expected_at: str | None
    next_expected_at: str | None
    last_started_at: str | None
    last_completed_at: str | None
    evidence_source: str | None
    recent_runs: Dict[str, Any]


class OutputHealthResult(HealthResult):
    last_verified_at: str | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_log_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%a %Y-%m-%d %H:%M:%S %Z",
    ):
        try:
            parsed = datetime.strptime(value.replace("+00:00", "Z"), fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def to_iso8601(value: Optional[datetime | str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        dt = _parse_log_timestamp(value)
        if dt is None:
            return value
        value = dt
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _capture_processes() -> tuple[list[tuple[int, int, str]], set[int]]:
    result = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,args="],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return [], set()
    processes: list[tuple[int, int, str]] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=2)
        if len(fields) != 3:
            continue
        pid, parent_pid, command = fields
        processes.append((int(pid), int(parent_pid), command))
    parents = {pid: parent_pid for pid, parent_pid, _command in processes}
    diagnostic_ancestry = {os.getpid()}
    cursor = os.getpid()
    while (parent := parents.get(cursor)) is not None:
        if parent in diagnostic_ancestry:
            break
        diagnostic_ancestry.add(parent)
        if parent == 1:
            break
        cursor = parent
    return processes, diagnostic_ancestry


def _patterns_are_running(
    patterns: tuple[str, ...],
    processes: list[tuple[int, int, str]],
    diagnostic_ancestry: set[int],
) -> bool:
    if not patterns:
        return False
    for pid, _parent_pid, command in processes:
        if pid in diagnostic_ancestry or "python" not in command or "grep" in command:
            continue
        if any(pattern in command for pattern in patterns):
            return True
    return False


def is_process_running(patterns: tuple[str, ...]) -> bool:
    processes, diagnostic_ancestry = _capture_processes()
    return _patterns_are_running(patterns, processes, diagnostic_ancestry)


def get_lock_state(
    lock_file: Optional[str], expected_runtime_minutes: int
) -> Dict[str, Any]:
    if not lock_file:
        return {
            "exists": False,
            "held": False,
            "probe_status": "not_applicable",
            "stale": False,
            "age_minutes": None,
        }

    path = Path(lock_file)
    if not path.exists():
        return {
            "exists": False,
            "held": False,
            "probe_status": "unlocked",
            "stale": False,
            "age_minutes": None,
        }

    age_minutes = (_utcnow().timestamp() - path.stat().st_mtime) / 60
    held: Optional[bool]
    probe_status = "unknown"
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                held = True
                probe_status = "held"
            else:
                held = False
                probe_status = "unlocked"
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    except (PermissionError, OSError):
        held = None
    return {
        "exists": True,
        "held": held,
        "probe_status": probe_status,
        # Backward-compatible field: only a confirmed held lock can be stale.
        "stale": held is True and age_minutes > expected_runtime_minutes,
        "age_minutes": round(age_minutes, 1),
        "path": str(path),
    }


def fetch_db_freshness(query: str) -> Dict[str, Any]:
    settings = get_settings()
    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        connect_timeout=5,
        options="-c statement_timeout=10000",
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query)
            row = cursor.fetchone() or {}
        metrics: Dict[str, Any] = {}
        last_write = row.get("last_write")
        if last_write is not None:
            metrics["last_write"] = last_write
            metrics["last_write_iso"] = to_iso8601(last_write)
        for key, value in row.items():
            if key == "last_write":
                continue
            metrics[key] = int(value or 0)
        return metrics
    finally:
        conn.close()


def _normalize_db_metric(_key: str, value: Any) -> Any:
    if isinstance(value, datetime):
        return to_iso8601(value)
    if isinstance(value, str):
        return value[:128]
    return int(value or 0)


def fetch_db_freshness_batch(
    jobs: list[CronJobDefinition],
) -> dict[str, Dict[str, Any]]:
    """Run every configured freshness query through one database connection."""

    settings = get_settings()
    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        connect_timeout=5,
        options="-c statement_timeout=10000",
    )
    conn.autocommit = True
    results: dict[str, Dict[str, Any]] = {}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            operator_jobs = [
                job
                for job in jobs
                if job.output_evaluator == "autonomous_cron_operator"
            ]
            if operator_jobs:
                try:
                    cursor.execute(
                        "SELECT enabled FROM autonomous_operator_state "
                        "WHERE operator = 'cron_health'"
                    )
                    state = cursor.fetchone() or {}
                    for job in operator_jobs:
                        results[job.id] = {"operator_enabled": state.get("enabled")}
                except psycopg2.Error as exc:
                    for job in operator_jobs:
                        results[job.id] = {
                            "operator_state_error": _sanitized_adapter_error(
                                exc, "operator state"
                            )
                        }
            for job in jobs:
                if not job.db_freshness_query:
                    continue
                try:
                    cursor.execute(job.db_freshness_query)
                    row = cursor.fetchone() or {}
                    metrics: Dict[str, Any] = {}
                    last_write = row.get("last_write")
                    if last_write is not None:
                        metrics["last_write"] = last_write
                        metrics["last_write_iso"] = to_iso8601(last_write)
                    for key, value in row.items():
                        if key != "last_write":
                            metrics[key] = _normalize_db_metric(key, value)
                    results[job.id] = metrics
                except Exception as exc:
                    results[job.id] = {
                        "freshness_error": _sanitized_adapter_error(
                            exc, "database freshness"
                        )
                    }
    finally:
        conn.close()
    return results


def fetch_thumbnail_cache_freshness() -> Dict[str, Any]:
    settings = get_settings()
    cache_dir = Path(settings.thumbnail_cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = Path(__file__).resolve().parents[2] / cache_dir

    if not cache_dir.exists():
        return {"file_count": 0, "last_write": None, "last_write_iso": None}

    newest_mtime = None
    file_count = 0
    for path in cache_dir.rglob("*"):
        if not path.is_file():
            continue
        file_count += 1
        mtime = path.stat().st_mtime
        if newest_mtime is None or mtime > newest_mtime:
            newest_mtime = mtime

    last_write = (
        datetime.fromtimestamp(newest_mtime, tz=timezone.utc) if newest_mtime else None
    )
    return {
        "file_count": file_count,
        "last_write": last_write,
        "last_write_iso": to_iso8601(last_write),
        "recent_writes": file_count,
    }


def _fetch_chat_health_output(filename: str) -> Dict[str, Any]:
    path = Path(get_settings().cron_log_dir) / filename
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return {"monitor_record_available": False}
    if len(raw) > 16 * 1024:
        return {"monitor_record_available": False}
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"monitor_record_available": False}
    if not isinstance(payload, dict):
        return {"monitor_record_available": False}
    return {
        "monitor_record_available": True,
        "monitor_status": str(payload.get("status") or "unknown")[:16],
        "monitor_reason_code": str(payload.get("reason_code") or "")[:64] or None,
        "monitor_completed_at": str(payload.get("completed_at") or "")[:64] or None,
        "undelivered_alert_events": max(0, int(payload.get("pending") or 0)),
        "new_alert_events": max(0, int(payload.get("new_events") or 0)),
        "delivered_alert_events": max(0, int(payload.get("delivered") or 0)),
    }


def fetch_chat_monitor_output() -> Dict[str, Any]:
    return _fetch_chat_health_output("chat-operational-alert-health.json")


def fetch_chat_synthetic_output() -> Dict[str, Any]:
    return _fetch_chat_health_output("chat-synthetic-probe-health.json")


def fetch_submission_review_output() -> Dict[str, Any]:
    path = (
        Path(get_settings().cron_log_dir) / "autonomous-submission-review-health.json"
    )
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return {"review_record_available": False}
    if len(raw) > 16 * 1024:
        return {"review_record_available": False}
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"review_record_available": False}
    if not isinstance(payload, dict):
        return {"review_record_available": False}
    return {
        "review_record_available": True,
        "review_status": str(payload.get("status") or "unknown")[:16],
        "review_completed_at": str(payload.get("completed_at") or "")[:64] or None,
        "submissions_claimed": max(0, int(payload.get("claimed") or 0)),
        "review_dry_run": bool(payload.get("dry_run")),
        "review_remote_launch": bool(payload.get("remote_launch")),
        "review_error_class": str(payload.get("error_class") or "")[:128] or None,
    }


def _persistent_execution_paths(settings: Any) -> tuple[Path, Path] | None:
    if settings.environment not in {"production", "staging"}:
        return None
    return (
        Path(settings.cron_log_dir) / "launcher.jsonl",
        Path("/srv/paperswithcode/environments")
        / settings.environment
        / "current/release.json",
    )


def fetch_persistent_execution(
    job: CronJobDefinition,
    log_status: Dict[str, Any],
    *,
    launcher_path: Path | None = None,
    manifest_path: Path | None = None,
) -> Dict[str, Any] | None:
    """Pair an exact-release launcher start with a terminal file-log result."""

    if launcher_path is None or manifest_path is None:
        paths = _persistent_execution_paths(get_settings())
        if paths is None:
            return None
        launcher_path, manifest_path = paths

    try:
        manifest_raw = manifest_path.read_bytes()
    except OSError:
        return None
    if len(manifest_raw) > 64 * 1024:
        return None
    try:
        manifest = json.loads(manifest_raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    release_sha = manifest.get("git_sha") if isinstance(manifest, dict) else None
    if not isinstance(release_sha, str) or not re.fullmatch(
        r"[0-9a-f]{40}", release_sha
    ):
        return None

    raw = _read_launcher_tail(launcher_path, MAX_LAUNCHER_EVIDENCE_BYTES)
    if raw is None:
        return None

    terminal_status = str(log_status.get("status") or "unknown")
    if terminal_status not in {"success", "success_no_work", "failed"}:
        return None
    completed = _parse_log_timestamp(log_status.get("last_run"))
    if completed is None:
        return None

    for raw_line in reversed(raw.splitlines()):
        try:
            record = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        # Terminal records ("exit", "lock_skipped") follow their launch record.
        if not isinstance(record, dict) or record.get("event"):
            continue
        if record.get("job") != job.id and record.get("health_job") != job.id:
            continue
        if record.get("git_sha") != release_sha:
            continue
        started = _parse_log_timestamp(record.get("at"))
        if started is None or completed < started:
            return None
        return {
            "status": "failed" if terminal_status == "failed" else "success",
            "started_at": to_iso8601(started),
            "completed_at": to_iso8601(completed),
            "release_sha": release_sha,
            "source": "launcher_and_file_log",
        }
    return None


def _read_launcher_tail(path: Path, max_bytes: int) -> bytes | None:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            offset = max(0, handle.tell() - max_bytes)
            handle.seek(offset)
            raw = handle.read(max_bytes)
    except OSError:
        return None
    return raw.partition(b"\n")[2] if offset else raw


def fetch_launcher_history(
    *,
    launcher_path: Path | None = None,
    now: datetime | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Count recent launcher exits, failures, and lock skips per health job.

    systemd keeps only the latest exit, so a job that fails every run but is
    running now, or a monitor that failed hundreds of times before its latest
    success, looks fine without this history.
    """

    if launcher_path is None:
        paths = _persistent_execution_paths(get_settings())
        if paths is None:
            return {}
        launcher_path = paths[0]
    raw = _read_launcher_tail(launcher_path, MAX_LAUNCHER_HISTORY_BYTES)
    if raw is None:
        return {}
    cutoff = (now or _utcnow()) - timedelta(hours=LAUNCHER_HISTORY_HOURS)
    history: Dict[str, Dict[str, Any]] = {}
    streak_closed: set[str] = set()
    for raw_line in reversed(raw.splitlines()):
        try:
            record = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("event") not in {
            "exit",
            "lock_skipped",
        }:
            continue
        finished = _parse_log_timestamp(record.get("at"))
        if finished is None or finished < cutoff:
            continue
        # `job` is the dashboard id; `health_job` names the log file, which for
        # lane jobs (e.g. sync_mmeb_v2 -> "v2") is not a dashboard id.
        job_id = str(record.get("job") or record.get("health_job") or "")
        summary = history.setdefault(
            job_id,
            {
                "window_hours": LAUNCHER_HISTORY_HOURS,
                "runs": 0,
                "failures": 0,
                "lock_skips": 0,
                "consecutive_failures": 0,
                "last_failure_at": None,
            },
        )
        if record["event"] == "lock_skipped":
            summary["lock_skips"] += 1
            continue
        summary["runs"] += 1
        if record.get("returncode") == 0:
            streak_closed.add(job_id)
            continue
        summary["failures"] += 1
        summary["last_failure_at"] = summary["last_failure_at"] or to_iso8601(finished)
        if job_id not in streak_closed:
            summary["consecutive_failures"] += 1
    return history


def _launcher_history_health(
    job: CronJobDefinition,
    execution: ExecutionHealthResult,
    history: Dict[str, Any] | None,
) -> ExecutionHealthResult:
    """Escalate execution health from recent failures the latest exit hides."""

    if not history or execution.get("applicable") is False:
        return execution
    runs = int(history.get("runs") or 0)
    failures = int(history.get("failures") or 0)
    streak = int(history.get("consecutive_failures") or 0)
    lock_skips = int(history.get("lock_skips") or 0)
    window = history.get("window_hours", LAUNCHER_HISTORY_HOURS)
    findings: list[tuple[str, str]] = []
    if streak >= 2:
        findings.append(("broken", f"the last {streak} launcher exits failed"))
    elif failures >= 3 and runs and failures / runs >= 0.1:
        findings.append(
            (
                "broken" if failures / runs >= 0.5 else "degraded",
                f"{failures} of {runs} runs failed in the last {window}h",
            )
        )
    if lock_skips and job.lock_skip_misses_work:
        findings.append(
            (
                "degraded",
                f"{lock_skips} run(s) skipped in the last {window}h because "
                "another run held the shared lock",
            )
        )
    if not findings:
        return {**execution, "recent_runs": history}
    status = execution["status"]
    for candidate, _reason in findings:
        status = _worse_output(status, candidate)
    reasons = [execution["reason"], *(reason for _status, reason in findings)]
    return {
        **execution,
        "status": status,
        "reason": "; ".join(reasons),
        "recent_runs": history,
    }


def fetch_autonomous_cron_output() -> Dict[str, Any]:
    path = Path(get_settings().cron_log_dir) / "autonomous-cron-operator-health.json"
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return {"operator_record_available": False}
    if len(raw) > 16 * 1024:
        return {"operator_record_available": False}
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"operator_record_available": False}
    if not isinstance(payload, dict):
        return {"operator_record_available": False}
    status = str(payload.get("status") or "unknown")[:32]
    healthy = status in {
        "healthy",
        "monitoring_only",
        "noop",
        "runtime_recovered",
        "source_repaired",
    }
    return {
        "operator_record_available": True,
        "operator_status": "healthy" if healthy else "degraded",
        "operator_completed_at": str(payload.get("completed_at") or "")[:64] or None,
        "operator_mode": str(payload.get("mode") or "")[:16] or None,
        "operator_reason_code": str(payload.get("reason_code") or "")[:128] or None,
    }


def _gh_json(args: list[str], timeout: int = 10) -> tuple[Any, Optional[str]]:
    env = os.environ.copy()
    github_token = get_settings().github_token
    if github_token:
        env["GH_TOKEN"] = github_token
    env["GH_REPO"] = GITHUB_REPOSITORY

    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            check=False,
            env=env,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return None, str(exc)

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "gh command failed").strip()
        return None, message

    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"failed to parse gh JSON: {exc}"


def _sanitized_adapter_error(value: object, adapter: str) -> str:
    message = str(value).lower()
    if any(token in message for token in ("auth", "credential", "401", "403")):
        return f"{adapter} authentication was rejected"
    if "permission" in message:
        return f"{adapter} permission denied"
    if "timeout" in message or "timed out" in message:
        return f"{adapter} request timed out"
    return f"{adapter} status is unavailable"


def _sanitized_job_error(value: object, job_id: str) -> str:
    message = str(value)
    lowered = message.lower()
    variables = sorted(set(re.findall(r"PWC_[A-Z0-9_]+", message)))
    variable = f" ({', '.join(variables)})" if variables else ""
    if any(token in lowered for token in ("credential", "token", "401", "403", "auth")):
        return f"{job_id} credential or authentication failure{variable}"
    if "429" in lowered or "rate limit" in lowered:
        return f"{job_id} upstream provider rate limiting"
    if "endpoint" in lowered:
        return f"{job_id} endpoint configuration or request failure{variable}"
    return f"{job_id} latest run failed"


def fetch_workflow_status(
    workflow_file: str,
    expected_jobs: tuple[str, ...] = (),
) -> Dict[str, Any]:
    """Fetch the latest GitHub Actions run for a workflow.

    This is best-effort: authentication or network failures should not hide fresh
    database writes, but when available the signal catches broken orchestration
    around jobs such as URL extraction's select/discover/persist pipeline.
    """

    cache_key = (workflow_file, "combined")
    cached = _WORKFLOW_STATUS_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < WORKFLOW_STATUS_CACHE_SECONDS:
        return dict(cached[1])

    def recent_runs(event: str) -> tuple[list[Dict[str, Any]], Optional[str]]:
        event_key = (workflow_file, event)
        event_cached = _WORKFLOW_STATUS_CACHE.get(event_key)
        if event_cached and now - event_cached[0] < WORKFLOW_STATUS_CACHE_SECONDS:
            return list(event_cached[1].get("runs") or []), event_cached[1].get("error")
        payload, event_error = _gh_json(
            [
                "run",
                "list",
                "--workflow",
                workflow_file,
                "--limit",
                "10",
                "--event",
                event,
                "--json",
                "databaseId,status,conclusion,createdAt,updatedAt,event,headBranch",
            ],
            timeout=8,
        )
        cached_payload = {"runs": payload or [], "error": event_error}
        _WORKFLOW_STATUS_CACHE[event_key] = (now, cached_payload)
        return list(payload or []), event_error

    scheduled_payload, error = recent_runs("schedule")
    if error:
        status = {
            "available": False,
            "workflow_file": workflow_file,
            "error": _sanitized_adapter_error(error, "GitHub Actions"),
        }
        _WORKFLOW_STATUS_CACHE[cache_key] = (now, status)
        return status

    manual_payload, manual_error = recent_runs("workflow_dispatch")
    list_payload = [*scheduled_payload, *manual_payload]
    list_payload.sort(key=lambda run: run.get("createdAt") or "", reverse=True)

    if not list_payload:
        status = {
            "available": True,
            "workflow_file": workflow_file,
            "status": "unknown",
            "conclusion": None,
            "error": "no workflow runs found",
        }
        _WORKFLOW_STATUS_CACHE[cache_key] = (now, status)
        return status

    scheduled_runs = list(scheduled_payload)
    manual_runs = list(manual_payload)
    active_runs = [
        run for run in list_payload if run.get("status") not in {None, "", "completed"}
    ]
    latest = scheduled_runs[0] if scheduled_runs else list_payload[0]
    run_id = latest.get("databaseId")
    view_payload = latest
    if run_id and len(expected_jobs) > 1:
        fetched_view, view_error = _gh_json(
            [
                "run",
                "view",
                str(run_id),
                "--json",
                "status,conclusion,createdAt,updatedAt,event,headBranch,jobs",
            ],
            timeout=10,
        )
        if view_error:
            view_payload = {
                **latest,
                "view_error": _sanitized_adapter_error(
                    view_error, "GitHub Actions job"
                ),
            }
        elif isinstance(fetched_view, dict):
            view_payload = {**latest, **fetched_view}

    jobs = view_payload.get("jobs") or []
    expected = set(expected_jobs)
    relevant_jobs = [job for job in jobs if not expected or job.get("name") in expected]
    failed_jobs = [
        job.get("name")
        for job in relevant_jobs
        if job.get("conclusion") not in {None, "", "success", "skipped"}
    ]
    running_jobs = [
        job.get("name")
        for job in relevant_jobs
        if job.get("status") not in {None, "", "completed"}
    ]

    status = {
        "available": True,
        "workflow_file": workflow_file,
        "run_id": run_id,
        "status": view_payload.get("status"),
        "conclusion": view_payload.get("conclusion"),
        "created_at": view_payload.get("createdAt"),
        "updated_at": view_payload.get("updatedAt"),
        "event": view_payload.get("event"),
        "head_branch": view_payload.get("headBranch"),
        "failed_jobs": [name for name in failed_jobs if name],
        "running_jobs": [name for name in running_jobs if name],
        "job_conclusions": {
            job.get("name"): job.get("conclusion")
            for job in relevant_jobs
            if job.get("name")
        },
        "view_error": view_payload.get("view_error"),
        "manual_query_error": (
            _sanitized_adapter_error(manual_error, "GitHub Actions manual-run")
            if manual_error
            else None
        ),
        "scheduled_run": scheduled_runs[0] if scheduled_runs else None,
        "manual_run": manual_runs[0] if manual_runs else None,
        "active_run": active_runs[0] if active_runs else None,
    }
    _WORKFLOW_STATUS_CACHE[cache_key] = (now, status)
    return status


def _systemd_show(unit: str, requested: str) -> Optional[Dict[str, str]]:
    try:
        result = subprocess.run(
            ["systemctl", "show", unit, f"--property={requested}"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )


def _system_boot_started_at() -> str | None:
    try:
        proc_stat = Path("/proc/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^btime\s+(\d+)$", proc_stat, re.MULTILINE)
    if match is None:
        return None
    started = datetime.fromtimestamp(int(match.group(1)), tz=timezone.utc)
    return to_iso8601(started)


def _read_systemd_pair(timer_unit: str, service_unit: str) -> Optional[Dict[str, Any]]:
    timer = _systemd_show(
        timer_unit,
        "LoadState,ActiveState,SubState,UnitFileState,LastTriggerUSec,"
        "NextElapseUSecRealtime,ActiveEnterTimestamp",
    )
    service = _systemd_show(
        service_unit,
        "LoadState,ActiveState,SubState,Result,ExecMainStatus,"
        "ExecMainStartTimestamp,ExecMainExitTimestamp,Job",
    )
    if timer is None or service is None:
        return None
    service_job = (
        _systemd_show(service["Job"], "JobType,State") if service.get("Job") else None
    )
    service_start_queued = bool(
        service_job
        and service_job.get("JobType") == "start"
        and service_job.get("State") in {"waiting", "running"}
    )
    return {
        "available": True,
        "timer": timer_unit,
        "service": service_unit,
        "enabled": timer.get("UnitFileState") in {"enabled", "enabled-runtime"},
        "timer_active": timer.get("ActiveState") == "active",
        "timer_state": timer.get("ActiveState"),
        "timer_substate": timer.get("SubState"),
        "last_trigger_at": timer.get("LastTriggerUSec") or None,
        "timer_activated_at": timer.get("ActiveEnterTimestamp") or None,
        "next_trigger_at": timer.get("NextElapseUSecRealtime") or None,
        "service_result": service.get("Result") or None,
        "exec_main_status": int(service.get("ExecMainStatus") or 0),
        "last_started_at": service.get("ExecMainStartTimestamp") or None,
        "last_completed_at": service.get("ExecMainExitTimestamp") or None,
        "service_active": service.get("ActiveState") == "active",
        "service_start_queued": service_start_queued,
        "boot_started_at": _system_boot_started_at(),
    }


def fetch_systemd_status(
    job: CronJobDefinition,
    log_status: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Read bounded timer/service properties for the registry-owned units.

    Duties driven by several timer/service pairs (for example the five
    preload_thumbnails lanes) are merged: the pair with the most recent
    completion provides the latest exit evidence, mirroring the previous
    latest-scheduled-workflow semantics.
    """

    pairs = job.systemd_unit_pairs
    if job.scheduler != "systemd" or not pairs:
        return {"available": False, "error": "systemd units are not registered"}

    statuses = []
    for timer_unit, service_unit in pairs:
        status = _read_systemd_pair(timer_unit, service_unit)
        if status is None:
            return {
                "available": False,
                "error": "systemd status permission denied or unavailable",
            }
        statuses.append(status)

    def timestamp_key(field: str):
        def key(status: Dict[str, Any]) -> datetime:
            parsed = _parse_log_timestamp(status.get(field))
            return parsed or datetime.min.replace(tzinfo=timezone.utc)

        return key

    latest = max(statuses, key=timestamp_key("last_completed_at"))
    queued_statuses = [
        status for status in statuses if status.get("service_start_queued")
    ]
    queued_triggers = [status.get("last_trigger_at") for status in queued_statuses]
    queued_since_at = None
    if queued_statuses and all(
        _parse_log_timestamp(value) is not None for value in queued_triggers
    ):
        queued_since_at = min(
            queued_triggers,
            key=lambda value: _parse_log_timestamp(value)
            or datetime.max.replace(tzinfo=timezone.utc),
        )
    merged = dict(latest)
    merged.update(
        enabled=all(status["enabled"] for status in statuses),
        timer_active=all(status["timer_active"] for status in statuses),
        service_active=any(status["service_active"] for status in statuses),
        service_start_queued=any(
            status.get("service_start_queued") for status in statuses
        ),
        queued_since_at=queued_since_at,
        last_started_at=max(statuses, key=timestamp_key("last_started_at")).get(
            "last_started_at"
        ),
        next_trigger_at=min(
            (
                status["next_trigger_at"]
                for status in statuses
                if status.get("next_trigger_at")
            ),
            key=lambda value: _parse_log_timestamp(value)
            or datetime.max.replace(tzinfo=timezone.utc),
            default=None,
        ),
        units=[status["service"] for status in statuses],
    )
    if not merged.get("last_completed_at") and log_status is not None:
        persistent = fetch_persistent_execution(job, log_status)
        if persistent is not None:
            merged["persistent_execution"] = persistent
    return merged


def discover_scheduled_duties() -> set[str]:
    """Discover pwc-cron duties from release-owned workflow and unit source."""

    duties: set[str] = set()
    for workflow in WORKFLOWS_DIR.glob("cron-*.yml"):
        source = workflow.read_text(encoding="utf-8")
        if not re.search(r"^\s{2}schedule:\s*$", source, re.MULTILINE):
            continue
        duties.update(re.findall(r"pwc-cron\s+([a-z0-9_]+)", source))
    duties.discard("status")

    deploy_dir = WORKFLOWS_DIR.parents[1] / "deploy"
    for pattern in (
        "systemd/pwc-*.service",
        "systemd/cron/pwc-*.service",
        "autonomous/*.service",
    ):
        for service in deploy_dir.glob(pattern):
            if not service.with_suffix(".timer").is_file():
                continue
            match = re.search(
                r"^ExecStart=.*/pwc-cron(?:-throttled)?\s+([a-z0-9_]+)",
                service.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
            if match:
                duties.add(match.group(1))
    return duties


def _schedule_slots(
    job: CronJobDefinition, now: datetime
) -> tuple[Optional[datetime], Optional[datetime]]:
    if not job.schedule_policies:
        return None, None
    pairs = [policy.slots(now) for policy in job.schedule_policies]
    return max(pair[0] for pair in pairs), min(pair[1] for pair in pairs)


def schedule_enabled(
    job: CronJobDefinition, settings: Any | None = None
) -> bool | None:
    """Return the configured scheduler state for conditionally enabled duties."""

    if not job.enablement_settings:
        return None
    active_settings = settings or get_settings()
    cron_log_dir = getattr(active_settings, "cron_log_dir", None)
    if job.id == "review_submissions" and cron_log_dir:
        state_path = Path(cron_log_dir) / "submission-review-schedule.json"
        try:
            state_raw = state_path.read_bytes()
        except FileNotFoundError:
            pass
        except OSError:
            return None
        else:
            if len(state_raw) > MAX_SCHEDULE_STATE_BYTES:
                return None
            try:
                state = json.loads(state_raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            if not isinstance(state, dict) or not isinstance(
                state.get("enabled"), bool
            ):
                return None
            return state["enabled"]
    return all(
        bool(getattr(active_settings, setting)) for setting in job.enablement_settings
    )


def _execution_health(
    job: CronJobDefinition,
    *,
    running: bool,
    log_status: Dict[str, Any],
    workflow_status: Dict[str, Any],
    systemd_status: Optional[Dict[str, Any]],
    schedule_enabled: bool | None,
    now: datetime,
) -> ExecutionHealthResult:
    previous_expected, next_expected = _schedule_slots(job, now)
    base = {
        "scheduler": job.scheduler,
        "last_expected_at": to_iso8601(previous_expected),
        "next_expected_at": to_iso8601(next_expected),
        "last_started_at": None,
        "last_completed_at": None,
    }

    if job.scheduler == "manual":
        result = log_status.get("status", "unknown")
        status = (
            "running"
            if running
            else (
                "broken"
                if result == "failed"
                else (
                    "healthy" if result in {"success", "success_no_work"} else "unknown"
                )
            )
        )
        return {
            **base,
            "status": status,
            "reason": (
                "manual invocation is active"
                if running
                else "latest manual invocation status"
            ),
        }

    grace = timedelta(minutes=job.schedule_grace_minutes)
    if job.scheduler == "systemd":
        evidence = systemd_status or {}
        if schedule_enabled is False:
            duty_name = (
                "autonomous submission review"
                if job.id == "review_submissions"
                else job.display_name
            )
            if not evidence.get("available"):
                return {
                    **base,
                    "status": "unknown",
                    "applicable": False,
                    "reason": (
                        "cannot verify disabled scheduler state because systemd "
                        "evidence is unavailable"
                    ),
                }
            if (
                evidence.get("enabled")
                or evidence.get("timer_active")
                or evidence.get("service_active")
                or running
            ):
                return {
                    **base,
                    "status": "broken",
                    "applicable": False,
                    "reason": (
                        f"{duty_name} timer is active while disabled by configuration"
                    ),
                }
            return {
                **base,
                "status": "healthy",
                "applicable": False,
                "reason": f"{duty_name} is disabled by configuration",
            }
        if not evidence.get("available"):
            return {
                **base,
                "status": "unknown",
                "reason": "systemd timer evidence is unavailable",
            }
        base.update(
            last_started_at=to_iso8601(evidence.get("last_started_at")),
            last_completed_at=to_iso8601(evidence.get("last_completed_at")),
            next_expected_at=to_iso8601(evidence.get("next_trigger_at"))
            or base["next_expected_at"],
        )
        if not evidence.get("enabled") or not evidence.get("timer_active"):
            return {
                **base,
                "status": "broken",
                "reason": "systemd timer is disabled or inactive",
            }
        if evidence.get("service_active") or running:
            age = _minutes_since(evidence.get("last_started_at"), now=now)
            if age is not None and age > job.expected_runtime_minutes:
                return {
                    **base,
                    "status": "stuck",
                    "reason": f"systemd service exceeded its {job.expected_runtime_minutes}m runtime budget",
                }
            return {**base, "status": "running", "reason": "systemd service is active"}
        if evidence.get("service_start_queued"):
            queue_budget = job.expected_runtime_minutes + job.schedule_grace_minutes
            queue_age = _minutes_since(evidence.get("queued_since_at"), now=now)
            if queue_age is None:
                return {
                    **base,
                    "status": "unknown",
                    "reason": (
                        "systemd start is queued but its queue age is unavailable"
                    ),
                }
            if queue_age > queue_budget:
                return {
                    **base,
                    "status": "stuck",
                    "reason": (
                        "systemd start remained queued beyond its "
                        f"{queue_budget}m budget"
                    ),
                }
            return {
                **base,
                "status": "running",
                "reason": "systemd start is queued",
            }
        if evidence.get("service_result") not in {None, "", "success"} or evidence.get(
            "exec_main_status"
        ) not in {None, 0}:
            return {
                **base,
                "status": "broken",
                "reason": "latest systemd service invocation failed",
            }
        completed = _parse_log_timestamp(evidence.get("last_completed_at"))
        if completed is None and (persistent := evidence.get("persistent_execution")):
            base.update(
                last_started_at=to_iso8601(persistent.get("started_at")),
                last_completed_at=to_iso8601(persistent.get("completed_at")),
                evidence_source=persistent.get("source"),
            )
            if persistent.get("status") == "failed":
                return {
                    **base,
                    "status": "broken",
                    "reason": "persistent execution evidence reports failure",
                }
            completed = _parse_log_timestamp(persistent.get("completed_at"))
        if completed is None and previous_expected:
            boot_started = _parse_log_timestamp(evidence.get("boot_started_at"))
            last_trigger = _parse_log_timestamp(evidence.get("last_trigger_at"))
            if (
                boot_started is not None
                and previous_expected < boot_started
                and last_trigger is not None
                and last_trigger < boot_started
            ):
                return {
                    **base,
                    "status": "unknown",
                    "reason": (
                        "pre-reboot systemd slot lacks persistent terminal evidence"
                    ),
                }
        if previous_expected and (
            completed is None or completed < previous_expected - grace
        ):
            # Restarts and reboots also move ActiveEnterTimestamp, but the
            # Persistent=true stamp keeps LastTriggerUSec, so only a timer that
            # has never fired was installed after the slot. Manual runs before
            # activation leave completion evidence but owe no timer slot.
            activated = _parse_log_timestamp(evidence.get("timer_activated_at"))
            if (
                activated is not None
                and previous_expected < activated
                and not evidence.get("last_trigger_at")
            ):
                return {
                    **base,
                    "status": "healthy",
                    "reason": (
                        "timer enabled after the last scheduled slot; "
                        "first systemd invocation pending"
                    ),
                }
            late = now > previous_expected + grace
            return {
                **base,
                "status": "broken" if late else "degraded",
                "reason": (
                    "expected systemd invocation is overdue"
                    if late
                    else "waiting for expected systemd invocation"
                ),
            }
        return {
            **base,
            "status": "healthy",
            "reason": "systemd timer and latest service exit are healthy",
        }

    evidence = workflow_status or {}
    if not evidence.get("available"):
        return {
            **base,
            "status": "unknown",
            "reason": "GitHub Actions evidence is unavailable",
        }
    scheduled = evidence.get("scheduled_run")
    # Backward compatibility for callers/tests that provide one normalized run.
    if (
        scheduled is None
        and evidence.get("event") in {None, "schedule"}
        and evidence.get("status")
    ):
        scheduled = {
            "status": evidence.get("status"),
            "conclusion": evidence.get("conclusion"),
            "createdAt": evidence.get("created_at"),
            "updatedAt": evidence.get("updated_at"),
        }
    active = evidence.get("active_run")
    if active and active.get("event") == "schedule":
        started = _parse_log_timestamp(active.get("createdAt"))
        base["last_started_at"] = to_iso8601(started)
        if started and now - started > timedelta(minutes=job.expected_runtime_minutes):
            return {
                **base,
                "status": "stuck",
                "reason": f"scheduled workflow exceeded its {job.expected_runtime_minutes}m runtime budget",
            }
        return {**base, "status": "running", "reason": "scheduled workflow is active"}
    if scheduled:
        started = _parse_log_timestamp(scheduled.get("createdAt"))
        completed = _parse_log_timestamp(scheduled.get("updatedAt"))
        base.update(
            last_started_at=to_iso8601(started), last_completed_at=to_iso8601(completed)
        )
        if scheduled.get("status") == "completed" and scheduled.get(
            "conclusion"
        ) not in {None, "", "success", "skipped"}:
            return {
                **base,
                "status": "broken",
                "reason": "latest scheduled workflow failed",
            }
        if scheduled.get("status") != "completed":
            return {
                **base,
                "status": "running",
                "reason": "scheduled workflow is active",
            }
        if previous_expected and (started is None or started < previous_expected):
            late = now > previous_expected + grace
            return {
                **base,
                "status": "broken" if late else "degraded",
                "reason": (
                    "scheduled workflow is overdue"
                    if late
                    else "waiting for the scheduled workflow to start"
                ),
            }
        return {
            **base,
            "status": "healthy",
            "reason": "latest scheduled workflow completed successfully",
        }

    if previous_expected:
        late = now > previous_expected + grace
        return {
            **base,
            "status": "broken" if late else "degraded",
            "reason": "no scheduled workflow run was found",
        }
    return {
        **base,
        "status": "unknown",
        "reason": "scheduled workflow evidence is missing",
    }


def _aggregate_health(
    execution: ExecutionHealthResult, output: OutputHealthResult
) -> HealthStatus:
    statuses = {execution["status"], output["status"]}
    if "stuck" in statuses:
        return "stuck"
    if "broken" in statuses:
        return "broken"
    if "degraded" in statuses:
        return "degraded"
    if "unknown" in statuses:
        return "unknown"
    if "running" in statuses:
        return "running"
    return "healthy"


_OUTPUT_RANK = {
    "healthy": 0,
    "running": 0,
    "unknown": 1,
    "degraded": 2,
    "broken": 3,
    "stuck": 4,
}


def _worse_output(current: str, candidate: str) -> str:
    return candidate if _OUTPUT_RANK[candidate] > _OUTPUT_RANK[current] else current


@dataclass(frozen=True)
class OutputEvaluationContext:
    """Typed evidence available to one registry-selected output policy."""

    work: Dict[str, Any]
    db: Dict[str, Any]
    workflow: Dict[str, Any]
    systemd: Dict[str, Any]
    now: datetime
    running: bool
    recent_log_success: bool
    db_reason: str | None
    dependency_status: str | None


def _tabarena_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    stale = context.db.get("stale_evaluations")
    if stale is None:
        return _worse_output(status, "unknown"), reasons + [
            "TabArena owned-row freshness evidence is unavailable"
        ]
    if stale:
        return _worse_output(status, "degraded"), reasons + [
            f"{stale} managed TabArena evaluations are stale; "
            "check unresolved paper identities"
        ]
    return status, reasons


def _conference_deadlines_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    overdue = context.db.get("top_tier_overdue")
    if overdue is None:
        return _worse_output(status, "unknown"), reasons + [
            "conference deadline freshness evidence is unavailable"
        ]
    without = context.db.get("top_tier_without_upcoming")
    total = context.db.get("top_tier_series")
    note = (
        f"{without} of {total} top-tier conferences have no upcoming deadline; "
        f"{overdue} are overdue by last cycle's calendar"
    )
    if overdue >= 3:
        return _worse_output(status, "degraded"), reasons + [
            note + "; check the latest sweep's results and add editions by hand"
        ]
    return status, reasons + [note]


def _workflow_output_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    if status != "unknown":
        return status, reasons
    conclusion = context.workflow.get("conclusion")
    completed = context.workflow.get("status") == "completed"
    if completed and conclusion in {"success", "skipped"}:
        return "healthy", ["workflow completed its job-owned output contract"]
    return status, reasons


def _paper_markdown_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work = context.work
    remaining = int(work.get("missing_after_upstream", 0) or 0)
    blocker = work.get("blocker_classification")
    budget_blocked = blocker in {"budget", "reliability_and_budget"}
    reliability_blocked = blocker in {"reliability", "reliability_and_budget"}
    if work.get("paid_authorization_required") and remaining:
        status = _worse_output(status, "degraded")
        reasons.append(
            "measured OCR profile awaits explicit paid execution authorization"
        )
    if (work.get("budget_exhausted") or budget_blocked) and remaining:
        status = _worse_output(status, "degraded")
        next_admission = work.get("next_admission_at")
        suffix = f"; next admission {next_admission}" if next_admission else ""
        reasons.append(
            (
                "OCR budget is exhausted and is the only blocker with "
                f"{remaining} papers still missing{suffix}"
            )
            if not reliability_blocked
            else (
                "OCR budget is exhausted alongside a reliability blocker with "
                f"{remaining} papers still missing{suffix}"
            )
        )
    semantic_invalid = int(work.get("semantic_invalid_existing", 0) or 0)
    if semantic_invalid:
        status = _worse_output(status, "broken")
        reasons.append(
            f"{semantic_invalid} semantic-invalid existing Markdown object(s) "
            "are excluded from usable coverage"
        )
    semantic_failures = int(work.get("semantic_validation_failures", 0) or 0)
    if semantic_failures:
        status = _worse_output(status, "broken")
        reasons.append(
            f"{semantic_failures} Markdown semantic validation failure(s) were recorded"
        )
    semantic_unavailable = int(work.get("semantic_evidence_unavailable", 0) or 0)
    if semantic_unavailable:
        status = _worse_output(status, "unknown")
        reasons.append(
            f"semantic evidence is unavailable for {semantic_unavailable} "
            "recent Markdown object(s)"
        )
    if work.get("remote_monitor_available") is False and status == "healthy":
        status = "unknown"
        reasons.append("remote OCR shard evidence is unavailable")
    terminal = int(work.get("terminal_shard_failures", 0) or 0)
    unresolved_mounts = int(work.get("unresolved_mount_failures", 0) or 0)
    if unresolved_mounts:
        status = _worse_output(status, "broken")
        reasons.append(
            f"{unresolved_mounts} logical OCR shard(s) have an unresolved "
            "volume mount failure"
        )
    if terminal and not unresolved_mounts:
        status = _worse_output(status, "broken")
        reasons.append(
            f"{terminal} remote OCR shard(s) had no usable output or a worker failure"
        )
    interrupted = int(work.get("interrupted_shards", 0) or 0)
    if interrupted:
        status = _worse_output(status, "degraded")
        reasons.append(
            f"{interrupted} remote OCR shard(s) made partial progress before interruption"
        )
    checkpoint_age = work.get("oldest_active_checkpoint_age_minutes")
    if checkpoint_age is not None and float(checkpoint_age) > 30:
        status = _worse_output(status, "broken")
        reasons.append("remote OCR progress checkpoint is stale")
    return status, reasons


def _paper_markdown_monitor_snapshot() -> Dict[str, Any]:
    """Use the short cache, but populate it once in a cold health process."""
    from backend.services.paper_markdown_job_monitor import (
        get_cached_paper_markdown_job_monitor,
        get_paper_markdown_job_monitor,
    )

    snapshot = get_cached_paper_markdown_job_monitor()
    if snapshot.get("updated_at") is None:
        snapshot = get_paper_markdown_job_monitor()
    return snapshot


def _merge_paper_markdown_monitor_metrics(
    work_metrics: Dict[str, Any],
    remote: Dict[str, Any],
) -> Dict[str, Any]:
    metrics = dict(work_metrics)
    summary = remote.get("summary") or {}
    metrics["remote_monitor_available"] = bool(remote.get("available"))
    summary_metrics = {
        "progress_evidence_timeouts": "remote_progress_evidence_timeouts",
        "latest_run_failed_jobs": "terminal_shard_failures",
        "latest_run_interrupted_jobs": "interrupted_shards",
        "oldest_active_checkpoint_age_minutes": (
            "oldest_active_checkpoint_age_minutes"
        ),
        "unresolved_mount_failures": "unresolved_mount_failures",
        "recovered_mount_failures": "recovered_mount_failures",
    }
    for summary_key, metric_key in summary_metrics.items():
        if summary_key in summary:
            metrics[metric_key] = int(summary.get(summary_key) or 0)
    metrics.setdefault("remote_progress_evidence_timeouts", 0)
    mode = str(metrics.get("mode") or "live")
    budget = (remote.get("budgets") or {}).get(mode) or {}
    blockers = remote.get("blockers") or {}
    if mode in blockers:
        metrics["blocker_classification"] = blockers.get(mode) or "none"
    else:
        metrics.setdefault("blocker_classification", "none")
    if "next_admission_at" in budget:
        metrics["next_admission_at"] = budget.get("next_admission_at")
    return metrics


def _paper_embeddings_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work, db = context.work, context.db
    missing = int(db.get("missing_embeddings", 0) or 0)
    hash_mismatches = int(db.get("content_hash_mismatches", 0) or 0)
    candidates = work.get("candidates")
    embedded = int(work.get("embeddings_updated", work.get("embedded", 0)) or 0)
    if missing and candidates == 0:
        status = _worse_output(status, "broken")
        reasons.append(
            f"{missing} eligible embeddings are missing despite a no-work run"
        )
    elif missing and candidates is not None and embedded == 0:
        status = _worse_output(status, "degraded")
        reasons.append(f"no embeddings were written while {missing} remain eligible")
    if hash_mismatches and candidates == 0:
        status = _worse_output(status, "broken")
        reasons.append(
            f"{hash_mismatches} active-generation content hashes are stale "
            "despite a no-work run"
        )
    elif hash_mismatches and candidates is not None and embedded == 0:
        status = _worse_output(status, "degraded")
        reasons.append(
            f"no embeddings were written while {hash_mismatches} content hashes are stale"
        )
    return status, reasons


def _hf_import_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work = context.work
    if work.get("upstream_fetch_succeeded") is False:
        return "broken", reasons + ["Hugging Face daily-paper feed fetch failed"]
    if work.get("upstream_fetch_succeeded") is True:
        failed = int(work.get("failed", 0) or 0)
        if failed:
            status = _worse_output(status, "broken")
            reasons.append(f"{failed} imported paper(s) failed")
        elif status == "unknown":
            status = "healthy"
            reasons.append("upstream feed was fetched and the import summary completed")
    return status, reasons


def _github_stars_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work = context.work
    if not context.running:
        for queue in ("fresh", "weekly"):
            selected = int(work.get(f"{queue}_selected_groups", 0) or 0)
            successes = int(work.get(f"{queue}_successes", 0) or 0)
            failures = int(work.get(f"{queue}_failures", 0) or 0)
            credential_failures = int(work.get(f"{queue}_credential_failures", 0) or 0)
            credential = work.get(f"{queue}_credential", f"{queue} GitHub credential")
            if selected and not successes and failures:
                status = _worse_output(status, "broken")
                if credential_failures:
                    reasons.append(
                        f"{credential} was rejected by GitHub; "
                        f"the {queue} queue had no successful fetches"
                    )
                else:
                    reasons.append(
                        f"{queue} GitHub queue had no successful fetches "
                        f"({failures} failures)"
                    )
            elif credential_failures:
                status = _worse_output(status, "degraded")
                reasons.append(
                    f"{credential} had {credential_failures} rejected request(s)"
                )

    for queue in ("fresh", "weekly"):
        stops = int(work.get(f"{queue}_rate_limit_stops", 0) or 0)
        selected = int(work.get(f"{queue}_selected_groups", 0) or 0)
        successes = int(work.get(f"{queue}_successes", 0) or 0)
        if stops:
            candidate = "broken" if selected and not successes else "degraded"
            status = _worse_output(status, candidate)
            reasons.append(f"{queue} queue exhausted its GitHub rate-limit reserve")
    return status, reasons


def _hot_github_trending_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work, db = context.work, context.db
    oldest_wait = int(db.get("oldest_eligible_wait_minutes", 0) or 0)
    stale_scores = int(db.get("stale_paper_scores", 0) or 0)
    one_snapshot = int(db.get("one_snapshot_over_30m", 0) or 0)
    reserve_stops = int(work.get("rate_limit_stops", 0) or 0)
    remaining = work.get("rate_limit_remaining")
    reserve = work.get("rate_limit_reserve")
    credential_failures = int(work.get("credential_failures", 0) or 0)
    credential = work.get("credential", "GitHub credential")

    if db.get("hot_repository_count") == 0 and context.recent_log_success:
        status = "healthy"
        if context.db_reason:
            reasons = [reason for reason in reasons if reason != context.db_reason]

    if oldest_wait > 30:
        status = _worse_output(status, "broken")
        reasons.append(f"oldest eligible hot repository has waited {oldest_wait}m")
    if stale_scores:
        status = _worse_output(status, "broken")
        reasons.append(f"{stale_scores} hot paper scores are missing or stale")
    if credential_failures:
        status = _worse_output(status, "broken")
        reasons.append(
            f"{credential} was rejected by GitHub "
            f"({credential_failures} failed requests)"
        )
    if one_snapshot and status == "healthy":
        status = "degraded"
        reasons.append(f"{one_snapshot} hot repositories have one snapshot after 30m")
    if reserve_stops:
        if status == "healthy":
            status = "degraded"
        reasons.append(f"rate-limit reserve stopped {reserve_stops} run(s)")
    if remaining is not None and reserve is not None and int(remaining) < int(reserve):
        status = _worse_output(status, "broken")
        reasons.append(
            f"rate-limit reserve violated ({remaining} remaining < {reserve})"
        )
    return status, reasons


def _counter_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work, db = context.work, context.db
    scanned = work.get(
        "papers_scanned",
        work.get(
            "papers_processed",
            work.get("repositories_processed", work.get("eligible_population")),
        ),
    )
    if scanned is None and db.get("papers_scanned") is None and status == "healthy":
        status = "unknown"
        reasons.append("job-owned scanned/fetched counters are unavailable")
    return status, reasons


def _provider_counter_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work = context.work
    status, reasons = _counter_contract(status, reasons, context)
    throttled = int(work.get("rate_limit_hits", 0) or 0)
    api_calls = int(work.get("api_calls", 0) or 0)
    failures = int(
        work.get("api_errors", 0)
        or work.get("papers_failed", 0)
        or work.get("artifacts_failed", 0)
        or 0
    )
    # Retried throttling is routine; only a material share of calls matters.
    if throttled and (not api_calls or throttled / api_calls >= 0.05):
        status = _worse_output(status, "degraded")
        reasons.append(f"upstream provider rate-limited {throttled} request(s)")
    if failures:
        status = _worse_output(status, "degraded")
        reasons.append(f"{failures} upstream item(s) failed")
    return status, reasons


def _trending_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    db = context.db
    status, reasons = _counter_contract(status, reasons, context)
    eligible = int(db.get("eligible_population", 0) or 0)
    positive = int(
        db.get("fresh_positive_scores", db.get("fresh_github_component_scores", 0)) or 0
    )
    if eligible and not positive:
        status = _worse_output(status, "broken")
        reasons.append("eligible population produced no positive trending components")
    elif "eligible_population" in db and eligible == 0:
        status = "healthy"
        reasons.append("eligible population is empty; successful no-work is valid")
    elif status == "unknown" and positive and int(db.get("recent_writes", 0) or 0) > 0:
        status = "healthy"
        reasons.append("database confirms fresh positive trending output")
    dependency_status = context.dependency_status
    if dependency_status and dependency_status not in {"healthy", "running"}:
        status = _worse_output(status, "degraded")
        reasons.append(f"dependency calculate_trending_scores is {dependency_status}")
    return status, reasons


def _organization_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    db = context.db
    status, reasons = _counter_contract(status, reasons, context)
    missing = int(db.get("missing_today_snapshots", 0) or 0)
    if missing:
        status = _worse_output(status, "degraded")
        reasons.append(f"{missing} managed organization(s) missed today's snapshot")
    return status, reasons


def _thumbnail_preload_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work = context.work
    status, reasons = _workflow_output_contract(status, reasons, context)
    failures = int(work.get("failed_downloads", 0) or 0)
    if failures:
        status = _worse_output(status, "degraded")
        reasons.append(f"{failures} thumbnail download(s) failed")
    return status, reasons


def _backfill_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work, db = context.work, context.db
    completed_age = _minutes_since(
        context.systemd.get("last_completed_at"), now=context.now
    )
    if (
        status == "degraded"
        and reasons == [context.db_reason]
        and not db.get("freshness_error")
        and int(db.get("total_partitions", 0) or 0) > 0
        and db.get("incomplete_partitions") == 0
        and db.get("unaccounted_partitions") == 0
        and db.get("retryable_failures") == 0
        and context.systemd.get("service_result") == "success"
        and context.systemd.get("exec_main_status") == 0
        and completed_age is not None
        and 0 <= completed_age <= 120
    ):
        status = "healthy"
        reasons = [
            "latest successful reconciliation found all recorded reference "
            "partitions complete and all papers processed or unresolvable"
        ]
    stale_running = int(db.get("stale_running", 0) or 0)
    if stale_running:
        status = _worse_output(status, "broken")
        reasons.append(f"{stale_running} stale database run row(s) block progress")
        blocking_age = int(db.get("blocking_run_age_minutes", 0) or 0)
        cursor = db.get("resume_cursor")
        if blocking_age:
            reasons.append(f"blocking run age is {blocking_age}m")
        if cursor is not None:
            reasons.append(f"resume cursor is {cursor}")
    elif int(db.get("running_runs", 0) or 0):
        checkpoint_age = int(db.get("checkpoint_age_minutes", 0) or 0)
        cursor = db.get("resume_cursor")
        reasons.append(
            f"fresh resumable checkpoint is {checkpoint_age}m old"
            + (f" at cursor {cursor}" if cursor is not None else "")
        )
    failed_runs = int(db.get("failed_runs", 0) or 0)
    if failed_runs:
        status = _worse_output(status, "degraded")
        reasons.append(f"{failed_runs} backfill run partition(s) are failed")
    provider_429 = int(db.get("provider_429_rows", 0) or 0)
    retryable = int(db.get("retryable_failures", 0) or 0)
    if provider_429:
        status = _worse_output(status, "degraded")
        reasons.append(
            f"provider rate limiting affects {provider_429} partition(s); "
            f"{retryable} retryable item(s) remain"
        )
    throttled = int(
        work.get("provider_rate_limit_hits", work.get("rate_limit_hits", 0)) or 0
    )
    if throttled:
        status = _worse_output(status, "degraded")
        reasons.append(f"provider throttled {throttled} request(s)")
    return status, reasons


def _daily_curation_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    db = context.db
    pause_condition = db.get("pause_condition")
    if pause_condition:
        status = _worse_output(status, "broken")
        reasons.append(f"scheduled dispatch is paused: {pause_condition}")

    # The registry SQL counts only the rolling cohort the enqueuer revisits.
    for metric, label in (
        ("failed_workflows", "failed workflow"),
        ("partial_workflows", "partial workflow"),
    ):
        count = int(db.get(metric, 0) or 0)
        if count:
            status = _worse_output(status, "broken")
            reasons.append(f"{count} recent {label}(s) require attention")

    for metric, label in (
        ("oldest_queued_age_minutes", "queued curation job"),
        ("oldest_running_age_minutes", "running curation job"),
    ):
        age = db.get(metric)
        if age is None:
            continue
        age_minutes = float(age)
        if age_minutes > 300:
            status = _worse_output(status, "broken")
            reasons.append(f"oldest {label} is {int(age_minutes)}m old")
        elif age_minutes > 180:
            status = _worse_output(status, "degraded")
            reasons.append(f"oldest {label} is {int(age_minutes)}m old")
    return status, reasons


def _trending_curation_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    status, reasons = _daily_curation_contract(status, reasons, context)
    failed = int(context.db.get("failed", 0) or 0)
    if failed:
        status = _worse_output(status, "broken")
        reasons.append(f"{failed} model resolution candidate(s) failed")
    return status, reasons


def _research_topics_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    """Topic feeds go stale when Jev keeps failing; no fallback hides it."""
    db = context.db
    age = db.get("oldest_unjudged_age_minutes")
    if age is not None and float(age) > 360:
        status = _worse_output(status, "broken")
        reasons.append(
            f"a paper has waited {int(float(age))}m for a verdict on a followed topic"
        )
    pending = db.get("oldest_pending_backfill_minutes")
    if pending is not None and float(pending) > 60:
        status = _worse_output(status, "degraded")
        reasons.append(
            f"a new topic has waited {int(float(pending))}m for its backfill"
        )
    failed = int(db.get("failed_backfills", 0) or 0)
    if failed:
        status = _worse_output(status, "degraded")
        reasons.append(f"{failed} followed topic backfill(s) gave up after retries")
    return status, reasons


def _curation_thumbnail_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    db = context.db
    queue_is_empty = not any(
        int(db.get(key, 0) or 0) for key in ("queued", "processing", "stale_processing")
    )
    # The queue is event-driven: an idle queue writes nothing, so write
    # staleness only matters while work is waiting.
    if context.systemd.get("service_result") == "success" and queue_is_empty:
        status = "healthy"
        reasons = ["latest queue poll completed and no thumbnail work is pending"]
    stale = int(db.get("stale_processing", 0) or 0)
    failed = int(db.get("failed", 0) or 0)
    if stale:
        status = _worse_output(status, "broken")
        reasons.append(f"{stale} curation thumbnail request(s) are stuck processing")
    if failed:
        status = _worse_output(status, "degraded")
        reasons.append(f"{failed} curation thumbnail request(s) failed in 24h")
    return status, reasons


def _chat_alert_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work = context.work
    if not work.get("monitor_record_available"):
        return "unknown", reasons + [
            "content-free monitor output record is unavailable"
        ]
    age = _minutes_since(work.get("monitor_completed_at"), now=context.now)
    if age is None or age > 5:
        return "broken", reasons + ["latest operational poll output is stale"]
    pending = int(work.get("undelivered_alert_events", 0) or 0)
    monitor_status = work.get("monitor_status")
    if pending or monitor_status == "degraded":
        return "broken", reasons + [
            f"{pending} operational alert event(s) remain undelivered"
        ]
    if monitor_status == "dormant":
        return "healthy", ["monitor is dormant because production chat is disabled"]
    if monitor_status == "paused":
        reason = work.get("monitor_reason_code")
        return "healthy", [
            f"paid synthetic probe is paused by autonomous control ({reason})"
        ]
    if monitor_status == "healthy":
        return "healthy", [
            "latest content-free operational poll completed successfully"
        ]
    return "unknown", reasons + ["operational monitor output state is unknown"]


def _submission_review_contract(
    _status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work = context.work
    if not work.get("review_record_available"):
        return "unknown", reasons + [
            "content-free submission review output record is unavailable"
        ]
    age = _minutes_since(work.get("review_completed_at"), now=context.now)
    if age is None:
        return "unknown", reasons + ["submission review completion time is unavailable"]
    if age > 135:
        return "broken", reasons + ["latest submission review output is stale"]
    if work.get("review_status") == "failed":
        return "broken", reasons + ["latest submission review pass failed"]
    if work.get("review_status") == "healthy":
        claimed = int(work.get("submissions_claimed", 0) or 0)
        return "healthy", [
            f"latest content-free submission review completed; claimed={claimed}"
        ]
    return "unknown", reasons + ["submission review output state is unknown"]


def _autonomous_cron_contract(
    _status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    work = context.work
    if not work.get("operator_record_available"):
        return "unknown", reasons + ["content-free operator record is unavailable"]
    age = _minutes_since(work.get("operator_completed_at"), now=context.now)
    if age is None:
        return "unknown", reasons + ["operator completion time is unavailable"]
    if age > 390:
        return "broken", reasons + ["latest autonomous CRON pass is stale"]
    if work.get("operator_status") == "healthy":
        return "healthy", ["latest bounded autonomous CRON pass completed"]
    return "broken", reasons + [
        f"autonomous CRON pass reported {work.get('operator_reason_code') or 'failure'}"
    ]


def _suggested_questions_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    db = context.db
    if "visible_missing" not in db:
        return status, reasons
    missing = int(db.get("visible_missing") or 0)
    if not missing:
        # A fully covered home feed writes nothing, so staleness is no-work.
        reasons = [reason for reason in reasons if reason != context.db_reason]
        if status in {"degraded", "broken", "unknown"} and not reasons:
            status = "healthy"
        reasons.append("every home-feed paper has stored suggested questions")
    elif missing > 5:
        status = _worse_output(status, "degraded")
        reasons.append(
            f"{missing} of {db.get('visible_papers')} home-feed papers lack "
            "suggested questions"
        )
    return status, reasons


OutputEvaluator = Callable[
    [str, List[str], OutputEvaluationContext],
    tuple[str, List[str]],
]


def _enrichment_snapshot_contract(status, reasons, context):
    if status in {"broken", "stuck", "running"}:
        return status, reasons
    if not context.work.get("snapshot_valid"):
        return "unknown", ["enrichment snapshot is missing or invalid"]
    age = _minutes_since(context.work.get("snapshot_generated_at"), now=context.now)
    completed_age = _minutes_since(
        context.systemd.get("last_completed_at"), now=context.now
    )
    if age is None or age < 0:
        return "unknown", ["enrichment snapshot timestamp is invalid"]
    if age > 36 * 60:
        return "degraded", ["enrichment snapshot is more than 36 hours old"]
    if (
        context.systemd.get("service_result") != "success"
        or context.systemd.get("exec_main_status") != 0
        or completed_age is None
        or not 0 <= completed_age <= age
    ):
        return "unknown", ["snapshot has no matching successful export completion"]
    return "healthy", ["fresh valid local snapshot and successful export completion"]


def _artificial_analysis_contract(
    status: str,
    reasons: List[str],
    context: OutputEvaluationContext,
) -> tuple[str, List[str]]:
    stale = context.db.get("stale_evaluations")
    missing = context.db.get("missing_fresh_datasets")
    if stale is None or missing is None:
        return _worse_output(status, "unknown"), reasons + [
            "Artificial Analysis cohort freshness evidence is unavailable"
        ]
    if missing:
        status = _worse_output(status, "degraded")
        reasons.append(
            f"{missing} Artificial Analysis datasets lack fresh managed rows"
        )
    if stale:
        status = _worse_output(status, "degraded")
        reasons.append(f"{stale} Artificial Analysis managed evaluations are stale")
    return status, reasons


@dataclass(frozen=True)
class OutputPolicy:
    """Registry-selected output rules and their operator guidance."""

    evaluate: OutputEvaluator
    dependency_diagnostic: str | None = None
    refresh_db_freshness: bool = False
    accept_systemd_completion: bool = False


OUTPUT_POLICIES = {
    "artificial_analysis": OutputPolicy(_artificial_analysis_contract),
    "enrichment_snapshot": OutputPolicy(_enrichment_snapshot_contract),
    "generic": OutputPolicy(lambda status, reasons, _context: (status, reasons)),
    "tabarena": OutputPolicy(_tabarena_contract),
    "conference_deadlines": OutputPolicy(_conference_deadlines_contract),
    "github_stars": OutputPolicy(_github_stars_contract),
    "hot_github_trending": OutputPolicy(_hot_github_trending_contract),
    "repository_trending": OutputPolicy(_trending_contract),
    "paper_trending": OutputPolicy(
        _trending_contract,
        dependency_diagnostic=(
            "Fix repo trending scores before trusting paper trending output"
        ),
    ),
    "hf_paper_import": OutputPolicy(_hf_import_contract),
    "daily_curation": OutputPolicy(_daily_curation_contract),
    "trending_curation": OutputPolicy(_trending_curation_contract),
    "citations": OutputPolicy(_provider_counter_contract),
    "hf_artifacts": OutputPolicy(_provider_counter_contract),
    "paper_markdown": OutputPolicy(_paper_markdown_contract),
    "paper_embeddings": OutputPolicy(_paper_embeddings_contract),
    "organization_sync": OutputPolicy(_organization_contract),
    "organization_trending": OutputPolicy(_organization_contract),
    "backfill": OutputPolicy(_backfill_contract),
    "thumbnail_preload": OutputPolicy(_thumbnail_preload_contract),
    "thumbnail_mirror": OutputPolicy(
        _workflow_output_contract,
        refresh_db_freshness=True,
        accept_systemd_completion=True,
    ),
    "weekly_linker": OutputPolicy(
        _workflow_output_contract,
        accept_systemd_completion=True,
    ),
    "curation_thumbnails": OutputPolicy(_curation_thumbnail_contract),
    "research_topics": OutputPolicy(_research_topics_contract),
    "chat_alert_monitor": OutputPolicy(_chat_alert_contract),
    "suggested_questions": OutputPolicy(_suggested_questions_contract),
    "report_only": OutputPolicy(
        lambda status, reasons, _context: (status, reasons),
        accept_systemd_completion=True,
    ),
    "submission_review": OutputPolicy(_submission_review_contract),
    "autonomous_cron_operator": OutputPolicy(_autonomous_cron_contract),
}


def _workflow_status_from_run(
    workflow_file: str,
    run: dict[str, Any],
    *,
    jobs: list[dict[str, Any]] | None = None,
    view_error: str | None = None,
    scheduled_run: dict[str, Any] | None = None,
    manual_run: dict[str, Any] | None = None,
    active_run: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    relevant_jobs = jobs or []
    failed_jobs = [
        job.get("name")
        for job in relevant_jobs
        if job.get("conclusion") not in {None, "", "success", "skipped"}
    ]
    running_jobs = [
        job.get("name")
        for job in relevant_jobs
        if job.get("status") not in {None, "", "completed"}
    ]
    return {
        "available": True,
        "workflow_file": workflow_file,
        "run_id": run.get("databaseId"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "created_at": run.get("createdAt"),
        "updated_at": run.get("updatedAt"),
        "event": run.get("event"),
        "head_branch": run.get("headBranch"),
        "failed_jobs": [name for name in failed_jobs if name],
        "running_jobs": [name for name in running_jobs if name],
        "job_conclusions": {
            job.get("name"): job.get("conclusion")
            for job in relevant_jobs
            if job.get("name")
        },
        "view_error": view_error,
        "manual_query_error": None,
        "scheduled_run": scheduled_run,
        "manual_run": manual_run,
        "active_run": active_run,
    }


def _normalize_api_run(api_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "databaseId": api_run.get("id"),
        "status": api_run.get("status"),
        "conclusion": api_run.get("conclusion"),
        "createdAt": api_run.get("created_at"),
        "updatedAt": api_run.get("updated_at"),
        "event": api_run.get("event"),
        "headBranch": api_run.get("head_branch"),
    }


def _fetch_workflow_status_for_job(job: CronJobDefinition) -> Dict[str, Any]:
    """Bootstrap one workflow that was absent from the recent-runs batch."""

    workflow_file = job.workflow_file or ""
    payload, error = _gh_json(
        [
            "api",
            (
                f"repos/{GITHUB_REPOSITORY}/actions/workflows/"
                f"{workflow_file}/runs?per_page=10&exclude_pull_requests=true"
            ),
        ],
        timeout=8,
    )
    if error:
        return {
            "available": False,
            "workflow_file": workflow_file,
            "error": _sanitized_adapter_error(error, "GitHub Actions"),
        }
    api_runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    if not api_runs:
        return {
            "available": True,
            "workflow_file": workflow_file,
            "status": "unknown",
            "conclusion": None,
            "error": "no workflow runs found",
        }
    runs = [_normalize_api_run(api_run) for api_run in api_runs]
    scheduled_run = next((run for run in runs if run.get("event") == "schedule"), None)
    manual_run = next(
        (run for run in runs if run.get("event") == "workflow_dispatch"), None
    )
    active_run = next(
        (run for run in runs if run.get("status") not in {None, "", "completed"}),
        None,
    )
    run = scheduled_run or runs[0]
    detail_jobs = None
    detail_error = None
    if run["databaseId"] and len(job.workflow_jobs) > 1:
        detail, detail_error = _gh_json(
            ["run", "view", str(run["databaseId"]), "--json", "jobs"],
            timeout=10,
        )
        if isinstance(detail, dict):
            expected = set(job.workflow_jobs)
            detail_jobs = [
                item for item in detail.get("jobs", []) if item.get("name") in expected
            ]
    return _workflow_status_from_run(
        workflow_file,
        run,
        jobs=detail_jobs,
        view_error=(
            _sanitized_adapter_error(detail_error, "GitHub Actions job")
            if detail_error
            else None
        ),
        scheduled_run=scheduled_run,
        manual_run=manual_run,
        active_run=active_run,
    )


def fetch_workflow_statuses(
    jobs: list[CronJobDefinition],
    *,
    previous_dashboard: Dict[str, Any] | None = None,
) -> dict[str, Dict[str, Any]]:
    """Fetch recent workflow runs once and retain unchanged older statuses."""

    workflow_jobs = [job for job in jobs if job.workflow_file]
    previous = {
        status["workflow_file"]: status
        for row in (previous_dashboard or {}).get("jobs", [])
        if isinstance(row, dict)
        and isinstance((status := row.get("workflow_status")), dict)
        and status.get("workflow_file")
    }
    runs_by_file: dict[str, list[dict[str, Any]]] = {}
    batch_error = None
    expected_files = {job.workflow_file for job in workflow_jobs}
    for page in range(1, WORKFLOW_RUN_BATCH_PAGES + 1):
        payload, error = _gh_json(
            [
                "api",
                (
                    f"repos/{GITHUB_REPOSITORY}/actions/runs"
                    f"?per_page=100&page={page}&exclude_pull_requests=true"
                ),
            ],
            timeout=10,
        )
        if error:
            batch_error = error
            break
        api_runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
        for api_run in api_runs:
            workflow_file = basename(api_run.get("path") or "")
            if workflow_file:
                runs_by_file.setdefault(workflow_file, []).append(
                    _normalize_api_run(api_run)
                )
        if expected_files <= runs_by_file.keys() or len(api_runs) < 100:
            break

    statuses: dict[str, Dict[str, Any]] = {}
    bootstrap: list[CronJobDefinition] = []
    now = _utcnow()
    for job in workflow_jobs:
        workflow_file = job.workflow_file or ""
        runs = runs_by_file.get(workflow_file, [])
        previous_status = previous.get(workflow_file, {})
        previous_scheduled = previous_status.get("scheduled_run") or {}
        previous_schedule_needs_refresh = previous_scheduled.get(
            "status"
        ) != "completed" or previous_scheduled.get("conclusion") not in {
            None,
            "",
            "success",
            "skipped",
        }
        previous_expected, _ = _schedule_slots(job, now)
        previous_started = _parse_log_timestamp(previous_scheduled.get("createdAt"))
        if (
            previous_expected
            and now > previous_expected + timedelta(minutes=job.schedule_grace_minutes)
            and (previous_started is None or previous_started < previous_expected)
        ):
            previous_schedule_needs_refresh = True
        if not runs:
            if workflow_file in previous and previous_schedule_needs_refresh:
                # A rerun updates the original GitHub run in place. If that old
                # failed run has fallen outside the repository-wide recent-run
                # page, refresh its workflow instead of retaining the failure.
                bootstrap.append(job)
            elif workflow_file in previous:
                statuses[job.id] = dict(previous[workflow_file])
            else:
                bootstrap.append(job)
            continue

        if not any(run.get("event") == "schedule" for run in runs) and not (
            previous_status.get("scheduled_run")
        ):
            bootstrap.append(job)
            continue
        if (
            not any(run.get("event") == "schedule" for run in runs)
            and previous_schedule_needs_refresh
        ):
            bootstrap.append(job)
            continue
        scheduled_run = next(
            (run for run in runs if run.get("event") == "schedule"),
            previous_status.get("scheduled_run"),
        )
        manual_run = next(
            (run for run in runs if run.get("event") == "workflow_dispatch"),
            previous_status.get("manual_run"),
        )
        active_run = next(
            (run for run in runs if run.get("status") not in {None, "", "completed"}),
            None,
        )
        run = scheduled_run or runs[0]

        detail_jobs: list[dict[str, Any]] | None = None
        detail_error = None
        if run.get("databaseId") and len(job.workflow_jobs) > 1:
            detail, detail_error = _gh_json(
                [
                    "run",
                    "view",
                    str(run["databaseId"]),
                    "--json",
                    "jobs",
                ],
                timeout=10,
            )
            if isinstance(detail, dict):
                expected = set(job.workflow_jobs)
                detail_jobs = [
                    item
                    for item in detail.get("jobs", [])
                    if item.get("name") in expected
                ]
        statuses[job.id] = _workflow_status_from_run(
            workflow_file,
            run,
            jobs=detail_jobs,
            view_error=(
                _sanitized_adapter_error(detail_error, "GitHub Actions job")
                if detail_error
                else None
            ),
            scheduled_run=scheduled_run,
            manual_run=manual_run,
            active_run=active_run,
        )

    if bootstrap:
        with ThreadPoolExecutor(max_workers=min(8, len(bootstrap))) as executor:
            futures = {
                job.id: executor.submit(
                    _fetch_workflow_status_for_job,
                    job,
                )
                for job in bootstrap
            }
            for job_id, future in futures.items():
                statuses[job_id] = future.result()

    if batch_error:
        logger.warning("cron workflow batch unavailable error=%s", batch_error)
    return statuses


def _minutes_since(
    value: Optional[datetime | str], *, now: Optional[datetime] = None
) -> Optional[float]:
    dt = value if isinstance(value, datetime) else _parse_log_timestamp(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    reference = now or _utcnow()
    return (reference - dt.astimezone(timezone.utc)).total_seconds() / 60


def _db_is_stale(
    db_metrics: Dict[str, Any],
    stale_after_minutes: int,
    *,
    now: Optional[datetime] = None,
) -> tuple[bool, Optional[str]]:
    last_write = db_metrics.get("last_write")
    if last_write is None:
        return True, "no database writes recorded"

    age = _minutes_since(last_write, now=now)
    if age is None:
        return True, "could not parse database write timestamp"

    if age > stale_after_minutes:
        return (
            True,
            f"database writes are {age:.0f}m old (stale after {stale_after_minutes}m)",
        )

    recent_writes = db_metrics.get("recent_writes")
    if recent_writes is not None and recent_writes == 0:
        return True, "no recent database writes in the freshness window"

    return False, None


def _recent_log_success(
    job: CronJobDefinition,
    log_status: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> tuple[bool, Optional[str]]:
    if log_status.get("status") not in {"success", "success_no_work"}:
        return False, None
    age = _minutes_since(log_status.get("last_run"), now=now)
    if age is None:
        return False, None
    if age > job.stale_after_minutes:
        return False, None
    return True, f"latest successful log run is {age:.0f}m old"


def evaluate_job_health(
    job: CronJobDefinition,
    log_status: Dict[str, Any],
    db_metrics: Optional[Dict[str, Any]] = None,
    lock_state: Optional[Dict[str, Any]] = None,
    dependency_status: Optional[str] = None,
    workflow_status: Optional[Dict[str, Any]] = None,
    systemd_status: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    process_running: bool | None = None,
    schedule_enabled: bool | None = None,
    launcher_history: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Combine log, process, lock, and DB signals into a dashboard status."""

    lock_state = lock_state or get_lock_state(
        job.lock_file, job.expected_runtime_minutes
    )
    now = now or _utcnow()
    running = bool(log_status.get("is_running")) or (
        is_process_running(job.process_patterns)
        if process_running is None
        else process_running
    )
    log_result = log_status.get("status", "unknown")
    work_metrics = dict(log_status.get("work_metrics") or {})
    db_metrics = db_metrics or {}
    if job.output_evaluator == "autonomous_cron_operator":
        operator_enabled = db_metrics.get("operator_enabled")
        if isinstance(operator_enabled, bool):
            schedule_enabled = operator_enabled
    output_policy = OUTPUT_POLICIES[job.output_evaluator or "generic"]
    log_no_work = log_result == "success_no_work"
    safe_log_error = (
        _sanitized_job_error(log_status["error"], job.id)
        if log_status.get("error")
        else None
    )

    last_run_iso = to_iso8601(log_status.get("last_run"))
    last_db_write_iso = db_metrics.get("last_write_iso")
    recent_write_count = db_metrics.get("recent_writes")

    reasons: List[str] = []
    diagnostics: List[str] = []

    db_stale = False
    db_reason: Optional[str] = None
    if job.db_freshness_query:
        if db_metrics.get("freshness_error"):
            db_stale = True
            db_reason = (
                f"database freshness query failed: {db_metrics['freshness_error']}"
            )
        else:
            db_stale, db_reason = _db_is_stale(
                db_metrics, job.stale_after_minutes, now=now
            )

    recent_log_success, _ = _recent_log_success(job, log_status, now=now)
    # An inode may persist forever; only a currently held kernel lock is evidence.
    # Give the wrapper a short handoff window before calling a held orphan broken.
    lock_blocks_job = (
        lock_state.get("held") is True
        and not running
        and float(lock_state.get("age_minutes") or 0) > 1
    )

    if lock_blocks_job:
        reasons.append(
            f"lock is held with no matching process ({lock_state.get('age_minutes')}m inode age)"
        )
        diagnostics.append("Inspect the lock owner and wrapper process ancestry")
    elif lock_state.get("held") is True and not running:
        running = True
        reasons.append("lock is held during the wrapper-to-Python handoff window")

    if running:
        # A queued or just-started invocation has not logged yet, so the log's
        # last_run still belongs to the previous run; the newest start wins.
        start_ages = [
            age
            for age in (
                _minutes_since(log_status.get("last_run"), now=now),
                _minutes_since((systemd_status or {}).get("last_started_at"), now=now),
            )
            if age is not None
        ]
        start_age = min(start_ages) if start_ages else None
        if start_age is not None and start_age > job.expected_runtime_minutes:
            status = "stuck"
            reasons.append(
                f"process running for {start_age:.0f}m (expected <= {job.expected_runtime_minutes}m)"
            )
            diagnostics.append("Inspect the process ancestry and bounded runtime logs")
        else:
            status = "running"
            reasons.append("process currently running")
    elif log_result == "failed":
        status = "broken"
        if safe_log_error:
            reasons.append(safe_log_error)
        else:
            reasons.append("latest log run failed")
        diagnostics.append(f"Tail `{get_settings().cron_log_dir}/{job.log_name}_*.log`")
    elif lock_blocks_job:
        status = "broken"
    elif log_no_work and job.healthy_no_work_allowed:
        status = "healthy"
        reasons.append("completed with no work (allowed for this job)")
    else:
        if output_policy.refresh_db_freshness:
            db_stale, db_reason = _db_is_stale(
                db_metrics, job.stale_after_minutes, now=now
            )
            if db_stale and db_reason:
                reasons.append(db_reason or "thumbnail cache looks stale")

        if db_stale and db_reason and db_reason not in reasons:
            reasons.append(db_reason)

        log_success = log_result in {"success", "success_no_work"}

        if log_no_work and not job.healthy_no_work_allowed:
            reasons.append("log reports success but zero work items processed")
            if db_stale:
                status = "broken" if job.critical else "degraded"
                diagnostics.append("Reconcile log completion with database freshness")
            elif log_success:
                status = "degraded"
            else:
                status = "degraded"
        elif db_stale and job.db_freshness_query and job.critical:
            status = "broken"
            diagnostics.append(
                "Database freshness overrides log success — inspect SQL errors"
            )
        elif db_stale and job.db_freshness_query:
            status = "degraded"
        elif log_result == "unknown" and not db_metrics.get("last_write"):
            status = "unknown"
            reasons.append("insufficient log and database evidence")
        elif log_success or (db_metrics.get("last_write") and not db_stale):
            status = "healthy"
        elif log_result == "unknown":
            status = "unknown"
            reasons.append("no recent log completion found")
        else:
            status = "degraded"
            reasons.append(f"log status is {log_result}")

    workflow_status = workflow_status or {}
    evaluator = output_policy.evaluate
    evaluation_context = OutputEvaluationContext(
        work=work_metrics,
        db=db_metrics,
        workflow=workflow_status,
        systemd=systemd_status or {},
        now=now,
        running=running,
        recent_log_success=recent_log_success,
        db_reason=db_reason,
        dependency_status=dependency_status,
    )
    semantic_status, semantic_reasons = evaluator("healthy", [], evaluation_context)
    status, reasons = evaluator(status, reasons, evaluation_context)
    if (
        output_policy.dependency_diagnostic
        and dependency_status
        and dependency_status not in {"healthy", "running"}
    ):
        diagnostics.append(output_policy.dependency_diagnostic)
    if (
        output_policy.accept_systemd_completion
        and status == "unknown"
        and systemd_status
        and systemd_status.get("service_result") == "success"
    ):
        status = "healthy"
        reasons = ["latest systemd invocation completed its job-owned output contract"]
    output_status = status
    output_reason = (
        "; ".join(dict.fromkeys(reasons)) if reasons else "job-owned output is fresh"
    )
    execution_health = _execution_health(
        job,
        running=running,
        log_status=log_status,
        workflow_status=workflow_status,
        systemd_status=systemd_status,
        schedule_enabled=schedule_enabled,
        now=now,
    )
    if job.scheduler != "manual":
        execution_health = _launcher_history_health(
            job, execution_health, launcher_history
        )
    if (
        execution_health.get("applicable") is False
        and execution_health["status"] == "healthy"
    ):
        output_status = "healthy"
        output_reason = "output is not applicable while the schedule is disabled"
        semantic_status = "healthy"
        semantic_reasons = [output_reason]
        reasons = [output_reason]
    output_health: OutputHealthResult = {
        "status": output_status,
        "reason": output_reason,
        "last_verified_at": last_db_write_iso or last_run_iso,
    }
    status = _aggregate_health(execution_health, output_health)
    if execution_health["status"] not in {"healthy", "running"}:
        diagnostics.append(execution_health["reason"])

    if job.critical and status in {"broken", "stuck"} and not diagnostics:
        diagnostics.append("Critical writer — investigate immediately")

    if status in {"broken", "degraded", "stuck"} and not diagnostics:
        if job.db_freshness_query:
            diagnostics.append(
                "Compare latest log completion time with database write time"
            )
        else:
            diagnostics.append(
                f"Tail `{get_settings().cron_log_dir}/{job.log_name}_*.log`"
            )

    status_reason = f"Execution: {execution_health['reason']}; Output: {output_reason}"

    return {
        "job_name": job.id,
        "display_name": job.display_name,
        "category": job.category,
        "dashboard_group": job.dashboard_group,
        "status": status,
        "log_status": log_result,
        "status_reason": status_reason,
        "last_run": last_run_iso,
        "last_db_write": last_db_write_iso,
        "recent_write_count": recent_write_count,
        "duration": log_status.get("duration"),
        "is_running": running,
        "error": safe_log_error,
        "schedule": job.schedule,
        "critical": job.critical,
        "work_metrics": work_metrics,
        "work_summary": log_status.get("work_summary"),
        "db_metrics": {
            key: value
            for key, value in db_metrics.items()
            if key not in {"last_write", "last_write_iso"}
        },
        "workflow_status": workflow_status or None,
        "systemd_status": systemd_status,
        "execution_health": execution_health,
        "output_health": output_health,
        "output_contract_evidence": {
            "semantic": {
                "status": semantic_status,
                "reason": "; ".join(dict.fromkeys(semantic_reasons))
                or "job-owned semantic evaluator passed",
                "evaluator": job.output_evaluator or "generic",
            }
        },
        "lock_stale": bool(lock_state.get("stale")),
        "lock_state": lock_state,
        "diagnostics": diagnostics[0] if diagnostics else None,
        "diagnostic_groups": {
            "scheduler_orchestration": (
                [execution_health["reason"]]
                if execution_health["status"] not in {"healthy", "running"}
                else []
            ),
            "output_freshness_completeness": list(dict.fromkeys(reasons)),
        },
    }


def _dashboard_job_summary(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    scheduled_jobs = [job for job in jobs if job["category"] != "manual"]
    manual_jobs = [job for job in jobs if job["category"] == "manual"]
    counts = {
        state: sum(1 for job in scheduled_jobs if job["status"] == state)
        for state in ("healthy", "degraded", "broken", "running", "stuck", "unknown")
    }
    passing = counts["healthy"] + counts["running"]
    scheduled_total = len(scheduled_jobs)
    return {
        "total_jobs": len(jobs),
        "scheduled_jobs": scheduled_total,
        "manual_jobs": len(manual_jobs),
        **counts,
        "health_score": (passing / scheduled_total * 100) if scheduled_total else 0.0,
    }


def _paper_markdown_work_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return _merge_paper_markdown_monitor_metrics(
        metrics, _paper_markdown_monitor_snapshot()
    )


def _chat_monitor_work_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {**metrics, **fetch_chat_monitor_output()}


def _chat_synthetic_work_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {**metrics, **fetch_chat_synthetic_output()}


def _submission_review_work_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {**metrics, **fetch_submission_review_output()}


def _autonomous_cron_work_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {**metrics, **fetch_autonomous_cron_output()}


WORK_METRICS_PROVIDERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "enrichment_snapshot": lambda metrics: {**metrics, **enrichment_snapshot_metrics()},
    "paper_markdown_monitor": _paper_markdown_work_metrics,
    "chat_monitor": _chat_monitor_work_metrics,
    "chat_synthetic": _chat_synthetic_work_metrics,
    "submission_review": _submission_review_work_metrics,
    "autonomous_cron": _autonomous_cron_work_metrics,
}


def build_cron_dashboard(
    previous_dashboard: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    import sys

    if str(WORKFLOWS_DIR) not in sys.path:
        sys.path.insert(0, str(WORKFLOWS_DIR))
    from scripts.utils.cron_helpers import get_cron_job_status

    collection_started = time.perf_counter()
    collection_now = _utcnow()
    today = collection_now.strftime("%Y%m%d")
    definitions = list(list_cron_jobs())
    jobs: List[Dict[str, Any]] = []
    status_by_id: Dict[str, str] = {}

    process_started = time.perf_counter()
    processes, diagnostic_ancestry = _capture_processes()
    running_by_id = {
        job.id: _patterns_are_running(
            job.process_patterns, processes, diagnostic_ancestry
        )
        for job in definitions
    }
    process_ms = (time.perf_counter() - process_started) * 1000

    def timed_collect(collector):
        started = time.perf_counter()
        return collector(), (time.perf_counter() - started) * 1000

    def collect_database():
        try:
            return fetch_db_freshness_batch(definitions)
        except Exception as exc:
            return {
                job.id: {
                    "freshness_error": _sanitized_adapter_error(
                        exc, "database freshness"
                    )
                }
                for job in definitions
                if job.db_freshness_query
            }

    with ThreadPoolExecutor(max_workers=4) as executor:
        database_future = executor.submit(timed_collect, collect_database)
        workflow_future = executor.submit(
            timed_collect,
            lambda: fetch_workflow_statuses(
                definitions, previous_dashboard=previous_dashboard
            ),
        )
        thumbnail_future = executor.submit(
            timed_collect, fetch_thumbnail_cache_freshness
        )
        launcher_future = executor.submit(fetch_launcher_history, now=collection_now)
        database_by_id, database_ms = database_future.result()
        workflow_by_id, workflow_ms = workflow_future.result()
        thumbnail_metrics, thumbnail_ms = thumbnail_future.result()
        launcher_history = launcher_future.result()
    supplemental_db_metrics = {"thumbnail_cache": thumbnail_metrics}

    def get_recent_log_status(job: CronJobDefinition) -> Dict[str, Any]:
        max_days = max(0, min(14, job.stale_after_minutes // (24 * 60) + 1))
        log_directory = Path(job.log_directory) if job.log_directory else None
        latest_status = get_cron_job_status(job.log_name, today, logs_dir=log_directory)
        if latest_status.get("exists") or max_days == 0:
            return latest_status

        for days_back in range(1, max_days + 1):
            date = (_utcnow() - timedelta(days=days_back)).strftime("%Y%m%d")
            candidate = get_cron_job_status(job.log_name, date, logs_dir=log_directory)
            if candidate.get("exists"):
                return candidate
        return latest_status

    for job in definitions:
        log_status = get_recent_log_status(job)
        if job.work_metrics_provider:
            provider = WORK_METRICS_PROVIDERS[job.work_metrics_provider]
            log_status["work_metrics"] = provider(
                dict(log_status.get("work_metrics") or {})
            )

        db_metrics = database_by_id.get(job.id, {})
        if job.db_metrics_provider:
            db_metrics = supplemental_db_metrics[job.db_metrics_provider]

        lock_state = get_lock_state(job.lock_file, job.expected_runtime_minutes)
        dependency_status = (
            status_by_id.get(job.dependency_job_id) if job.dependency_job_id else None
        )
        workflow_status = workflow_by_id.get(job.id)
        systemd_status = (
            fetch_systemd_status(job, log_status)
            if job.scheduler == "systemd"
            else None
        )

        evaluated = evaluate_job_health(
            job,
            log_status,
            db_metrics=db_metrics,
            lock_state=lock_state,
            dependency_status=dependency_status,
            workflow_status=workflow_status,
            systemd_status=systemd_status,
            schedule_enabled=schedule_enabled(job),
            now=collection_now,
            process_running=running_by_id[job.id],
            launcher_history=launcher_history.get(job.id),
        )
        health_findings = build_job_findings(job, evaluated, collection_now)
        evaluated["health_findings"] = [
            finding.as_dict() for finding in health_findings
        ]
        evaluated["operator_url"] = health_findings[0].operator_url
        evaluated["run_url"] = next(
            (finding.run_url for finding in health_findings if finding.run_url),
            None,
        )
        status_by_id[job.id] = evaluated["status"]
        jobs.append(evaluated)

    manual_jobs = [job for job in jobs if job["category"] == "manual"]
    job_summary = _dashboard_job_summary(jobs)

    critical_issues = [
        f"{job['display_name']}: {job['status_reason']}"
        for job in jobs
        if job["critical"] and job["status"] in {"broken", "stuck", "degraded"}
    ]

    what_to_check_next = next(
        (job["diagnostics"] for job in jobs if job["diagnostics"]),
        "All monitored jobs look healthy",
    )

    registered_ids = {
        job.id
        for job in list_cron_jobs()
        if job.scheduler in {"github_actions", "systemd"}
    }
    discovered_ids = discover_scheduled_duties()
    registered_scheduled = len(registered_ids)
    discovered_scheduled = len(discovered_ids)
    monitored_duties = len(registered_ids & discovered_ids)
    gap_ids = sorted(discovered_ids - registered_ids)

    payload = {
        "timestamp": to_iso8601(_utcnow()),
        "jobs": jobs,
        "manual_operations": manual_jobs,
        "summary": {
            **job_summary,
            "critical_issues": critical_issues,
            "what_to_check_next": what_to_check_next,
            "coverage": {
                "registered_scheduled_duties": registered_scheduled,
                "discovered_scheduled_duties": discovered_scheduled,
                "monitored_duties": monitored_duties,
                "coverage_gaps": len(gap_ids),
                "gap_ids": gap_ids,
            },
        },
    }
    total_ms = (time.perf_counter() - collection_started) * 1000
    logger.info(
        "cron_dashboard_collection jobs=%d total_ms=%.1f workflow_ms=%.1f "
        "database_ms=%.1f process_ms=%.1f thumbnail_ms=%.1f",
        len(jobs),
        total_ms,
        workflow_ms,
        database_ms,
        process_ms,
        thumbnail_ms,
    )
    return payload
