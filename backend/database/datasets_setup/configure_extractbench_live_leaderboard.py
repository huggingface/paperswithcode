"""Create the ExtractBench benchmark for the hourly live leaderboard sync.

ExtractBench (arxiv:2607.29677) scores schema-guided enterprise document
extraction. Requested in huggingface/paperswithcode-feedback#47. This script:

* creates (or refreshes) `datasets.slug = 'extractbench'` pointing at the
  latest version of the introducing paper,
* creates the three ExtractBench metrics and links them on the Agents and
  Document Understanding tasks,
* tags the introducing paper with both tasks.

The sync refuses to run until this script has been applied.
Dry-run by default; pass `--apply` to write.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/configure_extractbench_live_leaderboard.py --apply
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset, Metric, Paper, Task
from backend.services.extractbench_sync_service import (
    DATASET_SLUG,
    GROUNDING_METRICS,
    PRIMARY_METRIC_NAME,
    TASK_SLUG,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

EXTRACTBENCH_ARXIV_ID = "2607.29677"
TASK_SLUGS = (TASK_SLUG, "document-understanding")
PAPER_URL = f"https://paperswithcode.co/paper/{EXTRACTBENCH_ARXIV_ID}"
HF_DATASET_URL = "https://huggingface.co/datasets/llamaindex/ExtractBench"
GITHUB_URL = "https://github.com/run-llama/ExtractBench"
DATASET_NAME = "ExtractBench"
DATASET_SHORT_DESCRIPTION = (
    "Schema-guided extraction with grounding over 370 enterprise documents "
    "(4,869 pages)."
)
DATASET_DESCRIPTION = (
    "ExtractBench evaluates agents and extraction systems on schema-guided "
    "enterprise document extraction: given a document and a user-defined JSON "
    "schema, a system must return schema-conformant values together with "
    "source evidence. It covers 4,869 pages across 370 documents, 8 business "
    "domains, and 67 document types, split into short, medium, and long "
    "documents. The headline metric is unified value F1; word- and page-level "
    "grounding F1 measure whether each accepted value cites the right evidence."
)

METRICS = {
    PRIMARY_METRIC_NAME: (
        "ExtractBench Unified Value F1",
        "Order-insensitive F1 over flattened scalar fields and aligned record "
        "subfields, averaged per document. ExtractBench's headline metric.",
    ),
    "Word Grounding F1": (
        "ExtractBench Word-level Grounding F1",
        "A field counts only when its value is accepted and its predicted "
        "evidence box overlaps an accepted box at IoU 0.5; scored on documents "
        "with verified box ground truth.",
    ),
    "Page Grounding F1": (
        "ExtractBench Page-level Grounding F1",
        "A field counts only when its value is accepted and the cited source "
        "page is correct; scored on documents with verified box ground truth.",
    ),
}
assert set(METRICS) == {PRIMARY_METRIC_NAME, *(name for name, _ in GROUNDING_METRICS)}


def _latest_paper(session: Session) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == EXTRACTBENCH_ARXIV_ID, Paper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"ExtractBench paper {EXTRACTBENCH_ARXIV_ID} is not indexed")
    return paper


def _ensure_dataset(session: Session, paper: Paper) -> Dataset:
    dataset = session.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
    if dataset is None:
        dataset = Dataset(name=DATASET_NAME, slug=DATASET_SLUG)
        session.add(dataset)
        logger.info("Creating dataset %r", DATASET_SLUG)
    dataset.full_name = DATASET_NAME
    dataset.description = DATASET_DESCRIPTION
    dataset.short_description = DATASET_SHORT_DESCRIPTION
    dataset.url = HF_DATASET_URL
    dataset.hf_url = HF_DATASET_URL
    dataset.homepage = GITHUB_URL
    dataset.paper_url = PAPER_URL
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_year = 2026
    session.flush()
    logger.info("Dataset id=%s -> introducing paper id=%s", dataset.id, paper.id)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes")
    args = parser.parse_args()

    with db_manager.session_local() as session:
        paper = _latest_paper(session)
        dataset = _ensure_dataset(session, paper)
        metric_ids = _ensure_metrics(session)
        for task in _tasks(session):
            _link(session, task.id, dataset.id, metric_ids)
            _tag_source_paper(session, paper.id, task.id)
        if args.apply:
            session.commit()
            logger.info(
                "ExtractBench ready: dataset_id=%s metrics=%s", dataset.id, metric_ids
            )
        else:
            session.rollback()
            logger.info("Dry run complete; re-run with --apply")


if __name__ == "__main__":
    main()
