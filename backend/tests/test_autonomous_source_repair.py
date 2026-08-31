import hashlib
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.services.autonomous_capabilities import Capability
from backend.models.database import AutonomousReleaseConsumption
from backend.services.autonomous_operations_repository import (
    ManualModeEnabled,
    Operator,
    RepairLease,
    RepairLeaseUnavailable,
    RunContext,
)
from deploy.autonomous_check_runner import (
    CheckRunnerError,
    _immutable_runtime,
    _resource_limited_command,
    _run_bounded,
    _sandbox_command,
    _stop_unit,
    run_check,
)
from deploy.autonomous_release_bridge import (
    BridgeError,
    consume_authorization,
    parse_request,
)
from deploy.install_deploy_tools import (
    autonomous_check_wrapper,
    autonomous_release_broker_check,
    autonomous_release_wrapper,
    autonomous_sudoers,
)
from backend.services.autonomous_release_service import (
    AutonomousReleaseService,
    ReleaseVerificationError,
)
from backend.services.autonomous_source_repair import (
    AutonomousSourceRepairService,
    CandidatePolicyError,
    CheckOutcome,
    RepairProposal,
    RepairTarget,
    ReviewDecision,
    ReviewRejected,
)


NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)
RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")
TEST_RUNTIME = Path("/srv/paperswithcode/.venv")
TARGETS = {
    "example_job": RepairTarget(
        source_paths=(".github/workflows/scripts/example_job.py",),
        test_paths=("backend/tests/test_example_cron.py",),
    )
}


class FakeDB:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class LeaseRepository:
    def __init__(self, error=None, owns=True):
        self.error = error
        self.owns = owns
        self.released = []
        self.actions = []

    def acquire_repair_lease(self, _db, *, context, ttl):
        if self.error:
            raise self.error
        return RepairLease(uuid.uuid4(), context.run_id, NOW + ttl)

    def release_repair_lease(self, _db, *, lease_id, owner_run_id):
        self.released.append((lease_id, owner_run_id))
        return True

    def owns_repair_lease(self, _db, *, context):
        return self.owns

    def assert_mutation_allowed(self, _db, context):
        if self.error:
            raise self.error

    def append_action(self, _db, **values):
        self.actions.append(values)

    def has_published_repair(self, _db, *, context, sha_digest):
        return True


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )


@pytest.fixture
def repository(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git("init", "-b", "main", cwd=source)
    git("config", "user.email", "autonomy@example.com", cwd=source)
    git("config", "user.name", "Autonomy Test", cwd=source)
    job = source / ".github/workflows/scripts/example_job.py"
    job.parent.mkdir(parents=True)
    job.write_text("VALUE = 1\n", encoding="utf-8")
    test = source / "backend/tests/test_example_cron.py"
    test.parent.mkdir(parents=True)
    test.write_text("def test_example():\n    assert True\n", encoding="utf-8")
    git("add", ".", cwd=source)
    git("commit", "-m", "base", cwd=source)
    origin = tmp_path / "origin.git"
    git("clone", "--bare", str(source), str(origin), cwd=tmp_path)
    git("remote", "add", "origin", str(origin), cwd=source)
    git("fetch", "origin", cwd=source)
    return source


@pytest.fixture
def release_postgres():
    database_url = os.getenv("PWC_AUTONOMOUS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("PWC_AUTONOMOUS_TEST_DATABASE_URL is not configured")
    parsed = make_url(database_url)
    if not (parsed.database or "").startswith("autonomous_ops_test_"):
        pytest.fail("release broker tests require a disposable autonomy database")
    engine = create_engine(database_url, pool_size=4)
    schema = f"autonomy_release_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"""
CREATE SCHEMA {schema};
CREATE TABLE {schema}.autonomous_operator_state (
    operator TEXT PRIMARY KEY, enabled BOOLEAN NOT NULL, manual_mode BOOLEAN NOT NULL
);
CREATE TABLE {schema}.autonomous_run (
    id UUID PRIMARY KEY, operator TEXT NOT NULL, dry_run BOOLEAN NOT NULL
);
CREATE TABLE {schema}.autonomous_action (
    id UUID PRIMARY KEY, run_id UUID NOT NULL, operator TEXT NOT NULL,
    capability TEXT NOT NULL, reason_code TEXT NOT NULL,
    resource_kind TEXT NOT NULL, resource_identifier TEXT NOT NULL,
    after_digest TEXT, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE {schema}.autonomous_repair_lease (
    singleton_key TEXT PRIMARY KEY, owner_run_id UUID NOT NULL,
    owner_operator TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE {schema}.autonomous_release_consumption (
    authorization_action_id UUID PRIMARY KEY, run_id UUID NOT NULL,
    action TEXT NOT NULL, environment TEXT NOT NULL, sha TEXT NOT NULL,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
"""
        )
    try:
        yield engine, schema
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
        engine.dispose()


def _seed_release_authorization(
    engine,
    schema,
    *,
    reason_code="deploy_started",
    environment="production",
    action_age="0 seconds",
):
    sha = "a" * 40
    digest = hashlib.sha256(sha.encode()).hexdigest()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"""
TRUNCATE {schema}.autonomous_release_consumption,
         {schema}.autonomous_action,
         {schema}.autonomous_repair_lease,
         {schema}.autonomous_run,
         {schema}.autonomous_operator_state;
INSERT INTO {schema}.autonomous_operator_state VALUES
    ('global', false, false), ('cron_health', true, false);
INSERT INTO {schema}.autonomous_run VALUES
    ('{RUN_ID}', 'cron_health', false);
INSERT INTO {schema}.autonomous_repair_lease VALUES
    ('source_repair', '{RUN_ID}', 'cron_health',
     clock_timestamp() + interval '1 hour');
INSERT INTO {schema}.autonomous_action VALUES
    ('00000000-0000-0000-0000-000000000091', '{RUN_ID}', 'cron_health',
     'repair_declared_cron_source', 'published', 'source_repair', 'example_job',
     '{digest}', clock_timestamp() - interval '1 minute'),
    ('00000000-0000-0000-0000-000000000092', '{RUN_ID}', 'cron_health',
     'repair_declared_cron_source', '{reason_code}', 'source_repair',
     '{environment}:{sha}', '{digest}',
     clock_timestamp() - interval '{action_age}');
"""
        )


def _postgres_runner(engine, barrier=None):
    def run(command, **_kwargs):
        if barrier is not None:
            barrier.wait(timeout=10)
        with engine.begin() as connection:
            consumed = connection.exec_driver_sql(command[-1]).scalar_one_or_none()
        output = f"{consumed}\n" if consumed is not None else "\n"
        return subprocess.CompletedProcess(command, 0, output, "")

    return run


def proposal():
    return RepairProposal(
        capability=Capability.REPAIR_DECLARED_CRON_SOURCE,
        declared_job="example_job",
    )


def check(command, _cwd):
    return CheckOutcome(command, hashlib.sha256(repr(command).encode()).hexdigest())


def review(alias, _bundle, *, approved=True):
    return ReviewDecision(alias, approved, "e" * 64)


def context():
    return RunContext(RUN_ID, Operator.CRON_HEALTH, False, "manifest-v1")


def test_prepare_candidate_uses_clean_isolated_worktree(repository, tmp_path):
    dirty = repository / "local-note.txt"
    dirty.write_text("unrelated\n", encoding="utf-8")
    service = AutonomousSourceRepairService(
        repository=LeaseRepository(),
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
    )

    candidate = service.prepare_candidate(object(), context(), proposal())

    assert candidate.worktree != repository
    assert git("status", "--porcelain", cwd=candidate.worktree).stdout == ""
    assert dirty.is_file()
    assert (
        candidate.base_sha
        == git("rev-parse", "origin/main", cwd=repository).stdout.strip()
    )


def test_prepare_candidate_preserves_global_lease_contention(repository, tmp_path):
    service = AutonomousSourceRepairService(
        repository=LeaseRepository(RepairLeaseUnavailable("owned")),
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
    )

    with pytest.raises(RepairLeaseUnavailable):
        service.prepare_candidate(object(), context(), proposal())


def test_prepare_rejects_job_missing_from_server_registry(repository, tmp_path):
    service = AutonomousSourceRepairService(
        repository=LeaseRepository(),
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
    )
    unknown = RepairProposal(Capability.REPAIR_DECLARED_CRON_SOURCE, "unrelated_job")

    with pytest.raises(CandidatePolicyError, match="not repairable"):
        service.prepare_candidate(object(), context(), unknown)


def test_worktree_intent_is_discoverable_before_git_add(repository, tmp_path):
    leases = LeaseRepository()
    root = tmp_path / "candidates"
    service = AutonomousSourceRepairService(
        repository=leases,
        source_repository=repository,
        candidates_root=root,
        repair_targets=TARGETS,
        min_free_bytes=1,
    )
    real_git = service._git

    def fail_after_intent(*args, **kwargs):
        if args[:2] == ("worktree", "add"):
            assert list(root.glob("*.json"))
            raise subprocess.CalledProcessError(1, args)
        return real_git(*args, **kwargs)

    service._git = fail_after_intent

    with pytest.raises(subprocess.CalledProcessError):
        service.prepare_candidate(object(), context(), proposal())
    assert not list(root.glob("*.json"))


def test_review_rejects_undeclared_or_forbidden_paths(repository, tmp_path):
    service = AutonomousSourceRepairService(
        repository=LeaseRepository(),
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
    )
    candidate = service.prepare_candidate(object(), context(), proposal())
    forbidden = candidate.worktree / "backend/database/migrations/escape.sql"
    forbidden.parent.mkdir(parents=True)
    forbidden.write_text("DROP TABLE paper;\n", encoding="utf-8")

    with pytest.raises(CandidatePolicyError):
        service.review_candidate(
            FakeDB(),
            candidate,
            reviewer_alias="diagnosis",
            reviewer=review,
        )


def test_review_runs_server_selected_checks_and_rejection_stops_publish(
    repository, tmp_path
):
    checks = []
    service = AutonomousSourceRepairService(
        repository=LeaseRepository(),
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
        check_runner=lambda command, cwd: checks.append((command, cwd))
        or check(command, cwd),
    )
    candidate = service.prepare_candidate(object(), context(), proposal())
    (candidate.worktree / ".github/workflows/scripts/example_job.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )

    with pytest.raises(ReviewRejected):
        service.review_candidate(
            FakeDB(),
            candidate,
            reviewer_alias="diagnosis",
            reviewer=lambda alias, bundle: review(alias, bundle, approved=False),
        )

    assert checks[0][0][0] == "lint"
    assert checks[1][0][-1] == "backend/tests/test_example_cron.py"


def test_review_fails_if_a_check_changes_the_candidate(repository, tmp_path):
    def mutating_check(command, cwd):
        if command[0] == "pytest":
            (cwd / ".github/workflows/scripts/example_job.py").write_text(
                "VALUE = 3\n", encoding="utf-8"
            )
        return check(command, cwd)

    service = AutonomousSourceRepairService(
        repository=LeaseRepository(),
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
        check_runner=mutating_check,
    )
    candidate = service.prepare_candidate(object(), context(), proposal())
    (candidate.worktree / ".github/workflows/scripts/example_job.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )

    with pytest.raises(CandidatePolicyError, match="changed during validation"):
        service.review_candidate(
            FakeDB(), candidate, reviewer_alias="diagnosis", reviewer=review
        )


def test_manual_mode_enabled_after_review_blocks_push(repository, tmp_path):
    leases = LeaseRepository()
    service = AutonomousSourceRepairService(
        repository=leases,
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
        check_runner=check,
    )
    db = FakeDB()
    candidate = service.prepare_candidate(db, context(), proposal())
    (candidate.worktree / ".github/workflows/scripts/example_job.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )
    bundle = service.review_candidate(
        db, candidate, reviewer_alias="diagnosis", reviewer=review
    )
    before = git(
        "rev-parse", "refs/heads/main", cwd=repository.parent / "origin.git"
    ).stdout
    leases.error = ManualModeEnabled("manual")

    with pytest.raises(ManualModeEnabled):
        service.publish_candidate(db, candidate, bundle)
    assert (
        git("rev-parse", "refs/heads/main", cwd=repository.parent / "origin.git").stdout
        == before
    )


def test_cleanup_removes_only_registered_candidate_and_releases_lease(
    repository, tmp_path
):
    leases = LeaseRepository()
    service = AutonomousSourceRepairService(
        repository=leases,
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
    )
    run_context = context()
    candidate = service.prepare_candidate(object(), run_context, proposal())

    service.cleanup_candidate(object(), candidate)

    assert not candidate.worktree.exists()
    assert leases.released == [(candidate.lease_id, run_context.run_id)]


def test_cleanup_abandoned_worktree_after_lease_expiry(repository, tmp_path):
    leases = LeaseRepository()
    root = tmp_path / "candidates"
    first = AutonomousSourceRepairService(
        repository=leases,
        source_repository=repository,
        candidates_root=root,
        repair_targets=TARGETS,
        min_free_bytes=1,
    )
    candidate = first.prepare_candidate(object(), context(), proposal())
    leases.owns = False
    restarted = AutonomousSourceRepairService(
        repository=leases,
        source_repository=repository,
        candidates_root=root,
        repair_targets=TARGETS,
        min_free_bytes=1,
    )

    cleaned = restarted.cleanup_abandoned(
        object(), now=datetime.now(UTC) + timedelta(days=1)
    )

    assert cleaned == 1
    assert not candidate.worktree.exists()
    assert leases.released == [(candidate.lease_id, candidate.context.run_id)]


class CommandRecorder:
    def __init__(self):
        self.commands = []

    def __call__(self, command):
        self.commands.append(tuple(command))


def test_release_promotes_only_exact_sha_and_verifies_canary():
    commands = CommandRecorder()
    sha = "a" * 40
    service = AutonomousReleaseService(
        repository=LeaseRepository(),
        command_runner=commands,
        deployed_sha=lambda environment: sha,
        smoke_verifier=lambda environment, expected: True,
    )

    service.deploy_exact_sha(FakeDB(), context(), "staging", sha)

    assert commands.commands == [
        (
            "/usr/local/sbin/pwc-autonomous-release",
            "deploy",
            "staging",
            sha,
            str(RUN_ID),
        )
    ]


def test_manual_mode_blocks_deploy_before_command():
    commands = CommandRecorder()
    service = AutonomousReleaseService(
        repository=LeaseRepository(ManualModeEnabled("manual")),
        command_runner=commands,
        deployed_sha=lambda _environment: "a" * 40,
        smoke_verifier=lambda _environment, _expected: True,
    )

    with pytest.raises(ManualModeEnabled):
        service.deploy_exact_sha(FakeDB(), context(), "staging", "b" * 40)
    assert commands.commands == []


def test_non_chat_pipeline_blocks_production_sha_containing_chat_changes():
    commands = CommandRecorder()
    service = AutonomousReleaseService(
        repository=LeaseRepository(),
        command_runner=commands,
        deployed_sha=lambda _environment: "a" * 40,
        smoke_verifier=lambda _environment, _expected: True,
        changed_paths=lambda _before, _after: ("backend/services/chat_runtime.py",),
    )

    with pytest.raises(ReleaseVerificationError, match="staging-only chat"):
        service.deploy_exact_sha(FakeDB(), context(), "production", "b" * 40)
    assert commands.commands == []


def test_default_production_diff_uses_privileged_fetching_bridge():
    inspected = []

    def inspect(command):
        inspected.append(tuple(command))
        return ".github/workflows/scripts/example_job.py\n"

    service = AutonomousReleaseService(
        repository=LeaseRepository(),
        command_runner=CommandRecorder(),
        deployed_sha=lambda _environment: "a" * 40,
        smoke_verifier=lambda _environment, _expected: True,
        inspection_runner=inspect,
    )

    assert service.changed_paths("a" * 40, "b" * 40) == (
        ".github/workflows/scripts/example_job.py",
    )
    assert inspected == [
        (
            "/usr/local/sbin/pwc-autonomous-release",
            "diff",
            "a" * 40,
            "b" * 40,
        )
    ]


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_failed_canary_or_production_smoke_rolls_back_immediately(environment):
    commands = CommandRecorder()
    leases = LeaseRepository()
    failed_sha = "b" * 40
    previous_sha = "a" * 40
    current = [previous_sha]

    def run(command):
        commands(command)
        if command[1] == "deploy":
            current[0] = failed_sha
        elif command[1] == "rollback":
            current[0] = previous_sha

    service = AutonomousReleaseService(
        repository=leases,
        command_runner=run,
        deployed_sha=lambda _environment: current[0],
        smoke_verifier=lambda _environment, _expected: False,
        changed_paths=lambda _before, _after: (),
    )

    with pytest.raises(ReleaseVerificationError):
        service.deploy_exact_sha(FakeDB(), context(), environment, failed_sha)

    confirm = ("--confirm", "DEPLOY_PRODUCTION") if environment == "production" else ()
    rollback_confirm = (
        ("--confirm", "ROLLBACK_PRODUCTION") if environment == "production" else ()
    )
    assert commands.commands == [
        (
            "/usr/local/sbin/pwc-autonomous-release",
            "deploy",
            environment,
            failed_sha,
            str(RUN_ID),
            *confirm,
        ),
        (
            "/usr/local/sbin/pwc-autonomous-release",
            "rollback",
            environment,
            failed_sha,
            str(RUN_ID),
            *rollback_confirm,
        ),
    ]
    assert [action["reason_code"] for action in leases.actions] == [
        "deploy_started",
        "rollback_started",
        "rolled_back",
    ]


def test_rollback_refuses_when_failed_sha_is_not_current():
    service = AutonomousReleaseService(
        repository=LeaseRepository(),
        command_runner=CommandRecorder(),
        deployed_sha=lambda _environment: "d" * 40,
        smoke_verifier=lambda _environment, _expected: True,
    )

    with pytest.raises(ReleaseVerificationError, match="no longer active"):
        service.rollback(FakeDB(), context(), "staging", "e" * 40)


def test_unexpected_concurrent_sha_is_never_rolled_back():
    commands = CommandRecorder()
    current = ["a" * 40]

    def run(command):
        commands(command)
        current[0] = "c" * 40

    service = AutonomousReleaseService(
        repository=LeaseRepository(),
        command_runner=run,
        deployed_sha=lambda _environment: current[0],
        smoke_verifier=lambda _environment, _expected: True,
    )

    with pytest.raises(ReleaseVerificationError, match="unexpected SHA"):
        service.deploy_exact_sha(FakeDB(), context(), "staging", "b" * 40)
    assert commands.commands == [
        (
            "/usr/local/sbin/pwc-autonomous-release",
            "deploy",
            "staging",
            "b" * 40,
            str(RUN_ID),
        )
    ]


def test_sandbox_check_runner_is_installed_and_rejects_out_of_scope(
    tmp_path, monkeypatch
):
    assert "autonomous_check_runner.py" in autonomous_check_wrapper()
    assert "/usr/bin/sudo -n" in autonomous_check_wrapper()
    assert "/usr/bin/sudo -n" in autonomous_release_wrapper()
    assert "pwc-cron" in autonomous_sudoers()
    schema_check = autonomous_release_broker_check()
    assert "migration is not applied" in schema_check
    assert "tableowner <> 'postgres'" in schema_check
    assert "application roles can access" in schema_check
    assert "CREATE TABLE" not in schema_check

    monkeypatch.setenv("PWC_AUTONOMOUS_CHECK_ROOT", str(tmp_path.parent))
    monkeypatch.setenv("PWC_AUTONOMOUS_CHECK_TESTING", "1")
    with pytest.raises(CheckRunnerError, match="closed scope"):
        run_check(tmp_path, "pytest", ["backend/tests/test_escape.py"])


def test_release_broker_schema_is_a_checked_in_root_owned_migration():
    migration = (
        Path(__file__).parents[1]
        / "database/migrations/add_autonomous_release_broker.sql"
    ).read_text(encoding="utf-8")

    assert AutonomousReleaseConsumption.__table__.name in migration
    assert "session_user <> 'postgres'" in migration
    assert "OWNER TO postgres" in migration
    assert "REVOKE ALL" in migration


@pytest.mark.parametrize(
    "arguments",
    [
        ["deploy", "production", "a" * 39, str(RUN_ID)],
        ["deploy", "production", "a" * 40, "not-a-uuid"],
        [
            "rollback",
            "production",
            "a" * 40,
            str(RUN_ID),
            "--failed-sha",
            "b" * 40,
        ],
        ["diff", "a" * 40, "../../etc/shadow"],
        ["shell"],
    ],
)
def test_release_privilege_bridge_rejects_unbounded_requests(arguments):
    with pytest.raises(BridgeError):
        parse_request(arguments)


def test_release_privilege_bridge_accepts_only_exact_lifecycle_forms():
    sha = "a" * 40

    assert parse_request(["status"]) == ("/usr/local/sbin/pwc-status",)
    assert parse_request(["deploy", "staging", sha, str(RUN_ID)]) == (
        "/usr/local/sbin/pwc-deploy",
        "staging",
        sha,
    )
    assert parse_request(
        [
            "deploy",
            "production",
            sha,
            str(RUN_ID),
            "--confirm",
            "DEPLOY_PRODUCTION",
        ]
    ) == (
        "/usr/local/sbin/pwc-deploy",
        "production",
        sha,
        "--confirm",
        "DEPLOY_PRODUCTION",
    )
    assert parse_request(["diff", "b" * 40, sha]) is None


def test_release_bridge_consumes_one_database_backed_authorization():
    calls = []
    consumed_id = uuid.UUID("00000000-0000-0000-0000-000000000099")

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, f"{consumed_id}\n", "")

    consume_authorization("deploy", "production", "a" * 40, str(RUN_ID), runner=runner)

    command, kwargs = calls[0]
    assert command[:7] == [
        "/usr/sbin/runuser",
        "-u",
        "postgres",
        "--",
        "/usr/bin/psql",
        "--dbname",
        "paperswithcode_hf",
    ]
    query = command[-1]
    assert "manual_mode = false" in query
    assert "enabled = true" in query
    assert "expires_at > clock_timestamp()" in query
    assert "reason_code = 'published'" in query
    assert "autonomous_release_consumption" in query
    assert kwargs["env"] == {"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"}


def test_release_bridge_rejects_missing_or_consumed_authorization():
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "\n", "")

    with pytest.raises(BridgeError, match="single-use"):
        consume_authorization(
            "rollback", "staging", "a" * 40, str(RUN_ID), runner=runner
        )


def test_postgres_release_authorization_is_single_use(release_postgres):
    engine, schema = release_postgres
    _seed_release_authorization(engine, schema)
    runner = _postgres_runner(engine)

    consume_authorization(
        "deploy",
        "production",
        "a" * 40,
        str(RUN_ID),
        runner=runner,
        schema=schema,
    )
    with pytest.raises(BridgeError, match="single-use"):
        consume_authorization(
            "deploy",
            "production",
            "a" * 40,
            str(RUN_ID),
            runner=runner,
            schema=schema,
        )


@pytest.mark.parametrize(
    "gate_sql",
    [
        "UPDATE {schema}.autonomous_operator_state SET manual_mode=true "
        "WHERE operator='global'",
        "UPDATE {schema}.autonomous_operator_state SET enabled=false "
        "WHERE operator='cron_health'",
        "UPDATE {schema}.autonomous_repair_lease "
        "SET expires_at=clock_timestamp()-interval '1 second'",
        "UPDATE {schema}.autonomous_repair_lease "
        "SET owner_run_id='00000000-0000-0000-0000-000000000099'",
        "UPDATE {schema}.autonomous_action SET after_digest='b' "
        "WHERE reason_code='published'",
        "UPDATE {schema}.autonomous_action "
        "SET resource_identifier='staging:' || repeat('a',40) "
        "WHERE reason_code='deploy_started'",
    ],
)
def test_postgres_release_authorization_rechecks_every_durable_gate(
    release_postgres, gate_sql
):
    engine, schema = release_postgres
    _seed_release_authorization(engine, schema)
    with engine.begin() as connection:
        connection.execute(text(gate_sql.format(schema=schema)))

    with pytest.raises(BridgeError, match="single-use"):
        consume_authorization(
            "deploy",
            "production",
            "a" * 40,
            str(RUN_ID),
            runner=_postgres_runner(engine),
            schema=schema,
        )


def test_postgres_release_authorization_binds_run_action_and_expiry(
    release_postgres,
):
    engine, schema = release_postgres
    runner = _postgres_runner(engine)

    _seed_release_authorization(engine, schema)
    with pytest.raises(BridgeError, match="single-use"):
        consume_authorization(
            "deploy",
            "production",
            "a" * 40,
            "00000000-0000-0000-0000-000000000099",
            runner=runner,
            schema=schema,
        )

    _seed_release_authorization(engine, schema, reason_code="deploy_started")
    with pytest.raises(BridgeError, match="single-use"):
        consume_authorization(
            "rollback",
            "production",
            "a" * 40,
            str(RUN_ID),
            runner=runner,
            schema=schema,
        )

    _seed_release_authorization(engine, schema, action_age="6 minutes")
    with pytest.raises(BridgeError, match="single-use"):
        consume_authorization(
            "deploy",
            "production",
            "a" * 40,
            str(RUN_ID),
            runner=runner,
            schema=schema,
        )


def test_postgres_concurrent_release_consumers_have_one_winner(release_postgres):
    engine, schema = release_postgres
    _seed_release_authorization(engine, schema)
    barrier = Barrier(2)

    def consume():
        try:
            consume_authorization(
                "deploy",
                "production",
                "a" * 40,
                str(RUN_ID),
                runner=_postgres_runner(engine, barrier),
                schema=schema,
            )
        except BridgeError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: consume(), range(2)))

    assert sorted(results) == [False, True]


def test_sandbox_mounts_candidate_read_only_and_has_hard_resource_limits(tmp_path):
    candidate = tmp_path / "candidate-test"
    command = _sandbox_command(
        candidate,
        tmp_path / "python",
        ["-m", "pytest"],
        runtime=tmp_path,
    )

    assert command[command.index("--ro-bind") + 1 : command.index("--ro-bind") + 3] != [
        str(candidate),
        "/workspace",
    ]
    assert ["--ro-bind", str(candidate), "/workspace"] == command[
        command.index(str(candidate)) - 1 : command.index(str(candidate)) + 2
    ]

    limited = _resource_limited_command(command, "pwc-autonomous-check-test")
    for required in (
        "TasksMax=64",
        "MemoryMax=1073741824",
        "MemorySwapMax=0",
        "CPUQuota=200%",
        "RuntimeMaxSec=1800",
        "LimitFSIZE=67108864",
        "TemporaryFileSystem=/tmp:size=64M",
    ):
        assert f"--property={required}" in limited


def test_checker_resolves_runtime_from_candidate_lockfile(tmp_path, monkeypatch):
    import deploy.autonomous_check_runner as runner

    candidate = tmp_path / "candidate"
    candidate.mkdir()
    lockfile = candidate / "uv.lock"
    lockfile.write_text("version = 1\n", encoding="utf-8")
    identifier = hashlib.sha256(lockfile.read_bytes()).hexdigest()
    runtimes = tmp_path / "runtimes"
    runtime = runtimes / identifier
    (runtime / "bin").mkdir(parents=True)
    (runtime / "runtime.json").write_text(
        '{"lock_sha256": "' + identifier + '"}\n', encoding="utf-8"
    )
    for path in ("bin/python", "bin/pytest", "bin/ruff"):
        (runtime / path).touch()
    monkeypatch.setattr(runner, "RUNTIMES", runtimes)

    assert _immutable_runtime(candidate) == runtime


def test_sandbox_candidate_tests_cannot_rewrite_source(tmp_path):
    root = tmp_path / "candidates"
    candidate = root / "candidate-test"
    tests = candidate / "backend/tests"
    tests.mkdir(parents=True)
    source = candidate / "example.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    (tests / "test_mutate.py").write_text(
        "from pathlib import Path\n"
        "def test_mutate():\n"
        "    Path('example.py').write_text('VALUE = 2\\n')\n",
        encoding="utf-8",
    )
    with pytest.raises(subprocess.CalledProcessError):
        run_check(
            candidate,
            "pytest",
            ["backend/tests/test_mutate.py"],
            root=root,
            testing=True,
            runtime=TEST_RUNTIME,
        )
    assert source.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_sandbox_output_is_stopped_at_hard_cap():
    with pytest.raises(CheckRunnerError, match="output exceeded"):
        _run_bounded(
            [sys.executable, "-c", "print('x' * 70000)"],
            unit=None,
        )


def test_sandbox_cleanup_kills_every_process(monkeypatch):
    commands = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: commands.append(command),
    )

    _stop_unit("pwc-autonomous-check-test")

    assert commands == [
        [
            "/usr/bin/systemctl",
            "kill",
            "--signal=SIGKILL",
            "--kill-whom=all",
            "pwc-autonomous-check-test.service",
        ]
    ]


def test_production_python_lint_runs_ruff_check_and_format(tmp_path, monkeypatch):
    import deploy.autonomous_check_runner as runner

    root = tmp_path / "candidates"
    candidate = root / "candidate-test"
    candidate.mkdir(parents=True)
    (candidate / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
    captured = []
    monkeypatch.setattr(
        runner,
        "_run_bounded",
        lambda command, *, unit: captured.append(command),
    )

    run_check(candidate, "lint", ["example.py"], root=root, runtime=TEST_RUNTIME)

    flattened = [part for command in captured for part in command]
    assert flattened.count(str(TEST_RUNTIME / "bin/ruff")) == 2
    assert "check" in flattened
    assert "--no-fix" in flattened
    assert "format" in flattened
    assert "--check" in flattened


def test_sandbox_check_runner_executes_without_network_or_keys(tmp_path):
    root = tmp_path / "candidates"
    candidate = root / "candidate-test"
    tests = candidate / "backend/tests"
    tests.mkdir(parents=True)
    (candidate / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests / "test_safe.py").write_text(
        "import os\n"
        "def test_sandbox():\n"
        "    assert 'HF_TOKEN' not in os.environ\n"
        "    assert not __import__('pathlib').Path('/root').exists()\n",
        encoding="utf-8",
    )
    run_check(
        candidate,
        "lint",
        ["example.py"],
        root=root,
        testing=True,
        runtime=TEST_RUNTIME,
    )
    run_check(
        candidate,
        "pytest",
        ["backend/tests/test_safe.py"],
        root=root,
        testing=True,
        runtime=TEST_RUNTIME,
    )


def test_review_bundle_digest_binds_patch(repository, tmp_path):
    leases = LeaseRepository()
    service = AutonomousSourceRepairService(
        repository=leases,
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
        check_runner=check,
    )
    candidate = service.prepare_candidate(object(), context(), proposal())
    (candidate.worktree / ".github/workflows/scripts/example_job.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )

    db = FakeDB()
    bundle = service.review_candidate(
        db, candidate, reviewer_alias="diagnosis", reviewer=review
    )

    patch = git("diff", "--binary", "HEAD", cwd=candidate.worktree).stdout.encode()
    assert bundle.patch_digest == hashlib.sha256(patch).hexdigest()
    assert [action["reason_code"] for action in leases.actions] == [
        "validation_passed",
        "review_approved",
    ]
    assert len(bundle.check_outcomes) == 2
    assert db.commits == 2


def test_publish_pushes_only_reviewed_commit_on_unchanged_origin(repository, tmp_path):
    service = AutonomousSourceRepairService(
        repository=LeaseRepository(),
        source_repository=repository,
        candidates_root=tmp_path / "candidates",
        repair_targets=TARGETS,
        min_free_bytes=1,
        check_runner=check,
    )
    candidate = service.prepare_candidate(object(), context(), proposal())
    (candidate.worktree / ".github/workflows/scripts/example_job.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )
    bundle = service.review_candidate(
        FakeDB(), candidate, reviewer_alias="diagnosis", reviewer=review
    )

    sha = service.publish_candidate(FakeDB(), candidate, bundle)

    assert (
        sha
        == git(
            "rev-parse", "refs/heads/main", cwd=repository.parent / "origin.git"
        ).stdout.strip()
    )
    assert (
        git(
            "show", f"{sha}:.github/workflows/scripts/example_job.py", cwd=repository
        ).stdout
        == "VALUE = 2\n"
    )
