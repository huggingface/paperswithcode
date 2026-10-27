"""New external PDF papers are archived at ingestion for the reader and chat."""

from __future__ import annotations

import fitz
import httpx
import pytest

from backend.services import external_paper_pdf_archive_service as service

BUCKET = "huggingface/pwc-papers-content"
URL = "https://www.example.org/report.pdf"


def _pdf() -> bytes:
    with fitz.open() as document:
        document.new_page()
        return document.tobytes()


class FakeBucket:
    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})

    def install(self, monkeypatch):
        bucket = self

        class Api:
            def __init__(self, token=None):
                pass

            def batch_bucket_files(self, bucket_id, *, add, token=None):
                for data, key in add:
                    bucket.files[key] = data

        class FileSystem:
            def __init__(self, token=None):
                pass

            def exists(self, path):
                return path.split("/", 5)[5] in bucket.files

            def invalidate_cache(self, path=None):
                pass

        monkeypatch.setattr(service, "HfApi", Api)
        monkeypatch.setattr(service, "HfFileSystem", FileSystem)
        return self


def _download(monkeypatch, result):
    calls = []

    def download(url, **kwargs):
        calls.append(url)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(service, "download_external_pdf", download)
    return calls


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.gr.inc/avalonm1.pdf", True),
        ("https://openreview.net/pdf?id=abc", True),
        ("https://example.org/files/report.PDF?download=1", True),
        ("https://www.gr.inc/releases/avalon-m1", False),
        ("https://huggingface.co/org/model", False),
    ],
)
def test_is_pdf_source_url_matches_the_ocr_manifest_rule(url, expected):
    assert service.is_pdf_source_url(url) is expected


def test_archives_the_pdf_where_the_reader_reads_it(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)
    pdf = _pdf()
    _download(monkeypatch, pdf)

    service.archive_new_external_paper_pdf(7, URL, bucket_id=BUCKET, token=None)

    assert bucket.files == {"external/7/paper.pdf": pdf}


def test_keeps_an_existing_archive_without_downloading(monkeypatch):
    bucket = FakeBucket({"external/7/paper.pdf": b"%PDF-old"}).install(monkeypatch)
    calls = _download(monkeypatch, _pdf())

    assert (
        service.archive_external_paper_pdf(7, URL, bucket_id=BUCKET, token=None)
        is False
    )
    assert calls == []
    assert bucket.files == {"external/7/paper.pdf": b"%PDF-old"}


def test_skips_html_sources_and_unconfigured_buckets(monkeypatch):
    bucket = FakeBucket().install(monkeypatch)
    calls = _download(monkeypatch, _pdf())

    service.archive_new_external_paper_pdf(
        7, "https://www.gr.inc/releases/avalon-m1", bucket_id=BUCKET, token=None
    )
    service.archive_new_external_paper_pdf(7, URL, bucket_id=" ", token=None)

    assert calls == []
    assert bucket.files == {}


@pytest.mark.parametrize(
    "result",
    [
        httpx.ConnectTimeout("slow host"),
        ValueError("invalid_pdf"),
        b"%PDF-1.7 truncated",
    ],
)
def test_failures_are_left_to_the_ocr_worker(monkeypatch, result):
    bucket = FakeBucket().install(monkeypatch)
    _download(monkeypatch, result)

    service.archive_new_external_paper_pdf(7, URL, bucket_id=BUCKET, token=None)

    assert bucket.files == {}
