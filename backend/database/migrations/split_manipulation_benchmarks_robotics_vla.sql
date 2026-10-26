-- Supersedes duplicate_manipulation_benchmarks_on_robotics.sql. Applied 2026-10-22.
-- 1. Remove the evaluation copies that file put on robotics, re-pointing research
--    events to the original rows first.
-- 2. Move the generalist VLA suites (LIBERO, SimplerEnv, CALVIN, RoboTwin, RoboCasa,
--    RoboDojo) back to robotics, keeping their original evaluation ids.
-- 3. Leave RLBench, Meta-World, ManiSkill2, Push-T, Franka Kitchen and RoboMimic on
--    robotic-manipulation only.

CREATE TEMP TABLE vla_boards ON COMMIT DROP AS
SELECT id AS dataset_id FROM datasets
WHERE slug = ANY(ARRAY['libero', 'libero-spatial', 'libero-object', 'libero-goal', 'libero-long', 'libero-90', 'libero-10', 'libero-plus', 'libero-pro', 'simplerenv-widowx', 'simplerenv-google-robot', 'calvin-abc-d', 'calvin-abcd-to-d', 'robotwin', 'robotwin-2-0-easy-50-tasks', 'robotwin-2-0-hard-50-tasks', 'robocasa', 'robocasa365-atomic-seen', 'robocasa365-composite-seen', 'robocasa365-composite-unseen', 'robodojo']);

CREATE TEMP TABLE manipulation_boards ON COMMIT DROP AS
SELECT id AS dataset_id FROM datasets
WHERE slug = ANY(ARRAY['rlbench', 'meta-world-mt10', 'meta-world-mt50', 'maniskill2', 'push-t', 'franka-kitchen', 'robomimic-lift-ph-state', 'robomimic-can-ph-state']);

-- Copies exist only where the same board also has rows on robotic-manipulation.
CREATE TEMP TABLE robotics_copies ON COMMIT DROP AS
SELECT c.id AS copy_id, (
    SELECT min(o.id) FROM evaluations o JOIN tasks m ON m.id = o.task_id AND m.slug = 'robotic-manipulation'
    WHERE o.dataset_id = c.dataset_id AND o.paper_id = c.paper_id
      AND coalesce(o.model_name, '') = coalesce(c.model_name, '')
      AND coalesce(o.harness, '') = coalesce(c.harness, '')
) AS original_id
FROM evaluations c JOIN tasks r ON r.id = c.task_id AND r.slug = 'robotics'
WHERE c.dataset_id IN (SELECT dataset_id FROM vla_boards UNION SELECT dataset_id FROM manipulation_boards)
  AND EXISTS (
    SELECT 1 FROM evaluations o JOIN tasks m ON m.id = o.task_id AND m.slug = 'robotic-manipulation'
    WHERE o.dataset_id = c.dataset_id
  );

UPDATE research_events r SET evaluation_id = rc.original_id
FROM robotics_copies rc WHERE r.evaluation_id = rc.copy_id;

DELETE FROM evaluations WHERE id IN (SELECT copy_id FROM robotics_copies);

UPDATE evaluations e SET task_id = r.id FROM tasks r, tasks m
WHERE r.slug = 'robotics' AND m.slug = 'robotic-manipulation' AND e.task_id = m.id
  AND e.dataset_id IN (SELECT dataset_id FROM vla_boards);

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT r.id, td.dataset_id, td.supports_harness FROM task_datasets td
JOIN tasks m ON m.id = td.task_id AND m.slug = 'robotic-manipulation'
JOIN vla_boards b ON b.dataset_id = td.dataset_id, tasks r
WHERE r.slug = 'robotics'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT r.id, x.dataset_id, x.metric_id FROM task_dataset_metrics x
JOIN tasks m ON m.id = x.task_id AND m.slug = 'robotic-manipulation'
JOIN vla_boards b ON b.dataset_id = x.dataset_id, tasks r
WHERE r.slug = 'robotics'
ON CONFLICT DO NOTHING;

DELETE FROM task_dataset_metrics x USING tasks m
WHERE m.slug = 'robotic-manipulation' AND x.task_id = m.id
  AND x.dataset_id IN (SELECT dataset_id FROM vla_boards);

DELETE FROM task_datasets td USING tasks m
WHERE m.slug = 'robotic-manipulation' AND td.task_id = m.id
  AND td.dataset_id IN (SELECT dataset_id FROM vla_boards);

DELETE FROM task_dataset_metrics x USING tasks r
WHERE r.slug = 'robotics' AND x.task_id = r.id
  AND x.dataset_id IN (SELECT dataset_id FROM manipulation_boards);

DELETE FROM task_datasets td USING tasks r
WHERE r.slug = 'robotics' AND td.task_id = r.id
  AND td.dataset_id IN (SELECT dataset_id FROM manipulation_boards);
