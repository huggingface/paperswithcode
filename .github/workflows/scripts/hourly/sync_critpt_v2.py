"""Refresh the CritPt v2 board from the Artificial Analysis evaluation page."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_critpt_v2", __doc__))
