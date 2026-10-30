"""
Semantic Scholar API service for fetching citation counts and paper metadata.

This service handles interactions with the Semantic Scholar API to:
- Fetch citation counts for papers
- Search for papers by title/ArXiv ID
- Update paper metadata with citation information
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from backend.models.database import Paper as DBPaper
from backend.utils.exceptions import DatabaseError

# Configure logging
logger = logging.getLogger(__name__)

# Semantic Scholar API configuration
SEMANTIC_SCHOLAR_BASE_URL = "https://api.semanticscholar.org/graph/v1"
REQUEST_TIMEOUT = 30.0
RATE_LIMIT_DELAY = 1.0  # Delay between requests to respect rate limits (1 req/sec)
CITATION_UPDATE_INTERVAL = timedelta(days=7)  # Update citations weekly


class SemanticScholarUnavailableError(Exception):
    """Semantic Scholar could not answer, so the lookup result is unknown."""


class SemanticScholarService:
    """
    Service for interacting with the Semantic Scholar API.
    """

    def __init__(self, db: Session, api_key: Optional[str] = None):
        """
        Initialize the Semantic Scholar service.

        Args:
            db: Database session
            api_key: Optional API key for higher rate limits
        """
        self.db = db
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["x-api-key"] = api_key

    async def _make_request(
        self, url: str, params: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make an HTTP request to the Semantic Scholar API with rate limiting.

        Args:
            url: API endpoint URL
            params: Query parameters

        Returns:
            JSON response data, or None when Semantic Scholar rejects the lookup

        Raises:
            SemanticScholarUnavailableError: On rate limiting, server errors, or
                transport failures, where absence of data is not evidence.
        """
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.get(url, headers=self.headers, params=params)
        except httpx.HTTPError as error:
            raise SemanticScholarUnavailableError(str(error)) from error

        if response.status_code == 200:
            return response.json()
        if response.status_code == 429:
            await asyncio.sleep(RATE_LIMIT_DELAY * 2)
            raise SemanticScholarUnavailableError("rate limited")
        if response.status_code >= 500:
            raise SemanticScholarUnavailableError(f"HTTP {response.status_code}")
        logger.warning(f"Semantic Scholar API request failed: {response.status_code}")
        return None

    async def search_paper_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """
        Search for a paper by title using Semantic Scholar API.

        Args:
            title: Paper title to search for

        Returns:
            Paper data with citation count or None if not found
        """
        url = f"{SEMANTIC_SCHOLAR_BASE_URL}/paper/search"
        params = {
            "query": title,
            "fields": "paperId,title,citationCount,year,authors",
            "limit": 1,
        }

        response = await self._make_request(url, params)
        if response and response.get("data"):
            papers = response["data"]
            if papers:
                # Return the first (most relevant) result
                return papers[0]

        return None

    async def search_paper_by_arxiv_id(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """
        Search for a paper by ArXiv ID using Semantic Scholar API.

        Args:
            arxiv_id: ArXiv ID (e.g., "1706.03762")

        Returns:
            Paper data with citation count or None if not found
        """
        # Try direct lookup first
        url = f"{SEMANTIC_SCHOLAR_BASE_URL}/paper/arXiv:{arxiv_id}"
        params = {"fields": "paperId,title,citationCount,year,authors"}

        response = await self._make_request(url, params)
        if response:
            return response

        return None

    async def get_paper_by_semantic_scholar_id(
        self, paper_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get paper details by Semantic Scholar paper ID.

        Args:
            paper_id: Semantic Scholar paper ID

        Returns:
            Paper data with citation count or None if not found
        """
        url = f"{SEMANTIC_SCHOLAR_BASE_URL}/paper/{paper_id}"
        params = {"fields": "paperId,title,citationCount,year,authors"}

        return await self._make_request(url, params)

    def _normalize_title(self, title: str) -> str:
        """
        Normalize a title for comparison by removing extra whitespace,
        converting to lowercase, and removing common punctuation.
        """
        import re

        # Convert to lowercase and remove extra whitespace
        normalized = re.sub(r"\s+", " ", title.lower().strip())
        # Remove common punctuation that might differ between sources
        normalized = re.sub(r"[^\w\s]", "", normalized)
        return normalized

    def _titles_match(self, title1: str, title2: str) -> bool:
        """
        Check if two titles match after normalization.
        """
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)
        return norm1 == norm2

    async def update_paper_citation_count(self, db_paper: DBPaper) -> bool:
        """
        Update citation count for a single paper.
        Only updates if there's a 100% title match between our database and Semantic Scholar.

        Args:
            db_paper: Database paper instance

        Returns:
            True if successfully updated, False otherwise
        """
        try:
            # Skip if recently updated
            if (
                db_paper.citation_updated_at
                and datetime.now() - db_paper.citation_updated_at.replace(tzinfo=None)
                < CITATION_UPDATE_INTERVAL
            ):
                return True

            # Try to find paper by Semantic Scholar ID first
            paper_data = None
            if db_paper.semantic_scholar_id:
                paper_data = await self.get_paper_by_semantic_scholar_id(
                    db_paper.semantic_scholar_id
                )

            # If not found, try by ArXiv ID
            if not paper_data:
                paper_data = await self.search_paper_by_arxiv_id(db_paper.arxiv_id)

            # If still not found, try by title
            if not paper_data:
                paper_data = await self.search_paper_by_title(db_paper.title)

            if paper_data:
                # CRITICAL: Verify title match before updating
                ss_title = paper_data.get("title", "")
                if self._titles_match(db_paper.title, ss_title):
                    # Update paper with citation data
                    db_paper.citation_count = paper_data.get("citationCount", 0)
                    db_paper.semantic_scholar_id = paper_data.get("paperId")
                    db_paper.citation_updated_at = datetime.now()

                    self.db.commit()

                    logger.info(
                        f"✅ Updated citation count for paper {db_paper.arxiv_id}: {db_paper.citation_count} citations (title match confirmed)"
                    )
                    return True
                else:
                    # Titles don't match - mark as processed but don't update citation count
                    db_paper.semantic_scholar_id = None  # Clear any incorrect ID
                    db_paper.citation_updated_at = datetime.now()
                    self.db.commit()

                    logger.warning(
                        f"❌ Title mismatch for ArXiv {db_paper.arxiv_id}: '{db_paper.title}' vs '{ss_title}' - skipping citation update"
                    )
                    return False
            else:
                # Mark as processed even if not found to avoid repeated attempts
                db_paper.semantic_scholar_id = None
                db_paper.citation_updated_at = datetime.now()
                self.db.commit()

                logger.info(
                    f"Could not find paper {db_paper.arxiv_id} in Semantic Scholar"
                )
                return False

        except SQLAlchemyError as e:
            logger.error(
                f"Error updating citation count for paper {db_paper.arxiv_id}: {str(e)}"
            )
            self.db.rollback()
            return False

    async def batch_update_citation_counts(self, limit: int = 100) -> int:
        """
        Update citation counts for papers that need updating.

        Args:
            limit: Maximum number of papers to update in this batch

        Returns:
            Number of papers successfully updated
        """
        try:
            # Find papers that need citation updates
            cutoff_date = datetime.now() - CITATION_UPDATE_INTERVAL

            papers_to_update = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(
                    or_(
                        DBPaper.citation_updated_at.is_(None),
                        DBPaper.citation_updated_at < cutoff_date,
                    )
                )
                .order_by(DBPaper.date_published.desc())
                .limit(limit)
                .all()
            )

            updated_count = 0
            for paper in papers_to_update:
                try:
                    if await self.update_paper_citation_count(paper):
                        updated_count += 1
                except SemanticScholarUnavailableError as error:
                    # Leave the paper untouched so the next batch retries it.
                    logger.warning(
                        f"Stopping citation batch, Semantic Scholar unavailable: {error}"
                    )
                    break

                # Rate limiting
                await asyncio.sleep(RATE_LIMIT_DELAY)

            logger.info(
                f"Updated citation counts for {updated_count}/{len(papers_to_update)} papers"
            )
            return updated_count

        except Exception as e:
            logger.error(f"Error in batch citation update: {str(e)}")
            raise DatabaseError(f"Error updating citation counts: {str(e)}")

    async def get_highly_cited_papers(
        self, query: str, limit: int = 10
    ) -> List[Tuple[str, int]]:
        """
        Search for highly cited papers matching a query.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of tuples (paper_title, citation_count)
        """
        url = f"{SEMANTIC_SCHOLAR_BASE_URL}/paper/search"
        params = {
            "query": query,
            "fields": "title,citationCount",
            "limit": limit,
            "sort": "citationCount:desc",
        }

        response = await self._make_request(url, params)
        if response and response.get("data"):
            papers = response["data"]
            return [
                (paper.get("title", ""), paper.get("citationCount", 0))
                for paper in papers
            ]

        return []
