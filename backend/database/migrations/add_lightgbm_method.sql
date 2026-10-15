-- Add LightGBM method, sourced from the NeurIPS 2017 paper (external paper
-- row, no arXiv id). The keyword is case-sensitive, so it only matches the
-- exact "LightGBM" spelling in titles and abstracts.

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
    'lightgbm',
    'LightGBM',
    'Light Gradient Boosting Machine (LightGBM)',
    'LightGBM is a gradient boosting decision tree (GBDT) framework designed for fast training on large, high-dimensional tabular data. It bins continuous features into histograms and grows trees leaf-wise, always splitting the leaf with the largest loss reduction instead of expanding a whole level at a time. Two techniques cut the cost of finding splits: Gradient-based One-Side Sampling (GOSS) keeps every instance with a large gradient and randomly samples those with small gradients, and Exclusive Feature Bundling (EFB) merges sparse features that rarely take nonzero values together. In the original experiments LightGBM trained conventional GBDT up to over 20 times faster with almost the same accuracy. Alongside XGBoost and CatBoost it is a standard strong baseline for tabular prediction, ranking, and Kaggle-style competitions.',
    'LightGBM, Light Gradient Boosting Machine',
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
        WHERE source = 'external'
          AND title = 'LightGBM: A Highly Efficient Gradient Boosting Decision Tree'
          AND is_latest_version
        ORDER BY id DESC
        LIMIT 1
    ),
    NULL,
    'LightGBM: A Highly Efficient Gradient Boosting Decision Tree',
    'https://github.com/microsoft/LightGBM/blob/master/src/treelearner/serial_tree_learner.cpp',
    NULL,
    '[LightGBM documentation](https://lightgbm.readthedocs.io/en/latest/Features.html)'
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
WHERE slug = 'lightgbm'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'lightgbm'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Curated 2026-10-15 from every title/abstract mention of "LightGBM": each
-- paper below trains, adapts or analyzes LightGBM models.
CREATE TEMP TABLE lightgbm_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lightgbm'
  AND p.is_latest_version
  AND p.id IN (
        2644, -- Application of Machine Learning in Forecasting International Trade Tre
        14412, -- Spam-T5: Benchmarking Large Language Models for Few-Shot Email Spam De
        15624, -- Generative Table Pre-training Empowers Models for Tabular Prediction
        18950, -- OBESEYE: Interpretable Diet Recommender for Obesity Management using M
        23067, -- Extending Machine Learning-Based Early Sepsis Detection to Different D
        25085, -- Comparative Evaluation of Anomaly Detection Methods for Fraud Detectio
        26709, -- Predicting ATP binding sites in protein sequences using Deep Learning
        30306, -- Machine learning and economic forecasting: the role of international t
        33770, -- Predicting the duration of traffic incidents for Sydney greater metrop
        35615, -- Advanced User Credit Risk Prediction Model using LightGBM, XGBoost and
        36362, -- Enhancing Customer Churn Prediction in Telecommunications: An Adaptive
        48079, -- QuaDMix: Quality-Diversity Balanced Data Selection for Efficient LLM P
        57902, -- An Integrated Framework for Explainable, Fair, and Observable Hospital
        59750, -- AI-Driven Predictive Maintenance with Real-Time Contextual Data Fusion
        63089, -- Australian Bushfire Intelligence with AI-Driven Environmental Analytic
        63098, -- Early-Stage Prediction of Review Effort in AI-Generated Pull Requests
        66015, -- Enhancing Diagnostic Accuracy for Urinary Tract Disease through Explai
        67348, -- CardioForest: An Explainable Ensemble Learning Model for Automatic Wid
        68877, -- AgroSense: An Integrated Deep Learning System for Crop Recommendation
        72980, -- Advancing Tabular Stroke Modelling Through a Novel Hybrid Architecture
        74967, -- A Wearable Device Dataset for Mental Health Assessment Using Laser Dop
        81749, -- TreeGrad: Transferring Tree Ensembles to Neural Networks
        82047, -- EMBER: An Open Dataset for Training Static PE Malware Machine Learning
        85637, -- When Feature Importance Lies: Target Encoding at the Noise Floor
        86853, -- Discretization-free Multicalibration through Loss Minimization over Tr
        93857, -- Boosted Trees on a Diet: Compact Models for Resource-Constrained Devic
        98917, -- Comparative Analysis of ML Approaches for Chronic Disease Prediction w
        113894 -- EarlyEval: Cheaper Agent Evaluation via Early Outcome Prediction
  );

DELETE FROM paper_method_exclusions x
USING lightgbm_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM lightgbm_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM lightgbm_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: LightGBM appears only as a comparison baseline.
CREATE TEMP TABLE lightgbm_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lightgbm'
  AND p.is_latest_version
  AND p.id IN (
        5856, -- SAINT: Improved Neural Networks for Tabular Data via Row Attention and
        9317, -- Hopular: Modern Hopfield Networks for Tabular Data
        43727 -- Contrastive Learning for Cold Start Recommendation with Adaptive Featu
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'LightGBM curation 2026-10-15: compares against LightGBM without using it'
FROM lightgbm_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING lightgbm_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING lightgbm_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
