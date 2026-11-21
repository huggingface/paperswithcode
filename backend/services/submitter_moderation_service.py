"""Audited submitter suspension and spam-rejection workflows."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.services.catalog_mutation_service import CatalogMutationService
from backend.services.user_profile_service import UserProfileService


@dataclass(frozen=True)
class SubmissionSuspensionResult:
    hf_subject: str
    suspended: bool


class SubmitterModerationService:
    """Own atomic, append-only-audited submitter moderation use cases."""

    def __init__(self, db: Session):
        self.db = db
        self.profiles = UserProfileService(db)

    def set_suspension(
        self,
        *,
        hf_subject: str,
        suspended: bool,
        reason: str,
        actor: dict,
        request_id: str,
    ) -> SubmissionSuspensionResult:
        after, _, _ = CatalogMutationService(self.db).mutate(
            actor=actor,
            operation="moderate",
            entity_type="submitter_moderation",
            entity_id=hf_subject,
            request_payload={"suspended": suspended, "reason": reason},
            idempotency_key=None,
            expected_version=None,
            snapshot=lambda: self.profiles.moderation_snapshot(hf_subject, lock=True),
            apply=lambda: self.profiles.suspend(
                hf_subject=hf_subject,
                suspended=suspended,
                reason=reason,
                actor=actor,
            ),
            request_id=request_id,
        )
        return SubmissionSuspensionResult(
            hf_subject=hf_subject,
            suspended=after["is_submission_suspended"],
        )

    def reject_active_as_spam(
        self,
        *,
        hf_subject: str,
        actor: dict,
        request_id: str,
    ) -> int:
        before = self.profiles.moderation_snapshot(hf_subject)
        CatalogMutationService(self.db).mutate(
            actor=actor,
            operation="moderate",
            entity_type="submitter_moderation",
            entity_id=hf_subject,
            request_payload={"reject_active_as_spam": True},
            idempotency_key=None,
            expected_version=None,
            snapshot=lambda: self.profiles.moderation_snapshot(hf_subject, lock=True),
            apply=lambda: self.profiles.reject_active_as_spam(
                hf_subject=hf_subject,
                actor=actor,
            ),
            request_id=request_id,
        )
        return sum(
            1
            for submission in before["submissions"]
            if submission["status"] == "pending"
        )
