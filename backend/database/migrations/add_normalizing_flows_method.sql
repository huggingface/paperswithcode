-- Add Normalizing Flows method.
-- Normalizing flows have no single introducing paper: Tabak & Vanden-Eijnden
-- used flows for density estimation before Dinh et al. (NICE, arXiv 1410.8516)
-- introduced coupling layers and Rezende & Mohamed (arXiv 1505.05770) named
-- normalizing flows for variational inference. The source is therefore the
-- JMLR survey by Papamakarios et al., and source_paper_id stays NULL, which
-- keeps the hourly reference backfill from linking every citer of either paper.
--
-- Keywords deliberately omit "flow-based generative model": since 2023 the
-- phrase mostly describes flow matching and rectified flow models.

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
    'normalizing-flows',
    'Normalizing Flows',
    'Normalizing Flows',
    'Normalizing flows are generative models that transform a simple base distribution, usually a standard Gaussian, into a complex one through a sequence of invertible, differentiable mappings. Because every mapping is invertible with a tractable Jacobian determinant, the change-of-variables formula gives the exact log-likelihood of the data, so flows can be trained by maximum likelihood and support both exact density evaluation and sampling. The idea grew out of earlier density estimation work by Tabak and Vanden-Eijnden; in deep learning, [NICE](/paper/1410.8516) introduced additive coupling layers for density estimation, and [Rezende & Mohamed](/paper/1505.05770) named normalizing flows and used them to enrich variational posteriors. Later designs include affine coupling in [Real NVP](/paper/1605.08803), invertible 1x1 convolutions in [Glow](/paper/1807.03039), autoregressive flows such as MAF and IAF, spline flows, residual flows, and continuous normalizing flows defined by [neural ODEs](/methods/neural-ode). Flows are used for image, audio and speech generation (WaveGlow, Glow-TTS, VITS), variational inference, anomaly detection, simulation-based inference and Boltzmann generators, and [flow matching](/methods/flow-matching) emerged as a simulation-free way to train continuous flows.',
    'normalizing flow, normalising flow',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://jmlr.org/papers/v22/19-1028.html',
    'Normalizing Flows for Probabilistic Modeling and Inference',
    'https://github.com/bayesiains/nflows',
    NULL,
    '[Variational Inference with Normalizing Flows](/paper/1505.05770)'
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

-- Curated 2026-10-15 from every title/abstract mention of normalizing (or
-- normalising) flows, flow-based generative models and invertible neural
-- networks, plus the seminal NICE, Rezende & Mohamed and Real NVP papers. Each
-- paper below proposes, trains, analyzes or builds on a normalizing flow
-- (including continuous normalizing flows studied as flows).
CREATE TEMP TABLE normalizing_flows_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'normalizing-flows'
  AND p.id IN (
        188, -- Variational Inference with Normalizing Flows
        383, -- Density estimation using Real NVP
        1346, -- Neural Ordinary Differential Equations
        1382, -- Glow: Generative Flow with Invertible 1x1 Convolutions
        1583, -- WaveGlow: A Flow-based Generative Network for Speech Synthesis
        1802, -- Flow++: Improving Flow-Based Generative Models with Variational Dequan
        2103, -- MoGlow: Probabilistic and controllable motion synthesis using normalis
        2220, -- Residual Flows for Invertible Generative Modeling
        2238, -- Neural Spline Flows
        3106, -- Stochastic Normalizing Flows
        3566, -- Flowtron: an Autoregressive Flow-based Generative Network for Text-to-
        3609, -- Glow-TTS: A Generative Flow for Text-to-Speech via Monotonic Alignment
        3694, -- NanoFlow: Scalable Normalizing Flows with Sublinear Parameter Complexi
        5017, -- Argmax Flows and Multinomial Diffusion: Learning Categorical Distribut
        5161, -- Deep Generative Modelling: A Comparative Review of VAEs, GANs, Normali
        5913, -- Neural Hybrid Automata: Learning Dynamics with Multiple Modes and Stoc
        5954, -- Fair Normalizing Flows
        6125, -- Transflower: probabilistic autoregressive dance generation with multim
        6174, -- CInC Flow: Characterizable Invertible 3x3 Convolution
        6760, -- PortaSpeech: Portable and High-Quality Generative Text-to-Speech
        6767, -- Smooth Normalizing Flows
        7309, -- Group equivariant neural posterior estimation
        7368, -- RegNeRF: Regularizing Neural Radiance Fields for View Synthesis from S
        7391, -- HMC with Normalizing Flows
        8132, -- Generative Modeling for Low Dimensional Speech Attributes with Neural
        9030, -- MixFlows: principled variational inference via mixed flows
        9554, -- Marginal Tail-Adaptive Normalizing Flows
        9619, -- Supernova Light Curves Approximation based on Neural Network Models
        9887, -- Enhancing Image Rescaling using Dual Latent Variables in Invertible Ne
        10276, -- Normalizing Flows for Interventional Density Estimation
        10301, -- Understanding of the properties of neural network approaches for trans
        10463, -- Training Normalizing Flows from Dependent Data
        10924, -- Multi-hypothesis 3D human pose estimation metrics favor miscalibrated
        11321, -- OverFlow: Putting flows on top of neural transducers for better TTS
        11456, -- Normalizing Flows for Human Pose Anomaly Detection
        11868, -- On the Robustness of Normalizing Flows for Inverse Problems in Imaging
        12479, -- FInC Flow: Fast and Invertible $k \times k$ Convolutions for Normalizi
        12564, -- Rigid Body Flows for Sampling Molecular Crystal Structures
        12778, -- Timewarp: Transferable Acceleration of Molecular Dynamics by Learning
        12988, -- On Sampling with Approximate Transport Maps
        13049, -- Variational Mixture of HyperGenerators for Learning Distributions Over
        13197, -- Weakly Supervised Label Learning Flows
        15073, -- A Coupled Flow Approach to Imitation Learning
        16227, -- Training Energy-Based Normalizing Flow with Score-Matching Objectives
        16582, -- One-Line-of-Code Data Mollification Improves Optimization of Likelihoo
        16863, -- A Conditional Normalizing Flow for Accelerated Multi-Coil MR Imaging
        16891, -- Lifting Architectural Constraints of Injective Flows
        17588, -- 3D VR Sketch Guided 3D Shape Prototyping and Exploration
        18559, -- ProtoFL: Unsupervised Federated Learning via Prototypical Distillation
        18696, -- Kernelised Normalising Flows
        19350, -- Fast Inference and Update of Probabilistic Density Estimation on Traje
        19634, -- TrackFlow: Multi-Object Tracking with Normalizing Flows
        20540, -- Simulation-based Inference for Exoplanet Atmospheric Retrieval: Insigh
        21152, -- On the Stability of Iterative Retraining of Generative Models on their
        21291, -- CausalTime: Realistically Generated Time-series for Benchmarking of Ca
        23823, -- A Neural Framework for Generalized Causal Sensitivity Analysis
        24707, -- GMTalker: Gaussian Mixture-based Audio-Driven Emotional Talking Video
        29374, -- Fast and Unified Path Gradient Estimators for Normalizing Flows
        30164, -- VoiceShop: A Unified Speech-to-Speech Framework for Identity-Preservin
        31522, -- Maximum Entropy Reinforcement Learning via Energy-Based Normalizing Fl
        34126, -- FlowCon: Out-of-Distribution Detection using Flow-Based Contrastive Le
        34163, -- Learning Non-Linear Invariants for Unsupervised Out-of-Distribution De
        34652, -- Flow Perturbation to Accelerate Unbiased Sampling of Boltzmann distrib
        35470, -- Adaptive Two-Stage Cloud Resource Scaling via Hierarchical Multi-Indic
        35754, -- Open-Source Molecular Processing Pipeline for Generating Molecules
        37525, -- Knowledge Graph Embedding by Normalizing Flows
        38694, -- DurIAN-E 2: Duration Informed Attention Network with Adaptive Variatio
        38818, -- Parallel Backpropagation for Inverse of a Convolution with Application
        40708, -- JetFormer: An Autoregressive Generative Model of Raw Images and Text
        41224, -- Normalizing Flows are Capable Generative Models
        41916, -- Jet: A Modern Transformer-Based Normalizing Flow
        42231, -- Diverse Rare Sample Generation with Pretrained GANs
        45024, -- Scalable Equilibrium Sampling with Sequential Boltzmann Generators
        49004, -- Accelerate TarFlow Sampling with GS-Jacobi Iteration
        50717, -- STARFlow: Scaling Latent Normalizing Flows for High-resolution Image S
        53838, -- FARMER: Flow AutoRegressive Transformer over Pixels
        54334, -- MIST: Mutual Information Via Supervised Training
        54362, -- STARFlow-V: End-to-End Video Generative Modeling with Normalizing Flow
        54545, -- Flowing Backwards: Improving Normalizing Flows via Reverse Representat
        54644, -- One Layer Is Enough: Adapting Pretrained Visual Encoders for Image Gen
        54895, -- Bidirectional Normalizing Flow: From Data to Noise and Back
        61543, -- PolicyFlow: Policy Optimization with Continuous Normalizing Flow in Re
        62411, -- AllShowers: One model for all calorimeter showers
        64150, -- SimFlow: Simplified and End-to-End Training of Latent Normalizing Flow
        68298, -- GWKokab: An Implementation to Identify the Properties of Multiple Popu
        69197, -- Amortized Sampling with Transferable Normalizing Flows
        70765, -- Deep Variational Free Energy Calculation of Hydrogen Hugoniot
        72956, -- CacheFlow: Fast Human Motion Prediction by Cached Normalizing Flow
        73501, -- Transforming Simulation to Data Without Pairing
        73698, -- Accelerated Bayesian Inference for Pulsar Timing Arrays: Normalizing F
        77433, -- Normalizing flows as an enhanced sampling method for atomistic superco
        79284, -- PyramidFlow: High-Resolution Defect Contrastive Localization using Pyr
        80023, -- COMET Flows: Towards Generative Modeling of Multivariate Extremes and
        80058, -- Universal approximation property of invertible neural networks
        80127, -- TO-FLOW: Efficient Continuous Normalizing Flows with Temporal Optimiza
        80147, -- FLAG: Flow-based 3D Avatar Generation from Sparse Observations
        80392, -- FastFlow: Unsupervised Anomaly Detection and Localization via 2D Norma
        80589, -- Temperature Steerable Flows and Boltzmann Generators
        80594, -- Individual Survival Curves with Conditional Normalizing Flows
        80677, -- Conditional Variational Autoencoder with Adversarial Learning for End-
        81021, -- Neural Spatio-Temporal Point Processes
        81251, -- Coupling-based Invertible Neural Networks Are Universal Diffeomorphism
        81588, -- Intensity-Free Learning of Temporal Point Processes
        81882, -- FloWaveNet : A Generative Flow for Raw Audio
        82924, -- STARFlow2: Bridging Language Models and Normalizing Flows for Unified
        82925, -- Normalizing Trajectory Models
        84851, -- RC-NF: Robot-Conditioned Normalizing Flow for Real-Time Anomaly Detect
        84940, -- BUSSARD: Normalizing Flows for Bijective Universal Scene-Specific Anom
        85573, -- UST-Hand: An Uncertainty-aware Spatiotemporal Point Cloud Interaction
        85811, -- Amortized Variational Transdimensional Inference
        85891, -- Multivariate Latent Recalibration for Conditional Normalizing Flows
        85997, -- Partial Information Decomposition via Normalizing Flows in Latent Gaus
        86264, -- Path Gradients after Flow Matching
        86402, -- BoltzNCE: Learning likelihoods for Boltzmann Generation with Stochasti
        86536, -- MANGO: Multimodal Attention-based Normalizing Flow Approach to Fusion
        86624, -- Flexible Language Modeling in Continuous Space with Transformer-based
        86989, -- Inductive Domain Transfer In Misspecified Simulation-Based Inference
        87159, -- DiCoFlex: Model-Agnostic Diverse Counterfactuals with Flexible Control
        87399, -- Normalizing Flows are Capable Models for RL
        87419, -- Asymptotically exact variational flows via involutive MCMC kernels
        88583, -- Learning Distances from Data with Normalizing Flows and Score Matching
        88970, -- Score-based Pullback Riemannian Geometry: Extracting the Data Manifold
        89405, -- Importance Corrected Neural JKO Sampling
        89433, -- Temperature-Annealed Boltzmann Generators
        89584, -- Computing Optimal Transport Maps and Wasserstein Barycenters Using Con
        89603, -- Flexible Tails for Normalizing Flows
        89664, -- Flow-based Domain Randomization for Learning and Sequencing Robotic Sk
        89914, -- Annealing Flow Generative Models Towards Sampling High-Dimensional and
        89931, -- Can Transformers Learn Full Bayesian Inference in Context?
        90638, -- Robust Message Embedding via Attention Flow-Based Steganography
        90695, -- TensoFlow: Tensorial Flow-based Sampler for Inverse Rendering
        91240, -- Injective flows for star-like manifolds
        91390, -- Rare event modeling with self-regularized normalizing flows: what can
        92425, -- SoftCVI: Contrastive variational inference with self-generated soft la
        92772, -- Accelerated Parallel Tempering via Neural Transports
        93091, -- SESaMo: Symmetry-Enforcing Stochastic Modulation for Normalizing Flows
        93175, -- APC-RL: Exceeding data-driven behavior priors with adaptive policy com
        93397, -- Reliable Probabilistic Forecasting of Irregular Time Series through Ma
        93633, -- Efficient Regression-based Training of Normalizing Flows for Boltzmann
        93636, -- FALCON: Few-step Accurate Likelihoods for Continuous Flows
        93722, -- Joint Distillation for Fast Likelihood Evaluation and Sampling in Flow
        93877, -- AlignFlow: Improving Flow-based Generative Models with Semi-Discrete O
        93929, -- JAPAN: Joint Adaptive Prediction Areas with Normalising Flow
        94053, -- GDR-learners: Orthogonal Learning of Generative Models for Potential O
        94748, -- CE-Nav: Flow-Guided Reinforcement Refinement for Cross-Embodiment Loca
        95101, -- Latent Reasoning with Normalizing Flows
        95998, -- SIT-LMPC: Safe Information-Theoretic Learning Model Predictive Control
        97178, -- Data-Efficient Hierarchical Goal-Conditioned Reinforcement Learning Vi
        98945, -- MIMFlow: Integrating Masked Image Modeling with Normalizing Flows for
        99535, -- QHyer: Q-conditioned Hybrid Attention-mamba Transformer for Offline Go
        99752, -- MusicDET: Zero-Shot AI-Generated Music Detection
        100459, -- Unsupervised Disentanglement Without Compromises : How Functional Orth
        100596, -- SCOUT: Cyclic Causal Discovery Under Soft Interventions with Unknown T
        100882, -- Manifold-Aware Perturbations for Constrained Generative Modeling
        101124, -- Autoregressive Boltzmann Generators
        101611, -- Analytic Bijections for Smooth and Interpretable Normalizing Flows
        101850, -- Flow-Based Density Ratio Estimation for Intractable Distributions with
        102105, -- Normalizing Flows with Iterative Denoising
        102229, -- Identifying Connectivity Distributions from Neural Dynamics Using Flow
        104181, -- Probabilistic Monocular 3D Human Pose Estimation with Normalizing Flow
        104376, -- iFlow: Numerically Invertible Flows for Efficient Lossless Compression
        104935, -- Alzheimer’s Disease Recognition Based on Adaptive Graph Normalization
        105115, -- Distribution-Guided Multi-Tracer Brain PET Synthesis from Structural M
        105421, -- MixStyleFlow: Domain Generalization in Medical Image Segmentation usin
        105890, -- CFLOW-AD: Real-Time Unsupervised Anomaly Detection with Localization v
        105897, -- Same Same But DifferNet: Semi-Supervised Defect Detection with Normali
        105899, -- Asymmetric Student-Teacher Networks for Industrial Anomaly Detection
        105905, -- MSFlow: Multi-Scale Flow-based Framework for Unsupervised Anomaly Dete
        106440, -- Universal Learning of Stochastic Dynamics for Exact Belief Propagation
        106487, -- Flow-Induced Diagonal Gaussian Processes
        108209, -- Breaking the Adversarial Robustness-Performance Trade-off in Text Clas
        108317, -- Riemannian Manifold Learning for Stackelberg Games with Neural Flow Re
        110254, -- Doubling Your Data in Minutes: Ultra-fast Tabular Data Generation via
        111205, -- Investigating Stochastic Methods for Prosody Modeling in Speech Synthe
        111416, -- Synthesizing Speech with Selected Perceptual Voice Qualities – A Case
        112121, -- LRBA: Stealthy Backdoor Attacks on Speech Classification via Latent Re
        112789, -- Hierarchical Gaussian Mixture Normalizing Flow Modeling for Unified An
        112876, -- This Probably Looks Exactly Like That: An Invertible Prototypical Netw
        113026, -- GLARE: Low Light Image Enhancement via Generative Latent Feature based
        113499, -- Sequential Representation Learning via Static-Dynamic Conditional Dise
        113663, -- Energy-Clibrated VAE with Test Time Free Lunch
        115654, -- Denoising Point Clouds in Latent Space via Graph Convolution and Inver
        115849, -- Normalizing Flows on the Product Space of SO(3) Manifolds for Probabil
        116319, -- Perception-Oriented Video Frame Interpolation via Asymmetric Blending
        116507, -- Towards the Uncharted: Density-Descending Feature Perturbation for Sem
        116963, -- Boosting Flow-based Generative Super-Resolution Models via Learned Pri
        117125, -- FlowVQTalker: High-Quality Emotional Talking Face Generation through N
        117386, -- JSON: Jigsaw Self-play Optimization for Normalizing Flows
        117427, -- DeCoFlow: Structural Decomposition of Normalizing Flows for Continual
        118864, -- μFlow: Leveraging Average Images for Improving Generalisation of Deepf
        119041, -- Bounding-Box Trajectories Matter for Video Anomaly Detection
        120540, -- Reversing Flow for Image Restoration
        121265, -- RevINN: An End-to-End Invertible Neural Network for Reversible Adversa
        123503 -- NICE: Non-linear Independent Components Estimation
  );

DELETE FROM paper_method_exclusions x
USING normalizing_flows_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM normalizing_flows_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM normalizing_flows_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: the paper only mentions normalizing flows as a
-- baseline or model family, or its "flow-based generative model" is a flow
-- matching, rectified flow or diffusion model. The exclusions keep the keyword
-- backfill from re-linking them.
CREATE TEMP TABLE normalizing_flows_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'normalizing-flows'
  AND p.id IN (
        3299, -- TraDE: Transformers for Density Estimation
        4334, -- HiFi-GAN: Generative Adversarial Networks for Efficient and High Fidel
        6002, -- Spot the Difference: Detection of Topological Changes via Geometric Al
        6243, -- Feature Shift Detection: Localizing Which Features Have Shifted via Co
        10586, -- Flow Matching for Generative Modeling
        10716, -- Unifying Diffusion Models' Latent Space, with Applications to CycleDif
        11525, -- Diffusion Model Based Posterior Sampling for Noisy Linear Inverse Prob
        12751, -- Improving and generalizing flow-based generative models with minibatch
        12924, -- Flow Matching on General Geometries
        13011, -- Removing Structured Noise with Diffusion Models
        15284, -- Improved Techniques for Maximum Likelihood Estimation for Diffusion OD
        19709, -- Improving Generative Model-based Unfolding with Schrödinger Bridges
        21453, -- Analysis of learning a flow-based generative model from limited sample
        23666, -- Guided Flows for Generative Modeling and Decision Making
        24803, -- Mosaic-SDF for 3D Generative Models
        26941, -- AdaFlow: Imitation Learning with Variance-Adaptive Flow-Based Policies
        27122, -- Sequential Flow Straightening for Generative Modeling
        28351, -- CSE: Surface Anomaly Detection with Contrastively Selected Embedding
        31778, -- Reflected Flow Matching
        33169, -- Scaling the Codebook Size of VQGAN to 100,000 with a Utilization Rate
        33344, -- Hitchhiker's guide on the relation of Energy-Based Models with other g
        37401, -- FlowTurbo: Towards Real-time Flow-Based Image Generation with Velocity
        41462, -- OFTSR: One-Step Flow for Image Super-Resolution with Tunable Fidelity-
        44667, -- ReQFlow: Rectified Quaternion Flow for Efficient and High-Quality Prot
        46347, -- Deeply Supervised Flow-Based Generative Models
        50466, -- Solving Inverse Problems with FLAIR
        50635, -- Aligning Latent Spaces with Flow Priors
        53288, -- Equilibrium Matching: Generative Modeling with Implicit Energy-Based M
        53619, -- pi-Flow: Policy-Based Few-Step Generation via Imitation Distillation
        53935, -- The Principles of Diffusion Models
        54458, -- Flow Straighter and Faster: Efficient One-Step Generative Modeling via
        55266, -- ShowUI-π: Flow-based Generative Models as GUI Dexterous Hands
        55594, -- One-step Latent-free Image Generation with Pixel Mean Flows
        58804, -- MotionRFT: Unified Reinforcement Fine-Tuning for Text-to-Motion Genera
        59577, -- V2A-DPO: Omni-Preference Optimization for Video-to-Audio Generation
        60358, -- Momentum Guidance: Plug-and-Play Guidance for Flow Models
        61991, -- SNR-Edit: Structure-Aware Noise Rectification for Inversion-Free Flow-
        63628, -- SuperFlow: Training Flow Matching Models with RL on the Fly
        63806, -- Refining Graphical Neural Network Predictions Using Flow Matching for
        64621, -- VeCoR -- Velocity Contrastive Regularization for Flow Matching
        65892, -- Multimodal Datasets with Controllable Mutual Information
        66135, -- Fine-tuning Flow Matching Generative Models with Intermediate Feedback
        67038, -- Distilled Protein Backbone Generation
        67106, -- Fine-Tuning Flow Matching via Maximum Likelihood Estimation of Reconst
        67438, -- ThermalGen: Style-Disentangled Flow-Based Generative Models for RGB-to
        67454, -- SenSE: Semantic-Aware High-Fidelity Universal Speech Enhancement
        68654, -- If generative AI is the answer, what is the question?
        70197, -- RAAG: Ratio Aware Adaptive Guidance
        70199, -- SCFlow: Implicitly Learning Style and Content Disentanglement with Flo
        70559, -- Weighted Conditional Flow Matching
        70625, -- Flow Matching Policy Gradients
        72197, -- Antithetic Noise in Diffusion Models
        72756, -- How to build a consistency model: Learning flow maps via self-distilla
        74363, -- Proteina: Scaling Flow-based Protein Structure Generative Models
        81224, -- NVAE: A Deep Hierarchical Variational Autoencoder
        83524, -- Stitched Value Model for Diffusion Alignment
        84024, -- Task-Driven Implicit Representations for Automated Design of LiDAR Sys
        84395, -- POLAR: A Portrait OLAT Dataset and Generative Framework for Illuminati
        84991, -- Adapting a Pre-trained Single-Cell Foundation Model to Spatial Gene Ex
        85229, -- EgoFlow: Gradient-Guided Flow Matching for Egocentric 6DoF Object Moti
        85775, -- Flow-Based Policy for Online Reinforcement Learning
        85794, -- Physics-Constrained Flow Matching: Sampling Generative Models with Har
        86779, -- NeuralPLexer3: Accurate Biomolecular Complex Structure Prediction with
        86803, -- PhySense: Sensor Placement Optimization for Accurate Physics Sensing
        88593, -- Controlled Generation with Equivariant Variational Flow Matching
        89333, -- Stream-level Flow Matching with Gaussian Processes
        89655, -- Geometric Generative Modeling with Noise-Conditioned Graph Networks
        89794, -- An Adaptive Orthogonal Convolution Scheme for Efficient and Flexible C
        90547, -- DiverseFlow: Sample-Efficient Diverse Mode Coverage in Flows
        91155, -- Scale-Aware Contrastive Reverse Distillation for Unsupervised Medical
        91993, -- Linear combinations of latents in generative models: subspaces and bey
        92157, -- Online Reward-Weighted Fine-Tuning of Flow Matching with Wasserstein R
        93870, -- Translate Policy to Language: Flow Matching Generated Rewards for LLM
        94188, -- DoFlow: Flow-based Generative Models for Interventional and Counterfac
        98091, -- COT-FM: Cluster-wise Optimal Transport Flow Matching (AutoSOTA)
        99371, -- A Kinetic Energy Perspective of Flow Matching
        100212, -- Trajectory Stitching for Solving Inverse Problems with Flow-Based Mode
        100427, -- DAISI: Data Assimilation with Inverse Sampling using Stochastic Interp
        100609, -- Mean Flow Policy Optimization
        100752, -- PolyFlow: Safe and Efficient Polytope-Constrained Flow Matching with C
        100772, -- Moment Matching Q-Learning
        100945, -- Adapting Noise to Data: Generative Flows from Learned 1D Processes
        100967, -- Unfolding Generative Flows with Koopman Operators: Trajectory-Preservi
        101627, -- Solving Inverse Problems with Flow-based Models via Model Predictive C
        101949, -- Learning Discriminative and Generalizable Anomaly Detector for Dynamic
        106929, -- A-FloPS: Accelerating Diffusion Models via Adaptive Flow Path Sampler
        115896, -- Learned Lossless Image Compression based on Bit Plane Slicing
        118509, -- Trajectory Forcing: Structure-First Generation with Controllable Seman
        118531, -- Dual-End Consistency Model
        121307 -- Flow Matching for Multimodal Distributions
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'Normalizing flows curation 2026-10-15: mentions flows in passing or uses flow matching, not a normalizing flow'
FROM normalizing_flows_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING normalizing_flows_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING normalizing_flows_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
