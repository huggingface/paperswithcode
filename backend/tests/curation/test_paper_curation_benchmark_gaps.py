"""Benchmark gap validation, identity, persistence, and promotion."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace


from backend.config import get_settings
from backend.models.database import (
    BenchmarkCurationCandidate,
    BenchmarkCurationEvidence,
    Dataset,
    Metric,
    Paper,
    Task,
    TaskDataset,
)
from backend.services.benchmark_gap_service import (
    BenchmarkGapService,
    benchmark_candidate_identity_key,
)


def test_benchmark_gap_validation_isolates_malformed_entries():
    class Database:
        def get(self, _model, task_id):
            return SimpleNamespace(id=task_id)

    valid = {
        "reasoning": "A reusable public benchmark blocks a paper-native result.",
        "local_ref": "gap-1",
        "gap_type": "dataset_missing",
        "proposed_benchmark": {
            "name": "ExampleBench",
            "aliases": ["Example Bench"],
            "description": "A reusable public benchmark.",
            "task_candidates": [
                {
                    "task_id": 19,
                    "task_name": "Example Task",
                    "confidence": "high",
                    "reason": "The paper evaluates this task.",
                }
            ],
            "canonical_sources": [
                {
                    "kind": "homepage",
                    "url": "https://example.org/benchmark",
                    "title": "ExampleBench",
                }
            ],
        },
        "protocol": {
            "dataset_version": "v1",
            "splits": ["test"],
            "evaluation_protocol": "Evaluate on the public test split.",
            "metrics": [
                {
                    "name": "Accuracy",
                    "direction": "higher_is_better",
                    "unit": "percent",
                    "native_scale": "0-100",
                    "definition": "Exact-match accuracy.",
                }
            ],
            "supports_harness": False,
        },
        "blocked_evaluations": [
            {
                "local_ref": "blocked-1",
                "model_name": "Introduced Model",
                "harness": None,
                "split": "test",
                "metrics": {"Accuracy": 87.4},
                "best_metric": "Accuracy",
                "methodology": "Official test split.",
                "uses_additional_data": False,
                "is_open": True,
                "num_parameters": 7_000_000_000,
                "hf_model_url": "https://huggingface.co/example/model",
                "evidence_ids": ["e1"],
            }
        ],
        "evidence": [
            {
                "evidence_id": "e1",
                "source_kind": "paper_pdf",
                "source_url": "https://arxiv.org/pdf/2608.00042",
                "page": 7,
                "section": "4.2",
                "table": "Table 3",
                "snippet": "ExampleBench test results.",
                "supports": ["blocked-1"],
            }
        ],
        "catalog_search": {
            "queries": ["ExampleBench"],
            "near_matches": [],
            "conclusion": "No configured benchmark matches.",
        },
        "assessment": {
            "recommendation": "add_candidate",
            "confidence": "high",
            "why_worth_adding": "The protocol is public and reusable.",
            "ambiguities": [],
        },
    }

    accepted, rejected = BenchmarkGapService(Database()).validate(
        [valid, {"gap_type": "dataset_missing"}]
    )

    assert len(accepted) == 1
    assert accepted[0]["_normalized"]["task_ids"] == [19]
    assert rejected == [{"index": 1, "error": "reasoning is required"}]

    html_evidence = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "paper_markdown",
                "source_url": "https://arxiv.org/html/2608.00042",
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [html_evidence],
        paper=SimpleNamespace(
            source_url="https://arxiv.org/abs/2608.00042",
            arxiv_id="2608.00042",
        ),
    )

    assert len(accepted) == 1
    assert rejected == []

    queried_source = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "paper_source",
                "source_url": "https://example.com/report?id=1",
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [queried_source],
        paper=SimpleNamespace(
            source_url="https://example.com/report?id=1",
            arxiv_id=None,
        ),
    )

    assert len(accepted) == 1
    assert rejected == []

    eprint_evidence = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "paper_source",
                "source_url": "https://export.arxiv.org/e-print/2608.00042",
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [eprint_evidence],
        paper=SimpleNamespace(
            source_url="https://arxiv.org/abs/2608.00042",
            arxiv_id="2608.00042",
        ),
    )

    assert rejected == []
    assert accepted[0]["evidence"][0]["source_url"] == (
        "https://arxiv.org/html/2608.00042"
    )

    repository_evidence = {
        **valid,
        "evidence": [
            {
                **valid["evidence"][0],
                "source_kind": "github_readme",
                "source_url": (
                    "https://raw.githubusercontent.com/example/model/main/README.md"
                ),
                "supports": ["ExampleBench results in Table 3"],
            }
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [repository_evidence],
        paper=SimpleNamespace(
            source_url="https://example.com/release",
            arxiv_id=None,
        ),
        source_documents=[
            {"kind": "github_readme", "url": "https://github.com/example/model"}
        ],
    )

    assert len(accepted) == 1
    assert rejected == []

    mismatched_kind = {
        **repository_evidence,
        "evidence": [
            {**repository_evidence["evidence"][0], "source_kind": "paper_pdf"}
        ],
    }
    accepted, rejected = BenchmarkGapService(Database()).validate(
        [mismatched_kind],
        paper=SimpleNamespace(
            source_url="https://example.com/release",
            arxiv_id=None,
        ),
        source_documents=[
            {"kind": "github_readme", "url": "https://github.com/example/model"}
        ],
    )

    assert accepted == []
    assert rejected == [
        {"index": 0, "error": "evidence source kind does not match scoped source"}
    ]


def test_benchmark_gap_rejects_server_owned_fields():
    class Database:
        def get(self, _model, task_id):
            return SimpleNamespace(id=task_id)

    invalid = {
        "reasoning": "A gap.",
        "candidate_id": "agent-invented",
        "gap_type": "dataset_missing",
    }

    accepted, rejected = BenchmarkGapService(Database()).validate([invalid])

    assert accepted == []
    assert rejected == [
        {"index": 0, "error": "agent proposal contains server-owned fields"}
    ]


def test_benchmark_candidate_identity_uses_benchmark_name_not_evidence_url():
    osworld = {
        "gap_type": "dataset_missing",
        "_normalized": {
            "name": "OSWorld 2.0 (0808 offline)",
            "canonical_url": "https://arxiv.org/abs/2609.15364",
        },
    }
    agents_last_exam = {
        "gap_type": "dataset_missing",
        "_normalized": {
            "name": "Agents' Last Exam (Near-term)",
            "canonical_url": "https://arxiv.org/abs/2609.15364",
        },
    }
    gamecraft_from_another_paper = {
        "gap_type": "dataset_missing",
        "_normalized": {
            "name": "GameCraft Bench",
            "canonical_url": "https://arxiv.org/abs/2609.01481",
        },
    }
    gamecraft_from_result_paper = {
        "gap_type": "dataset_missing",
        "_normalized": {
            "name": "GameCraft-Bench",
            "canonical_url": "https://arxiv.org/abs/2609.15364",
        },
    }

    assert benchmark_candidate_identity_key(osworld) != (
        benchmark_candidate_identity_key(agents_last_exam)
    )
    assert benchmark_candidate_identity_key(gamecraft_from_another_paper) == (
        benchmark_candidate_identity_key(gamecraft_from_result_paper)
    )


def test_benchmark_gap_persist_upgrades_matching_legacy_identity():
    legacy = SimpleNamespace(
        id=uuid.uuid4(),
        identity_key="legacy-url-hash",
        gap_type="dataset_missing",
        canonical_name="GameCraft-Bench",
        last_seen_at=None,
        distinct_paper_count=0,
    )

    class Query:
        def __init__(self, result):
            self.result = result

        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def with_for_update(self):
            return self

        def one_or_none(self):
            return self.result

        def first(self):
            return self.result

        def scalar(self):
            return self.result

    class Database:
        def __init__(self):
            self.query_count = 0
            self.added = []

        def query(self, _model):
            self.query_count += 1
            return Query({1: None, 2: legacy, 3: None, 4: 1}[self.query_count])

        def add(self, value):
            self.added.append(value)

        def flush(self):
            pass

    gap = {
        "gap_type": "dataset_missing",
        "reasoning": "The exact protocol is absent.",
        "_normalized": {
            "name": "GameCraft Bench",
            "canonical_url": "https://arxiv.org/abs/2609.15364",
            "task_ids": [15],
            "aliases": [],
        },
    }
    expected_key = benchmark_candidate_identity_key(gap)
    database = Database()

    result = BenchmarkGapService(database).persist(
        paper_id=114228,
        job_id=uuid.uuid4(),
        gaps=[gap],
    )

    assert legacy.identity_key == expected_key
    assert result == [{"candidate_id": str(legacy.id), "identity_key": expected_key}]
    assert len(database.added) == 1
    assert isinstance(database.added[0], BenchmarkCurationEvidence)


def test_benchmark_gap_persist_locks_candidates_in_identity_order():
    class Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def with_for_update(self):
            return self

        def one_or_none(self):
            return None

        def first(self):
            return None

        def scalar(self):
            return 1

    class Database:
        def __init__(self):
            self.added = []

        def query(self, _model):
            return Query()

        def add(self, value):
            self.added.append(value)

        def flush(self):
            pass

    def gap(name):
        return {
            "gap_type": "dataset_missing",
            "reasoning": "The exact protocol is absent.",
            "_normalized": {
                "name": name,
                "canonical_url": None,
                "task_ids": [15],
                "aliases": [],
            },
        }

    gaps = [gap("OSWorld 0808"), gap("GameCraft-Bench"), gap("ALE Near-term")]
    expected_keys = [benchmark_candidate_identity_key(item) for item in gaps]
    database = Database()

    result = BenchmarkGapService(database).persist(
        paper_id=114228, job_id=uuid.uuid4(), gaps=gaps
    )

    locked_keys = [
        row.identity_key
        for row in database.added
        if not isinstance(row, BenchmarkCurationEvidence)
    ]
    assert locked_keys == sorted(expected_keys)
    assert [item["identity_key"] for item in result] == expected_keys


def test_reviewed_benchmark_promotion_requeues_only_evidence_papers():
    candidate_id = uuid.uuid4()
    candidate = SimpleNamespace(
        id=candidate_id,
        task_ids=[19],
        status="candidate",
        promoted_at=None,
    )
    evidence = SimpleNamespace(
        candidate_id=candidate_id,
        paper_id=42,
        created_at=datetime(2026, 8, 18, tzinfo=UTC),
        payload={"protocol": {"metrics": [{"name": "Accuracy"}]}},
    )
    paper = SimpleNamespace(
        id=42,
        source="arxiv",
        arxiv_id="2608.00042",
        title="Evidence paper",
    )

    class Query:
        def __init__(self, model):
            self.model = model

        def join(self, *_args):
            return self

        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def one_or_none(self):
            if self.model is Metric:
                return SimpleNamespace(id=7, name="Accuracy")
            return None

        def all(self):
            return [evidence] if self.model is BenchmarkCurationEvidence else []

        def first(self):
            return None

    class Database:
        def __init__(self):
            self.commits = 0

        def get(self, model, key):
            values = {
                (BenchmarkCurationCandidate, candidate_id): candidate,
                (Dataset, 8): SimpleNamespace(id=8),
                (Task, 19): SimpleNamespace(id=19),
                (TaskDataset, (19, 8)): SimpleNamespace(task_id=19, dataset_id=8),
                (Paper, 42): paper,
            }
            return values.get((model, key))

        def query(self, model):
            return Query(model)

        def commit(self):
            self.commits += 1

    class Jobs:
        def __init__(self):
            self.enqueued = []
            self.dispatched = False

        def enqueue(self, db, **values):
            self.enqueued.append((db, values))
            return SimpleNamespace(id=uuid.uuid4())

        def dispatch_next(self, *_args):
            self.dispatched = True

    database = Database()
    jobs = Jobs()
    result = BenchmarkGapService(database).promote_and_enqueue(
        candidate_id=candidate_id,
        dataset_id=8,
        task_id=19,
        best_metric="Accuracy",
        settings=get_settings(),
        job_service=jobs,
    )

    assert result["skipped_active_paper_ids"] == []
    assert len(result["enqueued_job_ids"]) == 1
    assert jobs.enqueued[0][1] | {"settings": None} == {
        "kind": "add-evals",
        "paper_id": 42,
        "paper_route": "2608.00042",
        "paper_title": "Evidence paper",
        "requested_by": f"benchmark-promotion:{candidate_id}",
        "trigger": "benchmark-promotion",
        "policy_version": f"benchmark-promotion-{str(candidate_id)[:12]}",
        "priority": 50,
        "dispatch": False,
        "commit": False,
        "settings": None,
    }
    assert candidate.status == "promoted"
    assert candidate.promoted_at is not None
    assert jobs.dispatched is True
