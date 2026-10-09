"""Synchronize LlamaIndex's living ParseBench document-parsing leaderboard."""

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

# The README top-10 table and parsebench.ai are both rendered from this CSV.
PARSEBENCH_CSV_URL = (
    "https://raw.githubusercontent.com/run-llama/parsebench/main/leaderboard.csv"
)
PARSEBENCH_SOURCE_URL = "https://parsebench.ai/"
TASK_SLUG = "ocr"
DATASET_SLUG = "parsebench"
PRIMARY_METRIC_NAME = "Overall (ParseBench)"
DIMENSION_METRICS = (
    ("Tables", "Tables"),
    ("Charts", "Charts"),
    ("Content Faithfulness", "Content_Faithfulness"),
    ("Semantic Formatting", "Semantic_Formatting"),
    ("Visual Grounding", "Visual_Grounding"),
)
METRIC_NAMES = (PRIMARY_METRIC_NAME, *(name for name, _ in DIMENSION_METRICS))
REQUIRED_COLUMNS = frozenset(
    {
        "Provider",
        "Category",
        "Overall",
        "Cost_Per_Page",
        "HF_Model_ID",
        *(column for _, column in DIMENSION_METRICS),
    }
)
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code ParseBench live sync."
MIN_EXPECTED_ENTRIES = 40
MAX_EXPECTED_ENTRIES = 400
# Refuse to replace the managed leaderboard when the reviewed subset collapses.
MIN_REVIEWED_ENTRIES = 30


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


_FABLE_5_1 = external(
    "https://www.anthropic.com/claude-fable-and-mythos-5-1",
    "Introducing Claude Fable 5.1 and Claude Mythos 5.1",
    "2026-09-01",
)
_FABLE_5 = external(
    "https://www.anthropic.com/news/claude-fable-5-mythos-5",
    "Claude Fable 5 and Claude Mythos 5",
    "2026-06-09",
)
_HAIKU_4_5 = external(
    "https://www.anthropic.com/claude/haiku", "Claude Haiku 4.5", "2025-10-15"
)
_GPT_5_5 = external(
    "https://openai.com/index/introducing-gpt-5-5/", "Introducing GPT-5.5", "2026-04-23"
)
_GPT_5_6 = external(
    "https://openai.com/index/gpt-5-6/",
    "GPT-5.6: Frontier intelligence that scales with your ambition",
    "2026-07-09",
)
_GPT_5_MINI = external(
    "https://openai.com/index/introducing-gpt-5/", "Introducing GPT-5", "2025-08-07"
)
_GEMINI_3_FLASH = external(
    "https://blog.google/products-and-platforms/products/gemini/gemini-3-flash/",
    "Introducing Gemini 3 Flash",
    "2025-12-17",
    abstract=(
        "Google's Gemini 3 Flash release brings frontier-level multimodal "
        "reasoning to the Flash tier with configurable thinking levels."
    ),
)
_GEMINI_3_5 = external(
    "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/",
    "Gemini 3.5: frontier intelligence with action",
    "2026-05-19",
)
_GEMINI_3_6_FLASH = external(
    "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
    "Introducing Gemini 3.6 Flash, 3.5 Flash-Lite, and 3.5 Flash Cyber",
    "2026-07-21",
)
_GEMINI_3_8_FLASH = external(
    "https://blog.google/innovation-and-ai/models-and-research/gemini-models/3-8-flash-and-3-8-flash-cyber/",
    "Introducing Gemini 3.8 Flash and 3.8 Flash Cyber",
    "2026-09-02",
)
_MISTRAL_OCR_4 = external(
    "https://mistral.ai/news/ocr-4/", "Mistral OCR 4", "2026-06-23"
)
_QWEN_3_8_27B = external(
    "https://huggingface.co/Qwen/Qwen3.8-27B", "Qwen3.8-27B", "2026-08-05", is_open=True
)
_QWEN_3_5 = external(
    "https://qwen.ai/blog?id=qwen3.5",
    "Qwen3.5: Towards Native Multimodal Agents",
    "2026-02-16",
    is_open=True,
)
_INFINITY_PARSER2 = arxiv("2607.07836")
_GEMMA_4 = arxiv("2607.02770")
_DEEPSEEK_V4_1_FLASH = arxiv("2609.19969")
# The ParseBench paper is LlamaIndex's own report on its LlamaParse pipelines.
_LLAMAPARSE = arxiv("2604.08538", is_open=False)

_GPT_6_1_SOL = external(
    "https://openai.com/index/introducing-gpt-6-1-sol/",
    "Introducing GPT-6.1 Sol",
    "2026-09-29",
)

_GEMINI_3_7_FLASH = external(
    "https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-3-7-flash/",
    "Introducing Gemini 3.7 Flash",
    "2026-08-13",
)

_OPUS_5_5 = external(
    "https://www.anthropic.com/claude-opus-5-5",
    "Introducing Claude Opus 5.5",
    "2026-09-22",
)

_SONNET_5_5 = external(
    "https://www.anthropic.com/claude-sonnet-5-5",
    "Introducing Claude Sonnet 5.5",
    "2026-09-28",
)

_HAIKU_5_5 = external(
    "https://www.anthropic.com/claude-haiku-5-5",
    "Introducing Claude Haiku 5.5",
    "2026-10-07",
)

_GPT_6_ASTRA = external(
    "https://openai.com/index/gpt-6-astra/",
    "GPT-6 Astra: A new generation of intelligence",
    "2026-09-03",
)

_GPT_6_SOL_LUNA = external(
    "https://openai.com/index/introducing-gpt-6-sol-and-luna/",
    "Introducing GPT-6 Sol and Luna",
    "2026-09-22",
)

# Exact upstream `Provider` labels are the trust boundary between a leaderboard
# row and its reviewed introducing paper or official release page. Rows whose
# label is not reviewed here stay unpublished and are reported by the job.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "HPD-Parsing": arxiv("2607.18839"),
    "HunyuanOCR 1.5": arxiv("2607.04884"),
    "TeleOCR": arxiv("2608.12898"),
    "OvisOCR2": arxiv("2607.13639"),
    "WeVisDoc-2B": arxiv("2609.20423"),
    "WeVisDoc-4B": arxiv("2609.20423"),
    "OpenAI GPT-6.1 Sol (Reasoning Low)": _GPT_6_1_SOL,
    "Google Gemini 3.7 Flash (Thinking High)": _GEMINI_3_7_FLASH,
    "Google Gemini 3.7 Flash (Thinking Medium)": _GEMINI_3_7_FLASH,
    "Google Gemini 3.7 Flash (Thinking Low)": _GEMINI_3_7_FLASH,
    "Anthropic Opus 5.5 (Effort High)": _OPUS_5_5,
    "Anthropic Opus 5.5": _OPUS_5_5,
    "Anthropic Opus 5.5 (Effort Low)": _OPUS_5_5,
    "Anthropic Sonnet 5.5": _SONNET_5_5,
    "Anthropic Haiku 5.5": _HAIKU_5_5,
    "OpenAI GPT-6 Astra (Reasoning Low)": _GPT_6_ASTRA,
    "OpenAI GPT-6 Sol (Reasoning High)": _GPT_6_SOL_LUNA,
    "OpenAI GPT-6 Sol (Reasoning Medium)": _GPT_6_SOL_LUNA,
    "OpenAI GPT-6 Sol (Reasoning None)": _GPT_6_SOL_LUNA,
    "OpenAI GPT-6 Luna (Reasoning Max)": _GPT_6_SOL_LUNA,
    "OpenAI GPT-6 Luna (Reasoning XHigh)": _GPT_6_SOL_LUNA,
    "OpenAI GPT-6 Luna (Reasoning High)": _GPT_6_SOL_LUNA,
    "OpenAI GPT-6 Luna (Reasoning Medium)": _GPT_6_SOL_LUNA,
    "OpenAI GPT-6 Luna (Reasoning Low)": _GPT_6_SOL_LUNA,
    "OpenAI GPT-6 Luna (Reasoning None)": _GPT_6_SOL_LUNA,
    "Google Gemini 3 Flash (Thinking Medium)": _GEMINI_3_FLASH,
    "Google Gemini 3.5 Flash (Thinking High)": _GEMINI_3_5,
    "Google Gemini 3.6 Flash (Thinking High)": _GEMINI_3_6_FLASH,
    "Google Gemini 3.8 Flash (Thinking Medium)": _GEMINI_3_8_FLASH,
    "Google Gemini 3.1 Pro (Thinking Low)": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-pro/",
        "Gemini 3.1 Pro: A smarter model for your most complex tasks",
        "2026-02-19",
        is_open=False,
    ),
    "Google Gemini 3.1 Flash Lite (Thinking Medium)": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-flash-lite/",
        "Gemini 3.1 Flash-Lite: Built for intelligence at scale",
        "2026-03-03",
        is_open=False,
    ),
    "Google Gemini 3.1 Flash Lite (Thinking High)": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-flash-lite/",
        "Gemini 3.1 Flash-Lite: Built for intelligence at scale",
        "2026-03-03",
        is_open=False,
    ),
    "Google Gemini 3.5 Flash Lite (Thinking High)": _GEMINI_3_6_FLASH,
    "Google Gemini 3.5 Flash Lite (Thinking Medium)": _GEMINI_3_6_FLASH,
    "OpenAI GPT-5.6 Terra (Reasoning Medium)": _GPT_5_6,
    "OpenAI GPT-5.6 Terra (Reasoning Low)": _GPT_5_6,
    "OpenAI GPT-5.6 Sol (Reasoning High)": _GPT_5_6,
    "OpenAI GPT-5.6 Luna (Reasoning Max)": _GPT_5_6,
    "OpenAI GPT-5.6 Luna (Reasoning XHigh)": _GPT_5_6,
    "OpenAI GPT-5.6 Luna (Reasoning High)": _GPT_5_6,
    "OpenAI GPT-5.6 Luna (Reasoning Medium)": _GPT_5_6,
    "OpenAI GPT-5.6 Luna (Reasoning Low)": _GPT_5_6,
    "LlamaParse Agentic Plus": _LLAMAPARSE,
    "LlamaParse Agentic": _LLAMAPARSE,
    "LlamaParse Cost Effective": _LLAMAPARSE,
    "Anthropic Fable 5.1": _FABLE_5_1,
    "Anthropic Fable 5": _FABLE_5,
    "Anthropic Opus 4.8": external(
        "https://www.anthropic.com/news/claude-opus-4-8",
        "Claude Opus 4.8",
        "2026-05-28",
    ),
    "Anthropic Opus 4.7": external(
        "https://www.anthropic.com/news/claude-opus-4-7",
        "Claude Opus 4.7",
        "2026-04-16",
    ),
    "Anthropic Opus 4.6": external(
        "https://www.anthropic.com/news/claude-opus-4-6",
        "Claude Opus 4.6",
        "2026-02-05",
    ),
    "Anthropic Sonnet 5": external(
        "https://www.anthropic.com/news/claude-sonnet-5",
        "Claude Sonnet 5",
        "2026-06-30",
    ),
    "Anthropic Haiku 4.5 (Thinking)": _HAIKU_4_5,
    "Anthropic Haiku 4.5 (Disable Thinking)": _HAIKU_4_5,
    "OpenAI GPT-5.5 (Reasoning Medium)": _GPT_5_5,
    "OpenAI GPT-5.5 (Reasoning None)": _GPT_5_5,
    "OpenAI GPT-5.6 Terra (Reasoning None)": _GPT_5_6,
    "OpenAI GPT-5.6 Sol (Reasoning None)": _GPT_5_6,
    "OpenAI GPT-5.6 Luna (Reasoning None)": _GPT_5_6,
    "OpenAI GPT-5.4 (Reasoning None)": external(
        "https://openai.com/index/introducing-gpt-5-4/",
        "Introducing GPT-5.4",
        "2026-03-05",
    ),
    "OpenAI GPT-5.4 Nano": external(
        "https://openai.com/index/introducing-gpt-5-4-mini-and-nano/",
        "Introducing GPT-5.4 mini and nano",
        "2026-03-17",
    ),
    "OpenAI GPT-5 Mini (Reasoning Medium)": _GPT_5_MINI,
    "OpenAI GPT-5 Mini (Reasoning Minimal)": _GPT_5_MINI,
    "Google Gemini 3 Flash (Thinking High)": _GEMINI_3_FLASH,
    "Google Gemini 3 Flash (Thinking Minimal)": _GEMINI_3_FLASH,
    "Google Gemini 3.1 Pro": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-pro/",
        "Gemini 3.1 Pro: A smarter model for your most complex tasks",
        "2026-02-19",
    ),
    "Google Gemini 3.1 Flash Lite": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-flash-lite/",
        "Gemini 3.1 Flash-Lite: Built for intelligence at scale",
        "2026-03-03",
    ),
    "Google Gemini 3.5 Flash (Thinking Medium)": _GEMINI_3_5,
    "Google Gemini 3.5 Flash (Thinking Minimal)": _GEMINI_3_5,
    "Google Gemini 3.5 Flash Lite": _GEMINI_3_6_FLASH,
    "Google Gemini 3.6 Flash (Thinking Medium)": _GEMINI_3_6_FLASH,
    "Google Gemini 3.6 Flash (Thinking Minimal)": _GEMINI_3_6_FLASH,
    "Google Gemini 3.8 Flash (Thinking High)": _GEMINI_3_8_FLASH,
    "Google Gemini 3.8 Flash (Thinking Low)": _GEMINI_3_8_FLASH,
    "GLM-5.3 Flash": external(
        "https://z.ai/blog/glm-5.3-flash",
        "GLM-5.3-Flash: Frontier Intelligence, Flash Cost",
        "2026-08-26",
        is_open=True,
    ),
    "Amazon Nova 2 Lite": external(
        "https://aws.amazon.com/blogs/aws/introducing-amazon-nova-2-lite-a-fast-cost-effective-reasoning-model/",
        "Introducing Amazon Nova 2 Lite, a fast, cost-effective reasoning model",
        "2025-12-02",
        abstract=(
            "Amazon Nova 2 Lite is a fast, cost-effective reasoning model in "
            "Amazon Bedrock that accepts text, image, video, and document inputs "
            "with configurable thinking budgets."
        ),
    ),
    "Mistral OCR 4 (Annotation)": _MISTRAL_OCR_4,
    "Mistral OCR 4": _MISTRAL_OCR_4,
    "rakedoc-nano": external(
        "https://huggingface.co/cloudraker/rakedoc-nano",
        "rakedoc-nano",
        "2026-08-29",
        abstract=(
            "rakedoc-nano is an open-weight document parsing model fine-tuned "
            "from florin-parser-nano that powers the CloudRaker Paperwork API."
        ),
        is_open=True,
    ),
    "florin-parser-nano": external(
        "https://huggingface.co/florin-inc/florin-parser-nano",
        "florin-parser-nano",
        "2026-08-17",
        abstract=(
            "florin-parser-nano is a LoRA fine-tune of KDL-Frontier-Parser-nano "
            "for enterprise document parsing, released with open weights."
        ),
        is_open=True,
    ),
    "KDL-Frontier-Parser-nano": external(
        "https://huggingface.co/KDLAI/KDL-Frontier-Parser-nano",
        "KDL-Frontier-Parser-nano",
        "2026-06-10",
        abstract=(
            "KDL-Frontier-Parser-nano is KoreaDeep's open-weight document parsing "
            "vision-language model for converting PDFs into structured output."
        ),
        is_open=True,
    ),
    "Infinity-Parser2-Pro": _INFINITY_PARSER2,
    "Infinity-Parser2-Flash": _INFINITY_PARSER2,
    "MinerU2.5-Pro-2605-1.2B": arxiv("2604.04771"),
    "MinerU2.5-2509-1.2B": arxiv("2509.22186"),
    "MinerU-Diffusion-V1-0320-2.5B": arxiv("2603.22458"),
    "Qwen 3.8 27B (Thinking)": _QWEN_3_8_27B,
    "Qwen 3.8 27B": _QWEN_3_8_27B,
    "Qwen3.6-35B-A3B": external(
        "https://huggingface.co/collections/Qwen/qwen36",
        "Qwen3.6",
        "2026-04-21",
        is_open=True,
    ),
    "Qwen3.5-4B": _QWEN_3_5,
    "Qwen3.5-9B": _QWEN_3_5,
    "Qwen3.5-2B": _QWEN_3_5,
    "Qwen3.5-0.8B": _QWEN_3_5,
    "Qwen3-VL-8B-Instruct": arxiv("2511.21631"),
    "Chandra-ocr-2": external(
        "https://huggingface.co/datalab-to/chandra-ocr-2",
        "Chandra OCR 2",
        "2026-03-16",
        is_open=True,
    ),
    "Surya OCR 2": external(
        "https://www.datalab.to/blog/surya-2", "Surya OCR 2", "2026-05-27", is_open=True
    ),
    "PaddleOCR-VL-1.6": arxiv("2606.03264"),
    "PaddleOCR-VL-1.5": arxiv("2601.21957"),
    "PaddleOCR-VL": arxiv("2510.14528"),
    "DeepSeek V4.1 Flash (Thinking High)": _DEEPSEEK_V4_1_FLASH,
    "DeepSeek V4.1 Flash (No Thinking)": _DEEPSEEK_V4_1_FLASH,
    "DeepSeek-OCR-2": arxiv("2601.20552"),
    "Gemma-4-31B-it": _GEMMA_4,
    "Gemma-4-26B-A4B-it": _GEMMA_4,
    "Gemma-4-E4B-it": _GEMMA_4,
    "Dots.mocr": arxiv("2603.13032"),
    "Falcon-OCR": arxiv("2603.27365"),
    "Docling-models": arxiv("2408.09869"),
    "Nemotron-3-Nano-Omni-30B-A3B (Thinking)": arxiv("2604.24954"),
    "LightOnOCR-2-1B": arxiv("2601.14251"),
    "Qianfan-OCR": arxiv("2603.13398"),
    "Unlimited-OCR": arxiv("2606.23050"),
    "Jina-OCR-v1": arxiv("2609.03181"),
    "Granite Vision 4.1 4B": external(
        "https://huggingface.co/ibm-granite/granite-vision-4.1-4b",
        "Granite Vision 4.1 4B",
        "2026-04-16",
        abstract=(
            "Granite Vision 4.1 4B is IBM's open-weight enterprise vision-language "
            "model release for document and chart understanding."
        ),
        is_open=True,
    ),
    "GLM-OCR": arxiv("2603.10910"),
}

# Parsing products and PDF libraries without an introducing paper or official
# model release page. They are reviewed exclusions, not unreviewed rows.
EXCLUDED_PROVIDERS: frozenset[str] = frozenset(
    {
        "Pulse Ultra 2",
        "anyformat (Standard)",
        "oi-parser",
        "Extend (2.0)",
        "Extend Light (1.0)",
        "Extend",
        "Reducto (Agentic)",
        "Reducto",
        "Reducto (r-1)",
        "Datalab Accurate",
        "Datalab Balanced",
        "Datalab Fast",
        "Databricks AI Parse",
        "Databricks AI Parse (batch)",
        "Azure Document Intelligence (Layout)",
        "Google Cloud Document AI",
        "AWS Textract",
        "LandingAI",
        "Firecrawl",
        "PyMuPDF4LLM",
        "PyMuPDF (HTML)",
        "PyMuPDF (Text)",
        "pypdf",
        "Warp Ingest",
        "LiteParse (no OCR)",
        "OpenDataLoader",
        "pdf-inspector",
        "MarkItDown",
    }
)


@dataclass(frozen=True)
class ParseBenchEntry:
    provider: str
    category: str
    overall: float
    dimensions: dict[str, float]
    cost_per_page_cents: float | None
    hf_model_id: str | None

    @property
    def metrics(self) -> dict[str, float]:
        return {PRIMARY_METRIC_NAME: self.overall, **self.dimensions}


@dataclass
class ParseBenchDiscovery:
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
class ParseBenchSyncStats:
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
            f"ParseBench {field_name} is invalid for {provider!r}"
        ) from exc
    if not isfinite(score) or not 0 <= score <= 100:
        raise ValueError(f"ParseBench {field_name} is outside 0-100 for {provider!r}")
    return score


def _cost(value: str, *, provider: str) -> float | None:
    if not value.strip():
        return None
    try:
        cost = float(value.strip())
    except ValueError as exc:
        raise ValueError(f"ParseBench cost is invalid for {provider!r}") from exc
    if not isfinite(cost) or cost < 0:
        raise ValueError(f"ParseBench cost is negative for {provider!r}")
    return cost


def parse_parsebench_leaderboard(csv_text: str) -> list[ParseBenchEntry]:
    """Validate the published leaderboard CSV before it can affect rows."""
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise TypeError("ParseBench response must be non-empty CSV text")
    reader = csv.DictReader(StringIO(csv_text))
    columns = set(reader.fieldnames or ())
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise ValueError(f"ParseBench CSV is missing columns: {missing!r}")

    entries: list[ParseBenchEntry] = []
    providers: set[str] = set()
    for raw in reader:
        provider = (raw.get("Provider") or "").strip()
        if not provider or len(provider) > 255 or ";" in provider:
            raise ValueError(f"ParseBench provider label is invalid: {provider!r}")
        if provider in providers:
            raise ValueError(f"ParseBench CSV repeats provider {provider!r}")
        providers.add(provider)
        category = (raw.get("Category") or "").strip()
        if not category:
            raise ValueError(f"ParseBench category is missing for {provider!r}")
        hf_model_id = (raw.get("HF_Model_ID") or "").strip() or None
        if hf_model_id is not None and (
            hf_model_id.count("/") != 1 or any(c.isspace() for c in hf_model_id)
        ):
            raise ValueError(f"ParseBench HF model id is invalid for {provider!r}")
        entries.append(
            ParseBenchEntry(
                provider=provider,
                category=category,
                overall=_score(
                    raw.get("Overall") or "", field_name="overall", provider=provider
                ),
                dimensions={
                    name: _score(
                        raw.get(column) or "", field_name=name, provider=provider
                    )
                    for name, column in DIMENSION_METRICS
                },
                cost_per_page_cents=_cost(
                    raw.get("Cost_Per_Page") or "", provider=provider
                ),
                hf_model_id=hf_model_id,
            )
        )

    if not MIN_EXPECTED_ENTRIES <= len(entries) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"ParseBench returned {len(entries)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )
    return entries


def fetch_parsebench_leaderboard(
    client: httpx.Client | None = None,
) -> list[ParseBenchEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-parsebench-sync/1.0"},
    )
    try:
        response = active_client.get(PARSEBENCH_CSV_URL)
        response.raise_for_status()
        return parse_parsebench_leaderboard(response.text)
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


def _methodology(entry: ParseBenchEntry) -> str:
    cost = (
        f"{entry.cost_per_page_cents:g} cents/page"
        if entry.cost_per_page_cents is not None
        else "cost not published"
    )
    return (
        f"{MANAGED_METHODOLOGY_PREFIX} provider={entry.provider}; "
        f"category={entry.category}; overall is the mean of the five "
        f"ParseBench dimension scores from the official leaderboard.csv; {cost}."
    )


class ParseBenchSyncService:
    """Replace only evaluation rows owned by the ParseBench live sync."""

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
            raise RuntimeError("ParseBench task or benchmark is not configured")
        if set(metric_ids) != set(METRIC_NAMES):
            raise RuntimeError("ParseBench metrics are not configured")
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
                raise RuntimeError("ParseBench metrics are not linked to the task")
        return task, dataset

    def sync(
        self,
        entries: list[ParseBenchEntry],
        *,
        discovery: ParseBenchDiscovery,
        commit: bool = True,
    ) -> ParseBenchSyncStats:
        if not entries:
            raise ValueError("Refusing to synchronize an empty ParseBench leaderboard")
        stats = ParseBenchSyncStats(fetched=len(entries))
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
            reviewed: list[ParseBenchEntry] = []
            for entry in entries:
                if entry.provider in MODEL_PAPER_IDENTITIES:
                    reviewed.append(entry)
                elif entry.provider in EXCLUDED_PROVIDERS:
                    stats.excluded += 1
                else:
                    stats.unreviewed.append(entry.provider)
            if len(reviewed) < MIN_REVIEWED_ENTRIES:
                raise RuntimeError(
                    f"ParseBench has only {len(reviewed)} reviewed rows; refusing "
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
                row.external_source_url = PARSEBENCH_SOURCE_URL
                row.source_url = PARSEBENCH_SOURCE_URL
                row.external = True
                row.hf_model_url = (
                    f"https://huggingface.co/{entry.hf_model_id}"
                    if entry.hf_model_id
                    else None
                )
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
            EvaluationService(self.db).recalculate_ranks(
                task.id, dataset.id, metric_name=PRIMARY_METRIC_NAME, commit=False
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise


class ParseBenchPaperDiscoveryService:
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

    async def discover(self, *, persist: bool = True) -> ParseBenchDiscovery:
        result = ParseBenchDiscovery()
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


async def discover_parsebench_papers(
    db: Session, *, persist: bool = True
) -> ParseBenchDiscovery:
    return await ParseBenchPaperDiscoveryService(db).discover(persist=persist)


def run_discovery(db: Session, *, persist: bool = True) -> ParseBenchDiscovery:
    return asyncio.run(discover_parsebench_papers(db, persist=persist))
