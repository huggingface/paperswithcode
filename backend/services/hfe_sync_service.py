"""Live board for the official Humanity's First Exam leaderboard on Kaggle.

https://www.kaggle.com/benchmarks/deepmind/hfe/leaderboard renders in the
browser, so the board reads Kaggle's documented public API
(``benchmarks.BenchmarksApiService/GetBenchmarkLeaderboard``, the call the
official ``kagglesdk`` makes) with a ``KAGGLE_API_TOKEN``. Kaggle publishes one
score per model configuration: family pass^4, the share of four-prompt
families answered correctly on all 16 draws. The PwC ``humanitys-first-exam-hfe``
benchmark mirrors it on its Family Pass^4 board; the Pass@1 board stays the
paper's Table 4. Scores are only comparable within one task version, so the
parser fails when Kaggle moves to another version or reshapes a row.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from backend.services.leaderboard_model_matching_service import family_lab
from backend.services.leaderboard_sync_catalog import ModelIdentity
from backend.services.live_leaderboard_sync import (
    USER_AGENT,
    LeaderboardEntry,
    LiveLeaderboard,
    check_entry_count,
)

HFE_URL = "https://www.kaggle.com/benchmarks/deepmind/hfe/leaderboard"
KAGGLE_API_URL = (
    "https://api.kaggle.com/v1/benchmarks.BenchmarksApiService/GetBenchmarkLeaderboard"
)
OWNER_SLUG = "deepmind"
BENCHMARK_SLUG = "hfe"
TASK_SLUG = "reasoning"
DATASET_SLUG = "humanitys-first-exam-hfe"
METRIC_NAME = "Family Pass^4"
SCORE_TASK = "Family pass^4"
OVERALL_TASK = "(Overall)"
TASK_VERSION = 1
CANDIDATE_CLASS = "BENCHMARK_CANDIDATE_CLASS_MODEL_VERSION_CONFIG"
MIN_EXPECTED_ENTRIES = 10
MAX_EXPECTED_ENTRIES = 100
MIN_SELECTED_ENTRIES = 10

_GEMINI_BLOG = "https://blog.google/innovation-and-ai/models-and-research/gemini-models"

MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "GPT-6.2 Astra": ModelIdentity(
        "GPT-6.2 Astra",
        source_url="https://openai.com/index/introducing-gpt-6-2-astra-sol/",
    ),
    "GPT-6.2 Sol": ModelIdentity(
        "GPT-6.2 Sol",
        source_url="https://openai.com/index/introducing-gpt-6-2-astra-sol/",
    ),
    "GPT-6.1 Sol": ModelIdentity(
        "GPT-6.1 Sol", source_url="https://openai.com/index/introducing-gpt-6-1-sol/"
    ),
    "GPT-6.1 Terra": ModelIdentity(
        "GPT-6.1 Terra",
        source_url="https://openai.com/index/introducing-gpt-6-1-terra",
    ),
    "GPT-6 Astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "GPT-5.6 Sol": ModelIdentity(
        "GPT-5.6 Sol", source_url="https://openai.com/index/gpt-5-6/"
    ),
    "Gemini 4 Neon": ModelIdentity(
        "Gemini 4 Neon", source_url=f"{_GEMINI_BLOG}/introducing-gemini-4-neon/"
    ),
    "Gemini 4 Carbon": ModelIdentity(
        "Gemini 4 Carbon",
        source_url=(
            "https://deepmind.google/blog/gemini-4-carbon-our-next-frontier-model/"
        ),
    ),
    "Gemini 4 Argon": ModelIdentity(
        "Gemini 4 Argon", source_url=f"{_GEMINI_BLOG}/gemini-4-argon/"
    ),
    "Gemini 4 Hydrogen": ModelIdentity(
        "Gemini 4 Hydrogen",
        source_url=f"{_GEMINI_BLOG}/introducing-gemini-4-hydrogen/",
    ),
    "Gemini 3.8 Flash": ModelIdentity(
        "Gemini 3.8 Flash", source_url=f"{_GEMINI_BLOG}/3-8-flash-and-3-8-flash-cyber/"
    ),
    "Gemini 3 Flash Preview": ModelIdentity(
        "Gemini 3 Flash",
        source_url=(
            "https://blog.google/products-and-platforms/products/gemini/gemini-3-flash/"
        ),
    ),
    "Gemini 3.1 Flash-Lite Preview": ModelIdentity(
        "Gemini 3.1 Flash-Lite", source_url=f"{_GEMINI_BLOG}/gemini-3-1-flash-lite/"
    ),
    "Claude Opus 5.5": ModelIdentity(
        "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
    ),
    "Claude Sonnet 5.5": ModelIdentity(
        "Claude Sonnet 5.5", source_url="https://www.anthropic.com/claude-sonnet-5-5"
    ),
    "Claude Haiku 5.5": ModelIdentity(
        "Claude Haiku 5.5", source_url="https://www.anthropic.com/claude-haiku-5-5"
    ),
}


def _score(task: dict[str, Any], name: str) -> tuple[Decimal, Decimal | None, date]:
    if task.get("taskVersion") != TASK_VERSION:
        raise ValueError(
            f"HFE {task.get('benchmarkTaskName')!r} for {name} is task version "
            f"{task.get('taskVersion')!r}; expected {TASK_VERSION}"
        )
    if task.get("displayType") != "PERCENTAGES":
        raise ValueError(f"HFE score for {name} is not a percentage")
    result = task.get("result") or {}
    numeric = result.get("numericResult") or {}
    try:
        value = Decimal(str(numeric["value"]))
    except (KeyError, ArithmeticError) as exc:
        raise ValueError(f"HFE score is missing or malformed: {name}") from exc
    if not value.is_finite() or not 0 <= value <= 1:
        raise ValueError(f"HFE score is out of range: {name}")
    interval = numeric.get("confidenceInterval")
    evaluated = datetime.fromisoformat(result["evaluationDate"].replace("Z", "+00:00"))
    return value, None if interval is None else Decimal(str(interval)), evaluated.date()


def parse_hfe(payload: dict[str, Any]) -> list[LeaderboardEntry]:
    """Parse Kaggle's HFE leaderboard, failing on any version or shape change."""
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("HFE leaderboard response has no rows")
    entries: list[LeaderboardEntry] = []
    for row in rows:
        name = (row.get("modelVersionName") or "").strip()
        config = (row.get("modelVersionConfigName") or "").strip()
        if not (name and config and len(name) <= 200):
            raise ValueError(f"HFE row has no model or configuration name: {row!r}")
        if row.get("candidateClass") != CANDIDATE_CLASS or row.get("agentName"):
            raise ValueError(f"HFE row {config!r} is not a model configuration")
        tasks = {
            task.get("benchmarkTaskName"): task for task in row.get("taskResults") or []
        }
        if set(tasks) != {OVERALL_TASK, SCORE_TASK}:
            raise ValueError(
                f"HFE row {config!r} reports tasks {sorted(map(str, tasks))}"
            )
        value, interval, evaluated = _score(tasks[SCORE_TASK], config)
        overall, _, _ = _score(tasks[OVERALL_TASK], config)
        if abs(overall - value) > Decimal("0.0005"):
            raise ValueError(f"HFE overall score differs from family pass^4: {config}")
        percent = (value * 100).quantize(Decimal("0.1"))
        margin = (
            ""
            if interval is None
            else f" (95% CI ±{(interval * 100).quantize(Decimal('0.1'))})"
        )
        entries.append(
            LeaderboardEntry(
                name,
                percent,
                f"configuration {config}, family pass^4 {percent}%{margin}",
                lab=family_lab(name),
                evaluated_on=evaluated,
            )
        )
    names = [entry.name for entry in entries]
    if duplicates := sorted({name for name in names if names.count(name) > 1}):
        raise ValueError(f"HFE lists {duplicates} more than once")
    check_entry_count(
        entries, "HFE leaderboard", MIN_EXPECTED_ENTRIES, MAX_EXPECTED_ENTRIES
    )
    return entries


def fetch_hfe(client: httpx.Client | None = None) -> list[LeaderboardEntry]:
    token = os.environ.get("KAGGLE_API_TOKEN")
    if not token:
        raise RuntimeError("KAGGLE_API_TOKEN is required")
    owned_client = client is None
    active_client = client or httpx.Client(timeout=httpx.Timeout(30, connect=5))
    try:
        response = active_client.post(
            KAGGLE_API_URL,
            json={"ownerSlug": OWNER_SLUG, "benchmarkSlug": BENCHMARK_SLUG},
            headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        return parse_hfe(response.json())
    finally:
        if owned_client:
            active_client.close()


BOARD = LiveLeaderboard(
    source="HFE",
    provider="hfe",
    url=HFE_URL,
    task_slug=TASK_SLUG,
    dataset_slug=DATASET_SLUG,
    metric=METRIC_NAME,
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    adopt_unmanaged=False,
    protocol=(
        "Kaggle HFE leaderboard, task version 1: share of four-prompt families "
        "whose four prompts are all answered correctly on four sampled rollouts "
        "each (16 draws), zero-shot, single turn, no tools; run by Google "
        "DeepMind and Kaggle."
    ),
)
