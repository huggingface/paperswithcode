"""Production entrypoint for X post like refreshes.

Read the like counts of linked X posts that are due on their first-week
schedule and update their likes-per-hour EMA in `x_post_metrics`, which feeds
the X part of the paper trending score. Syndication is tried first; posts it
cannot serve use the X API (X_API_BEARER_TOKEN), at most
PWC_X_LIKES_API_DAILY_CAP posts per UTC day (default 300).

The job is report-only unless PWC_X_LIKES_APPLY=true (or --apply): it then reads
through syndication only and rolls back, so nothing is stored or billed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from backend.database.connection import get_database_session
from backend.services.x_post_likes_service import (
    make_api_reader,
    make_syndication_reader,
    refresh_likes,
)

logger = logging.getLogger("refresh_x_post_likes")

DEFAULT_API_DAILY_CAP = 300


def api_usage_path() -> Path:
    lock_dir = os.getenv(
        "PWC_CRON_LOCK_DIR",
        str(Path(__file__).resolve().parents[2] / ".github/workflows/scripts/data"),
    )
    return Path(lock_dir) / "x_post_likes_api_usage.json"


def api_reads_today(path: Path, today: str) -> int:
    if not path.exists():
        return 0
    usage = json.loads(path.read_text())
    return usage["reads"] if usage.get("day") == today else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-posts", type=int, default=500)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Store readings even when PWC_X_LIKES_APPLY is not true",
    )
    args = parser.parse_args()
    if not 1 <= args.max_posts <= 2000:
        parser.error("--max-posts must be between 1 and 2000")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # One line per request would flood the journal with every hourly read.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    apply = args.apply or os.environ.get("PWC_X_LIKES_APPLY") == "true"

    now = datetime.now(UTC)
    today = now.date().isoformat()
    usage_path = api_usage_path()
    used = api_reads_today(usage_path, today)
    cap = int(os.environ.get("PWC_X_LIKES_API_DAILY_CAP") or DEFAULT_API_DAILY_CAP)
    token = os.environ.get("X_API_BEARER_TOKEN")
    client = httpx.Client()

    session = get_database_session()
    db = next(session)
    try:
        report = refresh_likes(
            db,
            now=now,
            read_syndication=make_syndication_reader(client),
            read_api=make_api_reader(client, token) if apply and token else None,
            api_budget=max(cap - used, 0),
            max_posts=args.max_posts,
        )
        if apply:
            db.commit()
            if report.api_reads:
                usage_path.parent.mkdir(parents=True, exist_ok=True)
                usage_path.write_text(
                    json.dumps({"day": today, "reads": used + report.api_reads})
                )
        else:
            db.rollback()
    finally:
        client.close()
        try:
            next(session)
        except StopIteration:
            pass

    print(
        json.dumps(
            {
                "apply": apply,
                "api_reads_today": used + report.api_reads,
                "api_daily_cap": cap,
                **asdict(report),
            },
            sort_keys=True,
        )
    )
    # A failing paid fallback (bad token, no credits) must show on the dashboard.
    return 1 if report.api_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
