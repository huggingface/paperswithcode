-- Add Rubrics as Rewards, introduced in arXiv 2507.17746.
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
    'rubrics-as-rewards',
    'Rubrics as Rewards',
    'Rubrics as Rewards (RaR)',
    'Rubrics as Rewards (RaR) is a reinforcement learning framework that extends [RLVR](/methods/rlvr) to domains without a single verifiable answer, such as medicine and science, by turning structured, checklist-style rubrics into reward signals. For each prompt, a strong LLM guided by expert reference answers synthesizes self-contained rubric criteria labelled Essential, Important, Optional or Pitfall. During on-policy training with [GRPO](/methods/grpo), an [LLM judge](/methods/llm-as-a-judge) scores each rollout against the rubric, and the criteria are aggregated into a scalar reward either explicitly, as a normalized weighted sum of per-criterion checks, or implicitly, by passing all criteria to the judge for a holistic score. Unlike opaque preference-trained [reward models](/methods/reward-model), rubric rewards are interpretable and less prone to spurious correlations. The best RaR variant yields up to a 28% relative improvement on HealthBench-1k over Likert-based judging and matches or surpasses rewards derived from expert-written references, while helping smaller judge models align with human preferences. Rubric-based rewards have since become a common recipe for RL on open-ended tasks.',
    'rubrics as rewards, rubrics-as-rewards, rubric as reward, rubric-based reward, rubric reward, rubric-based reinforcement learning, rubric-based rl',
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
        WHERE arxiv_id = '2507.17746'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Rubrics as Rewards: Reinforcement Learning Beyond Verifiable Domains',
    NULL,
    NULL,
    '[Rubrics as Rewards: Reinforcement Learning Beyond Verifiable Domains](/paper/2507.17746)'
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
WHERE slug = 'rubrics-as-rewards' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'rubrics-as-rewards' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 146 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE rubrics_as_rewards_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rubrics-as-rewards'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        47288, 48391, 49810, 51144, 52075, 52228, 52390, 52484, 52960, 53097, 53491, 53566,
        53660, 53692, 53698, 53704, 53766, 53788, 54180, 54634, 54806, 54903, 54951, 55120,
        55143, 55212, 55226, 55354, 55474, 55718, 55777, 55854, 55918, 56008, 56074, 56094,
        56174, 56221, 56334, 56381, 56404, 56412, 56423, 56476, 56604, 56632, 56660, 56666,
        57548, 57668, 57813, 57862, 59069, 59231, 59267, 59328, 59435, 59600, 59794, 60290,
        60435, 60525, 60571, 60648, 60749, 60782, 60833, 61041, 61219, 61426, 61458, 62037,
        62239, 62642, 63157, 64793, 64968, 64997, 65110, 65425, 65516, 65743, 66308, 66425,
        66506, 66781, 68247, 82953, 82998, 83132, 83243, 83246, 83426, 83537, 83612, 83684,
        84105, 85655, 95111, 97949, 98039, 98753, 98834, 98896, 98997, 99053, 100259, 100371,
        100529, 100812, 101500, 101601, 102144, 102925, 103003, 103482, 103517, 103583, 103753, 104465,
        104596, 105931, 106015, 106061, 106086, 106100, 106226, 108763, 109770, 113795, 113870, 118464,
        121953, 122085, 122114, 122163, 122168, 122334, 122708, 122801, 122805, 123139, 123277, 123279,
        123448, 123596
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'rubrics-as-rewards citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM rubrics_as_rewards_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING rubrics_as_rewards_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 32 local citers name the method in title or abstract.
CREATE TEMP TABLE rubrics_as_rewards_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rubrics-as-rewards'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        52404, 52978, 53394, 55193, 55690, 58199, 58495, 64054, 66751, 68162, 83270, 83477,
        83941, 92533, 102674, 104388, 105884, 106022, 108967, 109719, 109762, 113916, 114158, 118401,
        121974, 122133, 122542, 122651, 122845, 122969, 123248, 123264
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rubrics_as_rewards_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM rubrics_as_rewards_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 47 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE rubrics_as_rewards_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rubrics-as-rewards'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        52404, 52978, 53394, 55016, 55193, 55690, 58199, 58495, 58577, 59110, 59710, 59871,
        59983, 61734, 64054, 64303, 65465, 66751, 68162, 82977, 83270, 83477, 83941, 84779,
        85648, 92533, 104388, 105884, 106022, 108967, 109719, 109762, 113916, 114069, 114158, 118401,
        121974, 122133, 122332, 122542, 122651, 122656, 122845, 122961, 122969, 123248, 123264
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rubrics_as_rewards_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM rubrics_as_rewards_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
