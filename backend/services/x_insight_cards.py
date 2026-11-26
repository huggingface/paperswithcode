"""Image cards attached to Papers with Code insight posts on X.

Built on the brand frame (`backend/services/brand.py`, `pwc-brand` skill):
two 1200x675 layouts (X's 16:9 preview), a horizontal bar chart for
leaderboards and trend scores and a ranked list for top papers, and a 1600x2400
card that shows page one of a paper's PDF above the footer, for paper posts and
multi-image roundups.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import fitz
from PIL import Image, ImageDraw

from backend.services.brand import (
    LIGHT,
    fit_text,
    font,
    footer,
    frame,
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
PAGE_CARD_PAD = 48
_MARGINALIA = re.compile(r"^\s*(\d+|[∗*†].*)\s*$")


def _ink_top(page: fitz.Page, left: float, text_top: float) -> float:
    """Where anything is drawn above the text (a logo, a rule), else `text_top`."""
    if text_top < 1:
        return text_top
    band = page.get_pixmap(
        clip=fitz.Rect(left, 0, page.rect.width - left, text_top), alpha=False
    )
    gray = Image.frombytes("RGB", (band.width, band.height), band.samples).convert("L")
    ink = gray.point(lambda value: 255 if value < 230 else 0).getbbox()
    return ink[1] if ink else text_top


def _first_page_hero(pdf: bytes, width: int, height: int) -> Image.Image:
    """Page one from the title down, `width` pixels wide and at most `height` tall.

    The page always fills the width; where it goes on below `height`, it fades out."""
    with fitz.open(stream=pdf, filetype="pdf") as document:
        if document.page_count == 0:
            raise ValueError("PDF has no pages")
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
        left = max(min(b[0] for b in body) - 10, 0)
        top = max(_ink_top(page, left, min(b[1] for b in body)) - 10, 0)
        bottom = max(b[3] for b in body) + 8
        end = min(bottom, top + (page.rect.width - 2 * left) * height / width)
        faded = bottom > end
        clip = fitz.Rect(left, top, page.rect.width - left, end)
        zoom = width * 2 / clip.width
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    image = image.resize((width, round(image.height / 2)), Image.LANCZOS)
    if faded:
        fade = round(width * 0.12)
        mask = Image.linear_gradient("L").resize((width, fade))
        image.paste(
            (255, 255, 255), (0, image.height - fade, width, image.height), mask
        )
    return image


def _artwork_hero(
    artwork: Image.Image, title: str, width: int, height: int
) -> Image.Image:
    """A release page's title above its social image, filling `width` × `height`."""
    title_font = font("serif", round(width / 17), 500)
    pad = round(width * 0.04)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = wrap_text(probe, title, title_font, width - 2 * pad, 3) if title else []
    line_height = round(title_font.size * 1.2)
    text_height = pad + len(lines) * line_height + pad if lines else 0
    rgba = artwork.convert("RGBA")
    art = Image.alpha_composite(
        Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba
    ).convert("RGB")
    art_width = width - 2 * pad
    art_height = round(art.height * art_width / art.width)
    room = height - text_height - pad
    if art_height > room:
        art_width, art_height = round(art_width * room / art_height), room
    art = art.resize((art_width, art_height), Image.LANCZOS)
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((pad, pad + index * line_height), line, font=title_font, fill=P.ink)
    image.paste(art, ((width - art_width) // 2, text_height + (room - art_height) // 2))
    return image


def _title_hero(title: str, width: int, height: int) -> Image.Image:
    """A paper's title alone, centred on a `width` × `height` sheet."""
    title_font = font("serif", round(width / 12), 500)
    pad = round(width * 0.06)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = wrap_text(probe, title, title_font, width - 2 * pad, 4)
    line_height = round(title_font.size * 1.2)
    top = max(pad, (height - len(lines) * line_height) // 2)
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((pad, top + index * line_height), line, font=title_font, fill=P.ink)
    return image


def render_paper_page_card(
    pdf: bytes | Image.Image | None, *, paper_title: str = ""
) -> bytes:
    """A 2:3 card: page one of a paper's PDF above the brand footer.

    A release without a PDF passes its page's social image instead, shown
    under `paper_title`; with neither, the card shows `paper_title` alone."""
    image = Image.new("RGB", PAGE_CARD_SIZE, (255, 255, 255))
    footer_y = footer(ImageDraw.Draw(image), PAGE_CARD_SIZE, palette=P)
    width = PAGE_CARD_SIZE[0] - 2 * PAGE_CARD_PAD
    height = footer_y - PAGE_CARD_PAD
    if pdf is None:
        page = _title_hero(paper_title, width, height)
    elif isinstance(pdf, Image.Image):
        page = _artwork_hero(pdf, paper_title, width, height)
    else:
        page = _first_page_hero(pdf, width, height)
    image.paste(page, (PAGE_CARD_PAD, PAGE_CARD_PAD))
    return _png(image)
