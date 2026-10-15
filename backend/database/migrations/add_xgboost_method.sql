-- Add XGBoost method, sourced from arXiv 1603.02754. The keyword is
-- case-sensitive, so it only matches the exact "XGBoost" spelling.

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
    'xgboost',
    'XGBoost',
    'eXtreme Gradient Boosting (XGBoost)',
    'XGBoost is a scalable gradient boosting decision tree (GBDT) system for tabular data. Each new tree is fit with a second-order (Newton) approximation of the loss, and the objective adds L1/L2 penalties on leaf weights and a per-leaf cost that regularize tree complexity. Systems contributions made it fast enough for large datasets: a sparsity-aware split finder that learns a default direction for missing values, a weighted quantile sketch for approximate split proposals, and a cache-aware, column-block layout that supports parallel, out-of-core and distributed training. XGBoost was used in 17 of the 29 winning Kaggle solutions in 2015, and with [LightGBM](/methods/lightgbm) and [CatBoost](/methods/catboost) it remains the standard strong baseline that tabular deep learning models are compared against.',
    'XGBoost, eXtreme Gradient Boosting',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2016,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1603.02754'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'XGBoost: A Scalable Tree Boosting System',
    'https://github.com/dmlc/xgboost/blob/master/src/tree/updater_approx.cc',
    NULL,
    '[XGBoost: A Scalable Tree Boosting System](/paper/1603.02754)'
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
WHERE slug = 'xgboost'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'xgboost'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Curated 2026-10-15 from every title/abstract mention of "XGBoost": each paper
-- below trains, adapts, benchmarks or analyzes XGBoost models.
CREATE TEMP TABLE xgboost_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'xgboost'
  AND p.id IN (
        1622, -- Predicting thermoelectric properties from crystal graphs and material
        2644, -- Application of Machine Learning in Forecasting International Trade Tre
        3661, -- Experiments on Paraphrase Identification Using Quora Question Pairs Da
        4635, -- Short-Term Flow-Based Bandwidth Forecasting using Machine Learning
        5897, -- Tabular Data: Deep Learning is Not All You Need
        9007, -- Machine Learning Workflow to Explain Black-box Models for Early Alzhei
        11235, -- Prediction of superconducting properties of materials based on machine
        11987, -- FreCDo: A Large Corpus for French Cross-Domain Dialect Identification
        15264, -- Training Natural Language Processing Models on Encrypted Text for Enha
        17329, -- Izindaba-Tindzaba: Machine learning news categorisation for Long and S
        17945, -- Pricing European Options with Google AutoML, TensorFlow, and XGBoost
        18950, -- OBESEYE: Interpretable Diet Recommender for Obesity Management using M
        20156, -- Detecting Manufacturing Defects in PCBs via Data-Centric Machine Learn
        20575, -- Generating and Imputing Tabular Data via Diffusion and Flow-based Grad
        20951, -- Balancing Computational Efficiency and Forecast Error in Machine Learn
        23067, -- Extending Machine Learning-Based Early Sepsis Detection to Different D
        25387, -- Evaluating the Fairness of the MIMIC-IV Dataset and a Baseline Algorit
        26447, -- Credit Risk Meets Large Language Models: Building a Risk Indicator fro
        29713, -- Leveraging Corpus Metadata to Detect Template-based Translation: An Ex
        30306, -- Machine learning and economic forecasting: the role of international t
        33770, -- Predicting the duration of traffic incidents for Sydney greater metrop
        34219, -- PhishNet: A Phishing Website Detection Tool using XGBoost
        35615, -- Advanced User Credit Risk Prediction Model using LightGBM, XGBoost and
        36344, -- Scaling Up Diffusion and Flow-based XGBoost Models
        36362, -- Enhancing Customer Churn Prediction in Telecommunications: An Adaptive
        36551, -- Large Language Models versus Classical Machine Learning: Performance i
        37038, -- Towards Interpretable End-Stage Renal Disease (ESRD) Prediction: Utili
        37878, -- NRGBoost: Energy-Based Generative Boosted Trees
        38855, -- Testing the Efficacy of Hyperparameter Optimization Algorithms in Shor
        39340, -- Embedding-based classifiers can detect prompt injection attacks
        39412, -- Can Models Help Us Create Better Models? Evaluating LLMs as Data Scien
        39800, -- Machine learning-driven Anomaly Detection and Forecasting for Euclid S
        39848, -- ClinicalBench: Can LLMs Beat Traditional ML Models in Clinical Predict
        42923, -- Cueless EEG imagined speech for subject identification: dataset and be
        48581, -- Benchmarking Traditional Machine Learning and Deep Learning Models for
        48859, -- IISE PG&E Energy Analytics Challenge 2025: Hourly-Binned Regression Mo
        51168, -- LTRR: Learning To Rank Retrievers for LLMs
        51309, -- A deep learning and machine learning approach to predict neonatal deat
        57902, -- An Integrated Framework for Explainable, Fair, and Observable Hospital
        59204, -- Detecting the Machine: A Comprehensive Benchmark of AI-Generated Text
        62573, -- Intra-tree Column Subsampling Hinders XGBoost Learning of Ratio-like I
        63060, -- Unveiling the Heart-Brain Connection: An Analysis of ECG in Cognitive
        63089, -- Australian Bushfire Intelligence with AI-Driven Environmental Analytic
        63492, -- From Coverage to Causes: Data-Centric Fuzzing for JavaScript Engines
        66015, -- Enhancing Diagnostic Accuracy for Urinary Tract Disease through Explai
        67348, -- CardioForest: An Explainable Ensemble Learning Model for Automatic Wid
        68403, -- Tabular Data with Class Imbalance: Predicting Electric Vehicle Crash S
        68511, -- An Information-Theoretic Framework for Credit Risk Modeling: Unifying
        68877, -- AgroSense: An Integrated Deep Learning System for Crop Recommendation
        70382, -- Cross-Domain Web Information Extraction at Pinterest
        71703, -- crypto price prediction using lstm+xgboost
        72924, -- Guarded Query Routing for Large Language Models
        72980, -- Advancing Tabular Stroke Modelling Through a Novel Hybrid Architecture
        73861, -- Asset price movement prediction using empirical mode decomposition and
        74303, -- A Binary Classification Social Network Dataset for Graph Machine Learn
        75839, -- Explainable AI through a Democratic Lens: DhondtXAI for Proportional F
        76443, -- HULLMI: Human vs LLM identification with explainability
        77815, -- Intelligent Diagnosis of Alzheimer's Disease Based on Machine Learning
        77940, -- AntiPhishStack: LSTM-based Stacked Generalization Model for Optimized
        78003, -- SwitchTab: Switched Autoencoders Are Effective Tabular Learners
        79840, -- Why do tree-based models still outperform deep learning on tabular dat
        81393, -- Deep learning for Stock Market Prediction
        81429, -- Machine Learning Framework for RF-Based Drone Detection and Identifica
        82097, -- Predicting Customer Churn: Extreme Gradient Boosting with Temporal Dat
        83719, -- Exploring the Interpretability of Forecasting Models for Energy Balanc
        85878, -- Regression-adjusted Monte Carlo Estimators for Shapley Values and Prob
        89279, -- MixMin: Finding Data Mixtures via Convex Minimization
        91880, -- MixMax: Distributional Robustness in Function Space via Optimal Data M
        96602, -- Estimating Human Muscular Fatigue in Dynamic Collaborative Robotic Tas
        98917, -- Comparative Analysis of ML Approaches for Chronic Disease Prediction w
        104110, -- Wearable Sensor-Based IoT XAI Framework for Predicting Freezing of Gai
        104381, -- Benchmarking Sensor Robustness in Plasma Diagnostic Models: A Systemat
        111199 -- Predicting Adolescent Suicidal Risk from Multi-task-based Speech: An E
  );

DELETE FROM paper_method_exclusions x
USING xgboost_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM xgboost_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM xgboost_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: XGBoost appears only as a comparison baseline.
CREATE TEMP TABLE xgboost_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'xgboost'
  AND p.id IN (
        5856, -- SAINT: Improved Neural Networks for Tabular Data via Row Attention and
        9317, -- Hopular: Modern Hopfield Networks for Tabular Data
        10063, -- FOLD-SE: An Efficient Rule-based Machine Learning Algorithm with Scala
        14523, -- HyperTab: Hypernetwork Approach for Deep Learning on Small Tabular Dat
        21426, -- UniPredict: Large Language Models are Universal Tabular Classifiers
        23050, -- Wearable data from subjects playing Super Mario, sitting university ex
        24939, -- Labrador: Exploring the Limits of Masked Language Modeling for Laborat
        27141, -- Generative Nowcasting of Marine Fog Visibility in the Grand Banks area
        33193, -- Large Scale Transfer Learning for Tabular Data via Language Modeling
        36709, -- Developing an Explainable Artificial Intelligent (XAI) Model for Predi
        49586, -- Interpretable Multi-Task PINN for Emotion Recognition and EDA Predicti
        51634, -- FinAI-BERT: A Transformer-Based Model for Sentence-Level Detection of
        52521, -- DrugReasoner: Interpretable Drug Approval Prediction with a Reasoning-
        58475, -- CoGate-LSTM: Prototype-Guided Feature-Space Gating for Mitigating Grad
        65145, -- TabPFN-2.5: Advancing the State of the Art in Tabular Foundation Model
        72229, -- TabFlex: Scaling Tabular Learning to Millions with Linear Attention
        76354, -- Location based Probabilistic Load Forecasting of EV Charging Sites: De
        100041, -- STAND: Self-Aware Precondition Induction for Interactive Task Learning
        103842, -- TempusBench: An Evaluation Framework for Time-Series Forecasting
        111472 -- Automated evaluation of children's speech fluency for low-resource lan
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'XGBoost curation 2026-10-15: compares against XGBoost without using it'
FROM xgboost_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING xgboost_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING xgboost_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
