"""Refresh the SWE-sweep board from its official leaderboard."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_swe_sweep", __doc__))
