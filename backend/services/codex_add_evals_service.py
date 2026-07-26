"""Durable Hugging Face Jobs dispatcher for Codex paper curation."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import PaperCurationJob

JobKind = Literal["add-evals", "enrich-paper"]
JobStatus = Literal[
    "queued", "dispatching", "running", "completed", "failed", "canceled"
]
ACTIVE_STATUSES = {"dispatching", "running"}
TERMINAL_STATUSES = {"completed", "failed", "canceled"}
CURATOR_BOOTSTRAP_COMMAND = """set -eu
apt-get update
apt-get install -y --no-install-recommends curl git python3 ca-certificates
rm -rf /var/lib/apt/lists/*
ln -sf /usr/bin/python3 /usr/local/bin/python
npm install --global @openai/codex
curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" "https://raw.githubusercontent.com/huggingface/paperswithcode/${PWC_GIT_SHA}/jobs/run_paper_curation.py" -o /tmp/run_paper_curation.py
python3 /tmp/run_paper_curation.py
"""


class CodexPaperJob(BaseModel):
    id: uuid.UUID
    paper_id: int
    paper_route: str
    paper_title: str
    requested_by: str
    kind: JobKind
    status: JobStatus
    hf_job_id: str | None = None
    hf_job_url: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    applied_at: datetime | None = None
    report: str | None = None
    error: str | None = None
    attempt_count: int


class CodexPaperJobCounts(BaseModel):
    total: int = 0
    queued: int = 0
    dispatching: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    canceled: int = 0


class CodexPaperJobsResponse(BaseModel):
    timestamp: datetime
    jobs: list[CodexPaperJob]
    summary: CodexPaperJobCounts


def _now() -> datetime:
    return datetime.now(UTC)


def _launch_error(exc: Exception) -> str:
    """Keep the useful Hub response without leaking request credentials."""
    if isinstance(exc, HfHubHTTPError):
        detail = getattr(exc, "server_message", None) or str(exc)
        detail = " ".join(detail.split())
        return f"Could not launch Hugging Face Job: {detail[:1_000]}"
    return f"Could not launch Hugging Face Job ({type(exc).__name__})."


def _release_git_revision(root: Path) -> str | None:
    try:
        manifest = json.loads((root / "release.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    revision = manifest.get("git_sha")
    return revision if isinstance(revision, str) and len(revision) == 40 else None


def _git_revision() -> str:
    configured_revision = os.getenv("PWC_CODEX_JOBS_GIT_SHA", "").strip()
    if configured_revision:
        return configured_revision
    root = Path(__file__).parents[2]
    release_revision = _release_git_revision(root)
    if release_revision:
        return release_revision
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=root
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "HEAD"


class CodexPaperJobService:
    """Persist, launch, reconcile, and authenticate one shared remote worker."""

    def __init__(self, hf_api: HfApi | None = None) -> None:
        self._hf_api = hf_api

    def _api(self, settings: Settings) -> HfApi:
        return self._hf_api or HfApi(token=settings.codex_jobs_token)

    @staticmethod
    def _serialize(row: PaperCurationJob, settings: Settings) -> CodexPaperJob:
        return CodexPaperJob(
            id=row.id,
            paper_id=int(row.paper_id),
            paper_route=row.paper_route,
            paper_title=row.paper_title,
            requested_by=row.requested_by,
            kind=row.kind,
            status=row.status,
            hf_job_id=row.hf_job_id,
            hf_job_url=(
                f"https://huggingface.co/jobs/{settings.codex_jobs_namespace}/{row.hf_job_id}"
                if row.hf_job_id
                else None
            ),
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            applied_at=row.applied_at,
            report=row.report,
            error=row.error,
            attempt_count=row.attempt_count,
        )

    def enqueue(
        self,
        db: Session,
        *,
        kind: JobKind,
        paper_id: int,
        paper_route: str,
        paper_title: str,
        requested_by: str,
        settings: Settings,
    ) -> CodexPaperJob:
        row = PaperCurationJob(
            id=uuid.uuid4(),
            kind=kind,
            paper_id=paper_id,
            paper_route=paper_route,
            paper_title=paper_title,
            requested_by=requested_by,
            status="queued",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        self.dispatch_next(db, settings)
        db.refresh(row)
        return self._serialize(row, settings)

    def dispatch_next(self, db: Session, settings: Settings) -> None:
        """Launch exactly one queued Job when no remote curation Job is active."""
        if not settings.codex_jobs_enabled:
            return
        if (
            db.query(PaperCurationJob)
            .filter(PaperCurationJob.status.in_(ACTIVE_STATUSES))
            .first()
        ):
            return
        row = (
            db.query(PaperCurationJob)
            .filter(PaperCurationJob.status == "queued")
            .order_by(PaperCurationJob.created_at, PaperCurationJob.id)
            .first()
        )
        if row is None:
            return
        if (
            not settings.codex_jobs_namespace
            or not settings.codex_jobs_token
            or not settings.codex_jobs_openai_api_key
        ):
            row.status = "failed"
            row.error = "Hugging Face Jobs namespace or credentials are not configured."
            row.finished_at = _now()
            db.commit()
            return

        callback_token = secrets.token_urlsafe(32)
        row.status = "dispatching"
        row.callback_token_hash = hashlib.sha256(callback_token.encode()).hexdigest()
        row.attempt_count += 1
        db.commit()
        try:
            remote = self._api(settings).run_job(
                image=settings.codex_jobs_image,
                command=["bash", "-lc", CURATOR_BOOTSTRAP_COMMAND],
                env={
                    "PWC_CURATION_API_URL": settings.codex_jobs_api_url.rstrip("/"),
                    "PWC_CURATION_JOB_ID": str(row.id),
                    "PWC_CURATION_KIND": row.kind,
                    "PWC_GIT_SHA": _git_revision(),
                },
                secrets={
                    "PWC_CURATION_JOB_TOKEN": callback_token,
                    "OPENAI_API_KEY": settings.codex_jobs_openai_api_key,
                    "GITHUB_TOKEN": settings.github_token,
                },
                flavor="cpu-basic",
                timeout=f"{settings.codex_jobs_timeout_seconds}s",
                labels={
                    "product": "paperswithcode",
                    "workflow": "paper-curation",
                    "pwc_job_id": str(row.id),
                    "paper_id": str(row.paper_id),
                    "kind": row.kind,
                },
                namespace=settings.codex_jobs_namespace,
            )
            row.hf_job_id = str(remote.id)
            row.status = "running"
            row.started_at = _now()
            db.commit()
        except Exception as exc:
            row.status = "failed"
            row.error = _launch_error(exc)
            row.finished_at = _now()
            db.commit()

    def get(
        self, db: Session, job_id: uuid.UUID, settings: Settings
    ) -> CodexPaperJob | None:
        self.reconcile(db, settings)
        row = db.get(PaperCurationJob, job_id)
        return self._serialize(row, settings) if row else None

    def list_jobs(
        self, db: Session, settings: Settings, *, limit: int = 100
    ) -> CodexPaperJobsResponse:
        """Return recent curation history plus counts for the full durable queue."""
        self.reconcile(db, settings)
        rows = (
            db.query(PaperCurationJob)
            .order_by(PaperCurationJob.created_at.desc(), PaperCurationJob.id.desc())
            .limit(limit)
            .all()
        )
        counts = CodexPaperJobCounts()
        for job_status, count in (
            db.query(PaperCurationJob.status, func.count(PaperCurationJob.id))
            .group_by(PaperCurationJob.status)
            .all()
        ):
            setattr(counts, job_status, int(count))
            counts.total += int(count)
        return CodexPaperJobsResponse(
            timestamp=_now(),
            jobs=[self._serialize(row, settings) for row in rows],
            summary=counts,
        )

    def reconcile(self, db: Session, settings: Settings) -> None:
        """Mark finished remote Jobs that failed to call back, then advance FIFO."""
        active = (
            db.query(PaperCurationJob)
            .filter(PaperCurationJob.status.in_(ACTIVE_STATUSES))
            .all()
        )
        if (
            not active
            or not settings.codex_jobs_enabled
            or not settings.codex_jobs_token
        ):
            return
        remote_jobs = {
            str(job.id): job
            for job in self._api(settings).list_jobs(
                namespace=settings.codex_jobs_namespace
            )
        }
        changed = False
        for row in active:
            remote = remote_jobs.get(row.hf_job_id or "")
            stage = str(getattr(getattr(remote, "status", None), "stage", ""))
            if stage in {"ERROR", "DELETED", "COMPLETED"}:
                row.status = "failed"
                row.error = (
                    "Hugging Face Job completed without submitting a result."
                    if stage == "COMPLETED"
                    else f"Hugging Face Job ended with {stage.lower()}."
                )
                row.finished_at = _now()
                changed = True
            elif stage == "CANCELED":
                row.status = "canceled"
                row.finished_at = _now()
                changed = True
        if changed:
            db.commit()
            self.dispatch_next(db, settings)

    def authenticate(
        self, db: Session, job_id: uuid.UUID, token: str
    ) -> PaperCurationJob | None:
        row = db.get(PaperCurationJob, job_id)
        if row is None or not row.callback_token_hash:
            return None
        candidate = hashlib.sha256(token.encode()).hexdigest()
        return (
            row if secrets.compare_digest(candidate, row.callback_token_hash) else None
        )

    def complete(
        self,
        db: Session,
        row: PaperCurationJob,
        *,
        report: str,
        error: str | None,
        settings: Settings,
    ) -> CodexPaperJob:
        if row.status in TERMINAL_STATUSES:
            return self._serialize(row, settings)
        row.status = "failed" if error else "completed"
        row.report = report[:40_000] or None
        row.error = error[:4_000] if error else None
        row.finished_at = _now()
        db.commit()
        self.dispatch_next(db, settings)
        return self._serialize(row, settings)

    def cancel(
        self, db: Session, row: PaperCurationJob, settings: Settings
    ) -> CodexPaperJob:
        if row.status in TERMINAL_STATUSES:
            return self._serialize(row, settings)
        if row.hf_job_id and settings.codex_jobs_token:
            self._api(settings).cancel_job(
                job_id=row.hf_job_id, namespace=settings.codex_jobs_namespace
            )
        row.status = "canceled"
        row.finished_at = _now()
        db.commit()
        self.dispatch_next(db, settings)
        return self._serialize(row, settings)


codex_paper_job_service = CodexPaperJobService()
# Compatibility exports while callers migrate to the single service.
codex_add_evals_service = codex_paper_job_service
codex_enrich_paper_service = codex_paper_job_service
