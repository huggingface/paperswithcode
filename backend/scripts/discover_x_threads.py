"""Production entrypoint for X thread discovery.

Search X for posts in which authors introduce recent trending papers. The job
is report-only unless PWC_X_THREAD_DISCOVERY_APPLY=true (or --apply), in which
case author matches are linked through the audited `x_threads` section.
Every match is first reviewed by gpt-5.6-sol (PWC_OPENAI_API_KEY); without a key
the job does not link anything.

`--backfill-days N` instead scans older papers from the last N days once each
with full-archive search. X allows 300 archive searches per 15 minutes, so run
backfill batches at least 15 minutes apart.

`--review-linked-since YYYY-MM-DD` re-reviews threads the job linked since that
date and, when applying, unlinks the ones the reviewer rejects.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import UTC, date, datetime

import httpx

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.x_thread_discovery_service import (
    discover_x_threads,
    make_x_search,
    review_linked_threads,
    stored_candidates,
)
from backend.services.x_thread_review_service import review_post

logger = logging.getLogger("discover_x_threads")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-papers", type=int, default=40)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Link matches even when PWC_X_THREAD_DISCOVERY_APPLY is not true",
    )
    parser.add_argument(
        "--show-candidates",
        action="store_true",
        help="Print stored unlinked matches without searching X",
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        help="Scan never-scanned papers from the last N days with full-archive search",
    )
    parser.add_argument(
        "--review-linked-since",
        type=date.fromisoformat,
        help="Re-review threads linked since this date (YYYY-MM-DD) without searching X",
    )
    args = parser.parse_args()
    if not 1 <= args.max_papers <= 200:
        parser.error("--max-papers must be between 1 and 200")
    if args.backfill_days is not None and not 1 <= args.backfill_days <= 730:
        parser.error("--backfill-days must be between 1 and 730")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    apply = args.apply or os.environ.get("PWC_X_THREAD_DISCOVERY_APPLY") == "true"

    openai_key = get_settings().openai_api_key
    if apply and not openai_key:
        logger.warning(
            "x_thread_review_unavailable PWC_OPENAI_API_KEY is not set; report-only"
        )
        apply = False
    client = httpx.Client(timeout=60)

    def review(paper, match):
        return review_post(
            client,
            api_key=openai_key,
            title=paper.title,
            abstract=paper.abstract,
            post_author=match["author"],
            post_handle=match["handle"],
            post_text=match.get("text", ""),
            post_urls=match.get("urls", []),
        )

    session = get_database_session()
    db = next(session)
    try:
        if args.show_candidates:
            print(json.dumps(stored_candidates(db), indent=2, sort_keys=True))
            return 0
        if args.review_linked_since:
            if not openai_key:
                logger.warning("x_thread_review_skipped PWC_OPENAI_API_KEY is not set")
                return 1
            since = datetime.combine(args.review_linked_since, datetime.min.time(), UTC)
            rejected = review_linked_threads(
                db, review, apply=apply, linked_since=since
            )
            print(json.dumps({"apply": apply, "rejected": rejected}, sort_keys=True))
            return 0
        token = os.environ.get("X_API_BEARER_TOKEN")
        if not token:
            logger.warning("x_thread_discovery_skipped X_API_BEARER_TOKEN is not set")
            return 0
        report = discover_x_threads(
            db,
            make_x_search(token, full_archive=args.backfill_days is not None),
            apply=apply,
            max_papers=args.max_papers,
            backfill_days=args.backfill_days,
            review=review if openai_key else None,
        )
    finally:
        client.close()
        try:
            next(session)
        except StopIteration:
            pass
    summary = report.to_dict()
    print(json.dumps(summary, sort_keys=True))
    for error in summary["errors"]:
        logger.warning("x_thread_discovery_error %s", json.dumps(error))
    # Every search failing means the job is blind (bad token or quota).
    failed = len(summary["errors"])
    return 1 if failed and failed == summary["papers_scanned"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
