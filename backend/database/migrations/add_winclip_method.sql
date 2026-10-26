-- Add WinCLIP, introduced in arXiv 2303.14814.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'winclip',
    'WinCLIP',
    'WinCLIP',
    'WinCLIP is a zero-shot and few-shot method for visual anomaly classification and segmentation built on [CLIP](/methods/clip). It scores an image against compositional text prompts that describe normal and anomalous states of an object, and uses a window-based scheme that evaluates CLIP on multi-scale sliding windows to localize defects, aggregating the window scores into a pixel-level anomaly map. WinCLIP+ adds a few normal reference images whose window features are matched to the query, and the paper reports state-of-the-art zero-shot results on MVTec-AD and VisA.',
    'WinCLIP',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2303.14814' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'WinCLIP: Zero-/Few-Shot Anomaly Classification and Segmentation',
    NULL,
    NULL,
    '[WinCLIP: Zero-/Few-Shot Anomaly Classification and Segmentation](/paper/2303.14814)'
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
WHERE slug = 'winclip' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'winclip' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 107 local citers cite the source without naming the method in title or abstract; exclude them so the hourly reference backfill does not link them.
CREATE TEMP TABLE winclip_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'winclip'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        12573, 13075, 15695, 19910, 19934, 22719, 26466, 30620, 31528, 31575, 34208, 34772,
        34797, 35066, 35395, 38799, 38847, 41052, 44037, 45306, 45314, 45411, 45546, 46017,
        46245, 46619, 47716, 47930, 47979, 48717, 48718, 48750, 54183, 57176, 57358, 58531,
        59419, 59929, 63685, 67237, 67553, 69215, 69484, 69871, 70196, 70768, 72445, 73590,
        74673, 75604, 78504, 78650, 83508, 83970, 84547, 84561, 84694, 84808, 84940, 84981,
        85028, 85162, 87659, 88269, 88335, 89200, 90291, 90465, 90900, 93319, 94593, 98903,
        99349, 100434, 105371, 105779, 105887, 105892, 105903, 105904, 107319, 107850, 113520, 114290,
        115107, 115516, 115680, 115765, 115770, 116322, 116748, 116907, 116926, 117173, 117397, 118227,
        118752, 118827, 118986, 119017, 119033, 119054, 119071, 120337, 120635, 120889, 123348
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'winclip citation review 2026-10-22: cites the source without naming the method in title or abstract'
FROM winclip_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING winclip_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 1 local citers name the method in title or abstract.
CREATE TEMP TABLE winclip_cited ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'winclip'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        121546
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM winclip_cited x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM winclip_cited x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 2 papers match the method keywords (same matcher as the daily keyword backfill).
CREATE TEMP TABLE winclip_keyword ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'winclip'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        22851, 121546
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM winclip_keyword x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM winclip_keyword x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
