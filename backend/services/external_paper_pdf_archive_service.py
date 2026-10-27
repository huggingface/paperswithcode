"""Archive a new external paper's PDF so the reader and chat open it at once.

The reader and reader chat's PDF-text fallback read an external paper's PDF
only from the archived copy at ``external/<id>/paper.pdf`` in the paper
Markdown bucket. The OCR worker writes that copy, but only once a GPU slot is
free, which can take hours. Archiving at ingestion closes that gap; the worker
reuses the archived copy instead of downloading the PDF again.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

import fitz
import httpx
from huggingface_hub import HfApi, HfFileSystem

from backend.scripts.generate_missing_paper_markdown import download_external_pdf
from backend.services.paper_markdown_service import PAPER_PDF_MAX_BYTES

logger = logging.getLogger(__name__)

# Ingestion runs in request handlers, so a slow host must not hold one for
# the OCR worker's three minutes; the worker still archives what times out.
DOWNLOAD_TIMEOUT_SECONDS = 20
DOWNLOAD_DEADLINE_SECONDS = 60


def is_pdf_source_url(url: str) -> bool:
    """Whether the OCR worker reads ``url`` as the PDF (its manifest rule)."""
    parsed = urlsplit(url)
    marker = f"{parsed.path}?{parsed.query}".lower()
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and (".pdf" in marker or "/pdf" in parsed.path.lower())
    )


def archive_external_paper_pdf(
    paper_id: int, pdf_url: str, *, bucket_id: str, token: str | None
) -> bool:
    """Download and archive one PDF; return False when a copy already exists."""
    path = f"hf://buckets/{bucket_id}/external/{paper_id}/paper.pdf"
    filesystem = HfFileSystem(token=token)
    if filesystem.exists(path):
        return False
    data = download_external_pdf(
        pdf_url,
        timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS,
        max_elapsed_seconds=DOWNLOAD_DEADLINE_SECONDS,
    )
    if len(data) > PAPER_PDF_MAX_BYTES:
        raise ValueError("invalid_pdf")
    # The worker trusts an archived copy, so archive only a PDF that opens.
    with fitz.open(stream=data, filetype="pdf") as document:
        if document.page_count < 1:
            raise ValueError("invalid_pdf")
    HfApi(token=token).batch_bucket_files(
        bucket_id, add=[(data, f"external/{paper_id}/paper.pdf")], token=token
    )
    filesystem.invalidate_cache(f"hf://buckets/{bucket_id}/external")
    return True


def archive_new_external_paper_pdf(
    paper_id: int, source_url: str, *, bucket_id: str, token: str | None
) -> None:
    """Archive a new paper's PDF source, leaving any failure to the OCR worker."""
    if not is_pdf_source_url(source_url) or not bucket_id.strip():
        return
    try:
        archive_external_paper_pdf(
            paper_id, source_url, bucket_id=bucket_id.strip(), token=token
        )
    except (httpx.HTTPError, ValueError, fitz.FileDataError) as error:
        logger.warning(
            "external paper %s PDF not archived at ingestion: %s", paper_id, error
        )
