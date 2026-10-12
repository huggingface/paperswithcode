"""Curation URL preflight, OCR markdown fallback, and evidence manifests."""

from __future__ import annotations

import hashlib
import json
import urllib.error
from pathlib import Path

import pytest

from jobs import url_preflight
from backend.tests.curation.paper_curation_harness import (
    PAPER_TEXT,
    _HeadResponse,
    _context,
)


def test_url_patterns_are_the_authoritative_design_patterns():
    assert url_preflight.GITHUB_URL_PATTERN == r"\bhttps?:\/\/github\.com[^\s]*\b"
    assert (
        url_preflight.PROJECT_PAGE_URL_PATTERN
        == r"\bhttps?:\/\/[^\s\/]+\.github\.io[^\s]*\b"
    )


def test_normalize_candidate_ignores_malformed_markdown_link_url():
    assert (
        url_preflight.normalize_candidate(
            "https://odensenlp.github.io](https://odensenlp.github.io"
        )
        is None
    )


def test_preflight_reuses_complete_importer_links_but_verifies_markdown(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    fetched = []

    def fetch(url, _limit):
        fetched.append(url)
        assert url.endswith(".md")
        return PAPER_TEXT, url

    result = url_preflight.extract_candidates(_context(), fetch=fetch)

    assert result["complete"] is True
    assert result["markdown_available"] is True
    assert fetched == ["https://huggingface.co/papers/2608.00042.md"]
    assert {item["kind"] for item in result["candidates"]} == {"github", "project_page"}
    assert all("hf_api" in item["source_layers"][0] for item in result["candidates"])


def test_eval_preflight_manifests_model_card_blog_project_and_readme(monkeypatch):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    context = _context()
    context["paper"]["source_url"] = "https://example.com/official-blog"
    context["source_candidate"] = {
        "repo_id": "org/model",
        "model_card_url": "https://huggingface.co/org/model/raw/revision/README.md",
    }

    result = url_preflight.extract_candidates(
        context,
        fetch=lambda url, _limit: (PAPER_TEXT, url),
    )

    assert {(item["kind"], item["url"]) for item in result["source_documents"]} == {
        ("paper_source", "https://example.com/official-blog"),
        (
            "model_card",
            "https://huggingface.co/org/model/raw/revision/README.md",
        ),
        ("github_readme", "https://github.com/example/project"),
        ("project_page", "https://example.github.io/project"),
        ("paper_markdown", "https://huggingface.co/papers/2608.00042.md"),
    }


def test_preflight_requires_paper_text_even_with_official_links(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return json.dumps(
                {
                    "githubRepo": "https://github.com/example/project",
                    "projectPage": "https://example.github.io/project",
                }
            ).encode(), url
        assert url.endswith(".md")
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    result = url_preflight.extract_candidates(_context(project_page=False), fetch=fetch)

    assert result["awaiting_markdown"] is True
    assert result["complete"] is False
    assert fetched == [
        "https://huggingface.co/api/papers/2608.00042",
        "https://huggingface.co/papers/2608.00042.md",
        "https://arxiv.org/pdf/2608.00042",
    ]
    assert result["sources"][0]["sha256"]


def test_preflight_uses_discovered_project_candidate_for_conditional_html(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    context = _context(project_page=False)
    context["paper"]["repositories"] = []
    context["paper"]["abstract"] = "Project: https://demo.github.io/paper"
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            return b"", url
        if "/pdf/" in url:
            raise ValueError("fixture has no PDF")
        assert url == "https://demo.github.io/paper"
        return b'<a href="https://github.com/example/discovered">code</a>', url

    result = url_preflight.extract_candidates(context, fetch=fetch)

    assert "https://demo.github.io/paper" in fetched
    assert any(
        item["normalized_url"] == "https://github.com/example/discovered"
        and "project_page_html" in item["source_layers"]
        for item in result["candidates"]
    )


@pytest.mark.parametrize("image_caption", [False, True])
def test_preflight_uses_ocr_markdown_when_public_markdown_is_unavailable(
    monkeypatch,
    image_caption,
    tmp_path,
):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            if image_caption:
                return (
                    b"Title: https://arxiv.org/html/2608.00042/figure.svg\n\nMarkdown Content:\nA bar chart.",
                    url,
                )
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        raise AssertionError("OCR Markdown must avoid the PDF fallback")

    def fetch_ocr_markdown(arxiv_id: str, _limit: int, *, token: str):
        assert arxiv_id == "2608.00042"
        assert token == "hf-test"
        return (
            b"Code: https://github.com/example/project\n"
            b"Project: https://example.github.io/project\n" + PAPER_TEXT,
            "https://signed.example/markdown",
        )

    result = url_preflight.extract_candidates(
        _context(project_page=False),
        fetch=fetch,
        fetch_ocr_markdown=fetch_ocr_markdown,
        source_cache_dir=tmp_path / "paper-sources",
    )

    assert result["complete"] is True
    assert {source["source"] for source in result["sources"]} == {
        "hf_api",
        "ocr_markdown",
    }
    assert not result["errors"]
    assert not any("/pdf/" in url for url in fetched)
    source = next(
        item for item in result["source_documents"] if item["kind"] == "paper_markdown"
    )
    monkeypatch.delenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV)
    cached = Path(source["local_path"]).read_bytes()
    assert cached.endswith(PAPER_TEXT)
    assert hashlib.sha256(cached).hexdigest() == source["sha256"]
    assert source["url"] == "https://signed.example/markdown"
    assert "hf-test" not in json.dumps(result)


def test_preflight_accepts_ocr_markdown_when_hf_papers_api_has_no_record(
    monkeypatch,
):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    def fetch(url: str, _limit: int):
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    def fetch_ocr_markdown(arxiv_id: str, _limit: int, *, token: str):
        assert arxiv_id == "2608.00042"
        assert token == "hf-test"
        return PAPER_TEXT, "https://signed.example/markdown"

    context = _context(project_page=False)
    context["paper"]["repositories"] = []
    result = url_preflight.extract_candidates(
        context,
        fetch=fetch,
        fetch_ocr_markdown=fetch_ocr_markdown,
    )

    assert result["complete"] is True
    assert result["awaiting_markdown"] is False
    assert result["markdown_available"] is True
    assert result["errors"] == [{"source": "hf_api", "error": "HTTPError"}]


@pytest.mark.parametrize("project_status", [404, 410, 503])
def test_preflight_dead_project_page_keeps_paper_evidence(monkeypatch, project_status):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    def fetch(url: str, _limit: int):
        if "/api/papers/" in url:
            return json.dumps(
                {"projectPage": "https://example.github.io/missing"}
            ).encode(), url
        if url.endswith(".md"):
            return PAPER_TEXT, url
        raise urllib.error.HTTPError(url, project_status, "unavailable", {}, None)

    context = _context(project_page=False)
    context["paper"]["repositories"] = []
    result = url_preflight.extract_candidates(context, fetch=fetch)
    assert result["complete"] is (project_status in {404, 410})
    assert result["errors"][0]["http_status"] == project_status


def test_preflight_does_not_fetch_pdf_when_hf_markdown_is_available(monkeypatch):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            return PAPER_TEXT, url
        raise AssertionError("PDF is a last-resort source")

    result = url_preflight.extract_candidates(_context(project_page=False), fetch=fetch)

    assert result["complete"] is True
    assert not any("/pdf/" in url for url in fetched)


def test_preflight_checks_pdf_when_official_repository_is_available(
    monkeypatch,
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    result = url_preflight.extract_candidates(_context(project_page=False), fetch=fetch)

    assert result["complete"] is False
    assert result["awaiting_markdown"] is True
    assert {error["source"] for error in result["errors"]} == {
        "hf_markdown",
        "paper_pdf",
    }
    assert any("/pdf/" in url for url in fetched)


def test_preflight_marks_missing_public_and_ocr_markdown_as_awaiting(monkeypatch):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    def unavailable(url: str, _limit: int):
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    def unavailable_ocr(*_args, **_kwargs):
        raise urllib.error.HTTPError("bucket", 404, "not found", {}, None)

    context = _context(project_page=False)
    context["paper"]["repositories"] = []
    result = url_preflight.extract_candidates(
        context, fetch=unavailable, fetch_ocr_markdown=unavailable_ocr
    )

    assert result["awaiting_markdown"] is True
    assert result["markdown_available"] is False


def test_fetch_ocr_markdown_uses_authenticated_bucket_download(monkeypatch):
    captured = {}

    class Response:
        headers = {"Content-Length": "2"}

        def geturl(self):
            return "https://signed.example/markdown"

        def read(self, _size):
            return b"#\n"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def open(request, *, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(
        url_preflight.urllib.request,
        "build_opener",
        lambda *_handlers: type("Opener", (), {"open": staticmethod(open)})(),
    )

    body, final_url = url_preflight._fetch_ocr_markdown(
        "2608.00042v3", 10, token="hf-test"
    )

    assert body == b"#\n"
    assert final_url == (
        "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/"
        "2608%2F2608.00042.md"
    )
    assert captured == {
        "url": "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/2608%2F2608.00042.md",
        "authorization": "Bearer hf-test",
        "timeout": url_preflight.TIMEOUT_SECONDS,
    }


def test_ocr_bucket_redirect_strips_authorization_for_cdn_request():
    request = url_preflight.urllib.request.Request(
        "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/file",
        headers={"Authorization": "Bearer hf-test"},
    )

    redirected = url_preflight._BucketRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://cdn.example/signed-file",
    )

    assert redirected is not None
    assert redirected.full_url == "https://cdn.example/signed-file"
    assert redirected.get_header("Authorization") is None


def test_ocr_bucket_redirect_strips_authorization_for_scheme_downgrade():
    request = url_preflight.urllib.request.Request(
        "https://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/file",
        headers={"Authorization": "Bearer hf-test"},
    )

    redirected = url_preflight._BucketRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "http://huggingface.co/buckets/huggingface/pwc-papers-content/resolve/file",
    )

    assert redirected is not None
    assert redirected.get_header("Authorization") is None
