-- Add AutoML (Automated Machine Learning) method.
-- AutoML has no single introducing paper: it grew out of hyperparameter
-- optimization and algorithm selection work and was shaped by systems such as
-- Auto-WEKA and auto-sklearn. The source is therefore an explainer (the open
-- access AutoML book) and source_paper_id stays NULL.

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
    'automl',
    'AutoML',
    'Automated Machine Learning (AutoML)',
    'AutoML (Automated Machine Learning) automates the choices that otherwise require an ML expert, such as data preprocessing, feature engineering, model and algorithm selection, hyperparameter optimization, and ensembling, so that a strong model can be obtained for a new dataset with little manual effort. Classic systems frame this as a combined algorithm selection and hyperparameter optimization (CASH) problem solved with [Bayesian Optimization](/methods/bayesian-optimization), meta-learning, and ensembling, as in Auto-WEKA and [auto-sklearn](/paper/2007.04074). Stacking-based systems such as [AutoGluon](/paper/2003.06505) and cost-aware ones such as [FLAML](/paper/1911.04706) followed. For deep learning, [Neural Architecture Search](/methods/neural-architecture-search) automates model design, and more recently LLM agents automate end-to-end ML engineering.',
    'AutoML, automated machine learning',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://www.automl.org/book/',
    'Automated Machine Learning: Methods, Systems, Challenges',
    NULL,
    NULL,
    '[AutoML: A Survey of the State-of-the-Art](/paper/1908.00709)'
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

-- Curated 2026-10-12 from all 129 local papers whose title or abstract
-- mentions AutoML, "automated machine learning", or a named AutoML system
-- (auto-sklearn, AutoGluon, TPOT, Auto-WEKA, Auto-PyTorch, AutoKeras, FLAML).
-- Each paper below proposes, analyzes, benchmarks or surveys AutoML, or frames
-- its main contribution as AutoML.
CREATE TEMP TABLE automl_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'automl'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1802.03494', -- AMC: AutoML for Model Compression and Acceleration on Mobile Devices
          '1810.13306', -- Automated Machine Learning: From Principles to Practices
          '1906.02287', -- Automated Machine Learning: State-of-The-Art and Open Challenges
          '1908.00709', -- AutoML: A Survey of the State-of-the-Art
          '1911.04706', -- FLAML: A Fast and Lightweight AutoML Library
          '2003.02838', -- Accelerator-aware Neural Network Design using AutoML
          '2003.03384', -- AutoML-Zero: Evolving Machine Learning Algorithms From Scratch
          '2003.06505', -- AutoGluon-Tabular: Robust and Accurate AutoML for Structured Data
          '2006.06480', -- Adaptation Strategies for Automated Machine Learning on Evolving Data
          '2006.13799', -- Auto-PyTorch Tabular: Multi-Fidelity MetaLearning for Efficient and Ro
          '2007.04074', -- Auto-Sklearn 2.0: Hands-free AutoML via Meta-Learning
          '2008.08516', -- Automated Machine Learning -- a brief review at the end of the early y
          '2011.00073', -- Resource-Aware Pareto-Optimal Automated Machine Learning Platform
          '2012.04371', -- Efficient Automatic CASH via Rising Bandits
          '2101.08809', -- PyGlove: Symbolic Programming for Automated Machine Learning
          '2103.00742', -- Automated Machine Learning on Graphs: A Survey
          '2111.00083', -- A Scalable AutoML Approach Based on Graph Neural Networks
          '2111.02705', -- Benchmarking Multimodal AutoML for Tabular Data with Text Fields
          '2111.06495', -- FairAutoML: Embracing Unfairness Mitigation in AutoML
          '2201.00207', -- AutoDES: AutoML Pipeline Generation of Classification with Dynamic Ens
          '2201.03916', -- Automated Reinforcement Learning (AutoRL): A Survey and Open Problems
          '2203.13922', -- AutoML for Deep Recommender Systems: A Survey
          '2204.08358', -- AutoMLBench: A Comprehensive Experimental Evaluation of Automated Mach
          '2208.12754', -- Task Selection for AutoML System Evaluation
          '2211.04148', -- The Technological Emergence of AutoML: A Survey of Performant Software
          '2302.03255', -- DivBO: Diversity-aware CASH for Ensemble Learning
          '2302.05433', -- Unified Functional Hashing in Automatic Machine Learning
          '2303.00501', -- OmniForce: On Human-Centered, Large Model Empowered and Cloud-Edge Col
          '2303.07669', -- AutoTransfer: AutoML with Knowledge Transfer -- An Application to Grap
          '2304.14979', -- MLCopilot: Unleashing the Power of Large Language Models in Solving Ma
          '2305.02499', -- AutoML-GPT: Automatic Machine Learning with GPT
          '2305.03403', -- Large Language Models for Automated Data Science: Introducing CAAFE fo
          '2305.13657', -- ChatGPT as your Personal Data Scientist
          '2306.08107', -- AutoML in the Age of Large Language Models: Current Challenges, Future
          '2306.16913', -- AutoML in Heavily Constrained Applications
          '2307.08364', -- Q(D)O-ES: Population-based Quality (Diversity) Optimisation for Post H
          '2307.10774', -- Assessing the Use of AutoML for Data-Driven Software Engineering
          '2308.05566', -- AutoGluon-TimeSeries: AutoML for Probabilistic Time Series Forecasting
          '2309.01125', -- AutoML-GPT: Large Language Model for AutoML
          '2309.01552', -- OutRank: Speeding up AutoML-based Model Search for Large Sparse Data s
          '2311.02971', -- TabRepo: A Large Scale Repository of Tabular Model Evaluations and its
          '2402.15351', -- AutoMMLab: Automatically Generating Deployable Models from Language In
          '2410.02958', -- AutoML-Agent: A Multi-Agent LLM Framework for Full-Pipeline AutoML
          '2410.17238', -- SELA: Tree-Search Enhanced LLM Agents for Automated Machine Learning
          '2502.12929', -- Flow-of-Options: Diversified and Improved LLM Reasoning by Thinking Th
          '2502.14693', -- I-MCTS: Enhancing Agentic AutoML via Introspective Monte Carlo Tree Se
          '2504.10552', -- LEMUR Neural Network Dataset: Towards Seamless AutoML
          '2509.21138', -- AutoIntent: AutoML for Text Classification
          '2603.01824', -- OpenAutoNLU: Open Source AutoML Library for NLU
          '2510.08511', -- AutoMLGen: Navigating Fine-Grained Optimization for Coding Agents
          '2509.22768', -- ML2B: Multi-Lingual ML Benchmark For AutoML
          '2509.12019', -- AMQ: Enabling AutoML for Mixed-precision Weight-Only Quantization of
          '2508.10177', -- KompeteAI: Accelerated Autonomous Multi-Agent System for End-to-End Pi
          '2508.00924', -- XAutoLM: Efficient Fine-Tuning of Language Models via Meta-Learning an
          '2308.14120', -- Large Language Models Streamline Automated Machine Learning for Clinic
          '2211.04661', -- Challenges and Barriers of Using Low Code Software for Machine Learnin
          '2507.02554', -- AI Research Agents for Machine Learning: Search, Exploration, and Gene
          '2505.13941', -- MLZero: A Multi-Agent System for End-to-end Machine Learning Automatio
          '2401.08513', -- X-Hacking: The Threat of Misguided AutoML
          '2606.06473', -- MLEvolve: A Self-Evolving Framework for Automated Machine Learning Alg
          '2508.05144' -- PSEO: Optimizing Post-hoc Stacking Ensemble Through Hyperparameter Tun
      )
  );

DELETE FROM paper_method_exclusions x
USING automl_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM automl_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM automl_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: AutoML used as a baseline, motivation or passing
-- mention (including pure NAS papers). Durable exclusions keep the daily
-- keyword backfill from re-linking them.
CREATE TEMP TABLE automl_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'automl'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1904.07633', -- HARK Side of Deep Learning -- From Grad Student Descent to Automated M
          '1907.09595', -- MixConv: Mixed Depthwise Convolutional Kernels
          '2102.10882', -- Conditional Positional Encodings for Vision Transformers
          '2104.13840', -- Twins: Revisiting the Design of Spatial Attention in Vision Transforme
          '2107.12917', -- Experiments on Properties of Hidden Structures of Sparse Neural Networ
          '2109.07865', -- OMPQ: Orthogonal Mixed Precision Quantization
          '2110.14795', -- MedMNIST v2 -- A large-scale lightweight benchmark for 2D and 3D biome
          '2204.01715', -- BigDL 2.0: Seamless Scaling of AI Pipelines from Laptops to Distribute
          '2207.01848', -- TabPFN: A Transformer That Solves Small Tabular Classification Problem
          '2211.01939', -- Empirical Analysis of Model Selection for Heterogeneous Causal Effect
          '2303.04673', -- Cost-Effective Hyperparameter Optimization for Large Language Model Ge
          '2305.06090', -- XTab: Cross-table Pretraining for Tabular Transformers
          '2306.01324', -- Hyperparameters in Reinforcement Learning and How To Tune Them
          '2307.00476', -- Pricing European Options with Google AutoML, TensorFlow, and XGBoost
          '2307.01026', -- Temporal Graph Benchmark for Machine Learning on Temporal Graphs
          '2307.16890', -- Discovering Adaptable Symbolic Algorithms from Scratch
          '2308.02084', -- Efficient Model Adaptation for Continual Learning at the Edge
          '2310.17737', -- ArchBERT: Bi-Modal Understanding of Neural Architectures and Natural L
          '2312.16886', -- MobileVLM : A Fast, Strong and Open Vision Language Assistant for Mobi
          '2401.00193', -- KAXAI: An Integrated Environment for Knowledge Analysis and Explainabl
          '2402.03766', -- MobileVLM V2: Faster and Stronger Baseline for Vision Language Model
          '2402.17440', -- Principled Architecture-aware Scaling of Hyperparameters
          '2403.00522', -- VisionLLaMA: A Unified LLaMA Backbone for Vision Tasks
          '2403.07591', -- Robustifying and Boosting Training-Free Neural Architecture Search
          '2403.11446', -- LLM Guided Evolution - The Automation of Models Advancing Models
          '2406.19251', -- AutoRAG-HP: Automatic Online Hyper-Parameter Tuning for Retrieval-Augm
          '2407.07000', -- Etalon: Holistic Performance Evaluation Framework for LLM Inference Sy
          '2411.10591', -- Creation and Evaluation of a Food Product Image Dataset for Product Pr
          '2501.05460', -- Efficiently Serving Large Multimodal Models Using EPD Disaggregation
          '2503.08689', -- QuoTA: Query-oriented Token Assignment via CoT Query Decouple for Long
          '2504.01990', -- Advances and Challenges in Foundation Agents: From Brain-Inspired Inte
          '2504.11301', -- Learning to Be A Doctor: Searching for Effective Medical Agent Archite
          '2504.16005', -- CAPO: Cost-Aware Prompt Optimization
          '2506.03887', -- Pre$^3$: Enabling Deterministic Pushdown Automata for Faster Structure
          '2506.12708', -- Serving Large Language Models on Huawei CloudMatrix384
          '2507.19427', -- Step-3 is Large yet Affordable: Model-system Co-design for  Cost-effec
          '2604.01007', -- Omni-SimpleMem: Autoresearch-Guided Discovery of Lifelong Multimodal A
          '2603.19172', -- DyMoE: Dynamic Expert Orchestration with Mixed-Precision Quantization
          '2511.08667', -- TabPFN-2.5: Advancing the State of the Art in Tabular Foundation Model
          '2510.14686', -- xLLM Technical Report
          '2402.03970', -- Tabular Data: Is Deep Learning all you need?
          '2509.17063', -- TSGym: Design Choices for Deep Multivariate Time-Series Forecasting
          '2508.16700', -- GPT-OSS-20B: A Comprehensive Deployment-Centric Analysis of OpenAI's O
          '2506.02084', -- Temporal Causal-based Simulation for Realistic Time-series Generation
          '2410.03736', -- CliMB: An AI-enabled Partner for Clinical Predictive Modeling
          '2401.09670', -- DistServe: Disaggregating Prefill and Decoding for Goodput-optimized
          '2401.06948', -- Fast and Accurate Zero-Training Classification for Tabular Engineering
          '2310.02095', -- A Survey on the Role of Crowds in Combating Online Misinformation:  An
          '2305.11108', -- MiraBest: A Dataset of Morphologically Classified Radio Galaxies for
          '2605.07075', -- ModelLens: Finding the Best for Your Task from Myriads of Models
          '2603.00512', -- Wavelet-based Frame Selection by Detecting Semantic Boundary for Long
          '2505.17866', -- DesignX: Human-Competitive Algorithm Designer for Black-Box Optimizati
          '2502.04677', -- LLM Query Scheduling with Prefix Reuse and Latency Constraints
          '2506.06895', -- Scalable Gaussian Processes with Latent Kronecker Structure
          '2606.27457', -- Cluster, Route, Escalate: Cascaded Framework for Cost-Aware LLM Servin
          '2607.00466', -- ELDR: Expert-Locality-Aware Decode Routing for PD-Disaggregated MoE Se
          '2507.12453', -- Cost-aware Stopping for Bayesian Optimization
          '2605.27081', -- ReMoE: Boosting Expert Reuse through Router Fine-Tuning in Memory-Cons
          '2510.07486', -- AsyncSpade: Efficient Test-Time Scaling with Asynchronous Sparse Decod
          '2310.17843', -- Optimal Pricing for Data-Augmented AutoML Marketplaces
          '2603.13358', -- Not All Prefills Are Equal: PPD Disaggregation for Multi-turn LLM Serv
          '2607.23193', -- OmniScope: Modality-Decoupled Token Compression for Omnimodal Large La
          '2605.06105', -- Shallow Prefill, Deep Decoding: Efficient Long-Context Inference via L
          '2605.13986', -- TabPFN-3: Technical Report
          '2410.07129', -- Exploring Large Language Models for Detecting Mental Disorders
          '2407.13896', -- Data-Algorithm-Architecture Co-Optimization for Fair Neural Networks o
          '2609.37959', -- TabFM: A Zero-Shot Foundation Model for Tabular Data
          '2610.07987' -- VisionWeave: Weaving Elastic Visual Representations as a Native Capabi
      )
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'AutoML curation 2026-10-12: mentions AutoML without using it'
FROM automl_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING automl_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING automl_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
