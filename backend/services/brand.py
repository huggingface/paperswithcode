"""Papers with Code brand for server-rendered visuals (Pillow).

The single source for colors, fonts, and the logo in generated images: X
cards, OG images, and anything else drawn on the server. Values mirror the
website's tokens in `frontend/src/styles.css` (oklch accents converted to
sRGB hex); the guidelines live in the `pwc-brand` agent skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
DOMAIN = "paperswithcode.co"
NAME = "Papers with Code"

RGB = tuple[int, int, int]


def _hex(value: str) -> RGB:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


@dataclass(frozen=True)
class Palette:
    bg: RGB
    bg_elevated: RGB
    bg_subtle: RGB
    ink: RGB
    ink_soft: RGB
    ink_faint: RGB
    hairline: RGB
    hairline_strong: RGB
    accent: RGB
    accent_soft: RGB
    accent_text: RGB
    highlight_bg: RGB
    highlight_text: RGB


LIGHT = Palette(
    bg=_hex("#FAF8F4"),
    bg_elevated=_hex("#FFFFFF"),
    bg_subtle=_hex("#F2EFE8"),
    ink=_hex("#1A1814"),
    ink_soft=_hex("#5A554C"),
    ink_faint=_hex("#8E8678"),
    hairline=_hex("#E4DFD4"),
    hairline_strong=_hex("#C8C2B3"),
    accent=_hex("#305880"),  # oklch(0.45 0.08 250)
    accent_soft=_hex("#D6E7F8"),  # oklch(0.92 0.03 250)
    accent_text=_hex("#003C6C"),  # oklch(0.35 0.10 250)
    highlight_bg=_hex("#FFF1D9"),  # oklch(0.97 0.04 70)
    highlight_text=_hex("#733D00"),  # oklch(0.42 0.10 60)
)

DARK = Palette(
    bg=_hex("#11100E"),
    bg_elevated=_hex("#1A1815"),
    bg_subtle=_hex("#24211D"),
    ink=_hex("#F3EFE7"),
    ink_soft=_hex("#B9B2A6"),
    ink_faint=_hex("#989084"),
    hairline=_hex("#332F29"),
    hairline_strong=_hex("#514A40"),
    accent=_hex("#79A9DB"),  # oklch(0.72 0.09 250)
    accent_soft=_hex("#192A3C"),  # oklch(0.28 0.04 250)
    accent_text=_hex("#97C2F0"),  # oklch(0.80 0.08 250)
    highlight_bg=_hex("#33230F"),  # oklch(0.27 0.04 70)
    highlight_text=_hex("#EEB97B"),  # oklch(0.82 0.10 70)
)

FAMILIES = {
    "serif": "Newsreader.ttf",  # headings, titles, wordmark
    "serif-italic": "Newsreader-Italic.ttf",  # "with Code", ranks, emphasis
    "sans": "Inter.ttf",  # body text and subtitles
    "mono": "JetBrainsMono.ttf",  # eyebrows, labels, numbers, domain
}


@lru_cache(maxsize=128)
def font(family: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """A brand font at `size` px and `weight`; optical size follows the size."""
    loaded = ImageFont.truetype(str(FONT_DIR / FAMILIES[family]), size=size)
    values = []
    for axis in loaded.get_variation_axes():
        name = (
            axis["name"].decode().lower()
            if isinstance(axis["name"], bytes)
            else axis["name"].lower()
        )
        target = weight if name == "weight" else size
        values.append(max(axis["minimum"], min(axis["maximum"], target)))
    loaded.set_variation_by_axes(values)
    return loaded


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    fill: RGB,
    tracking: float,
) -> float:
    """Draw letter-spaced text (tracking in em, e.g. 0.1); return its width."""
    x, y = xy
    gap = tracking * font.size
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + gap
    return x - xy[0] - gap


def tracked_length(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    tracking: float,
) -> float:
    gap = tracking * font.size
    return sum(draw.textlength(char, font=font) for char in text) + gap * (
        len(text) - 1
    )


def draw_mark(
    draw: ImageDraw.ImageDraw, xy: tuple[int, int], size: int, palette: Palette = LIGHT
) -> None:
    """The logo mark: three nested squares (ink, paper, ink), square corners."""
    x, y = xy
    unit = size / 32
    draw.rectangle((x, y, x + size - 1, y + size - 1), fill=palette.ink)
    draw.rectangle(
        (x + 6 * unit, y + 6 * unit, x + 26 * unit - 1, y + 26 * unit - 1),
        fill=palette.bg,
    )
    draw.rectangle(
        (x + 12 * unit, y + 12 * unit, x + 20 * unit - 1, y + 20 * unit - 1),
        fill=palette.ink,
    )


def draw_wordmark(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    size: int,
    palette: Palette = LIGHT,
    *,
    with_mark: bool = True,
) -> float:
    """Mark + "Papers" (serif 600, ink) + "with Code" (serif italic, ink soft).

    Returns the total width. `size` is the font size; the mark is ~1.1x it.
    """
    x, y = xy
    start = x
    if with_mark:
        mark = round(size * 1.1)
        draw_mark(draw, (x, y + round(size * 0.12)), mark, palette)
        x += mark + round(size * 0.5)
    upright = font("serif", size, 600)
    italic = font("serif-italic", size, 400)
    draw.text((x, y), "Papers", font=upright, fill=palette.ink)
    x += draw.textlength("Papers ", font=upright)
    draw.text((x, y), "with Code", font=italic, fill=palette.ink_soft)
    x += draw.textlength("with Code", font=italic)
    return x - start


def fit_text(
    draw: ImageDraw.ImageDraw, text: str, font_: ImageFont.FreeTypeFont, width: float
) -> str:
    """Shorten `text` with an ellipsis until it fits `width` pixels."""
    if draw.textlength(text, font=font_) <= width:
        return text
    while text and draw.textlength(text + "…", font=font_) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_: ImageFont.FreeTypeFont,
    width: float,
    max_lines: int,
) -> list[str]:
    """Greedy word wrap into at most `max_lines`, ellipsizing the last line."""
    lines: list[str] = []
    for word in text.split():
        if lines and draw.textlength(f"{lines[-1]} {word}", font=font_) <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit_text(draw, lines[-1] + " …", font_, width)
    return [fit_text(draw, line, font_, width) for line in lines]


@dataclass
class Frame:
    """A branded canvas; draw content between `top` and `bottom`."""

    image: Image.Image
    draw: ImageDraw.ImageDraw
    scale: float
    margin: int
    top: int
    bottom: int

    def px(self, value: float) -> int:
        """A size from the 1200x675 reference scale, scaled to this canvas."""
        return round(value * self.scale)


def frame(
    size: tuple[int, int],
    *,
    title: str,
    subtitle: str = "",
    eyebrow: str = "",
    palette: Palette = LIGHT,
    title_size: int = 52,
    title_lines: int = 2,
) -> Frame:
    """Paper canvas with the standard header and footer.

    Header: mono eyebrow, Newsreader title (wrapped), Inter subtitle, hairline.
    Footer: hairline, wordmark left, domain right. Sizes are given on the
    1200x675 reference scale and scale with the canvas area (x1.2 on
    1080x1080, x0.97 on 1200x630); use `Frame.px` for your own sizes.
    """
    width, height = size
    scale = (width * height / (1200 * 675)) ** 0.5  # 1.0 on X cards, 1.2 square
    image = Image.new("RGB", size, palette.bg)
    draw = ImageDraw.Draw(image)
    margin = round(72 * scale)

    def px(value: float) -> int:
        return round(value * scale)

    y = px(56)
    if eyebrow:
        draw_tracked(
            draw,
            (margin, y),
            eyebrow.upper(),
            font=font("mono", px(17), 500),
            fill=palette.ink_faint,
            tracking=0.12,
        )
        y += px(38)
    title_font = font("serif", px(title_size), 500)
    for line in wrap_text(draw, title, title_font, width - 2 * margin, title_lines):
        draw.text((margin, y), line, font=title_font, fill=palette.ink)
        y += round(title_font.size * 1.15)
    if subtitle:
        subtitle_font = font("sans", px(23))
        for line in wrap_text(draw, subtitle, subtitle_font, width - 2 * margin, 2):
            draw.text(
                (margin, y + px(6)), line, font=subtitle_font, fill=palette.ink_soft
            )
            y += round(subtitle_font.size * 1.4)
        y += px(22)
    else:
        y += px(12)
    draw.line((margin, y, width - margin, y), fill=palette.hairline, width=1)

    footer_y = height - px(84)
    draw.line(
        (margin, footer_y, width - margin, footer_y), fill=palette.hairline, width=1
    )
    draw_wordmark(draw, (margin, footer_y + px(24)), px(26), palette)
    domain_font = font("mono", px(18), 400)
    domain_width = tracked_length(draw, DOMAIN, font=domain_font, tracking=0.02)
    draw_tracked(
        draw,
        (width - margin - domain_width, footer_y + px(32)),
        DOMAIN,
        font=domain_font,
        fill=palette.ink_faint,
        tracking=0.02,
    )
    return Frame(image, draw, scale, margin, y + px(28), footer_y - px(24))
