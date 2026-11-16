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

    G = floored_rank(best official repo stars/hour, live repo velocities,
                     GITHUB_MIN_STARS_PER_HOUR)

    a_i = kind_weight_i * floored_rank(hf_trending_score_i, live scores of that kind,
                                       HF_MIN_TRENDING_SCORE)
    H   = a_best + HF_EXTRA_ARTIFACT_SHARE * (1 - a_best) * (1 - prod_rest(1 - a_i))

    X   = quantile_rank(fastest linked X post likes/hour, all live post velocities)

    paper_trending_score = SCORE_SCALE * max(w_g * G + w_h * H, w_x * X)

X only lifts: few papers have a linked post, so blending it in linearly would
cap every paper without one below the X-tracked papers. As a lift, a paper
without X data keeps its GitHub/HF score, and a viral post can carry a paper to
the top on its own. The X weight ``w_x`` scales that lift
(``PWC_TRENDING_X_WEIGHT`` in [0, 1], default 0 = off, 1 = full). Posts slower than
``PWC_TRENDING_X_MIN_LIKES_PER_HOUR`` (default 1) count for nothing and stay out
of the X corpus: the corpus is small and pre-selected for notable papers, so a
slow post would otherwise rank mid-table.

GitHub and HF ranks are floored. Most live values are tiny (median repo
velocity ~0.01 stars/hour, median Hub trendingScore ~2), so a plain quantile
puts a repo with 3 stars in its first hours or a model with 10 recent likes in
the top few percent. ``floored_rank`` ranks values below the floor
(``GITHUB_MIN_STARS_PER_HOUR``, ``HF_MIN_TRENDING_SCORE``) only among
themselves, within ``[0, BELOW_FLOOR_SHARE]``, and values at or above it among
themselves, within ``[BELOW_FLOOR_SHARE, 1]``. Small signals still order the
long tail of papers, but cannot rank with real momentum.

H is led by the paper's best artifact. Its other artifacts can add at most
``HF_EXTRA_ARTIFACT_SHARE`` of the remaining headroom, so a model family
released as many small checkpoints cannot saturate H the way one top-of-Hub
model does.

Consequences (with X off):
- A paper at the very top of GitHub velocity (G=1) and a paper with a top-of-Hub
  model (H=1) both reach SCORE_SCALE * 0.5 -> they rank together at the top, so a
  paper can trend purely on its Hugging Face artifacts (the DeepSeek-V4 case).
- A paper strong on BOTH signals beats either alone (up to SCORE_SCALE).
- Extra HF artifacts help with diminishing returns, capped at
  ``HF_EXTRA_ARTIFACT_SHARE`` of the headroom above the best artifact.

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

# Blend weights between the GitHub and Hugging Face components. Equal weights so the top of each signal reaches the same
# single-signal ceiling.
GITHUB_WEIGHT = 0.5
HF_WEIGHT = 0.5

# Default X lift weight (off) and the slowest X post that still counts, in likes/hour.
DEFAULT_X_WEIGHT = 0.0
DEFAULT_X_MIN_LIKES_PER_HOUR = 1.0
# Only posts from the last week count; refresh_x_post_likes stops reading them.
X_POST_WINDOW_DAYS = 7

# Slowest repo star velocity (stars/hour, EMA) that ranks above the floor tier of G.
GITHUB_MIN_STARS_PER_HOUR = 1.0
# Lowest Hub trendingScore that ranks above the floor tier of H.
HF_MIN_TRENDING_SCORE = 10.0
# Share of each floored component reserved for values below the floor.
BELOW_FLOOR_SHARE = 0.1
# Share of the headroom above the best artifact that the other artifacts can fill.
HF_EXTRA_ARTIFACT_SHARE = 0.25

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
# Stored scores and components are rounded to 4 decimals before writing.
STORED_SCORE_TOLERANCE = 0.02

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


def floored_rank(sorted_values: Sequence[float], x: float, floor: float) -> float:
    """Quantile rank of ``x`` within its tier of ``sorted_values`` (0..1).

    Values below ``floor`` rank among the corpus values below it, scaled into
    ``[0, BELOW_FLOOR_SHARE]``; values at or above it rank among the corpus
    values at or above it, scaled into ``[BELOW_FLOOR_SHARE, 1]``.
    """
    if x is None or x <= 0 or not sorted_values:
        return 0.0
    split = bisect.bisect_left(sorted_values, floor)
    idx = bisect.bisect_right(sorted_values, x)
    if x < floor:
        return BELOW_FLOOR_SHARE * (min(idx / split, 1.0) if split else 1.0)
    above = len(sorted_values) - split
    tier_rank = min((idx - split) / above, 1.0) if above else 1.0
    return BELOW_FLOOR_SHARE + (1.0 - BELOW_FLOOR_SHARE) * tier_rank


def github_component(
    github_raw: float,
    github_sorted: Sequence[float],
    min_stars_per_hour: float = GITHUB_MIN_STARS_PER_HOUR,
) -> float:
    """Floored-rank GitHub component G for a paper's best official-repo velocity."""
    return floored_rank(github_sorted, github_raw or 0.0, min_stars_per_hour)


def hf_component(
    artifact_scores: Iterable[Tuple[str, float]],
    sorted_by_kind: Dict[str, Sequence[float]],
    kind_weights: Dict[str, float] = KIND_WEIGHTS,
    min_trending_score: float = HF_MIN_TRENDING_SCORE,
) -> float:
    """Aggregate HF artifacts into component H, led by the best artifact.

    Args:
        artifact_scores: iterable of ``(kind, raw_trending_score)`` tuples.
        sorted_by_kind: ascending-sorted positive trending scores per kind.
        kind_weights: per-kind weight applied to the floored rank.
        min_trending_score: floor between the low and high rank tiers.

    Each artifact contributes ``a_i = weight * floored_rank``. H is the best
    ``a_i`` plus at most ``HF_EXTRA_ARTIFACT_SHARE`` of the remaining headroom,
    filled by the soft-OR of the other artifacts, so H stays within [0, 1].
    """
    ranks = []
    for kind, raw in artifact_scores:
        if raw is None or raw <= 0:
            continue
        weight = kind_weights.get(kind, 0.0)
        corpus = sorted_by_kind.get(kind)
        if weight <= 0 or not corpus:
            continue
        rank = min(weight * floored_rank(corpus, raw, min_trending_score), 1.0)
        if rank > 0:
            ranks.append(rank)

    if not ranks:
        return 0.0
    ranks.sort(reverse=True)
    best = ranks[0]
    rest_product = 1.0
    for rank in ranks[1:]:
        rest_product *= 1.0 - rank
    return best + HF_EXTRA_ARTIFACT_SHARE * (1.0 - best) * (1.0 - rest_product)


def x_corpus(velocities: Iterable[float], min_likes_per_hour: float) -> List[float]:
    """Sorted X velocities fast enough to count (the X rank corpus)."""
    return sorted_positive(v for v in velocities if v >= min_likes_per_hour)


def x_component(
    x_raw: float, x_sorted: Sequence[float], min_likes_per_hour: float
) -> float:
    """Quantile-rank X component for a paper's fastest linked post."""
    if x_raw < min_likes_per_hour:
        return 0.0
    return quantile_rank(x_sorted, x_raw)


def composite_score(
    g_component: float,
    h_component: float,
    x_component: float = 0.0,
    x_weight: float = DEFAULT_X_WEIGHT,
) -> float:
    """Combine the normalized components into the final paper score."""
    github_hf = GITHUB_WEIGHT * g_component + HF_WEIGHT * h_component
    return SCORE_SCALE * max(github_hf, x_weight * x_component)


def hourly_lift(
    stored_score: float | None,
    stored_g: float | None,
    stored_h: float | None,
) -> float:
    """Return the part of a stored score that sits above its GitHub/HF base.

    Only the hourly job applies the X lift and decaying pins, so a targeted
    rescore keeps this value instead of recomputing it with its own settings.
    """
    if stored_score is None:
        return 0.0
    base = composite_score(stored_g or 0.0, stored_h or 0.0)
    return stored_score if stored_score > base + STORED_SCORE_TOLERANCE else 0.0


def compute_paper_score(
    github_raw: float,
    github_sorted: Sequence[float],
    artifact_scores: Iterable[Tuple[str, float]],
    sorted_by_kind: Dict[str, Sequence[float]],
    kind_weights: Dict[str, float] = KIND_WEIGHTS,
    *,
    x_raw: float = 0.0,
    x_sorted: Sequence[float] = (),
    x_weight: float = DEFAULT_X_WEIGHT,
    x_min_likes_per_hour: float = DEFAULT_X_MIN_LIKES_PER_HOUR,
) -> Tuple[float, float, float, float]:
    """Compute ``(score, g_component, h_component, x_component)`` for one paper."""
    g = github_component(github_raw, github_sorted)
    h = hf_component(artifact_scores, sorted_by_kind, kind_weights)
    x = x_component(x_raw, x_sorted, x_min_likes_per_hour)
    return composite_score(g, h, x, x_weight), g, h, x
