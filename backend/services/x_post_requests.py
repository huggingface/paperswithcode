"""Admin "Tweet it" requests for the Papers with Code X account.

An admin clicks "Tweet it" on a paper page. The off-box X agent (see
`backend/scripts/x_post_candidates.py`) fetches the open requests every run,
drafts each paper, and puts it at the front of its post queue in request
order: the first request posts next, the second after it, and so on.

A request is resolved when the post goes out (`record` in
`x_post_candidates`), when the admin cancels it, or when the agent drops the
post from its queue. Requesting a resolved, unposted paper again reopens it
at the back of the line.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models.database import Paper, PaperXPost, XInsightPost, XPostRequest
from backend.services.x_post_candidates import (
    PAPER_POST_KINDS,
    paper_candidate,
    posted_paper_ids,
)

ACCOUNT_URL = "https://x.com/paperswithcodee/status/"
RESOLUTIONS = ("posted", "cancelled", "removed")


class PaperNotFoundError(LookupError):
    pass


class AlreadyPostedError(ValueError):
    pass


@dataclass
class RequestStatus:
    state: str  # "none", "requested", "posted"
    position: int | None = None
    requested_at: datetime | None = None
    post_url: str | None = None


def open_requests(db: Session) -> list[XPostRequest]:
    """Open requests, oldest first: the order the agent posts them in."""
    return list(
        db.scalars(
            select(XPostRequest)
            .where(XPostRequest.resolved_at.is_(None))
            .order_by(XPostRequest.requested_at, XPostRequest.paper_id)
        )
    )


def post_url(db: Session, paper_id: int) -> str | None:
    """The latest X post about this paper, if the account made one. SOTA keys
    end with the paper id (`subject_paper_id`), other paper kinds are the id."""
    key = str(paper_id)
    post_id = db.scalar(
        select(XInsightPost.post_id)
        .where(
            XInsightPost.kind.in_(PAPER_POST_KINDS),
            or_(
                XInsightPost.subject_key == key,
                XInsightPost.subject_key.endswith(f":{key}"),
            ),
        )
        .order_by(XInsightPost.posted_at.desc())
        .limit(1)
    ) or db.scalar(select(PaperXPost.post_id).where(PaperXPost.paper_id == paper_id))
    return f"{ACCOUNT_URL}{post_id}" if post_id else None


def request_status(db: Session, paper_id: int) -> RequestStatus:
    requests = open_requests(db)
    for position, request in enumerate(requests, 1):
        if request.paper_id == paper_id:
            return RequestStatus("requested", position, request.requested_at)
    if paper_id in posted_paper_ids(db):
        return RequestStatus("posted", post_url=post_url(db, paper_id))
    return RequestStatus("none")


def request_post(
    db: Session, paper_id: int, *, requested_by: str | None, now: datetime | None = None
) -> RequestStatus:
    """Put the paper at the back of the line of open requests (a repeated
    click on an open request keeps its place)."""
    if db.get(Paper, paper_id) is None:
        raise PaperNotFoundError(f"paper {paper_id} not found")
    if paper_id in posted_paper_ids(db):
        raise AlreadyPostedError(f"paper {paper_id} was already posted on X")
    request = db.get(XPostRequest, paper_id)
    if request is None:
        request = XPostRequest(paper_id=paper_id)
        db.add(request)
    if request.resolved_at is not None or request.requested_at is None:
        request.requested_at = now or datetime.now(UTC)
        request.requested_by = requested_by
        request.resolved_at = None
        request.resolution = None
    db.commit()
    return request_status(db, paper_id)


def resolve_request(
    db: Session, paper_id: int, resolution: str, *, now: datetime | None = None
) -> bool:
    """Close an open request; False when there is none."""
    if resolution not in RESOLUTIONS:
        raise ValueError(f"unknown resolution {resolution!r}")
    request = db.get(XPostRequest, paper_id)
    if request is None or request.resolved_at is not None:
        return False
    request.resolved_at = now or datetime.now(UTC)
    request.resolution = resolution
    db.commit()
    return True


def requested_candidates(db: Session) -> list[dict[str, Any]]:
    """Every open request as a paper candidate for the agent, in post order,
    with the request's position and time in its facts."""
    posted = posted_paper_ids(db)
    requests = []
    for request in open_requests(db):
        if request.paper_id in posted:  # e.g. a SOTA post went out meanwhile
            request.resolved_at, request.resolution = datetime.now(UTC), "posted"
        else:
            requests.append(request)
    db.commit()
    papers = {
        p.id: p
        for p in db.scalars(
            select(Paper).where(Paper.id.in_([r.paper_id for r in requests]))
        )
    }
    items = []
    for position, request in enumerate(requests, 1):
        candidate = paper_candidate(db, papers[request.paper_id], rank=None)
        item = candidate.to_dict()
        item["facts"]["requested_by_admin"] = True
        item["request_position"] = position
        item["requested_at"] = request.requested_at.isoformat()
        items.append(item)
    return items
