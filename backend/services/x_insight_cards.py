"""Image cards attached to Papers with Code insight posts on X.

Two layouts, both 1200x675 (X's 16:9 preview), built on the brand frame
(`backend/services/brand.py`, `pwc-brand` skill): a horizontal bar chart for
leaderboards and trend scores, and a ranked list for top papers.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from backend.services.brand import LIGHT, fit_text, font, frame, wrap_text

SIZE = (1200, 675)
P = LIGHT


@dataclass(frozen=True)
class Bar:
    label: str
    value: float
    value_label: str
    highlight: bool = False


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_bar_card(
    title: str,
    subtitle: str,
    bars: list[Bar],
    *,
    lower_is_better: bool = False,
    eyebrow: str = "",
) -> bytes:
    """Horizontal bars, best first; bar length is relative to the best value."""
    card = frame(SIZE, title=title, subtitle=subtitle, eyebrow=eyebrow, palette=P)
    draw, margin = card.draw, card.margin
    label_width = 360
    value_width = 190
    bar_left = margin + label_width + 20
    bar_span = SIZE[0] - margin - value_width - bar_left
    values = [bar.value for bar in bars]
    low, high = min(values + [0.0]), max(values)
    best_low = min((value for value in values if value > 0), default=1.0)
    row = min(58, (card.bottom - card.top) // max(len(bars), 1))
    for index, bar in enumerate(bars):
        y = card.top + index * row
        if lower_is_better:
            share = best_low / bar.value if bar.value > 0 else 1.0
        else:
            share = (bar.value - low) / ((high - low) or 1.0)
        length = max(6, int(bar_span * max(0.0, min(1.0, share))))
        label_font = font("sans", 23, 600 if bar.highlight else 400)
        draw.text(
            (margin, y + 8),
            fit_text(draw, bar.label, label_font, label_width),
            font=label_font,
            fill=P.ink if bar.highlight else P.ink_soft,
        )
        draw.rounded_rectangle(
            (bar_left, y + 8, bar_left + length, y + row - 14),
            radius=4,
            fill=P.accent if bar.highlight else P.accent_soft,
        )
        draw.text(
            (bar_left + length + 14, y + 9),
            bar.value_label,
            font=font("mono", 21, 600 if bar.highlight else 400),
            fill=P.accent_text if bar.highlight else P.ink_soft,
        )
    return _png(card.image)


def render_list_card(
    title: str, subtitle: str, items: list[str], *, eyebrow: str = ""
) -> bytes:
    """A numbered list of up to five entries (paper titles)."""
    card = frame(SIZE, title=title, subtitle=subtitle, eyebrow=eyebrow, palette=P)
    draw, margin = card.draw, card.margin
    number_font = font("serif-italic", 36, 400)
    item_font = font("serif", 26, 500)
    row = min(84, (card.bottom - card.top + 24) // max(len(items), 1))
    for index, item in enumerate(items):
        y = card.top + index * row
        draw.text((margin, y - 4), f"{index + 1}", font=number_font, fill=P.accent)
        for offset, line in enumerate(
            wrap_text(draw, item, item_font, SIZE[0] - 2 * margin - 56, 2)
        ):
            draw.text((margin + 56, y + offset * 32), line, font=item_font, fill=P.ink)
    return _png(card.image)
