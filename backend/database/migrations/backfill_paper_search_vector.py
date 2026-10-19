"""Backfill ``papers.search_vector`` in resumable, committed batches.

Examples:
    uv run --env-file backend/keys.env python \
      backend/database/migrations/backfill_paper_search_vector.py --max-batches 10

    uv run --env-file backend/keys.env python \
      backend/database/migrations/backfill_paper_search_vector.py \
      --database-url postgresql://.../isolated_db --batch-size 500

    # After changing papers_search_vector_update(), recompute every row as
    # postgres (the session skips the updated_at trigger):
    sudo -u postgres uv run python \
      backend/database/migrations/backfill_paper_search_vector.py \
      --database-url postgresql:///paperswithcode_hf --rebuild --max-batches 1000

Each invocation is bounded by ``--max-batches`` and commits after every batch.
Rows left NULL are picked up by a later invocation, so interruption is safe.
A rebuild prints the last id it rewrote; pass it back as ``--after-id``.
"""

import argparse

from sqlalchemy import create_engine, text

from backend.config import get_settings


# Keep in step with papers_search_vector_update() in add_paper_search_vector.sql.
SEARCH_VECTOR = """
    setweight(to_tsvector('english', coalesce(p.title, '')), 'A') ||
    setweight(to_tsvector('english', regexp_replace(
        coalesce(p.title, ''), '[^[:alnum:]]+', ' ', 'g'
    )), 'A') ||
    setweight(to_tsvector('english', coalesce(p.abstract, '')), 'B')
"""

BACKFILL_BATCH = text(f"""
    WITH batch AS (
        SELECT id
        FROM papers
        WHERE search_vector IS NULL
        ORDER BY id
        LIMIT :batch_size
        FOR UPDATE SKIP LOCKED
    )
    UPDATE papers AS p
    SET search_vector = {SEARCH_VECTOR}
    FROM batch
    WHERE p.id = batch.id
""")

REBUILD_BATCH = text(f"""
    WITH batch AS (
        SELECT id
        FROM papers
        WHERE id > :after_id
        ORDER BY id
        LIMIT :batch_size
    )
    UPDATE papers AS p
    SET search_vector = {SEARCH_VECTOR}
    FROM batch
    WHERE p.id = batch.id
    RETURNING p.id
""")


def backfill(database_url: str, batch_size: int, max_batches: int) -> tuple[int, int]:
    engine = create_engine(database_url)
    updated = 0
    try:
        for _ in range(max_batches):
            with engine.begin() as connection:
                result = connection.execute(BACKFILL_BATCH, {"batch_size": batch_size})
                batch_count = result.rowcount
            updated += batch_count
            if batch_count < batch_size:
                break

        with engine.connect() as connection:
            remaining = connection.execute(
                text("SELECT count(*) FROM papers WHERE search_vector IS NULL")
            ).scalar_one()
    finally:
        engine.dispose()
    return updated, remaining


def rebuild(
    database_url: str, batch_size: int, max_batches: int, after_id: int
) -> tuple[int, int, bool]:
    """Recompute search_vector for rows after ``after_id`` without touching updated_at."""
    engine = create_engine(database_url)
    updated = 0
    try:
        for _ in range(max_batches):
            with engine.begin() as connection:
                # A search-index rewrite is not a content change; replica mode
                # skips the updated_at trigger (requires a superuser).
                connection.execute(text("SET LOCAL session_replication_role = replica"))
                ids = (
                    connection.execute(
                        REBUILD_BATCH, {"batch_size": batch_size, "after_id": after_id}
                    )
                    .scalars()
                    .all()
                )
            if not ids:
                return updated, after_id, True
            updated += len(ids)
            after_id = max(ids)
    finally:
        engine.dispose()
    return updated, after_id, False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument(
        "--rebuild", action="store_true", help="Recompute existing vectors too"
    )
    parser.add_argument("--after-id", type=int, default=0)
    args = parser.parse_args()
    if args.batch_size < 1 or args.max_batches < 1:
        parser.error("--batch-size and --max-batches must be positive")

    database_url = args.database_url or get_settings().database_url
    if args.rebuild:
        updated, last_id, done = rebuild(
            database_url, args.batch_size, args.max_batches, args.after_id
        )
        print(f"updated={updated} last_id={last_id} done={done}")
        return
    updated, remaining = backfill(database_url, args.batch_size, args.max_batches)
    print(f"updated={updated} remaining={remaining}")


if __name__ == "__main__":
    main()
