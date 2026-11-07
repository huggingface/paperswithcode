import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from backend.services.safe_outbound_http_service import (
    SafeFetchResult,
    SafeOutboundHttpError,
)
from backend.services.thumbnail_artwork import (
    CARD_HEIGHT,
    CARD_WIDTH,
    TRANSPARENT_BACKGROUND,
    compose_artwork_thumbnail,
    find_page_artwork_urls,
    load_artwork_image,
)
from backend.services.thumbnail_service import ThumbnailService, is_thumbnail_valid
from backend.utils.exceptions import ThumbnailGenerationError

PAGE_URL = "https://example.com/blog/model-launch"


def _png(size: tuple[int, int], color=(30, 60, 200, 255)) -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def _page(meta: str) -> bytes:
    return f"<html><head>{meta}</head><body>Hello</body></html>".encode()


def test_find_page_artwork_urls_orders_og_before_twitter_and_resolves_paths():
    html = """
      <meta name="twitter:image:alt" content="Content cover image">
      <meta name="twitter:image" content="https://cdn.example.com/twitter.png">
      <meta property="og:image" content="/images/cover.png?a=1&amp;b=2">
      <meta property="og:image" content="https://cdn.example.com/twitter.png">
    """

    assert find_page_artwork_urls(html, PAGE_URL) == [
        "https://example.com/images/cover.png?a=1&b=2",
        "https://cdn.example.com/twitter.png",
    ]


def test_find_page_artwork_urls_ignores_pages_without_images():
    assert find_page_artwork_urls("<title>No preview</title>", PAGE_URL) == []
    assert (
        find_page_artwork_urls('<meta property="og:image" content="data:x">', PAGE_URL)
        == []
    )


def test_find_page_artwork_urls_skips_site_logos_and_journal_covers():
    html = """
      <meta property="og:image" content="/static/browse/0.3.4/images/arxiv-logo-fb.png">
      <meta name="twitter:image"
        content="https://media.springernature.com/full/springer-static/cover-hires/journal/11263">
      <meta name="twitter:image:src"
        content="https://media.springernature.com/w153/springer-static/cover/book/978-3.jpg">
      <meta name="twitter:image:src" content="https://cdn.example.com/Fig1_HTML.png">
    """

    assert find_page_artwork_urls(html, PAGE_URL) == [
        "https://cdn.example.com/Fig1_HTML.png"
    ]


@pytest.mark.parametrize(
    "content",
    [
        _png((153, 230)),  # Springer proceedings cover thumbnail
        _png((1200, 300)),  # banner wider than the card can show
        _png((300, 1200)),  # very tall strip
        b"<html>not an image</html>",
    ],
)
def test_load_artwork_image_rejects_unusable_images(content: bytes):
    assert load_artwork_image(content) is None


def test_load_artwork_image_accepts_social_preview():
    image = load_artwork_image(_png((1200, 630)))

    assert image is not None
    assert image.size == (1200, 630)


def test_compose_artwork_thumbnail_fills_card_with_border_color():
    art = Image.new("RGBA", (1200, 630), (10, 20, 30, 255))

    card = compose_artwork_thumbnail(art)

    assert card.size == (CARD_WIDTH, CARD_HEIGHT)
    assert card.mode == "RGB"
    assert card.getpixel((5, 5)) == (10, 20, 30)


def test_compose_artwork_thumbnail_uses_neutral_background_for_transparent_art():
    art = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    art.paste((200, 0, 0, 255), (100, 100, 500, 500))

    card = compose_artwork_thumbnail(art)

    assert card.getpixel((5, 5)) == TRANSPARENT_BACKGROUND
    assert card.getpixel((CARD_WIDTH // 2, CARD_HEIGHT // 2)) == (200, 0, 0)


def _service(tmp_path: Path) -> ThumbnailService:
    service = ThumbnailService.__new__(ThumbnailService)
    service.max_pdf_size = 1_000_000
    service.pdf_timeout = 10
    service.thumbnail_width = CARD_WIDTH
    service.thumbnail_quality = 85
    service._read_archived_external_pdf = MagicMock(return_value=None)
    service.get_external_filename = lambda _paper_id: "external_42.jpg"
    service.get_existing_custom_thumbnail_path = MagicMock(return_value=None)
    service._get_active_cache_path = MagicMock(
        return_value=tmp_path / "external_42.jpg"
    )
    service._upload_to_bucket = MagicMock()
    service._render_external_metadata_thumbnail = MagicMock(
        return_value=Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), "white")
    )
    return service


def _install_fetch(monkeypatch, responses: dict[str, object]) -> list[str]:
    fetched: list[str] = []

    async def fetch(url, **_kwargs):
        fetched.append(url)
        response = responses[url]
        if isinstance(response, Exception):
            raise response
        return SafeFetchResult(url, 200, "text/html", response)

    monkeypatch.setattr(
        "backend.services.thumbnail_service.fetch_public_resource", fetch
    )
    return fetched


def _generate(service: ThumbnailService) -> Path:
    return asyncio.run(
        service.generate_external_thumbnail(42, PAGE_URL, title="Model Launch")
    )


def test_external_page_without_pdf_uses_social_artwork(tmp_path: Path, monkeypatch):
    service = _service(tmp_path)
    _install_fetch(
        monkeypatch,
        {
            PAGE_URL: _page(
                '<meta property="og:image" content="https://cdn.example.com/a.png">'
            ),
            "https://cdn.example.com/a.png": _png((1200, 630), (12, 34, 56, 255)),
        },
    )

    path = _generate(service)

    assert is_thumbnail_valid(path)
    with Image.open(path) as image:
        assert image.size == (CARD_WIDTH, CARD_HEIGHT)
        assert max(abs(a - b) for a, b in zip(image.getpixel((5, 5)), (12, 34, 56))) < 4
    service._render_external_metadata_thumbnail.assert_not_called()
    service._upload_to_bucket.assert_called_once_with(path, "external_42.jpg")


def test_unusable_first_artwork_falls_through_to_next_candidate(
    tmp_path: Path, monkeypatch
):
    service = _service(tmp_path)
    fetched = _install_fetch(
        monkeypatch,
        {
            PAGE_URL: _page(
                '<meta property="og:image" content="https://cdn.example.com/gone.png">'
                '<meta name="twitter:image" content="https://cdn.example.com/logo.png">'
                '<meta name="twitter:image:src" content="https://cdn.example.com/b.png">'
            ),
            "https://cdn.example.com/gone.png": SafeOutboundHttpError(
                502, "missing", origin_status_code=404
            ),
            "https://cdn.example.com/logo.png": _png((64, 64)),
            "https://cdn.example.com/b.png": _png((800, 800)),
        },
    )

    _generate(service)

    assert fetched[-1] == "https://cdn.example.com/b.png"
    service._render_external_metadata_thumbnail.assert_not_called()


@pytest.mark.parametrize(
    "page",
    [
        SafeOutboundHttpError(502, "bot wall", origin_status_code=403),
        SafeOutboundHttpError(415, "not html"),
        _page("<title>No preview image</title>"),
    ],
)
def test_page_without_usable_artwork_gets_title_card(tmp_path: Path, monkeypatch, page):
    service = _service(tmp_path)
    _install_fetch(monkeypatch, {PAGE_URL: page})

    _generate(service)

    service._render_external_metadata_thumbnail.assert_called_once_with(
        "Model Launch", PAGE_URL
    )


@pytest.mark.parametrize("failing", ["page", "artwork"])
@pytest.mark.parametrize("origin_status_code", [None, 429, 503])
def test_transient_artwork_failure_is_retried_instead_of_title_card(
    tmp_path: Path, monkeypatch, failing: str, origin_status_code: int | None
):
    service = _service(tmp_path)
    error = SafeOutboundHttpError(
        502, "unavailable", origin_status_code=origin_status_code
    )
    _install_fetch(
        monkeypatch,
        {
            PAGE_URL: error
            if failing == "page"
            else _page(
                '<meta property="og:image" content="https://cdn.example.com/a.png">'
            ),
            "https://cdn.example.com/a.png": error,
        },
    )

    with pytest.raises(ThumbnailGenerationError, match="temporarily unavailable"):
        _generate(service)

    service._render_external_metadata_thumbnail.assert_not_called()
    service._upload_to_bucket.assert_not_called()
