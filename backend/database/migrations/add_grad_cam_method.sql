-- Add Grad-CAM method, sourced from arXiv 1610.02391.

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
    'grad-cam',
    'Grad-CAM',
    'Gradient-weighted Class Activation Mapping (Grad-CAM)',
    'Grad-CAM produces class-discriminative visual explanations for decisions of a [CNN](/methods/cnn). It backpropagates the score of a target class to the feature maps of the last convolutional layer, [global-average-pools](/methods/global-average-pooling) these gradients into one importance weight per channel, and takes a ReLU of the weighted sum of the feature maps to get a coarse heatmap of the regions that support the class. Unlike CAM it needs no architectural change or retraining, so it applies to classification, image captioning, visual question answering and reinforcement learning models alike. Multiplying the heatmap with guided backpropagation gives Guided Grad-CAM, a high-resolution and class-discriminative visualization. Grad-CAM is one of the most widely used saliency methods for interpreting vision models and diagnosing dataset bias.',
    'Grad-CAM, GradCAM, gradient-weighted class activation mapping',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2016,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1610.02391'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Grad-CAM: Visual Explanations from Deep Networks via Gradient-based Localization',
    'https://github.com/ramprs/grad-cam',
    NULL,
    '[Grad-CAM: Visual Explanations from Deep Networks via Gradient-based Localization](/paper/1610.02391)'
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
WHERE slug = 'grad-cam'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'grad-cam'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-15. The source paper is cited by tens of thousands
-- of papers, mostly in passing. Of the 417 local papers among the first
-- 9,999 Semantic Scholar citers, only the 29 whose title or abstract
-- mention Grad-CAM or class activation maps are linked; the rest are excluded so the hourly reference
-- backfill does not re-link them.
CREATE TEMP TABLE grad_cam_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'grad-cam'
  AND p.id IN (
        42901, -- Prompt-CAM: A Simpler Interpretable Transformer for Fine-Grained Analy
        46815, -- Exploring CLIP's Dense Knowledge for Weakly Supervised Semantic Segmen
        57171, -- AI Generalisation Gap In Comorbid Sleep Disorder Staging
        58930, -- Combi-CAM: A Novel Multi-Layer Approach for Explainable Image Geolocal
        60693, -- Learning on the Fly: Replay-Based Continual Object Perception for Indo
        62355, -- Seeing Isn't Always Believing: Analysis of Grad-CAM Faithfulness and L
        63094, -- Uncertainty-Calibrated Explainable AI for Fetal Ultrasound Plane Class
        64061, -- Measuring the Effect of Background on Classification and Feature Impor
        65547, -- Weakly Supervised Pneumonia Localization from Chest X-Rays Using Deep
        67649, -- Seeing Isn't Believing: Context-Aware Adversarial Patch Synthesis via
        68072, -- CAMBench-QR : A Structure-Aware Benchmark for Post-Hoc Explanations wi
        68566, -- Enhanced SegNet with Integrated Grad-CAM for Interpretable Retinal Lay
        68585, -- MedicalPatchNet: A Patch-Based Self-Explainable AI Architecture for Ch
        69278, -- SugarcaneShuffleNet: A Very Fast, Lightweight Convolutional Neural Net
        69942, -- From Explainable to Explained AI: Ideas for Falsifying and Quantifying
        71641, -- Token Activation Map to Visually Explain Multimodal LLMs
        71826, -- AQUA20: A Benchmark Dataset for Underwater Species Classification unde
        72503, -- TalkingHeadBench: A Multi-Modal Benchmark & Analysis of Talking-Head D
        72803, -- Soft-CAM: Making black box models self-explainable for medical image a
        73095, -- Breast Cancer Classification in Deep Ultraviolet Fluorescence Images U
        73323, -- Towards a deep learning approach for classifying treatment response in
        73799, -- CF-CAM: Cluster Filter Class Activation Mapping for Reliable Gradient-
        84912, -- LUMINA: A Multi-Vendor Mammography Benchmark with Energy Harmonization
        87285, -- Cross-modal Associations in Vision and Language Models: Revisiting the
        87884, -- On the Complexity-Faithfulness Trade-off of Gradient-Based Explanation
        90931, -- Prototype-Based Image Prompting for Weakly Supervised Histopathologica
        102974, -- Diffusion-CAM: Faithful Visual Explanations for dMLLMs
        105315, -- Inter-class separability loss for weakly supervised mutually exclusive
        108993 -- Finer-CAM: Spotting the Difference Reveals Finer Details for Visual Ex
  );

DELETE FROM paper_method_exclusions x
USING grad_cam_cited_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM grad_cam_cited_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM grad_cam_cited_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE grad_cam_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'grad-cam'
  AND p.id IN (
        43057, -- FedCLEAN: byzantine defense by CLustering Errors of Activation maps in
        43292, -- Rethinking the Bias of Foundation Model under Long-tailed Distribution
        43560, -- Learning Fused State Representations for Control from Multi-View Obser
        43724, -- REALEDIT: Reddit Edits As a Large-scale Empirical Dataset for Image Tr
        43816, -- Bridging the Gap in XAI-Why Reliable Metrics Matter for Explainability
        43951, -- Sparse Autoencoders for Scientifically Rigorous Interpretation of Visi
        44034, -- We Can't Understand AI Using our Existing Vocabulary
        44484, -- Archetypal SAE: Adaptive and Stable Dictionary Learning for Concept Ex
        44580, -- Medical Image Classification with KAN-Integrated Transformers and Dila
        44784, -- MaxSup: Overcoming Representation Collapse in Label Smoothing
        44907, -- SFLD: Reducing the content bias for AI-generated Image Detection
        44944, -- MLLMs Know Where to Look: Training-free Perception of Small Visual Det
        45146, -- OverLoCK: An Overview-first-Look-Closely-next ConvNet with Context-Mix
        45166, -- Large Language Models as Attribution Regularizers for Efficient Model
        45195, -- Interpreting CLIP with Hierarchical Sparse Autoencoders
        45256, -- DADM: Dual Alignment of Domain and Modality for Face Anti-spoofing
        45425, -- XFMamba: Cross-Fusion Mamba for Multi-View Medical Image Classificatio
        45447, -- LangGas: Introducing Language in Selective Zero-Shot Background Subtra
        45627, -- CACTUS: An Open Dataset and Framework for Automated Cardiac Assessment
        45733, -- Interactive Medical Image Analysis with Concept-based Similarity Reaso
        45854, -- OLMD: Orientation-aware Long-term Motion Decoupling for Continuous Sig
        45934, -- Discovering Influential Neuron Path in Vision Transformers
        45958, -- ForAug: Recombining Foregrounds and Backgrounds to Improve Vision Tran
        46031, -- MACS: Multi-source Audio-to-image Generation with Contextual Significa
        46290, -- Where do Large Vision-Language Models Look at when Answering Questions
        46368, -- Spot the Fake: Large Multimodal Model-Based Synthetic Image Detection
        46387, -- LEGION: Learning to Ground and Explain for Synthetic Image Detection
        46392, -- TruthLens:A Training-Free Paradigm for DeepFake Detection
        46580, -- GOAL: Global-local Object Alignment Learning
        46617, -- Enhancing Dataset Distillation via Non-Critical Region Refinement
        46740, -- Attention IoU: Examining Biases in CelebA using Attention Maps
        46800, -- Imitating Radiological Scrolling: A Global-Local Attention Model for 3
        47089, -- Hybrid Global-Local Representation with Augmented Spatial Guidance for
        47280, -- SARLANG-1M: A Benchmark for Vision-Language Modeling in SAR Image Unde
        47627, -- A Survey on Efficient Vision-Language Models
        47933, -- Towards Explainable Fake Image Detection with Multi-Modal Large Langua
        47943, -- LGD: Leveraging Generative Descriptions for Zero-Shot Referring Image
        48302, -- Optimizing Deep Neural Networks using Safety-Guided Self Compression
        48433, -- Not All Parameters Matter: Masking Diffusion Models for Enhancing Gene
        48742, -- On Measuring Intrinsic Causal Attributions in Deep Neural Networks
        48814, -- M4-SAR: A Multi-Resolution, Multi-Polarization, Multi-Scene, Multi-Sou
        49026, -- Time series saliency maps: explaining models across multiple domains
        50432, -- Revisiting LRP: Positional Attribution as the Missing Ingredient for T
        50545, -- Adapt before Continual Learning
        50745, -- Interpretable and Reliable Detection of AI-Generated Images via Ground
        50872, -- CanadaFireSat: Toward high-resolution wildfire forecasting with multip
        50910, -- An Explainable Deep Learning Framework for Brain Stroke and Tumor Prog
        51719, -- VERITAS: Verification and Explanation of Realness in Images for Transp
        51795, -- MST-Distill: Mixture of Specialized Teachers for Cross-Modal Knowledge
        51888, -- SpaRTAN: Spatial Reinforcement Token-based Aggregation Network for Vis
        52041, -- Pixels, Patterns, but No Poetry: To See The World like Humans
        52092, -- Rep-MTL: Unleashing the Power of Representation-level Task Saliency fo
        52402, -- Unlearning Comparator: A Visual Analytics System for Comparative Evalu
        52731, -- Gradient-Attention Guided Dual-Masking Synergetic Framework for Robust
        52984, -- RefAM: Attention Magnets for Zero-Shot Referral Segmentation
        53679, -- RL makes MLLMs see better than SFT
        53852, -- MergeMix: A Unified Augmentation Paradigm for Visual and Multi-Modal U
        54316, -- Rethinking Saliency Maps: A Cognitive Human Aligned Taxonomy and Evalu
        54702, -- Pay Less Attention to Function Words for Free Robustness of Vision-Lan
        54857, -- Hybrid Attribution Priors for Explainable and Robust Model Training
        55611, -- Spotlighting Task-Relevant Features: Object-Centric Representations fo
        55820, -- Grounding and Enhancing Informativeness and Utility in Dataset Distill
        56043, -- From Features to Actions: Explainability in Traditional and Agentic AI
        56458, -- Easy to Learn, Yet Hard to Forget: Towards Robust Unlearning Under Bia
        56559, -- FVG-PT: Adaptive Foreground View-Guided Prompt Tuning for Vision-Langu
        56574, -- SlowBA: An efficiency backdoor attack towards VLM-based GUI agents
        56828, -- Look Before Acting: Enhancing Vision Foundation Representations for Vi
        57210, -- Automatic Image-Level Morphological Trait Annotation for Organismal Im
        57369, -- Structural Graph Probing of Vision-Language Models
        57752, -- ATTN-FIQA: Interpretable Attention-based Face Image Quality Assessment
        57946, -- Fusion Complexity Inversion: Why Simpler Cross View Modules Outperform
        58023, -- Attention-ResUNet for Automated Fetal Head Segmentation
        58407, -- Interpretable Clinical Classification with Kolmogorov-Arnold Networks
        58476, -- Dual-Thresholded Heatmap-Guided Proposal Clustering and Negative Certa
        58677, -- Toward Robust Semantic Communications: Proactive Importance-Ordered Re
        58833, -- Seeing Like Radiologists: Context- and Gaze-Guided Vision-Language Pre
        58987, -- AlphaDiffract: Automated Crystallographic Analysis of Powder X-ray Dif
        59237, -- YOLO26: An Analysis of NMS-Free End to End Framework for Real-Time Obj
        59533, -- Toward Complex-Valued Neural Networks for Waveform Generation
        59879, -- Beyond the Patch: Exploring Vulnerabilities of Visuomotor Policies via
        59929, -- MoECLIP: Patch-Specialized Experts for Zero-shot Anomaly Detection
        60234, -- ViCLIP-OT: The First Foundation Vision-Language Model for Vietnamese I
        60384, -- Pixels Don't Lie (But Your Detector Might): Bootstrapping MLLM-as-a-Ju
        60516, -- Formal Mechanistic Interpretability: Automated Circuit Discovery with
        61086, -- DAVE: Distribution-aware Attribution via ViT Gradient Decomposition
        61306, -- Deep-learning-based pan-phenomic data reveals the explosive evolution
        61516, -- Rectified LpJEPA: Joint-Embedding Predictive Architectures with Sparse
        61650, -- Pulling Back the Curtain on Deep Networks
        61709, -- AI-Generated Image Detectors Overrely on Global Artifacts: Evidence fr
        61791, -- Localizing Speech Deepfakes Beyond Transitions via Segment-Aware Learn
        61952, -- DiSa: Saliency-Aware Foreground-Background Disentangled Framework for
        61980, -- Unveiling Perceptual Artifacts: A Fine-Grained Benchmark for Interpret
        62119, -- Interpreting Agentic Systems: Beyond Model Explanations to System-Leve
        62130, -- StealthMark: Harmless and Stealthy Ownership Verification for Medical
        62233, -- WeDefense: A Toolkit to Defend Against Fake Audio
        62358, -- SL-CBM: Enhancing Concept Bottleneck Models with Semantic Locality for
        62700, -- Spec-o3: A Tool-Augmented Vision-Language Agent for Rare Celestial Obj
        63134, -- The Impact of Lesion Focus on the Performance of AI-Based Melanoma Cla
        63277, -- Clutter-Resistant Vision-Language-Action Models through Object-Centric
        63289, -- Patch-Discontinuity Mining for Generalized Deepfake Detection
        63410, -- Progressive Learned Image Compression for Machine Perception
        63912, -- ConceptPose: Training-Free Zero-Shot Object Pose Estimation using Conc
        63939, -- Uncertainty-Aware Subset Selection for Robust Visual Explainability un
        64015, -- Always Keep Your Promises: DynamicLRP, A Model-Agnostic Solution To La
        64193, -- Video2Act: A Dual-System Video Diffusion Policy with Robotic Spatio-Mo
        64339, -- AFRAgent : An Adaptive Feature Renormalization Based High Resolution A
        64528, -- Mistake Attribution: Fine-Grained Mistake Understanding in Egocentric
        64623, -- BackdoorVLM: A Benchmark for Backdoor Attacks on Vision-Language Model
        64699, -- Matching-Based Few-Shot Semantic Segmentation Models Are Interpretable
        64719, -- Towards Open-Ended Visual Scientific Discovery with Sparse Autoencoder
        64731, -- DSeq-JEPA: Discriminative Sequential Joint-Embedding Predictive Archit
        64812, -- TopoReformer: Mitigating Adversarial Attacks Using Topological Purific
        65340, -- DORAEMON: A Unified Library for Visual Object Modeling and Representat
        65423, -- Object Detection as an Optional Basis: A Graph Matching Network for Cr
        65485, -- Learning to Seek Evidence: A Verifiable Reasoning Agent with Causal Fa
        65601, -- AFM-Net: Advanced Fusing Hierarchical CNN Visual Priors with Global Se
        65714, -- Understanding Multi-View Transformers
        65851, -- Learning Event-guided Exposure-agnostic Video Frame Interpolation via
        65877, -- GRAID: Enhancing Spatial Reasoning of VLMs Through High-Fidelity Data
        66087, -- A Renaissance of Explicit Motion Information Mining from Transformers
        66543, -- Structured Spectral Graph Representation Learning for Multi-label Abno
        66732, -- Approximate Domain Unlearning for Vision-Language Models
        66951, -- MedCLM: Learning to Localize and Reason via a CoT-Curriculum in Medica
        67087, -- From Behavioral Performance to Internal Competence: Interpreting Visio
        67678, -- Explaining multimodal LLMs via intra-modal token interactions
        67825, -- FerretNet: Efficient Synthetic Image Detection via Local Pixel Depende
        67831, -- Punching Above Precision: Small Quantized Model Distillation with Lear
        67897, -- PPGFlowECG: Latent Rectified Flow with Cross-Modal Encoding for PPG-Gu
        68037, -- DeepASA: An Object-Oriented One-for-All Network for Auditory Scene Ana
        68168, -- Pruning the Paradox: How CLIP's Most Informative Heads Enhance Perform
        68245, -- Multi-Modal Interpretability for Enhanced Localization in Vision-Langu
        68430, -- End-to-End Visual Autonomous Parking via Control-Aided Attention
        68484, -- Invisible Attributes, Visible Biases: Exploring Demographic Shortcuts
        68516, -- CoSwin: Convolution Enhanced Hierarchical Shifted Window Attention For
        68776, -- TinyDrop: Tiny Model Guided Token Dropping for Vision Transformers
        69013, -- RelP: Faithful and Efficient Circuit Discovery via Relevance Patching
        69014, -- GCAV: A Global Concept Activation Vector Framework for Cross-Layer Con
        69427, -- WeedSense: Multi-Task Learning for Weed Segmentation, Height Estimatio
        69437, -- Do VLMs Have Bad Eyes? Diagnosing Compositional Failures via Mechanist
        69530, -- Cross-Domain Few-Shot Learning via Multi-View Collaborative Optimizati
        69675, -- Reasoning in Computer Vision: Taxonomy, Models, Tasks, and Methodologi
        69824, -- Superclass-Guided Representation Disentanglement for Spurious Correlat
        69870, -- MIMIC: Multimodal Inversion for Model Interpretation and Conceptualiza
        70003, -- NEP: Autoregressive Image Editing via Next Editing Token Prediction
        70080, -- Assessing Representation Stability for Transformer Models
        70157, -- CORE-ReID V2: Advancing the Domain Adaptation for Object Re-Identifica
        70394, -- Unraveling Hidden Representations: A Multi-Modal Layer Analysis for Be
        70411, -- Weakly Supervised Virus Capsid Detection with Image-Level Annotations
        70430, -- Decouple before Align: Visual Disentanglement Enhances Prompt Tuning
        71107, -- Interpretable Prediction of Lymph Node Metastasis in Rectal Cancer MRI
        71304, -- Comprehensive Evaluation of Prototype Neural Networks
        71424, -- Habitat Classification from Ground-Level Imagery Using Deep Neural Net
        71436, -- FastDINOv2: Frequency Based Curriculum Learning Improves Robustness an
        71567, -- Context-Aware Academic Emotion Dataset and Benchmark
        71799, -- Training-free Test-time Improvement for Explainable Medical Image Clas
        72055, -- Rethinking Brain Tumor Segmentation from the Frequency Domain Perspect
        72132, -- HieraEdgeNet: A Multi-Scale Edge-Enhanced Framework for Automated Poll
        72253, -- HoliSafe: Holistic Safety Benchmarking and Modeling with Safety Meta T
        72307, -- A Data-Driven Diffusion-based Approach for Audio Deepfake Explanations
        72565, -- Bridging Distribution Shift and AI Safety: Conceptual and Methodologic
        72767, -- Spiking Neural Networks Need High Frequency Information
        72962, -- EPIC: Explanation of Pretrained Image Classification Networks via Prot
        73040, -- HyMamba: Mamba with Hybrid Geometry-Feature Coupling for Efficient Poi
        73270, -- SCOPE-MRI: Bankart Lesion Detection as a Case Study in Data Curation a
        73860, -- SChanger: Change Detection from a Semantic Change and Spatial Consiste
        73937, -- EasyRobust: A Comprehensive and Easy-to-use Toolkit for Robust and Gen
        74022, -- Interpretable 3D Neural Object Volumes for Robust Conceptual Reasoning
        74534, -- ELIP: Enhanced Visual-Language Foundation Models for Image Retrieval
        74553, -- MACPruning: Dynamic Operation Pruning to Mitigate Side-Channel DNN Mod
        74692, -- Image Embedding Sampling Method for Diverse Captioning
        74734, -- DiffEx: Explaining a Classifier with Diffusion Models to Identify Micr
        74758, -- Explaining 3D Computed Tomography Classifiers with Counterfactuals
        74877, -- Universal Sparse Autoencoders: Interpretable Cross-Model Concept Align
        75009, -- From Few to Many: Self-Improving Many-Shot Reasoners Through Iterative
        75128, -- LASER: Lip Landmark Assisted Speaker Detection for Robustness
        75152, -- Generative Physical AI in Vision: A Survey
        82931, -- Scaling Continual Learning to 300+ Tasks with Bi-Level Routing Mixture
        83542, -- Rethinking Visual Attribution for Chest X-ray Reasoning in Large Visio
        83942, -- DynaFLIP: Rethinking Robotics Perception via Tri-Modal-Dynamics Guided
        84066, -- Towards Generalizable AI-Generated Image Detection via Image-Adaptive
        84085, -- Towards Stealthy and Effective Backdoor Attacks on Lane Detection: A N
        84156, -- Decoupling Bias, Aligning Distributions: Synergistic Fairness Optimiza
        84170, -- Concept Regions Matter: Benchmarking CLIP with a New Cluster-Importanc
        84199, -- Investigating Self-Supervised Representations for Audio-Visual Deepfak
        84344, -- A Sanity Check for Multi-In-Domain Face Forgery Detection in the Real
        84469, -- Hidden Monotonicity: Explaining Deep Neural Networks via their DC Deco
        84512, -- Hierarchical Concept Embedding & Pursuit for Interpretable Image Class
        84522, -- MaskDiME: Adaptive Masked Diffusion for Precise and Efficient Visual C
        84528, -- Similarity-as-Evidence: Calibrating Overconfident VLMs for Interpretab
        84548, -- SegMoTE: Token-Level Mixture of Experts for Medical Image Segmentation
        84569, -- The Invisible Gorilla Effect in Out-of-distribution Detection
        84570, -- StructXLIP: Enhancing Vision-language Models with Multimodal Structura
        84708, -- Adaptive Confidence Regularization for Multimodal Failure Detection
        84715, -- CAPT: Confusion-Aware Prompt Tuning for Reducing Vision-Language Misal
        84735, -- DeepScan: A Training-Free Framework for Visually Grounded Reasoning in
        84793, -- A Unified Framework for Knowledge Transfer in Bidirectional Model Scal
        84878, -- Text-Phase Synergy Network with Dual Priors for Unsupervised Cross-Dom
        84885, -- Stake the Points: Structure-Faithful Instance Unlearning
        84909, -- Domain-Skewed Federated Learning with Feature Decoupling and Calibrati
        84919, -- GraspALL: Adaptive Structural Compensation from Illumination Variation
        84928, -- Attribution-Guided Model Rectification of Unreliable Neural Network Be
        84955, -- Interpretable Cross-Domain Few-Shot Learning with Rectified Target-Dom
        85096, -- Generative Adversarial Perturbations with Cross-paradigm Transferabili
        85099, -- Select, Hypothesize and Verify: Towards Verified Neuron Concept Interp
        85255, -- Learning from Synthetic Data via Provenance-Based Input Gradient Guida
        85275, -- Parameter-Efficient Semantic Augmentation for Enhancing Open-Vocabular
        85278, -- Saliency-R1: Enforcing Interpretable and Faithful Vision-language Reas
        85298, -- Submodel Extraction for Efficient and Personalized Federated Learning
        85445, -- H-Sets: Hessian-Guided Discovery of Set-Level Feature Interactions in
        85520, -- BAMI: Training-Free Bias Mitigation in GUI Grounding
        85797, -- CSBrain: A Cross-scale Spatiotemporal Brain Foundation Model for EEG D
        85858, -- Representational Difference Explanations
        85912, -- Mind the GAP! The challenges of scale in pixel-based deep reinforcemen
        86096, -- Enhancing Visual Prompting through Expanded Transformation Space and O
        86125, -- Attention (as Discrete-Time Markov) Chains
        86640, -- An Analysis of Concept Bottleneck Models: Measuring, Understanding, an
        86747, -- DEXTER: Diffusion-Guided EXplanations with TExtual Reasoning for Visio
        86925, -- Normalize Filters! Classical Wisdom for Deep Vision
        87394, -- PhysioWave: A Multi-Scale Wavelet-Transformer for Physiological Signal
        87428, -- MSTAR: Box-free Multi-query Scene Text Retrieval with Attention Recycl
        87464, -- Test-Time Adaptation by Causal Trimming
        87569, -- Exploiting Diffusion Prior for Task-driven Image Restoration
        87662, -- Local Dense Logit Relations for Enhanced Knowledge Distillation
        87673, -- Rethinking Key-frame-based Micro-expression Recognition: A Robust and
        87753, -- Backdooring Self-Supervised Contrastive Learning by Noisy Alignment
        87846, -- iManip: Skill-Incremental Learning for Robotic Manipulation
        87848, -- SIC: Similarity-Based Interpretable Image Classification with Neural N
        88006, -- AIM: Amending Inherent Interpretability via Self-Supervised Masking
        88007, -- I Am Big, You Are Little; I Am Right, You Are Wrong
        88101, -- Intervening in Black Box: Concept Bottleneck Model for Enhancing Human
        88148, -- IAP: Invisible Adversarial Patch Attack through Perceptibility-Aware L
        88197, -- Cracking Instance Jigsaw Puzzles: An Alternative to Multiple Instance
        88347, -- Adversarial Reconstruction Feedback for Robust Fine-grained Generaliza
        88414, -- WaveMamba: Wavelet-Driven Mamba Fusion for RGB-Infrared Object Detecti
        88483, -- Cross-modal Ship Re-Identification via Optical and SAR Imagery: A Nove
        88929, -- Pixel-level Certified Explanations via Randomized Smoothing
        88949, -- From Pixels to Perception: Interpretable Predictions via Instance-wise
        88966, -- Enhancing Performance of Explainable AI Models with Constrained Concep
        89068, -- Ranked Entropy Minimization for Continual Test-Time Adaptation
        89200, -- Unlocking the Capabilities of Large Vision-Language Models for General
        89466, -- Human-Aligned Image Models Improve Visual Decoding from the Brain
        89487, -- Identifying and Understanding Cross-Class Features in Adversarial Trai
        89628, -- DocVXQA: Context-Aware Visual Explanations for Document Question Answe
        89641, -- InfoCons: Identifying Interpretable Critical Concepts in Point Clouds
        89774, -- Concept-Centric Token Interpretation for Vector-Quantized Generative M
        89976, -- TIMING: Temporality-Aware Integrated Gradients for Time Series Explana
        90028, -- Feature Learning beyond the Lazy-Rich Dichotomy: Insights from Represe
        90085, -- Interpretable Image Classification via Non-parametric Part Prototype L
        90111, -- Data-free Universal Adversarial Perturbation with Pseudo-semantic Prio
        90203, -- One Model for ALL: Low-Level Task Interaction Is a Key to Task-Agnosti
        90220, -- Decoupled Distillation to Erase: A General Unlearning Method for Any C
        90310, -- On Denoising Walking Videos for Gait Recognition
        90484, -- ESC: Erasing Space Concept for Knowledge Deletion
        90485, -- Language Guided Concept Bottleneck Models for Interpretable Continual
        90492, -- Deep Change Monitoring: A Hyperbolic Representative Learning Framework
        90548, -- GeoMM: On Geodesic Perspective for Multi-modal Learning
        90803, -- CoE: Chain-of-Explanation via Automatic Visual Concept Circuit Descrip
        90810, -- Point-to-Region Loss for Semi-Supervised Point-Based Crowd Counting
        90933, -- DART: Disease-aware Image-Text Alignment and Self-correcting Re-alignm
        90952, -- Task-Agnostic Guided Feature Expansion for Class-Incremental Learning
        91007, -- Jailbreaking the Non-Transferable Barrier via Test-Time Data Disguisin
        91019, -- Do ImageNet-trained Models Learn Shortcuts? The Impact of Frequency Sh
        91283, -- Narrowing Information Bottleneck Theory for Multimodal Image-Text Repr
        91437, -- Representational Similarity via Interpretable Visual Concepts
        91686, -- HiBug2: Efficient and Interpretable Error Slice Discovery for Comprehe
        91992, -- QPM: Discrete Optimization for Globally Interpretable Image Classifica
        92281, -- MindSimulator: Exploring Brain Concept Localization via Synthetic fMRI
        92502, -- GRAIL: Gradient-Reweighted Advantages for Reinforcement Learning with
        92662, -- Exploring Interpretability for Visual Prompt Tuning with Cross-layer C
        92756, -- Causal Interpretation of Neural Network Computations with Contribution
        92814, -- TIMESLIVER : SYMBOLIC-LINEAR DECOMPOSITION FOR EXPLAINABLE TIME SERIES
        92879, -- Hessian-Enhanced Token Attribution (HETA): Interpreting Autoregressive
        92942, -- Learning Concept Bottleneck Models from Mechanistic Explanations
        93096, -- Dual-Kernel Adapter: Expanding Spatial Horizons for Data-Constrained M
        93161, -- Mitigating Spurious Correlation via Distributionally Robust Learning w
        93281, -- Beyond Classification Accuracy: Neural-MedBench and the Need for Deepe
        93444, -- Counterfactual Explanations on Robust Perceptual Geodesics
        93506, -- TrojanTO: Action-Level Backdoor Attacks Against Trajectory Optimizatio
        93674, -- Seeing but Not Believing: Probing the Disconnect Between Visual Attent
        93968, -- Policy Contrastive Decoding for Robotic Foundation Models
        94004, -- Quantifying Cross-Attention Interaction in Transformers for Interpreti
        94082, -- Learning Nonlinear Causal Reductions to Explain Reinforcement Learning
        94261, -- NIMO: a Nonlinear Interpretable MOdel
        94304, -- Modality Alignment across Trees on Heterogeneous Hyperbolic Manifolds
        94573, -- Visual Prompt-Agnostic Evolution
        94657, -- xRFM: Accurate, scalable, and interpretable feature learning models fo
        94694, -- From Concepts to Components: Concept-Agnostic Attention Module Discove
        94780, -- Reading Images Like Texts: Sequential Image Understanding in Vision-La
        94802, -- N?wa: Mending the Spatial Integrity Torn by VLM Token Pruning
        94807, -- Revisit Visual Prompt Tuning: The Expressiveness of Prompt Experts
        94838, -- Improving Black-Box Generative Attacks via Generator Semantic Consiste
        94990, -- LogicXGNN: Grounded Logical Rules for Explaining Graph Neural Networks
        95047, -- Spurious Correlation-Aware Embedding Regularization for Worst-Group Ro
        95783, -- CLUE: Crossmodal Disambiguation Via Language-Vision Understanding with
        96544, -- BFA: Best-Feature-Aware Fusion for Multi-View Fine-Grained Manipulatio
        96614, -- Unreal Robotics Lab: A High-Fidelity Robotics Simulator with Advanced
        98724, -- Global Feature Enhancing and Fusion Framework for Strain Gauge Time Se
        99084, -- Learning to Move Before Learning to Do: Task-Agnostic pretraining for
        99115, -- Envisioning Beyond the Few: Disentangled Semantics and Primitives for
        99288, -- Inside the Visual Mind: Neuroscience-Motivated Concept Circuits for In
        99373, -- Parameters as Experts: Adapting Vision Models with Dynamic Parameter R
        99405, -- Tackling Fake Forgetting through Uncertainty Quantification
        99491, -- SEPS: Semantic-Enhanced Patch Slimming Framework for Fine-Grained Cros
        99546, -- NeurIPS: Neuro-anatomical Inductive Priors for Sphere-based Brain Deco
        99571, -- Auditing Sybil: Explaining Deep Lung Cancer Risk Prediction Through Ge
        99682, -- Unlearning?s Blind Spots: Over?Unlearning and Prototypical Relearning
        99693, -- Target-Agnostic Calibration under Distribution Shift with Frequency-Aw
        99906, -- Understanding Private Learning From Feature Perspective
        100358, -- OOVDet: Low-Density Prior Learning for Zero-Shot Out-of-Vocabulary Obj
        100448, -- Hidden in Plain Sight -- Class Competition Focuses Attribution Maps
        100523, -- Learn from A Rationalist: Distilling Intermediate Interpretable Ration
        101276, -- Class-Conditional Distribution Balancing for Group Robust Classificati
        101310, -- Manifold-Aligned Guided Integrated Gradients for Reliable Feature Attr
        101352, -- Evidential Reasoning Advances Interpretable Real-World Disease Screeni
        101408, -- Privacy-Aware Video Anomaly Detection through Orthogonal Subspace Proj
        101803, -- Interpretable Self-Supervised Learning via Representer Landmarks and N
        101970, -- RECTOR: Masked Region-Channel-Temporal Modeling for Affective and Cogn
        102306, -- Med-SegLens: Latent-Level Model Diffing for Interpretable Medical Imag
        102334, -- L2G-NET: Local to Global Spectral Graph Neural Networks via Cauchy Fac
        102584, -- Do All Visual Tokens Matter Equally? Object-Evidence Preserving Token
        102791, -- Not All Directions Matter: Towards Structured and Task-Aware Low-Rank
        103197, -- MMAC: A Multilingual, Multimodal Alignment Framework for Cultural Grou
        103445, -- Quantifying and Understanding Uncertainty in Large Reasoning Models
        103497, -- User Perceptions vs. Proxy LLM Judges: Privacy and Helpfulness in LLM
        104092, -- SEZ-HARN: Self-Explainable Zero-shot Human Activity Recognition Networ
        104582, -- Context-Aware Concept Distillation for Trustworthy Flood Prediction
        104887, -- A Causality-Inspired Model for Intima-Media Thickening Assessment in U
        105057, -- CoPA: Hierarchical Concept Prompting and Aggregating Network for Expla
        105224, -- Fusing Radiomic Features with Deep Representations for Gestational Age
        105319, -- IP-CRR: Information Pursuit for Interpretable Classification of Chest
        105474, -- MvHo-IB: Multi-View Higher-Order Information Bottleneck for Brain Diso
        105543, -- PLUS: Plug-and-Play Enhanced Liver Lesion Diagnosis Model on Non-Contr
        105827, -- VMRA-MaR: An Asymmetry-Aware Temporal Framework for Longitudinal Breas
        106431, -- From Attribution to Action: Jointly ALIGNing Predictions and Explanati
        106605, -- Guess or Recall? Training CNNs to Classify and Localize Memorization i
        106710, -- Parameter-Free Fine-tuning via Redundancy Elimination for Vision Found
        107008, -- Hierarchical Prompt Learning for Image- and Text-Based Person Re-Ident
        107032, -- DOS: Distilling Observable Softmaps of Zipfian Prototypes for Self-Sup
        107084, -- Sampling Control for Imbalanced Calibration in Semi-Supervised Learnin
        107314, -- MaskAnyNet: Rethinking Masked Image Regions as Valuable Information in
        107451, -- Towards Test-time Efficient Visual Place Recognition via Asymmetric Qu
        107476, -- Synthetic Forgetting Without Access: A Few-Shot Zero-Glance Framework
        107535, -- Enhancing Interpretability for Vision Models via Shapley Value Optimiz
        107569, -- Concepts from Representations: Post-hoc Concept Bottleneck Models via
        107667, -- CHARM: Collaborative Harmonization Across Arbitrary Modalities for Mod
        108060, -- Debiased Dual-Invariant Defense for Adversarially Robust Person Re-Ide
        108143, -- Improving Sustainability of Adversarial Examples in Class-Incremental
        108190, -- SSR: Semantic and Spatial Rectification for CLIP-based Weakly Supervis
        108290, -- CLUENet: Cluster Attention Makes Neural Networks Have Eyes
        108359, -- SRD: Reinforcement-Learned Semantic Perturbation for Backdoor Defense
        108365, -- OTI: A Model-free and Visually Interpretable Measure of Image Attackab
        108370, -- Enhancing Chemical Explainability Through Counterfactual Masking
        108478, -- A Closer Look at Knowledge Distillation in Spiking Neural Network Trai
        108542, -- Rethinking Crystal Symmetry Prediction: A Decoupled Perspective
        108992, -- How to Evaluate and Refine your CAM
        109697, -- EXPL-FR: Explaining Face Recognition Models via Vision-Language Alignm
        110440, -- A Necessary Step toward Faithfulness: Measuring and Improving Consiste
        110634, -- Interpretation Meets Safety: A Survey on Interpretation Methods and To
        111381, -- Understanding Dementia Speech Alignment with Diffusion-Based Image Gen
        113690, -- On Spectral Properties of Gradient-based Explanation Methods
        114048, -- Harnessing CLIP and DINO: An Uncertainty-Aware Cascaded Fusion Network
        117803, -- Seeing What Matters: Lesion-Aware High-Resolution Patch Discovery and
        118144, -- Improving Adversarial Robustness via Activation Amplification and Atte
        118172, -- Residual-Guided Expert Specialization for Incomplete Multimodal Learni
        119063, -- Diagnosing Aerial-View Object Detectors with Foundational Image Genera
        119074, -- This Looks Distinctly Like That: Grounding Interpretable Recognition i
        119093, -- Weight-Space Mixture-of-Experts for Implicit Neural Representation Cla
        119153, -- Learn to Rank: Visual Attribution by Learning Importance Ranking
        119424, -- SENTRY: SAM2-Enhanced Neighbor-Aware and Temporally Reasoned Memory fo
        119490, -- HAS: Highlight-guided Attention Steering for Multimodal LLM Video Summ
        119496, -- MoVA: Learning Asymmetric Dual Projections for Modular Long Video-Text
        119540, -- Disentangling Hallucinations: Orthogonal Semantic Projection for Robus
        119583, -- Entropy-Gradient Grounding: Training-Free Evidence Retrieval in Vision
        119664, -- DEX-AR: A Dynamic Explainability Method for Autoregressive Vision-Lang
        119909, -- Comprehensive Information Bottleneck for Unveiling Universal Attributi
        120002, -- Towards Fine-Grained Interpretability: Counterfactual Explanations for
        120012, -- Let Samples Speak: Mitigating Spurious Correlation by Exploiting the C
        120279, -- Towards Human-Understandable Multi-Dimensional Concept Discovery
        120300, -- SASep: Saliency-Aware Structured Separation of Geometry and Feature fo
        120337, -- PatchGuard: Adversarially Robust Anomaly Detection and Localization th
        120606, -- Show and Tell: Visually Explainable Deep Neural Nets via Spatially-Awa
        120975, -- Progressive Cross-Modal Causal Intervention for Long-Term Action Recog
        121075, -- CREward: A Type-Specific Creativity Reward Model
        121435, -- SinGeo: Unlock Single Model's Potential for Robust Cross-View Geo-Loca
        122009, -- A Language-Guided Multimodal Foundation Model for Zero-Shot and Multi-
        122403, -- AnswerMap: Faithful Spatial Interpretability of VLMs from Answer Poste
        122759, -- MEA: A Reward-Driven Multi-Agent System for Faithful Model Explanation
        122820 -- ConEx: Human-Interpretable Saliency Maps via Concept-Aware Attribution
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'Grad-CAM curation 2026-10-15: cites the source paper without using Grad-CAM'
FROM grad_cam_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING grad_cam_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING grad_cam_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id
  AND pm.paper_id <> (SELECT source_paper_id FROM methods WHERE slug = 'grad-cam');
