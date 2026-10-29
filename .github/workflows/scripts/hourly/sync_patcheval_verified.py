"""Refresh the PatchEval-Verified board from its official leaderboard."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_patcheval_verified", __doc__))
