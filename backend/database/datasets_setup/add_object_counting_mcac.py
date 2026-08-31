#!/usr/bin/env python3
"""Add MCAC and MCAC-M1 benchmarks to Object Counting."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Paper
from backend.utils.slug_utils import slugify
from backend.services.dataset_service import DatasetService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 340
SOURCE_ARXIV = "2309.04820"
MAE_METRIC_ID = 6
RMSE_METRIC_ID = 8

BENCHMARKS = [
    {
        "name": "MCAC",
        "full_name": "Multi-class Class-Agnostic Counting",
        "description": (
            "Synthetic multi-class class-agnostic counting dataset with 1–4 object "
            "classes per image and 1–300 instances per class. Train/val/test splits "
            "use mutually exclusive classes."
        ),
        "short_description": "Multi-class class-agnostic counting benchmark.",
        "homepage": "https://mcac.active.vision",
        "introduced_date": date(2023, 9, 9),
    },
    {
        "name": "MCAC-M1",
        "full_name": "MCAC Single-Class Subset",
        "description": (
            "Single-class subset of MCAC containing images with only one object "
            "class per image, used to evaluate methods in less ambiguous settings."
        ),
        "short_description": "Single-class subset of MCAC.",
        "homepage": "https://mcac.active.vision",
        "introduced_date": date(2023, 9, 9),
    },
]


def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing
    raise RuntimeError(
        f"ArXiv paper {arxiv_id} must be indexed before running this script"
    )


def paper_url_for(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def ensure_dataset(session, spec: dict, source_paper: Paper) -> int:
    slug = slugify(spec["name"])
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": slug}
    ).first()
    native_url = paper_url_for(source_paper)
    if row:
        dataset_id = int(row[0])
    else:
        created = DatasetService(session).create_dataset(
            DatasetCreateRequest(
                name=spec["name"],
                full_name=spec["full_name"],
                description=spec["description"],
                short_description=spec["short_description"],
                homepage=spec["homepage"],
                paper_url=native_url,
                introduced_date=spec["introduced_date"],
                task_ids=[TASK_ID],
                languages=["English"],
                modalities=["Images"],
            )
        )
        dataset_id = int(created.id)

    session.execute(
        text(
            """
            UPDATE datasets
            SET introducing_paper_id = :pid,
                introducing_paper_title = :title,
                paper_url = :paper_url,
                introduced_year = COALESCE(introduced_year, :year),
                homepage = COALESCE(homepage, :homepage),
                full_name = COALESCE(full_name, :full_name),
                short_description = COALESCE(short_description, :short_description)
            WHERE id = :did
            """
        ),
        {
            "pid": source_paper.id,
            "title": source_paper.title,
            "paper_url": native_url,
            "year": spec["introduced_date"].year,
            "homepage": spec["homepage"],
            "full_name": spec["full_name"],
            "short_description": spec["short_description"],
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
        {"t": TASK_ID, "d": dataset_id},
    )
    for metric_id in (MAE_METRIC_ID, RMSE_METRIC_ID):
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:t, :d, :m)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {"t": TASK_ID, "d": dataset_id, "m": metric_id},
        )
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:p, :t, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"p": source_paper.id, "t": TASK_ID},
    )
    return dataset_id


def main() -> None:
    session = db_manager.session_local()
    try:
        source_paper = ensure_arxiv_paper(session, SOURCE_ARXIV)
        for spec in BENCHMARKS:
            dataset_id = ensure_dataset(session, spec, source_paper)
            logger.info(
                "Benchmark %s id=%s source=%s",
                spec["name"],
                dataset_id,
                paper_url_for(source_paper),
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
