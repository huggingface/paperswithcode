-- Move the COCO and LVIS instance segmentation leaderboards from
-- image-segmentation to the instance-segmentation task added on 2026-10-21.
-- Leaderboards are keyed by (task, dataset), so the task link, the leaderboard
-- metrics, the evaluation rows and the badge tombstones all move together.
-- Cityscapes stays on image-segmentation because it mixes semantic and
-- instance results.

CREATE TEMP TABLE benchmark_task_moves ON COMMIT DROP AS
SELECT d.id AS dataset_id, old_t.id AS old_task_id, new_t.id AS new_task_id, new_t.slug AS new_task_slug
FROM (
    VALUES
        ('coco-2017-instance-segmentation', 'image-segmentation', 'instance-segmentation'),
        ('lvis-instance-segmentation', 'image-segmentation', 'instance-segmentation')
) AS v(dataset_slug, old_task_slug, new_task_slug)
JOIN datasets d ON d.slug = v.dataset_slug
JOIN tasks old_t ON old_t.slug = v.old_task_slug
JOIN tasks new_t ON new_t.slug = v.new_task_slug;

INSERT INTO task_datasets (task_id, dataset_id, created_at, updated_at, supports_harness)
SELECT m.new_task_id, td.dataset_id, td.created_at, now(), td.supports_harness
FROM task_datasets td
JOIN benchmark_task_moves m ON m.dataset_id = td.dataset_id AND m.old_task_id = td.task_id
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id, created_at)
SELECT m.new_task_id, tdm.dataset_id, tdm.metric_id, tdm.created_at
FROM task_dataset_metrics tdm
JOIN benchmark_task_moves m ON m.dataset_id = tdm.dataset_id AND m.old_task_id = tdm.task_id
ON CONFLICT DO NOTHING;

UPDATE evaluations e
SET task_id = m.new_task_id, updated_at = now()
FROM benchmark_task_moves m
WHERE e.dataset_id = m.dataset_id AND e.task_id = m.old_task_id;

UPDATE evaluation_badge_tombstones t
SET task_id = m.new_task_id, task_slug = m.new_task_slug
FROM benchmark_task_moves m
WHERE t.dataset_id = m.dataset_id AND t.task_id = m.old_task_id;

DELETE FROM task_dataset_metrics tdm
USING benchmark_task_moves m
WHERE tdm.dataset_id = m.dataset_id AND tdm.task_id = m.old_task_id;

DELETE FROM task_datasets td
USING benchmark_task_moves m
WHERE td.dataset_id = m.dataset_id AND td.task_id = m.old_task_id;

-- Papers with a result on a moved leaderboard belong to the new task.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT e.paper_id, m.new_task_id, 'manual'
FROM evaluations e
JOIN benchmark_task_moves m ON m.dataset_id = e.dataset_id AND m.new_task_id = e.task_id
ON CONFLICT DO NOTHING;
