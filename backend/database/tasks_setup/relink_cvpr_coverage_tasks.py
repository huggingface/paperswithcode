#!/usr/bin/env python3
"""Re-link CVPR coverage tasks after tightening keywords to reduce false positives."""

from __future__ import annotations

import os

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

from backend.utils.keyword_matching import (
    create_keyword_patterns,
    find_matching_items_simple,
)

TASK_KEYWORDS: dict[str, str] = {
    "autonomous-driving": (
        "self-driving, self driving, end-to-end driving, ADAS, BEV perception, "
        "driving scene understanding, autonomous driving system, self-driving car, "
        "self-driving vehicle, occupancy prediction for autonomous driving"
    ),
    "anomaly-detection": (
        "industrial anomaly, out-of-distribution detection, OOD detection, "
        "unsupervised anomaly detection, anomaly localization, "
        "zero-shot anomaly detection, video anomaly detection, anomaly segmentation, "
        "image anomaly detection"
    ),
    "remote-sensing": (
        "remote sensing, satellite imagery, aerial imagery, drone imagery"
    ),
    "deepfake-detection": (
        "deepfake detection, media forensics, face forensics, anti-spoofing, "
        "spoofing detection, synthetic media detection, face anti-spoof, "
        "face forgery detection, video forgery detection"
    ),
    "object-tracking": (
        "multi-object tracking, MOT, single object tracking, tracking-by-detection, "
        "multi object track, visual object tracking"
    ),
    "image-restoration": (
        "image restoration, image denoising, image deblurring, deraining, dehazing, "
        "blind image restoration, rain removal, haze removal"
    ),
    "medical-imaging": (
        "medical imaging, digital pathology, computational pathology, mammography, "
        "histopathology, clinical imaging, retinal imaging, fundus, ultrasound imaging, "
        "whole slide imaging, medical image segmentation, medical image analysis"
    ),
    "optical-flow": (
        "optical flow estimation, dense optical flow, optical flow network, "
        "optical flow prediction, optical flow model"
    ),
    "stereo-matching": (
        "stereo matching, stereo disparity, disparity estimation, depth from stereo"
    ),
    "omni-models": (
        "omni model, omni models, omni-modal, omnimodal, any-to-any model, "
        "interleaved multimodal, omni understanding"
    ),
}


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PWC_DB_HOST", "localhost"),
        port=os.getenv("PWC_DB_PORT", "5432"),
        database=os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        user=os.getenv("PWC_DB_USER", "postgres"),
        password=os.getenv("PWC_DB_PASSWORD", "postgres"),
    )


def relink_task(cur, slug: str, keywords: str) -> tuple[int, int]:
    cur.execute("SELECT id FROM tasks WHERE slug = %s", (slug,))
    task = cur.fetchone()
    if not task:
        raise RuntimeError(f"Task not found: {slug}")
    task_id = task["id"]

    cur.execute("UPDATE tasks SET keywords = %s WHERE id = %s", (keywords, task_id))
    cur.execute(
        "DELETE FROM paper_tasks WHERE task_id = %s AND source = 'auto'",
        (task_id,),
    )
    deleted = cur.rowcount

    case_sensitive, case_insensitive = create_keyword_patterns(
        [{"id": task_id, "keywords": keywords}]
    )

    cur.execute(
        """
        SELECT id, title, abstract
        FROM papers
        WHERE is_latest_version
        ORDER BY id
        """
    )

    matches: list[tuple[int, int]] = []
    for row in cur:
        text = f"{row['title']} {row['abstract'] or ''}"
        if find_matching_items_simple(text, case_sensitive, case_insensitive):
            matches.append((row["id"], task_id))

    if matches:
        execute_batch(
            cur,
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (%s, %s, 'auto')
            ON CONFLICT DO NOTHING
            """,
            matches,
            page_size=1000,
        )

    return deleted, len(matches)


def main() -> None:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("Re-linking CVPR coverage tasks with conservative keywords")
    print("=" * 72)
    for slug, keywords in TASK_KEYWORDS.items():
        deleted, created = relink_task(cur, slug, keywords)
        print(f"{slug:28s}  deleted {deleted:5,}  created {created:5,}")

    conn.commit()
    cur.close()
    conn.close()
    print("=" * 72)
    print("Done.")


if __name__ == "__main__":
    main()
