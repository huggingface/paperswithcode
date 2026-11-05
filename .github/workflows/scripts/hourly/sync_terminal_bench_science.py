"""Refresh the Terminal-Bench-Science board from the Artificial Analysis evaluation page."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_terminal_bench_science", __doc__))
