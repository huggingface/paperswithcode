"""Prepare one exclusive, signed submission-review batch for the HF launcher.

This process retains database access locally. The remote reviewer receives only
the generated immutable manifest and its scoped callbacks.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import AutonomousRun
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
    RunContext,
)
from backend.services.autonomous_alert_service import send_budget_threshold_alert
from backend.services.autonomous_digest_service import (
    AutonomousBudgetService,
    BudgetLimits,
)
from backend.services.autonomous_submission_service import AutonomousSubmissionService
from backend.services.autonomous_submission_job_service import (
    AutonomousSubmissionJobError,
    AutonomousSubmissionJobService,
)

HEALTH_RECORD = "autonomous-submission-review-health.json"


def write_health_record(path: Path, payload: dict) -> None:
    """Atomically persist bounded operational evidence without submission content."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o644)
    os.replace(temporary, path)


def prepare_review_batch(
    *,
    run_id: uuid.UUID,
    manifest_file: Path,
    limit: int = 25,
    launch_remote: bool = False,
    dry_run: bool = False,
) -> int:
    settings = get_settings()
    if not settings.autonomous_submission_enabled:
        raise RuntimeError("Autonomous submission review is disabled")
    context = RunContext(
        run_id=run_id,
        operator=Operator.SUBMISSIONS,
        dry_run=dry_run,
        manifest_revision="submission-review-v1",
    )
    with db_manager.session_local() as db:
        repository = AutonomousOperationsRepository()
        if db.get(AutonomousRun, run_id) is None:
            repository.append_run(
                db, context=context, status="completed", now=datetime.now(UTC)
            )
            db.commit()
        else:
            repository.assert_run_context(db, context)
        service = AutonomousSubmissionService(
            db,
            signing_secret=settings.autonomous_submission_callback_secret.encode(),
            callback_base_url=settings.autonomous_submission_callback_base_url,
        )
        if dry_run:
            preview = service.preview_submission_queue(limit=limit)
            print(
                "AUTONOMOUS_SUBMISSION_DRY_RUN "
                + json.dumps(preview, sort_keys=True, separators=(",", ":"))
            )
            return len(preview)
        if launch_remote:
            job_service = AutonomousSubmissionJobService(settings)
            for job_id in service.pending_remote_job_ids():
                status = job_service.poll(job_id)
                if not status.terminal:
                    raise AutonomousSubmissionJobError(
                        f"Submission Job {job_id} is still active"
                    )
                pending = service.release_remote_job(job_id)
                if pending:
                    raise AutonomousSubmissionJobError(
                        f"Submission Job {job_id} ended as {status.stage} "
                        f"with {pending} unsigned or missing callbacks"
                    )
        limits = BudgetLimits.from_environ(dict(os.environ))
        budget = AutonomousBudgetService(
            limits=limits,
            on_exhausted=send_budget_threshold_alert,
        ).enforce_before_run(
            db,
            operator=Operator.SUBMISSIONS,
            requested_cost_usd=settings.autonomous_submission_run_budget_usd,
            requested_tokens=limits.per_run_tokens,
        )
        if not budget.allowed:
            raise RuntimeError(f"autonomous submission {budget.reason_code}")
        batch = service.claim_submission_batch(run_id, limit=limit)
        if not batch:
            return 0
        manifest = service.build_submission_manifest(batch)
        service.write_manifest(manifest_file, manifest)
        if launch_remote:
            service.prepare_remote_review(batch, manifest)
            try:
                launched = job_service.launch(manifest)
                service.record_remote_job(batch, job_id=launched.job_id)
            except Exception:
                service.release_failed_remote_review(batch)
                raise
            print(
                "AUTONOMOUS_SUBMISSION_JOB "
                f"job_id={launched.job_id} url={launched.monitoring_url}"
            )
            return len(batch)
        reviewed = service.review_submission_batch(
            batch,
            budget_usd=settings.autonomous_submission_run_budget_usd,
        )
        for item in reviewed:
            service.apply_submission_decision(item.callback_token, item.decision)
        return len(batch)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=uuid.UUID)
    parser.add_argument("--manifest-file", type=Path)
    parser.add_argument("--limit", type=int, choices=range(1, 26), default=25)
    parser.add_argument("--launch-remote", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--health-file", type=Path)
    args = parser.parse_args()
    run_id = args.run_id or uuid.uuid4()
    manifest_file = args.manifest_file or Path(
        f"/var/lib/paperswithcode/autonomous-submissions/{run_id}.json"
    )
    health_file = args.health_file or Path(get_settings().cron_log_dir) / HEALTH_RECORD
    started_at = datetime.now(UTC)
    try:
        claimed = prepare_review_batch(
            run_id=run_id,
            manifest_file=manifest_file,
            limit=args.limit,
            launch_remote=args.launch_remote,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        write_health_record(
            health_file,
            {
                "status": "failed",
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "error_class": type(exc).__name__[:128],
            },
        )
        raise
    write_health_record(
        health_file,
        {
            "status": "healthy",
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "claimed": claimed,
            "dry_run": args.dry_run,
            "remote_launch": args.launch_remote,
        },
    )
    print(f"AUTONOMOUS_SUBMISSION_REVIEW claimed={claimed} run_id={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
