from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.models.database import PaperXThread
from backend.services import x_thread_service
from backend.services.catalog_errors import CatalogValidationError
from backend.services.paper_association_service import PaperAssociationService
from backend.services.pending_edit_errors import PendingEditError
from backend.services.pending_edit_payloads import payload_is_noop, validate_payload
from backend.services.x_thread_service import (
    X_THREAD_FIELDS,
    parse_x_post_id,
    preview_from_syndication,
)

TEXT = (
    "Introducing RoboJEPA &amp; friends.\n\nCode: https://t.co/Dk9zq7zN1k "
    "https://t.co/HVb4W0Ahkg"
)
POST = {
    "__typename": "Tweet",
    "id_str": "2108983104178213096",
    "created_at": "2026-10-10T18:08:49.000Z",
    "favorite_count": 729,
    "conversation_count": 34,
    # X ends the display range before the trailing media shortlink.
    "display_text_range": [0, TEXT.index(" https://t.co/HVb")],
    "text": TEXT,
    "entities": {
        "urls": [
            {
                "url": "https://t.co/Dk9zq7zN1k",
                "expanded_url": "https://robojepa.github.io",
            }
        ]
    },
    "user": {
        "name": "Artem Zholus",
        "screen_name": "artemZholus",
        "profile_image_url_https": "https://pbs.twimg.com/profile_images/1/a_normal.jpg",
    },
    "mediaDetails": [
        {
            "type": "video",
            "media_url_https": "https://pbs.twimg.com/amplify_video_thumb/1/img/x.jpg",
        }
    ],
}


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/artemZholus/status/2108983104178213096",
        "https://twitter.com/artemZholus/status/2108983104178213096?s=20",
        "https://mobile.twitter.com/artemZholus/status/2108983104178213096/photo/1",
        "http://www.x.com/i/web/status/2108983104178213096",
        "  https://x.com/artemZholus/statuses/2108983104178213096#reply  ",
    ],
)
def test_parse_x_post_id_accepts_status_urls(url):
    assert parse_x_post_id(url) == "2108983104178213096"


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/artemZholus",
        "https://example.com/artemZholus/status/2108983104178213096",
        "https://x.com.evil.example/a/status/1",
        "2108983104178213096",
    ],
)
def test_parse_x_post_id_rejects_other_urls(url):
    with pytest.raises(CatalogValidationError):
        parse_x_post_id(url)


def test_preview_expands_links_and_drops_media_shortlink():
    preview = preview_from_syndication(POST)

    assert preview.url == "https://x.com/artemZholus/status/2108983104178213096"
    assert preview.text == (
        "Introducing RoboJEPA & friends.\n\nCode: https://robojepa.github.io"
    )
    assert preview.author_avatar_url.endswith("/a_bigger.jpg")
    assert preview.posted_at == datetime(2026, 10, 10, 18, 8, 49, tzinfo=UTC)
    assert (preview.like_count, preview.reply_count) == (729, 34)
    assert preview.media_type == "video"


def test_unavailable_post_is_rejected():
    with pytest.raises(CatalogValidationError, match="unavailable"):
        preview_from_syndication({"__typename": "TweetTombstone"})


def test_pending_edit_payload_validates_and_detects_noop():
    url = "https://x.com/artemZholus/status/2108983104178213096"
    assert validate_payload("x_threads", {"x_threads": [f" {url} "]}) == {
        "x_threads": [url]
    }
    with pytest.raises(PendingEditError):
        validate_payload("x_threads", {"x_threads": ["https://x.com/someone"]})
    assert payload_is_noop(
        "x_threads",
        {"x_threads": ["https://twitter.com/a/status/2108983104178213096"]},
        {"x_threads": [{"url": url}]},
    )


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def delete(self):
        self.rows.clear()

    def __iter__(self):
        return iter(list(self.rows))


class _Session:
    def __init__(self, paper, threads):
        self.paper = paper
        self.threads = threads
        self.added = []

    def query(self, model):
        return _Query(self.threads if model is PaperXThread else [self.paper])

    def add(self, row):
        self.added.append(row)

    def flush(self):
        pass


def _row(tweet_id: str, **overrides) -> dict:
    return {
        field: overrides.get(field, f"{field}-{tweet_id}") for field in X_THREAD_FIELDS
    } | {"tweet_id": tweet_id}


def test_update_reuses_stored_previews_and_fetches_only_new_posts(monkeypatch):
    stored = SimpleNamespace(**_row("111", author_name="Stored"))
    db = _Session(SimpleNamespace(id=1), [stored])
    fetch = Mock(side_effect=lambda tweet_id: _row(tweet_id, author_name="Fresh"))
    monkeypatch.setattr(x_thread_service, "fetch_x_post_row", fetch)

    PaperAssociationService(db, Mock()).update_x_threads(
        1,
        [
            "https://x.com/b/status/222",
            "https://x.com/a/status/111",
            "https://twitter.com/b/status/222",
        ],
        commit=False,
    )

    fetch.assert_called_once_with("222")
    assert [(row.tweet_id, row.position, row.author_name) for row in db.added] == [
        ("222", 0, "Fresh"),
        ("111", 1, "Stored"),
    ]


def test_update_rejects_more_than_ten_threads(monkeypatch):
    db = _Session(SimpleNamespace(id=1), [])
    monkeypatch.setattr(x_thread_service, "fetch_x_post_row", Mock())

    with pytest.raises(CatalogValidationError, match="at most 10"):
        PaperAssociationService(db, Mock()).update_x_threads(
            1, [f"https://x.com/a/status/{i}" for i in range(11)], commit=False
        )
