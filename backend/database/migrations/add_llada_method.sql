-- Add LLaDA, introduced in arXiv 2502.09992.
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
    'llada',
    'LLaDA',
    'Large Language Diffusion with mAsking (LLaDA)',
    'LLaDA (Large Language Diffusion with mAsking) is a family of large language models built on masked [discrete diffusion](/methods/discrete-diffusion) instead of autoregressive next-token prediction. A forward process masks tokens independently with a ratio sampled uniformly between 0 and 1, and a vanilla [Transformer](/methods/transformer) mask predictor, trained by optimizing a likelihood bound, learns the reverse process; generation starts from a fully masked response and iteratively unmasks and remasks tokens. LLaDA 8B was pre-trained from scratch on 2.3 trillion tokens and then supervised fine-tuned on 4.5 million pairs, following the standard LLM recipe. It scaled competitively with self-built autoregressive baselines, was competitive with [LLaMA](/methods/llama) 3 8B on in-context learning, followed instructions after fine-tuning, and addressed the reversal curse, surpassing [GPT-4o](/methods/gpt-4o) on reversal poem completion. Follow-ups include LLaDA 1.5, LLaDA-V and LLaDA-MoE. It uses the masked diffusion objective of [MDLM](/methods/mdlm).',
    'LLaDA, large language diffusion model',
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
        WHERE arxiv_id = '2502.09992'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Large Language Diffusion Models',
    'https://github.com/ML-GSAI/LLaDA',
    NULL,
    '[Large Language Diffusion Models](/paper/2502.09992)'
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
WHERE slug = 'llada' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'llada' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 398 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE llada_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'llada'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        19700, 34113, 38279, 41619, 43564, 43867, 43955, 44169, 44428, 44942, 45765, 46429,
        46975, 47134, 47790, 48077, 48216, 48403, 49029, 49259, 49326, 49333, 49448, 49612,
        49616, 49768, 49819, 49830, 49942, 50078, 50124, 50311, 50414, 50970, 51173, 51405,
        51766, 51838, 51934, 52148, 52185, 52340, 52376, 52448, 52553, 52651, 52818, 52960,
        52987, 53007, 53203, 53206, 53215, 53251, 53267, 53268, 53276, 53278, 53315, 53327,
        53455, 53473, 53557, 53738, 53785, 53800, 53813, 53942, 53967, 54064, 54144, 54219,
        54449, 54532, 54538, 54625, 54664, 54694, 54743, 54751, 54810, 54817, 54832, 54833,
        54846, 54921, 55010, 55015, 55032, 55443, 55448, 55513, 55632, 55723, 55730, 55793,
        55796, 55954, 56064, 56099, 56133, 56141, 56311, 56451, 56522, 56861, 56943, 56964,
        57089, 57102, 57112, 57160, 57234, 57269, 57297, 57303, 57377, 57406, 57422, 57499,
        57725, 57792, 57981, 57985, 58363, 58540, 58633, 58857, 59059, 59128, 59152, 59169,
        59235, 59309, 59473, 59654, 59790, 59932, 59946, 59988, 60034, 60210, 60512, 60598,
        60638, 60755, 60786, 60817, 60903, 60931, 61069, 61132, 61140, 61171, 61183, 61338,
        61432, 61468, 61524, 61529, 61635, 61673, 61732, 61741, 61783, 61820, 61985, 62064,
        62066, 62069, 62337, 63005, 63263, 63311, 63322, 63326, 63330, 63382, 63433, 63701,
        64047, 64055, 64161, 64325, 64464, 64490, 64606, 64809, 64843, 65783, 65828, 65835,
        65934, 66128, 66268, 66361, 66617, 66697, 66721, 66780, 66799, 66864, 66944, 66948,
        67011, 67031, 67088, 67186, 67241, 67258, 67294, 67365, 67398, 67417, 67535, 67564,
        67567, 67761, 67773, 67847, 67870, 67924, 68023, 68891, 69364, 69507, 69550, 69663,
        69714, 70105, 70913, 70930, 70996, 71093, 71400, 71498, 72096, 72723, 73612, 73627,
        75016, 82882, 82915, 82937, 82946, 82971, 82992, 83014, 83125, 83233, 83256, 83380,
        83795, 83801, 83860, 83963, 84088, 84223, 84225, 84289, 84339, 84348, 84633, 85290,
        85332, 85653, 85995, 86070, 86243, 86369, 86447, 87452, 88682, 92593, 92674, 92712,
        92853, 92877, 92960, 93173, 93512, 93758, 93784, 93915, 94095, 94159, 94178, 94198,
        94264, 94312, 94321, 94338, 94379, 94387, 94487, 94587, 94859, 94864, 94879, 94880,
        95021, 95025, 95056, 95101, 97856, 97976, 98288, 98402, 98478, 98493, 98498, 98596,
        98995, 99089, 99351, 99384, 99415, 99431, 99457, 99520, 99577, 99611, 99646, 99666,
        99668, 99675, 99697, 99825, 99827, 99929, 99935, 99938, 100268, 100309, 100317, 100591,
        100592, 100794, 100823, 101096, 101216, 101264, 101341, 101342, 101406, 101454, 101456, 101469,
        101493, 101520, 101580, 101707, 101842, 101890, 101988, 102037, 102158, 102179, 102301, 102365,
        102436, 102627, 102628, 102731, 103200, 104035, 104218, 104434, 105855, 105959, 106053, 106147,
        106179, 106310, 106313, 106350, 106351, 108644, 108694, 108824, 108859, 109280, 109825, 113747,
        114002, 118388, 122135, 122136, 122552, 122557, 122611, 122712, 123003, 123018, 123148, 123419,
        123458, 123534
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'llada citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM llada_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING llada_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 77 local citers name the method in title or abstract.
CREATE TEMP TABLE llada_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'llada'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        48774, 49461, 49705, 49947, 50021, 50845, 51214, 52341, 52551, 52884, 53036, 53059,
        53087, 53547, 53602, 54054, 54690, 55622, 55704, 56356, 56388, 56566, 56581, 57033,
        57284, 57341, 57412, 57663, 58848, 59493, 61914, 61915, 62386, 62610, 62990, 64480,
        65856, 66981, 67391, 67481, 68607, 68902, 69454, 70341, 71175, 83543, 85676, 92595,
        93320, 93839, 94433, 94441, 94559, 94604, 94895, 95005, 98809, 99009, 99176, 99782,
        100125, 100308, 100764, 101231, 101257, 101597, 102152, 102283, 102389, 106210, 106352, 108662,
        114215, 121980, 122721, 122732, 123037
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM llada_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM llada_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 97 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE llada_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'llada'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        27079, 48774, 49461, 49705, 49947, 50021, 50845, 51214, 52194, 52341, 52551, 52884,
        53036, 53059, 53087, 53547, 53602, 54054, 54690, 54864, 55622, 55704, 55766, 55902,
        56356, 56388, 56566, 56581, 57033, 57284, 57341, 57412, 57663, 58848, 59493, 60466,
        61914, 61915, 62386, 62610, 62990, 63662, 64480, 65856, 66865, 66981, 67391, 67481,
        68607, 68902, 69454, 70341, 70769, 71175, 82868, 83543, 85676, 92595, 93320, 93839,
        94433, 94441, 94559, 94604, 94717, 94895, 95005, 98098, 98809, 99009, 99176, 99782,
        100125, 100308, 100764, 100969, 101231, 101257, 101575, 101597, 102152, 102283, 102389, 102583,
        102888, 103681, 106210, 106352, 108662, 113920, 114215, 121980, 122503, 122666, 122721, 122732,
        123037
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM llada_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM llada_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
