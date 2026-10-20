-- Add SmoothQuant, introduced in arXiv 2211.10438.
-- Added 2026-10-20 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.
-- The source paper gets the source evidence row (Introduced banner).

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
    'smoothquant',
    'SmoothQuant',
    'SmoothQuant',
    'SmoothQuant is a training-free post-training quantization method that enables 8-bit weight and 8-bit activation (W8A8) inference for large language models. Activation outliers concentrate in a few channels, which makes activations hard to quantize, so SmoothQuant divides activations by per-channel smoothing factors and multiplies the following weights by the same factors. This mathematically equivalent transform migrates quantization difficulty from activations to weights. It preserved accuracy on OPT-175B, BLOOM-176B and GLM-130B with up to 1.56x speedup and 2x memory reduction, and complements weight-only methods such as [GPTQ](/methods/gptq).',
    'SmoothQuant, smooth quant',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2022,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2211.10438'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'SmoothQuant: Accurate and Efficient Post-Training Quantization for Large Language Models',
    'https://github.com/mit-han-lab/smoothquant',
    NULL,
    '[SmoothQuant: Accurate and Efficient Post-Training Quantization for Large Language Models](/paper/2211.10438)'
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
WHERE slug = 'smoothquant' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'smoothquant' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 662 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE smoothquant_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'smoothquant'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        9543, 12087, 12279, 12604, 12837, 12851, 12997, 13338, 13693, 13772, 13926, 14216,
        14337, 14957, 15358, 15396, 15631, 15672, 15741, 16036, 16063, 16226, 16279, 16398,
        16465, 16618, 16727, 16806, 16988, 17347, 17633, 17650, 17691, 17739, 18201, 18280,
        18401, 18608, 19256, 19440, 19766, 19836, 19856, 19938, 19957, 20097, 20145, 20273,
        20291, 20373, 20479, 20875, 20916, 20923, 21004, 21086, 21113, 21116, 21196, 21237,
        21399, 21493, 21525, 21545, 21569, 21578, 21618, 21641, 21724, 21748, 21773, 21845,
        21917, 21939, 21963, 22096, 22127, 22346, 22590, 22696, 22856, 22996, 23213, 23414,
        23568, 23594, 24125, 24493, 24511, 24533, 24720, 24750, 25003, 25105, 25261, 25517,
        25581, 25601, 25719, 26051, 26346, 26365, 26547, 26625, 26704, 26767, 26792, 26880,
        26892, 26898, 26940, 26995, 27009, 27018, 27032, 27035, 27052, 27085, 27210, 27298,
        27346, 27370, 27380, 27437, 27486, 27673, 27715, 27861, 27917, 27967, 27989, 28087,
        28088, 28129, 28219, 28244, 28270, 28548, 28596, 28698, 28712, 28767, 29093, 29100,
        29346, 29494, 29503, 29662, 29701, 29896, 29951, 30034, 30079, 30170, 30337, 30351,
        30493, 30573, 30639, 30647, 30670, 30701, 30779, 30899, 30962, 31041, 31092, 31126,
        31500, 31570, 31578, 31630, 31642, 31756, 31772, 31798, 31925, 32071, 32126, 32260,
        32261, 32311, 32349, 32404, 32459, 32587, 32589, 32624, 32689, 32705, 32746, 32755,
        33092, 33133, 33330, 33458, 33496, 33567, 33583, 33607, 33651, 33663, 33767, 33832,
        33874, 33901, 34098, 34220, 34286, 34287, 34296, 34355, 34581, 34609, 34701, 34737,
        34748, 34752, 34801, 34811, 34852, 35080, 35165, 35201, 35350, 35816, 36043, 36088,
        36255, 36442, 36503, 36535, 36537, 36606, 36792, 36796, 36976, 37110, 37210, 37300,
        37327, 37343, 37546, 37695, 37752, 38019, 38112, 38116, 38146, 38212, 38259, 38359,
        38459, 38474, 38583, 38663, 38684, 38752, 39246, 39305, 39612, 39713, 39764, 39874,
        39888, 40063, 40066, 40081, 40083, 40121, 40260, 40492, 40512, 40977, 41054, 41867,
        41883, 42224, 42483, 42497, 42737, 42889, 43110, 43130, 43143, 43180, 43220, 43228,
        43309, 43348, 43390, 43418, 43491, 43522, 43543, 43577, 43673, 43755, 44053, 44112,
        44133, 44436, 44564, 45376, 45712, 45840, 45865, 46098, 46399, 46470, 46489, 46496,
        46704, 46886, 46963, 47069, 47242, 47303, 47354, 47616, 47711, 47762, 48149, 48241,
        48314, 48326, 48380, 48392, 48463, 48550, 48874, 48881, 48997, 49064, 49083, 49154,
        49206, 49535, 49688, 49733, 49746, 49938, 50054, 50063, 50166, 50818, 50822, 51142,
        51298, 51554, 51706, 51846, 52077, 52448, 52592, 52809, 52831, 52967, 53039, 53102,
        53187, 53302, 53320, 53404, 53452, 53601, 53643, 53982, 53988, 54138, 54247, 54454,
        54503, 54553, 54577, 54619, 54741, 54807, 54834, 55391, 55475, 55700, 55725, 55755,
        55888, 55907, 56114, 56163, 56274, 56489, 56690, 56788, 56844, 57016, 57308, 57828,
        57981, 58017, 58032, 58263, 58363, 58393, 58595, 58903, 59167, 59197, 59284, 59868,
        60159, 60479, 60494, 60621, 61018, 61025, 61255, 61514, 61567, 61695, 61723, 61872,
        61893, 61910, 61948, 61983, 62439, 62491, 62669, 62731, 62974, 64042, 64248, 64397,
        64643, 64715, 64738, 65041, 65048, 65943, 66039, 66117, 66148, 66195, 66524, 66525,
        67017, 67052, 67339, 67363, 67545, 67559, 67622, 67639, 67665, 67861, 67872, 68185,
        68248, 68331, 68456, 68761, 69203, 69338, 69390, 69837, 70193, 70340, 70463, 70498,
        70904, 70930, 70970, 71130, 71190, 71264, 72065, 72221, 72266, 72281, 72481, 72757,
        73110, 73128, 73130, 73217, 73241, 73245, 73277, 73288, 73843, 74117, 74130, 74206,
        74237, 74397, 74507, 74531, 74542, 74769, 74778, 74868, 75003, 75226, 75350, 75540,
        75778, 75882, 76030, 76070, 76073, 76302, 76583, 76797, 76946, 77103, 77321, 77718,
        77872, 77924, 78408, 78569, 78971, 83308, 83366, 83376, 83401, 83402, 83509, 83513,
        83521, 84192, 84653, 84960, 85732, 85804, 85840, 85889, 86409, 86411, 86515, 86740,
        87258, 87472, 87727, 87784, 87827, 87872, 87943, 88696, 88720, 88857, 89151, 89161,
        89335, 89558, 89765, 89906, 89940, 91110, 91477, 91645, 91737, 92221, 92254, 92436,
        92571, 92727, 92907, 93025, 93283, 93329, 93379, 93576, 93661, 93743, 93841, 93941,
        93950, 93989, 94064, 94473, 94505, 94517, 94541, 94852, 94995, 95130, 96121, 97509,
        97932, 98567, 99164, 99309, 99363, 99530, 99592, 99600, 99753, 100141, 100310, 100326,
        100347, 100432, 100437, 100521, 100552, 100658, 100904, 100927, 100970, 101032, 101255, 101309,
        101335, 101404, 101413, 101539, 101624, 101640, 101698, 101836, 102078, 102219, 102401, 102428,
        102550, 102728, 103233, 103378, 103828, 105976, 107085, 107263, 107970, 108786, 108853, 109061,
        109583, 109799, 110074, 110433, 113922, 114058, 114153, 117456, 118207, 118212, 118717, 118913,
        119392, 119551, 120216, 121046, 121989, 122011, 122303, 122393, 122447, 122691, 122700, 122887,
        123037, 123152
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'smoothquant citation review 2026-10-20: cites the source without naming the method in title or abstract'
FROM smoothquant_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING smoothquant_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 8 local citers name the method in title or abstract.
CREATE TEMP TABLE smoothquant_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'smoothquant'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        18087, 24390, 26342, 31761, 56493, 61311, 65361, 106368
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM smoothquant_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM smoothquant_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 11 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE smoothquant_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'smoothquant'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        18087, 24390, 25573, 26342, 31761, 35891, 56493, 61311, 65361, 70120, 106368
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM smoothquant_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM smoothquant_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
