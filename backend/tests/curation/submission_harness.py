"""Submission service builders shared by curation and pending-edit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousRun,
    AutonomousOperatorState,
)
from backend.services.autonomous_submission_service import (
    AutonomousSubmissionService,
)


NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)


def _run(db: Session, run_id: uuid.UUID) -> None:
    if db.get(AutonomousOperatorState, "global") is None:
        db.add_all(
            [
                AutonomousOperatorState(
                    operator=operator,
                    enabled=operator == "submissions",
                    manual_mode=False,
                    revision=1,
                    updated_by="admin:test",
                    updated_at=NOW,
                )
                for operator in (
                    "global",
                    "submissions",
                    "cron_health",
                    "chat_reliability",
                )
            ]
        )
    db.add(
        AutonomousRun(
            id=run_id,
            operator="submissions",
            dry_run=False,
            manifest_revision="submission-review-v1",
            status="completed",
            capability_requests=[],
            evidence_digests=[],
            created_at=NOW,
        )
    )
    db.commit()


def _service(db: Session, *, applied=None) -> AutonomousSubmissionService:
    return AutonomousSubmissionService(
        db,
        signing_secret=b"test-signing-secret-with-sufficient-entropy",
        callback_base_url="https://paperswithcode.co/api/v1",
        clock=lambda: NOW,
        decision_applier=applied,
        remote_budget_usd=Decimal("5"),
    )
