"""
FastAPI router for CRON job monitoring endpoints.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.cron_dashboard_snapshot_service import (
    CronDashboardSnapshotError,
    CronDashboardSnapshotService,
)
from backend.services.cron_health import build_cron_dashboard, to_iso8601
from backend.services.cron_registry import get_cron_job
from backend.services.paper_markdown_job_monitor import (
    get_paper_markdown_job_monitor,
)
from backend.utils.auth import require_admin

router = APIRouter()


class CronJobStatus(BaseModel):
    job_name: str
    display_name: str
    category: str
    dashboard_group: str = "operations"
    status: str
    log_status: Optional[str] = None
    status_reason: str
    last_run: Optional[str] = None
    last_db_write: Optional[str] = None
    recent_write_count: Optional[int] = None
    duration: Optional[float] = None
    is_running: bool = False
    error: Optional[str] = None
    next_run: Optional[str] = None
    schedule: Optional[str] = None
    critical: bool = False
    work_metrics: Dict[str, Any] = Field(default_factory=dict)
    work_summary: Optional[str] = None
    db_metrics: Dict[str, Any] = Field(default_factory=dict)
    workflow_status: Optional[Dict[str, Any]] = None
    systemd_status: Optional[Dict[str, Any]] = None
    execution_health: Dict[str, Any]
    output_health: Dict[str, Any]
    lock_state: Dict[str, Any] = Field(default_factory=dict)
    lock_stale: bool = False
    diagnostics: Optional[str] = None
    diagnostic_groups: Dict[str, List[str]] = Field(default_factory=dict)
    health_findings: List[Dict[str, Any]] = Field(default_factory=list)
    operator_url: Optional[str] = None
    run_url: Optional[str] = None


class CronJobsResponse(BaseModel):
    timestamp: str
    jobs: List[CronJobStatus]
    manual_operations: List[CronJobStatus] = Field(default_factory=list)
    summary: Dict[str, Any]
    snapshot_generated_at: str
    snapshot_age_seconds: float
    snapshot_stale: bool
    refreshing: bool


class PaperMarkdownJobsResponse(BaseModel):
    available: bool
    namespace: str
    updated_at: Optional[str] = None
    jobs: List[Dict[str, Any]] = Field(default_factory=list)
    logical_shards: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    budgets: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    selected_profiles: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    blockers: Dict[str, str] = Field(default_factory=dict)
    retry_dispositions: Dict[str, int] = Field(default_factory=dict)
    coverage: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    error: Optional[str] = None


@router.get(
    "/cron/status",
    response_model=CronJobsResponse,
    summary="Get CRON jobs status",
    dependencies=[Depends(require_admin)],
)
def get_cron_status(
    background_tasks: BackgroundTasks,
    days: int = Query(
        1, ge=1, le=7, description="Number of days to look back for status"
    ),
    force_refresh: bool = Query(
        False, description="Synchronously refresh the shared health snapshot"
    ),
):
    """Return the shared registry-backed CRON health snapshot."""
    _ = days  # reserved for future history windows
    service = CronDashboardSnapshotService()
    try:
        payload, schedule_refresh = service.get_status(force_refresh=force_refresh)
    except CronDashboardSnapshotError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if schedule_refresh:
        background_tasks.add_task(service.refresh_in_background)
    return CronJobsResponse(**payload)


@router.get(
    "/cron/paper-markdown-jobs",
    response_model=PaperMarkdownJobsResponse,
    summary="Get paper Markdown Hugging Face Jobs",
    dependencies=[Depends(require_admin)],
)
def get_paper_markdown_jobs():
    """Return recent Chandra shard state and compact worker progress."""
    return PaperMarkdownJobsResponse(**get_paper_markdown_job_monitor())


@router.get(
    "/cron/job/{job_name}",
    response_model=Dict[str, Any],
    summary="Get detailed status for a specific job",
    dependencies=[Depends(require_admin)],
)
def get_job_detail(
    job_name: str,
    days: int = Query(3, ge=1, le=30, description="Number of days of history to fetch"),
):
    """Get detailed status and recent log history for a registry job."""
    import sys
    from pathlib import Path

    job = get_cron_job(job_name)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    workflows_dir = Path(__file__).resolve().parents[2] / ".github" / "workflows"
    if str(workflows_dir) not in sys.path:
        sys.path.insert(0, str(workflows_dir))
    from scripts.utils.cron_helpers import get_cron_job_status

    job_history = []
    for offset in range(days):
        date = (datetime.utcnow() - timedelta(days=offset)).strftime("%Y%m%d")
        status = get_cron_job_status(job.log_name, date)
        if status["exists"]:
            job_history.append(
                {
                    "date": date,
                    "status": status["status"],
                    "last_run": to_iso8601(status.get("last_run")),
                    "duration": status["duration"],
                    "error": status["error"],
                }
            )

    current = build_cron_dashboard()["jobs"]
    current_status = next(
        (item for item in current if item["job_name"] == job_name), None
    )

    if not job_history and current_status is None:
        raise HTTPException(
            status_code=404, detail="Job not found or no logs available"
        )

    successful_runs = [item for item in job_history if item["status"] == "success"]
    failed_runs = [item for item in job_history if item["status"] == "failed"]
    durations = [
        item["duration"] for item in successful_runs if item["duration"] is not None
    ]
    avg_duration = sum(durations) / len(durations) if durations else None

    return {
        "job_name": job_name,
        "display_name": job.display_name,
        "current_status": current_status or (job_history[0] if job_history else None),
        "history": job_history,
        "metrics": {
            "total_runs": len(job_history),
            "successful_runs": len(successful_runs),
            "failed_runs": len(failed_runs),
            "success_rate": (
                (len(successful_runs) / len(job_history) * 100) if job_history else 0
            ),
            "avg_duration": avg_duration,
        },
    }


@router.get(
    "/cron/health",
    summary="Get CRON system health",
    dependencies=[Depends(require_admin)],
)
def get_cron_health():
    """Return overall CRON health based on registry jobs and DB freshness."""
    payload = build_cron_dashboard()
    summary = payload["summary"]
    issues = summary.get("critical_issues") or []
    healthy = summary["broken"] == 0 and summary["stuck"] == 0 and not issues

    return {
        "healthy": healthy,
        "timestamp": payload["timestamp"],
        "issues": issues,
        "what_to_check_next": summary.get("what_to_check_next"),
        "summary": summary,
        "message": (
            "All critical jobs healthy"
            if healthy
            else f"{len(issues)} critical issue(s) detected"
        ),
    }
