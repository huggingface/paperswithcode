from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import fitz
import httpx

from backend.services import x_insight_post_service as service
from backend.services.x_insight_cards import Bar, render_bar_card, render_list_card
from backend.services.x_insight_post_service import (
    Insight,
    accept_rewrite,
    compose_list,
    fmt,
    paper_label,
)


def test_fmt_keeps_at_most_two_decimals():
    assert [fmt(99.8), fmt(99.554), fmt(12.0), fmt(1234.56)] == [
        "99.8",
        "99.55",
        "12",
        "1234.6",
    ]


def test_paper_label_prefers_the_name_before_the_colon():
    assert paper_label("nanoMuse: An Open-Source Personal Agent") == "nanoMuse"
    assert paper_label("Short Title") == "Short Title"
    long = "A Very Long Title Without Any Colon That Keeps Going And Going Forever"
    assert paper_label(long) == "A Very Long Title Without Any Colon That Keeps…"


def test_compose_list_drops_entries_to_fit_but_keeps_three():
    labels = ["x" * 80] * 5
    text = compose_list("Top papers:", labels)
    assert text.count("\n") == 4  # head, blank line, three entries
    assert compose_list("Top:", ["A", "B", "C"]) == "Top:\n\n1. A\n2. B\n3. C"


def test_accept_rewrite_guards_numbers_links_and_length():
    draft = "GPT-6 Astra: 27 papers in 30 days, 18x its share."
    facts = '{"paper": "A 3D-native model"}'
    ok = "In 30 days, 27 papers used GPT-6 Astra: 18x its share."
    assert accept_rewrite(draft, ok, facts=facts, max_chars=280)
    assert accept_rewrite(draft, ok + " A 3D model.", facts=facts, max_chars=280)
    assert not accept_rewrite(draft, ok.replace("27", "28"), facts=facts, max_chars=280)
    assert not accept_rewrite(
        draft, ok.replace("18x", "many"), facts=facts, max_chars=280
    )
    assert not accept_rewrite(draft, ok + " #AI", facts=facts, max_chars=280)
    assert not accept_rewrite(draft, ok + " https://x.co", facts=facts, max_chars=280)
    assert not accept_rewrite(draft, ok, facts=facts, max_chars=20)


def test_cards_render_16_by_9_pngs():
    bar = render_bar_card(
        "New SOTA on LIBERO",
        "Robotics",
        [Bar("UNITAS", 99.8, "99.8", True), Bar("Other", 99.5, "99.5")],
    )
    lower = render_bar_card(
        "MASE",
        "lower",
        [Bar("a", 0.7, "0.7", True), Bar("b", 0.9, "0.9")],
        lower_is_better=True,
    )
    listing = render_list_card("Top papers", "This week", ["One", "Two", "Three"])
    for image in (bar, lower, listing):
        pixmap = fitz.Pixmap(image)
        assert (pixmap.width, pixmap.height) == (1200, 675)


class FakeDb:
    def __init__(self, last=()):
        self.last = list(last)
        self.added = []
        self.commits = 0

    def execute(self, query):
        return SimpleNamespace(all=lambda: self.last)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1


def test_plan_kinds_morning_roundups_then_sota_evening_rotation():
    monday_first = datetime(2026, 6, 1, 9, 43, tzinfo=UTC)  # a Monday
    assert service.plan_kinds(FakeDb(), monday_first) == [
        "top_papers_month",
        "top_papers_week",
        "new_sota",
        "trending_benchmark",
        "trending_method",
        "trending_task",
    ]
    evening = datetime(2026, 6, 2, 17, 43, tzinfo=UTC)
    posted = [
        ("trending_benchmark", datetime(2026, 6, 1, tzinfo=UTC)),
        ("trending_method", datetime(2026, 5, 30, tzinfo=UTC)),
        ("new_sota", datetime(2026, 6, 2, 9, 43, tzinfo=UTC)),
    ]
    assert service.plan_kinds(FakeDb(posted), evening) == [
        "trending_task",
        "trending_method",
        "trending_benchmark",
    ]


def test_plan_kinds_catches_up_missed_roundups_in_a_late_morning_run():
    late_tuesday_second = datetime(2026, 6, 2, 13, 5, tzinfo=UTC)
    assert service.plan_kinds(FakeDb(), late_tuesday_second)[:3] == [
        "top_papers_month",
        "top_papers_week",
        "new_sota",
    ]
    thursday_fourth = datetime(2026, 6, 4, 9, 43, tzinfo=UTC)
    assert service.plan_kinds(FakeDb(), thursday_fourth)[0] == "new_sota"


def test_write_with_luna_falls_back_to_the_template_on_errors():
    insight = Insight("trending_task", "agents", "Agents rise 4.2x.", "l", b"")

    def failing(request):
        return httpx.Response(429, json={"error": "rate limited"})

    def malformed(request):
        return httpx.Response(200, json={"unexpected": True})

    for handler in (failing, malformed):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        assert (
            service.write_with_luna(client, insight, api_key="k", max_chars=280)
            == "Agents rise 4.2x."
        )


def test_write_with_luna_keeps_a_valid_rewrite():
    insight = Insight("trending_task", "agents", "Agents rise 4.2x.", "l", b"")
    output = [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "Agents: up 4.2x."}],
        }
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"output": output})
        )
    )
    assert (
        service.write_with_luna(client, insight, api_key="k", max_chars=280)
        == "Agents: up 4.2x."
    )


class FakePoster:
    def __init__(self):
        self.posts = []

    def upload_image(self, image):
        return "media"

    def post(self, text, *, media_ids=None, reply_to=None):
        self.posts.append((text, media_ids, reply_to))
        return f"post{len(self.posts)}"


def test_post_insight_skips_empty_kinds_and_records_the_post(monkeypatch):
    insight = Insight("trending_task", "agents", "Agents rise.", "https://l", b"png")
    monkeypatch.setitem(service.BUILDERS, "new_sota", lambda db, now: None)
    monkeypatch.setitem(service.BUILDERS, "trending_task", lambda db, now: insight)
    db, poster = FakeDb(), FakePoster()
    report = service.post_insight(
        db,
        poster=poster,
        kinds=["new_sota", "trending_task"],
        write=lambda item: "Agents keep rising.",
        max_chars=280,
    )
    assert report.tried == ["new_sota", "trending_task"]
    assert poster.posts == [
        ("Agents keep rising.", ["media"], None),
        ("https://l", None, "post1"),
    ]
    (record,) = db.added
    assert (record.kind, record.subject_key, record.reply_id) == (
        "trending_task",
        "agents",
        "post2",
    )


def test_post_insight_dry_run_posts_nothing(monkeypatch):
    insight = Insight("trending_task", "agents", "Agents rise.", "https://l", b"png")
    monkeypatch.setitem(service.BUILDERS, "trending_task", lambda db, now: insight)
    db = FakeDb()
    report = service.post_insight(
        db, poster=None, kinds=["trending_task"], write=lambda i: i.text, max_chars=280
    )
    assert report.dry_run and report.text == "Agents rise." and db.added == []
