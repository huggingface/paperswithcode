-- Chat lookup-miss taxonomy gap fill (2026-11-11 audit): two methods that
-- production chat looked up with pwc_get_method on 2026-11-10/11 and missed.
--
-- TSM has an introducing paper (arXiv 1811.08383), so it gets source_paper_id
-- and an "Introduced" banner. Its display name is the exact lookup "TSM". The
-- keyword "TSM" is a case-sensitive substring in the keyword backfill, so it
-- also hits TSMixer, TSMC, Token Slimming Module and similar; every such local
-- paper was reviewed and is excluded below.
--
-- Fuzzy logic has no arXiv introducing paper (Zadeh, 1965), so it keeps
-- source_paper_id NULL with a canonical source_url, like
-- independent-component-analysis and self-organizing-map. Keywords are limited
-- to fuzzy-logic, fuzzy-set, fuzzy-inference and fuzzy-control phrasings; bare
-- "fuzzy" (fuzzy matching, fuzzy dark matter, fuzzing) is not a keyword.
--
-- Paper links were reviewed by hand; true positives get 'manual' evidence and
-- reviewed negatives that the keyword or reference backfills would link become
-- durable exclusions. Hero images were imported separately with
-- import_entity_image.py; this file records their credits.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES
(
    'temporal-shift-module',
    'TSM',
    'Temporal Shift Module (TSM)',
    'The Temporal Shift Module (TSM) adds temporal modeling to a 2D CNN at zero extra FLOPs and parameters. Inside each residual block it shifts a fraction of the feature channels (1/8 in each direction by default) one step forward and one step backward along the time axis, so that the following 2D convolution mixes information from neighbouring frames, approximating a [3D convolution](/methods/3d-convolution) at 2D cost. Placing the shift on the residual branch preserves the spatial features of the backbone, typically a [ResNet](/methods/resnet) or [MobileNet](/methods/mobilenet). A uni-directional variant that only shifts features from past frames supports low-latency online video recognition. TSM matched the accuracy of 3D CNNs such as I3D on Something-Something at a fraction of the computation and became a standard efficient backbone and baseline for action recognition, and temporal shifts are reused in video inpainting, video generation, remote photoplethysmography and video transformers.',
    'temporal shift module, temporal-shift module',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    2018,
    (SELECT id FROM papers WHERE arxiv_id = '1811.08383'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'TSM: Temporal Shift Module for Efficient Video Understanding',
    'https://github.com/mit-han-lab/temporal-shift-module/blob/master/ops/temporal_shift.py',
    NULL,
    'judge',
    ARRAY['Temporal Shift Module']
),
(
    'fuzzy-logic',
    'Fuzzy Logic',
    'Fuzzy Logic',
    'Fuzzy logic is a many-valued logic in which truth values are degrees in [0, 1] rather than just true or false. It builds on fuzzy set theory, introduced by Lotfi Zadeh (1965), where a membership function gives the degree to which each element belongs to a set, so that vague concepts such as "warm" or "tall" can be represented and combined. Conjunction, disjunction and negation are computed with t-norms, t-conorms and complements, for example min, max and 1 − x. A fuzzy inference system fuzzifies its inputs, applies a base of IF-THEN rules and defuzzifies the result; the Mamdani and Takagi–Sugeno–Kang (TSK) models are the two classic designs, and fuzzy controllers built on them are widely used in control engineering. Neuro-fuzzy systems such as ANFIS learn membership functions and rules with [gradient descent](/methods/gradient-descent), and fuzzy clustering generalizes [k-means clustering](/methods/k-means-clustering) to soft memberships. In machine learning, fuzzy logic supplies differentiable relaxations of logical formulas for neuro-symbolic models and complex knowledge-graph queries, interpretable rule-based classifiers, and ways to represent uncertainty.',
    'fuzzy logic, fuzzy-logic, fuzzy inference system, fuzzy inference, fuzzy set, fuzzy set theory, fuzzy controller, fuzzy control, fuzzy rule, fuzzy system, neuro-fuzzy, fuzzy membership function',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    1965,
    NULL,
    'https://doi.org/10.1016/S0019-9958(65)90241-X',
    'Fuzzy Sets (Zadeh, 1965)',
    NULL,
    NULL,
    'always',
    ARRAY['Fuzzy Set Theory']
)
ON CONFLICT (slug) DO UPDATE SET
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- Introduced banner for TSM.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'temporal-shift-module' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

-- temporal-shift-module: 131 links, 121 exclusions. Candidates: local Semantic Scholar citers of 1811.08383 and title/abstract matches for TSM / temporal shift.
CREATE TEMP TABLE tsm_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'temporal-shift-module'
  AND p.id IN (
        2309, -- 1907.01131 Learnable Gated Temporal Shift Module for Deep Video Inpainting
        2886, -- 1912.00998 A Multigrid Method for Efficiently Training Video Models
        3334, -- 2004.04730 X3D: Expanding Architectures for Efficient Video Recognition
        3962, -- 2007.15796 AR-Net: Adaptive Frame Resolution for Efficient Action Recognition
        4558, -- 2011.07949 RSPNet: Relative Speed Perception for Unsupervised Video Representation Lea
        5015, -- 2102.05095 Is Space-Time Attention All You Need for Video Understanding?
        5018, -- 2102.05775 AdaFuse: Adaptive Temporal Fusion Network for Efficient Action Recognition
        5169, -- 2103.05630 ForgeryNet: A Versatile Benchmark for Comprehensive Forgery Analysis
        5242, -- 2103.11511 MoViNets: Mobile Video Networks for Efficient Video Recognition
        5306, -- 2103.15691 ViViT: A Video Vision Transformer
        5393, -- 2104.03507 Progressive Temporal Feature Alignment Network for Video Inpainting
        5562, -- 2104.11178 VATT: Transformers for Multimodal Self-Supervised Learning from Raw Video,
        5563, -- 2104.11227 Multiscale Vision Transformers
        6114, -- 2106.13230 Video Swin Transformer
        6287, -- 2107.10161 Evidential Deep Learning for Open Set Action Recognition
        7449, -- 2112.04478 Prompting Visual-Language Models for Efficient Video Understanding
        7612, -- 2112.14238 AdaFocus V2: End-to-End Training of Spatial Dynamic Networks for Video Reco
        7682, -- 2201.04388 OCSampler: Compressing Videos to One Clip with Single-step Sampling
        7686, -- 2201.04676 UniFormer: Unified Transformer for Efficient Spatiotemporal Representation
        7752, -- 2201.09450 UniFormer: Unifying Convolution and Self-attention for Visual Recognition
        8246, -- 2203.07303 All in One: Exploring Unified Video-Language Pre-training
        8401, -- 2203.12602 VideoMAE: Masked Autoencoders are Data-Efficient Learners for Self-Supervis
        8593, -- 2204.02932 An Empirical Study of End-to-End Temporal Action Detection
        9824, -- 2207.09067 Time Is MattEr: Temporal Self-supervision for Video Transformers
        9964, -- 2208.01753 Two-Stream Transformer Architecture for Long Video Understanding
        9980, -- 2208.02816 Expanding Language-Image Pretrained Models for General Video Recognition
        10478, -- 2209.15280 Learning Transferable Spatiotemporal Representations from Natural Script Kn
        11394, -- 2211.09120 AdaMAE: Adaptive Masking for Efficient Spatiotemporal Learning with Masked
        11404, -- 2211.09552 UniFormerV2: Spatiotemporal Learning by Arming Image ViTs with Video UniFor
        11406, -- 2211.09648 HARDVS: Revisiting Human Activity Recognition with Dynamic Vision Sensors
        11561, -- 2211.12883 Mitigating and Evaluating Static Bias of Action Representations in the Back
        11658, -- 2211.15393 Video Test-Time Adaptation for Action Recognition
        11832, -- 2212.03229 Rethinking Video ViTs: Sparse Video Tubes for Joint Image and Video Learnin
        11923, -- 2212.05922 Audiovisual Masked Autoencoders
        12332, -- 2301.02642 Triple-stream Deep Metric Learning of Great Ape Behavioural Actions
        13459, -- 2303.01589 AZTR: Aerial Video Action Recognition with Auto Zoom and Temporal Reasoning
        13516, -- 2303.03202 Continuous Sign Language Recognition with Correlation Network
        13852, -- 2303.09756 Video Action Recognition with Attentive Semantic Units
        13910, -- 2303.11003 Tubelet-Contrastive Self-Supervision for Video-Efficient Generalization
        14070, -- 2303.13505 A Large-scale Study of Spatiotemporal Representation Learning with a New Be
        14154, -- 2303.14817 Frame Flexible Network
        14262, -- 2303.16727 VideoMAE V2: Scaling Video Masked Autoencoders with Dual Masking
        14745, -- 2304.08451 Efficient Video Action Detection with Token Dropout and Context Refinement
        14749, -- 2304.08477 Latent-Shift: Latent Diffusion with Temporal Shift for Efficient Text-to-Vi
        17130, -- 2306.04822 Optimizing ViViT Training: Time and Memory Reduction for Action Recognition
        17493, -- 2306.09331 Seeing the Pose in the Pixels: Learning Pose-Aware Representations in Visio
        18344, -- 2307.08908 What Can Simple Arithmetic Operations Do for Temporal Modeling?
        19057, -- 2308.04549 Prune Spatio-temporal Tokens by Semantic-aware Temporal Accumulation
        19393, -- 2308.09322 Audio-Visual Glance Network for Efficient Video Recognition
        19434, -- 2308.09710 SimDA: Simple Diffusion Adapter for Efficient Video Generation
        19632, -- 2308.11489 Learning from Semantic Alignment between Unpaired Multiviews for Egocentric
        19808, -- 2308.13711 EventTransAct: A video transformer-based framework for Event-camera based a
        20056, -- 2309.01265 SOAR: Scene-debiasing Open-set Action Recognition
        20129, -- 2309.02423 EgoPCA: A New Framework for Egocentric Hand-Object Interaction Understandin
        20432, -- 2309.07911 Disentangling Spatial and Temporal Learning for Efficient Image-to-Video Tr
        24066, -- 2311.18840 Just Add $π$! Pose Induced Video Transformers for Understanding Activities
        24078, -- 2312.00096 OST: Refining Text Knowledge with Optimal Spatio-Temporal Descriptor for Ge
        26103, -- 2401.11649 M2-CLIP: A Multimodal, Multi-task Adapting Framework for Video Action Recog
        26104, -- 2401.11654 ActionHub: A Large-scale Action Video Description Dataset for Zero-shot Act
        26833, -- 2402.03241 FROSTER: Frozen CLIP Is A Strong Teacher for Open-Vocabulary Action Recogni
        27294, -- 2402.08875 Advancing Human Action Recognition with Foundation Models trained on Unlabe
        28874, -- 2403.09626 Video Mamba Suite: State Space Model as a Versatile Alternative for Video U
        31278, -- 2405.08344 No Time to Waste: Squeeze Time into Channel for Mobile Video Understanding
        34240, -- 2407.05106 DailyDVS-200: A Comprehensive Benchmark Dataset for Event-Based Action Reco
        34251, -- 2407.05311 MMAD: Multi-label Micro-Action Detection in Videos
        34318, -- 2407.06113 C2C: Component-to-Composition Learning for Zero-Shot Compositional Action R
        34490, -- 2407.08476 VideoMamba: Spatio-Temporal Selective State Space Model
        35714, -- 2408.05421 EPAM-Net: An Efficient Pose-driven Attention-guided Multimodal Network for
        39779, -- 2411.05222 Don't Look Twice: Faster Video Transformers with Run-Length Tokenization
        40838, -- 2412.01508 HaGRIDv2: 1M Images for Static and Dynamic Hand Gesture Recognition
        41864, -- 2412.14294 TRecViT: A Recurrent Video Transformer
        41892, -- 2412.14719 Prototypical Calibrating Ambiguous Samples for Micro-Action Recognition
        45179, -- 2502.20361 OpenTAD: A Unified Framework and Comprehensive Study of Temporal Action Det
        45543, -- 2503.04470 Gate-Shift-Pose: Enhancing Action Recognition in Sports with Skeleton Infor
        45888, -- 2503.08529 SignRep: Enhancing Self-Supervised Sign Representations
        46320, -- 2503.14237 Make Your Training Flexible: Towards Deployment-Efficient Video Models
        47540, -- 2504.08222 F$^3$Set: Towards Analyzing Fast, Frequent, and Fine-grained Events from Vi
        51695, -- 2507.04306 Exploring Remote Physiological Signal Measurement under Dynamic Lighting Co
        64504, -- 2511.20928 Smooth regularization for efficient video recognition
        65283, -- 2511.05833 TYrPPG: Uncomplicated and Enhanced Learning Capability rPPG for Remote Hear
        66087, -- 2510.18705 A Renaissance of Explicit Motion Information Mining from Transformers for A
        67823, -- 2509.20899 Concepts in Motion: Temporal Bottlenecks for Interpretable Video Classifica
        68311, -- 2509.13255 ResidualViT for Efficient Temporally Dense Video Encoding
        71270, -- 2507.07795 Robust and Generalizable Heart Rate Estimation via Deep Learning for Remote
        73736, -- 2504.01774 Memory-efficient Low-latency Remote Photoplethysmography through Temporal-S
        73814, -- 2503.23447 CA^2ST: Cross-Attention in Audio, Space, and Time for Holistic Video Recogn
        74189, -- 2503.07821 Elderly Activity Recognition in the Wild: Results from the EAR Challenge
        75142, -- 2501.11340 GenVidBench: A 6-Million Benchmark for AI-Generated Video Detection
        76438, -- 2409.05260 Scalable Frame Sampling for Video Classification: A Semi-Optimal Policy App
        79220, -- 2303.11573 BigSmall: Efficient Multi-Task Learning for Disparate Spatial and Temporal
        79979, -- 2205.07134 ETAD: Training Action Detection End to End on a Laptop
        80103, -- 2203.14712 Assembly101: A Large-Scale Multi-View Video Dataset for Understanding Proce
        80262, -- 2201.04288 Multiview Transformers for Video Recognition
        80367, -- 2111.12993 PolyViT: Co-training Vision Transformers on Images, Videos and Audio
        80799, -- 2103.16559 Broaden Your Views for Self-Supervised Video Learning
        80860, -- 2006.03790 Multi-Task Temporal Shift Attention Networks for On-Device Contactless Vita
        81245, -- 2006.13256 Rescaling Egocentric Vision
        81545, -- 1911.00232 Multi-Moments in Time: Learning and Interpreting Models for Multi-Action Vi
        84478, -- 2601.11035 Your One-Stop Solution for AI-Generated Video Detection
        85250, -- 2604.02829 STRNet: Visual Navigation with Spatio-Temporal Representation through Dynam
        87536, -- 2605.28229 VidPrism: Heterogeneous Mixture of Experts for Image-to-Video Transfer
        88453, -- 2508.10896 ESSENTIAL: Episodic and Semantic Memory Integration for Video Class-Increme
        90142, -- 2503.15973 STOP: Integrated Spatial-Temporal Dynamic Prompting for Video Understanding
        90679, -- 2407.21616 EZSR: Event-based Zero-Shot Recognition
        93234, -- 2604.18367 EAST: Early Action Prediction Sampling Strategy with Token Masking
        94868, -- 2505.13997 StPR: Spatiotemporal Preservation and Routing for Exemplar-Free Video Class
        104296, -- 2004.06704 FineGym: A Hierarchical Video Dataset for Fine-grained Action Understanding
        106772, -- 2511.14186 Few-Shot Precise Event Spotting via Unified Multi-Entity Graph and Distilla
        107405, -- 2512.11340 Task-Specific Distance Correlation Matching for Few-Shot Action Recognition
        112433, -- 2403.09805 On the Utility of 3D Hand Poses for Action Recognition
        113027, -- 2405.18012 Flow-Assisted Motion Learning Network for Weakly-Supervised Group Activity
        113390, -- 2312.00826 DEVIAS: Learning Disentangled Video Representations of Action and Scene
        113740, -- 2304.12301 AssemblyHands: Towards Egocentric Activity Understanding via 3D Hand Pose E
        115511, -- 2403.12534 ExACT: Language-guided Conceptual Reasoning and Uncertainty Estimation for
        115882, -- 2404.03924 Learning Correlation Structures for Vision Transformers
        115938, -- 2304.00553 From Isolated Islands to Pangea: Unifying Semantic Space for Human Action U
        116275, -- 2312.13746 Video Recognition in Portrait Mode
        116359, -- 2311.15619 Align Before Adapt: Leveraging Entity-to-Region Alignments for Generalizabl
        116481, -- 2311.03149 Asymmetric Masked Distillation for Pre-Training Small Foundation Models
        116692, -- 2309.11718 CPR-Coach: Recognizing Composite Error Actions based on Single-class Traini
        116699, -- 2403.15194 Your Image is My Video: Reshaping the Receptive Field via Image-To-Video Di
        116737, -- 2403.19944 Binarized Low-light Raw Video Enhancement
        117073, -- 2304.02560 VicTR: Video-conditioned Text Representations for Activity Recognition
        117971, -- 2608.04865 Cooking beyond Frames: A Stereo Event Camera Dataset in the Kitchen
        121038, -- 2601.17391 SMV-EAR: Bring Spatiotemporal Multi-View Representation Learning into Effic
        121745, -- 2605.20680 DarkShake-DVS: Event-based Human Action Recognition under Low-light and Sha
        123916, -- 2104.07905 Ego-Exo: Transferring Visual Representations from Third-person to First-per
        123918, -- 2309.16669 Training a Large Video Model on a Single Machine in a Day
        125983, -- 2512.06275 FacePhys: State of the Heart Learning
        127261, -- 2609.05550 Subject-Relative Micro-Motion and Sleep Dynamics for Near-Infrared Video Sl
        132252 -- 1811.08383 TSM: Temporal Shift Module for Efficient Video Understanding
  );

DELETE FROM paper_method_exclusions x
USING tsm_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM tsm_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM tsm_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- temporal-shift-module: 121 reviewed negatives.
CREATE TEMP TABLE tsm_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'temporal-shift-module'
  AND p.id IN (
        2032, -- 1904.10247 Free-form Video Inpainting with 3D Gated Convolution and Temporal PatchGAN
        2449, -- 1908.08926 Efficient Deep Neural Networks
        2848, -- 1911.10074 Cost-Based Goal Recognition Meets Deep Learning
        3916, -- 2007.10247 Learning Joint Spatial-Temporal Transformations for Video Inpainting
        4322, -- 2010.05099 Diagnosing and Preventing Instabilities in Recurrent Video Processing
        5372, -- 2104.01699 A Configurable BNN ASIC using a Network of Programmable Threshold Logic Sta
        5746, -- 2105.08276 NExT-QA:Next Phase of Question-Answering to Explaining Temporal Actions
        6555, -- 2109.02613 Class Semantics-based Attention for Action Detection
        7037, -- 2110.12130 RCNet: Reverse Feature Pyramid and Cross-scale Shift Network for Object Det
        7302, -- 2111.12624 Self-slimmed Vision Transformer
        7354, -- 2111.15667 Adaptive Token Sampling For Efficient Vision Transformers
        7550, -- 2112.09133 Masked Feature Prediction for Self-Supervised Visual Pre-Training
        7605, -- 2112.13492 Vision Transformer for Small-Size Datasets
        7774, -- 2201.10801 When Shift Operation Meets Vision Transformer: An Extremely Simple Alternat
        8586, -- 2204.02663 Towards An End-to-End Framework for Flow-Guided Video Inpainting
        8646, -- 2204.04611 Decay No More: A Persistent Twitter Dataset for Learning Social Meaning
        9299, -- 2205.15868 CogVideo: Large-scale Pretraining for Text-to-Video Generation via Transfor
        9352, -- 2206.01720 Revisiting the "Video" in Video-Language Understanding
        12297, -- 2301.01380 Ego-Only: Egocentric Action Detection without Exocentric Transferring
        13140, -- 2302.08105 A Neural PDE Solver with Temporal Stencil Modeling
        14030, -- 2303.12793 CiCo: Domain-Aware Sign Language Retrieval via Cross-Lingual Contrastive Le
        14332, -- 2303.17839 Learning Procedure-aware Video Representation from Instructional Videos and
        15385, -- 2305.05662 InternGPT: Solving Vision-Centric Tasks by Interacting with ChatGPT Beyond
        17502, -- 2306.09364 TSMixer: Lightweight MLP-Mixer Model for Multivariate Time Series Forecasti
        17607, -- 2306.11248 Dynamic Perceiver for Efficient Visual Recognition
        17714, -- 2306.13474 Efficient Online Processing with Deep Neural Networks
        17723, -- 2306.13661 Constructing Time-Series Momentum Portfolios with Deep Multi-Task Learning
        18073, -- 2307.03353 A Survey of Deep Learning in Sports Applications: Perception, Comprehension
        18316, -- 2307.08476 SkeletonMAE: Graph-based Masked Autoencoder for Skeleton Sequence Pre-train
        18716, -- 2307.15055 PointOdyssey: A Large-Scale Synthetic Dataset for Long-Term Point Tracking
        18765, -- 2307.16140 Fully $1\times1$ Convolutional Network for Lightweight Image Super-Resoluti
        19075, -- 2308.04770 Objects do not disappear: Video object detection by single-frame object loc
        19357, -- 2308.08885 Event-Guided Procedure Planning from Instructional Videos with Text Supervi
        19619, -- 2308.11358 How Much Temporal Long-Term Context is Needed for Action Segmentation?
        19637, -- 2308.11568 SPANet: Frequency-balancing Token Mixer using Spectral Pooling Aggregation
        22068, -- 2310.10647 A Survey on Video Diffusion Models
        24288, -- 2312.02638 Synchronization is All You Need: Exocentric-to-Egocentric Transfer for Temp
        25545, -- 2401.03395 Deep Learning-based Image and Video Inpainting: A Survey
        25578, -- 2401.03955 Tiny Time Mixers (TTMs): Fast Pre-trained Models for Enhanced Zero/Few-Shot
        26761, -- 2402.02368 Timer: Generative Pre-trained Transformers Are Large Time Series Models
        26944, -- 2402.04324 ConsistI2V: Enhancing Visual Consistency for Image-to-Video Generation
        28624, -- 2403.06102 Coherent Temporal Synthesis for Incremental Action Segmentation
        29164, -- 2403.13244 Instruction Multi-Constraint Molecular Generation Using a Teacher-Student L
        29645, -- 2403.19888 MambaMixer: Efficient Selective State Space Models with Dual Token and Chan
        30038, -- 2404.04848 Task-Aware Encoder Control for Deep Video Compression
        31325, -- 2405.09546 BEHAVIOR Vision Suite: Customizable Dataset Generation via Simulation
        31401, -- 2405.11252 Dreamer XL: Towards High-Resolution Text-to-3D Generation via Trajectory Sc
        34397, -- 2407.07111 Diffusion Model-Based Video Editing: A Survey
        35346, -- 2407.20962 MMTrail: A Multimodal Trailer Video Dataset with Language and Music Descrip
        35595, -- 2408.03223 Don't Think It Twice: Exploit Shift Invariance for Efficient Online Streami
        35827, -- 2408.07410 Aquila2 Technical Report
        36374, -- 2408.16467 Spiking Diffusion Models
        37441, -- 2409.18938 From Seconds to Hours: Reviewing MultiModal Large Language Models on Compre
        38120, -- 2410.06456 From Generalist to Specialist: Adapting Vision Language Models via Task-Spe
        41284, -- 2412.07152 Hero-SR: One-Step Diffusion for Super-Resolution with Human Perception Prio
        41641, -- 2412.11673 $\texttt{DINO-Foresight}$: Looking into the Future with DINO
        43062, -- 2501.12218 Exploring Temporally-Aware Features for Point Tracking
        45524, -- 2503.04130 STORM: Token-Efficient Long Video Understanding for Multimodal LLMs
        46195, -- 2503.12496 Does Your Vision-Language Model Get Lost in the Long Video Sampling Dilemma
        49937, -- 2505.21333 MME-VideoOCR: Evaluating OCR-Based Capabilities of Multimodal LLMs in Video
        54456, -- 2512.01342 InternVideo-Next: Towards General Video Foundation Models without Video-Tex
        57839, -- 2605.00414 Trees to Flows and Back: Unifying Decision Trees and Diffusion Models
        58352, -- 2604.09067 Temporal Patch Shuffle (TPS): Leveraging Patch-Level Shuffling to Boost Gen
        59636, -- 2603.09283 From Ideal to Real: Stable Video Object Removal under Imperfect Conditions
        62184, -- 2601.16210 PyraTok: Language-Aligned Pyramidal Tokenizer for Video Understanding and G
        62656, -- 2601.07468 Beyond Dialogue Time: Temporal Semantic Memory for Personalized LLM Agents
        63571, -- 2512.16371 Factorized Video Generation: Decoupling Scene Construction and Temporal Syn
        64316, -- 2512.01128 OmniFD: A Unified Model for Versatile Face Forgery Detection
        67091, -- 2510.02282 VidGuard-R1: AI-Generated Video Detection and Explanation via Reasoning MLL
        70107, -- 2508.04539 TopKD: Top-scaled Knowledge Distillation
        71308, -- 2507.06782 Temporal Information Retrieval via Time-Specifier Model Merging
        71318, -- 2507.06535 Transferable Parasitic Estimation via Graph Contrastive Learning and Label
        75399, -- 2502.00001 Accelerating PageRank Algorithmic Tasks with a new Programmable Hardware Ar
        78154, -- 2312.02796 Materials Expert-Artificial Intelligence for Materials Discovery
        79054, -- 2305.09673 Vulnerability Detection Using Two-Stage Deep Learning Models
        79266, -- 2303.06053 TSMixer: An All-MLP Architecture for Time Series Forecasting
        80100, -- 2203.15332 Balanced Multimodal Learning via On-the-fly Gradient Modulation
        81256, -- 2006.10260 Video Moment Localization using Object Evidence and Reverse Captioning
        84510, -- 2602.10095 Causality in Video Diffusers is Separable from Denoising
        84678, -- 2603.00906 ShiftLUT: Spatial Shift Enhanced Look-Up Tables for Efficient Image Restora
        84943, -- 2603.16936 Bridging Facial Understanding and Animation via Language Models
        85807, -- 2507.00583 AI-Generated Video Detection via Perceptual Straightening
        87650, -- 2508.15439 Aligning Moments in Time using Video Queries
        88179, -- 2411.14401 Beyond Training: Dynamic Token Merging for Zero-Shot Video Understanding
        89638, -- 2503.07416 TimeStep Master: Asymmetrical Mixture of Timestep LoRA Experts for Versatil
        89958, -- 2506.13320 Action Dubber: Timing Audible Actions via Inflectional Flow
        90522, -- 2505.16980 Pursuing Temporal-Consistent Video Virtual Try-On via Dynamic Pose Interact
        90654, -- 2405.19209 VideoTree: Adaptive Tree-based Video Representation for LLM Reasoning on Lo
        91807, -- 2410.01920 Step-by-Step Reasoning for Math Problems via Twisted Sequential Monte Carlo
        92806, -- 2507.03373 TSM-Bench: Detecting LLM-Generated Text in Real-World Wikipedia Editing Pra
        94475, -- 2508.10453 Trajectory-aware Shifted State Space Models for Online Video Super-Resoluti
        94703, -- 2602.01369 Exposing and Defending the Achilles' Heel of Video Mixture-of-Experts
        94840, -- 2410.03794 Repurposing Foundation Model for Generalizable Medical Time Series Classifi
        94973, -- 2510.08480 Video-STAR: Reinforcing Open-Vocabulary Action Recognition with Tools
        95440, -- 2509.21571 Autonomous UAV–Quadruped Docking in Complex Terrains Via Active Posture Ali
        95929, -- external TIPS: Tiered Information-Rich Planning Strategy for Efficient UGV Autonomou
        97020, -- 2502.17235 Tidiness Score-Guided Monte Carlo Tree Search for Visual Tabletop Rearrange
        98901, -- 2511.13204 RefineVAD: Semantic-Guided Feature Recalibration for Weakly Supervised Vide
        99441, -- 2512.22317 LangPrecip: Language-Aware Multimodal Precipitation Nowcasting
        99572, -- 2511.14220 Twice Sequential Monte Carlo for Tree Search
        104887, -- 2503.12418 A Causality-Inspired Model for Intima-Media Thickening Assessment in Ultras
        106852, -- 2508.01533 ReasonAct: Progressive Training for Fine-Grained Video Reasoning in Small M
        106889, -- 2511.08340 HN-MVTS: HyperNetwork-based Multivariate Time Series Forecasting
        107594, -- 2511.17964 X-ReID: Multi-granularity Information Interaction for Video-Based Visible-I
        109345, -- 2512.20606 Probing and Leveraging Video Diffusion Transformer Features for Robust Poin
        112013, -- external GoP2Vec: A few shot learning for pronunciation assessment with goodness of
        113173, -- 2407.11954 Gated Temporal Diffusion for Stochastic Long-term Dense Anticipation
        113460, -- 2311.13616 Online Video Quality Enhancement with Spatial-Temporal Look-up Tables
        113727, -- 2509.23888 AssemblyHands-X: Modeling 3D Hand-Body Coordination for Understanding Biman
        113743, -- 2608.24804 StarHarness: Evolving Harnesses with Stratified Search for Enterprise Envir
        114085, -- 2609.10355 Why Is Video Still So Expensive? A Survey of Inference-Efficiency Mechanism
        114208, -- 2609.08365 ReMoMask-2: Latent Retrieval-Augmented Masked Motion Generation
        115389, -- 2503.14966 Ultrasound Image-to-Video Synthesis via Latent Dynamic Diffusion Models
        116312, -- 2403.06974 Memory-based Adapters for Online 3D Scene Perception
        118211, -- 2607.29033 SAM+D: Parameter-Efficient Dimensional Lifting of SAM-Family Models via Dep
        118849, -- 2606.23069 Rethinking Prototype-based Similarity Learning for Few-Shot Object Detectio
        122217, -- 2411.18941 Revealing Key Details to See Differences: A Novel Prototypical Perspective
        123917, -- 2301.02311 HierVL: Learning Hierarchical Video-Language Embeddings
        125732, -- external Tokenization and Architecture Jointly Allocate Component Roles in Time Seri
        130118, -- external MemoryFusion: Cross-Temporal Memory Learning for Multimodal Video Fusion
        130345 -- external Nearly Optimal Bounds for Orthogonal Trace-Sum Maximization
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Taxonomy gap fill 2026-11-11: cites TSM only in passing, or TSM abbreviates something else (TSMixer, TSMC, Token Slimming Module, ...)'
FROM tsm_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING tsm_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING tsm_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- fuzzy-logic: 49 links, 3 exclusions. Candidates: every local title/abstract mentioning fuzzy.
CREATE TEMP TABLE fuzzy_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'fuzzy-logic'
  AND p.id IN (
        2969, -- 1912.12932 A New Approach for Explainable Multiple Organ Annotation with Few Data
        3403, -- 2004.11638 Belief functions induced by random fuzzy sets: A general framework for repr
        5455, -- 2104.07060 Membership-Mappings for Data Representation Learning: Measure Theoretic Con
        8685, -- 2204.05765 Membership-Mappings for Practical Secure Distributed Deep Learning
        11724, -- 2211.17226 GENNAPE: Towards Generalized Neural Architecture Performance Estimators
        13330, -- 2302.13482 PyReason: Software for Open World Temporal Logic
        14705, -- 2304.07063 Rethinking Complex Queries on Knowledge Graphs with Neural Link Predictors
        19167, -- 2308.06378 DCNFIS: Deep Convolutional Neuro-Fuzzy Inference System
        20554, -- 2309.09658 A Novel Method of Fuzzy Topic Modeling based on Transformer Processing
        20843, -- 2309.13556 LOGICSEG: Parsing Visual Semantics with Neural Logic Learning and Reasoning
        29812, -- 2404.01526 Categorical semiotics: Foundations for Knowledge Integration
        33239, -- 2406.12345 Navigating Knowledge Management Implementation Success in Government Organi
        33934, -- 2407.01046 FRoG: Evaluating Fuzzy Reasoning of Generalized Quantifiers in Large Langua
        39907, -- 2411.07482 Enhancing Link Prediction with Fuzzy Graph Attention Networks and Dynamic N
        40397, -- 2411.16008 Peritumoral Expansion Radiomics for Improved Lung Cancer Classification
        43210, -- 2501.14661 Neural-Symbolic Message Passing with Dynamic Pruning
        46888, -- 2503.21809 Enhancing Predictive Accuracy in Tennis: Integrating Fuzzy Logic and CV-GRN
        47457, -- 2504.07055 $Π$-NeSy: A Possibilistic Neuro-Symbolic Approach
        56901, -- 2603.18558 HiMu: Hierarchical Multimodal Frame Selection for Long Video Question Answe
        61879, -- 2601.21116 AI-Assisted Engineering Should Track the Epistemic Status and Temporal Vali
        66602, -- 2510.10063 CLMN: Concept based Language Models via Neural Symbolic Reasoning
        68825, -- 2509.10510 FireGNN: Neuro-Symbolic Graph Neural Networks with Trainable Fuzzy Rules fo
        69473, -- 2508.13697 The DeepLog Neurosymbolic Machine
        70343, -- 2508.01581 Polymorphic Combinatorial Frameworks (PCF): Guiding the Design of Mathemati
        78499, -- 2309.11469 Multi-Label Takagi-Sugeno-Kang Fuzzy System
        78754, -- 2307.07881 Graph Embedded Intuitionistic Fuzzy Random Vector Functional Link Neural Ne
        79156, -- 2304.03876 Properties of several metric spaces of fuzzy sets
        80073, -- 2204.04335 Measuring and improving community resilience: a Fuzzy Logic approach
        82445, -- 1511.09230 A Type Theory for Probabilistic and Bayesian Reasoning
        82561, -- 1407.3179 Near-optimal Keypoint Sampling for Fast Pathological Lung Segmentation
        85007, -- 2603.20721 Cross-modal Fuzzy Alignment Network for Text-Aerial Person Retrieval and A
        95438, -- external Mechanomyography-Based Closed-Loop Control of FES Enabling Prolonged Force
        97183, -- external Adaptive Physical Human–Robot Interaction Via a Passivity-Aware Model Predi
        97343, -- 2502.11375 Robot Deformable Object Manipulation Via NMPC-Generated Demonstrations in D
        97597, -- 2602.20216 Sample-Efficient Learning with Online Expert Correction for Autonomous Cath
        101703, -- 2602.03034 KANFIS: A Neuro-Symbolic Framework for Interpretable and Uncertainty-Aware
        102057, -- 2603.08824 SoftJAX & SoftTorch: Empowering Automatic Differentiation Libraries with In
        107172, -- 2511.10392 Enhancing Kernel Power $K$-means: Scalable and Robust Clustering with Rando
        107550, -- 2512.20457 When Natural Strategies Meet Fuzziness and Resource-Bounded Actions
        110688, -- 2507.11405 DCR: Quantifying Data Contamination in LLMs Evaluation
        112682, -- 2407.08252 Spatially-Variant Degradation Model for Dataset-free Super-resolution
        114958, -- 2406.16189 Fuzzy Attention-based Border Rendering Network for Lung Organ Segmentation
        115228, -- external Quality-Aware Fuzzy Min-Max Neural Networks for Dynamic Brain Network Analy
        115707, -- 2311.16117 Predicated Diffusion: Predicate Logic-Based Attention Guidance for Text-to-
        119022, -- external FuDU: A Fuzzy Dual-dimension Uncertainty Framework for Streaming Active Lea
        120051, -- external Fuzzy Multimodal Learning for Trusted Cross-modal Retrieval
        121309, -- external SegGBC: Justifiable Coarse-to-Fine Granular-Ball Computing for Enhancing Cl
        121515, -- external DF^2-VB: Dual-level Fuzzy Fusion with View-specific Boosting for Multi-view
        127065 -- external Uncertainty-Aware Fuzzy Graph Contrastive Learning
  );

DELETE FROM paper_method_exclusions x
USING fuzzy_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM fuzzy_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM fuzzy_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- fuzzy-logic: 3 reviewed negatives.
CREATE TEMP TABLE fuzzy_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'fuzzy-logic'
  AND p.id IN (
        5627, -- 2105.00691 Hybrid Intelligence
        92981, -- 2506.10085 VITA: Zero-Shot Value Functions via Test-Time Adaptation of Vision–Language
        121967 -- external PyBibX – a Python library for bibliometric and scientometric analysis power
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Taxonomy gap fill 2026-11-11: mentions fuzzy logic only in passing'
FROM fuzzy_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING fuzzy_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING fuzzy_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- Hero image credits (images imported with import_entity_image.py).
UPDATE methods SET image_credit = '[TSM: Temporal Shift Module for Efficient Video Understanding](/paper/1811.08383)' WHERE slug = 'temporal-shift-module';
UPDATE methods SET image_credit = '[Fuzzy logic temperature](https://commons.wikimedia.org/wiki/File:Fuzzy_logic_temperature_en.svg), fullofstars, CC BY-SA 3.0' WHERE slug = 'fuzzy-logic';
