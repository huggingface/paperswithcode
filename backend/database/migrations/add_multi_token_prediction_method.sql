-- Add Multi-Token Prediction (no single introducing paper).
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
    'multi-token-prediction',
    'Multi-Token Prediction',
    'Multi-Token Prediction (MTP)',
    'Multi-token prediction (MTP) trains a language model to predict several future tokens at each position instead of only the next one, typically with extra output heads or modules on a shared [Transformer](/methods/transformer) trunk. The extra targets densify the training signal and the heads can later act as drafters for self-[speculative decoding](/methods/speculative-decoding). Precursors include [Blockwise Parallel Decoding for Deep Autoregressive Models](/paper/1811.03115) and the future n-gram objective of [ProphetNet](/paper/2001.04063). [Better & Faster Large Language Models via Multi-token Prediction](/paper/2404.19737) popularized MTP for LLM pre-training: with n independent heads, its 13B models solved 12% more HumanEval and 17% more MBPP problems than next-token baselines, and 4-token models decoded up to 3 times faster. [DeepSeek-V3](/paper/2412.19437) replaced parallel heads with sequential MTP modules that keep the causal chain, a design adopted by several later open models. Related draft-head methods include [Medusa](/methods/medusa) and [EAGLE](/methods/eagle).',
    'multi-token prediction, multi token prediction',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://docs.nvidia.com/megatron-core/developer-guide/0.15.0/api-guide/multi_token_prediction.html',
    'Multi-Token Prediction (MTP) - Megatron Core developer guide',
    'https://github.com/NVIDIA/Megatron-LM/blob/main/megatron/core/transformer/multi_token_prediction.py',
    NULL,
    '[Better & Faster Large Language Models via Multi-token Prediction](/paper/2404.19737)'
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

-- 60 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE multi_token_prediction_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'multi-token-prediction'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        7955, 12074, 30941, 39076, 41534, 42221, 46887, 47327, 47805, 48640, 48779, 50036,
        50176, 50786, 50969, 51836, 52537, 55117, 55996, 56843, 58114, 58147, 58565, 59560,
        60527, 61136, 61514, 65112, 67258, 68331, 71093, 71913, 71984, 72179, 72820, 82989,
        83310, 83876, 84348, 85645, 87513, 93087, 97940, 98159, 98192, 98431, 99667, 101160,
        102628, 102930, 103005, 104451, 106106, 108655, 109015, 109443, 112163, 113783, 118751, 122895
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM multi_token_prediction_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM multi_token_prediction_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
