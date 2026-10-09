"""Import DeepSWE leaderboard rows as external evaluations on model paper pages.

Fetches the v1.1 "Best" leaderboard from https://deepswe.datacurve.ai/ and
attaches each model's Pass@1 score to its introducing paper with external=true.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_deepswe_external_evals.py
"""

from __future__ import annotations

import logging
import re
import urllib.request
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation, Task as DBTask
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DEEPSWE_SOURCE_URL = "https://deepswe.datacurve.ai/"
TASK_SLUG = "coding-agents"
DATASET_SLUG = "deepswe"
METRIC = "Pass@1"
HARNESS = "MiniSWE-Agent"

# Effort level used on the public "Best" leaderboard table for each model slug.
BEST_EFFORT_BY_MODEL: dict[str, str] = {
    "claude-fable-5": "max",
    "gpt-5-5": "xhigh",
    "claude-opus-4-8": "max",
    "gpt-5-4": "xhigh",
    "gemini-3-5-flash": "medium",
    "kimi-k2-7-code": "",
    "claude-sonnet-4-6": "high",
    "gemini-3-1-pro-preview": "high",
}

DISPLAY_NAME_BY_MODEL: dict[str, str] = {
    "claude-fable-5": "Claude Fable 5",
    "gpt-5-5": "GPT-5.5",
    "claude-opus-4-8": "Claude Opus 4.8",
    "gpt-5-4": "GPT-5.4",
    "gemini-3-5-flash": "Gemini 3.5 Flash",
    "kimi-k2-7-code": "Kimi K2.7 Code",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "gemini-3-1-pro-preview": "Gemini 3.1 Pro",
}

MODEL_PAPER_IDS: dict[str, int] = {
    "claude-fable-5": 98110,
    "gpt-5-5": 97922,
    "claude-opus-4-8": 97913,
    "gpt-5-4": 97924,
    "kimi-k2-7-code": 98265,
    "claude-sonnet-4-6": 97925,
    "gemini-3-1-pro-preview": 97943,
}

CLOSED_MODELS = {
    "claude-fable-5",
    "gpt-5-5",
    "claude-opus-4-8",
    "gpt-5-4",
    "gemini-3-5-flash",
    "claude-sonnet-4-6",
    "gemini-3-1-pro-preview",
}

ENTRY_PATTERN = re.compile(
    r"model:\"([^\"]+)\",harness:\"([^\"]+)\",reasoning_effort:(null|\"[^\"]*\"),"
    r"config:\"([^\"]+)\",source:\"([^\"]+)\",pass_rate:([0-9.]+),pass_at_1:([0-9.]+),"
    r"pass_at_4:([0-9.]+),n_passed:([0-9]+),n_attempted:([0-9]+),"
    r"n_tasks_attempted:([0-9]+),n_tasks_passed_any:([0-9]+),ci_passed:([0-9]+),"
    r"ci_attempted:([0-9]+),ci_lo:([0-9.]+),ci_hi:([0-9.]+),ci_half:([0-9.]+)"
)


@dataclass
class LeaderboardEntry:
    model_slug: str
    harness: str
    reasoning_effort: str
    pass_at_1: float
    ci_half: float
    mean_cost_usd: float | None
    mean_output_tokens: float | None
    mean_agent_steps: float | None


def _parse_reasoning_effort(raw: str) -> str:
    if raw == "null":
        return ""
    return raw[1:-1]


def _parse_tail_fields(
    html: str, start: int
) -> tuple[float | None, float | None, float | None]:
    tail = html[start : start + 1200]
    cost_m = re.search(r"mean_cost_usd:([0-9.]+)", tail)
    out_m = re.search(r"mean_output_tokens:([0-9.]+)", tail)
    steps_m = re.search(r"mean_agent_steps:([0-9.]+)", tail)
    cost = float(cost_m.group(1)) if cost_m else None
    out_tokens = float(out_m.group(1)) if out_m else None
    steps = float(steps_m.group(1)) if steps_m else None
    return cost, out_tokens, steps


def fetch_leaderboard_entries() -> list[LeaderboardEntry]:
    with urllib.request.urlopen(DEEPSWE_SOURCE_URL, timeout=60) as resp:
        html = resp.read().decode()

    entries: list[LeaderboardEntry] = []
    for match in ENTRY_PATTERN.finditer(html):
        cost, out_tokens, steps = _parse_tail_fields(html, match.end())
        entries.append(
            LeaderboardEntry(
                model_slug=match.group(1),
                harness=match.group(2),
                reasoning_effort=_parse_reasoning_effort(match.group(3)),
                pass_at_1=float(match.group(7)),
                ci_half=float(match.group(17)),
                mean_cost_usd=cost,
                mean_output_tokens=out_tokens,
                mean_agent_steps=steps,
            )
        )

    if not entries:
        raise RuntimeError("Could not parse DeepSWE leaderboard from homepage HTML")

    selected: list[LeaderboardEntry] = []
    for model_slug, effort in BEST_EFFORT_BY_MODEL.items():
        matches = [
            entry
            for entry in entries
            if entry.model_slug == model_slug and entry.reasoning_effort == effort
        ]
        if not matches:
            raise RuntimeError(
                f"Missing DeepSWE row for {model_slug!r} effort={effort!r}"
            )
        selected.append(matches[0])

    return selected


def _display_model_name(model_slug: str, reasoning_effort: str) -> str:
    base = DISPLAY_NAME_BY_MODEL.get(model_slug, model_slug)
    if reasoning_effort:
        return f"{base} ({reasoning_effort})"
    return base


def _get_task_and_dataset(session: Session) -> tuple[int, int]:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task {TASK_SLUG!r} not found")
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": DATASET_SLUG},
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"Dataset {DATASET_SLUG!r} not found; run add_deepswe_benchmark.py first"
        )
    return int(task.id), int(row[0])


def _delete_existing_rows(session: Session, task_id: int, dataset_id: int) -> int:
    deleted = session.execute(
        text(
            """
            DELETE FROM evaluations
            WHERE task_id = :task_id
              AND dataset_id = :dataset_id
              AND source_url = :source_url
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "source_url": DEEPSWE_SOURCE_URL,
        },
    ).rowcount
    session.flush()
    return deleted or 0


def import_rows(
    session: Session, task_id: int, dataset_id: int
) -> tuple[int, list[str]]:
    entries = fetch_leaderboard_entries()
    skipped: list[str] = []
    created = 0

    for entry in entries:
        paper_id = MODEL_PAPER_IDS.get(entry.model_slug)
        if paper_id is None:
            skipped.append(f"{entry.model_slug}: no local paper row")
            continue

        model_name = _display_model_name(entry.model_slug, entry.reasoning_effort)
        pass_pct = round(entry.pass_at_1 * 100)
        ci_pct = round(entry.ci_half * 100, 1)
        methodology = (
            f"DeepSWE v1.1 Best leaderboard (independent source). "
            f"Pass@1 {pass_pct:g}% ±{ci_pct:g}% on 113 tasks via {HARNESS}. "
            f"Reasoning effort: {entry.reasoning_effort or 'default'}."
        )
        if entry.mean_cost_usd is not None:
            methodology += f" Avg cost ${entry.mean_cost_usd:.2f}/task."
        if entry.mean_output_tokens is not None:
            methodology += f" Mean output tokens {entry.mean_output_tokens:,.0f}."
        if entry.mean_agent_steps is not None:
            methodology += f" Mean agent steps {entry.mean_agent_steps:.0f}."

        existing = session.execute(
            text(
                """
                SELECT id FROM evaluations
                WHERE paper_id = :paper_id
                  AND task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND model_name = :model_name
                  AND COALESCE(harness, '') = :harness
                  AND best_metric = :best_metric
                """
            ),
            {
                "paper_id": paper_id,
                "task_id": task_id,
                "dataset_id": dataset_id,
                "model_name": model_name,
                "harness": HARNESS,
                "best_metric": METRIC,
            },
        ).first()
        if existing:
            skipped.append(f"{model_name}: duplicate row already exists")
            continue

        session.add(
            DBEvaluation(
                paper_id=paper_id,
                task_id=task_id,
                dataset_id=dataset_id,
                model_name=model_name,
                harness=HARNESS,
                methodology=methodology,
                metrics={METRIC: entry.pass_at_1},
                best_metric=METRIC,
                external_source_url=DEEPSWE_SOURCE_URL,
                source_url=DEEPSWE_SOURCE_URL,
                external=True,
                is_open=entry.model_slug not in CLOSED_MODELS,
            )
        )
        created += 1

    session.flush()
    EvaluationService(session).recalculate_ranks(
        task_id, dataset_id, metric_name=METRIC
    )
    return created, skipped


def main() -> None:
    with db_manager.session_local() as session:
        task_id, dataset_id = _get_task_and_dataset(session)
        deleted = _delete_existing_rows(session, task_id, dataset_id)
        created, skipped = import_rows(session, task_id, dataset_id)
        session.commit()
        logger.info("Deleted %d prior DeepSWE rows", deleted)
        logger.info("Created %d DeepSWE external evaluation rows", created)
        if skipped:
            logger.info("Skipped %d rows:", len(skipped))
            for line in skipped:
                logger.info("  - %s", line)


if __name__ == "__main__":
    main()
