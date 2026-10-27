"""Refresh paper-linked evaluations from the living DeepSWE leaderboard."""

import argparse

from backend.database.connection import db_manager
from backend.services.deepswe_sync_service import (
    DeepSweSyncService,
    fetch_deepswe_leaderboard,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncDeepSweJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_deepswe", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        leaderboard = fetch_deepswe_leaderboard()
        session = db_manager.session_local()
        try:
            stats = DeepSweSyncService(session).sync(
                leaderboard, commit=not self.dry_run
            )
            self.logger.info("deepswe_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            # Scheduled jobs never create papers: unmatched models become
            # release signals that scan_model_releases resolves to a paper.
            if stats.auto_matched:
                self.logger.warning(
                    "deepswe_auto_matched names=%s", ",".join(stats.auto_matched)
                )
            if stats.unmatched_models:
                self.logger.warning(
                    "deepswe_unmatched_models names=%s",
                    ",".join(stats.unmatched_models),
                )
            if stats.missing_papers:
                self.logger.warning(
                    "deepswe_missing_papers identities=%s",
                    ",".join(stats.missing_papers),
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncDeepSweJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
