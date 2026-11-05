"""Production entrypoint for posting a trending paper to X.

Posts a top trending recent arXiv paper that has a TL;DR, was never posted,
and is worth posting: a clear Papers with Code SOTA, or a well-known lab whose
official X account is known. A SOTA post states the result against the
previous best; otherwise Luna writes the post (PWC_OPENAI_API_KEY), falling
back to a template, and either has to open with a comparison or a claim. When
no candidate qualifies the slot is skipped, and `skipped` in the printed
summary gives each reason. The first PDF page is the image, and a reply
carries the paper page link. Needs the posting account's
OAuth 1.0a keys (X_POST_CONSUMER_KEY, X_POST_CONSUMER_SECRET,
X_POST_ACCESS_TOKEN, X_POST_ACCESS_TOKEN_SECRET); without them, or with
--dry-run, it only prints the post it would make.

PWC_X_POST_MAX_CHARS caps the post length (default 280; raise it when the
account has X Premium long posts).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import httpx

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.services.paper_pdf_text_service import _download_arxiv_pdf
from backend.services.x_trending_post_service import (
    XCredentials,
    XPoster,
    post_trending_paper,
    write_with_luna,
)

logger = logging.getLogger("post_trending_paper_to_x")
CREDENTIAL_KEYS = (
    "X_POST_CONSUMER_KEY",
    "X_POST_CONSUMER_SECRET",
    "X_POST_ACCESS_TOKEN",
    "X_POST_ACCESS_TOKEN_SECRET",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the post without posting"
    )
    parser.add_argument(
        "--save-image", type=Path, help="Write the rendered first page to this path"
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
        logger.warning("x_trending_post_skipped X_POST_* credentials are not set")

    def write(draft):
        if not api_key:
            return draft.template(max_chars)
        return write_with_luna(client, draft, api_key=api_key, max_chars=max_chars)

    session = get_database_session()
    db = next(session)
    try:
        report = post_trending_paper(
            db,
            poster=poster,
            fetch_pdf=lambda paper: _download_arxiv_pdf(paper.arxiv_id, paper.version),
            max_chars=max_chars,
            write=write,
            save_image=args.save_image.write_bytes if args.save_image else None,
        )
    finally:
        client.close()
        try:
            next(session)
        except StopIteration:
            pass
    summary = report.to_dict()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    for error in summary["errors"]:
        logger.warning("x_trending_post_error %s", json.dumps(error))
    # Candidates existed but none could be rendered.
    return 1 if summary["errors"] and summary["paper_id"] is None else 0


if __name__ == "__main__":
    raise SystemExit(main())
