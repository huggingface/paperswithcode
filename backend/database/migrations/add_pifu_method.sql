-- Add PIFu, introduced in arXiv 1905.05172.
-- Added 2026-10-21 because production chat users looked it up with
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
    'pifu',
    'PIFu',
    'Pixel-Aligned Implicit Function (PIFu)',
    'PIFu, the pixel-aligned implicit function, digitizes a clothed 3D human from one image or a few views. A fully convolutional image encoder gives a feature for every pixel, and an implicit function takes the feature at a 3D point''s projected location plus its depth and predicts whether the point is inside the surface, so geometry and texture can be sampled at any resolution. The model recovers detailed shapes such as clothing and hair and is a basis for later [3D human reconstruction](/tasks/3d-reconstruction) work.',
    'PIFu, pixel-aligned implicit function',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2019,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1905.05172'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'PIFu: Pixel-Aligned Implicit Function for High-Resolution Clothed Human Digitization',
    'https://github.com/shunsukesaito/PIFu',
    NULL,
    '[PIFu: Pixel-Aligned Implicit Function for High-Resolution Clothed Human Digitization](/paper/1905.05172)'
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
WHERE slug = 'pifu' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'pifu' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 320 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE pifu_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'pifu'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        3201, 3264, 3330, 3736, 3858, 4313, 4608, 4652, 4664, 4720, 4749, 4829,
        4897, 5134, 5303, 5319, 5338, 5529, 5545, 6060, 6085, 6119, 6188, 6191,
        6445, 6585, 6826, 7368, 7549, 7582, 7919, 8073, 8134, 8457, 8535, 8715,
        8781, 8810, 8871, 9720, 9784, 9833, 11036, 11466, 11701, 11806, 11907, 11954,
        11972, 11973, 12197, 12435, 12454, 12777, 13106, 13258, 13500, 13824, 13839, 13924,
        13932, 13933, 13981, 14029, 14034, 14137, 14183, 14325, 14392, 14420, 14456, 14481,
        14501, 14635, 14830, 14845, 15237, 15318, 15430, 15559, 15806, 15859, 16050, 16075,
        16336, 16849, 17537, 17547, 17883, 17957, 18420, 18475, 18513, 18547, 18760, 19062,
        19334, 19354, 19405, 19433, 19436, 19487, 19560, 19580, 19670, 19727, 19755, 19839,
        19881, 19915, 20204, 20334, 20559, 20596, 20758, 21205, 21628, 22760, 22853, 23187,
        23499, 23810, 23860, 23894, 23924, 23984, 24045, 24231, 24241, 24311, 24315, 24482,
        24560, 24627, 24996, 25072, 25168, 25258, 25480, 25631, 25972, 26137, 26204, 26526,
        26641, 27978, 28037, 28180, 28687, 28919, 28922, 29388, 29468, 29570, 29778, 29790,
        30256, 30455, 30720, 30780, 30888, 31634, 31637, 32252, 32727, 32811, 33249, 34030,
        34190, 34340, 34506, 34584, 34840, 35248, 35383, 35927, 36147, 36232, 36583, 36647,
        36927, 37334, 37339, 37557, 38045, 39939, 40511, 40616, 40724, 40918, 41244, 41904,
        42121, 43131, 43227, 43984, 44055, 44354, 44407, 44994, 45092, 45337, 45855, 45902,
        45905, 46074, 46420, 46473, 46694, 47889, 48358, 50079, 50283, 52447, 53390, 53864,
        55109, 59315, 61715, 64425, 64610, 67283, 68319, 69224, 69362, 70475, 70838, 70911,
        71484, 71942, 73294, 73625, 74721, 75109, 78058, 78406, 78491, 80037, 80485, 80540,
        80748, 80833, 81040, 81363, 84776, 84903, 84959, 85289, 85576, 85623, 86347, 88069,
        88394, 88484, 88513, 90087, 90088, 90300, 90301, 90368, 90428, 90513, 90528, 90560,
        90683, 92201, 93582, 94867, 94893, 98399, 101777, 103963, 104156, 104808, 104827, 104879,
        108289, 109867, 112896, 112902, 112912, 113494, 113542, 113605, 114908, 115311, 115535, 115691,
        115847, 115961, 116041, 116112, 116246, 116368, 116534, 116564, 116588, 116706, 116729, 116793,
        116801, 116953, 117028, 117032, 117045, 117275, 117289, 117303, 117414, 117993, 119194, 119267,
        119308, 119323, 119329, 119753, 119782, 119817, 123601, 123850
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'pifu citation review 2026-10-21: cites the source without naming the method in title or abstract'
FROM pifu_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING pifu_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 3 local citers name the method in title or abstract.
CREATE TEMP TABLE pifu_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'pifu'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        3285, 23879, 80041
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM pifu_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM pifu_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 4 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE pifu_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'pifu'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        3285, 80041, 112660, 113081
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM pifu_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM pifu_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
