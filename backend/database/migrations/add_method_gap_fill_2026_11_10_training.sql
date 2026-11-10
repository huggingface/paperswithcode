-- Method gap fill (2026-11-10 audit), group A: training infrastructure,
-- activations and normalization. Twelve widely used techniques were missing.
--
-- Sourced (introducing paper is local; "Introduced" banner added):
--   zero (1910.02054), mixed-precision-training (1710.03740),
--   ring-attention (2310.01889), gelu (1606.08415),
--   group-normalization (1803.08494), instance-normalization (1607.08022).
-- Unsourced (contested or pre-arXiv origins; source_url points to a canonical
-- reference and the description credits the seminal/popularizing papers):
--   tensor-parallelism (Megatron-LM popularized it; AlexNet and Mesh-TensorFlow
--   split layers across devices earlier), pipeline-parallelism (GPipe and
--   PipeDream appeared concurrently), learning-rate-warmup,
--   exponential-moving-average, early-stopping, silu (proposed in the GELU
--   paper, named SiLU by Elfwing et al., rediscovered as Swish by search).
--
-- Keywords tag papers through the daily keyword backfill, so they are exact
-- long-form names. "mixed precision" alone also names mixed-precision
-- quantization, so only "mixed precision training" is a keyword. Bare FSDP,
-- EMA, TP and PP live only in full_name/aliases.
--
-- abstract_linking: ZeRO is 'never' because the abstract matcher treats the
-- inner-capital name "ZeRO" case-insensitively, so it would match every
-- "zero-shot" abstract.
--
-- Paper links were reviewed: for sourced methods, the local Semantic Scholar
-- citers of the source paper; for all methods, bounded title/abstract regex
-- candidates. True positives get 'manual' evidence; reviewed negatives become
-- durable exclusions so the keyword and reference backfills do not re-link
-- them. Hero images were imported separately with import_entity_image.py;
-- their credits are recorded at the end of this file.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES
(
    'zero', 'ZeRO',
    'Zero Redundancy Optimizer (ZeRO)',
    'The Zero Redundancy Optimizer (ZeRO) removes the memory redundancy of data-parallel training by partitioning model states across data-parallel workers instead of replicating them. Stage 1 shards the optimizer states (for example the [Adam](/methods/adam) moments and FP32 master weights of [mixed precision training](/methods/mixed-precision-training)), stage 2 also shards gradients, and stage 3 also shards the parameters, which are gathered layer by layer with all-gather collectives just before they are needed in the forward and backward pass and released afterwards. Per-device memory for model states then falls roughly linearly with the number of workers, while communication stays close to standard data parallelism, so models can be trained far beyond the memory of one GPU without rewriting them as in [tensor parallelism](/methods/tensor-parallelism) or [pipeline parallelism](/methods/pipeline-parallelism). Introduced in DeepSpeed by [Rajbhandari et al.](/paper/1910.02054), it was extended to CPU and NVMe offloading in [ZeRO-Offload](/paper/2101.06840) and [ZeRO-Infinity](/paper/2104.07857). PyTorch implements stage 3 as Fully Sharded Data Parallel ([FSDP](/paper/2304.11277)), the default way to shard large-model training today, often combined with [gradient checkpointing](/methods/gradient-checkpointing).',
    'zero redundancy optimizer, fully sharded data parallel, fully sharded data parallelism, ZeRO-Offload, ZeRO-Infinity',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2019,
    (SELECT id FROM papers WHERE arxiv_id = '1910.02054'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'ZeRO: Memory Optimizations Toward Training Trillion Parameter Models',
    'https://github.com/deepspeedai/DeepSpeed/tree/master/deepspeed/runtime/zero',
    NULL,
    'never',
    ARRAY['Fully Sharded Data Parallel (FSDP)']
),
(
    'mixed-precision-training',
    'Mixed Precision Training',
    'Mixed Precision Training',
    'Mixed precision training runs most of the arithmetic of neural network training in a low-precision floating-point format such as FP16 or bfloat16 while keeping numerically sensitive parts in FP32. As formalized by [Micikevicius et al.](/paper/1710.03740), weights, activations and gradients are stored and multiplied in half precision, an FP32 master copy of the weights accumulates the updates so that small gradient steps are not rounded away, and loss scaling multiplies the loss before backpropagation so that small gradients do not underflow to zero in FP16. Reductions, softmax and normalization statistics are typically accumulated in FP32. This halves activation and weight memory and uses the much faster tensor-core matrix units of modern accelerators, usually without loss of accuracy. bfloat16, studied by [Kalamkar et al.](/paper/1905.12322), keeps the FP32 exponent range and needs no loss scaling, and [FP8](/methods/fp8) training ([Micikevicius et al., 2022](/paper/2209.05433)) pushes precision lower with per-tensor scaling. Automatic mixed precision (AMP) in PyTorch and other frameworks makes the technique a default for training large models, alongside [ZeRO](/methods/zero) and [gradient checkpointing](/methods/gradient-checkpointing).',
    'mixed precision training, mixed-precision training',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2017,
    (SELECT id FROM papers WHERE arxiv_id = '1710.03740'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Mixed Precision Training',
    'https://github.com/pytorch/pytorch/blob/main/torch/amp/autocast_mode.py',
    NULL,
    'always',
    ARRAY[]::text[]
),
(
    'tensor-parallelism',
    'Tensor Parallelism',
    'Tensor Parallelism (TP)',
    'Tensor parallelism is a form of model parallelism that splits the individual weight matrices of a layer across devices, so that every device holds a slice of every layer and computes part of each matrix multiplication. In the scheme popularized for [Transformers](/methods/transformer) by [Megatron-LM](/paper/1909.08053), the first linear layer of each MLP block is split by columns and the second by rows, and attention is split by heads, so each block needs only one all-reduce in the forward pass and one in the backward pass. Splitting layers across devices is older, for example the two-GPU AlexNet and Mesh-TensorFlow, but Megatron-LM made intra-layer tensor parallelism the standard way to train large language models. Because it communicates inside every layer, it is usually confined to the fast interconnect within one node and combined with [pipeline parallelism](/methods/pipeline-parallelism) across nodes and data parallelism or [ZeRO](/methods/zero) on top, as in the 3D parallelism of [Narayanan et al.](/paper/2104.04473). Sequence parallelism additionally shards the activations of normalization and dropout along the sequence, and tensor parallelism is also used at inference time to split large models over several accelerators ([Pope et al.](/paper/2211.05102)).',
    'tensor parallelism, tensor-parallelism, tensor parallel, tensor-parallel, tensor model parallelism, intra-layer model parallelism',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://huggingface.co/spaces/nanotron/ultrascale-playbook',
    'The Ultra-Scale Playbook: Training LLMs on GPU Clusters (Hugging Face)',
    'https://github.com/NVIDIA/Megatron-LM/tree/main/megatron/core/tensor_parallel',
    NULL,
    'always',
    ARRAY['Tensor Model Parallelism', 'Intra-Layer Model Parallelism']
),
(
    'pipeline-parallelism',
    'Pipeline Parallelism',
    'Pipeline Parallelism (PP)',
    'Pipeline parallelism is a form of model parallelism that partitions a network by depth into consecutive stages placed on different devices and streams micro-batches through them, so that the stages work on different micro-batches at the same time instead of waiting for each other. [GPipe](/paper/1811.06965) splits each mini-batch into micro-batches, runs all forward passes and then all backward passes, and applies one synchronous update, at the cost of an idle "bubble" at the start and end of every batch that shrinks as the number of micro-batches grows; [PipeDream](/paper/1806.03377) introduced the one-forward-one-backward (1F1B) schedule with weight stashing, which bounds activation memory. Later schedules such as interleaved 1F1B ([Narayanan et al.](/paper/2104.04473)), zero-bubble and DualPipe schedules further reduce idle time. Pipeline parallelism only communicates activations between neighbouring stages, so it scales across nodes with slower interconnects and is combined with [tensor parallelism](/methods/tensor-parallelism) within a node and data parallelism or [ZeRO](/methods/zero) across replicas in the 3D parallelism used to train large language models, usually together with [gradient checkpointing](/methods/gradient-checkpointing).',
    'pipeline parallelism, pipeline-parallelism, pipeline parallel, pipeline-parallel, pipeline model parallelism',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://huggingface.co/spaces/nanotron/ultrascale-playbook',
    'The Ultra-Scale Playbook: Training LLMs on GPU Clusters (Hugging Face)',
    'https://github.com/NVIDIA/Megatron-LM/tree/main/megatron/core/pipeline_parallel',
    NULL,
    'always',
    ARRAY['Pipeline Model Parallelism']
),
(
    'ring-attention',
    'Ring Attention',
    'Ring Attention',
    'Ring Attention distributes exact self-attention over very long sequences across many devices arranged in a ring. Each device holds one block of the query, key and value sequence; it computes [blockwise attention](/paper/2305.19370) of its queries against the key-value block it currently holds while passing that block to the next device and receiving the previous one, so after one full rotation every query block has attended to the whole sequence. Because communication of key-value blocks overlaps with the blockwise computation, and the online softmax of memory-efficient attention such as [FlashAttention](/methods/flash-attention) combines the partial results exactly, the maximum context grows linearly with the number of devices without approximation or extra overhead. [Liu et al.](/paper/2310.01889) introduced it for training and inference with millions of tokens; Ring Self-Attention in [sequence parallelism](/paper/2105.13120) passed keys and values around a ring earlier without the blockwise memory savings. [Striped Attention](/paper/2311.09431) balances the causal mask across devices, and Ring Attention is a main form of context parallelism alongside all-to-all head sharding such as [DeepSpeed Ulysses](/paper/2309.14509), used to train long-context [Transformers](/methods/transformer) and video-language world models.',
    'ring attention, RingAttention',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2310.01889'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Ring Attention with Blockwise Transformers for Near-Infinite Context',
    'https://github.com/haoliuhl/ringattention',
    NULL,
    'always',
    ARRAY['RingAttention']
),
(
    'learning-rate-warmup',
    'Learning Rate Warmup',
    'Learning Rate Warmup',
    'Learning rate warmup starts training with a small learning rate and increases it, usually linearly, to the target value over the first few hundred or thousand steps before the main [learning rate schedule](/methods/learning-rate-scheduler), such as [cosine annealing](/methods/cosine-annealing) or inverse square-root decay, takes over. Early in training the weights, normalization statistics and the second-moment estimates of adaptive optimizers such as [Adam](/methods/adam) are poorly calibrated, so large steps can diverge; warmup avoids these unstable early updates. [He et al.](/paper/1512.03385) used a short constant low-learning-rate phase to train very deep ResNets, [Goyal et al.](/paper/1706.02677) introduced gradual linear warmup together with the linear scaling rule for large-batch SGD, and the original [Transformer](/paper/1706.03762) relied on warmup to train at all. Later work explained the need for warmup by the variance of Adam''s adaptive learning rate ([RAdam](/paper/1908.03265)) and by the large gradients near the output of Post-LN Transformers ([Xiong et al.](/paper/2002.04745)). Warmup is now part of nearly every recipe for training Transformers and large-batch vision models, with warmup-stable-decay schedules common for large language models.',
    'learning rate warmup, learning-rate warmup, learning rate warm-up, learning-rate warm-up, linear warmup, warmup schedule',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://d2l.ai/chapter_optimization/lr-scheduler.html',
    'Learning Rate Scheduling: Warmup (Dive into Deep Learning)',
    NULL,
    NULL,
    'always',
    ARRAY['Learning Rate Warm-up']
),
(
    'exponential-moving-average',
    'Exponential Moving Average',
    'Exponential Moving Average (EMA)',
    'An exponential moving average (EMA) of model weights keeps a shadow copy θ_EMA ← βθ_EMA + (1 − β)θ of the parameters during training, with a decay β close to 1 (for example 0.999 or 0.9999), and uses the averaged weights for evaluation, sampling or as a target. Averaging the iterates of stochastic optimization goes back to Polyak and Ruppert averaging, which provably speeds up stochastic approximation; the exponential variant weights recent iterates more and tracks a moving model, smoothing out the noise of [SGD](/methods/sgd) and [Adam](/methods/adam) updates and usually improving generalization at no extra training cost, similar to stochastic weight averaging ([Izmailov et al.](/paper/1803.05407)). EMA weights are standard in diffusion models ([DDPM](/paper/2006.11239), with power-function EMA profiles studied in [EDM2](/paper/2312.02696)) and GANs ([Progressive GAN](/paper/1710.10196)), and an EMA of the online network forms the teacher or target network in Mean Teacher, [BYOL](/paper/2006.07733), [DINO](/methods/dino), momentum contrast and soft target-network updates in deep reinforcement learning.',
    'exponential moving average, exponentially moving average, polyak averaging, polyak-ruppert averaging',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1137/0330046',
    'Acceleration of Stochastic Approximation by Averaging (Polyak & Juditsky, 1992)',
    NULL,
    NULL,
    'judge',
    ARRAY['Polyak Averaging', 'Polyak-Ruppert Averaging']
),
(
    'early-stopping',
    'Early Stopping',
    'Early Stopping',
    'Early stopping is a regularization technique that ends training when performance on a held-out validation set stops improving, and keeps the parameters from the best validation checkpoint. As training continues, training loss keeps falling while validation loss eventually rises as the model starts to overfit, so the number of training iterations acts as a capacity control: for linear models trained with gradient descent, early stopping behaves much like L2 regularization or [weight decay](/methods/weight-decay). In practice a patience criterion stops training after the validation metric has not improved for a given number of epochs, and Prechelt (1998) compared such stopping criteria systematically. Early stopping is among the most widely used regularizers in deep learning alongside [Dropout](/methods/dropout) and weight decay, is a standard tool in hyperparameter search (where successive halving and Hyperband stop unpromising runs early), and is studied in theory for its role in noisy-label robustness, implicit regularization and benign overfitting.',
    'early stopping, early-stopping',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1007/3-540-49430-8_3',
    'Early Stopping - But When? (Prechelt, 1998)',
    NULL,
    NULL,
    'judge',
    ARRAY[]::text[]
),
(
    'gelu', 'GELU',
    'Gaussian Error Linear Unit (GELU)',
    'The Gaussian Error Linear Unit (GELU) is an activation function defined as GELU(x) = x·Φ(x), where Φ is the standard normal cumulative distribution function. Instead of gating inputs by their sign as the [ReLU](/methods/rectified-linear-unit-relu) does, it weights each input by the probability that a standard Gaussian variable is smaller than it, which gives a smooth, non-monotonic curve that is slightly negative for small negative inputs; it is often computed with the approximation 0.5x(1 + tanh(√(2/π)(x + 0.044715x³))). [Hendrycks and Gimpel](/paper/1606.08415) motivated it as the expectation of a stochastic, input-dependent dropout-like mask and showed gains over ReLU and ELU on vision, language and speech tasks. GELU became the default feed-forward activation of [BERT](/methods/bert), [GPT-2](/methods/gpt-2), the [Vision Transformer](/methods/vision-transformer) and many later [Transformers](/methods/transformer), and its gated form GEGLU is a sibling of [SwiGLU](/methods/swiglu). The same paper also proposed x·σ(x), now known as [SiLU](/methods/silu) or Swish.',
    'GELU, gaussian error linear unit, gaussian error linear units',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2016,
    (SELECT id FROM papers WHERE arxiv_id = '1606.08415'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Gaussian Error Linear Units (GELUs)',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
),
(
    'silu', 'SiLU',
    'Sigmoid Linear Unit (SiLU)',
    'The Sigmoid Linear Unit (SiLU), also known as Swish, is the activation function SiLU(x) = x·σ(x), where σ is the logistic sigmoid; the Swish form x·σ(βx) adds a fixed or learnable β. It is smooth, non-monotonic and unbounded above, close to the [ReLU](/methods/rectified-linear-unit-relu) for large inputs but with a small negative dip and non-zero gradients for negative inputs. It was proposed alongside the [GELU](/methods/gelu) by [Hendrycks and Gimpel](/paper/1606.08415), named the sigmoid-weighted linear unit (SiLU) by [Elfwing et al.](/paper/1702.03118) for neural-network function approximation in reinforcement learning, and rediscovered by automated search as Swish by [Ramachandran et al.](/paper/1710.05941), who found that it consistently matched or beat ReLU on ImageNet and machine translation. SiLU is the activation of EfficientNet, YOLOv5 and later YOLO detectors, and the U-Nets of diffusion models, and its gated form [SwiGLU](/methods/swiglu) is the feed-forward layer of most current large language models.',
    'SiLU, sigmoid linear unit, sigmoid-weighted linear unit, swish activation, swish function',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://docs.pytorch.org/docs/stable/generated/torch.nn.SiLU.html',
    'torch.nn.SiLU (PyTorch documentation)',
    NULL,
    NULL,
    'always',
    ARRAY['Swish']
),
(
    'group-normalization',
    'Group Normalization',
    'Group Normalization (GroupNorm)',
    'Group Normalization (GroupNorm) normalizes the activations of a layer within groups of channels: the channels of each sample are split into G groups, and each group is standardized by the mean and variance computed over its channels and spatial positions, followed by a learned per-channel scale and shift. Because its statistics come from a single sample, its accuracy does not depend on the batch size, unlike [Batch Normalization](/methods/batch-normalization), whose error grows quickly for small batches. With G = 1 it reduces to [Layer Normalization](/methods/layer-normalization) over all channels and with one channel per group to [Instance Normalization](/methods/instance-normalization). [Wu and He](/paper/1803.08494) showed that a ResNet-50 with GroupNorm (G = 32) trained with a batch of 2 images per GPU had 10.6% lower ImageNet error than its BatchNorm counterpart, and that it transfers better to detection and segmentation, where memory limits batches to one or two images per GPU. GroupNorm is now standard in Mask R-CNN-style detectors, video models, the U-Nets of diffusion models such as [DDPM](/paper/2006.11239) and [latent diffusion](/paper/2112.10752), and, with Weight Standardization, in large-scale transfer models.',
    'group normalization, GroupNorm',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2018,
    (SELECT id FROM papers WHERE arxiv_id = '1803.08494'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Group Normalization',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
),
(
    'instance-normalization',
    'Instance Normalization',
    'Instance Normalization (InstanceNorm)',
    'Instance Normalization (InstanceNorm) standardizes each channel of each sample separately by the mean and variance over its spatial positions, followed by an optional learned scale and shift. [Ulyanov et al.](/paper/1607.08022) showed that replacing [Batch Normalization](/methods/batch-normalization) with instance normalization in feed-forward style-transfer generators, at both training and test time, removes instance-specific contrast information from the content image and markedly improves the quality of stylized images. It became a standard layer of image-to-image translation and style transfer networks such as [CycleGAN](/methods/cyclegan), and adaptive instance normalization ([AdaIN](/paper/1703.06868)), which replaces the learned affine parameters with the channel statistics of a style image, enabled arbitrary style transfer and the style modulation of [StyleGAN](/methods/stylegan). Instance normalization is the special case of [Group Normalization](/methods/group-normalization) with one channel per group, and it is also used in medical image segmentation networks such as nnU-Net, in domain generalization to remove style statistics, and in time-series forecasting, where reversible instance normalization (RevIN) handles distribution shift.',
    'instance normalization, InstanceNorm',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2016,
    (SELECT id FROM papers WHERE arxiv_id = '1607.08022'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Instance Normalization: The Missing Ingredient for Fast Stylization',
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- Introduced banners for the sourced methods.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN (
    'zero', 'mixed-precision-training', 'ring-attention', 'gelu',
    'group-normalization', 'instance-normalization'
) AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

-- Reviewed paper links (2026-11-10). Candidates: local Semantic Scholar citers of
-- the source paper (sourced methods) plus bounded title/abstract regex matches.
-- Positives name and use, extend, analyze, survey or compare against the method
-- in their title/abstract; reviewed negatives become durable exclusions so the
-- keyword and reference backfills do not re-link them.

-- zero: 41 links, 766 exclusions (local S2 citers that do not name the method are excluded).
CREATE TEMP TABLE zero_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'zero'
  AND p.id IN (
        2632, 4908, 5476, 5882, 6409, 7074, 11300, 12851, 14882, 17563, 22838, 23013, 26421, 32794, 39489, 42497,
        42603, 47380, 47403, 51037, 53342, 55539, 55778, 56345, 57280, 61119, 62983, 67229, 72550, 73267, 74103, 75627,
        76885, 77843, 86348, 92869, 99721, 106449, 121997, 122513, 125652
  );

DELETE FROM paper_method_exclusions x
USING zero_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM zero_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM zero_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE zero_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'zero'
  AND p.id IN (
        4342, 4948, 5485, 7450, 8472, 8992, 11282, 11667, 11850, 13935, 14309, 14349, 14891, 15877, 16240, 16540,
        16618, 17530, 17650, 17744, 18201, 18491, 18988, 19454, 20012, 20193, 20598, 20626, 21310, 21471, 21525, 21561,
        21635, 21695, 21733, 21761, 22029, 22046, 22060, 22130, 23164, 23343, 24041, 24356, 24493, 24612, 24631, 24640,
        24995, 25002, 25023, 25263, 25270, 25364, 25414, 25466, 25711, 25836, 25913, 26042, 26337, 26354, 26358, 26429,
        26455, 26597, 26643, 26675, 26776, 27080, 27111, 27193, 27478, 27507, 27603, 27696, 27725, 27965, 28114, 28341,
        28423, 28461, 28506, 28510, 28801, 28988, 29124, 29234, 29474, 29496, 29501, 29900, 29982, 30052, 30123, 30477,
        30704, 31121, 31128, 31181, 31213, 31244, 31297, 31331, 31399, 31468, 31486, 31558, 31629, 31693, 31752, 31775,
        31779, 31820, 31825, 31906, 31911, 31912, 32082, 32088, 32129, 32329, 32355, 32393, 32486, 32631, 32634, 32646,
        32688, 32696, 32822, 33008, 33087, 33096, 33200, 33359, 33374, 33558, 33601, 33610, 33670, 33749, 33765, 34062,
        34158, 34276, 34336, 34392, 34420, 34443, 34509, 34671, 34697, 34801, 34869, 34923, 35105, 35153, 35165, 35280,
        35305, 35338, 35455, 35521, 35535, 35756, 35823, 35969, 35978, 36008, 36170, 36172, 36229, 36271, 36316, 36323,
        36535, 36554, 36645, 36651, 36662, 36669, 36680, 36745, 36782, 36786, 36834, 37088, 37109, 37188, 37220, 37385,
        37463, 37655, 37824, 37869, 37898, 38017, 38087, 38126, 38162, 38169, 38192, 38234, 38239, 38309, 38820, 38915,
        38936, 38944, 39008, 39054, 39058, 39060, 39085, 39210, 39246, 39248, 39257, 39296, 39446, 39464, 39533, 39569,
        39633, 39786, 39838, 39874, 39929, 39985, 40112, 40124, 40126, 40166, 40257, 40327, 40362, 40411, 40428, 40673,
        40729, 40840, 40894, 41076, 41130, 41233, 41309, 41438, 41458, 41678, 41797, 41833, 41851, 41861, 41891, 41913,
        41993, 42211, 42349, 42368, 42485, 42617, 42748, 42815, 42974, 43007, 43044, 43053, 43097, 43174, 43302, 43326,
        43427, 43544, 43707, 43792, 44012, 44135, 44136, 44203, 44207, 44223, 44314, 44355, 44411, 44432, 44527, 44579,
        44840, 44893, 44897, 44939, 45102, 45224, 45229, 45318, 45398, 45416, 45437, 45497, 45553, 45626, 45663, 45691,
        45712, 45731, 45891, 45991, 46002, 46158, 46211, 46212, 46275, 46531, 46541, 46567, 46591, 46622, 46706, 46772,
        46793, 46897, 46965, 47002, 47029, 47082, 47106, 47131, 47168, 47179, 47243, 47288, 47328, 47433, 47488, 47507,
        47818, 47899, 48011, 48326, 48345, 48490, 48603, 48783, 48788, 48842, 48866, 48874, 48935, 48946, 48991, 48992,
        49087, 49112, 49147, 49177, 49274, 49366, 49376, 49407, 49468, 49481, 49500, 49514, 49571, 49708, 49919, 50062,
        50168, 50192, 50217, 50235, 50297, 50377, 50451, 50481, 50487, 50528, 50708, 50775, 50801, 50959, 51090, 51164,
        51178, 51188, 51271, 51471, 51502, 51505, 51629, 51674, 51733, 51803, 51928, 52023, 52052, 52081, 52111, 52143,
        52191, 52246, 52290, 52377, 52469, 52558, 52840, 52843, 52846, 52927, 53051, 53070, 53139, 53149, 53202, 53329,
        53379, 53403, 53409, 53441, 53488, 53521, 53556, 53571, 53675, 53676, 53750, 53944, 53949, 54004, 54060, 54317,
        54588, 54642, 54751, 54858, 54901, 55003, 55015, 55086, 55090, 55566, 55756, 55843, 55865, 56081, 56091, 56136,
        56155, 56356, 56373, 56395, 56399, 56440, 56554, 56837, 56942, 57059, 57160, 57164, 57172, 57288, 57560, 57810,
        58136, 58187, 58295, 58342, 58401, 58740, 58853, 59030, 59259, 59269, 59288, 59305, 59581, 59796, 59861, 59940,
        59992, 60104, 60167, 60203, 60437, 60532, 60899, 61219, 61520, 61556, 61627, 61713, 61773, 61961, 62164, 62197,
        62277, 62453, 62522, 62541, 62946, 63190, 63360, 63592, 63926, 63931, 64207, 64479, 64517, 64767, 64773, 64785,
        65061, 65068, 65262, 65308, 65516, 66075, 66537, 66794, 66833, 66886, 67020, 67268, 67372, 67624, 67738, 67826,
        68002, 68063, 68133, 68247, 68326, 68642, 68678, 68685, 68705, 68793, 68921, 69069, 69123, 69167, 69306, 69363,
        69397, 69408, 69413, 69503, 69989, 70066, 70634, 70636, 70648, 70855, 71000, 71058, 71083, 71182, 71461, 71518,
        71608, 71637, 71652, 71664, 71904, 72034, 72053, 72087, 72204, 72270, 72356, 72524, 72572, 72589, 72661, 72689,
        72785, 72793, 72837, 72936, 72939, 73038, 73369, 73426, 73567, 73805, 73963, 74106, 74148, 74306, 74316, 74348,
        74394, 74515, 74544, 74573, 74635, 74763, 74766, 74917, 75115, 75126, 75280, 75371, 75538, 75792, 75829, 75886,
        75912, 76243, 76806, 77103, 77114, 77644, 77718, 77935, 78087, 78356, 82852, 83004, 83108, 83118, 83228, 83426,
        83477, 83580, 83858, 84286, 85025, 85047, 85365, 85389, 85706, 86041, 86109, 86126, 86234, 86501, 86835, 87127,
        87567, 87809, 88579, 88764, 88841, 89242, 89724, 91031, 91054, 91668, 92085, 92371, 92808, 92977, 93504, 93517,
        93562, 93787, 94251, 94340, 94410, 94623, 95074, 98038, 98200, 98207, 98542, 98817, 98861, 98962, 98980, 99144,
        99176, 99222, 99312, 99377, 99890, 99920, 100072, 100146, 100172, 100246, 100301, 100428, 100758, 101211, 101279, 101402,
        101457, 101526, 101888, 102287, 102409, 103129, 103321, 103423, 103526, 103535, 103557, 103604, 103677, 103899, 104007, 104064,
        104301, 104389, 104458, 104584, 106310, 106352, 106376, 106684, 109280, 109291, 109644, 109699, 110020, 110152, 110228, 110818,
        111702, 112804, 114019, 114054, 114104, 117326, 118993, 119292, 119431, 120362, 120735, 121987, 122125, 122360, 122787, 122817,
        123544, 123864, 124184, 124556, 124898, 125131, 125416, 125866, 125887, 126042, 126344, 126786, 126805, 126952, 127415, 127465,
        127881, 128044, 128367, 128547, 129544, 129707, 129793, 131249, 131571, 131598, 131605, 131624, 131816, 131820
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: names ZeRO/FSDP only in passing, or cites the ZeRO paper without naming it in title/abstract'
FROM zero_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING zero_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING zero_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- mixed-precision-training: 30 links, 642 exclusions (local S2 citers that do not name the method are excluded).
CREATE TEMP TABLE mpt_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mixed-precision-training'
  AND p.id IN (
        908, 1082, 1943, 2156, 2482, 2571, 4352, 22672, 25845, 31094, 32163, 36323, 36799, 42092, 43044, 43348,
        44334, 45840, 48721, 49214, 54437, 60105, 60203, 61520, 64342, 64397, 74418, 78495, 101668, 131217
  );

DELETE FROM paper_method_exclusions x
USING mpt_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mpt_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM mpt_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE mpt_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mixed-precision-training'
  AND p.id IN (
        1312, 1627, 1677, 1767, 1865, 1935, 2034, 2085, 2144, 2273, 2369, 2561, 2632, 2780, 2792, 2806,
        2856, 2978, 3129, 3375, 3388, 3434, 3613, 3683, 3700, 3738, 3747, 3757, 3839, 4037, 4154, 4325,
        4342, 4593, 4709, 4840, 4845, 4879, 4933, 4989, 5058, 5086, 5104, 5108, 5121, 5188, 5272, 5287,
        5294, 5484, 5582, 5702, 5741, 5773, 5804, 5882, 5909, 5985, 6047, 6050, 6061, 6270, 6358, 6409,
        6474, 6489, 6493, 6641, 6659, 6811, 6831, 6877, 6917, 6978, 7002, 7079, 7100, 7164, 7214, 7276,
        7284, 7357, 7575, 7576, 7604, 7690, 7781, 7792, 7912, 7925, 8004, 8165, 8246, 8446, 8466, 8473,
        8903, 8907, 9022, 9377, 9524, 9538, 9573, 9581, 9669, 9851, 9935, 10052, 10139, 10183, 10189, 10263,
        10361, 10578, 10614, 10765, 10952, 11237, 11281, 11409, 11495, 11679, 11687, 11729, 11820, 11850, 12031, 12199,
        12222, 12243, 12323, 12345, 12565, 12588, 12600, 12604, 12652, 12978, 13173, 13387, 13687, 13802, 13902, 13926,
        13948, 14177, 14337, 14349, 14375, 14388, 14394, 14462, 14463, 14502, 14624, 14676, 14686, 14699, 14782, 14866,
        14882, 14957, 15199, 15211, 15369, 15468, 15475, 15779, 15969, 16024, 16065, 16154, 16397, 16405, 16540, 16618,
        16729, 16746, 16774, 16925, 17002, 17090, 17134, 17530, 17650, 17714, 17779, 17848, 18087, 18093, 18124, 18178,
        18201, 18203, 18442, 18573, 18706, 18981, 18984, 19092, 19259, 19262, 19631, 20011, 20101, 20124, 20460, 20635,
        21086, 21146, 21147, 21761, 21917, 22731, 22784, 22997, 23164, 23171, 23284, 23351, 23851, 24126, 24127, 24147,
        24539, 24598, 25297, 25364, 25466, 25568, 25573, 25696, 25730, 25761, 25861, 26013, 26082, 26250, 26342, 26460,
        26597, 26675, 26839, 27370, 27466, 27493, 27751, 27818, 27853, 27917, 27985, 28121, 28313, 28341, 28762, 29093,
        29140, 29184, 29234, 29302, 29662, 29695, 29886, 29896, 30203, 30258, 30726, 30938, 31118, 31176, 31346, 31510,
        31630, 31642, 31657, 31839, 31887, 31940, 32090, 32316, 32500, 32794, 32846, 33119, 33249, 33305, 33377, 33558,
        33669, 33766, 33836, 33874, 33943, 34420, 34441, 34734, 34786, 34801, 34827, 34923, 35153, 35154, 35165, 35242,
        35327, 35438, 35743, 35891, 36088, 36235, 36248, 36294, 36535, 36651, 36669, 37068, 37072, 37300, 37341, 37355,
        37583, 38112, 38126, 38146, 38171, 38192, 38583, 38689, 38871, 38938, 39016, 39172, 39210, 39354, 39485, 39489,
        39696, 39702, 39713, 39830, 39838, 40061, 40262, 40410, 40633, 40729, 41003, 41085, 41179, 41471, 41636, 41696,
        41867, 41883, 41886, 42349, 42497, 42612, 42748, 42894, 43110, 43402, 43555, 43898, 44211, 44356, 44380, 44432,
        44649, 44731, 44840, 44903, 45474, 46180, 46212, 46275, 46470, 46953, 47225, 47505, 48050, 48326, 48647, 49154,
        49746, 50515, 50887, 51203, 51392, 51539, 52167, 52846, 53255, 53389, 53792, 53889, 53992, 54269, 54438, 54472,
        54577, 55048, 55157, 55180, 55599, 55865, 56075, 56081, 56255, 56844, 57016, 57280, 57445, 57810, 57946, 57981,
        57983, 58136, 58263, 58369, 58595, 58605, 59167, 59288, 59305, 59401, 59426, 59795, 59868, 60336, 60831, 61074,
        61288, 61332, 61961, 62164, 62617, 62805, 62983, 63190, 63329, 63384, 63479, 63988, 64643, 64704, 65189, 65247,
        65361, 65648, 65772, 66072, 66195, 66200, 66252, 66525, 66580, 66886, 66978, 67363, 67372, 67518, 67545, 67639,
        67665, 67826, 68009, 68055, 68370, 69356, 69518, 69792, 70278, 70319, 71190, 71542, 71761, 71904, 72326, 72550,
        72679, 72889, 73130, 73241, 74119, 74507, 74633, 74635, 74719, 74868, 74917, 75352, 75393, 75882, 75886, 75912,
        76928, 77024, 77104, 77300, 77440, 77480, 77989, 78187, 78594, 78599, 78652, 78971, 79185, 79333, 79387, 79534,
        79873, 79923, 79979, 80028, 80745, 80886, 80892, 80898, 81558, 83726, 83744, 83955, 84234, 84625, 85365, 85650,
        86184, 86348, 86668, 87046, 87471, 87609, 87727, 87827, 87856, 88518, 88712, 89054, 89161, 89228, 89761, 92168,
        92331, 92436, 92652, 93283, 93379, 93661, 94140, 94222, 94447, 94517, 94864, 94924, 95130, 95493, 97220, 97300,
        98055, 98420, 98684, 98902, 99139, 100097, 100310, 100322, 100432, 100759, 100801, 101446, 101510, 101849, 102312, 102883,
        103526, 103608, 103828, 103830, 104007, 104458, 104558, 104725, 106428, 106603, 107513, 107603, 107629, 107750, 108008, 108853,
        109652, 110007, 110909, 111344, 111480, 112463, 113371, 115544, 116343, 116534, 116605, 116978, 117104, 117326, 117617, 119392,
        119531, 119698, 120362, 121113, 122038, 122286, 122513, 122612, 122767, 123537, 123587, 124690, 125128, 125817, 126257, 126321,
        126619, 127218, 127633, 127865, 128470, 128498, 128729, 129384, 129456, 129472, 130597, 130632, 130933, 131098, 131148, 131155,
        131247, 131605
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: mixed-precision quantization or inference sense, passing mention, or cites the paper without naming mixed precision training'
FROM mpt_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING mpt_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING mpt_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- tensor-parallelism: 35 links, 9 exclusions.
CREATE TEMP TABLE tp_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'tensor-parallelism'
  AND p.id IN (
        2561, 5408, 5792, 7196, 8992, 10222, 14891, 15954, 22522, 22996, 25023, 26460, 26998, 35847, 36980, 37594,
        42748, 43660, 45415, 45539, 52470, 55865, 56612, 56798, 62983, 65095, 73426, 77222, 83310, 86294, 89335, 92869,
        101402, 122097, 125629
  );

DELETE FROM paper_method_exclusions x
USING tp_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM tp_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM tp_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE tp_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'tensor-parallelism'
  AND p.id IN (
        20910, 35978, 60159, 82916, 83108, 112213, 122321, 122323, 126620
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: passing mention of tensor parallelism, or another sense (parallel tensor computation)'
FROM tp_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING tp_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING tp_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- pipeline-parallelism: 73 links, 14 exclusions.
CREATE TEMP TABLE pp_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'pipeline-parallelism'
  AND p.id IN (
        1627, 2561, 3258, 5408, 5578, 5882, 7079, 7196, 10222, 11300, 14891, 19480, 19957, 23661, 23804, 24356,
        24493, 25023, 26013, 28381, 31244, 31684, 31906, 34759, 37338, 37594, 39177, 39786, 45133, 45318, 45691, 51502,
        52846, 53708, 54563, 56338, 57380, 57810, 61461, 62978, 62983, 72214, 73426, 74103, 74106, 74306, 75874, 77222,
        77333, 77843, 78599, 80881, 81993, 87513, 89243, 90161, 98207, 98980, 99312, 99920, 100093, 101279, 106449, 109388,
        114021, 122097, 125652, 126419, 127192, 127368, 128133, 128604, 130100
  );

DELETE FROM paper_method_exclusions x
USING pp_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM pp_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM pp_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE pp_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'pipeline-parallelism'
  AND p.id IN (
        5792, 20910, 35969, 43254, 54200, 62164, 63479, 83400, 92808, 98420, 102426, 102882, 104037, 128884
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: passing mention, or pipelining of system modules/agents rather than model pipeline parallelism'
FROM pp_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING pp_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING pp_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- ring-attention: 15 links, 256 exclusions (local S2 citers that do not name the method are excluded).
CREATE TEMP TABLE ring_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ring-attention'
  AND p.id IN (
        5792, 21310, 21430, 23407, 27247, 31244, 35644, 39577, 44033, 56282, 66075, 75340, 76885, 114021, 125574
  );

DELETE FROM paper_method_exclusions x
USING ring_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ring_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ring_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE ring_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ring-attention'
  AND p.id IN (
        21592, 24127, 24607, 24968, 25165, 25506, 26748, 26784, 27727, 28663, 29214, 29900, 30160, 30187, 30308, 30309,
        30902, 30952, 31034, 31150, 31176, 31201, 31373, 31399, 31407, 31509, 31599, 32147, 32319, 32601, 32636, 32905,
        33410, 33610, 33664, 33766, 33873, 33915, 34059, 34230, 34443, 34500, 34547, 34570, 34784, 34786, 34928, 35081,
        35411, 35847, 35978, 35979, 36453, 36666, 36778, 36944, 37051, 37338, 37431, 37752, 37790, 37938, 37947, 38126,
        38474, 38742, 38876, 39016, 39126, 39760, 40212, 40405, 40487, 40840, 40934, 41004, 41864, 42195, 42211, 42392,
        42970, 43044, 43074, 43220, 43233, 43437, 43519, 43850, 43911, 43954, 44035, 44203, 44701, 44807, 44991, 45001,
        45205, 45224, 45491, 45620, 45691, 45827, 45838, 45991, 46237, 46496, 46879, 46893, 47085, 47204, 47209, 47432,
        47488, 47984, 48192, 48693, 48866, 48881, 49228, 49400, 49452, 49747, 49920, 50112, 50444, 50579, 50609, 50634,
        50652, 51037, 51188, 51275, 51616, 51750, 51822, 51826, 52052, 52077, 52846, 53329, 53379, 53451, 53591, 53628,
        53708, 53800, 53816, 53850, 54317, 54384, 54392, 54653, 54758, 54862, 54954, 54984, 55756, 56024, 56337, 56623,
        57059, 57374, 57410, 58710, 59305, 59361, 59873, 60591, 61324, 61400, 62902, 63190, 63229, 63398, 63770, 64995,
        65214, 65536, 66952, 67309, 67627, 67738, 68465, 68967, 69221, 70714, 70981, 71223, 72023, 72133, 72581, 73426,
        74106, 74306, 74711, 75695, 75874, 77084, 77222, 77938, 83142, 83180, 83366, 83379, 83488, 83730, 83857, 84263,
        86126, 86835, 87008, 87943, 88879, 89805, 90281, 91313, 91541, 92712, 92787, 92808, 92900, 94410, 94623, 99534,
        99687, 100093, 101984, 102637, 102713, 103679, 104007, 104064, 104306, 104488, 104584, 108794, 109015, 109799, 110284, 117718,
        120721, 121997, 123560, 123599, 123606, 123751, 124067, 124255, 124517, 125744, 126344, 126952, 128522, 131624, 131757, 131820
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites Ring Attention without naming it in title/abstract, or another ring attention design'
FROM ring_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ring_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ring_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- learning-rate-warmup: 16 links, 56 exclusions.
CREATE TEMP TABLE warm_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'learning-rate-warmup'
  AND p.id IN (
        1318, 2402, 3092, 6855, 7340, 19024, 21829, 38980, 41796, 64089, 85863, 92338, 93047, 100029, 123678, 124533
  );

DELETE FROM paper_method_exclusions x
USING warm_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM warm_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM warm_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE warm_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'learning-rate-warmup'
  AND p.id IN (
        4991, 5337, 7884, 16599, 27242, 32453, 38595, 38738, 41333, 45099, 49087, 53601, 53948, 54935, 55997, 56081,
        56513, 57861, 58695, 59652, 60958, 64901, 65155, 65173, 66135, 67775, 68393, 68606, 69249, 72029, 72304, 72324,
        77515, 86234, 88381, 92548, 94674, 100201, 100723, 100988, 102799, 106714, 106927, 107703, 116423, 119383, 119778, 126786,
        127421, 127681, 129244, 129806, 130985, 131058, 131184, 131472
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: warm-up stage of another kind (SFT/RL warm-up, curriculum, module warm-up), not a learning rate warmup'
FROM warm_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING warm_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING warm_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- exponential-moving-average: 94 links, 115 exclusions.
CREATE TEMP TABLE ema_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'exponential-moving-average'
  AND p.id IN (
        3882, 5034, 11779, 12030, 12086, 12990, 15334, 17007, 17873, 18469, 18633, 18729, 19147, 22120, 22278, 23807,
        24292, 24701, 24970, 27242, 27316, 33597, 34036, 34281, 38483, 44620, 48085, 50519, 52771, 52822, 56719, 56903,
        57312, 57563, 59058, 59785, 62061, 65923, 67494, 68795, 69180, 70452, 72499, 78310, 82926, 85204, 85509, 88070,
        90304, 91193, 93110, 93951, 94838, 96223, 98361, 98562, 98656, 99970, 102655, 104513, 105052, 105690, 108337, 108632,
        108760, 108952, 109713, 111395, 111589, 112959, 114255, 115957, 116096, 116868, 119062, 122214, 122532, 122623, 123056, 124241,
        124797, 125177, 125560, 125829, 126796, 126938, 128391, 128620, 129086, 130225, 130722, 131603, 131876, 132007
  );

DELETE FROM paper_method_exclusions x
USING ema_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ema_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ema_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE ema_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'exponential-moving-average'
  AND p.id IN (
        1220, 2023, 2583, 2733, 3644, 4354, 12406, 13407, 14034, 22588, 26810, 28431, 28925, 28973, 30309, 33169,
        36598, 37545, 40581, 43018, 44271, 44808, 52282, 54541, 54566, 55253, 55559, 56461, 56710, 56837, 56995, 59283,
        59444, 60321, 60358, 60410, 60589, 60887, 61503, 63159, 63846, 66415, 66666, 67254, 68865, 71643, 76798, 77925,
        79734, 79814, 82871, 83464, 84504, 84927, 85081, 85279, 86839, 87391, 88457, 88891, 89228, 89714, 90167, 90946,
        94044, 94755, 94923, 96554, 97308, 97999, 98032, 98048, 98408, 98867, 99660, 102093, 102793, 103101, 103137, 103737,
        103787, 107819, 109303, 111189, 111191, 111305, 111745, 111747, 114087, 115900, 117703, 118456, 118552, 119280, 120767, 121103,
        121801, 123158, 123171, 124498, 124774, 124991, 125144, 125387, 125417, 125676, 126043, 126419, 126982, 127666, 127671, 127721,
        128296, 128925, 131190
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: EMA of gradients/statistics/signals (optimizers, routing, rewards) rather than of model weights, EMA abbreviates something else, or passing mention'
FROM ema_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ema_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ema_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- early-stopping: 49 links, 138 exclusions.
CREATE TEMP TABLE es_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'early-stopping'
  AND p.id IN (
        337, 1349, 1720, 2542, 2832, 8334, 11844, 12579, 13779, 14489, 18085, 21198, 21956, 26376, 29974, 34788,
        43589, 60060, 65677, 68852, 71844, 77850, 78297, 79464, 80410, 80856, 81448, 82234, 86090, 87218, 87638, 88718,
        88761, 88805, 89614, 92446, 93077, 93528, 94554, 94955, 99364, 101591, 101825, 101985, 103335, 126692, 127567, 127720,
        130303
  );

DELETE FROM paper_method_exclusions x
USING es_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM es_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM es_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE es_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'early-stopping'
  AND p.id IN (
        907, 1544, 3344, 6889, 8043, 9265, 9752, 10181, 10209, 11204, 12524, 13427, 13501, 18993, 20013, 21293,
        23309, 23776, 24411, 25678, 26031, 26154, 26602, 31621, 32322, 36193, 36954, 39661, 39767, 45232, 46954, 48511,
        49583, 49846, 50076, 50222, 50975, 52069, 53295, 53369, 53455, 53868, 55524, 55717, 56738, 57086, 57365, 57700,
        59046, 59912, 60024, 60253, 60888, 61400, 61684, 61958, 62138, 63392, 65913, 66292, 66597, 66729, 67384, 67941,
        68226, 68262, 68341, 69036, 69266, 69621, 72346, 75840, 76491, 83867, 86741, 86865, 87309, 87502, 88381, 88851,
        90711, 91412, 92547, 92572, 93970, 94007, 94102, 94284, 94486, 98069, 98081, 98914, 99109, 99495, 100161, 100398,
        100779, 101216, 101302, 101331, 101542, 101706, 101709, 101768, 102231, 102261, 102296, 106141, 106155, 106194, 106714, 107330,
        108849, 109213, 109263, 109699, 109742, 112802, 114980, 123830, 124437, 124695, 124759, 125038, 125106, 125525, 125633, 125962,
        126147, 126821, 127008, 128125, 129136, 130008, 130150, 130166, 130336, 131276
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: early stopping of inference, reasoning, search, sampling or agents rather than training, or passing mention'
FROM es_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING es_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING es_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- gelu: 31 links, 1254 exclusions (local S2 citers that do not name the method are excluded).
CREATE TEMP TABLE gelu_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gelu'
  AND p.id IN (
        420, 3096, 4761, 4859, 8652, 9682, 11031, 11584, 11609, 15819, 16553, 18565, 21525, 26642, 26782, 27715,
        31479, 32120, 32274, 33558, 34870, 38372, 38663, 43900, 47229, 68456, 72498, 72531, 87671, 100688, 125556
  );

DELETE FROM paper_method_exclusions x
USING gelu_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gelu_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM gelu_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE gelu_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gelu'
  AND p.id IN (
        2020, 2034, 2086, 2151, 2366, 2369, 2412, 2539, 2587, 2600, 2735, 2744, 2834, 2985, 3087, 3303,
        3328, 3388, 3449, 3598, 3773, 3797, 3849, 3991, 4199, 4214, 4244, 4377, 4495, 4637, 4646, 4706,
        4755, 4782, 4820, 4823, 4923, 4955, 5022, 5046, 5084, 5108, 5112, 5143, 5163, 5188, 5197, 5229,
        5259, 5269, 5272, 5306, 5395, 5396, 5428, 5454, 5458, 5562, 5563, 5638, 5667, 5732, 5741, 5742,
        5750, 5808, 5836, 5856, 5860, 5893, 5917, 5920, 5926, 5928, 5951, 5957, 6101, 6102, 6123, 6184,
        6256, 6275, 6303, 6310, 6317, 6333, 6395, 6401, 6517, 6532, 6689, 6738, 6745, 6748, 6754, 6788,
        6869, 6879, 6927, 6930, 7002, 7166, 7188, 7258, 7276, 7281, 7282, 7575, 7610, 7614, 7668, 7673,
        7758, 7912, 7922, 7976, 7979, 8004, 8011, 8017, 8018, 8023, 8169, 8215, 8229, 8257, 8311, 8326,
        8383, 8439, 8454, 8497, 8504, 8536, 8547, 8560, 8595, 8629, 8630, 8722, 8784, 8840, 8882, 8928,
        8975, 8986, 8989, 9012, 9137, 9206, 9210, 9219, 9246, 9363, 9413, 9449, 9536, 9550, 9564, 9634,
        9650, 9696, 9702, 9810, 9847, 9866, 10011, 10093, 10142, 10143, 10146, 10187, 10243, 10389, 10468, 10490,
        10494, 10505, 10536, 10550, 10578, 10599, 10699, 10735, 10825, 10836, 10881, 10893, 10939, 11049, 11079, 11098,
        11122, 11257, 11263, 11297, 11361, 11388, 11404, 11410, 11412, 11413, 11452, 11573, 11608, 11623, 11627, 11634,
        11642, 11644, 11671, 11687, 11723, 11843, 11869, 11904, 11975, 11985, 12004, 12027, 12070, 12084, 12095, 12148,
        12198, 12230, 12288, 12330, 12343, 12345, 12363, 12387, 12416, 12419, 12439, 12467, 12527, 12564, 12744, 12750,
        12839, 12980, 13000, 13068, 13218, 13261, 13263, 13307, 13349, 13368, 13534, 13555, 13626, 13697, 13740, 13782,
        13796, 13845, 13858, 13935, 14038, 14132, 14175, 14177, 14272, 14308, 14309, 14349, 14424, 14475, 14487, 14507,
        14533, 14711, 14722, 14779, 14881, 15012, 15027, 15147, 15150, 15199, 15212, 15261, 15344, 15467, 15470, 15529,
        15560, 15682, 15696, 15774, 15897, 15905, 15955, 15989, 16010, 16065, 16099, 16124, 16154, 16251, 16268, 16384,
        16520, 16559, 16574, 16584, 16618, 16633, 16774, 16800, 16843, 16859, 16871, 16880, 17058, 17189, 17243, 17283,
        17285, 17326, 17367, 17379, 17425, 17574, 17600, 17625, 17759, 17895, 17905, 17969, 17975, 17995, 18016, 18189,
        18201, 18280, 18325, 18356, 18472, 18506, 18642, 18677, 18760, 18775, 18781, 18852, 19132, 19156, 19204, 19222,
        19236, 19274, 19434, 19443, 19455, 19591, 19602, 19659, 19706, 19829, 19898, 19993, 20052, 20153, 20206, 20274,
        20308, 20326, 20343, 20353, 20422, 20474, 20485, 20606, 20683, 20741, 20846, 20895, 20914, 21145, 21317, 21321,
        21403, 21404, 21425, 21495, 21527, 21635, 21660, 21695, 21814, 21929, 22116, 22185, 22237, 22436, 22575, 22703,
        22787, 22814, 22860, 22893, 22903, 23219, 23356, 23467, 23685, 23806, 23927, 23954, 23969, 23983, 23984, 23993,
        24154, 24185, 24214, 24215, 24262, 24292, 24435, 24461, 24496, 24546, 24581, 24612, 24662, 24713, 24874, 24927,
        25005, 25296, 25401, 25456, 25554, 25568, 25581, 25591, 25599, 25630, 25687, 25703, 25738, 25866, 25931, 26082,
        26140, 26212, 26223, 26248, 26260, 26402, 26446, 26583, 26673, 26716, 26757, 26765, 26793, 26812, 26833, 26892,
        26898, 26994, 27046, 27204, 27206, 27214, 27250, 27398, 27481, 27703, 27971, 28073, 28089, 28187, 28201, 28208,
        28267, 28485, 28578, 28604, 28704, 28719, 28829, 28934, 29036, 29093, 29095, 29302, 29392, 29411, 29487, 29529,
        29614, 29645, 29653, 29708, 29726, 29782, 29939, 30078, 30079, 30166, 30418, 30458, 30616, 30781, 30823, 30948,
        30962, 31041, 31071, 31265, 31340, 31366, 31523, 31533, 31562, 31610, 31625, 31689, 31695, 31737, 31778, 31791,
        32077, 32118, 32144, 32245, 32295, 32305, 32371, 32587, 32611, 32642, 32764, 32799, 32906, 33222, 33279, 33309,
        33319, 33533, 33551, 33596, 33820, 33823, 34201, 34212, 34251, 34336, 34397, 34411, 34434, 34435, 34458, 34497,
        34578, 34676, 34709, 34741, 34744, 34783, 34841, 34934, 34935, 34998, 35004, 35038, 35067, 35112, 35206, 35225,
        35230, 35299, 35332, 35424, 35434, 35436, 35578, 35617, 35775, 35826, 35968, 36047, 36379, 36470, 36591, 36745,
        36925, 36951, 36998, 37135, 37154, 37191, 37573, 37620, 37696, 37711, 37773, 37784, 37805, 37974, 38106, 38144,
        38172, 38236, 38280, 38441, 38459, 38492, 38507, 38733, 38817, 39048, 39172, 39343, 39396, 39686, 39752, 40097,
        40151, 40336, 40357, 40500, 40507, 40626, 40678, 40801, 40853, 40855, 40862, 40875, 40936, 40971, 40996, 41098,
        41242, 41256, 41314, 41447, 41485, 41506, 41592, 41795, 41817, 41851, 42033, 42067, 42078, 42237, 42243, 42371,
        42724, 42986, 43077, 43112, 43136, 43162, 43490, 43522, 43706, 43726, 43877, 44371, 44780, 44938, 44992, 45110,
        45117, 45218, 45229, 45464, 45492, 45659, 46031, 46082, 46142, 46391, 47135, 47195, 47381, 47441, 47594, 47700,
        47721, 47818, 47859, 47874, 47937, 47988, 47990, 48236, 48599, 48647, 48710, 48856, 49090, 49299, 49456, 49487,
        49730, 50049, 50107, 50146, 50216, 50427, 50652, 50667, 50691, 50748, 50783, 50821, 50863, 50883, 50985, 51066,
        51240, 51313, 51328, 51351, 51371, 51476, 51506, 51539, 52057, 52120, 52255, 52392, 52400, 52569, 53255, 53263,
        53290, 53399, 53596, 54067, 54080, 54465, 54472, 54633, 54779, 54904, 55051, 55205, 55422, 55748, 55836, 56229,
        56366, 56448, 56509, 56536, 56737, 56792, 56848, 56849, 56868, 57016, 57119, 57250, 57314, 57438, 57547, 57619,
        57911, 58012, 58136, 58326, 58651, 58806, 58961, 59162, 59401, 59410, 59445, 59533, 59792, 60093, 60315, 60519,
        60742, 60823, 61013, 61657, 61798, 62279, 62707, 62805, 63208, 63297, 63500, 63592, 63771, 64063, 64102, 64184,
        64397, 64563, 64815, 65350, 65590, 65676, 65870, 65901, 66336, 66394, 66441, 66705, 66758, 66790, 67049, 67248,
        67684, 67717, 67908, 67958, 68070, 68302, 68313, 68536, 68715, 68766, 68933, 69251, 69524, 69590, 69755, 69948,
        70096, 70575, 70982, 70985, 71083, 71107, 71229, 71295, 71502, 71637, 71645, 71873, 72184, 72190, 72233, 72253,
        72599, 72613, 72795, 72983, 73037, 73074, 73288, 73569, 73652, 73745, 73814, 73881, 73892, 73981, 74007, 74140,
        74155, 74168, 74194, 74386, 74855, 74941, 75135, 75304, 75352, 75483, 75638, 75735, 75826, 75845, 75849, 75897,
        75919, 75974, 76032, 76097, 76113, 76144, 76148, 76350, 76402, 76451, 76487, 76680, 76823, 76901, 77104, 77111,
        77371, 77448, 77542, 77605, 77606, 77880, 78159, 78160, 78187, 78378, 78531, 78537, 78556, 78579, 78594, 78836,
        78940, 79073, 79112, 79439, 79569, 79593, 79644, 79869, 80006, 80064, 80124, 80166, 80262, 80379, 80476, 80554,
        81312, 81666, 82952, 83004, 83408, 83481, 83972, 84167, 84355, 84513, 84558, 84679, 84706, 84939, 84996, 85088,
        85110, 85139, 85369, 85431, 85747, 85770, 85857, 85901, 85952, 86093, 86131, 86408, 86457, 86518, 86543, 86652,
        86991, 87038, 87182, 87298, 87336, 87442, 87567, 87622, 87742, 87802, 87968, 88022, 88037, 88150, 88160, 88163,
        88262, 88292, 88363, 88390, 88397, 88436, 88509, 88528, 88713, 88724, 89099, 89113, 89122, 89132, 89174, 89390,
        89447, 89484, 89887, 89889, 90000, 90129, 90166, 90208, 90227, 90234, 90243, 90564, 90578, 90638, 90730, 90812,
        90827, 90836, 90876, 90904, 90973, 91035, 91040, 91053, 91093, 91138, 91143, 91236, 91483, 91645, 91842, 92003,
        92191, 92257, 92302, 92368, 92379, 92650, 92684, 92694, 92713, 92751, 92815, 92861, 93153, 93179, 93185, 93237,
        93247, 93293, 93385, 93431, 93458, 93486, 93498, 94117, 94138, 94364, 94449, 94524, 94529, 94586, 94664, 94796,
        94812, 95004, 95087, 95263, 95865, 96160, 96969, 98011, 98016, 98437, 98571, 98625, 98632, 99173, 99186, 99195,
        99232, 99414, 99477, 99543, 99605, 99811, 99974, 100005, 100155, 100176, 100197, 100554, 100734, 100767, 100769, 100843,
        100870, 100910, 100912, 100914, 101522, 101607, 101642, 101675, 101746, 101868, 101914, 102069, 102075, 102127, 102257, 102335,
        102539, 102569, 102604, 102632, 102697, 102882, 103644, 103888, 104085, 104260, 104341, 104360, 104413, 105058, 105671, 105728,
        105902, 105952, 105990, 106305, 106579, 106664, 106776, 106806, 106927, 107362, 107641, 107922, 108043, 108383, 108692, 108810,
        109202, 109228, 109399, 109501, 109903, 110873, 110996, 111047, 111075, 111239, 111539, 111894, 112028, 112150, 112722, 112752,
        113079, 113127, 113240, 113245, 113390, 113428, 113485, 113517, 113642, 113644, 113667, 113670, 114867, 115134, 115252, 115339,
        115385, 115598, 115613, 115677, 115811, 115859, 116019, 116043, 116102, 116179, 116211, 116268, 116284, 116355, 116481, 116483,
        116509, 116526, 116802, 116929, 117029, 117077, 117172, 117345, 117731, 118143, 118152, 118307, 118836, 119010, 119017, 119144,
        119145, 119257, 119281, 119809, 119948, 120107, 120150, 120178, 120474, 120678, 120747, 121602, 121981, 122469, 122705, 122941,
        123354, 123407, 123497, 123603, 123653, 123939, 124195, 124231, 124538, 124696, 125218, 125259, 125333, 125530, 125603, 125712,
        126219, 126258, 127410, 127812, 127938, 128252, 128267, 128689, 129391, 129603, 129626, 129705, 129709, 130072, 130140, 130376,
        130379, 130395, 130428, 130962, 131098, 131196
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: lists GELU among activations in passing, or cites the GELU paper without naming it in title/abstract'
FROM gelu_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING gelu_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING gelu_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- silu: 24 links, 25 exclusions.
CREATE TEMP TABLE silu_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'silu'
  AND p.id IN (
        918, 2445, 6754, 21525, 22109, 26782, 27715, 32120, 33558, 38828, 39607, 63136, 72531, 74767, 76823, 79644,
        82276, 83011, 94505, 95300, 98301, 100688, 113434, 126739
  );

DELETE FROM paper_method_exclusions x
USING silu_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM silu_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM silu_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE silu_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'silu'
  AND p.id IN (
        4761, 4923, 11836, 20767, 38694, 39686, 43726, 47990, 62707, 64569, 71645, 83481, 92713, 99630, 100554, 100683,
        100912, 101607, 105990, 124696, 125333, 126258, 127869, 130962, 131816
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: lists SiLU/Swish in passing, or a different function (Hard-Swish, SwiGLU variants, SwishRNN)'
FROM silu_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING silu_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING silu_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- group-normalization: 11 links, 465 exclusions (local S2 citers that do not name the method are excluded).
CREATE TEMP TABLE gn_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'group-normalization'
  AND p.id IN (
        1746, 3303, 6540, 28294, 61971, 81059, 120458, 124001, 124853, 124940, 125890
  );

DELETE FROM paper_method_exclusions x
USING gn_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gn_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM gn_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE gn_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'group-normalization'
  AND p.id IN (
        1568, 1579, 1659, 1665, 1722, 1742, 1779, 1851, 1902, 1912, 1948, 1992, 2029, 2091, 2098, 2166,
        2273, 2344, 2368, 2469, 2613, 2653, 2666, 2688, 2849, 2852, 2902, 2960, 3143, 3162, 3228, 3258,
        3285, 3351, 3598, 3709, 3717, 3764, 3836, 3925, 4238, 4408, 4415, 4541, 4636, 4785, 4905, 4906,
        4923, 4955, 4968, 5022, 5035, 5088, 5184, 5318, 5536, 5581, 5589, 5644, 5697, 5702, 5732, 5817,
        5942, 6012, 6035, 6164, 6193, 6237, 6266, 6353, 6373, 6489, 6631, 6749, 6795, 6809, 6995, 7012,
        7037, 7051, 7259, 7281, 7282, 7288, 7337, 7397, 7502, 7546, 7554, 7635, 7673, 7825, 8497, 8524,
        8617, 8644, 8695, 9012, 9072, 9076, 9508, 9628, 9668, 9810, 9817, 9821, 9855, 9918, 9959, 10026,
        10138, 10253, 10337, 10548, 10621, 10765, 10849, 10932, 11209, 11364, 11420, 11559, 11668, 11836, 11860, 11904,
        11909, 11988, 12027, 12236, 12283, 12485, 12606, 12616, 12825, 12952, 13001, 13068, 13221, 13293, 13534, 13636,
        13720, 14120, 14207, 14533, 14704, 14722, 14793, 14881, 15503, 15680, 15779, 15819, 16288, 16321, 16671, 16885,
        17041, 17221, 17336, 17356, 17365, 17406, 17519, 17546, 17686, 17864, 17887, 18250, 18319, 18325, 18345, 18633,
        18760, 19132, 19418, 19813, 19951, 20077, 20226, 20382, 20804, 21067, 21145, 21760, 21789, 21934, 22127, 22567,
        23666, 23843, 23983, 24017, 24060, 24233, 24352, 24443, 24678, 24929, 25854, 26246, 26517, 26536, 26812, 26867,
        26961, 27751, 27885, 28217, 28465, 28837, 28990, 29101, 29113, 29252, 30017, 30106, 30309, 30547, 30896, 31150,
        31201, 31265, 31340, 31419, 31455, 31588, 32295, 32458, 32487, 32523, 33287, 33554, 34102, 34397, 34784, 35040,
        35086, 35332, 35383, 35745, 35770, 36408, 36570, 36951, 37281, 37931, 38014, 38420, 38746, 39705, 40081, 40292,
        40415, 40516, 40606, 40875, 41687, 41826, 41997, 42815, 42986, 43368, 43726, 43860, 43887, 44770, 44854, 45188,
        46072, 48520, 48677, 49186, 50049, 50191, 50642, 50789, 51066, 51516, 51547, 51767, 52554, 53225, 53266, 54195,
        54717, 54771, 54790, 55145, 55253, 55748, 57353, 57358, 58203, 58320, 58577, 58802, 60632, 60912, 61230, 61339,
        61778, 61798, 63289, 63755, 65870, 67711, 70710, 71449, 71779, 72473, 72680, 73119, 73416, 76037, 76259, 77198,
        77616, 78415, 79170, 79190, 79219, 79275, 79385, 79488, 79559, 79644, 79846, 79892, 80203, 80330, 80558, 80639,
        80736, 80739, 80747, 80885, 80913, 81049, 81221, 81260, 81558, 82039, 82879, 82939, 83514, 83716, 85012, 86347,
        86643, 86925, 86970, 87216, 87336, 87357, 87567, 87624, 87630, 87705, 88012, 88371, 88711, 89122, 89160, 89174,
        89318, 89826, 89869, 90166, 90374, 90616, 90723, 90852, 91672, 91872, 92191, 92235, 92393, 92751, 94068, 94420,
        94442, 95378, 98212, 98350, 98645, 98979, 99791, 100435, 100578, 100912, 101355, 101594, 101659, 101904, 102076, 102446,
        103178, 103657, 103910, 104156, 104190, 104257, 104340, 104366, 106927, 107099, 107610, 108009, 108024, 108189, 109202, 109475,
        109886, 110420, 111384, 112451, 112881, 112972, 113127, 113423, 113483, 114255, 115067, 115252, 115368, 115593, 115768, 115779,
        115795, 115887, 116019, 116090, 116121, 116166, 116376, 116694, 116751, 116777, 116783, 116826, 116835, 117020, 117023, 117069,
        117884, 118159, 118331, 118452, 119809, 120474, 120476, 122775, 124231, 125216, 126822, 126939, 127388, 127862, 129021, 130673,
        132112
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: group-normalized advantages/rewards (GRPO), group norm regularizers, or cites the paper without naming GroupNorm'
FROM gn_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING gn_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING gn_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- instance-normalization: 44 links, 291 exclusions (local S2 citers that do not name the method are excluded).
CREATE TEMP TABLE inorm_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'instance-normalization'
  AND p.id IN (
        622, 716, 734, 1404, 1722, 1991, 2368, 2680, 3143, 3244, 4452, 4500, 5070, 5189, 11272, 11835,
        12056, 20767, 24786, 25974, 27066, 37609, 37641, 38694, 41386, 45779, 58203, 63722, 63783, 79200, 81175, 82365,
        84005, 85663, 93552, 95299, 104257, 112991, 113400, 119878, 120847, 121876, 123100, 124680
  );

DELETE FROM paper_method_exclusions x
USING inorm_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM inorm_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM inorm_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE inorm_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'instance-normalization'
  AND p.id IN (
        512, 517, 637, 640, 812, 888, 983, 998, 1034, 1072, 1425, 1516, 1659, 1675, 1779, 1902,
        1912, 2098, 2115, 2166, 2338, 2344, 2372, 2449, 2532, 2662, 2678, 2688, 2852, 2866, 2895, 2960,
        2988, 3228, 3303, 3333, 3534, 3598, 3673, 3684, 3717, 3858, 3904, 3927, 4021, 4037, 4055, 4602,
        4626, 4653, 4732, 4891, 4923, 4951, 5094, 5303, 5329, 5425, 5644, 5694, 5817, 5821, 6082, 6540,
        6844, 7259, 7323, 7332, 7445, 7578, 7633, 7643, 7673, 7690, 7894, 7896, 8292, 8384, 8542, 8549,
        8652, 8676, 8817, 9099, 9508, 9782, 9833, 9959, 10253, 10389, 10485, 10701, 10853, 10967, 11209, 11361,
        11443, 11466, 11559, 11613, 11642, 11969, 11975, 12277, 12283, 12345, 12546, 13298, 13372, 13485, 13534, 13896,
        14253, 14364, 14389, 14568, 14722, 14804, 14906, 15503, 15979, 16288, 16443, 16617, 16740, 17058, 17546, 18560,
        18716, 18720, 18760, 18882, 18941, 18998, 19322, 19359, 19418, 19511, 19813, 20008, 20623, 20665, 21067, 21123,
        21552, 21750, 21789, 21934, 21977, 22469, 22643, 22852, 22857, 23749, 24678, 24929, 25169, 25630, 25854, 26235,
        26634, 27964, 28990, 29074, 29101, 29876, 31210, 31419, 32623, 34397, 34962, 35040, 35424, 35739, 36408, 36634,
        37421, 37784, 39596, 40081, 40273, 40971, 42724, 43726, 46072, 48225, 49511, 50726, 51050, 51240, 51751, 54484,
        54717, 54772, 55747, 55748, 57696, 59211, 59238, 61778, 65348, 67610, 67690, 75845, 76039, 76350, 76728, 76932,
        78173, 78281, 78957, 79488, 79529, 79644, 79820, 80330, 80341, 80516, 80542, 80558, 80775, 81001, 81059, 81112,
        81179, 81402, 81450, 81558, 81737, 81822, 81825, 81865, 82056, 82144, 86579, 86925, 87201, 87346, 87393, 88711,
        89318, 89383, 89826, 90171, 90693, 90789, 91625, 91672, 91871, 92058, 94076, 94334, 94614, 94753, 101812, 101865,
        101939, 104339, 104340, 105194, 106844, 107820, 108181, 108515, 109204, 109212, 109890, 111330, 111403, 111729, 111936, 113142,
        113469, 113952, 114965, 115823, 116694, 116970, 117454, 117657, 117722, 120176, 120231, 120278, 123927, 124001, 127470, 130064,
        130411, 131406, 131451
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: passing mention of instance normalization, or cites the paper without naming it in title/abstract'
FROM inorm_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING inorm_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING inorm_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- Method image credits (figures imported with import_entity_image.py).
-- exponential-moving-average, learning-rate-warmup and early-stopping have no
-- image: no suitable openly licensed figure was found.
UPDATE methods SET image_credit = '[ZeRO: Memory Optimizations Toward Training Trillion Parameter Models](/paper/1910.02054)' WHERE slug = 'zero';
UPDATE methods SET image_credit = '[Mixed Precision Training](/paper/1710.03740)' WHERE slug = 'mixed-precision-training';
UPDATE methods SET image_credit = '[Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parallelism](/paper/1909.08053)' WHERE slug = 'tensor-parallelism';
UPDATE methods SET image_credit = '[GPipe: Efficient Training of Giant Neural Networks using Pipeline Parallelism](/paper/1811.06965)' WHERE slug = 'pipeline-parallelism';
UPDATE methods SET image_credit = '[Ring Attention with Blockwise Transformers for Near-Infinite Context](/paper/2310.01889)' WHERE slug = 'ring-attention';
UPDATE methods SET image_credit = '[Gaussian Error Linear Units (GELUs)](/paper/1606.08415)' WHERE slug = 'gelu';
UPDATE methods SET image_credit = '[Searching for Activation Functions](/paper/1710.05941)' WHERE slug = 'silu';
UPDATE methods SET image_credit = '[Group Normalization](/paper/1803.08494)' WHERE slug = 'group-normalization';
UPDATE methods SET image_credit = '[Group Normalization](/paper/1803.08494)' WHERE slug = 'instance-normalization';

-- Source evidence protects each Introduced link from automated removal.
INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug IN ('zero', 'mixed-precision-training', 'ring-attention', 'gelu', 'group-normalization', 'instance-normalization')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
