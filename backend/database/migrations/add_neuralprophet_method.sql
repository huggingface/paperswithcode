-- Add NeuralProphet method, introduced in arXiv 2111.15397. The source paper
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
    'neuralprophet',
    'NeuralProphet',
    'NeuralProphet',
    'NeuralProphet is an explainable time series forecasting framework and the neural successor to Facebook Prophet. Like Prophet, it decomposes a forecast into interpretable components: a piecewise-linear trend, Fourier-term seasonalities, events and holidays, and future regressors. It adds auto-regression through AR-Net and lagged covariates, each optionally modeled by a small feed-forward network, and it is implemented in PyTorch and trained with mini-batch gradient descent. On a range of datasets, adding the auto-regressive components improved short- to medium-term forecast accuracy by 55-92% over Prophet while keeping the model''s components interpretable and its interface familiar to forecasting practitioners.',
    'NeuralProphet',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2111.15397'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'NeuralProphet: Explainable Forecasting at Scale',
    'https://github.com/ourownstory/neural_prophet',
    NULL,
    '[NeuralProphet: Explainable Forecasting at Scale](/paper/2111.15397)'
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
WHERE slug = 'neuralprophet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'neuralprophet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
