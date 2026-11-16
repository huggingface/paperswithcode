"""Unit tests for the composite paper trending formula.

These exercise the pure formula in ``backend/utils/trending.py`` (no DB):
quantile normalization, floored ranks, best-led HF aggregation, kind weights,
capped extra-artifact returns, and the GitHub/HF blend, including a DeepSeek-like scenario where a
paper trends purely on its Hugging Face models.
"""

import pytest

from backend.utils.trending import (
    BELOW_FLOOR_SHARE,
    GITHUB_WEIGHT,
    HF_EXTRA_ARTIFACT_SHARE,
    HF_MAX_ARTIFACT_PAPERS,
    HF_WEIGHT,
    SCORE_SCALE,
    apply_decaying_pin,
    compute_paper_score,
    composite_score,
    x_component,
    x_corpus,
    decaying_pin_floor,
    floored_rank,
    github_component,
    hf_component,
    is_hf_aggregator,
    parse_trending_paper_id_pin_specs,
    parse_trending_pin_specs,
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


def test_floored_rank_splits_the_corpus_into_tiers():
    corpus = sorted_positive([0.1, 0.2, 0.3, 0.5, 1, 2, 5, 10])
    assert floored_rank(corpus, 0, 1.0) == 0.0
    assert floored_rank([], 5, 1.0) == 0.0
    # Below the floor: ranked among the four low values, within [0, share].
    assert floored_rank(corpus, 0.2, 1.0) == pytest.approx(BELOW_FLOOR_SHARE / 2)
    assert floored_rank(corpus, 0.9, 1.0) == pytest.approx(BELOW_FLOOR_SHARE)
    # At or above the floor: ranked among the four high values, within [share, 1].
    assert floored_rank(corpus, 1, 1.0) == pytest.approx(
        BELOW_FLOOR_SHARE + (1 - BELOW_FLOOR_SHARE) / 4
    )
    assert floored_rank(corpus, 10, 1.0) == 1.0
    ranks = [floored_rank(corpus, x, 1.0) for x in corpus]
    assert ranks == sorted(ranks)
    # An empty tier (value outside the corpus) cannot divide by zero.
    assert floored_rank([2.0, 3.0], 0.5, 1.0) == pytest.approx(BELOW_FLOOR_SHARE)
    assert floored_rank([0.2, 0.3], 4.0, 1.0) == 1.0


def test_github_component_uses_floored_rank():
    corpus = sorted_positive([0.5, 1, 2, 5, 10, 20])
    assert github_component(20, corpus) == 1.0
    assert github_component(2, corpus, 1.0) == pytest.approx(0.1 + 0.9 * 2 / 5)
    assert github_component(0.5, corpus, 1.0) == pytest.approx(BELOW_FLOOR_SHARE)
    assert github_component(0, corpus) == 0.0


def test_fresh_repo_with_few_stars_stays_below_the_floor_tier():
    """3 stars in a repo's first hours tops a corpus of near-zero velocities."""
    corpus = sorted_positive([0.001] * 90 + [0.86] + [1.5, 3, 8, 20, 50])
    assert quantile_rank(corpus, 0.86) > 0.9
    assert github_component(0.86, corpus, 1.0) <= BELOW_FLOOR_SHARE


def test_hf_component_empty_is_zero():
    assert hf_component([], {"model": [1.0, 2.0]}) == 0.0
    # Artifact with no corpus for its kind contributes nothing.
    assert hf_component([("dataset", 5)], {"model": [1.0, 2.0]}) == 0.0


def test_hf_component_is_led_by_the_best_artifact():
    models = sorted_positive([1, 4, 12, 46, 102])
    by_kind = {"model": models, "dataset": [], "space": []}
    # Single top model -> rank 1.0 -> H = 1.0.
    assert hf_component([("model", 102)], by_kind, min_trending_score=10) == 1.0
    # Extra artifacts fill part of the headroom above the best one.
    best = floored_rank(models, 46, 10)
    other = floored_rank(models, 12, 10)
    two = hf_component([("model", 12), ("model", 46)], by_kind, min_trending_score=10)
    assert two == pytest.approx(best + HF_EXTRA_ARTIFACT_SHARE * (1 - best) * other)
    assert best < two < 1.0


def test_many_small_checkpoints_do_not_saturate_hf():
    """Six checkpoints with ~10 recent likes each must not look like a top model."""
    models = sorted_positive(
        [1] * 300 + [2] * 300 + [5] * 200 + [8, 9, 9, 9] + list(range(10, 200))
    )
    by_kind = {"model": models, "dataset": [], "space": []}
    family = [("model", s) for s in (10, 9, 9, 9, 8, 8)]
    h = hf_component(family, by_kind, min_trending_score=10)
    best = floored_rank(models, 10, 10)
    assert h <= best + HF_EXTRA_ARTIFACT_SHARE * (1 - best)
    assert h < hf_component([("model", 199)], by_kind, min_trending_score=10) / 2


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

    deepseek_score, g, h, _ = compute_paper_score(
        github_raw=0.0,
        github_sorted=github_sorted,
        artifact_scores=[("model", 102), ("model", 46), ("model", 4), ("model", 1)],
        sorted_by_kind=by_kind,
    )
    assert g == 0.0
    assert h == 1.0
    assert deepseek_score == SCORE_SCALE * HF_WEIGHT  # 50

    mid_github, *_ = compute_paper_score(2.0, github_sorted, [], by_kind)
    top_github, *_ = compute_paper_score(20.0, github_sorted, [], by_kind)
    both, *_ = compute_paper_score(20.0, github_sorted, [("model", 102)], by_kind)

    # HF-only DeepSeek paper beats a mid GitHub paper and ties the top one.
    assert deepseek_score > mid_github
    assert deepseek_score == top_github
    # A paper strong on BOTH signals outranks either single-signal paper.
    assert both > deepseek_score
    assert both > top_github
    assert both == SCORE_SCALE


def test_no_signal_paper_scores_zero():
    score, g, h, _ = compute_paper_score(0.0, [1.0, 2.0], [], {"model": [1.0]})
    assert (score, g, h) == (0.0, 0.0, 0.0)


def test_parse_trending_pin_specs():
    assert parse_trending_pin_specs("") == {}
    assert parse_trending_pin_specs("2606.16140") == {"2606.16140": 72.0}
    assert parse_trending_pin_specs("2606.16140:48,2606.10804") == {
        "2606.16140": 48.0,
        "2606.10804": 72.0,
    }


def test_parse_trending_paper_id_pin_specs():
    assert parse_trending_paper_id_pin_specs("") == {}
    assert parse_trending_paper_id_pin_specs("104054:96,42") == {
        104054: 96.0,
        42: 72.0,
    }

    with pytest.raises(ValueError):
        parse_trending_paper_id_pin_specs("external:72")
    with pytest.raises(ValueError, match="positive"):
        parse_trending_paper_id_pin_specs("0:72")


def test_decaying_pin_fades_to_computed_score():
    assert decaying_pin_floor(0, 72) == 100.0
    assert decaying_pin_floor(36, 72) == 50.0
    assert decaying_pin_floor(72, 72) == 0.0

    # True score wins once it exceeds the fading floor.
    assert apply_decaying_pin(51.7, 0, 72) == 100.0
    assert apply_decaying_pin(51.7, 36, 72) == 51.7
    assert apply_decaying_pin(80.0, 36, 72) == 80.0
    assert apply_decaying_pin(51.7, 80, 72) == 51.7


def test_hf_aggregators_are_excluded_by_fan_out_and_denylist():
    assert not is_hf_aggregator("model", "org/model", 1)
    assert not is_hf_aggregator("model", "org/model", HF_MAX_ARTIFACT_PAPERS)
    assert is_hf_aggregator("model", "org/model", HF_MAX_ARTIFACT_PAPERS + 1)
    assert is_hf_aggregator("space", "tardellirs/paper-pulse", 1)
    # The denylist is per kind: a same-named repo of another kind still counts.
    assert not is_hf_aggregator("model", "tardellirs/paper-pulse", 1)


def test_x_only_lifts_the_github_hf_score():
    # A paper without X data keeps its GitHub/HF score.
    assert composite_score(1.0, 0.0, 0.0, x_weight=1.0) == pytest.approx(
        SCORE_SCALE * GITHUB_WEIGHT
    )
    # A faster X rank lifts the paper, a slower one never lowers it.
    assert composite_score(0.2, 0.2, 0.9, x_weight=1.0) == pytest.approx(
        SCORE_SCALE * 0.9
    )
    assert composite_score(0.8, 0.8, 0.5, x_weight=1.0) == pytest.approx(
        SCORE_SCALE * 0.8
    )
    # The weight scales the lift; a viral post alone can reach the top.
    assert composite_score(0.0, 0.0, 1.0, x_weight=0.5) == pytest.approx(
        SCORE_SCALE / 2
    )
    assert composite_score(0.0, 0.0, 1.0, x_weight=1.0) == pytest.approx(SCORE_SCALE)
    # Weighted at 0, X never changes a score.
    assert composite_score(0.4, 0.6, 1.0) == composite_score(0.4, 0.6)


def test_slow_x_posts_count_for_nothing_and_stay_out_of_the_corpus():
    corpus = x_corpus([0.2, 0.9, 1.0, 5.0, 40.0], min_likes_per_hour=1.0)
    assert corpus == [1.0, 5.0, 40.0]
    assert x_component(0.9, corpus, 1.0) == 0.0
    assert x_component(5.0, corpus, 1.0) == pytest.approx(2 / 3)
    assert x_component(40.0, corpus, 1.0) == 1.0

    score, g, h, x = compute_paper_score(
        0.0, [], [], {}, x_raw=40.0, x_sorted=corpus, x_weight=1.0
    )
    assert (g, h, x) == (0.0, 0.0, 1.0)
    assert score == pytest.approx(SCORE_SCALE)
