#!/usr/bin/env python3
"""Add PrACo benchmark and missing object-counting source papers."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Paper
from backend.services.dataset_service import DatasetService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.utils.slug_utils import slugify

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 340
MAE_METRIC_ID = 6

PRACO_ARXIV = "2409.15953"

EXTERNAL_PAPERS = {
    "groundingrec": {
        "source_url": "https://openaccess.thecvf.com/content/CVPR2024/html/Dai_Referring_Expression_Counting_CVPR_2024_paper.html",
        "title": "Referring Expression Counting",
        "abstract": (
            "Introduces Referring Expression Counting (REC), which counts objects "
            "with different attributes within the same class using natural-language "
            "referring expressions, together with the REC-8K evaluation dataset."
        ),
        "authors": ["Siyang Dai", "Jun Liu", "Ngai-Man Cheung"],
        "date_published": date(2024, 6, 17),
        "github_repository_urls": [
            "https://github.com/sydai/referring-expression-counting"
        ],
    },
    "countse": {
        "source_url": "https://openaccess.thecvf.com/content/ICCV2025/html/Liu_CountSE_Soft_Exemplar_Open-set_Object_Counting_ICCV_2025_paper.html",
        "title": "CountSE: Soft Exemplar Open-set Object Counting",
        "abstract": (
            "Proposes CountSE, a text-guided zero-shot object counting method that "
            "generates soft exemplars at multiple scales via semantic-guided "
            "exemplar selection and clustering-based exemplar filtering."
        ),
        "authors": ["Shuai Liu", "Peng Zhang", "Shiwei Zhang", "Wei Ke"],
        "date_published": date(2025, 10, 23),
        "github_repository_urls": ["https://github.com/pppppz22/CountSE"],
    },
}

PRACO_METRICS = [
    ("NMN", "lower_is_better", "Normalized Mean of Negative predictions"),
    ("PCCN", "higher_is_better", "Positive Class Count Nearness"),
    ("CntP", "higher_is_better", "Counting Precision"),
    ("CntR", "higher_is_better", "Counting Recall"),
]


def ensure_external_paper(session, key: str) -> Paper:
    spec = EXTERNAL_PAPERS[key]
    existing = (
        session.query(Paper)
        .filter(Paper.source == "external", Paper.source_url == spec["source_url"])
        .first()
    )
    if existing:
        return existing
    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=spec["source_url"],
            title=spec["title"],
            abstract=spec["abstract"],
            authors=spec["authors"],
            date_published=spec["date_published"],
            github_repository_urls=spec["github_repository_urls"],
        )
    )
    return result.paper


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


def ensure_metric(session, name: str, direction: str, full_name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).first()
    if row:
        return int(row[0])
    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:n, :d, :full, 'unbounded', :desc)
            RETURNING id
            """
        ),
        {"n": name, "d": direction, "full": full_name, "desc": full_name},
    ).scalar_one()
    logger.info("Created metric %s id=%s", name, metric_id)
    return int(metric_id)


def paper_url_for(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def ensure_praco_dataset(session, source_paper: Paper) -> int:
    slug = slugify("PrACo")
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": slug}
    ).first()
    native_url = paper_url_for(source_paper)
    if row:
        dataset_id = int(row[0])
    else:
        created = DatasetService(session).create_dataset(
            DatasetCreateRequest(
                name="PrACo",
                full_name="Prompt-Aware Counting (PrACo)",
                description=(
                    "Prompt-aware class-agnostic counting benchmark built from FSC-147 "
                    "images with a negative-label test (absent target class) and a "
                    "mosaic test (multi-class images with a single-class prompt)."
                ),
                short_description="Negative-label and mosaic prompt-aware counting tests.",
                homepage="https://github.com/ciampluca/PrACo",
                paper_url=native_url,
                introduced_date=date(2025, 2, 28),
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
            "year": 2025,
            "homepage": "https://github.com/ciampluca/PrACo",
            "full_name": "Prompt-Aware Counting (PrACo)",
            "short_description": "Negative-label and mosaic prompt-aware counting tests.",
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
    for metric_name, direction, full_name in PRACO_METRICS:
        metric_id = ensure_metric(session, metric_name, direction, full_name)
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
        praco_paper = ensure_arxiv_paper(session, PRACO_ARXIV)
        dataset_id = ensure_praco_dataset(session, praco_paper)
        logger.info(
            "PrACo benchmark id=%s paper=%s", dataset_id, paper_url_for(praco_paper)
        )

        for key in EXTERNAL_PAPERS:
            paper = ensure_external_paper(session, key)
            session.execute(
                text(
                    """
                    INSERT INTO paper_tasks (paper_id, task_id, source)
                    VALUES (:p, :t, 'manual')
                    ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                    """
                ),
                {"p": paper.id, "t": TASK_ID},
            )
            logger.info("%s paper id=%s url=%s", key, paper.id, paper_url_for(paper))

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
