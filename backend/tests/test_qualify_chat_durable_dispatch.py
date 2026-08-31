import json
import re
import uuid
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import backend.scripts.qualify_chat_durable_dispatch as durable_script
from backend.config import Settings
from backend.models.database import ChatSession, ChatTurnJob
from backend.scripts.qualify_chat_durable_dispatch import (
    CONFIRMATION,
    QualificationRefused,
    QualificationRunFailed,
    SchemaAudit,
    audit_postgresql_definitions,
    inspect_postgresql_contract,
    parser,
    run_qualification,
    validate_schema_audit,
    validate_operator_context,
)
from backend.services.chat_turn_job_repository import ChatTurnJobRepository


def _settings(**updates) -> Settings:
    return Settings(
        environment="staging",
        release_id="abc123-staging",
        db_search_path="staging,public",
        chat_durable_turn_dispatch_enabled=True,
        chat_worker_contract_version="worker-v1",
    ).model_copy(update=updates)


@pytest.mark.parametrize(
    ("confirmation", "settings", "release_id", "worker_contract", "message"),
    [
        ("wrong", _settings(), "abc123-staging", "worker-v1", "confirmation"),
        (
            CONFIRMATION,
            _settings(environment="production"),
            "abc123-staging",
            "worker-v1",
            "staging",
        ),
        (CONFIRMATION, _settings(), "other-staging", "worker-v1", "release"),
        (CONFIRMATION, _settings(), "abc123-staging", "worker-v2", "contract"),
        (
            CONFIRMATION,
            _settings(chat_durable_turn_dispatch_enabled=False),
            "abc123-staging",
            "worker-v1",
            "disabled",
        ),
        (
            CONFIRMATION,
            _settings(db_search_path="public"),
            "abc123-staging",
            "worker-v1",
            "search path",
        ),
    ],
)
def test_operator_context_refuses_unsafe_execution(
    confirmation, settings, release_id, worker_contract, message
):
    with pytest.raises(QualificationRefused, match=message):
        validate_operator_context(
            confirmation=confirmation,
            environment=settings,
            release_id=release_id,
            worker_contract_version=worker_contract,
        )


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ChatSession.__table__.create(engine)
    ChatTurnJob.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _valid_audit(**updates) -> SchemaAudit:
    values = {
        "schema": True,
        "role": True,
        "owner": True,
        "privileges": True,
        "indexes": True,
        "constraints": True,
    }
    values.update(updates)
    return SchemaAudit(**values)


def _valid_definition_snapshot():
    indexes = {
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
    constraints = {
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
            "definition": (
                "CHECK (worker_generation IS NULL OR worker_generation > 0)"
            ),
        },
        "chat_turn_jobs_lease_generation_check": {
            "kind": "c",
            "validated": True,
            "definition": ("CHECK (lease_generation IS NULL OR lease_generation > 0)"),
        },
        "chat_turn_jobs_state_check": {
            "kind": "c",
            "validated": True,
            "definition": (
                "CHECK (state::text = ANY (ARRAY['admitted'::character varying, "
                "'leased'::character varying, 'running'::character varying, "
                "'waiting_model'::character varying, "
                "'waiting_tool'::character varying, "
                "'cancelling'::character varying, "
                "'completed'::character varying, 'failed'::character varying, "
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
    return indexes, constraints


@pytest.mark.parametrize(
    "field", ["schema", "role", "owner", "privileges", "indexes", "constraints"]
)
def test_schema_audit_refuses_each_postgresql_contract_mismatch(field):
    with pytest.raises(QualificationRefused, match=field):
        validate_schema_audit(_valid_audit(**{field: False}))


@pytest.mark.parametrize(
    ("index_name", "field", "replacement"),
    [
        ("idx_chat_turn_jobs_claim", "columns", ["state", "turn_id"]),
        ("idx_chat_turn_jobs_expiry", "columns", ["lease_expires_at", "state"]),
        ("uq_chat_turn_jobs_nonterminal_owner", "predicate", "state = 'running'"),
        ("uq_chat_turn_jobs_nonterminal_owner", "unique", False),
        ("idx_chat_turn_jobs_claim", "included_columns", ["worker_id"]),
        ("idx_chat_turn_jobs_claim", "valid", False),
        ("idx_chat_turn_jobs_expiry", "ready", False),
    ],
)
def test_index_audit_rejects_each_material_definition_mismatch(
    index_name, field, replacement
):
    indexes, constraints = _valid_definition_snapshot()
    indexes[index_name][field] = replacement

    indexes_match, constraints_match = audit_postgresql_definitions(
        indexes=indexes, constraints=constraints
    )

    assert indexes_match is False
    assert constraints_match is True
    with pytest.raises(QualificationRefused, match="indexes"):
        validate_schema_audit(_valid_audit(indexes=indexes_match))


@pytest.mark.parametrize(
    "constraint_name",
    [
        "chat_turn_jobs_pkey",
        "chat_turn_jobs_request_id_key",
        "chat_turn_jobs_chat_session_id_fkey",
        "chat_turn_jobs_revision_check",
        "chat_turn_jobs_worker_generation_check",
        "chat_turn_jobs_lease_generation_check",
        "chat_turn_jobs_state_check",
        "chat_turn_jobs_lease_fields_check",
        "chat_turn_jobs_terminal_timestamp_check",
        "chat_turn_jobs_failure_code_check",
    ],
)
def test_constraint_audit_rejects_every_changed_material_definition(constraint_name):
    indexes, constraints = _valid_definition_snapshot()
    constraints[constraint_name]["definition"] = "CHECK (false)"

    indexes_match, constraints_match = audit_postgresql_definitions(
        indexes=indexes, constraints=constraints
    )

    assert indexes_match is True
    assert constraints_match is False
    with pytest.raises(QualificationRefused, match="constraints"):
        validate_schema_audit(_valid_audit(constraints=constraints_match))


@pytest.mark.parametrize("field", ["kind", "validated"])
def test_constraint_audit_rejects_wrong_kind_or_unvalidated_constraint(field):
    indexes, constraints = _valid_definition_snapshot()
    constraints["chat_turn_jobs_revision_check"][field] = (
        "u" if field == "kind" else False
    )

    indexes_match, constraints_match = audit_postgresql_definitions(
        indexes=indexes, constraints=constraints
    )

    assert indexes_match is True
    assert constraints_match is False
    with pytest.raises(QualificationRefused, match="constraints"):
        validate_schema_audit(_valid_audit(constraints=constraints_match))


def test_constraint_audit_rejects_wrong_foreign_key_schema():
    indexes, constraints = _valid_definition_snapshot()
    constraints["chat_turn_jobs_chat_session_id_fkey"]["reference_schema"] = "public"

    indexes_match, constraints_match = audit_postgresql_definitions(
        indexes=indexes, constraints=constraints
    )

    assert indexes_match is True
    assert constraints_match is False
    with pytest.raises(QualificationRefused, match="constraints"):
        validate_schema_audit(_valid_audit(constraints=constraints_match))


def test_definition_audit_ignores_only_harmless_whitespace():
    indexes, constraints = deepcopy(_valid_definition_snapshot())
    constraints["chat_turn_jobs_revision_check"]["definition"] = (
        "  CHECK   (revision > 0)  "
    )

    assert audit_postgresql_definitions(indexes=indexes, constraints=constraints) == (
        True,
        True,
    )


def test_qualification_exercises_lifecycle_cleans_rows_and_sanitizes_report():
    factory = _session_factory()

    report = run_qualification(
        session_factory=factory,
        release_id="abc123-staging",
        worker_contract_version="worker-v1",
        schema_audit=_valid_audit(),
    )

    assert set(report) == {
        "release",
        "scenarios",
        "outcomes",
        "timing_ms",
        "cleanup",
        "schema_audit",
    }
    assert report["release"] == {
        "release_id": "abc123-staging",
        "worker_contract_version": "worker-v1",
    }
    assert report["scenarios"] == {"requested": 7, "passed": 7, "failed": 0}
    assert report["outcomes"] == {
        "idempotent_admission": "replayed",
        "same_owner_contention": "account_busy",
        "global_capacity": "chat_overload",
        "claim_heartbeat_transition": "waiting_model",
        "stale_fence": "stale_turn_claim",
        "terminal_write": "completed",
        "expiry_interruption": "lease_expired",
    }
    assert report["timing_ms"]["count"] == 7
    assert 0 <= report["timing_ms"]["min"] <= report["timing_ms"]["p50"]
    assert report["timing_ms"]["p50"] <= report["timing_ms"]["max"]
    assert report["cleanup"] == {
        "clean": True,
        "jobs_deleted": 2,
        "sessions_deleted": 4,
    }
    assert report["schema_audit"] == {
        "schema": True,
        "role": True,
        "owner": True,
        "privileges": True,
        "indexes": True,
        "constraints": True,
    }
    serialized = json.dumps(report)
    assert "qualify-" not in serialized
    with factory() as db:
        assert db.query(ChatTurnJob).count() == 0
        assert db.query(ChatSession).count() == 0


def test_qualification_cleans_rows_when_a_repository_scenario_fails(monkeypatch):
    factory = _session_factory()

    def fail_heartbeat(*_args, **_kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(
        "backend.scripts.qualify_chat_durable_dispatch.ChatTurnJobRepository.heartbeat",
        fail_heartbeat,
    )

    with pytest.raises(QualificationRunFailed, match="runtime_failure") as failure:
        run_qualification(
            session_factory=factory,
            release_id="abc123-staging",
            worker_contract_version="worker-v1",
            schema_audit=_valid_audit(),
        )

    assert failure.value.cleanup == {
        "clean": True,
        "jobs_deleted": 2,
        "sessions_deleted": 4,
    }

    with factory() as db:
        assert db.query(ChatTurnJob).count() == 0
        assert db.query(ChatSession).count() == 0


def test_expiry_scenario_leaves_an_unrelated_earlier_expired_job_untouched():
    factory = _session_factory()
    unrelated_session_id = uuid.uuid4()
    unrelated_turn_id = uuid.uuid4()
    old = datetime(2025, 1, 1, tzinfo=UTC)
    with factory() as db:
        db.add(
            ChatSession(
                id=unrelated_session_id,
                hf_user_id="unrelated-owner",
                hf_username="unrelated-owner",
                selected_model="model",
            )
        )
        repository = ChatTurnJobRepository(advisory_locker=lambda *_args: None)
        repository.admit(
            db,
            turn_id=unrelated_turn_id,
            chat_session_id=unrelated_session_id,
            hf_user_id="unrelated-owner",
            request_id="unrelated-request",
            revision=1,
            dispatch_class="interactive",
            dispatch_route="external-pi",
            app_release_id="older-release",
            worker_contract_version="worker-v1",
            now=old,
            emergency_capacity=2,
        )
        repository.claim(
            db,
            turn_id=unrelated_turn_id,
            worker_id="unrelated-worker",
            worker_generation=1,
            now=old,
            lease_seconds=1,
        )
        db.commit()

    run_qualification(
        session_factory=factory,
        release_id="abc123-staging",
        worker_contract_version="worker-v1",
        schema_audit=_valid_audit(),
    )

    with factory() as db:
        unrelated = db.get(ChatTurnJob, unrelated_turn_id)
        assert unrelated is not None
        assert unrelated.state == "leased"
        assert unrelated.failure_code is None


def test_cli_requires_release_directory_and_exact_confirmation(tmp_path):
    release = tmp_path / "release"
    arguments = parser().parse_args(
        [
            "--release-dir",
            str(release),
            "--confirm",
            CONFIRMATION,
        ]
    )

    assert arguments.release_dir == release
    assert arguments.confirm == CONFIRMATION


def test_cli_modes_are_mutually_exclusive(tmp_path, capsys):
    with pytest.raises(SystemExit):
        parser().parse_args(
            [
                "--release-dir",
                str(tmp_path),
                "--confirm",
                CONFIRMATION,
                "--audit-disabled-only",
                "--qualify-enabled-only",
            ]
        )
    assert "not allowed with argument" in capsys.readouterr().err


def _install_active_staging_release(tmp_path, monkeypatch):
    release_root = tmp_path / "releases"
    release_root.mkdir()
    release = release_root / f"{'a' * 12}-staging"
    release.mkdir()
    environments = tmp_path / "environments" / "staging"
    environments.mkdir(parents=True)
    active = environments / "current"
    active.symlink_to(release)
    monkeypatch.setattr(durable_script, "RELEASE_ROOT", release_root, raising=False)
    monkeypatch.setattr(durable_script, "ACTIVE_STAGING_RELEASE", active, raising=False)
    return release


def test_disabled_schema_audit_cli_is_read_only_and_content_free(
    tmp_path, monkeypatch, capsys
):
    release = _install_active_staging_release(tmp_path, monkeypatch)
    release_id = f"{'a' * 12}-staging"
    manifest = {
        "release_id": release_id,
        "chat_runtime": {"worker_contract_version": "worker-v1"},
    }
    factory = _session_factory()
    with factory() as db:
        db.add(
            ChatSession(
                id=uuid.uuid4(),
                hf_user_id="unrelated-owner",
                hf_username="unrelated-owner",
                selected_model="qualification",
            )
        )
        db.commit()
        before = db.query(ChatSession).count()

    monkeypatch.setattr(durable_script, "validate_manifest", lambda *_args: manifest)
    monkeypatch.setattr(
        durable_script,
        "get_settings",
        lambda: _settings(
            release_id=release_id,
            chat_durable_turn_dispatch_enabled=False,
        ),
    )
    monkeypatch.setattr(durable_script.db_manager, "_session_local", factory)
    monkeypatch.setattr(
        durable_script, "inspect_postgresql_contract", lambda _db: _valid_audit()
    )
    monkeypatch.setattr(
        durable_script,
        "run_qualification",
        lambda **_kwargs: pytest.fail("read-only audit started qualification workload"),
    )

    exit_code = durable_script.main(
        [
            "--release-dir",
            str(release),
            "--confirm",
            CONFIRMATION,
            "--audit-disabled-only",
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert report == {
        "mode": "disabled_schema_audit",
        "release": {
            "release_id": release_id,
            "worker_contract_version": "worker-v1",
        },
        "schema_audit": {
            "schema": True,
            "role": True,
            "owner": True,
            "privileges": True,
            "indexes": True,
            "constraints": True,
        },
        "status": {"passed": True},
    }
    assert re.search(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", captured.out) is None
    with factory() as db:
        assert db.query(ChatSession).count() == before
        assert db.query(ChatTurnJob).count() == 0


def test_disabled_schema_audit_cli_refuses_enabled_bridge_before_database(
    tmp_path, monkeypatch, capsys
):
    release = _install_active_staging_release(tmp_path, monkeypatch)
    release_id = f"{'a' * 12}-staging"
    manifest = {
        "release_id": release_id,
        "chat_runtime": {"worker_contract_version": "worker-v1"},
    }
    monkeypatch.setattr(durable_script, "validate_manifest", lambda *_args: manifest)
    monkeypatch.setattr(
        durable_script, "get_settings", lambda: _settings(release_id=release_id)
    )
    monkeypatch.setattr(
        durable_script,
        "inspect_postgresql_contract",
        lambda _db: pytest.fail("enabled bridge reached disabled-state audit"),
    )

    exit_code = durable_script.main(
        [
            "--release-dir",
            str(release),
            "--confirm",
            CONFIRMATION,
            "--audit-disabled-only",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report["mode"] == "disabled_schema_audit"
    assert report["status"] == {"passed": False}
    assert all(value is False for value in report["schema_audit"].values())


@pytest.mark.parametrize(
    ("confirmation", "settings_updates"),
    [
        ("wrong", {}),
        (CONFIRMATION, {"environment": "production"}),
        (CONFIRMATION, {"release_id": "different-staging"}),
        (CONFIRMATION, {"chat_worker_contract_version": "worker-v2"}),
        (CONFIRMATION, {"db_search_path": "public"}),
    ],
)
def test_disabled_schema_audit_cli_refuses_every_unsafe_operator_context(
    tmp_path, monkeypatch, capsys, confirmation, settings_updates
):
    release = _install_active_staging_release(tmp_path, monkeypatch)
    release_id = f"{'a' * 12}-staging"
    manifest = {
        "release_id": release_id,
        "chat_runtime": {"worker_contract_version": "worker-v1"},
    }
    settings_values = {
        "release_id": release_id,
        "chat_durable_turn_dispatch_enabled": False,
    }
    settings_values.update(settings_updates)
    monkeypatch.setattr(durable_script, "validate_manifest", lambda *_args: manifest)
    monkeypatch.setattr(
        durable_script,
        "get_settings",
        lambda: _settings(**settings_values),
    )
    monkeypatch.setattr(
        durable_script,
        "inspect_postgresql_contract",
        lambda _db: pytest.fail("unsafe operator context reached database audit"),
    )

    exit_code = durable_script.main(
        [
            "--release-dir",
            str(release),
            "--confirm",
            confirmation,
            "--audit-disabled-only",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report["status"] == {"passed": False}


@pytest.mark.parametrize(
    "field", ["schema", "role", "owner", "privileges", "indexes", "constraints"]
)
def test_disabled_schema_audit_cli_refuses_each_contract_mismatch(
    tmp_path, monkeypatch, capsys, field
):
    release = _install_active_staging_release(tmp_path, monkeypatch)
    release_id = f"{'a' * 12}-staging"
    manifest = {
        "release_id": release_id,
        "chat_runtime": {"worker_contract_version": "worker-v1"},
    }
    factory = _session_factory()
    monkeypatch.setattr(durable_script, "validate_manifest", lambda *_args: manifest)
    monkeypatch.setattr(
        durable_script,
        "get_settings",
        lambda: _settings(
            release_id=release_id,
            chat_durable_turn_dispatch_enabled=False,
        ),
    )
    monkeypatch.setattr(durable_script.db_manager, "_session_local", factory)
    monkeypatch.setattr(
        durable_script,
        "inspect_postgresql_contract",
        lambda _db: _valid_audit(**{field: False}),
    )

    exit_code = durable_script.main(
        [
            "--release-dir",
            str(release),
            "--confirm",
            CONFIRMATION,
            "--audit-disabled-only",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report["status"] == {"passed": False}
    assert report["schema_audit"][field] is False


def test_disabled_schema_audit_cli_refuses_nonactive_release_before_database(
    tmp_path, monkeypatch, capsys
):
    active_release = _install_active_staging_release(tmp_path, monkeypatch)
    other_release = active_release.parent / f"{'b' * 12}-staging"
    other_release.mkdir()
    monkeypatch.setattr(
        durable_script,
        "validate_manifest",
        lambda *_args: pytest.fail("non-active release reached manifest validation"),
    )
    monkeypatch.setattr(
        durable_script,
        "get_settings",
        lambda: pytest.fail("non-active release reached runtime settings"),
    )

    exit_code = durable_script.main(
        [
            "--release-dir",
            str(other_release),
            "--confirm",
            CONFIRMATION,
            "--audit-disabled-only",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report["mode"] == "disabled_schema_audit"
    assert report["status"] == {"passed": False}


def test_postgresql_catalog_boundary_maps_only_aggregate_audit_booleans():
    statements = []

    class Result:
        def mappings(self):
            return self

        def one(self):
            indexes, constraints = _valid_definition_snapshot()
            return {
                "schema": True,
                "role": True,
                "owner": True,
                "privileges": True,
                "index_definitions": indexes,
                "constraint_definitions": constraints,
            }

    class Bind:
        class Dialect:
            name = "postgresql"

        dialect = Dialect()

    class Database:
        bind = Bind()

        def execute(self, statement):
            statements.append(str(statement).strip())
            return Result()

    assert inspect_postgresql_contract(Database()) == _valid_audit()
    assert statements[0] == "SET TRANSACTION READ ONLY"
    assert len(statements) == 2


def test_catalog_audit_refuses_a_non_postgresql_database():
    class Bind:
        class Dialect:
            name = "sqlite"

        dialect = Dialect()

    class Database:
        bind = Bind()

    with pytest.raises(QualificationRefused, match="PostgreSQL"):
        inspect_postgresql_contract(Database())


@pytest.mark.parametrize(
    ("error_type", "failure_code"),
    [(RuntimeError, "runtime_failure"), (SQLAlchemyError, "database_failure")],
)
def test_cli_sanitizes_failure_and_reports_completed_cleanup(
    tmp_path, monkeypatch, capsys, error_type, failure_code
):
    factory = _session_factory()
    release = tmp_path / "release"
    release.mkdir()
    manifest = {
        "release_id": "abc123-staging",
        "chat_runtime": {"worker_contract_version": "worker-v1"},
    }
    monkeypatch.setattr(durable_script, "validate_manifest", lambda *_args: manifest)
    monkeypatch.setattr(durable_script, "get_settings", _settings)
    monkeypatch.setattr(durable_script.db_manager, "_session_local", factory)
    monkeypatch.setattr(
        durable_script, "inspect_postgresql_contract", lambda _db: _valid_audit()
    )

    def fail_with_sensitive_context(_repository, _db, *, claim, **_kwargs):
        raise error_type(
            f"UPDATE chat_turn_jobs SET state='bad' WHERE turn_id={claim.turn_id}"
        )

    monkeypatch.setattr(ChatTurnJobRepository, "heartbeat", fail_with_sensitive_context)

    exit_code = durable_script.main(
        [
            "--release-dir",
            str(release),
            "--confirm",
            CONFIRMATION,
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert exit_code == 1
    assert captured.err == ""
    assert report["outcomes"] == {"qualification": failure_code}
    assert report["scenarios"] == {"requested": 7, "passed": 3, "failed": 1}
    assert report["timing_ms"]["count"] == 3
    assert 0 <= report["timing_ms"]["min"] <= report["timing_ms"]["p50"]
    assert report["timing_ms"]["p50"] <= report["timing_ms"]["max"]
    assert report["cleanup"] == {
        "clean": True,
        "jobs_deleted": 2,
        "sessions_deleted": 4,
    }
    assert (
        re.search(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            captured.out,
        )
        is None
    )
    assert "UPDATE" not in captured.out
    assert "turn_id" not in captured.out
    assert "qualify-" not in captured.out
    with factory() as db:
        assert db.query(ChatTurnJob).count() == 0
        assert db.query(ChatSession).count() == 0


@pytest.mark.parametrize("control_flow", [KeyboardInterrupt(), SystemExit(9)])
def test_cli_does_not_swallow_process_control_exceptions(
    tmp_path, monkeypatch, control_flow
):
    release = tmp_path / "release"
    release.mkdir()

    def interrupt(*_args):
        raise control_flow

    monkeypatch.setattr(durable_script, "validate_manifest", interrupt)

    with pytest.raises(type(control_flow)):
        durable_script.main(
            [
                "--release-dir",
                str(release),
                "--confirm",
                CONFIRMATION,
            ]
        )
