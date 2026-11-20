#!/usr/bin/env python3
"""
Recalculate ranks for all evaluation leaderboards.

This script finds all unique (task_id, dataset_id) combinations and recalculates
ranks for each leaderboard. It uses the metrics table to determine the correct
ranking direction (higher_is_better vs lower_is_better).

Usage:
    uv run --env-file backend/keys.env backend/scripts/recalculate_all_ranks.py
"""

import logging
import sys

from database.connection import get_database_session
from services.evaluation_service import EvaluationService
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_all_leaderboards(db):
    """
    Get all unique (task_id, dataset_id) combinations from evaluations.

    Returns:
        List of tuples: [(task_id, dataset_id, eval_count), ...]
    """
    query = text("""
        SELECT
            task_id,
            dataset_id,
            COUNT(*) as eval_count
        FROM evaluations
        WHERE best_metric IS NOT NULL
        GROUP BY task_id, dataset_id
        ORDER BY task_id, dataset_id
    """)

    result = db.execute(query)
    return result.fetchall()


def main():
    """Main function to recalculate all ranks."""
    logger.info("Starting rank recalculation for all leaderboards...")

    db = next(get_database_session())
    service = EvaluationService(db)

    try:
        logger.info("Finding all unique task+dataset combinations...")
        leaderboards = get_all_leaderboards(db)
        logger.info(f"Found {len(leaderboards)} unique leaderboards")

        if not leaderboards:
            logger.warning("No leaderboards found!")
            return

        total_updated = 0
        failed_count = 0

        for task_id, dataset_id, eval_count in leaderboards:
            try:
                logger.info(
                    f"Recalculating ranks for task_id={task_id}, dataset_id={dataset_id} "
                    f"({eval_count} evaluations)..."
                )

                updated_count = service.recalculate_ranks(
                    task_id=task_id, dataset_id=dataset_id
                )

                logger.info(f"  ✓ Updated {updated_count} evaluations")
                total_updated += updated_count

            except Exception as e:
                logger.error(
                    f"  ✗ Failed for task_id={task_id}, dataset_id={dataset_id}: {str(e)}"
                )
                failed_count += 1
                continue

        logger.info("=" * 60)
        logger.info("Recalculation complete!")
        logger.info(f"  Total leaderboards processed: {len(leaderboards)}")
        logger.info(f"  Total evaluations updated: {total_updated}")
        logger.info(f"  Failed leaderboards: {failed_count}")

        if failed_count > 0:
            logger.warning(f"  {failed_count} leaderboards failed to update")
            sys.exit(1)
        else:
            logger.info("  ✓ All ranks successfully updated!")

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
