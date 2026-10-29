"""Shared CRON job for the boards in ``backend.services.carbon_board_syncs``."""

import argparse

from backend.database.connection import db_manager
from backend.services.carbon_board_syncs import BOARD_SYNCS
from backend.services.live_leaderboard_sync import LiveLeaderboardSyncService
from scripts.utils.cron_helpers import CronJobBase


class LiveLeaderboardJob(CronJobBase):
    def __init__(self, job_name: str, *, dry_run: bool = False):
        super().__init__(job_name=job_name, log_level="INFO")
        self.sync = BOARD_SYNCS[job_name]
        self.dry_run = dry_run

    def run(self):
        entries = self.sync.fetch(None)
        session = db_manager.session_local()
        try:
            stats = LiveLeaderboardSyncService(session, self.sync.board).sync(
                entries, commit=not self.dry_run
            )
            self.logger.info("%s %s", self.job_name, stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            # Scheduled jobs never create papers: unreviewed models become
            # release-radar signals, and missing papers wait for a reviewer.
            for name, values in (
                ("unreviewed", stats.unreviewed),
                ("missing_papers", stats.missing_papers),
                ("missing_upstream", stats.missing_upstream),
            ):
                if values:
                    self.logger.warning(
                        "%s_%s models=%s", self.job_name, name, "|".join(values)
                    )
        finally:
            session.close()


def main(job_name: str, description: str) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if LiveLeaderboardJob(job_name, dry_run=args.dry_run).execute() else 1
