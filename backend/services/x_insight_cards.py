"""Image cards attached to Papers with Code insight posts on X.

Two layouts, both 1200x675 (X's 16:9 preview): a horizontal bar chart for
leaderboards and trend scores, and a ranked list for top papers.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

from backend.services.default_og_image import _load_font

WIDTH, HEIGHT = 1200, 675
MARGIN = 64
BACKGROUND = (250, 248, 244)
INK = (26, 24, 20)
MUTED = (110, 100, 88)
BAR = (214, 206, 194)
ACCENT = (220, 86, 47)
DOMAIN = "paperswithcode.co"


@dataclass(frozen=True)
class Bar:
    label: str
    value: float
    value_label: str
    highlight: bool = False


def _fit(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    """Shorten `text` with an ellipsis until it fits `width` pixels."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(draw, text: str, font, width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and draw.textlength(f"{lines[-1]} {word}", font=font) <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit(draw, lines[-1] + " …", font, width)
    return [_fit(draw, line, font, width) for line in lines]


def _frame(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 10), fill=ACCENT)
    title_font = _load_font(44, "bold")
    y = 48
    for line in _wrap(draw, title, title_font, WIDTH - 2 * MARGIN, 2):
        draw.text((MARGIN, y), line, font=title_font, fill=INK)
        y += 54
    draw.text((MARGIN, y + 4), subtitle, font=_load_font(26), fill=MUTED)
    footer = _load_font(24, "bold")
    draw.text((MARGIN, HEIGHT - 52), "Papers with Code", font=footer, fill=INK)
    width = draw.textlength(DOMAIN, font=_load_font(24))
    draw.text(
        (WIDTH - MARGIN - width, HEIGHT - 52), DOMAIN, font=_load_font(24), fill=MUTED
    )
    return image, draw, y + 64


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_bar_card(
    title: str, subtitle: str, bars: list[Bar], *, lower_is_better: bool = False
) -> bytes:
    """Horizontal bars, best first; bar length is relative to the best value."""
    image, draw, top = _frame(title, subtitle)
    label_font = _load_font(26)
    value_font = _load_font(26, "bold")
    label_width = 380
    value_width = 200
    bar_left = MARGIN + label_width + 16
    bar_span = WIDTH - MARGIN - value_width - bar_left
    values = [bar.value for bar in bars]
    low, high = min(values + [0.0]), max(values)
    row = min(64, (HEIGHT - 80 - top) // max(len(bars), 1))
    for index, bar in enumerate(bars):
        y = top + index * row
        if lower_is_better:
            share = (low or 1e-9) / (bar.value or 1e-9) if bar.value > 0 else 1.0
        else:
            share = (bar.value - low) / ((high - low) or 1.0)
        length = max(8, int(bar_span * max(0.0, min(1.0, share))))
        colour = ACCENT if bar.highlight else BAR
        label = _fit(draw, bar.label, label_font, label_width)
        draw.text(
            (MARGIN, y + 10),
            label,
            font=_load_font(26, "bold") if bar.highlight else label_font,
            fill=INK,
        )
        draw.rounded_rectangle(
            (bar_left, y + 8, bar_left + length, y + row - 14), radius=6, fill=colour
        )
        draw.text(
            (bar_left + length + 14, y + 10), bar.value_label, font=value_font, fill=INK
        )
    return _png(image)


def render_list_card(title: str, subtitle: str, items: list[str]) -> bytes:
    """A numbered list of up to five entries (paper titles)."""
    image, draw, top = _frame(title, subtitle)
    number_font = _load_font(34, "bold")
    item_font = _load_font(28)
    row = min(96, (HEIGHT - 80 - top) // max(len(items), 1))
    for index, item in enumerate(items):
        y = top + index * row
        draw.text((MARGIN, y), f"{index + 1}", font=number_font, fill=ACCENT)
        for offset, line in enumerate(
            _wrap(draw, item, item_font, WIDTH - 2 * MARGIN - 60, 2)
        ):
            draw.text(
                (MARGIN + 60, y + 2 + offset * 34), line, font=item_font, fill=INK
            )
    return _png(image)
