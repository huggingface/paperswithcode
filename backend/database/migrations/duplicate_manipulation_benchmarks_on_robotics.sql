-- Show the manipulation benchmarks moved by move_benchmarks_to_new_robotics_ego_pii_tasks.sql
-- on Robotics again: copy their task links, metric links and evaluation rows from
-- robotic-manipulation back to robotics, so both task pages list them. Applied 2026-10-22.
-- Idempotent: a benchmark that already has Robotics evaluations is skipped.

CREATE TEMP TABLE dup_boards ON COMMIT DROP AS
SELECT d.id AS dataset_id FROM datasets d
WHERE d.slug = ANY(ARRAY['libero', 'calvin-abcd-to-d', 'simplerenv-widowx', 'rlbench', 'push-t', 'simplerenv-google-robot', 'libero-plus', 'robotwin', 'franka-kitchen', 'meta-world-mt10', 'meta-world-mt50', 'robocasa', 'maniskill2', 'libero-spatial', 'libero-object', 'libero-goal', 'libero-long', 'libero-90', 'calvin-abc-d', 'robotwin-2-0-easy-50-tasks', 'robotwin-2-0-hard-50-tasks', 'robomimic-lift-ph-state', 'robomimic-can-ph-state', 'robocasa365-atomic-seen', 'libero-10', 'robocasa365-composite-seen', 'robocasa365-composite-unseen', 'libero-pro', 'robodojo'])
  AND NOT EXISTS (
    SELECT 1 FROM evaluations e JOIN tasks o ON o.id = e.task_id AND o.slug = 'robotics'
    WHERE e.dataset_id = d.id
  );

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT o.id, td.dataset_id, td.supports_harness FROM task_datasets td
JOIN tasks n ON n.id = td.task_id AND n.slug = 'robotic-manipulation'
JOIN dup_boards b ON b.dataset_id = td.dataset_id, tasks o
WHERE o.slug = 'robotics'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT o.id, x.dataset_id, x.metric_id FROM task_dataset_metrics x
JOIN tasks n ON n.id = x.task_id AND n.slug = 'robotic-manipulation'
JOIN dup_boards b ON b.dataset_id = x.dataset_id, tasks o
WHERE o.slug = 'robotics'
ON CONFLICT DO NOTHING;

INSERT INTO evaluations (
    task_id, paper_id, dataset_id, model_name, methodology, metrics, uses_additional_data,
    best_rank, best_metric, evaluated_on, external_source_url, created_at, updated_at,
    harness, num_parameters, is_open, hf_model_url, source_url, external
)
SELECT o.id, e.paper_id, e.dataset_id, e.model_name, e.methodology, e.metrics, e.uses_additional_data,
    e.best_rank, e.best_metric, e.evaluated_on, e.external_source_url, e.created_at, e.updated_at,
    e.harness, e.num_parameters, e.is_open, e.hf_model_url, e.source_url, e.external
FROM evaluations e
JOIN tasks n ON n.id = e.task_id AND n.slug = 'robotic-manipulation'
JOIN dup_boards b ON b.dataset_id = e.dataset_id, tasks o
WHERE o.slug = 'robotics';
