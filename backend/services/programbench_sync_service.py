"""Synchronize ProgramBench's living program-reconstruction leaderboard."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from math import isfinite
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService

PROGRAMBENCH_URL = "https://programbench.com/"
TASK_SLUG = "coding-agents"
DATASET_SLUG = "programbench"
PRIMARY_METRIC_NAME = "Resolved"
ALMOST_RESOLVED_METRIC_NAME = "Almost Resolved"
AVERAGE_PASS_RATE_METRIC_NAME = "Average Test Pass Rate"
METRIC_NAMES = (
    PRIMARY_METRIC_NAME,
    ALMOST_RESOLVED_METRIC_NAME,
    AVERAGE_PASS_RATE_METRIC_NAME,
)
HARNESS_NAME = "mini-SWE-agent"
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code ProgramBench live sync."
MIN_EXPECTED_ENTRIES = 15
MAX_EXPECTED_ENTRIES = 60
_RESULTS_PATTERN = re.compile(r"\bvar\s+results\s*=\s*(\[.*?\]);", re.DOTALL)


@dataclass(frozen=True)
class PaperIdentity:
    source_url: str
    is_open: bool = False


# Exact upstream run IDs are the trust boundary between a displayed model label
# and its reviewed official release page. New runs remain unpublished until the
# model identity has been reviewed here.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "muse-spark-1-1-xhigh": PaperIdentity(
        "https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/"
    ),
    "muse-spark-1-2-xhigh": PaperIdentity(
        "https://developer.meta.com/ai/resources/blog/build-with-muse-code/"
    ),
    "muse-spark-1-3-xhigh": PaperIdentity(
        "https://research.meta.ai/blog/introducing-muse-spark-1-3"
    ),
    "muse-spark-1-3-max": PaperIdentity(
        "https://research.meta.ai/blog/introducing-muse-spark-1-3"
    ),
    "claude-opus-5-xhigh": PaperIdentity(
        "https://www.anthropic.com/news/claude-opus-5"
    ),
    "gpt-5-6-sol-xhigh": PaperIdentity("https://openai.com/index/gpt-5-6/"),
    "gpt-5-5-xhigh": PaperIdentity("https://openai.com/index/introducing-gpt-5-5/"),
    "gpt-5-5-high": PaperIdentity("https://openai.com/index/introducing-gpt-5-5/"),
    "gemini-3-6-flash": PaperIdentity(
        "https://blog.google/innovation-and-ai/models-and-research/"
        "gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/"
    ),
    "gpt-5-6-sol": PaperIdentity("https://openai.com/index/gpt-5-6/"),
    "claude-opus-4-8-xhigh": PaperIdentity(
        "https://www.anthropic.com/news/claude-opus-4-8"
    ),
    "glm-5-2": PaperIdentity("https://z.ai/blog/glm-5.2", is_open=True),
    "gemini-3-7-flash": PaperIdentity(
        "https://blog.google/innovation-and-ai/models-and-research/"
        "gemini-models/introducing-gemini-3-7-flash/"
    ),
    "claude-opus-4-7-xhigh": PaperIdentity(
        "https://www.anthropic.com/news/claude-opus-4-7"
    ),
    "gemini-3-5-flash": PaperIdentity(
        "https://blog.google/innovation-and-ai/models-and-research/"
        "gemini-models/gemini-3-5/"
    ),
    "claude-opus-4-7": PaperIdentity("https://www.anthropic.com/news/claude-opus-4-7"),
    "claude-opus-4-6": PaperIdentity("https://www.anthropic.com/news/claude-opus-4-6"),
    "gpt-5-5": PaperIdentity("https://openai.com/index/introducing-gpt-5-5/"),
    "claude-sonnet-4-6": PaperIdentity(
        "https://www.anthropic.com/news/claude-sonnet-4-6"
    ),
    "gpt-5-4": PaperIdentity("https://openai.com/index/introducing-gpt-5-4/"),
    "gemini-3-1-pro": PaperIdentity(
        "https://blog.google/innovation-and-ai/models-and-research/"
        "gemini-models/gemini-3-1-pro/"
    ),
    "gemini-3-flash": PaperIdentity(
        "https://blog.google/products-and-platforms/products/gemini/gemini-3"
    ),
    "claude-haiku-4-5": PaperIdentity("https://www.anthropic.com/claude/haiku"),
    "gpt-5-4-mini": PaperIdentity(
        "https://openai.com/index/introducing-gpt-5-4-mini-and-nano/"
    ),
    "gpt-5-mini": PaperIdentity("https://openai.com/index/introducing-gpt-5/"),
}


@dataclass(frozen=True)
class ProgramBenchEntry:
    upstream_id: str
    model: str
    provider: str
    harness: str
    average_test_pass_rate: float
    resolved: float
    almost_resolved: float
    evaluated_on: date
    source_url: str


@dataclass
class ProgramBenchSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _percentage(text: str, *, field_name: str, upstream_id: str) -> float:
    raw = text.replace("%", "").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"ProgramBench {field_name} is invalid for {upstream_id}"
        ) from exc
    if not isfinite(value) or not 0 <= value <= 100:
        raise ValueError(
            f"ProgramBench {field_name} is outside 0-100 for {upstream_id}"
        )
    return value


def parse_programbench_leaderboard(html: str) -> list[ProgramBenchEntry]:
    """Validate the server-rendered leaderboard before it can affect rows."""
    if not isinstance(html, str) or not html.strip():
        raise TypeError("ProgramBench response must be non-empty HTML")
    match = _RESULTS_PATTERN.search(html)
    if match is None:
        raise ValueError("ProgramBench response has no embedded results payload")
    try:
        raw_results = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError("ProgramBench embedded results are invalid JSON") from exc
    if not isinstance(raw_results, list):
        raise TypeError("ProgramBench embedded results must be a list")

    results: dict[str, dict[str, Any]] = {}
    for raw in raw_results:
        if not isinstance(raw, dict):
            raise TypeError("ProgramBench result rows must be objects")
        upstream_id = raw.get("slug")
        if (
            not isinstance(upstream_id, str)
            or not upstream_id
            or len(upstream_id) > 255
        ):
            raise ValueError("ProgramBench result has an invalid slug")
        if upstream_id in results:
            raise ValueError("ProgramBench response contains duplicate run slugs")
        results[upstream_id] = raw

    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.lb-table")
    if table is None:
        raise ValueError("ProgramBench response has no leaderboard table")
    entries: list[ProgramBenchEntry] = []
    table_ids: set[str] = set()
    for row in table.select("tbody tr[data-href]"):
        href = row.get("data-href")
        if not isinstance(href, str):
            raise TypeError("ProgramBench row has no run URL")
        href_parts = href.strip("/").split("/")
        if len(href_parts) != 2 or href_parts[0] != "run" or not href_parts[1]:
            raise ValueError(f"ProgramBench row has an invalid run URL: {href}")
        upstream_id = href_parts[1]
        if upstream_id in table_ids:
            raise ValueError("ProgramBench table contains duplicate run slugs")
        raw = results.get(upstream_id)
        if raw is None:
            raise ValueError(f"ProgramBench result payload is missing {upstream_id}")
        model_node = row.select_one(".model-name")
        harness_node = row.select_one(".col-agent")
        resolved_node = row.select_one(
            ".col-num.resolved-highlight, .col-num.resolved-zero"
        )
        almost_node = row.select_one(".col-almost")
        if None in (model_node, harness_node, resolved_node, almost_node):
            raise ValueError(f"ProgramBench table row is malformed for {upstream_id}")
        model = model_node.get_text(" ", strip=True)
        harness = harness_node.get_text(" ", strip=True)
        provider = row.get("data-provider")
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError(f"ProgramBench provider is invalid for {upstream_id}")
        if raw.get("model") != model or raw.get("provider") != provider:
            raise ValueError(
                f"ProgramBench table and result payload disagree for {upstream_id}"
            )
        if harness != HARNESS_NAME:
            raise ValueError(
                f"ProgramBench harness changed for {upstream_id}: {harness!r}"
            )
        score = raw.get("score")
        timestamp = raw.get("date")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise TypeError(f"ProgramBench score is invalid for {upstream_id}")
        average_test_pass_rate = float(score) * 100
        if (
            not isfinite(average_test_pass_rate)
            or not 0 <= average_test_pass_rate <= 100
        ):
            raise ValueError(f"ProgramBench score is outside 0-1 for {upstream_id}")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise TypeError(f"ProgramBench date is invalid for {upstream_id}")
        evaluated_on = datetime.fromtimestamp(float(timestamp) / 1000, UTC).date()
        table_ids.add(upstream_id)
        entries.append(
            ProgramBenchEntry(
                upstream_id=upstream_id,
                model=model,
                provider=provider,
                harness=harness,
                average_test_pass_rate=round(average_test_pass_rate, 4),
                resolved=_percentage(
                    resolved_node.get_text(" ", strip=True),
                    field_name="resolved rate",
                    upstream_id=upstream_id,
                ),
                almost_resolved=_percentage(
                    almost_node.get_text(" ", strip=True),
                    field_name="almost-resolved rate",
                    upstream_id=upstream_id,
                ),
                evaluated_on=evaluated_on,
                source_url=urljoin(PROGRAMBENCH_URL, href),
            )
        )

    if not MIN_EXPECTED_ENTRIES <= len(entries) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"ProgramBench returned {len(entries)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )
    if table_ids != set(results):
        raise ValueError("ProgramBench table and result payload run sets disagree")
    if table_ids != set(MODEL_PAPER_IDENTITIES):
        missing = sorted(set(MODEL_PAPER_IDENTITIES) - table_ids)
        unreviewed = sorted(table_ids - set(MODEL_PAPER_IDENTITIES))
        raise ValueError(
            "ProgramBench reviewed run set changed; "
            f"missing={missing!r}; unreviewed={unreviewed!r}"
        )
    return entries


def fetch_programbench_leaderboard(
    client: httpx.Client | None = None,
) -> list[ProgramBenchEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-programbench-sync/1.0"},
    )
    try:
        response = active_client.get(PROGRAMBENCH_URL)
        response.raise_for_status()
        return parse_programbench_leaderboard(response.text)
    finally:
        if owned_client:
            active_client.close()


def _managed_upstream_id(row: Evaluation) -> str | None:
    methodology = row.methodology or ""
    if not methodology.startswith(MANAGED_METHODOLOGY_PREFIX):
        return None
    marker = " upstream_id="
    start = methodology.find(marker)
    if start == -1:
        return None
    return methodology[start + len(marker) :].split(";", 1)[0]


class ProgramBenchSyncService:
    """Replace only evaluation rows owned by the ProgramBench live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metrics = {
            metric.name: metric.id
            for metric in self.db.query(Metric)
            .filter(Metric.name.in_(METRIC_NAMES))
            .all()
        }
        if task is None or dataset is None or set(metrics) != set(METRIC_NAMES):
            raise RuntimeError(
                "ProgramBench task, benchmark, or metrics are not configured"
            )
        for metric_id in metrics.values():
            configured = (
                self.db.query(TaskDatasetMetric)
                .filter(
                    TaskDatasetMetric.task_id == task.id,
                    TaskDatasetMetric.dataset_id == dataset.id,
                    TaskDatasetMetric.metric_id == metric_id,
                )
                .one_or_none()
            )
            if configured is None:
                raise RuntimeError("ProgramBench metrics are not linked to the task")
        return task, dataset

    def sync(
        self, entries: list[ProgramBenchEntry], *, commit: bool = True
    ) -> ProgramBenchSyncStats:
        if not entries:
            raise ValueError(
                "Refusing to synchronize an empty ProgramBench leaderboard"
            )
        stats = ProgramBenchSyncStats(fetched=len(entries))
        try:
            task, dataset = self._leaderboard_identity()
            source_urls = {
                identity.source_url for identity in MODEL_PAPER_IDENTITIES.values()
            }
            papers = (
                self.db.query(Paper)
                .filter(
                    Paper.source == "external",
                    Paper.source_url.in_(source_urls),
                    Paper.is_latest_version,
                )
                .order_by(Paper.id.desc())
                .all()
            )
            papers_by_source: dict[str, Paper] = {}
            for paper in papers:
                papers_by_source.setdefault(paper.source_url, paper)
            managed_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                    Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
                )
                .all()
            )
            managed = {
                upstream_id: row
                for row in managed_rows
                if (upstream_id := _managed_upstream_id(row)) is not None
            }
            linked_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            upstream_ids = {entry.upstream_id for entry in entries}
            for entry in entries:
                identity = MODEL_PAPER_IDENTITIES.get(entry.upstream_id)
                paper = papers_by_source.get(identity.source_url) if identity else None
                if paper is None:
                    stats.missing_papers.append(entry.upstream_id)
                    continue
                row = managed.get(entry.upstream_id)
                if row is None:
                    row = Evaluation(
                        paper_id=paper.id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                row.paper_id = paper.id
                row.model_name = entry.model
                row.harness = entry.harness
                row.methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} upstream_id={entry.upstream_id}; "
                    "average hidden behavioral-test pass rate across the published task set; "
                    f"resolved={entry.resolved:g}%; "
                    f"almost_resolved={entry.almost_resolved:g}%."
                )
                row.metrics = {
                    PRIMARY_METRIC_NAME: entry.resolved,
                    ALMOST_RESOLVED_METRIC_NAME: entry.almost_resolved,
                    AVERAGE_PASS_RATE_METRIC_NAME: entry.average_test_pass_rate,
                }
                row.uses_additional_data = False
                row.is_open = identity.is_open
                row.best_metric = PRIMARY_METRIC_NAME
                row.evaluated_on = entry.evaluated_on
                row.external_source_url = entry.source_url
                row.source_url = entry.source_url
                row.external = True
                row.updated_at = datetime.now(UTC)
                if paper.id not in linked_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper.id, task_id=task.id, source="auto")
                    )
                    linked_paper_ids.add(paper.id)
                stats.matched += 1
            if stats.missing_papers and commit:
                raise RuntimeError(
                    "No reviewed papers resolved for ProgramBench runs: "
                    + ",".join(stats.missing_papers)
                )
            for upstream_id, row in managed.items():
                if upstream_id not in upstream_ids:
                    self.db.delete(row)
                    stats.deleted += 1
            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id,
                dataset.id,
                metric_name=PRIMARY_METRIC_NAME,
                commit=False,
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
