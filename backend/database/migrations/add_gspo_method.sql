-- Add GSPO, introduced in arXiv 2507.18071.
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
    'gspo',
    'GSPO',
    'Group Sequence Policy Optimization (GSPO)',
    'Group Sequence Policy Optimization (GSPO) is a reinforcement learning algorithm for training large language models, proposed by the Qwen team as a more stable alternative to [GRPO](/methods/grpo). Where GRPO and [PPO](/methods/ppo) apply importance ratios and clipping per token, GSPO defines a length-normalized importance ratio from the likelihood of the whole sampled response and performs clipping, rewarding and optimization at the sequence level, matching the unit at which rewards are given. Advantages are still normalized within a group of responses sampled for the same query, so no value model is needed. The authors report that GSPO trains more efficiently and reaches higher performance than GRPO, learns faster despite clipping far more tokens, and stabilizes reinforcement learning of [Mixture-of-Experts](/methods/mixture-of-experts) models without the Routing Replay workaround that GRPO needed. GSPO contributed to the improvements in the latest [Qwen3](/methods/qwen3) models and has been adopted by many later [RLVR](/methods/rlvr) recipes.',
    'GSPO, group sequence policy optimization, group sequence policy optimisation',
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
        WHERE arxiv_id = '2507.18071'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Group Sequence Policy Optimization',
    NULL,
    NULL,
    '[Group Sequence Policy Optimization](/paper/2507.18071)'
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
WHERE slug = 'gspo' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'gspo' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 391 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE gspo_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gspo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        44426, 47412, 48977, 49526, 52093, 52268, 52434, 52463, 52518, 52630, 52631, 52656,
        52676, 52760, 52783, 52785, 52794, 52835, 52840, 52844, 52854, 52888, 52955, 52957,
        52980, 53013, 53035, 53040, 53046, 53054, 53055, 53074, 53105, 53167, 53205, 53231,
        53233, 53272, 53284, 53362, 53370, 53386, 53393, 53452, 53462, 53473, 53551, 53593,
        53598, 53599, 53614, 53660, 53722, 53744, 53745, 53783, 53812, 53931, 53978, 53992,
        54004, 54111, 54112, 54128, 54213, 54249, 54282, 54332, 54452, 54541, 54544, 54578,
        54624, 54707, 54715, 54766, 54823, 54835, 54842, 54962, 55044, 55117, 55118, 55197,
        55231, 55235, 55263, 55267, 55286, 55337, 55469, 55537, 55548, 55554, 55606, 55621,
        55669, 55713, 55718, 55741, 55756, 55831, 55832, 55839, 55854, 55857, 55877, 55883,
        55903, 55912, 55931, 55951, 55968, 55970, 55971, 55979, 55987, 56003, 56007, 56009,
        56054, 56093, 56129, 56133, 56155, 56222, 56223, 56261, 56267, 56301, 56329, 56368,
        56432, 56522, 56602, 56637, 56751, 56816, 56821, 56874, 56886, 56918, 56925, 56937,
        56941, 56953, 57076, 57097, 57099, 57175, 57199, 57244, 57247, 57249, 57276, 57339,
        57469, 57506, 57521, 57552, 57555, 57574, 57630, 57796, 57855, 57858, 58088, 58294,
        58667, 58702, 58723, 58905, 59141, 59147, 59180, 59316, 59328, 59370, 59594, 59634,
        59640, 59784, 60075, 60227, 60427, 60550, 60611, 60731, 60782, 60834, 60973, 61100,
        61109, 61191, 61266, 61319, 61360, 61445, 61470, 61482, 61495, 61552, 61556, 61698,
        61711, 61726, 62028, 62242, 62252, 62879, 63157, 63220, 63394, 63411, 63528, 63704,
        64041, 64049, 64097, 64132, 64204, 64564, 64870, 65114, 65321, 65629, 65739, 65793,
        65817, 65878, 65947, 66056, 66077, 66329, 66449, 66697, 66711, 66721, 66991, 67005,
        67183, 67189, 67196, 67347, 67420, 67534, 67601, 67706, 67712, 67781, 67928, 68012,
        70217, 82877, 82919, 82991, 82996, 83011, 83120, 83151, 83206, 83248, 83252, 83287,
        83288, 83290, 83372, 83378, 83464, 83523, 83582, 83606, 83699, 83811, 83821, 83859,
        84105, 84243, 84335, 84649, 84920, 85101, 85489, 85652, 85672, 85682, 87502, 87528,
        92543, 92975, 93174, 93298, 93316, 93775, 93798, 94048, 94349, 94704, 94758, 94785,
        97964, 98039, 98119, 98150, 98192, 98325, 98329, 98425, 98444, 98518, 98753, 98894,
        99000, 99226, 99559, 99570, 99614, 99622, 99710, 99725, 99751, 99967, 99984, 99999,
        100088, 100101, 100187, 100408, 100573, 100814, 100834, 100873, 101051, 101101, 101232, 101402,
        101525, 102114, 102150, 102347, 102454, 102522, 102526, 102694, 103200, 104007, 104315, 104486,
        105875, 105985, 106169, 106179, 106361, 106387, 107187, 108749, 108873, 108889, 108974, 109155,
        109805, 113852, 114019, 114100, 114216, 114288, 118674, 118735, 119701, 122003, 122085, 122130,
        122131, 122139, 122205, 122246, 122254, 122278, 122347, 122367, 122586, 122651, 122793, 122805,
        122807, 122881, 123137, 123242, 123475, 123569, 123591
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'gspo citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM gspo_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING gspo_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 24 local citers name the method in title or abstract.
CREATE TEMP TABLE gspo_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gspo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        52626, 54357, 55073, 56257, 56463, 61160, 64360, 64625, 65346, 66829, 67012, 67270,
        83312, 94954, 98911, 100134, 102353, 102716, 104310, 104446, 108747, 109492, 119031, 123387
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gspo_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM gspo_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 42 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE gspo_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gspo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        39303, 52611, 52626, 52791, 53831, 54215, 54357, 55073, 55808, 56257, 56463, 59173,
        61160, 61353, 62590, 62738, 64047, 64054, 64360, 64625, 65346, 66829, 67012, 67270,
        67973, 83312, 83746, 85673, 94954, 98911, 100134, 102353, 102716, 104310, 104446, 108747,
        109492, 113967, 114020, 119031, 119577, 123387
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gspo_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM gspo_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
