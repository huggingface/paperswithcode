"""Refresh Science's Last Exam evaluations from the official leaderboard."""

from backend.services.sle_sync_service import fetch_sle_boards
from scripts.utils.live_leaderboard_job import LiveLeaderboardJob, main


class SyncSleJob(LiveLeaderboardJob):
    def fetch(self):
        # One data bundle holds every assessment; each is its own board.
        return fetch_sle_boards()


if __name__ == "__main__":
    raise SystemExit(main("sync_sle", __doc__, SyncSleJob))
