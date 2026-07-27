from pathlib import Path
from types import SimpleNamespace

from backend.database.paper_merge import (
    lookup_paper_merge_redirect,
    record_paper_merge_redirect,
)


class _Result:
    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row


class _RecordingSession:
    def __init__(self, row=None):
        self.calls = []
        self.row = row

    def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return _Result(self.row)


def test_lookup_paper_merge_redirect_is_read_only_and_schema_qualified():
    db = _RecordingSession(SimpleNamespace(route_identifier="2607.00001"))

    assert lookup_paper_merge_redirect(db, 83017) == "2607.00001"

    assert len(db.calls) == 1
    statement, parameters = db.calls[0]
    assert "SELECT route_identifier" in statement
    assert "FROM public.paper_redirects" in statement
    assert "CREATE TABLE" not in statement
    assert parameters == {"old_paper_id": 83017}


def test_record_paper_merge_redirect_writes_to_shared_catalog_table():
    db = _RecordingSession()
    arxiv_paper = SimpleNamespace(source="arxiv", arxiv_id="2607.00001", id=42)

    record_paper_merge_redirect(db, 83017, arxiv_paper)

    assert len(db.calls) == 1
    statement, parameters = db.calls[0]
    assert "INSERT INTO public.paper_redirects" in statement
    assert "CREATE TABLE" not in statement
    assert parameters == {
        "old_paper_id": 83017,
        "route_identifier": "2607.00001",
    }


def test_paper_redirects_migration_preserves_staging_read_only_boundary():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "add_paper_redirects.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS public.paper_redirects" in migration
    assert "GRANT SELECT ON public.paper_redirects TO pwc_staging" in migration
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON public.paper_redirects TO pwc_staging"
    ) not in " ".join(migration.split())
