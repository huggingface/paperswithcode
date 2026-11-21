import re
from pathlib import Path

from backend.database.migrations.backfill_paper_search_vector import SEARCH_VECTOR

TRIGGER_SQL = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "migrations"
    / "add_paper_search_vector.sql"
)


def _normalize(expression: str) -> str:
    return " ".join(expression.split())


def test_backfill_expression_matches_trigger_function():
    sql = re.sub(r"--[^\n]*", "", TRIGGER_SQL.read_text())
    match = re.search(r"NEW\.search_vector\s*:=(.*?);", sql, re.DOTALL)
    assert match is not None
    trigger_expression = match.group(1).replace("NEW.", "p.")

    assert _normalize(SEARCH_VECTOR) == _normalize(trigger_expression)
