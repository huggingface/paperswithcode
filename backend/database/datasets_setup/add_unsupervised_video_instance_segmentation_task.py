#!/usr/bin/env python3
"""Add Unsupervised video instance segmentation task and migrate UVIS evals.

Creates the UVIS task, links YouTube-VIS 2019/2021 and DAVIS leaderboards,
and moves zero-shot VideoCutLER evaluations off the shared Video segmentation task.

To undo, run revert_unsupervised_video_instance_segmentation_task.py first.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_unsupervised_video_instance_segmentation_task.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.taxonomy import TaskCreateRequest
from backend.models.database import Task as DBTask
from backend.services.evaluation_service import EvaluationService
from backend.services.task_service import TaskService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VIDEO_AREA_ID = 9
VIDEO_SEGMENTATION_TASK_ID = 262

TASK_NAME = "Unsupervised video instance segmentation"
TASK_SLUG = "unsupervised-video-instance-segmentation"
TASK_DESCRIPTION = (
    "Unsupervised video instance segmentation (UVIS) discovers, segments, and tracks "
    "multiple object instances across video frames without human annotations on target "
    "videos. Leaderboards here use zero-shot or fully unsupervised training protocols "
    "that are not comparable to supervised video instance segmentation or semi-supervised "
    "video object segmentation."
)
TASK_KEYWORDS = (
    "unsupervised video instance segmentation, UVIS, unsupervised VIS, "
    "zero-shot video instance segmentation, class-agnostic video instance segmentation"
)

YOUTUBE_VIS_2019_DATASET_ID = 606
YOUTUBE_VIS_2021_DATASET_ID = 607
DAVIS_DATASET_ID = 263

YOUTUBE_VIS_INTRO_PAPER_ID = 2087
YOUTUBE_VIS_ARXIV_ID = "1905.04804"
DAVIS_INTRO_PAPER_ID = 54095
DAVIS_ARXIV_ID = "1704.00675"

VIDEOCUTLER_PAPER_ID = 19871

AP_METRIC_ID = 124
AP50_METRIC_ID = 13
JF_METRIC_ID = 61

ZERO_SHOT_EVAL_IDS = [9080, 9081, 9082]

BENCHMARKS = [
    {
        "dataset_id": YOUTUBE_VIS_2019_DATASET_ID,
        "featured_rank": 1,
        "metric_ids": [AP_METRIC_ID, AP50_METRIC_ID],
        "intro_paper_id": YOUTUBE_VIS_INTRO_PAPER_ID,
        "paper_url": f"https://paperswithcode.co/paper/{YOUTUBE_VIS_ARXIV_ID}",
    },
    {
        "dataset_id": YOUTUBE_VIS_2021_DATASET_ID,
        "featured_rank": 2,
        "metric_ids": [AP_METRIC_ID, AP50_METRIC_ID],
        "intro_paper_id": YOUTUBE_VIS_INTRO_PAPER_ID,
        "paper_url": f"https://paperswithcode.co/paper/{YOUTUBE_VIS_ARXIV_ID}",
    },
    {
        "dataset_id": DAVIS_DATASET_ID,
        "featured_rank": 3,
        "metric_ids": [JF_METRIC_ID],
        "intro_paper_id": DAVIS_INTRO_PAPER_ID,
        "paper_url": f"https://paperswithcode.co/paper/{DAVIS_ARXIV_ID}",
    },
]


def _ensure_task(session: Session) -> DBTask:
    existing = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if existing is not None:
        logger.info("Task already exists: %r (id=%s)", existing.name, existing.id)
        return existing

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name=TASK_NAME,
            description=TASK_DESCRIPTION,
            keywords=TASK_KEYWORDS,
            area_id=VIDEO_AREA_ID,
        )
    )
    logger.info("Created task %r (id=%s, slug=%s)", task.name, task.id, task.slug)
    return session.query(DBTask).filter(DBTask.id == task.id).one()


def _promote_paper_task_to_manual(
    session: Session, paper_id: int, task_id: int
) -> None:
    session.execute(
        text(
            "INSERT INTO paper_tasks (paper_id, task_id, source) "
            "VALUES (:p, :t, 'manual') "
            "ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'"
        ),
        {"p": paper_id, "t": task_id},
    )


def _ensure_benchmark_links(session: Session, task_id: int) -> None:
    for spec in BENCHMARKS:
        session.execute(
            text(
                """
                INSERT INTO task_datasets (task_id, dataset_id, featured_rank, supports_harness)
                VALUES (:t, :d, :rank, FALSE)
                ON CONFLICT (task_id, dataset_id) DO UPDATE
                SET featured_rank = COALESCE(EXCLUDED.featured_rank, task_datasets.featured_rank)
                """
            ),
            {
                "t": task_id,
                "d": spec["dataset_id"],
                "rank": spec["featured_rank"],
            },
        )
        session.execute(
            text(
                """
                UPDATE datasets
                SET paper_url = :paper_url,
                    introducing_paper_id = :intro_id,
                    introducing_paper_title = (
                        SELECT title FROM papers WHERE id = :intro_id
                    )
                WHERE id = :dataset_id
                  AND (
                    paper_url IS NULL
                    OR paper_url NOT LIKE 'https://paperswithcode.co/paper/%'
                    OR introducing_paper_id IS NULL
                  )
                """
            ),
            {
                "paper_url": spec["paper_url"],
                "intro_id": spec["intro_paper_id"],
                "dataset_id": spec["dataset_id"],
            },
        )
        for metric_id in spec["metric_ids"]:
            session.execute(
                text(
                    "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
                    "VALUES (:t, :d, :m) ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
                ),
                {"t": task_id, "d": spec["dataset_id"], "m": metric_id},
            )


def _migrate_evaluations(session: Session, uvis_task_id: int) -> None:
    service = EvaluationService(session)

    for eval_id in ZERO_SHOT_EVAL_IDS:
        row = (
            session.execute(
                text(
                    "SELECT task_id, dataset_id, best_metric FROM evaluations WHERE id = :id"
                ),
                {"id": eval_id},
            )
            .mappings()
            .one()
        )
        service.update_evaluation(evaluation_id=eval_id, task_id=uvis_task_id)
        logger.info(
            "Moved evaluation %s -> task %s (dataset %s, metric %s)",
            eval_id,
            uvis_task_id,
            row["dataset_id"],
            row["best_metric"],
        )

    for dataset_id, metric_name in [
        (YOUTUBE_VIS_2019_DATASET_ID, "AP"),
        (YOUTUBE_VIS_2021_DATASET_ID, "AP"),
        (DAVIS_DATASET_ID, "J&F"),
    ]:
        service.recalculate_ranks(uvis_task_id, dataset_id, metric_name=metric_name)
        service.recalculate_ranks(
            VIDEO_SEGMENTATION_TASK_ID, dataset_id, metric_name=metric_name
        )


def main() -> None:
    session = db_manager.session_local()
    try:
        task = _ensure_task(session)
        _ensure_benchmark_links(session, task.id)

        _promote_paper_task_to_manual(session, YOUTUBE_VIS_INTRO_PAPER_ID, task.id)
        _promote_paper_task_to_manual(session, DAVIS_INTRO_PAPER_ID, task.id)
        _promote_paper_task_to_manual(session, VIDEOCUTLER_PAPER_ID, task.id)

        session.commit()
        _migrate_evaluations(session, task.id)
        session.commit()

        rows = (
            session.execute(
                text(
                    """
                SELECT d.name, td.featured_rank,
                       array_agg(m.name ORDER BY m.name) AS metrics
                FROM task_datasets td
                JOIN datasets d ON d.id = td.dataset_id
                LEFT JOIN task_dataset_metrics tdm
                  ON tdm.task_id = td.task_id AND tdm.dataset_id = td.dataset_id
                LEFT JOIN metrics m ON m.id = tdm.metric_id
                WHERE td.task_id = :task_id
                GROUP BY d.name, td.featured_rank
                ORDER BY td.featured_rank NULLS LAST, d.name
                """
                ),
                {"task_id": task.id},
            )
            .mappings()
            .all()
        )
        logger.info("UVIS task benchmarks:")
        for row in rows:
            logger.info(
                "  %s rank=%s metrics=%s",
                row["name"],
                row["featured_rank"],
                row["metrics"],
            )

        moved = (
            session.execute(
                text(
                    """
                SELECT e.id, e.model_name, d.name AS dataset, e.best_metric, e.metrics, e.task_id
                FROM evaluations e
                JOIN datasets d ON d.id = e.dataset_id
                WHERE e.paper_id = :paper_id
                ORDER BY e.task_id, d.name, e.model_name
                """
                ),
                {"paper_id": VIDEOCUTLER_PAPER_ID},
            )
            .mappings()
            .all()
        )
        logger.info("VideoCutLER evaluations after migration:")
        for row in moved:
            logger.info("  %s", dict(row))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
