-- Add Spectral Normalization method, sourced from arXiv 1802.05957.

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
    'spectral-normalization',
    'Spectral Normalization',
    'Spectral Normalization',
    'Spectral normalization is a weight normalization technique that divides each layer''s weight matrix by its spectral norm, its largest singular value, so that every layer and hence the whole network is constrained to be 1-Lipschitz. The spectral norm is estimated cheaply with a single step of power iteration per training update, reusing the singular vector from the previous step. Applied to the discriminator of a [GAN](/methods/gan), it stabilizes training without the extra cost of a gradient penalty and with little hyperparameter tuning, and unlike weight clipping or weight normalization it does not collapse the rank of the weights. SN-GANs matched or beat WGAN-GP and weight normalization on CIFAR-10 and STL-10 and generated 128x128 ImageNet images across all 1000 classes. It is now a standard component in GAN discriminators, including [BigGAN](/methods/biggan), and in other models that need Lipschitz control.',
    'spectral normalization, spectrally normalized, SN-GAN, SNGAN',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1802.05957'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Spectral Normalization for Generative Adversarial Networks',
    'https://github.com/pfnet-research/sngan_projection/blob/master/source/links/sn_linear.py',
    NULL,
    '[Spectral Normalization for Generative Adversarial Networks](/paper/1802.05957)'
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
WHERE slug = 'spectral-normalization'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'spectral-normalization'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
