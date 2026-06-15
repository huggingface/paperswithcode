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

# Final score multiplier (single-signal top ~= 50, both-signal top ~= 100).
SCORE_SCALE = 100.0


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
