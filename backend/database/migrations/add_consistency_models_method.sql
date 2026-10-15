-- Add Consistency Models method, sourced from arXiv 2303.01469.

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
    'consistency-models',
    'Consistency Models',
    'Consistency Models',
    'Consistency models are generative models that map any point on the trajectory of a probability flow ODE directly back to the trajectory''s origin, the clean data point. This self-consistency property allows high-quality generation in a single network evaluation, while optional multistep sampling alternates denoising and re-noising to trade compute for quality. They can be trained by consistency distillation from a pretrained [diffusion](/methods/diffusion) model or by consistency training as a standalone model without any teacher. In the original work, consistency distillation achieved one-step FID of 3.55 on CIFAR-10 and 6.20 on ImageNet 64x64, and the models support zero-shot editing such as inpainting, colorization and super-resolution. Latent consistency models and later consistency-based distillation methods built on this idea to speed up text-to-image diffusion.',
    'consistency model, consistency distillation',
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
        WHERE arxiv_id = '2303.01469'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Consistency Models',
    'https://github.com/openai/consistency_models',
    NULL,
    '[Consistency Models](/paper/2303.01469)'
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
WHERE slug = 'consistency-models'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'consistency-models'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
