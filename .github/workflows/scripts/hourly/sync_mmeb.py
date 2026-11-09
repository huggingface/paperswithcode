"""Refresh one linked MMEB-v2/v3 overall leaderboard."""

import argparse

from backend.database.connection import db_manager
from backend.services.mmeb_sync_service import (
    LANES,
    MmebSyncService,
    fetch_mmeb_leaderboard,
)
from scripts.utils.cron_helpers import DatabaseCronJob


class SyncMmebJob(DatabaseCronJob):
    def __init__(self, *, version: str, dry_run: bool = False):
        super().__init__(job_name=f"sync_mmeb_{version}", log_level="INFO")
        self.version = version
        self.dry_run = dry_run

    def run(self):
        entries = fetch_mmeb_leaderboard(version=self.version)
        session = db_manager.session_local()
        try:
            stats = MmebSyncService(session).sync(
                entries,
                version=self.version,
                commit=not self.dry_run,
            )
            summary = stats.to_dict()
            for key in (
                "auto_matched",
                "unresolved_models",
                "ambiguous_models",
                "unmanaged_conflicts",
            ):
                summary[key] = len(summary[key])
            self.logger.info("mmeb_sync version=%s stats=%s", self.version, summary)
            self.logger.info("Papers processed: %s", stats.matched)
            for label, values in (
                ("auto_matched", stats.auto_matched),
                ("unresolved_models", stats.unresolved_models),
                ("ambiguous_models", stats.ambiguous_models),
                ("unmanaged_conflicts", stats.unmanaged_conflicts),
            ):
                if values:
                    self.logger.warning(
                        "mmeb_%s count=%d sample=%s",
                        label,
                        len(values),
                        ",".join(values[:25]),
                    )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", choices=tuple(LANES))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncMmebJob(version=args.version, dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
