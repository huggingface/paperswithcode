-- Add SegFormer method, sourced from arXiv 2105.15203.

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
    'segformer',
    'SegFormer',
    'SegFormer',
    'SegFormer is a semantic segmentation framework that pairs a hierarchical [Transformer](/methods/transformer) encoder, the Mix Transformer (MiT), with a lightweight all-MLP decoder. The encoder uses overlapping patch embeddings, efficient self-attention with a reduced key/value sequence, and Mix-FFN blocks whose 3x3 depthwise convolution leaks positional information, so no positional encodings are needed and accuracy holds when the test resolution differs from training. It outputs features at 1/4 to 1/32 resolution, and the decoder projects each to a common width with MLP layers, upsamples, concatenates and fuses them into the mask. SegFormer-B4 reached 50.3% mIoU on ADE20K with 64M parameters, and SegFormer-B5 reached 84.0% mIoU on Cityscapes val while staying robust under the corruptions of Cityscapes-C. Compared with [Vision Transformer](/methods/vision-transformer) segmenters such as SETR, it is smaller, faster and has no heavy decoder.',
    'SegFormer',
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
        WHERE arxiv_id = '2105.15203'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'SegFormer: Simple and Efficient Design for Semantic Segmentation with Transformers',
    'https://github.com/NVlabs/SegFormer/blob/master/mmseg/models/backbones/mix_transformer.py',
    NULL,
    '[SegFormer: Simple and Efficient Design for Semantic Segmentation with Transformers](/paper/2105.15203)'
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
WHERE slug = 'segformer'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'segformer'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
