"""
Source-page artwork for external paper thumbnails.

Blog posts, model cards, and release pages rarely ship a PDF, but nearly all
publish a social preview image (`og:image` / `twitter:image`). These helpers
find that image in the page HTML and compose it onto a portrait paper card,
so a page without a PDF still gets a recognizable thumbnail instead of a
white title card.
"""

import re
from io import BytesIO
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError

CARD_WIDTH = 400
CARD_HEIGHT = 550
# The artwork is contained (never cropped) inside this box, centered on the card.
ARTWORK_BOX = (360, 430)
# Smaller images are favicons, logos, or tiny book covers (Springer serves a
# 153 px proceedings cover); they would look worse than a title card.
MIN_ARTWORK_WIDTH = 200
MIN_ARTWORK_HEIGHT = 100
# Wider banners become an unreadable strip on a portrait card.
MAX_ARTWORK_ASPECT = 2.6
MIN_ARTWORK_ASPECT = 1 / 3
MAX_ARTWORK_PIXELS = 40_000_000
TRANSPARENT_BACKGROUND = (248, 247, 251)

# Site-wide images that say nothing about the paper: publisher/site logos
# (arXiv's `arxiv-logo-fb.png`) and Springer journal or book covers.
GENERIC_ARTWORK_PATH = re.compile(r"logo|/cover(?:-hires)?/(?:journal|book)/", re.I)

ARTWORK_META_KEYS = (
    "og:image:secure_url",
    "og:image",
    "og:image:url",
    "twitter:image",
    "twitter:image:src",
)


def find_page_artwork_urls(html: str, page_url: str) -> list[str]:
    """Return the page's declared social preview image URLs, best first."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, list[str]] = {key: [] for key in ARTWORK_META_KEYS}
    for meta in soup.find_all("meta"):
        key = (meta.get("property") or meta.get("name") or "").strip().lower()
        content = (meta.get("content") or "").strip()
        if key in found and content:
            found[key].append(content)

    urls: list[str] = []
    for key in ARTWORK_META_KEYS:
        for content in found[key]:
            url = urljoin(page_url, content)
            parsed = urlsplit(url)
            if (
                parsed.scheme in {"http", "https"}
                and not GENERIC_ARTWORK_PATH.search(parsed.path)
                and url not in urls
            ):
                urls.append(url)
    return urls


def load_artwork_image(content: bytes) -> Image.Image | None:
    """Decode a downloaded image, or return None when it is unusable as artwork."""
    try:
        image = Image.open(BytesIO(content))
    except UnidentifiedImageError:
        return None
    width, height = image.size
    if width * height > MAX_ARTWORK_PIXELS:
        return None
    if width < MIN_ARTWORK_WIDTH or height < MIN_ARTWORK_HEIGHT:
        return None
    if not MIN_ARTWORK_ASPECT <= width / height <= MAX_ARTWORK_ASPECT:
        return None
    try:
        image.seek(0)
        return image.convert("RGBA")
    except OSError:
        return None


def _background_color(art: Image.Image) -> tuple[int, int, int]:
    """Use the artwork's mean border color so the card reads as one canvas."""
    width, height = art.size
    border = [
        art.crop((0, 0, width, 1)),
        art.crop((0, height - 1, width, height)),
        art.crop((0, 0, 1, height)),
        art.crop((width - 1, 0, width, height)),
    ]
    pixels = [pixel for strip in border for pixel in strip.get_flattened_data()]
    opaque = [pixel for pixel in pixels if pixel[3] >= 250]
    if len(opaque) < len(pixels) * 0.9:
        return TRANSPARENT_BACKGROUND
    return tuple(
        round(sum(pixel[i] for pixel in opaque) / len(opaque)) for i in range(3)
    )


def compose_artwork_thumbnail(art: Image.Image) -> Image.Image:
    """Place source artwork, uncropped, on a 400×550 portrait card."""
    art = art.convert("RGBA")
    scale = min(ARTWORK_BOX[0] / art.width, ARTWORK_BOX[1] / art.height)
    resized = art.resize(
        (max(1, round(art.width * scale)), max(1, round(art.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), _background_color(art))
    canvas.alpha_composite(
        resized,
        ((CARD_WIDTH - resized.width) // 2, (CARD_HEIGHT - resized.height) // 2),
    )
    return canvas.convert("RGB")
