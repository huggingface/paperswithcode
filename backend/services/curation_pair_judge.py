"""Blind LLM judge for Codex/Pi shadow curation pairs, and the cutover gates.

``pair_diff`` lists where the two runners disagree. The judge grades each
disagreeing proposal (a tag, a link, a leaderboard row) against the paper
without seeing which runner proposed it: candidates are shuffled by a hash and
labelled ``c1``, ``c2``, … Agreed proposals are taken as correct. The verdicts
are stored on the Pi job as ``pair_judgment`` and summed by ``gate_report``
into the per-stage gates that decide whether Pi can replace Codex.
"""

from __future__ import annotations

import hashlib
import json
import logging
import statistics
from datetime import UTC, datetime
from typing import Any, Literal

import anthropic
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import Dataset, Method, PaperCurationJob, Task
from backend.services.paper_markdown_service import read_paper_markdown_bounded

logger = logging.getLogger(__name__)

JUDGE_VERSION = 1
MARKDOWN_MAX_BYTES = 300 * 1024
MAX_PAUSE_CONTINUATIONS = 4

MIN_PAIRS = 100
SUCCESS_MARGIN = 0.03
TAG_PRECISION_MARGIN = 0.05
MAX_DURATION_RATIO = 1.5

ENRICH_FIELD_LABELS = {
    "task_ids": "task tag",
    "method_ids": "method tag",
    "repositories": "official code repository",
    "project_pages": "official project page",
    "hf_models": "Hugging Face model released with this paper",
    "hf_datasets": "Hugging Face dataset released with this paper",
    "hf_spaces": "Hugging Face Space released with this paper",
}
TAG_FIELDS = ("task_ids", "method_ids")

SYSTEM_PROMPT = """\
You audit proposals made by automated curators for a Papers with Code paper \
page. Each candidate below was proposed by one curator and not by another, so \
it is disputed. Grade every candidate on its own merits against the paper.

Rules the curators were given:
- Task and method tags: tag only what the paper is genuinely about: the tasks \
it addresses and the methods it introduces or substantially uses. Incidental \
mentions, related work and baselines it merely compares against are wrong. \
Prefer the specific tag when a specific and a generic one both fit.
- Repositories and project pages: only the paper's own official artifact. A \
repository of a baseline, dataset, framework or website template is wrong.
- Hugging Face models, datasets and Spaces: only artifacts released by the \
paper's authors as part of this work, not base models or third-party uploads.
- Leaderboard rows: only models or configurations the paper introduces, never \
comparison baselines. One row per leaderboard (task, benchmark, metric): the \
best result the paper reports for its own models there, with the exact value \
the paper prints, on the same benchmark version, split and setting.

Verdicts:
- correct: the candidate should be on the page as proposed.
- incorrect: it should not be on the page (wrong tag, unofficial link, \
baseline row, wrong benchmark, metric, split or setting, or not the best \
introduced-model row).
- wrong_score: leaderboard rows only, when the row itself is legitimate but \
its value does not match what the paper reports.
- unsure: the evidence does not settle it. Use this rarely.

Use web_fetch on a candidate URL when the paper text does not settle it. Give \
a verdict for every candidate id, with a one-sentence reason citing evidence \
(a section, table or page)."""


class CandidateVerdict(BaseModel):
    candidate_id: str
    verdict: Literal["correct", "incorrect", "wrong_score", "unsure"]
    reason: str


class JudgeOutput(BaseModel):
    verdicts: list[CandidateVerdict]


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def _proposal_rows(proposal: dict | None) -> dict[tuple[int, int, str], dict]:
    rows: dict[tuple[int, int, str], dict] = {}
    for item in (proposal or {}).get("evaluations") or []:
        for metric in item.get("metrics") or {}:
            key = (int(item["task_id"]), int(item["dataset_id"]), str(metric))
            rows.setdefault(key, item)
    return rows


def _names(db: Session, model, ids: set[int]) -> dict[int, Any]:
    if not ids:
        return {}
    return {row.id: row for row in db.scalars(select(model).where(model.id.in_(ids)))}


def _taxonomy_text(row) -> str:
    if row is None:
        return "(unknown id)"
    description = " ".join((row.description or "").split())[:400]
    return f"{row.name}: {description}" if description else row.name


def disagreement_candidates(
    db: Session, pi_row: PaperCurationJob, codex_row: PaperCurationJob
) -> list[dict[str, Any]]:
    """Return one candidate per disputed proposal, with its hidden origin.

    The ``prompt`` text is what the judge sees; ``origin`` (codex or pi) is
    never sent. A value conflict on one leaderboard cell becomes two candidates
    sharing a ``conflict`` key.
    """
    diff = pi_row.pair_diff or {}
    candidates: list[dict[str, Any]] = []
    if diff.get("kind") == "enrich-paper":
        enrich = diff.get("enrich") or {}
        ids = {
            field: {
                v for side in ("codex_only", "pi_only") for v in enrich[field][side]
            }
            for field in TAG_FIELDS
            if field in enrich
        }
        lookup = {
            "task_ids": _names(db, Task, ids.get("task_ids", set())),
            "method_ids": _names(db, Method, ids.get("method_ids", set())),
        }
        for field, split in enrich.items():
            for side in ("codex_only", "pi_only"):
                for value in split[side]:
                    shown = (
                        _taxonomy_text(lookup[field].get(value))
                        if field in TAG_FIELDS
                        else str(value)
                    )
                    candidates.append(
                        {
                            "field": field,
                            "value": value,
                            "origin": side.removesuffix("_only"),
                            "prompt": f"{ENRICH_FIELD_LABELS[field]}: {shown}",
                        }
                    )
    else:
        evaluations = diff.get("evaluations") or {}
        cells = [
            (cell, side, cell[side.removesuffix("_only")])
            for side in ("codex_only", "pi_only")
            for cell in evaluations.get(side) or []
        ] + [
            (cell, origin, cell[origin])
            for cell in evaluations.get("different") or []
            for origin in ("codex", "pi")
        ]
        datasets = _names(db, Dataset, {int(c["dataset_id"]) for c, _, _ in cells})
        tasks = _names(db, Task, {int(c["task_id"]) for c, _, _ in cells})
        proposals = {
            "codex": _proposal_rows(codex_row.proposal),
            "pi": _proposal_rows(pi_row.proposal),
        }
        for cell, side, row in cells:
            origin = side.removesuffix("_only")
            key = (int(cell["task_id"]), int(cell["dataset_id"]), str(cell["metric"]))
            methodology = (proposals[origin].get(key) or {}).get("methodology") or ""
            dataset = datasets.get(key[1])
            task = tasks.get(key[0])
            candidates.append(
                {
                    "field": "evaluation",
                    "value": {**cell_key(cell), **row},
                    "origin": origin,
                    "conflict": "|".join(map(str, key))
                    if side in ("codex", "pi")
                    else None,
                    "prompt": (
                        "leaderboard row: "
                        f"task {task.name if task else key[0]}, "
                        f"benchmark {dataset.name if dataset else key[1]}, "
                        f"metric {key[2]}, model {row.get('model_name')!r}, "
                        f"value {row.get('value')}. "
                        f"Curator's note: {' '.join(methodology.split())[:600]}"
                    ),
                }
            )
    # Blind order: a hash of the pair and the candidate, never the origin alone.
    candidates.sort(
        key=lambda c: _hash(
            pi_row.id, c["field"], json.dumps(c["value"], sort_keys=True), c["origin"]
        )
    )
    for index, candidate in enumerate(candidates, start=1):
        candidate["id"] = f"c{index}"
    return candidates


def cell_key(cell: dict) -> dict:
    return {key: cell[key] for key in ("task_id", "dataset_id", "metric")}


def _paper_text(paper: dict, settings: Settings) -> str:
    arxiv_id = paper.get("arxiv_id")
    source = "arxiv" if arxiv_id else "external"
    try:
        markdown, truncated = read_paper_markdown_bounded(
            str(arxiv_id or paper.get("id")),
            source=source,
            bucket_id=settings.paper_markdown_hf_bucket_id,
            token=settings.hf_token or None,
            max_bytes=MARKDOWN_MAX_BYTES,
        )
    except ValueError as error:
        logger.warning("No Markdown for paper %s: %s", paper.get("id"), error)
        return "(Full text unavailable; judge from the abstract and links.)"
    return markdown + ("\n\n(Full text truncated.)" if truncated else "")


def build_prompt(paper: dict, paper_text: str, candidates: list[dict]) -> str:
    lines = [f"- {c['id']}: {c['prompt']}" for c in candidates]
    links = [
        paper.get("source_url"),
        *(r.get("url") for r in paper.get("repositories") or []),
    ]
    return "\n".join(
        [
            f"Paper: {paper.get('title')}",
            f"arXiv: {paper.get('arxiv_id') or 'none'}",
            f"Abstract: {paper.get('abstract') or '(none)'}",
            "Known links: " + ", ".join(link for link in links if link),
            "",
            "Disputed candidates:",
            *lines,
            "",
            "<paper_text>",
            paper_text,
            "</paper_text>",
        ]
    )


def _ask_judge(
    client: anthropic.Anthropic, model: str, prompt: str
) -> tuple[JudgeOutput, dict[str, int]]:
    messages: list[dict] = [{"role": "user", "content": prompt}]
    usage = {"input_tokens": 0, "output_tokens": 0}
    for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
        response = client.beta.messages.parse(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=[{"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8}],
            output_config={"effort": "high"},
            output_format=JudgeOutput,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise RuntimeError(f"Judge returned no verdicts ({response.stop_reason})")
        return response.parsed_output, usage
    raise RuntimeError("Judge kept pausing")


def judge_pair(
    db: Session,
    pi_row: PaperCurationJob,
    codex_row: PaperCurationJob,
    *,
    client: anthropic.Anthropic,
    settings: Settings,
) -> dict[str, Any]:
    """Grade one pair's disagreements and return the judgment to store."""
    candidates = disagreement_candidates(db, pi_row, codex_row)
    judgment: dict[str, Any] = {
        "version": JUDGE_VERSION,
        "kind": pi_row.kind,
        "judged_at": datetime.now(UTC).isoformat(),
        "model": None,
        "usage": None,
        "candidates": [],
    }
    if not candidates:
        return judgment
    paper = (pi_row.context_snapshot or {}).get("paper") or {}
    prompt = build_prompt(paper, _paper_text(paper, settings), candidates)
    output, usage = _ask_judge(client, settings.curation_judge_model, prompt)
    verdicts = {v.candidate_id: v for v in output.verdicts}
    for candidate in candidates:
        verdict = verdicts.get(candidate["id"])
        judgment["candidates"].append(
            {
                "id": candidate["id"],
                "field": candidate["field"],
                "value": candidate["value"],
                "origin": candidate["origin"],
                "conflict": candidate.get("conflict"),
                "verdict": verdict.verdict if verdict else "unsure",
                "reason": verdict.reason if verdict else "No verdict returned.",
            }
        )
    judgment["model"] = settings.curation_judge_model
    judgment["usage"] = usage
    return judgment


def judge_pending_pairs(
    db: Session, settings: Settings, *, limit: int, kind: str | None = None
) -> dict[str, int]:
    """Judge compared pairs that have no judgment yet, oldest first."""
    if not settings.curation_judge_anthropic_api_key:
        raise ValueError("PWC_CURATION_JUDGE_ANTHROPIC_API_KEY is not configured")
    client = anthropic.Anthropic(
        api_key=settings.curation_judge_anthropic_api_key, max_retries=4
    )
    query = (
        select(PaperCurationJob)
        .where(
            PaperCurationJob.runner == "pi",
            PaperCurationJob.pair_diff.isnot(None),
            PaperCurationJob.pair_judgment.is_(None),
        )
        .order_by(PaperCurationJob.created_at)
        .limit(limit)
    )
    if kind:
        query = query.where(PaperCurationJob.kind == kind)
    counts = {"judged": 0, "failed": 0, "candidates": 0}
    for pi_row in db.scalars(query).all():
        codex_row = db.get(PaperCurationJob, pi_row.paired_job_id)
        if codex_row is None:
            continue
        try:
            judgment = judge_pair(
                db, pi_row, codex_row, client=client, settings=settings
            )
        except (anthropic.APIError, RuntimeError) as error:
            logger.error("Judging pair %s failed: %s", pi_row.id, error)
            counts["failed"] += 1
            continue
        pi_row.pair_judgment = judgment
        db.commit()
        counts["judged"] += 1
        counts["candidates"] += len(judgment["candidates"])
    return counts


def _precision(correct: int, graded: int) -> float | None:
    return round(correct / graded, 4) if graded else None


def _stage_report(pairs: list[PaperCurationJob], kind: str) -> dict[str, Any]:
    runners = ("codex", "pi")
    completed = {r: 0 for r in runners}
    durations: dict[str, list[int]] = {r: [] for r in runners}
    correct = {r: 0 for r in runners}
    graded = {r: 0 for r in runners}
    wrong_scores = {r: 0 for r in runners}
    unsure = 0
    judged = 0
    for row in pairs:
        diff = row.pair_diff
        for runner in runners:
            completed[runner] += diff[runner]["status"] == "completed"
            if diff[runner]["duration_ms"]:
                durations[runner].append(diff[runner]["duration_ms"])
        if row.pair_judgment is None:
            continue
        judged += 1
        if kind == "enrich-paper":
            agreed = sum(len(diff["enrich"][f]["both"]) for f in TAG_FIELDS)
        else:
            agreed = len(diff["evaluations"]["same"])
        for runner in runners:
            correct[runner] += agreed
            graded[runner] += agreed
        for candidate in row.pair_judgment["candidates"]:
            if kind == "enrich-paper" and candidate["field"] not in TAG_FIELDS:
                continue
            if candidate["verdict"] == "unsure":
                unsure += 1
                continue
            graded[candidate["origin"]] += 1
            correct[candidate["origin"]] += candidate["verdict"] == "correct"
            wrong_scores[candidate["origin"]] += candidate["verdict"] == "wrong_score"

    total = len(pairs)
    success = {r: _precision(completed[r], total) for r in runners}
    precision = {r: _precision(correct[r], graded[r]) for r in runners}
    medians = {
        r: statistics.median(durations[r]) if durations[r] else None for r in runners
    }
    ratio = (
        round(medians["pi"] / medians["codex"], 3)
        if medians["pi"] and medians["codex"]
        else None
    )
    gates = {
        "enough_pairs": total >= MIN_PAIRS,
        "all_judged": judged == total,
        "success": success["pi"] is not None
        and success["pi"] >= success["codex"] - SUCCESS_MARGIN,
        "median_time": ratio is not None and ratio <= MAX_DURATION_RATIO,
    }
    have_precision = None not in precision.values()
    if kind == "enrich-paper":
        gates["tag_precision"] = have_precision and (
            precision["pi"] >= precision["codex"] - TAG_PRECISION_MARGIN
        )
    else:
        gates["eval_precision"] = (
            have_precision and precision["pi"] >= precision["codex"]
        )
        gates["wrong_scores"] = wrong_scores["pi"] <= wrong_scores["codex"]
    return {
        "pairs": total,
        "judged": judged,
        "success_rate": success,
        "median_duration_s": {r: m and round(m / 1000, 1) for r, m in medians.items()},
        "duration_ratio": ratio,
        ("tag_precision" if kind == "enrich-paper" else "eval_precision"): precision,
        "graded": graded,
        "unsure": unsure,
        **({"wrong_scores": wrong_scores} if kind == "add-evals" else {}),
        "gates": gates,
        "passes": all(gates.values()),
    }


def gate_report(db: Session) -> dict[str, Any]:
    """Sum stored diffs and judgments into the per-stage cutover gates."""
    rows = db.scalars(
        select(PaperCurationJob).where(
            PaperCurationJob.runner == "pi", PaperCurationJob.pair_diff.isnot(None)
        )
    ).all()
    return {
        kind: _stage_report([r for r in rows if r.kind == kind], kind)
        for kind in ("enrich-paper", "add-evals")
    }
