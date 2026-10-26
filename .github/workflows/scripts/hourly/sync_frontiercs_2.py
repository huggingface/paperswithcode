"""Refresh reviewed FrontierCS 2 evaluations from frontier-cs.org."""

import argparse

from backend.database.connection import db_manager
from backend.services.frontiercs_2_sync_service import (
    FrontierCS2SyncService,
    fetch_frontiercs_2,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncFrontierCS2Job(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_frontiercs_2", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        leaderboard = fetch_frontiercs_2()
        session = db_manager.session_local()
        try:
            stats = FrontierCS2SyncService(session).sync(
                leaderboard, commit=not self.dry_run
            )
            self.logger.info("frontiercs_2_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            # Scheduled jobs never create papers: unreviewed models wait for a
            # reviewer to map them in MODEL_IDENTITIES.
            for name, values in (
                ("unreviewed", stats.unreviewed),
                ("missing_papers", stats.missing_papers),
                ("missing_upstream", stats.missing_upstream),
            ):
                if values:
                    self.logger.warning(
                        "frontiercs_2_%s models=%s", name, "|".join(values)
                    )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncFrontierCS2Job(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
