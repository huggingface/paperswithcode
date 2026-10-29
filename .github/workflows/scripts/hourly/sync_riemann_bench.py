"""Refresh the Riemann-Bench board from its official leaderboard."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_riemann_bench", __doc__))
