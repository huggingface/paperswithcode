-- Add BiRefNet method, sourced from arXiv 2401.03407.

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
    'birefnet',
    'BiRefNet',
    'Bilateral Reference Network (BiRefNet)',
    'BiRefNet is a segmentation network for high-resolution dichotomous image segmentation (DIS), the task of extracting very fine-grained foreground objects such as wire frames, hair or lattices. A localization module built on a [Transformer](/methods/transformer) encoder captures global semantics, and a reconstruction module recovers detail with bilateral reference: inward reference feeds multi-scale patches of the original high-resolution image into the decoder blocks, while outward reference uses gradient maps as auxiliary supervision so the network attends to areas rich in fine detail. Auxiliary classification and multi-stage supervision speed up training. BiRefNet set new state-of-the-art results on DIS5K and on high-resolution salient and camouflaged object detection benchmarks, and is widely used for background removal and image matting.',
    'BiRefNet',
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
        WHERE arxiv_id = '2401.03407'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Bilateral Reference for High-Resolution Dichotomous Image Segmentation',
    'https://github.com/ZhengPeng7/BiRefNet',
    NULL,
    '[Bilateral Reference for High-Resolution Dichotomous Image Segmentation](/paper/2401.03407)'
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
WHERE slug = 'birefnet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'birefnet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
