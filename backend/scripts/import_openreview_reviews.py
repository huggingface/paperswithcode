"""Import public OpenReview submissions and reviews (CRON, every 6 hours).

For each `--venue` (default: ICLR 2027), pages through every submission with
its forum replies, oldest submission number first, and upserts the public ones
into `openreview_submissions` / `openreview_notes`. Each page is committed on
its own, so an interrupted run keeps what it fetched. Notes that a forum no
longer shows publicly get `removed_at`. Afterwards, unmatched submissions are
linked to the one PwC paper with the same normalized title.

The OpenReview API refuses anonymous clients, so `PWC_OPENREVIEW_USERNAME`
and `PWC_OPENREVIEW_PASSWORD` must be set. Only notes readable by `everyone`
are stored, whatever the account itself may see.

    python -m backend.scripts.import_openreview_reviews
    python -m backend.scripts.import_openreview_reviews --dry-run --max-pages 2
    python -m backend.scripts.import_openreview_reviews --venue ICLR.cc/2026/Conference
"""

from __future__ import annotations

import argparse
import json
import logging
import time

import openreview

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.openreview_import_service import (
    ImportStats,
    conference_id_for,
    link_papers,
    parse_page,
    write_page,
)

logger = logging.getLogger("import_openreview_reviews")

API_URL = "https://api2.openreview.net"
DEFAULT_VENUES = ("ICLR.cc/2027/Conference",)


def import_venue(
    client: openreview.api.OpenReviewClient,
    venue_id: str,
    *,
    page_size: int,
    max_pages: int | None,
    pause_seconds: float,
    dry_run: bool,
) -> dict:
    stats = ImportStats()
    started = time.monotonic()
    with db_manager.session_local() as db:
        conference_id = conference_id_for(db, venue_id)
    offset = 0
    while max_pages is None or stats.pages < max_pages:
        notes = client.get_notes(
            invitation=f"{venue_id}/-/Submission",
            details="replies",
            sort="number:asc",
            limit=page_size,
            offset=offset,
        )
        if not notes:
            break
        # Note.to_json() leaves out the submission number.
        page = [
            ({**note.to_json(), "number": note.number}, note.details["replies"])
            for note in notes
        ]
        parsed = parse_page(page, venue_id, conference_id, stats)
        stats.pages += 1
        if not dry_run:
            with db_manager.session_local() as db:
                write_page(db, parsed, stats)
                db.commit()
        logger.info(
            "%s page %d: %d submissions, %d notes",
            venue_id,
            stats.pages,
            len(parsed.submissions),
            len(parsed.notes),
        )
        if len(notes) < page_size:
            break
        offset += page_size
        time.sleep(pause_seconds)
    if not dry_run:
        with db_manager.session_local() as db:
            stats.linked_papers = link_papers(db, venue_id)
            db.commit()
    return {
        "venue_id": venue_id,
        "conference_id": conference_id,
        **stats.as_json(),
        "seconds": round(time.monotonic() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--venue",
        action="append",
        dest="venues",
        help="OpenReview venue id; repeatable (default: ICLR.cc/2027/Conference)",
    )
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--pause-seconds", type=float, default=0.5)
    parser.add_argument(
        "--dry-run", action="store_true", help="fetch and parse, write nothing"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    settings = get_settings()
    if not settings.openreview_username or not settings.openreview_password:
        raise SystemExit(
            "PWC_OPENREVIEW_USERNAME / PWC_OPENREVIEW_PASSWORD are not set"
        )
    client = openreview.api.OpenReviewClient(
        baseurl=API_URL,
        username=settings.openreview_username,
        password=settings.openreview_password,
    )
    summaries = [
        import_venue(
            client,
            venue_id,
            page_size=args.page_size,
            max_pages=args.max_pages,
            pause_seconds=args.pause_seconds,
            dry_run=args.dry_run,
        )
        for venue_id in args.venues or DEFAULT_VENUES
    ]
    print(json.dumps({"dry_run": args.dry_run, "venues": summaries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
