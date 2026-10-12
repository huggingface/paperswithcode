"""Production entrypoint for the model-release radar.

Report recent official model releases (lab news feeds and unmapped Artificial
Analysis leaderboard models) and whether a paper row already covers each one.
The scan is read-only; unindexed releases are logged as a warning for an
operator to index with the add-external-paper and add-evals skills.
"""

from __future__ import annotations

import argparse
import json
import logging
import os

from backend.database.connection import get_database_session
from backend.services.artificial_analysis_sync_service import (
    fetch_artificial_analysis_leaderboard,
)
from backend.services.model_release_radar_service import (
    format_unindexed,
    scan_model_releases,
)

logger = logging.getLogger("scan_model_releases")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument(
        "--skip-artificial-analysis",
        action="store_true",
        help="Only scan lab news feeds",
    )
    args = parser.parse_args()
    if not 1 <= args.lookback_days <= 90:
        parser.error("--lookback-days must be between 1 and 90")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fetch_leaderboard = (
        None
        if args.skip_artificial_analysis
        or not os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY")
        else fetch_artificial_analysis_leaderboard
    )
    session = get_database_session()
    db = next(session)
    try:
        report = scan_model_releases(
            db, lookback_days=args.lookback_days, fetch_leaderboard=fetch_leaderboard
        )
    finally:
        try:
            next(session)
        except StopIteration:
            pass
    print(json.dumps(report.to_dict(), sort_keys=True))
    if report.unindexed:
        logger.warning("model_release_radar_unindexed %s", format_unindexed(report))
    for error in report.errors:
        logger.warning("model_release_radar_source_error %s", json.dumps(error))
    # Every source failing means the radar is blind, not that nothing shipped.
    return 1 if report.errors and len(report.errors) == report.sources_checked else 0


if __name__ == "__main__":
    raise SystemExit(main())
