"""Repository-only, evidence-backed submission review CLI."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import AutonomousRun, PendingPaperEdit
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
    RunContext,
)
from backend.services.autonomous_submission_service import AutonomousSubmissionService
from backend.services.catalog_mutation_service import json_safe
from backend.services.pending_edit_service import PendingEditService
from backend.services.pending_edit_snapshots import PendingEditSnapshotService

TERMINAL_DECISIONS = frozenset({"approve", "reject"})
MIN_TERMINAL_CONFIDENCE = 0.9


def register_submission_commands(commands) -> None:
    submissions = commands.add_parser(
        "submissions", help="Inspect the community submission queue"
    )
    subcommands = submissions.add_subparsers(dest="submissions_command", required=True)
    listing = subcommands.add_parser("list")
    _environment_argument(listing)
    listing.add_argument("--status", choices=["pending", "approved", "rejected"])
    listing.add_argument("--limit", type=int, default=50, choices=range(1, 101))
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(handler=list_submissions)

    show = subcommands.add_parser("show")
    show.add_argument("id", type=int)
    _environment_argument(show)
    show.add_argument("--json", action="store_true")
    show.set_defaults(handler=show_submission)

    decide = subcommands.add_parser("decide")
    decide.add_argument("id", type=int)
    _environment_argument(decide)
    decide.add_argument(
        "--decision", required=True, choices=["approve", "reject", "needs-human"]
    )
    decide.add_argument("--resolved-payload-file", type=Path)
    decide.add_argument("--review-file", type=Path, required=True)
    decide.add_argument("--review-run-id", type=uuid.UUID, required=True)
    decide.add_argument("--confirm", required=True, choices=["APPLY_SUBMISSION_REVIEW"])
    decide.add_argument("--json", action="store_true")
    decide.set_defaults(handler=decide_submission)

    autonomous_batch = subcommands.add_parser("autonomous-batch")
    _environment_argument(autonomous_batch)
    autonomous_batch.add_argument("--run-id", type=uuid.UUID, required=True)
    autonomous_batch.add_argument("--limit", type=int, default=25, choices=range(1, 26))
    autonomous_batch.add_argument("--manifest-file", type=Path, required=True)
    autonomous_batch.set_defaults(handler=build_autonomous_batch)


def _environment_argument(parser) -> None:
    parser.add_argument(
        "--environment", required=True, choices=["production", "staging"]
    )


def _verified_database(db, selected: str) -> dict:
    settings = get_settings()
    row = db.execute(
        text("SELECT current_user, current_schema(), current_schemas(false)")
    ).one()
    expected_schema = "staging" if selected == "staging" else "public"
    identity = {
        "selected_environment": selected,
        "configured_environment": settings.environment,
        "database_role": row[0],
        "database_schema": row[1],
        "search_path_schemas": list(row[2]),
    }
    if settings.environment != selected:
        raise ValueError("Selected environment does not match PWC_ENVIRONMENT")
    if row[0] != settings.db_user or row[1] != expected_schema:
        raise ValueError("Database role/schema does not match the selected environment")
    return identity


def _serialize(row: PendingPaperEdit) -> dict:
    return {
        "id": row.id,
        "paper_id": row.paper_id,
        "hf_subject": row.hf_subject,
        "hf_username": row.hf_username,
        "is_author": row.is_author,
        "edit_type": row.edit_type,
        "status": row.status,
        "proposed_payload": row.proposed_payload,
        "current_payload": row.current_payload,
        "applied_payload": row.applied_payload,
        "result_entity_type": row.result_entity_type,
        "result_entity_id": row.result_entity_id,
        "conflict_payload": row.conflict_payload,
        "reviewed_by_kind": row.reviewed_by_kind,
        "review_run_id": str(row.review_run_id) if row.review_run_id else None,
        "review_model": row.review_model,
        "review_evidence": row.review_evidence,
        "created_at": row.created_at,
        "reviewed_at": row.reviewed_at,
    }


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(json_safe(payload), indent=2, sort_keys=True))
    else:
        print(json.dumps(json_safe(payload), sort_keys=True))


def list_submissions(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        identity = _verified_database(db, args.environment)
        rows, total = PendingEditService(db).list_edits(
            status=args.status, limit=args.limit
        )
        _emit(
            {
                "database": identity,
                "count": total,
                "results": [_serialize(row) for row in rows],
            },
            args.json,
        )
    return 0


def show_submission(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        identity = _verified_database(db, args.environment)
        service = PendingEditService(db)
        row = service.get(args.id)
        current = (
            PendingEditSnapshotService(db).paper_edit(row.paper_id, row.edit_type)
            if row.paper_id is not None
            else {}
        )
        _emit(
            {
                "database": identity,
                "submission": _serialize(row),
                "canonical_now": current,
            },
            args.json,
        )
    return 0


def build_autonomous_batch(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.autonomous_submission_enabled:
        raise ValueError("Autonomous submission review is disabled")
    with db_manager.session_local() as db:
        _verified_database(db, args.environment)
        service = AutonomousSubmissionService(
            db,
            signing_secret=settings.autonomous_submission_callback_secret.encode(),
            callback_base_url=settings.autonomous_submission_callback_base_url,
        )
        batch = service.claim_submission_batch(args.run_id, limit=args.limit)
        if not batch:
            _emit({"run_id": str(args.run_id), "claimed": 0}, True)
            return 0
        manifest = service.build_submission_manifest(batch)
        service.write_manifest(args.manifest_file, manifest)
        _emit(
            {
                "run_id": str(args.run_id),
                "claimed": len(batch),
                "manifest_file": str(args.manifest_file),
            },
            True,
        )
    return 0


def _load_review(args: argparse.Namespace) -> dict:
    if args.review_file.stat().st_size > 131_072:
        raise ValueError("Review artifact exceeds 128 KiB")
    artifact = json.loads(args.review_file.read_text())
    if not isinstance(artifact, dict):
        raise ValueError("Review artifact must be a JSON object")
    required = {
        "decision",
        "rationale",
        "sources",
        "duplicate_checks",
        "confidence",
        "unresolved_questions",
        "model",
        "workflow_version",
        "codex_task_id",
        "reviewed_revision",
        "material_changes",
    }
    missing = sorted(required - artifact.keys())
    if missing:
        raise ValueError(f"Review artifact is missing: {', '.join(missing)}")
    normalized_decision = args.decision.replace("-", "_")
    if artifact["decision"] != normalized_decision:
        raise ValueError("Review artifact decision does not match --decision")
    return artifact


def _validate_terminal_review(
    artifact: dict, row: PendingPaperEdit, resolved_payload: dict | None
) -> None:
    if not isinstance(artifact["sources"], list) or not artifact["sources"]:
        raise ValueError("Terminal decisions require at least one evidence source")
    if not isinstance(artifact["duplicate_checks"], list):
        raise ValueError("duplicate_checks must be a list")
    if not isinstance(artifact["material_changes"], list):
        raise ValueError("material_changes must be a list")
    questions = artifact["unresolved_questions"]
    if not isinstance(questions, list) or questions:
        raise ValueError("Terminal decisions require no unresolved questions")
    confidence = artifact["confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not MIN_TERMINAL_CONFIDENCE <= confidence <= 1
    ):
        raise ValueError(
            f"Terminal decisions require numeric confidence >= {MIN_TERMINAL_CONFIDENCE}"
        )
    expected_revision = f"sha256:{row.payload_hash}"
    if not row.payload_hash or artifact["reviewed_revision"] != expected_revision:
        raise ValueError(
            "Review artifact does not match the current submission revision"
        )
    for field in ("rationale", "model", "workflow_version", "codex_task_id"):
        if not isinstance(artifact[field], str) or not artifact[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    if row.edit_type == "new_external_paper" and artifact["decision"] == "approve":
        payload = resolved_payload or row.proposed_payload
        if (
            not isinstance(payload, dict)
            or not payload.get("title")
            or not payload.get("date_published")
        ):
            raise ValueError(
                "External-paper approval requires a resolved title and publication date"
            )


def decide_submission(args: argparse.Namespace) -> int:
    artifact = _load_review(args)
    resolved_payload = None
    if args.resolved_payload_file:
        resolved_payload = json.loads(args.resolved_payload_file.read_text())
    with db_manager.session_local() as db:
        identity = _verified_database(db, args.environment)
        row = (
            db.query(PendingPaperEdit)
            .filter(PendingPaperEdit.id == args.id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise ValueError("Submission not found")
        evidence = {**artifact, "resolved_payload": resolved_payload}
        expected_status = (
            "approved"
            if args.decision == "approve"
            else "rejected"
            if args.decision == "reject"
            else "pending"
        )
        if row.review_run_id == args.review_run_id and row.review_evidence == evidence:
            if row.status != expected_status:
                raise ValueError("Review run is already attached to another decision")
            _emit({"database": identity, "submission": _serialize(row)}, args.json)
            return 0
        if row.status != "pending":
            raise ValueError(f"Submission is already {row.status}")

        if args.decision in TERMINAL_DECISIONS:
            _validate_terminal_review(artifact, row, resolved_payload)
            context = RunContext(
                run_id=args.review_run_id,
                operator=Operator.SUBMISSIONS,
                dry_run=False,
                manifest_revision=str(artifact["workflow_version"]),
            )
            operations = AutonomousOperationsRepository()
            if db.get(AutonomousRun, context.run_id) is None:
                operations.append_run(
                    db,
                    context=context,
                    status="completed",
                    now=datetime.now(timezone.utc),
                )
            else:
                operations.assert_run_context(db, context)
            # Run summaries are monitoring/audit data and remain durable even
            # when manual mode blocks the subsequent mutation.
            db.commit()
            service = PendingEditService(db)
            reviewer_subject = f"codex-review:{args.review_run_id}"
            review_kwargs = {
                "edit_id": row.id,
                "reviewer_username": "Codex",
                "reviewer_hf_subject": reviewer_subject,
                "reviewer_kind": "codex",
                "review_run_id": args.review_run_id,
                "review_model": str(artifact["model"])[:255],
                "review_evidence": evidence,
                "autonomous_context": context,
                "admin_note": artifact["rationale"],
                "user_review_reason": artifact.get("user_review_reason")
                or (artifact["rationale"] if args.decision == "reject" else None),
            }
            if args.decision == "approve":
                row = service.approve(
                    **review_kwargs, resolved_payload=resolved_payload
                )
            else:
                row = service.reject(**review_kwargs)
            _emit({"database": identity, "submission": _serialize(row)}, args.json)
            return 0

        # A defer/needs-human result deliberately leaves the human queue row
        # untouched. The autonomous run ledger records execution separately.
        _emit({"database": identity, "submission": _serialize(row)}, args.json)
    return 0
