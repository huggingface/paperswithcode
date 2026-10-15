-- Add CatBoost method, sourced from arXiv 1706.09516. The keyword is
-- case-sensitive, so it only matches the exact "CatBoost" spelling.

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
    'catboost',
    'CatBoost',
    'CatBoost',
    'CatBoost is a gradient boosting decision tree (GBDT) library that targets two sources of prediction shift in standard boosting. Ordered boosting computes each example''s gradient with a model that has not seen that example, using random permutations of the training set, which removes the bias that comes from reusing the same data to estimate gradients and fit trees. Ordered target statistics encode categorical features with running averages of the target over preceding examples in a permutation, avoiding the target leakage of naive target encoding, and CatBoost also builds combinations of categorical features greedily. Trees are oblivious (symmetric), using the same split at every node of a level, which makes inference fast. CatBoost outperformed [XGBoost](/methods/xgboost) and [LightGBM](/methods/lightgbm) on a range of benchmarks in the original paper and is a common default for data with many categorical features.',
    'CatBoost',
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
        WHERE arxiv_id = '1706.09516'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'CatBoost: unbiased boosting with categorical features',
    'https://github.com/catboost/catboost',
    NULL,
    '[CatBoost: unbiased boosting with categorical features](/paper/1706.09516)'
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
WHERE slug = 'catboost'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'catboost'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Curated 2026-10-15 from every title/abstract mention of "CatBoost": each paper
-- below trains, adapts, benchmarks or analyzes CatBoost models.
CREATE TEMP TABLE catboost_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'catboost'
  AND p.id IN (
        3661, -- Experiments on Paraphrase Identification Using Quora Question Pairs Da
        9103, -- All You Need Is Logs: Improving Code Completion by Learning from Anony
        66015, -- Enhancing Diagnostic Accuracy for Urinary Tract Disease through Explai
        75839 -- Explainable AI through a Democratic Lens: DhondtXAI for Proportional F
  );

DELETE FROM paper_method_exclusions x
USING catboost_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM catboost_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM catboost_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: CatBoost appears only as a comparison baseline.
CREATE TEMP TABLE catboost_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'catboost'
  AND p.id IN (
        5856, -- SAINT: Improved Neural Networks for Tabular Data via Row Attention and
        9317, -- Hopular: Modern Hopfield Networks for Tabular Data
        27464, -- TuneTables: Context Optimization for Scalable Prior-Data Fitted Networ
        36709, -- Developing an Explainable Artificial Intelligent (XAI) Model for Predi
        43877 -- TabICL: A Tabular Foundation Model for In-Context Learning on Large Da
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'CatBoost curation 2026-10-15: compares against CatBoost without using it'
FROM catboost_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING catboost_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING catboost_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
