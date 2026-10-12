from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "database"
    / "migrations"
    / "add_chat_pi_harness_production.sql"
)


def test_production_pi_migration_is_public_owned_and_staging_isolated():
    sql = MIGRATION.read_text()

    assert "SET LOCAL search_path = public" in sql
    assert "chat_pi_sessions" in sql
    assert "chat_pi_transcript_entries" in sql
    assert "chat_pi_prepared_forks" in sql
    assert "chat_harness_assignment_audit" in sql
    assert "OWNER TO paperswithcode_user" in sql
    assert "FROM pwc_staging" in sql
    assert "pwc_staging_owner" not in sql
    assert "chat_openrouter" not in sql
