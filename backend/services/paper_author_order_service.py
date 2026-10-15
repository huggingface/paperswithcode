"""Restore `paper_authors.author_order` for papers whose links all have order 1.

Before PR #519 the Hugging Face daily importer linked authors without an
order, so every link defaulted to 1 and the public API listed authors in
arbitrary order. The order is recovered from the paper's authoritative author
list (arXiv metadata, falling back to the Hugging Face papers API) by matching
each existing link to a listed author name. Papers whose links cannot all be
matched are reported, never guessed.
"""

from __future__ import annotations

import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.services.author_service import normalize_arxiv_author_name

ARXIV_API_URL = "https://export.arxiv.org/api/query"
HF_PAPER_API_URL = "https://huggingface.co/api/papers/{arxiv_id}"
ATOM = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "PapersWithCode-AuthorOrderBackfill/1.0 (https://paperswithcode.co)"
ARXIV_DELAY_SECONDS = 3.0
HF_DELAY_SECONDS = 0.5
MAX_ATTEMPTS = 4

_VERSION_SUFFIX = re.compile(r"v\d+$")


@dataclass(frozen=True)
class LinkedAuthor:
    author_id: int
    name: str
    hf_username: str | None


@dataclass(frozen=True)
class ListedAuthor:
    name: str
    hf_username: str | None = None


@dataclass(frozen=True)
class UnorderedPaper:
    paper_id: int
    arxiv_id: str | None
    authors: tuple[LinkedAuthor, ...]


def author_name_key(name: str) -> str:
    """Match key for author names: the importer's case-insensitive equality."""
    return normalize_arxiv_author_name(name).casefold()


def folded_author_name_key(name: str) -> str:
    """Looser key without accents or punctuation ("Lorenz K. Müller")."""
    decomposed = unicodedata.normalize("NFKD", author_name_key(name))
    letters = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", "", letters)


def bare_arxiv_id(arxiv_id: str) -> str:
    return _VERSION_SUFFIX.sub("", arxiv_id.strip())


def match_author_order(
    linked: Sequence[LinkedAuthor], listed: Sequence[ListedAuthor]
) -> tuple[dict[int, int], list[LinkedAuthor]]:
    """Return ({author_id: order}, unmatched links).

    Links match listed authors by HF username, then by the importer's name
    key, then by the folded name key; each pass takes the first unused listed
    position. Orders are dense (1..n) over the matched listed positions.
    """
    passes = (
        lambda author: author.hf_username,
        lambda author: author_name_key(author.name),
        lambda author: folded_author_name_key(author.name),
    )
    unused = list(range(len(listed)))
    positions: dict[int, int] = {}
    for key in passes:
        for author in linked:
            if author.author_id in positions or not key(author):
                continue
            position = next((i for i in unused if key(listed[i]) == key(author)), None)
            if position is not None:
                unused.remove(position)
                positions[author.author_id] = position
    unmatched = [author for author in linked if author.author_id not in positions]
    ranked = sorted(positions, key=positions.__getitem__)
    return {author_id: rank for rank, author_id in enumerate(ranked, start=1)}, (
        unmatched
    )


def iter_unordered_papers(
    db: Session, *, after_id: int, batch_size: int
) -> Iterator[list[UnorderedPaper]]:
    """Yield batches of multi-author papers whose links all have order 1."""
    while True:
        rows = (
            db.execute(
                text(
                    """
                    WITH batch AS (
                        SELECT paper_id
                        FROM paper_authors
                        WHERE paper_id > :after_id
                        GROUP BY paper_id
                        HAVING count(*) > 1 AND max(author_order) = 1
                            AND min(author_order) = 1
                        ORDER BY paper_id
                        LIMIT :batch_size
                    )
                    SELECT p.id AS paper_id, p.arxiv_id, a.id AS author_id,
                           a.name, a.hf_username
                    FROM batch
                    JOIN papers p ON p.id = batch.paper_id
                    JOIN paper_authors pa ON pa.paper_id = p.id
                    JOIN authors a ON a.id = pa.author_id
                    ORDER BY p.id, a.id
                    """
                ),
                {"after_id": after_id, "batch_size": batch_size},
            )
            .mappings()
            .all()
        )
        if not rows:
            return
        arxiv_ids: dict[int, str | None] = {}
        authors: dict[int, list[LinkedAuthor]] = {}
        for row in rows:
            arxiv_ids[row["paper_id"]] = row["arxiv_id"]
            authors.setdefault(row["paper_id"], []).append(
                LinkedAuthor(row["author_id"], row["name"], row["hf_username"])
            )
        yield [
            UnorderedPaper(paper_id, arxiv_ids[paper_id], tuple(linked))
            for paper_id, linked in authors.items()
        ]
        after_id = rows[-1]["paper_id"]


def write_author_order(db: Session, paper_id: int, order: dict[int, int]) -> int:
    """Write the order unless the paper's links changed since they were read."""
    result = db.execute(
        text(
            """
            UPDATE paper_authors pa
            SET author_order = v.author_order
            FROM unnest(CAST(:author_ids AS bigint[]), CAST(:orders AS int[]))
                AS v(author_id, author_order)
            WHERE pa.paper_id = :paper_id
              AND pa.author_id = v.author_id
              AND NOT EXISTS (
                  SELECT 1 FROM paper_authors other
                  WHERE other.paper_id = :paper_id AND other.author_order <> 1
              )
              AND (SELECT count(*) FROM paper_authors other
                   WHERE other.paper_id = :paper_id) = :link_count
            """
        ),
        {
            "paper_id": paper_id,
            "author_ids": list(order),
            "orders": list(order.values()),
            "link_count": len(order),
        },
    )
    return result.rowcount


class AuthorListClient:
    """Rate-limited fetches of authoritative author lists."""

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(
            timeout=30.0, headers={"User-Agent": USER_AGENT}
        )
        self._next_arxiv_at = 0.0
        self._next_hf_at = 0.0

    def _get(self, url: str, params: dict | None, delay: float, slot: str):
        for attempt in range(MAX_ATTEMPTS):
            wait = getattr(self, slot) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            response = self.client.get(url, params=params)
            setattr(self, slot, time.monotonic() + delay)
            if response.status_code not in (429, 500, 502, 503, 504):
                return response
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(delay * 2 ** (attempt + 2))
        response.raise_for_status()
        return response

    def arxiv_authors(self, arxiv_ids: Sequence[str]) -> dict[str, list[ListedAuthor]]:
        """Fetch author lists for up to ~100 bare arXiv ids in one request."""
        response = self._get(
            ARXIV_API_URL,
            {"id_list": ",".join(arxiv_ids), "max_results": len(arxiv_ids)},
            ARXIV_DELAY_SECONDS,
            "_next_arxiv_at",
        )
        response.raise_for_status()
        authors: dict[str, list[ListedAuthor]] = {}
        for entry in ET.fromstring(response.content).iter(f"{ATOM}entry"):
            entry_id = entry.findtext(f"{ATOM}id") or ""
            if "/abs/" not in entry_id:
                continue
            arxiv_id = bare_arxiv_id(entry_id.split("/abs/", 1)[1])
            names = [
                (author.findtext(f"{ATOM}name") or "").strip()
                for author in entry.iter(f"{ATOM}author")
            ]
            authors[arxiv_id] = [ListedAuthor(name) for name in names if name]
        return authors

    def hf_authors(self, arxiv_id: str) -> list[ListedAuthor] | None:
        response = self._get(
            HF_PAPER_API_URL.format(arxiv_id=arxiv_id),
            None,
            HF_DELAY_SECONDS,
            "_next_hf_at",
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return [
            ListedAuthor(author["name"], (author.get("user") or {}).get("user"))
            for author in response.json().get("authors") or []
            if author.get("name")
        ]
