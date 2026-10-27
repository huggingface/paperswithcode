"""Link recent arXiv papers to organizations from OpenAlex affiliations."""

import argparse
from datetime import date, timedelta

import httpx

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.openalex_organization_linking_service import (
    link_openalex_organizations,
)
from scripts.utils.cron_helpers import DatabaseCronJob

# OpenAlex adds a new arXiv paper's affiliations days to weeks after it
# appears, so every run revisits the whole window; existing links are skipped.
WINDOW_DAYS = 60


class LinkOpenAlexOrganizationsJob(DatabaseCronJob):
    def __init__(self, *, days: int, dry_run: bool = False):
        super().__init__(job_name="link_openalex_organizations", log_level="INFO")
        self.days = days
        self.dry_run = dry_run

    def run(self):
        session = db_manager.session_local()
        try:
            with httpx.Client(timeout=60) as client:
                stats = link_openalex_organizations(
                    session,
                    client,
                    since=date.today() - timedelta(days=self.days),
                    api_key=get_settings().openalex_api_key,
                    apply=not self.dry_run,
                )
        finally:
            session.close()
        self.logger.info(
            "openalex_organizations papers=%s matched_works=%s links=%s",
            stats.papers,
            stats.matched_works,
            sum(stats.linked.values()),
        )
        self.logger.info("Papers processed: %s", stats.papers)
        if stats.stopped_status:
            raise RuntimeError(
                f"OpenAlex returned {stats.stopped_status} after paper {stats.last_id}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=WINDOW_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    job = LinkOpenAlexOrganizationsJob(days=args.days, dry_run=args.dry_run)
    return 0 if job.execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
