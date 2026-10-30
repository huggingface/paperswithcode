import importlib.util
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from backend.utils.hf_utils import HfArtifactDiscoveryError


SCRIPT_PATH = (
    Path(__file__).parents[2]
    / ".github/workflows/scripts/hourly/update_hf_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location("update_hf_artifacts", SCRIPT_PATH)
assert SPEC and SPEC.loader
UPDATE_HF_ARTIFACTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATE_HF_ARTIFACTS)


def _paper():
    return SimpleNamespace(
        id=7,
        source="arxiv",
        arxiv_id="2606.23050",
        hf_models=[],
        hf_datasets=[],
        hf_spaces=[],
    )


def test_backfill_query_is_limited_to_unscanned_trend_population():
    session = Mock()
    session.execute.return_value.fetchall.return_value = []

    UPDATE_HF_ARTIFACTS.get_papers_needing_backfill(session, 123)

    query, params = session.execute.call_args.args
    sql = str(query)
    assert "hf_artifacts_scanned_at IS NULL" in sql
    assert "is_latest_version = TRUE" in sql
    assert "source = 'arxiv'" in sql
    assert "COALESCE(date_published, created_at::date) >= :start_date" in sql
    assert params == {"batch_size": 123, "start_date": date(2021, 1, 1)}


def test_explicit_backfill_query_includes_all_publication_dates():
    session = Mock()
    session.execute.return_value.fetchall.return_value = []

    UPDATE_HF_ARTIFACTS.get_papers_with_explicit_artifacts(session, 321)

    query, params = session.execute.call_args.args
    sql = str(query)
    assert "is_latest_version = TRUE" in sql
    assert "cardinality(hf_models)" in sql
    assert "date_published" not in sql
    assert params == {"batch_size": 321}


def test_explicit_backfill_syncs_without_hub_discovery(monkeypatch):
    session = Mock()
    paper = SimpleNamespace(
        id=104054,
        hf_models=["https://huggingface.co/moonshotai/Kimi-K3"],
        hf_datasets=[],
        hf_spaces=[],
    )
    monkeypatch.setattr(
        UPDATE_HF_ARTIFACTS,
        "get_papers_with_explicit_artifacts",
        Mock(return_value=[paper]),
    )
    sync = Mock(return_value={"artifacts": 1, "links_added": 1})
    monkeypatch.setattr(
        UPDATE_HF_ARTIFACTS,
        "sync_explicit_hf_artifact_links",
        sync,
    )

    result = UPDATE_HF_ARTIFACTS.run_explicit_backfill_phase(session, 50)

    assert result == {
        "papers_selected": 1,
        "papers_processed": 1,
        "papers_failed": 0,
        "links_created": 1,
    }
    sync.assert_called_once_with(
        session,
        104054,
        paper.hf_models,
        paper.hf_datasets,
        paper.hf_spaces,
    )
    session.commit.assert_called_once_with()


def test_failed_hub_lookup_is_not_checkpointed(monkeypatch):
    session = Mock()
    monkeypatch.setattr(
        UPDATE_HF_ARTIFACTS,
        "get_papers_needing_backfill",
        Mock(return_value=[_paper()]),
    )
    monkeypatch.setattr(
        UPDATE_HF_ARTIFACTS,
        "collect_paper_artifacts",
        Mock(side_effect=HfArtifactDiscoveryError("rate limited")),
    )
    monkeypatch.setattr(UPDATE_HF_ARTIFACTS, "check_memory_usage", lambda: 1000)
    monkeypatch.setattr(UPDATE_HF_ARTIFACTS.time, "sleep", Mock())

    result = UPDATE_HF_ARTIFACTS.run_discovery_phase(
        session,
        "token",
        date(2026, 1, 1),
        UPDATE_HF_ARTIFACTS.time.time(),
        backfill=True,
    )

    assert result["papers_processed"] == 0
    assert result["papers_failed"] == 1
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    session.execute.assert_not_called()


def test_successful_empty_lookup_is_checkpointed(monkeypatch):
    session = Mock()
    monkeypatch.setattr(
        UPDATE_HF_ARTIFACTS,
        "get_papers_needing_backfill",
        Mock(return_value=[_paper()]),
    )
    monkeypatch.setattr(
        UPDATE_HF_ARTIFACTS,
        "collect_paper_artifacts",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(UPDATE_HF_ARTIFACTS, "check_memory_usage", lambda: 1000)
    monkeypatch.setattr(UPDATE_HF_ARTIFACTS.time, "sleep", Mock())

    result = UPDATE_HF_ARTIFACTS.run_discovery_phase(
        session,
        "token",
        date(2026, 1, 1),
        UPDATE_HF_ARTIFACTS.time.time(),
        backfill=True,
    )

    executed_sql = [str(call.args[0]) for call in session.execute.call_args_list]
    assert result["papers_processed"] == 1
    assert result["papers_failed"] == 0
    assert any("SET hf_artifacts_scanned_at = NOW()" in sql for sql in executed_sql)
    session.commit.assert_called_once()
