-- Method gap fill 2026-11-10 (tier 2, group J): optimizers, initialization,
-- parameter-efficient fine-tuning and speech features.
--
-- Sourced (introducing paper is local, so an "Introduced" banner is added):
--   lion (2302.06675), kaiming-initialization (1502.01852), dora (2402.09353),
--   adapter-tuning (1902.00751).
-- Unsourced (no arXiv introducing paper; source_url points to the canonical
-- reference): adagrad (Duchi et al., JMLR 2011), rmsprop (Hinton's Coursera
-- lecture 6e, 2012), residual-vector-quantization (multistage VQ, Juang & Gray
-- 1982, long before SoundStream popularized it for neural codecs), mfcc (Davis &
-- Mermelstein 1980).
--
-- Keywords drive the daily keyword backfill and are limited to exact long-form
-- names. Bare "Lion" (SEA-Lion, Lion distillation, sea lions), "DoRA" (DoRA video
-- SSL, Dynamic Low-Rank Adaptation, ViDoRAG), "RVQ" (RVQA, OCRVQA, RVQuant) and
-- "adapter" collide with other senses, so they live only in name/full_name where
-- the abstract linker (or the Jev judge) decides.
--
-- Paper links: for sourced methods the local Semantic Scholar citers of the
-- source were linked with link_papers_by_source_citations.py and then reviewed;
-- citers whose title/abstract does not name the method became exclusions. For
-- all methods, title/abstract candidates were reviewed by hand; true positives
-- get 'manual' evidence and reviewed negatives become durable exclusions.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES
(
    'adagrad',
    'AdaGrad',
    'Adaptive Gradient Algorithm (AdaGrad)',
    'AdaGrad (Adaptive Gradient Algorithm), introduced by Duchi, Hazan and Singer (JMLR 2011), adapts the learning rate of every parameter to the history of its gradients. It accumulates the sum of squared gradients G_t = Σ g_s² and updates θ ← θ − η g_t / (√G_t + ε), so coordinates with large or frequent gradients take small steps and rare, informative features take large ones. The original paper derived it from online convex optimization with adaptive proximal functions and proved regret bounds that adapt to the geometry of the data, with diagonal and full-matrix variants. AdaGrad works well for sparse problems such as linear models over text features and embedding tables in recommendation systems, but because G_t only grows, its effective learning rate decays towards zero on long non-convex runs. [RMSProp](/methods/rmsprop) and AdaDelta replace the sum with an exponential moving average, and [Adam](/methods/adam) adds momentum on top. AdaGrad-Norm (a single scalar step size) is a standard object in convergence theory, and [Shampoo](/paper/1802.09568) and its distributed implementations approximate full-matrix AdaGrad with Kronecker-factored preconditioners.',
    'adagrad, ada-grad, adaptive gradient algorithm',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2011,
    NULL,
    'https://jmlr.org/papers/v12/duchi11a.html',
    'Adaptive Subgradient Methods for Online Learning and Stochastic Optimization (Duchi, Hazan & Singer, JMLR 2011)',
    'https://github.com/pytorch/pytorch/blob/main/torch/optim/adagrad.py',
    NULL,
    'always',
    ARRAY[]::text[]
),
(
    'rmsprop',
    'RMSProp',
    'Root Mean Square Propagation (RMSProp)',
    'RMSProp (Root Mean Square Propagation) is an adaptive learning-rate optimizer proposed by Geoffrey Hinton in lecture 6e of his 2012 Coursera course Neural Networks for Machine Learning; it was never published as a paper. It keeps an exponential moving average of squared gradients, v_t = ρ v_{t−1} + (1 − ρ) g_t², and divides each step by its square root, θ ← θ − η g_t / (√v_t + ε), with ρ ≈ 0.9. This normalizes the gradient scale per parameter like [AdaGrad](/methods/adagrad), but the moving average forgets old gradients, so the effective step size does not decay to zero and the method suits non-stationary, non-convex deep learning objectives. A centered variant that also tracks the mean gradient was used by Graves in [Generating Sequences With Recurrent Neural Networks](/paper/1308.0850). RMSProp was the default optimizer for recurrent networks and for deep reinforcement learning (DQN, A3C) for years, and [Adam](/methods/adam) is essentially RMSProp with momentum and bias correction. It remains a common baseline and an object of study in work on adaptive-optimizer SDEs, convergence and implicit bias.',
    'rmsprop, rms-prop',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2012,
    NULL,
    'https://www.cs.toronto.edu/~tijmen/csc321/slides/lecture_slides_lec6.pdf',
    'Neural Networks for Machine Learning, Lecture 6e: rmsprop (Tieleman & Hinton, 2012)',
    'https://github.com/pytorch/pytorch/blob/main/torch/optim/rmsprop.py',
    NULL,
    'always',
    ARRAY[]::text[]
),
(
    'lion',
    'Lion',
    'Lion (EvoLved Sign Momentum)',
    'Lion (EvoLved Sign Momentum) is an optimizer found by Chen et al. in [Symbolic Discovery of Optimization Algorithms](/paper/2302.06675) through an evolutionary program search over optimizer update rules, followed by simplification. Its update is the sign of an interpolation between the current gradient and a momentum term, θ ← θ − η (sign(β₁ m + (1 − β₁) g) + λ θ), after which the momentum is updated with a second coefficient β₂, m ← β₂ m + (1 − β₂) g. Because every coordinate moves by the same magnitude, Lion keeps only one state tensor (half the memory of [Adam](/methods/adam) and [AdamW](/methods/adamw)) and needs a learning rate 3–10× smaller with a correspondingly larger decoupled weight decay. In the source paper Lion matched or beat AdamW on ViT image classification, CLIP-style contrastive training, diffusion models and language modeling, for example raising ViT ImageNet accuracy by up to 2%. Later work showed that Lion with weight decay solves a box-constrained problem (the Lion-K family), analyzed its convergence, and built distributed, cautious and orthogonalized variants; it is often compared with sign-based optimizers such as signSGD and with [Muon](/methods/muon).',
    'lion optimizer, lion optimiser, evolved sign momentum',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2302.06675'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Symbolic Discovery of Optimization Algorithms',
    'https://github.com/google/automl/tree/master/lion',
    NULL,
    'judge',
    ARRAY['Lion Optimizer']
),
(
    'kaiming-initialization',
    'Kaiming Initialization',
    'Kaiming (He) Initialization',
    'Kaiming initialization, also called He or MSRA initialization, is the weight-initialization scheme derived by He et al. in [Delving Deep into Rectifiers](/paper/1502.01852) for networks with [ReLU](/methods/rectified-linear-unit-relu) and PReLU activations. Because a rectifier zeroes half of its inputs, the variance-preserving [Xavier initialization](/methods/xavier-initialization) shrinks the signal layer after layer; He et al. showed that drawing weights from a zero-mean Gaussian with variance 2 / n_l (n_l being the fan-in, or 2 / ((1 + a²) n_l) for a leaky slope a) keeps the variance of activations, and of back-propagated gradients when computed with fan-out, constant across depth. With it, a 30-layer plain ReLU network trained from scratch, where Xavier-initialized ones stalled. It is the default initialization for convolutional and linear layers followed by ReLU-family activations, including [ResNet](/methods/resnet), and is available as kaiming_normal_ and kaiming_uniform_ in PyTorch. Kaiming initialization with a single learning rate defines the standard parameterization that work on width scaling, μP and signal propagation compares against.',
    'kaiming initialization, kaiming initialisation, kaiming init, he initialization, he initializations, he initialisation, he-initialization, msra initialization, kaiming normal initialization',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2015,
    (SELECT id FROM papers WHERE arxiv_id = '1502.01852'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification',
    'https://github.com/pytorch/pytorch/blob/main/torch/nn/init.py',
    NULL,
    'always',
    ARRAY['He Initialization', 'MSRA Initialization']
),
(
    'dora',
    'DoRA',
    'Weight-Decomposed Low-Rank Adaptation (DoRA)',
    'DoRA (Weight-Decomposed Low-Rank Adaptation), introduced by Liu et al. in [DoRA: Weight-Decomposed Low-Rank Adaptation](/paper/2402.09353), is a parameter-efficient fine-tuning method that extends [LoRA](/methods/lora). It reparameterizes each pre-trained weight matrix as a magnitude vector times a unit-norm direction, W = m · V / ‖V‖_c, trains the magnitude m directly, and applies a low-rank LoRA update BA only to the direction, V = W₀ + BA. A weight-decomposition analysis in the paper showed that LoRA tends to change magnitude and direction together, whereas full fine-tuning often changes them in opposite proportions; decoupling them lets DoRA learn patterns closer to full fine-tuning. Like LoRA, the update merges into the weights after training, so inference costs nothing extra. DoRA outperformed LoRA at the same or lower rank on commonsense reasoning with LLaMA models, visual instruction tuning with LLaVA and image/video-text understanding with VL-BART, and is available in Hugging Face [PEFT](/methods/peft). It is a standard baseline for newer LoRA variants, and follow-ups reduce its memory and compute overhead (EDoRA, fused kernels) or extend the decomposition (BoRA).',
    'weight-decomposed low-rank adaptation, weight-decomposed low rank adaptation, weight decomposed low-rank adaptation',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2024,
    (SELECT id FROM papers WHERE arxiv_id = '2402.09353'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'DoRA: Weight-Decomposed Low-Rank Adaptation',
    'https://github.com/NVlabs/DoRA',
    NULL,
    'judge',
    ARRAY[]::text[]
),
(
    'adapter-tuning',
    'Adapter Tuning',
    'Adapter Tuning (Bottleneck Adapters)',
    'Adapter tuning, introduced by Houlsby et al. in [Parameter-Efficient Transfer Learning for NLP](/paper/1902.00751), adapts a frozen pre-trained network to a new task by inserting small trainable modules, adapters, inside each layer and training only those (plus layer norms and the task head). A bottleneck adapter projects the d-dimensional hidden state down to a small dimension r, applies a nonlinearity, projects back up and adds the result through a residual connection initialized near the identity; Houlsby et al. placed two per [Transformer](/methods/transformer) block, after the attention and feed-forward sublayers. On GLUE, adapters on [BERT](/methods/bert) came within 0.4% of full fine-tuning while training about 3.6% of the parameters per task, so one shared backbone can serve many tasks. Adapters were the first widely used [parameter-efficient fine-tuning](/methods/peft) method and led to parallel and sequential variants, [AdapterFusion](/paper/2005.00247), the [AdapterHub](/paper/2007.07779) library, hypercomplex [Compacter](/paper/2106.04647) layers and a [unified view](/paper/2110.04366) with [LoRA](/methods/lora), [Prefix Tuning](/methods/prefix-tuning) and [Prompt Tuning](/methods/prompt-tuning). Unlike LoRA, adapters cannot be merged into the weights and add a small inference cost. They are widely used to adapt vision transformers, CLIP, self-supervised speech models and multilingual models.',
    'adapter tuning, adapter-tuning, adapter-based fine-tuning, bottleneck adapter, bottleneck adapters, houlsby adapter, houlsby adapters',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2019,
    (SELECT id FROM papers WHERE arxiv_id = '1902.00751'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Parameter-Efficient Transfer Learning for NLP',
    'https://github.com/google-research/adapter-bert',
    NULL,
    'always',
    ARRAY['Bottleneck Adapter']
),
(
    'residual-vector-quantization',
    'Residual Vector Quantization',
    'Residual Vector Quantization (RVQ)',
    'Residual vector quantization (RVQ), also called multistage or residual quantization (RQ), encodes a vector with a cascade of codebooks: the first stage quantizes the input with ordinary [vector quantization](/methods/vector-quantization-vq), each later stage quantizes the residual error left by the previous ones, and the reconstruction is the sum of the selected codewords. With N stages of K codewords it addresses K^N reconstruction points while storing and searching only N·K codewords, and dropping later stages gives coarser codes, which makes the bitrate scalable. Multistage VQ was studied for speech coding in the early 1980s (Juang & Gray, 1982) and residual quantization is a standard tool for approximate nearest-neighbour search. [SoundStream](/methods/soundstream) made RVQ trainable end to end inside a [neural audio codec](/methods/neural-audio-codec), with quantizer dropout for variable bitrate, and it became the standard quantizer of codecs such as [EnCodec](/paper/2210.13438), [DAC](/paper/2306.06546) and Mimi. RVQ tokens feed codec language models for speech and music generation such as [VALL-E](/paper/2301.02111) and [Moshi](/paper/2410.00037), and RQ-VAE tokenizers apply it to images ([Autoregressive Image Generation using Residual Quantization](/paper/2203.01941)), human motion, actions and generative-retrieval identifiers. Finite scalar quantization and single-codebook tokenizers are its main alternatives.',
    'residual vector quantization, residual vector quantisation, residual vector quantizer, residual vector quantizers, residual vector-quantized, RVQ-VAE, RVQGAN, RVQ-GAN',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1109/ICASSP.1982.1171604',
    'Multiple Stage Vector Quantization for Speech Coding (Juang & Gray, ICASSP 1982)',
    'https://github.com/facebookresearch/encodec/blob/main/encodec/quantization/core_vq.py',
    NULL,
    'always',
    ARRAY['Residual Quantization (RQ)']
),
(
    'mfcc',
    'Mel-Frequency Cepstral Coefficients',
    'Mel-Frequency Cepstral Coefficients (MFCC)',
    'Mel-frequency cepstral coefficients (MFCCs) are a compact representation of the short-term power spectrum of a sound, popularized for speech recognition by Davis and Mermelstein (1980), who found them the best of several parametric representations for recognizing words in continuous speech. To compute them, the signal is cut into overlapping frames of about 25 ms, each frame is windowed and transformed with the [Fourier transform](/methods/fourier-transform), the power [spectrogram](/methods/spectrogram) is pooled by a bank of triangular filters spaced on the perceptual mel scale, the log filter-bank energies are taken, and a discrete cosine transform decorrelates them; usually the first 12–20 coefficients are kept, often with their first and second time derivatives (deltas). MFCCs were the standard front end of [Gaussian mixture model](/methods/gaussian-mixture-model) and [hidden Markov model](/methods/hidden-markov-model) speech recognizers and of i-vector speaker recognition. Deep models now mostly use log-mel filter banks or learn features from raw audio, but MFCCs remain a common input for keyword spotting, speaker identification, speech emotion and pathology detection, environmental sound classification and spoof detection, a baseline against self-supervised speech representations, and the target of HuBERT''s first clustering iteration.',
    'mel-frequency cepstral coefficients, mel frequency cepstral coefficients, mel-frequency cepstral coefficient, mel frequency cepstral coefficient, mel-frequency cepstrum coefficients, MFCC',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    1980,
    NULL,
    'https://doi.org/10.1109/TASSP.1980.1163420',
    'Comparison of Parametric Representations for Monosyllabic Word Recognition in Continuously Spoken Sentences (Davis & Mermelstein, 1980)',
    'https://github.com/pytorch/audio/blob/main/src/torchaudio/transforms/_transforms.py',
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

-- Introduced banners for the four sourced methods.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN ('lion', 'kaiming-initialization', 'dora', 'adapter-tuning')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug IN ('lion', 'kaiming-initialization', 'dora', 'adapter-tuning')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed paper links (2026-11-10). Positives use, extend, analyze, survey or
-- compare against the method; reviewed negatives become durable exclusions so
-- the keyword and reference backfills do not re-link them.

-- lion: 24 links, 182 exclusions. Local Semantic Scholar citers of 2302.06675 (196 incl. source) plus title/abstract candidates; kept only papers whose title/abstract uses, extends, analyzes or compares Lion.
CREATE TEMP TABLE lion_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lion'
  AND p.id IN (
        13076, -- 2302.06675 Symbolic Discovery of Optimization Algorithms
        18203, -- 2307.06440 No Train No Gain: Revisiting Efficient Training Algorithms For Transformer-based
        21661, -- 2310.05898 Lion Secretly Solves Constrained Optimization: As Lyapunov Predicts
        21761, -- 2310.07147 QFT: Quantized Full-parameter Tuning of LLMs with Affordable Resources
        29700, -- 2404.00438 Communication Efficient Distributed Training with Distributed Lion
        40049, -- 2411.10438 MARS: Unleashing the Power of Variance Reduction for Training Large Models
        40404, -- 2411.16085 Cautious Optimizers: Improving Training with One Line of Code
        42060, -- 2412.17107 Grams: Gradient Descent with Adaptive Momentum Scaling
        44271, -- 2502.11034 AdaGC: Improving Training Stability for Large Language Model Pretraining
        53528, -- 2510.12402 Cautious Weight Decay
        58400, -- 2604.07663 SAGE: Sign-Adaptive Gradient for Memory-Efficient LLM Optimization
        60203, -- 2602.23349 FlashOptim: Optimizers for Memory Efficient Training
        68595, -- 2509.07252 GCond: Gradient Conflict Resolution via Accumulation-based Stabilization for Lar
        71791, -- 2506.18297 Comparative Analysis of Lion and AdamW Optimizers for Cross-Encoder Reranking wi
        86771, -- 2502.02132 How Memory in Optimization Algorithms Implicitly Modifies the Loss
        99633, -- 2508.12327 Convergence Analysis of the Lion Optimizer in Centralized and Distributed Settin
        101113, -- 2506.04192 Lions and Muons: Optimization via Stochastic Frank-Wolfe under Heavy-Tailed Nois
        101435, -- 2602.01105 OLion: Approaching the Hadamard Ideal by Intersecting Spectral and L inf Implici
        104458, -- 2607.19058 Where Should Optimizer State Live? Tiered State Allocation for Memory-Efficient
        124188, -- external Riemannian Lyapunov Framework: Optimization as Closed-Loop Control on Riemannian
        124533, -- 2602.05813 Where Does Warm-Up Come From? Adaptive Scheduling for Norm-Constrained Optimizer
        124789, -- 2602.07425 Sign-Based Optimizers Are Effective Under Heavy-Tailed Noise
        124885, -- 2605.11172 Optimistic Dual Averaging Unifies Modern Optimizers
        127859  -- 2605.09991 Optimizer-Induced Mode Connectivity: From AdamW to Muon
  );

DELETE FROM paper_method_exclusions x
USING lion_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM lion_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM lion_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE lion_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lion'
  AND p.id IN (
        13201, -- 2302.09738 Simplifying Momentum-based Positive-definite Submanifold Optimization with Appli
        13935, -- 2303.11331 EVA-02: A Visual Representation for Neon Genesis
        14181, -- 2303.15343 Sigmoid Loss for Language Image Pre-Training
        14709, -- 2304.07193 DINOv2: Learning Robust Visual Features without Supervision
        14957, -- 2304.13013 Stable and low-precision training for large-scale vision-language models
        15346, -- 2305.04961 Joint Moment Retrieval and Highlight Detection Via Natural Language Queries
        15498, -- 2305.07583 MoMo: Momentum Models for Adaptive Learning Rates
        15581, -- 2305.08854 Laughing Matters: Introducing Laughing-Face Generation using Diffusion Models
        15888, -- 2305.12870 Lion: Adversarial Distillation of Proprietary Large Language Models
        16073, -- 2305.14342 Sophia: A Scalable Stochastic Second-order Optimizer for Language Model Pre-trai
        16162, -- 2305.14890 HARD: Hard Augmentations for Robust Distillation
        16488, -- 2305.18240 XGrad: Boosting Gradient-Based Optimizers With Weight Prediction
        16719, -- 2306.00204 Toward Understanding Why Adam Converges Faster Than SGD for Transformers
        16821, -- 2306.01129 White-Box Transformers via Sparse Rate Reduction
        16883, -- 2306.01762 Rapid Plug-in Defenders
        17089, -- 2306.04226 Normalization Layers Are All That Sharpness-Aware Minimization Needs
        17364, -- 2306.07879 Rethinking pose estimation in crowds: overcoming the detection information-bottl
        17717, -- 2306.13575 Scaling MLPs: A Tale of Inductive Bias
        19502, -- 2308.10204 ChatEDA: A Large Language Model Powered Autonomous Agent for EDA
        19505, -- 2308.10252 LMTuner: An user-friendly and highly-integrable Training Framework for fine-tuni
        19953, -- 2308.16271 Emergence of Segmentation with Minimalistic White-Box Transformers
        20095, -- 2309.01859 NLLB-CLIP -- train performant multilingual image retrieval model on a budget
        20124, -- 2309.02373 nanoT5: A PyTorch Framework for Pre-training and Fine-tuning T5-style Models wit
        21001, -- 2309.16064 Masked Autoencoders are Scalable Learners of Cellular Morphology
        21181, -- 2310.00746 RoleLLM: Benchmarking, Eliciting, and Enhancing Role-Playing Abilities of Large
        21457, -- 2310.03646 TRAM: Bridging Trust Regions and Sharpness Aware Minimization
        21724, -- 2310.06694 Sheared LLaMA: Accelerating Language Model Pre-training via Structured Pruning
        22580, -- 2310.16992 How well can machine-generated texts be identified and can language models be tr
        23043, -- 2311.04163 Outliers with Opposing Signals Have an Outsized Effect on Neural Network Optimiz
        23311, -- 2311.08364 Plum: Prompt Learning using Metaheuristic
        23406, -- 2311.09402 Synthetically Enhanced: Unveiling Synthetic Data's Potential in Medical Imaging
        23646, -- 2311.13133 LIMIT: Less Is More for Instruction Tuning Across Evaluation Paradigms
        24094, -- 2312.00267 Sample Efficient Preference Alignment in LLMs via Active Exploration
        24110, -- 2312.00407 CoLLiE: Collaborative Training of Large Language Models in an Efficient Way
        24237, -- 2312.02147 Rejuvenating image-GPT as Strong Visual Representation Learners
        24352, -- 2312.03511 Kandinsky 3.0 Technical Report
        24743, -- 2312.08472 AutoNumerics-Zero: Automated Discovery of State-of-the-Art Mathematical Function
        24889, -- 2312.10523 Paloma: A Benchmark for Evaluating Language Model Fit
        25010, -- 2312.12487 Adaptive Guidance: Training-free Acceleration of Conditional Diffusion Models
        25462, -- 2401.02020 Spikformer V2: Join the High Accuracy Club on ImageNet with an SNN Ticket
        26020, -- 2401.10402 Reconstructing the Invisible: Video Frame Restoration through Siamese Masked Con
        30405, -- 2404.10242 Masked Autoencoders for Microscopy are Scalable Learners of Cellular Biology
        30726, -- 2404.15653 CatLIP: CLIP-level Visual Recognition Accuracy with 2.7x Faster Pre-training on
        31170, -- 2405.05847 Learned feature representations are biased by complexity, learning order, positi
        31598, -- 2405.14578 Surge Phenomenon in Optimal Learning Rate and Batch Size Scaling
        31760, -- 2405.16397 AdaFisher: Adaptive Second Order Optimization via Fisher Information
        32112, -- 2405.20541 Perplexed by Perplexity: Perplexity-Based Data Pruning With Small Reference Mode
        32185, -- 2406.00505 Improving Text Generation on Images with Synthetic Captions
        32381, -- 2406.03476 Does your data spark joy? Performance gains from domain upsampling at the end of
        32803, -- 2406.08414 Discovering Preference Optimization Algorithms with and for Large Language Model
        33601, -- 2406.16793 Adam-mini: Use Fewer Learning Rates To Gain More
        35784, -- 2408.06697 SlotLifter: Slot-guided Feature Lifting for Learning Object-centric Radiance Fie
        36166, -- 2408.12857 Memory-Efficient LLM Training with Online Subspace Descent
        36598, -- 2409.03137 The AdEMAMix Optimizer: Better, Faster, Older
        36998, -- 2409.11321 SOAP: Improving and Stabilizing Shampoo using Adam
        37545, -- 2409.20325 Old Optimizer, New Norm: An Anthology
        38078, -- 2410.05871 A second-order-like optimizer with adaptive gradient scaling for deep learning
        38117, -- 2410.06373 Unveiling the Backbone-Optimizer Coupling Bias in Visual Representation Learning
        39172, -- 2410.19313 COAT: Compressing Optimizer states and Activation for Memory-Efficient FP8 Train
        39413, -- 2410.23332 MoLE: Enhancing Human-centric Text-to-image Diffusion via Mixture of Low-rank Ex
        39929, -- 2411.07837 FRUGAL: Memory-Efficient Optimization by Reducing State Overhead for Scalable Tr
        40011, -- 2411.09678 NeuralDEM - Real-time Simulation of Industrial Particulate Flows
        40719, -- 2411.19870 DeMo: Decoupled Momentum Optimization
        41099, -- 2412.04616 Assessing and Learning Alignment of Unimodal Vision and Language Models
        43044, -- 2501.11847 A Survey on Memory-Efficient Large-Scale Model Training in AI for Science
        43898, -- 2502.05967 $μ$nit Scaling: Simple and Scalable FP8 LLM Training
        44780, -- 2502.15757 TLOB: A Novel Transformer Model with Dual Attention for Price Trend Prediction w
        44903, -- 2502.17055 Stable-SPAM: How to Train in 4-Bit More Stably than 16-Bit Adam
        44940, -- 2502.17410 COSMOS: A Hybrid Adaptive Optimizer for Memory-Efficient Training of LLMs
        45061, -- 2502.19002 The Sharpness Disparity Principle in Transformers for Accelerating Language Mode
        45367, -- 2503.01843 When Can You Get Away with Low Memory Adam?
        45809, -- 2503.07595 Detection Avoidance Techniques for Large Language Models
        47380, -- 2504.05295 Dion: Distributed Orthonormalized Updates
        48326, -- 2505.01043 Low-Precision Training of Large Language Models: Methods, Challenges, and Opport
        48381, -- 2505.02222 Practical Efficiency of Muon for Pretraining
        49923, -- 2505.21114 Differentiable Solver Search for Fast Diffusion Sampling
        50231, -- 2505.24452 Stepsize anything: A unified learning rate schedule for budgeted-iteration train
        50439, -- 2506.02281 Angles Don't Lie: Unlocking Training-Efficient RL Through the Model's Own Signal
        51136, -- 2506.13131 AlphaEvolve: A coding agent for scientific and algorithmic discovery
        51889, -- 2507.11005 AdaMuon: Adaptive Muon Optimizer
        53342, -- 2510.05491 NorMuon: Making Muon more efficient and scalable
        53870, -- 2510.21800 MARS-M: When Variance Reduction Meets Matrices
        54811, -- 2512.14697 Spherical Leech Quantization for Visual Tokenization and Generation
        55076, -- 2512.24695 Nested Learning: The Illusion of Deep Learning Architectures
        56211, -- 2602.16928 Discovering Multiagent Learning Algorithms with Large Language Models
        56807, -- 2603.16184 Polyglot-Lion: Efficient Multilingual ASR for Singapore via Balanced Fine-Tuning
        58097, -- 2604.16687 Agentic Risk-Aware Set-Based Engineering Design
        58136, -- 2604.15416 StoSignSGD: Unbiased Structural Stochasticity Fixes SignSGD for Training Large L
        58295, -- 2512.08217 Correction of Decoupled Weight Decay
        58347, -- 2604.09258 Nexus: Same Pretraining Loss, Better Downstream Generalization via Common Minima
        59791, -- 2603.06120 Dynamic Momentum Recalibration in Online Gradient Learning
        60201, -- 2602.23353 SOTAlign: Semi-Supervised Alignment of Unimodal Vision and Language Models via O
        60202, -- 2602.23413 EvoX: Meta-Evolution for Automated Discovery
        60362, -- 2602.20133 AdaEvolve: Adaptive LLM Driven Zeroth-Order Optimization
        60511, -- 2602.16918 Xray-Visual Models: Scaling Vision models on Industry Scale Data
        60611, -- 2602.14697 Evolutionary System Prompt Learning for Reinforcement Learning in LLMs
        60883, -- 2602.10300 Configuration-to-Performance Scaling Law with Neural Ansatz
        60885, -- 2602.10226 Self-Evolving Recommendation System: End-To-End Autonomous Model Optimization Wi
        61692, -- 2601.23000 Mano: Restriking Manifold Optimization for LLM Training
        61764, -- 2601.22284 Riemannian Lyapunov Optimizer: A Unified Framework for Optimization
        62123, -- 2601.17126 EveNet: A Foundation Model for Particle Collision Data Analysis
        62136, -- 2601.16736 A Step to Decouple Optimization in 3DGS
        62263, -- 2601.14603 Variance-Adaptive Muon: Accelerating LLM Pretraining with NSR-Modulated and Vari
        64089, -- 2512.11853 Evolving Deep Learning Optimizers
        64468, -- 2511.21474 Going with the Speed of Sound: Pushing Neural Surrogates into Highly-turbulent T
        65222, -- 2511.07308 Can Training Dynamics of Scale-Invariant Neural Networks Be Explained by the The
        65711, -- 2510.25000 What Really Matters in Matrix-Whitening Optimizers?
        66350, -- 2510.14009 Noise-Adaptive Layerwise Learning Rates: Accelerating Geometry-Aware Optimizatio
        66555, -- 2510.10603 EA4LLM: A Gradient-Free Approach to Large Language Model Optimization via Evolut
        66911, -- 2510.05361 MT-DAO: Multi-Timescale Distributed Adaptive Optimizers with Local Updates
        66928, -- 2510.04988 Adaptive Memory Momentum via a Model-Based Framework for Deep Learning Optimizat
        67506, -- 2509.24218 Conda: Column-Normalized Adam for Training Large Language Models Faster
        69192, -- 2508.18258 ANO : Faster is Better in Noisy Landscape
        72572, -- 2505.22549 DES-LOC: Desynced Low Communication Adaptive Optimizers for Training Foundation
        72900, -- 2505.15255 Boosting Large Language Models for Mental Manipulation Detection via Data Augmen
        74624, -- 2502.12485 Safe at the Margins: A General Approach to Safety Alignment in Low-Resource Engl
        74711, -- 2502.09692 AB-UPT: Scaling Neural CFD Surrogates for High-Fidelity Automotive Aerodynamics
        74763, -- 2502.06742 Gradient Multi-Normalization for Stateless and Scalable LLM Training
        75438, -- 2412.13148 SWAN: SGD with Normalization and Whitening Enables Stateless LLM Training
        75866, -- 2411.02572 ViTally Consistent: Scaling Biological Representation Learning for Cell Microsco
        75919, -- 2410.22421 Point cloud-based diffusion models for the Electron-Ion Collider
        77161, -- 2405.19550 Stress-Testing Capability Elicitation With Password-Locked Models
        78248, -- 2311.08850 Controlling the Output of a Generative Model by Latent Feature Vector Shifting
        83317, -- 2605.10302 Follow the Mean: Reference-Guided Flow Matching
        83614, -- 2605.21803 Same Architecture, Different Capacity: Optimizer-Induced Spectral Scaling Laws
        84308, -- 2512.01738 MSPT: Efficient Large-Scale Physical Modeling via Parallelized Multi-Scale Atten
        85398, -- 2604.16388 Visual-RRT: Finding Paths toward Visual-Goals via Differentiable Rendering
        85957, -- 2505.24749 SUMO: Subspace-Aware Moment-Orthogonalization for Accelerating Memory-Efficient
        86119, -- 2504.15827 DualOptim: Enhancing Efficacy and Stability in Machine Unlearning with Dual Opti
        87290, -- 2509.16875 Towards Interpretable and Efficient Attention: Compressing All by Contracting a
        88722, -- 2402.02342 MetaOptimize: A Framework for Optimizing Step Sizes and Other Meta-parameters
        88783, -- 2502.17066 DUNIA: Pixel-Sized Embeddings via Cross-Modal Alignment for Earth Observation Ap
        89714, -- 2405.13698 How to set AdamW's weight decay as you scale model and dataset size
        89717, -- 2506.03790 Attention-Only Transformers via Unrolled Subspace Denoising
        90012, -- 2406.09570 Improving Consistency Models with Generator-Augmented Flows
        90123, -- 2407.07052 Latent Space Imaging
        91046, -- 2410.20625 LoRA Done RITE: Robust Invariant Transformation Equilibration for LoRA Optimizat
        91174, -- 2407.05649 Greener GRASS: Enhancing GNNs with Encoding, Rewiring, and Attention
        91563, -- 2402.05913 Efficient stagewise pretraining via progressive subnetworks
        92255, -- 2311.05589 A Coefficient Makes SVRG Effective
        92749, -- 2511.20584 A Tale of Two Geometries: Adaptive Optimizers and Non-Euclidean Descent
        92860, -- 2505.13196 A Physics-Inspired Optimizer: Velocity Regularized Adam
        93047, -- 2510.19093 Weight Decay may matter more than µP for Learning Rate Transfer in Practice
        93071, -- 2505.05589 ReactDance: Hierarchical Representation for High-Fidelity and Coherent Long-Form
        93196, -- 2510.00922 On Discovering Algorithms for Adversarial Imitation Learning
        93233, -- 2602.16642 Optimizer Choice Matters For The Emergence of Neural Collapse
        93282, -- 2505.16030 Locally Subspace-Informed Neural Operators for Efficient Multiscale PDE Solving
        94017, -- 2602.22689 No Caption, No Problem: Caption-Free Membership Inference via Model-Fitted Embed
        94098, -- 2509.23249 Deep Learning for Subspace Regression
        94256, -- 2507.17501 DNT: a Deeply Normalized Transformer that can be trained by Momentum SGD
        94865, -- 2509.18993 CR-Net: Scaling Parameter-Efficient Training with Cross-Layer Low-Rank Structure
        95699, -- external Tuning Hydrodynamic Coefficients Using a Genetic Algorithm for a Numerical Model
        96343, -- 2509.20681 Efficient Construction of Implicit Surface Models from a Single Image for Motion
        98213, -- 2606.11854 Fine-tuning Multi-modal LLMs with ART: Art-based Reinforcement Training
        98980, -- 2606.30634 One-Step Gradient Delay is Not a Barrier for Large-Scale Asynchronous Pipeline P
        99139, -- 2506.17768 Log-Normal Multiplicative Dynamics for Stable Low-Precision Deep Learning
        99212, -- 2512.14366 Optimizing Rank for High-Fidelity Implicit Neural Representations
        99228, -- 2512.10401 Diffusion Differentiable Resampling
        99418, -- 2602.04940 Transolver-3: Scaling Up Transformer Solvers to Industrial-Scale Geometries
        99660, -- 2605.15403 $\phi$-Balancing for Mixture-of-Experts Training
        100397, -- 2505.24275 GradPower: Powering Gradients for Faster Language Model Pre-Training
        100528, -- 2602.11208 Adaptive Physics Transformer with Fused Global-Local Attention for Subsurface En
        101125, -- 2605.18004 RL4RLA: Teaching ML to Discover Randomized Linear Algebra Algorithms Through Cur
        101242, -- 2602.06880 Decoupling Variance and Scale-Invariant Updates in Adaptive Gradient Descent for
        101481, -- 2509.14562 LiMuon: Light and Fast Muon Optimizer for Large Models
        102697, -- 2311.05709 OmniVec: Learning robust representations with cross modal sharing
        109052, -- 2608.05136 The Loss Does Not See the Basis, but Adam Does
        113599, -- 2409.10542 SAM4MLLM: Enhance Multi-Modal Large Language Model for Referring Expression Segm
        115572, -- 2403.07684 Genuine Knowledge from Practice: Diffusion Test-Time Adaptation for Video Advers
        116700, -- 2404.01925 Improving Bird's Eye View Semantic Segmentation by Task Decomposition
        122137, -- 2609.26457 Recursive self-improvement of AI research agents
        122743, -- 2610.06577 Optimizing the Optimizer: Language Models Discover Faster Molecular Relaxation
        123250, -- 2610.16533 Spectral-Driven Adaptive-Rank Optimizer for Large Language Model Reinforcement L
        124368, -- 2605.06615 When and Why SignSGD Outperforms SGD: A Theoretical Study Based on $\ell_1$-norm
        124496, -- 2602.09530 Learning to Discover Iterative Spectral Algorithms
        127110, -- 2606.19179 Compute Efficiency and Serial Runtime Tradeoffs for Stochastic Momentum Methods
        128613, -- 2605.08843 M$^3$: Reframing Training Measures for Discretized Physical Simulations
        129030, -- 2605.11850 Constrained Stochastic Spectral Preconditioning Converges for Nonconvex Objectiv
        129203, -- 2512.06370 Greedy Alignment Principle for Optimizer Selection
        129675, -- 2602.19931 Expanding the Role of Diffusion Models for Robust Classifier Training
        131876, -- 2610.41104 MUON-RT Reusing the Teacher's Trajectory for Momentum-Free Muon for LLM Self-Dis
        131970  -- external Lion-ER: LionRock Embodied Reasoner
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the Lion paper without naming the optimizer, names it only in passing, or Lion names something else (SEA-Lion, Lion distillation)'
FROM lion_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING lion_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING lion_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- dora: 27 links, 398 exclusions. Local Semantic Scholar citers of 2402.09353 (406 incl. source) plus title/abstract candidates; kept only papers whose title/abstract uses, extends or compares DoRA.
CREATE TEMP TABLE dora_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dora'
  AND p.id IN (
        27323, -- 2402.09353 DoRA: Weight-Decomposed Low-Rank Adaptation
        31693, -- 2405.15525 Sparse Matrix in Large Language Model Fine-tuning
        38375, -- 2410.09692 ALLoRA: Adaptive Learning Rate Mitigates LoRA Fatal Flaws
        39868, -- 2411.06971 MapSAM: Adapting Segment Anything Model for Automated Feature Detection in Histo
        40512, -- 2411.17426 CLOVER: Cross-Layer Orthogonal Vectors Pruning and Fine-Tuning
        41229, -- 2412.06441 BoRA: Bi-dimensional Weight-Decomposed Low-Rank Adaptation
        42299, -- 2412.20891 DoTA: Weight-Decomposed Tensor Adaptation for Large Language Models
        42606, -- 2501.04315 RoRA: Efficient Fine-Tuning of LLM with Reliability Optimization for Rank Adapta
        42870, -- 2501.08727 Transformed Low-rank Adaptation via Tensor Decomposition and Its Applications to
        43055, -- 2501.12067 EDoRA: Efficient Weight-Decomposed Low-Rank Adaptation via Singular Value Decomp
        49098, -- 2505.13840 EfficientLLM: Efficiency in Large Language Models
        51362, -- 2506.18267 ARD-LoRA: Dynamic Rank Allocation for Parameter-Efficient Fine-Tuning of Foundat
        51533, -- 2506.21594 Gazal-R1: Achieving State-of-the-Art Medical Reasoning with Parameter-Efficient
        51738, -- 2507.05566 SingLoRA: Low Rank Adaptation Using a Single Matrix
        55038, -- 2512.23165 Evaluating Parameter Efficient Methods for RLVR
        56942, -- 2603.22276 Scaling DoRA: High-Rank Adaptation via Factored Norms and Fused Kernels
        57633, -- 2604.19254 ShadowPEFT: Shadow Network for Parameter-Efficient Fine-Tuning
        68313, -- 2509.13240 Don't Forget the Nonlinearity: Unlocking Activation Functions in Efficient Fine-
        70328, -- 2508.01772 LoRA-based methods on Unet for transfer learning in Subarachnoid Hematoma Segmen
        72557, -- 2505.23094 MAP: Revisiting Weight Decomposition for Low-Rank Adaptation
        73554, -- 2504.09223 DL-QAT: Weight-Decomposed Low-Rank Quantization-Aware Training for Large Languag
        106580, -- 2511.00051 Calibrating and Rotating: A Unified Framework for Weight Conditioning in PEFT
        108775, -- 2605.09015 LLiMba: Sardinian on a Single GPU -- Adapting a 3B Language Model to a Vanishing
        110364, -- external DisLoRA: Task-specific Low-Rank Adaptation via Orthogonal Basis from Singular Va
        126452, -- 2607.02576 CORA: Per-Slice Coherent Orthogonal Rotation for SVD-based Low-Rank Adaptation
        129666, -- 2602.05339 Consistency-Preserving Concept Erasure via Unsafe–Safe Pairing and Directional F
        131192  -- external Where You Backpropagate Matters: Token Hypothesis for Memory-Efficient Fine-Tuni
  );

DELETE FROM paper_method_exclusions x
USING dora_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dora_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM dora_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE dora_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dora'
  AND p.id IN (
        18988, -- 2308.03303 LoRA-FA: Memory-efficient Low-rank Adaptation for Large Language Models Fine-tun
        21911, -- 2310.08584 Is ImageNet worth 1 video? Learning strong image encoders from 1 long unlabelled
        23650, -- 2311.13171 ComPEFT: Compression for Communicating Parameter Efficient Updates via Sparsific
        24373, -- 2312.03694 Parameter-Efficient Transfer Learning of Audio Spectrogram Transformers
        27018, -- 2402.05147 ApiQ: Finetuning of 2-Bit Quantized Large Language Model
        28647, -- 2403.06407 Can LLMs' Tuning Methods Work in Medical Multimodal Domain?
        28948, -- 2403.10704 Parameter Efficient Reinforcement Learning from Human Feedback
        29184, -- 2403.13372 LlamaFactory: Unified Efficient Fine-Tuning of 100+ Language Models
        29276, -- 2403.14608 Parameter-Efficient Fine-Tuning for Large Models: A Comprehensive Survey
        29909, -- 2404.02948 PiSSA: Principal Singular Values and Singular Vectors Adaptation of Large Langua
        29949, -- 2404.03592 ReFT: Representation Finetuning for Language Models
        30140, -- 2404.06369 WebCode2M: A Real-World Dataset for Code Generation from Webpage Designs
        30249, -- 2404.07979 LLoCO: Learning Long Contexts Offline
        30328, -- 2404.09027 MING-MOE: Enhancing Medical Multi-Task Learning in Large Language Models with Sp
        30626, -- 2404.13752 Adversarial Representation Engineering: A General Model Editing Framework for La
        30676, -- 2404.14619 OpenELM: An Efficient Language Model Family with Open Training and Inference Fra
        30701, -- 2404.15159 MixLoRA: Enhancing Large Language Models Fine-Tuning with LoRA-based Mixture of
        31018, -- 2405.01483 MANTIS: Interleaved Multi-Image Instruction Tuning
        31051, -- 2405.02246 What matters when building vision-language models?
        31256, -- 2405.07913 CTRLorALTer: Conditional LoRAdapter for Efficient 0-Shot Control & Altering of T
        31331, -- 2405.09673 LoRA Learns Less and Forgets Less
        31427, -- 2405.11804 (Perhaps) Beyond Human Translation: Harnessing Multi-Agent Collaboration for Tra
        31443, -- 2405.12130 MoRA: High-Rank Updating for Parameter-Efficient Fine-Tuning
        31500, -- 2405.13155 ReALLM: A general framework for LLM compression and fine-tuning
        31578, -- 2405.14366 MiniCache: KV Cache Compression in Depth Dimension for Large Language Models
        31583, -- 2405.14438 LoRA-Ensemble: Efficient Uncertainty Modelling for Self-attention Networks
        31612, -- 2405.14739 FLoRA: Low-Rank Core Space for N-dimension
        31633, -- 2405.14862 Bitune: Bidirectional Instruction-Tuning
        31648, -- 2405.15007 RE-Adapt: Reverse Engineered Adaptation of Large Language Models
        31837, -- 2405.17357 DoRA: Enhancing Parameter-Efficient Fine-Tuning with Dynamic Rank Distribution
        31857, -- 2405.17484 Bridging The Gap between Low-rank and Orthogonal Adaptation via Householder Refl
        31863, -- 2405.17604 LoRA-XS: Low-Rank Adaptation with Extremely Small Number of Parameters
        31938, -- 2405.18380 OwLore: Outlier-weighed Layerwise Sampled Low-Rank Projection for Memory-Efficie
        31959, -- 2405.18572 Low-rank finetuning for LLMs: A fairness perspective
        32017, -- 2405.19458 MemControl: Mitigating Memorization in Diffusion Models via Automated Parameter
        32096, -- 2405.20339 Visual Perception by Large Language Model's Weights
        32159, -- 2406.00132 QuanTA: Efficient High-Rank Fine-Tuning of LLMs with Quantum-Informed Tensor Ada
        32286, -- 2406.02214 SLTrain: a sparse plus low-rank approach for parameter and memory efficient pret
        32362, -- 2406.03136 Computational Limits of Low-Rank Adaptation (LoRA) Fine-Tuning for Transformer M
        32368, -- 2406.03216 Choice of PEFT Technique in Continual Learning: Prompt Tuning is Not All You Nee
        32527, -- 2406.05223 CorDA: Context-Oriented Decomposition Adaptation of Large Language Models for Ta
        32581, -- 2406.05885 Are Large Language Models Actually Good at Text Style Transfer?
        33017, -- 2406.10777 RoseLoRA: Row and Column-wise Sparse Low-rank Adaptation of Pre-trained Language
        33176, -- 2406.11909 Mixture-of-Subspaces in Low-Rank Adaptation
        33285, -- 2406.12832 LaMDA: Large Model Fine-Tuning via Spectrally Decomposed Low-Dimensional Adaptat
        33308, -- 2406.13175 Sparse High Rank Adapters
        33655, -- 2406.17484 MedCare: Advancing Medical LLMs through Decoupling Clinical Alignment and Knowle
        33676, -- 2406.17740 Structured Unrestricted-Rank Matrices for Parameter Efficient Fine-tuning
        33714, -- 2406.18120 ArzEn-LLM: Code-Switched Egyptian Arabic-English Translation and Speech Recognit
        34004, -- 2407.01920 To Forget or Not? Towards Practical Knowledge Unlearning for Large Language Mode
        34032, -- 2407.02211 PromptIntern: Saving Inference Costs by Internalizing Recurrent Prompt during La
        34455, -- 2407.08044 RoLoRA: Fine-tuning Rotated Outlier-free LLMs for Effective Weight-Activation Qu
        34456, -- 2407.08056 Pareto Low-Rank Adapters: Efficient Multi-Task Learning with Preferences
        34473, -- 2407.08296 Q-GaLore: Quantized GaLore with INT4 Projection and Layer-Adaptive Low-Rank Grad
        34505, -- 2407.08674 Still-Moving: Customized Video Generation without Customized Video Data
        35128, -- 2407.16724 Structure-aware Domain Knowledge Injection for Large Language Models
        35211, -- 2407.18242 LoRA-Pro: Are Low-Rank Adapters Properly Optimized?
        35262, -- 2407.19342 Parameter-Efficient Fine-Tuning via Circular Convolution
        35275, -- 2407.19580 Mini-batch Coresets for Memory-efficient Training of Large Language Models
        35588, -- 2408.03092 Extend Model Merging from Fine-Tuned to Pre-Trained Large Language Models via We
        35667, -- 2408.04556 BA-LoRA: Bias-Alleviating Low-Rank Adaptation to Mitigate Catastrophic Inheritan
        35776, -- 2408.06621 Towards Robust and Parameter-Efficient Knowledge Unlearning for LLMs
        35986, -- 2408.10280 NoRA: Nested Low-Rank Adaptation for Efficient Fine-Tuning Large Models
        36154, -- 2408.12637 Building and better understanding vision-language models: insights and future di
        36245, -- 2408.14471 A Practitioner's Guide to Continual Multimodal Pretraining
        36333, -- 2408.15915 Leveraging Open Knowledge for Advancing Task Expertise in Large Language Models
        36424, -- 2409.00055 SORSA: Singular Values and Orthonormal Regularized Singular Vectors Adaptation o
        36431, -- 2409.00119 3-in-1: 2D Rotary Adaptation for Efficient Finetuning, Efficient Batching and Co
        36591, -- 2409.02958 Multi-Modal Adapter for Vision-Language Models
        36648, -- 2409.04206 Fast Forwarding Low-Rank Training
        36700, -- 2409.05732 Towards Democratizing Multilingual Large Language Models For Medicine Through A
        37208, -- 2409.14924 Retrieval Augmented Generation (RAG) and Beyond: A Comprehensive Survey on How t
        37237, -- 2409.15371 Balancing LoRA Performance and Efficiency with Simple Shard Sharing
        37311, -- 2409.16722 PMSS: Pretrained Matrices Skeleton Selection for LLM Fine-tuning
        37649, -- 2410.01463 Selective Aggregation for Low-Rank Adaptation in Federated Learning
        37854, -- 2410.03190 Tuning Timestep-Distilled Diffusion Model Using Pairwise Sample Optimization
        38116, -- 2410.06364 SpaLLM: Unified Compressive Adaptation of Large Language Models with Sketching
        38327, -- 2410.09016 Parameter-Efficient Fine-Tuning of State Space Models
        38361, -- 2410.09437 MTL-LoRA: Low-Rank Adaptation for Multi-Task Learning
        38432, -- 2410.10450 KBLaM: Knowledge Base augmented Language Model
        38454, -- 2410.10739 Balancing Continuous Pre-Training and Instruction Fine-Tuning: Optimizing Instru
        38510, -- 2410.11160 MANet: Fine-Tuning Segment Anything Model for Multimodal Remote Sensing Semantic
        38553, -- 2410.11772 Layer-wise Importance Matters: Less Memory for Better Performance in Parameter-e
        38718, -- 2410.13618 LoLDU: Low-Rank Adaptation via Lower-Diag-Upper Decomposition for Parameter-Effi
        38991, -- 2410.16926 Pyramid Vector Quantization for LLMs
        39037, -- 2410.17599 Cross-model Control: Improving Multiple Large Language Models in One-time Traini
        39062, -- 2410.18035 MiLoRA: Efficient Mixture of Low-Rank Adaptation for Large Language Models Fine-
        39257, -- 2410.20777 KD-LoRA: A Hybrid Approach to Efficient Fine-Tuning with LoRA and Knowledge Dist
        39281, -- 2410.21228 LoRA vs Full Fine-tuning: An Illusion of Equivalence
        39816, -- 2411.05877 Generative Adapter: Contextualizing Language Models in Parameters with A Single
        39929, -- 2411.07837 FRUGAL: Memory-Efficient Optimization by Reducing State Overhead for Scalable Tr
        40000, -- 2411.09289 StreamAdapter: Efficient Test Time Adaptation from Contextual Streams
        40006, -- 2411.09539 A Practical Guide to Fine-tuning Language Models with Limited Data
        40231, -- 2411.13676 Hymba: A Hybrid-head Architecture for Small Language Models
        40694, -- 2411.19557 Initialization using Update Approximation is a Silver Bullet for Extremely Effic
        40729, -- 2412.00071 COAP: Memory-Efficient Training with Correlation-Aware Gradient Projection
        41032, -- 2412.04077 SoRA: Singular Value Decomposed Low-Rank Adaptation for Domain Generalizable Rep
        41085, -- 2412.04468 NVILA: Efficient Frontier Visual Language Models
        41206, -- 2412.06071 KaSA: Knowledge-Aware Singular-Value Adaptation of Large Language Models
        41221, -- 2412.06289 S$^{2}$FT: Efficient, Scalable and Generalizable LLM Fine-tuning by Structured S
        41339, -- 2412.07771 PETALface: Parameter Efficient Transfer Learning for Low-resolution Face Recogni
        41872, -- 2412.14426 All-in-One Tuning and Structural Pruning for Domain-Specific LLMs
        42169, -- 2412.18487 Segment-Based Attention Masking for GPTs
        42251, -- 2412.19820 GaLore$+$: Boosting Low-Rank Adaptation for LLMs with Cross-Head Projection
        42349, -- 2501.00365 Low-Rank Adaptation for Foundation Models: A Comprehensive Review
        42450, -- 2501.01765 SaLoRA: Safety-Alignment Preserved Low-Rank Adaptation
        42572, -- 2501.03829 Spectral-Aware Low-Rank Adaptation for Speaker Verification
        42770, -- 2501.06892 Language Fusion for Parameter-Efficient Cross-lingual Transfer
        42786, -- 2501.07237 Breaking Memory Limits: Gradient Wavelet Transform Enhances LLMs Training
        43031, -- 2501.11587 Recurrent Diffusion for Large-Scale Parameter Generation
        43162, -- 2501.13787 Parameter-Efficient Fine-Tuning for Foundation Models
        43194, -- 2501.14315 Mitigating Forgetting in LLM Fine-Tuning via Low-Perplexity Token Learning
        43252, -- 2501.15377 Fine Tuning without Catastrophic Forgetting via Selective Low Rank Adaptation
        43383, -- 2501.17823 U2A: Unified Unimodal Adaptation for Robust and Efficient Multimodal Learning
        43418, -- 2501.18475 CLoQ: Enhancing Fine-Tuning of Quantized LLMs via Calibrated LoRA Initialization
        43531, -- 2502.00987 RandLoRA: Full-rank parameter-efficient fine-tuning of large models
        43967, -- 2502.06820 LoCA: Location-Aware Cosine Adaptation for Parameter-Efficient Fine-Tuning
        44126, -- 2502.08905 DiffoRA: Enabling Parameter-Efficient LLM Fine-Tuning via Differential Low-Rank
        44432, -- 2502.12171 GoRA: Gradient-driven Adaptive Low Rank Adaptation
        44564, -- 2502.13533 Train Small, Infer Large: Memory-Efficient LoRA Training for Large Language Mode
        44762, -- 2502.15436 Fed-SB: A Silver Bullet for Extreme Communication Efficiency and Performance in
        44915, -- 2502.17159 Parameter Efficient Merging for Multimodal Large Language Models with Complement
        44986, -- 2502.18017 ViDoRAG: Visual Document Retrieval-Augmented Generation via Dynamic Iterative Re
        44990, -- 2502.18101 Detecting Offensive Memes with Social Biases in Singapore Context Using Multimod
        45547, -- 2503.04543 Keeping Yourself is Important in Downstream Tuning Multimodal Large Language Mod
        46396, -- 2503.15438 VenusFactory: A Unified Platform for Protein Engineering Data Retrieval and Lang
        46527, -- 2503.16944 HyperLoRA: Parameter-Efficient Adaptive Generation for Portrait Synthesis
        46615, -- 2503.18225 DeLoRA: Decoupling Angles and Strength in Low-rank Adaptation
        47109, -- 2504.00661 DynMoLE: Boosting Mixture of LoRA Experts Fine-Tuning with a Hybrid Routing Mech
        47200, -- 2504.02122 Overcoming Vocabulary Constraints with Pixel-level Fallback
        47395, -- 2504.05523 Pretraining Language Models for Diachronic Linguistic Change Discovery
        47485, -- 2504.07448 LoRI: Reducing Cross-Task Interference in Multi-Task Low-Rank Adaptation
        47812, -- 2504.12397 Activated LoRA: Fine-tuned LLMs for Intrinsics
        48132, -- 2504.18147 NoEsis: Differentially Private Knowledge Transfer in Modular LLM Adaptation
        48148, -- 2504.18580 Parameter-Efficient Checkpoint Merging via Metrics-Weighted Averaging
        48236, -- 2504.20859 X-Cross: Dynamic Integration of Language Models for Cross-Domain Sequential Reco
        48433, -- 2505.03097 Not All Parameters Matter: Masking Diffusion Models for Enhancing Generation Abi
        48575, -- 2505.06176 MonetGPT: Solving Puzzles Enhances MLLMs' Image Retouching Skills
        48999, -- 2505.12805 FedSVD: Adaptive Orthogonalization for Private Federated Learning with LoRA
        49143, -- 2505.14238 ABBA: Highly Expressive Hadamard Product Adaptation for Large Language Models
        49388, -- 2505.16270 Transformer Copilot: Learning from The Mistake Log in LLM Fine-tuning
        49778, -- 2505.19819 FinLoRA: Benchmarking LoRA Methods for Fine-Tuning LLMs on Financial Datasets
        49906, -- 2505.20809 Improved Representation Steering for Language Models
        49933, -- 2505.21289 LoFT: Low-Rank Adaptation That Behaves Like Full Fine-Tuning
        50167, -- 2505.23808 DenseLoRA: Dense Low-Rank Adaptation of Large Language Models
        50357, -- 2506.01049 Taming LLMs by Scaling Learning Rates with Gradient Grouping
        50433, -- 2506.02153 Small Language Models are the Future of Agentic AI
        50483, -- 2506.03077 StreamBP: Memory-Efficient Exact Backpropagation for Long Sequence Training of L
        50504, -- 2506.03230 DiaBlo: Diagonal Blocks Are Sufficient For Finetuning
        50513, -- 2506.03478 Facial Appearance Capture at Home with Patch-Level Reflectance Prior
        50774, -- 2506.07621 LoRMA: Low-Rank Multiplicative Adaptation for LLMs
        51090, -- 2506.12015 EMLoC: Emulator-based Memory-efficient Fine-tuning with LoRA Correction
        51212, -- 2506.14427 M3SD: Multi-modal, Multi-scenario and Multi-language Speaker Diarization Dataset
        51296, -- 2506.16406 Drag-and-Drop LLMs: Zero-Shot Prompt-to-Weights
        51298, -- 2506.16500 SparseLoRA: Accelerating LLM Fine-Tuning with Contextual Sparsity
        51351, -- 2506.17967 Adapting Vision-Language Models for Evaluating World Models
        51470, -- 2506.20629 PLoP: Precise LoRA Placement for Efficient Finetuning of Large Models
        51597, -- 2507.00029 LoRA-Mixer: Coordinate Modular LoRA Experts Through Serial Attention Routing
        51700, -- 2507.04487 LoSiA: Efficient High-Rank Fine-Tuning via Subnet Localization and Optimization
        51875, -- 2507.10524 Mixture-of-Recursions: Learning Dynamic Recursive Depths for Adaptive Token-Leve
        52903, -- 2509.17428 QWHA: Quantization-Aware Walsh-Hadamard Adaptation for Parameter-Efficient Fine-
        52916, -- 2509.17786 Accurate and Efficient Low-Rank Model Merging in Core Space
        52925, -- 2509.16415 StereoAdapter: Adapting Stereo Depth Estimation to Underwater Scenes
        52967, -- 2509.22075 COSPADI: Compressing LLMs via Calibration-Guided Sparse Dictionary Learning
        53452, -- 2510.11696 QeRL: Beyond Efficiency -- Quantization-enhanced Reinforcement Learning for LLMs
        54592, -- 2512.05110 ShadowDraw: From Any Object to Shadow-Drawing Compositional Art
        54677, -- 2512.04763 MemLoRA: Distilling Expert Adapters for On-Device Memory Systems
        55157, -- 2601.04890 Learnable Multipliers: Freeing the Scale of Language Model Matrix Layers
        55208, -- 2601.04823 DR-LoRA: Dynamic Rank LoRA for Mixture-of-Experts Adaptation
        55251, -- 2601.06788 Artificial Entanglement in the Fine-Tuning of Large Language Models
        55841, -- 2602.04998 Learning Rate Matters: Vanilla LoRA May Suffice for LLM Fine-tuning
        55884, -- 2602.06471 Revisiting the Shape Convention of Transformer Language Models
        55984, -- 2602.05085 Locas: Your Models are Principled Initializers of Locally-Supported Parametric M
        56354, -- 2602.22479 Efficient Continual Learning in Language Models via Thalamically Routed Cortical
        56621, -- 2603.10160 ReMix: Reinforcement routing for mixtures of LoRAs in LLM finetuning
        56692, -- 2603.08258 WaDi: Weight Direction-aware Distillation for One-step Image Synthesis
        56954, -- 2603.21884 Not All Layers Are Created Equal: Adaptive LoRA Ranks for Personalized Image Gen
        57588, -- 2604.16826 Crowded in B-Space: Calibrating Shared Directions for LoRA Merging
        57612, -- 2604.16943 MNAFT: modality neuron-aware fine-tuning of multimodal large language models for
        57869, -- 2604.23750 The Override Gap: A Magnitude Account of Knowledge Conflict Failure in Hypernetw
        58078, -- 2509.15974 BEFT: Bias-Efficient Fine-Tuning of Language Models in Low-Data Regimes
        58533, -- 2604.15351 Aletheia: Gradient-Guided Layer Selection for Efficient LoRA Fine-Tuning Across
        59202, -- 2603.17558 Zipper-LoRA: Dynamic Parameter Decoupling for Speech-LLM based Multilingual Spee
        59662, -- 2603.08647 Grow, Don't Overwrite: Fine-tuning Without Forgetting
        59769, -- 2603.06492 NOBLE: Accelerating Transformers with Nonlinear Low-Rank Branches
        59906, -- 2603.03964 BLOCK: An Open-Source Bi-Stage MLLM Character-to-Skin Pipeline for Minecraft
        60189, -- 2602.23802 EMO-R3: Reflective Reinforcement Learning for Emotional Reasoning in Multimodal
        60829, -- 2602.10993 LoRA-Squeeze: Simple and Effective Post-Tuning and In-Tuning Compression of LoRA
        60987, -- 2602.08550 GOT-Edit: Geometry-Aware Generic Object Tracking via Online Model Editing
        61161, -- 2602.05605 Shiva-DiT: Residual-Based Differentiable Top-k Selection for Efficient Diffusion
        61713, -- 2601.22708 A Unified Study of LoRA Variants: Taxonomy, Review, Codebase, and Empirical Eval
        61995, -- 2601.19089 EPAS: Efficient Training with Progressive Activation Sharing
        62312, -- 2601.13580 Neural Organ Transplantation (NOT): Checkpoint-Based Modular Adaptation for Tran
        62988, -- 2601.02273 TopoLoRA-SAM: Topology-Aware Parameter-Efficient Adaptation of Foundation Segmen
        63124, -- 2601.00566 Low Rank Comes with Low Security: Gradient Assembly Poisoning Attacks against Di
        63300, -- 2601.09718 StatLLaMA: Multi-Stage training for domain-optimized statistical large language
        63360, -- 2512.20920 RevFFN: Memory-Efficient Full-Parameter Fine-Tuning of Mixture-of-Experts LLMs w
        63574, -- 2512.16292 In-Context Probing for Membership Inference in Fine-Tuned Language Models
        63617, -- 2512.15233 Null-LoRA: Low-Rank Adaptation on Null Space
        63935, -- 2512.08524 Beyond Real Weights: Hypercomplex Representations for Stable Quantization
        63971, -- 2512.07703 PVeRA: Probabilistic Vector-Based Random Matrix Adaptation
        64532, -- 2511.20459 Generation, Evaluation, and Explanation of Novelists' Styles with Single-Token P
        64655, -- 2410.01870 PEANuT: Parameter-Efficient Adaptation with Weight-aware Neural Tweakers
        64705, -- 2511.17979 FeRA: Frequency-Energy Constrained Routing for Effective Diffusion Adaptation Fi
        64801, -- 2511.16069 ILoRA: Federated Learning with Low-Rank Adaptation for Heterogeneous Client Aggr
        65014, -- 2511.11315 LAET: A Layer-wise Adaptive Ensemble Tuning Framework for Pretrained Language Mo
        65509, -- 2511.01093 Continual Learning, Not Training: Online Adaptation For Agents
        65616, -- 2511.00101 Loquetier: A Virtualized Multi-LoRA Framework for Unified LLM Fine-tuning and Se
        65760, -- 2510.24037 Kernelized Sparse Fine-Tuning with Bi-level Parameter Competition for Vision Mod
        65786, -- 2510.23574 More Than Generation: Unifying Generation and Depth Estimation via Text-to-Image
        66030, -- 2510.19640 Latent Space Factorization in LoRA
        66578, -- 2510.15962 CTR-LoRA: Curvature-Aware and Trust-Region Guided Low-Rank Adaptation for Large
        66600, -- 2510.10071 ADEPT: Continual Pretraining via Adaptive Expansion and Dynamic Decoupled Tuning
        66701, -- 2510.08513 SliceFine: The Universal Winning-Slice Hypothesis for Pretrained Networks
        66711, -- 2510.08396 FlyLoRA: Boosting Task Decoupling and Parameter Efficiency via Implicit Rank-Wis
        67139, -- 2510.01622 LLM4Rec: Large Language Models for Multimodal Generative Recommendation with Cau
        67424, -- 2509.24979 Wan-Alpha: High-Quality Text-to-Video Generation with Alpha Channel
        67506, -- 2509.24218 Conda: Column-Normalized Adam for Training Large Language Models Faster
        67707, -- 2510.03255 SciTS: Scientific Time Series Understanding and Generation with LLMs
        68558, -- 2509.07945 One Model for All Tasks: Leveraging Efficient World Models in Multi-Task Plannin
        68579, -- 2509.07526 Competitive Audio-Language Models with Data-Efficient Single-Stage Training on P
        68670, -- 2509.05757 Hyperbolic Large Language Models
        69261, -- 2508.17337 DropLoRA: Sparse Low-Rank Adaptation for Parameter-Efficient Fine-Tuning
        70055, -- 2508.10922 A Survey on Video Temporal Grounding with Multimodal Large Language Model
        70076, -- 2508.05232 Cross-LoRA: A Data-Free LoRA Transfer Framework across Heterogeneous LLMs
        70189, -- 2508.03527 MoKA: Mixture of Kronecker Adapters
        70252, -- 2508.02668 LOST: Low-rank and Sparse Pre-training for Large Language Models
        70445, -- 2508.00230 Towards Higher Effective Rank in Parameter-efficient Fine-tuning using Khatri--R
        71317, -- 2507.06558 The Primacy of Magnitude in Low-Rank Adaptation
        71402, -- 2507.04453 ESSA: Evolutionary Strategies for Scalable Alignment
        71412, -- 2507.04221 Context Tuning for In-Context Optimization
        71784, -- 2506.18493 ShowFlow: From Robust Single Concept to Condition-Free Multi-Concept Generation
        71860, -- 2506.16506 Subspace-Boosted Model Merging
        72180, -- 2506.06844 Adapt Once, Thrive with Updates: Transferable Parameter-Efficient Fine-Tuning on
        72314, -- 2506.03133 PoLAR: Polar-Decomposed Low-Rank Adapter Representation
        72325, -- 2506.02961 FlowerTune: A Cross-Domain Benchmark for Federated Fine-Tuning of Large Language
        72373, -- 2506.01935 Low-Rank Head Avatar Personalization with Registers
        72524, -- 2506.15702 Minifinetuning: Low-Data Generation Domain Adaptation through Corrective Self-Di
        72591, -- 2505.22120 LoKI: Low-damage Knowledge Implanting of Large Language Models
        72881, -- 2505.15875 Decouple and Orthogonalize: A Data-Free Framework for LoRA Merging
        72982, -- 2505.12532 Exploring Sparsity for Parameter Efficient Fine Tuning Using Wavelets
        72988, -- 2505.12455 AltLoRA: Towards Better Gradient Approximation in Low-Rank Adaptation with Alter
        73004, -- 2505.11998 Parameter Efficient Continual Learning with Dynamic Low-Rank Adaptation
        73035, -- 2505.11235 Efficient Orthogonal Fine-Tuning with Principal Subspace Adaptation
        73626, -- 2504.06426 S'MoRE: Structural Mixture of Residual Experts for LLM Fine-tuning
        74345, -- 2503.01419 Parameter-Efficient Fine-Tuning of Large Language Models via Deconvolution in Su
        74398, -- 2503.01905 PaCA: Partial Connection Adaptation for Efficient Fine-Tuning
        75748, -- 2411.13901 Dressing the Imagination: A Dataset for AI-Powered Translation of Text into Fash
        75873, -- 2411.01800 Expanding Sparse Tuning for Low Memory Usage
        76298, -- 2409.15760 NanoVoice: Efficient Speaker-Adaptive Text-to-Speech for Multiple Speakers
        76515, -- 2408.14470 Step-by-Step Unmasking for Parameter-Efficient Fine-tuning of Large Language Mod
        76571, -- 2408.09397 Combo: Co-speech holistic 3D human motion generation and efficient customizable
        76757, -- 2407.09946 Low-Rank Interconnected Adaptation across Layers
        77013, -- 2406.09044 MiLoRA: Harnessing Minor Singular Components for Parameter-Efficient LLM Finetun
        77016, -- 2406.08798 FouRA: Fourier Low Rank Adaptation
        77019, -- 2406.08447 The Impact of Initialization on LoRA Finetuning Dynamics
        77114, -- 2406.06564 SwitchLoRA: Switched Low-Rank Adaptation Can Learn Full-Rank Information
        77294, -- 2405.06368 DP-DyLoRA: Fine-Tuning Transformer-Based Models On-Device under Differentially P
        77554, -- 2403.19243 Efficient Learning With Sine-Activated Low-rank Matrices
        83016, -- 2605.08423 Queryable LoRA: Instruction-Regularized Routing Over Shared Low-Rank Update Atom
        83972, -- 2409.19289 FINE: Factorizing Knowledge for Initialization of Variable-sized Diffusion Model
        83996, -- 2503.22172 Concept-Aware LoRA for Domain-Aligned Segmentation Dataset Generation
        84249, -- 2511.20302 CrossEarth-Gate: Fisher-Guided Adaptive Tuning Engine for Efficient Adaptation o
        84313, -- 2512.02441 Basis-Oriented Low-rank Transfer for Few-Shot and Test-Time Adaptation
        84323, -- 2512.02781 LumiX: Structured and Coherent Text-to-Intrinsic Generation
        84570, -- 2602.20089 StructXLIP: Enhancing Vision-language Models with Multimodal Structural Cues
        84611, -- 2602.21977 When LoRA Betrays: Backdooring Text-to-Image Models by Masquerading as Benign Ad
        85001, -- 2603.20403 FAAR: Efficient Frequency-Aware Multi-Task Fine-Tuning via Automatic Rank Select
        85003, -- 2603.20470 DiffGraph: An Automated Agent-driven Model Merging Framework for In-the-Wild Tex
        85170, -- 2603.27383 Decompose, Mix, Adapt: A Unified Framework for Parameter-Efficient Neural Networ
        85285, -- 2604.05183 OrthoFuse: Training-free Riemannian Fusion of Orthogonal Style-Concept Adapters
        85523, -- 2605.07256 TAS-LoRA: Transformer Architecture Search with Mixture-of-LoRA Experts
        85532, -- 2605.08589 S2FT: Parameter-Efficient Fine-Tuning in Sparse Spectrum Domain
        85538, -- 2605.10130 Thermal-Det: Language-Guided Cross-Modal Distillation for Open-Vocabulary Therma
        85698, -- 2510.01938 StelLA: Subspace Learning in Low-rank Adaptation using Stiefel Manifold
        85713, -- 2505.18877 RefLoRA: Refactored Low-Rank Adaptation for Efficient Fine-Tuning of Large Model
        85952, -- 2510.03276 QuadEnhancer: Leveraging Quadratic Transformations to Enhance Deep Neural Networ
        86006, -- 2506.19072 Hawaii: Hierarchical Visual Knowledge Transfer for Efficient Vision-Language Mod
        86024, -- 2505.21732 LaX: Boosting Low-Rank Training of Foundation Models via Latent Crossing
        86038, -- 2505.19107 Optimization Inspired Few-Shot Adaptation for Large Language Models
        86144, -- 2506.05191 MokA: Multimodal Low-Rank Adaptation for MLLMs
        86202, -- 2506.02453 PAID: Pairwise Angular-Invariant Decomposition for Continual Test-Time Adaptatio
        86409, -- 2502.03304 Harmony in Divergence: Towards Fast, Accurate, and Memory-efficient Zeroth-order
        86434, -- 2507.20400 Beyond Value Functions: Single-Loop Bilevel Optimization under Flatness Conditio
        86519, -- 2505.13515 LoRASuite: Efficient LoRA Adaptation Across Large Language Model Upgrades
        86530, -- 2505.22444 On Geometry-Enhanced Parameter-Efficient Fine-Tuning for 3D Scene Segmentation
        86736, -- 2506.21374 Pay Attention to Small Weights
        87062, -- 2508.08730 Magical: Medical Lay Language Generation via Semantic Invariance and Layperson-t
        87282, -- 2506.05568 Ravan: Multi-Head Low-Rank Adaptation for Federated Fine-Tuning
        87332, -- 2505.18738 AuroRA: Breaking Low-Rank Bottleneck of LoRA with Nonlinear Mapping
        87482, -- 2506.23551 A Unified Framework on the Universal Approximation of Transformer-type Architect
        87538, -- 2507.13260 Efficient Adaptation of Pre-trained Vision Transformer underpinned by Approximat
        87958, -- 2504.12436 Sparsity Outperforms Low-Rank Projections in Few-Shot Adaptation
        87975, -- 2411.13949 SMoLoRA: Exploring and Defying Dual Catastrophic Forgetting in Continual Visual
        88174, -- 2504.00851 Generalized Tensor-based Parameter-Efficient Fine-Tuning via Lie Group Transform
        88189, -- 2501.01529 SAFER: Sharpness Aware layer-selective Finetuning for Enhanced Robustness in vis
        88331, -- 2507.08044 ConsNoTrainLoRA: Data-driven Weight Initialization of Low-rank Adapters using Co
        88348, -- 2510.04668 ConceptSplit: Decoupled Multi-Concept Personalization of Diffusion Models via To
        88467, -- 2507.10855 Sparse Fine-Tuning of Transformers for Generative Tasks
        90118, -- 2503.18459 Hiding Images in Diffusion Models by Editing Learned Score Functions
        90436, -- 2504.01961 Learning from Streaming Video with Orthogonal Gradients
        90488, -- 2503.16843 LoRASculpt: Sculpting LoRA for Harmonizing General and Specialized Knowledge in
        90783, -- 2411.15224 Parameter Efficient Mamba Tuning via Projector-targeted Diagonal-centric Linear
        91000, -- 2503.14897 When Domain Generalization meets Generalized Category Discovery: An Adaptive Tas
        91046, -- 2410.20625 LoRA Done RITE: Robust Invariant Transformation Equilibration for LoRA Optimizat
        91099, -- 2503.12576 RaSA: Rank-Sharing Low-Rank Adaptation
        91203, -- 2501.13904 Privacy-Preserving Personalized Federated Prompt Learning for Multimodal Large L
        91420, -- 2410.01359 FlashMask: Efficient and Rich Mask Extension of FlashAttention
        91709, -- 2411.03855 MambaPEFT: Exploring Parameter-Efficient Fine-Tuning for Mamba
        91792, -- 2411.16870 RECAST: Reparameterized, Compact weight Adaptation for Sequential Tasks
        91915, -- 2410.09846 A Quantum Circuit-Based Compression Perspective for Parameter-Efficient Learning
        91917, -- 2410.18965 On the Crucial Role of Initialization for Matrix Factorization
        91930, -- 2410.16103 LDAdam: Adaptive Optimization from Low-Dimensional Gradient Statistics
        92256, -- 2409.01035 Unleashing the Power of Task-Specific Directions in Parameter Efficient Fine-tun
        92638, -- 2510.19675 Study of Training Dynamics for Memory-Constrained Fine-Tuning
        92862, -- 2602.17095 FLoRG: Federated Fine-tuning with Low-rank Gram Matrices and Procrustes Alignmen
        92952, -- 2511.06225 MoRA: Missing Modality Low-Rank Adaptation for Visual Recognition
        93173, -- 2510.17206 Soft-Masked Diffusion Language Models
        93231, -- 2603.13281 ICaRus: Identical Cache Reuse for Efficient Multi-Model Inference
        93269, -- 2505.20211 PiCa: Parameter-Efficient Fine-Tuning with Column Space Projection
        93304, -- 2603.05204 Stable-LoRA: Stabilizing Feature Learning of Low-Rank Adaptation
        93369, -- 2510.14301 A Guardrail for Safety Preservation: When Safety-Sensitive Subspace Meets Harmfu
        93420, -- 2603.01526 Scalable Multi-Task Low-Rank Model Adaptation
        93930, -- 2510.09160 Efficient Resource-Constrained Training of Transformers via Subspace Optimizatio
        93937, -- 2509.22020 Task-Adaptive Parameter-Efficient Fine-Tuning for Weather Foundation Models
        93980, -- 2508.06953 BoRA: Towards More Expressive Low-Rank Adaptation with Block Diversity
        94019, -- 2508.19564 Bi-LoRA: Efficient Sharpness-Aware Minimization for Fine-Tuning Large-Scale Mode
        94133, -- 2509.24245 Prompt and Parameter Co-Optimization for Large Language Models
        94380, -- 2510.01175 On the Benefits of Weight Normalization for Overparameterized Matrix Sensing
        94473, -- 2509.25214 On-the-Fly Adaptation to Quantization: Configuration-Aware LoRA for Efficient Fi
        94630, -- 2602.00135 LLaVA-FA: Learning Fourier Approximation for Compressing Large Multimodal Models
        94755, -- 2602.24283 Taming Momentum: Rethinking Optimizer States Through Low-Rank Approximation
        94861, -- 2506.18184 Memba: Membrane-driven Parameter-Efficient Fine-Tuning for Mamba
        94923, -- 2603.13792 IGU-LoRA: Adaptive Rank Allocation via Integrated Gradients and Uncertainty-Awar
        94962, -- 2601.22905 FlexLoRA: Entropy-Guided Flexible Low-Rank Adaptation
        96101, -- 2603.07404 Adaptive Capacity Allocation for Vision Language Action Fine-Tuning
        97970, -- 2606.07207 Entropy as a Structural Prior: How a Log-Barrier on DiT Belief Space Drives Musi
        98088, -- 2605.25077 WorldCraft: From Camera Navigation to Object Manipulation in Interactive Video W
        98317, -- 2606.12883 The Hidden Power of Scaling Factor in LoRA Optimization
        99075, -- 2607.02512 Program-as-Weights: A Programming Paradigm for Fuzzy Functions
        99080, -- 2607.02269 AnyGroundBench: A Specialized-Domain Benchmark for Video Grounding in Vision-Lan
        99828, -- 2602.00942 SALAAD: Sparse And Low-Rank Adaptation via ADMM for Large Language Model Inferen
        100231, -- 2510.24561 LoRA-DA: Data-Aware Initialization for Low-Rank Adaptation via Asymptotic Analys
        100468, -- 2603.00425 Weight Updates as Activation Shifts: A Principled Framework for Steering
        101122, -- 2510.23818 ScaLoRA: Optimally Scaled Low-Rank Adaptation for Efficient High-Rank Fine-Tunin
        102439, -- 2603.15965 MoLoRA: Composable Specialization via Per-Token Adapter Routing
        102981, -- 2506.02724 WeightLoRA: Keep Only Necessary Adapters
        104051, -- 2607.03065 Spectral Rewiring for Exploration, Purification, and Model Merging
        105154, -- 2503.07204 Endo-FASt3r: Endoscopic Foundation model Adaptation for Structure from motion
        105181, -- 2506.21535 Exploring the Design Space of 3D MLLMs for CT Report Generation
        105873, -- 2607.25802 Explicit Layer Modeling for Video Object Insertion and Layer Decomposition
        106174, -- 2602.17510 LORA-CRAFT: Cross-layer Rank Adaptation via Frozen Tucker Decomposition of Pre-t
        106325, -- 2604.23036 Preserving Long-Tailed Expert Information in Mixture-of-Experts Tuning
        106710, -- 2504.08915 Parameter-Free Fine-tuning via Redundancy Elimination for Vision Foundation Mode
        106932, -- 2504.09109 Probability Distribution Alignment and Low-Rank Weight Decomposition for Source-
        107470, -- 2511.17582 GateRA: Token-aware Modulation for Parameter-Efficient Fine-tuning
        108961, -- 2608.07051 YOLO-PEFT: Parameter-Efficient Fine-Tuning on YOLO Family
        110589, -- 2409.15520 MobiZO: Enabling Efficient LLM Fine-Tuning at the Edge via Inference Engines
        110603, -- 2506.02001 EcoLoRA: Communication-Efficient Federated Fine-Tuning of Large Language Models
        110919, -- 2508.19089 It’s All About In-Context Learning! Teaching Extremely Low-Resource Languages to
        111338, -- 2505.20006 Mixture of LoRA Experts for Low-Resourced Multi-Accent Automatic Speech Recognit
        112144, -- external SupraDoRAL: Automatic Word Prominence Detection Using Suprasegmental Dependencie
        113807, -- 2608.31036 Normalized Low-Rank Adaptation
        118162, -- 2607.08194 Dive into the implicit biases of low-rank vision-language alignment
        118211, -- 2607.29033 SAM+D: Parameter-Efficient Dimensional Lifting of SAM-Family Models via Depth-Ro
        118224, -- 2606.28077 TextDS: Parameter-Efficient Representation Alignment for Scene Text Detection un
        118439, -- 2607.12539 DiTailed: Ensuring Visual Object Consistency in Text-Image-to-Image Flow Matchin
        119504, -- 2511.18242 EgoVITA: Learning to Plan and Verify for Egocentric Video Reasoning
        119893, -- 2502.06029 DiTASK: Multi-Task Fine-Tuning with Diffeomorphic Transformations
        120590, -- 2503.18337 Coeff-Tuning: A Graph Filter Subspace View for Tuning Attention-Based Large Mode
        120820, -- 2603.21111 Frequency Switching Mechanism for Parameter-Efficient Multi-Task Learning
        121466, -- 2512.08912 LiDAS: Lighting-driven Dynamic Active Sensing for Nighttime Perception
        121912, -- 2604.01310 Sparse Spectral LoRA: Routed Experts for Medical VLMs
        122385, -- 2609.34054 PReCache: Efficient KV Cache Sharing for Multi-LoRA Agents via Low-Rank Precompu
        122676, -- 2609.33463 Rethinking Token Reweighting for SFT: Suppress, Reverse, and Extrapolate Learned
        122711, -- 2610.04226 PaLoRA: Paced Low-Rank Adaptation for Continual Learning
        123709, -- 2610.20019 MorphAct: Robot Policies Morphing with the Worlds They Act In
        124381, -- 2410.23066 Don't Pay Attention, PLANT It: Pretraining Attention via Learning-to-Rank
        124508, -- 2608.15285 PhaseLoRA: Control-Regime-Conditioned Low-Rank Adaptation for Continuous-Action
        124657, -- 2605.11872 LOFT: Low-Rank Orthogonal Fine-Tuning via Task-Aware Support Selection
        124679, -- 2605.19767 AR1-ZO: Topology-Aware Rank-1 Zeroth-Order Queries for High-Rank LoRA Fine-Tunin
        125462, -- 2512.08040 Lost in Translation, Found in Embeddings: Sign Language Translation and Alignmen
        125619, -- 2606.31397 Mixture-of-Control: State-Aware Fine-Tuning for Transformer-based Models
        125634, -- 2605.06127 Continuous Expert Assembly: Instance-Conditioned Low-Rank Residuals for All-in-O
        125867, -- 2605.21147 SMoA: Spectrum Modulation Adapter for Parameter-Efficient Fine-Tuning
        125945, -- 2610.06243 RoSA: Rotational Sparse Adaptation for Memory-Efficient Fine-Tuning
        126014, -- 2606.16454 SDS-LoRA: Overcoming Anisotropic Gradient Scaling in Low-Rank Adaptation
        126786, -- 2605.10741 AdaPaD: Adaptive Parallel Deflation for PEFT with Self-Correcting Rank Discovery
        126986, -- 2609.25655 From Experts to Sub-experts: Fine-grained Parameter-Efficient Fine-Tuning for Mo
        127161, -- 2603.00720 MARS: Harmonizing Multimodal Convergence via Adaptive Rank Search
        127316, -- 2605.12960 DiM$^3$: Bridging Multilingual and Multimodal Models via Direction- and Magnitud
        127390, -- 2605.25565 RotMoLE: Enhancing Mixture of Low-Rank Experts through Rotational Gating Mechani
        128918, -- 2605.06166 One Algorithm, Two Goals: Dual Scoring for Parameter and Data Selection in LLM F
        130411, -- 2605.24484 SPACE: Unifying Symmetric and Asymmetric Routing Problems for Generalist Neural
        130446, -- 2601.21929 LoRIF: Low-Rank Influence Functions for Scalable Training Data Attribution
        131122, -- 2605.22869 FuRA: Full-Rank Parameter-Efficient Fine-Tuning with Spectral Preconditioning
        131844, -- 2611.05193 Factorized MLLM Embeddings for Composed Image Retrieval
        131866  -- 2611.04634 VeriSpoof: Beyond Real or Fake with One Audio LLM
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites DoRA without naming it, names it only in passing, or DoRA names another method (DoRA video SSL, Dynamic Low-Rank Adaptation)'
FROM dora_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING dora_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING dora_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- kaiming-initialization: 9 links, 194 exclusions. Local Semantic Scholar citers of 1502.01852 (200 incl. source; most cite it for PReLU or ImageNet results) plus title/abstract candidates; kept only weight-initialization work that names or analyzes He-style initialization.
CREATE TEMP TABLE kaiming_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'kaiming-initialization'
  AND p.id IN (
        151, -- 1502.01852 Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Cla
        56848, -- 2603.16653 HeBA: Heterogeneous Bottleneck Adapters for Robust Vision-Language Models
        85939, -- 2505.12909 Sinusoidal Initialization, Time for a New Start
        85974, -- 2505.22491 On the Surprising Effectiveness of Large Learning Rates under Standard Width Sca
        87283, -- 2505.19827 Revisiting Glorot Initialization for Long-Range Linear Recurrences
        94702, -- 2505.24333 Two failure modes of deep transformers and how to avoid them: a unified theory o
        94933, -- 2509.03417 Initialization Schemes for Kolmogorov–Arnold Networks: An Empirical Study
        101746, -- 2602.19799 Path-conditioned training: a principled way to rescale ReLU neural networks
        126131  -- external Tropical Boundary Complexity of Deep ReLU Networks
  );

DELETE FROM paper_method_exclusions x
USING kaiming_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM kaiming_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM kaiming_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE kaiming_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'kaiming-initialization'
  AND p.id IN (
        333, -- 1603.05027 Identity Mappings in Deep Residual Networks
        48909, -- 2505.11881 Revisiting Residual Connections: Orthogonal Updates for Stable and Efficient Dee
        48999, -- 2505.12805 FedSVD: Adaptive Orthogonalization for Private Federated Learning with LoRA
        49279, -- 2505.15270 Scaling Diffusion Transformers Efficiently via $μ$P
        49709, -- 2505.19242 Deformable Attentive Visual Enhancement for Referring Segmentation Using Vision-
        50041, -- 2505.22785 Navigating the Latent Space Dynamics of Neural Models
        50054, -- 2505.22922 Scalable Parameter and Memory Efficient Pretraining for LLM: Recent Algorithmic
        50167, -- 2505.23808 DenseLoRA: Dense Low-Rank Adaptation of Large Language Models
        50239, -- 2505.24527 Optimal Density Functions for Weighted Convolution in Learning Models
        50241, -- 2505.24558 Optimal Weighted Convolution for Classification and Denosing
        50719, -- 2506.06280 Eigenspectrum Analysis of Neural Networks without Aspect Ratio Bias
        50808, -- 2506.07998 Generative Modeling of Weights: Generalization or Memorization?
        50810, -- 2506.08001 Reparameterized LLM Training via Orthogonal Equivalence Transformation
        51050, -- 2506.10973 Principled Approaches for Extending Neural Architectures to Function Spaces for
        51090, -- 2506.12015 EMLoC: Emulator-based Memory-efficient Fine-tuning with LoRA Correction
        51174, -- 2506.13771 LittleBit: Ultra Low-Bit Quantization via Latent Factorization
        51308, -- 2506.16925 Single-shot thermometry of simulated Bose--Einstein condensates using artificial
        51470, -- 2506.20629 PLoP: Precise LoRA Placement for Efficient Finetuning of Large Models
        51508, -- 2506.21338 AGTCNet: A Graph-Temporal Approach for Principled Motor Imagery EEG Classificati
        51612, -- 2507.00966 MambAttention: Mamba with Multi-Head Attention for Generalizable Single-Channel
        51636, -- 2507.02025 IntFold: A Controllable Foundation Model for General and Specialized Biomolecula
        52174, -- 2508.01928 IAUNet: Instance-Aware U-Net
        52427, -- 2508.13745 Refining Contrastive Learning and Homography Relations for Multi-Modal Recommend
        52848, -- 2509.14026 Quantum Variational Activation Functions Empower Kolmogorov-Arnold Networks
        53399, -- 2510.07314 GyroSwin: 5D Surrogates for Gyrokinetic Plasma Turbulence Simulations
        53665, -- 2510.15262 Robust Layerwise Scaling Rules by Proper Weight Decay Tuning
        53821, -- 2510.21223 Model Merging with Functional Dual Anchors
        54577, -- 2512.04746 SignRoundV2: Closing the Performance Gap in Extremely Low-Bit Post-Training Quan
        55051, -- 2512.24176 Guiding a Diffusion Transformer with the Internal Dynamics of Itself
        55183, -- 2601.02016 Enhancing Object Detection with Privileged Information: A Model-Agnostic Teacher
        55647, -- 2601.22141 Routing the Lottery: Adaptive Subnetworks for Heterogeneous Data
        55841, -- 2602.04998 Learning Rate Matters: Vanilla LoRA May Suffice for LLM Fine-tuning
        56621, -- 2603.10160 ReMix: Reinforcement routing for mixtures of LoRAs in LLM finetuning
        56688, -- 2603.12228 Neural Thickets: Diverse Task Experts Are Dense Around Pretrained Weights
        56846, -- 2603.17079 ACE-LoRA: Graph-Attentive Context Enhancement for Parameter-Efficient Adaptation
        56868, -- 2603.19224 EffectErase: Joint Video Object Removal and Insertion for High-Quality Effect Er
        57636, -- 2604.17078 Understanding and Enforcing Weight Disentanglement in Task Arithmetic
        57671, -- 2604.19835 Expert Upcycling: Shifting the Compute-Efficient Frontier of Mixture-of-Experts
        57747, -- 2604.21106 How Much Is One Recurrence Worth? Iso-Depth Scaling Laws for Looped Language Mod
        58901, -- 2603.25411 HiSpatial: Taming Hierarchical 3D Spatial Understanding in Vision-Language Model
        59687, -- 2603.08055 Speed3R: Sparse Feed-forward 3D Reconstruction Models
        60407, -- 2512.21390 GraviBERT: Transformer-based inference for gravitational-wave time series
        60479, -- 2602.17493 Learning with Boolean threshold functions
        61519, -- 2602.01418 Where to Attend: A Principled Vision-Centric Position Encoding with Parabolas
        61970, -- 2601.19618 The role of self-supervised pretraining in differentially private medical image
        62560, -- 2601.08393 Controlled LLM Training on Spectral Sphere
        62653, -- 2601.07516 Controlling Multimodal Conversational Agents with Coverage-Enhanced Latent Actio
        62707, -- 2601.10740 Neuro-Symbolic Activation Discovery: Transferring Mathematical Structures from P
        62776, -- 2601.05052 DeepWeightFlow: Re-Basined Flow Matching for Generating Neural Network Weights
        62913, -- 2601.03431 WeedRepFormer: Reparameterizable Vision Transformers for Real-Time Waterhemp Seg
        63066, -- 2601.01306 Towards a Principled Muon under μP: Ensuring Spectral Conditions throughout Trai
        64011, -- 2512.07136 A Large-Scale Multimodal Dataset and Benchmarks for Human Activity Scene Underst
        64063, -- 2512.05915 LDLT L-Lipschitz Network: Generalized Deep End-To-End Lipschitz Network Construc
        64719, -- 2511.17735 Towards Open-Ended Visual Scientific Discovery with Sparse Autoencoders
        65423, -- 2511.02489 Object Detection as an Optional Basis: A Graph Matching Network for Cross-View U
        65908, -- 2510.21450 ParaRNN: Unlocking Parallel Training of Nonlinear RNNs for Large Language Models
        66078, -- 2510.18812 A Unified Perspective on Optimization in Machine Learning and Neuroscience: From
        66832, -- 2510.06640 A Comparative Analysis of Contextual Representation Flow in State-Space and Tran
        66919, -- 2510.05092 Learning to Interpret Weight Differences in Language Models
        67051, -- 2510.02765 Curl Descent: Non-Gradient Learning Dynamics with Sign-Diverse Plasticity
        67129, -- 2510.01704 Holistic Order Prediction in Natural Scenes
        67543, -- 2509.23833 AISHELL6-whisper: A Chinese Mandarin Audio-visual Whisper Speech Dataset with Sp
        67608, -- 2509.23253 Training Deep Normalization-Free Spiking Neural Networks with Lateral Inhibition
        68024, -- 2509.17530 An Unlearning Framework for Continual Learning
        68313, -- 2509.13240 Don't Forget the Nonlinearity: Unlocking Activation Functions in Efficient Fine-
        68785, -- 2509.03234 TeRA: Vector-based Random Tensor Network for High-Rank Adaptation of Large Langu
        69155, -- 2508.18903 Distance-informed Neural Processes
        70071, -- 2508.05059 Learning from Oblivion: Predicting Knowledge Overflowed Weights via Retrodiction
        70252, -- 2508.02668 LOST: Low-rank and Sparse Pre-training for Large Language Models
        70445, -- 2508.00230 Towards Higher Effective Rank in Parameter-efficient Fine-tuning using Khatri--R
        71083, -- 2507.12144 FourCastNet 3: A geometric approach to probabilistic machine-learning weather fo
        71141, -- 2507.10419 Multiple Choice Learning of Low Rank Adapters for Language Modeling
        71317, -- 2507.06558 The Primacy of Magnitude in Low-Rank Adaptation
        71402, -- 2507.04453 ESSA: Evolutionary Strategies for Scalable Alignment
        71618, -- 2506.23639 Unified Multimodal Understanding via Byte-Pair Visual Encoding
        71696, -- 2506.22032 Partial CLIP is Enough: Chimera-Seg for Zero-shot Semantic Segmentation
        71699, -- 2506.21894 Thompson Sampling in Function Spaces via Neural Operators
        71784, -- 2506.18493 ShowFlow: From Robust Single Concept to Condition-Free Multi-Concept Generation
        71978, -- 2506.12704 Flexible Realignment of Language Models
        72027, -- 2505.18023 Time to Spike? Understanding the Representational Power of Spiking Neural Networ
        72055, -- 2506.10142 Rethinking Brain Tumor Segmentation from the Frequency Domain Perspective
        72127, -- 2506.07691 Training Superior Sparse Autoencoders for Instruct Models
        72141, -- 2506.07500 Mind the Gap: Removing the Discretization Gap in Differentiable Logic Gate Netwo
        72432, -- 2506.01153 Weight-Space Linear Recurrent Neural Networks
        72481, -- 2506.00486 It Takes a Good Model to Train a Good Model: Generalized Gaussian Priors for Opt
        72531, -- 2505.23942 SG-Blend: Learning an Interpolation Between Improved Swish and GELU for Robust N
        72557, -- 2505.23094 MAP: Revisiting Weight Decomposition for Low-Rank Adaptation
        72902, -- 2505.15174 Enhancing Certified Robustness via Block Reflector Orthogonal Layers and Logit A
        72979, -- 2505.12565 mCLM: A Modular Chemical Language Model that Generates Functional and Makeable M
        84066, -- 2508.01603 Towards Generalizable AI-Generated Image Detection via Image-Adaptive Prompt Lea
        84793, -- 2603.07506 A Unified Framework for Knowledge Transfer in Bidirectional Model Scaling
        85139, -- 2603.26096 AcTTA: Rethinking Test-Time Adaptation via Dynamic Activation
        85323, -- 2604.08846 Dictionary-Aligned Concept Control for Safeguarding Multimodal LLMs
        85948, -- 2509.17552 Can LLMs Reason Over Non-Text Modalities in a Training-Free Manner? A Case Study
        86056, -- 2506.23881 Spurious-Aware Prototype Refinement for Reliable Out-of-Distribution Detection
        86144, -- 2506.05191 MokA: Multimodal Low-Rank Adaptation for MLLMs
        86335, -- 2505.15647 Second-Order Convergence in Private Stochastic Non-Convex Optimization
        86504, -- 2506.13274 AdaLRS: Loss-Guided Adaptive Learning Rate Search for Efficient Foundation Model
        86519, -- 2505.13515 LoRASuite: Efficient LoRA Adaptation Across Large Language Model Upgrades
        86991, -- 2505.14512 Just One Layer Norm Guarantees Stable Extrapolation
        87152, -- 2510.02779 Optimal Rates for Generalization of Gradient Descent for Deep ReLU Classificatio
        87318, -- 2505.19087 Temperature is All You Need for Generalization in Langevin Dynamics and other Ma
        87358, -- 2506.05801 Neural Collapse in Cumulative Link Models for Ordinal Regression: An Analysis wi
        87588, -- 2507.04692 Structure-Guided Diffusion Models for High-Fidelity Portrait Shadow Removal
        88331, -- 2507.08044 ConsNoTrainLoRA: Data-driven Weight Initialization of Low-rank Adapters using Co
        88604, -- 2506.06940 Understanding Sharpness Dynamics in NN Training with a Minimalist Example: The E
        89108, -- 2505.12871 Does Low Rank Adaptation Lead to Lower Robustness against Training-Time Attacks?
        89793, -- 2506.03919 Weisfeiler and Leman Go Gambling: Why Expressive Lottery Tickets Win
        89890, -- 2505.23194 Beyond Zero Initialization: Investigating the Impact of Non-Zero Initialization
        92565, -- 2606.04048 Unlocking Feature Learning in Gated Delta Networks at Scale
        92623, -- 2512.23278 Flow2GAN: Hybrid Flow Matching and GAN with Multi-Resolution Network for Few-ste
        92626, -- 2602.08040 FIRE: Frobenius-Isometry Reinitialization for Balancing the Stability–Plasticity
        92659, -- 2505.21119 Universal Value-Function Uncertainties
        92764, -- 2510.25240 Generative Bayesian Optimization: Generative Models as Acquisition Functions
        92862, -- 2602.17095 FLoRG: Federated Fine-tuning with Low-rank Gram Matrices and Procrustes Alignmen
        93001, -- 2509.22445 Bridging Kolmogorov Complexity and Deep Learning: Asymptotically Optimal Descrip
        93187, -- 2512.04165 Mitigating the Curse of Detail: Scaling Arguments for Feature Learning and Sampl
        93304, -- 2603.05204 Stable-LoRA: Stabilizing Feature Learning of Low-Rank Adaptation
        93369, -- 2510.14301 A Guardrail for Safety Preservation: When Safety-Sensitive Subspace Meets Harmfu
        93427, -- 2604.10636 Mitigating Privacy Risk via Forget Set-Free Unlearning
        94280, -- 2510.02903 Learning Explicit Single-Cell Dynamics Using ODE Representations
        94495, -- 2509.20829 Explaining Grokking and Information Bottleneck through Neural Collapse Emergence
        94529, -- 2509.22562 Activation Function Design Sustains Plasticity in Continual Learning
        94573, -- 2601.20232 Visual Prompt-Agnostic Evolution
        94754, -- 2601.21320 Optimal Transport-Induced Samples against Out-of-Distribution Overconfidence
        94796, -- 2505.15504 Exploiting Low-Dimensional Manifold of Features for Few-Shot Whole Slide Image C
        94958, -- 2511.05581 Cannistraci-Hebb Training on Ultra-Sparse Spiking Neural Networks
        95051, -- 2603.14276 All-day Multi-scenes Lifelong Vision-and-Language Navigation with Tucker Adaptat
        95063, -- 2603.06073 Lifelong Embodied Navigation Learning
        98031, -- 2606.04925 Scene-Centric Unsupervised Video Panoptic Segmentation
        98144, -- 2606.11131 UniPET: a universal network for high-quality PET image denoising across varied d
        99124, -- 2605.05676 Decomposing the Basic Abilities of Large Language Models: Mitigating Cross-Task
        99252, -- 2605.15877 Shapley Neuron Values for Continual Learning: Which Neurons Matter Most?
        99356, -- 2605.08842 XPERT: Expert Knowledge Transfer for Effective Training of Language Models
        99539, -- 2606.03310 Learning Multi-Scale Hypergraph for High-Order Brain Connectivity Analysis
        99685, -- 2606.04485 LimiX-2M: Mitigating Low-Rank Collapse and Attention Bottlenecks in Tabular Foun
        99857, -- 2602.01267 Diving into Kronecker Adapters: Component Design Matters
        99865, -- 2506.15412 Partitioning for Intrinsic Model Inversion Resistance in Collaborative Inference
        99974, -- 2605.29983 Improving Adversarial Robustness of Attribution via Implicit Regularization
        99989, -- 2602.22962 Scaling Laws of Global Weather Models
        100231, -- 2510.24561 LoRA-DA: Data-Aware Initialization for Low-Rank Adaptation via Asymptotic Analys
        100497, -- 2601.21942 Clustering in Deep Stochastic Transformers
        100768, -- 2508.11522 Finite-Width Neural Tangent Kernels from Feynman Diagrams
        100823, -- 2605.29716 NaRA: Noise-Aware LoRA for Parameter-Efficient Fine-Tuning of Diffusion LLMs
        100881, -- 2602.07697 On the Infinite Width and Depth Limits of Predictive Coding Networks
        100912, -- 2602.12390 Rational Neural Networks have Expressivity Advantages
        100914, -- 2602.15634 Beyond ReLU: Bifurcation, Oversmoothing, and Topological Priors
        101068, -- 2604.03314 CoLA: Cross-Modal Low-rank Adaptation for Multimodal Downstream Tasks
        101134, -- 2605.31580 Giving Sensors a Voice: Multimodal JEPA for Semantic Time-Series Embeddings
        101419, -- 2507.13595 NoiseSDF2NoiseSDF: Learning Clean Neural Fields from Noisy Supervision
        101586, -- 2602.16340 The Implicit Bias of Adam and Muon on Smooth Homogeneous Neural Networks
        101753, -- 2509.22335 Spectral Collapse Drives Loss of Plasticity in Deep Continual Learning
        101803, -- 2509.24467 Interpretable Self-Supervised Learning via Representer Landmarks and Nyström App
        101894, -- 2606.20329 Constrained hybrid modelling to predict microbial dynamics and organic matter tu
        101904, -- 2605.27541 SparseOpt: Addressing Normalization-induced Gradient Skew in Sparse Training
        102028, -- 2605.21648 Dropout Universality: Scaling Laws and Optimal Scheduling at the Edge-of-Chaos
        102079, -- 2602.06204 Learning Rate Scaling across LoRA Ranks and Transfer to Full Finetuning
        102204, -- 2606.09762 Preserving Plasticity in Continual Learning via Dynamical Isometry
        102539, -- 2602.07494 Hyperparameter Transfer Laws for Non-Recurrent Multi-Path Neural Networks
        102639, -- 2607.03819 CGGS: Consistency-Augmented Geometric Gaussian Splatting for Ego-centric 3D Scen
        103127, -- 2604.06291 TalkLoRA: Communication-Aware Mixture of Low-Rank Adaptation for Large Language
        104558, -- 2607.10495 NanoVSR: Towards Real-Time Video Super-Resolution on Edge Devices
        104845, -- 2605.25426 Learning View-Dependent Splatting Kernels
        105480, -- 2506.15404 NERO: Explainable Out-of-Distribution Detection with Neuron-level Relevance in G
        106484, -- 2511.06859 TuckA: Hierarchical Compact Tensor Experts for Efficient Fine-Tuning
        106735, -- 2511.05853 Point Cloud Segmentation of Integrated Circuits Package Substrates Surface Defec
        107119, -- 2508.09428 What-Meets-Where: Unified Learning of Action and Contact Localization in Images
        107285, -- 2510.13003 OPLoRA: Orthogonal Projection LoRA Prevents Catastrophic Forgetting During Param
        107416, -- 2511.10015 Efficient Verification and Falsification of ReLU Neural Barrier Certificates
        107608, -- 2512.23146 A Network of Biologically Inspired Rectified Spectral Units (ReSUs) Learns Hiera
        108417, -- 2508.16922 MSPCaps: A Multi-Scale Patchify Capsule Network with Cross-Agreement Routing for
        110458, -- 2509.00996 MEPT: Mixture of Expert Prompt Tuning as a Manifold Mapper
        110526, -- 2509.16882 Dynamic Expert Specialization: Towards Catastrophic Forgetting-Free Multi-Domain
        110682, -- 2506.13541 Mixture of Weight-shared Heterogeneous Group Attention Experts for Dynamic Token
        111384, -- 2507.20926 End-to-End DOA-Guided Speech Extraction in Noisy Multi-Talker Scenarios
        111601, -- 2506.00865 GIA-MIC: Multimodal Emotion Recognition with Gated Interactive Attention and Mod
        111738, -- 2505.24498 Efficient Neural and Numerical Methods for High-QualityOnline Speech Spectrogram
        113877, -- 2608.08003 The Spectral Neuron
        119245, -- 2607.20660 Axolotl3D: a Unified Framework for Faithful 3D Shape Completion
        121647, -- 2511.20263 Advancing Image Classification with Discrete Diffusion Classification Modeling
        122203, -- 2609.23087 Neural Spectral Capacity: Measuring and Designing Architectures from Network Spe
        124918, -- 2510.05416 Correlating Cross-Iteration Noise for DP-SGD using Model Curvature
        125194, -- 2505.20892 One-Time Soft Alignment Enables Resilient Learning without Weight Transport
        125887, -- 2605.25880 The Quantization Benefits of Residual-Free Transformers
        126126, -- 2605.05113 How Long Does Infinite Width Last? Signal Propagation in Long-Range Linear Recur
        127269, -- 2610.02545 Reward Inflation: A Healthy Stimulus for Reinforcement Learning
        128864, -- 2605.08832 Inpainting physics: self-supervised learning for context-driven fluid simulation
        129057, -- 2606.26432 Embedding Foundation Model Predictions in Discrete-Choice Models with Structural
        129294, -- 2606.03990 Neuron Populations Exhibit Divergent Selectivity with Scale
        129537, -- 2605.19781 From SGD to Muon: Adaptive Optimization via Schatten-p Norms
        130353, -- 2606.10906 Human-AI Teaming Through the Lens of Calibration
        130411, -- 2605.24484 SPACE: Unifying Symmetric and Asymmetric Routing Problems for Generalist Neural
        130962, -- 2607.03148 Rethinking Neural Nonlinearity as Gating
        130996  -- 2605.29152 Do Deep Networks Forget Initialization? A Forgetting-Time View of Practical Indu
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites Delving Deep into Rectifiers (PReLU/ImageNet) without using or analyzing Kaiming initialization'
FROM kaiming_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING kaiming_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING kaiming_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- adapter-tuning: 400 links, 1408 exclusions. Local Semantic Scholar citers of 1902.00751 (1721 incl. source) whose title/abstract names adapters in the PEFT sense (LoRA-only, IP-Adapter and modality-connector mentions removed), plus reviewed title/abstract candidates.
CREATE TEMP TABLE adapter_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'adapter-tuning'
  AND p.id IN (
        1803, -- 1902.00751 Parameter-Efficient Transfer Learning for NLP
        3067, -- 2002.01808 K-Adapter: Infusing Knowledge into Pre-Trained Models with Adapters
        3483, -- 2005.00052 MAD-X: An Adapter-Based Framework for Multi-Task Cross-Lingual Transfer
        3489, -- 2005.00247 AdapterFusion: Non-Destructive Task Composition for Transfer Learning
        3895, -- 2007.07779 AdapterHub: A Framework for Adapting Transformers
        4847, -- 2101.00420 Learning to Generate Task-Specific Adapters from Task Description
        5489, -- 2104.08247 What to Pre-Train on? Efficient Intermediate Task Selection
        5917, -- 2106.04489 Parameter-efficient Multi-task Fine-tuning for Transformers via Shared Hypernetw
        5926, -- 2106.04647 Compacter: Efficient Low-Rank Hypercomplex Adapter Layers
        6036, -- 2106.09685 LoRA: Low-Rank Adaptation of Large Language Models
        6536, -- 2109.00904 MultiEURLEX -- A multi-lingual and multi-label legal document classification dat
        6622, -- 2109.06082 xGQA: Cross-Lingual Visual Question Answering
        6784, -- 2110.01518 Generalization in NLI: Ways (Not) To Go Beyond Simple Heuristics
        6934, -- 2110.07280 P-Adapters: Robustly Extracting Factual Information from Language Models with Di
        7075, -- 2110.14943 Semi-Siamese Bi-encoder Neural Ranking Model Using Lightweight Fine-Tuning
        7465, -- 2112.05253 MAGMA -- Multimodal Augmentation of Generative Models through Adapter-based Fine
        7564, -- 2112.09866 Cascading Adaptors to Leverage English Data to Improve Performance of Question A
        7890, -- 2202.03218 Efficient Adapter Transfer of Self-Supervised Speech Models for Automatic Speech
        7908, -- 2202.04173 Exploring the Limits of Domain-Adaptive Training for Detoxifying Large-Scale Lan
        8422, -- 2203.13693 UKP-SQUARE: An Online Platform for Question Answering Research
        8547, -- 2204.01172 PERFECT: Prompt-free and Efficient Few-shot Learning with Language Models
        8573, -- 2204.02292 Parameter-Efficient Neural Reranking for Cross-Lingual and Multilingual Retrieva
        8888, -- 2205.00084 Infusing Linguistic Knowledge of SMILES into Chemical Language Models
        8894, -- 2205.00305 AdapterBias: Parameter-efficient Token-dependent Representation Shift for Adapte
        9113, -- 2205.10835 Multilingual Machine Translation with Hyper-Adapters
        9124, -- 2205.11200 BBTv2: Towards a Gradient-Free Future with Large Language Models
        9150, -- 2205.12148 Hyper-X: A Unified Hypernetwork for Multi-Task Multilingual Transfer
        9163, -- 2205.12410 AdaMix: Mixture-of-Adaptations for Parameter-efficient Model Tuning
        9279, -- 2205.15308 Parameter-Efficient and Student-Friendly Knowledge Distillation
        9430, -- 2206.04673 Neural Prompt Search
        9462, -- 2206.06522 LST: Ladder Side-Tuning for Parameter and Memory Efficient Transfer Learning
        9509, -- 2206.08441 GAAMA 2.0: An Integrated System that Answers Boolean and Extractive Questions
        10180, -- 2208.14559 To Adapt or to Fine-tune: A Case Study on Abstractive Summarization
        10321, -- 2209.08206 Selective Token Generation for Few-shot Natural Language Generation
        10358, -- 2209.09593 EffEval: A Comprehensive Evaluation of Efficiency for MT Evaluation Metrics
        10408, -- 2209.12325 An Empirical Study on Cross-X Transfer for Legal Judgment Prediction
        10612, -- 2210.03255 Damage Control During Domain Adaptation for Transducer Based Automatic Speech Re
        10658, -- 2210.04284 SparseAdapter: An Easy Approach for Improving the Parameter-Efficiency of Adapte
        10679, -- 2210.04829 Hierarchical3D Adapters for Long Video-to-text Summarization
        10745, -- 2210.06175 Exploring Efficient-tuning Methods in Self-supervised Speech Models
        10849, -- 2210.08823 Scaling & Shifting Your Features: A New Baseline for Efficient Model Tuning
        11035, -- 2210.13617 Adapters for Enhanced Modeling of Multilingual Knowledge and Text
        11145, -- 2210.17451 AdaMix: Mixture-of-Adaptations for Parameter-efficient Model Tuning
        11167, -- 2211.00585 Adapter-Based Extension of Multi-Speaker Text-to-Speech Model for New Speakers
        11483, -- 2211.11363 AF Adapter: Continual Pretraining for Building Chinese Biomedical Language Model
        12010, -- 2212.08120 Injecting Domain Knowledge in Language Models for Task-Oriented Dialogue Systems
        12043, -- 2212.08992 PoE: a Panel of Experts for Generalized Automatic Dialogue Assessment
        12073, -- 2212.09535 BLOOM+1: Adding Language Support to BLOOM for Zero-Shot Prompting
        12408, -- 2301.06267 Multimodality Helps Unimodality: Cross-Modal Few-Shot Learning with Multimodal M
        12583, -- 2301.11660 Probing Out-of-Distribution Robustness of Language Models with Parameter-Efficie
        12781, -- 2302.01190 On the Efficacy of Differentially Private Few-shot Image Classification
        12813, -- 2302.01649 Structure-informed Language Models Are Protein Designers
        12997, -- 2302.04870 Offsite-Tuning: Transfer Learning without Full Model
        13071, -- 2302.06605 UniAdapter: Unified Parameter-Efficient Transfer Learning for Cross-modal Modeli
        13150, -- 2302.08453 T2I-Adapter: Learning Adapters to Dig out More Controllable Ability for Text-to-
        13439, -- 2303.01239 MixPHM: Redundancy-Aware Parameter-Efficient Tuning for Low-Resource Visual Ques
        13489, -- 2303.02483 FAME-ViL: Multi-Tasking Vision-Language Model for Heterogeneous Fashion Tasks
        13782, -- 2303.08566 Sensitivity-Aware Visual Parameter-Efficient Fine-Tuning
        13862, -- 2303.09914 Rehearsal-Free Domain Continual Face Anti-Spoofing: Generalize More and Forget L
        13868, -- 2303.10070 A Unified Continual Learning Framework with General Parameter-Efficient Tuning
        14023, -- 2303.12745 Audio-Visual Deception Detection: DOLOS Dataset and Parameter-Efficient Crossmod
        14040, -- 2303.13072 Beyond Universal Transformer: block reusing with adaptor in Transformer for auto
        14052, -- 2303.13310 SwissBERT: The Multilingual Language Model for Switzerland
        14211, -- 2303.15822 One Adapter for All Programming Languages? Adapter Tuning for Code Search and Su
        14231, -- 2303.16199 LLaMA-Adapter: Efficient Fine-tuning of Language Models with Zero-init Attention
        14452, -- 2304.01933 LLM-Adapters: An Adapter Family for Parameter-Efficient Fine-Tuning of Large Lan
        14515, -- 2304.03411 InstantBooth: Personalized Text-to-Image Generation without Test-Time Finetuning
        14599, -- 2304.04947 Conditional Adapters: Parameter-efficient Transfer Learning with Fast Inference
        14779, -- 2304.09148 SAM Fails to Segment Anything? -- SAM-Adapter: Adapting SAM in Underperformed Sc
        15065, -- 2304.15010 LLaMA-Adapter V2: Parameter-Efficient Visual Instruction Model
        15435, -- 2305.06404 LACoS-BLOOM: Low-rank Adaptation with Contrastive objective on 8 bits Siamese-BL
        15490, -- 2305.07490 ArtGPT-4: Towards Artistic-understanding Large Vision-Language Models with Enhan
        15491, -- 2305.07491 A Comprehensive Analysis of Adapter Efficiency
        15948, -- 2305.13406 DADA: Dialect Adaptation via Dynamic Aggregation of Linguistic Rules
        16186, -- 2305.15011 Bactrian-X: Multilingual Replicable Instruction-Following Models with Low-Rank A
        16191, -- 2305.15023 Cheap and Quick: Efficient Vision-Language Instruction Tuning for Large Language
        16349, -- 2305.16651 TADA: Task-Agnostic Dialect Adapters for English
        16353, -- 2305.16724 Code-Switched Text Synthesis in Unseen Language Pairs
        16746, -- 2306.00477 Make Pre-trained Model Reversible: From Parameter to Memory Efficient Fine-Tunin
        16918, -- 2306.02080 Benchmarking Robustness of Adaptation Methods on Pre-trained Vision-Language Mod
        17096, -- 2306.04344 ViDA: Homeostatic Visual Domain Adapter for Continual Test Time Adaptation
        17179, -- 2306.05406 Mixture-of-Domain-Adapters: Decoupling and Injecting Domain Knowledge to Pre-tra
        17382, -- 2306.07967 One-for-All: Generalized LoRA for Parameter-Efficient Fine-tuning
        17713, -- 2306.13465 3DSAM-adapter: Holistic adaptation of SAM from 2D to 3D for promptable tumor seg
        17714, -- 2306.13474 Efficient Online Processing with Deep Neural Networks
        17970, -- 2307.01124 Cross-modality Attention Adapter: A Glioma Segmentation Fine-tuning Method for S
        18057, -- 2307.03042 Parameter-Efficient Fine-Tuning of LLaMA for the Clinical Domain
        18059, -- 2307.03104 Efficient Domain Adaptation of Sentence Embeddings Using Adapters
        18230, -- 2307.07057 Leveraging Pretrained ASR Encoders for Effective and Efficient End-to-End Speech
        18313, -- 2307.08397 CLIP-Guided StyleGAN Inversion for Text-Driven Real Image Editing
        18514, -- 2307.11545 Bridging Vision and Language Encoders: Parameter-Efficient Tuning for Referring
        18807, -- 2307.16867 Revisiting the Parameter Efficiency of Adapters from the Perspective of Precisio
        18832, -- 2308.00398 DriveAdapter: Breaking the Coupling Barrier of Perception and Planning in End-to
        19200, -- 2308.06721 IP-Adapter: Text Compatible Image Prompt Adapter for Text-to-Image Diffusion Mod
        19238, -- 2308.07282 Comparison between parameter-efficient techniques and full fine-tuning: A case s
        19434, -- 2308.09710 SimDA: Simple Diffusion Adapter for Efficient Video Generation
        19443, -- 2308.09804 VL-PET: Vision-and-Language Parameter-Efficient Tuning via Granularity Control
        19712, -- 2308.12372 Vision Transformer Adapters for Generalizable Multitask Learning
        19937, -- 2308.15982 MerA: Merging Pretrained Adapters For Few-Shot Learning
        20071, -- 2309.01479 Parameter and Computation Efficient Transfer Learning for Vision-Language Pre-tr
        20072, -- 2309.01516 MultiWay-Adapater: Adapting large-scale multi-modal models for scalable image-te
        20187, -- 2309.03696 Efficient Adaptive Human-Object Interaction Detection with Concept-guided Memory
        20339, -- 2309.06526 Exploring the Benefits of Differentially Private Pre-training and Parameter-Effi
        20365, -- 2309.06922 Hydra: Multi-head Low-rank Adaptation for Parameter Efficient Fine-tuning
        20537, -- 2309.09298 OWL: A Large Language Model for IT Operations
        20874, -- 2309.13994 Unsupervised Accent Adaptation Through Masked Language Model Correction Of Discr
        21136, -- 2310.00230 SLM: Bridge the thin gap between speech and text foundation models
        21227, -- 2310.01217 ScaLearn: Simple and Highly Parameter-Efficient Task Transfer by Learning to Sca
        21236, -- 2310.01324 ZeroI2V: Zero-Cost Adaptation of Pre-trained Transformers from Image to Video
        21412, -- 2310.03059 Point-PEFT: Parameter-Efficient Fine-Tuning for 3D Pre-trained Models
        21630, -- 2310.05592 InterroLang: Exploring NLP Models and Datasets through Dialogue-based Explanatio
        21662, -- 2310.05905 TAIL: Task-specific Adapters for Imitation Learning with Large Pretrained Models
        22143, -- 2310.11670 Prototype-based HyperAdapter for Sample-Efficient Multi-task Tuning
        22247, -- 2310.13015 Audio-AdapterFusion: A Task-ID-free Approach for Efficient and Non-Destructive M
        22263, -- 2310.13225 Scalable Neural Network Kernels
        22285, -- 2310.13448 Steering Large Language Models for Machine Translation with Finetuning and In-Co
        22511, -- 2310.16240 Mixture-of-Linguistic-Experts Adapters for Improving and Interpreting Pre-traine
        22634, -- 2310.17743 StyleBART: Decorate Pretrained Model with Style Adapters for Unsupervised Stylis
        22848, -- 2311.00408 AdaSent: Efficient Domain-Adapted Sentence Embeddings for Few-Shot Classificatio
        22996, -- 2311.03285 S-LoRA: Serving Thousands of Concurrent LoRA Adapters
        23332, -- 2311.08590 PEMA: An Offsite-Tunable Plug-in External Memory Adaptation for Language Models
        23511, -- 2311.11077 Adapters: A Unified Library for Parameter-Efficient and Modular Transfer Learnin
        24306, -- 2312.02923 MoSA: Mixture of Sparse Adapters for Visual Efficient Tuning
        24335, -- 2312.03154 ViscoNet: Bridging and Harmonizing Visual and Textual Conditioning for ControlNe
        24371, -- 2312.03687 MatterGen: a generative model for inorganic materials design
        24373, -- 2312.03694 Parameter-Efficient Transfer Learning of Audio Spectrogram Transformers
        24381, -- 2312.03732 A Rank Stabilization Scaling Factor for Fine-Tuning with LoRA
        24551, -- 2312.05677 Batched Low-Rank Adaptation of Foundation Models
        24893, -- 2312.10613 p-Laplacian Adaptation for Generative Pre-trained Vision-Language Models
        25439, -- 2401.01736 Few-shot Adaptation of Multi-modal Foundation Models: A Survey
        25510, -- 2401.02731 Parameter-Efficient Sparsity Crafting from Dense to Mixture-of-Experts for Instr
        25918, -- 2401.08992 Efficient Adapter Finetuning for Tail Languages in Streaming Multilingual ASR
        26103, -- 2401.11649 M2-CLIP: A Multimodal, Multi-task Adapting Framework for Video Action Recognitio
        26208, -- 2401.13051 PA-SAM: Prompt Adapter SAM for High-Quality Image Segmentation
        26553, -- 2402.00149 The Impact of Language Adapters in Cross-Lingual Transfer for NLU
        26596, -- 2402.00828 Efficient Fine-tuning of Audio Spectrogram Transformers via Soft Mixture of Adap
        26716, -- 2402.01911 From PEFT to DEFT: Parameter Efficient Finetuning for Reducing Activation Densit
        26873, -- 2402.03631 CAT-SAM: Conditional Tuning for Few-Shot Adaptation of Segment Anything Model
        27152, -- 2402.06967 Instruct Once, Chat Consistently in Multiple Rounds: An Efficient Tuning Framewo
        27496, -- 2402.11417 LoRETTA: Low-Rank Economic Tensor-Train Adaptation for Ultra-Low-Parameter Fine-
        27541, -- 2402.11764 ChatGPT Based Data Augmentation for Improved Parameter-Efficient Debiasing of LL
        27605, -- 2402.12354 LoRA+: Efficient Low Rank Adaptation of Large Models
        27675, -- 2402.13137 The Hidden Space of Transformer Language Adapters
        27804, -- 2402.14505 Towards Seamless Adaptation of Pre-trained Models for Visual Place Recognition
        27929, -- 2402.15823 Parameter-efficient Prompt Learning for 3D Point Cloud Understanding
        28359, -- 2403.02084 ResAdapter: Domain Consistent Resolution Adapter for Diffusion Models
        28626, -- 2403.06136 RESTORE: Towards Feature Shift for Vision-Language Prompt Learning
        28854, -- 2403.09377 Introducing Routing Functions to Vision-Language Parameter-Efficient Fine-Tuning
        29038, -- 2403.11808 Dynamic Tuning Towards Parameter and Inference Efficiency for ViT Adaptation
        29067, -- 2403.12030 Expandable Subspace Ensemble for Pre-Trained Model-Based Class-Incremental Learn
        29191, -- 2403.13535 IDAdapter: Learning Mixed Features for Tuning-Free Personalization of Text-to-Im
        29461, -- 2403.17369 CoDA: Instructive Chain-of-Domain Adaptation with Severity-Aware Visual Prompt T
        29562, -- 2403.18783 Towards a World-English Language Model for On-Device Virtual Assistants
        29654, -- 2403.19979 Semantically-Shifted Incremental Adapter-Tuning is A Continual ViTransformer
        29782, -- 2404.01253 UniArk: Improving Generalisation and Consistency for Factual Knowledge Extractio
        29806, -- 2404.01430 Position-Aware Parameter Efficient Fine-Tuning Approach for Reducing Positional
        29909, -- 2404.02948 PiSSA: Principal Singular Values and Singular Vectors Adaptation of Large Langua
        30148, -- 2404.06448 Automated Federated Pipeline for Parameter-Efficient Fine-Tuning of Large Langua
        30216, -- 2404.07554 CAT: Contrastive Adapter Training for Personalized Image Generation
        30254, -- 2404.07989 Any2Point: Empowering Any-modality Large Models for Efficient 3D Understanding
        30281, -- 2404.08417 AdapterSwap: Continuous Training of LLMs with Data Removal and Access-Control Gu
        30384, -- 2404.09967 Ctrl-Adapter: An Efficient and Versatile Framework for Adapting Diverse Controls
        30577, -- 2404.12845 TartuNLP @ SIGTYP 2024 Shared Task: Adapting XLM-RoBERTa for Ancient and Histori
        30822, -- 2404.17360 UniRGB-IR: A Unified Framework for RGB-Infrared Semantic Tasks via Adapter Tunin
        31007, -- 2405.01159 TartuNLP at EvaLatin 2024: Emotion Polarity Detection
        31184, -- 2405.06196 VLSM-Adapter: Finetuning Vision-Language Segmentation Efficiently with Lightweig
        31400, -- 2405.11157 Towards Modular LLMs by Building and Reusing a Library of LoRAs
        31544, -- 2405.13952 Spectral Adapter: Fine-Tuning in Spectral Space
        31648, -- 2405.15007 RE-Adapt: Reverse Engineered Adaptation of Large Language Models
        31938, -- 2405.18380 OwLore: Outlier-weighed Layerwise Sampled Low-Rank Projection for Memory-Efficie
        31957, -- 2405.18541 Low-Rank Few-Shot Adaptation of Vision-Language Models
        32527, -- 2406.05223 CorDA: Context-Oriented Decomposition Adaptation of Large Language Models for Ta
        32676, -- 2406.07007 Crayon: Customized On-Device LLM via Instant Adapter Blending and Edge-Server Hy
        32747, -- 2406.07686 AV-DiT: Efficient Audio-Visual Diffusion Transformer for Joint Audio and Video G
        32916, -- 2406.09617 Multimodal Large Language Models with Fusion Low Rank Adaptation for Device Dire
        33468, -- 2406.15007 RouteFinder: Towards Foundation Models for Vehicle Routing Problems
        33676, -- 2406.17740 Structured Unrestricted-Rank Matrices for Parameter Efficient Fine-tuning
        33707, -- 2406.18060 AdaZeta: Adaptive Zeroth-Order Tensor-Train Adaption for Memory-Efficient Large
        34027, -- 2407.02157 FineCLIPER: Multi-modal Fine-grained CLIP for Dynamic Facial Expression Recognit
        34148, -- 2407.03861 TartuNLP @ AXOLOTL-24: Leveraging Classifier Output for New Sense Detection in L
        34251, -- 2407.05311 MMAD: Multi-label Micro-Action Detection in Videos
        34456, -- 2407.08056 Pareto Low-Rank Adapters: Efficient Multi-Task Learning with Preferences
        34957, -- 2407.14143 Class-Incremental Learning with CLIP: Adaptive Representation Adjustment and Par
        35186, -- 2407.17813 Enhancing Model Performance: Another Approach to Vision-Language Instruction Tun
        35412, -- 2408.00181 CC-SAM: SAM with Cross-feature Attention and Context for Ultrasound Image Segmen
        35730, -- 2408.05749 Efficient and Versatile Robust Fine-Tuning of Zero-shot Models
        35775, -- 2408.06610 CROME: Cross-Modal Adapters for Efficient Multimodal LLM
        35836, -- 2408.07500 Cross-Platform Video Person ReID: A New Benchmark Dataset and Adaptation Approac
        36264, -- 2408.14802 RAW-Adapter: Adapting Pre-trained Visual Model to Camera RAW Images
        36424, -- 2409.00055 SORSA: Singular Values and Orthonormal Regularized Singular Vectors Adaptation o
        36431, -- 2409.00119 3-in-1: 2D Rotary Adaptation for Efficient Finetuning, Efficient Batching and Co
        36591, -- 2409.02958 Multi-Modal Adapter for Vision-Language Models
        36741, -- 2409.06656 Sortformer: Seamless Integration of Speaker Diarization and ASR by Bridging Time
        36975, -- 2409.11051 Down-Sampling Inter-Layer Adapter for Parameter and Computation Efficient Ultra-
        37065, -- 2409.12421 Frequency-Guided Spatial Adaptation for Camouflaged Object Detection
        38022, -- 2410.05270 Fine-Tuning CLIP's Last Visual Projector: A Few-Shot Cornucopia
        38257, -- 2410.08114 Parameter-Efficient Fine-Tuning in Spectral Domain for Point Cloud Learning
        38510, -- 2410.11160 MANet: Fine-Tuning Segment Anything Model for Multimodal Remote Sensing Semantic
        38817, -- 2410.14633 Swiss Army Knife: Synergizing Biases in Knowledge from Vision Foundation Models
        39816, -- 2411.05877 Generative Adapter: Contextualizing Language Models in Parameters with A Single
        39843, -- 2411.06399 PSELDNets: Pre-trained Neural Networks on Large-scale Synthetic Datasets for Sou
        40195, -- 2411.13127 Adapting Vision Foundation Models for Robust Cloud Segmentation in Remote Sensin
        40532, -- 2411.17646 SAMWISE: Infusing Wisdom in SAM2 for Text-Driven Video Segmentation
        41221, -- 2412.06289 S$^{2}$FT: Efficient, Scalable and Generalizable LLM Fine-tuning by Structured S
        41738, -- 2412.12674 Train More Parameters But Mind Their Placement: Insights into Language Adaptatio
        42423, -- 2501.01347 AdaptVC: High Quality Voice Conversion with Adaptive Learning
        42450, -- 2501.01765 SaLoRA: Safety-Alignment Preserved Low-Rank Adaptation
        42770, -- 2501.06892 Language Fusion for Parameter-Efficient Cross-lingual Transfer
        43214, -- 2501.14713 FlexiGPT: Pruning and Extending Large Language Models with Low-Rank Weight Shari
        43817, -- 2502.04700 EigenLoRAx: Recycling Adapters to Find Principal Subspaces for Resource-Efficien
        44197, -- 2502.10140 Small Models, Big Impact: Efficient Corpus and Graph-Based Adaptation of Small M
        45609, -- 2503.05315 LoRACode: LoRA Adapters for Code Embeddings
        45776, -- 2503.07274 Efficient Distillation of Classifier-Free Guidance using Adapters
        46577, -- 2503.17735 RDTF: Resource-efficient Dual-mask Training Framework for Multi-frame Animated S
        46976, -- 2503.23083 Efficient Adaptation For Remote Sensing Visual Grounding
        47428, -- 2504.06220 Earth-Adapter: Bridge the Geospatial Domain Gaps with Mixture of Frequency Adapt
        47485, -- 2504.07448 LoRI: Reducing Cross-Task Interference in Multi-Task Low-Rank Adaptation
        49651, -- 2505.18777 HD-PiSSA: High-Rank Distributed Orthogonal Adaptation
        49933, -- 2505.21289 LoFT: Low-Rank Adaptation That Behaves Like Full Fine-Tuning
        50517, -- 2506.03525 Video-Skill-CoT: Skill-based Chain-of-Thoughts for Domain-Adaptive Video Reasoni
        50694, -- 2506.05928 MoA: Heterogeneous Mixture of Adapters for Parameter-Efficient Fine-Tuning of La
        51242, -- 2506.14824 FedNano: Toward Lightweight Federated Tuning for Pretrained Multimodal Large Lan
        51506, -- 2506.21298 Exploring Adapter Design Tradeoffs for Low Resource Music Generation
        53762, -- 2510.19316 KORE: Enhancing Knowledge Injection for Large Multimodal Models via Knowledge-Or
        54677, -- 2512.04763 MemLoRA: Distilling Expert Adapters for On-Device Memory Systems
        54899, -- 2512.12880 Improving Recursive Transformers with Mixture of LoRAs
        56573, -- 2603.08648 CAST: Modeling Visual State Transitions for Consistent Video Retrieval
        56613, -- 2603.09221 Beyond Test-Time Training: Learning to Reason via Hardware-Efficient Optimal Con
        56848, -- 2603.16653 HeBA: Heterogeneous Bottleneck Adapters for Robust Vision-Language Models
        56849, -- 2603.14706 AdapterTune: Zero-Initialized Low-Rank Adapters for Frozen Vision Transformers
        57753, -- 2604.24040 Improving Robustness of Tabular Retrieval via Representational Stability
        58891, -- 2603.25945 Adapting Segment Anything Model 3 for Concept-Driven Lesion Segmentation in Medi
        59769, -- 2603.06492 NOBLE: Accelerating Transformers with Nonlinear Low-Rank Branches
        61888, -- 2601.20845 PatchFormer: A Patch-Based Time Series Foundation Model with Hierarchical Masked
        62988, -- 2601.02273 TopoLoRA-SAM: Topology-Aware Parameter-Efficient Adaptation of Foundation Segmen
        63971, -- 2512.07703 PVeRA: Probabilistic Vector-Based Random Matrix Adaptation
        64651, -- 2511.19425 SAM3-Adapter: Efficient Adaptation of Segment Anything 3 for Camouflage Object S
        64705, -- 2511.17979 FeRA: Frequency-Energy Constrained Routing for Effective Diffusion Adaptation Fi
        65360, -- 2511.04008 GNN-MoE: Context-Aware Patch Routing using GNNs for Parameter-Efficient Domain G
        66394, -- 2510.13259 Hypernetworks for Perspectivist Adaptation
        66604, -- 2510.10022 Q-Adapter: Visual Query Adapter for Extracting Textually-related Features in Vid
        66701, -- 2510.08513 SliceFine: The Universal Winning-Slice Hypothesis for Pretrained Networks
        66891, -- 2510.05715 AgeBooth: Controllable Facial Aging and Rejuvenation via Diffusion Models
        67702, -- 2509.22158 Context Parametrization with Compositional Adapters
        68006, -- 2509.17816 Enhancing Semantic Segmentation with Continual Self-Supervised Pre-training
        68137, -- 2509.15888 Distribution-Aligned Decoding for Efficient LLM Task Adaptation
        68408, -- 2509.11414 Continually Adding New Languages to Multilingual Language Models
        68483, -- 2509.09572 PeftCD: Leveraging Vision Foundation Models with Parameter-Efficient Fine-Tuning
        69689, -- 2508.10352 Cross-Prompt Encoder for Low-Performing Languages
        69871, -- 2508.07819 Architectural Co-Design for Zero-Shot Anomaly Detection: Decoupling Representati
        70189, -- 2508.03527 MoKA: Mixture of Kronecker Adapters
        70963, -- 2507.14904 TriCLIP-3D: A Unified Parameter-Efficient Framework for Tri-Modal 3D Visual Grou
        70985, -- 2507.14613 Depthwise-Dilated Convolutional Adapters for Medical Object Tracking and Segment
        71402, -- 2507.04453 ESSA: Evolutionary Strategies for Scalable Alignment
        71632, -- 2312.01431 D^2ST-Adapter: Disentangled-and-Deformable Spatio-Temporal Adapter for Few-shot
        71763, -- 2506.19140 Command-V: Pasting LLM Behaviors via Activation Profiles
        71978, -- 2506.12704 Flexible Realignment of Language Models
        72219, -- 2506.05713 Come Together, But Not Right Now: A Progressive Strategy to Boost Low-Rank Adapt
        73514, -- 2504.10307 CROSSAN: Towards Efficient and Effective Adaptation of Multiple Multimodal Found
        74513, -- 2502.16601 SelaVPR++: Towards Seamless Adaptation of Foundation Models for Efficient Place
        74592, -- 2502.13999 DP-Adapter: Dual-Pathway Adapter for Boosting Fidelity and Text Consistency in C
        74622, -- 2502.12502 Efficient OpAmp Adaptation for Zoom Attention to Golden Contexts
        74678, -- 2502.10705 CoPEFT: Fast Adaptation Framework for Multi-Agent Collaborative Perception with
        74990, -- 2502.00630 Self-Prompt SAM: Medical Image Segmentation via Automatic Prompt SAM Adaptation
        75020, -- 2502.00089 Ensembles of Low-Rank Expert Adapters
        76250, -- 2409.19457 A Parameter-Efficient Tuning Framework for Language-guided Object Grounding and
        76515, -- 2408.14470 Step-by-Step Unmasking for Parameter-Efficient Fine-tuning of Large Language Mod
        76571, -- 2408.09397 Combo: Co-speech holistic 3D human motion generation and efficient customizable
        76834, -- 2407.02317 Soft Language Prompts for Language Transfer
        77512, -- 2404.02059 IISAN: Efficiently Adapting Multimodal Representation for Sequential Recommendat
        77559, -- 2403.18886 Self-Expansion of Pre-trained Models with Mixture of Adapters for Continual Lear
        78035, -- 2312.16649 Forgery-aware Adaptive Transformer for Generalizable Synthetic Image Detection
        78187, -- 2311.17241 End-to-End Temporal Action Detection with 1B Parameters Across 1000 Frames
        78391, -- 2310.07423 Adapting the adapters for code-switching in multilingual ASR
        78625, -- 2308.12305 FedDAT: An Approach for Foundation Model Finetuning in Multi-Modal Heterogeneous
        78992, -- 2305.15036 Exploring Adapter-based Transfer Learning for Recommender Systems: Empirical Stu
        79265, -- 2303.06233 Model-Agnostic Syntactical Information for Pre-Trained Programming Language Mode
        79972, -- 2205.08534 Vision Transformer Adapter for Dense Predictions
        80458, -- 2110.04544 CLIP-Adapter: Better Vision-Language Models with Feature Adapters
        82896, -- 2605.06477 GeoStack: A Framework for Quasi-Abelian Knowledge Composition in VLMs
        83706, -- 2605.24675 VaaWIT: Visual-Aware Adaptation of Large Language Models for Multilingual Web Im
        84965, -- 2603.18101 Training-Only Heterogeneous Image-Patch-Text Graph Supervision for Advancing Few
        85148, -- 2603.26317 Label-Free Cross-Task LoRA Merging with Null-Space Compression
        85698, -- 2510.01938 StelLA: Subspace Learning in Low-rank Adaptation using Stiefel Manifold
        85831, -- 2502.03604 Bilevel ZOFO: Efficient LLM Fine-Tuning and Meta-Training
        86598, -- 2507.02085 GeoAda: Efficiently Finetune Geometric Diffusion Models with Equivariant Adapter
        86909, -- 2410.01508 Disentangling Latent Shifts of In-Context Learning with Weak Supervision
        87538, -- 2507.13260 Efficient Adaptation of Pre-trained Vision Transformer underpinned by Approximat
        87596, -- 2408.14961 CVPT: Cross Visual Prompt Tuning
        87607, -- 2502.01289 A Framework for Double-Blind Federated Adaptation of Foundation Models
        87817, -- 2510.03701 Referring Expression Comprehension for Small Objects
        87919, -- 2507.19908 TrackAny3D: Transferring Pretrained 3D Models for Category-unified 3D Point Clou
        88020, -- 2403.14103 MaskSAM: Auto-prompt SAM with Mask Classification for Volumetric Medical Image S
        88588, -- 2410.02744 Neutral residues: revisiting adapters for model extension
        88931, -- 2502.13811 On the Duality between Gradient Transformations and Adapters
        89493, -- 2502.03029 On Zero-Initialized Attention: Optimal Prompt and Gating Factor Estimation
        89634, -- 2505.23271 LADA: Scalable Label-Specific CLIP Adapter for Continual Learning
        90019, -- 2506.07376 Adapter Naturally Serves as Decoupler for Cross-Domain Few-Shot Semantic Segment
        90248, -- 2505.20941 PMA: Towards Parameter-Efficient Point Cloud Understanding via Point Mamba Adapt
        90265, -- 2411.19041 TAMT: Temporal-Aware Model Tuning for Cross-Domain Few-Shot Action Recognition
        90342, -- 2408.08345 5%>100%: Breaking Performance Shackles of Full Fine-Tuning on Visual Recognition
        90545, -- 2409.14983 Dynamic Integration of Task-Specific Adapters for Class Incremental Learning
        90636, -- 2503.20282 Faster Parameter-Efficient Tuning with Token Redundancy Reduction
        90704, -- 2411.11223 Efficient Transfer Learning for Video-language Foundation Models
        90827, -- 2504.16023 PointLoRA: Low-Rank Adaptation with Token Selection for Point Cloud Learning
        90998, -- 2503.18368 MoST: Efficient Monarch Sparse Tuning for 3D Representation Learning
        91253, -- 2410.18720 GeoLoRA: Geometric integration for parameter efficient fine-tuning
        91637, -- 2503.17221 UniCon: Unidirectional Information Flow for Effective Control of Large-Scale Dif
        93096, -- 2602.18888 Dual-Kernel Adapter: Expanding Spatial Horizons for Data-Constrained Medical Ima
        93369, -- 2510.14301 A Guardrail for Safety Preservation: When Safety-Sensitive Subspace Meets Harmfu
        94060, -- 2507.05394 pFedMMA: Personalized Federated Fine-Tuning with Multi-Modal Adapter for Vision-
        94486, -- 2510.14543 Exploring Cross-Modal Flows for Few-Shot Learning
        94951, -- 2601.20280 The Forecast After the Forecast: A Post-Processing Shift in Time Series
        96130, -- 2509.14966 RoboEye: Enhancing 2D Robotic Object Identification with Selective 3D Geometric
        96628, -- 2508.01592 DMTrack: Spatio-Temporal Multimodal Tracking Via Dual-Adapter
        96820, -- 2603.04050 HE-VPR: Height Estimation Enabled Aerial Visual Place Recognition against Scale
        97984, -- 2606.07334 How Far Can Chord-Symbol Time-Series Adaptation Carry Genre Identity? Capabiliti
        99075, -- 2607.02512 Program-as-Weights: A Programming Paradigm for Fuzzy Functions
        99373, -- 2602.06862 Parameters as Experts: Adapting Vision Models with Dynamic Parameter Routing
        99857, -- 2602.01267 Diving into Kronecker Adapters: Component Design Matters
        100531, -- 2602.03846 PLATE: Plasticity-Tunable Efficient Adapters for Geometry-Aware Continual Learni
        102079, -- 2602.06204 Learning Rate Scaling across LoRA Ranks and Transfer to Full Finetuning
        102418, -- 2602.21716 TranX-Adapter: Bridging Artifacts and Semantics within MLLMs for Robust AI-gener
        103126, -- 2604.06819 Beyond End-to-End: Dynamic Chain Optimization for Private LLM Adaptation on the
        103154, -- 2604.19042 STK-Adapter: Incorporating Evolving Graph and Event Chain for Temporal Knowledge
        103243, -- 2510.16282 Instant Personalized Large Language Model Adaptation via Hypernetwork
        103589, -- 2511.07129 LoRA on the Go: Instance-level Dynamic LoRA Selection and Merging
        105357, -- 2506.19118 LKA: Large Kernel Adapter for Enhanced Medical Image Classification
        105641, -- 2501.03722 Self-adaptive Vision-Language Model for 3D Segmentation of Pulmonary Artery and
        106484, -- 2511.06859 TuckA: Hierarchical Compact Tensor Experts for Efficient Fine-Tuning
        106646, -- 2512.11366 qa-FLoRA: Data-free query-adaptive Fusion of LoRAs for LLMs
        106710, -- 2504.08915 Parameter-Free Fine-tuning via Redundancy Elimination for Vision Foundation Mode
        107019, -- 2410.23736 Modality and Task Adaptation for Enhanced Zero-shot Composed Image Retrieval
        107124, -- 2601.07139 AdaField: Generalizable Surface Pressure Modeling with Physics-Informed Pre-trai
        107197, -- 2511.09870 SAM-DAQ: Segment Anything Model with Depth-guided Adaptive Queries for RGB-D Vid
        107274, -- 2505.21895 SineLoRA∆: Sine-Activated Delta Compression
        107587, -- 2511.06696 Magnitude-Modulated Equivariant Adapter for Parameter-Efficient Fine-Tuning of E
        107645, -- 2402.01124 TransFR: Transferable Federated Recommendation with Adapter Tuning on Pre-traine
        107908, -- 2601.06429 A Unified Shape-Aware Foundation Model for Time Series Classification
        109197, -- 2501.16542 UniPET-SPK: A Unified Framework for Parameter-Efficient Tuning of Pre-trained Sp
        109431, -- 2409.06154 Static for Dynamic: Towards a Deeper Understanding of Dynamic Facial Expressions
        109432, -- 2312.05447 From Static to Dynamic: Adapting Landmark-Aware Image Models for Facial Expressi
        110630, -- 2510.25784 zFLoRA: Zero-Latency Fused Low-Rank Adapters
        111418, -- external Parameter-Efficient Fine-tuning with Instance-Aware Prompt and Parallel Adapters
        111454, -- external Fine-tuning Strategies for Automatic Speech Recognition of Low-Resource Speech w
        111584, -- external Leveraging Multi-Level Features of ATST with Conformer-Based Dual-Branch Network
        112855, -- 2407.13974 Continual Learning for Remote Physiological Measurement: Minimize Forgetting and
        112964, -- 2407.06871 Rethinking Image-to-Video Adaptation: An Object-centric Perspective
        113083, -- 2312.04763 Enhancing Recipe Retrieval with Foundation Models: A Data Augmentation Perspecti
        113094, -- 2407.09853 Image Compression for Machine and Human Vision With Spatial-Frequency Adaptation
        113273, -- 2408.02840 GAReT: Cross-view Video Geolocalization with Adapters and Auto-Regressive Transf
        113440, -- 2407.14302 Dyn-Adapter: Towards Disentangled Representation for Efficient Visual Recognitio
        113653, -- 2407.10281 Beyond Prompt Learning: Continual Adapter for Efficient Rehearsal-Free Continual
        113938, -- 2609.04199 Compile by Training: Turning Natural-Language Specifications into Local Neural F
        115022, -- external InstaSAM: Instance-aware Segment Any Nuclei Model with Point Annotations
        115545, -- 2404.00913 LLaMA-Excitor: General Instruction Tuning via Indirect Feature Interaction
        115568, -- 2403.01439 Dynamic Adapter Meets Prompt Tuning: Parameter-Efficient Transfer Learning for P
        115613, -- 2404.04996 Fantastic Animals and Where to Find Them: Segment Any Marine Animal with Dual SA
        115677, -- 2403.19811 X-MIC: Cross-Modal Instance Conditioning for Egocentric Action Generalization
        116063, -- 2302.06637 PerAda: Parameter-Efficient Federated Learning Personalization with Generalizati
        116179, -- 2406.06820 Adapters Strike Back
        116268, -- 2404.04624 Bridging the Gap Between End-to-End and Two-Step Text Spotting
        116478, -- 2309.15785 BT-Adapter: Video Conversation is Feasible Without Video Instruction Tuning
        116502, -- 2403.11549 Boosting Continual Learning of Vision-Language Models via Mixture-of-Experts Ada
        116526, -- 2403.16002 SDSTrack: Self-Distillation Symmetric Adapter Learning for Multi-Modal Visual Ob
        116802, -- 2402.18490 TAMM: TriAdapter Multi-Modal Learning for 3D Shape Understanding
        116854, -- 2312.16279 Cloud-Device Collaborative Learning for Multimodal Large Language Models
        116995, -- 2402.07739 Task-Conditioned Adaptation of Visual Features in Multi-Task Policy Learning
        118202, -- 2607.00338 DroneFINE: Domain-Aware Parameter-Efficient Fine-Tuning of Vision-Language Detec
        118537, -- 2606.20971 UNITY: Attention Flow Networks for Adaptive Conditioning in Diffusion
        119520, -- 2606.22383 Structured Hyperedge Adaptation for Parameter-Efficient Fine-Tuning of Vision Tr
        119616, -- 2606.29579 ScAle: Attention Head Scaling as a Minimal Adapter for Spatial Reasoning in Visi
        119926, -- 2408.17065 Generalizing Deepfake Video Detection with Plug-and-Play: Video-Level Blending a
        120023, -- external Adapting Text-to-Image Generation with Feature Difference Instruction for Generi
        120107, -- 2506.04453 Gradient Inversion Attacks on Parameter-Efficient Fine-Tuning
        120182, -- 2406.17559 Minimal Interaction Seperated Tuning: A New Paradigm for Visual Adaptation
        120234, -- 2411.11912 F^3OCUS - Federated Finetuning of Vision-Language Foundation Models with Optimal
        120335, -- 2505.12685 Mamba-Adaptor: State Space Model Adaptor for Visual Recognition
        120462, -- 2505.24816 CL-LoRA: Continual Low-Rank Adaptation for Rehearsal-Free Class-Incremental Lear
        120995, -- external Representation-Steered Incremental Adapter-Tuning for Class-Incremental Learning
        121022, -- external Depth Any Endoscopy: Towards Self-Supervised Generalizable Depth Estimation in M
        123647, -- 2302.08106 Towards Efficient Visual Adaption via Structural Re-parameterization
        123648, -- 2207.07039 Convolutional Bypasses Are Better Vision Transformer Adapters
        123651, -- 2310.06234 Efficient Adaptation of Large Vision Transformer via Adapter Re-Composing
        123653, -- 2305.00603 Consolidator: Mergeable Adapter with Grouped Connections for Visual Adaptation
        123709, -- 2610.20019 MorphAct: Robot Policies Morphing with the Worlds They Act In
        124389, -- external Adapting Vision Transformers to Organoid Imaging
        124443, -- external DAGA: Dynamic Attention-Guided Adaptation for Self-Supervised Vision Transformer
        124736, -- 2512.01675 GRASP: Guided Residual Adapters with Sample-wise Partitioning
        125634, -- 2605.06127 Continuous Expert Assembly: Instance-Conditioned Low-Rank Residuals for All-in-O
        125867, -- 2605.21147 SMoA: Spectrum Modulation Adapter for Parameter-Efficient Fine-Tuning
        126786, -- 2605.10741 AdaPaD: Adaptive Parallel Deflation for PEFT with Self-Correcting Rank Discovery
        127309, -- 2605.10337 CORTEG: Foundation Models Enable Cross-Modality Representation Transfer from Sca
        127470, -- 2609.39445 Raw-Routed Mixture of Adapters: A Causal Intervention for Routing Collapse in Ti
        127638, -- 2607.02711 RayTun3R: Online Camera Adaptation in 3D Foundation Models
        128909, -- external Phase-wise MLLM Tuning for Multi-framework WebUI Code Generation
        129279, -- 2605.10136 Per-Loss Adapters for Gradient Conflict in Physics-Informed Neural Networks
        129635, -- external Ferrogen: Generative Pipeline for Guided Search of Novel Ferroelectric Material
        130062, -- 2510.16014 STAR: Boosting Time Series Foundation Models for Anomaly Detection Through State
        130528  -- 2606.14222 Learning the Context of Errors: Black-Box Online Adaptation of Time Series Found
  );

DELETE FROM paper_method_exclusions x
USING adapter_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM adapter_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM adapter_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE adapter_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'adapter-tuning'
  AND p.id IN (
        1582, -- 1810.13306 Automated Machine Learning: From Principles to Practices
        2715, -- 1910.10683 Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transforme
        2730, -- 1910.11856 On the Cross-lingual Transferability of Monolingual Representations
        2782, -- 1911.03090 What Would Elsa Do? Freezing Layers During Transformer Fine-Tuning
        2788, -- 1911.03437 SMART: Robust and Efficient Fine-Tuning for Pre-trained Natural Language Models
        2795, -- 1911.03882 Pre-train and Plug-in: Flexible Conditional Text Generation with Variational Aut
        3230, -- 2003.08271 Pre-trained Models for Natural Language Processing: A Survey
        3417, -- 2004.12406 Masking as an Efficient Alternative to Finetuning for Pretrained Language Models
        3693, -- 2006.05987 Revisiting Few-sample BERT Fine-tuning
        4143, -- 2009.06732 Efficient Transformers: A Survey
        4242, -- 2010.00980 MultiCQA: Zero-Shot Transfer of Self-Supervised Text Matching Models on a Massiv
        4345, -- 2010.06467 Pretrained Transformers for Text Ranking: BERT and Beyond
        4402, -- 2010.11125 Beyond English-Centric Multilingual Machine Translation
        4411, -- 2010.11784 Self-Alignment Pretraining for Biomedical Entity Representations
        4643, -- 2012.00363 Modifying Memories in Transformer Models
        4735, -- 2012.07463 Parameter-Efficient Transfer Learning with Diff Pruning
        4784, -- 2012.13255 Intrinsic Dimensionality Explains the Effectiveness of Language Model Fine-Tunin
        4820, -- 2012.15562 UNKs Everywhere: Adapting Multilingual Language Models to New Scripts
        4822, -- 2012.15613 How Good is Your Tokenizer? On the Monolingual Performance of Multilingual Langu
        4833, -- 2101.00121 WARP: Word-level Adversarial ReProgramming
        4835, -- 2101.00190 Prefix-Tuning: Optimizing Continuous Prompts for Generation
        5027, -- 2102.06551 A Little Pretraining Goes a Long Way: A Case Study on Dependency Parsing Task fo
        5163, -- 2103.05247 Pretrained Transformers as Universal Computation Engines
        5204, -- 2103.08466 NADI 2021: The Second Nuanced Arabic Dialect Identification Shared Task
        5324, -- 2103.16716 BASE Layers: Simplifying Training of Large, Sparse Models
        5490, -- 2104.08253 Condenser: a Pre-training Architecture for Dense Retrieval
        5509, -- 2104.08691 The Power of Scale for Parameter-Efficient Prompt Tuning
        5519, -- 2104.08771 Cross-Attention is All You Need: Adapting Pretrained Transformers for Machine Tr
        5577, -- 2104.12250 XLM-T: Multilingual Language Models in Twitter for Sentiment Analysis and Beyond
        5589, -- 2104.12928 If your data distribution shifts, use self-learning
        6049, -- 2106.10199 BitFit: Simple Parameter-efficient Fine-tuning for Transformer-based Masked Lang
        6280, -- 2107.09622 More Parameters? No Thanks!
        6404, -- 2108.05036 DEMix Layers: Disentangling Domains for Modular Language Modeling
        6534, -- 2109.00720 LightNER: A Lightweight Tuning Paradigm for Low-resource NER via Pluggable Promp
        6776, -- 2110.00806 Swiss-Judgment-Prediction: A Multilingual Legal Judgment Prediction Benchmark
        6854, -- 2110.04366 Towards a Unified View of Parameter-Efficient Transfer Learning
        6877, -- 2110.05679 Large Language Models Can Be Strong Differentially Private Learners
        6901, -- 2110.06274 LiST: Lite Prompted Self-training Makes Parameter-Efficient Few-shot Learners
        6941, -- 2110.07560 Composable Sparse Fine-Tuning for Cross-Lingual Transfer
        6961, -- 2110.08118 Few-Shot Bot: Prompt-Based Learning for Dialogue Systems
        6972, -- 2110.08329 Control Prefixes for Parameter-Efficient Text Generation
        6984, -- 2110.08534 Lifelong Pretraining: Continually Adapting Language Models to Emerging Corpora
        7049, -- 2110.12894 The Efficiency Misnomer
        7103, -- 2111.00160 DSEE: Dually Sparsity-embedded Efficient Tuning of Pre-trained Language Models
        7128, -- 2111.01243 Recent Advances in Natural Language Processing via Large Pre-Trained Language Mo
        7141, -- 2111.01998 OpenPrompt: An Open-source Framework for Prompt-learning
        7256, -- 2111.09839 Training Neural Networks with Fixed Sparse Masks
        7402, -- 2112.01922 MetaQA: Combining Expert Agents for Multi-Skill Question Answering
        7490, -- 2112.06905 GLaM: Efficient Scaling of Language Models with Mixture-of-Experts
        7495, -- 2112.07522 LMTurk: Few-Shot Learners as Crowdsourcing Workers in a Language-Model-as-a-Serv
        7522, -- 2112.08542 QAFactEval: Improved QA-Based Factual Consistency Evaluation for Summarization
        7575, -- 2112.10684 Efficient Large Scale Language Modeling with Mixtures of Experts
        7889, -- 2202.03052 OFA: Unifying Architectures, Tasks, and Modalities Through a Simple Sequence-to-
        8004, -- 2202.08906 ST-MoE: Designing Stable and Transferable Sparse Expert Models
        8096, -- 2202.13914 Combining Modular Skills in Multitask Learning
        8120, -- 2203.01104 Parameter-Efficient Mixture-of-Experts Architecture for Pre-trained Language Mod
        8169, -- 2203.03691 HyperMixer: An MLP-based Low Cost Alternative to Transformers
        8267, -- 2203.07836 Graph Pre-training for AMR Parsing and Generation
        8326, -- 2203.09795 Three things everyone should know about Vision Transformers
        8342, -- 2203.10378 On Robust Prefix-Tuning for Text Classification
        8387, -- 2203.12119 Visual Prompt Tuning
        8397, -- 2203.12533 Pathways: Asynchronous Distributed Dataflow for ML
        8464, -- 2203.15243 Fine-tuning Image Transformers using Learnable Memory
        8489, -- 2203.16329 Parameter-efficient Model Adaptation for Vision Transformers
        8615, -- 2204.03574 Learning to Compose Soft Prompts for Compositional Zero-Shot Learning
        8626, -- 2204.03809 Federated Learning with Partial Model Personalization
        8675, -- 2204.05424 A Call for Clarity in Beam Search: How It Works and When It Stops
        8705, -- 2204.06487 Adapting Pre-trained Language Models to African Languages via Multilingual Adapt
        8748, -- 2204.07834 Bridging Cross-Lingual Gaps During Leveraging the Multilingual Sequence-to-Seque
        8772, -- 2204.08583 VQGAN-CLIP: Open Domain Image Generation and Editing with Natural Language Guida
        8776, -- 2204.08790 ELEVATER: A Benchmark and Toolkit for Evaluating Language-Augmented Visual Model
        8882, -- 2204.14198 Flamingo: a Visual Language Model for Few-Shot Learning
        8981, -- 2205.04682 Selective Fairness in Recommendation via Prompts
        8990, -- 2205.05124 Extracting Latent Steering Vectors from Pretrained Language Models
        8999, -- 2205.05638 Few-Shot Parameter-Efficient Fine-Tuning is Better and Cheaper than In-Context L
        9004, -- 2205.05862 AdaVAE: Exploring Adaptive GPT-2s in Variational Auto-Encoders for Language Mode
        9016, -- 2205.06266 Lifting the Curse of Multilinguality by Pre-training Modular Transformers
        9073, -- 2205.09911 Can Foundation Models Wrangle Your Data?
        9099, -- 2205.10643 Self-Supervised Speech Representation Learning: A Review
        9117, -- 2205.11005 Parameter-Efficient Sparsity for Large Language Models Fine-Tuning
        9171, -- 2205.12548 RLPrompt: Optimizing Discrete Text Prompts with Reinforcement Learning
        9180, -- 2205.12647 Overcoming Catastrophic Forgetting in Zero-Shot Cross-Lingual Generation
        9189, -- 2205.12701 Eliciting and Understanding Cross-Task Skills with Task-Level Mixture-of-Experts
        9219, -- 2205.13535 AdaptFormer: Adapting Vision Transformers for Scalable Visual Recognition
        9366, -- 2206.02252 Exploring Cross-lingual Textual Style Transfer with Large Multilingual Language
        9368, -- 2206.02336 Making Large Language Models Better Reasoners with Step-Aware Verifier
        9500, -- 2206.08082 Self-Generated In-Context Learning: Leveraging Auto-regressive Language Models a
        9502, -- 2206.08155 Zero-Shot Video Question Answering via Frozen Bidirectional Language Models
        9531, -- 2206.09059 CLiMB: A Continual Learning Benchmark for Vision-and-Language Tasks
        9831, -- 2207.09150 On the Usability of Transformers-based models for a French Question-Answering ta
        9877, -- 2207.11240 Discrete Key-Value Bottleneck
        9935, -- 2207.14386 Efficient NLP Model Finetuning via Multistage Data Filtering
        9956, -- 2208.01018 Massively Multilingual Lexical Specialization of Multilingual Transformers
        9970, -- 2208.02070 Efficient Fine-Tuning of Compressed Language Models with Learners
        9974, -- 2208.02532 Prompt Tuning for Generative Multimodal Pretrained Models
        9990, -- 2208.03306 Branch-Train-Merge: Embarrassingly Parallel Training of Expert Language Models
        10071, -- 2208.08241 ILLUME: Rationalizing Vision-Language Models through Human Interactions
        10094, -- 2208.09847 Scattered or Connected? An Optimized Parameter-efficient Tuning Approach for Inf
        10096, -- 2208.10160 PANDA: Prompt Transfer Meets Knowledge Distillation for Efficient Model Adaptati
        10099, -- 2208.10228 Review of Natural Language Processing in Pharmacology
        10124, -- 2208.11503 DPTDR: Deep Prompt Tuning for Dense Passage Retrieval
        10189, -- 2209.00099 Efficient Methods for Natural Language Processing: A Survey
        10207, -- 2209.01188 Petals: Collaborative Inference and Fine-tuning of Large Models
        10275, -- 2209.06192 StoryDALL-E: Adapting Pretrained Text-to-Image Transformers for Story Continuati
        10381, -- 2209.11055 Efficient Few-Shot Learning Without Prompts
        10452, -- 2209.14610 Dynamic Prompt Learning via Policy Gradient for Semi-structured Mathematical Rea
        10491, -- 2210.00038 Differentially Private Optimization on Large Model at Small Cost
        10578, -- 2210.02414 GLM-130B: An Open Bilingual Pre-trained Model
        10613, -- 2210.03265 Polyhistor: Parameter-Efficient Multi-Task Adaptation for Dense Vision Tasks
        10633, -- 2210.03821 Large Language Models can Implement Policy Iteration
        10637, -- 2210.03858 AlphaTuning: Quantization-Aware Parameter-Efficient Adaptation of Large-Scale Pr
        10661, -- 2210.04382 Parameter-Efficient Tuning with Special Token Adaptation
        10665, -- 2210.04457 XPrompt: Exploring the Extreme of Prompt Tuning
        10667, -- 2210.04492 Unified Detoxifying and Debiasing in Language Generation via Inference-time Adap
        10713, -- 2210.05549 Continual Training of Language Models for Few-Shot Learning
        10787, -- 2210.07144 Reprogramming Pretrained Language Models for Antibody Sequence Infilling
        10802, -- 2210.07370 M2D2: A Massively Multi-domain Language Modeling Dataset
        10811, -- 2210.07558 DyLoRA: Parameter Efficient Tuning of Pre-trained Models using Dynamic Search-Fr
        10887, -- 2210.10209 Exclusive Supermask Subnetwork Training for Continual Learning
        10892, -- 2210.10258 Continued Pretraining for Better Zero- and Few-Shot Promptability
        10896, -- 2210.10332 Revision Transformers: Instructing Language Models to Change their Values
        10910, -- 2210.10695 Incorporating Relevance Feedback for Information-Seeking Retrieval using Few-Sho
        10978, -- 2210.12517 Exploring The Landscape of Distributional Robustness for Question Answering Mode
        11040, -- 2210.13712 Parameter-Efficient Legal Domain Adaptation
        11171, -- 2211.00635 Two-stage LLM Fine-tuning with Less Specialization and More Generalization
        11255, -- 2211.03959 Pretraining in Deep Reinforcement Learning: A Survey
        11264, -- 2211.04256 Bridging Fairness and Environmental Sustainability in Natural Language Processin
        11362, -- 2211.08264 QAmeleon: Multilingual QA with Only 5 Examples
        11379, -- 2211.08723 Noisy Pairing and Partial Supervision for Stylized Opinion Summarization
        11475, -- 2211.11256 UniMSE: Towards Unified Multimodal Sentiment Analysis and Emotion Recognition
        11500, -- 2211.11720 Multitask Vision-Language Prompt Tuning
        11530, -- 2211.12485 HyperTuning: Toward Adapting Large Language Models without Back-propagation
        11551, -- 2211.12764 VoP: Text-Video Co-operative Prompt Tuning for Cross-Modal Retrieval
        11785, -- 2212.01393 Continual Learning for On-Device Speech Recognition using Disentangled Conformer
        11836, -- 2212.03246 MobileTL: On-device Transfer Learning with Inverted Residual Blocks
        11846, -- 2212.03533 Text Embeddings by Weakly-Supervised Contrastive Pre-training
        12065, -- 2212.09387 An Extensible Plug-and-Play Method for Multi-Aspect Controllable Text Generation
        12124, -- 2212.10315 HINT: Hypernetwork Instruction Tuning for Efficient Zero- & Few-Shot Generalisat
        12170, -- 2212.10773 MultiInstruct: Improving Multi-Modal Zero-Shot Learning via Instruction Tuning
        12178, -- 2212.10929 SPT: Semi-Parametric Prompt Tuning for Multitask Prompted Learning
        12379, -- 2301.04709 Causal Abstraction: A Theoretical Foundation for Mechanistic Interpretability
        12489, -- 2301.09626 Efficient Language Model Training through Cross-Lingual and Progressive Transfer
        12501, -- 2301.10140 The Semantic Scholar Open Data Platform
        12607, -- 2301.12050 Do Embodied Agents Dream of Pixelated Sheep: Embodied Decision Making using Lang
        12611, -- 2301.12132 AutoPEFT: Automatic Configuration Search for Parameter-Efficient Fine-Tuning
        12612, -- 2301.12140 Multilingual Sentence Transformer as A Multilingual Word Aligner
        12624, -- 2301.12313 Adapting Neural Link Predictors for Data-Efficient Complex Query Answering
        12717, -- 2301.13779 FLAME: A small language model for spreadsheet formulas
        12721, -- 2301.13823 Grounding Language Models to Images for Multimodal Inputs and Outputs
        12750, -- 2302.00456 Analyzing Feed-Forward Blocks in Transformers through the Lens of Attention Maps
        12752, -- 2302.00487 A Comprehensive Survey of Continual Learning: Theory, Method and Application
        12764, -- 2302.00856 idT5: Indonesian Version of Multilingual T5 Transformer
        12864, -- 2302.02551 CHiLS: Zero-Shot Image Classification with Hierarchical Label Sets
        12902, -- 2302.03202 Exploring the Benefits of Training Expert Language Models over Instruction Tunin
        12905, -- 2302.03241 Continual Pre-training of Language Models
        13023, -- 2302.05543 Adding Conditional Control to Text-to-Image Diffusion Models
        13053, -- 2302.06354 Less is More: Selective Layer Finetuning with SubTuning
        13069, -- 2302.06600 Task-Specific Skill Localization in Fine-tuned Language Models
        13255, -- 2302.11529 Modular Deep Learning
        13286, -- 2302.12246 Active Prompting with Chain-of-Thought for Large Language Models
        13307, -- 2302.12766 Language-Driven Representation Learning for Robotics
        13361, -- 2302.14286 HugNLP: A Unified and Comprehensive Library for Natural Language Processing
        13410, -- 2303.00501 OmniForce: On Human-Centered, Large Model Empowered and Cloud-Edge Collaborative
        13458, -- 2303.01580 Mixture of Soft Prompts for Controllable Data Generation
        13471, -- 2303.01904 EcoTTA: Memory-Efficient Continual Test-time Adaptation via Self-distilled Regul
        13478, -- 2303.02151 Prompt, Generate, then Cache: Cascade of Foundation Models makes Strong Few-shot
        13493, -- 2303.02506 Prismer: A Vision-Language Model with Multi-Task Experts
        13504, -- 2303.02861 Multitask Prompt Tuning Enables Parameter-Efficient Transfer Learning
        13505, -- 2303.02885 Improving Transformer-based Image Matching by Cascaded Capturing Spatially Infor
        13573, -- 2303.04671 Visual ChatGPT: Talking, Drawing and Editing with Visual Foundation Models
        13575, -- 2303.04715 Extending the Pre-Training of BLOOM for Improved Support of Traditional Chinese:
        13577, -- 2303.04751 Multimodal Parameter-Efficient Few-Shot Class Incremental Learning
        13589, -- 2303.04995 Text-Visual Prompting for Efficient 2D Temporal Video Grounding
        13598, -- 2303.05118 SLCA: Slow Learner with Classifier Alignment for Continual Learning on a Pre-tra
        13697, -- 2303.06911 ViM: Vision Middleware for Unified Downstream Transferring
        13718, -- 2303.07338 Revisiting Class-Incremental Learning with Pre-Trained Models: Generalizability
        13750, -- 2303.07910 Revisit Parameter-Efficient Transfer Learning: A Two-Stage Paradigm
        13766, -- 2303.08138 Diversity-Aware Meta Visual Prompting
        13781, -- 2303.08518 UPRISE: Universal Prompt Retrieval for Improving Zero-Shot Evaluation
        13845, -- 2303.09663 Efficient Computation Sharing for Multi-Task Visual Scene Understanding
        13887, -- 2303.10464 SPDF: Sparse Pre-training and Dense Fine-tuning for Large Language Models
        13889, -- 2303.10475 Large Language Model Instruction Following: A Survey of Progresses and Challenge
        13890, -- 2303.10512 AdaLoRA: Adaptive Budget Allocation for Parameter-Efficient Fine-Tuning
        13939, -- 2303.11403 eP-ALM: Efficient Perceptual Augmentation of Language Models
        13999, -- 2303.12314 Self-supervised Meta-Prompt Learning with Meta-Gradient Regularization for Few-s
        14008, -- 2303.12489 Few-shot Multimodal Multitask Multilingual Learning
        14068, -- 2303.13496 The effectiveness of MAE pre-pretraining for billion-scale pretraining
        14152, -- 2303.14773 BlackVIP: Black-Box Visual Prompting for Robust Transfer Learning
        14175, -- 2303.15230 Troika: Multi-Path Cross-Modal Traction for Compositional Zero-Shot Learning
        14201, -- 2303.15647 Scaling Down to Scale Up: A Guide to Parameter-Efficient Fine-Tuning
        14291, -- 2303.17169 Task-Oriented Multi-Modal Mutual Leaning for Vision-Language Models
        14344, -- 2303.18120 UKP-SQuARE v3: A Platform for Multi-Agent QA Research
        14378, -- 2304.00685 Vision-Language Models for Vision Tasks: A Survey
        14612, -- 2304.05216 Towards Efficient Fine-tuning of Pre-trained Code Models: An Experimental Study
        14669, -- 2304.06461 Multi-Mode Online Knowledge Distillation for Self-Supervised Visual Representati
        14672, -- 2304.06648 DiffFit: Unlocking Transferability of Large Diffusion Models via Simple Paramete
        14710, -- 2304.07221 Instance-aware Dynamic Prompt Tuning for Pre-trained Point Cloud Models
        14730, -- 2304.07880 Sabiá: Portuguese Large Language Models
        14748, -- 2304.08467 Learning to Compress Prompts with Gist Tokens
        14763, -- 2304.08865 Romanization-based Large-scale Adaptation of Multilingual Language Models
        14821, -- 2304.09972 MasakhaNEWS: News Topic Classification for African languages
        14928, -- 2304.12410 PEFT-Ref: A Modular Reference Architecture and Typology for Parameter-Efficient
        14933, -- 2304.12520 Hint-Aug: Drawing Hints from Foundation Vision Transformers Towards Boosted Few-
        14982, -- 2304.13639 PVP: Pre-trained Visual Parameter-Efficient Tuning
        15063, -- 2304.14999 Empirical Analysis of the Strengths and Weaknesses of PEFT Techniques for LLMs
        15084, -- 2305.00447 TALLRec: An Effective and Efficient Tuning Framework to Align Large Language Mod
        15118, -- 2305.01146 RadAdapt: Radiology Report Summarization via Lightweight Domain Adaptation of La
        15213, -- 2305.02665 Learning Language-Specific Layers for Multilingual Machine Translation
        15239, -- 2305.03048 Personalize Segment Anything Model with One Shot
        15285, -- 2305.03937 Residual Prompt Tuning: Improving Prompt Tuning with Residual Reparameterization
        15290, -- 2305.04091 Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Larg
        15463, -- 2305.06988 Self-Chained Image-Language Model for Video Localization and Question Answering
        15504, -- 2305.07677 Masked Audio Text Encoders are Effective Multi-Modal Rescorers
        15531, -- 2305.08088 Make Prompt-based Black-Box Tuning Colorful: Boosting Model Generalization from
        15538, -- 2305.08252 Parameter-Efficient Fine-Tuning for Medical Image Analysis: The Missed Opportuni
        15542, -- 2305.08285 Parameter-Efficient Fine-Tuning with Layer Pruning on Free-Text Sequence-to-Sequ
        15574, -- 2305.08828 PMIndiaSum: Multilingual and Cross-lingual Headline Summarization for Languages
        15640, -- 2305.09955 Knowledge Card: Filling LLMs' Knowledge Gaps with Plug-in Specialized Language M
        15754, -- 2305.11391 A Survey of Safety and Trustworthiness of Large Language Models through the Lens
        15771, -- 2305.11554 ToolkenGPT: Augmenting Frozen Language Models with Massive Tools via Tool Embedd
        15840, -- 2305.12281 Lifelong Language Pretraining with Distribution-Specialized Experts
        15926, -- 2305.13235 SPARSEFIT: Few-shot Prompting with Sparse Fine-tuning for Jointly Generating Pre
        15930, -- 2305.13256 TaskWeb: Selecting Better Source Tasks for Multi-task NLP
        15957, -- 2305.13514 Small Language Models Improve Giants by Rewriting Their Outputs
        15958, -- 2305.13516 Scaling Speech Technology to 1,000+ Languages
        16017, -- 2305.13989 MasakhaPOS: Part-of-Speech Tagging for Typologically Diverse African Languages
        16036, -- 2305.14152 Memory-Efficient Fine-Tuning of Compressed Large Language Models via sub-4-bit I
        16047, -- 2305.14232 Pre-training Multi-task Contrastive Learning Models for Scientific Literature Un
        16063, -- 2305.14314 QLoRA: Efficient Finetuning of Quantized LLMs
        16132, -- 2305.14760 Bi-Drop: Enhancing Fine-tuning Generalization via Synchronous sub-net Estimation
        16226, -- 2305.15265 Winner-Take-All Column Row Sampling for Memory Efficient Adaptation of Language
        16232, -- 2305.15296 MultiFusion: Fusing Pre-Trained Models for Multi-Lingual, Multi-Modal Image Gene
        16240, -- 2305.15348 READ: Recurrent Adaptation of Large Transformers
        16369, -- 2305.16876 CombLM: Adapting Black-Box Language Models through Small Fine-Tuned Models
        16374, -- 2305.16938 Few-shot Fine-tuning vs. In-context Learning: A Fair Comparison and Evaluation
        16409, -- 2305.17223 Do We Really Need a Large Number of Visual Prompts?
        16451, -- 2305.17660 Plug-and-Play Document Modules for Pre-trained Models
        16453, -- 2305.17691 Plug-and-Play Knowledge Injection for Pre-trained Language Models
        16480, -- 2305.18169 LM-CPPF: Paraphrasing-Guided Data Augmentation for Contrastive Prompt-Based Few-
        16503, -- 2305.18323 ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language M
        16522, -- 2305.18425 Efficient Storage of Fine-Tuned Models via Low-Rank Approximation of Weight Resi
        16525, -- 2305.18444 Continual Task Allocation in Meta-Policy Network via Sparse Prompting
        16559, -- 2305.18703 Domain Specialization as the Key to Make Large Language Models Disruptive: A Com
        16593, -- 2305.19000 Independent Component Alignment for Multi-Task Learning
        16620, -- 2305.19270 Learning without Forgetting for Vision-Language Models
        16727, -- 2306.00317 FlexRound: Learnable Rounding based on Element-wise Division for Post-Training Q
        16757, -- 2306.00618 Effective Structured Prompting by Meta-Learning and Representative Verbalizer
        16774, -- 2306.00789 Improved Cross-Lingual Transfer Learning For Automatic Speech Translation
        16808, -- 2306.00983 StyleDrop: Text-to-Image Generation in Any Style
        16843, -- 2306.01327 Speech Translation with Foundation Models and Optimal Transport: UPC at IWSLT23
        16861, -- 2306.01567 Segment Anything in High Quality
        16872, -- 2306.01707 Learning Multi-Step Reasoning by Solving Arithmetic Tasks
        16874, -- 2306.01709 Distilling Efficient Language-Specific Models for Cross-Lingual Transfer
        16928, -- 2306.02320 Exploring the Impact of Model Scaling on Parameter-Efficient Tuning
        17019, -- 2306.03341 Inference-Time Intervention: Eliciting Truthful Answers from a Language Model
        17050, -- 2306.03745 Soft Merging of Experts with Adaptive Routing
        17081, -- 2306.04136 Knowledge-Augmented Language Model Prompting for Zero-Shot Knowledge Graph Quest
        17111, -- 2306.04529 Git-Theta: A Git Extension for Collaborative Development of Machine Learning Mod
        17118, -- 2306.04640 ModuleFormer: Modularity Emerges from Mixture-of-Experts
        17123, -- 2306.04724 Prompter: Zero-shot Adaptive Prefixes for Dialogue State Tracking Domain Adaptat
        17143, -- 2306.04933 InfoPrompt: Information-Theoretic Soft Prompt Tuning for Natural Language Unders
        17150, -- 2306.05067 Improving Visual Prompt Tuning for Self-supervised Vision Transformers
        17194, -- 2306.05480 Artificial General Intelligence for Medical Imaging Analysis
        17318, -- 2306.07280 Controlling Text-to-Image Diffusion by Orthogonal Finetuning
        17341, -- 2306.07536 TART: A plug-and-play Transformer module for task-agnostic reasoning
        17395, -- 2306.08107 AutoML in the Age of Large Language Models: Current Challenges, Future Opportuni
        17401, -- 2306.08162 INT2.1: Towards Fine-Tunable Quantized Large Language Models with Error Correcti
        17432, -- 2306.08658 Babel-ImageNet: Massively Multilingual Evaluation of Vision-and-Language Represe
        17546, -- 2306.10001 Group Orthogonalization Regularization For Vision Models Adaptation and Robustne
        17590, -- 2306.10900 MotionGPT: Finetuned LLMs Are General-Purpose Motion Generators
        17613, -- 2306.11300 RS5M and GeoRSCLIP: A Large Scale Vision-Language Dataset and A Large Vision-Lan
        17686, -- 2306.12873 FuXi: A cascade machine learning forecasting system for 15-day global weather fo
        17700, -- 2306.13090 PromptIR: Prompting for All-in-One Blind Image Restoration
        17777, -- 2306.14870 Composing Parameter-Efficient Modules with Arithmetic Operations
        17779, -- 2306.14884 Learning to Modulate pre-trained Models in RL
        17820, -- 2306.15706 Approximated Prompt Tuning for Vision-Language Pre-trained Models
        17898, -- 2306.17154 Generate Anything Anywhere in Any Scene
        17900, -- 2306.17165 An Efficient General-Purpose Modular Vision Model via Multi-Task Heterogeneous T
        17901, -- 2306.17194 On the Exploitability of Instruction Tuning
        17923, -- 2306.17842 SPAE: Semantic Pyramid AutoEncoder for Multimodal Generation with Frozen LLMs
        17930, -- 2307.00119 Meta-training with Demonstration Retrieval for Efficient Few-shot Learning
        18012, -- 2307.02046 Recommender Systems in the Era of Large Language Models (LLMs)
        18058, -- 2307.03084 OpenDelta: A Plug-and-play Library for Parameter-efficient Adaptation of Pre-tra
        18166, -- 2307.05468 My3DGen: A Scalable Personalized 3D Generative Model
        18179, -- 2307.05741 Towards Robust and Efficient Continual Language Learning
        18201, -- 2307.06435 A Comprehensive Overview of Large Language Models
        18220, -- 2307.06949 HyperDreamBooth: HyperNetworks for Fast Personalization of Text-to-Image Models
        18288, -- 2307.08122 Tangent Transformers for Composition, Privacy and Removal
        18402, -- 2307.09787 DVPT: Dynamic Visual Prompt Tuning of Large Pre-trained Models for Medical Image
        18435, -- 2307.10485 FinGPT: Democratizing Internet-scale Data for Financial Large Language Models
        18498, -- 2307.11342 Tuning Pre-trained Model via Moment Probing
        18526, -- 2307.11795 Prompting Large Language Models with Speech Recognition Abilities
        18713, -- 2307.15049 Regularized Mask Tuning: Uncovering Hidden Knowledge in Pre-trained Vision-Langu
        18859, -- 2308.01240 Evaluating Instruction-Tuned Large Language Models on Code Comprehension and Gen
        18953, -- 2308.02862 Improving Generalization of Image Captioning with Unsupervised Prompt Learning
        18961, -- 2308.03028 Pre-Trained Large Language Models for Industrial Control
        18988, -- 2308.03303 LoRA-FA: Memory-efficient Low-rank Adaptation for Large Language Models Fine-tun
        18996, -- 2308.03427 TPTU: Large Language Model-based AI Agents for Task Planning and Tool Usage
        19151, -- 2308.06051 Towards Instance-adaptive Inference for Federated Learning
        19180, -- 2308.06522 SLoRA: Federated Parameter Efficient Fine-Tuning of Language Models
        19300, -- 2308.08090 Separate the Wheat from the Chaff: Model Deficiency Unlearning via Parameter-Eff
        19312, -- 2308.08234 Challenges and Opportunities of Using Transformer-Based Multi-Task Learning in N
        19371, -- 2308.09139 The Unreasonable Effectiveness of Large Language-Vision Models for Source-free V
        19386, -- 2308.09300 V2A-Mapper: A Lightweight Solution for Vision-to-Audio Generation by Connecting
        19424, -- 2308.09610 On the Effectiveness of LayerNorm Tuning for Continual Learning in Vision Transf
        19453, -- 2308.09892 Utilizing Semantic Textual Similarity for Clinical Survey Data Feature Selection
        19494, -- 2308.10149 A Survey on Fairness in Large Language Models
        19498, -- 2308.10172 VLN-PETL: Parameter-Efficient Transfer Learning for Vision-and-Language Navigati
        19535, -- 2308.10462 Exploring Parameter-Efficient Fine-Tuning Techniques for Code Generation with La
        19567, -- 2308.10792 Instruction Tuning for Large Language Models: A Survey
        19598, -- 2308.11148 LLaMA-Reviewer: Advancing Code Review Automation with Large Language Models thro
        19685, -- 2308.12043 IncreLoRA: Incremental Parameter Allocation Method for Parameter-Efficient Fine-
        19688, -- 2308.12058 DR-Tune: Improving Fine-tuning of Pretrained Visual Models by Distribution Regul
        19763, -- 2308.13111 Bayesian Low-rank Adaptation for Large Language Models
        19836, -- 2308.14149 Examining User-Friendly and Open-Sourced Large GPT Models: A Survey on Language,
        19852, -- 2308.14316 UniPT: Universal Parallel Tuning for Transfer Learning with Efficient Parameter
        19885, -- 2308.14929 Maestro: Uncovering Low-Rank Structures via Trainable Decomposition
        20011, -- 2309.00363 FederatedScope-LLM: A Comprehensive Package for Fine-tuning Large Language Model
        20026, -- 2309.00770 Bias and Fairness in Large Language Models: A Survey
        20035, -- 2309.00916 BLSP: Bootstrapping Language-Speech Pre-training via Behavior Alignment of Conti
        20157, -- 2309.03118 Knowledge Solver: Teaching LLMs to Search for Domain Knowledge from Knowledge Gr
        20171, -- 2309.03412 From Base to Conversational: Japanese Instruction Dataset and Tuning Large Langu
        20234, -- 2309.04658 Exploring Large Language Models for Communication Games: An Empirical Study on W
        20269, -- 2309.05173 DePT: Decomposed Prompt Tuning for Parameter-Efficient Fine-tuning
        20284, -- 2309.05444 Pushing Mixture of Experts to the Limit: Extremely Parameter Efficient MoE for I
        20311, -- 2309.05950 Language Models as Black-Box Optimizers for Vision-Language Models
        20356, -- 2309.06759 Scaled Prompt-Tuning for Few-Shot Natural Language Generation
        20375, -- 2309.07117 PILOT: A Pre-Trained Model-Based Continual Learning Toolbox
        20401, -- 2309.07439 DePT: Decoupled Prompt Tuning
        20478, -- 2309.08513 SCT: A Simple Baseline for Parameter-Efficient Fine-Tuning via Salient Channels
        20501, -- 2309.08708 Vocabulary-level Memory Efficiency for Language Model Fine-tuning
        20525, -- 2309.08968 Sorted LLaMA: Unlocking the Potential of Intermediate Layers of Large Language M
        20713, -- 2309.11756 Sparsely Shared LoRA on Whisper for Child Speech Recognition
        20816, -- 2309.13202 Investigating Large Language Models and Control Mechanisms to Improve Text Reada
        20923, -- 2309.14717 QA-LoRA: Quantization-Aware Low-Rank Adaptation of Large Language Models
        20925, -- 2309.14763 ConPET: Continual Parameter-Efficient Tuning for Large Language Models
        20936, -- 2309.15048 Class Incremental Learning via Likelihood Ratio Based Task Prediction
        20953, -- 2309.15223 Low-rank Adaptation of Large Language Model Rescoring for Parameter-Efficient Sp
        20977, -- 2309.15649 Generative Speech Recognition Error Correction with Large Language Models and Ta
        20992, -- 2309.15915 Zero-Shot and Few-Shot Video Question Answering with Multi-Modal Prompts
        21004, -- 2309.16119 ModuLoRA: Finetuning 2-Bit LLMs on Consumer GPUs by Integrating with Modular Qua
        21065, -- 2309.17002 Understanding and Mitigating the Label Noise in Pre-training on Downstream Tasks
        21088, -- 2309.17249 Batch Calibration: Rethinking Calibration for In-Context Learning and Prompt Eng
        21168, -- 2310.00582 Pink: Unveiling the Power of Referential Comprehension for Multi-modal LLMs
        21192, -- 2310.00819 Parameter-Efficient Tuning Helps Language Model Alignment
        21195, -- 2310.00847 Can Pre-trained Networks Detect Familiar Out-of-Distribution Data?
        21253, -- 2310.01407 CoDi: Conditional Diffusion Distillation for Higher-Fidelity and Faster Image Ge
        21280, -- 2310.01691 Zero-Shot Continuous Prompt Transfer: Generalizing Task Semantics Across Languag
        21300, -- 2310.01818 AutoLoRa: A Parameter-Free Automated Robust Fine-Tuning Framework
        21303, -- 2310.01825 Empirical Study of PEFT techniques for Winter Wheat Segmentation
        21306, -- 2310.01846 Benchmarking and Improving Generator-Validator Consistency of Language Models
        21342, -- 2310.02239 MiniGPT-5: Interleaved Vision-and-Language Generation via Generative Vokens
        21363, -- 2310.02556 NOLA: Compressing LoRA using Linear Combination of Random Basis
        21422, -- 2310.03188 Talking Models: Distill Pre-trained Knowledge to Downstream Models via Interacti
        21613, -- 2310.05393 Hierarchical Side-Tuning for Vision Transformers
        21635, -- 2310.05694 A Survey of Large Language Models for Healthcare: from Data, Technology, and App
        21652, -- 2310.05845 GraphLLM: Boosting Graph Reasoning Ability of Large Language Model
        21654, -- 2310.05861 Rephrase, Augment, Reason: Visual Grounding of Questions for Vision-Language Mod
        21692, -- 2310.06238 Tackling Data Bias in MUSIC-AVQA: Crafting a Balanced Dataset for Unbiased Quest
        21711, -- 2310.06434 Whispering LLaMA: A Cross-Modal Generative Error Correction Framework for Speech
        21768, -- 2310.07204 State of the Art on Diffusion Models for Visual Computing
        21784, -- 2310.07343 How Do Large Language Models Capture the Ever-changing World Knowledge? A Review
        21795, -- 2310.07478 Multimodal Graph Learning for Generative Tasks
        21799, -- 2310.07521 Survey on Factuality in Large Language Models: Knowledge, Retrieval and Domain-S
        21873, -- 2310.08320 Defending Our Privacy With Backdoors
        21907, -- 2310.08579 HyperHuman: Hyper-Realistic Human Generation with Latent Structural Diffusion
        21971, -- 2310.09424 SALM: Speech-augmented Language Model with In-context Learning for Speech Recogn
        21979, -- 2310.09503 JM3D & JM3D-LLM: Elevating 3D Understanding with Joint Multi-modal Cues
        22003, -- 2310.09832 Merging Experts into One: Improving Computational Efficiency of Mixture of Exper
        22019, -- 2310.10094 Decomposed Prompt Tuning via Low-Rank Reparameterization
        22090, -- 2310.10908 Unlocking Emergent Modularity in Large Language Models
        22128, -- 2310.11454 VeRA: Vector-based Random Matrix Adaptation
        22156, -- 2310.11829 Towards Graph Foundation Models: A Survey and Beyond
        22178, -- 2310.12100 Non-Intrusive Adaptation: Input-Centric Parameter-efficient Fine-Tuning for Vers
        22208, -- 2310.12611 Identifying and Adapting Transformer-Components Responsible for Gender Bias in a
        22215, -- 2310.12774 Survival of the Most Influential Prompts: Efficient Black-Box Prompt Search via
        22250, -- 2310.13024 Towards Anytime Fine-tuning: Continually Pre-trained Language Models with Hypern
        22333, -- 2310.14152 Orthogonal Subspace Learning for Language Model Continual Learning
        22451, -- 2310.15477 CRaSh: Clustering, Removing, and Sharing Enhance Fine-tuning without Full Large
        22543, -- 2310.16570 Give Me the Facts! A Survey on Factual Knowledge Probing in Pre-trained Language
        22575, -- 2310.16870 MACP: Efficient Model Adaptation for Cooperative Perception
        22636, -- 2310.17752 PockEngine: Sparse and Efficient Fine-tuning in a Pocket
        22696, -- 2310.18547 Punica: Multi-Tenant LoRA Serving
        22766, -- 2310.19698 When Do Prompting and Prefix-Tuning Work? A Theory of Capabilities and Limitatio
        22879, -- 2311.00915 Task-Agnostic Low-Rank Adapters for Unseen English Dialects
        22966, -- 2311.02684 Octavius: Mitigating Task Interference in MLLMs via LoRA-MoE
        22987, -- 2311.03099 Language Models are Super Mario: Absorbing Abilities from Homologous Models as a
        23115, -- 2311.05112 A Survey of Large Language Models in Medicine: Progress, Application, and Challe
        23134, -- 2311.05556 LCM-LoRA: A Universal Stable-Diffusion Acceleration Module
        23175, -- 2311.06243 Parameter-Efficient Orthogonal Finetuning via Butterfly Factorization
        23206, -- 2311.06791 InfMLLM: A Unified Framework for Visual-Language Tasks
        23329, -- 2311.08572 Low-Rank Adaptation for Multilingual Summarization: An Empirical Study
        23376, -- 2311.09179 SiRA: Sparse Mixture of Low Rank Adaptation
        23404, -- 2311.09344 Language and Task Arithmetic with Parameter-Efficient Layers for Zero-Shot Summa
        23419, -- 2311.09578 Tied-Lora: Enhancing parameter efficiency of LoRA with weight tying
        23455, -- 2311.09836 PELMS: Pre-training for Effective Low-Shot Multi-Document Summarization
        23501, -- 2311.10847 Token-Level Adaptation of LoRA Adapters for Downstream Task Generalization
        23532, -- 2311.11501 MultiLoRA: Democratizing LoRA for Better Multi-Task Learning
        23545, -- 2311.11696 Sparse Low-rank Adaptation of Pre-trained Language Models
        23561, -- 2311.11908 Continual Learning: Applications and the Road Forward
        23568, -- 2311.12023 LQ-LoRA: Low-rank Plus Quantized Matrix Decomposition for Efficient Language Mod
        23645, -- 2311.13126 Towards Better Parameter-Efficient Fine-Tuning for Large Language Models: A Posi
        23650, -- 2311.13171 ComPEFT: Compression for Communicating Parameter Efficient Updates via Sparsific
        23696, -- 2311.13937 Exploring Methods for Cross-lingual Text Style Transfer: The Case of Text Detoxi
        23843, -- 2311.16241 SemiVL: Semi-Supervised Semantic Segmentation with Vision-Language Guidance
        23961, -- 2311.17601 Continual Learning with Low Rank Adaptation
        23977, -- 2311.17842 Look Before You Leap: Unveiling the Power of GPT-4V in Robotic Vision-Language P
        24110, -- 2312.00407 CoLLiE: Collaborative Training of Large Language Models in an Efficient Way
        24111, -- 2312.00434 PEFTDebias : Capturing debiasing information using PEFTs
        24125, -- 2312.00662 Nonparametric Variational Regularisation of Pretrained Transformers
        24127, -- 2312.00678 The Efficiency Spectrum of Large Language Models: An Algorithmic Survey
        24162, -- 2312.00968 Omni-SMoLA: Boosting Generalist Multimodal Models with Soft Mixture of Low-rank
        24195, -- 2312.01629 CLAMP: Contrastive LAnguage Model Prompt-tuning
        24200, -- 2312.01678 Jellyfish: A Large Language Model for Data Preprocessing
        24203, -- 2312.01711 Regressor-Segmenter Mutual Prompt Learning for Crowd Counting
        24230, -- 2312.02133 Style Aligned Image Generation via Shared Attention
        24298, -- 2312.02783 Large Language Models on Graphs: A Comprehensive Survey
        24363, -- 2312.03611 DreamComposer: Controllable 3D Object Generation via Multi-View Conditions
        24370, -- 2312.03668 Integrating Pre-Trained Speech and Language Models for End-to-End Speech Recogni
        24379, -- 2312.03724 DP-OPT: Make Large Language Model Your Privacy-Preserving Prompt Engineer
        24393, -- 2312.03805 SYNC-CLIP: Synthetic Data Make CLIP Generalize Better in Data-Limited Scenarios
        24423, -- 2312.04265 Stronger, Fewer, & Superior: Harnessing Vision Foundation Models for Domain Gene
        24444, -- 2312.04511 An LLM Compiler for Parallel Function Calling
        24480, -- 2312.04775 How to Determine the Most Powerful Pre-trained Language Model without Brute Forc
        24561, -- 2312.05842 Mutual Enhancement of Large and Small Language Models with Cross-Silo Knowledge
        24656, -- 2312.07028 Dynamic Corrective Self-Distillation for Better Fine-Tuning of Pretrained Models
        24659, -- 2312.07066 DiffuVST: Narrating Fictional Scenes with Global-History-Guided Denoising Models
        24680, -- 2312.07395 A Simple Recipe for Contrastively Pre-training Video-First Encoders Beyond 16 Fr
        24688, -- 2312.07485 MinD-3D: Reconstruct High-quality 3D objects in Human Brain
        24714, -- 2312.07887 Learn or Recall? Revisiting Incremental Learning with Pre-trained Language Model
        24735, -- 2312.08361 Distributed Inference and Fine-tuning of Large Language Models Over The Internet
        24778, -- 2312.08900 Context-PEFT: Efficient Multi-Modal, Multi-Task Fine-Tuning
        24846, -- 2312.09979 LoRAMoE: Alleviate World Knowledge Forgetting in Large Language Models via MoE-S
        24859, -- 2312.10136 Gradient-based Parameter Selection for Efficient Fine-Tuning
        24882, -- 2312.10365 SPT: Fine-Tuning Transformer-based Language Models Efficiently with Sparsificati
        24927, -- 2312.11392 SCEdit: Efficient and Controllable Image Diffusion Generation via Skip Connectio
        24929, -- 2312.11420 Tuning LayerNorm in Attention: Towards Efficient Multi-Modal LLM Finetuning
        24962, -- 2312.11795 MELO: Enhancing Model Editing with Neuron-Indexed Dynamic LoRA
        24977, -- 2312.12148 Parameter-Efficient Fine-Tuning Methods for Pretrained Language Models: A Critic
        25045, -- 2312.13208 LlaMaVAE: Guiding Large Language Model Generation via Continuous Latent Sentence
        25120, -- 2312.14327 Parameter Efficient Tuning Allows Scalable Personalization of LLMs for Text Entr
        25123, -- 2312.14378 Multimodal Attention Merging for Improved Speech Recognition and Audio Event Cla
        25164, -- 2312.15230 PERP: Rethinking the Prune-Retrain Paradigm in the Era of LLMs
        25184, -- 2312.15614 A Comprehensive Evaluation of Parameter-Efficient Fine-Tuning on Software Engine
        25212, -- 2312.15997 Aligning Large Language Models with Human Preferences through Representation Eng
        25311, -- 2312.17493 Differentially Private Low-Rank Adaptation of Large Language Model Using Federat
        25364, -- 2401.00625 Beyond Efficiency: A Systematic Survey of Resource-Efficient Large Language Mode
        25373, -- 2401.00788 Astraios: Parameter-Efficient Instruction Tuning Code Large Language Models
        25408, -- 2401.01286 A Comprehensive Study of Knowledge Editing for Large Language Models
        25470, -- 2401.02122 PEFT for Speech: Unveiling Optimal Placement, Merging Strategies, and Ensemble T
        25492, -- 2401.02412 LLM Augmented LLMs: Expanding Capabilities through Composition
        25494, -- 2401.02415 LLaMA Pro: Progressive LLaMA with Block Expansion
        25498, -- 2401.02458 Data-Centric Foundation Models in Computational Healthcare: A Survey
        25531, -- 2401.03129 Examining Forgetting in Continual Pre-training of Aligned Large Language Models
        25592, -- 2401.04151 Chain of LoRA: Efficient Fine-tuning of Language Models via Residual Learning
        25601, -- 2401.04339 Memory-Efficient Fine-Tuning for Quantized Diffusion Model
        25603, -- 2401.04348 LAMPAT: Low-Rank Adaption for Multilingual Paraphrasing Using Adversarial Traini
        25609, -- 2401.04472 A Survey on Efficient Federated Learning Methods for Foundation Model Training
        25611, -- 2401.04507 TechGPT-2.0: A large language model project to solve the task of knowledge graph
        25749, -- 2401.06466 PersianMind: A Cross-Lingual Persian-English Large Language Model
        25804, -- 2401.07159 Quantized Side Tuning: Fast and Memory-Efficient Tuning of Quantized Large Langu
        25821, -- 2401.07598 MAPLE: Multilingual Evaluation of Parameter Efficient Finetuning of Large Langua
        25877, -- 2401.08565 Tuning Language Models by Proxy
        26029, -- 2401.10472 Named Entity Recognition Under Domain Shift via Metric Learning for Life Science
        26043, -- 2401.10660 Accelerating Multilingual Language Model for Excessively Tokenized Languages
        26085, -- 2401.11316 PRILoRA: Pruned and Rank-Increasing Low-Rank Adaptation
        26094, -- 2401.11509 Simple Domain Adaptation for Sparse Retrievers
        26142, -- 2401.12200 APT: Adaptive Pruning and Tuning Pretrained Language Models for Efficient Traini
        26146, -- 2401.12215 Less Could Be Better: Parameter-efficient Fine-tuning Advances Medical Vision Fo
        26187, -- 2401.12819 Dynamic Layer Tying for Parameter-Efficient Transformers
        26244, -- 2401.13601 MM-LLMs: Recent Advances in MultiModal Large Language Models
        26287, -- 2401.14194 Parameter-Efficient Conversational Recommender System as a Language Processing T
        26326, -- 2401.14556 Looking Right is Sometimes Right: Investigating the Capabilities of Decoder-only
        26354, -- 2401.15207 HiFT: A Hierarchical Full Parameter Fine-Tuning Strategy
        26365, -- 2401.15347 A Comprehensive Survey of Compression Algorithms for Language Models
        26510, -- 2401.17514 How Useful is Continued Pre-Training for Generative Unsupervised Domain Adaptati
        26531, -- 2401.17868 Convolution Meets LoRA: Parameter Efficient Finetuning for Segment Anything Mode
        26569, -- 2402.00433 Merging Multi-Task Models via Weight-Ensembling Mixture of Experts
        26655, -- 2402.01376 LoTR: Low Tensor Rank Weight Adaptation
        26676, -- 2402.01618 Style Vectors for Steering Generative Large Language Model
        26758, -- 2402.02340 Learning Semantic Proxies from Visual Prompts for Parameter-Efficient Fine-Tunin
        26788, -- 2402.02705 Representation Surgery for Multi-Task Model Merging
        26833, -- 2402.03241 FROSTER: Frozen CLIP Is A Strong Teacher for Open-Vocabulary Action Recognition
        26839, -- 2402.03293 Flora: Low-Rank Adapters Are Secretly Gradient Compressors
        26925, -- 2402.04154 Read to Play (R2-Play): Decision Transformer with Multimodal Game Instruction
        26946, -- 2402.04335 LegalLens: Leveraging LLMs for Legal Violation Identification in Unstructured Te
        26947, -- 2402.04347 The Hedgehog & the Porcupine: Expressive Linear Attentions with Softmax Mimicry
        26960, -- 2402.04527 RA-Rec: An Efficient ID Representation Alignment Framework for LLM-based Recomme
        26976, -- 2402.04644 LEVI: Generalizable Fine-tuning via Layer-wise Ensemble of Different Views
        26996, -- 2402.04914 Personalized Text Generation with Fine-Grained Linguistic Control
        27000, -- 2402.04964 ConvLoRA and AdaBN based Domain Adaptation via Self-Training
        27018, -- 2402.05147 ApiQ: Finetuning of 2-Bit Quantized Large Language Model
        27037, -- 2402.05457 It's Never Too Late: Fusing Acoustic Information into Large Language Models for
        27069, -- 2402.05859 Learning to Route Among Specialized Experts for Zero-Shot Generalization
        27186, -- 2402.07483 T-RAG: Lessons from the LLM Trenches
        27206, -- 2402.07792 Empowering Federated Learning for Massive Models with NVIDIA FLARE
        27263, -- 2402.08609 Mixtures of Experts Unlock Parameter Scaling for Deep RL
        27323, -- 2402.09353 DoRA: Weight-Decomposed Low-Rank Adaptation
        27346, -- 2402.09748 Model Compression and Efficient Inference for Large Language Models: A Survey
        27380, -- 2402.10193 BitDelta: Your Fine-Tune May Only Be Worth One Bit
        27385, -- 2402.10208 Recovering the Pre-Fine-Tuning Weights of Generative Models
        27405, -- 2402.10462 QDyLoRA: Quantized Dynamic Low-Rank Adaptation for Efficient Large Language Mode
        27432, -- 2402.10698 Question-Instructed Visual Descriptions for Zero-Shot Video Question Answering
        27500, -- 2402.11441 InfuserKI: Enhancing Large Language Models with Knowledge Graphs via Infuser-Gui
        27522, -- 2402.11592 Revisiting Zeroth-Order Optimization for Memory-Efficient LLM Fine-Tuning: A Ben
        27533, -- 2402.11700 Why Lift so Heavy? Slimming Large Language Models by Cutting Off the Layers
        27651, -- 2402.12851 MoELoRA: Contrastive Learning Guided Mixture of Experts on Parameter-Efficient F
        27875, -- 2402.15059 ColBERT-XM: A Modular Multi-Vector Representation Model for Zero-Shot Multilingu
        27883, -- 2402.15159 Machine Unlearning of Pre-trained Large Language Models
        27890, -- 2402.15220 ChunkAttention: Efficient Self-Attention with Prefix-Aware KV Cache and Two-Phas
        27925, -- 2402.15751 Sparse MeZO: Less Parameters for Better Performance in Zeroth-Order LLM Fine-Tun
        27955, -- 2402.16141 PeriodicLoRA: Breaking the Low-Rank Bottleneck in LoRA Optimization
        27999, -- 2402.16828 Training Neural Networks from Scratch with Parallel Low-Rank Adapters
        28013, -- 2402.16918 m2mKD: Module-to-Module Knowledge Distillation for Modular Transformers
        28035, -- 2402.17193 When Scaling Meets LLM Finetuning: The Effect of Data, Model and Finetuning Meth
        28042, -- 2402.17263 MELoRA: Mini-Ensemble Low-Rank Adapters for Parameter-Efficient Fine-Tuning
        28055, -- 2402.17412 DiffuseKronA: A Parameter Efficient Fine-tuning Method for Personalized Diffusio
        28111, -- 2402.18013 A Survey on Recent Advances in LLM-Based Multi-turn Dialogue Systems
        28114, -- 2402.18039 ResLoRA: Identity Residual Mapping in Low-Rank Adaption
        28173, -- 2402.18789 FlexLLM: A System for Co-Serving Large Language Model Inference and Parameter-Ef
        28192, -- 2402.19159 Trajectory Consistency Distillation: Improved Latent Consistency Distillation by
        28299, -- 2403.01165 STAR: Constraint LoRA with Dynamic Active Learning for Data-Efficient Fine-Tunin
        28377, -- 2403.02271 RIFF: Learning to Rephrase Inputs for Few-shot Fine-tuning of Language Models
        28457, -- 2403.03432 Mixture-of-LoRAs: An Efficient Multitask Tuning for Large Language Models
        28497, -- 2403.04190 Generative AI for Synthetic Data Generation: Methods, Challenges and the Future
        28570, -- 2403.05139 Improving Diffusion Models for Authentic Virtual Try-on in the Wild
        28573, -- 2403.05231 Tracking Meets LoRA: Faster Training, Larger Model, Stronger Performance
        28607, -- 2403.05798 $\textbf{S}^2$IP-LLM: Semantic Space Informed Prompt Learning with LLM for Time
        28647, -- 2403.06407 Can LLMs' Tuning Methods Work in Medical Multimodal Domain?
        28694, -- 2403.07088 SPA: Towards A Computational Friendly Cloud-Base and On-Devices Collaboration Se
        28718, -- 2403.07500 Block-wise LoRA: Revisiting Fine-grained LoRA for Effective Personalization and
        28807, -- 2403.08822 LoRA-SP: Streamlined Partial Parameter Adaptation for Resource-Efficient Fine-Tu
        28831, -- 2403.09113 AutoLoRA: Automatically Tuning Matrix Ranks in Low-Rank Adaptation Based on Meta
        28837, -- 2403.09192 PYRA: Parallel Yielding Re-Activation for Training-Inference Efficient Task Adap
        28908, -- 2403.10131 RAFT: Adapting Language Model to Domain Specific RAG
        29017, -- 2403.11530 Continual Forgetting for Pre-trained Vision Models
        29022, -- 2403.11621 Let's Focus on Neuron: Neuron-Level Supervised Fine-tuning for Large Language Mo
        29085, -- 2403.12313 Improving LoRA in Privacy-preserving Federated Learning
        29096, -- 2403.12468 CrossTune: Black-Box Few-Shot Classification with Label Enhancement
        29149, -- 2403.13037 BiLoRA: A Bi-level Optimization Framework for Overfitting-Resilient Low-Rank Ada
        29184, -- 2403.13372 LlamaFactory: Unified Efficient Fine-Tuning of 100+ Language Models
        29185, -- 2403.13447 HyperLLaVA: Dynamic Visual and Language Expert Tuning for Multimodal Large Langu
        29271, -- 2403.14572 Implicit Style-Content Separation using B-LoRA
        29276, -- 2403.14608 Parameter-Efficient Fine-Tuning for Large Models: A Comprehensive Survey
        29304, -- 2403.14870 VidLA: Video-Language Alignment at Scale
        29314, -- 2403.15049 Continual Vision-and-Language Navigation
        29385, -- 2403.16024 A Unified Module for Accelerating STABLE-DIFFUSION: LCM-LORA
        29392, -- 2403.16187 ALoRA: Allocating Low-Rank Adaptation for Fine-tuning Large Language Models
        29467, -- 2403.17536 ILLUMINER: Instruction-tuned Large Language Models as Few-shot Intent Classifier
        29501, -- 2403.17919 LISA: Layerwise Importance Sampling for Memory-Efficient Large Language Model Fi
        29555, -- 2403.18680 Non-Linear Inference Time Intervention: Improving LLM Truthfulness
        29669, -- 2403.20249 Relation Rectification in Diffusion Model
        29674, -- 2403.20284 LayerNorm: A key component in parameter-efficient fine-tuning
        29726, -- 2404.00656 WavLLM: Towards Robust and Adaptive Speech Large Language Model
        29744, -- 2404.00862 Bailong: Bilingual Transfer Learning based on QLoRA and Zip-tie Embedding
        29895, -- 2404.02827 BAdam: A Memory Efficient Full Parameter Optimization Method for Large Language
        29949, -- 2404.03592 ReFT: Representation Finetuning for Language Models
        29986, -- 2404.04031 Willkommens-Merkel, Chaos-Johnson, and Tore-Klose: Modeling the Evaluative Meani
        30005, -- 2404.04316 Parameter Efficient Quasi-Orthogonal Fine-Tuning via Givens Rotation
        30020, -- 2404.04522 Q-PEFT: Query-dependent Parameter Efficient Fine-tuning for Text Reranking with
        30055, -- 2404.05086 A Note on LoRA
        30066, -- 2404.05333 PORTULAN ExtraGLUE Datasets and Models: Kick-starting a Benchmark for the Neural
        30210, -- 2404.07448 Transferable and Principled Efficiency for Open-Vocabulary Segmentation
        30211, -- 2404.07470 Scalable Language Model with Generalized Continual Learning
        30319, -- 2404.08886 EIVEN: Efficient Implicit Attribute Value Extraction using Multimodal LLM
        30328, -- 2404.09027 MING-MOE: Enhancing Medical Multi-Task Learning in Large Language Models with Sp
        30362, -- 2404.09610 LoRA Dropout as a Sparsity Regularizer for Overfitting Control
        30385, -- 2404.09976 Diffscaler: Enhancing the Generative Prowess of Diffusion Transformers
        30441, -- 2404.10934 Shears: Unstructured Sparsity with Neural Low-rank Adapter Search
        30486, -- 2404.11792 Enhancing Q&A with Domain-Specific Fine-Tuning and Iterative Reasoning: A Compar
        30612, -- 2404.13506 Parameter Efficient Fine Tuning: A Comprehensive Analysis Across Applications
        30626, -- 2404.13752 Adversarial Representation Engineering: A General Model Editing Framework for La
        30685, -- 2404.14779 Med42 -- Evaluating Fine-Tuning Strategies for Medical LLMs: Full-Parameter vs.
        30701, -- 2404.15159 MixLoRA: Enhancing Large Language Models Fine-Tuning with LoRA-based Mixture of
        30746, -- 2404.16022 PuLID: Pure and Lightning ID Customization via Contrastive Alignment
        30760, -- 2404.16339 Training-Free Unsupervised Prompt for Vision-Language Models
        30817, -- 2404.17245 Parameter Efficient Fine-tuning of Self-supervised ViTs without Catastrophic For
        30848, -- 2404.17778 MRScore: Evaluating Radiology Report Generation with LLM-based Reward System
        30881, -- 2404.18466 HFT: Half Fine-Tuning for Large Language Models
        30899, -- 2404.18911 Kangaroo: Lossless Self-Speculative Decoding via Double Early Exiting
        30953, -- 2405.00201 SPAFIT: Stratified Progressive Adaptation Fine-tuning for Pre-trained Large Lang
        30974, -- 2405.00557 Mixture of insighTful Experts (MoTE): The Synergy of Thought Chains and Expert M
        30982, -- 2405.00657 RST-LoRA: A Discourse-Aware Low-Rank Adaptation for Long Document Abstractive Su
        30987, -- 2405.00732 LoRA Land: 310 Fine-tuned LLMs that Rival GPT-4, A Technical Report
        31023, -- 2405.01536 Customizing Text-to-Image Models with a Single Image Pair
        31074, -- 2405.03003 Parameter-Efficient Fine-Tuning with Discrete Fourier Transform
        31131, -- 2405.04760 Large Language Models for Cyber Security: A Systematic Literature Review
        31249, -- 2405.07813 Localizing Task Information for Improved Model Merging and Compression
        31288, -- 2405.08553 Improving Transformers with Dynamically Composable Multi-Head Attention
        31415, -- 2405.11464 Efficient Prompt Tuning by Multi-Space Projection and Prompt Fusion
        31443, -- 2405.12130 MoRA: High-Rank Updating for Parameter-Efficient Fine-Tuning
        31512, -- 2405.13432 Disperse-Then-Merge: Pushing the Limits of Instruction Tuning via Alignment Tax
        31612, -- 2405.14739 FLoRA: Low-Rank Core Space for N-dimension
        31663, -- 2405.15179 VB-LoRA: Extreme Parameter Efficient Fine-Tuning with Vector Banks
        31714, -- 2405.15729 Optimizing Large Language Models for OpenAPI Code Completion
        31739, -- 2405.16057 SPP: Sparsity-Preserved Parameter-Efficient Fine-Tuning for Large Language Model
        31751, -- 2405.16284 Generating clickbait spoilers with an ensemble of large language models
        31782, -- 2405.16625 Few-shot Tuning of Foundation Models for Class-incremental Learning
        31833, -- 2405.17258 $\textit{Trans-LoRA}$: towards data-free Transferable Parameter Efficient Finetu
        31837, -- 2405.17357 DoRA: Enhancing Parameter-Efficient Fine-Tuning with Dynamic Rank Distribution
        31863, -- 2405.17604 LoRA-XS: Low-Rank Adaptation with Extremely Small Number of Parameters
        31881, -- 2405.17825 Diffusion Model Patching via Mixture-of-Prompts
        31888, -- 2405.17890 SLMRec: Distilling Large Language Models into Small for Sequential Recommendatio
        31922, -- 2405.18203 IAPT: Instruction-Aware Prompt Tuning for Large Language Models
        31929, -- 2405.18292 Semantic are Beacons: A Semantic Perspective for Unveiling Parameter-Efficient F
        32027, -- 2405.19597 SVFT: Parameter-Efficient Fine-Tuning with Singular Vectors
        32030, -- 2405.19670 One Token Can Help! Learning Scalable and Pluggable Virtual Tokens for Retrieval
        32073, -- 2405.20215 TS-Align: A Teacher-Student Collaborative Framework for Scalable Iterative Finet
        32080, -- 2405.20271 ETHER: Efficient Finetuning of Large-Scale Models with Hyperplane Reflections
        32096, -- 2405.20339 Visual Perception by Large Language Model's Weights
        32159, -- 2406.00132 QuanTA: Efficient High-Rank Fine-Tuning of LLMs with Quantum-Informed Tensor Ada
        32163, -- 2406.00209 Mamba State-Space Models Are Lyapunov-Stable Learners
        32187, -- 2406.00515 A Survey on Large Language Models for Code Generation
        32249, -- 2406.01563 LoFiT: Localized Fine-tuning on LLM Representations
        32263, -- 2406.01775 OLoRA: Orthonormal Low-Rank Adaptation of Large Language Models
        32368, -- 2406.03216 Choice of PEFT Technique in Continual Learning: Prompt Tuning is Not All You Nee
        32400, -- 2406.03792 Light-PEFT: Lightening Parameter-Efficient Fine-Tuning via Early Pruning
        32424, -- 2406.04165 Repurposing Language Models into Embedding Models: Finding the Compute-Optimal R
        32536, -- 2406.05344 MemeGuard: An LLM and VLM-based Framework for Advancing Content Moderation via M
        32597, -- 2406.06072 Adapting Pretrained ViTs with Convolution Injector for Visuo-Motor Control
        32614, -- 2406.06279 Multi-Prompting Decoder Helps Better Language Understanding
        32625, -- 2406.06391 Towards Lifelong Learning of Large Language Models: A Survey
        33017, -- 2406.10777 RoseLoRA: Row and Column-wise Sparse Low-rank Adaptation of Pre-trained Language
        33018, -- 2406.10785 ShareLoRA: Parameter Efficient and Robust Large Language Model Fine-tuning via S
        33123, -- 2406.11617 DELLA-Merging: Reducing Interference in Model Merging through Magnitude-Based Sa
        33134, -- 2406.11675 BLoB: Bayesian Low-Rank Adaptation by Backpropagation for Large Language Models
        33176, -- 2406.11909 Mixture-of-Subspaces in Low-Rank Adaptation
        33285, -- 2406.12832 LaMDA: Large Model Fine-Tuning via Spectrally Decomposed Low-Dimensional Adaptat
        33396, -- 2406.14377 CE-SSL: Computation-Efficient Semi-Supervised Learning for ECG-based Cardiovascu
        33441, -- 2406.14764 RE-AdaptIR: Improving Information Retrieval through Reverse Engineered Adaptatio
        33487, -- 2406.15334 Multimodal Task Vectors Enable Many-Shot Multimodal In-Context Learning
        33494, -- 2406.15480 On Giant's Shoulders: Effortless Weak to Strong by Dynamic Logits Fusion
        33513, -- 2406.15734 RankAdaptor: Hierarchical Rank Allocation for Efficient Fine-Tuning Pruned LLMs
        33558, -- 2406.16282 Reducing Fine-Tuning Memory Overhead by Approximate and Memory-Sharing Backpropa
        33572, -- 2406.16377 On the Transformations across Reward Model, Parameter Update, and In-Context Pro
        33631, -- 2406.17245 Unlocking Continual Learning Abilities in Language Models
        33632, -- 2406.17255 MPCODER: Multi-user Personalized Code Generator with Explicit and Implicit Style
        33640, -- 2406.17304 Leveraging LLMs for Dialogue Quality Measurement
        33655, -- 2406.17484 MedCare: Advancing Medical LLMs through Decoupling Clinical Alignment and Knowle
        33763, -- 2406.18708 Learn it or Leave it: Module Composition and Pruning for Continual Learning
        33817, -- 2406.19395 Dataset Size Recovery from LoRA Weights
        33870, -- 2407.00066 Compress then Serve: Serving Thousands of LoRA Adapters with Little Overhead
        33912, -- 2407.00737 LLM4GEN: Leveraging Semantic Representation of LLMs for Text-to-Image Generation
        33938, -- 2407.01091 M2QA: Multi-domain Multilingual Question Answering
        33956, -- 2407.01320 Increasing Model Capacity for Free: A Simple Strategy for Parameter Efficient Fi
        34002, -- 2407.01906 Let the Expert Stick to His Last: Expert-Specialized Fine-Tuning for Sparse Arch
        34032, -- 2407.02211 PromptIntern: Saving Inference Costs by Internalizing Recurrent Prompt during La
        34082, -- 2407.02987 LoRA-Guard: Parameter-Efficient Guardrail Adaptation for Content Moderation of L
        34089, -- 2407.03036 SAFT: Towards Out-of-Distribution Generalization in Fine-Tuning
        34156, -- 2407.03955 Meta-prompting Optimized Retrieval-augmented Generation
        34161, -- 2407.04003 Fully Fine-tuned CLIP Models are Efficient Few-Shot Learners
        34171, -- 2407.04079 AXOLOTL'24 Shared Task on Multilingual Explainable Semantic Change Modeling
        34237, -- 2407.05000 LoRA-GA: Low-Rank Adaptation with Gradient Approximation
        34336, -- 2407.06204 A Survey on Mixture of Experts
        34420, -- 2407.07523 SHERL: Synthesizing High Accuracy and Efficient Memory for Resource-Limited Tran
        34505, -- 2407.08674 Still-Moving: Customized Video Generation without Customized Video Data
        34551, -- 2407.09209 Pronunciation Assessment with Multi-modal Large Language Models
        34591, -- 2407.09781 Dense Multimodal Alignment for Open-Vocabulary 3D Scene Understanding
        34714, -- 2407.11239 From GaLore to WeLore: How Low-Rank Weights Non-uniformly Emerge from Low-Rank G
        34780, -- 2407.12036 Exploring Advanced Large Language Models with LLMsuite
        34826, -- 2407.12616 Missing Modality Prediction for Unpaired Multimodal Learning via Joint Embedding
        34914, -- 2407.13579 Towards Zero-Shot Multimodal Machine Translation
        34959, -- 2407.14153 ESP-MedSAM: Efficient Self-Prompting SAM for Universal Domain-Generalized Medica
        35004, -- 2407.14962 Recent Advances in Generative AI and Large Language Models: Current Status, Chal
        35011, -- 2407.15085 Learn to Preserve and Diversify: Parameter-Efficient Group with Orthogonal Regul
        35172, -- 2407.17533 SFPrompt: Communication-Efficient Split Federated Fine-Tuning for Large Pre-Trai
        35199, -- 2407.18078 PEFT-U: Parameter-Efficient Fine-Tuning for User Personalization
        35211, -- 2407.18242 LoRA-Pro: Are Low-Rank Adapters Properly Optimized?
        35285, -- 2407.19775 Model Agnostic Hybrid Sharding For Heterogeneous Distributed Inference
        35325, -- 2407.20557 CELLM: An Efficient Communication in Large Language Models Training for Federate
        35377, -- 2407.21571 PMoE: Progressive Mixture of Experts with Asymmetric Transformer for Continual L
        35381, -- 2407.21654 MTA-CLIP: Language-Guided Semantic Segmentation with Mask-Text Alignment
        35387, -- 2407.21721 Open-Vocabulary Audio-Visual Semantic Segmentation
        35395, -- 2407.21794 Generalized Out-of-Distribution Detection and Beyond in Vision Language Model Er
        35441, -- 2408.00690 Improving Text Embeddings for Smaller Language Models Using Contrastive Fine-tun
        35468, -- 2408.00981 Cross-domain Named Entity Recognition via Graph Matching
        35478, -- 2408.01099 Contribution-based Low-Rank Adaptation with Pre-training Model for Real Image Re
        35588, -- 2408.03092 Extend Model Merging from Fine-Tuned to Pre-Trained Large Language Models via We
        35667, -- 2408.04556 BA-LoRA: Bias-Alleviating Low-Rank Adaptation to Mitigate Catastrophic Inheritan
        35683, -- 2408.04693 Understanding the Performance and Estimating the Cost of LLM Fine-Tuning
        35799, -- 2408.06854 LoRA$^2$ : Multi-Scale Low-Rank Approximations for Fine-Tuning Large Language Mo
        35811, -- 2408.07057 A Survey on Model MoErging: Recycling and Routing Among Specialized Experts for
        35826, -- 2408.07337 KIND: Knowledge Integration and Diversion for Training Decomposable Models
        35873, -- 2408.08258 Snuffy: Efficient Whole Slide Image Classifier
        35967, -- 2408.09984 Boosting Open-Domain Continual Learning via Leveraging Intra-domain Category-awa
        35986, -- 2408.10280 NoRA: Nested Low-Rank Adaptation for Efficient Fine-Tuning Large Models
        35997, -- 2408.10548 Language Modeling on Tabular Data: A Survey of Foundations, Techniques and Evolu
        36075, -- 2408.11382 Towards Inducing Document-Level Abilities in Standard Multilingual Neural Machin
        36107, -- 2408.11855 FactorLLM: Factorizing Knowledge via Mixture of Experts for Large Language Model
        36138, -- 2408.12396 Cross-Domain Foundation Model Adaptation: Pioneering Computer Vision Models for
        36308, -- 2408.15600 Exploring Selective Layer Fine-Tuning in Federated Learning
        36314, -- 2408.15666 StyleRemix: Interpretable Authorship Obfuscation via Distillation and Perturbati
        36359, -- 2408.16264 LoraMap: Harnessing the Power of LoRA Connections
        36433, -- 2409.00133 A Survey for Large Language Models in Biomedicine
        36490, -- 2409.01156 TempMe: Video Temporal Token Merging for Efficient Text-Video Retrieval
        36651, -- 2409.04267 An overview of domain-specific foundation model: key technologies, applications
        36701, -- 2409.05746 LLMs Will Always Hallucinate, and We Need to Live With This
        36713, -- 2409.05976 FLoRA: Federated Fine-Tuning Large Language Models with Heterogeneous Low-Rank A
        36815, -- 2409.08248 TextBoost: Towards One-Shot Personalization of Text-to-Image Models via Fine-tun
        36839, -- 2409.08596 Large Language Model Can Transcribe Speech in Multi-Talker Scenarios with Versat
        36877, -- 2409.09273 Leveraging Foundation Models for Efficient Federated Learning in Resource-restri
        36896, -- 2409.09510 Comparing Retrieval-Augmentation and Parameter-Efficient Fine-Tuning for Privacy
        36909, -- 2409.09825 GP-GPT: Large Language Model for Gene-Phenotype Mapping
        36974, -- 2409.11022 GEIC: Universal and Multilingual Named Entity Recognition with Large Language Mo
        37169, -- 2409.14144 Interpreting Arithmetic Mechanism in Large Language Models through Comparative N
        37208, -- 2409.14924 Retrieval Augmented Generation (RAG) and Beyond: A Comprehensive Survey on How t
        37311, -- 2409.16722 PMSS: Pretrained Matrices Skeleton Selection for LLM Fine-tuning
        37324, -- 2409.17044 How to Connect Speech Foundation Models and Large Language Models? What Matters
        37592, -- 2410.00513 Cross-lingual Back-Parsing: Utterance Synthesis from Meaning Representation for
        37612, -- 2410.00938 MoS: Unleashing Parameter Efficiency of Low-Rank Adaptation with Mixture of Shar
        37649, -- 2410.01463 Selective Aggregation for Low-Rank Adaptation in Federated Learning
        37656, -- 2410.01497 DLP-LoRA: Efficient Task-Specific LoRA Fusion with a Dynamic, Lightweight Plugin
        37670, -- 2410.01623 Fira: Can We Achieve Full-rank Training of LLMs Under Low-rank Constraint?
        38067, -- 2410.05770 Efficient Few-shot Learning for Multi-label Classification of Scientific Documen
        38194, -- 2410.07172 Glider: Global and Local Instruction-Driven Expert Router
        38207, -- 2410.07383 SparseGrad: A Selective Method for Efficient Fine-tuning of MLP Layers
        38304, -- 2410.08661 QEFT: Quantization for Efficient Fine-Tuning of LLMs
        38327, -- 2410.09016 Parameter-Efficient Fine-Tuning of State Space Models
        38360, -- 2410.09432 FedEx-LoRA: Exact Aggregation for Federated and Efficient Fine-Tuning of Foundat
        38361, -- 2410.09437 MTL-LoRA: Low-Rank Adaptation for Multi-Task Learning
        38373, -- 2410.09644 Adapters for Altering LLM Vocabularies: What Languages Benefit the Most?
        38375, -- 2410.09692 ALLoRA: Adaptive Learning Rate Mitigates LoRA Fatal Flaws
        38485, -- 2410.10870 PortLLM: Personalizing Evolving Large Language Models with Training-Free and Por
        38553, -- 2410.11772 Layer-wise Importance Matters: Less Memory for Better Performance in Parameter-e
        38652, -- 2410.12928 DreamCraft3D++: Efficient Hierarchical 3D Generation with Multi-Plane Reconstruc
        38671, -- 2410.13136 Unlocking the Capabilities of Masked Generative Models for Image Synthesis via S
        38674, -- 2410.13184 Router-Tuning: A Simple and Effective Approach for Enabling Dynamic-Depth in Tra
        38718, -- 2410.13618 LoLDU: Low-Rank Adaptation via Lower-Diag-Upper Decomposition for Parameter-Effi
        38753, -- 2410.13841 A Unified View of Delta Parameter Editing in Post-Trained Large-Scale Models
        38830, -- 2410.14713 QuAILoRA: Quantization-Aware Initialization for LoRA
        38859, -- 2410.15148 Less is More: Parameter-Efficient Selection of Intermediate Tasks for Transfer L
        39009, -- 2410.17222 Context-aware Prompt Tuning: Advancing In-Context Learning with Adversarial Meth
        39037, -- 2410.17599 Cross-model Control: Improving Multiple Large Language Models in One-time Traini
        39048, -- 2410.17779 ADEM-VL: Adaptive and Embedded Fusion for Efficient Vision-Language Tuning
        39062, -- 2410.18035 MiLoRA: Efficient Mixture of Low-Rank Adaptation for Large Language Models Fine-
        39246, -- 2410.20650 NeuZip: Memory-Efficient Training and Inference with Dynamic Compression of Neur
        39248, -- 2410.20672 Relaxed Recursive Transformers: Effective Parameter Sharing with Layer-wise LoRA
        39257, -- 2410.20777 KD-LoRA: A Hybrid Approach to Efficient Fine-Tuning with LoRA and Knowledge Dist
        39307, -- 2410.21485 SpeechQE: Estimating the Quality of Direct Speech Translation
        39320, -- 2410.21747 MotionGPT-2: A General-Purpose Motion-Language Model for Motion Generation and U
        39388, -- 2410.23054 Controlling Language and Diffusion Models by Transporting Activations
        39623, -- 2411.02462 Parameter-Efficient Fine-Tuning of Large Language Models for Unit Test Generatio
        39801, -- 2411.05663 Online-LoRA: Task-free Online Continual Learning via Low Rank Adaptation
        39868, -- 2411.06971 MapSAM: Adapting Segment Anything Model for Automated Feature Detection in Histo
        40006, -- 2411.09539 A Practical Guide to Fine-tuning Language Models with Limited Data
        40118, -- 2411.11706 MC-LLaVA: Multi-Concept Personalized Vision-Language Model
        40236, -- 2411.13814 AutoMixQ: Self-Adjusting Quantization for High Performance Memory-Efficient Fine
        40303, -- 2411.14961 LoRA-FAIR: Federated LoRA Fine-Tuning with Aggregation and Initialization Refine
        40335, -- 2411.15232 BiomedCoOp: Learning to Prompt for Biomedical Vision-Language Models
        40388, -- 2411.15804 LoRA-Mini : Adaptation Matrices Decomposition and Selective Training
        40937, -- 2412.02890 EvRT-DETR: Latent Space Adaptation of Image Detectors for Event-based Vision
        40938, -- 2412.02904 Enhancing Trust in Large Language Models with Uncertainty-Aware Fine-Tuning
        41003, -- 2412.03599 CPTQuant -- A Novel Mixed Precision Post-Training Quantization Techniques for La
        41206, -- 2412.06071 KaSA: Knowledge-Aware Singular-Value Adaptation of Large Language Models
        41275, -- 2412.07021 Sequential Compression Layers for Efficient Federated Learning in Foundational M
        41288, -- 2412.07187 A New Federated Learning Framework Against Gradient Inversion Attacks
        41339, -- 2412.07771 PETALface: Parameter Efficient Transfer Learning for Low-resolution Face Recogni
        41361, -- 2412.08174 Can Graph Neural Networks Learn Language with Extremely Weak Text Supervision?
        41393, -- 2412.08587 Advancing Single and Multi-task Text Classification through Large Language Model
        41441, -- 2412.09169 DECOR:Decomposition and Projection of Text Embeddings for Text-to-Image Customiz
        41554, -- 2412.10416 SUPERMERGE: An Approach For Gradient-Based Model Merging
        41625, -- 2412.11509 Skip Tuning: Pre-trained Vision-Language Models are Effective and Efficient Adap
        41749, -- 2412.12865 Preference-Oriented Supervised Fine-Tuning: Favoring Target Model Over Aligned L
        41758, -- 2412.12951 FineGates: LLMs Finetuning with Compression using Stochastic Gates
        41872, -- 2412.14426 All-in-One Tuning and Structural Pruning for Domain-Specific LLMs
        42049, -- 2412.16974 Cannot or Should Not? Automatic Analysis of Refusal Composition in IFT/RLHF Data
        42056, -- 2412.17052 ViLBias: A Comprehensive Framework for Bias Detection through Linguistic and Vis
        42236, -- 2412.19616 Gradient Weight-normalized Low-rank Projection for Efficient LLM Training
        42251, -- 2412.19820 GaLore$+$: Boosting Low-Rank Adaptation for LLMs with Cross-Head Projection
        42258, -- 2412.20004 Adaptive Parameter-Efficient Federated Fine-Tuning on Heterogeneous Devices
        42286, -- 2412.20597 GliLem: Leveraging GliNER for Contextualized Lemmatization in Estonian
        42349, -- 2501.00365 Low-Rank Adaptation for Foundation Models: A Comprehensive Review
        42358, -- 2501.00530 Superposition in Transformers: A Novel Way of Building Mixture of Experts
        42407, -- 2501.01164 Towards Interactive Deepfake Analysis
        42489, -- 2501.02497 Test-time Computing: from System-1 Thinking to System-2 Thinking
        42572, -- 2501.03829 Spectral-Aware Low-Rank Adaptation for Speaker Verification
        42606, -- 2501.04315 RoRA: Efficient Fine-Tuning of LLM with Reliability Optimization for Rank Adapta
        42791, -- 2501.07278 Lifelong Learning of Large Language Model based Agents: A Roadmap
        42870, -- 2501.08727 Transformed Low-rank Adaptation via Tensor Decomposition and Its Applications to
        42894, -- 2501.09194 Grounding Text-To-Image Diffusion Models For Controlled High-Quality Image Gener
        42924, -- 2501.09705 Practical Continual Forgetting for Pre-trained Vision Models
        42974, -- 2501.10326 Large language models for automated scholarly paper review: A survey
        43055, -- 2501.12067 EDoRA: Efficient Weight-Decomposed Low-Rank Adaptation via Singular Value Decomp
        43162, -- 2501.13787 Parameter-Efficient Fine-Tuning for Foundation Models
        43252, -- 2501.15377 Fine Tuning without Catastrophic Forgetting via Selective Low Rank Adaptation
        43292, -- 2501.15955 Rethinking the Bias of Foundation Model under Long-tailed Distribution
        43418, -- 2501.18475 CLoQ: Enhancing Fine-Tuning of Quantized LLMs via Calibrated LoRA Initialization
        43459, -- 2501.19084 Laser: Efficient Language-Guided Segmentation in Neural Radiance Fields
        43559, -- 2502.01247 Polynomial, trigonometric, and tropical activations
        43592, -- 2502.01657 Improving Rule-based Reasoning in LLMs via Neurosymbolic Representations
        43788, -- 2502.04412 Decoder-Only LLMs are Better Controllers for Diffusion Models
        43967, -- 2502.06820 LoCA: Location-Aware Cosine Adaptation for Parameter-Efficient Fine-Tuning
        44061, -- 2502.07855 Vision-Language Models for Edge Networks: A Comprehensive Survey
        44126, -- 2502.08905 DiffoRA: Enabling Parameter-Efficient LLM Fine-Tuning via Differential Low-Rank
        44145, -- 2502.09284 SparQLe: Speech Queries to Text Translation Through LLMs
        44264, -- 2502.10993 RoseRAG: Robust Retrieval-augmented Generation with Small-scale LLMs via Margin-
        44471, -- 2502.12663 Demystifying Multilingual Chain-of-Thought in Process Reward Modeling
        44646, -- 2502.14409 Unstructured Evidence Attribution for Long Context Query Focused Summarization
        44658, -- 2502.14538 LoRA-GGPO: Mitigating Double Descent in LoRA Fine-Tuning via Gradient-Guided Per
        44763, -- 2502.15483 MoMa: A Modular Deep Learning Framework for Material Property Prediction
        44787, -- 2502.15809 Black Sheep in the Herd: Playing with Spuriously Correlated Attributes for Visio
        44811, -- 2502.15957 R$^3$Mem: Bridging Memory Retention and Retrieval via Reversible Compression
        44865, -- 2502.16767 A Hybrid Approach to Information Retrieval and Answer Generation for Regulatory
        44882, -- 2502.16894 Make LoRA Great Again: Boosting LoRA with Adaptive Singular Values and Mixture-o
        45035, -- 2502.18635 Faster, Cheaper, Better: Multi-Objective Hyperparameter Optimization for LLM and
        45091, -- 2502.19429 scMamba: A Pre-Trained Model for Single-Nucleus RNA Sequencing Analysis in Neuro
        45197, -- 2502.20582 CS-PaperSum: A Large-Scale Dataset of AI-Generated Summaries for Scientific Pape
        45231, -- 2502.21321 LLM Post-Training: A Deep Dive into Reasoning Large Language Models
        45547, -- 2503.04543 Keeping Yourself is Important in Downstream Tuning Multimodal Large Language Mod
        45761, -- 2503.07103 Quantizing Large Language Models for Code Generation: A Differentiated Replicati
        46141, -- 2503.11335 APLA: A Simple Adaptation Method for Vision Transformers
        46222, -- 2503.12780 LangDA: Building Context-Awareness via Language for Domain Adaptive Semantic Seg
        46452, -- 2503.16071 Tuning LLMs by RAG Principles: Towards LLM-native Memory
        46615, -- 2503.18225 DeLoRA: Decoupling Angles and Strength in Low-rank Adaptation
        46661, -- 2503.18860 HunyuanPortrait: Implicit Condition Control for Enhanced Portrait Animation
        46716, -- 2503.19530 VectorFit : Adaptive Singular & Bias Vector Fine-Tuning of Pre-trained Foundatio
        46886, -- 2503.21782 Mobile-VideoGPT: Fast and Accurate Video Understanding Language Model
        46892, -- 2503.21838 MSPLoRA: A Multi-Scale Pyramid Low-Rank Adaptation for Efficient Model Fine-Tuni
        46960, -- 2503.22764 Boosting Large Language Models with Mask Fine-Tuning
        47109, -- 2504.00661 DynMoLE: Boosting Mixture of LoRA Experts Fine-Tuning with a Hybrid Routing Mech
        47116, -- 2504.00784 CellVTA: Enhancing Vision Foundation Models for Accurate Cell Segmentation and C
        47207, -- 2504.02231 AC-LoRA: Auto Component LoRA for Personalized Artistic Style Image Generation
        47280, -- 2504.03254 SARLANG-1M: A Benchmark for Vision-Language Modeling in SAR Image Understanding
        47468, -- 2504.07097 Sculpting Subspaces: Constrained Full Fine-Tuning in LLMs for Continual Learning
        47541, -- 2504.08247 Millions of States: Designing a Scalable MoE Architecture with RWKV-7 Meta-learn
        47627, -- 2504.09724 A Survey on Efficient Vision-Language Models
        47783, -- 2504.12080 DC-SAM: In-Context Segment Anything in Images and Videos via Dual Consistency
        47812, -- 2504.12397 Activated LoRA: Fine-tuned LLMs for Intrinsics
        48031, -- 2504.15669 DINOv2-powered Few-Shot Semantic Segmentation: A Unified Framework via Cross-Mod
        48090, -- 2504.16921 IberBench: LLM Evaluation on Iberian Languages
        48132, -- 2504.18147 NoEsis: Differentially Private Knowledge Transfer in Modular LLM Adaptation
        48148, -- 2504.18580 Parameter-Efficient Checkpoint Merging via Metrics-Weighted Averaging
        48320, -- 2505.00693 Robotic Visual Instruction
        48520, -- 2505.05023 Split Matching for Inductive Zero-shot Semantic Segmentation
        48579, -- 2505.06267 AKD : Adversarial Knowledge Distillation For Large Language Models Alignment on
        48816, -- 2505.10939 GenKnowSub: Improving Modularity and Reusability of LLMs through General Knowled
        49147, -- 2505.14256 FuxiMT: Sparsifying Large Language Models for Chinese-Centric Multilingual Machi
        49306, -- 2505.15581 UWSAM: Segment Anything Model Guided Underwater Instance Segmentation and A Larg
        49576, -- 2505.18125 TabSTAR: A Foundation Tabular Model With Semantically Target-Aware Representatio
        49786, -- 2505.19912 APE: A Data-Centric Benchmark for Efficient LLM Adaptation in Text Summarization
        49821, -- 2505.20154 UORA: Uniform Orthogonal Reinitialization Adaptation in Parameter-Efficient Fine
        49875, -- 2505.20355 GraLoRA: Granular Low-Rank Adaptation for Parameter-Efficient Fine-Tuning
        49906, -- 2505.20809 Improved Representation Steering for Language Models
        49910, -- 2505.20897 Cross from Left to Right Brain: Adaptive Text Dreamer for Vision-and-Language Na
        49977, -- 2505.21795 SANSA: Unleashing the Hidden Semantics in SAM2 for Few-Shot Segmentation
        50167, -- 2505.23808 DenseLoRA: Dense Low-Rank Adaptation of Large Language Models
        50357, -- 2506.01049 Taming LLMs by Scaling Learning Rates with Gradient Grouping
        50407, -- 2506.01850 MoDA: Modulation Adapter for Fine-Grained Visual Grounding in Instructional MLLM
        50504, -- 2506.03230 DiaBlo: Diagonal Blocks Are Sufficient For Finetuning
        50774, -- 2506.07621 LoRMA: Low-Rank Multiplicative Adaptation for LLMs
        50883, -- 2506.08887 DiscoVLA: Discrepancy Reduction in Vision, Language, and Alignment for Parameter
        51090, -- 2506.12015 EMLoC: Emulator-based Memory-efficient Fine-tuning with LoRA Correction
        51335, -- 2506.17497 From Generality to Mastery: Composer-Style Symbolic Music Generation via Large-S
        51362, -- 2506.18267 ARD-LoRA: Dynamic Rank Allocation for Parameter-Efficient Fine-Tuning of Foundat
        51426, -- 2506.19741 Noise Consistency Training: A Native Approach for One-Step Generator in Learning
        51435, -- 2506.19847 Orthogonal Finetuning Made Scalable
        51597, -- 2507.00029 LoRA-Mixer: Coordinate Modular LoRA Experts Through Serial Attention Routing
        51644, -- 2507.02503 Continual Gradient Low-Rank Projection Fine-Tuning for LLMs
        51700, -- 2507.04487 LoSiA: Efficient High-Rank Fine-Tuning via Subnet Localization and Optimization
        51975, -- 2507.13984 CSD-VAR: Content-Style Decomposition in Visual Autoregressive Models
        52645, -- 2509.03740 Singular Value Few-shot Adaptation of Vision-Language Models
        52916, -- 2509.17786 Accurate and Efficient Low-Rank Model Merging in Core Space
        52924, -- 2509.16633 When Big Models Train Small Ones: Label-Free Model Parity Alignment for Efficien
        53253, -- 2510.04399 Utility-Learning Tension in Self-Modifying Agents
        54515, -- 2512.02492 YingVideo-MV: Music-Driven Multi-Stage Video Generation
        54526, -- 2512.02351 Understanding and Harnessing Sparsity in Unified Multimodal Models
        54550, -- 2512.03073 Economies of Open Intelligence: Tracing Power & Participation in the Model Ecosy
        54590, -- 2512.04844 Mitigating Catastrophic Forgetting in Target Language Adaptation of LLMs via Sou
        54830, -- 2512.07328 ContextAnyone: Context-Aware Diffusion for Character-Consistent Text-to-Video Ge
        55350, -- 2601.00756 Memory Bank Compression for Continual Adaptation of Large Language Models
        55708, -- 2602.02103 No Global Plan in Chain-of-Thought: Uncover the Latent Planning Horizon of LLMs
        55841, -- 2602.04998 Learning Rate Matters: Vanilla LoRA May Suffice for LLM Fine-tuning
        56220, -- 2602.16835 NeST: Neuron Selective Tuning for LLM Safety
        56559, -- 2603.08708 FVG-PT: Adaptive Foreground View-Guided Prompt Tuning for Vision-Language Models
        56567, -- 2603.07236 HY-WU (Part I): An Extensible Functional Neural Memory Framework and An Instanti
        57492, -- 2604.14004 Memory Transfer Learning: How Memories are Transferred Across Domains in Coding
        57606, -- 2604.18267 MARCO: Navigating the Unseen Space of Semantic Correspondence
        57633, -- 2604.19254 ShadowPEFT: Shadow Network for Parameter-Efficient Fine-Tuning
        57687, -- 2604.19902 MMCORE: MultiModal COnnection with Representation Aligned Latent Embeddings
        57873, -- 2604.23665 HAC: Parameter-Efficient Hyperbolic Adaptation of CLIP for Zero-Shot VQA
        57927, -- 2604.21637 Multilinguality at the Edge: Developing Language Models for the Global South
        58011, -- 2604.19018 Local Linearity of LLMs Enables Activation Steering via Model-Based Linear Optim
        58078, -- 2509.15974 BEFT: Bias-Efficient Fine-Tuning of Language Models in Low-Data Regimes
        58218, -- 2604.12502 SEATrack: Simple, Efficient, and Adaptive Multimodal Tracker
        58281, -- 2604.11082 RESP: Reference-guided Sequential Prompting for Visual Glitch Detection in Video
        58664, -- 2604.00912 ProCap: Projection-Aware Captioning for Spatial Augmented Reality
        58935, -- 2603.23942 The Missing Adapter Layer for Research Computing
        59171, -- 2603.18774 SEAR: Simple and Efficient Adaptation of Visual Geometric Transformers for RGB+T
        59202, -- 2603.17558 Zipper-LoRA: Dynamic Parameter Decoupling for Speech-LLM based Multilingual Spee
        59288, -- 2603.16428 An Efficient Heterogeneous Co-Design for Fine-Tuning on a Single GPU
        59662, -- 2603.08647 Grow, Don't Overwrite: Fine-tuning Without Forgetting
        59823, -- 2603.05813 Activation Steering for Accent Adaptation in Speech Foundation Models
        59961, -- 2603.02934 On the Structural Limitations of Weight-Based Neural Adaptation and the Role of
        59976, -- 2603.02692 FiDeSR: High-Fidelity and Detail-Preserving One-Step Diffusion Super-Resolution
        59992, -- 2603.02885 MuxTune: Efficient Multi-Task LLM Fine-Tuning in Multi-Tenant Datacenters via Sp
        60073, -- 2603.01174 VP-Hype: A Hybrid Mamba-Transformer Framework with Visual-Textual Prompting for
        60121, -- 2603.00573 CoMoL: Efficient Mixture of LoRA Experts via Dynamic Core Space Merging
        60196, -- 2602.00477 Intention-Adaptive LLM Fine-Tuning for Text Revision Generation
        60447, -- 2602.18628 Non-Interfering Weight Fields: Treating Model Parameters as a Continuously Exten
        60532, -- 2602.16430 Designing Production-Scale OCR for India: Multilingual and Domain-Specific Syste
        60689, -- 2505.11771 Residual Feature Integration is Sufficient to Prevent Negative Transfer
        60745, -- 2602.12323 The Appeal and Reality of Recycling LoRAs with Adaptive Merging
        60777, -- 2602.11726 Dopamine: Brain Modes, Not Brains
        61119, -- 2602.06499 FCDP: Fully Cached Data Parallel for Communication-Avoiding Large-Scale Training
        61257, -- 2602.04337 Fine-tuning Pre-trained Vision-Language Models in a Human-Annotation-Free Manner
        61284, -- 2602.04101 Interfaze: The Future of AI is built on Task-Specific Small Models
        61335, -- 2602.03493 Least but not Last: Fine-tuning Intermediate Principal Components for Better Per
        61357, -- 2602.03220 PokeFusion Attention: Enhancing Reference-Free Style-Conditioned Generation
        61463, -- 2602.01745 Probability-Entropy Calibration: An Elastic Indicator for Adaptive Fine-tuning
        61482, -- 2602.01599 The Multiple Ticket Hypothesis: Random Sparse Subnetworks Suffice for RLVR
        61488, -- 2602.01522 When Is Rank-1 Enough? Geometry-Guided Initialization for Parameter-Efficient Fi
        61713, -- 2601.22708 A Unified Study of LoRA Variants: Taxonomy, Review, Codebase, and Empirical Eval
        61961, -- 2601.19739 TokenSeek: Memory Efficient Fine Tuning via Instance-Aware Token Ditching
        62031, -- 2601.18699 Mechanistic Analysis of Catastrophic Forgetting in Large Language Models During
        62091, -- 2601.17616 Split-on-Share: Mixture of Sparse Experts for Task-Agnostic Continual Learning
        62123, -- 2601.17126 EveNet: A Foundation Model for Particle Collision Data Analysis
        62146, -- 2601.17086 SonoEdit: Null-Space Constrained Knowledge Editing for Pronunciation Correction
        62177, -- 2602.00084 Why LoRA Resists Label Noise: A Theoretical Framework for Noise-Robust Parameter
        62312, -- 2601.13580 Neural Organ Transplantation (NOT): Checkpoint-Based Modular Adaptation for Tran
        62371, -- 2601.12906 Gated Differentiable Working Memory for Long-Context Language Modeling
        62398, -- 2601.11931 Language-Guided and Motion-Aware Gait Representation for Generalizable Recogniti
        62567, -- 2601.08209 Generation-Augmented Generation: A Plug-and-Play Framework for Private Knowledge
        62780, -- 2601.05038 ArcAligner: Adaptive Recursive Aligner for Compressed Context Embeddings in RAG
        63219, -- 2512.23537 AnyMS: Bottom-up Attention Decoupling for Layout-guided and Training-free Multi-
        63289, -- 2512.22027 Patch-Discontinuity Mining for Generalized Deepfake Detection
        63300, -- 2601.09718 StatLLaMA: Multi-Stage training for domain-optimized statistical large language
        63451, -- 2512.19069 Can abstract concepts from LLM improve SLM performance?
        63935, -- 2512.08524 Beyond Real Weights: Hypercomplex Representations for Stable Quantization
        64127, -- 2512.04513 BiTAgent: A Task-Aware Modular Framework for Bidirectional Coupling between Mult
        64208, -- 2512.02764 PEFT-Factory: Unified Parameter-Efficient Fine-Tuning of Autoregressive Large La
        64281, -- 2512.01512 MCAT: Scaling Many-to-Many Speech-to-Text Translation with MLLMs to 70 Languages
        64374, -- 2512.00319 RL-Struct: A Lightweight Reinforcement Learning Framework for Reliable Structure
        64391, -- 2511.23377 DEAL-300K: Diffusion-based Editing Area Localization with a 300K-Scale Dataset a
        64655, -- 2410.01870 PEANuT: Parameter-Efficient Adaptation with Weight-aware Neural Tweakers
        64801, -- 2511.16069 ILoRA: Federated Learning with Low-Rank Adaptation for Heterogeneous Client Aggr
        65014, -- 2511.11315 LAET: A Layer-wise Adaptive Ensemble Tuning Framework for Pretrained Language Mo
        65064, -- 2511.10283 Behavior Modeling for Training-free Building of Private Domain Multi Agent Syste
        65154, -- 2511.08484 Patching LLM Like Software: A Lightweight Method for Improving Safety Policy in
        65186, -- 2511.07934 Laytrol: Preserving Pretrained Knowledge in Layout Control for Multimodal Diffus
        65273, -- 2511.06024 Towards Implicit Aggregation: Robust Image Representation for Place Recognition
        65529, -- 2511.00797 Attention Saturation and Gradient Suppression at Inflection Layers: Diagnosing a
        65760, -- 2510.24037 Kernelized Sparse Fine-Tuning with Bi-level Parameter Competition for Vision Mod
        65842, -- 2510.22747 Low-Resource Dialect Adaptation of Large Language Models: A French Dialect Case-
        65887, -- 2510.21958 A Stylometric Application of Large Language Models
        65907, -- 2510.21461 Enhancing Video Inpainting with Aligned Frame Interval Guidance
        66030, -- 2510.19640 Latent Space Factorization in LoRA
        66085, -- 2510.18725 SemiAdapt and SemiLoRA: Efficient Domain Adaptation for Transformer-based Low-Re
        66277, -- 2510.15103 Continual Learning via Sparse Memory Finetuning
        66371, -- 2510.13580 Sparse Subnetwork Enhancement for Underrepresented Languages in Large Language M
        66541, -- 2305.14019 ChipGPT: How far are we from natural language hardware design
        66711, -- 2510.08396 FlyLoRA: Boosting Task Decoupling and Parameter Efficiency via Implicit Rank-Wis
        66904, -- 2510.05468 AMAQ: Adaptive Mixed-bit Activation Quantization for Collaborative Parameter Eff
        66947, -- 2510.04539 C3Editor: Achieving Controllable Consistency in 2D Model for 3D Editing
        66955, -- 2510.04454 Mitigating Forgetting Between Supervised and Reinforcement Learning Yields Stron
        67129, -- 2510.01704 Holistic Order Prediction in Natural Scenes
        67268, -- 2510.00206 LoRAFusion: Efficient LoRA Fine-Tuning for LLMs
        67566, -- 2509.23659 Aligning LLMs for Multilingual Consistency in Enterprise Applications
        67754, -- 2508.18244 Type-Compliant Adaptation Cascades: Adapting Programmatic LM Workflows to Data
        67953, -- 2509.18868 Memory in Large Language Models: Mechanisms, Evaluation and Evolution
        67975, -- 2509.18480 SimpleFold: Folding Proteins is Simpler than You Think
        68025, -- 2509.17489 MapCoder-Lite: Distilling Multi-Agent Coding into a Single Small LLM
        68197, -- 2509.14957 DF-LLaVA: Unlocking MLLM's potential for Synthetic Image Detection via Prompt-Gu
        68313, -- 2509.13240 Don't Forget the Nonlinearity: Unlocking Activation Functions in Efficient Fine-
        68437, -- 2509.10971 PHLoRA: data-free Post-hoc Low-Rank Adapter extraction from full-rank checkpoint
        68504, -- 2509.09119 Sensitivity-LoRA: Low-Load Sensitivity-Based Fine-Tuning for Large Language Mode
        68852, -- 2509.01842 GradES: Significantly Faster Training in Transformers with Gradient-Based Early
        69230, -- 2508.17638 Dynamic Embedding of Hierarchical Visual Features for Efficient Vision-Language
        69272, -- 2508.17184 Towards Alignment-Centric Paradigm: A Survey of Instruction Tuning in Large Lang
        69430, -- 2508.14465 DreamSwapV: Mask-guided Subject Swapping for Any Customized Video Editing
        69915, -- 2508.07285 A Survey on Non-Intrusive ASR Refinement: From Output-Level Correction to Full-M
        69971, -- 2508.06360 Cyberbullying Detection via Aggression-Enhanced Prompting
        70054, -- 2508.11670 RRRA: Resampling and Reranking through a Retriever Adapter
        70185, -- 2508.03566 SAM2-UNeXT: An Improved High-Resolution Baseline for Adapting Foundation Models
        70489, -- 2507.23373 Multi-Prompt Progressive Alignment for Multi-Source Unsupervised Domain Adaptati
        70519, -- 2507.22872 TR-PTS: Task-Relevant Parameter and Token Selection for Efficient Tuning
        70555, -- 2507.22342 UFV-Splatter: Pose-Free Feed-Forward 3D Gaussian Splatting Adapted to Unfavorabl
        71043, -- 2507.21117 A Comprehensive Review on Harnessing Large Language Models to Overcome Recommend
        71235, -- 2507.10586 AutoRAG-LoRA: Hallucination-Triggered Knowledge Retuning via Lightweight Adapter
        71365, -- 2507.05346 LoRA-Augmented Generation (LAG) for Knowledge-Intensive Language Tasks
        71493, -- 2506.01631 Gradient-Based Model Fingerprinting for LLM Similarity Detection and Family Clas
        71608, -- 2507.02964 Less Data, More Security: Advancing Cybersecurity LLMs Specialization via Resour
        71615, -- 2506.23700 MedSAM-CA: A CNN-Augmented ViT with Attention-Enhanced Multi-Scale Fusion for Me
        71649, -- 2506.23136 LLM-Assisted Question-Answering on Technical Documents Using Structured Data-Awa
        71727, -- 2506.24092 WaRA: Wavelet Low Rank Adaptation
        71745, -- 2506.19613 Position: Intelligent Science Laboratory Requires the Integration of Cognitive a
        71813, -- 2506.17759 LoLA-SpecViT: Local Attention SwiGLU Vision Transformer with LoRA for Hyperspect
        71829, -- 2506.17159 Co-Seg++: Mutual Prompt-Guided Collaborative Learning for Versatile Medical Segm
        71905, -- 2506.15251 Singular Value Decomposition on Kronecker Adaptation for Large Language Model
        72010, -- 2506.11638 LoRA-Gen: Specializing Large Language Model via Online LoRA Generation
        72153, -- 2506.07647 Foundation Model Empowered Synesthesia of Machines (SoM): AI-native Intelligent
        72180, -- 2506.06844 Adapt Once, Thrive with Updates: Transferable Parameter-Efficient Fine-Tuning on
        72260, -- 2506.12072 TrueGL: A Truthful, Reliable, and Unified Engine for Grounded Learning in Full-S
        72314, -- 2506.03133 PoLAR: Polar-Decomposed Low-Rank Adapter Representation
        72327, -- 2506.02916 Towards Transfer-Efficient Multi-modal Sequential Recommendation with State Spac
        72358, -- 2505.15380 Accelerating Autoregressive Speech Synthesis Inference With Speech Speculative D
        72373, -- 2506.01935 Low-Rank Head Avatar Personalization with Registers
        72502, -- 2506.00200 Structuring Radiology Reports: Challenging LLMs with Lightweight Models
        72524, -- 2506.15702 Minifinetuning: Low-Data Generation Domain Adaptation through Corrective Self-Di
        72557, -- 2505.23094 MAP: Revisiting Weight Decomposition for Low-Rank Adaptation
        72591, -- 2505.22120 LoKI: Low-damage Knowledge Implanting of Large Language Models
        72603, -- 2505.21942 Continual Learning Beyond Experience Rehearsal and Full Model Surrogates
        72831, -- 2505.17359 Towards VM Rescheduling Optimization Through Deep Reinforcement Learning
        72864, -- 2505.16227 Explain Less, Understand More: Jargon Detection via Personalized Parameter-Effic
        72871, -- 2412.20157 UniRestorer: Universal Image Restoration via Adaptively Estimating Image Degrada
        72959, -- 2505.13061 3D Visual Illusion Depth Estimation
        72982, -- 2505.12532 Exploring Sparsity for Parameter Efficient Fine Tuning Using Wavelets
        72988, -- 2505.12455 AltLoRA: Towards Better Gradient Approximation in Low-Rank Adaptation with Alter
        73004, -- 2505.11998 Parameter Efficient Continual Learning with Dynamic Low-Rank Adaptation
        73035, -- 2505.11235 Efficient Orthogonal Fine-Tuning with Principal Subspace Adaptation
        73174, -- 2505.03556 A Comprehensive Survey of Large AI Models for Future Communications: Foundations
        73185, -- 2403.16137 A Survey on Self-Supervised Graph Foundation Models: Knowledge-Based Perspective
        73263, -- 2504.20570 ReCIT: Reconstructing Full Private Data from Gradient in Parameter-Efficient Fin
        73339, -- 2504.17902 CAMU: Context Augmentation for Meme Understanding
        73458, -- 2504.13407 LoRA-Based Continual Learning with Constraints on Critical Parameter Changes
        73742, -- 2504.01521 Domain Guidance: A Simple Transfer Approach for a Pre-trained Diffusion Model
        73786, -- 2504.00254 ElaLoRA: Elastic & Learnable Low-Rank Adaptation for Efficient Model Fine-Tuning
        73905, -- 2503.18338 SPMTrack: Spatio-Temporal Parameter-Efficient Fine-Tuning with Mixture of Expert
        73926, -- 2503.17338 Capturing Individual Human Preferences with Reward Features
        74168, -- 2503.08154 S2A: A Unified Framework for Parameter and Memory Efficient Transfer Learning
        74230, -- 2503.05431 Quantum-PEFT: Ultra parameter-efficient fine-tuning
        74272, -- 2503.04058 EVE: Towards End-to-End Video Subtitle Extraction with Vision-Language Models
        74345, -- 2503.01419 Parameter-Efficient Fine-Tuning of Large Language Models via Deconvolution in Su
        74368, -- 2503.00634 Efficiently Editing Mixture-of-Experts Models with Compressed Experts
        74398, -- 2503.01905 PaCA: Partial Connection Adaptation for Efficient Fine-Tuning
        74435, -- 2502.20420 Chitranuvad: Adapting Multi-Lingual LLMs for Multimodal Translation
        74436, -- 2503.05786 FedMentalCare: Towards Privacy-Preserving Fine-Tuned LLMs to Analyze Mental Heal
        74485, -- 2502.17920 C-LoRA: Continual Low-Rank Adaptation for Pre-trained Models
        74774, -- 2502.06501 Learning Clustering-based Prototypes for Compositional Zero-shot Learning
        74855, -- 2501.12983 LLM4WM: Adapting LLM for Wireless Multi-Tasking
        74909, -- 2407.16920 Train-Attention: Meta-Learning Where to Focus in Continual Knowledge Learning
        75518, -- 2412.08528 Efficient Continual Learning for Small Language Models with a Discrete Key-Value
        75638, -- 2412.00784 EDTformer: An Efficient Decoder Transformer for Visual Place Recognition
        75666, -- 2411.19154 DESIRE: Dynamic Knowledge Consolidation for Rehearsal-Free Continual Learning
        75861, -- 2411.02992 Efficient and Effective Adaptation of Multimodal Foundation Models in Sequential
        75873, -- 2411.01800 Expanding Sparse Tuning for Low Memory Usage
        75982, -- 2410.17055 Optimal Design for Reward Modeling in RLHF
        75987, -- 2405.16747 Understanding Linear Probing then Fine-tuning Language Models from NTK Perspecti
        76003, -- 2410.15266 GSSF: Generalized Structural Sparse Function for Deep Cross-modal Metric Learnin
        76267, -- 2405.17461 EMR-Merging: Tuning-Free High-Performance Model Merging
        76330, -- 2409.13501 HUT: A More Computation Efficient Fine-Tuning Method With Hadamard Updated Trans
        76370, -- 2409.10472 Towards Semantic Versioning of Open Pre-trained Language Model Releases on Huggi
        76440, -- 2409.04999 Visual Grounding with Multi-modal Conditional Adaptation
        76573, -- 2408.09078 An Exploratory Study on Fine-Tuning Large Language Models for Secure Code Genera
        76646, -- 2408.01119 Task Prompt Vectors: Effective Initialization through Multi-Task Soft-Prompt Tra
        76665, -- 2407.20516 Machine Unlearning in Generative AI: A Survey
        76757, -- 2407.09946 Low-Rank Interconnected Adaptation across Layers
        76759, -- 2407.09801 IoT-LM: Large Multisensory Language Models for the Internet of Things
        76849, -- 2407.01235 A Fingerprint for Large Language Models
        76946, -- 2406.13046 Bayesian-LoRA: LoRA based Parameter Efficient Fine-Tuning using Optimal Quantiza
        77013, -- 2406.09044 MiLoRA: Harnessing Minor Singular Components for Parameter-Efficient LLM Finetun
        77019, -- 2406.08447 The Impact of Initialization on LoRA Finetuning Dynamics
        77025, -- 2406.08068 Large Language Models Meet Text-Centric Multimodal Sentiment Analysis: A Survey
        77114, -- 2406.06564 SwitchLoRA: Switched Low-Rank Adaptation Can Learn Full-Rank Information
        77117, -- 2406.00773 Diffusion Tuning: Transferring Diffusion Models via Chain of Forgetting
        77229, -- 2405.14124 Mixture of Experts Meets Prompt-Based Continual Learning
        77294, -- 2405.06368 DP-DyLoRA: Fine-Tuning Transformer-Based Models On-Device under Differentially P
        77355, -- 2405.01591 Simplifying Multimodality: Unimodal Approach to Multimodal Challenges in Radiolo
        77357, -- 2404.18322 BlockLLM: Multi-tenant Finer-grained Serving for Large Language Models
        77432, -- 2404.09957 How to build the best medical image segmentation algorithm using foundation mode
        77525, -- 2404.01077 Efficient Prompting Methods for Large Language Models: A Survey
        77569, -- 2403.18271 Unleashing the Potential of SAM for Medical Adaptation via Hierarchical Decoding
        77572, -- 2403.17589 Dual Memory Networks: A Versatile Adaptation Approach for Vision-Language Models
        77726, -- 2403.00108 LoRATK: LoRA Once, Backdoor Everywhere in the Share-and-Play Ecosystem
        77729, -- 2402.19231 CricaVPR: Cross-image Correlation-aware Representation Learning for Visual Place
        77857, -- 2402.02242 Parameter-Efficient Fine-Tuning for Pre-Trained Vision Models: A Survey and Benc
        77995, -- 2401.03217 Understanding Large-Language Model (LLM)-powered Human-Robot Interaction
        78046, -- 2312.14923 Fast-NTK: Parameter-Efficient Unlearning for Large-Scale Models
        78415, -- 2310.03986 Robust Multimodal Learning with Missing Modalities via Parameter-Efficient Adapt
        78519, -- 2309.09055 Exploring the impact of low-rank adaptation on the performance, efficiency, and
        78569, -- 2309.01507 Memory Efficient Optimizers with 4-bit States
        78794, -- 2307.03217 Quantification of Uncertainty with Adversarial Models
        78971, -- 2305.17455 CrossGET: Cross-Guided Ensemble of Tokens for Accelerating Vision-Language Trans
        79132, -- 2304.07575 What Makes Good In-context Demonstrations for Code Intelligence Tasks with LLMs?
        79646, -- 2210.11265 Disentangling Reasoning Capabilities from Language Models with Compositional Rea
        79901, -- 2206.06619 TransVG++: End-to-End Visual Grounding with Language Conditioned Vision Transfor
        80047, -- 2204.10432 Improving the Generalizability of Depression Detection by Leveraging Clinical Qu
        80367, -- 2111.12993 PolyViT: Co-training Vision Transformers on Images, Videos and Audio
        81560, -- 1910.09620 You May Not Need Order in Time Series Forecasting
        83144, -- 2605.08557 MC-RFM: Geometry-Aware Few-Shot Adaptation via Mixed-Curvature Riemannian Flow M
        83155, -- 2605.04651 FAAST: Forward-Only Associative Learning via Closed-Form Fast Weights for Test-T
        83377, -- 2605.18287 StableVLA: Towards Robust Vision-Language-Action Models without Extra Data
        83720, -- 2605.13858 A Hormone-inspired Emotion Layer for Transformer language models (HELT)
        83875, -- 2605.28819 PEFT-Arena: Understanding Parameter-Efficient Finetuning from a Stability-Plasti
        84037, -- 2506.09082 AVA-Bench: Atomic Visual Ability Benchmark for Vision Foundation Models
        84249, -- 2511.20302 CrossEarth-Gate: Fisher-Guided Adaptive Tuning Engine for Efficient Adaptation o
        84324, -- 2512.02902 VLA Models Are More Generalizable Than You Think: Revisiting Physical and Spatia
        84534, -- 2602.19019 TokenTrace: Multi-Concept Attribution through Watermarked Token Recovery
        85032, -- 2603.21660 OmniFM: Toward Modality-Robust and Task-Agnostic Federated Learning for Heteroge
        85282, -- 2604.04933 PointTPA: Dynamic Network Parameter Adaptation for 3D Scene Understanding
        85329, -- 2604.09088 Memory-Efficient Transfer Learning with Fading Side Networks via Masked Dual Pat
        85473, -- 2604.27596 SECOS: Semantic Capture for Rigorous Classification in Open-World Semi-Supervise
        85483, -- 2605.01309 CUE: Concept-Aware Multi-Label Expansion to Mitigate Concept Confusion in Long-T
        85532, -- 2605.08589 S2FT: Parameter-Efficient Fine-Tuning in Sparse Spectrum Domain
        85560, -- 2605.14938 Octopus: History-Free Gradient Orthogonalization for Continual Learning in Multi
        85713, -- 2505.18877 RefLoRA: Refactored Low-Rank Adaptation for Efficient Fine-Tuning of Large Model
        85818, -- 2505.15424 Gated Integration of Low-Rank Adaptation for Continual Learning of Language Mode
        85851, -- 2508.12815 Learning to Steer: Input-dependent Steering for Multimodal LLMs
        86158, -- 2505.22860 Permissioned LLMs: Enforcing Access Control in Large Language Models
        86202, -- 2506.02453 PAID: Pairwise Angular-Invariant Decomposition for Continual Test-Time Adaptatio
        86468, -- 2502.07783 Curvature Tuning: Provable Training-free Model Steering From a Single Parameter
        86519, -- 2505.13515 LoRASuite: Efficient LoRA Adaptation Across Large Language Model Upgrades
        86530, -- 2505.22444 On Geometry-Enhanced Parameter-Efficient Fine-Tuning for 3D Scene Segmentation
        86551, -- 2506.17475 A geometric framework for momentum-based optimizers for low-rank training
        86556, -- 2505.17282 Attention with Trained Embeddings Provably Selects Important Tokens
        86653, -- 2502.01755 Robust Federated Finetuning of LLMs via Alternating Optimization of LoRA
        86711, -- 2412.01930 PROFIT: A Specialized Optimizer for Deep Fine Tuning
        87092, -- 2509.15693 SceneForge: Enhancing 3D-text alignment with Structured Scene Compositions
        87172, -- 2503.09271 DitHub: A Modular Framework for Incremental Open-Vocabulary Object Detection
        87282, -- 2506.05568 Ravan: Multi-Head Low-Rank Adaptation for Federated Fine-Tuning
        87332, -- 2505.18738 AuroRA: Breaking Low-Rank Bottleneck of LoRA with Nonlinear Mapping
        87597, -- 2503.14836 On the Robustness Tradeoff in Fine-Tuning
        87624, -- 2506.22908 Attention to the Burstiness in Visual Prompt Tuning!
        87748, -- 2509.23594 StolenLoRA: Exploring LoRA Extraction Attacks via Synthetic Data
        87750, -- 2509.13922 Towards Robust Defense against Customization via Protective Perturbation Resista
        87767, -- 2507.00327 Beyond Low-Rank Tuning: Model Prior-Guided Rank Allocation for Effective Transfe
        87930, -- 2503.07979 Achieving More with Less: Additive Prompt Tuning for Rehearsal-Free Class-Increm
        87958, -- 2504.12436 Sparsity Outperforms Low-Rank Projections in Few-Shot Adaptation
        88174, -- 2504.00851 Generalized Tensor-based Parameter-Efficient Fine-Tuning via Lie Group Transform
        88472, -- 2503.09493 Parameter-Efficient Adaptation of Geospatial Foundation Models through Embedding
        88561, -- 2502.07560 Navigating Semantic Drift in Task-Agnostic Class-Incremental Learning
        88755, -- 2502.01179 Joint Localization and Activation Editing for Low-Resource Fine-Tuning
        88888, -- 2502.06042 Scaling Laws for Forgetting during Finetuning with Pretraining Data Injection
        88967, -- 2502.11149 Large Language-Geometry Model: When LLM meets Equivariance
        89071, -- 2502.02527 TabPFN Unleashed: A Scalable and Effective Solution to Tabular Classification Pr
        89252, -- 2410.04196 Improving Generalization with Flat Hilbert Bayesian Inference
        89871, -- 2506.06686 Learning Distribution-wise Control in Representation Space for Language Models
        89873, -- 2506.07247 Promoting Ensemble Diversity with Interactive Bayesian Distributional Robustness
        89890, -- 2505.23194 Beyond Zero Initialization: Investigating the Impact of Non-Zero Initialization
        89892, -- 2410.21759 IntLoRA: Integral Low-rank Adaptation of Quantized Diffusion Models
        89967, -- 2505.04119 GAPrompt: Geometry-Aware Point Cloud Prompt for 3D Vision Model
        90118, -- 2503.18459 Hiding Images in Diffusion Models by Editing Learned Score Functions
        90142, -- 2503.15973 STOP: Integrated Spatial-Temporal Dynamic Prompting for Video Understanding
        90343, -- 2503.16997 Steady Progress Beats Stagnation: Mutual Aid of Foundation and Conventional Mode
        90449, -- 2408.17064 Instant Adversarial Purification with Adversarial Consistency Distillation
        90506, -- 2409.16434 Lessons and Insights from a Unifying Study of Parameter-Efficient Fine-Tuning (P
        90665, -- 2501.04293 TADFormer: Task-Adaptive Dynamic TransFormer for Efficient Multi-Task Learning
        90783, -- 2411.15224 Parameter Efficient Mamba Tuning via Projector-targeted Diagonal-centric Linear
        91046, -- 2410.20625 LoRA Done RITE: Robust Invariant Transformation Equilibration for LoRA Optimizat
        91099, -- 2503.12576 RaSA: Rank-Sharing Low-Rank Adaptation
        91241, -- 2405.16156 Mixture of In-Context Prompters for Tabular PFNs
        91381, -- 2410.09343 ELICIT: LLM Augmentation Via External In-context Capability
        91386, -- 2411.06736 MrSteve: Instruction-Following Agents in Minecraft with What-Where-When Memory
        91416, -- 2502.19252 GraphBridge: Towards Arbitrary Transfer Learning in GNNs
        91534, -- 2410.04638 Provable weak-to-strong generalization via benign overfitting
        91563, -- 2402.05913 Efficient stagewise pretraining via progressive subnetworks
        91576, -- 2410.17961 Closed-Form Merging of Parameter-Efficient Modules for Federated Continual Learn
        91693, -- 2503.13208 Improving Complex Reasoning with Dynamic Prompt Corruption: A Soft Prompt Optimi
        91709, -- 2411.03855 MambaPEFT: Exploring Parameter-Efficient Fine-Tuning for Mamba
        91740, -- 2412.00383 Unified Parameter-Efficient Unlearning for LLMs
        91773, -- 2501.03291 ADePT: Adaptive Decomposed Prompt Tuning for Parameter-Efficient Fine-tuning
        91888, -- 2503.00306 Unlocking Efficient, Scalable, and Continual Knowledge Editing with Basis-Level
        91915, -- 2410.09846 A Quantum Circuit-Based Compression Perspective for Parameter-Efficient Learning
        91917, -- 2410.18965 On the Crucial Role of Initialization for Matrix Factorization
        91930, -- 2410.16103 LDAdam: Adaptive Optimization from Low-Dimensional Gradient Statistics
        91951, -- 2403.00269 Large Convolutional Model Tuning via Filter Subspace
        92072, -- 2503.00986 Modeling Fine-Grained Hand-Object Dynamics for Egocentric Video Representation L
        92087, -- 2501.15878 Slot-Guided Adaptation of Pre-trained Diffusion Models for Object-Centric Learni
        92111, -- 2404.18624 Do Vision & Language Decoders use Images and Text equally? How Self-consistent a
        92163, -- 2311.15776 Stable Segment Anything Model
        92244, -- 2410.00645 TSVD: Bridging Theory and Practice in Continual Learning with Pre-trained Models
        92254, -- 2502.14816 Dynamic Low-Rank Sparse Adaptation for Large Language Models
        92256, -- 2409.01035 Unleashing the Power of Task-Specific Directions in Parameter Efficient Fine-tun
        92260, -- 2410.21815 Gnothi Seauton: Empowering Faithful Self-Interpretability in Black-Box Transform
        92582, -- 2503.22886 Task Tokens: A Flexible Approach to Adapting Behavior Foundation Models
        92613, -- 2510.04682 TiTok: Transfer Token-level Knowledge via Contrastive Excess to Transplant LoRA
        92790, -- 2505.24262 On Fairness of Task Arithmetic: The Role of Task Vectors
        92952, -- 2511.06225 MoRA: Missing Modality Low-Rank Adaptation for Visual Recognition
        93269, -- 2505.20211 PiCa: Parameter-Efficient Fine-Tuning with Column Space Projection
        93325, -- 2505.22370 SplitLoRA: Balancing Stability and Plasticity in Continual Learning Through Grad
        93335, -- 2510.11750 PRISM: Enhancing PRotein Inverse Folding through Fine- Grained Retrieval on Stru
        93367, -- 2603.09888 LCA: Local Classifier Alignment for Continual Learning
        93696, -- 2510.09477 Efficient Autoregressive Inference for Transformer Probabilistic Models
        93980, -- 2508.06953 BoRA: Towards More Expressive Low-Rank Adaptation with Block Diversity
        93987, -- 2506.04216 Unified In-Context Video Editing
        94112, -- 2603.19308 GT-Space: Enhancing Heterogeneous Collaborative Perception with Ground Truth Fea
        94133, -- 2509.24245 Prompt and Parameter Co-Optimization for Large Language Models
        94290, -- 2506.07891 Video Unlearning via Low-Rank Refusal Vector
        94341, -- 2506.22039 UniCA: Unified Covariate Adaptation for Time Series Foundation Model
        94534, -- 2509.25684 LD-MoLE: Learnable Dynamic Routing for Mixture of LoRA Experts
        94544, -- 2511.08666 Privacy Beyond Pixels: Latent Anonymization for Privacy-Preserving Video Underst
        94573, -- 2601.20232 Visual Prompt-Agnostic Evolution
        94605, -- 2602.19926 Rethinking LoRA for Privacy-Preserving Federated Learning in Large Models
        94680, -- 2509.03810 Online time series prediction using feature adjustment
        94718, -- 2510.04309 Activation Steering with a Feedback Controller
        94807, -- 2501.18936 Revisit Visual Prompt Tuning: The Expressiveness of Prompt Experts
        94861, -- 2506.18184 Memba: Membrane-driven Parameter-Efficient Fine-Tuning for Mamba
        94865, -- 2509.18993 CR-Net: Scaling Parameter-Efficient Training with Cross-Layer Low-Rank Structure
        94923, -- 2603.13792 IGU-LoRA: Adaptive Rank Allocation via Integrated Gradients and Uncertainty-Awar
        94962, -- 2601.22905 FlexLoRA: Entropy-Guided Flexible Low-Rank Adaptation
        95037, -- 2602.17559 Revisiting Weight Regularization for Low-Rank Continual Learning
        95099, -- 2605.30794 MechVQA: Benchmarking and Enhancing Multimodal LLMs on Comprehensive Mechanical
        95212, -- 2508.01167 T2S: Tokenized Skill Scaling for Lifelong Imitation Learning
        96211, -- 2605.16892 DriveSafe: A Framework for Risk Detection and Safety Suggestions in Driving Scen
        97118, -- 2604.15703 P3T: Prototypical Point-Level Prompt Tuning with Enhanced Generalization for 3D
        98146, -- 2606.09131 Late-Layer Fusion is Enough: Dual-Path Vision Token Routing for Multimodal Large
        99296, -- 2603.13282 FedTreeLoRA: Reconciling Statistical and Functional Heterogeneity in Federated L
        99340, -- 2605.28495 JANUS-LORA: A Balanced Low-Rank Adaptation for Continual Learning
        99356, -- 2605.08842 XPERT: Expert Knowledge Transfer for Effective Training of Language Models
        99382, -- 2605.11817 See What Matters: Differentiable Grid Sample Pruning for Generalizable Vision-La
        99439, -- 2606.08687 Shift-Dependent Asymmetry: Orthogonal Inverse Low-Rank Adaptation for Federated
        99465, -- 2605.01973 Learn-to-learn on Arbitrary Textual Conditioning: A Hypernetwork-Driven Meta-gat
        99638, -- 2601.21003 Bayesian-LoRA: Probabilistic Low-Rank Adaptation of Large Language Models
        99736, -- 2606.10617 SSR-Merge: Subspace Signal Routing for Training-Free LoRA Merging in Diffusion M
        99970, -- 2605.29380 TRACER: Persistent Regularization for Robust Multimodal Finetuning
        100173, -- 2505.12741 Language Model Networks: Supervision-Efficient Learning through Dense Communicat
        100231, -- 2510.24561 LoRA-DA: Data-Aware Initialization for Low-Rank Adaptation via Asymptotic Analys
        100381, -- 2605.31484 Balanced LoRA: Removing Parameter Invariance to Accelerate Convergence
        100428, -- 2605.21558 From Parameters to Data: A Task-Parameter-Guided Fine-Tuning Pipeline for Effici
        100468, -- 2603.00425 Weight Updates as Activation Shifts: A Principled Framework for Steering
        100636, -- 2605.19409 Unlocking the Potential of Continual Model Merging: An ODE Perspective
        100651, -- 2605.18271 From Volume to Value: Preference-Aligned Memory Construction for On-Device RAG
        100692, -- 2510.00936 Resolution as a Direction: Vector-Panning Feature Alignment for Cross-Resolution
        100906, -- 2602.12952 Transporting Task Vectors across Different Architectures without Training
        101068, -- 2604.03314 CoLA: Cross-Modal Low-rank Adaptation for Multimodal Downstream Tasks
        101122, -- 2510.23818 ScaLoRA: Optimally Scaled Low-Rank Adaptation for Efficient High-Rank Fine-Tunin
        101186, -- 2602.03073 TMS: Trajectory-Mixed Supervision for On-Policy Self Distillation
        101604, -- 2605.29561 ParaTool: Shifting Tool Representations from Context to Parameters
        101728, -- 2509.22310 Adaptive Policy Backbone via Shared Network
        101840, -- 2601.22068 Quantifying the Uncertainty of Foundation Models with Singular Value Ensembles
        101891, -- 2506.11083 RedDebate: Safer Responses Through Multi-Agent Red Teaming Debates
        101934, -- 2606.00944 PRISM: Gauge-Invariant Tangent-Space Differentially Private LoRA
        102234, -- 2510.02453 How to Train Your Advisor: Steering Black-Box LLMs with Advisor Models
        102307, -- 2605.30179 iLoRA: Bayesian Low-Rank Adaptation with Latent Interaction Graphs for Microbiom
        102437, -- 2602.11171 A Language-Guided Bayesian Optimization for Efficient LoRA Hyperparameter Search
        102619, -- 2406.17261 TRAWL: Tensor Reduced and Approximated Weights for Large Language Models
        102652, -- 2605.19623 PrAda: Few-Shot Visual Adaptation for Text-Prompted Segmentation
        102676, -- 2606.28070 JD Oxygen AI Item Center (Oxygen AIIC) V1: An Industrial-Scale LLM/VLM-Centric S
        102742, -- 2308.02565 SimTeG: A Frustratingly Simple Approach Improves Textual Graph Learning
        102791, -- 2603.14228 Not All Directions Matter: Towards Structured and Task-Aware Low-Rank Model Adap
        102837, -- 2512.23260 Interpretable Safety Alignment via SAE-Constructed Low-Rank Subspace Adaptation
        103092, -- 2502.04506 When One LLM Drools, Multi-LLM Collaboration Rules
        103127, -- 2604.06291 TalkLoRA: Communication-Aware Mixture of Low-Rank Adaptation for Large Language
        103278, -- 2601.06471 PRISP: Privacy-Safe Few-Shot Personalization via Lightweight Adaptation
        103362, -- 2604.18124 TLoRA: Task-aware Low Rank Adaptation of Large Language Models
        103371, -- 2604.14090 From Weights to Activations: Is Steering the Next Frontier of Adaptation?
        103446, -- 2604.14010 Parameter Importance is Not Static: Evolving Parameter Isolation for Supervised
        103539, -- 2604.17753 Evolutionary Negative Module Pruning for Better LoRA Merging
        103585, -- 2602.02556 Beyond Experience Retrieval: Learning to Generate Utility-Optimized Structured E
        104104, -- 2605.12019 Efficient and Adaptive Human Activity Recognition via LLM Backbones
        105061, -- 2509.06740 Co-Seg: Mutual Prompt-Guided Collaborative Learning for Tissue and Nuclei Segmen
        105134, -- 2503.00748 Dynamic Gradient Sparsification Training for Few-Shot Fine-tuning of CT Lymph No
        105512, -- 2507.18112 Parameter-Efficient Fine-Tuning of 3D DDPM for MRI Image Generation Using Tensor
        105571, -- 2507.05852 Prototype-Guided and Lightweight Adapters for Inherent Interpretation and Genera
        105753, -- 2506.04950 Time-Lapse Video-Based Embryo Grading via Complementary Spatial-Temporal Pattern
        105867, -- 2607.25108 OPERA: Offline Policy-guided Expert Routing and Adaptation for Universal Biomedi
        106174, -- 2602.17510 LORA-CRAFT: Cross-layer Rank Adaptation via Frozen Tucker Decomposition of Pre-t
        106190, -- 2505.24302 ScienceMeter: Tracking Scientific Knowledge Updates in Language Models
        106199, -- 2604.06263 Incentive-Aware Multi-Fidelity Optimization for Generative Advertising in Large
        106244, -- 2507.05387 The Generalization Ridge: Information Flow in Natural Language Generation
        106411, -- 2511.10707 Bias-Restrained Prefix Representation Finetuning for Mathematical Reasoning
        106463, -- 2601.03305 Mass Concept Erasure in Diffusion Models with Concept Hierarchy
        106491, -- 2511.12113 MetaGDPO: Alleviating Catastrophic Forgetting with Metacognitive Knowledge Throu
        106580, -- 2511.00051 Calibrating and Rotating: A Unified Framework for Weight Conditioning in PEFT
        106597, -- 2511.05894 Open-World 3D Scene Graph Generation for Retrieval-Augmented Reasoning
        106740, -- 2511.10210 Advanced Black-Box Tuning of Large Language Models with Limited API Calls
        106751, -- 2511.21733 RoSA: Enhancing Parameter-Efficient Fine-Tuning via RoPE-aware Selective Adaptat
        106932, -- 2504.09109 Probability Distribution Alignment and Low-Rank Weight Decomposition for Source-
        107028, -- 2603.11873 AdaFuse: Accelerating Dynamic Adapter Inference via Token-Level Pre-Gating and F
        107246, -- 2511.12917 Explore How to Inject Beneficial Noise in MLLMs
        107285, -- 2510.13003 OPLoRA: Orthogonal Projection LoRA Prevents Catastrophic Forgetting During Param
        107307, -- 2511.08238 Remodeling Semantic Relationships in Vision-Language Fine-Tuning
        107363, -- 2508.01254 Self-Enhanced Image Clustering with Cross-Modal Semantic Consistency
        107400, -- 2507.00502 Shared & Domain Self-Adaptive Experts with Frequency-Aware Discrimination for Co
        107411, -- 2512.04748 Model Whisper: Steering Vectors Unlock Large Language Models’ Potential in Test-
        107470, -- 2511.17582 GateRA: Token-aware Modulation for Parameter-Efficient Fine-tuning
        107549, -- 2511.17987 Escaping Optimization Stagnation: Taking Steps Beyond Task Arithmetic via Differ
        107571, -- 2508.16191 GEM: A Scale-Aware and Distribution-Sensitive Sparse Fine-Tuning Framework for E
        107629, -- 2605.04058 MP-ISMoE: Mixed-Precision Interactive Side Mixture-of-Experts for Efficient Tran
        107634, -- 2509.04502 VaccineRAG: Boosting Multimodal Large Language Models’ Immunity to Harmful RAG S
        107693, -- 2505.19355 Estimating Online Influence Needs Causal Modeling! Counterfactual Analysis of Mi
        107767, -- 2603.12587 MRGeo: Robust Cross-View Geo-Localization of Corrupted Images via Spatial and Ch
        107841, -- 2511.08334 Empowering DINO Representations for Underwater Instance Segmentation via Aligner
        107959, -- 2506.05577 Policy Search, Retrieval, and Composition via Task Similarity in Collaborative A
        108152, -- 2503.02659 Put the Space of LoRA Initialization to the Extreme to Preserve Pre-trained Know
        108201, -- 2504.12311 Learning Optimal Prompt Ensemble for Multi-source Visual Prompt Transfer
        108205, -- 2506.12409 Branch, or Layer? Zeroth-Order Optimization for Continual Learning of Vision-Lan
        108206, -- 2601.08499 EfficientFSL: Enhancing Few-Shot Classification via Query-Only Tuning In Vision
        108378, -- 2505.15683 FedSEA-LLaMA: A Secure, Efficient and Adaptive Federated Splitting Framework for
        108489, -- 2511.20073 Learning Procedural-Aware Video Representations Through State-Grounded Hierarchy
        108551, -- 2601.11113 Differentially Private Subspace Fine-Tuning for Large Language Models
        108640, -- 2607.25614 MemSFT: Mitigating Alignment Tax with an External Parametric Memory
        108815, -- 2605.02638 ViewSAM: Learning View-aware Cross-modal Semantics for Weakly Supervised Cross-v
        109216, -- 2205.12755 An Evolutionary Approach to Dynamic Introduction of Tasks in Large-scale Multita
        109311, -- 2506.01373 No Train Yet Gain: Towards Generic Multi-Object Tracking in Sports and Beyond
        109434, -- 2509.14527 CLAIP-Emo: Parameter-Efficient Adaptation of Language-supervised models for In-t
        109436, -- 2207.11081 Emotion Separation and Recognition from a Facial Expression by Generating the Po
        109957, -- 2507.09924 MixLoRA-DSI: Dynamically Expandable Mixture-of-LoRA Experts for Rehearsal-Free G
        110030, -- 2504.05343 AROMA: Autonomous Rank-one Matrix Adaptation
        110228, -- 2509.05657 LM-Searcher: Cross-domain Neural Architecture Search with LLMs via Unified Numer
        110241, -- 2508.21741 Not All Parameters Are Created Equal: Smart Isolation Boosts Fine-Tuning Perform
        110334, -- 2506.02973 Expanding before Inferring: Enhancing Factuality in Large Language Models throug
        110380, -- 2509.10513 Mixture-of-Clustered-Experts: Advancing Expert Specialization and Generalization
        110458, -- 2509.00996 MEPT: Mixture of Expert Prompt Tuning as a Manifold Mapper
        110526, -- 2509.16882 Dynamic Expert Specialization: Towards Catastrophic Forgetting-Free Multi-Domain
        110555, -- 2502.15178 Enhancing Speech Large Language Models with Prompt-Aware Mixture of Audio Encode
        110567, -- 2509.12112 CBP-Tuning: Efficient Local Customization for Black-box Large Language Models
        110570, -- 2509.11878 \textit{Do It Yourself (DIY)}: Modifying Images for Poems in a Zero-Shot Setting
        110589, -- 2409.15520 MobiZO: Enabling Efficient LLM Fine-Tuning at the Edge via Inference Engines
        110676, -- 2509.17688 TASO: Task-Aligned Sparse Optimization for Parameter-Efficient Model Adaptation
        110794, -- 2508.17637 Weights-Rotated Preference Optimization for Large Language Models
        110979, -- 2503.01345 Same Question, Different Words: A Latent Adversarial Framework for Prompt Robust
        111085, -- 2503.18008 Personalized Language Models via Privacy-Preserving Evolutionary Model Merging
        111338, -- 2505.20006 Mixture of LoRA Experts for Low-Resourced Multi-Accent Automatic Speech Recognit
        111628, -- 2409.09340 Egocentric Speaker Classification in Child-Adult Dyadic Interactions: From Sensi
        111992, -- 2505.24224 MOPSA: Mixture of Prompt-Experts Based Speaker Adaptation for Elderly Speech Rec
        112584, -- 2404.05052 Facial Affective Behavior Analysis with Instruction Tuning
        112593, -- 2407.10704 Quantized Prompt for Efficient Generalization of Vision-Language Models
        112641, -- 2407.15087 Navigation Instruction Generation with BEV Perception and Large Language Models
        112738, -- 2407.13437 FREST: Feature RESToration for Semantic Segmentation under Multiple Adverse Cond
        112829, -- 2407.02846 Multi-Task Domain Adaptation for Language Grounding with 3D Objects
        112864, -- 2407.05342 Mind the Interference: Retaining Pre-trained Knowledge in Parameter Efficient Co
        112865, -- 2407.08109 Urban Waterlogging Detection: A Challenging Benchmark and Large-Small Model Co-A
        112993, -- 2407.06964 Parameter-Efficient and Memory-Efficient Tuning for Vision Transformer: A Disent
        113002, -- 2409.08260 Improving Text-guided Object Inpainting with Semantic Pre-inpainting
        113055, -- 2407.11414 SDPT: Synchronous Dual Prompt Tuning for Fusion-based Visual-Language Pre-traine
        113079, -- 2403.04697 AUFormer: Vision Transformers are Parameter-Efficient Facial Action Unit Detecto
        113325, -- 2401.02094 PILoRA: Prototype Guided Incremental LoRA for Federated Class-Incremental Learni
        113451, -- 2407.14330 Straightforward Layer-wise Pruning for More Efficient Visual Adaptation
        113473, -- 2407.11820 Stepping Stones: A Progressive Training Strategy for Audio-Visual Semantic Segme
        113491, -- 2407.10947 Can Textual Semantics Mitigate Sounding Object Segmentation Preference?
        113650, -- 2403.14797 Preventing Catastrophic Forgetting through Memory Networks in Continuous Detecti
        113807, -- 2608.31036 Normalized Low-Rank Adaptation
        113892, -- 2608.30949 MULTI3IR: A Benchmark for Multi-perspective Multi-domain Multi-modal Information
        113941, -- 2609.04201 Scal3R: Learning Efficient Multi-Relative Pose Query for Scalable Online 3D Reco
        114943, -- 2403.07576 Fine-grained Prompt Tuning: A Parameter and Memory Efficient Transfer Learning M
        115019, -- 2405.08786 Incorporating Clinical Guidelines through Adapting Multi-modal Large Language Mo
        115084, -- 2410.04689 Low-Rank Continual Pyramid Vision Transformer: Incrementally Segment Whole-Body
        115188, -- 2407.07517 Parameter Efficient Fine Tuning for Multi-scanner PET to PET Reconstruction
        115306, -- 2405.17877 Sparsity- and Hybridity-Inspired Visual Parameter-Efficient Fine-Tuning for Medi
        115375, -- 2406.15764 TP-DRSeg: Improving Diabetic Retinopathy Lesion Segmentation with Explicit Text-
        115551, -- 2311.17112 Parameter Efficient Fine-tuning via Cross Block Orchestration for Segment Anythi
        115590, -- 2308.12001 Boosting Image Quality Assessment through Efficient Transformer Adaptation with
        115650, -- 2406.00480 AlignSAM: Aligning Segment Anything Model to Open Context via Reinforcement Lear
        115710, -- 2405.11867 Depth Prompting for Sensor-Agnostic Depth Estimation
        115737, -- 2405.11487 Previously on ... From Recaps to Story Summarization
        115790, -- 2404.00653 Dual DETRs for Multi-Label Temporal Action Detection
        115860, -- 2403.10519 Frozen Feature Augmentation for Few-Shot Image Classification
        115980, -- 2403.14430 Ranking Distillation for Open-Ended Video Question Answering with Insufficient L
        115991, -- 2403.19067 Low-Rank Rescaled Vision Transformer Fine-Tuning: A Residual Design Approach
        116066, -- 2404.00228 InfLoRA: Interference-Free Low-Rank Adaptation for Continual Learning
        116211, -- 2402.02887 Time- Memory- and Parameter-Efficient Visual Adaptation
        116314, -- 2403.04245 A Study of Dropout-Induced Modality Bias on Robustness to Missing Video Frames f
        116410, -- 2403.01849 One Prompt Word is Enough to Boost Adversarial Robustness for Pre-trained Vision
        116511, -- 2403.09634 OneTracker: Unifying Visual Object Tracking with Foundation Models and Efficient
        116598, -- 2311.17352 Efficient Stitchable Task Adaptation
        116788, -- 2311.13612 Descriptor and Word Soups: Overcoming the Parameter Efficiency Accuracy Tradeoff
        116948, -- 2311.16926 LLaFS: When Large Language Models Meet Few-Shot Segmentation
        116989, -- 2404.11207 Exploring the Transferability of Visual Prompting for Multimodal Large Language
        116993, -- 2312.05716 Initialization Matters for Adversarial Transfer Learning
        117016, -- 2305.11577 LeftRefill: Filling Right Canvas based on Left Reference through Generalized Tex
        117956, -- 2512.15423 The 3D Mirage: Probing and Taming 3D Hallucinations
        118114, -- 2607.04484 TrustCLIP: Learning Private Visual Features via Adversarial Reconstruction
        118126, -- 2606.24740 BioMedVR: Confusion-Aware Mixture-of-Prompt Experts for Biomedical Visual Reprog
        118136, -- 2607.14595 MagicPrompt: Ultra-Lightweight Prompt Tuning for Video Generation
        118146, -- 2606.24963 Curvature-Guided Mixing for MLLM Adaptation
        118168, -- 2607.19171 Point Ladder Tuning: Parameter-Efficient Hierarchical Adaptation for 3D Point Cl
        118182, -- 2510.00458 VLOD-TTA: Test-Time Adaptation of Vision-Language Object Detectors
        118194, -- 2603.19873 SIMPLER: Efficient Foundation Model Adaptation via Similarity-Guided Layer Pruni
        118211, -- 2607.29033 SAM+D: Parameter-Efficient Dimensional Lifting of SAM-Family Models via Depth-Ro
        118212, -- 2608.24469 Low-Rank Ternary Adaptation for Fine-Tuning Transformers
        118227, -- 2607.02930 CL-Anomaly: Layer-Adaptive Mixture-of-Experts with Multimodal Large Language Mod
        119143, -- 2607.06109 RoME: Robust Mixture of Low-Rank Experts against Multiple Adversarial Perturbati
        119289, -- 2603.20509 Lessons and Open Questions from a Unified Study of Camera-Trap Species Recogniti
        119373, -- 2606.28626 SIGNET: Motion-Level Knowledge Transfer for Cross-Language Sign Language Transla
        119558, -- 2607.06918 LoCA: Spatially-Aware Low-Rank Convolutional Adaptation of Vision Foundation Mod
        119893, -- 2502.06029 DiTASK: Multi-Task Fine-Tuning with Diffeomorphic Transformations
        119898, -- 2505.23694 DA-VPT: Semantic-Guided Visual Prompt Tuning for Vision Transformers
        119981, -- 2603.01759 Meta-Learning Hyperparameters for Parameter Efficient Fine-Tuning
        120524, -- external Adaptive Parameter Selection for Tuning Vision-Language Models
        120534, -- 2503.09487 Project-Probe-Aggregate: Efficient Fine-Tuning for Group Robustness
        120590, -- 2503.18337 Coeff-Tuning: A Graph Filter Subspace View for Tuning Attention-Based Large Mode
        121621, -- 2605.11760 M4-SAM: Multi-Modal Mixture-of-Experts with Memory-Augmented SAM for RGB-D Video
        122406, -- 2609.16145 Safe Error Correction for Language Models: Frozen-Base Adjustment with Capabilit
        122441, -- 2601.06362 Do Implicit Personalization and Explicit Styles Conflict? PsPLUG: A Lightweight
        122446, -- 2601.06352 CARD: Cluster-level Adaptation with Reward-guided Decoding for Personalized Text
        123338, -- 2408.01343 StitchFusion: Weaving Any Visual Modalities to Enhance Multimodal Semantic Segme
        123646, -- 2212.03145 FacT: Factor-Tuning for Lightweight Adaptation on Vision Transformer
        123649, -- 2312.07856 DTL: Disentangled Transfer Learning for Visual Recognition
        123650, -- 2310.19859 Res-Tuning: A Flexible and Efficient Tuning Paradigm via Unbinding Tuner from Ba
        123652, -- 2402.04009 Low-rank Attention Side-Tuning for Parameter-Efficient Fine-Tuning
        123654, -- 2405.18897 MLAE: Masked LoRA Experts for Visual Parameter-Efficient Fine-Tuning
        123780, -- 2610.26802 Scaling Parameter-Efficient Fine-Tuning for Brain Encoding
        124278, -- external Bayesian Backprop as Belief Propagation: Single-Pass Predictive Uncertainty
        124605, -- 2606.04775 Activation Steering of Video Generation Models via Reduced-Order Linear Optimal
        125469, -- 2605.05413 From History to State: Constant-Context Skill Learning for LLM Agents
        125619, -- 2606.31397 Mixture-of-Control: State-Aware Fine-Tuning for Transformer-based Models
        125818, -- 2606.16602 PhysGuard: Fisher-Guided Gradient Projection for Sim-to-Real Neural PDE Surrogat
        125866, -- 2605.21177 ChunkFT: Byte-Streamed Optimization for Memory-Efficient Full Fine-Tuning
        125945, -- 2610.06243 RoSA: Rotational Sparse Adaptation for Memory-Efficient Fine-Tuning
        126627, -- 2601.05903 HAPS: Hierarchical LLM Routing with Joint Architecture and Parameter Search
        126722, -- 2605.05054 Direct Product Flow Matching: Decoupling Radial and Angular Dynamics for Few-Sho
        126765, -- 2610.14558 PGSB: Pretrained-Guided Shared Basis for LoRA Model Merging
        126861, -- 2606.05516 Dominant-Layer ZO: A Single Layer Dominates Zeroth-Order Fine-Tuning of LLMs
        126986, -- 2609.25655 From Experts to Sub-experts: Fine-grained Parameter-Efficient Fine-Tuning for Mo
        127019, -- 2609.31559 Online Learning via Learned Latent Bayesian Tracking
        127570, -- 2609.33716 Revisiting Diffusion Fine-Tuning for Unsupervised Domain Adaptation
        127819, -- external FedIBS: Federated Vision-Language Adaptation via Intrinsic Bias Selection
        127907, -- 2605.14364 MoRe: Modular Representations for Principled Continual Representation Learning o
        128212, -- 2605.26104 EVIDENT: Routing MLLM Adaptation through Entity-Grounded Visual Evidence for Cro
        128853, -- 2605.10288 BROS: Bias-Corrected Randomized Subspaces for Memory-Efficient Single-Loop Bilev
        129180, -- 2605.18822 Hybrid-LoRA: Bridging Full Fine-Tuning and Low-Rank Adaptation for Post-Training
        129373, -- 2602.02060 FiLoRA: Focus-and-Ignore LoRA for Controllable Feature Reliance
        130100, -- 2609.14339 Communication-Efficient LLM Adaptation over Decentralized GPU Meshes
        130423, -- 2605.11936 From Noise to Diversity: Random Embedding Injection in LLM Reasoning
        131096, -- external Localizing and Repairing Sparse-Prompt Failure in SAM Decoders via Box-to-Point
        131555, -- 2512.05359 Group Orthogonal Low-Rank Adaptation for RGB-T Tracking
        131900, -- 2611.06042 UniRestorer++: Scalable Universal Image Restoration with Multi-Granularity Degra
        131951  -- 2611.06976 On the Opportunities and Challenges of Prefill-to-Autoregressive Cross-Model Tra
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites Houlsby adapters without naming adapter tuning, or "adapter" means a LoRA adapter, IP-Adapter or modality connector'
FROM adapter_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING adapter_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING adapter_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- adagrad: 26 reviewed true positives of 39 title/abstract candidates (AdaGrad, its full-matrix/Norm variants and AdaGrad-family preconditioners such as Shampoo).
CREATE TEMP TABLE adagrad_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'adagrad'
  AND p.id IN (
        1129, -- 1802.09568 Shampoo: Preconditioned Stochastic Tensor Optimization
        1523, -- 1810.00760 Riemannian Adaptive Optimization Methods
        3126, -- 2002.09018 Scalable Second Order Optimization for Deep Learning
        3162, -- 2003.00295 Adaptive Federated Optimization
        4948, -- 2101.11075 Adaptivity without Compromise: A Momentumized, Adaptive, Dual Averaged Gradient
        13167, -- 2302.08783 SGD with AdaGrad Stepsizes: Full Adaptivity with High Probability to Unknown Par
        17237, -- 2306.06098 Error Feedback Can Accurately Compress Preconditioners
        20336, -- 2309.06497 A Distributed Data-Parallel PyTorch Implementation of the Distributed Shampoo Op
        21324, -- 2310.02093 Stochastic Gradient Descent with Preconditioned Polyak Step-size
        27478, -- 2402.11215 AdAdaGrad: Adaptive Batch Size Schemes for Adaptive Gradient Methods
        27552, -- 2402.11858 Stochastic Hessian Fittings with Lie Groups
        32471, -- 2406.04443 Clipping Improves Adam-Norm and AdaGrad-Norm when the Noise Is Heavy-Tailed
        33680, -- 2406.17748 A New Perspective on Shampoo's Preconditioner
        39874, -- 2411.07120 Lean and Mean Adaptive Optimization via Subset-Norm and Subspace-Momentum with C
        58066, -- 2604.17423 A unified convergence theory for adaptive first-order methods in the nonconvex c
        68796, -- 2509.02981 AdaGrad Meets Muon: Adaptive Stepsizes for Orthogonal Updates
        77354, -- 2405.09637 CLASSP: a Biologically-Inspired Approach to Continual Learning through Adjustmen
        78901, -- 2306.06101 Prodigy: An Expeditiously Adaptive Parameter-Free Learner
        88732, -- 2503.10537 Structured Preconditioners in Adaptive Optimization: A Unified Analysis
        91483, -- 2406.15244 AdaGrad under Anisotropic Smoothness
        93816, -- 2506.23803 SGD with Adaptive Preconditioning: Unified Analysis and Momentum Acceleration
        101242, -- 2602.06880 Decoupling Variance and Scale-Invariant Updates in Adaptive Gradient Descent for
        102337, -- 2605.18694 Can Adaptive Gradient Methods Converge under Heavy-Tailed Noise? A Case Study of
        124753, -- external Near-Optimal Best-of-Both-Worlds Algorithms for Decoupled Exploration and Exploi
        126553, -- external AcceleGrad#: Adaptive Geometry-Aware Acceleration
        127575  -- external Sharper Regret Bounds for Shampoo
  );

DELETE FROM paper_method_exclusions x
USING adagrad_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM adagrad_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM adagrad_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE adagrad_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'adagrad'
  AND p.id IN (
        1026, -- 1712.07628 Improving Generalization Performance by Switching from Adam to SGD
        1851, -- 1902.09843 Adaptive Gradient Methods with Dynamic Bound of Learning Rate
        2358, -- 1907.08610 Lookahead Optimizer: k steps forward, 1 step back
        2583, -- 1909.11015 diffGrad: An Optimization Method for Convolutional Neural Networks
        2733, -- 1910.12249 An Adaptive and Momental Bound Method for Stochastic Learning
        3644, -- 2006.00719 ADAHESSIAN: An Adaptive Second Order Optimizer for Machine Learning
        5132, -- 2103.01931 Categorical Foundations of Gradient-Based Learning
        25306, -- 2312.17369 SANIA: Polyak-type Optimization Framework Leads to Scale Invariant Stochastic Al
        26354, -- 2401.15207 HiFT: A Hierarchical Full Parameter Fine-Tuning Strategy
        31598, -- 2405.14578 Surge Phenomenon in Optimal Learning Rate and Batch Size Scaling
        80222, -- 2202.02248 Backpropagation Neural Tree
        101193, -- 2605.30648 Convergence of Steepest Descent and Adam under Non-Uniform Smoothness
        128904  -- 2605.08980 Muon Does Not Converge on Convex Lipschitz Functions
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: AdaGrad named only in a list of adaptive optimizers or as a passing baseline'
FROM adagrad_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING adagrad_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING adagrad_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- rmsprop: 12 reviewed true positives of 25 title/abstract candidates.
CREATE TEMP TABLE rmsprop_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rmsprop'
  AND p.id IN (
        2379, -- 1907.12935 RNN-based Online Handwritten Character Recognition Using Accelerometer and Gyros
        4928, -- 2101.09192 Gravity Optimizer: a Kinematic Approach on Optimization in Deep Learning
        9082, -- 2205.10287 On the SDEs and Scaling Rules for Adaptive Gradient Algorithms
        10293, -- 2209.07219 Training Neural Networks in Single vs Double Precision
        25866, -- 2401.08426 GD doesn't make the cut: Three ways that non-differentiability affects neural ne
        29807, -- 2404.01436 Convergence Guarantees for RMSProp and Adam in Generalized-smooth Non-convex Opt
        32199, -- 2406.00846 Local Methods with Adaptivity via Scaling
        38078, -- 2410.05871 A second-order-like optimizer with adaptive gradient scaling for deep learning
        56162, -- 2602.15322 On Surprising Effectiveness of Masking Updates in Adaptive Optimizers
        85968, -- 2504.14882 Some Optimizers are More Equal: Understanding the Role of Optimizers in Group Fa
        91427, -- 2411.15958 Adaptive Methods through the Lens of SDEs: Theoretical Insights on the Role of N
        101193  -- 2605.30648 Convergence of Steepest Descent and Adam under Non-Uniform Smoothness
  );

DELETE FROM paper_method_exclusions x
USING rmsprop_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rmsprop_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM rmsprop_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE rmsprop_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rmsprop'
  AND p.id IN (
        1026, -- 1712.07628 Improving Generalization Performance by Switching from Adam to SGD
        1220, -- 1804.04235 Adafactor: Adaptive Learning Rates with Sublinear Memory Cost
        1851, -- 1902.09843 Adaptive Gradient Methods with Dynamic Bound of Learning Rate
        2023, -- 1904.09237 On the Convergence of Adam and Beyond
        2402, -- 1908.03265 On the Variance of the Adaptive Learning Rate and Beyond
        2583, -- 1909.11015 diffGrad: An Optimization Method for Convolutional Neural Networks
        31598, -- 2405.14578 Surge Phenomenon in Optimal Learning Rate and Batch Size Scaling
        80222, -- 2202.02248 Backpropagation Neural Tree
        80736, -- 2105.02716 Noether's Learning Dynamics: Role of Symmetry Breaking in Neural Networks
        92864, -- 2506.06558 Rapid Training of Hamiltonian Graph Networks Using Random Features
        107111, -- 2505.07614 Bant: Byzantine Antidote via Trial Function and Trust Scores
        109052, -- 2608.05136 The Loss Does Not See the Basis, but Adam Does
        130073  -- external How Can SignSGD Outperform SGD? A Functional Scaling Law Perspective
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: RMSProp named only in a list of adaptive optimizers or as a passing analogy'
FROM rmsprop_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING rmsprop_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING rmsprop_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- residual-vector-quantization: 61 reviewed true positives of 82 title/abstract candidates.
CREATE TEMP TABLE rvq_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'residual-vector-quantization'
  AND p.id IN (
        6198, -- 2107.03312 SoundStream: An End-to-End Neural Audio Codec
        14776, -- 2304.09116 NaturalSpeech 2: Latent Diffusion Models are Natural and Zero-Shot Speech and Si
        16707, -- 2306.00107 MERT: Acoustic Music Understanding Model with Large-Scale Self-supervised Traini
        17265, -- 2306.06546 High-Fidelity Audio Compression with Improved RVQGAN
        19973, -- 2308.16692 SpeechTokenizer: Unified Speech Tokenizer for Speech Large Language Models
        21177, -- 2310.00704 UniAudio: An Audio Foundation Model Toward Universal Audio Generation
        24900, -- 2312.10741 StyleSinger: Style Transfer for Out-of-Domain Singing Voice Synthesis
        27588, -- 2402.12208 Language-Codec: Bridging Discrete Codec Representations and Speech Language Mode
        29890, -- 2404.02781 CLaM-TTS: Improving Neural Codec Language Model for Zero-Shot Text-to-Speech
        35632, -- 2408.03822 Compact 3D Gaussian Splatting for Static and Dynamic Radiance Fields
        36413, -- 2408.17175 Codec Does Matter: Exploring the Semantic Shortcoming of Codec for Audio Languag
        37113, -- 2409.13216 MuCodec: Ultra Low-Bitrate Music Codec
        37561, -- 2410.00037 Moshi: a speech-text foundation model for real-time dialogue
        38742, -- 2410.13798 Learning Graph Quantized Tokenizers
        38802, -- 2410.14411 SNAC: Multi-Scale Neural Audio Codec
        38850, -- 2410.15017 DM-Codec: Distilling Multimodal Representations for Speech Tokenization
        40142, -- 2411.12008 Compression of Higher Order Ambisonics with Multichannel RVQGAN
        40889, -- 2412.02202 3D representation in 512-Byte:Variational tokenizer is the key for autoregressiv
        41345, -- 2412.07797 Mogo: RQ Hierarchical Causal Transformer for High-Quality 3D Human Motion Genera
        41534, -- 2412.10208 Efficient Generative Modeling with Residual Vector Quantization-Based Tokens
        42401, -- 2501.01108 MuQ: Self-Supervised Music Representation Learning with Mel Residual Vector Quan
        49548, -- 2505.17726 Slot-MLLM: Object-Centric Visual Tokenization for Multimodal LLM
        51291, -- 2506.16310 Optimizing Multilingual Text-To-Speech with Accents & Emotions
        51862, -- 2507.09144 $I^{2}$-World: Intra-Inter Tokenization for Efficient Dynamic 4D Scene Forecasti
        52195, -- 2508.02605 ReMoMask: Retrieval-Augmented Masked Motion Generation
        55449, -- 2601.16093 SAMTok: Representing Any Mask with Two Words
        56872, -- 2603.18090 MOSS-TTS Technical Report
        57566, -- 2604.15923 Hierarchical Codec Diffusion for Video-to-Speech Generation
        58768, -- 2603.28366 AutoCut: End-to-end advertisement video editing based on multimodal discretizati
        59518, -- 2603.12108 EvoTok: A Unified Image Tokenizer via Residual Latent Evolution for Visual Under
        60260, -- 2602.22417 Absorbing Discrete Diffusion for Speech Enhancement
        61352, -- 2602.03310 RDT2: Exploring the Scaling Limit of UMI Data Towards Zero-Shot Cross-Embodiment
        66402, -- 2510.13068 NeuroRVQ: Multi-Scale EEG Tokenization for Generative Large Brainwave Models
        67870, -- 2509.20060 Discrete Diffusion for Generative Modeling of Text-Aligned Speech Tokens
        67929, -- 2509.19186 Improving Test-Time Performance of RVQ-based Neural Codecs
        68486, -- 2509.09550 Finite Scalar Quantization Enables Redundant and Transmission-Robust Neural Audi
        73103, -- 2505.07235 Multi-band Frequency Reconstruction for Neural Psychoacoustic Coding
        75631, -- 2412.01762 XQ-GAN: An Open-source Image Tokenization Framework for Autoregressive Generatio
        77343, -- 2404.19441 ESC: Efficient Speech Coding with Cross-Scale Residual Vector Quantized Transfor
        79067, -- 2305.02765 HiFi-Codec: Group-residual Vector quantization for High Fidelity Audio Codec
        79213, -- 2303.12984 LMCodec: A Low Bitrate Speech Codec With Causal Transformer Models
        92050, -- 2501.03078 Qinco2: Vector Compression and Search with Improved Implicit Neural Codebooks
        107021, -- 2506.05952 MOGO: Residual Quantized Hierarchical Causal Transformer for Real-Time and Infin
        109825, -- 2608.11593 Luna-TTS Family Technical Report
        110790, -- 2510.04577 Language Model Based Text-to-Audio Generation: Anti-Causally Aligned Collaborati
        111237, -- 2506.16538 Towards Bitrate-Efficient and Noise-Robust Speech Coding with Variable Bitrate R
        111750, -- 2506.15456 Factorized RVQ-GAN For Disentangled Speech Tokenization
        112005, -- external SPCODEC: Split and Prediction for Neural Speech Codec
        112095, -- external Efficient Streaming TTS Acoustic Model with Depthwise RVQ Decoding Strategies in
        113821, -- 2608.30935 LightNav-0: Eliciting VLM Spatial Intelligence for Generalist Embodied Navigatio
        114182, -- 2609.12945 StepAudio 3 Gen Technical Report
        117380, -- 2607.11215 Q-BridgeNet: A Quantization Network for Cross-Lingual Sign Language Translation
        120723, -- external Multi-level Causal LLM-based Text-to-Motion Generation with Human Alignment
        121966, -- 2609.16034 StepAudio 3 Music Technical Report
        124396, -- 2512.07192 HyperVQ: Enabling Hyperprior Entropy Modeling for VQ-Based Generative Image Comp
        125180, -- 2610.11105 TKCAM: Text and Keyframe to Camera Trajectory Generation
        125287, -- external Next-Token Prediction Enables Scalable Learning of Sleep Physiology
        125552, -- external Adaptive Residual Quantization for Memory-Efficient Temporal Action Segmentation
        126525, -- 2606.09241 Closing the Indexing-Decoding Gap in Multimodal Generative Retrieval via Prefix
        128996, -- 2607.02148 SAMoR: Motion Modelling for Articulated Objects of Any Skeleton and Topology
        130066  -- 2602.03570 Asymmetric Hierarchical Anchoring for Robust Audio–Visual Cross-Modal Generaliza
  );

DELETE FROM paper_method_exclusions x
USING rvq_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rvq_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM rvq_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE rvq_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'residual-vector-quantization'
  AND p.id IN (
        2085, -- 1905.03696 HAWQ: Hessian AWare Quantization of Neural Networks with Mixed-Precision
        13593, -- 2303.05068 Toward Unsupervised Realistic Visual Question Answering
        28512, -- 2403.04473 TextMonkey: An OCR-Free Large Multimodal Model for Understanding Document
        30873, -- 2404.18397 ViOCRVQA: Novel Benchmark Dataset and Vision Reader for Visual Question Answerin
        32532, -- 2406.05298 Spectral Codecs: Improving Non-Autoregressive Speech Synthesis with Spectrogram-
        40505, -- 2411.17335 MotionLLaMA: A Unified Framework for Motion Synthesis and Comprehension
        49032, -- 2505.13181 Efficient Speech Language Modeling via Energy Distance in Continuous Latent Spac
        49520, -- 2505.17426 UniTTS: An end-to-end TTS system without decoupling of acoustic and semantic inf
        52482, -- 2508.16790 TaDiCodec: Text-aware Diffusion Speech Tokenizer for Speech Language Modeling
        54741, -- 2512.02901 Fairy2i: Training Complex LLMs from Real LLMs with All Parameters in {pm 1, pm i
        69633, -- 2508.11196 UAV-VL-R1: Generalizing Vision-Language Models via Supervised Fine-Tuning and Mu
        71631, -- 2502.07707 PRVQL: Progressive Knowledge-guided Refinement for Robust Egocentric Visual Quer
        75629, -- 2412.01053 FreeCodec: A disentangled neural speech codec with fewer tokens
        83900, -- 2605.28992 FRAPPE: Full Input, Residual Output Autoencoding with Projection Pursuit Encoder
        91781, -- 2502.01084 Continuous Autoregressive Modeling with Stochastic Monotonic Alignment for Speec
        99390, -- 2512.01537 Two-dimensional quantization for geometry-aware audio coding
        100479, -- 2510.05176 PatternKV: Flattening KV Representation Expands Quantization Headroom
        108202, -- 2501.11790 Benchmarking LLMs’ Mathematical Reasoning with Unseen Random Variables Questions
        126039, -- 2602.20191 MoBiQuant: Mixture-of-Bits Quantization for Token-Adaptive Any-Precision LLM
        127871, -- 2603.02883 SemanticDialect: Semantic-Aware Mixed-Format Quantization for Video Diffusion Tr
        128915  -- external AudioGS: High-Fidelity Neural Audio Compression via Continuous Gaussian Splattin
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: RVQ abbreviates something else (RVQA, OCRVQA, RVQuant), scalar/weight residual quantization, or RVQ is only the contrasted alternative'
FROM rvq_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING rvq_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING rvq_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- mfcc: 41 reviewed true positives of 48 title/abstract candidates.
CREATE TEMP TABLE mfcc_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mfcc'
  AND p.id IN (
        781, -- 1706.09559 Audio Spectrogram Representations for Processing with Convolutional Neural Netwo
        2954, -- 1912.10458 Emotion Recognition from Speech
        5252, -- 2103.12157 Tiny Transformers for Environmental Sound Classification at the Edge
        5632, -- 2105.00933 Deep Neural Network for Musical Instrument Recognition using MFCCs
        6090, -- 2106.12174 Deep Neural Network Based Respiratory Pathology Classification Using Cough Sound
        6679, -- 2109.08941 Violence Detection in Videos
        8207, -- 2203.05780 Acoustic To Articulatory Speech Inversion Using Multi-Resolution Spectro-Tempora
        8467, -- 2203.15335 Iranian Modal Music (Dastgah) detection using deep neural networks
        12296, -- 2301.01378 An ensemble-based framework for mispronunciation detection of Arabic phonemes
        15438, -- 2305.06429 Mispronunciation Detection of Basic Quranic Recitation Rules using Deep Learning
        24548, -- 2312.05640 Keyword spotting -- Detecting commands in speech using deep learning
        32884, -- 2406.09345 DiscreteSLU: A Large Language Model with Self-Supervised Discrete Speech Units f
        35261, -- 2407.19340 Integrating Large Language Models into a Tri-Modal Architecture for Automated De
        35793, -- 2408.06804 Deep Learning for Speaker Identification: Architectural Insights from AB-1 Corpu
        40227, -- 2411.13592 A Novel Speech Analysis and Correction Tool for Arabic-Speaking Children
        47236, -- 2504.02598 Graphs are everywhere -- Psst! In Music Recommendation too
        50380, -- 2506.01365 Attention Is Not Always the Answer: Optimizing Voice Activity Detection with Sim
        63526, -- 2512.17281 LibriVAD: A Scalable Open Dataset with Deep Learning Benchmarks for Voice Activi
        64357, -- 2512.00563 Explainable Multi-Modal Deep Learning for Automatic Detection of Lung Diseases f
        67655, -- 2509.22808 ArFake: A Multi-Dialect Benchmark and Baselines for Arabic Spoof-Speech Detectio
        70659, -- 2507.20417 Two Views, One Truth: Spectral and Self-Supervised Features Fusion for Robust Sp
        72921, -- 2505.23781 Unified AI for Accurate Audio Anomaly Detection
        73050, -- 2505.10885 BanglaFake: Constructing and Evaluating a Specialized Bengali Deepfake Audio Dat
        80862, -- 2102.12664 MixSpeech: Data Augmentation for Low-resource Automatic Speech Recognition
        82219, -- 1706.07156 Comparison of Time-Frequency Representations for Environmental Sound Classificat
        82634, -- 1301.1932 An Approach for Classification of Dysfluent and Fluent Speech Using K-NN And SVM
        83084, -- external Niagara Batch English SSM
        95313, -- external MFCC Inspired Spectral Feature Extraction for Robust Touch Interaction in Social
        102699, -- external ESC: Dataset for Environmental Sound Classification
        109393, -- 2110.03427 Is Attention always needed? A Case Study on Language Identification from Speech
        111218, -- external Temporal Convolutional Network with Smoothed and Weighted Losses for Distant Voi
        111221, -- 2506.01129 Comparative Evaluation of Acoustic Feature Extraction Tools for Clinical Speech
        111274, -- external Comparison of Acoustic and Textual Features for Dysarthria Severity Classificati
        111487, -- 2506.01148 Towards Fusion of Neural Audio Codec-based Representations with Spectral for Hea
        111553, -- external Multimodal and Multitask Learning for Predicting Multiple Scores in L2 English S
        111627, -- external On Enhancing the Performance of Children's ASR Task in Limited Data Scenario
        111752, -- external Phonetic Posteriorgram-Based Phoneme Selection for Vocal Cord Disorder Classific
        111800, -- external Boosting StoRM Convergence with Metric Guidance and Non-uniform State-Sampling f
        112124, -- external Alzheimer’s Disease Detection Using Co-Attention Mechanism for Acoustic and ASR-
        114300, -- 2005.07272 Target-Speaker Voice Activity Detection: a Novel Approach for Multi-Speaker Diar
        130187  -- 2609.04134 Prospective Coding Improves Learning in Deep Continuous-Time Recurrent Networks
  );

DELETE FROM paper_method_exclusions x
USING mfcc_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mfcc_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM mfcc_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE mfcc_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mfcc'
  AND p.id IN (
        3064, -- 2002.01322 Training Keyword Spotters with Limited and Synthesized Speech Data
        18943, -- 2308.02560 From Discrete Tokens to High-Fidelity Audio Using Multi-Band Diffusion
        75903, -- 2410.24066 Cough-E: A multimodal, privacy-preserving cough detection algorithm for the edge
        76179, -- 2410.02560 Convolutional Variational Autoencoders for Spectrogram Compression in Automatic
        110720, -- 2509.05849 From perception to production: how acoustic invariance facilitates articulatory
        112090, -- external Intelligibility Prediction for Time-Modified Speech Signals Using Spectro-Tempor
        114955  -- external fTSPL: Enhancing Brain Analysis with fMRI-Text Synergistic Prompt Learning
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: MFCC only as a contrasted alternative, or PMFCC/another sense'
FROM mfcc_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING mfcc_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING mfcc_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- Hero image credits (images imported with import_entity_image.py). AdaGrad and
-- RMSProp have no image: no source figure exists and no openly licensed figure
-- was found.
UPDATE methods SET image_credit = '[Symbolic Discovery of Optimization Algorithms](/paper/2302.06675)' WHERE slug = 'lion';
UPDATE methods SET image_credit = '[Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification](/paper/1502.01852)' WHERE slug = 'kaiming-initialization';
UPDATE methods SET image_credit = '[DoRA: Weight-Decomposed Low-Rank Adaptation](/paper/2402.09353)' WHERE slug = 'dora';
UPDATE methods SET image_credit = '[Parameter-Efficient Transfer Learning for NLP](/paper/1902.00751)' WHERE slug = 'adapter-tuning';
UPDATE methods SET image_credit = '[SoundStream: An End-to-End Neural Audio Codec](/paper/2107.03312)' WHERE slug = 'residual-vector-quantization';
UPDATE methods SET image_credit = '[Mel cepstrum example](https://commons.wikimedia.org/wiki/File:Mel_cepstrum_example.png), RitsuCJ, CC0' WHERE slug = 'mfcc';
