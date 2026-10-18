-- Add Best-of-N (no single introducing paper).
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
    'best-of-n',
    'Best-of-N',
    'Best-of-N Sampling (BoN)',
    'Best-of-N (BoN) sampling, also called rejection sampling in RLHF work, is an inference-time method that draws N independent candidate responses from a language model and returns the one scored highest by a [reward model](/methods/reward-model), verifier or other scoring function. It needs no change to the policy and trades extra compute for quality, which makes it the standard baseline for [test-time scaling](/methods/test-time-scaling). Early uses include ranking GSM8K solutions with trained verifiers ([Cobbe et al.](/paper/2110.14168)) and rejection sampling against a human-preference reward model in [WebGPT](/paper/2112.09332). Common variants include weighted Best-of-N, which pools verifier scores over identical final answers, and comparisons against [self-consistency](/methods/self-consistency) voting, beam search and lookahead search guided by [process reward models](/methods/process-reward-model) ([Snell et al.](/paper/2408.03314)). Best-of-N outputs also serve as training data for rejection-sampling fine-tuning and distillation, and optimizing a proxy reward too hard with large N degrades true quality, a form of [reward hacking](/methods/reward-hacking) measured by [Gao et al.](/paper/2210.10760)',
    'best-of-n, best of n, best-of-n sampling, BoN sampling, Best-of-$N$',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://huggingface.co/spaces/HuggingFaceH4/blogpost-scaling-test-time-compute',
    'Scaling test-time compute with open models',
    NULL,
    NULL,
    '[Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters](/paper/2408.03314)'
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

-- 211 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE best_of_n_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'best-of-n'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        8154, 14615, 16080, 19172, 20341, 21378, 22244, 25450, 26129, 26141, 28303, 31200,
        32198, 32402, 33473, 34310, 34639, 34984, 35232, 35604, 36091, 36118, 36291, 37797,
        37823, 37884, 38139, 38397, 38653, 38916, 39034, 39227, 40514, 40912, 40991, 41593,
        41947, 42248, 42444, 42793, 42944, 43114, 43547, 43818, 43959, 44002, 44162, 44184,
        44290, 44602, 44781, 44824, 44939, 45013, 45033, 45081, 45151, 45182, 45232, 45277,
        45552, 45612, 46033, 46186, 46917, 47182, 47221, 47312, 47460, 47633, 47864, 47892,
        48086, 48659, 48888, 48936, 49063, 49086, 49513, 49871, 50416, 50495, 50603, 50653,
        50725, 51025, 51094, 51278, 51300, 51332, 51393, 51476, 51618, 52451, 52484, 53014,
        53112, 53144, 53307, 53379, 53432, 53559, 53675, 53848, 53895, 54107, 54338, 54549,
        54878, 55626, 55704, 56122, 56378, 57313, 57342, 57557, 57738, 57963, 58405, 58640,
        59291, 59796, 59912, 60099, 60854, 61036, 61765, 61856, 61916, 63433, 63936, 64285,
        64483, 65640, 65730, 66247, 66461, 66910, 67944, 68189, 68247, 68327, 68883, 68982,
        69112, 70150, 70823, 70944, 71943, 72377, 73384, 73448, 73598, 74344, 75022, 83447,
        83449, 83615, 83846, 83961, 85720, 86758, 87108, 87496, 88690, 89216, 89863, 93069,
        93140, 93170, 93338, 93416, 93827, 94120, 94425, 94701, 94996, 98014, 98108, 98416,
        98507, 99181, 99847, 100841, 101240, 101689, 101706, 102593, 102714, 102918, 103351, 106167,
        106177, 107086, 107114, 107409, 107484, 108262, 108414, 108749, 110031, 110045, 110127, 110551,
        110833, 118464, 119593, 122455, 123200, 123477, 123622
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM best_of_n_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM best_of_n_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
