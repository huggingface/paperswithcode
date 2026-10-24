"""Production entrypoint for the model-release radar.

Report recent model releases (lab news feeds, unmapped Artificial Analysis
leaderboard models, and web news about any lab) and whether a paper row
already covers each one.
Unindexed releases are logged as a warning and recorded as release signals.
Qualifying signals get a scoped resolve-model-paper curation job that finds
the lab's own announcement and resolves it to a paper; a new external paper
then gets the usual enrich-paper -> add-evals workflow. `--report-only`
skips recording and queueing.
"""

from __future__ import annotations

import argparse
import json
import logging
import os

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.artificial_analysis_sync_service import (
    fetch_artificial_analysis_leaderboard,
)
from backend.services.model_release_radar_service import (
    ExaSearchClient,
    OpenAIReleaseExtractor,
    format_unindexed,
    scan_model_releases,
)
from backend.services.codex_add_evals_service import codex_paper_job_service
from backend.services.model_release_signal_service import (
    queue_release_signals,
    record_release_signals,
)

logger = logging.getLogger("scan_model_releases")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument(
        "--skip-artificial-analysis",
        action="store_true",
        help="Do not check the Artificial Analysis leaderboard",
    )
    parser.add_argument(
        "--skip-web-search",
        action="store_true",
        help="Do not search web news for releases",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only report releases; do not record signals or queue curation",
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
    exa_key = os.environ.get("EXA_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    web_search = extract_releases = None
    if not args.skip_web_search and exa_key and openai_key:
        web_search = ExaSearchClient(exa_key).search
        extract_releases = OpenAIReleaseExtractor(openai_key)
    elif not args.skip_web_search:
        logger.warning(
            "model_release_radar_source_error web search needs EXA_API_KEY and "
            "OPENAI_API_KEY"
        )
    session = get_database_session()
    db = next(session)
    try:
        report = scan_model_releases(
            db,
            lookback_days=args.lookback_days,
            fetch_leaderboard=fetch_leaderboard,
            web_search=web_search,
            extract_releases=extract_releases,
        )
        queued = []
        if not args.report_only:
            settings = get_settings()
            record_release_signals(db, report)
            queued = queue_release_signals(db, settings, jobs=codex_paper_job_service)
            db.commit()
            if queued:
                codex_paper_job_service.dispatch_next(db, settings)
    finally:
        try:
            next(session)
        except StopIteration:
            pass
    print(json.dumps(report.to_dict(), sort_keys=True))
    if report.unindexed:
        logger.warning("model_release_radar_unindexed %s", format_unindexed(report))
    for signal in queued:
        logger.info(
            "model_release_radar_queued %s",
            json.dumps(
                {"lab": signal.lab, "model": signal.model_name, "url": signal.lead_url}
            ),
        )
    for error in report.errors:
        logger.warning("model_release_radar_source_error %s", json.dumps(error))
    # Every source failing means the radar is blind, not that nothing shipped.
    return 1 if report.errors and len(report.errors) == report.sources_checked else 0


if __name__ == "__main__":
    raise SystemExit(main())
