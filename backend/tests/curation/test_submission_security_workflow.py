import asyncio
from types import SimpleNamespace

import pytest
from fastapi import Response
from starlette.requests import Request

from backend.cli import build_parser
from backend.cli_submissions import _validate_terminal_review
from backend.models.database import PendingPaperEdit
from backend.routers.papers import PaperSubmitRequest, submit_paper
from backend.services import paper_submission_service as paper_submission_module
from backend.services.pending_edit_errors import PendingEditError
from backend.services.pending_edit_payloads import validate_payload
from backend.services.thumbnail_service import ThumbnailService


def test_taxonomy_payloads_require_application_context():
    with pytest.raises(PendingEditError, match="both task_id and dataset_id"):
        validate_payload(
            "new_metric",
            {
                "name": "Score",
                "description": "Description",
                "direction": "higher_is_better",
                "task_id": 1,
            },
        )
    with pytest.raises(PendingEditError, match="source URL"):
        validate_payload("new_conference", {"name": "Venue 2027", "year": 2027})


def test_benchmark_suggestion_normalizes_free_text_names():
    payload = validate_payload(
        "new_benchmark",
        {
            "benchmark": "  New Benchmark  ",
            "task": "  Uncatalogued Task  ",
            "description": "  Administrative suggestion  ",
        },
    )
    assert payload == {
        "benchmark": "New Benchmark",
        "task": "Uncatalogued Task",
        "description": "Administrative suggestion",
    }


def test_taxonomy_payload_normalizes_typed_fields():
    payload = validate_payload(
        "new_metric",
        {
            "name": "  Accuracy ",
            "description": "  Correct predictions  ",
            "direction": "higher_is_better",
            "task_id": 7,
            "dataset_id": 9,
        },
    )
    assert payload == {
        "name": "Accuracy",
        "description": "Correct predictions",
        "direction": "higher_is_better",
        "task_id": 7,
        "dataset_id": 9,
    }


def test_external_paper_date_is_normalized_as_a_date():
    payload = validate_payload(
        "new_external_paper",
        {
            "source_url": "https://example.com/paper",
            "date_published": "2026-08-04",
        },
    )
    assert payload["date_published"] == "2026-08-04"

    with pytest.raises(PendingEditError, match="date_published is invalid"):
        validate_payload(
            "new_external_paper",
            {
                "source_url": "https://example.com/paper",
                "date_published": "2026-08-04T12:30:00",
            },
        )


def test_external_paper_submission_returns_pending_review_response(monkeypatch):
    submitted = SimpleNamespace(id=42)
    service = SimpleNamespace(submit=lambda **_kwargs: submitted)
    monkeypatch.setattr(
        paper_submission_module, "PendingEditService", lambda _db: service
    )

    result = asyncio.run(
        submit_paper(
            http_request=Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/v1/papers/submit",
                    "headers": [],
                    "client": ("127.0.0.1", 12345),
                }
            ),
            response=Response(),
            request=PaperSubmitRequest(source_url="https://example.com/paper"),
            idempotency_key=None,
            user={
                "username": "submitter",
                "hf_subject": "hf-subject",
                "role": "user",
            },
            db=object(),
        )
    )

    assert result.route_identifier is None
    assert result.submission_id == 42
    assert result.pending_review is True


def test_submission_cli_requires_explicit_environment():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["submissions", "list", "--json"])
    args = parser.parse_args(
        ["submissions", "show", "42", "--environment", "production", "--json"]
    )
    assert args.id == 42
    assert args.environment == "production"


def test_codex_terminal_decisions_require_current_high_confidence_evidence():
    artifact = {
        "decision": "approve",
        "rationale": "Verified",
        "sources": [{"url": "https://example.com/paper"}],
        "duplicate_checks": [],
        "confidence": 0.99,
        "unresolved_questions": [],
        "model": "test-model",
        "workflow_version": "v1",
        "codex_task_id": "task",
        "reviewed_revision": "sha256:abc",
        "material_changes": [],
    }
    row = PendingPaperEdit(
        edit_type="new_external_paper",
        proposed_payload={"source_url": "https://example.com/paper"},
        payload_hash="abc",
    )
    _validate_terminal_review(
        artifact,
        row,
        {
            "source_url": "https://example.com/paper",
            "title": "Paper",
            "date_published": "2026-08-18",
        },
    )

    stale = {**artifact, "reviewed_revision": "sha256:old"}
    with pytest.raises(ValueError, match="current submission revision"):
        _validate_terminal_review(stale, row, None)

    uncertain = {**artifact, "confidence": 0.8}
    with pytest.raises(ValueError, match="numeric confidence"):
        _validate_terminal_review(uncertain, row, None)

    unresolved = {**artifact, "unresolved_questions": ["Is this canonical?"]}
    with pytest.raises(ValueError, match="no unresolved questions"):
        _validate_terminal_review(unresolved, row, None)


def test_arbitrary_webpage_screenshots_are_disabled():
    assert not hasattr(ThumbnailService, "_capture_external_page_screenshot")
