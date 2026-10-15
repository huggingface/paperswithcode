"""Restore author order on papers whose author links all have order 1.

Report-only unless --apply. Papers are read in batches of --batch-size by id;
each batch costs one arXiv request (5 s apart, backing off on 429/5xx), with
a Hugging Face papers API request only for papers arXiv cannot fully match. Applied papers drop out of
the selection, so a rerun resumes; pass --after-id to skip past reported ones.
Unmatched papers are appended to --report as JSON lines and left unchanged.
"""

from __future__ import annotations

import argparse
import json
import logging

from backend.database.connection import get_database_session
from backend.services.paper_author_order_service import (
    AuthorListClient,
    bare_arxiv_id,
    iter_unordered_papers,
    match_author_order,
    write_author_order,
)

logger = logging.getLogger("backfill_paper_author_order")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write author orders")
    parser.add_argument("--after-id", type=int, default=0, help="Start after paper id")
    parser.add_argument("--limit", type=int, help="Stop after this many papers")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--report", required=True, help="JSON-lines file for unmatched papers"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    client = AuthorListClient()
    session = get_database_session()
    db = next(session)
    seen = fixed = from_hf = unmatched = stale = 0
    try:
        with open(args.report, "a", encoding="utf-8") as report:
            for batch in iter_unordered_papers(
                db, after_id=args.after_id, batch_size=args.batch_size
            ):
                if args.limit is not None:
                    batch = batch[: args.limit - seen]
                ids = sorted({bare_arxiv_id(p.arxiv_id) for p in batch if p.arxiv_id})
                arxiv_lists = client.arxiv_authors(ids) if ids else {}
                for paper in batch:
                    seen += 1
                    arxiv_id = bare_arxiv_id(paper.arxiv_id) if paper.arxiv_id else None
                    listed = arxiv_lists.get(arxiv_id) if arxiv_id else None
                    order, missing = match_author_order(paper.authors, listed or [])
                    source = "arxiv"
                    if missing and arxiv_id:
                        hf_listed = client.hf_authors(arxiv_id)
                        if hf_listed:
                            order, missing = match_author_order(
                                paper.authors, hf_listed
                            )
                            source = "hf"
                    if missing:
                        unmatched += 1
                        report.write(
                            json.dumps(
                                {
                                    "paper_id": paper.paper_id,
                                    "arxiv_id": paper.arxiv_id,
                                    "unmatched": [a.name for a in missing],
                                    "linked": [a.name for a in paper.authors],
                                    "arxiv_authors": [a.name for a in listed or []],
                                }
                            )
                            + "\n"
                        )
                        continue
                    if args.apply:
                        if write_author_order(db, paper.paper_id, order) != len(order):
                            db.rollback()
                            stale += 1
                            logger.info("skip %s: links changed", paper.paper_id)
                            continue
                        db.commit()
                    fixed += 1
                    from_hf += source == "hf"
                db.rollback()
                report.flush()
                logger.info(
                    "seen=%d %s=%d (hf=%d) unmatched=%d stale=%d; resume with --after-id %d",
                    seen,
                    "fixed" if args.apply else "fixable",
                    fixed,
                    from_hf,
                    unmatched,
                    stale,
                    batch[-1].paper_id if batch else args.after_id,
                )
                if args.limit is not None and seen >= args.limit:
                    break
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
