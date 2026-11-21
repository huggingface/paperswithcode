"""Import PostTrainBench leaderboard rows as external evaluations on model paper pages.

Fetches aggregated scores from https://posttrainbench.com/scores.js and attaches
each agent's weighted-average Accuracy to its introducing paper with external=true.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_posttrainbench_external_evals.py
"""

from __future__ import annotations

import json
import logging
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

POSTTRAINBENCH_SOURCE_URL = "https://posttrainbench.com/"
SCORES_URL = "https://posttrainbench.com/scores.js"
SCORES_ASSIGNMENT = "window.SCORES_DATA = "
RESULTS_VERSION = "v1.1"
TASK_SLUG = "agents"
DATASET_SLUG = "posttrainbench"
METRIC = "Accuracy"

BASE_MODELS = [
    "Qwen3-1.7B-Base",
    "Qwen3-4B-Base",
    "SmolLM3-3B-Base",
    "gemma-3-4b-pt",
]

AGENT_SPECS: dict[str, dict] = {
    "fable-5": {
        "paper_id": 98110,
        "model_name": "Claude Fable 5 (1M, Max)",
        "harness": "Claude Code",
        "is_open": False,
        "methodology_note": (
            "Fable 5 uses Opus 4.8 Max scores for GPQA after Fable refused "
            "that benchmark."
        ),
    },
    "gpt-5.6-sol": {
        "paper_id": 102702,
        "model_name": "GPT-5.6 Sol (Max)",
        "harness": "Codex CLI",
        "is_open": False,
    },
    "opus-5": {
        "paper_id": 104561,
        "model_name": "Claude Opus 5",
        "harness": "Claude Code",
        "is_open": False,
        "methodology_note": "Single-run result; multi-seed results are pending.",
    },
    "grok-4.5-high": {
        "paper_id": 102703,
        "model_name": "Grok 4.5 (High)",
        "harness": "Cursor CLI",
        "is_open": False,
    },
    "kimi-k3": {
        "paper_id": 104584,
        "model_name": "Kimi K3",
        "harness": "Claude Code",
        "is_open": True,
        "hf_model_url": "https://huggingface.co/moonshotai/Kimi-K3",
        "num_parameters": 2_779_931_837_184,
        "methodology_note": "The agent used the model's 1M context window.",
    },
    "glm-5.2": {
        "paper_id": 98456,
        "model_name": "GLM-5.2 (Max)",
        "harness": "Claude Code",
        "is_open": True,
        "hf_model_url": "https://huggingface.co/zai-org/GLM-5.2",
        "num_parameters": 753_329_940_480,
    },
    "opus-4.8": {
        "paper_id": 97913,
        "model_name": "Claude Opus 4.8 (High)",
        "harness": "Claude Code",
        "is_open": False,
    },
    "opus-4.8-max": {
        "paper_id": 97913,
        "model_name": "Claude Opus 4.8 (Max)",
        "harness": "Claude Code",
        "is_open": False,
    },
    "opus-4.7": {
        "paper_id": 97914,
        "model_name": "Claude Opus 4.7 (xHigh)",
        "harness": "Claude Code",
        "is_open": False,
    },
    "gpt-5.5-xhigh": {
        "paper_id": 97922,
        "model_name": "GPT-5.5 (xHigh)",
        "harness": "Codex CLI",
        "is_open": False,
    },
    "gpt-5.4-high": {
        "paper_id": 97924,
        "model_name": "GPT-5.4 (High)",
        "harness": "Codex CLI",
        "is_open": False,
    },
    "gemini-3.1-pro": {
        "paper_id": 97943,
        "model_name": "Gemini 3.1 Pro",
        "harness": "OpenCode",
        "is_open": False,
    },
}


@dataclass
class LeaderboardEntry:
    agent_key: str
    average_score: float
    std_dev: float | None
    n_runs: int | None


def parse_scores_payload(source: str) -> dict:
    _, assignment, payload = source.partition(SCORES_ASSIGNMENT)
    if not assignment:
        raise RuntimeError("Unexpected PostTrainBench scores.js format")
    payload = payload.strip()
    if payload.endswith(";"):
        payload = payload[:-1]
    return json.loads(payload)


def fetch_scores_payload() -> dict:
    with urllib.request.urlopen(SCORES_URL, timeout=60) as resp:
        return parse_scores_payload(resp.read().decode())


def calculate_weighted_average(payload: dict, agent_key: str) -> float | None:
    model_benchmark_data = payload.get("modelBenchmarkData", {})
    if agent_key not in model_benchmark_data:
        return None

    benchmark_weights = payload["benchmarkWeights"]
    total = 0.0
    for model in BASE_MODELS:
        weighted_sum = 0.0
        for benchmark, weight in benchmark_weights.items():
            weighted_sum += (
                model_benchmark_data[agent_key][model][benchmark]["value"] * weight
            )
        total += weighted_sum
    return round(total / len(BASE_MODELS), 2)


def fetch_leaderboard_entries(payload: dict) -> list[LeaderboardEntry]:
    entries: list[LeaderboardEntry] = []
    aggregated = payload.get("aggregatedScores", {})

    for agent_key in AGENT_SPECS:
        if agent_key in aggregated:
            row = aggregated[agent_key]
            entries.append(
                LeaderboardEntry(
                    agent_key=agent_key,
                    average_score=float(row["avg"]),
                    std_dev=float(row["std"]) if row.get("std") is not None else None,
                    n_runs=int(row["n"]) if row.get("n") is not None else None,
                )
            )
            continue

        average = calculate_weighted_average(payload, agent_key)
        if average is None:
            raise RuntimeError(f"Missing PostTrainBench scores for {agent_key!r}")
        entries.append(
            LeaderboardEntry(
                agent_key=agent_key,
                average_score=average,
                std_dev=None,
                n_runs=None,
            )
        )

    return entries


def _get_task_and_dataset(session: Session) -> tuple[int, int]:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task {TASK_SLUG!r} not found")
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": DATASET_SLUG},
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Dataset {DATASET_SLUG!r} not found")
    return int(task.id), int(row[0])


def _delete_existing_rows(session: Session, task_id: int, dataset_id: int) -> int:
    deleted = session.execute(
        text(
            """
            DELETE FROM evaluations
            WHERE task_id = :task_id
              AND dataset_id = :dataset_id
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
        },
    ).rowcount
    session.flush()
    return deleted or 0


def _delete_misattributed_rows(
    session: Session, task_id: int, dataset_id: int, paper_ids: list[int]
) -> int:
    deleted = session.execute(
        text(
            """
            DELETE FROM evaluations
            WHERE task_id = :task_id
              AND dataset_id = :dataset_id
              AND paper_id = ANY(:paper_ids)
              AND COALESCE(source_url, '') <> :source_url
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "paper_ids": paper_ids,
            "source_url": POSTTRAINBENCH_SOURCE_URL,
        },
    ).rowcount
    session.flush()
    return deleted or 0


def _format_score(value: float) -> str:
    rounded = round(value, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}"


def _best_entry_per_paper(
    entries: list[LeaderboardEntry],
) -> tuple[list[LeaderboardEntry], list[str]]:
    """Keep only the highest-scoring variant when multiple agent keys map to one paper."""
    best_by_paper: dict[int, LeaderboardEntry] = {}
    skipped: list[str] = []

    for entry in entries:
        paper_id = AGENT_SPECS[entry.agent_key]["paper_id"]
        existing = best_by_paper.get(paper_id)
        if existing is None:
            best_by_paper[paper_id] = entry
            continue
        if entry.average_score > existing.average_score:
            skipped.append(
                f"{AGENT_SPECS[existing.agent_key]['model_name']}: "
                f"superseded by {AGENT_SPECS[entry.agent_key]['model_name']} "
                f"({existing.average_score:g}% -> {entry.average_score:g}%)"
            )
            best_by_paper[paper_id] = entry
        else:
            skipped.append(
                f"{AGENT_SPECS[entry.agent_key]['model_name']}: "
                f"lower score ({entry.average_score:g}%) than "
                f"{AGENT_SPECS[existing.agent_key]['model_name']} "
                f"({existing.average_score:g}%)"
            )

    return list(best_by_paper.values()), skipped


def import_rows(
    session: Session, task_id: int, dataset_id: int, payload: dict
) -> tuple[int, list[str]]:
    entries, variant_skipped = _best_entry_per_paper(fetch_leaderboard_entries(payload))
    skipped: list[str] = list(variant_skipped)
    created = 0

    for entry in entries:
        spec = AGENT_SPECS[entry.agent_key]
        paper_id = spec["paper_id"]
        model_name = spec["model_name"]
        harness = spec["harness"]

        methodology = (
            f"PostTrainBench {RESULTS_VERSION} weighted average across four base LLMs "
            "(Qwen3-1.7B, Qwen3-4B, SmolLM3-3B, Gemma-3-4B) and seven downstream "
            "benchmarks (AIME 2025, Arena Hard, BFCL, GPQA Main, GSM8K, HealthBench, "
            "HumanEval). Each agent had 10 hours on one H100 GPU. The v1.1 results "
            "apply independent contamination, API-usage, and benchmark-lookup audits "
            "plus programmatic model-identity checks."
        )
        methodology += f" Agent scaffold: {harness}."
        if entry.n_runs is not None:
            methodology += f" Reported mean over {entry.n_runs} runs."
        if entry.std_dev is not None:
            methodology += f" Std dev {entry.std_dev:g}%."
        if note := spec.get("methodology_note"):
            methodology += f" {note}"

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
                "harness": harness,
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
                harness=harness,
                methodology=methodology,
                metrics={METRIC: _format_score(entry.average_score)},
                best_metric=METRIC,
                external_source_url=POSTTRAINBENCH_SOURCE_URL,
                source_url=POSTTRAINBENCH_SOURCE_URL,
                external=True,
                is_open=spec["is_open"],
                hf_model_url=spec.get("hf_model_url"),
                num_parameters=spec.get("num_parameters"),
            )
        )
        created += 1

    session.flush()
    EvaluationService(session).recalculate_ranks(
        task_id, dataset_id, metric_name=METRIC
    )
    return created, skipped


def main() -> None:
    payload = fetch_scores_payload()
    paper_ids = sorted({spec["paper_id"] for spec in AGENT_SPECS.values()})

    with db_manager.session_local() as session:
        task_id, dataset_id = _get_task_and_dataset(session)
        deleted = _delete_existing_rows(session, task_id, dataset_id)
        misattributed = _delete_misattributed_rows(
            session, task_id, dataset_id, paper_ids
        )
        created, skipped = import_rows(session, task_id, dataset_id, payload)
        session.commit()
        logger.info("Deleted %d prior PostTrainBench rows", deleted)
        logger.info(
            "Deleted %d misattributed PostTrainBench rows on mapped papers",
            misattributed,
        )
        logger.info("Created %d PostTrainBench external evaluation rows", created)
        if skipped:
            logger.info("Skipped %d rows:", len(skipped))
            for line in skipped:
                logger.info("  - %s", line)


if __name__ == "__main__":
    main()
