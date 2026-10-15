-- Add RT-DETR method, sourced from arXiv 2304.08069.

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
    'rt-detr',
    'RT-DETR',
    'Real-Time Detection Transformer (RT-DETR)',
    'RT-DETR (Real-Time DEtection TRansformer) is the first real-time end-to-end object detector, built on [DETR](/methods/detr) and free of [non-maximum suppression](/methods/non-maximum-suppression-nms). Its efficient hybrid encoder decouples intra-scale interaction, applying self-attention only to the highest-level feature map (AIFI), from cross-scale fusion done by a convolutional module (CCFF), which removes most of the cost of multi-scale Transformer encoders. Uncertainty-minimal query selection picks high-quality encoder features as initial object queries, and the number of decoder layers can be changed at inference to trade speed for accuracy without retraining. RT-DETR-R50 and R101 reached 53.1% and 54.3% AP on COCO at 108 and 74 FPS on a T4 GPU, outperforming [YOLO](/methods/yolo) detectors of similar scale in both speed and accuracy.',
    'RT-DETR, RTDETR',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2304.08069'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'DETRs Beat YOLOs on Real-time Object Detection',
    'https://github.com/lyuwenyu/RT-DETR',
    NULL,
    '[DETRs Beat YOLOs on Real-time Object Detection](/paper/2304.08069)'
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
WHERE slug = 'rt-detr'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'rt-detr'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
