-- Add ResMLP method, sourced from arXiv 2105.03404.

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
    'resmlp',
    'ResMLP',
    'ResMLP',
    'ResMLP is an image classification architecture built entirely from multi-layer perceptrons. Like a [Vision Transformer](/methods/vision-transformer) it splits the image into patches and projects them linearly, but each residual block replaces self-attention with a single linear layer in which patches interact, applied identically to every channel, followed by a two-layer [feed-forward network](/methods/feedforward-network) applied independently to each patch. A simple per-channel affine transformation replaces [layer normalization](/methods/layer-normalization), which keeps training stable. Trained with the DeiT recipe of heavy data augmentation and optionally [distillation](/methods/knowledge-distillation), ResMLP reaches a competitive accuracy and complexity trade-off on ImageNet using only ImageNet-1k, and the same design works for self-supervised learning and machine translation. With the concurrent MLP-Mixer it showed that attention is not essential for strong vision models.',
    'ResMLP',
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
        WHERE arxiv_id = '2105.03404'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'ResMLP: Feedforward networks for image classification with data-efficient training',
    'https://github.com/facebookresearch/deit/blob/main/resmlp_models.py',
    NULL,
    '[ResMLP: Feedforward networks for image classification with data-efficient training](/paper/2105.03404)'
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
WHERE slug = 'resmlp'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'resmlp'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
