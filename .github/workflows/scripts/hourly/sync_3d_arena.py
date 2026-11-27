"""Refresh paper-linked evaluation rows from the living 3D Arena leaderboard."""

import argparse

import httpx

from backend.database.connection import db_manager
from backend.services.three_d_arena_sync_service import (
    ThreeDArenaSyncService,
    fetch_arena_leaderboard,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncThreeDArenaJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_3d_arena", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        try:
            entries = fetch_arena_leaderboard()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise
            self.logger.warning(
                "3d_arena_rate_limited skipping run; existing rows are kept"
            )
            return
        session = db_manager.session_local()
        try:
            stats = ThreeDArenaSyncService(session).sync(
                entries, commit=not self.dry_run
            )
            self.logger.info("3d_arena_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            if stats.unmatched_models:
                self.logger.warning(
                    "3d_arena_unmatched_models names=%s",
                    ",".join(stats.unmatched_models),
                )
            if stats.missing_papers:
                self.logger.warning(
                    "3d_arena_missing_papers identities=%s",
                    ",".join(stats.missing_papers),
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncThreeDArenaJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
