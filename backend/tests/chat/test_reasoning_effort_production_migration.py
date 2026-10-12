from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "database"
    / "migrations"
    / "add_chat_reasoning_effort_production.sql"
)


def test_production_reasoning_effort_migration_is_provider_complete_and_isolated():
    sql = MIGRATION.read_text()

    assert "SET LOCAL search_path = public" in sql
    assert "chat_sessions" in sql
    assert "chat_messages" in sql
    assert "chat_turn_capabilities" in sql
    assert "chat_openrouter_provider_calls" in sql
    assert "chat_openrouter_provider_calls_reasoning_effort_check" in sql
    assert "OWNER TO paperswithcode_user" in sql
    assert "FROM pwc_staging" in sql
