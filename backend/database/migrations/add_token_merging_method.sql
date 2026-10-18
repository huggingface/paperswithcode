-- Add Token Merging, introduced in arXiv 2210.09461.
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
    'token-merging',
    'Token Merging',
    'Token Merging (ToMe)',
    'Token Merging (ToMe) speeds up existing [Vision Transformer](/methods/vision-transformer) models without retraining by gradually combining similar tokens inside each transformer block. Between the attention and MLP layers, a lightweight bipartite soft matching step splits tokens into two sets, connects each token to its most similar token in the other set, and merges the r most similar pairs, so the sequence shrinks layer by layer. Matching is as fast as token pruning but more accurate, since information is merged rather than discarded. Off the shelf, ToMe doubles the throughput of state-of-the-art ViT-L @ 512 and ViT-H @ 518 models on images and gives 2.2x throughput for ViT-L on video with only a 0.2-0.3% accuracy drop; applied during training it speeds up [MAE](/methods/masked-autoencoder) fine-tuning on video by up to 2x. [ToMe for Stable Diffusion](/paper/2303.17604) carried the idea to diffusion models, and token merging is now a standard tool for token reduction in vision-language and video models.',
    'ToMe, token merging',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2022,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2210.09461'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Token Merging: Your ViT But Faster',
    'https://github.com/facebookresearch/ToMe',
    NULL,
    '[Token Merging: Your ViT But Faster](/paper/2210.09461)'
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
WHERE slug = 'token-merging' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'token-merging' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 467 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE token_merging_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'token-merging'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        10525, 11545, 12447, 14317, 14533, 14599, 14632, 15243, 15672, 15767, 16279, 16409,
        16410, 16417, 16469, 17137, 17258, 17526, 17753, 18024, 18199, 18785, 19057, 19066,
        19381, 19400, 19796, 20067, 20219, 21237, 21295, 21399, 21429, 21641, 21744, 21845,
        22077, 22078, 22727, 22994, 23040, 23283, 23470, 23570, 24018, 24122, 24212, 24772,
        24867, 25307, 25343, 25831, 26531, 26776, 27329, 27723, 27774, 28034, 28506, 28512,
        28694, 28837, 28879, 28901, 29038, 29792, 30086, 30098, 30347, 30410, 31149, 31719,
        31737, 31821, 31853, 32004, 32164, 32522, 32610, 32742, 32815, 33298, 33717, 33753,
        34041, 34046, 34296, 34397, 34487, 34752, 34870, 34971, 35152, 35299, 35719, 36304,
        36407, 36423, 36465, 36491, 36535, 36732, 37190, 37444, 37951, 38216, 38557, 38831,
        38946, 39018, 39029, 39606, 39616, 39662, 39779, 39879, 40310, 40336, 40357, 40517,
        40538, 40550, 40572, 40698, 40713, 40727, 40800, 40858, 40977, 41085, 41205, 41265,
        41314, 41389, 41464, 41639, 41647, 41782, 41831, 42334, 42361, 42474, 42534, 42579,
        42659, 43074, 43152, 43251, 43363, 43519, 43638, 44339, 45152, 45542, 45694, 45778,
        45860, 45957, 46098, 46129, 46158, 46195, 46320, 46414, 46473, 46495, 46686, 46748,
        46889, 46984, 47008, 47225, 47231, 47325, 47794, 48057, 48063, 48091, 48127, 48190,
        48647, 48953, 49593, 49648, 49691, 49747, 49894, 50125, 50325, 50361, 50362, 50471,
        51068, 51137, 51542, 51820, 51840, 52057, 52077, 52140, 52517, 53535, 53773, 53852,
        54046, 54247, 54288, 54379, 54435, 54459, 54464, 54520, 54633, 54688, 55276, 55297,
        55512, 56089, 56090, 56138, 56270, 56360, 56452, 56516, 56552, 56649, 56803, 56966,
        56975, 57040, 57076, 57130, 57164, 57355, 58030, 58209, 58343, 58478, 58535, 58879,
        59599, 59683, 59755, 60021, 60120, 60400, 60430, 60451, 60486, 60511, 60654, 60726,
        61025, 61042, 61161, 61362, 61476, 61700, 61894, 61945, 61997, 62073, 63385, 63610,
        63746, 63854, 63977, 64007, 64703, 64843, 66037, 66148, 66780, 67043, 67192, 67442,
        67521, 67538, 67820, 68020, 68311, 68635, 68776, 68887, 68907, 69217, 69268, 69340,
        69622, 69717, 69999, 70176, 70414, 71035, 71129, 71558, 71686, 71757, 71942, 72407,
        72613, 72840, 72928, 73184, 73374, 73558, 74090, 74152, 74272, 74397, 74523, 74552,
        75003, 75208, 76037, 76645, 77402, 78971, 82982, 83375, 83604, 83727, 83921, 84094,
        84108, 84132, 84253, 84316, 84321, 84333, 84366, 84461, 84673, 84789, 84921, 85000,
        85034, 85042, 85049, 85303, 85314, 85338, 85357, 85367, 85380, 85405, 85537, 85557,
        85575, 85788, 86023, 86251, 86331, 86829, 87039, 87123, 87587, 87735, 87757, 87839,
        87943, 88234, 88250, 88303, 88454, 88493, 89068, 90107, 90317, 90435, 91824, 92065,
        92140, 93234, 93690, 94027, 94308, 94457, 94467, 94562, 94654, 94679, 94780, 94802,
        95865, 96211, 97518, 97643, 98146, 98217, 98954, 99106, 99233, 99341, 99608, 102344,
        102607, 103288, 104737, 104743, 105976, 106131, 106771, 107106, 107518, 108264, 108267, 108270,
        108500, 108647, 108958, 109460, 110210, 110268, 110710, 112433, 112551, 112593, 112650, 113363,
        113375, 113607, 113822, 114038, 114085, 116281, 116359, 116465, 116618, 116659, 116870, 117106,
        117133, 117433, 117665, 117729, 117748, 117821, 118207, 118362, 118445, 118543, 118556, 118609,
        118661, 118665, 118732, 119253, 119342, 119359, 119397, 119478, 119530, 119577, 119602, 119703,
        119929, 120224, 120669, 120970, 121759, 121935, 122284, 122695, 122941, 123003, 123510
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'token-merging citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM token_merging_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING token_merging_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 60 local citers name the method in title or abstract.
CREATE TEMP TABLE token_merging_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'token-merging'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        14319, 17835, 18460, 22983, 24894, 25689, 29179, 29927, 30773, 31586, 31742, 32841,
        33982, 36490, 37030, 37834, 39434, 40349, 40452, 40825, 40966, 41515, 43775, 46531,
        47132, 48096, 49938, 50029, 50618, 51826, 53482, 54306, 56839, 58455, 61017, 61571,
        61716, 64103, 64352, 65292, 65827, 66395, 67112, 68807, 70714, 71758, 76712, 78431,
        84263, 84873, 87120, 88179, 89621, 90636, 90676, 94743, 102440, 107509, 116533, 122940
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM token_merging_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM token_merging_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 88 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE token_merging_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'token-merging'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        5808, 14319, 17835, 18460, 19196, 22983, 24894, 25689, 29179, 29927, 30773, 31586,
        31742, 32841, 33982, 36490, 37030, 37834, 38631, 39255, 39434, 40349, 40452, 40584,
        40825, 40966, 41515, 43775, 46531, 46627, 47132, 48096, 49938, 50029, 50618, 51058,
        51826, 53482, 54306, 56839, 58455, 61017, 61051, 61466, 61571, 61716, 64103, 64352,
        64865, 65031, 65292, 65827, 66395, 67112, 68807, 70714, 71001, 71758, 76712, 78431,
        84176, 84263, 84640, 84873, 87120, 88179, 89621, 90636, 90676, 94743, 96772, 99604,
        100791, 102440, 102584, 105347, 105573, 107509, 108008, 113976, 116533, 119531, 120032, 120809,
        120940, 121334, 121688, 122940
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM token_merging_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM token_merging_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
