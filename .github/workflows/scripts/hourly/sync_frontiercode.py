"""Index reviewed model papers and refresh Cognition FrontierCode evaluations."""

import argparse

from backend.database.connection import db_manager
from backend.services.frontiercode_sync_service import (
    FrontierCodeSyncService,
    fetch_frontiercode_leaderboard,
    run_discovery,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncFrontierCodeJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_frontiercode", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        leaderboard = fetch_frontiercode_leaderboard()
        session = db_manager.session_local()
        try:
            discovery = run_discovery(session, persist=not self.dry_run)
            self.logger.info("frontiercode_discovery %s", discovery.to_dict())
            stats = FrontierCodeSyncService(session).sync(
                leaderboard,
                discovery=discovery,
                commit=not self.dry_run,
            )
            self.logger.info("frontiercode_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            # Scheduled jobs never create papers for unreviewed models: those
            # without one become release signals that scan_model_releases
            # resolves to a paper.
            for name, values in (
                ("auto_matched", stats.auto_matched),
                ("unreviewed", stats.unreviewed),
            ):
                if values:
                    self.logger.warning(
                        "frontiercode_%s models=%s", name, "|".join(values)
                    )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncFrontierCodeJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
