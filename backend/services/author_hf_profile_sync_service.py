"""Link authors to the Hugging Face accounts that claimed their papers.

Hugging Face users claim authorship of a paper on its HF page, usually days
after the paper was imported here. The paper list at
``https://huggingface.co/api/papers`` carries each claim (author name plus HF
user), newest papers first, so a bounded walk over recent papers picks up late
claims and refreshed avatars at 100 papers per request.

Each HF account has its own author row, which lists only the papers the
account claimed. A claim moves the paper's link from the author matched by name
(arXiv lists names only) to the account's row, creating that row the first time
the account is seen, and marks the link claimed. Other papers of the name-matched
author stay where they are, so namesakes never end up on someone's profile. The
job never moves an account from one author row to another.

An account's row takes the HF full name once the account claims a paper under
that byline, so someone who changed their name shows it on all their papers,
including ones published under a former name.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.database import Author, Paper, PaperAuthor
from backend.services.author_service import normalize_arxiv_author_name

HF_PAPERS_URL = "https://huggingface.co/api/papers"
HF_PAPERS_PAGE_SIZE = 100
# HF allows 500 requests per 5 minutes; stay well below it.
HF_PAGE_PAUSE_SECONDS = 1.0
# HF's own name-based guesses, not yet confirmed (or rejected) by the author.
UNCONFIRMED_STATUSES = frozenset({"extracted_pending", "extracted_infirmed"})


@dataclass
class AuthorHfProfileStats:
    papers_fetched: int = 0
    papers_matched: int = 0
    claims_seen: int = 0
    claimed: int = 0
    linked: int = 0
    refreshed: int = 0
    renamed: int = 0
    unchanged: int = 0
    unmatched: int = 0
    conflicts: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def iter_hf_papers(
    client: httpx.Client,
    published_since: datetime,
    *,
    pause_seconds: float = HF_PAGE_PAUSE_SECONDS,
) -> Iterator[dict[str, Any]]:
    """Yield HF papers newest first until one predates ``published_since``."""
    url: str | None = HF_PAPERS_URL
    params: dict[str, int] | None = {"limit": HF_PAPERS_PAGE_SIZE}
    while url:
        response = client.get(url, params=params)
        response.raise_for_status()
        page = response.json()
        if not page:
            return
        for paper in page:
            published_at = datetime.fromisoformat(
                paper["publishedAt"].replace("Z", "+00:00")
            )
            if published_at < published_since:
                return
            yield paper
        # The cursor link already carries the page size.
        url = response.links.get("next", {}).get("url")
        params = None
        if url and pause_seconds:
            time.sleep(pause_seconds)


def _claims(hf_paper: dict[str, Any]) -> list[tuple[str, dict[str, Any], Any]]:
    return [
        (author["name"], author["user"], author.get("status"))
        for author in hf_paper.get("authors") or []
        if author.get("name")
        and author.get("user")
        and not author.get("hidden")
        and author["user"].get("type", "user") == "user"
        and author.get("status") not in UNCONFIRMED_STATUSES
    ]


def _name_key(name: str) -> str:
    return normalize_arxiv_author_name(name).casefold()


class AuthorHfProfileSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.stats = AuthorHfProfileStats()

    def sync_paper(self, hf_paper: dict[str, Any]) -> None:
        """Apply one HF paper's authorship claims to its linked author rows."""
        self.stats.papers_fetched += 1
        claims = _claims(hf_paper)
        if not claims:
            return
        paper = (
            self.db.query(Paper)
            .filter(Paper.arxiv_id == hf_paper["id"], Paper.is_latest_version)
            .order_by(Paper.id.desc())
            .first()
        )
        if paper is None:
            return
        self.stats.papers_matched += 1
        links: dict[str, tuple[PaperAuthor, Author] | None] = {}
        for link, author in (
            self.db.query(PaperAuthor, Author)
            .join(Author, PaperAuthor.author_id == Author.id)
            .filter(PaperAuthor.paper_id == paper.id)
        ):
            key = _name_key(author.name)
            # Two coauthors that normalize to one name are ambiguous: skip both.
            links[key] = None if key in links else (link, author)
        for name, user, status in claims:
            self.stats.claims_seen += 1
            self._apply_claim(paper, name, links.get(_name_key(name)), user, status)

    def _apply_claim(
        self,
        paper: Paper,
        byline: str,
        name_link: tuple[PaperAuthor, Author] | None,
        user: dict[str, Any],
        status: Any,
    ) -> None:
        profile = {
            "hf_username": user["user"],
            "hf_id": user["_id"],
            "hf_avatar_url": user.get("avatarUrl"),
            "hf_status": status,
            "hf_is_pro": bool(user.get("isPro")),
        }
        owners = (
            self.db.query(Author)
            .filter(
                or_(
                    Author.hf_id == profile["hf_id"],
                    Author.hf_username == profile["hf_username"],
                )
            )
            .all()
        )
        if len(owners) > 1:
            # The id and the username belong to different rows (a rename
            # collided with an older row); leave it for a human.
            self.stats.conflicts += 1
            return
        owner = owners[0] if owners else None
        if owner is not None:
            if owner.hf_id and owner.hf_id != profile["hf_id"]:
                # Only the username matches: HF reassigned a freed username to
                # another account. Never rebind the row's identity.
                self.stats.conflicts += 1
                return
            # Refresh the profile (avatar, renamed username, Pro status).
            self._update(owner, profile)
            self._adopt_full_name(owner, byline, user)
            owner_link = (
                self.db.query(PaperAuthor)
                .filter(
                    PaperAuthor.paper_id == paper.id,
                    PaperAuthor.author_id == owner.id,
                )
                .one_or_none()
            )
            if owner_link is not None:
                link = name_link[0] if name_link else None
                if link is not None and link is not owner_link and not link.claimed:
                    # The name-matched duplicate of the claiming author.
                    self.db.delete(link)
                self._mark_claimed(owner_link)
                return

        if name_link is None:
            self.stats.unmatched += 1
            return
        link, author = name_link
        if link.claimed:
            # Another HF account already claimed this author on this paper.
            self.stats.conflicts += 1
            return
        if owner is None:
            owner = Author(name=normalize_arxiv_author_name(author.name), **profile)
            self.db.add(owner)
            self.db.flush()
            self.stats.linked += 1
            self._adopt_full_name(owner, byline, user)
        link.author_id = owner.id
        self._mark_claimed(link)

    def _adopt_full_name(
        self, author: Author, byline: str, user: dict[str, Any]
    ) -> None:
        # Only a full name the account publishes under: HF full names can be
        # nicknames or handles.
        fullname = user.get("fullname")
        if not fullname or _name_key(fullname) != _name_key(byline):
            return
        if _name_key(author.name) == _name_key(byline):
            return
        author.name = normalize_arxiv_author_name(fullname)
        self.db.flush()
        self.stats.renamed += 1

    def _mark_claimed(self, link: PaperAuthor) -> None:
        if link.claimed:
            return
        link.claimed = True
        self.db.flush()
        self.stats.claimed += 1

    def _update(self, author: Author, profile: dict[str, Any]) -> None:
        changed = {
            field: value
            for field, value in profile.items()
            if getattr(author, field) != value
        }
        if not changed:
            self.stats.unchanged += 1
            return
        for field, value in changed.items():
            setattr(author, field, value)
        self.db.flush()
        self.stats.refreshed += 1
