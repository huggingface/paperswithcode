"""Post the top trending paper to the Papers with Code X account.

Each run picks the highest-trending recent arXiv paper with a TL;DR that has
not been posted yet, renders the first page of its PDF as an image, and posts
the title, a new line, and the TL;DR with that image. The paper page link
follows as a reply, so the main post carries no link. `paper_x_posts` records
every posted paper so it is never posted twice.

X calls use OAuth 1.0a user context, whose tokens do not expire.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable
from urllib.parse import quote

import fitz
import httpx
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from backend.models.database import Paper, PaperXPost
from backend.utils.urls import get_paper_route_identifier

logger = logging.getLogger(__name__)

X_API = "https://api.x.com/2"
CANDIDATE_WINDOW_DAYS = 14
CANDIDATES_PER_RUN = 5
RENDER_ZOOM = 2.0
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ELLIPSIS = "…"
# Download failures, unreadable PDFs (PyMuPDF raises FileDataError, a
# RuntimeError, or low-level FzErrorBase), and PDFs without pages.
RENDER_ERRORS = (
    httpx.HTTPError,
    ValueError,
    RuntimeError,
    IndexError,
    fitz.mupdf.FzErrorBase,
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class XCredentials:
    consumer_key: str
    consumer_secret: str
    access_token: str
    access_token_secret: str


def _percent(value: str) -> str:
    return quote(value, safe="-._~")


def oauth1_header(
    method: str,
    url: str,
    credentials: XCredentials,
    *,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> str:
    """OAuth 1.0a HMAC-SHA1 header; JSON and multipart bodies are not signed."""
    params = {
        "oauth_consumer_key": credentials.consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": credentials.access_token,
        "oauth_version": "1.0",
    }
    normalized = "&".join(
        f"{_percent(key)}={_percent(value)}" for key, value in sorted(params.items())
    )
    base = "&".join([method.upper(), _percent(url), _percent(normalized)])
    key = (
        f"{_percent(credentials.consumer_secret)}&"
        f"{_percent(credentials.access_token_secret)}"
    )
    digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    params["oauth_signature"] = base64.b64encode(digest).decode()
    return "OAuth " + ", ".join(
        f'{_percent(key)}="{_percent(value)}"' for key, value in sorted(params.items())
    )


class XPoster:
    """Minimal X API v2 client for image uploads and posts."""

    def __init__(self, credentials: XCredentials, client: httpx.Client) -> None:
        self.credentials = credentials
        self.client = client

    def _post(self, url: str, **kwargs: Any) -> dict:
        headers = {"Authorization": oauth1_header("POST", url, self.credentials)}
        response = self.client.post(url, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(
                f"X HTTP {response.status_code} for {url}: {response.text[:500]}"
            )
        return response.json()

    def upload_image(self, image: bytes) -> str:
        body = self._post(
            f"{X_API}/media/upload",
            files={"media": ("page.png", image, "image/png")},
            data={"media_category": "tweet_image"},
        )
        return body["data"]["id"]

    def post(
        self,
        text: str,
        *,
        media_ids: list[str] | None = None,
        reply_to: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {"text": text}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}
        return self._post(f"{X_API}/tweets", json=payload)["data"]["id"]


def weighted_length(text: str) -> int:
    """X's weighted character count: Latin and common punctuation count 1, else 2."""
    return sum(
        1
        if ord(char) <= 0x10FF
        or 0x2000 <= ord(char) <= 0x200D
        or 0x2010 <= ord(char) <= 0x201F
        or 0x2032 <= ord(char) <= 0x2037
        else 2
        for char in text
    )


def _truncate(text: str, limit: int) -> str:
    """Cut at a word boundary so the result plus an ellipsis fits `limit`."""
    limit -= weighted_length(ELLIPSIS)
    while text and weighted_length(text) > limit:
        cut = text.rfind(" ")
        text = text[:cut] if cut > 0 else text[:-1]
    return text.rstrip(" ,;:") + ELLIPSIS


def compose_post(title: str, tldr: str, *, max_chars: int) -> str:
    """Title, a new line, then the TL;DR; drop trailing sentences to fit."""
    title = " ".join(title.split())
    sentences = _SENTENCE_END.split(" ".join(tldr.split()))
    while sentences:
        text = f"{title}\n{' '.join(sentences)}"
        if weighted_length(text) <= max_chars:
            return text
        if len(sentences) == 1:
            break
        sentences.pop()
    head = f"{title}\n"
    room = max_chars - weighted_length(head)
    if sentences and room >= 40:
        return head + _truncate(sentences[0], room)
    return _truncate(title, max_chars)


def render_first_page(pdf: bytes) -> bytes:
    """Render page one as PNG, lowering the resolution until it fits X's limit."""
    zoom = RENDER_ZOOM
    with fitz.open(stream=pdf, filetype="pdf") as document:
        page = document[0]
        while True:
            image = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
            if len(image) <= MAX_IMAGE_BYTES or zoom <= 1:
                return image
            zoom -= 0.25


def paper_url(paper: Paper) -> str:
    route = get_paper_route_identifier(paper.source, paper.arxiv_id, paper.id)
    return f"https://paperswithcode.co/paper/{route}"


def candidate_papers(db: Session, *, today: date, limit: int) -> list[Paper]:
    """Recent trending arXiv papers with a TL;DR that were never posted."""
    since = today - timedelta(days=CANDIDATE_WINDOW_DAYS)
    return list(
        db.scalars(
            select(Paper)
            .where(
                Paper.is_latest_version,
                Paper.source == "arxiv",
                Paper.arxiv_id.is_not(None),
                Paper.date_published >= since,
                Paper.trending_score > 0,
                func.length(func.trim(Paper.tldr)) > 0,
                ~exists().where(PaperXPost.paper_id == Paper.id),
            )
            .order_by(Paper.trending_score.desc(), Paper.id.desc())
            .limit(limit)
        )
    )


@dataclass
class PostReport:
    dry_run: bool
    paper_id: int | None = None
    arxiv_id: str | None = None
    text: str | None = None
    url: str | None = None
    post_id: str | None = None
    reply_id: str | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "paper_id": self.paper_id,
            "arxiv_id": self.arxiv_id,
            "text": self.text,
            "url": self.url,
            "post_id": self.post_id,
            "reply_id": self.reply_id,
            "errors": self.errors,
        }


def post_trending_paper(
    db: Session,
    *,
    poster: XPoster | None,
    fetch_pdf: Callable[[Paper], bytes],
    max_chars: int,
    today: date | None = None,
    save_image: Callable[[bytes], None] | None = None,
) -> PostReport:
    """Post the top unposted trending paper; without a poster, only preview it.

    A paper whose PDF cannot be fetched or rendered is skipped for the next
    candidate. The post is recorded before the link reply, so a failed reply
    never causes the paper to be posted again.
    """
    report = PostReport(dry_run=poster is None)
    today = today or datetime.now(UTC).date()
    for paper in candidate_papers(db, today=today, limit=CANDIDATES_PER_RUN):
        try:
            image = render_first_page(fetch_pdf(paper))
        except RENDER_ERRORS as error:
            report.errors.append({"paper_id": paper.id, "error": str(error)[:300]})
            continue
        report.paper_id = paper.id
        report.arxiv_id = paper.arxiv_id
        report.text = compose_post(paper.title, paper.tldr or "", max_chars=max_chars)
        report.url = paper_url(paper)
        if save_image:
            save_image(image)
        if poster is None:
            return report
        media_id = poster.upload_image(image)
        report.post_id = poster.post(report.text, media_ids=[media_id])
        record = PaperXPost(
            paper_id=paper.id, post_id=report.post_id, posted_at=datetime.now(UTC)
        )
        db.add(record)
        db.commit()
        report.reply_id = poster.post(report.url, reply_to=report.post_id)
        record.reply_id = report.reply_id
        db.commit()
        return report
    return report
