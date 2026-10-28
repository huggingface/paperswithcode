"""
Regression tests for `PendingEditService.submit()` no-op detection.

Submissions that match the paper's current state must be rejected with a
`PendingEditError` so the /submissions admin dashboard isn't cluttered with
"empty" review cards. See `backend/services/pending_edit_service.py`.
"""

import argparse
import json
import uuid
from hashlib import sha256
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend import cli_submissions
from backend.config import Settings
from backend.models.curation import ApplyMutationRequest
from backend.models.database import (
    CatalogMutationEvent,
    PaperOrganization,
    PaperTask,
    PaperCurationSchedulerState,
    PaperCurationJob,
    PendingPaperEdit,
    TrendingModelCandidate,
    UserProfile,
)
from backend.models.database import (
    Conference as DBConference,
)
from backend.models.database import (
    Dataset as DBDataset,
)
from backend.models.database import (
    Method as DBMethod,
)
from backend.models.database import (
    Metric as DBMetric,
)
from backend.models.database import (
    Organization as DBOrganization,
)
from backend.models.database import (
    Paper as DBPaper,
)
from backend.models.database import (
    Task as DBTask,
)
from backend.routers.pending_edits import _to_response
from backend.services.autonomous_capabilities import AutonomousCapabilityDenied
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
    RunContext,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)
from backend.services.catalog_errors import CatalogConflictError
from backend.services.curation_autonomy import curation_run_context
from backend.services.pending_edit_service import (
    PendingEditAlreadyReviewedError,
    PendingEditConflictError,
    PendingEditError,
    PendingEditService,
    SubmissionRateLimitError,
    SubmissionSuspendedError,
)
from backend.services.pending_edit_payloads import validate_payload
from backend.services.submission_rollback_service import SubmissionRollbackService
from backend.tests.paper_edits import pending_harness

db_session = pending_harness.db_session
paper_fixture = pending_harness.paper_fixture
hf_organizations = pending_harness.hf_organizations


def _no_rows_created(db_session) -> None:
    assert db_session.query(PendingPaperEdit).count() == 0


def test_submit_tasks_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="tasks",
            proposed_payload={"task_ids": [2, 1]},  # same set, different order
        )
    _no_rows_created(db_session)


def test_submit_tasks_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1, 2, 3]},
    )
    assert row.id is not None
    assert row.status == "pending"
    assert row.proposed_payload == {"task_ids": [1, 2, 3]}


def test_approve_tasks_rebases_compatible_live_addition(db_session):
    db_session.add(
        DBPaper(
            id=2,
            title="P2",
            source="external",
            source_url="https://example.com/p2",
        )
    )
    db_session.add_all(
        [
            DBTask(id=1, name="Task A", slug="task-a", level=0),
            DBTask(id=2, name="Task B", slug="task-b", level=0),
            DBTask(id=3, name="Task C", slug="task-c", level=0),
        ]
    )
    db_session.commit()
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=2,
        hf_username="alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1, 2, 3]},
    )

    db_session.add(PaperTask(paper_id=2, task_id=1))
    db_session.commit()

    reviewed = service.approve(edit_id=row.id, reviewer_username="admin")

    task_ids = {
        item.task_id
        for item in db_session.query(PaperTask).filter(PaperTask.paper_id == 2)
    }
    assert task_ids == {1, 2, 3}
    assert reviewed.applied_payload == {"task_ids": [1, 2, 3]}
    assert reviewed.conflict_payload is None


def test_approve_tasks_rebase_preserves_unrelated_live_change(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=1,
        hf_username="alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [2]},
    )
    db_session.add(PaperTask(paper_id=1, task_id=3))
    db_session.commit()

    reviewed = service.approve(edit_id=row.id, reviewer_username="admin")

    task_ids = {
        item.task_id
        for item in db_session.query(PaperTask).filter(PaperTask.paper_id == 1)
    }
    assert task_ids == {2, 3}
    assert reviewed.applied_payload == {"task_ids": [2, 3]}


def test_approve_non_membership_edit_still_rejects_stale_snapshot(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=1,
        hf_username="alice",
        edit_type="source_url",
        proposed_payload={"source_url": "https://example.com/submitted"},
    )
    paper = db_session.get(DBPaper, 1)
    paper.source_url = "https://example.com/intervening"
    db_session.commit()

    with pytest.raises(
        PendingEditConflictError, match="Canonical state changed after submission"
    ):
        service.approve(edit_id=row.id, reviewer_username="admin")

    assert db_session.get(PendingPaperEdit, row.id).conflict_payload == {
        "submitted_snapshot": {
            "source_url": "https://example.com/paper",
            "source": "external",
        },
        "current_snapshot": {
            "source_url": "https://example.com/intervening",
            "source": "external",
        },
    }


def test_submit_methods_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="methods",
            proposed_payload={"method_ids": [10]},
        )
    _no_rows_created(db_session)


def test_submit_methods_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="methods",
        proposed_payload={"method_ids": [10, 11]},
    )
    assert row.id is not None


def test_submit_directory_taxonomy_suggestion_without_paper_succeeds(db_session):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={
            "name": "Long-context Retrieval",
            "description": "Retrieving evidence from very long contexts.",
        },
    )

    assert row.id is not None
    assert row.paper_id is None
    assert row.is_author is False
    assert row.current_payload == {}

    reviewed = service.approve(edit_id=row.id, reviewer_username="admin")
    assert reviewed.status == "approved"


def test_submit_task_suggestion_allows_omitted_description(db_session):
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={"name": "Long-context Retrieval"},
    )

    assert row.proposed_payload == {"name": "Long-context Retrieval"}


def test_submit_method_suggestion_accepts_image_and_sources(db_session):
    image_data_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4"
        "//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
    )
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_method",
        proposed_payload={
            "name": "New Attention",
            "description": " ",
            "image": {
                "file_name": " attention.png ",
                "mime_type": "image/png",
                "data_url": image_data_url,
            },
            "image_credit": " Example Research Group ",
            "source_url": " https://example.org/new-attention ",
        },
    )

    assert row.proposed_payload == {
        "name": "New Attention",
        "image": {
            "file_name": "attention.png",
            "mime_type": "image/png",
            "data_url": image_data_url,
        },
        "image_credit": "Example Research Group",
        "source_url": "https://example.org/new-attention",
    }
    response = _to_response(row)
    assert response.proposed_payload["image"] == {
        "file_name": "attention.png",
        "mime_type": "image/png",
        "url": f"/api/v1/admin/paper-edits/{row.id}/image",
    }
    assert row.proposed_payload["image"]["data_url"] == image_data_url


def test_submit_method_suggestion_rejects_invalid_source(db_session):
    with pytest.raises(PendingEditError, match="HTTP"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="new_method",
            proposed_payload={
                "name": "New Attention",
                "source_url": "javascript:alert(1)",
            },
        )
    _no_rows_created(db_session)


def test_submit_directory_conference_suggestion_without_paper_succeeds(db_session):
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_conference",
        proposed_payload={
            "name": "Conference on Long-context Research 2027",
            "year": 2027,
            "start_date": "2027-05-03",
            "end_date": "2027-05-07",
            "venue": " Vancouver Convention Centre ",
            "url": "https://example.org/conference",
        },
    )

    assert row.id is not None
    assert row.paper_id is None
    assert row.proposed_payload == {
        "name": "Conference on Long-context Research 2027",
        "year": 2027,
        "start_date": "2027-05-03",
        "end_date": "2027-05-07",
        "venue": "Vancouver Convention Centre",
        "url": "https://example.org/conference",
    }


def test_submit_directory_conference_suggestion_rejects_invalid_url(db_session):
    with pytest.raises(PendingEditError, match="HTTP"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="new_conference",
            proposed_payload={
                "name": "Conference on Long-context Research 2027",
                "year": 2027,
                "url": "example.org/conference",
            },
        )
    _no_rows_created(db_session)


def test_submit_non_taxonomy_edit_without_paper_rejects(db_session):
    with pytest.raises(PendingEditError, match="paper_id is required"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="tasks",
            proposed_payload={"task_ids": [1]},
        )
    _no_rows_created(db_session)


def test_submit_repositories_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="repositories",
            proposed_payload={
                "repositories": [
                    {"url": "https://github.com/owner/repo", "is_official": True},
                ]
            },
        )
    _no_rows_created(db_session)


def test_submit_repositories_is_official_flip_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="repositories",
        proposed_payload={
            "repositories": [
                {"url": "https://github.com/owner/repo", "is_official": False},
            ]
        },
    )
    assert row.id is not None


def test_submit_project_pages_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="project_pages",
            proposed_payload={
                "project_pages": [
                    {"url": "https://example.com/project", "is_official": False},
                ]
            },
        )
    _no_rows_created(db_session)


def test_submit_source_url_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="source_url",
            # Same URL with surrounding whitespace — should still be a no-op.
            proposed_payload={"source_url": "  https://example.com/paper  "},
        )
    _no_rows_created(db_session)


def test_submit_source_url_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="source_url",
        proposed_payload={"source_url": "https://example.com/paper/v2"},
    )
    assert row.id is not None
    assert row.proposed_payload == {"source_url": "https://example.com/paper/v2"}


def test_submit_hf_artifacts_noop_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="hf_artifacts",
            proposed_payload={
                "hf_models": [],
                "hf_datasets": [],
                "hf_spaces": [],
            },
        )
    _no_rows_created(db_session)


def test_submit_hf_artifacts_change_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="hf_artifacts",
        proposed_payload={
            "hf_models": ["https://huggingface.co/org/model-a"],
            "hf_datasets": ["https://huggingface.co/datasets/org/data-a"],
            "hf_spaces": ["https://huggingface.co/spaces/org/demo-a"],
        },
    )
    assert row.id is not None
    assert row.proposed_payload["hf_models"] == [
        "https://huggingface.co/org/model-a",
    ]


def test_submit_hf_artifacts_invalid_bucket_rejects(db_session, paper_fixture):
    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="not a Hugging Face model"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="hf_artifacts",
            proposed_payload={
                "hf_models": ["https://huggingface.co/datasets/org/data-a"],
                "hf_datasets": [],
                "hf_spaces": [],
            },
        )
    _no_rows_created(db_session)


def test_submit_tasks_empty_against_empty_paper_rejects(db_session):
    db_session.add(
        DBPaper(
            id=2,
            title="P2",
            abstract=None,
            source="external",
            source_url="https://example.com/p2",
            arxiv_id=None,
        )
    )
    db_session.commit()

    service = PendingEditService(db_session)
    with pytest.raises(PendingEditError, match="does not contain any changes"):
        service.submit(
            paper_id=2,
            hf_username="alice",
            edit_type="tasks",
            proposed_payload={"task_ids": []},
        )
    _no_rows_created(db_session)


def test_submit_evaluations_create_succeeds(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="evaluations",
        proposed_payload={
            "operations": [
                {
                    "op": "create",
                    "data": {
                        "task_id": 1,
                        "dataset_id": 99,
                        "model_name": "TestModel",
                        "metrics": {"Accuracy": "91.2"},
                        "best_metric": "Accuracy",
                        "is_open": True,
                    },
                }
            ]
        },
    )
    assert row.id is not None
    assert row.status == "pending"
    assert row.proposed_payload["operations"][0]["op"] == "create"


def test_adjusted_task_approval_is_administrative_and_idempotent(db_session):
    service = PendingEditService(db_session)
    submitted = service.submit(
        paper_id=None,
        hf_username="alice",
        hf_subject="hf-alice",
        edit_type="new_task",
        proposed_payload={"name": "Original task"},
    )
    reviewed = service.approve(
        edit_id=submitted.id,
        reviewer_username="admin",
        reviewer_hf_subject="hf-admin",
        resolved_payload={"name": "Reviewed task", "keywords": "reviewed"},
    )
    assert reviewed.status == "approved"
    assert reviewed.proposed_payload == {"name": "Original task"}
    assert reviewed.applied_payload == {"name": "Reviewed task", "keywords": "reviewed"}
    assert reviewed.result_entity_type is None
    assert reviewed.result_entity_id is None
    assert reviewed.catalog_event_id is None
    assert db_session.query(DBTask).count() == 0
    with pytest.raises(PendingEditAlreadyReviewedError):
        service.approve(edit_id=submitted.id, reviewer_username="admin")


def test_codex_cannot_approve_human_only_taxonomy(db_session):
    service = PendingEditService(db_session)
    submitted = service.submit(
        paper_id=None,
        hf_username="alice",
        hf_subject="hf-alice",
        edit_type="new_task",
        proposed_payload={"name": "Reviewed by Codex"},
    )
    run_id = uuid.uuid4()
    evidence = {"decision": "approve", "sources": ["https://example.com"]}

    with pytest.raises(PendingEditError, match="human-only taxonomy"):
        service.approve(
            edit_id=submitted.id,
            reviewer_username="Codex",
            reviewer_hf_subject=f"codex-review:{run_id}",
            reviewer_kind="codex",
            review_run_id=run_id,
            review_model="test-model",
            review_evidence=evidence,
        )
    db_session.expire_all()
    assert db_session.get(PendingPaperEdit, submitted.id).status == "pending"


def test_codex_cannot_reject_human_only_taxonomy(db_session):
    service = PendingEditService(db_session)
    submitted = service.submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_metric",
        proposed_payload={
            "name": "Human metric",
            "description": "Human review required",
            "direction": "higher_is_better",
            "task_id": 1,
            "dataset_id": 1,
        },
    )
    with pytest.raises(PendingEditError, match="human-only taxonomy"):
        service.reject(
            edit_id=submitted.id,
            reviewer_username="Codex",
            reviewer_kind="codex",
        )
    db_session.expire_all()
    assert db_session.get(PendingPaperEdit, submitted.id).status == "pending"


def test_real_manual_mode_blocks_codex_pending_edit_mutation(db_session, paper_fixture):
    submitted = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1, 3]},
    )
    context = RunContext(uuid.uuid4(), Operator.SUBMISSIONS, False, "policy-v1")
    AutonomousOperationsRepository().append_run(
        db_session,
        context=context,
        status="completed",
        now=datetime.now(timezone.utc),
    )

    with pytest.raises(AutonomousCapabilityDenied, match="manual_mode"):
        PendingEditService(db_session).approve(
            edit_id=submitted.id,
            reviewer_username="Codex",
            reviewer_kind="codex",
            autonomous_context=context,
        )
    db_session.rollback()
    assert db_session.get(PendingPaperEdit, submitted.id).status == "pending"


def test_enabled_codex_review_uses_typed_existing_taxonomy_adapter(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    submitted = service.submit(
        paper_id=1,
        hf_username="alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1, 3]},
    )
    context = RunContext(uuid.uuid4(), Operator.SUBMISSIONS, False, "policy-v1")
    operations = AutonomousOperationsRepository()
    operations.append_run(
        db_session,
        context=context,
        status="completed",
        now=datetime.now(timezone.utc),
    )
    state = operations.get_control_state(db_session)
    operations.set_manual_mode(
        db_session,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:test",
        now=datetime.now(timezone.utc),
    )
    state = operations.get_control_state(db_session)
    operations.set_operator_enabled(
        db_session,
        operator=Operator.SUBMISSIONS,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:test",
        now=datetime.now(timezone.utc),
    )

    reviewed = service.approve(
        edit_id=submitted.id,
        reviewer_username="Codex",
        reviewer_kind="codex",
        autonomous_context=context,
    )
    assert reviewed.status == "approved"
    assert {
        row.task_id
        for row in db_session.query(PaperTask).filter(PaperTask.paper_id == 1)
    } == {1, 3}


def test_real_manual_mode_blocks_scheduled_curation_callback(db_session, paper_fixture):
    context = RunContext(uuid.uuid4(), Operator.SUBMISSIONS, False, "curation-v1")
    AutonomousOperationsRepository().append_run(
        db_session,
        context=context,
        status="completed",
        now=datetime.now(timezone.utc),
    )
    row = SimpleNamespace(
        kind="enrich-paper",
        paper_id=1,
        trigger="hf-daily-cron",
    )
    body = SimpleNamespace(
        enrich=SimpleNamespace(task_ids=[1], method_ids=[]),
        evaluations=[],
    )
    with pytest.raises(AutonomousCapabilityDenied, match="manual_mode"):
        CodexCurationCallbackService(db_session).authorize_autonomous_callback(
            row, body, context=context
        )


def test_pausing_dispatch_does_not_revoke_an_inflight_curation_callback(
    db_session, paper_fixture
):
    operations = AutonomousOperationsRepository()
    state = operations.get_control_state(db_session)
    state = operations.set_manual_mode(
        db_session,
        enabled=False,
        expected_revision=state.revision,
        actor="admin:test",
        now=datetime.now(timezone.utc),
    )
    operations.set_operator_enabled(
        db_session,
        operator=Operator.CURATION,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:test",
        now=datetime.now(timezone.utc),
    )
    candidate = TrendingModelCandidate(
        repo_id="org/paused-canary-model",
        author="org",
        readme_sha="a" * 64,
        status="resolving",
    )
    db_session.add(candidate)
    db_session.flush()
    row = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        candidate_id=candidate.id,
        requested_by="hf-trending-cron",
        trigger="hf-trending-cron",
        policy_version="hf-trending-v1",
        priority=25,
        status="running",
    )
    db_session.add(row)
    context = curation_run_context(row)
    operations.append_run(
        db_session,
        context=context,
        status="completed",
        now=datetime.now(timezone.utc),
    )
    db_session.add(
        PaperCurationSchedulerState(
            id=1,
            dispatch_enabled=False,
            paused_at=datetime.now(timezone.utc),
            pause_condition="operator",
            pause_reason="canary observation",
        )
    )
    db_session.commit()

    result = CodexCurationCallbackService(db_session).apply(
        row,
        ApplyMutationRequest.model_validate(
            {
                "resolve_model_paper": {
                    "decision": "reject",
                    "reason": "The repository only repackages existing weights.",
                    "novelty_kind": "repackaging",
                    "evidence_urls": ["https://huggingface.co/org/paused-canary-model"],
                }
            }
        ),
        autonomous_context=context,
    )

    assert result["status"] == "rejected"
    assert row.applied_at is not None
    assert candidate.status == "rejected"


def test_codex_cli_applies_terminal_approval(db_session, tmp_path, monkeypatch):
    submitted = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        hf_subject="hf-alice",
        edit_type="new_task",
        proposed_payload={"name": "CLI-reviewed task"},
    )
    artifact = {
        "decision": "approve",
        "rationale": "Canonical task verified from the cited source.",
        "sources": [{"url": "https://example.com/task"}],
        "duplicate_checks": [],
        "confidence": 0.99,
        "unresolved_questions": [],
        "model": "test-model",
        "workflow_version": "v1",
        "codex_task_id": "task",
        "reviewed_revision": f"sha256:{submitted.payload_hash}",
        "material_changes": [],
    }
    review_file = tmp_path / "review.json"
    review_file.write_text(json.dumps(artifact))
    run_id = uuid.uuid4()
    monkeypatch.setattr(
        cli_submissions,
        "db_manager",
        SimpleNamespace(session_local=lambda: nullcontext(db_session)),
    )
    monkeypatch.setattr(
        cli_submissions,
        "_verified_database",
        lambda _db, selected: {"selected_environment": selected},
    )

    with pytest.raises(PendingEditError, match="human-only taxonomy"):
        cli_submissions.decide_submission(
            argparse.Namespace(
                id=submitted.id,
                environment="production",
                decision="approve",
                resolved_payload_file=None,
                review_file=review_file,
                review_run_id=run_id,
                confirm="APPLY_SUBMISSION_REVIEW",
                json=True,
            )
        )

    db_session.expire_all()
    reviewed = db_session.get(PendingPaperEdit, submitted.id)
    assert reviewed.status == "pending"


def test_taxonomy_approval_does_not_apply_duplicate_name(db_session, paper_fixture):
    row = PendingEditService(db_session).submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_task",
        proposed_payload={"name": "Task A"},
    )
    reviewed = PendingEditService(db_session).approve(
        edit_id=row.id, reviewer_username="admin"
    )
    assert reviewed.status == "approved"
    assert reviewed.result_entity_id is None
    assert db_session.query(DBTask).filter(DBTask.name == "Task A").count() == 1


def test_external_paper_approval_uses_submission_date_when_undated(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    submitted = service.submit(
        paper_id=None,
        hf_username="external-paper-user",
        edit_type="new_external_paper",
        proposed_payload={
            "source_url": "https://example.org/undated-external-paper",
            "title": "An Undated External Paper",
            "authors": ["Example Author"],
        },
    )
    submitted.created_at = datetime(2026, 8, 4, 23, 59, tzinfo=timezone.utc)
    db_session.commit()

    reviewed = service.approve(edit_id=submitted.id, reviewer_username="admin")

    assert reviewed.proposed_payload.get("date_published") is None
    assert reviewed.applied_payload["date_published"] == "2026-08-04"
    paper = db_session.get(DBPaper, int(reviewed.result_entity_id))
    assert paper.date_published.isoformat() == "2026-08-04"


@pytest.mark.parametrize(
    ("edit_type", "payload", "model"),
    [
        ("new_task", {"name": "Suggested Task"}, DBTask),
        (
            "new_method",
            {"name": "Suggested Method", "source_url": "https://example.org/method"},
            DBMethod,
        ),
        (
            "new_benchmark",
            {
                "benchmark": "Suggested Benchmark",
                "task": "Uncatalogued Task",
                "description": "A benchmark suggestion.",
            },
            DBDataset,
        ),
        (
            "new_metric",
            {
                "name": "Suggested Score",
                "description": "A score suggestion.",
                "direction": "higher_is_better",
                "task_id": 1,
                "dataset_id": 1,
            },
            DBMetric,
        ),
        (
            "new_conference",
            {
                "name": "Suggested Conference 2027",
                "year": 2027,
                "url": "https://example.org/conference-2027",
            },
            DBConference,
        ),
    ],
)
def test_taxonomy_approval_is_administrative_only(
    db_session, edit_type, payload, model
):
    service = PendingEditService(db_session)
    count_before = db_session.query(model).count()
    submission = service.submit(
        paper_id=None,
        hf_username="taxonomy-user",
        edit_type=edit_type,
        proposed_payload=payload,
    )
    reviewed = service.approve(edit_id=submission.id, reviewer_username="admin")

    assert reviewed.status == "approved"
    assert reviewed.applied_payload == validate_payload(edit_type, payload)
    assert reviewed.result_entity_type is None
    assert reviewed.result_entity_id is None
    assert reviewed.catalog_event_id is None
    assert db_session.query(model).count() == count_before


def test_benchmark_approval_with_source_paper_is_administrative(
    db_session, paper_fixture
):
    submission = PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="benchmark-user",
        edit_type="new_benchmark",
        proposed_payload={
            "benchmark": "Paper-Scoped Benchmark",
            "task": "Uncatalogued Task",
            "description": "A benchmark proposed from its source paper.",
        },
    )

    reviewed = PendingEditService(db_session).approve(
        edit_id=submission.id, reviewer_username="admin"
    )

    assert reviewed.status == "approved"
    assert reviewed.paper_id == 1
    assert reviewed.result_entity_id is None
    assert reviewed.catalog_event_id is None
    assert db_session.query(DBDataset).count() == 0


def test_created_entity_rollback_is_append_only(db_session):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_external_paper",
        proposed_payload={
            "title": "Rollback paper",
            "source_url": "https://example.org/rollback-paper",
            "authors": [],
        },
    )
    row = service.approve(edit_id=row.id, reviewer_username="admin")
    event = db_session.get(CatalogMutationEvent, row.catalog_event_id)
    paper_id = int(row.result_entity_id)
    rollback = SubmissionRollbackService(db_session).rollback(
        event=event,
        actor={"hf_subject": "hf-admin", "username": "admin", "role": "admin"},
        request_id="test-rollback",
    )
    assert db_session.get(DBPaper, paper_id) is None
    assert rollback.operation == "rollback"
    assert rollback.rollback_of_event_id == event.id
    assert db_session.get(PendingPaperEdit, row.id).status == "approved"


def test_created_entity_rollback_refuses_after_later_dependency(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    row = service.submit(
        paper_id=None,
        hf_username="alice",
        edit_type="new_external_paper",
        proposed_payload={
            "title": "Now referenced",
            "source_url": "https://example.org/now-referenced",
            "authors": [],
        },
    )
    row = service.approve(edit_id=row.id, reviewer_username="admin")
    event = db_session.get(CatalogMutationEvent, row.catalog_event_id)
    paper_id = int(row.result_entity_id)
    db_session.add(PaperTask(paper_id=paper_id, task_id=1))
    db_session.commit()
    with pytest.raises(CatalogConflictError, match="stale_catalog_version"):
        SubmissionRollbackService(db_session).rollback(
            event=event,
            actor={"hf_subject": "hf-admin", "username": "admin", "role": "admin"},
            request_id="test-conflict",
        )
    assert db_session.get(DBPaper, paper_id) is not None


def test_active_submission_limit_is_database_backed(
    db_session, paper_fixture, monkeypatch
):
    current = Settings(submission_max_active_pending=1)
    monkeypatch.setattr(
        "backend.services.pending_edit_service.get_settings", lambda: current
    )
    service = PendingEditService(db_session)
    service.submit(
        paper_id=1,
        hf_username="alice",
        hf_subject="hf-alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1]},
    )
    with pytest.raises(SubmissionRateLimitError, match="Active pending"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            hf_subject="hf-alice",
            edit_type="methods",
            proposed_payload={"method_ids": [10, 11]},
        )


def test_idempotent_replay_does_not_create_another_row(db_session, paper_fixture):
    service = PendingEditService(db_session)
    first = service.submit(
        paper_id=1,
        hf_username="alice",
        hf_subject="hf-alice",
        idempotency_key="same-request",
        edit_type="tasks",
        proposed_payload={"task_ids": [1]},
    )
    replay = service.submit(
        paper_id=1,
        hf_username="alice",
        hf_subject="hf-alice",
        idempotency_key="same-request",
        edit_type="tasks",
        proposed_payload={"task_ids": [1]},
    )
    assert replay.id == first.id
    assert db_session.query(PendingPaperEdit).count() == 1
    with pytest.raises(PendingEditError, match="another payload"):
        service.submit(
            paper_id=1,
            hf_username="alice",
            hf_subject="hf-alice",
            idempotency_key="same-request",
            edit_type="tasks",
            proposed_payload={"task_ids": [1, 2, 3]},
        )


def test_suspension_blocks_new_submission_without_deleting_history(
    db_session, paper_fixture
):
    service = PendingEditService(db_session)
    existing = service.submit(
        paper_id=1,
        hf_username="alice",
        hf_subject="hf-alice",
        edit_type="tasks",
        proposed_payload={"task_ids": [1]},
    )
    profile = db_session.get(UserProfile, "hf-alice")
    profile.is_submission_suspended = True
    db_session.commit()
    with pytest.raises(SubmissionSuspendedError):
        service.submit(
            paper_id=1,
            hf_username="alice",
            hf_subject="hf-alice",
            edit_type="methods",
            proposed_payload={"method_ids": [10, 11]},
        )
    assert db_session.get(PendingPaperEdit, existing.id).status == "pending"


@pytest.mark.parametrize("substantive_change", [False, True])
def test_evaluation_approval_ignores_only_recalculated_rank(
    db_session, paper_fixture, monkeypatch, substantive_change
):
    from unittest.mock import Mock

    submitted = {
        "evaluations": [{"id": 42, "best_rank": 10, "metrics": {"Accuracy": 66.12}}]
    }
    current = {
        "evaluations": [
            {
                "id": 42,
                "best_rank": 11,
                "metrics": {"Accuracy": 67 if substantive_change else 66.12},
            }
        ]
    }
    service = PendingEditService(db_session)
    monkeypatch.setattr(service.snapshots, "paper_edit", lambda *args: submitted)
    row = service.submit(
        paper_id=1,
        hf_username="alice",
        edit_type="evaluations",
        proposed_payload={
            "operations": [
                {
                    "op": "update",
                    "evaluation_id": 42,
                    "data": {"metrics": {"Accuracy": "65.9"}},
                }
            ]
        },
    )
    row.conflict_payload = {
        "submitted_snapshot": submitted,
        "current_snapshot": current,
    }
    db_session.commit()
    monkeypatch.setattr(service.snapshots, "paper_edit", lambda *args: current)
    monkeypatch.setattr(
        service.snapshots, "approval_event", lambda *args, **kwargs: current
    )
    apply = Mock(return_value=("paper", "1"))
    monkeypatch.setattr(service.mutations, "apply_human_review", apply)

    if substantive_change:
        with pytest.raises(PendingEditConflictError):
            service.approve(edit_id=row.id, reviewer_username="admin")
        apply.assert_not_called()
        assert row.status == "pending"
    else:
        reviewed = service.approve(edit_id=row.id, reviewer_username="admin")
        assert reviewed.status == "approved"
        assert reviewed.conflict_payload is None
        assert reviewed.current_payload == submitted
        assert reviewed.catalog_event_id is not None
        apply.assert_called_once()


@pytest.mark.parametrize("stage", ["submit", "approve_stored"])
def test_malformed_evaluation_batch_rejected_without_partial_acceptance(
    db_session, paper_fixture, monkeypatch, stage
):
    from unittest.mock import Mock

    service = PendingEditService(db_session)
    valid = {
        "op": "create",
        "data": {
            "task_id": 1,
            "dataset_id": 99,
            "metrics": {"Accuracy": 0},
            "best_metric": "Accuracy",
        },
    }
    invalid = {
        "op": "create",
        "data": {
            **valid["data"],
            "num_parameters": -1,
        },
    }
    payload = {"operations": [valid, invalid]}
    apply = Mock()
    monkeypatch.setattr(service.mutations, "apply_human_review", apply)
    if stage == "submit":
        with pytest.raises(PendingEditError, match=r"operations\[1\]"):
            service.submit(
                paper_id=1,
                hf_username="alice",
                edit_type="evaluations",
                proposed_payload=payload,
            )
        assert db_session.query(PendingPaperEdit).count() == 0
    else:
        row = service.submit(
            paper_id=1,
            hf_username="alice",
            edit_type="evaluations",
            proposed_payload={"operations": [valid]},
        )
        # Simulate a stored proposal accepted before canonical validation.
        row.proposed_payload = payload
        db_session.commit()
        with pytest.raises(PendingEditError, match=r"operations\[1\]"):
            service.approve(edit_id=row.id, reviewer_username="admin")
        assert row.status == "pending"
        assert row.applied_payload is None
    apply.assert_not_called()


LOGO_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4"
    "//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)


def _organization_suggestion(db_session, **overrides):
    payload = {
        "name": "Prime Intellect",
        "hf_slug": "https://huggingface.co/PrimeIntellect/",
        "website_url": "https://www.primeintellect.ai/",
        "image": {
            "file_name": "logo.png",
            "mime_type": "image/png",
            "data_url": LOGO_DATA_URL,
        },
        **overrides,
    }
    return PendingEditService(db_session).submit(
        paper_id=1,
        hf_username="alice",
        hf_subject="hf-alice",
        edit_type="new_organization",
        proposed_payload=payload,
    )


def test_organization_suggestion_approval_creates_and_tags_paper(
    db_session, paper_fixture
):
    row = _organization_suggestion(db_session)
    assert row.proposed_payload["hf_slug"] == "PrimeIntellect"

    reviewed = PendingEditService(db_session).approve(
        edit_id=row.id, reviewer_username="admin"
    )

    organization = db_session.get(DBOrganization, int(reviewed.result_entity_id))
    assert reviewed.result_entity_type == "organization"
    assert (organization.slug, organization.hf_slug, organization.hf_url) == (
        "prime-intellect",
        "PrimeIntellect",
        "https://huggingface.co/PrimeIntellect",
    )
    assert organization.website_url.startswith("https://www.primeintellect.ai")
    assert organization.logo_mime_type == "image/png"
    assert organization.logo_sha256 == sha256(organization.logo_data).hexdigest()
    assert organization.is_featured is False
    link = db_session.get(PaperOrganization, (1, organization.id))
    assert (link.source, link.added_by_hf_username) == ("manual", "alice")

    event = db_session.get(CatalogMutationEvent, reviewed.catalog_event_id)
    assert event.entity_type == "submission_created_organization"
    assert event.after_snapshot["paper_ids"] == [1]


def test_organization_suggestion_requires_hf_handle_or_website(db_session):
    with pytest.raises(PendingEditError, match="Hugging Face handle or a website"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="new_organization",
            proposed_payload={"name": "Prime Intellect"},
        )
    _no_rows_created(db_session)


def test_organization_suggestion_approval_refuses_existing_hf_handle(
    db_session, paper_fixture
):
    db_session.add(DBOrganization(name="Prime", slug="prime", hf_slug="primeintellect"))
    db_session.commit()
    row = _organization_suggestion(db_session)

    with pytest.raises(PendingEditError, match="/organizations/prime"):
        PendingEditService(db_session).approve(
            edit_id=row.id, reviewer_username="admin"
        )


def test_organization_suggestion_slug_falls_back_to_hf_handle(
    db_session, paper_fixture
):
    row = _organization_suggestion(db_session, name="智谱", hf_slug="zai-org")
    reviewed = PendingEditService(db_session).approve(
        edit_id=row.id, reviewer_username="admin"
    )
    organization = db_session.get(DBOrganization, int(reviewed.result_entity_id))
    assert (organization.name, organization.slug) == ("智谱", "zai-org")


def test_organization_suggestion_rejects_unsluggable_name_without_handle(
    db_session,
):
    with pytest.raises(PendingEditError, match="Latin letters or digits"):
        PendingEditService(db_session).submit(
            paper_id=None,
            hf_username="alice",
            edit_type="new_organization",
            proposed_payload={"name": "智谱", "website_url": "https://example.org"},
        )
    _no_rows_created(db_session)
