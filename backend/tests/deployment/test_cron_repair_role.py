"""The taxonomy-safe database role and host identity for source-repairable CRON jobs.

The PostgreSQL checks need ``PWC_CRON_REPAIR_ROLE_TEST_DATABASE_URL``: a
superuser URL for a database whose name contains "test" in a disposable
cluster, because the migration creates cluster-wide roles.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import psycopg2
import pytest
from psycopg2 import errors
from sqlalchemy.engine import make_url

import deploy.configure_db_roles as configure_db_roles
import deploy.cron_launcher as cron_launcher
from backend.services.autonomous_cron_operator import (
    _SAFE_SOURCE_REPAIRS,
    build_cron_repair_contracts,
)
from deploy.install_deploy_tools import cron_wrapper

REPO = Path(__file__).resolve().parents[3]
MIGRATION = REPO / "backend/database/migrations/add_cron_repair_role.sql"


def test_source_repair_is_limited_to_jobs_under_a_taxonomy_safe_identity():
    assert _SAFE_SOURCE_REPAIRS == (
        cron_launcher.RESTRICTED_TRENDING_JOBS | cron_launcher.CRON_REPAIR_JOBS
    )
    assert not cron_launcher.RESTRICTED_TRENDING_JOBS & cron_launcher.CRON_REPAIR_JOBS
    assert cron_launcher.CRON_REPAIR_JOBS <= set(cron_launcher.COMMANDS)
    contracts = build_cron_repair_contracts()
    assert {
        name for name, contract in contracts.items() if contract.source_repair_allowed
    } == _SAFE_SOURCE_REPAIRS


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _module_name(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".")


def test_repairable_source_runs_only_under_a_taxonomy_safe_identity():
    sources = [
        path
        for root in ("backend", ".github", "deploy", "url_extraction_agent")
        for path in (REPO / root).rglob("*.py")
        if "tests" not in path.relative_to(REPO).parts
    ]
    imports = {path: _imported_modules(path) for path in sources}
    contracts = build_cron_repair_contracts()
    repairable = {
        path
        for contract in contracts.values()
        if contract.source_repair_allowed
        for path in contract.source_paths
    }
    for owned_path in repairable:
        module = _module_name(owned_path)
        short = module.removeprefix(".github.workflows.")
        importers = {
            str(path.relative_to(REPO))
            for path, modules in imports.items()
            if module in modules or short in modules
        }
        assert importers <= repairable, (owned_path, importers - repairable)
    for name, spec in cron_launcher.COMMANDS.items():
        if name in _SAFE_SOURCE_REPAIRS:
            continue
        entries = {
            spec.command[1]
            if spec.command[0] == "-m"
            else _module_name(spec.command[0])
        }
        assert not {
            path
            for path in repairable
            if {
                _module_name(path),
                _module_name(path).removeprefix(".github.workflows."),
            }
            & entries
        }, name


def test_cron_wrapper_runs_repairable_jobs_as_the_repair_identity():
    wrapper = cron_wrapper()
    branches = wrapper.split('case "$1" in', 1)[1].split("esac", 1)[0]
    pattern, branch = re.search(
        r"\n  ([a-z_|]+)\)\n(.*?)\n    ;;", branches.split(";;", 1)[1], re.S
    ).groups()

    assert set(pattern.split("|")) == cron_launcher.CRON_REPAIR_JOBS
    assert "--uid=pwc-cron-repair --gid=pwc-cron-repair" in branch
    assert "EnvironmentFile=/etc/paperswithcode/repair-cron.env" in branch
    assert "SupplementaryGroups" not in branch
    assert "repair-cron.env" not in wrapper.replace(branch, "")


def test_repair_environment_replaces_the_application_database_login():
    source = {
        "PATH": "/usr/bin",
        "PWC_DB_HOST": "db",
        "PWC_DB_NAME": "paperswithcode",
        "PWC_DB_USER": "paperswithcode_user",
        "PWC_DB_PASSWORD": "application-secret",
        "PWC_CRON_REPAIR_DB_PASSWORD": "repair-secret",
        "PWC_POSTGRES_BACKUP_DB_PASSWORD": "backup-secret",
        "PWC_POSTGRES_BACKUP_DB_USER": "pwc_backup",
        "PWC_JWT_SECRET": "app-only",
        "X_API_BEARER_TOKEN": "job-token",
        "HF_HOME": "/var/lib/paperswithcode/production/hf-cache",
    }

    environment = cron_launcher.cron_repair_environment(source, "refresh_x_post_likes")

    assert environment["PWC_DB_USER"] == "pwc_cron_repair"
    assert environment["PWC_DB_PASSWORD"] == "repair-secret"
    assert "application-secret" not in environment.values()
    assert "backup-secret" not in environment.values()
    assert "PWC_CRON_REPAIR_DB_PASSWORD" not in environment
    assert "PWC_POSTGRES_BACKUP_DB_USER" not in environment
    assert "PWC_JWT_SECRET" not in environment
    assert environment["X_API_BEARER_TOKEN"] == "job-token"
    assert environment["PWC_CRON_LOG_DIR"] == str(cron_launcher.CRON_REPAIR_LOG_DIR)
    assert environment["PWC_CRON_LOCK_DIR"] == str(cron_launcher.CRON_REPAIR_LOCK_DIR)
    assert environment["HF_HOME"].startswith(str(cron_launcher.CRON_REPAIR_STATE_DIR))


def test_repair_environment_fails_closed_without_the_role_password():
    with pytest.raises(RuntimeError, match="PWC_CRON_REPAIR_DB_PASSWORD"):
        cron_launcher.cron_repair_environment(
            {"PWC_DB_USER": "paperswithcode_user", "PWC_DB_PASSWORD": "secret"},
            "refresh_paper_embeddings",
        )


def test_role_configuration_applies_the_migration_then_sets_the_password():
    sql = configure_db_roles.cron_repair_role_sql(password="it's-secret")

    assert sql.startswith(MIGRATION.read_text(encoding="utf-8"))
    assert sql.endswith("ALTER ROLE pwc_cron_repair PASSWORD 'it''s-secret';\n")
    assert "PASSWORD" not in MIGRATION.read_text(encoding="utf-8").split("--", 1)[0]


SCHEMA = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user')
    THEN
        CREATE ROLE paperswithcode_user LOGIN;
    END IF;
END $$;
DROP SCHEMA IF EXISTS public CASCADE;
DROP SCHEMA IF EXISTS staging CASCADE;
CREATE SCHEMA public;
CREATE SCHEMA staging;
CREATE TABLE staging.chat_sessions (id bigserial PRIMARY KEY);
CREATE TABLE areas (id bigserial PRIMARY KEY, name text);
CREATE TABLE tasks (id bigserial PRIMARY KEY, name text);
CREATE TABLE methods (id bigserial PRIMARY KEY, name text);
CREATE TABLE datasets (id bigserial PRIMARY KEY, name text);
CREATE TABLE metrics (id bigserial PRIMARY KEY, name text);
CREATE TABLE conferences (id bigserial PRIMARY KEY, name text);
CREATE TABLE papers (id bigserial PRIMARY KEY, title text);
CREATE TABLE paper_tasks (paper_id bigint, task_id bigint);
CREATE TABLE paper_methods (paper_id bigint, method_id bigint);
CREATE TABLE task_datasets (task_id bigint, dataset_id bigint);
CREATE TABLE x_post_metrics (id bigserial PRIMARY KEY, likes integer);
CREATE VIEW base_datasets AS SELECT id, name FROM datasets;
GRANT ALL ON ALL TABLES IN SCHEMA public, staging TO paperswithcode_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public, staging TO paperswithcode_user;
GRANT USAGE ON SCHEMA staging TO paperswithcode_user;
INSERT INTO tasks (name) VALUES ('Image Classification');
INSERT INTO papers (title) VALUES ('A paper');
INSERT INTO paper_tasks VALUES (1, 1);
"""


@pytest.fixture(scope="module")
def repair_role_database():
    url = os.getenv("PWC_CRON_REPAIR_ROLE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PWC_CRON_REPAIR_ROLE_TEST_DATABASE_URL is not configured")
    if "test" not in (make_url(url).database or ""):
        pytest.fail("Refusing a database whose name does not contain 'test'")
    connection = psycopg2.connect(url)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(SCHEMA)
        cursor.execute(MIGRATION.read_text(encoding="utf-8"))
        cursor.execute(MIGRATION.read_text(encoding="utf-8"))
    yield connection
    connection.close()


def _as_repair_role(connection, statement: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            cursor.execute("SET LOCAL ROLE pwc_cron_repair")
            cursor.execute(statement)
        finally:
            cursor.execute("ROLLBACK")


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO tasks (name) VALUES ('Invented Task')",
        "UPDATE tasks SET name = 'Renamed'",
        "DELETE FROM tasks",
        "INSERT INTO methods (name) VALUES ('Invented Method')",
        "INSERT INTO datasets (name) VALUES ('Invented Benchmark')",
        "INSERT INTO metrics (name) VALUES ('Invented Metric')",
        "INSERT INTO conferences (name) VALUES ('Invented Conference')",
        "INSERT INTO areas (name) VALUES ('Invented Area')",
        "INSERT INTO paper_tasks VALUES (1, 1)",
        "DELETE FROM paper_tasks",
        "INSERT INTO paper_methods VALUES (1, 1)",
        "INSERT INTO task_datasets VALUES (1, 1)",
        "INSERT INTO base_datasets (name) VALUES ('Through a view')",
        "TRUNCATE tasks",
        "CREATE TABLE tasks_copy (id bigint)",
        "SELECT * FROM staging.chat_sessions",
    ],
)
def test_repair_role_cannot_change_taxonomy(repair_role_database, statement):
    with pytest.raises(errors.InsufficientPrivilege):
        _as_repair_role(repair_role_database, statement)


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT name FROM tasks",
        "SELECT task_id FROM paper_tasks",
        "SELECT name FROM base_datasets",
        "INSERT INTO x_post_metrics (likes) VALUES (3)",
        "UPDATE papers SET title = 'Renamed paper'",
        "DELETE FROM x_post_metrics",
    ],
)
def test_repair_role_keeps_catalog_privileges(repair_role_database, statement):
    _as_repair_role(repair_role_database, statement)


def test_cron_health_combines_launcher_history_across_job_directories(
    tmp_path: Path, monkeypatch
):
    import json
    from types import SimpleNamespace

    from backend.services import cron_health

    main_dir = tmp_path / "cron-logs"
    repair_dir = tmp_path / "repair-cron-logs"
    records = {
        main_dir: [
            ("2026-11-24T08:00:00+00:00", "refresh_paper_embeddings", 0),
            ("2026-11-24T09:00:00+00:00", "refresh_paper_embeddings", 1),
            ("2026-11-24T09:30:00+00:00", "update_citations", 1),
        ],
        repair_dir: [
            ("2026-11-24T10:00:00+00:00", "refresh_paper_embeddings", 1),
        ],
    }
    for directory, rows in records.items():
        directory.mkdir()
        (directory / "launcher.jsonl").write_text(
            "".join(
                json.dumps({"at": at, "event": "exit", "job": job, "returncode": code})
                + "\n"
                for at, job, code in rows
            )
        )
    monkeypatch.setattr(
        cron_health,
        "get_settings",
        lambda: SimpleNamespace(environment="production", cron_log_dir=str(main_dir)),
    )
    monkeypatch.setattr(
        cron_health,
        "list_cron_jobs",
        lambda: [SimpleNamespace(log_directory=str(repair_dir))],
    )

    history = cron_health.fetch_launcher_history(
        now=cron_health._parse_log_timestamp("2026-11-24T11:00:00Z")
    )

    assert history["update_citations"]["failures"] == 1
    embeddings = history["refresh_paper_embeddings"]
    assert embeddings["runs"] == 3
    assert embeddings["failures"] == 2
    assert embeddings["consecutive_failures"] == 2
