"""Incrementally refresh the active paper-embedding generation via TEI."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import httpx
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from backend.services.embedding_contracts import build_embedding_input, content_hash


RETRYABLE_STATUS_CODES = {408, 429, 502, 503, 504}


@dataclass(frozen=True)
class ActiveEmbeddingGeneration:
    id: int
    model_name: str
    model_revision: str
    dimensions: int
    input_format_version: str


@dataclass(frozen=True)
class EmbeddingCandidate:
    paper_id: int
    title: str
    abstract: str | None
    content_hash: str

    @property
    def embedding_input(self) -> str:
        return build_embedding_input(self.title, self.abstract)


@dataclass(frozen=True)
class IncrementalRefreshResult:
    run_id: str
    generation_id: int
    candidates: int
    embedded: int
    stale: int
    missing_remaining: int
    content_hash_mismatches: int


def active_generation(db: Session) -> ActiveEmbeddingGeneration:
    row = (
        db.execute(
            text(
                """
                SELECT id, model_name, model_revision, dimensions,
                       input_format_version
                FROM paper_embedding_generations
                WHERE status = 'active'
                """
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError("No active paper-embedding generation")
    return ActiveEmbeddingGeneration(**dict(row))


def find_refresh_candidates(
    db: Session,
    *,
    generation_id: int,
    limit: int,
) -> list[EmbeddingCandidate]:
    """Find missing rows first, then stream stored hashes for mismatches."""
    if limit < 1:
        raise ValueError("limit must be positive")
    missing_rows = (
        db.execute(
            text(
                """
                SELECT p.id, p.title, p.abstract
                FROM papers p
                LEFT JOIN paper_embeddings e
                  ON e.paper_id = p.id AND e.generation_id = :generation_id
                WHERE p.is_latest_version
                  AND e.paper_id IS NULL
                ORDER BY p.updated_at, p.id
                LIMIT :limit
                """
            ),
            {"generation_id": generation_id, "limit": limit},
        )
        .mappings()
        .all()
    )
    candidates = [
        EmbeddingCandidate(
            paper_id=int(row["id"]),
            title=row["title"],
            abstract=row["abstract"],
            content_hash=content_hash(row["title"], row["abstract"]),
        )
        for row in missing_rows
    ]
    if len(candidates) >= limit:
        return candidates

    mismatch_statement = text(
        """
        SELECT p.id, p.title, p.abstract, e.content_hash
        FROM papers p
        JOIN paper_embeddings e
          ON e.paper_id = p.id AND e.generation_id = :generation_id
        WHERE p.is_latest_version
        ORDER BY p.id
        """
    ).execution_options(stream_results=True, max_row_buffer=1_000)
    result = db.execute(mismatch_statement, {"generation_id": generation_id})
    try:
        for row in result.mappings().yield_per(1_000):
            current_hash = content_hash(row["title"], row["abstract"])
            if row["content_hash"] == current_hash:
                continue
            candidates.append(
                EmbeddingCandidate(
                    paper_id=int(row["id"]),
                    title=row["title"],
                    abstract=row["abstract"],
                    content_hash=current_hash,
                )
            )
            if len(candidates) >= limit:
                break
    finally:
        result.close()
    return candidates


def embedding_backlog_counts(db: Session, *, generation_id: int) -> tuple[int, int]:
    """Stream durable missing-row and content-hash mismatch counts."""
    statement = text(
        """
        SELECT p.title, p.abstract, e.content_hash
        FROM papers AS p
        LEFT JOIN paper_embeddings AS e
          ON e.paper_id = p.id AND e.generation_id = :generation_id
        WHERE p.is_latest_version
        """
    ).execution_options(stream_results=True, max_row_buffer=1_000)
    rows = (
        db.execute(statement, {"generation_id": generation_id})
        .mappings()
        .yield_per(1_000)
    )
    missing = mismatches = 0
    for row in rows:
        stored_hash = row["content_hash"]
        if stored_hash is None:
            missing += 1
        elif stored_hash != content_hash(row["title"], row["abstract"]):
            mismatches += 1
    return missing, mismatches


def _validated_vectors(
    payload: object, *, rows: int, dimensions: int
) -> list[list[float]]:
    if isinstance(payload, dict):
        payload = payload.get("embeddings")
    if not isinstance(payload, list) or len(payload) != rows:
        raise ValueError(f"Expected {rows} embedding rows")

    validated = []
    for values in payload:
        if not isinstance(values, list) or len(values) != dimensions:
            raise ValueError(f"Expected {dimensions}-dimensional embeddings")
        vector = [float(value) for value in values]
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("Embedding contains NaN or infinity")
        norm = math.sqrt(sum(value * value for value in vector))
        if not 0.98 <= norm <= 1.02:
            raise ValueError(f"Expected normalized embeddings; norm={norm:.6f}")
        validated.append(vector)
    return validated


def encode_documents(
    client: httpx.Client,
    *,
    endpoint_url: str,
    token: str,
    texts: list[str],
    dimensions: int,
    max_attempts: int = 3,
) -> list[list[float]]:
    """Encode one bounded document batch with cold-start/rate-limit retries."""
    if not endpoint_url or not token:
        raise RuntimeError("HF embedding endpoint URL and token are required")
    if not texts:
        return []

    for attempt in range(max_attempts):
        response = client.post(
            endpoint_url,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "inputs": texts,
                "dimensions": dimensions,
                "normalize": True,
                "prompt_name": "document",
            },
        )
        if (
            response.status_code in RETRYABLE_STATUS_CODES
            and attempt + 1 < max_attempts
        ):
            time.sleep(2**attempt)
            continue
        response.raise_for_status()
        return _validated_vectors(
            response.json(), rows=len(texts), dimensions=dimensions
        )
    raise RuntimeError("Embedding endpoint retry loop exited unexpectedly")


def _vector_literal(values: Iterable[float]) -> str:
    return "[" + ",".join(format(value, ".8g") for value in values) + "]"


def upsert_current_embeddings(
    db: Session,
    *,
    generation: ActiveEmbeddingGeneration,
    candidates: list[EmbeddingCandidate],
    vectors: list[list[float]],
) -> tuple[int, int]:
    """Lock source rows, discard raced changes, and upsert current vectors."""
    if len(candidates) != len(vectors):
        raise ValueError("Candidate/vector row count mismatch")
    if not candidates:
        return 0, 0

    paper_ids = [candidate.paper_id for candidate in candidates]
    statement = text(
        """
        SELECT id, title, abstract
        FROM papers
        WHERE id IN :paper_ids AND is_latest_version
        FOR SHARE
        """
    ).bindparams(bindparam("paper_ids", expanding=True))
    current_rows = {
        int(row["id"]): row
        for row in db.execute(statement, {"paper_ids": paper_ids}).mappings()
    }

    pending = []
    stale = 0
    for candidate, vector in zip(candidates, vectors, strict=True):
        current = current_rows.get(candidate.paper_id)
        if (
            current is None
            or content_hash(current["title"], current["abstract"])
            != candidate.content_hash
        ):
            stale += 1
            continue
        pending.append(
            {
                "generation_id": generation.id,
                "paper_id": candidate.paper_id,
                "content_hash": candidate.content_hash,
                "embedding": _vector_literal(vector),
            }
        )

    if pending:
        db.execute(
            text(
                f"""
                INSERT INTO paper_embeddings
                    (generation_id, paper_id, content_hash, embedding)
                VALUES
                    (:generation_id, :paper_id, :content_hash,
                     CAST(:embedding AS halfvec({generation.dimensions})))
                ON CONFLICT (generation_id, paper_id) DO UPDATE
                SET content_hash = EXCLUDED.content_hash,
                    embedding = EXCLUDED.embedding,
                    created_at = now()
                """
            ),
            pending,
        )
    db.commit()
    return len(pending), stale


def _record_run(
    db: Session,
    *,
    run_id: str,
    generation_id: int,
    status: str,
    row_count: int | None,
    details: dict[str, object],
    completed: bool,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO embedding_pipeline_runs
                (run_id, generation_id, kind, status, row_count, details,
                 completed_at)
            VALUES
                (:run_id, :generation_id, 'import', :status, :row_count,
                 CAST(:details AS jsonb), :completed_at)
            ON CONFLICT (run_id, kind) DO UPDATE
            SET status = EXCLUDED.status,
                row_count = EXCLUDED.row_count,
                details = EXCLUDED.details,
                completed_at = EXCLUDED.completed_at
            """
        ),
        {
            "run_id": run_id,
            "generation_id": generation_id,
            "status": status,
            "row_count": row_count,
            "details": json.dumps(details),
            "completed_at": datetime.now(timezone.utc) if completed else None,
        },
    )
    db.commit()


def refresh_active_embeddings(
    db: Session,
    *,
    endpoint_url: str,
    token: str,
    limit: int = 500,
    batch_size: int = 16,
    timeout_seconds: float = 120,
    client: httpx.Client | None = None,
    run_id: str | None = None,
) -> IncrementalRefreshResult:
    """Embed a bounded delta directly into the active generation."""
    if batch_size < 1 or batch_size > 128:
        raise ValueError("batch_size must be between 1 and 128")
    generation = active_generation(db)
    run_id = run_id or (
        "cron-incremental-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    candidates = find_refresh_candidates(db, generation_id=generation.id, limit=limit)
    _record_run(
        db,
        run_id=run_id,
        generation_id=generation.id,
        status="running",
        row_count=len(candidates),
        details={"candidates": len(candidates), "batch_size": batch_size},
        completed=False,
    )

    owns_client = client is None
    http = client or httpx.Client(timeout=timeout_seconds)
    embedded = stale = 0
    missing_remaining = content_hash_mismatches = 0
    try:
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start : start + batch_size]
            vectors = encode_documents(
                http,
                endpoint_url=endpoint_url,
                token=token,
                texts=[candidate.embedding_input for candidate in batch],
                dimensions=generation.dimensions,
            )
            batch_embedded, batch_stale = upsert_current_embeddings(
                db,
                generation=generation,
                candidates=batch,
                vectors=vectors,
            )
            embedded += batch_embedded
            stale += batch_stale
        missing_remaining, content_hash_mismatches = embedding_backlog_counts(
            db, generation_id=generation.id
        )
    except Exception as error:
        db.rollback()
        _record_run(
            db,
            run_id=run_id,
            generation_id=generation.id,
            status="failed",
            row_count=embedded,
            details={
                "candidates": len(candidates),
                "embedded": embedded,
                "stale": stale,
                "error_type": type(error).__name__,
            },
            completed=True,
        )
        raise
    finally:
        if owns_client:
            http.close()

    _record_run(
        db,
        run_id=run_id,
        generation_id=generation.id,
        status="complete",
        row_count=embedded,
        details={
            "candidates": len(candidates),
            "embedded": embedded,
            "stale": stale,
            "batch_size": batch_size,
            "missing_remaining": missing_remaining,
            "content_hash_mismatches": content_hash_mismatches,
        },
        completed=True,
    )
    return IncrementalRefreshResult(
        run_id=run_id,
        generation_id=generation.id,
        candidates=len(candidates),
        embedded=embedded,
        stale=stale,
        missing_remaining=missing_remaining,
        content_hash_mismatches=content_hash_mismatches,
    )
