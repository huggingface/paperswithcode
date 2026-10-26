-- Add EfficientNetV2, introduced in arXiv 2104.00298.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'efficientnetv2',
    'EfficientNetV2',
    'EfficientNetV2',
    'EfficientNetV2 is a family of convolutional image classifiers that improves on [EfficientNet](/methods/efficientnet) for training speed and parameter efficiency. It uses training-aware neural architecture search and scaling, swaps depthwise convolutions for fused-MBConv blocks in the early stages where depthwise layers are slow on accelerators, and adds progressive learning that grows image size while scaling regularization. The models train much faster than prior state of the art while being up to 6.8x smaller, and with ImageNet-21k pretraining EfficientNetV2 reaches 87.3% ImageNet top-1 accuracy, 2.0 points above ViT while training 5x-11x faster.',
    'EfficientNetV2, EfficientNet-V2, EfficientNet V2',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2104.00298' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'EfficientNetV2: Smaller Models and Faster Training',
    'https://github.com/google/automl/tree/master/efficientnetv2',
    NULL,
    '[EfficientNetV2: Smaller Models and Faster Training](/paper/2104.00298)'
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
WHERE slug = 'efficientnetv2' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'efficientnetv2' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 233 local citers cite the source without naming the method in title or abstract; exclude them so the hourly reference backfill does not link them.
CREATE TEMP TABLE efficientnetv2_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'efficientnetv2'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        3310, 5271, 5362, 5732, 5742, 5921, 5928, 6051, 6112, 6184, 6395, 6769,
        7262, 7302, 7352, 7552, 7673, 7686, 7752, 7880, 7953, 8018, 8150, 8345,
        8466, 8560, 8612, 8719, 8851, 8904, 9197, 9260, 9413, 9550, 9628, 9700,
        9876, 10550, 10615, 10753, 10765, 10907, 10920, 11031, 11239, 11297, 11409, 11844,
        11893, 11999, 12283, 13017, 13263, 13335, 13452, 13534, 13773, 14109, 14133, 14272,
        14296, 14422, 14495, 14618, 14624, 15244, 15495, 15547, 15783, 16455, 16761, 17243,
        17355, 17679, 17763, 18323, 18646, 18914, 19375, 19790, 19891, 19929, 20345, 20700,
        21485, 22768, 23027, 23954, 23995, 24101, 24628, 25113, 25947, 26112, 27002, 29053,
        29151, 29293, 29620, 29652, 29653, 29856, 29878, 29910, 30203, 30459, 30547, 30686,
        31346, 31949, 31995, 32274, 33211, 33389, 34452, 34458, 35152, 35335, 35369, 35988,
        36199, 36616, 36878, 37651, 37661, 37717, 38904, 39752, 39847, 40394, 41007, 41578,
        41592, 41792, 42808, 43102, 43729, 43900, 44061, 44580, 44629, 45464, 46262, 46740,
        46748, 47280, 47911, 58877, 60020, 60681, 61924, 62547, 63045, 63966, 64015, 64074,
        65185, 65555, 67246, 67682, 68585, 68776, 69270, 69602, 70154, 71023, 71048, 71424,
        71502, 71575, 71870, 71913, 72800, 73804, 73843, 74398, 75664, 76136, 76152, 76474,
        76730, 76872, 77051, 77289, 77382, 78331, 78619, 78830, 78871, 79112, 79384, 79858,
        79859, 79954, 80070, 80190, 84022, 84259, 84392, 85939, 86184, 86829, 86919, 87291,
        87702, 87996, 88133, 88412, 88636, 90557, 91087, 92150, 92384, 92519, 94838, 95537,
        98837, 101092, 102692, 105224, 106866, 107095, 107314, 108544, 113145, 113466, 113964, 115365,
        115882, 116870, 117554, 121983, 122038
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'efficientnetv2 citation review 2026-10-22: cites the source without naming the method in title or abstract'
FROM efficientnetv2_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING efficientnetv2_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 8 local citers name the method in title or abstract.
CREATE TEMP TABLE efficientnetv2_cited ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'efficientnetv2'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        13560, 14520, 18339, 25416, 40002, 50501, 61492, 70751
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM efficientnetv2_cited x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM efficientnetv2_cited x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 11 papers match the method keywords (same matcher as the daily keyword backfill).
CREATE TEMP TABLE efficientnetv2_keyword ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'efficientnetv2'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        13560, 14520, 18339, 25416, 40002, 42878, 50501, 61492, 66099, 70751, 120952
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM efficientnetv2_keyword x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM efficientnetv2_keyword x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
