-- Add Fall Detection.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Fall Detection',
    'fall-detection',
    'Fall detection identifies when a person falls, so that elderly people and patients living alone can get help quickly. Systems work from camera video, depth or skeleton sequences, wearable accelerometers, radar or audio, and must separate real falls from lying down, sitting and other daily activities while keeping false alarms low. Staged datasets dominate the literature, so generalization to real homes is the main open problem, which links the task to [Anomaly Detection](/tasks/anomaly-detection) and human activity recognition.',
    'fall detection, human fall detection, fall recognition, elderly fall detection, fall detection system, fall detection systems, vision-based fall detection, wearable fall detection, fall event detection, fall prediction',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[OmniFall: A Unified Staged-to-Wild Benchmark for Human Fall Detection](/paper/2505.19889)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

-- 11 papers match the task keywords (same matcher as the
-- weekly keyword backfill).
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'auto'
FROM papers p
CROSS JOIN tasks t
WHERE t.slug = 'fall-detection'
  AND p.id IN (
        10106, 36027, 41116, 49781, 72476, 72611, 82133, 88712, 95712, 97522, 104211
  )
ON CONFLICT DO NOTHING;
