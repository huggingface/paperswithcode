-- Add Sparse Autoencoder (no single introducing paper).
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
    'sparse-autoencoder',
    'Sparse Autoencoder',
    'Sparse Autoencoder (SAE)',
    'A sparse autoencoder (SAE) is an [autoencoder](/methods/autoencoder-ae) trained to reconstruct its input through an overcomplete hidden layer while a sparsity penalty (an L1 term, or a TopK or JumpReLU activation) keeps only a few latents active per input. The idea is decades old in unsupervised feature learning, but SAEs became a central tool of mechanistic interpretability when they were applied to the internal activations of language models. There they decompose polysemantic neurons, which fire in many unrelated contexts, into a dictionary of sparsely active, more monosemantic features. [Sparse Autoencoders Find Highly Interpretable Features in Language Models](/paper/2309.08600) and Anthropic''s Towards Monosemanticity (2023) established the approach, and [Scaling and evaluating sparse autoencoders](/paper/2406.04093) and [Gemma Scope](/paper/2408.05147) scaled it to frontier-size models. SAE features are used for circuit analysis, model steering alongside [representation engineering](/methods/representation-engineering), [probing](/methods/probing), unlearning and data selection.',
    'sparse autoencoder, sparse auto-encoder',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://arxiv.org/abs/2503.05613',
    'A Survey on Sparse Autoencoders: Interpreting the Internal Mechanisms of Large Language Models',
    'https://github.com/decoderesearch/SAELens',
    NULL,
    '[Sparse Autoencoders Find Highly Interpretable Features in Language Models](/paper/2309.08600)'
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

-- 348 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE sparse_autoencoder_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'sparse-autoencoder'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        66, 2604, 2955, 12379, 20491, 31280, 31451, 31459, 31538, 31632, 32414, 32417,
        33124, 33186, 33684, 34970, 34975, 35406, 35439, 35705, 36646, 37184, 38160, 38221,
        38482, 38511, 38536, 38604, 38769, 38823, 38914, 39170, 39196, 39241, 39309, 39351,
        39522, 39558, 39591, 39594, 39831, 39915, 39970, 40046, 40102, 40256, 40306, 40453,
        41040, 41161, 41228, 41469, 41665, 42008, 42101, 42727, 42733, 42782, 42999, 43283,
        43321, 43352, 43393, 43394, 43441, 43457, 43692, 43781, 43951, 44096, 44141, 44278,
        44317, 44321, 44484, 44615, 45195, 45493, 45753, 45820, 45968, 45976, 46217, 46354,
        46410, 46568, 46665, 47255, 47504, 47538, 47928, 48185, 48240, 48445, 48770, 49124,
        49160, 49191, 49303, 49363, 49377, 49424, 49551, 49737, 49807, 49841, 49870, 50007,
        50508, 50961, 51039, 51189, 51342, 51423, 51780, 51949, 52399, 52425, 52698, 53125,
        53141, 53192, 53245, 53909, 54295, 54347, 54749, 55052, 55380, 55405, 55586, 55691,
        55856, 55894, 55985, 56085, 56107, 56153, 56635, 56938, 57210, 57760, 58283, 58469,
        58543, 58847, 58958, 59462, 59925, 59952, 60163, 60334, 60538, 60613, 60642, 60808,
        60858, 60984, 61072, 61583, 61942, 61950, 61999, 62562, 62587, 62934, 63449, 63691,
        63825, 63918, 63968, 64251, 64719, 65636, 65780, 66124, 66193, 66681, 66682, 67185,
        67244, 67472, 67632, 67652, 67835, 67875, 68758, 68931, 69182, 69264, 69293, 69398,
        69631, 69811, 70634, 70766, 70937, 70943, 71036, 71064, 71739, 71752, 71982, 72127,
        72151, 72318, 72512, 72516, 72562, 73234, 73754, 73795, 74142, 74224, 74474, 74510,
        74525, 74584, 74854, 74877, 74908, 74980, 75574, 82948, 83298, 83863, 84652, 85323,
        85384, 85465, 85601, 85741, 85960, 85992, 86350, 86438, 86456, 87074, 87106, 88768,
        89057, 89102, 89551, 89654, 89745, 91910, 91925, 92105, 92634, 92756, 92870, 92925,
        92942, 93023, 93229, 93464, 93515, 93594, 93695, 93737, 93783, 93923, 93942, 94055,
        94111, 94164, 95533, 98011, 98064, 98151, 98181, 98446, 98505, 99250, 99278, 99288,
        99368, 99575, 99642, 99737, 99948, 100406, 100803, 100920, 101006, 101067, 101070, 101187,
        101469, 101788, 101886, 101901, 101919, 101968, 102084, 102143, 102306, 102379, 102399, 102415,
        102617, 102814, 102837, 102861, 103096, 103189, 103383, 103460, 103520, 105570, 106103, 106183,
        106217, 106236, 106268, 106854, 106864, 106996, 107410, 107541, 107859, 108553, 108704, 108806,
        109289, 109991, 110135, 110275, 110460, 110525, 110805, 110807, 110865, 110900, 111063, 113733,
        114079, 114156, 117440, 118421, 119081, 119085, 119115, 120700, 122207, 122546, 123625, 123627
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM sparse_autoencoder_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM sparse_autoencoder_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
