"""Refresh RSI-Inference Bench evaluations from the official leaderboard."""

from backend.services.rsi_inference_sync_service import fetch_rsi_inference_boards
from scripts.utils.live_leaderboard_job import LiveLeaderboardJob, main


class SyncRsiInferenceJob(LiveLeaderboardJob):
    def fetch(self):
        return fetch_rsi_inference_boards()


if __name__ == "__main__":
    raise SystemExit(main("sync_rsi_inference", __doc__, SyncRsiInferenceJob))
