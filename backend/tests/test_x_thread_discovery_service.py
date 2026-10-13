from __future__ import annotations

import time
from datetime import UTC, date, datetime

import httpx
import pytest

from backend.services.x_thread_discovery_service import (
    MAX_QUERY_LENGTH,
    X_ARCHIVE_SEARCH_URL,
    X_SEARCH_URL,
    archive_window,
    author_matches,
    build_query,
    make_x_search,
    match_posts,
    organization_matches,
    post_text_and_urls,
    short_name,
)


@pytest.mark.parametrize(
    ("display_name", "expected"),
    [
        ("Ruijin Hua", "Ruijin Hua"),
        ("ruijin hua 🦉 @ NeurIPS", "Ruijin Hua"),
        ("Artem Zholus (he/him)", "Artem Zholus"),
        ("Zhuokai Zhao | ICLR", "Zhuokai Zhao"),
        ("José García", "Jose Garcia"),
        ("Yann LeCun", None),
        ("Hua", None),
    ],
)
def test_author_matches_display_names(display_name, expected):
    authors = ["Ruijin Hua", "Artem Zholus", "Zhuokai Zhao", "Jose Garcia"]
    assert author_matches(display_name, authors) == expected


def test_author_matches_ignores_middle_names_and_initials():
    assert author_matches("Jane Doe", ["Jane Q. Doe"]) == "Jane Q. Doe"
    assert author_matches("Jane Doe", ["Jane Quinn Doe"]) == "Jane Quinn Doe"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("RoboJEPA: Scaling Robotic Latent World Models", "RoboJEPA"),
        ("SplitJEPA: Learning Invariant and Variant Latent Worlds", "SplitJEPA"),
        ("Qwen3-VL: Technical Report", "Qwen3-VL"),
        ("Attention: Is All You Need", None),
        ("Scaling Laws for Everything", None),
    ],
)
def test_short_name(title, expected):
    assert short_name(title) == expected


def test_build_query_uses_links_name_and_title():
    query = build_query(
        "2610.10515",
        "RoboJEPA: Scaling Robotic Latent World Models",
        ["http://robojepa.github.io/"],
        ["https://github.com/facebookresearch/robojepa"],
    )
    assert query == (
        '(url:"2610.10515" OR url:"robojepa.github.io" OR '
        'url:"github.com/facebookresearch/robojepa" OR "RoboJEPA" OR '
        '"Scaling Robotic Latent World Models") -is:retweet -is:reply'
    )


def test_build_query_stays_within_x_limit():
    query = build_query(
        "2610.00001",
        "A " + "very long title " * 40,
        [f"https://lab{i}.example.org/project/page" for i in range(20)],
        [],
    )
    assert len(query) <= MAX_QUERY_LENGTH
    assert query.startswith('(url:"2610.00001"')


def _response(*posts):
    return {
        "data": [
            {
                "id": post_id,
                "conversation_id": conversation,
                "author_id": author_id,
                "created_at": created,
                "public_metrics": {"like_count": likes},
            }
            for post_id, conversation, author_id, created, likes in posts
        ],
        "includes": {
            "users": [
                {"id": "u1", "name": "Ruijin Hua", "username": "Helios_Hua"},
                {"id": "u2", "name": "Zhuokai Zhao", "username": "zkzhao"},
                {"id": "u3", "name": "AK", "username": "_akhaliq"},
            ]
        },
    }


def test_match_posts_keeps_best_original_post_per_author():
    response = _response(
        ("10", "10", "u1", "2026-10-11T10:00:00Z", 511),
        ("11", "11", "u1", "2026-10-11T12:00:00Z", 20),
        ("12", "10", "u1", "2026-10-11T10:05:00Z", 900),  # reply in own thread
        ("13", "13", "u3", "2026-10-11T09:00:00Z", 2000),  # not an author
        ("14", "14", "u2", "2026-10-11T11:00:00Z", 40),
        ("15", "15", "u2", "2026-08-01T11:00:00Z", 999),  # before the paper
    )
    matches = match_posts(
        response, ["Ruijin Hua", "Zichuan Liu", "Zhuokai Zhao"], date(2026, 10, 10)
    )
    assert [(m["url"], m["author"], m["likes"]) for m in matches] == [
        ("https://x.com/Helios_Hua/status/10", "Ruijin Hua", 511),
        ("https://x.com/zkzhao/status/14", "Zhuokai Zhao", 40),
    ]


def test_match_posts_handles_empty_results():
    assert match_posts({"meta": {"result_count": 0}}, ["Ruijin Hua"], None) == []


def test_author_matches_nickname_through_handle():
    authors = ["Wei Huang", "Yukang Chen"]
    assert author_matches("Aaron Huang", authors, "AaronWeiHuang") == "Wei Huang"
    assert author_matches("Aaron Huang", authors, "aaronh") is None


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        (
            {"name": "NVIDIA AI", "username": "NVIDIAAI", "verified_type": "business"},
            "NVIDIA",
        ),
        (
            {"name": "AI at Meta", "username": "AIatMeta", "verified_type": "business"},
            "Meta",
        ),
        ({"name": "Ai2", "username": "allen_ai", "verified_type": "business"}, "Ai2"),
        ({"name": "NVIDIA fan", "username": "nvfan", "verified_type": "blue"}, None),
        ({"name": "NVIDIA AI", "username": "NVIDIAAI"}, None),
        ({"name": "OpenAI", "username": "OpenAI", "verified_type": "business"}, None),
    ],
)
def test_organization_matches_only_business_accounts_of_linked_orgs(user, expected):
    assert organization_matches(user, ["NVIDIA", "Meta", "Ai2"]) == expected


def test_match_posts_accepts_organization_accounts_but_not_outsiders():
    response = {
        "data": [
            {
                "id": "20",
                "conversation_id": "20",
                "author_id": "o1",
                "created_at": "2026-10-11T10:00:00Z",
                "public_metrics": {"like_count": 300},
            },
            {
                "id": "21",
                "conversation_id": "21",
                "author_id": "x1",
                "created_at": "2026-10-11T10:00:00Z",
                "public_metrics": {"like_count": 5000},
            },
        ],
        "includes": {
            "users": [
                {
                    "id": "o1",
                    "name": "NVIDIA Robotics",
                    "username": "NVIDIARobotics",
                    "verified_type": "business",
                },
                {
                    "id": "x1",
                    "name": "AK",
                    "username": "_akhaliq",
                    "verified_type": "blue",
                },
            ]
        },
    }
    matches = match_posts(response, ["Wei Huang"], date(2026, 10, 10), ["NVIDIA"])
    assert [(m["handle"], m["author"], m["kind"]) for m in matches] == [
        ("NVIDIARobotics", "NVIDIA", "organization")
    ]


def test_archive_window_brackets_publication():
    now = datetime(2026, 10, 12, 12, tzinfo=UTC)
    assert archive_window(date(2026, 5, 20), now) == (
        "2026-05-13T00:00:00Z",
        "2026-07-19T00:00:00Z",
    )


def test_archive_window_ends_before_now_for_recent_papers():
    now = datetime(2026, 10, 12, 12, tzinfo=UTC)
    assert archive_window(date(2026, 10, 1), now)[1] == "2026-10-12T11:59:00Z"


def test_make_x_search_uses_full_archive_window(monkeypatch):
    calls = []

    def fake_get(url, *, params, headers, timeout):
        calls.append((url, params))
        return httpx.Response(200, json={}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    make_x_search("token")("q", date(2026, 5, 20))
    make_x_search("token", full_archive=True)("q", date(2026, 5, 20))

    (recent_url, recent), (archive_url, archive) = calls
    assert recent_url == X_SEARCH_URL
    assert "start_time" not in recent
    assert archive_url == X_ARCHIVE_SEARCH_URL
    assert archive["start_time"] == "2026-05-13T00:00:00Z"
    assert archive["sort_order"] == "relevancy"


def test_build_query_keeps_project_path_on_shared_hosts():
    query = build_query(
        None,
        "ROWBench: Do Video Models Render What the Program Specifies?",
        ["https://alaya-lab.github.io/PROWBench"],
        [],
    )
    assert 'url:"alaya-lab.github.io/PROWBench"' in query
    assert 'url:"alaya-lab.github.io"' not in query


def test_post_text_and_urls_prefers_long_form_text_and_unwound_links():
    post = {
        "text": "Short https://t.co/x",
        "entities": {
            "urls": [{"url": "https://t.co/x", "expanded_url": "https://a.io"}]
        },
        "note_tweet": {
            "text": "Long form text",
            "entities": {
                "urls": [
                    {
                        "url": "https://t.co/y",
                        "expanded_url": "https://t.co/y",
                        "unwound_url": "https://arxiv.org/abs/2610.00001",
                    }
                ]
            },
        },
    }
    assert post_text_and_urls(post) == (
        "Long form text",
        ["https://arxiv.org/abs/2610.00001"],
    )
    assert post_text_and_urls({"text": "Plain"}) == ("Plain", [])
