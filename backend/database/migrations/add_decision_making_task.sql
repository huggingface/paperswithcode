-- Decision Making: typed decisions over predefined options (decision models,
-- System One models and LLMs constrained to fixed options).
INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Decision Making',
    'decision-making',
    'Decision making evaluates models that answer typed questions about an input instead of generating free-form text: choosing one or several options, assigning a label, picking a tool, scoring against a rubric, or estimating the probability that a statement is true. It covers [decision models](/methods/decision-model) such as [Jev](/methods/jev), which return a schema-valid answer with calibrated probabilities in a single forward pass, as well as language models constrained to fixed options. These decisions power routing, guardrails, [intent detection](/tasks/intent-detection), [reranking](/tasks/text-reranking) and tool selection inside [agents](/tasks/agents), so leaderboards score both accuracy and the quality of the returned probabilities (calibration and Brier score), often alongside latency and cost.',
    'decision model, system one model, system-1 decision model, typed decision, decisions api',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    NULL,
    '[MMDM: Measuring Massive Multitask Decision Making](/paper/2611.14309)',
    'https://artificialanalysis.ai/evaluations/artificial-analysis-decision-index, https://benchmarkheaven.com/jev-models/api, https://huggingface.co/spaces/multimodalart/jev-decision-index'
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

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, v.ord
FROM tasks t
CROSS JOIN (VALUES ('agents', 0), ('intent-detection', 1), ('text-reranking', 2)) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'decision-making'
ON CONFLICT DO NOTHING;
