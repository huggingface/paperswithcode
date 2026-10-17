"""Refresh reviewed Chartography (no tools) evaluations from Surge AI."""

import argparse

from backend.database.connection import db_manager
from backend.services.surge_chartography_sync_service import (
    SurgeChartographySyncService,
    fetch_surge_chartography,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncSurgeChartographyJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_surge_chartography", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        entries = fetch_surge_chartography()
        session = db_manager.session_local()
        try:
            stats = SurgeChartographySyncService(session).sync(
                entries, commit=not self.dry_run
            )
            self.logger.info("surge_chartography_sync %s", stats.to_dict())
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
                        "surge_chartography_%s models=%s", name, "|".join(values)
                    )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncSurgeChartographyJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
