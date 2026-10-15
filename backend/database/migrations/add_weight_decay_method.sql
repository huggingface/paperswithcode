-- Add weight decay method.
-- Weight decay has no single introducing paper: penalizing squared weights
-- goes back to ridge regression, and Hanson & Pratt (1988) and Krogh & Hertz
-- (1991) applied it to neural networks. The source is therefore the
-- Krogh & Hertz proceedings page and source_paper_id stays NULL.
--
-- The bare phrase "weight decay" is common in training details, so the
-- candidate set below was reviewed by hand and the negatives are written to
-- paper_method_exclusions so the daily keyword backfill does not relink them.

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
    'weight-decay',
    'Weight Decay',
    'Weight Decay',
    'Weight decay is a regularization technique that shrinks every weight toward zero at each training step, $\theta_{t+1} = \theta_t - \eta \nabla L(\theta_t) - \eta\lambda\theta_t$, which discourages large weights and improves generalization. For plain [SGD](/methods/sgd) it is equivalent to adding an L2 penalty $\tfrac{\lambda}{2}\lVert\theta\rVert^2$ to the loss, the same penalty used in ridge regression; Hanson & Pratt and Krogh & Hertz popularized it for neural networks around 1990. For adaptive optimizers such as [Adam](/methods/adam) the two differ, which led [Loshchilov & Hutter](/paper/1711.05101) to propose decoupled weight decay in [AdamW](/methods/adamw). In modern deep networks with normalization layers, weight decay mainly controls the effective learning rate and training dynamics rather than model capacity, and it is a key hyperparameter in large language model pre-training, grokking, and optimizers such as Lion and Muon.',
    'weight decay, weight-decay, decoupled weight decay',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://proceedings.neurips.cc/paper/1991/hash/8eefcfdf5990e441f0fb6f3fad709e21-Abstract.html',
    'A Simple Weight Decay Can Improve Generalization',
    'https://github.com/pytorch/pytorch/blob/main/torch/optim/sgd.py',
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

-- Curated 2026-10-15 from every title/abstract mention of "weight decay":
-- each paper below proposes, analyzes or tunes weight decay, or relies on it
-- as a component of its method.
CREATE TEMP TABLE weight_decay_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'weight-decay'
  AND p.id IN (
        762, -- On Calibration of Modern Neural Networks
        765, -- L2 Regularization versus Batch and Weight Normalization
        962, -- Decoupled Weight Decay Regularization
        1183, -- A disciplined approach to neural network hyper-parameters: Part 1 -- l
        1318, -- Layer rotation: a surprisingly powerful indicator of generalization in
        2144, -- Stochastic Gradient Methods with Layer-wise Adaptive Moments for Train
        2606, -- Global Sparse Momentum SGD for Pruning Very Deep Neural Networks
        4167, -- MEAL V2: Boosting Vanilla ResNet-50 to 80%+ Top-1 Accuracy on ImageNet
        5034, -- Understanding self-supervised Learning Dynamics without Contrastive Pa
        6410, -- Logit Attenuating Weight Normalization
        6906, -- Parallel Deep Neural Networks Have Zero Duality Gap
        8600, -- Fusing finetuned models for better pretraining
        8661, -- Regularization-based Pruning of Irrelevant Weights in Deep Neural Arch
        12487, -- Deep Learning Meets Sparse Regularization: A Signal Processing Perspec
        16343, -- Exploring Weight Balancing on Long-Tailed Recognition Problem
        16510, -- Disentanglement via Latent Quantization
        20895, -- Small-scale proxies for large-scale Transformer training instabilities
        21511, -- Why Do We Need Weight Decay in Modern Deep Learning?
        21661, -- Lion Secretly Solves Constrained Optimization: As Lyapunov Predicts
        22252, -- To grok or not to grok: Disentangling generalization and memorization
        24057, -- Dichotomy of Early and Late Phase Implicit Biases Can Provably Induce
        26028, -- Critical Data Size of Language Models from a Grokking Perspective
        31473, -- FAdam: Adam is a natural gradient optimizer using diagonal empirical F
        34576, -- BitNet b1.58 Reloaded: State-of-the-art Performance Also on Smaller Ne
        37689, -- Composing Global Optimizers to Reasoning Tasks via Algebraic Objects i
        37860, -- How Much Can We Forget about Data Contamination?
        38573, -- The Fair Language Model Paradox
        41032, -- SoRA: Singular Value Decomposed Low-Rank Adaptation for Domain General
        44897, -- Muon is Scalable for LLM Training
        48100, -- OUI Need to Talk About Weight Decay: A New Perspective on Overfitting
        49089, -- Power Lines: Scaling Laws for Weight Decay and Batch Size in LLM Pre-t
        51963, -- Training Transformers with Enforced Lipschitz Constants
        53528, -- Cautious Weight Decay
        53665, -- Robust Layerwise Scaling Rules by Proper Weight Decay Tuning
        55157, -- Learnable Multipliers: Freeing the Scale of Language Model Matrix Laye
        56033, -- Weight Decay Improves Language Model Plasticity
        56212, -- On the Mechanism and Dynamics of Modular Addition: Fourier Features, L
        56755, -- When Does Sparsity Mitigate the Curse of Depth in LLMs
        58295, -- Correction of Decoupled Weight Decay
        58743, -- Rethinking Language Model Scaling under Transferable Hypersphere Optim
        60060, -- Scaling with Collapse: Efficient and Predictable Training of LLM Famil
        60420, -- Celo2: Towards Learned Optimization Free Lunch
        61218, -- Decoupled Orthogonal Dynamics: Regularization for Deep Network Optimiz
        62061, -- IMU-1: Sample-Efficient Pre-training of Small Language Models
        62777, -- How to Set the Learning Rate for Large-Scale Pre-training?
        65222, -- Can Training Dynamics of Scale-Invariant Neural Networks Be Explained
        66986, -- What Makes Diffusion Language Models Super Data Learners?
        67416, -- Efficient Hyperparameter Tuning via Trajectory Invariance Principle
        67770, -- Provable Scaling Laws of Feature Emergence from Learning Dynamics of G
        68209, -- Pre-training under infinite compute
        68766, -- The Optimiser Hidden in Plain Sight: Training with the Loss Landscape'
        74714, -- LoRA Training Provably Converges to a Low-Rank Global Minimum or It Fa
        79073, -- Multitask learning in Audio Captioning: a sentence embedding regressio
        82889, -- Prescriptive Scaling Laws for Data Constrained Training
        83806, -- Negligible in Size, Significant in Effect: On Scale Vectors in Large L
        85806, -- A Theoretical Framework for Grokking: Interpolation followed by Rieman
        85987, -- AlphaDecay: Module-wise Weight Decay for Heavy-Tailed Balancing in LLM
        87228, -- Understanding the Generalization of Stochastic Gradient Adam in Learni
        87387, -- Low Rank Gradients and Where to Find Them
        88853, -- Adaptive kernel predictors from feature-learning infinite limits of ne
        89546, -- Grokking Beyond the Euclidean Norm of Model Parameters
        89714, -- How to set AdamW's weight decay as you scale model and dataset size
        89901, -- Mirror, Mirror of the Flow: How Does Regularization Shape Implicit Bia
        91052, -- Wide Neural Networks Trained with Weight Decay Provably Exhibit Neural
        93047, -- Weight Decay may matter more than µP for Learning Rate Transfer in Pra
        93233, -- Optimizer Choice Matters For The Emergence of Neural Collapse
        93632, -- Completed Hyperparameter Transfer across Modules, Width, Depth, Batch
        93923, -- From Data Statistics to Feature Geometry: How Correlations Shape Super
        94047, -- Scaling Laws and Spectra of Shallow Neural Networks in the Feature Lea
        94067, -- How does the optimizer implicitly bias the model merging loss landscap
        94666, -- Never Saddle for Reparameterized Steepest Descent as Mirror Flow
        101076, -- To Grok Grokking: Provable Grokking in Ridge Regression
        101113, -- Lions and Muons: Optimization via Stochastic Frank-Wolfe under Heavy-T
        101591, -- Dynamics of neural scaling laws in random feature regression with powe
        101963, -- Ubiquity of Emergent Hebbian Dynamics in Regularized Learning
        102016, -- Quantifying LLM Attention-Head Stability: Implications for Circuit Uni
        102223, -- Disentangling Geometry, Performance, and Training in Language Models
        102481, -- Theoretical Analysis of Sparse Optimization with Reparameterization, W
        104413, -- The Geometry of Semantic Space: A Continuous Geometric Framework for t
        106549, -- Tuning for Two Adversaries: Enhancing the Robustness Against Transfer
        108326, -- FedAdamW: A Communication-Efficient Optimizer with Convergence and Gen
        111395, -- An Investigative Study on Recent Sharpness- and Flatness-Based Optimiz
        120332, -- Investigating the Role of Weight Decay in Enhancing Nonconvex SGD
        123168, -- The Life Cycle of a Massive Activation: Stochastic Birth, Weight-Decay
        123397 -- Scaling Repeated-Data Pretraining: Batch Size, Regularization, and GPU
  );

DELETE FROM paper_method_exclusions x
USING weight_decay_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM weight_decay_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM weight_decay_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: passing mentions, hyperparameter listings,
-- baseline-only comparisons, or unrelated "weight decay" (decaying sample,
-- loss, edge or reward weights).
CREATE TEMP TABLE weight_decay_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'weight-decay'
  AND p.id IN (
        1579, -- DropBlock: A regularization method for convolutional networks
        6329, -- Rethinking and Improving Relative Position Encoding for Vision Transfo
        10464, -- NAG-GS: Semi-Implicit, Accelerated and Robust Stochastic Optimizer
        13236, -- Revisiting Weighted Aggregation in Federated Learning with Neural Netw
        13661, -- Stabilizing Transformer Training by Preventing Attention Entropy Colla
        17871, -- Sparse Model Soups: A Recipe for Improved Pruning via Model Averaging
        18755, -- Effective Whole-body Pose Estimation with Two-stages Distillation
        24411, -- Understanding the Role of Optimization in Double Descent
        31331, -- LoRA Learns Less and Forgets Less
        33422, -- Policy Gradient-Driven Noise Mask
        46210, -- Understanding Gradient Orthogonalization for Deep Learning via Non-Euc
        58646, -- The Newton-Muon Optimizer
        59330, -- OrgForge: A Multi-Agent Simulation Framework for Verifiable Synthetic
        59848, -- MobileFetalCLIP: Selective Repulsive Knowledge Distillation for Mobile
        60671, -- OR-Agent: Bridging Evolutionary Search and Structured Research for Aut
        71991, -- GrokAlign: Geometric Characterisation and Acceleration of Grokking
        72053, -- PyLO: Towards Accessible Learned Optimizers in PyTorch
        85863, -- Learning in Compact Spaces with Approximately Normalized Transformer
        87662, -- Local Dense Logit Relations for Enhanced Knowledge Distillation
        89870, -- M³HF: Multi-agent Reinforcement Learning from Multi-phase Human Feedba
        91844, -- For Better or For Worse? Learning Minimum Variance Features With Label
        94820, -- The Rank and Gradient Lost in Non-stationarity: Sample Weight Decay fo
        98033, -- Content-Aware Frequency Encoding for Implicit Neural Representations w
        98069, -- FORGE — Continual Learning for fMRI-Based Brain Disorder Diagnosis (Au
        99842, -- The Stability of Singular Distribution: A Spectral Perspective on the
        101916, -- Who Gets Credit or Blame? Attributing Accountability in Modern AI Syst
        102092, -- Correctness-Optimized Residual Activation Lens (CORAL): Transferrable
        108955, -- Modular TTT: Rethinking Test-Time Training as Composable Modules
        109061, -- Omega-S: A Functional Resilience Index for LLM Fine-Tuning
        109767 -- WarpSAC: Towards the Pinnacle of Scalable Off-policy RL by Rethinking
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'Weight decay curation 2026-10-15: mentions weight decay without using or studying it'
FROM weight_decay_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING weight_decay_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING weight_decay_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
