-- Add PatchCore method, sourced from arXiv 2106.08265.

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
    'patchcore',
    'PatchCore',
    'PatchCore',
    'PatchCore is an unsupervised industrial anomaly detection and localization method that needs only defect-free training images. It extracts locally aware patch features from the mid-level layers of an ImageNet-pretrained CNN such as WideResNet-50, aggregating each patch with its neighbourhood, and stores them in a memory bank. Greedy coreset subsampling shrinks the bank to a small subset that still covers the nominal feature space, which keeps inference fast. At test time each patch is scored by its distance to the nearest neighbour in the memory bank ([k-NN](/methods/knn)); the maximum patch score gives the image-level anomaly score and the upsampled patch scores give a segmentation map. PatchCore reached up to 99.6% image-level AUROC on MVTec AD and became a standard baseline for visual anomaly detection.',
    'PatchCore',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2106.08265'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Towards Total Recall in Industrial Anomaly Detection',
    'https://github.com/amazon-science/patchcore-inspection',
    NULL,
    '[Towards Total Recall in Industrial Anomaly Detection](/paper/2106.08265)'
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
WHERE slug = 'patchcore'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'patchcore'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
