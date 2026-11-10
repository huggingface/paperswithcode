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
    'adagrad', 'AdaGrad',
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
    'rmsprop', 'RMSProp',
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
    'lion', 'Lion',
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
    'dora', 'DoRA',
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
        13076, 18203, 21661, 21761, 29700, 40049, 40404, 42060, 44271, 53528, 58400, 60203, 68595, 71791, 86771, 99633,
        101113, 101435, 104458, 124188, 124533, 124789, 124885, 127859
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
        13201, 13935, 14181, 14709, 14957, 15346, 15498, 15581, 15888, 16073, 16162, 16488, 16719, 16821, 16883, 17089,
        17364, 17717, 19502, 19505, 19953, 20095, 20124, 21001, 21181, 21457, 21724, 22580, 23043, 23311, 23406, 23646,
        24094, 24110, 24237, 24352, 24743, 24889, 25010, 25462, 26020, 30405, 30726, 31170, 31598, 31760, 32112, 32185,
        32381, 32803, 33601, 35784, 36166, 36598, 36998, 37545, 38078, 38117, 39172, 39413, 39929, 40011, 40719, 41099,
        43044, 43898, 44780, 44903, 44940, 45061, 45367, 45809, 47380, 48326, 48381, 49923, 50231, 50439, 51136, 51889,
        53342, 53870, 54811, 55076, 56211, 56807, 58097, 58136, 58295, 58347, 59791, 60201, 60202, 60362, 60511, 60611,
        60883, 60885, 61692, 61764, 62123, 62136, 62263, 64089, 64468, 65222, 65711, 66350, 66555, 66911, 66928, 67506,
        69192, 72572, 72900, 74624, 74711, 74763, 75438, 75866, 75919, 77161, 78248, 83317, 83614, 84308, 85398, 85957,
        86119, 87290, 88722, 88783, 89714, 89717, 90012, 90123, 91046, 91174, 91563, 92255, 92749, 92860, 93047, 93071,
        93196, 93233, 93282, 94017, 94098, 94256, 94865, 95699, 96343, 98213, 98980, 99139, 99212, 99228, 99418, 99660,
        100397, 100528, 101125, 101242, 101481, 102697, 109052, 113599, 115572, 116700, 122137, 122743, 123250, 124368, 124496, 127110,
        128613, 129030, 129203, 129675, 131876, 131970
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
        27323, 31693, 38375, 39868, 40512, 41229, 42299, 42606, 42870, 43055, 49098, 51362, 51533, 51738, 55038, 56942,
        57633, 68313, 70328, 72557, 73554, 106580, 108775, 110364, 126452, 129666, 131192
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
        18988, 21911, 23650, 24373, 27018, 28647, 28948, 29184, 29276, 29909, 29949, 30140, 30249, 30328, 30626, 30676,
        30701, 31018, 31051, 31256, 31331, 31427, 31443, 31500, 31578, 31583, 31612, 31633, 31648, 31837, 31857, 31863,
        31938, 31959, 32017, 32096, 32159, 32286, 32362, 32368, 32527, 32581, 33017, 33176, 33285, 33308, 33655, 33676,
        33714, 34004, 34032, 34455, 34456, 34473, 34505, 35128, 35211, 35262, 35275, 35588, 35667, 35776, 35986, 36154,
        36245, 36333, 36424, 36431, 36591, 36648, 36700, 37208, 37237, 37311, 37649, 37854, 38116, 38327, 38361, 38432,
        38454, 38510, 38553, 38718, 38991, 39037, 39062, 39257, 39281, 39816, 39929, 40000, 40006, 40231, 40694, 40729,
        41032, 41085, 41206, 41221, 41339, 41872, 42169, 42251, 42349, 42450, 42572, 42770, 42786, 43031, 43162, 43194,
        43252, 43383, 43418, 43531, 43967, 44126, 44432, 44564, 44762, 44915, 44986, 44990, 45547, 46396, 46527, 46615,
        47109, 47200, 47395, 47485, 47812, 48132, 48148, 48236, 48433, 48575, 48999, 49143, 49388, 49778, 49906, 49933,
        50167, 50357, 50433, 50483, 50504, 50513, 50774, 51090, 51212, 51296, 51298, 51351, 51470, 51597, 51700, 51875,
        52903, 52916, 52925, 52967, 53452, 54592, 54677, 55157, 55208, 55251, 55841, 55884, 55984, 56354, 56621, 56692,
        56954, 57588, 57612, 57869, 58078, 58533, 59202, 59662, 59769, 59906, 60189, 60829, 60987, 61161, 61713, 61995,
        62312, 62988, 63124, 63300, 63360, 63574, 63617, 63935, 63971, 64532, 64655, 64705, 64801, 65014, 65509, 65616,
        65760, 65786, 66030, 66578, 66600, 66701, 66711, 67139, 67424, 67506, 67707, 68558, 68579, 68670, 69261, 70055,
        70076, 70189, 70252, 70445, 71317, 71402, 71412, 71784, 71860, 72180, 72314, 72325, 72373, 72524, 72591, 72881,
        72982, 72988, 73004, 73035, 73626, 74345, 74398, 75748, 75873, 76298, 76515, 76571, 76757, 77013, 77016, 77019,
        77114, 77294, 77554, 83016, 83972, 83996, 84249, 84313, 84323, 84570, 84611, 85001, 85003, 85170, 85285, 85523,
        85532, 85538, 85698, 85713, 85952, 86006, 86024, 86038, 86144, 86202, 86409, 86434, 86519, 86530, 86736, 87062,
        87282, 87332, 87482, 87538, 87958, 87975, 88174, 88189, 88331, 88348, 88467, 90118, 90436, 90488, 90783, 91000,
        91046, 91099, 91203, 91420, 91709, 91792, 91915, 91917, 91930, 92256, 92638, 92862, 92952, 93173, 93231, 93269,
        93304, 93369, 93420, 93930, 93937, 93980, 94019, 94133, 94380, 94473, 94630, 94755, 94861, 94923, 94962, 96101,
        97970, 98088, 98317, 99075, 99080, 99828, 100231, 100468, 101122, 102439, 102981, 104051, 105154, 105181, 105873, 106174,
        106325, 106710, 106932, 107470, 108961, 110589, 110603, 110919, 111338, 112144, 113807, 118162, 118211, 118224, 118439, 119504,
        119893, 120590, 120820, 121466, 121912, 122385, 122676, 122711, 123709, 124381, 124508, 124657, 124679, 125462, 125619, 125634,
        125867, 125945, 126014, 126786, 126986, 127161, 127316, 127390, 128918, 130411, 130446, 131122, 131844, 131866
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
        151, 56848, 85939, 85974, 87283, 94702, 94933, 101746, 126131
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
        333, 48909, 48999, 49279, 49709, 50041, 50054, 50167, 50239, 50241, 50719, 50808, 50810, 51050, 51090, 51174,
        51308, 51470, 51508, 51612, 51636, 52174, 52427, 52848, 53399, 53665, 53821, 54577, 55051, 55183, 55647, 55841,
        56621, 56688, 56846, 56868, 57636, 57671, 57747, 58901, 59687, 60407, 60479, 61519, 61970, 62560, 62653, 62707,
        62776, 62913, 63066, 64011, 64063, 64719, 65423, 65908, 66078, 66832, 66919, 67051, 67129, 67543, 67608, 68024,
        68313, 68785, 69155, 70071, 70252, 70445, 71083, 71141, 71317, 71402, 71618, 71696, 71699, 71784, 71978, 72027,
        72055, 72127, 72141, 72432, 72481, 72531, 72557, 72902, 72979, 84066, 84793, 85139, 85323, 85948, 86056, 86144,
        86335, 86504, 86519, 86991, 87152, 87318, 87358, 87588, 88331, 88604, 89108, 89793, 89890, 92565, 92623, 92626,
        92659, 92764, 92862, 93001, 93187, 93304, 93369, 93427, 94280, 94495, 94529, 94573, 94754, 94796, 94958, 95051,
        95063, 98031, 98144, 99124, 99252, 99356, 99539, 99685, 99857, 99865, 99974, 99989, 100231, 100497, 100768, 100823,
        100881, 100912, 100914, 101068, 101134, 101419, 101586, 101753, 101803, 101894, 101904, 102028, 102079, 102204, 102539, 102639,
        103127, 104558, 104845, 105480, 106484, 106735, 107119, 107285, 107416, 107608, 108417, 110458, 110526, 110682, 111384, 111601,
        111738, 113877, 119245, 121647, 122203, 124918, 125194, 125887, 126126, 127269, 128864, 129057, 129294, 129537, 130353, 130411,
        130962, 130996
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
        1803, 3067, 3483, 3489, 3895, 4847, 5489, 5917, 5926, 6036, 6536, 6622, 6784, 6934, 7075, 7465,
        7564, 7890, 7908, 8422, 8547, 8573, 8888, 8894, 9113, 9124, 9150, 9163, 9279, 9430, 9462, 9509,
        10180, 10321, 10358, 10408, 10612, 10658, 10679, 10745, 10849, 11035, 11145, 11167, 11483, 12010, 12043, 12073,
        12408, 12583, 12781, 12813, 12997, 13071, 13150, 13439, 13489, 13782, 13862, 13868, 14023, 14040, 14052, 14211,
        14231, 14452, 14515, 14599, 14779, 15065, 15435, 15490, 15491, 15948, 16186, 16191, 16349, 16353, 16746, 16918,
        17096, 17179, 17382, 17713, 17714, 17970, 18057, 18059, 18230, 18313, 18514, 18807, 18832, 19200, 19238, 19434,
        19443, 19712, 19937, 20071, 20072, 20187, 20339, 20365, 20537, 20874, 21136, 21227, 21236, 21412, 21630, 21662,
        22143, 22247, 22263, 22285, 22511, 22634, 22848, 22996, 23332, 23511, 24306, 24335, 24371, 24373, 24381, 24551,
        24893, 25439, 25510, 25918, 26103, 26208, 26553, 26596, 26716, 26873, 27152, 27496, 27541, 27605, 27675, 27804,
        27929, 28359, 28626, 28854, 29038, 29067, 29191, 29461, 29562, 29654, 29782, 29806, 29909, 30148, 30216, 30254,
        30281, 30384, 30577, 30822, 31007, 31184, 31400, 31544, 31648, 31938, 31957, 32527, 32676, 32747, 32916, 33468,
        33676, 33707, 34027, 34148, 34251, 34456, 34957, 35186, 35412, 35730, 35775, 35836, 36264, 36424, 36431, 36591,
        36741, 36975, 37065, 38022, 38257, 38510, 38817, 39816, 39843, 40195, 40532, 41221, 41738, 42423, 42450, 42770,
        43214, 43817, 44197, 45609, 45776, 46577, 46976, 47428, 47485, 49651, 49933, 50517, 50694, 51242, 51506, 53762,
        54677, 54899, 56573, 56613, 56848, 56849, 57753, 58891, 59769, 61888, 62988, 63971, 64651, 64705, 65360, 66394,
        66604, 66701, 66891, 67702, 68006, 68137, 68408, 68483, 69689, 69871, 70189, 70963, 70985, 71402, 71632, 71763,
        71978, 72219, 73514, 74513, 74592, 74622, 74678, 74990, 75020, 76250, 76515, 76571, 76834, 77512, 77559, 78035,
        78187, 78391, 78625, 78992, 79265, 79972, 80458, 82896, 83706, 84965, 85148, 85698, 85831, 86598, 86909, 87538,
        87596, 87607, 87817, 87919, 88020, 88588, 88931, 89493, 89634, 90019, 90248, 90265, 90342, 90545, 90636, 90704,
        90827, 90998, 91253, 91637, 93096, 93369, 94060, 94486, 94951, 96130, 96628, 96820, 97984, 99075, 99373, 99857,
        100531, 102079, 102418, 103126, 103154, 103243, 103589, 105357, 105641, 106484, 106646, 106710, 107019, 107124, 107197, 107274,
        107587, 107645, 107908, 109197, 109431, 109432, 110630, 111418, 111454, 111584, 112855, 112964, 113083, 113094, 113273, 113440,
        113653, 113938, 115022, 115545, 115568, 115613, 115677, 116063, 116179, 116268, 116478, 116502, 116526, 116802, 116854, 116995,
        118202, 118537, 119520, 119616, 119926, 120023, 120107, 120182, 120234, 120335, 120462, 120995, 121022, 123647, 123648, 123651,
        123653, 123709, 124389, 124443, 124736, 125634, 125867, 126786, 127309, 127470, 127638, 128909, 129279, 129635, 130062, 130528
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
        1582, 2715, 2730, 2782, 2788, 2795, 3230, 3417, 3693, 4143, 4242, 4345, 4402, 4411, 4643, 4735,
        4784, 4820, 4822, 4833, 4835, 5027, 5163, 5204, 5324, 5490, 5509, 5519, 5577, 5589, 6049, 6280,
        6404, 6534, 6776, 6854, 6877, 6901, 6941, 6961, 6972, 6984, 7049, 7103, 7128, 7141, 7256, 7402,
        7490, 7495, 7522, 7575, 7889, 8004, 8096, 8120, 8169, 8267, 8326, 8342, 8387, 8397, 8464, 8489,
        8615, 8626, 8675, 8705, 8748, 8772, 8776, 8882, 8981, 8990, 8999, 9004, 9016, 9073, 9099, 9117,
        9171, 9180, 9189, 9219, 9366, 9368, 9500, 9502, 9531, 9831, 9877, 9935, 9956, 9970, 9974, 9990,
        10071, 10094, 10096, 10099, 10124, 10189, 10207, 10275, 10381, 10452, 10491, 10578, 10613, 10633, 10637, 10661,
        10665, 10667, 10713, 10787, 10802, 10811, 10887, 10892, 10896, 10910, 10978, 11040, 11171, 11255, 11264, 11362,
        11379, 11475, 11500, 11530, 11551, 11785, 11836, 11846, 12065, 12124, 12170, 12178, 12379, 12489, 12501, 12607,
        12611, 12612, 12624, 12717, 12721, 12750, 12752, 12764, 12864, 12902, 12905, 13023, 13053, 13069, 13255, 13286,
        13307, 13361, 13410, 13458, 13471, 13478, 13493, 13504, 13505, 13573, 13575, 13577, 13589, 13598, 13697, 13718,
        13750, 13766, 13781, 13845, 13887, 13889, 13890, 13939, 13999, 14008, 14068, 14152, 14175, 14201, 14291, 14344,
        14378, 14612, 14669, 14672, 14710, 14730, 14748, 14763, 14821, 14928, 14933, 14982, 15063, 15084, 15118, 15213,
        15239, 15285, 15290, 15463, 15504, 15531, 15538, 15542, 15574, 15640, 15754, 15771, 15840, 15926, 15930, 15957,
        15958, 16017, 16036, 16047, 16063, 16132, 16226, 16232, 16240, 16369, 16374, 16409, 16451, 16453, 16480, 16503,
        16522, 16525, 16559, 16593, 16620, 16727, 16757, 16774, 16808, 16843, 16861, 16872, 16874, 16928, 17019, 17050,
        17081, 17111, 17118, 17123, 17143, 17150, 17194, 17318, 17341, 17395, 17401, 17432, 17546, 17590, 17613, 17686,
        17700, 17777, 17779, 17820, 17898, 17900, 17901, 17923, 17930, 18012, 18058, 18166, 18179, 18201, 18220, 18288,
        18402, 18435, 18498, 18526, 18713, 18859, 18953, 18961, 18988, 18996, 19151, 19180, 19300, 19312, 19371, 19386,
        19424, 19453, 19494, 19498, 19535, 19567, 19598, 19685, 19688, 19763, 19836, 19852, 19885, 20011, 20026, 20035,
        20157, 20171, 20234, 20269, 20284, 20311, 20356, 20375, 20401, 20478, 20501, 20525, 20713, 20816, 20923, 20925,
        20936, 20953, 20977, 20992, 21004, 21065, 21088, 21168, 21192, 21195, 21253, 21280, 21300, 21303, 21306, 21342,
        21363, 21422, 21613, 21635, 21652, 21654, 21692, 21711, 21768, 21784, 21795, 21799, 21873, 21907, 21971, 21979,
        22003, 22019, 22090, 22128, 22156, 22178, 22208, 22215, 22250, 22333, 22451, 22543, 22575, 22636, 22696, 22766,
        22879, 22966, 22987, 23115, 23134, 23175, 23206, 23329, 23376, 23404, 23419, 23455, 23501, 23532, 23545, 23561,
        23568, 23645, 23650, 23696, 23843, 23961, 23977, 24110, 24111, 24125, 24127, 24162, 24195, 24200, 24203, 24230,
        24298, 24363, 24370, 24379, 24393, 24423, 24444, 24480, 24561, 24656, 24659, 24680, 24688, 24714, 24735, 24778,
        24846, 24859, 24882, 24927, 24929, 24962, 24977, 25045, 25120, 25123, 25164, 25184, 25212, 25311, 25364, 25373,
        25408, 25470, 25492, 25494, 25498, 25531, 25592, 25601, 25603, 25609, 25611, 25749, 25804, 25821, 25877, 26029,
        26043, 26085, 26094, 26142, 26146, 26187, 26244, 26287, 26326, 26354, 26365, 26510, 26531, 26569, 26655, 26676,
        26758, 26788, 26833, 26839, 26925, 26946, 26947, 26960, 26976, 26996, 27000, 27018, 27037, 27069, 27186, 27206,
        27263, 27323, 27346, 27380, 27385, 27405, 27432, 27500, 27522, 27533, 27651, 27875, 27883, 27890, 27925, 27955,
        27999, 28013, 28035, 28042, 28055, 28111, 28114, 28173, 28192, 28299, 28377, 28457, 28497, 28570, 28573, 28607,
        28647, 28694, 28718, 28807, 28831, 28837, 28908, 29017, 29022, 29085, 29096, 29149, 29184, 29185, 29271, 29276,
        29304, 29314, 29385, 29392, 29467, 29501, 29555, 29669, 29674, 29726, 29744, 29895, 29949, 29986, 30005, 30020,
        30055, 30066, 30210, 30211, 30319, 30328, 30362, 30385, 30441, 30486, 30612, 30626, 30685, 30701, 30746, 30760,
        30817, 30848, 30881, 30899, 30953, 30974, 30982, 30987, 31023, 31074, 31131, 31249, 31288, 31415, 31443, 31512,
        31612, 31663, 31714, 31739, 31751, 31782, 31833, 31837, 31863, 31881, 31888, 31922, 31929, 32027, 32030, 32073,
        32080, 32096, 32159, 32163, 32187, 32249, 32263, 32368, 32400, 32424, 32536, 32597, 32614, 32625, 33017, 33018,
        33123, 33134, 33176, 33285, 33396, 33441, 33487, 33494, 33513, 33558, 33572, 33631, 33632, 33640, 33655, 33763,
        33817, 33870, 33912, 33938, 33956, 34002, 34032, 34082, 34089, 34156, 34161, 34171, 34237, 34336, 34420, 34505,
        34551, 34591, 34714, 34780, 34826, 34914, 34959, 35004, 35011, 35172, 35199, 35211, 35285, 35325, 35377, 35381,
        35387, 35395, 35441, 35468, 35478, 35588, 35667, 35683, 35799, 35811, 35826, 35873, 35967, 35986, 35997, 36075,
        36107, 36138, 36308, 36314, 36359, 36433, 36490, 36651, 36701, 36713, 36815, 36839, 36877, 36896, 36909, 36974,
        37169, 37208, 37311, 37324, 37592, 37612, 37649, 37656, 37670, 38067, 38194, 38207, 38304, 38327, 38360, 38361,
        38373, 38375, 38485, 38553, 38652, 38671, 38674, 38718, 38753, 38830, 38859, 39009, 39037, 39048, 39062, 39246,
        39248, 39257, 39307, 39320, 39388, 39623, 39801, 39868, 40006, 40118, 40236, 40303, 40335, 40388, 40937, 40938,
        41003, 41206, 41275, 41288, 41339, 41361, 41393, 41441, 41554, 41625, 41749, 41758, 41872, 42049, 42056, 42236,
        42251, 42258, 42286, 42349, 42358, 42407, 42489, 42572, 42606, 42791, 42870, 42894, 42924, 42974, 43055, 43162,
        43252, 43292, 43418, 43459, 43559, 43592, 43788, 43967, 44061, 44126, 44145, 44264, 44471, 44646, 44658, 44763,
        44787, 44811, 44865, 44882, 45035, 45091, 45197, 45231, 45547, 45761, 46141, 46222, 46452, 46615, 46661, 46716,
        46886, 46892, 46960, 47109, 47116, 47207, 47280, 47468, 47541, 47627, 47783, 47812, 48031, 48090, 48132, 48148,
        48320, 48520, 48579, 48816, 49147, 49306, 49576, 49786, 49821, 49875, 49906, 49910, 49977, 50167, 50357, 50407,
        50504, 50774, 50883, 51090, 51335, 51362, 51426, 51435, 51597, 51644, 51700, 51975, 52645, 52916, 52924, 53253,
        54515, 54526, 54550, 54590, 54830, 55350, 55708, 55841, 56220, 56559, 56567, 57492, 57606, 57633, 57687, 57873,
        57927, 58011, 58078, 58218, 58281, 58664, 58935, 59171, 59202, 59288, 59662, 59823, 59961, 59976, 59992, 60073,
        60121, 60196, 60447, 60532, 60689, 60745, 60777, 61119, 61257, 61284, 61335, 61357, 61463, 61482, 61488, 61713,
        61961, 62031, 62091, 62123, 62146, 62177, 62312, 62371, 62398, 62567, 62780, 63219, 63289, 63300, 63451, 63935,
        64127, 64208, 64281, 64374, 64391, 64655, 64801, 65014, 65064, 65154, 65186, 65273, 65529, 65760, 65842, 65887,
        65907, 66030, 66085, 66277, 66371, 66541, 66711, 66904, 66947, 66955, 67129, 67268, 67566, 67754, 67953, 67975,
        68025, 68197, 68313, 68437, 68504, 68852, 69230, 69272, 69430, 69915, 69971, 70054, 70185, 70489, 70519, 70555,
        71043, 71235, 71365, 71493, 71608, 71615, 71649, 71727, 71745, 71813, 71829, 71905, 72010, 72153, 72180, 72260,
        72314, 72327, 72358, 72373, 72502, 72524, 72557, 72591, 72603, 72831, 72864, 72871, 72959, 72982, 72988, 73004,
        73035, 73174, 73185, 73263, 73339, 73458, 73742, 73786, 73905, 73926, 74168, 74230, 74272, 74345, 74368, 74398,
        74435, 74436, 74485, 74774, 74855, 74909, 75518, 75638, 75666, 75861, 75873, 75982, 75987, 76003, 76267, 76330,
        76370, 76440, 76573, 76646, 76665, 76757, 76759, 76849, 76946, 77013, 77019, 77025, 77114, 77117, 77229, 77294,
        77355, 77357, 77432, 77525, 77569, 77572, 77726, 77729, 77857, 77995, 78046, 78415, 78519, 78569, 78794, 78971,
        79132, 79646, 79901, 80047, 80367, 81560, 83144, 83155, 83377, 83720, 83875, 84037, 84249, 84324, 84534, 85032,
        85282, 85329, 85473, 85483, 85532, 85560, 85713, 85818, 85851, 86158, 86202, 86468, 86519, 86530, 86551, 86556,
        86653, 86711, 87092, 87172, 87282, 87332, 87597, 87624, 87748, 87750, 87767, 87930, 87958, 88174, 88472, 88561,
        88755, 88888, 88967, 89071, 89252, 89871, 89873, 89890, 89892, 89967, 90118, 90142, 90343, 90449, 90506, 90665,
        90783, 91046, 91099, 91241, 91381, 91386, 91416, 91534, 91563, 91576, 91693, 91709, 91740, 91773, 91888, 91915,
        91917, 91930, 91951, 92072, 92087, 92111, 92163, 92244, 92254, 92256, 92260, 92582, 92613, 92790, 92952, 93269,
        93325, 93335, 93367, 93696, 93980, 93987, 94112, 94133, 94290, 94341, 94534, 94544, 94573, 94605, 94680, 94718,
        94807, 94861, 94865, 94923, 94962, 95037, 95099, 95212, 96211, 97118, 98146, 99296, 99340, 99356, 99382, 99439,
        99465, 99638, 99736, 99970, 100173, 100231, 100381, 100428, 100468, 100636, 100651, 100692, 100906, 101068, 101122, 101186,
        101604, 101728, 101840, 101891, 101934, 102234, 102307, 102437, 102619, 102652, 102676, 102742, 102791, 102837, 103092, 103127,
        103278, 103362, 103371, 103446, 103539, 103585, 104104, 105061, 105134, 105512, 105571, 105753, 105867, 106174, 106190, 106199,
        106244, 106411, 106463, 106491, 106580, 106597, 106740, 106751, 106932, 107028, 107246, 107285, 107307, 107363, 107400, 107411,
        107470, 107549, 107571, 107629, 107634, 107693, 107767, 107841, 107959, 108152, 108201, 108205, 108206, 108378, 108489, 108551,
        108640, 108815, 109216, 109311, 109434, 109436, 109957, 110030, 110228, 110241, 110334, 110380, 110458, 110526, 110555, 110567,
        110570, 110589, 110676, 110794, 110979, 111085, 111338, 111628, 111992, 112584, 112593, 112641, 112738, 112829, 112864, 112865,
        112993, 113002, 113055, 113079, 113325, 113451, 113473, 113491, 113650, 113807, 113892, 113941, 114943, 115019, 115084, 115188,
        115306, 115375, 115551, 115590, 115650, 115710, 115737, 115790, 115860, 115980, 115991, 116066, 116211, 116314, 116410, 116511,
        116598, 116788, 116948, 116989, 116993, 117016, 117956, 118114, 118126, 118136, 118146, 118168, 118182, 118194, 118211, 118212,
        118227, 119143, 119289, 119373, 119558, 119893, 119898, 119981, 120524, 120534, 120590, 121621, 122406, 122441, 122446, 123338,
        123646, 123649, 123650, 123652, 123654, 123780, 124278, 124605, 125469, 125619, 125818, 125866, 125945, 126627, 126722, 126765,
        126861, 126986, 127019, 127570, 127819, 127907, 128212, 128853, 129180, 129373, 130100, 130423, 131096, 131555, 131900, 131951
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
        1129, 1523, 3126, 3162, 4948, 13167, 17237, 20336, 21324, 27478, 27552, 32471, 33680, 39874, 58066, 68796,
        77354, 78901, 88732, 91483, 93816, 101242, 102337, 124753, 126553, 127575
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
        1026, 1851, 2358, 2583, 2733, 3644, 5132, 25306, 26354, 31598, 80222, 101193, 128904
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
        2379, 4928, 9082, 10293, 25866, 29807, 32199, 38078, 56162, 85968, 91427, 101193
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
        1026, 1220, 1851, 2023, 2402, 2583, 31598, 80222, 80736, 92864, 107111, 109052, 130073
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
        6198, 14776, 16707, 17265, 19973, 21177, 24900, 27588, 29890, 35632, 36413, 37113, 37561, 38742, 38802, 38850,
        40142, 40889, 41345, 41534, 42401, 49548, 51291, 51862, 52195, 55449, 56872, 57566, 58768, 59518, 60260, 61352,
        66402, 67870, 67929, 68486, 73103, 75631, 77343, 79067, 79213, 92050, 107021, 109825, 110790, 111237, 111750, 112005,
        112095, 113821, 114182, 117380, 120723, 121966, 124396, 125180, 125287, 125552, 126525, 128996, 130066
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
        2085, 13593, 28512, 30873, 32532, 40505, 49032, 49520, 52482, 54741, 69633, 71631, 75629, 83900, 91781, 99390,
        100479, 108202, 126039, 127871, 128915
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
        781, 2954, 5252, 5632, 6090, 6679, 8207, 8467, 12296, 15438, 24548, 32884, 35261, 35793, 40227, 47236,
        50380, 63526, 64357, 67655, 70659, 72921, 73050, 80862, 82219, 82634, 83084, 95313, 102699, 109393, 111218, 111221,
        111274, 111487, 111553, 111627, 111752, 111800, 112124, 114300, 130187
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
        3064, 18943, 75903, 76179, 110720, 112090, 114955
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
