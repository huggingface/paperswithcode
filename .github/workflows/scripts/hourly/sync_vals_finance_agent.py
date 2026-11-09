"""Refresh reviewed Finance Agent v2 evaluations from the Vals AI leaderboard."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_vals_finance_agent", __doc__))
