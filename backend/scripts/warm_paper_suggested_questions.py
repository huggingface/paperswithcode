"""Production entrypoint for pre-generating paper-page suggested questions.

Fills `paper_suggested_questions` for the papers visitors see first (the
home feed's first pages, then the first page of every task and method page)
so their paper pages show questions without waiting on gpt-6-luna. Papers
that already have questions are skipped; `--limit` bounds generations per run.
Needs PWC_OPENAI_API_KEY; `--dry-run` only counts the work.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime

import httpx

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.paper_suggested_questions_warm_service import (
    visible_paper_ids,
    warm_suggested_questions,
)

logger = logging.getLogger("warm_paper_suggested_questions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=1500, help="Maximum generations this run"
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--dry-run", action="store_true", help="Count candidates without generating"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    api_key = get_settings().openai_api_key
    if not api_key and not args.dry_run:
        logger.error("PWC_OPENAI_API_KEY is not set")
        return 1

    db = db_manager.session_local()
    try:
        paper_ids = visible_paper_ids(db, datetime.now(UTC).date())
        with httpx.Client(timeout=30) as client:
            stats = warm_suggested_questions(
                db,
                paper_ids,
                client=client,
                api_key=api_key,
                limit=0 if args.dry_run else args.limit,
                workers=args.workers,
            )
    finally:
        db.close()

    print(json.dumps({"dry_run": args.dry_run, **stats}, sort_keys=True))
    # A run where every generation failed means the model is unavailable.
    return 1 if stats["failed"] and not stats["generated"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
