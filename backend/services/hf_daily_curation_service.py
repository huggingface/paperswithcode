"""Idempotent rolling-cohort reconciliation for autonomous paper curation."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from huggingface_hub import HfFileSystem
from huggingface_hub.errors import HfHubHTTPError
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.curation import ApplyMutationRequest
from backend.models.database import (
    Paper,
    PaperCurationJob,
    PaperCurationSchedulerState,
    PaperCurationWorkflow,
)
from backend.services.codex_add_evals_service import (
    EXTERNAL_PAPER_POLICY_VERSION,
    CodexPaperJobService,
    codex_paper_job_service,
    deferred_workflows_for_release,
    operator_retryable,
)
from backend.services.curation_priority_service import (
    DAILY_PRIORITY,
    X_TRENDING_PRIORITY,
    has_pending_daily_papers,
    is_priority_paper,
    pending_daily_papers,
    pending_x_trending_papers,
)
from backend.services.benchmark_gap_service import BenchmarkGapService
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)
from backend.scripts.generate_missing_paper_markdown import (
    validate_canonical_markdown,
)
from backend.services.external_page_markdown_service import web_markdown_pending
from backend.utils.hf_daily_papers import fetch_hf_daily_papers
from backend.utils.urls import get_paper_route_identifier
from jobs.curation_failure_codes import AWAITING_MARKDOWN

FetchCohort = Callable[[date], list[str]]
MarkdownAvailable = Callable[[Paper, Settings], bool]
logger = logging.getLogger(__name__)
_MAX_AUTOMATIC_RETRIES = 3


class CurationRetryConflict(ValueError):
    """A newer active workflow owns the requested paper."""


def _dispatched_canary_workflows(
    workflows: list[PaperCurationWorkflow],
) -> list[PaperCurationWorkflow]:
    """Exclude durable deferred overflow from the initial canary gate."""
    return [
        workflow
        for workflow in workflows
        if workflow.deferred_reason not in {"canary_cap", "queue_cap"}
    ]


def fetch_hf_daily_cohort(cohort_date: date) -> list[str]:
    """Fetch a complete HF daily list, preserving upstream order."""
    payloads = asyncio.run(fetch_hf_daily_papers(cohort_date.isoformat()))
    return [
        arxiv_id
        for item in payloads
        if (arxiv_id := (item.get("paper") or {}).get("id"))
    ]


def paper_markdown_available(paper: Paper, settings: Settings) -> bool:
    """Require bounded canonical Markdown that satisfies the OCR semantic contract.

    An external paper is ready once its page Markdown exists or can no longer
    arrive; curation then reads the copy or the live page.
    """
    if getattr(paper, "source", None) == "external" and not paper.arxiv_id:
        return not web_markdown_pending(
            paper,
            bucket_id=settings.paper_markdown_hf_bucket_id,
            token=settings.hf_token or None,
        )
    arxiv_id = re.sub(r"v\d+$", "", paper.arxiv_id or "")
    if not arxiv_id or not settings.hf_token:
        return False
    key = f"{arxiv_id[:4]}/{arxiv_id}.md"
    path = f"hf://buckets/{settings.paper_markdown_hf_bucket_id}/{key}"
    try:
        filesystem = HfFileSystem(token=settings.hf_token)
        with filesystem.open(path, "rb", block_size=0) as handle:
            raw = handle.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            return False
        markdown = raw.decode("utf-8")
        validate_canonical_markdown(paper.title or "", markdown)
        return True
    except (HfHubHTTPError, OSError, UnicodeDecodeError, ValueError):
        return False


class HFDailyCurationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        fetch_cohort: FetchCohort = fetch_hf_daily_cohort,
        job_service: CodexPaperJobService = codex_paper_job_service,
        markdown_available: MarkdownAvailable = paper_markdown_available,
    ) -> None:
        self.db = db
        self.settings = settings
        self.fetch_cohort = fetch_cohort
        self.job_service = job_service
        self.markdown_available = markdown_available

    def retry_terminal_workflow(self, workflow: PaperCurationWorkflow) -> bool:
        """Retry one failed scheduled workflow without creating an unbounded loop."""
        attempts = (
            self.db.query(PaperCurationJob)
            .filter(
                PaperCurationJob.parent_workflow_id == workflow.id,
                PaperCurationJob.trigger == "hf-daily-cron",
                PaperCurationJob.status.in_(
                    {"dispatching", "running", "completed", "failed", "canceled"}
                ),
            )
            .order_by(PaperCurationJob.created_at.desc())
            .all()
        )
        if not attempts or any(
            attempt.status in {"dispatching", "running"} for attempt in attempts
        ):
            return False
        terminal_attempts = [
            attempt
            for attempt in attempts
            if attempt.status in {"completed", "failed", "canceled"}
        ]
        if len(terminal_attempts) >= _MAX_AUTOMATIC_RETRIES:
            return False
        self.job_service.retry(
            self.db,
            terminal_attempts[0],
            self.settings,
            priority=50,
        )
        return True

    def release_awaiting_markdown(
        self, capacity: int, *, daily_only: bool = False
    ) -> int:
        """Requeue deferred enrichment only after canonical Markdown exists."""
        if capacity <= 0:
            return 0
        query = self.db.query(PaperCurationWorkflow).filter(
            PaperCurationWorkflow.status == "deferred",
            PaperCurationWorkflow.deferred_reason == "awaiting_markdown",
        )
        if daily_only:
            query = query.join(
                Paper, Paper.id == PaperCurationWorkflow.paper_id
            ).filter(is_priority_paper())
        workflows = (
            query.order_by(
                PaperCurationWorkflow.updated_at,
                PaperCurationWorkflow.cohort_date,
                PaperCurationWorkflow.cohort_order,
                PaperCurationWorkflow.created_at,
            )
            .limit(max(100, capacity * 10))
            .all()
        )
        released = 0
        for workflow in workflows:
            if released >= capacity:
                break
            paper = self.db.get(Paper, workflow.paper_id)
            if paper is None:
                workflow.status = "failed"
                workflow.error = "Paper was deleted while awaiting Markdown"
                continue
            if not self.markdown_available(paper, self.settings):
                # Rotate checked-but-unavailable rows behind the rest of the
                # bounded scan so a large backlog cannot starve ready papers.
                workflow.updated_at = datetime.now(UTC)
                continue
            external = workflow.policy_version == EXTERNAL_PAPER_POLICY_VERSION
            enriched = workflow.enrich_satisfied_by_job_id or (
                external
                and self.db.query(PaperCurationJob.id)
                .filter(
                    PaperCurationJob.parent_workflow_id == workflow.id,
                    PaperCurationJob.kind == "enrich-paper",
                    PaperCurationJob.status == "completed",
                )
                .first()
            )
            self.job_service.enqueue(
                self.db,
                kind="add-evals" if enriched else "enrich-paper",
                paper_id=paper.id,
                paper_route=get_paper_route_identifier(
                    paper.source, paper.arxiv_id, paper.id
                ),
                paper_title=paper.title,
                # External-paper workflows stay in the admin lane.
                requested_by="external-paper-markdown-ready"
                if external
                else "hf-daily-cron-markdown-ready",
                settings=self.settings,
                trigger="admin" if external else "hf-daily-cron",
                parent_workflow_id=workflow.id,
                cohort_date=workflow.cohort_date,
                policy_version=workflow.policy_version,
                priority=50,
                dispatch=False,
                commit=False,
            )
            workflow.status = "queued"
            workflow.deferred_reason = None
            workflow.error = None
            released += 1
        return released

    def _state(self) -> PaperCurationSchedulerState:
        state = self.db.get(PaperCurationSchedulerState, 1)
        if state is None:
            state = PaperCurationSchedulerState(id=1)
            self.db.add(state)
            self.db.flush()
        return state

    def set_dispatch(self, enabled: bool, *, reason: str | None = None) -> dict:
        state = self._state()
        state.dispatch_enabled = enabled
        if enabled:
            acknowledged_at = datetime.now(UTC)
            state.paused_at = None
            state.pause_reason = None
            state.pause_condition = None
            state.acknowledged_at = acknowledged_at
            state.first_enabled_at = state.first_enabled_at or acknowledged_at
            state.consecutive_trace_failures = 0
            state.consecutive_apply_failures = 0
            logger.warning("paper curation dispatch resumed")
        else:
            state.paused_at = datetime.now(UTC)
            state.pause_reason = reason or "disabled by operator"
            state.pause_condition = "operator"
            logger.error("paper curation dispatch paused condition=operator")
        self.db.commit()
        if enabled:
            self.job_service.dispatch_next(self.db, self.settings)
        return self.status()

    def retry_scheduled_job(self, job_id: uuid.UUID) -> dict:
        """Retry one terminal scheduled stage through the shared durable queue."""
        row = self.db.get(PaperCurationJob, job_id)
        if row is None:
            raise LookupError("Curation job not found")
        if not operator_retryable(row):
            raise ValueError(
                "Only scheduled HF daily, trending, or benchmark-gap add-evals "
                "curation jobs may be retried"
            )
        if getattr(row, "parent_workflow_id", None) is not None:
            current_workflow = (
                self.db.query(PaperCurationWorkflow)
                .filter(
                    PaperCurationWorkflow.paper_id == row.paper_id,
                    PaperCurationWorkflow.id != row.parent_workflow_id,
                    PaperCurationWorkflow.status.in_({"queued", "running", "deferred"}),
                )
                .first()
            )
            if current_workflow is not None:
                raise CurationRetryConflict(
                    f"Paper {row.paper_id} has active workflow {current_workflow.id}; "
                    "continue that workflow instead of retrying its predecessor"
                )
        retry_scope = PaperCurationJob.retry_of_id == row.id
        if getattr(row, "kind", None) == "resolve-model-paper":
            retry_scope = (
                (PaperCurationJob.candidate_id == row.candidate_id)
                & (PaperCurationJob.kind == row.kind)
                & (PaperCurationJob.policy_version == row.policy_version)
            )
        active_retry = (
            self.db.query(PaperCurationJob)
            .filter(
                retry_scope,
                PaperCurationJob.status.in_({"queued", "dispatching", "running"}),
            )
            .order_by(PaperCurationJob.created_at.desc())
            .first()
        )
        if active_retry is not None:
            active_retry.priority = min(active_retry.priority, 50)
            self.db.commit()
            self.job_service.dispatch_next(self.db, self.settings)
            return self.job_service.serialize(active_retry, self.settings).model_dump(
                mode="json"
            )
        if row.status == "queued":
            row.priority = min(row.priority, 50)
            self.db.commit()
            self.job_service.dispatch_next(self.db, self.settings)
            retried = self.job_service.serialize(row, self.settings)
        else:
            retried = self.job_service.retry(
                self.db,
                row,
                self.settings,
                priority=50,
            )
        return retried.model_dump(mode="json")

    def dispatch_canary_job(self, job_id: uuid.UUID) -> dict:
        """Dispatch exactly one queued scheduled job while normal dispatch is paused."""
        row = self.db.get(PaperCurationJob, job_id)
        if row is None:
            raise LookupError("Curation job not found")
        if not operator_retryable(row):
            raise ValueError("Only scheduled curation jobs may be canary-dispatched")
        if row.status != "queued":
            raise ValueError("Canary dispatch requires a queued curation job")
        state = self.db.get(PaperCurationSchedulerState, 1)
        if state is None or state.dispatch_enabled or state.paused_at is None:
            raise ValueError("Canary dispatch requires normal dispatch to be paused")
        row = self.job_service.dispatch_canary(self.db, self.settings, row)
        return self.job_service.serialize(row, self.settings).model_dump(mode="json")

    def validator_replay(self, job_id: uuid.UUID) -> dict:
        """Run a saved proposal through current read-only policy validators."""
        row = self.db.get(PaperCurationJob, job_id)
        if row is None:
            raise LookupError("Curation job not found")
        if row.proposal is None:
            raise ValueError("Curation job has no saved proposal")
        body = ApplyMutationRequest.model_validate(row.proposal)
        replay_row = SimpleNamespace(
            id=row.id,
            kind=row.kind,
            paper_id=row.paper_id,
            trigger=row.trigger,
            status="running",
            submitted_at=None,
            applied_at=None,
            trace_status="disabled",
            url_candidates=row.url_candidates,
        )
        accepted_gaps, rejected_gaps = BenchmarkGapService(self.db).validate(
            body.benchmark_gaps,
            paper=self.db.get(Paper, row.paper_id) if body.benchmark_gaps else None,
            source_documents=(row.url_candidates or {}).get("source_documents") or [],
        )
        service = CodexCurationCallbackService(self.db)
        try:
            if rejected_gaps and row.trigger != "admin":
                details = "; ".join(
                    f"#{item['index']}: {item['error']}" for item in rejected_gaps
                )
                raise ValueError(
                    f"Scheduled benchmark gap validation failed: {details}"
                )
            service._validate_mutation(replay_row, body)
            validation = service._validate_scheduled_policy(replay_row, body)
        except (LookupError, RuntimeError, TypeError, ValueError) as exc:
            return {
                "job_id": str(row.id),
                "valid": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "benchmark_gaps_accepted": len(accepted_gaps),
                "benchmark_gaps_rejected": rejected_gaps,
            }
        return {
            "job_id": str(row.id),
            "valid": True,
            "validation": validation,
            "benchmark_gaps_accepted": len(accepted_gaps),
            "benchmark_gaps_rejected": rejected_gaps,
        }

    def status(self) -> dict:
        state = self._state()
        oldest = (
            self.db.query(func.min(PaperCurationJob.created_at))
            .filter(
                PaperCurationJob.trigger != "admin", PaperCurationJob.status == "queued"
            )
            .scalar()
        )
        return {
            "dispatch_enabled": state.dispatch_enabled,
            "paused_at": state.paused_at,
            "pause_reason": state.pause_reason,
            "pause_condition": state.pause_condition,
            "canary_released": state.canary_released,
            "oldest_scheduled_queued_at": oldest,
            "configuration": {
                "jobs_enabled": self.settings.codex_jobs_enabled,
                "scheduler_enabled": self.settings.codex_curation_scheduler_enabled,
                "direct_apply_enabled": (
                    self.settings.codex_curation_direct_apply_enabled
                ),
                "trace_upload_enabled": (
                    self.settings.codex_curation_trace_upload_enabled
                ),
                "trace_bucket_configured": bool(
                    self.settings.codex_curation_trace_hf_bucket_id
                ),
                "image": self.settings.codex_jobs_image,
                "image_revision": self.settings.codex_jobs_image_revision,
                "model": self.settings.codex_jobs_model,
                "reasoning_effort": self.settings.codex_jobs_reasoning_effort,
                "codex_cli_version": self.settings.codex_jobs_cli_version,
                "max_active": self.settings.codex_jobs_max_active,
                "max_scheduled_active": self.settings.codex_jobs_max_scheduled_active,
                "queue_depth": self.settings.codex_curation_queue_depth,
                "canary_limit": self.settings.codex_curation_canary_limit,
            },
        }

    def _enqueue_workflow(
        self, workflow: PaperCurationWorkflow, paper: Paper, *, priority: int
    ) -> None:
        queued = (
            self.db.query(PaperCurationJob)
            .filter(
                PaperCurationJob.parent_workflow_id == workflow.id,
                PaperCurationJob.status == "queued",
            )
            .first()
        )
        if queued is not None:
            queued.priority = priority
            queued.cohort_date = workflow.cohort_date
            workflow.status = "queued"
            workflow.deferred_reason = None
            return
        self.job_service.enqueue(
            self.db,
            kind="add-evals" if workflow.enrich_satisfied_by_job_id else "enrich-paper",
            paper_id=paper.id,
            paper_route=get_paper_route_identifier(
                paper.source, paper.arxiv_id, paper.id
            ),
            paper_title=paper.title,
            requested_by="hf-daily-cron",
            settings=self.settings,
            trigger="hf-daily-cron",
            parent_workflow_id=workflow.id,
            cohort_date=workflow.cohort_date,
            policy_version=workflow.policy_version,
            priority=priority,
            dispatch=False,
            commit=False,
        )
        workflow.status = "queued"
        workflow.deferred_reason = None

    def release_admin_awaiting_markdown(self) -> int:
        """Requeue parked admin paper jobs once their canonical Markdown exists.

        A parked job that a newer live, waiting, or completed admin job for the
        same paper and stage replaced is canceled instead. Each transition applies only while the row is still
        waiting, so a concurrent admin cancel is never overwritten.
        """
        released = 0
        for row in (
            self.db.query(PaperCurationJob)
            .filter(PaperCurationJob.status == AWAITING_MARKDOWN)
            .order_by(PaperCurationJob.created_at)
            .all()
        ):
            superseded = (
                self.db.query(PaperCurationJob.id)
                .filter(
                    PaperCurationJob.paper_id == row.paper_id,
                    PaperCurationJob.kind == row.kind,
                    PaperCurationJob.trigger == "admin",
                    PaperCurationJob.created_at > row.created_at,
                    PaperCurationJob.status.notin_({"failed", "canceled"}),
                )
                .first()
                is not None
            )
            if superseded:
                changes = {
                    "status": "canceled",
                    "error": "Superseded by a newer admin job for this paper.",
                }
            else:
                paper = self.db.get(Paper, row.paper_id)
                if paper is None or not self.markdown_available(paper, self.settings):
                    continue
                changes = {
                    "status": "queued",
                    "hf_job_id": None,
                    "error": None,
                    "started_at": None,
                    "finished_at": None,
                }
            updated = (
                self.db.query(PaperCurationJob)
                .filter(
                    PaperCurationJob.id == row.id,
                    PaperCurationJob.status == AWAITING_MARKDOWN,
                )
                .update(changes, synchronize_session="fetch")
            )
            released += updated if changes["status"] == "queued" else 0
        return released

    def reconcile(
        self,
        *,
        today: date | None = None,
        lookback_days: int = 7,
        paper_limit: int | None = None,
        dry_run: bool = False,
    ) -> dict:
        today = today or datetime.now(UTC).date()
        released_admin = self.release_admin_awaiting_markdown()
        if not dry_run:
            # Publish releases before the slow cohort fetch rather than holding
            # their row locks against admin cancels.
            self.db.commit()
        discovered: list[tuple[date, int, str]] = []
        seen: set[str] = set()
        for offset in range(lookback_days):
            cohort_date = today - timedelta(days=offset)
            for order, arxiv_id in enumerate(self.fetch_cohort(cohort_date)):
                if arxiv_id not in seen:
                    seen.add(arxiv_id)
                    discovered.append((cohort_date, order, arxiv_id))

        for cohort_date, _, arxiv_id in discovered:
            for paper in self.db.query(Paper).filter(Paper.arxiv_id == arxiv_id).all():
                paper.hf_daily_featured_on = max(
                    paper.hf_daily_featured_on or cohort_date, cohort_date
                )
        self.db.flush()
        # Papers trending on X are admitted ahead of the HF daily cohort.
        x_trending = [
            (shared_on, order, paper.arxiv_id)
            for order, (paper, shared_on) in enumerate(
                pending_x_trending_papers(self.db)
            )
        ]
        x_trending_ids = {arxiv_id for _, _, arxiv_id in x_trending}
        discovered = x_trending + [
            entry for entry in discovered if entry[2] not in x_trending_ids
        ]
        seen |= x_trending_ids
        for paper in pending_daily_papers(self.db).order_by(
            Paper.hf_daily_featured_on.desc(), Paper.id
        ):
            if paper.arxiv_id not in seen:
                seen.add(paper.arxiv_id)
                discovered.append((paper.hf_daily_featured_on, 0, paper.arxiv_id))

        state = self._state()
        daily_pending = has_pending_daily_papers(self.db)
        if daily_pending and state.canary_released:
            # Keep queued attempts intact, but free their admission slots. Never
            # interrupt running remote jobs or strand an active second stage.
            active_job = (
                self.db.query(PaperCurationJob.id)
                .filter(
                    PaperCurationJob.parent_workflow_id == PaperCurationWorkflow.id,
                    PaperCurationJob.status.in_({"running", "dispatching"}),
                )
                .exists()
            )
            for workflow in (
                self.db.query(PaperCurationWorkflow)
                .join(Paper, Paper.id == PaperCurationWorkflow.paper_id)
                .filter(
                    PaperCurationWorkflow.status == "queued",
                    PaperCurationWorkflow.source_candidate_id.is_(None),
                    ~is_priority_paper(),
                    ~active_job,
                )
            ):
                workflow.status = "deferred"
                workflow.deferred_reason = "queue_cap"
            self.db.flush()

        # Deferred overflow is durable backlog, not part of the initial ten
        # workflows whose terminal health decides whether that backlog may run.
        policy_workflows = (
            self.db.query(PaperCurationWorkflow)
            .filter(
                PaperCurationWorkflow.policy_version
                == self.settings.codex_curation_policy_version
            )
            .all()
        )
        existing_canary = _dispatched_canary_workflows(policy_workflows)
        if existing_canary and not state.canary_released:
            terminal = [
                item
                for item in existing_canary
                if item.status in {"completed", "satisfied", "failed", "partial"}
            ]
            if len(terminal) == len(existing_canary) and all(
                item.status in {"completed", "satisfied"} for item in terminal
            ):
                state.canary_released = True

        queue_count = (
            self.db.query(PaperCurationWorkflow)
            .filter(PaperCurationWorkflow.status.in_({"queued", "running"}))
            .count()
        )
        capacity = max(0, self.settings.codex_curation_queue_depth - queue_count)
        reconcile_limit = paper_limit or self.settings.codex_curation_reconcile_limit
        summary = {
            "discovered": len(discovered),
            "created": 0,
            "released_deferred": 0,
            "deferred": 0,
            "missing_imports": [],
            "already_satisfied": 0,
            "released_markdown_ready": 0,
            "released_admin_markdown_ready": released_admin,
            "retried": 0,
        }

        # Awaiting workflows already belong to the canary. Releasing one uses
        # queue capacity, but must not be blocked by the new-canary gate.
        markdown_ready = self.release_awaiting_markdown(
            min(capacity, reconcile_limit), daily_only=daily_pending
        )
        capacity -= markdown_ready
        reconcile_limit -= markdown_ready
        summary["released_markdown_ready"] = markdown_ready

        if state.canary_released:
            canary_capacity = capacity
        elif existing_canary:
            # Never grow the first canary cohort on a later reconciliation.
            canary_capacity = 0
        else:
            canary_capacity = self.settings.codex_curation_canary_limit
        create_capacity = min(
            capacity,
            canary_capacity,
            reconcile_limit,
        )
        admission_capacity = min(capacity, reconcile_limit)

        for cohort_date, order, arxiv_id in discovered:
            priority = (
                X_TRENDING_PRIORITY if arxiv_id in x_trending_ids else DAILY_PRIORITY
            )
            paper = (
                self.db.query(Paper)
                .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
                .one_or_none()
            )
            if paper is None:
                summary["missing_imports"].append(
                    {"arxiv_id": arxiv_id, "cohort_date": cohort_date.isoformat()}
                )
                continue
            existing = (
                self.db.query(PaperCurationWorkflow)
                .filter(PaperCurationWorkflow.paper_id == paper.id)
                .first()
            )
            if existing:
                # The live HF cohort is authoritative, including papers originally
                # queued through a conference backfill under the same policy.
                if existing.status in {"queued", "running", "deferred"}:
                    existing.cohort_date = cohort_date
                    existing.cohort_order = order
                    for job in (
                        self.db.query(PaperCurationJob)
                        .filter(
                            PaperCurationJob.parent_workflow_id == existing.id,
                            PaperCurationJob.status.in_(
                                {"queued", "dispatching", "running"}
                            ),
                        )
                        .all()
                    ):
                        job.priority = min(job.priority, priority)
                        job.cohort_date = cohort_date
                    if (
                        existing.status == "deferred"
                        and existing.deferred_reason in {"queue_cap", "canary_cap"}
                        and create_capacity > 0
                    ):
                        self._enqueue_workflow(existing, paper, priority=priority)
                        create_capacity -= 1
                        admission_capacity -= 1
                        summary["released_deferred"] += 1
                if (
                    existing.status in {"failed", "partial"}
                    and admission_capacity > 0
                    and self.retry_terminal_workflow(existing)
                ):
                    summary["retried"] += 1
                    admission_capacity -= 1
                    create_capacity = max(0, create_capacity - 1)
                continue
            admin_success = {
                kind: self.db.query(PaperCurationJob)
                .filter(
                    PaperCurationJob.paper_id == paper.id,
                    PaperCurationJob.kind == kind,
                    PaperCurationJob.trigger == "admin",
                    PaperCurationJob.status == "completed",
                )
                .order_by(PaperCurationJob.finished_at.desc())
                .first()
                for kind in ("enrich-paper", "add-evals")
            }
            status = "queued" if create_capacity > 0 else "deferred"
            workflow = PaperCurationWorkflow(
                id=uuid.uuid4(),
                paper_id=paper.id,
                cohort_date=cohort_date,
                cohort_order=order,
                policy_version=self.settings.codex_curation_policy_version,
                status=status,
                enrich_satisfied_by_job_id=admin_success["enrich-paper"].id
                if admin_success["enrich-paper"]
                else None,
                evals_satisfied_by_job_id=admin_success["add-evals"].id
                if admin_success["add-evals"]
                else None,
                deferred_reason=(
                    None
                    if status == "queued"
                    else "queue_cap"
                    if state.canary_released
                    else "canary_cap"
                ),
            )
            if all(admin_success.values()):
                workflow.status = "satisfied"
                workflow.finished_at = datetime.now(UTC)
                summary["already_satisfied"] += 1
            elif status == "deferred":
                summary["deferred"] += 1
            else:
                create_capacity -= 1
                admission_capacity -= 1
                summary["created"] += 1
            self.db.add(workflow)
            self.db.flush()
            if workflow.status == "queued":
                self._enqueue_workflow(workflow, paper, priority=priority)

        # Resume source-ready historical work too; blocked daily papers must
        # not prevent it from using capacity left after daily admission. Existing
        # awaiting-Markdown workflows may resume even before the canary opens.
        self.db.flush()
        markdown_ready = self.release_awaiting_markdown(admission_capacity)
        create_capacity = max(0, create_capacity - markdown_ready)
        summary["released_markdown_ready"] += markdown_ready

        # Only fill spare capacity with historical work after admitting today's
        # rolling HF daily cohort, including previously deferred daily papers.
        self.db.flush()
        deferred = deferred_workflows_for_release(self.db, create_capacity)
        for workflow in deferred:
            paper = self.db.get(Paper, workflow.paper_id)
            if paper is None:
                workflow.status = "failed"
                workflow.error = (
                    "Paper was deleted before deferred curation could start"
                )
                continue
            self._enqueue_workflow(workflow, paper, priority=100)
            create_capacity -= 1
            summary["released_deferred"] += 1

        if dry_run:
            self.db.rollback()
            summary["dry_run"] = True
            return summary
        if (
            self.settings.codex_curation_scheduler_enabled
            and self.settings.codex_curation_direct_apply_enabled
            and state.first_enabled_at is None
        ):
            state.dispatch_enabled = True
            state.first_enabled_at = datetime.now(UTC)
        self.db.commit()
        self.job_service.dispatch_next(self.db, self.settings)
        summary["scheduler"] = self.status()
        return summary
