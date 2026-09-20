"""Prepare the ParseBench benchmark for the hourly live leaderboard sync.

ParseBench (arxiv:2604.08538) was created by `add_parsebench_benchmark.py` as
`datasets.slug = 'parsebench'`, linked to the OCR and Document Understanding
tasks with a single `Accuracy` metric holding snapshot scores copied from the
paper. The live sync publishes
ParseBench's own overall score plus its five dimension scores, so this script:

* points the benchmark at the latest version of the introducing paper,
* creates and links the six ParseBench metrics on both tasks,
* unlinks the placeholder `Accuracy` metric,
* retires the stale snapshot rows that the live sync supersedes.

Dry-run by default; pass `--apply` to write.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/configure_parsebench_live_leaderboard.py --apply
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset, Evaluation, Metric, Paper, Task
from backend.services.evaluation_service import EvaluationService
from backend.services.parsebench_sync_service import (
    DATASET_SLUG,
    DIMENSION_METRICS,
    MANAGED_METHODOLOGY_PREFIX,
    PRIMARY_METRIC_NAME,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PARSEBENCH_ARXIV_ID = "2604.08538"
TASK_SLUGS = ("ocr", "document-understanding")
PAPER_URL = f"https://paperswithcode.co/paper/{PARSEBENCH_ARXIV_ID}"
DATASET_URL = "https://huggingface.co/datasets/llamaindex/ParseBench"
DATASET_HOMEPAGE = "https://github.com/run-llama/parsebench"

METRICS = {
    PRIMARY_METRIC_NAME: (
        "ParseBench Overall Score",
        "Mean of ParseBench's five dimension scores (Tables, Charts, Content "
        "Faithfulness, Semantic Formatting, Visual Grounding). This is "
        "ParseBench's headline leaderboard metric.",
    ),
    "Tables": (
        "ParseBench Tables Score",
        "Table structure fidelity (GriTS + TableRecordMatch) over 503 pages of "
        "merged-cell and hierarchical-header tables.",
    ),
    "Charts": (
        "ParseBench Charts Score",
        "Chart data-point match rate over 568 pages of bar, line, pie, and "
        "compound charts with correct series and axis labels.",
    ),
    "Content Faithfulness": (
        "ParseBench Content Faithfulness Score",
        "Rule pass rate for omissions, hallucinations, and reading-order "
        "violations over 506 text pages.",
    ),
    "Semantic Formatting": (
        "ParseBench Semantic Formatting Score",
        "Rule pass rate for meaning-carrying formatting (strikethrough, "
        "super/subscript, bold, title hierarchy) over 476 text pages.",
    ),
    "Visual Grounding": (
        "ParseBench Visual Grounding Score",
        "Element pass rate for tracing extracted elements back to their source "
        "location on 500 layout pages.",
    ),
}
assert set(METRICS) == {PRIMARY_METRIC_NAME, *(name for name, _ in DIMENSION_METRICS)}


def _latest_paper(session: Session) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == PARSEBENCH_ARXIV_ID, Paper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"ParseBench paper {PARSEBENCH_ARXIV_ID} is not indexed")
    return paper


def _dataset(session: Session, paper: Paper) -> Dataset:
    dataset = session.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
    if dataset is None:
        raise RuntimeError(f"Dataset slug={DATASET_SLUG!r} not found")
    dataset.url = DATASET_URL
    dataset.homepage = DATASET_HOMEPAGE
    dataset.paper_url = PAPER_URL
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = dataset.introduced_year or 2026
    logger.info("Dataset %s -> introducing paper id=%s", dataset.id, paper.id)
    return dataset


def _tasks(session: Session) -> list[Task]:
    tasks = session.query(Task).filter(Task.slug.in_(TASK_SLUGS)).all()
    missing = set(TASK_SLUGS) - {task.slug for task in tasks}
    if missing:
        raise RuntimeError(f"Tasks not found: {sorted(missing)!r}")
    return tasks


def _ensure_metrics(session: Session) -> dict[str, int]:
    metric_ids: dict[str, int] = {}
    for name, (full_name, description) in METRICS.items():
        metric = session.query(Metric).filter(Metric.name == name).one_or_none()
        if metric is None:
            metric = Metric(name=name)
            session.add(metric)
            logger.info("Creating metric %r", name)
        metric.full_name = full_name
        metric.direction = "higher_is_better"
        metric.scale = "0-100"
        metric.description = description
        session.flush()
        metric_ids[name] = metric.id
    return metric_ids


def _link(session: Session, task_id: int, dataset_id: int, metric_ids: dict[str, int]):
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )
    for metric_id in metric_ids.values():
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
        )
    session.execute(
        text(
            """
            DELETE FROM task_dataset_metrics
            WHERE task_id = :task_id AND dataset_id = :dataset_id
              AND metric_id = (SELECT id FROM metrics WHERE name = 'Accuracy')
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )


def _tag_source_paper(session: Session, paper_id: int, task_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT DO NOTHING
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


def _retire_snapshots(session: Session, dataset_id: int) -> int:
    """Delete `Accuracy` rows that copied ParseBench overall scores by hand.

    Every such row is a point-in-time copy of the same leaderboard the live
    sync now owns, so keeping them would list the same model twice.
    """
    rows = (
        session.query(Evaluation)
        .filter(
            Evaluation.dataset_id == dataset_id,
            Evaluation.best_metric == "Accuracy",
            ~Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
        )
        .all()
    )
    service = EvaluationService(session)
    for row in rows:
        logger.info(
            "Retiring snapshot evaluation id=%s model=%r accuracy=%s",
            row.id,
            row.model_name,
            (row.metrics or {}).get("Accuracy"),
        )
        service.delete_evaluation(row.id, commit=False)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes")
    args = parser.parse_args()

    with db_manager.session_local() as session:
        paper = _latest_paper(session)
        dataset = _dataset(session, paper)
        tasks = _tasks(session)
        metric_ids = _ensure_metrics(session)
        for task in tasks:
            _link(session, task.id, dataset.id, metric_ids)
            _tag_source_paper(session, paper.id, task.id)
        retired = _retire_snapshots(session, dataset.id)
        session.flush()
        for task in tasks:
            EvaluationService(session).recalculate_ranks(
                task.id, dataset.id, metric_name=PRIMARY_METRIC_NAME, commit=False
            )
        if args.apply:
            session.commit()
            logger.info(
                "ParseBench ready: dataset_id=%s retired=%s paper_url=%s",
                dataset.id,
                retired,
                PAPER_URL,
            )
        else:
            session.rollback()
            logger.info(
                "Dry run complete (%s snapshot rows would be retired); "
                "re-run with --apply",
                retired,
            )


if __name__ == "__main__":
    main()
