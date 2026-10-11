#!/usr/bin/env python3
"""Add Cross-view object correspondence task and Ego-Exo4D leaderboards.

Creates the task, wires Ego→Exo and Exo→Ego IoU leaderboards to the Ego-Exo4D
source paper (2311.18259), and imports supervised VGGT-S results from 2604.13596.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_cross_view_object_correspondence_benchmarks.py
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.taxonomy import TaskCreateRequest
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Paper, Task as DBTask
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.services.task_service import TaskService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VIDEO_AREA_ID = 9
IOU_METRIC_ID = 29

EGO_EXO4D_ARXIV_ID = "2311.18259"
VGGT_S_ARXIV_ID = "2604.13596"

TASK_NAME = "Cross-view object correspondence"
TASK_SLUG = "cross-view-object-correspondence"
TASK_DESCRIPTION = (
    "Cross-view object correspondence localizes and segments the same physical "
    "object across different camera viewpoints, often between egocentric and "
    "exocentric streams. Methods take a source-view object mask (or prompt) and "
    "predict the matching mask in a target view. Related to "
    "[Image segmentation](/tasks/image-segmentation) for single-view masks and "
    "[Video Understanding](/tasks/video-understanding) for broader egocentric "
    "activity understanding."
)
TASK_KEYWORDS = (
    "cross-view object correspondence, cross view object correspondence, "
    "ego-exo object correspondence, ego exo correspondence, cross-view segmentation, "
    "cross view segmentation, ego-exo4d, ego exo4d, mask transfer across views, "
    "cross-view mask prediction"
)

BENCHMARKS = [
    {
        "name": "Ego-Exo4D (Ego→Exo)",
        "full_name": "Ego-Exo4D Object Correspondence (Ego→Exo)",
        "short_description": (
            "Given an egocentric object mask, segment the same object in the "
            "exocentric view."
        ),
        "description": (
            "Ego→Exo split of the Ego-Exo4D object correspondence benchmark. Given "
            "a query mask in the egocentric view, models predict the matching object "
            "mask in the synchronized exocentric view. Reported as mean IoU on the "
            "official validation split."
        ),
        "slug_hint": "ego-exo4d-ego-to-exo",
    },
    {
        "name": "Ego-Exo4D (Exo→Ego)",
        "full_name": "Ego-Exo4D Object Correspondence (Exo→Ego)",
        "short_description": (
            "Given an exocentric object mask, segment the same object in the "
            "egocentric view."
        ),
        "description": (
            "Exo→Ego split of the Ego-Exo4D object correspondence benchmark. Given "
            "a query mask in the exocentric view, models predict the matching object "
            "mask in the synchronized egocentric view. Reported as mean IoU on the "
            "official validation split."
        ),
        "slug_hint": "ego-exo4d-exo-to-ego",
    },
]

EVAL_ROWS = [
    {
        "dataset_slug": "ego-exo4d-ego-to-exo",
        "model_name": "VGGT-S",
        "score": "67.7",
        "methodology": (
            "Supervised VGGT-S on the official Ego-Exo4D train/validation split; "
            "Ego→Exo mean IoU from Table 1 of arXiv:2604.13596."
        ),
    },
    {
        "dataset_slug": "ego-exo4d-exo-to-ego",
        "model_name": "VGGT-S",
        "score": "68.0",
        "methodology": (
            "Supervised VGGT-S on the official Ego-Exo4D train/validation split; "
            "Exo→Ego mean IoU from Table 1 of arXiv:2604.13596."
        ),
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


def _source_paper(session: Session) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == EGO_EXO4D_ARXIV_ID, Paper.is_latest_version.is_(True))
        .one()
    )
    return paper


def _result_paper(session: Session) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == VGGT_S_ARXIV_ID, Paper.is_latest_version.is_(True))
        .one()
    )
    return paper


def _promote_paper_task_to_manual(
    session: Session, paper_id: int, task_id: int
) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:p, :t, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"p": paper_id, "t": task_id},
    )


def _ensure_dataset(
    session: Session,
    spec: dict,
    task_id: int,
    source_paper: Paper,
) -> int:
    slug = spec["slug_hint"]
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": slug}
    ).first()
    paper_url = f"https://paperswithcode.co/paper/{source_paper.arxiv_id}"

    if row:
        dataset_id = int(row[0])
    else:
        created = DatasetService(session).create_dataset(
            DatasetCreateRequest(
                name=spec["name"],
                full_name=spec["full_name"],
                description=spec["description"],
                short_description=spec["short_description"],
                homepage="https://ego-exo4d-data.org/",
                paper_url=paper_url,
                introduced_date=date(2024, 6, 1),
                task_ids=[task_id],
                languages=["English"],
                modalities=["Videos"],
            )
        )
        dataset_id = int(created.id)
        session.execute(
            text("UPDATE datasets SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": dataset_id},
        )

    session.execute(
        text(
            """
            UPDATE datasets
            SET introducing_paper_id = :pid,
                introducing_paper_title = :title,
                paper_url = :paper_url,
                introduced_year = COALESCE(introduced_year, 2024),
                homepage = COALESCE(homepage, :homepage),
                full_name = COALESCE(full_name, :full_name),
                short_description = COALESCE(short_description, :short_description),
                slug = :slug
            WHERE id = :did
            """
        ),
        {
            "pid": source_paper.id,
            "title": source_paper.title,
            "paper_url": paper_url,
            "homepage": "https://ego-exo4d-data.org/",
            "full_name": spec["full_name"],
            "short_description": spec["short_description"],
            "slug": slug,
            "did": dataset_id,
        },
    )
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:t, :d, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
            """
        ),
        {"t": task_id, "d": dataset_id},
    )
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:t, :d, :m)
            ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
            """
        ),
        {"t": task_id, "d": dataset_id, "m": IOU_METRIC_ID},
    )
    return dataset_id


def _ensure_evaluations(
    session: Session,
    task_id: int,
    result_paper: Paper,
    dataset_ids_by_slug: dict[str, int],
) -> None:
    service = EvaluationService(session)
    for row in EVAL_ROWS:
        dataset_id = dataset_ids_by_slug[row["dataset_slug"]]
        params = {
            "paper_id": result_paper.id,
            "task_id": task_id,
            "dataset_id": dataset_id,
            "model_name": row["model_name"],
            "harness": None,
            "best_metric": "IoU",
        }
        existing = session.execute(
            text(
                """
                SELECT id FROM evaluations
                WHERE paper_id = :paper_id
                  AND task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND model_name = :model_name
                  AND COALESCE(harness, '') = COALESCE(:harness, '')
                  AND best_metric = :best_metric
                """
            ),
            params,
        ).first()
        if existing:
            logger.info(
                "Evaluation already exists for %s on %s",
                row["model_name"],
                row["dataset_slug"],
            )
            continue

        service.create_evaluation(
            paper_id=result_paper.id,
            task_id=task_id,
            dataset_id=dataset_id,
            model_name=row["model_name"],
            methodology=row["methodology"],
            metrics={"IoU": row["score"]},
            best_metric="IoU",
            external_source_url=f"https://paperswithcode.co/paper/{result_paper.arxiv_id}",
            is_open=True,
        )
        logger.info(
            "Created evaluation %s / %s IoU=%s",
            row["model_name"],
            row["dataset_slug"],
            row["score"],
        )

    for dataset_id in dataset_ids_by_slug.values():
        service.recalculate_ranks(task_id, dataset_id, metric_name="IoU")


def main() -> None:
    session = db_manager.session_local()
    try:
        task = _ensure_task(session)
        source_paper = _source_paper(session)
        result_paper = _result_paper(session)

        dataset_ids_by_slug: dict[str, int] = {}
        for spec in BENCHMARKS:
            dataset_id = _ensure_dataset(session, spec, task.id, source_paper)
            dataset_ids_by_slug[spec["slug_hint"]] = dataset_id
            logger.info(
                "Benchmark %s id=%s slug=%s",
                spec["name"],
                dataset_id,
                spec["slug_hint"],
            )

        _promote_paper_task_to_manual(session, source_paper.id, task.id)
        _promote_paper_task_to_manual(session, result_paper.id, task.id)

        _ensure_evaluations(session, task.id, result_paper, dataset_ids_by_slug)
        session.commit()

        rows = (
            session.execute(
                text(
                    """
                    SELECT d.slug, d.name, d.paper_url,
                           array_agg(m.name ORDER BY m.name) AS metrics
                    FROM task_datasets td
                    JOIN datasets d ON d.id = td.dataset_id
                    LEFT JOIN task_dataset_metrics tdm
                      ON tdm.task_id = td.task_id AND tdm.dataset_id = td.dataset_id
                    LEFT JOIN metrics m ON m.id = tdm.metric_id
                    WHERE td.task_id = :task_id
                    GROUP BY d.slug, d.name, d.paper_url
                    ORDER BY d.name
                    """
                ),
                {"task_id": task.id},
            )
            .mappings()
            .all()
        )
        logger.info("Task %s benchmarks:", TASK_SLUG)
        for row in rows:
            logger.info("  %s", dict(row))

        evals = (
            session.execute(
                text(
                    """
                    SELECT e.model_name, d.slug, e.best_metric, e.metrics, e.is_open
                    FROM evaluations e
                    JOIN datasets d ON d.id = e.dataset_id
                    WHERE e.paper_id = :paper_id
                    ORDER BY d.slug
                    """
                ),
                {"paper_id": result_paper.id},
            )
            .mappings()
            .all()
        )
        logger.info("VGGT-S evaluations:")
        for row in evals:
            logger.info("  %s", dict(row))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
