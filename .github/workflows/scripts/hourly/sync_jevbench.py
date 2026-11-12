"""Refresh JevBench evaluations from Benchmark Heaven's official API board."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_jevbench", __doc__))
