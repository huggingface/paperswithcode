"""
Composite paper trending score formula.

Blends the existing GitHub star-velocity EMA (``repositories.trending_score``,
stars/hour) with Hugging Face artifact Hub trending scores
(``hf_artifacts.trending_score``) into a single paper-level score.

The two raw signals live on wildly different and highly skewed scales (GitHub
star velocity has a very fat tail; HF trendingScore is more compressed), so a
fixed log/percentile rescale either lets GitHub dominate or saturates the top of
the ranking. Instead we map each signal through its own **empirical quantile
rank** over the live corpus, which puts both on a comparable, saturation-free
[0, 1] scale regardless of distribution shape:

    G = quantile_rank(best official repo stars/hour, all live repo velocities)

    a_i = kind_weight_i * quantile_rank(hf_trending_score_i, all live scores of that kind)
    H   = 1 - prod(1 - a_i)        # weighted soft-OR: diminishing returns, stays in [0, 1]

    paper_trending_score = SCORE_SCALE * (GITHUB_WEIGHT * G + HF_WEIGHT * H)

Consequences:
- A paper at the very top of GitHub velocity (G=1) and a paper with a top-of-Hub
  model (H=1) both reach SCORE_SCALE * 0.5 -> they rank together at the top, so a
  paper can trend purely on its Hugging Face artifacts (the DeepSeek-V4 case).
- A paper strong on BOTH signals beats either alone (up to SCORE_SCALE).
- Extra HF artifacts help with diminishing returns and can never push a paper
  past the single-signal ceiling on their own.

Aggregator artifacts (paper feeds, awesome lists, leaderboards) cite hundreds of
papers, and the Hub links each of them back. They say nothing about one paper
trending, so artifacts linked to more than ``HF_MAX_ARTIFACT_PAPERS`` papers or
listed in ``HF_AGGREGATOR_DENYLIST`` count for nothing. The links stay on paper
pages; only scoring ignores them.

This module is dependency-free (stdlib ``bisect``) so it is unit-testable without
a database or numpy.
"""

from __future__ import annotations

import bisect
from typing import Dict, Iterable, List, Sequence, Tuple

# Blend weights between the GitHub and Hugging Face components. Equal weights so
# the top of each signal reaches the same single-signal ceiling.
GITHUB_WEIGHT = 0.5
HF_WEIGHT = 0.5

# Per-kind importance of HF artifacts (applied to the quantile rank).
KIND_WEIGHTS: Dict[str, float] = {
    "model": 1.0,
    "dataset": 0.8,
    "space": 0.7,
}

# A paper's own artifact is linked to a handful of papers; live trending models
# never exceed 5, while aggregator Spaces and datasets reach thousands.
HF_MAX_ARTIFACT_PAPERS = 5

# Known aggregators, excluded whatever their current fan-out.
HF_AGGREGATOR_DENYLIST = frozenset(
    {
        ("space", "tardellirs/paper-pulse"),
        ("space", "tardellirs/model-pulse"),
        ("space", "eduagarcia/multilingual-tokenizer-leaderboard"),
        ("dataset", "molmohsen/awesome-ai-agent-papers"),
    }
)

# Final score multiplier (single-signal top ~= 50, both-signal top ~= 100).
SCORE_SCALE = 100.0

# Editorial decaying pin: temporary boost that linearly fades to the computed score.
PIN_PEAK_SCORE = 100.0
DEFAULT_PIN_DECAY_HOURS = 72.0


def parse_trending_pin_specs(
    raw: str, default_decay_hours: float = DEFAULT_PIN_DECAY_HOURS
) -> Dict[str, float]:
    """Parse ``arxiv[:hours],...`` into ``{arxiv_id: decay_hours}``."""
    specs: Dict[str, float] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            arxiv_id, hours_str = part.split(":", 1)
            specs[arxiv_id.strip()] = float(hours_str.strip())
        else:
            specs[part] = default_decay_hours
    return specs


def parse_trending_paper_id_pin_specs(
    raw: str, default_decay_hours: float = DEFAULT_PIN_DECAY_HOURS
) -> Dict[int, float]:
    """Parse ``paper_id[:hours],...`` into positive integer paper IDs."""
    specs: Dict[int, float] = {}
    for raw_id, decay_hours in parse_trending_pin_specs(
        raw, default_decay_hours
    ).items():
        paper_id = int(raw_id)
        if paper_id <= 0:
            raise ValueError("trending pin paper IDs must be positive")
        specs[paper_id] = decay_hours
    return specs


def decaying_pin_floor(
    hours_elapsed: float,
    decay_hours: float,
    peak: float = PIN_PEAK_SCORE,
) -> float:
    """Linear editorial floor that fades from ``peak`` to 0 over ``decay_hours``."""
    if decay_hours <= 0 or hours_elapsed >= decay_hours:
        return 0.0
    return peak * (1.0 - hours_elapsed / decay_hours)


def apply_decaying_pin(
    computed: float | None,
    hours_elapsed: float,
    decay_hours: float,
    peak: float = PIN_PEAK_SCORE,
) -> float:
    """Blend a decaying editorial floor with the computed composite score."""
    floor = decaying_pin_floor(hours_elapsed, decay_hours, peak=peak)
    base = float(computed) if computed is not None else 0.0
    return max(base, floor)


def is_hf_aggregator(kind: str, repo_id: str, linked_papers: int) -> bool:
    """Whether an HF artifact is an aggregator that must not drive trending."""
    return (
        linked_papers > HF_MAX_ARTIFACT_PAPERS
        or (kind, repo_id) in HF_AGGREGATOR_DENYLIST
    )


def sorted_positive(values: Iterable[float]) -> List[float]:
    """Return a sorted list of the strictly-positive values (the rank corpus)."""
    return sorted(float(v) for v in values if v is not None and v > 0)


def quantile_rank(sorted_values: Sequence[float], x: float) -> float:
    """Empirical quantile rank of ``x`` within ``sorted_values`` (0..1).

    Defined as the fraction of corpus values <= ``x``. Returns 0.0 for a
    non-positive ``x`` or an empty corpus. ``sorted_values`` must be sorted
    ascending (use :func:`sorted_positive`).
    """
    if x is None or x <= 0 or not sorted_values:
        return 0.0
    idx = bisect.bisect_right(sorted_values, x)
    return idx / len(sorted_values)


def github_component(github_raw: float, github_sorted: Sequence[float]) -> float:
    """Quantile-rank GitHub component G for a paper's best official-repo velocity."""
    return quantile_rank(github_sorted, github_raw or 0.0)


def hf_component(
    artifact_scores: Iterable[Tuple[str, float]],
    sorted_by_kind: Dict[str, Sequence[float]],
    kind_weights: Dict[str, float] = KIND_WEIGHTS,
) -> float:
    """Aggregate HF artifacts into component H via weighted soft-OR.

    Args:
        artifact_scores: iterable of ``(kind, raw_trending_score)`` tuples.
        sorted_by_kind: ascending-sorted positive trending scores per kind.
        kind_weights: per-kind weight applied to the quantile rank.

    Each artifact contributes ``a_i = weight * quantile_rank``; the combined
    ``H = 1 - prod(1 - a_i)`` stays within [0, 1] and rewards additional
    artifacts with diminishing returns.
    """
    product = 1.0
    saw_any = False
    for kind, raw in artifact_scores:
        if raw is None or raw <= 0:
            continue
        weight = kind_weights.get(kind, 0.0)
        if weight <= 0:
            continue
        corpus = sorted_by_kind.get(kind)
        if not corpus:
            continue
        rank = weight * quantile_rank(corpus, raw)
        if rank <= 0:
            continue
        product *= 1.0 - min(rank, 1.0)
        saw_any = True

    if not saw_any:
        return 0.0
    return 1.0 - product


def composite_score(g_component: float, h_component: float) -> float:
    """Combine the normalized components into the final paper score."""
    return SCORE_SCALE * (GITHUB_WEIGHT * g_component + HF_WEIGHT * h_component)


def compute_paper_score(
    github_raw: float,
    github_sorted: Sequence[float],
    artifact_scores: Iterable[Tuple[str, float]],
    sorted_by_kind: Dict[str, Sequence[float]],
    kind_weights: Dict[str, float] = KIND_WEIGHTS,
) -> Tuple[float, float, float]:
    """Compute ``(score, g_component, h_component)`` for one paper."""
    g = github_component(github_raw, github_sorted)
    h = hf_component(artifact_scores, sorted_by_kind, kind_weights)
    return composite_score(g, h), g, h
