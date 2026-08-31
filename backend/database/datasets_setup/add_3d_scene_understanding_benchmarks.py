#!/usr/bin/env python3
"""Wire ScanNet scene-language benchmarks to the 3D understanding task.

Adds:
  - ScanQA, SQA3D, Scan2Cap, ScanRefer, Multi3DRef
  - Leaderboard metrics used by GPT4Scene and related 3D-VLM papers

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_3d_scene_understanding_benchmarks.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.dataset_service import DatasetService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_SLUG = "3d-understanding"

SOURCE_ARXIV = {
    "scanqa": "2112.10482",
    "sqa3d": "2210.07474",
    "scan2cap": "2012.02206",
    "scanrefer": "1912.08830",
    "multi3dref": "2309.05251",
}

NEW_METRICS = [
    ("EM-1", "higher_is_better", "Exact Match at IoU threshold 1 for 3D QA"),
    ("Acc@0.25", "higher_is_better", "Accuracy at IoU 0.25 for 3D visual grounding"),
    ("F1@0.25", "higher_is_better", "F1 at IoU 0.25 for multi-object 3D grounding"),
]

BENCHMARKS = [
    {
        "name": "ScanQA",
        "slug": "scanqa",
        "full_name": "ScanQA: 3D Question Answering for Spatial Scene Understanding",
        "description": (
            "ScanQA contains 41K+ question-answer pairs over ScanNet scenes for "
            "3D spatial scene understanding and embodied question answering."
        ),
        "short_description": "3D question answering benchmark on ScanNet scenes.",
        "homepage": "https://github.com/atr-dbi/scanqa",
        "introduced_date": date(2021, 12, 20),
        "source_key": "scanqa",
        "featured_rank": 7,
        "metrics": ["CIDEr", "ROUGE"],
        "modalities": ["3D", "Texts"],
    },
    {
        "name": "SQA3D",
        "slug": "sqa3d",
        "full_name": "Situated Question Answering in 3D Scenes",
        "description": (
            "SQA3D evaluates embodied scene understanding from an egocentric agent "
            "perspective with situated, knowledge-intensive questions over ScanNet."
        ),
        "short_description": "Situated 3D question answering from an egocentric viewpoint.",
        "homepage": "https://sqa3d.github.io",
        "introduced_date": date(2022, 10, 14),
        "source_key": "sqa3d",
        "featured_rank": 8,
        "metrics": ["EM-1"],
        "modalities": ["3D", "Images", "Video", "Texts"],
    },
    {
        "name": "Scan2Cap",
        "slug": "scan2cap",
        "full_name": "Scan2Cap: Context-aware Dense Captioning in RGB-D Scans",
        "description": (
            "Scan2Cap is the dense 3D captioning benchmark on ScanNet, requiring "
            "models to localize objects and generate natural-language descriptions."
        ),
        "short_description": "Dense 3D object captioning on ScanNet scenes.",
        "homepage": "https://github.com/daveredrum/Scan2Cap",
        "introduced_date": date(2020, 12, 3),
        "source_key": "scan2cap",
        "featured_rank": 9,
        "metrics": ["CIDEr", "ROUGE"],
        "modalities": ["3D", "Texts"],
    },
    {
        "name": "ScanRefer",
        "slug": "scanrefer",
        "full_name": "ScanRefer: 3D Object Localization in RGB-D Scans using Natural Language",
        "description": (
            "ScanRefer contains 51K+ natural-language expressions grounding objects "
            "in 800 ScanNet scenes for 3D visual grounding."
        ),
        "short_description": "3D visual grounding with natural-language expressions.",
        "homepage": "https://github.com/daveredrum/ScanRefer",
        "introduced_date": date(2019, 12, 18),
        "source_key": "scanrefer",
        "featured_rank": 10,
        "metrics": ["Acc@0.25", "Acc@0.5"],
        "modalities": ["3D", "Texts"],
    },
    {
        "name": "Multi3DRef",
        "slug": "multi3dref",
        "full_name": "Multi3DRefer: Grounding Text Description to Multiple 3D Objects",
        "description": (
            "Multi3DRef extends 3D visual grounding to multi-target referring expressions "
            "over ScanNet scenes."
        ),
        "short_description": "Multi-object 3D visual grounding benchmark.",
        "homepage": "https://github.com/ZzZZCHS/M3DRef-CLIP",
        "introduced_date": date(2023, 9, 11),
        "source_key": "multi3dref",
        "featured_rank": 11,
        "metrics": ["F1@0.25", "F1"],
        "modalities": ["3D", "Texts"],
    },
]


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(f"Failed to fetch arXiv metadata for {arxiv_id}")

    paper_id = PaperService(session).add_paper(
        {
            "arxiv_id": metadata.arxiv_id,
            "title": metadata.title,
            "abstract": metadata.abstract,
            "version": metadata.version,
            "date_published": metadata.published.date() if metadata.published else None,
            "primary_category": metadata.primary_category,
            "all_categories": metadata.categories,
            "is_latest_version": True,
        }
    )
    paper = session.get(Paper, paper_id)
    if metadata.authors:
        for order, author_name in enumerate(metadata.authors, start=1):
            author = session.query(Author).filter(Author.name == author_name).first()
            if not author:
                author = Author(name=author_name)
                session.add(author)
                session.flush()
            session.add(
                PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=order)
            )
        session.flush()
    return paper


def paper_url_for(paper: Paper) -> str:
    arxiv_id = getattr(paper, "arxiv_id", None)
    if arxiv_id:
        return f"https://paperswithcode.co/paper/{arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def paper_title(paper: Paper) -> str:
    return str(getattr(paper, "title", "") or "")


def ensure_metric(session, name: str, direction: str, description: str) -> int:
    row = session.execute(
        text("SELECT id, direction FROM metrics WHERE name = :n"),
        {"n": name},
    ).fetchone()
    if row:
        metric_id = int(row[0])
        if row[1] != direction:
            session.execute(
                text("UPDATE metrics SET direction = :d WHERE id = :id"),
                {"d": direction, "id": metric_id},
            )
        return metric_id

    metric_id = session.execute(
        text(
            "INSERT INTO metrics (name, direction, full_name, scale, description) "
            "VALUES (:n, :d, :f, :s, :desc) RETURNING id"
        ),
        {
            "n": name,
            "d": direction,
            "f": name,
            "s": "unbounded",
            "desc": description,
        },
    ).scalar_one()
    return int(metric_id)


def ensure_new_metrics(session) -> dict[str, int]:
    metric_ids: dict[str, int] = {}
    for name, direction, description in NEW_METRICS:
        metric_ids[name] = ensure_metric(session, name, direction, description)
        logger.info("Ensured metric %r (id=%s)", name, metric_ids[name])
    return metric_ids


def resolve_metric_id(session, metric_name: str, metric_ids: dict[str, int]) -> int:
    if metric_name in metric_ids:
        return metric_ids[metric_name]
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"),
        {"n": metric_name},
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Metric {metric_name!r} not found in database")
    return int(row[0])


def ensure_dataset_row(
    session,
    task_id: int,
    spec: dict,
    source_paper: Paper,
) -> int:
    slug = spec["slug"]
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": slug},
    ).first()

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
                paper_url=paper_url_for(source_paper),
                introduced_date=spec["introduced_date"],
                task_ids=[task_id],
                modalities=spec.get("modalities", ["3D"]),
            )
        )
        dataset_id = int(created.id)
        logger.info("Created dataset %r (id=%s)", spec["name"], dataset_id)

    session.execute(
        text(
            """
            UPDATE datasets
            SET introducing_paper_id = :pid,
                introducing_paper_title = :title,
                paper_url = :paper_url,
                introduced_year = COALESCE(introduced_year, :year),
                homepage = COALESCE(:homepage, homepage),
                full_name = COALESCE(:full_name, full_name),
                short_description = COALESCE(:short_description, short_description),
                description = COALESCE(:description, description)
            WHERE id = :did
            """
        ),
        {
            "pid": source_paper.id,
            "title": paper_title(source_paper),
            "paper_url": paper_url_for(source_paper),
            "year": spec.get("introduced_date").year
            if spec.get("introduced_date")
            else None,
            "homepage": spec.get("homepage"),
            "full_name": spec.get("full_name"),
            "short_description": spec.get("short_description"),
            "description": spec.get("description"),
            "did": dataset_id,
        },
    )

    return dataset_id


def wire_task_dataset(
    session,
    task_id: int,
    dataset_id: int,
    featured_rank: int | None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, featured_rank, supports_harness)
            VALUES (:t, :d, :rank, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET featured_rank = EXCLUDED.featured_rank,
                supports_harness = FALSE
            """
        ),
        {"t": task_id, "d": dataset_id, "rank": featured_rank},
    )


def wire_metrics(
    session,
    task_id: int,
    dataset_id: int,
    metric_names: list[str],
    metric_ids: dict[str, int],
) -> list[str]:
    linked: list[str] = []
    for metric_name in metric_names:
        metric_id = resolve_metric_id(session, metric_name, metric_ids)
        session.execute(
            text(
                "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
                "VALUES (:t, :d, :m) "
                "ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
            ),
            {"t": task_id, "d": dataset_id, "m": metric_id},
        )
        linked.append(metric_name)
    return linked


def promote_paper_task(session, paper_id: int, task_id: int) -> None:
    session.execute(
        text(
            "INSERT INTO paper_tasks (paper_id, task_id, source) "
            "VALUES (:p, :t, 'manual') "
            "ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'"
        ),
        {"p": paper_id, "t": task_id},
    )


async def main() -> None:
    session = db_manager.session_local()
    report: list[str] = []
    try:
        task_row = session.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"),
            {"slug": TASK_SLUG},
        ).one()
        task_id = int(task_row[0])
        metric_ids = ensure_new_metrics(session)

        arxiv_papers: dict[str, Paper] = {}
        for key, arxiv_id in SOURCE_ARXIV.items():
            arxiv_papers[key] = await ensure_arxiv_paper(session, arxiv_id)
            logger.info(
                "Resolved arXiv source %s -> paper id=%s title=%r",
                arxiv_id,
                arxiv_papers[key].id,
                paper_title(arxiv_papers[key]),
            )

        for spec in BENCHMARKS:
            source_paper = arxiv_papers[spec["source_key"]]
            dataset_id = ensure_dataset_row(session, task_id, spec, source_paper)
            wire_task_dataset(session, task_id, dataset_id, spec.get("featured_rank"))
            linked_metrics = wire_metrics(
                session, task_id, dataset_id, spec["metrics"], metric_ids
            )
            promote_paper_task(session, source_paper.id, task_id)

            row = session.execute(
                text("SELECT name, slug, paper_url FROM datasets WHERE id = :id"),
                {"id": dataset_id},
            ).one()
            report.append(
                f"{row.name} (slug={row.slug}): metrics={linked_metrics}, "
                f"featured_rank={spec.get('featured_rank')}, paper_url={row.paper_url}"
            )

        session.commit()
        logger.info("3D scene understanding benchmarks wired successfully.")
        for line in report:
            logger.info("  %s", line)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
