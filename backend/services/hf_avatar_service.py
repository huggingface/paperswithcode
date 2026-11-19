"""Hugging Face avatars for the homepage topic cards, fetched server-side and cached.

``huggingface.co/api/users/<name>/avatar?redirect=true`` works as an ``<img>``
source on most pages, but some browsers get HTTP 503 for every huggingface.co
image from other origins (seen on staging). The cards therefore load the few
featured followers' avatars from our own origin.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import httpx

AVATAR_API = "https://huggingface.co/api/users/{}/avatar"
HF_ORIGIN = "https://huggingface.co"
CACHE_SECONDS = 24 * 60 * 60
TIMEOUT_SECONDS = 2.0
MAX_IMAGE_BYTES = 512 * 1024
MAX_CACHED_IMAGES = 500
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml")

# username -> (expires at, image URL); only successful lookups are kept.
_cache: dict[str, tuple[float, str]] = {}
# username -> (expires at, content type, bytes)
_images: dict[str, tuple[float, str, bytes]] = {}


def avatar_urls(usernames: list[str]) -> dict[str, str]:
    """Image URLs for the usernames HF resolved; others are left out."""
    now = time.monotonic()
    missing = sorted(
        {name for name in usernames if _cache.get(name, (0.0, ""))[0] <= now}
    )
    if missing:
        with (
            httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client,
            ThreadPoolExecutor(max_workers=len(missing)) as pool,
        ):
            found = pool.map(lambda name: fetch_avatar_url(client, name), missing)
            for name, url in zip(missing, found):
                if url:
                    _cache[name] = (now + CACHE_SECONDS, url)
    return {name: _cache[name][1] for name in usernames if name in _cache}


def fetch_avatar_url(client: httpx.Client, username: str) -> str | None:
    try:
        response = client.get(AVATAR_API.format(quote(username, safe="")))
        response.raise_for_status()
        url = response.json().get("avatarUrl")
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(url, str):
        return None
    if url.startswith("/"):
        return HF_ORIGIN + url
    return url if url.startswith("https://") else None


def avatar_image(username: str) -> tuple[str, bytes] | None:
    """The avatar's content type and bytes, or None when HF has none to give."""
    now = time.monotonic()
    cached = _images.get(username)
    if cached and cached[0] > now:
        return cached[1], cached[2]
    url = avatar_urls([username]).get(username)
    if url is None:
        return None
    try:
        response = httpx.get(url, timeout=TIMEOUT_SECONDS, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    if content_type not in IMAGE_TYPES or len(response.content) > MAX_IMAGE_BYTES:
        return None
    if len(_images) >= MAX_CACHED_IMAGES:
        _images.clear()
    _images[username] = (now + CACHE_SECONDS, content_type, response.content)
    return content_type, response.content
