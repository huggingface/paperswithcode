-- Federated learning has no single introducing paper: McMahan et al. (arXiv
-- 1602.05629) named it and introduced FedAvg, but Konecny et al.'s 2015 federated
-- optimization work came first. The source is therefore the Kairouz et al. survey,
-- source_paper_id stays NULL, and papers are linked from a reviewed set.

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
    'federated-learning',
    'Federated Learning',
    'Federated Learning (FL)',
    'Federated learning (FL) trains a shared model across many clients, such as phones, hospitals or companies, that keep their raw data local and exchange only model updates with a coordinating server. In each round the server sends the current model to a subset of clients, each client trains on its own data, and the server aggregates the returned updates. The Federated Averaging (FedAvg) algorithm of [McMahan et al.](/paper/1602.05629), which coined the term federated learning, runs several local SGD epochs per client and averages the resulting weights, cutting communication by orders of magnitude; it built on earlier federated optimization work by Konečný et al. Core challenges include non-IID and unbalanced client data, communication cost, partial and unreliable participation, and privacy, which is strengthened with secure aggregation and differential privacy. Variants include cross-device and cross-silo FL, horizontal and vertical FL, heterogeneity-robust optimizers such as [FedProx](/paper/1812.06127), personalized FL and federated fine-tuning of large language models with [LoRA](/methods/lora).',
    'federated learning, federated averaging, FedAvg, federated optimization',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://arxiv.org/abs/1912.04977',
    'Advances and Open Problems in Federated Learning',
    'https://github.com/adap/flower',
    NULL,
    '[Federated learning process central case](https://commons.wikimedia.org/wiki/File:Federated_learning_process_central_case.png) by Jeromemetronome, CC BY-SA 4.0'
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

-- Curated 2026-10-15 from every title/abstract mention of "federated" or FedAvg: each paper below proposes, analyzes, attacks or applies federated learning.
CREATE TEMP TABLE federated_learning_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'federated-learning'
  AND p.id IN (
        314, -- Communication-Efficient Learning of Deep Networks from Decentralized D
        504, -- Practical Secure Aggregation for Federated Learning on User-Held Data
        1283, -- Gradient-Leaks: Understanding and Controlling Deanonymization in Feder
        1676, -- LEAF: A Benchmark for Federated Settings
        1703, -- Federated Optimization in Heterogeneous Networks
        3105, -- Federated Learning with Matched Averaging
        3162, -- Adaptive Federated Optimization
        3269, -- Adaptive Personalized Federated Learning
        3399, -- Federated Stochastic Gradient Langevin Dynamics
        3726, -- Personalized Federated Learning with Moreau Envelopes
        3947, -- Flower: A Friendly Federated Learning Research Framework
        4033, -- Inverse Distance Aggregation for Federated Learning with Non-IID Data
        4321, -- Fairness-aware Agnostic Federated Learning
        4590, -- A Reputation Mechanism Is All You Need: Collaborative Fairness and Adv
        4760, -- Learning from History for Byzantine Robust Optimization
        4976, -- FEDZIP: A Compression Framework for Communication-Efficient Federated
        5575, -- FedSup: A Communication-Efficient Federated Learning Fatigue Driving B
        5711, -- The Federated Tumor Segmentation (FeTS) Challenge
        5718, -- OpenFL: An open-source framework for Federated Learning
        5771, -- Data-Free Knowledge Distillation for Heterogeneous Federated Learning
        5934, -- No Fear of Heterogeneity: Classifier Calibration for Federated Learnin
        6197, -- RoFL: Robustness of Secure Federated Learning
        6288, -- Federated Learning using Smart Contracts on Blockchains, based on Rewa
        6417, -- FedPara: Low-Rank Hadamard Product for Communication-Efficient Federat
        6454, -- FedSkel: Efficient Federated Learning on Heterogeneous Systems with Sk
        6467, -- Anarchic Federated Learning
        6527, -- Federated Reconnaissance: Efficient, Distributed, Class-Incremental Le
        6680, -- Improving Fairness for Data Valuation in Horizontal Federated Learning
        6814, -- Federated Learning via Plurality Vote
        6823, -- Distributed Methods with Compressed Communication for Solving Variatio
        6853, -- FRL: Federated Rank Learning
        7018, -- Bristle: Decentralized Federated Learning in Byzantine, Non-i.i.d. Env
        7088, -- Improving Fairness via Federated Learning
        7457, -- On Convergence of Federated Averaging Langevin Dynamics
        7639, -- Wireless-Enabled Asynchronous Federated Fourier Neural Network for Tur
        7661, -- Fair and efficient contribution valuation for vertical federated learn
        8002, -- LAMP: Extracting Text from Gradients with Language Model Priors
        8041, -- Bitwidth Heterogeneous Federated Learning with Progressive Weight Dequ
        8211, -- FedSyn: Synthetic Data Generation using Federated Learning
        8277, -- SemiPFL: Personalized Semi-Supervised Federated Learning Framework for
        8313, -- Fine-tuning Global Model via Data-Free Knowledge Distillation for Non-
        8380, -- Feature Distribution Matching for Federated Domain Generalization
        8396, -- Federated Learning Approach for Lifetime Prediction of Semiconductor L
        8626, -- Federated Learning with Partial Model Personalization
        8753, -- Self-Aware Personalized Federated Learning
        9215, -- FedBR: Improving Federated Learning on Heterogeneous Data via Local Le
        9268, -- FRAug: Tackling Federated Learning with Non-IID Features via Represent
        9342, -- On the Generalization of Wasserstein Robust Federated Learning
        9400, -- Subject Membership Inference Attacks in Federated Learning
        9419, -- HideNseek: Federated Lottery Ticket via Server-side Pruning and Sign S
        9436, -- Fast Deep Autoencoder for Federated learning
        9450, -- Anchor Sampling for Federated Learning with Partial Client Participati
        9552, -- A General Theory for Federated Optimization with Asynchronous and Hete
        9553, -- Personalized Subgraph Federated Learning
        9599, -- zPROBE: Zero Peek Robustness Checks for Federated Learning
        9612, -- FAIR-BFL: Flexible and Incentive Redesign for Blockchain-based Federat
        9689, -- Federated Self-supervised Learning for Video Understanding
        9713, -- Adaptive Personlization in Federated Learning for Highly Non-i.i.d. Da
        9821, -- FLAIR: Federated Learning Annotated Image Repository
        9832, -- FedX: Unsupervised Federated Learning with Cross Knowledge Distillatio
        9841, -- Reducing Training Time in Cross-Silo Federated Learning using Multigra
        9994, -- Federated Adversarial Learning: A Framework with Convergence Analysis
        10033, -- Dropout is NOT All You Need to Prevent Gradient Leakage
        10101, -- Long-Short History of Gradients is All You Need: Detecting Malicious a
        10265, -- Cocktail Party Attack: Breaking Aggregation-Based Privacy in Federated
        10545, -- Exploring Parameter-Efficient Fine-Tuning to Enable Foundation Models
        10553, -- Group Personalized Federated Learning
        10832, -- Sketching for First Order Method: Efficient Algorithm for Low-Bandwidt
        11004, -- FLIP: A Provable Defense Framework for Backdoor Mitigation in Federate
        11253, -- Privacy-Aware Compression for Federated Learning Through Numerical Mec
        11309, -- Secure Aggregation Is Not All You Need: Mitigating Privacy Attacks wit
        11332, -- Universal EHR Federated Learning Framework
        11351, -- Federated Learning for Healthcare Domain - Pipeline, Applications and
        11592, -- Knowledge-Aware Federated Active Learning with Non-IID Data
        11737, -- HashVFL: Defending Against Data Reconstruction Attacks in Vertical Fed
        11787, -- PGFed: Personalize Each Client's Global Objective for Federated Learni
        11799, -- Distributed Pruning Towards Tiny Neural Networks in Federated Learning
        12202, -- Federated PCA on Grassmann Manifold for Anomaly Detection in IoT Netwo
        12214, -- When Do Curricula Work in Federated Learning?
        12472, -- Federated Recommendation with Additive Personalization
        12476, -- Doubly Adversarial Federated Bandits
        12616, -- BAFFLE: A Baseline of Backpropagation-Free Federated Learning
        12628, -- FedRC: Tackling Diverse Distribution Shifts Challenge in Federated Lea
        12893, -- One-shot Empirical Privacy Estimation for Federated Learning
        12894, -- On the Convergence of Federated Averaging with Cyclic Client Participa
        12948, -- Improving the Model Consistency of Decentralized Federated Learning
        13002, -- Principled Federated Domain Adaptation: Gradient Projection and Auto-W
        13016, -- Achieving Linear Speedup in Non-IID Federated Bilevel Learning
        13046, -- Byzantine-Robust Learning on Heterogeneous Data via Gradient Splitting
        13052, -- One-Shot Federated Conformal Prediction
        13168, -- Multimodal Federated Learning via Contrastive Representation Ensemble
        13221, -- FedSpeed: Larger Local Interval, Less Communication Round, and Higher
        13236, -- Revisiting Weighted Aggregation in Federated Learning with Neural Netw
        13303, -- From Noisy Fixed-Point Iterations to Private ADMM for Centralized and
        13324, -- Post Quantum Secure Blockchain-based Federated Learning for Mobile Edg
        13332, -- Communication-efficient Federated Learning with Single-Step Synthetic
        13340, -- On Differentially Private Federated Linear Contextual Bandits
        13347, -- Proof-of-Contribution-Based Design for Collaborative Machine Learning
        13484, -- Federated Virtual Learning on Heterogeneous Data with Local-global Dis
        13679, -- Multi-metrics adaptively identifies backdoors in Federated learning
        13699, -- TARGET: Federated Class-Continual Learning via Exemplar-Free Distillat
        13867, -- No Fear of Classifier Biases: Neural Collapse Inspired Federated Learn
        14237, -- Communication-Efficient Vertical Federated Learning with Limited Overl
        14251, -- Fair Federated Medical Image Segmentation via Client Contribution Esti
        14416, -- On Mitigating the Utility-Loss in Differentially Private Learning: A n
        14611, -- TinyReptile: TinyML with Federated Meta-Learning
        14949, -- Chameleon: Adapting to Peer Images for Planting Durable Backdoors in F
        14975, -- FedVS: Straggler-Resilient and Privacy-Preserving Vertical Federated L
        15095, -- Towards Unbiased Training in Federated Open-world Semi-supervised Lear
        15112, -- Personalized Federated Learning under Mixture of Distributions
        15220, -- Efficient Personalized Federated Learning via Sparse Model-Adaptation
        15383, -- Towards Building the Federated GPT: Federated Instruction Tuning
        15404, -- XTab: Cross-table Pretraining for Tabular Transformers
        16299, -- FAVANO: Federated AVeraging with Asynchronous NOdes
        16444, -- Federated Conformal Predictors for Distributed Uncertainty Quantificat
        16615, -- FedDisco: Federated Learning with Discrepancy-Aware Collaboration
        16712, -- Surrogate Model Extension (SME): A Fast and Accurate Weight Update Att
        16982, -- Hiding in Plain Sight: Disguising Data Stealing Attacks in Federated L
        17025, -- A Lightweight Method for Tackling Unknown Participation Statistics in
        17153, -- Communication-Efficient Gradient Descent-Accent Methods for Distribute
        17156, -- Conformal Prediction for Federated Uncertainty Quantification Under La
        17166, -- Federated Linear Contextual Bandits with User-level Differential Priva
        17198, -- PeFLL: Personalized Federated Learning by Learning to Learn
        17213, -- Fair yet Asymptotically Equal Collaborative Learning
        17221, -- FedWon: Triumphing Multi-domain Federated Learning Without Normalizati
        17261, -- Optimizing the Collaboration Structure in Cross-Silo Federated Learnin
        17423, -- Learning to Specialize: Joint Gating-Expert Training for Adaptive MoEs
        17597, -- FSAR: Federated Skeleton-based Action Recognition with Adaptive Topolo
        17605, -- Adaptive Federated Learning with Auto-Tuned Clients
        17643, -- Randomized Quantization is All You Need for Differential Privacy in Fe
        17707, -- FedSelect: Customized Selection of Parameters for Fine-Tuning during P
        17855, -- Momentum Benefits Non-IID Federated Learning Simply and Provably
        18011, -- VertiBench: Advancing Feature Distribution Diversity in Vertical Feder
        18142, -- Benchmarking Algorithms for Federated Domain Generalization
        18245, -- L-DAWA: Layer-wise Divergence Aware Weight Aggregation in Federated Se
        18343, -- Local or Global: Selective Knowledge Assimilation for Federated Learni
        18438, -- Blockchain-Based Federated Learning: Incentivizing Data Sharing and Pe
        18493, -- MAS: Towards Resource-Efficient Federated Multiple-Task Learning
        18496, -- Demystifying Local and Global Fairness Trade-offs in Federated Learnin
        18559, -- ProtoFL: Unsupervised Federated Learning via Prototypical Distillation
        19029, -- Federated Zeroth-Order Optimization using Trajectory-Informed Surrogat
        19052, -- Backdoor Federated Learning by Poisoning Backdoor-Critical Layers
        19069, -- GIFD: A Generative Gradient Inversion Method with Feature Domain Optim
        19151, -- Towards Instance-adaptive Inference for Federated Learning
        19180, -- SLoRA: Federated Parameter Efficient Fine-Tuning of Language Models
        19308, -- Stochastic Controlled Averaging for Federated Learning with Communicat
        19372, -- FedPerfix: Towards Partial Model Personalization of Vision Transformer
        19392, -- Towards Attack-tolerant Federated Learning via Critical Parameter Anal
        19418, -- Understanding the Role of Layer Normalization in Label-Skewed Federate
        19509, -- GPFL: Simultaneously Learning Global and Personalized Feature Informat
        19628, -- Internal Cross-layer Gradients for Extending Homogeneity to Heterogene
        19646, -- Aggregating Intrinsic Information to Enhance BCI Performance through F
        19911, -- Efficient Model Personalization in Federated Learning via Client-Speci
        20011, -- FederatedScope-LLM: A Comprehensive Package for Fine-tuning Large Lang
        20058, -- Federated Orthogonal Training: Mitigating Global Catastrophic Forgetti
        20165, -- Federated Learning Over Images: Vertical Decompositions and Pre-Traine
        20359, -- FedDIP: Federated Learning with Extreme Dynamic Pruning and Incrementa
        20660, -- Bold but Cautious: Unlocking the Potential of Personalized Federated L
        20791, -- Expressive variational quantum circuits provide inherent privacy in fe
        20840, -- Tackling Intertwined Data and Device Heterogeneities in Federated Lear
        20921, -- FedCompass: Efficient Cross-Silo Federated Learning on Heterogeneous C
        21121, -- Enabling Differentially Private Federated Learning for Speech Recognit
        21314, -- Federated Wasserstein Distance
        21418, -- FedHyper: A Universal and Robust Learning Rate Scheduler for Federated
        21685, -- Text-driven Prompt Generation for Vision-Language Models in Federated
        22002, -- VFLAIR: A Research Library and Benchmark for Vertical Federated Learni
        22014, -- FATE-LLM: A Industrial Grade Federated Learning Framework for Large La
        22158, -- Effective and Efficient Federated Tree Learning on Hybrid Data
        22301, -- Towards Realistic Mechanisms That Incentivize Federated Participation
        22588, -- Navigating Data Heterogeneity in Federated Learning A Semi-Supervised
        22737, -- Enhancing Scalability and Reliability in Semi-Decentralized Federated
        22926, -- Communication-Efficient Federated Non-Linear Bandit Optimization
        23286, -- DiLoCo: Distributed Low-Communication Training of Language Models
        24421, -- A Novel Federated Learning-Based IDS for Enhancing UAVs Privacy and Se
        24569, -- Fake It Till Make It: Federated Learning with Consensus-Oriented Gener
        24589, -- Federated Full-Parameter Tuning of Billion-Sized Language Models with
        24676, -- Privacy-Aware Energy Consumption Modeling of Connected Battery Electri
        25020, -- Incremental Semi-supervised Federated Learning for Health Inference vi
        25049, -- Enhancing Neural Training via a Correlated Dynamics Model
        25311, -- Differentially Private Low-Rank Adaptation of Large Language Model Usi
        25609, -- A Survey on Efficient Federated Learning Methods for Foundation Model
        25916, -- FedLoGe: Joint Local and Generic Federated Learning under Long-tailed
        25927, -- Asynchronous Local-SGD Training for Language Modeling
        26135, -- Personalized Over-the-Air Federated Learning with Personalized Reconfi
        26231, -- Federated learning with distributed fixed design quantum chips and qua
        26359, -- Finite-Time Analysis of On-Policy Heterogeneous Federated Reinforcemen
        26487, -- Spectral Co-Distillation for Personalized Federated Learning
        26821, -- Towards Eliminating Hard Label Constraints in Gradient Inversion Attac
        26956, -- Incentivized Truthful Communication for Federated Bandits
        27133, -- Transformers with Attentive Federated Aggregation for Time Series Stoc
        27154, -- Clients Collaborate: Flexible Differentially Private Federated Learnin
        27155, -- FedImpro: Measuring and Improving Client Update in Federated Learning
        27206, -- Empowering Federated Learning for Massive Models with NVIDIA FLARE
        27441, -- FedD2S: Personalized Data-Free Federated Knowledge Distillation
        27690, -- Federated Causal Discovery from Heterogeneous Data
        27798, -- Robust Training of Federated Models with Extremely Label Deficiency
        27878, -- Enhancing One-Shot Federated Learning Through Data and Ensemble Co-Boo
        28277, -- Blockchain-empowered Federated Learning: Benefits, Challenges, and Sol
        29048, -- KnFu: Effective Knowledge Fusion
        29085, -- Improving LoRA in Privacy-preserving Federated Learning
        29154, -- Resilience in Online Federated Learning: Mitigating Model-Poisoning At
        29296, -- FedMef: Towards Memory-efficient Federated Dynamic Pruning
        29780, -- Open-Vocabulary Federated Learning with Multimodal Prototyping
        30025, -- Vanishing Variance Problem in Fully Decentralized Neural-Network Syste
        30147, -- pfl-research: simulation framework for accelerating research in Privat
        30148, -- Automated Federated Pipeline for Parameter-Efficient Fine-Tuning of La
        30378, -- FedP3: Federated Personalized and Privacy-friendly Network Pruning und
        30551, -- Towards Multi-modal Transformers in Federated Learning
        30606, -- EHRFL: Federated Learning Framework for Institution-Specific Model Con
        30967, -- Detection of ransomware attacks using federated learning based on the
        31044, -- Federated Learning for Tabular Data using TabNet: A Vehicular Use-Case
        31238, -- On-device Online Learning and Semantic Management of TinyML Systems
        31359, -- Federated Hybrid Model Pruning through Loss Landscape Exploration
        31396, -- LIFL: A Lightweight, Event-driven Serverless Platform for Federated Le
        31540, -- FACT or Fiction: Can Truthful Mechanisms Eliminate Federated Free Ridi
        31687, -- Towards Client Driven Federated Learning
        31746, -- Analytic Federated Learning
        32169, -- FedAST: Federated Asynchronous Simultaneous Training
        32936, -- Recent Advances in Federated Learning Driven Large Language Models: A
        33254, -- Low-Resource Machine Translation through the Lens of Personalized Fede
        34414, -- Federated PCA on Grassmann Manifold for IoT Anomaly Detection
        35172, -- SFPrompt: Communication-Efficient Split Federated Fine-Tuning for Larg
        35325, -- CELLM: An Efficient Communication in Large Language Models Training fo
        36130, -- Tackling Data Heterogeneity in Federated Learning via Loss Decompositi
        36176, -- A Web-Based Solution for Federated Learning with LLM-Based Automation
        36308, -- Exploring Selective Layer Fine-Tuning in Federated Learning
        36463, -- DAMe: Personalized Federated Social Event Detection with Dual Aggregat
        36713, -- FLoRA: Federated Fine-Tuning Large Language Models with Heterogeneous
        36724, -- Ferret: Federated Full-Parameter Tuning at Scale for Large Language Mo
        36877, -- Leveraging Foundation Models for Efficient Federated Learning in Resou
        37124, -- Noise-Robust and Resource-Efficient ADMM-based Federated Learning
        37533, -- Federated Instruction Tuning of LLMs with Domain Coverage Augmentation
        37649, -- Selective Aggregation for Low-Rank Adaptation in Federated Learning
        37926, -- pFedGame -- Decentralized Federated Learning using Game Theory in Dyna
        38360, -- FedEx-LoRA: Exact Aggregation for Federated and Efficient Fine-Tuning
        40286, -- FedMLLM: Federated Fine-tuning MLLM on Multimodal Heterogeneity Data
        40303, -- LoRA-FAIR: Federated LoRA Fine-Tuning with Aggregation and Initializat
        41275, -- Sequential Compression Layers for Efficient Federated Learning in Foun
        41288, -- A New Federated Learning Framework Against Gradient Inversion Attacks
        41642, -- Just a Simple Transformation is Enough for Data Protection in Vertical
        42258, -- Adaptive Parameter-Efficient Federated Fine-Tuning on Heterogeneous De
        43057, -- FedCLEAN: byzantine defense by CLustering Errors of Activation maps in
        43479, -- Federated Sketching LoRA: On-Device Collaborative Fine-Tuning of Large
        43822, -- DMPA: Model Poisoning Attacks on Decentralized Federated Learning for
        44762, -- Fed-SB: A Silver Bullet for Extreme Communication Efficiency and Perfo
        45200, -- FedConv: A Learning-on-Model Paradigm for Heterogeneous Federated Clie
        45349, -- FLAME: A Federated Learning Benchmark for Robotic Manipulation
        45520, -- Subgraph Federated Learning for Local Generalization
        45596, -- FedMABench: Benchmarking Mobile Agents on Decentralized Heterogeneous
        45692, -- Geometric Knowledge-Guided Localized Global Distribution Alignment for
        45770, -- FedRand: Enhancing Privacy in Federated Learning with Randomized LoRA
        46152, -- Exploring the Vulnerabilities of Federated Learning: A Deep Dive into
        46177, -- A Survey on Federated Fine-tuning of Large Language Models
        46185, -- PA-CFL: Privacy-Adaptive Clustered Federated Learning for Transformer-
        46283, -- FedVSR: Towards Model-Agnostic Federated Learning in Video Super-Resol
        46828, -- Multi-Objective Optimization for Privacy-Utility Balance in Differenti
        47198, -- On Model Protection in Federated Learning against Eavesdropping Attack
        48078, -- Private Federated Learning using Preference-Optimized Synthetic Data
        48162, -- Federated Learning-based Semantic Segmentation for Lane and Object Det
        48590, -- FedADP: Unified Model Aggregation for Federated Learning with Heteroge
        48999, -- FedSVD: Adaptive Orthogonalization for Private Federated Learning with
        49074, -- Federated Low-Rank Adaptation for Foundation Models: A Survey
        49083, -- Exploring Federated Pruning for Large Language Models
        51242, -- FedNano: Toward Lightweight Federated Tuning for Pretrained Multimodal
        51670, -- Federated Learning for ICD Classification with Lightweight Models and
        53259, -- Power Transform Revisited: Numerically Stable, and Federated
        53260, -- Federated Computation of ROC and PR Curves
        54436, -- FedRE: A Representation Entanglement Framework for Model-Heterogeneous
        54725, -- Fed-SE: Federated Self-Evolution for Privacy-Constrained Multi-Environ
        55936, -- FlexMoRE: A Flexible Mixture of Rank-heterogeneous Experts for Efficie
        56037, -- FedPS: Federated data Preprocessing via aggregated Statistics
        56413, -- ProtegoFed: Backdoor-Free Federated Instruction Tuning with Interspers
        56682, -- EmbTracker: Traceable Black-box Watermarking for Federated Language Mo
        57568, -- EdgeDetect: Importance-Aware Gradient Compression with Homomorphic Agg
        57803, -- Sample Selection Using Multi-Task Autoencoders in Federated Learning w
        57804, -- Enhanced Privacy and Communication Efficiency in Non-IID Federated Lea
        58101, -- SafeLM: Unified Privacy-Aware Optimization for Trustworthy Federated L
        58635, -- FecalFed: Privacy-Preserving Poultry Disease Detection via Federated L
        59454, -- FED-HARGPT: A Hybrid Centralized-Federated Approach of a Transformer-b
        60198, -- Towards Privacy-Guaranteed Label Unlearning in Vertical Federated Lear
        60568, -- Revisiting Backdoor Threat in Federated Instruction Tuning from a Sign
        60752, -- Federated Gaussian Process Learning via Pseudo-Representations for Lar
        61605, -- Forecasting Energy Availability in Local Energy Communities via LSTM F
        62163, -- Learning to Collaborate: An Orchestrated-Decentralized Framework for P
        63124, -- Low Rank Comes with Low Security: Gradient Assembly Poisoning Attacks
        63169, -- AutoFed: Manual-Free Federated Traffic Prediction via Personalized Pro
        64801, -- ILoRA: Federated Learning with Low-Rank Adaptation for Heterogeneous C
        64998, -- A Unified Convergence Analysis for Semi-Decentralized Learning: Sample
        66320, -- Helmsman: Autonomous Synthesis of Federated Learning Systems via Multi
        67247, -- Robust Federated Anomaly Detection Using Dual-Signal Autoencoders: App
        68092, -- Learned Digital Codes for Over-the-Air Federated Learning
        68140, -- ToFU: Transforming How Federated Learning Systems Forget User Data
        68289, -- ParaAegis: Parallel Protection for Flexible Privacy-preserved Federate
        68334, -- FedMentor: Domain-Aware Differential Privacy for Heterogeneous Federat
        68509, -- DP-FedLoRA: Privacy-Enhanced Federated Fine-Tuning for On-Device Large
        68755, -- AI-in-the-Loop: Privacy Preserving Real-Time Scam Detection and Conver
        68851, -- FedMVP: Federated Multimodal Visual Prompt Tuning for Vision-Language
        68899, -- One-Shot Clustering for Federated Learning Under Clustering-Agnostic A
        69412, -- Federated Distillation on Edge Devices: Efficient Client-Side Filterin
        69775, -- FedJam: Multimodal Federated Learning Framework for Jamming Detection
        69956, -- Stabilizing Federated Learning under Extreme Heterogeneity with HeteRo
        70683, -- FedSWA: Improving Generalization in Federated Learning with Highly Het
        70854, -- FedVLM: Scalable Personalized Vision-Language Models through Federated
        70905, -- FairFedMed: Benchmarking Group Fairness in Federated Medical Imaging w
        71289, -- AdeptHEQ-FL: Adaptive Homomorphic Encryption for Federated Learning of
        71611, -- Spatio-Temporal Representation Decoupling and Enhancement for Federate
        71646, -- FedRef: Communication-Efficient Bayesian Fine-Tuning using a Reference
        71714, -- FedDAA: Dynamic Client Clustering for Concept Drift Adaptation in Fede
        71779, -- Federated Loss Exploration for Improved Convergence on Non-IID Data
        71844, -- FedFitTech: A Baseline in Federated Learning for Fitness Tracking
        71855, -- FLAME: Towards Federated Fine-Tuning Large Language Models Through Ada
        72284, -- HtFLlib: A Comprehensive Heterogeneous Federated Learning Library and
        72325, -- FlowerTune: A Cross-Domain Benchmark for Federated Fine-Tuning of Larg
        73222, -- SemSpaceFL: A Collaborative Hierarchical Federated Learning Framework
        73263, -- ReCIT: Reconstructing Full Private Data from Gradient in Parameter-Eff
        73303, -- Privacy-Preserving Federated Embedding Learning for Localized Retrieva
        73484, -- Federated Spectral Graph Transformers Meet Neural Ordinary Differentia
        73561, -- Boosting multi-demographic federated learning for chest radiograph ana
        73683, -- Federated Learning over 5G, WiFi, and Ethernet: Measurements and Evalu
        73832, -- FLIP: Towards Comprehensive and Reliable Evaluation of Federated Promp
        74017, -- Redefining non-IID Data in Federated Learning for Computer Vision Task
        74036, -- Federated Continual Instruction Tuning
        74406, -- Unlearning through Knowledge Overwriting: Reversible Federated Unlearn
        74436, -- FedMentalCare: Towards Privacy-Preserving Fine-Tuned LLMs to Analyze M
        74841, -- Mitigating Unintended Memorization with LoRA in Federated Learning for
        75245, -- FedSA: A Unified Representation Learning via Semantic Anchors for Prot
        75269, -- Ferrari: Federated Feature Unlearning via Optimizing Feature Sensitivi
        75413, -- Federated Heavy Hitter Analytics with Local Differential Privacy
        75679, -- Task Arithmetic Through The Lens Of One-Shot Federated Learning
        76027, -- FRAG: Toward Federated Vector Database Management for Collaborative an
        76100, -- Efficient Adaptive Federated Optimization
        76169, -- FedMAC: Tackling Partial-Modality Missing in Federated Learning with C
        76246, -- Infighting in the Dark: Multi-Label Backdoor Attack in Federated Learn
        76815, -- Towards Federated RLHF with Aggregated Client Preference for LLMs
        76895, -- Entity Augmentation for Efficient Classification of Vertically Partiti
        77156, -- Federated Learning with Bilateral Curation for Partially Class-Disjoin
        77177, -- Federating Dynamic Models using Early-Exit Architectures for Automatic
        77268, -- Harmonizing Generalization and Personalization in Federated Prompt Lea
        77294, -- DP-DyLoRA: Fine-Tuning Transformer-Based Models On-Device under Differ
        77310, -- FedStale: leveraging stale client updates in federated learning
        77436, -- SpamDam: Towards Privacy-Preserving and Adversary-Resistant SMS Spam D
        77586, -- An Upload-Efficient Scheme for Transferring Knowledge From a Server-Si
        77697, -- MeanCache: User-Centric Semantic Caching for LLM Web Services
        77994, -- FedTGP: Trainable Global Prototypes with Adaptive-Margin-Enhanced Cont
        78050, -- Federated Learning via Input-Output Collaborative Distillation
        78061, -- Foreseeing Reconstruction Quality of Gradient Inversion: An Optimizati
        78132, -- FedASMU: Efficient Asynchronous Federated Learning with Dynamic Stalen
        78136, -- PFLlib: A Beginner-Friendly and Comprehensive Personalized Federated L
        78293, -- Dynamic Fair Federated Learning Based on Reinforcement Learning
        78350, -- pFedLoRA: Model-Heterogeneous Personalized Federated Learning with LoR
        78385, -- Every Parameter Matters: Ensuring the Convergence of Federated Learnin
        78625, -- FedDAT: An Approach for Foundation Model Finetuning in Multi-Modal Het
        78831, -- Joint Downlink-Uplink Beamforming for Wireless Multi-Antenna Federated
        78865, -- DP-BREM: Differentially-Private and Byzantine-Robust Federated Learnin
        79023, -- Federated learning for secure development of AI models for Parkinson's
        79124, -- BadVFL: Backdoor Attacks in Vertical Federated Learning
        79199, -- Unimodal Training-Multimodal Prediction: Cross-modal Federated Learnin
        79212, -- FedGH: Heterogeneous Federated Learning with Generalized Global Header
        79268, -- Vertical Federated Graph Neural Network for Recommender System
        79326, -- MoDeST: Bridging the Gap between Federated and Decentralized Learning
        79341, -- Personalized Privacy-Preserving Framework for Cross-Silo Federated Lea
        79440, -- Federated Learning under Heterogeneous and Correlated Client Availabil
        79462, -- Federated Multi-Agent Deep Reinforcement Learning Approach via Physics
        79537, -- Collaborative Training of Medical Artificial Intelligence Models with
        79566, -- Improving Federated Learning Communication Efficiency with Global Mome
        79574, -- Quantifying the Impact of Label Noise on Federated Learning
        79846, -- TCT: Convexifying Federated Learning using Bootstrapped Neural Tangent
        79945, -- AsyncFedED: Asynchronous Federated Learning with Euclidean Distance ba
        79948, -- QUIC-FL: Quick Unbiased Compression for Federated Learning
        80153, -- Fully Decentralized, Scalable Gaussian Processes for Multi-Agent Feder
        80402, -- Papaya: Practical, Private, and Scalable Federated Learning
        80473, -- Privacy enabled Financial Text Classification using Differential Priva
        80566, -- EDEN: Communication-Efficient and Robust Distributed Mean Estimation f
        80715, -- DRIVE: One-bit Distributed Mean Estimation
        80837, -- Personalized Federated Learning using Hypernetworks
        83659, -- Learned Digital Codes for Over-the-Air Computation in Federated Edge L
        83992, -- Enhancing Visual Representation with Textual Semantics: Textual Semant
        84019, -- Generalized and Personalized Federated Learning with Black-Box Foundat
        84077, -- HFedATM: Hierarchical Federated Domain Generalization via Optimal Tran
        84562, -- Personalized Longitudinal Medical Report Generation via Temporally-Awa
        84567, -- DP-FedAdamW: An Efficient Optimizer for Differentially Private Federat
        84589, -- ProxyFL: A Proxy-Guided Framework for Federated Semi-Supervised Learni
        84687, -- Fed-ADE: Adaptive Learning Rate for Federated Post-adaptation under Di
        84718, -- HiLoRA: Hierarchical Low-Rank Adaptation for Personalized Federated Le
        84752, -- FedAFD: Multimodal Federated Learning via Adversarial Fusion and Disti
        84837, -- Federated Active Learning Under Extreme Non-IID and Global Class Imbal
        84866, -- Few-for-Many Personalized Federated Learning
        84884, -- FedBPrompt: Federated Domain Generalization Person Re-Identification v
        84909, -- Domain-Skewed Federated Learning with Feature Decoupling and Calibrati
        84989, -- FedRG: Unleashing the Representation Geometry for Federated Learning w
        85032, -- OmniFM: Toward Modality-Robust and Task-Agnostic Federated Learning fo
        85298, -- Submodel Extraction for Efficient and Personalized Federated Learning
        85300, -- FedDAP: Domain-Aware Prototype Learning for Federated Learning under D
        85320, -- From Selection to Scheduling: Federated Geometry-Aware Correction Make
        85475, -- Taming Noise-Induced Prototype Degradation for Privacy-Preserving Pers
        85476, -- FedHarmony: Harmonizing Heterogeneous Label Correlations in Federated
        85498, -- Fine-Tuning Impairs the Balancedness of Foundation Models in Long-tail
        85627, -- Federated Learning for Multivariate Time Series Anomaly Detection in I
        85711, -- Adaptive LoRA Experts Allocation and Selection for Federated Fine-Tuni
        85712, -- FedEL: Federated Elastic Learning for Heterogeneous Devices
        85768, -- FedQS: Optimizing Gradient and Model Aggregation for Semi-Asynchronous
        85769, -- FORLA:Federated Object-centric Representation Learning with Slot Atten
        85814, -- Personalized Bayesian Federated Learning with Wasserstein Barycenter A
        86012, -- C${}^2$Prompt: Class-aware Client Knowledge Interaction for Federated
        86073, -- Personalized Subgraph Federated Learning with Differentiable Auxiliary
        86085, -- Layer-wise Update Aggregation with Recycling for Communication-Efficie
        86115, -- OmniFC: Rethinking Federated Clustering via Lossless and Secure Distan
        86199, -- Towards Effective Federated Graph Foundation Model via Mitigating Know
        86228, -- Sketched Gaussian Mechanism for Private Federated Learning
        86306, -- FedRTS: Federated Robust Pruning via Combinatorial Thompson Sampling
        86358, -- Exact and Linear Convergence for Federated Learning under Arbitrary Cl
        86522, -- Adaptive Latent-Space Constraints in Personalized FL
        86653, -- Robust Federated Finetuning of LLMs via Alternating Optimization of Lo
        86662, -- MARS: A Malignity-Aware Backdoor Defense in Federated Learning
        86759, -- Sharp Gaussian approximations for Decentralized Federated Learning
        86799, -- Tackling Feature-Classifier Mismatch in Federated Learning via Prompt-
        86833, -- Multiplayer Federated Learning: Reaching Equilibrium with Less Communi
        86847, -- Resource-Constrained Federated Continual Learning: What Does Matter?
        86848, -- Feature Distillation is the Better Choice for Model-Heterogeneous Fede
        86954, -- Streaming Federated Learning with Markovian Data
        86956, -- Covariances for Free: Exploiting Mean Distributions for Training-free
        87059, -- A Unified Analysis of Stochastic Gradient Descent with Arbitrary Data
        87065, -- Differentially Private Federated Low Rank Adaptation Beyond Fixed-Matr
        87087, -- Efficient Federated Learning against Byzantine Attacks and Data Hetero
        87276, -- FedFACT: A Provable Framework for Controllable Group-Fairness Calibrat
        87282, -- Ravan: Multi-Head Low-Rank Adaptation for Federated Fine-Tuning
        87311, -- Global Prompt Refinement with Non-Interfering Attention Masking for On
        87312, -- Class-wise Balancing Data Replay for Federated Class-Incremental Learn
        87341, -- PREAMBLE: Private and Efficient Aggregation via Block Sparse Vectors
        87456, -- Tracing Back the Malicious Clients in Poisoning Attacks to Federated L
        87457, -- Competitive Advantage Attacks to Decentralized Federated Learning
        87475, -- Decentralized Dynamic Cooperation of Personalized Models for Federated
        87607, -- A Framework for Double-Blind Federated Adaptation of Foundation Models
        87610, -- FedPall: Prototype-based Adversarial and Collaborative Learning for Fe
        87677, -- Mind the Cost of Scaffold! Benign Clients May Even Become Accomplices
        87716, -- FedDifRC: Unlocking the Potential of Text-to-Image Diffusion Models in
        87769, -- Towards Privacy-preserved Pre-training of Remote Sensing Foundation Mo
        87834, -- Client2Vec: Improving Federated Learning by Distribution Shifts Aware
        87837, -- Cooperative Pseudo Labeling for Unsupervised Federated Classification
        87942, -- FedMeNF: Privacy-Preserving Federated Meta-Learning for Neural Fields
        87996, -- Geminio: Language-Guided Gradient Inversion Attacks in Federated Learn
        88010, -- Soft Separation and Distillation: Toward Global Uniformity in Federate
        88042, -- Class-Wise Federated Averaging for Efficient Personalization
        88057, -- Forgetting Through Transforming: Enabling Federated Unlearning via Cla
        88079, -- Latte: Collaborative Test-Time Adaptation of Vision-Language Models in
        88107, -- FedVLA: Federated Vision-Language-Action Learning with Dual Gating Mix
        88173, -- Find a Scapegoat: Poisoning Membership Inference Attack and Defense to
        88187, -- EFTViT: Efficient Federated Training of Vision Transformers with Maske
        88202, -- You Are Your Own Best Teacher: Achieving Centralized-level Performance
        88224, -- Federated Domain Generalization with Domain-specific Soft Prompts Gene
        88371, -- FedWSQ: Efficient Federated Learning with Weight Standardization and D
        88591, -- Voronoi-grid-based Pareto Front Learning and Its Application to Collab
        88625, -- Provably Near-Optimal Federated Ensemble Distillation with Negligible
        88631, -- Local Pan-privacy for Federated Analytics
        88662, -- Federated In-Context Learning: Iterative Refinement for Improved Answe
        88707, -- Understanding the Statistical Accuracy-Communication Trade-off in Pers
        88758, -- DMM: Distributed Matrix Mechanism for Differentially-Private Federated
        88899, -- Private Model Personalization Revisited
        88927, -- Privacy-Preserving Federated Convex Optimization: Balancing Partial-Pa
        89160, -- Hybrid Batch Normalisation: Resolving the Dilemma of Batch Normalisati
        89191, -- Theoretically Unmasking Inference Attacks Against LDP-Protected Client
        89204, -- Uncertainty-Based Extensible Codebook for Discrete Federated Learning
        89270, -- FedECADO: A Dynamical System Model of Federated Learning
        89380, -- Scaffold with Stochastic Gradients: New Analysis with Linear Speed-Up
        89384, -- On-Device Collaborative Language Modeling via a Mixture of Generalists
        89406, -- Generalization in Federated Learning: A Conditional Mutual Information
        89416, -- Interaction-Aware Gaussian Weighting for Clustered Federated Learning
        89446, -- One-Shot Heterogeneous Federated Learning with Local Model-Guided Diff
        89450, -- FedBEns: One-Shot Federated Learning based on Bayesian Ensemble
        89454, -- SecEmb: Sparsity-Aware Secure Federated Learning of On-Device Recommen
        89467, -- Multi-Session Budget Optimization for Forward Auction-based Federated
        89569, -- Leveraging Randomness in Model and Data Partitioning for Privacy Ampli
        89718, -- Certifiably Robust Model Evaluation in Federated Learning under Meta-D
        89806, -- FedOne: Query-Efficient Federated Learning for Black-box Discrete Prom
        89807, -- Federated Incomplete Multi-view Clustering with Globally Fused Graph G
        89861, -- S2FGL: Spatial Spectral Federated Graph Learning
        89891, -- The Panaceas for Improving Low-Rank Decomposition in Communication-Eff
        89898, -- FOCoOp: Enhancing Out-of-Distribution Robustness in Federated Prompt L
        89928, -- Towards Trustworthy Federated Learning with Untrusted Participants
        89985, -- Federated Generalised Variational Inference: A Robust Probabilistic Fe
        90115, -- Handling Spatial-Temporal Data Heterogeneity for Federated Continual L
        90149, -- FedAWA: Adaptive Optimization of Aggregation Weights in Federated Lear
        90158, -- FedMIA: An Effective Membership Inference Attack Exploiting "All for O
        90245, -- From Laboratory to Real World: A New Benchmark Towards Privacy-Preserv
        90324, -- dFLMoE: Decentralized Federated Learning via Mixture of Experts for Me
        90399, -- Model Poisoning Attacks to Federated Learning via Multi-Round Consiste
        90448, -- Mind the Gap: Confidence Discrepancy Can Guide Federated Semi-Supervis
        90459, -- A Simple Data Augmentation for Feature Distribution Skewed Federated L
        90557, -- Federated Learning with Domain Shift Eraser
        90625, -- NoT: Federated Unlearning via Weight Negation
        90635, -- Detecting Backdoor Attacks in Federated Learning via Direction Alignme
        90723, -- Beyond Local Sharpness: Communication-Efficient Global Sharpness-aware
        90858, -- Patient-Level Anatomy Meets Scanning-Level Physics: Personalized Feder
        90866, -- FedBiP: Heterogeneous One-Shot Federated Learning with Personalized La
        91031, -- DEPT: Decoupled Embeddings for Pre-training Language Models
        91203, -- Privacy-Preserving Personalized Federated Prompt Learning for Multimod
        91214, -- GRAIN: Exact Graph Reconstruction from Gradients
        91376, -- Decoupled Subgraph Federated Learning
        91446, -- Emerging Safety Attack and Defense in Federated Instruction Tuning of
        91466, -- Federated Domain Generalization with Data-free On-server Matching Grad
        91467, -- FedLWS: Federated Learning with Adaptive Layer-wise Weight Shrinking
        91567, -- Differentially Private Federated Learning with Time-Adaptive Privacy S
        91573, -- Federated Granger Causality Learning For Interdependent Clients With S
        91576, -- Closed-Form Merging of Parameter-Efficient Modules for Federated Conti
        91598, -- Mixture of Experts Made Personalized: Federated Prompt Learning for Vi
        91624, -- Debiasing Federated Learning with Correlated Client Participation
        91639, -- Unlocking the Potential of Model Calibration in Federated Learning
        91646, -- On the Linear Speedup of Personalized Federated Reinforcement Learning
        91677, -- Can Textual Gradient Work in Federated Learning?
        91688, -- Federated Continual Learning Goes Online: Uncertainty-Aware Memory Man
        91756, -- Enhancing Clustered Federated Learning: Integration of Strategies and
        91806, -- PRISM: Privacy-Preserving Improved Stochastic Masking for Federated Ge
        91991, -- On the Byzantine-Resilience of Distillation-Based Federated Learning
        92002, -- Enhancing Federated Domain Adaptation with Multi-Domain Prototype-Base
        92091, -- Federated Class-Incremental Learning: A Hybrid Approach Using Latent E
        92106, -- Asynchronous Federated Reinforcement Learning with Policy Gradient Upd
        92108, -- Vertical Federated Learning with Missing Features During Training and
        92193, -- Methods with Local Steps and Random Reshuffling for Generally Smooth N
        92228, -- Connecting Federated ADMM to Bayes
        92280, -- Achieving Dimension-Free Communication in Federated Learning via Zerot
        92388, -- Decentralized Sporadic Federated Learning: A Unified Algorithmic Frame
        92441, -- LoCoDL: Communication-Efficient Distributed Learning with Local Traini
        92684, -- A Unified Federated Framework for Trajectory Data Preparation via LLMs
        92755, -- RESFL: An Uncertainty-Aware Framework for Responsible Federated Learni
        92862, -- FLoRG: Federated Fine-tuning with Low-rank Gram Matrices and Procruste
        92992, -- Byzantine-Robust Federated Learning with Learnable Aggregation Weights
        93036, -- Convergent Differential Privacy Analysis for General Federated Learnin
        93115, -- The Gaussian-Head OFL Family: One-Shot Federated Learning from Client
        93225, -- Deploying Models to Non-participating Clients in Federated Learning wi
        93265, -- Robust Federated Inference
        93308, -- Tighter Performance Theory of FedExProx
        93412, -- Deep Latent Variable Model based Vertical Federated Learning with Flex
        93456, -- Low-pass Personalized Subgraph Federated Recommendation
        93465, -- FedDAG: Clustered Federated Learning via Global Data and Gradient Inte
        93528, -- Mitigating Non-IID Drift in Zeroth-Order Federated LLM Fine-Tuning wit
        93532, -- Co-LoRA: Collaborative Model Personalization on Heterogeneous Multi-Mo
        93612, -- Incentives in Federated Learning with Heterogeneous Agents
        93772, -- Toward Enhancing Representation Learning in Federated Multi-Task Setti
        93805, -- Federated Learning of Quantile Inference under Local Differential Priv
        93814, -- Non-Convex Federated Optimization under Cost-Aware Client Selection
        93824, -- Converge Faster, Talk Less: Hessian-Informed Federated Zeroth-Order Op
        93829, -- Traceable Black-Box Watermarks For Federated Learning
        93858, -- Riemannian Federated Learning via Averaging Gradient Streams
        93883, -- Protection against Source Inference Attacks in Federated Learning
        93924, -- A Federated Generalized Expectation-Maximization Algorithm for Mixture
        94009, -- Federated ADMM from Bayesian Duality
        94060, -- pFedMMA: Personalized Federated Fine-Tuning with Multi-Modal Adapter f
        94068, -- FedMuon: Federated Learning with Bias-corrected LMO-based Optimization
        94319, -- Bridging Generalization Gap of Heterogeneous Federated Clients Using G
        94416, -- Layerwise Federated Learning for Heterogeneous Quantum Clients using Q
        94470, -- Developmental Federated Tuning: A Cognitive-Inspired Paradigm for Effi
        94521, -- SABRE-FL: Selective and Accurate Backdoor Rejection for Federated Prom
        94541, -- Heterogeneous Federated Fine-Tuning with Parallel One-Rank Adaptation
        94605, -- Rethinking LoRA for Privacy-Preserving Federated Learning in Large Mod
        94628, -- DeepAFL: Deep Analytic Federated Learning
        94676, -- Proving the Limited Scalability of Centralized Distributed Optimizatio
        94777, -- Federated Learning with Profile Mapping under Distribution Shifts and
        94806, -- Beyond Aggregation: Guiding Clients in Heterogeneous Federated Learnin
        94918, -- SHE-LoRA: Selective Homomorphic Encryption for Federated Tuning with H
        95000, -- FeDaL: Federated Dataset Learning for General Time Series Foundation M
        95562, -- Distributed AI for Robotics
        96865, -- Communication-Efficient Module-Wise Federated Learning for Grasp Pose
        97220, -- Tiny-DroNeRF: Tiny Neural Radiance Fields Aboard Federated Learning-En
        97297, -- Informed Federated Learning to Train a Robotic Arm Inverse Dynamic Mod
        98029, -- FedSDR: Federated Graph Learning with Structural Noise Detection and R
        98078, -- Few-for-Many Personalized Federated Learning (FedFewS) (AutoSOTA)
        98754, -- FedOT: Ownership Verification and Leakage Tracing via Watermarks for F
        99198, -- Delayed Momentum Aggregation: Communication-efficient Byzantine-robust
        99296, -- FedTreeLoRA: Reconciling Statistical and Functional Heterogeneity in F
        99337, -- BESplit: Bias-Compensated Split Federated Learning with Evidential Agg
        99348, -- DANCE: Dynamic, Available, Neighbor-gated Condensation for Federated T
        99367, -- Trustworthy Federated Label Distribution Learning under Annotation Qua
        99370, -- Federated Bilevel Performative Prediction
        99376, -- Regret-Based Federated Causal Discovery with Unknown Interventions
        99387, -- HO-SFL: Hybrid-Order Split Federated Learning with Backprop-Free Clien
        99439, -- Shift-Dependent Asymmetry: Orthogonal Inverse Low-Rank Adaptation for
        99706, -- Don't Reinvent the Wheel, Just Realign the Spokes: Resource-Efficient
        99986, -- FedSDR: Federated Self-Distillation with Rectification
        100460, -- Collaborative Threshold Watermarking
        100610, -- FedEBA+: Towards Fair and Effective Federated Learning via Entropy-Bas
        100698, -- Breaking the Capacity Bottleneck in Model-Heterogeneous Federated Lear
        100712, -- Learning Locally, Revising Globally: Global Reviser for Federated Lear
        100770, -- UB-SMoE: Universally Balanced Sparse Mixture-of-Experts for Resource-a
        100832, -- Federated Learning with Unlabeled Clients: Personalization Can Happen
        100845, -- Heterogeneity-Aware Knowledge Sharing for Graph Federated Learning
        100993, -- FedRGL: Robust Federated Graph Learning under Label Noise
        101060, -- FedRot-LoRA: Mitigating Rotational Misalignment in Federated LoRA
        101099, -- Adaptive Personalized Federated Learning via Multi-task Averaging of K
        101154, -- Federated Causal Inference on Multi-Site Observational Data via Propen
        101350, -- FedReLa: Imbalanced Federated Learning via Re-Labeling
        101445, -- Decoupled Training with Local Reinforcement Fine-Tuning in Federated L
        101474, -- Federated Distillation for Whole Slide Image via Gaussian-Mixture Feat
        101540, -- Federated Variational Preference Alignment with Gumbel-Softmax Prior f
        101592, -- Scaling Unsupervised Multi-Source Federated Domain Adaptation through
        101630, -- Clipping Makes Distributed and Federated Asynchronous SGD Robust to St
        101663, -- FedHPro: Federated Hyper-Prototype Learning via Gradient Matching
        101851, -- CLoVE: Personalized Federated Learning through Clustering of Loss Vect
        101998, -- Accurate, Private, Secure, Federated U-statistics with Higher Degree
        102154, -- FedQueue: Queue-Aware Federated Learning for Cross-Facility HPC Traini
        102260, -- Distribution Alignment for One-Shot Federated Learning via Optimal Tra
        102272, -- Distributed Direct Preference Optimization
        102278, -- Server-Proximal Aggregation for Federated Domain-Incremental Learning
        102671, -- DP-FedSOFIM: Differentially Private Federated Stochastic Optimization
        103102, -- FedProxy: Federated Fine-Tuning of LLMs via Proxy SLMs and Heterogenei
        103126, -- Beyond End-to-End: Dynamic Chain Optimization for Private LLM Adaptati
        103263, -- Safe-FedLLM: Delving into the Safety of Federated Large Language Model
        103271, -- DFAMS: Dynamic-flow guided Federated Alignment based Multi-prototype S
        103435, -- CO-EVO: Co-evolving Semantic Anchoring and Style Diversification for F
        103618, -- FedMental: Evaluating Federated Learning for Mental Health Detection f
        103652, -- SecureGate: Learning When to Reveal PII Safely via Token-Gated Dual-Ad
        103799, -- Exploring Cross-Client Memorization of Training Data in Large Language
        104093, -- MHARFedLLM: Multimodal Human Activity Recognition Using Federated Larg
        104116, -- Freezing of Gait Detection Using Gramian Angular Fields and Federated
        104119, -- Towards Adaptive Asynchronous Federated Learning for Human Activity Re
        104121, -- CDFL: Efficient Federated Human Activity Recognition using Contrastive
        104995, -- Bridging Knowledge Discrepancy in Retinal Image Analysis through Feder
        105086, -- Decentralized Noise Handling in Medical Imaging: Encoder-Decoder Based
        105149, -- Embedding-Based Federated Data Sharing via Differentially Private Cond
        105171, -- Equitable Federated Learning with NCA
        105193, -- FedAMM: Federated Learning for Brain Tumor Segmentation with Arbitrary
        105194, -- FedCLAM: Client Adaptive Momentum with Foreground Intensity Matching f
        105195, -- FedWSIDD: Federated Whole Slide Image Classification via Dataset Disti
        105243, -- GradInvDiff: Stealing Medical Privacy in Federated Learning via Diffus
        105289, -- Hypergraph-Guided Federated Distillation Learning for Efficient and Ro
        105386, -- Maverick: Collaboration-free Federated Unlearning for Medical Privacy
        105531, -- Personalized Federated Side-Tuning for Medical Image Classification
        105571, -- Prototype-Guided and Lightweight Adapters for Inherent Interpretation
        105608, -- Restyled, Tuning, and Alignment: Taming VLMs for Federated Non-IID Med
        105613, -- Revisit the Stability of Vanilla Federated Learning Under Diverse Cond
        105658, -- Shuffle-Diversity Collaborative Federated Learning for Imbalanced Medi
        105733, -- Temporal Model-Based Federated Active Medical Image Classification
        106326, -- FERA: Uncertainty-Aware Federated Reasoning for Large Language Models
        106436, -- Scaling Law Analysis in Federated Learning: How to Select the Optimal
        106553, -- Breaking the Aggregation Bottleneck in Federated Recommendation: A Per
        106611, -- Personalized Federated Learning with Bidirectional Communication Compr
        106641, -- Causality-inspired Federated Learning for Dynamic Spatio-Temporal Grap
        106657, -- Enhanced Federated Deep Multi-View Clustering Under Uncertainty Scenar
        106814, -- CoRe-Fed: Bridging Collaborative and Representation Fairness via Feder
        106817, -- FedTopo: Topology-Informed Representation Alignment in Federated Learn
        106825, -- Towards Federated Clustering: A Client-wise Private Graph Aggregation
        106873, -- HealSplit: Towards Self-Healing Through Adversarial Distillation in Sp
        106906, -- Plug-and-Play Parameter-Efficient Tuning of Embeddings for Federated R
        106945, -- Topological Federated Clustering via Gravitational Potential Fields Un
        107054, -- Federated Linear Dueling Bandits
        107096, -- FedGRPO: Privately Optimizing Foundation Models with Group-Relative Re
        107097, -- Multi-Modal Style Transfer-based Prompt Tuning for Efficient Federated
        107099, -- FedPM: Federated Learning Using Second-order Optimization with Precond
        107108, -- DSFedMed: Dual-Scale Federated Medical Image Segmentation via Mutual D
        107111, -- Bant: Byzantine Antidote via Trial Function and Trust Scores
        107302, -- Federated Vision-Language-Recommendation with Personalized Fusion
        107318, -- Data Heterogeneity and Forgotten Labels in Split Federated Learning
        107322, -- Horizontal and Vertical Federated Causal Structure Learning via Higher
        107343, -- Bi-level Personalization for Federated Foundation Models: A Task-vecto
        107359, -- LSHFed: Robust and Communication-Efficient Federated Learning with Loc
        107387, -- FedP²EFT: Federated Learning to Personalize PEFT for Multilingual LLMs
        107407, -- SMoFi: Step-wise Momentum Fusion for Split Federated Learning on Heter
        107586, -- Unlocking Dynamic Inter-Client Spatial Dependencies: A Federated Spati
        107597, -- Tackling Resource-Constrained and Data-Heterogeneity in Federated Lear
        107643, -- TOFA: Training-Free One-Shot Federated Adaptation for Vision-Language
        107645, -- TransFR: Transferable Federated Recommendation with Adapter Tuning on
        107652, -- Enhanced Privacy Leakage from Noise-Perturbed Gradients via Gradient-G
        107655, -- FedSDA: Federated Stain Distribution Alignment for Non-IID Histopathol
        107701, -- FedARKS: Federated Aggregation via Robust and Discriminative Knowledge
        107726, -- REMISVFU: Vertical Federated Unlearning via Representation Misdirectio
        107780, -- Divide, Conquer and Unite: Hierarchical Style-Recalibrated Prototype A
        107791, -- FedAU2: Attribute Unlearning for User-Level Federated Recommender Syst
        107813, -- SFedHIFI: Fire Rate-Based Heterogeneous Information Fusion for Spiking
        107947, -- Federated CLIP for Resource-Efficient Heterogeneous Medical Image Clas
        108020, -- Communication-Efficient Heterogeneous Federated Learning with Sparse P
        108161, -- Optimal Look-back Horizon for Time Series Forecasting in Federated Lea
        108170, -- FedALT: Federated Fine-Tuning Through Adaptive Local Training with Res
        108214, -- FedSDWC: Federated Synergistic Dual-Representation Weak Causal Learnin
        108326, -- FedAdamW: A Communication-Efficient Optimizer with Convergence and Gen
        108371, -- Poisoning with a Pill: Circumventing Detection in Federated Learning
        108374, -- FedMerge: Federated Model Merging for Personalization
        108378, -- FedSEA-LLaMA: A Secure, Efficient and Adaptive Federated Splitting Fra
        108403, -- Oblivionis: A Lightweight Learning and Unlearning Framework for Federa
        108482, -- Feature-Aware One-Shot Federated Learning via Hierarchical Token Seque
        108502, -- FedShard: Federated Unlearning with Efficiency Fairness and Performanc
        108508, -- FedCure: Mitigating Participation Bias in Semi-Asynchronous Federated
        109239, -- Personalized Federated Learning with Hidden Information on Personalize
        109696, -- Hybrid Quantum-inspired Kolmogorov-Arnold Networks for Privacy-Aware F
        110073, -- pFedGPT: Hierarchically Optimizing LoRA Aggregation Weights for Person
        110191, -- X-FLoRA: Cross-modal Federated Learning with Modality-expert LoRA for
        110397, -- PPC-GPT: Federated Task-Specific Compression of Large Language Models
        110419, -- Multilingual Federated Low-Rank Adaptation for Collaborative Content A
        110603, -- EcoLoRA: Communication-Efficient Federated Fine-Tuning of Large Langua
        111397, -- Federated Learning with Feature Space Separation for Speaker Recogniti
        111500, -- Regularized Federated Learning for Privacy-Preserving Dysarthric and E
        112541, -- Fisher Calibration for Backdoor-Robust Heterogeneous Federated Learnin
        112599, -- SkyMask: Attack-agnostic Robust Federated Learning with Fine-grained L
        112759, -- Diffusion-Driven Data Replay: A Novel Approach to Combat Forgetting in
        112762, -- Unveiling Privacy Risks in Stochastic Neural Networks Training: Effect
        112821, -- Federated Learning with Local Openset Noisy Labels
        113003, -- Personalized Federated Domain-Incremental Learning based on Adaptive K
        113038, -- FedRA: A Random Allocation Strategy for Federated Tuning to Unleash th
        113124, -- FedVAD: Enhancing Federated Video Anomaly Detection with GPT-Driven Se
        113239, -- Distributed Active Client Selection With Noisy Clients Using Model Ass
        113262, -- Pick-a-back: Selective Device-to-Device Knowledge Transfer in Federate
        113289, -- FedHARM: Harmonizing Model Architectural Diversity in Federated Learni
        113325, -- PILoRA: Prototype Guided Incremental LoRA for Federated Class-Incremen
        113423, -- FedHide: Federated Learning by Hiding in the Neighbors
        113444, -- Feature Diversification and Adaptation for Federated Domain Generaliza
        113537, -- Unlocking the Potential of Federated Learning: The Symphony of Dataset
        113556, -- PFedEdit: Personalized Federated Learning via Automated Model Editing
        113559, -- SuperFedNAS: Cost-Efficient Federated Neural Architecture Search for O
        113594, -- Overcome Modal Bias in Multi-modal Federated Learning via Balanced Mod
        113620, -- Local and Global Flatness for Federated Domain Generalization
        113631, -- FedTSA: A Cluster-based Two-Stage Aggregation Method for Model-heterog
        114332, -- A New Perspective to Boost Performance Fairness For Medical Federated
        114424, -- CAR-MFL: Cross-Modal Augmentation by Retrieval for Multimodal Federate
        114887, -- Enable the Right to be Forgotten with Federated Client Unlearning in M
        114895, -- Enhancing Federated Learning Performance Fairness via Collaboration Gr
        114919, -- FACMIC: Federated Adaptative CLIP Model for Medical Image Classificati
        114929, -- Federated Multi-Centric Image Segmentation with Uneven Label Distribut
        114930, -- FedEvi: Improving Federated Medical Image Segmentation via Evidential
        114931, -- FedFMS: Exploring Federated Foundation Models for Medical Image Segmen
        114932, -- FedIA: Federated Medical Image Segmentation with Heterogeneous Annotat
        114933, -- FedMedICL: Towards Holistic Evaluation of Distribution Shifts in Feder
        114934, -- FedMLP: Federated Multi-Label Medical Image Classification under Task
        114935, -- FedMRL: Data Heterogeneity Aware Federated Multi-agent Deep Reinforcem
        114956, -- FUNAvg: Federated Uncertainty Weighted Averaging for Datasets with Div
        115118, -- MH-pFLGB: Model Heterogeneous personalized Federated Learning via Glob
        115183, -- Overcoming Atlas Heterogeneity in Federated Learning for Cross-site Co
        115201, -- pFLFE: Cross-silo Personalized Federated Learning via Feature Enhancem
        115289, -- SiFT: A Serial Framework with Textual Guidance for Federated Learning
        115321, -- Stealing Knowledge from Pre-trained Language Models for Federated Clas
        115449, -- Fair Federated Learning under Domain Skew with Local Consistency and D
        115536, -- Think Twice Before Selection: Federated Evidential Active Learning for
        115618, -- Communication-Efficient Federated Learning with Accelerated Client Gra
        115696, -- Revamping Federated Learning Security from a Defender's Perspective: A
        115715, -- FLHetBench: Benchmarking Device and State Heterogeneity in Federated L
        115719, -- An Aggregation-Free Federated Learning for Tackling Data Heterogeneity
        115915, -- DiPrompT: Disentangled Prompt Tuning for Multiple Latent Domain Genera
        115950, -- Byzantine-robust Decentralized Federated Learning via Dual-domain Clus
        115989, -- Device-Wise Federated Network Pruning
        115996, -- FedSelect: Personalized Federated Learning with Customized Selection o
        116000, -- FedAS: Bridging Inconsistency in Personalized Federated Learning
        116052, -- FedUV: Uniformity and Variance for Heterogeneous Federated Learning
        116053, -- FedSOL: Stabilized Orthogonal Learning with Proximal Restrictions in F
        116063, -- PerAda: Parameter-Efficient Federated Learning Personalization with Ge
        116125, -- Text-Enhanced Data-free Approach for Federated Class-Incremental Learn
        116259, -- FedHCA2: Towards Hetero-Client Federated Multi-Task Learning
        116328, -- Efficiently Assemble Normalization Layers and Regularization for Feder
        116342, -- Federated Generalized Category Discovery
        116705, -- Federated Online Adaptation for Deep Stereo
        116714, -- Traceable Federated Continual Learning
        116757, -- Leak and Learn: An Attacker's Cookbook to Train Using Leaked Data from
        116783, -- Relaxed Contrastive Learning for Federated Learning
        116924, -- Rethinking the Representation in Federated Unsupervised Learning with
        116939, -- Global and Local Prompts Cooperation via Optimal Transport for Federat
        116954, -- Unlocking the Potential of Prompt-Tuning in Bridging Generalized and P
        117069, -- Decentralized Directed Collaboration for Personalized Federated Learni
        117085, -- Data Valuation and Detections in Federated Learning
        117104, -- Mixed-Precision Quantization for Federated Learning on Resource-Constr
        117205, -- Towards Efficient Replay in Federated Incremental Learning
        117245, -- Adaptive Hyper-graph Aggregation for Modality-Agnostic Federated Learn
        118117, -- Diffusion to Obfuscation: Time-Adaptive Synthesized Generation Against
        118119, -- Identifiable Gated Residual Personalization for Federated Parameter-Ef
        118141, -- H-SFP: Hierarchical Federated Learning with Decoupled Split-Model Prot
        118142, -- FedNASP: Federated Vision-Language Navigation with Adaptive Step-wise
        118155, -- Benchmarking Federated Learning &amp; Knowledge Distillation for Point
        118161, -- FedDO: Dynamic Client Optimization for Adaptive Federated Learning
        118165, -- Prototype Normalization: Optimizing Prototype Separation for Heterogen
        118178, -- Prevention over Correction: Learning Aligned Representations in One-sh
        118179, -- FedMental: Topology-Aware Federated Prototype Learning for Polymorphic
        118195, -- Fisher-Routed Mixture of Experts for Federated Class-Incremental Learn
        118206, -- Data-Free Client Contribution Estimation via Logit Maximization for Fe
        118209, -- Neural Collapse-Inspired Multi-Label Federated Learning under Label-Di
        118230, -- FeDepth: Federated Learning for Depth Estimation under Robot Heterogen
        118231, -- SUM: Unified Geometric Surgery on Spatio-Temporal Adaptation Vectors f
        118765, -- Capturing Spectral and Spatial Patterns for Federated Remote Sensing S
        119119, -- Proteus: Model Leakage-Induced Adversarial Attack in Federated Learnin
        119440, -- AnaPFL: When Closed-Form Solutions Meet Generalizationand Personalizat
        119924, -- FedCALM: Conflict-aware Layer-wise Mitigation for Selective Aggregatio
        120107, -- Gradient Inversion Attacks on Parameter-Efficient Fine-Tuning
        120114, -- Population Normalization for Federated Learning
        120136, -- FedCS: Coreset Selection for Federated Learning
        120234, -- F^3OCUS - Federated Finetuning of Vision-Language Foundation Models wi
        120388, -- pFedMxF: Personalized Federated Class-Incremental Learning with Mixtur
        120409, -- Subspace Constraint and Contribution Estimation for Heterogeneous Fede
        120465, -- HistoFS: Non-IID Histopathologic Whole Slide Image Classification via
        120492, -- Fortifying Federated Learning Towards Trustworthiness via Auditable Da
        120549, -- FedSPA: Generalizable Federated Graph Learning under Homophily Heterog
        120705, -- Personalized Federated Training of Diffusion Models with Privacy Guara
        120715, -- Pose-guided Enriched Feature Learning for Federated-by-camera Person R
        120753, -- Computation and Communication Efficient Federated Unlearning via On-se
        120759, -- FedMPT: Federated Multi-Label Prompt Tuning of Vision-Language Models
        120877, -- FedCART: Tackling Long-Tailed Distributions in Federated Adversarial T
        120892, -- GDFA: Geometry-Driven Federated Unlearning with Directional Task Vecto
        120908, -- Towards Stable Federated Continual Test-Time Adaptation in Wild World
        120932, -- FedSDR: Federated Graph Learning with Structural Noise Detection and R
        120962, -- OS-Fed: One Snapshot Is All You Need
        120974, -- Eliminate Distance Differences Induced by Backdoor Attacks: Layer-Sele
        121054, -- Domain Sensitive Federated Learning with Fisher-Informed Pruning
        121061, -- FedARA: Resource-adaptive Low-rank Personalized Federated Learning via
        121208, -- FedRAC: Rolling Submodel Allocation for Collaborative Fairness in Fede
        121242, -- Stealing Split Learning Bottom Models by Recovering Embedding Geometry
        121254, -- FedAdamom: Adaptive Momentum for Improved Generalization in Federated
        121275, -- Single-Round Scalable Analytic Federated Learning
        121394, -- FedMOP: Achieving Enhanced Privacy and Performance in Federated Learni
        121550, -- FedAlign: Differentially Private Distribution Alignment for Non-IID Fe
        121564, -- Batman: Benign Knowledge Alignment Through Malicious Null Space in Fed
        121608, -- Guiding Diffusion Models with Fine-Grained Conditions and Semantics-Pr
        121726, -- Controllable Federated Prompt Learning at Test Time
        121748 -- FedSST: Rethinking Fair Federated Graph Learning under Structural Shif
  );

DELETE FROM paper_method_exclusions x
USING federated_learning_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM federated_learning_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM federated_learning_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: federated learning is mentioned only as motivation, an application area or a baseline, or "federated" refers to federated search, identity or knowledge graphs.
CREATE TEMP TABLE federated_learning_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'federated-learning'
  AND p.id IN (
        1010, -- Deep Gradient Compression Reduce the Communication Bandwidth For distr
        1011, -- Deep Gradient Compression: Reducing the Communication Bandwidth for Di
        1607, -- MD-GAN: Multi-Discriminator Generative Adversarial Networks for Distri
        9510, -- PRANC: Pseudo RAndom Networks for Compacting deep models
        12271, -- Efficient On-device Training via Gradient Filtering
        12484, -- OvarNet: Towards Open-vocabulary Object Attribute Recognition
        12781, -- On the Efficacy of Differentially Private Few-shot Image Classificatio
        13130, -- Experimenting with Emerging RISC-V Systems for Decentralised Machine L
        17792, -- Towards Sybil Resilience in Decentralized Learning
        18222, -- Layer-wise Linear Mode Connectivity
        18287, -- Tangent Model Composition for Ensembling and Continual Fine-tuning
        19657, -- Understanding Hessian Alignment for Domain Generalization
        20246, -- Towards Real-World Burst Image Super-Resolution: Benchmark and Method
        20510, -- EgoObjects: A Large-Scale Egocentric Dataset for Fine-Grained Object U
        22072, -- Privacy Preservation in Artificial Intelligence and Extended Reality (
        22088, -- Survey of Vulnerabilities in Large Language Models Revealed by Adversa
        25132, -- Accelerated Convergence of Stochastic Heavy Ball Method under Anisotro
        28131, -- Decentralised Traffic Incident Detection via Network Lasso
        28401, -- Training Machine Learning models at the Edge: A Survey
        28697, -- DrJAX: Scalable and Differentiable MapReduce Primitives in JAX
        28724, -- RSBuilding: Towards General Remote Sensing Image Building Extraction a
        32199, -- Local Methods with Adaptivity via Scaling
        32699, -- Scholarly Question Answering using Large Language Models in the NFDI4D
        36433, -- A Survey for Large Language Models in Biomedicine
        39658, -- ATM: Improving Model Merging by Alternating Tuning and Merging
        40788, -- A Comprehensive Guide to Explainable AI: From Classical Models to LLMs
        41428, -- Deep Learning Model Security: Threats and Defenses
        42484, -- Efficient Deployment of Large Language Models on Resource-constrained
        45369, -- Vision Language Models in Medicine
        50734, -- Breaking Data Silos: Towards Open and Scalable Mobility Foundation Mod
        51923, -- Site-Level Fine-Tuning with Progressive Layer Freezing: Towards Robust
        52243, -- Position: The Current AI Conference Model is Unsustainable! Diagnosing
        52768, -- CognitiveSky: Scalable Sentiment and Narrative Analysis for Decentrali
        56081, -- Pretraining A Large Language Model using Distributed GPUs: A Memory-Ef
        57380, -- Backdoor Attacks on Decentralised Post-Training
        61879, -- AI-Assisted Engineering Should Track the Epistemic Status and Temporal
        62110, -- Towards a Declarative Agentic Layer for Intelligent Agents in MCP-Base
        62270, -- Interoperable Architecture for Digital Identity Delegation for AI Agen
        64465, -- EoS-FM: Can an Ensemble of Specialist Models act as a Generalist Featu
        67841, -- Adaptive Cybersecurity Architecture for Digital Product Ecosystems Usi
        69043, -- Bitcoin as an Interplanetary Monetary Standard with Proof-of-Transit T
        69882, -- Toward Goal-Oriented Communication in Multi-Agent Systems: An overview
        70247, -- PROV-AGENT: Unified Provenance for Tracking AI Agent Interactions in A
        71642, -- From Prompt Injections to Protocol Exploits: Threats in LLM-Powered AI
        72473, -- Differential privacy for medical deep learning: methods, tradeoffs, an
        72853, -- WikiDBGraph: Large-Scale Database Graph of Wikidata for Collaborative
        73253, -- Artificial Intelligence for Personalized Prediction of Alzheimer's Dis
        74448, -- Efficient Federated Search for Retrieval-Augmented Generation
        75832, -- TinyML NLP Scheme for Semantic Wireless Sentiment Classification with
        75889, -- Why do we regularise in every iteration for imaging inverse problems?
        76127, -- A large collection of bioinformatics question-query pairs over federat
        80343, -- Differential Privacy in Privacy-Preserving Big Data and Learning: Chal
        80884, -- A Metamodel and Framework for Artificial General Intelligence From The
        81683, -- SybilQuorum: Open Distributed Ledgers Through Trust Networks
        84368, -- Fully Decentralized Certified Unlearning
        86234, -- ACCO: Accumulate While You Communicate for Communication-Overlapped Sh
        87020, -- Robust Estimation Under Heterogeneous Corruption Rates
        88516, -- Secure On-Device Video OOD Detection Without Backpropagation
        88954, -- Decoupled SGDA for Games with Intermittent Strategy Communication
        89845, -- Distributed Event-Based Learning via ADMM
        91120, -- Towards Faster Decentralized Stochastic Optimization with Communicatio
        91207, -- Many-Objective Multi-Solution Transport
        92086, -- Group Distributionally Robust Dataset Distillation with Risk Minimizat
        94080, -- Personalized Collaborative Learning with Affinity-Based Variance Reduc
        95003, -- Ringleader ASGD: The First Asynchronous SGD with Optimal Time Complexi
        99126, -- Social Hippocampus Memory Learning
        100484, -- Compositional Generative Modeling from Decentralized Data
        101547, -- Complexity of Decentralized Optimization with Mixed Affine Constraints
        102131, -- Convergence Rate of the Last Iterate of Stochastic Proximal Algorithms
        106470, -- Anti-adversarial Learning: Desensitizing Prompts for Large Language Mo
        106783, -- Bayesian Network Structural Consensus via Greedy Min-Cut Analysis
        106807, -- S-D-RSM: Stochastic Distributed Regularized Splitting Method for Large
        107140, -- Group Fair Matchings Using Convex Cost Functions
        107478, -- Decentralized Online Convex Optimization with Unknown Feedback Delays
        110108, -- QualBench: Benchmarking Chinese LLMs with Localized Professional Quali
        115008, -- Image Distillation for Safe Data Sharing in Histopathology
        115663 -- MAPSeg: Unified Unsupervised Domain Adaptation for Heterogeneous Medic
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'Federated learning curation 2026-10-15: mentions federated learning without using it'
FROM federated_learning_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING federated_learning_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING federated_learning_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
