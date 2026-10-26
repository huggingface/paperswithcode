-- Add DCGAN, introduced in arXiv 1511.06434.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'dcgan',
    'DCGAN',
    'Deep Convolutional Generative Adversarial Network (DCGAN)',
    'DCGAN is a family of architectural guidelines that made [GAN](/methods/gan) training stable with convolutional networks. The generator uses fractionally-strided convolutions to map a noise vector to an image, the discriminator uses strided convolutions, and both drop pooling and fully connected layers in favor of batch normalization, ReLU in the generator and LeakyReLU in the discriminator. Beyond sample quality, the paper showed that the learned features transfer to classification and that the latent space supports vector arithmetic on image attributes, and DCGAN became the default baseline for later image GANs.',
    'DCGAN, DCGANs, deep convolutional generative adversarial network, deep convolutional GAN',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2015,
    (SELECT id FROM papers WHERE arxiv_id = '1511.06434' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Unsupervised Representation Learning with Deep Convolutional Generative Adversarial Networks',
    'https://github.com/pytorch/examples/tree/main/dcgan',
    NULL,
    '[Unsupervised Representation Learning with Deep Convolutional Generative Adversarial Networks](/paper/1511.06434)'
)
ON CONFLICT (slug) DO UPDATE SET
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
WHERE slug = 'dcgan' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'dcgan' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 350 local citers cite the source without naming the method in title or abstract; exclude them so the hourly reference backfill does not link them.
CREATE TEMP TABLE dcgan_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dcgan'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        2041, 2090, 2143, 2156, 2264, 2293, 2301, 2314, 2320, 2322, 2337, 2338,
        2383, 2437, 2518, 2661, 2662, 2706, 2821, 2855, 2861, 2889, 2992, 3085,
        3129, 3132, 3176, 3192, 3194, 3220, 3254, 3278, 3315, 3524, 3566, 3616,
        3692, 3705, 3718, 3755, 3800, 3823, 3848, 3858, 3881, 3960, 4069, 4117,
        4127, 4313, 4354, 4373, 4540, 4608, 4614, 4640, 4712, 4795, 4797, 4802,
        4891, 4898, 4957, 4991, 5022, 5151, 5161, 5199, 5213, 5316, 5347, 5415,
        5417, 5473, 5526, 5546, 5679, 5692, 5846, 5859, 5877, 5892, 5910, 5943,
        5945, 6014, 6078, 6213, 6386, 6815, 6852, 6861, 6916, 7257, 7298, 7314,
        7342, 7344, 7509, 7521, 7578, 7736, 7748, 7791, 7824, 8047, 8212, 8227,
        8532, 8761, 8839, 8961, 9245, 9347, 9367, 9427, 9453, 9538, 9788, 9832,
        9840, 9968, 10137, 10199, 10543, 10576, 11315, 11355, 11443, 11493, 11504, 11509,
        11567, 11760, 11879, 11972, 12245, 12315, 12374, 12392, 12473, 12658, 12680, 13011,
        13171, 13455, 13557, 13607, 13622, 13696, 13907, 13914, 13943, 13963, 14102, 14121,
        14397, 14508, 14761, 14881, 14948, 14967, 16075, 16109, 16295, 16509, 16648, 16945,
        17186, 17492, 17715, 18151, 18164, 18166, 18282, 18397, 18416, 18466, 18694, 18754,
        18788, 18867, 19707, 19940, 19969, 19975, 20539, 20554, 20944, 21220, 21304, 21370,
        22314, 22917, 23484, 23662, 23954, 24357, 24601, 25033, 25445, 25545, 26096, 28359,
        28479, 28856, 29132, 29448, 29450, 30618, 30771, 31214, 31995, 32083, 32321, 32414,
        32469, 32713, 32903, 33344, 33965, 34994, 35004, 36018, 36824, 36894, 37713, 37746,
        39608, 40364, 40586, 43155, 43591, 43641, 44511, 44907, 45276, 45689, 45763, 46538,
        46822, 47107, 48880, 49277, 50084, 50365, 51020, 51334, 51411, 52653, 53648, 54390,
        54732, 56306, 61370, 61911, 65913, 66280, 66300, 67173, 68723, 69614, 69769, 71742,
        72402, 73055, 74413, 75591, 75947, 76744, 77428, 78050, 78281, 78379, 78792, 78968,
        79186, 79368, 79464, 79479, 79516, 79618, 79644, 79710, 79716, 79904, 79989, 80057,
        80244, 80410, 80549, 80669, 80703, 80788, 80856, 80877, 81001, 81002, 81105, 81141,
        81202, 81218, 81224, 81233, 81281, 81351, 81408, 81474, 81663, 86022, 86247, 86424,
        87828, 88048, 88292, 88625, 89171, 89613, 90105, 91982, 92093, 94376, 94614, 94966,
        99987, 100613, 101797, 101999, 102557, 102615, 102639, 103371, 105722, 106327, 106970, 107363,
        108965, 109402, 112587, 113091, 113160, 113245, 113540, 113635, 115707, 116694, 116964, 118542,
        120390, 123933
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'dcgan citation review 2026-10-22: cites the source without naming the method in title or abstract'
FROM dcgan_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING dcgan_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 2 local citers name the method in title or abstract.
CREATE TEMP TABLE dcgan_cited ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dcgan'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        5331, 79375
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dcgan_cited x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM dcgan_cited x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 6 papers match the method keywords (same matcher as the daily keyword backfill).
CREATE TEMP TABLE dcgan_keyword ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dcgan'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        775, 1153, 5331, 61680, 79375, 81991
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dcgan_keyword x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM dcgan_keyword x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
