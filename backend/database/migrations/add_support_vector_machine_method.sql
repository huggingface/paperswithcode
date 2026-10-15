-- The SVM grew out of Boser, Guyon & Vapnik (1992) and Cortes & Vapnik (1995),
-- neither of which has a local paper row, so the source is the Cortes & Vapnik DOI,
-- introduced_year stays NULL, and papers are linked from a reviewed set.

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
    'support-vector-machine',
    'Support Vector Machine',
    'Support Vector Machine (SVM)',
    'A support vector machine (SVM) is a supervised learning model that finds the decision boundary with the largest margin between classes. Only the training points closest to the boundary, the support vectors, determine the solution, which is found by solving a convex quadratic program. The kernel trick replaces inner products with a kernel function, such as a polynomial or radial basis function kernel, so the same algorithm learns nonlinear boundaries in an implicit high-dimensional feature space, and the soft-margin formulation with the hinge loss tolerates overlapping classes and noise. The method grew out of Vapnik and Chervonenkis''s optimal-margin classifier; Boser, Guyon and Vapnik (1992) introduced the kernelized maximum-margin algorithm, and Cortes and Vapnik (1995) added the soft margin under the name support-vector networks. Extensions include support vector regression and one-class SVMs for novelty detection. SVMs were a dominant classifier before deep learning and remain a common baseline, often compared with [logistic regression](/methods/logistic-regression) and [random forests](/methods/random-forest).',
    'support vector machine, support-vector machine, SVM',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://doi.org/10.1007/BF00994018',
    'Support-Vector Networks (Cortes & Vapnik, 1995)',
    'https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/svm/_classes.py',
    NULL,
    '[SVM margin](https://commons.wikimedia.org/wiki/File:SVM_margin.png) by Larhmam, CC BY-SA 4.0'
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

-- Curated 2026-10-15 from every title/abstract mention of support vector machines or SVM: each paper below trains, extends or analyzes SVM classifiers.
CREATE TEMP TABLE support_vector_machine_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'support-vector-machine'
  AND p.id IN (
        53, -- Pseudo vs. True Defect Classification in Printed Circuits Boards using
        79, -- CNN Features off-the-shelf: an Astounding Baseline for Recognition
        218, -- Classifier-Based Text Simplification for Improved Machine Translation
        732, -- Audio-replay attack detection countermeasures
        851, -- Arabic Multi-Dialect Segmentation: bi-LSTM-CRF vs. SVM
        876, -- A Neural Network Architecture Combining Gated Recurrent Unit (GRU) and
        901, -- Gaussian Three-Dimensional kernel SVM for Edge Detection Applications
        922, -- RETUYT in TASS 2017: Sentiment Analysis for Spanish Tweets using SVM a
        975, -- On Breast Cancer Detection: An Application of Machine Learning Algorit
        1013, -- An Architecture Combining Convolutional Neural Network (CNN) and Suppo
        1035, -- Towards Building an Intelligent Anti-Malware System: A Deep Learning A
        1251, -- Supervised learning with quantum enhanced feature spaces
        1455, -- Extracting Sentiment Attitudes From Analytical Texts
        1618, -- Benchmarking datasets for Anomaly-based Network Intrusion Detection: K
        2120, -- Identification of synoptic weather types over Taiwan area with multipl
        2194, -- ShEMO -- A Large-Scale Validated Database for Persian Speech Emotion D
        2300, -- Training Models to Extract Treatment Plans from Clinical Notes Using C
        2643, -- Instagram Fake and Automated Account Detection
        3293, -- Sparse Concept Coded Tetrolet Transform for Unconstrained Odia Charact
        3439, -- A Natural Language Processing Pipeline of Chinese Free-text Radiology
        3537, -- Automatic Detection and Recognition of Individuals in Patterned Specie
        3711, -- Vietnamese Word Segmentation with SVM: Ambiguity Reduction and Suffix
        3955, -- Dynamic texture analysis for detecting fake faces in video sequences
        4496, -- XED: A Multilingual Dataset for Sentiment Analysis and Emotion Detecti
        4518, -- Fighting an Infodemic: COVID-19 Fake News Dataset
        4520, -- Machine learning applications to DNA subsequence and restriction site
        4751, -- Hate Speech detection in the Bengali language: A dataset and its basel
        4837, -- A Hybrid MLP-SVM Model for Classification using Spatial-Spectral Featu
        5056, -- Evaluating the Performance of Some Local Optimizers for Variational Qu
        5500, -- Emotion Classification in a Resource Constrained Language Using Transf
        5841, -- Weighting vectors for machine learning: numerical harmonic analysis ap
        6046, -- Predicting Gender by First Name Using Character-level Machine Learning
        6187, -- Total Nitrogen Estimation in Agricultural Soils via Aerial Multispectr
        6679, -- Violence Detection in Videos
        6757, -- A system on chip for melanoma detection using FPGA-based SVM classifie
        7645, -- Using Machine Learning for Anomaly Detection on a System-on-Chip under
        7766, -- A Classical Approach to Handcrafted Feature Extraction Techniques for
        8138, -- In the Service of Online Order: Tackling Cyber-Bullying with Machine L
        9007, -- Machine Learning Workflow to Explain Black-box Models for Early Alzhei
        9292, -- APPReddit: a Corpus of Reddit Posts Annotated for Appraisal
        10363, -- emojiSpace: Spatial Representation of Emojis
        11153, -- The Numerical Stability of Hyperbolic Representation Learning
        11358, -- Is Style All You Need? Dependencies Between Emotion and GST-based Spea
        11639, -- Synergies between Disentanglement and Sparsity: Generalization and Ide
        11951, -- Learning 3D Representations from 2D Pre-trained Models via Image-to-Po
        11987, -- FreCDo: A Large Corpus for French Cross-Domain Dialect Identification
        12445, -- SpotHitPy: A Study For ML-Based Song Hit Prediction Using Spotify
        13707, -- Large Language Models in the Workplace: A Case Study on Prompt Enginee
        14723, -- ArguGPT: evaluating, understanding and identifying argumentative essay
        15452, -- BanglaBook: A Large-scale Bangla Dataset for Sentiment Analysis from B
        16285, -- Linguistic Properties of Truthful Response
        16940, -- The Power Of Simplicity: Why Simple Linear Models Outperform Complex M
        17349, -- Automating Microservices Test Failure Analysis using Kubernetes Cluste
        18377, -- Measuring Student Behavioral Engagement using Histogram of Actions
        18950, -- OBESEYE: Interpretable Diet Recommender for Obesity Management using M
        19988, -- Transformers as Support Vector Machines
        22091, -- Machine Learning in the Quantum Age: Quantum vs. Classical Support Vec
        28369, -- Not All Layers of LLMs Are Necessary During Inference
        29579, -- Evaluating Large Language Models for Health-Related Text Classificatio
        32663, -- AGB-DE: A Corpus for the Automated Legal Assessment of Clauses in Germ
        33869, -- A Machine Learning Approach for Identifying Anatomical Biomarkers of E
        35739, -- Adapting General Disentanglement-Based Speaker Anonymization for Enhan
        36362, -- Enhancing Customer Churn Prediction in Telecommunications: An Adaptive
        36372, -- Is text normalization relevant for classifying medieval charters?
        39836, -- Robust Detection of LLM-Generated Text: A Comparative Analysis
        39848, -- ClinicalBench: Can LLMs Beat Traditional ML Models in Clinical Predict
        40227, -- A Novel Speech Analysis and Correction Tool for Arabic-Speaking Childr
        40418, -- Diagnosis of diabetic retinopathy using machine learning & deep learni
        42225, -- Uncertainty quantification for improving radiomic-based models in radi
        42923, -- Cueless EEG imagined speech for subject identification: dataset and be
        44909, -- Adversarial Training for Defense Against Label Poisoning Attacks
        48581, -- Benchmarking Traditional Machine Learning and Deep Learning Models for
        51469, -- Deciphering GunType Hierarchy through Acoustic Analysis of Gunshot Rec
        52136, -- Embedding-Aware Quantum-Classical SVMs for Scalable Quantum Machine Le
        57764, -- Quantum Kernel Advantage over Classical Collapse in Medical Foundation
        57803, -- Sample Selection Using Multi-Task Autoencoders in Federated Learning w
        60989, -- A Multi-objective Evolutionary Algorithm Based on Bi-population with U
        66212, -- Self-Supervised Learning to Fly using Efficient Semantic Segmentation
        68062, -- Automotive Sound Quality for EVs: Psychoacoustic Metrics with Reproduc
        68942, -- A Multi-Strategy Approach for AI-Generated Text Detection
        70433, -- Honey Classification using Hyperspectral Imaging and Machine Learning
        72476, -- Human Fall Detection using Transfer Learning-based 3D CNN
        72921, -- Unified AI for Accurate Audio Anomaly Detection
        73168, -- Quantum QSAR for drug discovery
        73376, -- Creating and Evaluating Code-Mixed Nepali-English and Telugu-English D
        73997, -- Evaluating Machine Learning Approaches for ASCII Art Generation
        77815, -- Intelligent Diagnosis of Alzheimer's Disease Based on Machine Learning
        78121, -- Multi-class Support Vector Machine with Maximizing Minimum Margin
        78309, -- Enhancing Epileptic Seizure Detection with EEG Feature Embeddings
        78834, -- Voting-based Multimodal Automatic Deception Detection
        79496, -- Authorship Identification of Source Code Segments Written by Multiple
        80398, -- On the Equivalence between Neural Network and Support Vector Machine
        81462, -- Regression-based music emotion prediction using triplet neural network
        82147, -- 11K Hands: Gender recognition and biometric identification using a lar
        82189, -- DolphinAtack: Inaudible Voice Commands
        82368, -- Features and Kernels for Audio Event Recognition
        82634, -- An Approach for Classification of Dysfluent and Fluent Speech Using K-
        86749, -- Multi-Class Support Vector Machine with Differential Privacy
        89830, -- Joker: Joint Optimization Framework for Lightweight Kernel Machines
        91794, -- Faster Algorithms for Structured Linear and Kernel Support Vector Mach
        95134, -- Privacy Policy Enforcement Guardrails for Data-Sensitive Retrieval-Aug
        97653, -- Tactile-Based Human Intent Recognition for Robot Assistive Navigation
        98917, -- Comparative Analysis of ML Approaches for Chronic Disease Prediction w
        99136, -- FiSeR: Fine-Grained Source Representations for Cross-Domain AI Image D
        102159, -- Randomized Feasibility Methods for Constrained Optimization with Adapt
        102857, -- LLM-VA: Resolving the Jailbreak-Overrefusal Trade-off via Vector Align
        104107, -- Privacy-Preserving Sensor-Based Human Activity Recognition for Low-Res
        104131, -- A Public Domain Dataset for Human Activity Recognition Using Smartphon
        105955, -- AMRD: Adaptive Multi-Teacher Relational Distillation for Lightweight S
        109241, -- Investigating Critical Frequency Bands and Channels for EEG-Based Emot
        111199, -- Predicting Adolescent Suicidal Risk from Multi-task-based Speech: An E
        111754, -- Hybrid HMM-SVM classifier using frication-based features for detection
        111827, -- A Multimodal Chinese Dataset for Cross-lingual Sarcasm Detection
        111829, -- Analysis of the ABC Classification Backends for NIST SRE24
        112012, -- Multimodal Silent Recognition of Phonemes Using Radar and Optopalatogr
        112055, -- Towards Classification of Typical and Atypical Disfluencies: A Self Su
        112143 -- Identifying Primary Stress Across Related Languages and Dialects with
  );

DELETE FROM paper_method_exclusions x
USING support_vector_machine_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM support_vector_machine_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM support_vector_machine_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: SVMs appear only as a baseline the paper outperforms or in a survey, or the SVM substring belongs to an unrelated name (MSVMamba, SSVM, SVMA, LSVM).
CREATE TEMP TABLE support_vector_machine_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'support-vector-machine'
  AND p.id IN (
        162, -- Convolutional LSTM Networks for Subcellular Localization of Proteins
        311, -- Medical Concept Representation Learning from Electronic Health Records
        1494, -- Using the Tsetlin Machine to Learn Human-Interpretable Rules for High-
        2625, -- The merits of Universal Language Model Fine-tuning for Small Datasets
        3081, -- The Alzheimer's Disease Prediction Of Longitudinal Evolution (TADPOLE)
        3110, -- Listwise Learning to Rank with Deep Q-Networks
        3790, -- 70 years of machine learning in geoscience in review
        4135, -- Investigating Bi-LSTM and CRF with POS Tag Embedding for Indonesian Na
        4838, -- Improved Neural Network based Plant Diseases Identification
        4934, -- WangchanBERTa: Pretraining transformer-based Thai Language Models
        5449, -- The Surprising Performance of Simple Baselines for Misinformation Dete
        5549, -- Wireless Sensing With Deep Spectrogram Network and Primitive Based Aut
        6070, -- From Unsupervised to Semi-supervised Anomaly Detection Methods for HRR
        7619, -- Label Distributionally Robust Losses for Multi-class Classification: C
        9317, -- Hopular: Modern Hopfield Networks for Tabular Data
        10549, -- Sampling Streaming Data with Parallel Vector Quantization -- PVQ
        12360, -- Learning Support and Trivial Prototypes for Interpretable Image Classi
        14854, -- Deep reproductive feature generation framework for the diagnosis of CO
        15483, -- Implications of Deep Circuits in Improving Quality of Quantum Question
        16511, -- Constrained Optimization via Exact Augmented Lagrangian and Randomized
        20088, -- StyleAdapter: A Unified Stylized Image Generation Model
        26290, -- Enhanced Labeling Technique for Reddit Text and Fine-Tuned Longformer
        30214, -- From Words to Numbers: Your Large Language Model Is Secretly A Capable
        31563, -- Multi-Scale VMamba: Hierarchy in Hierarchy Visual State Space Model
        34892, -- Evaluating Large Language Models for Anxiety and Depression Classifica
        36204, -- MSVM-UNet: Multi-Scale Vision Mamba UNet for Medical Image Segmentatio
        37118, -- Applying Pre-trained Multilingual BERT in Embeddings for Improved Mali
        40788, -- A Comprehensive Guide to Explainable AI: From Classical Models to LLMs
        40887, -- Deep Learning, Machine Learning, Advancing Big Data Analytics and Mana
        42637, -- Planing It by Ear: Convolutional Neural Networks for Acoustic Anomaly
        45650, -- HealthiVert-GAN: A Novel Framework of Pseudo-Healthy Vertebral Image S
        45744, -- Griffin: Aerial-Ground Cooperative Detection and Tracking Dataset and
        51918, -- Watch, Listen, Understand, Mislead: Tri-modal Adversarial Attacks on S
        52521, -- DrugReasoner: Interpretable Drug Approval Prediction with a Reasoning-
        59524, -- The Mirror Design Pattern: Strict Data Geometry over Model Scale for P
        60284, -- Support Tokens, Stability Margins, and a New Foundation for Robust LLM
        67516, -- MDD-Thinker: Towards Large Reasoning Models for Major Depressive Disor
        67595, -- Splines-Based Feature Importance in Kolmogorov-Arnold Networks: A Fram
        70084, -- Fine-Tuning Small Language Models (SLMs) for Autonomous Web-based Geog
        72924, -- Guarded Query Routing for Large Language Models
        75034, -- Analyzing Geospatial and Socioeconomic Disparities in Breast Cancer Sc
        76373, -- Machine Learning to Detect Anxiety Disorders from Error-Related Negati
        76461, -- Introduction to Machine Learning
        78008, -- Natural Language Processing and Multimodal Stock Price Prediction
        78078, -- Decoding Concerns: Multi-label Classification of Vaccine Sentiments in
        80074, -- Are We Really Making Much Progress in Text Classification? A Comparati
        81442, -- One-Class Graph Neural Networks for Anomaly Detection in Attributed Ne
        81619, -- Self-paced Ensemble for Highly Imbalanced Massive Data Classification
        82229, -- Self-Normalizing Neural Networks
        82333, -- DeepSpace: An Online Deep Learning Framework for Mobile Big Data to Un
        87152, -- Optimal Rates for Generalization of Gradient Descent for Deep ReLU Cla
        89419, -- FastCAV: Efficient Computation of Concept Activation Vectors for Expla
        96360, -- Tactile Execution Monitoring of Robotic Manipulation Via Time-Series B
        100954, -- Linear-Core Surrogates: Smooth Loss Functions with Linear Rates for Cl
        107205, -- Statistical Learning Theory for Distributional Classification
        109233, -- The Tsetlin Machine -- A Game Theoretic Bandit Driven Approach to Opti
        111202, -- Network of acoustic characteristics for the automatic detection of sui
        111435, -- Robust Vocal Intensity Prediction: Overcoming Dataset Bias with Pretra
        111915, -- EmoDB 2.0: A Database of Emotional Speech in a World that is not Black
        112144, -- SupraDoRAL: Automatic Word Prominence Detection Using Suprasegmental D
        119262 -- InteractiveAvatar: Real-Time Streaming Video Generation for Consistent
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'SVM curation 2026-10-15: mentions SVMs without using them'
FROM support_vector_machine_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING support_vector_machine_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING support_vector_machine_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
