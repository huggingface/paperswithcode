#!/usr/bin/env python3
"""Qualify durable turn dispatch without invoking a chat execution runtime."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatSession, ChatTurnJob
from backend.services.chat_turn_job_repository import (
    AccountBusy,
    ChatOverload,
    ChatTurnJobRepository,
    StaleTurnClaim,
    TurnLeaseClaim,
)
from deploy.release import validate_manifest

CONFIRMATION = "QUALIFY_STAGING_DURABLE_DISPATCH"
RELEASE_ROOT = Path("/srv/paperswithcode/releases")
ACTIVE_STAGING_RELEASE = Path("/srv/paperswithcode/environments/staging/current")
_STAGING_RELEASE_NAME = re.compile(r"^[0-9a-f]{12}-staging$")
EXPECTED_OUTCOMES = {
    "idempotent_admission": "replayed",
    "same_owner_contention": "account_busy",
    "global_capacity": "chat_overload",
    "claim_heartbeat_transition": "waiting_model",
    "stale_fence": "stale_turn_claim",
    "terminal_write": "completed",
    "expiry_interruption": "lease_expired",
}
EXPECTED_INDEX_DEFINITIONS = {
    "idx_chat_turn_jobs_claim": {
        "columns": ["state", "admitted_at", "turn_id"],
        "included_columns": [],
        "predicate": None,
        "unique": False,
        "valid": True,
        "ready": True,
    },
    "idx_chat_turn_jobs_expiry": {
        "columns": ["state", "lease_expires_at"],
        "included_columns": [],
        "predicate": None,
        "unique": False,
        "valid": True,
        "ready": True,
    },
    "uq_chat_turn_jobs_nonterminal_owner": {
        "columns": ["hf_user_id"],
        "included_columns": [],
        "predicate": (
            "state::text = ANY (ARRAY['admitted'::character varying, "
            "'leased'::character varying, 'running'::character varying, "
            "'waiting_model'::character varying, "
            "'waiting_tool'::character varying, "
            "'cancelling'::character varying]::text[])"
        ),
        "unique": True,
        "valid": True,
        "ready": True,
    },
}
EXPECTED_CONSTRAINT_DEFINITIONS = {
    "chat_turn_jobs_pkey": {
        "kind": "p",
        "validated": True,
        "definition": "PRIMARY KEY (turn_id)",
    },
    "chat_turn_jobs_request_id_key": {
        "kind": "u",
        "validated": True,
        "definition": "UNIQUE (request_id)",
    },
    "chat_turn_jobs_chat_session_id_fkey": {
        "kind": "f",
        "validated": True,
        "definition": (
            "FOREIGN KEY (chat_session_id) REFERENCES "
            "chat_sessions(id) ON DELETE CASCADE"
        ),
        "reference_schema": "staging",
    },
    "chat_turn_jobs_revision_check": {
        "kind": "c",
        "validated": True,
        "definition": "CHECK (revision > 0)",
    },
    "chat_turn_jobs_worker_generation_check": {
        "kind": "c",
        "validated": True,
        "definition": "CHECK (worker_generation IS NULL OR worker_generation > 0)",
    },
    "chat_turn_jobs_lease_generation_check": {
        "kind": "c",
        "validated": True,
        "definition": "CHECK (lease_generation IS NULL OR lease_generation > 0)",
    },
    "chat_turn_jobs_state_check": {
        "kind": "c",
        "validated": True,
        "definition": (
            "CHECK (state::text = ANY (ARRAY['admitted'::character varying, "
            "'leased'::character varying, 'running'::character varying, "
            "'waiting_model'::character varying, "
            "'waiting_tool'::character varying, "
            "'cancelling'::character varying, 'completed'::character varying, "
            "'failed'::character varying, "
            "'interrupted'::character varying]::text[]))"
        ),
    },
    "chat_turn_jobs_lease_fields_check": {
        "kind": "c",
        "validated": True,
        "definition": (
            "CHECK (state::text = 'admitted'::text AND worker_id IS NULL "
            "AND worker_generation IS NULL AND lease_generation IS NULL "
            "AND lease_expires_at IS NULL OR (state::text = ANY "
            "(ARRAY['leased'::character varying, 'running'::character varying, "
            "'waiting_model'::character varying, "
            "'waiting_tool'::character varying, "
            "'cancelling'::character varying]::text[])) AND worker_id IS NOT NULL "
            "AND worker_generation IS NOT NULL AND lease_generation IS NOT NULL "
            "AND lease_expires_at IS NOT NULL OR (state::text = ANY "
            "(ARRAY['completed'::character varying, 'failed'::character varying, "
            "'interrupted'::character varying]::text[])) AND worker_id IS NOT NULL "
            "AND worker_generation IS NOT NULL AND lease_generation IS NOT NULL "
            "AND lease_expires_at IS NULL)"
        ),
    },
    "chat_turn_jobs_terminal_timestamp_check": {
        "kind": "c",
        "validated": True,
        "definition": (
            "CHECK ((state::text = ANY (ARRAY['completed'::character varying, "
            "'failed'::character varying, "
            "'interrupted'::character varying]::text[])) = "
            "(terminal_at IS NOT NULL))"
        ),
    },
    "chat_turn_jobs_failure_code_check": {
        "kind": "c",
        "validated": True,
        "definition": (
            "CHECK (failure_code IS NULL OR failure_code::text ~ "
            "'^[a-z0-9][a-z0-9_]{0,63}$'::text)"
        ),
    },
}


class QualificationRefused(RuntimeError):
    """The operator context is unsafe for durable-dispatch qualification."""


class QualificationRunFailed(RuntimeError):
    """A sanitized failed workload outcome with its aggregate cleanup result."""

    def __init__(
        self,
        *,
        code: str,
        passed: int,
        timing_ms: dict[str, int | float | None],
        cleanup: dict[str, bool | int],
        schema_audit: SchemaAudit,
    ):
        super().__init__(code)
        self.code = code
        self.passed = passed
        self.timing_ms = timing_ms
        self.cleanup = cleanup
        self.schema_audit = schema_audit


@dataclass(frozen=True, slots=True)
class SchemaAudit:
    schema: bool
    role: bool
    owner: bool
    privileges: bool
    indexes: bool
    constraints: bool


def _definition_matches(
    actual: object, expected: Mapping[str, object], *, definition_field: str
) -> bool:
    if not isinstance(actual, Mapping) or set(actual) != set(expected):
        return False
    for field, expected_value in expected.items():
        actual_value = actual[field]
        if field == definition_field and isinstance(expected_value, str):
            if not isinstance(actual_value, str):
                return False
            if " ".join(actual_value.split()) != " ".join(expected_value.split()):
                return False
        elif actual_value != expected_value:
            return False
    return True


def audit_postgresql_definitions(
    *, indexes: object, constraints: object
) -> tuple[bool, bool]:
    """Compare material catalog definitions, tolerating whitespace only."""

    indexes_match = isinstance(indexes, Mapping) and set(indexes) == set(
        EXPECTED_INDEX_DEFINITIONS
    )
    if indexes_match:
        indexes_match = all(
            _definition_matches(indexes[name], expected, definition_field="predicate")
            for name, expected in EXPECTED_INDEX_DEFINITIONS.items()
        )
    constraints_match = isinstance(constraints, Mapping) and set(constraints) == set(
        EXPECTED_CONSTRAINT_DEFINITIONS
    )
    if constraints_match:
        constraints_match = all(
            _definition_matches(
                constraints[name], expected, definition_field="definition"
            )
            for name, expected in EXPECTED_CONSTRAINT_DEFINITIONS.items()
        )
    return indexes_match, constraints_match


def validate_schema_audit(audit: SchemaAudit) -> None:
    for name, valid in asdict(audit).items():
        if not valid:
            raise QualificationRefused(f"PostgreSQL {name} contract mismatch")


def _summarize_timings(values: list[float]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "min": None, "p50": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "p50": statistics.median(values),
        "max": max(values),
    }


def inspect_postgresql_contract(db: Session) -> SchemaAudit:
    """Audit the staging table through content-free PostgreSQL aggregates."""

    if db.bind is None or db.bind.dialect.name != "postgresql":
        raise QualificationRefused("qualification requires PostgreSQL")
    db.execute(text("SET TRANSACTION READ ONLY"))
    row = (
        db.execute(
            text(
                """
            WITH expected_columns(name, data_type, nullable, max_length) AS (
                VALUES
                    ('turn_id','uuid',false,NULL),
                    ('chat_session_id','uuid',false,NULL),
                    ('hf_user_id','character varying',false,255),
                    ('request_id','character varying',false,200),
                    ('revision','integer',false,NULL),
                    ('dispatch_class','character varying',false,32),
                    ('dispatch_route','character varying',false,255),
                    ('state','character varying',false,24),
                    ('worker_id','character varying',true,128),
                    ('worker_generation','bigint',true,NULL),
                    ('lease_generation','bigint',true,NULL),
                    ('app_release_id','character varying',false,255),
                    ('worker_contract_version','character varying',false,128),
                    ('admitted_at','timestamp with time zone',false,NULL),
                    ('dispatched_at','timestamp with time zone',true,NULL),
                    ('started_at','timestamp with time zone',true,NULL),
                    ('heartbeat_at','timestamp with time zone',true,NULL),
                    ('lease_expires_at','timestamp with time zone',true,NULL),
                    ('terminal_at','timestamp with time zone',true,NULL),
                    ('failure_code','character varying',true,64),
                    ('last_agent_session_id','uuid',true,NULL),
                    ('last_resume_boundary_id','text',true,NULL)
            ), actual_columns AS (
                SELECT column_name AS name, data_type, is_nullable = 'YES' AS nullable,
                       character_maximum_length AS max_length
                FROM information_schema.columns
                WHERE table_schema = 'staging' AND table_name = 'chat_turn_jobs'
            ), column_drift AS (
                SELECT 1 FROM expected_columns e FULL JOIN actual_columns a USING (name)
                WHERE e.name IS NULL OR a.name IS NULL
                   OR e.data_type <> a.data_type OR e.nullable <> a.nullable
                   OR e.max_length IS DISTINCT FROM a.max_length
            ), table_info AS (
                SELECT oid, relowner, relacl FROM pg_class
                WHERE oid = to_regclass('staging.chat_turn_jobs')
            ), index_contracts AS (
                SELECT c.relname AS name,
                       ARRAY(
                           SELECT pg_get_indexdef(i.indexrelid, position, true)
                           FROM generate_series(1, i.indnkeyatts) position
                           ORDER BY position
                       ) AS columns,
                       ARRAY(
                           SELECT pg_get_indexdef(i.indexrelid, position, true)
                           FROM generate_series(
                               i.indnkeyatts + 1, i.indnatts
                           ) position
                           ORDER BY position
                       ) AS included_columns,
                       pg_get_expr(i.indpred, i.indrelid, true) AS predicate,
                       i.indisunique AS is_unique,
                       i.indisvalid AS valid,
                       i.indisready AS ready
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE i.indrelid = to_regclass('staging.chat_turn_jobs')
                  AND c.relname IN (
                      'idx_chat_turn_jobs_claim',
                      'idx_chat_turn_jobs_expiry',
                      'uq_chat_turn_jobs_nonterminal_owner'
                  )
            ), constraint_contracts AS (
                SELECT conname AS name,
                       contype::text AS kind,
                       convalidated AS validated,
                       pg_get_constraintdef(pc.oid, true) AS definition,
                       rn.nspname AS reference_schema
                FROM pg_constraint pc
                LEFT JOIN pg_class rc ON rc.oid = pc.confrelid
                LEFT JOIN pg_namespace rn ON rn.oid = rc.relnamespace
                WHERE pc.conrelid = to_regclass('staging.chat_turn_jobs')
                  AND pc.conname IN (
                      'chat_turn_jobs_pkey',
                      'chat_turn_jobs_request_id_key',
                      'chat_turn_jobs_chat_session_id_fkey',
                      'chat_turn_jobs_revision_check',
                      'chat_turn_jobs_worker_generation_check',
                      'chat_turn_jobs_lease_generation_check',
                      'chat_turn_jobs_state_check',
                      'chat_turn_jobs_lease_fields_check',
                      'chat_turn_jobs_terminal_timestamp_check',
                      'chat_turn_jobs_failure_code_check'
                  )
            )
            SELECT
                current_schema() = 'staging'
                    AND to_regclass('staging.chat_turn_jobs') IS NOT NULL
                    AND NOT EXISTS (SELECT FROM column_drift) AS schema,
                current_user = 'pwc_staging' AS role,
                (SELECT pg_get_userbyid(relowner) = 'pwc_staging_owner'
                 FROM table_info) AS owner,
                has_table_privilege(current_user, to_regclass('staging.chat_turn_jobs'),
                                    'SELECT,INSERT,UPDATE,DELETE')
                    AND NOT has_table_privilege(to_regrole('paperswithcode_user'),
                                                to_regclass('staging.chat_turn_jobs'),
                                                'SELECT,INSERT,UPDATE,DELETE')
                    AND NOT EXISTS (
                        SELECT FROM table_info t,
                             LATERAL aclexplode(
                                 coalesce(t.relacl, acldefault('r', t.relowner))
                             ) a
                        WHERE a.grantee = 0 AND a.privilege_type IN
                            ('SELECT','INSERT','UPDATE','DELETE')
                    ) AS privileges,
                coalesce(
                    (SELECT jsonb_object_agg(
                        name,
                        jsonb_build_object(
                            'columns', columns,
                            'included_columns', included_columns,
                            'predicate', predicate,
                            'unique', is_unique,
                            'valid', valid,
                            'ready', ready
                        )
                    ) FROM index_contracts),
                    '{}'::jsonb
                ) AS index_definitions,
                coalesce(
                    (SELECT jsonb_object_agg(
                        name,
                        jsonb_strip_nulls(jsonb_build_object(
                            'kind', kind,
                            'validated', validated,
                            'definition', definition,
                            'reference_schema', reference_schema
                        ))
                    ) FROM constraint_contracts),
                    '{}'::jsonb
                ) AS constraint_definitions
            """
            )
        )
        .mappings()
        .one()
    )
    indexes, constraints = audit_postgresql_definitions(
        indexes=row["index_definitions"],
        constraints=row["constraint_definitions"],
    )
    return SchemaAudit(
        schema=bool(row["schema"]),
        role=bool(row["role"]),
        owner=bool(row["owner"]),
        privileges=bool(row["privileges"]),
        indexes=indexes,
        constraints=constraints,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Qualify staging durable dispatch through its repository contract"
    )
    result.add_argument("--release-dir", type=Path, required=True)
    result.add_argument("--confirm", required=True)
    modes = result.add_mutually_exclusive_group()
    modes.add_argument(
        "--audit-disabled-only",
        action="store_true",
        help="audit the active staging schema only while durable dispatch is disabled",
    )
    modes.add_argument(
        "--qualify-enabled-only",
        action="store_true",
        help="run the normal qualification only while durable dispatch is enabled",
    )
    return result


def resolve_active_staging_release(requested_release: Path) -> Path:
    """Require the exact active immutable staging release directory."""

    release_root = RELEASE_ROOT.resolve(strict=True)
    active_release = ACTIVE_STAGING_RELEASE.resolve(strict=True)
    requested_release = requested_release.resolve(strict=True)
    if (
        requested_release != active_release
        or requested_release.parent != release_root
        or _STAGING_RELEASE_NAME.fullmatch(requested_release.name) is None
    ):
        raise QualificationRefused(
            "audit requires the exact active immutable staging release"
        )
    return requested_release


def _validate_shared_operator_context(
    *,
    confirmation: str,
    environment: Settings,
    release_id: str,
    worker_contract_version: str,
) -> None:
    if confirmation != CONFIRMATION:
        raise QualificationRefused("qualification confirmation is invalid")
    if environment.environment != "staging":
        raise QualificationRefused("qualification requires staging")
    if environment.release_id != release_id:
        raise QualificationRefused("live and immutable release identities differ")
    if environment.chat_worker_contract_version != worker_contract_version:
        raise QualificationRefused("live and immutable worker contracts differ")
    if environment.db_search_path.split(",", 1)[0].strip() != "staging":
        raise QualificationRefused("qualification requires the staging search path")


def validate_operator_context(
    *,
    confirmation: str,
    environment: Settings,
    release_id: str,
    worker_contract_version: str,
) -> None:
    _validate_shared_operator_context(
        confirmation=confirmation,
        environment=environment,
        release_id=release_id,
        worker_contract_version=worker_contract_version,
    )
    if not environment.chat_durable_turn_dispatch_enabled:
        raise QualificationRefused("durable dispatch bridge is disabled")


def validate_disabled_audit_context(
    *,
    confirmation: str,
    environment: Settings,
    release_id: str,
    worker_contract_version: str,
) -> None:
    _validate_shared_operator_context(
        confirmation=confirmation,
        environment=environment,
        release_id=release_id,
        worker_contract_version=worker_contract_version,
    )
    if environment.chat_durable_turn_dispatch_enabled:
        raise QualificationRefused("disabled-state audit requires a disabled bridge")


def run_qualification(
    *,
    session_factory: Callable[[], Session],
    release_id: str,
    worker_contract_version: str,
    schema_audit: SchemaAudit,
) -> dict[str, Any]:
    """Exercise the content-free repository contract and always remove its rows."""

    validate_schema_audit(schema_audit)
    run_token = uuid.uuid4().hex
    session_ids = [uuid.uuid4() for _ in range(4)]
    owners = [f"qualify-{run_token}-{index}" for index in (0, 0, 1, 2)]
    turn_ids: list[uuid.UUID] = []
    timings: list[float] = []
    outcomes: dict[str, str] = {}
    cleanup = {"clean": False, "jobs_deleted": 0, "sessions_deleted": 0}

    def scenario(name: str, operation: Callable[[], str]) -> None:
        started = time.monotonic()
        outcome = operation()
        expected = EXPECTED_OUTCOMES[name]
        if outcome != expected:
            raise RuntimeError(
                f"durable qualification invariant failed for {name}: {outcome}"
            )
        outcomes[name] = outcome
        timings.append((time.monotonic() - started) * 1000)

    with session_factory() as db:
        repository = ChatTurnJobRepository(
            advisory_locker=(
                (lambda *_args: None) if db.bind.dialect.name == "sqlite" else None
            )
        )
        sessions = [
            ChatSession(
                id=session_id,
                hf_user_id=owner,
                hf_username=owner,
                selected_model="qualification",
            )
            for session_id, owner in zip(session_ids, owners, strict=True)
        ]

        def admit(index: int, *, capacity: int = 2, request: str | None = None):
            turn_id = uuid.uuid4()
            request_id = request or f"qualify-{run_token}-{uuid.uuid4().hex}"
            result = repository.admit(
                db,
                turn_id=turn_id,
                chat_session_id=sessions[index].id,
                hf_user_id=sessions[index].hf_user_id,
                request_id=request_id,
                revision=1,
                dispatch_class="qualification",
                dispatch_route="durable-repository",
                app_release_id=release_id,
                worker_contract_version=worker_contract_version,
                now=datetime.now(UTC),
                emergency_capacity=capacity,
            )
            if result.created:
                turn_ids.append(turn_id)
            return result

        failure_code: str | None = None
        try:
            db.add_all(sessions)
            db.commit()
            first_request = f"qualify-{run_token}-replay"
            first = admit(0, request=first_request)
            db.commit()

            def replay() -> str:
                result = repository.admit(
                    db,
                    turn_id=first.job.turn_id,
                    chat_session_id=sessions[0].id,
                    hf_user_id=sessions[0].hf_user_id,
                    request_id=first_request,
                    revision=1,
                    dispatch_class="qualification",
                    dispatch_route="durable-repository",
                    app_release_id=release_id,
                    worker_contract_version=worker_contract_version,
                    now=datetime.now(UTC),
                    emergency_capacity=2,
                )
                return "replayed" if not result.created else "created"

            scenario("idempotent_admission", replay)

            def owner_contention() -> str:
                try:
                    admit(1)
                except AccountBusy as error:
                    return error.code
                return "admitted"

            scenario("same_owner_contention", owner_contention)
            second = admit(2)
            db.commit()

            def capacity_rejection() -> str:
                try:
                    admit(3)
                except ChatOverload as error:
                    return error.code
                return "admitted"

            scenario("global_capacity", capacity_rejection)
            now = datetime.now(UTC)
            claim = repository.claim(
                db,
                turn_id=first.job.turn_id,
                worker_id=f"qualification-{run_token}",
                worker_generation=1,
                now=now,
                lease_seconds=30,
            )

            def claimed_lifecycle() -> str:
                repository.heartbeat(
                    db, claim=claim, now=now + timedelta(seconds=1), lease_seconds=30
                )
                repository.transition(
                    db, claim=claim, state="running", now=now + timedelta(seconds=2)
                )
                job = repository.transition(
                    db,
                    claim=claim,
                    state="waiting_model",
                    now=now + timedelta(seconds=3),
                )
                return job.state

            scenario("claim_heartbeat_transition", claimed_lifecycle)

            def stale_fence() -> str:
                stale = TurnLeaseClaim(
                    turn_id=claim.turn_id,
                    worker_id=claim.worker_id,
                    worker_generation=claim.worker_generation,
                    lease_generation=claim.lease_generation + 1,
                )
                try:
                    repository.heartbeat(
                        db,
                        claim=stale,
                        now=now + timedelta(seconds=4),
                        lease_seconds=30,
                    )
                except StaleTurnClaim:
                    return "stale_turn_claim"
                return "accepted"

            scenario("stale_fence", stale_fence)

            def terminal_write() -> str:
                terminal = repository.write_terminal(
                    db,
                    claim=claim,
                    state="completed",
                    now=now + timedelta(seconds=5),
                )
                replayed = repository.write_terminal(
                    db,
                    claim=claim,
                    state="completed",
                    now=now + timedelta(seconds=6),
                )
                if replayed.turn_id != terminal.turn_id:
                    return "failed"
                return replayed.state

            scenario("terminal_write", terminal_write)
            expiry_claim = repository.claim(
                db,
                turn_id=second.job.turn_id,
                worker_id=f"qualification-expiry-{run_token}",
                worker_generation=1,
                now=now,
                lease_seconds=1,
            )

            def expiry() -> str:
                job = repository.interrupt_exact_expired(
                    db,
                    turn_id=expiry_claim.turn_id,
                    now=now + timedelta(seconds=2),
                )
                return job.failure_code

            scenario("expiry_interruption", expiry)
            db.commit()
        except Exception as error:
            failure_code = (
                "database_failure"
                if isinstance(error, SQLAlchemyError)
                else "runtime_failure"
            )
        finally:
            try:
                db.rollback()
                deleted_jobs = db.execute(
                    delete(ChatTurnJob).where(ChatTurnJob.turn_id.in_(turn_ids))
                ).rowcount
                deleted_sessions = db.execute(
                    delete(ChatSession).where(ChatSession.id.in_(session_ids))
                ).rowcount
                db.commit()
                remaining_jobs = db.scalar(
                    select(ChatTurnJob.turn_id)
                    .where(ChatTurnJob.turn_id.in_(turn_ids))
                    .limit(1)
                )
                remaining_sessions = db.scalar(
                    select(ChatSession.id)
                    .where(ChatSession.id.in_(session_ids))
                    .limit(1)
                )
                cleanup = {
                    "clean": remaining_jobs is None and remaining_sessions is None,
                    "jobs_deleted": deleted_jobs,
                    "sessions_deleted": deleted_sessions,
                }
            except Exception:
                failure_code = "cleanup_failure"
                try:
                    db.rollback()
                except Exception:
                    pass

    if failure_code is not None:
        raise QualificationRunFailed(
            code=failure_code,
            passed=len(outcomes),
            timing_ms=_summarize_timings(timings),
            cleanup=cleanup,
            schema_audit=schema_audit,
        ) from None

    return {
        "release": {
            "release_id": release_id,
            "worker_contract_version": worker_contract_version,
        },
        "scenarios": {"requested": 7, "passed": len(outcomes), "failed": 0},
        "outcomes": outcomes,
        "timing_ms": _summarize_timings(timings),
        "cleanup": cleanup,
        "schema_audit": asdict(schema_audit),
    }


def _failure_report(
    *,
    release_id: str,
    worker_contract_version: str,
    code: str,
    passed: int,
    timing_ms: dict[str, int | float | None],
    cleanup: dict[str, bool | int],
    schema_audit: SchemaAudit,
) -> dict[str, Any]:
    return {
        "release": {
            "release_id": release_id,
            "worker_contract_version": worker_contract_version,
        },
        "scenarios": {
            "requested": len(EXPECTED_OUTCOMES),
            "passed": passed,
            "failed": 1,
        },
        "outcomes": {"qualification": code},
        "timing_ms": timing_ms,
        "cleanup": cleanup,
        "schema_audit": asdict(schema_audit),
    }


def _disabled_audit_report(
    *,
    release_id: str,
    worker_contract_version: str,
    schema_audit: SchemaAudit,
    passed: bool,
) -> dict[str, Any]:
    return {
        "mode": "disabled_schema_audit",
        "release": {
            "release_id": release_id,
            "worker_contract_version": worker_contract_version,
        },
        "schema_audit": asdict(schema_audit),
        "status": {"passed": passed},
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    disabled_audit = args.audit_disabled_only
    release_id = "unavailable"
    worker_contract_version = "unavailable"
    empty_audit = SchemaAudit(*(False for _ in range(6)))
    empty_cleanup: dict[str, bool | int] = {
        "clean": True,
        "jobs_deleted": 0,
        "sessions_deleted": 0,
    }
    empty_timing = _summarize_timings([])
    audit = empty_audit

    def failure_report(code: str, schema_audit: SchemaAudit) -> dict[str, Any]:
        if disabled_audit:
            return _disabled_audit_report(
                release_id=release_id,
                worker_contract_version=worker_contract_version,
                schema_audit=schema_audit,
                passed=False,
            )
        return _failure_report(
            release_id=release_id,
            worker_contract_version=worker_contract_version,
            code=code,
            passed=0,
            timing_ms=empty_timing,
            cleanup=empty_cleanup,
            schema_audit=schema_audit,
        )

    try:
        release_dir = (
            resolve_active_staging_release(args.release_dir)
            if disabled_audit
            else args.release_dir.resolve(strict=True)
        )
        manifest = validate_manifest(release_dir, "staging")
        release_id = manifest["release_id"]
        runtime = manifest.get("chat_runtime")
        if not isinstance(runtime, dict):
            raise QualificationRefused("release has no durable chat contract")
        contract = runtime.get("worker_contract_version")
        if not isinstance(contract, str) or not contract:
            raise QualificationRefused("release worker contract is missing")
        worker_contract_version = contract
        environment = get_settings()
        context_validator = (
            validate_disabled_audit_context
            if disabled_audit
            else validate_operator_context
        )
        context_validator(
            confirmation=args.confirm,
            environment=environment,
            release_id=release_id,
            worker_contract_version=worker_contract_version,
        )
        with db_manager.session_local() as db:
            audit = inspect_postgresql_contract(db)
        if disabled_audit:
            validate_schema_audit(audit)
            report = _disabled_audit_report(
                release_id=release_id,
                worker_contract_version=worker_contract_version,
                schema_audit=audit,
                passed=True,
            )
        else:
            report = run_qualification(
                session_factory=db_manager.session_local,
                release_id=release_id,
                worker_contract_version=worker_contract_version,
                schema_audit=audit,
            )
            if not report["cleanup"]["clean"]:
                raise QualificationRunFailed(
                    code="cleanup_failure",
                    passed=len(EXPECTED_OUTCOMES),
                    timing_ms=report["timing_ms"],
                    cleanup=report["cleanup"],
                    schema_audit=audit,
                )
    except QualificationRunFailed as error:
        report = _failure_report(
            release_id=release_id,
            worker_contract_version=worker_contract_version,
            code=error.code,
            passed=error.passed,
            timing_ms=error.timing_ms,
            cleanup=error.cleanup,
            schema_audit=error.schema_audit,
        )
    except (QualificationRefused, FileNotFoundError, ValueError):
        report = failure_report("qualification_refused", audit)
    except SQLAlchemyError:
        report = failure_report("database_failure", empty_audit)
    except Exception:
        report = failure_report("runtime_failure", empty_audit)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    if disabled_audit:
        return 0 if report["status"]["passed"] else 1
    return 0 if report["scenarios"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
