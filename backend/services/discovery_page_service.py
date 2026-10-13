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
    Metric,
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
    TaskDatasetMetric,
)
from backend.services.discovery_text_service import (
    markdown_plain_text,
    meta_description,
)
from backend.services.leaderboard_ranking_service import (
    RankableEvaluation,
    RankableTask,
    rank_leaderboard,
)
from backend.services.conference_service import ConferenceService
from backend.services.dataset_service import DatasetService
from backend.services.sitemap_service import eligible_paper_filter
from backend.utils.urls import get_paper_route_identifier
from backend.utils.task_slugs import canonical_task_slug, task_slug_candidates

PRODUCTION_ORIGIN = "https://paperswithcode.co"
DISCOVERY_PAPER_LIMIT = 20

# Reserved /conferences/{slug}/{listing} paths rendered by ConferenceTaskView
# as presentation and award listings rather than task filters.
CONFERENCE_LISTINGS = {
    "all": "All papers",
    "oral": "Oral papers",
    "spotlight": "Spotlight papers",
    "outstanding": "Outstanding papers",
    "best-paper-finalists": "Best paper finalists",
}
LEADERBOARD_ROW_LIMIT = 100
TASK_BENCHMARK_LIMIT = 50
# Most-evaluated benchmarks summarized in a task page's "Best models" table.
TASK_TOP_MODEL_BENCHMARKS = 5

# Curated landing page for GPT-6 Astra robotics work (/astra-for-robotics).
ASTRA_ROBOTICS_PATH = "/astra-for-robotics"
ASTRA_ROBOTICS_TASK_SLUG = "robotics"
ASTRA_ROBOTICS_METHOD_SLUG = "gpt-6-astra"
ASTRA_ROBOTICS_HEADING = "GPT-6 Astra for Robotics"
ASTRA_ROBOTICS_DESCRIPTION = (
    "Papers, technical reports, and evaluations that use OpenAI's GPT-6 Astra "
    "to control robots, either directly as a robot policy that outputs actions "
    "from camera observations, or as an agent that plans, writes code, and "
    "calls tools or lower-level policies."
)


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
class DiscoveryLeaderboardRow:
    rank: Optional[int]
    model: str
    score: Optional[str]
    paper_route_identifier: Optional[str]
    paper_title: Optional[str]
    published: Optional[date]


@dataclass(frozen=True)
class DiscoveryLeaderboard:
    metric: str
    lower_is_better: bool
    task_name: Optional[str]
    rows: tuple[DiscoveryLeaderboardRow, ...]
    total_rows: int


@dataclass(frozen=True)
class DiscoveryTopModel:
    """The leading model, and leading open model, on one task benchmark."""

    benchmark: DiscoveryLink
    model: str
    open_model: Optional[str]


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
    # Inline Markdown shown in the page body; ``description`` is the short
    # plain-text summary used for meta tags.
    body_markdown: Optional[str] = None
    trends_markdown: tuple[str, ...] = ()
    benchmark_links: tuple[DiscoveryLink, ...] = ()
    leaderboard: Optional[DiscoveryLeaderboard] = None
    top_models: tuple[DiscoveryTopModel, ...] = ()
    top_models_as_of: Optional[date] = None

    @property
    def canonical_url(self) -> str:
        return f"{PRODUCTION_ORIGIN}{self.canonical_path}"


# Index pages that exist for each entity kind's breadcrumb trail.
INDEX_BREADCRUMBS = {
    "Task": DiscoveryLink("/tasks", "Tasks"),
    "Method": DiscoveryLink("/methods", "Methods"),
    "Conference": DiscoveryLink("/conferences", "Conferences"),
    "Organization": DiscoveryLink("/organizations", "Organizations"),
}


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

    def _task_by_slug(self, slug: str) -> Optional[Task]:
        for candidate in task_slug_candidates(slug):
            entity = self.db.query(Task).filter(Task.slug == candidate).one_or_none()
            if entity is not None:
                return entity
        return None

    def task(self, slug: str, today: date | None = None) -> Optional[DiscoveryPage]:
        canonical_slug = canonical_task_slug(slug)
        entity = self._task_by_slug(slug)
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
        # Most-evaluated leaderboards first, so crawlers reach the benchmark
        # pages that carry this task's results.
        evaluation_count = func.count(Evaluation.id)
        benchmarks = (
            self.db.query(Dataset.id, Dataset.slug, Dataset.name, evaluation_count)
            .join(TaskDataset, TaskDataset.dataset_id == Dataset.id)
            .outerjoin(
                Evaluation,
                (Evaluation.dataset_id == Dataset.id)
                & (Evaluation.task_id == entity.id),
            )
            .filter(TaskDataset.task_id == entity.id, Dataset.slug.is_not(None))
            .group_by(Dataset.id)
            .order_by(evaluation_count.desc(), Dataset.name.asc())
            .limit(TASK_BENCHMARK_LIMIT)
            .all()
        )
        links = [DiscoveryLink(f"/tasks/{s}", n) for s, n in related]
        papers = self._papers_for_relation(
            PaperTask, PaperTask.task_id == entity.id, f"Tagged with {entity.name}"
        )
        description = entity.description or (
            f"Research papers, benchmarks, and methods for {entity.name}."
        )
        page = replace(
            self._entity_page(
                "Task",
                f"/tasks/{canonical_slug}",
                entity.name,
                description,
                links,
                papers,
            ),
            trends_markdown=tuple(
                str(item) for item in (entity.research_trends or [])[:3]
            ),
            benchmark_links=tuple(
                DiscoveryLink(f"/benchmark/{s}", n) for _, s, n, _ in benchmarks
            ),
        )
        top_models = self._task_top_models(entity.id, benchmarks)
        if not top_models:
            return page
        as_of = today or date.today()
        month = as_of.strftime("%B %Y")
        leader = top_models[0]
        open_note = (
            f"; the best open model there is {leader.open_model}"
            if leader.open_model and leader.open_model != leader.model
            else ""
        )
        summary = (
            f"{leader.model} leads {leader.benchmark.label} for {entity.name}"
            f"{open_note}. Compare the best {entity.name} models across "
            + f"{len(top_models)} benchmark{'s' if len(top_models) != 1 else ''}"
            + " with papers and code."
        )
        return replace(
            page,
            title=(
                f"Best {entity.name} Models ({month}): leaderboards and papers "
                "| Papers with Code"
            ),
            description=meta_description(summary),
            top_models=top_models,
            top_models_as_of=as_of,
        )

    def _task_top_models(
        self, task_id: int, benchmarks
    ) -> tuple[DiscoveryTopModel, ...]:
        """Summarize the leading models on a task's most-evaluated benchmarks.

        Uses the same best-result selection as the task page's benchmark list,
        so the crawlable summary agrees with what the SPA shows.
        """
        evaluated = [row for row in benchmarks if row[3]][:TASK_TOP_MODEL_BENCHMARKS]
        if not evaluated:
            return ()
        dataset_ids = [int(row[0]) for row in evaluated]
        best = DatasetService(self.db)._best_results_for_datasets(
            dataset_ids, [task_id]
        )
        if not best:
            return ()
        # The open leader must come from the overall leader's metric; an
        # open-only primary metric could name another leaderboard's winner.
        open_leaders: dict[int, str] = {}
        for dataset_id, metric, model_name in (
            self.db.query(
                Evaluation.dataset_id, Evaluation.best_metric, Evaluation.model_name
            )
            .filter(
                Evaluation.dataset_id.in_(dataset_ids),
                Evaluation.task_id == task_id,
                Evaluation.is_open.is_(True),
                Evaluation.model_name.is_not(None),
            )
            .order_by(Evaluation.best_rank.asc().nullslast(), Evaluation.id.asc())
            .all()
        ):
            if dataset_id in best and metric == best[dataset_id]["metric"]:
                open_leaders.setdefault(dataset_id, model_name)
        return tuple(
            DiscoveryTopModel(
                benchmark=DiscoveryLink(f"/benchmark/{slug}", name),
                model=best[dataset_id]["model_name"],
                open_model=open_leaders.get(dataset_id),
            )
            for dataset_id, slug, name, _ in evaluated
            if dataset_id in best
        )

    def astra_for_robotics(self) -> DiscoveryPage:
        """Curated landing page: GPT-6 Astra used for robot control.

        Membership is data-driven: a paper appears when it is tagged with both
        the Robotics task and the GPT-6 Astra method, so curators add papers by
        tagging rather than by editing code.
        """
        task = (
            self.db.query(Task)
            .filter(Task.slug == ASTRA_ROBOTICS_TASK_SLUG)
            .one_or_none()
        )
        method = (
            self.db.query(Method)
            .filter(Method.slug == ASTRA_ROBOTICS_METHOD_SLUG)
            .one_or_none()
        )
        papers: tuple[DiscoveryPaperLink, ...] = ()
        if task is not None and method is not None:
            rows = (
                self.db.query(Paper)
                .join(PaperTask, PaperTask.paper_id == Paper.id)
                .join(PaperMethod, PaperMethod.paper_id == Paper.id)
                .filter(
                    PaperTask.task_id == task.id,
                    PaperMethod.method_id == method.id,
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
            papers = tuple(
                self._paper_link(paper, "GPT-6 Astra for robotics") for paper in rows
            )
        links = (
            DiscoveryLink(f"/methods/{ASTRA_ROBOTICS_METHOD_SLUG}", "GPT-6 Astra"),
            DiscoveryLink(f"/tasks/{ASTRA_ROBOTICS_TASK_SLUG}", "Robotics"),
        )
        return DiscoveryPage(
            kind="Collection",
            canonical_path=ASTRA_ROBOTICS_PATH,
            title=f"{ASTRA_ROBOTICS_HEADING} | Papers with Code",
            description=ASTRA_ROBOTICS_DESCRIPTION,
            heading=ASTRA_ROBOTICS_HEADING,
            breadcrumbs=(DiscoveryLink("/", "Home"),),
            entity_links=links,
            paper_links=papers,
            robots="index,follow" if papers else "noindex,follow",
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
        requested = None
        if task_slug:
            requested = self._task_by_slug(task_slug)
            if requested is None:
                return None
        tasks = [
            RankableTask(int(task_id), task_slug_value, name)
            for task_id, task_slug_value, name in (
                self.db.query(Task.id, Task.slug, Task.name)
                .join(TaskDataset, TaskDataset.task_id == Task.id)
                .filter(TaskDataset.dataset_id == entity.id)
                .order_by(Task.name.asc())
                .all()
            )
        ]
        # Same rows and order as the SPA's `ordering=best_rank` request.
        evaluations = [
            RankableEvaluation(
                id=int(row.id),
                paper_id=int(row.paper_id),
                task_id=int(row.task_id),
                model_name=row.model_name,
                harness=row.harness,
                metrics=row.metrics or {},
                best_metric=row.best_metric,
                best_rank=row.best_rank,
            )
            for row in self.db.query(
                Evaluation.id,
                Evaluation.paper_id,
                Evaluation.task_id,
                Evaluation.model_name,
                Evaluation.harness,
                Evaluation.metrics,
                Evaluation.best_metric,
                Evaluation.best_rank,
            )
            .filter(Evaluation.dataset_id == entity.id)
            .order_by(
                Evaluation.best_rank.asc().nullslast(),
                Evaluation.best_metric.asc().nullslast(),
                Evaluation.id.asc(),
            )
            .all()
        ]
        # A task filter needs the leaderboard association or evaluations.
        if requested is not None:
            task_ids = {task.id for task in tasks}
            task_ids.update(evaluation.task_id for evaluation in evaluations)
            if requested.id not in task_ids:
                return None
        configured: dict[int, list[str]] = {}
        for task_id, metric_name in (
            self.db.query(TaskDatasetMetric.task_id, Metric.name)
            .join(Metric, Metric.id == TaskDatasetMetric.metric_id)
            .filter(TaskDatasetMetric.dataset_id == entity.id)
            .order_by(Metric.name.ilike("%overall%").desc(), Metric.name.asc())
            .all()
        ):
            configured.setdefault(int(task_id), []).append(metric_name)
        metric_names = {name for names in configured.values() for name in names}
        for evaluation in evaluations:
            metric_names.update(evaluation.metrics)
        directions = dict(
            self.db.query(Metric.name, Metric.direction)
            .filter(Metric.name.in_(metric_names))
            .all()
            if metric_names
            else []
        )
        ranked = rank_leaderboard(
            tasks=tasks,
            evaluations=evaluations,
            configured_metrics=configured,
            directions=directions,
            task_slug=requested.slug if requested is not None else None,
        )
        shown = ranked.rows[:LEADERBOARD_ROW_LIMIT]
        paper_ids = {row.entry.first.paper_id for row in shown}
        papers = {
            int(paper.id): paper
            for paper in (
                self.db.query(
                    Paper.id,
                    Paper.title,
                    Paper.source,
                    Paper.arxiv_id,
                    Paper.date_published,
                    eligible_paper_filter().label("eligible"),
                )
                .filter(Paper.id.in_(paper_ids))
                .all()
                if paper_ids
                else []
            )
        }
        rows = []
        paper_links: list[DiscoveryPaperLink] = []
        for row in shown:
            first = row.entry.first
            paper = papers.get(first.paper_id)
            model = first.model_name or (paper.title if paper else "") or "—"
            route = None
            if paper is not None and paper.eligible:
                route = get_paper_route_identifier(
                    paper.source, paper.arxiv_id, int(paper.id)
                )
                if len(paper_links) < DISCOVERY_PAPER_LIMIT and all(
                    link.route_identifier != route for link in paper_links
                ):
                    paper_links.append(
                        DiscoveryPaperLink(
                            route,
                            paper.title,
                            paper.date_published,
                            " · ".join(
                                value
                                for value in (
                                    f"Evaluation on {entity.name}",
                                    first.model_name,
                                    ranked.metric,
                                )
                                if value
                            ),
                        )
                    )
            rows.append(
                DiscoveryLeaderboardRow(
                    rank=row.rank,
                    model=model,
                    score=None if row.raw_value is None else str(row.raw_value),
                    paper_route_identifier=route,
                    paper_title=paper.title if paper else None,
                    published=paper.date_published if paper else None,
                )
            )
        if not paper_links and not task_slug:
            paper_links = list(
                self._papers_for_relation(
                    PaperDataset,
                    PaperDataset.dataset_id == entity.id,
                    f"Reports results on {entity.name}",
                )
            )
        body = (
            entity.description
            or entity.short_description
            or (
                f"Comparable results and research papers for the {entity.name} benchmark."
            )
        )
        leader = rows[0] if rows and rows[0].rank == 1 else None
        if leader is not None:
            scope = f"{ranked.task.name} results" if ranked.task else "results"
            description = meta_description(
                f"{leader.model} leads the {entity.name} leaderboard with "
                f"{ranked.metric} {leader.score}. Compare {len(ranked.rows)} "
                f"ranked {scope} with papers and code."
            )
        else:
            description = meta_description(markdown_plain_text(body))
        breadcrumbs = [DiscoveryLink("/", "Home"), INDEX_BREADCRUMBS["Task"]]
        if ranked.task is not None and ranked.task.slug:
            breadcrumbs.append(
                DiscoveryLink(f"/tasks/{ranked.task.slug}", ranked.task.name)
            )
        return DiscoveryPage(
            kind="Benchmark",
            canonical_path=f"/benchmark/{slug}",
            title=(
                f"{entity.name} Leaderboard: state of the art results "
                "| Papers with Code"
            ),
            description=description,
            heading=entity.name,
            breadcrumbs=tuple(breadcrumbs),
            entity_links=tuple(
                DiscoveryLink(f"/tasks/{task.slug}", task.name)
                for task in tasks[:10]
                if task.slug
            ),
            paper_links=tuple(paper_links),
            robots="index,follow" if paper_links else "noindex,follow",
            body_markdown=body,
            leaderboard=DiscoveryLeaderboard(
                metric=ranked.metric,
                lower_is_better=ranked.lower_is_better,
                task_name=ranked.task.name if ranked.task else None,
                rows=tuple(rows),
                total_rows=len(ranked.rows),
            )
            if rows
            else None,
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

    def conference_listing(self, slug: str, listing: str) -> Optional[DiscoveryPage]:
        page = self.conference(slug)
        if page is None:
            return None
        conference = self.db.query(Conference).filter(Conference.slug == slug).one()
        query = (
            self.db.query(Paper)
            .join(PaperConference, PaperConference.paper_id == Paper.id)
            .filter(
                PaperConference.conference_id == conference.id,
                eligible_paper_filter(),
            )
        )
        if listing in ("oral", "spotlight"):
            query = query.filter(
                Paper.proceeding == f"{conference.name} {listing.capitalize()}"
            )
        elif listing == "outstanding":
            query = query.filter(
                PaperConference.award.in_(ConferenceService.OUTSTANDING_AWARDS)
            )
        elif listing == "best-paper-finalists":
            query = query.filter(
                PaperConference.award == ConferenceService.BEST_PAPER_FINALIST_AWARD
            )
        papers = (
            query.order_by(
                Paper.trending_score.desc().nullslast(),
                Paper.date_published.desc().nullslast(),
                Paper.id.desc(),
            )
            .limit(DISCOVERY_PAPER_LIMIT)
            .all()
        )
        label = CONFERENCE_LISTINGS[listing]
        return replace(
            page,
            paper_links=tuple(
                self._paper_link(paper, f"{label} at {page.heading}")
                for paper in papers
            ),
            robots="noindex,follow",
        )

    def conference_task(self, slug: str, task_slug: str) -> Optional[DiscoveryPage]:
        if task_slug in CONFERENCE_LISTINGS:
            return self.conference_listing(slug, task_slug)
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
        index = INDEX_BREADCRUMBS.get(kind)
        return DiscoveryPage(
            kind=kind,
            canonical_path=path,
            title=f"{name} — papers and benchmarks | Papers with Code",
            description=meta_description(markdown_plain_text(description)),
            heading=name,
            breadcrumbs=(DiscoveryLink("/", "Home"),) + ((index,) if index else ()),
            body_markdown=description,
            entity_links=tuple(links),
            paper_links=tuple(papers),
            robots="index,follow" if papers else "noindex,follow",
        )
