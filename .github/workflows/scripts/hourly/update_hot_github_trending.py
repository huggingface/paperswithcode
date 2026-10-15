"""Refresh and propagate trending scores for 0-30-day GitHub repositories.

This bounded orchestration job runs every 15 minutes. It selects and snapshots
the hot queue, scores only repositories touched successfully in this run, then
updates only their linked latest papers while retaining full-corpus
normalization.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from backend.database.connection import db_manager
from scripts.hourly.calculate_paper_trending_scores import (
    calculate_paper_scores,
    get_latest_paper_ids_for_repositories,
)
from scripts.hourly.calculate_trending_scores import calculate_repository_scores
from scripts.hourly.update_github_stars import (
    DEFAULT_RATE_LIMIT_RESERVE,
    bounded_env_float,
    bounded_env_int,
    run_queue,
)
from scripts.utils.cron_helpers import DatabaseCronJob


def resolve_hot_token(*, allow_missing: bool = False) -> tuple[str, bool]:
    """Return the hot credential and whether it shares the fresh token."""
    hot_token = os.getenv("PWC_GITHUB_TOKEN_HOT")
    token = hot_token or os.getenv("PWC_GITHUB_TOKEN")
    if not token and not allow_missing:
        raise RuntimeError(
            "PWC_GITHUB_TOKEN_HOT or fallback PWC_GITHUB_TOKEN is required"
        )
    return token or "", hot_token is None


def require_successful_fetch(fetch: dict) -> None:
    """Fail the job when selected GitHub work produced no usable response."""
    if fetch["selected_groups"] > 0 and fetch["successes"] == 0:
        raise RuntimeError(
            "Hot GitHub refresh failed for every selected repository group "
            f"({fetch['failures']} failures across {fetch['api_calls']} API calls)"
        )


class HotGitHubTrendingJob(DatabaseCronJob):
    def __init__(self, selection_only: bool = False):
        super().__init__(job_name="update_hot_github_trending", log_level="INFO")
        self.selection_only = selection_only

    def run(self):
        started = time.monotonic()
        token, shared_token = resolve_hot_token(allow_missing=self.selection_only)

        threshold_minutes = bounded_env_int(
            "PWC_GITHUB_HOT_THRESHOLD_MINUTES", 15, 10, 60
        )
        max_updates = bounded_env_int("PWC_GITHUB_HOT_MAX_UPDATES", 500, 1, 500)
        delay = bounded_env_float("PWC_GITHUB_HOT_DELAY_SECONDS", 0.25, 0.0, 5.0)
        configured_reserve = bounded_env_int(
            "PWC_GITHUB_RATE_LIMIT_RESERVE",
            DEFAULT_RATE_LIMIT_RESERVE,
            0,
            5_000,
        )
        # A dedicated token has an independent budget. Shared-token operation
        # always protects at least 500 calls for the hourly fresh queue.
        reserve = (
            max(DEFAULT_RATE_LIMIT_RESERVE, configured_reserve) if shared_token else 0
        )

        fetch_started = time.monotonic()
        fetch = run_queue(
            "hot",
            token,
            max_updates,
            12 * 60,
            delay=delay,
            rate_limit_reserve=reserve,
            hot_threshold_minutes=threshold_minutes,
            selection_only=self.selection_only,
        )
        fetch_seconds = time.monotonic() - fetch_started
        if self.selection_only:
            summary = {
                "selection_only": True,
                "shared_token": shared_token,
                "projected_calls_per_hour": fetch["selected_groups"] * 4,
                **fetch,
            }
            self.logger.info("HOT_GITHUB_TRENDING_SUMMARY %s", json.dumps(summary))
            return

        repository_ids = fetch["touched_repository_ids"]
        repository_result = {"updated": 0, "insufficient": 0, "skipped": 0}
        paper_result = {
            "population": 0,
            "selected": 0,
            "written": 0,
            "cleared": 0,
        }
        paper_ids: list[int] = []
        repository_score_seconds = 0.0
        paper_score_seconds = 0.0

        if repository_ids:
            session = db_manager.session_local()
            try:
                score_started = time.monotonic()
                repository_result = calculate_repository_scores(
                    session,
                    repository_ids,
                    hot_mode=True,
                    logger=self.logger,
                )
                repository_score_seconds = time.monotonic() - score_started

                paper_ids = get_latest_paper_ids_for_repositories(
                    session, repository_ids
                )
                paper_started = time.monotonic()
                paper_result = calculate_paper_scores(session, paper_ids=paper_ids)
                paper_score_seconds = time.monotonic() - paper_started
            finally:
                session.close()

        summary = {
            "selection_only": False,
            "shared_token": shared_token,
            "credential": (
                "PWC_GITHUB_TOKEN" if shared_token else "PWC_GITHUB_TOKEN_HOT"
            ),
            "eligible_repository_groups": fetch["eligible_groups"],
            "selected_repository_groups": fetch["selected_groups"],
            "api_calls": fetch["api_calls"],
            "successes": fetch["successes"],
            "failures": fetch["failures"],
            "credential_failures": fetch["credential_failures"],
            "not_found": fetch["not_found"],
            "legal_blocked": fetch["legal_blocked"],
            "retries": fetch["retries"],
            "snapshots_written": fetch["snapshots_stored"],
            "repository_scores_updated": repository_result["updated"],
            "repository_scores_insufficient": repository_result["insufficient"],
            "repository_scores_skipped": repository_result["skipped"],
            "paper_ids_selected": len(paper_ids),
            "paper_scores_updated": paper_result["written"],
            "paper_scores_cleared": paper_result["cleared"],
            "rate_limit_stops": fetch["rate_limit_stops"],
            "rate_limit_limit": fetch["rate_limit_limit"],
            "rate_limit_remaining": fetch["rate_limit_remaining"],
            "rate_limit_reset": fetch["rate_limit_reset"],
            "rate_limit_reserve": reserve,
            "oldest_eligible_hot_repository_age_days": fetch[
                "oldest_eligible_age_days"
            ],
            "fetch_seconds": round(fetch_seconds, 3),
            "repository_score_seconds": round(repository_score_seconds, 3),
            "paper_score_seconds": round(paper_score_seconds, 3),
            "total_seconds": round(time.monotonic() - started, 3),
        }
        self.logger.info("HOT_GITHUB_TRENDING_SUMMARY %s", json.dumps(summary))
        self.logger.info("Repositories processed: %d", fetch["processed_groups"])
        self.logger.info("Trending scores updated: %d", repository_result["updated"])
        require_successful_fetch(fetch)
        self.logger.info("Hot GitHub Trending Update Completed successfully")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected hot repositories without API calls or writes",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    success = HotGitHubTrendingJob(selection_only=args.dry_run).execute()
    sys.exit(0 if success else 1)
