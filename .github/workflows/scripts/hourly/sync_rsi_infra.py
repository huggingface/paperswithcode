"""Refresh RSI-Infra Bench evaluations from the official leaderboard table."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_rsi_infra", __doc__))
