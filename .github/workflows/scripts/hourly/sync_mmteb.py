"""Refresh the arXiv-backed MMTEB v2 overall leaderboard."""

import argparse

from backend.database.connection import db_manager
from backend.services.mmteb_sync_service import (
    LANES,
    MmtebSyncService,
    fetch_mmteb_leaderboard,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncMmtebJob(CronJobBase):
    def __init__(self, *, lane_id: str, dry_run: bool = False):
        super().__init__(job_name=f"sync_mmteb_{lane_id}", log_level="INFO")
        self.lane_id = lane_id
        self.dry_run = dry_run

    def run(self):
        entries = fetch_mmteb_leaderboard()
        session = db_manager.session_local()
        try:
            stats = MmtebSyncService(session).sync(
                entries,
                lane_id=self.lane_id,
                commit=not self.dry_run,
            )
            summary = stats.to_dict()
            for key in (
                "no_arxiv_models",
                "missing_papers",
                "ambiguous_papers",
                "unmanaged_conflicts",
            ):
                summary[key] = len(summary[key])
            self.logger.info("mmteb_sync lane=%s stats=%s", self.lane_id, summary)
            self.logger.info("Papers processed: %s", stats.matched)
            for label, values in (
                ("no_arxiv_models", stats.no_arxiv_models),
                ("missing_papers", stats.missing_papers),
                ("ambiguous_papers", stats.ambiguous_papers),
                ("unmanaged_conflicts", stats.unmanaged_conflicts),
            ):
                if values:
                    self.logger.warning(
                        "mmteb_%s count=%d sample=%s",
                        label,
                        len(values),
                        ",".join(values[:25]),
                    )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=tuple(LANES))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncMmtebJob(lane_id=args.lane, dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
