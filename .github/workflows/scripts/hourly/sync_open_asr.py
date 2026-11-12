"""Refresh paper-linked evaluations from the living Open ASR Leaderboard."""

import argparse
import asyncio

from backend.database.connection import db_manager
from backend.services.open_asr_language_sync_service import (
    OpenAsrLanguageSyncService,
    fetch_open_asr_language_leaderboards,
)
from backend.services.open_asr_sync_service import (
    OpenAsrPaperDiscoveryService,
    OpenAsrSyncService,
    fetch_open_asr_leaderboard,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncOpenAsrJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_open_asr", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        entries = fetch_open_asr_leaderboard()
        session = db_manager.session_local()
        try:
            sync_service = OpenAsrSyncService(session)
            discovery = asyncio.run(
                OpenAsrPaperDiscoveryService(session).discover(
                    sync_service.models_needing_discovery(entries),
                    persist=not self.dry_run,
                )
            )
            self.logger.info("open_asr_discovery %s", discovery.to_dict())
            stats = sync_service.sync(
                entries,
                discovery=discovery,
                commit=not self.dry_run,
            )
            self.logger.info("open_asr_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            if stats.unmatched_models:
                self.logger.warning(
                    "open_asr_unmatched_models names=%s",
                    ",".join(stats.unmatched_models),
                )
            if stats.missing_papers:
                self.logger.warning(
                    "open_asr_missing_papers identities=%s",
                    ",".join(stats.missing_papers),
                )
            # Fetched only now, so a language-view failure never blocks the
            # English board; language boards read the papers it just resolved.
            language_stats = OpenAsrLanguageSyncService(session).sync(
                fetch_open_asr_language_leaderboards(), commit=not self.dry_run
            )
            for dataset_slug, value in language_stats.items():
                self.logger.info(
                    "open_asr_language_sync dataset=%s stats=%s",
                    dataset_slug,
                    value.to_dict(),
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncOpenAsrJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
