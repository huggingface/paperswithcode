#!/usr/bin/env python3
"""Add Face Verification benchmarks (legacy PwC slugs) and ViT-8R evals for 2606.12036.

Legacy PwC had face-verification-on-* leaderboards for all seven benchmarks reported
in the paper, but none were mapped in our DB. This script creates the task,
benchmarks, metrics, indexes the source paper, and imports benchmark-wise best
ViT-8R rows from Table 2 (tab:sota_table) in the arXiv source.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/import_vit8r_face_verification_evals.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.taxonomy import TaskCreateRequest
from backend.models.database import Author, Dataset as DBDataset, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOURCE_ARXIV = "2606.12036"
GITHUB_URL = "https://github.com/TaharChettaoui/ViT-FR-Registers"
VISION_AREA_ID = 1
ACCURACY_METRIC_ID = 18
TAR_FAR_1E4 = "TAR @ FAR=1e-4"

BENCHMARKS = [
    {
        "name": "LFW",
        "slug": "lfw",
        "full_name": "Labeled Faces in the Wild",
        "homepage": "http://vis-www.cs.umass.edu/lfw/",
        "description": (
            "LFW contains 13,233 web-collected face images from 5,749 identities. "
            "The standard protocol reports verification accuracy on 6,000 face pairs."
        ),
        "short_description": "Classic unconstrained face verification benchmark (6k pairs).",
        "introduced_year": 2007,
        "metric_id": ACCURACY_METRIC_ID,
        "source_kind": "external",
        "source_url": "http://vis-www.cs.umass.edu/lfw/lfw.pdf",
        "external_title": "Labeled Faces in the Wild: A Database for Studying Face Recognition in Unconstrained Environments",
        "external_abstract": (
            "Face recognition has reached an unprecedented level of accuracy in recent "
            "years, but robust face recognition in unconstrained environments remains "
            "challenging. Labeled Faces in the Wild provides a database of face "
            "photographs designed for studying unconstrained face recognition."
        ),
        "external_authors": [
            "Gary B. Huang",
            "Manu Ramesh",
            "Tamara Berg",
            "Erik Learned-Miller",
        ],
        "external_date": date(2007, 10, 1),
    },
    {
        "name": "CFP-FP",
        "slug": "cfp-fp",
        "full_name": "Celebrities in Frontal-Profile (CFP-FP)",
        "homepage": "http://www.cfpw.io/",
        "description": (
            "CFP-FP evaluates frontal-profile face verification with 500 subjects and "
            "7,000 images split into frontal and profile views."
        ),
        "short_description": "Frontal-profile celebrity face verification benchmark.",
        "introduced_year": 2016,
        "metric_id": ACCURACY_METRIC_ID,
        "source_kind": "arxiv",
        "source_arxiv": "1511.07047",
    },
    {
        "name": "AgeDB-30",
        "slug": "agedb-30",
        "full_name": "AgeDB-30",
        "homepage": "https://ibug.doc.ic.ac.uk/resources/agedb/",
        "description": (
            "AgeDB-30 is the official AgeDB verification protocol with a 30-year minimum "
            "age gap between positive pairs."
        ),
        "short_description": "Age-invariant face verification with 30+ year age gaps.",
        "introduced_year": 2017,
        "metric_id": ACCURACY_METRIC_ID,
        "source_kind": "arxiv",
        "source_arxiv": "1707.02139",
    },
    {
        "name": "CALFW",
        "slug": "calfw",
        "full_name": "Cross-Age LFW",
        "homepage": "http://whdeng.cn/CALFW/index.html",
        "description": (
            "CALFW extends LFW with cross-age positive pairs to stress age-invariant "
            "face verification under the standard 6,000-pair protocol."
        ),
        "short_description": "Cross-age renovation of LFW for verification.",
        "introduced_year": 2017,
        "metric_id": ACCURACY_METRIC_ID,
        "source_kind": "arxiv",
        "source_arxiv": "1708.08197",
    },
    {
        "name": "CPLFW",
        "slug": "cplfw",
        "full_name": "Cross-Pose LFW",
        "homepage": "http://whdeng.cn/CPLFW/index.html",
        "description": (
            "CPLFW extends LFW with cross-pose positive pairs to evaluate pose-robust "
            "face verification under the standard 6,000-pair protocol."
        ),
        "short_description": "Cross-pose renovation of LFW for verification.",
        "introduced_year": 2019,
        "metric_id": ACCURACY_METRIC_ID,
        "source_kind": "arxiv",
        "source_arxiv": "1901.03454",
    },
    {
        "name": "IJB-B",
        "slug": "ijb-b",
        "full_name": "IARPA Janus Benchmark-B",
        "homepage": "https://www.nist.gov/programs-projects/face-challenges",
        "description": (
            "IJB-B is a template-based unconstrained face benchmark with 1,845 subjects, "
            "11,754 images, and 7,011 videos for 1:1 verification and 1:N identification."
        ),
        "short_description": "Large-scale template-based face verification benchmark.",
        "introduced_year": 2017,
        "metric_id": None,
        "source_kind": "arxiv",
        "source_arxiv": "1812.04058",
    },
    {
        "name": "IJB-C",
        "slug": "ijb-c",
        "full_name": "IARPA Janus Benchmark-C",
        "homepage": "https://www.nist.gov/programs-projects/face-challenges",
        "description": (
            "IJB-C extends IJB-A with about 138,000 face images and 11,000 videos for "
            "large-scale unconstrained face verification."
        ),
        "short_description": "Large-scale video/image face verification benchmark.",
        "introduced_year": 2018,
        "metric_id": None,
        "source_kind": "arxiv",
        "source_arxiv": "1804.10275",
    },
]

# Benchmark-wise best ViT-8R scores from tab:sota_table (paper body).
EVALS = [
    {
        "dataset_slug": "lfw",
        "score": "99.83",
        "metric": "Accuracy",
        "methodology": (
            "Verification accuracy (%); MS1MV3 training; official protocol; "
            "Table 2 (tab:sota_table) in arXiv:2606.12036."
        ),
    },
    {
        "dataset_slug": "cfp-fp",
        "score": "99.17",
        "metric": "Accuracy",
        "methodology": (
            "Verification accuracy (%); MS1MV3 training; official protocol; "
            "Table 2 (tab:sota_table) in arXiv:2606.12036."
        ),
    },
    {
        "dataset_slug": "agedb-30",
        "score": "98.35",
        "metric": "Accuracy",
        "methodology": (
            "Verification accuracy (%); MS1MV3 training; AgeDB-30 protocol; "
            "Table 2 (tab:sota_table) in arXiv:2606.12036."
        ),
    },
    {
        "dataset_slug": "calfw",
        "score": "96.20",
        "metric": "Accuracy",
        "methodology": (
            "Verification accuracy (%); MS1MV2 training (benchmark-wise best over "
            "MS1MV2/MS1MV3/WebFace4M rows); Table 2 (tab:sota_table) in arXiv:2606.12036."
        ),
    },
    {
        "dataset_slug": "cplfw",
        "score": "94.68",
        "metric": "Accuracy",
        "methodology": (
            "Verification accuracy (%); MS1MV3 training; official protocol; "
            "Table 2 (tab:sota_table) in arXiv:2606.12036."
        ),
    },
    {
        "dataset_slug": "ijb-b",
        "score": "96.11",
        "metric": TAR_FAR_1E4,
        "methodology": (
            "TAR at FAR=1e-4 (%); MS1MV3 training; official 1:1 mixed verification "
            "protocol; Table 2 (tab:sota_table) in arXiv:2606.12036."
        ),
    },
    {
        "dataset_slug": "ijb-c",
        "score": "97.37",
        "metric": TAR_FAR_1E4,
        "methodology": (
            "TAR at FAR=1e-4 (%); MS1MV3 training; official 1:1 mixed verification "
            "protocol; Table 2 (tab:sota_table) in arXiv:2606.12036."
        ),
    },
]

MODEL_NAME = "ViT-8R"
NUM_PARAMETERS = 113_838_000


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
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )

    paper_service = PaperService(session)
    paper_id = paper_service.add_paper(
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
    if not paper_id:
        existing = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
            .first()
        )
        if existing:
            return existing
        raise RuntimeError(f"Failed to create paper row for {arxiv_id}")

    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Created paper {paper_id} but could not reload it")

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

    logger.info("Imported arXiv paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def ensure_external_paper(session, spec: dict) -> Paper:
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
            title=spec["external_title"],
            abstract=spec["external_abstract"],
            authors=spec.get("external_authors"),
            date_published=spec.get("external_date"),
        )
    )
    paper = session.query(Paper).filter(Paper.id == int(result.paper.id)).one()
    logger.info("Created external paper for %s (id=%s)", spec["name"], paper.id)
    return paper


def paper_url(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def ensure_task(session) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = 'face-verification'")
    ).first()
    if row:
        return int(row[0])

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name="Face Verification",
            description=(
                "Determine whether two face images belong to the same identity under "
                "unconstrained in-the-wild settings."
            ),
            keywords="face verification,face recognition,lfw,ijb",
            area_id=VISION_AREA_ID,
        )
    )
    logger.info("Created Face Verification task id=%s", task.id)
    return int(task.id)


def ensure_tar_metric(session) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"),
        {"name": TAR_FAR_1E4},
    ).first()
    if row:
        return int(row[0])

    row = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (
                :name,
                'higher_is_better',
                'True Acceptance Rate at FAR=1e-4',
                'percent',
                'TAR reported at false acceptance rate 1e-4 on IJB verification protocols.'
            )
            RETURNING id
            """
        ),
        {"name": TAR_FAR_1E4},
    ).first()
    logger.info("Created metric %r id=%s", TAR_FAR_1E4, row[0])
    return int(row[0])


def ensure_dataset(session, spec: dict, source_paper: Paper) -> DBDataset:
    native = paper_url(source_paper)
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == spec["slug"]).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name=spec["name"],
            slug=spec["slug"],
            full_name=spec["full_name"],
            description=spec["description"],
            short_description=spec["short_description"],
            homepage=spec["homepage"],
            paper_url=native,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_year=spec["introduced_year"],
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
    else:
        dataset.full_name = spec["full_name"]
        dataset.description = spec["description"]
        dataset.short_description = spec["short_description"]
        dataset.homepage = spec["homepage"]
        dataset.paper_url = native
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = dataset.introduced_year or spec["introduced_year"]
        session.flush()
        logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def link_task_dataset(session, task_id: int, dataset_id: int) -> None:
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


def link_metric(session, task_id: int, dataset_id: int, metric_id: int) -> None:
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


def tag_paper_task(session, paper_id: int, task_id: int) -> None:
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


async def main() -> None:
    with db_manager.session_local() as session:
        task_id = ensure_task(session)
        tar_metric_id = ensure_tar_metric(session)
        dataset_by_slug: dict[str, DBDataset] = {}

        for spec in BENCHMARKS:
            if spec["source_kind"] == "arxiv":
                source_paper = await ensure_arxiv_paper(session, spec["source_arxiv"])
            else:
                source_paper = ensure_external_paper(session, spec)

            metric_id = spec["metric_id"] or tar_metric_id
            dataset = ensure_dataset(session, spec, source_paper)
            link_task_dataset(session, task_id, dataset.id)
            link_metric(session, task_id, dataset.id, metric_id)
            tag_paper_task(session, source_paper.id, task_id)
            dataset_by_slug[spec["slug"]] = dataset

        source_paper = await ensure_arxiv_paper(session, SOURCE_ARXIV)
        tag_paper_task(session, source_paper.id, task_id)

        eval_service = EvaluationService(session)
        created = 0
        for row in EVALS:
            dataset = dataset_by_slug[row["dataset_slug"]]
            existing = session.execute(
                text(
                    """
                    SELECT id FROM evaluations
                    WHERE paper_id = :paper_id
                      AND task_id = :task_id
                      AND dataset_id = :dataset_id
                      AND model_name = :model_name
                      AND COALESCE(harness, '') = ''
                      AND best_metric = :best_metric
                    """
                ),
                {
                    "paper_id": source_paper.id,
                    "task_id": task_id,
                    "dataset_id": dataset.id,
                    "model_name": MODEL_NAME,
                    "best_metric": row["metric"],
                },
            ).first()
            if existing:
                logger.info("Skip existing eval for %s", dataset.name)
                continue

            eval_service.create_evaluation(
                paper_id=source_paper.id,
                task_id=task_id,
                dataset_id=dataset.id,
                model_name=MODEL_NAME,
                methodology=row["methodology"],
                metrics={row["metric"]: row["score"]},
                best_metric=row["metric"],
                num_parameters=NUM_PARAMETERS,
                is_open=True,
            )
            created += 1
            logger.info(
                "Added eval %s %s=%s on dataset_id=%s",
                MODEL_NAME,
                row["metric"],
                row["score"],
                dataset.id,
            )

        session.commit()
        logger.info(
            "Done: paper_id=%s task_id=%s eval_rows_added=%s",
            source_paper.id,
            task_id,
            created,
        )
        print(f"PAPER_URL=https://paperswithcode.co/paper/{SOURCE_ARXIV}")


if __name__ == "__main__":
    asyncio.run(main())
