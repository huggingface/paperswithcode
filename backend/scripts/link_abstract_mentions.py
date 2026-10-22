"""Link literal catalog names in paper abstracts (abstract entity linking).

Judges every paper whose stored mentions are missing, stale (the abstract
changed), or from an older prompt version, newest papers first. Needs
PWC_OPENROUTER_API_KEY for the Jev judge; `--dry-run` only counts the work.

    python -m backend.scripts.link_abstract_mentions --limit 500
    python -m backend.scripts.link_abstract_mentions --paper-ids 123785 123682
"""

from __future__ import annotations

import argparse
import logging

import httpx
from sqlalchemy import select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Paper
from backend.services.abstract_link_service import (
    JevJudge,
    abstract_sha,
    judge_paper,
    load_index,
    stored_abstract_shas,
    store_paper_mentions,
)

logger = logging.getLogger("link_abstract_mentions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-ids", type=int, nargs="*", help="Only these papers")
    parser.add_argument("--limit", type=int, default=500, help="Papers to link")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    api_key = get_settings().openrouter_api_key
    if not api_key and not args.dry_run:
        logger.error("PWC_OPENROUTER_API_KEY is not set")
        return 1

    db = db_manager.session_local()
    linked = skipped = empty = failed = 0
    try:
        index = load_index(db)
        current = stored_abstract_shas(db)
        query = select(Paper.id).where(
            Paper.is_latest_version, Paper.abstract.isnot(None)
        )
        if args.paper_ids:
            query = query.where(Paper.id.in_(args.paper_ids))
        paper_ids = db.scalars(query.order_by(Paper.id.desc())).all()
        with httpx.Client(timeout=60) as client:
            judge = JevJudge(api_key, client)
            for paper_id in paper_ids:
                if linked >= args.limit:
                    break
                paper = db.get(Paper, paper_id)
                if not args.paper_ids and current.get(paper.id) == abstract_sha(
                    paper.abstract
                ):
                    skipped += 1
                    continue
                if args.dry_run:
                    linked += 1
                    continue
                try:
                    rows = judge_paper(db, paper, index, judge)
                except httpx.HTTPError as error:
                    logger.warning("paper %s: judge failed: %s", paper.id, error)
                    failed += 1
                    continue
                store_paper_mentions(db, paper.id, rows)
                db.commit()
                if rows:
                    linked += 1
                else:
                    empty += 1  # nothing to link; cheap to rescan, not counted
    finally:
        db.close()
    logger.info(
        "abstracts linked: %d, without candidates: %d, already current: %d, "
        "judge failures: %d",
        linked,
        empty,
        skipped,
        failed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
