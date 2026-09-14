from types import SimpleNamespace

import pytest

from jobs import url_preflight


PAPER = (
    b"# Paper\n"
    + b"We describe our method and evaluate it against the baselines. " * 25
)


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"Title: step-audio-3-gen-framework-four-color.svg\n\nMarkdown Content:\nThis is a diagram of a web application",
        b"Title: https://arxiv.org/html/2609.12945/figure.png\n" + PAPER,
        b"Title: Paper\n\nMarkdown Content:\nA diagram.",
        b"<svg>" + b"x" * 1000,
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
