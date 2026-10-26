"""Synchronize the official FrontierCS 2 leaderboard."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import httpx
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
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix

FRONTIERCS_2_URL = "https://frontier-cs.org/#leaderboard"
# The leaderboard page renders client-side from constants in this bundle.
FRONTIERCS_2_DATA_URL = "https://frontier-cs.org/assets/js/fcs2-data.js"
TASK_SLUG = "coding-agents"
DATASET_SLUG = "frontiercs-2"
PASS_RATE = "Pass Rate"
FCI = "FCI"
METRIC_NAMES = (PASS_RATE, FCI)
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("FrontierCS 2")
MIN_EXPECTED_ENTRIES = 8
MAX_EXPECTED_ENTRIES = 200
# Refuse to touch the managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 8


@dataclass(frozen=True)
class ModelIdentity:
    """A reviewed leaderboard model and the paper that introduces it."""

    model_name: str
    arxiv_id: str | None = None
    source_url: str | None = None
    is_open: bool = False
    hf_model_url: str | None = None

    def __post_init__(self) -> None:
        if (self.arxiv_id is None) == (self.source_url is None):
            raise ValueError("ModelIdentity requires exactly one paper identity")

    @property
    def paper_key(self) -> str:
        return self.arxiv_id or self.source_url or ""


_DEEPSEEK_V4_1_FLASH = "2609.19969"

# Exact FrontierCS model names are the trust boundary between a leaderboard
# entry and its introducing paper; the harness is shown per entry. Catalog
# model names and papers follow the reviewed Vals AI sync identities.
# Unreviewed names are reported, never imported.
MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "Claude Opus 5.5": ModelIdentity(
        "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
    ),
    "Gemini 4 Argon": ModelIdentity(
        "Gemini 4 Argon",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-4-argon/"
        ),
    ),
    "GPT-6 Astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "GPT-6.1 Sol": ModelIdentity(
        "GPT-6.1 Sol", source_url="https://openai.com/index/introducing-gpt-6-1-sol/"
    ),
    "GLM 5.3": ModelIdentity(
        "GLM-5.3",
        source_url="https://z.ai/blog/glm-5.3",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3",
    ),
    "GLM 5.3 Flash": ModelIdentity(
        "GLM-5.3-Flash",
        source_url="https://z.ai/blog/glm-5.3-flash",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3-Flash",
    ),
    "Kimi K3": ModelIdentity(
        "Kimi K3",
        arxiv_id="2607.24653",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K3",
    ),
    "DeepSeek V4.1 Flash": ModelIdentity(
        "DeepSeek-V4.1-Flash",
        arxiv_id=_DEEPSEEK_V4_1_FLASH,
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash",
    ),
    "DeepSeek V4.1 Flash 1017": ModelIdentity(
        "DeepSeek-V4.1-Flash-1017",
        arxiv_id=_DEEPSEEK_V4_1_FLASH,
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017",
    ),
    "Muse Spark 1.3": ModelIdentity(
        "Muse Spark 1.3",
        source_url="https://research.meta.ai/blog/introducing-muse-spark-1-3",
    ),
    "Muse Wonder 1.0": ModelIdentity(
        "Muse Wonder 1.0", source_url="https://research.meta.ai/blog/muse-wonder"
    ),
    "Qwen 3.8 Max": ModelIdentity(
        "Qwen3.8-Max", source_url="https://qwen.ai/blog?id=qwen3.8"
    ),
    "Step 5 Preview": ModelIdentity(
        "Step-5-Preview",
        source_url="https://huggingface.co/stepfun-ai/Step-5-Preview",
        is_open=True,
        hf_model_url="https://huggingface.co/stepfun-ai/Step-5-Preview",
    ),
}


@dataclass(frozen=True)
class FrontierCSEntry:
    upstream_id: str
    name: str
    harness: str
    pass_rate: float
    passes: int
    runs: int
    fci: float
    fci_low: float
    fci_high: float

    @property
    def label(self) -> str:
        return f"{self.name} ({self.harness})"


@dataclass(frozen=True)
class FrontierCSLeaderboard:
    updated: date
    entries: list[FrontierCSEntry]


@dataclass
class FrontierCSSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    changed: int = 0
    unreviewed: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)
    missing_upstream: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


_BARE_KEY = re.compile(r"([{,])\s*([A-Za-z_$][\w$]*)\s*:")


def _literal(source: str, name: str) -> Any:
    """Decode the JS object/array literal assigned to a top-level constant."""
    matches = list(re.finditer(rf"(?<![\w.$]){name}=(?=[\[{{])", source))
    if len(matches) != 1:
        raise ValueError(f"FrontierCS data has {len(matches)} {name} literals")
    start = matches[0].end()
    depth = 0
    in_string = escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            else:
                in_string = char != '"'
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                literal = source[start : index + 1]
                break
    else:
        raise ValueError(f"FrontierCS {name} literal is unterminated")
    try:
        return json.loads(_BARE_KEY.sub(r'\1"\2":', literal))
    except json.JSONDecodeError as exc:
        raise ValueError(f"FrontierCS {name} literal is not plain data") from exc


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"FrontierCS {what} is not a number: {value!r}")
    return float(value)


def parse_frontiercs_2(source: str) -> FrontierCSLeaderboard:
    """Parse the leaderboard constants, failing on any layout change."""
    if not isinstance(source, str) or not source.strip():
        raise TypeError("FrontierCS response must be non-empty JavaScript")
    updated_match = re.findall(r'(?<![\w.$])UPDATED="([^"]+)"', source)
    if len(updated_match) != 1:
        raise ValueError("FrontierCS UPDATED date layout changed")
    updated = datetime.strptime(updated_match[0], "%B %d, %Y").date()
    models = _literal(source, "MODELS")
    passes = _literal(source, "PASS")
    indices = _literal(source, "ECI")
    if not isinstance(models, list) or not isinstance(passes, dict):
        raise ValueError("FrontierCS MODELS/PASS layout changed")
    if not isinstance(indices, dict):
        raise ValueError("FrontierCS ECI layout changed")
    entries: list[FrontierCSEntry] = []
    seen: set[str] = set()
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("FrontierCS model layout changed")
        upstream_id, name, harness = model.get("id"), model.get("name"), model.get("h")
        if not all(
            isinstance(v, str) and v.strip() for v in (upstream_id, name, harness)
        ):
            raise ValueError(f"FrontierCS model is malformed: {model!r}")
        if len(name) > 200 or len(harness) > 200:
            raise ValueError(f"FrontierCS model is malformed: {model!r}")
        pass_row, index_row = passes.get(upstream_id), indices.get(upstream_id)
        if not isinstance(pass_row, list) or len(pass_row) != 3:
            raise ValueError(f"FrontierCS pass rate is missing for {upstream_id}")
        if not isinstance(index_row, list) or len(index_row) != 4:
            raise ValueError(f"FrontierCS FCI is missing for {upstream_id}")
        rate, passed, runs = (_number(v, f"{upstream_id} pass") for v in pass_row)
        fci, low, high, _tasks = (_number(v, f"{upstream_id} FCI") for v in index_row)
        if not (runs > 0 and 0 <= passed <= runs and passed == int(passed)):
            raise ValueError(f"FrontierCS pass counts are invalid for {upstream_id}")
        # The published percent must agree with the pass count it summarizes.
        if round(passed / runs * 100, 1) != rate:
            raise ValueError(f"FrontierCS pass rate disagrees for {upstream_id}")
        if not low <= fci <= high:
            raise ValueError(f"FrontierCS FCI interval is invalid for {upstream_id}")
        entry = FrontierCSEntry(
            upstream_id, name, harness, rate, int(passed), int(runs), fci, low, high
        )
        if entry.label in seen:
            raise ValueError(f"FrontierCS lists {entry.label!r} twice")
        seen.add(entry.label)
        entries.append(entry)
    if not MIN_EXPECTED_ENTRIES <= len(entries) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"FrontierCS 2 has {len(entries)} entries; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )
    return FrontierCSLeaderboard(updated, entries)


def fetch_frontiercs_2(client: httpx.Client | None = None) -> FrontierCSLeaderboard:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(30, connect=5), follow_redirects=True
    )
    try:
        response = active_client.get(FRONTIERCS_2_DATA_URL)
        response.raise_for_status()
        return parse_frontiercs_2(response.text)
    finally:
        if owned_client:
            active_client.close()


def _methodology(entry: FrontierCSEntry) -> str:
    return (
        f"{MANAGED_METHODOLOGY_PREFIX} Official leaderboard entry "
        f'"{entry.name}" ({entry.harness}): {entry.pass_rate}% pass rate '
        f"({entry.passes}/{entry.runs} runs beat the human reference), "
        f"FCI {entry.fci} (90% interval {entry.fci_low} to {entry.fci_high}), "
        f"listed at {FRONTIERCS_2_URL}. One run per task; FCI is refitted "
        "on every leaderboard update with Kimi K2.7 at 0."
    )


class FrontierCS2SyncService:
    """Create and revise reviewed FrontierCS 2 rows; never create papers."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        if task is None or dataset is None:
            raise RuntimeError("FrontierCS 2 task or benchmark is not configured")
        configured = (
            self.db.query(TaskDatasetMetric)
            .join(Metric, Metric.id == TaskDatasetMetric.metric_id)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
                Metric.name.in_(METRIC_NAMES),
            )
            .count()
        )
        if configured != len(METRIC_NAMES):
            raise RuntimeError("FrontierCS 2 metrics are not linked to the task")
        return task, dataset

    def _paper_ids(self) -> dict[str, int]:
        """Resolve reviewed paper identities without ever creating papers."""
        identities = MODEL_IDENTITIES.values()
        arxiv_ids = {i.arxiv_id for i in identities if i.arxiv_id}
        source_urls = {i.source_url for i in identities if i.source_url}
        papers = (
            self.db.query(Paper.id, Paper.arxiv_id, Paper.source_url)
            .filter(
                Paper.is_latest_version,
                (Paper.arxiv_id.in_(arxiv_ids))
                | ((Paper.source == "external") & Paper.source_url.in_(source_urls)),
            )
            .order_by(Paper.id)
            .all()
        )
        resolved: dict[str, int] = {}
        for paper_id, arxiv_id, source_url in papers:
            key = arxiv_id if arxiv_id in arxiv_ids else source_url
            resolved[key] = paper_id
        return resolved

    def sync(
        self, leaderboard: FrontierCSLeaderboard, *, commit: bool = True
    ) -> FrontierCSSyncStats:
        entries = leaderboard.entries
        selected = [
            (MODEL_IDENTITIES[entry.name], entry)
            for entry in entries
            if entry.name in MODEL_IDENTITIES
        ]
        if len(selected) < MIN_SELECTED_ENTRIES:
            raise RuntimeError(
                f"FrontierCS 2 has only {len(selected)} reviewed entries; "
                "refusing to update the managed leaderboard"
            )
        stats = FrontierCSSyncStats(
            fetched=len(entries),
            unreviewed=[e.label for e in entries if e.name not in MODEL_IDENTITIES],
        )
        try:
            task, dataset = self._leaderboard_identity()
            paper_ids = self._paper_ids()
            rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .order_by(Evaluation.id)
                .all()
            )
            rows_by_identity: dict[tuple[int, str, str | None], Evaluation] = {}
            for row in rows:
                rows_by_identity.setdefault(
                    (row.paper_id, row.model_name, row.harness), row
                )
            linked_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            now = datetime.now(UTC)
            published: set[int] = set()
            for identity, entry in selected:
                paper_id = paper_ids.get(identity.paper_key)
                if paper_id is None:
                    stats.missing_papers.append(entry.label)
                    continue
                metrics = {PASS_RATE: entry.pass_rate, FCI: entry.fci}
                methodology = _methodology(entry)
                key = (paper_id, identity.model_name, entry.harness)
                row = rows_by_identity.get(key)
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=identity.model_name,
                        harness=entry.harness,
                        is_open=identity.is_open,
                        hf_model_url=identity.hf_model_url,
                        external_source_url=FRONTIERCS_2_URL,
                        source_url=FRONTIERCS_2_URL,
                        external=True,
                        uses_additional_data=False,
                    )
                    self.db.add(row)
                    rows_by_identity[key] = row
                    stats.created += 1
                elif row.metrics != metrics or row.methodology != methodology:
                    stats.changed += 1
                row.metrics = metrics
                row.methodology = methodology
                row.best_metric = PASS_RATE
                row.evaluated_on = leaderboard.updated
                row.updated_at = now
                if paper_id not in linked_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                    )
                    linked_paper_ids.add(paper_id)
                published.add(id(row))
                stats.matched += 1

            stats.missing_upstream = sorted(
                f"{row.model_name} ({row.harness})"
                for row in rows
                if id(row) not in published
                and (row.methodology or "").startswith(MANAGED_METHODOLOGY_PREFIX)
            )
            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id, dataset.id, metric_name=PASS_RATE, commit=False
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
