#!/usr/bin/env python3
"""
Link papers to methods based on keyword matching in titles and abstracts.

Matching Strategy:
- Uses longest-match priority to prevent overlapping matches
- If text contains "GPT-4", only GPT-4 matches (not GPT)
- This handles hierarchical method names like GPT, GPT-2, GPT-3, GPT-4

Case-Sensitivity Rules:
- Keywords with at least 1 capital letter: case-sensitive matching
  * Examples: "BERT", "GPT-4", "ResNet", "VLM"
  * Uses substring matching to catch plurals (VLMs, GANs) and compounds (LVLMs, OpenCLIP)
  * Case sensitivity prevents false positives (CLIP vs clip)
- All-lowercase keywords: case-insensitive matching
  * Examples: "transformer", "attention", "dropout"
  * Uses word boundary matching to prevent false matches
"""

import os

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
from typing import Dict, List
from collections import defaultdict

from backend.utils.keyword_matching import (
    create_keyword_patterns_with_metadata,
    find_matching_items_longest_match,
)

KEYWORD_EVIDENCE_UPSERT = """
    WITH inserted AS (
        INSERT INTO paper_methods (paper_id, method_id)
        SELECT %(paper_id)s, %(method_id)s
        WHERE NOT EXISTS (
            SELECT 1 FROM paper_method_exclusions
            WHERE paper_id = %(paper_id)s AND method_id = %(method_id)s
        )
        ON CONFLICT (paper_id, method_id) DO NOTHING
        RETURNING paper_id, method_id
    )
    INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
    SELECT paper_id, method_id, 'keyword' FROM inserted
    UNION ALL
    SELECT %(paper_id)s, %(method_id)s, 'keyword'
    WHERE NOT EXISTS (SELECT 1 FROM inserted)
      AND EXISTS (
          SELECT 1 FROM paper_methods
          WHERE paper_id = %(paper_id)s AND method_id = %(method_id)s
      )
    ON CONFLICT (paper_id, method_id, evidence_type)
    DO UPDATE SET last_seen_at = now()
"""


def load_methods_with_keywords(conn) -> List[Dict]:
    """Load all methods that have keywords defined."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, keywords
        FROM methods
        WHERE keywords IS NOT NULL AND keywords != ''
        ORDER BY id
    """)

    methods = cur.fetchall()
    cur.close()
    return methods


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", "postgres"),
    )


def link_papers_by_keywords():
    """Main function to link papers to methods based on keyword matching."""

    try:
        print("=" * 80)
        print("Linking Papers to Methods Based on Keywords")
        print("=" * 80)

        conn = get_db_connection()
        print("\n1. Loading methods with keywords...")
        methods = load_methods_with_keywords(conn)
        print(f"   ✓ Loaded {len(methods)} methods with keywords")

        print("\n2. Building keyword patterns...")
        case_sensitive_patterns, case_insensitive_patterns = (
            create_keyword_patterns_with_metadata(methods)
        )
        total_keywords = len(case_sensitive_patterns) + len(case_insensitive_patterns)
        print(
            f"   ✓ Built patterns for {total_keywords} unique keywords (longest-match)"
        )
        print(f"   - {len(case_sensitive_patterns)} unique case-sensitive keywords")
        print(f"   - {len(case_insensitive_patterns)} unique case-insensitive keywords")

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as count FROM paper_methods")
        initial_count = cur.fetchone()["count"]
        print(f"\n3. Current paper_methods relationships: {initial_count:,}")

        print("\n4. Processing papers...")
        print("   (Streaming through papers and matching keywords...)")

        cur.execute("""
            SELECT id, title, abstract
            FROM papers
            WHERE is_latest_version = true
            ORDER BY id
        """)

        papers_processed = 0
        papers_matched = 0
        new_relationships = 0
        batch = []
        batch_size = 1000

        method_match_counts = defaultdict(int)

        for paper in cur:
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

            matching_method_ids = find_matching_items_longest_match(
                text, case_sensitive_patterns, case_insensitive_patterns
            )

            if matching_method_ids:
                papers_matched += 1

                for method_id in matching_method_ids:
                    batch.append({"paper_id": paper["id"], "method_id": method_id})
                    new_relationships += 1
                    method_match_counts[method_id] += 1

            if len(batch) >= batch_size:
                cur2 = conn.cursor()
                execute_batch(
                    cur2,
                    KEYWORD_EVIDENCE_UPSERT,
                    batch,
                )
                conn.commit()
                cur2.close()
                batch = []

        if batch:
            cur2 = conn.cursor()
            execute_batch(
                cur2,
                KEYWORD_EVIDENCE_UPSERT,
                batch,
            )
            conn.commit()
            cur2.close()

        cur.close()

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as count FROM paper_methods")
        final_count = cur.fetchone()["count"]

        print(f"\n   ✓ Finished processing {papers_processed:,} papers")

        print("\n" + "=" * 80)
        print("Import Statistics")
        print("=" * 80)
        print(f"Papers processed:              {papers_processed:>10,}")
        print(f"Papers with keyword matches:   {papers_matched:>10,}")
        print(f"New relationships found:       {new_relationships:>10,}")
        print(f"Initial paper_methods count:   {initial_count:>10,}")
        print(f"Final paper_methods count:     {final_count:>10,}")
        print(f"Relationships actually added:  {final_count - initial_count:>10,}")

        print("\n" + "=" * 80)
        print("Top 20 Methods by New Keyword Matches")
        print("=" * 80)

        method_id_to_name = {}
        for method in methods:
            method_id_to_name[method["id"]] = method["name"]

        sorted_methods = sorted(
            method_match_counts.items(), key=lambda x: x[1], reverse=True
        )[:20]

        for method_id, count in sorted_methods:
            method_name = method_id_to_name.get(method_id, f"Unknown (ID {method_id})")
            print(f"{method_name:30} {count:>8,} matches")

        print("\n" + "=" * 80)
        print("Top 20 Methods by Total Paper Count (after keyword linking)")
        print("=" * 80)

        cur.execute("""
            SELECT m.name, COUNT(pm.paper_id) as paper_count
            FROM methods m
            LEFT JOIN paper_methods pm ON m.id = pm.method_id
            GROUP BY m.id, m.name
            ORDER BY paper_count DESC
            LIMIT 20
        """)

        for row in cur.fetchall():
            print(f"{row['name']:30} {row['paper_count']:>8,} papers")

        cur.close()
        conn.close()

        print("\n✅ Successfully linked papers to methods based on keywords!")

    except Exception as e:
        print(f"\n❌ Error linking papers by keywords: {str(e)}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(link_papers_by_keywords())
