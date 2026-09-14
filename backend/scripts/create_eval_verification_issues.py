"""Reconcile eval outreach hourly; preview by default, publish with --execute."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import logging
import os
from pathlib import Path
import subprocess

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.github_eval_outreach_catalog import candidates
from backend.services.github_eval_outreach_service import OutreachRunner
from backend.services.github_eval_outreach_state import OutreachState
from backend.services.github_issue_body_service import generate_github_issue_draft
from backend.services.github_issue_publish_service import (
    GithubApiError,
    gh_json,
    github_environment,
)


@contextmanager
def read_catalog():
    session = get_database_session()
    db = next(session)
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text("SET LOCAL statement_timeout = '60s'"))
        yield db
    finally:
        db.rollback()
        session.close()


def load_catalog():
    with read_catalog() as db:
        return candidates(db, datetime.now(timezone.utc) - timedelta(hours=1))


def load_draft(paper_id):
    with read_catalog() as db:
        return generate_github_issue_draft(db, str(paper_id))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Read the durable last-run summary without network access",
    )
    parser.add_argument("--limit", type=int, choices=range(1, 101), default=50)
    parser.add_argument("--max-create", type=int, choices=range(1, 11), default=10)
    parser.add_argument("--token-env", default="PWC_GITHUB_TOKEN")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(
            os.environ.get(
                "PWC_CRON_LOCK_DIR", "/var/lib/paperswithcode/production/cron-locks"
            )
        )
        / "github-eval-outreach.sqlite3",
    )
    args = parser.parse_args()
    path = args.state_file.resolve()
    if args.status:
        state = OutreachState(path, dry_run=True)
        try:
            print(
                json.dumps(
                    {
                        "last_run": state.get("last_run"),
                        "pending_repositories": [key for key, _ in state.pending()],
                    },
                    sort_keys=True,
                )
            )
        finally:
            state.close()
        return 0
    env = github_environment(args.token_env)
    calls = 0

    def api(arguments):
        nonlocal calls
        calls += 1
        if calls > 600:
            raise ValueError(
                "GitHub request budget exhausted; resume next scheduled run"
            )
        if not args.execute and "POST" in arguments:
            raise ValueError("Preview cannot publish issues")
        try:
            return gh_json(arguments, env)
        except GithubApiError as error:
            if error.is_rate_limited:
                state.put(
                    "rate_limit",
                    {
                        "not_before": max(
                            datetime.now(timezone.utc).timestamp() + 3600,
                            error.retry_at,
                        )
                    },
                )
            raise

    handlers = [logging.StreamHandler()]
    lock = None
    if args.execute:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_suffix(".lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            print("Evaluation outreach already running")
            return 0
        log_dir = Path(
            os.environ.get(
                "PWC_CRON_LOG_DIR", "/var/lib/paperswithcode/production/cron-logs"
            )
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(log_dir / "create_eval_verification_issues.log")
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
    state = OutreachState(path, dry_run=not args.execute)
    runner = OutreachRunner(
        state,
        api,
        load_catalog,
        load_draft,
        dry_run=not args.execute,
        limit=args.limit,
        max_create=args.max_create,
    )
    try:
        logging.info("Starting evaluation outreach")
        try:
            result = runner.run()
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            result = {
                "at": datetime.now(timezone.utc).isoformat(),
                "error": str(error),
                "counts": dict(runner.counts),
                "events": runner.events,
            }
            state.put("last_run", result)
            logging.error("Evaluation outreach failed: %s", error)
            print(json.dumps(result, sort_keys=True))
            return 1
        print(json.dumps(result, sort_keys=True))
        if result["counts"].get("needs_review") or result["counts"].get("rate_limited"):
            logging.error(
                "Evaluation outreach is blocked by uncertain posts or a rate-limit cooldown"
            )
            return 1
        logging.info(
            "Evaluation outreach completed: %s",
            json.dumps(result["counts"], sort_keys=True),
        )
        return 0
    finally:
        state.close()
        if lock:
            lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
