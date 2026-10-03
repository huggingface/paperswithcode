"""Common paper-feed execution; domain services supply their resolved scope.

Global trending has a separate SQL selector because it ranks repository winners
before pagination. It shares response hydration, while scoped feeds share the
entire ORM pipeline. Ordering policies preserve public endpoint differences.
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.orm import Query, aliased

from backend.models.database import (
    Paper as DBPaper,
    PaperRepository as DBPaperRepository,
    PaperTask,
)
from backend.models.papers import Papers
from backend.services.paper_implementation_service import (
    family_repository_exists_clause,
)

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService


@dataclass(frozen=True)
class FeedOrdering:
    nulls_last: bool = False
    id_tiebreaker: bool = False
    case_insensitive_direction: bool = False
    fallback_to_date: bool = False


GENERAL_ORDERING = FeedOrdering(nulls_last=True, case_insensitive_direction=True)
TASK_ORDERING = FeedOrdering(id_tiebreaker=True, fallback_to_date=True)


class PaperFeedExecutor:
    def __init__(self, papers: "PaperService"):
        self.papers = papers

    def execute(
        self,
        query: Query[DBPaper],
        *,
        page: int,
        page_size: int,
        order_by: str,
        order_dir: str,
        ordering: FeedOrdering,
        latest_only: bool = True,
        has_code: bool = False,
        has_official_implementation: bool = False,
        has_hf_artifacts: bool = False,
        search: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        deduplicate_task_id: int | None = None,
        include_resources: bool = False,
    ) -> Papers:
        if latest_only:
            query = query.filter(DBPaper.is_latest_version)
        if has_code:
            query = self.papers.apply_has_code_filter(query)
        if has_official_implementation:
            query = query.filter(family_repository_exists_clause(official_only=True))
        if has_hf_artifacts:
            query = self.papers.apply_has_hf_artifacts_filter(query)
        if search:
            query = query.filter(
                or_(
                    DBPaper.title.ilike(f"%{search}%"),
                    DBPaper.abstract.ilike(f"%{search}%"),
                )
            )
        if start_date is not None:
            query = query.filter(DBPaper.date_published >= start_date)
        if end_date is not None:
            query = query.filter(DBPaper.date_published <= end_date)

        if order_by == "trending":
            if deduplicate_task_id is not None:
                query = deduplicate_task_trending_repositories(
                    query, deduplicate_task_id
                )
            query = self.papers.apply_scoped_trending_order(query)
        else:
            fields = {
                "date_published": DBPaper.date_published,
                "citation_count": DBPaper.citation_count,
                "title": DBPaper.title,
            }
            field = fields.get(order_by)
            if field is None:
                if not ordering.fallback_to_date:
                    raise ValueError(f"Unsupported order_by: {order_by}")
                field = DBPaper.date_published
            direction = (
                order_dir.lower() if ordering.case_insensitive_direction else order_dir
            )
            sort = desc if direction == "desc" else asc
            primary = sort(field)
            if ordering.nulls_last:
                primary = primary.nullslast()
            terms = [primary]
            if ordering.id_tiebreaker:
                terms.append(sort(DBPaper.id))
            query = query.order_by(*terms)

        count = query.order_by(None).count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        return self.page(
            rows,
            count=count,
            page=page,
            page_size=page_size,
            include_resources=include_resources,
        )

    def page(
        self,
        rows: list[DBPaper],
        *,
        count: int,
        page: int,
        page_size: int,
        include_resources: bool,
    ) -> Papers:
        return Papers(
            count=count,
            next_page=page + 1 if page * page_size < count else None,
            previous_page=page - 1 if page > 1 else None,
            results=self.papers.hydrate_cards(
                rows, include_resources=include_resources
            ),
        )


def deduplicate_task_trending_repositories(
    query: Query[DBPaper], task_id: int
) -> Query[DBPaper]:
    """Keep the newest task paper for each shared official repository.

    The global trending feed attributes a repository's activity to only
    its newest linked paper. Apply the same rule to task-scoped trending
    feeds so a project that publishes a follow-up paper does not occupy
    multiple cards with one repository signal. Papers without an official
    repository remain independent.
    """
    current_repo = aliased(DBPaperRepository)
    other_repo = aliased(DBPaperRepository)
    other_paper = aliased(DBPaper)
    other_task = aliased(PaperTask)

    same_date = or_(
        other_paper.date_published == DBPaper.date_published,
        and_(
            other_paper.date_published.is_(None),
            DBPaper.date_published.is_(None),
        ),
    )
    newer_paper = or_(
        and_(
            DBPaper.date_published.is_(None),
            other_paper.date_published.is_not(None),
        ),
        other_paper.date_published > DBPaper.date_published,
        and_(same_date, other_paper.id > DBPaper.id),
    )
    newer_for_shared_repo = (
        select(1)
        .select_from(current_repo)
        .join(
            other_repo,
            other_repo.repository_id == current_repo.repository_id,
        )
        .join(other_paper, other_paper.id == other_repo.paper_id)
        .join(other_task, other_task.paper_id == other_paper.id)
        .where(
            current_repo.paper_id == DBPaper.id,
            current_repo.is_official.is_(True),
            other_repo.is_official.is_(True),
            other_task.task_id == task_id,
            other_paper.is_latest_version.is_(True),
            newer_paper,
        )
        .exists()
    )
    return query.filter(~newer_for_shared_repo)
