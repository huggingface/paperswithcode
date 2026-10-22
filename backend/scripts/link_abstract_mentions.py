"""Link literal catalog names in paper abstracts (abstract entity linking).

Hourly (default): papers created or updated in the last `--since-days` whose
stored mentions are missing, stale (the abstract changed), or from an older
prompt version, newest first, at most `--limit` papers.

Nightly (`--rescan`): every paper, so catalog changes (new methods, aliases,
modes) reach older abstracts. Earlier verdicts for the same abstract are
reused, so the judge is asked only about new pairs, and rows are rewritten only
when a paper's links changed.

Needs PWC_OPENROUTER_API_KEY for the Jev judge; `--dry-run` only counts.

    python -m backend.scripts.link_abstract_mentions
    python -m backend.scripts.link_abstract_mentions --rescan
    python -m backend.scripts.link_abstract_mentions --paper-ids 123785 123682
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import or_, select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Paper
from backend.services.abstract_link_service import (
    JevJudge,
    abstract_sha,
    judge_paper,
    load_index,
    mentions_changed,
    store_paper_mentions,
    stored_abstract_shas,
)

logger = logging.getLogger("link_abstract_mentions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-ids", type=int, nargs="*", help="Only these papers")
    parser.add_argument("--rescan", action="store_true", help="Every paper")
    parser.add_argument("--since-days", type=int, default=3)
    parser.add_argument("--limit", type=int, default=500, help="Papers to rewrite")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    api_key = get_settings().openrouter_api_key
    if not api_key and not args.dry_run:
        logger.error("PWC_OPENROUTER_API_KEY is not set")
        return 1

    db = db_manager.session_local()
    written = unchanged = skipped = failed = 0
    try:
        index = load_index(db)
        current = stored_abstract_shas(db)
        query = select(Paper.id).where(
            Paper.is_latest_version, Paper.abstract.isnot(None)
        )
        if args.paper_ids:
            query = query.where(Paper.id.in_(args.paper_ids))
        elif not args.rescan:
            since = datetime.now(UTC) - timedelta(days=args.since_days)
            query = query.where(
                or_(Paper.created_at >= since, Paper.updated_at >= since)
            )
        paper_ids = db.scalars(query.order_by(Paper.id.desc())).all()
        with httpx.Client(timeout=60) as client:
            judge = JevJudge(api_key, client)
            for paper_id in paper_ids:
                if written >= args.limit:
                    break
                paper = db.get(Paper, paper_id)
                fresh = current.get(paper.id) == abstract_sha(paper.abstract)
                if fresh and not (args.rescan or args.paper_ids):
                    skipped += 1
                    continue
                if args.dry_run:
                    written += 1
                    continue
                try:
                    rows = judge_paper(db, paper, index, judge)
                except httpx.HTTPError as error:
                    logger.warning("paper %s: judge failed: %s", paper.id, error)
                    failed += 1
                    continue
                if not mentions_changed(db, paper.id, rows):
                    unchanged += 1
                    continue
                store_paper_mentions(db, paper.id, rows)
                db.commit()
                written += 1
    finally:
        db.close()
    logger.info(
        "papers rewritten: %d, unchanged: %d, already current: %d, judge failures: %d",
        written,
        unchanged,
        skipped,
        failed,
    )
    return 1 if failed and not written else 0


if __name__ == "__main__":
    raise SystemExit(main())
