"""Cached monitoring for Chandra paper-Markdown Hugging Face Jobs."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, HfFileSystem
from huggingface_hub.errors import EntryNotFoundError, HfHubHTTPError

from backend.config import Settings, get_settings
from backend.services.paper_markdown_budget_service import (
    PAPER_MARKDOWN_GPU_HOURLY_RATE_USD,
    paper_markdown_budget_snapshot,
)
from backend.services.paper_markdown_job_profile import paper_markdown_job_profile

_RUN_ID = re.compile(r"^(?:backfill|live|live-fresh)-\d{8}T\d{6}-[0-9a-f]{8}$")
_SHARD_ID = re.compile(r"^\d{5}$")
_JOB_STAGES = [
    "SCHEDULING",
    "RUNNING",
    "COMPLETED",
    "ERROR",
    "CANCELED",
]
_CACHE_SECONDS = 20
_HISTORY_DAYS = 7
_MAX_HISTORY_JOBS = 200
_MAX_DISPLAY_JOBS = 24
_PROGRESS_READ_WORKERS = 8
_PROGRESS_READ_DEADLINE_SECONDS = 15.0
_PROGRESS_EXECUTOR = ThreadPoolExecutor(
    max_workers=_PROGRESS_READ_WORKERS,
    thread_name_prefix="paper-markdown-progress",
)
_CACHE_LOCK = threading.Lock()
_CACHE: tuple[float, dict[str, Any]] | None = None


def _coverage_history(now: datetime) -> dict[str, dict[str, Any]]:
    configured_log_dir = os.environ.get("PWC_CRON_LOG_DIR")
    if not configured_log_dir:
        configured_log_dir = getattr(
            get_settings(),
            "cron_log_dir",
            ".github/workflows/scripts/logs",
        )
    path = Path(configured_log_dir) / "paper_markdown_coverage.jsonl"
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 1024 * 1024))
        raw = handle.read()
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines()[1 if size > len(raw) else 0 :]:
        try:
            payload = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("scope") in {
            "full",
            "recent_14_days",
        }:
            rows.append(payload)
    result: dict[str, dict[str, Any]] = {}
    for scope in ("full", "recent_14_days"):
        scoped = [row for row in rows if row.get("scope") == scope]
        if not scoped:
            continue
        current = scoped[-1]
        cutoff = now - timedelta(days=7)
        baseline = None
        for row in scoped:
            try:
                observed = datetime.fromisoformat(
                    str(row.get("observed_at")).replace("Z", "+00:00")
                )
            except ValueError:
                continue
            if observed <= cutoff:
                baseline = row
        current = dict(current)
        for field, delta_name in (
            ("eligible_papers", "eligible_delta_7d"),
            ("canonical_markdown_count", "canonical_delta_7d"),
            ("missing_count", "missing_delta_7d"),
        ):
            current[delta_name] = (
                int(current.get(field) or 0) - int(baseline.get(field) or 0)
                if baseline
                else None
            )
        result[scope] = current
    return result


def _logical_shards(provider_attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse provider retries without discarding their audit history."""

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for attempt in provider_attempts:
        key = (
            str(attempt.get("run_id") or attempt["id"]),
            str(attempt.get("shard_id") or attempt["id"]),
        )
        grouped.setdefault(key, []).append(attempt)

    logical: list[dict[str, Any]] = []
    for (run_id, shard_id), attempts in grouped.items():
        # Jobs arrive newest first. A complete canonical checkpoint is authoritative
        # even when an earlier or late provider attempt reports an error.
        successful = next(
            (item for item in attempts if item["effective_outcome"] == "success"),
            None,
        )
        current = successful or attempts[0]
        mount_failures = [
            item for item in attempts if item.get("failure_cause") == "volume_mount"
        ]
        recovered_mount = bool(mount_failures and successful)
        unresolved_mount = bool(
            mount_failures
            and not successful
            and current.get("failure_cause") == "volume_mount"
            and current.get("effective_outcome") == "infrastructure_failure"
        )
        requires_operator_ack = bool(len(mount_failures) >= 2 and not successful)
        logical.append(
            {
                "run_id": run_id,
                "shard_id": shard_id,
                "mode": current.get("mode"),
                "profile_id": current.get("profile_id"),
                "provider_attempts": len(attempts),
                "provider_job_ids": [item["id"] for item in attempts],
                "latest_provider_job_id": attempts[0]["id"],
                "representative_provider_job_id": current["id"],
                "effective_outcome": current["effective_outcome"],
                "failure_cause": current.get("failure_cause"),
                "recovered_mount_failure": recovered_mount,
                "unresolved_mount_failure": unresolved_mount,
                "requires_operator_ack": requires_operator_ack,
                "created_at": attempts[0].get("created_at"),
            }
        )
    return logical


def _run_lane(run_id: str) -> str:
    """``live``, ``live-fresh`` or ``backfill`` from ``<lane>-<stamp>-<hex>``."""
    return run_id.rsplit("-", 2)[0]


def _retry_dispositions(coverage: dict[str, dict[str, Any]]) -> dict[str, int]:
    latest = coverage.get("full") or coverage.get("recent_14_days") or {}
    return {
        key: max(0, int(latest.get(key) or 0))
        for key in (
            "retryable_due",
            "retryable_deferred",
            "permanent_failures",
            "attempts_exhausted",
        )
    }


def _blocker(reliability_blocked: bool, budget_blocked: bool) -> str:
    if reliability_blocked and budget_blocked:
        return "reliability_and_budget"
    if reliability_blocked:
        return "reliability"
    if budget_blocked:
        return "budget"
    return "none"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stage(job: object) -> str:
    status = getattr(job, "status", None)
    stage = getattr(status, "stage", status)
    return str(getattr(stage, "value", stage) or "UNKNOWN").upper()


def _hardware(job: object) -> str | None:
    flavor = getattr(job, "flavor", None)
    if flavor is None:
        return None
    return str(getattr(flavor, "name", None) or flavor)


def _provider_attempt(labels: dict[str, Any]) -> int:
    try:
        return max(1, int(labels.get("provider_attempt") or labels.get("attempt") or 1))
    except (TypeError, ValueError):
        return 1


def _effective_outcome(
    stage: str, progress: dict[str, Any] | None, *, checkpoint_stale: bool = False
) -> str:
    """Separate useful output state from the provider's terminal label."""
    if progress:
        total = int(progress.get("total_papers") or 0)
        processed = int(progress.get("processed_papers") or 0)
        if progress.get("fatal_error") or progress.get("status") == "failed":
            return "worker_failure"
        if total and processed == total and progress.get("status") == "completed":
            return "success"
        if stage in {"SCHEDULING", "RUNNING"} and not checkpoint_stale:
            return "active"
        if processed < total:
            if stage in {"ERROR", "CANCELED"} or checkpoint_stale:
                return "interrupted"
            return "partial"
    if stage in {"SCHEDULING", "RUNNING"}:
        return "active"
    if stage in {"ERROR", "CANCELED"}:
        return "infrastructure_failure"
    if stage == "COMPLETED":
        return "worker_failure"
    return "unknown"


def _failure_cause(
    outcome: str, stage_message: str | None, progress: dict[str, Any] | None
) -> str | None:
    if outcome not in {"infrastructure_failure", "interrupted", "worker_failure"}:
        return None
    message = (stage_message or "").lower()
    if "mount" in message or "volume" in message:
        return "volume_mount"
    if "143" in message or (progress or {}).get("termination_requested"):
        return "exit_143"
    if "timeout" in message or "timed out" in message:
        return "timeout"
    if outcome == "worker_failure":
        return "worker_failure"
    if outcome == "interrupted":
        return "interrupted"
    return "startup_or_infrastructure"


def _read_progress(
    filesystem: HfFileSystem,
    settings: Settings,
    run_id: str | None,
    shard_id: str | None,
) -> dict[str, Any] | None:
    if not run_id or not shard_id:
        return None
    if not _RUN_ID.fullmatch(run_id) or not _SHARD_ID.fullmatch(shard_id):
        return None

    path = (
        f"hf://buckets/{settings.paper_markdown_hf_bucket_id}/"
        f"_jobs/progress/{run_id}/{shard_id}.json"
    )
    try:
        with filesystem.open(path, "rb", block_size=0) as handle:
            raw = handle.read(64 * 1024 + 1)
    except (EntryNotFoundError, FileNotFoundError, HfHubHTTPError):
        return None
    if len(raw) > 64 * 1024:
        return None
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    integer_fields = (
        "total_papers",
        "processed_papers",
        "succeeded_papers",
        "failed_papers",
        "already_existed_papers",
        "extracted_images",
        "omitted_images",
    )
    progress: dict[str, Any] = {
        key: max(0, int(payload.get(key) or 0)) for key in integer_fields
    }
    progress.update(
        {
            "status": str(payload.get("status") or "unknown")[:32],
            "updated_at": str(payload.get("updated_at") or "")[:64] or None,
            "started_at": str(payload.get("started_at") or "")[:64] or None,
            "fatal_error": str(payload.get("fatal_error") or "")[:1000] or None,
            "termination_requested": bool(payload.get("termination_requested")),
            "cleanup_state": str(payload.get("cleanup_state") or "")[:32] or None,
            "paper_duration_p50_seconds": payload.get("paper_duration_p50_seconds"),
            "paper_duration_p95_seconds": payload.get("paper_duration_p95_seconds"),
            "error_samples": [
                {
                    "arxiv_id": str(item.get("arxiv_id") or "")[:32],
                    "error": str(item.get("error") or "")[:500],
                }
                for item in (payload.get("error_samples") or [])[:5]
                if isinstance(item, dict)
            ],
        }
    )
    return progress


def _read_progress_batch(
    filesystem: HfFileSystem,
    settings: Settings,
    jobs: list[Any],
) -> tuple[list[dict[str, Any] | None], int]:
    futures = []
    for job in jobs:
        labels = getattr(job, "labels", None) or {}
        futures.append(
            _PROGRESS_EXECUTOR.submit(
                _read_progress,
                filesystem,
                settings,
                labels.get("run_id"),
                labels.get("shard_id"),
            )
        )
    completed, incomplete = wait(
        futures,
        timeout=_PROGRESS_READ_DEADLINE_SECONDS,
    )
    for future in incomplete:
        future.cancel()
    return [
        future.result() if future in completed else None for future in futures
    ], len(incomplete)


def _fetch(settings: Settings) -> dict[str, Any]:
    if not settings.hf_token:
        return {
            "available": False,
            "namespace": settings.paper_markdown_hf_namespace,
            "updated_at": _iso(datetime.now(timezone.utc)),
            "jobs": [],
            "summary": {},
            "error": "Hugging Face monitoring token is not configured",
        }

    api = HfApi(token=settings.hf_token)
    filesystem = HfFileSystem(token=settings.hf_token)
    remote_jobs = list(
        api.list_jobs(
            status=_JOB_STAGES,
            labels={"app": "pwc-paper-markdown"},
            timeout=10,
            namespace=settings.paper_markdown_hf_namespace,
            token=settings.hf_token,
        )
    )
    remote_jobs.sort(
        key=lambda job: (
            getattr(job, "created_at", None)
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )

    snapshot_now = datetime.now(timezone.utc)
    history_cutoff = snapshot_now - timedelta(days=_HISTORY_DAYS)
    history_remote_jobs = [
        job
        for job in remote_jobs
        if (getattr(job, "labels", None) or {}).get("job_type") != "volume_probe"
        and (
            (created_at := getattr(job, "created_at", None)) is None
            or created_at.astimezone(timezone.utc) >= history_cutoff
            or _stage(job) in {"SCHEDULING", "RUNNING"}
        )
    ][:_MAX_HISTORY_JOBS]
    progress_snapshots, progress_evidence_timeouts = _read_progress_batch(
        filesystem,
        settings,
        history_remote_jobs,
    )
    history_jobs: list[dict[str, Any]] = []
    for job, progress in zip(history_remote_jobs, progress_snapshots, strict=True):
        labels = getattr(job, "labels", None) or {}
        run_id = labels.get("run_id")
        shard_id = labels.get("shard_id")
        status = getattr(job, "status", None)
        stage_message = str(getattr(status, "message", "") or "")[:1000] or None
        durations = getattr(job, "durations", None)
        stage = _stage(job)
        # Replacement attempts share the logical progress path. A provider-confirmed
        # mount failure never reached that path, so a replacement's checkpoint must
        # not retroactively turn the failed provider attempt into a success.
        if (
            stage in {"ERROR", "CANCELED"}
            and _failure_cause("infrastructure_failure", stage_message, None)
            == "volume_mount"
        ):
            progress = None
        checkpoint_stale = False
        if progress and progress.get("updated_at"):
            try:
                checkpoint_at = datetime.fromisoformat(
                    str(progress["updated_at"]).replace("Z", "+00:00")
                )
                checkpoint_stale = (
                    datetime.now(timezone.utc) - checkpoint_at.astimezone(timezone.utc)
                ).total_seconds() > 30 * 60
            except ValueError:
                checkpoint_stale = True
        effective_outcome = _effective_outcome(
            stage, progress, checkpoint_stale=checkpoint_stale
        )
        history_jobs.append(
            {
                "id": str(getattr(job, "id", "")),
                "url": str(getattr(job, "url", "")),
                "stage": stage,
                "stage_message": stage_message,
                "mode": labels.get("mode"),
                "run_id": run_id,
                "shard_id": shard_id,
                "provider_attempt": _provider_attempt(labels),
                "profile_id": labels.get("profile_id") or labels.get("profile"),
                "hardware": _hardware(job),
                "created_at": _iso(getattr(job, "created_at", None)),
                "started_at": _iso(getattr(job, "started_at", None)),
                "finished_at": _iso(getattr(job, "finished_at", None)),
                "duration_seconds": getattr(durations, "total_secs", None),
                "progress": progress,
                "effective_outcome": effective_outcome,
                "failure_cause": _failure_cause(
                    effective_outcome, stage_message, progress
                ),
            }
        )

    jobs = history_jobs[:_MAX_DISPLAY_JOBS]
    logical_shards = _logical_shards(history_jobs)
    stages: dict[str, int] = {}
    for job in history_jobs:
        stages[job["stage"]] = stages.get(job["stage"], 0) + 1
    history_by_id = {job["id"]: job for job in history_jobs}
    logical_jobs = [
        history_by_id[shard["representative_provider_job_id"]]
        for shard in logical_shards
    ]
    progress_rows = [job["progress"] for job in logical_jobs if job["progress"]]
    outcomes: dict[str, int] = {}
    failure_causes: dict[str, int] = {}
    for shard in logical_shards:
        outcome = shard["effective_outcome"]
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        if shard.get("failure_cause"):
            cause = shard["failure_cause"]
            failure_causes[cause] = failure_causes.get(cause, 0) + 1
    # Keyed by lane (the run-id prefix), so a 5-minute live-fresh run never
    # hides the latest hourly live run.
    latest_run_ids: dict[str, str] = {}
    for shard in logical_shards:
        mode = shard.get("mode")
        run_id = shard.get("run_id")
        if mode in {"live", "backfill"} and run_id:
            latest_run_ids.setdefault(_run_lane(str(run_id)), str(run_id))
    latest = set(latest_run_ids.values())
    latest_run_shards = [
        shard for shard in logical_shards if shard.get("run_id") in latest
    ]
    latest_run_jobs = [job for job in jobs if job.get("run_id") in latest]
    active_checkpoint_ages = []
    for job in latest_run_jobs:
        if job["stage"] not in {
            "PENDING",
            "STARTING",
            "QUEUED",
            "SCHEDULING",
            "RUNNING",
        } or not job.get("progress"):
            continue
        updated_at = job["progress"].get("updated_at")
        try:
            parsed = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        active_checkpoint_ages.append(
            max(
                0,
                int(
                    (snapshot_now - parsed.astimezone(timezone.utc)).total_seconds()
                    / 60
                ),
            )
        )
    summary = {
        "visible_jobs": len(jobs),
        "history_jobs_7d": len(history_jobs),
        "provider_attempts": len(history_jobs),
        "logical_shards": len(logical_shards),
        "active_jobs": sum(
            count
            for stage, count in stages.items()
            if stage in {"PENDING", "STARTING", "QUEUED", "SCHEDULING", "RUNNING"}
        ),
        "completed_jobs": stages.get("COMPLETED", 0),
        "failed_jobs": stages.get("ERROR", 0) + stages.get("CANCELED", 0),
        "processed_papers": sum(row["processed_papers"] for row in progress_rows),
        "succeeded_papers": sum(row["succeeded_papers"] for row in progress_rows),
        "failed_papers": sum(row["failed_papers"] for row in progress_rows),
        "extracted_images": sum(row["extracted_images"] for row in progress_rows),
        "omitted_images": sum(row["omitted_images"] for row in progress_rows),
        "progress_evidence_timeouts": progress_evidence_timeouts,
        "latest_run_failed_jobs": sum(
            1
            for shard in latest_run_shards
            if shard["effective_outcome"]
            in {"infrastructure_failure", "worker_failure"}
        ),
        "latest_run_interrupted_jobs": sum(
            1
            for shard in latest_run_shards
            if shard["effective_outcome"] == "interrupted"
        ),
        "unresolved_mount_failures": sum(
            bool(shard["unresolved_mount_failure"]) for shard in latest_run_shards
        ),
        "recovered_mount_failures": sum(
            bool(shard["recovered_mount_failure"]) for shard in logical_shards
        ),
        "mount_failures_requiring_operator_ack": sum(
            bool(shard["requires_operator_ack"]) for shard in logical_shards
        ),
        "oldest_active_checkpoint_age_minutes": (
            max(active_checkpoint_ages) if active_checkpoint_ages else 0
        ),
    }
    summary.update({f"effective_{key}_jobs": value for key, value in outcomes.items()})
    summary.update(
        {f"cause_{key}_jobs": value for key, value in failure_causes.items()}
    )
    terminal_outcomes = sum(
        outcomes.get(outcome, 0)
        for outcome in (
            "success",
            "partial",
            "interrupted",
            "infrastructure_failure",
            "worker_failure",
        )
    )
    summary["effective_success_rate_7d"] = (
        round(outcomes.get("success", 0) / terminal_outcomes, 4)
        if terminal_outcomes
        else 0
    )
    summary["paper_failure_rate_7d"] = (
        round(summary["failed_papers"] / summary["processed_papers"], 4)
        if summary["processed_papers"]
        else 0
    )
    terminal_jobs = max(
        1,
        sum(
            1
            for job in logical_jobs
            if job["stage"] in {"COMPLETED", "ERROR", "CANCELED"}
        ),
    )
    for failure_class in ("infrastructure_failure", "interrupted", "worker_failure"):
        summary[f"platform_{failure_class}_rate"] = round(
            outcomes.get(failure_class, 0) / terminal_jobs, 4
        )
    efficiency_jobs = [
        job
        for job in history_jobs
        if job["stage"] in {"COMPLETED", "ERROR", "CANCELED"}
        and job["effective_outcome"] in {"success", "partial", "interrupted"}
    ]
    efficiency_progress = [
        job["progress"]
        for job in logical_jobs
        if job.get("progress")
        and job["effective_outcome"] in {"success", "partial", "interrupted"}
    ]
    total_gpu_seconds = sum(
        float(job.get("duration_seconds") or 0) for job in efficiency_jobs
    )
    successful_papers = sum(
        int(row.get("succeeded_papers") or 0) for row in efficiency_progress
    )
    summary["estimated_dollars_per_successful_paper"] = (
        round(
            total_gpu_seconds
            / 3600
            * PAPER_MARKDOWN_GPU_HOURLY_RATE_USD
            / successful_papers,
            4,
        )
        if successful_papers
        else 0
    )
    summary["papers_per_gpu_hour"] = (
        round(successful_papers / (total_gpu_seconds / 3600), 2)
        if total_gpu_seconds
        else 0
    )
    p50_values = sorted(
        float(row["paper_duration_p50_seconds"])
        for row in efficiency_progress
        if row.get("paper_duration_p50_seconds") is not None
    )
    p95_values = sorted(
        float(row["paper_duration_p95_seconds"])
        for row in efficiency_progress
        if row.get("paper_duration_p95_seconds") is not None
    )
    summary["paper_duration_p50_seconds"] = (
        p50_values[len(p50_values) // 2] if p50_values else 0
    )
    summary["paper_duration_p95_seconds"] = p95_values[-1] if p95_values else 0
    coverage = _coverage_history(snapshot_now)
    retry_dispositions = _retry_dispositions(coverage)
    summary.update(retry_dispositions)
    full_missing = int((coverage.get("full") or {}).get("missing_count") or 0)
    summary["estimated_cost_to_clear_backlog_usd"] = round(
        full_missing * summary["estimated_dollars_per_successful_paper"], 2
    )

    active_live = sum(
        1
        for job in remote_jobs
        if (getattr(job, "labels", None) or {}).get("mode") == "live"
        and _stage(job) in {"SCHEDULING", "RUNNING", "STARTING", "PENDING", "QUEUED"}
    )
    active_backfill = sum(
        1
        for job in remote_jobs
        if (getattr(job, "labels", None) or {}).get("mode") == "backfill"
        and _stage(job) in {"SCHEDULING", "RUNNING", "STARTING", "PENDING", "QUEUED"}
    )
    budgets = {
        "live": paper_markdown_budget_snapshot(
            remote_jobs,
            mode="live",
            ceiling_usd=settings.paper_markdown_incremental_monthly_budget_usd,
            planned_jobs=max(0, 1 - active_live),
            now=snapshot_now,
            cost_policy=getattr(settings, "paper_markdown_cost_policy", "metered"),
        ),
        "backfill": paper_markdown_budget_snapshot(
            remote_jobs,
            mode="backfill",
            ceiling_usd=settings.paper_markdown_backfill_budget_usd,
            planned_jobs=max(
                0,
                getattr(settings, "paper_markdown_backfill_concurrency", 4)
                - active_backfill,
            ),
            now=snapshot_now,
            cost_policy=getattr(settings, "paper_markdown_cost_policy", "metered"),
        ),
    }
    blockers = {
        mode: _blocker(
            any(
                shard.get("mode") == mode
                and shard["effective_outcome"]
                in {"infrastructure_failure", "worker_failure"}
                for shard in latest_run_shards
            ),
            bool(budget["desired_jobs"] and not budget["affordable_jobs"]),
        )
        for mode, budget in budgets.items()
    }
    summary["retryable_papers_blocked_by_budget"] = (
        retry_dispositions["retryable_due"]
        if any(
            value in {"budget", "reliability_and_budget"} for value in blockers.values()
        )
        else 0
    )
    paid_dispatch_enabled = bool(
        getattr(settings, "paper_markdown_paid_dispatch_enabled", False)
    )
    summary["paid_dispatch_enabled"] = int(paid_dispatch_enabled)
    summary["paid_execution_authorization_required"] = int(
        getattr(settings, "paper_markdown_cost_policy", "metered") == "metered"
        and not paid_dispatch_enabled
        and any(
            budget["desired_jobs"] and budget["affordable_jobs"]
            for budget in budgets.values()
        )
    )
    return {
        "available": progress_evidence_timeouts == 0,
        "namespace": settings.paper_markdown_hf_namespace,
        "updated_at": _iso(datetime.now(timezone.utc)),
        "jobs": jobs,
        "logical_shards": logical_shards,
        "summary": summary,
        "coverage": coverage,
        "budgets": budgets,
        "selected_profiles": {
            mode: paper_markdown_job_profile(mode).as_dict()
            for mode in ("live", "backfill")
        },
        "blockers": blockers,
        "retry_dispositions": retry_dispositions,
        "error": (
            f"progress evidence timed out for {progress_evidence_timeouts} "
            "recent job(s)"
            if progress_evidence_timeouts
            else None
        ),
    }


def get_paper_markdown_job_monitor() -> dict[str, Any]:
    """Return a short-lived cached snapshot for the admin dashboard."""
    global _CACHE

    now = time.monotonic()
    with _CACHE_LOCK:
        if _CACHE and now - _CACHE[0] < _CACHE_SECONDS:
            return dict(_CACHE[1])
        settings = get_settings()
        try:
            result = _fetch(settings)
        except (HfHubHTTPError, OSError, ValueError) as error:
            result = {
                "available": False,
                "namespace": settings.paper_markdown_hf_namespace,
                "updated_at": _iso(datetime.now(timezone.utc)),
                "jobs": [],
                "summary": {},
                "error": str(error)[:1000],
            }
        _CACHE = (now, result)
        return dict(result)


def get_cached_paper_markdown_job_monitor() -> dict[str, Any]:
    """Return cached monitor evidence without adding remote I/O to health scans."""

    now = time.monotonic()
    with _CACHE_LOCK:
        if _CACHE and now - _CACHE[0] < _CACHE_SECONDS:
            return dict(_CACHE[1])
    return {"available": False, "jobs": [], "summary": {}, "error": None}


def clear_paper_markdown_job_monitor_cache() -> None:
    """Clear the process cache for tests and operator-triggered refreshes."""
    global _CACHE
    with _CACHE_LOCK:
        _CACHE = None
