"""Fill `paper_x_threads.video_url` for video posts linked before it existed.

Report-only unless --apply. Each distinct post is re-previewed once from X's
syndication endpoint; posts that are no longer available are skipped.
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import select, update

from backend.database.connection import get_database_session
from backend.models.database import PaperXThread
from backend.services.catalog_errors import CatalogValidationError
from backend.services.x_thread_service import fetch_x_post_preview

logger = logging.getLogger("backfill_x_thread_videos")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write video URLs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    session = get_database_session()
    db = next(session)
    try:
        tweet_ids = db.scalars(
            select(PaperXThread.tweet_id)
            .where(PaperXThread.media_type == "video")
            .where(PaperXThread.video_url.is_(None))
            .distinct()
        ).all()
        found = 0
        for tweet_id in tweet_ids:
            try:
                video_url = fetch_x_post_preview(tweet_id).video_url
            except CatalogValidationError as error:
                logger.info("skip %s: %s", tweet_id, error)
                continue
            if not video_url:
                continue
            found += 1
            if args.apply:
                db.execute(
                    update(PaperXThread)
                    .where(PaperXThread.tweet_id == tweet_id)
                    .values(video_url=video_url)
                )
                db.commit()
        logger.info(
            "%s video URLs for %d of %d posts",
            "Wrote" if args.apply else "Found",
            found,
            len(tweet_ids),
        )
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
