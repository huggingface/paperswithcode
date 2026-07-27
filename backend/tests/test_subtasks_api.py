"""
Tests for first-class task hierarchy (subtasks):
  - leaderboards key off the most-specific task (the child / subtask)
  - parent task pages can roll up child benchmarks and evaluations via
    `include_descendants=True`
  - rank recalculation stays scoped per (task_id, dataset_id, best_metric)

These mirror the post-migration shape in production where Language Modeling
benchmarks live under per-capability subtasks (World Knowledge, Math,
Reasoning, Coding, ...).
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import (
    Base,
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Metric as DBMetric,
    Paper as DBPaper,
    Task as DBTask,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.benchmark_trend_service import BenchmarkTrendService
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    """SQLite cannot autoincrement BIGINT; rewrite to INTEGER for tests."""
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


def _seed_lm_with_subtasks(db):
    """Build a minimal Language Modeling parent + two subtasks + benchmarks.

    Layout:
        Language Modeling (id=1)               <-- parent task; no benchmarks
          ├── World Knowledge (id=2)
          │     - MMLU (dataset 1, metric Accuracy, two evaluations)
          │     - GPQA Diamond (dataset 2, metric Accuracy)
          └── Math (id=3)
                - GSM8k (dataset 3, metric Accuracy)
    """
    parent = DBTask(id=1, name="Language Modeling", slug="language-modeling", level=0)
    knowledge = DBTask(
        id=2,
        name="World Knowledge",
        slug="world-knowledge",
        parent_id=1,
        level=1,
    )
    math = DBTask(id=3, name="Math", slug="math", parent_id=1, level=1)
    db.add_all([parent, knowledge, math])

    datasets = [
        DBDataset(id=1, name="MMLU", slug="mmlu"),
        DBDataset(id=2, name="GPQA Diamond", slug="gpqa-diamond"),
        DBDataset(id=3, name="GSM8k", slug="gsm8k"),
    ]
    db.add_all(datasets)

    db.add(DBMetric(id=1, name="Accuracy", direction="higher_is_better"))

    db.add_all(
        [
            TaskDataset(task_id=2, dataset_id=1),
            TaskDataset(task_id=2, dataset_id=2),
            TaskDataset(task_id=3, dataset_id=3),
            TaskDatasetMetric(task_id=2, dataset_id=1, metric_id=1),
            TaskDatasetMetric(task_id=2, dataset_id=2, metric_id=1),
            TaskDatasetMetric(task_id=3, dataset_id=3, metric_id=1),
        ]
    )

    papers = [
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2026.0{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 5)
    ]
    db.add_all(papers)

    db.add_all(
        [
            DBEvaluation(
                id=10,
                paper_id=1,
                task_id=2,
                dataset_id=1,
                model_name="GPT-x",
                metrics={"Accuracy": "85.0"},
                best_metric="Accuracy",
            ),
            DBEvaluation(
                id=11,
                paper_id=2,
                task_id=2,
                dataset_id=1,
                model_name="GPT-y",
                metrics={"Accuracy": "90.0"},
                best_metric="Accuracy",
            ),
            DBEvaluation(
                id=12,
                paper_id=3,
                task_id=2,
                dataset_id=2,
                model_name="GPT-x",
                metrics={"Accuracy": "60.0"},
                best_metric="Accuracy",
            ),
            DBEvaluation(
                id=13,
                paper_id=4,
                task_id=3,
                dataset_id=3,
                model_name="GPT-y",
                metrics={"Accuracy": "95.0"},
                best_metric="Accuracy",
            ),
        ]
    )

    db.commit()


def _seed_benchmark_trends(db, today):
    task = DBTask(id=50, name="OCR", slug="ocr-trends", level=0)
    rising = DBDataset(id=500, name="RisingBench", slug="rising-bench")
    established = DBDataset(id=501, name="EstablishedBench", slug="established-bench")
    db.add_all([task, rising, established])
    db.add_all(
        [
            TaskDataset(task_id=50, dataset_id=500),
            TaskDataset(task_id=50, dataset_id=501, featured_rank=1),
        ]
    )

    papers = []
    evaluations = []
    evaluation_id = 5000
    paper_id = 500

    def add_reports(dataset_id, ages):
        nonlocal evaluation_id, paper_id
        for age in ages:
            papers.append(
                DBPaper(
                    id=paper_id,
                    title=f"Paper {paper_id}",
                    abstract="",
                    arxiv_id=f"2607.{paper_id:05d}",
                    version="v1",
                    is_latest_version=True,
                    date_published=today - timedelta(days=age),
                )
            )
            evaluations.append(
                DBEvaluation(
                    id=evaluation_id,
                    paper_id=paper_id,
                    task_id=50,
                    dataset_id=dataset_id,
                    model_name=f"Model {paper_id}",
                    metrics={"Accuracy": 1},
                    best_metric="Accuracy",
                )
            )
            evaluation_id += 1
            paper_id += 1

    add_reports(500, [2, 8, 15, 22])
    add_reports(501, [3, 45, 120, 145, 170, 200, 230])

    # A second metric row from the same paper must not inflate reporting count.
    evaluations.append(
        DBEvaluation(
            id=evaluation_id,
            paper_id=500,
            task_id=50,
            dataset_id=500,
            model_name="Model 500",
            metrics={"F1": 1},
            best_metric="F1",
        )
    )
    db.add_all(papers)
    db.add_all(evaluations)
    db.commit()


def test_trending_benchmarks_default_to_ninety_days(db_session):
    today = date(2026, 7, 27)
    _seed_benchmark_trends(db_session, today)

    response = BenchmarkTrendService(db_session).get_trending_benchmarks(
        "ocr-trends",
        today=today,
    )

    assert response.recent_days == 90
    assert [item.name for item in response.results] == [
        "RisingBench",
        "EstablishedBench",
    ]
    rising, established = response.results
    assert rising.recent_paper_count == 4
    assert rising.all_time_paper_count == 4
    assert rising.best_model_name == "Model 500"
    assert established.recent_paper_count == 2
    assert established.baseline_paper_count == 5
    assert established.featured_rank == 1


def test_trending_benchmarks_resolve_exact_task_name(db_session):
    today = date(2026, 7, 27)
    _seed_benchmark_trends(db_session, today)

    response = BenchmarkTrendService(db_session).get_trending_benchmarks(
        "OCR",
        today=today,
    )

    assert response.task_slug == "ocr-trends"
    assert response.results[0].name == "RisingBench"


def test_trending_benchmarks_endpoint_exposes_default_window(client):
    today = datetime.now(UTC).date()
    db = TestingSessionLocal()
    try:
        _seed_benchmark_trends(db, today)
    finally:
        db.close()

    response = client.get("/api/v1/tasks/ocr-trends/trending-benchmarks")

    assert response.status_code == 200
    body = response.json()
    assert body["task_slug"] == "ocr-trends"
    assert body["signal"] == "evaluation_reports"
    assert body["recent_days"] == 90
    assert body["baseline_days"] == 180
    assert body["results"][0]["name"] == "RisingBench"
    assert body["results"][0]["best_model_name"] == "Model 500"
    assert len(body["results"][0]["history"]) == 6


def test_create_evaluation_on_child_task_validates_against_child_leaderboard(
    db_session,
):
    """Creating an evaluation against a subtask (child task) must succeed
    when the (child, dataset, metric) triple exists in `task_dataset_metrics`."""
    _seed_lm_with_subtasks(db_session)

    service = EvaluationService(db_session)
    created = service.create_evaluation(
        paper_id=1,
        task_id=2,  # World Knowledge child task
        dataset_id=2,  # GPQA Diamond
        metrics={"Accuracy": "70.0"},
        best_metric="Accuracy",
        model_name="ModelZ",
    )

    assert created.task_id == "2"
    assert created.dataset_id == "2"
    assert created.best_metric == "Accuracy"


def test_create_evaluation_on_parent_task_without_triple_fails(db_session):
    """The parent Language Modeling task no longer owns benchmarks, so
    creating an evaluation pointing at the parent must fail validation."""
    _seed_lm_with_subtasks(db_session)

    service = EvaluationService(db_session)
    with pytest.raises(ValueError, match="No leaderboard defined"):
        service.create_evaluation(
            paper_id=1,
            task_id=1,  # parent Language Modeling
            dataset_id=1,
            metrics={"Accuracy": "70.0"},
            best_metric="Accuracy",
            model_name="ModelZ",
        )


def test_get_datasets_for_parent_without_descendants_returns_nothing(db_session):
    """Parent Language Modeling page must not surface benchmarks unless the
    caller opts into rolling up subtask benchmarks via include_descendants."""
    _seed_lm_with_subtasks(db_session)

    result = DatasetService(db_session).get_datasets(task_id=1)
    assert [d.slug for d in result.results] == []


def test_get_datasets_for_parent_with_include_descendants_rolls_up(db_session):
    """include_descendants=True surfaces benchmarks owned by all subtasks."""
    _seed_lm_with_subtasks(db_session)

    result = DatasetService(db_session).get_datasets(
        task_id=1, include_descendants=True
    )

    assert sorted(d.slug for d in result.results) == [
        "gpqa-diamond",
        "gsm8k",
        "mmlu",
    ]


def test_get_datasets_for_child_task_only_returns_its_benchmarks(db_session):
    """Fetching by the child task id must scope strictly to that subtask."""
    _seed_lm_with_subtasks(db_session)

    result = DatasetService(db_session).get_datasets(task_id=2)
    assert sorted(d.slug for d in result.results) == ["gpqa-diamond", "mmlu"]


def test_task_benchmark_best_model_can_be_scoped_to_open_rows(client):
    """Task-page benchmark cards should match open-only leaderboard views.

    If the absolute rank-1 model is closed-source, an `is_open=true` task-page
    request should display the best open row instead of the hidden model.
    """
    db = TestingSessionLocal()
    _seed_lm_with_subtasks(db)
    db.query(DBEvaluation).filter(DBEvaluation.id == 11).update(
        {"best_rank": 1, "is_open": False}
    )
    db.query(DBEvaluation).filter(DBEvaluation.id == 10).update(
        {"best_rank": 2, "is_open": True}
    )
    db.commit()
    db.close()

    unfiltered = client.get("/api/v1/tasks/2/page").json()
    open_only = client.get("/api/v1/tasks/2/page?is_open=true").json()

    unfiltered_mmlu = next(d for d in unfiltered["benchmarks"] if d["slug"] == "mmlu")
    open_mmlu = next(d for d in open_only["benchmarks"] if d["slug"] == "mmlu")

    assert unfiltered_mmlu["best_model_name"] == "GPT-y"
    assert open_mmlu["best_model_name"] == "GPT-x"


def test_dataset_detail_embeds_task_scoped_leaderboard_summary(client):
    db = TestingSessionLocal()
    _seed_lm_with_subtasks(db)
    db.close()

    response = client.get(
        "/api/v1/datasets/mmlu?include_paper=true&task=world-knowledge"
    )

    assert response.status_code == 200
    summary = response.json()["leaderboard_summary"]
    assert summary == {
        "task_id": "2",
        "task_slug": "world-knowledge",
        "metric": "Accuracy",
        "value": "90.0",
        "model_name": "GPT-y",
        "evaluation_id": "11",
    }
    assert response.headers["cache-control"] == (
        "public, max-age=60, stale-while-revalidate=300"
    )


def test_dataset_detail_summary_respects_open_source_filter(client):
    db = TestingSessionLocal()
    _seed_lm_with_subtasks(db)
    db.query(DBEvaluation).filter(DBEvaluation.id == 11).update({"is_open": False})
    db.commit()
    db.close()

    response = client.get("/api/v1/datasets/mmlu?task=world-knowledge&is_open=true")

    assert response.status_code == 200
    summary = response.json()["leaderboard_summary"]
    assert summary["model_name"] == "GPT-x"
    assert summary["value"] == "85.0"


def test_dataset_detail_summary_respects_lower_is_better_metrics(client):
    db = TestingSessionLocal()
    _seed_lm_with_subtasks(db)
    db.query(DBMetric).filter(DBMetric.name == "Accuracy").update(
        {"direction": "lower_is_better"}
    )
    db.commit()
    db.close()

    response = client.get("/api/v1/datasets/mmlu?task=2")

    assert response.status_code == 200
    summary = response.json()["leaderboard_summary"]
    assert summary["model_name"] == "GPT-x"
    assert summary["value"] == "85.0"


def test_get_evaluations_with_include_descendants_rolls_up_subtask_evals(client):
    """The /evaluations API supports include_descendants for parent tasks."""
    db = TestingSessionLocal()
    _seed_lm_with_subtasks(db)
    db.close()

    parent_only = client.get("/api/v1/evaluations/?task_id=1&page_size=50").json()
    assert parent_only["count"] == 0

    rolled_up = client.get(
        "/api/v1/evaluations/?task_id=1&include_descendants=true&page_size=50"
    ).json()
    assert rolled_up["count"] == 4

    child_only = client.get("/api/v1/evaluations/?task_id=2&page_size=50").json()
    assert child_only["count"] == 3
    assert all(row["task_id"] == "2" for row in child_only["results"])


def test_dataset_evaluations_default_to_best_rank_order(client):
    """Dataset-scoped leaderboard calls should surface the rank-1 row first.

    Benchmark pages sometimes omit an explicit ordering parameter. Those calls
    must not fall back to creation order, where a newly inserted rank-3 row can
    appear above the actual best model.
    """
    db = TestingSessionLocal()
    _seed_lm_with_subtasks(db)
    db.query(DBEvaluation).filter(DBEvaluation.id == 11).update({"best_rank": 1})
    db.query(DBEvaluation).filter(DBEvaluation.id == 10).update({"best_rank": 2})

    # Make insertion/id order adversarial: rank 3 has the largest id and would
    # sort first under the old default `-created_at`/newest-first behavior.
    db.add(
        DBPaper(
            id=20,
            title="Late Paper",
            abstract="Abstract 20",
            arxiv_id="2026.00020",
            version="v1",
            is_latest_version=True,
        )
    )
    db.add(
        DBEvaluation(
            id=20,
            paper_id=20,
            task_id=2,
            dataset_id=1,
            model_name="Late rank-three model",
            metrics={"Accuracy": "87.0"},
            best_metric="Accuracy",
            best_rank=3,
        )
    )
    db.commit()
    db.close()

    response = client.get("/api/v1/evaluations/?dataset_id=1&task_id=2&page_size=50")
    assert response.status_code == 200
    rows = response.json()["results"]

    assert [row["best_rank"] for row in rows] == [1, 2, 3]
    assert rows[0]["model_name"] == "GPT-y"


def test_recalculate_ranks_is_scoped_to_child_task(db_session):
    """Rank recalculation runs per (child_task_id, dataset_id, best_metric)
    so two subtasks sharing nothing don't pollute each other's ordering."""
    _seed_lm_with_subtasks(db_session)
    service = EvaluationService(db_session)

    updated = service.recalculate_ranks(task_id=2, dataset_id=1, metric_name="Accuracy")
    assert updated == 2

    rows = (
        db_session.query(DBEvaluation)
        .filter(DBEvaluation.task_id == 2, DBEvaluation.dataset_id == 1)
        .all()
    )
    by_id = {row.id: row.best_rank for row in rows}
    # Higher Accuracy wins; eval 11 = 90.0 -> rank 1, eval 10 = 85.0 -> rank 2.
    assert by_id == {11: 1, 10: 2}

    # The other subtask leaderboard is untouched until we recalc it.
    other_eval = db_session.query(DBEvaluation).filter(DBEvaluation.id == 13).first()
    assert other_eval.best_rank is None


def test_task_children_endpoint_lists_subtasks_for_parent(client):
    """Frontend /tasks/{id}/children powers the parent task page subtask grid."""
    db = TestingSessionLocal()
    _seed_lm_with_subtasks(db)
    db.close()

    response = client.get("/api/v1/tasks/1/children")
    assert response.status_code == 200
    payload = response.json()
    slugs = sorted(t["slug"] for t in payload["results"])
    assert slugs == ["math", "world-knowledge"]
    assert all(t["parent_id"] == "1" for t in payload["results"])
    assert all(t["level"] == 1 for t in payload["results"])


def _seed_paper_with_three_benchmarks(db):
    """Seed one focal paper plus extra papers that pump benchmark popularity.

    Layout:
        Task 10 owns three benchmarks.
        Dataset 100 (MCP-Atlas)  -> 1 eval from focal paper + 4 from others = 5
        Dataset 200 (BrowseComp) -> 1 eval from focal paper + 1 from another = 2
        Dataset 300 (Niche)      -> 1 eval from focal paper                   = 1

    Focal paper (id=999) has exactly one row on each benchmark, and the rows
    were inserted in the *opposite* of popularity order so a default
    -created_at sort would return Niche, BrowseComp, MCP-Atlas. The
    benchmark_popularity ordering must flip that to MCP-Atlas, BrowseComp,
    Niche regardless of insertion / created_at order.
    """
    task = DBTask(id=10, name="Agents", slug="agents", level=0)
    db.add(task)

    db.add_all(
        [
            DBDataset(id=100, name="MCP-Atlas", slug="mcp-atlas"),
            DBDataset(id=200, name="BrowseComp", slug="browsecomp"),
            DBDataset(id=300, name="Niche", slug="niche"),
        ]
    )
    db.add(DBMetric(id=10, name="Accuracy", direction="higher_is_better"))

    # One TaskDataset entry per (task, dataset) so the dataset listing endpoint
    # surfaces all three benchmarks under task 10. featured_rank is set
    # adversarially: the *least* popular benchmark gets the smallest
    # featured_rank, so pinned ordering (featured_rank first) must surface the
    # least-popular ranked benchmark ahead of the most-popular unranked one.
    db.add_all(
        [
            TaskDataset(task_id=10, dataset_id=100, featured_rank=None),
            TaskDataset(task_id=10, dataset_id=200, featured_rank=2),
            TaskDataset(task_id=10, dataset_id=300, featured_rank=1),
            TaskDatasetMetric(task_id=10, dataset_id=100, metric_id=10),
            TaskDatasetMetric(task_id=10, dataset_id=200, metric_id=10),
            TaskDatasetMetric(task_id=10, dataset_id=300, metric_id=10),
        ]
    )

    papers = [
        DBPaper(
            id=pid,
            title=f"Paper {pid}",
            abstract=f"Abstract {pid}",
            arxiv_id=f"2026.1{pid:04d}",
            version="v1",
            is_latest_version=True,
        )
        for pid in [999, 1001, 1002, 1003, 1004, 1005]
    ]
    db.add_all(papers)

    # Focal paper rows in least-popular-first order so created_at sort
    # would otherwise place Niche first.
    db.add_all(
        [
            DBEvaluation(
                id=500,
                paper_id=999,
                task_id=10,
                dataset_id=300,
                model_name="GLM-5",
                metrics={"Accuracy": "70.0"},
                best_metric="Accuracy",
            ),
            DBEvaluation(
                id=501,
                paper_id=999,
                task_id=10,
                dataset_id=200,
                model_name="GLM-5",
                metrics={"Accuracy": "60.0"},
                best_metric="Accuracy",
            ),
            DBEvaluation(
                id=502,
                paper_id=999,
                task_id=10,
                dataset_id=100,
                model_name="GLM-5",
                metrics={"Accuracy": "80.0"},
                best_metric="Accuracy",
            ),
        ]
    )

    # Extra rows from other papers so MCP-Atlas accumulates 5 evaluations
    # and BrowseComp accumulates 2 evaluations.
    db.add_all(
        [
            DBEvaluation(
                id=600 + i,
                paper_id=1001 + i,
                task_id=10,
                dataset_id=100,
                model_name=f"OtherModel{i}",
                metrics={"Accuracy": str(50 + i)},
                best_metric="Accuracy",
            )
            for i in range(4)
        ]
    )
    db.add(
        DBEvaluation(
            id=610,
            paper_id=1005,
            task_id=10,
            dataset_id=200,
            model_name="OtherBrowse",
            metrics={"Accuracy": "55.0"},
            best_metric="Accuracy",
        )
    )

    db.commit()


def test_paper_evaluations_sorted_by_benchmark_popularity(client):
    """Paper page rows must surface the most-evaluated benchmark first
    regardless of insertion order (which would otherwise dominate via the
    default -created_at sort)."""
    db = TestingSessionLocal()
    _seed_paper_with_three_benchmarks(db)
    db.close()

    response = client.get(
        "/api/v1/evaluations/?paper_id=999&ordering=-benchmark_popularity&page_size=50"
    )
    assert response.status_code == 200
    payload = response.json()

    # Focal paper has exactly three evaluations.
    assert payload["count"] == 3
    dataset_slugs = [row["dataset_slug"] for row in payload["results"]]
    assert dataset_slugs == ["mcp-atlas", "browsecomp", "niche"]


def _seed_paper_with_multiple_rows_per_benchmark(db):
    """Seed a focal paper that has *multiple* evaluations on the same benchmark.

    Layout:
        Task 20 owns two benchmarks.
        Dataset 400 (BenchPop) -> 3 evals from focal paper + 4 from others = 7
        Dataset 500 (BenchTail) -> 1 eval from focal paper                  = 1

    The focal paper's three rows on BenchPop are inserted in *ascending id*
    order with adversarial best_rank values so that an id-only tie-break
    would yield [rank 3, rank 1, rank None] — the wrong order. The
    benchmark_popularity ordering must instead surface the rank-1 row first,
    then rank 3, then the unranked row (nulls last).
    """
    task = DBTask(id=20, name="Bench Tasks", slug="bench-tasks", level=0)
    db.add(task)

    db.add_all(
        [
            DBDataset(id=400, name="BenchPop", slug="benchpop"),
            DBDataset(id=500, name="BenchTail", slug="benchtail"),
        ]
    )
    db.add(DBMetric(id=20, name="Accuracy", direction="higher_is_better"))

    db.add_all(
        [
            TaskDataset(task_id=20, dataset_id=400),
            TaskDataset(task_id=20, dataset_id=500),
            TaskDatasetMetric(task_id=20, dataset_id=400, metric_id=20),
            TaskDatasetMetric(task_id=20, dataset_id=500, metric_id=20),
        ]
    )

    papers = [
        DBPaper(
            id=pid,
            title=f"Paper {pid}",
            abstract=f"Abstract {pid}",
            arxiv_id=f"2026.2{pid:04d}",
            version="v1",
            is_latest_version=True,
        )
        for pid in [2999, 3001, 3002, 3003, 3004]
    ]
    db.add_all(papers)

    # Focal paper rows on BenchPop, inserted with ascending ids but adversarial
    # ranks so id-only tie-breaking would mis-order them.
    db.add_all(
        [
            DBEvaluation(
                id=800,
                paper_id=2999,
                task_id=20,
                dataset_id=400,
                model_name="VariantA",
                metrics={"Accuracy": "70.0"},
                best_metric="Accuracy",
                best_rank=3,
            ),
            DBEvaluation(
                id=801,
                paper_id=2999,
                task_id=20,
                dataset_id=400,
                model_name="VariantB",
                metrics={"Accuracy": "90.0"},
                best_metric="Accuracy",
                best_rank=1,
            ),
            DBEvaluation(
                id=802,
                paper_id=2999,
                task_id=20,
                dataset_id=400,
                model_name="VariantC",
                metrics={"Accuracy": "55.0"},
                best_metric="Accuracy",
                best_rank=None,
            ),
            DBEvaluation(
                id=803,
                paper_id=2999,
                task_id=20,
                dataset_id=500,
                model_name="VariantA",
                metrics={"Accuracy": "60.0"},
                best_metric="Accuracy",
                best_rank=1,
            ),
        ]
    )

    # Extra rows from other papers so BenchPop accumulates 7 total evaluations
    # (the focal paper's 3 + these 4) and BenchTail stays at 1.
    db.add_all(
        [
            DBEvaluation(
                id=900 + i,
                paper_id=3001 + i,
                task_id=20,
                dataset_id=400,
                model_name=f"OtherModel{i}",
                metrics={"Accuracy": str(40 + i)},
                best_metric="Accuracy",
                best_rank=4 + i,
            )
            for i in range(4)
        ]
    )

    db.commit()


def test_paper_evaluations_within_benchmark_sorted_by_best_rank(client):
    """Within each benchmark group, paper page rows must be ordered by
    `best_rank` ascending (with NULL ranks last) so the strongest entry on
    each benchmark surfaces first — mirroring the benchmark leaderboard.

    The popular benchmark must still come before the less popular one."""
    db = TestingSessionLocal()
    _seed_paper_with_multiple_rows_per_benchmark(db)
    db.close()

    response = client.get(
        "/api/v1/evaluations/?paper_id=2999&ordering=-benchmark_popularity&page_size=50"
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["count"] == 4
    rows = payload["results"]

    # Across benchmarks: BenchPop (popularity 7) before BenchTail (popularity 1).
    dataset_slugs = [row["dataset_slug"] for row in rows]
    assert dataset_slugs == ["benchpop", "benchpop", "benchpop", "benchtail"]

    # Within BenchPop: rank 1, then rank 3, then unranked (nulls last).
    benchpop_ranks = [
        row["best_rank"] for row in rows if row["dataset_slug"] == "benchpop"
    ]
    assert benchpop_ranks == [1, 3, None]


def test_task_benchmarks_pinned_by_featured_rank_over_paper_count(client):
    """The task page benchmark list must pin benchmarks that carry a
    `featured_rank` ahead of unranked ones, ordered by ascending rank, even
    when an unranked benchmark has far more evaluations. The seed sets
    featured_rank=1 on Niche (1 eval) and featured_rank=2 on BrowseComp (2
    evals), leaving MCP-Atlas (5 evals) unranked; the pinned order must be
    Niche, BrowseComp, then MCP-Atlas, so popularity only orders the unranked
    tail."""
    db = TestingSessionLocal()
    _seed_paper_with_three_benchmarks(db)
    db.close()

    response = client.get(
        "/api/v1/datasets/?task=10&ordering=-paper_count&page_size=50"
    )
    assert response.status_code == 200
    payload = response.json()

    slugs = [d["slug"] for d in payload["results"]]
    assert slugs == ["niche", "browsecomp", "mcp-atlas"]
    # paper_count is the per-dataset evaluation row count; sanity check it
    # matches the seeded counts so we know the pin beat the popularity sort.
    counts = {d["slug"]: d["paper_count"] for d in payload["results"]}
    assert counts == {"mcp-atlas": 5, "browsecomp": 2, "niche": 1}


def test_task_benchmarks_filtered_by_min_eval_count(client):
    """`min_eval_count=2` hides single-evaluation benchmarks from the default
    task-page listing so sparse leaderboards don't clutter the UI. The
    benchmark fixture seeds MCP-Atlas (5 evals), BrowseComp (2), Niche (1);
    featured rank affects ordering only, so pinned Niche is still hidden."""
    db = TestingSessionLocal()
    _seed_paper_with_three_benchmarks(db)
    db.close()

    response = client.get(
        "/api/v1/datasets/?task=10&ordering=-paper_count&page_size=50&min_eval_count=2"
    )
    assert response.status_code == 200
    payload = response.json()

    slugs = [d["slug"] for d in payload["results"]]
    assert slugs == ["browsecomp", "mcp-atlas"]
    assert payload["count"] == 2


def test_task_page_hides_single_entry_benchmarks_by_default(client):
    """The bundled task-page payload omits benchmarks with only one entry,
    even when they have a featured rank."""
    db = TestingSessionLocal()
    _seed_paper_with_three_benchmarks(db)
    db.close()

    response = client.get("/api/v1/tasks/10/page")
    assert response.status_code == 200
    slugs = [d["slug"] for d in response.json()["benchmarks"]]
    assert slugs == ["browsecomp", "mcp-atlas"]


def test_task_benchmarks_unfiltered_when_min_eval_count_absent(client):
    """The filter must be opt-in: omitting `min_eval_count` keeps every
    benchmark (including sparse ones) visible so existing callers and the
    benchmark detail page see the full set."""
    db = TestingSessionLocal()
    _seed_paper_with_three_benchmarks(db)
    db.close()

    response = client.get(
        "/api/v1/datasets/?task=10&ordering=-paper_count&page_size=50"
    )
    assert response.status_code == 200
    payload = response.json()

    slugs = [d["slug"] for d in payload["results"]]
    assert slugs == ["niche", "browsecomp", "mcp-atlas"]
    assert payload["count"] == 3


if __name__ == "__main__":
    pytest.main([__file__])
