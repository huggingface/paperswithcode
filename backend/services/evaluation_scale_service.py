"""Check source-to-leaderboard conversions without guessing from score magnitude."""

import math

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
