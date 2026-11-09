-- Chat lookup-miss taxonomy gap fill (2026-11-09 audit): 6 learning methods.
-- GAIL has an introducing paper (arXiv 1606.03476). Pseudo-labeling, TCN, 3D
-- convolution, backpropagation and ERM have contested or pre-arXiv origins, so
-- they keep source_paper_id NULL (see add_neural_architecture_search_method.sql)
-- and their paper links below are reviewed title/abstract candidates.
-- Hero images are imported separately with import_entity_image.py.
--
-- Keywords avoid bare abbreviations that are case-sensitive substrings in the
-- keyword backfill: "GAIL" (NationalGAILab URLs), "TCN" (STCN, TCNN), "ERM"
-- (HERMES, epiretinal membrane) and "BP".

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'gail',
    'GAIL',
    'Generative Adversarial Imitation Learning (GAIL)',
    'Generative Adversarial Imitation Learning (GAIL) learns a policy directly from expert demonstrations, without a reward signal, by casting [imitation learning](/methods/imitation-learning) as an adversarial game. A discriminator learns to tell expert state-action pairs from those produced by the policy, and the policy is updated with [TRPO](/paper/1502.05477) to fool it. This matches the expert''s state-action occupancy measure, as maximum-entropy inverse reinforcement learning does, but skips recovering an explicit cost function. The setup mirrors a [GAN](/methods/gan), with the policy as the generator. On MuJoCo control tasks GAIL reached near-expert performance from a few demonstrations where behavioral cloning fell short, and it underlies later adversarial imitation methods such as AIRL and InfoGAIL. Unlike [DAgger](/methods/dagger), it needs no interactive expert queries.',
    'generative adversarial imitation learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2016,
    (SELECT id FROM papers WHERE arxiv_id = '1606.03476'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Generative Adversarial Imitation Learning',
    'https://github.com/openai/imitation',
    NULL,
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'pseudo-labeling',
    'Pseudo-Labeling',
    'Pseudo-Labeling',
    'Pseudo-labeling is a semi-supervised learning technique that uses a model''s own predictions on unlabeled data as training targets: the most likely class, usually kept only above a confidence threshold, is treated as if it were a true label, and the model trains on labeled and pseudo-labeled examples together. Lee (2013) popularized the name for deep networks and related it to entropy minimization; training a classifier on its own predictions is much older. Modern methods combine it with consistency regularization and strong data augmentation, as in [FixMatch](/paper/2001.07685), with a separate teacher, as in [Noisy Student](/paper/1911.04252), and with corrections for confirmation bias ([Arazo et al.](/paper/1908.02983)). It is widely used in [semi-supervised learning](/methods/semi-supervised-learning), unsupervised domain adaptation, and label-efficient detection, segmentation and speech recognition. Pseudo-labeling is the labeling step; [self-training](/methods/self-training) is the broader loop that repeatedly retrains a model, often a student, on such labels.',
    'pseudo-labeling, pseudo-labelling, pseudo labeling, pseudo labelling, pseudo-label, pseudo label',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://storage.googleapis.com/kaggle-forum-message-attachments/8924/pseudo_label_final.pdf',
    'Pseudo-Label: The Simple and Efficient Semi-Supervised Learning Method for Deep Neural Networks',
    'https://github.com/google-research/remixmatch/blob/master/pseudo_label.py',
    NULL,
    NULL,
    'always',
    ARRAY['Pseudo-Label', 'Pseudo-Labelling']
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'temporal-convolutional-network',
    'Temporal Convolutional Network',
    'Temporal Convolutional Network (TCN)',
    'A Temporal Convolutional Network (TCN) models sequences with stacks of 1D [convolutions](/methods/convolution) over time instead of recurrence. Typical TCNs use causal convolutions, so each output depends only on past inputs, with dilations that grow exponentially with depth so the receptive field covers long histories in few layers, wrapped in [residual blocks](/methods/residual-block). Because all time steps are computed in parallel, TCNs train faster and more stably than [RNNs](/methods/rnn) and [LSTMs](/methods/lstm). [Lea et al.](/paper/1608.08242) introduced the name for encoder-decoder action segmentation models, and [Bai et al.](/paper/1803.01271) defined the generic causal, dilated architecture now usually meant by the term, which outperformed canonical recurrent networks across many sequence modeling benchmarks; both build on the dilated causal convolutions of [WaveNet](/methods/wavenet). TCNs are used for time-series forecasting, action segmentation, speech and audio processing, and EEG and sensor data.',
    'temporal convolutional network, temporal convolution network, temporal convolutional networks',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://github.com/locuslab/TCN',
    'TCN: Sequence Modeling Benchmarks and Temporal Convolutional Networks',
    'https://github.com/locuslab/TCN/blob/master/TCN/tcn.py',
    NULL,
    NULL,
    'judge',
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    '3d-convolution',
    '3D Convolution',
    '3D Convolutional Neural Network (3D CNN)',
    'A 3D convolution slides a three-dimensional kernel over a volume, either a space-time stack of video frames or volumetric data such as CT and MRI scans, so each output responds to patterns across all three dimensions at once. 3D convolutional neural networks (3D CNNs) stack such layers to learn spatiotemporal or volumetric features directly. Ji et al. (2013) applied 3D CNNs to human action recognition, and [C3D](/paper/1412.0767) showed that 3×3×3 kernels trained on large video datasets give strong generic video features. Later work inflated 2D ImageNet filters into 3D ([I3D](/paper/1705.07750)) and factorized 3D kernels into separate spatial and temporal convolutions ([R(2+1)D](/paper/1711.11248)) to cut cost. 3D convolution extends 2D [convolution](/methods/convolution) and is used for action recognition, video understanding, medical image segmentation and 3D shape analysis.',
    '3D convolution, 3D convolutional, 3D-convolution, 3D CNN, 3D-CNN, 3D ConvNet',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1109/TPAMI.2012.59',
    '3D Convolutional Neural Networks for Human Action Recognition',
    NULL,
    NULL,
    NULL,
    'always',
    ARRAY['3D CNN', '3D ConvNet', '3D Convolutional Neural Network']
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'backpropagation',
    'Backpropagation',
    'Backpropagation',
    'Backpropagation computes the gradient of a loss with respect to every weight of a neural network by applying the chain rule backward through the computation graph: a forward pass stores intermediate activations, and a backward pass propagates error signals from the output toward the inputs, so all gradients cost about as much as one extra forward pass. It is reverse-mode automatic differentiation applied to neural networks, and its gradients feed optimizers such as [gradient descent](/methods/gradient-descent), [SGD](/methods/sgd) and [Adam](/methods/adam). Linnainmaa (1970) described reverse-mode differentiation and Werbos (1974) proposed applying it to neural networks; Rumelhart, Hinton and Williams (1986) showed that it learns useful internal representations in multilayer networks, which made it the standard way to train them. [Backpropagation Through Time](/methods/backpropagation-through-time-bptt) unrolls recurrent networks to apply it across time steps. Research on backpropagation studies its memory cost, biologically plausible alternatives such as feedback alignment and forward-only learning, and zeroth-order substitutes.',
    'backpropagation, back-propagation, back propagation',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1038/323533a0',
    'Learning representations by back-propagating errors',
    NULL,
    NULL,
    NULL,
    'always',
    ARRAY['Back-propagation', 'Backprop']
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'empirical-risk-minimization',
    'Empirical Risk Minimization',
    'Empirical Risk Minimization (ERM)',
    'Empirical risk minimization (ERM) trains a model by choosing the parameters that minimize the average loss on the training sample, used as a stand-in for the expected loss (risk) under the unknown data distribution. Formalized by Vapnik in statistical learning theory, it is the objective behind standard supervised training with [SGD](/methods/sgd), and its generalization is analyzed through uniform convergence, VC dimension and Rademacher complexity; structural risk minimization adds a capacity penalty such as [weight decay](/methods/weight-decay). Many methods are defined against ERM: [mixup](/paper/1710.09412) trains on interpolated examples, [Invariant Risk Minimization](/paper/1907.02893) and distributionally robust optimization target out-of-distribution generalization, and [sharpness-aware minimization](/methods/sharpness-aware-minimization) seeks flat minima. Well-tuned ERM remains a strong baseline on domain generalization benchmarks.',
    'empirical risk minimization, empirical risk minimisation',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1109/72.788640',
    'An overview of statistical learning theory',
    NULL,
    NULL,
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

-- Introduced banner for GAIL.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'gail' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

-- Reviewed paper links (2026-11-09). Candidates: local citers of 1606.03476 for
-- GAIL, and bounded title/abstract regex matches for the other five methods.
-- Positives use, extend, analyze, survey or compare against the method;
-- reviewed negatives become durable exclusions so the keyword and reference
-- backfills do not re-link them.

-- gail: 37 links, 325 exclusions (15 added after the first hourly reference
-- backfill, which links OpenAlex citers beyond the Semantic Scholar set).
CREATE TEMP TABLE gail_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gail'
  AND p.id IN (
        397, -- 1606.03476 Generative Adversarial Imitation Learning
        2984, -- 2001.02792 On Computation and Generalization of Generative Adversarial Imitation
        3437, -- 2004.13796 TextGAIL: Generative Adversarial Imitation Learning for Text Generatio
        3835, -- 2006.16785 Lipschitzness Is All You Need To Tame Off-policy Generative Adversaria
        4028, -- 2008.06924 Inverse Reinforcement Learning with Natural Language Goals
        15178, -- 2305.02195 CALM: Conditional Adversarial Latent Models for Directable Virtual Cha
        15251, -- 2305.03286 Composite Motion Learning with Task Control
        15869, -- 2305.12633 Multi-task Hierarchical Adversarial Inverse Reinforcement Learning
        27776, -- 2402.14194 BeTAIL: Behavior Transformer Adversarial Imitation Learning from Human
        30286, -- 2404.08513 Adversarial Imitation Learning via Boosting
        31744, -- 2405.16194 Diffusion-Reward Adversarial Imitation Learning
        38094, -- 2410.06151 Quality Diversity Imitation Learning
        53750, -- 2510.19307 Unified Reinforcement and Imitation Learning for Vision-Language Model
        54174, -- 2511.10643 Black-Box On-Policy Distillation of Large Language Models
        60760, -- 2602.12155 FAIL: Flow Matching Adversarial Imitation Learning for Image Generatio
        76160, -- 2410.03847 Enhancing Inverse Reinforcement Learning through Encoding Dynamic Info
        77742, -- 2402.18294 Whole-body Humanoid Robot Locomotion with Human Reference
        79989, -- 2104.02180 AMP: Adversarial Motion Priors for Stylized Physics-Based Character Co
        90442, -- 2412.05334 Closed-Loop Supervised Fine-Tuning of Tokenized Traffic Models
        91237, -- 2410.13855 Diffusing States and Matching Scores: A New Framework for Imitation Le
        91297, -- 2411.07007 Non-Adversarial Inverse Reinforcement Learning via Successor Feature M
        91370, -- 2501.14856 Noise-conditioned Energy-based Annealed Rewards (NEAR): A Generative F
        92737, -- 2511.17879 Generative Adversarial Post-Training Mitigates Reward Hacking in Live
        93196, -- 2510.00922 On Discovering Algorithms for Adversarial Imitation Learning
        93451, -- 2510.09487 Near-Optimal Second-Order Guarantees for Model-Based Adversarial Imita
        93668, -- 2603.05440 Latent Wasserstein Adversarial Imitation Learning
        94841, -- 2507.21533 Model Predictive Adversarial Imitation Learning for Planning from Obse
        94870, -- 2510.06913 DecompGAIL: Learning Realistic Traffic Behaviors with Decomposed Multi
        96633, -- external EDAIL: Adversarial Imitation Learning Via Exploration-Driven Data Augm
        97163, -- 2505.18899 Beyond Domain Randomization: Event-Inspired Perception for Visually Ro
        97188, -- 2603.02783 Generative Adversarial Imitation Learning for Robot Swarms: Learning f
        101315, -- 2605.27095 Adversarial Dual On-Policy Distillation from Expressive Teacher
        101616, -- 2606.22056 Provably Efficient Policy-Reward Co-Pretraining for Adversarial Imitat
        102404, -- 2603.22713 Non-Adversarial Imitation Learning Provably Free of Compounding Errors
        104774, -- 2512.03028 SMP: Reusable Score-Matching Motion Priors for Physics-Based Character
        107367, -- 2511.15292 Adversarial Attack on Black-Box Multi-Agent by Adaptive Perturbation
        112263  -- 2505.04961 Physics-Based Motion Imitation with Adversarial Differential Discrimin
  );

DELETE FROM paper_method_exclusions x
USING gail_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gail_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM gail_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE gail_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gail'
  AND p.id IN (
        569, -- 1701.07274 Deep Reinforcement Learning: An Overview
        754, -- 1706.03741 Deep reinforcement learning from human preferences
        1107, -- 1802.05957 Spectral Normalization for Generative Adversarial Networks
        1117, -- 1802.07740 Machine Theory of Mind
        1124, -- 1802.08802 Reinforcement Learning on Web Interfaces Using Workflow-Guided Exploration
        1209, -- 1804.02717 DeepMimic: Example-Guided Deep Reinforcement Learning of Physics-Based
        1486, -- 1809.02627 Unity: A General Platform for Intelligent Agents
        1624, -- 1811.06521 Reward learning from human preferences and demonstrations in Atari
        1634, -- 1811.07871 Scalable agent alignment via reward modeling: a research direction
        1764, -- 1901.07186 Towards Learning to Imitate from a Single Video Demonstration
        1792, -- 1901.10995 Go-Explore: a New Approach for Hard-Exploration Problems
        1833, -- 1902.07742 From Language to Goals: Inverse Reinforcement Learning for Vision-Based
        2142, -- 1905.10987 Learning to Route in Similarity Graphs
        2259, -- 1906.05838 Goal-conditioned Imitation Learning
        82028, -- 1805.00909 Reinforcement Learning and Control as Probabilistic Inference: Tutorial
        2338, -- 1907.05600 Generative Modeling by Estimating Gradients of the Data Distribution
        2992, -- 2001.03653 Towards GAN Benchmarks Which Require Generalization
        3433, -- 2004.13529 Augmented Behavioral Cloning from Observation
        3806, -- 2006.14796 AvE: Assistance via Empowerment
        4770, -- 2012.11717 Social NCE: Contrastive Learning of Socially-aware Motion Representati
        4812, -- 2012.15375 Refine and Imitate: Reducing Repetition and Inconsistency in Persuasio
        5762, -- 2105.09637 Navigation Turing Test (NTT): Learning to Evaluate Human-Like Navigati
        6181, -- 2107.01969 The MineRL BASALT Competition on Learning from Human Feedback
        6385, -- 2108.03658 One-Shot Object Affordance Detection in the Wild
        6531, -- 2109.00527 Boosting Search Engines with Interactive Agents
        6633, -- 2109.06689 Reactive and Safe Road User Simulations using Neural Barrier Certifica
        7015, -- 2110.10819 Shaking the foundations: delusions in sequence models for interaction
        7180, -- 2111.04714 A Dataset Perspective on Offline Reinforcement Learning
        7185, -- 2111.04850 Dueling RL: Reinforcement Learning with Trajectory Preferences
        7234, -- 2111.08857 SEIHAI: A Sample-efficient Hierarchical AI for the MineRL Competition
        7372, -- 2112.00861 A General Language Assistant as a Laboratory for Alignment
        7804, -- 2201.12594 Robust Imitation Learning from Corrupted Demonstrations
        8090, -- 2202.13675 A Survey on Recent Advances and Challenges in Reinforcement Learning M
        8164, -- 2203.03580 The Unsurprising Effectiveness of Pre-Trained Vision Models for Contro
        8384, -- 2203.11932 Dataset Distillation by Matching Training Trajectories
        8402, -- 2203.12677 Vision-Based Manipulators Need to Also See from Their Hands
        9534, -- 2206.09328 A Survey on Model-based Reinforcement Learning
        9546, -- 2206.09674 EAGER: Asking and Answering Questions for Automatic Reward Shaping in
        9577, -- 2206.11251 Behavior Transformers: Cloning $k$ modes with one stone
        9586, -- 2206.11795 Video PreTraining (VPT): Learning to Act by Watching Unlabeled Online
        9653, -- 2206.15469 Watch and Match: Supercharging Imitation with Regularized Optimal Tran
        9850, -- 2207.10148 Learning Deformable Object Manipulation from Expert Demonstrations
        9932, -- 2207.14299 Graph Inverse Reinforcement Learning from Diverse Videos
        10201, -- 2209.00796 Diffusion Models: A Comprehensive Survey of Methods and Applications
        10424, -- 2209.13224 Regularized Soft Actor-Critic for Behavior Transfer Learning
        10538, -- 2210.01379 Extraneousness-Aware Imitation Learning
        10763, -- 2210.06518 Semi-Supervised Offline Reinforcement Learning with Action-Free Trajec
        10817, -- 2210.07658 Abstract-to-Executable Trajectory Translation for One-Shot Task Genera
        10820, -- 2210.07765 Activity-aware Human Mobility Prediction with Hierarchical Graph Atten
        10880, -- 2210.10047 From Play to Policy: Conditional Behavior Generation from Uncurated Ro
        10905, -- 2210.10595 DIAMBRA Arena: a New Reinforcement Learning Platform for Research and
        11200, -- 2211.01724 Learning Control by Iterative Inversion
        11318, -- 2211.06839 Out-of-Dynamics Imitation Learning from Multimodal Demonstrations
        11662, -- 2211.15457 Hypernetworks for Zero-shot Transfer in Reinforcement Learning
        11918, -- 2212.05698 MoDem: Accelerating Visual Model-Based Reinforcement Learning with Dem
        12187, -- 2212.11419 Imitation Is Not Enough: Robustifying Imitation with Reinforcement Lea
        12212, -- 2212.12669 On Realization of Intelligent Decision-Making in the Real World: A Fou
        12521, -- 2301.10677 Imitating Human Behaviour with Diffusion Models
        12551, -- 2301.11270 Principled Reinforcement Learning with Human Feedback from Pairwise or
        12795, -- 2302.01399 Accelerating Policy Gradient by Estimating Value Function from Prior C
        13157, -- 2302.08560 Dual RL: Unification and New Methods for Reinforcement and Imitation L
        13551, -- 2303.04129 Foundation Models for Decision Making: Problems, Methods, and Opportun
        13556, -- 2303.04212 ConBaT: Control Barrier Transformer for Safe Policy Learning
        14094, -- 2303.13971 Optimal Transport for Offline Imitation Learning
        14141, -- 2303.14623 Inverse Reinforcement Learning without Reinforcement Learning
        14182, -- 2303.15349 Information Maximizing Curriculum: A Curriculum-Based Approach for Imi
        14290, -- 2303.17156 MAHALO: Unifying Offline Reinforcement Learning and Imitation Learning
        14354, -- 2304.00046 Accelerating exploration and representation learning with offline pre-
        14373, -- 2304.00464 UniDexGrasp++: Improving Dexterous Grasping Policy Learning via Geomet
        14477, -- 2304.02532 Goal-Conditioned Imitation Learning using Score-based Diffusion Polici
        14536, -- 2304.03833 Learning Robot Manipulation from Cross-Morphology Demonstration
        14650, -- 2304.06094 Energy-guided Entropic Neural Optimal Transport
        14809, -- 2304.09825 Using Offline Data to Speed Up Reinforcement Learning in Procedurally
        15073, -- 2305.00303 A Coupled Flow Approach to Imitation Learning
        15223, -- 2305.02857 Maximum Causal Entropy Inverse Constrained Reinforcement Learning
        15747, -- 2305.11290 Massively Scalable Inverse Reinforcement Learning in Google Maps
        16219, -- 2305.15193 Adaptive Policy Learning to Additional Tasks
        16290, -- 2305.15930 End-to-End Meta-Bayesian Optimisation with Transformer Neural Processe
        16449, -- 2305.17625 Cross-Domain Policy Adaptation via Value-Guided Data Filtering
        16504, -- 2305.18341 Coarse-Tuning Models of Code with Reinforcement Learning Feedback
        16760, -- 2306.00629 Identifiability and Generalizability in Constrained Inverse Reinforcem
        17189, -- 2306.05426 SequenceMatch: Imitation Learning for Autoregressive Sequence Modellin
        17460, -- 2306.09082 Behavioral Cloning via Search in Embedded Demonstration Dataset
        17764, -- 2306.14534 CEIL: Generalized Contextual Imitation Learning
        17882, -- 2306.16927 End-to-end Autonomous Driving: Challenges and Frontiers
        17999, -- 2307.01849 Crossway Diffusion: Improving Diffusion-based Visuomotor Policy via Se
        18452, -- 2307.10710 Reparameterized Policy Learning for Multimodal Trajectory Optimization
        18599, -- 2307.13101 Contrastive Example-Based Control
        18946, -- 2308.02585 PARL: A Unified Framework for Policy Alignment in Reinforcement Learni
        19403, -- 2308.09387 Multi-Level Compositional Reasoning for Interactive Instruction Follow
        19749, -- 2308.12952 BridgeData V2: A Dataset for Robot Learning at Scale
        20022, -- 2309.00711 Learning Shared Safety Constraints from Multi-task Demonstrations
        20341, -- 2309.06553 Query-Dependent Prompt Evaluation and Optimization with Offline Invers
        21209, -- 2310.01045 Tool-Augmented Reward Modeling
        21289, -- 2310.01737 Blending Imitation and Reinforcement Learning for Robust Policy Improv
        21386, -- 2310.02902 Searching for High-Value Molecules Using Reinforcement Learning and Tr
        21420, -- 2310.03173 $\mathcal{B}$-Coder: Value-Based Deep Reinforcement Learning for Progr
        21617, -- 2310.05422 Reward-Consistent Dynamics Models are Strongly Generalizable for Offli
        21686, -- 2310.06147 Reinforcement Learning in the Era of LLMs: What is Essential? What is
        21687, -- 2310.06171 Memory-Consistent Neural Networks for Imitation Learning
        21793, -- 2310.07433 Imitation Learning from Observation with Automatic Discount Scheduling
        21836, -- 2310.07899 RoboCLIP: One Demonstration is Enough to Learn Robot Policies
        22228, -- 2310.12931 Eureka: Human-Level Reward Design via Coding Large Language Models
        22422, -- 2310.15145 Robot Fine-Tuning Made Easy: Pre-Training Rewards and Policies for Aut
        22667, -- 2310.18247 Guided Data Augmentation for Offline Reinforcement Learning and Imitat
        22793, -- 2310.20141 Contrastive Difference Predictive Coding
        23636, -- 2311.12996 RLIF: Interactive Imitation Learning as Reinforcement Learning
        23874, -- 2311.16714 Embodied Multi-Modal Agent trained by an LLM from a Parallel TextWorld
        24211, -- 2312.01957 Distilled Self-Critique of LLMs with Synthetic Data: a Bayesian Perspe
        24219, -- 2312.02019 Action Inference by Maximising Evidence: Zero-Shot Imitation from Obse
        24763, -- 2312.08782 Toward General-Purpose Robots via Foundation Models: A Survey and Meta
        25414, -- 2401.01335 Self-Play Fine-Tuning Converts Weak Language Models to Strong Language
        25540, -- 2401.03306 MOTO: Offline Pre-training to Online Fine-tuning for Model-based Robot
        26442, -- 2401.16444 Enhancing Human Experience in Human-Agent Collaboration: A Human-Cente
        26881, -- 2402.03681 RL-VLM-F: Reinforcement Learning from Vision Language Foundation Model
        26899, -- 2402.03807 SEABO: A Simple Search-Based Method for Offline Imitation Learning
        26941, -- 2402.04292 AdaFlow: Imitation Learning with Variance-Adaptive Flow-Based Policies
        27163, -- 2402.07127 Learning by Watching: A Review of Video-based Learning Approaches for
        27839, -- 2402.14807 A Decision-Language Model (DLM) for Dynamic Restless Multi-Armed Bandi
        28440, -- 2403.03181 Behavior Generation with Latent Actions
        28441, -- 2403.03185 Correlated Proxies: A New Definition and Improved Mitigation for Rewar
        29061, -- 2403.12017 Supervised Fine-Tuning as Inverse Reinforcement Learning
        29123, -- 2403.12835 AnySkill: Learning Open-Vocabulary Physical Skill for Interactive Agen
        30786, -- 2404.16779 DrS: Learning Reusable Dense Rewards for Multi-Stage Tasks
        30898, -- 2404.18896 Overcoming Knowledge Barriers: Online Imitation Learning from Observat
        31553, -- 2405.14093 A Survey on Vision-Language-Action Models for Embodied AI
        31704, -- 2405.15624 Inverse-RLignment: Large Language Model Alignment from Demonstrations
        32202, -- 2406.00888 Aligning Language Models with Demonstrated Feedback
        32420, -- 2406.04144 Redundancy-aware Action Spaces for Robot Learning
        32441, -- 2406.04274 Self-Play with Adversarial Critic: Provable and Scalable Offline Align
        33539, -- 2406.16087 Imperative Learning: A Self-supervised Neuro-Symbolic Learning Framewo
        34228, -- 2407.04856 Explorative Imitation Learning: A Path Signature Approach for Continuo
        34539, -- 2407.09024 Aligning Diffusion Behaviors with Q-functions for Efficient Continuous
        34634, -- 2407.10341 Affordance-Guided Reinforcement Learning via Visual Prompting
        34669, -- 2407.10839 Offline Reinforcement Learning with Imputed Rewards
        35476, -- 2408.01072 A Survey on Self-play Methods in Reinforcement Learning
        35731, -- 2408.05804 A Single Goal is All You Need: Skills and Exploration Emerge from Cont
        36292, -- 2408.15270 SkillMimic: Learning Basketball Interaction Skills from Demonstrations
        36485, -- 2409.01083 Affordance-based Robot Manipulation with Flow Matching
        36504, -- 2409.01369 Imitating Language via Scalable Inverse Reinforcement Learning
        37648, -- 2410.01458 From Reward Shaping to Q-Shaping: Achieving Unbiased Learning with LLM
        37705, -- 2410.01968 Bi-Level Motion Imitation for Humanoid Robots
        37736, -- 2410.02231 SEAL: SEmantic-Augmented Imitation Learning via Language Model
        37859, -- 2410.03246 Latent Action Priors for Locomotion with Deep Reinforcement Learning
        38821, -- 2410.14660 A Large Language Model-Driven Reward Design Framework via Dynamic Feed
        39065, -- 2410.18065 SPIRE: Synergistic Planning, Imitation, and Reinforcement Learning for
        39563, -- 2411.01349 The Role of Domain Randomization in Training Diffusion Policies for Wh
        39783, -- 2411.05273 Real-World Offline Reinforcement Learning from Vision Language Model F
        40211, -- 2411.13451 AdaptAgent: Adapting Multimodal Web Agents with Few-Shot Learning from
        41180, -- 2412.05718 RLZero: Direct Policy Inference from Language Without In-Domain Superv
        41214, -- 2412.06207 Skill-Enhanced Reinforcement Learning Acceleration from Demonstrations
        42326, -- 2501.00078 Human-like Bots for Tactical Shooters Using Compute-Efficient Sensors
        43663, -- 2502.02508 Satori: Reinforcement Learning with Chain-of-Action-Thought Enhances L
        43704, -- 2502.03369 Learning from Active Human Involvement through Proxy Value Propagation
        44500, -- 2502.13006 Integrating Reinforcement Learning, Action Model Learning, and Numeric
        45558, -- 2503.04679 Multi-Agent Inverse Q-Learning from Demonstrations
        45894, -- 2503.08604 EMMOE: A Comprehensive Benchmark for Embodied Mobile Manipulation in O
        46163, -- 2503.11646 Adversarial Data Collection: Human-Collaborative Perturbations for Eff
        48349, -- 2505.01619 Skill-based Safe Reinforcement Learning with Risk Planning
        48370, -- 2505.02094 SkillMimic-V2: Learning Robust and Generalizable Interaction Skills fr
        48598, -- 2505.06584 JAEGER: Dual-Level Humanoid Whole-Body Controller
        48838, -- 2505.11146 X2C: A Dataset Featuring Nuanced Facial Expressions for Realistic Huma
        50642, -- 2506.05294 A Smooth Sea Never Made a Skilled $\texttt{SAILOR}$: Robust Imitation
        51722, -- 2507.05197 Pre-Trained Policy Discriminators are General Reward Models
        51953, -- 2507.13158 Inverse Reinforcement Learning Meets Large Language Model Post-Trainin
        52090, -- 2507.21045 Reconstructing 4D Spatial Intelligence: A Survey
        55542, -- 2601.19897 Self-Distillation Enables Continual Learning
        56244, -- 2602.19313 TOPReward: Token Probabilities as Hidden Zero-Shot Rewards for Robotic
        56417, -- 2602.24121 Planning from Observation and Interaction
        60015, -- 2603.02139 Rethinking Camera Choice: An Empirical Study on Fisheye Camera Propert
        60018, -- 2603.02115 Robometer: Scaling General-Purpose Robotic Reward Models via Trajector
        60135, -- 2603.00825 COMBAT: Conditional World Models for Behavioral Agent Training
        61399, -- 2602.02710 Maximum Likelihood Reinforcement Learning
        61788, -- 2601.21968 OVD: On-policy Verbal Distillation
        62416, -- 2601.11421 The Great March 100: 100 Detail-oriented Tasks for Evaluating Embodied
        62577, -- 2601.08731 Learning from Demonstrations via Capability-Aware Goal Sampling
        63030, -- 2601.01743 AI Agent Systems: Architectures, Applications, and Evaluation
        64263, -- 2512.01809 Much Ado About Noising: Dispelling the Myths of Generative Robotic Con
        64596, -- 2511.19584 Learning Massively Multitask World Models for Continuous Control
        65930, -- 2510.21090 Self-Rewarding PPO: Aligning Large Language Models with Demonstrations
        67121, -- 2510.01857 Learning Reasoning Reward Models from Expert Demonstration via Inverse
        67872, -- 2509.20021 Embodied AI: From LLMs to World Models
        69684, -- 2508.10399 Large Model Empowered Embodied AI: A Survey on Decision-Making and Emb
        70013, -- 2508.05941 Latent Policy Barrier: Learning Robust Visuomotor Policies by Staying
        71976, -- 2507.00018 Implicit Reward as the Bridge: A Unified View of SFT and DPO Connectio
        73049, -- 2505.10911 ReWiND: Language-Guided Rewards Teach Robot Policies without New Demon
        73634, -- 2504.06141 Adversarial Training of Reward Models
        75854, -- 2411.04005 Object-Centric Dexterous Manipulation from Human Motion Data
        76044, -- 2410.22355 Learning Goal-oriented Bimanual Dough Rolling Using Dynamic Heterogene
        76135, -- 2410.05547 Understanding and Imitating Human-Robot Motion with Restricted Visual
        76687, -- 2402.10885 3D Diffuser Actor: Policy Diffusion with 3D Scene Representations
        77033, -- 2406.07541 CDSA: Conservative Denoising Score-based Algorithm for Offline Reinfor
        77059, -- 2406.05427 Decision Mamba: A Multi-Grained State Space Model with Self-Evolution
        77135, -- 2405.20579 HOPE: A Reinforcement Learning-based Hybrid Policy Path Planner for Di
        77801, -- 2402.11367 Multi Task Inverse Reinforcement Learning for Common Sense Reward
        78076, -- 2312.10807 Language-conditioned Learning for Robotic Manipulation: A Survey
        78204, -- 2311.14379 Robot Learning in the Era of Foundation Models: A Survey
        78354, -- 2310.12972 CCIL: Continuity-based Data Augmentation for Corrective Imitation Lear
        78453, -- 2309.17046 CrossLoco: Human Motion Driven Control of Legged Robots via Guided Uns
        78975, -- 2305.16985 Inverse Dynamics Pretraining Learns Good Representations for Multitask
        78988, -- 2305.15363 Inverse Preference Learning: Preference-based RL without a Reward Func
        79580, -- 2211.06665 A Survey on Explainable Reinforcement Learning: Concepts, Algorithms,
        79908, -- 2206.04873 Imitation Learning via Differentiable Physics
        80142, -- 2203.07092 The Multi-Agent Pickup and Delivery Problem: MAPF, MARL and Its Wareho
        80489, -- 2109.13396 Bridge Data: Boosting Generalization of Robotic Skills with Cross-Doma
        81276, -- 2006.04021 Skill Discovery of Coordination in Multi-agent Reinforcement Learning
        81458, -- 2002.00444 Deep Reinforcement Learning for Autonomous Driving: A Survey
        81567, -- 1910.06658 Topological Navigation Graph Framework
        82899, -- 2605.00623 Recovering Hidden Reward in Diffusion-Based Policies
        83991, -- 2503.10626 NIL: No-data Imitation Learning
        85113, -- 2603.25199 TacSIm: A Dataset and Benchmark for Football Tactical Style Imitation
        85202, -- 2603.29272 MaskAdapt: Learning Flexible Motion Adaptation via Mask-Invariant Prio
        86231, -- 2505.18595 MisoDICE: Multi-Agent Imitation from Mixed-Quality Demonstrations
        86819, -- 2510.01545 Predictive Preference Learning from Human Interventions
        86937, -- 2509.22807 MTRec: Learning to Align with User Preferences via Mental Reward Model
        87253, -- 2506.08822 FreqPolicy: Efficient Flow-based Visuomotor Policy via Frequency Consi
        87449, -- 2503.14259 Quantization-Free Autoregressive Action Transformer
        87617, -- 2507.04331 Wavelet Policy: Lifting Scheme for Policy Learning in Long-Horizon Tas
        87789, -- 2411.17764 PROGRESSOR: A Perceptually Guided Reward Estimator with Self-Supervise
        88127, -- 2508.11049 GenFlowRL: Shaping Rewards with Generative Object-Centric Flow in Visu
        88211, -- 2503.09186 Rethinking Bimanual Robotic Manipulation: Learning with Decoupled Inte
        88664, -- 2507.10539 Graph World Model
        88944, -- 2506.21121 GoIRL: Graph-Oriented Inverse Reinforcement Learning for Multimodal Tr
        89011, -- 2501.18528 Joint Learning of Energy-based Models and their Partition Function
        89082, -- 2410.08751 Zero-Shot Offline Imitation Learning via Optimal Transport
        89401, -- 2506.12822 Enhancing Rating-Based Reinforcement Learning to Effectively Leverage
        89520, -- 2410.14081 Reward-free World Models for Online Imitation Learning
        89675, -- 2502.19859 IL-SOAR : Imitation Learning with Soft Optimistic Actor cRitic
        89840, -- 2503.01837 Multi-Stage Manipulation with Demonstration-Augmented Reward, Policy,
        89870, -- 2503.02077 M³HF: Multi-agent Reinforcement Learning from Multi-phase Human Feedba
        90021, -- 2503.06893 Policy Regularization on Globally Accessible States in Cross-Dynamics
        91081, -- 2412.08021 Can a MISL Fly? Analysis and Ingredients for Mutual Information Skill
        91187, -- 2410.13837 ORSO: Accelerating Reward Design via Online Reward Selection and Polic
        91191, -- 2502.02705 Rapidly Adapting Policies to the Real-World via Simulation-Guided Fine
        91233, -- 2503.13162 Efficient Imitation under Misspecification
        91364, -- 2503.05079 On a Connection Between Imitation Learning and RLHF
        91414, -- 2410.05782 Reinforcement Learning from Imperfect Corrective Actions and Proxy Rew
        91498, -- 2410.15910 Diverse Policies Recovering via Pointwise Mutual Information Weighted
        91635, -- 2408.03029 Highly Efficient Self-Adaptive Reward Shaping for Reinforcement Learni
        91757, -- 2412.13630 Policy Decorator: Model-Agnostic Online Refinement for Large Policy Mo
        91836, -- 2412.07544 Contractive Dynamical Imitation Policies for Efficient Out-of-Sample R
        91846, -- 2306.06394 PEAR: Primitive Enabled Adaptive Relabeling for Boosting Hierarchical
        91966, -- 2502.20630 Subtask-Aware Visual Reward Learning from Segmented Demonstrations
        92287, -- 2503.20105 Direct Post-Training Preference Alignment for Multi-Agent Motion Gener
        92345, -- 2410.05063 Control-oriented Clustering of Visual Latent Representation
        92400, -- 2412.09149 Student-Informed Teacher Training
        92429, -- 2407.08725 MetaUrban: An Embodied AI Simulation Platform for Urban Micromobility
        92801, -- 2602.01789 RFS: Reinforcement learning with Residual flow steering for dexterous
        92840, -- 2602.21020 Matching Multiple Experts: On the Exploitability of Multi-Agent Imitat
        92898, -- 2603.04861 Causally Robust Reward Learning from Reason-Augmented Preference Feedb
        92981, -- 2506.10085 VITA: Zero-Shot Value Functions via Test-Time Adaptation of Vision–Lan
        93021, -- 2503.00923 HWC-Loco: A Hierarchical Whole-Body Control Approach to Robust Humanoi
        93175, -- 2601.19452 APC-RL: Exceeding data-driven behavior priors with adaptive policy com
        93302, -- 2406.03862 Robust Deep Reinforcement Learning against Adversarial Behavior Manipu
        93702, -- 2502.07656 Causal Imitation Learning under Expert-Observable and Expert-Unobserva
        93935, -- 2510.02180 GRACE: A Language Model Framework for Explainable Inverse Reinforcemen
        93971, -- 2502.19544 Efficient Reinforcement Learning by Guiding World Models with Non-Cura
        93977, -- 2501.06376 Robustness in the Face of Partial Identifiability in Reward Learning
        94030, -- 2603.02008 Temporal Representations for Exploration: Learning Complex Exploratory
        94536, -- 2512.09101 Masked Generative Policy for Robotic Control
        94625, -- 2510.06203 Reference Grounded Skill Discovery
        94843, -- 2510.09096 When a Robot is More Capable than a Human: Learning from Constrained D
        95367, -- 2503.01439 AVR: Active Vision-Driven Precise Robot Manipulation with Viewpoint an
        95678, -- 2509.16136 Reward Evolution with Graph-Of-Thoughts: A Bi-Level Language Model Fra
        95764, -- 2603.14522 One-Policy-Fits-All: Geometry-Aware Action Latents for Cross-Embodimen
        96409, -- 2403.10996 Mixed-Reality Digital Twins: Leveraging the Physical and Virtual World
        96544, -- 2502.11161 BFA: Best-Feature-Aware Fusion for Multi-View Fine-Grained Manipulatio
        96638, -- 2509.25443 CoTaP: Compliant Task Pipeline and Reinforcement Learning of Its Contr
        96823, -- 2510.23576 UrbanVLA: A Vision-Language-Action Model for Urban Micromobility
        97088, -- 2601.01651 DemoBot: Efficient Learning of Bimanual Manipulation with Dexterous Ha
        97116, -- 2509.14159 MIMIC-D: Multi-Modal Imitation for MultI-Agent Coordination with Decen
        97348, -- 2507.11840 The Developments and Challenges towards Dexterous and Embodied Robotic
        97496, -- 2505.24266 SignBot: Learning Human-To-Humanoid Sign Language Interaction
        97538, -- 2603.28053 Reducing Oracle Feedback with Vision Language Embeddings for Preferenc
        97580, -- 2603.15179 KiRAS: Keyframe Guided Self-Imitation for Robust and Adaptive Skill Le
        97644, -- 2512.07041 CERNet: Class-Embedding Predictive-Coding RNN for Unified Robot Motion
        99471, -- 2505.20110 Beyond the Proxy: Trajectory-Distilled Guidance for Offline GFlowNet T
        99582, -- 2512.15605 Autoregressive Language Models are Secretly Energy-Based Models: Insig
        99881, -- 2605.20654 Reflector: Internalizing Step-wise Reflection against Indirect Jailbre
        100467, -- 2605.11020 Trust Region Inverse Reinforcement Learning: Explicit Dual Ascent usin
        100541, -- 2510.03013 Distributional Inverse Reinforcement Learning
        100812, -- 2511.21667 Escaping the Verifier: Learning to Reason via Demonstrations
        100909, -- 2509.22402 ReLAM: Learning Anticipation Model for Rewarding Visual Robotic Manipu
        100916, -- 2509.26627 TimeRewarder: Learning Dense Reward from Passive Videos via Frame-wise
        101163, -- 2512.16911 Posterior Behavioral Cloning: Pretraining BC Policies for Efficient RL
        101282, -- 2510.11499 Offline Reinforcement Learning with Generative Trajectory Policies
        101651, -- 2601.22823 Offline Reinforcement Learning of High-Quality Behaviors Under Robust
        101679, -- 2605.03357 Population-Aware Imitation Learning in Mean-field Games with Common No
        101813, -- 2602.22810 Multi-agent imitation learning with function approximation: linear Mar
        101915, -- 2510.17059 Consistent Zero-Shot Imitation with Contrastive Goal Inference
        101975, -- 2511.22888 Adversarial Training for Process Reward Models
        102259, -- 2604.25496 Improving Zero-Shot Offline RL via Behavioral Task Sampling
        102473, -- 2506.22578 The Hidden Link between RLHF and Contrastive Learning
        102654, -- 2607.01897 Rank-Then-Act: Reward-Free Control from Frame-Order Progress
        103834, -- 2607.06957 Flow-ERD: Agent-type Aware Flow Matching with Entropy-Regularized Dist
        103884, -- 1909.01387 Making Efficient Use of Demonstrations to Solve Hard Exploration Probl
        104788, -- 2604.24833 MotionBricks: Scalable Real-Time Motions with Modular Latent Generativ
        106982, -- 2512.19737 Simulation-Driven Railway Delay Prediction: An Imitation Learning Appr
        107055, -- 2504.05585 TW-CRL: Time-Weighted Contrastive Reward Learning for Efficient Invers
        107104, -- 2304.03535 CRISP: Curriculum-Inducing Primitive Informed Subgoal Prediction for B
        107298, -- 2511.07260 PADiff: Predictive and Adaptive Diffusion Policies for Ad Hoc Teamwork
        107333, -- 2505.20335 Language Model Distillation: A Temporal Difference Imitation Learning
        109025, -- 2608.09853 RynnValue: Scaling Robotic Value Foundation Models with Temporal Dista
        109772, -- 2608.25864 MA-VLA: Multi-Arm Vision-Language-Action Model for Collaboration and C
        110875, -- 2502.11918 VLP: Vision-Language Preference Learning for Embodied Manipulation
        113275, -- 2502.05641 Generating Physically Realistic and Directable Human Motions from Mult
        113413, -- 2407.15086 MaxMI: A Maximal Mutual Information Criterion for Manipulation Concept
        114256, -- 2406.01544 Validity Learning on Failures: Mitigating the Distribution Shift in Au
        114420, -- 2406.13165 Cardiac Copilot: Automatic Probe Guidance for Echocardiography with Wo
        115695, -- 2403.17601 LASIL: Learner-Aware Supervised Imitation Learning For Long-term Micro
        116090, -- 2312.11598 SkillDiffuser: Interpretable Hierarchical Planning via Skill Abstracti
        119721, -- 2308.09036 Synthesizing Physically Plausible Human Motions in 3D Scenes
        119821, -- 2309.07907 Physically Plausible Full-Body Hand-Object Interaction Synthesis
        123656, -- 2203.01577 HOI4D: A 4D Egocentric Dataset for Category-Level Human-Object Interac
        124170, -- 2610.14041 A Geometric Perspective on Reward Function Updates in Inverse Reinforc
        124980, -- 2509.10656 Self-Supervised Goal-Reaching Results in Multi-Agent Cooperation and E
        126276, -- 2601.00452 Imitation from Observations with Trajectory-Level Generative Embedding
        126304, -- 2605.03660 Stage Light is Sequence$^2$: Multi-Light Control via Imitation Learnin
        126551, -- 2605.12000 Split the Differences, Pool the Rest: Provably Efficient Multi-Objecti
        126670, -- 2602.06769 Soft Forward-Backward Representations for Zero-shot Reinforcement Lear
        127728, -- 2605.17017 When Dynamics Shift, Robust Task Inference Wins: Offline Imitation Lea
        127878, -- 2604.21177 Revisiting Subgradient Dominance in Robust MDPs: Counterexamples, Hard
        130463, -- 2602.04851 PDF-HR: Pose Distance Fields for Humanoid Robots
        130505, -- 2602.08689 Learning to Sample From Diffusion Models via Inverse Reinforcement Lea
        131179  -- 2509.21172 Inverse Reinforcement Learning with Just Classification and a Few Regr
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Taxonomy gap fill 2026-11-09: cites or names GAIL without using, extending or comparing adversarial imitation'
FROM gail_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING gail_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING gail_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- pseudo-labeling: 1065 links, 5 exclusions.
CREATE TEMP TABLE pseudo_labeling_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'pseudo-labeling'
  AND p.id IN (
        1290, -- 1805.07473 Progressive Ensemble Networks for Zero-Shot Recognition
        1664, -- 1811.12506 3D Semi-Supervised Learning with Uncertainty-Aware Multi-View Co-Train
        2166, -- 1905.13305 Countering Noisy Labels By Learning From Auxiliary Clean Labels
        2189, -- 1906.00817 Zero-Shot Semantic Segmentation
        2399, -- 1908.02983 Pseudo-Labeling and Confirmation Bias in Deep Semi-Supervised Learning
        2566, -- 1909.09116 Self-Training for End-to-End Speech Recognition
        2800, -- 1911.04252 Self-training with Noisy Student improves ImageNet classification
        2910, -- 1912.03330 ClusterFit: Improving Generalization of Visual Representations
        3157, -- 2003.00080 Transferring Dense Pose to Proximal Animal Classes
        3241, -- 2003.10580 Meta Pseudo Labels
        3697, -- 2006.06525 Attentive WaveBlock: Complementarity-enhanced Mutual Networks for Unsu
        3908, -- 2007.08702 DACS: Domain Adaptation via Cross-domain Mixed Sampling
        3912, -- 2007.09397 Weakly Supervised Instance Segmentation by Learning Annotation Consist
        4074, -- 2008.11702 Delving into Inter-Image Invariance for Unsupervised Visual Representa
        4128, -- 2009.05166 FILTER: An Enhanced Fusion Method for Cross-lingual Language Understan
        4206, -- 2009.12007 G-SimCLR: Self-Supervised Contrastive Learning with Guided Projection
        4406, -- 2010.11430 Self-training and Pre-training are Complementary for Speech Recognitio
        4414, -- 2010.11910 Neural Audio Fingerprint for High-specific Audio Retrieval based on Co
        4440, -- 2010.13002 Pre-trained Summarization Distillation
        4481, -- 2011.00362 A Survey on Contrastive Self-supervised Learning
        4574, -- 2011.09031 Predictions For Pre-training Language Models
        4680, -- 2012.03358 Select, Label, and Mix: Learning Discriminative Invariant Feature Repr
        4730, -- 2012.07177 Simple Copy-Paste is a Strong Data Augmentation Method for Instance Se
        4802, -- 2012.14584 Annotation-Efficient Learning for Medical Image Segmentation based on
        4876, -- 2101.03713 Learning from Weakly-labeled Web Videos via Exploring Sub-Concepts
        4907, -- 2101.06639 Removing Undesirable Feature Contributions Using Out-of-Distribution D
        5052, -- 2102.08602 LambdaNetworks: Modeling Long-Range Interactions Without Attention
        5589, -- 2104.12928 If your data distribution shifts, use self-learning
        5829, -- 2106.00168 Rethinking Pseudo Labels for Semi-Supervised Object Detection
        5853, -- 2106.01226 Semi-Supervised Semantic Segmentation with Cross Pseudo Supervision
        5885, -- 2106.02792 Weakly-Supervised Methods for Suicide Risk Assessment: Role of Related
        5947, -- 2106.05682 DASO: Distribution-Aware Semantics-Oriented Pseudo-label for Imbalance
        6019, -- 2106.09018 End-to-End Semi-Supervised Object Detection with Soft Teacher
        6149, -- 2106.15326 Source-free Domain Adaptation via Avatar Prototype Generation and Adap
        6270, -- 2107.08369 Flood Segmentation on Sentinel-1 SAR Imagery with Semi-Supervised Lear
        6286, -- 2107.10064 Few Shots Are All You Need: A Progressive Few Shot Learning Approach f
        6320, -- 2107.13389 SimROD: A Simple Adaptation Method for Robust Object Detection
        6416, -- 2108.06027 PAIR: Leveraging Passage-Centric Similarity Relation for Improving Den
        6444, -- 2108.08468 QUEACO: Borrowing Treasures from Weakly-labeled Behavior Data for Quer
        6489, -- 2108.11801 Unsupervised domain adaptation for clinician pose estimation and insta
        6736, -- 2109.13059 Trans-Encoder: Unsupervised sentence-pair modelling through self- and
        6965, -- 2110.08188 Guided Point Contrastive Learning for Semi-supervised Point Cloud Sema
        7081, -- 2110.15128 Contrast and Mix: Temporal Contrastive Video Domain Adaptation with Ba
        7104, -- 2111.00161 Pseudo-Labeling for Massively Multilingual Speech Recognition
        7301, -- 2111.12580 UDA-COPE: Unsupervised Domain Adaptation for Category-level Object Pos
        7305, -- 2111.12940 Towards Fewer Annotations: Active Learning via Region Impurity and Pre
        7340, -- 2111.14887 DAFormer: Improving Network Architectures and Training Strategies for
        7344, -- 2111.15242 ConDA: Unsupervised Domain Adaptation for LiDAR Segmentation via Regul
        7357, -- 2112.00065 Boosting EfficientNets Ensemble Performance via Pseudo-Labels and Synt
        7396, -- 2112.01790 SSDL: Self-Supervised Dictionary Learning
        7436, -- 2112.03865 Universalizing Weak Supervision
        7475, -- 2112.05749 Label, Verify, Correct: A Simple Few Shot Object Detection Method
        7497, -- 2112.07577 GPL: Generative Pseudo Labeling for Unsupervised Domain Adaptation of
        7562, -- 2112.09583 Align and Prompt: Video-and-Language Pre-training with Entity Prompts
        7685, -- 2201.04620 SparseDet: Improving Sparsely Annotated Object Detection with Pseudo-p
        7839, -- 2202.00796 On Balancing Bias and Variance in Unsupervised Multi-Source-Free Domai
        8175, -- 2203.03884 Semi-Supervised Semantic Segmentation Using Unreliable Pseudo-Labels
        8380, -- 2203.11635 Feature Distribution Matching for Federated Domain Generalization
        8420, -- 2203.13591 Continual Test-Time Domain Adaptation
        8438, -- 2203.14316 MutexMatch: Semi-Supervised Learning with Mutex-Based Consistency Regu
        8485, -- 2203.16219 Acknowledging the Unknown for Multi-label Learning with Single Positiv
        8558, -- 2204.01678 MultiMAE: Multi-modal Multi-task Masked Autoencoders
        8582, -- 2204.02610 Efficient Test-Time Model Adaptation without Forgetting
        8724, -- 2204.07300 Dense Learning based Semi-Supervised Object Detection
        8805, -- 2204.10377 Contrastive Test-Time Adaptation
        8855, -- 2204.12667 MM-TTA: Multi-Modal Test-Time Adaptation for 3D Semantic Segmentation
        8968, -- 2205.03598 Towards Computationally Feasible Deep Active Learning
        9312, -- 2206.00274 Point-Teaching: Weakly Semi-Supervised Object Detection with Point Ann
        9379, -- 2206.02721 Revisiting Realistic Test-Time Training: Sequential Inference and Adap
        9466, -- 2206.06640 Confidence Score for Source-Free Unsupervised Domain Adaptation
        9544, -- 2206.09591 Domain-Adaptive Text Classification with Structured Knowledge from Unl
        9674, -- 2207.00712 Turning to a Teacher for Timestamp Supervised Temporal Action Segmenta
        9693, -- 2207.02372 Domain Adaptive Video Segmentation via Temporal Pseudo Supervision
        9813, -- 2207.08185 Mind the Gap: Polishing Pseudo labels for Accurate Semi-supervised Obj
        10007, -- 2208.04619 RDA: Reciprocal Distribution Alignment for Robust Semi-supervised Lear
        10012, -- 2208.05110 Collaborative Propagation on Multiple Instance Graphs for 3D Instance
        10084, -- 2208.09243 Pseudo-Labels Are All You Need
        10208, -- 2209.01217 A Method for Discovering Novel Classes in Tabular Data
        10214, -- 2209.01589 Consistent-Teacher: Towards Reducing Inconsistent Pseudo-targets in Se
        10287, -- 2209.06993 Learning from Future: A Novel Self-Training Framework for Semantic Seg
        10488, -- 2209.15483 Augmentation Invariant Discrete Representation for Generative Spoken L
        10579, -- 2210.02442 Making Your First Choice: To Address Cold Start Problem in Vision Acti
        10695, -- 2210.05246 Cluster-level pseudo-labelling for source-free cross-domain facial exp
        11074, -- 2210.14723 Semi-Supervised Learning Based on Reference Model for Low-resource TTS
        11401, -- 2211.09446 Detecting Arbitrary Keypoints on Limbs and Skis with Sparse Partly Cor
        11501, -- 2211.11727 Parametric Classification for Generalized Category Discovery: A Baseli
        11512, -- 2211.11950 UpCycling: Semi-supervised 3D Object Detection without Sharing Raw-lev
        11644, -- 2211.14813 SegCLIP: Patch Aggregation with Learnable Centers for Open-Vocabulary
        11697, -- 2211.16352 Découvrir de nouvelles classes dans des données tabulaires
        11779, -- 2212.01322 MIC: Masked Image Consistency for Context-Enhanced Domain Adaptation
        11786, -- 2212.01424 PROB: Probabilistic Objectness for Open World Object Detection
        11863, -- 2212.04145 Decorate the Newcomers: Visual Domain Prompt for Continual Test Time A
        11979, -- 2212.07585 Rethinking the Role of Pre-Trained Networks in Source-Free Domain Adap
        12043, -- 2212.08992 PoE: a Panel of Experts for Generalized Automatic Dialogue Assessment
        12175, -- 2212.10806 MaskingDepth: Masked Consistency Regularization for Semi-supervised Mo
        12231, -- 2212.13420 Self Meta Pseudo Labels: Meta Pseudo Labels Without The Teacher
        13093, -- 2302.06992 Hard-aware Instance Adaptive Self-training for Unsupervised Cross-doma
        13225, -- 2302.10586 Diffusion Models and Semi-Supervised Learners Benefit Mutually with Fe
        13270, -- 2302.12028 Novel Class Discovery: an Introduction and Key Concepts
        13316, -- 2302.12986 Self-similarity Driven Scale-invariant Learning for Weakly Supervised
        13325, -- 2302.13334 Knowledge Restore and Transfer for Multi-label Class-Incremental Learn
        13444, -- 2303.01267 Token Contrast for Weakly-Supervised Semantic Segmentation
        13624, -- 2303.05668 UNFUSED: UNsupervised Finetuning Using SElf supervised Distillation
        13647, -- 2303.06135 Rewarding Chatbots for Real-World Engagement with Millions of Users
        13812, -- 2303.09083 Focus on Your Target: A Dual Teacher-Student Framework for Domain-adap
        13846, -- 2303.09706 Unsupervised Self-Driving Attention Prediction via Uncertainty Mining
        13922, -- 2303.11203 Less is More: Reducing Task and Model Complexity for 3D Point Cloud Se
        13941, -- 2303.11420 ADCNet: Learning from Raw Radar Data via Distillation
        13989, -- 2303.12078 Two-shot Video Object Segmentation
        14004, -- 2303.12370 Weakly Supervised Video Representation Learning with Unaligned Text fo
        14030, -- 2303.12793 CiCo: Domain-Aware Sign Language Retrieval via Cross-Lingual Contrasti
        14042, -- 2303.13090 Orthogonal Annotation Benefits Barely-supervised Medical Image Segment
        14421, -- 2304.01464 Hierarchical Supervision and Shuffle Data Augmentation for 3D Semi-Sup
        14715, -- 2304.07354 NEV-NCD: Negative Learning, Entropy, and Variance regularization based
        14817, -- 2304.09913 MARS: Model-agnostic Biased Object Removal without Additional Supervis
        14921, -- 2304.12314 Distilling from Similar Tasks for Transfer Learning on a Budget
        15009, -- 2304.14104 Learning Human-Human Interactions in Images from Weak Textual Supervis
        15039, -- 2304.14531 High-dimensional Clustering onto Hamiltonian Cycle
        15053, -- 2304.14795 Semi-Supervised RF Fingerprinting with Consistency-Based Regularizatio
        15093, -- 2305.00673 Bidirectional Copy-Paste for Semi-Supervised Medical Image Segmentatio
        15252, -- 2305.03287 Low-Resource Multi-Granularity Academic Function Recognition Based on
        15463, -- 2305.06988 Self-Chained Image-Language Model for Video Localization and Question
        15568, -- 2305.08685 CLIP-VG: Self-paced Curriculum Adapting of CLIP for Visual Grounding
        15668, -- 2305.10424 ZeroFlow: Scalable Scene Flow via Distillation
        15718, -- 2305.11012 SDC-UDA: Volumetric Unsupervised Domain Adaptation Framework for Slice
        16167, -- 2305.14913 CoLaDa: A Collaborative Label Denoising Framework for Cross-lingual Na
        16406, -- 2305.17197 Entailment as Robust Self-Learner
        16414, -- 2305.17303 Distilling BlackBox to Interpretable models for Efficient Transfer Lea
        16707, -- 2306.00107 MERT: Acoustic Music Understanding Model with Large-Scale Self-supervi
        16724, -- 2306.00265 Doubly Robust Self-Training
        16865, -- 2306.01669 Enhancing CLIP with CLIP: Exploring Pseudolabeling for Limited-Label P
        16926, -- 2306.02314 Using Unreliable Pseudo-Labels for Label-Efficient Semantic Segmentati
        17054, -- 2306.03802 Learning to Ground Instructional Articles in Videos through Narrations
        17093, -- 2306.04300 CorrMatch: Label Propagation via Correlation Matching for Semi-Supervi
        17096, -- 2306.04344 ViDA: Homeostatic Visual Domain Adapter for Continual Test Time Adapta
        18021, -- 2307.02249 Rethinking Multiple Instance Learning for Whole Slide Image Classifica
        18089, -- 2307.03741 Training Ensembles with Inliers and Outliers for Semi-supervised Activ
        18276, -- 2307.07944 Revisiting Domain-Adaptive 3D Object Detection by Reliable, Diverse an
        18343, -- 2307.08809 Local or Global: Selective Knowledge Assimilation for Federated Learni
        18364, -- 2307.09254 Selective Generation for Controllable Language Models
        18413, -- 2307.10062 Unsupervised Accuracy Estimation of Deep Visual Models using Domain-Ad
        18568, -- 2307.12576 Self-refining of Pseudo Labels for Music Source Separation with Noisy
        18605, -- 2307.13251 GaPro: Box-Supervised 3D Point Cloud Instance Segmentation Using Gauss
        18633, -- 2307.13813 How to Scale Your EMA
        18643, -- 2307.13938 Improving Semi-Supervised Semantic Segmentation with Dual-Level Siames
        18715, -- 2307.15052 Learning Depth Estimation for Transparent and Mirror Surfaces
        18792, -- 2307.16634 CDUL: CLIP-Driven Unsupervised Learning for Multi-Label Image Classifi
        18983, -- 2308.03286 Multi-Label Self-Supervised Learning with Scene Images
        19012, -- 2308.03793 ReCLIP: Refine Contrastive Language Image Pre-Training with Source Fre
        19065, -- 2308.04638 GeoAdapt: Self-Supervised Test-Time Adaptation in LiDAR Place Recognit
        19086, -- 2308.04946 SelectNAdapt: Support Set Selection for Few-Shot Domain Adaptation
        19104, -- 2308.05359 Pseudo-label Alignment for Semi-supervised Instance Segmentation
        19147, -- 2308.05991 Cyclic-Bootstrap Labeling for Weakly Supervised Object Detection
        19208, -- 2308.06777 Shrinking Class Space for Enhanced Certainty in Semi-Supervised Learni
        19285, -- 2308.07918 Helping Hands: An Object-Aware Ego-Centric Video Recognition Model
        19356, -- 2308.08872 Towards Semi-supervised Learning with Non-random Missing Labels
        19396, -- 2308.09351 RLIPv2: Fast Scaling of Relational Language-Image Pre-training
        19451, -- 2308.09887 Calibrating Uncertainty for Semi-Supervised Crowd Counting
        19474, -- 2308.10016 Pseudo Flow Consistency for Self-Supervised 6D Object Pose Estimation
        19503, -- 2308.10205 GeT: Generative Target Structure Debiasing for Domain Adaptation
        19640, -- 2308.11596 SeamlessM4T: Massively Multilingual & Multimodal Machine Translation
        19663, -- 2308.11874 Semi-Supervised Learning via Weight-aware Distillation under Class Dis
        19665, -- 2308.11880 SUMMIT: Source-Free Adaptation of Uni-Modal Models to Multi-Modal Targ
        19668, -- 2308.11901 Camera-Driven Representation Learning for Unsupervised Domain Adaptive
        19728, -- 2308.12595 Logic-induced Diagnostic Reasoning for Semi-supervised Semantic Segmen
        19769, -- 2308.13168 IOMatch: Simplifying Open-Set Semi-Supervised Learning with Joint Inli
        19777, -- 2308.13236 Black-box Unsupervised Domain Adaptation with Bi-directional Atkinson-
        19790, -- 2308.13411 Harvard Glaucoma Detection and Progression: A Multimodal Multitask Dat
        19824, -- 2308.13954 Prior-guided Source-free Domain Adaptation for Human Pose Estimation
        19858, -- 2308.14374 Online Continual Learning on Hierarchical Label Expansion
        19865, -- 2308.14575 Referring Image Segmentation Using Text Supervision
        19934, -- 2308.15939 Bootstrap Fine-Grained Vision-Language Alignment for Unified Zero-Shot
        20054, -- 2309.01246 Towards Generic Image Manipulation Detection with Weakly-Supervised Se
        20226, -- 2309.04422 Video Task Decathlon: Unifying Image and Video Tasks in Autonomous Dri
        20562, -- 2309.09749 Facilitating NSFW Text Detection in Open-Domain Dialogue Systems via K
        20593, -- 2309.10244 UPL-SFDA: Uncertainty-aware Pseudo Label Guided Source-Free Domain Ada
        20663, -- 2309.11132 Contrastive Pseudo Learning for Open-World DeepFake Attribution
        20954, -- 2309.15251 VPA: Fully Test-Time Visual Prompt Adaptation
        21243, -- 2310.01376 Towards Distribution-Agnostic Generalized Category Discovery
        21401, -- 2310.03013 SemiReward: A General Reward Model for Semi-supervised Learning
        21490, -- 2310.03975 HuBERTopic: Enhancing Semantic Representation of HuBERT through Self-s
        21622, -- 2310.05483 HarmonicNeRF: Geometry-Informed Synthetic View Augmentation for 3D Sce
        21847, -- 2310.08056 Learning from Label Proportions: Bootstrapping Supervised Learners via
        22332, -- 2310.14108 CLIP meets Model Zoo Experts: Pseudo-Supervision for Visual Enhancemen
        22369, -- 2310.14577 DeCrisisMB: Debiased Semi-Supervised Learning for Crisis Tweet Classif
        22370, -- 2310.14583 JointMatch: A Unified Approach for Diverse and Collaborative Pseudo-La
        22389, -- 2310.14814 Leveraging Ensemble Diversity for Robust Self-Training in the Presence
        22517, -- 2310.16271 CycleAlign: Iterative Distillation from Black-box LLM to White-box Mod
        22588, -- 2310.17097 Navigating Data Heterogeneity in Federated Learning A Semi-Supervised
        22638, -- 2310.17784 Data-Centric Financial Large Language Models
        22690, -- 2310.18444 M3C: A Framework towards Convergent, Flexible, and Unsupervised Learni
        22850, -- 2311.00430 Distil-Whisper: Robust Knowledge Distillation via Large-Scale Pseudo L
        23065, -- 2311.04292 Aspect-based Meeting Transcript Summarization: A Two-Stage Approach wi
        23533, -- 2311.11525 Generalized Category Discovery in Semantic Segmentation
        24081, -- 2312.00114 Un-EvMoSeg: Unsupervised Event-based Independent Motion Segmentation
        24666, -- 2312.07169 Semi-supervised Active Learning for Video Action Detection
        24670, -- 2312.07264 Dual Structure-Aware Image Filterings for Semi-supervised Medical Imag
        24671, -- 2312.07266 ProxyDet: Synthesizing Proxy Novel Classes via Classwise Mixup for Ope
        24693, -- 2312.07530 Weakly Supervised 3D Object Detection via Multi-Level Visual Guidance
        24766, -- 2312.08852 ERASE: Error-Resilient Representation Learning on Graphs for Label Noi
        24982, -- 2312.12237 Roll With the Punches: Expansion and Shrinkage of Soft Label Selection
        25281, -- 2312.17225 4DGen: Grounded 4D Content Generation with Spatial-temporal Consistenc
        25594, -- 2401.04230 SOAP: Cross-sensor Domain Adaptation for 3D Object Detection Using Sta
        25805, -- 2401.07278 Semi-Supervised Semantic Segmentation using Redesigned Self-Training f
        25914, -- 2401.08968 COCO is "ALL'' You Need for Visual Instruction Fine-tuning
        25918, -- 2401.08992 Efficient Adapter Finetuning for Tail Languages in Streaming Multiling
        25937, -- 2401.09266 P$^2$OT: Progressive Partial Optimal Transport for Deep Imbalanced Clu
        25978, -- 2401.09786 Adaptive Self-training Framework for Fine-grained Scene Graph Generati
        26029, -- 2401.10472 Named Entity Recognition Under Domain Shift via Metric Learning for Li
        26046, -- 2401.10711 Weakly Supervised Gaussian Contrastive Grounding with Large Multimodal
        26057, -- 2401.10848 Source-Free and Image-Only Unsupervised Domain Adaptation for Category
        26474, -- 2401.16862 State Value Generation with Prompt Learning and Self-Training for Low-
        26684, -- 2402.01692 Maximizing Data Efficiency for Cross-Lingual TTS Adaptation by Self-Su
        26808, -- 2402.02985 Applying Unsupervised Semantic Segmentation to High-Resolution UAV Ima
        27195, -- 2402.07633 Complete Instances Mining for Weakly Supervised Instance Segmentation
        27688, -- 2402.13232 A Touch, Vision, and Language Dataset for Multimodal Alignment
        28179, -- 2402.18958 Boosting Semi-Supervised Object Detection in Remote Sensing Images Wit
        28399, -- 2403.02600 TESTAM: A Time-Enhanced Spatio-Temporal Attention Model with Mixture o
        28426, -- 2403.02998 Towards Calibrated Deep Clustering Network
        28431, -- 2403.03095 Cross Pseudo-Labeling for Semi-Supervised Audio-Visual Source Localiza
        28437, -- 2403.03145 Dual Mean-Teacher: An Unbiased Semi-Supervised Framework for Audio-Vis
        28462, -- 2403.03516 Unsupervised Multilingual Dense Retrieval via Generative Pseudo Labeli
        28710, -- 2403.07366 Entropy is not Enough for Test-Time Adaptation: From the Perspective o
        29082, -- 2403.12173 TnT-LLM: Text Mining at Scale with Large Language Models
        29162, -- 2403.13225 Modeling the Label Distributions for Weakly-Supervised Semantic Segmen
        29167, -- 2403.13250 Facilitating Pornographic Text Detection for Open-Domain Dialogue Syst
        29196, -- 2403.13556 Find n' Propagate: Open-Vocabulary 3D Object Detection in Urban Enviro
        29330, -- 2403.15317 Point-DETR3D: Leveraging Imagery Data with Spatial Point Prior for Wea
        29850, -- 2404.02041 SelfPose3d: Self-Supervised Multi-Person Multi-View 3d Pose Estimation
        29878, -- 2404.02544 Semi-Supervised Unconstrained Head Pose Estimation in the Wild
        29938, -- 2404.03446 SP$^2$OT: Semantic-Regularized Progressive Partial Optimal Transport f
        30070, -- 2404.05426 Test-Time Zero-Shot Temporal Action Localization
        30282, -- 2404.08421 Adapting the Segment Anything Model During Usage in Novel Situations
        30541, -- 2404.12386 SOHES: Self-supervised Open-world Hierarchical Entity Segmentation
        30760, -- 2404.16339 Training-Free Unsupervised Prompt for Vision-Language Models
        30803, -- 2404.16944 Constellation Dataset: Benchmarking High-Altitude Object Detection for
        31133, -- 2405.04788 SemiCD-VL: Visual-Language Model Guidance Makes Better Semi-supervised
        31378, -- 2405.10548 Language Models can Exploit Cross-Task In-context Learning for Data-Sc
        31418, -- 2405.11574 Reproducibility Study of CDUL: CLIP-Driven Unsupervised Learning for M
        31946, -- 2405.18416 3D StreetUnveiler with Semantic-Aware 2DGS
        32197, -- 2406.00830 Collaborative Novel Object Discovery and Box-Guided Cross-Modal Alignm
        32214, -- 2406.01020 ATTIQA: Generalizable Image Quality Feature Extractor using Attribute-
        32291, -- 2406.02285 Towards Supervised Performance on Speaker Verification with Self-Super
        32523, -- 2406.05131 A Semi-Self-Supervised Approach for Dense-Pattern Video Object Segment
        32660, -- 2406.06679 PatchRefiner: Leveraging Synthetic Data for Real-Domain High-Resolutio
        32670, -- 2406.06908 UVIS: Unsupervised Video Instance Segmentation
        32869, -- 2406.09206 Self-Training for Sample-Efficient Active Learning for Text Classifica
        32899, -- 2406.09406 4M-21: An Any-to-Any Vision Model for Tens of Tasks and Modalities
        32904, -- 2406.09414 Depth Anything V2
        33114, -- 2406.11546 GigaSpeech 2: An Evolving, Large-Scale and Multi-domain ASR Corpus for
        33219, -- 2406.12225 The Solution for CVPR2024 Foundational Few-Shot Object Detection Chall
        33290, -- 2406.12849 Depth Anywhere: Enhancing 360 Monocular Depth Estimation via Perspecti
        33573, -- 2406.16427 Dynamic Pseudo Label Optimization in Point-Supervised Nuclei Segmentat
        33677, -- 2406.17741 Point-SAM: Promptable 3D Segmentation Model for Point Clouds
        33950, -- 2407.01257 uDistil-Whisper: Label-Free Data Filtering for Knowledge Distillation
        34036, -- 2407.02253 Parameter-Selective Continual Test-Time Adaptation
        34110, -- 2407.03251 ACTRESS: Active Retraining for Semi-supervised Visual Grounding
        34185, -- 2407.04219 Semi-supervised Learning for Code-Switching ASR with Large Language Mo
        34300, -- 2407.05890 Affordances-Oriented Planning using Foundation Models for Continuous V
        34383, -- 2407.07024 Exploring Scalability of Self-Training for Open-Vocabulary Temporal Ac
        34410, -- 2407.07341 A Guide To Effectively Leveraging LLMs for Low-Resource Text Summariza
        34440, -- 2407.07844 OV-DINO: Unified Open-Vocabulary Detection with Language-Aware Selecti
        34498, -- 2407.08569 Approaching Outside: Scaling Unsupervised 3D Object Detection from 2D
        34816, -- 2407.12489 Dual-level Adaptive Self-Labeling for Novel Class Discovery in Point C
        34874, -- 2407.12997 Multi-Iteration Multi-Stage Fine-Tuning of Transformers for Sound Even
        34887, -- 2407.13157 Learning Camouflaged Object Detection from Noisy Pseudo Label
        34910, -- 2407.13524 Enhancing Source-Free Domain Adaptive Object Detection with Low-confid
        35008, -- 2407.15041 Self-training Room Layout Estimation via Geometry-aware Ray-casting
        35153, -- 2407.17331 Multi-label Cluster Discrimination for Visual Representation Learning
        35370, -- 2407.21465 MarvelOVD: Marrying Object Recognition and Vision-Language Models for
        35418, -- 2408.00286 Diff3DETR:Agent-based Diffusion Model for Semi-supervised 3D Object De
        35702, -- 2408.05101 MooER: LLM-based Speech Recognition and Translation Models from Moore
        35726, -- 2408.05674 PS-TTL: Prototype-based Soft-labels and Test-Time Learning for Few-sho
        35910, -- 2408.08855 DPA: Dual Prototypes Alignment for Unsupervised Adaptation of Vision-L
        36225, -- 2408.14026 Empowering Low-Resource Language ASR via Large-Scale Pseudo Labeling
        36450, -- 2409.00487 TrackSSM: A General Motion Predictor by State-Space Model
        36756, -- 2409.06903 Semi-Supervised Reward Modeling via Iterative Self-Training
        37125, -- 2409.13499 Fast Streaming Transducer ASR Prototyping via Knowledge Distillation w
        37509, -- 2409.19833 HazyDet: Open-source Benchmark for Drone-view Object Detection with De
        37541, -- 2409.20253 Medical Image Segmentation with SAM-generated Annotations
        37805, -- 2410.02746 Contrastive Localized Language-Image Pre-Training
        37843, -- 2410.03124 On Unsupervised Prompt Learning for Classification with Black-box Lang
        38046, -- 2410.05557 Rethinking Weak-to-Strong Augmentation in Source-Free Domain Adaptive
        38392, -- 2410.09865 SynFER: Towards Boosting Facial Expression Recognition with Synthetic
        38564, -- 2410.11831 CoTracker3: Simpler and Better Point Tracking by Pseudo-Labelling Real
        38799, -- 2410.14379 AnomalyNCD: Towards Novel Anomaly Class Discovery in Industrial Scenar
        39596, -- 2411.02256 Unified Speech Recognition: A Single Model for Auditory, Visual, and A
        39798, -- 2411.05564 Open-set object detection: towards unified problem formulation and ben
        39938, -- 2411.08028 Learning with Less: Knowledge Distillation from Large Language Models
        40672, -- 2411.19346 CLIP meets DINO for Tuning Zero-Shot Classifier using Unlabeled Image
        40809, -- 2412.01106 One Shot, One Talk: Whole-body Talking Avatar from a Single Image
        41278, -- 2412.07072 Stable Mean Teacher for Semi-supervised Video Action Detection
        41325, -- 2412.07746 LoRA3D: Low-Rank Self-Calibration of 3D Geometric Foundation Models
        41357, -- 2412.08101 Generative Zoo
        41660, -- 2412.11812 CLDA-YOLO: Visual Contrastive Learning Based Domain Adaptive YOLO Dete
        41685, -- 2412.11983 Leveraging Large Language Models for Effective Label-free Node Classif
        42470, -- 2501.02158 Joint Optimization for 4D Human-Scene Reconstruction in the Wild
        42662, -- 2501.05234 Optimizing Estonian TV Subtitles with Semi-supervised Learning and LLM
        43255, -- 2501.15384 MetaOcc: Surround-View 4D Radar and Camera Fusion Framework for 3D Occ
        43839, -- 2502.05139 Meta Audiobox Aesthetics: Unified Automatic Quality Assessment for Spe
        44476, -- 2502.12755 Efficient Machine Translation Corpus Generation: Integrating Human-in-
        44736, -- 2502.15152 Confidence-Weighted Boundary-Aware Learning for Semi-Supervised Semant
        44756, -- 2502.15418 MHQA: A Diverse, Knowledge Intensive Mental Health Question Answering
        45069, -- 2502.19204 Distill Any Depth: Distillation Creates a Stronger Monocular Depth Est
        45137, -- 2502.19941 Alleviating Distribution Shift in Synthetic Data for Machine Translati
        45186, -- 2502.20389 LIFT-GS: Cross-Scene Render-Supervised Distillation for 3D Language Gr
        45378, -- 2503.01917 Steer LLM Latents for Hallucination Detection
        45479, -- 2503.03365 TopoMortar: A dataset to evaluate image segmentation methods focused o
        45759, -- 2503.07098 OmniSAM: Omnidirectional Segment Anything Model for UDA in Panoramic S
        45893, -- 2503.08601 LiSu: A Dataset and Method for LiDAR Surface Normal Estimation
        46222, -- 2503.12780 LangDA: Building Context-Awareness via Language for Domain Adaptive Se
        46462, -- 2503.16184 Accurate Scene Text Recognition with Efficient Model Scaling and Cloze
        46472, -- 2503.16282 Generalized Few-shot 3D Point Cloud Segmentation with Vision-Language
        46530, -- 2503.16976 GeoT: Geometry-guided Instance-dependent Transition Matrix for Semi-su
        46705, -- 2503.19355 ST-VLM: Kinematic Instruction Tuning for Spatio-Temporal Reasoning in
        46874, -- 2503.21751 Reconstructing Humans with a Biomechanically Accurate Skeleton
        47076, -- 2503.24381 UniOcc: A Unified Benchmark for Occupancy Forecasting and Prediction i
        47185, -- 2504.01955 Scene-Centric Unsupervised Panoptic Segmentation
        47307, -- 2504.03755 ProtoGCD: Unified and Unbiased Prototype Learning for Generalized Cate
        47383, -- 2504.05301 S^4M: Boosting Semi-Supervised Instance Segmentation with SAM
        47552, -- 2504.08531 Embodied Image Captioning: Self-supervised Learning Agents for Spatial
        47642, -- 2504.09966 SemiETS: Integrating Spatial and Content Consistencies for Semi-Superv
        47775, -- 2504.11856 Cross-Frequency Collaborative Training Network and Dataset for Semi-su
        47789, -- 2504.12186 CoMotion: Concurrent Multi-person 3D Motion
        47890, -- 2504.13458 Learning from Noisy Pseudo-labels for All-Weather Land Cover Mapping
        48019, -- 2504.15404 Context Aware Grounded Teacher for Source Free Object Detection
        48035, -- 2504.15728 SAGA: Semantic-Aware Gray color Augmentation for Visible-to-Thermal Do
        48337, -- 2505.01448 OpenAVS: Training-Free Open-Vocabulary Audio Visual Segmentation with
        48452, -- 2505.03538 RAIL: Region-Aware Instructive Learning for Semi-Supervised Tooth Segm
        49058, -- 2505.13404 Granary: Speech Recognition and Translation Dataset in 25 European Lan
        49915, -- 2505.20981 RefAV: Towards Planning-Centric Scenario Mining
        49982, -- 2505.21904 CAST: Contrastive Adaptation and Distillation for Semi-Supervised Inst
        50038, -- 2505.22759 FAMA: The First Large-Scale Open-Science Speech Foundation Model for E
        50210, -- 2505.24216 Shuffle PatchMix Augmentation with Confidence-Margin Weighted Pseudo-L
        50758, -- 2506.07368 C3S3: Complementary Competition and Contrastive Selection for Semi-Sup
        50790, -- 2506.07886 EgoM2P: Egocentric Multimodal Multitask Pretraining
        51018, -- 2506.10601 Semantic-decoupled Spatial Partition Guided Point-supervised Oriented
        51060, -- 2506.11130 A Self-Refining Framework for Enhancing ASR Using TTS-Synthesized Data
        51212, -- 2506.14427 M3SD: Multi-modal, Multi-scenario and Multi-language Speaker Diarizati
        51518, -- 2506.21484 TITAN: Query-Token based Domain Adaptive Adversarial Learning
        51529, -- 2506.21547 SAM4D: Segment Anything in Camera and LiDAR Streams
        51602, -- 2507.00339 Training for X-Ray Vision: Amodal Segmentation, Amodal Content Complet
        51621, -- 2507.01634 Depth Anything at Any Condition
        52282, -- 2508.06429 SPARSE Data, Rich Results: Few-Shot Semi-Supervised Learning via Class
        52632, -- 2509.02523 Flavors of Moonshine: Tiny Specialized ASR Models for Edge Devices
        52755, -- 2509.09926 LoFT: Parameter-Efficient Fine-Tuning for Long-tailed Semi-Supervised
        53023, -- 2509.25077 BRIDGE - Building Reinforcement-Learning Depth-to-Image Data Generatio
        53193, -- 2510.03574 Efficient Test-Time Scaling for Small Vision-Language Models
        53406, -- 2510.05684 D2E: Scaling Vision-Action Pretraining on Desktop Data for Transfer to
        53429, -- 2510.08047 Pseudo2Real: Task Arithmetic for Pseudo-Label Correction in Automatic
        53499, -- 2510.06582 Through the Perspective of LiDAR: A Feature-Enriched and Uncertainty-A
        54096, -- 2110.08733 LoveDA: A Remote Sensing Land-Cover Dataset for Domain Adaptive Semant
        54661, -- 2512.06864 Boosting Unsupervised Video Instance Segmentation with Automatic Quali
        54745, -- 2512.11130 Fast-FoundationStereo: Real-Time Zero-Shot Stereo Matching
        54868, -- 2512.16913 Depth Any Panoramas: A Foundation Model for Panoramic Depth Estimation
        55102, -- 2512.23035 Toward Stable Semi-Supervised Remote Sensing Segmentation via Co-Guida
        55198, -- 2601.05882 An Empirical Study on Preference Tuning Generalization and Diversity U
        55394, -- 2601.13761 DARC: Decoupled Asymmetric Reasoning Curriculum for LLM Evolution
        55457, -- 2601.14255 VideoMaMa: Mask-Guided Video Matting via Generative Prior
        55461, -- 2601.15549 VIOLA: Towards Video In-Context Learning with Minimal Annotations
        55619, -- 2601.22628 TTCS: Test-Time Curriculum Synthesis for Self-Evolving
        56109, -- 2602.13022 Learning Image-based Tree Crown Segmentation from Enhanced Lidar-based
        56393, -- 2603.00610 CMI-RewardBench: Evaluating Music Reward Models with Compositional Mul
        56403, -- 2603.02203 Tool Verification for Test-Time Reinforcement Learning
        56490, -- 2602.23229 Large Multimodal Models as General In-Context Classifiers
        56875, -- 2603.11804 OSM-based Domain Adaptation for Remote Sensing VLMs
        57368, -- 2604.03841 Training a Student Expert via Semi-Supervised Foundation Model Distill
        57427, -- 2604.11547 Eliciting Medical Reasoning with Knowledge-enhanced Data Synthesis: A
        57490, -- 2604.14144 SpatialEvo: Self-Evolving Spatial Intelligence via Deterministic Geome
        57824, -- 2604.24952 Learning from Noisy Preferences: A Semi-Supervised Learning Approach t
        57888, -- 2604.23289 MetaErr: Towards Predicting Error Patterns in Deep Neural Networks
        58419, -- 2604.07021 ModuSeg: Decoupling Object Discovery and Semantic Retrieval for Traini
        58802, -- 2603.27344 TerraSeg: Self-Supervised Ground Segmentation for Any LiDAR
        59027, -- 2603.21478 TaigiSpeech: A Low-Resource Real-World Speech Intent Dataset and Preli
        59115, -- 2603.19880 What If Consensus Lies? Selective-Complementary Reinforcement Learning
        59196, -- 2603.17775 CoVerRL: Breaking the Consensus Trap in Label-Free Reasoning via Gener
        59206, -- 2603.17470 VirPro: Visual-referred Probabilistic Prompt Learning for Weakly-Super
        59292, -- 2603.16223 Dual Consensus: Escaping from Spurious Majority in Unsupervised RLVR v
        59303, -- 2603.15988 Something from Nothing: Data Augmentation for Robust Severity Level Es
        59511, -- 2603.12217 Real-World Point Tracking with Verifier-Guided Pseudo-Labeling
        59589, -- 2603.11378 Continued Pretraining for Low-Resource Swahili ASR: Achieving State-of
        59785, -- 2603.06167 A Semi-Supervised Framework for Breast Ultrasound Segmentation with Tr
        60363, -- 2602.20231 UniLACT: Depth-Aware RGB Latent Action Learning for Vision-Language-Ac
        60440, -- 2602.18721 ReHear: Iterative Pseudo-Label Refinement for Semi-Supervised Speech R
        60732, -- 2602.12561 PLLM: Pseudo-Labeling Large Language Models for CAD Program Synthesis
        61181, -- 2602.05330 MTPano: Multi-Task Panoramic Scene Understanding via Label-Free Integr
        61235, -- 2602.04699 Annotation Free Spacecraft Detection and Segmentation using Vision Lan
        61257, -- 2602.04337 Fine-tuning Pre-trained Vision-Language Models in a Human-Annotation-F
        61495, -- 2602.02150 ECHO: Entropy-Confidence Hybrid Optimization for Test-Time Reinforceme
        61617, -- 2602.00604 The TMU System for the XACLE Challenge: Training Large Audio Language
        61633, -- 2602.00484 GTATrack: Winner Solution to SoccerTrack 2025 with Deep-EIoU and Globa
        61744, -- 2602.00202 Vision-Language Model Purified Semi-Supervised Semantic Segmentation f
        62295, -- 2601.13886 Revisiting Multi-Task Visual Representation Learning
        62476, -- 2601.10094 V-Zero: Self-Improving Multimodal Reasoning with Zero Annotation
        62572, -- 2601.08139 Subspace Alignment for Vision-Language Model Test-time Adaptation
        62584, -- 2510.14420 Instructions are all you need: Self-supervised Reinforcement Learning
        62683, -- 2601.06802 Doing More with Less: Data Augmentation for Sudanese Dialect Automatic
        63619, -- 2512.15146 Beyond Majority Voting: Towards Fine-grained and More Reliable Reward
        64482, -- 2512.00086 Multi-modal On-Device Learning for Monocular Depth Estimation on Ultra
        64542, -- 2511.20253 Zoo3D: Zero-Shot 3D Object Detection at Scene Level
        64585, -- 2511.19759 Vision-Language Enhanced Foundation Model for Semi-supervised Medical
        64614, -- 2511.19067 DynaMix: Generalizable Person Re-identification via Dynamic Relabeling
        65133, -- 2511.08903 LLM-Guided Probabilistic Fusion for Label-Efficient Document Layout An
        65594, -- 2510.27210 GUI-Rise: Structured Reasoning and History Summarization for GUI Navig
        65763, -- 2511.00040 Semi-Supervised Preference Optimization with Limited Feedback
        66049, -- 2510.19351 Learning To Defer To A Population With Limited Demonstrations
        66150, -- 2510.17662 DELULU: Discriminative Embedding Learning Using Latent Units for Speak
        66301, -- 2510.14792 CoT-PL: Visual Chain-of-Thought Reasoning Meets Pseudo-Labeling for Op
        66339, -- 2510.14242 Flip-Flop Consistency: Unsupervised Training for Robustness to Prompt
        66538, -- 2510.11567 A Framework for Low-Effort Training Data Generation for Urban Semantic
        67866, -- 2509.20154 U-Mamba2-SSL for Semi-Supervised Tooth and Pulp Segmentation in CBCT
        68077, -- 2509.16704 When Confidence Fails: Revisiting Pseudo-Label Selection in Semi-super
        68495, -- 2509.09429 Semantic Concentration for Self-Supervised Dense Representations Learn
        68741, -- 2509.04072 LibriQuote: A Speech Dataset of Fictional Character Utterances for Exp
        68815, -- 2509.02450 EmoPerso: Enhancing Personality Detection with Self-Supervised Emotion
        69084, -- 2508.19909 Integrating SAM Supervision for 3D Weakly Supervised Point Cloud Segme
        69096, -- 2508.19808 AutoQ-VIS: Improving Unsupervised Video Instance Segmentation via Auto
        69162, -- 2508.18799 Robust and Label-Efficient Deep Waste Detection
        69336, -- 2508.16100 CYCLE-INSTRUCT: Fully Seed-Free Instruction Tuning via Dual Self-Train
        69376, -- 2508.15313 First RAG, Second SEG: A Training-Free Paradigm for Camouflaged Object
        69425, -- 2508.16656 OASIS: Open-world Adaptive Self-supervised and Imbalanced-aware System
        69626, -- 2508.11356 ETTRL: Balancing Exploration and Exploitation in LLM Test-Time Reinfor
        69650, -- 2508.10838 Unsupervised Stereo via Multi-Baseline Geometry-Consistent Self-Traini
        69865, -- 2508.07905 Generative Video Matting
        69977, -- 2508.06317 Uncertainty-quantified Rollout Policy Adaptation for Unlabelled Cross-
        70063, -- 2508.05090 Cold-Start Active Preference Learning in Socio-Economic Domains
        70157, -- 2508.04036 CORE-ReID V2: Advancing the Domain Adaptation for Object Re-Identifica
        70230, -- 2508.03064 CORE-ReID: Comprehensive Optimization and Refinement through Ensemble
        70411, -- 2508.00563 Weakly Supervised Virus Capsid Detection with Image-Level Annotations
        70489, -- 2507.23373 Multi-Prompt Progressive Alignment for Multi-Source Unsupervised Domai
        70549, -- 2508.00922 CaliMatch: Adaptive Calibration for Improving Safe Semi-supervised Lea
        70857, -- 2507.22075 Prototype-Guided Pseudo-Labeling with Neighborhood-Aware Consistency f
        70885, -- 2507.16429 Robust Noisy Pseudo-label Learning for Semi-supervised Medical Image S
        70952, -- 2507.15094 BleedOrigin: Dynamic Bleeding Source Localization in Endoscopic Submuc
        71348, -- 2507.05724 Omni-Router: Sharing Routing Decisions in Sparse Mixture-of-Experts fo
        71451, -- 2507.03302 Leveraging Out-of-Distribution Unlabeled Images: Semi-Supervised Seman
        71486, -- 2507.02395 Continual Multiple Instance Learning with Enhanced Localization for Hi
        72077, -- 2506.09476 WakeupUrban: Unsupervised Semantic Segmentation of Mid-20^{th} century
        72299, -- 2506.03570 FreePRM: Training Process Reward Models Without Ground Truth Process L
        72696, -- 2505.20415 Enhancing Logical Reasoning in Language Models via Symbolically-Guided
        73032, -- 2505.11314 CROC: Evaluating and Training T2I Metrics with Pseudo- and Human-Label
        73251, -- 2504.21211 A Cost-Effective LLM-based Approach to Identify Wildlife Trafficking i
        73506, -- 2504.11111 S^2Teacher: Step-by-step Teacher for Sparsely Annotated Oriented Objec
        73768, -- 2504.00848 Zero-Shot 4D Lidar Panoptic Segmentation
        74018, -- 2503.13743 MonoCT: Overcoming Monocular 3D Detection Domain Shift with Consistent
        74568, -- 2502.14604 Noisy Test-Time Adaptation in Vision-Language Models
        74632, -- 2502.12366 ScriptoriumWS: A Code Generation Assistant for Weak Supervision
        74661, -- 2502.11381 Without Paired Labeled Data: End-to-End Self-Supervised Learning for D
        74832, -- 2502.05356 Distillation and Pruning for Scalable Self-Supervised Representation-B
        75047, -- 2501.17534 3DSES: an indoor Lidar point cloud segmentation dataset with real and
        75113, -- 2501.12907 S-KEY: Self-supervised Learning of Major and Minor Keys from Audio
        75319, -- 2501.00602 STORM: Spatio-Temporal Reconstruction Model for Large-Scale Outdoor Sc
        75699, -- 2411.17235 MLI-NeRF: Multi-Light Intrinsic-Aware Neural Radiance Fields
        76150, -- 2410.04426 CoVLM: Leveraging Consensus from Vision-Language Models for Semi-super
        76384, -- 2409.09770 Cluster Aware Graph Anomaly Detection
        76690, -- 2407.16931 ScholarChemQA: Unveiling the Power of Language Models in Chemical Rese
        76984, -- 2406.11077 Learning Relighting and Intrinsic Decomposition in Neural Radiance Fie
        77028, -- 2406.07803 EmoSphere-TTS: Emotional Style and Intensity Modeling via Spherical Em
        77443, -- 2404.08977 RoNID: New Intent Discovery with Generated-Reliable Labels and Cluster
        77466, -- 2404.07341 Conformer-1: Robust ASR via Large-Scale Semisupervised Bootstrapping
        77665, -- 2401.17828 Leveraging Swin Transformer for Local-to-Global Weakly Supervised Sema
        77748, -- 2402.17351 ICP-Flow: LiDAR Scene Flow Estimation with ICP
        77916, -- 2401.12507 Open-Set Facial Expression Recognition
        78310, -- 2310.18640 Switching Temporary Teachers for Semi-Supervised Semantic Segmentation
        78731, -- 2307.13375 Towards Unifying Anatomy Segmentation: Automated Generation of a Full-
        78925, -- 2306.02553 Learning to Relate to Previous Turns in Conversational Search
        79139, -- 2304.05754 Self-Supervised Learning with Cluster-Aware-DINO for High-Performance
        79466, -- 2212.13415 Spacecraft Pose Estimation Based on Unsupervised Domain Adaptation and
        79509, -- 2212.02400 Location-Aware Self-Supervised Transformers for Semantic Segmentation
        79533, -- 2211.13969 Unsupervised Continual Semantic Adaptation through Neural Rendering
        79654, -- 2210.09629 1st Place Solutions for the UVO Challenge 2022
        79794, -- 2208.05413 Non-Contrastive Self-Supervised Learning of Utterance-Level Speech Rep
        79843, -- 2101.07555 JigsawGAN: Auxiliary Learning for Solving Jigsaw Puzzles with Generati
        80025, -- 2205.00275 Dynamic Curriculum Learning for Great Ape Detection in the Wild
        80048, -- 2204.09931 Learning to Purification for Unsupervised Person Re-identification
        80106, -- 2203.14523 Translation Consistent Semi-supervised Segmentation for 3D Medical Ima
        80144, -- 2203.06915 SimMatch: Semi-supervised Learning with Similarity Matching
        80180, -- 2202.12040 Self-Training: A Survey
        80347, -- 2112.01071 Extract Free Dense Labels from CLIP
        80425, -- 2110.13740 DP-SSL: Towards Robust Semi-supervised Learning with A Few Labeled Sam
        80447, -- 2110.07578 Learning Temporal 3D Human Pose Estimation with Pseudo-Labels
        80464, -- 2110.02591 Weakly-supervised Text Classification Based on Keyword Graph
        80549, -- 2108.12611 Stagewise Unsupervised Domain Adaptation with Adversarial Self-Trainin
        80719, -- 2105.08655 Semi-Supervised Classification and Segmentation on High Resolution Aer
        80878, -- 2102.09480 Unbiased Teacher for Semi-Supervised Object Detection
        81373, -- 2004.05551 OpenMix: Reviving Known Knowledge for Discovering Novel Visual Categor
        81472, -- 2001.06001 Curriculum Labeling: Revisiting Pseudo-Labeling for Semi-Supervised Le
        82243, -- 1705.00609 Mind the Class Weight Bias: Weighted Maximum Mean Discrepancy for Unsu
        82981, -- 2605.09959 G-Zero: Self-Play for Open-Ended Generation from Zero Data
        83576, -- 2311.18083 Meta Co-Training: Two Views are Better than One
        84022, -- 2505.21147 Semi-Supervised Conformal Prediction With Unlabeled Nonconformity Scor
        84054, -- 2507.06233 AnthroTAP: Learning Point Tracking with Real-World Motion
        84375, -- 2512.10421 Neural Collapse in Test-Time Adaptation
        84419, -- 2512.17514 Foundation Model Priors Enhance Object Focus in Feature Space for Sour
        84487, -- 2601.15288 Attribute-Preserving Pseudo-Labeling for Diffusion-Based Face Swapping
        84589, -- 2602.21078 ProxyFL: A Proxy-Guided Framework for Federated Semi-Supervised Learni
        84634, -- 2602.22917 Towards Multimodal Domain Generalization with Few Labels
        84710, -- 2603.02286 Beyond Prompt Degradation: Prototype-guided Dual-pool Prompting for In
        84743, -- 2603.04090 EgoPoseFormer v2: Accurate Egocentric Human Motion Estimation for AR/V
        84757, -- 2603.05012 Tell2Adapt: A Unified Framework for Source Free Unsupervised Domain Ad
        84837, -- 2603.10341 Federated Active Learning Under Extreme Non-IID and Global Class Imbal
        84856, -- 2603.11521 EReCu: Pseudo-label Evolution Fusion and Refinement with Multi-Cue Lea
        84861, -- 2603.11618 Shape-of-You: Fused Gromov-Wasserstein Optimal Transport for Semantic
        84878, -- 2603.12711 Text-Phase Synergy Network with Dual Priors for Unsupervised Cross-Dom
        84911, -- 2603.14507 Expanding mmWave Datasets for Human Pose Estimation with Unlabeled Dat
        84917, -- 2603.14750 Face-Guided Sentiment Boundary Enhancement for Weakly-Supervised Tempo
        85038, -- 2603.21904 SHAPE: Structure-aware Hierarchical Unsupervised Domain Adaptation wit
        85109, -- 2603.25131 Denoise and Align: Towards Source-Free UDA for Robust Panoramic Semant
        85236, -- 2604.01646 MonoSAOD: Monocular 3D Object Detection with Sparsely Annotated Label
        85288, -- 2604.05354 Unsupervised Multi-agent and Single-agent Perception from Cooperative
        85391, -- 2604.15756 TTL: Test-time Textual Learning for OOD Detection with Pretrained Visi
        85426, -- 2604.19379 PanDA: Unsupervised Domain Adaptation for Multimodal 3D Panoptic Segme
        85573, -- 2605.17742 UST-Hand: An Uncertainty-aware Spatiotemporal Point Cloud Interaction
        85618, -- 2201.13192 Uncertainty-aware Pseudo-label Selection for Positive-Unlabeled Learni
        86054, -- 2503.09707 Revisiting Semi-Supervised Learning in the Era of Foundation Models
        86405, -- 2502.12565 Self Iterative Label Refinement via Robust Unlabeled Learning
        86486, -- 2510.13864 Self-Training with Dynamic Weighting for Robust Gradual Domain Adaptat
        86520, -- 2309.13886 Can Class-Priors Help Single-Positive Multi-Label Learning?
        86566, -- 2509.21526 TRiCo: Triadic Game-Theoretic Co-Training for Robust Semi-Supervised L
        86741, -- 2501.16226 The Effect of Optimal Self-Distillation in Noisy Gaussian Mixture Mode
        86752, -- 2410.20797 Reduction-based Pseudo-label Generation for Instance-dependent Partial
        86821, -- 2508.17152 On the sample complexity of semi-supervised multi-objective learning
        86825, -- 2510.03993 Keep It on a Leash: Controllable Pseudo-label Generation Towards Reali
        86909, -- 2410.01508 Disentangling Latent Shifts of In-Context Learning with Weak Supervisi
        86995, -- 2510.12114 Self-Supervised Selective-Guided Diffusion Model for Old-Photo Face Re
        87066, -- 2510.02731 Hybrid-Collaborative Augmentation and Contrastive Sample Adaptive-Diff
        87069, -- 2510.15266 Semi-Supervised Regression with Heteroscedastic Pseudo-Labels
        87110, -- 2510.13660 OmniGaze: Reward-inspired Generalizable Gaze Estimation In The Wild
        87244, -- 2509.22813 TRUST: Test-Time Refinement using Uncertainty-Guided SSM Traverses
        87261, -- 2507.14312 CLIPTTA: Robust Contrastive Vision-Language Test-Time Adaptation
        87280, -- 2502.14704 Not All Data are Good Labels: On the Self-supervised Labeling for Time
        87558, -- 2507.17373 SFUOD: Source-Free Unknown Object Detection
        87563, -- 2411.16072 Language Driven Occupancy Prediction
        87574, -- 2507.22438 From Sharp to Blur: Unsupervised Domain Adaptation for 2D Human Pose E
        87611, -- 2412.11154 From Easy to Hard: Progressive Active Learning Framework for Infrared
        87755, -- 2506.09445 TOGA: Temporally Grounded Open-Ended Video QA with Weak Supervision
        87780, -- 2507.03539 CLOT: Closed Loop Optimal Transport for Unsupervised Action Segmentati
        87805, -- 2508.18788 PseudoMapTrainer: Learning Online Mapping without HD Maps
        87837, -- 2510.10100 Cooperative Pseudo Labeling for Unsupervised Federated Classification
        87858, -- 2506.05312 Do It Yourself: Learning Semantic Correspondence from Pseudo-Labels
        87882, -- 2508.00442 TopoTTA: Topology-Enhanced Test-Time Adaptation for Tubular Structure
        87896, -- 2507.12029 Intra-view and Inter-view Correlation Guided Multi-view Novel Class Di
        87935, -- 2509.03893 Weakly-Supervised Learning of Dense Functional Correspondences
        88094, -- 2507.01384 MUG: Pseudo Labeling Augmented Audio-Visual Mamba Network for Audio-Vi
        88178, -- 2406.18992 Semi-supervised Concept Bottleneck Models
        88213, -- 2508.05316 Divide-and-Conquer for Enhancing Unlabeled Learning, Stability, and Pl
        88260, -- 2504.10117 AGO: Adaptive Grounding for Open World 3D Occupancy Prediction
        88295, -- 2507.01801 AMD: Adaptive Momentum and Decoupled Contrastive Learning Framework fo
        88299, -- 2508.20381 More Reliable Pseudo-labels, Better Performance: A Generalized Approac
        88317, -- 2509.16970 LLM-Assisted Semantic Guidance for Sparsely Annotated Remote Sensing O
        88392, -- 2503.08829 Seal Your Backdoor with Variational Defense
        88437, -- 2507.01884 Self-Reinforcing Prototype Evolution with Dual-Knowledge Cooperation f
        88443, -- 2504.00139 SuperEvent: Cross-Modal Learning of Event-based Keypoint Detection for
        88468, -- 2506.21198 Unlocking Constraints: Source-Free Occlusion-Aware Seamless Segmentati
        88506, -- 2508.04943 TRKT: Weakly Supervised Dynamic Scene Graph Generation with Temporal-e
        88625, -- 2502.06349 Provably Near-Optimal Federated Ensemble Distillation with Negligible
        88684, -- 2505.16225 MAPLE: Many-Shot Adaptive Pseudo-Labeling for In-Context Learning
        88788, -- 2411.12665 Regression for the Mean: Auto-Evaluation and Inference with Few Labels
        89502, -- 2505.16341 A Square Peg in a Square Hole: Meta-Expert for Long-Tailed Semi-Superv
        89524, -- 2507.07621 Sparse Causal Discovery with Generative Intervention for Unsupervised
        89653, -- 2502.05075 Discrepancies are Virtue: Weak-to-Strong Generalization through Lens o
        89735, -- 2505.06948 Unsupervised Learning for Class Distribution Mismatch
        89799, -- 2506.00816 L3A: Label-Augmented Analytic Adaptation for Multi-Label Class Increme
        89807, -- 2506.15703 Federated Incomplete Multi-view Clustering with Globally Fused Graph G
        89811, -- 2505.09955 TransPL: VQ-Code Transition Matrices for Pseudo-Labeling of Time Serie
        89884, -- 2505.02056 Handling Imbalanced Pseudolabels for Vision-Language Models with Conce
        90081, -- 2503.08421 Learning to Detect Objects from Multi-Agent LiDAR Scans without Manual
        90101, -- 2411.16064 Multi-Granularity Class Prototype Topology Distillation for Class-Incr
        90121, -- 2503.17984 Taste More, Taste Better: Diverse Data and Strong Model Boost Semi-Sup
        90193, -- 2505.22458 Universal Domain Adaptation for Semantic Segmentation
        90237, -- 2412.11198 GEM: A Generalizable Ego-Vision Multimodal World Model for Fine-Graine
        90290, -- 2408.11280 Exploring Scene Affinity for Semi-Supervised LiDAR Semantic Segmentati
        90307, -- 2502.04074 3D Prior Is All You Need: Cross-Task Few-shot 2D Gaze Estimation
        90343, -- 2503.16997 Steady Progress Beats Stagnation: Mutual Aid of Foundation and Convent
        90347, -- 2503.06467 SP3D: Boosting Sparsely-Supervised 3D Object Detection via Accurate Cr
        90369, -- 2505.19694 Knowledge-Aligned Counterfactual-Enhancement Diffusion Perception for
        90381, -- 2505.16399 Sketchy Bounding-box Supervision for 3D Instance Segmentation
        90386, -- 2411.08753 Which Viewpoint Shows it Best? Language for Weakly Supervising View Se
        90426, -- 2412.01052 CRISP: Object Pose and Shape Estimation with Test-Time Adaptation
        90448, -- 2503.13227 Mind the Gap: Confidence Discrepancy Can Guide Federated Semi-Supervis
        90499, -- 2503.18364 MaSS13K: A Matting-level Semantic Segmentation Benchmark
        90542, -- 2411.10411 Repurposing Stable Diffusion Attention for Training-Free Unsupervised
        90562, -- 2505.09615 UWAV: Uncertainty-weighted Weakly-supervised Audio-Visual Video Parsin
        90582, -- 2503.20211 Synthetic-to-Real Self-supervised Robust Depth Estimation via Learning
        90645, -- 2503.02231 CGMatch: A Different Perspective of Semi-supervised Learning
        90669, -- 2503.16873 Classifier-guided CLIP Distillation for Unsupervised Multi-label Class
        90760, -- 2503.12539 BFANet: Revisiting 3D Semantic Segmentation with Boundary Feature Anal
        90761, -- 2504.11930 Beyond Words: Augmenting Discriminative Richness via Diffusions in Uns
        90772, -- 2503.06277 STiL: Semi-supervised Tabular-Image Learning for Comprehensive Task-Re
        90810, -- 2505.21943 Point-to-Region Loss for Semi-Supervised Point-Based Crowd Counting
        90851, -- 2502.20249 Enhancing 3D Gaze Estimation in the Wild using Weak Supervision with G
        90890, -- 2406.13378 PanDA: Towards Panoramic Depth Anything with Unlabeled Panoramas and M
        90925, -- 2411.10364 Forming Auxiliary High-confident Instance-level Loss to Promote Learni
        90930, -- 2505.03638 Towards Smart Point-and-Shoot Photography
        90986, -- 2503.21099 Learning Class Prototypes for Unified Sparse-Supervised 3D Object Dete
        91016, -- 2503.23747 Consistency-aware Self-Training for Iterative-based Stereo Matching
        91018, -- 2504.14860 Bridge the Gap: From Weak to Full Supervision for Temporal Action Loca
        91414, -- 2410.05782 Reinforcement Learning from Imperfect Corrective Actions and Proxy Rew
        91534, -- 2410.04638 Provable weak-to-strong generalization via benign overfitting
        91611, -- 2410.09348 BANGS: Game-theoretic Node Selection for Graph Self-Training
        91705, -- 2502.10587 Towards Self-Supervised Covariance Estimation in Deep Heteroscedastic
        91766, -- 2410.02646 Learning 3D Perception from Others' Predictions
        91841, -- 2502.15189 Scale-Free Graph-Language Models
        91860, -- 2406.04273 ELFS: Label-Free Coreset Selection with Proxy Training Dynamics
        92213, -- 2405.00746 Leveraging Sub-Optimal Data for Human-in-the-Loop Reinforcement Learni
        92402, -- 2502.10195 Exploring the Camera Bias of Person Re-identification
        92689, -- 2511.01191 SELF-HARMONY: LEARNING TO HARMONIZE SELF-SUPERVISION AND SELF-PLAY IN
        93287, -- 2602.22621 CGSA: Class-Guided Slot-Aware Adaptation for Source-Free Object Detect
        93635, -- 2502.16736 Adaptive Conformal Guidance for Learning under Uncertainty
        93687, -- 2505.11824 Latent Veracity Inference for Identifying Errors in Stepwise Reasoning
        93794, -- 2602.19316 Pay Attention to CTC: Fast and Robust Pseudo-Labelling for Unified Spe
        93809, -- 2512.09365 KGOT: Unified Knowledge Graph and Optimal Transport Pseudo-Labeling fo
        93848, -- 2601.18938 FSD-CAP: Fractional Subgraph Diffusion with Class-Aware Propagation fo
        93856, -- 2604.08553 GNN-as-Judge: Unleashing the Power of LLMs for Graph Learning with GNN
        94490, -- 2509.25787 Self-Evolving Vision-Language Models for Image Quality Assessment via
        94533, -- 2509.24005 Does Weak-to-strong Generalization Happen under Spurious Correlations?
        94591, -- 2509.23067 Semantic Voting: A Self-Evaluation-Free Approach for Efficient LLM Sel
        94803, -- 2602.03634 SPWOOD: Sparse Partial Weakly-Supervised Oriented Object Detection
        94809, -- 2509.26281 Point2RBox-v3: Self-Bootstrapping from Point Annotations via Integrate
        95109, -- 2606.01753 Quality-Guided Semi-Supervised Learning for Medical Image Segmentation
        95217, -- external Vision-Based Panoptic Occupancy Prediction in Urban Environments
        95238, -- external Self-Supervised Point Cloud Single Object Tracking
        95668, -- external Multi-State Consistency Visual Language Model Combine Wavelet Transfor
        95828, -- external DropClick: Semi-Automated One-Click Segmentation for Agricultural Robo
        96217, -- 2602.01389 Instance-Guided Unsupervised Domain Adaptation for Robotic Semantic Se
        96257, -- 2509.23880 Learning Adaptive Pseudo-Label Selection for Semi-Supervised 3D Object
        96559, -- 2503.19625 DynOPETs: A Versatile Benchmark for Dynamic Object Pose Estimation and
        96809, -- 2512.23147 GeoTeacher: Geometry-Guided Semi-Supervised 3D Object Detection
        97039, -- 2412.06491 PPT: Pretraining with Pseudo-Labeled Trajectories for Motion Forecasti
        97109, -- 2603.25298 Connectivity-Aware Representations for Constrained Motion Planning Via
        97403, -- external From Simulation to Deployment: Curriculum-Based Domain Adaptation for
        97476, -- external CMG3D: Compensation towards Modality Gap for Open-Vocabulary Indoor 3D
        97514, -- external Towards Efficient Semi-Supervised Semantic Segmentation for Solid-Stat
        97880, -- external A Cyclic Adaptation-Generalization Framework with Uncertainty-Guided S
        98031, -- 2606.04925 Scene-Centric Unsupervised Video Panoptic Segmentation
        98551, -- 2606.15527 Selective Synergistic Learning for Video Object-Centric Learning
        98619, -- 2104.02246 One Thing One Click: A Self-Training Approach for Weakly Supervised 3D
        98622, -- 2012.10217 SegGroup: Seg-Level Supervision for 3D Instance and Semantic Segmentat
        98656, -- 2208.05688 Semi-supervised Vision Transformers at Scale
        98657, -- 2104.13963 Semi-Supervised Learning of Visual Features by Non-Parametrically Pred
        98837, -- 2606.24457 Lite Any Stereo V2: Faster and Stronger Efficient Zero-Shot Stereo Mat
        98902, -- 2304.04514 DetCLIPv2: Scalable Open-Vocabulary Object Detection Pre-training via
        99112, -- 2506.11142 FARCLUSS: Fuzzy Adaptive Rebalancing and Contrastive Uncertainty Learn
        99239, -- 2606.07419 DisPOSE: Projected Polystochastic Diffusion for Self-Supervised Multi-
        99333, -- 2605.25561 Are We Overconfident in Models and Results for Semi-Supervised 3D Medi
        99380, -- 2605.28239 Learning to Label: A Reinforced Self-Evolving Framework for Semi-super
        99665, -- 2604.20395 SpaCeFormer: Fast Proposal-Free Open-Vocabulary 3D Instance Segmentati
        99702, -- 2601.17469 Identifying and Correcting Label Noise for Robust GNNs via Influence C
        99982, -- 2605.07557 Beyond Distribution Estimation: Simplex Anchored Structural Inference
        100140, -- 2605.17135 Collaborative Learning for Semi-Supervised LiDAR Semantic Segmentation
        100277, -- 2602.03668 MVP-LAM: Learning Action-Centric Latent Action via Cross-Viewpoint Rec
        100440, -- 2510.22785 Self-Calibrated Consistency can Fight Back for Adversarial Robustness
        100450, -- 2605.20538 Continual Segmentation under Joint Nonstationarity
        100627, -- 2605.18156 Semi-LAR: Semi-supervised Contrastive Learning with Linear Attention f
        100993, -- 2411.18905 FedRGL: Robust Federated Graph Learning under Label Noise
        101141, -- 2510.09801 How can we assess human-agent interactions? Case studies in software a
        101236, -- 2605.20766 Diffuse to Detect: Bi-Level Sample Rebalancing with Pseudo-Label Diffu
        101721, -- 2606.16856 Video-Based Optimal Transport for Feedback-Efficient Offline Preferenc
        102103, -- 2505.20178 No Free Lunch: Non-Asymptotic Analysis of Prediction-Powered Inference
        102237, -- 2602.14029 Why Self-Distillation Helps and Hurts: Denoising vs. Signal Forgetting
        102489, -- 2605.27080 Semi-Supervised Gaze Estimation via Disentangled Subspace Contrastive
        102580, -- 2607.03068 PixCon: Clean-Positive Contrastive Learning for Foundation-Model Semi-
        102630, -- 2607.06559 RynnWorld-4D: 4D Embodied World Models for Robotic Manipulation
        103584, -- 2604.07484 ConsistRM: Improving Generative Reward Models via Consistency-Aware Se
        104235, -- 2012.00212 UPFlow: Upsampling Pyramid for Unsupervised Optical Flow Learning
        104236, -- 2211.06018 MDFlow: Unsupervised Optical Flow Learning by Reliable Mutual Knowledg
        104619, -- 2210.13705 An Effective Deep Network for Head Pose Estimation without Keypoints
        104907, -- external A Semi-Supervised Knowledge Distillation Framework for Left Ventricle
        104912, -- external A Virtual Domain Collaborative Learning Framework for Semi-supervised
        104932, -- 2506.20563 AdvMIM: Adversarial Masked Image Modeling for Semi-Supervised Medical
        104933, -- external AffinityUMamba: Uncertainty-Aware Medical Image Segmentation via Proba
        105082, -- external D-CAM: Learning Generalizable Weakly-Supervised Medical Image Segmenta
        105125, -- external Dual Knowledge-Aware Guidance for Source-Free Domain Adaptive Fundus I
        105227, -- external GA-SAM: Geometry-Aware SAM Adaptation with Sparse Annotation-Driven Po
        105246, -- external Graph-based Neighbor-Aware Network for Gaze-Supervised Medical Image S
        105260, -- external HARP: Harmonization and Adaptive Refinement of Pseudo-Labels for Cross
        105321, -- external ISAC: Redefining the Vascular Segmentation Paradigm through Mask Compl
        105324, -- external Iterative Foundation-Dedicated Learning: Optimized Key Frames, Prompts
        105325, -- external ITMatch: Arch-Guided Semi-Supervised Tooth Arrangement via Iterative C
        105349, -- external Leveraging Diffusion Models for Continual Test-Time Adaptation in Fund
        105496, -- 2312.05407 ODES: Online Domain Adaptation with Expert Guidance for Medical Image
        105533, -- 2411.16794 Phase-Informed Tool Segmentation for Manual Small-Incision Cataract Su
        105653, -- 2506.01471 SemiVT-Surge: Semi-Supervised Video Transformer for Surgical Phase Rec
        105670, -- external Source-Free Domain Adaptation for Cross-Modality Cardiac Image Segment
        105673, -- external Sparsely Annotated Medical Image Segmentation via Cross-SAM of 3D and
        105676, -- external Spatial Aggregation for Semi-supervised Active Learning in 3D Medical
        105694, -- 2507.22059 StepAL: Step-aware Active Learning for Cataract Surgical Videos
        105714, -- external Synchronous Inhibition and Activation for Weakly Supervised Semantic S
        105715, -- 2411.04493 Synergy-Guided Regional Supervision of Pseudo Labels for Semi-Supervis
        105733, -- external Temporal Model-Based Federated Active Medical Image Classification
        105766, -- external Towards Robust Retinal Vessel Segmentation via Reducing Open-set Label
        105784, -- external UM-SAM: Unsupervised Medical Image Segmentation using Knowledge Distil
        105888, -- 2305.16713 ReConPatch : Contrastive Patch Representation Learning for Industrial
        106404, -- 2406.00410 Posterior Label Smoothing for Node Classification
        106477, -- 2512.05698 OWL: Unsupervised 3D Object Detection by Occupancy Guided Warm-up and
        106485, -- 2511.22862 Bridging Modalities via Progressive Re-alignment for Multimodal Test-T
        106513, -- 2508.00716 Nested Graph Pseudo-Label Refinement for Noisy Label Domain Adaptation
        106565, -- 2508.02254 Semi-Supervised Semantic Segmentation via Derivative Label Propagation
        106628, -- 2601.05855 Bidirectional Channel-selective Semantic Interaction for Semi-Supervis
        106667, -- 2508.17229 Multi-Metric Preference Alignment for Generative Speech Restoration
        106669, -- 2511.07301 Beyond Boundaries: Leveraging Vision Foundation Models for Source-Free
        106676, -- 2601.11243 Image-Text Knowledge Modeling for Unsupervised Multi-Scenario Person R
        106803, -- 2603.05231 Boosting ASR Robustness via Test-Time Reinforcement Learning with Audi
        106878, -- 2511.12054 UniABG: Unified Adversarial View Bridging and Graph Correspondence for
        106892, -- 2509.15623 PCSR: Pseudo-label Consistency-Guided Sample Refinement for Noisy Corr
        107144, -- 2511.15057 ProPL: Universal Semi-Supervised Ultrasound Image Segmentation via Pro
        107177, -- 2512.00725 ESMC: MLLM-Based Embedding Selection for Explainable Multiple Clusteri
        107363, -- 2508.01254 Self-Enhanced Image Clustering with Cross-Modal Semantic Consistency
        107457, -- 2511.07966 Multi-Modal Assistance for Unsupervised Domain Adaptation on Point Clo
        107506, -- 2511.20225 DiCaP: Distribution-Calibrated Pseudo-labeling for Semi-Supervised Mul
        107574, -- 2511.09319 DualFete: Revisiting Teacher-Student Interactions from a Feedback Pers
        107654, -- 2511.08071 Radar-APLANC: Unsupervised Radar-based Heartbeat Sensing via Augmented
        107756, -- 2512.12667 Open-World Deepfake Attribution via Confidence-Aware Asymmetric Learni
        107770, -- 2511.18075 VK-Det: Visual Knowledge Guided Prototype Learning for Open-Vocabulary
        107776, -- 2504.09525 SimLabel: Similarity-Weighted Semi-supervision for Multi-annotator Lea
        107786, -- 2511.11181 Dynamic Deep Graph Learning for Incomplete Multi-View Clustering with
        107831, -- 2601.12715 RSOD: Reliability-Guided Sonar Image Object Detection with Extremely L
        107894, -- 2511.10068 Perceive, Act and Correct: Confidence Is Not Enough for Hyperspectral
        107939, -- 2601.09531 Bipartite Mode Matching for Vision Training Set Search from a Hierarch
        107982, -- 2511.10003 DBGroup: Dual-Branch Point Grouping for Weakly Supervised 3D Semantic
        108070, -- 2508.06452 TRUST: Leveraging Text Robustness for Unsupervised Domain Adaptation
        108098, -- 2512.22973 YOLO-IOD: Towards Real Time Incremental Object Detection
        108137, -- 2504.00401 Beyond Wide-Angle Images: Structure-to-Detail Video Portrait Correctio
        108163, -- 2508.12409 S5: Scalable Semi-Supervised Semantic Segmentation in Remote Sensing
        108268, -- 2506.11599 A²LC: Active and Automated Label Correction for Semantic Segmentation
        108398, -- 2510.18910 Large Connectome Model: An fMRI Foundation Model of Brain Connectomes
        108431, -- 2603.01524 Better Matching, Less Forgetting: A Quality-Guided Matcher for Transfo
        108561, -- 2512.04524 Prototype-Based Semantic Consistency Alignment for Domain Adaptive Ret
        108815, -- 2605.02638 ViewSAM: Learning View-aware Cross-modal Semantics for Weakly Supervis
        109141, -- 2608.12773 CW-BASS v2: Saturation-Aware Pseudo-Label Selection for Semi-Supervise
        109697, -- 2608.21486 EXPL-FR: Explaining Face Recognition Models via Vision-Language Alignm
        109807, -- 2608.27448 TTPO: Test-Time Policy Optimization
        110016, -- 2506.07801 MultiMatch: Multihead Consistency Regularization Matching for Semi-Sup
        110088, -- 2509.12662 Chat-Driven Text Generation and Interaction for Person Retrieval
        110181, -- external Cross-domain Rumor Detection via Test-Time Adaptation and Large Langua
        110342, -- external Calibrating Pseudo-Labeling with Class Distribution for Semi-supervise
        110654, -- 2509.10004 Unsupervised Hallucination Detection by Inspecting Reasoning Processes
        110826, -- external Correlation-Aware Example Selection for In-Context Learning with Nonsy
        111138, -- 2507.20169 Self-Improvement for Audio Large Language Model using Unlabeled Speech
        111173, -- 2508.08110 Iterative Refinement, Not Training Objective, Makes HuBERT Behave Diff
        111232, -- 2506.11089 Better Pseudo-labeling with Multi-ASR Fusion and Error Correction by S
        111291, -- external Scaling pseudo-labeling data for end-to-end low-resource speech transl
        111459, -- 2505.24446 Pseudo Labels-based Neural Speech Enhancement for the AVSR Task in the
        111461, -- 2506.02621 Cross-attention and Self-attention for Audio-visual Speaker Diarizatio
        111493, -- 2505.14449 Mitigating Subgroup Disparities in Multi-Label Speech Emotion Recognit
        111589, -- external An Effective Anomalous Sound Detection Method Based on Global and Loca
        111634, -- external Grammatical Error Detection on Spontaneous Children's Speech Using Ite
        111676, -- external WhisperMSS: A Two-Stage Framework for Mandarin Singing Transcription a
        111691, -- 2506.07659 Unified Semi-Supervised Pipeline for Automatic Speech Recognition
        111693, -- external R2S: Real-to-Synthetic Representation Learning for Training Speech Rec
        111729, -- 2505.24450 SuPseudo: A Pseudo-supervised Learning Method for Neural Speech Enhanc
        111765, -- 2506.04981 Better Semi-supervised Learning for Multi-domain ASR Through Increment
        111810, -- 2505.24656 MSDA: Combining Pseudo-labeling and Self-Supervision for Unsupervised
        111837, -- external LHCP-ASR: An English Speech Corpus of High-Energy Particle Physics Tal
        111875, -- external Automatic Labeling and Correction of Noisy Labels for Robust Self-Supe
        111882, -- external From Scarcity to Sufficiency: Speech Recognition Pipeline for Zero-res
        111893, -- 2507.12015 EME-TTS: Unlocking the Emphasis and Emotion Link in Speech Synthesis
        111991, -- 2506.03681 Efficient Data Selection for Domain Adaptation of ASR Using Pseudo-Lab
        111996, -- 2506.10653 Robust Unsupervised Adaptation of a Speech Recogniser Using Entropy Mi
        112016, -- 2505.21137 Scaling and Prompting for Improved End-to-End Spoken Grammatical Error
        112417, -- 2407.09047 Cs2K: Class-specific and Class-shared Knowledge Guidance for Increment
        112461, -- 2409.01448 FinePseudo: Improving Pseudo-Labelling through Temporal-Alignablity fo
        112504, -- 2404.11426 SPAMming Labels: Efficient Annotations for the Trackers of Tomorrow
        112521, -- 2409.18961 ProMerge: Prompt and Merge for Unsupervised Instance Segmentation
        112534, -- 2408.15524 Ray-Distance Volume Rendering for Neural Scene Reconstruction
        112552, -- external Point-supervised Panoptic Segmentation via Estimating Pseudo Labels fr
        112573, -- external CSOT: Cross-Scan Object Transfer for Semi-Supervised LiDAR Object Dete
        112583, -- 2409.02101 Towards Real-World Adverse Weather Image Restoration: Enhancing Clearn
        112591, -- 2401.06825 Multi-Memory Matching for Unsupervised Visible-Infrared Person Re-Iden
        112765, -- 2401.13551 Interleaving One-Class and Weakly-Supervised Models with Adaptive Thre
        112816, -- 2405.14841 MOD-UV: Learning Mobile Object Detectors from Unlabeled Videos
        112830, -- external Efficient Active Domain Adaptation for Semantic Segmentation by Select
        112848, -- 2407.08931 Global-Local Collaborative Inference with LLM for Lidar-Based Open-Voc
        112861, -- external Revisiting Domain-Adaptive Object Detection in Adverse Weather by the
        112899, -- 2403.13129 Better Call SAL: Towards Learning to Segment Anything in Lidar
        112959, -- external Better Regression Makes Better Test-time Adaptive 3D Object Detection
        112986, -- 2407.02389 SAFARI: Adaptive Sequence Transformer for Weakly Supervised Referring
        112996, -- 2408.08050 CamoTeacher: Dual-Rotation Consistency Learning for Semi-Supervised Ca
        113018, -- 2407.15451 Domain-Adaptive 2D Human Pose Estimation via Dual Teachers in Extremel
        113025, -- external Co-Student: Collaborating Strong and Weak Students for Sparsely Annota
        113064, -- 2407.11859 Mitigating Background Shift in Class-Incremental Semantic Segmentation
        113078, -- external Hierarchical Unsupervised Relation Distillation for Source Free Domain
        113109, -- 2407.16497 Dynamic Retraining-Updating Mean Teacher for Source-Free Object Detect
        113114, -- 2407.18624 Dual-Decoupling Learning and Metric-Adaptive Thresholding for Semi-Sup
        113135, -- 2407.11356 The Devil is in the Statistics: Mitigating and Exploiting Statistics D
        113142, -- 2407.07586 Simplifying Source-Free Domain Adaptation for Object Detection: Effect
        113146, -- 2306.04621 Flexible Distribution Alignment: Towards Long-tailed Semi-supervised L
        113154, -- 2407.12387 HGL: Hierarchical Geometry Learning for Test-time Adaptation in 3D Poi
        113178, -- 2302.03566 Look Around and Learn: Self-Training Object Detection by Exploration
        113179, -- 2409.08102 Bayesian Self-Training for Semi-Supervised 3D Segmentation
        113189, -- 2402.17891 Weakly Supervised Co-training with Swapping Assignments for Semantic S
        113203, -- 2402.17514 Robust Zero-Shot Crowd Counting and Localization with Adaptive Resolut
        113281, -- 2407.07673 Towards Adaptive Pseudo-label Learning for Semi-Supervised Temporal Ac
        113295, -- external Pseudo-Labelling Should Be Aware of Disguising Channel Activations
        113298, -- 2409.13106 UL-VIO: Ultra-lightweight Visual-Inertial Odometry with Noise Robust T
        113323, -- external Learning to Distinguish Samples for Generalized Category Discovery
        113341, -- 2409.13977 Improving 3D Semi-supervised Learning by Effectively Utilizing All Unl
        113352, -- external GTMS: A Gradient-driven Tree-guided Mask-free Referring Image Segmenta
        113355, -- 2409.13431 Leveraging Text Localization for Scene Text Removal via Text-aware Mas
        113382, -- 2409.05122 PMT: Progressive Mean Teacher via Exploring Temporal Consistency for S
        113424, -- 2408.14371 SelEx: Self-Expertise in Fine-Grained Generalized Category Discovery
        113442, -- external Robust Nearest Neighbors for Source-Free Domain Adaptation under Class
        113476, -- external Continual Learning and Unknown Object Discovery in 3D Scenes via Self-
        113485, -- 2407.19675 Semi-Supervised Teacher-Reference-Student Architecture for Action Qual
        113507, -- 2407.04036 Beyond Pixels: Semi-Supervised Semantic Segmentation with a Multi-scal
        113510, -- 2407.12630 Weighting Pseudo-Labels via High-Activation Feature Index Similarity a
        113535, -- 2403.18600 RAP: Retrieval-Augmented Planner for Adaptive Procedure Planning in In
        113557, -- 2401.01650 De-Confusing Pseudo-Labels in Source-Free Domain Adaptation
        113591, -- 2408.13492 Online Continuous Generalized Category Discovery
        113625, -- 2408.16235 LMT-GP: Combined Latent Mean-Teacher and Gaussian Process for Semi-sup
        113648, -- 2407.11382 "Segment, Lift and Fit: Automatic 3D Shape Labeling from 2D Prompts"
        113654, -- external ExMatch: Self-guided Exploitation for Semi-Supervised Learning with Sc
        113679, -- 2311.11646 Toward Open Vocabulary Aerial Object Detection with CLIP-Activated Stu
        113706, -- external Image Manipulation Detection With Implicit Neural Representation and L
        113973, -- 2609.04250 Motion-Omni: End-to-End Joint Speech and Full-Body Motion for Spoken D
        114264, -- 2601.11475 Generative Scenario Rollouts for End-to-End Autonomous Driving
        114316, -- 2410.08509 A Bayesian Approach to Weakly-supervised Laparoscopic Image Segmentati
        114343, -- external A Weakly-supervised Multi-lesion Segmentation Framework Based on Targe
        114416, -- external Cache-Driven Spatial Test-Time Adaptation for Cross-Modality Medical I
        114455, -- external Confidence-guided Semi-supervised Learning for Generalized Lesion Loca
        114495, -- external Decoupled Training for Semi-supervised Medical Image Segmentation with
        114836, -- external DES-SAM: Distillation-Enhanced Semantic SAM for Cervical Nuclear Segme
        114844, -- 2407.09918 DiffRect: Latent Diffusion Label Rectification for Semi-supervised Med
        114850, -- external Diffusion-Enhanced Transformation Consistency Learning for Retinal Ima
        114860, -- 2407.06585 D-MASTER: Mask Annealed Transformer for Unsupervised Domain Adaptation
        114888, -- 2409.04758 Enabling Text-free Inference in Language-guided Segmentation of Chest
        114902, -- external Enhancing Whole Slide Image Classification with Discriminative and Con
        114934, -- 2406.18995 FedMLP: Federated Multi-Label Medical Image Classification under Task
        114942, -- 2407.04242 Fine-grained Context and Multi-modal Alignment for Freehand 3D Ultraso
        114945, -- external FM-ABS: Promptable Foundation Model Drives Active Barely Supervised Le
        114973, -- external GMoD: Graph-driven Momentum Distillation Framework with Active Percept
        114982, -- 2410.02212 Hard Negative Sample Mining for Whole Slide Image Classification
        115015, -- 2409.12539 Improving cone-beam CT Image Quality with Knowledge Distillation-Enhan
        115022, -- external InstaSAM: Instance-aware Segment Any Nuclei Model with Point Annotatio
        115031, -- 2409.06928 Intrapartum Ultrasound Image Segmentation of Pubic Symphysis and Fetal
        115033, -- external IPLC: Iterative Pseudo Label Correction Guided by SAM for Source-Free
        115060, -- external Learning to Segment Multiple Organs from Multimodal Partially Labeled
        115085, -- 2406.13583 Low-Rank Mixture-of-Experts for Continual Medical Image Segmentation
        115147, -- 2407.17726 Multi-modal Data Binding for Survival Analysis Modeling with Incomplet
        115184, -- external Overlay Mantle-Free for Semi-Supervised Medical Image Segmentation
        115185, -- external Pair Shuffle Consistency for Semi-supervised Medical Image Segmentatio
        115242, -- 2405.16102 Reliable Source Approximation: Source-Free Unsupervised Domain Adaptat
        115266, -- 2409.16728 SDCL: Students Discrepancy-Informed Correction Learning for Semi-super
        115272, -- 2407.05248 Self-Paced Sample Selection for Barely-Supervised Medical Image Segmen
        115283, -- external Semi-supervised Lymph Node Metastasis Classification with Pathology-gu
        115285, -- external Semi-supervised Tubular Structure Segmentation with Cross Geometry and
        115292, -- 2406.19364 SimTxtSeg: Weakly-Supervised Medical Image Segmentation with Simple Te
        115324, -- 2503.13987 Striving for Simplicity: Simple Yet Effective Prior-Aware Pseudo-Label
        115350, -- external Textmatch: Using Text Prompts to Improve Semi-supervised Medical Image
        115351, -- external TextPolyp: Point-supervised Polyp Segmentation with Text Cues
        115400, -- external Unsupervised Domain Adaptation using Soft-Labeled Contrastive Learning
        115403, -- external Unsupervised Ultrasound Image Quality Assessment with Score Consistenc
        115407, -- external VCLIPSeg: Voxel-wise CLIP-Enhanced model for Semi-Supervised Medical I
        115457, -- 2403.19278 CAT: Exploiting Inter-Class Dynamics for Domain Adaptive Object Detect
        115503, -- 2405.20729 Extreme Point Supervised Instance Segmentation
        115506, -- 2402.17323 SDDGR: Stable Diffusion-based Deep Generative Replay for Class Increme
        115517, -- external DIOD: Self-Distillation Meets Object Discovery
        115524, -- 2403.15019 BSNet: Box-Supervised Simulation-assisted Mean Teacher for 3D Instance
        115553, -- external Data-Free Quantization via Pseudo-label Filtering
        115562, -- 2404.00149 VSRD: Instance-Aware Volumetric Silhouette Rendering for Weakly Superv
        115613, -- 2404.04996 Fantastic Animals and Where to Find Them: Segment Any Marine Animal wi
        115644, -- external NightCC: Nighttime Color Constancy via Adaptive Channel Masking
        115663, -- 2303.09373 MAPSeg: Unified Unsupervised Domain Adaptation for Heterogeneous Medic
        115678, -- 2403.13870 ExMap: Leveraging Explainability Heatmaps for Unsupervised Group Robus
        115721, -- external Hierarchical Intra-modal Correlation Learning for Label-free 3D Semant
        115724, -- 2404.08531 Text Prompt with Normality Guidance for Weakly Supervised Video Anomal
        115795, -- 2404.10966 Domain-Specific Block Selection and Paired-View Pseudo-Labeling for On
        115804, -- 2403.11184 DuPL: Dual Student with Trustworthy Progressive Learning for Robust We
        115826, -- 2403.17387 Decoupled Pseudo-labeling for Semi-Supervised Monocular 3D Object Dete
        115827, -- 2404.01518 Temporally Consistent Unbalanced Optimal Transport for Unsupervised Ac
        115843, -- 2402.19463 SeMoLi: What Moves Together Belongs Together
        115886, -- external Weakly-Supervised Audio-Visual Video Parsing with Prototype-based Pseu
        115927, -- 2312.03502 Improving the Generalization of Segmentation Foundation Model under Di
        115928, -- 2404.19384 Pseudo Label Refinery for Unsupervised Domain Adaptation on Cross-data
        115937, -- 2404.08951 Constructing and Exploring Intermediate Domains in Mixed Domain Semi-s
        115942, -- 2403.16194 Pose-Guided Self-Training with Two-Stage Clustering for Unsupervised L
        115952, -- external Molecular Data Programming: Towards Molecule Pseudo-labeling with Syst
        115958, -- 2402.18146 3DSFLabelling: Boosting 3D Scene Flow Estimation by Pseudo Auto-labell
        115999, -- 2406.11189 Frozen CLIP: A Strong Backbone for Weakly Supervised Semantic Segmenta
        116028, -- 2403.01818 AllSpark: Reborn Labeled Features from Unlabeled in Transformer for Se
        116036, -- external A-Teacher: Asymmetric Network for 3D Semi-Supervised Object Detection
        116057, -- 2403.18293 Efficient Test-Time Adaptation of Vision-Language Models
        116070, -- external Uncertainty-Guided Never-Ending Learning to Drive
        116087, -- external Improved Self-Training for Test-Time Adaptation
        116138, -- external Active Domain Adaptation with False Negative Prediction for Object Det
        116152, -- 2403.18442 Backpropagation-free Network for 3D Test-time Adaptation
        116193, -- 2202.04291 L2B: Learning to Bootstrap Robust Models for Combating Label Noise
        116232, -- 2404.00979 PDF: A Probability-Driven Framework for Open World 3D Point Cloud Sema
        116285, -- 2312.12480 Continual-MAE: Adaptive Distribution Masked Autoencoders for Continual
        116306, -- 2311.17902 Language-conditioned Detection Transformer
        116411, -- external A Versatile Framework for Continual Test-Time Domain Adaptation: Balan
        116427, -- 2403.04381 Single-to-Dual-View Adaptation for Egocentric 3D Hand Pose Estimation
        116456, -- 2403.18548 A Semi-supervised Nighttime Dehazing Baseline with Spatial-Frequency A
        116461, -- 2311.17286 LEOD: Label-Efficient Object Detection for Event Cameras
        116476, -- 2403.16788 HPL-ESS: Hybrid Pseudo-Labeling for Unsupervised Event-based Semantic
        116488, -- 2403.10391 CDMAD: Class-Distribution-Mismatch-Aware Debiasing for Class-Imbalance
        116501, -- 2403.20126 ECLIPSE: Efficient Continual Learning in Panoptic Segmentation with Vi
        116520, -- external HINTED: Hard Instance Enhanced Detector with Mixed-Density Feature Fus
        116569, -- 2403.02746 Learning without Exact Guidance: Updating Large-scale High-resolution
        116580, -- 2403.03421 LEAD: Learning Decomposition for Source-free Universal Domain Adaptati
        116581, -- 2404.05063 AUEditNet: Dual-Branch Facial Action Unit Intensity Manipulation with
        116603, -- 2403.11674 Towards Generalizing to Unseen Domains with Few Labels
        116616, -- 2312.02914 Unsupervised Video Domain Adaptation with Masked Pre-Training and Coll
        116628, -- 2403.14198 Unleashing Unlabeled Data: A Paradigm for Cross-View Geo-Localization
        116661, -- 2404.01725 Disentangled Pre-training for Human-Object Interaction Detection
        116756, -- external Fine-grained Prototypical Voting with Heterogeneous Mixup for Semi-sup
        116778, -- 2406.06813 Stable Neighbor Denoising for Source-free Domain Adaptive Segmentation
        116797, -- 2403.07700 CuVLER: Enhanced Unsupervised Object Discoveries through Exhaustive Se
        116857, -- 2311.16510 Source-Free Domain Adaptation with Frozen Multimodal Foundation Model
        116861, -- 2403.18360 Learning CNN on ViT: A Hybrid Model to Explicitly Class-specific Bound
        116868, -- 2403.07705 Robust Synthetic-to-Real Transfer for Stereo Matching
        116927, -- 2308.06412 Taming Self-Training for Open-Vocabulary Object Detection
        116931, -- external Infer from What You Have Seen Before: Temporally-dependent Classifier
        116945, -- 2404.05687 Retrieval-Augmented Open-Vocabulary Object Detection
        117037, -- 2404.16493 Commonsense Prototype for Outdoor Unsupervised 3D Object Detection
        117060, -- 2303.10365 CroSel: Cross Selection of Confident Pseudo Labels for Partial-Label L
        117149, -- external Unveiling the Unknown: Unleashing the Power of Unknown to Known in Ope
        117153, -- 2403.11234 Universal Semi-Supervised Domain Adaptation by Mitigating Common-Class
        117158, -- 2402.18206 Balancing Act: Distribution-Guided Debiasing in Diffusion Models
        117204, -- 2404.01819 Sparse Semi-DETR: Sparse Learnable Queries for Semi-Supervised Object
        117211, -- 2303.17783 Uncertainty-Aware Source-Free Adaptive Image Super-Resolution with Wav
        117217, -- 2305.06973 FreePoint: Unsupervised Point Cloud Instance Segmentation
        117253, -- 2601.05105 UniLiPs: Unified LiDAR Pseudo-Labeling with Geometry-Grounded Dynamic
        117258, -- external Uncertainty-aware 3D Edge Reconstruction with Difference of Gaussians
        117524, -- external CapFrame: Text-Instructed Viewpoint Grounding in 3D Gaussian Scenes vi
        117604, -- 2606.24353 Open-Vocabulary BEV Segmentation with 3D-Aware Geometric Constraints
        117725, -- 2506.18266 YouTube-Occ: Learning Indoor 3D Semantic Occupancy Prediction from You
        117766, -- 2607.04249 Beyond Random Sampling: Distribution-Aware Alignment for Semi-Supervis
        117768, -- 2509.22476 Multi-Channel Uncertainty-Weighted Score Matching for Conditional Diff
        117985, -- 2606.29908 Pondering the Way: Spatial-perceiving World Action Model for Embodied
        118083, -- 2603.16742 When the City Teaches the Car: Label-Free 3D Perception from Infrastru
        118121, -- 2606.30875 The Label Imitation Game: Turing Test Network for Zero-Shot Pseudo-Lab
        118184, -- 2606.31456 Zero-Shot Quantization for Object Detectors using Off-the-Shelf Genera
        118554, -- 2606.31147 WaterGen: Decoupling Scene and Medium in Underwater Image Generation
        118567, -- 2603.08030 QualiTeacher: Quality-Conditioned Pseudo-Labeling for Real-World Image
        118791, -- 2608.25692 CloSeR: Unified Relational Distillation from Closed-Set Teachers for C
        118796, -- external CoT-PL: Chain-of-Thought Pseudo-Labeling for Open-Vocabulary Object De
        118812, -- 2605.31187 From Local Geometry to Global Pseudo-Labeling for Robust Positive–Unla
        118859, -- external Calibrate Before Adapt: Training-Free Pseudo-Label Calibration for Sem
        118860, -- 2607.14560 Breaking the Model Forgetting Cycle in Long-Incremental 3D Object Dete
        118876, -- 2607.04984 Virtual Category-Guided Continual Generalized Category Discovery
        118881, -- external SOVTrack: Open-Vocabulary Multi-Object Tracking with Self-Supervised P
        118890, -- external Rethinking Pseudo-Labels: Multi-Granularity Supervision for Domain Ada
        118907, -- 2608.20710 Geometric Regularization for Long-Tailed Semi-Supervised Learning via
        118946, -- 2512.10244 Solving Semi-Supervised Few-Shot Learning from an Auto-Annotation Pers
        118948, -- 2606.31834 Real-Time Source-Free Object Detection
        118955, -- 2604.06825 RePL: Pseudo-label Refinement for Semi-supervised LiDAR Semantic Segme
        118960, -- 2603.16241 Exclusivity-Guided Mask Learning for Semi-Supervised Crowd Instance Se
        118972, -- 2607.05263 Learning Probabilistic Embeddings for Unsupervised Action Segmentation
        118981, -- 2606.30476 PS-MOT: Cultivating Instance Awareness from Point Seeds for Multi-Obje
        118992, -- 2607.08201 TMI: Text-to-Image Meets Image-to-Image for Complementary Data Synthes
        119025, -- 2606.31373 Domain Adaptive Object Detection via Dual-Stream Bilevel-Cycle Optimiz
        119142, -- 2606.26973 Geometric Gradient Rectification for Safe Open-Set Semi-Supervised Lea
        119215, -- 2507.02393 PLOT: Pseudo-Labeling via Object Tracking for Monocular 3D Object Dete
        119420, -- 2607.21592 Unified Video Dense Prediction from Disjoint Data
        119497, -- 2603.21559 Revisiting Weakly-Supervised Video Scene Graph Generation via Pair Aff
        119841, -- external SnowMaster: Comprehensive Real-world Image Desnowing via MLLM with Mul
        119853, -- external CocoER: Aligning Multi-Level Feature by Competition and Coordination f
        119904, -- external Boosting Point-Supervised Temporal Action Localization through Integra
        119908, -- external Annotation Ambiguity Aware Semi-Supervised Medical Image Segmentation
        119939, -- external Blood Flow Speed Estimation with Optical Coherence Tomography Angiogra
        119971, -- external Boost the Inference with Co-training: A Depth-guided Mutual Learning F
        119992, -- external Dynamic Pseudo Labeling via Gradient Cutting for High-Low Entropy Expl
        120025, -- external Identity-Clothing Similarity Modeling for Unsupervised Clothing Change
        120033, -- external WISNet: Pseudo Label Generation on Unbalanced and Patch Annotated Wast
        120093, -- external Leveraging Temporal Cues for Semi-Supervised Multi-View 3D Object Dete
        120164, -- external Weakly Supervised Semantic Segmentation via Progressive Confidence Reg
        120170, -- external Seek Common Ground While Reserving Differences: Semi-Supervised Image-
        120203, -- external Revisiting Source-Free Domain Adaptation: Insights into Representative
        120239, -- 2506.07087 UCOD-DPL: Unsupervised Camouflaged Object Detection via Dynamic Pseudo
        120322, -- 2506.07857 LogoSP: Local-global Grouping of Superpoints for Unsupervised Semantic
        120350, -- external Distinguish Then Exploit: Source-free Open Set Domain Adaptation via W
        120363, -- 2506.11493 Preserving Clusters in Prompt Learning for Unsupervised Domain Adaptat
        120371, -- 2507.01721 Soft Self-labeling and Potts Relaxations for Weakly-supervised Segment
        120432, -- external Towards Cost-Effective Learning: A Synergy of Semi-Supervised and Acti
        120468, -- external Minimizing Labeled, Maximizing Unlabeled: An Image-Driven Approach for
        120482, -- external Improving Semi-Supervised Semantic Segmentation with Sliced-Wasserstei
        120503, -- external Language-Assisted Debiasing and Smoothing for Foundation Model-Based S
        120510, -- external Revisiting Generative Replay for Class Incremental Object Detection
        120516, -- external ROLL: Robust Noisy Pseudo-label Learning for Multi-View Clustering wit
        120521, -- external Detect Any Mirrors: Boosting Learning Reliability on Large-Scale Unlab
        120531, -- external A Semantic Knowledge Complementarity based Decoupling Framework for Se
        120554, -- external MODfinity: Unsupervised Domain Adaptation with Multimodal Information
        120582, -- external ADU: Adaptive Detection of Unknown Categories in Black-Box Domain Adap
        120594, -- external Self-Supervised Cross-View Correspondence with Predictive Cycle Consis
        120744, -- external SAMIX: Reinforcing SAM2 with Semantic Adapter and Reference Selecting
        120756, -- 2506.04737 Mind the Gap: Transferring Labels to Align Object Detection Datasets
        120930, -- external STAR: Test-Time Adaptation Can Enhance Universal Prompt Learning for V
        120942, -- external Towards Uncertainty-aware Unsupervised Domain Adaptation for Videos an
        120949, -- external Spatial-SAM: Spatially Consistent 3D Electron Microscopy Segmentation
        120955, -- external TVHighlights: LLM-Guided Human-Free Collaborative Training for Video H
        120967, -- external UZ3DVG: Unaided Zero-Shot 3D Visual Grounding with Generated Language
        121225, -- external Measure The Feature Universe: Topology-based Pseudo Labeling and Gravi
        121286, -- external Semi-supervised Echocardiography Video Segmentation via Anchor Semanti
        121310, -- external GaussianMatch: Semi-Supervised Regression with Pseudo-Label Filtering
        121338, -- external Graph Attention Prototypical Network for Robust Few-Shot Classificatio
        121377, -- external Vision-Language Model Guided Source-Free Domain Adaptation via Optimal
        121434, -- external Test-Time Training for LiDAR Semantic Segmentation under Corruption vi
        121596, -- external Beyond Weak Supervision: MLLMs-Guided Graded Knowledge Distillation fo
        121632, -- external Expert-Teacher-Student Collaborative Learning for Domain Adaptive Obje
        121663, -- 2507.02751 Partial Weakly-Supervised Oriented Object Detection
        121711, -- external Revisiting the Necessity of Full Accuracy: Weakly Supervised Object-Le
        121779, -- external Divide, Conquer, and Aggregate: Asymmetric Experts for Class-Imbalance
        121906, -- external D^3FER: Dual Channel and Dual Branch Network for Robust Facial Express
        121914, -- external From Softmax to Dirichlet: Evidential Learning for Semi-supervised Sem
        122506, -- 2609.39102 False Frontiers: Diagnosing and Mitigating Co-Cheating in Self-Evolvin
        122530, -- 2609.18587 Label-free steering: Compressing test-time reinforcement learning into
        124103, -- 2112.01513 OW-DETR: Open-world Detection Transformer
        124147, -- external Cross-Foundation Complementary Learning Systems for Continual Test-Tim
        124234, -- external AdapMatch: Adaptive Bias Decoupling for Semi-Supervised Partial Label
        124235, -- external Progressive Pseudo-label Self-balancing Towards Unsupervised Vision-La
        124241, -- external Beyond Stabilization: Dual-EMA Teachers for Global–Local Semantic Lear
        124245, -- external HIFC-IQA: Train-Free Cross-Domain Image Quality Assessment via Dual-Pr
        124333, -- external Unsupervised Domain Adaptation for Semantic Segmentation Based on Inst
        124483, -- external DARE: Dual-Level Adversarial Learning with Domain-Aware Regularization
        124513, -- external Ultra-DPO: Reimagining LLM Alignment as a Semi-Supervised Task
        124578, -- 2603.19422 Pseudo-Labeling for Unsupervised Domain Adaptation with Kernel GLMs
        124733, -- external Repurposing Video Diffusion Transformers for Cross-View Temporal Objec
        124757, -- external Topology-Aware Optimal Transport for Source-Free Test-Time Adaptation
        124802, -- external FC-DGCN: Deep Graph Convolutional Network for Face Clustering and Reco
        124870, -- external Prediction-only distillation with optimal mixing in ridge-regularized
        124913, -- external Graph Learning from Label Proportions using Topology-Aware Pseudo Labe
        124943, -- 2609.15221 MAST: Label-Efficient, Robust, and Generalizable Sound Detection for B
        125439, -- external Mitigating Confidence Miscalibration in Open-World Semi-Supervised Lea
        125595, -- external Static-to-Dynamic: Animating Still Mattes via Generative Motion for Vi
        125713, -- 2606.11583 Beyond the Golden Teacher: Enhancing Graph Learning through LLM-GNN Co
        125766, -- external CLEAR: Complementary Tripartite Play with Bayesian Calibration for Sem
        125768, -- external Complementary Cache Guidance with Gradient Disentanglement for Continu
        125845, -- external Controlling Temporal Pseudo-Label Marginals for Stable Online Test-Tim
        126204, -- external Test-Time Adaptation via Self-Reinforced Optimal Transport for Zero-Sh
        126247, -- 2609.33668 When Noise Meets Long-Tail: Feature-Threshold Dual Calibration for Rob
        126989, -- external PARI: Policy-Driven Active Residual Intervention for Weakly Supervised
        127069, -- external ViewSAM: Learning View-aware Semantics for Weakly Supervised Cross-vie
        127088, -- 2608.18864 RVLoss: Runoff Vote Loss for Self-Supervised LiDAR Scene Flow Estimati
        127189, -- 2605.23198 Label-Efficient Dataset Pruning via Semi-Supervised Pseudo-Labeling
        127256, -- external Cross-Modal Prior-Guided Training with Visual Foundation Models for Un
        127338, -- external Spectral Energy Allocation Enables Source-Free Domain Adaptation in Ti
        127421, -- external Bridging Sequence and Structure with Unified Domain Adaptation for Dru
        127541, -- external Test-Time Graph Anomaly Detection via Shifted Augmentation with Dynami
        127791, -- external CTRL: Continual Test-Time Reinforcement Learning for Large Language Mo
        128064, -- 2605.04594 HeterSEED: Semantics–Structure Decoupling for Heterogeneous Graph Lear
        128117, -- external Domain-Conditioned Class Imbalance: Why Global Class Balance Fails Acr
        128155, -- external FIND: Frequency Invariance Disentanglement for Test-Time Adaptation in
        128245, -- external FreeAct: Demonstration-Free Robot Adaptation via Action-Grounded Gener
        128479, -- external Nüwa.RNA: An RNA Foundation Model for Unified Representation with Deep
        128622, -- 2610.16261 Hardware-Friendly Token-Group Activation Quantization for Low-Bit Mamb
        128623, -- 2610.15846 Mobility Helps Learning: Unsupervised Model Adaptation for Object Reco
        128733, -- 2605.11857 Beyond Parameter Aggregation: Semantic Consensus for Federated Fine-Tu
        129023, -- external Stability-Aware Self-Training for CLIP under Cross-Modal Anchoring Mis
        129061, -- external Trajectory-Matching Meta Pseudo-Labeling for Semi-Supervised Learning
        129285, -- 2609.34374 ABC-Align: Prediction-Powered Alignment with Adaptive Bias Control
        129341, -- 2605.19976 RECIPE: Procedural Planning via Grounding in Instructional Video
        129410, -- external Trainable Topology Supervision under Structurally Unreliable Pseudo Su
        129443, -- external Exploiting Negative Multi-Cluster Structure in Class-Wise Embeddings f
        129487, -- external HoloGene: Learning to Lift Sliced Spatial Transcriptomics to Holistic
        129797, -- external Online Bayesian Recalibration of Brain–Computer Interfaces with Langua
        129928, -- external QB-Highlights: Quality-Guided Budgeted Highlight Detection in Videos w
        130368, -- external BayesAT: Bayes-Guided Progressive Distillation for Semi-Supervised Adv
        130706, -- external Training-Free Active Test-Time Adaptation for Vision-Language Models
        130754, -- external Parametric Meets Non-parametric: Bridging Dual Prediction Spaces for S
        130783, -- 2605.19063 Mapping Uncharted Symmetries: Machine Discovery in Combinatorics
        130887, -- external PLLS-CP: Unsupervised Hallucination Detection with Layer Selection and
        131283, -- 2606.19737 Calibration without labels in multiple testing
        131909, -- 2611.04949 HERIT: Enabling Global Access to Hanja-to-English Historical Translati
        132073  -- 2001.07685 FixMatch: Simplifying Semi-Supervised Learning with Consistency and Co
  );

DELETE FROM paper_method_exclusions x
USING pseudo_labeling_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM pseudo_labeling_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM pseudo_labeling_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE pseudo_labeling_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'pseudo-labeling'
  AND p.id IN (
        12185, -- 2212.11270 Generalized Decoding for Pixel, Image, and Language
        21127, -- 2310.00161 Region-centric Image-Language Pretraining for Open-Vocabulary Detectio
        125098, -- external Efficient Multi-Source Prompt Adaptation for Cross-Domain Open-Vocabul
        125182, -- 2505.12358 AbFlowNet: Optimizing Antibody-Antigen Binding Energy via Diffusion-GF
        126684  -- 2608.10595 DegradeQuery: Counterfactual Tuple Pretraining for Context-Aware PROTA
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Taxonomy gap fill 2026-11-09: mentions pseudo-labeling only to say the method does without it'
FROM pseudo_labeling_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING pseudo_labeling_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING pseudo_labeling_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- temporal-convolutional-network: 33 links, 8 exclusions.
CREATE TEMP TABLE temporal_convolutional_network_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'temporal-convolutional-network'
  AND p.id IN (
        1503, -- 1809.07454 Conv-TasNet: Surpassing Ideal Time-Frequency Magnitude Masking for Spe
        1547, -- 1810.06682 Trellis Networks for Sequence Modeling
        1809, -- 1902.01659 Early Recognition of Sepsis with Gaussian Process Temporal Convolution
        3024, -- 2001.08702 Lipreading using Temporal Convolutional Networks
        5023, -- 2102.06200 Efficient neural networks for real-time modeling of analog dynamic ran
        5080, -- 2102.11603 SeqNet: Learning Descriptors for Sequence-based Hierarchical Place Rec
        17880, -- 2306.16922 The Expressive Leaky Memory Neuron: an Efficient and Expressive Phenom
        18836, -- 2308.00533 A Novel Temporal Multi-Gate Mixture-of-Experts Approach for Vehicle Tr
        19619, -- 2308.11358 How Much Temporal Long-Term Context is Needed for Action Segmentation?
        20637, -- 2309.10910 Amplifying Pathological Detection in EEG Signaling Pathways through Cr
        24545, -- 2312.05605 TCNCA: Temporal Convolution Network with Chunked Attention for Scalabl
        31718, -- 2405.15755 ETTrack: Enhanced Temporal Motion Predictor for Multi-Object Tracking
        43708, -- 2502.03430 A Temporal Convolutional Network-Based Approach and a Benchmark Datase
        63660, -- 2512.14106 HydroGEM: A Self Supervised Zero Shot Hybrid TCN Transformer Foundatio
        65195, -- 2511.10680 LAD-BNet: Lag-Aware Dual-Branch Networks for Real-Time Energy Forecast
        67216, -- 2510.00726 CroSTAta: Cross-State Transition Attention Transformer for Robotic Man
        71870, -- 2506.16073 TD3Net: A Temporal Densely Connected Multi-Dilated Convolutional Netwo
        76354, -- 2409.11862 Location based Probabilistic Load Forecasting of EV Charging Sites: De
        76537, -- 2408.12408 An Evaluation of Deep Learning Models for Stock Market Trend Predictio
        78969, -- 2305.17473 A Comprehensive Overview and Comparative Analysis on Deep Learning Mod
        80029, -- 2202.05735 SleepPPG-Net: a deep learning algorithm for robust sleep staging from
        80204, -- 2202.07036 Benchmarking Online Sequence-to-Sequence and Character-based Handwriti
        80951, -- 2012.11806 Graph and Temporal Convolutional Networks for 3D Multi-person Pose Est
        81900, -- 1810.07550 The Newton Scheme for Deep Learning
        82076, -- 1803.01271 An Empirical Evaluation of Generic Convolutional and Recurrent Network
        83626, -- 2605.19990 Minimalist Visual Inertial Odometry
        96310, -- 2604.10262 Deep Photonic Reservoir Computer Meets UAV Control: An Ultra-Fast Lear
        96337, -- 2509.14063 Language Conditioning Improves Accuracy of Aircraft Goal Prediction in
        96721, -- 2605.28412 Tactile-Proprioceptive Sensor Fusion for Contact Wrench Estimation in
        96739, -- external GIMloco: Generic Internal Model-Based Locomotion for Quadruped Robots
        104172, -- 2004.11822 3D Human Pose Estimation using Spatio-Temporal Networks with Explicit
        111218, -- external Temporal Convolutional Network with Smoothed and Weighted Losses for D
        132075  -- 1608.08242 Temporal Convolutional Networks: A Unified Approach to Action Segmenta
  );

DELETE FROM paper_method_exclusions x
USING temporal_convolutional_network_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM temporal_convolutional_network_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM temporal_convolutional_network_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE temporal_convolutional_network_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'temporal-convolutional-network'
  AND p.id IN (
        150, -- 1502.01710 Text Understanding from Scratch
        1423, -- 1808.00928 Learning Actionable Representations from Visual Observations
        3994, -- 2008.02531 Self-supervised Video Representation Learning Using Inter-intra Contra
        15945, -- 2305.13386 Can LLMs facilitate interpretation of pre-trained language models?
        51508, -- 2506.21338 AGTCNet: A Graph-Temporal Approach for Principled Motor Imagery EEG Cl
        84112, -- 2509.24850 PHASE-Net: Physics-Grounded Harmonic Attention System for Efficient Re
        107818, -- 2511.05859 Predicting the Future by Retrieving the Past
        117366  -- external A Lightweight Multi-Variable Spatio-Temporal Convolutional Framework f
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Taxonomy gap fill 2026-11-09: TCN means another model, or the mention is a passing one'
FROM temporal_convolutional_network_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING temporal_convolutional_network_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING temporal_convolutional_network_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- 3d-convolution: 137 links, 29 exclusions.
CREATE TEMP TABLE conv3d_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = '3d-convolution'
  AND p.id IN (
        180, -- 1504.07469 Compact CNN for Indexing Egocentric Videos
        722, -- 1705.07750 Quo Vadis, Action Recognition? A New Model and the Kinetics Dataset
        808, -- 1707.06783 3DCNN-DQN-RNN: A Deep Reinforcement Learning Framework for Semantic Pa
        886, -- 1709.07330 H-DenseUNet: Hybrid Densely Connected UNet for Liver and Tumor Segment
        990, -- 1711.10305 Learning Spatio-Temporal Representation with Pseudo-3D Residual Networ
        995, -- 1711.11248 A Closer Look at Spatiotemporal Convolutions for Action Recognition
        1073, -- 1801.09522 Multichannel Sound Event Detection Using 3D Convolutional Neural Netwo
        1176, -- 1803.08669 Pyramid Stereo Matching Network
        1645, -- 1811.09795 Self-Supervised Video Representation Learning with Space-Time Cubic Pu
        2041, -- 1904.11407 DynamoNet: Dynamic Action and Motion Network
        2138, -- 1905.10835 A multi-path 2.5 dimensional convolutional neural network system for s
        2223, -- 1906.02792 Attention is all you need for Videos: Self-attention based Video Summa
        2309, -- 1907.01131 Learnable Gated Temporal Shift Module for Deep Video Inpainting
        3166, -- 2003.00832 An End-to-End Visual-Audio Attention Network for Emotion Recognition i
        3244, -- 2003.10685 Deep Line Art Video Colorization with a Few References
        3386, -- 2004.09548 AANet: Adaptive Aggregation Network for Efficient Stereo Matching
        4009, -- 2008.04838 TransNet V2: An effective deep network architecture for fast shot tran
        4720, -- 2012.06178 Detailed 3D Human Body Reconstruction from Multi-view Images Combining
        5015, -- 2102.05095 Is Space-Time Attention All You Need for Video Understanding?
        5026, -- 2102.06515 Mediastinal lymph nodes segmentation using 3D convolutional neural net
        5242, -- 2103.11511 MoViNets: Mobile Video Networks for Efficient Video Recognition
        5536, -- 2104.09648 Memory Efficient 3D U-Net with Reversible Mobile Inverted Bottlenecks
        5546, -- 2104.10157 VideoGPT: Video Generation using VQ-VAE and Transformers
        5804, -- 2105.14071 Classification of Brain Tumours in MR Images using Deep Spatiospatial
        7012, -- 2110.10640 OSS-Net: Memory Efficient High Resolution Semantic Segmentation of 3D
        7686, -- 2201.04676 UniFormer: Unified Transformer for Efficient Spatiotemporal Representa
        7775, -- 2201.10849 Predicting Knee Osteoarthritis Progression from Structural MRI using D
        8698, -- 2204.06228 Do You Really Mean That? Content Driven Audio-Visual Deepfake Dataset
        9442, -- 2206.05275 Spatial-temporal Concept based Explanation of 3D ConvNets
        9489, -- 2206.07696 Diffusion Models for Video Prediction and Infilling
        9647, -- 2206.15073 COVID Detection and Severity Prediction with 3D-ConvNeXt and Custom Pr
        9690, -- 2207.02094 Is a PET all you need? A multi-modal study for Alzheimer's disease usi
        9858, -- 2207.10409 Sequence Models for Drone vs Bird Classification
        12500, -- 2301.10100 Using a Waffle Iron for Automotive Point Cloud Semantic Segmentation
        13566, -- 2303.04439 A Light Weight Model for Active Speaker Detection
        13589, -- 2303.04995 Text-Visual Prompting for Efficient 2D Temporal Video Grounding
        13809, -- 2303.09040 Hybrid Spectral Denoising Transformer with Guided Attention
        13839, -- 2303.09551 SurroundOcc: Multi-Camera 3D Occupancy Prediction for Autonomous Drivi
        15165, -- 2305.01979 Glitch in the Matrix: A Large Scale Benchmark for Content Driven Audio
        15560, -- 2305.08585 Toward Moiré-Free and Detail-Preserving Demosaicking
        17616, -- 2306.11316 Unfolding Framework with Prior of Convolution-Transformer Mixture and
        17714, -- 2306.13474 Efficient Online Processing with Deep Neural Networks
        18248, -- 2307.07469 Interactive Spatiotemporal Token Attention Network for Skeleton-based
        18274, -- 2307.07938 CVSformer: Cross-View Synthesis Transformer for Semantic Scene Complet
        18377, -- 2307.09420 Measuring Student Behavioral Engagement using Histogram of Actions
        19992, -- 2308.16909 StyleInV: A Temporal Style Modulated Inversion Network for Uncondition
        20918, -- 2309.14616 NDC-Scene: Boost Monocular 3D Semantic Scene Completion in Normalized
        21675, -- 2310.06008 CoBEVFusion: Cooperative Perception with LiDAR-Camera Bird's-Eye View
        22012, -- 2310.10038 Smart City Transportation: Deep Learning Ensemble Approach for Traffic
        24334, -- 2312.03133 Predicting Bone Degradation Using Vision Transformer and Synthetic Cel
        26211, -- 2401.13147 Deep Spatiotemporal Clutter Filtering of Transthoracic Echocardiograph
        26387, -- 2401.15739 SegmentAnyTree: A sensor and platform agnostic deep learning model for
        26410, -- 2401.16102 Flexible Parallel Neural Network Architecture Model for Early Predicti
        27099, -- 2402.06107 Multiple Instance Learning for Cheating Detection and Localization in
        28742, -- 2403.07807 StyleGaussian: Instant 3D Style Transfer with Gaussian Splatting
        33377, -- 2406.14130 ExVideo: Extending Video Diffusion Models via Parameter-Efficient Post
        33827, -- 2406.19568 What Matters in Detecting AI-Generated Videos like Sora?
        34648, -- 2407.10632 Bidirectional Stereo Image Compression with Cross-Dimensional Entropy
        35981, -- 2408.10198 MeshFormer: High-Quality Mesh Generation with 3D-Guided Reconstruction
        39393, -- 2410.23132 Revisiting MAE pre-training for 3D medical image segmentation
        39621, -- 2411.02441 Cross-D Conv: Cross-Dimensional Transferable Knowledge Base via Fourie
        42707, -- 2501.05961 Swin-X2S: Reconstructing 3D Shape from 2D Biplanar X-ray with Swin Tra
        43099, -- 2501.12810 Machine Learning Modeling for Multi-order Human Visual Motion Processi
        46768, -- 2503.20168 EVolSplat: Efficient Volume-based Gaussian Splatting for Urban View Sy
        47648, -- 2504.10068 Mavors: Multi-granularity Video Representation for Multimodal Large La
        47729, -- 2504.11289 UniAnimate-DiT: Human Image Animation with Large-Scale Video Diffusion
        54271, -- 2511.13001 Medal S: Spatio-Textual Prompt Model for Medical Segmentation
        57051, -- 2603.25730 PackForcing: Short Video Training Suffices for Long Video Sampling and
        57152, -- 2603.26661 GaussianGPT: Towards Autoregressive 3D Gaussian Scene Generation
        60073, -- 2603.01174 VP-Hype: A Hybrid Mamba-Transformer Framework with Visual-Textual Prom
        60418, -- 2602.19161 Flash-VAED: Plug-and-Play VAE Decoders for Efficient Video Generation
        63504, -- 2512.17774 MedNeXt-v2: Scaling 3D ConvNeXts for Large-Scale Supervised Representa
        63895, -- 2512.09471 Temporal-Spatial Tubelet Embedding for Cloud-Robust MSI Reconstruction
        64609, -- 2511.19229 Learning Plug-and-play Memory for Guiding Video Diffusion Models
        65077, -- 2511.10040 LoG3D: Ultra-High-Resolution 3D Shape Modeling via Local-to-Global Par
        65283, -- 2511.05833 TYrPPG: Uncomplicated and Enhanced Learning Capability rPPG for Remote
        68819, -- 2509.02415 Decoupling Bidirectional Geometric Representations of 4D cost volume w
        68978, -- 2509.00169 Generative Latent Space Dynamics of Electron Density
        69748, -- 2508.09650 TOTNet: Occlusion-Aware Temporal Tracking for Robust Ball Detection in
        71081, -- 2507.12166 RadioDiff-3D: A 3Dtimes3D Radio Map Dataset and Generative Diffusion B
        71270, -- 2507.07795 Robust and Generalizable Heart Rate Estimation via Deep Learning for R
        71813, -- 2506.17759 LoLA-SpecViT: Local Attention SwiGLU Vision Transformer with LoRA for
        72067, -- 2506.09735 MPFNet: A Multi-Prior Fusion Network with a Progressive Training Strat
        72476, -- 2506.03193 Human Fall Detection using Transfer Learning-based 3D CNN
        77088, -- 2406.03359 SuperFormer: Volumetric Transformer Architectures for MRI Super-Resolu
        79137, -- 2304.06116 AutoShot: A Short Video Dataset and State-of-the-Art Shot Boundary Det
        79899, -- 2206.07293 FRCRN: Boosting Feature Representation using Frequency Recurrence for
        81043, -- 2010.13338 EDNet: Efficient Disparity Estimation with Cost Volume Combination and
        81077, -- 2010.06163 Bridging 2D and 3D Segmentation Networks for Computation Efficient Vol
        81341, -- 2005.02142 Suspicious Behavior Detection on Shoplifting Cases for Crime Preventio
        81405, -- 2003.10432 Atlas: End-to-End 3D Scene Reconstruction from Posed Images
        81623, -- 1903.02306 Video-based surgical skill assessment using 3D convolutional neural ne
        81660, -- 1907.11454 Using 3D Convolutional Neural Networks to Learn Spatiotemporal Feature
        81678, -- 1902.06701 HybridSN: Exploring 3D-2D CNN Feature Hierarchy for Hyperspectral Imag
        81861, -- 1811.11187 Scan2CAD: Learning CAD Model Alignment in RGB-D Scans
        82021, -- 1805.02877 Low-Latency Human Action Recognition with Weighted Multi-Region Convol
        82140, -- 1711.09577 Can Spatiotemporal 3D CNNs Retrace the History of 2D CNNs and ImageNet
        84373, -- 2512.09373 FUSER: Feed-Forward Multiview 3D Registration Transformer and SE(3)$^N
        87729, -- 2503.03259 BANet: Bilateral Aggregation Network for Mobile Stereo Matching
        88499, -- 2411.17845 CABLD: Contrast-Agnostic Brain Landmark Detection with Consistency-Bas
        90462, -- 2503.02745 ArcPro: Architectural Programs for Structured 3D Abstraction of Sparse
        90498, -- 2503.12009 UniMamba: Unified Spatial-Channel Representation Learning with Group-E
        95764, -- 2603.14522 One-Policy-Fits-All: Geometry-Aware Action Latents for Cross-Embodimen
        96141, -- external EdgeGrasp: Enhancing Edge Perception for 7-DoF Grasping Pose Estimatio
        96837, -- 2505.16249 Manipulating Elasto-Plastic Objects with 3D Occupancy and Learning-Bas
        98274, -- 1904.08755 4D Spatio-Temporal ConvNets: Minkowski Convolutional Neural Networks
        98280, -- 2011.10033 Cylindrical and Asymmetrical 3D Convolution Networks for LiDAR Segment
        98629, -- 2107.13824 VMNet: Voxel-Mesh Network for Geodesic-Aware 3D Semantic Segmentation
        98632, -- 2206.10555 LargeKernel3D: Scaling up Kernels in 3D Sparse CNNs
        98642, -- 2403.14418 OA-CNNs: Omni-Adaptive Sparse CNNs for 3D Semantic Segmentation
        99486, -- 2606.25546 Disease-Centric Vision-Language Pretraining with Hybrid Visual Encodin
        102668, -- 2008.05765 Revisiting Temporal Modeling for Video Super-resolution
        103852, -- 2302.02858 TR3D: Towards Real-Time Indoor 3D Object Detection
        103910, -- 1905.02693 3D Packing for Self-Supervised Monocular Depth Estimation
        104345, -- 1801.04260 Conditional Probability Models for Deep Image Compression
        104352, -- 1910.06244 Neural Image Compression via Non-Local Attention Optimization and Impr
        105474, -- 2507.02847 MvHo-IB: Multi-View Higher-Order Information Bottleneck for Brain Diso
        105512, -- 2507.18112 Parameter-Efficient Fine-Tuning of 3D DDPM for MRI Image Generation Us
        105558, -- external PRGNN: Pyramidal Region Graph Neural Network for Region-Based Brain PE
        106941, -- 2511.06831 DeepRWCap: Neural-Guided Random-Walk Capacitance Solver for IC Design
        107973, -- 2511.09352 Spatio-Temporal Context Learning with Temporal Difference Convolution
        108609, -- 2111.15483 ST-MFNet: A Spatio-Temporal Multi-Flow Network for Frame Interpolation
        109468, -- 1804.02505 MVSNet: Depth Inference for Unstructured Multi-view Stereo
        113104, -- 2402.13729 Hybrid Video Diffusion Models with 2D Triplane and 3D Wavelet Represen
        114927, -- 2406.14014 Feature Fusion Based on Mutual-Cross-Attention Mechanism for EEG Emoti
        115152, -- external Multi-modality 3D CNN Transformer for Assisting Clinical Decision in I
        115200, -- external PET Image Denoising Based on 3D Denoising Diffusion Probabilistic Mode
        115385, -- 2409.08492 Tri-Plane Mamba: Efficiently Adapting Segment Anything Model for 3D Me
        115423, -- external Weak-supervised Attention Fusion Network for Carotid Artery Vessel Wal
        115671, -- 2403.15173 LSK3DNet: Towards Effective and Efficient 3D Perception with Large Spa
        116418, -- 2402.17562 An Empirical Study of the Generalization Ability of Lidar 3D Object De
        116875, -- external Cross-Dimension Affinity Distillation for 3D EM Neuron Segmentation
        119926, -- 2408.17065 Generalizing Deepfake Video Detection with Plug-and-Play: Video-Level
        120157, -- external SuperLightNet: Lightweight Parameter Aggregation Network for Multimoda
        120963, -- external FlashDecoder: Real-Time Latent-to-Pixel Streaming Decoder with Transfo
        120972, -- external $\alpha$Matte4K & $\mu$Matting: Dataset and Model for Ultra-Micro Prec
        132074  -- 1412.0767 Learning Spatiotemporal Features with 3D Convolutional Networks
  );

DELETE FROM paper_method_exclusions x
USING conv3d_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM conv3d_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM conv3d_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE conv3d_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = '3d-convolution'
  AND p.id IN (
        442, -- 1608.04337 Design of Efficient Convolutional Layers using Single Intra-channel Co
        2912, -- 1912.03538 Context R-CNN: Long Term Temporal Context for Per-Camera Object Detect
        5306, -- 2103.15691 ViViT: A Video Vision Transformer
        9893, -- 2207.12148 Applying Spatiotemporal Attention to Identify Distracted and Drowsy Dr
        27695, -- 2402.13252 Improving Robustness for Joint Optimization of Camera Poses and Decomp
        28689, -- 2403.06977 VideoMamba: State Space Model for Efficient Video Understanding
        28874, -- 2403.09626 Video Mamba Suite: State Space Model as a Versatile Alternative for Vi
        29962, -- 2404.03650 OpenNeRF: Open Set 3D Neural Scene Segmentation with Pixel-Wise Featur
        31278, -- 2405.08344 No Time to Waste: Squeeze Time into Channel for Mobile Video Understan
        34017, -- 2407.02040 ScaleDreamer: Scalable Text-to-3D Synthesis with Asynchronous Score Di
        34029, -- 2407.02159 SparseSSP: 3D Subcellular Structure Prediction from Sparse-View Transm
        46749, -- 2503.19904 Tracktention: Leveraging Point Tracking to Attend Videos Faster and Be
        52149, -- 2508.00823 IGL-Nav: Incremental 3D Gaussian Localization for Image-goal Navigatio
        55848, -- 2602.04220 Adaptive 1D Video Diffusion Autoencoder
        59615, -- 2603.11071 TinyNav: End-to-End TinyML for Real-Time Autonomous Navigation on Micr
        64133, -- 2512.04358 MAFNet:Multi-frequency Adaptive Fusion Network for Real-time Stereo Ma
        66543, -- 2510.10779 Structured Spectral Graph Representation Learning for Multi-label Abno
        69872, -- 2508.07811 DiTVR: Zero-Shot Diffusion Transformer for Video Restoration
        71398, -- 2507.04559 MambaVideo for Discrete Video Tokenization with Channel-Split Quantiza
        77220, -- 2405.14527 ArchesWeather: An efficient AI weather forecasting model at 1.5° resol
        79355, -- 2302.08474 Efficient 3D Object Reconstruction using Visual Transformers
        81196, -- 2007.12140 HITNet: Hierarchical Iterative Tile Refinement Network for Real-time S
        87774, -- 2502.17288 GaussianFlowOcc: Sparse and Weakly Supervised Occupancy Estimation usi
        98630, -- 2007.13138 Virtual Multi-view Fusion for 3D Semantic Segmentation
        115311, -- 2407.15433 Spatial-Division Augmented Occupancy Field for Bone Shape Reconstructi
        117481, -- 2606.31636 LiteMatch: Lightweight Zero-Shot Stereo Matching via Cost Volume Stabi
        120338, -- external AniGrad: Anisotropic Gradient-Adaptive Sampling for 3D Reconstruction
        127382, -- external FusionNeXt: Sequence-First 3D Multi-Modal Fusion in the Era of LLMs
        131077  -- external Coarse-to-Fine 3D MRI Reconstruction via Resolution-Agnostic Neural Op
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Taxonomy gap fill 2026-11-09: mentions 3D convolution in passing without using or studying it'
FROM conv3d_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING conv3d_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING conv3d_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- backpropagation: 301 links, 511 exclusions.
CREATE TEMP TABLE backpropagation_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'backpropagation'
  AND p.id IN (
        75, -- 1401.4082 Stochastic Backpropagation and Approximate Inference in Deep Generativ
        114, -- 1409.7495 Unsupervised Domain Adaptation by Backpropagation
        414, -- 1606.06871 A Comprehensive Study of Deep Bidirectional LSTM RNNs for Acoustic Mod
        603, -- 1703.01827 All You Need is Beyond a Good Init: Exploring Better Solution for Trai
        992, -- 1711.10455 Backprop as Functor: A compositional perspective on supervised learnin
        1021, -- 1712.06567 Deep Neuroevolution: Genetic Algorithms Are a Competitive Alternative
        1287, -- 1805.07039 A Theoretical Explanation for Perplexing Behaviors of Backpropagation-
        1338, -- 1806.05298 Apuntes de Redes Neuronales Artificiales
        1346, -- 1806.07366 Neural Ordinary Differential Equations
        1565, -- 1810.10667 Truncated Back-propagation for Bilevel Optimization
        1830, -- 1902.06853 On the Impact of the Activation Function on Deep Neural Networks Train
        2243, -- 1906.04554 Principled Training of Neural Networks with Direct Feedback Alignment
        3036, -- 2001.10331 f-BRS: Rethinking Backpropagating Refinement for Interactive Segmentat
        3084, -- 2002.03629 Accelerating Feedforward Computation via Parallel Nonlinear Equation S
        3191, -- 2003.03384 AutoML-Zero: Evolving Machine Learning Algorithms From Scratch
        3258, -- 2003.11666 Pipelined Backpropagation at Scale: Training Large Models without Batc
        3649, -- 2006.01475 Light-in-the-loop: using a photonics co-processor for scalable trainin
        3788, -- 2006.12878 Direct Feedback Alignment Scales to Modern Deep Learning Tasks and Arc
        4349, -- 2010.06891 Memformer: A Memory-Augmented Transformer for Sequence Modeling
        4724, -- 2012.06373 Hardware Beyond Backpropagation: a Photonic Co-Processor for Direct Fe
        4865, -- 2101.02115 Adversarial Robustness by Design through Analog Computing and Syntheti
        4909, -- 2101.06983 Scaling Deep Contrastive Learning Batch Size under Memory Limited Setu
        5123, -- 2103.01189 Learners' Languages
        5904, -- 2106.03645 Photonic Differential Privacy with Direct Feedback Alignment
        6067, -- 2106.11086 Analytically Tractable Bayesian Deep Q-Learning
        6201, -- 2107.03759 Analytically Tractable Hidden-States Inference in Bayesian Neural Netw
        6454, -- 2108.09081 FedSkel: Efficient Federated Learning on Heterogeneous Systems with Sk
        7139, -- 2111.01760 Increasing Liquid State Machine Performance with Edge-of-Chaos Dynamic
        7276, -- 2111.11124 Mesa: A Memory-saving Training Framework for Transformers
        7651, -- 2201.01965 Efficient Global Optimization of Two-layer ReLU Networks: Quadratic-ti
        7814, -- 2201.13195 Memory-Efficient Backpropagation through Large Linear Layers
        7998, -- 2202.08587 Gradients without Backpropagation
        8992, -- 2205.05198 Reducing Activation Recomputation in Large Transformer Models
        9309, -- 2206.00164 A Theoretical Framework for Inference Learning
        9654, -- 2206.15472 On-Device Training Under 256KB Memory
        10075, -- 2208.08503 Learning with Local Gradients at the Edge
        10399, -- 2209.11883 Hebbian Deep Learning Without Feedback
        11068, -- 2210.14593 Scaling Laws Beyond Backpropagation
        11530, -- 2211.12485 HyperTuning: Toward Adapting Large Language Models without Back-propag
        12229, -- 2212.13345 The Forward-Forward Algorithm: Some Preliminary Investigations
        12447, -- 2301.08110 AtMan: Understanding Transformer Predictions Through Memory Efficient
        12616, -- 2301.12195 BAFFLE: A Baseline of Backpropagation-Free Federated Learning
        12782, -- 2302.01228 Dual Propagation: Accelerating Contrastive Hebbian Learning with Dyadi
        12993, -- 2302.04852 SparseProp: Efficient Sparse Backpropagation for Faster Training of Ne
        13018, -- 2302.05440 Forward Learning with Top-Down Feedback: Empirical and Analytical Char
        13338, -- 2302.13939 SpikeGPT: Generative Pre-trained Language Model with Spiking Neural Ne
        13363, -- 2302.14311 Towards Memory- and Time-Efficient Backpropagation for Training Spikin
        13471, -- 2303.01904 EcoTTA: Memory-Efficient Continual Test-time Adaptation via Self-disti
        13899, -- 2303.10725 SIESTA: Efficient Online Continual Learning with Sleep
        14078, -- 2303.13703 End-to-End Diffusion Latent Optimization Improves Classifier Guidance
        14326, -- 2303.17732 Optimal Input Gain: All You Need to Supercharge a Feed-Forward Neural
        14593, -- 2304.04824 Gradient-based Uncertainty Attribution for Explainable Bayesian Deep L
        14867, -- 2304.11042 Backpropagation-free Training of Deep Physical Neural Networks
        15586, -- 2305.08960 One Forward is Enough for Neural Network Training via Likelihood Ratio
        15847, -- 2305.12393 Layer Collaboration in the Forward-Forward Algorithm
        16063, -- 2305.14314 QLoRA: Efficient Finetuning of Quantized LLMs
        16505, -- 2305.18353 Emergent representations in networks trained with the Forward-Forward
        16610, -- 2305.19167 Reduced Precision Floating-Point Optimization for Deep Neural Network
        16703, -- 2306.00045 Lottery Tickets in Evolutionary Optimization: On Sparse Backpropagatio
        17293, -- 2306.06968 Can Forward Gradient Match Backpropagation?
        17495, -- 2306.09342 PaReprop: Fast Parallelized Reversible Backpropagation
        17728, -- 2306.13812 Maintaining Plasticity in Deep Continual Learning
        17914, -- 2306.17670 Learning Delays in Spiking Neural Networks using Dilated Convolutions
        18453, -- 2307.10711 AdjointDPM: Adjoint Sensitivity Method for Gradient Backpropagation of
        18719, -- 2307.15063 To Adapt or Not to Adapt? Real-Time Adaptation for Semantic Segmentati
        18770, -- 2307.16273 zkDL: Efficient Zero-Knowledge Proofs of Deep Learning Training
        19094, -- 2308.05059 A Novel Method for improving accuracy in neural network by reinstating
        19255, -- 2308.07625 Backpropagation Path Search On Adversarial Transferability
        20117, -- 2309.02214 Improving equilibrium propagation without weight symmetry through Jaco
        20815, -- 2309.13192 Towards Green AI in Fine-tuning Large Language Models via Adaptive Bac
        20855, -- 2309.13700 Video Adverse-Weather-Component Suppression Network via Weather Messen
        20958, -- 2309.15275 Efficient Low-rank Backpropagation for Vision Transformer Adaptation
        21190, -- 2310.00811 Sparse Backpropagation for MoE Training
        21473, -- 2310.03739 Aligning Text-to-Image Diffusion Models with Reward Backpropagation
        21939, -- 2310.08915 Dynamic Sparse No Training: Training-Free Fine-tuning for Sparse LLMs
        22263, -- 2310.13225 Scalable Neural Network Kernels
        22758, -- 2310.19614 Dis-inhibitory neuronal circuits can control the sign of synaptic plas
        23233, -- 2311.07427 Boolean Variation and Boolean Logic BackPropagation
        26100, -- 2401.11618 Efficient local linearity regularization to overcome catastrophic over
        27033, -- 2402.05424 Neural Circuit Diagrams: Robust Diagrams for the Communication, Implem
        27409, -- 2402.10492 Developing an Optimal Model for Predicting the Severity of Wheat Stem
        27522, -- 2402.11592 Revisiting Zeroth-Order Optimization for Memory-Efficient LLM Fine-Tun
        27925, -- 2402.15751 Sparse MeZO: Less Parameters for Better Performance in Zeroth-Order LL
        28038, -- 2402.17227 Efficient Backpropagation with Variance-Controlled Adaptive Sampling
        28047, -- 2402.17318 Scaling Supervised Local Learning with Augmented Auxiliary Networks
        28698, -- 2403.07134 COMQ: A Backpropagation-Free Algorithm for Post-Training Quantization
        28716, -- 2403.07483 DiabetesNet: A Deep Learning Approach to Diabetes Diagnosis
        28969, -- 2403.11004 Forward Learning of Graph Neural Networks
        29786, -- 2404.01278 BiPer: Binary Neural Networks using a Periodic Function
        30547, -- 2404.12406 Lowering PyTorch's Memory Consumption for Selective Differentiation
        31650, -- 2405.15020 AdjointDEIS: Efficient Gradients for Diffusion Models
        31729, -- 2405.15868 LLS: Local Learning Rule for Deep Neural Networks Inspired by Neural A
        31900, -- 2405.17991 VeLoRA: Memory Efficient Training using Rank-1 Sub-Token Projections
        31906, -- 2405.18047 2BP: 2-Stage Backpropagation
        32113, -- 2405.20594 Deep Learning without Weight Symmetry
        33134, -- 2406.11675 BLoB: Bayesian Low-Rank Adaptation by Backpropagation for Large Langua
        33330, -- 2406.13474 Attention-aware Post-training Quantization without Backpropagation
        33518, -- 2406.15758 EDGE-LLM: Enabling Efficient Large Language Model Adaptation on Edge D
        33558, -- 2406.16282 Reducing Fine-Tuning Memory Overhead by Approximate and Memory-Sharing
        33707, -- 2406.18060 AdaZeta: Adaptive Zeroth-Order Tensor-Train Adaption for Memory-Effici
        34281, -- 2407.05623 Momentum Auxiliary Network for Supervised Local Learning
        37512, -- 2409.19841 Counter-Current Learning: A Biologically Plausible Dual Network Approa
        38818, -- 2410.14634 Parallel Backpropagation for Inverse of a Convolution with Application
        39313, -- 2410.21644 On filter design in deep convolutional neural network
        39696, -- 2411.04036 Stepping Forward on the Last Mile
        40731, -- 2412.00088 Stochastic Taylor Derivative Estimator: Efficient amortization for arb
        41177, -- 2412.05667 Training neural networks without backpropagation using particles
        41700, -- 2412.12096 PanSplat: 4K Panorama Synthesis with Feed-Forward Gaussian Splatting
        42396, -- 2501.01045 ZeroFlow: Overcoming Catastrophic Forgetting is Easier than You Think
        42539, -- 2501.03176 Scalable Forward-Forward Algorithm
        42897, -- 2501.09238 Mono-Forward: Backpropagation-Free Algorithm for Efficient Neural Netw
        43345, -- 2501.17086 Accelerated Training through Iterative Gradient Propagation Along the
        43657, -- 2502.02472 SDE Matching: Scalable and Simulation-Free Training of Latent Stochast
        46365, -- 2503.14868 Efficient Personalization of Quantized Diffusion Model without Backpro
        47067, -- 2503.24322 NoProp: Training Neural Networks without Back-propagation or Forward-p
        50483, -- 2506.03077 StreamBP: Memory-Efficient Exact Backpropagation for Long Sequence Tra
        51197, -- 2506.14202 DiffusionBlocks: Blockwise Training for Generative Models via Score-Ba
        54331, -- 2511.13288 Multi-Agent Deep Research: Training Multi-Agent Systems with M-GRPO
        54836, -- 2512.14693 Universal Reasoning Model
        55766, -- 2601.22954 Residual Context Diffusion Language Models
        56006, -- 2602.11008 ROCKET: Rapid Optimization via Calibration-guided Knapsack Enhanced Tr
        56114, -- 2602.03120 Quantized Evolution Strategies: High-precision Fine-tuning of Quantize
        56636, -- 2603.10145 Lost in Backpropagation: The LM Head is a Gradient Bottleneck
        57747, -- 2604.21106 How Much Is One Recurrence Worth? Iso-Depth Scaling Laws for Looped La
        59197, -- 2603.17771 Attention Sinks Induce Gradient Sinks
        59572, -- 2603.10544 SCORE: Replacing Layer Stacking with Contractive Recurrent Depth
        61255, -- 2602.04929 TurboBoA: Faster and Exact Attention-aware Quantization without Backpr
        61840, -- 2601.21367 Hebbian Learning with Global Direction
        61983, -- 2601.19320 StableQAT: Stable Quantization-Aware Training at Ultra-Low Bitwidths
        63520, -- 2512.20668 Forward Only Learning for Orthogonal Neural Networks of any Depth
        64482, -- 2512.00086 Multi-modal On-Device Learning for Monocular Depth Estimation on Ultra
        64770, -- 2511.16652 Evolution Strategies at the Hyperscale
        65041, -- 2507.11017 First-Order Error Matters: Accurate Compensation for Quantized Large L
        65587, -- 2510.27265 T3: Test-Time Model Merging in VLMs for Zero-Shot Medical Imaging Anal
        66078, -- 2510.18812 A Unified Perspective on Optimization in Machine Learning and Neurosci
        67442, -- 2509.24837 Training-Free Token Pruning via Zeroth-Order Gradient Estimation in Vi
        67608, -- 2509.23253 Training Deep Normalization-Free Spiking Neural Networks with Lateral
        67941, -- 2509.19063 Beyond Backpropagation: Exploring Innovative Algorithms for Energy-Eff
        68852, -- 2509.01842 GradES: Significantly Faster Training in Transformers with Gradient-Ba
        69390, -- 2509.00031 End-to-End On-Device Quantization-Aware Training for LLMs at Inference
        69991, -- 2508.11674 Learning Internal Biological Neuron Parameters and Complexity-Based En
        71240, -- 2507.10581 Universal Approximation Theorem for a Single-Layer Transformer
        71763, -- 2506.19140 Command-V: Pasting LLM Behaviors via Activation Profiles
        72491, -- 2506.00356 Exploring the Performance of Perforated Backpropagation through Furthe
        73669, -- 2504.05097 State Tuning: State-based Test-Time Scaling on RWKV-7
        73843, -- 2503.21261 HOT: Hadamard-based Optimized Training
        74418, -- 2502.20586 Training LLMs with MXFP4
        74633, -- 2502.12346 QuZO: Quantized Zeroth-Order Fine-Tuning for Large Language Models
        74935, -- 2502.01837 TESS: A Scalable Temporally and Spatially Local Learning Rule for Spik
        75043, -- 2501.18018 Perforated Backpropagation: A Neuroscience Inspired Extension to Artif
        75265, -- 2501.04287 ElasticZO: A Memory-Efficient On-Device Learning with Combined Zeroth-
        76070, -- 2410.09771 EUGens: Efficient, Unified, and General Dense Layers
        76284, -- 2409.16697 Numerical Approximation Capacity of Neural Networks with Bounded Param
        76856, -- 2403.12975 Training morphological neural networks with gradient descent: some the
        76922, -- 2406.15643 Taming 3DGS: High-Quality Radiance Fields with Limited Resources
        76998, -- 2406.10576 Bypass Back-propagation: Optimization-based Structural Pruning for Lar
        78495, -- 2309.12381 Memory Efficient Mixed-Precision Optimizers
        78652, -- 2109.12894 Training Spiking Neural Networks Using Lessons From Deep Learning
        79125, -- 2304.08612 Bridging Discrete and Backpropagation: Straight-Through and Beyond
        79503, -- 2212.04377 Models Developed for Spiking Neural Networks
        79879, -- 2206.12338 Diegetic Representation of Feedback in Open Games
        80222, -- 2202.02248 Backpropagation Neural Tree
        80814, -- 2103.12032 Tangent Space Backpropagation for 3D Transformation Groups
        81105, -- 2009.14075 Backpropagating through Fréchet Inception Distance
        81438, -- 2002.10085 Temporal Spike Sequence Learning via Backpropagation for Deep Spiking
        81813, -- 1902.04760 Scaling Limits of Wide Neural Networks with Weight Sharing: Gaussian P
        81814, -- 1902.04704 Neural network models and deep learning - a primer for biologists
        81844, -- 1812.06574 A Biologically Plausible Supervised Learning Method for Spiking Neural
        81956, -- 1804.02464 Differentiable plasticity: training plastic neural networks with backp
        82057, -- 1804.00746 The simple essence of automatic differentiation
        82257, -- 1602.05179 Equilibrium Propagation: Bridging the Gap Between Energy-Based Models
        82347, -- 1609.06935 Quantum Neural Machine Learning - Backpropagation and Dynamics
        82451, -- 1511.05497 Learning Neural Network Architectures using Backpropagation
        82575, -- 1404.7828 Deep Learning in Neural Networks: An Overview
        82604, -- 1308.3432 Estimating or Propagating Gradients Through Stochastic Neurons for Con
        82779, -- 0903.4416 Backpropagation training in adaptive quantum networks
        83155, -- 2605.04651 FAAST: Forward-Only Associative Learning via Closed-Form Fast Weights
        83973, -- 2410.07547 Rethinking SNN Online Training and Deployment: Gradient-Coherent Learn
        84746, -- 2603.04733 FOZO: Forward-Only Zeroth-Order Prompt Optimization for Test-Time Adap
        85705, -- 2504.11558 Error Broadcast and Decorrelation as a Potential Artificial and Natura
        85831, -- 2502.03604 Bilevel ZOFO: Efficient LLM Fine-Tuning and Meta-Training
        85937, -- 2506.20990 SharpZO: Hybrid Sharpness-Aware Vision Language Model Prompt Tuning vi
        86196, -- 2505.13644 Collapsing Taylor Mode Automatic Differentiation
        86776, -- 2505.16649 Stochastic Forward-Forward Learning through Representational Dimension
        86839, -- 2504.12463 Dense Backpropagation Improves Training for Sparse Mixture-of-Experts
        86934, -- 2510.15366 Sequence Modeling with Spectral Mean Flows
        86973, -- 2505.13124 $\mu$PC: Scaling Predictive Coding to 100+ Layer Networks
        87547, -- 2410.08989 Zeroth-Order Fine-Tuning of LLMs in Random Subspaces
        87959, -- 2507.10213 Boosting Multimodal Learning via Disentangled Gradient Learning
        88516, -- 2503.06166 Secure On-Device Video OOD Detection Without Backpropagation
        88879, -- 2411.03493 LASER: Attention with Exponential Transformation
        88956, -- 2505.05086 Beyond Low-rank Decomposition: A Shortcut Approach for Efficient On-De
        89904, -- 2506.15563 Control and Realism: Best of Both Worlds in Layout-to-Image without Tr
        89938, -- 2412.13610 Faster and Stronger: When ANN-SNN Conversion Meets Parallel Spiking Ca
        89955, -- 2501.09976 Dendritic Localized Learning: Toward Biologically Plausible Algorithm
        91119, -- 2411.02001 Local Loss Optimization in the Infinite Width: Stable Parameterization
        91249, -- 2410.18070 Training Free Guided Flow-Matching with Optimal Control
        91253, -- 2410.18720 GeoLoRA: Geometric integration for parameter efficient fine-tuning
        91497, -- 2402.15173 Second-Order Fine-Tuning without Pain for LLMs: A Hessian Informed Zer
        92284, -- 2410.05966 FLOPS: Forward Learning with OPtimal Sampling
        92371, -- 2406.02052 PETRA: Parallel End-to-end Training with Reversible Architectures
        92608, -- 2506.18777 Programming by Backprop: An Instruction is Worth 100 Examples When Fin
        92656, -- 2508.11659 Toward Practical Equilibrium Propagation: Brain-inspired Recurrent Neu
        93020, -- 2601.00426 RMAAT: Astrocyte-Inspired Memory Compression and Replay for Efficient
        93042, -- 2510.06649 Local Reinforcement Learning with Action-Conditioned Root Mean Squared
        93845, -- 2512.04189 BEP: A Binary Error Propagation Algorithm for Binary Neural Networks T
        93930, -- 2510.09160 Efficient Resource-Constrained Training of Transformers via Subspace O
        93937, -- 2509.22020 Task-Adaptive Parameter-Efficient Fine-Tuning for Weather Foundation M
        93974, -- 2407.12516 Online Pseudo-Zeroth-Order Training of Neuromorphic Spiking Neural Net
        94007, -- 2506.13772 MobiEdit: Resource-efficient Knowledge Editing for Personalized On-dev
        94124, -- 2602.12590 Unbiased Gradient Estimation for Event Binning via Functional Backprop
        94193, -- 2604.13263 Binomial Gradient-Based Meta-Learning for Enhanced Meta-Gradient Estim
        94340, -- 2502.00340 Unlocking Full Efficiency of Token Filtering in Large Language Model T
        94932, -- 2604.16678 UniCon: Unified Framework for Efficient Contrastive Alignment via Kern
        95027, -- 2509.20284 Biologically Plausible Learning via Bidirectional Spike-Based Distilla
        95064, -- 2502.00639 Half-order Fine-Tuning for Diffusion Model: A Recursive Likelihood Rat
        96040, -- 2405.19309 SDPRLayers: Certifiable Backpropagation through Polynomial Optimizatio
        96239, -- external Continual-RL for Generalization in Autonomous Racing on the RoboRacer
        98032, -- external FOZO: Forward-Only Zeroth-Order Prompt Optimization for Test-Time Adap
        98681, -- 2606.11075 Exploring the Design Space of Reward Backpropagation for Flow Matching
        99246, -- 2510.00419 Learning a Zeroth-Order Optimizer for Fine-Tuning LLMs
        99275, -- 2605.18591 Randomized Advantage Transformation (RAT): Computing Natural Policy Gr
        99359, -- 2603.21725 CurvZO: Adaptive Curvature-Guided Sparse Zeroth-Order Optimization for
        99387, -- 2603.14773 HO-SFL: Hybrid-Order Split Federated Learning with Backprop-Free Clien
        100072, -- 2601.17261 AGZO: Activation-Guided Zeroth-Order Optimization for LLM Fine-Tuning
        100396, -- 2605.00650 AdaMeZO: Adam-style Zeroth-Order Optimizer for LLM Fine-tuning Without
        100789, -- 2506.23800 Towards the Training of Deeper Predictive Coding Neural Networks
        100822, -- 2605.01220 Visual Implicit Autoregressive Modeling
        100843, -- 2505.20137 ePC: Fast and Deep Predictive Coding in Digital Simulation
        100881, -- 2602.07697 On the Infinite Width and Depth Limits of Predictive Coding Networks
        101861, -- 2605.14373 Turning Stale Gradients into Stable Gradients: Coherent Coordinate Des
        102007, -- 2601.21683 Can local learning match self-supervised backpropagation?
        102555, -- 2405.03432 Improved Forward-Forward Contrastive Learning
        106714, -- 2508.13812 Timestep-Compressed Attack on Spiking Neural Networks Through Timestep
        106862, -- 2502.10012 Unlocking Efficient Vehicle Dynamics Modeling via Analytic World Model
        107608, -- 2512.23146 A Network of Biologically Inspired Rectified Spectral Units (ReSUs) Le
        107629, -- 2605.04058 MP-ISMoE: Mixed-Precision Interactive Side Mixture-of-Experts for Effi
        108498, -- 2508.08604 Transferable Model-agnostic Vision-Language Model Adaptation for Effic
        109166, -- external Integrating convolutional layers and biformer network with forward-for
        109209, -- external Gradient-based learning applied to document recognition
        109229, -- 2108.13621 Spike time displacement based error backpropagation in convolutional s
        109236, -- 2106.07030 The Backpropagation Algorithm Implemented on Spiking Neuromorphic Hard
        110198, -- external MUZO: Leveraging Multiple Queries and Momentum for Zeroth-Order Fine-T
        110529, -- 2502.11513 MaZO: Masked Zeroth-Order Optimization for Multi-Task Fine-Tuning of L
        110791, -- 2411.10696 HELENE: Hessian Layer-wise Clipping and Gradient Annealing for Acceler
        112615, -- 2407.05638 HPFF: Hierarchical Locally Supervised Learning with Patch Feature Fusi
        113057, -- 2407.13986 Deep Feature Surgery: Towards Accurate and Efficient Multi-Exit Networ
        113393, -- 2407.14170 Forbes: Face Obfuscation Rendering via Backpropagation Refinement Sche
        113395, -- 2403.18388 FTBC: Forward Temporal Bias Correction for Optimizing ANN-SNN Conversi
        113436, -- external GGRt: Towards Generalizable 3D Gaussians without Pose Priors in Real-T
        113538, -- external Rethinking Fast Adversarial Training: A Splitting Technique To Overcom
        116152, -- 2403.18442 Backpropagation-free Network for 3D Test-time Adaptation
        116975, -- external Sheared Backpropagation for Fine-tuning Foundation Models
        117654, -- 2603.08997 SkipGS: Post-Densification Backward Skipping for Efficient 3DGS Traini
        118190, -- 2509.21617 LANCE: Low Rank Activation Compression for Efficient On-Device Continu
        120840, -- 2605.24797 HCL-FF: Hierarchical and Contrastive Learning for Forward-Forward Algo
        120923, -- external Beyond Soft Label: Dataset Distillation via Orthogonal Gradient Matchi
        121137, -- external InTrain: Intrinsic Trainability for Zero-Cost Neural Architecture Sear
        122715, -- 2610.06833 Towards Looped Models Done Right, Part II: Rethinking at Fixed Points
        123071, -- 1901.06656 Training Neural Networks with Local Error Signals
        123078, -- 2105.08810 Sparse Spiking Gradient Descent
        123185, -- 2610.12737 Kernelized Parameter Sensitivity Atlases for Amortized Conditional Int
        124149, -- external Towards Identifying Dominant Low-Rank Subspaces in Zeroth-Order Fine-T
        124278, -- external Bayesian Backprop as Belief Propagation: Single-Pass Predictive Uncert
        124540, -- 2602.17155 Powering Up Zeroth-Order Training via Subspace Gradient Orthogonalizat
        124635, -- external Layer Free-Riding in Forward-Forward Networks: Real, Repairable, but N
        124679, -- 2605.19767 AR1-ZO: Topology-Aware Rank-1 Zeroth-Order Queries for High-Rank LoRA
        124909, -- external DP-EGGROLL: Centered Fitness-Vector Privatization for Backprop-Free Di
        125123, -- 2605.18867 EVA-0: Test-Time Model Evolution with Only Two Forward Passes per Samp
        125194, -- 2505.20892 One-Time Soft Alignment Enables Resilient Learning without Weight Tran
        125711, -- external K-prop: Deep Online Learning by Backpropagating Temporal Kernels
        125945, -- 2610.06243 RoSA: Rotational Sparse Adaptation for Memory-Efficient Fine-Tuning
        126051, -- 2606.03584 Training a Predictive Coding Network on ImageNet using Equilibrium Pro
        126167, -- 2601.21177 Flow Perturbation++: Multi-Step Unbiased Jacobian Estimation for High-
        126184, -- external Accelerating Neural Network Training with Augmented Koopman Dynamics
        126209, -- 2410.11648 Efficient, Accurate and Stable Gradients for Neural ODEs
        126592, -- external Know What You Need: Efficient Activation Checkpointing
        126728, -- external Nonlinear Direct Feedback Alignment for Scalable Backpropagation-Free
        127057, -- external Simplified Reversible Residual Networks
        127174, -- external CC-GS: Low-Memory 3D Gaussian Splatting Training via CPU-GPU Block-Wis
        127217, -- 2605.27946 Is Backpropagation Optimal? When Synthetic Gradients Improve Sample Ef
        127400, -- 2605.31022 Augmented Lagrangian Predictive Coding
        127517, -- external Mix-Opt: Mixed Optimization for Memory-Efficient Personalization of Te
        127548, -- external A method to automatically discover symbolic local learning rules
        127560, -- 2609.33240 The Price of Locality: Why Forward-Forward Underperforms Backpropagati
        127563, -- external Loop alignment: Self-organized Weight Transpose in Predictive Coding t
        128536, -- external Second-Order Complexity Theory for Neural Networks
        128713, -- 2512.21075 Feature Learning Dynamics in Infinite-Depth Neural Networks
        129139, -- 2605.10777 Locking Pretrained Weights via Deep Low-Rank Residual Distillation
        129222, -- external A Control-Theoretic Approximation to Predictive Coding Dynamics
        129248, -- 2605.11911 Understanding Sample Efficiency in Predictive Coding
        129691, -- 2610.06397 Learning Pareto Stationary Fronts via Single-Pass Backpropagation
        129741, -- 2601.21572 Signal-Adaptive Trust Regions for Gradient-Free Optimization of Recurr
        129917, -- external EDEN: Emergent Dynamics in Evolutionary Neural-networks for Robust Con
        130722, -- external BLANP: Memory-Efficient Backpropagation-Free Local Training via Antith
        130764, -- external GeoCurv-TTT: Geometry-Aware Deformation Restoration for 3D Test-Time T
        130951, -- 2606.11123 Overcoming Rank Collapse in Feedback Alignment
        131192, -- external Where You Backpropagate Matters: Token Hypothesis for Memory-Efficient
        131517, -- 2610.26030 Truncate or Not? A Scaling Study of Looped Transformers with Truncated
        131963, -- 2301.12667 NeSyFOLD: Neurosymbolic Framework for Interpretable Image Classificati
        132060  -- 2610.19080 Backpropagating Verifier Rewards Through Continuous Flow Language Mode
  );

DELETE FROM paper_method_exclusions x
USING backpropagation_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM backpropagation_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM backpropagation_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE backpropagation_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'backpropagation'
  AND p.id IN (
        8, -- 1102.0183 High-Performance Neural Networks for Visual Object Classification
        96, -- 1406.2661 Generative Adversarial Networks
        123, -- 1411.4389 Long-term Recurrent Convolutional Networks for Visual Recognition and
        153, -- 1502.03044 Show, Attend and Tell: Neural Image Caption Generation with Visual Att
        191, -- 1505.07818 Domain-Adversarial Training of Neural Networks
        192, -- 1505.08075 Transition-Based Dependency Parsing with Stack Long Short-Term Memory
        285, -- 1512.02479 Explaining NonLinear Classification Decisions with Deep Taylor Decompo
        298, -- 1602.00134 Convolutional Pose Machines
        302, -- 1602.02068 From Softmax to Sparsemax: A Sparse Model of Attention and Multi-Label
        326, -- 1603.03101 Recursive Recurrent Nets with Attention Modeling for OCR in the Wild
        467, -- 1609.09106 HyperNetworks
        493, -- 1611.01144 Categorical Reparameterization with Gumbel-Softmax
        657, -- 1704.02685 Learning Important Features Through Propagating Activation Differences
        664, -- 1704.03976 Virtual Adversarial Training: A Regularization Method for Supervised a
        705, -- 1705.03633 Inferring and Executing Programs for Visual Reasoning
        713, -- 1705.05598 Learning how to explain neural networks: PatternNet and PatternAttribu
        959, -- 1711.03705 Online Deep Learning: Learning Deep Neural Networks on the Fly
        1006, -- 1712.01337 Self-supervised Learning of Motion Capture
        1228, -- 1804.06657 NTUA-SLP at SemEval-2018 Task 2: Predicting Emojis using RNNs with Con
        1230, -- 1804.06659 NTUA-SLP at SemEval-2018 Task 3: Tracking Ironic Tweets using Ensemble
        1601, -- 1811.01339 A Novel Predictive-Coding-Inspired Variational RNN Model for Online Pr
        1615, -- 1811.04968 PennyLane: Automatic differentiation of hybrid quantum-classical compu
        1722, -- 1812.09912 Image-to-Image Translation via Group-wise Deep Whitening-and-Coloring
        1738, -- 1901.01695 Vector representations of text data in deep learning
        1797, -- 1902.00057 Probabilistic Discriminative Learning with Layered Graphical Models
        1867, -- 1903.01093 Differentiable Causal Computations via Delayed Trace
        2128, -- 1905.09717 Network Pruning via Transformable Architecture Search
        2923, -- 1912.05911 Recurrent Neural Networks (RNNs): A gentle Introduction and Overview
        2932, -- 1912.07116 Image Processing Using Multi-Code GAN Prior
        2963, -- 1912.12055 nnAudio: An on-the-fly GPU Audio to Spectrogram Conversion Toolbox Usi
        3037, -- 2001.10382 Selective Weak Supervision for Neural Information Retrieval
        3122, -- 2002.08909 REALM: Retrieval-Augmented Language Model Pre-Training
        3192, -- 2003.03581 StyleGAN2 Distillation for Feed-forward Image Manipulation
        3228, -- 2003.07845 PowerNorm: Rethinking Batch Normalization in Transformers
        3302, -- 2004.02866 There and Back Again: Revisiting Backpropagation Saliency Methods
        3511, -- 2005.00975 Efficient Second-Order TreeCRF for Neural Dependency Parsing
        3659, -- 2006.02570 Exploration of Interpretability Techniques for Deep COVID-19 Classific
        3962, -- 2007.15796 AR-Net: Adaptive Frame Resolution for Efficient Action Recognition
        3966, -- 2008.00299 Eigen-CAM: Class Activation Map using Principal Components
        3999, -- 2008.03736 Fast and Accurate Neural CRF Constituency Parsing
        4175, -- 2009.09232 Learned Low Precision Graph Neural Networks
        5468, -- 2104.07566 BAM: A Balanced Attention Mechanism for Single Image Super Resolution
        5509, -- 2104.08691 The Power of Scale for Parameter-Efficient Prompt Tuning
        5572, -- 2104.11914 EXplainable Neural-Symbolic Learning (X-NeSyL) methodology to fuse dee
        5814, -- 2105.14669 Memory-Efficient Differentiable Transformer Architecture Search
        5958, -- 2106.06038 Modeling Hierarchical Structures with Continuous Recursive Neural Netw
        6194, -- 2107.03050 Controlled Caption Generation for Images Through Adversarial Attacks
        6587, -- 2109.04504 Bootstrapped Meta-Learning
        6892, -- 2110.06081 On Expressivity and Trainability of Quadratic Networks
        6908, -- 2110.06537 Well-classified Examples are Underestimated in Classification with Dee
        7054, -- 2110.13511 AutoDEUQ: Automated Deep Ensemble with Uncertainty Quantification
        7138, -- 2111.01754 Meta-Learning to Improve Pre-Training
        7415, -- 2112.02906 ALIKE: Accurate and Lightweight Keypoint Detection and Descriptor Extr
        7431, -- 2112.03740 Dilated convolution with learnable spacings
        7464, -- 2112.05224 Spinning Language Models: Risks of Propaganda-As-A-Service and Counter
        7701, -- 2201.05748 Concise Logarithmic Loss Function for Robust Training of Anomaly Detec
        7831, -- 2202.00441 Few-Bit Backward: Quantized Gradients of Activation Functions for Memo
        7870, -- 2202.02435 On Neural Differential Equations
        7894, -- 2202.03376 Message Passing Neural PDE Solvers
        8815, -- 2204.10629 MEKER: Memory Efficient Knowledge Embedding Representation for Link Pr
        9367, -- 2206.02262 Diffusion-GAN: Training GANs with Diffusion
        9462, -- 2206.06522 LST: Ladder Side-Tuning for Parameter and Memory Efficient Transfer Le
        9952, -- 2208.00809 Neural network layers as parametric spans
        10213, -- 2209.01540 An Empirical Study of End-to-End Video-Language Transformers with Mask
        10349, -- 2209.09422 Bit Allocation using Optimization
        10361, -- 2209.09815 Towards Fine-tuning Pre-trained Language Models with Integer Forward a
        10453, -- 2209.14624 Is Complexity Required for Neural Network Pruning? A Case Study on Glo
        10768, -- 2210.06662 Action Matching: Learning Stochastic Dynamics from Samples
        10907, -- 2210.10620 Active Image Indexing
        11273, -- 2211.04800 Designing Network Design Strategies Through Gradient Path Analysis
        11525, -- 2211.12343 Diffusion Model Based Posterior Sampling for Noisy Linear Inverse Prob
        11755, -- 2212.00774 Score Jacobian Chaining: Lifting Pretrained 2D Diffusion Models for 3D
        11831, -- 2212.03220 Visual Query Tuning: Towards Effective Usage of Intermediate Represent
        12271, -- 2301.00330 Efficient On-device Training via Gradient Filtering
        12355, -- 2301.03480 Differentiable Simulations for Enhanced Sampling of Rare Events
        12684, -- 2301.13196 Looped Transformers as Programmable Computers
        13014, -- 2302.05326 Scalable Real-Time Recurrent Learning Using Columnar-Constructive Netw
        13240, -- 2302.11007 Unification of popular artificial neural network activation functions
        13425, -- 2303.00914 Neuro-Modulated Hebbian Learning for Fully Test-Time Adaptation
        13874, -- 2303.10139 Distill n' Explain: explaining graph neural networks using simple surr
        14293, -- 2303.17209 Human from Blur: Human Pose Tracking from Blurry Images
        14954, -- 2304.12998 ChatLLM Network: More brains, More intelligence
        15195, -- 2305.02374 A Novel Plagiarism Detection Approach Combining BERT-based Word Embedd
        15429, -- 2305.06349 RECKONING: Reasoning through Dynamic Knowledge Encoding
        15526, -- 2305.08040 Provable Multi-instance Deep AUC Maximization with Stochastic Pooling
        15532, -- 2305.08099 Self-supervised Neural Factor Analysis for Disentangling Utterance-lev
        16240, -- 2305.15348 READ: Recurrent Adaptation of Large Transformers
        16419, -- 2305.17333 Fine-Tuning Language Models with Just Forward Passes
        16598, -- 2305.19044 Exploring the Promise and Limits of Real-Time Recurrent Learning
        16654, -- 2305.19744 Neural Markov Jump Processes
        16680, -- 2305.19999 Beam Tree Recursive Cells
        16806, -- 2306.00978 AWQ: Activation-aware Weight Quantization for LLM Compression and Acce
        16990, -- 2306.03082 InstructZero: Efficient Instruction Optimization for Black-Box Large L
        17650, -- 2306.11987 Training Transformers with 4-bit Integers
        18203, -- 2307.06440 No Train No Gain: Revisiting Efficient Training Algorithms For Transfo
        18579, -- 2307.12774 Fast Full-frame Video Stabilization with Iterative Optimization
        18748, -- 2307.15663 CoRe Optimizer: An All-in-One Solution for Machine Learning
        19417, -- 2308.09564 Deep Equilibrium Object Detection
        19583, -- 2308.10997 MarkovGen: Structured Prediction for Efficient Text-to-Image Generatio
        20242, -- 2309.04756 Probabilistic Triangulation for Uncalibrated Multi-View 3D Human Pose
        20432, -- 2309.07911 Disentangling Spatial and Temporal Learning for Efficient Image-to-Vid
        20654, -- 2309.11043 Score Mismatching for Generative Modeling
        21077, -- 2309.17130 GRANDE: Gradient-Based Decision Tree Ensembles for Tabular Data
        21103, -- 2309.17400 Directly Fine-Tuning Diffusion Models on Differentiable Rewards
        22204, -- 2310.12474 Enhancing High-Resolution 3D Generation through Pixel-wise Gradient Cl
        22347, -- 2310.14418 REFER: An End-to-end Rationale Extraction Framework for Explanation Re
        22636, -- 2310.17752 PockEngine: Sparse and Efficient Fine-tuning in a Pocket
        23036, -- 2311.04082 Time-Efficient Reinforcement Learning with Stochastic Stateful Policie
        23508, -- 2311.11012 Bit Cipher -- A Simple yet Powerful Word Representation System that In
        23794, -- 2311.15657 Enhancing Diffusion Models with Text-Encoder Reinforcement Learning
        23833, -- 2311.16102 Diffusion-TTA: Test-time Adaptation of Discriminative Models via Gener
        23877, -- 2311.16739 As-Plausible-As-Possible: Plausibility-Aware Mesh Deformation Using 2D
        24239, -- 2312.02150 Readout Guidance: Learning Control from Diffusion Features
        24493, -- 2312.04916 EE-LLM: Large-Scale Training and Inference of Early-Exit Large Languag
        24599, -- 2312.06562 On Meta-Prompting
        24942, -- 2312.11510 QuadAttack: A Quadratic Programming Approach to Ordered Top-K Attacks
        24988, -- 2312.12337 pixelSplat: 3D Gaussian Splats from Image Pairs for Scalable Generaliz
        25362, -- 2401.00604 SteinDreamer: Variance Reduction for Text-to-3D Score Distillation via
        25804, -- 2401.07159 Quantized Side Tuning: Fast and Memory-Efficient Tuning of Quantized L
        25860, -- 2401.08392 DoraemonGPT: Toward Understanding Dynamic Scenes with Large Language M
        26457, -- 2401.16656 Gradient-Based Language Model Red Teaming
        26512, -- 2401.17544 Trainable Fixed-Point Quantization for Deep Learning Acceleration on F
        27000, -- 2402.04964 ConvLoRA and AdaBN based Domain Adaptation via Self-Training
        27032, -- 2402.05406 Everybody Prune Now: Structured Pruning of LLMs with only Forward Pass
        27476, -- 2402.11196 Maintaining Adversarial Robustness in Continuous Learning
        27705, -- 2402.13412 Scaling physics-informed hard constraints with mixture-of-experts
        28086, -- 2402.17760 Learning to Program Variational Quantum Circuits with Fast Weights
        28166, -- 2402.18700 Learning to Compress Prompt in Natural Language Formats
        28914, -- 2403.10255 Arbitrary-Scale Image Generation and Upsampling using Latent Diffusion
        29618, -- 2403.19549 GlORIE-SLAM: Globally Optimized RGB-only Implicit Encoding Point Cloud
        29955, -- 2404.03620 LCM-Lookahead for Encoder-based Text-to-Image Personalization
        31973, -- 2405.18750 T2V-Turbo: Breaking the Quality Bottleneck of Video Consistency Model
        32321, -- 2406.02549 Dreamguider: Improved Training free Diffusion-based Conditional Genera
        32706, -- 2406.07394 Accessing GPT-4 level Mathematical Olympiad Solutions via Monte Carlo
        32724, -- 2406.07496 TextGrad: Automatic "Differentiation" via Text
        33546, -- 2406.16218 Trace is the Next AutoDiff: Generative Optimization with Rich Feedback
        33720, -- 2406.18173 UIO-LLMs: Unbiased Incremental Optimization for Long-Context LLMs
        33748, -- 2406.18532 Symbolic Learning Enables Self-Evolving Agents
        34420, -- 2407.07523 SHERL: Synthesizing High Accuracy and Efficient Memory for Resource-Li
        34518, -- 2407.08737 Video Diffusion Alignment via Reward Gradients
        34748, -- 2407.11681 MINI-LLM: Memory-Efficient Structured Pruning for Large Language Model
        34897, -- 2407.13331 Reconstruct the Pruned Model without Any Retraining
        34953, -- 2407.14110 MC-PanDA: Mask Confidence for Panoptic Domain Adaptation
        35459, -- 2408.00766 Optimizing Diffusion Models for Joint Trajectory Prediction and Contro
        36050, -- 2408.11104 ConFIG: Towards Conflict-free Training of Physics Informed Neural Netw
        36086, -- 2408.11721 Detection-Driven Object Count Optimization for Text-to-Image Diffusion
        36445, -- 2409.00314 Towards Secure and Usable 3D Assets: A Novel Framework for Automatic V
        36739, -- 2409.06633 SaRA: High-Efficient Diffusion Model Fine-tuning with Progressive Spar
        36823, -- 2409.08278 DreamHOI: Subject-Driven Generation of 3D Human-Object Interactions wi
        36966, -- 2409.10876 Self-Supervised Speed of Sound Recovery for Aberration-Corrected Photo
        37045, -- 2409.12136 GRIN: GRadient-INformed MoE
        37678, -- 2410.01707 Interpretable Contrastive Monte Carlo Tree Search Reasoning
        38119, -- 2410.06424 Restructuring Vector Quantization with the Rotation Trick
        38494, -- 2410.11001 Graph of Records: Boosting Retrieval Augmented Generation for Long-con
        38720, -- 2410.13643 Fine-Tuning Discrete Diffusion Models via Reward Optimization with App
        38993, -- 2410.16946 Self-Evolving Multi-Agent Collaboration Networks for Software Developm
        39238, -- 2410.20474 GrounDiT: Grounding Diffusion Transformers via Noisy Patch Transplanta
        39334, -- 2410.22179 Robust and Unbounded Length Generalization in Autoregressive Transform
        39673, -- 2411.03562 Large Language Models Orchestrating Structured Reasoning Achieve Kaggl
        40061, -- 2411.10573 Hysteresis Activation Function for Efficient Inference
        40348, -- 2411.15393 Gradient-Free Classifier Guidance for Diffusion Model Sampling
        40733, -- 2412.00100 Steering Rectified Flow Models in the Vector Field for Controlled Imag
        40922, -- 2412.02692 Taming Scalable Visual Tokenizer for Autoregressive Image Generation
        41221, -- 2412.06289 S$^{2}$FT: Efficient, Scalable and Generalizable LLM Fine-tuning by St
        42160, -- 2412.18319 Mulberry: Empowering MLLM with o1-like Reasoning and Reflection via Co
        42337, -- 2501.00289 Dual Diffusion for Unified Image Generation and Understanding
        42916, -- 2501.09565 A New Teacher-Reviewer-Student Framework for Semi-supervised 2D Human
        43219, -- 2501.14787 Matrix Calculus (for Machine Learning and Beyond)
        43347, -- 2501.17104 COS(M+O)S: Curiosity and RL-Enhanced MCTS for Exploring Story Space vi
        44072, -- 2502.07987 Universal Adversarial Attack on Aligned Multimodal LLMs
        44074, -- 2502.08006 Greed is Good: A Unifying Perspective on Guided Generation
        44334, -- 2502.11458 Towards Efficient Pre-training: Exploring FP4 Precision in Large Langu
        44415, -- 2502.12119 PRISM: Self-Pruning Intrinsic Selection Method for Training-Free Multi
        45160, -- 2502.20235 Attention Distillation: A Unified Approach to Visual Characteristics T
        45472, -- 2503.03272 Towards Effective and Sparse Adversarial Attack on Spiking Neural Netw
        46293, -- 2503.13942 Structured Knowledge Accumulation: An Autonomous Framework for Layer-W
        46980, -- 2503.23104 Fast Training of Recurrent Neural Networks with Stationary State Feedb
        47798, -- 2504.12292 SHeaP: Self-Supervised Head Geometry Predictor Learned via 2D Gaussian
        48299, -- 2505.00312 AWARE-NET: Adaptive Weighted Averaging for Robust Ensemble Network in
        48578, -- 2505.06257 Beyond Attention: Toward Machines with Intrinsic Higher Mental States
        49327, -- 2505.15791 VARD: Efficient and Dense Fine-Tuning for Diffusion Models with Value-
        49436, -- 2505.16710 Training Long-Context LLMs Efficiently via Chunk-wise Optimization
        50010, -- 2505.22338 Text2Grad: Reinforcement Learning from Natural Language Feedback
        50905, -- 2506.09046 Agentic Neural Networks: Self-Evolving Multi-Agent Systems via Textual
        52303, -- 2508.07629 Klear-Reasoner: Advancing Reasoning Capability via Gradient-Preserving
        53868, -- 2510.22010 FlowOpt: Fast Optimization Through Whole Flow Processes for Training-F
        54229, -- 2511.09809 Test-Time Spectrum-Aware Latent Steering for Zero-Shot Generalization
        54347, -- 2511.18024 Extracting Interaction-Aware Monosemantic Concepts in Recommender Syst
        54402, -- 2511.21541 Video Generation Models Are Good Latent Reward Models
        54477, -- 2512.00762 Seeing the Wind from a Falling Leaf
        54668, -- 2512.08153 TreeGRPO: Tree-Advantage GRPO for Online RL Post-Training of Diffusion
        55215, -- 2601.05741 ViTNT-FIQA: Training-Free Face Image Quality Assessment with Vision Tr
        55523, -- 2601.17668 Fast KVzip: Efficient and Accurate LLM Inference with Gated KV Evictio
        55670, -- 2602.01624 PISCES: Annotation-free Text-to-Video Post-Training via Optimal Transp
        55900, -- 2602.07845 Recurrent-Depth VLA: Implicit Test-Time Compute Scaling of Vision-Lang
        56548, -- 2603.07700 TDM-R1: Reinforcing Few-Step Diffusion Models with Non-Differentiable
        57537, -- 2604.15311 LeapAlign: Post-Training Flow Matching Models at Any Generation Step b
        57657, -- 2602.10751 Predicting integers from continuous parameters
        57739, -- 2508.10180 For-Value: Efficient Forward-Only Data Valuation for finetuning LLMs a
        57752, -- 2604.22841 ATTN-FIQA: Interpretable Attention-based Face Image Quality Assessment
        58530, -- 2604.00733 Spectral Compact Training: Pre-Training Large Language Models via Perm
        58625, -- 2601.21064 Textual Equilibrium Propagation for Deep Compound AI Systems
        58884, -- 2603.25155 Photon: Speedup Volume Understanding with Efficient Multimodal Large L
        59048, -- 2603.21210 Pretrained Video Models as Differentiable Physics Simulators for Urban
        59105, -- 2603.20526 Does This Gradient Spark Joy?
        59113, -- 2603.19939 Timestep-Aware Block Masking for Efficient Diffusion Model Inference
        59160, -- 2603.20304 Transferable Multi-Bit Watermarking Across Frozen Diffusion Models via
        59852, -- 2603.05296 Latent Policy Steering through One-Step Flow Policies
        60254, -- 2602.22571 GIFSplat: Generative Prior-Guided Iterative Feed-Forward 3D Gaussian S
        60329, -- 2602.20511 Leveraging Causal Reasoning Method for Explaining Medical Image Segmen
        60448, -- 2603.06619 Not all tokens are needed(NAT): token efficient reinforcement learning
        60550, -- 2602.16839 Training Large Reasoning Models Efficiently via Progressive Thought En
        60600, -- 2602.14974 DM0: An Embodied-Native Vision-Language-Action Model towards Physical
        60892, -- 2602.11206 UltraLIF: Fully Differentiable Spiking Neural Networks via Ultradiscre
        60902, -- 2602.09878 MVISTA-4D: View-Consistent 4D World Model with Test-Time Action Infere
        61691, -- 2601.23014 Mem-T: Densifying Rewards for Long-Horizon Memory Agents
        61726, -- 2601.22582 MC-GRPO: Median-Centered Group Relative Policy Optimization for Small-
        62281, -- 2601.14234 Q-learning with Adjoint Matching
        63311, -- 2512.22288 Co-GRPO: Co-Optimized Group Relative Policy Optimization for Masked Di
        63360, -- 2512.20920 RevFFN: Memory-Efficient Full-Parameter Fine-Tuning of Mixture-of-Expe
        64015, -- 2512.07010 Always Keep Your Promises: DynamicLRP, A Model-Agnostic Solution To La
        64885, -- 2511.14390 Accelerating Automatic Differentiation of Direct Form Digital Filters
        65323, -- 2511.04753 CPO: Condition Preference Optimization for Controllable Image Generati
        65653, -- 2510.26358 AgriGS-SLAM: Orchard Mapping Across Seasons via Multi-View Gaussian Sp
        65772, -- 2510.23926 Improving the Straight-Through Estimator with Zeroth-Order Information
        65838, -- 2510.22777 SeeDNorm: Self-Rescaled Dynamic Normalization
        65977, -- 2510.20468 Transferable Black-Box One-Shot Forging of Watermarks via Image Prefer
        66187, -- 2510.16882 Utility-Diversity Aware Online Batch Selection for LLM Supervised Fine
        66337, -- 2510.14255 Identity-Preserving Image-to-Video Generation via Reward-Guided Optimi
        66574, -- 2510.10693 High-Dimensional Learning Dynamics of Quantized Models with Straight-T
        67020, -- 2510.03515 RAPID: An Efficient Reinforcement Learning Algorithm for Small Languag
        67410, -- 2509.25094 Unsupervised Representation Learning for 3D Mesh Parameterization with
        67545, -- 2509.23809 Tequila: Trapping-free Ternary Quantization for Large Language Models
        67770, -- 2509.21519 Provable Scaling Laws of Feature Emergence from Learning Dynamics of G
        68266, -- 2509.13936 Noise-Level Diffusion Guidance: Well Begun is Half Done
        68430, -- 2509.11090 End-to-End Visual Autonomous Parking via Control-Aided Attention
        69393, -- 2504.16316 On the Consistency of GNN Explanations for Malware Detection
        70184, -- 2508.03587 Zero-Variance Gradients for Variational Autoencoders
        70366, -- 2508.01318 AffectGPT-R1: Leveraging Reinforcement Learning for Open-Vocabulary Mu
        70535, -- 2507.22604 ShortFT: Diffusion Model Alignment via Shortcut-based Fine-Tuning
        71790, -- 2506.18331 End-to-End Fine-Tuning of 3D Texture Generation using Differentiable R
        72200, -- 2506.06130 Gradient Similarity Surgery in Multi-Task Deep Learning
        72810, -- 2505.17630 GIM: Improved Interpretability for Large Language Models
        74513, -- 2502.16601 SelaVPR++: Towards Seamless Adaptation of Foundation Models for Effici
        74801, -- 2502.05964 Revisiting Gradient-based Uncertainty for Monocular Depth Estimation
        74980, -- 2502.00726 Perspectives for Direct Interpretability in Multi-Agent Deep Reinforce
        75558, -- 2412.06097 Order Theory in the Context of Machine Learning
        76098, -- 2410.07698 Enhancing Zeroth-order Fine-tuning for Language Models with Low-rank S
        77621, -- 2403.11491 Uncertainty-Calibrated Test-Time Model Adaptation without Forgetting
        77941, -- 2401.08909 Leveraging Gradients for Unsupervised Accuracy Estimation under Distri
        78156, -- 2312.02659 Supervised learning of spatial features with STDP and homeostasis usin
        79908, -- 2206.04873 Imitation Learning via Differentiable Physics
        79929, -- 2206.01178 Discretization Invariant Networks for Learning Maps between Neural Fie
        80137, -- 2203.07772 Fast Autofocusing using Tiny Transformer Networks for Digital Holograp
        80152, -- 2203.03379 An STDP-Based Supervised Learning Algorithm for Spiking Neural Network
        80208, -- 2202.06358 Do Inpainting Yourself: Generative Facial Inpainting Guided by Exempla
        80685, -- 2106.04053 Discriminative Triad Matching and Reconstruction for Weakly Referring
        80709, -- 2105.11346 Position-Sensing Graph Neural Networks: Proactively Learning Nodes Rel
        80750, -- 2104.13478 Geometric Deep Learning: Grids, Groups, Graphs, Geodesics, and Gauges
        80825, -- 2103.09002 Hebbian Semi-Supervised Learning in a Sample Efficiency Setting
        81088, -- 2010.03509 Automatic Backward Filtering Forward Guiding for Markov processes and
        81260, -- 2006.08656 Multiscale Deep Equilibrium Models
        81383, -- 2004.02396 A Learning Framework for n-bit Quantized Neural Networks toward FPGAs
        81474, -- 2001.04536 Understanding and mitigating gradient pathologies in physics-informed
        81624, -- 1909.01377 Deep Equilibrium Models
        81686, -- 1906.09852 Lifelong Learning Starting From Zero
        81982, -- 1806.08874 The Foundations of Deep Learning with a Path Towards General Intellige
        82014, -- 1805.07504 Deep Loopy Neural Network Model for Graph Structured Data Representati
        82034, -- 1804.08150 Deep Learning in Spiking Neural Networks
        82051, -- 1804.03289 Planning Multi-Fingered Grasps as Probabilistic Inference in a Learned
        82122, -- 1712.08862 Neural Network Multitask Learning for Traffic Flow Forecasting
        82206, -- 1707.06381 Adaptive Learning Rule for Hardware-based Deep Neural Networks Using E
        82209, -- 1707.09864 Generalizing the Convolution Operator in Convolutional Neural Networks
        82839, -- 2605.03849 Stream-R1: Reliability-Perplexity Aware Reward Distillation for Stream
        82863, -- 1703.06211 Deformable Convolutional Networks
        83773, -- 2605.26108 Reinforcing Few-step Generators via Reward-Tilted Distribution Matchin
        83889, -- 2605.25174 Growing a Neural Network in Breadth, Depth, and Time
        83965, -- 2402.14598 MemFlow: A Lightweight Forward Memorizing Framework for Quick Domain A
        84119, -- 2510.03101 AdaBet: Gradient-free Layer Selection for Efficient Training of Deep N
        84386, -- 2512.12080 BAgger: Backwards Aggregation for Mitigating Drift in Autoregressive V
        84521, -- 2602.17535 LATA: Laplacian-Assisted Transductive Adaptation for Conformal Uncerta
        84525, -- 2602.18845 Echoes of Ownership: Adversarial-Guided Dual Injection for Copyright P
        85303, -- 2604.07399 Critical Patch-Aware Sparse Prompting with Decoupled Training for Cont
        85329, -- 2604.09088 Memory-Efficient Transfer Learning with Fading Side Networks via Maske
        85400, -- 2604.16540 PoInit-of-View: Poisoning Initialization of Views Transfers Across Mul
        85501, -- 2605.03820 Multimodal Learning on Low-Quality Data with Conformal Predictive Self
        85696, -- 2506.21427 Flow-Based Single-Step Completion for Efficient and Expressive Policy
        85788, -- 2506.00871 Towards Predicting Any Human Trajectory In Context
        86280, -- 2505.22509 Accelerating Optimization via Differentiable Stopping Time
        86300, -- 2410.18804 Fast constrained sampling in pre-trained diffusion models
        86314, -- 2510.06254 Enhanced Self-Distillation Framework for Efficient Spiking Neural Netw
        86338, -- 2403.03881 Unlocking Dataset Distillation with Diffusion Models
        86408, -- 2506.05259 Learning long range dependencies through time reversal symmetry breaki
        86622, -- 2509.20733 PALQO: Physics-informed model for Accelerating Large-scale Quantum Opt
        86668, -- 2506.06470 SIGMA: Refining Large Language Model Reasoning via Sibling-Guided Mont
        86686, -- 2405.13954 What is Your Data Worth to GPT? LLM-Scale Data Valuation with Influenc
        87056, -- 2510.14810 Rethinking Hebbian Principle: Low-Dimensional Structural Projection fo
        87157, -- 2507.05158 InfoSteer: Steering Information Utility in Language Model Post-Trainin
        87477, -- 2510.04838 Beyond Random: Automatic Inner-loop Optimization in Dataset Distillati
        87607, -- 2502.01289 A Framework for Double-Blind Federated Adaptation of Foundation Models
        87609, -- 2506.23674 Partial Forward Blocking: A Novel Data Pruning Paradigm for Lossless T
        87647, -- 2503.14786 SketchSplat: 3D Edge Reconstruction via Differentiable Multi-view Sket
        87988, -- 2503.22351 One Look is Enough: Seamless Patchwise Refinement for Zero-Shot Monocu
        88387, -- 2507.06651 Diff2I2P: Differentiable Image-to-Point Cloud Registration with Diffus
        88446, -- 2506.01955 Dual-Process Image Generation
        88530, -- 2412.11569 The dark side of the forces: assessing non-conservative force models f
        88655, -- 2505.00533 Test-time Correlation Alignment
        88686, -- 2410.02711 NETS: A Non-equilibrium Transport Sampler
        89144, -- 2505.19659 LangDAug: Langevin Data Augmentation for Multi-Source Domain Generaliz
        89163, -- 2502.00361 Efficient Online Reinforcement Learning for Diffusion Policy
        89446, -- 2311.08870 One-Shot Heterogeneous Federated Learning with Local Model-Guided Diff
        89588, -- 2501.18006 Topological Signatures of Adversaries in Multimodal Alignments
        90290, -- 2408.11280 Exploring Scene Affinity for Semi-Supervised LiDAR Semantic Segmentati
        90729, -- 2503.16572 Efficient ANN-Guided Distillation: Aligning Rate-based Features of Spi
        91677, -- 2502.19980 Can Textual Gradient Work in Federated Learning?
        91959, -- 2410.03973 Efficient Training of Neural Stochastic Differential Equations by Matc
        91990, -- 2502.08696 Scalable Discrete Diffusion Samplers: Combinatorial Optimization and S
        92103, -- 2410.05760 Training-Free Diffusion Model Alignment with Sampling Demons
        92232, -- 2405.16720 Large Scale Knowledge Washing
        92446, -- 2502.07547 Instance-dependent Early Stopping
        92522, -- external Legendre Memory Units: Continuous-Time Representation in Recurrent Neu
        92696, -- 2505.12299 MobileIPL: Enhancing Mobile Agents Thinking Process via Iterative Pref
        92884, -- 2512.05297 CFO: Learning Continuous-Time PDE Dynamics via Flow-Matched Neural Ope
        93336, -- 2507.13231 VITA: Vision-to-Action Flow Matching Policy
        93686, -- 2510.11590 Diffusion-DFL: Decision-focused Diffusion Models for Stochastic Optimi
        93839, -- 2507.04832 Discrete Diffusion Trajectory Alignment via Stepwise Decomposition
        93860, -- 2510.03648 SAFA-SNN: Sparsity-Aware On-Device Few-Shot Class-Incremental Learning
        93944, -- 2501.15889 Adaptive Width Neural Networks
        93957, -- 2508.10480 Pinet: Optimizing hard-constrained neural networks with orthogonal pro
        94033, -- 2602.10911 Tuning the burn-in phase in training recurrent neural networks improve
        94118, -- 2510.00502 Diffusion Alignment as Variational Expectation-Maximization
        94214, -- 2512.18365 Efficient Zero-shot Inpainting with Decoupled Diffusion Guidance
        94363, -- 2409.09245 Robust Training of Neural Networks at Arbitrary Precision and Sparsity
        94804, -- 2505.11134 Robustify Spiking Neural Networks via Dominant Singular Deflation unde
        95033, -- 2602.03284 Time Is All It Takes: Spike-Retiming Attacks on Event-Driven Spiking N
        95163, -- 2501.04194 STLCG++: A Masking Approach for Differentiable Signal Temporal Logic S
        95516, -- 2508.21065 Learning on the Fly: Rapid Policy Adaptation Via Differentiable Simula
        95986, -- external D2MFusion: An End-To-End Differentiable Trajectory Optimizer for Safe
        96046, -- external Learning Location-Specific Latent Behavior Priors for Occupancy Predic
        98059, -- external Rethinking SNN Online Training and Deployment — Gradient-Coherent Lear
        98129, -- 2606.11087 Test-Time Gradient Guidance of Flow Policies in Reinforcement Learning
        98213, -- 2606.11854 Fine-tuning Multi-modal LLMs with ART: Art-based Reinforcement Trainin
        99107, -- 2606.02521 Drifting Preference Optimization for One-Step Generative Models
        99485, -- 2409.06282 ReAugment: Targeted Few-Shot Time Series Augmentation via Model Zoo-Gu
        99609, -- 2605.17118 Differentiable Optimization Layers for Guaranteed Fairness in Deep Lea
        99767, -- 2604.21360 Prototype-Based Test-Time Adaptation of Vision-Language Models
        99896, -- 2508.06214 Reparameterization Proximal Policy Optimization
        99897, -- 2602.03501 Reparameterization Flow Policy Optimization
        100212, -- 2602.08538 Trajectory Stitching for Solving Inverse Problems with Flow-Based Mode
        100409, -- 2601.16880 Theory of Minimal Weight Perturbations in Deep Networks and its Applic
        100421, -- 2512.07247 AdLift: Lifting Adversarial Perturbations to Safeguard 3D Gaussian Spl
        100746, -- 2505.16736 Backward Oversmoothing: why is it hard to train deep Graph Neural Netw
        100801, -- 2602.19017 Why ReLU? A Bit-Model Dichotomy for Deep Network Training
        100906, -- 2602.12952 Transporting Task Vectors across Different Architectures without Train
        101266, -- 2605.28900 Spectral Guidance for Flexible and Efficient Control of Diffusion Mode
        101279, -- 2605.29664 AMDP: Asynchronous Multi-Directional Pipeline Parallelism for Large-Sc
        101286, -- 2602.11408 GHOST: Unmasking Phantom States in Mamba2 via Grouped Hidden-state Out
        101318, -- 2603.20020 Detached Skip-Links and $R$-Probe: Decoupling Feature Aggregation from
        101412, -- 2605.31005 Learning Multi-Agent Coordination via Sheaf-ADMM
        101482, -- 2605.19073 Riemannian Networks over Full-Rank Correlation Matrices
        101490, -- 2602.08306 TextResNet: Decoupling and Routing Optimization Signals in Compound AI
        101627, -- 2601.23231 Solving Inverse Problems with Flow-based Models via Model Predictive C
        101710, -- 2510.19420 Securing Multi-Agent Systems Against Corruptions via Node Contribution
        101723, -- 2605.10989 SURGE: Surrogate Gradient Adaptation in Binary Neural Networks
        101890, -- 2602.19066 IDLM: Inverse-distilled Diffusion Language Models
        101939, -- 2605.30198 Active Continual Learning with Metaplastic Binary Bayesian Neural Netw
        101952, -- 2604.26258 FlowBot: Inducing LLM Workflows with Bilevel Optimization and Textual
        101981, -- 2605.21108 Efficient Learning of Deep State Space Models via Importance Smoothing
        102015, -- 2512.21829 Tilt Matching for Scalable Sampling and Fine-Tuning
        102212, -- 2605.31236 SwitchCraft: A Programmatic Framework for Designing State-Switching Pr
        102332, -- 2606.12411 Context-Driven Incremental Compression for Multi-Turn Dialogue Generat
        102335, -- 2605.13435 Q-Flow: Stable and Expressive Reinforcement Learning with Flow-based P
        102367, -- 2606.00243 Dynamics and Representation Structure of Local Approximations to Gradi
        102377, -- 2605.03288 Neural Control: Adjoint Learning Through Equilibrium Constraints
        102436, -- 2602.03211 Lookahead Sample Reward Guidance for Test-Time Scaling of Diffusion Mo
        103284, -- 2604.10918 CSPO: Alleviating Reward Ambiguity for Structured Table-to-LaTeX Gener
        103888, -- 2502.02538 Flow Q-Learning
        104041, -- 2607.15275 RoboTTT: Context Scaling for Robot Policies
        104485, -- 2607.20368 Self Gradient Forcing: Native Long Video Extrapolation
        104994, -- 2507.00582 Bridging Classical and Learning-based Iterative Registration through D
        105431, -- 2506.19174 MOSCARD - Multimodal Opportunistic Screening for Cardiovascular Advers
        106007, -- 2605.28983 The Hamilton-Jacobi Theory of Deep Learning
        106053, -- 2605.22967 Learned Relay Representations for Forward-Thinking Discrete Diffusion
        106757, -- 2511.08079 Deep Inverse Shading: Consistent Albedo and Surface Detail Recovery vi
        107141, -- 2509.00189 HiVA: Self-organized Hierarchical Variable Agent via Goal-driven Seman
        107328, -- 2405.18248 Extreme Value Monte Carlo Tree Search for Classical Planning
        107566, -- 2602.05454 Attention Retention for Continual Learning with Vision Transformers
        108130, -- 2512.10461 T-SKM-Net: Trainable Neural Network Framework for Linear Constraint Sa
        109006, -- 2607.27945 Complementary Matrix-Gated QKAN Fast-Weight Programmers for Quantum Dy
        109238, -- 1708.00630 ProjectionNet: Learning Efficient On-Device Deep Networks Using Neural
        109442, -- 2608.17310 Agentic ESOpt: Fine-Tuning Long-Horizon LLM Agents with Minimal GPU Re
        109998, -- 2505.11717 WebInject: Prompt Injection Attack to Web Agents
        110319, -- 2508.19633 A Symbolic Adversarial Learning Framework for Evolving Fake News Gener
        110971, -- 2509.16516 LLM-Guided Co-Training for Text Classification
        112393, -- external Efficient Few-Shot Action Recognition via Multi-Level Post-Reasoning
        112535, -- external Attention Decomposition for Cross-Domain Semantic Segmentation
        112784, -- 2407.16193 CloudFixer: Test-Time Adaptation for 3D Point Clouds via Diffusion-Gui
        112896, -- 2407.15844 HandDGP: Camera-Space Hand Mesh Prediction with Differentiable Global
        112901, -- 2312.02141 iMatching: Imperative Correspondence Learning
        112918, -- external Unsupervised Dense Prediction using Differentiable Normalized Cuts
        112965, -- 2407.09115 Layer-Wise Relevance Propagation with Conservation Property for ResNet
        112993, -- 2407.06964 Parameter-Efficient and Memory-Efficient Tuning for Vision Transformer
        113446, -- external RecurrentBEV: A Long-term Temporal Fusion Framework for Multi-view 3D
        113604, -- external Revisit Self-supervision with Local Structure-from-Motion
        113621, -- 2405.00760 Deep Reward Supervisions for Tuning Text-to-Image Diffusion Models
        113666, -- 2407.15540 Differentiable Product Quantization for Memory Efficient Camera Reloca
        113900, -- 2609.00591 A Glance Is All You Need: Single-Pass Fine-Grained Image Captioning wi
        114175, -- 2609.13141 SAS: Simple Attention Sparsification via End-to-End Optimization of Co
        114408, -- external Black-Box Adaptation for Medical Image Segmentation
        115579, -- 2405.02066 WateRF: Robust Watermarks in Radiance Fields for Protection of Copyrig
        116057, -- 2403.18293 Efficient Test-Time Adaptation of Vision-Language Models
        116211, -- 2402.02887 Time- Memory- and Parameter-Efficient Visual Adaptation
        116788, -- 2311.13612 Descriptor and Word Soups: Overcoming the Parameter Efficiency Accurac
        116798, -- 2406.02996 Quantifying Task Priority for Multi-Task Optimization
        117095, -- 2403.16885 CVT-xRF: Contrastive In-Voxel Transformer for 3D Consistent Radiance F
        117224, -- 2403.03122 NRDF: Neural Riemannian Distance Fields for Learning Articulated Pose
        117225, -- external RepAn: Enhanced Annealing through Re-parameterization
        117400, -- 2607.13265 Differentiable Polarized Path Tracing
        117609, -- 2603.21695 RefracGS: Novel View Synthesis Through Refractive Water Surfaces with
        118541, -- 2511.20705 Solving Diffusion Inverse Problems with Restart Posterior Sampling
        118579, -- 2512.05672 InverseCrafter: Efficient Video ReCapture as a Latent Domain Inverse P
        119486, -- 2607.12042 SymbOmni: Evolving Agentic Omni Models via Symbolic Concept Learning
        119583, -- 2604.08456 Entropy-Gradient Grounding: Training-Free Evidence Retrieval in Vision
        119718, -- 2406.09801 RaNeuS: Ray-adaptive Neural Surface Reconstruction
        119836, -- external DeepLA-Net: Very Deep Local Aggregation Networks for Point Cloud Analy
        119887, -- external No Pains, More Gains: Recycling Sub-Salient Patches for Efficient High
        120189, -- external Convex Combination Star Shape Prior for Data-driven Image Semantic Seg
        120207, -- external D^3CTTA: Domain-Dependent Decorrelation for Continual Test-Time Adapti
        120838, -- external ViTPrompt: Training-Free Prompt Refinement with Visual Tokens for Open
        120842, -- external Resolving the Stability-Plasticity Dilemma in Reinforcement Learning v
        121190, -- external Circular-DPO: Aligning Multi-Stage 3D Generative Models via Preference
        121209, -- external SpeeDiff: Scalable Pixel-Anchored End-to-End Latent Diffusion Model
        121259, -- external Localizing, Structuring, and Rendering: Bridging 3D and 2D Vision-Lang
        121264, -- external Curvature-Aware Zeroth-Order Optimization for Memory-Efficient Test-Ti
        121712, -- external PureProof: Diffusion-Resistant Black-box Targeted Attack on Large Visi
        121918, -- 1511.07247 NetVLAD: CNN architecture for weakly supervised place recognition
        122388, -- 2609.31892 NVAlign: Direct-Gradient Optimization for Non-Verbal Control in Contin
        122612, -- 2609.39627 Introduction to Computer Vision
        122675, -- 2609.34895 LVMT: Video Mask Transformer for Long-term Video Segmentation
        122789, -- 2610.04426 UnAct: Gradient-Free Unlearning via Targeted Activation Intervention
        122815, -- 2610.05954 MEND: RL For Flow Models via Proximal Velocity Matching
        122979, -- 2609.34344 Learning to Steer, Steering to See: Unveiling the Geometry of RLVR in
        123081, -- 2210.04195 Online Training Through Time for Spiking Neural Networks
        123386, -- 2610.17552 FlashVSR+: Efficient Video Super-Resolution via Hybrid Attention and R
        123650, -- 2310.19859 Res-Tuning: A Flexible and Efficient Tuning Paradigm via Unbinding Tun
        123849, -- 2011.07357 Solving Physics Puzzles by Reasoning about Paths
        123852, -- 2610.25844 SWIFT: Self-guided Weak-to-strong dIFfusion models via Target extrapol
        124037, -- 2610.31574 Rethinking Sequence Compression with Test-time Regression
        124367, -- external From Outcome to Representation: Tracing Reasoning Mechanisms through I
        124458, -- external End-to-End Differentiable Diffusion Conditioning for Physics-Informed
        124503, -- 2604.15259 Stability and Generalization in Looped Transformers
        124930, -- 2605.14297 Policy Optimization in Hybrid Discrete-Continuous Action Spaces via Mi
        125012, -- 2610.04093 Beyond Masked Sparsity: SNACK Enables Truly Sparse Neural Networks on
        125233, -- 2605.07907 Consistency Regularised Gradient Flows for Inverse Problems
        125389, -- external Training-Free Open World Object Detection
        125539, -- 2606.00066 DUET: Unified Dual-Space Emotion Control for Diffusion and Flow-Matchi
        125663, -- 2606.27095 Data-Free Reservoir Features for Efficient Long-Horizon Cold-Start Con
        125693, -- 2605.12683 Parallel-in-Time Training of Recurrent Neural Networks for Dynamical S
        125907, -- external Subset-Conditioned Boundary Compensation for Missing-Modality Multimod
        126014, -- 2606.16454 SDS-LoRA: Overcoming Anisotropic Gradient Scaling in Low-Rank Adaptati
        126235, -- external FLIP: Fast and Accurate Global Lipschitz Estimation for Large Feedforw
        126278, -- external Restoring the RNA-Ligand Interaction Manifold via Topology-Preserving
        126432, -- external Inverse Modeling of Neural Recordings via Differentiable Biophysical S
        126445, -- external Efficient Diffusion Policy Fine Tuning with Latent Noise Representatio
        126680, -- external DrPO: Drifting Preference Optimization for One-Step Generative Models
        126748, -- external Echo learning enables biologically plausible temporal credit assignmen
        126804, -- 2610.21748 The Dormant Spiking Neuron: A State-Driven Mechanism for Efficient Spi
        126816, -- 2605.06126 AffectGPT-RL: Revealing Roles of Reinforcement Learning in Open-Vocabu
        126888, -- external Bonobo: Efficient Library-Scale Generation for De Novo Antibody Design
        126900, -- external Efficient Training of Deep Spiking Neural Networks with Input-Driven D
        126996, -- external From Static Geometry to Dynamical Singularity: Detecting Memorization
        127003, -- external Iterative Nonlinear Computation Underlying Abstract Reasoning
        127053, -- 2601.10471 DeFlow: Decoupling Behavior-Prior Modeling and Value Maximization for
        127435, -- 2610.10857 Self-Supervised Keyframe Discovery for Horizon-Invariant Behavior Clon
        127529, -- 2605.16208 A Scalable Nonparametric Continuous-Time Survival Model through Numeri
        127601, -- 2609.31066 Modeling quantum neural network gradient with reinforcement learning
        127752, -- 2605.08733 Generative Actor-Critic with Soft Bridge Policies
        127925, -- external HyperFlow: Gradient-Free Test-Time Adaptation for Cross-Domain Few-Sho
        128197, -- 2603.17685 Flow Matching Policy Optimization with Mirror Descent and Entropy Cons
        128385, -- 2605.08323 The Reciprocity Gradient
        128402, -- external Incorporating Neural Network Structure in the Bayesian Learning Rule
        128739, -- external SpikingGamma: Temporally Precise Online SNN Training Through Smoothed
        128812, -- external Moment-Constrained Latent Steering for Flow Policy
        128908, -- external Improving Quantized Zeroth-Order Optimization through Reconstructed Lo
        128921, -- external Co-GRPO: Co-Optimized Group Relative Policy Optimization for Masked Im
        129011, -- 2606.19741 Interpreting Neural Combinatorial Optimization via Evolving Programmat
        129053, -- 2609.35615 Behavioral Foundation Models for Quality Diversity
        129366, -- 2605.06152 Grokking or Glitching? How Low-Precision Drives Slingshot Loss Spikes
        129383, -- external Freshness-Gated Imagination: Step-Level Trust for Latent World Models
        129450, -- 2604.01030 Diff3R: Feed-forward 3D Gaussian Splatting with Uncertainty Aware Diff
        129460, -- external An Educated Guess: Deriving Statistically Aligned Gradient Estimates f
        129500, -- external CoTs as Probabilistic Programs: A Programmatic View of Thinking Step-b
        129556, -- 2605.14489 A Novel Schur-Decomposition-Based Weight Projection Method for Stable
        129656, -- 2606.22630 Scalable Maximum Entropy Reinforcement Learning for Diffusion Policies
        129793, -- external MICA: Activation Checkpointing for Double-Backward Training of Machine
        129943, -- external Beyond Single-Shot Conditioning: Test-Time Condition Refinement for Di
        129983, -- external Closed-Form Implicit Neural Representations
        130071, -- 2512.05511 Rethinking Infrared Small Target Detection: A Foundation Driven Effici
        130187, -- 2609.04134 Prospective Coding Improves Learning in Deep Continuous-Time Recurrent
        130376, -- 2510.00563 Memory Determines Learning Direction: A Theory of Gradient-Based Optim
        130382, -- 2603.12677 MetaKE: Meta-Learning for Knowledge Editing Toward a Better Accuracy-E
        130528, -- 2606.14222 Learning the Context of Errors: Black-Box Online Adaptation of Time Se
        130698, -- 2605.12801 Fast and Stable Gradient Approximation for Bilinear Forms of Hermitian
        130727, -- 2606.24969 Frequency Domain Reservoir Computing
        130878, -- external Filtered-Trace Online Variational Training for Probabilistic Spiking N
        131077, -- external Coarse-to-Fine 3D MRI Reconstruction via Resolution-Agnostic Neural Op
        131624, -- 2610.38331 Multi-Token Prediction Done Right
        131734, -- 2610.37481 Follow the Gradient: Tracing Safety Degradation Back to Training Data
        131887, -- external Trainable Fractional Fourier Transform
        132001, -- 2611.00448 Learning to evolve by matching velocities
        132061  -- 2609.11801 Thinking with Looped Flows
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Taxonomy gap fill 2026-11-09: uses backpropagation only as routine training, or means BPTT, tree search or textual feedback'
FROM backpropagation_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING backpropagation_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING backpropagation_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- empirical-risk-minimization: 120 links, 12 exclusions.
CREATE TEMP TABLE empirical_risk_minimization_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'empirical-risk-minimization'
  AND p.id IN (
        931, -- 1710.09412 mixup: Beyond Empirical Risk Minimization
        1986, -- 1904.05046 Generalizing from a Few Examples: A Survey on Few-Shot Learning
        7950, -- 2202.06523 MetaShift: A Dataset of Datasets for Evaluating Contextual Distributio
        9139, -- 2205.11672 Why does Throwing Away Data Improve Worst-Group Error?
        9332, -- 2206.01131 Predictive Multiplicity in Probabilistic Classification
        9361, -- 2206.02058 When Personalization Harms: Reconsidering the Use of Group Attributes
        9415, -- 2206.04046 Sparse Mixture-of-Experts are Domain Generalizable Learners
        10076, -- 2208.08661 Domain-Specific Risk Minimization for Out-of-Distribution Generalizati
        10572, -- 2210.02390 Bayesian Prompt Learning for Image-Language Model Generalization
        11032, -- 2210.13512 Provably Learning Diverse Features in Multi-View Data with Midpoint Mi
        11218, -- 2211.02291 SelecMix: Debiased Learning by Contradicting-pair Sampling
        12547, -- 2301.11214 Returning The Favour: When Regression Benefits From Probabilistic Caus
        12812, -- 2302.01629 Beyond the Universal Law of Robustness: Sharper Laws for Random Featur
        12896, -- 2302.03115 Easy Learning from Label Proportions
        13337, -- 2302.13934 Statistical Learning under Heterogeneous Distribution Shift
        13456, -- 2303.01566 On the Provable Advantage of Unsupervised Pretraining
        13501, -- 2303.02732 Iterative Approximate Cross-Validation
        13560, -- 2303.04278 CUDA: Convolution-based Unlearnable Datasets
        14543, -- 2304.03916 Mitigating Spurious Correlations in Multi-modal Models during Fine-tun
        16221, -- 2305.15196 Feature-aligned N-BEATS with Sinkhorn divergence
        16768, -- 2306.00740 On the Limitations of Temperature Scaling for Distributions with Overl
        17083, -- 2306.04174 End-to-End Learning for Stochastic Optimization: A Bayesian Perspectiv
        18020, -- 2307.02245 Set Learning for Accurate and Calibrated Models
        18806, -- 2307.16851 Towards Trustworthy and Aligned Machine Learning: A Data-centric Surve
        19058, -- 2308.04553 From Fake to Real: Pretraining on Balanced Synthetic Images to Prevent
        20572, -- 2309.09888 Context is Environment
        20913, -- 2309.14563 Towards a statistical theory of data selection under weak supervision
        21114, -- 2310.00027 Out-Of-Domain Unlabeled Data Improves Generalization
        22377, -- 2310.14661 Tractable MCMC for Private Learning with Pure and Gaussian Differentia
        26339, -- 2401.14846 Understanding Domain Generalization: A Noise Robustness Perspective
        32339, -- 2406.02862 Rethinking Guidance Information to Utilize Unlabeled Samples:A Label E
        35514, -- 2408.01746 Domain penalisation for improved Out-of-Distribution Generalisation
        36476, -- 2409.00908 EnsLoss: Stochastic Calibrated Loss Ensembles for Preventing Overfitti
        39476, -- 2411.00079 Label Noise: Ignorance Is Bliss
        39522, -- 2411.00743 Decoding Dark Matter: Specialized Sparse Autoencoders for Interpreting
        40769, -- 2412.00569 Contextual Bandits in Payment Processing: Non-uniform Exploration and
        43224, -- 2501.14912 Feasible Learning
        45722, -- 2503.06698 What's in a Latent? Leveraging Diffusion Latent Space for Domain Gener
        62981, -- 2601.02322 Environment-Adaptive Covariate Selection: Learning When to Use Spuriou
        74313, -- 2503.02138 Elliptic Loss Regularization
        75650, -- 2411.19757 Dual Risk Minimization: Towards Next-Level Robustness in Fine-tuning Z
        78639, -- 2308.08778 Environment Diversification with Multi-head Neural Network for Invaria
        80419, -- 2102.08604 SWAD: Domain Generalization by Seeking Flat Minima
        81708, -- 1906.01908 Empirical Risk Minimization under Random Censorship: Theory and Practi
        82893, -- 2605.06643 Are We Making Progress in Multimodal Domain Generalization? A Comprehe
        85920, -- 2506.12994 Differentially Private Bilevel Optimization: Efficient Algorithms with
        85944, -- 2506.00135 Tradeoffs between Mistakes and ERM Oracle Calls in Online and Transduc
        86079, -- 2502.06343 Causal Lifting of Neural Representations: Zero-Shot Generalization for
        86147, -- 2411.13029 Probably Approximately Precision and Recall Learning
        86395, -- 2503.21071 Purifying Approximate Differential Privacy with Randomized Post-proces
        86811, -- 2502.09257 Bandit Multiclass List Classification
        86853, -- 2505.17435 Discretization-free Multicalibration through Loss Minimization over Tr
        86891, -- 2505.17958 The Nuclear Route: Sharp Asymptotics of ERM in Overparameterized Quadr
        87162, -- 2502.09496 On Agnostic PAC Learning in the Small Error Regime
        87541, -- 2503.13236 Gradient Extrapolation for Debiased Representation Learning
        87575, -- 2503.17226 DDB: Diffusion Driven Balancing to Address Spurious Correlations
        88628, -- 2505.23027 Diverse Prototypical Ensembles Improve Robustness to Subpopulation Shi
        88700, -- 2503.04706 Sample-Optimal Agnostic Boosting with Unlabeled Data
        88782, -- 2503.07988 Provable Zero-Shot Generalization in Offline Reinforcement Learning
        88805, -- 2502.13283 Benefits of Early Stopping in Gradient Descent for Overparameterized L
        88811, -- 2505.05355 Nearly Optimal Sample Complexity for Learning with Label Proportions
        89287, -- 2505.24737 Adapting to Linear Separable Subsets with Large-Margin in Differential
        89334, -- 2410.05880 Improved Sample Complexity for Private Nonsmooth Nonconvex Optimizatio
        89351, -- 2410.06303 Compositional Risk Minimization
        89407, -- 2410.22656 Tilted Sharpness-Aware Minimization
        91403, -- 2501.18277 SEBRA : Debiasing through Self-Guided Bias Ranking
        92208, -- 2410.05609 The Breakdown of Gaussian Universality in Classification of High-dimen
        92225, -- 2404.01712 Hessian-Free Online Certified Unlearning
        92363, -- 2410.18837 High-dimensional Analysis of Knowledge Distillation: Weak-to-Strong Ge
        92888, -- 2603.04546 Oracle-efficient Hybrid Learning with Constrained Adversaries
        93757, -- 2505.21422 When Shift Happens - Confounding Is to Blame
        93779, -- 2602.03895 Benchmarking Bias Mitigation Toward Fairness Without Harm from Vision
        93916, -- 2505.05740 Deep-ICE: The first globally optimal algorithm for empirical risk mini
        93995, -- 2509.24801 Physics-informed learning under mixing: How physical knowledge speeds
        94161, -- 2508.07392 Tight Bounds for Schrodinger Potential Estimation in Unpaired Data Tra
        94499, -- 2602.01863 Transformers as Measure-Theoretic Associative Memory: A Statistical Pe
        99783, -- 2604.03146 Characterization of Gaussian Universality Breakdown in High-Dimensiona
        100296, -- 2605.11638 Learning $U$-Statistics with Active Inference
        100361, -- 2601.23031 Asymptotic Theory of Iterated Empirical Risk Minimization, with Applic
        100801, -- 2602.19017 Why ReLU? A Bit-Model Dichotomy for Deep Network Training
        100849, -- 2504.12175 Approximation Bounds for Transformer Networks with Application to Regr
        100915, -- 2602.08350 All ERMs Can Fail in Stochastic Convex Optimization Lower Bounds in Li
        100958, -- 2512.12572 On the Accuracy of Newton Step and Influence Function Data Attribution
        101028, -- 2602.10680 A Solvable High-Dimensional Model Where Nonlinear Autoencoders Learn S
        101093, -- 2509.24914 Single-Head Attention in High Dimensions: A Theory of Generalization,
        101189, -- 2601.17257 A Constrained Optimization Perspective of Unrolled Transformers
        101857, -- 2606.06855 Stability beyond Bounded Differences: Sharp Generalization Bounds unde
        102042, -- 2604.09175 Generalization and Scaling Laws for Mixture-of-ExpertsTransformers
        102125, -- 2606.12691 Two-Layer Linear Auto-Regressive Models Estimate Latent States
        102202, -- 2510.14331 LLM Priors for ERM over Programs
        105939, -- 2607.05850 Breaking Spurious Correlations via Generative Randomization and Cross-
        106486, -- 2409.04407 Exploiting Missing Data Remediation Strategies Using Adversarial Missi
        106574, -- 2601.12296 Distribution Shift Is Key to Learning Invariant Prediction
        106807, -- 2511.10133 S-D-RSM: Stochastic Distributed Regularized Splitting Method for Large
        113447, -- 2409.17691 Efficient Bias Mitigation Without Privileged Information
        115527, -- 2302.04729 Task-Driven Wavelets using Constrained Empirical Risk Minimization
        115874, -- 2402.18919 Decompose-and-Compose: A Compositional Approach to Mitigating Spurious
        116898, -- 2403.07241 Calibrating Multi-modal Representations: A Pursuit of Group Robustness
        117182, -- 2402.18817 Gradient Alignment for Cross-Domain Face Anti-Spoofing
        117865, -- 2603.29313 HSFM: Hard-Set-Guided Feature-Space Meta-Learning for Robust Classific
        120012, -- 2512.22874 Let Samples Speak: Mitigating Spurious Correlation by Exploiting the C
        124322, -- 2606.28309 Surprises in Proper Positive-Only Learning
        124649, -- 2605.09565 Online Set Learning from Precision and Recall Feedback
        125245, -- 2610.01028 Optimal Transport Reweighting for Robust Learning under Spurious Corre
        125939, -- external Reference-Guided Training: Adaptive Gradient Scaling via Per-Sample Lo
        126278, -- external Restoring the RNA-Ligand Interaction Manifold via Topology-Preserving
        126709, -- 2605.07155 Regret–Oracle Complexity Tradeoffs in Agnostic Online Learning
        126792, -- external Stability-Weighted Direction Regularization Disentangles Generator Sho
        126831, -- 2605.17799 Is Complex Training Necessary for Long-Tailed OOD Detection? A Re-thin
        126914, -- external Majority-of-Three is an Optimal PAC Learner
        128555, -- 2602.00437 Exact Instance Compression for Convex Empirical Risk Minimization via
        128607, -- 2602.02358 Transfer Learning Through Conditional Quantile Matching
        128769, -- external On JEPA Isotropy
        129536, -- 2602.06924 Rank-Constrained Adaptation for Reliable Real-World Performance
        129699, -- external Taming the Tails: Why Distributionally Robust Optimization Needs New T
        130101, -- 2609.31458 Nonparametric In-Context Learning under Growing Geometric Complexity:
        130462, -- external Random-Effects Centroids for Domain Generalization
        130730, -- external Causal Gradient Steering: Exposing Shortcut Gradients by Destroying Ca
        131151, -- 2605.08811 Learning Theory of Transformers: Local-to-Global Approximation via Sof
        131242  -- external Optimal Byzantine-resilient Federated Learning with User-level Differe
  );

DELETE FROM paper_method_exclusions x
USING empirical_risk_minimization_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM empirical_risk_minimization_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM empirical_risk_minimization_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE empirical_risk_minimization_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'empirical-risk-minimization'
  AND p.id IN (
        12656, -- 2301.12736 On Second-Order Scoring Rules for Epistemic Uncertainty Quantification
        114921, -- 2407.06250 FairDiff: Fair Segmentation with Point-Image Diffusion
        121622, -- external Learning Forgery-Aware Lip Representations Without Forgery Priors
        127321, -- 2609.35703 A Unified Uncertainty Representation for Graph Neural Networks via Dou
        49264, -- 2505.15143 Filtering Learning Histories Enhances In-Context Reinforcement Learnin
        24729, -- 2312.08255 OCTDL: Optical Coherence Tomography Dataset for Image-Based Deep Learn
        56699, -- 2603.13224 Visual-ERM: Reward Modeling for Visual Equivalence
        61192, -- 2602.05152 RAG without Forgetting: Continual Query-Infused Key Memory
        87319, -- 2506.21683 Risk-Averse Total-Reward Reinforcement Learning
        96230, -- 2605.04757 3D Printing of Passively Actuated Self-Folding Robots with Integrated
        115172, -- external Ocular Stethoscope: Auditory Support for Retinal Membrane Peeling
        130294  -- external AERO: Adaptive Ensemble-Disagreement Routing for Oracle Feedback in Sa
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Taxonomy gap fill 2026-11-09: ERM means another term, or the mention is a passing one'
FROM empirical_risk_minimization_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING empirical_risk_minimization_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING empirical_risk_minimization_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- Hero image credits (images imported with import_entity_image.py).
UPDATE methods SET image_credit = '[Generative Adversarial Imitation Learning](/paper/1606.03476)' WHERE slug = 'gail';
UPDATE methods SET image_credit = '[FixMatch: Simplifying Semi-Supervised Learning with Consistency and Confidence](/paper/2001.07685)' WHERE slug = 'pseudo-labeling';
UPDATE methods SET image_credit = '[An Empirical Evaluation of Generic Convolutional and Recurrent Networks for Sequence Modeling](/paper/1803.01271)' WHERE slug = 'temporal-convolutional-network';
UPDATE methods SET image_credit = '[Learning Spatiotemporal Features with 3D Convolutional Networks](/paper/1412.0767)' WHERE slug = '3d-convolution';
UPDATE methods SET image_credit = '[Back Propagation Example](https://commons.wikimedia.org/wiki/File:Back_Propagation_Example.svg), Andreas Maier, CC BY 4.0' WHERE slug = 'backpropagation';
UPDATE methods SET image_credit = '[mixup: Beyond Empirical Risk Minimization](/paper/1710.09412)' WHERE slug = 'empirical-risk-minimization';
