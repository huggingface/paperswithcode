"""Production entrypoint for rolling HF daily-paper curation reconciliation."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.codex_add_evals_service import CanaryDispatchFailed
from backend.services.hf_daily_curation_service import (
    CurationRetryConflict,
    HFDailyCurationService,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--lookback-days", type=int, default=7, choices=range(1, 31))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--enable-dispatch", action="store_true")
    action.add_argument("--disable-dispatch", action="store_true")
    action.add_argument("--canary-job", type=uuid.UUID)
    action.add_argument("--retry-job", type=uuid.UUID)
    action.add_argument("--validate-job", type=uuid.UUID)
    action.add_argument("--status", action="store_true")
    parser.add_argument("--reason")
    args = parser.parse_args()
    session = get_database_session()
    db = next(session)
    try:
        service = HFDailyCurationService(db, get_settings())
        if args.status:
            result = service.status()
        elif args.canary_job:
            try:
                result = service.dispatch_canary_job(args.canary_job)
            except CanaryDispatchFailed as error:
                result = {
                    "error": str(error),
                    "job_id": str(args.canary_job),
                    "launched": False,
                }
        elif args.retry_job:
            try:
                result = service.retry_scheduled_job(args.retry_job)
            except CurationRetryConflict as error:
                result = {
                    "error": str(error),
                    "job_id": str(args.retry_job),
                    "retry_conflict": True,
                }
        elif args.validate_job:
            result = service.validator_replay(args.validate_job)
        elif args.enable_dispatch:
            result = service.set_dispatch(True)
        elif args.disable_dispatch:
            result = service.set_dispatch(False, reason=args.reason)
        else:
            result = service.reconcile(
                today=args.date,
                lookback_days=args.lookback_days,
                paper_limit=args.limit,
                dry_run=args.dry_run,
            )
        summary = json.dumps(result, default=str, sort_keys=True)
        print(f"HF_DAILY_CURATION_SUMMARY {summary}", file=sys.stderr)
        print(summary)
        return (
            1
            if result.get("valid") is False
            or result.get("launched") is False
            or result.get("retry_conflict") is True
            else 0
        )
    finally:
        try:
            next(session)
        except StopIteration:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
