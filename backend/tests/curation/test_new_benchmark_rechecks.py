"""New leaderboards queue capped add-evals re-checks for papers that report them."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperCurationBootstrapBundle,
    PaperCurationJob,
    PaperCurationSchedulerState,
    PaperCurationWorkflow,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services import new_benchmark_recheck_service as recheck_module
from backend.services.abstract_mention_service import CatalogEntity
from backend.services.codex_add_evals_service import CodexPaperJobService
from backend.services.new_benchmark_recheck_service import (
    NewBenchmarkRecheckService,
    without_references,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


NOW = datetime(2026, 11, 3, 6, 35, tzinfo=UTC)
BOARD_CREATED = NOW - timedelta(hours=10)
BEFORE = BOARD_CREATED - timedelta(days=20)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Task.__table__,
            Dataset.__table__,
            Metric.__table__,
            TaskDataset.__table__,
            TaskDatasetMetric.__table__,
            Evaluation.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationBootstrapBundle.__table__,
            PaperCurationJob.__table__,
            PaperCurationSchedulerState.__table__,
        ],
    )
    with Session(engine) as session:
        # The production loader uses Postgres casts; read the test datasets.
        monkeypatch.setattr(
            recheck_module,
            "load_catalog_entities",
            lambda database: [
                CatalogEntity(
                    entity_type="dataset",
                    entity_id=row.id,
                    name=row.name,
                    slug=row.slug,
                    parent_id=row.parent_dataset_id,
                )
                for row in database.query(Dataset)
            ],
        )
        session.add_all(
            [
                Task(id=1, name="Mathematical Reasoning", slug="math-reasoning"),
                Task(id=2, name="Image Classification", slug="image-classification"),
                Metric(id=1, name="Accuracy", direction="higher_is_better"),
                Dataset(id=10, name="GSM8K", slug="gsm8k"),
                Dataset(id=11, name="ImageNet", slug="imagenet"),
                Dataset(id=20, name="AIME 2025", slug="aime-2025"),
                Dataset(id=40, name="MMLU", slug="mmlu"),
                Dataset(id=41, name="MMLU-Pro", slug="mmlu-pro"),
            ]
        )
        session.flush()
        add_board(session, 1, 10, BEFORE - timedelta(days=100))
        add_board(session, 2, 11, BEFORE - timedelta(days=100))
        add_board(session, 1, 41, BEFORE - timedelta(days=100))
        yield session


def add_board(db, task_id: int, dataset_id: int, created_at: datetime) -> None:
    db.add(
        TaskDatasetMetric(
            task_id=task_id, dataset_id=dataset_id, metric_id=1, created_at=created_at
        )
    )
    db.flush()


def add_paper(
    db,
    paper_id: int,
    *,
    task_id: int = 1,
    dataset_id: int = 10,
    eval_at: datetime = BEFORE,
    abstract: str | None = None,
) -> Paper:
    paper = Paper(
        id=paper_id,
        arxiv_id=f"2610.{paper_id:05d}",
        title=f"Paper {paper_id}",
        source="arxiv",
        abstract=abstract,
        is_latest_version=True,
        date_published=(BEFORE - timedelta(days=paper_id)).date(),
    )
    db.add(paper)
    db.add(
        Evaluation(
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            model_name=f"Model {paper_id}",
            metrics={"Accuracy": 50.0},
            best_metric="Accuracy",
            created_at=eval_at,
        )
    )
    db.flush()
    return paper


def body(*sentences: str) -> str:
    return "# Paper\n\n" + "\n\n".join(sentences)


def run(db, texts: dict[int, tuple[str, bool]], **kwargs):
    reads: list[int] = []

    def read_text(paper):
        reads.append(paper.id)
        return texts.get(paper.id, (paper.abstract or "", False))

    service = NewBenchmarkRecheckService(db, get_settings(), read_text=read_text)
    result = service.reconcile(
        since=NOW - timedelta(days=2), job_service=CodexPaperJobService(), **kwargs
    )
    return result, reads


def rechecks(db) -> dict[int, PaperCurationJob]:
    return {
        row.paper_id: row
        for row in db.query(PaperCurationJob).filter(
            PaperCurationJob.policy_version.like("new-benchmark-%")
        )
    }


def test_new_board_queues_rechecks_only_for_papers_that_report_it(db):
    add_board(db, 1, 20, BOARD_CREATED)
    reports = "Table 2: AIME 2025 accuracy of our model. We gain 4 points on AIME 2025."
    add_paper(db, 1)  # reports it in its own tables
    add_paper(db, 2)  # cites it only in the bibliography
    add_paper(db, 3)  # names it once, in related work
    add_paper(db, 4)  # already has an AIME 2025 row
    db.add(
        Evaluation(
            paper_id=4,
            task_id=1,
            dataset_id=20,
            model_name="Model 4",
            metrics={"Accuracy": 30.0},
            best_metric="Accuracy",
            created_at=BOARD_CREATED,
        )
    )
    add_paper(db, 5, abstract="We reach 61% on AIME 2025.")  # no Markdown yet
    add_paper(db, 6, eval_at=BOARD_CREATED + timedelta(hours=1))  # curated after
    add_paper(db, 7, task_id=2, dataset_id=11)  # another task
    add_paper(db, 8)  # add-evals already in flight
    db.add(
        PaperCurationJob(
            id=uuid.uuid4(),
            kind="add-evals",
            paper_id=8,
            requested_by="test",
            status="running",
            trigger="hf-daily-cron",
        )
    )
    db.flush()
    texts = {
        1: (body(reports), True),
        2: (body("Intro.", "## References", "AIME 2025 problems. AIME 2025."), True),
        3: (body("Prior work evaluates on AIME 2025."), True),
        6: (body(reports), True),
        7: (body(reports), True),
        8: (body(reports), True),
    }

    result, reads = run(db, texts)

    assert [item["paper_id"] for item in result["rechecks"]] == [1, 5]
    assert sorted(reads) == [1, 2, 3, 5]
    jobs = rechecks(db)
    assert set(jobs) == {1, 5}
    job = jobs[1]
    assert (job.kind, job.status, job.trigger, job.priority) == (
        "add-evals",
        "queued",
        "benchmark-promotion",
        50,
    )
    assert job.policy_version == "new-benchmark-20"
    assert job.requested_by == "new-benchmark:20"

    # Idempotent per (paper, dataset): the next daily run queues nothing new.
    again, _reads = run(db, texts)
    assert again["rechecks"] == []
    assert len(rechecks(db)) == 2


def test_longer_benchmark_names_are_not_mentions_of_a_new_prefix_board(db):
    add_board(db, 1, 40, BOARD_CREATED)
    add_paper(db, 1)
    add_paper(db, 2)
    texts = {
        1: (body("MMLU-Pro: 71.2.", "On MMLU-Pro we beat the baseline."), True),
        2: (body("MMLU: 88.0 and MMLU-Pro: 71.2.", "MMLU improves by 2."), True),
    }

    result, _reads = run(db, texts)

    assert [item["paper_id"] for item in result["rechecks"]] == [2]


def test_rechecks_are_capped_per_benchmark_and_prefer_more_mentions(db, monkeypatch):
    monkeypatch.setattr(recheck_module, "MAX_PER_BENCHMARK", 2)
    add_board(db, 1, 20, BOARD_CREATED)
    texts = {}
    for paper_id, mentions in ((1, 2), (2, 5), (3, 3)):
        add_paper(db, paper_id)
        texts[paper_id] = (body(*["AIME 2025: 40.0."] * mentions), True)

    result, _reads = run(db, texts)

    assert [(i["paper_id"], i["mentions"]) for i in result["rechecks"]] == [
        (2, 5),
        (3, 3),
    ]


def test_per_benchmark_cap_counts_jobs_from_earlier_runs(db, monkeypatch):
    monkeypatch.setattr(recheck_module, "MAX_PER_BENCHMARK", 2)
    add_board(db, 1, 20, BOARD_CREATED)
    texts = {}
    for paper_id in (1, 2, 3, 4):
        add_paper(db, paper_id)
        texts[paper_id] = (body("AIME 2025: 40.0.", "AIME 2025: 41.0."), True)

    first, _reads = run(db, texts)
    second, reads = run(db, texts)

    assert len(first["rechecks"]) == 2
    assert second["rechecks"] == []
    assert reads == []
    assert len(rechecks(db)) == 2


def test_failed_rechecks_free_their_paper_and_cap_slot(db, monkeypatch):
    monkeypatch.setattr(recheck_module, "MAX_PER_BENCHMARK", 1)
    add_board(db, 1, 20, BOARD_CREATED)
    add_paper(db, 1)
    texts = {1: (body("AIME 2025: 40.0.", "AIME 2025: 41.0."), True)}
    run(db, texts)
    rechecks(db)[1].status = "failed"
    db.flush()

    result, _reads = run(db, texts)

    assert [item["paper_id"] for item in result["rechecks"]] == [1]


def test_storage_failure_defers_the_benchmark_instead_of_using_abstracts(db):
    add_board(db, 1, 20, BOARD_CREATED)
    add_paper(db, 1, abstract="We reach 61% on AIME 2025.")
    service = NewBenchmarkRecheckService(
        db, get_settings(), read_text=lambda paper: None
    )

    result = service.reconcile(
        since=NOW - timedelta(days=2), job_service=CodexPaperJobService()
    )

    assert result["rechecks"] == []
    assert result["unscanned_dataset_ids"] == [20]


def test_text_budget_leaves_the_rest_for_the_next_run(db, monkeypatch):
    monkeypatch.setattr(recheck_module, "MAX_TEXT_READS", 1)
    add_board(db, 1, 20, BOARD_CREATED)
    add_paper(db, 1)
    add_paper(db, 2)

    result, reads = run(db, {}, dry_run=True)

    assert len(reads) == 1
    assert result["unscanned_dataset_ids"] == [20]
    assert rechecks(db) == {}


def test_one_job_covers_a_paper_that_reports_several_new_boards(db):
    add_board(db, 1, 20, BOARD_CREATED)
    add_board(db, 1, 40, BOARD_CREATED + timedelta(minutes=5))
    add_paper(db, 1)
    texts = {1: (body("AIME 2025: 40.0. MMLU: 80.", "AIME 2025 and MMLU."), True)}

    result, _reads = run(db, texts)

    assert [(i["dataset_id"], i["paper_id"]) for i in result["rechecks"]] == [(20, 1)]


def test_without_references_keeps_appendices_after_the_bibliography():
    markdown = "\n".join(
        [
            "# Title",
            "## 5 Results",
            "AIME 2025 table",
            "## References",
            "[1] AIME 2025 dataset card.",
            "### Older work",
            "[2] More citations.",
            "## Appendix A Extra results",
            "AIME 2025 appendix table",
        ]
    )

    kept = without_references(markdown)

    assert "AIME 2025 table" in kept
    assert "AIME 2025 appendix table" in kept
    assert "dataset card" not in kept
    assert "More citations" not in kept


def test_dispatcher_caps_active_new_benchmark_rechecks(db, monkeypatch):
    def job(paper_id: int, status: str, policy: str, minutes: int):
        db.add(
            Paper(
                id=paper_id,
                arxiv_id=f"2610.{paper_id:05d}",
                title=f"P{paper_id}",
                source="arxiv",
            )
        )
        row = PaperCurationJob(
            id=uuid.uuid4(),
            kind="add-evals",
            paper_id=paper_id,
            requested_by="test",
            status=status,
            trigger="benchmark-promotion",
            policy_version=policy,
            priority=50,
            created_at=NOW + timedelta(minutes=minutes),
        )
        db.add(row)
        return row

    job(1, "running", "new-benchmark-20", 0)
    job(2, "running", "new-benchmark-21", 1)
    waiting = job(3, "queued", "new-benchmark-22", 2)
    other = job(4, "queued", "benchmark-promotion-abc", 3)
    db.flush()
    dispatched = []

    def dispatch_row(_db, _settings, row):
        row.status = "running"
        dispatched.append(row.paper_id)

    service = CodexPaperJobService()
    monkeypatch.setattr(service, "_dispatch_row", dispatch_row)
    settings = get_settings().model_copy(
        update={"codex_jobs_max_active": 7, "codex_curation_scheduler_enabled": False}
    )

    service._dispatch_next_locked(db, settings)

    assert dispatched == [4]
    assert (waiting.status, other.status) == ("queued", "running")
