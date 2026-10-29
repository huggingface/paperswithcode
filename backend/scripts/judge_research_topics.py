"""Judge papers against followed free-text research topics with Jev.

Hourly (default): every paper from the last 90 days whose card changed or that
has no verdict yet, against every followed topic. Failed Jev calls leave pairs
unjudged for the next run.

Every minute (`--backfill`): claim topics awaiting their first judgement (new
topics, retries, or claims whose worker died) and judge the last 90 days plus
older papers by dense + lexical recall, in batches while they still match.

Needs PWC_OPENROUTER_API_KEY.

    python -m backend.scripts.judge_research_topics
    python -m backend.scripts.judge_research_topics --backfill
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime

import httpx

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.research_topic_service import (
    JevTopicJudge,
    backfill,
    claim_backfill,
    judge_recent,
)

logger = logging.getLogger("judge_research_topics")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true", help="Drain new topics")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    api_key = get_settings().openrouter_api_key
    if not api_key:
        logger.error("PWC_OPENROUTER_API_KEY is not set")
        return 1

    db = db_manager.session_local()
    try:
        with httpx.Client(timeout=60) as client:
            judge = JevTopicJudge(api_key, client)
            if args.backfill:
                while topic := claim_backfill(db, datetime.now(UTC)):
                    status = backfill(db, judge, topic, datetime.now(UTC))
                    logger.info(
                        "topic %s backfill %s: %s/%s papers",
                        topic.id,
                        status,
                        topic.backfill_done,
                        topic.backfill_total,
                    )
                return 0
            judged, failed = judge_recent(db, judge, datetime.now(UTC))
    finally:
        db.close()
    logger.info("pairs judged: %d, judge failures: %d", judged, failed)
    return 1 if failed and not judged else 0


if __name__ == "__main__":
    raise SystemExit(main())
