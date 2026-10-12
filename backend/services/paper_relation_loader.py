"""Typed batched relation loading for paper API projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, TypeVar

from sqlalchemy import Integer, and_, cast, desc, func, or_
from sqlalchemy.orm import Session, aliased

from backend.models.evaluations import (
    BenchmarkSummary,
    LeaderboardRankSummary,
)
from backend.models.papers import (
    AuthorLink,
    FrameworkSummary,
    MethodSummary,
    OrganizationSummary,
    ProjectPage,
    RelatedPaperSummary,
    Repository,
    TaskSummary,
    XThread,
)
from backend.models.database import (
    Author as DBAuthor,
    Conference as DBConference,
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Framework as DBFramework,
    HfArtifact as DBHfArtifact,
    Method as DBMethod,
    Organization as DBOrganization,
    Paper as DBPaper,
    PaperAuthor,
    PaperConference as DBPaperConference,
    PaperHfArtifact as DBPaperHfArtifact,
    PaperMethod,
    PaperOrganization as DBPaperOrganization,
    PaperProjectPage as DBPaperProjectPage,
    PaperRelation as DBPaperRelation,
    PaperRepository as DBPaperRepository,
    PaperTask,
    PaperXThread as DBPaperXThread,
    ProjectPage as DBProjectPage,
    Repository as DBRepository,
    Task as DBTask,
)
from backend.utils.organization_logos import organization_logo_path
from backend.utils.urls import get_method_source_url, get_paper_route_identifier


@dataclass(frozen=True, slots=True)
class PaperConferenceRelation:
    """Conference fields embedded in a paper API response."""

    name: str
    slug: str


@dataclass(slots=True)
class PaperRelations:
    """Typed relation maps used to hydrate a batch of paper rows."""

    authors: dict[int, list[str]] = field(default_factory=dict)
    author_links: dict[int, list[AuthorLink]] = field(default_factory=dict)
    tasks: dict[int, list[TaskSummary]] = field(default_factory=dict)
    methods: dict[int, list[MethodSummary]] = field(default_factory=dict)
    organizations: dict[int, list[OrganizationSummary]] = field(default_factory=dict)
    leaderboard_ranks: dict[int, list[LeaderboardRankSummary]] = field(
        default_factory=dict
    )
    hf_artifact_counts: dict[int, dict[str, int]] = field(default_factory=dict)
    introduced_benchmarks: dict[int, list[BenchmarkSummary]] = field(
        default_factory=dict
    )
    introduced_frameworks: dict[int, list[FrameworkSummary]] = field(
        default_factory=dict
    )
    predecessor_papers: dict[int, list[RelatedPaperSummary]] = field(
        default_factory=dict
    )
    successor_papers: dict[int, list[RelatedPaperSummary]] = field(default_factory=dict)
    conferences: dict[int, PaperConferenceRelation] = field(default_factory=dict)
    repositories: dict[int, list[Repository]] = field(default_factory=dict)
    repository_coverage: dict[int, tuple[bool, int]] = field(default_factory=dict)
    project_pages: dict[int, list[ProjectPage]] = field(default_factory=dict)
    x_threads: dict[int, list[XThread]] = field(default_factory=dict)


_RelationValue = TypeVar("_RelationValue")
_AuthorRow = tuple[int, int, str, str | None]


def _append_relation(
    relation_map: dict[int, list[_RelationValue]],
    paper_id: int,
    value: _RelationValue,
) -> None:
    relation_map.setdefault(int(paper_id), []).append(value)


def _method_summary(
    method: DBMethod, source_paper: DBPaper | None = None
) -> MethodSummary:
    return MethodSummary(
        id=str(method.id),
        name=method.name,
        slug=method.slug,
        introduced_year=method.introduced_year,
        source_paper_id=(
            str(method.source_paper_id) if method.source_paper_id is not None else None
        ),
        source_url=get_method_source_url(method.source_url, source_paper),
        source_title=method.source_title,
        code_snippet_url=method.code_snippet_url,
    )


def _related_paper_summary(related: DBPaper) -> RelatedPaperSummary:
    return RelatedPaperSummary(
        id=str(related.id),
        title=related.title,
        arxiv_id=related.arxiv_id,
        source=related.source,
        source_url=related.source_url,
        published=related.date_published,
        route_identifier=get_paper_route_identifier(
            related.source, related.arxiv_id, related.id
        ),
    )


class PaperRelationLoader:
    """Load card, detail, and resource paper relations in bounded batches."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _unique_ids(paper_ids: Sequence[int]) -> list[int]:
        return list(dict.fromkeys(int(paper_id) for paper_id in paper_ids))

    def load_cards(self, paper_ids: Sequence[int]) -> PaperRelations:
        """Load only relations rendered by paper cards."""
        relations = PaperRelations()
        unique_ids = self._unique_ids(paper_ids)
        if unique_ids:
            self._load_card_relations(unique_ids, relations)
            self._load_repository_coverage(unique_ids, relations)
        return relations

    def load_details(self, paper_ids: Sequence[int]) -> PaperRelations:
        """Load card relations plus detail-only paper relations."""
        relations = PaperRelations()
        unique_ids = self._unique_ids(paper_ids)
        if not unique_ids:
            return relations

        author_rows = self._load_card_relations(unique_ids, relations)
        for paper_id, author_id, author_name, hf_username in author_rows:
            _append_relation(
                relations.author_links,
                paper_id,
                AuthorLink(
                    id=str(author_id),
                    name=author_name,
                    hf_username=hf_username,
                ),
            )
        self._load_detail_relations(unique_ids, relations)
        self._load_repository_coverage(unique_ids, relations)
        return relations

    @staticmethod
    def _family_join(requested, family):
        return or_(
            and_(
                requested.arxiv_id.is_not(None),
                family.arxiv_id == requested.arxiv_id,
            ),
            and_(requested.arxiv_id.is_(None), family.id == requested.id),
        )

    def _load_repository_coverage(
        self,
        paper_ids: list[int],
        relations: PaperRelations,
    ) -> None:
        requested = aliased(DBPaper)
        family = aliased(DBPaper)
        rows = (
            self.db.query(
                requested.id,
                func.max(cast(DBPaperRepository.is_official, Integer)),
                func.count(func.distinct(DBPaperRepository.repository_id)),
            )
            .select_from(requested)
            .join(family, self._family_join(requested, family))
            .join(DBPaperRepository, DBPaperRepository.paper_id == family.id)
            .filter(requested.id.in_(paper_ids))
            .group_by(requested.id)
            .all()
        )
        relations.repository_coverage.update(
            {
                int(paper_id): (bool(has_official), int(repository_count))
                for paper_id, has_official, repository_count in rows
            }
        )

    def load_resources(
        self,
        paper_ids: Sequence[int],
        relations: PaperRelations,
    ) -> PaperRelations:
        """Add repositories and project pages to an existing projection."""
        unique_ids = self._unique_ids(paper_ids)
        if not unique_ids:
            return relations

        requested = aliased(DBPaper)
        family = aliased(DBPaper)
        repository_rows = (
            self.db.query(
                requested.id,
                DBPaperRepository.is_official,
                DBRepository,
            )
            .select_from(requested)
            .join(family, self._family_join(requested, family))
            .join(DBPaperRepository, DBPaperRepository.paper_id == family.id)
            .join(
                DBRepository,
                DBPaperRepository.repository_id == DBRepository.id,
            )
            .filter(requested.id.in_(unique_ids))
            .order_by(
                requested.id,
                desc(DBPaperRepository.is_official),
                desc(DBRepository.num_stars),
            )
            .all()
        )
        seen_repositories: dict[int, set[int]] = {}
        for paper_id, is_official, repository in repository_rows:
            seen = seen_repositories.setdefault(int(paper_id), set())
            if repository.id in seen:
                continue
            seen.add(repository.id)
            _append_relation(
                relations.repositories,
                paper_id,
                Repository(
                    id=str(repository.id),
                    url=repository.url,
                    owner=repository.owner,
                    name=repository.name,
                    num_stars=repository.num_stars,
                    is_official=is_official,
                    source=repository.source,
                    trending_score=(
                        float(repository.trending_score)
                        if repository.trending_score is not None
                        else None
                    ),
                    trending_score_updated_at=repository.trending_score_updated_at,
                    created_at=(
                        repository.created_at.date() if repository.created_at else None
                    ),
                    updated_at=(
                        repository.updated_at.date() if repository.updated_at else None
                    ),
                ),
            )

        project_page_rows = (
            self.db.query(DBPaperProjectPage.paper_id, DBProjectPage)
            .join(
                DBProjectPage,
                DBPaperProjectPage.project_page_id == DBProjectPage.id,
            )
            .filter(DBPaperProjectPage.paper_id.in_(unique_ids))
            .order_by(DBPaperProjectPage.paper_id, desc(DBProjectPage.created_at))
            .all()
        )
        for paper_id, project_page in project_page_rows:
            _append_relation(
                relations.project_pages,
                paper_id,
                ProjectPage(
                    id=str(project_page.id),
                    url=project_page.url,
                    is_official=project_page.is_official,
                    source=project_page.source,
                    created_at=(
                        project_page.created_at.date()
                        if project_page.created_at
                        else None
                    ),
                    updated_at=(
                        project_page.updated_at.date()
                        if project_page.updated_at
                        else None
                    ),
                ),
            )

        x_thread_rows = (
            self.db.query(DBPaperXThread)
            .filter(DBPaperXThread.paper_id.in_(unique_ids))
            .order_by(DBPaperXThread.paper_id, DBPaperXThread.position)
            .all()
        )
        for row in x_thread_rows:
            _append_relation(
                relations.x_threads,
                row.paper_id,
                XThread.model_validate(row, from_attributes=True),
            )

        return relations

    def _load_card_relations(
        self,
        paper_ids: list[int],
        relations: PaperRelations,
    ) -> list[_AuthorRow]:
        author_rows: list[_AuthorRow] = (
            self.db.query(
                PaperAuthor.paper_id,
                DBAuthor.id,
                DBAuthor.name,
                DBAuthor.hf_username,
            )
            .join(DBAuthor, PaperAuthor.author_id == DBAuthor.id)
            .filter(PaperAuthor.paper_id.in_(paper_ids))
            .order_by(PaperAuthor.paper_id, PaperAuthor.author_order)
            .all()
        )
        for paper_id, _author_id, author_name, _hf_username in author_rows:
            _append_relation(relations.authors, paper_id, author_name)

        task_rows = (
            self.db.query(PaperTask.paper_id, DBTask)
            .join(DBTask, PaperTask.task_id == DBTask.id)
            .filter(PaperTask.paper_id.in_(paper_ids))
            .order_by(PaperTask.paper_id, DBTask.name)
            .all()
        )
        for paper_id, task in task_rows:
            _append_relation(
                relations.tasks,
                paper_id,
                TaskSummary(id=str(task.id), name=task.name, slug=task.slug),
            )

        method_rows = (
            self.db.query(PaperMethod.paper_id, DBMethod)
            .join(DBMethod, PaperMethod.method_id == DBMethod.id)
            .filter(PaperMethod.paper_id.in_(paper_ids))
            .order_by(PaperMethod.paper_id, DBMethod.name)
            .all()
        )
        source_paper_ids = {
            method.source_paper_id
            for _, method in method_rows
            if method.source_paper_id is not None
        }
        source_papers_by_id = {}
        if source_paper_ids:
            source_papers_by_id = {
                paper.id: paper
                for paper in self.db.query(DBPaper)
                .filter(DBPaper.id.in_(source_paper_ids))
                .all()
            }
        for paper_id, method in method_rows:
            _append_relation(
                relations.methods,
                paper_id,
                _method_summary(
                    method,
                    source_papers_by_id.get(method.source_paper_id),
                ),
            )

        hf_count_rows = (
            self.db.query(
                DBPaperHfArtifact.paper_id,
                DBHfArtifact.kind,
                func.count().label("cnt"),
            )
            .join(
                DBHfArtifact,
                DBPaperHfArtifact.hf_artifact_id == DBHfArtifact.id,
            )
            .filter(DBPaperHfArtifact.paper_id.in_(paper_ids))
            .group_by(DBPaperHfArtifact.paper_id, DBHfArtifact.kind)
            .all()
        )
        for paper_id, kind, count in hf_count_rows:
            relations.hf_artifact_counts.setdefault(int(paper_id), {})[kind] = int(
                count
            )

        rank_rows = (
            self.db.query(
                DBEvaluation.paper_id,
                DBEvaluation.dataset_id,
                DBEvaluation.id,
                DBEvaluation.best_rank,
                DBEvaluation.best_metric,
                DBDataset.name,
                DBDataset.slug,
                DBTask.slug,
            )
            .join(DBDataset, DBEvaluation.dataset_id == DBDataset.id)
            .join(DBTask, DBEvaluation.task_id == DBTask.id)
            .filter(
                DBEvaluation.paper_id.in_(paper_ids),
                DBEvaluation.best_rank.isnot(None),
                DBEvaluation.best_rank <= 3,
            )
            .order_by(
                DBEvaluation.paper_id,
                DBEvaluation.best_rank.asc(),
                DBDataset.name,
                DBEvaluation.id,
            )
            .all()
        )
        seen_paper_datasets: set[tuple[int, int]] = set()
        for (
            paper_id,
            dataset_id,
            evaluation_id,
            best_rank,
            best_metric,
            name,
            slug,
            task_slug,
        ) in rank_rows:
            key = (paper_id, dataset_id)
            if key in seen_paper_datasets:
                continue
            seen_paper_datasets.add(key)
            _append_relation(
                relations.leaderboard_ranks,
                paper_id,
                LeaderboardRankSummary(
                    evaluation_id=str(evaluation_id),
                    dataset_name=name,
                    dataset_slug=slug,
                    best_rank=int(best_rank),
                    best_metric=best_metric,
                    task_slug=task_slug,
                ),
            )

        organization_rows = (
            self.db.query(DBPaperOrganization, DBOrganization)
            .join(
                DBOrganization,
                DBPaperOrganization.organization_id == DBOrganization.id,
            )
            .filter(DBPaperOrganization.paper_id.in_(paper_ids))
            .order_by(DBPaperOrganization.paper_id, DBOrganization.name)
            .all()
        )
        for link, organization in organization_rows:
            _append_relation(
                relations.organizations,
                link.paper_id,
                OrganizationSummary(
                    id=str(organization.id),
                    name=organization.name,
                    slug=organization.slug,
                    logo_url=(
                        organization_logo_path(
                            organization.slug,
                            organization.logo_mime_type,
                            organization.logo_sha256,
                        )
                        if organization.logo_mime_type
                        else organization.logo_url
                    ),
                    source=link.source,
                    added_by_hf_username=link.added_by_hf_username,
                ),
            )

        return author_rows

    def _load_detail_relations(
        self,
        paper_ids: list[int],
        relations: PaperRelations,
    ) -> None:
        introduced_dataset_rows = (
            self.db.query(DBDataset)
            .filter(DBDataset.introducing_paper_id.in_(paper_ids))
            .order_by(DBDataset.introducing_paper_id, DBDataset.name)
            .all()
        )
        for dataset in introduced_dataset_rows:
            _append_relation(
                relations.introduced_benchmarks,
                dataset.introducing_paper_id,
                BenchmarkSummary(
                    id=str(dataset.id),
                    name=dataset.name,
                    slug=dataset.slug,
                    full_name=dataset.full_name,
                    introduced_year=dataset.introduced_year,
                ),
            )

        introduced_framework_rows = (
            self.db.query(DBFramework)
            .filter(DBFramework.introducing_paper_id.in_(paper_ids))
            .order_by(DBFramework.introducing_paper_id, DBFramework.name)
            .all()
        )
        for framework in introduced_framework_rows:
            _append_relation(
                relations.introduced_frameworks,
                framework.introducing_paper_id,
                FrameworkSummary(
                    id=str(framework.id),
                    slug=framework.slug,
                    name=framework.name,
                ),
            )

        successor_rows = (
            self.db.query(DBPaperRelation.source_paper_id, DBPaper)
            .join(DBPaper, DBPaperRelation.target_paper_id == DBPaper.id)
            .filter(DBPaperRelation.source_paper_id.in_(paper_ids))
            .order_by(
                DBPaperRelation.source_paper_id,
                DBPaper.date_published.asc().nullslast(),
                DBPaper.id,
            )
            .all()
        )
        for paper_id, related in successor_rows:
            _append_relation(
                relations.successor_papers,
                paper_id,
                _related_paper_summary(related),
            )

        predecessor_rows = (
            self.db.query(DBPaperRelation.target_paper_id, DBPaper)
            .join(DBPaper, DBPaperRelation.source_paper_id == DBPaper.id)
            .filter(DBPaperRelation.target_paper_id.in_(paper_ids))
            .order_by(
                DBPaperRelation.target_paper_id,
                DBPaper.date_published.asc().nullslast(),
                DBPaper.id,
            )
            .all()
        )
        for paper_id, related in predecessor_rows:
            _append_relation(
                relations.predecessor_papers,
                paper_id,
                _related_paper_summary(related),
            )

        conference_rows = (
            self.db.query(DBPaperConference.paper_id, DBConference)
            .join(DBConference, DBPaperConference.conference_id == DBConference.id)
            .filter(DBPaperConference.paper_id.in_(paper_ids))
            .order_by(
                DBPaperConference.paper_id,
                desc(DBConference.year),
                DBConference.name,
            )
            .all()
        )
        for paper_id, conference in conference_rows:
            relations.conferences.setdefault(
                int(paper_id),
                PaperConferenceRelation(name=conference.name, slug=conference.slug),
            )
