"""Synchronize the official Vals AI Finance Agent v2 leaderboard."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix

VALS_FINANCE_AGENT_URL = "https://www.vals.ai/benchmarks/fabv2"
TASK_SLUG = "agents"
DATASET_SLUG = "finance-agent-v2"
METRIC_NAME = "Accuracy"
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("Vals AI Finance Agent v2")
# Only these leading columns are read; Vals relabels the cost/duration columns
# after them (2026-10-26: "Tokens / Test", "Duration / Test").
TABLE_HEADER = ("Rank", "Model", "Accuracy")
MIN_EXPECTED_ROWS = 40
MAX_EXPECTED_ROWS = 400
# Refuse to touch the managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 50


@dataclass(frozen=True)
class ModelIdentity:
    """A reviewed leaderboard model and the paper that introduces it.

    `renamed_from` adopts a hand-imported row stored under an older name
    (only when its score matches), so a correction does not duplicate it.
    """

    model_name: str
    arxiv_id: str | None = None
    source_url: str | None = None
    is_open: bool = False
    hf_model_url: str | None = None
    renamed_from: str | None = None

    def __post_init__(self) -> None:
        if (self.arxiv_id is None) == (self.source_url is None):
            raise ValueError("ModelIdentity requires exactly one paper identity")

    @property
    def paper_key(self) -> str:
        return self.arxiv_id or self.source_url or ""


_MUSE_SPARK_1_3 = "https://research.meta.ai/blog/introducing-muse-spark-1-3"

# Exact Vals model labels are the trust boundary between a leaderboard row and
# its introducing paper. Model names follow the catalog (reviewed on
# 2026-10-14, 2026-10-16 and 2026-10-18), not Vals' spelling. Unreviewed labels are
# reported, never imported.
MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "Gemini 4 Argon": ModelIdentity(
        "Gemini 4 Argon",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/"
        ),
    ),
    "Gemini 3.8 Flash": ModelIdentity(
        "Gemini 3.8 Flash",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/"
        ),
    ),
    "Muse Spark Open": ModelIdentity(
        "Muse Spark Open",
        source_url="https://research.meta.ai/blog/muse-spark-open",
        is_open=True,
        hf_model_url="https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B",
    ),
    "Muse Spark 1.2": ModelIdentity(
        "Muse Spark 1.2",
        source_url=(
            "https://developer.meta.com/ai/resources/blog/build-with-muse-code/"
        ),
    ),
    "Muse Spark 1.3 Max": ModelIdentity(
        "Muse Spark 1.3 Max", source_url=_MUSE_SPARK_1_3, renamed_from="Muse Spark 1.3"
    ),
    "Wonder Full": ModelIdentity(
        "Muse Wonder Full (max)", source_url="https://research.meta.ai/blog/muse-wonder"
    ),
    "Gemini 3.7 Flash": ModelIdentity(
        "Gemini 3.7 Flash",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-3-7-flash/"
        ),
    ),
    "Muse Spark 1.3": ModelIdentity("Muse Spark 1.3", source_url=_MUSE_SPARK_1_3),
    "Claude Fable 5.1": ModelIdentity(
        "Claude Fable 5.1",
        source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
    ),
    "Claude Opus 5": ModelIdentity(
        "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
    ),
    "Claude Opus 5.5": ModelIdentity(
        "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
    ),
    "Claude Sonnet 5.5": ModelIdentity(
        "Claude Sonnet 5.5", source_url="https://www.anthropic.com/claude-sonnet-5-5"
    ),
    "Gemini 3.5 Flash": ModelIdentity(
        "Gemini 3.5 Flash",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/"
        ),
    ),
    "GLM 5.3 Flash": ModelIdentity(
        "GLM-5.3-Flash",
        source_url="https://z.ai/blog/glm-5.3-flash",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3-Flash",
    ),
    "MiMo V2.6 Pro": ModelIdentity(
        "MiMo-V2.6-Pro", arxiv_id="2610.11959", is_open=True
    ),
    "Muse Spark 1.1": ModelIdentity(
        "Muse Spark 1.1",
        source_url=("https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/"),
    ),
    "Wonder": ModelIdentity(
        "Muse Wonder (max)", source_url="https://research.meta.ai/blog/muse-wonder"
    ),
    "Claude Fable 5": ModelIdentity(
        "Claude Fable 5",
        source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
    ),
    "Gemini 3.6 Flash": ModelIdentity(
        "Gemini 3.6 Flash",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/"
        ),
    ),
    "MiMo V2.6 Flash": ModelIdentity(
        "MiMo-V2.6-Flash", arxiv_id="2610.11959", is_open=True
    ),
    "GLM 5.3": ModelIdentity(
        "GLM-5.3",
        source_url="https://z.ai/blog/glm-5.3",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3",
    ),
    "Hy4 Preview": ModelIdentity(
        "Hy4 preview",
        source_url=(
            "https://github.com/Tencent-Hunyuan/Hy4-preview/blob/1296fab2674cb5a645ccfe53e9a8dc225dbe69f2/README.md"
        ),
        is_open=True,
        hf_model_url="https://huggingface.co/tencent/Hy4-preview",
    ),
    "GPT-5.6 Luna": ModelIdentity(
        "GPT-5.6 Luna", source_url="https://openai.com/index/gpt-5-6/"
    ),
    "Mistral Large 4": ModelIdentity(
        "Mistral Large 4 Preview", source_url="https://mistral.ai/news/mistral-large-4/"
    ),
    "GPT-5.6 Terra": ModelIdentity(
        "GPT-5.6 Terra", source_url="https://openai.com/index/gpt-5-6/"
    ),
    "Claude Haiku 5.5": ModelIdentity(
        "Claude Haiku 5.5", source_url="https://www.anthropic.com/claude-haiku-5-5"
    ),
    "Claude Opus 4.8": ModelIdentity(
        "Claude Opus 4.8", source_url="https://www.anthropic.com/news/claude-opus-4-8"
    ),
    "Claude Sonnet 5": ModelIdentity(
        "Claude Sonnet 5", source_url="https://www.anthropic.com/news/claude-sonnet-5"
    ),
    "GPT-5.6 Sol": ModelIdentity(
        "GPT-5.6 Sol", source_url="https://openai.com/index/gpt-5-6/"
    ),
    "Grok 4.6": ModelIdentity("Grok 4.6", source_url="https://x.ai/news/grok-4-6"),
    "GPT-6 Astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "DeepSeek V4.1 Flash": ModelIdentity(
        "DeepSeek-V4.1-Flash",
        arxiv_id="2609.19969",
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash",
    ),
    "Kimi K3": ModelIdentity(
        "Kimi K3",
        arxiv_id="2607.24653",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K3",
    ),
    "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
    "GPT-6.1 Sol": ModelIdentity(
        "GPT-6.1 Sol", source_url="https://openai.com/index/introducing-gpt-6-1-sol/"
    ),
    "GPT 5.5": ModelIdentity(
        "GPT-5.5", source_url="https://openai.com/index/introducing-gpt-5-5/"
    ),
    "Claude Opus 4.7": ModelIdentity(
        "Claude Opus 4.7", source_url="https://www.anthropic.com/news/claude-opus-4-7"
    ),
    "Claude Sonnet 4.6": ModelIdentity(
        "Claude Sonnet 4.6",
        source_url="https://www.anthropic.com/news/claude-sonnet-4-6",
    ),
    "Qwen 3.8 Max": ModelIdentity(
        "Qwen3.8-Max", source_url="https://qwen.ai/blog?id=qwen3.8"
    ),
    "DeepSeek V4 Pro 0813": ModelIdentity(
        "DeepSeek-V4-Pro-0813",
        arxiv_id="2606.19348",
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813",
    ),
    "GPT-6 Luna": ModelIdentity(
        "GPT-6 Luna",
        source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
    ),
    "GLM 5.2": ModelIdentity(
        "GLM-5.2",
        source_url="https://z.ai/blog/glm-5.2",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.2",
    ),
    "DeepSeek V4 Flash 0731": ModelIdentity(
        "DeepSeek-V4-Flash-0731",
        arxiv_id="2606.19348",
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731",
    ),
    "DeepSeek V4.1 Flash 1017": ModelIdentity(
        "DeepSeek-V4.1-Flash-1017",
        arxiv_id="2609.19969",
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017",
    ),
    "GPT-6 Sol": ModelIdentity(
        "GPT-6 Sol",
        source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
    ),
    "Qwen 3.8 27B": ModelIdentity(
        "Qwen3.8-27B",
        source_url="https://huggingface.co/Qwen/Qwen3.8-27B",
        is_open=True,
        hf_model_url="https://huggingface.co/Qwen/Qwen3.8-27B",
    ),
    "Grok 4.5": ModelIdentity("Grok 4.5", source_url="https://x.ai/news/grok-4-5"),
    "MiniMax-M3": ModelIdentity(
        "MiniMax M3",
        source_url="https://www.minimax.io/blog/minimax-m3",
        is_open=True,
        hf_model_url="https://huggingface.co/MiniMaxAI/MiniMax-M3",
    ),
    "Qwen 3.7 Max": ModelIdentity(
        "Qwen3.7-Max", source_url="https://qwen.ai/blog?id=qwen3.7"
    ),
    "Gemini 3.5 Flash Lite": ModelIdentity(
        "Gemini 3.5 Flash-Lite",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/"
        ),
    ),
    "Inkling": ModelIdentity(
        "Inkling",
        source_url="https://thinkingmachines.ai/news/introducing-inkling/",
        is_open=True,
        hf_model_url="https://huggingface.co/thinkingmachines/Inkling",
    ),
    "GPT 5.4 Mini": ModelIdentity(
        "GPT-5.4 mini",
        source_url="https://openai.com/index/introducing-gpt-5-4-mini-and-nano/",
    ),
    "Kimi K2.6": ModelIdentity(
        "Kimi K2.6",
        source_url="https://www.kimi.com/blog/kimi-k2-6",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K2.6",
    ),
    "GLM 5.1": ModelIdentity(
        "GLM-5.1",
        source_url="https://z.ai/blog/glm-5.1",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.1",
    ),
    "DeepSeek V4": ModelIdentity(
        "DeepSeek-V4-Pro",
        arxiv_id="2606.19348",
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro",
    ),
    "Gemini 3.1 Pro Preview (02/26)": ModelIdentity(
        "Gemini 3.1 Pro",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-pro/"
        ),
    ),
    "Gemini 3 Flash (12/25)": ModelIdentity(
        "Gemini 3 Flash",
        source_url=(
            "https://blog.google/products-and-platforms/products/gemini/gemini-3-flash/"
        ),
    ),
    "MiMo V2.5 Pro": ModelIdentity(
        "MiMo-V2.5-Pro",
        source_url="https://huggingface.co/XiaomiMiMo/MiMo-V2.5-Pro",
        is_open=True,
        hf_model_url="https://huggingface.co/XiaomiMiMo/MiMo-V2.5-Pro",
    ),
    "Inkling Small": ModelIdentity(
        "Inkling-Small",
        source_url="https://huggingface.co/thinkingmachines/Inkling-Small",
        is_open=True,
        hf_model_url="https://huggingface.co/thinkingmachines/Inkling-Small",
    ),
    "Qwen 3.7 Plus": ModelIdentity(
        "Qwen3.7-Plus", source_url="https://www.qwencloud.com/models/qwen3.7-plus"
    ),
    "GPT 5.4 Nano": ModelIdentity(
        "GPT-5.4 nano",
        source_url="https://openai.com/index/introducing-gpt-5-4-mini-and-nano/",
    ),
    "Grok 4.3": ModelIdentity(
        "Grok 4.3", source_url="https://docs.x.ai/developers/models/grok-4.3"
    ),
    "Nemotron 3 Ultra": ModelIdentity(
        "Nemotron 3 Ultra",
        arxiv_id="2606.15007",
        is_open=True,
        hf_model_url="https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16",
    ),
    "Kimi K2.5": ModelIdentity(
        "Kimi K2.5",
        arxiv_id="2602.02276",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K2.5",
    ),
    "Mistral Medium 3.5": ModelIdentity(
        "Mistral Medium 3.5",
        source_url="https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
        is_open=True,
    ),
    "Claude Haiku 4.5 (Thinking)": ModelIdentity(
        "Claude Haiku 4.5", source_url="https://www.anthropic.com/claude/haiku"
    ),
    "Gemini 3.1 Flash Lite Preview": ModelIdentity(
        "Gemini 3.1 Flash-Lite",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-flash-lite/"
        ),
    ),
    "MiniMax-M2.7": ModelIdentity(
        "MiniMax-M2.7",
        arxiv_id="2605.26494",
        is_open=True,
        hf_model_url="https://huggingface.co/MiniMaxAI/MiniMax-M2.7",
    ),
    "Laguna M.1": ModelIdentity("Laguna M.1", arxiv_id="2605.27605"),
    "Nemotron 3.5 Lightning": ModelIdentity(
        "NVIDIA Nemotron 3.5 Lightning 30B-A3B",
        source_url=(
            "https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16"
        ),
        is_open=True,
        hf_model_url="https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16",
    ),
    "Laguna XS.2": ModelIdentity(
        "Laguna XS.2",
        arxiv_id="2605.27605",
        is_open=True,
        hf_model_url="https://huggingface.co/poolside/Laguna-XS.2",
    ),
    "Command A+": ModelIdentity(
        "Command A+",
        source_url="https://cohere.com/blog/command-a-plus",
        is_open=True,
        hf_model_url="https://huggingface.co/CohereLabs/command-a-plus-05-2026-bf16",
    ),
    # Models without a catalog paper before 2026-10-16, indexed from their
    # official release pages (papers 123607-123614).
    "Ling 3.0 Flash Fin": ModelIdentity(
        "Ling-3.0-flash-Fin",
        source_url="https://huggingface.co/inclusionAI/Ling-3.0-flash-Fin",
        is_open=True,
        hf_model_url="https://huggingface.co/inclusionAI/Ling-3.0-flash-Fin",
    ),
    "Ember-1": ModelIdentity("Ember-1", source_url="https://fireworks.ai/blog/ember-1"),
    "Step 5 Preview": ModelIdentity(
        "Step-5-Preview",
        source_url="https://huggingface.co/stepfun-ai/Step-5-Preview",
        is_open=True,
        hf_model_url="https://huggingface.co/stepfun-ai/Step-5-Preview",
    ),
    "Qwen 3.6 Plus": ModelIdentity(
        "Qwen3.6-Plus", source_url="https://qwen.ai/blog?id=qwen3.6"
    ),
    "MiMo V2.5": ModelIdentity(
        "MiMo-V2.5",
        source_url="https://mimo.xiaomi.com/mimo-v2-5",
        is_open=True,
        hf_model_url="https://huggingface.co/XiaomiMiMo/MiMo-V2.5",
    ),
    "Ling 3.0 Flash": ModelIdentity(
        "Ling-3.0-flash",
        source_url="https://huggingface.co/inclusionAI/Ling-3.0-flash",
        is_open=True,
        hf_model_url="https://huggingface.co/inclusionAI/Ling-3.0-flash",
    ),
    "Grok 4.20 (Reasoning)": ModelIdentity(
        "Grok 4.20 (Reasoning)",
        source_url="https://docs.x.ai/developers/models/grok-4.20",
    ),
    "Mercury 2.5": ModelIdentity(
        "Mercury 2.5",
        source_url="https://www.inceptionlabs.ai/blog/introducing-mercury-2-5",
    ),
}


@dataclass(frozen=True)
class ValsEntry:
    position: int
    label: str
    accuracy: Decimal
    model_url: str


@dataclass
class ValsSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    changed: int = 0
    adopted: int = 0
    renamed: list[str] = field(default_factory=list)
    unreviewed: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)
    missing_upstream: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _text(node) -> str:
    return " ".join(node.get_text(" ").split())


def parse_vals_finance_agent(html: str) -> list[ValsEntry]:
    """Parse the leaderboard table, failing on any layout change."""
    if not isinstance(html, str) or not html.strip():
        raise TypeError("Vals AI response must be non-empty HTML")
    tables = BeautifulSoup(html, "html.parser").find_all("table")
    if len(tables) != 1:
        raise ValueError(f"Vals AI page has {len(tables)} tables; expected 1")
    rows = tables[0].find_all("tr")
    header = tuple(_text(cell) for cell in rows[0].find_all(["th", "td"]))
    if header[: len(TABLE_HEADER)] != TABLE_HEADER:
        raise ValueError(f"Vals AI table header changed: {header!r}")
    entries: list[ValsEntry] = []
    seen: set[str] = set()
    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) != len(header):
            raise ValueError(f"Vals AI row has {len(cells)} columns")
        position, label, accuracy = (_text(cell) for cell in cells[:3])
        link = cells[1].find("a", href=True)
        if not position.isdigit() or link is None or not label or len(label) > 255:
            raise ValueError(f"Vals AI row is malformed: {label!r}")
        if not accuracy.endswith("%"):
            raise ValueError(f"Vals AI accuracy is not a percentage: {accuracy!r}")
        try:
            value = Decimal(accuracy[:-1])
        except InvalidOperation as exc:
            raise ValueError(f"Vals AI accuracy is invalid: {accuracy!r}") from exc
        if not 0 <= value <= 100:
            raise ValueError(f"Vals AI accuracy is outside 0-100 for {label!r}")
        if label in seen:
            raise ValueError(f"Vals AI lists {label!r} twice")
        seen.add(label)
        entries.append(
            ValsEntry(
                int(position),
                label,
                value,
                urljoin(VALS_FINANCE_AGENT_URL, link["href"]),
            )
        )
    if not MIN_EXPECTED_ROWS <= len(entries) <= MAX_EXPECTED_ROWS:
        raise ValueError(
            f"Vals AI Finance Agent v2 has {len(entries)} rows; expected "
            f"{MIN_EXPECTED_ROWS}-{MAX_EXPECTED_ROWS}"
        )
    return entries


def fetch_vals_finance_agent(client: httpx.Client | None = None) -> list[ValsEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(30, connect=5),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-vals-finance-agent-sync/1.0"},
    )
    try:
        response = active_client.get(VALS_FINANCE_AGENT_URL)
        response.raise_for_status()
        return parse_vals_finance_agent(response.text)
    finally:
        if owned_client:
            active_client.close()


_MANAGED_HEAD = re.compile(
    re.escape(MANAGED_METHODOLOGY_PREFIX)
    + r' Official leaderboard entry "(?P<label>.+?)": (?P<score>[^,]+)% Accuracy, '
    r"listed at (?P<url>\S+)\.(?: (?P<notes>.*))?$",
    re.DOTALL,
)


def _methodology(entry: ValsEntry, notes: str) -> str:
    head = (
        f"{MANAGED_METHODOLOGY_PREFIX} Official leaderboard entry "
        f'"{entry.label}": {entry.accuracy}% Accuracy, listed at '
        f"{VALS_FINANCE_AGENT_URL}."
    )
    return f"{head} {notes}" if notes else head


def _curated_notes(row: Evaluation) -> str:
    """Return the reviewer-written methodology kept beneath the managed head."""
    methodology = (row.methodology or "").strip()
    head = _MANAGED_HEAD.match(methodology)
    if head is not None:
        return head.group("notes") or ""
    return methodology


def _score_matches(stored: Any, published: Decimal) -> bool:
    """A stored value is current when it rounds to the published one."""
    if isinstance(stored, bool) or not isinstance(stored, (int, float)):
        return False
    exponent = published.as_tuple().exponent
    places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    return Decimal(str(stored)).quantize(Decimal(1).scaleb(-places)) == published


class ValsFinanceAgentSyncService:
    """Create and revise reviewed Finance Agent v2 rows; never create papers."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        if task is None or dataset is None:
            raise RuntimeError("Finance Agent v2 task or benchmark is not configured")
        configured = (
            self.db.query(TaskDatasetMetric)
            .join(Metric, Metric.id == TaskDatasetMetric.metric_id)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
                Metric.name == METRIC_NAME,
            )
            .count()
        )
        if configured != 1:
            raise RuntimeError("Finance Agent v2 Accuracy is not linked to the task")
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

    def sync(self, entries: list[ValsEntry], *, commit: bool = True) -> ValsSyncStats:
        selected = [
            (MODEL_IDENTITIES[entry.label], entry)
            for entry in entries
            if entry.label in MODEL_IDENTITIES
        ]
        if len(selected) < MIN_SELECTED_ENTRIES:
            raise RuntimeError(
                f"Finance Agent v2 has only {len(selected)} reviewed rows; "
                "refusing to update the managed leaderboard"
            )
        stats = ValsSyncStats(
            fetched=len(entries),
            unreviewed=[e.label for e in entries if e.label not in MODEL_IDENTITIES],
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
            rows_by_identity: dict[tuple[int, str], Evaluation] = {}
            for row in rows:
                if METRIC_NAME in (row.metrics or {}):
                    rows_by_identity.setdefault((row.paper_id, row.model_name), row)
            # Renames first, so the old name is free for its own identity.
            for identity, entry in selected:
                paper_id = paper_ids.get(identity.paper_key)
                old = rows_by_identity.get((paper_id, identity.renamed_from))
                if (
                    identity.renamed_from is None
                    or old is None
                    or (paper_id, identity.model_name) in rows_by_identity
                    or not _score_matches(old.metrics.get(METRIC_NAME), entry.accuracy)
                ):
                    continue
                old.model_name = identity.model_name
                del rows_by_identity[(paper_id, identity.renamed_from)]
                rows_by_identity[(paper_id, identity.model_name)] = old
                stats.renamed.append(
                    f"{identity.renamed_from} -> {identity.model_name}"
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
                metrics = {METRIC_NAME: float(entry.accuracy)}
                row = rows_by_identity.get((paper_id, identity.model_name))
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=identity.model_name,
                        metrics=metrics,
                        is_open=identity.is_open,
                        hf_model_url=identity.hf_model_url,
                        external_source_url=VALS_FINANCE_AGENT_URL,
                        source_url=VALS_FINANCE_AGENT_URL,
                        external=True,
                        uses_additional_data=False,
                        evaluated_on=now.date(),
                    )
                    self.db.add(row)
                    rows_by_identity[(paper_id, identity.model_name)] = row
                    stats.created += 1
                    notes = ""
                else:
                    # Adopted rows keep their reviewed provenance fields; only
                    # the leaderboard-owned score and methodology head change.
                    notes = _curated_notes(row)
                    managed = _MANAGED_HEAD.match((row.methodology or "").strip())
                    current = _score_matches(
                        (row.metrics or {}).get(METRIC_NAME), entry.accuracy
                    )
                    if managed is None:
                        stats.adopted += 1
                    revised_head = row.methodology != _methodology(entry, notes)
                    if not current or (managed is not None and revised_head):
                        stats.changed += 1
                    if not current:
                        row.metrics = {**(row.metrics or {}), **metrics}
                row.methodology = _methodology(entry, notes)
                row.best_metric = METRIC_NAME
                row.updated_at = now
                if paper_id not in linked_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                    )
                    linked_paper_ids.add(paper_id)
                published.add(id(row))
                stats.matched += 1

            stats.missing_upstream = sorted(
                row.model_name
                for row in rows
                if id(row) not in published
                and _MANAGED_HEAD.match((row.methodology or "").strip())
            )
            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id, dataset.id, metric_name=METRIC_NAME, commit=False
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
