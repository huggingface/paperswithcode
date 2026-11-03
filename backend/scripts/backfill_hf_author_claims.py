"""Backfill Hugging Face claims on legacy author links and split off namesakes.

Two steps (see backend/services/author_claim_backfill_service.py):

    # 1. Cache HF author lists of every paper with an unclaimed HF-linked link.
    #    Read-only on the database, paced for HF's rate limit; rerun to resume.
    uv run --env-file backend/keys.env python -m backend.scripts.backfill_hf_author_claims \
        fetch --cache claims.jsonl

    # 2. Replay the cache, fix doubled links, split namesakes, merge provable
    #    duplicates, delete empty authors. Rolled back (a dry run) unless
    #    --apply; every change is written to --report as JSON lines either way.
    uv run --env-file backend/keys.env python -m backend.scripts.backfill_hf_author_claims \
        run --cache claims.jsonl --report report.jsonl [--apply]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from backend.database.connection import db_manager
from backend.services.author_claim_backfill_service import (
    DEFAULT_REQUESTS_PER_SECOND,
    PHASES,
    AuthorClaimCleanup,
    HfPaperClient,
    fetch_hf_papers,
)

logger = logging.getLogger("backfill_hf_author_claims")


def _fetch(args: argparse.Namespace) -> None:
    client = HfPaperClient(requests_per_second=args.rate)
    with db_manager.session_local() as db:
        fetched = fetch_hf_papers(
            db,
            client,
            Path(args.cache),
            limit=args.limit,
            on_progress=lambda count, paper_id: logger.info(
                "fetched=%d through paper %d", count, paper_id
            ),
        )
    logger.info("fetched %d papers into %s", fetched, args.cache)


def _run(args: argparse.Namespace) -> None:
    phases = args.phases.split(",")
    unknown = set(phases) - set(PHASES)
    if unknown:
        raise SystemExit(f"unknown phases: {', '.join(sorted(unknown))}")
    with (
        db_manager.session_local() as db,
        open(args.report, "w", encoding="utf-8") as report,
    ):
        cleanup = AuthorClaimCleanup(
            db, lambda entry: report.write(json.dumps(entry) + "\n")
        )
        steps = {
            "claims": lambda: cleanup.replay_claims(Path(args.cache)),
            "doubles": cleanup.fix_doubles,
            "split": cleanup.split_namesakes,
            "merge": cleanup.merge_namesakes,
            "empty": cleanup.delete_empty_authors,
        }
        # Phases run in their fixed order; each builds on the previous one.
        for phase in PHASES:
            if phase not in phases:
                continue
            steps[phase]()
            if args.apply:
                db.commit()
            logger.info("%s done: %s", phase, json.dumps(cleanup.stats.to_dict()))
        if not args.apply:
            db.rollback()
    print(
        json.dumps(
            {"apply": args.apply, "phases": phases, **cleanup.stats.to_dict()},
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="Cache HF author lists (read-only)")
    fetch.add_argument("--cache", required=True, help="JSON-lines cache to append to")
    fetch.add_argument("--limit", type=int, help="Stop after this many requests")
    fetch.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_REQUESTS_PER_SECOND,
        help=f"HF requests per second (default {DEFAULT_REQUESTS_PER_SECOND})",
    )

    run = commands.add_parser("run", help="Replay claims and clean up authors")
    run.add_argument("--cache", required=True, help="Cache written by fetch")
    run.add_argument("--report", required=True, help="JSON-lines change report")
    run.add_argument("--phases", default=",".join(PHASES))
    run.add_argument("--apply", action="store_true", help="Commit the changes")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    {"fetch": _fetch, "run": _run}[args.command](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
