"""Live board for the official RSI-Exam leaderboard.

https://rsi-exam.ai/ renders its leaderboard as three static SVG panels (Full,
Public 35, Private 53). The PwC ``rsi-exam`` benchmark mirrors the Full panel:
every model's mean frozen normalised hidden-set score over all active tasks,
together with the coding-agent harness it ran in. Scores are only comparable
within one release and task set, so the parser fails when the release label
or the Full task count changes.
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

RSI_EXAM_URL = "https://rsi-exam.ai/"
TASK_SLUG = "auto-research"
DATASET_SLUG = "rsi-exam"
METRIC_NAME = "Normalized Score"
# A new release or task set rescales every score; a reviewer decides whether
# the managed rows move with it.
RELEASE = "RSI-Exam 0.1"
FULL_TASKS = 88
MIN_EXPECTED_ENTRIES = 10
MAX_EXPECTED_ENTRIES = 100
# Refuse to touch the managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 8

# The board's harness labels, by their lower-case form on the page.
HARNESSES = {
    "antigravity": "Antigravity",
    "claude code": "Claude Code",
    "codex": "Codex",
    "grok": "Grok",
    "kimi code": "Kimi Code",
    "musecode": "Muse Code",
    "qwen coder": "Qwen Code",
}

# Board names that carry no family prefix, by the start of the name.
_NAME_LABS = {
    "Fable ": "Anthropic",
    "Muse ": "Meta",
    "Opus ": "Anthropic",
    "Step ": "StepFun",
}

# Exact RSI-Exam row names are the trust boundary between a model and its
# introducing paper. Other names are matched automatically when the catalog
# names them unambiguously, and otherwise handed to the release radar.
MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "Opus 5.5": ModelIdentity(
        "Claude Opus 5.5", source_url="https://www.anthropic.com/claude-opus-5-5"
    ),
    "Opus 5": ModelIdentity(
        "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
    ),
    "Fable 5.1": ModelIdentity(
        "Claude Fable 5.1",
        source_url="https://www.anthropic.com/claude-fable-and-mythos-5-1",
    ),
    "GPT-6-astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "GPT-5.6-sol": ModelIdentity(
        "GPT-5.6 Sol", source_url="https://openai.com/index/gpt-5-6/"
    ),
    "GPT-5.5": ModelIdentity(
        "GPT-5.5", source_url="https://openai.com/index/introducing-gpt-5-5/"
    ),
    "Gemini 4 Argon": ModelIdentity(
        "Gemini 4 Argon",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-4-argon/"
        ),
    ),
    "Gemini 3.8 Flash": ModelIdentity(
        "Gemini 3.8 Flash",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/3-8-flash-and-3-8-flash-cyber/"
        ),
    ),
    "Gemini 3.7 Flash": ModelIdentity(
        "Gemini 3.7 Flash",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/introducing-gemini-3-7-flash/"
        ),
    ),
    "Qwen 4 Max": ModelIdentity(
        "Qwen4 Max", source_url="https://qwen.ai/blog?id=qwen4-max"
    ),
    # A dated API snapshot of Qwen3.8-Max, listed beside the release model.
    "Qwen3.8 Max-0902": ModelIdentity(
        "Qwen3.8 Max-0902", source_url="https://qwen.ai/blog?id=qwen3.8"
    ),
    "Qwen3.8 Max": ModelIdentity(
        "Qwen3.8 Max", source_url="https://qwen.ai/blog?id=qwen3.8"
    ),
    "Kimi K3.1 Pro": ModelIdentity(
        "Kimi K3.1 Pro", source_url="https://www.kimi.com/blog/kimi-k3-1-pro"
    ),
    "Kimi K3": ModelIdentity("Kimi K3", arxiv_id="2607.24653", is_open=True),
    "GLM 5.3": ModelIdentity(
        "GLM-5.3", source_url="https://z.ai/blog/glm-5.3", is_open=True
    ),
    "Muse Spark 1.3": ModelIdentity(
        "Muse Spark 1.3",
        source_url="https://research.meta.ai/blog/introducing-muse-spark-1-3",
    ),
    "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
    "Grok 4.6": ModelIdentity("Grok 4.6", source_url="https://x.ai/news/grok-4-6"),
    "Step 5 Preview": ModelIdentity(
        "Step 5 Preview",
        source_url="https://huggingface.co/stepfun-ai/Step-5-Preview",
        is_open=True,
    ),
    "DeepSeek V4 Pro": ModelIdentity(
        "DeepSeek V4 Pro", arxiv_id="2606.19348", is_open=True
    ),
}

_FULL_PANEL = re.compile(
    r'<div class="hlbwrap" id="lbpanel-full"[^>]*data-board="full"[^>]*>(.*?)</div>',
    re.S,
)
_FULL_TASKS = re.compile(r"over all (\d+) active tasks")
_ROW = re.compile(r'<g class="hlbrow"[^>]*>(.*?)</g>', re.S)


def _text(row: str, cls: str) -> str | None:
    match = re.search(rf'<text class="{cls}"[^>]*>([^<]*)</text>', row)
    return html.unescape(match[1]).strip() if match else None


def _name_lab(name: str) -> str:
    return next(
        (lab for prefix, lab in _NAME_LABS.items() if name.startswith(prefix)), ""
    )


def parse_rsi_exam(text: str) -> list[LeaderboardEntry]:
    """Parse the Full board, failing on any release or layout change."""
    if RELEASE not in text:
        raise ValueError(f"RSI-Exam page no longer names release {RELEASE!r}")
    panel = _FULL_PANEL.search(text)
    if panel is None:
        raise ValueError("RSI-Exam Full leaderboard panel not found")
    tasks = _FULL_TASKS.search(panel[1])
    if tasks is None or int(tasks[1]) != FULL_TASKS:
        found = tasks[1] if tasks else None
        raise ValueError(
            f"RSI-Exam Full board covers {found} tasks; expected {FULL_TASKS}"
        )

    entries: list[LeaderboardEntry] = []
    rows = _ROW.findall(panel[1])
    previous: Decimal | None = None
    for position, row in enumerate(rows, start=1):
        rank, name = _text(row, "hlbrank"), _text(row, "hlbmodel")
        sub, score = _text(row, "hlbsub"), _text(row, "hlbval")
        if rank != str(position):
            raise ValueError(f"RSI-Exam Full board rank {rank!r} at row {position}")
        if not (name and len(name) <= 200):
            raise ValueError(f"RSI-Exam Full board rank {rank} has no name")
        harness_label, _, effort = (sub or "").partition(" · ")
        harness = HARNESSES.get(harness_label.strip())
        if harness is None or not effort.strip():
            raise ValueError(f"RSI-Exam harness {sub!r} is not reviewed: {name}")
        try:
            value = Decimal(score or "")
        except ArithmeticError as exc:
            raise ValueError(f"RSI-Exam score is malformed: {name}") from exc
        if not value.is_finite() or not -1 <= value <= 1:
            raise ValueError(f"RSI-Exam score is out of range: {name}")
        if previous is not None and value > previous:
            raise ValueError(f"RSI-Exam score is out of rank order: {name}")
        previous = value
        entries.append(
            LeaderboardEntry(
                name,
                value,
                f"rank {rank} of {len(rows)} on the {RELEASE} Full board "
                f"({FULL_TASKS} tasks), normalised score {score}, run in "
                f"{sub}",
                harness=harness,
                lab=_name_lab(name) or family_lab(name),
            )
        )
    keys = [(entry.name, entry.harness) for entry in entries]
    if duplicates := sorted({str(k) for k in keys if keys.count(k) > 1}):
        raise ValueError(f"RSI-Exam lists {duplicates} twice")
    check_entry_count(
        entries, "RSI-Exam Full board", MIN_EXPECTED_ENTRIES, MAX_EXPECTED_ENTRIES
    )
    return entries


def fetch_rsi_exam(client: httpx.Client | None = None) -> list[LeaderboardEntry]:
    return parse_rsi_exam(fetch_text(RSI_EXAM_URL, client))


BOARD = LiveLeaderboard(
    source="RSI-Exam",
    provider="rsi-exam",
    url=RSI_EXAM_URL,
    task_slug=TASK_SLUG,
    dataset_slug=DATASET_SLUG,
    metric=METRIC_NAME,
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    protocol=(
        f"{RELEASE} Full board: equal-weight mean over {FULL_TASKS} tasks "
        "(35 public, 53 private) of the frozen normalised hidden-set score, "
        "where the inherited starter is 0, a frontier-calibrated reference "
        "0.6 and the upper bound 1; one rollout per model per task in a "
        "sealed container with up to 12 hours to improve the starter."
    ),
)
