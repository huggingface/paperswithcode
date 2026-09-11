"""Refresh paper-linked evaluations from the living Open TTS Leaderboard."""

import argparse

from backend.database.connection import db_manager
from backend.services.open_tts_sync_service import (
    OpenTtsSyncService,
    fetch_open_tts_leaderboard,
    run_open_tts_discovery,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncOpenTtsJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_open_tts", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        entries = fetch_open_tts_leaderboard()
        session = db_manager.session_local()
        try:
            discovery = run_open_tts_discovery(
                session,
                persist=not self.dry_run,
            )
            self.logger.info("open_tts_discovery %s", discovery.to_dict())
            stats = OpenTtsSyncService(session).sync(
                entries,
                discovery=discovery,
                commit=not self.dry_run,
            )
            self.logger.info("open_tts_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            if stats.missing_papers:
                self.logger.warning(
                    "open_tts_missing_papers identities=%s",
                    ",".join(stats.missing_papers),
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncOpenTtsJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
