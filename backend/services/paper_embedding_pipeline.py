"""Safe, resumable embedding export/import and operational status helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.models.database import Paper
from backend.services.embedding_contracts import (
    EmbeddingRunManifest,
    ShardManifest,
    build_embedding_input,
    content_hash,
    sha256_file,
)


@dataclass(frozen=True)
class ExportResult:
    run_dir: Path
    manifest: EmbeddingRunManifest


def _snapshot_id(db: Session) -> str:
    return str(db.execute(text("SELECT txid_current_snapshot()::text")).scalar_one())


def _existing_hashes(db: Session, generation_id: int | None) -> dict[int, str]:
    if generation_id is None:
        return {}
    rows = db.execute(
        text(
            """
            SELECT paper_id, content_hash FROM paper_embeddings
            WHERE generation_id = :generation_id
            """
        ),
        {"generation_id": generation_id},
    )
    return {int(row[0]): str(row[1]) for row in rows}


def export_papers(
    db: Session,
    output_root: Path,
    *,
    run_id: str,
    model_name: str,
    model_revision: str,
    dimensions: int,
    shard_rows: int = 5_000,
    generation_id: int | None = None,
    max_rows: int | None = None,
) -> ExportResult:
    """Export a consistent latest-paper snapshot into checksummed JSONL shards."""
    if shard_rows < 1:
        raise ValueError("shard_rows must be positive")
    run_dir = output_root / "runs" / run_id / "input"
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty run directory: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
    snapshot = _snapshot_id(db)
    existing_hashes = _existing_hashes(db, generation_id)
    query = db.query(Paper).filter(Paper.is_latest_version).order_by(Paper.id)

    shard_manifests: list[ShardManifest] = []
    row_count = 0
    handle = None
    shard_path: Path | None = None
    shard_count = 0
    try:
        for paper in query.yield_per(min(shard_rows, 1_000)):
            paper_hash = content_hash(paper.title, paper.abstract)
            if (
                generation_id is not None
                and existing_hashes.get(paper.id) == paper_hash
            ):
                continue
            if max_rows is not None and row_count >= max_rows:
                break
            if handle is None or shard_count >= shard_rows:
                if handle is not None and shard_path is not None:
                    handle.close()
                    shard_manifests.append(
                        ShardManifest(
                            path=shard_path.name,
                            rows=shard_count,
                            sha256=sha256_file(shard_path),
                        )
                    )
                shard_path = run_dir / f"papers-{len(shard_manifests):05d}.jsonl"
                handle = shard_path.open("w", encoding="utf-8")
                shard_count = 0
            record = {
                "paper_id": paper.id,
                "title": paper.title,
                "abstract": paper.abstract,
                "embedding_input": build_embedding_input(paper.title, paper.abstract),
                "content_hash": paper_hash,
                "updated_at": paper.updated_at.isoformat()
                if paper.updated_at
                else None,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            shard_count += 1
            row_count += 1
    finally:
        if handle is not None and shard_path is not None:
            handle.close()
            shard_manifests.append(
                ShardManifest(
                    path=shard_path.name,
                    rows=shard_count,
                    sha256=sha256_file(shard_path),
                )
            )

    manifest = EmbeddingRunManifest.create(
        run_id=run_id,
        model_name=model_name,
        model_revision=model_revision,
        dimensions=dimensions,
        corpus_snapshot=snapshot,
        row_count=row_count,
        shards=shard_manifests,
    )
    manifest.write(run_dir / "manifest.json")
    return ExportResult(run_dir=run_dir, manifest=manifest)


def _vector_literal(values: Iterable[float], dimensions: int) -> str:
    vector = [float(value) for value in values]
    if len(vector) != dimensions:
        raise ValueError(f"Wrong vector dimensions: {len(vector)} != {dimensions}")
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("Vector contains NaN or infinity")
    norm = math.sqrt(sum(value * value for value in vector))
    if not 0.98 <= norm <= 1.02:
        raise ValueError(f"Expected a normalized vector; norm={norm:.6f}")
    return "[" + ",".join(format(value, ".8g") for value in vector) + "]"


def create_generation(
    db: Session,
    manifest: EmbeddingRunManifest,
    bucket_run_uri: str,
) -> int:
    generation_id = db.execute(
        text(
            """
            INSERT INTO paper_embedding_generations (
              model_name, model_revision, dimensions, input_format_version,
              normalization, query_instruction_version, bucket_run_uri, status
            ) VALUES (
              :model_name, :model_revision, :dimensions, :input_format_version,
              :normalization, :query_instruction_version, :bucket_run_uri, 'loading'
            ) RETURNING id
            """
        ),
        {**manifest.to_dict(), "bucket_run_uri": bucket_run_uri},
    ).scalar_one()
    db.execute(
        text("SELECT create_paper_embedding_partition(:id, :dimensions)"),
        {"id": generation_id, "dimensions": manifest.dimensions},
    )
    db.commit()
    return int(generation_id)


def import_embeddings(
    db: Session,
    output_dir: Path,
    *,
    generation_id: int,
    batch_rows: int = 500,
) -> dict[str, int]:
    """Validate completed Parquet artifacts and idempotently load one generation."""
    import pyarrow.parquet as pq

    final_manifest_path = output_dir / "manifest.json"
    final = json.loads(final_manifest_path.read_text(encoding="utf-8"))
    if final.get("status") != "complete":
        raise ValueError("Embedding output manifest is not complete")
    generation = (
        db.execute(
            text(
                """SELECT dimensions, model_name, model_revision, input_format_version
                 FROM paper_embedding_generations WHERE id = :id"""
            ),
            {"id": generation_id},
        )
        .mappings()
        .one()
    )
    for key in ("dimensions", "model_name", "model_revision", "input_format_version"):
        if final[key] != generation[key]:
            raise ValueError(f"Generation mismatch for {key}")

    imported = stale = 0
    seen: set[int] = set()
    pending: list[dict[str, object]] = []
    for shard in final["shards"]:
        path = output_dir / shard["path"]
        if sha256_file(path) != shard["sha256"]:
            raise ValueError(f"Checksum mismatch: {path}")
        table = pq.read_table(path)
        if table.num_rows != shard["rows"]:
            raise ValueError(f"Output shard row mismatch: {path}")
        value_type = table.schema.field("embedding").type.value_type
        if str(value_type) != "halffloat":
            raise ValueError(f"Expected float16 embeddings, got {value_type}")
        for row in table.to_pylist():
            paper_id = int(row["paper_id"])
            if paper_id in seen:
                raise ValueError(f"Duplicate paper ID in output: {paper_id}")
            seen.add(paper_id)
            current = (
                db.execute(
                    text(
                        "SELECT title, abstract FROM papers WHERE id=:id AND is_latest_version"
                    ),
                    {"id": paper_id},
                )
                .mappings()
                .one_or_none()
            )
            if (
                current is None
                or content_hash(current["title"], current["abstract"])
                != row["content_hash"]
            ):
                stale += 1
                continue
            pending.append(
                {
                    "generation_id": generation_id,
                    "paper_id": paper_id,
                    "content_hash": row["content_hash"],
                    "embedding": _vector_literal(
                        row["embedding"], generation["dimensions"]
                    ),
                }
            )
            if len(pending) >= batch_rows:
                imported += _flush_embeddings(db, pending, generation["dimensions"])
                pending.clear()
    if pending:
        imported += _flush_embeddings(db, pending, generation["dimensions"])
    if len(seen) != final["row_count"]:
        raise ValueError(
            f"Output coverage mismatch: {len(seen)} != {final['row_count']}"
        )
    db.execute(
        text(
            """UPDATE paper_embedding_generations
               SET validation_metrics=CAST(:metrics AS jsonb) WHERE id=:id"""
        ),
        {
            "id": generation_id,
            "metrics": json.dumps(
                {"imported": imported, "stale": stale, "artifact_rows": len(seen)}
            ),
        },
    )
    db.commit()
    return {"imported": imported, "stale": stale, "artifact_rows": len(seen)}


def build_generation_index(engine: Engine, generation_id: int) -> None:
    """Build the isolated generation partition's HNSW index concurrently."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        dimensions = connection.execute(
            text("SELECT dimensions FROM paper_embedding_generations WHERE id=:id"),
            {"id": generation_id},
        ).scalar_one()
        partition = f"paper_embeddings_g{int(generation_id)}"
        index = f"idx_paper_embeddings_g{int(generation_id)}_hnsw_cosine"
        connection.exec_driver_sql(
            f"""CREATE INDEX CONCURRENTLY IF NOT EXISTS {index} ON {partition}
                USING hnsw ((embedding::halfvec({int(dimensions)})) halfvec_cosine_ops)"""
        )
        connection.exec_driver_sql(f"ANALYZE {partition}")


def mark_generation_ready(db: Session, generation_id: int) -> None:
    valid = db.execute(
        text(
            """SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
               WHERE c.relname=:name"""
        ),
        {"name": f"idx_paper_embeddings_g{generation_id}_hnsw_cosine"},
    ).scalar_one_or_none()
    if valid is not True:
        raise ValueError(f"Generation {generation_id} is missing a valid HNSW index")
    db.execute(
        text(
            """UPDATE paper_embedding_generations SET status='ready'
               WHERE id=:id AND status='loading'"""
        ),
        {"id": generation_id},
    )
    db.commit()


def _flush_embeddings(
    db: Session, rows: list[dict[str, object]], dimensions: int
) -> int:
    db.execute(
        text(
            f"""
            INSERT INTO paper_embeddings (generation_id, paper_id, content_hash, embedding)
            VALUES (:generation_id, :paper_id, :content_hash, CAST(:embedding AS halfvec({dimensions})))
            ON CONFLICT (generation_id, paper_id) DO UPDATE
              SET content_hash=EXCLUDED.content_hash,
                  embedding=EXCLUDED.embedding,
                  created_at=now()
            """
        ),
        rows,
    )
    db.commit()
    return len(rows)


def activate_generation(db: Session, generation_id: int) -> None:
    ready = db.execute(
        text("SELECT status FROM paper_embedding_generations WHERE id=:id FOR UPDATE"),
        {"id": generation_id},
    ).scalar_one_or_none()
    if ready != "ready":
        raise ValueError(f"Generation {generation_id} must be ready, got {ready!r}")
    db.execute(text("LOCK TABLE papers IN SHARE MODE"))
    missing = stale = 0
    rows = db.execute(
        text(
            """SELECT p.title, p.abstract, e.content_hash
                 FROM papers p LEFT JOIN paper_embeddings e
                   ON e.paper_id=p.id AND e.generation_id=:id
               WHERE p.is_latest_version"""
        ),
        {"id": generation_id},
    ).yield_per(1000)
    for title, abstract, stored_hash in rows:
        if stored_hash is None:
            missing += 1
        elif stored_hash != content_hash(title, abstract):
            stale += 1
    if missing or stale:
        raise ValueError(
            f"Generation {generation_id} cannot activate with "
            f"{missing} missing and {stale} stale eligible papers"
        )
    db.execute(
        text(
            "UPDATE paper_embedding_generations SET status='retired' WHERE status='active'"
        )
    )
    db.execute(
        text(
            """UPDATE paper_embedding_generations
               SET status='active', activated_at=now() WHERE id=:id"""
        ),
        {"id": generation_id},
    )
    db.commit()


def embedding_status(db: Session) -> dict[str, object]:
    active = (
        db.execute(
            text(
                """SELECT id, model_name, model_revision, dimensions, status, activated_at
                 FROM paper_embedding_generations WHERE status='active'"""
            )
        )
        .mappings()
        .one_or_none()
    )
    coverage = (
        db.execute(
            text(
                """
            SELECT count(*) FILTER (WHERE e.paper_id IS NULL) AS missing,
                   count(*) FILTER (WHERE e.paper_id IS NOT NULL) AS embedded,
                   count(*) FILTER (WHERE e.paper_id IS NULL AND p.abstract IS NULL) AS missing_title_only,
                   min(p.updated_at) FILTER (WHERE e.paper_id IS NULL) AS oldest_missing
            FROM papers p
            LEFT JOIN paper_embeddings e
              ON e.paper_id=p.id AND e.generation_id=:generation_id
            WHERE p.is_latest_version
            """
            ),
            {"generation_id": active["id"] if active else -1},
        )
        .mappings()
        .one()
    )
    recent_runs = (
        db.execute(
            text(
                """SELECT run_id, generation_id, kind, status, row_count, artifact_uri,
                      started_at, completed_at
                 FROM embedding_pipeline_runs ORDER BY started_at DESC LIMIT 10"""
            )
        )
        .mappings()
        .all()
    )
    oldest = coverage["oldest_missing"]
    freshness_breached = bool(
        oldest and (datetime.now(timezone.utc) - oldest).total_seconds() > 24 * 60 * 60
    )
    return {
        "active_generation": dict(active) if active else None,
        **dict(coverage),
        "freshness_slo_hours": 24,
        "freshness_slo_breached": freshness_breached,
        "recent_runs": [dict(run) for run in recent_runs],
    }


def bucket_retention_plan(
    runs: list[dict[str, object]],
    *,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """Return deletable Bucket prefixes; callers must separately apply the plan."""
    now = now or datetime.now(timezone.utc)
    plan = []
    for run in runs:
        age_days = (now - datetime.fromisoformat(str(run["created_at"]))).days
        keep_days = 90 if run.get("status") == "complete" else 14
        protected = bool(run.get("active") or run.get("previous") or run.get("pinned"))
        if not protected and age_days > keep_days:
            plan.append(
                {"prefix": run["prefix"], "reason": f"{age_days}d>{keep_days}d"}
            )
    return plan
