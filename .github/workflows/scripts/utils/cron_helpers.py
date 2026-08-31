#!/usr/bin/env python3
"""
Shared utilities and base classes for CRON jobs.

This module provides common functionality for all cron jobs including:
- Base class with logging setup
- Error handling and notifications
- Execution time tracking
- Database connection helpers
"""

import logging
import json
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
import os

from backend.config import get_settings

MAX_CRON_LOG_READ_BYTES = 2 * 1024 * 1024


def _read_log_tail(path: Path) -> list[str]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        offset = max(0, size - MAX_CRON_LOG_READ_BYTES)
        handle.seek(offset)
        raw = handle.read(MAX_CRON_LOG_READ_BYTES)
    if offset:
        raw = raw.partition(b"\n")[2]
    return raw.decode("utf-8", errors="replace").splitlines(keepends=True)


class CronJobBase(ABC):
    """
    Base class for all CRON jobs with common functionality.

    Provides:
    - Structured logging with rotation
    - Execution time tracking
    - Error handling and notifications
    - Database connection management
    """

    def __init__(self, job_name: str, log_level: str = "INFO"):
        """
        Initialize the cron job.

        Args:
            job_name: Unique name for this cron job
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.job_name = job_name
        self.log_level = log_level
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

        # Set up logging
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        """Set up logging for the cron job."""
        # Create logs directory if it doesn't exist
        logs_dir = Path(
            os.environ.get("PWC_CRON_LOG_DIR", Path(__file__).parent.parent / "logs")
        )
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Create log file with date
        today = datetime.now().strftime("%Y%m%d")
        log_file = logs_dir / f"{self.job_name}_{today}.log"

        # Set up logger
        logger = logging.getLogger(f"cron.{self.job_name}")
        logger.setLevel(getattr(logging, self.log_level.upper()))

        # Remove existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # File handler
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler for immediate feedback
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        return logger

    def get_database_connection(self):
        """Get a database connection using psycopg2 with timeouts."""
        try:
            settings = get_settings()
            return psycopg2.connect(
                host=settings.db_host,
                port=settings.db_port,
                database=settings.db_name,
                user=settings.db_user,
                password=settings.db_password,
                connect_timeout=10,  # 10 second connection timeout
                options="-c statement_timeout=30000",  # 30 second query timeout
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise

    def execute(self) -> bool:
        """
        Execute the cron job with proper error handling and logging.

        Returns:
            True if job completed successfully, False otherwise
        """
        self.start_time = datetime.now(timezone.utc)

        self.logger.info(f"Starting cron job: {self.job_name}")
        self.logger.info(
            "Release ID: %s", os.environ.get("PWC_RELEASE_ID", "development")
        )
        self.logger.info(f"Start time: {self.start_time.isoformat()}")

        try:
            # Run the main job logic
            self.run()

            self.end_time = datetime.now(timezone.utc)
            duration = (self.end_time - self.start_time).total_seconds()

            self.logger.info(f"Cron job completed successfully: {self.job_name}")
            self.logger.info(f"End time: {self.end_time.isoformat()}")
            self.logger.info(f"Duration: {duration:.2f} seconds")

            return True

        except Exception as e:
            self.end_time = datetime.now(timezone.utc)
            duration = (self.end_time - self.start_time).total_seconds()

            self.logger.error(f"Cron job failed: {self.job_name}")
            self.logger.error(f"Error: {str(e)}")
            self.logger.error(f"Traceback:\n{traceback.format_exc()}")
            self.logger.error(f"Duration before failure: {duration:.2f} seconds")

            # Optionally send notifications for critical failures
            self._handle_failure(e)

            return False

    def _handle_failure(self, error: Exception):
        """
        Handle job failure - can be overridden for custom notification logic.

        Args:
            error: The exception that caused the failure
        """
        # Base implementation - just log the error
        # Subclasses can override to send emails, Slack notifications, etc.
        pass

    @abstractmethod
    def run(self):
        """
        Main execution logic for the cron job.
        Must be implemented by subclasses.
        """
        pass


class DatabaseCronJob(CronJobBase):
    """
    Specialized base class for cron jobs that work with the database.

    Provides additional database-specific utilities and connection management.
    """

    def __init__(self, job_name: str, log_level: str = "INFO"):
        super().__init__(job_name, log_level)
        self.connection = None

    def execute(self) -> bool:
        """Execute with database connection management."""
        try:
            self.connection = self.get_database_connection()
            return super().execute()
        finally:
            if self.connection:
                self.connection.close()
                self.logger.debug("Database connection closed")

    def execute_query(self, query: str, params: tuple = None) -> list:
        """
        Execute a database query and return results.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            List of query results as dictionaries
        """
        if not self.connection:
            raise RuntimeError("No database connection available")

        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if cursor.description:  # SELECT query
                    return cursor.fetchall()
                else:  # INSERT/UPDATE/DELETE query
                    self.connection.commit()
                    return []
        except Exception as e:
            self.connection.rollback()
            self.logger.error(f"Database query failed: {e}")
            self.logger.error(f"Query: {query}")
            if params:
                self.logger.error(f"Parameters: {params}")
            raise

    def get_table_count(self, table_name: str) -> int:
        """Get the number of rows in a table."""
        result = self.execute_query(f"SELECT COUNT(*) as count FROM {table_name}")
        return result[0]["count"] if result else 0

    def vacuum_analyze_table(self, table_name: str):
        """Perform VACUUM ANALYZE on a table."""
        self.logger.info(f"Running VACUUM ANALYZE on {table_name}")
        # VACUUM cannot be run in a transaction, so we need a separate connection
        try:
            settings = get_settings()
            conn = psycopg2.connect(
                host=settings.db_host,
                port=settings.db_port,
                database=settings.db_name,
                user=settings.db_user,
                password=settings.db_password,
            )
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute(f"VACUUM ANALYZE {table_name}")
            conn.close()
            self.logger.info(f"VACUUM ANALYZE completed for {table_name}")
        except Exception as e:
            self.logger.error(f"VACUUM ANALYZE failed for {table_name}: {e}")
            # Don't raise the exception - this is optional maintenance


def get_cron_job_status(
    job_name: str,
    date: Optional[str] = None,
    *,
    logs_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Get the status of a cron job from its log file.

    Args:
        job_name: Name of the cron job
        date: Date in YYYYMMDD format (defaults to today)

    Returns:
        Dictionary with job status information
    """
    import subprocess
    import re

    if not date:
        date = datetime.now().strftime("%Y%m%d")

    logs_dir = logs_dir or Path(
        os.environ.get("PWC_CRON_LOG_DIR", Path(__file__).parent.parent / "logs")
    )
    log_file = logs_dir / f"{job_name}_{date}.log"

    status = {
        "job_name": job_name,
        "date": date,
        "log_file": str(log_file),
        "exists": log_file.exists(),
        "last_run": None,
        "status": "unknown",
        "duration": None,
        "error": None,
        "is_running": False,
        "work_metrics": {},  # Store work metrics (papers processed, repos updated, etc)
    }

    if not log_file.exists():
        return status

    # Check if job is currently running by looking for active processes
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )

        if result.returncode == 0:
            # Look for processes containing the job name or related patterns
            search_patterns = [
                job_name,
                job_name.replace("_", "-"),  # Handle name variations
                job_name.replace("_", ""),  # Handle concatenated names
            ]

            # Add specific mappings for known jobs
            if job_name == "github_stars_cron":
                search_patterns.extend(["update_github_stars", "github_stars"])
            elif job_name == "update_citations_hourly":
                search_patterns.extend(["update_citations", "citations"])

            for line in result.stdout.split("\n"):
                if "python" in line and "grep" not in line:
                    for pattern in search_patterns:
                        if pattern in line:
                            status["is_running"] = True
                            break
                    if status["is_running"]:
                        break
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass  # If ps command fails, continue with log analysis

    try:
        lines = _read_log_tail(log_file)

        # Parse log file for status information
        found_completion = False
        found_failure = False
        last_start_time = None
        last_start_index = None

        # Look for the most recent start and completion/failure messages
        for index, line in enumerate(lines):
            if "Starting" in line and (
                "cron job:" in line
                or "optimized" in line
                or "GitHub Stars Update" in line
                or "Trending Score" in line
                or "Score Calculation" in line
            ):
                # Extract timestamp from log line
                timestamp_match = re.match(
                    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line
                )
                if timestamp_match:
                    last_start_time = timestamp_match.group(1)
                    last_start_index = index

        # Slice at the run boundary instead of comparing timestamps line by line.
        # Tracebacks and wrapped log messages are often untimestamped; accepting all
        # such lines accidentally lets an old failure override a newer run.
        current_run_lines = (
            lines[last_start_index:] if last_start_index is not None else lines
        )

        # Check for completion/failure messages from the current run only
        for line in reversed(current_run_lines):  # Start from the end
            if (
                "completed successfully" in line
                or "Job completed successfully" in line
                or "Update Completed" in line
                or "Calculation Completed" in line
            ):
                status["status"] = "success"
                found_completion = True
                break
            elif "Job timed out" in line:
                status["status"] = "failed"
                status["error"] = line.strip()
                found_failure = True
                break
            elif "failed" in line.lower() and (
                "job failed" in line.lower()
                or "cron job failed" in line.lower()
                or "extraction failed" in line.lower()
                or "url extraction failed" in line.lower()
                or "critical error" in line.lower()
                or "invalid api key" in line.lower()
                or "api key" in line.lower()
                and "invalid" in line.lower()
            ):
                status["status"] = "failed"
                found_failure = True
                # Try to extract error message
                if "Error:" in line:
                    status["error"] = line.split("Error:")[-1].strip()
                elif "FAILED:" in line:
                    status["error"] = line.split("FAILED:")[-1].strip()
                elif "failed:" in line.lower():
                    status["error"] = line.split(":")[-1].strip()
                break

        current_run_incomplete = (
            last_start_time is not None and not found_completion and not found_failure
        )

        # If we found a recent start but no completion/failure, and process is running, it's running
        if current_run_incomplete and status["is_running"]:
            status["status"] = "running"
            status["last_run"] = last_start_time
        elif not found_completion and not found_failure and status["is_running"]:
            status["status"] = "running"

        # Only clear running state when the current run finished
        if found_completion or found_failure:
            status["is_running"] = False

        # Extract timing information
        start_time = None
        end_time = None
        completion_time = None

        for line in current_run_lines:
            if "Start time:" in line:
                start_time = line.split("Start time:")[-1].strip()
            elif "End time:" in line:
                end_time = line.split("End time:")[-1].strip()
            elif "Duration:" in line:
                duration_str = line.split("Duration:")[-1].strip()
                try:
                    status["duration"] = float(duration_str.split()[0])
                except (ValueError, IndexError):
                    pass
            elif "Runtime:" in line:
                # Handle "Runtime: X minutes" or "Runtime: X seconds" format
                runtime_str = line.split("Runtime:")[-1].strip()
                try:
                    parts = runtime_str.split()
                    if len(parts) >= 2:
                        value = float(parts[0])
                        unit = parts[1].lower()
                        if "minute" in unit:
                            status["duration"] = value * 60
                        elif "second" in unit:
                            status["duration"] = value
                        elif "hour" in unit:
                            status["duration"] = value * 3600
                except (ValueError, IndexError):
                    pass

        # For jobs that completed, extract the completion timestamp
        if found_completion:
            for line in reversed(current_run_lines):
                if (
                    "Update Completed" in line
                    or "Calculation Completed" in line
                    or "completed successfully" in line
                ):
                    timestamp_match = re.match(
                        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line
                    )
                    if timestamp_match:
                        completion_time = timestamp_match.group(1)
                        break

        if current_run_incomplete and status["is_running"] and last_start_time:
            status["last_run"] = last_start_time
        elif not status["last_run"]:
            if completion_time:
                status["last_run"] = completion_time
            elif end_time:
                status["last_run"] = end_time
            elif start_time:
                status["last_run"] = start_time
            elif last_start_time:
                status["last_run"] = last_start_time

        # Extract work metrics from logs (papers processed, repos updated, etc)
        work_metrics = {}
        for line in current_run_lines:
            if "PAPER_MARKDOWN_SUMMARY " in line:
                payload = line.split("PAPER_MARKDOWN_SUMMARY ", 1)[1]
                try:
                    work_metrics.update(json.loads(payload))
                except json.JSONDecodeError:
                    pass
            elif "HOT_GITHUB_TRENDING_SUMMARY " in line:
                payload = line.split("HOT_GITHUB_TRENDING_SUMMARY ", 1)[1]
                try:
                    work_metrics.update(json.loads(payload))
                except json.JSONDecodeError:
                    pass
            elif "GITHUB_STARS_SUMMARY " in line:
                payload = line.split("GITHUB_STARS_SUMMARY ", 1)[1]
                try:
                    work_metrics.update(json.loads(payload))
                except json.JSONDecodeError:
                    pass
            elif any(
                marker in line
                for marker in (
                    "HF_DAILY_PAPERS_SUMMARY ",
                    "HF_DAILY_CURATION_SUMMARY ",
                    "HF_ARTIFACTS_SUMMARY ",
                    "PAPER_EMBEDDINGS_SUMMARY ",
                    "THUMBNAIL_PRELOAD_SUMMARY ",
                    "THUMBNAIL_MIRROR_SUMMARY ",
                    "CURATION_THUMBNAILS_SUMMARY ",
                    "CITATION_UPDATE_SUMMARY ",
                    "TRENDING_SCORES_SUMMARY ",
                    "PAPER_TRENDING_SUMMARY ",
                    "ORGANIZATION_SYNC_SUMMARY ",
                    "ORGANIZATION_TRENDING_SUMMARY ",
                )
            ):
                marker = next(
                    item
                    for item in (
                        "HF_DAILY_PAPERS_SUMMARY ",
                        "HF_DAILY_CURATION_SUMMARY ",
                        "HF_ARTIFACTS_SUMMARY ",
                        "PAPER_EMBEDDINGS_SUMMARY ",
                        "THUMBNAIL_PRELOAD_SUMMARY ",
                        "THUMBNAIL_MIRROR_SUMMARY ",
                        "CURATION_THUMBNAILS_SUMMARY ",
                        "CITATION_UPDATE_SUMMARY ",
                        "TRENDING_SCORES_SUMMARY ",
                        "PAPER_TRENDING_SUMMARY ",
                        "ORGANIZATION_SYNC_SUMMARY ",
                        "ORGANIZATION_TRENDING_SUMMARY ",
                    )
                    if item in line
                )
                try:
                    work_metrics.update(json.loads(line.split(marker, 1)[1]))
                except json.JSONDecodeError:
                    pass
            # Papers processed
            elif re.search(r"Papers processed:\s*(\d+)", line):
                match = re.search(r"Papers processed:\s*(\d+)", line)
                work_metrics["papers_processed"] = int(match.group(1))
            # Named paper groups, for composite jobs such as
            # ``Papers processed: language=60 tts=14``.
            elif "Papers processed:" in line:
                payload = line.split("Papers processed:", 1)[1]
                named_counts = re.findall(
                    r"\b([a-z][a-z0-9_-]*)=(\d+)\b", payload, re.IGNORECASE
                )
                if named_counts:
                    work_metrics["papers_processed"] = sum(
                        int(value) for _name, value in named_counts
                    )
                    for name, value in named_counts:
                        work_metrics[f"{name.lower()}_processed"] = int(value)
            # Repositories processed (with or without "Total")
            elif re.search(
                r"(?:Total\s+)?repositories processed:\s*(\d+)", line, re.IGNORECASE
            ):
                match = re.search(
                    r"(?:Total\s+)?repositories processed:\s*(\d+)", line, re.IGNORECASE
                )
                work_metrics["repositories_processed"] = int(match.group(1))
            # Repository URLs updated
            elif re.search(r"Repository URLs updated:\s*(\d+)", line):
                match = re.search(r"Repository URLs updated:\s*(\d+)", line)
                work_metrics["repository_urls_updated"] = int(match.group(1))
            # Papers found
            elif re.search(r"Found (\d+) papers", line):
                match = re.search(r"Found (\d+) papers", line)
                work_metrics["papers_found"] = int(match.group(1))
            # Trending scores updated (captures both "Repos updated" and "Trending scores updated")
            elif re.search(
                r"(?:Repos updated|Trending scores updated):\s*(\d+)",
                line,
                re.IGNORECASE,
            ):
                match = re.search(
                    r"(?:Repos updated|Trending scores updated):\s*(\d+)",
                    line,
                    re.IGNORECASE,
                )
                work_metrics["repos_updated"] = int(match.group(1))

        # Only set zero values if we didn't already find explicit counts
        for line in lines:
            # No papers/repos to process messages - only apply if not already set
            if (
                "No papers need citation updates" in line
                and "papers_processed" not in work_metrics
            ):
                work_metrics["papers_processed"] = 0
                work_metrics["reason"] = "no_papers_to_update"
            elif (
                "No more repositories to process" in line
                and "repositories_processed" not in work_metrics
            ):
                work_metrics["repositories_processed"] = 0
                work_metrics["reason"] = "no_repos_to_update"
            elif (
                "No papers found that need processing" in line
                and "papers_processed" not in work_metrics
            ):
                work_metrics["papers_processed"] = 0
                work_metrics["reason"] = "no_papers_found"

        status["work_metrics"] = work_metrics

        # Detect "fake success" - job completed but did no work
        if found_completion and not found_failure:
            # Check if this was a success but no work was done
            total_work = (
                work_metrics.get("papers_processed", 0)
                + work_metrics.get("repositories_processed", 0)
                + work_metrics.get("repository_urls_updated", 0)
                + work_metrics.get("repos_updated", 0)
            )

            # Special check for extract_urls: if papers were found but all skipped due to critical errors
            papers_found = work_metrics.get("papers_found", 0)
            papers_processed = work_metrics.get("papers_processed", 0)
            papers_skipped_critical = None

            # Try to extract papers_skipped_critical_errors from log
            for line in lines:
                if "Papers skipped (critical errors):" in line:
                    import re

                    match = re.search(
                        r"Papers skipped \(critical errors\):\s*(\d+)", line
                    )
                    if match:
                        papers_skipped_critical = int(match.group(1))
                        break

            # If we found papers but processed none due to critical errors, mark as failed
            if (
                papers_found > 0
                and papers_processed == 0
                and papers_skipped_critical is not None
                and papers_skipped_critical > 0
            ):
                status["status"] = "failed"
                status["error"] = (
                    f"Found {papers_found} papers but processed 0 due to "
                    f"{papers_skipped_critical} critical errors (likely invalid API keys)"
                )
                found_failure = True
            elif total_work == 0:
                status["status"] = "success_no_work"
                status["work_summary"] = (
                    "Completed successfully but no items to process"
                )
            else:
                status["work_summary"] = f"Processed {total_work} items"

    except Exception as e:
        status["error"] = f"Failed to parse log file: {e}"

    return status


def cleanup_old_logs(days_to_keep: int = 30):
    """
    Clean up old log files from the cron logs directory.

    Args:
        days_to_keep: Number of days of logs to keep
    """
    logs_dir = Path(__file__).parent.parent / "logs"
    if not logs_dir.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=days_to_keep)

    for log_file in logs_dir.glob("*.log"):
        try:
            # Extract date from filename (assuming format: jobname_YYYYMMDD.log)
            parts = log_file.stem.split("_")
            if len(parts) >= 2:
                date_str = parts[-1]
                if len(date_str) == 8 and date_str.isdigit():
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    if file_date < cutoff_date:
                        log_file.unlink()
                        print(f"Deleted old log file: {log_file}")
        except (ValueError, OSError) as e:
            print(f"Error processing log file {log_file}: {e}")
