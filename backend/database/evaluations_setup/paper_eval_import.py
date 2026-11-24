"""Canonical primitives for small, paper-native evaluation imports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import text

from backend.models.database import Evaluation
from backend.services.evaluation_service import EvaluationService


def resolve_scope(
    db,
    *,
    arxiv_id: str,
    task_slug: str,
    dataset_slugs: Iterable[str],
) -> tuple[int, int, dict[str, int]]:
    paper_ids = (
        db.execute(
            text(
                """SELECT id FROM papers
               WHERE arxiv_id = :arxiv_id AND is_latest_version
               ORDER BY id"""
            ),
            {"arxiv_id": arxiv_id},
        )
        .scalars()
        .all()
    )
    if len(paper_ids) != 1:
        raise RuntimeError(f"Expected one latest paper for {arxiv_id}: {paper_ids}")

    task_id = db.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"), {"slug": task_slug}
    ).scalar_one_or_none()
    if task_id is None:
        raise RuntimeError(f"Missing task {task_slug!r}")

    requested_slugs = set(dataset_slugs)
    rows = db.execute(
        text("SELECT id, slug FROM datasets WHERE slug = ANY(:slugs)"),
        {"slugs": sorted(requested_slugs)},
    ).mappings()
    dataset_ids = {row["slug"]: int(row["id"]) for row in rows}
    missing = requested_slugs - dataset_ids.keys()
    if missing:
        raise RuntimeError(f"Missing configured datasets: {sorted(missing)}")
    return int(paper_ids[0]), int(task_id), dataset_ids


def validate_leaderboard(
    db,
    *,
    task_id: int,
    dataset_id: int,
    dataset_slug: str,
    metrics: Iterable[str],
    best_metric: str,
) -> None:
    row = (
        db.execute(
            text(
                """SELECT td.supports_harness,
                      array_agg(m.name ORDER BY m.name) AS metrics
               FROM task_datasets td
               JOIN task_dataset_metrics tdm
                 ON tdm.task_id = td.task_id AND tdm.dataset_id = td.dataset_id
               JOIN metrics m ON m.id = tdm.metric_id
               WHERE td.task_id = :task_id AND td.dataset_id = :dataset_id
               GROUP BY td.supports_harness"""
            ),
            {"task_id": task_id, "dataset_id": dataset_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError(f"No configured leaderboard for {dataset_slug!r}")
    if row["supports_harness"]:
        raise RuntimeError(f"{dataset_slug!r} unexpectedly supports harness")
    allowed = set(row["metrics"])
    outgoing = set(metrics)
    if not outgoing <= allowed or best_metric not in allowed:
        raise RuntimeError(
            f"Invalid metrics for {dataset_slug}: "
            f"outgoing={sorted(outgoing)}, allowed={sorted(allowed)}"
        )


def upsert_evaluation(
    db,
    service: EvaluationService,
    *,
    paper_id: int,
    task_id: int,
    dataset_id: int,
    model_name: str,
    metrics: Mapping[str, Any],
    methodology: str,
    best_metric: str,
    source_url: str,
    num_parameters: int | None = None,
    hf_model_url: str | None = None,
) -> tuple[str, int]:
    existing = (
        db.execute(
            text(
                """SELECT id, metrics, methodology, is_open, source_url,
                      num_parameters, hf_model_url
               FROM evaluations
               WHERE paper_id = :paper_id
                 AND task_id = :task_id
                 AND dataset_id = :dataset_id
                 AND model_name = :model_name
                 AND harness IS NULL
                 AND best_metric = :best_metric"""
            ),
            {
                "paper_id": paper_id,
                "task_id": task_id,
                "dataset_id": dataset_id,
                "model_name": model_name,
                "best_metric": best_metric,
            },
        )
        .mappings()
        .one_or_none()
    )
    desired = {
        "metrics": dict(metrics),
        "methodology": methodology,
        "is_open": True,
        "source_url": source_url,
        "num_parameters": num_parameters,
        "hf_model_url": hf_model_url,
    }
    if existing is None:
        created = service.create_evaluation(
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            model_name=model_name,
            metrics=dict(metrics),
            methodology=methodology,
            best_metric=best_metric,
            source_url=source_url,
            num_parameters=num_parameters,
            hf_model_url=hf_model_url,
            is_open=True,
        )
        return "created", int(created.id)
    if {key: existing[key] for key in desired} == desired:
        return "unchanged", int(existing["id"])

    row = db.get(Evaluation, existing["id"])
    row.metrics = dict(metrics)
    row.methodology = methodology
    row.is_open = True
    row.source_url = source_url
    row.external = False
    row.num_parameters = num_parameters
    row.hf_model_url = hf_model_url
    db.commit()
    for metric_name in metrics:
        service.recalculate_ranks(task_id, dataset_id, metric_name=metric_name)
    return "updated", int(existing["id"])
