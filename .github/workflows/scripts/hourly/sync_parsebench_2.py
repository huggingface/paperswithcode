"""Index reviewed model papers and refresh ParseBench-2 evaluations from leaderboard-v2.csv."""

import argparse

from backend.database.connection import db_manager
from backend.services.parsebench_sync_service import (
    PARSEBENCH_2,
    ParseBenchSyncService,
    fetch_parsebench_leaderboard,
    run_discovery,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncParseBench2Job(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_parsebench_2", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        entries = fetch_parsebench_leaderboard(board=PARSEBENCH_2)
        session = db_manager.session_local()
        try:
            discovery = run_discovery(
                session, board=PARSEBENCH_2, persist=not self.dry_run
            )
            self.logger.info("parsebench_2_discovery %s", discovery.to_dict())
            stats = ParseBenchSyncService(session, PARSEBENCH_2).sync(
                entries, discovery=discovery, commit=not self.dry_run
            )
            self.logger.info("parsebench_2_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            if stats.unreviewed:
                self.logger.warning(
                    "parsebench_2_unreviewed providers=%s", "|".join(stats.unreviewed)
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncParseBench2Job(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
