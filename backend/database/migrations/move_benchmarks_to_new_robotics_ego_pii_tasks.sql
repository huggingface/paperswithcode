-- Re-home existing benchmarks (links, metrics and evaluation rows) onto the new
-- Robotic Manipulation, Egocentric Vision and PII Detection tasks. Applied 2026-10-21.

-- robotics -> robotic-manipulation
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT n.id, td.dataset_id, td.supports_harness FROM task_datasets td
JOIN tasks o ON o.id = td.task_id AND o.slug = 'robotics' JOIN datasets d ON d.id = td.dataset_id AND d.slug = ANY(ARRAY['libero', 'calvin-abcd-to-d', 'simplerenv-widowx', 'rlbench', 'push-t', 'simplerenv-google-robot', 'libero-plus', 'robotwin', 'franka-kitchen', 'meta-world-mt10', 'meta-world-mt50', 'robocasa', 'maniskill2', 'libero-spatial', 'libero-object', 'libero-goal', 'libero-long', 'libero-90', 'calvin-abc-d', 'robotwin-2-0-easy-50-tasks', 'robotwin-2-0-hard-50-tasks', 'robomimic-lift-ph-state', 'robomimic-can-ph-state', 'robocasa365-atomic-seen', 'libero-10', 'robocasa365-composite-seen', 'robocasa365-composite-unseen', 'libero-pro', 'robodojo']), tasks n
WHERE n.slug = 'robotic-manipulation'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT n.id, x.dataset_id, x.metric_id FROM task_dataset_metrics x
JOIN tasks o ON o.id = x.task_id AND o.slug = 'robotics' JOIN datasets d ON d.id = x.dataset_id AND d.slug = ANY(ARRAY['libero', 'calvin-abcd-to-d', 'simplerenv-widowx', 'rlbench', 'push-t', 'simplerenv-google-robot', 'libero-plus', 'robotwin', 'franka-kitchen', 'meta-world-mt10', 'meta-world-mt50', 'robocasa', 'maniskill2', 'libero-spatial', 'libero-object', 'libero-goal', 'libero-long', 'libero-90', 'calvin-abc-d', 'robotwin-2-0-easy-50-tasks', 'robotwin-2-0-hard-50-tasks', 'robomimic-lift-ph-state', 'robomimic-can-ph-state', 'robocasa365-atomic-seen', 'libero-10', 'robocasa365-composite-seen', 'robocasa365-composite-unseen', 'libero-pro', 'robodojo']), tasks n
WHERE n.slug = 'robotic-manipulation'
ON CONFLICT DO NOTHING;

UPDATE evaluations e SET task_id = n.id FROM tasks o, tasks n, datasets d
WHERE o.slug = 'robotics' AND n.slug = 'robotic-manipulation' AND e.task_id = o.id
  AND d.id = e.dataset_id AND d.slug = ANY(ARRAY['libero', 'calvin-abcd-to-d', 'simplerenv-widowx', 'rlbench', 'push-t', 'simplerenv-google-robot', 'libero-plus', 'robotwin', 'franka-kitchen', 'meta-world-mt10', 'meta-world-mt50', 'robocasa', 'maniskill2', 'libero-spatial', 'libero-object', 'libero-goal', 'libero-long', 'libero-90', 'calvin-abc-d', 'robotwin-2-0-easy-50-tasks', 'robotwin-2-0-hard-50-tasks', 'robomimic-lift-ph-state', 'robomimic-can-ph-state', 'robocasa365-atomic-seen', 'libero-10', 'robocasa365-composite-seen', 'robocasa365-composite-unseen', 'libero-pro', 'robodojo']);

DELETE FROM task_dataset_metrics x USING tasks o, datasets d
WHERE o.slug = 'robotics' AND x.task_id = o.id AND d.id = x.dataset_id AND d.slug = ANY(ARRAY['libero', 'calvin-abcd-to-d', 'simplerenv-widowx', 'rlbench', 'push-t', 'simplerenv-google-robot', 'libero-plus', 'robotwin', 'franka-kitchen', 'meta-world-mt10', 'meta-world-mt50', 'robocasa', 'maniskill2', 'libero-spatial', 'libero-object', 'libero-goal', 'libero-long', 'libero-90', 'calvin-abc-d', 'robotwin-2-0-easy-50-tasks', 'robotwin-2-0-hard-50-tasks', 'robomimic-lift-ph-state', 'robomimic-can-ph-state', 'robocasa365-atomic-seen', 'libero-10', 'robocasa365-composite-seen', 'robocasa365-composite-unseen', 'libero-pro', 'robodojo']);

DELETE FROM task_datasets td USING tasks o, datasets d
WHERE o.slug = 'robotics' AND td.task_id = o.id AND d.id = td.dataset_id AND d.slug = ANY(ARRAY['libero', 'calvin-abcd-to-d', 'simplerenv-widowx', 'rlbench', 'push-t', 'simplerenv-google-robot', 'libero-plus', 'robotwin', 'franka-kitchen', 'meta-world-mt10', 'meta-world-mt50', 'robocasa', 'maniskill2', 'libero-spatial', 'libero-object', 'libero-goal', 'libero-long', 'libero-90', 'calvin-abc-d', 'robotwin-2-0-easy-50-tasks', 'robotwin-2-0-hard-50-tasks', 'robomimic-lift-ph-state', 'robomimic-can-ph-state', 'robocasa365-atomic-seen', 'libero-10', 'robocasa365-composite-seen', 'robocasa365-composite-unseen', 'libero-pro', 'robodojo']);

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT d.introducing_paper_id, n.id, 'manual' FROM datasets d, tasks n
WHERE n.slug = 'robotic-manipulation' AND d.slug = ANY(ARRAY['libero', 'calvin-abcd-to-d', 'simplerenv-widowx', 'rlbench', 'push-t', 'simplerenv-google-robot', 'libero-plus', 'robotwin', 'franka-kitchen', 'meta-world-mt10', 'meta-world-mt50', 'robocasa', 'maniskill2', 'libero-spatial', 'libero-object', 'libero-goal', 'libero-long', 'libero-90', 'calvin-abc-d', 'robotwin-2-0-easy-50-tasks', 'robotwin-2-0-hard-50-tasks', 'robomimic-lift-ph-state', 'robomimic-can-ph-state', 'robocasa365-atomic-seen', 'libero-10', 'robocasa365-composite-seen', 'robocasa365-composite-unseen', 'libero-pro', 'robodojo']) AND d.introducing_paper_id IS NOT NULL
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

-- video-understanding -> egocentric-vision
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT n.id, td.dataset_id, td.supports_harness FROM task_datasets td
JOIN tasks o ON o.id = td.task_id AND o.slug = 'video-understanding' JOIN datasets d ON d.id = td.dataset_id AND d.slug = ANY(ARRAY['egolife', 'egoschema', 'egoper']), tasks n
WHERE n.slug = 'egocentric-vision'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT n.id, x.dataset_id, x.metric_id FROM task_dataset_metrics x
JOIN tasks o ON o.id = x.task_id AND o.slug = 'video-understanding' JOIN datasets d ON d.id = x.dataset_id AND d.slug = ANY(ARRAY['egolife', 'egoschema', 'egoper']), tasks n
WHERE n.slug = 'egocentric-vision'
ON CONFLICT DO NOTHING;

UPDATE evaluations e SET task_id = n.id FROM tasks o, tasks n, datasets d
WHERE o.slug = 'video-understanding' AND n.slug = 'egocentric-vision' AND e.task_id = o.id
  AND d.id = e.dataset_id AND d.slug = ANY(ARRAY['egolife', 'egoschema', 'egoper']);

DELETE FROM task_dataset_metrics x USING tasks o, datasets d
WHERE o.slug = 'video-understanding' AND x.task_id = o.id AND d.id = x.dataset_id AND d.slug = ANY(ARRAY['egolife', 'egoschema', 'egoper']);

DELETE FROM task_datasets td USING tasks o, datasets d
WHERE o.slug = 'video-understanding' AND td.task_id = o.id AND d.id = td.dataset_id AND d.slug = ANY(ARRAY['egolife', 'egoschema', 'egoper']);

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT d.introducing_paper_id, n.id, 'manual' FROM datasets d, tasks n
WHERE n.slug = 'egocentric-vision' AND d.slug = ANY(ARRAY['egolife', 'egoschema', 'egoper']) AND d.introducing_paper_id IS NOT NULL
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

-- named-entity-recognition -> pii-detection
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT n.id, td.dataset_id, td.supports_harness FROM task_datasets td
JOIN tasks o ON o.id = td.task_id AND o.slug = 'named-entity-recognition' JOIN datasets d ON d.id = td.dataset_id AND d.slug = ANY(ARRAY['pii-masking-300k', 'open-pii-masking-500k-span-correct', 'open-pii-masking-500k-label-exact']), tasks n
WHERE n.slug = 'pii-detection'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT n.id, x.dataset_id, x.metric_id FROM task_dataset_metrics x
JOIN tasks o ON o.id = x.task_id AND o.slug = 'named-entity-recognition' JOIN datasets d ON d.id = x.dataset_id AND d.slug = ANY(ARRAY['pii-masking-300k', 'open-pii-masking-500k-span-correct', 'open-pii-masking-500k-label-exact']), tasks n
WHERE n.slug = 'pii-detection'
ON CONFLICT DO NOTHING;

UPDATE evaluations e SET task_id = n.id FROM tasks o, tasks n, datasets d
WHERE o.slug = 'named-entity-recognition' AND n.slug = 'pii-detection' AND e.task_id = o.id
  AND d.id = e.dataset_id AND d.slug = ANY(ARRAY['pii-masking-300k', 'open-pii-masking-500k-span-correct', 'open-pii-masking-500k-label-exact']);

DELETE FROM task_dataset_metrics x USING tasks o, datasets d
WHERE o.slug = 'named-entity-recognition' AND x.task_id = o.id AND d.id = x.dataset_id AND d.slug = ANY(ARRAY['pii-masking-300k', 'open-pii-masking-500k-span-correct', 'open-pii-masking-500k-label-exact']);

DELETE FROM task_datasets td USING tasks o, datasets d
WHERE o.slug = 'named-entity-recognition' AND td.task_id = o.id AND d.id = td.dataset_id AND d.slug = ANY(ARRAY['pii-masking-300k', 'open-pii-masking-500k-span-correct', 'open-pii-masking-500k-label-exact']);

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT d.introducing_paper_id, n.id, 'manual' FROM datasets d, tasks n
WHERE n.slug = 'pii-detection' AND d.slug = ANY(ARRAY['pii-masking-300k', 'open-pii-masking-500k-span-correct', 'open-pii-masking-500k-label-exact']) AND d.introducing_paper_id IS NOT NULL
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

-- EPIC-KITCHENS-100 has no results yet; link it only.
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d
WHERE t.slug = 'egocentric-vision' AND d.slug = 'epic-kitchens-100-ek100'
ON CONFLICT (task_id, dataset_id) DO NOTHING;
