#!/bin/bash
# Wrapper script for the composite paper trending score CRON job.
# Uses flock to prevent overlapping runs.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$PROJECT_DIR/.github/workflows:${PYTHONPATH:-}"
LOCKFILE="/tmp/paper_trending_scores.lock"

cd "$PROJECT_DIR" || exit 1

exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "$(date) - Another instance is running, exiting"
    exit 0
fi

# De-prioritised (CPU + IO) and time-boxed so it cannot starve the API workers
# or run past the next hourly tick.
timeout -k 60s 50m nice -n 19 ionice -c3 /root/.local/bin/uv run --env-file backend/keys.env python -m scripts.hourly.calculate_paper_trending_scores

flock -u 200
