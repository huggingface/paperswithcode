"""Production entrypoint for Papers with Code insight posts on X.

Twice a day, posts one insight to the Papers with Code X account: the top
trending papers of the week (Mondays) or month (the 1st), a new SOTA, or the
fastest-growing benchmark, method, or task (see x_insight_post_service). The
text is Luna's rewrite of a fixed template (PWC_OPENAI_API_KEY), kept only
when every number matches; otherwise the template is posted.

Uses the same X_POST_* OAuth 1.0a keys and PWC_X_POST_MAX_CHARS as
post_trending_paper_to_x; without the keys, or with --dry-run, it only prints
the post it would make.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.x_insight_post_service import (
    KINDS,
    plan_kinds,
    post_insight,
    write_with_luna,
)
from backend.services.x_trending_post_service import XCredentials, XPoster

logger = logging.getLogger("post_x_insight")
CREDENTIAL_KEYS = (
    "X_POST_CONSUMER_KEY",
    "X_POST_CONSUMER_SECRET",
    "X_POST_ACCESS_TOKEN",
    "X_POST_ACCESS_TOKEN_SECRET",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kind", choices=KINDS, action="append", help="Try only these kinds, in order"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the post without posting"
    )
    parser.add_argument(
        "--save-image", type=Path, help="Write the chart card to this path"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    max_chars = int(os.environ.get("PWC_X_POST_MAX_CHARS") or 280)
    api_key = get_settings().openai_api_key

    keys = [os.environ.get(key, "") for key in CREDENTIAL_KEYS]
    client = httpx.Client(timeout=60)
    poster = None
    if args.dry_run:
        pass
    elif all(keys):
        poster = XPoster(XCredentials(*keys), client)
    else:
        logger.warning("x_insight_post_skipped X_POST_* credentials are not set")

    def write(insight):
        if not api_key:
            return insight.text
        return write_with_luna(client, insight, api_key=api_key, max_chars=max_chars)

    session = get_database_session()
    db = next(session)
    try:
        report = post_insight(
            db,
            poster=poster,
            kinds=args.kind or plan_kinds(db, datetime.now(UTC)),
            write=write,
            max_chars=max_chars,
            save_image=args.save_image.write_bytes if args.save_image else None,
        )
    finally:
        client.close()
        try:
            next(session)
        except StopIteration:
            pass
    print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
