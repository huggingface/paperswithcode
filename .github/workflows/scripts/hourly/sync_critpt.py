"""Refresh the CritPt board from the Artificial Analysis evaluation page."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_critpt", __doc__))
