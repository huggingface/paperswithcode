"""Daily review of agent-reported benchmark gaps and their scoped creation jobs.

Scheduled add-evals jobs report benchmarks they could not score against as
``BenchmarkCurationCandidate`` rows. Once a day an overseer job reviews every
eligible candidate together (approve, merge duplicates, reject, defer), and
each approved candidate gets one ``add-benchmark`` job that researches the
source paper, task, and metrics. The backend validates and writes every
catalog row itself, then requeues add-evals for the papers that reported the
gap.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.curation import (
    AddBenchmarkMutation,
    BenchmarkMetricChoice,
    BenchmarkSourcePaper,
    NewBenchmarkDataset,
    ReviewBenchmarkGapsMutation,
)
from backend.models.database import (
    BenchmarkCurationCandidate,
    BenchmarkCurationEvidence,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperCurationJob,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.benchmark_gap_service import BenchmarkGapService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_ingestion_service import PaperIngestionService
from backend.services.trending_model_resolution_service import (
    TrendingModelResolutionService,
)
from backend.utils.slug_utils import slugify
from backend.utils.urls import get_paper_route_identifier

TRIGGER = "benchmark-gap-cron"
POLICY_VERSION = "benchmark-gap-v1"
MIN_DISTINCT_PAPERS = 3
ELIGIBLE_CONFIDENCE = ("high", "medium")
# The remote runner gives Codex 20 minutes; this bounds the overseer's reading.
REVIEW_BATCH_LIMIT = 150
DAILY_CREATION_CAP = 20
DEFER_DAYS = 14
FAILURE_RETRY_DAYS = 3
MAX_CREATION_FAILURES = 2
REVIEW_PRIORITY = 10
CREATION_PRIORITY = 20
RECHECK_PRIORITY = 60
ACTIVE_JOB_STATUSES = ("queued", "dispatching", "running")


def _now() -> datetime:
    return datetime.now(UTC)


def _name_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _utc_midnight(now: datetime) -> datetime:
    return datetime.combine(now.date(), datetime.min.time(), UTC)


def _paper_url(paper: Paper) -> str:
    route = get_paper_route_identifier(paper.source, paper.arxiv_id, paper.id)
    return f"https://paperswithcode.co/paper/{route}"


class BenchmarkGapReviewService:
    def __init__(self, db: Session, settings: Settings, job_service=None) -> None:
        if job_service is None:
            from backend.services.codex_add_evals_service import (  # noqa: PLC0415
                codex_paper_job_service,
            )

            job_service = codex_paper_job_service
        self.db = db
        self.settings = settings
        self.job_service = job_service

    # Eligibility and scheduling

    def eligible_query(self, now: datetime | None = None):
        """Candidates the overseer may decide on, strongest evidence first."""
        now = now or _now()
        candidate = BenchmarkCurationCandidate
        return (
            self.db.query(candidate)
            .filter(
                candidate.distinct_paper_count >= MIN_DISTINCT_PAPERS,
                candidate.confidence.in_(ELIGIBLE_CONFIDENCE),
                or_(
                    and_(
                        candidate.status == "candidate",
                        or_(
                            candidate.deferred_until.is_(None),
                            candidate.deferred_until <= now,
                        ),
                    ),
                    and_(
                        candidate.status == "rejected",
                        candidate.reviewed_paper_count.isnot(None),
                        candidate.distinct_paper_count
                        >= 2 * candidate.reviewed_paper_count,
                    ),
                ),
            )
            .order_by(
                candidate.distinct_paper_count.desc(),
                candidate.last_seen_at.desc(),
                candidate.id,
            )
        )

    def _active_job(self, kind: str, **scope) -> PaperCurationJob | None:
        query = self.db.query(PaperCurationJob).filter(
            PaperCurationJob.kind == kind,
            PaperCurationJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        for field, value in scope.items():
            query = query.filter(getattr(PaperCurationJob, field) == value)
        return query.first()

    def _jobs_created_since(self, kind: str, since: datetime) -> int:
        return (
            self.db.query(func.count(PaperCurationJob.id))
            .filter(
                PaperCurationJob.kind == kind,
                PaperCurationJob.trigger == TRIGGER,
                PaperCurationJob.created_at >= since,
            )
            .scalar()
            or 0
        )

    def _approved_ready(self, now: datetime, limit: int):
        candidate = BenchmarkCurationCandidate
        active = (
            self.db.query(PaperCurationJob.id)
            .filter(
                PaperCurationJob.benchmark_candidate_id == candidate.id,
                PaperCurationJob.kind == "add-benchmark",
                PaperCurationJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .exists()
        )
        return (
            self.db.query(candidate)
            .filter(
                candidate.status == "approved",
                or_(
                    candidate.deferred_until.is_(None), candidate.deferred_until <= now
                ),
                ~active,
            )
            .order_by(candidate.distinct_paper_count.desc(), candidate.id)
            .limit(max(limit, 0))
            .all()
        )

    def queue_approved_creations(self, now: datetime | None = None) -> list[str]:
        """Queue add-benchmark jobs for approved candidates within the daily cap."""
        now = now or _now()
        used = self._jobs_created_since("add-benchmark", _utc_midnight(now))
        queued = []
        for candidate in self._approved_ready(now, DAILY_CREATION_CAP - used):
            job = self.job_service.enqueue_benchmark_job(
                self.db,
                kind="add-benchmark",
                benchmark_candidate_id=candidate.id,
                requested_by=TRIGGER,
                settings=self.settings,
                priority=CREATION_PRIORITY,
            )
            queued.append(str(job.id))
        return queued

    def reconcile(self, *, dispatch: bool = True, dry_run: bool = False) -> dict:
        """Daily CRON entrypoint: drain approved work, then start one review."""
        now = _now()
        eligible = self.eligible_query(now).count()
        review_due = (
            eligible > 0
            and self._active_job("review-benchmark-gaps") is None
            and self._jobs_created_since("review-benchmark-gaps", _utc_midnight(now))
            == 0
        )
        result: dict[str, Any] = {
            "eligible_candidates": eligible,
            "review_due": review_due,
            "dry_run": dry_run,
        }
        if dry_run:
            used = self._jobs_created_since("add-benchmark", _utc_midnight(now))
            result["approved_ready"] = len(
                self._approved_ready(now, DAILY_CREATION_CAP - used)
            )
            return result
        result["creation_jobs_queued"] = self.queue_approved_creations(now)
        if review_due:
            job = self.job_service.enqueue_benchmark_job(
                self.db,
                kind="review-benchmark-gaps",
                benchmark_candidate_id=None,
                requested_by=TRIGGER,
                settings=self.settings,
                priority=REVIEW_PRIORITY,
            )
            result["review_job_id"] = str(job.id)
        self.db.commit()
        if dispatch:
            self.job_service.dispatch_next(self.db, self.settings)
        return result

    def status(self) -> dict:
        now = _now()
        counts = dict(
            self.db.query(
                BenchmarkCurationCandidate.status,
                func.count(BenchmarkCurationCandidate.id),
            )
            .group_by(BenchmarkCurationCandidate.status)
            .all()
        )
        return {
            "candidates_by_status": counts,
            "eligible_candidates": self.eligible_query(now).count(),
            "creation_jobs_today": self._jobs_created_since(
                "add-benchmark", _utc_midnight(now)
            ),
            "daily_creation_cap": DAILY_CREATION_CAP,
        }

    # Context for the remote jobs

    def _evidence_by_candidate(self, candidate_ids: list[uuid.UUID]) -> dict:
        grouped: dict[uuid.UUID, list[BenchmarkCurationEvidence]] = {}
        if not candidate_ids:
            return grouped
        for row in (
            self.db.query(BenchmarkCurationEvidence)
            .filter(BenchmarkCurationEvidence.candidate_id.in_(candidate_ids))
            .order_by(BenchmarkCurationEvidence.created_at)
        ):
            grouped.setdefault(row.candidate_id, []).append(row)
        return grouped

    def _task_labels(self, task_ids: set[int]) -> dict[int, dict]:
        if not task_ids:
            return {}
        tasks = self.db.query(Task).filter(Task.id.in_(task_ids)).all()
        parents = {
            task.id: task
            for task in self.db.query(Task).filter(
                Task.id.in_({task.parent_id for task in tasks if task.parent_id})
            )
        }
        return {
            int(task.id): {
                "id": int(task.id),
                "name": task.name,
                "slug": task.slug,
                "parent": (
                    {"id": int(task.parent_id), "name": parents[task.parent_id].name}
                    if task.parent_id in parents
                    else None
                ),
            }
            for task in tasks
        }

    def _dataset_index(self) -> dict[str, set[int]]:
        index: dict[str, set[int]] = {}
        for dataset_id, name, full_name, slug in self.db.query(
            Dataset.id, Dataset.name, Dataset.full_name, Dataset.slug
        ):
            for value in (name, full_name, slug):
                key = _name_key(value)
                if key:
                    index.setdefault(key, set()).add(int(dataset_id))
        return index

    def _dataset_summaries(self, dataset_ids: set[int]) -> dict[int, dict]:
        if not dataset_ids:
            return {}
        summaries = {
            int(dataset.id): {
                "id": int(dataset.id),
                "name": dataset.name,
                "full_name": dataset.full_name,
                "introducing_paper_id": dataset.introducing_paper_id,
                "description": (dataset.short_description or dataset.description or "")[
                    :300
                ]
                or None,
                "leaderboards": [],
            }
            for dataset in self.db.query(Dataset).filter(Dataset.id.in_(dataset_ids))
        }
        leaderboards: dict[tuple[int, int], dict] = {}
        for task_dataset, task in (
            self.db.query(TaskDataset, Task)
            .join(Task, Task.id == TaskDataset.task_id)
            .filter(TaskDataset.dataset_id.in_(dataset_ids))
        ):
            entry = {"task_id": int(task.id), "task_name": task.name, "metrics": []}
            leaderboards[(int(task.id), int(task_dataset.dataset_id))] = entry
            summaries[int(task_dataset.dataset_id)]["leaderboards"].append(entry)
        for link, metric in (
            self.db.query(TaskDatasetMetric, Metric)
            .join(Metric, Metric.id == TaskDatasetMetric.metric_id)
            .filter(TaskDatasetMetric.dataset_id.in_(dataset_ids))
        ):
            entry = leaderboards.get((int(link.task_id), int(link.dataset_id)))
            if entry is not None:
                entry["metrics"].append(metric.name)
        return summaries

    def _catalog_matches(
        self, names: list[str], index: dict[str, set[int]]
    ) -> set[int]:
        matches: set[int] = set()
        for name in names:
            matches.update(index.get(_name_key(name), set()))
        return matches

    def _candidate_summary(
        self,
        candidate: BenchmarkCurationCandidate,
        evidence: list[BenchmarkCurationEvidence],
        tasks: dict[int, dict],
        papers: dict[int, Paper],
        catalog: dict[int, dict],
        index: dict[str, set[int]],
    ) -> dict:
        metrics: Counter[tuple[str, str]] = Counter()
        sources: Counter[str] = Counter()
        source_details: dict[str, dict] = {}
        splits: Counter[str] = Counter()
        recommendations: Counter[str] = Counter()
        near_matches: dict[int, str | None] = {}
        why = None
        for row in evidence:
            payload = row.payload or {}
            protocol = payload.get("protocol") or {}
            for metric in protocol.get("metrics") or []:
                if isinstance(metric, dict) and metric.get("name"):
                    metrics[(metric["name"], metric.get("direction") or "")] += 1
            splits.update(value for value in protocol.get("splits") or [] if value)
            proposed = payload.get("proposed_benchmark") or {}
            for source in proposed.get("canonical_sources") or []:
                if isinstance(source, dict) and source.get("url"):
                    sources[source["url"]] += 1
                    source_details.setdefault(
                        source["url"],
                        {"kind": source.get("kind"), "title": source.get("title")},
                    )
            for match in (payload.get("catalog_search") or {}).get(
                "near_matches"
            ) or []:
                if isinstance(match, dict) and match.get("dataset_id"):
                    near_matches[int(match["dataset_id"])] = match.get(
                        "rejection_reason"
                    )
            assessment = payload.get("assessment") or {}
            recommendations[assessment.get("recommendation") or "unknown"] += 1
            why = why or assessment.get("why_worth_adding")
        exact = self._catalog_matches(
            [candidate.canonical_name, *(candidate.aliases or [])], index
        )
        paper_ids = sorted({int(row.paper_id) for row in evidence})
        return {
            "id": str(candidate.id),
            "name": candidate.canonical_name,
            "gap_type": candidate.gap_type,
            "status": candidate.status,
            "aliases": list(candidate.aliases or []),
            "distinct_paper_count": candidate.distinct_paper_count,
            "confidence": candidate.confidence,
            "last_seen_at": candidate.last_seen_at.isoformat()
            if candidate.last_seen_at
            else None,
            "reported_tasks": [
                tasks[task_id]
                for task_id in candidate.task_ids or []
                if task_id in tasks
            ],
            "reported_metrics": [
                {"name": name, "direction": direction, "papers": count}
                for (name, direction), count in metrics.most_common(6)
            ],
            "reported_splits": [value for value, _ in splits.most_common(5)],
            "reported_sources": [
                {"url": url, **source_details[url], "papers": count}
                for url, count in sources.most_common(5)
            ],
            "recommendations": dict(recommendations),
            "why_worth_adding": (why or "")[:400] or None,
            "evidence_papers": [
                {"id": paper_id, "title": papers[paper_id].title}
                for paper_id in paper_ids[:5]
                if paper_id in papers
            ],
            "catalog_name_matches": [
                catalog[dataset_id]
                for dataset_id in sorted(exact)
                if dataset_id in catalog
            ],
            "agent_near_matches": [
                {"dataset_id": dataset_id, "reported_rejection": reason}
                for dataset_id, reason in list(near_matches.items())[:5]
            ],
            "previous_review": (
                {"status": candidate.status, "reason": candidate.review_reason}
                if candidate.reviewed_at is not None
                else None
            ),
        }

    def _summaries(self, candidates: list[BenchmarkCurationCandidate]) -> list[dict]:
        evidence = self._evidence_by_candidate([item.id for item in candidates])
        tasks = self._task_labels(
            {task_id for item in candidates for task_id in item.task_ids or []}
        )
        paper_ids = {int(row.paper_id) for rows in evidence.values() for row in rows}
        papers = (
            {
                int(paper.id): paper
                for paper in self.db.query(Paper).filter(Paper.id.in_(paper_ids))
            }
            if paper_ids
            else {}
        )
        index = self._dataset_index()
        matched = set()
        for item in candidates:
            matched |= self._catalog_matches(
                [item.canonical_name, *(item.aliases or [])], index
            )
        catalog = self._dataset_summaries(matched)
        return [
            self._candidate_summary(
                item, evidence.get(item.id, []), tasks, papers, catalog, index
            )
            for item in candidates
        ]

    def review_context(self) -> dict:
        now = _now()
        query = self.eligible_query(now)
        candidates = query.limit(REVIEW_BATCH_LIMIT).all()
        return {
            "policy": {
                "min_distinct_papers": MIN_DISTINCT_PAPERS,
                "eligible_total": query.count(),
                "batch_limit": REVIEW_BATCH_LIMIT,
                "daily_creation_cap": DAILY_CREATION_CAP,
                "creation_jobs_today": self._jobs_created_since(
                    "add-benchmark", _utc_midnight(now)
                ),
            },
            "candidates": self._summaries(candidates),
        }

    def creation_context(self, row: PaperCurationJob) -> dict:
        candidate = self.db.get(BenchmarkCurationCandidate, row.benchmark_candidate_id)
        if candidate is None:
            raise LookupError("Benchmark candidate not found")
        evidence = self._evidence_by_candidate([candidate.id]).get(candidate.id, [])
        summary = self._summaries([candidate])[0]
        task_ids = set(candidate.task_ids or [])
        children = (
            {
                int(task.id)
                for task in self.db.query(Task).filter(Task.parent_id.in_(task_ids))
            }
            if task_ids
            else set()
        )
        papers = (
            {
                int(paper.id): paper
                for paper in self.db.query(Paper).filter(
                    Paper.id.in_({int(item.paper_id) for item in evidence})
                )
            }
            if evidence
            else {}
        )
        reports = []
        for item in evidence[:20]:
            payload = item.payload or {}
            paper = papers.get(int(item.paper_id))
            reports.append(
                {
                    "paper_id": int(item.paper_id),
                    "paper_title": paper.title if paper else None,
                    "paper_arxiv_id": paper.arxiv_id if paper else None,
                    "proposed_benchmark": payload.get("proposed_benchmark"),
                    "protocol": payload.get("protocol"),
                    "catalog_search": payload.get("catalog_search"),
                    "blocked_evaluations": [
                        {
                            key: value
                            for key, value in blocked.items()
                            if key in {"model_name", "split", "metrics", "best_metric"}
                        }
                        for blocked in (payload.get("blocked_evaluations") or [])[:3]
                        if isinstance(blocked, dict)
                    ],
                    "assessment": payload.get("assessment"),
                }
            )
        return {
            "candidate": summary,
            "overseer_reason": candidate.review_reason,
            "reports": reports,
            "related_tasks": list(self._task_labels(task_ids | children).values()),
        }

    def catalog_search(self, query: str) -> dict:
        """Datasets (configured or not), tasks, and metrics for a creation job."""
        pattern = f"%{query}%"
        key = _name_key(query)
        datasets = (
            self.db.query(Dataset.id)
            .filter(
                or_(
                    Dataset.name.ilike(pattern),
                    Dataset.full_name.ilike(pattern),
                    Dataset.slug.ilike(f"%{slugify(query)}%"),
                )
            )
            .order_by(Dataset.name)
            .limit(20)
            .all()
        )
        metrics = (
            self.db.query(Metric)
            .filter(or_(Metric.name.ilike(pattern), Metric.full_name.ilike(pattern)))
            .order_by(Metric.name)
            .limit(20)
            .all()
        )
        tasks = (
            self.db.query(Task)
            .filter(or_(Task.name.ilike(pattern), Task.slug.ilike(pattern)))
            .order_by(Task.name)
            .limit(20)
            .all()
        )
        return {
            "query": query,
            "datasets": list(
                self._dataset_summaries({int(item.id) for item in datasets}).values()
            ),
            "tasks": list(self._task_labels({int(task.id) for task in tasks}).values()),
            "metrics": [
                {
                    "id": int(metric.id),
                    "name": metric.name,
                    "full_name": metric.full_name,
                    "direction": metric.direction,
                    "scale": metric.scale,
                    "exact_name_match": _name_key(metric.name) == key,
                }
                for metric in metrics
            ],
        }

    # Overseer decisions

    def apply_review(
        self,
        mutation: ReviewBenchmarkGapsMutation,
        *,
        reported_before: datetime | None = None,
    ) -> dict:
        """Apply one decision per candidate in the review batch.

        Every batch candidate first reported before ``reported_before`` (the
        review job's creation) must be decided; later arrivals wait a day.
        """
        now = _now()
        eligible = {item.id for item in self.eligible_query(now).all()}
        decided = {item.candidate_id for item in mutation.decisions}
        missing = [
            str(item.id)
            for item in self.eligible_query(now).limit(REVIEW_BATCH_LIMIT)
            if item.id not in decided
            and (reported_before is None or item.first_seen_at < reported_before)
        ]
        if missing:
            raise ValueError(
                f"Decide every candidate in context.review.candidates; "
                f"{len(missing)} have no decision: {', '.join(missing[:20])}"
                + (" ..." if len(missing) > 20 else "")
            )
        merge_sources = {
            item.candidate_id for item in mutation.decisions if item.decision == "merge"
        }
        counts: Counter[str] = Counter()
        for decision in mutation.decisions:
            candidate = self.db.get(BenchmarkCurationCandidate, decision.candidate_id)
            if candidate is None or candidate.id not in eligible:
                raise ValueError(
                    f"Candidate {decision.candidate_id} is not eligible for review"
                )
            candidate.review_reason = decision.reason
            # Database time, like the created_at of jobs queued in this transaction.
            candidate.reviewed_at = func.now()
            if decision.decision == "approve":
                candidate.status = "approved"
                candidate.deferred_until = None
            elif decision.decision == "reject":
                candidate.status = "rejected"
                candidate.reviewed_paper_count = candidate.distinct_paper_count
            elif decision.decision == "defer":
                candidate.status = "candidate"
                candidate.deferred_until = now + timedelta(days=DEFER_DAYS)
            else:
                if decision.merge_into_candidate_id in merge_sources:
                    raise ValueError(
                        f"Candidate {decision.candidate_id} cannot merge into "
                        f"{decision.merge_into_candidate_id}, which is itself merged"
                    )
                target = self.db.get(
                    BenchmarkCurationCandidate, decision.merge_into_candidate_id
                )
                if target is None or target.status not in {
                    "candidate",
                    "approved",
                    "promoted",
                }:
                    raise ValueError(
                        f"Merge target {decision.merge_into_candidate_id} is not an "
                        "open or promoted candidate"
                    )
                self._merge(candidate, target)
                if target.status == "promoted":
                    # The leaderboard exists already; score the new papers.
                    self.db.flush()
                    BenchmarkGapService(self.db).enqueue_evidence_rechecks(
                        target,
                        trigger=TRIGGER,
                        priority=RECHECK_PRIORITY,
                        settings=self.settings,
                        job_service=self.job_service,
                    )
            counts[decision.decision] += 1
        self.db.flush()
        return {
            "status": "applied",
            "decisions": dict(counts),
            "summary": mutation.summary,
            "creation_jobs_queued": self.queue_approved_creations(now),
        }

    def _merge(
        self, source: BenchmarkCurationCandidate, target: BenchmarkCurationCandidate
    ) -> None:
        for evidence in (
            self.db.query(BenchmarkCurationEvidence)
            .filter(BenchmarkCurationEvidence.candidate_id == source.id)
            .all()
        ):
            duplicate = (
                self.db.query(BenchmarkCurationEvidence.id)
                .filter(
                    BenchmarkCurationEvidence.candidate_id == target.id,
                    BenchmarkCurationEvidence.paper_id == evidence.paper_id,
                    BenchmarkCurationEvidence.job_id == evidence.job_id,
                )
                .first()
            )
            if duplicate is None:
                evidence.candidate_id = target.id
            else:
                self.db.delete(evidence)
        self.db.flush()
        target.aliases = sorted(
            {*(target.aliases or []), *(source.aliases or []), source.canonical_name}
            - {target.canonical_name}
        )
        target.task_ids = sorted({*(target.task_ids or []), *(source.task_ids or [])})
        target.distinct_paper_count = self._distinct_papers(target.id)
        target.last_seen_at = max(target.last_seen_at, source.last_seen_at)
        source.status = "merged"
        source.merged_into_id = target.id
        source.distinct_paper_count = 0

    def _distinct_papers(self, candidate_id: uuid.UUID) -> int:
        return int(
            self.db.query(func.count(func.distinct(BenchmarkCurationEvidence.paper_id)))
            .filter(BenchmarkCurationEvidence.candidate_id == candidate_id)
            .scalar()
            or 0
        )

    # Benchmark creation

    def apply_add_benchmark(
        self, row: PaperCurationJob, mutation: AddBenchmarkMutation
    ) -> dict:
        candidate = self.db.get(BenchmarkCurationCandidate, row.benchmark_candidate_id)
        if candidate is None:
            raise LookupError("Benchmark candidate not found")
        if candidate.status != "approved":
            raise ValueError(
                f"Candidate {candidate.id} is {candidate.status}, not approved"
            )
        now = _now()
        candidate.review_reason = mutation.reason
        # Database time, like the created_at of jobs queued in this transaction.
        candidate.reviewed_at = func.now()
        if mutation.decision == "reject":
            candidate.status = "rejected"
            candidate.reviewed_paper_count = candidate.distinct_paper_count
            return {"status": "rejected", "candidate_id": str(candidate.id)}
        if mutation.decision == "defer":
            candidate.deferred_until = now + timedelta(days=DEFER_DAYS)
            return {"status": "deferred", "candidate_id": str(candidate.id)}

        created: dict[str, Any] = {"metric_ids": [], "task_dataset_metric_ids": []}
        task = self._resolve_task(mutation, created)
        metrics = [self._resolve_metric(choice, created) for choice in mutation.metrics]
        if len({metric.id for metric in metrics}) != len(metrics):
            raise ValueError("Leaderboard metrics must be distinct")
        paper = None
        if mutation.decision == "create":
            paper = self._resolve_source_paper(
                mutation.source_paper, mutation.evidence_urls
            )
            dataset = self._create_dataset(mutation.new_dataset, paper)
            created["dataset"] = True
        else:
            dataset = self.db.get(Dataset, mutation.existing_dataset_id)
            if dataset is None:
                raise ValueError(f"Dataset {mutation.existing_dataset_id} not found")
            created["dataset"] = False
            if dataset.introducing_paper_id is not None:
                paper = self.db.get(Paper, dataset.introducing_paper_id)
            elif mutation.source_paper is not None:
                paper = self._resolve_source_paper(
                    mutation.source_paper, mutation.evidence_urls
                )
                dataset.introducing_paper_id = paper.id
                dataset.introducing_paper_title = paper.title
                dataset.paper_url = _paper_url(paper)
                created["introducing_paper_set"] = True
        created["paper_task"] = False
        if paper is not None and self.db.get(PaperTask, (paper.id, task.id)) is None:
            self.db.add(PaperTask(paper_id=paper.id, task_id=task.id, source="auto"))
            created["paper_task"] = True
        created["task_dataset"] = (
            self.db.get(TaskDataset, (task.id, dataset.id)) is None
        )
        if created["task_dataset"]:
            self.db.add(
                TaskDataset(
                    task_id=task.id,
                    dataset_id=dataset.id,
                    supports_harness=mutation.supports_harness,
                )
            )
        for metric in metrics:
            if self.db.get(TaskDatasetMetric, (task.id, dataset.id, metric.id)) is None:
                self.db.add(
                    TaskDatasetMetric(
                        task_id=task.id, dataset_id=dataset.id, metric_id=metric.id
                    )
                )
                created["task_dataset_metric_ids"].append(int(metric.id))
        self.db.flush()
        if self.db.get(TaskDataset, (task.id, dataset.id)) is None or any(
            self.db.get(TaskDatasetMetric, (task.id, dataset.id, metric.id)) is None
            for metric in metrics
        ):
            raise ValueError("Post-write leaderboard verification failed")

        candidate.status = "promoted"
        candidate.promoted_at = now
        candidate.deferred_until = None
        candidate.resolution = {
            "job_id": str(row.id),
            "decision": mutation.decision,
            "dataset_id": int(dataset.id),
            "task_id": int(task.id),
            "metric_ids": [int(metric.id) for metric in metrics],
            "primary_metric": metrics[0].name,
            "source_paper_id": int(paper.id) if paper is not None else None,
            "created": created,
        }
        rechecks = BenchmarkGapService(self.db).enqueue_evidence_rechecks(
            candidate,
            trigger=TRIGGER,
            priority=RECHECK_PRIORITY,
            settings=self.settings,
            job_service=self.job_service,
        )
        return {
            "status": "promoted",
            "candidate_id": str(candidate.id),
            **candidate.resolution,
            "dataset_url": f"https://paperswithcode.co/benchmark/{dataset.slug}",
            "recheck_job_ids": rechecks["enqueued_job_ids"],
            "skipped_active_paper_ids": rechecks["skipped_active_paper_ids"],
        }

    def _resolve_task(self, mutation: AddBenchmarkMutation, created: dict) -> Task:
        if mutation.existing_task_id is not None:
            task = self.db.get(Task, mutation.existing_task_id)
            if task is None:
                raise ValueError(f"Task {mutation.existing_task_id} not found")
            created["task"] = False
            return task
        proposal = mutation.new_task
        parent = self.db.get(Task, proposal.parent_task_id)
        if parent is None:
            raise ValueError(f"Parent task {proposal.parent_task_id} not found")
        slug = slugify(proposal.name)
        key = _name_key(proposal.name)
        for task_id, name, task_slug in self.db.query(Task.id, Task.name, Task.slug):
            if task_slug == slug or _name_key(name) == key:
                raise ValueError(
                    f"Task {name!r} already exists as task {task_id}; "
                    "use existing_task_id"
                )
        task = Task(
            name=proposal.name.strip(),
            slug=slug,
            description=proposal.description.strip(),
            keywords=proposal.keywords.strip(),
            parent_id=parent.id,
            area_id=parent.area_id,
            level=(parent.level or 0) + 1,
        )
        self.db.add(task)
        self.db.flush()
        created["task"] = True
        return task

    def _resolve_metric(self, choice: BenchmarkMetricChoice, created: dict) -> Metric:
        if choice.existing_metric_id is not None:
            metric = self.db.get(Metric, choice.existing_metric_id)
            if metric is None:
                raise ValueError(f"Metric {choice.existing_metric_id} not found")
            return metric
        proposal = choice.new_metric
        key = _name_key(proposal.name)
        for metric_id, name, full_name in self.db.query(
            Metric.id, Metric.name, Metric.full_name
        ):
            if key in {_name_key(name), _name_key(full_name)}:
                raise ValueError(
                    f"Metric {proposal.name!r} duplicates metric {metric_id} "
                    f"({name!r}); use existing_metric_id"
                )
        metric = Metric(
            name=proposal.name.strip(),
            full_name=proposal.full_name.strip(),
            direction=proposal.direction,
            scale=proposal.scale,
            description=proposal.description.strip(),
        )
        self.db.add(metric)
        self.db.flush()
        created["metric_ids"].append(int(metric.id))
        return metric

    def _resolve_source_paper(
        self, source: BenchmarkSourcePaper, evidence_urls: list[str]
    ) -> Paper:
        if source.existing_paper_id is not None:
            paper = self.db.get(Paper, source.existing_paper_id)
            if paper is None or not paper.is_latest_version:
                raise ValueError(f"Paper {source.existing_paper_id} not found")
            if not TrendingModelResolutionService._paper_supported_by_evidence(
                paper, evidence_urls
            ):
                raise ValueError(
                    "Source paper requires its canonical URL in evidence_urls"
                )
            return paper
        if source.arxiv_id is not None:
            if not any(
                TrendingModelResolutionService._canonical_arxiv_evidence(
                    source.arxiv_id, url
                )
                for url in evidence_urls
            ):
                raise ValueError("arXiv source paper requires matching evidence_urls")
            paper, _ = asyncio.run(
                PaperIngestionService(self.db).get_or_import_arxiv_paper(
                    source.arxiv_id, commit=False
                )
            )
            return paper
        external = source.external_paper
        if external.source_url.rstrip("/") not in {
            url.rstrip("/") for url in evidence_urls
        }:
            raise ValueError("External source paper requires matching evidence_urls")
        result = ExternalResourceService(self.db).add_external_resource(
            ExternalResourceInput(
                source_url=external.source_url,
                title=external.title,
                abstract=external.abstract,
                date_published=external.date_published,
            ),
            commit=False,
        )
        paper = self.db.get(Paper, int(result.paper.id))
        if paper is None:
            raise RuntimeError("External paper ingestion returned no database row")
        return paper

    def _create_dataset(self, proposal: NewBenchmarkDataset, paper: Paper) -> Dataset:
        slug = slugify(proposal.name)
        if not slug:
            raise ValueError("Benchmark name must contain a letter or number")
        keys = {_name_key(proposal.name), _name_key(proposal.full_name)} - {""}
        for dataset_id, name, full_name, dataset_slug in self.db.query(
            Dataset.id, Dataset.name, Dataset.full_name, Dataset.slug
        ):
            if dataset_slug == slug or keys & {_name_key(name), _name_key(full_name)}:
                raise ValueError(
                    f"Benchmark {proposal.name!r} already exists as dataset "
                    f"{dataset_id} ({name!r}); use map_existing"
                )
        dataset = Dataset(
            name=proposal.name.strip(),
            slug=slug,
            full_name=proposal.full_name,
            description=proposal.description.strip(),
            homepage=proposal.homepage,
            hf_url=proposal.hf_url,
            introducing_paper_id=paper.id,
            introducing_paper_title=paper.title,
            paper_url=_paper_url(paper),
        )
        self.db.add(dataset)
        self.db.flush()
        return dataset

    # Job lifecycle

    def handle_terminal_job(self, row: PaperCurationJob) -> None:
        """Back off an approved candidate whose creation job did not apply."""
        if row.kind != "add-benchmark" or row.status not in {"failed", "canceled"}:
            return
        candidate = self.db.get(BenchmarkCurationCandidate, row.benchmark_candidate_id)
        if candidate is None or candidate.status != "approved":
            return
        self.db.flush()
        reviewed_at = (
            select(BenchmarkCurationCandidate.reviewed_at)
            .where(BenchmarkCurationCandidate.id == candidate.id)
            .scalar_subquery()
        )
        failures = (
            self.db.query(func.count(PaperCurationJob.id))
            .filter(
                PaperCurationJob.benchmark_candidate_id == candidate.id,
                PaperCurationJob.kind == "add-benchmark",
                PaperCurationJob.status.in_({"failed", "canceled"}),
                # Count only the current approval; reviewed_at moves on each
                # overseer approval and creation-job decision. Compare in SQL so
                # both timestamps come from the database clock.
                or_(
                    reviewed_at.is_(None),
                    PaperCurationJob.created_at >= reviewed_at,
                ),
            )
            .scalar()
            or 0
        )
        now = _now()
        reason = f"Creation job {row.id} {row.status}: {row.error or 'no error'}"
        if failures >= MAX_CREATION_FAILURES:
            # Send it back through the overseer instead of retrying forever.
            candidate.status = "candidate"
            candidate.deferred_until = now + timedelta(days=DEFER_DAYS)
        else:
            candidate.deferred_until = now + timedelta(days=FAILURE_RETRY_DAYS)
        candidate.review_reason = reason[:2_000]

    def rollback(self, candidate_id: uuid.UUID) -> dict:
        """Remove the catalog rows one creation job added, while only it uses them."""
        candidate = self.db.get(BenchmarkCurationCandidate, candidate_id)
        if candidate is None:
            raise LookupError("Benchmark candidate not found")
        resolution = candidate.resolution or {}
        created = resolution.get("created")
        if candidate.status != "promoted" or not created:
            raise ValueError("Only an automatically promoted candidate can roll back")
        task_id, dataset_id = resolution["task_id"], resolution["dataset_id"]
        rechecks = (
            self.db.query(PaperCurationJob)
            .filter(
                PaperCurationJob.trigger == TRIGGER,
                PaperCurationJob.kind == "add-evals",
                PaperCurationJob.policy_version
                == BenchmarkGapService.recheck_policy_version(candidate),
                PaperCurationJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .all()
        )
        if any(job.status != "queued" for job in rechecks):
            raise ValueError("Wait for the running evidence rechecks to finish")
        evidence_papers = {
            int(paper_id)
            for (paper_id,) in self.db.query(BenchmarkCurationEvidence.paper_id).filter(
                BenchmarkCurationEvidence.candidate_id == candidate.id
            )
        }
        scope = Evaluation.dataset_id == dataset_id
        if not created.get("dataset"):
            scope = scope & (Evaluation.task_id == task_id)
        evaluations = self.db.query(Evaluation).filter(scope).all()
        foreign = sorted({int(item.paper_id) for item in evaluations} - evidence_papers)
        if foreign:
            raise ValueError(
                f"Leaderboard has evaluations from papers {foreign} that did not "
                "report this gap; remove them by hand first"
            )
        if created.get("dataset") and (
            self.db.query(TaskDataset)
            .filter(
                TaskDataset.dataset_id == dataset_id, TaskDataset.task_id != task_id
            )
            .first()
        ):
            raise ValueError("The dataset has since been linked to other tasks")
        for job in rechecks:
            job.status = "canceled"
            job.finished_at = _now()
        for evaluation in evaluations:
            self.db.delete(evaluation)
        for metric_id in created.get("task_dataset_metric_ids") or []:
            link = self.db.get(TaskDatasetMetric, (task_id, dataset_id, metric_id))
            if link is not None:
                self.db.delete(link)
        if created.get("task_dataset"):
            link = self.db.get(TaskDataset, (task_id, dataset_id))
            if link is not None:
                self.db.delete(link)
        self.db.flush()
        removed: dict[str, Any] = {"evaluations": len(evaluations)}
        if created.get("dataset"):
            self.db.delete(self.db.get(Dataset, dataset_id))
            removed["dataset_id"] = dataset_id
        elif created.get("introducing_paper_set"):
            dataset = self.db.get(Dataset, dataset_id)
            dataset.introducing_paper_id = None
            dataset.introducing_paper_title = None
            dataset.paper_url = None
        if created.get("paper_task") and resolution.get("source_paper_id"):
            link = self.db.get(PaperTask, (resolution["source_paper_id"], task_id))
            if link is not None:
                self.db.delete(link)
        self.db.flush()
        removed["metric_ids"] = []
        for metric_id in created.get("metric_ids") or []:
            metric = self.db.get(Metric, metric_id)
            in_use = (
                self.db.query(TaskDatasetMetric.metric_id)
                .filter(TaskDatasetMetric.metric_id == metric_id)
                .first()
            )
            if metric is not None and in_use is None:
                self.db.delete(metric)
                removed["metric_ids"].append(metric_id)
        if created.get("task"):
            task_in_use = any(
                query.first() is not None
                for query in (
                    self.db.query(TaskDataset.task_id).filter(
                        TaskDataset.task_id == task_id
                    ),
                    self.db.query(PaperTask.task_id).filter(
                        PaperTask.task_id == task_id
                    ),
                    self.db.query(Task.id).filter(Task.parent_id == task_id),
                )
            )
            if not task_in_use:
                self.db.delete(self.db.get(Task, task_id))
                removed["task_id"] = task_id
        now = _now()
        candidate.status = "rejected"
        candidate.reviewed_paper_count = candidate.distinct_paper_count
        candidate.reviewed_at = now
        candidate.review_reason = "Rolled back by an administrator"
        candidate.resolution = {**resolution, "rolled_back_at": now.isoformat()}
        self.db.commit()
        return {"status": "rolled_back", "candidate_id": str(candidate.id), **removed}
