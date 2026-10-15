-- Gaussian process regression has no single introducing paper (kriging and
-- Williams & Rasmussen 1996 predate the ML usage), so the source is the canonical
-- Rasmussen & Williams textbook and papers are linked from a reviewed set.

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
    'gaussian-process-regression',
    'Gaussian Process Regression',
    'Gaussian Process Regression (GPR)',
    'Gaussian process regression (GPR) is a nonparametric Bayesian method that places a Gaussian process prior directly over functions. The prior is specified by a mean function and a covariance (kernel) function, such as the squared-exponential or Matérn kernel, that encodes assumptions about smoothness and length scale. Conditioning on noisy observations gives a closed-form Gaussian posterior, so every prediction comes with a calibrated predictive mean and variance, and kernel hyperparameters are fit by maximizing the marginal likelihood. Exact inference costs cubic time in the number of training points, which motivated sparse inducing-point, variational and structured-kernel approximations. The method has roots in kriging from geostatistics and was popularized in machine learning by Williams and Rasmussen; GPR is the standard surrogate model in [Bayesian optimization](/methods/bayesian-optimization) and is widely used for uncertainty-aware regression, active learning and scientific modeling.',
    'gaussian process regression, gaussian process, GP regression',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'http://gaussianprocess.org/gpml/',
    'Gaussian Processes for Machine Learning (Rasmussen & Williams, 2006)',
    'https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/gaussian_process/_gpr.py',
    NULL,
    '[Gaussian Process Regression](https://commons.wikimedia.org/wiki/File:Gaussian_Process_Regression.png) by Cdipaolo96, CC BY-SA 4.0'
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

-- Curated 2026-10-15 from every title/abstract mention of "Gaussian process": each paper below fits, extends, analyzes or applies Gaussian process regression or GP surrogate models.
CREATE TEMP TABLE gaussian_process_regression_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gaussian-process-regression'
  AND p.id IN (
        466, -- Optimizing Neural Network Hyperparameters with Gaussian Processes for
        1241, -- Gaussian Material Synthesis
        1381, -- A Tutorial on Bayesian Optimization
        1424, -- Multitask Gaussian Process with Hierarchical Latent Interactions
        1539, -- Generating Shared Latent Variables for Robots to Imitate Human Movemen
        1737, -- Learning Nonlinear State Space Models with Hamiltonian Sequential Mont
        1809, -- Early Recognition of Sepsis with Gaussian Process Temporal Convolution
        2973, -- Approximate Inference for Fully Bayesian Gaussian Process Regression
        3246, -- Model-based Asynchronous Hyperparameter and Neural Architecture Search
        3371, -- What do you Mean? The Role of the Mean Function in Bayesian Optimisati
        3686, -- Time-Resolved fMRI Shared Response Model using Gaussian Process Factor
        3706, -- Interpretable Neural Architecture Search via Bayesian Optimisation wit
        4087, -- Machine learning thermal circuit network model for thermal design opti
        4100, -- Real Image Super Resolution Via Heterogeneous Model Ensemble using GP-
        4536, -- Sparse within Sparse Gaussian Processes using Neighbor Information
        4557, -- Cluster-Specific Predictions with Multi-Task Gaussian Processes
        4615, -- All You Need is a Good Functional Prior for Bayesian Deep Learning
        5165, -- Active Testing: Sample-Efficient Model Evaluation
        5631, -- How Bayesian Should Bayesian Optimisation Be?
        6509, -- A theory of representation learning gives a deep generalisation of ker
        7572, -- Transformers Can Do Bayesian Inference
        8081, -- StrongSORT: Make DeepSORT Great Again
        8259, -- ActFormer: A GAN-based Transformer towards General Action-Conditioned
        8319, -- A Framework and Benchmark for Deep Batch Active Learning for Regressio
        9273, -- Efficient Transformed Gaussian Processes for Non-Stationary Dependent
        9452, -- Modeling the Machine Learning Multiverse
        9767, -- Markovian Gaussian Process Variational Autoencoders
        10815, -- Monotonicity and Double Descent in Uncertainty Estimation with Gaussia
        10988, -- Meta Learning of Interface Conditions for Multi-Domain Physics-Informe
        11742, -- Safe Learning-Based Control of Elastic Joint Robots via Control Barrie
        12249, -- Gaussian Process Priors for Systems of Linear Partial Differential Equ
        12540, -- Random Grid Neural Processes for Parametric Partial Differential Equat
        12692, -- Variational sparse inverse Cholesky approximation for latent Gaussian
        12800, -- Randomized Gaussian Process Upper Confidence Bound with Tighter Bayesi
        12801, -- Towards Practical Preferential Bayesian Optimization with Skew Gaussia
        12973, -- Fully Bayesian Autoencoders with Latent Sparse Gaussian Processes
        13206, -- Free-Form Variational Inference for Gaussian Process State-Space Model
        13220, -- Gaussian processes at the Helm(holtz): A more fluid model for ocean cu
        13379, -- Interactive Segmentation as Gaussian Process Classification
        14486, -- Self-Distillation for Gaussian Process Regression and Classification
        15006, -- Spherical Inducing Features for Orthogonally-Decoupled Gaussian Proces
        15889, -- MMGP: a Mesh Morphing Gaussian Process-based machine learning method f
        16683, -- Constrained Causal Bayesian Optimization
        16685, -- A Study of Bayesian Neural Network Surrogates for Bayesian Optimizatio
        16888, -- Linear Time GPs for Inferring Latent Trajectories from Neural Spike Tr
        17042, -- Memory-Based Dual Gaussian Processes for Sequential Learning
        17086, -- Improving Hyperparameter Learning under Approximate Inference in Gauss
        17107, -- Training-Free Neural Active Learning with Initialization-Robustness Gu
        18605, -- GaPro: Box-Supervised 3D Point Cloud Instance Segmentation Using Gauss
        20461, -- Sparsity-Aware Distributed Learning for Gaussian Processes with Linear
        21052, -- Implicit Gaussian process representation of vector fields over arbitra
        21097, -- Leave-one-out Distinguishability in Machine Learning
        21415, -- Multi-modal Gaussian Process Variational Autoencoders for Neural and B
        22813, -- Stochastic Gradient Descent for Gaussian Processes Done Right
        22909, -- A Coreset-based, Tempered Variational Posterior for Accurate and Scala
        23079, -- Solving High Frequency and Multi-Scale PDEs with Gaussian Processes
        23090, -- Functional Bayesian Tucker Decomposition for Continuous-indexed Tensor
        23503, -- Short-term Volatility Estimation for High Frequency Trades using Gauss
        23638, -- Multi-fidelity Bayesian Optimization in Engineering Design
        25057, -- Longitudinal prediction of DNA methylation to forecast epigenetic outc
        26324, -- Bayesian Optimization through Gaussian Cox Process Models for Spatio-t
        28425, -- Localized Zeroth-Order Prompt Optimization
        28744, -- Chronos: Learning the Language of Time Series
        28893, -- Touch-GS: Visual-Tactile Supervised 3D Gaussian Splatting
        32219, -- NeoRL: Efficient Exploration for Nonepisodic RL
        32500, -- Navigating Efficiency in MobileViT through Gaussian Process on Global
        33758, -- Improving Hyperparameter Optimization with Checkpointed Model Weights
        35664, -- Model-Based Transfer Learning for Contextual Reinforcement Learning
        36190, -- TVG: A Training-free Transition Video Generation Method with Diffusion
        37819, -- A Spatio-Temporal Machine Learning Model for Mortgage Credit Risk: Def
        43609, -- Learning Hyperparameters via a Data-Emphasized Variational Objective
        43644, -- GP-GS: Gaussian Processes for Enhanced Gaussian Splatting
        52920, -- Adaptive Kernel Design for Bayesian Optimization Is a Piece of CAKE wi
        53295, -- Adaptive Pruning for Increased Robustness and Reduced Computational Ov
        55651, -- Machine Learning for Energy-Performance-aware Scheduling
        57201, -- Efficient and Principled Scientific Discovery through Bayesian Optimiz
        57751, -- ProEval: Proactive Failure Discovery and Efficient Performance Estimat
        58239, -- Uncertainty-Aware Image Classification In Biomedical Imaging Using Spe
        60599, -- Distributed Quantum Gaussian Processes for Multi-Agent Systems
        60752, -- Federated Gaussian Process Learning via Pseudo-Representations for Lar
        62415, -- Learning-Based Shrinking Disturbance-Invariant Tubes for State- and In
        63145, -- Latent-Constrained Conditional VAEs for Augmenting Large-Scale Climate
        64440, -- Probabilistic Digital Twin for Misspecified Structural Dynamical Syste
        65502, -- A structural equation formulation for general quasi-periodic Gaussian
        65676, -- TempoPFN: Synthetic Pre-training of Linear RNNs for Zero-shot Time Ser
        66206, -- Infinite Neural Operators: Gaussian processes on functions
        68118, -- ROOT: Rethinking Offline Optimization as Distributional Translation vi
        70246, -- CauKer: classification time series foundation models can be pretrained
        72984, -- Efficient Implementation of Gaussian Process Regression Accelerated Sa
        73988, -- Extended Dark Energy analysis using DESI DR2 BAO measurements
        74402, -- Pattern and Origin for the Extreme γ-ray Flares of 3C 454.3 and 3C 279
        74652, -- O-MMGP: Optimal Mesh Morphing Gaussian Process Regression for Solving
        74736, -- Learning large scale industrial physics simulations
        75864, -- A Safe and Data-efficient Model-based Reinforcement Learning System fo
        75915, -- A Third-Order Gaussian Process Trajectory Representation Framework wit
        76560, -- Optimizing the L-σ Relation of HII Galaxies for Improving Cosmological
        78154, -- Materials Expert-Artificial Intelligence for Materials Discovery
        78223, -- Sustainable Concrete via Bayesian Optimization
        79413, -- Tensor Gaussian Process with Contraction for Multi-Channel Imaging Ana
        79442, -- Robust Bayesian Target Value Optimization
        79469, -- Piecewise-Velocity Model for Learning Continuous-time Dynamic Node Rep
        79616, -- Constrained Efficient Global Optimization of Expensive Black-box Funct
        79692, -- A Probabilistic Model for Aircraft in Climb using Monotonic Functional
        79801, -- An Empirical Analysis of the Laplace and Neural Tangent Kernels
        80153, -- Fully Decentralized, Scalable Gaussian Processes for Multi-Agent Feder
        80237, -- Scaling Gaussian Process Optimization by Evaluating a Few Unique Candi
        80591, -- MLMOD: Machine Learning Methods for Data-Driven Modeling in LAMMPS
        80865, -- Safe Learning-based Gradient-free Model Predictive Control Based on Cr
        81044, -- Simple and Principled Uncertainty Estimation with Deterministic Deep L
        81440, -- Near-linear Time Gaussian Process Optimization with Adaptive Batching
        81632, -- Gaussian Process Optimization with Adaptive Sketching: Scalable and No
        81916, -- Fast and Accurate Uncertainty Estimation in Chemical Machine Learning
        82063, -- Distributed Adaptive Sampling for Kernel Matrix Approximation
        82096, -- Neural Architecture Search with Bayesian Optimisation and Optimal Tran
        82496, -- Dropout as a Bayesian Approximation: Representing Model Uncertainty in
        82532, -- Avoiding tipping points in fisheries management through Gaussian Proce
        82565, -- Freeze-Thaw Bayesian Optimization
        83715, -- Integrative Analysis and Imputation of Multiple Data Streams via Deep
        85254, -- GP-4DGS: Probabilistic 4D Gaussian Splatting from Monocular Video via
        85902, -- Optimal kernel regression bounds under energy-bounded noise
        85962, -- Modeling Neural Activity with Conditionally Linear Dynamical Systems
        86075, -- STACI: Spatio-Temporal Aleatoric Conformal Inference
        86391, -- Uncertainty Quantification with the Empirical Neural Tangent Kernel
        86450, -- Recurrent Memory for Online Interdomain Gaussian Processes
        86490, -- Convergence Rates of Constrained Expected Improvement
        86858, -- SING: SDE Inference via Natural Gradients
        86881, -- Robust Satisficing Gaussian Process Bandits Under Adversarial Attacks
        86975, -- Robust and Computation-Aware Gaussian Processes
        87138, -- Turbocharging Gaussian Process Inference with Approximate Sketch-and-P
        87351, -- Gaussian Process Upper Confidence Bound Achieves Nearly-Optimal Regret
        87378, -- Improved Regret Bounds for Gaussian Process Upper Confidence Bound in
        87425, -- Sparse Gaussian Processes: Structured Approximations and Power-EP Revi
        87469, -- Multi-View Oriented GPLVM: Expressiveness and Efficiency
        88537, -- Learning Time-Varying Multi-Region Brain Communications via Scalable M
        88562, -- Improved Regret Analysis in Gaussian Process Bandits: Optimality for N
        88789, -- Stochastic Poisson Surface Reconstruction with One Solve using Geometr
        88825, -- Scalable Gaussian Processes with Latent Kronecker Structure
        88887, -- Hierarchical Reinforcement Learning with Uncertainty-Guided Diffusiona
        88950, -- Understanding High-Dimensional Bayesian Optimization
        89250, -- Learning Safe Control via On-the-Fly Bandit Exploration
        89389, -- Multi-Timescale Dynamics Model Bayesian Optimization for Plasma Stabil
        89396, -- Hyperband-based Bayesian Optimization for Black-box Prompt Selection
        89412, -- BARK: A Fully Bayesian Tree Kernel for Black-box Optimization
        89492, -- PAC-Bayes Analysis for Recalibration in Classification
        89658, -- Neighbour-Driven Gaussian Process Variational Autoencoders for Scalabl
        89668, -- Continuous Bayesian Model Selection for Multivariate Causal Discovery
        89682, -- Robust and Conjugate Spatio-Temporal Gaussian Processes
        89706, -- Distributionally Robust Active Learning for Gaussian Process Regressio
        89738, -- The Price of Linear Time: Error Analysis of Structured Kernel Interpol
        90005, -- Linearization Turns Neural Operators into Function-Valued Gaussian Pro
        90011, -- Adjusting Model Size in Continual Gaussian Processes: How Big is Big E
        90057, -- New Bounds for Sparse Variational Gaussian Processes
        91030, -- Standard Gaussian Process is All You Need for High-Dimensional Bayesia
        91042, -- Residual Deep Gaussian Processes on Manifolds
        91256, -- Optimizing Posterior Samples for Bayesian Optimization via Rootfinding
        91835, -- Learning the Optimal Stopping for Early Classification within Finite H
        92261, -- Bayesian Analysis of Combinatorial Gaussian Process Bandits
        92629, -- Adaptive Rollout Allocation for Online Reinforcement Learning with Ver
        92741, -- ActiveCQ: Active Estimation of Causal Quantities
        92996, -- Laplacian Kernelized Bandit
        93051, -- Uncertainty-Aware Diagnostics for Physics-Informed Machine Learning
        93157, -- Bayesian Parameter Shift Rules in Variational Quantum Eigensolvers
        93450, -- Combinatorial Bandit Bayesian Optimization for Tensor Outputs
        93723, -- SEED-SET: Scalable Evolving Experimental Design for System-level Ethic
        94405, -- Sample-efficient and Scalable Exploration in Continuous-Time RL
        94478, -- Diffusion Bridge Variational Inference for Deep Gaussian Processes
        94527, -- Graph Random Features for Scalable Gaussian Processes
        94772, -- Meta-Learning Theory-Informed Inductive Biases using Deep Kernel Gauss
        95248, -- Perception-Driven Estimation of Terrain Motion Resistance for UGVs
        95251, -- Taxonomy-Aware Dynamic Motion Generation on Hyperbolic Manifolds
        95307, -- Real-Time Online Learning for Model Predictive Control Using a Spatio-
        95471, -- Depth-Constrained ASV Navigation with Deep RL and Limited Sensing
        95583, -- Towards Versatile Opti-Acoustic Sensor Fusion and Volumetric Mapping f
        95818, -- Gaussian Process Implicit Surfaces As Control Barrier Functions for Sa
        95889, -- Probabilistically-Safe Bipedal Navigation Over Uncertain Terrain Via C
        95930, -- ILeSiA: Interactive Learning of Robot Situational Awareness from Camer
        95935, -- Multivariate Active Learning and Adaptive Sampling with Multi-Kernel G
        95994, -- Muscle Fatigue-Aware Controller for a Semi-Rigid Knee Exoskeleton (I)
        96158, -- Human-Interpretable Uncertainty Explanations for Point Cloud Registrat
        96167, -- Energy-Aware Informative Path Planning for Heterogeneous Multi-Robot S
        96229, -- Task Generalization with Pathwise Conditioning of Gaussian Process for
        96488, -- Gaussian Process-Based Gait Optimization of a Cable-Driven Soft Quadru
        96524, -- Multi-Robot Informative Sampling and Coverage in GPS-Denied Environmen
        96767, -- DisFlow: Scene Flow from Distance Field for Object Pose, Velocity Trac
        96850, -- Stable Trajectory Planning for Quadruped Robots Using Terrain Features
        96900, -- Autonomous Exploration for Shape Reconstruction and Measurement Via In
        96959, -- A Distributed Gaussian Process Model for Multi-Robot Mapping
        97049, -- Prior-Constrained Explorative Guidance for Generalization in Diffusion
        97202, -- Multi-Robot Trajectory Planning Via Constrained Bayesian Optimization
        97225, -- Dual Quaternion Based Compliant Movement Primitives for Deformable Obj
        97331, -- Real-Time Communication Relay Planning with a Low-Complexity Network Q
        97685, -- Resource Mapping with a Mobile Exploration Robot Using Spectral Mixtur
        97718, -- Long-Term Mapping of the Douro River Plume with Multi-Agent Reinforcem
        97770, -- Continuous Gaussian Process Pre-Optimization for Asynchronous Event-In
        97817, -- Data-Efficient Constrained Robot Learning with Probabilistic Lagrangia
        99280, -- RoCA: Robust Cross-Domain End-to-End Autonomous Driving
        99292, -- Regime-Adaptive Bayesian Optimization via Dirichlet Process Mixtures o
        99700, -- Flexible Kernels for Protein Property Prediction
        99774, -- Transformed Latent Variable Multi-Output Gaussian Processes
        99898, -- Robust Bayesian Optimisation with Unbounded Corruptions
        100012, -- Tighter Regret Lower Bound for Gaussian Process Bandits with Squared E
        100067, -- PolicyGuard: Towards Test-time and Step-level Adversary Defense for Re
        100204, -- $\texttt{ShaplEIG}$: Bayesian Experimental Design for Shapley Value Es
        100667, -- Transformers Can Learn Posterior Predictive Distributions In-Context
        100926, -- Modeling Temporal scRNA-seq Data with Latent Gaussian Process and Opti
        101021, -- SIKA-GP: Accelerating Gaussian Process Inference with Sparse Inducing
        101086, -- LILO: Bayesian Optimization with Natural Language Feedback
        101179, -- gp2Scale: A Class of Compactly Supported Non-Stationary Kernels and Di
        101200, -- Empirical Gaussian Processes
        101263, -- Principle-Evolvable Scientific Discovery via Uncertainty Minimization
        101523, -- Scalable Bayesian Inference for Nonlinear Conservation Laws
        101858, -- Efficient Neural Controlled Differential Equations via Attentive Kerne
        101899, -- Goal-Oriented Lower-Tail Calibration of Gaussian Processes for Bayesia
        101989, -- Posterior Sampling Reinforcement Learning with Gaussian Processes for
        102217, -- On Regret Bounds of Thompson Sampling for Bayesian Optimization
        102501, -- Active Timepoint Selection for Learning Measure-Valued Trajectories
        106487, -- Flow-Induced Diagonal Gaussian Processes
        106740, -- Advanced Black-Box Tuning of Large Language Models with Limited API Ca
        106743, -- Parametric Pareto Set Learning for Expensive Multi-Objective Optimizat
        106764, -- Streaming Generated Gaussian Process Experts for Online Learning and C
        107015, -- Causal Structure Learning for Dynamical Systems with Theoretical Score
        107208, -- PhyPlan: Learning to Plan Tasks with Generalizable and Rapid Physical
        107659, -- Reward Redistribution via Gaussian Process Likelihood Estimation
        107815, -- Structure Detection for Contextual Reinforcement Learning
        108071, -- Exact Shapley Attributions in Quadratic-time for FANOVA Gaussian Proce
        108125, -- Function-on-Function Bayesian Optimization
        108415, -- Practical Global and Local Bounds in Gaussian Process Regression via C
        110638, -- RD-MCSA: A Multi-Class Sentiment Analysis Approach Integrating In-Cont
        111520, -- Few-Shot Speech Deepfake Detection Adaptation with Gaussian Processes
        112209, -- Practical Gaussian Process Implicit Surfaces with Sparse Convolutions
        113625, -- LMT-GP: Combined Latent Mean-Teacher and Gaussian Process for Semi-sup
        114391, -- Automated Robust Muscle Segmentation in Multi-level Contexts using a P
        115841, -- Bayesian Exploration of Pre-trained Models for Low-shot Image Classifi
        118617, -- Accelerating Diffusion Transformers with Gaussian Process Rectified Fe
        120099, -- Dense-SfM: Structure from Motion with Dense Consistent Matching
        122165, -- WhatWorkedBench: Benchmarking Experimental Understanding in AI Agents
        122858, -- Operator-Informed Gaussian Processes for Complex Helmholtz Wavefields:
        123181 -- Constrained Probabilistic Numerics: Gaussian Process Solvers for Linea
  );

DELETE FROM paper_method_exclusions x
USING gaussian_process_regression_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gaussian_process_regression_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM gaussian_process_regression_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: Gaussian processes appear only as a baseline or motivation, as a probability-theory object (infinite-width network limits, Brownian bridges, diffusion noise), or as a GP-shaped prior inside another model.
CREATE TEMP TABLE gaussian_process_regression_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gaussian-process-regression'
  AND p.id IN (
        395, -- Policy Networks with Two-Stage Training for Dialogue Systems
        624, -- Modeling Long- and Short-Term Temporal Patterns with Deep Neural Netwo
        1349, -- Neural Tangent Kernel: Convergence and Generalization in Neural Networ
        2461, -- Finite size corrections for neural network Gaussian processes
        3790, -- 70 years of machine learning in geoscience in review
        6175, -- Scale Mixtures of Neural Network Gaussian Processes
        6598, -- KNODE-MPC: A Knowledge-based Data-driven Predictive Control Framework
        9412, -- Neural Diffusion Processes
        9619, -- Supernova Light Curves Approximation based on Neural Network Models
        10301, -- Understanding of the properties of neural network approaches for trans
        11389, -- Global Optimization with Parametric Function Approximation
        12563, -- Estimating Causal Effects using a Multi-task Deep Ensemble
        14323, -- Neural signature kernels as infinite-width-depth-limits of controlled
        14790, -- Martingale Posterior Neural Processes
        15269, -- Optimizing Hyperparameters with Conformal Quantile Regression
        15314, -- Disentangled Multi-Fidelity Deep Bayesian Active Learning
        16574, -- Prediction Error-based Classification for Class-Incremental Learning
        17870, -- DialoGPS: Dialogue Path Sampling in Continuous Semantic Space for Data
        20568, -- Convolutional Deep Kernel Machines
        21387, -- Use Your INSTINCT: INSTruction optimization for LLMs usIng Neural band
        21478, -- Grokking as a First Order Phase Transition in Two Layer Networks
        22545, -- Beyond IID weights: sparse and low-rank deep Neural Networks are also
        27959, -- Deep Neural Network Initialization with Sparsity Inducing Activations
        28671, -- In-context Exploration-Exploitation for Reinforcement Learning
        28963, -- Function-space Parameterization of Neural Networks for Sequential Lear
        30790, -- In-Context Freeze-Thaw Bayesian Optimization for Hyperparameter Optimi
        30825, -- Multi-layer random features and the approximation power of neural netw
        33016, -- A Rate-Distortion View of Uncertainty Quantification
        34770, -- Global Optimisation of Black-Box Functions with Generative Models in t
        43653, -- Distribution Transformers: Fast Approximate Bayesian Inference With On
        44864, -- Exact Learning of Permutations for Nonzero Binary Inputs with Logarith
        51034, -- The Diffusion Duality
        61420, -- Statistical Learning Theory in Lean 4: Empirical Processes from Scratc
        61596, -- Latent Shadows: The Gaussian-Discrete Duality in Masked Diffusion
        63205, -- Flow Matching Neural Processes
        65683, -- GPTOpt: Teaching LLMs to do Interpretable Black-Box Optimization
        68021, -- RAVEN: RAnking and Validation of ExoplaNets
        68269, -- TFMAdapter: Lightweight Instance-Level Adaptation of Foundation Models
        71699, -- Thompson Sampling in Function Spaces via Neural Operators
        78005, -- The Slepian model based independent interval approximation of persiste
        79006, -- Convergence of local times of stochastic processes associated with res
        79087, -- Nonparametric Modeling of Diffusion MRI Signal in Q-space
        81813, -- Scaling Limits of Wide Neural Networks with Weight Sharing: Gaussian P
        81912, -- Set Transformer: A Framework for Attention-based Permutation-Invariant
        82657, -- Some Properties of Large Excursions of a Stationary Gaussian Process
        86185, -- Infinite-Width Limit of a Single Attention Layer: Analysis via Tensor
        86603, -- A Provable Approach for End-to-End Safe Reinforcement Learning
        86651, -- Hessian-guided Perturbed Wasserstein Gradient Flows for Escaping Saddl
        86720, -- Generating Full-field Evolution of Physical Dynamics from Irregular Sp
        87226, -- Fairness-aware Bayes Optimal Functional Classification
        87347, -- Regression Trees Know Calculus
        87353, -- Uncertainty Estimation on Graphs with Structure Informed Stochastic Pa
        88834, -- From Kernels to Features: A Multi-Scale Adaptive Theory of Feature Lea
        89051, -- Diffusion models for Gaussian distributions: Exact solutions and Wasse
        89333, -- Stream-level Flow Matching with Gaussian Processes
        89573, -- Arbitrarily-Conditioned Multi-Functional Diffusion for Multi-Physics E
        90040, -- Identifying Causal Direction via Variational Bayesian Compression
        91073, -- Comparing noisy neural population dynamics using optimal transport dis
        91180, -- When narrower is better: the narrow width limit of Bayesian parallel b
        91537, -- Flow Matching with Gaussian Process Priors for Probabilistic Time Seri
        91716, -- Diffusion Transformer Captures Spatial-Temporal Dependencies: A Theory
        91903, -- Deep Random Features for Scalable Interpolation of Spatiotemporal Data
        91961, -- Causal Discovery via Bayesian Optimization
        91971, -- Variance-Reducing Couplings for Random Features
        92028, -- Deep Kernel Posterior Learning under Infinite Variance Prior Weights
        92204, -- A Unified Theory of Quantum Neural Network Loss Landscapes
        92309, -- Bayesian Optimization via Continual Variational Last Layer Training
        92415, -- PABBO: Preferential Amortized Black-Box Optimization
        93294, -- DeNOTS: Stable Deep Neural ODEs for Time Series
        93397, -- Reliable Probabilistic Forecasting of Irregular Time Series through Ma
        94260, -- Slicing Wasserstein over Wasserstein via Functional Optimal Transport
        94522, -- Scalable Random Wavelet Features: Efficient Non-Stationary Kernel Appr
        94687, -- Physics-Informed Inference Time Scaling for Solving High-Dimensional P
        95444, -- Hierarchical Online Learning for Adaptive Sampling of Discrete Species
        95450, -- Learning Constraint-Aware Dynamical Systems from Human Demonstrations
        99421, -- A Decision-Theoretic View of Test-Time Training: When, How Far, and Wh
        99638, -- Bayesian-LoRA: Probabilistic Low-Rank Adaptation of Large Language Mod
        99840, -- Random Process Flow Matching: Generative Implicit Representations of M
        100410, -- Bayesian Rain Field Reconstruction using Commercial Microwave Links an
        100511, -- BALLAST: Bayesian Active Learning with Look-ahead Amendment for Sea-dr
        101591, -- Dynamics of neural scaling laws in random feature regression with powe
        101947, -- Well-Posed KL-Regularized Control via Wasserstein and Kalman–Wasserste
        102061, -- Foundation Inference Models for Ordinary Differential Equations
        107501, -- RGMP: Recurrent Geometric-prior Multimodal Policy for Generalizable Hu
        121541 -- SPOT: Spatiotemporal Prompt Optimization for Motion-Stabilized MLLM-Gu
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'Gaussian process regression curation 2026-10-15: mentions Gaussian processes without fitting GP regression'
FROM gaussian_process_regression_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING gaussian_process_regression_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING gaussian_process_regression_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
