"""Refresh reviewed SWE-Marathon v1.1 evaluations from Abundant AI's swe-marathon.org."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_swe_marathon", __doc__))
