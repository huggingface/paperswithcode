-- Add Anomaly Transformer method, introduced in arXiv 2110.02642. The source paper
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
    'anomaly-transformer',
    'Anomaly Transformer',
    'Anomaly Transformer',
    'Anomaly Transformer is an unsupervised model for detecting anomalies in multivariate time series. Its Anomaly-Attention block computes two associations for every time point: a prior association, a learnable Gaussian kernel over relative temporal distance that favors adjacent points, and a series association given by ordinary self-attention weights. Normal points can associate with informative points across the whole series, whereas anomalies tend to concentrate on their neighbors, so the association discrepancy between the two distributions is a distinguishable criterion. A minimax training strategy amplifies this discrepancy, and the anomaly score combines it with the reconstruction error. Anomaly Transformer reported state-of-the-art results on six benchmarks spanning service monitoring, space and earth exploration, and water treatment.',
    'Anomaly Transformer',
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
        WHERE arxiv_id = '2110.02642'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Anomaly Transformer: Time Series Anomaly Detection with Association Discrepancy',
    'https://github.com/thuml/Anomaly-Transformer',
    NULL,
    '[Anomaly Transformer: Time Series Anomaly Detection with Association Discrepancy](/paper/2110.02642)'
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
WHERE slug = 'anomaly-transformer'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'anomaly-transformer'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
