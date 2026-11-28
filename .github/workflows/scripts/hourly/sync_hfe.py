"""Refresh HFE Family Pass^4 evaluations from the official Kaggle leaderboard."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_hfe", __doc__))
