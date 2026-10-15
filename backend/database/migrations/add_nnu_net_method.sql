-- Add nnU-Net method, sourced from arXiv 1809.10486.

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
    'nnu-net',
    'nnU-Net',
    'no-new-U-Net (nnU-Net)',
    'nnU-Net ("no-new-Net") is a self-configuring framework for biomedical image segmentation built around the plain [U-Net](/methods/u-net). Instead of proposing a new architecture, it derives the whole pipeline from the properties of each dataset: resampling and normalization, patch and batch size, network topology, and the choice among a 2D U-Net, a 3D U-Net and a two-stage 3D U-Net cascade. Training uses a combined [Dice](/methods/dice-loss) and cross-entropy loss with heavy data augmentation, and the best configuration or ensemble is selected by cross-validation, followed by optional connected-component post-processing. Without manual tuning, nnU-Net achieved the top average score in the Medical Segmentation Decathlon, and it remains the default baseline for medical segmentation challenges.',
    'nnU-Net, nnUNet',
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
        WHERE arxiv_id = '1809.10486'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'nnU-Net: Self-adapting Framework for U-Net-Based Medical Image Segmentation',
    'https://github.com/MIC-DKFZ/nnUNet',
    NULL,
    '[nnU-Net: Self-adapting Framework for U-Net-Based Medical Image Segmentation](/paper/1809.10486)'
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
WHERE slug = 'nnu-net'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'nnu-net'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
