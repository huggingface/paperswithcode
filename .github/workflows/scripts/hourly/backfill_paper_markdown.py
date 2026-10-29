"""Copy available HF paper Markdown and dispatch Chandra for remaining gaps."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pymupdf
from huggingface_hub import HfApi, HfFileSystem, Volume
from huggingface_hub.errors import HfHubHTTPError
from sqlalchemy import exists, or_, select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Paper, PaperConference
from backend.scripts.generate_missing_paper_markdown import (
    download_external_pdf,
    entry_status_key,
    status_record,
    validate_canonical_markdown,
)
from backend.services.external_page_markdown_service import (
    ExternalPageMarkdownError,
    external_page_url,
    prepare_external_page_markdown,
    retry_due,
    status_key as external_page_status_key,
)
from backend.services.paper_markdown_budget_service import (
    paper_markdown_budget_snapshot,
)
from backend.services.paper_markdown_job_profile import (
    PAPER_MARKDOWN_FRESH_JOB_PROFILE,
    paper_markdown_job_profile,
)
from backend.services.paper_markdown_service import paper_markdown_bucket_key
from scripts.utils.cron_helpers import CronJobBase

ARXIV_ID = re.compile(r"^(?P<base>\d{4}\.\d{4,5})(?:v\d+)?$")
ACTIVE_STAGES = {"PENDING", "RUNNING", "STARTING", "QUEUED", "SCHEDULING"}
# A job still SCHEDULING ("waiting for requested hardware") this long is not
# going to start; it only pins one of the few concurrency slots.  On
# 2026-09-17 three such jobs held every backfill and live slot for nine hours
# and admission reported desired=0 all day.
SCHEDULING_STALL = timedelta(minutes=90)
SCRIPT = (
    Path(__file__).resolve().parents[4]
    / "backend"
    / "scripts"
    / "generate_missing_paper_markdown.py"
)
COVERAGE_HISTORY_NAME = "paper_markdown_coverage.jsonl"
DISPATCH_SCHEMA_VERSION = 1
MOUNT_PROBE_MAX_AGE = timedelta(hours=2)
MOUNT_RETRY_DELAY = timedelta(minutes=10)
LIVE_REPAIR_LIMIT = 20
RECENT_WINDOW = timedelta(days=14)
# The fresh lane (``--lane fresh``, every 5 minutes) owns papers indexed this
# recently; the hourly live lane leaves them alone so a new paper never waits
# behind a ~3h 100-paper live shard for its page-tagged reader layout.
FRESH_WINDOW = timedelta(hours=24)
# The full lane also validates canonical objects below this size from any month.
# Failed arXiv HTML scrapes are a few hundred bytes, while a converted paper is
# tens of kilobytes; objects rejected for a short body fall well below it.
STUB_SCAN_BYTES = 8 * 1024
EXTERNAL_PDF_ARCHIVE_LIMIT = 64
EXTERNAL_PDF_ARCHIVE_TIMEOUT_SECONDS = 30
# Firecrawl scrapes per invocation; the live and full lanes each run hourly.
EXTERNAL_PAGE_SCRAPE_LIMIT = 20
EXTERNAL_PAGE_SCRAPE_TIMEOUT_SECONDS = 60
PROBE_SCRIPT = (
    Path(__file__).resolve().parents[4]
    / "backend"
    / "scripts"
    / "probe_paper_markdown_volume.py"
)


def normalize_arxiv_id(value: str | None) -> str | None:
    match = ARXIV_ID.fullmatch((value or "").strip())
    return match.group("base") if match else None


def markdown_key(arxiv_id: str) -> str:
    return f"{arxiv_id[:4]}/{arxiv_id}.md"


def external_pdf_url(paper: Paper) -> str | None:
    source_url = str(paper.source_url or "").strip()
    if source_url:
        parsed = urlsplit(source_url)
        pdf_marker = f"{parsed.path}?{parsed.query}".lower()
        if (
            parsed.scheme in {"http", "https"}
            and parsed.netloc
            and (".pdf" in pdf_marker or "/pdf" in parsed.path.lower())
        ):
            return source_url
    explicit = str(paper.conference_url_pdf or "").strip()
    return explicit or None


def paper_manifest_entry(paper: Paper) -> dict[str, object] | None:
    source = str(paper.source or "arxiv")
    version = str(paper.version or "v1")
    if not version.startswith("v"):
        version = f"v{version}"
    if source == "arxiv":
        arxiv_id = normalize_arxiv_id(paper.arxiv_id)
        if arxiv_id is None:
            return None
        return {
            "paper_key": arxiv_id,
            "paper_id": str(paper.id),
            "source": "arxiv",
            "arxiv_id": arxiv_id,
            "version": version,
            "title": paper.title,
            "source_url": None,
            "pdf_url": None,
            "pdf_key": None,
            "output_key": markdown_key(arxiv_id),
        }
    if source != "external":
        return None
    pdf_url = external_pdf_url(paper)
    if pdf_url is None:
        return None
    paper_id = str(paper.id)
    paper_key = f"external/{paper_id}"
    return {
        "paper_key": paper_key,
        "paper_id": paper_id,
        "source": "external",
        "arxiv_id": None,
        "version": version,
        "title": paper.title,
        "source_url": str(paper.source_url or pdf_url),
        "pdf_url": pdf_url,
        "pdf_key": f"{paper_key}/paper.pdf",
        "output_key": f"{paper_key}.md",
    }


def entry_paper_key(entry: dict[str, object]) -> str:
    return str(entry.get("paper_key") or entry["arxiv_id"])


def layout_marker_key(entry: dict[str, object]) -> str:
    """The anchored layout Markdown, which the worker writes last."""
    return str(entry["output_key"])


def chunks[T](values: list[T], size: int) -> list[list[T]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def job_stage(job: object) -> str:
    status = getattr(job, "status", None)
    stage = getattr(job, "stage", None) or getattr(status, "stage", status)
    return str(getattr(stage, "value", stage) or "").upper()


def job_labels(job: object) -> dict[str, str]:
    labels = getattr(job, "labels", {}) or {}
    return {str(key): str(value) for key, value in labels.items()}


def job_stage_message(job: object) -> str:
    status = getattr(job, "status", None)
    return str(getattr(status, "message", "") or "")


def is_volume_mount_failure(job: object) -> bool:
    message = job_stage_message(job).lower()
    return job_stage(job) in {"ERROR", "CANCELED"} and (
        "mount" in message or "volume" in message
    )


def utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def status_disposition(
    status: dict[str, object],
    *,
    now: datetime | None = None,
    max_attempts: int = 3,
    canonical_missing: bool = False,
    requested_version: str | None = None,
) -> str:
    """Return a persisted retry disposition without parsing free-form errors."""
    state = str(status.get("status") or "").lower()
    try:
        attempts = max(0, int(status.get("attempt_count") or 0))
    except (TypeError, ValueError):
        return "permanent_failure"
    if state in {"succeeded", "already_exists"}:
        if canonical_missing:
            return "retryable_due" if attempts < max_attempts else "attempts_exhausted"
        return "completed"
    # Legacy failed records predate structured retry metadata. Admit each once
    # so the worker can persist a classified v2 record without error-string
    # inference in the scheduler.
    if state == "failed" and not status.get("schema_version"):
        return "retryable_due"
    if attempts >= max_attempts:
        return "attempts_exhausted"
    # Older workers treated interrupted HTTP transfers as permanent failures.
    if state == "failed" and status.get("error_class") in {
        "RemoteProtocolError",
        "ReadError",
        "ConnectError",
        "WriteError",
    }:
        return "retryable_due"
    if (
        state == "failed"
        and status.get("error_class") == "arxiv_http_404"
        and requested_version is not None
        and status.get("requested_version") != requested_version
    ):
        return "retryable_due"
    # Worker releases before the bounded arXiv-version fallback could classify a
    # stale requested version as a permanent 404. Re-admit those records once;
    # the corrected worker records that it tried the fallback chain.
    if (
        state == "failed"
        and status.get("source") != "external"
        and status.get("error_class") == "arxiv_http_404"
        and status.get("version_fallback_attempted") is not True
    ):
        return "retryable_due"
    # Before the Git LFS URL fix, GitHub-hosted PDFs resolved to the LFS pointer
    # and failed as a permanent invalid_pdf. Re-admit those records once; the
    # corrected archiver and worker record that they used the fixed resolver.
    if (
        state == "failed"
        and status.get("source") == "external"
        and status.get("error_class") == "invalid_pdf"
        and status.get("lfs_pdf_url_attempted") is not True
    ):
        return "retryable_due"
    if status.get("retryable") is not True:
        return "permanent_failure"
    retry_at = status.get("next_retry_at")
    if not retry_at:
        return "retryable_due"
    try:
        due_at = datetime.fromisoformat(str(retry_at).replace("Z", "+00:00"))
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
    except ValueError:
        return "retryable_deferred"
    return (
        "retryable_due"
        if due_at <= (now or datetime.now(UTC))
        else "retryable_deferred"
    )


def append_coverage_history(payload: dict[str, object]) -> None:
    """Keep append-only local evidence for seven-day coverage deltas."""
    log_dir = Path(
        os.environ.get("PWC_CRON_LOG_DIR", Path(__file__).resolve().parents[1] / "logs")
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / COVERAGE_HISTORY_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


class PaperMarkdownBackfillJob(CronJobBase):
    fresh = False

    def __init__(
        self,
        *,
        full: bool,
        execute: bool,
        confirm: bool,
        max_jobs: int | None,
        batch_size: int | None,
        probe_volume: bool = False,
        recover_mount_failures: bool = False,
        paid_canary: bool = False,
        retry_only: bool = False,
        repair_invalid_limit: int = 0,
        lane: str | None = None,
    ):
        super().__init__("paper_markdown_backfill")
        self.settings = get_settings()
        self.full = full
        self.fresh = lane == "fresh"
        self.should_execute = execute
        self.confirm = confirm
        self.max_jobs = max_jobs
        self.batch_size = batch_size
        self.probe_volume = probe_volume
        self.recover_mount_failures = recover_mount_failures
        self.paid_canary = paid_canary
        self.retry_only = retry_only
        self.repair_invalid_limit = repair_invalid_limit
        self.budget_projected_usd: float | None = None
        self.budget_ceiling_usd: float | None = None
        self.budget_desired_jobs = 0
        self.budget_affordable_jobs = 0
        self.retryable_papers_blocked_by_budget = 0
        self.paid_authorization_required = False
        self.stalled_scheduling_jobs = 0
        self.api = HfApi(token=self.settings.hf_token or None)
        self.filesystem = HfFileSystem(token=self.settings.hf_token or None)

    @property
    def mode(self) -> str:
        return "backfill" if self.full else "live"

    @property
    def profile(self):
        if self.fresh:
            return PAPER_MARKDOWN_FRESH_JOB_PROFILE
        return paper_markdown_job_profile(self.mode)

    def _papers(
        self, *, recent_only: bool = False, window: timedelta | None = None
    ) -> list[dict[str, object]]:
        if window is None and (not self.full or recent_only):
            window = FRESH_WINDOW if self.fresh else RECENT_WINDOW
        with db_manager.session_local() as db:
            query = select(Paper).where(
                Paper.is_latest_version,
                Paper.source.in_(("arxiv", "external")),
            )
            if window is not None:
                query = query.where(Paper.created_at >= datetime.now(UTC) - window)
                query = query.order_by(Paper.created_at.desc(), Paper.id.desc())
            else:
                in_conference = or_(
                    Paper.conference.isnot(None),
                    exists().where(PaperConference.paper_id == Paper.id),
                )
                query = query.order_by(
                    Paper.hf_daily_featured_on.is_(None),
                    in_conference,
                    Paper.date_published.desc().nullslast(),
                    Paper.id.desc(),
                )
            rows = db.execute(query).scalars()
            papers: dict[str, dict[str, object]] = {}
            for paper in rows:
                entry = paper_manifest_entry(paper)
                if entry is None:
                    continue
                papers[entry_paper_key(entry)] = entry
            return list(papers.values())

    def _fresh_paper_keys(self) -> set[str]:
        """Papers the fresh lane owns, which the hourly live lane skips."""
        if self.full or self.fresh:
            return set()
        return {entry_paper_key(item) for item in self._papers(window=FRESH_WINDOW)}

    def _prepare_external_pages(self) -> dict[str, int]:
        """Turn HTML-only external papers without Markdown into Markdown."""
        with db_manager.session_local() as db:
            query = select(
                Paper.id,
                Paper.title,
                Paper.source,
                Paper.source_url,
                Paper.conference_url_pdf,
            ).where(Paper.is_latest_version, Paper.source == "external")
            if self.full:
                query = query.order_by(Paper.id)
            else:
                query = query.where(
                    Paper.created_at >= datetime.now(UTC) - timedelta(days=14)
                ).order_by(Paper.created_at.desc(), Paper.id.desc())
            pages = {
                str(row.id): (row.title, url)
                for row in db.execute(query)
                if (
                    url := external_page_url(
                        source=row.source,
                        source_url=row.source_url,
                        conference_url_pdf=row.conference_url_pdf,
                    )
                )
            }
        existing = self._existing_paths(
            self.settings.paper_markdown_hf_bucket_id,
            [
                paper_markdown_bucket_key(paper_id, source="external")
                for paper_id in pages
            ],
        )
        missing = [
            paper_id
            for paper_id in pages
            if paper_markdown_bucket_key(paper_id, source="external") not in existing
        ]
        statuses = self._status_records(
            [external_page_status_key(paper_id) for paper_id in missing]
        )
        due = [
            paper_id
            for paper_id in missing
            if retry_due(statuses.get(external_page_status_key(paper_id), {}))
        ]
        selected = due[:EXTERNAL_PAGE_SCRAPE_LIMIT]
        counts = {
            "external_pages_eligible": len(pages),
            "external_pages_missing": len(missing),
            "external_pages_due": len(due),
            "external_pages_published": 0,
            "external_pages_failed": 0,
        }
        if not self.should_execute or not self.settings.firecrawl_api_key:
            return counts

        def prepare(paper_id: str) -> bool:
            title, url = pages[paper_id]
            try:
                prepare_external_page_markdown(
                    paper_id=paper_id,
                    title=title,
                    page_url=url,
                    api_key=self.settings.firecrawl_api_key,
                    bucket_id=self.settings.paper_markdown_hf_bucket_id,
                    token=self.settings.hf_token or None,
                    timeout_seconds=EXTERNAL_PAGE_SCRAPE_TIMEOUT_SECONDS,
                )
            except ExternalPageMarkdownError as error:
                self.logger.info(
                    "external page Markdown failed for %s: %s", paper_id, error.code
                )
                return False
            return True

        with ThreadPoolExecutor(max_workers=4) as executor:
            outcomes = list(executor.map(prepare, selected))
        counts["external_pages_published"] = sum(outcomes)
        counts["external_pages_failed"] = len(outcomes) - sum(outcomes)
        return counts

    def _semantic_records(
        self,
        papers: list[dict[str, object]],
        canonical: dict[str, object],
        *,
        bucket: str | None = None,
    ) -> dict[str, str]:
        """Inspect only the bounded recent canonical cohort."""
        selected = [item for item in papers if str(item["output_key"]) in canonical]

        def inspect(item: dict[str, object]) -> tuple[str, str]:
            key = str(item["output_key"])
            path = f"hf://buckets/{bucket or self.settings.paper_markdown_hf_bucket_id}/{key}"
            try:
                with self.filesystem.open(path, "rb", block_size=0) as handle:
                    raw = handle.read(64 * 1024 * 1024 + 1)
                if len(raw) > 64 * 1024 * 1024:
                    return key, "invalid"
                validate_canonical_markdown(str(item["title"]), raw.decode("utf-8"))
                return key, "valid"
            except ValueError:
                return key, "invalid"
            except (OSError, UnicodeDecodeError, HfHubHTTPError):
                return key, "unavailable"

        with ThreadPoolExecutor(max_workers=8) as executor:
            return dict(executor.map(inspect, selected))

    def _existing_paths(self, bucket: str, paths: list[str]) -> dict[str, object]:
        found: dict[str, object] = {}
        for batch in chunks(paths, 1000):
            for entry in self.api.get_bucket_paths_info(
                bucket, batch, token=self.settings.hf_token or None
            ):
                found[entry.path] = entry
        return found

    def _status_records(self, paths: list[str]) -> dict[str, dict[str, object]]:
        existing = self._existing_paths(
            self.settings.paper_markdown_hf_bucket_id, paths
        )

        def read(path: str) -> tuple[str, dict[str, object]]:
            bucket_path = (
                f"hf://buckets/{self.settings.paper_markdown_hf_bucket_id}/{path}"
            )
            try:
                with self.filesystem.open(bucket_path, "rb", block_size=0) as handle:
                    raw = handle.read(64 * 1024 + 1)
                if len(raw) > 64 * 1024:
                    return path, {"status": "oversized", "retryable": False}
                payload = json.loads(raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, HfHubHTTPError):
                return path, {"status": "unreadable", "retryable": False}
            if isinstance(payload, dict):
                return path, payload
            return path, {"status": "invalid", "retryable": False}

        with ThreadPoolExecutor(max_workers=8) as executor:
            return dict(executor.map(read, existing))

    def _layout_candidates(
        self, papers: list[dict[str, object]], *, limit: int
    ) -> tuple[list[dict[str, object]], int]:
        """Return due layout-only work in ``papers`` order and the missing count.

        ``papers`` already have canonical Markdown, often an arXiv HTML copy
        without pages, so the worker only adds the page-aware layout.
        """
        layout = self._existing_paths(
            self.settings.paper_layout_hf_bucket_id,
            [layout_marker_key(item) for item in papers],
        )
        missing = [item for item in papers if layout_marker_key(item) not in layout]
        selected: list[dict[str, object]] = []
        for window in chunks(missing, 1000):
            if len(selected) >= limit:
                break
            entries = [{**item, "layout_only": True} for item in window]
            statuses = self._status_records([entry_status_key(e) for e in entries])
            for entry in entries:
                status = statuses.get(entry_status_key(entry))
                disposition = status_disposition(status) if status else None
                if disposition in {None, "retryable_due"}:
                    selected.append({**entry, "retry": disposition is not None})
        return selected[:limit], len(missing)

    def _busy_paper_keys(self, jobs: list[object]) -> tuple[set[str], bool]:
        """Papers already in an active job's manifest, so no shard repeats them.

        Also reports whether every active OCR manifest was readable, because
        an unreadable manifest hides which papers are busy.
        """
        keys: set[str] = set()
        complete = True
        for job in jobs:
            labels = job_labels(job)
            if job_stage(job) not in ACTIVE_STAGES:
                continue
            if labels.get("job_type", "ocr") != "ocr":
                continue
            if not labels.get("run_id") or not labels.get("shard_id"):
                complete = False
                continue
            path = (
                f"hf://buckets/{self.settings.paper_markdown_hf_bucket_id}/_jobs/"
                f"manifests/{labels['run_id']}/{labels['shard_id']}.jsonl"
            )
            try:
                with self.filesystem.open(path, "rb", block_size=0) as handle:
                    lines = handle.read().decode("utf-8").splitlines()
            except (OSError, UnicodeDecodeError, HfHubHTTPError):
                complete = False
                continue
            keys.update(entry_paper_key(json.loads(line)) for line in lines if line)
        return keys, complete

    def _copy_upstream(
        self, missing: list[dict[str, object]]
    ) -> tuple[list[dict[str, object]], int]:
        paths = [str(item["output_key"]) for item in missing]
        upstream = self._existing_paths(
            self.settings.paper_markdown_upstream_bucket_id, paths
        )
        validation = self._semantic_records(
            missing, upstream, bucket=self.settings.paper_markdown_upstream_bucket_id
        )
        copy_items: list[tuple[str, str, str, str]] = []
        copied_paths: set[str] = set()
        for path, entry in upstream.items():
            xet_hash = getattr(entry, "xet_hash", None)
            if not xet_hash or validation.get(path) != "valid":
                continue
            copy_items.append(
                (
                    "bucket",
                    self.settings.paper_markdown_upstream_bucket_id,
                    xet_hash,
                    path,
                )
            )
            copied_paths.add(path)
        if self.should_execute:
            for batch in chunks(copy_items, 100):
                self.api.batch_bucket_files(
                    self.settings.paper_markdown_hf_bucket_id,
                    copy=batch,
                    token=self.settings.hf_token or None,
                )
        remaining = [
            item for item in missing if str(item["output_key"]) not in copied_paths
        ]
        return remaining, len(copied_paths)

    def _remote_jobs(self) -> list[object]:
        return list(
            self.api.list_jobs(
                labels={"app": "pwc-paper-markdown"},
                namespace=self.settings.paper_markdown_hf_namespace,
                token=self.settings.hf_token or None,
            )
        )

    def _reap_stalled_scheduling(self, jobs: list[object]) -> list[object]:
        """Cancel our jobs stuck in SCHEDULING past SCHEDULING_STALL.

        Returns the remaining jobs so slot accounting does not count a job
        that will never leave the hardware queue.  Dry runs only report.
        """
        now = datetime.now(UTC)
        kept: list[object] = []
        for job in jobs:
            created = getattr(job, "created_at", None)
            if isinstance(created, datetime) and created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            stalled = (
                job_stage(job) == "SCHEDULING"
                and job_labels(job).get("app") == "pwc-paper-markdown"
                and isinstance(created, datetime)
                and now - created >= SCHEDULING_STALL
            )
            if not stalled:
                kept.append(job)
                continue
            self.stalled_scheduling_jobs += 1
            job_id = str(getattr(job, "id", ""))
            if self.should_execute:
                self.api.cancel_job(
                    job_id=job_id, namespace=self.settings.paper_markdown_hf_namespace
                )
            self.logger.warning(
                "paper Markdown job %s %s after %s in SCHEDULING (%s)",
                job_id,
                "cancelled" if self.should_execute else "would be cancelled",
                now - created,
                job_stage_message(job) or "no status message",
            )
        return kept

    def _active_jobs(self, jobs: list[object]) -> list[object]:
        return [
            job
            for job in jobs
            if job_stage(job) in ACTIVE_STAGES
            and job_labels(job).get("mode") == self.mode
            and (job_labels(job).get("lane") == "fresh") == self.fresh
        ]

    def _budget_decision(
        self, desired_jobs: int, jobs: list[object]
    ) -> dict[str, object]:
        ceiling = (
            self.settings.paper_markdown_backfill_budget_usd
            if self.full
            else self.settings.paper_markdown_incremental_monthly_budget_usd
        )
        budget = paper_markdown_budget_snapshot(
            jobs,
            mode=self.mode,
            ceiling_usd=ceiling,
            planned_jobs=desired_jobs,
            profile=self.profile,
            cost_policy=self.settings.paper_markdown_cost_policy,
        )
        self.budget_desired_jobs = int(budget["desired_jobs"])
        self.budget_affordable_jobs = int(budget["affordable_jobs"])
        self.budget_projected_usd = float(budget["projected_usd"])
        self.budget_ceiling_usd = ceiling
        if desired_jobs and not self.budget_affordable_jobs:
            self.logger.warning(
                "paper Markdown GPU budget exhausted: %s",
                budget["reason"],
            )
        return budget

    def _bucket_json(self, key: str) -> dict[str, object]:
        path = f"hf://buckets/{self.settings.paper_markdown_hf_bucket_id}/{key}"
        try:
            with self.filesystem.open(path, "rb", block_size=0) as handle:
                raw = handle.read(64 * 1024 + 1)
            if len(raw) > 64 * 1024:
                return {}
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, HfHubHTTPError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_bucket_json(self, key: str, payload: dict[str, object]) -> None:
        self.api.batch_bucket_files(
            self.settings.paper_markdown_hf_bucket_id,
            add=[(json.dumps(payload, sort_keys=True, indent=2).encode(), key)],
            token=self.settings.hf_token or None,
        )

    @staticmethod
    def _dispatch_key(run_id: str, shard_id: str) -> str:
        return f"_jobs/dispatch/{run_id}/{shard_id}.json"

    def _persist_dispatch(
        self,
        *,
        run_id: str,
        shard_id: str,
        manifest_key: str,
        provider_attempts: list[dict[str, object]],
        requires_operator_ack: bool = False,
    ) -> None:
        self._write_bucket_json(
            self._dispatch_key(run_id, shard_id),
            {
                "schema_version": DISPATCH_SCHEMA_VERSION,
                "logical_run_id": run_id,
                "logical_shard_id": shard_id,
                "manifest_key": manifest_key,
                "mode": self.mode,
                "profile": self.profile.as_dict(),
                "provider_attempts": provider_attempts,
                "requires_operator_ack": requires_operator_ack,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    def _run_ocr_job(
        self,
        *,
        run_id: str,
        shard_id: str,
        manifest_key: str,
        provider_attempt: int,
        replacement_for: str | None = None,
    ) -> object:
        labels = {
            "app": "pwc-paper-markdown",
            "mode": self.mode,
            "run_id": run_id,
            "shard_id": shard_id,
            "job_type": "ocr",
            "profile_id": self.profile.profile_id,
            "hard_timeout_seconds": str(self.profile.hard_timeout_seconds),
            "provider_attempt": str(provider_attempt),
            "retry_number": str(max(0, provider_attempt - 1)),
        }
        if replacement_for:
            labels["replacement_for"] = replacement_for
        if self.fresh:
            labels["lane"] = "fresh"
        return self.api.run_uv_job(
            str(SCRIPT),
            script_args=[
                "--bucket-id",
                self.settings.paper_markdown_hf_bucket_id,
                "--manifest-key",
                manifest_key,
                "--layout-bucket-id",
                self.settings.paper_layout_hf_bucket_id,
                "--soft-deadline-seconds",
                str(self.profile.soft_deadline_seconds),
            ],
            image=self.settings.paper_markdown_runtime_image,
            flavor=self.settings.paper_markdown_hardware,
            timeout=self.profile.hard_timeout,
            labels=labels,
            env={
                "PWC_MARKDOWN_MODEL_ID": self.settings.paper_markdown_model_id,
                "PWC_MARKDOWN_MODEL_REVISION": (
                    self.settings.paper_markdown_model_revision
                ),
                "PWC_MARKDOWN_MAX_PAGES": str(self.settings.paper_markdown_max_pages),
                "PWC_SCRIPT_VERSION": os.environ.get("PWC_RELEASE_ID", "development"),
            },
            secrets={"HF_TOKEN": self.settings.hf_token},
            volumes=[],
            namespace=self.settings.paper_markdown_hf_namespace,
            token=self.settings.hf_token or None,
        )

    def _launch_volume_probe(self) -> dict[str, object]:
        remote_jobs = self._remote_jobs()
        has_slot = len(self._active_jobs(remote_jobs)) < self.profile.concurrency
        budget = self._budget_decision(1 if has_slot else 0, remote_jobs)
        if not has_slot:
            return {
                "operation": "volume_probe",
                "execute": self.should_execute,
                "launched": False,
                "reason": "no measured-profile concurrency slot is available",
                "profile": self.profile.as_dict(),
                "budget": budget,
            }
        if not int(budget["affordable_jobs"]):
            return {
                "operation": "volume_probe",
                "execute": self.should_execute,
                "launched": False,
                "reason": budget["reason"],
                "profile": self.profile.as_dict(),
                "budget": budget,
            }
        if not self.should_execute:
            return {
                "operation": "volume_probe",
                "execute": False,
                "launched": False,
                "reason": "dry run; paid capability probe not dispatched",
                "profile": self.profile.as_dict(),
                "budget": budget,
            }
        if not self.confirm:
            raise ValueError("paid volume capability probe requires --confirm")

        probe_id = f"probe-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
        manifest_key = f"_jobs/capabilities/{probe_id}.manifest.json"
        result_key = f"_jobs/capabilities/{probe_id}.json"
        self._write_bucket_json(
            manifest_key,
            {
                "schema_version": 1,
                "probe_id": probe_id,
                "nonce": uuid.uuid4().hex,
                "bucket_id": self.settings.paper_markdown_hf_bucket_id,
                "namespace": self.settings.paper_markdown_hf_namespace,
                "mount_path": "/content",
                "read_only": False,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        info = self.api.run_uv_job(
            str(PROBE_SCRIPT),
            script_args=[
                "--manifest",
                f"/content/{manifest_key}",
                "--result",
                f"/content/{result_key}",
                "--content-root",
                "/content",
            ],
            image=self.settings.paper_markdown_runtime_image,
            flavor=self.settings.paper_markdown_hardware,
            timeout=self.profile.hard_timeout,
            labels={
                "app": "pwc-paper-markdown",
                "mode": self.mode,
                "job_type": "volume_probe",
                "probe_id": probe_id,
                "profile_id": self.profile.profile_id,
                "hard_timeout_seconds": str(self.profile.hard_timeout_seconds),
            },
            secrets={"HF_TOKEN": self.settings.hf_token},
            volumes=[
                Volume(
                    type="bucket",
                    source=self.settings.paper_markdown_hf_bucket_id,
                    mount_path="/content",
                    read_only=False,
                )
            ],
            namespace=self.settings.paper_markdown_hf_namespace,
            token=self.settings.hf_token or None,
        )
        return {
            "operation": "volume_probe",
            "execute": True,
            "launched": True,
            "probe_id": probe_id,
            "provider_job_id": str(
                getattr(info, "id", None) or getattr(info, "job_id", "")
            ),
            "profile": self.profile.as_dict(),
            "budget": budget,
        }

    def _latest_successful_mount_probe(
        self, remote_jobs: list[object], *, now: datetime
    ) -> dict[str, object] | None:
        probes = sorted(
            (
                job
                for job in remote_jobs
                if job_labels(job).get("job_type") == "volume_probe"
                and job_stage(job) == "COMPLETED"
            ),
            key=lambda job: (
                utc_datetime(getattr(job, "finished_at", None))
                or datetime.min.replace(tzinfo=UTC)
            ),
            reverse=True,
        )
        for job in probes:
            finished_at = utc_datetime(getattr(job, "finished_at", None))
            if finished_at is None or now - finished_at > MOUNT_PROBE_MAX_AGE:
                continue
            probe_id = job_labels(job).get("probe_id")
            if not probe_id:
                continue
            evidence = self._bucket_json(f"_jobs/capabilities/{probe_id}.json")
            if (
                evidence.get("status") == "succeeded"
                and evidence.get("probe_id") == probe_id
                and evidence.get("bucket_id")
                == self.settings.paper_markdown_hf_bucket_id
                and evidence.get("namespace")
                == self.settings.paper_markdown_hf_namespace
                and evidence.get("mount_path") == "/content"
                and evidence.get("read_only") is False
            ):
                return {
                    "probe_id": probe_id,
                    "provider_job_id": str(getattr(job, "id", "")),
                    "finished_at": finished_at.isoformat(),
                }
        return None

    def _mount_recovery_candidates(
        self, remote_jobs: list[object], *, now: datetime
    ) -> tuple[list[dict[str, object]], int]:
        logical: dict[tuple[str, str], list[object]] = {}
        for job in remote_jobs:
            labels = job_labels(job)
            if labels.get("job_type", "ocr") != "ocr":
                continue
            if labels.get("mode") != self.mode:
                continue
            run_id = labels.get("run_id")
            shard_id = labels.get("shard_id")
            if run_id and shard_id:
                logical.setdefault((run_id, shard_id), []).append(job)

        candidates: list[dict[str, object]] = []
        acknowledgement_required = 0
        for (run_id, shard_id), attempts in logical.items():
            attempts.sort(
                key=lambda job: int(job_labels(job).get("provider_attempt", "0"))
            )
            mount_failures = [job for job in attempts if is_volume_mount_failure(job)]
            if len(mount_failures) >= 2:
                acknowledgement_required += 1
                continue
            if len(attempts) != 1 or len(mount_failures) != 1:
                continue
            failed = mount_failures[0]
            finished_at = utc_datetime(getattr(failed, "finished_at", None))
            if finished_at is None or now - finished_at < MOUNT_RETRY_DELAY:
                continue
            progress_key = f"_jobs/progress/{run_id}/{shard_id}.json"
            if self._bucket_json(progress_key):
                continue
            manifest_key = f"_jobs/manifests/{run_id}/{shard_id}.jsonl"
            manifest_path = (
                f"hf://buckets/{self.settings.paper_markdown_hf_bucket_id}/"
                f"{manifest_key}"
            )
            if not self.filesystem.exists(manifest_path):
                continue
            candidates.append(
                {
                    "run_id": run_id,
                    "shard_id": shard_id,
                    "manifest_key": manifest_key,
                    "failed_provider_job_id": str(getattr(failed, "id", "")),
                    "failed_at": finished_at.isoformat(),
                }
            )
        return candidates, acknowledgement_required

    def _recover_mount_failures(self) -> dict[str, object]:
        now = datetime.now(UTC)
        remote_jobs = self._remote_jobs()
        candidates, acknowledgement_required = self._mount_recovery_candidates(
            remote_jobs, now=now
        )
        probe = self._latest_successful_mount_probe(remote_jobs, now=now)
        available_slots = max(
            0, self.profile.concurrency - len(self._active_jobs(remote_jobs))
        )
        if self.max_jobs is not None:
            available_slots = min(available_slots, self.max_jobs)
        desired = min(len(candidates), available_slots)
        budget = self._budget_decision(desired, remote_jobs)
        selected = candidates[: int(budget["affordable_jobs"])]
        if self.should_execute and selected and not self.confirm:
            raise ValueError("paid mount recovery requires --confirm")

        launched: list[dict[str, object]] = []
        for candidate in selected:
            if not self.should_execute:
                launched.append({**candidate, "dry_run": True})
                continue
            info = self._run_ocr_job(
                run_id=str(candidate["run_id"]),
                shard_id=str(candidate["shard_id"]),
                manifest_key=str(candidate["manifest_key"]),
                provider_attempt=2,
                replacement_for=str(candidate["failed_provider_job_id"]),
            )
            provider_job_id = str(
                getattr(info, "id", None) or getattr(info, "job_id", "")
            )
            self._persist_dispatch(
                run_id=str(candidate["run_id"]),
                shard_id=str(candidate["shard_id"]),
                manifest_key=str(candidate["manifest_key"]),
                provider_attempts=[
                    {
                        "attempt": 1,
                        "retry_number": 0,
                        "provider_job_id": candidate["failed_provider_job_id"],
                        "terminal_cause": "volume_mount",
                        "finished_at": candidate["failed_at"],
                    },
                    {
                        "attempt": 2,
                        "retry_number": 1,
                        "provider_job_id": provider_job_id,
                        "dispatched_at": datetime.now(UTC).isoformat(),
                        "capability_probe_id": probe["probe_id"] if probe else None,
                    },
                ],
            )
            launched.append({**candidate, "provider_job_id": provider_job_id})
        return {
            "operation": "mount_recovery",
            "storage_transport": "bucket_api",
            "execute": self.should_execute,
            "probe": probe,
            "retryable_logical_shards": len(candidates),
            "operator_acknowledgement_required": acknowledgement_required,
            "launched_replacements": len(launched),
            "replacement_attempts": launched,
            "profile": self.profile.as_dict(),
            "budget": budget,
        }

    def _launch(
        self,
        candidates: list[dict[str, object]],
        *,
        additional_active_job_ids: set[str] | None = None,
    ) -> list[dict[str, str]]:
        remote_jobs = self._reap_stalled_scheduling(self._remote_jobs())
        active = self._active_jobs(remote_jobs)
        busy, busy_known = self._busy_paper_keys(remote_jobs)
        candidates = [item for item in candidates if entry_paper_key(item) not in busy]
        # Repairs overwrite existing objects, so they run beside active workers
        # only when every active manifest proves the paper is not in flight.
        if not busy_known and any(
            item.get("replace_invalid_sha256") for item in candidates
        ):
            self.logger.warning(
                "Markdown repair waits: an active worker's manifest is unreadable"
            )
            candidates = [
                item for item in candidates if not item.get("replace_invalid_sha256")
            ]
        concurrency = self.profile.concurrency
        if self.max_jobs is not None:
            concurrency = min(concurrency, self.max_jobs)
        visible_ids = {
            str(getattr(job, "id", None) or getattr(job, "job_id", ""))
            for job in active
        }
        unlisted_active = len((additional_active_job_ids or set()) - visible_ids)
        available_slots = max(0, concurrency - len(active) - unlisted_active)
        batch_size = self.profile.max_papers
        if self.batch_size is not None:
            maximum = self.profile.max_papers
            if self.batch_size < 1 or self.batch_size > maximum:
                raise ValueError(f"batch size must be between 1 and {maximum}")
            batch_size = self.batch_size
        candidate_plans = chunks(candidates, batch_size)
        desired_plans = candidate_plans[:available_slots]
        budget = self._budget_decision(len(desired_plans), remote_jobs)
        affordable = int(budget["affordable_jobs"])
        plans = desired_plans[:affordable]
        self.retryable_papers_blocked_by_budget = max(
            0,
            sum(bool(item.get("retry")) for plan in desired_plans for item in plan)
            - sum(bool(item.get("retry")) for plan in plans for item in plan),
        )
        if self.should_execute and plans and not self.confirm:
            raise ValueError("paid GPU dispatch requires --confirm")
        paid_dispatch_enabled = bool(
            getattr(self.settings, "paper_markdown_paid_dispatch_enabled", False)
        )
        if (
            self.should_execute
            and plans
            and self.settings.paper_markdown_cost_policy == "metered"
            and not paid_dispatch_enabled
            and not getattr(self, "paid_canary", False)
        ):
            self.paid_authorization_required = True
            self.logger.warning(
                "measured-profile OCR dispatch awaits explicit paid execution "
                "authorization"
            )
            self.logger.info(
                "paper Markdown admission: desired=%s affordable=%s "
                "planned_or_launched=0",
                self.budget_desired_jobs,
                self.budget_affordable_jobs,
            )
            return []

        launched: list[dict[str, str]] = []
        remaining_external_downloads = EXTERNAL_PDF_ARCHIVE_LIMIT
        run_id = (
            f"{'backfill' if self.full else 'live'}-{'fresh-' if self.fresh else ''}"
            f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
        )
        for shard_number, entries in enumerate(candidate_plans):
            if len(launched) >= affordable:
                break
            if self.should_execute:
                entries, attempted = self._archive_external_pdfs(
                    entries, max_downloads=remaining_external_downloads
                )
                remaining_external_downloads -= attempted
                if not entries:
                    continue
            shard_id = f"{shard_number:05d}"
            manifest_key = f"_jobs/manifests/{run_id}/{shard_id}.jsonl"
            manifest = (
                "\n".join(json.dumps(item, sort_keys=True) for item in entries) + "\n"
            ).encode()
            if not self.should_execute:
                launched.append(
                    {
                        "run_id": run_id,
                        "shard_id": shard_id,
                        "papers": str(len(entries)),
                        "mode": "dry_run",
                        "profile_id": self.profile.profile_id,
                        "hard_timeout_seconds": str(self.profile.hard_timeout_seconds),
                        "soft_deadline_seconds": str(
                            self.profile.soft_deadline_seconds
                        ),
                        "retried": str(
                            sum(bool(item.get("retry")) for item in entries)
                        ),
                    }
                )
                continue
            self.api.batch_bucket_files(
                self.settings.paper_markdown_hf_bucket_id,
                add=[(manifest, manifest_key)],
                token=self.settings.hf_token or None,
            )
            self._persist_dispatch(
                run_id=run_id,
                shard_id=shard_id,
                manifest_key=manifest_key,
                provider_attempts=[],
            )
            info = self._run_ocr_job(
                run_id=run_id,
                shard_id=shard_id,
                manifest_key=manifest_key,
                provider_attempt=1,
            )
            job_id = str(getattr(info, "id", None) or getattr(info, "job_id", ""))
            self._persist_dispatch(
                run_id=run_id,
                shard_id=shard_id,
                manifest_key=manifest_key,
                provider_attempts=[
                    {
                        "attempt": 1,
                        "retry_number": 0,
                        "provider_job_id": job_id,
                        "dispatched_at": datetime.now(UTC).isoformat(),
                    }
                ],
            )
            launched.append(
                {
                    "run_id": run_id,
                    "shard_id": shard_id,
                    "papers": str(len(entries)),
                    "hf_job_id": job_id,
                    "retried": str(sum(bool(item.get("retry")) for item in entries)),
                }
            )
        self.logger.info(
            "paper Markdown admission: desired=%s affordable=%s planned_or_launched=%s",
            self.budget_desired_jobs,
            self.budget_affordable_jobs,
            len(launched),
        )
        return launched

    def _archive_external_pdfs(
        self, entries: list[dict[str, object]], *, max_downloads: int
    ) -> tuple[list[dict[str, object]], int]:
        external = [
            entry
            for entry in entries
            if entry.get("source") == "external" and entry.get("pdf_key")
        ]
        existing = self._existing_paths(
            self.settings.paper_markdown_hf_bucket_id,
            [str(entry["pdf_key"]) for entry in external],
        )
        missing = [entry for entry in external if str(entry["pdf_key"]) not in existing]
        selected = missing[:max_downloads]
        deferred = {entry_paper_key(entry) for entry in missing[max_downloads:]}

        def archive(entry: dict[str, object]) -> str | None:
            pdf_key = str(entry["pdf_key"])
            try:
                pdf = download_external_pdf(
                    str(entry["pdf_url"]),
                    timeout_seconds=EXTERNAL_PDF_ARCHIVE_TIMEOUT_SECONDS,
                    max_elapsed_seconds=EXTERNAL_PDF_ARCHIVE_TIMEOUT_SECONDS,
                )
                with pymupdf.open(stream=pdf, filetype="pdf") as document:
                    if document.page_count < 1:
                        raise ValueError("invalid_pdf")
            except Exception as error:  # noqa: BLE001 - isolate failures per paper
                paper_key = entry_paper_key(entry)
                status_key = f"_jobs/status/{paper_key}.json"
                failure = status_record(
                    {
                        "paper_key": paper_key,
                        "paper_id": entry.get("paper_id"),
                        "source": "external",
                        "arxiv_id": None,
                        "status": "failed",
                        "error": str(error)[:1000],
                        "requested_version": entry["version"],
                        "version_fallback_attempted": False,
                        "lfs_pdf_url_attempted": True,
                    },
                    prior=self._bucket_json(status_key),
                    error=error,
                )
                self._write_bucket_json(status_key, failure)
                self.logger.warning(
                    "external PDF archival failed for %s: %s", paper_key, error
                )
                return paper_key
            try:
                self.api.batch_bucket_files(
                    self.settings.paper_markdown_hf_bucket_id,
                    add=[(pdf, pdf_key)],
                    token=self.settings.hf_token or None,
                )
            except Exception as error:  # noqa: BLE001 - isolate failures per paper
                self.logger.warning(
                    "external PDF upload failed for %s: %s",
                    entry_paper_key(entry),
                    error,
                )
                return entry_paper_key(entry)
            return None

        failed: set[str] = set()
        if selected:
            with ThreadPoolExecutor(max_workers=min(8, len(selected))) as executor:
                failed.update(key for key in executor.map(archive, selected) if key)
        excluded = failed | deferred
        return (
            [entry for entry in entries if entry_paper_key(entry) not in excluded],
            len(selected),
        )

    def run(self) -> None:
        if self.should_execute and not self.settings.hf_token:
            raise ValueError("PWC_HF_TOKEN is required")
        if self.probe_volume:
            result = self._launch_volume_probe()
            self.logger.info("PAPER_MARKDOWN_SUMMARY %s", json.dumps(result))
            return
        if self.recover_mount_failures:
            result = self._recover_mount_failures()
            self.logger.info("PAPER_MARKDOWN_SUMMARY %s", json.dumps(result))
            return
        additional_active_job_ids: set[str] = set()
        if self.full and self.should_execute:
            recovery = self._recover_mount_failures()
            additional_active_job_ids = {
                str(attempt["provider_job_id"])
                for attempt in recovery.get("replacement_attempts", [])
                if attempt.get("provider_job_id")
            }
        papers = self._papers()
        paths = [str(item["output_key"]) for item in papers]
        canonical = self._existing_paths(
            self.settings.paper_markdown_hf_bucket_id, paths
        )
        missing = [item for item in papers if str(item["output_key"]) not in canonical]
        remaining, upstream_available = (
            (missing, 0)
            if getattr(self, "repair_invalid_limit", 0)
            else self._copy_upstream(missing)
        )
        remaining_paths = {str(item["output_key"]) for item in remaining}
        recent_papers = papers if not self.full else self._papers(recent_only=True)
        recent_keys = {str(item["output_key"]) for item in recent_papers}
        stub_papers = [
            item
            for item in papers
            if self.full
            and str(item["output_key"]) not in recent_keys
            and getattr(canonical.get(str(item["output_key"])), "size", STUB_SCAN_BYTES)
            < STUB_SCAN_BYTES
        ]
        inspected_papers = recent_papers + stub_papers
        inspected_keys = recent_keys | {str(item["output_key"]) for item in stub_papers}
        canonical_after = {
            key: value for key, value in canonical.items() if key in inspected_keys
        }
        if self.should_execute:
            canonical_after.update(
                {
                    str(item["output_key"]): object()
                    for item in missing
                    if str(item["output_key"]) in recent_keys
                    and str(item["output_key"]) not in remaining_paths
                }
            )
        semantic_records = self._semantic_records(inspected_papers, canonical_after)
        semantic_invalid_existing = sum(
            result == "invalid" for result in semantic_records.values()
        )
        semantic_evidence_unavailable = sum(
            result == "unavailable" for result in semantic_records.values()
        )
        status_paths = [
            f"_jobs/status/{entry_paper_key(item)}.json" for item in remaining
        ]
        automatic_repairs = not self.retry_only and not self.fresh
        if getattr(self, "repair_invalid_limit", 0) or automatic_repairs:
            status_paths.extend(
                f"_jobs/status/{entry_paper_key(item)}.json"
                for item in inspected_papers
                if semantic_records.get(str(item["output_key"])) == "invalid"
            )
        status_records = self._status_records(status_paths)
        missing_versions = {
            f"_jobs/status/{entry_paper_key(item)}.json": str(item["version"])
            for item in remaining
        }
        dispositions = {
            path: status_disposition(
                payload,
                canonical_missing=path in missing_versions,
                requested_version=missing_versions.get(path),
            )
            for path, payload in status_records.items()
        }
        fresh_keys = self._fresh_paper_keys()
        left_to_fresh_lane = 0
        candidates = []
        for item in remaining:
            status_path = f"_jobs/status/{entry_paper_key(item)}.json"
            disposition = dispositions.get(status_path)
            if entry_paper_key(item) in fresh_keys:
                left_to_fresh_lane += 1
                continue
            if disposition is None or disposition == "retryable_due":
                candidates.append({**item, "retry": disposition == "retryable_due"})
        missing_candidate_count = len(candidates)
        repair_limit = getattr(self, "repair_invalid_limit", 0)
        # New papers keep arriving inside the live window, which the live lane
        # owns, so only older missing work holds back full-lane repairs.
        blocking_missing = [
            item
            for item in candidates
            if not self.full or str(item["output_key"]) not in recent_keys
        ]
        if automatic_repairs and not blocking_missing and not repair_limit:
            repair_limit = LIVE_REPAIR_LIMIT
        if repair_limit:
            # Runs repair a bounded cohort after eligible missing work drains: the
            # live lane its recent window, the full lane older small objects.
            # Explicit repair runs always handle only their requested cohort.
            repairs = []
            for item in stub_papers if self.full else recent_papers:
                key = str(item["output_key"])
                if semantic_records.get(key) != "invalid":
                    continue
                disposition = dispositions.get(
                    f"_jobs/status/{entry_paper_key(item)}.json"
                )
                if disposition not in {None, "completed", "retryable_due"}:
                    continue
                path = f"hf://buckets/{self.settings.paper_markdown_hf_bucket_id}/{key}"
                with self.filesystem.open(path, "rb", block_size=0) as handle:
                    original = handle.read(64 * 1024 * 1024 + 1)
                if len(original) > 64 * 1024 * 1024:
                    continue
                try:
                    validate_canonical_markdown(
                        str(item["title"]), original.decode("utf-8")
                    )
                except ValueError:
                    repairs.append(
                        {
                            **item,
                            "retry": disposition == "retryable_due",
                            "replace_invalid_sha256": hashlib.sha256(
                                original
                            ).hexdigest(),
                        }
                    )
                if len(repairs) >= repair_limit:
                    break
            # A full run with nothing to repair keeps its live-window missing work.
            if repairs or not self.full:
                candidates = repairs
        layout_missing = 0
        if not getattr(self, "repair_invalid_limit", 0):
            # Canonical OCR above writes layout too; the rest only lacks layout.
            # The full lane leaves the recent window to the live lane.
            has_canonical = set(canonical)
            if self.should_execute:
                has_canonical |= {
                    str(item["output_key"]) for item in missing
                } - remaining_paths
            queued = {entry_paper_key(item) for item in candidates}
            layout_scope = [
                item
                for item in papers
                if str(item["output_key"]) in has_canonical
                and entry_paper_key(item) not in queued
                and entry_paper_key(item) not in fresh_keys
                and semantic_records.get(str(item["output_key"])) != "invalid"
                and not (self.full and str(item["output_key"]) in recent_keys)
            ]
            layout_capacity = self.profile.concurrency * self.profile.max_papers
            layout_candidates, layout_missing = self._layout_candidates(
                layout_scope, limit=max(0, layout_capacity - len(candidates))
            )
            candidates.extend(layout_candidates)
        if self.retry_only:
            candidates = [item for item in candidates if item["retry"]]
        failed_or_completed = max(
            0, len(remaining) - missing_candidate_count - left_to_fresh_lane
        )
        repair_candidates = sum(
            bool(item.get("replace_invalid_sha256")) for item in candidates
        )
        layout_only_candidates = sum(
            bool(item.get("layout_only")) for item in candidates
        )
        copied_from_upstream = upstream_available if self.should_execute else 0
        canonical_after_upstream = len(canonical) + copied_from_upstream
        usable_markdown = max(
            0,
            canonical_after_upstream
            - semantic_invalid_existing
            - semantic_evidence_unavailable,
        )
        coverage = {
            "observed_at": datetime.now(UTC).isoformat(),
            "scope": (
                "full"
                if self.full
                else "fresh_24_hours"
                if self.fresh
                else "recent_14_days"
            ),
            "eligible_papers": len(papers),
            "canonical_markdown_count": canonical_after_upstream,
            "usable_markdown_count": usable_markdown,
            "repair_candidates": repair_candidates,
            "semantic_invalid_existing": semantic_invalid_existing,
            "semantic_evidence_unavailable": semantic_evidence_unavailable,
            "copied_from_upstream_count": copied_from_upstream,
            "planned_upstream_copy_count": (
                0 if self.should_execute else upstream_available
            ),
            "missing_count": len(remaining),
            "layout_missing_count": layout_missing,
            "coverage_percentage": round(usable_markdown / len(papers) * 100, 2)
            if papers
            else 100.0,
        }
        if additional_active_job_ids:
            launched = self._launch(
                candidates, additional_active_job_ids=additional_active_job_ids
            )
        else:
            launched = self._launch(candidates)
        # After OCR dispatch, so a web-page failure cannot hold up PDF papers.
        external_pages = (
            {}
            if self.retry_only or self.fresh or getattr(self, "repair_invalid_limit", 0)
            else self._prepare_external_pages()
        )
        retryable_due = sum(
            disposition == "retryable_due" for disposition in dispositions.values()
        )
        retryable_deferred = sum(
            disposition == "retryable_deferred" for disposition in dispositions.values()
        )
        permanent_failures = sum(
            disposition == "permanent_failure" for disposition in dispositions.values()
        )
        attempts_exhausted = sum(
            disposition == "attempts_exhausted" for disposition in dispositions.values()
        )
        semantic_validation_failures = sum(
            payload.get("error_class") == "semantic_markdown_mismatch"
            for payload in status_records.values()
        )
        coverage.update(
            {
                "retryable_due": retryable_due,
                "retryable_deferred": retryable_deferred,
                "permanent_failures": permanent_failures,
                "attempts_exhausted": attempts_exhausted,
                "semantic_validation_failures": semantic_validation_failures,
                "retryable_papers_blocked_by_budget": (
                    self.retryable_papers_blocked_by_budget
                ),
                "paid_authorization_required": self.paid_authorization_required,
                "selected_profile": self.profile.as_dict(),
            }
        )
        # Coverage history tracks the hourly scopes; a 5-minute lane would
        # only add noise to it.
        if not self.fresh:
            append_coverage_history(coverage)
        metrics = {
            "mode": self.mode,
            "lane": "fresh" if self.fresh else self.mode,
            "left_to_fresh_lane": left_to_fresh_lane,
            "execute": self.should_execute,
            "eligible_papers": len(papers),
            "canonical_markdown": len(canonical),
            "canonical_markdown_after_upstream": canonical_after_upstream,
            "usable_markdown": usable_markdown,
            "repair_candidates": repair_candidates,
            "semantic_invalid_existing": semantic_invalid_existing,
            "semantic_evidence_unavailable": semantic_evidence_unavailable,
            "semantic_validation_failures": semantic_validation_failures,
            "coverage_scope": coverage["scope"],
            "coverage_percentage": coverage["coverage_percentage"],
            "missing_before": len(missing),
            "upstream_available": upstream_available,
            "missing_after_upstream": len(remaining),
            "previously_attempted": failed_or_completed,
            "retryable_due": retryable_due,
            "retryable_deferred": retryable_deferred,
            "permanent_failures": permanent_failures,
            "attempts_exhausted": attempts_exhausted,
            "retryable_papers_blocked_by_budget": (
                self.retryable_papers_blocked_by_budget
            ),
            "retried_papers": sum(int(item.get("retried") or 0) for item in launched),
            "ocr_candidates": len(candidates),
            "layout_missing": layout_missing,
            "layout_only_candidates": layout_only_candidates,
            "retry_only": self.retry_only,
            "jobs_planned_or_launched": len(launched),
            "stalled_scheduling_jobs": self.stalled_scheduling_jobs,
            "desired_jobs": self.budget_desired_jobs,
            "affordable_jobs": self.budget_affordable_jobs,
            "papers_planned_or_launched": sum(int(item["papers"]) for item in launched),
            "budget_exhausted": (
                self.budget_desired_jobs > 0 and self.budget_affordable_jobs == 0
            ),
            "budget_projected_usd": self.budget_projected_usd,
            "budget_ceiling_usd": self.budget_ceiling_usd,
            "paid_authorization_required": self.paid_authorization_required,
            "selected_profile_id": self.profile.profile_id,
            "hard_timeout_seconds": self.profile.hard_timeout_seconds,
            "soft_deadline_seconds": self.profile.soft_deadline_seconds,
            "reservation_per_job_usd": self.profile.reservation_per_job_usd,
            "hf_job_ids": ",".join(
                item["hf_job_id"] for item in launched if item.get("hf_job_id")
            )
            or "none",
            **external_pages,
        }
        self.logger.info("PAPER_MARKDOWN_SUMMARY %s", json.dumps(metrics))
        self.logger.info("Papers processed: %s", upstream_available)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument(
        "--lane",
        choices=("fresh",),
        help="fresh: OCR papers indexed in the last 24 hours on dedicated slots",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--probe-volume", action="store_true")
    parser.add_argument("--recover-mount-failures", action="store_true")
    parser.add_argument(
        "--paid-canary",
        action="store_true",
        help="authorize one explicitly confirmed measured-profile OCR canary",
    )
    parser.add_argument(
        "--retry-only",
        action="store_true",
        help="limit a reconciliation/canary to persisted retryable-due papers",
    )
    parser.add_argument(
        "--repair-invalid-limit",
        type=int,
        default=0,
        help="Repair at most this many invalid recent objects; preserve originals",
    )
    args = parser.parse_args()
    if args.repair_invalid_limit < 0 or args.repair_invalid_limit > 20:
        parser.error("--repair-invalid-limit must be between 0 and 20")
    if args.repair_invalid_limit and (
        args.full or args.retry_only or args.probe_volume or args.recover_mount_failures
    ):
        parser.error(
            "invalid-object repair must run separately from other recovery modes"
        )
    if args.lane and (
        args.full
        or args.retry_only
        or args.repair_invalid_limit
        or args.probe_volume
        or args.recover_mount_failures
    ):
        parser.error("--lane fresh runs separately from other modes")
    if args.max_jobs is not None and args.max_jobs < 1:
        parser.error("--max-jobs must be positive")
    if args.probe_volume and args.recover_mount_failures:
        parser.error(
            "--probe-volume and --recover-mount-failures are mutually exclusive"
        )
    if args.paid_canary and (args.probe_volume or args.recover_mount_failures):
        parser.error("--paid-canary is only for an OCR canary")
    job = PaperMarkdownBackfillJob(
        full=args.full,
        execute=args.execute,
        confirm=args.confirm,
        max_jobs=args.max_jobs,
        batch_size=args.batch_size,
        probe_volume=args.probe_volume,
        recover_mount_failures=args.recover_mount_failures,
        paid_canary=args.paid_canary,
        retry_only=args.retry_only,
        repair_invalid_limit=args.repair_invalid_limit,
        lane=args.lane,
    )
    raise SystemExit(0 if job.execute() else 1)


if __name__ == "__main__":
    main()
