-- Add AdaBoost method. Its introducing paper (Freund & Schapire, EuroCOLT
-- 1995; JCSS 1997) has no local paper row, so the source is its DOI and
-- source_paper_id stays NULL.

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
    'adaboost',
    'AdaBoost',
    'Adaptive Boosting (AdaBoost)',
    'AdaBoost (Adaptive Boosting) builds a strong classifier as a weighted vote of weak learners, typically decision stumps, trained one after another. After each round it increases the weights of the training examples the current learner misclassified, so the next learner focuses on the hard cases, and it weights each learner by its accuracy. AdaBoost was the first practical boosting algorithm: Freund and Schapire proved that it drives training error down exponentially fast whenever each weak learner beats random guessing, and it was later shown to minimize the exponential loss by stagewise additive modeling. That view led to gradient boosting, the basis of [XGBoost](/methods/xgboost), [LightGBM](/methods/lightgbm) and [CatBoost](/methods/catboost). AdaBoost also powered the Viola-Jones face detector, and it is a common contrast to bagging-based [Random Forests](/methods/random-forest).',
    'AdaBoost, Adaboost',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    1995,
    NULL,
    'https://doi.org/10.1006/jcss.1997.1504',
    'A Decision-Theoretic Generalization of On-Line Learning and an Application to Boosting',
    'https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/ensemble/_weight_boosting.py',
    NULL,
    NULL
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
WHERE slug = 'adaboost'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'adaboost'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Curated 2026-10-15 from every title/abstract mention of "AdaBoost": each paper
-- below trains, adapts, benchmarks or analyzes AdaBoost models.
CREATE TEMP TABLE adaboost_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'adaboost'
  AND p.is_latest_version
  AND p.id IN (
        5254, -- The Success of AdaBoost and Its Application in Portfolio Management
        8008, -- An Integrated Optimization and Machine Learning Models to Predict the
        12059, -- PromptBoosting: Black-Box Text Classification with Ten Forward Passes
        12580, -- AdaBoost is not an Optimal Weak to Strong Learner
        14205, -- Predicting Thermoelectric Power Factor of Bismuth Telluride During Las
        75913, -- DiabML: AI-assisted diabetes diagnosis method with meta-heuristic-base
        81393, -- Deep learning for Stock Market Prediction
        82226, -- AFIF4: Deep Gender Classification based on AdaBoost-based Fusion of Is
        82650, -- An Introduction to Artificial Prediction Markets for Classification
        104703, -- Feature-based head pose estimation from images
        111667, -- Accessible Real-time Eye-gaze Tracking for Neurocognitive Health Asses
        119582 -- AdaBoosting Text Prompts for Vision-Language Models
  );

DELETE FROM paper_method_exclusions x
USING adaboost_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM adaboost_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM adaboost_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: AdaBoost appears only as a comparison baseline.
CREATE TEMP TABLE adaboost_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'adaboost'
  AND p.is_latest_version
  AND p.id IN (
        30214 -- From Words to Numbers: Your Large Language Model Is Secretly A Capable
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'AdaBoost curation 2026-10-15: compares against AdaBoost without using it'
FROM adaboost_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING adaboost_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING adaboost_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
