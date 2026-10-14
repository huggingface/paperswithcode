"""Link authors to the Hugging Face accounts that claimed their recent papers.

Usage:
    PYTHONPATH=.github/workflows uv run --env-file backend/keys.env \
        python -m scripts.daily.sync_hf_author_profiles --days 3650 --dry-run
"""

import argparse
import json
from datetime import UTC, datetime, timedelta

import httpx

from backend.database.connection import db_manager
from backend.services.author_hf_profile_sync_service import (
    AuthorHfProfileSyncService,
    iter_hf_papers,
)
from scripts.utils.cron_helpers import CronJobBase

DEFAULT_LOOKBACK_DAYS = 30
COMMIT_EVERY_PAPERS = 500


class SyncHFAuthorProfilesJob(CronJobBase):
    def __init__(self, *, days: int, dry_run: bool):
        super().__init__(job_name="sync_hf_author_profiles", log_level="INFO")
        self.days = days
        self.dry_run = dry_run

    def run(self):
        since = datetime.now(UTC) - timedelta(days=self.days)
        session = db_manager.session_local()
        service = AuthorHfProfileSyncService(session)
        try:
            with httpx.Client(
                timeout=httpx.Timeout(30, connect=10), follow_redirects=True
            ) as client:
                for hf_paper in iter_hf_papers(client, since):
                    service.sync_paper(hf_paper)
                    if service.stats.papers_fetched % COMMIT_EVERY_PAPERS == 0:
                        self._finish_batch(session)
                        self.logger.info(
                            "hf_author_profiles_progress %s", service.stats.to_dict()
                        )
            self._finish_batch(session)
        finally:
            session.close()
        stats = service.stats
        self.logger.info("Papers processed: %s", stats.papers_fetched)
        self.logger.info(
            "HF_AUTHOR_PROFILES_SUMMARY %s",
            json.dumps({"days": self.days, "dry_run": self.dry_run, **stats.to_dict()}),
        )

    def _finish_batch(self, session) -> None:
        if self.dry_run:
            session.rollback()
        else:
            session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Scan HF papers published within this many days (default: 30).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    job = SyncHFAuthorProfilesJob(days=args.days, dry_run=args.dry_run)
    return 0 if job.execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
