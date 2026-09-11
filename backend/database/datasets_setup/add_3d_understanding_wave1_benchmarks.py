#!/usr/bin/env python3
"""Wire Wave 1 feed-forward 3D geometry benchmarks to the 3D understanding task.

Adds or updates:
  - 7-Scenes, NRGBD, DyCheck, TUM-Dynamic, Sintel (camera)
  - Camera pose metrics on CO3Dv2 / Re10K / ScanNet-1500 / Sintel / DyCheck / TUM-Dynamic
  - Reconstruction metrics on 7-Scenes / NRGBD
  - Featured ranks for core comparison benchmarks

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_3d_understanding_wave1_benchmarks.py
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
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_SLUG = "3d-understanding"

SOURCE_ARXIV = {
    "nrgbd": "2104.04532",
    "dycheck": "2210.13445",
}

SOURCE_EXTERNAL = {
    "7_scenes": {
        "source_url": (
            "https://openaccess.thecvf.com/content_cvpr_2013/papers/"
            "Shotton_Scene_Coordinate_Regression_2013_CVPR_paper.pdf"
        ),
        "title": (
            "Scene Coordinate Regression Forests for Camera Relocalization in RGB-D Images"
        ),
        "abstract": (
            "Introduces scene coordinate regression forests for RGB-D camera "
            "relocalization and the 7-Scenes dataset of tracked indoor RGB-D sequences "
            "widely used for dense tracking, mapping, and feed-forward reconstruction."
        ),
        "authors": [
            "Jamie Shotton",
            "Ben Glocker",
            "Christopher Zach",
            "Shahram Izadi",
            "Antonio Criminisi",
            "Andrew Fitzgibbon",
        ],
        "date_published": date(2013, 6, 1),
    },
    "tum_dynamic": {
        "source_url": "https://www.cvlibs.net/publications/Sturm2012IROS.pdf",
        "title": "A benchmark for the evaluation of RGB-D SLAM systems",
        "abstract": (
            "Introduces the TUM RGB-D benchmark for evaluating RGB-D SLAM and "
            "geometry-estimation systems on indoor sequences with accurate ground-truth "
            "trajectories. Widely used for dynamic-scene camera evaluation splits such as "
            "TUM-Dynamic in recent feed-forward reconstruction papers."
        ),
        "authors": [
            "Jürgen Sturm",
            "Nikolas Engelhard",
            "Felix Endres",
            "Wolfram Burgard",
            "Daniel Cremers",
        ],
        "date_published": date(2012, 10, 1),
    },
    "sintel": {
        "source_url": "http://sintel.is.tue.mpg.de/",
        "title": "A Naturalistic Open Source Movie for Optical Flow Evaluation",
        "abstract": (
            "Introduces the MPI Sintel movie dataset with rendered views, depth, and "
            "camera motion. Commonly used for optical-flow, depth, and camera-pose "
            "evaluation on challenging synthetic scenes."
        ),
        "authors": [
            "Daniel J. Butler",
            "Jonas Wulff",
            "Stanley B. Blackburn",
            "Erich Wenger",
            "Benjamin Mosberger",
            "Felix Fischer",
            "David A. Haefner",
            "Alexey Krivokon",
            "Michael Stark",
            "Gabriele Crete",
            "Patrick Roth",
            "Michael Black",
        ],
        "date_published": date(2012, 10, 7),
    },
    "imc": {
        "source_url": "https://www.cs.ubc.ca/research/image-matching-challenge/",
        "title": "Image Matching Challenge — Phototourism Benchmark",
        "abstract": (
            "Benchmark suite from the Image Matching Challenge / Image Matching Workshop "
            "for evaluating local features, matchers, and camera-pose estimation on "
            "phototourism scenes with COLMAP-derived reference geometry."
        ),
        "authors": [
            "Image Matching Workshop Organizers",
        ],
        "date_published": date(2020, 6, 1),
    },
}

NEW_METRICS = [
    (
        "RRA@15",
        "higher_is_better",
        "Relative Rotation Accuracy at 15° threshold",
    ),
    (
        "RTA@15",
        "higher_is_better",
        "Relative Translation Accuracy at 15° threshold",
    ),
    (
        "mAA@30",
        "higher_is_better",
        "Mean Average Accuracy at 30° threshold",
    ),
]

BENCHMARKS = [
    {
        "slug": "co3dv2",
        "existing": True,
        "featured_rank": 1,
        "metrics": ["AUC@30", "RRA@15", "RTA@15", "mAA@30"],
    },
    {
        "slug": "re10k",
        "existing": True,
        "featured_rank": 2,
        "metrics": ["AUC@30", "RRA@15", "RTA@15", "mAA@30"],
    },
    {
        "slug": "scannet-1500",
        "existing": True,
        "featured_rank": 3,
        "metrics": ["AUC@10", "AUC@20"],
    },
    {
        "name": "Sintel",
        "slug": "sintel",
        "full_name": "MPI Sintel",
        "description": (
            "MPI Sintel is a synthetic movie dataset with multiple rendered views, depth, "
            "and camera motion. Feed-forward geometry papers evaluate camera-pose accuracy "
            "on Sintel using AUC at angular thresholds."
        ),
        "short_description": "Synthetic movie dataset for camera-pose and flow evaluation.",
        "homepage": "http://sintel.is.tue.mpg.de/",
        "introduced_date": date(2012, 10, 7),
        "source_key": "sintel",
        "source_kind": "external",
        "featured_rank": 4,
        "metrics": ["AUC@3", "AUC@30"],
        "modalities": ["Images", "Video"],
    },
    {
        "slug": "7-scenes",
        "existing": True,
        "featured_rank": 5,
        "source_key": "7_scenes",
        "source_kind": "external",
        "homepage": "https://www.microsoft.com/en-us/research/project/rgb-d-dataset-7-scenes/",
        "metrics": [
            "Pointmap Accuracy",
            "Completeness",
            "Normal Consistency",
            "Overall (Chamfer)",
        ],
    },
    {
        "slug": "imc-image-matching-challenge",
        "existing": True,
        "featured_rank": 6,
        "source_key": "imc",
        "source_kind": "external",
        "homepage": "https://www.cs.ubc.ca/research/image-matching-challenge/",
        "metrics": ["AUC@3", "AUC@5", "AUC@10"],
    },
    {
        "name": "NRGBD",
        "slug": "nrgbd",
        "full_name": "Neural RGB-D (NRGBD)",
        "description": (
            "Neural RGB-D scene benchmark used for dense surface reconstruction evaluation. "
            "Feed-forward reconstruction papers report accuracy, completeness, and Chamfer "
            "distance after aligning predicted geometry to ground truth."
        ),
        "short_description": "RGB-D scene reconstruction benchmark from Neural RGB-D.",
        "homepage": "https://niessnerlab.org/projects/neuralrgbd",
        "introduced_date": date(2022, 6, 1),
        "source_key": "nrgbd",
        "source_kind": "arxiv",
        "featured_rank": None,
        "metrics": [
            "Pointmap Accuracy",
            "Completeness",
            "Normal Consistency",
            "Overall (Chamfer)",
            "AUC@3",
            "AUC@30",
        ],
        "modalities": ["Images", "Depth"],
    },
    {
        "name": "DyCheck",
        "slug": "dycheck",
        "full_name": "DyCheck",
        "description": (
            "DyCheck is a dynamic-scene view-synthesis benchmark used to evaluate camera "
            "pose and reconstruction on non-rigid / dynamic content."
        ),
        "short_description": "Dynamic view-synthesis benchmark for camera-pose evaluation.",
        "homepage": "https://dycheck.github.io/",
        "introduced_date": date(2022, 12, 1),
        "source_key": "dycheck",
        "source_kind": "arxiv",
        "featured_rank": None,
        "metrics": ["AUC@3", "AUC@30"],
        "modalities": ["Images", "Video"],
    },
    {
        "name": "TUM-Dynamic",
        "slug": "tum-dynamic",
        "full_name": "TUM RGB-D Dynamic",
        "description": (
            "Dynamic evaluation split derived from the TUM RGB-D benchmark, used for "
            "camera-pose estimation on moving-scene sequences in recent feed-forward "
            "reconstruction papers."
        ),
        "short_description": "Dynamic TUM RGB-D split for camera-pose evaluation.",
        "homepage": "https://cvg.cit.tum.de/data/datasets/rgbd-dataset",
        "introduced_date": date(2012, 10, 1),
        "source_key": "tum_dynamic",
        "source_kind": "external",
        "featured_rank": None,
        "metrics": ["AUC@3", "AUC@30"],
        "modalities": ["Images", "Depth"],
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


def ensure_external_paper(session, key: str) -> Paper:
    spec = SOURCE_EXTERNAL[key]
    existing = (
        session.query(Paper)
        .filter(
            Paper.source == "external",
            Paper.source_url == spec["source_url"],
        )
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
        )
    )
    return result.paper


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
            "s": "0-100"
            if direction == "higher_is_better" and name.startswith("AUC")
            else "unbounded",
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


def ensure_source_paper(session, spec: dict) -> Paper | None:
    source_kind = spec.get("source_kind")
    source_key = spec.get("source_key")
    if not source_kind or not source_key:
        return None
    if source_kind == "arxiv":
        raise RuntimeError("arxiv source papers must be resolved asynchronously")
    return ensure_external_paper(session, source_key)


def ensure_dataset_row(
    session,
    task_id: int,
    spec: dict,
    source_paper: Paper | None,
) -> int:
    slug = spec["slug"]
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": slug},
    ).first()

    if row:
        dataset_id = int(row[0])
    else:
        if source_paper is None:
            raise RuntimeError(f"Cannot create dataset {slug!r} without source paper")
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
                modalities=spec.get("modalities", ["Images"]),
            )
        )
        dataset_id = int(created.id)
        logger.info("Created dataset %r (id=%s)", spec["name"], dataset_id)

    if source_paper is not None:
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
    if featured_rank is None:
        session.execute(
            text(
                "INSERT INTO task_datasets (task_id, dataset_id, supports_harness) "
                "VALUES (:t, :d, FALSE) "
                "ON CONFLICT (task_id, dataset_id) DO NOTHING"
            ),
            {"t": task_id, "d": dataset_id},
        )
        return

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
            source_paper: Paper | None = None
            if spec.get("source_kind") == "arxiv":
                source_paper = arxiv_papers[spec["source_key"]]
            elif spec.get("source_kind") == "external":
                source_paper = ensure_external_paper(session, spec["source_key"])

            dataset_id = ensure_dataset_row(session, task_id, spec, source_paper)
            wire_task_dataset(session, task_id, dataset_id, spec.get("featured_rank"))
            linked_metrics = wire_metrics(
                session, task_id, dataset_id, spec["metrics"], metric_ids
            )
            if source_paper is not None:
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
        logger.info("Wave 1 3D understanding benchmarks wired successfully.")
        for line in report:
            logger.info("  %s", line)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
