"""
Merge an external paper row into its ArXiv counterpart.

When the same work is indexed twice (once as `source='external'` and later as
`source='arxiv'`), keep the ArXiv row and move all linked data onto it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.models.database import (
    Evaluation,
    Paper,
    PaperAuthor,
    PaperConference,
    PaperDataset,
    PaperMethod,
    PaperOrganization,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    Repository,
)
from backend.services.evaluation_service import EvaluationService
from backend.utils.urls import get_paper_route_identifier


def record_paper_merge_redirect(
    db: Session, old_paper_id: int, arxiv_paper: Paper
) -> None:
    route_identifier = get_paper_route_identifier(
        arxiv_paper.source, arxiv_paper.arxiv_id, arxiv_paper.id
    )
    db.execute(
        text(
            """
            INSERT INTO public.paper_redirects (old_paper_id, route_identifier)
            VALUES (:old_paper_id, :route_identifier)
            ON CONFLICT (old_paper_id) DO UPDATE
            SET route_identifier = EXCLUDED.route_identifier
            """
        ),
        {"old_paper_id": old_paper_id, "route_identifier": route_identifier},
    )


def lookup_paper_merge_redirect(db: Session, old_paper_id: int) -> str | None:
    row = db.execute(
        text(
            """
            SELECT route_identifier
            FROM public.paper_redirects
            WHERE old_paper_id = :old_paper_id
            """
        ),
        {"old_paper_id": old_paper_id},
    ).first()
    return row.route_identifier if row else None


def find_arxiv_paper_for_title(db: Session, title: str) -> Paper | None:
    normalized = title.strip().lower()
    if not normalized:
        return None
    return (
        db.query(Paper)
        .filter(
            Paper.source == "arxiv",
            Paper.is_latest_version.is_(True),
            func.lower(func.trim(Paper.title)) == normalized,
        )
        .order_by(Paper.id.desc())
        .first()
    )


def find_external_paper_for_title(db: Session, title: str) -> Paper | None:
    normalized = title.strip().lower()
    if not normalized:
        return None
    return (
        db.query(Paper)
        .filter(
            Paper.source == "external",
            Paper.is_latest_version.is_(True),
            func.lower(func.trim(Paper.title)) == normalized,
        )
        .order_by(Paper.id.asc())
        .first()
    )


def merge_external_paper_into_arxiv(
    db: Session,
    external_id: int,
    arxiv_paper_id: int,
) -> dict[str, Any]:
    external = db.get(Paper, external_id)
    arxiv_paper = db.get(Paper, arxiv_paper_id)
    if external is None or arxiv_paper is None:
        raise ValueError(
            f"Paper not found: external={external_id}, arxiv={arxiv_paper_id}"
        )
    if external.source != "external":
        raise ValueError(
            f"Paper {external_id} is not external (source={external.source})"
        )
    if arxiv_paper.source != "arxiv" or not arxiv_paper.arxiv_id:
        raise ValueError(
            f"Paper {arxiv_paper_id} is not an ArXiv row (source={arxiv_paper.source})"
        )

    stats: dict[str, Any] = {
        "external_id": external_id,
        "arxiv_paper_id": arxiv_paper_id,
        "arxiv_id": arxiv_paper.arxiv_id,
        "evaluations_moved": 0,
        "evaluations_dropped": 0,
        "repos_merged": 0,
        "repos_moved": 0,
        "tasks_merged": 0,
        "tasks_moved": 0,
        "methods_merged": 0,
        "methods_moved": 0,
        "authors_merged": 0,
        "authors_moved": 0,
        "datasets_merged": 0,
        "datasets_moved": 0,
        "project_pages_merged": 0,
        "project_pages_moved": 0,
        "conferences_merged": 0,
        "conferences_moved": 0,
        "organizations_merged": 0,
        "organizations_moved": 0,
        "bookmarks_moved": 0,
        "bookmarks_dropped": 0,
    }

    external_source_url = external.source_url
    affected_leaderboards: set[tuple[int, int, str | None]] = set()

    for evaluation in (
        db.query(Evaluation).filter(Evaluation.paper_id == external_id).all()
    ):
        conflict = (
            db.query(Evaluation)
            .filter(
                Evaluation.paper_id == arxiv_paper_id,
                Evaluation.task_id == evaluation.task_id,
                Evaluation.dataset_id == evaluation.dataset_id,
                Evaluation.model_name == evaluation.model_name,
                Evaluation.harness.is_(evaluation.harness)
                if evaluation.harness is None
                else Evaluation.harness == evaluation.harness,
                Evaluation.best_metric == evaluation.best_metric,
            )
            .first()
        )
        if conflict:
            db.delete(evaluation)
            stats["evaluations_dropped"] += 1
        else:
            evaluation.paper_id = arxiv_paper_id
            if external_source_url and not evaluation.external_source_url:
                evaluation.external_source_url = external_source_url
            stats["evaluations_moved"] += 1
            affected_leaderboards.add(
                (evaluation.task_id, evaluation.dataset_id, evaluation.best_metric)
            )

    arxiv_repo_links = {
        link.repository_id: link
        for link in db.query(PaperRepository)
        .filter(PaperRepository.paper_id == arxiv_paper_id)
        .all()
    }
    arxiv_repo_urls: dict[str, PaperRepository] = {}
    for link in arxiv_repo_links.values():
        repo = db.get(Repository, link.repository_id)
        if repo and repo.url:
            arxiv_repo_urls[repo.url.lower()] = link

    for link in (
        db.query(PaperRepository).filter(PaperRepository.paper_id == external_id).all()
    ):
        existing = arxiv_repo_links.get(link.repository_id)
        if existing:
            existing.is_official = existing.is_official or link.is_official
            db.delete(link)
            stats["repos_merged"] += 1
            continue

        repo = db.get(Repository, link.repository_id)
        url_match = arxiv_repo_urls.get(repo.url.lower()) if repo and repo.url else None
        if url_match:
            url_match.is_official = url_match.is_official or link.is_official
            db.delete(link)
            stats["repos_merged"] += 1
        else:
            link.paper_id = arxiv_paper_id
            stats["repos_moved"] += 1
            if repo and repo.url:
                arxiv_repo_urls[repo.url.lower()] = link
                arxiv_repo_links[link.repository_id] = link

    arxiv_tasks = {
        link.task_id: link
        for link in db.query(PaperTask)
        .filter(PaperTask.paper_id == arxiv_paper_id)
        .all()
    }
    for link in db.query(PaperTask).filter(PaperTask.paper_id == external_id).all():
        existing = arxiv_tasks.get(link.task_id)
        if existing:
            if link.source == "manual" and existing.source != "manual":
                existing.source = "manual"
            db.delete(link)
            stats["tasks_merged"] += 1
        else:
            link.paper_id = arxiv_paper_id
            stats["tasks_moved"] += 1
            arxiv_tasks[link.task_id] = link

    arxiv_methods = {
        link.method_id
        for link in db.query(PaperMethod)
        .filter(PaperMethod.paper_id == arxiv_paper_id)
        .all()
    }
    for link in db.query(PaperMethod).filter(PaperMethod.paper_id == external_id).all():
        if link.method_id in arxiv_methods:
            db.delete(link)
            stats["methods_merged"] += 1
        else:
            link.paper_id = arxiv_paper_id
            stats["methods_moved"] += 1
            arxiv_methods.add(link.method_id)

    arxiv_authors = {
        link.author_id
        for link in db.query(PaperAuthor)
        .filter(PaperAuthor.paper_id == arxiv_paper_id)
        .all()
    }
    for link in db.query(PaperAuthor).filter(PaperAuthor.paper_id == external_id).all():
        if link.author_id in arxiv_authors:
            db.delete(link)
            stats["authors_merged"] += 1
        else:
            link.paper_id = arxiv_paper_id
            stats["authors_moved"] += 1
            arxiv_authors.add(link.author_id)

    arxiv_datasets = {
        link.dataset_id
        for link in db.query(PaperDataset)
        .filter(PaperDataset.paper_id == arxiv_paper_id)
        .all()
    }
    for link in (
        db.query(PaperDataset).filter(PaperDataset.paper_id == external_id).all()
    ):
        if link.dataset_id in arxiv_datasets:
            db.delete(link)
            stats["datasets_merged"] += 1
        else:
            link.paper_id = arxiv_paper_id
            stats["datasets_moved"] += 1
            arxiv_datasets.add(link.dataset_id)

    arxiv_pages = {
        link.project_page_id
        for link in db.query(PaperProjectPage)
        .filter(PaperProjectPage.paper_id == arxiv_paper_id)
        .all()
    }
    for link in (
        db.query(PaperProjectPage)
        .filter(PaperProjectPage.paper_id == external_id)
        .all()
    ):
        if link.project_page_id in arxiv_pages:
            db.delete(link)
            stats["project_pages_merged"] += 1
        else:
            link.paper_id = arxiv_paper_id
            stats["project_pages_moved"] += 1
            arxiv_pages.add(link.project_page_id)

    arxiv_conferences = {
        link.conference_id
        for link in db.query(PaperConference)
        .filter(PaperConference.paper_id == arxiv_paper_id)
        .all()
    }
    for link in (
        db.query(PaperConference).filter(PaperConference.paper_id == external_id).all()
    ):
        if link.conference_id in arxiv_conferences:
            db.delete(link)
            stats["conferences_merged"] += 1
        else:
            link.paper_id = arxiv_paper_id
            stats["conferences_moved"] += 1
            arxiv_conferences.add(link.conference_id)

    arxiv_orgs = {
        link.organization_id
        for link in db.query(PaperOrganization)
        .filter(PaperOrganization.paper_id == arxiv_paper_id)
        .all()
    }
    for link in (
        db.query(PaperOrganization)
        .filter(PaperOrganization.paper_id == external_id)
        .all()
    ):
        if link.organization_id in arxiv_orgs:
            db.delete(link)
            stats["organizations_merged"] += 1
        else:
            link.paper_id = arxiv_paper_id
            stats["organizations_moved"] += 1
            arxiv_orgs.add(link.organization_id)

    bookmark_rows = db.execute(
        text("SELECT hf_username FROM user_bookmarks WHERE paper_id = :pid"),
        {"pid": external_id},
    ).fetchall()
    for (hf_username,) in bookmark_rows:
        exists = db.execute(
            text(
                """
                SELECT 1 FROM user_bookmarks
                WHERE hf_username = :user AND paper_id = :pid
                """
            ),
            {"user": hf_username, "pid": arxiv_paper_id},
        ).first()
        if exists:
            db.execute(
                text(
                    "DELETE FROM user_bookmarks WHERE hf_username = :user AND paper_id = :pid"
                ),
                {"user": hf_username, "pid": external_id},
            )
            stats["bookmarks_dropped"] += 1
        else:
            db.execute(
                text(
                    """
                    UPDATE user_bookmarks
                    SET paper_id = :arxiv_id
                    WHERE hf_username = :user AND paper_id = :external_id
                    """
                ),
                {
                    "arxiv_id": arxiv_paper_id,
                    "user": hf_username,
                    "external_id": external_id,
                },
            )
            stats["bookmarks_moved"] += 1

    db.execute(
        text(
            "UPDATE pending_paper_edits SET paper_id = :arxiv_id WHERE paper_id = :external_id"
        ),
        {"arxiv_id": arxiv_paper_id, "external_id": external_id},
    )
    db.execute(
        text(
            """
            UPDATE paper_relations
            SET source_paper_id = :arxiv_id
            WHERE source_paper_id = :external_id
            """
        ),
        {"arxiv_id": arxiv_paper_id, "external_id": external_id},
    )
    db.execute(
        text(
            """
            UPDATE paper_relations
            SET target_paper_id = :arxiv_id
            WHERE target_paper_id = :external_id
            """
        ),
        {"arxiv_id": arxiv_paper_id, "external_id": external_id},
    )
    db.execute(
        text(
            "UPDATE methods SET source_paper_id = :arxiv_id WHERE source_paper_id = :external_id"
        ),
        {"arxiv_id": arxiv_paper_id, "external_id": external_id},
    )
    db.execute(
        text(
            """
            UPDATE datasets
            SET introducing_paper_id = :arxiv_id
            WHERE introducing_paper_id = :external_id
            """
        ),
        {"arxiv_id": arxiv_paper_id, "external_id": external_id},
    )

    record_paper_merge_redirect(db, external_id, arxiv_paper)

    db.flush()
    db.delete(external)
    db.flush()

    eval_service = EvaluationService(db)
    for task_id, dataset_id, best_metric in affected_leaderboards:
        eval_service.recalculate_ranks(
            task_id=task_id,
            dataset_id=dataset_id,
            metric_name=best_metric,
        )

    return stats
