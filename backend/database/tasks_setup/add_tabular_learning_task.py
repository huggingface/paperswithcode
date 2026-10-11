#!/usr/bin/env python3
"""Add Tabular Learning task and tag selected papers."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.taxonomy import TaskCreateRequest
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OTHER_AREA_ID = 8

ARXIV_IDS = [
    "1908.07442",
    "2605.10616",
    "2505.14415",
    "2504.16109",
]

TASK = {
    "slug": "tabular-learning",
    "name": "Tabular Learning",
    "area_id": OTHER_AREA_ID,
    "description": (
        "Tabular learning trains models on tabular data: tables where each row "
        "is an observation (record or instance) and each column is an attribute "
        "or feature measured for that observation. Methods target classification, "
        "regression, and related predictive tasks on this row-and-column structure, "
        "including specialized, transferable, and tabular foundation models."
    ),
    "keywords": (
        "tabular learning, tabular data, tabular deep learning, "
        "tabular foundation model, table foundation model, "
        "representation learning for tabular data, deep tabular"
    ),
    "image_url": "https://paperswithcode.co/images/tasks/tabular-learning.png",
    "image_credit": "[What is Tabular Data? (Statology)](https://www.statology.org/tabular-data/)",
}


def ensure_task(session, spec: dict) -> int:
    row = session.execute(
        text(
            "SELECT id, area_id, image_url, image_credit, description, keywords "
            "FROM tasks WHERE slug = :slug"
        ),
        {"slug": spec["slug"]},
    ).first()
    if row:
        task_id = int(row[0])
        updates: dict[str, object] = {"id": task_id}
        changed_fields: list[str] = []

        for field in (
            "area_id",
            "image_url",
            "image_credit",
            "description",
            "keywords",
        ):
            desired = spec.get(field)
            if desired is not None and row._mapping[field] != desired:
                updates[field] = desired
                changed_fields.append(field)

        if changed_fields:
            set_clause = ", ".join(f"{field} = :{field}" for field in changed_fields)
            session.execute(
                text(f"UPDATE tasks SET {set_clause} WHERE id = :id"),
                updates,
            )
            logger.info(
                "Updated %s (id=%s): %s",
                spec["name"],
                task_id,
                ", ".join(changed_fields),
            )
        else:
            logger.info("Task already exists: %s (id=%s)", spec["name"], task_id)
        return task_id

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name=spec["name"],
            description=spec["description"],
            keywords=spec["keywords"],
            area_id=spec["area_id"],
            image_url=spec.get("image_url"),
            image_credit=spec.get("image_credit"),
        )
    )
    logger.info("Created task: %s (id=%s)", spec["name"], task.id)
    return int(task.id)


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        logger.info("Paper %s already exists (id=%s)", arxiv_id, existing.id)
        return existing

    arxiv_service = ArxivService()
    paper_service = PaperService(session)
    metadata = await arxiv_service.get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )

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
    logger.info("Imported paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def link_paper_to_task(session, paper_id: int, task_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


async def run() -> None:
    session = db_manager.session_local()
    try:
        task_id = ensure_task(session, TASK)

        for arxiv_id in ARXIV_IDS:
            paper = await ensure_arxiv_paper(session, arxiv_id)
            link_paper_to_task(session, int(paper.id), task_id)
            logger.info(
                "Tagged paper %s (id=%s) with Tabular Learning", arxiv_id, paper.id
            )

        session.commit()
        logger.info("Done: task_id=%s, papers tagged=%s", task_id, len(ARXIV_IDS))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
