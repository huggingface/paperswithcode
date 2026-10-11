#!/usr/bin/env python3
"""Add Object Counting task and CountGD++ evaluation benchmarks."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.taxonomy import TaskCreateRequest
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Paper
from backend.services.dataset_service import DatasetService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.task_service import TaskService
from backend.utils.slug_utils import slugify

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VISION_AREA_ID = 1
MAE_METRIC_ID = 6
RMSE_METRIC_ID = 8
AP_METRIC_ID = 124
AP50_METRIC_ID = 13

TASK_NAME = "Object Counting"
TASK_SLUG = "object-counting"

SOURCE_PAPERS = {
    "fscd147": {
        "arxiv_id": "2207.10988",
        "source_url": "https://arxiv.org/abs/2207.10988",
        "title": "Few-shot Object Counting and Detection",
        "abstract": (
            "Introduces FSCD-147, extending FSC-147 with bounding-box annotations on "
            "validation and test splits for joint few-shot counting and detection."
        ),
        "authors": ["Thanh Nguyen", "Chau Pham", "Khoi Nguyen", "Minh Hoai"],
        "date_published": date(2022, 7, 22),
    },
    "fsc147": {
        "arxiv_id": "2104.08391",
        "source_url": "https://arxiv.org/abs/2104.08391",
        "title": "Learning To Count Everything",
        "abstract": (
            "Introduces FSC-147, a dataset of 147 object categories with over 6000 "
            "images for few-shot open-world object counting."
        ),
        "authors": ["Vires Ranjan", "Udbhav Sharma", "Thu Nguyen", "Minh Hoai"],
        "date_published": date(2021, 4, 16),
    },
    "shanghaitech": {
        "source_url": "https://openaccess.thecvf.com/content_cvpr_2016/papers/Zhang_Single-Image_Crowd_Counting_CVPR_2016_paper.pdf",
        "title": "Single-Image Crowd Counting via Multi-Column Convolutional Neural Network",
        "abstract": (
            "Introduces the ShanghaiTech crowd counting dataset with Parts A and B, "
            "widely used for crowd counting evaluation."
        ),
        "authors": [
            "Yingying Zhang",
            "Desen Zhou",
            "Siqin Chen",
            "Shenghua Gao",
            "Yi Ma",
        ],
        "date_published": date(2016, 6, 1),
    },
    "omnicount": {
        "source_url": "https://ojs.aaai.org/index.php/AAAI/article/view/33635",
        "title": "OmniCount: Multi-Label Object Counting with Semantic-Geometric Priors",
        "abstract": (
            "Introduces OmniCount-191, a multi-label object counting benchmark with "
            "semantic-geometric priors, including a Fruits test subset."
        ),
        "authors": [
            "Anindya Mondal",
            "Sauradip Nag",
            "Xiatian Zhu",
            "Anjan Dutta",
        ],
        "date_published": date(2025, 2, 1),
    },
    "videocount": {
        "arxiv_id": "2506.15368",
        "source_url": "https://arxiv.org/abs/2506.15368",
        "title": "Open-world Object Counting in Videos",
        "abstract": (
            "Introduces VideoCount, including the Science-Count (Crystals) benchmark "
            "for counting dynamically forming crystals in x-ray videos."
        ),
        "authors": ["Niki Amini-Naieni", "Andrew Zisserman"],
        "date_published": date(2025, 6, 18),
    },
    "pairtally": {
        "arxiv_id": "2509.13939",
        "source_url": "https://arxiv.org/abs/2509.13939",
        "title": "Can Current AI Models Count What We Mean, Not What They See? A Benchmark and Systematic Evaluation",
        "abstract": (
            "Introduces PairTally, a fine-grained object counting benchmark with dense "
            "mixed objects and subtle visual differences."
        ),
        "authors": ["Gia Khanh Nguyen", "Yifeng Huang", "Minh Hoai"],
        "date_published": date(2025, 11, 1),
    },
    "blood_cell": {
        "source_url": "https://www.kaggle.com/datasets/draaslan/blood-cell-detection-dataset",
        "title": "Blood Cell Detection Dataset",
        "abstract": (
            "Microscopic blood smear images with bounding-box annotations for red and "
            "white blood cells, used for multi-class counting evaluation."
        ),
        "authors": ["Abdüssamet Aslan"],
        "date_published": date(2024, 1, 1),
    },
}

BENCHMARKS = [
    {
        "name": "FSC-147",
        "full_name": "Few-Shot Counting 147",
        "description": (
            "FSC-147 is a dataset of 147 object categories with over 6000 images for "
            "few-shot open-world object counting. Each instance is annotated with a dot "
            "at its center; three exemplar instances per image also have bounding boxes."
        ),
        "short_description": "Few-shot open-world object counting benchmark.",
        "homepage": "https://github.com/cvlab-stonybrook/LearningToCountEverything",
        "introduced_date": date(2021, 4, 16),
        "source_key": "fsc147",
        "metrics": [MAE_METRIC_ID, RMSE_METRIC_ID],
    },
    {
        "name": "FSCD-147",
        "full_name": "Few-Shot Counting and Detection 147",
        "description": (
            "FSCD-147 adds bounding boxes to the FSC-147 validation and test splits for "
            "joint open-world counting and detection evaluation. Use this benchmark for "
            "methods that output instance bounding boxes."
        ),
        "short_description": "FSC-147 val/test with boxes for counting-and-detection methods.",
        "homepage": "https://github.com/vinairesearch/counting-detr",
        "introduced_date": date(2022, 7, 22),
        "source_key": "fscd147",
        "metrics": [MAE_METRIC_ID, RMSE_METRIC_ID, AP_METRIC_ID, AP50_METRIC_ID],
    },
    {
        "name": "ShanghaiTech Part A",
        "full_name": "ShanghaiTech Crowd Counting Part A",
        "description": (
            "Part A of ShanghaiTech contains 482 crowd images with 33-3139 people per "
            "image, commonly used for crowd counting MAE/RMSE evaluation."
        ),
        "short_description": "ShanghaiTech Part A crowd counting benchmark.",
        "homepage": "https://www.kaggle.com/datasets/tthle/shanghaitech",
        "introduced_date": date(2016, 6, 1),
        "source_key": "shanghaitech",
        "metrics": [MAE_METRIC_ID, RMSE_METRIC_ID],
    },
    {
        "name": "ShanghaiTech Part B",
        "full_name": "ShanghaiTech Crowd Counting Part B",
        "description": (
            "Part B of ShanghaiTech contains 716 street-scene crowd images with 9-578 "
            "people per image."
        ),
        "short_description": "ShanghaiTech Part B crowd counting benchmark.",
        "homepage": "https://www.kaggle.com/datasets/tthle/shanghaitech",
        "introduced_date": date(2016, 6, 1),
        "source_key": "shanghaitech",
        "metrics": [MAE_METRIC_ID, RMSE_METRIC_ID],
    },
    {
        "name": "OmniCount (Fruits)",
        "full_name": "OmniCount-191 Fruits Subset",
        "description": (
            "Fruits test subset of OmniCount-191 with 303 images and eight fruit "
            "categories annotated with bounding boxes."
        ),
        "short_description": "OmniCount Fruits multi-label counting benchmark.",
        "homepage": "https://github.com/aimondal/OmniCount",
        "introduced_date": date(2025, 2, 1),
        "source_key": "omnicount",
        "metrics": [MAE_METRIC_ID, RMSE_METRIC_ID, AP_METRIC_ID, AP50_METRIC_ID],
    },
    {
        "name": "Blood Cell Detection",
        "full_name": "Blood Cell Detection",
        "description": (
            "100 peripheral blood smear images with red and white blood cell bounding "
            "boxes for multi-class counting evaluation."
        ),
        "short_description": "Microscopic blood cell counting benchmark.",
        "homepage": "https://www.kaggle.com/datasets/draaslan/blood-cell-detection-dataset",
        "introduced_date": date(2024, 1, 1),
        "source_key": "blood_cell",
        "metrics": [MAE_METRIC_ID, RMSE_METRIC_ID, AP_METRIC_ID, AP50_METRIC_ID],
    },
    {
        "name": "VideoCount (Crystals)",
        "full_name": "VideoCount Science-Count (Crystals)",
        "description": (
            "Science-Count (Crystals) subset of VideoCount with x-ray videos of "
            "rapidly forming crystals for video-based counting."
        ),
        "short_description": "Dynamic crystal video counting benchmark.",
        "homepage": "https://github.com/niki-amini-naeni/CountVid",
        "introduced_date": date(2025, 6, 18),
        "source_key": "videocount",
        "metrics": [MAE_METRIC_ID, RMSE_METRIC_ID],
    },
    {
        "name": "PairTally",
        "full_name": "PairTally",
        "description": (
            "681 dense images testing fine-grained object counting with subtle "
            "differences between mixed object categories."
        ),
        "short_description": "Fine-grained mixed-object counting benchmark.",
        "homepage": "https://github.com/bbvisual/PairTally_Benchmark",
        "introduced_date": date(2025, 11, 1),
        "source_key": "pairtally",
        "metrics": [MAE_METRIC_ID, RMSE_METRIC_ID],
    },
]


def ensure_source_paper(session, key: str) -> Paper:
    spec = SOURCE_PAPERS[key]
    arxiv_id = spec.get("arxiv_id")
    if arxiv_id:
        existing = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
            .first()
        )
        if existing:
            return existing

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
        )
    )
    return result.paper


def paper_url_for(source_paper: Paper) -> str:
    if source_paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{source_paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{source_paper.id}"


def ensure_task(session) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"), {"slug": TASK_SLUG}
    ).first()
    if row:
        task_id = int(row[0])
    else:
        task = TaskService(session).create_task(
            TaskCreateRequest(
                name=TASK_NAME,
                description=(
                    "Count object instances in images or videos when the target "
                    "category is specified at test time via text and/or visual "
                    "exemplars. Related to [Crowd Counting](/tasks/crowd-counting) "
                    "for people-only settings and [Visual Question Answering]"
                    "(/tasks/visual-question-answering) for counting questions."
                ),
                keywords=(
                    "object counting,open-world counting,few-shot counting,"
                    "class-agnostic counting,visual counting,open-vocabulary counting"
                ),
                area_id=VISION_AREA_ID,
            )
        )
        task_id = int(task.id)

    return task_id


def ensure_dataset(session, spec: dict, task_id: int, source_paper: Paper) -> int:
    slug = slugify(spec["name"])
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": slug}
    ).first()
    native_paper_url = paper_url_for(source_paper)

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
                paper_url=native_paper_url,
                introduced_date=spec["introduced_date"],
                task_ids=[task_id],
                languages=["English"],
                modalities=["Images"] if "Video" not in spec["name"] else ["Videos"],
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
            "paper_url": native_paper_url,
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
        {"t": task_id, "d": dataset_id},
    )
    for metric_id in spec["metrics"]:
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
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:p, :t, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"p": source_paper.id, "t": task_id},
    )
    return dataset_id


def main() -> None:
    session = db_manager.session_local()
    try:
        task_id = ensure_task(session)
        logger.info("Object Counting task id=%s", task_id)
        for spec in BENCHMARKS:
            source_paper = ensure_source_paper(session, spec["source_key"])
            dataset_id = ensure_dataset(session, spec, task_id, source_paper)
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
