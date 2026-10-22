-- Add ByteTrack, introduced in arXiv 2110.06864.
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
    'bytetrack',
    'ByteTrack',
    'ByteTrack',
    'ByteTrack is a tracking-by-detection method for [multi-object tracking](/tasks/object-tracking) that associates almost every detection box instead of discarding low-score ones. Its BYTE association step first matches high-score boxes to existing tracklets, then matches the leftover tracklets against low-score boxes, which recovers occluded or blurred objects and reduces fragmented tracks. It needs no appearance model, runs at about 30 FPS, and reached 80.3 MOTA and 77.3 IDF1 on MOT17, ranking first on the benchmark at the time.',
    'ByteTrack',
    (
        SELECT id
        FROM areas
        WHERE name = 'Video'
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2110.06864'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'ByteTrack: Multi-Object Tracking by Associating Every Detection Box',
    'https://github.com/ifzhang/ByteTrack',
    NULL,
    '[ByteTrack: Multi-Object Tracking by Associating Every Detection Box](/paper/2110.06864)'
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
WHERE slug = 'bytetrack' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'bytetrack' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 217 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE bytetrack_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bytetrack'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        7329, 8081, 8440, 8641, 8714, 8905, 9426, 9643, 9700, 11390, 11446, 11587,
        13227, 14609, 14736, 17163, 17428, 18738, 18749, 19032, 19140, 19192, 19634, 19644,
        19683, 19775, 20497, 22381, 23275, 24065, 24124, 24614, 24798, 24914, 25183, 26078,
        26283, 28559, 28933, 29012, 29427, 29668, 30038, 30464, 30803, 31718, 32180, 32252,
        32430, 32503, 34187, 35200, 35204, 35269, 36341, 36450, 36987, 37544, 37696, 39510,
        39593, 40135, 40330, 40408, 40513, 42797, 43946, 44088, 44408, 44479, 45072, 46207,
        46286, 46546, 46741, 47267, 47341, 47714, 48333, 50627, 51263, 52171, 52691, 52866,
        54490, 54525, 54913, 54958, 57893, 58997, 61633, 63277, 63285, 63966, 64229, 64614,
        64818, 66291, 66432, 68095, 68384, 69436, 70325, 70756, 71133, 71232, 71241, 71324,
        72433, 73075, 73680, 73907, 74253, 75102, 75146, 75225, 75893, 75953, 75981, 76453,
        76767, 76874, 76961, 77173, 77459, 77883, 78101, 78118, 78572, 78864, 78874, 78980,
        79251, 79538, 79835, 79903, 83969, 84380, 84771, 84772, 84803, 85031, 85370, 85432,
        85514, 86688, 87476, 87595, 87680, 88343, 88442, 89934, 90435, 91020, 92136, 94650,
        95932, 96378, 96391, 96525, 96624, 97039, 98182, 98352, 98440, 98783, 98797, 104188,
        104514, 104860, 105864, 106543, 106550, 106734, 107346, 107743, 107917, 108186, 109311, 109321,
        109322, 109323, 109851, 109924, 112451, 112504, 112892, 113019, 113084, 114004, 114959, 115655,
        115799, 115902, 115914, 115917, 116373, 116387, 116508, 116555, 116562, 116576, 116666, 117912,
        118095, 118950, 118953, 118962, 118981, 119014, 119031, 119041, 119730, 120043, 122055, 123357,
        123743
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'bytetrack citation review 2026-10-21: cites the source without naming the method in title or abstract'
FROM bytetrack_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING bytetrack_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 7 local citers name the method in title or abstract.
CREATE TEMP TABLE bytetrack_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bytetrack'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        14116, 37355, 58608, 94627, 105992, 116620, 118627
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM bytetrack_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM bytetrack_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 7 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE bytetrack_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bytetrack'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        14116, 37355, 58608, 94627, 105992, 116620, 118627
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM bytetrack_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM bytetrack_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
