-- Add Gradient Boosted Decision Trees (GBDT). Production chat users looked up
-- "GBDT" and "GDBT" on 2026-10-15/16. Friedman's 2001 Annals of Statistics
-- paper is the canonical reference but has no local paper row, and boosting
-- as functional gradient descent has precursors (AdaBoost, Breiman, Mason et
-- al.), so the method uses an external source URL and no source evidence.

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
    'gbdt',
    'Gradient Boosted Decision Trees',
    'Gradient Boosted Decision Trees (GBDT)',
    'Gradient boosted decision trees (GBDT) build a strong predictor as a sum of small regression trees, added one at a time. At each stage a new tree is fitted to the negative gradient of a differentiable loss with respect to the current predictions (the pseudo-residuals), its leaf values are set by a line search, and its output is added to the ensemble after scaling by a learning rate (shrinkage). Friedman''s gradient boosting machine (2001) framed boosting as gradient descent in function space, building on [AdaBoost](/methods/adaboost) and on Breiman''s and Mason et al.''s functional-gradient views of boosting. This extended boosting from exponential loss to squared, absolute, Huber and logistic losses, and stochastic gradient boosting (2002) added row subsampling. Modern implementations such as [XGBoost](/methods/xgboost), [LightGBM](/methods/lightgbm), [CatBoost](/methods/catboost) and scikit-learn''s HistGradientBoosting add second-order updates, histogram binning, regularization and categorical-feature handling. GBDTs remain a default for tabular data, usually stronger than a [random forest](/methods/random-forest), and are the main baseline that tabular deep learning and foundation models such as [TabPFN](/methods/tabpfn) are measured against.',
    'GBDT, GBDTs, GDBT, gradient boosted decision trees, gradient-boosted decision trees, gradient boosting decision tree, gradient boosting decision trees, gradient boosted decision tree, gradient boosted trees, gradient-boosted trees, gradient boosting trees, gradient boosting machine, gradient boosting machines, gradient boosted regression trees, multiple additive regression trees',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2001,
    NULL,
    'https://doi.org/10.1214/aos/1013203451',
    'Greedy Function Approximation: A Gradient Boosting Machine',
    'https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/ensemble/_gb.py',
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

-- Curated 2026-10-16 from every title/abstract mention of gradient boosting or
-- GBDT: each paper below trains, adapts, benchmarks or analyzes gradient
-- boosted trees.
CREATE TEMP TABLE gbdt_linked_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gbdt'
  AND p.is_latest_version
  AND p.id IN (
        2648, -- NGBoost: Natural Gradient Boosting for Probabilistic Prediction
        3010, -- Generalization of Change-Point Detection in Time Series Data Based on Di
        3877, -- Accuracy Prediction with Non-neural Model for Neural Architecture Search
        4155, -- Kaggle forecasting competitions: An overlooked learning opportunity
        5056, -- Evaluating the Performance of Some Local Optimizers for Variational Quan
        6046, -- Predicting Gender by First Name Using Character-level Machine Learning
        6128, -- Solar Irradiation Forecasting using Genetic Algorithms
        7766, -- A Classical Approach to Handcrafted Feature Extraction Techniques for Ba
        7925, -- Quantune: Post-training Quantization of Convolutional Neural Networks us
        8008, -- An Integrated Optimization and Machine Learning Models to Predict the Ad
        8556, -- Which Tricks Are Important for Learning to Rank?
        8895, -- Adapting and Evaluating Influence-Estimation Methods for Gradient-Booste
        9007, -- Machine Learning Workflow to Explain Black-box Models for Early Alzheime
        10312, -- FairGBM: Gradient Boosting with Fairness Constraints
        11635, -- Condensed Gradient Boosting
        15231, -- When Do Neural Nets Outperform Boosted Trees on Tabular Data?
        17349, -- Automating Microservices Test Failure Analysis using Kubernetes Cluster
        17945, -- Pricing European Options with Google AutoML, TensorFlow, and XGBoost
        18262, -- Real-time Traffic Classification for 5G NSA Encrypted Data Flows With Ph
        20156, -- Detecting Manufacturing Defects in PCBs via Data-Centric Machine Learnin
        20575, -- Generating and Imputing Tabular Data via Diffusion and Flow-based Gradie
        20817, -- The LHCb ultra-fast simulation option, Lamarr: design and validation
        25112, -- Noninvasive Estimation of Mean Pulmonary Artery Pressure Using MRI, Comp
        25610, -- TwinBooster: Synergising Large Language Models with Barlow Twins and Gra
        27299, -- Predicting User Experience on Laptops from Hardware Specifications
        31428, -- A Three-Phase Analysis of Synergistic Effects During Co-pyrolysis of Alg
        33770, -- Predicting the duration of traffic incidents for Sydney greater metropol
        33812, -- TabReD: Analyzing Pitfalls and Filling the Gaps in Tabular Deep Learning
        34280, -- Unmasking Trees for Tabular Data
        34469, -- Gradient Boosting Reinforcement Learning
        35402, -- Barlow Twins Deep Neural Network for Advanced 1D Drug-Target Interaction
        36372, -- Is text normalization relevant for classifying medieval charters?
        37878, -- NRGBoost: Energy-Based Generative Boosted Trees
        39486, -- Deep Learning Through A Telescoping Lens: A Simple Model Provides Empiri
        42225, -- Uncertainty quantification for improving radiomic-based models in radiat
        50949, -- Advancing Exchange Rate Forecasting: Leveraging Machine Learning and AI
        51307, -- TabArena: A Living Benchmark for Machine Learning on Tabular Data
        51309, -- A deep learning and machine learning approach to predict neonatal death
        57839, -- Trees to Flows and Back: Unifying Decision Trees and Diffusion Models
        62573, -- Intra-tree Column Subsampling Hinders XGBoost Learning of Ratio-like Int
        64807, -- iLTM: Integrated Large Tabular Model
        64808, -- Machine Learning vs. Randomness: Challenges in Predicting Binary Options
        66043, -- Advancing Drug Development Through Strategic Cell Line and Compound Sele
        66996, -- Tabular Data: Is Deep Learning all you need?
        68021, -- RAVEN: RAnking and Validation of ExoplaNets
        70382, -- Cross-Domain Web Information Extraction at Pinterest
        71110, -- Robust-Multi-Task Gradient Boosting
        71703, -- crypto price prediction using lstm+xgboost
        73833, -- FUSE : A Ridge and Random Forest-Based Metric for Evaluating MT in Indig
        75192, -- Better by Default: Strong Pre-Tuned MLPs and Boosted Trees on Tabular Da
        77005, -- Global Crop-Specific Fertilization Dataset from 1961-2019
        78161, -- On Gradient Boosted Decision Trees and Neural Rankers: A Case-Study on S
        78309, -- Enhancing Epileptic Seizure Detection with EEG Feature Embeddings
        78469, -- Can-SAVE: Deploying Low-Cost and Population-Scale Cancer Screening via S
        78510, -- A Hierarchy-based Analysis Approach for Blended Learning: A Case Study w
        78614, -- Real-time Detection of AI-Generated Speech for DeepFake Voice Conversion
        79981, -- High Performance of Gradient Boosting in Binding Affinity Prediction
        80294, -- Evaluating categorical encoding methods on a real credit card fraud dete
        80964, -- SOREL-20M: A Large Scale Benchmark Dataset for Malicious PE Detection
        81393, -- Deep learning for Stock Market Prediction
        81462, -- Regression-based music emotion prediction using triplet neural networks
        81749, -- TreeGrad: Transferring Tree Ensembles to Neural Networks
        82047, -- EMBER: An Open Dataset for Training Static PE Malware Machine Learning M
        82097, -- Predicting Customer Churn: Extreme Gradient Boosting with Temporal Data
        82216, -- CatBoost: unbiased boosting with categorical features
        83719, -- Exploring the Interpretability of Forecasting Models for Energy Balancin
        85151, -- BHCast: Unlocking Black Hole Plasma Dynamics from a Single Blurry Image
        86585, -- From Counterfactuals to Trees: Competitive Analysis of Model Extraction
        87313, -- Statistical Inference for Gradient Boosting Regression
        93734, -- Smooth Calibration Error: Uniform Convergence and Functional Gradient An
        95122, -- Generalization of Runoff Risk Prediction at Field Scales to a Continenta
        98319, -- When is Your LLM Steerable?
        101185, -- SurrogateSHAP: Training-Free Contributor Attribution for Text-to-Image (
        107209, -- Robust Watermarking on Gradient Boosting Decision Trees
        109262, -- LightGBM: A Highly Efficient Gradient Boosting Decision Tree
        109263, -- ChimeraBoost
        109268, -- PerpetualBooster
        109478, -- A prediction and behavioural analysis of machine learning methods for mo
        123583 -- AI-Driven, Timing-Aware Power Optimization
  );

DELETE FROM paper_method_exclusions x
USING gbdt_linked_papers l
WHERE x.paper_id = l.paper_id AND x.method_id = l.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gbdt_linked_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM gbdt_linked_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: gradient boosting appears only as motivation or a
-- comparison baseline, refers to boosting neural networks, or GBRT means
-- gradient-based red teaming.
CREATE TEMP TABLE gbdt_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gbdt'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        570, 2602, 3112, 3985, 5600, 5856, 8651, 9317, 12338, 13251, 13509, 18671,
        21077, 21678, 26290, 26457, 27141, 28348, 30214, 35759, 37988, 43877, 49061, 49576,
        54067, 57860, 58559, 60229, 60819, 62989, 64385, 68768, 69623, 73617, 78319, 80648,
        81610, 81619, 94657, 98209, 100193, 101130, 109244
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'gbdt curation 2026-10-16: mentions gradient boosting only as context or a baseline, or boosts neural networks rather than trees'
FROM gbdt_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING gbdt_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING gbdt_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
