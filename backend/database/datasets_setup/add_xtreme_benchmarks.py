#!/usr/bin/env python3
"""Add XTREME benchmark datasets used by RemBERT / cross-lingual NLU."""

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

ACCURACY_METRIC_ID = 18
F1_METRIC_ID = 21
TEXT_CLASSIFICATION_TASK_ID = 30
NER_TASK_ID = 294
QA_TASK_ID = 296
LANGUAGE_AREA_ID = 2

BENCHMARKS = [
    {
        "name": "WikiANN",
        "full_name": "WikiANN (PAN-X)",
        "slug": "wikiann",
        "description": (
            "WikiANN, also known as PAN-X, is a multilingual named entity recognition "
            "dataset derived from Wikipedia. Articles are annotated with LOC, PER, and "
            "ORG tags in IOB2 format across many languages."
        ),
        "short_description": (
            "Multilingual Wikipedia NER corpus with LOC, PER, and ORG annotations."
        ),
        "homepage": "https://huggingface.co/datasets/wikiann",
        "introduced_date": date(2017, 7, 1),
        "task_id": NER_TASK_ID,
        "metric_id": F1_METRIC_ID,
        "source": "external",
        "source_external_url": "https://aclanthology.org/P17-1178/",
        "source_arxiv": None,
        "external_title": "Cross-lingual Name Tagging and Linking for 282 Languages",
        "external_abstract": (
            "The ambitious goal of this work is to develop a cross-lingual name tagging "
            "and linking framework for 282 languages that exist in Wikipedia. Given a "
            "document in any of these languages, our framework is able to identify name "
            "mentions, assign a coarse-grained or fine-grained type to each mention, and "
            "link it to an English Knowledge Base (KB) if it is linkable."
        ),
        "external_authors": [
            "Xiaoman Pan",
            "Boliang Zhang",
            "Jonathan May",
            "Joel Nothman",
            "Kevin Knight",
            "Heng Ji",
        ],
    },
    {
        "name": "PAWS-X",
        "full_name": "PAWS-X",
        "slug": "paws-x",
        "description": (
            "PAWS-X contains human-translated PAWS evaluation pairs and machine-translated "
            "training pairs in six typologically distinct languages for cross-lingual "
            "paraphrase identification."
        ),
        "short_description": "Cross-lingual paraphrase identification benchmark in six languages.",
        "homepage": "https://github.com/google-research-datasets/paws/tree/master/pawsx",
        "introduced_date": date(2019, 8, 30),
        "task_id": TEXT_CLASSIFICATION_TASK_ID,
        "metric_id": ACCURACY_METRIC_ID,
        "source": "arxiv",
        "source_arxiv": "1908.11828",
    },
    {
        "name": "XQuAD",
        "full_name": "Cross-lingual Question Answering Dataset (XQuAD)",
        "slug": "xquad",
        "description": (
            "XQuAD is a cross-lingual extractive question answering benchmark built from "
            "professionally translated SQuAD v1.1 development examples across eleven languages."
        ),
        "short_description": "Parallel cross-lingual extractive QA over SQuAD v1.1 passages.",
        "homepage": "https://github.com/deepmind/xquad",
        "introduced_date": date(2019, 10, 25),
        "task_id": QA_TASK_ID,
        "metric_id": F1_METRIC_ID,
        "source": "arxiv",
        "source_arxiv": "1910.11856",
    },
    {
        "name": "MLQA",
        "full_name": "MultiLingual Question Answering (MLQA)",
        "slug": "mlqa",
        "description": (
            "MLQA is a multi-way aligned extractive question answering benchmark spanning "
            "seven languages, designed to evaluate cross-lingual QA transfer."
        ),
        "short_description": "Parallel extractive QA benchmark across seven languages.",
        "homepage": "https://github.com/facebookresearch/mlqa",
        "introduced_date": date(2019, 10, 16),
        "task_id": QA_TASK_ID,
        "metric_id": F1_METRIC_ID,
        "source": "arxiv",
        "source_arxiv": "1910.07475",
    },
    {
        "name": "TyDiQA-GoldP",
        "full_name": "TyDi QA Gold Passage",
        "slug": "tydiqa-goldp",
        "description": (
            "TyDiQA-GoldP is the gold-passage version of TyDi QA used in XTREME. It uses "
            "only the gold passage as context, excludes unanswerable questions, and covers "
            "nine typologically diverse languages."
        ),
        "short_description": "Gold-passage extractive QA split of TyDi QA across nine languages.",
        "homepage": "https://github.com/google-research-datasets/tydiqa",
        "introduced_date": date(2020, 3, 10),
        "task_id": QA_TASK_ID,
        "metric_id": F1_METRIC_ID,
        "source": "arxiv",
        "source_arxiv": "2003.05002",
    },
    {
        "name": "Universal Dependencies",
        "full_name": "Universal Dependencies",
        "slug": "universal-dependencies",
        "description": (
            "Universal Dependencies provides cross-linguistically consistent treebank "
            "annotation of morphology and syntax, including universal part-of-speech tags "
            "used for multilingual POS tagging benchmarks such as XTREME."
        ),
        "short_description": "Multilingual treebanks with universal POS and dependency annotation.",
        "homepage": "https://universaldependencies.org/",
        "introduced_date": date(2020, 4, 1),
        "task_slug": "part-of-speech-tagging",
        "metric_id": F1_METRIC_ID,
        "source": "arxiv",
        "source_arxiv": "2004.10643",
    },
]


def ensure_pos_task(session) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = 'part-of-speech-tagging'")
    ).first()
    if row:
        return int(row[0])

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name="Part-of-Speech Tagging",
            description=(
                "Assign part-of-speech tags to tokens in text, including multilingual "
                "and cross-lingual POS tagging benchmarks."
            ),
            keywords="pos tagging,part-of-speech tagging,universal dependencies,upos",
            area_id=LANGUAGE_AREA_ID,
        )
    )
    logger.info("Created Part-of-Speech Tagging task id=%s", task.id)
    return int(task.id)


def resolve_source_paper(session, spec: dict) -> Paper:
    if spec["source"] == "arxiv":
        row = session.execute(
            text(
                "SELECT id FROM papers WHERE arxiv_id = :aid AND is_latest_version "
                "ORDER BY id LIMIT 1"
            ),
            {"aid": spec["source_arxiv"]},
        ).first()
        if not row:
            raise RuntimeError(f"Missing arXiv paper {spec['source_arxiv']}")
        return session.get(Paper, int(row[0]))

    existing = (
        session.query(Paper)
        .filter(
            Paper.source == "external",
            Paper.source_url == spec["source_external_url"],
        )
        .first()
    )
    if existing:
        return existing

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=spec["source_external_url"],
            title=spec["external_title"],
            abstract=spec["external_abstract"],
            authors=spec["external_authors"],
            date_published=spec["introduced_date"],
        )
    )
    return result.paper


def ensure_benchmark(session, spec: dict, task_id: int, source_paper: Paper) -> int:
    slug = spec.get("slug") or slugify(spec["name"])
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": slug}
    ).first()
    if row:
        dataset_id = int(row[0])
        logger.info("Reusing dataset %s id=%s", spec["name"], dataset_id)
    else:
        paper_url = (
            f"https://paperswithcode.co/paper/{source_paper.arxiv_id}"
            if source_paper.arxiv_id
            else f"https://paperswithcode.co/paper/{source_paper.id}"
        )
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
                modalities=["Text"],
            )
        )
        dataset_id = int(created.id)
        logger.info("Created dataset %s id=%s", spec["name"], dataset_id)

    paper_url = (
        f"https://paperswithcode.co/paper/{source_paper.arxiv_id}"
        if source_paper.arxiv_id
        else f"https://paperswithcode.co/paper/{source_paper.id}"
    )
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
                short_description = COALESCE(short_description, :short_description),
                slug = COALESCE(slug, :slug)
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
            "slug": slug,
            "did": dataset_id,
        },
    )
    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id) "
            "VALUES (:t, :d) ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id},
    )
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:t, :d, :m) ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id, "m": spec["metric_id"]},
    )
    session.execute(
        text(
            "INSERT INTO paper_tasks (paper_id, task_id, source) "
            "VALUES (:p, :t, 'manual') "
            "ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'"
        ),
        {"p": source_paper.id, "t": task_id},
    )
    return dataset_id


def main() -> None:
    pos_task_id = None
    with db_manager.session_local() as session:
        pos_task_id = ensure_pos_task(session)
        created: list[tuple[str, int, str]] = []
        for spec in BENCHMARKS:
            task_id = (
                pos_task_id
                if spec.get("task_slug") == "part-of-speech-tagging"
                else spec["task_id"]
            )
            source_paper = resolve_source_paper(session, spec)
            dataset_id = ensure_benchmark(session, spec, task_id, source_paper)
            paper_url = (
                f"https://paperswithcode.co/paper/{source_paper.arxiv_id}"
                if source_paper.arxiv_id
                else f"https://paperswithcode.co/paper/{source_paper.id}"
            )
            created.append((spec["name"], dataset_id, paper_url))
        session.commit()

    for name, dataset_id, paper_url in created:
        print(f"{name}: dataset_id={dataset_id} source={paper_url}")


if __name__ == "__main__":
    main()
