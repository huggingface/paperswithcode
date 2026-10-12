"""PostgreSQL relevance, ranking, vector, index, and latency coverage."""

import statistics
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.database.migrations.backfill_entity_search_vectors import backfill
from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    Method,
    Paper,
    PaperMethod,
    PaperTask,
    Task,
    TaskDataset,
)
from backend.services.dataset_service import DatasetService
from backend.services.method_service import MethodService
from backend.services.task_service import TaskService

MIGRATIONS = Path(__file__).parents[1] / "database" / "migrations"


def _execute_statements(connection, path: Path) -> None:
    for statement in path.read_text().split(";"):
        if statement.strip():
            connection.exec_driver_sql(statement)


@pytest.fixture(scope="module")
def entity_search_database_url():
    settings = get_settings()
    database_name = f"pwc_entity_search_test_{uuid4().hex[:12]}"
    subprocess.run(
        [
            "runuser",
            "-u",
            "postgres",
            "--",
            "createdb",
            "--owner",
            settings.db_user,
            database_name,
        ],
        check=True,
    )
    url = make_url(settings.database_url).set(database=database_name)
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        subprocess.run(
            ["runuser", "-u", "postgres", "--", "dropdb", "--force", database_name],
            check=True,
        )


@pytest.fixture(scope="module")
def entity_search_engine(entity_search_database_url):
    engine = create_engine(entity_search_database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in ("datasets", "methods", "tasks"):
            connection.execute(text(f"ALTER TABLE {table} DROP COLUMN search_vector"))
        migration = (MIGRATIONS / "add_entity_search_vectors.sql").read_text()
        connection.exec_driver_sql(migration)
        connection.exec_driver_sql(migration)
        connection.exec_driver_sql((MIGRATIONS / "enable_pg_trgm.sql").read_text())
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        _execute_statements(connection, MIGRATIONS / "add_entity_search_indexes.sql")
        _execute_statements(connection, MIGRATIONS / "add_entity_search_indexes.sql")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def session_factory(entity_search_engine):
    return sessionmaker(bind=entity_search_engine, expire_on_commit=False)


@pytest.fixture(scope="module", autouse=True)
def seeded_catalog(session_factory):
    today = datetime.now(UTC).date()
    with session_factory() as session:
        session.add_all(
            [
                Task(id=900, name="Evaluation", slug="evaluation"),
                Task(
                    id=1000,
                    name="Image Classification",
                    slug="image-classification",
                ),
                Task(id=1001, name="Image Matching", slug="image-matching"),
                Task(
                    id=1002,
                    name="Robotics",
                    slug="robotics",
                    description="Uses image observations.",
                ),
                Task(id=1003, name="Growth Task Alpha", slug="growth-task-alpha"),
                Task(id=1004, name="Growth Task Beta", slug="growth-task-beta"),
            ]
        )
        session.add_all(
            [
                Dataset(id=21, name="SWE-Bench", slug="swe-bench"),
                Dataset(id=22, name="SWE-Bench Verified", slug="swe-bench-verified"),
                Dataset(id=23, name="SWE-Bench Pro", slug="swe-bench-pro"),
                Dataset(
                    id=427,
                    name="SWE-Bench Multilingual",
                    slug="swe-bench-multilingual",
                ),
                Dataset(id=100, name="ScanNet", slug="scannet"),
                Dataset(id=101, name="ScanNet++", slug="scannet-plus-plus"),
                Dataset(id=447, name="τ²-Bench", slug="tau2-bench"),
                Dataset(id=580, name="τ²-Bench (Telecom)", slug="tau2-bench-telecom"),
                Dataset(
                    id=1420,
                    name="SIR²+ WildScene (RealRestorer protocol)",
                    slug="sir2-plus-wildscene",
                ),
                Dataset(
                    id=868,
                    name="VideoMatte (512×288)",
                    slug="videomatte-512x288",
                ),
                Dataset(
                    id=870,
                    name="YouTubeMatte (512×288)",
                    slug="youtube-matte-512x288",
                ),
                Dataset(
                    id=832,
                    name="Ego-Exo4D (Ego→Exo)",
                    slug="ego-exo4d-ego-to-exo",
                ),
                Dataset(id=900, name="Kimi K3", slug="kimi-k3"),
                Dataset(
                    id=901,
                    name="EETm2",
                    slug="eetm2",
                    description="A benchmark for transformer forecasting.",
                ),
                Dataset(id=902, name="Sparse Benchmark", slug="sparse-benchmark"),
                Dataset(id=903, name="Trend Set Alpha", slug="trend-set-alpha"),
                Dataset(id=904, name="Trend Set Beta", slug="trend-set-beta"),
                Dataset(id=905, name="HumanEval", slug="humaneval"),
                Dataset(
                    id=906,
                    name="BEDLAM (Human-Scene)",
                    slug="bedlam-human-scene",
                ),
            ]
        )
        session.add_all(
            [
                Method(id=1000, name="Transformer", slug="transformer"),
                Method(id=1001, name="Vision Transformer", slug="vision-transformer"),
                Method(
                    id=1002,
                    name="CNN",
                    slug="cnn",
                    full_name="Convolutional Neural Network",
                ),
                Method(
                    id=1003,
                    name="Unrelated Architecture",
                    slug="unrelated-architecture",
                    description="Uses transformer blocks.",
                ),
                Method(id=1004, name="Usage Method Alpha", slug="usage-method-alpha"),
                Method(id=1005, name="Usage Method Beta", slug="usage-method-beta"),
            ]
        )
        session.flush()
        session.add_all(
            [
                TaskDataset(task_id=900, dataset_id=903),
                TaskDataset(task_id=900, dataset_id=904),
            ]
        )

        paper_dates = {
            1: today - timedelta(days=10),
            2: today - timedelta(days=200),
            3: today - timedelta(days=10),
            4: today - timedelta(days=200),
        }
        for paper_id, published in paper_dates.items():
            session.add(
                Paper(
                    id=paper_id,
                    title=f"Search trend paper {paper_id}",
                    arxiv_id=f"2607.{paper_id:05d}",
                    version="v1",
                    is_latest_version=True,
                    date_published=published,
                )
            )
        session.flush()
        session.add_all(
            [
                Evaluation(
                    id=1,
                    paper_id=1,
                    task_id=900,
                    dataset_id=904,
                    model_name="Recent",
                    metrics={"Score": 1},
                ),
                Evaluation(
                    id=2,
                    paper_id=2,
                    task_id=900,
                    dataset_id=903,
                    model_name="Old",
                    metrics={"Score": 1},
                ),
                Evaluation(
                    id=3,
                    paper_id=1,
                    task_id=900,
                    dataset_id=905,
                    model_name="Recent",
                    metrics={"Score": 1},
                ),
                PaperMethod(paper_id=3, method_id=1005),
                PaperMethod(paper_id=4, method_id=1004),
            ]
        )

        next_paper_id = 100
        for task_id, recent_count, baseline_count in (
            (1003, 1, 5),
            (1004, 3, 1),
        ):
            for _ in range(recent_count):
                session.add(
                    Paper(
                        id=next_paper_id,
                        title=f"Recent task paper {next_paper_id}",
                        arxiv_id=f"2607.{next_paper_id:05d}",
                        version="v1",
                        is_latest_version=True,
                        date_published=today - timedelta(days=10),
                    )
                )
                session.flush()
                session.add(PaperTask(paper_id=next_paper_id, task_id=task_id))
                next_paper_id += 1
            for _ in range(baseline_count):
                session.add(
                    Paper(
                        id=next_paper_id,
                        title=f"Baseline task paper {next_paper_id}",
                        arxiv_id=f"2607.{next_paper_id:05d}",
                        version="v1",
                        is_latest_version=True,
                        date_published=today - timedelta(days=60),
                    )
                )
                session.flush()
                session.add(PaperTask(paper_id=next_paper_id, task_id=task_id))
                next_paper_id += 1
        session.commit()


def _slugs(page):
    return [result.slug for result in page.results]


def test_benchmark_identity_prefix_unicode_and_sparse_visibility(session_factory):
    with session_factory() as session:
        service = DatasetService(session)
        assert _slugs(service.search_datasets("SWE Bench"))[:1] == ["swe-bench"]
        assert "swe-bench-multilingual" in _slugs(
            service.search_datasets("swe ben mul")
        )
        assert _slugs(
            service.search_datasets(
                "https://paperswithcode.co/benchmark/swe-bench-multilingual"
            )
        ) == ["swe-bench-multilingual"]
        assert _slugs(service.search_datasets("ScanNet"))[:2] == [
            "scannet",
            "scannet-plus-plus",
        ]
        assert _slugs(service.search_datasets("ScanNet++"))[0] == "scannet-plus-plus"
        assert "tau2-bench" in _slugs(service.search_datasets("tau2 bench"))
        assert "sir2-plus-wildscene" in _slugs(service.search_datasets("sir2+"))
        assert set(_slugs(service.search_datasets("512x288"))) == {
            "videomatte-512x288",
            "youtube-matte-512x288",
        }
        assert _slugs(service.search_datasets("ego to exo")) == ["ego-exo4d-ego-to-exo"]
        assert _slugs(service.search_datasets("k3")) == ["kimi-k3"]
        assert service.search_datasets("imi").results == []
        sparse = service.search_datasets("Sparse Benchmark")
        assert _slugs(sparse) == ["sparse-benchmark"]
        assert sparse.results[0].paper_count == 0
        assert (
            service.search_datasets("Sparse Benchmark", min_eval_count=1).results == []
        )

        first_page = service.search_datasets("SWE Bench", page_size=2)
        second_page = service.search_datasets("SWE Bench", page=2, page_size=2)
        assert first_page.count == 4
        assert first_page.next_page == 2
        assert second_page.previous_page == 1
        assert set(_slugs(first_page)).isdisjoint(_slugs(second_page))

        assert set(_slugs(service.search_datasets("trend set", task_id=900))) == {
            "trend-set-alpha",
            "trend-set-beta",
        }
        assert service.search_datasets("trend set", task_id=1000).results == []


def test_name_only_boundaries_and_full_name_identity(session_factory):
    with session_factory() as session:
        assert DatasetService(session).search_datasets("Transformer").results == []
        methods = MethodService(session)
        assert _slugs(methods.search_methods("Transformer"))[:2] == [
            "transformer",
            "vision-transformer",
        ]
        assert "unrelated-architecture" not in _slugs(
            methods.search_methods("Transformer")
        )
        assert _slugs(methods.search_methods("Convolutional Neural Network")) == ["cnn"]
        assert methods.search_methods("Neural Network").results == []
        tasks = TaskService(session)
        assert _slugs(tasks.search_tasks("image")) == [
            "image-classification",
            "image-matching",
        ]
        assert "robotics" not in _slugs(tasks.search_tasks("image"))
        assert DatasetService(session).search_datasets("427").results == []
        assert (
            DatasetService(session)
            .search_datasets("https://example.com/benchmark/swe-bench")
            .results
            == []
        )


def test_zero_result_only_fuzzy_recovery_and_ambiguity(session_factory):
    with session_factory() as session:
        service = DatasetService(session)
        assert _slugs(service.search_datasets("swe benhc")) == ["swe-bench"]
        assert _slugs(service.search_datasets("multilingal")) == [
            "swe-bench-multilingual"
        ]
        assert _slugs(service.search_datasets("verifed")) == ["swe-bench-verified"]
        # A successful deterministic family query never mixes in typo candidates.
        assert "swe-bench" in _slugs(service.search_datasets("swe ben"))


def test_entity_native_trends_break_textual_ties(session_factory):
    with session_factory() as session:
        assert _slugs(DatasetService(session).search_datasets("trend set"))[:2] == [
            "trend-set-beta",
            "trend-set-alpha",
        ]
        # Hyphenated compounds and repeated words must not outrank trends for
        # a single-term query.
        assert _slugs(DatasetService(session).search_datasets("human"))[:2] == [
            "humaneval",
            "bedlam-human-scene",
        ]
        assert _slugs(MethodService(session).search_methods("usage method"))[:2] == [
            "usage-method-beta",
            "usage-method-alpha",
        ]
        assert _slugs(TaskService(session).search_tasks("growth task"))[:2] == [
            "growth-task-beta",
            "growth-task-alpha",
        ]


def test_vectors_triggers_indexes_and_plans(
    entity_search_engine, entity_search_database_url
):
    with entity_search_engine.begin() as connection:
        assert connection.execute(
            text("""
                SELECT pwc_entity_search_normalize('ＳＷＥ－Ｂｅｎｃｈ'),
                       pwc_entity_search_normalize('τ²-Bench'),
                       pwc_entity_search_normalize('Ego→Exo')
            """)
        ).one() == ("swe bench", "tau2 bench", "ego to exo")
        null_counts = connection.execute(
            text("""
                SELECT
                  (SELECT count(*) FROM datasets WHERE search_vector IS NULL),
                  (SELECT count(*) FROM methods WHERE search_vector IS NULL),
                  (SELECT count(*) FROM tasks WHERE search_vector IS NULL)
            """)
        ).one()
        assert tuple(null_counts) == (0, 0, 0)
        connection.execute(
            text("UPDATE datasets SET name = 'Trigger Vector Name' WHERE id = 902")
        )
        vector = connection.execute(
            text("SELECT search_vector::text FROM datasets WHERE id = 902")
        ).scalar_one()
        assert "trigger" in vector and "vector" in vector

        connection.execute(text("SET LOCAL enable_seqscan = off"))
        fts_plan = "\n".join(
            row[0]
            for row in connection.execute(
                text("""
                    EXPLAIN SELECT id FROM datasets
                    WHERE search_vector @@ websearch_to_tsquery('simple', 'swe')
                """)
            )
        )
        assert "idx_datasets_search_vector" in fts_plan
        trigram_plan = "\n".join(
            row[0]
            for row in connection.execute(
                text("""
                    EXPLAIN SELECT id FROM datasets
                    ORDER BY CAST('swe benhc' AS text)
                             <-> pwc_entity_search_normalize(name)
                    LIMIT 100
                """)
            )
        )
        assert "idx_datasets_name_search_trgm" in trigram_plan

    with entity_search_engine.begin() as connection:
        connection.execute(text("UPDATE datasets SET search_vector = NULL"))
        connection.execute(text("UPDATE methods SET search_vector = NULL"))
        connection.execute(text("UPDATE tasks SET search_vector = NULL"))
    updated, remaining = backfill(
        entity_search_database_url, batch_size=7, max_batches=100
    )
    assert all(updated[table] > 0 for table in ("datasets", "methods", "tasks"))
    assert remaining == {"datasets": 0, "methods": 0, "tasks": 0}


def test_warm_query_p95_is_below_one_hundred_ms(session_factory):
    with session_factory() as session:
        service = DatasetService(session)
        service.search_datasets("swe bench")
        timings = []
        for _ in range(25):
            started = time.perf_counter()
            service.search_datasets("swe bench")
            timings.append((time.perf_counter() - started) * 1000)
        p95 = statistics.quantiles(timings, n=20)[18]
        assert p95 < 100, f"warm dataset search p95 was {p95:.1f} ms"


def _seed_cleanup_fixture(connection) -> None:
    connection.exec_driver_sql("""
        INSERT INTO tasks (id, name, slug, parent_id, level)
        VALUES
          (5, 'Responsible AI', 'responsible-ai', NULL, 0),
          (256, 'General', 'general', NULL, 0),
          (260, 'Other', 'other', NULL, 0),
          (264, 'Few-shot Image Classification',
           'few-shot-image-classification', NULL, 0),
          (265, 'Open-vocabulary Object Detection',
           'open-vocabulary-object-detection', NULL, 0),
          (281, 'Coding', 'coding', NULL, 0),
          (282, 'Safety and Grounding', 'safety-and-grounding', 5, 1);

        INSERT INTO datasets (id, name, slug)
        VALUES
          (83, 'Safety Set One', 'safety-set-one'),
          (183, 'Safety Set Two', 'safety-set-two'),
          (269, 'NAVI', 'navi'),
          (274, 'SPair', 'spair'),
          (294, 'Safety Set Three', 'safety-set-three'),
          (315, 'Bird-SQL (dev)', 'bird-sql-dev'),
          (327, 'EvalPlus', 'evalplus'),
          (352, 'Revisited Oxford (R_Ox) — Medium split',
           'revisited-oxford-r-ox-medium-split'),
          (370, 'OpenRewrite-Eval', 'openrewrite-eval'),
          (627, 'Safety Set Four', 'safety-set-four');

        INSERT INTO papers (
            id, title, source, arxiv_id, version, is_latest_version,
            citation_count, urls_extracted
        )
        VALUES
          (55555, 'Safety paper', 'arxiv', '2607.55555', 'v1', true, 0, false),
          (83677, 'Llama 4', 'arxiv', '2607.83677', 'v1', true, 0, false),
          (99023, 'LongCat-2.0', 'arxiv', '2607.99023', 'v1', true, 0, false);

        INSERT INTO paper_tasks (paper_id, task_id, source)
        VALUES
          (55555, 282, 'manual'),
          (83677, 281, 'manual'),
          (99023, 281, 'manual');

        INSERT INTO metrics (id, name, direction)
        SELECT id, 'Cleanup Metric ' || id, 'higher_is_better'
        FROM generate_series(2001, 2010) AS id;

        INSERT INTO task_datasets (task_id, dataset_id)
        VALUES
          (281, 315), (281, 327), (281, 370),
          (260, 269), (260, 274), (260, 352),
          (282, 83), (282, 183), (282, 294), (282, 627);

        INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
        VALUES
          (281, 315, 2001), (281, 327, 2002), (281, 370, 2003),
          (260, 269, 2004), (260, 274, 2005), (260, 352, 2006),
          (282, 83, 2007), (282, 183, 2008),
          (282, 294, 2009), (282, 627, 2010);

        INSERT INTO evaluations (
            id, paper_id, task_id, dataset_id, model_name, metrics,
            uses_additional_data
        )
        SELECT
            10000 + row_number() OVER (),
            CASE WHEN task_id = 281 THEN 83677 ELSE 99023 END,
            task_id,
            dataset_id,
            'cleanup row ' || sample_number,
            '{"Score": 1}'::jsonb,
            false
        FROM (
            VALUES
              (281, 315, 3),
              (281, 327, 5),
              (281, 370, 1),
              (260, 269, 1),
              (260, 274, 1),
              (260, 352, 2)
        ) AS target(task_id, dataset_id, sample_count)
        CROSS JOIN LATERAL generate_series(
            1, target.sample_count
        ) AS sample_number;

        INSERT INTO evaluations (
            id, paper_id, task_id, dataset_id, model_name, metrics,
            uses_additional_data
        )
        SELECT
            11000 + sample_number,
            55555,
            282,
            (ARRAY[83, 183, 294, 627])[mod(sample_number - 1, 4) + 1],
            'safety row ' || sample_number,
            '{"Score": 1}'::jsonb,
            false
        FROM generate_series(1, 28) AS sample_number;
    """)


def _safety_snapshot(connection):
    return connection.execute(
        text("""
            SELECT
              (SELECT count(*) FROM tasks
               WHERE id = 282 AND slug = 'safety-and-grounding'
                 AND parent_id = 5),
              (SELECT count(*) FROM paper_tasks WHERE task_id = 282),
              (SELECT count(*) FROM task_datasets WHERE task_id = 282),
              (SELECT count(*) FROM task_dataset_metrics WHERE task_id = 282),
              (SELECT count(*) FROM evaluations WHERE task_id = 282)
        """)
    ).one()


def test_cleanup_preconditions_rollback_idempotency_and_drop_gate(
    entity_search_engine,
):
    cleanup = (MIGRATIONS / "cleanup_obsolete_hidden_tasks.sql").read_text()
    drop_visibility = (MIGRATIONS / "remove_tasks_is_visible.sql").read_text()
    with entity_search_engine.begin() as connection:
        _seed_cleanup_fixture(connection)
        safety_before = tuple(_safety_snapshot(connection))
        assert safety_before == (1, 1, 4, 4, 28)

    with entity_search_engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("UPDATE datasets SET slug = 'drifted' WHERE id = 315"))
        with pytest.raises(Exception, match="benchmark identity precondition"):
            connection.exec_driver_sql(cleanup.replace("%", "%%"))
        transaction.rollback()

    with entity_search_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT slug FROM datasets WHERE id = 315")
            ).scalar_one()
            == "bird-sql-dev"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM evaluations WHERE id >= 10000")
            ).scalar_one()
            == 41
        )

    with entity_search_engine.begin() as connection:
        connection.exec_driver_sql(cleanup.replace("%", "%%"))
    with entity_search_engine.begin() as connection:
        connection.exec_driver_sql(cleanup.replace("%", "%%"))

    with entity_search_engine.connect() as connection:
        assert (
            connection.execute(
                text("""
                SELECT count(*) FROM tasks
                WHERE id IN (256, 260, 264, 265, 281)
            """)
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("""
                SELECT count(*) FROM datasets
                WHERE id IN (269, 274, 315, 327, 352, 370)
            """)
            ).scalar_one()
            == 0
        )
        assert tuple(_safety_snapshot(connection)) == safety_before

    # Validate the production-gated drop only on this disposable database.
    with entity_search_engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE tasks ADD COLUMN is_visible boolean NOT NULL DEFAULT true"
        )
        connection.exec_driver_sql(
            "CREATE INDEX idx_tasks_is_visible ON tasks(is_visible)"
        )
        connection.exec_driver_sql(drop_visibility)
    with entity_search_engine.connect() as connection:
        assert (
            connection.execute(
                text("""
                SELECT count(*)
                FROM information_schema.columns
                WHERE table_name = 'tasks' AND column_name = 'is_visible'
            """)
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("""
                SELECT count(*)
                FROM pg_indexes
                WHERE tablename = 'tasks'
                  AND indexname = 'idx_tasks_is_visible'
            """)
            ).scalar_one()
            == 0
        )
