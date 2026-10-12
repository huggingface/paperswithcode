from types import SimpleNamespace

from backend.scripts.report_chat_ttft import (
    browser_semantic_metric,
    distribution,
    passes,
)


def test_ttft_report_distribution_and_gate_are_explicit():
    values = list(range(1, 101))

    result = distribution(values)

    assert result == {
        "count": 100,
        "min": 1,
        "p50": 50,
        "p75": 75,
        "p90": 90,
        "p95": 95,
        "p99": 99,
        "max": 100,
    }
    assert passes(result, count=50, p50=50, p90=90)
    assert not passes(result, count=101, p50=50, p90=90)


def test_browser_semantic_metric_uses_earliest_visible_event():
    rows = [
        SimpleNamespace(
            browser_first_reasoning_delta_ms=None,
            browser_first_tool_call_ms=None,
            browser_first_answer_delta_ms=1200,
        ),
        SimpleNamespace(
            browser_first_reasoning_delta_ms=900,
            browser_first_tool_call_ms=700,
            browser_first_answer_delta_ms=1100,
        ),
    ]

    result = browser_semantic_metric(rows)

    assert result["count"] == 2
    assert result["min"] == 700
    assert result["max"] == 1200
