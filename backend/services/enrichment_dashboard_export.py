"""Build a compact, read-only snapshot for the enrichment dashboard."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text


SCHEMA_VERSION = 1


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _rows(db: Any, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(query), params).mappings().all()]


def _day(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def build_snapshot(
    db: Any,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    """Return daily curation activity and details for an inclusive UTC range."""

    if end_date is None:
        end_date = datetime.now(timezone.utc).date()
    if start_date is None:
        start_date = date(2020, 1, 1)
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date")
    start_ts = datetime.combine(start_date, datetime.min.time(), timezone.utc)
    end_ts = datetime.combine(
        end_date + timedelta(days=1), datetime.min.time(), timezone.utc
    )
    params = {"start_ts": start_ts, "end_ts": end_ts}

    jobs = _rows(
        db,
        """
        SELECT id, paper_id, paper_title, kind, status, trigger, created_at,
               started_at, finished_at, applied_at, mutation_result, error
        FROM paper_curation_jobs
        WHERE trigger IN ('hf-daily-cron', 'hf-trending-cron')
          AND paper_id IS NOT NULL
          AND created_at >= :start_ts AND created_at < :end_ts
        ORDER BY created_at, id
        """,
        params,
    )
    paper_ids = sorted({int(row["paper_id"]) for row in jobs})

    evaluations: list[dict[str, Any]] = []
    if paper_ids:
        evaluations = _rows(
            db,
            """
            SELECT e.id, e.paper_id, p.title AS paper_title, t.name AS task,
                   d.name AS dataset, e.model_name, e.harness, e.best_metric,
                   e.metrics, e.source_url, e.created_at
            FROM evaluations e
            JOIN papers p ON p.id = e.paper_id
            JOIN tasks t ON t.id = e.task_id
            JOIN datasets d ON d.id = e.dataset_id
            WHERE e.paper_id = ANY(:paper_ids)
              AND e.created_at >= :start_ts AND e.created_at < :end_ts
            ORDER BY e.created_at, e.id
            """,
            {**params, "paper_ids": paper_ids},
        )

    gaps = _rows(
        db,
        """
        SELECT c.identity_key, c.canonical_name, c.gap_type, c.canonical_url,
               c.status AS review_status, c.distinct_paper_count,
               c.review_reason, c.reviewed_at, c.resolution,
               p.id AS paper_id, p.title AS paper_title, e.created_at
        FROM benchmark_curation_candidates c
        JOIN benchmark_curation_evidence e ON e.candidate_id = c.id
        JOIN papers p ON p.id = e.paper_id
        WHERE e.created_at >= :start_ts AND e.created_at < :end_ts
        ORDER BY e.created_at, c.canonical_name, p.id
        """,
        params,
    )
    trending_models = _rows(
        db,
        """
        SELECT c.repo_id, c.author, c.status, c.rejection_reason,
               c.featured_publisher, c.trending_score, c.readme_revision,
               c.first_seen_at, c.processed_at, r.canonical_name,
               r.publisher, r.is_open, r.paper_id, p.title AS paper_title
        FROM trending_model_candidates c
        LEFT JOIN model_releases r ON r.id = c.model_release_id
        LEFT JOIN papers p ON p.id = r.paper_id
        WHERE COALESCE(c.processed_at, c.first_seen_at) >= :start_ts
          AND COALESCE(c.processed_at, c.first_seen_at) < :end_ts
        ORDER BY COALESCE(c.processed_at, c.first_seen_at), c.repo_id
        """,
        params,
    )
    trending_model_decisions = _rows(
        db,
        """
        SELECT c.repo_id, c.author, c.readme_revision, c.status AS candidate_status,
               j.id AS job_id, j.status AS job_status, j.model, j.proposal,
               j.validation_summary, j.mutation_result, j.error, j.trace_uri,
               j.created_at, j.started_at, j.finished_at, j.applied_at
        FROM paper_curation_jobs j
        JOIN trending_model_candidates c ON c.id = j.candidate_id
        WHERE j.kind = 'resolve-model-paper'
          AND j.created_at >= :start_ts AND j.created_at < :end_ts
        ORDER BY j.created_at, j.id
        """,
        params,
    )
    benchmark_gap_jobs = _rows(
        db,
        """
        SELECT j.id AS job_id, j.kind, j.status AS job_status,
               j.benchmark_candidate_id, c.canonical_name, c.status AS candidate_status,
               j.mutation_result, j.error, j.trace_uri, j.created_at, j.finished_at,
               j.applied_at
        FROM paper_curation_jobs j
        LEFT JOIN benchmark_curation_candidates c ON c.id = j.benchmark_candidate_id
        WHERE j.kind IN ('review-benchmark-gaps', 'add-benchmark')
          AND j.created_at >= :start_ts AND j.created_at < :end_ts
        ORDER BY j.created_at, j.id
        """,
        params,
    )

    daily: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "enrichment_jobs": 0,
            "enrichment_applied": 0,
            "enrichment_noops": 0,
            "enrichment_failed": 0,
            "evaluation_jobs": 0,
            "evaluations_created": 0,
            "benchmark_gap_reports": 0,
        }
    )
    papers: list[dict[str, Any]] = []
    for row in jobs:
        day = _day(row["created_at"])
        stats = daily[day]
        if row["kind"] == "enrich-paper":
            stats["enrichment_jobs"] += 1
            if row["status"] == "failed":
                stats["enrichment_failed"] += 1
            elif (row.get("mutation_result") or {}).get("status") == "no_changes":
                stats["enrichment_noops"] += 1
            elif row["status"] == "completed":
                stats["enrichment_applied"] += 1
        else:
            stats["evaluation_jobs"] += 1
            result = row.get("mutation_result") or {}
            stats["evaluations_created"] += int(
                result.get("evaluations_created", 0) or 0
            )
        if row["kind"] == "enrich-paper":
            result = row.get("mutation_result") or {}
            papers.append(
                {
                    "day": day,
                    "paper_id": row["paper_id"],
                    "title": row["paper_title"],
                    "job_id": str(row["id"]),
                    "trigger": row.get("trigger"),
                    "status": row["status"],
                    "mutation_status": result.get("status"),
                    "error": row.get("error"),
                }
            )

    for row in evaluations:
        day = _day(row["created_at"])
        daily[day]["evaluations_created"] += 0  # counted from job result above

    unique_gaps: dict[tuple[str, str], dict[str, Any]] = {}
    for row in gaps:
        key = (row["identity_key"], _day(row["created_at"]))
        existing = unique_gaps.get(key)
        if existing is None:
            unique_gaps[key] = {**row, "source_papers": [row["paper_title"]]}
        elif row["paper_title"] not in existing["source_papers"]:
            existing["source_papers"].append(row["paper_title"])
    for row in unique_gaps.values():
        daily[_day(row["created_at"])]["benchmark_gap_reports"] += 1

    def clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_json_safe(row) for row in rows]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": [{"day": day, **daily[day]} for day in sorted(daily)],
        "papers": papers,
        "evaluations": clean(evaluations),
        "benchmark_gaps": clean(list(unique_gaps.values())),
        "trending_models": clean(trending_models),
        "trending_model_decisions": clean(trending_model_decisions),
        "benchmark_gap_jobs": clean(benchmark_gap_jobs),
    }


def write_snapshot(snapshot: dict[str, Any], path: str | Path) -> None:
    """Write a validated snapshot atomically."""

    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported snapshot schema")
    if not snapshot.get("generated_at"):
        raise ValueError("snapshot has no generated_at")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_json_safe(snapshot), indent=2, sort_keys=True) + "\n"
    )
    temporary.replace(target)
