import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.services.enrichment_dashboard_export import build_snapshot, write_snapshot


class Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeDB:
    def __init__(
        self, jobs, evaluations, gaps, trending_models=None, trending_decisions=None
    ):
        self.jobs = jobs
        self.evaluations = evaluations
        self.gaps = gaps
        self.trending_models = trending_models or []
        self.trending_decisions = trending_decisions or []

    def execute(self, statement, *_args, **_kwargs):
        query = str(statement)
        if "JOIN trending_model_candidates" in query:
            return Result(self.trending_decisions)
        if "FROM paper_curation_jobs" in query:
            return Result(self.jobs)
        if "FROM evaluations" in query:
            return Result(self.evaluations)
        if "FROM benchmark_curation_candidates" in query:
            return Result(self.gaps)
        if "FROM trending_model_candidates" in query:
            return Result(self.trending_models)
        raise AssertionError(f"Unexpected snapshot query: {query}")


def test_snapshot_groups_jobs_and_deduplicates_gap_paper_pairs(tmp_path):
    timestamp = datetime(2026, 8, 25, 2, tzinfo=timezone.utc)
    jobs = [
        {
            "id": "job-1",
            "paper_id": 1,
            "paper_title": "Paper",
            "kind": "enrich-paper",
            "status": "completed",
            "created_at": timestamp,
            "mutation_result": {"status": "applied"},
            "error": None,
        },
        {
            "id": "job-2",
            "paper_id": 1,
            "paper_title": "Paper",
            "kind": "add-evals",
            "status": "completed",
            "created_at": timestamp,
            "mutation_result": {"evaluations_created": 2},
            "error": None,
        },
    ]
    evaluations = [
        {
            "id": 4,
            "paper_id": 1,
            "paper_title": "Paper",
            "task": "QA",
            "dataset": "Test",
            "model_name": "M",
            "harness": None,
            "best_metric": "Accuracy",
            "metrics": {"Accuracy": 90},
            "source_url": "https://example.test",
            "created_at": timestamp,
        }
    ]
    gap = {
        "identity_key": "gap",
        "canonical_name": "NewBench",
        "gap_type": "dataset_missing",
        "canonical_url": "https://example.test/bench",
        "review_status": "candidate",
        "distinct_paper_count": 1,
        "paper_id": 1,
        "paper_title": "Paper",
        "created_at": timestamp,
    }
    snapshot = build_snapshot(
        FakeDB(jobs, evaluations, [gap, gap]), date(2026, 8, 25), date(2026, 8, 25)
    )
    assert snapshot["daily"] == [
        {
            "day": "2026-08-25",
            "enrichment_jobs": 1,
            "enrichment_applied": 1,
            "enrichment_noops": 0,
            "enrichment_failed": 0,
            "evaluation_jobs": 1,
            "evaluations_created": 2,
            "benchmark_gap_reports": 1,
        }
    ]
    assert len(snapshot["benchmark_gaps"]) == 1
    assert snapshot["trending_models"] == []
    assert snapshot["trending_model_decisions"] == []


def test_write_snapshot_creates_json(tmp_path):
    path = tmp_path / "snapshot.json"
    write_snapshot({"schema_version": 1, "generated_at": "now"}, path)
    assert path.exists()


def test_snapshot_serializes_trending_decision_job_uuid(tmp_path):
    timestamp = datetime(2026, 8, 26, 15, tzinfo=timezone.utc)
    job_id = uuid.uuid4()
    snapshot = build_snapshot(
        FakeDB(
            [],
            [],
            [],
            trending_decisions=[
                {
                    "repo_id": "org/model",
                    "job_id": job_id,
                    "created_at": timestamp,
                }
            ],
        ),
        date(2026, 8, 26),
        date(2026, 8, 26),
    )
    path = tmp_path / "snapshot.json"

    write_snapshot(snapshot, path)

    assert str(job_id) in path.read_text()


def test_snapshot_handles_in_progress_enrichment_without_mutation_result():
    timestamp = datetime(2026, 8, 26, 15, tzinfo=timezone.utc)
    snapshot = build_snapshot(
        FakeDB(
            [
                {
                    "id": uuid.uuid4(),
                    "paper_id": 1,
                    "paper_title": "Paper",
                    "kind": "enrich-paper",
                    "status": "running",
                    "trigger": "hf-trending-cron",
                    "created_at": timestamp,
                    "mutation_result": None,
                    "error": None,
                }
            ],
            [],
            [],
        ),
        date(2026, 8, 26),
        date(2026, 8, 26),
    )

    assert snapshot["papers"][0]["mutation_status"] is None


def test_snapshot_serializes_postgres_numeric_values(tmp_path):
    timestamp = datetime(2026, 8, 26, 15, tzinfo=timezone.utc)
    snapshot = build_snapshot(
        FakeDB(
            [],
            [],
            [],
            trending_models=[
                {
                    "repo_id": "org/model",
                    "trending_score": Decimal("123.45"),
                    "first_seen_at": timestamp,
                }
            ],
        ),
        date(2026, 8, 26),
        date(2026, 8, 26),
    )
    path = tmp_path / "snapshot.json"

    write_snapshot(snapshot, path)

    assert '"trending_score": 123.45' in path.read_text()
