"""Refresh reviewed Physics-IQ Verified evaluations from the official README."""

from backend.services.physics_iq_verified_sync_service import fetch_physics_iq_boards
from scripts.utils.live_leaderboard_job import LiveLeaderboardJob, main


class SyncPhysicsIqVerifiedJob(LiveLeaderboardJob):
    def fetch(self):
        # One README holds both tracks; each is its own board.
        return fetch_physics_iq_boards()


if __name__ == "__main__":
    raise SystemExit(
        main("sync_physics_iq_verified", __doc__, SyncPhysicsIqVerifiedJob)
    )
