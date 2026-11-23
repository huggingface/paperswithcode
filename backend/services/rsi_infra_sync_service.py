"""Live board for the official RSI-Infra Bench leaderboard.

RSI-Infra Bench (AI4AI for Anything) measures how far a coding agent speeds up
real training code in a 10-hour budget without changing training results. Its
leaderboard page renders a static HTML table: each model, its harness, the
overall score and its speed-up on each of the eight tasks. The overall score
is an ECI-style fit over per-task log-speedup scores anchored at Claude Opus
5.5 = 40 and Kimi K3.1 Pro = 10, so the parser fails when the task set or the
anchors change.
"""

from __future__ import annotations

import html
import re
from decimal import Decimal

import httpx

from backend.services.leaderboard_model_matching_service import family_lab
from backend.services.leaderboard_sync_catalog import ModelIdentity
from backend.services.live_leaderboard_sync import (
    LeaderboardEntry,
    LiveLeaderboard,
    check_entry_count,
    fetch_text,
)

RSI_INFRA_URL = (
    "https://ai4ai-for-anything.github.io/blog/rsi-infra-bench/leaderboard/index.html"
)
TASK_SLUG = "auto-research"
DATASET_SLUG = "rsi-infra-bench"
METRIC_NAME = "Score"
TASKS = (
    "LLaVA",
    "YOCO",
    "NanoChat",
    "BAGEL SFT",
    "R3",
    "3DGS",
    "Slime GRPO",
    "Slime OPD",
)
ANCHORS = {"Claude Opus 5.5": Decimal("40.00"), "Kimi k3.1-pro": Decimal("10.00")}
MIN_EXPECTED_ENTRIES = 5
MAX_EXPECTED_ENTRIES = 100
MIN_SELECTED_ENTRIES = 5

HARNESSES = {
    "Antigravity CLI": "Antigravity CLI",
    "Claude Code": "Claude Code",
    "Codex": "Codex",
    "DSH": "DeepSeek Harness",
    "Qwen Code": "Qwen Code",
}

MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "Gemini 4 Neon": ModelIdentity(
        "Gemini 4 Neon",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/introducing-gemini-4-neon/"
        ),
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
    "Gemini 4 Hydrogen": ModelIdentity(
        "Gemini 4 Hydrogen",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/introducing-gemini-4-hydrogen/"
        ),
    ),
    "Gemini 4 Carbon": ModelIdentity(
        "Gemini 4 Carbon",
        source_url=(
            "https://deepmind.google/blog/gemini-4-carbon-our-next-frontier-model/"
        ),
    ),
    "GPT-6.2 Astra": ModelIdentity(
        "GPT-6.2 Astra",
        source_url="https://openai.com/index/introducing-gpt-6-2-astra-sol/",
    ),
    "GPT-6.2 Sol": ModelIdentity(
        "GPT-6.2 Sol",
        source_url="https://openai.com/index/introducing-gpt-6-2-astra-sol/",
    ),
    "GPT-6 Astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "MiniMax M3.1 Flash": ModelIdentity(
        "MiniMax-M3.1-Flash",
        source_url="https://www.minimax.io/blog/minimax-m31f",
        is_open=True,
    ),
    "Qwen4-Max": ModelIdentity(
        "Qwen4 Max", source_url="https://qwen.ai/blog?id=qwen4-max"
    ),
    "Step-5 Preview": ModelIdentity(
        "Step-5-Preview",
        source_url="https://huggingface.co/stepfun-ai/Step-5-Preview",
        is_open=True,
    ),
    "GLM-5.3": ModelIdentity(
        "GLM-5.3",
        source_url="https://z.ai/blog/glm-5.3",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3",
    ),
    "DeepSeek V4.1 Flash-1017": ModelIdentity(
        "DeepSeek-V4.1-Flash-1017", arxiv_id="2609.19969", is_open=True
    ),
    "Kimi k3.1-pro": ModelIdentity(
        "Kimi K3.1 Pro",
        source_url="https://www.kimi.com/blog/kimi-k3-1-pro",
        is_open=True,
    ),
    "Hy4": ModelIdentity(
        "Hy4",
        source_url=(
            "https://www.tencent.com/tencent-launches-hy4-joining-the-ranks-of-"
            "the-worlds-leading-open-source-ai-models/"
        ),
        is_open=True,
    ),
}

_TABLE = re.compile(r"<table id=board>(.*?)</table>", re.S)
_HEADER_TASK = re.compile(r"<th scope=col class=tk>.*?<span class=tl>([^<]*)</span>")
_ROW = re.compile(r"<tr class=m\d+>(.*?)</tr>", re.S)
_RANK = re.compile(r"<a class=badge[^>]*>([^<]*)</a>")
_NAME = re.compile(r"<span class=mfull>([^<]*)</span>")
_NOTE = re.compile(r"<span class=upd>([^<]*)</span>")
_HARNESS = re.compile(r"<span class=hn[^>]*>([^<]*)</span>")
_LAB = re.compile(r"<span class=mo>([^<·]*)")
_SCORE = re.compile(r"<span class=scv>([^<]*)</span>")
_SPEEDUP = re.compile(r"<td class='tk[^']*'[^>]*><a [^>]*>([\d.]+)<span class=x>")
_OTHER_JUDGE = re.compile(r"<em>([^<]*) were judged by the released judge")


def _match(pattern: re.Pattern[str], text: str) -> str | None:
    found = pattern.search(text)
    return html.unescape(found[1]).strip() if found else None


def parse_rsi_infra(text: str) -> list[LeaderboardEntry]:
    """Parse the leaderboard table, failing on any task, anchor or layout change."""
    if "RSI-Infra Bench</title>" not in text:
        raise ValueError("RSI-Infra Bench page no longer names the benchmark")
    table = _TABLE.search(text)
    if table is None:
        raise ValueError("RSI-Infra Bench leaderboard table not found")
    tasks = tuple(html.unescape(t) for t in _HEADER_TASK.findall(table[1]))
    if tasks != TASKS:
        raise ValueError(f"RSI-Infra Bench tasks changed: {tasks}")
    other_judge = set(re.split(r",\s*|\s+and\s+", _match(_OTHER_JUDGE, text) or ""))

    rows = _ROW.findall(table[1])
    entries: list[LeaderboardEntry] = []
    previous: Decimal | None = None
    for position, row in enumerate(rows, start=1):
        rank, name = _match(_RANK, row), _match(_NAME, row)
        if rank != str(position):
            raise ValueError(f"RSI-Infra Bench rank {rank!r} at row {position}")
        if not (name and len(name) <= 200):
            raise ValueError(f"RSI-Infra Bench rank {rank} has no name")
        harness = HARNESSES.get(_match(_HARNESS, row) or "")
        if harness is None:
            raise ValueError(
                f"RSI-Infra Bench harness {_match(_HARNESS, row)!r} is not "
                f"reviewed: {name}"
            )
        score = _match(_SCORE, row)
        try:
            value = Decimal(score or "")
        except ArithmeticError as exc:
            raise ValueError(f"RSI-Infra Bench score is malformed: {name}") from exc
        if not value.is_finite() or value < 0:
            raise ValueError(f"RSI-Infra Bench score is out of range: {name}")
        if previous is not None and value > previous:
            raise ValueError(f"RSI-Infra Bench score is out of rank order: {name}")
        previous = value
        if name in ANCHORS and value != ANCHORS[name]:
            raise ValueError(f"RSI-Infra Bench anchor {name} moved to {value}")
        speedups = _SPEEDUP.findall(row)
        if len(speedups) != len(TASKS):
            raise ValueError(
                f"RSI-Infra Bench row for {name} has {len(speedups)} task speed-ups"
            )
        notes = []
        if note := _match(_NOTE, row):
            notes.append(f"marked {note!r} on the board")
        if name in other_judge:
            notes.append("judged by the released judge on other 8-GPU Hopper machines")
        per_task = ", ".join(f"{task} {x}x" for task, x in zip(TASKS, speedups))
        entries.append(
            LeaderboardEntry(
                name,
                value,
                f"rank {rank} of {len(rows)}, score {score}, run in {harness}; "
                f"per-task speed-ups {per_task}"
                + "".join(f"; {note}" for note in notes),
                harness=harness,
                lab=_match(_LAB, row) or family_lab(name),
            )
        )
    missing = set(ANCHORS) - {entry.name for entry in entries}
    if missing:
        raise ValueError(f"RSI-Infra Bench anchors missing: {sorted(missing)}")
    keys = [(entry.name, entry.harness) for entry in entries]
    if duplicates := sorted({str(k) for k in keys if keys.count(k) > 1}):
        raise ValueError(f"RSI-Infra Bench lists {duplicates} twice")
    check_entry_count(
        entries, "RSI-Infra Bench board", MIN_EXPECTED_ENTRIES, MAX_EXPECTED_ENTRIES
    )
    return entries


def fetch_rsi_infra(client: httpx.Client | None = None) -> list[LeaderboardEntry]:
    return parse_rsi_infra(fetch_text(RSI_INFRA_URL, client))


BOARD = LiveLeaderboard(
    source="RSI-Infra Bench",
    provider="rsi-infra-bench",
    url=RSI_INFRA_URL,
    task_slug=TASK_SLUG,
    dataset_slug=DATASET_SLUG,
    metric=METRIC_NAME,
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    protocol=(
        "RSI-Infra Bench (preview, 8 training-code tasks on 1-4 Hopper GPUs, "
        "10-hour budget, one run per model and task): the speed-up is the "
        "original per-step time over the agent's, and a result that changes "
        "training outcomes counts as 1x; each task scores ln(speed-up) over "
        "ln(best speed-up on the task), and the overall score is an ECI-style "
        "fit over all task scores anchored at Claude Opus 5.5 = 40 and Kimi "
        "K3.1 Pro = 10."
    ),
)
