from types import SimpleNamespace
import io

import pytest

from jobs import url_preflight


PAPER = (
    b"# Paper\n"
    + b"We describe our method and evaluate it against the baselines. " * 25
)


@pytest.mark.parametrize("content_length", [True, False])
def test_project_fetch_keeps_separate_pdf_and_html_limits(monkeypatch, content_length):
    monkeypatch.setattr(url_preflight, "MAX_TEXT_BYTES", 20)

    class Response(io.BytesIO):
        def __init__(self, body):
            super().__init__(body)
            self.headers = {"Content-Length": str(len(body))} if content_length else {}

        def geturl(self):
            return "https://cdn.example.org/report.pdf"

    for body, allowed in [(b"%PDF-" + b"x" * 30, True), (b"<html>" + b"x" * 30, False)]:
        monkeypatch.setattr(
            url_preflight.urllib.request, "urlopen", lambda *a, **k: Response(body)
        )
        if allowed:
            assert url_preflight._fetch("https://example.org/card", 40)[0] == body
        else:
            with pytest.raises(ValueError, match="exceeds 20 bytes"):
                url_preflight._fetch("https://example.org/card", 40)
    monkeypatch.setattr(
        url_preflight.urllib.request,
        "urlopen",
        lambda *a, **k: Response(b"%PDF-" + b"x" * 40),
    )
    with pytest.raises(ValueError, match="exceeds 40 bytes"):
        url_preflight._fetch("https://example.org/card", 40)


@pytest.mark.parametrize("readable", [True, False])
@pytest.mark.parametrize("broken_annotations", [True, False])
def test_project_redirect_to_pdf_requires_readable_evidence(
    monkeypatch, readable, broken_annotations
):
    class Page(dict):
        def extract_text(self):
            return PAPER.decode() if readable else ""

        def get(self, key, default=None):
            if broken_annotations and key == "/Annots":
                raise url_preflight.PdfReadError("broken annotation reference")
            return super().get(key, default)

    monkeypatch.setattr(
        url_preflight, "PdfReader", lambda *_a, **_k: SimpleNamespace(pages=[Page()])
    )
    project = "https://example.org/system-card"
    result = url_preflight.extract_candidates(
        {"paper": {"id": 42, "project_pages": [{"url": project, "is_official": True}]}},
        fetch=lambda url, limit: (b"%PDF-fixture", "https://cdn.example.org/card.pdf"),
    )
    assert result["complete"] is readable
    if readable:
        assert result["sources"][0]["source"] == "project_page_pdf"
        assert {
            "kind": "paper_pdf",
            "url": "https://cdn.example.org/card.pdf",
        } in result["source_documents"]
    else:
        assert result["sources"] == []


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"Title: step-audio-3-gen-framework-four-color.svg\n\nMarkdown Content:\nThis is a diagram of a web application",
        b"Title: https://arxiv.org/html/2609.12945/figure.png\n" + PAPER,
        b"Title: Paper\n\nMarkdown Content:\nA diagram.",
        b"<svg>" + b"x" * 1000,
        b"Title: figure.svg\r\n\r\nMarkdown Content:\r\n" + PAPER,
        b'<?xml version="1.0"?><svg>' + b"x" * 1000,
        b"<!-- generated figure -->\n<svg>" + b"x" * 1000,
        b"\xef\xbb\xbf<!-- generated page -->\n<html>" + b"x" * 1000,
    ],
)
def test_placeholder_is_not_paper_coverage(body):
    with pytest.raises(ValueError):
        url_preflight.validate_paper_text(body)


def test_readable_pdf_is_manifested_when_markdown_is_a_caption(monkeypatch):
    monkeypatch.delenv(url_preflight.OCR_MARKDOWN_TOKEN_ENV, raising=False)

    class Page(dict):
        def extract_text(self):
            return PAPER.decode()

    monkeypatch.setattr(
        url_preflight, "PdfReader", lambda *_a, **_k: SimpleNamespace(pages=[Page()])
    )

    def fetch(url, _limit):
        if "/api/papers/" in url:
            return b"{}", url
        if url.endswith(".md"):
            return b"Title: figure.svg\nMarkdown Content:\nA diagram.", url
        assert url == "https://arxiv.org/pdf/2609.12945"
        return b"%PDF fixture", url

    result = url_preflight.extract_candidates(
        {"paper": {"id": 42, "arxiv_id": "2609.12945"}},
        fetch=fetch,
    )
    assert result["complete"] is True
    assert result["paper_text_available"] is True
    assert result["markdown_available"] is False
    assert result["awaiting_markdown"] is False
    assert result["source_documents"] == [
        {"kind": "paper_pdf", "url": "https://arxiv.org/pdf/2609.12945"}
    ]


def test_project_navigation_is_separated_from_paper_artifacts():
    parser = url_preflight._Links()
    parser.feed("""<header><nav><a href="https://stepaudiollm.github.io/step-audio-3-music/">Music</a></nav>
    <a href="https://github.com/official/code">Code</a></header>
    <main><a href="https://github.com/official/evals">Evaluation</a></main>
    <footer><a href="https://lab.github.io/">Lab</a></footer>""")
    assert parser.urls == ["https://github.com/official/evals"]
    assert parser.navigation_urls == [
        "https://stepaudiollm.github.io/step-audio-3-music/",
        "https://github.com/official/code",
        "https://lab.github.io/",
    ]


@pytest.mark.parametrize(
    "asset", ["assets/tts-elo-chinese.png", "figure.SVG", "paper.pdf"]
)
def test_project_assets_are_not_project_pages(asset):
    assert (
        url_preflight.normalize_candidate(
            f"https://stepaudiollm.github.io/step-audio-3-gen/{asset}"
        )
        is None
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [("external", True), ("arxiv", False)],
)
def test_external_paper_reads_its_first_model_card(source, expected):
    result = url_preflight.extract_candidates(
        {
            "paper": {
                "id": 42,
                "source": source,
                "source_url": "https://example.org/blog/release",
                "hf_models": ["org/Model-X", "https://huggingface.co/org/Model-X-FP8"],
            }
        },
        fetch=lambda url, limit: (b"<html></html>", url),
    )
    documents = [entry["url"] for entry in result["source_documents"]]
    assert ("https://huggingface.co/org/Model-X" in documents) is expected
    assert "https://huggingface.co/org/Model-X-FP8" not in documents
