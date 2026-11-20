"""
Run the dataset variants and splits migration.

This script applies the SQL migration to add support for dataset variants and splits.

Usage:
    uv run --env-file backend/keys.env backend/database/migrations/run_add_dataset_variants_and_splits.py
"""

import logging
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Apply the dataset variants and splits migration."""
    logger.info("=" * 80)
    logger.info("Running Dataset Variants and Splits Migration")
    logger.info("=" * 80)

    migration_file = Path(__file__).parent / "add_dataset_variants_and_splits.sql"
    logger.info(f"Reading migration from: {migration_file}")

    with open(migration_file, "r") as f:
        migration_sql = f.read()

    db_params = {
        "host": os.getenv("PWC_DB_HOST", "localhost"),
        "port": os.getenv("PWC_DB_PORT", "5432"),
        "database": os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        "user": os.getenv("PWC_DB_USER", "postgres"),
        "password": os.getenv("PWC_DB_PASSWORD", ""),
    }

    try:
        logger.info("Connecting to database...")
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        logger.info("Executing migration SQL...")
        cursor.execute(migration_sql)

        conn.commit()
        logger.info("Migration committed successfully!")

        logger.info("\nVerifying migration...")
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'datasets'
                AND column_name IN ('parent_dataset_id', 'variant_type', 'split_name', 'introduced_year', 'paper_url')
            ORDER BY column_name
        """)

        columns = cursor.fetchall()
        logger.info("New columns added to datasets table:")
        for col in columns:
            logger.info(f"  - {col[0]}: {col[1]}")

        cursor.execute("""
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'public'
                AND table_name IN ('base_datasets', 'datasets_with_parent', 'dataset_hierarchies')
            ORDER BY table_name
        """)

        views = cursor.fetchall()
        logger.info("\nViews created:")
        for view in views:
            logger.info(f"  - {view[0]}")

        logger.info("\n" + "=" * 80)
        logger.info("Migration completed successfully!")
        logger.info("=" * 80)

        cursor.close()
        conn.close()

        return 0

    except psycopg2.Error as e:
        logger.error(f"Database error during migration: {e}", exc_info=True)
        if "conn" in locals():
            conn.rollback()
        return 1
    except Exception as e:
        logger.error(f"Error running migration: {e}", exc_info=True)
        if "conn" in locals():
            conn.rollback()
        return 1


if __name__ == "__main__":
    sys.exit(main())
