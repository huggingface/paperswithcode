"""Environment-scoped, idempotent chat and catalog migrations."""

from __future__ import annotations

from pathlib import Path


def test_chat_share_migration_is_environment_owned_and_idempotent():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/add_chat_shares.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_shares" in migration
    assert "snapshot_version SMALLINT NOT NULL DEFAULT 1" in migration
    assert "messages JSONB NOT NULL" in migration
    assert "chat_shares_messages_array_check" in migration
    assert "REFERENCES chat_messages" not in migration
    assert migration.count("ON DELETE CASCADE") >= 1
    assert "ADD COLUMN IF NOT EXISTS finish_reason VARCHAR(64)" in migration
    assert "ALTER TABLE chat_shares OWNER TO pwc_staging_owner" in migration
    assert "ALTER TABLE chat_shares OWNER TO paperswithcode_user" in migration
    assert "DROP TABLE IF EXISTS chat_share_messages" in migration
    assert (
        "EXECUTE\n            "
        "'SELECT EXISTS (SELECT 1 FROM chat_share_messages LIMIT 1)'" in migration
    )
    assert "AND EXISTS (SELECT FROM chat_share_messages LIMIT 1)" not in migration
    assert "TO pwc_staging;" in migration
    assert "TO paperswithcode_user;" in migration
    assert "FROM paperswithcode_user;" in migration


def test_staging_role_defaults_to_read_only_outside_application_pool():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/consolidate_staging_schema.sql"
    ).read_text()
    connection = (repository / "backend/database/connection.py").read_text()
    audit = (repository / "deploy/audit_staging_db.py").read_text()

    assert "ALTER ROLE pwc_staging SET default_transaction_read_only = on" in migration
    assert "ALTER ROLE pwc_staging RESET default_transaction_read_only" not in migration
    assert 'options += " -c default_transaction_read_only=off"' in connection
    assert 'read_only_default != "on"' in audit


def test_chat_edit_preparation_migration_is_environment_scoped_and_typed():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/add_chat_edit_preparation_state.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "prepared_fork_sdk_session_id UUID" in migration
    assert "prepared_fork_sdk_project_key TEXT" in migration
    assert "chat_messages_prepared_fork_pair_check" in migration


def test_common_chat_migrations_support_isolated_production_schema():
    repository = Path(__file__).resolve().parents[3]
    migrations = (
        "add_chat_sessions.sql",
        "add_chat_sandbox_runtime.sql",
        "add_chat_turn_latency.sql",
        "add_chat_sandbox_pool.sql",
        "add_chat_active_cost.sql",
        "add_chat_user_billing.sql",
        "add_chat_qualification_metadata.sql",
        "repair_chat_qualification_evidence_contract.sql",
        "add_chat_sandbox_spend_cap.sql",
        "add_chat_shares.sql",
        "add_chat_edit_preparation_state.sql",
        "add_chat_paper_mentions.sql",
        "add_chat_primary_paper.sql",
        "add_chat_title_budget.sql",
        "add_chat_sandbox_egress_policy.sql",
        "add_chat_warm_assignment_race.sql",
    )

    for name in migrations:
        migration = (repository / "backend/database/migrations" / name).read_text()
        assert "current_schema() NOT IN ('staging', 'public')" in migration

    sessions = (
        repository / "backend/database/migrations/add_chat_sessions.sql"
    ).read_text()
    assert "ALTER TABLE chat_sessions OWNER TO pwc_staging_owner" in sessions
    assert "ALTER TABLE chat_sessions OWNER TO paperswithcode_user" in sessions
    assert "FROM paperswithcode_user" in sessions
    assert "FROM pwc_staging" in sessions

    billing = (
        repository / "backend/database/migrations/add_chat_user_billing.sql"
    ).read_text()
    assert "provider_mode VARCHAR(32)" in billing
    assert "provider_credential_revision UUID" in billing
    assert "provider_error_code VARCHAR(64)" in billing


def test_chat_archiving_migration_is_additive_and_idempotent():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/add_chat_session_archiving.sql"
    ).read_text()

    assert "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ" in migration
    assert "WHERE archived_at IS NULL" in migration
    assert "DROP " not in migration


def test_chat_sandbox_egress_policy_migration_is_environment_scoped_and_idempotent():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/add_chat_sandbox_egress_policy.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "egress_policy_digest VARCHAR(64) NOT NULL" in migration
    assert "ADD COLUMN IF NOT EXISTS egress_policy_digest" in migration
    assert "DROP " not in migration
    assert (
        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945" in migration
    )


def test_chat_title_budget_migration_is_environment_isolated_and_idempotent():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/add_chat_title_budget.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_title_budget_states" in migration
    assert "UNIQUE (environment, billing_cycle)" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_title_provider_calls" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_title_budget_events" in migration
    assert (
        "ALTER TABLE chat_title_budget_states OWNER TO pwc_staging_owner" in migration
    )
    assert (
        "ALTER TABLE chat_title_budget_states OWNER TO paperswithcode_user" in migration
    )
    assert "FROM paperswithcode_user" in migration
    assert "FROM pwc_staging" in migration


def test_production_openrouter_migration_is_role_isolated_and_idempotent():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository
        / "backend/database/migrations/add_chat_openrouter_user_budget_production.sql"
    ).read_text()

    assert "SET LOCAL search_path = public" in migration
    assert "current_schema() <> 'public'" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_openrouter_credentials" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_openrouter_monthly_usage" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_openrouter_provider_calls" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_openrouter_credential_audit" in migration
    assert "OWNER TO paperswithcode_user" in migration
    assert "TO paperswithcode_user" in migration
    assert "FROM pwc_staging" in migration


def test_production_direct_openai_migration_is_role_isolated_and_idempotent():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/add_chat_direct_openai_production.sql"
    ).read_text()

    assert "SET LOCAL search_path = public" in migration
    assert "current_schema() <> 'public'" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_openai_monthly_usage" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_openai_provider_calls" in migration
    assert "'openai_funded'" in migration
    assert "OWNER TO paperswithcode_user" in migration
    assert "TO paperswithcode_user" in migration
    assert "FROM pwc_staging" in migration


def test_production_web_search_migration_is_role_isolated_and_idempotent():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/add_chat_web_search_production.sql"
    ).read_text()

    assert "SET LOCAL search_path = public" in migration
    assert "current_schema() <> 'public'" in migration
    assert "ADD COLUMN IF NOT EXISTS web_search_enabled" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_web_search_budget_states" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_web_search_circuit_events" in migration
    assert "CREATE TABLE IF NOT EXISTS chat_web_search_owner_usage" in migration
    assert "OWNER TO paperswithcode_user" in migration
    assert "TO paperswithcode_user" in migration
    assert "FROM pwc_staging" in migration


def test_production_hf_catalog_migration_is_role_isolated_and_idempotent():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/add_chat_hf_catalog_production.sql"
    ).read_text()

    assert "SET LOCAL search_path = public" in migration
    assert "current_schema() <> 'public'" in migration
    assert "ADD COLUMN IF NOT EXISTS hf_catalog_calls" in migration
    assert "ADD COLUMN IF NOT EXISTS hf_recursive_list_calls" in migration
    assert "TO paperswithcode_user" in migration
    assert "FROM pwc_staging" in migration


def test_warm_assignment_migration_is_guarded_additive_and_role_isolated():
    repository = Path(__file__).resolve().parents[3]
    migration = (
        repository / "backend/database/migrations/add_chat_warm_assignment_race.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "ADD COLUMN IF NOT EXISTS health_check_token_hash" in migration
    assert "ADD COLUMN IF NOT EXISTS health_check_started_at" in migration
    assert "ADD COLUMN IF NOT EXISTS failure_stage" in migration
    assert "chat_sandbox_pool_health_check_pair_check" in migration
    assert (
        "CREATE INDEX IF NOT EXISTS idx_chat_sandbox_pool_available_health" in migration
    )
    assert "OWNER TO pwc_staging_owner" in migration
    assert "OWNER TO paperswithcode_user" in migration
    assert "REVOKE ALL ON chat_sandbox_pool FROM paperswithcode_user" in migration
    assert "REVOKE ALL ON chat_sandbox_pool FROM pwc_staging" in migration


def test_medium_reasoning_effort_migrations_widen_every_chat_check():
    repository = Path(__file__).resolve().parents[3]
    migrations = repository / "backend/database/migrations"
    for name, schema in (
        ("add_chat_medium_reasoning_effort.sql", "staging"),
        ("add_chat_medium_reasoning_effort_production.sql", "public"),
    ):
        migration = (migrations / name).read_text()

        assert f"current_schema() <> '{schema}'" in migration
        for table in (
            "chat_sessions",
            "chat_messages",
            "chat_turn_capabilities",
            "chat_openrouter_provider_calls",
            "chat_openai_provider_calls",
        ):
            assert f"DROP CONSTRAINT IF EXISTS {table}_reasoning_effort_check" in (
                migration
            )
            assert f"VALIDATE CONSTRAINT {table}_reasoning_effort_check" in migration
        assert migration.count("('low','medium','high','max')") == 5
