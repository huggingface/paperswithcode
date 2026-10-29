"""Refresh the Vending-Bench 2 board from its official leaderboard."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_vending_bench_2", __doc__))
