"""Link authors to the Hugging Face accounts that claimed their papers.

Hugging Face users claim authorship of a paper on its HF page, usually days
after the paper was imported here. The paper list at
``https://huggingface.co/api/papers`` carries each claim (author name plus HF
user), newest papers first, so a bounded walk over recent papers picks up late
claims and refreshed avatars at 100 papers per request.

Matching is conservative: a claim only fills an author row that is already
linked to that paper under the claimed name and has no HF account yet. The job
never creates authors and never moves an account from one author to another.
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


@dataclass
class AuthorHfProfileStats:
    papers_fetched: int = 0
    papers_matched: int = 0
    claims_seen: int = 0
    linked: int = 0
    refreshed: int = 0
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
        paper_authors: dict[str, Author | None] = {}
        for author in (
            self.db.query(Author)
            .join(PaperAuthor, PaperAuthor.author_id == Author.id)
            .filter(PaperAuthor.paper_id == paper.id)
        ):
            key = _name_key(author.name)
            # Two coauthors that normalize to one name are ambiguous: skip both.
            paper_authors[key] = None if key in paper_authors else author
        for name, user, status in claims:
            self.stats.claims_seen += 1
            self._apply_claim(paper_authors, name, user, status)

    def _apply_claim(
        self,
        paper_authors: dict[str, Author | None],
        name: str,
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
        if owners:
            owner = owners[0]
            if owner.hf_id and owner.hf_id != profile["hf_id"]:
                # Only the username matches: HF reassigned a freed username to
                # another account. Never rebind the row's identity.
                self.stats.conflicts += 1
                return
            # The account is already linked: keep its author, refresh the
            # profile (avatar, renamed username, Pro status).
            self._update(owner, profile, linked=False)
            return

        author = paper_authors.get(_name_key(name))
        if author is None:
            self.stats.unmatched += 1
            return
        if author.hf_username or author.hf_id:
            # Two HF accounts claim the same author name: a namesake.
            self.stats.conflicts += 1
            return
        self._update(author, profile, linked=True)

    def _update(self, author: Author, profile: dict[str, Any], *, linked: bool) -> None:
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
        if linked:
            self.stats.linked += 1
        else:
            self.stats.refreshed += 1
