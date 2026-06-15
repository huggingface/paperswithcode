#!/usr/bin/env python3
"""
CRON Job Management Script

Utility script to manage and monitor cron jobs for the PapersWithCode project.

Usage:
    uv run .github/workflows/scripts/manage_cron.py status [job_name] [date]
    uv run .github/workflows/scripts/manage_cron.py list
    uv run .github/workflows/scripts/manage_cron.py test <job_name>
    uv run .github/workflows/scripts/manage_cron.py cleanup
"""

import argparse
import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import sys

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(WORKFLOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOWS_DIR))

from scripts.utils.cron_helpers import get_cron_job_status, cleanup_old_logs  # noqa: E402


def list_cron_jobs():
    """List all available cron jobs."""
    cron_dir = Path(__file__).parent

    print("Available CRON Jobs:")
    print("=" * 50)

    categories = ["hourly", "daily", "weekly", "monthly"]

    for category in categories:
        category_dir = cron_dir / category
        if category_dir.exists():
            print(f"\n{category.upper()} Jobs:")
            print("-" * 20)

            for script in category_dir.glob("*.py"):
                if script.name != "__init__.py":
                    job_name = script.stem
                    print(f"  - {job_name}")

                    # Try to get description from docstring
                    try:
                        with open(script, "r") as f:
                            lines = f.readlines()

                        # Look for description in docstring
                        in_docstring = False
                        description = ""

                        for line in lines:
                            if '"""' in line and not in_docstring:
                                in_docstring = True
                                # Check if description is on the same line
                                after_quotes = line.split('"""', 1)[1]
                                if after_quotes.strip():
                                    description = after_quotes.strip()
                                    break
                            elif in_docstring and '"""' in line:
                                break
                            elif in_docstring and line.strip():
                                description = line.strip()
                                break

                        if description:
                            print(f"    {description}")

                    except Exception:
                        pass


def show_job_status(job_name: str = None, date: str = None):
    """Show status of cron jobs."""
    if job_name:
        # Show status for specific job
        status = get_cron_job_status(job_name, date)
        print(f"Status for {job_name}:")
        print("=" * 50)
        print(f"Date: {status['date']}")
        print(f"Log file: {status['log_file']}")
        print(f"Exists: {status['exists']}")

        if status["exists"]:
            print(f"Status: {status['status']}")
            if status.get("is_running"):
                print("🔄 Currently running")
            print(f"Last run: {status['last_run']}")
            if status["duration"]:
                print(f"Duration: {status['duration']:.2f} seconds")
            if status["error"]:
                print(f"Error: {status['error']}")
        else:
            print("No log file found for this job/date")

    else:
        # Show status for all jobs
        cron_dir = Path(__file__).parent
        today = datetime.now().strftime("%Y%m%d")

        print(f"CRON Job Status Summary - {today}")
        print("=" * 60)

        categories = ["hourly", "daily", "weekly", "monthly"]

        for category in categories:
            category_dir = cron_dir / category
            if category_dir.exists():
                print(f"\n{category.upper()} Jobs:")
                print("-" * 30)

                for script in category_dir.glob("*.py"):
                    if script.name != "__init__.py":
                        job_name = script.stem

                        # Map script names to actual log file names
                        log_name_mapping = {
                            "update_github_stars": "github_stars_cron",
                            "update_citations": "update_citations_hourly",
                            "extract_urls": "extract_urls_hourly",
                            "calculate_trending_scores": "calculate_trending_scores",
                            "update_hf_artifacts": "update_hf_artifacts",
                            "calculate_paper_trending_scores": "calculate_paper_trending_scores",
                            "link_methods_by_references": "link_methods_by_references_weekly",
                            "link_papers_by_task_keywords": "link_papers_by_task_keywords_weekly",
                        }
                        log_name = log_name_mapping.get(job_name, job_name)

                        # Skip wrapper jobs to avoid duplicates
                        if "wrapper" in log_name:
                            continue

                        status = get_cron_job_status(log_name, today)

                        status_icon = (
                            "✓"
                            if status["status"] == "success"
                            else "🔄"
                            if status["status"] == "running"
                            else "✗"
                            if status["status"] == "failed"
                            else "?"
                        )
                        print(
                            f"  {status_icon} {job_name:<25} {status['status']:<10} {status['last_run'] or 'Never'}"
                        )


def test_job(job_name: str):
    """Test run a specific cron job."""
    cron_dir = Path(__file__).parent

    # Find the job script
    job_script = None
    categories = ["hourly", "daily", "weekly", "monthly"]

    for category in categories:
        script_path = cron_dir / category / f"{job_name}.py"
        if script_path.exists():
            job_script = script_path
            break

    if not job_script:
        print(f"Error: Job '{job_name}' not found")
        return False

    print(f"Testing cron job: {job_name}")
    print(f"Script: {job_script}")
    print("=" * 50)

    # Run the job script
    import subprocess
    import sys

    try:
        category = job_script.parent.name
        module_name = f"scripts.{category}.{job_script.stem}"
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            f"{WORKFLOWS_DIR}:{env['PYTHONPATH']}"
            if env.get("PYTHONPATH")
            else str(WORKFLOWS_DIR)
        )
        result = subprocess.run(
            [sys.executable, "-m", module_name],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        print("STDOUT:")
        print(result.stdout)

        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)

        print(f"\nExit code: {result.returncode}")

        return result.returncode == 0

    except Exception as e:
        print(f"Error running job: {e}")
        return False


def cleanup_logs():
    """Clean up old log files."""
    print("Cleaning up old log files...")

    try:
        cleanup_old_logs(days_to_keep=30)
        print("Log cleanup completed successfully")
    except Exception as e:
        print(f"Error during log cleanup: {e}")


class CronStatusAnalyzer:
    """Analyzes cron job status and performance."""

    def __init__(self):
        self.cron_dir = Path(__file__).parent
        self.logs_dir = self.cron_dir / "logs"
        self.today = datetime.now().strftime("%Y%m%d")

    def get_available_jobs(self) -> Dict[str, List[str]]:
        """Get all available cron jobs organized by category."""
        jobs = defaultdict(list)

        categories = ["hourly", "daily", "weekly", "monthly"]
        for category in categories:
            category_dir = self.cron_dir / category
            if category_dir.exists():
                for script in category_dir.glob("*.py"):
                    if script.name != "__init__.py":
                        jobs[category].append(script.stem)

        return dict(jobs)

    def get_active_cron_jobs(self) -> List[str]:
        """Get currently scheduled cron jobs from crontab."""
        try:
            result = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True, check=False
            )

            if result.returncode != 0:
                return []

            active_jobs = []
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    # Extract job name from cron line
                    if "scripts/" in line or "cron/" in line:
                        # Look for script paths in current or legacy crontab entries.
                        match = re.search(
                            r"(?:scripts|cron)/(?:daily/|hourly/|weekly/|monthly/)?([^/\s]+)(?:\.py|\.sh)",
                            line,
                        )
                        if match:
                            job_name = match.group(1)
                            active_jobs.append(job_name)

            return active_jobs

        except Exception as e:
            print(f"Error getting crontab: {e}")
            return []

    def parse_log_file(self, log_file: Path) -> Dict[str, Any]:
        """Parse a log file and extract detailed statistics."""
        stats = {
            "file": str(log_file),
            "exists": log_file.exists(),
            "size_mb": 0,
            "runs": [],
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "avg_duration": 0,
            "memory_usage": [],
            "performance_metrics": {},
            "errors": [],
            "warnings": [],
        }

        if not log_file.exists():
            return stats

        try:
            stats["size_mb"] = log_file.stat().st_size / (1024 * 1024)

            with open(log_file, "r") as f:
                content = f.read()
                lines = content.split("\n")

            current_run = None
            durations = []

            for line in lines:
                if not line.strip():
                    continue

                # Extract timestamp
                timestamp_match = re.match(
                    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line
                )
                if timestamp_match:
                    timestamp = timestamp_match.group(1)
                else:
                    continue

                # Track job runs
                if "Starting cron job:" in line or "Starting optimized" in line:
                    current_run = {
                        "start_time": timestamp,
                        "status": "running",
                        "duration": None,
                        "memory_peak": None,
                        "processed_items": 0,
                    }

                elif (
                    "completed successfully" in line
                    or "Job completed successfully" in line
                ):
                    if current_run:
                        current_run["status"] = "success"
                        stats["runs"].append(current_run)
                        stats["successful_runs"] += 1
                        current_run = None

                elif "failed" in line.lower() and "error" in line.lower():
                    if current_run:
                        current_run["status"] = "failed"
                        stats["runs"].append(current_run)
                        stats["failed_runs"] += 1
                        current_run = None

                    # Extract error details
                    if len(stats["errors"]) < 5:  # Keep last 5 errors
                        stats["errors"].append(
                            {
                                "timestamp": timestamp,
                                "message": line.split(" - ")[-1]
                                if " - " in line
                                else line,
                            }
                        )

                # Extract duration
                duration_match = re.search(r"Duration: ([\d.]+) seconds", line)
                if duration_match:
                    duration = float(duration_match.group(1))
                    durations.append(duration)
                    if current_run:
                        current_run["duration"] = duration

                # Extract memory usage (for optimized scripts)
                memory_match = re.search(r"(\d+)MB memory available", line)
                if memory_match:
                    memory_mb = int(memory_match.group(1))
                    stats["memory_usage"].append(memory_mb)
                    if current_run:
                        current_run["memory_peak"] = memory_mb

                # Extract processing metrics
                progress_match = re.search(
                    r"Progress: (\d+) (?:unique repos|papers)", line
                )
                if progress_match and current_run:
                    current_run["processed_items"] = int(progress_match.group(1))

                # Extract URL extraction specific metrics
                if "📄 Papers Processed:" in line:
                    papers_match = re.search(r"📄 Papers Processed: (\d+)", line)
                    if papers_match and current_run:
                        current_run["processed_items"] = int(papers_match.group(1))

                # Extract GitHub URLs found
                if "🔗 Papers with GitHub:" in line:
                    github_match = re.search(r"🔗 Papers with GitHub: (\d+)", line)
                    if github_match and current_run:
                        current_run["github_urls_found"] = int(github_match.group(1))

                # Extract project pages found
                if "🌐 Papers with Project Page:" in line:
                    project_match = re.search(
                        r"🌐 Papers with Project Page: (\d+)", line
                    )
                    if project_match and current_run:
                        current_run["project_pages_found"] = int(project_match.group(1))

                # Extract processing rate
                if "⚡ Processing Rate:" in line:
                    rate_match = re.search(
                        r"⚡ Processing Rate: ([\d.]+) papers/second", line
                    )
                    if rate_match and current_run:
                        current_run["processing_rate"] = float(rate_match.group(1))

                # Extract daily capacity estimate
                if "📈 Estimated Daily Capacity:" in line:
                    capacity_match = re.search(
                        r"📈 Estimated Daily Capacity: (\d+) papers", line
                    )
                    if capacity_match and current_run:
                        current_run["daily_capacity"] = int(capacity_match.group(1))

                # Track warnings
                if "WARNING" in line and len(stats["warnings"]) < 3:
                    stats["warnings"].append(
                        {
                            "timestamp": timestamp,
                            "message": line.split(" - ")[-1] if " - " in line else line,
                        }
                    )

            # Calculate statistics
            stats["total_runs"] = len(stats["runs"])
            if durations:
                stats["avg_duration"] = sum(durations) / len(durations)

            # Performance metrics
            if stats["memory_usage"]:
                stats["performance_metrics"]["avg_memory_mb"] = sum(
                    stats["memory_usage"]
                ) / len(stats["memory_usage"])
                stats["performance_metrics"]["peak_memory_mb"] = max(
                    stats["memory_usage"]
                )
                stats["performance_metrics"]["min_memory_mb"] = min(
                    stats["memory_usage"]
                )

            successful_runs = [r for r in stats["runs"] if r["status"] == "success"]
            if successful_runs:
                processed_items = [
                    r["processed_items"]
                    for r in successful_runs
                    if r["processed_items"] > 0
                ]
                if processed_items:
                    stats["performance_metrics"]["avg_items_processed"] = sum(
                        processed_items
                    ) / len(processed_items)
                    stats["performance_metrics"]["total_items_processed"] = sum(
                        processed_items
                    )

                # URL extraction specific metrics
                github_urls = [
                    r["github_urls_found"]
                    for r in successful_runs
                    if r.get("github_urls_found", 0) > 0
                ]
                if github_urls:
                    stats["performance_metrics"]["avg_github_urls_found"] = sum(
                        github_urls
                    ) / len(github_urls)

                project_pages = [
                    r["project_pages_found"]
                    for r in successful_runs
                    if r.get("project_pages_found", 0) > 0
                ]
                if project_pages:
                    stats["performance_metrics"]["avg_project_pages_found"] = sum(
                        project_pages
                    ) / len(project_pages)

                processing_rates = [
                    r["processing_rate"]
                    for r in successful_runs
                    if r.get("processing_rate", 0) > 0
                ]
                if processing_rates:
                    stats["performance_metrics"]["avg_processing_rate"] = sum(
                        processing_rates
                    ) / len(processing_rates)

                daily_capacities = [
                    r["daily_capacity"]
                    for r in successful_runs
                    if r.get("daily_capacity", 0) > 0
                ]
                if daily_capacities:
                    stats["performance_metrics"]["avg_daily_capacity"] = sum(
                        daily_capacities
                    ) / len(daily_capacities)

        except Exception as e:
            stats["errors"].append(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "message": f"Error parsing log file: {e}",
                }
            )

        return stats

    def get_recent_logs(self, days: int = 3) -> Dict[str, Dict]:
        """Get logs from the last N days."""
        recent_logs = {}

        if not self.logs_dir.exists():
            return recent_logs

        # Get date range
        dates = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            dates.append(date)

        # Find all log files for recent dates
        for log_file in self.logs_dir.glob("*.log"):
            # Skip wrapper jobs to avoid duplicates
            if "wrapper" in log_file.name:
                continue

            # Extract job name and date from filename
            parts = log_file.stem.split("_")
            if len(parts) >= 2:
                date_str = parts[-1]
                if date_str in dates:
                    job_name = "_".join(parts[:-1])
                    if job_name not in recent_logs:
                        recent_logs[job_name] = {}
                    recent_logs[job_name][date_str] = self.parse_log_file(log_file)

        return recent_logs

    def generate_summary(self, detailed: bool = False) -> Dict[str, Any]:
        """Generate comprehensive cron job summary."""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "system_info": {
                "available_jobs": self.get_available_jobs(),
                "active_cron_jobs": self.get_active_cron_jobs(),
            },
            "job_status": {},
            "performance_summary": {},
            "alerts": [],
        }

        # Get recent logs
        recent_logs = self.get_recent_logs(3)

        # Analyze each job
        for job_name, date_logs in recent_logs.items():
            today_log = date_logs.get(self.today, {})

            # Get basic status
            status = get_cron_job_status(job_name, self.today)

            job_summary = {
                "basic_status": status,
                "recent_performance": {},
                "health_score": 100,
            }

            if detailed:
                job_summary["detailed_logs"] = date_logs

            # Calculate performance metrics across recent days
            total_runs = sum(log.get("total_runs", 0) for log in date_logs.values())
            successful_runs = sum(
                log.get("successful_runs", 0) for log in date_logs.values()
            )
            failed_runs = sum(log.get("failed_runs", 0) for log in date_logs.values())

            if total_runs > 0:
                success_rate = (successful_runs / total_runs) * 100
                job_summary["recent_performance"] = {
                    "total_runs": total_runs,
                    "success_rate": success_rate,
                    "failed_runs": failed_runs,
                }

                # Calculate health score
                if success_rate < 50:
                    job_summary["health_score"] = 0
                elif success_rate < 80:
                    job_summary["health_score"] = 50
                elif success_rate < 95:
                    job_summary["health_score"] = 75

                # Add alerts for problematic jobs
                if success_rate < 80:
                    summary["alerts"].append(
                        {
                            "level": "error" if success_rate < 50 else "warning",
                            "job": job_name,
                            "message": f"Low success rate: {success_rate:.1f}% ({failed_runs} failures in recent runs)",
                        }
                    )

            # Check for recent errors
            recent_errors = []
            for date_log in date_logs.values():
                recent_errors.extend(date_log.get("errors", []))

            if recent_errors and len(recent_errors) > 2:
                summary["alerts"].append(
                    {
                        "level": "warning",
                        "job": job_name,
                        "message": f"Multiple recent errors ({len(recent_errors)} errors found)",
                    }
                )

            # Performance analysis for today
            if today_log.get("performance_metrics"):
                metrics = today_log["performance_metrics"]
                job_summary["today_performance"] = metrics

                # Check memory usage
                if metrics.get("avg_memory_mb", 0) < 500:
                    summary["alerts"].append(
                        {
                            "level": "warning",
                            "job": job_name,
                            "message": f"Low memory usage detected: {metrics.get('avg_memory_mb', 0):.0f}MB average",
                        }
                    )

            summary["job_status"][job_name] = job_summary

        # Check for missing jobs
        available_jobs = summary["system_info"]["available_jobs"]
        active_jobs = summary["system_info"]["active_cron_jobs"]

        all_available = []
        for category_jobs in available_jobs.values():
            all_available.extend(category_jobs)

        missing_jobs = set(all_available) - set(active_jobs)
        if missing_jobs:
            summary["alerts"].append(
                {
                    "level": "info",
                    "job": "system",
                    "message": f"Jobs not scheduled in crontab: {', '.join(missing_jobs)}",
                }
            )

        # Generate performance summary
        all_jobs = list(summary["job_status"].keys())
        if all_jobs:
            health_scores = [
                job["health_score"] for job in summary["job_status"].values()
            ]
            summary["performance_summary"] = {
                "total_jobs_monitored": len(all_jobs),
                "average_health_score": sum(health_scores) / len(health_scores),
                "healthy_jobs": len([s for s in health_scores if s >= 80]),
                "problematic_jobs": len([s for s in health_scores if s < 80]),
                "critical_jobs": len([s for s in health_scores if s < 50]),
            }

        return summary

    def print_summary(self, summary: Dict[str, Any], detailed: bool = False):
        """Print formatted summary to console."""
        print("=" * 80)
        print("🔄 PAPERSWITHCODE CRON JOBS STATUS SUMMARY")
        print("=" * 80)
        print(f"📅 Generated: {summary['timestamp']}")
        print()

        # System Overview
        print("📊 SYSTEM OVERVIEW")
        print("-" * 40)
        available = summary["system_info"]["available_jobs"]
        active = summary["system_info"]["active_cron_jobs"]

        for category, jobs in available.items():
            print(f"  {category.upper()}: {len(jobs)} jobs available")
            if detailed:
                for job in jobs:
                    status = "🟢 Active" if job in active else "⚪ Inactive"
                    print(f"    - {job} {status}")

        print(
            f"\n  📋 Total Available: {sum(len(jobs) for jobs in available.values())}"
        )
        print(f"  ⚡ Currently Active: {len(active)}")
        print()

        # Performance Summary
        if summary["performance_summary"]:
            perf = summary["performance_summary"]
            print("📈 PERFORMANCE SUMMARY")
            print("-" * 40)
            print(f"  🎯 Jobs Monitored: {perf['total_jobs_monitored']}")
            print(f"  💚 Healthy Jobs: {perf['healthy_jobs']}")
            print(f"  ⚠️  Problematic Jobs: {perf['problematic_jobs']}")
            print(f"  🔴 Critical Jobs: {perf['critical_jobs']}")
            print(f"  📊 Average Health Score: {perf['average_health_score']:.1f}/100")
            print()

        # Alerts
        if summary["alerts"]:
            print("🚨 ALERTS & ISSUES")
            print("-" * 40)
            for alert in summary["alerts"]:
                icon = {"error": "🔴", "warning": "⚠️", "info": "ℹ️"}.get(
                    alert["level"], "📝"
                )
                print(f"  {icon} [{alert['job'].upper()}] {alert['message']}")
            print()

        # Job Status Details with Enhanced Formatting
        print("📋 JOB STATUS DETAILS")
        print("-" * 40)

        # Group jobs by category for better organization
        job_categories = {"hourly": [], "daily": [], "weekly": [], "monthly": []}

        # Track processed jobs to avoid duplicates
        processed_jobs = set()

        for job_name, job_data in summary["job_status"].items():
            # Skip if we've already processed this job
            if job_name in processed_jobs:
                continue
            processed_jobs.add(job_name)

            # Determine category based on job name patterns
            if (
                "hourly" in job_name
                or "github_stars" in job_name
                or "citations" in job_name
                or "extract_urls" in job_name
            ):
                job_categories["hourly"].append((job_name, job_data))
            elif "daily" in job_name or "import_hf" in job_name:
                job_categories["daily"].append((job_name, job_data))
            elif "weekly" in job_name:
                job_categories["weekly"].append((job_name, job_data))
            elif "monthly" in job_name:
                job_categories["monthly"].append((job_name, job_data))
            else:
                # Default to hourly for unknown jobs
                job_categories["hourly"].append((job_name, job_data))

        for category, jobs in job_categories.items():
            if not jobs:
                continue

            print(f"\n🕐 {category.upper()} JOBS")
            print("=" * 50)

            for job_name, job_data in jobs:
                status = job_data["basic_status"]
                health = job_data["health_score"]

                # Status icon
                if status["status"] == "success":
                    status_icon = "✅"
                elif status["status"] == "running":
                    status_icon = "🔄"
                elif status["status"] == "failed":
                    status_icon = "❌"
                else:
                    status_icon = "❓"

                # Health icon
                if health >= 80:
                    health_icon = "💚"
                elif health >= 50:
                    health_icon = "⚠️"
                else:
                    health_icon = "🔴"

                # Job name formatting
                display_name = job_name.replace("_", " ").title()
                if "github" in job_name.lower():
                    display_name = "GitHub Stars Update"
                elif "citations" in job_name.lower():
                    display_name = "Citations Update"
                elif "extract_urls" in job_name.lower():
                    display_name = "URL Extraction"
                elif "import_hf" in job_name.lower():
                    display_name = "Hugging Face Papers Import"

                print(f"\n  {status_icon} {display_name}")
                print(
                    f"    Status: {status['status'].upper()} | Health: {health}/100 {health_icon}"
                )

                if status["status"] == "running":
                    print("    🔄 Currently executing...")

                if status["last_run"]:
                    print(f"    Last Run: {status['last_run']}")

                if status["duration"]:
                    print(f"    Duration: {status['duration']:.2f}s")

                # Enhanced performance metrics
                if "recent_performance" in job_data and job_data["recent_performance"]:
                    perf = job_data["recent_performance"]
                    print(
                        f"    Recent: {perf['total_runs']} runs, {perf['success_rate']:.1f}% success"
                    )

                # Today's performance metrics with better formatting
                if "today_performance" in job_data:
                    today_perf = job_data["today_performance"]
                    if "avg_items_processed" in today_perf:
                        items = today_perf["avg_items_processed"]
                        if "github" in job_name.lower():
                            print(f"    📊 Repositories: {items:.0f} processed/run avg")
                        elif "citations" in job_name.lower():
                            print(f"    📊 Papers: {items:.0f} processed/run avg")
                        elif "extract_urls" in job_name.lower():
                            print(f"    📊 Papers: {items:.0f} processed/run avg")
                        else:
                            print(f"    📊 Items: {items:.0f} processed/run avg")

                    if "avg_memory_mb" in today_perf:
                        avg_mem = today_perf["avg_memory_mb"]
                        peak_mem = today_perf.get("peak_memory_mb", avg_mem)
                        print(
                            f"    💾 Memory: {avg_mem:.0f}MB avg, {peak_mem:.0f}MB peak"
                        )

                # Special formatting for specific job types
                if "extract_urls" in job_name.lower():
                    # Add URL extraction specific metrics if available
                    if "today_performance" in job_data:
                        perf = job_data["today_performance"]
                        if "total_items_processed" in perf:
                            total = perf["total_items_processed"]
                            print(f"    🔗 URLs Found: {total:.0f} total processed")
                        if "avg_github_urls_found" in perf:
                            github = perf["avg_github_urls_found"]
                            print(f"    📂 GitHub URLs: {github:.0f} found/run avg")
                        if "avg_project_pages_found" in perf:
                            pages = perf["avg_project_pages_found"]
                            print(f"    🌐 Project Pages: {pages:.0f} found/run avg")
                        if "avg_processing_rate" in perf:
                            rate = perf["avg_processing_rate"]
                            print(f"    ⚡ Rate: {rate:.2f} papers/second")
                        if "avg_daily_capacity" in perf:
                            capacity = perf["avg_daily_capacity"]
                            print(f"    📈 Daily Capacity: {capacity:.0f} papers")

                if status["error"]:
                    print(f"    ❌ Error: {status['error']}")

        print("\n" + "=" * 80)
        print("💡 TIP: Use '--detailed' flag for more comprehensive analysis")
        print("=" * 80)


def run_summary(detailed: bool = False, json_output: bool = False, days: int = 3):
    """Run the comprehensive cron job summary."""
    try:
        analyzer = CronStatusAnalyzer()
        summary = analyzer.generate_summary(detailed=detailed)

        if json_output:
            print(json.dumps(summary, indent=2, default=str))
        else:
            analyzer.print_summary(summary, detailed=detailed)

    except Exception as e:
        print(f"❌ Error generating cron status summary: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Manage CRON jobs for PapersWithCode")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    subparsers.add_parser("list", help="List all available cron jobs")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show cron job status")
    status_parser.add_argument("job_name", nargs="?", help="Specific job name to check")
    status_parser.add_argument("date", nargs="?", help="Date in YYYYMMDD format")

    # Test command
    test_parser = subparsers.add_parser("test", help="Test run a cron job")
    test_parser.add_argument("job_name", help="Name of the job to test")

    # Cleanup command
    subparsers.add_parser("cleanup", help="Clean up old log files")

    # Summary command
    summary_parser = subparsers.add_parser(
        "summary", help="Show comprehensive cron job summary"
    )
    summary_parser.add_argument(
        "--detailed", action="store_true", help="Include detailed log analysis"
    )
    summary_parser.add_argument(
        "--json", action="store_true", help="Output in JSON format"
    )
    summary_parser.add_argument(
        "--days", type=int, default=3, help="Number of days to analyze"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "list":
        list_cron_jobs()
    elif args.command == "status":
        show_job_status(args.job_name, args.date)
    elif args.command == "test":
        success = test_job(args.job_name)
        sys.exit(0 if success else 1)
    elif args.command == "cleanup":
        cleanup_logs()
    elif args.command == "summary":
        run_summary(args.detailed, args.json, args.days)


if __name__ == "__main__":
    main()
