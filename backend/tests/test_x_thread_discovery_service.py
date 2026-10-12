from __future__ import annotations

from datetime import date

import pytest

from backend.services.x_thread_discovery_service import (
    MAX_QUERY_LENGTH,
    author_matches,
    build_query,
    match_posts,
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
