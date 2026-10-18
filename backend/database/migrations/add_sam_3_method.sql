-- Add SAM 3, introduced in arXiv 2511.16719.
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
    'sam-3',
    'SAM 3',
    'Segment Anything Model 3 (SAM 3)',
    'SAM 3 (Segment Anything with Concepts) is the third model in Meta''s [Segment Anything](/methods/segment-anything-sam) series. It introduces Promptable Concept Segmentation (PCS): given a concept prompt, either a short noun phrase such as "yellow school bus", image exemplars, or both, it detects, segments and tracks every matching object instance in images and videos and returns masks with unique identities. The model combines an image-level detector and a memory-based video tracker, inherited from [SAM 2](/methods/sam-2), that share a single backbone, and adds a presence head that decouples recognition from localization to improve detection accuracy. A scalable data engine produced a high-quality dataset with 4M unique concept labels, including hard negatives. SAM 3 doubles the accuracy of existing systems on image and video PCS and improves on previous SAM models for promptable visual segmentation. It was released with the SA-Co (Segment Anything with Concepts) benchmark.',
    'sam 3, sam3, segment anything model 3, Segment Anything Model (SAM) 3, segment anything with concepts',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2511.16719'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'SAM 3: Segment Anything with Concepts',
    'https://github.com/facebookresearch/sam3',
    NULL,
    '[SAM 3: Segment Anything with Concepts](/paper/2511.16719)'
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
WHERE slug = 'sam-3' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'sam-3' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 247 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE sam_3_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'sam-3'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        30803, 36733, 46223, 52018, 52139, 52995, 53735, 54230, 54276, 54285, 55372, 56088,
        56109, 56113, 56132, 56134, 56180, 56410, 56428, 56539, 56577, 56592, 56728, 56754,
        56763, 56785, 56933, 56977, 57013, 57088, 57096, 57157, 57176, 57177, 57182, 57242,
        57376, 57520, 57627, 57667, 58000, 58284, 58424, 58802, 58803, 58892, 58901, 58964,
        58974, 59012, 59059, 59161, 59188, 59242, 59384, 59482, 59608, 59636, 59638, 59684,
        59714, 60963, 61614, 62227, 62400, 62960, 63546, 64585, 65791, 67823, 69025, 69848,
        69876, 71014, 82850, 82902, 82921, 83184, 83305, 83405, 83409, 83522, 83593, 83607,
        83764, 85194, 85278, 85675, 85683, 87515, 94654, 95080, 97951, 98122, 98138, 98230,
        98289, 98393, 98463, 98482, 98494, 98527, 98530, 98586, 98596, 98736, 98742, 98747,
        98837, 98916, 98929, 99024, 99085, 99178, 99208, 99380, 99718, 99726, 99739, 99875,
        99994, 100121, 100527, 100568, 100612, 100790, 101799, 102451, 102576, 102682, 103875, 103958,
        103994, 104379, 104441, 104460, 104523, 104570, 105923, 105925, 105980, 108615, 108671, 108698,
        108735, 108828, 108829, 108845, 108889, 108919, 109085, 109123, 109363, 109448, 109459, 109536,
        113728, 113746, 113747, 113802, 113929, 113953, 113965, 114023, 117405, 117412, 117603, 117612,
        117624, 117677, 117892, 118002, 118124, 118211, 118245, 118314, 118327, 118341, 118475, 118509,
        118690, 118709, 118753, 118815, 118822, 118896, 118962, 118981, 118993, 119043, 119066, 119157,
        119254, 119302, 119308, 119315, 119380, 119398, 119424, 119487, 119492, 119510, 119552, 119628,
        119642, 119680, 119683, 121983, 121996, 122077, 122078, 122096, 122117, 122119, 122177, 122262,
        122264, 122280, 122296, 122349, 122562, 122564, 122606, 122624, 122675, 122756, 122783, 122800,
        122836, 122870, 122890, 122944, 122947, 122948, 122959, 122965, 122974, 122976, 122984, 123052,
        123118, 123180, 123282, 123395, 123402, 123546, 123593
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'sam-3 citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM sam_3_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING sam_3_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 29 local citers name the method in title or abstract.
CREATE TEMP TABLE sam_3_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'sam-3'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        54351, 54655, 54678, 55376, 57133, 57677, 58480, 58608, 58891, 58965, 59537, 60092,
        62480, 63949, 64120, 64810, 83153, 83758, 85190, 98543, 98697, 98981, 103819, 108815,
        109136, 114004, 118752, 119407, 122657
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM sam_3_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM sam_3_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 37 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE sam_3_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'sam-3'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        54351, 54655, 54678, 55376, 55525, 57116, 57677, 58480, 58608, 58891, 58965, 59537,
        60092, 60758, 61710, 62480, 63949, 64120, 64651, 64810, 64818, 83153, 83758, 85190,
        98543, 98697, 98981, 103819, 108815, 109136, 113986, 114004, 118752, 118874, 118878, 119407,
        122657
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM sam_3_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM sam_3_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
