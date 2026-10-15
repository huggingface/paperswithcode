-- Add DINOv2 method, sourced from arXiv 2304.07193.

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
    'dinov2',
    'DINOv2',
    'DINOv2',
    'DINOv2 is a [self-supervised](/methods/self-supervised-learning) method and family of [Vision Transformer](/methods/vision-transformer) models that produce general-purpose visual features which work frozen, with only linear heads, across classification, segmentation, depth estimation and retrieval. It scales up discriminative self-distillation by combining the image-level [DINO](/methods/dino) loss with the patch-level iBOT masked-token loss, Sinkhorn-Knopp centering, a KoLeo regularizer that spreads features, and a short high-resolution training phase. Training data comes from LVD-142M, a 142M-image dataset curated automatically by retrieving uncurated web images close to curated sources. A 1B-parameter ViT-g teacher is [distilled](/methods/knowledge-distillation) into smaller ViT-S, ViT-B and ViT-L models, and DINOv2 features became a common backbone for dense prediction and robotics.',
    'DINOv2, DINO v2',
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
        WHERE arxiv_id = '2304.07193'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'DINOv2: Learning Robust Visual Features without Supervision',
    'https://github.com/facebookresearch/dinov2',
    NULL,
    '[DINOv2: Learning Robust Visual Features without Supervision](/paper/2304.07193)'
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
WHERE slug = 'dinov2'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'dinov2'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
