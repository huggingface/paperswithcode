"""Parse X (formerly Twitter) post URLs and capture link previews.

Previews come from X's public embed syndication endpoint, the same source the
official embed widget uses, so no API credentials are needed. They are stored
when a post is linked to a paper; paper pages never call X.
"""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import httpx

from backend.services.catalog_errors import CatalogValidationError

MAX_X_THREADS_PER_PAPER = 10
SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"

_POST_URL = re.compile(
    r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/"
    r"(?:(?P<handle>[A-Za-z0-9_]{1,15})|i/web|i)/status(?:es)?/(?P<id>\d{1,25})"
    r"(?:[/?#].*)?$"
)


@dataclass(frozen=True)
class XPostPreview:
    tweet_id: str
    url: str
    author_name: str
    author_handle: str
    author_avatar_url: str | None
    text: str
    posted_at: datetime | None
    like_count: int | None
    reply_count: int | None
    media_url: str | None
    media_type: str | None
    fetched_at: datetime


X_THREAD_FIELDS = (
    "tweet_id",
    "url",
    "author_name",
    "author_handle",
    "author_avatar_url",
    "text",
    "posted_at",
    "like_count",
    "reply_count",
    "media_url",
    "media_type",
    "fetched_at",
)


def parse_x_post_id(url: str) -> str:
    """Return the post ID of an x.com or twitter.com status URL."""
    match = _POST_URL.match((url or "").strip())
    if not match:
        raise CatalogValidationError(
            f"Not an X post URL: {url!r} (expected https://x.com/<user>/status/<id>)"
        )
    return match.group("id")


def _display_text(post: dict) -> str:
    text = post.get("text") or ""
    start, end = post.get("display_text_range") or (0, len(text))
    visible = text[start:end]
    # Swap t.co shortlinks for their destinations; media links fall outside
    # the display range and are rendered from mediaDetails instead.
    for entity in (post.get("entities") or {}).get("urls", []):
        if entity.get("url") and entity.get("expanded_url"):
            visible = visible.replace(entity["url"], entity["expanded_url"])
    return html.unescape(visible).strip()


def _media(post: dict) -> tuple[str | None, str | None]:
    for media in post.get("mediaDetails") or []:
        if media.get("media_url_https"):
            kind = "photo" if media.get("type") == "photo" else "video"
            return media["media_url_https"], kind
    return None, None


def _posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def preview_from_syndication(post: dict) -> XPostPreview:
    """Normalize one syndication `tweet-result` payload."""
    if post.get("__typename") != "Tweet" or not post.get("user"):
        raise CatalogValidationError(
            "This X post is unavailable (deleted, protected, or age-restricted)"
        )
    user = post["user"]
    tweet_id = post["id_str"]
    avatar = user.get("profile_image_url_https")
    media_url, media_type = _media(post)
    return XPostPreview(
        tweet_id=tweet_id,
        url=f"https://x.com/{user['screen_name']}/status/{tweet_id}",
        author_name=user.get("name") or user["screen_name"],
        author_handle=user["screen_name"],
        # `_normal` is 48 px; `_bigger` stays sharp on high-density screens.
        author_avatar_url=avatar.replace("_normal.", "_bigger.") if avatar else None,
        text=_display_text(post),
        posted_at=_posted_at(post.get("created_at")),
        like_count=post.get("favorite_count"),
        reply_count=post.get("conversation_count"),
        media_url=media_url,
        media_type=media_type,
        fetched_at=datetime.now(UTC),
    )


def fetch_x_post_row(tweet_id: str) -> dict:
    """Fetch a public X post preview as a `paper_x_threads` row."""
    return asdict(fetch_x_post_preview(tweet_id))


def fetch_x_post_preview(tweet_id: str) -> XPostPreview:
    """Fetch a public X post preview, raising a validation error if unavailable."""
    try:
        response = httpx.get(
            SYNDICATION_URL,
            params={"id": tweet_id, "lang": "en", "token": "a"},
            timeout=10,
        )
    except httpx.HTTPError as error:
        raise CatalogValidationError(
            f"Could not reach X to preview post {tweet_id}: {error}"
        ) from error
    if response.status_code == 404 or not response.headers.get(
        "content-type", ""
    ).startswith("application/json"):
        raise CatalogValidationError(f"X post {tweet_id} was not found")
    if response.status_code != 200:
        raise CatalogValidationError(
            f"X returned HTTP {response.status_code} for post {tweet_id}"
        )
    return preview_from_syndication(response.json())
