"""Run the add_external_resources_schema migration.

Adds the minimal source split (`source`, `source_url`) to the `papers` table,
relaxes `arxiv_id` to be nullable, and replaces the existing
`(arxiv_id, version)` unique constraint with partial unique indexes.

Idempotent - safe to re-run.
"""

import sys

from sqlalchemy import text

from backend.database.connection import db_manager


SQL_FILE = "backend/database/migrations/add_external_resources_schema.sql"


def main() -> None:
    print("=" * 80)
    print("Running migration: add_external_resources_schema")
    print("=" * 80)

    session = db_manager.session_local()
    try:
        with open(SQL_FILE, "r") as f:
            sql_content = f.read()

        session.execute(text(sql_content))
        session.commit()

        print("Migration completed successfully")
        print()
        print("Verifying changes...")

        result = session.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'papers'
                  AND column_name IN ('source', 'source_url', 'arxiv_id')
                ORDER BY column_name
                """
            )
        )
        for col in result.fetchall():
            print(f"   - {col[0]}: {col[1]} (nullable={col[2]}, default={col[3]})")

        index_check = session.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'papers'
                  AND indexname IN (
                      'uq_papers_arxiv_id_version_when_present',
                      'uq_papers_source_url_external',
                      'idx_papers_source'
                  )
                ORDER BY indexname
                """
            )
        )
        index_names = sorted({row[0] for row in index_check.fetchall()})
        print(f"   - indexes: {index_names}")

        constraint_check = session.execute(
            text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'papers'::regclass
                  AND conname IN (
                      'papers_source_check',
                      'papers_source_identifier_check',
                      'uq_paper_arxiv_version'
                  )
                ORDER BY conname
                """
            )
        )
        constraint_names = sorted({row[0] for row in constraint_check.fetchall()})
        print(f"   - constraints: {constraint_names}")

        if "uq_paper_arxiv_version" in constraint_names:
            print("ERROR: legacy `uq_paper_arxiv_version` still present.")
            sys.exit(1)
        if "papers_source_check" not in constraint_names:
            print("ERROR: `papers_source_check` constraint missing.")
            sys.exit(1)
        if "papers_source_identifier_check" not in constraint_names:
            print("ERROR: `papers_source_identifier_check` constraint missing.")
            sys.exit(1)

        backfill = session.execute(
            text("SELECT source, COUNT(*) FROM papers GROUP BY source ORDER BY source")
        )
        print("   - row counts by source:")
        for row in backfill.fetchall():
            print(f"       {row[0]}: {row[1]:,}")

        print()
        print("=" * 80)

    except Exception as exc:
        print(f"Migration failed: {exc}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
