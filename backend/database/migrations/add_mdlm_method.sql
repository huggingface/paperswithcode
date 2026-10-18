-- Add MDLM, introduced in arXiv 2406.07524.
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
    'mdlm',
    'MDLM',
    'Masked Diffusion Language Model (MDLM)',
    'MDLM (Masked Diffusion Language Model) is a [discrete diffusion](/methods/discrete-diffusion) approach to language modeling in which a forward process progressively replaces tokens with a mask token and a bidirectional [Transformer](/methods/transformer) learns to reverse it. Sahoo et al. pair a modern training recipe with a simplified, Rao-Blackwellized continuous-time variational objective that reduces to a weighted mixture of classical masked language modeling losses, so encoder-only, [BERT](/methods/bert)-style networks can be trained as proper generative models. MDLM supports efficient ancestral samplers, including semi-autoregressive generation of arbitrary-length text. Building on the absorbing-state D3PM of [Structured Denoising Diffusion Models in Discrete State-Spaces](/paper/2107.03006), it set a new state of the art among diffusion language models and approached autoregressive perplexity within 15-25% on LM1B and OpenWebText. Its objective underlies later large-scale masked diffusion language models such as [LLaDA](/methods/llada).',
    'MDLM, masked diffusion language model',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2024,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2406.07524'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Simple and Effective Masked Diffusion Language Models',
    'https://github.com/kuleshov-group/mdlm',
    NULL,
    '[Simple and Effective Masked Diffusion Language Models](/paper/2406.07524)'
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
WHERE slug = 'mdlm' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'mdlm' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 414 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE mdlm_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mdlm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        19700, 31818, 32457, 35724, 35872, 36459, 36588, 38111, 38279, 38720, 38782, 39054,
        39106, 39271, 40814, 41258, 41319, 41531, 41619, 42337, 42717, 43564, 43578, 43955,
        43982, 44010, 44190, 44347, 45123, 45248, 45297, 45434, 45544, 45649, 45765, 45769,
        45849, 45862, 45981, 46001, 46554, 46816, 47790, 48077, 48216, 48559, 48618, 49029,
        49178, 49251, 49259, 49326, 49448, 49461, 49612, 49616, 49705, 49819, 49942, 49947,
        50021, 50124, 50311, 50395, 50414, 50970, 51034, 51173, 51197, 51214, 51326, 51471,
        51476, 51498, 51766, 51838, 51934, 52185, 52340, 52376, 52551, 52760, 52884, 52987,
        53059, 53087, 53203, 53206, 53215, 53269, 53276, 53278, 53315, 53384, 53557, 53602,
        53738, 53785, 53800, 53813, 54064, 54144, 54664, 54694, 54743, 54810, 54817, 55010,
        55065, 55228, 55443, 55448, 55513, 55622, 55632, 55704, 55796, 56064, 56133, 56141,
        56233, 56251, 56283, 56298, 56356, 56388, 56522, 56566, 56769, 56843, 56905, 56943,
        56952, 56964, 57033, 57089, 57112, 57269, 57284, 57297, 57303, 57341, 57377, 57406,
        57412, 57499, 57663, 57725, 57792, 57981, 58363, 58633, 58848, 58857, 58904, 59128,
        59152, 59473, 59493, 59654, 59946, 59988, 60019, 60034, 60210, 60348, 60466, 60786,
        61049, 61132, 61140, 61432, 61468, 61529, 61596, 61673, 61702, 61732, 61756, 61783,
        61789, 61808, 61914, 61915, 62064, 62066, 62337, 62386, 62610, 62990, 63005, 63096,
        63326, 63662, 64161, 64287, 64325, 64480, 64490, 65535, 65783, 65835, 65856, 65934,
        66268, 66617, 66697, 66721, 66864, 66944, 67011, 67031, 67088, 67251, 67258, 67296,
        67365, 67391, 67398, 67417, 67535, 67598, 67761, 67773, 67847, 67870, 67883, 67924,
        68419, 68607, 68891, 68902, 69259, 69364, 69541, 69663, 70105, 70341, 70769, 70913,
        70996, 71096, 71265, 71498, 72096, 72469, 72620, 72723, 74129, 74318, 74563, 75016,
        75983, 82915, 82937, 82992, 83014, 83380, 83514, 83801, 83860, 83963, 84633, 85290,
        85653, 85676, 85740, 85995, 86364, 86369, 86447, 86624, 86684, 86865, 86920, 87161,
        88649, 88682, 89099, 89375, 89740, 89803, 91260, 91456, 91480, 91765, 91850, 92252,
        92593, 92674, 92853, 92877, 92886, 92911, 92960, 93008, 93320, 93512, 93758, 93784,
        93839, 93891, 93985, 94023, 94118, 94159, 94178, 94200, 94296, 94321, 94379, 94441,
        94487, 94587, 94604, 94879, 94880, 94895, 95005, 95025, 95056, 97976, 98288, 98402,
        98812, 98950, 99009, 99089, 99132, 99351, 99384, 99431, 99516, 99520, 99611, 99646,
        99675, 99782, 99935, 99938, 100042, 100044, 100125, 100184, 100268, 100308, 100317, 100364,
        100588, 100794, 100836, 101033, 101194, 101216, 101231, 101257, 101264, 101342, 101454, 101456,
        101493, 101520, 101580, 101597, 101707, 101769, 101890, 102037, 102152, 102155, 102158, 102179,
        102221, 102283, 102628, 102731, 104035, 104218, 104589, 105855, 105949, 105959, 106053, 106147,
        106310, 106313, 106350, 106351, 107143, 108644, 108662, 108694, 108824, 108859, 109112, 109685,
        109825, 110234, 110981, 114002, 114095, 114154, 118551, 118631, 120771, 122136, 122552, 122557,
        122611, 122712, 122732, 123018, 123148, 123419
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'mdlm citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM mdlm_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING mdlm_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 37 local citers name the method in title or abstract.
CREATE TEMP TABLE mdlm_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mdlm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        42117, 49830, 51405, 53036, 53473, 54532, 55723, 55793, 57422, 58540, 58856, 60598,
        60826, 63322, 63603, 64809, 65828, 67481, 68698, 69507, 72753, 73627, 92595, 93173,
        94095, 94198, 98809, 99176, 99929, 100764, 101406, 104434, 105859, 106179, 106352, 121980,
        122721
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mdlm_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM mdlm_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 48 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE mdlm_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mdlm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        42117, 48774, 49830, 51405, 53036, 53473, 53748, 54532, 55723, 55793, 56815, 57062,
        57422, 58540, 58856, 60598, 60826, 63322, 63603, 64809, 65828, 67481, 68698, 69507,
        72753, 73627, 92595, 93173, 93364, 94095, 94198, 94387, 98413, 98809, 99176, 99929,
        100764, 101406, 102389, 104434, 105859, 106179, 106352, 109720, 121980, 122503, 122666, 122721
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mdlm_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM mdlm_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
