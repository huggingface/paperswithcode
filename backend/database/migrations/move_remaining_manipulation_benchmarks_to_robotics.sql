-- Robotics holds every robot leaderboard; robotic-manipulation stays a paper tag.
-- Move the last eight boards (RLBench, Meta-World MT10/MT50, ManiSkill2, Push-T,
-- Franka Kitchen, RoboMimic Lift/Can PH State) from robotic-manipulation to robotics,
-- keeping their evaluation ids. Applied 2026-10-22.

CREATE TEMP TABLE manipulation_boards ON COMMIT DROP AS
SELECT id AS dataset_id FROM datasets
WHERE slug = ANY(ARRAY['rlbench', 'meta-world-mt10', 'meta-world-mt50', 'maniskill2', 'push-t', 'franka-kitchen', 'robomimic-lift-ph-state', 'robomimic-can-ph-state']);

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT r.id, td.dataset_id, td.supports_harness FROM task_datasets td
JOIN tasks m ON m.id = td.task_id AND m.slug = 'robotic-manipulation'
JOIN manipulation_boards b ON b.dataset_id = td.dataset_id, tasks r
WHERE r.slug = 'robotics'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT r.id, x.dataset_id, x.metric_id FROM task_dataset_metrics x
JOIN tasks m ON m.id = x.task_id AND m.slug = 'robotic-manipulation'
JOIN manipulation_boards b ON b.dataset_id = x.dataset_id, tasks r
WHERE r.slug = 'robotics'
ON CONFLICT DO NOTHING;

UPDATE evaluations e SET task_id = r.id FROM tasks r, tasks m
WHERE r.slug = 'robotics' AND m.slug = 'robotic-manipulation' AND e.task_id = m.id
  AND e.dataset_id IN (SELECT dataset_id FROM manipulation_boards);

DELETE FROM task_dataset_metrics x USING tasks m
WHERE m.slug = 'robotic-manipulation' AND x.task_id = m.id
  AND x.dataset_id IN (SELECT dataset_id FROM manipulation_boards);

DELETE FROM task_datasets td USING tasks m
WHERE m.slug = 'robotic-manipulation' AND td.task_id = m.id
  AND td.dataset_id IN (SELECT dataset_id FROM manipulation_boards);
