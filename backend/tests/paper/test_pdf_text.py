import fitz
import httpx
import pytest

from backend.services import paper_pdf_text_service
from backend.services.paper_pdf_text_service import (
    extract_pdf_text_bounded,
    read_paper_pdf_text_bounded,
)


def _pdf(*pages: str) -> bytes:
    with fitz.open() as document:
        for text in pages:
            document.new_page().insert_text((72, 72), text)
        return document.tobytes()


def test_extracts_pages_in_order_until_the_byte_limit():
    pdf = _pdf("First page", "Second page")

    text, truncated = extract_pdf_text_bounded(pdf, max_bytes=10_000)
    assert truncated is False
    assert text.index("First page") < text.index("Second page")

    text, truncated = extract_pdf_text_bounded(pdf, max_bytes=8)
    assert truncated is True
    assert text == "First pa"


def test_rejects_non_pdfs_and_pdfs_without_text():
    with pytest.raises(ValueError, match="Not a PDF"):
        extract_pdf_text_bounded(b"<html>", max_bytes=100)
    with pytest.raises(ValueError, match="no extractable text"):
        extract_pdf_text_bounded(_pdf(""), max_bytes=100)


def test_arxiv_download_uses_the_catalog_version_and_stays_on_arxiv(monkeypatch):
    pdf = _pdf("GitSwarm")
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.host == "arxiv.org" and request.url.path == "/pdf/2610.04862v1":
            return httpx.Response(200, content=pdf)
        return httpx.Response(302, headers={"Location": "https://evil.example/x.pdf"})

    real_client = httpx.Client
    monkeypatch.setattr(
        paper_pdf_text_service.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    text, _ = read_paper_pdf_text_bounded(
        "123292",
        source="arxiv",
        arxiv_id="2610.04862",
        version="v1",
        bucket_id="owner/content",
        token=None,
        max_bytes=1000,
    )
    assert "GitSwarm" in text
    assert requested == ["https://arxiv.org/pdf/2610.04862v1"]

    with pytest.raises(ValueError, match="off arXiv"):
        read_paper_pdf_text_bounded(
            "123292",
            source="arxiv",
            arxiv_id="2610.04862",
            version="v2",
            bucket_id="owner/content",
            token=None,
            max_bytes=1000,
        )


def test_large_arxiv_pdfs_are_refused_while_streaming(monkeypatch):
    monkeypatch.setattr(paper_pdf_text_service, "PDF_TEXT_MAX_PDF_BYTES", 10)
    real_client = httpx.Client
    monkeypatch.setattr(
        paper_pdf_text_service.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, content=b"%PDF-" + b"x" * 64)
            ),
            **kwargs,
        ),
    )
    with pytest.raises(ValueError, match="too large"):
        read_paper_pdf_text_bounded(
            "1",
            source="arxiv",
            arxiv_id="2610.04862",
            version=None,
            bucket_id="owner/content",
            token=None,
            max_bytes=1000,
        )
