-- Chat lookup-miss taxonomy gap fill (2026-11-23 chat health audit): four
-- methods that production chat looked up with pwc_get_method and did not find.
--
-- HOG, Viola-Jones and inverse perspective mapping predate arXiv, so
-- source_paper_id stays NULL, source_url points to the introducing paper's DOI
-- and no "Introduced" banner is added. SWAD has an arXiv source paper.
--
-- Keywords tag papers through the daily keyword backfill, so they are long-form
-- names only. The bare acronyms HOG and IPM collide with other senses
-- (HOG-Diff, History of Gradients, integral probability metric, interior-point
-- method) and live only in full_name, where pwc_get_method resolves a unique
-- trailing acronym and the Jev judge decides each abstract mention. "Haar
-- cascade" is an alias of Viola-Jones because the OpenCV Haar cascade
-- classifier is that detector.
--
-- Paper links were curated by hand from every local title/abstract candidate
-- (long forms plus the bare acronyms); true positives get 'manual' evidence and
-- reviewed negatives become durable exclusions. Hero images were imported
-- separately with import_entity_image.py; this file records their credits.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES
(
    'hog',
    'Histogram of Oriented Gradients',
    'Histogram of Oriented Gradients (HOG)',
    'The histogram of oriented gradients (HOG) is a hand-crafted image descriptor that represents local shape by the distribution of edge directions. The image is divided into small cells (for example 8×8 pixels); each cell accumulates a histogram of gradient orientations weighted by gradient magnitude, and histograms are contrast-normalized over overlapping blocks of cells, which makes the descriptor robust to illumination changes and small deformations. Dalal and Triggs introduced it in 2005 for pedestrian detection, pairing a sliding-window HOG descriptor with a linear SVM, and it became the standard feature for detection before CNNs, including in deformable part models and the dlib face detector. HOG is still used as a lightweight feature for classical pipelines and as a reconstruction target in masked image modeling, as in [Masked Feature Prediction](/paper/2112.09133).',
    'histogram of oriented gradients, histograms of oriented gradients, histogram of oriented gradient, HOG descriptor, HOG feature',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2005,
    NULL,
    'https://doi.org/10.1109/CVPR.2005.177',
    'Histograms of Oriented Gradients for Human Detection',
    'https://scikit-image.org/docs/stable/api/skimage.feature.html#skimage.feature.hog',
    NULL,
    'judge',
    ARRAY['Histograms of Oriented Gradients']
),
(
    'viola-jones',
    'Viola-Jones',
    'Viola-Jones Object Detection Framework',
    'The Viola-Jones framework is the first real-time face detector, introduced by Paul Viola and Michael Jones in 2001. It combines three ideas. Haar-like features, differences of pixel sums over adjacent rectangles, are computed in constant time from an integral image. AdaBoost selects a small set of discriminative features from hundreds of thousands of candidates and builds strong classifiers from them. These classifiers are chained into an attentional cascade in which early, cheap stages reject most background windows, so later, more complex stages run on few windows. The OpenCV "Haar cascade" classifiers implement this detector, and it remained the default face detector in cameras and vision libraries until [HOG](/methods/hog) and CNN-based detectors replaced it.',
    'Viola-Jones, Viola–Jones, Viola Jones, Haar cascade, Haar-like feature',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2001,
    NULL,
    'https://doi.org/10.1109/CVPR.2001.990517',
    'Rapid Object Detection using a Boosted Cascade of Simple Features',
    'https://docs.opencv.org/4.x/db/d28/tutorial_cascade_classifier.html',
    NULL,
    'always',
    ARRAY['Viola–Jones', 'Haar Cascade', 'Haar Cascade Classifier']
),
(
    'inverse-perspective-mapping',
    'Inverse Perspective Mapping',
    'Inverse Perspective Mapping (IPM)',
    'Inverse perspective mapping (IPM) warps a perspective camera image onto a top-down view of the ground plane, removing the perspective effect so that parallel road markings appear parallel and distances are metric. It assumes a flat ground and a known camera height, pitch and intrinsics, and applies the homography between the image plane and the ground plane. Mallot et al. introduced it in 1991 for obstacle detection from optical flow, and it became standard in lane detection and road scene understanding, for example in the GOLD system. In bird''s-eye-view perception for autonomous driving, IPM is the simplest way to lift camera features into BEV space, used by 3D [lane detection](/tasks/lane-detection) models; its flat-ground assumption distorts objects above the road and slopes, which learned view transforms such as LSS and BEVFormer address.',
    'inverse perspective mapping, inverse perspective transform, inverse perspective transformation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    1991,
    NULL,
    'https://doi.org/10.1007/BF00201978',
    'Inverse perspective mapping simplifies optical flow computation and obstacle detection',
    NULL,
    NULL,
    'judge',
    ARRAY[]::text[]
),
(
    'swad',
    'SWAD',
    'Stochastic Weight Averaging Densely (SWAD)',
    'SWAD is a domain generalization method that finds flatter minima by averaging model weights densely along the training trajectory. The authors show that the gap between source and unseen target domain loss is bounded by the flatness of the loss surface, and that stochastic weight averaging (SWA), which averages a few checkpoints at the end of each cycle, is not enough. SWAD instead averages the weights after every iteration within a window chosen from validation loss, starting once validation loss stops decreasing and stopping when it starts to overfit, and uses a constant learning rate without cycles. With plain empirical risk minimization it improved average accuracy on DomainBed (PACS, VLCS, OfficeHome, TerraIncognita and DomainNet) by about 1.6 points, and it can be combined with other domain generalization methods. Weight-averaging methods such as SMA and model soups build on it.',
    'SWAD, stochastic weight averaging densely',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2102.08604'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'SWAD: Domain Generalization by Seeking Flat Minima',
    'https://github.com/khanrc/swad',
    NULL,
    'always',
    ARRAY[]::text[]
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

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'swad' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'swad' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE gap_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p JOIN methods m ON (
    (m.slug = 'hog' AND (
        p.arxiv_id IN (
            '1412.0035', -- Understanding Deep Image Representations by Inverting Them
            '1506.02753', -- Inverting Visual Representations with Convolutional Networks
            '2112.09133', -- Masked Feature Prediction for Self-Supervised Visual Pre-Training
            '2201.10102', -- A Classical Approach to Handcrafted Feature Extraction Techniques for Bangla
            '2310.18653', -- Feature Guided Masked Autoencoder for Self-supervised Learning in Remote Sensing
            '2312.12480', -- Continual-MAE: Adaptive Distribution Masked Autoencoders for Continual Test-Time
            '2504.09377', -- Beyond Degradation Conditions: All-in-One Image Restoration via HOG Transformers
            '2507.19138', -- RealisVSR: Detail-enhanced Diffusion for Real-World 4K Video Super-Resolution
            '2508.12132' -- TriQDef: Disrupting Semantic and Gradient Alignment to Prevent Adversarial Patch
        )
        OR (p.source = 'external' AND p.id IN (
            105492 -- Non-Salient Object Segmentation in Medical Images via Pre-trained Multi-Granular
        ))
    ))
    OR (m.slug = 'viola-jones' AND p.source = 'external' AND p.id IN (
        104703 -- Feature-based head pose estimation from images
    ))
    OR (m.slug = 'inverse-perspective-mapping' AND p.arxiv_id IN (
        '2301.02371', -- Anchor3DLane: Learning to Regress 3D Anchors for Monocular 3D Lane Detection
        '2504.18325' -- Depth3DLane: Monocular 3D Lane Detection via Depth Prior Distillation
    ))
    OR (m.slug = 'swad' AND p.arxiv_id IN (
        '2309.11446' -- Weight Averaging Improves Knowledge Distillation under Domain Shift
    ))
)
WHERE p.is_latest_version;

DELETE FROM paper_method_exclusions x
USING gap_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gap_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM gap_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE gap_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p JOIN methods m ON (
    (m.slug = 'hog' AND (
        p.arxiv_id IN (
            '1708.04370', -- Dockerface: an Easy to Install and Use Faster R-CNN Face Detector
            '2208.10273', -- Long-Short History of Gradients is All You Need
            '2304.06194', -- SiLK -- Simple Learned Keypoints
            '2502.04308', -- HOG-Diff: Higher-Order Guided Diffusion for Graph Generation
            '2509.13801', -- Masked Feature Modeling Enhances Adaptive Segmentation
            '2604.10772' -- HOG-Layout: Hierarchical 3D Scene Generation, Optimization and Editing
        )
        OR (p.source = 'external' AND p.id IN (
            114997 -- HoG-Net: Hierarchical Multi-Organ Graph Network for Head and Neck Cancer
        ))
    ))
    OR (m.slug = 'viola-jones' AND p.arxiv_id IN (
        '1708.04370', -- Dockerface: an Easy to Install and Use Faster R-CNN Face Detector
        '2502.02004' -- Wavelet-based Positional Representation for Long Context
    ))
    OR (m.slug = 'inverse-perspective-mapping' AND (
        p.arxiv_id IN (
            '0903.3246', -- Lectures on holographic methods for condensed matter physics
            '2301.13362', -- Optimizing DDPM Sampling with Shortcut Fine-Tuning
            '2305.13715', -- Covariate balancing using the integral probability metric
            '2502.00737', -- Scalable Sobolev IPM for Probability Measures on a Graph
            '2505.01353', -- Differentiable Nonlinear Model Predictive Control
            '2505.16156', -- Integral Imprecise Probability Metrics
            '2605.13684' -- Scale-Sensitive Shattering: Learnability and Evaluability at Optimal Scale
        )
        OR (p.source = 'external' AND p.id IN (
            112589, -- Multi-Person Pose Forecasting with Individual Interaction Perceptron
            128195, -- Orlicz-Sobolev with Musielak: An Efficient Regularization Approach
            128396, -- Integral Probability Boundaries
            128767 -- Tree-Sliced Orlicz Integral Probability Metric
        ))
    ))
)
WHERE p.is_latest_version;

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'taxonomy gap fill 2026-11-23: passing mention or another sense of the acronym (HoG, IPM, Haar wavelet)'
FROM gap_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING gap_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING gap_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- swad: Semantic Scholar lists 131 more local citers of the source paper. None
-- names SWAD in its title or abstract, so all are reviewed negatives; the
-- hourly reference backfill would otherwise link them.
CREATE TEMP TABLE swad_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'swad'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2205.09739', -- Diverse Weight Averaging for Out-of-Distribution Generalization
          '2210.13533', -- Sufficient Invariant Learning for Distribution Shift
          '2211.13723', -- Improving Multi-task Learning via Seeking Task-based Flat Regions
          '2211.14058', -- Cross-Domain Ensemble Distillation for Domain Generalization
          '2306.03241', -- Early Weight Averaging meets High Learning Rates for LLM Pre-training
          '2307.11108', -- Flatness-Aware Minimization for Domain Generalization
          '2401.12187', -- WARM: On the Benefits of Weight Averaged Reward Models
          '2402.18817', -- Gradient Alignment for Cross-Domain Face Anti-Spoofing
          '2403.00946', -- Fine-tuning with Very Large Dropout
          '2403.06392', -- Towards Robust Out-of-Distribution Generalization Bounds via Sharpness
          '2403.19522', -- Model Stock: All we need is just a few fine-tuned models
          '2406.16768', -- WARP: On the Benefits of Weight Averaged Rewarded Policies
          '2410.16476', -- In Search of the Successful Interpolation: On the Role of Sharpness in CLIP
          '2412.05551', -- GAQAT: gradient-adaptive quantization-aware training for domain generalizat
          '2412.13573', -- Seeking Consistent Flat Minima for Better Domain Generalization via Refinin
          '2501.18864', -- Flatness Guided Test-Time Adaptation for Vision-Language Models
          '2502.06761', -- When, Where and Why to Average Weights?
          '2502.07274', -- Forget Forgetting: Continual Learning in a World of Abundant Memory
          '2503.11078', -- Understanding Flatness in Generative Models: Its Role and Benefits
          '2505.24592', -- A Flat Minima Perspective on Understanding Augmentations and Model Robustne
          '2510.14231', -- When Flatness Does (Not) Guarantee Adversarial Robustness
          '2511.20258', -- Modality-Balanced Collaborative Distillation for Multi-Modal Domain General
          '2203.01522', -- BatchFormer: Learning to Explore Sample Relationships for Robust Representa
          '2204.08040', -- NICO++: Towards Better Benchmarking for Domain Generalization
          '2206.04046', -- Sparse Mixture-of-Experts are Domain Generalizable Learners
          '2206.08213', -- A Closer Look at Smoothness in Domain Adversarial Training
          '2212.00979', -- PASTA: Proportional Amplitude Spectrum Training Augmentation for Syn-to-Rea
          '2212.09849', -- Dataless Knowledge Fusion by Merging Weights of Language Models
          '2212.10445', -- Model Ratatouille: Recycling Diverse Models for Out-of-Distribution General
          '2302.00487', -- A Comprehensive Survey of Continual Learning: Theory, Method and Applicatio
          '2302.00864', -- CLIPood: Generalizing CLIP to Out-of-Distributions
          '2302.02350', -- Aggregation of Disentanglement: Reconsidering Domain Variations in Domain G
          '2302.07011', -- A Modern Look at the Relationship between Sharpness and Generalization
          '2303.07123', -- Modality-Agnostic Debiasing for Single Domain Generalization
          '2304.01434', -- VNE: An Effective Method for Improving Deep Representation by Manipulating
          '2304.11263', -- Benchmarking Low-Shot Robustness to Natural Distribution Shifts
          '2305.13046', -- POEM: Polarization of Embeddings for Domain-Invariant Representations
          '2305.15253', -- Rethinking the Evaluation Protocol of Domain Generalization
          '2305.18171', -- Improved Probabilistic Image-Text Representations
          '2306.01708', -- TIES-Merging: Resolving Interference When Merging Models
          '2306.02595', -- Explore and Exploit the Diverse Knowledge in Model Zoo for Domain Generaliz
          '2306.02879', -- Neuron Activation Coverage: Rethinking Out-of-distribution Detection and Ge
          '2306.04911', -- Test-Time Style Shifting: Handling Arbitrary Styles in Domain Generalizatio
          '2306.07052', -- Gradient Ascent Post-training Enhances Language Model Generalization
          '2306.14306', -- Adaptive Sharpness-Aware Pruning for Robust Sparse Networks
          '2307.12502', -- Cross Contrasting Feature Perturbation for Domain Generalization
          '2307.14709', -- Taxonomy Adaptive Cross-Domain Adaptation in Medical Imaging via Optimizati
          '2307.15199', -- PromptStyler: Prompt-driven Style Generation for Source-free Domain General
          '2308.03448', -- Make Explicit Calibration Implicit: Calibrate Denoiser Instead of the Noise
          '2308.09391', -- Generalizable Decision Boundaries: Dualistic Meta-Learning for Open Set Dom
          '2308.09718', -- Towards Large-scale 3D Representation Learning with Multi-dataset Point Pro
          '2308.10285', -- DomainDrop: Suppressing Domain-Sensitive Channels for Domain Generalization
          '2308.10297', -- DomainAdaptor: A Novel Approach to Test-time Adaptation
          '2309.06256', -- Mitigating the Alignment Tax of RLHF
          '2309.13258', -- Order-preserving Consistency Regularization for Domain Adaptation and Gener
          '2309.17230', -- Spurious Feature Diversification Improves Out-of-distribution Generalizatio
          '2310.00488', -- Membership Privacy Risks of Sharpness Aware Minimization
          '2310.02575', -- AdaMerging: Adaptive Model Merging for Multi-Task Learning
          '2310.05055', -- FairTune: Optimizing Parameter Efficient Fine Tuning for Fairness in Medica
          '2310.08255', -- Leveraging Vision-Language Models for Improving Domain Generalization in Im
          '2312.09390', -- Weak-to-Strong Generalization: Eliciting Strong Capabilities With Weak Supe
          '2401.10491', -- Knowledge Fusion of Large Language Models
          '2401.14846', -- Understanding Domain Generalization: A Noise Robustness Perspective
          '2402.02705', -- Representation Surgery for Multi-Task Model Merging
          '2402.07785', -- HYPO: Hyperspherical Out-of-Distribution Generalization
          '2402.10373', -- BioMistral: A Collection of Open-Source Pretrained Large Language Models fo
          '2402.18853', -- Rethinking Multi-domain Generalization with A General Learning Objective
          '2403.05523', -- Beyond Finite Data: Towards Data-free Out-of-distribution Generalization vi
          '2403.11674', -- Towards Generalizing to Unseen Domains with Few Labels
          '2404.00710', -- Unknown Prompt, the only Lacuna: Unveiling CLIPs Potential for Open Domain
          '2404.09011', -- PracticalDG: Perturbation Distillation on Vision-Language Models for Hybrid
          '2404.17768', -- Changing the Training Data Distribution to Reduce Simplicity Bias Improves
          '2404.19286', -- Soft Prompt Generation for Domain Generalization
          '2405.15961', -- Grounding Stylistic Domain Generalization with Quantitative Domain Shift Me
          '2405.16397', -- AdaFisher: Adaptive Second Order Optimization via Fisher Information
          '2406.11385', -- MetaGPT: Merging Large Language Models Using Model Exclusive Task Arithmeti
          '2407.02403', -- Face Reconstruction Transfer Attack as Out-of-Distribution Generalization
          '2407.08822', -- FedMedICL: Towards Holistic Evaluation of Distribution Shifts in Federated
          '2407.15085', -- Learn to Preserve and Diversify: Parameter-Efficient Group with Orthogonal
          '2407.18821', -- Deep Companion Learning: Enhancing Generalization Through Historical Consis
          '2408.05749', -- Efficient and Versatile Robust Fine-Tuning of Zero-shot Models
          '2408.07666', -- Model Merging in LLMs, MLLMs, and Beyond: Methods, Theories, Applications a
          '2410.04196', -- Improving Generalization with Flat Hilbert Bayesian Inference
          '2410.06020', -- QT-DoG: Quantization-aware Training for Domain Generalization
          '2411.19757', -- Dual Risk Minimization: Towards Next-Level Robustness in Fine-tuning Zero-S
          '2412.02856', -- Is Large-scale Pretraining the Secret to Good Domain Generalization?
          '2502.00089', -- Ensembles of Low-Rank Expert Adapters
          '2502.00264', -- Beyond the Permutation Symmetry of Transformers: The Role of Rotation for M
          '2502.10691', -- Controlling Neural Collapse Enhances Out-of-Distribution Detection and Tran
          '2502.10743', -- 1bit-Merging: Dynamic Quantized Merging for Large Language Models
          '2502.10749', -- LoRE-Merging: Exploring Low-Rank Estimation For Large Language Model Mergin
          '2502.20162', -- Gradient-Guided Annealing for Domain Generalization
          '2503.05204', -- Data-Efficient Generalization for Zero-shot Composed Image Retrieval
          '2503.06698', -- Whats in a Latent? Leveraging Diffusion Latent Space for Domain Generaliza
          '2503.13915', -- Unlocking the Potential of Unlabeled Data in Semi-Supervised Domain General
          '2503.14897', -- When Domain Generalization meets Generalized Category Discovery: An Adaptiv
          '2503.18987', -- Balanced Direction from Multifarious Choices: Arithmetic Meta-Learning for
          '2504.02666', -- BECAME: Bayesian Continual Learning with Adaptive Model Merging
          '2504.02996', -- Noise-Aware Generalization: Robustness to In-Domain Noise and Out-of-Domain
          '2505.04877', -- Learning from Loss Landscape: Generalizable Mixed-Precision Quantization vi
          '2505.06977', -- CAT Merging: A Training-Free Approach for Resolving Conflicts in Model Merg
          '2505.21574', -- Do We Need All the Synthetic Data? Towards Targeted Synthetic Image   Augme
          '2505.22389', -- Train with Perturbation, Infer after Merging: A Two-Stage Framework for Con
          '2505.23117', -- Decom-Renorm-Merge: Model Merging on the Right Space Improves   Multitaskin
          '2505.23209', -- Navigating the Accuracy-Size Trade-Off with Flexible Model Merging
          '2506.00288', -- Emergent Abilities of Large Language Models under Continued Pretraining   f
          '2506.07247', -- Promoting Ensemble Diversity with Interactive Bayesian Distributional Robus
          '2506.09093', -- Merging Smarter, Generalizing Better: Enhancing Model Merging on OOD Data
          '2507.05221', -- CTA: Cross-Task Alignment for Better Test Time Training
          '2507.07883', -- SAMO: A Lightweight Sharpness-Aware Approach for Multi-Task Optimization wi
          '2508.16973', -- Balanced Sharpness-Aware Minimization for Imbalanced Regression
          '2509.01548', -- Model Unmerging: Making Your Models Unmergeable for Secure Model Sharing
          '2509.15791', -- Minimal Semantic Sufficiency Meets Unsupervised Domain Generalization
          '2509.22335', -- Spectral Collapse Drives Loss of Plasticity in Deep Continual Learning
          '2509.22813', -- TRUST: Test-Time Refinement using Uncertainty-Guided SSM Traverses
          '2510.12266', -- HiLoRA: Adaptive Hierarchical LoRA Routing for Training-Free Domain General
          '2510.13865', -- Deep Edge Filter: Return of the Human-Crafted Layer in Deep Learning
          '2511.00066', -- Sharpness-Guided Group Relative Policy Optimization via Probability Shaping
          '2511.17918', -- Frequency-Adaptive Sharpness Regularization for Improving 3D Gaussian Splat
          '2512.02421', -- Generalizing Vision-Language Models with Dedicated Prompt Guidance
          '2512.18722', -- Generating Risky Samples with Conformity Constraints via Diffusion Models
          '2602.02015', -- Robust Domain Generalization under Divergent Marginal and Conditional Distr
          '2602.04937', -- Linear Model Merging Unlocks Simple and Scalable Multimodal Data Mixture Op
          '2602.08813', -- Robust Policy Optimization to Prevent Catastrophic Forgetting
          '2602.23777', -- Reasoning-Driven Multimodal LLM for Domain Generalization
          '2605.05136', -- CPCANet: Deep Unfolding Common Principal Component Analysis for Domain Gene
          '2605.27975', -- Continual Learning in Modern Hopfield Networks with an Application to Diffu
          '2606.28142', -- MixTTA: Low-Rank Cross-Channel Mixing for Reliable Test-Time Adaptation
          '2607.01657', -- Domain Generalization via Text-Anchored Information Bottleneck
          '2607.22117', -- Projection Pursuit CPCANet for Domain Generalization
          '2610.00968' -- Structure-agnostic Causal Representation Learning
      )
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'taxonomy gap fill 2026-11-23: cites the SWAD paper without naming SWAD in title or abstract'
FROM swad_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING swad_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING swad_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
