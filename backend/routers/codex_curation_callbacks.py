"""Scoped callback API used by remote Hugging Face Codex Jobs."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from huggingface_hub.errors import HfHubHTTPError
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.models.curation import (
    ApplyMutationRequest,
    CompleteJobRequest,
    CurationTraceFinalizeRequest,
    CurationTracePreapplyRequest,
    PromoteBenchmarkCandidateRequest,
)
from backend.models.curation import CurationLink as CurationLink
from backend.models.curation import EnrichPaperMutation as EnrichPaperMutation
from backend.models.evaluations import (
    EvaluationCreateRequest as EvaluationCreateRequest,
)
from backend.models.database import (
    PaperCurationJob,
    PaperCurationSchedulerState,
)
from backend.services.autonomous_capabilities import AutonomousCapabilityDenied
from backend.services.autonomous_operations_repository import RunContext
from backend.services.benchmark_gap_service import BenchmarkGapService
from backend.services.codex_add_evals_service import (
    CodexPaperJob,
    CodexPaperJobsResponse,
    codex_paper_job_service,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
    CodexCurationEnrichmentNotAllowedError,
    CodexCurationEnrichmentRequiredError,
    CodexCurationEvaluationPaperMismatchError,
    CodexCurationEvaluationsNotAllowedError,
    CodexCurationMutationClosedError,
    CodexCurationPaperNotFoundError,
)
from backend.services.curation_thumbnail_queue_service import serialize_thumbnail
from backend.services.curation_autonomy import ensure_curation_run
from backend.services.curation_trace_service import CurationTraceService
from backend.services.evaluation_service import EvaluationService
from backend.services.hf_daily_curation_service import HFDailyCurationService
from backend.services.paper_association_service import PaperAssociationService
from backend.services.paper_service import PaperService
from backend.utils.auth import require_hf_admin

router = APIRouter(prefix="/admin/codex-curation/jobs", tags=["admin"])
logger = logging.getLogger(__name__)


def _require_enabled(settings: Settings) -> None:
    if not settings.codex_jobs_enabled:
        raise HTTPException(status_code=404, detail="Not found")


def _callback_job(
    job_id: uuid.UUID,
    authorization: str | None,
    db: Session,
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing job bearer token")
    token = authorization[7:]
    row = codex_paper_job_service.authenticate(db, job_id, token)
    if row is None:
        token_owner = codex_paper_job_service.token_owner_for_other_job(
            db, job_id, token
        )
        if token_owner is not None:
            state = db.get(PaperCurationSchedulerState, 1)
            if state is None:
                state = PaperCurationSchedulerState(id=1)
                db.add(state)
            if state.paused_at is None:
                state.paused_at = datetime.now(UTC)
                state.pause_condition = "cross_paper_authorization"
                state.pause_reason = (
                    "A valid curation callback token was presented for another job"
                )
                logger.error(
                    "paper curation dispatch paused condition=cross_paper_authorization"
                )
            db.commit()
        raise HTTPException(status_code=401, detail="Invalid job bearer token")
    return row


def _service(db: Session) -> CodexCurationCallbackService:
    """Construct through router imports so existing test patch seams remain valid."""
    paper_service = PaperService(db)
    return CodexCurationCallbackService(
        db,
        job_service=codex_paper_job_service,
        evaluation_service=EvaluationService(db),
        association_service=PaperAssociationService(db, paper_service.get_paper_by_id),
    )


def _autonomous_callback_context(db: Session, row: PaperCurationJob) -> RunContext:
    context = ensure_curation_run(db, row)
    # Monitoring remains durable while a later policy check may reject writes.
    db.commit()
    return context


def _leaderboard_inventory(db: Session, query: str) -> list[dict]:
    """Compatibility seam for tests patching the legacy router helper."""
    return _service(db).leaderboard_inventory(query)


def _consume_query(db: Session, row: PaperCurationJob, field: str) -> None:
    db.refresh(row, with_for_update=True)
    value = getattr(row, field)
    if value >= 30:
        db.rollback()
        raise HTTPException(status_code=429, detail="Scoped query limit reached")
    setattr(row, field, value + 1)
    db.commit()


@router.get("", response_model=CodexPaperJobsResponse)
def list_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    trigger: str | None = Query(default=None),
    status: str | None = Query(default=None),
    policy_version: str | None = Query(default=None),
    cohort_date: date | None = Query(default=None),
    review_status: str | None = Query(default=None),
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """List the durable paper-curation queue and recent execution history."""
    _require_enabled(settings)
    if not any((trigger, status, policy_version, cohort_date, review_status)):
        return codex_paper_job_service.list_jobs(db, settings, limit=limit)
    return codex_paper_job_service.list_jobs(
        db,
        settings,
        limit=limit,
        trigger=trigger,
        status=status,
        policy_version=policy_version,
        cohort_date=cohort_date,
        review_status=review_status,
    )


@router.post("/benchmark-candidates/{candidate_id}/promote")
def promote_benchmark_candidate(
    candidate_id: uuid.UUID,
    body: PromoteBenchmarkCandidateRequest,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Promote one reviewed gap and queue targeted evidence-paper rechecks."""
    _require_enabled(settings)
    try:
        return BenchmarkGapService(db).promote_and_enqueue(
            candidate_id=candidate_id,
            dataset_id=body.dataset_id,
            task_id=body.task_id,
            best_metric=body.best_metric,
            settings=settings,
            job_service=codex_paper_job_service,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{job_id}/retry", response_model=CodexPaperJob)
def retry_job(
    job_id: uuid.UUID,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = db.get(PaperCurationJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return codex_paper_job_service.retry(db, row, settings)


@router.post("/{job_id}/retry-trace")
def retry_trace_upload(
    job_id: uuid.UUID,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = db.get(PaperCurationJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if row.trace_status != "finalize_failed":
        raise HTTPException(
            status_code=409, detail="Trace is not awaiting finalization"
        )
    try:
        return CurationTraceService(db, settings).retry_finalize(row)
    except (ValueError, RuntimeError, HfHubHTTPError, OSError) as error:
        row.trace_attempt_count += 1
        db.commit()
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/{job_id}/trace")
def get_trace_manifest(
    job_id: uuid.UUID,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = db.get(PaperCurationJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        return CurationTraceService(db, settings).read_manifest(row)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.delete("/{job_id}", response_model=CodexPaperJob)
def cancel_job(
    job_id: uuid.UUID,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = db.get(PaperCurationJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return codex_paper_job_service.cancel(db, row, settings)


@router.post("/scheduler/{action}")
def scheduler_action(
    action: str,
    _admin: dict = Depends(require_hf_admin),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    service = HFDailyCurationService(db, settings)
    if action == "resume":
        return service.set_dispatch(True)
    if action == "pause":
        return service.set_dispatch(False, reason="paused from admin dashboard")
    raise HTTPException(status_code=404, detail="Unknown scheduler action")


@router.get("/{job_id}/context")
def get_context(
    job_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    try:
        return _service(db).context(row, settings)
    except CodexCurationPaperNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{job_id}/bootstrap")
def bootstrap_job(
    job_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Serve an allowlisted worktree bound to the active immutable release."""
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    try:
        return codex_paper_job_service.bootstrap_bundle(row)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{job_id}/taxonomy")
def search_taxonomy(
    job_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=120),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    _consume_query(db, row, "taxonomy_query_count")
    return _service(db).search_taxonomy(q)


@router.get("/{job_id}/leaderboards")
def search_leaderboards(
    job_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=120),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    """Search only existing, fully configured leaderboards for a scoped worker."""
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    _consume_query(db, row, "leaderboard_query_count")
    return {"query": q, "leaderboards": _leaderboard_inventory(db, q)}


@router.post("/{job_id}/apply")
def apply_mutation(
    job_id: uuid.UUID,
    body: ApplyMutationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    try:
        service = _service(db)
        context = (
            _autonomous_callback_context(db, row)
            if getattr(row, "trigger", "admin") != "admin"
            else None
        )
        if context is not None and not settings.codex_curation_direct_apply_enabled:
            service.authorize_autonomous_callback(row, body, context=context)
        if (
            getattr(row, "trigger", "admin") != "admin"
            and not settings.codex_curation_direct_apply_enabled
        ):
            service._validate_mutation(row, body)
            validation = service._validate_scheduled_policy(row, body)
            row.proposal = body.model_dump(mode="json")
            row.validation_summary = {**validation, "mode": "shadow"}
            row.mutation_result = {
                "status": "shadow",
                "evaluations_created": 0,
                "evaluations_updated": 0,
            }
            row.submitted_at = datetime.now(UTC)
            db.commit()
            return {
                "status": "shadow",
                "evaluations_created": 0,
                "evaluations_updated": 0,
            }
        return service.apply(row, body, autonomous_context=context)
    except CodexCurationMutationClosedError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CodexCurationEnrichmentNotAllowedError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CodexCurationEvaluationPaperMismatchError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except CodexCurationEvaluationsNotAllowedError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CodexCurationEnrichmentRequiredError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AutonomousCapabilityDenied as error:
        db.rollback()
        raise HTTPException(status_code=423, detail=str(error)) from error
    except (LookupError, RuntimeError, ValueError) as error:
        if getattr(row, "kind", None) == "resolve-model-paper" or isinstance(
            error, ValueError
        ):
            raise HTTPException(status_code=422, detail=str(error)) from error
        raise


@router.post("/{job_id}/trace/preapply")
def store_preapply_trace(
    job_id: uuid.UUID,
    body: CurationTracePreapplyRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    if row.status not in {"dispatching", "running"} or row.submitted_at is not None:
        raise HTTPException(
            status_code=409, detail="Job no longer accepts trace preflight"
        )
    try:
        return CurationTraceService(db, settings).preapply(
            row,
            proposal=body.proposal,
            events_gzip_b64=body.events_gzip_b64,
            prompt=body.prompt,
            url_candidates=body.url_candidates,
        )
    except (ValueError, RuntimeError, HfHubHTTPError, OSError) as error:
        row.trace_status = "preapply_failed"
        row.trace_attempt_count += 1
        state = db.get(PaperCurationSchedulerState, 1)
        if state and row.trigger != "admin":
            state.consecutive_trace_failures += 1
            if state.consecutive_trace_failures >= 3:
                state.paused_at = datetime.now(UTC)
                state.pause_condition = "trace_upload_failures"
                state.pause_reason = "Three consecutive scheduled trace uploads failed"
                logger.error(
                    "paper curation dispatch paused condition=trace_upload_failures"
                )
        db.commit()
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/{job_id}/trace/finalize")
def finalize_trace(
    job_id: uuid.UUID,
    body: CurationTraceFinalizeRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    try:
        return CurationTraceService(db, settings).finalize(row, body.model_dump())
    except (ValueError, RuntimeError, HfHubHTTPError, OSError) as error:
        row.trace_status = "finalize_failed"
        row.trace_attempt_count += 1
        state = db.get(PaperCurationSchedulerState, 1)
        if state and row.trigger != "admin":
            state.consecutive_trace_failures += 1
            if state.consecutive_trace_failures >= 3:
                state.paused_at = datetime.now(UTC)
                state.pause_condition = "trace_upload_failures"
                state.pause_reason = "Three consecutive scheduled trace uploads failed"
                logger.error(
                    "paper curation dispatch paused condition=trace_upload_failures"
                )
        db.commit()
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/{job_id}/thumbnail")
def get_thumbnail_status(
    job_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    return {"thumbnail": serialize_thumbnail(row)}


@router.post("/{job_id}/complete", response_model=CodexPaperJob)
def complete_job(
    job_id: uuid.UUID,
    body: CompleteJobRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    _require_enabled(settings)
    row = _callback_job(job_id, authorization, db)
    return codex_paper_job_service.complete(
        db, row, report=body.report, error=body.error, settings=settings
    )
