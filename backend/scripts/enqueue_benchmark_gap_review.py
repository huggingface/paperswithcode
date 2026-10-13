"""Production entrypoint for the daily benchmark-gap review."""

from __future__ import annotations

import argparse
import json

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.benchmark_gap_review_service import BenchmarkGapReviewService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-dispatch", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    session = get_database_session()
    db = next(session)
    try:
        service = BenchmarkGapReviewService(db, get_settings())
        result = (
            service.status()
            if args.status
            else service.reconcile(dispatch=not args.no_dispatch, dry_run=args.dry_run)
        )
        print(json.dumps(result, default=str, sort_keys=True))
        return 0
    finally:
        try:
            next(session)
        except StopIteration:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
