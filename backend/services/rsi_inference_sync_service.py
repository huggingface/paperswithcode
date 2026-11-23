"""Live boards for the official RSI-Inference Bench leaderboard.

Apple's RSI-Inference Bench publishes its leaderboard as
``docs/leaderboard.html`` in the ``apple-aiml-research/ml-rsi-inference-bench``
repository; the page renders from a plain-data ``window.RSI_LEADERBOARD``
object. Three PwC benchmarks on ``auto-research`` mirror it: the joint
category-weighted Bradley-Terry rating on the Elo scale, the Day-0 Model
Support track (pass@1) and the Inference Optimization and Regression Fix
track (geometric-mean speed-up). Ratings are only comparable within one
rating method and task release, so the parser fails when either changes.
A row the board marks incomplete is provisional and skipped.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from backend.services.leaderboard_model_matching_service import family_lab
from backend.services.leaderboard_sync_catalog import ModelIdentity
from backend.services.live_leaderboard_sync import (
    LeaderboardEntry,
    LiveLeaderboard,
    check_entry_count,
    fetch_text,
    js_literal,
)

RSI_INFERENCE_URL = (
    "https://htmlpreview.github.io/?https://github.com/apple-aiml-research/"
    "ml-rsi-inference-bench/blob/main/docs/leaderboard.html"
)
RSI_INFERENCE_DATA_URL = (
    "https://raw.githubusercontent.com/apple-aiml-research/"
    "ml-rsi-inference-bench/main/docs/leaderboard.html"
)
TASK_SLUG = "auto-research"
SCHEMA = "rsi-inference-leaderboard/1"
RATING_METHOD = "weighted-bt-elo-v2"
RELEASE_TASKS = 37
TRACK_TASKS = {"model_support": 10, "optimization": 27}
MIN_EXPECTED_ENTRIES = 5
MAX_EXPECTED_ENTRIES = 100
MIN_SELECTED_ENTRIES = 5

_NAME_LABS = {
    "Fable-": "Anthropic",
    "Opus-": "Anthropic",
    "Sonnet-": "Anthropic",
}

MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "Sonnet-5.5": ModelIdentity(
        "Claude Sonnet 5.5", source_url="https://www.anthropic.com/claude-sonnet-5-5"
    ),
    "Opus-5.5": ModelIdentity(
        "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
    ),
    "Fable-5.1": ModelIdentity(
        "Claude Fable 5.1",
        source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
    ),
    "Opus-5": ModelIdentity(
        "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
    ),
    "Opus-4.8": ModelIdentity(
        "Claude Opus 4.8", source_url="https://www.anthropic.com/news/claude-opus-4-8"
    ),
    "GPT-6.1-Sol": ModelIdentity(
        "GPT-6.1 Sol", source_url="https://openai.com/index/introducing-gpt-6-1-sol/"
    ),
    "GPT-6-Astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "GPT-6-Sol": ModelIdentity(
        "GPT-6 Sol",
        source_url="https://openai.com/index/introducing-gpt-6-sol-and-luna/",
    ),
    "Gemini-4-Argon": ModelIdentity(
        "Gemini 4 Argon",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-4-argon/"
        ),
    ),
    "Gemini-3.8-Flash": ModelIdentity(
        "Gemini 3.8 Flash",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/3-8-flash-and-3-8-flash-cyber/"
        ),
    ),
    "Gemini-3.7-Flash": ModelIdentity(
        "Gemini 3.7 Flash",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/introducing-gemini-3-7-flash/"
        ),
    ),
    "DeepSeek-V4.1-Flash-1017": ModelIdentity(
        "DeepSeek-V4.1-Flash-1017", arxiv_id="2609.19969", is_open=True
    ),
    "DeepSeek-V4.1-Flash": ModelIdentity(
        "DeepSeek-V4.1-Flash", arxiv_id="2609.19969", is_open=True
    ),
    "MiniMax-M3.1-Flash": ModelIdentity(
        "MiniMax-M3.1-Flash",
        source_url="https://www.minimax.io/blog/minimax-m31f",
        is_open=True,
    ),
    "GLM-5.3": ModelIdentity(
        "GLM-5.3",
        source_url="https://z.ai/blog/glm-5.3",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3",
    ),
}

_PROTOCOL_HEAD = (
    f"RSI-Inference Bench ({RELEASE_TASKS} tasks on vLLM and SGLang, H100 and "
    "B200, 8-hour agent budget, offline)"
)

RATING_BOARD = LiveLeaderboard(
    source="RSI-Inference Bench",
    provider="rsi-inference-bench",
    url=RSI_INFERENCE_URL,
    task_slug=TASK_SLUG,
    dataset_slug="rsi-inference-bench",
    metric="Elo",
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    protocol=(
        f"{_PROTOCOL_HEAD} joint rating: category-weighted Bradley-Terry "
        "rating on the Elo scale (mean 1500) over pairwise task comparisons, "
        "weighting model support 0.25, throughput optimization 0.5 and "
        "regression fixes 0.25."
    ),
)
MODEL_SUPPORT_BOARD = LiveLeaderboard(
    source="RSI-Inference Bench Model Support",
    provider="rsi-inference-bench",
    url=RSI_INFERENCE_URL,
    task_slug=TASK_SLUG,
    dataset_slug="rsi-inference-bench-model-support",
    metric="Pass@1",
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    protocol=(
        f"{_PROTOCOL_HEAD} Day-0 Model Support track: pass@1 in percent over "
        f"{TRACK_TASKS['model_support']} tasks, full passes over attempts "
        "averaged over tasks, where a partial pass counts as a failure; the "
        "board breaks ties by the share of hidden tests passed."
    ),
)
OPTIMIZATION_BOARD = LiveLeaderboard(
    source="RSI-Inference Bench Optimization",
    provider="rsi-inference-bench",
    url=RSI_INFERENCE_URL,
    task_slug=TASK_SLUG,
    dataset_slug="rsi-inference-bench-optimization",
    metric="Speedup",
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    protocol=(
        f"{_PROTOCOL_HEAD} Inference Optimization and Regression Fix track: "
        f"geometric mean over {TRACK_TASKS['optimization']} tasks (20 "
        "throughput optimization, 7 regression) of the speed-up against each "
        "task's baseline; a result failing its correctness check counts as "
        "1.00x."
    ),
)
BOARDS = (RATING_BOARD, MODEL_SUPPORT_BOARD, OPTIMIZATION_BOARD)

_DATA_ROOT = "window.RSI_LEADERBOARD"


def _lab(name: str) -> str:
    return next(
        (lab for prefix, lab in _NAME_LABS.items() if name.startswith(prefix)),
        family_lab(name),
    )


def _check_release(data: dict[str, Any]) -> None:
    if data.get("schema") != SCHEMA:
        raise ValueError(f"RSI-Inference schema changed: {data.get('schema')!r}")
    method = (data.get("rating") or {}).get("method")
    if method != RATING_METHOD:
        raise ValueError(f"RSI-Inference rating method changed: {method!r}")
    tasks = (data.get("release") or {}).get("tasks")
    if tasks != RELEASE_TASKS:
        raise ValueError(f"RSI-Inference release has {tasks} tasks; expected 37")
    released = {
        track.get("id"): track.get("tasks_released") for track in data.get("tracks", [])
    }
    if released != TRACK_TASKS:
        raise ValueError(f"RSI-Inference tracks changed: {released}")


def _entries(
    rows: list[dict[str, Any]],
    what: str,
    score: str,
    scale: Decimal,
    describe: str,
) -> list[LeaderboardEntry]:
    entries: list[LeaderboardEntry] = []
    names: set[str] = set()
    previous: Decimal | None = None
    for position, row in enumerate(rows, start=1):
        name = row.get("agent")
        if not (isinstance(name, str) and name and len(name) <= 200):
            raise ValueError(f"RSI-Inference {what} row {position} has no agent")
        if name in names:
            raise ValueError(f"RSI-Inference {what} lists {name} twice")
        names.add(name)
        raw = row.get(score)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ValueError(f"RSI-Inference {what} {score} is malformed: {name}")
        listed = Decimal(str(raw))
        if previous is not None and listed > previous:
            raise ValueError(f"RSI-Inference {what} is out of rank order: {name}")
        previous = listed
        if not row.get("complete"):
            continue
        entries.append(
            LeaderboardEntry(
                name,
                (listed * scale).normalize(),
                f"rank {row.get('rank')} of {len(rows)} on the {what}, "
                f"{describe} {listed}",
                lab=_lab(name),
            )
        )
    check_entry_count(
        entries, f"RSI-Inference {what}", MIN_EXPECTED_ENTRIES, MAX_EXPECTED_ENTRIES
    )
    return entries


def parse_rsi_inference(
    text: str,
) -> list[tuple[LiveLeaderboard, list[LeaderboardEntry]]]:
    """Parse the three boards, failing on any rating, release or layout change."""
    start = text.find(_DATA_ROOT)
    if start < 0:
        raise ValueError("RSI-Inference page no longer defines RSI_LEADERBOARD")
    data = js_literal(text, text.index("{", start), "RSI-Inference leaderboard")
    _check_release(data)
    joint = data.get("joint") or []
    for position, row in enumerate(joint, start=1):
        if row.get("rank") != position:
            raise ValueError(
                f"RSI-Inference joint rank {row.get('rank')!r} at row {position}"
            )
    return [
        (
            RATING_BOARD,
            _entries(joint, "joint board", "rating", Decimal(1), "rating"),
        ),
        (
            MODEL_SUPPORT_BOARD,
            _entries(
                data.get("model_support") or [],
                "Model Support track",
                "pass_at_1",
                Decimal(100),
                "pass@1",
            ),
        ),
        (
            OPTIMIZATION_BOARD,
            _entries(
                data.get("optimization") or [],
                "Optimization track",
                "speedup",
                Decimal(1),
                "geometric-mean speed-up",
            ),
        ),
    ]


def fetch_rsi_inference_boards(
    client: httpx.Client | None = None,
) -> list[tuple[LiveLeaderboard, list[LeaderboardEntry]]]:
    return parse_rsi_inference(fetch_text(RSI_INFERENCE_DATA_URL, client))
