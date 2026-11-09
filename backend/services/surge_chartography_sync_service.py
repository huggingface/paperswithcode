"""Live board for the official Surge AI Chartography (no tools) leaderboard.

The parser reads Surge's server-rendered block into ``LeaderboardEntry`` rows,
and the shared ``LiveLeaderboardSyncService`` publishes them.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup

from backend.services.leaderboard_sync_catalog import ModelIdentity
from backend.services.live_leaderboard_sync import (
    LeaderboardEntry,
    LiveLeaderboard,
    fetch_text,
)

SURGE_CHARTOGRAPHY_URL = "https://surgehq.ai/benchmarks/chartography"
TASK_SLUG = "image-understanding"
# Surge evaluates without tools; the with-tools `chartography` benchmark is
# curated by hand from vendor model cards and is never touched here.
DATASET_SLUG = "chartography-no-tools"
METRIC_NAME = "Pass@1"
MODEL_NAME_SUFFIX = " (no tools)"
LEADERBOARD_TITLE = "Chartography Leaderboard"
# The page is a Webflow site that rejects non-browser user agents.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36 paperswithcode-surge-chartography-sync/1.0"
)
MIN_EXPECTED_ROWS = 25
MAX_EXPECTED_ROWS = 400
# Refuse to touch the managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 30


_GEMINI_BLOG = "https://blog.google/innovation-and-ai/models-and-research/gemini-models"
_GPT_5_6 = "https://openai.com/index/gpt-5-6/"
_GPT_6 = "https://openai.com/index/introducing-gpt-6-sol-and-luna/"

# Exact Surge model labels (provider + model, without the reasoning
# configuration) are the trust boundary between a leaderboard row and its
# introducing paper. Model names follow the catalog, reviewed against the 41
# rows hand-imported on 2026-10-17. Other labels are matched automatically when
# the catalog names them unambiguously, and otherwise handed to the release
# radar.
MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "Gemini 4 Argon": ModelIdentity(
        "Gemini 4 Argon", source_url=f"{_GEMINI_BLOG}/gemini-4-argon/"
    ),
    "GPT 6 Astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "Claude Opus 5.5": ModelIdentity(
        "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
    ),
    "GPT 6 Sol": ModelIdentity("GPT-6 Sol", source_url=_GPT_6),
    "Claude Fable 5.1": ModelIdentity(
        "Claude Fable 5.1",
        source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
    ),
    "GPT 5.6 Sol": ModelIdentity("GPT-5.6 Sol", source_url=_GPT_5_6),
    "Gemini 3.8 Flash": ModelIdentity(
        "Gemini 3.8 Flash", source_url=f"{_GEMINI_BLOG}/3-8-flash-and-3-8-flash-cyber/"
    ),
    "Gemini 3.7 Flash": ModelIdentity(
        "Gemini 3.7 Flash",
        source_url=f"{_GEMINI_BLOG}/introducing-gemini-3-7-flash/",
    ),
    "Claude Fable 5": ModelIdentity(
        "Claude Fable 5",
        source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5",
    ),
    "Gemini 3.6 Flash": ModelIdentity(
        "Gemini 3.6 Flash",
        source_url=f"{_GEMINI_BLOG}/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
    ),
    "GPT 5.6 Terra": ModelIdentity("GPT-5.6 Terra", source_url=_GPT_5_6),
    "Muse Spark 1.2": ModelIdentity(
        "Muse Spark 1.2",
        source_url="https://developer.meta.com/ai/resources/blog/build-with-muse-code/",
    ),
    "GPT 5.6 Luna": ModelIdentity("GPT-5.6 Luna", source_url=_GPT_5_6),
    "GPT 5.5": ModelIdentity(
        "GPT-5.5", source_url="https://openai.com/index/introducing-gpt-5-5/"
    ),
    "GPT 5.4": ModelIdentity(
        "GPT-5.4", source_url="https://openai.com/index/introducing-gpt-5-4/"
    ),
    "GPT 6 Luna": ModelIdentity("GPT-6 Luna", source_url=_GPT_6),
    "Qwen 3.8 Max": ModelIdentity(
        "Qwen3.8-Max", source_url="https://qwen.ai/blog?id=qwen3.8", is_open=True
    ),
    "Muse Spark 1.3": ModelIdentity(
        "Muse Spark 1.3",
        source_url="https://research.meta.ai/blog/introducing-muse-spark-1-3",
    ),
    "Claude Opus 5": ModelIdentity(
        "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
    ),
    "Kimi K3": ModelIdentity(
        "Kimi K3",
        arxiv_id="2607.24653",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K3",
    ),
    "Gemini 3.1 Pro": ModelIdentity(
        "Gemini 3.1 Pro", source_url=f"{_GEMINI_BLOG}/gemini-3-1-pro/"
    ),
    "Muse Spark 1.1": ModelIdentity(
        "Muse Spark 1.1",
        source_url="https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/",
    ),
    "Grok 4.6": ModelIdentity("Grok 4.6", source_url="https://x.ai/news/grok-4-6"),
    # The Qwen Cloud API version of the open-weight Qwen3.8-Flash-Next.
    "Qwen 3.8 Flash": ModelIdentity(
        "Qwen3.8-Flash", source_url="https://huggingface.co/Qwen/Qwen3.8-Flash-Next"
    ),
    "Muse Glimmer 30B": ModelIdentity(
        "Muse Glimmer-30B",
        arxiv_id="2610.24628",
        is_open=True,
        hf_model_url="https://huggingface.co/meta-models/Muse-Glimmer-30B",
    ),
    "Grok 4.5": ModelIdentity("Grok 4.5", source_url="https://x.ai/news/grok-4-5"),
    "Claude Sonnet 5": ModelIdentity(
        "Claude Sonnet 5", source_url="https://www.anthropic.com/news/claude-sonnet-5"
    ),
    "Claude Opus 4.7": ModelIdentity(
        "Claude Opus 4.7", source_url="https://www.anthropic.com/news/claude-opus-4-7"
    ),
    "GLM 5.3 Flash": ModelIdentity(
        "GLM-5.3-Flash",
        source_url="https://z.ai/blog/glm-5.3-flash",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3-Flash",
    ),
    "Claude Opus 4.8": ModelIdentity(
        "Claude Opus 4.8", source_url="https://www.anthropic.com/news/claude-opus-4-8"
    ),
    "Qwen 3.5 Plus": ModelIdentity(
        "Qwen3.5-Plus", source_url="https://qwen.ai/blog?id=qwen3.5"
    ),
    "Qwen 3.7 Plus": ModelIdentity(
        "Qwen3.7-Plus", source_url="https://www.qwencloud.com/models/qwen3.7-plus"
    ),
    "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
    "Grok 4.3": ModelIdentity(
        "Grok 4.3", source_url="https://docs.x.ai/developers/models/grok-4.3"
    ),
    "Kimi K2.5": ModelIdentity(
        "Kimi K2.5",
        arxiv_id="2602.02276",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K2.5",
    ),
    "Kimi K2.6": ModelIdentity(
        "Kimi K2.6",
        source_url="https://www.kimi.com/blog/kimi-k2-6",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K2.6",
    ),
    "DeepSeek V4.1 Flash": ModelIdentity(
        "DeepSeek-V4.1-Flash",
        arxiv_id="2609.19969",
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash",
    ),
    "Gemini 3.5 Flash-Lite": ModelIdentity(
        "Gemini 3.5 Flash-Lite",
        source_url=f"{_GEMINI_BLOG}/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
    ),
    "Inkling": ModelIdentity(
        "Inkling",
        source_url="https://thinkingmachines.ai/news/introducing-inkling/",
        is_open=True,
        hf_model_url="https://huggingface.co/thinkingmachines/inkling",
    ),
    "Inkling Small": ModelIdentity(
        "Inkling-Small",
        source_url="https://huggingface.co/thinkingmachines/Inkling-Small",
        is_open=True,
        hf_model_url="https://huggingface.co/thinkingmachines/Inkling-Small",
    ),
    "Mistral Large 3": ModelIdentity(
        "Mistral Large 3",
        source_url="https://docs.mistral.ai/models/model-cards/mistral-large-3-25-12",
        is_open=True,
    ),
}

# Reviewed labels that are deliberately not published.
EXCLUDED_LABELS: dict[str, str] = {
    "DeepSeek V4 Flash Vision (experimental)": (
        "experimental checkpoint; its catalog paper was deleted on 2026-10-17"
    ),
}


def _text(node) -> str:
    return " ".join(node.get_text(" ").split())


_CONFIGURATION = re.compile(r"^(?P<model>.+?) \((?P<configuration>[^()]+)\)$")


def _split_label(brand: str, name: str) -> tuple[str, str]:
    """Join the provider and model, separating the trailing reasoning setup.

    Surge shows a model as provider + "<model> (<reasoning configuration>)"
    (e.g. "Gemini" + "4 Argon (High reasoning)"); a model without a listed
    configuration ("Mistral" + "Large 3") uses "default".
    """
    match = _CONFIGURATION.match(name)
    model, configuration = (
        (match["model"], match["configuration"]) if match else (name, "default")
    )
    # "Inkling" + "Inkling" is the model Inkling, not "Inkling Inkling".
    label = (
        model
        if model == brand or model.startswith(f"{brand} ")
        else (f"{brand} {model}")
    )
    return label, configuration


def parse_surge_chartography(html: str) -> list[LeaderboardEntry]:
    """Parse the server-rendered leaderboard, failing on any layout change."""
    if not isinstance(html, str) or not html.strip():
        raise TypeError("Surge AI response must be non-empty HTML")
    soup = BeautifulSoup(html, "html.parser")
    titles = [
        node
        for node in soup.select(".lead-rank-table-title")
        if _text(node) == LEADERBOARD_TITLE
    ]
    if len(titles) != 1:
        raise ValueError(
            f"Surge AI page has {len(titles)} {LEADERBOARD_TITLE!r} blocks; expected 1"
        )
    block = titles[0].find_parent(class_="lead-rank-table-list-inner")
    if block is None:
        raise ValueError("Surge AI leaderboard block layout changed")
    entries: list[LeaderboardEntry] = []
    seen: set[str] = set()
    for position, row in enumerate(block.select("[data-leaderboard-row]"), start=1):
        brand = row.select_one(".head-rank-table-brand")
        name = row.select_one(".head-rank-table-name")
        score = row.select_one("[data-score]")
        if brand is None or name is None or score is None:
            raise ValueError(f"Surge AI row {position} layout changed")
        # The logo's alt text ("Google logo") names the lab, when present.
        logo = row.select_one(".lead-model-logo img[alt]")
        alt = " ".join(logo["alt"].split()) if logo is not None else ""
        lab = alt.removesuffix(" logo") if alt.endswith(" logo") else ""
        label, configuration = _split_label(_text(brand), _text(name))
        if not label or len(label) > 200:
            raise ValueError(f"Surge AI row {position} is malformed: {label!r}")
        # The bar width and the visible text must agree, followed by "%".
        visible = _text(score.parent)
        try:
            value = Decimal(score["data-score"])
        except InvalidOperation as exc:
            raise ValueError(f"Surge AI score is invalid for {label!r}") from exc
        if visible.replace(" ", "") != f"{score['data-score']}%":
            raise ValueError(f"Surge AI score is not a percentage: {visible!r}")
        if not 0 <= value <= 100:
            raise ValueError(f"Surge AI score is outside 0-100 for {label!r}")
        if label in seen:
            raise ValueError(f"Surge AI lists {label!r} twice")
        seen.add(label)
        entries.append(
            LeaderboardEntry(
                label,
                value,
                f"{value}% Pass@1 ({configuration})",
                lab=lab[:200],
            )
        )
    if not MIN_EXPECTED_ROWS <= len(entries) <= MAX_EXPECTED_ROWS:
        raise ValueError(
            f"Surge AI Chartography has {len(entries)} rows; expected "
            f"{MIN_EXPECTED_ROWS}-{MAX_EXPECTED_ROWS}"
        )
    return entries


def fetch_surge_chartography(
    client: httpx.Client | None = None,
) -> list[LeaderboardEntry]:
    return parse_surge_chartography(
        fetch_text(SURGE_CHARTOGRAPHY_URL, client, user_agent=USER_AGENT)
    )


BOARD = LiveLeaderboard(
    source="Surge AI Chartography",
    provider="surge-chartography",
    url=SURGE_CHARTOGRAPHY_URL,
    task_slug=TASK_SLUG,
    dataset_slug=DATASET_SLUG,
    metric=METRIC_NAME,
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    model_name_suffix=MODEL_NAME_SUFFIX,
    excluded=EXCLUDED_LABELS,
)
