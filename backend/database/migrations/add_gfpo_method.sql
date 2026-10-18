-- Add GFPO, introduced in arXiv 2508.09726.
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog. The source paper gets the source evidence row (Introduced banner).

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'gfpo',
    'GFPO',
    'Group Filtered Policy Optimization (GFPO)',
    'Group Filtered Policy Optimization (GFPO) is a reinforcement learning method from Microsoft Research that curbs the response-length inflation typical of [GRPO](/methods/grpo) training with [verifiable rewards](/methods/rlvr). For each problem it samples a larger group of responses than GRPO, ranks them by a target attribute such as response length or token efficiency (reward per token), and keeps only the top-k; advantages are computed over this retained subset and filtered-out responses receive zero advantage. This selective learning acts as implicit reward shaping, teaching the model to think less at inference time by sampling more during training. On [Phi-4-reasoning](/paper/2504.21318), GFPO cuts GRPO''s length inflation by 46-71% on AIME 24/25, GPQA, Omni-MATH and LiveCodeBench while maintaining accuracy, and optimizing reward per token raises the reduction to 71-85%. An Adaptive Difficulty variant gives harder problems more training resources based on real-time difficulty estimates. GFPO trades extra training compute for cheaper [test-time scaling](/methods/test-time-scaling).',
    'GFPO, group filtered policy optimization, group-filtered policy optimization',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2508.09726'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Sample More to Think Less: Group Filtered Policy Optimization for Concise Reasoning',
    NULL,
    NULL,
    '[Sample More to Think Less: Group Filtered Policy Optimization for Concise Reasoning](/paper/2508.09726)'
)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'gfpo' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'gfpo' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 45 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE gfpo_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gfpo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        46489, 46858, 52630, 53055, 53284, 53338, 53590, 55156, 55713, 55986, 56093, 56223,
        56738, 56744, 57002, 58332, 58577, 60022, 60426, 60630, 60632, 60691, 61552, 62239,
        63316, 63523, 65321, 66587, 67420, 67534, 69503, 73526, 82991, 83736, 84105, 92948,
        94631, 94705, 94954, 95036, 98232, 98436, 108754, 108802, 114189
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'gfpo citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM gfpo_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING gfpo_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 1 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE gfpo_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gfpo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        102614
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gfpo_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM gfpo_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
