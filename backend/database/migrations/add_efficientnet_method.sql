-- Add EfficientNet, introduced in arXiv 1905.11946.
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
    'efficientnet',
    'EfficientNet',
    'EfficientNet',
    'EfficientNet is a family of convolutional image classifiers built around compound scaling, which grows network depth, width and input resolution together with one fixed coefficient instead of scaling a single dimension. A small baseline found by neural architecture search is scaled up to give models B0 to B7. EfficientNet-B7 reached 84.3% top-1 on ImageNet while being 8.4x smaller and 6.1x faster than the best earlier ConvNet, and the models became a standard backbone for transfer learning, detection and [semantic segmentation](/tasks/image-segmentation).',
    'EfficientNet, EfficientNets',
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
        WHERE arxiv_id = '1905.11946'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks',
    'https://github.com/tensorflow/tpu/tree/master/models/official/efficientnet',
    NULL,
    '[EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks](/paper/1905.11946)'
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
WHERE slug = 'efficientnet' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'efficientnet' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 428 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE efficientnet_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'efficientnet'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        37661, 38093, 38117, 38118, 38208, 38330, 38399, 38545, 38715, 38762, 38904, 39014,
        39492, 39733, 39752, 39777, 39862, 39875, 39906, 40106, 40120, 40330, 40336, 40375,
        40394, 40580, 40902, 41061, 41126, 41415, 41456, 41592, 41640, 41690, 41769, 41792,
        42034, 42137, 42237, 42404, 42425, 42480, 42740, 43022, 43035, 43087, 43100, 43132,
        43226, 43242, 43251, 43444, 43468, 43726, 43729, 43900, 43914, 44083, 44203, 44367,
        44536, 44580, 44645, 44681, 44748, 44854, 45110, 45219, 45340, 45391, 45464, 45848,
        45884, 45932, 46262, 46463, 46748, 46769, 46838, 46985, 47604, 47842, 47855, 47877,
        47933, 47968, 47971, 48188, 48348, 48695, 48717, 48765, 48838, 48860, 48886, 48977,
        49002, 49608, 49750, 50159, 50239, 50241, 50745, 51002, 51089, 51886, 51888, 51977,
        52057, 52078, 52127, 52136, 53373, 53499, 53682, 53700, 53758, 53861, 54045, 54188,
        54262, 54348, 54848, 54907, 55131, 55137, 55545, 57550, 57799, 58306, 58335, 58413,
        58478, 58570, 58813, 58930, 59178, 59195, 59261, 59329, 59416, 59480, 59525, 59886,
        60024, 60031, 60143, 60203, 60354, 60465, 60566, 60681, 60919, 60989, 61011, 61101,
        61182, 61363, 61370, 61410, 61709, 61924, 62549, 62760, 62913, 63094, 63289, 63504,
        63892, 64316, 64895, 64952, 65098, 65191, 65266, 65274, 65428, 65554, 65638, 65642,
        66000, 66032, 66052, 66200, 66387, 66428, 66549, 66585, 66625, 67096, 67974, 68096,
        68381, 68641, 68715, 68886, 68903, 69090, 69166, 69177, 69495, 69514, 70088, 70154,
        70346, 70524, 70582, 70613, 70658, 70665, 70919, 70984, 71053, 71298, 71307, 71380,
        71502, 71575, 71583, 71715, 71826, 71870, 71875, 72274, 72329, 72436, 72443, 72531,
        72577, 72622, 72643, 72676, 72758, 73043, 73221, 73254, 73270, 73651, 73722, 73731,
        73757, 73776, 73797, 73881, 73891, 73937, 74055, 74526, 74777, 74785, 75148, 75663,
        75805, 75823, 75888, 75929, 76181, 82861, 82944, 83881, 84006, 84067, 84100, 84147,
        84293, 84344, 84457, 84786, 84797, 84826, 84886, 84928, 84975, 85041, 85120, 85226,
        85279, 85335, 85364, 85523, 85906, 86135, 86153, 86174, 86239, 86375, 86481, 86487,
        86521, 86522, 86650, 86796, 86844, 86851, 86919, 87104, 87158, 87244, 87291, 87298,
        87612, 87622, 87659, 87899, 88087, 88109, 88360, 88412, 88609, 88698, 89245, 89444,
        89725, 89733, 89794, 89929, 89974, 90106, 90117, 90164, 90218, 90288, 90291, 90325,
        90382, 90395, 90478, 90500, 90557, 90581, 90629, 90662, 90722, 90774, 90860, 90936,
        91261, 91267, 91300, 91774, 92040, 92121, 92127, 92281, 92966, 93245, 93565, 93975,
        94112, 94128, 94259, 94488, 94982, 94988, 95000, 95039, 95046, 95061, 95356, 95363,
        95948, 96583, 96614, 97243, 97766, 98539, 99006, 99157, 99183, 99446, 99546, 99800,
        100635, 100776, 101268, 101291, 101569, 101648, 101979, 102381, 104113, 104558, 104629, 104729,
        105402, 105618, 105769, 105812, 105955, 106650, 107120, 107207, 107252, 107339, 107515, 107640,
        107823, 108020, 108042, 108224, 108246, 108367, 108546, 108793, 109420, 109903, 111314, 111430,
        112999, 117415, 117470, 117604, 117937, 118566, 118693, 118770, 119062, 119108, 119954, 120066,
        120184, 120305, 120578, 121172, 121546, 121647, 121909, 122106
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'efficientnet citation review 2026-10-21: cites the source without naming the method in title or abstract'
FROM efficientnet_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING efficientnet_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 20 local citers name the method in title or abstract.
CREATE TEMP TABLE efficientnet_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'efficientnet'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        39027, 40002, 40561, 45882, 47990, 48100, 48299, 50706, 52094, 54791, 57946, 61554,
        65547, 65555, 68585, 68877, 69278, 72874, 84912, 100971
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM efficientnet_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM efficientnet_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 98 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE efficientnet_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'efficientnet'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        1984, 2460, 2586, 2800, 2843, 2845, 3115, 3251, 3274, 3303, 3364, 3378,
        3655, 3669, 3799, 4463, 4875, 4923, 4955, 4972, 5022, 5052, 5153, 5196,
        5255, 5341, 5349, 5362, 5536, 6189, 6807, 7207, 7357, 8904, 9413, 9628,
        12480, 13560, 13754, 13849, 14109, 14520, 15714, 17215, 17751, 18339, 19489, 21745,
        23027, 23148, 25416, 29020, 32177, 39027, 39164, 39206, 40002, 40561, 42366, 42878,
        43011, 45882, 47990, 48100, 48299, 50501, 50706, 52094, 54791, 57946, 61492, 61554,
        62355, 63409, 63783, 65547, 65555, 66099, 68585, 68877, 69278, 69905, 70751, 72874,
        73739, 78329, 79733, 79898, 80475, 80479, 80848, 80988, 81362, 84912, 91855, 92150,
        100971, 120952
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM efficientnet_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM efficientnet_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
