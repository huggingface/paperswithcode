#!/usr/bin/env python3
"""Stable, allowlisted launcher for production scheduled jobs."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

CURRENT = Path("/srv/paperswithcode/environments/production/current")
VENV = Path("/srv/paperswithcode/.venv")
LOG_DIR = Path("/var/lib/paperswithcode/production/cron-logs")


@dataclass(frozen=True)
class Job:
    command: tuple[str, ...]
    timeout: str
    mutates_shared_data: bool
    idempotency: str
    health_job: str


def job(
    *command: str,
    timeout: str,
    idempotency: str,
    health_job: str | None = None,
) -> Job:
    return Job(
        command=command,
        timeout=timeout,
        mutates_shared_data=True,
        idempotency=idempotency,
        health_job=health_job or command[-1].rsplit(".", 1)[-1],
    )


COMMANDS: dict[str, Job] = {
    "update_github_stars": job(
        "-m",
        "scripts.hourly.update_github_stars",
        timeout="50m",
        idempotency="upsert current repository star counts",
    ),
    "update_citations": job(
        "-m",
        "scripts.hourly.update_citations",
        timeout="50m",
        idempotency="upsert current citation counts",
    ),
    "extract_urls": job(
        "-m",
        "url_extraction_agent.runner",
        timeout="2h",
        idempotency="persist only selected unresolved paper URLs",
    ),
    "extract_urls_select": job(
        "-m",
        "url_extraction_agent.database",
        "select",
        timeout="30m",
        idempotency="read-only candidate selection",
        health_job="extract_urls",
    ),
    "extract_urls_persist": job(
        "-m",
        "url_extraction_agent.database",
        "persist",
        timeout="30m",
        idempotency="validated URL upserts",
        health_job="extract_urls",
    ),
    "calculate_trending_scores": job(
        "-m",
        "scripts.hourly.calculate_trending_scores",
        timeout="50m",
        idempotency="replace current task trending scores",
    ),
    "calculate_paper_trending_scores": job(
        "-m",
        "scripts.hourly.calculate_paper_trending_scores",
        timeout="50m",
        idempotency="replace current paper trending scores",
    ),
    "update_hf_artifacts": job(
        "-m",
        "scripts.hourly.update_hf_artifacts",
        timeout="50m",
        idempotency="upsert current Hugging Face artifact links",
    ),
    "import_hf_daily_papers": job(
        "-m",
        "scripts.daily.import_hf_daily_papers",
        timeout="2h",
        idempotency="upsert papers by stable source identity",
    ),
    "preload_thumbnails": job(
        "-m",
        "scripts.daily.preload_thumbnails",
        timeout="2h",
        idempotency="skip valid existing thumbnail objects",
    ),
    "mirror_thumbnails_to_disk": job(
        "-m",
        "scripts.daily.mirror_thumbnails_to_disk",
        timeout="2h",
        idempotency="replace local mirror files by object key",
    ),
    "link_methods_by_references": job(
        "-m",
        "scripts.weekly.link_methods_by_references",
        timeout="6h",
        idempotency="insert missing paper-method relationships",
    ),
    "link_papers_by_task_keywords": job(
        "-m",
        "scripts.weekly.link_papers_by_task_keywords",
        timeout="6h",
        idempotency="insert missing paper-task relationships",
    ),
    "refresh_paper_embeddings": job(
        "-m",
        "scripts.hourly.refresh_paper_embeddings",
        timeout="6h",
        idempotency="resume generation and activate only complete embeddings",
    ),
}


def main() -> int:
    manifest = json.loads((CURRENT / "release.json").read_text())
    if len(sys.argv) == 2 and sys.argv[1] == "status":
        print(
            json.dumps(
                {
                    "environment": "production",
                    "release_id": manifest["release_id"],
                    "git_sha": manifest["git_sha"],
                    "uid": os.getuid(),
                    "jobs": {
                        name: asdict(spec) for name, spec in sorted(COMMANDS.items())
                    },
                },
                indent=2,
            )
        )
        return 0
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(
            "usage: pwc-cron status | <registered-job> [permitted arguments]",
            file=sys.stderr,
        )
        return 2
    job = sys.argv[1]
    spec = COMMANDS[job]
    extra = sys.argv[2:]
    if any("\n" in arg or "\x00" in arg for arg in extra):
        print("invalid argument", file=sys.stderr)
        return 2
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "job": job,
        "release_id": manifest["release_id"],
        "git_sha": manifest["git_sha"],
        "target_environment": "production",
        "timeout": spec.timeout,
        "mutates_shared_data": spec.mutates_shared_data,
        "idempotency": spec.idempotency,
        "health_job": spec.health_job,
    }
    with (LOG_DIR / "launcher.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    command = spec.command
    env = os.environ.copy()
    env["PWC_ENVIRONMENT"] = "production"
    env["PWC_RELEASE_ID"] = manifest["release_id"]
    env["PWC_CRON_LOG_DIR"] = str(LOG_DIR)
    env["PYTHONPATH"] = str(CURRENT / ".github" / "workflows")
    if job in {"preload_thumbnails", "mirror_thumbnails_to_disk"}:
        env["PWC_THUMBNAIL_MUTATIONS_ENABLED"] = "true"
    argv = [str(VENV / "bin" / "python"), *command, *extra]
    lock_dir = Path(
        os.environ.get(
            "PWC_CRON_LOCK_DIR", "/var/lib/paperswithcode/production/cron-locks"
        )
    )
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / f"{job}.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"{job} is already running")
            return 0
        return subprocess.run(
            ["timeout", "-k", "60s", spec.timeout, *argv],
            cwd=CURRENT,
            env=env,
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
