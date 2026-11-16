"""Synchronize LlamaIndex's living ParseBench and ParseBench-2 leaderboards.

Both boards are CSVs in the run-llama/parsebench repository. Each
``ParseBenchBoard`` names its CSV, benchmark, metrics and reviewed identity map;
the parser, paper discovery and sync are shared.
"""

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
    Evaluation,
    Paper,
    PaperTask,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.leaderboard_model_matching_service import (
    LeaderboardModel,
    LeaderboardModelMatcher,
    vendor_label_model,
)
from backend.services.leaderboard_sync_catalog import (
    resolve_leaderboard,
)
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix
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
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("ParseBench")
MIN_EXPECTED_ENTRIES = 40
MAX_EXPECTED_ENTRIES = 400
# Refuse to replace the managed leaderboard when the reviewed subset collapses.
MIN_REVIEWED_ENTRIES = 30
# Categories whose rows are single models ("VLM - Proprietary", "VLM - Open
# Weight"); parsing products and PDF libraries need a reviewed identity.
MODEL_CATEGORY_PREFIX = "VLM"

# ParseBench-2 is a separate benchmark with its own CSV, six dimensions and
# provider labels ("Claude Opus 5.5", not "Anthropic Opus 5.5").
PARSEBENCH_2_CSV_URL = (
    "https://raw.githubusercontent.com/run-llama/parsebench/main/leaderboard-v2.csv"
)
PARSEBENCH_2_DATASET_SLUG = "parsebench-2"
PARSEBENCH_2_PRIMARY_METRIC_NAME = "Overall (ParseBench-2)"
PARSEBENCH_2_DIMENSION_METRICS = (
    ("Text (ParseBench-2)", "Text"),
    ("Formatting (ParseBench-2)", "Formatting"),
    ("Tables (ParseBench-2)", "Tables"),
    ("Charts (ParseBench-2)", "Charts"),
    ("Visual Grounding (ParseBench-2)", "Visual_Grounding"),
    ("Forms (ParseBench-2)", "Forms"),
)


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

_LIGHTONOCR_3 = external(
    "https://huggingface.co/blog/lightonai/lightonocr-3",
    "LightOnOCR-3: High-Performance OCR and Layout Extraction in One Model",
    "2026-10-08",
    is_open=True,
)

_GPT_6_1_TERRA = external(
    "https://openai.com/index/introducing-gpt-6-1-terra",
    "Introducing GPT-6.1 Terra",
    "2026-10-26",
)

_GPT_6_SOL_LUNA = external(
    "https://openai.com/index/introducing-gpt-6-sol-and-luna/",
    "Introducing GPT-6 Sol and Luna",
    "2026-09-22",
)

_GEMINI_3_1_FLASH_LITE = external(
    "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-flash-lite/",
    "Gemini 3.1 Flash-Lite: Built for intelligence at scale",
    "2026-03-03",
)

_NEMOTRON_3_5_PARSE = external(
    "https://huggingface.co/nvidia/Nemotron-3.5-Parse",
    "Nemotron 3.5 Parse",
    "2026-10-17",
    is_open=True,
)

_MINICPM_OCR_1 = external(
    "https://huggingface.co/openbmb/MiniCPM-OCR-1.0",
    "MiniCPM-OCR 1.0",
    "2026-10-21",
    is_open=True,
)

_CHANDRA_OCR_2 = external(
    "https://huggingface.co/datalab-to/chandra-ocr-2",
    "Chandra OCR 2",
    "2026-03-16",
    is_open=True,
)

_SURYA_OCR_2 = external(
    "https://www.datalab.to/blog/surya-2", "Surya OCR 2", "2026-05-27", is_open=True
)

_KDL_NANO = external(
    "https://huggingface.co/KDLAI/KDL-Frontier-Parser-nano",
    "KDL-Frontier-Parser-nano",
    "2026-06-10",
    abstract=(
        "KDL-Frontier-Parser-nano is KoreaDeep's open-weight document parsing "
        "vision-language model for converting PDFs into structured output."
    ),
    is_open=True,
)

_MINERU_2_5_PRO = arxiv("2604.04771")
_PADDLEOCR_VL_1_6 = arxiv("2606.03264")
_TELEOCR = arxiv("2608.12898")
_UNLIMITED_OCR_2 = arxiv("2610.39308")
_DOTS_MOCR = arxiv("2603.13032")
_FALCON_OCR = arxiv("2603.27365")
_JINA_OCR_V1 = arxiv("2609.03181")

# Exact upstream `Provider` labels are the trust boundary between a leaderboard
# row and its reviewed introducing paper or official release page. Rows whose
# label is not reviewed here stay unpublished and are reported by the job.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "HPD-Parsing": arxiv("2607.18839"),
    "HunyuanOCR 1.5": arxiv("2607.04884"),
    "TeleOCR": _TELEOCR,
    "OvisOCR2": arxiv("2607.13639"),
    "WeVisDoc-2B": arxiv("2609.20423"),
    "WeVisDoc-4B": arxiv("2609.20423"),
    "OpenAI GPT-6.1 Sol (Reasoning Low)": _GPT_6_1_SOL,
    "OpenAI GPT-6.1 Terra (Reasoning Medium)": _GPT_6_1_TERRA,
    "OpenAI GPT-6.1 Terra (Reasoning Low)": _GPT_6_1_TERRA,
    "OvisOCR3": arxiv("2610.33066"),
    "Unlimited-OCR-2": _UNLIMITED_OCR_2,
    "Nemotron-3.5-Parse": _NEMOTRON_3_5_PARSE,
    "MiniCPM-OCR 1.0": _MINICPM_OCR_1,
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
    "Google Gemini 3.1 Flash Lite (Thinking Medium)": _GEMINI_3_1_FLASH_LITE,
    "Google Gemini 3.1 Flash Lite (Thinking High)": _GEMINI_3_1_FLASH_LITE,
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
    "Google Gemini 3.1 Flash Lite": _GEMINI_3_1_FLASH_LITE,
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
    "KDL-Frontier-Parser-nano": _KDL_NANO,
    # The v2 checkpoint has no release page of its own; KoreaDeep publishes it
    # as the next version of the nano parser.
    "KDL-Frontier-Parser-nano-v2": _KDL_NANO,
    "Infinity-Parser2-Pro": _INFINITY_PARSER2,
    "Infinity-Parser2-Flash": _INFINITY_PARSER2,
    "MinerU2.5-Pro-2605-1.2B": _MINERU_2_5_PRO,
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
    "Chandra-ocr-2": _CHANDRA_OCR_2,
    "Surya OCR 2": _SURYA_OCR_2,
    "PaddleOCR-VL-1.6": _PADDLEOCR_VL_1_6,
    "PaddleOCR-VL-1.5": arxiv("2601.21957"),
    "PaddleOCR-VL": arxiv("2510.14528"),
    "DeepSeek V4.1 Flash (Thinking High)": _DEEPSEEK_V4_1_FLASH,
    "DeepSeek V4.1 Flash (No Thinking)": _DEEPSEEK_V4_1_FLASH,
    "DeepSeek-OCR-2": arxiv("2601.20552"),
    "Gemma-4-31B-it": _GEMMA_4,
    "Gemma-4-26B-A4B-it": _GEMMA_4,
    "Gemma-4-E4B-it": _GEMMA_4,
    "Dots.mocr": _DOTS_MOCR,
    "Falcon-OCR": _FALCON_OCR,
    "Docling-models": arxiv("2408.09869"),
    "Nemotron-3-Nano-Omni-30B-A3B (Thinking)": arxiv("2604.24954"),
    "LightOnOCR-2-1B": arxiv("2601.14251"),
    "LightOnOCR-3-4B": _LIGHTONOCR_3,
    "LightOnOCR-3-1B": _LIGHTONOCR_3,
    "LightOnOCR-3-0.8B": _LIGHTONOCR_3,
    "aeddix-alpine-ocr (KDL pipeline)": external(
        "https://huggingface.co/aeddix-labs/aeddix-alpine-ocr",
        "Aeddix Alpine OCR",
        "2026-10-06",
        abstract=(
            "Aeddix Alpine OCR is an open-weight 1.2B document parsing model "
            "fine-tuned from MinerU2.5-Pro-2605-1.2B that converts page images "
            "to Markdown."
        ),
        is_open=True,
    ),
    "Qianfan-OCR": arxiv("2603.13398"),
    "Unlimited-OCR": arxiv("2606.23050"),
    "Jina-OCR-v1": _JINA_OCR_V1,
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
        "Reducto (r-1-mini)",
        "DocAI",
        "Nutrient DWS (Agentic)",
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
        # API snapshot document-parse-260930; Upstage publishes only a changelog.
        "Upstage Document Parse 2 (Enhanced)",
    }
)


_PARSEBENCH_2 = external(
    "https://www.llamaindex.ai/files/parsebench-v2-severity-aware-evaluation-of-document-parsing.pdf",
    "ParseBench-2: Severity-Aware Evaluation of Document Parsing",
    "2026-11-12",
)
_GEMINI_4_ARGON = external(
    "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/",
    "Gemini 4 Argon: our next era of frontier intelligence",
    "2026-09-30",
)
_MISTRAL_OCR_4_1 = external(
    "https://docs.mistral.ai/models/ocr-4-1", "Mistral OCR 4.1", "2026-07-16"
)

# ParseBench-2 `Provider` labels with their reviewed paper and, for open-weight
# models, the Hub checkpoint (the v2 CSV has no HF_Model_ID column). Seeded
# from the reviewed one-time import of 2026-11-16.
PARSEBENCH_2_MODELS: dict[str, tuple[PaperIdentity, str | None]] = {
    # The ParseBench-2 report is LlamaIndex's own report on LlamaParse.
    "LlamaParse (Agentic Plus)": (_PARSEBENCH_2, None),
    "LlamaParse (Agentic)": (_PARSEBENCH_2, None),
    "LlamaParse (Cost Effective)": (_PARSEBENCH_2, None),
    "Claude Opus 5.5": (_OPUS_5_5, None),
    "Claude Sonnet 5.5": (_SONNET_5_5, None),
    "Claude Haiku 5.5": (_HAIKU_5_5, None),
    "Gemini 4 argon (low)": (_GEMINI_4_ARGON, None),
    "Gemini 3 Flash (minimal)": (_GEMINI_3_FLASH, None),
    "Gemini 3.5 Flash": (_GEMINI_3_5, None),
    "Gemini 3.6 Flash": (_GEMINI_3_6_FLASH, None),
    "Gemini 3.5 Flash-Lite": (_GEMINI_3_6_FLASH, None),
    "Gemini 3.7 Flash (low)": (_GEMINI_3_7_FLASH, None),
    "Gemini 3.8 Flash (low)": (_GEMINI_3_8_FLASH, None),
    "Gemini 3.1 Flash-Lite": (_GEMINI_3_1_FLASH_LITE, None),
    "GPT-5.6 terra (low)": (_GPT_5_6, None),
    "GPT-5.6 luna (low)": (_GPT_5_6, None),
    "GPT-6 luna (low)": (_GPT_6_SOL_LUNA, None),
    "GPT-6.1 terra (low)": (_GPT_6_1_TERRA, None),
    "Mistral OCR 4.1 (annotation)": (_MISTRAL_OCR_4_1, None),
    "Mistral OCR 4.1": (_MISTRAL_OCR_4_1, None),
    "KDL-Frontier-Parser-nano-v2": (_KDL_NANO, "KDLAI/KDL-Frontier-Parser-nano-v2"),
    "Infinity-Parser2 Pro": (_INFINITY_PARSER2, "infly/Infinity-Parser2-Pro"),
    "Infinity-Parser2 Flash": (_INFINITY_PARSER2, "infly/Infinity-Parser2-Flash"),
    "LightOnOCR-3 4B": (_LIGHTONOCR_3, "lightonai/LightOnOCR-3-4B"),
    "LightOnOCR-3 0.8B": (_LIGHTONOCR_3, "lightonai/LightOnOCR-3-0.8B"),
    "Chandra 2": (_CHANDRA_OCR_2, "datalab-to/chandra-ocr-2"),
    "MinerU2.5-Pro": (_MINERU_2_5_PRO, "opendatalab/MinerU2.5-Pro-2605-1.2B"),
    "Nemotron Parse 3.5": (_NEMOTRON_3_5_PARSE, "nvidia/Nemotron-3.5-Parse"),
    "PaddleOCR-VL 1.6": (_PADDLEOCR_VL_1_6, "PaddlePaddle/PaddleOCR-VL-1.6"),
    "MiniCPM-OCR-1.0": (_MINICPM_OCR_1, "openbmb/MiniCPM-OCR-1.0"),
    "surya-ocr-2": (_SURYA_OCR_2, "datalab-to/surya-ocr-2"),
    "HunyuanOCR": (arxiv("2511.19575"), "tencent/HunyuanOCR"),
    "TeleOCR": (_TELEOCR, "StarDoc-AI/TeleOCR"),
    "Unlimited-OCR-2": (_UNLIMITED_OCR_2, "baidu/Unlimited-OCR-2"),
    "dots.mocr": (_DOTS_MOCR, "rednote-hilab/dots.mocr"),
    "Qwen3.8 27B": (_QWEN_3_8_27B, "Qwen/Qwen3.8-27B"),
    "Falcon-OCR": (_FALCON_OCR, "tiiuae/Falcon-OCR"),
    "jina-ocr-v1": (_JINA_OCR_V1, "jinaai/jina-ocr-v1"),
    "Qwen3.5-4B": (_QWEN_3_5, "Qwen/Qwen3.5-4B"),
    "gemma-4-E4B-it": (_GEMMA_4, "google/gemma-4-E4B-it"),
}

# Commercial parsing products without an introducing paper, as on ParseBench.
PARSEBENCH_2_EXCLUDED_PROVIDERS: frozenset[str] = frozenset(
    {
        "Reducto (r-1)",
        "Reducto (r-1-mini)",
        "Reducto (non-agentic)",
        "Reducto",
        "Extend (Parse 2)",
        "Extend (Parse Light)",
        "Extend (Parse)",
        "Pulse (Ultra 2)",
        "Datalab (Accurate)",
        "Datalab (Balanced)",
        "Datalab (Fast)",
        "Databricks AI Parse",
        "LandingAI",
        "Azure Document Intelligence (layout)",
    }
)


@dataclass(frozen=True)
class ParseBenchBoard:
    """One ParseBench leaderboard CSV and the benchmark it keeps current."""

    source: str
    csv_url: str
    dataset_slug: str
    primary_metric: str
    # (metric name, CSV column) for every dimension score.
    dimensions: tuple[tuple[str, str], ...]
    identities: dict[str, PaperIdentity]
    excluded: frozenset[str]
    # Category prefixes of single-model rows; other rows need a reviewed identity.
    model_categories: tuple[str, ...]
    # How Overall is derived, quoted in every managed methodology.
    overall_note: str
    matcher_provider: str
    # CSV column naming each row's Hub checkpoint, if the board publishes one.
    hf_column: str | None = None
    # Hub checkpoints for reviewed labels on boards without an HF column.
    hf_model_ids: dict[str, str] = field(default_factory=dict)
    source_url: str = PARSEBENCH_SOURCE_URL
    task_slug: str = TASK_SLUG
    min_entries: int = MIN_EXPECTED_ENTRIES
    max_entries: int = MAX_EXPECTED_ENTRIES
    min_reviewed: int = MIN_REVIEWED_ENTRIES

    @property
    def metric_names(self) -> tuple[str, ...]:
        return (self.primary_metric, *(name for name, _ in self.dimensions))

    @property
    def managed_prefix(self) -> str:
        return managed_methodology_prefix(self.source)

    @property
    def required_columns(self) -> frozenset[str]:
        columns = {"Provider", "Category", "Overall", "Cost_Per_Page"}
        columns.update(column for _, column in self.dimensions)
        if self.hf_column:
            columns.add(self.hf_column)
        return frozenset(columns)


PARSEBENCH = ParseBenchBoard(
    source="ParseBench",
    csv_url=PARSEBENCH_CSV_URL,
    dataset_slug=DATASET_SLUG,
    primary_metric=PRIMARY_METRIC_NAME,
    dimensions=DIMENSION_METRICS,
    identities=MODEL_PAPER_IDENTITIES,
    excluded=EXCLUDED_PROVIDERS,
    model_categories=(MODEL_CATEGORY_PREFIX,),
    overall_note=(
        "overall is the mean of the five ParseBench dimension scores from the "
        "official leaderboard.csv"
    ),
    matcher_provider="parsebench",
    hf_column="HF_Model_ID",
)

PARSEBENCH_2 = ParseBenchBoard(
    source="ParseBench-2",
    csv_url=PARSEBENCH_2_CSV_URL,
    dataset_slug=PARSEBENCH_2_DATASET_SLUG,
    primary_metric=PARSEBENCH_2_PRIMARY_METRIC_NAME,
    dimensions=PARSEBENCH_2_DIMENSION_METRICS,
    identities={label: model[0] for label, model in PARSEBENCH_2_MODELS.items()},
    excluded=PARSEBENCH_2_EXCLUDED_PROVIDERS,
    model_categories=("Vision Models", "Open Weight"),
    overall_note=(
        "overall is the mean of the six ParseBench-2 dimension scores from the "
        "official leaderboard-v2.csv"
    ),
    matcher_provider="parsebench-2",
    hf_model_ids={
        label: hf_model_id
        for label, (_, hf_model_id) in PARSEBENCH_2_MODELS.items()
        if hf_model_id
    },
)


@dataclass(frozen=True)
class ParseBenchEntry:
    provider: str
    category: str
    overall: float
    dimensions: dict[str, float]
    cost_per_page_cents: float | None
    hf_model_id: str | None
    primary_metric: str = PRIMARY_METRIC_NAME

    @property
    def metrics(self) -> dict[str, float]:
        return {self.primary_metric: self.overall, **self.dimensions}


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
    # Hand-imported rows for the same paper and label that the sync now owns.
    adopted: int = 0
    deleted: int = 0
    excluded: int = 0
    auto_matched: list[str] = field(default_factory=list)
    unreviewed: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _hf_model_url(entry: ParseBenchEntry, board: ParseBenchBoard) -> str | None:
    hf_model_id = entry.hf_model_id or board.hf_model_ids.get(entry.provider)
    return f"https://huggingface.co/{hf_model_id}" if hf_model_id else None


def _leaderboard_model(entry: ParseBenchEntry) -> LeaderboardModel:
    # Open-weight rows name their Hub organization. Proprietary rows take the
    # lab of a known model family ("GLM-5.3 Flash"), else the vendor the
    # label leads with ("OpenAI GPT-6.1 Sol (Reasoning Low)").
    lab = entry.hf_model_id.split("/", 1)[0] if entry.hf_model_id else ""
    return vendor_label_model(entry.provider, lab)


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


def parse_parsebench_leaderboard(
    csv_text: str, board: ParseBenchBoard = PARSEBENCH
) -> list[ParseBenchEntry]:
    """Validate the published leaderboard CSV before it can affect rows."""
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise TypeError(f"{board.source} response must be non-empty CSV text")
    reader = csv.DictReader(StringIO(csv_text))
    columns = set(reader.fieldnames or ())
    missing = sorted(board.required_columns - columns)
    if missing:
        raise ValueError(f"{board.source} CSV is missing columns: {missing!r}")

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
        hf_model_id = (
            (raw.get(board.hf_column) or "").strip() or None
            if board.hf_column
            else None
        )
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
                    for name, column in board.dimensions
                },
                cost_per_page_cents=_cost(
                    raw.get("Cost_Per_Page") or "", provider=provider
                ),
                hf_model_id=hf_model_id,
                primary_metric=board.primary_metric,
            )
        )

    if not board.min_entries <= len(entries) <= board.max_entries:
        raise ValueError(
            f"{board.source} returned {len(entries)} rows; expected "
            f"{board.min_entries}-{board.max_entries}"
        )
    return entries


def fetch_parsebench_leaderboard(
    client: httpx.Client | None = None, board: ParseBenchBoard = PARSEBENCH
) -> list[ParseBenchEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-parsebench-sync/1.0"},
    )
    try:
        response = active_client.get(board.csv_url)
        response.raise_for_status()
        return parse_parsebench_leaderboard(response.text, board)
    finally:
        if owned_client:
            active_client.close()


def _managed_provider(row: Evaluation, board: ParseBenchBoard) -> str | None:
    methodology = row.methodology or ""
    if not methodology.startswith(board.managed_prefix):
        return None
    marker = " provider="
    start = methodology.find(marker)
    if start == -1:
        return None
    return methodology[start + len(marker) :].split(";", 1)[0]


def _methodology(entry: ParseBenchEntry, board: ParseBenchBoard) -> str:
    cost = (
        f"{entry.cost_per_page_cents:g} cents/page"
        if entry.cost_per_page_cents is not None
        else "cost not published"
    )
    return (
        f"{board.managed_prefix} provider={entry.provider}; "
        f"category={entry.category}; {board.overall_note}; {cost}."
    )


class ParseBenchSyncService:
    """Replace only evaluation rows owned by one ParseBench board's live sync."""

    def __init__(self, db: Session, board: ParseBenchBoard = PARSEBENCH):
        self.db = db
        self.board = board

    def sync(
        self,
        entries: list[ParseBenchEntry],
        *,
        discovery: ParseBenchDiscovery,
        commit: bool = True,
    ) -> ParseBenchSyncStats:
        board = self.board
        if not entries:
            raise ValueError(
                f"Refusing to synchronize an empty {board.source} leaderboard"
            )
        stats = ParseBenchSyncStats(fetched=len(entries))
        try:
            task, dataset = resolve_leaderboard(
                self.db,
                board.source,
                board.task_slug,
                board.dataset_slug,
                board.metric_names,
            )
            board_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .all()
            )
            managed: dict[str, Evaluation] = {}
            # Hand-imported rows keyed by (paper, label) that a published
            # entry takes over instead of duplicating.
            adoptable: dict[tuple[int, str], Evaluation] = {}
            for row in board_rows:
                if (provider := _managed_provider(row, board)) is not None:
                    managed[provider] = row
                elif not (row.methodology or "").startswith(board.managed_prefix):
                    adoptable.setdefault((row.paper_id, row.model_name), row)
            linked_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            reviewed: list[ParseBenchEntry] = []
            new_models: list[ParseBenchEntry] = []
            for entry in entries:
                if entry.provider in board.identities:
                    reviewed.append(entry)
                elif entry.provider in board.excluded:
                    stats.excluded += 1
                elif entry.category.startswith(board.model_categories):
                    new_models.append(entry)
                else:
                    stats.unreviewed.append(entry.provider)
            if len(reviewed) < board.min_reviewed:
                raise RuntimeError(
                    f"{board.source} has only {len(reviewed)} reviewed rows; "
                    "refusing to replace the managed leaderboard"
                )
            # New single-model rows are matched to an indexed paper; the rest
            # become release-radar signals and match on a later run.
            matcher = LeaderboardModelMatcher(
                self.db,
                provider=board.matcher_provider,
                leaderboard_name=board.source,
                leaderboard_url=board.source_url,
            )
            matched = matcher.match([_leaderboard_model(e) for e in new_models])
            # (entry, paper id, is_open, HF model URL)
            publishable: list[tuple[ParseBenchEntry, int, bool, str | None]] = []
            for entry in reviewed:
                identity = board.identities[entry.provider]
                paper_id = discovery.papers.get(identity.key)
                if paper_id is None:
                    if commit:
                        raise RuntimeError(
                            f"No reviewed paper resolved for {entry.provider!r}"
                        )
                    stats.missing_papers.append(entry.provider)
                    continue
                publishable.append(
                    (entry, paper_id, identity.is_open, _hf_model_url(entry, board))
                )
            for entry in new_models:
                if (match := matched.get(_leaderboard_model(entry).name)) is None:
                    stats.unreviewed.append(entry.provider)
                    continue
                # A published Hub checkpoint makes the row open-weight.
                publishable.append(
                    (
                        entry,
                        match.paper_id,
                        entry.hf_model_id is not None or match.is_open,
                        _hf_model_url(entry, board) or match.hf_model_url,
                    )
                )
                stats.auto_matched.append(entry.provider)
            matcher.report_unmatched(
                [
                    _leaderboard_model(e)
                    for e in new_models
                    if _leaderboard_model(e).name not in matched
                ]
            )

            now = datetime.now(UTC)
            published: set[str] = set()
            for entry, paper_id, is_open, hf_model_url in publishable:
                row = managed.get(entry.provider)
                if row is not None:
                    stats.updated += 1
                elif row := adoptable.pop((paper_id, entry.provider), None):
                    stats.adopted += 1
                else:
                    row = Evaluation(
                        paper_id=paper_id, task_id=task.id, dataset_id=dataset.id
                    )
                    self.db.add(row)
                    stats.created += 1
                row.paper_id = paper_id
                row.model_name = entry.provider
                row.harness = None
                row.methodology = _methodology(entry, board)
                row.metrics = entry.metrics
                row.uses_additional_data = False
                row.is_open = is_open
                row.best_metric = board.primary_metric
                row.evaluated_on = now.date()
                row.external_source_url = board.source_url
                row.source_url = board.source_url
                row.external = True
                row.hf_model_url = hf_model_url
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
                task.id, dataset.id, metric_name=board.primary_metric, commit=False
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
        board: ParseBenchBoard = PARSEBENCH,
        ingestion_service: PaperIngestionService | None = None,
        external_service: ExternalResourceService | None = None,
    ):
        self.db = db
        self.board = board
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
            identity.key: identity for identity in self.board.identities.values()
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
    db: Session, *, board: ParseBenchBoard = PARSEBENCH, persist: bool = True
) -> ParseBenchDiscovery:
    return await ParseBenchPaperDiscoveryService(db, board=board).discover(
        persist=persist
    )


def run_discovery(
    db: Session, *, board: ParseBenchBoard = PARSEBENCH, persist: bool = True
) -> ParseBenchDiscovery:
    return asyncio.run(discover_parsebench_papers(db, board=board, persist=persist))
