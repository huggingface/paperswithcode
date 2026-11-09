"""Candidates and posting records for the Papers with Code X agent.

The agent that writes the X account's posts runs off the catalog host's
release tree and calls this through `pwc-cron x_post_candidates`:

    pwc-cron x_post_candidates list
        One JSON object on stdout: {"generated_at", "candidates": [...]}.
        Each candidate has kind, subject_key, draft, link, facts, score,
        screenshot_url, and image_png_base64 (a chart card, or null).

    pwc-cron x_post_candidates record --kind new_sota --subject-key K \
        --post-id 123 [--reply-id 456]
        Records a posted subject in x_insight_posts so it is never offered
        again.

See backend/services/x_post_candidates.py for what each kind means.
"""

from __future__ import annotations

import argparse
import base64
import json
from datetime import UTC, datetime

from backend.database.connection import get_database_session
from backend.services.x_post_candidates import KINDS, gather, record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Print every candidate as JSON")
    record_parser = commands.add_parser("record", help="Record a posted subject")
    record_parser.add_argument("--kind", choices=KINDS, required=True)
    record_parser.add_argument("--subject-key", required=True)
    record_parser.add_argument("--post-id", required=True)
    record_parser.add_argument("--reply-id")
    args = parser.parse_args()

    session = get_database_session()
    db = next(session)
    try:
        if args.command == "list":
            now = datetime.now(UTC)
            candidates = []
            for candidate in gather(db, now=now):
                item = candidate.to_dict()
                item["image_png_base64"] = (
                    base64.b64encode(candidate.image).decode()
                    if candidate.image
                    else None
                )
                candidates.append(item)
            output = {"generated_at": now.isoformat(), "candidates": candidates}
        else:
            row = record(
                db,
                kind=args.kind,
                subject_key=args.subject_key,
                post_id=args.post_id,
                reply_id=args.reply_id,
            )
            output = {
                "recorded": row.id,
                "kind": row.kind,
                "subject_key": row.subject_key,
            }
    finally:
        try:
            next(session)
        except StopIteration:
            pass
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
