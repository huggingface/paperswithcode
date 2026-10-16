"""Refresh reviewed Finance Agent v2 evaluations from the Vals AI leaderboard."""

import argparse

from backend.database.connection import db_manager
from backend.services.vals_finance_agent_sync_service import (
    ValsFinanceAgentSyncService,
    fetch_vals_finance_agent,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncValsFinanceAgentJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_vals_finance_agent", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        entries = fetch_vals_finance_agent()
        session = db_manager.session_local()
        try:
            stats = ValsFinanceAgentSyncService(session).sync(
                entries, commit=not self.dry_run
            )
            self.logger.info("vals_finance_agent_sync %s", stats.to_dict())
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
                        "vals_finance_agent_%s models=%s", name, "|".join(values)
                    )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncValsFinanceAgentJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
