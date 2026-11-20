"""
Data validation script for evaluation metrics.

This script checks for and fixes common data inconsistencies in the evaluations table,
particularly metric naming inconsistencies that can cause display issues.
"""

import sys
import os
from typing import Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.config import get_settings


STANDARDIZATION_ALIASES = {
    "box AP": ["box mAP", "box_ap", "box_map", "bbox AP", "bbox mAP"],
    "AP50": ["AP@50", "AP@0.5", "AP_50"],
    "AP75": ["AP@75", "AP@0.75", "AP_75"],
}

REVIEW_ONLY_ALIASES = {
    "AP": ["mAP", "mean AP"],
    "mAP": ["mean AP"],
}


def get_database_connection():
    """Get a psycopg2 database connection."""
    settings = get_settings()
    url = settings.database_url.replace("postgresql://", "")
    user_pass, host_port_db = url.split("@")
    user, password = user_pass.split(":")
    host_port, database = host_port_db.split("/")
    host, port = host_port.split(":") if ":" in host_port else (host_port, "5432")

    return psycopg2.connect(
        host=host, port=port, database=database, user=user, password=password
    )


def get_all_metric_keys(cursor) -> List[str]:
    """Get all unique metric keys used in evaluations."""
    cursor.execute("""
        SELECT DISTINCT jsonb_object_keys(metrics) as metric_name
        FROM evaluations
        ORDER BY metric_name
    """)
    return [row["metric_name"] for row in cursor.fetchall()]


def find_metric_inconsistencies(cursor) -> Dict[str, List[str]]:
    """
    Find potential metric naming inconsistencies.

    Returns a dictionary mapping standardized names to their variations.
    """
    metric_keys = get_all_metric_keys(cursor)

    inconsistencies = {}

    for standard_name, variations in STANDARDIZATION_ALIASES.items():
        found_variations = [v for v in variations if v in metric_keys]
        if found_variations:
            inconsistencies[standard_name] = found_variations

    return inconsistencies


def get_metric_label_audit_rows(cursor):
    """Compare metric keys on evaluations with leaderboard metric definitions."""
    cursor.execute("""
        SELECT
            e.id,
            e.model_name,
            e.task_id,
            e.dataset_id,
            t.name AS task_name,
            d.name AS dataset_name,
            metric_key.metric_name,
            e.best_metric,
            COALESCE(
                (
                    SELECT array_agg(DISTINCT m.name ORDER BY m.name)
                    FROM task_dataset_metrics tdm
                    JOIN metrics m ON m.id = tdm.metric_id
                    WHERE tdm.task_id = e.task_id
                      AND tdm.dataset_id = e.dataset_id
                ),
                ARRAY[]::text[]
            ) AS allowed_metrics
        FROM evaluations e
        JOIN tasks t ON t.id = e.task_id
        JOIN datasets d ON d.id = e.dataset_id
        CROSS JOIN LATERAL jsonb_object_keys(e.metrics) AS metric_key(metric_name)
        ORDER BY t.name, d.name, e.best_metric, metric_key.metric_name, e.id
    """)
    return cursor.fetchall()


def classify_metric_label(metric_name: str, allowed_metrics: List[str]) -> str:
    """Classify a metric label against its configured leaderboard metrics."""
    if metric_name in allowed_metrics:
        return "valid_source_label"

    for standard_name, variations in STANDARDIZATION_ALIASES.items():
        if metric_name in variations and standard_name in allowed_metrics:
            return "possible_alias"

    for standard_name, variations in REVIEW_ONLY_ALIASES.items():
        if metric_name in variations and standard_name in allowed_metrics:
            return "possible_alias"

    return "leaderboard_mismatch"


def audit_metric_labels(cursor) -> int:
    """Report metric labels that do not match configured leaderboard metrics."""
    rows = get_metric_label_audit_rows(cursor)

    summary = {
        "valid_source_label": 0,
        "possible_alias": 0,
        "leaderboard_mismatch": 0,
    }
    grouped_issues = {}

    for row in rows:
        allowed_metrics = list(row["allowed_metrics"] or [])
        status = classify_metric_label(row["metric_name"], allowed_metrics)
        summary[status] += 1

        if status == "valid_source_label":
            continue

        key = (
            status,
            row["task_name"],
            row["dataset_name"],
            row["best_metric"],
            row["metric_name"],
            tuple(allowed_metrics),
        )
        grouped_issues[key] = grouped_issues.get(key, 0) + 1

    print("\nMetric label audit:")
    for status, count in summary.items():
        print(f"  {status}: {count}")

    if not grouped_issues:
        print("  ✓ All metric keys match configured leaderboard metrics")
        return 0

    print("\nMetric labels needing review, grouped by leaderboard:")
    for (
        status,
        task_name,
        dataset_name,
        best_metric,
        metric_name,
        allowed_metrics,
    ), count in sorted(grouped_issues.items())[:25]:
        allowed = ", ".join(allowed_metrics) if allowed_metrics else "none configured"
        print(
            f"  [{status}] {task_name} / {dataset_name} / best={best_metric}: "
            f"{metric_name} ({count} evaluation(s); allowed: {allowed})"
        )

    if len(grouped_issues) > 25:
        print(f"  ... {len(grouped_issues) - 25} more grouped issue(s)")

    return summary["possible_alias"] + summary["leaderboard_mismatch"]


def find_standardization_candidates(cursor):
    """Find safe metric-name rewrites based on leaderboard definitions."""
    rows = get_metric_label_audit_rows(cursor)
    candidates = []

    for row in rows:
        allowed_metrics = list(row["allowed_metrics"] or [])
        metric_name = row["metric_name"]

        for standard_name, variations in STANDARDIZATION_ALIASES.items():
            if (
                metric_name in variations
                and standard_name in allowed_metrics
                and metric_name not in allowed_metrics
            ):
                candidate = dict(row)
                candidate["standard_name"] = standard_name
                candidates.append(candidate)
                break

    return candidates


def standardize_metric_names(cursor, dry_run=True) -> int:
    """
    Standardize metric names across all evaluations.

    Args:
        cursor: Database cursor
        dry_run: If True, only report what would be changed

    Returns:
        Number of evaluations updated
    """
    candidates = find_standardization_candidates(cursor)

    if not candidates:
        print("✓ No safe metric naming standardizations found!")
        return 0

    print("\nFound safe metric naming standardizations:")

    total_updated = 0

    for candidate in candidates:
        eval_id = candidate["id"]
        variation = candidate["metric_name"]
        standard_name = candidate["standard_name"]

        print(
            f"  Evaluation {eval_id}: {variation} → {standard_name} "
            f"({candidate['task_name']} / {candidate['dataset_name']})"
        )

        if not dry_run:
            cursor.execute(
                """
                UPDATE evaluations
                SET
                    metrics = jsonb_set(metrics - %s, %s, metrics->%s),
                    best_metric = CASE
                        WHEN best_metric = %s THEN %s
                        ELSE best_metric
                    END
                WHERE id = %s
                  AND metrics ? %s
                  AND NOT metrics ? %s
            """,
                (
                    variation,
                    f"{{{standard_name}}}",
                    variation,
                    variation,
                    standard_name,
                    eval_id,
                    variation,
                    standard_name,
                ),
            )
            total_updated += cursor.rowcount
            print(f"    ✓ Updated {cursor.rowcount} evaluation(s)")

    return len(candidates) if dry_run else total_updated


def validate_best_metrics(cursor, dry_run=True) -> int:
    """
    Ensure all evaluations have a best_metric set.

    Args:
        cursor: Database cursor
        dry_run: If True, only report what would be changed

    Returns:
        Number of evaluations updated
    """
    cursor.execute("""
        SELECT id, model_name, metrics
        FROM evaluations
        WHERE best_metric IS NULL
        LIMIT 10
    """)

    missing_best_metric = cursor.fetchall()

    if not missing_best_metric:
        print("\n✓ All evaluations have best_metric set!")
        return 0

    print(f"\nFound {len(missing_best_metric)} evaluations without best_metric set")

    total_updated = 0

    for eval_row in missing_best_metric:
        eval_id = eval_row["id"]
        model_name = eval_row["model_name"]
        metrics = eval_row["metrics"]

        if "box AP" in metrics:
            best_metric = "box AP"
        elif "AP" in metrics:
            best_metric = "AP"
        else:
            best_metric = next(iter(metrics.keys())) if metrics else None

        if best_metric:
            print(f"  Evaluation {eval_id} ({model_name}): best_metric = {best_metric}")

            if not dry_run:
                cursor.execute(
                    """
                    UPDATE evaluations
                    SET best_metric = %s
                    WHERE id = %s
                """,
                    (best_metric, eval_id),
                )
                total_updated += 1

    return total_updated


def main():
    """Main validation and cleanup function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate and fix evaluation metric inconsistencies"
    )
    parser.add_argument(
        "--fix", action="store_true", help="Actually fix issues (default is dry-run)"
    )
    args = parser.parse_args()

    dry_run = not args.fix

    print("=" * 60)
    print("Evaluation Metrics Validation")
    print("=" * 60)

    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
        print("Use --fix to actually apply changes\n")
    else:
        print("\n⚠️  FIXING MODE - Changes will be applied\n")

    try:
        conn = get_database_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        print("\n1. Auditing metric labels against leaderboard definitions...")
        metric_label_issues = audit_metric_labels(cursor)

        print("\n2. Checking for safe metric naming standardizations...")
        updated_metrics = standardize_metric_names(cursor, dry_run=dry_run)

        print("\n3. Checking for missing best_metric values...")
        updated_best_metrics = validate_best_metrics(cursor, dry_run=dry_run)

        if not dry_run:
            conn.commit()
            print("\n✓ All changes committed to database")

        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  Metric labels needing review: {metric_label_issues}")
        print(f"  Metric names standardized: {updated_metrics}")
        print(f"  Best metrics set: {updated_best_metrics}")
        print("=" * 60)

        cursor.close()
        conn.close()

        if dry_run:
            has_findings = (
                metric_label_issues > 0
                or updated_metrics > 0
                or updated_best_metrics > 0
            )
            if updated_metrics > 0 or updated_best_metrics > 0:
                print("\n💡 Run with --fix to apply safe automated changes")
            if metric_label_issues > 0:
                print("\n💡 Review leaderboard mismatches before applying manual fixes")
            if has_findings:
                return 1

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
