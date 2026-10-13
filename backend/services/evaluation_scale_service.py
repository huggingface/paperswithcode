"""Check source-to-leaderboard conversions without guessing from score magnitude."""

import math
from collections.abc import Callable

from backend.models.evaluations import EvaluationScoreEvidence


def metric_scale_bounds(scale: str | None) -> tuple[float, float] | None:
    normalized = (scale or "").strip().lower().replace(" ", "")
    return {
        "0-1": (0.0, 1.0),
        "[0,1]": (0.0, 1.0),
        "fraction": (0.0, 1.0),
        "0-100": (0.0, 100.0),
        "[0,100]": (0.0, 100.0),
        "percent": (0.0, 100.0),
        "percentage": (0.0, 100.0),
        "0-1000": (0.0, 1000.0),
        "[0,1000]": (0.0, 1000.0),
    }.get(normalized)


def validate_source_score(
    scale: str | None, value: float, evidence: EvaluationScoreEvidence
) -> None:
    """Reject incorrect conversions; never silently rewrite a proposed score."""
    target = metric_scale_bounds(scale)
    source = metric_scale_bounds(evidence.source_scale)
    expected = evidence.source_value
    if target in {(0.0, 1.0), (0.0, 100.0)}:
        if source is None:
            raise ValueError("Rate metrics require explicit source_scale 0-1 or 0-100")
        if not source[0] <= expected <= source[1]:
            raise ValueError("Source score is outside its declared source_scale")
        expected = expected * target[1] / source[1]
    elif evidence.source_scale != "native":
        raise ValueError(
            "Unknown or non-rate metric scale requires native source units; "
            "do not infer a percentage conversion"
        )
    if not math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError(
            f"Score scale mismatch for {evidence.metric}: source "
            f"{evidence.source_value:g} ({evidence.source_scale}) requires "
            f"{expected:g} on configured scale {scale!r}, received {value:g}"
        )


# A board needs this many other rows, with its lowest 5% scoring at least this
# much, before its own values can contradict a submitted sub-1 percentage.
BOARD_SCALE_MIN_ROWS = 3
BOARD_SCALE_MIN_LOW_TAIL = 5.0


def validate_board_scale(
    scale: str | None,
    evidence: EvaluationScoreEvidence,
    load_board_values: Callable[[], list[float]],
) -> None:
    """Reject a sub-1 "percentage" that the leaderboard's own rows contradict.

    A source cell such as 0.923 declared as 0-100 passes the conversion check
    but is usually a fraction of 92.3%. Accept it when the leaderboard is too
    small to judge or genuinely scores low (ARC-AGI-2, sparse success rates).
    """
    if metric_scale_bounds(scale) != (0.0, 100.0) or evidence.source_scale != "0-100":
        return
    if not 0 < evidence.source_value <= 1:
        return
    values = sorted(load_board_values())
    if len(values) < BOARD_SCALE_MIN_ROWS:
        return
    low_tail = values[int(0.05 * (len(values) - 1))]
    if low_tail < BOARD_SCALE_MIN_LOW_TAIL:
        return
    raise ValueError(
        f"{evidence.metric} {evidence.source_value:g} declared as 0-100 looks like "
        f"a 0-1 fraction: the lowest 5% of the leaderboard's {len(values)} other "
        f"rows score at least {low_tail:g}. If the source cell is a fraction, "
        f"declare source_scale 0-1 and submit {evidence.source_value * 100:g}; if "
        "the source truly reports a sub-1 percentage, omit this result."
    )
