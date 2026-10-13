"""Refresh reviewed Physics-IQ Verified evaluations from the official README."""

import argparse

from backend.database.connection import db_manager
from backend.services.physics_iq_verified_sync_service import (
    PhysicsIqSyncService,
    fetch_physics_iq_leaderboard,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncPhysicsIqVerifiedJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_physics_iq_verified", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        entries = fetch_physics_iq_leaderboard()
        session = db_manager.session_local()
        try:
            stats = PhysicsIqSyncService(session).sync(entries, commit=not self.dry_run)
            self.logger.info("physics_iq_verified_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            # Scheduled jobs never create papers: unreviewed models wait for a
            # reviewer to map them in MODEL_IDENTITIES.
            if stats.unreviewed:
                self.logger.warning(
                    "physics_iq_verified_unreviewed models=%s",
                    "|".join(stats.unreviewed),
                )
            if stats.missing_papers:
                self.logger.warning(
                    "physics_iq_verified_missing_papers models=%s",
                    "|".join(stats.missing_papers),
                )
            if stats.missing_upstream:
                self.logger.warning(
                    "physics_iq_verified_missing_upstream rows=%s",
                    "|".join(stats.missing_upstream),
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncPhysicsIqVerifiedJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
