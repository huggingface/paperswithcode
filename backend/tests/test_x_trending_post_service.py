from __future__ import annotations

import json
from types import SimpleNamespace

import fitz
import httpx

from backend.services import x_trending_post_service as service
from backend.services.x_trending_post_service import (
    XCredentials,
    XPoster,
    compose_post,
    oauth1_header,
    render_first_page,
    weighted_length,
)

CREDENTIALS = XCredentials("ck", "cs", "at", "as")


def _pdf(pages: int = 2) -> bytes:
    document = fitz.open()
    for number in range(pages):
        document.new_page().insert_text((72, 72), f"Page {number + 1}")
    return document.tobytes()


def test_compose_post_keeps_title_newline_tldr_when_it_fits():
    text = compose_post("A  Title", "First point. Second point.", max_chars=280)
    assert text == "A Title\nFirst point. Second point."


def test_compose_post_drops_trailing_sentences_to_fit():
    tldr = "Short first sentence. " + "x" * 300 + "."
    assert compose_post("Title", tldr, max_chars=280) == (
        "Title\nShort first sentence."
    )


def test_compose_post_truncates_a_long_first_sentence_at_a_word():
    tldr = " ".join(["word"] * 100) + "."
    text = compose_post("Title", tldr, max_chars=100)
    assert text.startswith("Title\nword word")
    assert text.endswith("word…")
    assert weighted_length(text) <= 100


def test_weighted_length_counts_wide_characters_twice():
    assert weighted_length("ab—é") == 4
    assert weighted_length("模型") == 4


def test_render_first_page_returns_png_of_page_one():
    image = render_first_page(_pdf())
    assert image.startswith(b"\x89PNG")
    assert fitz.Pixmap(image).width == 595 * 2  # A4 page at 2x


def test_oauth1_header_signs_only_oauth_parameters():
    header = oauth1_header(
        "POST",
        "https://api.x.com/2/tweets",
        CREDENTIALS,
        nonce="nonce",
        timestamp="1700000000",
    )
    assert header.startswith('OAuth oauth_consumer_key="ck", oauth_nonce="nonce"')
    assert 'oauth_token="at"' in header
    assert 'oauth_signature_method="HMAC-SHA1"' in header
    assert header == oauth1_header(
        "POST",
        "https://api.x.com/2/tweets",
        CREDENTIALS,
        nonce="nonce",
        timestamp="1700000000",
    )


def test_poster_uploads_image_then_posts_with_media_and_reply():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"].startswith("OAuth ")
        if request.url.path == "/2/media/upload":
            return httpx.Response(200, json={"data": {"id": "m1"}})
        return httpx.Response(201, json={"data": {"id": f"t{len(requests)}"}})

    poster = XPoster(CREDENTIALS, httpx.Client(transport=httpx.MockTransport(handler)))
    media_id = poster.upload_image(b"png")
    post_id = poster.post("hello", media_ids=[media_id])
    poster.post("https://paperswithcode.co/paper/1", reply_to=post_id)

    assert b'name="media_category"' in requests[0].content
    assert json.loads(requests[1].content) == {
        "text": "hello",
        "media": {"media_ids": ["m1"]},
    }
    assert json.loads(requests[2].content) == {
        "text": "https://paperswithcode.co/paper/1",
        "reply": {"in_reply_to_tweet_id": "t2"},
    }


class FakeDb:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1


class FakePoster:
    def __init__(self):
        self.posts = []

    def upload_image(self, image):
        return "media"

    def post(self, text, *, media_ids=None, reply_to=None):
        self.posts.append((text, media_ids, reply_to))
        return f"post{len(self.posts)}"


def _paper(paper_id, arxiv_id):
    return SimpleNamespace(
        id=paper_id,
        source="arxiv",
        arxiv_id=arxiv_id,
        title="Great Paper",
        tldr="It works.",
    )


def test_post_trending_paper_skips_unrenderable_pdf_and_records_post(monkeypatch):
    papers = [_paper(1, "2610.00001"), _paper(2, "2610.00002")]
    monkeypatch.setattr(service, "candidate_papers", lambda db, **_: papers)

    def fetch_pdf(paper):
        if paper.id == 1:
            raise httpx.ConnectError("down")
        return _pdf()

    db, poster = FakeDb(), FakePoster()
    report = service.post_trending_paper(
        db, poster=poster, fetch_pdf=fetch_pdf, max_chars=280
    )

    assert report.paper_id == 2
    assert report.errors == [{"paper_id": 1, "error": "down"}]
    assert poster.posts == [
        ("Great Paper\nIt works.", ["media"], None),
        ("https://paperswithcode.co/paper/2610.00002", None, "post1"),
    ]
    (record,) = db.added
    assert (record.paper_id, record.post_id, record.reply_id) == (2, "post1", "post2")
    assert db.commits == 2


def test_post_trending_paper_dry_run_posts_nothing(monkeypatch):
    monkeypatch.setattr(
        service, "candidate_papers", lambda db, **_: [_paper(3, "2610.00003")]
    )
    db = FakeDb()
    report = service.post_trending_paper(
        db, poster=None, fetch_pdf=lambda paper: _pdf(), max_chars=280
    )
    assert report.dry_run and report.text == "Great Paper\nIt works."
    assert db.added == [] and report.post_id is None
