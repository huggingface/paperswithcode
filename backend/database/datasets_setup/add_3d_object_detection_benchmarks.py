#!/usr/bin/env python3
"""Wire 3D object detection benchmarks (nuScenes, Waymo, KITTI, ScanNet).

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_3d_object_detection_benchmarks.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.api import TaskCreateRequest
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Paper
from backend.services.arxiv_service import ArxivService
from backend.services.dataset_service import DatasetService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VISION_AREA_ID = 1
MAP_METRIC_ID = 11
AP50_METRIC_ID = 13

TASK = {
    "name": "3D object detection",
    "description": (
        "Identify and localize objects in 3D space from point clouds, depth maps, "
        "multi-view images, or fused sensor data. Core to autonomous driving, "
        "robotics, and augmented reality."
    ),
    "keywords": "3D object detection",
}

SOURCE_ARXIV = {
    "nuscenes": "1903.11027",
    "waymo": "1912.04838",
    "scannet": "1702.04405",
}

SOURCE_EXTERNAL = {
    "kitti": {
        "source_url": "https://www.cvlibs.net/publications/Geiger2012CVPR.pdf",
        "title": "Are we ready for autonomous driving? The KITTI vision benchmark suite",
        "abstract": (
            "Autonomous driving requires perception modules that provide a complete "
            "understanding of the environment. This paper describes the KITTI vision "
            "benchmark suite, comprising stereo, optical flow, visual odometry, 3D object "
            "detection, and 3D tracking benchmarks. The 3D object detection benchmark "
            "evaluates detectors on LiDAR point clouds and images for cars, pedestrians, "
            "and cyclists with Easy, Moderate, and Hard difficulty splits."
        ),
        "authors": ["Andreas Geiger", "Philip Lenz", "Raquel Urtasun"],
        "date_published": date(2012, 6, 16),
    },
}

BENCHMARKS = [
    {
        "slug": "nuscenes",
        "existing": True,
        "source_key": "nuscenes",
        "source_kind": "arxiv",
        "metrics": ["NDS", "mAP"],
        "description": (
            "Large-scale autonomous driving dataset with 3D bounding boxes for 1,000 scenes "
            "collected in Boston and Singapore. Each scene is 20 seconds long and annotated "
            "at 2Hz, yielding 28,130 training, 6,019 validation, and 6,008 test samples. "
            "The sensor suite includes a 32-beam LiDAR, 6 cameras, and radars with full "
            "360° coverage. The 3D object detection challenge evaluates 10 classes: cars, "
            "trucks, buses, trailers, construction vehicles, pedestrians, motorcycles, "
            "bicycles, traffic cones, and barriers."
        ),
        "short_description": (
            "Large-scale autonomous driving dataset with multimodal sensors and 3D boxes."
        ),
        "introduced_date": date(2019, 3, 26),
    },
    {
        "slug": "waymo-open-dataset",
        "existing": True,
        "source_key": "waymo",
        "source_kind": "arxiv",
        "metrics": ["mAPH", "mAP"],
    },
    {
        "slug": "scannet",
        "existing": True,
        "source_key": "scannet",
        "source_kind": "arxiv",
        "metrics": ["mAP", "AP50"],
    },
    {
        "name": "KITTI 3D Object Detection",
        "slug": "kitti-3d-object-detection",
        "full_name": "KITTI 3D Object Detection Benchmark",
        "description": (
            "Classic outdoor 3D object detection benchmark from the KITTI Vision Benchmark "
            "Suite. Evaluates 3D bounding-box detectors on Velodyne LiDAR point clouds and "
            "stereo/RGB images for cars, pedestrians, and cyclists. Results are reported "
            "with bird's-eye-view AP at IoU 0.7 (cars) or 0.5 (pedestrians/cyclists) across "
            "Easy, Moderate, and Hard difficulty splits on the validation set."
        ),
        "short_description": (
            "Outdoor LiDAR/RGB 3D detection benchmark for cars, pedestrians, and cyclists."
        ),
        "homepage": "http://www.cvlibs.net/datasets/kitti/eval_object.php?obj_benchmark=3d",
        "introduced_date": date(2012, 6, 16),
        "source_key": "kitti",
        "source_kind": "external",
        "metrics": ["mAP"],
        "modalities": ["Images", "LiDAR"],
    },
]

NEW_METRICS = [
    (
        "mAPH",
        "higher_is_better",
        "Mean Average Precision weighted by Heading",
        "0-100",
        "Waymo Open Dataset 3D detection metric combining detection AP with heading accuracy.",
    ),
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


def ensure_task(session) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = '3d-object-detection'"),
    ).first()
    if row:
        return int(row[0])

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name=TASK["name"],
            description=TASK["description"],
            keywords=TASK["keywords"],
            area_id=VISION_AREA_ID,
        )
    )
    return int(task.id)


def ensure_metric(
    session,
    name: str,
    direction: str,
    full_name: str,
    scale: str,
    description: str,
) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"),
        {"n": name},
    ).first()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:n, :d, :full, :scale, :desc)
            RETURNING id
            """
        ),
        {
            "n": name,
            "d": direction,
            "full": full_name,
            "scale": scale,
            "desc": description,
        },
    ).scalar_one()
    logger.info("Created metric %r (id=%s)", name, metric_id)
    return int(metric_id)


def ensure_metric_ids(session) -> dict[str, int]:
    metric_ids = {
        "mAP": MAP_METRIC_ID,
        "AP50": AP50_METRIC_ID,
        "NDS": ensure_metric(
            session,
            "NDS",
            "higher_is_better",
            "nuScenes Detection Score",
            "0-1",
            "Official nuScenes 3D detection leaderboard score combining mAP and attribute errors.",
        ),
    }
    for name, direction, full_name, scale, description in NEW_METRICS:
        metric_ids[name] = ensure_metric(
            session, name, direction, full_name, scale, description
        )
    return metric_ids


def wire_task_dataset(session, task_id: int, dataset_id: int) -> None:
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
        name = spec.get("name") or row[1]
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
                modalities=spec.get("modalities", ["Images", "3D", "LiDAR"]),
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

        external_papers: dict[str, Paper] = {}
        for key in SOURCE_EXTERNAL:
            external_papers[key] = ensure_external_paper(session, key)

        task_id = ensure_task(session)
        metric_ids = ensure_metric_ids(session)
        logger.info("3d-object-detection task_id=%s", task_id)

        for spec in BENCHMARKS:
            source_kind = spec["source_kind"]
            source_key = spec["source_key"]
            if source_kind == "arxiv":
                source_paper = arxiv_papers[source_key]
            else:
                source_paper = external_papers[source_key]

            dataset_id = ensure_dataset(session, task_id, spec, source_paper)
            wire_task_dataset(session, task_id, dataset_id)
            for metric_name in spec["metrics"]:
                wire_metric(session, task_id, dataset_id, metric_ids[metric_name])
            promote_paper_task(session, source_paper.id, task_id)

            report.append(
                f"{spec['slug']} -> dataset_id={dataset_id} "
                f"source={paper_url_for(source_paper)} "
                f"metrics={spec['metrics']}"
            )

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
