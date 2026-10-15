-- Add BEVDet method, sourced from arXiv 2112.11790.

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
    'bevdet',
    'BEVDet',
    'BEVDet',
    'BEVDet is a multi-camera 3D object detection paradigm that detects objects in Bird''s-Eye-View (BEV) space. Its modular design has four parts: an image-view encoder that extracts features from each camera image, a view transformer that lifts them into BEV using a predicted per-pixel depth distribution (following Lift-Splat-Shoot), a BEV encoder that further processes the BEV features, and a task-specific 3D detection head. BEVDet introduced data augmentation applied separately in image space and BEV space to curb overfitting, and Scale-NMS, which rescales boxes per category before [non-maximum suppression](/methods/non-maximum-suppression-nms). BEVDet-Tiny reached 31.2% mAP and 39.2% NDS on nuScenes val with 215.3 GFLOPs, running 9.2 times faster than FCOS3D, and BEVDet4D, BEVDepth and related work extended the paradigm.',
    'BEVDet',
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
        WHERE arxiv_id = '2112.11790'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'BEVDet: High-performance Multi-camera 3D Object Detection in Bird-Eye-View',
    'https://github.com/HuangJunJie2017/BEVDet',
    NULL,
    '[BEVDet: High-performance Multi-camera 3D Object Detection in Bird-Eye-View](/paper/2112.11790)'
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
WHERE slug = 'bevdet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'bevdet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
