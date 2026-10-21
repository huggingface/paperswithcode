"""
Hourly Citation Count Update CRON Job

Optimized version that processes a bounded chunk of papers each hour while staying
within Semantic Scholar's API limits.

Rate Limits (Semantic Scholar API):
- 1 request per second across all endpoints
- Must stay below this threshold to avoid rejected requests

Optimized Strategy:
- Snapshot at most 1,500 papers per run so updates cannot invalidate pagination
- Use conservative rate limiting with buffer for API variations and retries
- Prioritize papers that haven't been updated recently
- Stop at a soft deadline, flush completed results, and defer the remainder
- Efficient async processing with proper error handling
- Skip papers updated within the last 30 days (configurable)

Schedule: Hourly (every hour)
Dependencies: PostgreSQL, Semantic Scholar API

Performance:
- Bounded hourly runs keep GitHub Actions and VPS load predictable under throttling
"""

import asyncio
import json
import math
import signal
import sys
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Dict, Optional, Any
import httpx
from dataclasses import dataclass

from scripts.utils.cron_helpers import DatabaseCronJob
from backend.config import get_settings
from backend.services.paper_service import PaperService
from backend.database.connection import get_database_session
from backend.utils.exceptions import DatabaseError


@dataclass
class CitationResult:
    """Result of citation lookup for a paper."""

    paper_id: int
    arxiv_id: str
    title: str
    citation_count: int
    semantic_scholar_id: Optional[str]
    success: bool
    error_message: Optional[str] = None


class CitationHourlyUpdateJob(DatabaseCronJob):
    """Hourly job to update paper citation counts with optimized throughput."""

    def __init__(self):
        super().__init__(job_name="update_citations_hourly", log_level="INFO")
        self.settings = get_settings()

        # Initialize paper service - get the actual session from the generator
        self.db_session = next(get_database_session())
        self.paper_service = PaperService(self.db_session)

        # Semantic Scholar API configuration
        self.api_key = self.settings.semantic_scholar_api_key
        self.base_url = "https://api.semanticscholar.org/graph/v1"

        # Conservative hourly bounds leave room for Semantic Scholar throttling.
        self.request_delay = 1.5
        self.batch_size = 100  # Larger batches for efficiency
        self.max_papers_per_run = 1500
        self.request_timeout = 10.0  # Shorter timeout for hourly jobs
        self.update_threshold_days = (
            7  # Only update papers older than this (reduced for more frequent updates)
        )
        self.chunk_size = 500  # Process papers in smaller chunks to reduce memory usage
        # Each run refreshes at least this share of the cycle, so papers that
        # were refreshed on the same days do not all come due together.
        self.steady_rate_headroom = 1.2

        # Timeout protection: keep each hourly tick bounded.
        self.max_runtime_seconds = 45 * 60
        self.soft_runtime_seconds = 40 * 60
        self.flush_reserve_seconds = 30
        self.deadline_monotonic = None
        self.shutdown_requested = False

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Statistics
        self.stats = {
            "papers_found": 0,
            "papers_processed": 0,
            "citations_updated": 0,
            "papers_not_found": 0,
            "api_errors": 0,
            "rate_limit_hits": 0,
            "processing_errors": 0,
            "api_calls": 0,
            "api_successes": 0,
            "credential_failures": 0,
            "papers_selected": 0,
            "papers_deferred": 0,
            "papers_refreshed_early": 0,
            "deadline_reached": False,
            "shutdown_requested": False,
            "elapsed_seconds": 0,
        }

        # HTTP client will be created in async context
        self.client = None

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        self.logger.warning(f"Received {signal_name} - initiating graceful shutdown")
        self.shutdown_requested = True

    def run(self):
        """Main execution logic for citation updates."""
        self.logger.info("Starting hourly citation count update")

        # Get total count of papers that need citation updates
        total_papers = self.get_papers_count()
        self.logger.info(f"Found {total_papers} papers to update")

        # Refresh at least the steady hourly share, topping up with papers
        # that are not due yet, and at most the rate-limit bound.
        papers_to_process = min(
            max(total_papers, self.steady_papers_per_run()),
            self.max_papers_per_run,
        )
        if papers_to_process == 0:
            self.logger.info("No papers need citation updates at this time")
            return
        if papers_to_process < total_papers:
            self.logger.info(
                f"Limited to {papers_to_process} papers for this hourly run"
            )

        # The soft deadline leaves time to flush the current batch and emit a
        # successful summary before both the internal and launcher hard limits.
        started_monotonic = time.monotonic()
        self.deadline_monotonic = started_monotonic + self.soft_runtime_seconds

        # Process one stable, bounded selection in chunks. The selected rows
        # leave the pending set as they are updated, so querying each chunk
        # with an increasing OFFSET would skip work.
        try:
            asyncio.run(
                asyncio.wait_for(
                    self.process_papers_in_streaming_chunks(papers_to_process),
                    timeout=self.max_runtime_seconds,
                )
            )
        except asyncio.TimeoutError:
            self.logger.error(
                f"Job timed out after {self.max_runtime_seconds}s - "
                f"this prevents zombie processes"
            )
            self.log_summary()
            raise RuntimeError("citation update exceeded its runtime limit")
        except KeyboardInterrupt:
            self.logger.warning("Job interrupted by user")
            raise

        self.stats["papers_deferred"] = max(
            0, self.stats["papers_found"] - self.stats["papers_processed"]
        )
        self.stats["shutdown_requested"] = self.shutdown_requested
        self.stats["elapsed_seconds"] = round(time.monotonic() - started_monotonic, 1)

        # Log summary
        self.log_summary()

        if self.stats["credential_failures"]:
            raise RuntimeError("Semantic Scholar credential was rejected")
        if (
            self.stats["api_calls"]
            and self.stats["api_successes"] == 0
            and (self.stats["api_errors"] or self.stats["rate_limit_hits"])
        ):
            raise RuntimeError("Semantic Scholar produced no successful responses")

        # Update database statistics (less frequent for hourly jobs)
        if (
            datetime.now().hour % 6 == 0
            and not self.stats["deadline_reached"]
            and not self.shutdown_requested
        ):  # Only every 6 hours when the run retained maintenance headroom
            self.vacuum_analyze_table("papers")

    def get_papers_count(self) -> int:
        """Get count of papers that need citation updates."""
        count = self.paper_service.get_papers_needing_citation_update_count(
            self.update_threshold_days
        )
        self.stats["papers_found"] = count
        return count

    def steady_papers_per_run(self) -> int:
        """Return the hourly share that refreshes every paper once per cycle."""
        refreshable = self.paper_service.get_citation_refreshable_count()
        cycle_hours = self.update_threshold_days * 24
        return math.ceil(refreshable * self.steady_rate_headroom / cycle_hours)

    def get_early_refresh_chunk(self, limit: int) -> List[Dict]:
        """Get not-yet-due papers that were refreshed longest ago."""
        return self.paper_service.get_papers_for_early_citation_refresh(
            limit, self.update_threshold_days
        )

    def get_papers_chunk(self, offset: int, limit: int) -> List[Dict]:
        """Get a chunk of papers that need citation updates."""
        return self.paper_service.get_papers_needing_citation_update_chunk(
            offset, limit, self.update_threshold_days
        )

    async def process_papers_in_streaming_chunks(self, total_papers_to_process: int):
        """Process a stable bounded selection in memory-efficient chunks."""
        papers = self.get_papers_chunk(0, total_papers_to_process)
        early = []
        if len(papers) < total_papers_to_process:
            early = self.get_early_refresh_chunk(total_papers_to_process - len(papers))
        papers += early
        # End the selection's read transaction before slow API calls: the
        # database role kills sessions idle in a transaction for 10 minutes.
        self.db_session.close()
        self.stats["papers_refreshed_early"] = len(early)
        self.stats["papers_selected"] = len(papers)
        if not papers:
            self.logger.info("No pending papers remained after selection")
            return

        total_chunks = (len(papers) + self.chunk_size - 1) // self.chunk_size

        self.logger.info(
            f"Processing {len(papers)} selected papers in {total_chunks} "
            f"chunks of {self.chunk_size}"
        )

        start_time = time.time()

        for chunk_num in range(total_chunks):
            offset = chunk_num * self.chunk_size
            chunk = papers[offset : offset + self.chunk_size]

            self.logger.info(
                f"Processing chunk {chunk_num + 1}/{total_chunks} "
                f"(selected_offset={offset}, size={len(chunk)})"
            )

            chunk_start = time.time()
            completed_chunk = await self.process_papers_with_rate_limiting(chunk)

            # Log chunk completion and memory efficiency
            chunk_elapsed = time.time() - chunk_start
            total_elapsed = time.time() - start_time
            rate = (
                self.stats["papers_processed"] / total_elapsed
                if total_elapsed > 0
                else 0
            )

            progress = ((chunk_num + 1) / total_chunks) * 100
            self.logger.info(
                f"Chunk {chunk_num + 1}/{total_chunks} completed in {chunk_elapsed:.1f}s - "
                f"Progress: {progress:.1f}% - "
                f"Rate: {rate:.1f} papers/sec - "
                f"Updated: {self.stats['citations_updated']}"
            )

            if not completed_chunk:
                self.logger.info(
                    "Stopping citation refresh cleanly; remaining selected "
                    "papers stay eligible for the next hourly run"
                )
                break

            # Small delay between chunks to prevent overwhelming the system
            if chunk_num < total_chunks - 1:
                await asyncio.sleep(1)

    def _can_start_request(self) -> bool:
        """Return whether another request can finish before the soft deadline."""
        if self.shutdown_requested:
            return False
        if self.deadline_monotonic is None:
            return True
        required = (
            self.request_timeout + self.request_delay + self.flush_reserve_seconds
        )
        if self.deadline_monotonic - time.monotonic() > required:
            return True
        self.stats["deadline_reached"] = True
        return False

    async def process_papers_with_rate_limiting(self, papers: List[Dict]) -> bool:
        """Process papers until the chunk completes or the soft deadline arrives."""
        self.logger.debug(
            f"Processing {len(papers)} papers with {self.request_delay}s delays"
        )

        # Create HTTP client with optimized settings
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=10)

        async with httpx.AsyncClient(
            timeout=self.request_timeout, limits=limits, headers=headers
        ) as client:
            self.client = client

            # Process papers in batches
            total_batches = (len(papers) + self.batch_size - 1) // self.batch_size

            for batch_num in range(total_batches):
                start_idx = batch_num * self.batch_size
                end_idx = min(start_idx + self.batch_size, len(papers))
                batch = papers[start_idx:end_idx]

                self.logger.debug(
                    f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} papers)"
                )

                # Process each paper in the batch with rate limiting
                batch_results = []
                completed_batch = True

                for paper in batch:
                    if not self._can_start_request():
                        completed_batch = False
                        break
                    try:
                        result = await self.process_single_paper(paper)
                        batch_results.append(result)

                        # Optimized rate limiting - wait between each request
                        if result:  # Only count actual API calls
                            await asyncio.sleep(self.request_delay)

                    except Exception as e:
                        self.logger.error(
                            f"Error processing paper {paper.get('id')}: {e}"
                        )
                        self.stats["processing_errors"] += 1
                        if self.stats["credential_failures"]:
                            raise

                # Update database with batch results
                if batch_results:
                    self.update_citations_batch(batch_results)

                if not completed_batch:
                    return False

        return True

    async def process_single_paper(self, paper: Dict) -> Optional[CitationResult]:
        """Process a single paper to update its citation count."""
        paper_id = paper["id"]
        arxiv_id = paper["arxiv_id"]
        title = paper["title"]

        self.stats["papers_processed"] += 1

        # Log high-priority papers
        priority_type = paper.get("priority_type", "UNKNOWN")
        if priority_type in ["NEVER_UPDATED", "ZERO_CITATIONS"]:
            self.logger.debug(
                f"Processing {priority_type} paper: {arxiv_id} (current citations: {paper.get('citation_count', 0)})"
            )

        # Fetch citation data from Semantic Scholar API
        citation_data = await self.fetch_citation_data(arxiv_id, title)

        if citation_data:
            new_citation_count = citation_data.get("citationCount", 0)
            current_citation_count = paper.get("citation_count", 0)

            # Log significant updates for high-priority papers
            if (
                priority_type in ["NEVER_UPDATED", "ZERO_CITATIONS"]
                and new_citation_count != current_citation_count
            ):
                self.logger.info(
                    f"Updated {priority_type} paper {arxiv_id}: {current_citation_count} → {new_citation_count} citations"
                )

            return CitationResult(
                paper_id=paper_id,
                arxiv_id=arxiv_id,
                title=title,
                citation_count=new_citation_count,
                semantic_scholar_id=citation_data.get("paperId"),
                success=True,
            )
        else:
            # Mark as processed but not found
            return CitationResult(
                paper_id=paper_id,
                arxiv_id=arxiv_id,
                title=title,
                citation_count=0,
                semantic_scholar_id=None,
                success=False,
                error_message="Not found in Semantic Scholar",
            )

    async def fetch_citation_data(
        self, arxiv_id: str, title: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch citation data from Semantic Scholar API with optimized error handling."""
        url = f"{self.base_url}/paper/arXiv:{arxiv_id}"
        params = {"fields": "paperId,title,citationCount,year"}

        try:
            for attempt in range(3):
                self.stats["api_calls"] += 1
                response = await self.client.get(url, params=params)
                if response.status_code != 429:
                    break
                self.stats["rate_limit_hits"] += 1
                delay = 10.0 * (attempt + 1)
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        try:
                            retry_at = parsedate_to_datetime(retry_after)
                            delay = max(delay, retry_at.timestamp() - time.time())
                        except (TypeError, ValueError, OverflowError):
                            pass  # Malformed provider hint: retain bounded backoff.
                if attempt == 2 or delay > 60 or not self._can_start_request():
                    raise RuntimeError("Semantic Scholar rate limit; deferred")
                if self.deadline_monotonic is not None and (
                    self.deadline_monotonic - time.monotonic()
                    <= delay + self.request_timeout + self.flush_reserve_seconds
                ):
                    self.stats["deadline_reached"] = True
                    raise RuntimeError("Semantic Scholar retry exceeds run deadline")
                self.logger.warning(
                    "Rate limited for %s; retrying in %.1fs", arxiv_id, delay
                )
                await asyncio.sleep(delay)
                if not self._can_start_request():
                    raise RuntimeError("Semantic Scholar retry deferred at deadline")

            if response.status_code == 200:
                self.stats["api_successes"] += 1
                data = response.json()

                # Verify title match for accuracy
                if self.titles_match(title, data.get("title", "")):
                    self.logger.debug(
                        f"Found citations for {arxiv_id}: {data.get('citationCount', 0)}"
                    )
                    return data
                else:
                    self.logger.debug(f"Title mismatch for {arxiv_id}")
                    return None

            elif response.status_code == 404:
                self.stats["api_successes"] += 1
                self.logger.debug(f"Paper not found in Semantic Scholar: {arxiv_id}")
                self.stats["papers_not_found"] += 1
                return None

            elif response.status_code in {401, 403}:
                self.stats["api_errors"] += 1
                self.stats["credential_failures"] += 1
                raise RuntimeError(
                    f"Semantic Scholar credential rejected ({response.status_code})"
                )

            else:
                self.logger.warning(
                    f"Semantic Scholar API error for {arxiv_id}: {response.status_code}"
                )
                self.stats["api_errors"] += 1
                raise RuntimeError(
                    f"Semantic Scholar API returned {response.status_code}"
                )

        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout fetching citation data for {arxiv_id}")
            self.stats["api_errors"] += 1
            raise
        except Exception as e:
            self.logger.error(f"Error fetching citation data for {arxiv_id}: {e}")
            self.stats["api_errors"] += 1
            raise

    def titles_match(self, title1: str, title2: str, threshold: float = 0.8) -> bool:
        """Check if two titles are similar enough using word-based similarity."""
        import re

        def normalize_title(title):
            # Convert to lowercase, remove punctuation, split into words
            return set(re.findall(r"\w+", title.lower()))

        words1 = normalize_title(title1)
        words2 = normalize_title(title2)

        if not words1 or not words2:
            return False

        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold

    def update_citations_batch(self, results: List[CitationResult]):
        """Update database with citation results in batch."""
        if not results:
            return

        citation_updates = [
            {
                "paper_id": result.paper_id,
                "citation_count": result.citation_count,
                "semantic_scholar_id": result.semantic_scholar_id,
                "success": result.success,
            }
            for result in results
        ]
        try:
            update_stats = self.paper_service.update_citation_counts_batch(
                citation_updates
            )
        except DatabaseError as error:
            # Rate-limit waits leave the session idle long enough for the
            # server to drop it. The service has already rolled back, so the
            # next attempt reconnects; the results are still in memory.
            self.logger.warning(
                "Citation batch write failed (%s); retrying once on a fresh connection",
                error,
            )
            update_stats = self.paper_service.update_citation_counts_batch(
                citation_updates
            )
        self.stats["citations_updated"] += update_stats["updated"]
        self.logger.debug(
            f"Updated {update_stats['updated']} papers with citations, "
            f"marked {update_stats['failed']} as processed"
        )

    def log_summary(self):
        """Log execution summary with performance metrics."""
        self.logger.info("Hourly citation count update completed:")
        self.logger.info(f"  - Papers found: {self.stats['papers_found']}")
        self.logger.info(f"  - Papers processed: {self.stats['papers_processed']}")
        self.logger.info(f"  - Citations updated: {self.stats['citations_updated']}")
        self.logger.info(f"  - Papers not found: {self.stats['papers_not_found']}")
        self.logger.info(f"  - API calls made: {self.stats['api_calls']}")
        self.logger.info(f"  - API errors: {self.stats['api_errors']}")
        self.logger.info(f"  - Rate limit hits: {self.stats['rate_limit_hits']}")
        self.logger.info(f"  - Processing errors: {self.stats['processing_errors']}")
        self.logger.info(f"CITATION_UPDATE_SUMMARY {json.dumps(self.stats)}")

        if self.stats["papers_processed"] > 0:
            success_rate = (
                self.stats["citations_updated"] / self.stats["papers_processed"]
            ) * 100
            self.logger.info(f"  - Success rate: {success_rate:.1f}%")

        # Performance projections
        if self.stats["api_calls"] > 0:
            # Calculate the observed end-to-end request rate.
            elapsed = float(self.stats.get("elapsed_seconds") or 0)
            actual_rate = self.stats["api_calls"] / elapsed if elapsed > 0 else 0
            hourly_projection = self.stats["papers_processed"]
            daily_projection = hourly_projection * 24

            self.logger.info(f"  - Actual API rate: {actual_rate:.2f} req/sec")
            self.logger.info(f"  - Hourly processing rate: {hourly_projection} papers")
            self.logger.info(f"  - Daily projection: {daily_projection:,} papers")

        # Get current citation statistics (brief version for hourly jobs)
        self.log_citation_statistics_brief()

    def log_citation_statistics_brief(self):
        """Log brief citation statistics for hourly jobs."""
        try:
            stats = self.paper_service.get_citation_statistics()

            self.logger.info(
                f"  - Overall progress: {stats['processed_percentage']:.1f}% "
                f"({stats['papers_processed']:,}/{stats['total_papers']:,})"
            )
            self.logger.info(
                f"  - Papers with citations: {stats['papers_with_citations']:,}"
            )

        except Exception as e:
            self.logger.error(f"Error getting citation statistics: {e}")

    def cleanup(self):
        """Clean up database connections."""
        try:
            if hasattr(self, "db_session") and self.db_session:
                self.db_session.close()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    job = CitationHourlyUpdateJob()
    try:
        success = job.execute()
    finally:
        job.cleanup()
    sys.exit(0 if success else 1)
