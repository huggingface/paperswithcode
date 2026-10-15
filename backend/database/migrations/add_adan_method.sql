-- Add Adan method, introduced in arXiv 2208.06677. The source paper
-- gets the source evidence row (Introduced banner); citers are linked by
-- link_papers_by_source_citations.py and the hourly reference backfill.

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
    'adan',
    'Adan',
    'Adaptive Nesterov Momentum (Adan)',
    'Adan (Adaptive Nesterov Momentum) is a deep-learning optimizer that combines adaptive per-parameter learning rates, like [Adam](/methods/adam), with Nesterov acceleration. To avoid the extra cost of computing the gradient at an extrapolated point, it reformulates Nesterov momentum into a Nesterov momentum estimation that uses only the current and previous gradients, and it keeps exponential moving averages of the gradient, the gradient difference and the squared corrected gradient, together with decoupled [weight decay](/methods/weight-decay). Adan comes with a convergence guarantee for nonconvex stochastic problems that matches the known lower bound. Across ResNet, ConvNeXt, ViT, Swin, MAE, GPT-2, BERT and reinforcement-learning benchmarks it outperformed tuned optimizers such as [AdamW](/methods/adamw) and LAMB, and it reached comparable or better results with half the training epochs on several of them.',
    'Adan optimizer, adan, adaptive nesterov momentum',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2022,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2208.06677'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Adan: Adaptive Nesterov Momentum Algorithm for Faster Optimizing Deep Models',
    'https://github.com/sail-sg/Adan',
    NULL,
    '[Adan: Adaptive Nesterov Momentum Algorithm for Faster Optimizing Deep Models](/paper/2208.06677)'
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
WHERE slug = 'adan'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'adan'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
