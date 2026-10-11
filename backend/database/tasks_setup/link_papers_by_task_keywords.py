#!/usr/bin/env python3
"""
Link papers to tasks based on keyword matching in titles and abstracts.

Matching Strategy:
- Uses simple matching where all matching keywords are tagged
- A paper can have multiple task categories (e.g., image classification AND object detection)

Case-Sensitivity Rules:
- Keywords with at least 1 capital letter: case-sensitive matching
  * Examples: "BERT", "VLM", "GPT-4"
  * Uses substring matching to catch plurals (VLMs, GANs) and compounds (LVLMs, OpenCLIP)
  * Case sensitivity prevents false positives (CLIP vs clip)
- All-lowercase keywords: case-insensitive matching
  * Examples: "transformer", "attention", "object detection"
  * Uses word boundary matching to prevent false matches (e.g., "transformed" when looking for "transformer")

Modes:
- Default (add-only): inserts any new paper<->task links the matcher produces,
  never removes anything. Safe to run repeatedly. (`ON CONFLICT DO NOTHING`)
- `--rebuild`: deletes every `source = 'auto'` row first, then re-inserts what
  the matcher currently produces. `source = 'manual'` rows (set via the admin
  API or one-off scripts) are never touched.
"""

import argparse
import os
from typing import Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict

from backend.services.task_keyword_batches import insert_task_links, iter_latest_papers
from backend.utils.keyword_matching import (
    apply_task_supersession_rules,
    create_keyword_patterns,
    find_matching_items_simple,
)


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", "postgres"),
    )


def load_tasks_with_keywords(conn, task_slugs: list[str] | None = None) -> List[Dict]:
    """Load all tasks that have keywords defined."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if task_slugs:
        cur.execute(
            """
            SELECT id, slug, name, keywords
            FROM tasks
            WHERE keywords IS NOT NULL AND keywords != '' AND slug = ANY(%s)
            ORDER BY id
            """,
            (task_slugs,),
        )
    else:
        cur.execute("""
            SELECT id, slug, name, keywords
            FROM tasks
            WHERE keywords IS NOT NULL AND keywords != ''
            ORDER BY id
        """)

    tasks = cur.fetchall()
    cur.close()
    return tasks


def link_papers_by_task_keywords(
    rebuild: bool = False,
    paper_ids: list[int] | None = None,
    task_slugs: list[str] | None = None,
):
    """Link all papers, or a specified subset, to tasks by keyword matching."""

    try:
        print("=" * 80)
        print("Linking Papers to Tasks Based on Keywords")
        if rebuild:
            print("Mode: REBUILD (delete-then-insert for source='auto' rows)")
        else:
            print("Mode: add-only (default)")
        if paper_ids is not None:
            print(f"Scope: {len(paper_ids):,} selected papers")
        if task_slugs:
            print(f"Tasks: {', '.join(task_slugs)}")
        print("=" * 80)

        conn = get_db_connection()

        print("\n1. Loading tasks with keywords...")
        tasks = load_tasks_with_keywords(conn, task_slugs)
        if task_slugs:
            found_slugs = {task["slug"] for task in tasks}
            missing_slugs = sorted(set(task_slugs) - found_slugs)
            if missing_slugs:
                raise ValueError(
                    f"Unknown tasks or tasks without keywords: {', '.join(missing_slugs)}"
                )
        print(f"   ✓ Loaded {len(tasks)} tasks with keywords")
        slug_to_id = {task["slug"]: task["id"] for task in tasks}
        task_keywords_by_slug = {
            task["slug"]: [
                keyword.strip()
                for keyword in task["keywords"].split(",")
                if keyword.strip()
            ]
            for task in tasks
        }

        print("\n2. Building keyword patterns...")
        case_sensitive_patterns, case_insensitive_patterns = create_keyword_patterns(
            tasks
        )
        total_keywords = len(case_sensitive_patterns) + len(case_insensitive_patterns)
        print(
            f"   ✓ Built patterns for {total_keywords} unique keywords (simple matching)"
        )
        print(f"   - {len(case_sensitive_patterns)} unique case-sensitive keywords")
        print(f"   - {len(case_insensitive_patterns)} unique case-insensitive keywords")

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as count FROM paper_tasks")
        initial_count = cur.fetchone()["count"]
        cur.execute("SELECT source, COUNT(*) as count FROM paper_tasks GROUP BY source")
        by_source_initial = {row["source"]: row["count"] for row in cur.fetchall()}
        print(f"\n3. Current paper_tasks relationships: {initial_count:,}")
        print(f"   - auto:   {by_source_initial.get('auto', 0):>10,}")
        print(f"   - manual: {by_source_initial.get('manual', 0):>10,}")

        if rebuild:
            scope = "selected-task" if task_slugs else "all"
            print(f"\n3b. REBUILD: deleting {scope} source='auto' rows ...")
            cur2 = conn.cursor()
            if task_slugs:
                cur2.execute(
                    "DELETE FROM paper_tasks WHERE source = 'auto' AND task_id = ANY(%s)",
                    ([task["id"] for task in tasks],),
                )
            else:
                cur2.execute("DELETE FROM paper_tasks WHERE source = 'auto'")
            deleted_count = cur2.rowcount
            conn.commit()
            cur2.close()
            print(f"   ✓ Deleted {deleted_count:,} auto rows")

        print("\n4. Processing papers...")
        print("   (Streaming through papers and matching keywords...)")

        cur.close()
        conn.close()

        papers_processed = 0
        papers_matched = 0
        new_relationships = 0
        batch = []
        batch_size = 1000

        task_match_counts = defaultdict(int)

        for paper in iter_latest_papers(get_db_connection, paper_ids):
            papers_processed += 1

            if papers_processed % 5000 == 0:
                print(
                    f"   Processed {papers_processed:,} papers, "
                    f"matched {papers_matched:,}, "
                    f"found {new_relationships:,} new relationships..."
                )

            text = ""
            if paper["title"]:
                text = paper["title"]
            if paper["abstract"]:
                text += " " + paper["abstract"]

            if not text.strip():
                continue

            matching_task_ids = find_matching_items_simple(
                text, case_sensitive_patterns, case_insensitive_patterns
            )
            matching_task_ids = apply_task_supersession_rules(
                matching_task_ids,
                slug_to_id,
                text,
                paper["title"],
                task_keywords_by_slug,
            )

            if matching_task_ids:
                papers_matched += 1

                for task_id in matching_task_ids:
                    batch.append({"paper_id": paper["id"], "task_id": task_id})
                    new_relationships += 1
                    task_match_counts[task_id] += 1

            if len(batch) >= batch_size:
                insert_task_links(get_db_connection, batch)
                batch = []

        if batch:
            insert_task_links(get_db_connection, batch)

        conn = get_db_connection()

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as count FROM paper_tasks")
        final_count = cur.fetchone()["count"]
        cur.execute("SELECT source, COUNT(*) as count FROM paper_tasks GROUP BY source")
        by_source_final = {row["source"]: row["count"] for row in cur.fetchall()}

        print(f"\n   ✓ Finished processing {papers_processed:,} papers")

        print("\n" + "=" * 80)
        print("Import Statistics")
        print("=" * 80)
        print(f"Papers processed:              {papers_processed:>10,}")
        print(f"Papers with keyword matches:   {papers_matched:>10,}")
        print(f"Relationships matcher emitted: {new_relationships:>10,}")
        print(f"Initial paper_tasks count:     {initial_count:>10,}")
        print(f"Final paper_tasks count:       {final_count:>10,}")
        print(f"Net delta:                     {final_count - initial_count:>+10,}")
        print(f"Auto rows now:                 {by_source_final.get('auto', 0):>10,}")
        print(f"Manual rows now:               {by_source_final.get('manual', 0):>10,}")

        print("\n" + "=" * 80)
        print("Top 20 Tasks by New Keyword Matches")
        print("=" * 80)

        task_id_to_name = {task["id"]: task["name"] for task in tasks}

        sorted_tasks = sorted(
            task_match_counts.items(), key=lambda x: x[1], reverse=True
        )[:20]

        for task_id, count in sorted_tasks:
            task_name = task_id_to_name.get(task_id, f"Unknown (ID {task_id})")
            print(f"{task_name:40} {count:>8,} matches")

        print("\n" + "=" * 80)
        print("Top 20 Tasks by Total Paper Count (after keyword linking)")
        print("=" * 80)

        cur.execute("""
            SELECT t.name, COUNT(pt.paper_id) as paper_count
            FROM tasks t
            LEFT JOIN paper_tasks pt ON t.id = pt.task_id
            GROUP BY t.id, t.name
            ORDER BY paper_count DESC
            LIMIT 20
        """)

        for row in cur.fetchall():
            print(f"{row['name']:40} {row['paper_count']:>8,} papers")

        cur.close()
        conn.close()

        print("\n✅ Successfully linked papers to tasks based on keywords!")

    except Exception as e:
        print(f"\n❌ Error linking papers by keywords: {str(e)}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "Delete all source='auto' paper_tasks rows before re-inserting. "
            "Manual rows are preserved. Use this to drop stale tags created by "
            "old/broader keyword sets."
        ),
    )
    parser.add_argument(
        "--task-slug",
        action="append",
        dest="task_slugs",
        help=(
            "Limit matching and rebuild deletion to this task slug. Repeat for "
            "multiple tasks."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    exit(
        link_papers_by_task_keywords(
            rebuild=args.rebuild,
            task_slugs=args.task_slugs,
        )
    )
