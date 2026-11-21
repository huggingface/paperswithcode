"""
Run the add_trending_score migration.

This script adds the trending_score and trending_score_updated_at columns
to the repositories table.
"""

import sys
from sqlalchemy import text
from backend.database.connection import db_manager


def main():
    """Run the migration."""
    print("=" * 80)
    print("Running migration: add_trending_score")
    print("=" * 80)

    session = None
    try:
        session = db_manager.session_local()

        sql_file = "backend/database/migrations/add_trending_score.sql"
        with open(sql_file, "r") as f:
            sql_content = f.read()

        session.execute(text(sql_content))
        session.commit()

        print("✅ Migration completed successfully!")
        print()
        print("Verifying changes...")

        result = session.execute(
            text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'repositories'
            AND column_name IN ('trending_score', 'trending_score_updated_at')
            ORDER BY column_name;
        """)
        )

        columns = result.fetchall()
        if len(columns) == 2:
            print("✅ Columns verified:")
            for col in columns:
                print(f"   - {col[0]}: {col[1]}")
        else:
            print("⚠️  Warning: Could not verify all columns")

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
