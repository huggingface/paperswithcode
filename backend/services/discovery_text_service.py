"""Inline Markdown helpers for server-rendered discovery pages.

Catalog descriptions use a small inline Markdown subset: links, bold, italic,
and code spans. These helpers render that subset to escaped HTML or plain
text without pulling a full Markdown engine into the per-request path.
"""

from __future__ import annotations

import re
from html import escape

META_DESCRIPTION_LIMIT = 155

# Link targets may contain one level of parentheses, as Wikipedia URLs do.
_LINK_RE = re.compile(r"\[([^\[\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)")
_CODE_RE = re.compile(r"`([^`]+)`")
_STRONG_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_EM_RE = re.compile(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])")
_PLACEHOLDER_RE = re.compile("\x00(\\d+)\x00")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def _safe_href(url: str) -> str | None:
    # Browsers treat "/\host" like "//host", so backslashes are never safe.
    if "\\" in url:
        return None
    if url.startswith("/") and not url.startswith("//"):
        return url
    if url.startswith(("https://", "http://")):
        return url
    return None


def _inline_html(text: str) -> str:
    """Render links, code, bold, and italic; everything else is escaped.

    Code spans and link tags become placeholders first, so emphasis may span
    a link while asterisks inside code and link targets stay literal.
    """
    fragments: list[str] = []

    def hold(fragment: str) -> str:
        fragments.append(fragment)
        return f"\x00{len(fragments) - 1}\x00"

    def link(match: re.Match[str]) -> str:
        href = _safe_href(match[2])
        if href is None:
            return match[1]
        opening = f'<a href="{escape(href, quote=True)}">'
        return hold(opening) + match[1] + hold("</a>")

    text = _CODE_RE.sub(
        lambda match: hold(f"<code>{escape(match[1])}</code>"),
        text.replace("\x00", ""),
    )
    html = escape(_LINK_RE.sub(link, text))
    html = _STRONG_RE.sub(r"<strong>\1</strong>", html)
    html = _EM_RE.sub(r"<em>\1</em>", html)
    return _PLACEHOLDER_RE.sub(lambda match: fragments[int(match[1])], html)


def markdown_html(text: str) -> str:
    """Render paragraphs of inline Markdown as escaped HTML paragraphs."""
    paragraphs = (" ".join(block.split()) for block in re.split(r"\n\s*\n", text))
    return "".join(f"<p>{_inline_html(block)}</p>" for block in paragraphs if block)


def markdown_inline_html(text: str) -> str:
    """Render one inline Markdown fragment, such as a list item, as HTML."""
    return _inline_html(" ".join(text.split()))


def markdown_plain_text(text: str) -> str:
    """Strip inline Markdown syntax, keeping link labels and emphasized words."""
    text = _LINK_RE.sub(r"\1", text)
    text = _CODE_RE.sub(r"\1", text)
    text = _STRONG_RE.sub(r"\1", text)
    text = _EM_RE.sub(r"\1", text)
    return " ".join(text.split())


def meta_description(text: str, limit: int = META_DESCRIPTION_LIMIT) -> str:
    """Shorten plain text to whole sentences, or whole words, within ``limit``."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    summary = ""
    for sentence in _SENTENCE_END_RE.split(text):
        candidate = f"{summary} {sentence}".strip()
        if len(candidate) > limit:
            break
        summary = candidate
    if len(summary) >= limit // 2:
        return summary
    words = text[: limit - 1].rsplit(" ", 1)[0]
    return words.rstrip(" ,;:—-") + "…"
