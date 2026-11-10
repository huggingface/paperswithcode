import json
from datetime import datetime, timezone

import pytest

from backend.services.openreview_import_service import (
    ImportStats,
    leading_int,
    note_row,
    parse_page,
    submission_row,
    venue_slug,
)

VENUE = "ICLR.cc/2027/Conference"


def submission(number=2, readers=("everyone",), venueid=f"{VENUE}/Submission"):
    return {
        "id": "j6wn1MIOB5",
        "number": number,
        "readers": list(readers),
        "license": "CC BY 4.0",
        "cdate": 1789000000000,
        "mdate": 1793967233346,
        "content": {
            "title": {"value": "Safe Runtime Learning"},
            "abstract": {"value": "We study ..."},
            "keywords": {"value": ["safety", "runtime learning"]},
            "primary_area": {"value": "reinforcement learning"},
            "venueid": {"value": venueid},
            "venue": {"value": "ICLR 2027 Conference Submission"},
            "pdf": {"value": "/pdf/abc.pdf"},
        },
    }


def review(note_id="qXX6sTu1er", readers=("everyone",), invitation="Official_Review"):
    return {
        "id": note_id,
        "forum": "j6wn1MIOB5",
        "replyto": "j6wn1MIOB5",
        "readers": list(readers),
        "signatures": [f"{VENUE}/Submission2/Reviewer_B3x7"],
        "invitations": [f"{VENUE}/Submission2/-/{invitation}", f"{VENUE}/-/Edit"],
        "license": "CC BY 4.0",
        "cdate": 1793848807349,
        "mdate": 1793967233346,
        "content": {
            "paper_summary": {"value": "The goal of this paper ..."},
            "rating": {"value": "4"},
            "confidence": {"value": "2: unsure"},
            "flag_for_ethics_review": {"value": "No"},
        },
    }


def test_venue_slug_matches_conference_slugs():
    assert venue_slug(VENUE) == "iclr-2027"
    assert venue_slug("NeurIPS.cc/2026/Conference") == "neurips-2026"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("4", 4),
        ("6: marginally above the threshold", 6),
        (8, 8),
        ("n/a", None),
        (None, None),
        (True, None),
    ],
)
def test_leading_int(value, expected):
    assert leading_int(value) == expected


def test_submission_row_unwraps_content():
    row = submission_row(submission(), VENUE, conference_id=132)
    assert row["title"] == "Safe Runtime Learning"
    assert row["keywords"] == ["safety", "runtime learning"]
    assert row["status"] == "Submission"
    assert row["conference_id"] == 132
    assert row["modified_at"] == datetime.fromtimestamp(1793967233.346, tz=timezone.utc)


def test_withdrawn_status_is_last_venueid_segment():
    row = submission_row(
        submission(venueid=f"{VENUE}/Withdrawn_Submission"), VENUE, None
    )
    assert row["status"] == "Withdrawn_Submission"


def test_review_row():
    row = note_row(review())
    assert row["kind"] == "official_review"
    assert row["invitation"] == "Official_Review"
    assert row["signature"] == "Reviewer_B3x7"
    assert row["rating"] == 4
    assert row["confidence"] == 2
    assert json.loads(row["content"])["paper_summary"] == "The goal of this paper ..."


def test_unknown_invitation_is_other():
    assert note_row(review(invitation="Ethics_Review_Flag"))["kind"] == "other"


def test_private_notes_are_never_kept():
    """The importing account may be a reviewer; its private view must not leak."""
    stats = ImportStats()
    replies = [
        review("public1"),
        review("private1", readers=(f"{VENUE}/Program_Committee",)),
    ]
    page = [
        (submission(), replies),
        (submission(number=3, readers=(f"{VENUE}/Authors",)), [review("other")]),
    ]
    parsed = parse_page(page, VENUE, conference_id=None, stats=stats)
    assert [row["number"] for row in parsed.submissions] == [2]
    assert [row["id"] for row in parsed.notes] == ["public1"]
    assert stats.private_notes == 1
    assert stats.private_submissions == 1
    assert stats.as_json()["notes"] == {"official_review": 1}
