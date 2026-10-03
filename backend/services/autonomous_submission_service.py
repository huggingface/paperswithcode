"""Exclusive batches and scoped callbacks for autonomous submission review."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousRun,
    AutonomousSubmissionClaim,
    PendingPaperEdit,
)
from backend.services.autonomous_capabilities import HUMAN_ONLY_EDIT_TYPES
from backend.services.autonomous_operations_repository import Operator, RunContext
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
)
from backend.services.pending_edit_transactions import review_transaction
from backend.services.pending_edit_service import PendingEditService


class AutonomousSubmissionCallbackError(RuntimeError):
    """A remote callback failed authentication, fencing, or decision policy."""


class AutonomousSubmissionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    decision: Literal["approve", "reject", "defer"]
    rationale: str = Field(min_length=1, max_length=4000)
    evidence: list[str] = Field(min_length=1, max_length=50)
    confidence: float = Field(ge=0, le=1)
    resolved_payload: dict[str, Any] | None = None


class RemoteSubmissionUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0, le=10_000_000)
    output_tokens: int = Field(ge=0, le=10_000_000)
    cost_usd: Decimal = Field(ge=0)


@dataclass(frozen=True, slots=True)
class ClaimedSubmission:
    claim_id: uuid.UUID
    pending_edit_id: int
    run_id: uuid.UUID
    edit_type: str
    snapshot: dict[str, Any]
    snapshot_digest: str
    callback_token: str
    expires_at: datetime
    required_decision: Literal["defer"] | None


@dataclass(frozen=True, slots=True)
class ReviewedSubmission:
    claim_id: uuid.UUID
    callback_token: str
    decision: AutonomousSubmissionDecision


DecisionApplier = Callable[[RunContext, AutonomousSubmissionDecision], Any]


def _iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class AutonomousSubmissionService:
    """Claim immutable queue snapshots and consume single-scope decisions."""

    def __init__(
        self,
        db: Session,
        *,
        signing_secret: bytes,
        callback_base_url: str,
        clock: Callable[[], datetime] | None = None,
        decision_applier: DecisionApplier | None = None,
        remote_budget_usd: Decimal = Decimal("0"),
    ):
        if len(signing_secret) < 32:
            raise ValueError("Autonomous submission signing secret is too short")
        if not callback_base_url.startswith(("https://", "http://localhost")):
            raise ValueError("Autonomous callback base URL is invalid")
        self.db = db
        self._secret = signing_secret
        self._base_url = callback_base_url.rstrip("/")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._decision_applier = decision_applier or self._apply_canonical_decision
        self._remote_budget_usd = remote_budget_usd

    @staticmethod
    def _snapshot(row: PendingPaperEdit) -> dict[str, Any]:
        return {
            "id": row.id,
            "paper_id": row.paper_id,
            "edit_type": row.edit_type,
            "proposed_payload": row.proposed_payload,
            "current_payload": row.current_payload,
            "payload_hash": row.payload_hash,
            "created_at": _iso(row.created_at),
        }

    @staticmethod
    def _review_snapshot(item: ClaimedSubmission) -> dict[str, Any]:
        if item.required_decision is None:
            return item.snapshot
        return {
            **item.snapshot,
            "proposed_payload": {"human_only_taxonomy": True},
            "current_payload": {},
        }

    def claim_submission_batch(
        self,
        run_id: uuid.UUID,
        *,
        limit: int = 25,
        ttl: timedelta = timedelta(hours=1),
    ) -> list[ClaimedSubmission]:
        if not isinstance(run_id, uuid.UUID) or not 1 <= limit <= 25:
            raise ValueError("Autonomous submission batch request is invalid")
        if not timedelta(minutes=5) <= ttl <= timedelta(hours=2):
            raise ValueError("Autonomous submission claim TTL is invalid")
        run = self.db.get(AutonomousRun, run_id)
        if run is None or run.operator != Operator.SUBMISSIONS.value:
            raise ValueError("Submission claim requires a durable submissions run")
        context = RunContext(
            run_id=run.id,
            operator=Operator.SUBMISSIONS,
            dry_run=run.dry_run,
            manifest_revision=run.manifest_revision,
        )
        AutonomousOperationsRepository().assert_mutation_allowed(self.db, context)
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("Autonomous submission clock must be timezone-aware")
        blocking_claim = exists(
            select(AutonomousSubmissionClaim.claim_id).where(
                AutonomousSubmissionClaim.pending_edit_id == PendingPaperEdit.id,
                or_(
                    AutonomousSubmissionClaim.state == "completed",
                    and_(
                        AutonomousSubmissionClaim.state == "claimed",
                        AutonomousSubmissionClaim.expires_at > now,
                    ),
                ),
            )
        )
        rows = list(
            self.db.scalars(
                select(PendingPaperEdit)
                .where(PendingPaperEdit.status == "pending", ~blocking_claim)
                .order_by(PendingPaperEdit.created_at, PendingPaperEdit.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        expires_at = now + ttl
        claimed: list[ClaimedSubmission] = []
        for row in rows:
            snapshot = self._snapshot(row)
            snapshot_digest = _digest(snapshot)
            token = secrets.token_urlsafe(32)
            existing = self.db.scalar(
                select(AutonomousSubmissionClaim)
                .where(
                    AutonomousSubmissionClaim.pending_edit_id == row.id,
                    AutonomousSubmissionClaim.run_id == run_id,
                )
                .with_for_update()
            )
            claim_id = existing.claim_id if existing is not None else uuid.uuid4()
            claim = existing or AutonomousSubmissionClaim(
                claim_id=claim_id,
                pending_edit_id=row.id,
                run_id=run_id,
                created_at=now,
            )
            claim.snapshot_digest = snapshot_digest
            claim.callback_token_hash = hashlib.sha256(token.encode()).hexdigest()
            claim.expires_at = expires_at
            claim.state = "claimed"
            claim.decision = None
            claim.decision_digest = None
            claim.completed_at = None
            claim.review_run_id = None
            claim.attested_decision_digest = None
            claim.remote_manifest_digest = None
            claim.remote_job_id = None
            claim.remote_review_run_id = None
            if existing is None:
                self.db.add(claim)
            claimed.append(
                ClaimedSubmission(
                    claim_id=claim_id,
                    pending_edit_id=row.id,
                    run_id=run_id,
                    edit_type=row.edit_type,
                    snapshot=snapshot,
                    snapshot_digest=snapshot_digest,
                    callback_token=token,
                    expires_at=expires_at,
                    required_decision=(
                        "defer" if row.edit_type in HUMAN_ONLY_EDIT_TYPES else None
                    ),
                )
            )
        self.db.commit()
        return claimed

    def preview_submission_queue(self, *, limit: int = 25) -> list[dict[str, Any]]:
        if not 1 <= limit <= 25:
            raise ValueError("Autonomous submission preview limit is invalid")
        rows = list(
            self.db.scalars(
                select(PendingPaperEdit)
                .where(PendingPaperEdit.status == "pending")
                .order_by(PendingPaperEdit.created_at, PendingPaperEdit.id)
                .limit(limit)
            )
        )
        return [
            {
                "pending_edit_id": row.id,
                "edit_type": row.edit_type,
                "required_decision": (
                    "defer" if row.edit_type in HUMAN_ONLY_EDIT_TYPES else None
                ),
            }
            for row in rows
        ]

    def build_submission_manifest(
        self, batch: list[ClaimedSubmission]
    ) -> dict[str, Any]:
        if not batch:
            raise ValueError("Autonomous submission batch is empty")
        run_ids = {item.run_id for item in batch}
        expiries = {item.expires_at for item in batch}
        if len(run_ids) != 1 or len(expiries) != 1 or len(batch) > 25:
            raise ValueError("Autonomous submission batch is inconsistent")
        manifest: dict[str, Any] = {
            "schema": "pwc.autonomous-submission-review.v1",
            "run_id": str(next(iter(run_ids))),
            "model_alias": "luna-medium",
            "expires_at": _iso(next(iter(expiries))),
            "allowed_decisions": ["approve", "reject", "defer"],
            "items": [
                {
                    "claim_id": str(item.claim_id),
                    "snapshot": self._review_snapshot(item),
                    "snapshot_digest": item.snapshot_digest,
                    "required_decision": item.required_decision,
                    "callback_url": (
                        f"{self._base_url}/autonomous-submissions/"
                        f"{item.claim_id}/decision"
                    ),
                    "callback_token": item.callback_token,
                }
                for item in batch
            ],
        }
        manifest["signature"] = hmac.new(
            self._secret, _canonical(manifest), hashlib.sha256
        ).hexdigest()
        return manifest

    def review_submission_batch(
        self,
        batch: list[ClaimedSubmission],
        *,
        budget_usd: Decimal,
        runner=None,
    ) -> list[ReviewedSubmission]:
        """Review one claimed batch through Task 3's attested Luna/medium path."""
        from backend.services.autonomous_capabilities import Capability
        from backend.services.autonomous_codex_runner import (
            CodexRequest,
            EvidenceRef,
            codex_result_schema,
            run_codex,
        )

        if not batch or len({item.run_id for item in batch}) != 1:
            raise ValueError("Autonomous submission review batch is inconsistent")
        capabilities = (Capability.REVIEW_SUBMISSION,)
        manifest_digest = _digest(
            [
                {
                    "claim_id": str(item.claim_id),
                    "snapshot_digest": item.snapshot_digest,
                    "required_decision": item.required_decision,
                    "expires_at": _iso(item.expires_at),
                }
                for item in batch
            ]
        )
        review_run_id = uuid.uuid5(batch[0].run_id, manifest_digest)
        context = RunContext(
            run_id=review_run_id,
            operator=Operator.SUBMISSIONS,
            dry_run=False,
            manifest_revision=f"submission-review-v1:{manifest_digest}",
        )
        request = CodexRequest(
            context=context,
            evidence=tuple(
                EvidenceRef(
                    kind="submission_snapshot",
                    identifier=str(item.pending_edit_id),
                    digest=item.snapshot_digest,
                )
                for item in batch
            ),
            capabilities=capabilities,
            output_schema=codex_result_schema(capabilities, structured_submission=True),
            budget_usd=budget_usd,
            model_alias="diagnosis",
            evidence_payload={
                "submissions": [
                    {
                        "claim_id": str(item.claim_id),
                        "required_decision": item.required_decision,
                        "snapshot": self._review_snapshot(item),
                    }
                    for item in batch
                ]
            },
        )
        result = (runner or run_codex)(request, db=self.db)
        if result.status != "completed":
            raise RuntimeError(
                f"Submission review model did not complete: {result.exit_classification}"
            )
        by_edit_id = {str(item.pending_edit_id): item for item in batch}
        actions = {
            action.resource.identifier: action for action in result.proposed_actions
        }
        if set(actions) != set(by_edit_id) or len(result.proposed_actions) != len(
            batch
        ):
            raise RuntimeError(
                "Submission reviewer returned incomplete or duplicate scope"
            )
        reviewed = []
        for edit_id, item in by_edit_id.items():
            action = actions[edit_id]
            if (
                action.capability != Capability.REVIEW_SUBMISSION
                or action.reason_code not in {"approve", "reject", "defer"}
                or action.rationale is None
                or action.confidence is None
                or not action.evidence
                or (item.required_decision == "defer" and action.reason_code != "defer")
            ):
                raise RuntimeError("Submission reviewer returned an invalid decision")
            decision = AutonomousSubmissionDecision(
                claim_id=item.claim_id,
                decision=action.reason_code,
                rationale=action.rationale,
                evidence=list(action.evidence),
                confidence=action.confidence,
                resolved_payload=action.resolved_payload,
            )
            claim = self.db.get(AutonomousSubmissionClaim, item.claim_id)
            if claim is None or claim.state != "claimed":
                raise RuntimeError("Submission claim changed during review")
            claim.review_run_id = review_run_id
            claim.attested_decision_digest = _digest(decision.model_dump(mode="json"))
            reviewed.append(
                ReviewedSubmission(item.claim_id, item.callback_token, decision)
            )
        self.db.commit()
        return reviewed

    def verify_manifest(self, manifest: dict[str, Any]) -> bool:
        supplied = manifest.get("signature")
        if not isinstance(supplied, str):
            return False
        unsigned = {key: value for key, value in manifest.items() if key != "signature"}
        expected = hmac.new(
            self._secret, _canonical(unsigned), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(supplied, expected)

    def prepare_remote_review(
        self, batch: list[ClaimedSubmission], manifest: dict[str, Any]
    ) -> None:
        """Fence claims for a database-free worker before launching it."""
        if not self.verify_manifest(manifest):
            raise ValueError("Remote submission manifest signature is invalid")
        manifest_claims = {uuid.UUID(item["claim_id"]) for item in manifest["items"]}
        if manifest_claims != {item.claim_id for item in batch}:
            raise ValueError("Remote submission manifest scope is inconsistent")
        manifest_digest = _digest(manifest)
        for item in batch:
            claim = self.db.get(AutonomousSubmissionClaim, item.claim_id)
            if claim is None or claim.state != "claimed":
                raise ValueError("Remote submission claim changed before launch")
            claim.remote_manifest_digest = manifest_digest
            claim.remote_job_id = None
            claim.remote_review_run_id = uuid.uuid5(item.claim_id, manifest_digest)
            claim.review_run_id = None
            claim.attested_decision_digest = None
        self.db.commit()

    def record_remote_job(self, batch: list[ClaimedSubmission], *, job_id: str) -> None:
        if not job_id or len(job_id) > 255:
            raise ValueError("Remote submission Job ID is invalid")
        for item in batch:
            claim = self.db.get(AutonomousSubmissionClaim, item.claim_id)
            if claim is None or claim.remote_manifest_digest is None:
                raise ValueError("Remote submission claim changed after launch")
            claim.remote_job_id = job_id
        self.db.commit()

    def pending_remote_job_ids(self) -> tuple[str, ...]:
        return tuple(
            self.db.scalars(
                select(AutonomousSubmissionClaim.remote_job_id)
                .where(
                    AutonomousSubmissionClaim.state == "claimed",
                    AutonomousSubmissionClaim.remote_job_id.is_not(None),
                )
                .distinct()
                .order_by(AutonomousSubmissionClaim.remote_job_id)
            )
        )

    def release_remote_job(self, job_id: str) -> int:
        claims = list(
            self.db.scalars(
                select(AutonomousSubmissionClaim).where(
                    AutonomousSubmissionClaim.state == "claimed",
                    AutonomousSubmissionClaim.remote_job_id == job_id,
                )
            )
        )
        now = self._clock()
        for claim in claims:
            claim.expires_at = now
            claim.review_run_id = None
            claim.attested_decision_digest = None
            claim.remote_manifest_digest = None
            claim.remote_job_id = None
            claim.remote_review_run_id = None
        self.db.commit()
        return len(claims)

    def release_failed_remote_review(self, batch: list[ClaimedSubmission]) -> None:
        """Expire prepared claims after launch failure so a later run can retry."""
        now = self._clock()
        for item in batch:
            claim = self.db.get(AutonomousSubmissionClaim, item.claim_id)
            if claim is not None and claim.state == "claimed":
                claim.expires_at = now
                claim.review_run_id = None
                claim.attested_decision_digest = None
                claim.remote_manifest_digest = None
                claim.remote_job_id = None
                claim.remote_review_run_id = None
        self.db.commit()

    @staticmethod
    def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
        """Create a new private manifest without following or replacing paths."""
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def apply_submission_decision(
        self,
        callback_token: str,
        decision: AutonomousSubmissionDecision,
        *,
        remote_signature: str | None = None,
        remote_usage: str | None = None,
    ) -> None:
        with review_transaction(self.db):
            self._apply_submission_decision(
                callback_token,
                decision,
                remote_signature=remote_signature,
                remote_usage=remote_usage,
            )

    def _apply_submission_decision(
        self,
        callback_token: str,
        decision: AutonomousSubmissionDecision,
        *,
        remote_signature: str | None = None,
        remote_usage: str | None = None,
    ) -> None:
        now = self._clock()
        claim = self.db.execute(
            select(AutonomousSubmissionClaim)
            .where(AutonomousSubmissionClaim.claim_id == decision.claim_id)
            .with_for_update()
        ).scalar_one_or_none()
        if claim is None:
            raise AutonomousSubmissionCallbackError("Callback scope is invalid")
        expected_token = hashlib.sha256(callback_token.encode()).hexdigest()
        if not hmac.compare_digest(claim.callback_token_hash, expected_token):
            raise AutonomousSubmissionCallbackError("Callback token is invalid")
        if (
            claim.expires_at.replace(tzinfo=UTC)
            if claim.expires_at.tzinfo is None
            else claim.expires_at
        ) <= now:
            raise AutonomousSubmissionCallbackError("Callback has expired")
        decision_payload = decision.model_dump(mode="json")
        decision_digest = _digest(decision_payload)
        if claim.state == "completed":
            if hmac.compare_digest(claim.decision_digest or "", decision_digest):
                return
            raise AutonomousSubmissionCallbackError("Callback replay changed decision")
        row = self.db.get(PendingPaperEdit, claim.pending_edit_id)
        if row is None or _digest(self._snapshot(row)) != claim.snapshot_digest:
            raise AutonomousSubmissionCallbackError("Callback scope snapshot changed")
        if row.edit_type in HUMAN_ONLY_EDIT_TYPES and decision.decision != "defer":
            raise AutonomousSubmissionCallbackError(
                "Human-only taxonomy submissions must defer"
            )
        if row.edit_type != "new_external_paper" and decision.resolved_payload not in (
            None,
            row.proposed_payload,
        ):
            raise AutonomousSubmissionCallbackError(
                "Resolved payload cannot expand submission scope"
            )
        if decision.decision != "defer" and decision.confidence < 0.9:
            raise AutonomousSubmissionCallbackError(
                "Terminal submission decisions require confidence >= 0.9"
            )
        if row.edit_type == "new_external_paper" and decision.resolved_payload:
            if decision.resolved_payload.get("source_url") != row.proposed_payload.get(
                "source_url"
            ):
                raise AutonomousSubmissionCallbackError(
                    "External-paper source URL cannot expand submission scope"
                )
            if {"enrich", "enrichment"} & decision.resolved_payload.keys():
                raise AutonomousSubmissionCallbackError(
                    "External-paper enrichment is not allowed"
                )
        if (
            claim.attested_decision_digest is None
            and remote_signature is not None
            and remote_usage is not None
            and claim.remote_manifest_digest is not None
            and claim.remote_review_run_id is not None
        ):
            try:
                if len(remote_usage) > 4096:
                    raise ValueError("usage header is too large")
                usage_payload = RemoteSubmissionUsage.model_validate_json(
                    base64.urlsafe_b64decode(remote_usage.encode()).decode()
                )
            except (TypeError, ValueError):
                raise AutonomousSubmissionCallbackError(
                    "Remote decision usage is invalid"
                ) from None
            if (
                self._remote_budget_usd <= 0
                or usage_payload.cost_usd > self._remote_budget_usd
            ):
                raise AutonomousSubmissionCallbackError(
                    "Remote decision exceeded its cost limit"
                )
            signed_payload = {
                "decision": decision_payload,
                "usage": usage_payload.model_dump(mode="json"),
            }
            expected_signature = hmac.new(
                callback_token.encode(), _canonical(signed_payload), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(remote_signature, expected_signature):
                raise AutonomousSubmissionCallbackError(
                    "Remote decision signature is invalid"
                )
            if self.db.get(AutonomousRun, claim.remote_review_run_id) is not None:
                raise AutonomousSubmissionCallbackError(
                    "Remote review run identity was already used"
                )
            remote_context = RunContext(
                run_id=claim.remote_review_run_id,
                operator=Operator.SUBMISSIONS,
                dry_run=False,
                manifest_revision=(
                    f"remote-submission-v1:{claim.remote_manifest_digest}"
                ),
            )
            AutonomousOperationsRepository().append_run(
                self.db,
                context=remote_context,
                status="completed",
                exit_classification="completed",
                capability_requests=[
                    {
                        "capability": "review_submission",
                        "resource_kind": "pending_edit",
                        "resource_identifier": str(row.id),
                        "resource_exists": True,
                        "reason_code": decision.decision,
                        "rationale": decision.rationale,
                        "evidence": decision.evidence,
                        "confidence": decision.confidence,
                        "resolved_payload": decision.resolved_payload,
                    }
                ],
                evidence_digests=[claim.snapshot_digest],
                input_tokens=usage_payload.input_tokens,
                output_tokens=usage_payload.output_tokens,
                cost_usd=usage_payload.cost_usd,
                now=now,
            )
            claim.review_run_id = claim.remote_review_run_id
            claim.attested_decision_digest = decision_digest
        if claim.review_run_id is None or not hmac.compare_digest(
            claim.attested_decision_digest or "", decision_digest
        ):
            raise AutonomousSubmissionCallbackError(
                "Callback does not match the attested model decision"
            )
        run = self.db.get(AutonomousRun, claim.review_run_id)
        if (
            run is None
            or run.operator != Operator.SUBMISSIONS.value
            or run.status != "completed"
            or run.exit_classification != "completed"
        ):
            raise AutonomousSubmissionCallbackError("Callback run scope is invalid")
        context = RunContext(
            run_id=run.id,
            operator=Operator.SUBMISSIONS,
            dry_run=run.dry_run,
            manifest_revision=run.manifest_revision,
        )
        AutonomousOperationsRepository().assert_mutation_allowed(self.db, context)
        self._decision_applier(context, decision)
        claim.state = "completed"
        claim.decision = decision.decision
        claim.decision_digest = decision_digest
        claim.completed_at = now

    def _apply_canonical_decision(
        self, context: RunContext, decision: AutonomousSubmissionDecision
    ) -> None:
        claim = self.db.get(AutonomousSubmissionClaim, decision.claim_id)
        if claim is None:
            raise AutonomousSubmissionCallbackError("Callback scope is invalid")
        if decision.decision == "defer":
            return
        evidence = {
            "decision": decision.decision,
            "rationale": decision.rationale,
            "sources": decision.evidence,
            "confidence": decision.confidence,
            "resolved_payload": decision.resolved_payload,
            "workflow_version": context.manifest_revision,
        }
        kwargs = {
            "edit_id": claim.pending_edit_id,
            "reviewer_username": "Codex",
            "reviewer_hf_subject": f"codex-review:{context.run_id}",
            "reviewer_kind": "codex",
            "autonomous_context": context,
            "review_run_id": context.run_id,
            "review_model": "luna-medium",
            "review_evidence": evidence,
            "admin_note": decision.rationale,
        }
        service = PendingEditService(self.db)
        if decision.decision == "approve":
            service.approve(
                **kwargs,
                resolved_payload=decision.resolved_payload,
                commit=False,
            )
        else:
            service.reject(
                **kwargs,
                user_review_reason=decision.rationale,
                commit=False,
            )
