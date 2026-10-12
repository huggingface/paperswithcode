from __future__ import annotations

from backend.services.discovery_text_service import (
    markdown_html,
    markdown_plain_text,
    meta_description,
)
from backend.services.leaderboard_ranking_service import (
    RankableEvaluation,
    RankableTask,
    parse_metric_value,
    rank_leaderboard,
)


def test_markdown_html_escapes_text_and_drops_unsafe_links():
    html = markdown_html(
        'A <b>"x"</b> [safe *link*](/tasks/a?x=1&y=2) '
        "[bad](javascript:alert) [proto](//evil.example)\n\nSecond **para**."
    )
    assert "<b>" not in html
    assert "&lt;b&gt;&quot;x&quot;&lt;/b&gt;" in html
    assert '<a href="/tasks/a?x=1&amp;y=2">safe <em>link</em></a>' in html
    assert 'href="javascript' not in html and "bad" in html
    assert 'href="//evil.example"' not in html
    assert html.endswith("<p>Second <strong>para</strong>.</p>")


def test_markdown_plain_text_and_meta_description():
    text = markdown_plain_text("**World models** map a *state* to [the next](/x).")
    assert text == "World models map a state to the next."
    shortened = meta_description("word " * 60)
    assert len(shortened) <= 155 and shortened.endswith("…")
    two = "A" * 70 + ". " + "B" * 70 + ". " + "C" * 70 + "."
    assert meta_description(two) == "A" * 70 + ". " + "B" * 70 + "."


def test_parse_metric_value_matches_javascript_parse_float():
    assert parse_metric_value("88.55 ± 0.04") == 88.55
    assert parse_metric_value("72.1%") == 72.1
    assert parse_metric_value(" 1e2") == 100.0
    assert parse_metric_value("n/a") is None
    assert parse_metric_value(None) is None
    assert parse_metric_value(3) == 3.0


def _evaluation(id, task_id, model, metrics, best_metric, best_rank, paper_id=None):
    return RankableEvaluation(
        id=id,
        paper_id=paper_id or id,
        task_id=task_id,
        model_name=model,
        harness=None,
        metrics=metrics,
        best_metric=best_metric,
        best_rank=best_rank,
    )


def test_rank_leaderboard_uses_dominant_task_metric_and_direction():
    tasks = [RankableTask(1, "a", "A"), RankableTask(2, "b", "B")]
    evaluations = [
        _evaluation(1, 2, "m1", {"WER": "5.0"}, "WER", 1),
        _evaluation(2, 2, "m2", {"WER": "3.0"}, "WER", 2),
        # Same model and paper as m2: folded into one row with both metrics.
        _evaluation(3, 2, "m2", {"CER": "1.0"}, "CER", 1, paper_id=2),
        _evaluation(4, 1, "other", {"WER": "1.0"}, "WER", 1),
    ]
    ranked = rank_leaderboard(
        tasks=tasks,
        evaluations=evaluations,
        configured_metrics={},
        directions={"WER": "lower_is_better"},
    )
    assert ranked.task.slug == "b"
    assert ranked.metric == "WER"
    assert ranked.lower_is_better
    assert [(row.rank, row.entry.first.model_name) for row in ranked.rows] == [
        (1, "m2"),
        (2, "m1"),
    ]
    assert ranked.rows[0].entry.metrics == {"WER": "3.0", "CER": "1.0"}

    requested = rank_leaderboard(
        tasks=tasks,
        evaluations=evaluations,
        configured_metrics={1: ["WER"]},
        directions={},
        task_slug="a",
    )
    assert [row.entry.first.model_name for row in requested.rows] == ["other"]
