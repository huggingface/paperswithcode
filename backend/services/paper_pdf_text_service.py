"""Bounded plain-text extraction from a paper PDF.

Chat uses this only while a paper's canonical Markdown is still being produced
by the hourly OCR pipeline, so a freshly indexed paper can be discussed at once.
"""

from __future__ import annotations

import re

import fitz
import httpx

from backend.services.paper_markdown_service import (
    normalize_markdown_arxiv_id,
    stream_external_paper_pdf,
)

PDF_TEXT_MAX_PDF_BYTES = 50 * 1024 * 1024
ARXIV_PDF_TIMEOUT_SECONDS = 10
ARXIV_PDF_HOSTS = {"arxiv.org", "export.arxiv.org"}
USER_AGENT = "paperswithcode-chat/1.0 (https://paperswithcode.co)"
_ARXIV_VERSION = re.compile(r"v[1-9][0-9]{0,2}")


def _require_arxiv_host(request: httpx.Request) -> None:
    if request.url.scheme != "https" or request.url.host not in ARXIV_PDF_HOSTS:
        raise ValueError("arXiv PDF redirected off arXiv")


def _download_arxiv_pdf(arxiv_id: str, version: str | None) -> bytes:
    suffix = version if version and _ARXIV_VERSION.fullmatch(version) else ""
    url = f"https://arxiv.org/pdf/{normalize_markdown_arxiv_id(arxiv_id)}{suffix}"
    data = bytearray()
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=ARXIV_PDF_TIMEOUT_SECONDS,
        follow_redirects=True,
        max_redirects=3,
        event_hooks={"request": [_require_arxiv_host]},
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > PDF_TEXT_MAX_PDF_BYTES:
                    raise ValueError("arXiv PDF is too large for text extraction")
    return bytes(data)


def _read_external_pdf(paper_id: str, *, bucket_id: str, token: str | None) -> bytes:
    chunks, size = stream_external_paper_pdf(paper_id, bucket_id=bucket_id, token=token)
    if size > PDF_TEXT_MAX_PDF_BYTES:
        raise ValueError("Archived PDF is too large for text extraction")
    return b"".join(chunks)


def extract_pdf_text_bounded(pdf: bytes, *, max_bytes: int) -> tuple[str, bool]:
    """Return the leading text of a PDF, cut at ``max_bytes`` UTF-8 bytes."""
    if not pdf.startswith(b"%PDF-"):
        raise ValueError("Not a PDF")
    parts: list[str] = []
    used = 0
    truncated = False
    with fitz.open(stream=pdf, filetype="pdf") as document:
        for page in document:
            encoded = page.get_text().replace("\x00", " ").encode()
            if used + len(encoded) > max_bytes:
                parts.append(encoded[: max_bytes - used].decode("utf-8", "ignore"))
                truncated = True
                break
            parts.append(encoded.decode())
            used += len(encoded)
    text = "".join(parts)
    if not text.strip():
        raise ValueError("PDF has no extractable text")
    return text, truncated


def read_paper_pdf_text_bounded(
    paper_id: str,
    *,
    source: str,
    arxiv_id: str | None,
    version: str | None,
    bucket_id: str,
    token: str | None,
    max_bytes: int,
) -> tuple[str, bool]:
    if source == "arxiv" and arxiv_id:
        pdf = _download_arxiv_pdf(arxiv_id, version)
    elif source == "external":
        pdf = _read_external_pdf(paper_id, bucket_id=bucket_id, token=token)
    else:
        raise ValueError("Paper has no readable PDF")
    return extract_pdf_text_bounded(pdf, max_bytes=max_bytes)
