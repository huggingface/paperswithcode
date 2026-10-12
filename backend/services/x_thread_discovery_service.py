"""Discover X threads in which authors introduce recent trending papers.

For each candidate paper the job runs one X API v2 recent search for posts that
link the paper (arXiv/HF paper URLs, project page, official repository) or
name it (method short name, title). Only original posts from the paper's own
authors (matched by display name or handle) or from a business-verified account
of one of its linked organizations are kept; outside accounts never are. Matches are stored on the
paper's scan row and, when applying, linked through the audited `x_threads`
curation section, which captures the preview shown on the paper page.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from backend.models.database import (
    Paper,
    PaperProjectPage,
    PaperRepository,
    PaperXThread,
    PaperXThreadScan,
    ProjectPage,
    Repository,
)
from backend.services.catalog_errors import CatalogError
from backend.services.paper_curation_service import PaperCurationService

X_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
MAX_QUERY_LENGTH = 512
MAX_SCANS_PER_PAPER = 3
RESCAN_AFTER = timedelta(hours=20)
CANDIDATE_WINDOW_DAYS = 10
MAX_THREADS_PER_PAPER = 2
ACTOR = {
    "source": "cron",
    "hf_subject": "system:x-thread-discovery",
    "username": "x-thread-discovery",
    "role": "admin",
}

Search = Callable[[str], dict]


@dataclass
class PaperScanResult:
    paper_id: int
    arxiv_id: str | None
    title: str
    query: str
    matches: list[dict] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class DiscoveryReport:
    apply: bool
    papers: list[PaperScanResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "apply": self.apply,
            "papers_scanned": len(self.papers),
            "papers_matched": sum(bool(p.matches) for p in self.papers),
            "threads_linked": sum(len(p.linked) for p in self.papers),
            "errors": [
                {"paper_id": p.paper_id, "error": p.error}
                for p in self.papers
                if p.error
            ],
            "matches": [
                {
                    "paper_id": p.paper_id,
                    "arxiv_id": p.arxiv_id,
                    "title": p.title,
                    "posts": p.matches,
                    "linked": p.linked,
                }
                for p in self.papers
                if p.matches
            ],
        }


def make_x_search(bearer_token: str, *, timeout: float = 30) -> Search:
    """Return a recent-search function bound to an X API bearer token."""

    def search(query: str) -> dict:
        response = httpx.get(
            X_SEARCH_URL,
            params={
                "query": query,
                "max_results": 25,
                "tweet.fields": "author_id,created_at,public_metrics,conversation_id",
                "expansions": "author_id",
                "user.fields": "name,username,verified_type",
            },
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    return search


def _name_tokens(name: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in folded if not unicodedata.combining(c)).lower()
    # Display names often carry suffixes such as "Jane Doe @ NeurIPS" or "(she/her)".
    ascii_name = re.split(r"[@|(\[]", ascii_name)[0]
    return re.findall(r"[a-z]+", ascii_name)


def author_matches(
    display_name: str, authors: list[str], handle: str = ""
) -> str | None:
    """Return the paper author named by an X account's display name or handle."""
    shown = set(_name_tokens(display_name))
    handle = handle.lower()
    for author in authors:
        tokens = _name_tokens(author)
        if len(tokens) >= 2 and set(tokens) <= shown:
            return author
        # Accept "First Last" when the paper lists middle names or initials.
        full = [token for token in tokens if len(token) > 1]
        if len(full) >= 2 and {full[0], full[-1]} <= shown:
            return author
        # Nicknamed display names ("Aaron Huang" for Wei Huang) often keep the
        # real name in the handle (@AaronWeiHuang).
        if len(full) >= 2 and any(
            len(joined) >= 6 and joined in handle
            for joined in (full[0] + full[-1], full[-1] + full[0])
        ):
            return author
    return None


def organization_matches(user: dict, organizations: list[str]) -> str | None:
    """Return the linked organization a business-verified X account belongs to."""
    if user.get("verified_type") != "business":
        return None
    shown = set(_name_tokens(user.get("name", "")))
    handle = user.get("username", "").lower()
    shown.update(re.findall(r"[a-z0-9]+", user.get("name", "").lower()))
    for organization in organizations:
        tokens = re.findall(r"[a-z0-9]+", organization.lower())
        # Very short names ("AI") would match unrelated business accounts.
        if len("".join(tokens)) < 3:
            continue
        if set(tokens) <= shown or "".join(tokens) in handle:
            return organization
    return None


def short_name(title: str) -> str | None:
    """Return a distinctive method name such as "RoboJEPA" from "RoboJEPA: ..."."""
    if ":" not in title:
        return None
    name = title.split(":", 1)[0].strip()
    distinctive = re.search(r"[A-Z].*[A-Z]|\d", name[1:]) is not None
    if 4 <= len(name) <= 30 and len(name.split()) <= 3 and distinctive:
        return name
    return None


def build_query(
    arxiv_id: str | None,
    title: str,
    project_urls: list[str],
    repo_urls: list[str],
) -> str:
    """OR together the strongest signals that still fit X's query length limit."""
    terms: list[str] = []
    if arxiv_id:
        terms.append(f'url:"{arxiv_id}"')
    for url in project_urls:
        host = urlsplit(url).netloc.removeprefix("www.")
        path = urlsplit(url).path.strip("/")
        # Shared hosts (github.io pages live under the host itself) stay specific.
        target = host if host.endswith(".github.io") or not path else f"{host}/{path}"
        terms.append(f'url:"{target}"')
    for url in repo_urls:
        parts = urlsplit(url).path.strip("/").split("/")
        if len(parts) >= 2:
            terms.append(f'url:"github.com/{parts[0]}/{parts[1]}"')
    name = short_name(title)
    if name:
        terms.append(f'"{name}"')
    main_title = title.split(":", 1)[-1].strip() if name else title.strip()
    terms.append('"{}"'.format(main_title.replace('"', "")))

    suffix = " -is:retweet -is:reply"
    chosen: list[str] = []
    for term in dict.fromkeys(terms):
        candidate = "(" + " OR ".join([*chosen, term]) + ")" + suffix
        if len(candidate) <= MAX_QUERY_LENGTH:
            chosen.append(term)
    return "(" + " OR ".join(chosen) + ")" + suffix


def match_posts(
    response: dict,
    authors: list[str],
    published: date | None,
    organizations: list[str] = (),
) -> list[dict]:
    """Keep each author's or organization's most-liked original post, best first."""
    users = {u["id"]: u for u in response.get("includes", {}).get("users", [])}
    earliest = (
        datetime.combine(published - timedelta(days=7), datetime.min.time(), UTC)
        if published
        else None
    )
    best: dict[str, dict] = {}
    for post in response.get("data", []):
        user = users.get(post.get("author_id"))
        if not user or post.get("conversation_id", post["id"]) != post["id"]:
            continue
        author = author_matches(user.get("name", ""), authors, user["username"])
        kind = "author"
        if not author:
            author = organization_matches(user, list(organizations))
            kind = "organization"
        if not author:
            continue
        created = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
        if earliest and created < earliest:
            continue
        likes = post.get("public_metrics", {}).get("like_count", 0)
        match = {
            "url": f"https://x.com/{user['username']}/status/{post['id']}",
            "author": author,
            "kind": kind,
            "handle": user["username"],
            "likes": likes,
            "created_at": post["created_at"],
        }
        if author not in best or likes > best[author]["likes"]:
            best[author] = match
    return sorted(best.values(), key=lambda m: -m["likes"])[:MAX_THREADS_PER_PAPER]


def candidate_papers(db: Session, *, today: date, limit: int) -> list[Paper]:
    """Recent trending or HF-featured arXiv papers that still lack X threads."""
    since = today - timedelta(days=CANDIDATE_WINDOW_DAYS)
    rescan_before = datetime.now(UTC) - RESCAN_AFTER
    scan = PaperXThreadScan
    return list(
        db.scalars(
            select(Paper)
            .outerjoin(scan, scan.paper_id == Paper.id)
            .where(
                Paper.is_latest_version,
                Paper.source == "arxiv",
                Paper.date_published >= since,
                or_(
                    Paper.hf_daily_featured_on >= since,
                    Paper.trending_score > 0,
                ),
                ~exists().where(PaperXThread.paper_id == Paper.id),
                or_(
                    scan.paper_id.is_(None),
                    (scan.scan_count < MAX_SCANS_PER_PAPER)
                    & (scan.last_scanned_at < rescan_before)
                    & scan.linked_at.is_(None),
                ),
            )
            .order_by(
                func.coalesce(Paper.trending_score, 0).desc(),
                Paper.hf_daily_featured_on.desc().nullslast(),
                Paper.id.desc(),
            )
            .limit(limit)
        )
    )


def _paper_links(db: Session, paper_id: int) -> tuple[list[str], list[str]]:
    project_urls = list(
        db.scalars(
            select(ProjectPage.url)
            .join(PaperProjectPage, PaperProjectPage.project_page_id == ProjectPage.id)
            .where(PaperProjectPage.paper_id == paper_id)
        )
    )
    repo_urls = list(
        db.scalars(
            select(Repository.url)
            .join(PaperRepository, PaperRepository.repository_id == Repository.id)
            .where(PaperRepository.paper_id == paper_id, PaperRepository.is_official)
        )
    )
    return project_urls, repo_urls


def _record_scan(db: Session, paper_id: int, result: PaperScanResult) -> None:
    now = datetime.now(UTC)
    row = db.get(PaperXThreadScan, paper_id)
    if row is None:
        row = PaperXThreadScan(paper_id=paper_id, scan_count=0, candidates=[])
        db.add(row)
    row.scan_count += 1
    row.last_scanned_at = now
    if result.matches:
        row.candidates = result.matches
    if result.linked:
        row.linked_at = now


def discover_x_threads(
    db: Session,
    search: Search,
    *,
    apply: bool,
    max_papers: int,
    today: date | None = None,
) -> DiscoveryReport:
    report = DiscoveryReport(apply=apply)
    curation = PaperCurationService(db)
    for paper in candidate_papers(db, today=today or date.today(), limit=max_papers):
        authors = [author.name for author in paper.authors]
        organizations = [organization.name for organization in paper.organizations]
        project_urls, repo_urls = _paper_links(db, paper.id)
        query = build_query(paper.arxiv_id, paper.title, project_urls, repo_urls)
        result = PaperScanResult(paper.id, paper.arxiv_id, paper.title, query)
        report.papers.append(result)
        try:
            response = search(query)
        except httpx.HTTPStatusError as error:
            result.error = f"X search HTTP {error.response.status_code}"
            if error.response.status_code in {401, 403, 429}:
                break  # Credentials or quota: every later search would fail too.
            continue
        except httpx.HTTPError as error:
            result.error = f"X search failed: {error}"
            continue
        result.matches = match_posts(
            response, authors, paper.date_published, organizations
        )
        if apply and result.matches:
            urls = [match["url"] for match in result.matches]
            try:
                curation.update(
                    paper_id=paper.id,
                    section="x_threads",
                    payload={"x_threads": urls},
                    actor=ACTOR,
                    idempotency_key=str(uuid.uuid4()),
                    expected_version=None,
                    request_id=f"x-thread-discovery:{paper.id}",
                )
                result.linked = urls
            except CatalogError as error:
                db.rollback()
                result.error = f"link failed: {error.detail}"
        _record_scan(db, paper.id, result)
        db.commit()
    return report


def stored_candidates(db: Session) -> list[dict[str, Any]]:
    """Matches recorded while report-only, for review before enabling apply."""
    rows = db.execute(
        select(PaperXThreadScan.paper_id, Paper.arxiv_id, PaperXThreadScan.candidates)
        .join(Paper, Paper.id == PaperXThreadScan.paper_id)
        .where(PaperXThreadScan.linked_at.is_(None))
        .where(func.jsonb_array_length(PaperXThreadScan.candidates) > 0)
    )
    return [
        {"paper_id": paper_id, "arxiv_id": arxiv_id, "posts": candidates}
        for paper_id, arxiv_id, candidates in rows
    ]
