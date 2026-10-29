"""Curation URL preflight, OCR markdown fallback, and evidence manifests."""

from __future__ import annotations

import hashlib
import io
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


def _front_matter_pdf() -> bytes:
    stream = b"BT /F1 12 Tf 72 720 Td (1 MOSI Intelligence 3 Fudan University) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> /Annots [6 0 R] >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Annot /Subtype /Link /Rect [72 700 300 720] "
        b"/A << /S /URI /URI (https://huggingface.co/collections/OpenMOSS-Team/moss-image) >> >>",
    ]
    body = b"%PDF-1.4\n"
    offsets = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n%s\nendobj\n" % (number, content)
    xref = len(body)
    body += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    body += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    body += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return body


def _enrich_context() -> dict:
    context = _context(project_page=False)
    context["job"] = {"kind": "enrich-paper"}
    return context


def test_enrich_preflight_supplies_pdf_front_matter_alongside_markdown(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    fetched = []

    def fetch(url: str, limit: int):
        fetched.append((url, limit))
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            return PAPER_TEXT, url
        return _front_matter_pdf(), url

    result = url_preflight.extract_candidates(
        _enrich_context(), fetch=fetch, source_cache_dir=tmp_path
    )

    assert result["complete"] is True
    assert (
        "https://arxiv.org/pdf/2608.00042",
        url_preflight.MAX_FRONT_MATTER_PDF_BYTES,
    ) in fetched
    front_matter = [
        item
        for item in result["source_documents"]
        if item["kind"] == "paper_front_matter"
    ]
    assert len(front_matter) == 1
    body = Path(front_matter[0]["local_path"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == front_matter[0]["sha256"]
    assert b"Fudan University" in body
    assert b"https://huggingface.co/collections/OpenMOSS-Team/moss-image" in body
    # Page-1 PDF text is supplementary; Markdown stays the paper text source.
    assert result["markdown_available"] is True
    assert not any(item["kind"] == "paper_pdf" for item in result["source_documents"])


def test_enrich_preflight_front_matter_failure_does_not_block(monkeypatch, tmp_path):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )

    def fetch(url: str, _limit: int):
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            return PAPER_TEXT, url
        raise ValueError("response exceeds limit")

    result = url_preflight.extract_candidates(
        _enrich_context(), fetch=fetch, source_cache_dir=tmp_path
    )

    assert result["complete"] is True
    assert result["errors"] == [{"source": "paper_front_matter", "error": "ValueError"}]
    assert not any(
        item["kind"] == "paper_front_matter" for item in result["source_documents"]
    )


def test_enrich_preflight_reuses_fetched_paper_pdf_for_front_matter(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    monkeypatch.setattr(url_preflight, "validate_paper_text", lambda _body: None)
    fetched = []

    def fetch(url: str, _limit: int):
        fetched.append(url)
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        return _front_matter_pdf(), url

    result = url_preflight.extract_candidates(
        _enrich_context(), fetch=fetch, source_cache_dir=tmp_path
    )

    assert fetched.count("https://arxiv.org/pdf/2608.00042") == 1
    assert {item["kind"] for item in result["source_documents"]} >= {
        "paper_pdf",
        "paper_front_matter",
    }


def test_add_evals_preflight_skips_front_matter(monkeypatch, tmp_path):
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HeadResponse(),
    )
    context = _context(project_page=False)
    context["job"] = {"kind": "add-evals"}

    def fetch(url: str, _limit: int):
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            return PAPER_TEXT, url
        raise AssertionError("add-evals does not read PDF front matter")

    result = url_preflight.extract_candidates(
        context, fetch=fetch, source_cache_dir=tmp_path
    )

    assert result["complete"] is True


def _external_context(*, markdown_expected: bool) -> dict:
    context = _context(project_page=False)
    context["paper"].update(
        id=131370,
        arxiv_id=None,
        source="external",
        source_url="https://openai.com/index/introducing-gpt-6-1-terra",
        repositories=[],
        markdown_expected=markdown_expected,
    )
    return context


def _refused(url: str, _limit: int):
    raise urllib.error.HTTPError(url, 403, "forbidden", {}, None)


def test_external_preflight_reads_the_prepared_page_copy(monkeypatch, tmp_path):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")

    def fetch_external_markdown(paper_id: int, _limit: int, *, token: str):
        assert (paper_id, token) == (131370, "hf-test")
        return (
            PAPER_TEXT,
            "https://huggingface.co/buckets/x/resolve/external%2F131370.md",
        )

    result = url_preflight.extract_candidates(
        _external_context(markdown_expected=True),
        fetch=_refused,
        fetch_external_markdown=fetch_external_markdown,
        source_cache_dir=tmp_path / "paper-sources",
    )

    assert result["awaiting_markdown"] is False
    assert result["markdown_available"] is True
    assert not result["errors"]
    source = next(
        item for item in result["source_documents"] if item["kind"] == "paper_source"
    )
    # The copy belongs to the release page the curator must cite.
    assert source["url"] == "https://openai.com/index/introducing-gpt-6-1-terra"
    assert Path(source["local_path"]).read_bytes() == PAPER_TEXT
    assert hashlib.sha256(PAPER_TEXT).hexdigest() == source["sha256"]
    assert "hf-test" not in json.dumps(result)


@pytest.mark.parametrize("expected", [True, False])
def test_external_preflight_waits_only_for_an_expected_copy(monkeypatch, expected):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")

    def missing(*_args, **_kwargs):
        raise urllib.error.HTTPError("bucket", 404, "not found", {}, None)

    result = url_preflight.extract_candidates(
        _external_context(markdown_expected=expected),
        fetch=_refused,
        fetch_external_markdown=missing,
    )

    assert result["awaiting_markdown"] is expected
    assert result["complete"] is True
    assert "local_path" not in result["source_documents"][0]


RELEASE_PAGE = (
    PAPER_TEXT.decode()
    + "\n![Faceted crystal header](https://cdn.example/images/header.webp)\n"
    + "[![Model benchmark table](https://cdn.example/images/evals-table.w1200.webp)]"
    + "(https://cdn.example/images/evals-table.original.png)\n"
    + "![chart showing ExploitGym](/images/exploitgym.webp)\n"
    + "[![](https://cdn.example/images/related-story.fill-300x300.webp)](/blog/other)\n"
).encode()


def test_results_image_links_keep_result_images_and_prefer_full_size():
    links = url_preflight.results_image_links(
        RELEASE_PAGE.decode(), "https://openai.com/index/introducing-gpt-6-1-terra"
    )

    assert links == [
        (
            "Model benchmark table",
            [
                "https://cdn.example/images/evals-table.original.png",
                "https://cdn.example/images/evals-table.w1200.webp",
            ],
        ),
        ("chart showing ExploitGym", ["https://openai.com/images/exploitgym.webp"]),
    ]


def test_add_evals_external_preflight_downloads_results_images(monkeypatch, tmp_path):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")
    context = _external_context(markdown_expected=True)
    context["job"] = {"kind": "add-evals"}

    def fetch(url: str, _limit: int):
        if url == "https://cdn.example/images/evals-table.original.png":
            raise ValueError("response exceeds limit")
        if url == "https://cdn.example/images/evals-table.w1200.webp":
            return b"RIFF\x00\x00\x00\x00WEBPVP8 ", url
        if url == "https://openai.com/images/exploitgym.webp":
            return b"<html>not an image</html>", url
        return _refused(url, _limit)

    result = url_preflight.extract_candidates(
        context,
        fetch=fetch,
        fetch_external_markdown=lambda *_args, **_kwargs: (RELEASE_PAGE, "bucket"),
        source_cache_dir=tmp_path / "paper-sources",
    )

    images = [
        item for item in result["source_documents"] if item["kind"] == "results_image"
    ]
    # The oversized original falls back to the inline copy.
    assert [(item["url"], item["alt"]) for item in images] == [
        ("https://cdn.example/images/evals-table.w1200.webp", "Model benchmark table")
    ]
    assert Path(images[0]["local_path"]).suffix == ".webp"
    assert images[0]["page_url"] == context["paper"]["source_url"]
    # An image that cannot be read never blocks curation.
    assert result["complete"] is True
    assert {
        "source": "results_image",
        "url": "https://openai.com/images/exploitgym.webp",
        "error": "NotAnImage",
    } in result["errors"]


def test_enrich_external_preflight_skips_results_images(monkeypatch, tmp_path):
    monkeypatch.setenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, "hf-test")
    context = _external_context(markdown_expected=True)
    context["job"] = {"kind": "enrich-paper"}

    def fetch(url: str, _limit: int):
        if "images" in url:
            raise AssertionError("enrichment does not read result images")
        return _refused(url, _limit)

    result = url_preflight.extract_candidates(
        context,
        fetch=fetch,
        fetch_external_markdown=lambda *_args, **_kwargs: (RELEASE_PAGE, "bucket"),
        source_cache_dir=tmp_path / "paper-sources",
    )

    assert all(item["kind"] != "results_image" for item in result["source_documents"])


class _BodyResponse(io.BytesIO):
    headers: dict = {}

    def geturl(self):
        return "https://cdn.example/images/evals-table.original.png"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_fetch_allows_large_images_but_keeps_html_on_the_text_budget(monkeypatch):
    size = url_preflight.MAX_TEXT_BYTES + 1_000_000
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * size
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _BodyResponse(png),
    )
    body, _url = url_preflight._fetch(
        "https://cdn.example/t.png", url_preflight.MAX_IMAGE_BYTES
    )
    assert body == png

    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _BodyResponse(b"<html>" + b"x" * size),
    )
    with pytest.raises(ValueError, match="exceeds"):
        url_preflight._fetch("https://cdn.example/t.png", url_preflight.MAX_IMAGE_BYTES)
