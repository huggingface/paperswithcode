-- Feedback issue huggingface/paperswithcode-feedback#56 on Attention Is All
-- You Need (1706.03762).
--
-- 1. The paper's 92.7 F1 on Penn Treebank WSJ Section 23 is a constituency
--    parsing result, but its leaderboard sat on Classic Language Modeling,
--    whose boards measure perplexity. Add a Constituency Parsing task and move
--    the board there. Leaderboards are keyed by (task, dataset), so the task
--    link, the leaderboard metric, the evaluation rows and the badge
--    tombstones all move together.
-- 2. The WMT 2014 newstest2014 sets come from the WMT 2014 shared task, not
--    from the Transformer paper, which only evaluates on them.
-- 3. The Transformer paper does not describe KV caching, and no single paper
--    introduced it. As its source, the paper also made the citation backfill
--    tag thousands of its citers with the method, so drop those links unless
--    the paper itself mentions KV caching.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id, image_credit
)
VALUES (
    'Constituency Parsing',
    'constituency-parsing',
    'Constituency parsing recovers the phrase-structure tree of a sentence: nested constituents such as noun phrases (NP) and verb phrases (VP) built over the words and their [part-of-speech tags](/tasks/part-of-speech-tagging). Parsers are scored by labeled bracketing F1 (EVALB), most often on Section 23 of the Penn Treebank Wall Street Journal corpus. Neural parsers either score spans with a chart decoder ([Kitaev & Klein](/paper/1805.01052)) or treat parsing as sequence-to-sequence generation of a linearized tree ([Vinyals et al.](/paper/1412.7449)).',
    'constituency parsing, constituency parser, constituent parsing, phrase-structure parsing, phrase structure parsing, phrase-structure trees, constituency trees, constituency tree, constituent tree, bracketing F1, EVALB',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    0,
    NULL,
    '[Constituency Parsing with a Self-Attentive Encoder](/paper/1805.01052)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

CREATE TEMP TABLE benchmark_task_moves ON COMMIT DROP AS
SELECT d.id AS dataset_id, old_t.id AS old_task_id, new_t.id AS new_task_id, new_t.slug AS new_task_slug
FROM datasets d
JOIN tasks old_t ON old_t.slug = 'classic-language-modeling'
JOIN tasks new_t ON new_t.slug = 'constituency-parsing'
WHERE d.slug = 'penn-treebank-wsj-section-23';

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

-- Papers with a result on the moved leaderboard, and the two parsers the
-- description cites, belong to the new task.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT e.paper_id, m.new_task_id, 'manual'
FROM evaluations e
JOIN benchmark_task_moves m ON m.dataset_id = e.dataset_id AND m.new_task_id = e.task_id
ON CONFLICT DO NOTHING;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'constituency-parsing'
WHERE p.arxiv_id IN ('1805.01052', '1412.7449') AND p.is_latest_version
ON CONFLICT DO NOTHING;

UPDATE datasets
SET introducing_paper_id = NULL,
    introducing_paper_title = 'Findings of the 2014 Workshop on Statistical Machine Translation',
    paper_url = 'https://aclanthology.org/W14-3302/',
    introduced_year = 2014,
    updated_at = now()
WHERE slug IN ('wmt-2014-english-french-newstest2014', 'wmt-2014-english-german-newstest2014');

UPDATE methods
SET source_paper_id = NULL,
    source_title = 'KV cache strategies (Hugging Face Transformers documentation)',
    source_url = 'https://huggingface.co/docs/transformers/en/kv_cache',
    introduced_year = NULL,
    updated_at = now()
WHERE slug = 'key-value-cache';

-- Links backed only by the old source row or by citing the Transformer paper
-- (the legacy links came from the same citation fan-out), whose title and
-- abstract never mention KV caching.
CREATE TEMP TABLE kv_cache_citer_links ON COMMIT DROP AS
SELECT pm.paper_id, pm.method_id
FROM paper_methods pm
JOIN methods m ON m.id = pm.method_id AND m.slug = 'key-value-cache'
JOIN papers p ON p.id = pm.paper_id
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_evidence e
    WHERE e.paper_id = pm.paper_id AND e.method_id = pm.method_id
      AND e.evidence_type NOT IN ('source', 'reference', 'legacy_unknown')
)
AND concat_ws(' ', p.title, p.abstract) !~* '(kv[- ]?cach|key[- ]value cach|key[- ]value (store|memor)|incremental decoding)';

DELETE FROM paper_method_evidence e
USING methods m
WHERE e.method_id = m.id AND m.slug = 'key-value-cache'
  AND e.evidence_type IN ('source', 'reference');

DELETE FROM paper_method_evidence e
USING kv_cache_citer_links l
WHERE e.paper_id = l.paper_id AND e.method_id = l.method_id;

DELETE FROM paper_methods pm
USING kv_cache_citer_links l
WHERE pm.paper_id = l.paper_id AND pm.method_id = l.method_id;
