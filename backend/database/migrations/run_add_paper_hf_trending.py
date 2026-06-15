"""
Run the add_paper_hf_trending migration.

Creates the normalized Hugging Face artifact tables (hf_artifacts,
paper_hf_artifacts) and the paper-level composite trending score columns.
"""

import sys
from sqlalchemy import text
from backend.database.connection import db_manager


def main():
    """Run the migration."""
    print("=" * 80)
    print("Running migration: add_paper_hf_trending")
    print("=" * 80)

    session = None
    try:
        session = db_manager.session_local()

        sql_file = "backend/database/migrations/add_paper_hf_trending.sql"
        with open(sql_file, "r") as f:
            sql_content = f.read()

        session.execute(text(sql_content))
        session.commit()

        print("✅ Migration completed successfully!")
        print()
        print("Verifying changes...")

        tables = session.execute(
            text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name IN ('hf_artifacts', 'paper_hf_artifacts')
            ORDER BY table_name;
        """)
        ).fetchall()
        print(f"✅ Tables present: {[t[0] for t in tables]}")

        columns = session.execute(
            text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'papers'
            AND column_name IN (
                'trending_score', 'trending_score_updated_at',
                'github_trending_component', 'hf_trending_component',
                'hf_artifacts_scanned_at'
            )
            ORDER BY column_name;
        """)
        ).fetchall()
        print(f"✅ Paper columns present: {[c[0] for c in columns]}")

        print()
        print("=" * 80)

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if session:
            session.rollback()
        sys.exit(1)
    finally:
        if session:
            session.close()


if __name__ == "__main__":
    main()
