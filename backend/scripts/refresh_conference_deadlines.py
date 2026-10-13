"""pwc-cron entrypoint: daily AI conference deadline sweep.

Collects finished off-box research Jobs (applying their validated change sets),
then launches the daily sweep. See backend/scripts/conference_deadlines.py.
"""

from backend.scripts.conference_deadlines import scheduled_main

if __name__ == "__main__":
    raise SystemExit(scheduled_main("daily"))
