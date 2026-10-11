#!/usr/bin/env python3
"""Add Scene Text Recognition task and standard STR benchmarks."""

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

GENERAL_AREA_ID = 3
ACCURACY_METRIC_ID = 18
TASK_NAME = "Scene Text Recognition"
TASK_SLUG = "scene-text-recognition"

SOURCE_PAPERS = {
    "ic13": {
        "source_url": "https://doi.org/10.1109/ICDAR.2013.221",
        "title": "ICDAR 2013 Robust Reading Competition",
        "abstract": (
            "Report on the ICDAR 2013 Robust Reading Competition, including focused "
            "scene text recognition tasks and datasets derived from natural-scene images."
        ),
        "authors": [
            "Dimosthenis Karatzas",
            "Faisal Shafait",
            "Seiichi Uchida",
            "Masakazu Iwamura",
            "Lluis Gomez-Bigorda",
            "Salvador Rusinol",
            "Joan Mas",
            "David Fernandez",
            "Joan Almazan",
            "Lluis de las Heras",
        ],
        "date_published": date(2013, 8, 1),
    },
    "svt": {
        "source_url": (
            "https://openaccess.thecvf.com/content/ICCV2011/papers/"
            "Wang_End-to-End_Scene_Text_Recognition_ICCV_2011_paper.pdf"
        ),
        "title": "End-to-end Scene Text Recognition",
        "abstract": (
            "Introduces the Street View Text dataset harvested from Google Street View "
            "and an end-to-end scene text recognition approach evaluated on cropped "
            "word images."
        ),
        "authors": ["Kai Wang", "Boris Babenko", "Serge Belongie"],
        "date_published": date(2011, 11, 6),
    },
    "iiit5k": {
        "source_url": (
            "https://britishmachinevisionassociation.github.io/bmvc/2012/BMVC-2012/"
            "papers/paper119/paper119.pdf"
        ),
        "title": "Scene Text Recognition using Higher Order Language Priors",
        "abstract": (
            "Introduces the IIIT 5K-Word dataset of 5,000 cropped word images from "
            "street scenes and digital sources for scene text recognition evaluation."
        ),
        "authors": ["Ankush Mishra", "Karteek Alahari", "C. V. Jawahar"],
        "date_published": date(2012, 9, 1),
    },
    "ic15": {
        "source_url": "https://doi.org/10.1109/ICDAR.2015.333",
        "title": "ICDAR 2015 Competition on Robust Reading",
        "abstract": (
            "Report on the ICDAR 2015 Robust Reading Competition, including incidental "
            "scene text recognition benchmarks widely used for cropped-word evaluation."
        ),
        "authors": [
            "Dimosthenis Karatzas",
            "Lluis Gomez-Bigorda",
            "Angela Nicolaou",
            "Suman K. Ghosh",
            "Andrew D. Bagdanov",
            "Masakazu Iwamura",
            "Jiri Matas",
            "Lukas Neumann",
            "Vijay Ramaseshan Chandrasekhar",
            "Shang Lu",
            "Faisal Shafait",
            "Seiichi Uchida",
            "Ernest Valveny",
        ],
        "date_published": date(2015, 8, 1),
    },
    "svtp": {
        "source_url": (
            "https://openaccess.thecvf.com/content_ICCV_2013/papers/"
            "Phan_Recognizing_Text_with_ICCV_2013_paper.pdf"
        ),
        "title": "Recognizing Text with Perspective Distortion in Natural Scenes",
        "abstract": (
            "Introduces the Street View Text-Perspective dataset of cropped words with "
            "perspective distortion for scene text recognition evaluation."
        ),
        "authors": [
            "Trung Quy Phan",
            "Palaiahnakote Shivakumara",
            "Shangxuan Tian",
            "Chew Lim Tan",
        ],
        "date_published": date(2013, 12, 1),
    },
    "cute80": {
        "source_url": "https://doi.org/10.1016/j.eswa.2014.06.024",
        "title": "A Robust Arbitrary Text Detection System for Natural Scene Images",
        "abstract": (
            "Introduces the CUTE80 dataset of curved scene-text images used for robust "
            "scene text recognition evaluation."
        ),
        "authors": [
            "Arief Risnumawan",
            "Palaiahnakote Shivakumara",
            "Chee Seng Chan",
            "Chew Lim Tan",
        ],
        "date_published": date(2014, 10, 1),
    },
}

BENCHMARKS = [
    {
        "name": "IC13",
        "full_name": "ICDAR 2013 (STR)",
        "description": (
            "Cropped-word scene text recognition benchmark derived from ICDAR 2013. "
            "MGP-STR and many STR papers evaluate on 857 alphanumeric test images "
            "after filtering non-alphanumeric or very short words."
        ),
        "short_description": (
            "ICDAR 2013 cropped-word recognition benchmark used in standard STR tables."
        ),
        "homepage": "https://rrc.cvc.uab.es/?ch=2",
        "introduced_date": date(2013, 8, 1),
        "source_key": "ic13",
        "featured_rank": 1,
        "modalities": ["Images"],
        "languages": ["English"],
    },
    {
        "name": "SVT",
        "full_name": "Street View Text",
        "description": (
            "Street View Text (SVT) contains 647 cropped word images harvested from "
            "Google Street View with high variability and often low resolution."
        ),
        "short_description": "647 cropped Street View word images for scene text recognition.",
        "homepage": "http://vision.ucsd.edu/~kai/svt/",
        "introduced_date": date(2011, 11, 6),
        "source_key": "svt",
        "featured_rank": 2,
        "modalities": ["Images"],
        "languages": ["English"],
    },
    {
        "name": "IIIT5K",
        "full_name": "IIIT 5K-Word",
        "description": (
            "IIIT5K contains 5,000 cropped word images (3,000 test) from street scenes "
            "and originally-digital images. Standard STR evaluation uses the test split "
            "without lexicon constraints."
        ),
        "short_description": "5,000 cropped word images from street scenes and digital text.",
        "homepage": (
            "https://cvit.iiit.ac.in/research/projects/cvit-projects/the-iiit-5k-word-dataset"
        ),
        "introduced_date": date(2012, 9, 1),
        "source_key": "iiit5k",
        "featured_rank": 3,
        "modalities": ["Images"],
        "languages": ["English"],
    },
    {
        "name": "IC15",
        "full_name": "ICDAR 2015 (STR)",
        "description": (
            "Cropped-word scene text recognition benchmark derived from ICDAR 2015 "
            "incidental text. Standard STR papers evaluate on 1,811 filtered test "
            "images excluding extremely distorted cases."
        ),
        "short_description": (
            "ICDAR 2015 cropped-word recognition benchmark for irregular scene text."
        ),
        "homepage": "https://rrc.cvc.uab.es/?ch=4",
        "introduced_date": date(2015, 8, 1),
        "source_key": "ic15",
        "featured_rank": 4,
        "modalities": ["Images"],
        "languages": ["English"],
    },
    {
        "name": "SVTP",
        "full_name": "Street View Text-Perspective",
        "description": (
            "SVTP contains 639 cropped word images collected from Google Street View "
            "with perspective distortion, widely used as an irregular-scene STR benchmark."
        ),
        "short_description": "639 perspective-distorted Street View word images.",
        "homepage": "http://cvit.dhv.rsu.edu.tw/go/home/dataset",
        "introduced_date": date(2013, 12, 1),
        "source_key": "svtp",
        "featured_rank": 5,
        "modalities": ["Images"],
        "languages": ["English"],
    },
    {
        "name": "CUTE80",
        "full_name": "CUTE80",
        "description": (
            "CUTE80 contains 288 curved cropped word images and is a standard irregular "
            "scene text recognition benchmark."
        ),
        "short_description": "288 curved cropped word images for scene text recognition.",
        "homepage": "https://github.com/mohtashim-nawaz/Cute80-Dataset",
        "introduced_date": date(2014, 10, 1),
        "source_key": "cute80",
        "featured_rank": 6,
        "modalities": ["Images"],
        "languages": ["English"],
    },
]


def ensure_source_paper(session, key: str) -> Paper:
    spec = SOURCE_PAPERS[key]
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


def ensure_task(session) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"), {"slug": TASK_SLUG}
    ).first()
    if row:
        return int(row[0])

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name=TASK_NAME,
            description=(
                "Recognize textual content from cropped natural-scene word images. "
                "Standard STR benchmarks include regular datasets such as IC13, SVT, "
                "and IIIT5K, plus irregular datasets such as IC15, SVTP, and CUTE80."
            ),
            keywords=(
                "scene text recognition,STR,text recognition,cropped word recognition"
            ),
            area_id=GENERAL_AREA_ID,
        )
    )
    return int(task.id)


def ensure_dataset(session, spec: dict, task_id: int, source_paper: Paper) -> int:
    slug = slugify(spec["name"])
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": slug}
    ).first()
    paper_url = f"https://paperswithcode.co/paper/{source_paper.id}"

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
                paper_url=paper_url,
                introduced_date=spec["introduced_date"],
                task_ids=[task_id],
                languages=spec["languages"],
                modalities=spec["modalities"],
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
            "paper_url": paper_url,
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
            INSERT INTO task_datasets (task_id, dataset_id, featured_rank, supports_harness)
            VALUES (:t, :d, :rank, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET featured_rank = EXCLUDED.featured_rank,
                supports_harness = FALSE
            """
        ),
        {"t": task_id, "d": dataset_id, "rank": spec["featured_rank"]},
    )
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:t, :d, :m)
            ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
            """
        ),
        {"t": task_id, "d": dataset_id, "m": ACCURACY_METRIC_ID},
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
        logger.info("Scene Text Recognition task_id=%s", task_id)

        for spec in BENCHMARKS:
            source_paper = ensure_source_paper(session, spec["source_key"])
            dataset_id = ensure_dataset(session, spec, task_id, source_paper)
            logger.info(
                "Ready %s dataset_id=%s source_paper_id=%s paper_url=%s",
                spec["name"],
                dataset_id,
                source_paper.id,
                f"https://paperswithcode.co/paper/{source_paper.id}",
            )

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
