"""Synchronize Cognition's living FrontierCode 1.1 leaderboard."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from math import isfinite
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
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.leaderboard_model_matching_service import (
    LeaderboardModel,
    LeaderboardModelMatcher,
)
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix
from backend.services.paper_ingestion_service import PaperIngestionService

FRONTIERCODE_ENDPOINT = "https://cognition.com/data/frontiercode-leaderboard/data.json"
FRONTIERCODE_SOURCE_URL = "https://cognition.com/frontiercode"
TASK_SLUG = "coding-agents"
DATASET_SLUGS = {"main": "frontiercode-main", "extended": "frontiercode-extended"}
METRIC_NAMES = ("Score", "Pass Rate")
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("FrontierCode")
MIN_EXPECTED_MODELS = 20
MAX_EXPECTED_MODELS = 60
EXPECTED_SUBSET_SIZES = {"main": 100, "extended": 150}

HARNESS_NAMES = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "grok-build": "Grok Build",
    "chisel": "Chisel",
    "mini-swe-agent": "MiniSWE-Agent",
    "cursor-cli": "Cursor CLI",
}


@dataclass(frozen=True)
class PaperIdentity:
    arxiv_id: str | None = None
    source_url: str | None = None
    title: str | None = None
    date_published: date | None = None
    abstract: str | None = None
    is_open: bool = False

    def __post_init__(self) -> None:
        if (self.arxiv_id is None) == (self.source_url is None):
            raise ValueError("PaperIdentity requires exactly one stable identity")
        if self.source_url and (not self.title or not self.date_published):
            raise ValueError(
                "External paper identities require title and publication date"
            )


def external(
    source_url: str,
    title: str,
    published: str,
    *,
    abstract: str | None = None,
    is_open: bool = False,
) -> PaperIdentity:
    return PaperIdentity(
        source_url=source_url,
        title=title,
        date_published=date.fromisoformat(published),
        abstract=abstract,
        is_open=is_open,
    )


# Exact, reviewed introducing papers or official release pages for every model
# present on FrontierCode 1.1 when it was last reviewed. Other models are
# matched automatically when the catalog names them unambiguously, and
# otherwise handed to the release radar.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "Claude Haiku 5.5": external(
        "https://www.anthropic.com/claude-haiku-5-5",
        "Introducing Claude Haiku 5.5",
        "2026-10-07",
    ),
    "Claude Opus 5.5": external(
        "https://www.anthropic.com/claude-opus-5-5",
        "Introducing Claude Opus 5.5",
        "2026-09-22",
    ),
    "Claude Sonnet 5.5": external(
        "https://www.anthropic.com/claude-sonnet-5-5",
        "Introducing Claude Sonnet 5.5",
        "2026-09-28",
    ),
    "GPT-6 Sol": external(
        "https://openai.com/index/introducing-gpt-6-sol-and-luna/",
        "Introducing GPT-6 Sol and Luna",
        "2026-09-22",
    ),
    "GPT-6 Luna": external(
        "https://openai.com/index/introducing-gpt-6-sol-and-luna/",
        "Introducing GPT-6 Sol and Luna",
        "2026-09-22",
    ),
    "GPT-6.1 Sol": external(
        "https://openai.com/index/introducing-gpt-6-1-sol/",
        "Introducing GPT-6.1 Sol",
        "2026-09-29",
    ),
    "Grok 4.7": external(
        "https://x.ai/news/grok-4-7",
        "Introducing Grok 4.7",
        "2026-09-21",
    ),
    "Claude Fable 5.1": external(
        "https://www.anthropic.com/claude-fable-and-mythos-5-1",
        "Introducing Claude Fable 5.1 and Claude Mythos 5.1",
        "2026-09-01",
    ),
    "DeepSeek V4 Pro 0813": PaperIdentity(arxiv_id="2606.19348", is_open=True),
    "GLM 5.3": external(
        "https://z.ai/blog/glm-5.3",
        "GLM-5.3: Frontier Coding with Emergent Cyber Capabilities",
        "2026-08-14",
        is_open=True,
    ),
    "GLM 5.3 Flash": external(
        "https://z.ai/blog/glm-5.3-flash",
        "GLM-5.3-Flash: Frontier Intelligence, Flash Cost",
        "2026-08-26",
        is_open=True,
    ),
    "GPT-6 Astra": external(
        "https://openai.com/index/gpt-6-astra/",
        "GPT-6 Astra: A new generation of intelligence",
        "2026-09-03",
    ),
    "Gemini 3.8 Flash": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/",
        "Introducing Gemini 3.8 Flash and 3.8 Flash Cyber",
        "2026-09-02",
    ),
    "Nemotron 3 Ultra": PaperIdentity(arxiv_id="2606.15007", is_open=True),
    "Claude Fable 5": external(
        "https://www.anthropic.com/news/claude-fable-5-mythos-5",
        "Claude Fable 5 and Claude Mythos 5",
        "2026-06-09",
    ),
    "GPT-5.6 Sol": external(
        "https://openai.com/index/gpt-5-6/",
        "GPT-5.6: Frontier intelligence that scales with your ambition",
        "2026-07-09",
    ),
    "Claude Opus 4.8": external(
        "https://www.anthropic.com/news/claude-opus-4-8",
        "Claude Opus 4.8",
        "2026-05-28",
    ),
    "GPT-5.5": external(
        "https://openai.com/index/introducing-gpt-5-5/",
        "Introducing GPT-5.5",
        "2026-04-23",
    ),
    "Grok 4.5": external(
        "https://x.ai/news/grok-4-5", "Introducing Grok 4.5", "2026-07-08"
    ),
    "Grok 4.6": external(
        "https://x.ai/news/grok-4-6", "Introducing Grok 4.6", "2026-08-12"
    ),
    "Claude Sonnet 5": external(
        "https://www.anthropic.com/news/claude-sonnet-5",
        "Claude Sonnet 5",
        "2026-06-30",
    ),
    "GPT-5.6 Terra": external(
        "https://openai.com/index/gpt-5-6/",
        "GPT-5.6: Frontier intelligence that scales with your ambition",
        "2026-07-09",
    ),
    "GPT-5.6 Luna": external(
        "https://openai.com/index/gpt-5-6/",
        "GPT-5.6: Frontier intelligence that scales with your ambition",
        "2026-07-09",
    ),
    "SWE-2": external(
        "https://cognition.com/blog/swe-2",
        "Introducing SWE-2: Pushing the Pareto Frontier",
        "2026-09-10",
        abstract=(
            "Cognition's SWE-2 coding model is post-trained from Kimi K3, "
            "using reinforcement learning across reasoning-effort levels "
            "to improve coding capability and cost, and is available in Devin."
        ),
    ),
    "SWE-1.7": external(
        "https://cognition.com/blog/swe-1-7",
        "SWE-1.7: Frontier Intelligence at a Fraction of the Cost",
        "2026-07-08",
        abstract=(
            "Cognition's SWE-1.7 coding-agent model improves frontier-level "
            "software engineering performance and is available in Devin."
        ),
    ),
    "Claude Opus 4.7": external(
        "https://www.anthropic.com/news/claude-opus-4-7",
        "Claude Opus 4.7",
        "2026-04-16",
    ),
    "Kimi K2.7": external(
        "https://huggingface.co/moonshotai/Kimi-K2.7-Code",
        "Kimi K2.7 Code",
        "2026-06-11",
        is_open=True,
    ),
    "Composer 2.5": PaperIdentity(arxiv_id="2603.24477"),
    "GLM 5.2": external(
        "https://z.ai/blog/glm-5.2",
        "GLM-5.2: Built for Long-Horizon Tasks",
        "2026-06-16",
        is_open=True,
    ),
    "DeepSeek V4 Pro": PaperIdentity(arxiv_id="2606.19348", is_open=True),
    "MiniMax M3": external(
        "https://www.minimax.io/blog/minimax-m3",
        "MiniMax M3: Frontier Coding, 1M Context, Native Multimodality — All in One Model",
        "2026-06-01",
        is_open=True,
    ),
    "Inkling": external(
        "https://thinkingmachines.ai/news/introducing-inkling/",
        "Inkling: Our open-weights model",
        "2026-07-15",
        is_open=True,
    ),
    "Qwen 3.7 Plus": external(
        "https://www.qwencloud.com/models/qwen3.7-plus",
        "Qwen 3.7 Plus",
        "2026-06-02",
    ),
    "Claude Opus 5": external(
        "https://www.anthropic.com/news/claude-opus-5",
        "Introducing Claude Opus 5",
        "2026-07-24",
    ),
    "SWE-1.6": external(
        "https://cognition.com/blog/swe-1-6",
        "Introducing SWE 1.6: Improving Model UX",
        "2026-04-07",
        abstract=(
            "Cognition's SWE-1.6 release improves coding-agent model user "
            "experience, including reduced overthinking and better tool use."
        ),
    ),
    "Kimi K3": PaperIdentity(arxiv_id="2607.24653", is_open=True),
    "Gemini 3.6 Flash": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
        "Introducing Gemini 3.6 Flash, 3.5 Flash-Lite, and 3.5 Flash Cyber",
        "2026-07-21",
    ),
    "Gemini 3.7 Flash": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-3-7-flash/",
        "Introducing Gemini 3.7 Flash",
        "2026-08-13",
    ),
    "GPT-5.4-mini": external(
        "https://openai.com/index/introducing-gpt-5-4-mini-and-nano/",
        "Introducing GPT-5.4 mini and nano",
        "2026-03-17",
        abstract=(
            "OpenAI's GPT-5.4 mini and nano release introduces smaller models "
            "optimized for lower-latency and lower-cost workloads."
        ),
    ),
    "Claude Opus 4.6": external(
        "https://www.anthropic.com/news/claude-opus-4-6",
        "Claude Opus 4.6",
        "2026-02-05",
    ),
    "Claude Sonnet 4.6": external(
        "https://www.anthropic.com/news/claude-sonnet-4-6",
        "Claude Sonnet 4.6",
        "2026-02-17",
    ),
    "DeepSeek V4 Flash 0731": PaperIdentity(arxiv_id="2606.19348", is_open=True),
    "Mistral 3.5 Medium": external(
        "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
        "Mistral Medium 3.5",
        "2026-04-28",
        abstract=(
            "Mistral Medium 3.5 is a general-purpose model release documented "
            "for text and coding workloads."
        ),
        is_open=True,
    ),
    "DeepSeek V4.1 Flash": PaperIdentity(arxiv_id="2609.19969", is_open=True),
    "Gemini 4 Argon": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/",
        "Gemini 4 Argon: our next era of frontier intelligence",
        "2026-09-30",
    ),
    # "Mistral Large 4 (Preview)" left the leaderboard on 2026-10-28.
}


@dataclass(frozen=True)
class FrontierCodeEntry:
    model: str
    effort: str
    harness: str
    subset: str
    score: float
    pass_rate: float
    lab: str = ""


@dataclass(frozen=True)
class FrontierCodeLeaderboard:
    entries: list[FrontierCodeEntry]


@dataclass
class FrontierCodeDiscovery:
    papers: dict[str, int] = field(default_factory=dict)
    indexed_papers: list[str] = field(default_factory=list)
    would_index: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": len(self.papers),
            "indexed_papers": self.indexed_papers,
            "would_index": self.would_index,
        }


@dataclass
class FrontierCodeSyncStats:
    fetched_models: int = 0
    selected: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    matched: int = 0
    indexed_papers: int = 0
    # Models outside MODEL_PAPER_IDENTITIES that the catalog matched on its own.
    auto_matched: list[str] = field(default_factory=list)
    # Models with no paper yet; each is a release signal for the radar.
    unreviewed: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)
    datasets: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _finite_rate(value: Any, *, field_name: str, model: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"FrontierCode {field_name} is invalid for {model}")
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"FrontierCode {field_name} is not finite for {model}")
    if not 0 <= parsed <= 1:
        raise ValueError(f"FrontierCode {field_name} is outside 0-1 for {model}")
    return parsed


def parse_frontiercode_leaderboard(payload: Any) -> FrontierCodeLeaderboard:
    if not isinstance(payload, dict) or not isinstance(payload.get("v1_1"), dict):
        raise TypeError("FrontierCode response must contain a v1_1 object")
    revision = payload["v1_1"]
    models = revision.get("models")
    efforts = revision.get("efforts")
    subsets = revision.get("subsets")
    harnesses = revision.get("harness")
    data = revision.get("data")
    if not all(
        isinstance(value, dict) for value in (efforts, subsets, harnesses, data)
    ):
        raise TypeError("FrontierCode v1_1 metadata is malformed")
    if (
        not isinstance(models, list)
        or not MIN_EXPECTED_MODELS <= len(models) <= MAX_EXPECTED_MODELS
    ):
        count = len(models) if isinstance(models, list) else "invalid"
        raise ValueError(f"FrontierCode returned {count} models")
    if subsets != EXPECTED_SUBSET_SIZES:
        raise ValueError(f"FrontierCode subset sizes changed: {subsets!r}")
    if len(set(models)) != len(models):
        raise ValueError("FrontierCode response contains duplicate models")
    missing = sorted(set(MODEL_PAPER_IDENTITIES) - set(models))
    if missing:
        raise ValueError(f"FrontierCode reviewed models are missing: {missing!r}")
    # The legend colors each model by its lab; a lab is known only when
    # exactly one lab has the model's color.
    colors = revision.get("colors")
    lab_colors = revision.get("lab_colors")
    if not isinstance(colors, dict) or not isinstance(lab_colors, dict):
        colors, lab_colors = {}, {}
    labs_by_color: dict[str, list[str]] = {}
    for lab, color in lab_colors.items():
        if isinstance(lab, str) and isinstance(color, str):
            labs_by_color.setdefault(color, []).append(lab.strip()[:200])

    entries: list[FrontierCodeEntry] = []
    for model in models:
        if not isinstance(model, str) or not model.strip() or len(model) > 255:
            raise ValueError("FrontierCode response contains an invalid model name")
        model_efforts = efforts.get(model)
        harness = harnesses.get(model)
        model_data = data.get(model)
        if not isinstance(model_efforts, list) or not model_efforts:
            raise ValueError(f"FrontierCode has no efforts for {model}")
        if not isinstance(harness, str) or not harness.strip() or len(harness) > 255:
            raise ValueError(f"FrontierCode has an invalid harness for {model}")
        if not isinstance(model_data, dict):
            raise TypeError(f"FrontierCode has no data for {model}")
        color = colors.get(model)
        labs = labs_by_color.get(color, []) if isinstance(color, str) else []
        lab = labs[0] if len(labs) == 1 else ""
        for effort in model_efforts:
            if not isinstance(effort, str) or not effort.strip() or len(effort) > 32:
                raise ValueError(f"FrontierCode has an invalid effort for {model}")
            effort_data = model_data.get(effort)
            if not isinstance(effort_data, dict):
                raise TypeError(f"FrontierCode has no {effort} data for {model}")
            for subset in DATASET_SLUGS:
                result = effort_data.get(subset)
                if not isinstance(result, dict):
                    raise TypeError(
                        f"FrontierCode has no {subset} data for {model}/{effort}"
                    )
                entries.append(
                    FrontierCodeEntry(
                        model=model,
                        effort=effort,
                        harness=HARNESS_NAMES.get(harness, harness),
                        subset=subset,
                        score=_finite_rate(
                            result.get("new_score"), field_name="score", model=model
                        ),
                        pass_rate=_finite_rate(
                            result.get("correct"), field_name="pass rate", model=model
                        ),
                        lab=lab,
                    )
                )
    return FrontierCodeLeaderboard(entries=entries)


def fetch_frontiercode_leaderboard(
    client: httpx.Client | None = None,
) -> FrontierCodeLeaderboard:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=False,
        headers={"User-Agent": "paperswithcode-frontiercode-sync/1.0"},
    )
    try:
        response = active_client.get(FRONTIERCODE_ENDPOINT)
        response.raise_for_status()
        return parse_frontiercode_leaderboard(response.json())
    finally:
        if owned_client:
            active_client.close()


def select_best_entries(entries: list[FrontierCodeEntry]) -> list[FrontierCodeEntry]:
    best: dict[tuple[str, str], FrontierCodeEntry] = {}
    for entry in entries:
        key = (entry.model, entry.subset)
        current = best.get(key)
        if current is None or entry.score > current.score:
            best[key] = entry
    return sorted(
        best.values(), key=lambda entry: (entry.subset, -entry.score, entry.model)
    )


def _managed_key(row: Evaluation) -> tuple[str, str] | None:
    methodology = row.methodology or ""
    if not methodology.startswith(MANAGED_METHODOLOGY_PREFIX):
        return None
    marker = " subset="
    start = methodology.find(marker)
    if start == -1:
        return None
    subset = methodology[start + len(marker) :].split(";", 1)[0]
    return row.model_name or "", subset


class FrontierCodeSyncService:
    """Replace only evaluation rows owned by the FrontierCode live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, dict[str, Dataset]]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        datasets = {
            subset: self.db.query(Dataset).filter(Dataset.slug == slug).one_or_none()
            for subset, slug in DATASET_SLUGS.items()
        }
        metric_ids = {
            metric.name: metric.id
            for metric in self.db.query(Metric)
            .filter(Metric.name.in_(METRIC_NAMES))
            .all()
        }
        if task is None or any(dataset is None for dataset in datasets.values()):
            raise RuntimeError("FrontierCode task or benchmarks are not configured")
        if set(metric_ids) != set(METRIC_NAMES):
            raise RuntimeError("FrontierCode metrics are not configured")
        for dataset in datasets.values():
            for metric_id in metric_ids.values():
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
                    raise RuntimeError(
                        "FrontierCode leaderboard metrics are not linked"
                    )
        return task, datasets  # type: ignore[return-value]

    def sync(
        self,
        leaderboard: FrontierCodeLeaderboard,
        *,
        discovery: FrontierCodeDiscovery,
        commit: bool = True,
    ) -> FrontierCodeSyncStats:
        selected = select_best_entries(leaderboard.entries)
        if not selected:
            raise ValueError(
                "Refusing to synchronize an empty FrontierCode leaderboard"
            )
        stats = FrontierCodeSyncStats(
            fetched_models=len({entry.model for entry in leaderboard.entries}),
            selected=len(selected),
            indexed_papers=len(discovery.indexed_papers),
        )
        try:
            task, datasets = self._leaderboard_identity()
            stats.datasets = {
                subset: dataset.id for subset, dataset in datasets.items()
            }
            managed_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id.in_(
                        [dataset.id for dataset in datasets.values()]
                    ),
                    Evaluation.external_source_url == FRONTIERCODE_SOURCE_URL,
                    Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
                )
                .all()
            )
            managed = {
                key: row
                for row in managed_rows
                if (key := _managed_key(row)) is not None
            }
            linked_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            upstream_keys = {(entry.model, entry.subset) for entry in selected}
            new_models = list(
                dict.fromkeys(
                    LeaderboardModel(entry.model, entry.lab)
                    for entry in selected
                    if entry.model not in MODEL_PAPER_IDENTITIES
                )
            )
            matcher = LeaderboardModelMatcher(
                self.db,
                provider="frontiercode",
                leaderboard_name="FrontierCode",
                leaderboard_url=FRONTIERCODE_SOURCE_URL,
            )
            matched = matcher.match(new_models)
            stats.auto_matched = [m.name for m in new_models if m.name in matched]
            stats.unreviewed = [m.name for m in new_models if m.name not in matched]
            matcher.report_unmatched([m for m in new_models if m.name not in matched])
            for entry in selected:
                if entry.model in MODEL_PAPER_IDENTITIES:
                    identity = MODEL_PAPER_IDENTITIES[entry.model]
                    paper_id = discovery.papers.get(entry.model)
                    is_open, hf_model_url = identity.is_open, None
                elif (match := matched.get(entry.model)) is not None:
                    paper_id = match.paper_id
                    is_open, hf_model_url = match.is_open, match.hf_model_url
                else:
                    continue
                if paper_id is None:
                    if commit:
                        raise RuntimeError(
                            f"No reviewed paper resolved for {entry.model}"
                        )
                    stats.missing_papers.append(entry.model)
                    continue
                key = (entry.model, entry.subset)
                row = managed.get(key)
                methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} subset={entry.subset}; "
                    f"FrontierCode 1.1 best reasoning effort={entry.effort}; "
                    f"{EXPECTED_SUBSET_SIZES[entry.subset]} tasks; unfair internet-use runs are zeroed."
                )
                metrics = {
                    "Score": round(entry.score * 100, 4),
                    "Pass Rate": round(entry.pass_rate * 100, 4),
                }
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=datasets[entry.subset].id,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                row.paper_id = paper_id
                row.model_name = entry.model
                row.harness = entry.harness
                row.methodology = methodology
                row.metrics = metrics
                row.uses_additional_data = False
                row.is_open = is_open
                if hf_model_url:
                    row.hf_model_url = hf_model_url
                row.best_metric = "Score"
                row.evaluated_on = datetime.now(UTC).date()
                row.external_source_url = FRONTIERCODE_SOURCE_URL
                row.source_url = FRONTIERCODE_SOURCE_URL
                row.external = True
                row.updated_at = datetime.now(UTC)
                if paper_id not in linked_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                    )
                    linked_paper_ids.add(paper_id)
                stats.matched += 1
            for key, row in managed.items():
                if key not in upstream_keys:
                    self.db.delete(row)
                    stats.deleted += 1
            self.db.flush()
            service = EvaluationService(self.db)
            for dataset in datasets.values():
                for metric_name in METRIC_NAMES:
                    service.recalculate_ranks(
                        task.id,
                        dataset.id,
                        metric_name=metric_name,
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


class FrontierCodePaperDiscoveryService:
    def __init__(
        self,
        db: Session,
        *,
        ingestion_service: PaperIngestionService | None = None,
        external_service: ExternalResourceService | None = None,
    ):
        self.db = db
        self.ingestion_service = ingestion_service or PaperIngestionService(db)
        self.external_service = external_service or ExternalResourceService(db)

    async def discover(self, *, persist: bool = True) -> FrontierCodeDiscovery:
        result = FrontierCodeDiscovery()
        for model, identity in MODEL_PAPER_IDENTITIES.items():
            query = self.db.query(Paper).filter(Paper.is_latest_version)
            paper = (
                (
                    query.filter(Paper.arxiv_id == identity.arxiv_id)
                    if identity.arxiv_id
                    else query.filter(
                        Paper.source == "external",
                        Paper.source_url == identity.source_url,
                    )
                )
                .order_by(Paper.id.desc())
                .first()
            )
            if paper is None and not persist:
                result.would_index.append(
                    identity.arxiv_id or identity.source_url or model
                )
                continue
            if paper is None and identity.arxiv_id:
                paper, created = await self.ingestion_service.get_or_import_arxiv_paper(
                    identity.arxiv_id
                )
                if created:
                    result.indexed_papers.append(identity.arxiv_id)
            elif paper is None:
                ingestion = self.external_service.add_external_resource(
                    ExternalResourceInput(
                        source_url=identity.source_url or "",
                        title=identity.title or model,
                        abstract=identity.abstract,
                        date_published=identity.date_published,
                    )
                )
                paper = (
                    self.db.query(Paper).filter(Paper.id == ingestion.paper.id).one()
                )
                result.indexed_papers.append(identity.source_url or model)
            result.papers[model] = paper.id
        return result


async def discover_frontiercode_papers(
    db: Session, *, persist: bool = True
) -> FrontierCodeDiscovery:
    return await FrontierCodePaperDiscoveryService(db).discover(persist=persist)


def run_discovery(db: Session, *, persist: bool = True) -> FrontierCodeDiscovery:
    return asyncio.run(discover_frontiercode_papers(db, persist=persist))
