"""Submission and review orchestration for non-admin catalog edits."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import (
    Author,
    CatalogMutationEvent,
    Paper,
    PaperAuthor,
    PendingPaperEdit,
)
from backend.services.catalog_mutation_service import json_safe
from backend.services.autonomous_capabilities import (
    HUMAN_ONLY_EDIT_TYPES,
    AutonomousCapabilityDenied,
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_operations_repository import RunContext
from backend.services.autonomous_policy import AutonomousPolicy
from backend.services.pending_edit_auto_approval import (
    AUTO_EDIT_TYPES,
    AUTO_REVIEWER,
    AutoApprovalPolicy,
)
from backend.services.pending_edit_errors import (
    PendingEditAlreadyReviewedError,
    PendingEditApplyError,
    PendingEditConflictError,
    PendingEditError,
    PendingEditNotFoundError,
    SubmissionRateLimitError,
    SubmissionSuspendedError,
)
from backend.services.pending_edit_transactions import review_transaction
from backend.services.pending_edit_mutations import PendingEditMutationService
from backend.services.pending_edit_payloads import (
    EDIT_TYPES,
    edit_spec,
    payload_is_noop,
    validate_payload,
)
from backend.services.pending_edit_snapshots import PendingEditSnapshotService
from backend.services.user_profile_service import UserProfileError, UserProfileService
from backend.utils.exceptions import PaperNotFoundError

STATUSES = frozenset({"pending", "approved", "rejected"})

# Human-only suggestions whose approval only records the decision; admins
# create the entity separately. Approving an organization suggestion creates it.
RECORD_ONLY_EDIT_TYPES = HUMAN_ONLY_EDIT_TYPES - {"new_organization"}

logger = logging.getLogger(__name__)

MEMBERSHIP_EDIT_FIELDS = {
    "tasks": ("tasks", "task_ids"),
    "methods": ("methods", "method_ids"),
}


def _conflict_snapshot(edit_type: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Exclude automatically recalculated ranks from evaluation conflicts."""
    if edit_type != "evaluations":
        return snapshot
    return {
        **snapshot,
        "evaluations": [
            {key: value for key, value in evaluation.items() if key != "best_rank"}
            for evaluation in snapshot.get("evaluations", [])
        ],
    }


def _rebase_membership_payload(
    edit_type: str,
    submitted_snapshot: dict[str, Any],
    current_snapshot: dict[str, Any],
    proposed_payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Apply a submitted set change to newer canonical membership state."""

    fields = MEMBERSHIP_EDIT_FIELDS.get(edit_type)
    if fields is None:
        return None
    snapshot_field, payload_field = fields
    submitted_ids = {item["id"] for item in submitted_snapshot[snapshot_field]}
    current_ids = {item["id"] for item in current_snapshot[snapshot_field]}
    proposed_ids = set(proposed_payload[payload_field])
    added_ids = proposed_ids - submitted_ids
    removed_ids = submitted_ids - proposed_ids
    merged_ids = (current_ids - removed_ids) | added_ids
    return {payload_field: sorted(merged_ids)}


class PendingEditService:
    """Coordinate identity, limits, persistence, and review transactions.

    Payload policy, snapshots, and mutations live in focused collaborators so
    this service owns only the submission lifecycle.
    """

    def __init__(
        self, db: Session, *, autonomous_policy: AutonomousPolicy | None = None
    ):
        self.db = db
        self.autonomous_policy = autonomous_policy or AutonomousPolicy()
        self.snapshots = PendingEditSnapshotService(db)
        self.mutations = PendingEditMutationService(
            db, autonomous_policy=self.autonomous_policy
        )

    def _authorize_codex_review(
        self, row: PendingPaperEdit, context: RunContext | None
    ) -> RunContext:
        if context is None:
            raise PendingEditError("Autonomous review requires a durable run context")
        decision = self.autonomous_policy.authorize(
            self.db,
            context,
            Capability.REVIEW_SUBMISSION,
            ResourceRef(ResourceKind.PENDING_EDIT, str(row.id), True),
        )
        if not decision.allowed:
            raise AutonomousCapabilityDenied(decision.reason_code)
        return context

    def is_linked_author(self, paper_id: int, hf_username: str) -> bool:
        normalized = hf_username.strip().lower()
        if not normalized:
            return False
        match = (
            self.db.query(PaperAuthor.paper_id)
            .join(Author, PaperAuthor.author_id == Author.id)
            .filter(
                PaperAuthor.paper_id == paper_id,
                Author.hf_username.isnot(None),
                Author.hf_username.ilike(normalized),
            )
            .first()
        )
        return match is not None

    def submit(
        self,
        *,
        paper_id: Optional[int],
        hf_username: str,
        hf_subject: Optional[str] = None,
        source_ip: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        exempt_from_limits: bool = False,
        edit_type: str,
        proposed_payload: Any,
    ) -> PendingPaperEdit:
        if edit_type not in EDIT_TYPES:
            raise PendingEditError(
                f"Unsupported edit_type: {edit_type}. Allowed: {sorted(EDIT_TYPES)}"
            )
        spec = edit_spec(edit_type)
        if paper_id is None and spec.requires_paper:
            raise PendingEditError(
                "paper_id is required unless submitting a taxonomy suggestion"
            )
        if paper_id is not None and self.db.get(Paper, paper_id) is None:
            raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

        normalized_payload = validate_payload(edit_type, proposed_payload)
        settings = get_settings()
        encoded_payload = json.dumps(
            normalized_payload, sort_keys=True, separators=(",", ":")
        ).encode()
        if len(encoded_payload) > settings.submission_max_payload_bytes:
            raise PendingEditError("Submission payload is too large")
        payload_hash = hashlib.sha256(encoded_payload).hexdigest()
        stable_subject = hf_subject or f"legacy-username:{hf_username.lower()}"
        if idempotency_key and len(idempotency_key) > 255:
            raise PendingEditError("Idempotency key is too long")

        self._lock_submitter(stable_subject)
        try:
            profile = UserProfileService(self.db).upsert_verified_identity(
                stable_subject, hf_username
            )
        except UserProfileError as exc:
            raise PendingEditError(str(exc)) from exc
        if profile.is_submission_suspended:
            raise SubmissionSuspendedError("This account cannot create new submissions")

        replay = self._idempotent_replay(stable_subject, idempotency_key, payload_hash)
        if replay is not None:
            return replay

        current_payload = (
            {} if paper_id is None else self.snapshots.paper_edit(paper_id, edit_type)
        )
        if payload_is_noop(edit_type, normalized_payload, current_payload):
            raise PendingEditError("Submission does not contain any changes.")

        duplicate = self._pending_duplicate(
            stable_subject, paper_id, edit_type, payload_hash
        )
        if duplicate is not None:
            return duplicate
        if not exempt_from_limits:
            self._enforce_limits(stable_subject, source_ip)
        row = PendingPaperEdit(
            paper_id=paper_id,
            hf_username=hf_username,
            hf_subject=stable_subject,
            source_ip=source_ip,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            is_author=(
                self.is_linked_author(paper_id, hf_username)
                if paper_id is not None
                else False
            ),
            edit_type=edit_type,
            proposed_payload=normalized_payload,
            current_payload=current_payload,
            status="pending",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        logger.info(
            "submission_created id=%s subject=%s edit_type=%s paper_id=%s",
            row.id,
            stable_subject,
            edit_type,
            paper_id,
        )
        self._auto_approve(row)
        return row

    def _auto_approve(self, row: PendingPaperEdit) -> None:
        """Apply a freshly stored submission; on any failure it stays queued.

        The submitter lock is taken again because the one held while storing the
        row ended with its commit. Deciding and applying under it makes the
        daily and removal limits hold for parallel requests from one account.
        """
        try:
            self._decide_and_apply(row)
        except Exception:
            logger.exception("submission_auto_approve_failed id=%s", row.id)
            self.db.rollback()
        self.db.refresh(row)

    def _decide_and_apply(self, row: PendingPaperEdit) -> None:
        self._lock_submitter(row.hf_subject)
        decision = AutoApprovalPolicy(self.db).decide(
            hf_subject=row.hf_subject,
            paper_id=row.paper_id,
            edit_type=row.edit_type,
            current=row.current_payload or {},
            proposed=row.proposed_payload,
        )
        logger.info(
            "submission_auto_decision id=%s apply=%s held=%s",
            row.id,
            decision.apply,
            decision.held_reason,
        )
        if not decision.apply:
            if decision.note:
                row.admin_note = decision.note
            self.db.commit()
            return
        self.approve(
            edit_id=row.id,
            reviewer_username=AUTO_REVIEWER,
            reviewer_kind="auto",
        )

    def _lock_submitter(self, hf_subject: str) -> None:
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:subject, 0))"),
                {"subject": hf_subject},
            )

    def _idempotent_replay(
        self, hf_subject: str, idempotency_key: str | None, payload_hash: str
    ) -> PendingPaperEdit | None:
        if not idempotency_key:
            return None
        replay = (
            self.db.query(PendingPaperEdit)
            .filter(
                PendingPaperEdit.hf_subject == hf_subject,
                PendingPaperEdit.idempotency_key == idempotency_key,
            )
            .first()
        )
        if replay is not None and replay.payload_hash != payload_hash:
            raise PendingEditError(
                "Idempotency key was already used for another payload"
            )
        return replay

    def _pending_duplicate(
        self, hf_subject: str, paper_id: int | None, edit_type: str, payload_hash: str
    ) -> PendingPaperEdit | None:
        return (
            self.db.query(PendingPaperEdit)
            .filter(
                PendingPaperEdit.hf_subject == hf_subject,
                PendingPaperEdit.edit_type == edit_type,
                PendingPaperEdit.paper_id == paper_id,
                PendingPaperEdit.payload_hash == payload_hash,
                PendingPaperEdit.status == "pending",
            )
            .first()
        )

    def _enforce_limits(self, hf_subject: str, source_ip: str | None) -> None:
        settings = get_settings()
        active = (
            self.db.query(PendingPaperEdit.id)
            .filter(
                PendingPaperEdit.hf_subject == hf_subject,
                PendingPaperEdit.status == "pending",
            )
            .count()
        )
        if active >= settings.submission_max_active_pending:
            raise SubmissionRateLimitError("Active pending submission limit reached")
        window_start = datetime.now(timezone.utc) - timedelta(hours=1)
        subject_created = (
            self.db.query(PendingPaperEdit.id)
            .filter(
                PendingPaperEdit.hf_subject == hf_subject,
                PendingPaperEdit.created_at >= window_start,
            )
            .count()
        )
        if subject_created >= settings.submission_hourly_subject_limit:
            raise SubmissionRateLimitError("Hourly account submission limit reached")
        if source_ip:
            ip_created = (
                self.db.query(PendingPaperEdit.id)
                .filter(
                    PendingPaperEdit.source_ip == source_ip,
                    PendingPaperEdit.created_at >= window_start,
                )
                .count()
            )
            if ip_created >= settings.submission_hourly_ip_limit:
                raise SubmissionRateLimitError(
                    "Hourly network submission limit reached"
                )

    def list_edits(
        self,
        *,
        status: Optional[str] = None,
        edit_type: Optional[str] = None,
        paper_id: Optional[int] = None,
        reviewed_by_kind: Optional[str] = None,
        hf_username: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[PendingPaperEdit], int]:
        if status is not None and status not in STATUSES:
            raise PendingEditError(
                f"Unsupported status: {status}. Allowed: {sorted(STATUSES)}"
            )
        if edit_type is not None and edit_type not in EDIT_TYPES:
            raise PendingEditError(
                f"Unsupported edit_type: {edit_type}. Allowed: {sorted(EDIT_TYPES)}"
            )
        query = self.db.query(PendingPaperEdit)
        if status:
            query = query.filter(PendingPaperEdit.status == status)
        if edit_type:
            query = query.filter(PendingPaperEdit.edit_type == edit_type)
        if paper_id is not None:
            query = query.filter(PendingPaperEdit.paper_id == paper_id)
        if reviewed_by_kind:
            query = query.filter(PendingPaperEdit.reviewed_by_kind == reviewed_by_kind)
        if hf_username:
            query = query.filter(PendingPaperEdit.hf_username.ilike(hf_username))
        total = query.count()
        rows = (
            query.order_by(desc(PendingPaperEdit.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return rows, total

    def get(self, edit_id: int) -> PendingPaperEdit:
        row = self.db.get(PendingPaperEdit, edit_id)
        if row is None:
            raise PendingEditNotFoundError(f"Pending edit with ID {edit_id} not found")
        return row

    def approve(
        self,
        *,
        edit_id: int,
        reviewer_username: Optional[str],
        reviewer_hf_subject: Optional[str] = None,
        reviewer_kind: str = "human",
        autonomous_context: RunContext | None = None,
        review_run_id: Any = None,
        review_model: Optional[str] = None,
        review_evidence: Optional[dict[str, Any]] = None,
        resolved_payload: Optional[dict[str, Any]] = None,
        admin_note: Optional[str] = None,
        user_review_reason: Optional[str] = None,
        commit: bool = True,
    ) -> PendingPaperEdit:
        boundary = review_transaction(self.db) if commit else nullcontext()
        with boundary:
            return self._approve(
                edit_id=edit_id,
                reviewer_username=reviewer_username,
                reviewer_hf_subject=reviewer_hf_subject,
                reviewer_kind=reviewer_kind,
                autonomous_context=autonomous_context,
                review_run_id=review_run_id,
                review_model=review_model,
                review_evidence=review_evidence,
                resolved_payload=resolved_payload,
                admin_note=admin_note,
                user_review_reason=user_review_reason,
            )

    def _approve(
        self,
        *,
        edit_id: int,
        reviewer_username: Optional[str],
        reviewer_hf_subject: Optional[str] = None,
        reviewer_kind: str = "human",
        autonomous_context: RunContext | None = None,
        review_run_id: Any = None,
        review_model: Optional[str] = None,
        review_evidence: Optional[dict[str, Any]] = None,
        resolved_payload: Optional[dict[str, Any]] = None,
        admin_note: Optional[str] = None,
        user_review_reason: Optional[str] = None,
    ) -> PendingPaperEdit:
        if reviewer_kind not in {"human", "codex", "auto"}:
            raise PendingEditError("Unsupported reviewer kind")
        row = self._pending_for_review(edit_id)
        if reviewer_kind == "codex" and row.edit_type in HUMAN_ONLY_EDIT_TYPES:
            raise PendingEditError(
                "Autonomous reviews must defer human-only taxonomy resources"
            )
        if reviewer_kind == "auto" and row.edit_type not in AUTO_EDIT_TYPES:
            raise PendingEditError("This edit type is not eligible for auto-approval")
        if reviewer_kind == "codex":
            autonomous_context = self._authorize_codex_review(row, autonomous_context)
        spec = edit_spec(row.edit_type)
        if row.paper_id is None and spec.requires_paper:
            raise PendingEditError("This edit is missing its paper_id")
        applied_payload = validate_payload(
            row.edit_type,
            resolved_payload if resolved_payload is not None else row.proposed_payload,
        )
        if (
            row.edit_type == "new_external_paper"
            and "date_published" not in applied_payload
        ):
            applied_payload["date_published"] = row.created_at.date().isoformat()
        if row.paper_id is not None:
            current = self.snapshots.paper_edit(row.paper_id, row.edit_type)
            if _conflict_snapshot(row.edit_type, current) != _conflict_snapshot(
                row.edit_type, row.current_payload or {}
            ):
                rebased_payload = _rebase_membership_payload(
                    row.edit_type,
                    row.current_payload or {},
                    current,
                    applied_payload,
                )
                if rebased_payload is None:
                    row.conflict_payload = {
                        "submitted_snapshot": row.current_payload or {},
                        "current_snapshot": current,
                    }
                    raise PendingEditConflictError(
                        "Canonical state changed after submission",
                        edit_id=edit_id,
                        conflict_payload=row.conflict_payload,
                    )
                applied_payload = rebased_payload
            row.conflict_payload = None

        is_administrative = row.edit_type in RECORD_ONLY_EDIT_TYPES
        result_type: str | None = None
        result_id: str | None = None
        before: Any = {}
        if not is_administrative:
            before = self.snapshots.approval_event(row.edit_type, row.paper_id)
            try:
                if reviewer_kind == "codex":
                    assert autonomous_context is not None
                    result_type, result_id = self.mutations.apply_autonomous(
                        context=autonomous_context,
                        edit_type=row.edit_type,
                        paper_id=row.paper_id,
                        payload=applied_payload,
                    )
                else:
                    result_type, result_id = self.mutations.apply_human_review(
                        row.edit_type,
                        row.paper_id,
                        applied_payload,
                        actor_hf_subject=row.hf_subject,
                        actor_username=row.hf_username,
                    )
            except Exception as exc:
                raise PendingEditApplyError(edit_id, exc) from exc

        row.status = "approved"
        row.reviewed_by = reviewer_username
        row.reviewed_by_kind = reviewer_kind
        row.reviewed_by_hf_subject = reviewer_hf_subject
        row.review_run_id = review_run_id
        row.review_model = review_model
        row.review_evidence = review_evidence
        row.applied_payload = applied_payload
        row.result_entity_type = result_type
        row.result_entity_id = result_id
        if not is_administrative:
            after = self.snapshots.approval_event(
                row.edit_type,
                row.paper_id,
                result_type=result_type,
                result_id=result_id,
            )
            event = self._approval_event(
                row,
                reviewer_username,
                reviewer_hf_subject,
                before,
                after,
                auto=reviewer_kind == "auto",
            )
            self.db.add(event)
            self.db.flush()
            row.catalog_event_id = event.id
        row.admin_note = admin_note
        row.user_review_reason = user_review_reason
        row.reviewed_at = datetime.now(timezone.utc)
        self.db.flush()
        logger.info(
            "submission_approved id=%s reviewer_subject=%s result=%s:%s",
            row.id,
            reviewer_hf_subject,
            result_type,
            result_id,
        )
        return row

    def _pending_for_review(self, edit_id: int) -> PendingPaperEdit:
        row = (
            self.db.query(PendingPaperEdit)
            .filter(PendingPaperEdit.id == edit_id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise PendingEditNotFoundError(f"Pending edit with ID {edit_id} not found")
        if row.status != "pending":
            raise PendingEditAlreadyReviewedError(
                f"Pending edit {edit_id} is already {row.status}"
            )
        return row

    @staticmethod
    def _approval_event(
        row: PendingPaperEdit,
        reviewer_username: str | None,
        reviewer_hf_subject: str | None,
        before: Any,
        after: Any,
        *,
        auto: bool = False,
    ) -> CatalogMutationEvent:
        if row.edit_type.startswith("new_"):
            entity_type = f"submission_created_{row.result_entity_type}"
            entity_id = row.result_entity_id
        elif row.paper_id is not None:
            entity_type = (
                "evaluation"
                if row.edit_type == "evaluations"
                else f"paper_{row.edit_type}"
            )
            entity_id = (
                f"paper:{row.paper_id}"
                if row.edit_type == "evaluations"
                else str(row.paper_id)
            )
        else:
            entity_type = f"submission_created_{row.result_entity_type}"
            entity_id = row.result_entity_id
        # Auto-applied edits are attributed to the submitter so that contributor
        # history and bulk revert by account see them.
        return CatalogMutationEvent(
            actor_hf_subject=row.hf_subject
            if auto
            else reviewer_hf_subject or "legacy-human-reviewer",
            actor_username=row.hf_username if auto else reviewer_username,
            actor_role="contributor" if auto else "admin",
            operation="approve_submission",
            entity_type=entity_type,
            entity_id=entity_id,
            before_snapshot=json_safe(before),
            after_snapshot=json_safe(after),
            request_id=f"submission-{'auto' if auto else 'review'}:{row.id}",
            source_environment=get_settings().environment,
            release_id=get_settings().release_id,
        )

    def reject(
        self,
        *,
        edit_id: int,
        reviewer_username: Optional[str],
        reviewer_hf_subject: Optional[str] = None,
        reviewer_kind: str = "human",
        autonomous_context: RunContext | None = None,
        review_run_id: Any = None,
        review_model: Optional[str] = None,
        review_evidence: Optional[dict[str, Any]] = None,
        admin_note: Optional[str] = None,
        user_review_reason: Optional[str] = None,
        commit: bool = True,
    ) -> PendingPaperEdit:
        if reviewer_kind not in {"human", "codex"}:
            raise PendingEditError("Unsupported reviewer kind")
        row = self._pending_for_review(edit_id)
        if reviewer_kind == "codex" and row.edit_type in HUMAN_ONLY_EDIT_TYPES:
            raise PendingEditError(
                "Autonomous reviews must defer human-only taxonomy resources"
            )
        if reviewer_kind == "codex":
            self._authorize_codex_review(row, autonomous_context)
        row.status = "rejected"
        row.reviewed_by = reviewer_username
        row.reviewed_by_kind = reviewer_kind
        row.reviewed_by_hf_subject = reviewer_hf_subject
        row.review_run_id = review_run_id
        row.review_model = review_model
        row.review_evidence = review_evidence
        row.admin_note = admin_note
        row.user_review_reason = user_review_reason
        row.reviewed_at = datetime.now(timezone.utc)
        if commit:
            self.db.commit()
            self.db.refresh(row)
        else:
            self.db.flush()
        logger.info(
            "submission_rejected id=%s reviewer_subject=%s",
            row.id,
            reviewer_hf_subject,
        )
        return row
