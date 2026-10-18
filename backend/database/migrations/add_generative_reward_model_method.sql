-- Add Generative Reward Model (no single introducing paper).
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog.

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
    'generative-reward-model',
    'Generative Reward Model',
    'Generative Reward Model (GenRM)',
    'A generative reward model (GenRM) casts reward modeling or verification as text generation: instead of a scalar head trained as a discriminative classifier, a fine-tuned LLM writes its judgment, often after a chain-of-thought critique, and the reward is read from the probability of a token such as ''Yes'' or from a generated preference. This reuses the generation abilities of pretrained LLMs, lets the model reason before judging, and allows extra [test-time compute](/methods/test-time-compute) for verification through majority voting over sampled critiques. The idea appeared concurrently in 2024. [Generative Verifiers](/paper/2408.15240) trained verifiers with next-token prediction jointly on verification and solution generation, improving [Best-of-N](/methods/best-of-n) problem solving by 16-40% over discriminative, DPO and [LLM-as-a-judge](/methods/llm-as-a-judge) verifiers on algorithmic and math tasks. [Generative Reward Models](/paper/2410.12832) iteratively trained an LLM on self-generated reasoning traces to produce preference labels, matching Bradley-Terry [reward models](/methods/reward-model) in distribution and beating them by 10-45% out of distribution. [Critique-out-Loud](/paper/2408.11791) reward models follow a related recipe.',
    'generative reward model, generative reward modeling, GenRM, generative verifier',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2024,
    NULL,
    'https://arxiv.org/abs/2510.01925',
    'Enhancing Large Language Model Reasoning with Reward Models: An Analytical Survey',
    NULL,
    NULL,
    '[Generative Verifiers: Reward Modeling as Next-Token Prediction](/paper/2408.15240)'
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

-- 67 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE generative_reward_model_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'generative-reward-model'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        25714, 36291, 37797, 38637, 40514, 42647, 43715, 45407, 46323, 46917, 47038, 47134,
        47227, 48391, 48509, 48916, 49387, 50291, 51006, 51196, 51608, 51849, 52574, 52973,
        53559, 53629, 53717, 53948, 54565, 55862, 55880, 56073, 56423, 56699, 57113, 57561,
        58146, 59231, 59875, 61082, 61916, 62441, 62621, 62642, 63103, 64933, 65187, 65674,
        65743, 65967, 66308, 67284, 67386, 67993, 68812, 70601, 70823, 71358, 73672, 83686,
        85731, 98243, 103517, 103584, 108874, 114156, 123047
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM generative_reward_model_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM generative_reward_model_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
