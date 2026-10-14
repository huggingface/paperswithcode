"""Allowlisted weekly digests with hourly bounded retry opportunities.

Operators can review the email before launch without touching the outbox:
  pwc-cron send_research_digests --preview <hf-username> [--html]
  pwc-cron send_research_digests --test-to <hf-username>
--test-to sends one sample only to that account's own opted-in address.
"""

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from backend.database.connection import db_manager
from backend.models.database.research import ResearchSubscription
from backend.services.research_delivery_service import (
    delivery_ready,
    sample_digest,
    send_test_digest,
    subject_for_username,
    weekly_window,
    prepare_digest,
    deliver_digest,
    expire_pending_digests,
)


def review(username: str, send: bool, show_html: bool) -> int:
    now = datetime.now(timezone.utc)
    with db_manager.session_local() as db:
        subject = subject_for_username(db, username)
        if subject is None:
            print(f"No account with username {username!r}.")
            return 1
        if send:
            print(send_test_digest(db, subject, now))
            return 0
        payload = sample_digest(db, subject, now)
    if payload is None:
        print(f"{username} has no research follows or email preference yet.")
        return 1
    print("Subject:", payload["subject"])
    print("To:", ", ".join(payload["to"]) or "(no verified email)")
    print()
    print(payload["html"] if show_html else payload["text"])
    return 0


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--preview", metavar="USERNAME")
    group.add_argument("--test-to", metavar="USERNAME")
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args(argv or [])
    if args.preview or args.test_to:
        raise SystemExit(
            review(args.preview or args.test_to, bool(args.test_to), args.html)
        )
    if not delivery_ready():
        print("Research digest delivery disabled; no messages prepared or sent.")
        return
    now = datetime.now(timezone.utc)
    with db_manager.session_local() as db:
        expired = expire_pending_digests(db, now)
    if expired:
        print(f"Closed {expired} research digests outside their retry window.")
    _, end = weekly_window(now)
    if now - end >= timedelta(hours=23):
        print("Outside weekly delivery/retry window; no work.")
        return
    counts = Counter()
    after = ""
    while True:
        with db_manager.session_local() as db:
            subjects = list(
                db.scalars(
                    select(ResearchSubscription.hf_subject)
                    .where(
                        ResearchSubscription.enabled,
                        ResearchSubscription.hf_subject > after,
                    )
                    .order_by(ResearchSubscription.hf_subject)
                    .limit(100)
                )
            )
        if not subjects:
            break
        for subject in subjects:
            with db_manager.session_local() as db:
                digest = prepare_digest(db, subject, now)
                if digest:
                    counts[
                        deliver_digest(db, subject, end, datetime.now(timezone.utc))
                    ] += 1
        after = subjects[-1]
    print("Research digest outcomes:", dict(counts))


if __name__ == "__main__":
    main(sys.argv[1:])
