-- Particle filtering has no single uncontested introducing paper (Gordon et al.
-- 1993, Kitagawa and Del Moral developed it in parallel), and none has a local
-- paper row. The source is the Gordon et al. bootstrap-filter paper, introduced_year
-- stays NULL, and papers are linked from a reviewed set.

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
    'particle-filter',
    'Particle Filter',
    'Particle Filter (Sequential Monte Carlo)',
    'A particle filter, or sequential Monte Carlo (SMC) method, estimates the evolving posterior distribution over the hidden state of a dynamical system from noisy observations by representing it with a set of weighted samples, or particles. At each time step, particles are propagated through the transition model, reweighted by the likelihood of the new observation, and resampled in proportion to their weights so that computation concentrates on probable states and weight degeneracy is avoided. Unlike the Kalman filter, particle filters handle nonlinear dynamics and non-Gaussian, multimodal posteriors. The bootstrap filter of Gordon, Salmond and Smith (1993) and Kitagawa''s Monte Carlo filter are the classic formulations. Particle filters are standard for visual tracking, robot localization (Monte Carlo localization), [SLAM](/methods/slam) and state-space inference, and SMC is increasingly used to steer or constrain sampling from language and diffusion models.',
    'particle filter, particle filtering, sequential monte carlo',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://doi.org/10.1049/ip-f-2.1993.0015',
    'Novel approach to nonlinear/non-Gaussian Bayesian state estimation (Gordon, Salmond & Smith, 1993)',
    'https://github.com/rlabbe/filterpy/blob/master/filterpy/monte_carlo/resampling.py',
    NULL,
    NULL
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

-- Curated 2026-10-15 from every title/abstract mention of particle filters or sequential Monte Carlo: each paper below uses, extends or analyzes particle filtering / SMC.
CREATE TEMP TABLE particle_filter_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'particle-filter'
  AND p.id IN (
        1737, -- Learning Nonlinear State Space Models with Hamiltonian Sequential Mont
        6384, -- BeatNet: CRNN and Particle Filtering for Online Joint Beat Downbeat an
        6933, -- Divide-and-Conquer Fusion
        12286, -- State and parameter learning with PaRIS particle Gibbs
        16989, -- Sequential Monte Carlo Steering of Large Language Models using Probabi
        17918, -- Practical and Asymptotically Exact Conditional Sampling in Diffusion M
        22757, -- On Feynman--Kac training of partial Bayesian neural networks
        24568, -- Learning Differentiable Particle Filter on the Fly
        24572, -- Correcting Diffusion Generation through Resampling
        26580, -- Uncertainty-Aware Guidance for Target Tracking subject to Intermittent
        30830, -- Probabilistic Inference in Language Models via Twisted Sequential Mont
        40311, -- Time is on my sight: scene graph filtering for dynamic environment per
        41334, -- Bayesian Optimization of Antibodies Informed by a Generative Model of
        45434, -- Feynman-Kac Correctors in Diffusion: Annealing, Guidance, and Product
        47390, -- Fast Controlled Generation from Language Models with Adaptive Weighted
        50375, -- Psi-Sampler: Initial Particle Sampling for SMC-Based Inference-Time Re
        52995, -- Finding 3D Positions of Distant Objects from Noisy Camera Movement and
        55793, -- Self-Rewarding Sequential Monte Carlo for Masked Diffusion Language Mo
        65091, -- PALMS+: Modular Image-Based Floor Plan Localization Leveraging Depth F
        66887, -- Mitigating Premature Exploitation in Particle-based Monte Carlo for In
        72165, -- Syntactic Control of Language Models by Posterior Inference
        74613, -- Composition and Control with Distilled Energy Diffusion Models and Seq
        75999, -- PALMS: Plane-based Accessible Indoor Localization Using Mobile Smartph
        79628, -- MidasTouch: Monte-Carlo inference over distributions across sliding to
        82696, -- Adaptive sequential Monte Carlo by means of mixture of experts
        85923, -- Learning Latent Variable Models via Jarzynski-adjusted Langevin Algori
        86544, -- Reverse Diffusion Sequential Monte Carlo Samplers
        86564, -- RETRO SYNFLOW: Discrete Flow-Matching for Accurate and Diverse Single-
        86959, -- Sequential Monte Carlo for Policy Optimization in Continuous POMDPs
        87167, -- ProSpero: Active Learning for Robust Protein Design Beyond Wild-Type N
        88201, -- LoD-Loc v2: Aerial Visual Localization over Low Level-of-Detail City M
        89430, -- Inverse Problem Sampling in Latent Space Using Sequential Monte Carlo
        89776, -- Tuning Sequential Monte Carlo Samplers via Greedy Incremental Divergen
        89844, -- Solving Linear-Gaussian Bayesian Inverse Problems with Decoupled Diffu
        89951, -- Trust-Region Twisted Policy Improvement
        91499, -- Sequential Controlled Langevin Diffusions
        91807, -- Step-by-Step Reasoning for Math Problems via Twisted Sequential Monte
        92416, -- Test-time Alignment of Diffusion Models without Reward Over-optimizati
        93758, -- Inference-Time Scaling of Discrete Diffusion Models via Importance Wei
        95176, -- A New Approach to Real-Time Odometry Calibration Using an Adaptive Par
        95353, -- Coupled Particle Filters for Robust Affordance Estimation
        95433, -- BEV-Patch-PF: Particle Filtering with BEV-Aerial Feature Matching for
        95483, -- Tightly Coupled Rao-Blackwellized Particle Filter for GNSS-Only Positi
        96564, -- Denoising Particle Filters: Learning State Estimation with Single-Step
        97193, -- View Synthesis and 6DoF Pose Estimation in mmWave Radar Neural Radianc
        97194, -- M-VTOP: Modular Visuo-Tactile Object Pose Estimation for High-Precisio
        97537, -- PLOP: Particle Filtering for Learning Object Physics from Robot Intera
        99228, -- Diffusion Differentiable Resampling
        99572, -- Twice Sequential Monte Carlo for Tree Search
        99666, -- SURGE: Approximation and Training Free Particle Filter for Diffusion S
        99668, -- Simple Approximation and Derivative Free Inference-Time Scaling for Di
        99670, -- On the Power of (Approximate) Reward Models for Inference-Time Scaling
        99782, -- Lookahead Path Likelihood Optimization for Diffusion LLMs
        99930, -- Mitigating Bias in Locally Constrained Decoding via Tractable Proposal
        100023, -- A Probabilistic Framework for LLM-Based Model Discovery
        100395, -- Reinforced Sequential Monte Carlo for Amortised Sampling
        100782, -- Particle-Guided Diffusion Models for Partial Differential Equations
        100931, -- SG2Loc: Sequential Visual Localization on 3D Scene Graphs
        101104, -- Agentic Monte Carlo: Simulating Reinforcement Learning for Black-Box A
        101758, -- Online Bayesian Experimental Design for Partially Observed Dynamical S
        101841, -- Efficient Stochastic Optimisation via Sequential Monte Carlo
        101981, -- Efficient Learning of Deep State Space Models via Importance Smoothing
        102369, -- Diamond Maps: Efficient Reward Alignment via Stochastic Flow Maps
        106313, -- Inference-Time Scaling of Diffusion Language Models via Trajectory Ref
        107709, -- More than Irrational: Modeling Belief-Biased Agents
        108694, -- Contrastive Distribution Matching for Amortized Sequential Monte Carlo
        110714, -- Resource-Rational Noisy-Channel Language Processing: Testing the Effec
        117119, -- The Unreasonable Effectiveness of Pre-Trained Features for Camera Pose
        122777 -- Sharpen Without Search: On-Policy Distillation of Sequence-Level Power
  );

DELETE FROM paper_method_exclusions x
USING particle_filter_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM particle_filter_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM particle_filter_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: particle filters or SMC appear only as a baseline, an inspiration or background.
CREATE TEMP TABLE particle_filter_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'particle-filter'
  AND p.id IN (
        2049, -- Localization, Detection and Tracking of Multiple Moving Sound Sources
        45024, -- Scalable Equilibrium Sampling with Sequential Boltzmann Generators
        49086, -- A*-Decoding: Token-Efficient Inference Scaling
        57187, -- GPA: Learning GUI Process Automation from Demonstrations
        67169, -- Kilometer-Scale GNSS-Denied UAV Navigation via Heightmap Gradients: A
        67758, -- DriftLite: Lightweight Drift Control for Inference-Time Scaling of Dif
        69197, -- Amortized Sampling with Transferable Normalizing Flows
        72283, -- Solving Inverse Problems via Diffusion-Based Priors: An Approximation-
        74644, -- Hypothesis-Driven Theory-of-Mind Reasoning for Large Language Models
        77313, -- Fleet of Agents: Coordinated Problem Solving with Large Language Model
        78201, -- A Metalearned Neural Circuit for Nonparametric Bayesian Inference
        86256, -- Progressive Inference-Time Annealing of Diffusion Models for Sampling
        88649, -- LEAPS: A discrete neural sampler via locally equivariant networks
        93750, -- CREPE: Controlling diffusion with REPlica Exchange
        97726, -- A Contact-Driven Framework for Manipulating in the Blind
        100410, -- Bayesian Rain Field Reconstruction using Commercial Microwave Links an
        100546, -- Effective Model Pruning : Measuring the Redundancy of Model Components
        101322, -- TFTF: Training-Free Targeted Flow for Conditional Sampling
        101741, -- Training-Free Bayesian Filtering with Generative Emulators
        102436, -- Lookahead Sample Reward Guidance for Test-Time Scaling of Diffusion Mo
        122408, -- Why Deterministic PRM Guidance Underperforms in Discrete Diffusion Rea
        123069 -- PreSTO: Predictive Subtree Prefetching for Fast LLM Power Sampling
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'Particle filter curation 2026-10-15: mentions particle filtering without using it'
FROM particle_filter_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING particle_filter_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING particle_filter_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
