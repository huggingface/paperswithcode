"""
AI-powered batch processor for extracting GitHub URLs and project pages from papers.

This script processes papers to find GitHub repositories and project pages using:
1. AI extraction via GoogleGenerator (Gemini 3.5 Flash, with 2.5 Flash fallback)
2. Memory monitoring for 4GB RAM systems
3. Database-driven deduplication (no caching needed)
4. Coordination with HF API CRON job via urls_extracted flag

Processing Logic:
- Only processes papers where urls_extracted = FALSE
- Papers imported from HF API have urls_extracted = TRUE (set by import_hf_daily_papers.py)
- This naturally excludes HF API papers without complex query logic
- AI-extracted URLs are saved with source='ai_extraction' and is_official=True
- hf_api URLs always take priority over AI-extracted URLs (enforced by skip_if_official_exists)
- After successful processing, marks paper with urls_extracted = TRUE

Error Handling:
- Any extraction failure (PDF download, provider, parsing) leaves urls_extracted FALSE
  so the paper is retried in a future run
- A paper whose arXiv PDF does not exist is marked processed with the URLs found so far

Logs can be saved at backend/database/logs.

Usage:
```bash
# Process papers with default settings
uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --limit 100

# Memory-safe processing with custom batch size and start year
uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --batch-size 10 --start-year 2020
```
"""

import argparse
import asyncio
import logging
import time
import psutil
from typing import List, Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.genai_steps.extract_github_and_project_page_url import (
    get_project_github_urls,
    warm_pdf_cache,
)
from backend.generators.google_generator import GoogleGenerator
from backend.database.logging_config import setup_logging
from backend.utils.github_utils import parse_github_url

logger = setup_logging("batch_extract", log_level=logging.INFO)


class BatchURLExtractor:
    """Batch processor to extract GitHub URLs and project pages from papers."""

    def __init__(
        self,
        batch_size: int = 20,
        dry_run: bool = False,
        use_paid_tier: bool = False,
        start_year: int = 2014,
    ):
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.start_year = start_year

        requests_per_minute = 10
        requests_per_day = 350 if not use_paid_tier else 10000
        self.generator = GoogleGenerator(
            requests_per_minute=requests_per_minute,
            requests_per_day=requests_per_day,
        )

        self.stats = {
            "papers_found": 0,
            "papers_processed": 0,
            "papers_with_github": 0,
            "papers_with_project_page": 0,
            "papers_with_both": 0,
            "papers_with_neither": 0,
            "github_skipped_existing": 0,
            "project_page_skipped_existing": 0,
            "api_errors": 0,
            "papers_skipped_critical_errors": 0,
            "start_time": time.time(),
        }

        self.process = psutil.Process()
        self.memory_limit_mb = 3500

    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics."""
        memory_info = self.process.memory_info()
        system_memory = psutil.virtual_memory()

        return {
            "process_memory_mb": memory_info.rss / 1024 / 1024,
            "system_memory_percent": system_memory.percent,
            "system_available_mb": system_memory.available / 1024 / 1024,
        }

    def check_memory_safety(self) -> tuple[bool, str]:
        """Check if memory usage is safe for continued processing."""
        memory_stats = self.get_memory_usage()

        if memory_stats["process_memory_mb"] > self.memory_limit_mb:
            return (
                False,
                f"Process memory ({memory_stats['process_memory_mb']:.1f}MB) exceeds limit ({self.memory_limit_mb}MB)",
            )

        if memory_stats["system_memory_percent"] > 85:
            return (
                False,
                f"System memory usage ({memory_stats['system_memory_percent']:.1f}%) too high",
            )

        if memory_stats["system_available_mb"] < 500:
            return (
                False,
                f"Available system memory ({memory_stats['system_available_mb']:.1f}MB) too low",
            )

        return True, "Memory usage is safe"

    def get_papers_missing_urls(
        self, db: Session, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get papers that need URL extraction using the simplified urls_extracted field.

        Papers imported from HF API already have urls_extracted=TRUE, so they won't be processed.
        This keeps the query simple and efficient.
        """

        start_date = f"{self.start_year}-01-01"

        query = """
        SELECT
            p.id,
            p.arxiv_id,
            p.title,
            p.abstract,
            p.date_published,
            p.urls_extracted
        FROM papers p
        WHERE p.abstract IS NOT NULL
          AND p.abstract != ''
          AND p.arxiv_id IS NOT NULL
          AND p.arxiv_id != ''
          AND p.date_published >= :start_date
          AND p.urls_extracted = FALSE
        ORDER BY
            p.date_published DESC NULLS LAST,
            p.id DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        result = db.execute(text(query), {"start_date": start_date}).fetchall()

        papers = [
            {
                "id": row.id,
                "arxiv_id": row.arxiv_id,
                "title": row.title,
                "abstract": row.abstract,
                "urls_extracted": bool(row.urls_extracted),
            }
            for row in result
        ]

        if papers:
            logger.info("📋 Sample of papers to process:")
            for i, paper in enumerate(papers[:3]):
                logger.info(
                    f"  {i + 1}. {paper['arxiv_id']} - {paper['title'][:100]}..."
                )
                logger.info(f"     URLs Extracted: {paper['urls_extracted']}")
                logger.info(f"     Abstract length: {len(paper['abstract'])} chars")

        return papers

    def save_results_to_db(
        self,
        db: Session,
        paper_id: int,
        github_url: str,
        project_page_url: str,
        source: str = "ai_extraction",
    ) -> None:
        """Save extracted URLs to the database using service layer methods.

        Note: This function ALWAYS marks the paper as urls_extracted = TRUE.
        Only call this when extraction was successful (even if no URLs found).
        Do NOT call for critical errors like rate limiting or PDF download failures.
        """
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Paper {paper_id}: Would save GitHub={github_url}, Project={project_page_url}"
            )
            return

        try:
            from backend.services.repository_service import RepositoryService
            from backend.services.project_page_service import ProjectPageService

            repo_service = RepositoryService(db)
            project_service = ProjectPageService(db)

            owner, name = parse_github_url((github_url or "").strip())
            if github_url and not (owner and name):
                logger.info(f"⏭️  Skipped non-repository GitHub URL: {github_url}")
            if owner and name:
                repository = repo_service.create_repository_for_paper(
                    paper_id=str(paper_id),
                    url=github_url.strip(),
                    owner=owner,
                    name=name,
                    num_stars=0,
                    is_official=True,
                    source=source,
                    skip_if_official_exists=True,
                )

                if repository:
                    logger.info(f"💾 Saved GitHub repo: {github_url}")
                    self.stats["papers_with_github"] += 1
                else:
                    logger.info(
                        f"⏭️  Skipped GitHub repo (official exists): {github_url}"
                    )
                    self.stats["github_skipped_existing"] += 1

            if project_page_url and project_page_url.strip():
                project_page = project_service.create_project_page_for_paper(
                    paper_id=str(paper_id),
                    url=project_page_url.strip(),
                    is_official=True,
                    source=source,
                    skip_if_official_exists=True,
                )

                if project_page:
                    logger.info(f"💾 Saved project page: {project_page_url}")
                    self.stats["papers_with_project_page"] += 1
                else:
                    logger.info(
                        f"⏭️  Skipped project page (official exists): {project_page_url}"
                    )
                    self.stats["project_page_skipped_existing"] += 1

            update_paper = """
            UPDATE papers
            SET urls_extracted = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :paper_id
            """
            db.execute(text(update_paper), {"paper_id": paper_id})

            if github_url or project_page_url:
                logger.info(f"✅ Marked paper {paper_id} as processed with URLs found")
            else:
                logger.info(f"🔄 Marked paper {paper_id} as processed (no URLs found)")

            db.commit()

        except Exception:
            db.rollback()
            raise

    async def process_paper(self, paper: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Process a single paper using the unified get_project_github_urls function."""
        arxiv_id = paper["arxiv_id"]
        paper_id = paper["id"]
        abstract = paper["abstract"]

        logger.info(
            f"🤖 Starting AI extraction for {arxiv_id}: {paper.get('title', 'N/A')[:80]}..."
        )

        reasoning, response = await get_project_github_urls(
            arxiv_id=arxiv_id,
            session_id=None,
            use_reasoning=False,
            abstract=abstract,
            generator=self.generator,
        )

        github_url = response.get("github_url", "") if response else ""
        project_page_url = response.get("project_page_url", "") if response else ""

        github_status = f"✅ {github_url}" if github_url else "❌ None"
        project_status = f"✅ {project_page_url}" if project_page_url else "❌ None"
        logger.info(f"🔗 {arxiv_id}: GitHub={github_status}, Project={project_status}")

        self.save_results_to_db(
            db,
            paper_id,
            github_url,
            project_page_url,
            "ai_extraction",
        )

        self.stats["papers_processed"] += 1
        if github_url and project_page_url:
            self.stats["papers_with_both"] += 1
        if not github_url and not project_page_url:
            self.stats["papers_with_neither"] += 1

        return {
            "paper_id": paper_id,
            "arxiv_id": arxiv_id,
            "github_url": github_url,
            "project_page_url": project_page_url,
            "success": True,
        }

    async def process_batch(
        self, papers: List[Dict[str, Any]], db: Session
    ) -> List[Dict[str, Any]]:
        """Process a batch of papers with controlled concurrency."""
        logger.info(f"🚀 Processing batch of {len(papers)} papers (UNIFIED MODE)")

        semaphore = asyncio.Semaphore(3)

        async def process_with_semaphore(paper):
            async with semaphore:
                return await self.process_paper(paper, db)

        results = await asyncio.gather(
            *[process_with_semaphore(paper) for paper in papers], return_exceptions=True
        )

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"❌ Extraction failed for {papers[i]['arxiv_id']} "
                    f"(will retry in a later run): {type(result).__name__}: {result}"
                )
                self.stats["api_errors"] += 1
                self.stats["papers_skipped_critical_errors"] += 1
            else:
                processed_results.append(result)

        return processed_results

    def print_stats(self) -> None:
        """Print processing statistics."""
        elapsed = time.time() - self.stats["start_time"]

        memory_stats = self.get_memory_usage()

        print("\n" + "=" * 60)
        print("📊 AI BATCH PROCESSING STATISTICS")
        print("=" * 60)
        print(f"📅 Start Year Filter: {self.start_year}")
        print(f"⏱️  Total Time: {elapsed:.1f} seconds")
        print(f"📄 Papers Processed: {self.stats['papers_processed']}")

        if self.stats["papers_processed"] > 0:
            print(
                f"🔗 Papers with GitHub: {self.stats['papers_with_github']} ({self.stats['papers_with_github'] / self.stats['papers_processed'] * 100:.1f}%)"
            )
            print(
                f"🌐 Papers with Project Page: {self.stats['papers_with_project_page']} ({self.stats['papers_with_project_page'] / self.stats['papers_processed'] * 100:.1f}%)"
            )
            print(
                f"🎯 Papers with Both: {self.stats['papers_with_both']} ({self.stats['papers_with_both'] / self.stats['papers_processed'] * 100:.1f}%)"
            )
            print(
                f"❌ Papers with Neither: {self.stats['papers_with_neither']} ({self.stats['papers_with_neither'] / self.stats['papers_processed'] * 100:.1f}%)"
            )

        print(f"⚠️  API Errors: {self.stats['api_errors']}")
        print(
            f"🚫 Papers Skipped (Critical Errors): {self.stats['papers_skipped_critical_errors']}"
        )
        print(
            f"⏭️  GitHub URLs Skipped (existing): {self.stats['github_skipped_existing']}"
        )
        print(
            f"⏭️  Project Pages Skipped (existing): {self.stats['project_page_skipped_existing']}"
        )

        print(
            f"💾 Memory Usage: {memory_stats['process_memory_mb']:.1f}MB process, {memory_stats['system_memory_percent']:.1f}% system"
        )
        print(f"💾 Available Memory: {memory_stats['system_available_mb']:.1f}MB")

        if self.stats["papers_processed"] > 0:
            rate = self.stats["papers_processed"] / elapsed
            print(f"⚡ Processing Rate: {rate:.2f} papers/second")

            daily_limit = self.generator.requests_per_day
            estimated_daily = daily_limit

            print(f"📈 Estimated Daily Capacity: {estimated_daily:.0f} papers")
            if estimated_daily > 0:
                print(
                    f"📈 Estimated for 10K papers: {10000 / estimated_daily:.1f} days"
                )

        print("=" * 60)

    async def run(self, limit: Optional[int] = None) -> None:
        """Run the batch processing."""
        logger.info(
            f"🚀 Starting batch URL extraction (limit={limit}, batch_size={self.batch_size}, dry_run={self.dry_run})"
        )

        logger.info("📋 Warming PDF cache for few-shot examples...")
        try:
            cache_info = await warm_pdf_cache()
            logger.info(
                f"✅ PDF cache ready: {cache_info['cached_count']} files, {cache_info['total_size_mb']:.1f} MB"
            )
        except Exception as e:
            logger.warning(f"⚠️  Failed to warm PDF cache: {e}")

        db_session_gen = get_database_session()
        db = next(db_session_gen)

        try:
            papers = self.get_papers_missing_urls(db, limit)
            self.stats["papers_found"] = len(papers)
            logger.info(f"📄 Found {len(papers)} papers needing URL extraction")

            if not papers:
                logger.info("✅ No papers found that need processing")
                return

            for i in range(0, len(papers), self.batch_size):
                memory_safe, memory_message = self.check_memory_safety()
                if not memory_safe:
                    logger.warning(f"⚠️  Memory limit reached: {memory_message}")
                    logger.info("🛑 Stopping processing to avoid system instability")
                    break

                batch = papers[i : i + self.batch_size]
                batch_num = (i // self.batch_size) + 1
                total_batches = (len(papers) + self.batch_size - 1) // self.batch_size

                logger.info(f"📦 Processing batch {batch_num}/{total_batches}")

                await self.process_batch(batch, db)

                if batch_num % 3 == 0 or batch_num == total_batches:
                    self.print_stats()

            self.print_stats()

        except Exception as e:
            logger.error(f"❌ Fatal error in batch processing: {e}")
            raise
        finally:
            db.close()


async def main():
    parser = argparse.ArgumentParser(
        description="AI batch extract GitHub URLs and project pages from papers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum number of papers to process", default=None
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Number of papers to process in each batch",
        default=20,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run without saving results to database"
    )
    parser.add_argument(
        "--paid-tier",
        action="store_true",
        help="Use paid tier rate limits (1000/day instead of 50/day)",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2014,
        help="Start year for filtering papers (default: 2014)",
    )

    args = parser.parse_args()

    extractor = BatchURLExtractor(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        use_paid_tier=args.paid_tier,
        start_year=args.start_year,
    )

    await extractor.run(limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
