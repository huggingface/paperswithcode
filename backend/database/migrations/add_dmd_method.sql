-- Add DMD, introduced in arXiv 2311.18828.
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
    'dmd',
    'DMD',
    'Distribution Matching Distillation (DMD)',
    'Distribution Matching Distillation (DMD) turns a pretrained [diffusion](/methods/diffusion) model into a one-step image generator. Instead of regressing the teacher''s sampling trajectories, it matches the generator to the teacher at the distribution level by minimizing an approximate KL divergence whose gradient is the difference between two score functions: a frozen "real" score from the teacher and a "fake" score from a second diffusion model trained online on the generator''s samples. The original method adds a regression loss on noise-image pairs precomputed with the teacher, and reached 2.62 FID on ImageNet 64×64 and 11.49 FID on zero-shot COCO-30k, close to [Stable Diffusion](/methods/stable-diffusion) at 20 FPS. The follow-up [DMD2](/paper/2405.14867) removes the regression loss with a two time-scale update rule, adds a [GAN](/methods/gan) loss on real images and supports multi-step sampling, reaching 1.28 FID on ImageNet-64×64. DMD-style losses are now a standard tool for few-step image and video generation, used alongside [Consistency Models](/methods/consistency-models) and in [Self Forcing](/methods/self-forcing).',
    'distribution matching distillation, DMD2',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2311.18828'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'One-step Diffusion with Distribution Matching Distillation',
    'https://github.com/tianweiy/DMD2',
    NULL,
    '[One-step Diffusion with Distribution Matching Distillation](/paper/2311.18828)'
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
WHERE slug = 'dmd' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'dmd' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 617 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE dmd_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dmd'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        11179, 20332, 23869, 25012, 27067, 27751, 28326, 28514, 28528, 28670, 29060, 29072,
        29113, 29132, 29417, 29746, 29989, 30539, 30585, 30623, 30631, 30669, 30930, 31231,
        31297, 31527, 31691, 31719, 31806, 32090, 32093, 32295, 32447, 32454, 32550, 32572,
        32671, 33413, 34397, 34835, 35085, 35448, 35877, 36230, 36268, 36338, 36501, 36866,
        36913, 36985, 37002, 37326, 37353, 37401, 37493, 37535, 37677, 37854, 38202, 38451,
        38501, 38504, 38615, 38985, 38989, 39174, 39404, 39492, 39619, 39763, 39764, 39867,
        39981, 40208, 40490, 40529, 40539, 40552, 40586, 40733, 40859, 40875, 40920, 40985,
        41051, 41087, 41205, 41421, 41462, 41489, 41562, 41717, 41983, 42064, 42435, 42674,
        42843, 43112, 43122, 43260, 43446, 43562, 43569, 43603, 43622, 43797, 43852, 43911,
        44181, 44778, 44896, 44997, 45355, 45471, 45574, 45648, 45714, 45717, 45765, 45802,
        45805, 45813, 45822, 45839, 45956, 45990, 46009, 46083, 46197, 46239, 46258, 46321,
        46473, 46483, 46553, 46709, 46787, 46865, 46915, 47092, 47265, 47385, 47602, 47746,
        47827, 47854, 48677, 48784, 48984, 49072, 49383, 49754, 49923, 49926, 49928, 49988,
        50181, 50487, 50491, 50599, 50644, 50664, 50817, 50920, 51034, 51224, 51272, 51406,
        51426, 51453, 51582, 51687, 51995, 52055, 52099, 52411, 52614, 52654, 52806, 52896,
        52937, 52953, 52985, 53022, 53134, 53206, 53214, 53286, 53509, 53549, 53619, 53716,
        53798, 53838, 53854, 54030, 54144, 54270, 54342, 54392, 54419, 54447, 54497, 54521,
        54543, 54571, 54594, 54626, 54631, 54700, 54735, 54748, 54755, 54759, 54794, 54800,
        54847, 54880, 54971, 55005, 55009, 55029, 55032, 55066, 55178, 55329, 55473, 55549,
        55671, 55809, 55846, 55860, 55923, 56138, 56302, 56306, 56338, 56360, 56365, 56390,
        56462, 56495, 56545, 56548, 56599, 56623, 56692, 56698, 56756, 56777, 56836, 56885,
        56905, 57082, 57083, 57135, 57204, 57336, 57366, 57456, 57460, 57466, 57475, 57537,
        57559, 57581, 57626, 57629, 57640, 57779, 57781, 57818, 57931, 58216, 58556, 58966,
        59036, 59163, 59207, 59228, 59406, 59500, 59522, 59527, 59532, 59976, 60356, 60652,
        60655, 60747, 61050, 61171, 61229, 61230, 61719, 61794, 62129, 62203, 63229, 63288,
        63468, 63598, 63600, 63752, 63793, 64171, 64254, 64377, 64390, 64467, 64606, 64640,
        64743, 65214, 65602, 65645, 65729, 65923, 65925, 66384, 66715, 66733, 66929, 66948,
        67106, 67171, 67194, 67252, 67395, 67406, 67417, 67469, 67524, 67530, 67597, 67673,
        67774, 68180, 68351, 68659, 69236, 69249, 69462, 69480, 69819, 69901, 69967, 70335,
        70427, 70535, 70670, 70863, 70971, 71858, 72408, 72640, 72704, 72757, 72926, 74955,
        75608, 75781, 75937, 75971, 76151, 77068, 77222, 78637, 82847, 82925, 82967, 83110,
        83164, 83182, 83189, 83209, 83238, 83302, 83399, 83506, 83594, 83684, 83695, 83751,
        83842, 83917, 83949, 84110, 84168, 84180, 84184, 84203, 84225, 84230, 84272, 84364,
        84386, 84465, 84510, 84515, 84627, 84700, 84788, 85037, 85104, 85178, 85373, 85422,
        85590, 85650, 85748, 86473, 87202, 87227, 87253, 87260, 87507, 87509, 87604, 87644,
        87782, 87872, 88164, 88184, 88316, 88406, 88446, 88485, 88909, 89032, 89043, 89221,
        89638, 89757, 89767, 89791, 89929, 89947, 90117, 90118, 90712, 90717, 90739, 90740,
        90767, 90988, 91308, 91453, 91516, 91770, 91832, 92024, 92478, 92503, 92535, 92538,
        92548, 92705, 93581, 93633, 93959, 93966, 94309, 94312, 94467, 94502, 94614, 94699,
        94883, 95056, 95098, 97975, 98038, 98194, 98235, 98252, 98322, 98396, 98408, 98469,
        98533, 98803, 98846, 98958, 99083, 99105, 99107, 99210, 99529, 99559, 99729, 100830,
        101714, 101890, 102026, 102585, 102615, 102623, 102629, 102633, 102680, 102710, 102711, 102723,
        103329, 103834, 104043, 104392, 104449, 104488, 104556, 104585, 104738, 104753, 104774, 104798,
        104818, 105847, 105852, 105855, 106069, 106425, 107063, 107076, 107398, 107658, 107969, 108128,
        108450, 108518, 108648, 108650, 108730, 108933, 109082, 109129, 109143, 109378, 109523, 109636,
        109643, 109664, 109769, 109776, 109811, 109817, 109842, 109849, 112241, 112315, 113801, 113845,
        113857, 113932, 114018, 114055, 114207, 114212, 116045, 117405, 117456, 117555, 117716, 117767,
        117898, 117946, 118362, 118374, 118405, 118446, 118468, 118494, 118524, 118531, 118599, 118602,
        118609, 118620, 118989, 119228, 119280, 119383, 119418, 120469, 121075, 121076, 121733, 121960,
        122022, 122104, 122120, 122252, 122257, 122262, 122274, 122289, 122290, 122337, 122341, 122549,
        122732, 122747, 122849, 122914, 122944, 122982, 123053, 123202, 123382, 123400, 123486, 123496,
        123497, 123515, 123540, 123559, 123598
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'dmd citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM dmd_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING dmd_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 68 local citers name the method in title or abstract.
CREATE TEMP TABLE dmd_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dmd'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        31179, 31635, 37999, 39263, 41340, 42986, 49900, 50320, 53384, 53618, 53993, 54420,
        54453, 54563, 54566, 54600, 55275, 55330, 55714, 57050, 57230, 57306, 57375, 59034,
        60040, 60680, 63155, 64028, 64461, 64688, 64906, 65486, 82839, 82874, 83683, 83773,
        83918, 85686, 87567, 90616, 94236, 98136, 98420, 98812, 99713, 101793, 102586, 105919,
        109136, 109142, 109183, 109649, 113810, 113884, 114029, 118054, 118560, 118605, 119430, 121994,
        122201, 122679, 122791, 122854, 122911, 122936, 123123, 123550
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dmd_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM dmd_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 56 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE dmd_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dmd'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        31635, 36884, 37999, 39263, 41340, 50320, 53384, 53993, 54420, 54453, 54563, 54566,
        54600, 55275, 55330, 55714, 56193, 57050, 57230, 57306, 57375, 59034, 63155, 64028,
        64906, 65486, 82839, 82874, 83281, 83366, 83674, 83683, 83773, 87567, 90616, 94236,
        98812, 99713, 101793, 102586, 105919, 108643, 109183, 113884, 114029, 118605, 119430, 122201,
        122679, 122791, 122854, 122911, 122936, 123123, 123386, 123550
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dmd_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM dmd_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
