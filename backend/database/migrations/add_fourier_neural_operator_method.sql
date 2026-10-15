-- Add Fourier Neural Operator method, introduced in arXiv 2010.08895. The source paper
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
    'fourier-neural-operator',
    'Fourier Neural Operator',
    'Fourier Neural Operator (FNO)',
    'The Fourier Neural Operator (FNO) learns a mapping between infinite-dimensional function spaces, such as from the initial condition or coefficient field of a partial differential equation to its solution, instead of solving one instance at a time. Each Fourier layer applies a fast Fourier transform, multiplies a truncated set of low-frequency modes by learned complex weights, transforms back, and adds a pointwise linear path before a nonlinearity. Because the learned weights live in Fourier space, a trained FNO can be evaluated at resolutions it was not trained on (zero-shot super-resolution). On Burgers, Darcy flow and Navier-Stokes benchmarks it outperformed earlier neural-network solvers and ran up to three orders of magnitude faster than traditional PDE solvers. FNO is the best-known neural operator and is used for weather, climate and fluid-dynamics surrogates; it is often compared with [Physics-Informed Neural Networks](/methods/physics-informed-neural-networks).',
    'fourier neural operator, FNO, neural operator',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2020,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2010.08895'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Fourier Neural Operator for Parametric Partial Differential Equations',
    'https://github.com/neuraloperator/neuraloperator',
    NULL,
    '[Fourier Neural Operator for Parametric Partial Differential Equations](/paper/2010.08895)'
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
WHERE slug = 'fourier-neural-operator'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'fourier-neural-operator'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
