"""Synchronize LlamaIndex's living ExtractBench schema-guided extraction leaderboard."""

from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from io import StringIO
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
from backend.services.paper_ingestion_service import PaperIngestionService

# The README leaderboard and grounding tables are both rendered from this CSV.
EXTRACTBENCH_CSV_URL = (
    "https://raw.githubusercontent.com/run-llama/ExtractBench/main/leaderboard.csv"
)
EXTRACTBENCH_SOURCE_URL = "https://github.com/run-llama/ExtractBench#leaderboard"
TASK_SLUG = "document-understanding"
DATASET_SLUG = "extractbench"
PRIMARY_METRIC_NAME = "Value F1"
GROUNDING_METRICS = (
    ("Word Grounding F1", "Word_Grounding"),
    ("Page Grounding F1", "Page_Grounding"),
)
METRIC_NAMES = (PRIMARY_METRIC_NAME, *(name for name, _ in GROUNDING_METRICS))
REQUIRED_COLUMNS = frozenset(
    {
        "Provider",
        "Category",
        "Overall",
        "Cost_Per_Page",
        *(column for _, column in GROUNDING_METRICS),
    }
)
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code ExtractBench live sync."
MIN_EXPECTED_ENTRIES = 30
MAX_EXPECTED_ENTRIES = 400
# Refuse to replace the managed leaderboard when the reviewed subset collapses.
MIN_REVIEWED_ENTRIES = 20


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

    @property
    def key(self) -> str:
        return self.arxiv_id or self.source_url or ""


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


def arxiv(arxiv_id: str, *, is_open: bool = True) -> PaperIdentity:
    return PaperIdentity(arxiv_id=arxiv_id, is_open=is_open)


_SONNET_5_5 = external(
    "https://www.anthropic.com/claude-sonnet-5-5",
    "Introducing Claude Sonnet 5.5",
    "2026-09-28",
)
_OPUS_5_5 = external(
    "https://www.anthropic.com/claude-opus-5-5",
    "Introducing Claude Opus 5.5",
    "2026-09-22",
)
_OPUS_4_8 = external(
    "https://www.anthropic.com/news/claude-opus-4-8",
    "Claude Opus 4.8",
    "2026-05-28",
)
_GPT_6_SOL_LUNA = external(
    "https://openai.com/index/introducing-gpt-6-sol-and-luna/",
    "Introducing GPT-6 Sol and Luna",
    "2026-09-22",
)
_GPT_5_6 = external(
    "https://openai.com/index/gpt-5-6/",
    "GPT-5.6: Frontier intelligence that scales with your ambition",
    "2026-07-09",
)
_GPT_5_5 = external(
    "https://openai.com/index/introducing-gpt-5-5/", "Introducing GPT-5.5", "2026-04-23"
)
_QWEN_3_5 = external(
    "https://qwen.ai/blog?id=qwen3.5",
    "Qwen3.5: Towards Native Multimodal Agents",
    "2026-02-16",
    is_open=True,
)
_INTERNVL_3_5 = arxiv("2508.18265")
_GEMMA_4 = arxiv("2607.02770")
# The ExtractBench paper is LlamaIndex's own report on its LlamaExtract tiers.
_LLAMAEXTRACT = arxiv("2607.29677", is_open=False)

# Exact upstream `Provider` labels are the trust boundary between a leaderboard
# row and its reviewed introducing paper or official release page. Rows whose
# label is not reviewed here stay unpublished and are reported by the job.
# Coding-agent rows (Claude Code, Codex) resolve to the underlying model.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "LlamaExtract Agentic Plus": _LLAMAEXTRACT,
    "LlamaExtract Agentic": _LLAMAEXTRACT,
    "LlamaExtract Cost-Effective": _LLAMAEXTRACT,
    "Claude Code (Sonnet 5.5 Evidence)": _SONNET_5_5,
    "Claude Code (Opus 5.5 Evidence)": _OPUS_5_5,
    "Claude Code (Opus 4.8 Evidence)": _OPUS_4_8,
    "Claude Code (Opus 4.8)": _OPUS_4_8,
    "Codex (GPT-6 Sol Evidence)": _GPT_6_SOL_LUNA,
    "Codex (GPT-6 Luna Evidence)": _GPT_6_SOL_LUNA,
    "Codex (GPT-5.6 Sol Evidence)": _GPT_5_6,
    "Codex (GPT-5.6 Terra Evidence)": _GPT_5_6,
    "Codex (GPT-5.6 Luna Evidence)": _GPT_5_6,
    "Codex (GPT-5.5)": _GPT_5_5,
    "Codex (GPT-5.5 Evidence)": _GPT_5_5,
    "OpenAI GPT-6 Astra": external(
        "https://openai.com/index/gpt-6-astra/",
        "GPT-6 Astra: A new generation of intelligence",
        "2026-09-03",
    ),
    "OpenAI GPT-5.4 Nano": external(
        "https://openai.com/index/introducing-gpt-5-4-mini-and-nano/",
        "Introducing GPT-5.4 mini and nano",
        "2026-03-17",
    ),
    "Google Gemini 3.8 Flash": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/",
        "Introducing Gemini 3.8 Flash and 3.8 Flash Cyber",
        "2026-09-02",
    ),
    "Google Gemini 3.5 Flash": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/",
        "Gemini 3.5: frontier intelligence with action",
        "2026-05-19",
    ),
    "DeepSeek V4.1 Flash": arxiv("2609.19969"),
    "GLM-5.3 Flash": external(
        "https://z.ai/blog/glm-5.3-flash",
        "GLM-5.3-Flash: Frontier Intelligence, Flash Cost",
        "2026-08-26",
        is_open=True,
    ),
    "Kimi K3": arxiv("2607.24653"),
    "Qwen3.8 27B": external(
        "https://huggingface.co/Qwen/Qwen3.8-27B",
        "Qwen3.8-27B",
        "2026-08-05",
        is_open=True,
    ),
    "Qwen3.8 Flash Next": external(
        "https://huggingface.co/Qwen/Qwen3.8-Flash-Next",
        "Qwen3.8-Flash-Next",
        "2026-08-24",
        abstract=(
            "Qwen3.8-Flash-Next is Qwen's open-weight experimental preview of the "
            "architecture that will underpin Qwen4, built for efficient scaling "
            "of parameters and context length."
        ),
        is_open=True,
    ),
    "Qwen3.6 35B": external(
        "https://huggingface.co/collections/Qwen/qwen36",
        "Qwen3.6",
        "2026-04-21",
        is_open=True,
    ),
    "Qwen3.5 35B": _QWEN_3_5,
    "Qwen3.5 9B": _QWEN_3_5,
    "Qwen3.5 4B": _QWEN_3_5,
    "Qwen3.5 2B": _QWEN_3_5,
    "Qwen3.5 0.8B": _QWEN_3_5,
    "Gemma4 26B": _GEMMA_4,
    "Gemma4 12B": _GEMMA_4,
    "Gemma4 E4B": _GEMMA_4,
    "Gemma4 E2B": _GEMMA_4,
    "InternVL3.5 8B": _INTERNVL_3_5,
    "InternVL3.5 14B": _INTERNVL_3_5,
    "MiniCPM-V 4.5": arxiv("2509.18154"),
    "Kimi-VL A3B": arxiv("2504.07491"),
    # The GLM-4.6V model card cites the GLM-4.5V / GLM-4.1V-Thinking report.
    "GLM-4.6V Flash": arxiv("2507.01006"),
    "NuExtract3": external(
        "https://about.nuextract.ai/blog/nuextract-3-release",
        "NuExtract3: The Reasoning Open-Source OCR & Structured Extraction LLM",
        "2026-05-12",
        is_open=True,
    ),
    "NuExtract 2.0 8B": external(
        "https://huggingface.co/numind/NuExtract-2.0-8B",
        "NuExtract 2.0 8B",
        "2025-05-06",
        abstract=(
            "NuExtract 2.0 is NuMind's family of open-weight multimodal, "
            "multilingual models for structured information extraction, built "
            "on the Qwen-VL family."
        ),
        is_open=True,
    ),
    "Lift Datalab 9B": external(
        "https://huggingface.co/datalab-to/lift",
        "lift",
        "2026-06-19",
        abstract=(
            "lift is Datalab's open-weight structured extraction model that "
            "returns schema-valid JSON from PDFs and images using "
            "schema-constrained decoding."
        ),
        is_open=True,
    ),
}

# Extraction products without an introducing paper or official model release
# page. They are reviewed exclusions, not unreviewed rows.
EXCLUDED_PROVIDERS: frozenset[str] = frozenset(
    {
        "Pulse (Effort)",
        "Pulse (Non-effort)",
        "Reducto Deep Extract",
        "Reducto Extract",
        "Reducto Extract (v4)",
        "Extend Extract",
        "Extend (Max Context)",
        "Datalab (Accurate + Balanced)",
    }
)


@dataclass(frozen=True)
class ExtractBenchEntry:
    provider: str
    category: str
    value_f1: float
    grounding: dict[str, float]
    cost_per_page_usd: float | None

    @property
    def metrics(self) -> dict[str, float]:
        return {PRIMARY_METRIC_NAME: self.value_f1, **self.grounding}


@dataclass
class ExtractBenchDiscovery:
    papers: dict[str, int] = field(default_factory=dict)
    indexed_papers: list[str] = field(default_factory=list)
    would_index: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": len(self.papers),
            "indexed_papers": list(self.indexed_papers),
            "would_index": list(self.would_index),
        }


@dataclass
class ExtractBenchSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    excluded: int = 0
    unreviewed: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _score(value: str, *, field_name: str, provider: str) -> float:
    try:
        score = float(value.strip())
    except ValueError as exc:
        raise ValueError(
            f"ExtractBench {field_name} is invalid for {provider!r}"
        ) from exc
    if not isfinite(score) or not 0 <= score <= 100:
        raise ValueError(f"ExtractBench {field_name} is outside 0-100 for {provider!r}")
    return score


def _cost(value: str, *, provider: str) -> float | None:
    if not value.strip():
        return None
    try:
        cost = float(value.strip())
    except ValueError as exc:
        raise ValueError(f"ExtractBench cost is invalid for {provider!r}") from exc
    if not isfinite(cost) or cost < 0:
        raise ValueError(f"ExtractBench cost is negative for {provider!r}")
    return cost


def _grounding(raw: dict[str, str], *, provider: str) -> dict[str, float]:
    """Return grounding scores, or none for systems that emit no evidence.

    Upstream writes 0.00 for both grounding columns when a system returns no
    evidence at all; publishing those zeros would rank non-participants last.
    """
    scores = {
        name: _score(raw.get(column) or "", field_name=name, provider=provider)
        for name, column in GROUNDING_METRICS
    }
    return scores if any(scores.values()) else {}


def parse_extractbench_leaderboard(csv_text: str) -> list[ExtractBenchEntry]:
    """Validate the published leaderboard CSV before it can affect rows."""
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise TypeError("ExtractBench response must be non-empty CSV text")
    reader = csv.DictReader(StringIO(csv_text))
    columns = set(reader.fieldnames or ())
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise ValueError(f"ExtractBench CSV is missing columns: {missing!r}")

    entries: list[ExtractBenchEntry] = []
    providers: set[str] = set()
    for raw in reader:
        provider = (raw.get("Provider") or "").strip()
        if not provider or len(provider) > 255 or ";" in provider:
            raise ValueError(f"ExtractBench provider label is invalid: {provider!r}")
        if provider in providers:
            raise ValueError(f"ExtractBench CSV repeats provider {provider!r}")
        providers.add(provider)
        category = (raw.get("Category") or "").strip()
        if not category:
            raise ValueError(f"ExtractBench category is missing for {provider!r}")
        entries.append(
            ExtractBenchEntry(
                provider=provider,
                category=category,
                value_f1=_score(
                    raw.get("Overall") or "", field_name="overall", provider=provider
                ),
                grounding=_grounding(raw, provider=provider),
                cost_per_page_usd=_cost(
                    raw.get("Cost_Per_Page") or "", provider=provider
                ),
            )
        )

    if not MIN_EXPECTED_ENTRIES <= len(entries) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"ExtractBench returned {len(entries)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )
    return entries


def fetch_extractbench_leaderboard(
    client: httpx.Client | None = None,
) -> list[ExtractBenchEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-extractbench-sync/1.0"},
    )
    try:
        response = active_client.get(EXTRACTBENCH_CSV_URL)
        response.raise_for_status()
        return parse_extractbench_leaderboard(response.text)
    finally:
        if owned_client:
            active_client.close()


def _managed_provider(row: Evaluation) -> str | None:
    methodology = row.methodology or ""
    if not methodology.startswith(MANAGED_METHODOLOGY_PREFIX):
        return None
    marker = " provider="
    start = methodology.find(marker)
    if start == -1:
        return None
    return methodology[start + len(marker) :].split(";", 1)[0]


def _methodology(entry: ExtractBenchEntry) -> str:
    cost = (
        f"${entry.cost_per_page_usd:g}/page"
        if entry.cost_per_page_usd is not None
        else "cost not published"
    )
    grounding = (
        "grounding F1 scored on documents with verified box ground truth"
        if entry.grounding
        else "no grounding evidence returned"
    )
    return (
        f"{MANAGED_METHODOLOGY_PREFIX} provider={entry.provider}; "
        f"category={entry.category}; unified value F1 is the unweighted "
        f"document mean from the official leaderboard.csv; {grounding}; {cost}."
    )


class ExtractBenchSyncService:
    """Replace only evaluation rows owned by the ExtractBench live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metric_ids = {
            metric.name: metric.id
            for metric in self.db.query(Metric)
            .filter(Metric.name.in_(METRIC_NAMES))
            .all()
        }
        if task is None or dataset is None:
            raise RuntimeError("ExtractBench task or benchmark is not configured")
        if set(metric_ids) != set(METRIC_NAMES):
            raise RuntimeError("ExtractBench metrics are not configured")
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
                raise RuntimeError("ExtractBench metrics are not linked to the task")
        return task, dataset

    def sync(
        self,
        entries: list[ExtractBenchEntry],
        *,
        discovery: ExtractBenchDiscovery,
        commit: bool = True,
    ) -> ExtractBenchSyncStats:
        if not entries:
            raise ValueError(
                "Refusing to synchronize an empty ExtractBench leaderboard"
            )
        stats = ExtractBenchSyncStats(fetched=len(entries))
        try:
            task, dataset = self._leaderboard_identity()
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
                provider: row
                for row in managed_rows
                if (provider := _managed_provider(row)) is not None
            }
            linked_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            reviewed: list[ExtractBenchEntry] = []
            for entry in entries:
                if entry.provider in MODEL_PAPER_IDENTITIES:
                    reviewed.append(entry)
                elif entry.provider in EXCLUDED_PROVIDERS:
                    stats.excluded += 1
                else:
                    stats.unreviewed.append(entry.provider)
            if len(reviewed) < MIN_REVIEWED_ENTRIES:
                raise RuntimeError(
                    f"ExtractBench has only {len(reviewed)} reviewed rows; refusing "
                    "to replace the managed leaderboard"
                )

            now = datetime.now(UTC)
            published: set[str] = set()
            for entry in reviewed:
                identity = MODEL_PAPER_IDENTITIES[entry.provider]
                paper_id = discovery.papers.get(identity.key)
                if paper_id is None:
                    if commit:
                        raise RuntimeError(
                            f"No reviewed paper resolved for {entry.provider!r}"
                        )
                    stats.missing_papers.append(entry.provider)
                    continue
                row = managed.get(entry.provider)
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id, task_id=task.id, dataset_id=dataset.id
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                row.paper_id = paper_id
                row.model_name = entry.provider
                row.harness = None
                row.methodology = _methodology(entry)
                row.metrics = entry.metrics
                row.uses_additional_data = False
                row.is_open = identity.is_open
                row.best_metric = PRIMARY_METRIC_NAME
                row.evaluated_on = now.date()
                row.external_source_url = EXTRACTBENCH_SOURCE_URL
                row.source_url = EXTRACTBENCH_SOURCE_URL
                row.external = True
                row.hf_model_url = None
                row.updated_at = now
                if paper_id not in linked_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                    )
                    linked_paper_ids.add(paper_id)
                published.add(entry.provider)
                stats.matched += 1

            for provider, row in managed.items():
                if provider not in published:
                    self.db.delete(row)
                    stats.deleted += 1
            self.db.flush()
            ranking = EvaluationService(self.db)
            for metric_name in METRIC_NAMES:
                ranking.recalculate_ranks(
                    task.id, dataset.id, metric_name=metric_name, commit=False
                )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise


class ExtractBenchPaperDiscoveryService:
    """Resolve every reviewed identity to a local paper, importing when missing."""

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

    def _find(self, identity: PaperIdentity) -> Paper | None:
        query = self.db.query(Paper).filter(Paper.is_latest_version)
        if identity.arxiv_id:
            query = query.filter(Paper.arxiv_id == identity.arxiv_id)
        else:
            query = query.filter(
                Paper.source == "external", Paper.source_url == identity.source_url
            )
        return query.order_by(Paper.id.desc()).first()

    async def discover(self, *, persist: bool = True) -> ExtractBenchDiscovery:
        result = ExtractBenchDiscovery()
        identities = {
            identity.key: identity for identity in MODEL_PAPER_IDENTITIES.values()
        }
        for key, identity in identities.items():
            paper = self._find(identity)
            if paper is None and not persist:
                result.would_index.append(key)
                continue
            if paper is None and identity.arxiv_id:
                paper, created = await self.ingestion_service.get_or_import_arxiv_paper(
                    identity.arxiv_id
                )
                if created:
                    result.indexed_papers.append(key)
            elif paper is None:
                ingestion = self.external_service.add_external_resource(
                    ExternalResourceInput(
                        source_url=identity.source_url or "",
                        title=identity.title or key,
                        abstract=identity.abstract,
                        date_published=identity.date_published,
                    )
                )
                paper = (
                    self.db.query(Paper).filter(Paper.id == ingestion.paper.id).one()
                )
                result.indexed_papers.append(key)
            result.papers[key] = paper.id
        return result


async def discover_extractbench_papers(
    db: Session, *, persist: bool = True
) -> ExtractBenchDiscovery:
    return await ExtractBenchPaperDiscoveryService(db).discover(persist=persist)


def run_discovery(db: Session, *, persist: bool = True) -> ExtractBenchDiscovery:
    return asyncio.run(discover_extractbench_papers(db, persist=persist))
