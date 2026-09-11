#!/usr/bin/env python3
"""Root-side one-shot broker for policy-authorized CRON recovery retries."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path


PSQL = "/usr/bin/psql"
RUNUSER = "/usr/sbin/runuser"
PWC_CRON = "/usr/local/sbin/pwc-cron"
DATABASE = "paperswithcode_hf"
STATE_ROOT = Path("/var/lib/paperswithcode/autonomous-retry-broker")
SAFE_JOBS = frozenset(
    {
        "backfill_method_keywords",
        "backfill_method_references",
        "calculate_organization_trending_scores",
        "calculate_paper_trending_scores",
        "calculate_trending_scores",
        "enqueue_hf_daily_paper_curation",
        "enqueue_hf_trending_model_curation",
        "export_enrichment_dashboard",
        "import_hf_daily_papers",
        "mirror_thumbnails_to_disk",
        "paper_markdown_backfill",
        "preload_thumbnails",
        "process_curation_thumbnails",
        "refresh_paper_embeddings",
        "review_submissions",
        "sync_hf_organizations",
        "update_citations",
        "update_github_stars",
        "update_hf_artifacts",
        "update_hot_github_trending",
    }
)


class BridgeError(RuntimeError):
    pass


def parse_request(arguments: list[str]) -> tuple[uuid.UUID, str]:
    if len(arguments) != 2:
        raise BridgeError("autonomous CRON retry requires an exact run and job")
    try:
        run_id = uuid.UUID(arguments[0])
    except ValueError:
        raise BridgeError("autonomous CRON retry requires an exact run ID") from None
    job_name = arguments[1]
    if job_name not in SAFE_JOBS:
        raise BridgeError("autonomous CRON retry job is not allowlisted")
    return run_id, job_name


def authorize(run_id: uuid.UUID, job_name: str) -> None:
    query = f"""
SELECT run.id
  FROM public.autonomous_run AS run
 WHERE run.id = '{run_id}'::uuid
   AND run.operator = 'cron_health'
   AND run.dry_run = false
   AND EXISTS (
       SELECT 1 FROM public.autonomous_operator_state
        WHERE operator = 'global' AND manual_mode = false
   )
   AND EXISTS (
       SELECT 1 FROM public.autonomous_operator_state
        WHERE operator = 'cron_health' AND enabled = true
   )
   AND EXISTS (
       SELECT 1 FROM public.autonomous_action
        WHERE run_id = run.id
          AND operator = 'cron_health'
          AND capability = 'retry_declared_cron'
          AND reason_code = 'retry_authorized'
          AND resource_kind = 'declared_cron'
          AND resource_identifier = '{job_name}'
   )
 LIMIT 1;
"""
    outcome = subprocess.run(
        [
            RUNUSER,
            "-u",
            "postgres",
            "--",
            PSQL,
            "--dbname",
            DATABASE,
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            "--set",
            "ON_ERROR_STOP=1",
            "--command",
            query,
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    if outcome.stdout.strip() != str(run_id):
        raise BridgeError("no live CRON retry authorization matched the request")


def consume(run_id: uuid.UUID, job_name: str) -> Path:
    STATE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE_ROOT.chmod(0o700)
    marker = STATE_ROOT / f"{run_id}-{job_name}"
    try:
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise BridgeError("autonomous CRON retry was already consumed") from None
    os.close(descriptor)
    return marker


def main(arguments: list[str] | None = None) -> int:
    if os.geteuid() != 0:
        raise BridgeError("autonomous CRON retry bridge requires root")
    run_id, job_name = parse_request(
        list(sys.argv[1:] if arguments is None else arguments)
    )
    authorize(run_id, job_name)
    consume(run_id, job_name)
    return subprocess.run(
        [PWC_CRON, job_name],
        check=False,
        env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    ).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BridgeError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
