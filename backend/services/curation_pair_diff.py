"""Compare a Pi shadow curation proposal with the Codex job it was paired with.

Both jobs started from the same frozen paper context, so every difference
between their proposals is a difference between the runners. Enrichment links
are compared as additions over that starting state; evaluations are matched on
``(task_id, dataset_id, metric)``. Only the disagreements need grading.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

PAIR_DIFF_VERSION = 1
ENRICH_ID_FIELDS = ("task_ids", "method_ids")
ENRICH_URL_FIELDS = ("repositories", "project_pages")
ENRICH_NAME_FIELDS = ("hf_models", "hf_datasets", "hf_spaces")


def _job_summary(row) -> dict[str, Any]:
    return {
        "job_id": str(row.id),
        "status": row.status,
        "error": (row.error or "")[:500] or None,
        "duration_ms": row.duration_ms,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "model": row.model,
    }


def _split(codex: set, pi: set) -> dict[str, list]:
    return {
        "both": sorted(codex & pi),
        "codex_only": sorted(codex - pi),
        "pi_only": sorted(pi - codex),
    }


def _starting_state(paper: dict) -> dict[str, set]:
    return {
        "task_ids": {item["id"] for item in paper.get("tasks") or []},
        "method_ids": {item["id"] for item in paper.get("methods") or []},
        "repositories": {item["url"] for item in paper.get("repositories") or []},
        "project_pages": {item["url"] for item in paper.get("project_pages") or []},
        "hf_models": set(paper.get("hf_models") or []),
        "hf_datasets": set(paper.get("hf_datasets") or []),
        "hf_spaces": set(paper.get("hf_spaces") or []),
    }


def _enrich_additions(enrich: dict | None, before: dict[str, set]) -> dict[str, set]:
    enrich = enrich or {}
    proposed = {
        **{field: set(enrich.get(field) or []) for field in ENRICH_ID_FIELDS},
        **{
            field: {link["url"] for link in enrich.get(field) or []}
            for field in ENRICH_URL_FIELDS
        },
        **{field: set(enrich.get(field) or []) for field in ENRICH_NAME_FIELDS},
    }
    # A field left out of the proposal keeps its current value: no additions.
    return {
        field: values - before[field] if enrich.get(field) is not None else set()
        for field, values in proposed.items()
    }


def _evaluation_cells(proposal: dict) -> dict[tuple[int, int, str], dict]:
    cells: dict[tuple[int, int, str], dict] = {}
    for item in proposal.get("evaluations") or []:
        for metric, value in (item.get("metrics") or {}).items():
            cells.setdefault(
                (int(item["task_id"]), int(item["dataset_id"]), str(metric)),
                {"model_name": item.get("model_name"), "value": value},
            )
    return cells


def _same_score(left: Any, right: Any) -> bool:
    try:
        return math.isclose(float(left), float(right), rel_tol=1e-3, abs_tol=0.01)
    except (TypeError, ValueError):
        return str(left).strip() == str(right).strip()


def _compare_evaluations(codex: dict, pi: dict) -> dict[str, list]:
    codex_cells, pi_cells = _evaluation_cells(codex), _evaluation_cells(pi)
    result: dict[str, list] = {
        "same": [],
        "different": [],
        "codex_only": [],
        "pi_only": [],
    }
    for key in sorted(codex_cells.keys() | pi_cells.keys()):
        cell = {"task_id": key[0], "dataset_id": key[1], "metric": key[2]}
        if key not in pi_cells:
            result["codex_only"].append({**cell, "codex": codex_cells[key]})
        elif key not in codex_cells:
            result["pi_only"].append({**cell, "pi": pi_cells[key]})
        elif _same_score(codex_cells[key]["value"], pi_cells[key]["value"]):
            result["same"].append({**cell, "value": codex_cells[key]["value"]})
        else:
            result["different"].append(
                {**cell, "codex": codex_cells[key], "pi": pi_cells[key]}
            )
    return result


def curation_pair_diff(codex_row, pi_row) -> dict[str, Any]:
    """Return the stored comparison of one terminal Codex/Pi job pair."""
    codex = codex_row.proposal or {}
    pi = pi_row.proposal or {}
    diff: dict[str, Any] = {
        "version": PAIR_DIFF_VERSION,
        "kind": pi_row.kind,
        "computed_at": datetime.now(UTC).isoformat(),
        "codex": _job_summary(codex_row),
        "pi": _job_summary(pi_row),
        "both_submitted": bool(codex_row.proposal and pi_row.proposal),
    }
    if pi_row.kind == "enrich-paper":
        before = _starting_state((pi_row.context_snapshot or {}).get("paper") or {})
        codex_added = _enrich_additions(codex.get("enrich"), before)
        pi_added = _enrich_additions(pi.get("enrich"), before)
        diff["enrich"] = {
            field: _split(codex_added[field], pi_added[field]) for field in before
        }
        diff["disagreements"] = sum(
            len(split["codex_only"]) + len(split["pi_only"])
            for split in diff["enrich"].values()
        )
    else:
        evaluations = _compare_evaluations(codex, pi)
        diff["evaluations"] = evaluations
        diff["benchmark_gaps"] = {
            "codex": len(codex.get("benchmark_gaps") or []),
            "pi": len(pi.get("benchmark_gaps") or []),
        }
        diff["evaluation_removals"] = {
            "codex": len(codex.get("evaluation_removals") or []),
            "pi": len(pi.get("evaluation_removals") or []),
        }
        diff["disagreements"] = sum(
            len(evaluations[name]) for name in ("different", "codex_only", "pi_only")
        )
    return diff
