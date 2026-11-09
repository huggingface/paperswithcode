"""Live board for the official Vals AI Finance Agent v2 leaderboard.

The parser reads Vals' leaderboard table into ``LeaderboardEntry`` rows, and
the shared ``LiveLeaderboardSyncService`` publishes them.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup

from backend.services.leaderboard_sync_catalog import ModelIdentity
from backend.services.live_leaderboard_sync import (
    LeaderboardEntry,
    LiveLeaderboard,
    fetch_text,
)

VALS_FINANCE_AGENT_URL = "https://www.vals.ai/benchmarks/fabv2"
TASK_SLUG = "agents"
DATASET_SLUG = "finance-agent-v2"
METRIC_NAME = "Accuracy"
# Only these leading columns are read; Vals relabels the cost/duration columns
# after them (2026-10-26: "Tokens / Test", "Duration / Test").
TABLE_HEADER = ("Rank", "Model", "Accuracy")
USER_AGENT = "paperswithcode-vals-finance-agent-sync/1.0"
MIN_EXPECTED_ROWS = 40
MAX_EXPECTED_ROWS = 400
# Refuse to touch the managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 50


_MUSE_SPARK_1_3 = "https://research.meta.ai/blog/introducing-muse-spark-1-3"

# Exact Vals model labels are the trust boundary between a leaderboard row and
# its introducing paper. Model names follow the catalog (reviewed on
# 2026-10-14, 2026-10-16 and 2026-10-18), not Vals' spelling. Other labels are
# matched automatically when the catalog names them unambiguously, and
# otherwise handed to the release radar.
_MISTRAL_LARGE_4 = ModelIdentity(
    "Mistral Large 4 Preview",
    source_url=(
        "https://huggingface.co/mistralai/Mistral-Large-4-1T-A52B/blob/main/"
        "assets/technical_report.pdf"
    ),
)
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
        "Muse Spark 1.3 Max", source_url=_MUSE_SPARK_1_3
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
    # Upstream switches between both labels.
    "Mistral Large 4": _MISTRAL_LARGE_4,
    "Mistral Large 4 Preview": _MISTRAL_LARGE_4,
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
    "Qwen 3.8 Max 0902": ModelIdentity(
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


def _text(node) -> str:
    return " ".join(node.get_text(" ").split())


def parse_vals_finance_agent(html: str) -> list[LeaderboardEntry]:
    """Parse the leaderboard table, failing on any layout change."""
    if not isinstance(html, str) or not html.strip():
        raise TypeError("Vals AI response must be non-empty HTML")
    # The page also renders sample answers whose Markdown can contain tables,
    # so pick the leaderboard by its header instead of by position.
    leaderboards = []
    for table in BeautifulSoup(html, "html.parser").find_all("table"):
        rows = table.find_all("tr")
        header = (
            tuple(_text(cell) for cell in rows[0].find_all(["th", "td"]))
            if rows
            else ()
        )
        if header[: len(TABLE_HEADER)] == TABLE_HEADER:
            leaderboards.append((rows, header))
    if len(leaderboards) != 1:
        raise ValueError(
            f"Vals AI page has {len(leaderboards)} leaderboard tables with header "
            f"{TABLE_HEADER!r}; expected 1"
        )
    rows, header = leaderboards[0]
    entries: list[LeaderboardEntry] = []
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
        entries.append(LeaderboardEntry(label, value, f"{value}% Accuracy"))
    if not MIN_EXPECTED_ROWS <= len(entries) <= MAX_EXPECTED_ROWS:
        raise ValueError(
            f"Vals AI Finance Agent v2 has {len(entries)} rows; expected "
            f"{MIN_EXPECTED_ROWS}-{MAX_EXPECTED_ROWS}"
        )
    return entries


def fetch_vals_finance_agent(
    client: httpx.Client | None = None,
) -> list[LeaderboardEntry]:
    return parse_vals_finance_agent(
        fetch_text(VALS_FINANCE_AGENT_URL, client, user_agent=USER_AGENT)
    )


BOARD = LiveLeaderboard(
    source="Vals AI Finance Agent v2",
    provider="vals-finance-agent",
    url=VALS_FINANCE_AGENT_URL,
    task_slug=TASK_SLUG,
    dataset_slug=DATASET_SLUG,
    metric=METRIC_NAME,
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
)
