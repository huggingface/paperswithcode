"""Live board for the official FrontierRSI leaderboard.

https://frontier-rsi.org/ (Abundant AI) renders its leaderboard client-side
from a plain-data ``window.FRSI = {...}`` object in ``data.js``. Each task
lists every model's four trial rewards and their mean (avg@4); the site ranks
a model by the mean of its avg@4 over all tasks, so every task counts equally.
The PwC ``frontier-rsi`` benchmark mirrors that overall score as a percentage.
Scores are only comparable on one task set, so the parser fails when the
category list or the task count changes.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal

import httpx

from backend.services.leaderboard_sync_catalog import ModelIdentity
from backend.services.live_leaderboard_sync import (
    LeaderboardEntry,
    LiveLeaderboard,
    check_entry_count,
    fetch_text,
)

FRONTIER_RSI_URL = "https://frontier-rsi.org/"
FRONTIER_RSI_DATA_URL = "https://frontier-rsi.org/data.js"
TASK_SLUG = "auto-research"
DATASET_SLUG = "frontier-rsi"
METRIC_NAME = "Score"
CATEGORIES = ("pretrain", "posttrain", "inference", "kernels")
TASK_COUNT = 27
MIN_EXPECTED_ENTRIES = 5
MAX_EXPECTED_ENTRIES = 100
MIN_SELECTED_ENTRIES = 5

HARNESSES = {
    "Antigravity CLI": "Antigravity CLI",
    "Claude Code": "Claude Code",
    "Codex": "Codex",
    "Grok Build": "Grok Build",
    "Muse Code": "Muse Code",
    "mini-swe-agent": "mini-SWE-agent",
}

MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "Gemini 4 Neon": ModelIdentity(
        "Gemini 4 Neon",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/introducing-gemini-4-neon/"
        ),
    ),
    "Claude Fable 5.2": ModelIdentity(
        "Claude Fable 5.2",
        source_url="https://www.anthropic.com/claude-fable-and-mythos-5-2",
    ),
    "Claude Opus 5.5": ModelIdentity(
        "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
    ),
    "GPT-6.2 Astra": ModelIdentity(
        "GPT-6.2 Astra",
        source_url="https://openai.com/index/introducing-gpt-6-2-astra-sol/",
    ),
    "GPT-6.2 Sol": ModelIdentity(
        "GPT-6.2 Sol",
        source_url="https://openai.com/index/introducing-gpt-6-2-astra-sol/",
    ),
    "Gemini 4 Carbon": ModelIdentity(
        "Gemini 4 Carbon",
        source_url=(
            "https://deepmind.google/blog/gemini-4-carbon-our-next-frontier-model/"
        ),
    ),
    "Gemini 4 Argon": ModelIdentity(
        "Gemini 4 Argon",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-4-argon/"
        ),
    ),
    "GPT-6.1 Sol": ModelIdentity(
        "GPT-6.1 Sol", source_url="https://openai.com/index/introducing-gpt-6-1-sol/"
    ),
    "GPT-6 Astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "Kimi K3.1 Pro": ModelIdentity(
        "Kimi K3.1 Pro",
        source_url="https://www.kimi.com/blog/kimi-k3-1-pro",
        is_open=True,
    ),
    "Muse Wonder 1.0": ModelIdentity(
        "Muse Wonder 1.0", source_url="https://research.meta.ai/blog/muse-wonder"
    ),
    "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
    "Inkling 2 Small": ModelIdentity(
        "Inkling-2-Small",
        source_url="https://thinkingmachines.ai/news/inkling-2-small",
        is_open=True,
    ),
}

_DATA_ROOT = "window.FRSI"


def parse_frontier_rsi(text: str) -> list[LeaderboardEntry]:
    """Rank models as the site does, failing on any task-set or layout change."""
    start = text.find(_DATA_ROOT)
    if start < 0:
        raise ValueError("FrontierRSI data.js no longer defines window.FRSI")
    try:
        data, _ = json.JSONDecoder().raw_decode(text, text.index("{", start))
    except json.JSONDecodeError as exc:
        raise ValueError("FrontierRSI data is not JSON") from exc
    categories = tuple(category["id"] for category in data.get("categories", []))
    if categories != CATEGORIES:
        raise ValueError(f"FrontierRSI categories changed: {categories}")
    tasks = data.get("tasks") or []
    if len(tasks) != TASK_COUNT:
        raise ValueError(f"FrontierRSI lists {len(tasks)} tasks; expected {TASK_COUNT}")

    totals: dict[str, Decimal] = {}
    setups: dict[str, tuple[str, str]] = {}
    for task in tasks:
        if task.get("category") not in CATEGORIES:
            raise ValueError(f"FrontierRSI task {task.get('id')!r} has no category")
        seen: set[str] = set()
        for result in task.get("models") or []:
            name = result.get("model")
            if not (isinstance(name, str) and name and len(name) <= 200):
                raise ValueError(f"FrontierRSI task {task.get('id')!r} has no model")
            if name in seen:
                raise ValueError(f"FrontierRSI task {task['id']!r} lists {name} twice")
            seen.add(name)
            harness = HARNESSES.get(result.get("harness"))
            effort = result.get("effort")
            if harness is None or not effort:
                raise ValueError(
                    f"FrontierRSI harness {result.get('harness')!r} is not "
                    f"reviewed: {name}"
                )
            if setups.setdefault(name, (harness, effort)) != (harness, effort):
                raise ValueError(f"FrontierRSI runs {name} in two setups")
            if result.get("avg") is None:
                continue
            value = Decimal(str(result["avg"]))
            if not 0 <= value <= 1:
                raise ValueError(f"FrontierRSI avg@4 is out of range: {name}")
            totals[name] = totals.get(name, Decimal(0)) + value

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    entries: list[LeaderboardEntry] = []
    for rank, (name, total) in enumerate(ranked, start=1):
        score = (total * 100 / TASK_COUNT).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        harness, effort = setups[name]
        lab = (data.get("models") or {}).get(name, {}).get("lab", "")
        entries.append(
            LeaderboardEntry(
                name,
                score,
                f"rank {rank} of {len(ranked)}, score {score}% (avg@4 over "
                f"{TASK_COUNT} tasks), run in {harness} at {effort} effort",
                harness=harness,
                lab=lab,
            )
        )
    check_entry_count(
        entries, "FrontierRSI leaderboard", MIN_EXPECTED_ENTRIES, MAX_EXPECTED_ENTRIES
    )
    return entries


def fetch_frontier_rsi(client: httpx.Client | None = None) -> list[LeaderboardEntry]:
    return parse_frontier_rsi(fetch_text(FRONTIER_RSI_DATA_URL, client))


BOARD = LiveLeaderboard(
    source="FrontierRSI",
    provider="frontier-rsi",
    url=FRONTIER_RSI_URL,
    task_slug=TASK_SLUG,
    dataset_slug=DATASET_SLUG,
    metric=METRIC_NAME,
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    protocol=(
        f"FrontierRSI overall score: equal-weight mean over {TASK_COUNT} "
        "AI-research tasks (pre-training, post-training and harness, "
        "inference and serving, kernels) of each model's avg@4, the mean "
        "reward of four independent trials; a trial's reward is calibrated "
        "against the best valid model trial from an initial run, with partial "
        "credit within 10% of it and 0 for a failed correctness, accuracy or "
        "resource check."
    ),
)
