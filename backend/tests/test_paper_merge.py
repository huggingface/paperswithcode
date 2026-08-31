from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.database import paper_merge
from backend.database.paper_merge import (
    _merge_hf_artifacts,
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


def test_merge_hf_artifacts_preserves_arrays_and_normalized_links(monkeypatch):
    arxiv_paper = SimpleNamespace(
        id=20,
        hf_models=["https://huggingface.co/org/existing"],
        hf_datasets=None,
        hf_spaces=None,
        hf_artifacts_scanned_at="stale",
    )
    external = SimpleNamespace(
        id=10,
        hf_models=[
            "https://huggingface.co/org/existing",
            "https://huggingface.co/moonshotai/Kimi-K3",
        ],
        hf_datasets=["https://huggingface.co/datasets/org/data"],
        hf_spaces=["https://huggingface.co/spaces/org/demo"],
    )
    target_link = SimpleNamespace(paper_id=20, hf_artifact_id=1)
    duplicate_link = SimpleNamespace(paper_id=10, hf_artifact_id=1)
    moved_link = SimpleNamespace(paper_id=10, hf_artifact_id=2)
    query = Mock()
    query.filter.return_value.all.side_effect = [
        [target_link],
        [duplicate_link, moved_link],
    ]
    db = Mock()
    db.query.return_value = query
    sync = Mock(return_value={"artifacts": 4, "links_added": 1})
    monkeypatch.setattr(paper_merge, "sync_explicit_hf_artifact_links", sync)
    stats = {
        "hf_artifacts_merged": 0,
        "hf_artifacts_moved": 0,
        "hf_artifact_links_created": 0,
    }

    _merge_hf_artifacts(db, external, arxiv_paper, stats)

    assert arxiv_paper.hf_models == [
        "https://huggingface.co/org/existing",
        "https://huggingface.co/moonshotai/Kimi-K3",
    ]
    assert arxiv_paper.hf_datasets == ["https://huggingface.co/datasets/org/data"]
    assert arxiv_paper.hf_spaces == ["https://huggingface.co/spaces/org/demo"]
    assert arxiv_paper.hf_artifacts_scanned_at is None
    assert moved_link.paper_id == 10
    transfer_sql = str(db.execute.call_args_list[0].args[0])
    assert "ON CONFLICT (paper_id, hf_artifact_id) DO NOTHING" in transfer_sql
    sync.assert_called_once_with(
        db,
        20,
        arxiv_paper.hf_models,
        arxiv_paper.hf_datasets,
        arxiv_paper.hf_spaces,
    )
    assert stats == {
        "hf_artifacts_merged": 1,
        "hf_artifacts_moved": 1,
        "hf_artifact_links_created": 1,
    }


def test_merge_method_links_moves_evidence_before_collapsing_duplicate_parent():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(
            text(
                "CREATE TABLE paper_methods ("
                "paper_id INTEGER NOT NULL, method_id INTEGER NOT NULL, "
                "PRIMARY KEY (paper_id, method_id))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE paper_method_evidence ("
                "paper_id INTEGER NOT NULL, method_id INTEGER NOT NULL, "
                "evidence_type VARCHAR(24) NOT NULL, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "details JSON, PRIMARY KEY (paper_id, method_id, evidence_type), "
                "FOREIGN KEY (paper_id, method_id) "
                "REFERENCES paper_methods(paper_id, method_id) ON DELETE CASCADE)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO paper_methods (paper_id, method_id) "
                "VALUES (10, 1), (10, 2), (20, 2)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO paper_method_evidence "
                "(paper_id, method_id, evidence_type, details) VALUES "
                "(10, 1, 'keyword', '{\"source\":\"external\"}'), "
                "(10, 2, 'keyword', '{\"source\":\"external\"}'), "
                "(10, 2, 'reference', '{\"source\":\"external\"}'), "
                "(20, 2, 'keyword', '{\"source\":\"canonical\"}')"
            )
        )

    stats = {
        "methods_merged": 0,
        "methods_moved": 0,
        "method_evidence_merged": 0,
        "method_evidence_moved": 0,
    }
    with Session(engine) as db:
        paper_merge._merge_method_links(db, 10, 20, stats)
        db.flush()
        parents = db.execute(
            text("SELECT paper_id, method_id FROM paper_methods ORDER BY 1, 2")
        ).all()
        evidence = db.execute(
            text(
                "SELECT paper_id, method_id, evidence_type, details "
                "FROM paper_method_evidence ORDER BY 1, 2, 3"
            )
        ).all()

    assert parents == [(20, 1), (20, 2)]
    assert [(row[0], row[1], row[2]) for row in evidence] == [
        (20, 1, "keyword"),
        (20, 2, "keyword"),
        (20, 2, "reference"),
    ]
    assert '"canonical"' in evidence[1][3]
    assert stats == {
        "methods_merged": 1,
        "methods_moved": 1,
        "method_evidence_merged": 1,
        "method_evidence_moved": 2,
    }
