from __future__ import annotations

import json
from types import SimpleNamespace

import fitz
import httpx
import pytest

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


def test_compose_post_leads_with_the_most_striking_tldr_sentence():
    tldr = (
        "We study agents. FooNet scores 91.2% on BarBench, beating GPT-6 by "
        "4 points. It is open."
    )
    text = compose_post(
        "FooNet: A  Model", tldr, handles=["foolab"], organization="Foo", max_chars=280
    )
    assert text == (
        "FooNet scores 91.2% on BarBench, beating GPT-6 by 4 points.\n\n"
        "FooNet by @foolab"
    )


def test_compose_post_credits_the_organization_by_name_without_a_handle():
    assert compose_post(
        "FooNet: X", "It works.", organization="Foo", max_chars=280
    ) == ("It works.\n\nFooNet from Foo")
    assert compose_post("FooNet: X", "", max_chars=280) == "FooNet"


def test_striking_sentence_ignores_numbers_in_names_and_pronoun_openers():
    assert service.striking_sentence(
        "Qwen3 and GPT-6 are 27B models. Alpha scores 80."
    ) == ("Alpha scores 80.")
    assert service.striking_sentence("It scores 9. Beta scores 8.") == "Beta scores 8."


def test_paragraphs_puts_each_sentence_on_its_own_paragraph():
    assert service.paragraphs("A is 2.5x faster. B vs. C wins!\nD?  E.") == (
        "A is 2.5x faster.\n\nB vs. C wins!\n\nD?\n\nE."
    )
    assert service.paragraphs("One.\n\n\nTwo.") == "One.\n\nTwo."


def test_compose_post_truncates_a_long_sentence_but_keeps_the_credit():
    tldr = "Gamma scores 1 " + " ".join(["word"] * 100) + "."
    text = compose_post("Gamma: X", tldr, handles=["lab"], max_chars=100)
    assert text.startswith("Gamma scores 1 word")
    assert text.endswith("…\n\nGamma by @lab")
    assert weighted_length(text) <= 100


def test_compose_post_truncation_counts_the_ellipsis_as_two():
    for limit in range(20, 60):
        text = compose_post(" ".join(["word"] * 30), "", max_chars=limit)
        assert text.endswith("…")
        assert weighted_length(text) <= limit


def test_accept_post_allows_only_fact_numbers_and_the_given_mentions():
    facts = '{"tldr": "FooNet scores 91.2 on BarBench."}'
    ok = "FooNet scores 91.2 on BarBench.\n\nFooNet by @foolab"
    assert service.accept_post(ok, facts=facts, mentions=["foolab"], max_chars=280)
    for bad in (
        ok.replace("91.2", "92.1"),  # invented number
        ok.replace("@foolab", "Foo Lab"),  # dropped mention
        ok + " and @elonmusk",  # extra mention
        ok + " https://x.co",
        ok + " #ML",
    ):
        assert not service.accept_post(
            bad, facts=facts, mentions=["foolab"], max_chars=280
        )
    assert not service.accept_post(ok, facts=facts, mentions=["foolab"], max_chars=40)


def _luna_client(text=None, status=200):
    def handler(request):
        body = {
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": text}]}
            ]
        }
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _draft(handles=()):
    paper = _paper(1, "2610.00001")
    paper.tldr = "FooNet scores 91.2 on BarBench."
    return service.Draft(
        paper=paper, handles=list(handles), organization="Foo", results=[]
    )


def test_write_with_luna_keeps_a_checked_post_and_falls_back_otherwise():
    draft = _draft(["foolab"])
    good = "FooNet hits 91.2 on BarBench. FooNet by @foolab"
    assert service.write_with_luna(
        _luna_client(good), draft, api_key="k", max_chars=280
    ) == ("FooNet hits 91.2 on BarBench.\n\nFooNet by @foolab")
    template = draft.template(280)
    assert template == "FooNet scores 91.2 on BarBench.\n\nGreat Paper by @foolab"
    for client in (
        _luna_client("FooNet hits 99 on BarBench. By @foolab"),
        _luna_client(good, status=500),
    ):
        assert (
            service.write_with_luna(client, draft, api_key="k", max_chars=280)
            == template
        )


def test_organization_x_handle_needs_a_thread_by_the_org_or_its_hf_link():
    org = SimpleNamespace(name="ServiceNow", slug="servicenow", hf_slug="ServiceNow")
    threads = [("alice", "Alice"), ("ServiceNowRSRCH", "ServiceNow AI Research")]
    never = lambda slug: pytest.fail("HF should not be fetched")  # noqa: E731
    assert service.organization_x_handle(org, threads, never) == "ServiceNowRSRCH"
    assert (
        service.organization_x_handle(org, [("alice", "Alice")], lambda s: "snow")
        == "snow"
    )
    # An author's thread or a name that merely contains the org is no proof.
    assert (
        service.organization_x_handle(
            org, [("alice", "Alice"), ("x", "NotServiceNow")], lambda s: None
        )
        is None
    )
    no_hf = SimpleNamespace(name="Lab", slug=None, hf_slug=None)
    assert service.organization_x_handle(no_hf, [("y", None)], never) is None
    assert service.organization_x_handle(org, [], lambda s: "bad handle!") is None


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
        abstract="",
        organizations=[],
    )


NO_LOOKUPS = {"find_handles": lambda paper: [], "find_results": lambda paper: []}


def test_post_trending_paper_prefers_a_paper_with_a_verified_handle(monkeypatch):
    papers = [_paper(1, "2610.00001"), _paper(2, "2610.00002")]
    papers[1].organizations = [SimpleNamespace(name="Lab")]
    monkeypatch.setattr(service, "candidate_papers", lambda db, **_: papers)
    report = service.post_trending_paper(
        FakeDb(),
        poster=None,
        fetch_pdf=lambda paper: _pdf(),
        max_chars=280,
        find_handles=lambda paper: ["lab"] if paper.id == 2 else [],
        find_results=lambda paper: [],
        write=lambda draft: f"{draft.organization} {draft.handles}",
    )
    assert (report.paper_id, report.handles, report.text) == (2, ["lab"], "Lab ['lab']")
    assert report.template == "It works.\n\nGreat Paper by @lab"


def test_post_trending_paper_skips_unrenderable_pdf_and_records_post(monkeypatch):
    papers = [_paper(1, "2610.00001"), _paper(2, "2610.00002")]
    monkeypatch.setattr(service, "candidate_papers", lambda db, **_: papers)

    def fetch_pdf(paper):
        if paper.id == 1:
            raise httpx.ConnectError("down")
        return _pdf()

    db, poster = FakeDb(), FakePoster()
    report = service.post_trending_paper(
        db, poster=poster, fetch_pdf=fetch_pdf, max_chars=280, **NO_LOOKUPS
    )

    assert report.paper_id == 2
    assert report.errors == [{"paper_id": 1, "error": "down"}]
    assert poster.posts == [
        ("It works.\n\nGreat Paper", ["media"], None),
        ("https://paperswithcode.co/paper/2610.00002", None, "post1"),
    ]
    (record,) = db.added
    assert (record.paper_id, record.post_id, record.reply_id) == (2, "post1", "post2")
    assert db.commits == 2


def test_post_trending_paper_skips_unreadable_pdfs(monkeypatch):
    papers = [_paper(1, "2610.00001"), _paper(2, "2610.00002"), _paper(3, "x")]
    monkeypatch.setattr(service, "candidate_papers", lambda db, **_: papers)
    pdfs = {1: b"garbage", 2: b"%PDF-1.4\n%%EOF"}
    report = service.post_trending_paper(
        FakeDb(),
        poster=None,
        fetch_pdf=lambda paper: pdfs.get(paper.id) or _pdf(),
        max_chars=280,
        **NO_LOOKUPS,
    )
    assert report.paper_id == 3
    assert [error["paper_id"] for error in report.errors] == [1, 2]


def test_post_trending_paper_dry_run_posts_nothing(monkeypatch):
    monkeypatch.setattr(
        service, "candidate_papers", lambda db, **_: [_paper(3, "2610.00003")]
    )
    db = FakeDb()
    report = service.post_trending_paper(
        db, poster=None, fetch_pdf=lambda paper: _pdf(), max_chars=280, **NO_LOOKUPS
    )
    assert report.dry_run and report.text == "It works.\n\nGreat Paper"
    assert db.added == [] and report.post_id is None
