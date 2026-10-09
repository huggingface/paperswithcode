"""Synchronize DeepSWE's living v1.1 leaderboard into evaluation rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService

DEEPSWE_ENDPOINT = "https://deepswe.datacurve.ai/artifacts/v1.1/leaderboard-live.json"
DEEPSWE_SOURCE_URL = "https://deepswe.datacurve.ai/"
DATASET_SLUG = "deepswe"
TASK_SLUG = "coding-agents"
METRIC_NAME = "Pass@1"
HARNESS_NAME = "MiniSWE-Agent"
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code DeepSWE live sync."
MIN_EXPECTED_CONFIGS = 40
MAX_EXPECTED_CONFIGS = 100
MIN_EXPECTED_MODELS = 15
MAX_EXPECTED_MODELS = 50


@dataclass(frozen=True)
class PaperIdentity:
    arxiv_id: str | None = None
    source_url: str | None = None
    is_open: bool = False

    def __post_init__(self) -> None:
        if (self.arxiv_id is None) == (self.source_url is None):
            raise ValueError("PaperIdentity requires exactly one stable identity")


# Product labels are never fuzzily attached to papers. New upstream models remain
# unmatched until a curator adds a defensible release identity here.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "claude-opus-5": PaperIdentity(
        source_url="https://www.anthropic.com/news/claude-opus-5"
    ),
    "gpt-5-6-sol": PaperIdentity(source_url="https://openai.com/index/gpt-5-6/"),
    "claude-fable-5": PaperIdentity(
        source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5"
    ),
    "gpt-5-6-terra": PaperIdentity(source_url="https://openai.com/index/gpt-5-6/"),
    "kimi-k3": PaperIdentity(arxiv_id="2607.24653", is_open=True),
    "gpt-5-6-luna": PaperIdentity(source_url="https://openai.com/index/gpt-5-6/"),
    "gpt-5-5": PaperIdentity(
        source_url="https://openai.com/index/introducing-gpt-5-5/"
    ),
    "deepseek-v4-pro": PaperIdentity(arxiv_id="2606.19348", is_open=True),
    "claude-opus-4-8": PaperIdentity(
        source_url="https://www.anthropic.com/news/claude-opus-4-8"
    ),
    "claude-sonnet-5": PaperIdentity(
        source_url="https://www.anthropic.com/news/claude-sonnet-5"
    ),
    "grok-4-5": PaperIdentity(source_url="https://x.ai/news/grok-4-5"),
    "deepseek-v4-flash": PaperIdentity(arxiv_id="2606.19348", is_open=True),
    "muse-spark-1-1": PaperIdentity(
        source_url="https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/"
    ),
    "gpt-5-4": PaperIdentity(
        source_url="https://openai.com/index/introducing-gpt-5-4/"
    ),
    "gemini-3-6-flash": PaperIdentity(
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/"
        )
    ),
    "glm-5-2": PaperIdentity(source_url="https://z.ai/blog/glm-5.2", is_open=True),
    "gemini-3-5-flash": PaperIdentity(
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-3-5/"
        )
    ),
    "kimi-k2-7-code": PaperIdentity(
        source_url="https://huggingface.co/moonshotai/Kimi-K2.7-Code",
        is_open=True,
    ),
    "claude-sonnet-4-6": PaperIdentity(
        source_url="https://www.anthropic.com/news/claude-sonnet-4-6"
    ),
    "gemini-3-1-pro-preview": PaperIdentity(
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-3-1-pro/"
        )
    ),
}

MODEL_DISPLAY_NAMES = {
    "claude-opus-5": "Claude Opus 5",
    "gpt-5-6-sol": "GPT-5.6 Sol",
    "claude-fable-5": "Claude Fable 5",
    "gpt-5-6-terra": "GPT-5.6 Terra",
    "kimi-k3": "Kimi K3",
    "grok-4-6": "Grok 4.6",
    "gpt-5-6-luna": "GPT-5.6 Luna",
    "gpt-5-5": "GPT-5.5",
    "gemini-3-7-flash": "Gemini 3.7 Flash",
    "deepseek-v4-pro": "DeepSeek-V4-Pro",
    "claude-opus-4-8": "Claude Opus 4.8",
    "qwen3-8-max": "Qwen3.8 Max",
    "muse-spark-1-2": "Muse Spark 1.2",
    "claude-sonnet-5": "Claude Sonnet 5",
    "grok-4-5": "Grok 4.5",
    "deepseek-v4-flash": "DeepSeek-V4-Flash",
    "muse-spark-1-1": "Muse Spark 1.1",
    "gpt-5-4": "GPT-5.4",
    "gemini-3-6-flash": "Gemini 3.6 Flash",
    "glm-5-2": "GLM-5.2",
    "gemini-3-5-flash": "Gemini 3.5 Flash",
    "kimi-k2-7-code": "Kimi K2.7 Code",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "gemini-3-1-pro-preview": "Gemini 3.1 Pro Preview",
}

# These rows predate the managed sync and came from the same DeepSWE v1.1 page.
# Adopting them avoids duplicate leaderboard entries on the first run.
LEGACY_MODEL_NAMES = {
    "claude-fable-5": "Claude Fable 5 (max)",
    "gpt-5-5": "GPT-5.5 (xhigh)",
    "claude-opus-4-8": "Claude Opus 4.8 (max)",
    "gpt-5-4": "GPT-5.4 (xhigh)",
    "kimi-k2-7-code": "Kimi K2.7 Code",
    "claude-sonnet-4-6": "Claude Sonnet 4.6 (high)",
    "gemini-3-1-pro-preview": "Gemini 3.1 Pro (high)",
}


@dataclass(frozen=True)
class DeepSweEntry:
    model: str
    harness: str
    reasoning_effort: str | None
    config: str
    pass_at_1: float
    ci_half: float
    n_attempted: int
    n_tasks_attempted: int
    n_runs: int
    mean_cost_usd: float | None
    mean_output_tokens: float | None
    mean_agent_steps: float | None


@dataclass(frozen=True)
class DeepSweLeaderboard:
    generated_at: datetime
    n_tasks: int
    entries: list[DeepSweEntry]


@dataclass
class DeepSweSyncStats:
    fetched_configs: int = 0
    fetched_models: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unmatched_models: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched_configs": self.fetched_configs,
            "fetched_models": self.fetched_models,
            "matched": self.matched,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "unmatched_models": self.unmatched_models,
            "missing_papers": self.missing_papers,
        }


def _finite_number(value: Any, *, field_name: str, model: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"DeepSWE {field_name} is invalid for {model}")
    parsed = float(value)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise ValueError(f"DeepSWE {field_name} is not finite for {model}")
    return parsed


def parse_deepswe_leaderboard(payload: Any) -> DeepSweLeaderboard:
    """Validate the upstream artifact before it can affect persisted rows."""
    if not isinstance(payload, dict):
        raise TypeError("DeepSWE response must be a JSON object")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise TypeError("DeepSWE rows must be a JSON list")
    if not MIN_EXPECTED_CONFIGS <= len(rows) <= MAX_EXPECTED_CONFIGS:
        raise ValueError(
            f"DeepSWE returned {len(rows)} configs; expected "
            f"{MIN_EXPECTED_CONFIGS}-{MAX_EXPECTED_CONFIGS}"
        )
    n_tasks = payload.get("n_tasks_in_set")
    if (
        isinstance(n_tasks, bool)
        or not isinstance(n_tasks, int)
        or not 100 <= n_tasks <= 200
    ):
        raise ValueError("DeepSWE task count is outside accepted bounds")
    generated_raw = payload.get("generated_at")
    if not isinstance(generated_raw, str):
        raise TypeError("DeepSWE generated_at must be an ISO timestamp")
    generated_at = datetime.fromisoformat(generated_raw.replace("Z", "+00:00"))
    if generated_at.tzinfo is None:
        raise ValueError("DeepSWE generated_at must include a timezone")

    entries: list[DeepSweEntry] = []
    configs: set[str] = set()
    models: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise TypeError("DeepSWE rows must be JSON objects")
        model = raw.get("model")
        harness = raw.get("harness")
        effort = raw.get("reasoning_effort")
        config = raw.get("config")
        if not isinstance(model, str) or not model.strip() or len(model) > 255:
            raise ValueError("DeepSWE row has an invalid model")
        if harness != "mini-swe-agent":
            raise ValueError(f"DeepSWE harness is invalid for {model}")
        if effort is not None and (
            not isinstance(effort, str) or not effort.strip() or len(effort) > 32
        ):
            raise ValueError(f"DeepSWE reasoning effort is invalid for {model}")
        if not isinstance(config, str) or not config.strip() or len(config) > 255:
            raise ValueError(f"DeepSWE config is invalid for {model}")
        if config in configs:
            raise ValueError("DeepSWE response contains duplicate configs")
        configs.add(config)
        models.add(model)

        score = _finite_number(
            raw.get("pass_at_1"), field_name="pass_at_1", model=model
        )
        ci_half = _finite_number(raw.get("ci_half"), field_name="ci_half", model=model)
        if not 0 <= score <= 1 or not 0 <= ci_half <= 1:
            raise ValueError(f"DeepSWE score is outside accepted bounds for {model}")
        integer_fields: dict[str, int] = {}
        for field_name in ("n_attempted", "n_tasks_attempted", "n_runs"):
            value = raw.get(field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"DeepSWE {field_name} is invalid for {model}")
            integer_fields[field_name] = value
        if integer_fields["n_tasks_attempted"] > n_tasks:
            raise ValueError(f"DeepSWE attempted too many tasks for {model}")

        optional_numbers: dict[str, float | None] = {}
        for field_name in (
            "mean_cost_usd",
            "mean_output_tokens",
            "mean_agent_steps",
        ):
            value = raw.get(field_name)
            optional_numbers[field_name] = (
                None
                if value is None
                else _finite_number(value, field_name=field_name, model=model)
            )
            if (
                optional_numbers[field_name] is not None
                and optional_numbers[field_name] < 0
            ):
                raise ValueError(f"DeepSWE {field_name} is negative for {model}")

        entries.append(
            DeepSweEntry(
                model=model,
                harness=harness,
                reasoning_effort=effort,
                config=config,
                pass_at_1=score,
                ci_half=ci_half,
                n_attempted=integer_fields["n_attempted"],
                n_tasks_attempted=integer_fields["n_tasks_attempted"],
                n_runs=integer_fields["n_runs"],
                mean_cost_usd=optional_numbers["mean_cost_usd"],
                mean_output_tokens=optional_numbers["mean_output_tokens"],
                mean_agent_steps=optional_numbers["mean_agent_steps"],
            )
        )

    if not MIN_EXPECTED_MODELS <= len(models) <= MAX_EXPECTED_MODELS:
        raise ValueError(
            f"DeepSWE returned {len(models)} models; expected "
            f"{MIN_EXPECTED_MODELS}-{MAX_EXPECTED_MODELS}"
        )
    return DeepSweLeaderboard(
        generated_at=generated_at.astimezone(UTC), n_tasks=n_tasks, entries=entries
    )


def fetch_deepswe_leaderboard(
    client: httpx.Client | None = None,
) -> DeepSweLeaderboard:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=False,
        headers={"User-Agent": "paperswithcode-deepswe-sync/1.0"},
    )
    try:
        response = active_client.get(DEEPSWE_ENDPOINT)
        response.raise_for_status()
        return parse_deepswe_leaderboard(response.json())
    finally:
        if owned_client:
            active_client.close()


def select_best_entries(entries: list[DeepSweEntry]) -> list[DeepSweEntry]:
    """Select the source-defined best Pass@1 configuration for each model."""
    best: dict[str, DeepSweEntry] = {}
    for entry in entries:
        current = best.get(entry.model)
        if current is None or entry.pass_at_1 > current.pass_at_1:
            best[entry.model] = entry
    return sorted(best.values(), key=lambda entry: (-entry.pass_at_1, entry.model))


def _managed_model_key(methodology: str | None) -> str | None:
    if not methodology or not methodology.startswith(MANAGED_METHODOLOGY_PREFIX):
        return None
    marker = " upstream_model="
    start = methodology.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = methodology.find(";", start)
    return methodology[start:] if end == -1 else methodology[start:end]


def _model_name(entry: DeepSweEntry) -> str:
    display = MODEL_DISPLAY_NAMES.get(entry.model, entry.model)
    return (
        f"{display} ({entry.reasoning_effort})" if entry.reasoning_effort else display
    )


def _methodology(entry: DeepSweEntry, leaderboard: DeepSweLeaderboard) -> str:
    ci_percent = entry.ci_half * 100
    details = [
        f"upstream_model={entry.model}",
        "DeepSWE v1.1 best configuration",
        f"reasoning effort {entry.reasoning_effort or 'not reported'}",
        f"{entry.n_tasks_attempted}/{leaderboard.n_tasks} tasks attempted",
        f"{entry.n_attempted} scored attempts across {entry.n_runs} runs",
        f"95% confidence interval ±{ci_percent:.2f} percentage points",
    ]
    if entry.mean_cost_usd is not None:
        details.append(f"mean cost ${entry.mean_cost_usd:.2f} per attempt")
    if entry.mean_output_tokens is not None:
        details.append(f"mean output tokens {entry.mean_output_tokens:.0f}")
    if entry.mean_agent_steps is not None:
        details.append(f"mean agent steps {entry.mean_agent_steps:.0f}")
    details.append(f"upstream generated {leaderboard.generated_at.isoformat()}")
    return f"{MANAGED_METHODOLOGY_PREFIX} " + "; ".join(details) + "."


class DeepSweSyncService:
    """Replace only the evaluation rows owned by the DeepSWE live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metric = self.db.query(Metric).filter(Metric.name == METRIC_NAME).one_or_none()
        if task is None or dataset is None or metric is None:
            raise RuntimeError("DeepSWE task, benchmark, or metric is not configured")
        configured = (
            self.db.query(TaskDatasetMetric)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
                TaskDatasetMetric.metric_id == metric.id,
            )
            .one_or_none()
        )
        if configured is None:
            raise RuntimeError("DeepSWE leaderboard metric is not linked to the task")
        return task, dataset

    def _papers_by_model(self) -> tuple[dict[str, int], list[str]]:
        paper_ids: dict[str, int] = {}
        missing: list[str] = []
        for model, identity in MODEL_PAPER_IDENTITIES.items():
            query = self.db.query(Paper).filter(Paper.is_latest_version)
            if identity.arxiv_id:
                query = query.filter(Paper.arxiv_id == identity.arxiv_id)
                label = identity.arxiv_id
            else:
                query = query.filter(
                    Paper.source == "external", Paper.source_url == identity.source_url
                )
                label = identity.source_url or ""
            paper = query.one_or_none()
            if paper is None:
                missing.append(f"{model}:{label}")
            else:
                paper_ids[model] = paper.id
        return paper_ids, missing

    def sync(
        self,
        leaderboard: DeepSweLeaderboard,
        *,
        commit: bool = True,
    ) -> DeepSweSyncStats:
        best_entries = select_best_entries(leaderboard.entries)
        if not best_entries:
            raise ValueError("Refusing to synchronize an empty DeepSWE leaderboard")
        stats = DeepSweSyncStats(
            fetched_configs=len(leaderboard.entries),
            fetched_models=len(best_entries),
        )

        try:
            task, dataset = self._leaderboard_identity()
            paper_ids, missing_papers = self._papers_by_model()
            stats.missing_papers.extend(missing_papers)
            managed_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                    Evaluation.best_metric == METRIC_NAME,
                    Evaluation.external_source_url == DEEPSWE_SOURCE_URL,
                    Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
                )
                .all()
            )
            managed_by_key = {
                key: row
                for row in managed_rows
                if (key := _managed_model_key(row.methodology)) is not None
            }
            upstream_keys = {entry.model for entry in best_entries}

            for entry in best_entries:
                identity = MODEL_PAPER_IDENTITIES.get(entry.model)
                if identity is None:
                    stats.unmatched_models.append(entry.model)
                    continue
                paper_id = paper_ids.get(entry.model)
                if paper_id is None:
                    continue

                row = managed_by_key.get(entry.model)
                if row is None:
                    legacy_name = LEGACY_MODEL_NAMES.get(entry.model)
                    if legacy_name:
                        row = (
                            self.db.query(Evaluation)
                            .filter(
                                Evaluation.task_id == task.id,
                                Evaluation.dataset_id == dataset.id,
                                Evaluation.paper_id == paper_id,
                                Evaluation.model_name == legacy_name,
                                Evaluation.best_metric == METRIC_NAME,
                                Evaluation.external_source_url == DEEPSWE_SOURCE_URL,
                            )
                            .one_or_none()
                        )
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1

                row.paper_id = paper_id
                row.model_name = _model_name(entry)
                row.harness = HARNESS_NAME
                row.methodology = _methodology(entry, leaderboard)
                row.metrics = {METRIC_NAME: entry.pass_at_1}
                row.uses_additional_data = False
                row.is_open = identity.is_open
                row.best_metric = METRIC_NAME
                row.evaluated_on = leaderboard.generated_at.date()
                row.external_source_url = DEEPSWE_SOURCE_URL
                row.source_url = DEEPSWE_SOURCE_URL
                row.external = True
                row.updated_at = datetime.now(UTC)
                stats.matched += 1

            # A validated response is authoritative for model presence. Current
            # but unresolved models are protected; only disappeared managed rows go.
            for row in managed_rows:
                key = _managed_model_key(row.methodology)
                if key is not None and key not in upstream_keys:
                    self.db.delete(row)
                    stats.deleted += 1

            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id,
                dataset.id,
                metric_name=METRIC_NAME,
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
