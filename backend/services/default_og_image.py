"""
Render the static default Open Graph image used when a paper has no
thumbnail on disk yet.

The image is rendered lazily on first request and cached in memory because:
  - It only depends on the brand (see backend/services/brand.py and the
    `pwc-brand` skill); nothing changes per request.
  - Generating it at runtime means we don't have to commit a binary asset.
  - Pillow is already a dependency of the thumbnail pipeline.

It mirrors the site's own og-image.png: the mark, the wordmark, and the
tagline, centred on paper.
"""

from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageDraw

from backend.services.brand import DOMAIN, LIGHT, draw_mark, draw_tracked, font
from backend.services.brand import tracked_length

_OG_WIDTH = 1200
_OG_HEIGHT = 630
_TAGLINE = "Trending AI research papers with code, datasets, and leaderboards."

_cached_png: Optional[bytes] = None


def _render() -> bytes:
    palette = LIGHT
    image = Image.new("RGB", (_OG_WIDTH, _OG_HEIGHT), palette.bg)
    draw = ImageDraw.Draw(image)
    centre = _OG_WIDTH // 2

    mark = 112
    draw_mark(draw, (centre - mark // 2, 128), mark, palette)

    upright = font("serif", 92, 600)
    italic = font("serif-italic", 92, 400)
    word, rest = "Papers ", "with Code"
    width = draw.textlength(word, font=upright) + draw.textlength(rest, font=italic)
    x = centre - width / 2
    draw.text((x, 282), word, font=upright, fill=palette.ink)
    x += draw.textlength(word, font=upright)
    draw.text((x, 282), rest, font=italic, fill=palette.ink_soft)

    tagline = font("sans", 30)
    tagline_width = draw.textlength(_TAGLINE, font=tagline)
    draw.text(
        (centre - tagline_width / 2, 418), _TAGLINE, font=tagline, fill=palette.ink_soft
    )

    domain = font("mono", 22, 500)
    domain_width = tracked_length(draw, DOMAIN, font=domain, tracking=0.08)
    draw_tracked(
        draw,
        (centre - domain_width / 2, 530),
        DOMAIN,
        font=domain,
        fill=palette.ink_faint,
        tracking=0.08,
    )

    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def get_default_og_image_bytes() -> bytes:
    """Return the cached PNG bytes for the default OG image, generating on first call."""
    global _cached_png
    if _cached_png is None:
        _cached_png = _render()
    return _cached_png
