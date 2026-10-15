-- Add Fully Convolutional Network (FCN) method, sourced from arXiv 1411.4038.
-- The bare "FCN" keyword is omitted: case-sensitive substring matching would
-- hit "FCNN" (fully connected neural network) and other acronyms.

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
    'fully-convolutional-network',
    'FCN',
    'Fully Convolutional Network (FCN)',
    'A Fully Convolutional Network (FCN) makes dense, per-pixel predictions with a network made only of [convolutional](/methods/convolution) layers, so it accepts inputs of any size and is trained end-to-end, pixels to pixels. Long, Shelhamer and Darrell converted classification [CNNs](/methods/cnn) such as [AlexNet](/methods/alexnet), VGG and GoogLeNet into FCNs by recasting their fully connected layers as convolutions, then added learnable in-network upsampling (transposed convolution) to recover the input resolution. Skip connections fuse coarse, semantic predictions from deep layers with fine, appearance-rich features from shallow layers, giving the FCN-32s, FCN-16s and FCN-8s variants. FCN-8s reached 62.2% mean IU on PASCAL VOC 2012 test, a 20% relative improvement, and the encoder-decoder idea led directly to [U-Net](/methods/u-net), SegNet and DeepLab.',
    'fully convolutional network, FCN-8s, FCN-16s, FCN-32s',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2014,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1411.4038'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Fully Convolutional Networks for Semantic Segmentation',
    'https://github.com/shelhamer/fcn.berkeleyvision.org/blob/master/voc-fcn8s/net.py',
    NULL,
    '[Fully Convolutional Networks for Semantic Segmentation](/paper/1411.4038)'
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
WHERE slug = 'fully-convolutional-network'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'fully-convolutional-network'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-15. The source paper is cited by tens of thousands
-- of papers, mostly in passing. Of the 459 local papers among the first
-- 9,999 Semantic Scholar citers, only the 5 whose title or abstract
-- mention fully convolutional networks or FCNs are linked; the rest are excluded so the hourly reference
-- backfill does not re-link them.
CREATE TEMP TABLE fully_convolutional_network_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'fully-convolutional-network'
  AND p.id IN (
        23151, -- PolyMaX: General Dense Prediction with Mask Transformer
        24637, -- SqueezeSAM: User friendly mobile interactive segmentation
        26827, -- RRWNet: Recursive Refinement Network for effective retinal artery/vein
        34895, -- Make a Strong Teacher with Label Assistance: A Novel Knowledge Distill
        75557 -- A Pipeline and NIR-Enhanced Dataset for Parking Lot Segmentation
  );

DELETE FROM paper_method_exclusions x
USING fully_convolutional_network_cited_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM fully_convolutional_network_cited_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM fully_convolutional_network_cited_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE fully_convolutional_network_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'fully-convolutional-network'
  AND p.id IN (
        18567, -- A Good Student is Cooperative and Reliable: CNN-Transformer Collaborat
        18609, -- Unmasking Anomalies in Road-Scene Segmentation
        18620, -- Model Calibration in Dense Classification with Adaptive Label Perturba
        18719, -- To Adapt or Not to Adapt? Real-Time Adaptation for Semantic Segmentati
        18807, -- Revisiting the Parameter Efficiency of Adapters from the Perspective o
        18836, -- A Novel Temporal Multi-Gate Mixture-of-Experts Approach for Vehicle Tr
        18842, -- LISA: Reasoning Segmentation via Large Language Model
        18852, -- Dynamic Token Pruning in Plain Vision Transformers for Semantic Segmen
        18906, -- Dynamic Token-Pass Transformers for Semantic Segmentation
        18933, -- Convolutions Die Hard: Open-Vocabulary Segmentation with Single Frozen
        19003, -- FeatEnHancer: Enhancing Hierarchical Features for Object Detection and
        19171, -- R2S100K: Road-Region Segmentation Dataset For Semi-Supervised Autonomo
        19194, -- Estimator Meets Equilibrium Perspective: A Rectified Straight Through
        19277, -- ImbSAM: A Closer Look at Sharpness-Aware Minimization in Class-Imbalan
        19296, -- Shortcut-V2V: Compression Framework for Video-to-Video Translation bas
        19333, -- MeViS: A Large-scale Benchmark for Video Segmentation with Motion Expr
        19384, -- Self-Calibrated Cross Attention Network for Few-Shot Segmentation
        19385, -- NAPA-VQ: Neighborhood Aware Prototype Augmentation with Vector Quantiz
        19426, -- LaRS: A Diverse Panoptic Maritime Obstacle Detection Dataset and Bench
        19428, -- VALERIE22 -- A photorealistic, richly metadata annotated dataset of ur
        19464, -- Semantics Meets Temporal Correspondence: Self-supervised Object-centri
        19582, -- Diffusion Model as Representation Learner
        19708, -- Diffusion-based Image Translation with Label Guidance for Domain Adapt
        19728, -- Logic-induced Diagnostic Reasoning for Semi-supervised Semantic Segmen
        19744, -- Boosting Semantic Segmentation from the Perspective of Explicit Class
        19818, -- Beyond One-to-One: Rethinking the Referring Image Segmentation
        19897, -- Learning to Upsample by Learning to Sample
        19936, -- RoboTAP: Tracking Arbitrary Points for Few-Shot Visual Imitation
        19953, -- Emergence of Segmentation with Minimalistic White-Box Transformers
        19959, -- Adversarial Finetuning with Latent Representation Constraint to Mitiga
        20031, -- Few shot font generation via transferring similarity guided global sty
        20054, -- Towards Generic Image Manipulation Detection with Weakly-Supervised Se
        20077, -- Object-Size-Driven Design of Convolutional Neural Networks: Virtual Ax
        20131, -- Building a Winning Team: Selecting Source Model Ensembles using a Subm
        20280, -- Decoupling Common and Unique Representations for Multimodal Self-super
        20545, -- Discovering Sounding Objects by Audio Queries for Audio Visual Segment
        20667, -- Multi-grained Temporal Prototype Learning for Few-shot Video Object Se
        20839, -- Rewrite Caption Semantics: Bridging Semantic Gaps for Language-Supervi
        20843, -- LOGICSEG: Parsing Visual Semantics with Neural Logic Learning and Reas
        20890, -- Informative Data Mining for One-Shot Cross-Domain Semantic Segmentatio
        20981, -- Rapid Network Adaptation: Learning to Adapt Neural Networks Using Test
        21275, -- You Only Look at Once for Real-time and Generic Multi-Task
        22092, -- Towards Training-free Open-world Segmentation via Image Prompt Foundat
        22408, -- P2AT: Pyramid Pooling Axial Transformer for Real-time Semantic Segment
        22469, -- GNeSF: Generalizable Neural Semantic Fields
        22505, -- Image Segmentation using U-Net Architecture for Powder X-ray Diffracti
        22783, -- Battle of the Backbones: A Large-Scale Comparison of Pretrained Models
        23004, -- SegGen: Supercharging Segmentation Models with Text2Mask and Mask2Img
        23319, -- Towards Open-Ended Visual Recognition with Large Language Model
        23533, -- Generalized Category Discovery in Semantic Segmentation
        23542, -- OmniSeg3D: Omniversal 3D Segmentation via Hierarchical Contrastive Lea
        23732, -- SEGIC: Unleashing the Emergent Correspondence for In-Context Segmentat
        23930, -- Generative Models: What Do They Know? Do They Know Things? Let's Find
        23954, -- Improving Feature Stability during Upsampling -- Spectral Artifacts an
        24015, -- Combined Scheduling, Memory Allocation and Tensor Replacement for Mini
        24035, -- DiffCAD: Weakly-Supervised Probabilistic CAD Model Retrieval and Align
        24442, -- FRNet: Frustum-Range Networks for Scalable LiDAR Segmentation
        24570, -- Jumpstarting Surgical Computer Vision
        24596, -- Cooperation Does Matter: Exploring Multi-Order Bilateral Relations for
        24626, -- OpenSD: Unified Open-Vocabulary Segmentation and Detection
        24736, -- See, Say, and Segment: Teaching LMMs to Overcome False Premises
        24740, -- SAM-guided Graph Cut for 3D Instance Segmentation
        24796, -- Tokenize Anything via Prompting
        24832, -- WeatherProof: A Paired-Dataset Approach to Semantic Segmentation in Ad
        24858, -- SkySense: A Multi-Modal Remote Sensing Foundation Model Towards Univer
        25047, -- StableKD: Breaking Inter-block Optimization Entanglement for Stable Kn
        25082, -- TinySAM: Pushing the Envelope for Efficient Segment Anything Model
        25115, -- VCoder: Versatile Vision Encoders for Multimodal Large Language Models
        25570, -- Fully Attentional Networks with Self-emerging Token Labeling
        25599, -- BD-MSA: Body decouple VHR Remote Sensing Image Change Detection method
        25865, -- U-DIADS-Bib: a full and few-shot pixel-precise dataset for document la
        26109, -- Semantic Prompt Learning for Weakly-Supervised Semantic Segmentation
        26115, -- Detect-Order-Construct: A Tree Construction based Approach for Hierarc
        26529, -- Instruction-Guided Scene Text Recognition
        26531, -- Convolution Meets LoRA: Parameter Efficient Finetuning for Segment Any
        26540, -- Multilinear Operator Networks
        26646, -- Delving into Decision-based Black-box Attacks on Semantic Segmentation
        26778, -- Generalizable Entity Grounding via Assistance of Large Language Model
        27350, -- TEXTRON: Weakly Supervised Multilingual Text Detection through Data Pr
        27634, -- Object-level Geometric Structure Preserving for Natural Image Stitchin
        27676, -- Neural Network Diffusion
        27900, -- AutoMMLab: Automatically Generating Deployable Models from Language In
        28255, -- Can Transformers Capture Spatial Relations between Objects?
        28583, -- Frequency-Adaptive Dilated Convolution for Semantic Segmentation
        28587, -- OmniCount: Multi-label Object Counting with Semantic-Geometric Priors
        28724, -- RSBuilding: Towards General Remote Sensing Image Building Extraction a
        28826, -- When Semantic Segmentation Meets Frequency Aliasing
        28855, -- GiT: Towards Generalist Vision Transformer through Universal Language
        28871, -- PosSAM: Panoptic Open-vocabulary Segment Anything
        28934, -- FeatUp: A Model-Agnostic Framework for Features at Any Resolution
        28944, -- SwinMTL: A Shared Architecture for Simultaneous Depth Estimation and S
        29055, -- GenView: Enhancing View Quality with Pretrained Generative Model for S
        29162, -- Modeling the Label Distributions for Weakly-Supervised Semantic Segmen
        29745, -- TryOn-Adapter: Efficient Fine-Grained Clothing Identity Adaptation for
        29823, -- Samba: Semantic Segmentation of Remotely Sensed Images with State Spac
        29856, -- ViTamin: Designing Scalable Vision Models in the Vision-Language Era
        29966, -- Spike-driven Transformer V2: Meta Spiking Neural Network Architecture
        30091, -- CoReS: Orchestrating the Dance of Reasoning and Segmentation
        30101, -- Privacy-Preserving Deep Learning Using Deformable Operators for Secure
        30140, -- WebCode2M: A Real-World Dataset for Code Generation from Webpage Desig
        30157, -- Training-Free Open-Vocabulary Segmentation with Offline Diffusion-Augm
        30253, -- ControlNet++: Improving Conditional Controls with Efficient Consistenc
        30297, -- COCONut: Modernizing COCO Segmentation
        30437, -- Gasformer: A Transformer-based Architecture for Segmenting Methane Emi
        30541, -- SOHES: Self-supervised Open-world Hierarchical Entity Segmentation
        30547, -- Lowering PyTorch's Memory Consumption for Selective Differentiation
        30600, -- BACS: Background Aware Continual Semantic Segmentation
        30809, -- Calculation of Femur Caput Collum Diaphyseal angle for X-Rays images u
        31099, -- Information-driven Affordance Discovery for Efficient Robotic Manipula
        31218, -- Zero Shot Context-Based Object Segmentation using SLIP (SAM+CLIP)
        31248, -- Deep Learning-Based Object Pose Estimation: A Comprehensive Survey
        31300, -- CLIP with Quality Captions: A Strong Pretraining for Vision Tasks
        31553, -- A Survey on Vision-Language-Action Models for Embodied AI
        31756, -- BOLD: Boolean Logic Deep Learning
        31984, -- FUSU: A Multi-temporal-source Land Use Change Segmentation Dataset for
        32083, -- SemFlow: Binding Semantic Segmentation and Image Synthesis via Rectifi
        32399, -- Instance Segmentation and Teeth Classification in Panoramic X-rays
        32678, -- PanoSSC: Exploring Monocular Panoptic 3D Scene Reconstruction for Auto
        32713, -- Beware of Aliases -- Signal Preservation is Crucial for Robust Image R
        32735, -- Vision Model Pre-training on Interleaved Image-Text Data via Latent Co
        33617, -- L-SFAN: Lightweight Spatially-focused Attention Network for Pain Behav
        33915, -- Diffusion Models and Representation Learning: A Survey
        34022, -- Label Anything: Multi-Class Few-Shot Semantic Segmentation with Visual
        34562, -- FANet: Feature Amplification Network for Semantic Segmentation in Clut
        34597, -- Background Adaptation with Residual Modeling for Exemplar-Free Class-I
        34598, -- Eliminating Feature Ambiguity for Few-Shot Segmentation
        34619, -- WPS-SAM: Towards Weakly-Supervised Part Segmentation with Foundation M
        34955, -- I Know About "Up"! Enhancing Spatial Reasoning in Visual Language Mode
        35152, -- Embedding-Free Transformer with Inference Spatial Reduction for Effici
        35309, -- Theia: Distilling Diverse Vision Foundation Models for Robot Learning
        35381, -- MTA-CLIP: Language-Guided Semantic Segmentation with Mask-Text Alignme
        35595, -- Don't Think It Twice: Exploit Shift Invariance for Efficient Online St
        35605, -- Segment Anything in Medical Images and Videos: Benchmark and Deploymen
        35785, -- MAIR++: Improving Multi-view Attention Inverse Rendering with Implicit
        36144, -- UMAD: University of Macau Anomaly Detection Benchmark Dataset
        36147, -- Sapiens: Foundation for Human Vision Models
        36167, -- Frequency-aware Feature Fusion for Dense Image Prediction
        36231, -- Feature Aligning Few shot Learning Method Using Local Descriptors Weig
        36419, -- Language-guided Scale-aware MedSegmentor for Lesion Segmentation in Me
        36687, -- Driving with Prior Maps: Unified Vector Prior Encoding for Autonomous
        36735, -- Seg-HGNN: Unsupervised and Light-Weight Image Segmentation with Hyperb
        36893, -- Multi-Scale Grouped Prototypes for Interpretable Semantic Segmentation
        37090, -- Wavelet GPT: Wavelet Inspired Large Language Models
        37114, -- Deep Generative Adversarial Network for Occlusion Removal from a Singl
        37316, -- Robust Scene Change Detection Using Visual Foundation Models and Cross
        37378, -- DarkSAM: Fooling Segment Anything Model to Segment Nothing
        38248, -- Scaling Up Your Kernels: Large Kernel Design in ConvNets towards Unive
        38502, -- Locality Alignment Improves Vision-Language Models
        39174, -- Simpler Diffusion (SiD2): 1.5 FID on ImageNet512 with pixel-space diff
        39505, -- Human-inspired Perspectives: A Survey on AI Long-term Memory
        39513, -- Event-guided Low-light Video Semantic Segmentation
        39763, -- Diff-2-in-1: Bridging Generation and Dense Perception with Diffusion M
        39891, -- Watermark Anything with Localized Messages
        39993, -- Harnessing Vision Foundation Models for High-Performance, Training-Fre
        40028, -- CorrCLIP: Reconstructing Correlations in CLIP with Off-the-Shelf Found
        40152, -- A Survey of Medical Vision-and-Language Applications and Their Techniq
        40237, -- CLIPer: Hierarchically Improving Spatial Representation of CLIP for Op
        40344, -- There is no SAMantics! Exploring SAM as a Backbone for Visual Understa
        41026, -- Multi-View Pose-Agnostic Change Localization with Zero Labels
        41199, -- Nested Diffusion Models Using Hierarchical Latent Priors
        41641, -- $\texttt{DINO-Foresight}$: Looking into the Future with DINO
        42110, -- Reasoning to Attend: Try to Understand How <SEG> Token Works
        42797, -- TimberVision: A Multi-Task Dataset and Framework for Log-Component Seg
        43331, -- Beyond-Labels: Advancing Open-Vocabulary Segmentation With Vision-Lang
        43468, -- ContextFormer: Redefining Efficiency in Semantic Segmentation
        43643, -- UNIP: Rethinking Pre-trained Attention Patterns for Infrared Semantic
        44131, -- The Stochastic Parrot on LLM's Shoulder: A Summative Assessment of Phy
        44854, -- VPNeXt -- Rethinking Dense Decoding for Plain Vision Transformer
        45197, -- CS-PaperSum: A Large-Scale Dataset of AI-Generated Summaries for Scien
        45391, -- Adaptive Camera Sensor for Vision Models
        45662, -- USP: Unified Self-Supervised Pretraining for Image Generation and Unde
        45703, -- Seg-Zero: Reasoning-Chain Guided Segmentation via Cognitive Reinforcem
        46096, -- Neighboring Autoregressive Modeling for Efficient Visual Generation
        46495, -- DynamicVis: An Efficient and General Visual Foundation Model for Remot
        46509, -- Cross-Modal and Uncertainty-Aware Agglomeration for Open-Vocabulary 3D
        46595, -- Co-SemDepth: Fast Joint Semantic Segmentation and Depth Estimation on
        46654, -- Frequency Dynamic Convolution for Dense Image Prediction
        46884, -- Semantic Library Adaptation: LoRA Retrieval and Fusion for Open-Vocabu
        46985, -- LSNet: See Large, Focus Small
        47258, -- Global Rice Multi-Class Segmentation Dataset (RiceSEG): A Comprehensiv
        47428, -- Earth-Adapter: Bridge the Geospatial Domain Gaps with Mixture of Frequ
        48190, -- VCM: Vision Concept Modeling Based on Implicit Contrastive Learning wi
        48520, -- Split Matching for Inductive Zero-shot Semantic Segmentation
        48722, -- Marigold: Affordable Adaptation of Diffusion-Based Image Generators fo
        48839, -- STEP: A Unified Spiking Transformer Evaluation Platform for Fair and R
        48886, -- DPSeg: Dual-Prompt Cost Volume Learning for Open-Vocabulary Semantic S
        49144, -- Decoupling Classifier for Boosting Few-shot Object Detection and Insta
        49474, -- Extremely Simple Multimodal Outlier Synthesis for Out-of-Distribution
        49709, -- Deformable Attentive Visual Enhancement for Referring Segmentation Usi
        49774, -- The Missing Point in Vision Transformers for Universal Image Segmentat
        50747, -- FLAIR-HUB: Large-scale Multimodal Dataset for Land Cover and Crop Mapp
        51020, -- Symmetrical Flow Matching: Unified Image Generation, Segmentation, and
        51366, -- Rethinking Decoder Design: Improving Biomarker Segmentation Using Dept
        52139, -- Multimodal Referring Segmentation: A Survey
        52214, -- LaTCoder: Converting Webpage Design to Code with Layout-as-Thought
        52269, -- MOSEv2: A More Challenging Dataset for Video Object Segmentation in Co
        52273, -- Improving Masked Style Transfer using Blended Partial Convolution
        52297, -- ASM-UNet: Adaptive Scan Mamba Integrating Group Commonalities and Indi
        52657, -- Durian: Dual Reference-guided Portrait Animation with Attribute Transf
        53094, -- Who invented deep residual learning?
        53450, -- Temporal Prompting Matters: Rethinking Referring Video Object Segmenta
        53994, -- HyperClick: Advancing Reliable GUI Grounding via Uncertainty Calibrati
        54372, -- DiffSeg30k: A Multi-Turn Diffusion Editing Benchmark for Localized AIG
        54398, -- NAF: Zero-Shot Feature Upsampling via Neighborhood Attention Filtering
        54530, -- Shoe Style-Invariant and Ground-Aware Learning for Dense Foot Contact
        54828, -- MeViS: A Multi-Modal Dataset for Referring Motion Expression Video Seg
        54871, -- REGLUE Your Latents with Global and Local Semantics for Entangled Diff
        55376, -- Medical SAM3: A Foundation Model for Universal Prompt-Driven Medical I
        55602, -- Generation Enhances Understanding in Unified Multimodal Models via Mul
        56229, -- VidEoMT: Your ViT is Secretly Also a Video Segmentation Model
        56342, -- Retrieve and Segment: Are a Few Examples Enough to Bridge the Supervis
        57040, -- PMT: Plain Mask Transformer for Image and Video Segmentation with Froz
        57457, -- Towards Long-horizon Agentic Multimodal Search
        58320, -- A3-FPN: Asymptotic Content-Aware Pyramid Attention Network for Dense V
        58602, -- SPAR: Single-Pass Any-Resolution ViT for Open-vocabulary Segmentation
        58676, -- TALENT: Target-aware Efficient Tuning for Referring Image Segmentation
        58779, -- ForestSim: A Synthetic Benchmark for Intelligent Vehicle Perception in
        58813, -- PRUE: A Practical Recipe for Field Boundary Segmentation at Scale
        59125, -- Rethinking Vector Field Learning for Generative Segmentation
        59136, -- Rethinking MLLM Itself as a Segmenter with a Single Segmentation Token
        59241, -- DesertFormer: Transformer-Based Semantic Segmentation for Off-Road Des
        59262, -- SF-Mamba: Rethinking State Space Model for Vision
        59430, -- Bidirectional Cross-Attention Fusion of High-Res RGB and Low-Res HSI f
        59635, -- SpaceSense-Bench: A Large-Scale Multi-Modal Benchmark for Spacecraft P
        61683, -- Segment Any Events with Language
        61980, -- Unveiling Perceptual Artifacts: A Fine-Grained Benchmark for Interpret
        62300, -- Towards Onboard Continuous Change Detection for Floods
        62400, -- Segment and Matte Anything in a Unified Model
        62913, -- WeedRepFormer: Reparameterizable Vision Transformers for Real-Time Wat
        62953, -- EarthVL: A Progressive Earth Vision-Language Understanding and Generat
        63076, -- Promptable Foundation Models for SAR Remote Sensing: Adapting the Segm
        63410, -- Progressive Learned Image Compression for Machine Perception
        63560, -- SARMAE: Masked Autoencoder for SAR Representation Learning
        63858, -- GDKVM: Echocardiography Video Segmentation via Spatiotemporal Key-Valu
        64082, -- Decoding with Structured Awareness: Integrating Directional, Frequency
        64120, -- SAM3-I: Segment Anything with Instructions
        64316, -- OmniFD: A Unified Model for Versatile Face Forgery Detection
        64541, -- DRL-Guided Neural Batch Sampling for Semi-Supervised Pixel-Level Anoma
        64651, -- SAM3-Adapter: Efficient Adaptation of Segment Anything 3 for Camouflag
        64741, -- FireScope: Wildfire Risk Prediction with a Chain-of-Thought Oracle
        64898, -- RISE: Single Static Radar-based Indoor Scene Understanding
        65285, -- MACMD: Multi-dilated Contextual Attention and Channel Mixer Decoding f
        65323, -- CPO: Condition Preference Optimization for Controllable Image Generati
        66190, -- ArmFormer: Lightweight Transformer Architecture for Real-Time Multi-Cl
        66588, -- SaFiRe: Saccade-Fixation Reiteration with Mamba for Referring Image Se
        67002, -- UGround: Towards Unified Visual Grounding with Unrolled Transformers
        67237, -- Normal-Abnormal Guided Generalist Anomaly Detection
        67974, -- MK-UNet: Multi-kernel Lightweight CNN for Medical Image Segmentation
        68276, -- Masked Feature Modeling Enhances Adaptive Segmentation
        68388, -- Microsurgical Instrument Segmentation for Robot-Assisted Surgery
        68474, -- TUNI: Real-time RGB-T Semantic Segmentation with Unified Multi-Modal F
        68516, -- CoSwin: Convolution Enhanced Hierarchical Shifted Window Attention For
        68611, -- Barlow-Swin: Toward a novel siamese-based segmentation architecture us
        69084, -- Integrating SAM Supervision for 3D Weakly Supervised Point Cloud Segme
        69401, -- GasTwinFormer: A Hybrid Vision Transformer for Livestock Methane Emiss
        69427, -- WeedSense: Multi-Task Learning for Weed Segmentation, Height Estimatio
        69810, -- Revisiting Efficient Semantic Segmentation: Learning Offsets for Bette
        69871, -- Architectural Co-Design for Zero-Shot Anomaly Detection: Decoupling Re
        69912, -- BEVANet: Bilateral Efficient Visual Attention Network for Real-Time Se
        70006, -- Learning 3D Texture-Aware Representations for Parsing Diverse Human Cl
        70778, -- SemiSegECG: A Multi-Dataset Benchmark for Semi-Supervised Semantic Seg
        70882, -- DenseSR: Image Shadow Removal as Dense Prediction
        71091, -- Spatial Frequency Modulation for Semantic Segmentation
        71271, -- SURPRISE3D: A Dataset for Spatial Understanding and Reasoning in Compl
        71615, -- MedSAM-CA: A CNN-Augmented ViT with Attention-Enhanced Multi-Scale Fus
        71696, -- Partial CLIP is Enough: Chimera-Seg for Zero-shot Semantic Segmentatio
        71913, -- Sequential Policy Gradient for Adaptive Hyperparameter Optimization
        72248, -- LLMs Can Compensate for Deficiencies in Visual Representations
        72274, -- GlobalBuildingAtlas: An Open Global and Complete Dataset of Building P
        72789, -- Segment Anyword: Mask Prompt Inversion for Open-Set Grounded Segmentat
        73378, -- SAIP-Net: Enhancing Remote Sensing Image Segmentation via Spectral Ada
        73602, -- MedSegFactory: Text-Guided Generation of Medical Image-Mask Pairs
        73960, -- High Temporal Consistency through Semantic Similarity Propagation in S
        74273, -- Underlying Semantic Diffusion for Effective and Efficient In-Context L
        74291, -- Is Pre-training Applicable to the Decoder for Dense Prediction?
        74299, -- Catheter Detection and Segmentation in X-ray Images via Multi-task Lea
        74628, -- YUNet: Improved YOLOv11 Network for Skyline Detection
        75041, -- Video-based Surgical Tool-tip and Keypoint Tracking using Multi-frame
        76138, -- A Deep Learning-Based Approach for Mangrove Monitoring
        76212, -- Semantic Segmentation of Unmanned Aerial Vehicle Remote Sensing Images
        76823, -- Swish-T : Enhancing Swish Activation with Tanh Bias for Improved Neura
        77048, -- UniVS: Unified and Universal Video Segmentation with Prompts as Querie
        77376, -- ThermoPore: Predicting Part Porosity Based on Thermal Images Using Dee
        77429, -- SegFormer3D: an Efficient Transformer for 3D Medical Image Segmentatio
        77561, -- Towards Image Ambient Lighting Normalization
        77599, -- PECI-Net: Bolus segmentation from video fluoroscopic swallowing study
        77700, -- When do Convolutional Neural Networks Stop Learning?
        78031, -- FENet: Focusing Enhanced Network for Lane Detection
        78067, -- Open Vocabulary Semantic Scene Sketch Understanding
        78185, -- Cam4DOcc: Benchmark for Camera-Only 4D Occupancy Forecasting in Autono
        78195, -- Mitigating Hallucination in Visual Language Models with Visual Supervi
        78415, -- Robust Multimodal Learning with Missing Modalities via Parameter-Effic
        78524, -- Robust Burned Area Delineation through Multitask Learning
        78545, -- MMSFormer: Multimodal Transformer for Material and Semantic Segmentati
        78735, -- Building Extraction from Remote Sensing Images via an Uncertainty-Awar
        83153, -- From Pixels to Concepts: Do Segmentation Models Understand What They S
        84034, -- F2Net: A Frequency-Fused Network for Ultra-High Resolution Remote Sens
        84312, -- SAGE: Style-Adaptive Generalization for Privacy-Constrained Semantic S
        84855, -- SPEGC: Continual Test-Time Adaptation via Semantic-Prompt-Enhanced Gra
        85029, -- PEARL: Geometry Aligns Semantics for Training-Free Open-Vocabulary Sem
        85077, -- SemLayer: Semantic-aware Generative Segmentation and Layer Constructio
        85086, -- RS-SSM: Refining Forgotten Specifics in State Space Model for Video Se
        85144, -- OSA: Echocardiography Video Segmentation via Orthogonalized State Upda
        85178, -- You Only Erase Once: Erasing Anything without Bringing Unexpected Cont
        85279, -- Batch Loss Score for Dynamic Data Pruning
        85595, -- Distributed Image Compression with Multimodal Side Information at Extr
        85699, -- Point or Line? Using Line-based Representation for Panoptic Symbol Spo
        85734, -- CAML: Collaborative Auxiliary Modality Learning for Multi-Agent System
        86136, -- On the VC dimension of deep group convolutional neural networks
        86170, -- OpenWorldSAM: Extending SAM2 for Universal Image Segmentation with Lan
        86331, -- Native Segmentation Vision Transformers
        86536, -- MANGO: Multimodal Attention-based Normalizing Flow Approach to Fusion
        87543, -- Rethinking Detecting Salient and Camouflaged Objects in Unconstrained
        87602, -- LawDIS: Language-Window-based Controllable Dichotomous Image Segmentat
        87702, -- Dynamic Dictionary Learning for Remote Sensing Image Segmentation
        87713, -- Balancing Conservatism and Aggressiveness: Prototype-Affinity Hybrid N
        87895, -- SkySense V2: A Unified Foundation Model for Multi-modal Remote Sensing
        87937, -- Object-level Correlation for Few-Shot Segmentation
        87945, -- Learn2Synth: Learning Optimal Data Synthesis Using Hypergradients for
        88183, -- Towards Fine-grained Interactive Segmentation in Images and Videos
        88271, -- Unified Open-World Segmentation with Multi-Modal Prompts
        88292, -- Reverse Convolution and Its Applications to Image Restoration
        88405, -- Frequency-Dynamic Attention Modulation For Dense Prediction
        88492, -- SpikePack: Enhanced Information Flow in Spiking Neural Networks with H
        88608, -- Complex Wavelet Mutual Information Loss: A Multi-Scale Loss Function f
        88632, -- Curvature Enhanced Data Augmentation for Regression
        88956, -- Beyond Low-rank Decomposition: A Shortcut Approach for Efficient On-De
        89930, -- Unlocking the Power of SAM 2 for Few-Shot Segmentation
        90019, -- Adapter Naturally Serves as Decoupler for Cross-Domain Few-Shot Semant
        90079, -- CALICO: Part-Focused Semantic Co-Segmentation with Large Vision-Langua
        90099, -- Inference-Scale Complexity in ANN-SNN Conversion for High-Performance
        90160, -- DocSAM: Unified Document Image Segmentation via Query Decomposition an
        90170, -- MDP: Multidimensional Vision Model Pruning with Latency Constraint
        90192, -- Foveated Instance Segmentation
        90193, -- Universal Domain Adaptation for Semantic Segmentation
        90260, -- Data Distributional Properties As Inductive Bias for Systematic Genera
        90324, -- dFLMoE: Decentralized Federated Learning via Mixture of Experts for Me
        90409, -- CoMBO: Conflict Mitigation via Branched Optimization for Class Increme
        90452, -- Fine-Grained Image-Text Correspondence with Cost Aggregation for Open-
        90499, -- MaSS13K: A Matting-level Semantic Segmentation Benchmark
        90517, -- Unified Dense Prediction of Video Diffusion
        90542, -- Repurposing Stable Diffusion Attention for Training-Free Unsupervised
        90653, -- Golden Cudgel Network for Real-Time Semantic Segmentation
        90718, -- Exploiting Temporal State Space Sharing for Video Semantic Segmentatio
        90789, -- The Devil is in Low-Level Features for Cross-Domain Few-Shot Segmentat
        91626, -- Bringing NeRFs to the Latent Space: Inverse Graphics Autoencoder
        91899, -- Accessing Vision Foundation Models via ImageNet-1K
        92118, -- Aligned Datasets Improve Detection of Latent Diffusion-Generated Image
        92504, -- A Systematic Survey on Deep Learning Architectures for Point Cloud Cla
        93288, -- RainPro-8: An Efficient Deep Learning Model to Estimate Rainfall Proba
        95061, -- Breaking Scale Anchoring: Frequency Representation Learning for Accura
        95702, -- TERDNet: Transformer Encoder-Recurrent Decoder Network for Scene Chang
        96508, -- Anatomical Prior-Driven Framework for Autonomous Robotic Cardiac Ultra
        97660, -- GSRender: Deduplicated Occupancy Estimation Via Weakly Supervised 3D G
        98530, -- ViT-Up: Faithful Feature Upsampling for Vision Transformers
        99175, -- LightAVSeg: Lightweight Audio-Visual Segmentation
        99333, -- Are We Overconfident in Models and Results for Semi-Supervised 3D Medi
        103806, -- SAM-MT: Real-Time Interactive Multi-Target Video Segmentation
        104083, -- HARMamba: Efficient and Lightweight Wearable Sensor Human Activity Rec
        106465, -- Exploring Efficient Open-Vocabulary Segmentation in the Remote Sensing
        106487, -- Flow-Induced Diagonal Gaussian Processes
        106565, -- Semi-Supervised Semantic Segmentation via Derivative Label Propagation
        106867, -- DuGI-MAE: Improving Infrared Mask Autoencoders via Dual-Domain Guidanc
        107200, -- Toward Real-World High-Precision Image Matting and Segmentation
        107830, -- Do We Need Perfect Data? Leveraging Noise for Domain Generalized Segme
        108084, -- BD-Net: Has Depth-Wise Convolution Ever Been Applied in Binary Neural
        108190, -- SSR: Semantic and Spatial Rectification for CLIP-based Weakly Supervis
        108319, -- Divide-and-Conquer Decoupled Network for Cross-Domain Few-Shot Segment
        109354, -- 3D TransUNet: Advancing Medical Image Segmentation through Vision Tran
        109846, -- Luce: Relightable Gaussians for 3D Asset Generation
        112483, -- CPM: Class-conditional Prompting Machine for Audio-visual Segmentation
        112507, -- Joint RGB-Spectral Decomposition Model Guided Image Enhancement in Mob
        112537, -- A Simple Latent Diffusion Approach for Panoptic Segmentation and Mask
        112590, -- InfMAE: A Foundation Model in The Infrared Modality
        112605, -- Learning to Obstruct Few-Shot Image Classification over Restricted Cla
        112625, -- Deep Nets with Subsampling Layers Unwittingly Discard Useful Activatio
        112696, -- Early Preparation Pays Off: New Classifier Pre-tuning for Class Increm
        112753, -- Representing Topological Self-Similarity Using Fractal Feature Maps fo
        112804, -- OvSW: Overcoming Silent Weights for Accurate Binary Neural Networks
        112891, -- A Semantic Space is Worth 256 Language Descriptions: Make Stronger Seg
        112922, -- Free-ATM: Harnessing Free Attention Masks for Representation Learning
        112924, -- In Defense of Lazy Visual Grounding for Open-Vocabulary Semantic Segme
        112940, -- Effective Lymph Nodes Detection in CT Scans Using Location Debiased Qu
        112949, -- Knowledge Transfer with Simulated Inter-Image Erasing for Weakly Super
        112978, -- Benchmarking Object Detectors with COCO: A New Path Forward
        113000, -- Rethinking and Improving Visual Prompt Selection for In-Context Learni
        113034, -- Active Generation for Image Classification
        113059, -- Progressive Proxy Anchor Propagation for Unsupervised Semantic Segment
        113064, -- Mitigating Background Shift in Class-Incremental Semantic Segmentation
        113088, -- Region-aware Distribution Contrast: A Novel Approach to Multi-Task Par
        113093, -- StructLDM: Structured Latent Diffusion for 3D Human Generation
        113106, -- Context-Guided Spatial Feature Reconstruction for Efficient Semantic S
        113185, -- Rate-Distortion-Cognition Controllable Versatile Neural Image Compress
        113313, -- Single-Photon 3D Imaging with Equi-Depth Photon Histograms
        113354, -- From Pixels to Objects: A Hierarchical Approach for Part and Object Se
        113363, -- Sparse Refinement for Efficient High-Resolution Semantic Segmentation
        113397, -- Centering the Value of Every Modality: Towards Efficient and Resilient
        113473, -- Stepping Stones: A Progressive Training Strategy for Audio-Visual Sema
        113543, -- To Supervise or Not to Supervise: Understanding and Addressing the Key
        113599, -- SAM4MLLM: Enhance Multi-Modal Large Language Model for Referring Expre
        113703, -- Distributed Semantic Segmentation with Efficient Joint Source and Task
        113907, -- Autoregressive Mosaics: Probing 2D Spatial Reasoning in Text-Only Lang
        114406, -- Biophysics Informed Pathological Regularisation for Brain Tumour Segme
        115072, -- LiverUSRecon: Automatic 3D Reconstruction and Volumetry of the Liver w
        115118, -- MH-pFLGB: Model Heterogeneous personalized Federated Learning via Glob
        115474, -- Open-Vocabulary Segmentation with Semantic-Assisted Calibration
        115496, -- Curriculum Point Prompting for Weakly-Supervised Referring Image Segme
        115555, -- Open-Set Domain Adaptation for Semantic Segmentation
        115578, -- Domain Prompt Learning with Quaternion Networks
        115687, -- APSeg: Auto-Prompt Network for Cross-Domain Few-Shot Semantic Segmenta
        115690, -- LORS: Low-rank Residual Structure for Parameter-Efficient Network Stac
        115770, -- Open-World Semantic Segmentation Including Class Similarity
        115869, -- Hunting Attributes: Context Prototype-Aware Learning for Weakly Superv
        115933, -- Beyond Image Super-Resolution for Image Recognition with Task-Driven P
        115999, -- Frozen CLIP: A Strong Backbone for Weakly Supervised Semantic Segmenta
        116002, -- SED: A Simple Encoder-Decoder for Open-Vocabulary Semantic Segmentatio
        116028, -- AllSpark: Reborn Labeled Features from Unlabeled in Transformer for Se
        116073, -- Multi-Task Dense Prediction via Mixture of Low-Rank Experts
        116088, -- Learn to Rectify the Bias of CLIP for Unsupervised Semantic Segmentati
        116105, -- Domain-Rectifying Adapter for Cross-Domain Few-Shot Segmentation
        116217, -- Universal Segmentation at Arbitrary Granularity with Language Instruct
        116243, -- OpenESS: Event-based Semantic Scene Understanding with Open Vocabulari
        116266, -- Boosting Adversarial Transferability by Block Shuffle and Rotation
        116419, -- Rethinking Prior Information Generation with CLIP for Few-Shot Segment
        116426, -- Mask Grounding for Referring Image Segmentation
        116507, -- Towards the Uncharted: Density-Descending Feature Perturbation for Sem
        116518, -- SNI-SLAM: Semantic Neural Implicit SLAM
        116532, -- Rethinking Interactive Image Segmentation with Low Latency High Qualit
        116571, -- Image-to-Image Matching via Foundation Models: A New Perspective for O
        116577, -- Contextrast: Contextual Contrastive Learning for Semantic Segmentation
        116699, -- Your Image is My Video: Reshaping the Receptive Field via Image-To-Vid
        116721, -- Open-Vocabulary Semantic Segmentation with Image Embedding Balancing
        116885, -- SFOD: Spiking Fusion Object Detector
        117034, -- Separate and Conquer: Decoupling Co-occurrence via Decomposition and R
        117036, -- Segment Any Event Streams via Weighted Adaptation of Pivotal Tokens
        117039, -- Clustering Propagation for Universal Medical Image Segmentation
        117057, -- Segment Every Out-of-Distribution Object
        117885, -- Learning to Suppress SPAD-based LiDAR Flare
        118405, -- OSVE: One Step Video Editing with One Step Diffusion Models
        118536, -- DiffRGD: An Inference-Time Diffusion Guidance Through Riemannian Gradi
        118847, -- Learning Structurally Consistent Representations for Multi-View Radar
        119064, -- Learning Semantic-Robust Change Detection via Semantic-Invariant Self-
        119122, -- Learning with Bilevel-Minimax Optimization for Efficient and Reliable
        119136, -- Fast and Flexible Robustness Certificates for Semantic Segmentation
        119144, -- Learning from Adversity: Semantic-Aware Mask Refinement through Advers
        119637, -- WeatherReasonSeg: A Benchmark for Weather-Aware Reasoning Segmentation
        120101, -- DeformCL: Learning Deformable Centerline Representation for Vessel Ext
        120509, -- DSV-LFS: Unifying LLM-Driven Semantic Cues with Visual Features for Ro
        120665, -- Towards Robust Multi-Modal Semantic Segmentation with Teacher-Student
        122349, -- Hard Vision, Easy Vision: What GPT-6 Astra Reveals Across Computer Vis
        122440, -- LightMIS: Ultra-Lightweight Medical Image Segmentation Without a Stage
        122647, -- GTR: Gated Token Recurrence for Efficient Dense Prediction
        123085, -- Efficient Global Neural Architecture Search
        123338 -- StitchFusion: Weaving Any Visual Modalities to Enhance Multimodal Sema
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'FCN curation 2026-10-15: cites the source paper without using FCN'
FROM fully_convolutional_network_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING fully_convolutional_network_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING fully_convolutional_network_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id
  AND pm.paper_id <> (SELECT source_paper_id FROM methods WHERE slug = 'fully-convolutional-network');
