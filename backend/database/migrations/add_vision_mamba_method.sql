-- Add Vision Mamba (Vim) method, sourced from arXiv 2401.09417. The bare "Vim"
-- keyword is omitted: case-sensitive substring matching would hit Vimeo-90K
-- and other unrelated tokens.

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
    'vision-mamba',
    'Vision Mamba',
    'Vision Mamba (Vim)',
    'Vision Mamba (Vim) is a generic vision backbone that replaces the self-attention of a [Vision Transformer](/methods/vision-transformer) with bidirectional [Mamba](/methods/mamba) blocks. The image is split into patches, linearly projected and given position embeddings, with a class token inserted in the middle of the sequence. Each Vim block processes the token sequence both forward and backward with selective [state space models](/methods/state-space-models), so every token can gather global context while compute and memory grow linearly with sequence length. Vim outperformed DeiT on ImageNet classification, COCO detection and ADE20K segmentation, and at 1248x1248 resolution it ran 2.8 times faster and used 86.8% less GPU memory than DeiT for batch inference.',
    'Vision Mamba',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2024,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2401.09417'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Vision Mamba: Efficient Visual Representation Learning with Bidirectional State Space Model',
    'https://github.com/hustvl/Vim',
    NULL,
    '[Vision Mamba: Efficient Visual Representation Learning with Bidirectional State Space Model](/paper/2401.09417)'
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
WHERE slug = 'vision-mamba'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'vision-mamba'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
