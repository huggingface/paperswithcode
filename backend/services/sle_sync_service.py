"""Live boards for the official Science's Last Exam (SLE) leaderboard.

https://sciences-last-exam.org/leaderboard renders from a plain-data
``window.SLE = {leaderboard: {...}}`` object in a content-hashed
``assets/data.<hash>.js`` bundle that the page loads. The object lists each
evaluated model (with its agent harness and reasoning effort) and its score
on every assessment. Five assessments and the official composite are separate
PwC benchmarks on ``scientific-reasoning``; each is its own board here.

End-to-end research scores 0 for every model and has no board of its own; it
still counts in the composite, which is the equal-weight mean of six
assessments. A score the site marks with a status (``"in progress"``) is
provisional: that row is skipped, and so is the model's composite.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

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

SLE_LEADERBOARD_URL = "https://sciences-last-exam.org/leaderboard"
SLE_SITE_URL = "https://sciences-last-exam.org/"
TASK_SLUG = "scientific-reasoning"
# Hypothesis Discovery runs in the benchmark's own research harness, not in
# the model's coding-agent harness.
HYPOTHESIS_HARNESS = "DiscoveryRSI"
MIN_EXPECTED_MODELS = 3
MAX_EXPECTED_MODELS = 60
# Refuse to touch a managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 3

_DATA_BUNDLE = re.compile(r"""["'](?:\./|/)?(assets/data\.[0-9a-f]+\.js)["']""")
_LEADERBOARD_KEY = re.compile(r"""\bleaderboard\s*:\s*(?=\{)""")
# The composite averages exactly these assessments; a new member (Wet-lab
# Execution, say) restates every composite and needs a reviewer decision.
COMPOSITE_MEMBERS = ("pp", "eo", "sc", "so", "hd", "e2e")


# (capability id, label, PwC benchmark slug, PwC metric, SLE metric, protocol)
BOARD_SPECS = (
    (
        "all",
        "composite",
        "science-s-last-exam-sle",
        "Composite Score",
        "Composite score",
        "SLE v1 composite: equal-weight mean of six assessments on a 0-100 "
        "scale (Hypothesis Discovery, Protocol Planning, Scientific Computing, "
        "Scientific Software Operation, Experiment Observation and End-to-end "
        "research, which scores 0 for every listed model); models with a "
        "provisional assessment are left out.",
    ),
    (
        "hd",
        "Hypothesis Discovery",
        "sle-hypothesis-discovery",
        "Inspire Rate",
        "Inspire rate",
        "SLE v1 Hypothesis Discovery (5 tasks) in the DiscoveryRSI research "
        "harness: percentage of hypothesis versions that anticipate research "
        "published after the model's knowledge cutoff; runs still in progress "
        "are left out.",
    ),
    (
        "pp",
        "Protocol Planning",
        "sle-protocol-planning",
        "Mean score",
        "Mean score",
        "SLE v1 Protocol Planning (40 tasks): mean task reward x 100.",
    ),
    (
        "sc",
        "Scientific Computing",
        "sle-scientific-computing",
        "Pass Rate",
        "Pass rate",
        "SLE v1 Scientific Computing (23 tasks): percentage of tasks passing "
        "every scientific check.",
    ),
    (
        "so",
        "Scientific Software Operation",
        "sle-scientific-software-operation",
        "Pass Rate",
        "Pass rate",
        "SLE v1 Scientific Software Operation (14 tasks): percentage of tasks "
        "receiving full credit.",
    ),
    (
        "eo",
        "Experiment Observation",
        "sle-experiment-observation",
        "Pass Rate",
        "Pass rate",
        "SLE v1 Experiment Observation (30 tasks): percentage of tasks with "
        "every requested field correct.",
    ),
)

# Exact SLE model names are the trust boundary between a leaderboard row and
# its introducing paper. Other names are matched automatically when the
# catalog names them unambiguously, and otherwise handed to the release radar.
MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "GPT-6.1 Sol": ModelIdentity(
        "GPT-6.1 Sol", source_url="https://openai.com/index/introducing-gpt-6-1-sol/"
    ),
    "Claude Opus 5": ModelIdentity(
        "Claude Opus 5", source_url="https://www.anthropic.com/news/claude-opus-5"
    ),
    "Gemini 4 Argon": ModelIdentity(
        "Gemini 4 Argon",
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-4-argon/"
        ),
    ),
    "DeepSeek V4.1 Flash": ModelIdentity(
        "DeepSeek-V4.1-Flash",
        arxiv_id="2609.19969",
        is_open=True,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash",
    ),
    "Qwen3.8 Max": ModelIdentity(
        "Qwen3.8-Max",
        source_url="https://qwen.ai/blog?id=qwen3.8",
        is_open=True,
        hf_model_url="https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B",
    ),
    "GLM-5.3 Flash": ModelIdentity(
        "GLM-5.3-Flash",
        source_url="https://z.ai/blog/glm-5.3-flash",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3-Flash",
    ),
    "Kimi K3.1 Pro": ModelIdentity(
        "Kimi K3.1 Pro",
        source_url="https://www.kimi.com/blog/kimi-k3-1-pro",
        is_open=True,
    ),
    "MiniMax-M3": ModelIdentity(
        "MiniMax-M3",
        source_url="https://www.minimax.io/blog/minimax-m3",
        is_open=True,
        hf_model_url="https://huggingface.co/MiniMaxAI/MiniMax-M3",
    ),
    "MiMo-V2.6-Pro": ModelIdentity(
        "MiMo-V2.6-Pro", arxiv_id="2610.11959", is_open=True
    ),
}


def _boards() -> dict[str, LiveLeaderboard]:
    return {
        capability: LiveLeaderboard(
            source="Science's Last Exam",
            provider="sle",
            url=SLE_LEADERBOARD_URL,
            task_slug=TASK_SLUG,
            dataset_slug=dataset_slug,
            metric=metric,
            identities=MODEL_IDENTITIES,
            min_selected=MIN_SELECTED_ENTRIES,
            protocol=protocol,
        )
        for capability, _, dataset_slug, metric, _, protocol in BOARD_SPECS
    }


BOARDS = _boards()


def data_bundle_url(page: str) -> str:
    """Return the hashed data bundle the leaderboard page loads."""
    bundles = set(_DATA_BUNDLE.findall(page))
    if len(bundles) != 1:
        raise ValueError(f"SLE leaderboard page loads {len(bundles)} data bundles")
    return SLE_SITE_URL + bundles.pop()


def _score(value: object, what: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"SLE {what} is malformed")
    if not 0 <= value <= 100:
        raise ValueError(f"SLE {what} is outside 0-100")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_sle(text: str) -> list[tuple[LiveLeaderboard, list[LeaderboardEntry]]]:
    """Split the leaderboard object into one entry list per board.

    Fails on any change to the assessments, their metrics, or the composite
    definition, because those change what a score means.
    """
    match = _LEADERBOARD_KEY.search(text)
    if match is None:
        raise ValueError("SLE data bundle has no leaderboard object")
    board = js_literal(text, match.end(), "SLE leaderboard")
    models = board.get("models") if isinstance(board, dict) else None
    capabilities = board.get("capabilities") if isinstance(board, dict) else None
    results = board.get("results") if isinstance(board, dict) else None
    updated = board.get("updated") if isinstance(board, dict) else None
    if not (
        isinstance(models, list)
        and isinstance(capabilities, list)
        and isinstance(results, dict)
        and isinstance(updated, str)
    ):
        raise ValueError("SLE leaderboard layout changed")
    members = (board.get("aggregation") or {}).get("members")
    if tuple(members or ()) != COMPOSITE_MEMBERS:
        raise ValueError(f"SLE composite members changed: {members!r}")
    metrics = {
        item.get("id"): item.get("metric")
        for item in capabilities
        if isinstance(item, dict)
    }
    for capability, label, _, _, upstream_metric, _ in BOARD_SPECS:
        if metrics.get(capability) != upstream_metric:
            raise ValueError(
                f"SLE {label} metric is {metrics.get(capability)!r}; "
                f"expected {upstream_metric!r}"
            )
        if not isinstance(results.get(capability), dict):
            raise ValueError(f"SLE {label} results are missing")

    roster: dict[str, tuple[str, str, str]] = {}
    for model in models:
        key = model.get("id") if isinstance(model, dict) else None
        name = model.get("name") if isinstance(model, dict) else None
        harness = model.get("harness") if isinstance(model, dict) else None
        if not (
            isinstance(key, str)
            and isinstance(name, str)
            and name.strip(" *")
            and len(name) <= 200
            and isinstance(harness, str)
            and harness.strip()
        ):
            raise ValueError(f"SLE model row is malformed: {model!r}")
        # A trailing asterisk flags a provisional composite on the site.
        label = name.strip().rstrip("*").strip()
        if key in roster or label in {entry[0] for entry in roster.values()}:
            raise ValueError(f"SLE lists {label} twice")
        roster[key] = (label, harness.strip(), str(model.get("setting") or "default"))
    if not MIN_EXPECTED_MODELS <= len(roster) <= MAX_EXPECTED_MODELS:
        raise ValueError(
            f"SLE leaderboard has {len(roster)} models; expected "
            f"{MIN_EXPECTED_MODELS}-{MAX_EXPECTED_MODELS}"
        )

    # A model with any provisional assessment has a provisional composite.
    provisional = {
        key
        for capability in COMPOSITE_MEMBERS
        for key, result in (results.get(capability) or {}).items()
        if isinstance(result, dict) and result.get("status")
    }
    boards: list[tuple[LiveLeaderboard, list[LeaderboardEntry]]] = []
    for capability, label, _, _, _, _ in BOARD_SPECS:
        entries: list[LeaderboardEntry] = []
        for key, result in results[capability].items():
            if key not in roster:
                raise ValueError(f"SLE {label} scores an unlisted model: {key}")
            if not isinstance(result, dict) or result.get("score") is None:
                continue
            if result.get("status") or (capability == "all" and key in provisional):
                continue
            name, harness, effort = roster[key]
            value = _score(result["score"], f"{label} score of {name}")
            if capability == "hd":
                harness = HYPOTHESIS_HARNESS
            entries.append(
                LeaderboardEntry(
                    name,
                    value,
                    f"{label} {value} with the {harness} harness at {effort} "
                    f"reasoning effort, board updated {updated}",
                    harness=harness,
                    lab=family_lab(name),
                )
            )
        check_entry_count(
            entries, f"SLE {label} board", MIN_SELECTED_ENTRIES, MAX_EXPECTED_MODELS
        )
        boards.append((BOARDS[capability], entries))
    return boards


def fetch_sle_boards(
    client: httpx.Client | None = None,
) -> list[tuple[LiveLeaderboard, list[LeaderboardEntry]]]:
    """Fetch the leaderboard page, then the data bundle it loads."""
    page = fetch_text(SLE_LEADERBOARD_URL, client)
    return parse_sle(fetch_text(data_bundle_url(page), client))
