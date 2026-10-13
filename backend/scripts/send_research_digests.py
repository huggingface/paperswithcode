"""Allowlisted weekly digests with hourly bounded retry opportunities."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from backend.database.connection import db_manager
from backend.models.database.research import ResearchSubscription
from backend.services.research_delivery_service import (
    delivery_ready,
    weekly_window,
    prepare_digest,
    deliver_digest,
)


def main():
    if not delivery_ready():
        print("Research digest delivery disabled; no messages prepared or sent.")
        return
    now = datetime.now(timezone.utc)
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
    main()
