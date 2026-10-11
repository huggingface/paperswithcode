#!/usr/bin/env python3
"""Wire 3D semantic / instance segmentation benchmarks for Volt-style leaderboards.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_3d_segmentation_benchmarks.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.taxonomy import TaskCreateRequest
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Paper
from backend.services.arxiv_service import ArxivService
from backend.services.dataset_service import DatasetService
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VISION_AREA_ID = 1
MIOU_METRIC_ID = 31
AP50_METRIC_ID = 13

SEM_TASK = {
    "name": "3D semantic segmentation",
    "slug": "3d-semantic-segmentation",
    "description": (
        "Predict per-point or per-voxel semantic class labels for 3D indoor and "
        "outdoor scene scans."
    ),
    "keywords": "3d semantic segmentation,point cloud semantic segmentation,lidar segmentation",
}

INST_TASK = {
    "name": "3D instance segmentation",
    "slug": "3d-instance-segmentation",
    "description": (
        "Segment and classify individual object instances in 3D scene scans."
    ),
    "keywords": "3d instance segmentation,point cloud instance segmentation",
}

SOURCE_ARXIV = {
    "scannet": "1702.04405",
    "scannet200": "2204.07761",
    "scannetpp": "2308.11417",
    "nuscenes": "1903.11027",
    "semantickitti": "1904.01416",
    "waymo": "1912.04838",
}

SEM_BENCHMARKS = [
    {
        "slug": "scannet",
        "existing": True,
        "featured_rank": 1,
        "source_key": "scannet",
    },
    {
        "name": "ScanNet200",
        "slug": "scannet200",
        "full_name": "ScanNet200",
        "description": (
            "200-class 3D semantic segmentation benchmark built on ScanNet scans, "
            "capturing long-tail indoor object categories."
        ),
        "short_description": "200-class indoor 3D semantic segmentation on ScanNet scans.",
        "homepage": "http://kaldir.vc.in.tum.de/scannet_benchmark/",
        "introduced_date": date(2022, 3, 7),
        "source_key": "scannet200",
        "featured_rank": 2,
        "modalities": ["Images", "3D", "RGB-D"],
    },
    {
        "name": "ScanNet++",
        "slug": "scannet-plus-plus",
        "full_name": "ScanNet++",
        "description": (
            "High-fidelity indoor 3D reconstructions with dense semantic labels "
            "for 100 classes across 956 scenes."
        ),
        "short_description": "High-fidelity indoor 3D semantic segmentation benchmark.",
        "homepage": "https://kaldir.vc.in.tum.de/scannetpp_benchmark/",
        "introduced_date": date(2023, 8, 1),
        "source_key": "scannetpp",
        "featured_rank": 3,
        "modalities": ["Images", "3D", "RGB-D"],
    },
    {
        "name": "nuScenes",
        "slug": "nuscenes",
        "full_name": "nuScenes",
        "description": (
            "Large-scale autonomous driving dataset with LiDAR semantic segmentation "
            "labels for 16 outdoor classes across 1,000 scenes."
        ),
        "short_description": "Outdoor LiDAR semantic segmentation benchmark.",
        "homepage": "https://www.nuscenes.org/",
        "introduced_date": date(2020, 3, 1),
        "source_key": "nuscenes",
        "featured_rank": 4,
        "modalities": ["Images", "3D", "LiDAR"],
    },
    {
        "name": "SemanticKITTI",
        "slug": "semantickitti",
        "full_name": "SemanticKITTI",
        "description": (
            "Large-scale outdoor LiDAR semantic segmentation benchmark derived "
            "from the KITTI Vision Odometry sequences."
        ),
        "short_description": "Outdoor LiDAR semantic segmentation benchmark.",
        "homepage": "http://semantic-kitti.org/",
        "introduced_date": date(2019, 4, 3),
        "source_key": "semantickitti",
        "featured_rank": 5,
        "modalities": ["3D", "LiDAR"],
    },
    {
        "name": "Waymo Open Dataset",
        "slug": "waymo-open-dataset",
        "full_name": "Waymo Open Dataset",
        "description": (
            "Large-scale autonomous driving dataset with dense 64-beam LiDAR "
            "semantic segmentation labels for outdoor scenes."
        ),
        "short_description": "Outdoor LiDAR semantic segmentation on Waymo scenes.",
        "homepage": "https://waymo.com/open/",
        "introduced_date": date(2019, 12, 10),
        "source_key": "waymo",
        "featured_rank": 6,
        "modalities": ["3D", "LiDAR"],
    },
]

INST_BENCHMARKS = [
    {"slug": "scannet", "existing": True, "featured_rank": 1, "source_key": "scannet"},
    {
        "name": "ScanNet200",
        "slug": "scannet200",
        "existing": True,
        "featured_rank": 2,
        "source_key": "scannet200",
    },
]


def paper_url_for(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


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
    if paper is None:
        raise RuntimeError(f"Failed to load newly created paper {paper_id}")
    return paper


def ensure_task(session, spec: dict) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"),
        {"slug": spec["slug"]},
    ).first()
    if row:
        return int(row[0])

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name=spec["name"],
            description=spec["description"],
            keywords=spec["keywords"],
            area_id=VISION_AREA_ID,
        )
    )
    return int(task.id)


def wire_task_dataset(
    session, task_id: int, dataset_id: int, featured_rank: int | None
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, featured_rank, supports_harness)
            VALUES (:t, :d, :rank, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET featured_rank = COALESCE(EXCLUDED.featured_rank, task_datasets.featured_rank),
                supports_harness = FALSE
            """
        ),
        {"t": task_id, "d": dataset_id, "rank": featured_rank},
    )


def wire_metric(session, task_id: int, dataset_id: int, metric_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:t, :d, :m)
            ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
            """
        ),
        {"t": task_id, "d": dataset_id, "m": metric_id},
    )


def promote_paper_task(session, paper_id: int, task_id: int) -> None:
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


def ensure_dataset(session, task_id: int, spec: dict, source_paper: Paper) -> int:
    slug = spec["slug"]
    row = session.execute(
        text("SELECT id, name FROM datasets WHERE slug = :slug"),
        {"slug": slug},
    ).first()

    if row:
        dataset_id = int(row[0])
        name = spec.get("name_override") or spec.get("name") or row[1]
    else:
        name = spec.get("name") or slug.replace("-", " ").title()
        created = DatasetService(session).create_dataset(
            DatasetCreateRequest(
                name=name,
                full_name=spec.get("full_name", name),
                description=spec["description"],
                short_description=spec["short_description"],
                homepage=spec["homepage"],
                paper_url=paper_url_for(source_paper),
                introduced_date=spec["introduced_date"],
                task_ids=[task_id],
                modalities=spec.get("modalities", ["Images", "3D"]),
            )
        )
        dataset_id = int(created.id)
        logger.info("Created dataset %r (id=%s)", name, dataset_id)

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
            "title": source_paper.title,
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


async def main() -> None:
    session = db_manager.session_local()
    report: list[str] = []
    try:
        arxiv_papers: dict[str, Paper] = {}
        for key, arxiv_id in SOURCE_ARXIV.items():
            arxiv_papers[key] = await ensure_arxiv_paper(session, arxiv_id)
            logger.info(
                "Resolved %s -> paper id=%s arxiv=%s",
                key,
                arxiv_papers[key].id,
                arxiv_papers[key].arxiv_id,
            )

        sem_task_id = ensure_task(session, SEM_TASK)
        inst_task_id = ensure_task(session, INST_TASK)
        logger.info(
            "semantic task_id=%s instance task_id=%s", sem_task_id, inst_task_id
        )

        for spec in SEM_BENCHMARKS:
            source_paper = arxiv_papers[spec["source_key"]]
            dataset_id = ensure_dataset(session, sem_task_id, spec, source_paper)
            wire_task_dataset(
                session, sem_task_id, dataset_id, spec.get("featured_rank")
            )
            wire_metric(session, sem_task_id, dataset_id, MIOU_METRIC_ID)
            promote_paper_task(session, source_paper.id, sem_task_id)
            report.append(f"semantic/{spec['slug']} -> dataset_id={dataset_id}")

        for spec in INST_BENCHMARKS:
            source_paper = arxiv_papers[spec["source_key"]]
            dataset_id = ensure_dataset(session, inst_task_id, spec, source_paper)
            wire_task_dataset(
                session, inst_task_id, dataset_id, spec.get("featured_rank")
            )
            wire_metric(session, inst_task_id, dataset_id, AP50_METRIC_ID)
            promote_paper_task(session, source_paper.id, inst_task_id)
            report.append(f"instance/{spec['slug']} -> dataset_id={dataset_id}")

        session.commit()
        for line in report:
            logger.info("  %s", line)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
