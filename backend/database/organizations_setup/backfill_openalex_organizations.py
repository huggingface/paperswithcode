#!/usr/bin/env python3
"""Link arXiv papers to organizations from their OpenAlex author affiliations.

Affiliations reach the catalog only through the reviewed institution map, as
``paper_organizations`` rows with ``source = 'openalex'``. Links are only ever
added; ``DELETE ... WHERE source = 'openalex'`` undoes a run. The daily
``link_openalex_organizations`` CRON keeps recent papers current; this command
is for historical backfills.

Papers are processed in ascending ID order, 100 per OpenAlex request. The
command is a dry run unless ``--apply`` is supplied. It uses
``PWC_OPENALEX_API_KEY`` when set. When OpenAlex refuses a request (for example
once the daily budget is spent) it stops and prints the ``--resume-after-id``
value for the next run:
  uv run --env-file backend/keys.env python \
    backend/database/organizations_setup/backfill_openalex_organizations.py \
    --since 2025-01-01 --apply
"""

from __future__ import annotations

import argparse
from datetime import date

import httpx

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.openalex_organization_linking_service import (
    LinkingStats,
    link_openalex_organizations,
)


def print_progress(stats: LinkingStats) -> None:
    print(
        f"papers={stats.papers} matched_works={stats.matched_works} "
        f"links={sum(stats.linked.values())} last_id={stats.last_id}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    parser.add_argument("--resume-after-id", type=int, default=0)
    parser.add_argument("--limit", type=int, help="Stop after this many papers.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with db_manager.session_local() as db, httpx.Client(timeout=60) as client:
        stats = link_openalex_organizations(
            db,
            client,
            since=args.since,
            api_key=get_settings().openalex_api_key,
            resume_after_id=args.resume_after_id,
            limit=args.limit,
            apply=args.apply,
            on_batch=print_progress,
        )
    if stats.stopped_status:
        print(
            f"STOPPED: OpenAlex returned {stats.stopped_status}; "
            f"rerun with --resume-after-id {stats.last_id}"
        )
    verb = "linked" if args.apply else "would link (before existing-link dedupe)"
    print(
        f"{verb} {sum(stats.linked.values())} paper-organization pairs; "
        f"last_id={stats.last_id}"
    )
    for slug, count in stats.linked.most_common(25):
        print(f"  {slug}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
