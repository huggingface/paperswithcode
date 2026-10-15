-- Add Differentiable Binarization (DBNet) method, sourced from arXiv 1911.08947.

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
    'differentiable-binarization',
    'DBNet',
    'Differentiable Binarization (DBNet)',
    'Differentiable Binarization (DB), used in the DBNet scene text detector, makes the binarization step of segmentation-based text detection trainable end to end. A feature-pyramid backbone predicts a probability map of text regions and a threshold map; instead of a fixed hard threshold, DB computes an approximate binary map as 1 / (1 + exp(-k(P - T))) with a large amplification factor k, which is differentiable and lets the network learn adaptive per-pixel thresholds that separate adjacent text instances. At inference the threshold branch can be dropped, keeping post-processing cheap. With a ResNet-18 backbone DBNet reached an 82.8 F-measure at 62 FPS on MSRA-TD500, handling arbitrary-shaped and curved text, and [DBNet++](/paper/2202.10304) added adaptive scale fusion. DB is the default text detector in toolkits such as PaddleOCR and MMOCR.',
    'DBNet, DBNet++, differentiable binarization',
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
        WHERE arxiv_id = '1911.08947'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Real-time Scene Text Detection with Differentiable Binarization',
    'https://github.com/MhLiao/DB',
    NULL,
    '[Real-time Scene Text Detection with Differentiable Binarization](/paper/1911.08947)'
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
SELECT source_paper_id, id
FROM methods
WHERE slug = 'differentiable-binarization'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'differentiable-binarization'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
