"""Refresh FrontierRSI evaluations from the official frontier-rsi.org data."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_frontier_rsi", __doc__))
