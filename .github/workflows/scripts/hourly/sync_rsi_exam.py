"""Refresh RSI-Exam evaluations from the official rsi-exam.ai Full board."""

from scripts.utils.live_leaderboard_job import main

if __name__ == "__main__":
    raise SystemExit(main("sync_rsi_exam", __doc__))
