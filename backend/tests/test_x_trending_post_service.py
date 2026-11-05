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
    assert compose_post("FooNet: X", "", max_chars=280) is None


def test_striking_sentence_ignores_numbers_in_names_and_pronoun_openers():
    assert service.striking_sentence(
        "Qwen3 and GPT-6 are 27B models. Alpha beats Beta by 8."
    ) == ("Alpha beats Beta by 8.")
    assert service.striking_sentence("It beats A by 9. B beats C by 8.") == (
        "B beats C by 8."
    )


def test_good_lead_needs_a_comparison_for_numbers_and_no_small_delta():
    assert service.good_lead("Alpha unifies speech and vision.")
    assert service.good_lead("Alpha beats GPT-6 by 4.9 points.")
    assert service.good_lead("Alpha ranks first of 27 on MDPBench.")
    assert not service.good_lead("History Forcing reaches 79.82 on VBench-Long.")
    assert not service.good_lead("It improves scores by 0.3 points over Beta.")
    assert not service.good_lead("Alpha is +0.4% better than Beta.")
    # Words that merely start like a comparison do not count.
    assert not service.good_lead("Alpha scores 79.82 on the VBench leaderboard.")
    assert not service.good_lead("Alpha recorded 12 topics.")
    assert service.good_lead("Alpha scores 87, topping Beta.")
    assert service.good_lead("Beta is beaten by Alpha, 87 to 81.")
    assert compose_post("A: B", "Alpha scores 79.82 on VBench.", max_chars=280) is None


def test_paragraphs_puts_each_sentence_on_its_own_paragraph():
    assert service.paragraphs("A is 2.5x faster. B vs. C wins!\nD?  E.") == (
        "A is 2.5x faster.\n\nB vs. C wins!\n\nD?\n\nE."
    )
    assert service.paragraphs("One.\n\n\nTwo.") == "One.\n\nTwo."


def test_compose_post_truncates_a_long_sentence_but_keeps_the_credit():
    tldr = "Gamma beats Delta by 12 " + " ".join(["word"] * 100) + "."
    text = compose_post("Gamma: X", tldr, handles=["lab"], max_chars=100)
    assert text.startswith("Gamma beats Delta by 12 word")
    assert text.endswith("…\n\nGamma by @lab")
    assert weighted_length(text) <= 100


def test_compose_post_truncation_counts_the_ellipsis_as_two():
    for limit in range(20, 60):
        text = compose_post("T", " ".join(["word"] * 30) + ".", max_chars=limit)
        assert text.endswith("…")
        assert weighted_length(text) <= limit


def test_accept_post_allows_only_fact_numbers_and_the_given_mentions():
    facts = '{"tldr": "FooNet beats BarNet by 9.1 on BarBench, scoring 91.2."}'
    ok = "FooNet beats BarNet by 9.1 on BarBench.\n\nFooNet by @foolab"
    assert service.accept_post(ok, facts=facts, mentions=["foolab"], max_chars=280)
    for bad in (
        ok.replace("9.1", "9.2"),  # invented number
        "FooNet scores 91.2 on BarBench.\n\nFooNet by @foolab",  # bare score
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
    paper.tldr = "FooNet beats BarNet by 9.1 on BarBench."
    return service.Draft(
        paper=paper, handles=list(handles), organization="Foo", results=[]
    )


def test_write_with_luna_keeps_a_checked_post_and_falls_back_otherwise():
    draft = _draft(["foolab"])
    good = "FooNet tops BarBench, beating BarNet by 9.1. FooNet by @foolab"
    assert service.write_with_luna(
        _luna_client(good), draft, api_key="k", max_chars=280
    ) == ("FooNet tops BarBench, beating BarNet by 9.1.\n\nFooNet by @foolab")
    template = draft.template(280)
    assert template == (
        "FooNet beats BarNet by 9.1 on BarBench.\n\nGreat Paper by @foolab"
    )
    for client in (
        _luna_client("FooNet beats BarNet by 99. By @foolab"),
        _luna_client("FooNet scores 9.1 on BarBench. By @foolab"),
        _luna_client(good, status=500),
    ):
        assert (
            service.write_with_luna(client, draft, api_key="k", max_chars=280)
            == template
        )


SOTA = service.Sota(
    benchmark="FrontierScience-Olympiad",
    metric="Accuracy",
    model="Axion 1.0-122B",
    value=87.0,
    previous_model="Sage-A1.5",
    previous_value=81.0,
    entries=11,
    margin=6 / 81,
)


def test_sota_post_congratulates_a_tagged_lab_and_skips_luna():
    draft = _draft(["ByteDanceOSS"])
    draft.sota = SOTA
    never = httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail()))
    assert service.write_with_luna(never, draft, api_key="k", max_chars=280) == (
        "Congrats @ByteDanceOSS: Axion 1.0-122B is SOTA on "
        "FrontierScience-Olympiad!\n\nIt scores 87 Accuracy, ahead of Sage-A1.5 "
        "at 81."
    )
    assert service.sota_post(SOTA, [], max_chars=280) == (
        "New SOTA on FrontierScience-Olympiad: Axion 1.0-122B scores 87 Accuracy, "
        "ahead of Sage-A1.5 at 81.\n\nFirst of 11 on the Papers with Code "
        "leaderboard."
    )


class SotaDb:
    """Answers `sota_result`'s two queries: rank-1 rows and metric direction."""

    def __init__(self, evaluations, direction="higher_is_better"):
        self.evaluations, self.direction = evaluations, direction

    def execute(self, query):
        return SimpleNamespace(all=lambda: self.evaluations)

    def scalar(self, query):
        return self.direction


def _board(*values):
    """Paper 1's evaluation 1 scores values[0]; other papers the rest."""
    return [
        service.Row(index + 1, 1 if index == 0 else index + 1, f"M{index}", value)
        for index, value in enumerate(values)
    ]


def test_sota_result_needs_five_entries_and_a_one_percent_margin(monkeypatch):
    evaluation = SimpleNamespace(id=1, dataset_id=7, best_metric="Accuracy")
    db, paper = SotaDb([(evaluation, "BarBench")]), SimpleNamespace(id=1)
    boards = {
        "clear": _board(87, 81, 80, 70, 60),
        "small": _board(79.82, 79.5, 70, 60, 50),  # +0.3 points
        "few": _board(87, 81, 80, 70),
    }
    for name, board in boards.items():
        monkeypatch.setattr(service, "leaderboard_rows", lambda *_, b=board: b)
        result = service.sota_result(db, paper)
        assert (result is not None) == (name == "clear"), name
    monkeypatch.setattr(
        service, "leaderboard_rows", lambda *_: _board(4.0, 4.5, 5, 6, 7)
    )
    result = service.sota_result(SotaDb(db.evaluations, "lower_is_better"), paper)
    assert (result.value, result.previous_value, result.entries) == (4.0, 4.5, 5)


def test_notable_handles_use_the_reviewed_map_then_verified_sources():
    paper = SimpleNamespace(
        id=1,
        organizations=[
            SimpleNamespace(name="Uni", slug="uni", hf_slug="Uni"),
            SimpleNamespace(name="NVIDIA", slug="nvidia", hf_slug="nvidia"),
            SimpleNamespace(name="Tencent", slug="tencent", hf_slug="tencent"),
        ],
    )
    db = SotaDb([])  # no threads
    assert service.notable_handles(db, paper, lambda slug: None) == ["NVIDIAAIDev"]
    assert service.notable_handles(db, paper, lambda slug: "TencentGlobal") == [
        "NVIDIAAIDev",
        "TencentGlobal",
    ]
    paper.organizations = paper.organizations[:1]
    assert service.notable_handles(db, paper, lambda slug: "uni") == []


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


LAB = {
    "find_handles": lambda paper: ["lab"],
    "find_results": lambda paper: [],
    "find_sota": lambda paper: None,
}


def test_post_trending_paper_skips_papers_not_worth_posting(monkeypatch):
    papers = [_paper(index, f"2610.0000{index}") for index in (1, 2, 3, 4)]
    papers[1].tldr = "Beta scores 79.82 on VBench."  # bare score: no good lead
    monkeypatch.setattr(service, "candidate_papers", lambda db, **_: papers)
    report = service.post_trending_paper(
        FakeDb(),
        poster=None,
        fetch_pdf=lambda paper: _pdf(),
        max_chars=280,
        find_handles=lambda paper: ["lab"] if paper.id in (2, 4) else [],
        find_results=lambda paper: [],
        find_sota=lambda paper: SOTA if paper.id in (3, 4) else None,
    )
    # Paper 4 has both a SOTA and a tagged lab, so it goes first.
    assert (report.paper_id, report.reason, report.handles) == (
        4,
        "sota_and_notable_lab",
        ["lab"],
    )
    assert report.text.startswith("Congrats @lab: Axion 1.0-122B is SOTA")
    assert report.skipped == [
        {"paper_id": 1, "reason": "no clear SOTA or verified lab"}
    ]


def test_post_trending_paper_skips_the_slot_when_nothing_is_worth_it(monkeypatch):
    papers = [_paper(1, "2610.00001"), _paper(2, "2610.00002")]
    papers[1].tldr = "Beta scores 79.82 on VBench."
    monkeypatch.setattr(service, "candidate_papers", lambda db, **_: papers)
    db, poster = FakeDb(), FakePoster()
    report = service.post_trending_paper(
        db,
        poster=poster,
        fetch_pdf=lambda paper: pytest.fail("nothing should be rendered"),
        max_chars=280,
        find_handles=lambda paper: ["lab"] if paper.id == 2 else [],
        find_results=lambda paper: [],
        find_sota=lambda paper: None,
    )
    assert report.paper_id is None and poster.posts == [] and db.added == []
    assert report.skipped == [
        {"paper_id": 1, "reason": "no clear SOTA or verified lab"},
        {"paper_id": 2, "reason": "no good lead"},
    ]


def test_post_trending_paper_skips_unrenderable_pdf_and_records_post(monkeypatch):
    papers = [_paper(1, "2610.00001"), _paper(2, "2610.00002")]
    monkeypatch.setattr(service, "candidate_papers", lambda db, **_: papers)

    def fetch_pdf(paper):
        if paper.id == 1:
            raise httpx.ConnectError("down")
        return _pdf()

    db, poster = FakeDb(), FakePoster()
    report = service.post_trending_paper(
        db, poster=poster, fetch_pdf=fetch_pdf, max_chars=280, **LAB
    )

    assert report.paper_id == 2
    assert report.errors == [{"paper_id": 1, "error": "down"}]
    assert poster.posts == [
        ("It works.\n\nGreat Paper by @lab", ["media"], None),
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
        **LAB,
    )
    assert report.paper_id == 3
    assert [error["paper_id"] for error in report.errors] == [1, 2]


def test_post_trending_paper_dry_run_posts_nothing(monkeypatch):
    monkeypatch.setattr(
        service, "candidate_papers", lambda db, **_: [_paper(3, "2610.00003")]
    )
    db = FakeDb()
    report = service.post_trending_paper(
        db, poster=None, fetch_pdf=lambda paper: _pdf(), max_chars=280, **LAB
    )
    assert report.dry_run and report.text == "It works.\n\nGreat Paper by @lab"
    assert db.added == [] and report.post_id is None
