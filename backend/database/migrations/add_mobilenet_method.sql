-- Add MobileNet method, sourced from the MobileNetV1 paper (arXiv 1704.04861).
-- MobileNetV2/V3 are covered as keyword aliases and credited in the
-- description.

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
    'mobilenet',
    'MobileNet',
    'MobileNet',
    'MobileNets are efficient [convolutional neural networks](/methods/cnn) for mobile and embedded vision. MobileNetV1 factorizes each standard convolution into a [depthwise convolution](/methods/depthwise-convolution), which filters each input channel separately, followed by a 1x1 [pointwise convolution](/methods/pointwise-convolution) that combines channels; for 3x3 kernels this depthwise separable convolution uses 8 to 9 times less computation with only a small loss in accuracy. Two hyperparameters, a width multiplier and a resolution multiplier, trade accuracy for latency and size. [MobileNetV2](/paper/1801.04381) added inverted residual blocks with linear bottlenecks, and [MobileNetV3](/paper/1905.02244) was found with hardware-aware [neural architecture search](/methods/neural-architecture-search) and adds squeeze-and-excitation and h-swish. MobileNets are widely used as backbones for on-device classification, detection (e.g. SSD) and segmentation.',
    'MobileNet, MobileNets, MobileNetV1, MobileNetV2, MobileNetV3, MobileNet V2, MobileNet V3',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2017,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1704.04861'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications',
    'https://github.com/tensorflow/models/blob/master/research/slim/nets/mobilenet_v1.py',
    NULL,
    '[MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications](/paper/1704.04861)'
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
WHERE slug = 'mobilenet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'mobilenet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-15. The source paper is cited by tens of thousands
-- of papers, mostly in passing. Of the 410 local papers among the first
-- 9,999 Semantic Scholar citers, only the 25 whose title or abstract
-- mention MobileNet are linked; the rest are excluded so the hourly reference
-- backfill does not re-link them.
CREATE TEMP TABLE mobilenet_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mobilenet'
  AND p.id IN (
        17906, -- ReMaX: Relaxing for Better Training on Efficient Panoptic Segmentation
        18368, -- RepViT: Revisiting Mobile CNN From ViT Perspective
        21553, -- SWAP: Sparse Entropic Wasserstein Regression for Robust Network Prunin
        22752, -- SparseByteNN: A Novel Mobile Inference Acceleration Framework Based on
        25478, -- Lightweight Fish Classification Model for Sustainable Marine Managemen
        28294, -- ELA: Efficient Local Attention for Deep Convolutional Neural Networks
        30418, -- MobileNetV4 -- Universal Models for the Mobile Ecosystem
        30459, -- GhostNetV3: Exploring the Training Strategies for Compact Models
        35988, -- HaSPeR: An Image Repository for Hand Shadow Puppet Recognition
        39862, -- ScaleKD: Strong Vision Transformers Could Be Excellent Teachers
        41592, -- RapidNet: Multi-Level Dilated Convolution Based Mobile Backbone
        42570, -- AutoFish: Dataset and Benchmark for Fine-grained Analysis of Fish
        43251, -- iFormer: Integrating ConvNet and Transformer for Mobile Application
        47990, -- VeLU: Variance-enhanced Learning Unit for Deep Neural Networks
        56919, -- Automatic detection of Gen-AI texts: A comparative framework of neural
        62760, -- STResNet & STYOLO : A New Family of Compact Classification and Object
        65555, -- Beyond ImageNet: Understanding Cross-Dataset Robustness of Lightweight
        69278, -- SugarcaneShuffleNet: A Very Fast, Lightweight Convolutional Neural Net
        71826, -- AQUA20: A Benchmark Dataset for Underwater Species Classification unde
        85445, -- H-Sets: Hessian-Guided Discovery of Set-Level Feature Interactions in
        87632, -- Active Membership Inference Test (aMINT): Enhancing Model Auditability
        88463, -- VRM: Knowledge Distillation via Virtual Relation Matching
        94143, -- Dual-Solver: A Generalized ODE Solver for Diffusion Models with Dual P
        108084, -- BD-Net: Has Depth-Wise Convolution Ever Been Applied in Binary Neural
        116641 -- Jointly Training and Pruning CNNs via Learnable Agent Guidance and Ali
  );

DELETE FROM paper_method_exclusions x
USING mobilenet_cited_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mobilenet_cited_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM mobilenet_cited_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE mobilenet_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mobilenet'
  AND p.id IN (
        17279, -- Unlocking Feature Visualization for Deeper Networks with MAgnitude Con
        17283, -- AerialFormer: Multi-resolution Transformer for Aerial Image Segmentati
        17393, -- BPKD: Boundary Privileged Knowledge Distillation For Semantic Segmenta
        17509, -- AQuA: A Benchmarking Tool for Label Quality Assessment
        17578, -- Towards Stability of Autoregressive Neural Operators
        17607, -- Dynamic Perceiver for Efficient Visual Recognition
        17648, -- Balanced Mixture of SuperNets for Learning the CNN Pooling Architectur
        17714, -- Efficient Online Processing with Deep Neural Networks
        17726, -- Swin-Free: Achieving Better Cross-Window Attention and Efficiency with
        17754, -- Faster Segment Anything: Towards Lightweight SAM for Mobile Applicatio
        17756, -- Adaptive Sharpness-Aware Pruning for Robust Sparse Networks
        17763, -- ParameterNet: Parameters Are All You Need
        17997, -- EdgeFace: Efficient Face Recognition Model for Edge Devices
        18063, -- Distilling Large Vision-Language Model with Out-of-Distribution Genera
        18181, -- PIGEON: Predicting Image Geolocations
        18270, -- Neural Architecture Retrieval
        18280, -- A Survey of Techniques for Optimizing Transformer Inference
        18302, -- ShiftNAS: Improving One-shot NAS via Probability Shift
        18319, -- Cumulative Spatial Knowledge Distillation for Vision Transformers
        18323, -- Scale-Aware Modulation Meet Transformer
        18360, -- Towards Trustworthy Dataset Distillation
        18506, -- Strip-MLP: Efficient Token Interaction for Vision MLP
        18533, -- An Intelligent Remote Sensing Image Quality Inspection System
        18642, -- AIDE: A Vision-Driven Multi-View, Multi-Modal, Multi-Tasking Dataset f
        18646, -- Adaptive Frequency Filters As Efficient Global Token Mixers
        18781, -- DRAW: Defending Camera-shooted RAW against Image Manipulation
        18888, -- A Novel Convolutional Neural Network Architecture with a Continuous Sy
        18912, -- Accurate Neural Network Pruning Requires Rethinking Sparse Optimizatio
        19109, -- Product Review Image Ranking for Fashion E-commerce
        19149, -- Enhancing Generalization of Universal Adversarial Perturbation through
        19194, -- Estimator Meets Equilibrium Perspective: A Rectified Straight Through
        19233, -- Unified Data-Free Compression: Pruning and Quantization without Fine-T
        19338, -- Dynamic Neural Network is All You Need: Understanding the Robustness o
        19497, -- FashionNTM: Multi-turn Fashion Image Retrieval via Cascaded Memory
        19556, -- Foundation Model-oriented Robustness: Robust Image Model Evaluation wi
        19563, -- Patch Is Not All You Need
        19796, -- Eventful Transformers: Leveraging Temporal Redundancy in Vision Transf
        19798, -- A2Q: Accumulator-Aware Quantization with Guaranteed Overflow Avoidance
        19809, -- Residual Denoising Diffusion Models
        19885, -- Maestro: Uncovering Low-Rank Structures via Trainable Decomposition
        20061, -- UniSA: Unified Generative Framework for Sentiment Analysis
        20067, -- DAT++: Spatially Dynamic Vision Transformer with Deformable Attention
        20223, -- Mobile V-MoEs: Scaling Down Vision Transformers via Sparse Mixture-of-
        20345, -- Accelerating Deep Neural Networks via Semi-Structured Activation Spars
        20479, -- Scaling Laws for Sparsely-Connected Foundation Models
        20679, -- Gold-YOLO: Efficient Object Detector via Gather-and-Distribute Mechani
        20780, -- Background Activation Suppression for Weakly Supervised Object Localiz
        20885, -- LAPP: Layer Adaptive Progressive Pruning for Compressing CNNs from Scr
        21084, -- ResBit: Residual Bit Vector for Categorical Values
        21316, -- Decoding Human Activities: Analyzing Wearable Accelerometer and Gyrosc
        21539, -- A Holistic Evaluation of Piano Sound Quality
        21594, -- Accelerating Machine Learning Primitives on Commodity Hardware
        21717, -- Self-Supervised Dataset Distillation for Transfer Learning
        22096, -- TEQ: Trainable Equivalent Transformation for Quantization of LLMs
        22109, -- Zipformer: A faster and better encoder for automatic speech recognitio
        22138, -- In defense of parameter sharing for model-compression
        22779, -- NetDistiller: Empowering Tiny Deep Learning via In-Situ Distillation
        23020, -- SBCFormer: Lightweight Network Capable of Full-size ImageNet Classific
        23148, -- FMViT: A multiple-frequency mixing Vision Transformer
        23233, -- Boolean Variation and Boolean Logic BackPropagation
        23498, -- SENetV2: Aggregated dense layer for channelwise and global representat
        23512, -- Deep Tensor Network
        23625, -- Wafer Map Defect Patterns Semi-Supervised Classification Using Latent
        23789, -- UniRepLKNet: A Universal Perception Large-Kernel ConvNet for Audio, Vi
        23869, -- MobileDiffusion: Instant Text-to-Image Generation on Mobile Devices
        23908, -- MobileCLIP: Fast Image-Text Models through Multi-Modal Reinforced Trai
        24142, -- Talent-Interview: Web-Client Cheating Detection for Online Exams
        24556, -- Building Variable-sized Models via Learngene Pool
        24618, -- EdgeSAM: Prompt-In-the-Loop Distillation for On-Device Deployment of S
        24626, -- OpenSD: Unified Open-Vocabulary Segmentation and Detection
        24881, -- Conformer-Based Speech Recognition On Extreme Edge-Computing Devices
        25195, -- Towards Real-World Blind Face Restoration with Generative Diffusion Pr
        25426, -- Enhancing Generalization of Invisible Facial Privacy Cloak via Gradien
        25569, -- A multimodal gesture recognition dataset for desktop human-computer in
        25646, -- Derm-T2IM: Harnessing Synthetic Skin Lesion Data via Stable Diffusion
        25686, -- Self Expanding Convolutional Neural Networks
        25999, -- VMamba: Visual State Space Model
        26112, -- Unveiling the Human-like Similarities of Automatic Facial Expression R
        26192, -- Facing the Elephant in the Room: Visual Prompt Tuning or Full Finetuni
        26316, -- Unveiling the Unseen: Identifiable Clusters in Trained Depthwise Convo
        26361, -- Shortcuts Everywhere and Nowhere: Exploring Multi-Trigger Backdoor Att
        26365, -- A Comprehensive Survey of Compression Algorithms for Language Models
        26440, -- Do deep neural networks utilize the weight space efficiently?
        26446, -- SHViT: Single-Head Vision Transformer with Memory Efficient Macro Desi
        26966, -- Troublemaker Learning for Low-Light Image Enhancement
        27002, -- EfficientViT-SAM: Accelerated Segment Anything Model Without Accuracy
        27371, -- Tuning In: Analysis of Audio Classifier Performance in Clinical Settin
        27469, -- Knowledge Distillation Based on Transformed Teacher Matching
        27634, -- Object-level Geometric Structure Preserving for Natural Image Stitchin
        28319, -- Image2Sentence based Asymmetrical Zero-shot Composed Image Retrieval
        28660, -- Enhancing Image Caption Generation Using Reinforcement Learning with H
        28698, -- COMQ: A Backpropagation-Free Algorithm for Post-Training Quantization
        28725, -- Robustifying and Boosting Training-Free Neural Architecture Search
        28850, -- LocalMamba: Visual State Space Model with Windowed Selective Scan
        28899, -- EfficientVMamba: Atrous Selective Scan for Light Weight Visual Mamba
        28927, -- NeuFlow: Real-time, High-accuracy Optical Flow Estimation on Robots Us
        29107, -- SUN Team's Contribution to ABAW 2024 Competition: Audio-visual Valence
        29171, -- Building Optimal Neural Architectures using Interpretable Knowledge
        29172, -- Rotary Position Embedding for Vision Transformer
        29519, -- QuakeSet: A Dataset and Low-Resource Models to Monitor Earthquakes thr
        29576, -- Structurally Prune Anything: Any Architecture, Any Framework, Any Time
        29620, -- DenseNets Reloaded: Paradigm Shift Beyond ResNets and ViTs
        29652, -- Efficient Modulation for Vision Networks
        29653, -- Rewrite the Stars
        29658, -- Transformer-Lite: High-efficiency Deployment of Large Language Models
        29786, -- BiPer: Binary Neural Networks using a Periodic Function
        29809, -- Modality Translation for Object Detection Adaptation Without Forgettin
        29856, -- ViTamin: Designing Scalable Vision Models in the Vision-Language Era
        29878, -- Semi-Supervised Unconstrained Head Pose Estimation in the Wild
        30339, -- Characterizing Soft-Error Resiliency in Arm's Ethos-U55 Embedded Machi
        30563, -- QUTE: Quantifying Uncertainty in TinyML with Early-exit-assisted ensem
        30912, -- XFeat: Accelerated Features for Lightweight Image Matching
        31327, -- FunnelNet: An End-to-End Deep Learning Framework to Monitor Digital He
        31563, -- Multi-Scale VMamba: Hierarchy in Hierarchy Visual State Space Model
        31570, -- ZipCache: Accurate and Efficient KV Cache Quantization with Salient To
        31585, -- YOLOv10: Real-Time End-to-End Object Detection
        31729, -- LLS: Local Learning Rule for Deep Neural Networks Inspired by Neural A
        31756, -- BOLD: Boolean Logic Deep Learning
        31776, -- vHeat: Building Vision Models upon Heat Conduction
        31949, -- ViG: Linear-complexity Visual Sequence Learning with Gated Linear Atte
        32258, -- TinySV: Speaker Verification in TinyML with On-device Learning
        32299, -- GrootVL: Tree Topology is All You Need in State Space Model
        32412, -- ArMeme: Propagandistic Content in Arabic Memes
        32479, -- Classification of Non-native Handwritten Characters Using Convolutiona
        32500, -- Navigating Efficiency in MobileViT through Gaussian Process on Global
        32723, -- Comparing Deep Learning Models for Rice Mapping in Bhutan Using High R
        32831, -- mOSCAR: A Large-scale Multilingual and Multimodal Document-level Corpu
        32906, -- Alleviating Distortion in Image Generation via Multi-Resolution Diffus
        33037, -- Pick-or-Mix: Dynamic Channel Sampling for ConvNets
        33383, -- LeYOLO, New Scalable and Efficient CNN Architecture for Object Detecti
        33533, -- RepNeXt: A Fast Multi-Scale CNN using Structural Reparameterization
        33703, -- A Cross Spatio-Temporal Pathology-based Lung Nodule Dataset
        33711, -- A Lung Nodule Dataset with Histopathology-based Cancer Type Annotation
        33809, -- Mamba or RWKV: Exploring High-Quality and High-Efficiency Segment Anyt
        34183, -- AMD: Automatic Multi-step Distillation of Large-scale Vision Models
        34251, -- MMAD: Multi-label Micro-Action Detection in Videos
        34283, -- Learning to Adapt Category Consistent Meta-Feature of CLIP for Few-Sho
        34580, -- Integrating Deep Learning in Cardiology: A Comprehensive Review of Atr
        34604, -- NamedCurves: Learned Image Enhancement via Color Naming
        34935, -- GroupMamba: Efficient Group-Based Visual State Space Model
        35196, -- LKCell: Efficient Cell Nuclei Instance Segmentation with Large Convolu
        35204, -- XS-VID: An Extremely Small Video Object Detection Dataset
        35235, -- VSSD: Vision Mamba with Non-Causal State Space Duality
        35512, -- AVESFormer: Efficient Transformer Design for Real-Time Audio-Visual Se
        35792, -- Integrating Saliency Ranking and Reinforcement Learning for Enhanced O
        36496, -- MobileIQA: Exploiting Mobile-level Diverse Opinion Network For No-Refe
        36975, -- Down-Sampling Inter-Layer Adapter for Parameter and Computation Effici
        37022, -- SymFace: Additional Facial Symmetry Loss for Deep Face Recognition
        37274, -- Seeing Faces in Things: A Model and Dataset for Pareidolia
        37284, -- AIM 2024 Challenge on UHD Blind Photo Quality Assessment
        38248, -- Scaling Up Your Kernels: Large Kernel Design in ConvNets towards Unive
        38259, -- Q-VLM: Post-training Quantization for Large Vision-Language Models
        38715, -- All models are wrong, some are useful: Model Selection with Limited La
        38802, -- SNAC: Multi-Scale Neural Audio Codec
        39448, -- TrAct: Making First-layer Pre-Activations Trainable
        40161, -- Ultra-Sparse Memory Network
        40336, -- EfficientViM: Efficient Vision Mamba with Hidden State Mixer based Sta
        40389, -- SVTRv2: CTC Beats Encoder-Decoder Models in Scene Text Recognition
        40394, -- MobileMamba: Lightweight Multi-Receptive Visual Mamba Network
        40586, -- TSD-SR: One-Step Diffusion with Target Score Distillation for Real-Wor
        40773, -- Visual Modality Prompt for Adapting Vision-Language Object Detectors
        40977, -- PrefixKV: Adaptive Prefix KV Cache is What Vision Instruction-Followin
        41489, -- SnapGen: Taming High-Resolution Text-to-Image Models for Mobile Device
        41497, -- DQA: An Efficient Method for Deep Quantization of Deep Neural Network
        41640, -- Online Writer Retrieval with Chinese Handwritten Phrases: A Synergisti
        41792, -- CompactFlowNet: Efficient Real-time Optical Flow Estimation on Mobile
        42078, -- xPatch: Dual-Stream Time Series Forecasting with Exponential Seasonal-
        42164, -- Re-assessing ImageNet: How aligned is its single-label assumption with
        42191, -- Torque-Aware Momentum
        42237, -- RecConv: Efficient Recursive Convolutions for Multi-Frequency Represen
        43112, -- LiT: Delving into a Simplified Linear Diffusion Transformer for Image
        43136, -- Softplus Attention with Re-weighting Boosts Length Extrapolation in La
        43468, -- ContextFormer: Redefining Efficiency in Semantic Segmentation
        43888, -- Contrastive Representation Distillation via Multi-Scale Feature Decoup
        43900, -- Kolmogorov-Arnold Fourier Networks
        44061, -- Vision-Language Models for Edge Networks: A Comprehensive Survey
        44723, -- A Rapid Test for Accuracy and Bias of Face Recognition Technology
        45030, -- A Comprehensive Survey on Composed Image Retrieval
        45464, -- Partial Convolution Meets Visual Attention
        45592, -- EDM: Efficient Deep Feature Matching
        45932, -- RFUAV: A Benchmark Dataset for Unmanned Aerial Vehicle Detection and I
        46320, -- Make Your Training Flexible: Towards Deployment-Efficient Video Models
        46463, -- Think or Not Think: A Study of Explicit Thinking in Rule-Based Visual
        46592, -- Real-World Remote Sensing Image Dehazing: Benchmark and Baseline
        46985, -- LSNet: See Large, Focus Small
        47700, -- The Tenth NTIRE 2025 Efficient Super-Resolution Challenge Report
        48843, -- DiCo: Revitalizing ConvNets for Scalable and Efficient Diffusion Model
        49224, -- Beyond Modality Collapse: Representations Blending for Multimodal Data
        53096, -- Convolutional Set Transformer
        54493, -- DualCamCtrl: Dual-Branch Diffusion Model for Geometry-Aware Camera-Con
        55017, -- YOLO-Master: MOE-Accelerated with Specialized Transformers for Enhance
        58777, -- AffordMatcher: Affordance Learning in 3D Scenes from Visual Signifiers
        59178, -- CageDroneRF: A Large-Scale RF Benchmark and Toolkit for Drone Percepti
        59329, -- Thermal Image Refinement with Depth Estimation using Recurrent Network
        59839, -- Evolving Medical Imaging Agents via Experience-driven Self-skill Disco
        59886, -- FPGA-Enabled Machine Learning Applications in Earth Observation: A Sys
        59929, -- MoECLIP: Patch-Specialized Experts for Zero-shot Anomaly Detection
        60027, -- MobileMold: A Smartphone-Based Microscopy Dataset for Food Mold Detect
        60031, -- Diagnosing Generalization Failures from Representational Geometry Mark
        60273, -- SocialPulse: On-Device Detection of Social Interactions in Naturalisti
        60418, -- Flash-VAED: Plug-and-Play VAE Decoders for Efficient Video Generation
        60566, -- A Generative-First Neural Audio Autoencoder
        61363, -- Beyond Cropping and Rotation: Automated Evolution of Powerful Task-Spe
        61410, -- Energy-Efficient Neuromorphic Computing for Edge AI: A Framework with
        61492, -- TruKAN: Towards More Efficient Kolmogorov-Arnold Networks Using Trunca
        61719, -- LINA: Linear Autoregressive Image Generative Models with Continuous To
        62913, -- WeedRepFormer: Reparameterizable Vision Transformers for Real-Time Wat
        63409, -- Item Region-based Style Classification Network (IRSN): A Fashion Style
        63892, -- NeuroSketch: An Effective Framework for Neural Decoding via Systematic
        64042, -- Optimizing LLMs Using Quantization for Mobile Execution
        64063, -- LDLT L-Lipschitz Network: Generalized Deep End-To-End Lipschitz Networ
        64903, -- TZ-LLM: Protecting On-Device Large Language Models with Arm TrustZone
        65098, -- CompressNAS : A Fast and Efficient Technique for Model Compression usi
        65191, -- SynTTS-Commands: A Public Dataset for On-Device KWS via TTS-Synthesize
        65266, -- Physics-Informed Image Restoration via Progressive PDE Integration
        65274, -- One-Shot Knowledge Transfer for Scalable Person Re-Identification
        65428, -- Purrturbed but Stable: Human-Cat Invariant Representations Across CNNs
        65963, -- TernaryCLIP: Efficiently Compressing Vision-Language Models with Terna
        66000, -- Attentive Convolution: Unifying the Expressivity of Self-Attention wit
        66387, -- Removing Cost Volumes from Optical Flow Estimators
        66411, -- CSI-4CAST: A Hybrid Deep Learning Model for CSI Prediction with Compre
        67426, -- Social 3D Scene Graphs: Modeling Human Actions and Relations for Inter
        67682, -- HierLight-YOLO: A Hierarchical and Lightweight Object Detection Networ
        67974, -- MK-UNet: Multi-kernel Lightweight CNN for Medical Image Segmentation
        67978, -- LAWCAT: Efficient Distillation from Quadratic to Linear Attention with
        68311, -- ResidualViT for Efficient Temporally Dense Video Encoding
        68715, -- VCMamba: Bridging Convolutions with Multi-Directional Mamba for Effici
        68795, -- StableSleep: Source-Free Test-Time Adaptation for Sleep Staging with L
        69248, -- TinySR: Pruning Diffusion for Real-World Image Super-Resolution
        69290, -- NAT: Learning to Attack Neurons for Enhanced Adversarial Transferabili
        69555, -- SuryaBench: Benchmark Dataset for Advancing Machine Learning in Heliop
        69687, -- A dataset and model for recognition of audiologically relevant environ
        69783, -- Turbo-VAED: Fast and Stable Transfer of Video-VAEs to Mobile Devices
        70071, -- Learning from Oblivion: Predicting Knowledge Overflowed Weights via Re
        70107, -- TopKD: Top-scaled Knowledge Distillation
        70141, -- UniFGVC: Universal Training-Free Few-Shot Fine-Grained Vision Classifi
        71210, -- Butter: Frequency Consistency and Hierarchical Fusion for Autonomous D
        71583, -- ADAptation: Reconstruction-based Unsupervised Active Learning for Brea
        71714, -- FedDAA: Dynamic Client Clustering for Concept Drift Adaptation in Fede
        71779, -- Federated Loss Exploration for Improved Convergence on Non-IID Data
        72329, -- OpenFace 3.0: A Lightweight Multitask System for Comprehensive Facial
        72577, -- Progressive Data Dropout: An Embarrassingly Simple Approach to Faster
        72585, -- S2AFormer: Strip Self-Attention for Efficient Vision Transformer
        72603, -- Continual Learning Beyond Experience Rehearsal and Full Model Surrogat
        72874, -- 15,500 Seconds: Lean UAV Classification Using EfficientNet and Lightwe
        73881, -- ChA-MAEViT: Unifying Channel-Aware Masked Autoencoders and Multi-Chann
        74168, -- S2A: A Unified Framework for Parameter and Memory Efficient Transfer L
        74386, -- L-Lipschitz Gershgorin ResNet Network
        74526, -- ZIA: A Theoretical Framework for Zero-Input AI
        74552, -- Simpler Fast Vision Transformers with a Jumbo CLS Token
        74561, -- FetalCLIP: A Visual-Language Foundation Model for Fetal Ultrasound Ima
        74994, -- Emotion Recognition and Generation: A Comprehensive Review of Face, Sp
        75420, -- Color Enhancement for V-PCC Compressed Point Cloud via 2D Attribute Ma
        75885, -- Fish-Speech: Leveraging Large Language Models for Advanced Multilingua
        76187, -- MixLinear: Extreme Low Resource Multivariate Time Series Forecasting w
        76663, -- Vulnerabilities in AI-generated Image Detection: The Challenge of Adve
        76697, -- ESOD: Efficient Small Object Detection on High-Resolution Images
        76712, -- Efficient Visual Transformer by Learnable Token Merging
        76773, -- OPIMA: Optical Processing-In-Memory for Convolutional Neural Network A
        76870, -- SCOPE: Stochastic Cartographic Occupancy Prediction Engine for Uncerta
        77051, -- Scaling Graph Convolutions for Mobile Vision
        77288, -- EMCAD: Efficient Multi-scale Convolutional Attention Decoding for Medi
        77289, -- GreedyViG: Dynamic Axial Graph Construction for Efficient Vision GNNs
        77424, -- Rawformer: Unpaired Raw-to-Raw Translation for Learnable Camera ISPs
        77469, -- Monocular 3D lane detection for Autonomous Driving: Recent Achievement
        77683, -- A&B BNN: Add&Bit-Operation-Only Hardware-Friendly Binary Neural Networ
        77700, -- When do Convolutional Neural Networks Stop Learning?
        77715, -- Logit Standardization in Knowledge Distillation
        77930, -- RMP-SAM: Towards Real-Time Multi-Purpose Segment Anything
        78179, -- Ego-Exo4D: Understanding Skilled Human Activity from First- and Third-
        78335, -- Dynamic Convolutional Neural Networks as Efficient Pre-trained Audio M
        78609, -- ACC-UNet: A Completely Convolutional UNet model for the 2020s
        78640, -- Never-ending Learning of User Interfaces
        78872, -- Efficient ResNets: Residual Network Design
        84068, -- Protego: User-Centric Pose-Invariant Privacy Protection Against Face R
        84306, -- ViT$^3$: Unlocking Test-Time Training in Vision
        84367, -- Leveraging Multispectral Sensors for Color Correction in Mobile Camera
        84826, -- Reviving ConvNeXt for Efficient Convolutional Diffusion Models
        84837, -- Federated Active Learning Under Extreme Non-IID and Global Class Imbal
        85335, -- AsymLoc: Towards Asymmetric Feature Matching for Efficient Visual Loca
        85523, -- TAS-LoRA: Transformer Architecture Search with Mixture-of-LoRA Experts
        85628, -- CoAtNeXt:An Attention-Enhanced ConvNeXtV2-Transformer Hybrid Model for
        86386, -- Graph Your Own Prompt
        86412, -- The Fluorescent Veil: A Stealthy and Effective Physical Adversarial Pa
        86487, -- The Quest for Universal Master Key Filters in DS-CNNs
        86509, -- PocketSR: The Super-Resolution Expert in Your Pocket Mobiles
        86612, -- PLEIADES: Building Temporal Kernels with Orthogonal Polynomials
        86919, -- Asymmetric Duos: Sidekicks Improve Uncertainty
        87298, -- DAMamba: Vision State Space Model with Dynamic Adaptive Scan
        87622, -- UniConvNet: Expanding Effective Receptive Field while Maintaining Asym
        87642, -- TinyViM: Frequency Decoupling for Tiny Hybrid Vision Mamba
        87645, -- Competitive Distillation: A Simple Learning Strategy for Improving Vis
        87662, -- Local Dense Logit Relations for Enhanced Knowledge Distillation
        87744, -- Robust Machine Unlearning for Quantized Neural Networks via Adaptive G
        87836, -- Metric Convolutions: A Unifying Theory to Adaptive Image Convolutions
        87923, -- Scheduling Weight Transitions for Quantization-Aware Training
        88021, -- Knowledge Distillation with Refined Logits
        88025, -- EDFFDNet: Towards Accurate and Efficient Unsupervised Multi-Grid Image
        88087, -- CaO2: Rectifying Inconsistencies in Diffusion-Based Dataset Distillati
        88103, -- Emulating Self-attention with Convolution for Efficient Image Super-Re
        88292, -- Reverse Convolution and Its Applications to Image Restoration
        89231, -- Determinant Estimation under Memory Constraints and Neural Scaling Law
        89794, -- An Adaptive Orthogonal Convolution Scheme for Efficient and Flexible C
        89947, -- Asymmetric Decision-Making in Online Knowledge Distillation: Unifying
        90161, -- Ferret: An Efficient Online Continual Learning Framework under Varying
        90395, -- Improving Adversarial Transferability on Vision Transformers via Forwa
        90581, -- Where the Devil Hides: Deepfake Detectors Can No Longer Be Trusted
        90662, -- DVHGNN: Multi-Scale Dilated Vision HGNN for Efficient Vision Recogniti
        90699, -- Gaussian Eigen Models for Human Heads
        90737, -- Efficient Event-Based Object Detection: A Hybrid Neural Network with S
        90774, -- ReRAW: RGB-to-RAW Image Reconstruction via Stratified Sampling for Eff
        90836, -- From Alexnet to Transformers: Measuring the Non-linearity of Deep Neur
        91223, -- Preserving Deep Representations in One-Shot Pruning: A Hessian-Free Se
        91762, -- On the Performance Analysis of Momentum Method: A Frequency Domain Per
        91774, -- Designing Concise ConvNets with Columnar Stages
        91817, -- OCCAM: Towards Cost-Efficient and Accuracy-Aware Classification Infere
        92013, -- Two Sparse Matrices are Better than One: Sparsifying Neural Networks w
        92384, -- Let SSMs be ConvNets: State-space Modeling with Optimal Tensor Contrac
        92923, -- Densemarks: Learning Canonical Embeddings for Human Heads Images via P
        93258, -- SiNGER: A Clearer Voice Distills Vision Transformers Further
        93523, -- DISK: Differentiable Sparse Kernel Complex for Efficient Spatially-Var
        93975, -- Rectified Decoupled Dataset Distillation: A Closer Look for Fair and C
        94171, -- How NOT to benchmark your SITE metric: Beyond Static Leaderboards and
        94194, -- Pixel3DMM: Versatile Screen-Space Priors for Single-Image 3D Face Reco
        94488, -- Expressive yet Efficient Feature Expansion with Adaptive Cross-Hadamar
        94982, -- LipNeXt: Scaling up Lipschitz-based Certified Robustness to Billion-pa
        95031, -- SNAP-UQ: Self-supervised Next-Activation Prediction for Single-Pass Un
        95774, -- Keypoint-Based Dynamic Object 6-DoF Pose Tracking Via Event Camera
        96423, -- Establishing Reality-Virtuality Interconnections in Urban Digital Twin
        96583, -- StarIO: A Lightweight Inertial Odometry for Nonlinear Motion
        98335, -- TwinLiteNet+: An Enhanced Multi-Task Segmentation Model for Autonomous
        99392, -- S2M-Net: Spectral-Spatial Mixing with Morphology-Aware Adaptive Loss f
        99542, -- Forget by Uncertainty: Orthogonal Entropy Unlearning for Quantized Neu
        99795, -- Improving the Sensitivity of Backdoor Detectors via Class Subspace Ort
        101155, -- Towards Effective Waste Segmentation for Automated Waste Recycling in
        101522, -- Revisiting Neural Processes via Fourier Transform and Volterra Series
        101746, -- Path-conditioned training: a principled way to rescale ReLU neural net
        102381, -- Partial Ring Scan: Revisiting Scan Order in Vision State Space Models
        102483, -- How does Bayesian Sampling help Membership Inference Attacks?
        104614, -- On the power of data augmentation for head pose estimation
        106443, -- Enhancing All-to-X Backdoor Attacks with Optimized Target Class Mappin
        106480, -- Condensed Data Expansion Using Model Inversion for Knowledge Distillat
        106722, -- Heterogeneous Complementary Distillation
        106941, -- DeepRWCap: Neural-Guided Random-Walk Capacitance Solver for IC Design
        107249, -- WaveFormer: Frequency-Time Decoupled Vision Modeling with Wave Equatio
        107281, -- CompEvent: Complex-valued Event-RGB Fusion for Low-light Video Enhance
        107318, -- Data Heterogeneity and Forgotten Labels in Split Federated Learning
        109562, -- TinyCast: Probabilistic Zero-Shot Forecasting with Computed Periodicit
        112514, -- GenQ: Quantization in Low Data Regimes with Generative Synthetic Data
        112531, -- Generalizable Facial Expression Recognition
        112625, -- Deep Nets with Subsampling Layers Unwittingly Discard Useful Activatio
        112630, -- Resilience of Entropy Model in Distributed Neural Networks
        112650, -- PaPr: Training-Free One-Step Patch Pruning with Lightweight ConvNets f
        112822, -- "Refine, Discriminate and Align: Stealing Encoders via Sample-Wise Pro
        112833, -- LiteSAM is Actually what you Need for segment Everything
        112955, -- Fine-grained Dynamic Network for Generic Event Boundary Detection
        113149, -- Wavelet Convolutions for Large Receptive Fields
        113279, -- UNIT: Backdoor Mitigation via Automated Neural Distribution Tightening
        113348, -- Timestep-Aware Correction for Quantized Diffusion Models
        113354, -- From Pixels to Objects: A Hierarchical Approach for Part and Object Se
        113361, -- Rethinking Features-Fused-Pyramid-Neck for Object Detection
        113363, -- Sparse Refinement for Efficient High-Resolution Semantic Segmentation
        114487, -- Data-Algorithm-Architecture Co-Optimization for Fair Neural Networks o
        115671, -- LSK3DNet: Towards Effective and Efficient 3D Perception with Large Spa
        115733, -- MaxQ: Multi-Axis Query for N:M Sparsity Network
        115882, -- Learning Correlation Structures for Vision Transformers
        115929, -- AZ-NAS: Assembling Zero-Cost Proxies for Network Architecture Search
        115933, -- Beyond Image Super-Resolution for Image Recognition with Task-Driven P
        116250, -- PikeLPN: Mitigating Overlooked Inefficiencies of Low-Precision Neural
        116463, -- A Stealthy Wrongdoer: Feature-Oriented Reconstruction Attack against S
        116465, -- SlowFormer: Adversarial Attack on Compute and Energy Consumption of Ef
        116699, -- Your Image is My Video: Reshaping the Receptive Field via Image-To-Vid
        116978, -- Retraining-Free Model Quantization via One-Shot Weight-Coupling Learni
        117106, -- MADTP: Multimodal Alignment-Guided Dynamic Token Pruning for Accelerat
        117202, -- Neural Clustering based Visual Representation Learning
        118191, -- Distill on a Diet: Efficient Knowledge Distillation via Learnable Data
        118627, -- A First Exploration of Neuromorphic OT-CFM for Multi-Speaker VSR
        118795, -- Towards Sparsely Annotated Open-World Object Detection
        118853, -- SFKD: Spatial?Frequency Joint-Aware Heterogeneous Knowledge Distillati
        118948, -- Real-Time Source-Free Object Detection
        119099, -- REDistill: Robust Estimator Distillation for Balancing Robustness and
        119108, -- Scaling Laws for Black-box Adversarial Attacks
        119257, -- Fabric Image Demoir?ing Benchmark from Synthesis to Restoration
        119902, -- MMTL-UniAD: A Unified Framework for Multimodal and Multi-Task Learning
        122381 -- Not All Objectives Are Born Equal: Priority-Constrained Descent for Hi
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'MobileNet curation 2026-10-15: cites the source paper without using MobileNet'
FROM mobilenet_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING mobilenet_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING mobilenet_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id
  AND pm.paper_id <> (SELECT source_paper_id FROM methods WHERE slug = 'mobilenet');
