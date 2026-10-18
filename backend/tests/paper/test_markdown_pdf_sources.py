"""Paper-Markdown PDF sources: arXiv fallbacks and the hardened external PDF path."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from backend.tests.paper.markdown_harness import (
    WORKER,
)


def test_worker_download_pdf_falls_back_to_existing_arxiv_version(monkeypatch):
    requested_urls: list[str] = []

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url: str):
            requested_urls.append(url)
            status = 200 if url.endswith("v1.pdf") else 404
            content = b"%PDF-valid" if status == 200 else b"missing"
            return httpx.Response(
                status, content=content, request=httpx.Request("GET", url)
            )

    monkeypatch.setattr(WORKER.httpx, "Client", Client)

    pdf, resolved_version = WORKER.download_pdf("1401.3590", "v3")

    assert pdf == b"%PDF-valid"
    assert resolved_version == "v1"
    assert [url.rsplit("v", 1)[-1] for url in requested_urls] == [
        "3.pdf",
        "2.pdf",
        "1.pdf",
    ]


def test_worker_download_pdf_does_not_fallback_on_rate_limit(monkeypatch):
    client = Mock()
    url = "https://arxiv.org/pdf/1401.3590v3.pdf"
    client.get.return_value = httpx.Response(
        429, content=b"rate limited", request=httpx.Request("GET", url)
    )
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(WORKER.httpx, "Client", Mock(return_value=client))

    with pytest.raises(httpx.HTTPStatusError):
        WORKER.download_pdf("1401.3590", "v3")

    client.get.assert_called_once_with(url)


def test_worker_resolves_external_repository_pdf_urls():
    assert WORKER.normalize_external_pdf_url(
        "https://github.com/QwenLM/Qwen3.8-Flash-Next/blob/main/tech_report.pdf"
    ) == (
        "https://raw.githubusercontent.com/"
        "QwenLM/Qwen3.8-Flash-Next/main/tech_report.pdf"
    )
    assert (
        WORKER.normalize_external_pdf_url(
            "https://huggingface.co/acme/report/blob/main/report.pdf"
        )
        == "https://huggingface.co/acme/report/resolve/main/report.pdf"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/report.pdf",
        "http://169.254.169.254/latest/meta-data/report.pdf",
        "https://localhost/report.pdf",
        "https://user:password@example.com/report.pdf",
    ],
)
def test_worker_rejects_unsafe_external_pdf_urls(url):
    with pytest.raises(ValueError, match="invalid_external_pdf_url"):
        WORKER.normalize_external_pdf_url(url)


def test_worker_rejects_unsafe_external_pdf_redirects(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            self.request_hook = kwargs["event_hooks"]["request"][0]

        def __enter__(self):
            self.request_hook(httpx.Request("GET", "http://127.0.0.1/report.pdf"))
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(WORKER.httpx, "Client", Client)

    with pytest.raises(ValueError, match="invalid_external_pdf_url"):
        WORKER.download_external_pdf("https://example.com/report.pdf")


def test_worker_rejects_external_pdf_hostname_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(
        WORKER.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (WORKER.socket.AF_INET, WORKER.socket.SOCK_STREAM, 6, "", ("10.0.0.4", 443))
        ],
    )

    with pytest.raises(ValueError, match="invalid_external_pdf_url"):
        WORKER.validate_external_pdf_network_target("https://example.com/report.pdf")


def test_worker_streams_external_pdf_with_a_hard_size_cap(monkeypatch):
    read_past_limit = False

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            nonlocal read_past_limit
            yield b"%PDF-"
            yield b"1234"
            read_past_limit = True
            yield b"must-not-be-read"

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def stream(self, method, url):
            assert method == "GET"
            assert url == "https://example.com/report.pdf"
            return Response()

    monkeypatch.setattr(
        WORKER, "validate_external_pdf_network_target", lambda value: value
    )
    monkeypatch.setattr(WORKER, "MAX_PDF_BYTES", 8, raising=False)
    monkeypatch.setattr(WORKER.httpx, "Client", Client)

    with pytest.raises(ValueError, match="invalid_pdf"):
        WORKER.download_external_pdf("https://example.com/report.pdf")

    assert read_past_limit is False


def test_worker_enforces_external_pdf_elapsed_time_limit(monkeypatch):
    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield b"%PDF-valid"

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def stream(self, _method, _url):
            return Response()

    monkeypatch.setattr(
        WORKER, "validate_external_pdf_network_target", lambda value: value
    )
    monkeypatch.setattr(WORKER.httpx, "Client", Client)
    monkeypatch.setattr(WORKER.time, "monotonic", Mock(side_effect=[0, 31]))

    with pytest.raises(httpx.TimeoutException, match="download deadline"):
        WORKER.download_external_pdf(
            "https://example.com/report.pdf", max_elapsed_seconds=30
        )


def test_worker_archives_external_pdf_and_publishes_source_aware_markdown(
    tmp_path, monkeypatch
):
    entry = {
        "paper_key": "external/109743",
        "paper_id": "109743",
        "source": "external",
        "arxiv_id": None,
        "version": "v1",
        "title": "External report",
        "source_url": "https://github.com/acme/report/blob/main/report.pdf",
        "pdf_url": "https://github.com/acme/report/blob/main/report.pdf",
        "pdf_key": "external/109743/paper.pdf",
        "output_key": "external/109743.md",
    }
    pdf = b"%PDF-external"

    class Reader:
        def __init__(self, stream, strict):
            assert stream.read() == pdf
            assert strict is True
            self.pages = [object(), object()]

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=Reader))
    monkeypatch.setattr(WORKER, "download_pdf_for_entry", lambda _entry: (pdf, "v1"))
    monkeypatch.setattr(
        WORKER,
        "run_chandra",
        lambda path, pages: (
            (
                "External report Markdown body " * 80,
                {},
                [],
            )
            if path.read_bytes() == pdf and pages == 2
            else (_ for _ in ()).throw(AssertionError("unexpected OCR input"))
        ),
    )

    result = WORKER.process(entry, tmp_path / "content", tmp_path / "run")

    assert (tmp_path / "content/external/109743/paper.pdf").read_bytes() == pdf
    markdown = (tmp_path / "content/external/109743.md").read_text()
    assert "URL Source: https://github.com/acme/report/blob/main/report.pdf" in markdown
    assert result["paper_key"] == "external/109743"
    assert result["pdf_key"] == "external/109743/paper.pdf"


def test_worker_does_not_archive_external_pdf_before_document_validation(
    tmp_path, monkeypatch
):
    entry = {
        "paper_key": "external/109743",
        "paper_id": "109743",
        "source": "external",
        "arxiv_id": None,
        "version": "v1",
        "title": "Invalid external report",
        "source_url": "https://example.com/report.pdf",
        "pdf_url": "https://example.com/report.pdf",
        "pdf_key": "external/109743/paper.pdf",
        "output_key": "external/109743.md",
    }

    class InvalidReader:
        def __init__(self, *_args, **_kwargs):
            raise ValueError("broken PDF structure")

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=InvalidReader))
    monkeypatch.setattr(
        WORKER,
        "download_pdf_for_entry",
        lambda _entry: (b"%PDF-broken", "v1"),
    )

    with pytest.raises(ValueError, match="broken PDF structure"):
        WORKER.process(entry, tmp_path / "content", tmp_path / "run")

    assert not (tmp_path / "content/external/109743/paper.pdf").exists()
