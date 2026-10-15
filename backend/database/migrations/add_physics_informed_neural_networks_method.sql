-- Add Physics-Informed Neural Networks method, introduced in arXiv 1711.10561. The source paper
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
    'physics-informed-neural-networks',
    'Physics-Informed Neural Networks',
    'Physics-Informed Neural Networks (PINNs)',
    'Physics-Informed Neural Networks (PINNs) are neural networks trained to satisfy both observed data and the governing equations of a physical system. The network represents the unknown solution of a partial differential equation, and automatic differentiation evaluates the PDE residual at collocation points, so the loss combines a data or boundary-condition term with a physics term that penalizes violations of the equation. The same setup handles forward problems (data-driven solution) and inverse problems (data-driven discovery of unknown PDE coefficients, in the companion Part II paper), and was demonstrated on the Burgers, Schrödinger and Allen-Cahn equations. Earlier work by Lagaris et al. (1998) already trained neural networks to solve differential equations; Raissi, Perdikaris and Karniadakis named and popularized the physics-informed formulation. PINNs are a common baseline for scientific machine learning alongside operator-learning approaches such as the [Fourier Neural Operator](/methods/fourier-neural-operator).',
    'physics-informed neural network, physics informed neural network, PINN',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2017,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1711.10561'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Physics Informed Deep Learning (Part I): Data-driven Solutions of Nonlinear Partial Differential Equations',
    'https://github.com/maziarraissi/PINNs',
    NULL,
    '[Physics Informed Deep Learning (Part I): Data-driven Solutions of Nonlinear Partial Differential Equations](/paper/1711.10561)'
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
WHERE slug = 'physics-informed-neural-networks'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'physics-informed-neural-networks'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
