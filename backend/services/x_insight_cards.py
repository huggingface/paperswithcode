"""Image cards attached to Papers with Code insight posts on X.

Built on the brand frame (`backend/services/brand.py`, `pwc-brand` skill):
two 1200x675 layouts (X's 16:9 preview), a horizontal bar chart for
leaderboards and trend scores and a ranked list for top papers, and a 1600x2400
card that shows page one of a paper's PDF, for multi-image roundups.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import fitz
from PIL import Image, ImageDraw, ImageFont

from backend.services.brand import (
    LIGHT,
    draw_tracked,
    fit_text,
    font,
    frame,
    tracked_length,
    wrap_text,
)

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


PAGE_CARD_SIZE = (1600, 2400)
_INTRODUCTION = re.compile(r"^\s*(1\.?\s*)?Introduction\b", re.IGNORECASE)
_MARGINALIA = re.compile(r"^\s*(\d+|[∗*†].*)\s*$")


def _first_page_hero(pdf: bytes, width: int, height: int) -> Image.Image:
    """Page one from the title down to the introduction, `width` pixels wide.

    A short hero runs on into the page, up to `height`, and fades out."""
    with fitz.open(stream=pdf, filetype="pdf") as document:
        page = document[0]
        blocks = [b for b in page.get_text("blocks") if b[2] > page.rect.width * 0.1]
        body = [
            b
            for b in blocks
            if not _MARGINALIA.match(b[4].split("\n")[0])
            and b[1] < page.rect.height * 0.9
        ]
        if not body:
            raise ValueError("PDF page one has no text")
        intro = [b for b in blocks if _INTRODUCTION.match(b[4])]
        left = max(min(b[0] for b in body) - 10, 0)
        top = max(min(b[1] for b in body) - 10, 0)
        bottom = max(b[3] for b in body) + 8
        end = intro[0][1] - 8 if intro else bottom
        fill = top + (page.rect.width - 2 * left) * height / width
        faded = fill > end and bottom > end
        if faded:
            end = min(fill, bottom)
        clip = fitz.Rect(left, top, page.rect.width - left, end)
        zoom = width * 2 / clip.width
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    image = image.resize((width, round(image.height / 2)), Image.LANCZOS)
    if faded and bottom > end:
        fade = round(width * 0.12)
        mask = Image.linear_gradient("L").resize((width, fade))
        image.paste(
            (255, 255, 255), (0, image.height - fade, width, image.height), mask
        )
    return image


def _fit_sentences(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_: ImageFont.FreeTypeFont,
    width: int,
    lines: int,
) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    for count in range(len(sentences), 0, -1):
        wrapped = wrap_text(draw, " ".join(sentences[:count]), font_, width, lines + 1)
        if len(wrapped) <= lines:
            return wrapped
    return wrap_text(draw, sentences[0], font_, width, lines)


def render_paper_page_card(
    pdf: bytes,
    *,
    title: str,
    subtitle: str,
    eyebrow: str,
    counter: str,
    source: str,
    summary: str,
) -> bytes:
    """A 2:3 card that shows page one of a paper's PDF with a why-read-it line."""
    width = PAGE_CARD_SIZE[0]
    card = frame(
        PAGE_CARD_SIZE,
        title=title,
        subtitle=subtitle,
        eyebrow=eyebrow,
        palette=P,
        title_size=40,
        title_lines=2,
    )
    draw, px, margin = card.draw, card.px, card.margin
    counter_font = font("mono", px(17), 500)
    counter_width = tracked_length(draw, counter, font=counter_font, tracking=0.12)
    draw_tracked(
        draw,
        (width - margin - counter_width, px(56)),
        counter,
        font=counter_font,
        fill=P.ink_faint,
        tracking=0.12,
    )

    summary_font = font("sans", px(19))
    lines = _fit_sentences(draw, summary, summary_font, width - 2 * margin, 4)
    line_height = round(summary_font.size * 1.45)
    summary_top = card.bottom - len(lines) * line_height - px(34)
    draw_tracked(
        draw,
        (margin, summary_top),
        "WHY READ IT",
        font=font("mono", px(14), 500),
        fill=P.accent,
        tracking=0.12,
    )
    for index, line in enumerate(lines):
        draw.text(
            (margin, summary_top + px(34) + index * line_height),
            line,
            font=summary_font,
            fill=P.ink,
        )

    pad = px(14)
    sheet_top = card.top
    inner_width = width - 2 * margin - 2 * pad
    inner_height = summary_top - px(64) - sheet_top - 2 * pad
    page = _first_page_hero(pdf, inner_width, inner_height)
    if page.height > inner_height:
        page = page.resize(
            (round(page.width * inner_height / page.height), inner_height),
            Image.LANCZOS,
        )
    sheet_bottom = sheet_top + page.height + 2 * pad
    draw.rounded_rectangle(
        (margin, sheet_top, width - margin, sheet_bottom),
        radius=px(8),
        fill=(255, 255, 255),
        outline=P.hairline_strong,
        width=2,
    )
    card.image.paste(
        page, (margin + pad + (inner_width - page.width) // 2, sheet_top + pad)
    )
    draw.text(
        (margin, sheet_bottom + px(10)),
        source,
        font=font("mono", px(13)),
        fill=P.ink_faint,
    )
    return _png(card.image)
