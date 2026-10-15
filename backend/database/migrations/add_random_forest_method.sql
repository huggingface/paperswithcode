-- Add Random Forest method, sourced from Breiman's 2001 "Random Forests"
-- external paper row. Ho's 1995 random decision forests are credited in the
-- description as the precursor; Breiman named and formalized the method.

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
    'random-forest',
    'Random Forest',
    'Random Forest',
    'A random forest is an ensemble of decision trees, each trained on a bootstrap sample of the data (bagging) and restricted to a random subset of features when choosing every split. Averaging many decorrelated trees, by majority vote for classification or by mean for regression, sharply reduces the variance of a single deep tree while keeping its low bias. Random forests also give an out-of-bag error estimate from the samples each tree did not see and permutation-based feature importances. The idea builds on Ho''s random decision forests (1995), which used random feature subspaces; Breiman''s 2001 paper combined them with bagging and gave the method its name. Random forests need little tuning and remain a standard baseline for tabular data, alongside gradient-boosted trees such as [XGBoost](/methods/xgboost), [LightGBM](/methods/lightgbm) and [CatBoost](/methods/catboost) and the boosting algorithm [AdaBoost](/methods/adaboost).',
    'random forest, random forests, Random Forest, Random Forests',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2001,
    (
        SELECT id
        FROM papers
        WHERE source = 'external'
          AND title = 'Random Forests'
          AND is_latest_version
        ORDER BY id DESC
        LIMIT 1
    ),
    NULL,
    'Random Forests',
    'https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/ensemble/_forest.py',
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
WHERE slug = 'random-forest'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'random-forest'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Curated 2026-10-15 from every title/abstract mention of "random forest": each paper
-- below trains, adapts, benchmarks or analyzes random forest models.
CREATE TEMP TABLE random_forest_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'random-forest'
  AND p.is_latest_version
  AND p.id IN (
        312, -- "Why Should I Trust You?": Explaining the Predictions of Any Classifie
        373, -- SemiContour: A Semi-supervised Learning Approach for Contour Detection
        570, -- An Empirical Analysis of Feature Engineering for Predictive Modeling
        1455, -- Extracting Sentiment Attitudes From Analytical Texts
        2117, -- Machine learning approach for segmenting glands in colon histology ima
        2396, -- Anti-Money Laundering in Bitcoin: Experimenting with Graph Convolution
        3085, -- Collaborative Training of Balanced Random Forests for Open Set Domain
        3293, -- Sparse Concept Coded Tetrolet Transform for Unconstrained Odia Charact
        3371, -- What do you Mean? The Role of the Mean Function in Bayesian Optimisati
        3439, -- A Natural Language Processing Pipeline of Chinese Free-text Radiology
        3790, -- 70 years of machine learning in geoscience in review
        4060, -- ATM Cash demand forecasting in an Indian Bank with chaos and deep lear
        4371, -- Mycorrhiza: Genotype Assignment usingPhylogenetic Networks
        4520, -- Machine learning applications to DNA subsequence and restriction site
        4635, -- Short-Term Flow-Based Bandwidth Forecasting using Machine Learning
        4839, -- Brain Tumor Detection and Classification based on Hybrid Ensemble Clas
        5056, -- Evaluating the Performance of Some Local Optimizers for Variational Qu
        6046, -- Predicting Gender by First Name Using Character-level Machine Learning
        7127, -- Stock Price Prediction Using Time Series, Econometric, Machine Learnin
        7409, -- Next Day Wildfire Spread: A Machine Learning Data Set to Predict Wildf
        7647, -- Comparison of biomedical relationship extraction methods and models fo
        7766, -- A Classical Approach to Handcrafted Feature Extraction Techniques for
        8344, -- Inspection-L: Self-Supervised GNN Node Embeddings for Money Laundering
        8514, -- A Baseline Readability Model for Cebuano
        9007, -- Machine Learning Workflow to Explain Black-box Models for Early Alzhei
        10363, -- emojiSpace: Spatial Representation of Emojis
        10549, -- Sampling Streaming Data with Parallel Vector Quantization -- PVQ
        12445, -- SpotHitPy: A Study For ML-Based Song Hit Prediction Using Spotify
        12498, -- Explainable Data-Driven Optimization: From Context to Decision and Bac
        13247, -- Impact of a Batter in ODI Cricket Implementing Regression Models from
        13460, -- A Meta-Learning Approach to Predicting Performance and Data Requiremen
        14205, -- Predicting Thermoelectric Power Factor of Bismuth Telluride During Las
        14689, -- Online Recognition of Incomplete Gesture Data to Interface Collaborati
        15536, -- NLP-based Cross-Layer 5G Vulnerabilities Detection via Fuzzing Generat
        17074, -- Transferable Adversarial Robustness for Categorical Data via Universal
        17105, -- On Computing Optimal Tree Ensembles
        17349, -- Automating Microservices Test Failure Analysis using Kubernetes Cluste
        17804, -- A Meta-analytical Comparison of Naive Bayes and Random Forest for Soft
        18950, -- OBESEYE: Interpretable Diet Recommender for Obesity Management using M
        19883, -- Matbench Discovery -- A framework to evaluate machine learning crystal
        20330, -- Grounded Language Acquisition From Object and Action Imagery
        22315, -- Fast hyperboloid decision tree algorithms
        24554, -- Forecasting Lithium-Ion Battery Longevity with Limited Data Availabili
        24903, -- Land use/land cover classification of fused Sentinel-1 and Sentinel-2
        25969, -- Comparative Study on the Performance of Categorical Variable Encoders
        26664, -- Why do Random Forests Work? Understanding Tree Ensembles as Self-Regul
        27134, -- Using remotely sensed data for air pollution assessment
        27653, -- Towards MLOps: A DevOps Tools Recommender System for Machine Learning
        30306, -- Machine learning and economic forecasting: the role of international t
        31428, -- A Three-Phase Analysis of Synergistic Effects During Co-pyrolysis of A
        33770, -- Predicting the duration of traffic incidents for Sydney greater metrop
        35217, -- A Comprehensive Analysis of Machine Learning Models for Algorithmic Tr
        36394, -- Advance Real-time Detection of Traffic Incidents in Highways using Veh
        36551, -- Large Language Models versus Classical Machine Learning: Performance i
        37038, -- Towards Interpretable End-Stage Renal Disease (ESRD) Prediction: Utili
        37118, -- Applying Pre-trained Multilingual BERT in Embeddings for Improved Mali
        39340, -- Embedding-based classifiers can detect prompt injection attacks
        40109, -- Upside-Down Reinforcement Learning for More Interpretable Optimal Cont
        40380, -- DrugAgent: Automating AI-aided Drug Discovery Programming through LLM
        40397, -- Peritumoral Expansion Radiomics for Improved Lung Cancer Classificatio
        40477, -- Understanding GEMM Performance and Energy on NVIDIA Ada Lovelace: A Ma
        41662, -- Are You Doubtful? Oh, It Might Be Difficult Then! Exploring the Use of
        42225, -- Uncertainty quantification for improving radiomic-based models in radi
        45515, -- GlucoLens: Explainable Postprandial Blood Glucose Prediction from Diet
        47018, -- POINT$^{2}$: A Polymer Informatics Training and Testing Database
        48581, -- Benchmarking Traditional Machine Learning and Deep Learning Models for
        51309, -- A deep learning and machine learning approach to predict neonatal deat
        52689, -- MachineLearningLM: Scaling Many-shot In-context Learning via Continued
        53770, -- RIR-Mega: a large-scale simulated room impulse response dataset for ma
        54085, -- Benchmark Designers Should "Train on the Test Set" to Expose Exploitab
        56579, -- Spatiotemporal Heterogeneity of AI-Driven Traffic Flow Patterns and La
        58002, -- When Graph Structure Becomes a Liability: A Critical Re-Evaluation of
        59008, -- High Resolution Flood Extent Detection Using Deep Learning with Random
        59075, -- Multi-RF Fusion with Multi-GNN Blending for Molecular Property Predict
        61670, -- Machine Learning to Predict Spectral Anisotropy in Valence-to-Core X-r
        63089, -- Australian Bushfire Intelligence with AI-Driven Environmental Analytic
        64808, -- Machine Learning vs. Randomness: Challenges in Predicting Binary Optio
        64978, -- A Practical Machine Learning Approach for Dynamic Stock Recommendation
        65609, -- LLM-based Multi-class Attack Analysis and Mitigation Framework in IoT/
        66618, -- CARLE: A Hybrid Deep-Shallow Learning Framework for Robust and Explain
        66835, -- Adapting Quantum Machine Learning for Energy Dissociation of Bonds
        67007, -- 6G-Enabled Digital Twin Framework for Real-Time Cyber-Physical Systems
        67348, -- CardioForest: An Explainable Ensemble Learning Model for Automatic Wid
        68062, -- Automotive Sound Quality for EVs: Psychoacoustic Metrics with Reproduc
        68403, -- Tabular Data with Class Imbalance: Predicting Electric Vehicle Crash S
        68447, -- Quantum-Inspired Stacked Integrated Concept Graph Model (QISICGM) for
        70084, -- Fine-Tuning Small Language Models (SLMs) for Autonomous Web-based Geog
        70868, -- Binary Tree Option Pricing Under Market Microstructure Effects: A Rand
        70912, -- A Lightweight Face Quality Assessment Framework to Improve Face Verifi
        71901, -- Side-Channel Extraction of Dataflow AI Accelerator Hardware Parameters
        72921, -- Unified AI for Accurate Audio Anomaly Detection
        72980, -- Advancing Tabular Stroke Modelling Through a Novel Hybrid Architecture
        73006, -- Accelerating the Search for Superconductors Using Machine Learning
        73376, -- Creating and Evaluating Code-Mixed Nepali-English and Telugu-English D
        73833, -- FUSE : A Ridge and Random Forest-Based Metric for Evaluating MT in Ind
        73861, -- Asset price movement prediction using empirical mode decomposition and
        73997, -- Evaluating Machine Learning Approaches for ASCII Art Generation
        74303, -- A Binary Classification Social Network Dataset for Graph Machine Learn
        75031, -- Examining the Impact of Income Inequality and Gender on School Complet
        75034, -- Analyzing Geospatial and Socioeconomic Disparities in Breast Cancer Sc
        75204, -- ESURF: Simple and Effective EDU Segmentation
        75271, -- Quantum-Enhanced Conformal Methods for Multi-Output Uncertainty: A Hol
        75298, -- A Comprehensive Catalog of Emission-line Nebulae, Star Clusters, and S
        75621, -- Classifying pedestrian crossing flows: A data-driven approach using fu
        75935, -- Systematically Analyzing Prompt Injection Vulnerabilities in Diverse L
        76443, -- HULLMI: Human vs LLM identification with explainability
        77815, -- Intelligent Diagnosis of Alzheimer's Disease Based on Machine Learning
        78078, -- Decoding Concerns: Multi-label Classification of Vaccine Sentiments in
        78138, -- Generative Inverse Design of Metamaterials with Functional Responses b
        78307, -- Discovering Black Hole Mass Scaling Relations with Symbolic Regression
        78338, -- Confronting LLMs with Traditional ML: Rethinking the Fairness of Large
        78479, -- Can neural networks count digit frequency?
        78550, -- Method-Level Bug Severity Prediction using Source Code Metrics and LLM
        78767, -- Machine Learning Predictions of High-Curie-Temperature Materials
        79396, -- Exploring QSAR Models for Activity-Cliff Prediction
        79496, -- Authorship Identification of Source Code Segments Written by Multiple
        79715, -- ArNLI: Arabic Natural Language Inference for Entailment and Contradict
        79840, -- Why do tree-based models still outperform deep learning on tabular dat
        80220, -- Data set creation and empirical analysis for detecting signs of depres
        81047, -- Towards Benchmark Datasets for Machine Learning Based Website Phishing
        81265, -- Modeling bike availability in a bike-sharing system using machine lear
        81393, -- Deep learning for Stock Market Prediction
        82102, -- Interpretable Deep Convolutional Neural Networks via Meta-learning
        82299, -- A General Approach for Predicting the Behavior of the Supreme Court of
        83548, -- Food-101: Mining Discriminative Components with Random Forests
        85693, -- Bengali Fake News Detection
        86327, -- Autoencoding Random Forests
        86585, -- From Counterfactuals to Trees: Competitive Analysis of Model Extractio
        86798, -- Random Forest Autoencoders for Guided Representation Learning
        87313, -- Statistical Inference for Gradient Boosting Regression
        89277, -- Mixed-curvature decision trees and random forests
        89780, -- ExpProof : Operationalizing Explanations for Confidential Models with
        89980, -- Generalized Random Forests Using Fixed-Point Trees
        91445, -- DynFrs: An Efficient Framework for Machine Unlearning in Random Forest
        92782, -- Jacobian Aligned Random Forests
        96602, -- Estimating Human Muscular Fatigue in Dynamic Collaborative Robotic Tas
        97275, -- Decoding Multi-Finger Motions and Grasp Types with Grasp-Specific Mode
        98917, -- Comparative Analysis of ML Approaches for Chronic Disease Prediction w
        104077, -- Benchmarking Classical, Deep, and Generative Models for Human Activity
        104107, -- Privacy-Preserving Sensor-Based Human Activity Recognition for Low-Res
        104270, -- Automated Cervical Cancer Detection Using Feature-Fused Deep CNNs and
        105799, -- Unraveling Brainstem Deformations in Joubert Syndrome: A Statistical S
        107184, -- On the Probabilistic Learnability of Compact Neural Network Preimage B
        109478, -- A prediction and behavioural analysis of machine learning methods for
        111151, -- Relative cue weighting in multilingual stop voicing production
        115740 -- Supervised Anomaly Detection for Complex Industrial Images
  );

DELETE FROM paper_method_exclusions x
USING random_forest_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM random_forest_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM random_forest_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: random forest appears only as a comparison baseline.
CREATE TEMP TABLE random_forest_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'random-forest'
  AND p.is_latest_version
  AND p.id IN (
        1494, -- Using the Tsetlin Machine to Learn Human-Interpretable Rules for High-
        2138, -- A multi-path 2.5 dimensional convolutional neural network system for s
        4135, -- Investigating Bi-LSTM and CRF with POS Tag Embedding for Indonesian Na
        5856, -- SAINT: Improved Neural Networks for Tabular Data via Row Attention and
        6106, -- DCoM: A Deep Column Mapper for Semantic Data Type Detection
        9192, -- Ultra-compact Binary Neural Networks for Human Activity Recognition on
        9317, -- Hopular: Modern Hopfield Networks for Tabular Data
        9859, -- Estimation of Non-Crossing Quantile Regression Process with Deep ReQU
        14523, -- HyperTab: Hypernetwork Approach for Deep Learning on Small Tabular Dat
        15200, -- Breast Cancer Diagnosis Using Machine Learning Techniques
        15259, -- Large Language Models for Automated Data Science: Introducing CAAFE fo
        17505, -- SSL4EO-L: Datasets and Foundation Models for Landsat Imagery
        20076, -- OutRank: Speeding up AutoML-based Model Search for Large Sparse Data s
        26290, -- Enhanced Labeling Technique for Reddit Text and Fine-Tuned Longformer
        30214, -- From Words to Numbers: Your Large Language Model Is Secretly A Capable
        35469, -- IncidentNet: Traffic Incident Detection, Localization and Severity Est
        37878, -- NRGBoost: Energy-Based Generative Boosted Trees
        45478, -- Transformers for molecular property prediction: Domain adaptation effi
        51634, -- FinAI-BERT: A Transformer-Based Model for Sentence-Level Detection of
        62444, -- Detecting Toxic Flow
        62989, -- POSEIDON: Physics-Optimized Seismic Energy Inference and Detection Ope
        67595, -- Splines-Based Feature Importance in Kolmogorov-Arnold Networks: A Fram
        81526, -- Forecasting significant stock price changes using neural networks
        81724, -- An Ensemble of Bayesian Neural Networks for Exoplanetary Atmospheric R
        82229, -- Self-Normalizing Neural Networks
        82650, -- An Introduction to Artificial Prediction Markets for Classification
        100041, -- STAND: Self-Aware Precondition Induction for Interactive Task Learning
        100492, -- Correcting Split Selection in Online Decision Trees via Anytime-Valid
        103955, -- Long-Sequence LSTM Modeling for NBA Game Outcome Prediction Using a No
        109233, -- The Tsetlin Machine -- A Game Theoretic Bandit Driven Approach to Opti
        111472 -- Automated evaluation of children's speech fluency for low-resource lan
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'random forest curation 2026-10-15: compares against random forest without using it'
FROM random_forest_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING random_forest_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING random_forest_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
