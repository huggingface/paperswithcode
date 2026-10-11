"""Index reviewed model papers and refresh ExtractBench evaluations from leaderboard.csv."""

import argparse

from backend.database.connection import db_manager
from backend.services.extractbench_sync_service import (
    ExtractBenchSyncService,
    fetch_extractbench_leaderboard,
    run_discovery,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncExtractBenchJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_extractbench", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        entries = fetch_extractbench_leaderboard()
        session = db_manager.session_local()
        try:
            discovery = run_discovery(session, persist=not self.dry_run)
            self.logger.info("extractbench_discovery %s", discovery.to_dict())
            stats = ExtractBenchSyncService(session).sync(
                entries, discovery=discovery, commit=not self.dry_run
            )
            self.logger.info("extractbench_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            if stats.unreviewed:
                self.logger.warning(
                    "extractbench_unreviewed providers=%s", "|".join(stats.unreviewed)
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncExtractBenchJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
