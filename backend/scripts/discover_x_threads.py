"""Production entrypoint for X thread discovery.

Search X for posts in which authors introduce recent trending papers. The job
is report-only unless PWC_X_THREAD_DISCOVERY_APPLY=true (or --apply), in which
case author matches are linked through the audited `x_threads` section.
"""

from __future__ import annotations

import argparse
import json
import logging
import os

from backend.database.connection import get_database_session
from backend.services.x_thread_discovery_service import (
    discover_x_threads,
    make_x_search,
    stored_candidates,
)

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
    args = parser.parse_args()
    if not 1 <= args.max_papers <= 200:
        parser.error("--max-papers must be between 1 and 200")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    apply = args.apply or os.environ.get("PWC_X_THREAD_DISCOVERY_APPLY") == "true"

    session = get_database_session()
    db = next(session)
    try:
        if args.show_candidates:
            print(json.dumps(stored_candidates(db), indent=2, sort_keys=True))
            return 0
        token = os.environ.get("X_API_BEARER_TOKEN")
        if not token:
            logger.warning("x_thread_discovery_skipped X_API_BEARER_TOKEN is not set")
            return 0
        report = discover_x_threads(
            db, make_x_search(token), apply=apply, max_papers=args.max_papers
        )
    finally:
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
