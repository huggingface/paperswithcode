-- Add Attention U-Net method, sourced from arXiv 1804.03999.

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
    'attention-u-net',
    'Attention U-Net',
    'Attention U-Net',
    'Attention U-Net adds attention gates to the skip connections of a [U-Net](/methods/u-net) for medical image segmentation. Each additive attention gate uses the coarser features of the decoder as a gating signal to compute per-pixel attention coefficients for the encoder features arriving through the [skip connection](/methods/skip-connection), suppressing responses from irrelevant background and highlighting the target structure before concatenation. The gates are trained with the rest of the network and add little computation, which removes the need for separate organ localization models in cascaded pipelines. On abdominal CT pancreas segmentation it consistently improved over the standard U-Net, and attention gates became a common building block in medical segmentation networks.',
    'Attention U-Net, Attention UNet, AttU-Net',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1804.03999'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Attention U-Net: Learning Where to Look for the Pancreas',
    'https://github.com/ozan-oktay/Attention-Gated-Networks',
    NULL,
    '[Attention U-Net: Learning Where to Look for the Pancreas](/paper/1804.03999)'
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
WHERE slug = 'attention-u-net'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'attention-u-net'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
