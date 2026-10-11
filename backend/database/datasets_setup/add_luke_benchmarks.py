#!/usr/bin/env python3
"""Add Open Entity, TACRED, and ReCoRD benchmarks for LUKE eval import."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.taxonomy import TaskCreateRequest
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService
from backend.utils.slug_utils import slugify

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

F1_METRIC_ID = 21
LUKE_PAPER_ID = 4244
LUKE_SOURCE_URL = "https://paperswithcode.co/paper/2010.01057"
LUKE_NUM_PARAMETERS = 483_000_000

BENCHMARKS = [
    {
        "name": "Open Entity",
        "full_name": "Open Entity",
        "description": (
            "Open Entity is a collection of about 6,000 sentences with fine-grained "
            "entity type annotations. Entity types are free-form noun phrases describing "
            "the role the target entity plays in the sentence."
        ),
        "short_description": (
            "About 6,000 sentences with fine-grained entity type annotations derived "
            "from the Ultra-Fine Entity Typing benchmark."
        ),
        "homepage": "https://www.cs.utexas.edu/~eunsol/html_pages/open_entity.html",
        "introduced_date": date(2018, 1, 1),
        "task_slug": "entity-typing",
        "source_arxiv": "1807.04905",
        "source_external_url": None,
        "eval_score": "78.2",
        "eval_methodology": (
            "Loose micro-F1 on Open Entity test set; multi-label entity typing with "
            "[MASK] entity inputs. Source: LUKE paper Table 1 (test F1)."
        ),
    },
    {
        "name": "TACRED",
        "full_name": "The TAC Relation Extraction Dataset",
        "description": (
            "TACRED is a large-scale relation extraction dataset with 106,264 examples "
            "built over newswire and web text from the TAC KBP corpus. Examples cover "
            "42 relation types or the no_relation label."
        ),
        "short_description": (
            "Large-scale relation extraction dataset with 106,264 crowd-sourced examples."
        ),
        "homepage": "https://nlp.stanford.edu/projects/tacred/",
        "introduced_date": date(2017, 9, 1),
        "task_slug": "relation-extraction",
        "source_arxiv": None,
        "source_external_url": "https://aclanthology.org/D17-1004/",
        "eval_score": "72.7",
        "eval_methodology": (
            "Micro-F1 on TACRED test set; [HEAD]/[TAIL] entity inputs with concatenated "
            "entity representations. Source: LUKE paper Table 2 (test F1)."
        ),
    },
    {
        "name": "ReCoRD",
        "full_name": "ReCoRD",
        "description": (
            "ReCoRD is a large-scale reading comprehension dataset requiring commonsense "
            "reasoning. Queries are generated from CNN/Daily Mail news articles and answers "
            "are entity spans from a summarizing passage."
        ),
        "short_description": (
            "Commonsense cloze-style reading comprehension over news passages."
        ),
        "homepage": "https://sheng-z.github.io/ReCoRD-explorer/",
        "introduced_date": date(2018, 10, 30),
        "task_slug": "question-answering",
        "source_arxiv": "1810.12885",
        "source_external_url": None,
        "eval_score": "91.2",
        "eval_methodology": (
            "Token-level F1 on ReCoRD test set; cloze-style QA with [MASK] entity for the "
            "missing entity and passage entities. Source: LUKE paper Table 4 (test F1)."
        ),
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

    arxiv_service = ArxivService()
    paper_service = PaperService(session)
    metadata = await arxiv_service.get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(f"Failed to fetch arXiv metadata for {arxiv_id}")

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


def ensure_tacred_source_paper(session) -> Paper:
    existing = (
        session.query(Paper)
        .filter(
            Paper.source == "external",
            Paper.source_url == BENCHMARKS[1]["source_external_url"],
        )
        .first()
    )
    if existing:
        return existing

    service = ExternalResourceService(session)
    result = service.add_external_resource(
        ExternalResourceInput(
            source_url=BENCHMARKS[1]["source_external_url"],
            title="Position-aware Attention and Supervised Data Improve Slot Filling",
            abstract=(
                "Organized relational knowledge in the form of knowledge graphs is important "
                "for many applications. This paper proposes a position-aware neural sequence "
                "model for relation extraction and introduces TACRED, a large supervised "
                "relation extraction dataset obtained via crowdsourcing and targeted toward "
                "TAC KBP relations."
            ),
            authors=[
                "Yuhao Zhang",
                "Peng Qi",
                "Christopher D. Manning",
            ],
            date_published=date(2017, 9, 1),
        )
    )
    return result.paper


def ensure_entity_typing_task(session) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = 'entity-typing'")
    ).first()
    if row:
        return int(row[0])

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name="Entity Typing",
            description=(
                "Predict semantic types for entity mentions in text, including fine-grained "
                "and ultra-fine entity typing benchmarks."
            ),
            keywords="entity typing,fine-grained entity typing,ultra-fine entity typing",
            area_id=2,
        )
    )
    return int(task.id)


def ensure_dataset(session, spec: dict, task_id: int, source_paper: Paper) -> int:
    slug = slugify(spec["name"])
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": slug}
    ).first()
    if row:
        dataset_id = int(row[0])
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
                languages=["English"],
                modalities=["Text"],
            )
        )
        dataset_id = int(created.id)

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
        {"t": task_id, "d": dataset_id, "m": F1_METRIC_ID},
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


def ensure_luke_eval(
    session, task_id: int, dataset_id: int, score: str, methodology: str
) -> None:
    params = {
        "paper_id": LUKE_PAPER_ID,
        "task_id": task_id,
        "dataset_id": dataset_id,
        "model_name": "LUKE",
        "best_metric": "F1",
    }
    existing = session.execute(
        text(
            """
            SELECT id FROM evaluations
            WHERE paper_id=:paper_id AND task_id=:task_id AND dataset_id=:dataset_id
              AND model_name=:model_name
              AND COALESCE(harness, '') = ''
              AND best_metric=:best_metric
            """
        ),
        params,
    ).first()
    if existing:
        logger.info("Skipping existing LUKE eval for dataset_id=%s", dataset_id)
        return

    EvaluationService(session).create_evaluation(
        paper_id=LUKE_PAPER_ID,
        task_id=task_id,
        dataset_id=dataset_id,
        model_name="LUKE",
        methodology=methodology,
        metrics={"F1": score},
        best_metric="F1",
        harness=None,
        external_source_url=LUKE_SOURCE_URL,
        num_parameters=LUKE_NUM_PARAMETERS,
    )


async def main() -> None:
    session = db_manager.session_local()
    try:
        entity_typing_task_id = ensure_entity_typing_task(session)
        task_ids_by_slug = {
            row.slug: row.id
            for row in session.execute(text("SELECT id, slug FROM tasks")).all()
        }

        for spec in BENCHMARKS:
            if spec["source_arxiv"]:
                source_paper = await ensure_arxiv_paper(session, spec["source_arxiv"])
            else:
                source_paper = ensure_tacred_source_paper(session)

            task_id = (
                entity_typing_task_id
                if spec["task_slug"] == "entity-typing"
                else int(task_ids_by_slug[spec["task_slug"]])
            )
            dataset_id = ensure_dataset(session, spec, task_id, source_paper)
            ensure_luke_eval(
                session,
                task_id,
                dataset_id,
                spec["eval_score"],
                spec["eval_methodology"],
            )
            logger.info(
                "Ready %s dataset_id=%s task_id=%s source_paper_id=%s",
                spec["name"],
                dataset_id,
                task_id,
                source_paper.id,
            )

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
