"""Durable Hugging Face Jobs dispatcher for Codex paper curation."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Literal

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    BenchmarkCurationCandidate,
    BenchmarkCurationEvidence,
    ModelRelease,
    ModelReleaseSignal,
    Paper,
    PaperCurationBootstrapBundle,
    PaperCurationJob,
    PaperCurationSchedulerState,
    PaperCurationWorkflow,
    TrendingModelCandidate,
)
from backend.services.curation_priority_service import is_priority_paper
from backend.services.curation_thumbnail_queue_service import (
    queue_missing_paper_thumbnail,
    serialize_thumbnail,
)
from backend.services.autonomous_capabilities import AutonomousCapabilityDenied
from backend.services.curation_autonomy import authorize_curation_launch
from backend.utils.urls import get_paper_route_identifier
from jobs.curation_failure_codes import AWAITING_MARKDOWN, parse_failure_code

logger = logging.getLogger(__name__)

JobKind = Literal[
    "add-evals",
    "enrich-paper",
    "resolve-model-paper",
    "review-benchmark-gaps",
    "add-benchmark",
]
BENCHMARK_GAP_KINDS = frozenset({"review-benchmark-gaps", "add-benchmark"})
BENCHMARK_GAP_TRIGGER = "benchmark-gap-cron"
# Release-radar resolutions share the scheduled pause, capacity, and the
# trending-model resolution lane.
RADAR_TRIGGER = "model-release-radar"
RADAR_POLICY_VERSION = "model-release-radar-v1"
# Benchmark-gap work shares the scheduled pause and capacity, but gets its own
# small lane so a constant daily backlog cannot starve it.
SCHEDULED_TRIGGERS = frozenset(
    {"hf-daily-cron", "hf-trending-cron", BENCHMARK_GAP_TRIGGER, RADAR_TRIGGER}
)
BENCHMARK_GAP_MAX_ACTIVE = 2


def operator_retryable(row: PaperCurationJob) -> bool:
    """Scheduled stages an operator may retry or canary-dispatch by job id.

    Benchmark-promotion add-evals rows re-score one paper on the scheduled
    benchmark-gap lane, so they qualify alongside daily and trending stages.
    """
    return row.trigger in {"hf-daily-cron", "hf-trending-cron"} or (
        row.trigger == BENCHMARK_GAP_TRIGGER and row.kind == "add-evals"
    )


# Health breakers that count only daily/trending paper stages. The daily
# benchmark-gap overseer is unrelated to them, so they must not hold it back.
SCHEDULED_HEALTH_PAUSES = frozenset(
    {"apply_or_verification_failures", "terminal_failure_rate"}
)
# New external papers run in the admin lane, capped so a backfill cannot take
# every worker from interactive admin and scheduled daily work.
EXTERNAL_PAPER_POLICY_VERSION = "external-paper-v1"
EXTERNAL_PAPER_MAX_ACTIVE = 2
JobStatus = Literal[
    "queued",
    "dispatching",
    "running",
    "completed",
    "failed",
    "canceled",
    "awaiting_markdown",
]
ACTIVE_STATUSES = {"dispatching", "running"}
TERMINAL_STATUSES = {"completed", "failed", "canceled"}
# Admin paper jobs that ran before any paper text existed wait here, outside the
# dispatch queue, until hourly reconciliation finds the paper's Markdown.
ADMIN_MARKDOWN_KINDS = frozenset({"add-evals", "enrich-paper"})
# Admin pages poll job status every few seconds; reconcile lists every remote
# Job in the namespace, so read paths share one call per process per interval.
READ_RECONCILE_INTERVAL_SECONDS = 30.0
CURATOR_COMMAND = "exec python3 /runner/run_paper_curation.py"
CURATION_DISPATCH_LOCK_ID = 0x50574344
CURATOR_BOOTSTRAP_PATHS = (
    ".agents/skills/add-evals/SKILL.md",
    ".agents/skills/enrich-paper/SKILL.md",
    ".agents/skills/remote-paper-curation/SKILL.md",
    ".agents/skills/resolve-model-paper/SKILL.md",
    "jobs/curation_api.py",
    "jobs/curation_failure_codes.py",
    "jobs/schemas/curation_proposal.schema.json",
    "jobs/url_preflight.py",
)


class CanaryDispatchFailed(RuntimeError):
    """The selected canary did not reach the accepted remote-running state."""


@contextmanager
def curation_dispatch_lock(db: Session) -> Iterator[None]:
    """Serialize every curation capacity decision on PostgreSQL."""
    get_bind = getattr(db, "get_bind", None)
    bind = get_bind() if get_bind is not None else None
    if bind is None or bind.dialect.name != "postgresql":
        yield
        return
    engine = getattr(bind, "engine", bind)
    with engine.connect() as connection:
        connection.execute(select(func.pg_advisory_lock(CURATION_DISPATCH_LOCK_ID)))
        try:
            yield
        finally:
            connection.execute(
                select(func.pg_advisory_unlock(CURATION_DISPATCH_LOCK_ID))
            )


class CodexPaperJob(BaseModel):
    id: uuid.UUID
    paper_id: int | None
    candidate_id: uuid.UUID | None = None
    benchmark_candidate_id: uuid.UUID | None = None
    release_signal_id: uuid.UUID | None = None
    paper_route: str | None
    paper_title: str | None
    requested_by: str
    kind: JobKind
    status: JobStatus
    hf_job_id: str | None = None
    hf_job_url: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    submitted_at: datetime | None = None
    applied_at: datetime | None = None
    report: str | None = None
    error: str | None = None
    attempt_count: int
    thumbnail: dict | None = None
    parent_workflow_id: uuid.UUID | None = None
    trigger: str = "admin"
    cohort_date: date | None = None
    policy_version: str = "admin-v1"
    priority: int = 100
    repository_sha: str | None = None
    skill_sha256: str | None = None
    prompt_sha256: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    codex_cli_version: str | None = None
    trace_status: str = "pending"
    trace_uri: str | None = None
    trace_sha256: str | None = None
    proposal: dict | None = None
    validation_summary: dict | None = None
    mutation_result: dict | None = None
    url_candidates: dict | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    audit_status: str = "unreviewed"


class CodexPaperJobCounts(BaseModel):
    total: int = 0
    queued: int = 0
    dispatching: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    canceled: int = 0
    awaiting_markdown: int = 0


class CodexPaperJobsResponse(BaseModel):
    timestamp: datetime
    jobs: list[CodexPaperJob]
    summary: CodexPaperJobCounts
    workflows: list[dict] = Field(default_factory=list)
    benchmark_candidates: list[dict] = Field(default_factory=list)
    scheduler: dict = Field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(UTC)


def _is_callback_validation_rejection(row: PaperCurationJob) -> bool:
    return (getattr(row, "validation_summary", None) or {}).get("status") == "rejected"


# The runner's generic failure for a callback that never got a response: the
# HF Job could not reach the site, which says nothing about the curation itself.
_TRANSPORT_FAILURE = re.compile(
    r"^Remote runner failed \((URLError|RemoteDisconnected|TimeoutError|"
    r"ConnectionResetError|IncompleteRead)\)\.$"
)


def _is_transport_failure(error: str | None) -> bool:
    return _TRANSPORT_FAILURE.match(error or "") is not None


def _is_source_evidence_failure(error: str | None) -> bool:
    if parse_failure_code(error) == AWAITING_MARKDOWN:
        return True
    lowered = (error or "").lower()
    return any(
        value in lowered
        for value in ("source evidence", "insufficient evidence", "unavailable source")
    )


def _curator_skill_digest(kind: JobKind) -> str:
    root = Path(__file__).parents[2]
    skill_name = (
        "resolve-model-paper"
        if kind == "resolve-model-paper"
        else "enrich-paper"
        if kind == "enrich-paper"
        else "add-evals"
    )
    paths = [
        root / ".agents/skills/remote-paper-curation/SKILL.md",
        root / f".agents/skills/{skill_name}/SKILL.md",
    ]
    return hashlib.sha256(b"\0".join(path.read_bytes() for path in paths)).hexdigest()


def _curator_bootstrap_bundle(revision: str) -> dict:
    root = Path(__file__).parents[2]
    files = []
    for relative in CURATOR_BOOTSTRAP_PATHS:
        content = (root / relative).read_bytes()
        files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
                "content_b64": base64.b64encode(content).decode(),
            }
        )
    return {"revision": revision, "files": files}


def _bootstrap_bundle_key(bundle: dict) -> str:
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _store_bootstrap_bundle(db: Session, revision: str) -> str | None:
    """Store the release's bootstrap snapshot once and return its content key."""
    if len(revision) != 40:
        return None
    bundle = _curator_bootstrap_bundle(revision)
    key = _bootstrap_bundle_key(bundle)
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            pg_insert(PaperCurationBootstrapBundle)
            .values(sha256=key, bundle=bundle)
            .on_conflict_do_nothing()
        )
    elif db.get(PaperCurationBootstrapBundle, key) is None:
        db.add(PaperCurationBootstrapBundle(sha256=key, bundle=bundle))
        db.flush()
    return key


def _persisted_bootstrap_bundle(row: PaperCurationJob) -> dict | None:
    if row.bootstrap_bundle_sha256 is None:
        return None
    bundle = row.stored_bootstrap_bundle.bundle
    if _bootstrap_bundle_key(bundle) != row.bootstrap_bundle_sha256:
        raise ValueError("Persisted bootstrap bundle does not match its key")
    return bundle


def _validated_bootstrap_bundle(row: PaperCurationJob, bundle: dict) -> dict:
    if not isinstance(bundle, dict) or bundle.get("revision") != row.repository_sha:
        raise ValueError("Persisted bootstrap revision does not match the job")
    files = bundle.get("files")
    if not isinstance(files, list) or len(files) != len(CURATOR_BOOTSTRAP_PATHS):
        raise ValueError("Persisted bootstrap file allowlist is incomplete")
    if {item.get("path") for item in files if isinstance(item, dict)} != set(
        CURATOR_BOOTSTRAP_PATHS
    ):
        raise ValueError("Persisted bootstrap file allowlist is incomplete")
    for item in files:
        try:
            content = base64.b64decode(item["content_b64"], validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Persisted bootstrap content is invalid") from exc
        if hashlib.sha256(content).hexdigest() != item.get("sha256"):
            raise ValueError("Persisted bootstrap hash mismatch")
    return bundle


def deferred_workflows_for_release(
    db: Session,
    limit: int,
    *,
    policy_version: str | None = None,
) -> list[PaperCurationWorkflow]:
    """Release one starved workflow, then fill remaining capacity newest-first."""
    if limit <= 0:
        return []
    query = db.query(PaperCurationWorkflow).filter(
        PaperCurationWorkflow.status == "deferred",
        PaperCurationWorkflow.deferred_reason.in_({"canary_cap", "queue_cap"}),
    )
    if policy_version is not None:
        query = query.filter(PaperCurationWorkflow.policy_version == policy_version)
    overdue = (
        query.filter(PaperCurationWorkflow.created_at < _now() - timedelta(hours=24))
        .order_by(
            PaperCurationWorkflow.created_at,
            PaperCurationWorkflow.cohort_date,
            PaperCurationWorkflow.cohort_order,
            PaperCurationWorkflow.id,
        )
        .first()
    )
    selected = [overdue] if overdue is not None else []
    newest = query
    if overdue is not None:
        newest = newest.filter(PaperCurationWorkflow.id != overdue.id)
    selected.extend(
        newest.order_by(
            PaperCurationWorkflow.cohort_date.desc(),
            PaperCurationWorkflow.cohort_order,
            PaperCurationWorkflow.created_at,
            PaperCurationWorkflow.id,
        )
        .limit(limit - len(selected))
        .all()
    )
    return selected


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
        self._read_reconcile_lock = threading.Lock()
        self._last_read_reconcile = float("-inf")

    def _api(self, settings: Settings) -> HfApi:
        return self._hf_api or HfApi(token=settings.codex_jobs_token)

    @staticmethod
    def serialize(row: PaperCurationJob, settings: Settings) -> CodexPaperJob:
        return CodexPaperJob(
            id=row.id,
            paper_id=int(row.paper_id) if row.paper_id is not None else None,
            candidate_id=getattr(row, "candidate_id", None),
            benchmark_candidate_id=getattr(row, "benchmark_candidate_id", None),
            release_signal_id=getattr(row, "release_signal_id", None),
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
            submitted_at=getattr(row, "submitted_at", None),
            applied_at=row.applied_at,
            report=row.report,
            error=row.error,
            attempt_count=row.attempt_count,
            thumbnail=(
                serialize_thumbnail(row)
                if getattr(row, "thumbnail_requested_at", None) is not None
                else None
            ),
            parent_workflow_id=getattr(row, "parent_workflow_id", None),
            trigger=getattr(row, "trigger", "admin"),
            cohort_date=getattr(row, "cohort_date", None),
            policy_version=getattr(row, "policy_version", "admin-v1"),
            priority=getattr(row, "priority", 100),
            repository_sha=getattr(row, "repository_sha", None),
            skill_sha256=getattr(row, "skill_sha256", None),
            prompt_sha256=getattr(row, "prompt_sha256", None),
            model=getattr(row, "model", None),
            reasoning_effort=getattr(row, "reasoning_effort", None),
            codex_cli_version=getattr(row, "codex_cli_version", None),
            trace_status=getattr(row, "trace_status", "pending"),
            trace_uri=getattr(row, "trace_uri", None),
            trace_sha256=getattr(row, "trace_sha256", None),
            proposal=getattr(row, "proposal", None),
            validation_summary=getattr(row, "validation_summary", None),
            mutation_result=getattr(row, "mutation_result", None),
            url_candidates=getattr(row, "url_candidates", None),
            input_tokens=getattr(row, "input_tokens", None),
            output_tokens=getattr(row, "output_tokens", None),
            duration_ms=getattr(row, "duration_ms", None),
            audit_status=getattr(row, "audit_status", "unreviewed"),
        )

    # Compatibility name for callers and tests that predate the public serializer.
    _serialize = serialize

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
        trigger: str = "admin",
        parent_workflow_id: uuid.UUID | None = None,
        cohort_date=None,
        policy_version: str | None = None,
        priority: int | None = None,
        dispatch: bool = True,
        retry_of_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> CodexPaperJob:
        repository_sha = _git_revision()
        bootstrap_bundle_sha256 = _store_bootstrap_bundle(db, repository_sha)
        row = PaperCurationJob(
            id=uuid.uuid4(),
            kind=kind,
            paper_id=paper_id,
            paper_route=paper_route,
            paper_title=paper_title,
            requested_by=requested_by,
            status="queued",
            trigger=trigger,
            parent_workflow_id=parent_workflow_id,
            cohort_date=cohort_date,
            policy_version=policy_version
            or (
                settings.codex_curation_policy_version
                if trigger != "admin"
                else "admin-v1"
            ),
            priority=priority
            if priority is not None
            else (0 if trigger == "admin" else 100),
            repository_sha=repository_sha if len(repository_sha) == 40 else None,
            skill_sha256=_curator_skill_digest(kind),
            bootstrap_bundle_sha256=bootstrap_bundle_sha256,
            model=settings.codex_jobs_model,
            reasoning_effort=settings.codex_jobs_reasoning_effort,
            codex_cli_version=settings.codex_jobs_cli_version,
            validator_version="scheduled-policy-v1",
            retry_of_id=retry_of_id,
        )
        db.add(row)
        db.flush()
        if trigger in {"hf-daily-cron", "hf-trending-cron"}:
            queue_missing_paper_thumbnail(db, row, db.get(Paper, paper_id))
        if commit:
            db.commit()
            db.refresh(row)
        if dispatch:
            self.dispatch_next(db, settings)
        if commit:
            db.refresh(row)
        return self.serialize(row, settings)

    def enqueue_resolution(
        self,
        db: Session,
        *,
        candidate: TrendingModelCandidate,
        requested_by: str,
        settings: Settings,
        dispatch: bool = True,
        commit: bool = True,
        retry_of_id: uuid.UUID | None = None,
    ) -> CodexPaperJob:
        repository_sha = _git_revision()
        row = PaperCurationJob(
            id=uuid.uuid4(),
            kind="resolve-model-paper",
            paper_id=None,
            candidate_id=candidate.id,
            paper_route=None,
            paper_title=None,
            requested_by=requested_by,
            status="queued",
            trigger="hf-trending-cron",
            cohort_date=_now().date(),
            policy_version="hf-trending-v1",
            priority=25,
            repository_sha=repository_sha if len(repository_sha) == 40 else None,
            skill_sha256=_curator_skill_digest("resolve-model-paper"),
            bootstrap_bundle_sha256=_store_bootstrap_bundle(db, repository_sha),
            model=settings.codex_jobs_model,
            reasoning_effort=settings.codex_jobs_reasoning_effort,
            codex_cli_version=settings.codex_jobs_cli_version,
            validator_version="trending-model-policy-v1",
            retry_of_id=retry_of_id,
        )
        candidate.status = "queued"
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
        if dispatch:
            self.dispatch_next(db, settings)
        if commit:
            db.refresh(row)
        return self.serialize(row, settings)

    def enqueue_signal_resolution(
        self,
        db: Session,
        *,
        signal: ModelReleaseSignal,
        requested_by: str,
        settings: Settings,
        dispatch: bool = True,
        commit: bool = True,
        retry_of_id: uuid.UUID | None = None,
    ) -> CodexPaperJob:
        """Queue one release-radar signal for paper resolution."""
        repository_sha = _git_revision()
        row = PaperCurationJob(
            id=uuid.uuid4(),
            kind="resolve-model-paper",
            paper_id=None,
            release_signal_id=signal.id,
            paper_route=None,
            paper_title=None,
            requested_by=requested_by,
            status="queued",
            trigger=RADAR_TRIGGER,
            cohort_date=_now().date(),
            policy_version=RADAR_POLICY_VERSION,
            priority=25,
            repository_sha=repository_sha if len(repository_sha) == 40 else None,
            skill_sha256=_curator_skill_digest("resolve-model-paper"),
            bootstrap_bundle_sha256=_store_bootstrap_bundle(db, repository_sha),
            model=settings.codex_jobs_model,
            reasoning_effort=settings.codex_jobs_reasoning_effort,
            codex_cli_version=settings.codex_jobs_cli_version,
            validator_version="release-radar-policy-v1",
            retry_of_id=retry_of_id,
        )
        signal.status = "queued"
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
        if dispatch:
            self.dispatch_next(db, settings)
        if commit:
            db.refresh(row)
        return self.serialize(row, settings)

    def enqueue_benchmark_job(
        self,
        db: Session,
        *,
        kind: JobKind,
        benchmark_candidate_id: uuid.UUID | None,
        requested_by: str,
        settings: Settings,
        priority: int,
        retry_of_id: uuid.UUID | None = None,
    ) -> PaperCurationJob:
        """Add one unscoped review or candidate-scoped creation job (no commit)."""
        if kind not in BENCHMARK_GAP_KINDS:
            raise ValueError(f"{kind} is not a benchmark-gap job kind")
        repository_sha = _git_revision()
        row = PaperCurationJob(
            id=uuid.uuid4(),
            kind=kind,
            paper_id=None,
            benchmark_candidate_id=benchmark_candidate_id,
            paper_route=None,
            paper_title=None,
            requested_by=requested_by,
            status="queued",
            trigger=BENCHMARK_GAP_TRIGGER,
            cohort_date=_now().date(),
            policy_version="benchmark-gap-v1",
            priority=priority,
            repository_sha=repository_sha if len(repository_sha) == 40 else None,
            skill_sha256=_curator_skill_digest(kind),
            bootstrap_bundle_sha256=_store_bootstrap_bundle(db, repository_sha),
            model=settings.codex_jobs_model,
            reasoning_effort=settings.codex_jobs_reasoning_effort,
            codex_cli_version=settings.codex_jobs_cli_version,
            validator_version="benchmark-gap-policy-v1",
            retry_of_id=retry_of_id,
        )
        db.add(row)
        db.flush()
        return row

    def enqueue_resolved_candidate_workflow(
        self,
        db: Session,
        candidate: TrendingModelCandidate,
        settings: Settings,
        *,
        dispatch: bool = True,
        commit: bool = True,
    ) -> bool:
        """Start the standard enrich -> add-evals workflow for one resolved card."""
        if dispatch and not commit:
            raise ValueError("Dispatch requires a committed workflow")
        if candidate.status != "resolved" or candidate.model_release_id is None:
            return False
        revision = candidate.readme_revision or candidate.readme_sha
        existing = (
            db.query(PaperCurationWorkflow)
            .filter(
                PaperCurationWorkflow.source_candidate_id == candidate.id,
                PaperCurationWorkflow.source_revision == revision,
                PaperCurationWorkflow.policy_version == "hf-trending-v1",
            )
            .first()
        )
        if existing is not None:
            return False
        release = db.get(ModelRelease, candidate.model_release_id)
        if release is None or release.paper_id is None:
            return False
        active = (
            db.query(PaperCurationWorkflow)
            .filter(
                PaperCurationWorkflow.paper_id == release.paper_id,
                PaperCurationWorkflow.status.in_({"queued", "running", "deferred"}),
            )
            .first()
        )
        if active is not None:
            return False
        paper = db.get(Paper, release.paper_id)
        if paper is None:
            return False
        workflow = PaperCurationWorkflow(
            id=uuid.uuid4(),
            paper_id=paper.id,
            source_candidate_id=candidate.id,
            source_revision=revision,
            cohort_date=_now().date(),
            cohort_order=0,
            policy_version="hf-trending-v1",
            status="queued",
        )
        db.add(workflow)
        db.flush()
        self.enqueue(
            db,
            kind="enrich-paper",
            paper_id=paper.id,
            paper_route=get_paper_route_identifier(
                paper.source, paper.arxiv_id, paper.id
            ),
            paper_title=paper.title,
            requested_by="hf-trending-cron",
            settings=settings,
            trigger="hf-trending-cron",
            parent_workflow_id=workflow.id,
            cohort_date=workflow.cohort_date,
            policy_version=workflow.policy_version,
            priority=25,
            dispatch=False,
            commit=False,
        )
        if commit:
            db.commit()
        if dispatch:
            self.dispatch_next(db, settings)
        return True

    def dispatch_next(self, db: Session, settings: Settings) -> None:
        """Fill configured shared capacity while reserving one slot for admin work."""
        if not settings.codex_jobs_enabled:
            return
        with curation_dispatch_lock(db):
            self._dispatch_next_locked(db, settings)

    def _dispatch_next_locked(self, db: Session, settings: Settings) -> None:
        while True:
            active = (
                db.query(PaperCurationJob)
                .filter(PaperCurationJob.status.in_(ACTIVE_STATUSES))
                .all()
            )
            if len(active) >= settings.codex_jobs_max_active:
                return
            scheduled_active = sum(
                item.trigger in SCHEDULED_TRIGGERS for item in active
            )
            benchmark_gap_active = sum(
                item.trigger == BENCHMARK_GAP_TRIGGER for item in active
            )
            scheduler_state = db.get(PaperCurationSchedulerState, 1)
            usage_allowed = self._scheduled_usage_allowed(db, scheduler_state)
            scheduled_allowed = bool(
                settings.codex_curation_scheduler_enabled
                and scheduler_state
                and scheduler_state.dispatch_enabled
                and scheduler_state.paused_at is None
                and usage_allowed
                and scheduled_active < settings.codex_jobs_max_scheduled_active
            )
            admin_rows = db.query(PaperCurationJob).filter(
                PaperCurationJob.status == "queued",
                PaperCurationJob.trigger.in_({"admin", "benchmark-promotion"}),
            )
            external_active = sum(
                getattr(item, "policy_version", None) == EXTERNAL_PAPER_POLICY_VERSION
                for item in active
            )
            if external_active >= EXTERNAL_PAPER_MAX_ACTIVE:
                admin_rows = admin_rows.filter(
                    PaperCurationJob.policy_version != EXTERNAL_PAPER_POLICY_VERSION
                )
            row = admin_rows.order_by(
                PaperCurationJob.priority,
                PaperCurationJob.created_at,
                PaperCurationJob.id,
            ).first()
            if row is None and self._benchmark_review_allowed(
                settings, scheduler_state, usage_allowed
            ):
                # The one daily overseer takes any free slot, ahead of the
                # benchmark-gap lane cap and the daily-paper health breakers.
                row = self._next_benchmark_gap_row(db, kind="review-benchmark-gaps")
            if (
                row is None
                and scheduled_allowed
                and benchmark_gap_active < BENCHMARK_GAP_MAX_ACTIVE
            ):
                row = self._next_benchmark_gap_row(db)
            if row is None and scheduled_allowed:
                row = self._next_scheduled_row(db)
            if row is None:
                return
            self._dispatch_row(db, settings, row)
            if row.status == "failed":
                continue

    def dispatch_canary(
        self, db: Session, settings: Settings, row: PaperCurationJob
    ) -> PaperCurationJob:
        """Dispatch one selected scheduled row without resuming the scheduler."""
        if not settings.codex_jobs_enabled:
            raise RuntimeError("Codex Jobs are disabled")
        if not settings.codex_curation_scheduler_enabled:
            raise RuntimeError("Scheduled curation is disabled")
        with curation_dispatch_lock(db):
            return self._dispatch_canary_locked(db, settings, row)

    def _dispatch_canary_locked(
        self, db: Session, settings: Settings, row: PaperCurationJob
    ) -> PaperCurationJob:
        get_bind = getattr(db, "get_bind", None)
        bind = get_bind() if get_bind is not None else None
        if bind is not None and bind.dialect.name == "postgresql":
            db.refresh(row, with_for_update=True)
        if not operator_retryable(row):
            raise ValueError("Only scheduled curation jobs may be canary-dispatched")
        if row.status != "queued":
            raise ValueError("Canary dispatch requires a queued curation job")
        state = db.get(PaperCurationSchedulerState, 1)
        if (
            state is None
            or state.dispatch_enabled
            or state.paused_at is None
            or state.pause_condition != "operator"
        ):
            raise RuntimeError("Canary dispatch requires an explicit operator pause")
        if not self._scheduled_usage_allowed(db, state):
            raise RuntimeError("Canary dispatch is blocked by the token guardrail")
        active = (
            db.query(PaperCurationJob)
            .filter(PaperCurationJob.status.in_(ACTIVE_STATUSES))
            .all()
        )
        if len(active) >= settings.codex_jobs_max_active:
            raise RuntimeError("No Codex Job capacity is available")
        if row.trigger == BENCHMARK_GAP_TRIGGER:
            lane_active = sum(item.trigger == BENCHMARK_GAP_TRIGGER for item in active)
            lane_limit = BENCHMARK_GAP_MAX_ACTIVE
        else:
            lane_active = sum(
                item.trigger in {"hf-daily-cron", "hf-trending-cron"} for item in active
            )
            lane_limit = settings.codex_jobs_max_scheduled_active
        if lane_active >= lane_limit:
            raise RuntimeError("No scheduled curation capacity is available")
        self._dispatch_row(db, settings, row)
        if row.status != "running" or not row.hf_job_id:
            raise CanaryDispatchFailed(
                f"Canary job did not launch (terminal status: {row.status})"
            )
        return row

    @staticmethod
    def _next_trending_row(db: Session) -> PaperCurationJob | None:
        return (
            db.query(PaperCurationJob)
            .filter(
                PaperCurationJob.trigger.in_({"hf-trending-cron", RADAR_TRIGGER}),
                PaperCurationJob.status == "queued",
            )
            .order_by(
                PaperCurationJob.priority,
                PaperCurationJob.created_at,
                PaperCurationJob.id,
            )
            .first()
        )

    @staticmethod
    def _benchmark_review_allowed(
        settings: Settings,
        state: PaperCurationSchedulerState | None,
        usage_allowed: bool,
    ) -> bool:
        return bool(
            settings.codex_curation_scheduler_enabled
            and state
            and state.dispatch_enabled
            and (
                state.paused_at is None
                or state.pause_condition in SCHEDULED_HEALTH_PAUSES
            )
            and usage_allowed
        )

    @staticmethod
    def _next_benchmark_gap_row(
        db: Session, kind: str | None = None
    ) -> PaperCurationJob | None:
        query = db.query(PaperCurationJob).filter(
            PaperCurationJob.trigger == BENCHMARK_GAP_TRIGGER,
            PaperCurationJob.status == "queued",
        )
        if kind is not None:
            query = query.filter(PaperCurationJob.kind == kind)
        return query.order_by(
            PaperCurationJob.priority,
            PaperCurationJob.created_at,
            PaperCurationJob.id,
        ).first()

    @staticmethod
    def _next_scheduled_row(db: Session) -> PaperCurationJob | None:
        """Choose ready daily and X-trending work first, then keep workers busy."""
        daily = (
            db.query(PaperCurationJob)
            .join(Paper, Paper.id == PaperCurationJob.paper_id)
            .join(
                PaperCurationWorkflow,
                PaperCurationWorkflow.id == PaperCurationJob.parent_workflow_id,
            )
            .filter(
                is_priority_paper(),
                PaperCurationJob.trigger.in_({"hf-daily-cron", "hf-trending-cron"}),
                PaperCurationJob.status == "queued",
                PaperCurationWorkflow.status.in_({"queued", "running"}),
            )
            .order_by(
                PaperCurationJob.priority,
                Paper.hf_daily_featured_on.desc().nullslast(),
                PaperCurationJob.created_at,
                PaperCurationJob.id,
            )
            .first()
        )
        if daily is not None:
            return daily
        cutoff = _now() - timedelta(hours=24)
        overdue_active = (
            db.query(PaperCurationJob.id)
            .join(
                PaperCurationWorkflow,
                PaperCurationWorkflow.id == PaperCurationJob.parent_workflow_id,
            )
            .filter(
                PaperCurationJob.trigger.in_({"hf-daily-cron", "hf-trending-cron"}),
                PaperCurationJob.status.in_(ACTIVE_STATUSES),
                PaperCurationWorkflow.created_at < cutoff,
            )
            .first()
        )
        base = (
            db.query(PaperCurationJob)
            .join(
                PaperCurationWorkflow,
                PaperCurationWorkflow.id == PaperCurationJob.parent_workflow_id,
            )
            .filter(
                PaperCurationJob.trigger.in_({"hf-daily-cron", "hf-trending-cron"}),
                PaperCurationJob.status == "queued",
                PaperCurationWorkflow.status.in_({"queued", "running"}),
            )
        )
        if overdue_active is None:
            overdue = (
                base.filter(PaperCurationWorkflow.created_at < cutoff)
                .order_by(
                    PaperCurationWorkflow.created_at,
                    PaperCurationWorkflow.cohort_order,
                    PaperCurationJob.created_at,
                    PaperCurationJob.id,
                )
                .first()
            )
            if overdue is not None:
                return overdue
        trending = CodexPaperJobService._next_trending_row(db)
        if trending is not None:
            return trending
        return base.order_by(
            PaperCurationJob.priority,
            PaperCurationJob.cohort_date.desc().nullslast(),
            PaperCurationWorkflow.cohort_order,
            PaperCurationJob.created_at,
            PaperCurationJob.id,
        ).first()

    @staticmethod
    def _scheduled_usage_snapshot(
        db: Session, state: PaperCurationSchedulerState | None
    ) -> dict:
        now = _now()
        # Only the three summed columns: a full-row load pulled ~1,300 completed
        # jobs with their bootstrap bundles into memory on every dispatch.
        rows = (
            db.query(
                PaperCurationJob.finished_at,
                PaperCurationJob.input_tokens,
                PaperCurationJob.output_tokens,
            )
            .filter(
                PaperCurationJob.trigger.in_({"hf-daily-cron", "hf-trending-cron"}),
                PaperCurationJob.status == "completed",
                PaperCurationJob.finished_at >= now - timedelta(days=8),
            )
            .all()
        )
        totals = {now.date() - timedelta(days=offset): 0 for offset in range(8)}
        for row in rows:
            if row.finished_at and row.finished_at.date() in totals:
                totals[row.finished_at.date()] += (row.input_tokens or 0) + (
                    row.output_tokens or 0
                )
        positive_baseline = [
            tokens
            for offset in range(1, 8)
            if (tokens := totals[now.date() - timedelta(days=offset)]) > 0
        ]
        baseline = median(positive_baseline) if positive_baseline else 0
        baseline_active = bool(
            state
            and state.first_enabled_at
            and state.first_enabled_at <= now - timedelta(days=7)
            and len(positive_baseline) >= 3
        )
        threshold = int(2 * baseline) if baseline_active and baseline > 0 else None
        return {
            "mode": "enforced" if baseline_active else "baseline_alert_only",
            "current_day_tokens": int(totals[now.date()]),
            "trailing_seven_day_median_tokens": int(baseline),
            "positive_baseline_days": len(positive_baseline),
            "pause_threshold_tokens": threshold,
        }

    @classmethod
    def _scheduled_usage_allowed(
        cls, db: Session, state: PaperCurationSchedulerState | None
    ) -> bool:
        if state is None or state.first_enabled_at is None:
            return True
        usage = cls._scheduled_usage_snapshot(db, state)
        threshold = usage["pause_threshold_tokens"]
        now = _now()
        if (
            state.dispatch_enabled
            and state.pause_condition == "daily_token_guardrail"
            and state.paused_at is not None
            and state.paused_at.astimezone(UTC).date() < now.date()
            and threshold is not None
            and usage["current_day_tokens"] <= threshold
        ):
            state.paused_at = None
            state.pause_condition = None
            state.pause_reason = None
            db.commit()
            logger.info("paper curation daily token pause expired after UTC rollover")
        if threshold is not None and usage["current_day_tokens"] > threshold:
            # A usage observation must never replace an operator/security pause.
            if state.pause_condition not in {None, "daily_token_guardrail"}:
                return False
            state.paused_at = now
            state.pause_condition = "daily_token_guardrail"
            state.pause_reason = (
                "Scheduled token usage exceeded twice the trailing seven-day median"
            )
            db.commit()
            logger.error(
                "paper curation dispatch paused condition=daily_token_guardrail"
            )
            return False
        return True

    def _dispatch_row(
        self, db: Session, settings: Settings, row: PaperCurationJob
    ) -> None:
        if getattr(row, "trigger", "admin") in SCHEDULED_TRIGGERS:
            try:
                authorize_curation_launch(db, row)
            except AutonomousCapabilityDenied as error:
                state = db.get(PaperCurationSchedulerState, 1)
                if state is not None:
                    state.paused_at = _now()
                    state.pause_condition = "autonomous_policy_denied"
                    reason = str(error)
                    state.pause_reason = (
                        "Scheduled curation operator is disabled"
                        if reason == "operator_disabled"
                        else f"Scheduled curation authorization denied: {reason}"
                    )
                db.commit()
                logger.error(
                    "paper curation dispatch paused condition=autonomous_policy_denied reason=%s",
                    error,
                )
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

        try:
            self._bind_active_release(db, row, settings)
            callback_token = secrets.token_urlsafe(32)
            row.status = "dispatching"
            row.callback_token_hash = hashlib.sha256(
                callback_token.encode()
            ).hexdigest()
            row.attempt_count += 1
            if row.kind == "resolve-model-paper" and row.candidate_id is not None:
                candidate = db.get(TrendingModelCandidate, row.candidate_id)
                if candidate is not None:
                    candidate.status = "resolving"
            signal = self._release_signal(db, row)
            if signal is not None:
                signal.status = "resolving"
            db.commit()
            image = self._verified_job_image(db, settings, row)
            image_name = image.rsplit("/", 1)[-1]
            if (
                not image.startswith("hf.co/spaces/")
                and "@sha256:" not in image
                and ":" not in image_name
            ):
                image = f"{image}:{row.repository_sha or _git_revision()}"
            remote = self._run_job_with_retry(
                settings=settings,
                row=row,
                callback_token=callback_token,
                image=image,
            )
            row.hf_job_id = str(remote.id)
            row.status = "running"
            row.started_at = _now()
            db.commit()
        except Exception as exc:
            row.status = "failed"
            row.error = _launch_error(exc)
            row.finished_at = _now()
            if row.kind == "resolve-model-paper" and row.candidate_id is not None:
                candidate = db.get(TrendingModelCandidate, row.candidate_id)
                if candidate is not None:
                    candidate.status = "failed"
                    candidate.rejection_reason = row.error
                    candidate.processed_at = _now()
            self._fail_release_signal(db, row)
            self._advance_workflow(db, row, settings)
            db.commit()

    @staticmethod
    def _bind_active_release(
        db: Session, row: PaperCurationJob, settings: Settings
    ) -> None:
        """Bind an unstarted queue row to the release that will serve bootstrap."""
        revision = _git_revision()
        if len(revision) != 40:
            raise RuntimeError("Active curation release revision is unavailable")
        if row.repository_sha == revision:
            return
        previous = row.repository_sha
        row.repository_sha = revision
        row.skill_sha256 = _curator_skill_digest(row.kind)
        row.bootstrap_bundle_sha256 = _store_bootstrap_bundle(db, revision)
        row.model = settings.codex_jobs_model
        row.reasoning_effort = settings.codex_jobs_reasoning_effort
        row.codex_cli_version = settings.codex_jobs_cli_version
        row.validator_version = "scheduled-policy-v1"
        logger.info(
            "rebound queued curation job %s from release %s to %s",
            row.id,
            previous,
            revision,
        )

    def _verified_job_image(
        self, db: Session, settings: Settings, row: PaperCurationJob
    ) -> str:
        if not settings.codex_jobs_image:
            raise RuntimeError("Curator image is not configured (PWC_CODEX_JOBS_IMAGE)")
        image = settings.codex_jobs_image.replace(
            "{sha}", row.repository_sha or _git_revision()
        )
        prefix = "hf.co/spaces/"
        if not image.startswith(prefix):
            return image
        expected = settings.codex_jobs_image_revision
        if not expected:
            raise RuntimeError("Curator Space revision is not configured")
        repo_id = image.removeprefix(prefix)
        observed = None
        for attempt in range(3):
            try:
                observed = self._api(settings).space_info(repo_id=repo_id).sha
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        if observed == expected:
            return image
        if row.trigger in SCHEDULED_TRIGGERS:
            state = db.get(PaperCurationSchedulerState, 1)
            if state is not None:
                state.paused_at = _now()
                state.pause_condition = "curator_image_revision_mismatch"
                state.pause_reason = (
                    f"Curator Space revision changed from {expected} to {observed}"
                )
                db.commit()
        raise RuntimeError(
            f"Curator Space revision mismatch: expected {expected}, observed {observed}"
        )

    def _run_job_with_retry(
        self,
        *,
        settings: Settings,
        row: PaperCurationJob,
        callback_token: str,
        image: str,
    ):
        def launch():
            return self._api(settings).run_job(
                image=image,
                command=[
                    "bash",
                    "-lc",
                    f"sleep 2; {CURATOR_COMMAND}"
                    if row.retry_of_id is not None
                    else CURATOR_COMMAND,
                ],
                env={
                    "PWC_CURATION_API_URL": settings.codex_jobs_api_url.rstrip("/"),
                    "PWC_CURATION_JOB_ID": str(row.id),
                    "PWC_CURATION_KIND": row.kind,
                    "PWC_GIT_SHA": row.repository_sha or _git_revision(),
                    "PWC_CURATION_TRIGGER": row.trigger,
                    "PWC_CURATION_MODEL": row.model or settings.codex_jobs_model,
                    "PWC_CURATION_REASONING_EFFORT": row.reasoning_effort
                    or settings.codex_jobs_reasoning_effort,
                    "PWC_CODEX_CLI_VERSION": row.codex_cli_version
                    or settings.codex_jobs_cli_version,
                },
                secrets={
                    "PWC_CURATION_JOB_TOKEN": callback_token,
                    "OPENAI_API_KEY": settings.codex_jobs_openai_api_key,
                    "PWC_PAPER_MARKDOWN_HF_TOKEN": settings.hf_token,
                },
                flavor="cpu-basic",
                timeout=f"{2100 if row.kind == 'add-evals' else 1500}s",
                labels={
                    "product": "paperswithcode",
                    "workflow": "paper-curation",
                    "pwc_job_id": str(row.id),
                    "paper_id": str(row.paper_id) if row.paper_id is not None else "",
                    "candidate_id": (
                        str(row.candidate_id)
                        if getattr(row, "candidate_id", None) is not None
                        else str(row.benchmark_candidate_id)
                        if getattr(row, "benchmark_candidate_id", None) is not None
                        else str(row.release_signal_id)
                        if getattr(row, "release_signal_id", None) is not None
                        else ""
                    ),
                    "kind": row.kind,
                },
                namespace=settings.codex_jobs_namespace,
            )

        for attempt in range(3):
            try:
                return launch()
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def get(
        self, db: Session, job_id: uuid.UUID, settings: Settings
    ) -> CodexPaperJob | None:
        self.reconcile_if_due(db, settings)
        row = db.get(PaperCurationJob, job_id)
        return self.serialize(row, settings) if row else None

    def list_jobs(
        self,
        db: Session,
        settings: Settings,
        *,
        limit: int = 100,
        trigger: str | None = None,
        status: str | None = None,
        policy_version: str | None = None,
        cohort_date: date | None = None,
        review_status: str | None = None,
    ) -> CodexPaperJobsResponse:
        """Return recent curation history plus counts for the full durable queue."""
        self.reconcile_if_due(db, settings)
        query = db.query(PaperCurationJob)
        if trigger:
            query = query.filter(PaperCurationJob.trigger == trigger)
        if status:
            query = query.filter(PaperCurationJob.status == status)
        if policy_version:
            query = query.filter(PaperCurationJob.policy_version == policy_version)
        if cohort_date:
            query = query.filter(PaperCurationJob.cohort_date == cohort_date)
        if review_status:
            query = query.filter(PaperCurationJob.audit_status == review_status)
        rows = (
            query.order_by(
                PaperCurationJob.created_at.desc(), PaperCurationJob.id.desc()
            )
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
        workflow_query = db.query(PaperCurationWorkflow)
        if policy_version:
            workflow_query = workflow_query.filter(
                PaperCurationWorkflow.policy_version == policy_version
            )
        if cohort_date:
            workflow_query = workflow_query.filter(
                PaperCurationWorkflow.cohort_date == cohort_date
            )
        if status:
            workflow_query = workflow_query.filter(
                PaperCurationWorkflow.status == status
            )
        if review_status:
            workflow_query = workflow_query.filter(
                PaperCurationWorkflow.review_status == review_status
            )
        workflows = (
            workflow_query.order_by(
                PaperCurationWorkflow.created_at.desc(), PaperCurationWorkflow.id.desc()
            )
            .limit(limit)
            .all()
        )
        workflow_payload = []
        for workflow in workflows:
            jobs = sorted(
                workflow.jobs, key=lambda item: (item.created_at, str(item.id))
            )
            workflow_payload.append(
                {
                    "id": str(workflow.id),
                    "paper_id": workflow.paper_id,
                    "cohort_date": workflow.cohort_date.isoformat(),
                    "policy_version": workflow.policy_version,
                    "status": workflow.status,
                    "review_status": workflow.review_status,
                    "dependency_override": workflow.dependency_override,
                    "deferred_reason": workflow.deferred_reason,
                    "error": workflow.error,
                    "created_at": workflow.created_at.isoformat(),
                    "finished_at": workflow.finished_at.isoformat()
                    if workflow.finished_at
                    else None,
                    "stages": [
                        self.serialize(job, settings).model_dump(mode="json")
                        for job in jobs
                    ],
                }
            )
        benchmark_candidates = []
        for candidate in (
            db.query(BenchmarkCurationCandidate)
            .order_by(
                BenchmarkCurationCandidate.status,
                BenchmarkCurationCandidate.distinct_paper_count.desc(),
                BenchmarkCurationCandidate.last_seen_at.desc(),
            )
            .limit(100)
            .all()
        ):
            evidence_rows = (
                db.query(BenchmarkCurationEvidence)
                .filter(BenchmarkCurationEvidence.candidate_id == candidate.id)
                .order_by(BenchmarkCurationEvidence.created_at)
                .all()
            )
            benchmark_candidates.append(
                {
                    "id": str(candidate.id),
                    "canonical_name": candidate.canonical_name,
                    "gap_type": candidate.gap_type,
                    "canonical_url": candidate.canonical_url,
                    "task_ids": candidate.task_ids,
                    "aliases": candidate.aliases,
                    "status": candidate.status,
                    "distinct_paper_count": candidate.distinct_paper_count,
                    "confidence": candidate.confidence,
                    "first_seen_at": candidate.first_seen_at.isoformat(),
                    "last_seen_at": candidate.last_seen_at.isoformat(),
                    "promoted_at": (
                        candidate.promoted_at.isoformat()
                        if candidate.promoted_at
                        else None
                    ),
                    "review_reason": candidate.review_reason,
                    "reviewed_at": (
                        candidate.reviewed_at.isoformat()
                        if candidate.reviewed_at
                        else None
                    ),
                    "deferred_until": (
                        candidate.deferred_until.isoformat()
                        if candidate.deferred_until
                        else None
                    ),
                    "merged_into_id": (
                        str(candidate.merged_into_id)
                        if candidate.merged_into_id
                        else None
                    ),
                    "resolution": candidate.resolution,
                    "evidence_paper_ids": sorted(
                        {int(item.paper_id) for item in evidence_rows}
                    ),
                }
            )
        scheduler_state = db.get(PaperCurationSchedulerState, 1)
        scheduled_usage = self._scheduled_usage_snapshot(db, scheduler_state)
        oldest_scheduled = (
            db.query(func.min(PaperCurationJob.created_at))
            .filter(
                PaperCurationJob.trigger.in_({"hf-daily-cron", "hf-trending-cron"}),
                PaperCurationJob.status == "queued",
            )
            .scalar()
        )
        return CodexPaperJobsResponse(
            timestamp=_now(),
            jobs=[self.serialize(row, settings) for row in rows],
            summary=counts,
            workflows=workflow_payload,
            benchmark_candidates=benchmark_candidates,
            scheduler={
                "dispatch_enabled": bool(
                    scheduler_state and scheduler_state.dispatch_enabled
                ),
                "paused_at": scheduler_state.paused_at.isoformat()
                if scheduler_state and scheduler_state.paused_at
                else None,
                "pause_reason": scheduler_state.pause_reason
                if scheduler_state
                else None,
                "pause_condition": scheduler_state.pause_condition
                if scheduler_state
                else None,
                "canary_released": bool(
                    scheduler_state and scheduler_state.canary_released
                ),
                "oldest_scheduled_queued_at": oldest_scheduled.isoformat()
                if oldest_scheduled
                else None,
                "queue_age_level": (
                    "critical"
                    if oldest_scheduled
                    and oldest_scheduled < _now() - timedelta(hours=5)
                    else "warning"
                    if oldest_scheduled
                    and oldest_scheduled < _now() - timedelta(hours=3)
                    else "healthy"
                ),
                "usage": scheduled_usage,
            },
        )

    def retry(
        self,
        db: Session,
        row: PaperCurationJob,
        settings: Settings,
        *,
        priority: int | None = None,
    ) -> CodexPaperJob:
        if row.status not in TERMINAL_STATUSES:
            return self.serialize(row, settings)
        if row.parent_workflow_id is not None:
            workflow = db.get(PaperCurationWorkflow, row.parent_workflow_id)
            if workflow is not None:
                workflow.status = "running"
                workflow.error = None
                workflow.finished_at = None
                # Check workflow ownership before enqueue can commit a new job.
                db.flush()
        if row.kind in BENCHMARK_GAP_KINDS:
            retried = self.enqueue_benchmark_job(
                db,
                kind=row.kind,
                benchmark_candidate_id=row.benchmark_candidate_id,
                requested_by="admin-retry",
                settings=settings,
                priority=row.priority if priority is None else priority,
                retry_of_id=row.id,
            )
            db.commit()
        elif row.kind == "resolve-model-paper" and row.release_signal_id is not None:
            signal = db.get(ModelReleaseSignal, row.release_signal_id)
            if signal is None:
                raise LookupError("Release signal no longer exists")
            retried = self.enqueue_signal_resolution(
                db,
                signal=signal,
                requested_by="admin-retry",
                settings=settings,
                retry_of_id=row.id,
                dispatch=False,
            )
        elif row.kind == "resolve-model-paper":
            candidate = db.get(TrendingModelCandidate, row.candidate_id)
            if candidate is None:
                raise LookupError("Trending model candidate no longer exists")
            retried = self.enqueue_resolution(
                db,
                candidate=candidate,
                requested_by="admin-retry",
                settings=settings,
                retry_of_id=row.id,
                dispatch=False,
            )
        else:
            retried = self.enqueue(
                db,
                kind=row.kind,
                paper_id=row.paper_id,
                paper_route=row.paper_route,
                paper_title=row.paper_title,
                requested_by="admin-retry",
                settings=settings,
                trigger=row.trigger,
                parent_workflow_id=row.parent_workflow_id,
                cohort_date=row.cohort_date,
                policy_version=row.policy_version,
                priority=(0 if row.trigger == "admin" else row.priority)
                if priority is None
                else priority,
                retry_of_id=row.id,
                dispatch=False,
            )
        self.dispatch_next(db, settings)
        refreshed = db.get(PaperCurationJob, retried.id)
        return self.serialize(refreshed, settings)

    def reconcile_if_due(self, db: Session, settings: Settings) -> None:
        """Reconcile from polled read paths at most once per interval."""
        if (
            time.monotonic() - self._last_read_reconcile
            < READ_RECONCILE_INTERVAL_SECONDS
        ):
            return
        if not self._read_reconcile_lock.acquire(blocking=False):
            return
        try:
            self._last_read_reconcile = time.monotonic()
            self.reconcile(db, settings)
        finally:
            self._read_reconcile_lock.release()

    def reconcile(self, db: Session, settings: Settings) -> None:
        """Mark finished remote Jobs that failed to call back, then advance FIFO."""
        active = dict(
            db.execute(
                select(PaperCurationJob.id, PaperCurationJob.hf_job_id).where(
                    PaperCurationJob.status.in_(ACTIVE_STATUSES)
                )
            ).all()
        )
        if (
            not active
            or not settings.codex_jobs_enabled
            or not settings.codex_jobs_token
        ):
            return
        # Never hold a pooled connection idle in transaction across the slow
        # namespace-wide Hub call; that starved public requests on 2026-10-13.
        db.commit()
        remote_stages = {
            str(job.id): str(getattr(getattr(job, "status", None), "stage", ""))
            for job in self._api(settings).list_jobs(
                namespace=settings.codex_jobs_namespace
            )
        }
        ended_stages = {"ERROR", "DELETED", "COMPLETED", "CANCELED"}
        if not any(
            remote_stages.get(hf_job_id or "") in ended_stages
            for hf_job_id in active.values()
        ):
            return
        # Re-read: a callback may have finished a Job during the Hub call.
        changed_rows = [
            row
            for row in db.query(PaperCurationJob)
            .filter(
                PaperCurationJob.id.in_(list(active)),
                PaperCurationJob.status.in_(ACTIVE_STATUSES),
            )
            .all()
            if remote_stages.get(row.hf_job_id or "") in ended_stages
        ]
        for row in changed_rows:
            stage = remote_stages[row.hf_job_id]
            if stage == "CANCELED":
                row.status = "canceled"
            else:
                row.status = "failed"
                row.error = (
                    "Hugging Face Job completed without submitting a result."
                    if stage == "COMPLETED"
                    else f"Hugging Face Job ended with {stage.lower()}."
                )
            row.finished_at = _now()
        if changed_rows:
            for row in changed_rows:
                self._advance_workflow(db, row, settings)
            db.commit()
            self.dispatch_next(db, settings)

    def authenticate(
        self, db: Session, job_id: uuid.UUID, token: str
    ) -> PaperCurationJob | None:
        row = db.get(PaperCurationJob, job_id)
        if (
            row is None
            or not row.callback_token_hash
            or row.status in TERMINAL_STATUSES
        ):
            return None
        candidate = hashlib.sha256(token.encode()).hexdigest()
        return (
            row if secrets.compare_digest(candidate, row.callback_token_hash) else None
        )

    def bootstrap_bundle(self, row: PaperCurationJob) -> dict:
        """Return the job's hash-validated minimal curation worktree."""
        bundle = _persisted_bootstrap_bundle(row)
        if bundle is not None:
            return _validated_bootstrap_bundle(row, bundle)
        revision = _git_revision()
        if row.repository_sha != revision:
            raise ValueError("Job revision does not match the active immutable release")
        return _curator_bootstrap_bundle(revision)

    @staticmethod
    def token_owner_for_other_job(
        db: Session, job_id: uuid.UUID, token: str
    ) -> PaperCurationJob | None:
        """Identify a valid active token presented outside its one-job scope."""
        if not hasattr(db, "query"):
            return None
        candidate = hashlib.sha256(token.encode()).hexdigest()
        return (
            db.query(PaperCurationJob)
            .filter(
                PaperCurationJob.id != job_id,
                PaperCurationJob.callback_token_hash == candidate,
                PaperCurationJob.status.in_(ACTIVE_STATUSES),
            )
            .first()
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
        # Authentication may have loaded this row before another callback finished.
        # Serialize the complete transition, not just the terminal-state write.
        db.refresh(row, with_for_update=True)
        if row.status in TERMINAL_STATUSES:
            return self.serialize(row, settings)
        completion_error = error
        accepted_apply = bool(
            getattr(row, "submitted_at", None) is not None
            and getattr(row, "mutation_result", None) is not None
            and (
                (getattr(row, "validation_summary", None) or {}).get(
                    "post_write_verification"
                )
                == "passed"
                or (
                    (getattr(row, "validation_summary", None) or {}).get("mode")
                    == "shadow"
                    and (getattr(row, "mutation_result", None) or {}).get("status")
                    == "shadow"
                )
            )
        )
        if completion_error is None and not accepted_apply:
            completion_error = "Remote job completed without an accepted apply."
        thumbnail_status = getattr(row, "thumbnail_status", None)
        thumbnail_blocks_completion = (
            getattr(row, "kind", None) != "resolve-model-paper"
        )
        if (
            completion_error is None
            and thumbnail_blocks_completion
            and thumbnail_status in {"queued", "processing"}
        ):
            completion_error = (
                "Remote job completed before requested thumbnail work reached a "
                "terminal state."
            )
        if (
            completion_error is None
            and thumbnail_blocks_completion
            and thumbnail_status == "failed"
        ):
            completion_error = (
                getattr(row, "thumbnail_error", None)
                or "Requested thumbnail generation failed."
            )
        # A valid mutation is not rolled back or rerun solely because final trace
        # storage failed. Its trace remains retryable and visible to operators.
        trace_finalize_failed = bool(
            completion_error
            and completion_error.startswith("Trace finalization failed")
            and row.applied_at is not None
        )
        row.status = (
            "completed"
            if completion_error is None or trace_finalize_failed
            else "failed"
        )
        row.report = report[:40_000] or None
        row.error = completion_error[:4_000] if completion_error else None
        row.finished_at = _now()
        if self._awaits_markdown(row):
            row.status = AWAITING_MARKDOWN
            # Close the finished attempt's callbacks; release issues a new token.
            row.callback_token_hash = None
        candidate_id = getattr(row, "candidate_id", None)
        if getattr(row, "kind", None) == "resolve-model-paper" and candidate_id:
            candidate = db.get(TrendingModelCandidate, candidate_id)
            if candidate is not None:
                if row.status == "completed":
                    self.enqueue_resolved_candidate_workflow(
                        db, candidate, settings, dispatch=False, commit=False
                    )
                elif candidate.status not in {"resolved", "rejected"}:
                    candidate.status = "failed"
                    candidate.rejection_reason = row.error
                    candidate.processed_at = _now()
        if row.status != "completed":
            self._fail_release_signal(db, row)
        self._advance_workflow(db, row, settings)
        db.flush()
        self._evaluate_scheduled_health(db, row)
        # Queued jobs are the durable dispatch backlog. A dispatch failure after
        # this commit cannot strand a terminal job without its successor.
        db.commit()
        self.dispatch_next(db, settings)
        return self.serialize(row, settings)

    @staticmethod
    def _release_signal(
        db: Session, row: PaperCurationJob
    ) -> ModelReleaseSignal | None:
        signal_id = getattr(row, "release_signal_id", None)
        if getattr(row, "kind", None) != "resolve-model-paper" or signal_id is None:
            return None
        return db.get(ModelReleaseSignal, signal_id)

    @classmethod
    def _fail_release_signal(cls, db: Session, row: PaperCurationJob) -> None:
        """Mark an unresolved signal failed so a later sighting can retry it."""
        signal = cls._release_signal(db, row)
        if signal is not None and signal.status not in {"resolved", "rejected"}:
            signal.status = "failed"
            signal.rejection_reason = row.error
            signal.processed_at = _now()

    @staticmethod
    def _awaits_markdown(row: PaperCurationJob) -> bool:
        """Park a first admin attempt that found no paper text instead of failing it.

        A released attempt that still finds no text fails normally, so a paper
        whose Markdown never satisfies the runner cannot loop.
        """
        return (
            row.status == "failed"
            and parse_failure_code(row.error) == AWAITING_MARKDOWN
            and getattr(row, "trigger", "admin") == "admin"
            and getattr(row, "parent_workflow_id", None) is None
            and row.kind in ADMIN_MARKDOWN_KINDS
            and row.attempt_count == 1
        )

    def _evaluate_scheduled_health(self, db: Session, row: PaperCurationJob) -> None:
        if getattr(row, "trigger", "admin") not in {
            "hf-daily-cron",
            "hf-trending-cron",
        }:
            return
        state = db.get(PaperCurationSchedulerState, 1)
        if state is None:
            return
        uncounted = _is_source_evidence_failure(row.error) or _is_transport_failure(
            row.error
        )
        if row.status == "failed" and not uncounted:
            state.consecutive_apply_failures += 1
        elif row.status == "completed":
            state.consecutive_apply_failures = 0
        condition = None
        reason = None
        if state.consecutive_apply_failures >= 3:
            condition = "apply_or_verification_failures"
            reason = "Three consecutive scheduled apply or verification stages failed"
        recent = (
            db.query(PaperCurationJob)
            .filter(
                PaperCurationJob.trigger.in_({"hf-daily-cron", "hf-trending-cron"}),
                PaperCurationJob.status.in_({"completed", "failed"}),
                *(
                    [PaperCurationJob.finished_at > state.acknowledged_at]
                    if state.acknowledged_at is not None
                    else []
                ),
            )
            .order_by(PaperCurationJob.finished_at.desc())
            .limit(25)
            .all()
        )
        failed = [item for item in recent if item.status == "failed"]
        transport_failures = [
            item for item in failed if _is_transport_failure(item.error)
        ]
        counted_failures = [
            item
            for item in failed
            if not _is_source_evidence_failure(item.error)
            and not _is_transport_failure(item.error)
        ]
        if len(recent) == 25 and len(transport_failures) / 25 > 0.50:
            # Retried transport failures are noise, but a run of them means the
            # runners cannot reach the site at all, so this pause holds every
            # scheduled lane and takes precedence over the daily-only breakers.
            condition = "runner_transport_failures"
            reason = (
                "More than half of the latest 25 scheduled stages lost their callbacks"
            )
        elif len(recent) == 25 and len(counted_failures) / 25 > 0.20:
            condition = "terminal_failure_rate"
            reason = "More than 20% of the latest 25 scheduled stages failed"
        if condition and state.paused_at is None:
            state.paused_at = _now()
            state.pause_condition = condition
            state.pause_reason = reason
            logger.error("paper curation dispatch paused condition=%s", condition)

    def _advance_workflow(
        self, db: Session, row: PaperCurationJob, settings: Settings
    ) -> None:
        if getattr(row, "kind", None) in BENCHMARK_GAP_KINDS:
            from backend.services.benchmark_gap_review_service import (  # noqa: PLC0415
                BenchmarkGapReviewService,
            )

            BenchmarkGapReviewService(db, settings, self).handle_terminal_job(row)
            return
        if getattr(row, "parent_workflow_id", None) is None:
            return
        workflow = db.get(PaperCurationWorkflow, row.parent_workflow_id)
        if workflow is None:
            return
        if row.status == "completed" and row.kind == "enrich-paper":
            evals_done = (
                db.query(PaperCurationJob.id)
                .filter(
                    PaperCurationJob.parent_workflow_id == workflow.id,
                    PaperCurationJob.kind == "add-evals",
                    PaperCurationJob.status == "completed",
                )
                .first()
            )
            if evals_done is not None:
                # A late or admin re-run of enrich must not leave a workflow
                # open whose evaluation stage already finished; retry() reopens
                # it before the re-run starts.
                workflow.status = "completed"
                workflow.finished_at = workflow.finished_at or _now()
                return
            workflow.status = "running"
            exists = (
                db.query(PaperCurationJob)
                .filter(
                    PaperCurationJob.parent_workflow_id == workflow.id,
                    PaperCurationJob.kind == "add-evals",
                )
                .first()
            )
            if exists is None and workflow.evals_satisfied_by_job_id is None:
                self.enqueue(
                    db,
                    kind="add-evals",
                    paper_id=row.paper_id,
                    paper_route=row.paper_route,
                    paper_title=row.paper_title,
                    requested_by=row.requested_by,
                    settings=settings,
                    trigger=row.trigger,
                    parent_workflow_id=workflow.id,
                    cohort_date=workflow.cohort_date,
                    policy_version=workflow.policy_version,
                    priority=row.priority,
                    dispatch=False,
                    commit=False,
                )
            elif workflow.evals_satisfied_by_job_id is not None:
                workflow.status = "completed"
                workflow.finished_at = _now()
        elif row.status == "completed" and row.kind == "add-evals":
            workflow.status = "completed"
            workflow.finished_at = _now()
            # External-paper workflows are not part of any scheduled canary.
            if workflow.policy_version != EXTERNAL_PAPER_POLICY_VERSION:
                self._release_canary_backlog(db, workflow.policy_version, settings)
        elif row.status == "failed":
            if parse_failure_code(row.error) == AWAITING_MARKDOWN:
                workflow.status = "deferred"
                workflow.deferred_reason = "awaiting_markdown"
                workflow.error = None
                workflow.finished_at = None
                return
            if (
                row.retry_of_id is None
                and not _is_callback_validation_rejection(row)
                and "validation" not in (row.error or "").lower()
            ):
                # Preserve every remote attempt as its own immutable job row.
                self.enqueue(
                    db,
                    kind=row.kind,
                    paper_id=row.paper_id,
                    paper_route=row.paper_route,
                    paper_title=row.paper_title,
                    requested_by="hf-daily-cron-retry",
                    settings=settings,
                    trigger=row.trigger,
                    parent_workflow_id=workflow.id,
                    cohort_date=workflow.cohort_date,
                    policy_version=workflow.policy_version,
                    priority=row.priority,
                    dispatch=False,
                    retry_of_id=row.id,
                    commit=False,
                )
                workflow.status = "running"
            else:
                workflow.status = "partial" if row.kind == "add-evals" else "failed"
                workflow.error = row.error
                workflow.finished_at = _now()
        elif row.status == "canceled":
            workflow.status = "canceled"
            workflow.error = "Canceled by an administrator"
            workflow.finished_at = _now()

    def _release_canary_backlog(
        self, db: Session, policy_version: str, settings: Settings
    ) -> None:
        # Production sessions disable autoflush. Eligibility queries must see
        # the workflow transition that triggered this release.
        db.flush()
        state = db.get(PaperCurationSchedulerState, 1)
        if state is None or state.canary_released:
            return
        canary = (
            db.query(PaperCurationWorkflow)
            .filter(
                PaperCurationWorkflow.policy_version == policy_version,
                PaperCurationWorkflow.status != "deferred",
            )
            .all()
        )
        if not canary or any(
            item.status not in {"completed", "satisfied"} for item in canary
        ):
            return
        state.canary_released = True
        nonterminal = (
            db.query(PaperCurationWorkflow)
            .filter(PaperCurationWorkflow.status.in_({"queued", "running"}))
            .count()
        )
        capacity = max(0, settings.codex_curation_queue_depth - nonterminal)
        deferred = deferred_workflows_for_release(
            db, capacity, policy_version=policy_version
        )
        for deferred_workflow in deferred:
            paper = db.get(Paper, deferred_workflow.paper_id)
            if paper is None:
                deferred_workflow.status = "failed"
                deferred_workflow.error = "Paper was deleted before canary release"
                continue
            kind = (
                "add-evals"
                if deferred_workflow.enrich_satisfied_by_job_id
                else "enrich-paper"
            )
            self.enqueue(
                db,
                kind=kind,
                paper_id=paper.id,
                paper_route=get_paper_route_identifier(
                    paper.source, paper.arxiv_id, paper.id
                ),
                paper_title=paper.title,
                requested_by="hf-daily-cron",
                settings=settings,
                trigger="hf-daily-cron",
                parent_workflow_id=deferred_workflow.id,
                cohort_date=deferred_workflow.cohort_date,
                policy_version=deferred_workflow.policy_version,
                priority=100,
                dispatch=False,
                commit=False,
            )
            deferred_workflow.status = "queued"
            deferred_workflow.deferred_reason = None

    def cancel(
        self, db: Session, row: PaperCurationJob, settings: Settings
    ) -> CodexPaperJob:
        if row.status in TERMINAL_STATUSES:
            return self.serialize(row, settings)
        if (
            row.hf_job_id
            and settings.codex_jobs_token
            and row.status != AWAITING_MARKDOWN
        ):
            self._api(settings).cancel_job(
                job_id=row.hf_job_id, namespace=settings.codex_jobs_namespace
            )
        row.status = "canceled"
        row.finished_at = _now()
        self._fail_release_signal(db, row)
        self._advance_workflow(db, row, settings)
        db.commit()
        self.dispatch_next(db, settings)
        return self.serialize(row, settings)


codex_paper_job_service = CodexPaperJobService()
# Compatibility exports while callers migrate to the single service.
codex_add_evals_service = codex_paper_job_service
codex_enrich_paper_service = codex_paper_job_service
