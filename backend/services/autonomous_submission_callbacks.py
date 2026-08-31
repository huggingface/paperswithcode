"""Construction and HTTP-facing validation for scoped review callbacks."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.autonomous_submission_service import (
    AutonomousSubmissionDecision,
    AutonomousSubmissionService,
)


def submission_callback_service(
    db: Session, settings: Settings
) -> AutonomousSubmissionService:
    return AutonomousSubmissionService(
        db,
        signing_secret=settings.autonomous_submission_callback_secret.encode(),
        callback_base_url=settings.autonomous_submission_callback_base_url,
        remote_budget_usd=settings.autonomous_submission_run_budget_usd,
    )


def apply_submission_callback(
    db: Session,
    settings: Settings,
    *,
    claim_id: uuid.UUID,
    bearer_token: str,
    decision: AutonomousSubmissionDecision,
    remote_signature: str | None = None,
    remote_usage: str | None = None,
) -> None:
    if decision.claim_id != claim_id:
        raise ValueError("Callback path does not match decision scope")
    submission_callback_service(db, settings).apply_submission_decision(
        bearer_token,
        decision,
        remote_signature=remote_signature,
        remote_usage=remote_usage,
    )
