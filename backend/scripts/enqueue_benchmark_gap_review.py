"""Production entrypoint for the daily benchmark-gap review.

After the review it queues add-evals re-checks for indexed papers whose own
text reports a benchmark whose leaderboard appeared in the last
`--new-benchmark-days` days (see new_benchmark_recheck_service).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.benchmark_gap_review_service import BenchmarkGapReviewService
from backend.services.new_benchmark_recheck_service import NewBenchmarkRecheckService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-dispatch", action="store_true")
    parser.add_argument("--status", action="store_true")
    # Two days, so one missed daily run loses no boards.
    parser.add_argument("--new-benchmark-days", type=float, default=2)
    args = parser.parse_args()
    session = get_database_session()
    db = next(session)
    try:
        settings = get_settings()
        service = BenchmarkGapReviewService(db, settings)
        if args.status:
            print(json.dumps(service.status(), default=str, sort_keys=True))
            return 0
        result = service.reconcile(dispatch=False, dry_run=args.dry_run)
        result["new_benchmark_rechecks"] = NewBenchmarkRecheckService(
            db, settings
        ).reconcile(
            since=datetime.now(UTC) - timedelta(days=args.new_benchmark_days),
            job_service=service.job_service,
            dry_run=args.dry_run,
        )
        if not args.no_dispatch and not args.dry_run:
            service.job_service.dispatch_next(db, settings)
        print(json.dumps(result, default=str, sort_keys=True))
        return 0
    finally:
        try:
            next(session)
        except StopIteration:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
