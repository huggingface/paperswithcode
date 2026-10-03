"""Approval must not end a transaction owned by a callback or another caller."""

import base64
import hashlib
import hmac
import json
import uuid
from contextlib import nullcontext
from unittest.mock import Mock

from fastapi import HTTPException

import pytest

from backend.models.database import (
    AutonomousRun,
    AutonomousSubmissionClaim,
    CatalogMutationEvent,
    Paper,
    PendingPaperEdit,
)
from backend.services.autonomous_submission_service import AutonomousSubmissionDecision
from backend.services.pending_edit_errors import (
    PendingEditApplyError,
    PendingEditConflictError,
)
from backend.services.pending_edit_mutations import PendingEditMutationService
from backend.services.pending_edit_service import PendingEditService
from backend.tests.test_autonomous_submission_service import _run, _service
from backend.tests import test_pending_edit_noop as fixtures

db_session = fixtures.db_session
paper_fixture = fixtures.paper_fixture


def submit(db):
    return PendingEditService(db).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="source_url",
        proposed_payload={"source_url": "https://example.com/proposed"},
    )


def break_approval(db, monkeypatch, kind):
    if kind == "conflict":
        db.get(Paper, 1).source_url = "https://example.com/intervening"
        db.commit()
    else:

        def fail(self, *args, **kwargs):
            self.db.get(Paper, 1).source_url = "https://example.com/partial"
            self.db.flush()
            raise ValueError("mutation failed after writing")

        monkeypatch.setattr(PendingEditMutationService, "apply_human_review", fail)
        monkeypatch.setattr(PendingEditMutationService, "apply_autonomous", fail)


@pytest.mark.parametrize("kind", ["conflict", "apply"])
@pytest.mark.parametrize("owns_transaction", [False, True])
def test_approval_failure_respects_transaction_owner(
    db_session, paper_fixture, monkeypatch, kind, owns_transaction
):
    db = db_session
    row = submit(db)
    row_id = row.id
    break_approval(db, monkeypatch, kind)
    original_title = db.get(Paper, 1).title
    db.get(Paper, 1).title = "unrelated uncommitted change"
    commit = Mock(wraps=db.commit)
    rollback = Mock(wraps=db.rollback)
    monkeypatch.setattr(db, "commit", commit)
    monkeypatch.setattr(db, "rollback", rollback)
    expected_error = (
        PendingEditConflictError
        if kind == "conflict"
        else (ValueError if owns_transaction else PendingEditApplyError)
    )

    with pytest.raises(expected_error):
        PendingEditService(db).approve(
            edit_id=row_id, reviewer_username="admin", commit=owns_transaction
        )

    if not owns_transaction:
        commit.assert_not_called()
        rollback.assert_not_called()
        assert db.get(Paper, 1).title == "unrelated uncommitted change"
        db.rollback()
    else:
        assert rollback.call_count == 1
        commit.assert_not_called()  # The diagnostic uses its own explicit transaction.
    db.expire_all()
    assert db.get(Paper, 1).title == original_title
    assert db.get(Paper, 1).source_url != "https://example.com/partial"
    pending = db.get(PendingPaperEdit, row_id)
    assert pending.status == "pending"
    assert pending.reviewed_at is None
    assert bool(pending.conflict_payload) == (owns_transaction and kind == "conflict")
    assert bool(pending.failure_reason) == (owns_transaction and kind == "apply")
    assert db.query(CatalogMutationEvent).count() == 0


def test_successful_caller_owned_approval_can_be_rolled_back(
    db_session, paper_fixture, monkeypatch
):
    db = db_session
    row_id = submit(db).id
    original_source = db.get(Paper, 1).source_url
    commit = Mock(wraps=db.commit)
    rollback = Mock(wraps=db.rollback)
    monkeypatch.setattr(db, "commit", commit)
    monkeypatch.setattr(db, "rollback", rollback)
    row = PendingEditService(db).approve(
        edit_id=row_id, reviewer_username="admin", commit=False
    )
    assert row.status == "approved"
    commit.assert_not_called()
    rollback.assert_not_called()
    assert db.query(CatalogMutationEvent).count() == 1
    db.rollback()
    assert db.get(PendingPaperEdit, row_id).status == "pending"
    assert db.get(Paper, 1).source_url == original_source
    assert db.query(CatalogMutationEvent).count() == 0


@pytest.mark.parametrize("kind", ["conflict", "apply", "success"])
def test_remote_callback_keeps_attestation_claim_and_catalog_atomic(
    db_session, paper_fixture, monkeypatch, kind
):
    db = db_session
    run_id = uuid.uuid4()
    _run(db, run_id)
    row_id = submit(db).id
    service = _service(db)
    batch = service.claim_submission_batch(run_id, limit=1)
    manifest = service.build_submission_manifest(batch)
    service.prepare_remote_review(batch, manifest)
    item = batch[0]
    remote_run_id = db.get(
        AutonomousSubmissionClaim, item.claim_id
    ).remote_review_run_id
    decision = AutonomousSubmissionDecision(
        claim_id=item.claim_id,
        decision="approve",
        rationale="Reviewed source",
        evidence=["submission_snapshot"],
        confidence=0.99,
    )
    usage = {"input_tokens": 100, "output_tokens": 20, "cost_usd": "0.01"}
    encoded_usage = base64.urlsafe_b64encode(json.dumps(usage).encode()).decode()
    canonical = json.dumps(
        {"decision": decision.model_dump(mode="json"), "usage": usage},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(
        item.callback_token.encode(), canonical, hashlib.sha256
    ).hexdigest()
    if kind != "success":
        break_approval(db, monkeypatch, kind)
    original_title = db.get(Paper, 1).title
    db.get(Paper, 1).title = "unrelated callback state"

    # Successful replays apply once. Failed callbacks remain retryable without
    # reserving the remote run ID or completing the claim.
    for _ in range(2):
        expected = (
            nullcontext()
            if kind == "success"
            else pytest.raises(
                PendingEditConflictError if kind == "conflict" else ValueError
            )
        )
        with expected:
            service.apply_submission_decision(
                item.callback_token,
                decision,
                remote_signature=signature,
                remote_usage=encoded_usage,
            )
        db.expire_all()
        claim = db.get(AutonomousSubmissionClaim, item.claim_id)
        if kind == "success":
            assert claim.state == "completed"
            assert claim.completed_at is not None
            assert claim.attested_decision_digest is not None
            assert claim.review_run_id == remote_run_id
            assert db.get(AutonomousRun, remote_run_id) is not None
            assert db.get(Paper, 1).source_url == "https://example.com/proposed"
            row = db.get(PendingPaperEdit, row_id)
            assert row.status == "approved"
            assert row.review_run_id == remote_run_id
            assert db.query(CatalogMutationEvent).count() == 1
            continue
        assert claim.state == "claimed"
        assert claim.completed_at is None
        assert claim.attested_decision_digest is None
        assert claim.review_run_id is None
        assert db.get(AutonomousRun, remote_run_id) is None
        assert db.get(Paper, 1).title == original_title
        assert db.get(Paper, 1).source_url != "https://example.com/partial"
        row = db.get(PendingPaperEdit, row_id)
        assert row.status == "pending"
        assert bool(row.conflict_payload) == (kind == "conflict")
        assert bool(row.failure_reason) == (kind == "apply")
        assert row.review_run_id is None
        assert db.query(CatalogMutationEvent).count() == 0


@pytest.mark.parametrize("kind, status", [("conflict", 409), ("apply", 400)])
def test_human_route_preserves_error_responses_and_diagnostics(
    db_session, paper_fixture, monkeypatch, kind, status
):
    from backend.routers.pending_edits import approve_pending_paper_edit

    row_id = submit(db_session).id
    break_approval(db_session, monkeypatch, kind)
    with pytest.raises(HTTPException) as raised:
        approve_pending_paper_edit(
            edit_id=row_id,
            body=None,
            admin={"username": "admin", "hf_subject": "admin-subject"},
            db=db_session,
        )
    assert raised.value.status_code == status
    db_session.expire_all()
    row = db_session.get(PendingPaperEdit, row_id)
    assert bool(row.conflict_payload) == (kind == "conflict")
    assert bool(row.failure_reason) == (kind == "apply")
