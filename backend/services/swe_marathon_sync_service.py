"""Live board for the official SWE-Marathon v1.1 leaderboard (Abundant AI).

swe-marathon.org renders its leaderboard client-side. The page's hashed
script bundle embeds the v1.1 results as ``{version:`v1.1`,tasks:JSON.parse(`...`)}``:
per task, one config per agent, model and reasoning effort, each with its
trials and their 0/1 rewards. The site's pass@1 is the share of a config's
trials with reward 1 over all tasks; the parser computes the same from the
trials, keeps only complete runs (every task, the full trial count), and
publishes each model's best effort per agent through the shared
``LiveLeaderboardSyncService``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urljoin

import httpx

from backend.services.leaderboard_model_matching_service import family_lab
from backend.services.leaderboard_sync_catalog import ModelIdentity
from backend.services.live_leaderboard_sync import (
    LeaderboardEntry,
    LiveLeaderboard,
    fetch_text,
)

SWE_MARATHON_URL = "https://www.swe-marathon.org/"
TASK_SLUG = "long-horizon-agents"
DATASET_SLUG = "swe-marathon"
METRIC_NAME = "Resolution Rate"
VERSION = "v1.1"
MIN_EXPECTED_ENTRIES = 10
MAX_EXPECTED_ENTRIES = 300
# Refuse to touch the managed leaderboard when the reviewed subset collapses.
MIN_SELECTED_ENTRIES = 15
# The site treats a config without a reasoning effort as max.
DEFAULT_EFFORT = "max"
# Tie-break between efforts of one model with the same pass rate.
_EFFORT_ORDER = ("max", "xhigh", "high", "medium", "low", "minimal", "none")
# Labs for the canonical model prefixes whose model names name no family.
_PREFIX_LABS = {"meta": "Meta"}

_BUNDLE = re.compile(r'<script[^>]+src="(/assets/index-[\w-]+\.js)"')
_RESULTS = re.compile(r"version:`(v[\d.]+)`,tasks:JSON\.parse\(`")
_BINARY = re.compile(r"^(\d+) / (\d+)$")

_ANTHROPIC = "https://www.anthropic.com"
_GEMINI_BLOG = "https://blog.google/innovation-and-ai/models-and-research/gemini-models"
_GPT_5_6 = "https://openai.com/index/gpt-5-6/"
_GPT_6 = "https://openai.com/index/introducing-gpt-6-sol-and-luna/"
_MUSE_WONDER = "https://research.meta.ai/blog/muse-wonder"

# Exact SWE-Marathon model names are the trust boundary between a leaderboard
# config and its introducing paper; catalog names follow the 26 rows imported
# from Abundant AI's data on 2026-10-14. Other names are matched automatically
# when the catalog names them unambiguously, and otherwise handed to the
# release radar.
MODEL_IDENTITIES: dict[str, ModelIdentity] = {
    "Gemini 4 Carbon": ModelIdentity(
        "Gemini 4 Carbon",
        source_url=(
            "https://deepmind.google/blog/gemini-4-carbon-our-next-frontier-model/"
        ),
    ),
    "Gemini 4 Argon": ModelIdentity(
        "Gemini 4 Argon", source_url=f"{_GEMINI_BLOG}/gemini-4-argon/"
    ),
    "Gemini 3.7 Flash": ModelIdentity(
        "Gemini 3.7 Flash", source_url=f"{_GEMINI_BLOG}/introducing-gemini-3-7-flash/"
    ),
    "Muse Wonder Full": ModelIdentity("Muse Wonder Full", source_url=_MUSE_WONDER),
    "Muse Wonder": ModelIdentity("Muse Wonder", source_url=_MUSE_WONDER),
    "Muse Spark 1.3": ModelIdentity(
        "Muse Spark 1.3",
        source_url="https://research.meta.ai/blog/introducing-muse-spark-1-3",
    ),
    "Claude Opus 5.5": ModelIdentity(
        "Claude Opus 5.5", source_url=f"{_ANTHROPIC}/claude-opus-5-5"
    ),
    "Claude Sonnet 5.5": ModelIdentity(
        "Claude Sonnet 5.5", source_url=f"{_ANTHROPIC}/claude-sonnet-5-5"
    ),
    "Claude Haiku 5.5": ModelIdentity(
        "Claude Haiku 5.5", source_url=f"{_ANTHROPIC}/claude-haiku-5-5"
    ),
    "Claude Fable 5.1": ModelIdentity(
        "Claude Fable 5.1", source_url=f"{_ANTHROPIC}/claude-fable-and-mythos-5-1"
    ),
    "Claude Fable 5": ModelIdentity(
        "Claude Fable 5", source_url=f"{_ANTHROPIC}/news/claude-fable-5-mythos-5"
    ),
    "Claude Opus 5": ModelIdentity(
        "Claude Opus 5", source_url=f"{_ANTHROPIC}/news/claude-opus-5"
    ),
    "Claude Sonnet 5": ModelIdentity(
        "Claude Sonnet 5", source_url=f"{_ANTHROPIC}/news/claude-sonnet-5"
    ),
    "Claude Opus 4.8": ModelIdentity(
        "Claude Opus 4.8", source_url=f"{_ANTHROPIC}/news/claude-opus-4-8"
    ),
    "GPT-6 Astra": ModelIdentity(
        "GPT-6 Astra", source_url="https://openai.com/index/gpt-6-astra/"
    ),
    "GPT-6.1 Sol": ModelIdentity(
        "GPT-6.1 Sol", source_url="https://openai.com/index/introducing-gpt-6-1-sol/"
    ),
    "GPT-6 Sol": ModelIdentity("GPT-6 Sol", source_url=_GPT_6),
    "GPT-6 Luna": ModelIdentity("GPT-6 Luna", source_url=_GPT_6),
    "GPT-5.6-sol": ModelIdentity("GPT-5.6 Sol", source_url=_GPT_5_6),
    "GPT-5.6-terra": ModelIdentity("GPT-5.6 Terra", source_url=_GPT_5_6),
    "GPT-5.6-luna": ModelIdentity("GPT-5.6 Luna", source_url=_GPT_5_6),
    "Grok 4.7": ModelIdentity("Grok 4.7", source_url="https://x.ai/news/grok-4-7"),
    "Grok 4.6": ModelIdentity("Grok 4.6", source_url="https://x.ai/news/grok-4-6"),
    "Grok 4.5": ModelIdentity("Grok 4.5", source_url="https://x.ai/news/grok-4-5"),
    "GLM 5.3": ModelIdentity(
        "GLM-5.3",
        source_url="https://z.ai/blog/glm-5.3",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3",
    ),
    "GLM 5.3 Flash": ModelIdentity(
        "GLM-5.3-Flash",
        source_url="https://z.ai/blog/glm-5.3-flash",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.3-Flash",
    ),
    "GLM 5.2": ModelIdentity(
        "GLM-5.2",
        source_url="https://z.ai/blog/glm-5.2",
        is_open=True,
        hf_model_url="https://huggingface.co/zai-org/GLM-5.2",
    ),
    "Kimi K3": ModelIdentity(
        "Kimi K3",
        arxiv_id="2607.24653",
        is_open=True,
        hf_model_url="https://huggingface.co/moonshotai/Kimi-K3",
    ),
    "DeepSeek V4 Pro": ModelIdentity(
        "DeepSeek V4 Pro", arxiv_id="2606.19348", is_open=True
    ),
}


@dataclass
class _Run:
    """One agent, model and effort, accumulated over the tasks."""

    canonical: str
    passes: int = 0
    trials: int = 0
    tasks: set[str] = field(default_factory=set)
    trial_counts: set[int] = field(default_factory=set)
    latest: date | None = None


def _template_literal(source: str, start: int) -> str:
    """Decode the JS template literal whose body begins at ``start``."""
    chars: list[str] = []
    index = start
    while index < len(source):
        char = source[index]
        if char == "\\":
            if index + 1 >= len(source):
                break
            chars.append(source[index + 1])
            index += 2
            continue
        if char == "`":
            return "".join(chars)
        if char == "$" and source.startswith("${", index):
            raise ValueError("SWE-Marathon results literal is not plain data")
        chars.append(char)
        index += 1
    raise ValueError("SWE-Marathon results literal is unterminated")


def _started(trial: dict) -> date | None:
    value = trial.get("startedAt")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"SWE-Marathon trial start is malformed: {value!r}")
    return datetime.strptime(value, "%Y-%m-%d %H:%M UTC").date()


def parse_swe_marathon_bundle(bundle: str) -> list[LeaderboardEntry]:
    """Parse the v1.1 results in the site bundle, failing on any layout change."""
    if not isinstance(bundle, str) or not bundle.strip():
        raise TypeError("SWE-Marathon bundle must be non-empty JavaScript")
    blocks = list(_RESULTS.finditer(bundle))
    versions = [match[1] for match in blocks]
    if versions != [VERSION]:
        raise ValueError(
            f"SWE-Marathon bundle has result versions {versions}; expected [{VERSION!r}]"
        )
    try:
        tasks = json.loads(_template_literal(bundle, blocks[0].end()))
    except json.JSONDecodeError as exc:
        raise ValueError("SWE-Marathon results are not JSON") from exc
    if not isinstance(tasks, dict) or not tasks:
        raise ValueError("SWE-Marathon results layout changed")

    runs: dict[tuple[str, str, str], _Run] = {}
    for task_name, task in tasks.items():
        configs = task.get("configs") if isinstance(task, dict) else None
        if not isinstance(configs, list):
            raise ValueError(f"SWE-Marathon task {task_name!r} layout changed")
        for config in configs:
            agent = config.get("agent") if isinstance(config, dict) else None
            model = config.get("model") if isinstance(config, dict) else None
            if not all(
                isinstance(v, str) and v.strip() and len(v) <= 200
                for v in (agent, model)
            ):
                raise ValueError(f"SWE-Marathon config is malformed in {task_name!r}")
            effort = config.get("reasoningEffort") or DEFAULT_EFFORT
            trials = config.get("trials")
            binary = _BINARY.match(str(config.get("binary", "")))
            if (
                not isinstance(effort, str)
                or not isinstance(trials, list)
                or not binary
            ):
                raise ValueError(f"SWE-Marathon config is malformed: {agent} {model}")
            rewards = [trial.get("reward") for trial in trials]
            if any(reward not in (0, 1) for reward in rewards):
                raise ValueError(
                    f"SWE-Marathon rewards are not binary: {agent} {model}"
                )
            passes = sum(1 for reward in rewards if reward == 1)
            # The trial list and the published "k / n" must agree.
            if (int(binary[1]), int(binary[2])) != (passes, len(trials)):
                raise ValueError(
                    f"SWE-Marathon pass count disagrees: {agent} {model} {task_name}"
                )
            key = (agent.strip(), model.strip(), effort)
            run = runs.setdefault(key, _Run(str(config.get("canonicalModel") or "")))
            if task_name in run.tasks:
                raise ValueError(f"SWE-Marathon lists {key} twice in {task_name!r}")
            run.tasks.add(task_name)
            run.passes += passes
            run.trials += len(trials)
            run.trial_counts.add(len(trials))
            for trial in trials:
                started = _started(trial)
                if started and (run.latest is None or started > run.latest):
                    run.latest = started

    # A complete run covers every task with the board's trial count per task.
    per_task = Counter(
        count for run in runs.values() for count in run.trial_counts
    ).most_common(1)[0][0]
    best: dict[tuple[str, str], tuple[tuple, str, _Run]] = {}
    for (agent, model, effort), run in runs.items():
        if len(run.tasks) != len(tasks) or run.trial_counts != {per_task}:
            continue
        effort_rank = _EFFORT_ORDER.index(effort) if effort in _EFFORT_ORDER else 99
        rank = (-run.passes / run.trials, effort_rank)
        if (agent, model) not in best or rank < best[(agent, model)][0]:
            best[(agent, model)] = (rank, effort, run)

    entries: list[LeaderboardEntry] = []
    for (agent, model), (_, effort, run) in best.items():
        value = (Decimal(100 * run.passes) / Decimal(run.trials)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        prefix = run.canonical.partition("/")[0]
        entries.append(
            LeaderboardEntry(
                model,
                value,
                f"{value}% pass@1 ({run.passes}/{run.trials} trials over "
                f"{len(run.tasks)} tasks) at {effort} reasoning effort",
                harness=agent,
                lab=family_lab(model) or _PREFIX_LABS.get(prefix, ""),
                evaluated_on=run.latest,
            )
        )
    entries.sort(key=lambda entry: (-entry.value, entry.label))
    if not MIN_EXPECTED_ENTRIES <= len(entries) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"SWE-Marathon {VERSION} has {len(entries)} complete runs; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )
    return entries


def bundle_url(html: str) -> str:
    """Return the hashed script bundle the home page loads."""
    paths = set(_BUNDLE.findall(html or ""))
    if len(paths) != 1:
        raise ValueError(f"SWE-Marathon page loads {len(paths)} index bundles")
    return urljoin(SWE_MARATHON_URL, paths.pop())


def fetch_swe_marathon(client: httpx.Client | None = None) -> list[LeaderboardEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(60, connect=5), follow_redirects=True
    )
    try:
        url = bundle_url(fetch_text(SWE_MARATHON_URL, active_client))
        return parse_swe_marathon_bundle(fetch_text(url, active_client))
    finally:
        if owned_client:
            active_client.close()


BOARD = LiveLeaderboard(
    source="Abundant AI SWE-Marathon",
    provider="swe-marathon",
    url=SWE_MARATHON_URL,
    task_slug=TASK_SLUG,
    dataset_slug=DATASET_SLUG,
    metric=METRIC_NAME,
    identities=MODEL_IDENTITIES,
    min_selected=MIN_SELECTED_ENTRIES,
    # Self-reported vendor rows (Kimi K3.1 Pro) stay beside Abundant AI's runs.
    adopt_unmanaged=False,
    protocol=(
        f"SWE-Marathon {VERSION}: 20 ultra-long-horizon software projects, eight "
        "trials per task run by the benchmark authors (Abundant AI); pass@1 is "
        "the share of trials whose verifier passes, at the model's best "
        "reasoning effort."
    ),
)
