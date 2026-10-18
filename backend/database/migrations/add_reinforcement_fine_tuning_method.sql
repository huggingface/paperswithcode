-- Add Reinforcement Fine-Tuning (no single introducing paper).
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
    'reinforcement-fine-tuning',
    'Reinforcement Fine-Tuning',
    'Reinforcement Fine-Tuning (RFT)',
    'Reinforcement fine-tuning adapts a pretrained or instruction-tuned language model to a task by reinforcement learning against a grader, rather than by imitating reference outputs as in supervised [fine-tuning](/methods/fine-tuning). The model samples answers, usually with chain-of-thought reasoning; a programmatic checker or model-based grader scores them; and a policy-gradient algorithm such as [PPO](/methods/ppo) or [GRPO](/methods/grpo) reinforces the high-scoring ones, so the model learns from many self-generated reasoning paths per labelled prompt. The term was popularized by OpenAI, which announced Reinforcement Fine-Tuning for its o-series reasoning models in December 2024 and offers it as an API service with configurable graders. Earlier, [ReFT: Reasoning with Reinforced Fine-Tuning](/paper/2401.08967) warmed up a model with SFT and then ran PPO with rewards derived from ground-truth answers, outperforming SFT on GSM8K, MathQA and SVAMP. Reinforcement fine-tuning is closely related to [RLVR](/methods/rlvr) and should not be confused with [rejection-sampling fine-tuning](/paper/2308.01825), which shares the RFT abbreviation.',
    'reinforcement fine-tuning, reinforcement finetuning, reinforcement fine tuning, reinforced fine-tuning',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2024,
    NULL,
    'https://platform.openai.com/docs/guides/reinforcement-fine-tuning',
    'Reinforcement fine-tuning (OpenAI API documentation)',
    NULL,
    NULL,
    '[ReFT: Reasoning with Reinforced Fine-Tuning](/paper/2401.08967)'
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

-- 171 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE reinforcement_fine_tuning_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'reinforcement-fine-tuning'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        22824, 25913, 35819, 41951, 42041, 42933, 43870, 44552, 45153, 45358, 45754, 45806,
        46463, 46806, 47146, 47372, 47394, 47453, 47514, 47678, 48008, 48067, 48439, 48956,
        49117, 49133, 49146, 49473, 49555, 49624, 49664, 49672, 50111, 50213, 50278, 50381,
        50439, 50578, 50764, 50815, 51172, 51427, 51722, 51731, 51763, 51790, 52433, 52469,
        52600, 52880, 52893, 52978, 53042, 53043, 53099, 53605, 53994, 54240, 54333, 54337,
        54442, 54474, 54580, 54796, 55588, 55645, 55857, 56166, 56549, 56805, 57675, 57954,
        57993, 58296, 58804, 59385, 59668, 60127, 60277, 60445, 60857, 61219, 61325, 62292,
        62352, 63357, 63447, 63669, 64034, 64399, 64471, 64790, 65534, 65629, 65740, 65787,
        65795, 66082, 66104, 66554, 66731, 67419, 67828, 69107, 69525, 69565, 70121, 70495,
        70619, 70986, 71470, 71517, 72062, 72240, 72595, 72989, 73311, 73650, 74988, 83464,
        84102, 84164, 84286, 84516, 84722, 84920, 85154, 86282, 86846, 92153, 93578, 94100,
        94704, 94770, 94826, 94896, 96210, 96823, 98014, 98089, 98820, 99522, 99869, 100070,
        100187, 100472, 101232, 101445, 102305, 103157, 103187, 103584, 103957, 107074, 107139, 107540,
        107602, 108210, 108837, 108889, 109644, 113811, 114255, 114278, 117978, 118278, 118637, 120667,
        120770, 121625, 121660
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM reinforcement_fine_tuning_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM reinforcement_fine_tuning_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
