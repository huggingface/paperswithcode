"""Canonical identity for one displayed benchmark leaderboard entry."""

from __future__ import annotations

import json
import re

EvaluationDisplayEntryKey = tuple[int, int, int, str, str]

# Case, spacing and separators never distinguish two models ("I-DLM-32B" and
# "I-DLM (32B)"); symbols such as "+" or "*" do ("DAT" and "DAT+").
_MODEL_NAME_SEPARATORS = re.compile(r"[\s\-_.,:;()\[\]/]+")


def evaluation_display_entry_key(
    paper_id: int,
    task_id: int,
    dataset_id: int,
    model_name: str | None,
    harness: str | None,
) -> EvaluationDisplayEntryKey:
    """Match the frontend's paper/task/dataset/model/harness display grouping."""
    return (
        paper_id,
        task_id,
        dataset_id,
        model_name or "",
        harness or "",
    )


def serialize_evaluation_display_entry_key(key: EvaluationDisplayEntryKey) -> str:
    """Encode a display identity injectively for JSON report object keys."""
    return json.dumps(key, ensure_ascii=False, separators=(",", ":"))


def leaderboard_model_key(
    model_name: str | None, harness: str | None
) -> tuple[str, str]:
    """Identify one model's entry on a leaderboard, whichever paper it is filed on."""
    return (
        _MODEL_NAME_SEPARATORS.sub("", (model_name or "").casefold()),
        (harness or "").strip().casefold(),
    )
