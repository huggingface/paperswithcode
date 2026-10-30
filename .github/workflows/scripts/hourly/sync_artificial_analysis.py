"""Refresh paper-linked Artificial Analysis language and TTS evaluations."""

import argparse

from backend.database.connection import db_manager
from backend.services.artificial_analysis_sync_service import (
    ArtificialAnalysisSyncService,
    fetch_artificial_analysis_leaderboard,
    run_discovery,
)
from backend.services.artificial_analysis_tts_sync_service import (
    ArtificialAnalysisTtsSyncService,
    fetch_artificial_analysis_tts_leaderboard,
    run_tts_discovery,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncArtificialAnalysisJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_artificial_analysis", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        leaderboard = fetch_artificial_analysis_leaderboard()
        self.logger.info(
            "artificial_analysis_api_quota remaining=%s limit=%s",
            leaderboard.quota_remaining,
            leaderboard.quota_limit,
        )
        if leaderboard.withdrawn_indexes:
            self.logger.warning(
                "artificial_analysis_withdrawn_indexes %s (rows kept)",
                ",".join(leaderboard.withdrawn_indexes),
            )
        session = db_manager.session_local()
        try:
            discovery = run_discovery(
                session, persist=not self.dry_run, leaderboard=leaderboard
            )
            self.logger.info("artificial_analysis_discovery %s", discovery.to_dict())
            stats = ArtificialAnalysisSyncService(session).sync(
                leaderboard,
                discovery=discovery,
                commit=not self.dry_run,
            )
            self.logger.info("artificial_analysis_sync %s", stats.to_dict())
            if stats.missing_upstream:
                self.logger.warning(
                    "artificial_analysis_missing_upstream %s",
                    ",".join(stats.missing_upstream),
                )
            tts_entries = fetch_artificial_analysis_tts_leaderboard()
            tts_discovery = run_tts_discovery(session, persist=not self.dry_run)
            self.logger.info(
                "artificial_analysis_tts_discovery %s", tts_discovery.to_dict()
            )
            tts_stats = ArtificialAnalysisTtsSyncService(session).sync(
                tts_entries,
                discovery=tts_discovery,
                commit=not self.dry_run,
            )
            self.logger.info("artificial_analysis_tts_sync %s", tts_stats.to_dict())
            self.logger.info(
                "Papers processed: language=%s tts=%s",
                stats.matched,
                tts_stats.matched,
            )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncArtificialAnalysisJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
