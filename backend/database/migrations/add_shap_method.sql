-- Add SHAP method, introduced in arXiv 1705.07874. The source paper
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
    'shap',
    'SHAP',
    'SHapley Additive exPlanations (SHAP)',
    'SHAP (SHapley Additive exPlanations) explains an individual prediction by assigning each input feature an importance value equal to its Shapley value from cooperative game theory: the feature''s average marginal contribution to the model output over all subsets of the other features. The paper frames explanation methods as additive feature attribution models and shows that Shapley values are the unique attribution satisfying local accuracy, missingness and consistency, unifying earlier methods such as LIME, DeepLIFT and layer-wise relevance propagation. Because exact Shapley values are exponential to compute, it introduced model-agnostic Kernel SHAP and the Deep SHAP approximation for neural networks; later work added the exact polynomial-time TreeSHAP for tree ensembles such as [XGBoost](/methods/xgboost) and [LightGBM](/methods/lightgbm). SHAP values and the accompanying `shap` library are a standard tool for global and local interpretability in tabular, vision and text models.',
    'shapley additive explanations, SHAP value, SHAP-based, SHAP analysis, KernelSHAP, Kernel SHAP, TreeSHAP, DeepSHAP, Deep SHAP',
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
        WHERE arxiv_id = '1705.07874'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'A Unified Approach to Interpreting Model Predictions',
    'https://github.com/shap/shap',
    NULL,
    '[A Unified Approach to Interpreting Model Predictions](/paper/1705.07874)'
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
WHERE slug = 'shap'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'shap'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 67 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention SHAP are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE shap_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'shap'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        56296, 56550, 56962, 57651, 57763, 57916, 58950, 59572, 60262, 83408, 83542, 83657,
        83762, 85151, 85211, 85278, 85520, 92524, 92879, 93467, 93483, 94923, 98459, 98840,
        99054, 99288, 99440, 100021, 101172, 101310, 101903, 102450, 102872, 102974, 103378, 103481,
        103651, 104582, 106137, 108992, 109118, 109528, 109702, 112990, 117437, 119074, 119153, 122759,
        122779, 122820
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'shap citation review 2026-10-15: cites the source paper without using the method'
FROM shap_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING shap_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING shap_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
