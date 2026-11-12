"""Live board for Benchmark Heaven's official JevBench API leaderboard.

https://benchmarkheaven.com/api/jevbench/latest publishes every measured
decision system with its four axes (Intelligence, Calibration, Speed, Cost),
its Composite Score and its rank on the open-weights and API boards. The PwC
``jevbench`` benchmark mirrors the official API board (benchmarkheaven.com/
jev-models/api): ranked API offerings scored under the current method, by
Composite Score. Preliminary, unranked, wrapper and listed-only rows carry no
API-board rank and are skipped, and the parser fails when the method changes,
because JevBench scores are not comparable across method versions.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlsplit

import httpx

from backend.services.leaderboard_model_matching_service import family_lab
from backend.services.leaderboard_sync_catalog import ModelIdentity
from backend.services.live_leaderboard_sync import (
    LeaderboardEntry,
    LiveLeaderboard,
    check_entry_count,
    fetch_text,
)

JEVBENCH_API_URL = "https://benchmarkheaven.com/api/jevbench/latest"
JEVBENCH_BOARD_URL = "https://benchmarkheaven.com/jev-models/api"
TASK_SLUG = "decision-making"
DATASET_SLUG = "jevbench"
METRIC_NAME = "Composite Score"
SCHEMA_VERSION = 2
# A new method restates every score on another scale; a reviewer decides
# whether the managed rows move with it.
METHOD = "v1.7"
MIN_EXPECTED_ENTRIES = 20
MAX_EXPECTED_ENTRIES = 300
# Refuse to touch the managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 4

# Vendors by the host of a system's source URL; the upstream names often end
# in the vendor, which the row name then leaves out ("Drex Max (Nace AI)").
_HOST_LABS = {
    "alphanimble.com": "AlphaNimble",
    "attest.engineering": "Attest",
    "bespokelabs.ai": "Bespoke Labs",
    "celeris.ai": "Celeris",
    "decisionnode.com": "DecisionNode",
    "fastino.ai": "Fastino",
    "hyland.com": "Hyland",
    "launchables.ai": "Launchables",
    "levanto.ai": "Levanto Labs",
    "liquid.ai": "Liquid AI",
    "microsoft.com": "Microsoft",
    "milliseconds.ai": "milliseconds.ai",
    "nace.ai": "Nace AI",
    "scaledown.ai": "ScaleDown",
    "singularitycompute.com": "Singularity Compute",
    "sqwish.ai": "Sqwish",
    "strike-ai.eu": "Strike AI",
    "subq.ai": "SubQ",
    "surd.ai": "SurdAI",
    "typesafe.ai": "TypeSafe AI",
    "vansa.org": "Vansa",
}

# Vendors of systems whose source URL is a third-party host (OpenRouter, a
# Hugging Face repo) or missing, by the start of the row name.
_NAME_LABS = {
    "Amos ": "Scira",
    "Fastino ": "Fastino",
    "Mercury Decide": "Inception",
}

_GPT_6 = "https://openai.com/index/introducing-gpt-6-sol-and-luna/"

# Exact JevBench row names are the trust boundary between a system and its
# introducing paper. Other names are matched automatically when the catalog
# names them unambiguously, and otherwise handed to the release radar.
MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    # The Drex technical report; the model-card page was merged into it.
    "Drex Max": ModelIdentity(
        "Drex Max",
        arxiv_id="2611.07854",
        is_open=True,
        hf_model_url="https://huggingface.co/nace-ai/drex-max-v1",
    ),
    # JevBench measures general LLMs as decision models through their chat
    # API; each keeps its best reasoning setting on the board.
    "GPT-6 Luna (low reasoning effort)": ModelIdentity("GPT-6 Luna", source_url=_GPT_6),
    "GPT-6 Luna (default medium reasoning effort)": ModelIdentity(
        "GPT-6 Luna", source_url=_GPT_6
    ),
    "GPT-5.6 Luna (low reasoning effort)": ModelIdentity(
        "GPT-5.6 Luna", source_url="https://openai.com/index/gpt-5-6/"
    ),
    "Gemini 3.1 Flash-Lite": ModelIdentity(
        "Gemini 3.1 Flash-Lite",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-3-1-flash-lite/"
        ),
    ),
    "Qwen3.8 27B (Chutes TEE)": ModelIdentity(
        "Qwen3.8-27B",
        source_url="https://huggingface.co/Qwen/Qwen3.8-27B",
        is_open=True,
        hf_model_url="https://huggingface.co/Qwen/Qwen3.8-27B",
    ),
    "DeepSeek V4.1 Flash (thinking default)": ModelIdentity(
        "DeepSeek V4.1 Flash", arxiv_id="2609.19969", is_open=True
    ),
}


def _host_lab(url: object) -> str:
    host = (urlsplit(url).hostname or "") if isinstance(url, str) else ""
    return next(
        (
            lab
            for suffix, lab in _HOST_LABS.items()
            if host == suffix or host.endswith(f".{suffix}")
        ),
        "",
    )


def _name_lab(name: str) -> str:
    return next(
        (lab for prefix, lab in _NAME_LABS.items() if name.startswith(prefix)), ""
    )


def _axis(system: dict, name: str) -> str:
    value = (system.get("axes") or {}).get(name)
    return "n/a" if value is None else f"{value:.1f}"


def parse_jevbench(text: str) -> list[LeaderboardEntry]:
    """Parse the official API board, failing on any method or layout change."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("JevBench results are not JSON") from exc
    if not isinstance(payload, dict) or payload.get("benchmark") != "JevBench":
        raise ValueError("JevBench results layout changed")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"JevBench schema {payload.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION}"
        )
    method = (payload.get("method") or {}).get("label")
    if method != METHOD:
        raise ValueError(f"JevBench method is {method!r}; expected {METHOD!r}")
    release = payload.get("latest_release")
    systems = payload.get("systems")
    if not isinstance(release, str) or not isinstance(systems, list):
        raise ValueError("JevBench results layout changed")

    board = [
        system
        for system in systems
        if isinstance(system, dict) and system.get("api_board_rank") is not None
    ]
    board.sort(key=lambda system: system["api_board_rank"])
    ranks = [system["api_board_rank"] for system in board]
    if ranks != list(range(1, len(board) + 1)):
        raise ValueError("JevBench API-board ranks are not 1..n")

    entries: list[LeaderboardEntry] = []
    previous: float | None = None
    for system in board:
        name, score = system.get("name"), system.get("composite_score")
        rank = system["api_board_rank"]
        if not (isinstance(name, str) and name.strip() and len(name) <= 200):
            raise ValueError(f"JevBench API-board rank {rank} has no name")
        if (
            system.get("ranked") is not True
            or system.get("listing") != "ranked"
            or system.get("method") != METHOD
        ):
            raise ValueError(f"JevBench ranks an unranked or stale row: {name}")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(f"JevBench composite is malformed: {name}")
        if not 0 <= score <= 100 or (previous is not None and score > previous):
            raise ValueError(f"JevBench composite is out of rank order: {name}")
        previous = score

        lab = _host_lab(system.get("source_url"))
        label = name.strip()
        # Only a whole trailing "(Lab)" is the vendor, never the end of a
        # larger parenthetical such as "(hosted by Foo (Lab))".
        stripped = label.removesuffix(f" ({lab})") if lab else label
        if stripped != label and stripped.count("(") == stripped.count(")"):
            label = stripped
        value = Decimal(str(score)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        measured_on = (system.get("draw") or {}).get("measured_on")
        entries.append(
            LeaderboardEntry(
                label,
                value,
                f"rank {rank} of {len(board)} on the API board of release "
                f"{release}, Composite Score {value} (Intelligence "
                f"{_axis(system, 'intelligence')}, Calibration "
                f"{_axis(system, 'calibration')}, Speed {_axis(system, 'speed')}, "
                f"Cost {_axis(system, 'cost')}), measured in "
                f"{system.get('measured_in')}",
                lab=lab or _name_lab(label) or family_lab(label),
                evaluated_on=(
                    date.fromisoformat(measured_on)
                    if isinstance(measured_on, str)
                    else None
                ),
            )
        )
    names = [entry.name for entry in entries]
    if duplicates := sorted({n for n in names if names.count(n) > 1}):
        raise ValueError(f"JevBench lists {duplicates} twice")
    check_entry_count(
        entries, "JevBench API board", MIN_EXPECTED_ENTRIES, MAX_EXPECTED_ENTRIES
    )
    return entries


def fetch_jevbench(client: httpx.Client | None = None) -> list[LeaderboardEntry]:
    return parse_jevbench(fetch_text(JEVBENCH_API_URL, client))


BOARD = LiveLeaderboard(
    source="Benchmark Heaven JevBench",
    provider="jevbench",
    url=JEVBENCH_BOARD_URL,
    task_slug=TASK_SLUG,
    dataset_slug=DATASET_SLUG,
    metric=METRIC_NAME,
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    protocol=(
        f"JevBench method {METHOD}, official API board (hosted offerings): "
        "Composite Score is the equal-weight (25:25:25:25) harmonic mean of "
        "Intelligence, Calibration, Speed and Cost on 0-100 axes, with squared "
        "penalties below the axis floors, measured by Benchmark Heaven on "
        "typed decision items; preliminary and unranked rows are left out."
    ),
)
