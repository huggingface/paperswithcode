-- Scientific Reasoning task, and the science leaderboards that sat on
-- Math (FrontierScience), Reasoning (CritPt) and Agents (Terminal-Bench-Science). Each board moves whole (links, metric and
-- every evaluation in one transaction) so the single-board trigger passes.

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Scientific Reasoning',
    'scientific-reasoning',
    'Scientific reasoning evaluates whether AI models can solve expert-level problems in physics, chemistry, biology and other natural sciences, from olympiad-style questions with a single checkable answer to open research problems graded with rubrics and multi-step research workflows carried out by agents in a terminal. Unlike general knowledge tests, these benchmarks need multi-step derivations, quantitative modelling and domain-specific tools, and are written and verified by practising scientists. Related: [Math](/tasks/math), [Reasoning](/tasks/reasoning), [World Knowledge](/tasks/world-knowledge), [Agents](/tasks/agents) and [Auto Research](/tasks/auto-research).',
    'scientific reasoning, science reasoning, expert-level scientific, scientific problem solving, scientific problem-solving, science olympiad, physics olympiad, chemistry olympiad, biology olympiad, physics reasoning, chemistry reasoning, research-level physics, scientific research workflows',
    (SELECT area_id FROM tasks WHERE slug = 'math' LIMIT 1),
    0,
    NULL,
    NULL,
    '[FrontierScience: Evaluating AI''s Ability to Perform Expert-Level Scientific Tasks](/paper/2601.21165)',
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

CREATE TEMP TABLE science_boards (slug text PRIMARY KEY) ON COMMIT DROP;
INSERT INTO science_boards VALUES
    ('frontierscience-olympiad'),
    ('frontierscience-research'),
    ('terminal-bench-science-0-1'),
    ('critpt');

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, bool_or(old.supports_harness)
FROM datasets d
JOIN science_boards b ON b.slug = d.slug
JOIN task_datasets old ON old.dataset_id = d.id
CROSS JOIN tasks t
WHERE t.slug = 'scientific-reasoning'
GROUP BY t.id, d.id
ON CONFLICT (task_id, dataset_id) DO UPDATE
    SET supports_harness = task_datasets.supports_harness OR EXCLUDED.supports_harness;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT DISTINCT t.id, tdm.dataset_id, tdm.metric_id
FROM task_dataset_metrics tdm
JOIN datasets d ON d.id = tdm.dataset_id
JOIN science_boards b ON b.slug = d.slug
CROSS JOIN tasks t
WHERE t.slug = 'scientific-reasoning'
ON CONFLICT DO NOTHING;

UPDATE evaluations e
SET task_id = t.id
FROM datasets d, science_boards b, tasks t
WHERE e.dataset_id = d.id
  AND b.slug = d.slug
  AND t.slug = 'scientific-reasoning'
  AND e.task_id <> t.id;

DELETE FROM task_dataset_metrics tdm
USING datasets d, science_boards b, tasks t
WHERE tdm.dataset_id = d.id
  AND b.slug = d.slug
  AND t.slug = 'scientific-reasoning'
  AND tdm.task_id <> t.id;

DELETE FROM task_datasets td
USING datasets d, science_boards b, tasks t
WHERE td.dataset_id = d.id
  AND b.slug = d.slug
  AND t.slug = 'scientific-reasoning'
  AND td.task_id <> t.id;

-- Tag each benchmark's introducing paper with the new task.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT d.introducing_paper_id, t.id, 'manual'
FROM datasets d
JOIN science_boards b ON b.slug = d.slug
CROSS JOIN tasks t
WHERE t.slug = 'scientific-reasoning'
  AND d.introducing_paper_id IS NOT NULL
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

COMMIT;
