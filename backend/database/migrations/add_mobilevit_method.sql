-- Add MobileViT, introduced in arXiv 2110.02178.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'mobilevit',
    'MobileViT',
    'MobileViT',
    'MobileViT is a light-weight vision backbone for mobile devices that combines the local processing of convolutions with the global reasoning of transformers. Its MobileViT block applies a convolution, unfolds the feature map into patches, runs a [Transformer](/methods/transformer) across the patches as a learned global convolution, then folds the result back and fuses it with the input. With about 6M parameters, MobileViT reaches 78.4% ImageNet top-1 accuracy, 6.2 points above MobileNetv3 at a similar budget, and it also serves as a backbone for detection and segmentation.',
    'MobileViT, MobileViTs',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2110.02178' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'MobileViT: Light-weight, General-purpose, and Mobile-friendly Vision Transformer',
    'https://github.com/apple/ml-cvnets',
    NULL,
    '[MobileViT: Light-weight, General-purpose, and Mobile-friendly Vision Transformer](/paper/2110.02178)'
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
WHERE slug = 'mobilevit' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'mobilevit' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 173 local citers cite the source without naming the method in title or abstract; exclude them so the hourly reference backfill does not link them.
CREATE TEMP TABLE mobilevit_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mobilevit'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        6018, 7752, 8078, 9206, 9253, 9260, 9336, 9413, 9628, 9765, 9866, 10525,
        10550, 10870, 11239, 11327, 11328, 11563, 12005, 12015, 12288, 13190, 13335, 13390,
        13480, 13846, 13849, 13948, 14320, 14608, 14618, 15169, 15742, 16321, 16896, 17258,
        17567, 17607, 17754, 17997, 18280, 18323, 18368, 18578, 18646, 18820, 18835, 19196,
        19213, 20223, 20749, 21485, 23020, 23470, 24153, 24556, 24618, 25296, 25516, 26871,
        27085, 27316, 27718, 27900, 28207, 28319, 28899, 29519, 29645, 29856, 30203, 30418,
        30459, 30619, 30726, 32274, 32419, 32576, 33383, 33533, 33809, 33815, 34140, 34452,
        34870, 35152, 35512, 35629, 36496, 36616, 37284, 39166, 40336, 40394, 41592, 41792,
        42034, 42237, 42420, 42956, 43251, 43468, 43731, 45464, 46985, 48695, 50029, 51888,
        52057, 52140, 54779, 59578, 59839, 60400, 62953, 64042, 64649, 65555, 68456, 68516,
        68525, 68715, 69166, 69290, 70092, 70346, 70593, 72585, 72613, 73184, 73722, 73986,
        74552, 77045, 77051, 77289, 77294, 77930, 78179, 78515, 78830, 79120, 79367, 80070,
        85557, 85586, 86239, 86386, 86851, 86852, 87622, 87839, 88371, 88609, 89974, 90492,
        91267, 91644, 94488, 95774, 95948, 104085, 108786, 112650, 112833, 112926, 113139, 115774,
        116233, 116569, 118101, 119151, 123355
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'mobilevit citation review 2026-10-22: cites the source without naming the method in title or abstract'
FROM mobilevit_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING mobilevit_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 14 local citers name the method in title or abstract.
CREATE TEMP TABLE mobilevit_cited ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mobilevit'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        9377, 9564, 13534, 14012, 14196, 15470, 19623, 23027, 26446, 29020, 29652, 32500,
        64101, 76712
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mobilevit_cited x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM mobilevit_cited x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 15 papers match the method keywords (same matcher as the daily keyword backfill).
CREATE TEMP TABLE mobilevit_keyword ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mobilevit'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        9377, 9564, 13534, 14012, 14196, 15470, 19623, 23027, 26446, 29020, 29652, 32500,
        64101, 76712, 107428
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mobilevit_keyword x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM mobilevit_keyword x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
