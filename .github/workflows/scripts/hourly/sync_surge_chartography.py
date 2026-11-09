"""Refresh reviewed Chartography (no tools) evaluations from Surge AI."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_surge_chartography", __doc__))
