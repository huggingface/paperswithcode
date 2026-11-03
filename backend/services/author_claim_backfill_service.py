"""Backfill Hugging Face claims on legacy author links and split off namesakes.

Before PR #519 the importers matched arXiv bylines to the author row of
whoever first claimed that name on Hugging Face, so a common name's HF-linked
row (``/authors/<id>``) lists many namesakes' papers. ``paper_authors.claimed``
was only backfilled from HF's daily-papers list, so most legacy links are
unclaimed although HF records the account's claim on the paper itself.

The cleanup runs in four phases, in this order:

1. ``claims``: replay each paper's HF author list (fetched once into a JSON
   lines cache by :func:`fetch_hf_papers`) through the daily sync, which marks
   the account's links claimed and moves links another account claimed to that
   account's row.
2. ``doubles``: a paper linked to two rows under one author name at the same
   byline position keeps the claimed link, else the name-only one. Same-name
   links at different positions may be two coauthors and are only reported.
3. ``split``: an unclaimed link of an HF-linked row stays only when the paper
   shares a coauthor with one of the row's claimed papers; otherwise it moves
   to the name-only author of that name. Rows without any claimed paper have
   no evidence either way and are only reported.
4. ``merge``: a name-only link moves to the only HF account with that name
   when the paper is provably the account's: it shares an official repository
   with one of the account's anchor papers, or a coauthor whose identity is
   certain on both papers (an HF-linked row with claimed or curated links), or
   at least two distinctive name-only coauthors (no two accounts share the
   name, and the row has at most ``MAX_COAUTHOR_PAPERS`` papers). Anchor papers are
   the account's claimed papers, or all papers of a curated row (an HF username
   set by hand, without an HF id). Papers without such evidence stay put.
5. ``empty``: name-only rows left without papers (and nothing else pointing at
   them) are deleted; the row that took their papers, else a namesake row,
   inherits their URL through ``author_aliases``.

Each phase reports every change it makes, so a rolled-back run is the dry run.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from backend.models.database import Author, AuthorAlias, PaperAuthor
from backend.services.author_hf_profile_sync_service import (
    AuthorHfProfileSyncService,
    _name_key,
)
from backend.services.author_service import (
    get_or_create_author_by_name,
    normalize_arxiv_author_name,
)

HF_PAPER_URL = "https://huggingface.co/api/papers/{arxiv_id}"
USER_AGENT = "PapersWithCode-AuthorClaimBackfill/1.0 (https://paperswithcode.co)"
# HF allows 500 requests per 5 minutes per IP; stay below it.
DEFAULT_REQUESTS_PER_SECOND = 1.5
MAX_ATTEMPTS = 6
FIRST_BACKOFF_SECONDS = 30.0

PHASES = ("claims", "doubles", "split", "merge", "empty")
# Coauthors that tie a paper to an account when no stronger evidence exists.
MIN_SHARED_COAUTHORS = 2
# A name-only row with more papers likely lumps several namesakes together.
MAX_COAUTHOR_PAPERS = 100

_MERGE_SETUP = (
    "DROP TABLE IF EXISTS merge_hf",
    "DROP TABLE IF EXISTS merge_identity",
    "DROP TABLE IF EXISTS merge_anchor",
    "DROP TABLE IF EXISTS merge_candidate",
    "DROP TABLE IF EXISTS merge_coauthor",
    """
    CREATE TEMP TABLE merge_hf AS
    SELECT id, lower(name) AS name_key, hf_id IS NULL AS curated
    FROM authors
    WHERE hf_id IS NOT NULL OR hf_username IS NOT NULL
    """,
    # Links whose author is certainly the person: claimed, or hand-curated.
    """
    CREATE TEMP TABLE merge_identity AS
    SELECT pa.author_id, pa.paper_id
    FROM paper_authors pa
    JOIN merge_hf h ON h.id = pa.author_id
    WHERE pa.claimed OR h.curated
    """,
    "CREATE TEMP TABLE merge_anchor AS SELECT * FROM merge_identity",
    """
    CREATE TEMP TABLE merge_candidate AS
    SELECT pa.paper_id, pa.author_id AS name_only_id, h.id AS hf_author_id
    FROM paper_authors pa
    JOIN authors a ON a.id = pa.author_id
    JOIN merge_hf h ON h.name_key = lower(a.name)
    WHERE a.hf_id IS NULL AND a.hf_username IS NULL
      AND h.name_key IN (
          SELECT name_key FROM merge_hf GROUP BY name_key HAVING count(*) = 1
      )
      AND EXISTS (SELECT 1 FROM merge_anchor an WHERE an.author_id = h.id)
    """,
    # Name-only coauthors distinctive enough to count as shared evidence.
    f"""
    CREATE TEMP TABLE merge_coauthor AS
    SELECT a.id AS author_id
    FROM authors a
    WHERE a.hf_id IS NULL AND a.hf_username IS NULL
      AND (SELECT count(*) FROM merge_hf h WHERE h.name_key = lower(a.name)) < 2
      AND (
          SELECT count(*) FROM paper_authors pa WHERE pa.author_id = a.id
      ) <= {MAX_COAUTHOR_PAPERS}
      AND EXISTS (
          SELECT 1 FROM paper_authors pa
          JOIN merge_anchor an ON an.paper_id = pa.paper_id
          WHERE pa.author_id = a.id
      )
    """,
)

_MERGE_EVIDENCE = """
SELECT c.paper_id, c.name_only_id, c.hf_author_id,
       EXISTS (
           SELECT 1
           FROM paper_repositories r1
           JOIN paper_repositories r2
             ON r2.repository_id = r1.repository_id AND r2.is_official
           JOIN merge_anchor an
             ON an.paper_id = r2.paper_id AND an.author_id = c.hf_author_id
           WHERE r1.paper_id = c.paper_id AND r1.is_official
             AND r2.paper_id <> c.paper_id
       ) AS shares_repository,
       EXISTS (
           SELECT 1
           FROM merge_identity co
           JOIN merge_identity co2 ON co2.author_id = co.author_id
           JOIN merge_anchor an
             ON an.paper_id = co2.paper_id AND an.author_id = c.hf_author_id
           WHERE co.paper_id = c.paper_id
             AND co.author_id <> c.hf_author_id
             AND co2.paper_id <> c.paper_id
       ) AS shares_verified_coauthor,
       (
           SELECT count(DISTINCT co.author_id)
           FROM paper_authors co
           JOIN merge_coauthor mc ON mc.author_id = co.author_id
           JOIN paper_authors co2 ON co2.author_id = co.author_id
           JOIN merge_anchor an
             ON an.paper_id = co2.paper_id AND an.author_id = c.hf_author_id
           WHERE co.paper_id = c.paper_id
             AND co.author_id <> c.name_only_id
             AND co2.paper_id <> c.paper_id
       ) AS shared_coauthors
FROM merge_candidate c
ORDER BY c.hf_author_id, c.paper_id
"""

Report = Callable[[dict[str, Any]], None]


def iter_claim_targets(
    db: Session, *, after_id: int = 0, batch_size: int = 1000
) -> Iterator[list[tuple[int, str]]]:
    """Yield batches of (paper id, arXiv id) whose HF-linked links are unclaimed."""
    while True:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT p.id, p.arxiv_id
                FROM papers p
                JOIN paper_authors pa ON pa.paper_id = p.id
                JOIN authors a ON a.id = pa.author_id
                WHERE p.id > :after_id
                  AND p.is_latest_version
                  AND p.arxiv_id IS NOT NULL
                  AND NOT pa.claimed
                  AND (a.hf_id IS NOT NULL OR a.hf_username IS NOT NULL)
                ORDER BY p.id
                LIMIT :limit
                """
            ),
            {"after_id": after_id, "limit": batch_size},
        ).all()
        if not rows:
            return
        yield [(row[0], row[1]) for row in rows]
        after_id = rows[-1][0]


def cached_arxiv_ids(cache: Path) -> set[str]:
    if not cache.exists():
        return set()
    with cache.open(encoding="utf-8") as lines:
        return {json.loads(line)["arxiv_id"] for line in lines if line.strip()}


class HfPaperClient:
    """Paced Hugging Face papers API client that backs off on 429 and 5xx."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND,
        sleep: Callable[[float], None] = time.sleep,
    ):
        headers = {"User-Agent": USER_AGENT}
        if token := os.environ.get("HF_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30, connect=10), follow_redirects=True
        )
        self.headers = headers
        self.interval = 1 / requests_per_second
        self.sleep = sleep
        self._last = 0.0

    def authors(self, arxiv_id: str) -> list[dict[str, Any]] | None:
        """Return the paper's HF author list, or None when HF has no such paper."""
        backoff = FIRST_BACKOFF_SECONDS
        for attempt in range(MAX_ATTEMPTS):
            wait = self._last + self.interval - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            response = self.client.get(
                HF_PAPER_URL.format(arxiv_id=arxiv_id), headers=self.headers
            )
            if response.status_code == 404:
                return None
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 == MAX_ATTEMPTS:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After", "")
                self.sleep(float(retry_after) if retry_after.isdigit() else backoff)
                backoff *= 2
                continue
            response.raise_for_status()
            return [_claim_fields(a) for a in response.json().get("authors") or []]
        raise AssertionError("unreachable")


def _claim_fields(author: dict[str, Any]) -> dict[str, Any]:
    """Keep only what the claim sync reads, so the cache stays small."""
    kept = {k: author[k] for k in ("name", "hidden", "status") if k in author}
    if user := author.get("user"):
        kept["user"] = {
            k: user[k]
            for k in ("_id", "user", "fullname", "avatarUrl", "isPro", "type")
            if k in user
        }
    return kept


def fetch_hf_papers(
    db: Session,
    client: HfPaperClient,
    cache: Path,
    *,
    limit: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """Append HF author lists of uncached target papers to ``cache``.

    Read-only on the database; a rerun skips papers already in the cache.
    """
    done = cached_arxiv_ids(cache)
    fetched = 0
    with cache.open("a", encoding="utf-8") as out:
        for batch in iter_claim_targets(db):
            db.rollback()
            for paper_id, arxiv_id in batch:
                if arxiv_id in done:
                    continue
                authors = client.authors(arxiv_id)
                out.write(json.dumps({"arxiv_id": arxiv_id, "authors": authors}) + "\n")
                done.add(arxiv_id)
                fetched += 1
                if limit is not None and fetched >= limit:
                    return fetched
            out.flush()
            if on_progress:
                on_progress(fetched, batch[-1][0])
    return fetched


def _is_hf(author: Author) -> bool:
    return author.hf_id is not None or author.hf_username is not None


@dataclass
class CleanupStats:
    counts: Counter = field(default_factory=Counter)
    claim_sync: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {**dict(sorted(self.counts.items())), "claim_sync": self.claim_sync}


class AuthorClaimCleanup:
    def __init__(self, db: Session, report: Report):
        self.db = db
        self.report = report
        self.stats = CleanupStats()
        # Name-only author id -> the account its papers merged into.
        self.merged_into: dict[int, int] = {}
        # Filled by replay_claims: HF byline names by arXiv id (name key ->
        # name) and HF-linked author names before the replay renamed any.
        self.bylines: dict[str, dict[str, str]] = {}
        self.original_names: dict[int, str] = {}

    def replay_claims(self, cache: Path) -> None:
        """Apply cached HF author lists through the daily claim sync."""
        # The sync renames an account's row to its HF full name; the split
        # still needs the name the legacy links were matched by.
        self.original_names = dict(
            self.db.query(Author.id, Author.name).filter(
                or_(Author.hf_id.isnot(None), Author.hf_username.isnot(None))
            )
        )
        sync = AuthorHfProfileSyncService(self.db)
        with cache.open(encoding="utf-8") as lines:
            for line in lines:
                entry = json.loads(line)
                if entry["authors"] is None:
                    self.stats.counts["claims_not_on_hf"] += 1
                    continue
                self.bylines[entry["arxiv_id"]] = {
                    _name_key(author["name"]): normalize_arxiv_author_name(
                        author["name"]
                    )
                    for author in entry["authors"]
                    if author.get("name")
                }
                before = sync.stats.claimed
                sync.sync_paper({"id": entry["arxiv_id"], "authors": entry["authors"]})
                if sync.stats.claimed > before:
                    self.report(
                        {
                            "phase": "claims",
                            "arxiv_id": entry["arxiv_id"],
                            "claimed": sync.stats.claimed - before,
                        }
                    )
        self.stats.claim_sync = sync.stats.to_dict()

    def fix_doubles(self) -> None:
        """Keep one link per paper and author name: the claimed, else name-only."""
        groups: dict[tuple[int, str], list[tuple[PaperAuthor, Author]]] = defaultdict(
            list
        )
        doubled = (
            self.db.query(PaperAuthor, Author)
            .join(Author, Author.id == PaperAuthor.author_id)
            .filter(
                PaperAuthor.paper_id.in_(
                    self.db.query(PaperAuthor.paper_id)
                    .join(Author, Author.id == PaperAuthor.author_id)
                    .group_by(PaperAuthor.paper_id, func.lower(Author.name))
                    .having(text("count(*) > 1"))
                )
            )
        )
        for link, author in doubled:
            groups[(link.paper_id, _name_key(author.name))].append((link, author))
        for (paper_id, _), links in sorted(groups.items()):
            if len(links) < 2:
                continue
            claimed = [pair for pair in links if pair[0].claimed]
            name_only = [pair for pair in links if not _is_hf(pair[1])]
            keep = claimed or name_only
            # Two coauthors can share a name; only one byline slot is a double.
            if len({link.author_order for link, _ in links}) > 1:
                skip = "different_positions"
            elif len(keep) != 1:
                skip = "no_single_keeper"
            else:
                skip = None
            if skip:
                self.stats.counts[f"doubles_skipped_{skip}"] += 1
                self.report(
                    {
                        "phase": "doubles",
                        "action": "skip",
                        "reason": skip,
                        "paper_id": paper_id,
                        "author_ids": [author.id for _, author in links],
                    }
                )
                continue
            kept_link, kept = keep[0]
            for link, author in links:
                if link is kept_link:
                    continue
                self.db.delete(link)
                self.stats.counts["doubles_removed"] += 1
                self.report(
                    {
                        "phase": "doubles",
                        "action": "remove_link",
                        "paper_id": paper_id,
                        "author_id": author.id,
                        "hf_username": author.hf_username,
                        "kept_author_id": kept.id,
                        "name": author.name,
                    }
                )
        self.db.flush()

    def split_namesakes(self) -> None:
        """Move unclaimed links without coauthor evidence to name-only authors.

        Only bylines that two or more HF accounts publish under move: a second
        account proves namesakes exist. A name with one account may just be
        that person's unclaimed papers, so it stays.
        """
        # An account renamed by a claim still counts under its former name.
        accounts = Counter(
            key
            for author_id, name in self.db.query(Author.id, Author.name).filter(
                Author.hf_id.isnot(None)
            )
            for key in {
                _name_key(name),
                _name_key(self.original_names.get(author_id, name)),
            }
        )
        rows = self.db.execute(
            text(
                """
                WITH hf AS (
                    SELECT id FROM authors
                    WHERE hf_id IS NOT NULL OR hf_username IS NOT NULL
                ),
                evidence AS (
                    SELECT DISTINCT pa.author_id, co.author_id AS coauthor_id
                    FROM paper_authors pa
                    JOIN hf ON hf.id = pa.author_id
                    JOIN paper_authors co
                      ON co.paper_id = pa.paper_id AND co.author_id <> pa.author_id
                    WHERE pa.claimed
                )
                SELECT pa.author_id, pa.paper_id, p.arxiv_id,
                       EXISTS (
                           SELECT 1 FROM paper_authors pc WHERE pc.author_id = pa.author_id AND pc.claimed
                       ) AS has_claims,
                       EXISTS (
                           SELECT 1
                           FROM paper_authors co
                           JOIN evidence e
                             ON e.author_id = pa.author_id
                            AND e.coauthor_id = co.author_id
                           WHERE co.paper_id = pa.paper_id
                             AND co.author_id <> pa.author_id
                       ) AS shares_coauthor
                FROM paper_authors pa
                JOIN hf ON hf.id = pa.author_id
                JOIN papers p ON p.id = pa.paper_id
                WHERE NOT pa.claimed AND p.is_latest_version
                ORDER BY pa.author_id, pa.paper_id
                """
            )
        ).all()
        namesakes: dict[str, Author] = {}
        rows_moved_from: set[int] = set()
        no_claims: Counter = Counter()
        for author_id, paper_id, arxiv_id, has_claims, shares_coauthor in rows:
            if not has_claims:
                no_claims[author_id] += 1
                continue
            if shares_coauthor:
                self.stats.counts["split_kept_by_coauthor"] += 1
                continue
            author = self.db.get(Author, author_id)
            byline_name = self._byline_name(author, arxiv_id)
            if byline_name is None:
                self.stats.counts["split_skipped_name_not_on_byline"] += 1
                self.report(
                    {
                        "phase": "split",
                        "action": "skip_name_not_on_byline",
                        "paper_id": paper_id,
                        "author_id": author_id,
                    }
                )
                continue
            key = _name_key(byline_name)
            if accounts[key] < 2:
                self.stats.counts["split_skipped_unique_name"] += 1
                continue
            namesake = namesakes.get(key)
            if namesake is None:
                namesake = get_or_create_author_by_name(self.db, byline_name)
                namesakes[key] = namesake
            rows_moved_from.add(author_id)
            link = self.db.get(PaperAuthor, (paper_id, author_id))
            if self.db.get(PaperAuthor, (paper_id, namesake.id)) is not None:
                self.db.delete(link)
                action = "remove_link"
            else:
                order = link.author_order
                self.db.delete(link)
                self.db.flush()
                self.db.add(
                    PaperAuthor(
                        paper_id=paper_id, author_id=namesake.id, author_order=order
                    )
                )
                action = "move_link"
            self.db.flush()
            self.stats.counts[f"split_{action}"] += 1
            self.report(
                {
                    "phase": "split",
                    "action": action,
                    "paper_id": paper_id,
                    "author_id": author_id,
                    "hf_username": author.hf_username,
                    "to_author_id": namesake.id,
                    "name": byline_name,
                }
            )
        self.stats.counts["split_rows_moved_from"] = len(rows_moved_from)
        self.stats.counts["split_rows_without_claims"] = len(no_claims)
        self.stats.counts["split_links_on_rows_without_claims"] = sum(
            no_claims.values()
        )
        for author_id, links in no_claims.most_common():
            self.report(
                {
                    "phase": "split",
                    "action": "skip_no_claims",
                    "author_id": author_id,
                    "unclaimed_links": links,
                }
            )

    def _byline_name(self, author: Author, arxiv_id: str | None) -> str | None:
        """Return the name the link was matched by, or None when unsure.

        It is the row's name, or its name before this run renamed it, as
        listed on the paper's HF byline. Without a cached byline, only a row
        this run did not rename has a known name.
        """
        keys = {
            _name_key(author.name),
            _name_key(self.original_names.get(author.id, author.name)),
        }
        byline = self.bylines.get(arxiv_id) if arxiv_id else None
        if byline is None:
            return author.name if len(keys) == 1 else None
        found = [byline[key] for key in keys if key in byline]
        return found[0] if len(found) == 1 else None

    def merge_namesakes(self) -> None:
        """Move name-only links to the account they provably belong to."""
        for statement in _MERGE_SETUP:
            self.db.execute(text(statement))
        rows = self.db.execute(text(_MERGE_EVIDENCE)).all()
        self.stats.counts["merge_candidates"] = len(rows)
        for paper_id, name_only_id, hf_author_id, repo, coauthor, shared in rows:
            evidence = [
                reason
                for reason, found in (
                    ("official_repository", repo),
                    ("verified_coauthor", coauthor),
                    ("shared_coauthors", shared >= MIN_SHARED_COAUTHORS),
                )
                if found
            ]
            if not evidence:
                continue
            link = self.db.get(PaperAuthor, (paper_id, name_only_id))
            if self.db.get(PaperAuthor, (paper_id, hf_author_id)) is not None:
                self.db.delete(link)
                action = "remove_link"
            else:
                order = link.author_order
                self.db.delete(link)
                self.db.flush()
                self.db.add(
                    PaperAuthor(
                        paper_id=paper_id, author_id=hf_author_id, author_order=order
                    )
                )
                action = "move_link"
            self.db.flush()
            self.merged_into[name_only_id] = hf_author_id
            self.stats.counts[f"merge_{action}"] += 1
            for reason in evidence:
                self.stats.counts[f"merge_by_{reason}"] += 1
            self.report(
                {
                    "phase": "merge",
                    "action": action,
                    "paper_id": paper_id,
                    "author_id": name_only_id,
                    "to_author_id": hf_author_id,
                    "evidence": evidence,
                    "shared_coauthors": shared,
                }
            )
        self.stats.counts["merge_rows_into"] = len(set(self.merged_into.values()))

    def delete_empty_authors(self) -> None:
        """Delete name-only authors without papers, aliasing them to a namesake."""
        empty = (
            self.db.execute(
                text(
                    """
                    SELECT a.id FROM authors a
                    WHERE a.hf_id IS NULL AND a.hf_username IS NULL
                      AND NOT EXISTS (SELECT 1 FROM paper_authors x WHERE x.author_id = a.id)
                      AND NOT EXISTS (SELECT 1 FROM author_google_scholar_profiles x WHERE x.author_id = a.id)
                      AND NOT EXISTS (SELECT 1 FROM author_google_scholar_candidates x WHERE x.author_id = a.id)
                      AND NOT EXISTS (SELECT 1 FROM author_photos x WHERE x.author_id = a.id)
                      AND NOT EXISTS (
                          SELECT 1 FROM research_follows x
                          WHERE x.kind = 'author' AND x.entity_id = a.id
                      )
                    ORDER BY a.id
                    """
                )
            )
            .scalars()
            .all()
        )
        for author_id in empty:
            author = self.db.get(Author, author_id)
            merged_into = self.merged_into.get(author_id)
            target = self.db.get(Author, merged_into) if merged_into else None
            target = target or (
                self.db.query(Author)
                .filter(
                    Author.id != author_id,
                    Author.id.notin_(empty),
                    text("lower(authors.name) = lower(:name)"),
                )
                .params(name=author.name)
                .order_by(
                    Author.hf_id.isnot(None), Author.hf_username.isnot(None), Author.id
                )
                .first()
            )
            aliases = self.db.query(AuthorAlias).filter_by(author_id=author_id).all()
            if target is None and aliases:
                # Deleting would cascade away aliases that keep old URLs alive.
                self.stats.counts["empty_kept_alias_target"] += 1
                continue
            for alias in aliases:
                alias.author_id = target.id
            if target is not None:
                self.db.add(AuthorAlias(alias_id=author_id, author_id=target.id))
            self.db.delete(author)
            self.db.flush()
            self.stats.counts["empty_deleted"] += 1
            self.stats.counts["empty_aliased"] += target is not None
            self.report(
                {
                    "phase": "empty",
                    "action": "delete_author",
                    "author_id": author_id,
                    "name": author.name,
                    "alias_to": target.id if target else None,
                }
            )
