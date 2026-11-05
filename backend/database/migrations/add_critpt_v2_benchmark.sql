-- CritPt v2 board on Scientific Reasoning; kept current by sync_critpt_v2.

BEGIN;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, homepage,
    introducing_paper_id, introducing_paper_title, introduced_year, paper_url,
    abstract_linking, created_at, updated_at
)
SELECT
    'CritPt v2',
    'CritPt v2 (Complex Research using Integrated Thinking - Physics Test, revised)',
    'critpt-v2',
    'CritPt v2 is the benchmark authors'' revision of [CritPt](/benchmark/critpt): the 70 unpublished, research-level physics challenges written by more than 60 active physics researchers, re-reviewed with expert collaborators to correct underspecified statements, errors and typos. Artificial Analysis evaluates models on it with a code-execution tool in an offline Linux sandbox, so scores are not comparable with the original no-tool CritPt results.',
    'Revised CritPt: 70 research-level physics challenges solved with a sandboxed code-execution tool.',
    'https://artificialanalysis.ai/evaluations/critpt-v2',
    'https://critpt.com/',
    p.id,
    p.title,
    2026,
    'https://paperswithcode.co/paper/2509.26574',
    'judge',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM papers p
WHERE p.arxiv_id = '2509.26574' AND p.is_latest_version
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id)
SELECT t.id, d.id
FROM tasks t, datasets d
WHERE t.slug = 'scientific-reasoning' AND d.slug = 'critpt-v2'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t, datasets d, metrics m
WHERE t.slug = 'scientific-reasoning'
  AND d.slug = 'critpt-v2'
  AND m.name = 'Accuracy'
  AND NOT EXISTS (
      SELECT 1 FROM task_dataset_metrics x
      WHERE x.task_id = t.id AND x.dataset_id = d.id AND x.metric_id = m.id
  );

COMMIT;
