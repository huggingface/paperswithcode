-- Add CycleGAN method, sourced from arXiv 1703.10593.

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
    'cyclegan',
    'CycleGAN',
    'Cycle-Consistent Adversarial Network (CycleGAN)',
    'CycleGAN learns image-to-image translation between two domains without paired training examples. It trains two generators, G: X to Y and F: Y to X, each with an adversarial discriminator in the target domain as in a [GAN](/methods/gan). Because the adversarial loss alone does not tie a specific input to a specific output, CycleGAN adds a cycle-consistency loss requiring F(G(x)) to reconstruct x and G(F(y)) to reconstruct y, and optionally an identity loss to preserve colour. The method made unpaired translation practical for style transfer (photos to Monet or Van Gogh), object transfiguration (horses to zebras), season transfer and photo enhancement, and cycle-consistency became a common ingredient in domain adaptation and unpaired translation.',
    'CycleGAN, cycle-consistent adversarial network, cycle-consistent adversarial networks',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2017,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1703.10593'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Unpaired Image-to-Image Translation using Cycle-Consistent Adversarial Networks',
    'https://github.com/junyanz/pytorch-CycleGAN-and-pix2pix/blob/master/models/cycle_gan_model.py',
    NULL,
    '[Unpaired Image-to-Image Translation using Cycle-Consistent Adversarial Networks](/paper/1703.10593)'
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
WHERE slug = 'cyclegan'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'cyclegan'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
