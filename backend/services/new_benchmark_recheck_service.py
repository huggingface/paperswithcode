"""Re-check indexed papers when a new benchmark leaderboard appears.

A leaderboard (task, dataset) is new when its first ``task_dataset_metrics``
row is recent, however it was created (add-benchmark, gap review, a sync, or
by hand). Papers already curated on other boards of the same task were checked
before it existed, so their own text may report it. This scans that text
(stored paper Markdown, else the abstract) for the benchmark's names and queues
a bounded add-evals re-check for the papers that mention it most. A mention is
only a reason to look again: comparator columns mention benchmarks too, so the
curator verifies every row before anything is written.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from huggingface_hub.errors import HfHubHTTPError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Paper,
    PaperCurationJob,
    TaskDatasetMetric,
)
from backend.services.abstract_mention_service import (
    MentionIndex,
    build_index,
    find_candidates,
    load_catalog_entities,
    tokenize,
)
from backend.services.codex_add_evals_service import NEW_BENCHMARK_POLICY_PREFIX
from backend.services.paper_markdown_service import (
    PaperMarkdownStorageError,
    read_paper_markdown_bounded,
)
from backend.utils.urls import get_paper_route_identifier

logger = logging.getLogger(__name__)

TRIGGER = "benchmark-promotion"
PRIORITY = 50
# One popular benchmark must not flood the admin lane, which dispatches ahead
# of daily curation; the dispatcher also caps this lane's active jobs.
MAX_PER_BENCHMARK = 5
MAX_PER_RUN = 20
# Newest sibling-board papers scanned per benchmark, and stored Markdown
# reads per run (~1 s each).
SCAN_PER_BENCHMARK = 50
MAX_TEXT_READS = 400
MARKDOWN_MAX_BYTES = 400_000
# A full paper names a benchmark once in related work; ask for a second
# mention. An abstract that names it at all is enough.
MIN_MARKDOWN_MENTIONS = 2
_ACTIVE = ("queued", "dispatching", "running")
# Failed or canceled re-checks free their paper and their slot in the cap.
_HELD = (*_ACTIVE, "completed")
_REFERENCES = re.compile(
    r"^(#{1,6})\s*(?:\d+\.?\s*)?(references|bibliography)\s*$", re.I
)
_HEADING = re.compile(r"^(#{1,6})\s")


def policy_version(dataset_id: int) -> str:
    return f"{NEW_BENCHMARK_POLICY_PREFIX}{dataset_id}"


def without_references(markdown: str) -> str:
    """Drop bibliography sections, whose titles name every cited benchmark."""
    kept: list[str] = []
    skip_level = 0
    for line in markdown.splitlines():
        heading = _HEADING.match(line)
        if heading and skip_level and len(heading.group(1)) <= skip_level:
            skip_level = 0
        if references := _REFERENCES.match(line.strip()):
            skip_level = len(references.group(1))
        if not skip_level:
            kept.append(line)
    return "\n".join(kept)


@dataclass
class NewBenchmark:
    dataset: Dataset
    task_ids: list[int]
    created_at: datetime
    # Evals on any of these mean the paper already reports the benchmark.
    family_ids: set[int] = field(default_factory=set)
    # Mentions of these count: the dataset, its parent, and its splits.
    match_ids: set[int] = field(default_factory=set)


class NewBenchmarkRecheckService:
    def __init__(
        self,
        db: Session,
        settings,
        *,
        read_text: Callable[[Paper], tuple[str, bool] | None] | None = None,
    ):
        self.db = db
        self.settings = settings
        self.read_text = read_text or self._read_stored_text
        self._texts: dict[int, tuple[str, bool]] = {}
        self.text_reads = 0

    def new_benchmarks(self, since: datetime) -> list[NewBenchmark]:
        boards = (
            self.db.query(
                TaskDatasetMetric.task_id,
                TaskDatasetMetric.dataset_id,
                func.min(TaskDatasetMetric.created_at).label("created_at"),
            )
            .group_by(TaskDatasetMetric.task_id, TaskDatasetMetric.dataset_id)
            .having(func.min(TaskDatasetMetric.created_at) >= since)
            .order_by(func.min(TaskDatasetMetric.created_at))
            .all()
        )
        by_dataset: dict[int, NewBenchmark] = {}
        for board in boards:
            if board.dataset_id in by_dataset:
                by_dataset[board.dataset_id].task_ids.append(board.task_id)
                continue
            dataset = self.db.get(Dataset, board.dataset_id)
            by_dataset[board.dataset_id] = NewBenchmark(
                dataset=dataset,
                task_ids=[board.task_id],
                created_at=board.created_at,
            )
        for benchmark in by_dataset.values():
            dataset = benchmark.dataset
            children = {
                row.id
                for row in self.db.query(Dataset.id).filter(
                    Dataset.parent_dataset_id == dataset.id
                )
            }
            benchmark.match_ids = {dataset.id, *children}
            benchmark.family_ids = set(benchmark.match_ids)
            if dataset.parent_dataset_id is not None:
                benchmark.match_ids.add(dataset.parent_dataset_id)
                benchmark.family_ids |= {
                    dataset.parent_dataset_id,
                    *(
                        row.id
                        for row in self.db.query(Dataset.id).filter(
                            Dataset.parent_dataset_id == dataset.parent_dataset_id
                        )
                    ),
                }
        return list(by_dataset.values())

    def candidate_papers(self, benchmark: NewBenchmark) -> list[Paper]:
        """Papers curated on the task before the board existed, newest first."""
        first_evals = (
            self.db.query(Evaluation.paper_id, func.min(Evaluation.created_at))
            .filter(
                Evaluation.task_id.in_(benchmark.task_ids),
                Evaluation.paper_id.isnot(None),
            )
            .group_by(Evaluation.paper_id)
            .all()
        )
        paper_ids = {
            int(paper_id)
            for paper_id, first in first_evals
            if first is not None and first < benchmark.created_at
        }
        paper_ids.discard(benchmark.dataset.introducing_paper_id)
        if not paper_ids:
            return []
        reported = {
            row.paper_id
            for row in self.db.query(Evaluation.paper_id).filter(
                Evaluation.dataset_id.in_(benchmark.family_ids),
                Evaluation.paper_id.in_(paper_ids),
            )
        }
        # Skip papers with add-evals in flight, already checked after the
        # board existed, or already queued by this mechanism for it.
        checked = {
            row.paper_id
            for row in self.db.query(PaperCurationJob.paper_id).filter(
                PaperCurationJob.kind == "add-evals",
                PaperCurationJob.paper_id.in_(paper_ids),
                or_(
                    PaperCurationJob.status.in_(_ACTIVE),
                    (
                        PaperCurationJob.policy_version
                        == policy_version(benchmark.dataset.id)
                    )
                    & PaperCurationJob.status.in_(_HELD),
                    (PaperCurationJob.created_at >= benchmark.created_at)
                    & (PaperCurationJob.status == "completed"),
                ),
            )
        }
        remaining = paper_ids - reported - checked
        if not remaining:
            return []
        return (
            self.db.query(Paper)
            .filter(Paper.id.in_(remaining), Paper.is_latest_version)
            .order_by(Paper.date_published.desc().nullslast(), Paper.id.desc())
            .limit(SCAN_PER_BENCHMARK)
            .all()
        )

    def mentions(
        self, paper: Paper, benchmark: NewBenchmark, index: MentionIndex
    ) -> int | None:
        """Mentions of the benchmark in the paper's text.

        None means the benchmark cannot be finished this run: the read budget
        is spent or Markdown storage is failing. The next run retries it.
        """
        if paper.id not in self._texts:
            if self.text_reads >= MAX_TEXT_READS:
                return None
            self.text_reads += 1
            stored = self.read_text(paper)
            if stored is None:
                return None
            text_value, from_markdown = stored
            if from_markdown:
                text_value = without_references(text_value)
            self._texts[paper.id] = (text_value, from_markdown)
        text_value, from_markdown = self._texts[paper.id]
        heads = {tokens[0] for tokens in index.surfaces}
        count = 0
        # The matcher is slow over a whole paper; run it only on the lines
        # that could hold a mention.
        for line in text_value.splitlines():
            lowered = line.lower()
            if not any(head in lowered for head in heads):
                continue
            count += sum(
                candidate.entity_type == "dataset"
                and candidate.entity_id in benchmark.match_ids
                for candidate in find_candidates(line, index)
            )
        threshold = MIN_MARKDOWN_MENTIONS if from_markdown else 1
        return count if count >= threshold else 0

    def reconcile(
        self, *, since: datetime, job_service, dry_run: bool = False
    ) -> dict[str, Any]:
        """Queue capped re-checks for benchmarks whose first board is recent."""
        benchmarks = self.new_benchmarks(since)
        index = self._index(benchmarks)
        queued: list[dict[str, Any]] = []
        unscanned: list[int] = []
        for benchmark in benchmarks:
            if len(queued) >= MAX_PER_RUN:
                unscanned.append(benchmark.dataset.id)
                continue
            # The cap holds across runs: earlier runs' jobs count against it.
            budget = MAX_PER_BENCHMARK - self._queued_before(benchmark)
            if budget <= 0:
                continue
            hits: list[tuple[int, Paper]] = []
            complete = True
            for paper in self.candidate_papers(benchmark):
                count = self.mentions(paper, benchmark, index)
                if count is None:
                    complete = False
                    break
                if count:
                    hits.append((count, paper))
            if not complete:
                unscanned.append(benchmark.dataset.id)
            # One add-evals run reads the whole paper, so it also covers every
            # other new board the paper mentions.
            queued_papers = {item["paper_id"] for item in queued}
            hits = [hit for hit in hits if hit[1].id not in queued_papers]
            hits.sort(key=lambda hit: (-hit[0], -hit[1].id))
            room = min(budget, MAX_PER_RUN - len(queued))
            for count, paper in hits[:room]:
                item = {
                    "dataset_id": benchmark.dataset.id,
                    "dataset": benchmark.dataset.name,
                    "paper_id": paper.id,
                    "mentions": count,
                }
                if not dry_run:
                    job = job_service.enqueue(
                        self.db,
                        kind="add-evals",
                        paper_id=paper.id,
                        paper_route=get_paper_route_identifier(
                            paper.source, paper.arxiv_id, paper.id
                        ),
                        paper_title=paper.title,
                        requested_by=f"new-benchmark:{benchmark.dataset.id}",
                        settings=self.settings,
                        trigger=TRIGGER,
                        policy_version=policy_version(benchmark.dataset.id),
                        priority=PRIORITY,
                        dispatch=False,
                        commit=False,
                    )
                    item["job_id"] = str(job.id)
                queued.append(item)
        if not dry_run:
            self.db.commit()
        return {
            "new_benchmarks": len(benchmarks),
            "text_reads": self.text_reads,
            "rechecks": queued,
            "unscanned_dataset_ids": unscanned,
        }

    def _queued_before(self, benchmark: NewBenchmark) -> int:
        return (
            self.db.query(func.count(PaperCurationJob.id))
            .filter(
                PaperCurationJob.policy_version == policy_version(benchmark.dataset.id),
                PaperCurationJob.status.in_(_HELD),
            )
            .scalar()
        )

    def _index(self, benchmarks: list[NewBenchmark]) -> MentionIndex:
        """Index the benchmarks plus every dataset sharing a leading name token.

        Same-prefix datasets keep longest-match precedence, so `MMLU-Pro` in a
        paper is not counted as a mention of a new `MMLU` board.
        """
        datasets = [
            entity
            for entity in load_catalog_entities(self.db)
            if entity.entity_type == "dataset"
        ]
        wanted = {i for benchmark in benchmarks for i in benchmark.match_ids}

        def heads(entity) -> set[str]:
            return {
                tokens[0].lower()
                for name in (entity.name, *entity.aliases)
                if (tokens := tokenize(name))
            }

        wanted_heads = set().union(
            *(heads(entity) for entity in datasets if entity.entity_id in wanted)
        )
        return build_index(
            entity for entity in datasets if heads(entity) & wanted_heads
        )

    def _read_stored_text(self, paper: Paper) -> tuple[str, bool] | None:
        """Stored paper Markdown, else the abstract; None while storage fails."""
        try:
            markdown, _ = read_paper_markdown_bounded(
                paper.arxiv_id or str(paper.id),
                bucket_id=self.settings.paper_markdown_hf_bucket_id,
                token=self.settings.hf_token or None,
                max_bytes=MARKDOWN_MAX_BYTES,
            )
        except (PaperMarkdownStorageError, HfHubHTTPError) as error:
            logger.warning("Markdown storage failed for paper %s: %s", paper.id, error)
            return None
        except ValueError as error:  # not converted yet, or not readable
            logger.info("No stored Markdown for paper %s: %s", paper.id, error)
            return paper.abstract or "", False
        return markdown, True
