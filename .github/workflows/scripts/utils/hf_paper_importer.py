"""
Shared per-paper import helpers for Hugging Face paper data.

Used by both the daily importer (.github/workflows/scripts/daily/import_hf_daily_papers.py) and
the full-history backfill (.github/workflows/scripts/backfill/backfill_hf_papers.py).

This mixin is meant to be combined with `scripts.utils.cron_helpers.DatabaseCronJob`
so it has access to `self.execute_query`, `self.logger`, and counter attributes.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp

from backend.services.author_hf_profile_sync_service import UNCONFIRMED_STATUSES
from backend.utils.github_utils import parse_github_url
from backend.utils.keyword_matching import (
    apply_task_supersession_rules,
    create_keyword_patterns,
    create_keyword_patterns_with_metadata,
    find_matching_items_simple,
    find_matching_items_longest_match,
)
from backend.utils.verify_url import verify_url


class HuggingFacePaperImporterMixin:
    """Reusable helpers for importing/enriching papers from the HF API.

    Expects the consumer (subclass) to:
    - Inherit from `DatabaseCronJob` (provides `self.execute_query`, `self.logger`).
    - Define the counter attributes used below in its `__init__` (e.g.
      `self.new_papers_count`, `self.new_authors_count`, ...).
    - Initialize the keyword pattern dicts to empty in `__init__` so the
      tagging methods are safe no-ops before `load_*_keywords` is called.
    """

    # ------------------------------------------------------------------
    # Keyword pattern loading
    # ------------------------------------------------------------------

    def load_task_keywords(self) -> None:
        """Load tasks with keywords for simple-matching auto-tagging."""
        query = """
            SELECT id, slug, name, keywords
            FROM tasks
            WHERE keywords IS NOT NULL AND keywords != ''
            ORDER BY id
        """
        tasks = self.execute_query(query)
        if not tasks:
            self.logger.warning("No tasks with keywords found")
            return

        self.task_slug_to_id = {task["slug"]: task["id"] for task in tasks}

        (
            self.task_case_sensitive_patterns,
            self.task_case_insensitive_patterns,
        ) = create_keyword_patterns(tasks)

        total = len(self.task_case_sensitive_patterns) + len(
            self.task_case_insensitive_patterns
        )
        self.logger.info(
            f"Loaded {len(tasks)} tasks with {total} unique keywords for auto-tagging (simple matching)"
        )

    def load_method_keywords(self) -> None:
        """Load methods with keywords for longest-match auto-tagging."""
        query = """
            SELECT id, name, keywords
            FROM methods
            WHERE keywords IS NOT NULL AND keywords != ''
            ORDER BY id
        """
        methods = self.execute_query(query)
        if not methods:
            self.logger.warning("No methods with keywords found")
            return

        (
            self.method_case_sensitive_patterns,
            self.method_case_insensitive_patterns,
        ) = create_keyword_patterns_with_metadata(methods)

        total = len(self.method_case_sensitive_patterns) + len(
            self.method_case_insensitive_patterns
        )
        self.logger.info(
            f"Loaded {len(methods)} methods with {total} unique keywords for auto-tagging (longest-match)"
        )

    # ------------------------------------------------------------------
    # HF API fetchers
    # ------------------------------------------------------------------

    async def fetch_paper_detail(
        self,
        arxiv_id: str,
        session: Optional[aiohttp.ClientSession] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict]:
        """Fetch the full per-paper detail from /api/papers/{arxiv_id}."""
        url = f"https://huggingface.co/api/papers/{arxiv_id}"

        async def _do(s: aiohttp.ClientSession) -> Optional[Dict]:
            async with s.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    return await response.json()
                self.logger.debug(
                    f"Detail fetch for {arxiv_id} returned HTTP {response.status}"
                )
                return None

        if session is not None:
            return await _do(session)
        async with aiohttp.ClientSession() as s:
            return await _do(s)

    async def fetch_paper_urls_legacy(
        self, arxiv_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Backwards-compatible helper returning (githubRepo, projectPage)."""
        detail = await self.fetch_paper_detail(arxiv_id)
        if not detail:
            return None, None
        return detail.get("githubRepo"), detail.get("projectPage")

    # ------------------------------------------------------------------
    # Paper queries / inserts
    # ------------------------------------------------------------------

    def get_paper_by_arxiv_id(self, arxiv_id: str) -> Optional[Dict]:
        """Return the existing paper row id (or None) for an arxiv id."""
        results = self.execute_query(
            "SELECT id FROM papers WHERE arxiv_id = %s", (arxiv_id,)
        )
        return results[0] if results else None

    def insert_paper(
        self,
        arxiv_id: str,
        title: str,
        abstract: str,
        date_published: Optional[datetime],
        tldr: Optional[str] = None,
    ) -> Optional[int]:
        """Insert a paper as pending until both HF URL types are linked."""
        query = """
        INSERT INTO papers (arxiv_id, title, abstract, date_published, tldr, urls_extracted, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """
        try:
            results = self.execute_query(
                query, (arxiv_id, title, abstract, date_published, tldr)
            )
            return results[0]["id"] if results else None
        except Exception as e:
            self.logger.error(f"Failed to insert paper {arxiv_id}: {e}")
            return None

    def update_paper_tldr_if_null(self, paper_id: int, tldr: str) -> None:
        """Set the tldr on a paper only if it's currently NULL/empty."""
        if not tldr:
            return
        try:
            self.execute_query(
                """
                UPDATE papers
                SET tldr = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND (tldr IS NULL OR tldr = '')
                """,
                (tldr, paper_id),
            )
        except Exception as e:
            self.logger.error(f"Failed to update tldr for paper {paper_id}: {e}")

    def paper_has_complete_urls(self, paper_id: int) -> bool:
        """True if paper has both official URL associations."""
        rows = self.execute_query(
            """
            SELECT
                EXISTS(
                    SELECT 1 FROM paper_repositories
                    WHERE paper_id = %s AND is_official = TRUE
                ) AS has_repo,
                EXISTS(
                    SELECT 1
                    FROM paper_project_pages ppp
                    JOIN project_pages pp ON pp.id = ppp.project_page_id
                    WHERE ppp.paper_id = %s AND pp.is_official = TRUE
                ) AS has_page
            """,
            (paper_id, paper_id),
        )
        if not rows:
            return False
        row = rows[0]
        return bool(row.get("has_repo")) and bool(row.get("has_page"))

    def refresh_urls_extracted(self, paper_id: int) -> None:
        """Mark extraction complete only when both official URL types exist."""
        complete = self.paper_has_complete_urls(paper_id)
        self.execute_query(
            """
            UPDATE papers
            SET urls_extracted = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (complete, paper_id),
        )

    @staticmethod
    def parse_published_at(published_at: Optional[str]):
        """Parse the HF publishedAt ISO string to a `date` (or None)."""
        if not published_at:
            return None
        try:
            return datetime.fromisoformat(published_at.replace("Z", "+00:00")).date()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Author handling
    # ------------------------------------------------------------------

    def process_authors(
        self, paper_id: int, authors_data: List[Dict], link_to_paper: bool = True
    ) -> None:
        """Create/update authors for a paper and (optionally) link them.

        An author claimed on HF is linked through the account's own author row
        (created on first sight) and the link is marked claimed; anyone else is
        matched by name to a row without an HF account, so a namesake's papers
        never land on someone's profile.

        When `link_to_paper=False` only the profiles of already known HF
        accounts are refreshed; claims on existing papers are applied by the
        `sync_hf_author_profiles` job.
        """
        for order, author_data in enumerate(authors_data, start=1):
            author_name = author_data.get("name")
            if not author_name:
                continue

            user_info = author_data.get("user") or {}
            claimed = bool(
                user_info.get("_id")
                and user_info.get("user")
                and not author_data.get("hidden")
                and user_info.get("type", "user") == "user"
                and author_data.get("status") not in UNCONFIRMED_STATUSES
            )
            if claimed:
                profile = (
                    user_info["user"],
                    user_info["_id"],
                    user_info.get("avatarUrl"),
                    author_data.get("status"),
                    bool(user_info.get("isPro", False)),
                )
                author_id = self.find_hf_author(user_info["_id"], user_info["user"])
                if author_id:
                    self.update_author_hf_info(author_id, *profile)
                elif link_to_paper:
                    author_id = self.create_author(author_name, *profile)
            elif link_to_paper:
                author_id = self.get_or_create_author(author_name)
            else:
                continue

            if author_id and link_to_paper:
                self.link_paper_author(paper_id, author_id, order, claimed)

    def find_hf_author(self, hf_id: str, hf_username: str) -> Optional[int]:
        """Return the author row of this HF account, if it has one."""
        results = self.execute_query(
            "SELECT id FROM authors WHERE hf_id = %s OR hf_username = %s"
            " ORDER BY hf_id = %s DESC, id LIMIT 1",
            (hf_id, hf_username, hf_id),
        )
        return results[0]["id"] if results else None

    def get_or_create_author(self, name: str) -> Optional[int]:
        """Find the name-only author with this name (any case) or create one."""
        results = self.execute_query(
            """
            SELECT id FROM authors
            WHERE LOWER(name) = LOWER(%s) AND hf_id IS NULL AND hf_username IS NULL
            ORDER BY name <> %s, id
            LIMIT 1
            """,
            (name, name),
        )
        if results:
            return results[0]["id"]
        return self.create_author(name)

    def create_author(
        self,
        name: str,
        hf_username: Optional[str] = None,
        hf_id: Optional[str] = None,
        hf_avatar_url: Optional[str] = None,
        hf_status: Optional[str] = None,
        hf_is_pro: bool = False,
    ) -> Optional[int]:
        """Insert a new author row."""
        query = """
        INSERT INTO authors (name, hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """
        try:
            results = self.execute_query(
                query, (name, hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro)
            )
            if results:
                self.new_authors_count += 1
                return results[0]["id"]
            return None
        except Exception as e:
            self.logger.error(f"Failed to create author {name}: {e}")
            return None

    def update_author_hf_info(
        self,
        author_id: int,
        hf_username: Optional[str],
        hf_id: Optional[str],
        hf_avatar_url: Optional[str],
        hf_status: Optional[str],
        hf_is_pro: bool,
    ) -> None:
        """Backfill an author row with HF profile data (no overwrite of existing values)."""
        query = """
        UPDATE authors
        SET hf_username = COALESCE(hf_username, %s),
            hf_id = COALESCE(hf_id, %s),
            hf_avatar_url = COALESCE(hf_avatar_url, %s),
            hf_status = COALESCE(hf_status, %s),
            hf_is_pro = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """
        try:
            self.execute_query(
                query,
                (hf_username, hf_id, hf_avatar_url, hf_status, hf_is_pro, author_id),
            )
        except Exception as e:
            self.logger.error(f"Failed to update author {author_id} HF info: {e}")

    def link_paper_author(
        self, paper_id: int, author_id: int, author_order: int, claimed: bool
    ) -> None:
        """Link a paper to an author (idempotent)."""
        query = """
        INSERT INTO paper_authors (paper_id, author_id, author_order, claimed)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (paper_id, author_id) DO NOTHING
        """
        try:
            self.execute_query(query, (paper_id, author_id, author_order, claimed))
        except Exception as e:
            self.logger.error(
                f"Failed to link paper {paper_id} to author {author_id}: {e}"
            )

    # ------------------------------------------------------------------
    # Repository / project page handling
    # ------------------------------------------------------------------

    @staticmethod
    def is_valid_github_url(url: str) -> bool:
        try:
            parsed = urlparse(url)
            return (
                parsed.netloc.lower() in ["github.com", "www.github.com"]
                and len(parsed.path.strip("/").split("/")) >= 2
            )
        except Exception:
            return False

    def insert_repository(self, paper_id: int, github_url: str) -> None:
        """Link a paper to a github repository (creating the repo row if needed)."""
        if not self.is_valid_github_url(github_url):
            self.logger.warning(f"Invalid GitHub URL: {github_url}")
            return

        owner, name = parse_github_url(github_url)

        results = self.execute_query(
            "SELECT id FROM repositories WHERE url = %s", (github_url,)
        )

        if results:
            repo_id = results[0]["id"]
            link_results = self.execute_query(
                "SELECT 1 FROM paper_repositories WHERE paper_id = %s AND repository_id = %s",
                (paper_id, repo_id),
            )
            if link_results:
                return

            try:
                self.execute_query(
                    """
                    INSERT INTO paper_repositories (paper_id, repository_id, is_official)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (paper_id, repository_id) DO NOTHING
                    """,
                    (paper_id, repo_id, True),
                )
                self.logger.debug(f"Linked existing repository to paper: {github_url}")
            except Exception as e:
                self.logger.error(
                    f"Failed to link repository {github_url} to paper {paper_id}: {e}"
                )
            return

        try:
            results = self.execute_query(
                """
                INSERT INTO repositories (url, owner, name, source, created_at, updated_at)
                VALUES (%s, %s, %s, 'hf_api', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (github_url, owner, name),
            )
            if results:
                repo_id = results[0]["id"]
                self.execute_query(
                    """
                    INSERT INTO paper_repositories (paper_id, repository_id, is_official)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (paper_id, repository_id) DO NOTHING
                    """,
                    (paper_id, repo_id, True),
                )
                self.new_repos_count += 1
                self.logger.debug(f"Added new repository: {github_url}")
        except Exception as e:
            self.logger.error(f"Failed to insert repository {github_url}: {e}")

    def insert_project_page(
        self, paper_id: int, project_url: str, skip_verification: bool = False
    ) -> None:
        """Link a paper to a project page (creating the row if needed).

        Pass `skip_verification=True` when calling from inside a running event
        loop (e.g. async code): in that case the caller is responsible for
        verifying the URL via `verify_url(...)` beforehand.
        """
        if not skip_verification:
            if not asyncio.run(verify_url(project_url)):
                self.logger.warning(f"Invalid project page URL: {project_url}")
                return

        results = self.execute_query(
            "SELECT id FROM project_pages WHERE url = %s", (project_url,)
        )

        if results:
            page_id = results[0]["id"]
            link_results = self.execute_query(
                "SELECT 1 FROM paper_project_pages WHERE paper_id = %s AND project_page_id = %s",
                (paper_id, page_id),
            )
            if link_results:
                return

            try:
                self.execute_query(
                    """
                    INSERT INTO paper_project_pages (paper_id, project_page_id)
                    VALUES (%s, %s)
                    ON CONFLICT (paper_id, project_page_id) DO NOTHING
                    """,
                    (paper_id, page_id),
                )
                self.logger.debug(
                    f"Linked existing project page to paper: {project_url}"
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to link project page {project_url} to paper {paper_id}: {e}"
                )
            return

        try:
            results = self.execute_query(
                """
                INSERT INTO project_pages (url, is_official, source, created_at, updated_at)
                VALUES (%s, %s, 'hf_api', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (project_url, True),
            )
            if results:
                page_id = results[0]["id"]
                self.execute_query(
                    """
                    INSERT INTO paper_project_pages (paper_id, project_page_id)
                    VALUES (%s, %s)
                    ON CONFLICT (paper_id, project_page_id) DO NOTHING
                    """,
                    (paper_id, page_id),
                )
                self.new_pages_count += 1
                self.logger.debug(f"Added new project page: {project_url}")
        except Exception as e:
            self.logger.error(f"Failed to insert project page {project_url}: {e}")

    # ------------------------------------------------------------------
    # Task / method tagging
    # ------------------------------------------------------------------

    def tag_paper_with_tasks(
        self, paper_id: int, title: Optional[str], abstract: Optional[str]
    ) -> None:
        if not getattr(self, "task_case_sensitive_patterns", None) and not getattr(
            self, "task_case_insensitive_patterns", None
        ):
            return

        text_parts = []
        if title:
            text_parts.append(title)
        if abstract:
            text_parts.append(abstract)
        text = " ".join(text_parts).strip()
        if not text:
            return

        matching_task_ids = find_matching_items_simple(
            text,
            self.task_case_sensitive_patterns,
            self.task_case_insensitive_patterns,
        )
        slug_to_id = getattr(self, "task_slug_to_id", {})
        matching_task_ids = apply_task_supersession_rules(
            matching_task_ids, slug_to_id, text, title
        )
        if not matching_task_ids:
            return

        query = """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (%s, %s, 'auto')
            ON CONFLICT (paper_id, task_id) DO NOTHING
        """
        for task_id in matching_task_ids:
            try:
                self.execute_query(query, (paper_id, task_id))
                self.new_tasks_count += 1
            except Exception as e:
                self.logger.error(
                    f"Failed to link paper {paper_id} to task {task_id}: {e}"
                )

    def tag_paper_with_methods(
        self, paper_id: int, title: Optional[str], abstract: Optional[str]
    ) -> None:
        if not getattr(self, "method_case_sensitive_patterns", None) and not getattr(
            self, "method_case_insensitive_patterns", None
        ):
            return

        text_parts = []
        if title:
            text_parts.append(title)
        if abstract:
            text_parts.append(abstract)
        text = " ".join(text_parts).strip()
        if not text:
            return

        matching_method_ids = find_matching_items_longest_match(
            text,
            self.method_case_sensitive_patterns,
            self.method_case_insensitive_patterns,
        )
        if not matching_method_ids:
            return

        query = """
            WITH inserted AS (
                INSERT INTO paper_methods (paper_id, method_id)
                SELECT %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM paper_method_exclusions
                    WHERE paper_id = %s AND method_id = %s
                )
                ON CONFLICT (paper_id, method_id) DO NOTHING
                RETURNING paper_id, method_id
            )
            INSERT INTO paper_method_evidence
                (paper_id, method_id, evidence_type)
            SELECT paper_id, method_id, 'keyword' FROM inserted
            UNION ALL
            SELECT %s, %s, 'keyword'
            WHERE NOT EXISTS (SELECT 1 FROM inserted)
              AND EXISTS (
                SELECT 1 FROM paper_methods
                WHERE paper_id = %s AND method_id = %s
            )
            ON CONFLICT (paper_id, method_id, evidence_type)
            DO UPDATE SET last_seen_at = now()
        """
        for method_id in matching_method_ids:
            try:
                self.execute_query(
                    query,
                    (
                        paper_id,
                        method_id,
                        paper_id,
                        method_id,
                        paper_id,
                        method_id,
                        paper_id,
                        method_id,
                    ),
                )
                self.new_methods_count += 1
            except Exception as e:
                self.logger.error(
                    f"Failed to link paper {paper_id} to method {method_id}: {e}"
                )
