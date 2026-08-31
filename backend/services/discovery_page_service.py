"""Bounded view models for crawlable public discovery pages."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.database import (
    Author,
    Conference,
    Dataset,
    Evaluation,
    Method,
    Organization,
    Paper,
    PaperAuthor,
    PaperConference,
    PaperDataset,
    PaperMethod,
    PaperOrganization,
    PaperTask,
    Task,
    TaskDataset,
)
from backend.services.sitemap_service import eligible_paper_filter
from backend.utils.urls import get_paper_route_identifier
from backend.utils.task_slugs import canonical_task_slug, task_slug_candidates

PRODUCTION_ORIGIN = "https://paperswithcode.co"
DISCOVERY_PAPER_LIMIT = 20


@dataclass(frozen=True)
class DiscoveryLink:
    href: str
    label: str


@dataclass(frozen=True)
class DiscoveryPaperLink:
    route_identifier: str
    title: str
    published: Optional[date]
    context_label: str


@dataclass(frozen=True)
class DiscoveryPage:
    kind: str
    canonical_path: str
    title: str
    description: str
    heading: str
    breadcrumbs: tuple[DiscoveryLink, ...]
    entity_links: tuple[DiscoveryLink, ...]
    paper_links: tuple[DiscoveryPaperLink, ...]
    robots: str = "index,follow"

    @property
    def canonical_url(self) -> str:
        return f"{PRODUCTION_ORIGIN}{self.canonical_path}"


class DiscoveryPageService:
    """Create discovery documents with a constant, bounded number of queries."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _paper_link(paper: Paper, context: str) -> DiscoveryPaperLink:
        return DiscoveryPaperLink(
            route_identifier=get_paper_route_identifier(
                paper.source, paper.arxiv_id, int(paper.id)
            ),
            title=paper.title,
            published=paper.date_published,
            context_label=context,
        )

    def _papers_for_relation(self, relation, relation_filter, context: str):
        papers = (
            self.db.query(Paper)
            .join(relation, relation.paper_id == Paper.id)
            .filter(relation_filter, eligible_paper_filter())
            .order_by(
                Paper.trending_score.desc().nullslast(),
                Paper.date_published.desc().nullslast(),
                Paper.id.desc(),
            )
            .limit(DISCOVERY_PAPER_LIMIT)
            .all()
        )
        return tuple(self._paper_link(paper, context) for paper in papers)

    def homepage(self) -> DiscoveryPage:
        papers = (
            self.db.query(Paper)
            .filter(eligible_paper_filter())
            .order_by(
                Paper.trending_score.desc().nullslast(),
                Paper.date_published.desc().nullslast(),
                Paper.id.desc(),
            )
            .limit(DISCOVERY_PAPER_LIMIT)
            .all()
        )
        tasks = (
            self.db.query(
                Task.slug, Task.name, func.count(PaperTask.paper_id).label("n")
            )
            .join(PaperTask, PaperTask.task_id == Task.id)
            .filter(Task.slug.is_not(None))
            .group_by(Task.id)
            .order_by(func.count(PaperTask.paper_id).desc(), Task.name.asc())
            .limit(8)
            .all()
        )
        entity_links = [
            DiscoveryLink(f"/tasks/{slug}", name) for slug, name, _ in tasks
        ]
        entity_links.extend(
            [
                DiscoveryLink("/papers/recent", "Recent papers"),
                DiscoveryLink("/papers/archive", "Paper archive"),
                DiscoveryLink("/tasks", "Research tasks"),
                DiscoveryLink("/methods", "Methods"),
            ]
        )
        return DiscoveryPage(
            kind="Homepage",
            canonical_path="/",
            title="Papers with Code — Trending research and open source",
            description=(
                "Discover trending machine-learning papers, methods, benchmarks, "
                "datasets, and open-source implementations."
            ),
            heading="Trending Research",
            breadcrumbs=(),
            entity_links=tuple(entity_links),
            paper_links=tuple(
                self._paper_link(paper, "Trending research") for paper in papers
            ),
        )

    def task(self, slug: str) -> Optional[DiscoveryPage]:
        canonical_slug = canonical_task_slug(slug)
        entity = None
        for candidate in task_slug_candidates(slug):
            entity = self.db.query(Task).filter(Task.slug == candidate).one_or_none()
            if entity is not None:
                break
        if entity is None:
            return None
        related = (
            self.db.query(Task.slug, Task.name)
            .filter(
                Task.slug.is_not(None),
                (Task.parent_id == entity.id) | (Task.id == entity.parent_id),
            )
            .order_by(Task.name.asc())
            .limit(10)
            .all()
        )
        datasets = (
            self.db.query(Dataset.slug, Dataset.name)
            .join(TaskDataset, TaskDataset.dataset_id == Dataset.id)
            .filter(TaskDataset.task_id == entity.id, Dataset.slug.is_not(None))
            .order_by(Dataset.name.asc())
            .limit(10)
            .all()
        )
        links = [DiscoveryLink(f"/tasks/{s}", n) for s, n in related]
        links.extend(DiscoveryLink(f"/benchmark/{s}", n) for s, n in datasets)
        papers = self._papers_for_relation(
            PaperTask, PaperTask.task_id == entity.id, f"Tagged with {entity.name}"
        )
        description = entity.description or (
            f"Research papers, benchmarks, and methods for {entity.name}."
        )
        if entity.research_trends:
            description = f"{description} Current directions include: " + "; ".join(
                str(item) for item in entity.research_trends[:3]
            )
        return self._entity_page(
            "Task", f"/tasks/{canonical_slug}", entity.name, description, links, papers
        )

    def method(self, slug: str) -> Optional[DiscoveryPage]:
        entity = self.db.query(Method).filter(Method.slug == slug).one_or_none()
        if entity is None:
            return None
        links: list[DiscoveryLink] = []
        if entity.source_paper is not None and self._paper_is_eligible(
            entity.source_paper
        ):
            route_id = get_paper_route_identifier(
                entity.source_paper.source,
                entity.source_paper.arxiv_id,
                int(entity.source_paper.id),
            )
            links.append(DiscoveryLink(f"/paper/{route_id}", "Source paper"))
        related_tasks = (
            self.db.query(Task.slug, Task.name)
            .join(PaperTask, PaperTask.task_id == Task.id)
            .join(PaperMethod, PaperMethod.paper_id == PaperTask.paper_id)
            .filter(PaperMethod.method_id == entity.id, Task.slug.is_not(None))
            .distinct()
            .order_by(Task.name)
            .limit(10)
            .all()
        )
        links.extend(DiscoveryLink(f"/tasks/{s}", n) for s, n in related_tasks)
        papers = self._papers_for_relation(
            PaperMethod,
            PaperMethod.method_id == entity.id,
            f"Uses or discusses {entity.name}",
        )
        description = entity.description or (
            f"Source papers and research using the {entity.name} method."
        )
        return self._entity_page(
            "Method", f"/methods/{slug}", entity.name, description, links, papers
        )

    def benchmark(
        self, slug: str, task_slug: str | None = None
    ) -> Optional[DiscoveryPage]:
        entity = self.db.query(Dataset).filter(Dataset.slug == slug).one_or_none()
        if entity is None:
            return None
        tasks = (
            self.db.query(Task.slug, Task.name)
            .join(TaskDataset, TaskDataset.task_id == Task.id)
            .filter(TaskDataset.dataset_id == entity.id, Task.slug.is_not(None))
            .order_by(Task.name.asc())
            .limit(10)
            .all()
        )
        evaluation_query = (
            self.db.query(Paper, Evaluation.model_name, Evaluation.best_metric)
            .join(Evaluation, Evaluation.paper_id == Paper.id)
            .filter(Evaluation.dataset_id == entity.id, eligible_paper_filter())
        )
        if task_slug:
            task = None
            for candidate in task_slug_candidates(task_slug):
                task = self.db.query(Task).filter(Task.slug == candidate).one_or_none()
                if task is not None:
                    break
            if task is None:
                return None
            evaluation_query = evaluation_query.filter(Evaluation.task_id == task.id)
        evaluation_rows = (
            evaluation_query.order_by(
                Evaluation.best_rank.asc().nullslast(),
                Paper.date_published.desc().nullslast(),
                Paper.id.desc(),
            )
            .limit(DISCOVERY_PAPER_LIMIT)
            .all()
        )
        seen: set[int] = set()
        paper_links = []
        for paper, model_name, metric in evaluation_rows:
            if int(paper.id) in seen:
                continue
            seen.add(int(paper.id))
            label = f"Evaluation on {entity.name}"
            context = " · ".join(
                value for value in (label, model_name, metric) if value
            )
            paper_links.append(self._paper_link(paper, context))
        if not paper_links and not task_slug:
            paper_links = list(
                self._papers_for_relation(
                    PaperDataset,
                    PaperDataset.dataset_id == entity.id,
                    f"Reports results on {entity.name}",
                )
            )
        if task_slug and not paper_links:
            return None
        description = (
            entity.description
            or entity.short_description
            or (
                f"Comparable results and research papers for the {entity.name} benchmark."
            )
        )
        return self._entity_page(
            "Benchmark",
            f"/benchmark/{slug}",
            entity.name,
            description,
            [DiscoveryLink(f"/tasks/{s}", n) for s, n in tasks],
            paper_links,
        )

    def conference(self, slug: str) -> Optional[DiscoveryPage]:
        entity = self.db.query(Conference).filter(Conference.slug == slug).one_or_none()
        if entity is None:
            return None
        papers = self._papers_for_relation(
            PaperConference,
            PaperConference.conference_id == entity.id,
            f"Published at {entity.name}",
        )
        tasks = (
            self.db.query(Task.slug, Task.name)
            .join(PaperTask, PaperTask.task_id == Task.id)
            .join(PaperConference, PaperConference.paper_id == PaperTask.paper_id)
            .filter(
                PaperConference.conference_id == entity.id,
                Task.slug.is_not(None),
            )
            .distinct()
            .order_by(Task.name)
            .limit(10)
            .all()
        )
        context = [
            entity.description or f"Accepted and notable papers from {entity.name}."
        ]
        if entity.start_date:
            context.append(f"Starts {entity.start_date.isoformat()}.")
        if entity.venue or entity.location:
            context.append(f"Venue: {entity.venue or entity.location}.")
        return self._entity_page(
            "Conference",
            f"/conferences/{slug}",
            entity.name,
            " ".join(context),
            [DiscoveryLink(f"/tasks/{s}", n) for s, n in tasks],
            papers,
        )

    def conference_task(self, slug: str, task_slug: str) -> Optional[DiscoveryPage]:
        page = self.conference(slug)
        task = self.db.query(Task).filter(Task.slug == task_slug).one_or_none()
        if page is None or task is None:
            return None
        papers = (
            self.db.query(Paper)
            .join(PaperConference, PaperConference.paper_id == Paper.id)
            .join(PaperTask, PaperTask.paper_id == Paper.id)
            .filter(
                PaperConference.conference_id
                == self.db.query(Conference.id)
                .filter(Conference.slug == slug)
                .scalar_subquery(),
                PaperTask.task_id == task.id,
                eligible_paper_filter(),
            )
            .order_by(Paper.date_published.desc().nullslast(), Paper.id.desc())
            .limit(DISCOVERY_PAPER_LIMIT)
            .all()
        )
        if not papers:
            return None
        return replace(
            page,
            paper_links=tuple(
                self._paper_link(paper, f"{task.name} at {page.heading}")
                for paper in papers
            ),
            robots="noindex,follow",
        )

    def organization(self, slug: str) -> Optional[DiscoveryPage]:
        entity = (
            self.db.query(Organization).filter(Organization.slug == slug).one_or_none()
        )
        if entity is None:
            return None
        papers = self._papers_for_relation(
            PaperOrganization,
            PaperOrganization.organization_id == entity.id,
            f"Attributed to {entity.name}",
        )
        description = entity.description or (
            f"Public research papers and topics associated with {entity.name}."
        )
        links = []
        if entity.website_url:
            links.append(DiscoveryLink(entity.website_url, f"{entity.name} website"))
        tasks = (
            self.db.query(Task.slug, Task.name)
            .join(PaperTask, PaperTask.task_id == Task.id)
            .join(
                PaperOrganization,
                PaperOrganization.paper_id == PaperTask.paper_id,
            )
            .filter(
                PaperOrganization.organization_id == entity.id,
                Task.slug.is_not(None),
            )
            .distinct()
            .order_by(Task.name)
            .limit(10)
            .all()
        )
        links.extend(DiscoveryLink(f"/tasks/{s}", n) for s, n in tasks)
        return self._entity_page(
            "Organization", f"/orgs/{slug}", entity.name, description, links, papers
        )

    def organization_task(self, slug: str, task_slug: str) -> Optional[DiscoveryPage]:
        page = self.organization(slug)
        task = self.db.query(Task).filter(Task.slug == task_slug).one_or_none()
        if page is None or task is None:
            return None
        papers = (
            self.db.query(Paper)
            .join(PaperOrganization, PaperOrganization.paper_id == Paper.id)
            .join(PaperTask, PaperTask.paper_id == Paper.id)
            .filter(
                PaperOrganization.organization_id
                == self.db.query(Organization.id)
                .filter(Organization.slug == slug)
                .scalar_subquery(),
                PaperTask.task_id == task.id,
                eligible_paper_filter(),
            )
            .order_by(
                Paper.trending_score.desc().nullslast(),
                Paper.date_published.desc().nullslast(),
                Paper.id.desc(),
            )
            .limit(DISCOVERY_PAPER_LIMIT)
            .all()
        )
        if not papers:
            return None
        return replace(
            page,
            paper_links=tuple(
                self._paper_link(paper, f"{task.name} research from {page.heading}")
                for paper in papers
            ),
            robots="noindex,follow",
        )

    def author(self, author_id: int) -> Optional[DiscoveryPage]:
        entity = self.db.query(Author).filter(Author.id == author_id).one_or_none()
        if entity is None:
            return None
        papers = self._papers_for_relation(
            PaperAuthor,
            PaperAuthor.author_id == entity.id,
            f"Authored by {entity.name}",
        )
        description = f"Research papers authored or co-authored by {entity.name}."
        organizations = (
            self.db.query(Organization.slug, Organization.name)
            .join(
                PaperOrganization, PaperOrganization.organization_id == Organization.id
            )
            .join(PaperAuthor, PaperAuthor.paper_id == PaperOrganization.paper_id)
            .filter(
                PaperAuthor.author_id == entity.id,
            )
            .distinct()
            .order_by(Organization.name)
            .limit(10)
            .all()
        )
        links = [DiscoveryLink(f"/orgs/{slug}", name) for slug, name in organizations]
        if entity.hf_username:
            links.append(
                DiscoveryLink(
                    f"https://huggingface.co/{entity.hf_username}",
                    f"{entity.name} on Hugging Face",
                )
            )
        return self._entity_page(
            "Author", f"/authors/{author_id}", entity.name, description, links, papers
        )

    @staticmethod
    def _paper_is_eligible(paper: Paper) -> bool:
        return bool(
            paper.is_latest_version
            and paper.title
            and paper.title.strip()
            and paper.abstract
            and paper.abstract.strip()
            and (
                (paper.source == "arxiv" and paper.arxiv_id)
                or (paper.source == "external" and paper.source_url)
            )
        )

    @staticmethod
    def _entity_page(kind, path, name, description, links, papers) -> DiscoveryPage:
        return DiscoveryPage(
            kind=kind,
            canonical_path=path,
            title=f"{name} — papers and benchmarks | Papers with Code",
            description=description,
            heading=name,
            breadcrumbs=(
                DiscoveryLink("/", "Home"),
                DiscoveryLink(path.rsplit("/", 1)[0] or "/", f"{kind}s"),
            ),
            entity_links=tuple(links),
            paper_links=tuple(papers),
            robots="index,follow" if papers else "noindex,follow",
        )
