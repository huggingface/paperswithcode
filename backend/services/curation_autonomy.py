"""Autonomous policy identity and admission for scheduled curation jobs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousRun,
    BenchmarkCurationCandidate,
    Paper,
    PaperCurationJob,
    TrendingModelCandidate,
)
from backend.services.autonomous_capabilities import (
    AutonomousCapabilityDenied,
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
    RunContext,
)
from backend.services.autonomous_policy import AutonomousPolicy


def curation_run_context(row: PaperCurationJob) -> RunContext:
    policy_version = getattr(row, "policy_version", "scheduled-v1")
    revision = sha256(policy_version.encode()).hexdigest()
    return RunContext(
        run_id=uuid.uuid5(uuid.NAMESPACE_URL, f"pwc-curation:{row.id}"),
        operator=Operator.CURATION,
        dry_run=False,
        manifest_revision=f"curation:{revision}",
    )


def ensure_curation_run(db: Session, row: PaperCurationJob) -> RunContext:
    context = curation_run_context(row)
    repository = AutonomousOperationsRepository()
    if db.get(AutonomousRun, context.run_id) is None:
        repository.append_run(
            db,
            context=context,
            status="completed",
            now=datetime.now(UTC),
        )
    else:
        repository.assert_run_context(db, context)
    return context


def authorize_curation_launch(db: Session, row: PaperCurationJob) -> RunContext:
    """Fail closed before allocating a remote scheduled-curation worker."""
    context = curation_run_context(row)
    capability, resource = curation_primary_authorization(db, row)
    decision = AutonomousPolicy().authorize_admission(db, context, capability, resource)
    if not decision.allowed:
        raise AutonomousCapabilityDenied(decision.reason_code)
    return context


def curation_primary_authorization(
    db: Session, row: PaperCurationJob
) -> tuple[Capability, ResourceRef]:
    """Resolve the job-scoped capability and primary durable resource."""
    if row.kind == "resolve-model-paper":
        candidate_id = getattr(row, "candidate_id", None)
        return (
            Capability.RESOLVE_MODEL_PAPER,
            ResourceRef(
                ResourceKind.TRENDING_MODEL_CANDIDATE,
                "missing" if candidate_id is None else str(candidate_id),
                candidate_id is not None
                and db.get(TrendingModelCandidate, candidate_id) is not None,
            ),
        )
    if row.kind == "review-benchmark-gaps":
        # The overseer's per-candidate decisions are checked again at apply.
        return (
            Capability.CREATE_BENCHMARK_FROM_GAP,
            ResourceRef(ResourceKind.BENCHMARK_CANDIDATE, "review-queue", True),
        )
    if row.kind == "add-benchmark":
        candidate_id = getattr(row, "benchmark_candidate_id", None)
        return (
            Capability.CREATE_BENCHMARK_FROM_GAP,
            ResourceRef(
                ResourceKind.BENCHMARK_CANDIDATE,
                "missing" if candidate_id is None else str(candidate_id),
                candidate_id is not None
                and db.get(BenchmarkCurationCandidate, candidate_id) is not None,
            ),
        )
    if row.kind in {"add-evals", "enrich-paper"}:
        paper_id = getattr(row, "paper_id", None)
        capability = (
            Capability.APPLY_EXISTING_LEADERBOARD_EVAL
            if row.kind == "add-evals"
            else Capability.APPLY_EXISTING_TAXONOMY_EDIT
        )
        return (
            capability,
            ResourceRef(
                ResourceKind.PAPER,
                "missing" if paper_id is None else str(paper_id),
                paper_id is not None and db.get(Paper, paper_id) is not None,
            ),
        )
    raise AutonomousCapabilityDenied("capability_not_in_manifest")
