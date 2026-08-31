"""Production entrypoint for hourly Hugging Face trending-model curation."""

from __future__ import annotations

import argparse
import json

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.hf_trending_model_curation_service import (
    HFTrendingModelCurationService,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-queued", type=int, default=10)
    parser.add_argument("--no-dispatch", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.max_queued <= 50:
        parser.error("--max-queued must be between 0 and 50")
    session = get_database_session()
    db = next(session)
    try:
        service = HFTrendingModelCurationService(db, get_settings(), rollout=True)
        result = (
            service.status()
            if args.status
            else service.reconcile(
                dispatch=not args.no_dispatch,
                dry_run=args.dry_run,
                max_queued=args.max_queued,
            )
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
