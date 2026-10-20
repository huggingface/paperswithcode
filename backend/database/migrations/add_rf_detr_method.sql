-- Add RF-DETR, introduced in arXiv 2511.09554.
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
    'rf-detr',
    'RF-DETR',
    'RF-DETR',
    'RF-DETR is a real-time [DETR](/methods/detr)-style object detector from Roboflow that pairs a [DINOv2](/methods/dinov2) backbone with a lightweight deformable-attention decoder and uses weight-sharing neural architecture search to pick accuracy-latency trade-offs (resolution, patch size, decoder depth, queries) for a target dataset without retraining. It is the first real-time detector reported above 60 AP on COCO and transfers well to diverse domains on the RF100-VL benchmark, competing with [RT-DETR](/methods/rt-detr), D-FINE and YOLO models. Segmentation variants extend it to instance segmentation.',
    'RF-DETR, RFDETR, RF DETR',
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
        WHERE arxiv_id = '2511.09554'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'RF-DETR: Neural Architecture Search for Real-Time Detection Transformers',
    'https://github.com/roboflow/rf-detr',
    NULL,
    '[RF-DETR: Neural Architecture Search for Real-Time Detection Transformers](/paper/2511.09554)'
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
WHERE slug = 'rf-detr' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'rf-detr' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 17 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE rf_detr_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rf-detr'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        45362, 54913, 59632, 60629, 61272, 63188, 64074, 83221, 85190, 105984, 118074, 118636,
        118809, 118896, 118948, 121983, 122647
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'rf-detr citation review 2026-10-20: cites the source without naming the method in title or abstract'
FROM rf_detr_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING rf_detr_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 3 local citers name the method in title or abstract.
CREATE TEMP TABLE rf_detr_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rf-detr'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        59146, 84587, 106023
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rf_detr_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM rf_detr_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 7 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE rf_detr_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rf-detr'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        47858, 59146, 59237, 69099, 84587, 106023, 114204
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rf_detr_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM rf_detr_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
