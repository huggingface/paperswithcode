import importlib.util
from pathlib import Path


APP = Path(__file__).parents[1] / "app.py"


def load_app(monkeypatch, tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        '{"schema_version": 1, "generated_at": "now", "daily": [], "papers": [], "evaluations": [], "benchmark_gaps": []}'
    )
    monkeypatch.setenv("SNAPSHOT_PATH", str(snapshot))
    spec = importlib.util.spec_from_file_location("enrichment_dashboard_app", APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_filters_search_papers(monkeypatch, tmp_path):
    app = load_app(monkeypatch, tmp_path)
    snapshot = {
        "papers": [
            {
                "day": "2026-08-25",
                "paper_id": 7,
                "title": "A Paper",
                "status": "completed",
                "mutation_status": "applied",
                "error": None,
            }
        ],
    }
    assert len(app.filter_enrichment(snapshot, "2026-08-25", "paper")) == 1
    assert len(app.filter_enrichment(snapshot, "2026-08-25", "missing")) == 0
