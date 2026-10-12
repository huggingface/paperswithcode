-- Add Neural Architecture Search (NAS) method.
-- NAS has no single introducing paper: neuroevolution of network topologies
-- predates Zoph & Le (arXiv 1611.01578), who popularized the term. The source
-- is therefore an explainer survey and source_paper_id stays NULL, which also
-- keeps the hourly reference backfill from linking every citer of 1611.01578.
--
-- Keywords deliberately omit the bare "NAS" token: case-sensitive substring
-- matching would hit NASA, NASNet-free text, SNAS and other unrelated uses.

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
    'neural-architecture-search',
    'Neural Architecture Search',
    'Neural Architecture Search (NAS)',
    'Neural Architecture Search (NAS) automates the design of neural network architectures by searching a predefined space of candidate operations and connections for the configuration that best trades off accuracy against cost. Early work evolved network topologies with genetic algorithms (neuroevolution); the term was popularized by [Zoph & Le](/paper/1611.01578), who trained an [RNN](/methods/rnn) controller with [REINFORCE](/methods/reinforce) to sample child networks rewarded by their validation accuracy. Later work used evolutionary search, Bayesian optimization, weight-sharing supernets, differentiable relaxations such as DARTS, and training-free zero-cost proxies, cutting search cost from thousands of GPU days to a few hours. NAS produced widely used architectures such as NASNet, MnasNet, EfficientNet and MobileNetV3, and is now applied to hardware-aware model design and to compressing large language models.',
    'neural architecture search, differentiable architecture search, NAS-Bench',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://jmlr.org/papers/v20/18-598.html',
    'Neural Architecture Search: A Survey',
    NULL,
    NULL,
    '[Neural Architecture Search with Reinforcement Learning](/paper/1611.01578)'
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

-- Drop provenance from the earlier sourced version of this method.
DELETE FROM paper_method_evidence
WHERE evidence_type = 'source'
  AND method_id = (SELECT id FROM methods WHERE slug = 'neural-architecture-search');

DELETE FROM method_reference_backfill_months
WHERE method_id = (SELECT id FROM methods WHERE slug = 'neural-architecture-search');

-- Curated 2026-10-12 from all 616 local candidates: the 448 catalog papers
-- citing 1611.01578 on Semantic Scholar plus every title/abstract mention of
-- "architecture search" or "NAS". Each paper below proposes, analyzes,
-- benchmarks or surveys a NAS method, or obtains its main model by
-- architecture search.
CREATE TEMP TABLE nas_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'neural-architecture-search'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1611.01578', -- Neural Architecture Search with Reinforcement Learning
          '1704.08792', -- DeepArchitect: Automatically Designing and Training Deep Architectures
          '1707.04873', -- Efficient Architecture Search by Network Transformation
          '1707.07012', -- Learning Transferable Architectures for Scalable Image Recognition
          '1708.05344', -- SMASH: One-Shot Model Architecture Search through HyperNetworks
          '1711.00436', -- Hierarchical Representations for Efficient Architecture Search
          '1712.00559', -- Progressive Neural Architecture Search
          '1802.01548', -- Regularized Evolution for Image Classifier Architecture Search
          '1806.02639', -- Path-Level Network Transformation for Efficient Architecture Search
          '1806.06927', -- Auto-Meta: Automated Gradient Based Meta Learner Search
          '1806.07912', -- Resource-Efficient Neural Architect
          '1806.09055', -- DARTS: Differentiable Architecture Search
          '1807.06906', -- Towards Automated Deep Learning: Efficient Joint Neural Architecture a
          '1807.11626', -- MnasNet: Platform-Aware Neural Architecture Search for Mobile
          '1808.00391', -- Efficient Progressive Neural Architecture Search
          '1810.05749', -- Graph HyperNetworks for Neural Architecture Search
          '1810.11875', -- Automatically Evolving CNN Architectures Based on Blocks
          '1812.00332', -- ProxylessNAS: Direct Neural Architecture Search on Target Task and Har
          '1812.03443', -- FBNet: Hardware-Aware Efficient ConvNet Design via Differentiable Neur
          '1902.08142', -- Evaluating the Search Phase of Neural Architecture Search
          '1903.03777', -- Partial Order Pruning: for Best Speed/Accuracy Trade-off in Neural Arc
          '1903.09900', -- sharpDARTS: Faster and More Accurate Differentiable Architecture Searc
          '1904.00420', -- Single Path One-Shot Neural Architecture Search with Uniform Sampling
          '1904.00438', -- Understanding Neural Architecture Search Techniques
          '1904.02877', -- Single-Path NAS: Designing Hardware-Efficient ConvNets in less than 4
          '1904.09981', -- GraphNAS: Graph Neural Architecture Search with Reinforcement Learning
          '1905.02244', -- Searching for MobileNetV3
          '1905.09717', -- Network Pruning via Transformable Architecture Search
          '1905.11946', -- EfficientNet: Rethinking Model Scaling for Convolutional Neural Networ
          '1906.06832', -- Sample-Efficient Neural Architecture Search by Learning Action Space
          '1907.05737', -- PC-DARTS: Partial Channel Connections for Memory-Efficient Architectur
          '1908.00709', -- AutoML: A Survey of the State-of-the-Art
          '1908.09791', -- Once-for-All: Train One Network and Specialize it for Efficient Deploy
          '1909.00311', -- Scalable Reinforcement-Learning-Based Neural Architecture Search for C
          '1909.01051', -- MANAS: Multi-Agent Neural Architecture Search
          '1909.03184', -- Auto-GNN: Neural Architecture Search of Graph Neural Networks
          '1909.06035', -- DARTS+: Improved Differentiable Architecture Search with Early Stoppin
          '1909.09656', -- Understanding and Robustifying Differentiable Architecture Search
          '1910.11831', -- Stabilizing DARTS with Amended Gradient Estimation on Architectural Pa
          '1911.10862', -- Binarized Neural Architecture Search
          '1912.00848', -- Neural Predictor for Neural Architecture Search
          '1912.05027', -- SpineNet: Learning Scale-Permuted Backbone for Recognition and Localiz
          '1912.06059', -- Grid Search, Random Search, Genetic Algorithm: A Big Comparison for NA
          '1912.07768', -- Generative Teaching Networks: Accelerating Neural Architecture Search
          '1912.12522', -- NAS evaluation is frustratingly hard
          '1912.12814', -- RC-DARTS: Resource Constrained Differentiable Architecture Search
          '2001.01431', -- Deeper Insights into Weight Sharing in Neural Architecture Search
          '2001.05887', -- MixPath: A Unified Approach for One-shot Neural Architecture Search
          '2001.06392', -- Latency-Aware Differentiable Neural Architecture Search
          '2002.04116', -- Co-Exploration of Neural Architectures and Heterogeneous ASIC Accelera
          '2003.02838', -- Accelerator-aware Neural Network Design using AutoML
          '2003.04276', -- How to Train Your Super-Net: An Analysis of Training Heuristics in Wei
          '2003.10865', -- Model-based Asynchronous Hyperparameter and Neural Architecture Search
          '2003.11142', -- BigNAS: Scaling Up Neural Architecture Search with Big Single-Stage Mo
          '2004.14525', -- MobileDets: Searching for Object Detection Architectures for Mobile Ac
          '2005.14187', -- HAT: Hardware-Aware Transformers for Efficient Natural Language Proces
          '2006.02049', -- FBNetV3: Joint Architecture-Recipe Search using Predictor Pretraining
          '2006.03656', -- AutoHAS: Efficient Hyperparameter and Architecture Search
          '2006.07556', -- Interpretable Neural Architecture Search via Bayesian Optimisation wit
          '2006.08509', -- APQ: Joint Search for Network Architecture, Pruning and Quantization P
          '2006.11321', -- AutoOD: Automated Outlier Detection via Curiosity-guided Search and Se
          '2007.03331', -- GOLD-NAS: Gradual, One-Level, Differentiable
          '2007.04785', -- Accuracy Prediction with Non-neural Model for Neural Architecture Sear
          '2008.03901', -- RARTS: An Efficient First-Order Relaxed Architecture Search Method
          '2008.10292', -- Automated Search for Resource-Efficient Branched Multi-Task Networks
          '2009.00165', -- Neural Architecture Search For Keyword Spotting
          '2009.01371', -- Real Image Super Resolution Via Heterogeneous Model Ensemble using GP-
          '2009.09232', -- Learned Low Precision Graph Neural Networks
          '2010.10499', -- Optimal Subarchitecture Extraction For BERT
          '2011.00073', -- Resource-Aware Pareto-Optimal Automated Machine Learning Platform
          '2011.09011', -- AttentiveNAS: Improving Neural Architecture Search via Attentive Sampl
          '2011.11233', -- ROME: Robustifying Memory-Efficient NAS via Topology Disentanglement a
          '2012.06400', -- Differential Evolution for Neural Architecture Search
          '2101.00336', -- Neural Architecture Search via Combinatorial Multi-Armed Bandit
          '2101.05442', -- Automated Model Design and Benchmarking of 3D Deep Learning Models for
          '2101.08809', -- PyGlove: Symbolic Programming for Automated Machine Learning
          '2101.09336', -- A Comprehensive Survey on Hardware-Aware Neural Architecture Search
          '2101.10667', -- Evolutionary Multi-objective Architecture Search Framework: Applicatio
          '2102.02340', -- MUFASA: Multimodal Fusion Architecture Search for Electronic Health Re
          '2102.04040', -- LightSpeech: Lightweight and Fast Text to Speech with Neural Architect
          '2102.04208', -- Contrastive Embeddings for Neural Architectures
          '2102.07954', -- AlphaNet: Improved Training of Supernets with Alpha-Divergence
          '2102.11646', -- HardCoRe-NAS: Hard Constrained diffeRentiable Neural Architecture Sear
          '2103.00742', -- Automated Machine Learning on Graphs: A Survey
          '2103.11511', -- MoViNets: Mobile Video Networks for Efficient Video Recognition
          '2103.12424', -- BossNAS: Exploring Hybrid CNN-transformers with Block-wisely Self-supe
          '2103.13581', -- EfficientTDNN: Efficient Architecture Search for Speaker Recognition
          '2103.14282', -- Rethinking Graph Neural Architecture Search from Message-passing
          '2104.00298', -- EfficientNetV2: Smaller Models and Faster Training
          '2104.00597', -- One-Shot Neural Ensemble Architecture Search by Diversity-Guided Searc
          '2104.12766', -- HAO: Hardware-aware neural Architecture Optimization for Efficient Inf
          '2104.14545', -- LightTrack: Finding Lightweight Neural Networks for Object Tracking vi
          '2105.14669', -- Memory-Efficient Differentiable Transformer Architecture Search
          '2106.14406', -- Poisoning the Search Space in Neural Architecture Search
          '2107.07343', -- Mutation is all you need
          '2107.12679', -- MFAGAN: A Compression Framework for Memory-Efficient On-Device Super-R
          '2108.04392', -- Rethinking Architecture Selection in Differentiable NAS
          '2108.06156', -- EEEA-Net: An Early Exit Evolutionary Neural Architecture Search
          '2108.09306', -- D-DARTS: Distributed Differentiable Architecture Search
          '2109.00642', -- Searching for Efficient Multi-Stage Vision Transformers
          '2109.01356', -- Edge-featured Graph Neural Architecture Search
          '2109.12425', -- L$^{2}$NAS: Learning to Optimize Neural Architectures via Continuous-A
          '2109.12426', -- Profiling Neural Blocks and Design Spaces for Mobile Neural Architectu
          '2110.08616', -- GradSign: Model Performance Inference with Theoretical Insights
          '2110.08710', -- NeuralArTS: Structuring Neural Architecture Search with Type Theory
          '2110.15352', -- MCUNetV2: Memory-Efficient Patch-based Inference for Tiny Deep Learnin
          '2111.07138', -- Towards One Shot Search Space Poisoning in Neural Architecture Search
          '2111.10007', -- FBNetV5: Neural Architecture Search for Multiple Tasks in One Run
          '2111.14725', -- Searching the Search Space of Vision Transformer
          '2111.15097', -- EAGAN: Efficient Two-stage Evolutionary Architecture Search for GANs
          '2201.11679', -- DropNAS: Grouped Operation Dropout for Differentiable Architecture Sea
          '2201.12507', -- AutoDistil: Few-shot Task-agnostic Neural Architecture Search for Dist
          '2202.11921', -- Auto-scaling Vision Transformers without Training
          '2202.12934', -- Accelerating Neural Architecture Exploration Across Modalities Using G
          '2202.12954', -- A Hardware-Aware System for Accelerating Deep Neural Network Optimizat
          '2203.14577', -- Demystifying the Neural Tangent Kernel from a Practical Perspective: C
          '2203.15207', -- Generalizing Few-Shot NAS with Gradient Matching
          '2204.07615', -- TabNAS: Rejection Sampling for Neural Architecture Search on Tabular D
          '2205.00841', -- GPUNet: Searching the Deployable Convolution Neural Networks for GPUs
          '2205.02162', -- UnrealNAS: Can We Search Neural Architectures with Unreal Data?
          '2205.10358', -- A Hardware-Aware Framework for Accelerating Neural Architecture Search
          '2205.11656', -- FlexiBERT: Are Current Transformer Architectures too Homogeneous and R
          '2205.15678', -- Automatic Relation-aware Graph Network Proliferation
          '2206.01520', -- A Survey on Computationally Efficient Neural Architecture Search
          '2206.04673', -- Neural Prompt Search
          '2207.03677', -- SuperTickets: Drawing Task-Agnostic Lottery Tickets from Supernets via
          '2207.06968', -- DASS: Differentiable Architecture Search for Sparse neural networks
          '2207.07187', -- NASRec: Weight Sharing Neural Architecture Search for Recommender Syst
          '2207.13955', -- Neural Architecture Search on Efficient Transformers and Beyond
          '2208.14839', -- QuantNAS for super resolution: searching for efficient quantization-fr
          '2210.07535', -- AutoMoE: Heterogeneous Mixture-of-Experts with Adaptive Computation fo
          '2210.09943', -- Rethinking Bias Mitigation: Fairer Architectures Make for Fairer Face
          '2210.14016', -- Shortest Edit Path Crossover: A Theory-driven Solution to the Permutat
          '2211.12759', -- NAS-LID: Efficient Neural Architecture Search with Local Intrinsic Dim
          '2211.13955', -- MPCViT: Searching for Accurate and Efficient MPC-Friendly Vision Trans
          '2211.15444', -- DAMO-YOLO : A Report on Real-Time Object Detection Design
          '2211.17226', -- GENNAPE: Towards Generalized Neural Architecture Performance Estimator
          '2211.17228', -- AIO-P: Expanding Neural Performance Predictors Beyond Image Classifica
          '2301.08727', -- Neural Architecture Search: Insights from 1000 Papers
          '2301.09231', -- GP-NAS-ensemble: a model for NAS Performance Prediction
          '2302.04406', -- Neural Architecture Search via Two Constant Shared Weights Initialisat
          '2302.05629', -- Improving Differentiable Architecture Search via Self-Distillation
          '2302.14772', -- PA&DA: Jointly Sampling PAth and DAta for Consistent NAS
          '2302.14838', -- EvoPrompting: Language Models for Code-Level Neural Architecture Searc
          '2303.06856', -- Dynamic Neural Network for Multi-Task Learning Searching across Divers
          '2303.07065', -- MSINet: Twins Contrastive Search of Multi-Scale Interaction for Object
          '2303.07669', -- AutoTransfer: AutoML with Knowledge Transfer -- An Application to Grap
          '2303.08308', -- SpaceEvo: Hardware-Friendly Search Space Design for Efficient INT8 Inf
          '2303.09730', -- ElasticViT: Conflict-aware Supernet Training for Deploying Fast Vision
          '2303.15678', -- DisWOT: Student Architecture Search for Distillation WithOut Training
          '2304.05405', -- Efficient Automation of Neural Network Design: A Survey on Differentia
          '2304.10970', -- Can GPT-4 Perform Neural Architecture Search?
          '2305.08611', -- GeNAS: Neural Architecture Search with Better Generalization
          '2305.14065', -- Do Not Train It: A Linear Neural Architecture Search of Graph Neural N
          '2305.16943', -- DiffusionNAG: Predictor-guided Neural Architecture Generation with Dif
          '2306.00288', -- Training-free Neural Architecture Search for RNNs and Transformers
          '2306.01102', -- LLMatic: Neural Architecture Search via Large Language Models and Qual
          '2306.04845', -- Mixture-of-Supernets: Improving Weight-Sharing Supernet Training with
          '2306.06852', -- Rethink DARTS Search Space and Renovate a New Benchmark
          '2306.06855', -- Small Temperature is All You Need for Differentiable Architecture Sear
          '2306.09295', -- Neural Fine-Tuning Search for Few-Shot Learning
          '2306.11982', -- Balanced Mixture of SuperNets for Learning the CNN Pooling Architectur
          '2307.08300', -- ShiftNAS: Improving One-shot NAS via Probability Shift
          '2308.11421', -- TurboViT: Generating Fast Vision Transformers via Generative Architect
          '2308.11838', -- A Benchmark Study on Calibration
          '2308.15609', -- InstaTune: Instantaneous Neural Architecture Search During Fine-Tuning
          '2309.12576', -- Understanding Patterns of Deep Learning ModelEvolution in Network Arch
          '2310.16898', -- MCUFormer: Deploying Vision Transformers on Microcontrollers with Limi
          '2310.18384', -- MicroNAS: Memory and Latency Constrained Hardware-Aware Neural Archite
          '2312.10440', -- Weight-Entanglement Meets Gradient-Based Neural Architecture Search
          '2312.13301', -- SimQ-NAS: Simultaneous Quantization Policy and Neural Architecture Sea
          '2402.02105', -- ParZC: Parametric Zero-Cost Proxies for Efficient NAS
          '2403.04161', -- SWAP-NAS: Sample-Wise Activation Patterns for Ultra-fast NAS
          '2403.07591', -- Robustifying and Boosting Training-Free Neural Architecture Search
          '2403.13134', -- Robust NAS under adversarial training: benchmark, theory, and beyond
          '2403.13293', -- Building Optimal Neural Architectures using Interpretable Knowledge
          '2404.10518', -- MobileNetV4 -- Universal Models for the Mobile Ecosystem
          '2404.10934', -- Shears: Unstructured Sparsity with Neural Low-rank Adapter Search
          '2405.02267', -- Structural Pruning of Pre-trained Language Models via Neural Architect
          '2405.18377', -- LLaMA-NAS: Efficient Neural Architecture Search for Large Language Mod
          '2405.20838', -- einspace: Searching for Neural Architectures from Fundamental Operatio
          '2407.16269', -- HyTAS: A Hyperspectral Image Transformer Architecture Search Benchmark
          '2409.17372', -- Search for Efficient Large Language Models
          '2410.04808', -- LPZero: Language Model Zero-cost Proxy Search from Zero
          '2410.06479', -- Large Language Model Compression with Neural Architecture Search
          '2410.08339', -- Simultaneous Weight and Architecture Optimization for Neural Networks
          '2411.05046', -- PhoneLM:an Efficient and Capable Small Language Model Family through P
          '2411.19146', -- Puzzle: Distillation-Based NAS for Inference-Optimized LLMs
          '2501.16372', -- Low-Rank Adapters Meet Neural Architecture Search for LLM Compression
          '2502.10459', -- LLM4GNAS: A Large Language Model Based Toolkit for Graph Neural Archit
          '2504.00885', -- Spectral Architecture Search for Neural Networks
          '2504.15983', -- W-PCA Based Gradient-Free Proxy for Efficient Search of Lightweight La
          '2505.00949', -- Llama-Nemotron: Efficient Reasoning Models
          '2506.08270', -- SWAT-NN: Simultaneous Weights and Architecture Training for Neural Net
          '2511.09554', -- RF-DETR: Neural Architecture Search for Real-Time Detection Transforme
          '2511.23404', -- LFM2 Technical Report
          '2512.11130', -- Fast-FoundationStereo: Real-Time Zero-Shot Stereo Matching
          '2604.16555', -- LLM as a Tool, Not an Agent: Code-Mined Tree Transformations for Neura
          '2603.19563', -- Dual-Domain Representation Alignment: Bridging 2D and 3D Vision via Ge
          '2602.11937', -- Extending Puzzle for Mixture-of-Experts Reasoning Models with Applicat
          '2602.08513', -- A Multi-objective Evolutionary Algorithm Based on Bi-population with U
          '2602.02891', -- TraceNAS: Zero-shot LLM Pruning via Gradient Trace Correlation
          '2512.24120', -- Enhancing LLM-Based Neural Network Generation: Few-Shot Prompting and
          '2510.14336', -- DARTS-GT: Differentiable Architecture Search for Graph Transformers wi
          '2510.04938', -- ONNX-Net: Towards Universal Representations and Instant Performance
          '2510.00379', -- Composer: A Search Framework for Hybrid Neural Architecture Design
          '2509.05656', -- OptiProxy-NAS: Optimization Proxy based End-to-End Neural Architecture
          '2508.15884', -- Jet-Nemotron: Efficient Language Model with Post Neural Architecture
          '2508.14946', -- HHNAS-AM: Hierarchical Hybrid Neural Architecture Search using Adaptiv
          '2508.12977', -- Dextr: Zero-Shot Neural Architecture Search with Singular Value Decomp
          '2507.18074', -- AlphaGo Moment for Model Architecture Discovery
          '2504.12971', -- Transferrable Surrogates in Expressive Neural Architecture Search Spac
          '2502.04975', -- Training-free Neural Architecture Search through Variance of Knowledge
          '2501.03782', -- Vision Transformer Neural Architecture Search for Out-of-Distribution
          '2404.15118', -- Identifying phase transitions in physical systems with neural networks
          '2403.06020', -- Multi-conditioned Graph Diffusion for Neural Architecture Search
          '2403.02484', -- Encodings for Prediction-based Neural Architecture Search
          '2309.07967', -- iHAS: Instance-wise Hierarchical Architecture Search for Deep Learning
          '2304.14636', -- PreNAS: Preferred One-Shot Learning Towards Efficient Neural   Archite
          '2304.06116', -- AutoShot: A Short Video Dataset and State-of-the-Art Shot Boundary Det
          '2303.08250', -- CHEEM: Continual Learning by Reuse, New, Adapt and Skip -- A Hierarchi
          '2106.07714', -- Learning Deep Morphological Networks with Neural Architecture Search
          '2201.10781', -- ASFD: Automatic and Scalable Face Detector
          '2106.08630', -- HELP: Hardware-Adaptive Efficient Latency Prediction for NAS via   Met
          '2007.10319', -- MCUNet: Tiny Deep Learning on IoT Devices
          '2003.04092', -- Searching Central Difference Convolutional Networks for Face Anti-Spoo
          '2001.00326', -- NAS-Bench-201: Extending the Scope of Reproducible Neural Architecture
          '1911.10695', -- When NAS Meets Robustness: In Search of Robust Architectures against A
          '1905.01924', -- Fast and Reliable Architecture Selection for Convolutional Neural Netw
          '1802.07191', -- Neural Architecture Search with Bayesian Optimisation and Optimal Tran
          '1801.07650', -- Dynamic Optimization of Neural Network Structures Using Probabilistic
          '1705.10823', -- Accelerating Neural Architecture Search using Performance Prediction
          '2605.15871', -- Agentic Discovery of Neural Architectures: AIRA-Compose and AIRA-Desig
          '2509.18151', -- HyperNAS: Enhancing Architecture Representation for NAS Predictor via
          '2605.05148', -- What Matters in Practical Learned Image Compression
          '2605.07256', -- TAS-LoRA: Transformer Architecture Search with Mixture-of-LoRA Experts
          '2506.04001', -- CARL: Causality-guided Architecture Representation Learning for an Int
          '2506.05869', -- Loss Functions for Predictor-based Neural Architecture Search
          '2506.06019', -- Runtime Analysis of Evolutionary NAS for Multiclass Classification
          '2503.10740', -- Subnet-Aware Dynamic Supernet Training for Neural Architecture Search
          '2412.19206', -- NADER: Neural Architecture Design via Multi-Agent Collaboration
          '2402.18213', -- Multi-objective Differentiable Neural Architecture Search
          '2408.08776', -- NEAR: A Training-Free Pre-Estimator of Machine Learning Model Performa
          '2505.22226', -- Expressive yet Efficient Feature Expansion with Adaptive Cross-Hadamar
          '1901.07261', -- Fast, Accurate and Lightweight Super-Resolution with Neural Architectu
          '2403.10318', -- pTNAS: Progressive Neural Architecture Search for Tabular Data
          '2605.04057', -- Structured Progressive Knowledge Activation for LLM-Driven Neural Arch
          '2512.00283', -- BIOARC: Discovering Optimal Neural Architectures for Biological Founda
          '2606.00535', -- DREAM-S: Speculative Decoding with Searchable Drafting and Target-Awar
          '2504.15865', -- MedNNS: Supernet-based Medical Task-Adaptive Neural Network Search
          '2407.04203', -- DeNAS-ViT: Data Efficient NAS-Optimized Vision Transformer for Ultraso
          '2005.03215', -- AutoSpeech: Neural Architecture Search for Speaker Recognition
          '2109.08839', -- SpeechNAS: Towards Better Trade-off between Latency and Accuracy for L
          '2509.05657', -- LM-Searcher: Cross-domain Neural Architecture Search with LLMs via Uni
          '2407.13122', -- MO-EMT-NAS: Multi-Objective Continuous Transfer of Architectural Knowl
          '2301.10879', -- SuperFedNAS: Cost-Efficient Federated Neural Architecture Search for O
          '2407.13896', -- Data-Algorithm-Architecture Co-Optimization for Fair Neural Networks o
          '2404.02189', -- Insights from the Use of Previously Unseen Neural Architecture Search
          '2403.19232', -- AZ-NAS: Assembling Zero-Cost Proxies for Network Architecture Search
          '2405.05502', -- Towards Accurate and Robust Architectures via Neural Architecture Sear
          '2406.00195', -- SNED: Superposition Network Architecture Search for Efficient Video Di
          '2403.11380', -- Boosting Order-Preserving and Transferability for Neural Architecture
          '2505.07300', -- L-SWAG: Layer-Sample Wise Activation with Gradients Information for Ze
          '2111.09957', -- Rethinking Dilated Convolution for Real-time Semantic Segmentation
          '2502.03553' -- Efficient Global Neural Architecture Search
      )
      OR (p.source = 'external' AND p.id IN (
          105034, -- Compact Training-free NAS with Alternating Evolution Game for Medical
          112409, -- Auto-GAS: Automated Proxy Discovery for Training-free Generative Archi
          112410, -- Auto-DAS: Automated Proxy Discovery for Training-free Distillation-awa
          113164, -- Dependency-aware Differentiable Neural Architecture Search
          113616, -- Depth-Aware Blind Image Decomposition for Real-World Adverse Weather R
          119154, -- Topology-Weighted Effective Rank: A Zero-Cost Proxy for Training Dynam
          120850, -- Vision-Oriented Lightweight Neural Architecture Search with Budget-Ada
          121029, -- Progressive Neural Architecture Generation
          121137 -- InTrain: Intrinsic Trainability for Zero-Cost Neural Architecture Sear
      ))
  );

DELETE FROM paper_method_exclusions x
USING nas_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM nas_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM nas_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: citation-only, passing mentions, or "architecture
-- search" over non-neural spaces (quantum circuits, agent pipelines). Durable
-- exclusions keep the keyword and reference backfills from re-linking them.
CREATE TEMP TABLE nas_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'neural-architecture-search'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1608.05859', -- Using the Output Embedding to Improve Language Models
          '1701.07274', -- Deep Reinforcement Learning: An Overview
          '1707.08819', -- A Downsampled Variant of ImageNet as an Alternative to the CIFAR datas
          '1708.02182', -- Regularizing and Optimizing LSTM Language Models
          '1709.01507', -- Squeeze-and-Excitation Networks
          '1709.06030', -- N2N Learning: Network to Network Compression via Policy Gradient Reinf
          '1709.07432', -- Dynamic Evaluation of Neural Sequence Models
          '1710.05941', -- Searching for Activation Functions
          '1711.02846', -- Intriguing Properties of Adversarial Examples
          '1711.03705', -- Online Deep Learning: Learning Deep Neural Networks on the Fly
          '1712.00409', -- Deep Learning Scaling is Predictable, Empirically
          '1801.04381', -- MobileNetV2: Inverted Residuals and Linear Bottlenecks
          '1801.05895', -- Sparsely Aggregated Convolutional Networks
          '1802.03494', -- AMC: AutoML for Model Compression and Acceleration on Mobile Devices
          '1802.04443', -- On Characterizing the Capacity of Neural Networks using Algebraic Topo
          '1804.00222', -- Meta-Learning Update Rules for Unsupervised Representation Learning
          '1805.09501', -- AutoAugment: Learning Augmentation Policies from Data
          '1807.06173', -- A Discriminative Approach to Bayesian Filtering with Applications to H
          '1807.11164', -- ShuffleNet V2: Practical Guidelines for Efficient CNN Architecture Des
          '1807.11293', -- Improving Spatiotemporal Self-Supervision by Deep Reinforcement Learni
          '1810.05270', -- Rethinking the Value of Network Pruning
          '1810.06682', -- Trellis Networks for Sequence Modeling
          '1810.12894', -- Exploration by Random Network Distillation
          '1810.13306', -- Automated Machine Learning: From Principles to Practices
          '1901.02860', -- Transformer-XL: Attentive Language Models Beyond a Fixed-Length Contex
          '1902.00751', -- Parameter-Efficient Transfer Learning for NLP
          '1903.03088', -- Self-Tuning Networks: Bilevel Optimization of Hyperparameters using St
          '1903.05285', -- All You Need is a Few Shifts: Designing Efficient Convolutional Neural
          '1903.10520', -- Micro-Batch Training with Batch-Channel Normalization and Weight Stand
          '1904.05046', -- Generalizing from a Few Examples: A Survey on Few-Shot Learning
          '1904.07633', -- HARK Side of Deep Learning -- From Grad Student Descent to Automated M
          '1904.10921', -- Plug-in, Trainable Gate for Streamlining Arbitrary Neural Networks
          '1904.11487', -- Blurring the Line Between Structure and Learning to Optimize and Adapt
          '1905.04970', -- Tabular Benchmarks for Joint Architecture and Hyperparameter Optimizat
          '1905.05055', -- Object Detection in 20 Years: A Survey
          '1905.07628', -- Evolving Rewards to Automate Reinforcement Learning
          '1905.11532', -- Structure Learning for Neural Module Networks
          '1906.02287', -- Automated Machine Learning: State-of-The-Art and Open Challenges
          '1906.06784', -- Interpolated Adversarial Training: Achieving Robust Neural Networks wi
          '1907.09595', -- MixConv: Mixed Depthwise Convolutional Kernels
          '1908.02404', -- Fast and Accurate Capitalization and Punctuation for Automatic Speech
          '1908.08926', -- Efficient Deep Neural Networks
          '1909.11622', -- Photorealistic Material Editing Through Direct Image Manipulation
          '1909.13719', -- RandAugment: Practical automated data augmentation with a reduced sear
          '1910.04376', -- RLCard: A Toolkit for Reinforcement Learning in Card Games
          '1910.04867', -- A Large-scale Study of Representation Learning with the Visual Task Ad
          '1910.06764', -- Stabilizing Transformers for Reinforcement Learning
          '1910.06827', -- Learning Generalisable Omni-Scale Representations for Person Re-Identi
          '1911.09723', -- Fast Sparse ConvNets
          '2001.11279', -- Goal-directed graph construction using reinforcement learning
          '2002.08258', -- Knapsack Pruning with Inner Distillation
          '2002.11102', -- On Feature Normalization and Data Augmentation
          '2002.11794', -- Train Large, Then Compress: Rethinking Model Size for Efficient Traini
          '2003.03384', -- AutoML-Zero: Evolving Machine Learning Algorithms From Scratch
          '2003.08271', -- Pre-trained Models for Natural Language Processing: A Survey
          '2003.13678', -- Designing Network Design Spaces
          '2004.02967', -- Evolving Normalization-Activation Layers
          '2006.01895', -- Learning to Branch for Multi-Task Learning
          '2006.02334', -- DetectoRS: Detecting Objects with Recursive Feature Pyramid and Switch
          '2006.04466', -- Differentiable Neural Input Search for Recommender Systems
          '2006.08218', -- Self-supervised Learning: Generative or Contrastive
          '2006.10598', -- Neural Parameter Allocation Search
          '2006.12703', -- Efficient Hyperparameter Optimization in Deep Learning Using a Variabl
          '2006.13799', -- Auto-PyTorch Tabular: Multi-Fidelity MetaLearning for Efficient and Ro
          '2006.14090', -- Neural Architecture Design for GPU-Efficient Networks
          '2007.15353', -- Growing Efficient Deep Networks by Structured Continuous Sparsificatio
          '2008.08516', -- Automated Machine Learning -- a brief review at the end of the early y
          '2009.00236', -- A Survey of Deep Active Learning
          '2009.01555', -- Sample-Efficient Automated Deep Reinforcement Learning
          '2009.04534', -- Pay Attention when Required
          '2009.08453', -- MEAL V2: Boosting Vanilla ResNet-50 to 80%+ Top-1 Accuracy on ImageNet
          '2010.05006', -- Automated Concatenation of Embeddings for Structured Prediction
          '2010.08168', -- A Generalizable and Accessible Approach to Machine Learning with Globa
          '2010.14819', -- Model Rubik's Cube: Twisting Resolution, Depth and Width for TinyNets
          '2011.00241', -- Methods for Pruning Deep Neural Networks
          '2011.04212', -- PAMS: Quantized Super-Resolution via Parameterized Max Scale
          '2011.09899', -- MixMix: All You Need for Data-Free Compression Are Feature and Data Mi
          '2012.13587', -- Inception Convolution with Efficient Dilation Search
          '2101.03697', -- RepVGG: Making VGG-style ConvNets Great Again
          '2101.03958', -- Evolving Reinforcement Learning Algorithms
          '2102.08602', -- LambdaNetworks: Modeling Long-Range Interactions Without Attention
          '2102.09407', -- Adaptive Rational Activations to Boost Deep Reinforcement Learning
          '2103.04505', -- Split Computing and Early Exiting for Deep Learning Applications: Surv
          '2103.04753', -- Applicability and Surrogacy of Uncorrelated Airspace Encounter Models
          '2103.06255', -- Involution: Inverting the Inherence of Convolution for Visual Recognit
          '2103.06877', -- Fast and Accurate Model Scaling
          '2103.13630', -- A Survey of Quantization Methods for Efficient Neural Network Inferenc
          '2103.14636', -- A Practical Survey on Faster and Lighter Transformers
          '2104.04692', -- Not All Attention Is All You Need
          '2104.05704', -- Escaping the Big Data Paradigm with Compact Transformers
          '2105.03536', -- Pareto-Optimal Quantized ResNet Is Mostly 4-bit
          '2105.09821', -- DEHB: Evolutionary Hyperband for Scalable, Robust and Efficient Hyperp
          '2106.03062', -- On Training Sample Memorization: Lessons from Benchmarking Generative
          '2106.03374', -- RegMix: Data Mixing Augmentation for Regression
          '2106.08962', -- Efficient Deep Learning: A Survey on Making Deep Learning Models Small
          '2107.12917', -- Experiments on Properties of Hidden Structures of Sparse Neural Networ
          '2108.01265', -- Memorize, Factorize, or be Naïve: Learning Optimal Feature Interaction
          '2108.08398', -- A good body is all you need: avoiding catastrophic interference via ag
          '2109.15099', -- PP-LCNet: A Lightweight CPU Convolutional Neural Network
          '2110.07985', -- On-Policy Model Errors in Reinforcement Learning
          '2110.08059', -- FlexConv: Continuous Kernel Convolutions with Differentiable Kernel Si
          '2110.09276', -- Natural Attribute-based Shift Detection
          '2110.13041', -- Applications and Techniques for Fast Machine Learning in Science
          '2110.13100', -- Parameter Prediction for Unseen Deep Architectures
          '2112.05779', -- Quantum Architecture Search via Continual Reinforcement Learning
          '2112.09245', -- Automated Deep Learning: Neural Architecture Search Is Not the End
          '2112.14570', -- Lyapunov Exponents for Diversity in Differentiable Games
          '2201.05000', -- Automated Reinforcement Learning: An Overview
          '2202.02777', -- Learning Features with Parameter-Free Layers
          '2202.06387', -- Scaling Laws Under the Microscope: Predicting Transformer Performance
          '2202.09318', -- DataMUX: Data Multiplexing for Neural Networks
          '2203.02549', -- Structured Pruning is All You Need for Pruning CNNs at Initialization
          '2203.03619', -- Adaptive Cross-Layer Attention for Image Restoration
          '2203.06717', -- Scaling Up Your Kernels to 31x31: Revisiting Large Kernel Design in CN
          '2203.10489', -- TVConv: Efficient Translation Variant Convolution for Layout-aware Vis
          '2203.13922', -- AutoML for Deep Recommender Systems: A Survey
          '2203.15643', -- Nix-TTS: Lightweight and End-to-End Text-to-Speech via Module-wise Dis
          '2204.12743', -- Self-Supervised Text Erasing with Controllable Image Synthesis
          '2205.00167', -- Self-Programming Artificial Intelligence Using Code-Generating Languag
          '2205.01271', -- Lite Pose: Efficient Architecture Design for 2D Human Pose Estimation
          '2205.11995', -- Deep Low-Density Separation for Semi-Supervised Classification
          '2205.14756', -- EfficientViT: Multi-Scale Linear Attention for High-Resolution Dense P
          '2205.14959', -- Dataset Condensation via Efficient Synthetic-Data Parameterization
          '2206.01191', -- EfficientFormer: Vision Transformers at MobileNet Speed
          '2206.06614', -- Transformers are Meta-Reinforcement Learners
          '2206.11922', -- Worldwide AI Ethics: a review of 200 guidelines and recommendations fo
          '2206.15472', -- On-Device Training Under 256KB Memory
          '2207.01848', -- TabPFN: A Transformer That Solves Small Tabular Classification Problem
          '2207.09639', -- DC-BENCH: Dataset Condensation Benchmark
          '2208.12754', -- Task Selection for AutoML System Evaluation
          '2211.02048', -- Efficient Spatially Sparse Inference for Conditional GANs and Diffusio
          '2211.09760', -- VeLO: Training Versatile Learned Optimizers by Scaling Up
          '2211.11004', -- Minimizing the Accumulated Trajectory Error to Improve Dataset Distill
          '2211.16385', -- Multi-Agent Reinforcement Learning for Microprocessor Design Space Exp
          '2212.07936', -- A Study on the Intersection of GPU Utilization and CNN Inference
          '2212.14032', -- On Implicit Bias in Overparameterized Bilevel Optimization
          '2301.04502', -- Pruning Compact ConvNets for Efficient Inference
          '2301.11063', -- Rewarded meta-pruning: Meta Learning with Rewards for Channel Pruning
          '2301.12132', -- AutoPEFT: Automatic Configuration Search for Parameter-Efficient Fine-
          '2302.04089', -- ZipLM: Inference-Aware Structured Pruning of Language Models
          '2302.05433', -- Unified Functional Hashing in Automatic Machine Learning
          '2302.06586', -- Stitchable Neural Networks
          '2302.06675', -- Symbolic Discovery of Optimization Algorithms
          '2302.08476', -- Counting Carbon: A Survey of Factors Influencing the Emissions of Mach
          '2302.14574', -- A Little Bit Attention Is All You Need for Person Re-Identification
          '2303.00566', -- Structured Pruning for Deep Convolutional Neural Networks: A survey
          '2303.03667', -- Run, Don't Walk: Chasing Higher FLOPS for Faster Neural Networks
          '2303.13635', -- Low Rank Optimization for Efficient Deep Learning: Making A Balance be
          '2303.17605', -- SparseViT: Revisiting Activation Sparsity for Efficient High-Resolutio
          '2304.04370', -- OpenAGI: When LLM Meets Domain Experts
          '2304.04959', -- AdaTT: Adaptive Task-to-Task Fusion Network for Multitask Learning in
          '2304.05288', -- Task Difficulty Aware Parameter Allocation & Regularization for Lifelo
          '2304.09145', -- Outlier Suppression+: Accurate quantization of large language models b
          '2304.09453', -- Network Pruning Spaces
          '2305.00097', -- NNSplitter: An Active Defense Solution for DNN Model via Automated Wei
          '2305.02665', -- Learning Language-Specific Layers for Multilingual Machine Translation
          '2305.04522', -- Event Knowledge Incorporation with Posterior Regularization for Event-
          '2305.08021', -- TIPS: Topologically Important Path Sampling for Anytime Neural Network
          '2305.10429', -- DoReMi: Optimizing Data Mixtures Speeds Up Language Model Pretraining
          '2305.11462', -- Extending Memory for Language Modelling
          '2305.13657', -- ChatGPT as your Personal Data Scientist
          '2306.00008', -- Brainformers: Trading Simplicity for Efficiency
          '2306.00477', -- Make Pre-trained Model Reversible: From Parameter to Memory Efficient
          '2306.00577', -- TorchRL: A data-driven decision-making library for PyTorch
          '2306.00980', -- SnapFusion: Text-to-Image Diffusion Model on Mobile Devices within Two
          '2306.05785', -- End-to-End Neural Network Compression via $\frac{\ell_1}{\ell_2}$ Regu
          '2306.13474', -- Efficient Online Processing with Deep Neural Networks
          '2307.07982', -- A Survey of Techniques for Optimizing Transformer Inference
          '2307.08579', -- Scale-Aware Modulation Meet Transformer
          '2307.13901', -- YOLOBench: Benchmarking Efficient Object Detectors on Embedded Systems
          '2308.02084', -- Efficient Model Adaptation for Continual Learning at the Edge
          '2308.03979', -- PAIF: Perception-Aware Infrared-Visible Image Fusion for Attack-Tolera
          '2308.06787', -- RMP-Loss: Regularizing Membrane Potential Distribution for Spiking Neu
          '2308.07633', -- A Survey on Model Compression for Large Language Models
          '2308.14256', -- FaceChain: A Playground for Human-centric Artificial Intelligence Gene
          '2308.14328', -- Reinforcement Learning for Generative AI: A Survey
          '2308.15003', -- Generative Model for Models: Rapid DNN Customization for Diverse Tasks
          '2309.08859', -- Rethinking Learning Rate Tuning in the Era of Large Language Models
          '2309.09310', -- UGC: Unified GAN Compression for Efficient Image-to-Image Translation
          '2309.13851', -- DISeR: Designing Imaging Systems with Reinforcement Learning
          '2309.16663', -- HyperPPO: A scalable method for finding small policies for robotic con
          '2310.00093', -- DataDAM: Efficient Dataset Distillation with Attention Matching
          '2310.00386', -- Order-Preserving GFlowNets
          '2310.07707', -- MatFormer: Nested Transformer for Elastic Inference
          '2310.07999', -- LEMON: Lossless model expansion
          '2310.15342', -- Towards Hybrid-grained Feature Interaction Selection for Deep Sparse N
          '2310.18882', -- Differentiable Learning of Generalized Structured Matrices for Efficie
          '2311.03216', -- Mini Minds: Exploring Bebeshka and Zlata Baby Models
          '2311.18246', -- Combined Scheduling, Memory Allocation and Tensor Replacement for Mini
          '2312.07243', -- A Unified Sampling Framework for Solver Searching of Diffusion Probabi
          '2312.07950', -- CBQ: Cross-Block Quantization for Large Language Models
          '2312.08614', -- Factorization Vision Transformer: Modeling Long Range Dependency with
          '2312.09411', -- OTOv3: Automatic Architecture-Agnostic Neural Network Training and Com
          '2312.12487', -- Adaptive Guidance: Training-free Acceleration of Conditional Diffusion
          '2312.12791', -- Model-Based Control with Sparse Neural Dynamics
          '2401.02122', -- PEFT for Speech: Unveiling Optimal Placement, Merging Strategies, and
          '2401.04666', -- Benchmark Analysis of Various Pre-trained Deep Learning Models on ASSI
          '2401.07159', -- Quantized Side Tuning: Fast and Memory-Efficient Tuning of Quantized L
          '2401.10166', -- VMamba: Visual State Space Model
          '2401.11576', -- Quantum Architecture Search with Unsupervised Representation Learning
          '2401.12819', -- Dynamic Layer Tying for Parameter-Efficient Transformers
          '2402.02855', -- Dynamic Sparse Learning: A Novel Paradigm for Efficient Recommendation
          '2402.03500', -- Curriculum reinforcement learning for quantum architecture search unde
          '2402.09748', -- Model Compression and Efficient Inference for Large Language Models: A
          '2402.14905', -- MobileLLM: Optimizing Sub-billion Parameter Language Models for On-Dev
          '2402.17440', -- Principled Architecture-aware Scaling of Hyperparameters
          '2402.18789', -- FlexLLM: A System for Co-Serving Large Language Model Inference and Pa
          '2403.03063', -- CrackNex: a Few-shot Low-light Crack Segmentation Model Based on Retin
          '2403.08265', -- Random Search as a Baseline for Sparse Neural Network Architecture Sea
          '2403.11446', -- LLM Guided Evolution - The Automation of Models Advancing Models
          '2403.13187', -- Evolutionary Optimization of Model Merging Recipes
          '2403.19163', -- D'OH: Decoder-Only Random Hypernetworks for Implicit Neural Representa
          '2404.14294', -- A Survey on Efficient Inference for Large Language Models
          '2404.14618', -- Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing
          '2404.17768', -- Changing the Training Data Distribution to Reduce Simplicity Bias Impr
          '2405.02128', -- Single and Multi-Hop Question-Answering Datasets for Reticular Chemist
          '2405.09927', -- Moreau Envelope for Nonconvex Bi-Level Optimization: A Single-loop and
          '2405.16807', -- Extreme Compression of Adaptive Neural Images
          '2406.12042', -- Not All Prompts Are Made Equal: Prompt-based Pruning of Text-to-Image
          '2406.17630', -- KANQAS: Kolmogorov-Arnold Network for Quantum Architecture Search
          '2406.18630', -- Improving Hyperparameter Optimization with Checkpointed Model Weights
          '2407.18202', -- Differentiable Quantum Architecture Search in Asynchronous Quantum Rei
          '2408.00137', -- Correcting Negative Bias in Large Language Models through Negative Att
          '2408.06793', -- Layerwise Recurrent Router for Mixture-of-Experts
          '2408.13010', -- A Web-Based Solution for Federated Learning with LLM-Based Automation
          '2409.15254', -- Archon: An Architecture Search Framework for Inference-Time Techniques
          '2409.18582', -- Optimistic Games for Combinatorial Bayesian Optimization with Applicat
          '2410.11772', -- Layer-wise Importance Matters: Less Memory for Better Performance in P
          '2410.20011', -- A Survey of Small Language Models
          '2412.13488', -- Refining Salience-Aware Sparse Fine-Tuning Strategies for Language Mod
          '2502.04180', -- Multi-agent Architecture Search via Agentic Supernet
          '2502.13138', -- AIDE: AI-Driven Exploration in the Space of Code
          '2502.13251', -- Neural Attention Search
          '2502.17941', -- Optimal Brain Apoptosis
          '2503.02393', -- Vision-Language Model IP Protection via Prompt-based Learning
          '2503.18339', -- GranQ: Granular Zero-Shot Quantization with Channel-Wise Activation Sc
          '2503.22764', -- Boosting Large Language Models with Mask Fine-Tuning
          '2504.03424', -- The AI Cosmologist I: An Agentic System for Automated Data Analysis
          '2505.06497', -- FedADP: Unified Model Aggregation for Federated Learning with Heteroge
          '2505.07782', -- MLE-Dojo: Interactive Environments for Empowering LLM Agents in Machin
          '2506.06017', -- AgentSwift: Efficient LLM Agent Design via Value-guided Hierarchical S
          '2509.26476', -- Regression Language Models for Code
          '2510.04399', -- Utility-Learning Tension in Self-Modifying Agents
          '2510.08525', -- Which Heads Matter for Reasoning? RL-Guided KV Cache Compression
          '2601.03509', -- Evolving Programmatic Skill Networks
          '2601.11516', -- Building Production-Ready Probes For Gemini
          '2602.12612', -- Self-EvolveRec: Self-Evolving Recommender Systems with LLM-based Direc
          '2602.10377', -- Hardware Co-Design Scaling Laws via Roofline Modelling for On-Device L
          '2603.07300', -- AutoResearch-RL: Perpetual Self-Evaluating Reinforcement Learning Agen
          '2603.17891', -- RAMP: Reinforcement Adaptive Mixed Precision Quantization for Efficien
          '2603.23994', -- Understanding the Challenges in Iterative Generative Optimization with
          '2604.01007', -- Omni-SimpleMem: Autoresearch-Guided Discovery of Lifelong Multimodal A
          '2604.06938', -- POS-ISP: Pipeline Optimization at the Sequence Level for Task-aware IS
          '2604.12152', -- Domain-Specific Latent Representations Improve the Fidelity of Diffusi
          '2604.11248', -- Evolving Many Worlds: Towards Open-Ended Discovery in Petri Dish NCA v
          '2604.05550', -- AutoSOTA: An End-to-End Automated Research System for State-of-the-Art
          '2603.15381', -- Why AI systems don't learn and what to do about it: Lessons on autonom
          '2602.02597', -- ContextEvolve: Multi-Agent Context Compression for Systems Code Optimi
          '2602.02543', -- Toward Ultra-Long-Horizon Sequential Model Editing
          '2601.14525', -- Towards Execution-Grounded Automated AI Research
          '2601.10560', -- Learning Latency-Aware Orchestration for Parallel Multi-Agent Systems
          '2512.15973', -- Dynamic Rank Reinforcement Learning for Adaptive Low-Rank Multi-Head S
          '2511.01386', -- RAGSmith: A Framework for Finding the Optimal Composition of Retrieval
          '2510.07227', -- Where to Begin: Efficient Pretraining via Subnetwork Selection and Dis
          '2509.25933', -- From MNIST to ImageNet: Understanding the Scalability Boundaries of
          '2509.17063', -- TSGym: Design Choices for Deep Multivariate Time-Series Forecasting
          '2509.12019', -- AMQ: Enabling AutoML for Mixed-precision Weight-Only Quantization of
          '2507.12189', -- BenchRL-QAS: Benchmarking reinforcement learning algorithms for quantu
          '2506.23136', -- LLM-Assisted Question-Answering on Technical Documents Using Structure
          '2506.22389', -- Towards Distributed Neural Architectures
          '2506.15051', -- Sequential Policy Gradient for Adaptive Hyperparameter Optimization
          '2506.07666', -- ProARD: progressive adversarial robustness distillation: provide wide
          '2506.15692', -- MLE-STAR: Machine Learning Engineering Agent via Search and Targeted
          '2505.01468', -- One Search Fits All: Pareto-Optimal Eco-Friendly Model Selection
          '2502.12751', -- Architect of the Bits World: Masked Autoregressive Modeling for Circui
          '2411.12626', -- Exploring the Manifold of Neural Networks Using Diffusion Geometry
          '2312.05770', -- FedASMU: Efficient Asynchronous Federated Learning with Dynamic   Stal
          '2310.20447', -- Efficient Bayesian Learning Curve Extrapolation using Prior-Data Fitte
          '2308.16406', -- CktGNN: Circuit Graph Neural Network for Electronic Design Automation
          '2306.06101', -- Prodigy: An Expeditiously Adaptive Parameter-Free Learner
          '2306.04990', -- Multi-Architecture Multi-Expert Diffusion Models
          '2305.17473', -- A Comprehensive Overview and Comparative Analysis on Deep Learning Mod
          '2209.08575', -- SegNeXt: Rethinking Convolutional Attention Design for Semantic Segmen
          '2205.15619', -- Meta-ticket: Finding optimal subnetworks for few-shot learning within
          '2201.04288', -- Multiview Transformers for Video Recognition
          '2110.12858', -- Benchmarking the Processing of Aircraft Tracks with Triples Mode and
          '2101.01332', -- Equality Saturation for Tensor Graph Superoptimization
          '2102.05426', -- BRECQ: Pushing the Limit of Post-Training Quantization by Block Recons
          '2102.01963', -- Local Critic Training for Model-Parallel Learning of Deep Neural Netwo
          '2008.00861', -- Processing of Crowdsourced Observations of Aircraft in a High   Perfor
          '2006.05057', -- Towards More Practical Adversarial Attacks on Graph Neural Networks
          '2005.02165', -- AutoTune: Automatically Tuning Convolutional Neural Networks for Impro
          '2003.05689', -- Hyper-Parameter Optimization: A Review of Algorithms and Applications
          '2001.09212', -- PCGRL: Procedural Content Generation via Reinforcement Learning
          '1912.05074', -- UNet++: Redesigning Skip Connections to Exploit Multiscale Features in
          '1912.02047', -- Neural Machine Translation: A Review and Survey
          '1911.09804', -- Measuring Uncertainty through Bayesian Learning of Deep Neural Network
          '1911.03787', -- Learning to Optimize in Swarms
          '1909.01377', -- Deep Equilibrium Models
          '1904.11132', -- TreeGrad: Transferring Tree Ensembles to Neural Networks
          '1904.01569', -- Exploring Randomly Wired Neural Networks for Image Recognition
          '1703.02702', -- Robust Adversarial Reinforcement Learning
          '2605.05724', -- Auto Research with Specialist Agents Develops Effective and Non-Trivia
          '2605.08083', -- LLMs Improving LLMs: Agentic Discovery for Test-Time Scaling
          '2507.02554', -- AI Research Agents for Machine Learning: Search, Exploration, and Gene
          '2505.18568', -- Learning without Isolation: Pathway Protection for Continual Learning
          '2411.13513', -- Procurement Auctions via Approximately Optimal Submodular Optimization
          '2406.18851', -- LICO: Large Language Models for In-Context Molecular Optimization
          '2406.04508', -- OCCAM: Towards Cost-Efficient and Accuracy-Aware Classification Infere
          '2402.04676', -- Group Distributionally Robust Dataset Distillation with Risk Minimizat
          '2404.02573', -- Knowledge Distillation with Multi-granularity Mixture of Priors for Im
          '2605.29259', -- KLAS: Using Similarity to Stitch Neural Networks for Improved Accuracy
          '2602.22552', -- Relatron: Automating Relational Machine Learning over Relational Datab
          '2501.15889', -- Adaptive Width Neural Networks
          '2507.13263', -- From Sorting Algorithms to Scalable Kernels: Bayesian Optimization in
          '2606.09659', -- End-to-End Context Compression at Scale
          '2601.20043', -- Regime-Adaptive Bayesian Optimization via Dirichlet Process Mixtures o
          '2507.15336', -- Beyond Model Base Retrieval: Weaving Knowledge to Master Fine-grained
          '2601.20231', -- Certificate-Guided Pruning for Stochastic Lipschitz Optimization
          '2510.22899', -- On the Anisotropy of Score-Based Generative Models
          '2602.22268', -- AutoQRA: Joint Optimization of Mixed-Precision Quantization and Low-ra
          '2604.26258', -- FlowBot: Inducing LLM Workflows with Bilevel Optimization and Textual
          '2606.30111', -- Automating the Design of Embodied Agent Architectures
          '2601.04327', -- ParaCodex: A Profiling-Guided Autonomous Coding Agent for Reliable Par
          '2111.14813', -- TransWeather: Transformer-based Restoration of Images Degraded by Adve
          '2103.15726', -- Slimmable Compressive Autoencoders for Practical Neural Image Compress
          '2205.12755', -- An Evolutionary Approach to Dynamic Introduction of Tasks in Large-sca
          '2410.16822', -- Can Large Language Models Act as Ensembler for Multi-GNNs?
          '2506.13180', -- Dynamic Acoustic Model Architecture Optimization in Training for ASR
          '2411.12841', -- Data-to-Model Distillation: Data-Efficient Learning Framework
          '2409.15557', -- Mixture of Efficient Diffusion Experts Through Automatic Interval and
          '2403.04149', -- MAP: MAsk-Pruning for Source-Free Model Intellectual Property Protecti
          '2403.07560', -- Unleashing Network Potentials for Semantic Scene Completion
          '2405.14136', -- Efficient Multitask Dense Predictor via Binarization
          '2403.19490', -- Jointly Training and Pruning CNNs via Learnable Agent Guidance and Ali
          '2403.15194', -- Your Image is My Video: Reshaping the Receptive Field via Image-To-Vid
          '2401.01543', -- Retraining-Free Model Quantization via One-Shot Weight-Coupling Learni
          '2603.20024', -- Layered Quantum Architecture Search for 3D Point Cloud Classification
          '2603.01759', -- Meta-Learning Hyperparameters for Parameter Efficient Fine-Tuning
          '2609.24657' -- Circuit Hypernetworks for Quantum-Augmented Diffusion Language Models
      )
      OR (p.source = 'external' AND p.id IN (
          115443, -- Efficient Hyperparameter Optimization with Adaptive Fidelity Identific
          120956 -- RAAS: LLM Agentic System Architecture Search with GRPO
      ))
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'NAS curation 2026-10-12: mentions or cites NAS without using it'
FROM nas_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING nas_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING nas_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
