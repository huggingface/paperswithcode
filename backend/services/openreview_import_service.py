"""Import public OpenReview submissions and their replies into PwC.

OpenReview API v2 returns each submission with its forum replies
(`details=replies`). This module turns those JSON notes into rows for
`openreview_submissions` and `openreview_notes` and writes them.

Only notes readable by `everyone` are kept. The importing account may be a
reviewer, area chair or author at the venue and then sees confidential notes;
those must never reach PwC.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

KIND_BY_INVITATION = {
    "Official_Review": "official_review",
    "Meta_Review": "meta_review",
    "Decision": "decision",
    "Official_Comment": "official_comment",
    "Public_Comment": "public_comment",
    "Rebuttal": "rebuttal",
    "Withdrawal": "withdrawal",
    "Desk_Rejection": "desk_rejection",
}

# Normalized titles shorter than this ("Introduction", "Attention") are too
# generic to identify a paper.
MIN_LINK_TITLE_LENGTH = 20


@dataclass
class ImportStats:
    pages: int = 0
    submissions: int = 0
    private_submissions: int = 0
    notes: Counter = field(default_factory=Counter)
    private_notes: int = 0
    removed_notes: int = 0
    linked_papers: int = 0

    def as_json(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "submissions": self.submissions,
            "private_submissions_skipped": self.private_submissions,
            "notes": dict(sorted(self.notes.items())),
            "private_notes_skipped": self.private_notes,
            "removed_notes": self.removed_notes,
            "linked_papers": self.linked_papers,
        }


def venue_slug(venue_id: str) -> str:
    """'ICLR.cc/2027/Conference' -> 'iclr-2027' (the PwC conference slug)."""
    series, year = venue_id.split("/")[:2]
    return f"{series.split('.')[0].lower()}-{year}"


def is_public(note: dict[str, Any]) -> bool:
    return "everyone" in note.get("readers", ())


def unwrap(content: dict[str, Any]) -> dict[str, Any]:
    """OpenReview v2 wraps each field as {"value": ...}; return plain values."""
    return {
        key: item["value"]
        for key, item in content.items()
        if isinstance(item, dict) and "value" in item
    }


def leading_int(value: Any) -> Optional[int]:
    """'6: marginally above the threshold' -> 6; '4' -> 4; 4 -> 4."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    match = re.match(r"\s*(-?\d+)", str(value)) if value is not None else None
    return int(match.group(1)) if match else None


def last_segment(value: str, separator: str) -> str:
    return value.rsplit(separator, 1)[-1]


def timestamp(milliseconds: Optional[int]) -> Optional[datetime]:
    if milliseconds is None:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)


def submission_row(
    note: dict[str, Any], venue_id: str, conference_id: Optional[int]
) -> Optional[dict[str, Any]]:
    if not is_public(note):
        return None
    content = unwrap(note["content"])
    keywords = content.get("keywords") or []
    return {
        "id": note["id"],
        "venue_id": venue_id,
        "conference_id": conference_id,
        "number": note["number"],
        "title": content.get("title") or "",
        "abstract": content.get("abstract"),
        "keywords": [str(k) for k in keywords] if isinstance(keywords, list) else [],
        "primary_area": content.get("primary_area"),
        "status": last_segment(content.get("venueid") or "Submission", "/"),
        "venue": content.get("venue"),
        "pdf_path": content.get("pdf"),
        "license": note.get("license"),
        "created_at": timestamp(note.get("cdate") or note.get("tcdate")),
        "modified_at": timestamp(note.get("mdate") or note.get("tmdate")),
    }


def note_row(reply: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not is_public(reply):
        return None
    invitation = last_segment(reply["invitations"][0], "/-/")
    content = unwrap(reply["content"])
    signature = last_segment(reply["signatures"][0], "/") if reply["signatures"] else ""
    return {
        "id": reply["id"],
        "forum_id": reply["forum"],
        "reply_to": reply.get("replyto"),
        "kind": KIND_BY_INVITATION.get(invitation, "other"),
        "invitation": invitation[:100],
        "signature": signature[:100],
        "content": json.dumps(content),
        "rating": leading_int(content.get("rating")),
        "confidence": leading_int(content.get("confidence")),
        "license": reply.get("license"),
        "created_at": timestamp(reply.get("cdate") or reply.get("tcdate")),
        "modified_at": timestamp(reply.get("mdate") or reply.get("tmdate")),
    }


@dataclass
class ParsedPage:
    submissions: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)


def parse_page(
    page: Iterable[tuple[dict[str, Any], list[dict[str, Any]]]],
    venue_id: str,
    conference_id: Optional[int],
    stats: ImportStats,
) -> ParsedPage:
    """Parse (submission, replies) pairs, dropping everything not public."""
    parsed = ParsedPage()
    for submission, replies in page:
        row = submission_row(submission, venue_id, conference_id)
        if row is None:
            stats.private_submissions += 1
            continue
        parsed.submissions.append(row)
        for reply in replies:
            reply_row = note_row(reply)
            if reply_row is None:
                stats.private_notes += 1
                continue
            parsed.notes.append(reply_row)
            stats.notes[reply_row["kind"]] += 1
    stats.submissions += len(parsed.submissions)
    return parsed


UPSERT_SUBMISSION_SQL = text(
    """
    INSERT INTO openreview_submissions
        (id, venue_id, conference_id, number, title, abstract, keywords,
         primary_area, status, venue, pdf_path, license, created_at,
         modified_at, fetched_at)
    VALUES
        (:id, :venue_id, :conference_id, :number, :title, :abstract, :keywords,
         :primary_area, :status, :venue, :pdf_path, :license, :created_at,
         :modified_at, now())
    ON CONFLICT (id) DO UPDATE SET
        conference_id = EXCLUDED.conference_id,
        title = EXCLUDED.title,
        abstract = EXCLUDED.abstract,
        keywords = EXCLUDED.keywords,
        primary_area = EXCLUDED.primary_area,
        status = EXCLUDED.status,
        venue = EXCLUDED.venue,
        pdf_path = EXCLUDED.pdf_path,
        license = EXCLUDED.license,
        modified_at = EXCLUDED.modified_at,
        fetched_at = now(),
        -- A retitled submission must be matched again.
        paper_id = CASE WHEN openreview_submissions.title = EXCLUDED.title
                        THEN openreview_submissions.paper_id END
    """
)

UPSERT_NOTE_SQL = text(
    """
    INSERT INTO openreview_notes
        (id, forum_id, reply_to, kind, invitation, signature, content, rating,
         confidence, license, created_at, modified_at, fetched_at)
    VALUES
        (:id, :forum_id, :reply_to, :kind, :invitation, :signature,
         cast(:content AS jsonb), :rating, :confidence, :license, :created_at,
         :modified_at, now())
    ON CONFLICT (id) DO UPDATE SET
        reply_to = EXCLUDED.reply_to,
        kind = EXCLUDED.kind,
        invitation = EXCLUDED.invitation,
        signature = EXCLUDED.signature,
        content = EXCLUDED.content,
        rating = EXCLUDED.rating,
        confidence = EXCLUDED.confidence,
        license = EXCLUDED.license,
        modified_at = EXCLUDED.modified_at,
        fetched_at = now(),
        removed_at = NULL
    """
)

MARK_REMOVED_SQL = text(
    """
    UPDATE openreview_notes
    SET removed_at = now()
    WHERE forum_id = ANY(cast(:forum_ids AS varchar[]))
      AND NOT (id = ANY(cast(:seen_ids AS varchar[])))
      AND removed_at IS NULL
    """
)

# Link each unmatched submission to the one latest-version paper with the same
# normalized title; ambiguous titles stay unlinked.
LINK_PAPERS_SQL = text(
    """
    WITH wanted AS (
        SELECT id, regexp_replace(lower(title), '[^a-z0-9]+', '', 'g') AS key
        FROM openreview_submissions
        WHERE venue_id = :venue_id AND paper_id IS NULL
    ),
    matches AS (
        SELECT w.id, min(p.id) AS paper_id
        FROM wanted w
        JOIN papers p
          ON regexp_replace(lower(p.title), '[^a-z0-9]+', '', 'g') = w.key
        WHERE p.is_latest_version AND length(w.key) >= :min_length
        GROUP BY w.id
        HAVING count(*) = 1
    )
    UPDATE openreview_submissions s
    SET paper_id = m.paper_id
    FROM matches m
    WHERE s.id = m.id
    """
)


def write_page(db: Session, parsed: ParsedPage, stats: ImportStats) -> None:
    """Upsert one parsed page and mark notes that are no longer public."""
    if parsed.submissions:
        db.execute(UPSERT_SUBMISSION_SQL, parsed.submissions)
    if parsed.notes:
        db.execute(UPSERT_NOTE_SQL, parsed.notes)
    if parsed.submissions:
        result = db.execute(
            MARK_REMOVED_SQL,
            {
                "forum_ids": [row["id"] for row in parsed.submissions],
                "seen_ids": [row["id"] for row in parsed.notes],
            },
        )
        stats.removed_notes += result.rowcount


def link_papers(db: Session, venue_id: str) -> int:
    result = db.execute(
        LINK_PAPERS_SQL,
        {"venue_id": venue_id, "min_length": MIN_LINK_TITLE_LENGTH},
    )
    return result.rowcount


def conference_id_for(db: Session, venue_id: str) -> Optional[int]:
    return db.execute(
        text("SELECT id FROM conferences WHERE slug = :slug"),
        {"slug": venue_slug(venue_id)},
    ).scalar()
