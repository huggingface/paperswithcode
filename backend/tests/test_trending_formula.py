"""Unit tests for the composite paper trending formula.

These exercise the pure formula in ``backend/utils/trending.py`` (no DB):
quantile normalization, HF soft-OR aggregation, kind weights, diminishing
returns, and the GitHub/HF blend, including a DeepSeek-like scenario where a
paper trends purely on its Hugging Face models.
"""

from backend.utils.trending import (
    GITHUB_WEIGHT,
    HF_WEIGHT,
    SCORE_SCALE,
    compute_paper_score,
    composite_score,
    github_component,
    hf_component,
    quantile_rank,
    sorted_positive,
)


def test_sorted_positive_filters_and_sorts():
    assert sorted_positive([3, 1, 2, 0, -5, None]) == [1.0, 2.0, 3.0]
    assert sorted_positive([]) == []


def test_quantile_rank_bounds_and_monotonicity():
    corpus = sorted_positive([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    # Non-positive / empty corpus -> 0.
    assert quantile_rank(corpus, 0) == 0.0
    assert quantile_rank([], 5) == 0.0
    # Max maps to 1.0; values below max are strictly smaller.
    assert quantile_rank(corpus, 10) == 1.0
    assert quantile_rank(corpus, 5) == 0.5
    assert quantile_rank(corpus, 1) == 0.1
    # Monotonic non-decreasing.
    ranks = [quantile_rank(corpus, x) for x in range(1, 11)]
    assert ranks == sorted(ranks)
    # A value beyond the corpus max still caps at 1.0.
    assert quantile_rank(corpus, 9999) == 1.0


def test_github_component_uses_quantile():
    corpus = sorted_positive([0.5, 1, 2, 5, 10, 20])
    assert github_component(20, corpus) == 1.0
    assert github_component(2, corpus) == 0.5
    assert github_component(0, corpus) == 0.0


def test_hf_component_empty_is_zero():
    assert hf_component([], {"model": [1.0, 2.0]}) == 0.0
    # Artifact with no corpus for its kind contributes nothing.
    assert hf_component([("dataset", 5)], {"model": [1.0, 2.0]}) == 0.0


def test_hf_component_soft_or_and_diminishing_returns():
    models = sorted_positive([1, 4, 46, 102])
    by_kind = {"model": models, "dataset": [], "space": []}
    # Single top model -> rank 1.0 -> H = 1.0.
    single = hf_component([("model", 102)], by_kind)
    assert single == 1.0
    # Two mid models: soft-OR exceeds each but stays < 1.
    two = hf_component([("model", 4), ("model", 1)], by_kind)
    r4 = quantile_rank(models, 4)  # 0.5
    r1 = quantile_rank(models, 1)  # 0.25
    assert two == 1 - (1 - r4) * (1 - r1)
    assert r4 < two < 1.0


def test_hf_component_applies_kind_weights():
    by_kind = {"model": [10.0], "dataset": [10.0], "space": [10.0]}
    # Same raw + same corpus, different kind weights => model > dataset > space.
    m = hf_component([("model", 10)], by_kind)
    d = hf_component([("dataset", 10)], by_kind)
    s = hf_component([("space", 10)], by_kind)
    assert m == 1.0  # weight 1.0 * rank 1.0
    assert d == 0.8
    assert s == 0.7


def test_composite_score_blend():
    assert composite_score(1.0, 0.0) == SCORE_SCALE * GITHUB_WEIGHT
    assert composite_score(0.0, 1.0) == SCORE_SCALE * HF_WEIGHT
    assert composite_score(1.0, 1.0) == SCORE_SCALE


def test_deepseek_like_paper_trends_on_hf_alone():
    """A paper with top-of-corpus HF models ranks at the single-signal ceiling,
    beating a mid-velocity GitHub paper and tying the top GitHub paper."""
    github_sorted = sorted_positive([0.5, 1, 2, 5, 10, 20])
    models = sorted_positive([1, 4, 46, 102])
    by_kind = {"model": models, "dataset": [], "space": []}

    deepseek_score, g, h = compute_paper_score(
        github_raw=0.0,
        github_sorted=github_sorted,
        artifact_scores=[("model", 102), ("model", 46), ("model", 4), ("model", 1)],
        sorted_by_kind=by_kind,
    )
    assert g == 0.0
    assert h == 1.0
    assert deepseek_score == SCORE_SCALE * HF_WEIGHT  # 50

    mid_github, _, _ = compute_paper_score(2.0, github_sorted, [], by_kind)
    top_github, _, _ = compute_paper_score(20.0, github_sorted, [], by_kind)
    both, _, _ = compute_paper_score(20.0, github_sorted, [("model", 102)], by_kind)

    # HF-only DeepSeek paper beats a mid GitHub paper and ties the top one.
    assert deepseek_score > mid_github
    assert deepseek_score == top_github
    # A paper strong on BOTH signals outranks either single-signal paper.
    assert both > deepseek_score
    assert both > top_github
    assert both == SCORE_SCALE


def test_no_signal_paper_scores_zero():
    score, g, h = compute_paper_score(0.0, [1.0, 2.0], [], {"model": [1.0]})
    assert (score, g, h) == (0.0, 0.0, 0.0)
