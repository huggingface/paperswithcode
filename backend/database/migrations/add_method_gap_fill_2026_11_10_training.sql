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
    'zero',
    'ZeRO',
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
    'gelu',
    'GELU',
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
    'silu',
    'SiLU',
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
    image_url = EXCLUDED.image_url,
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
        2632, -- 1910.02054 ZeRO: Memory Optimizations Toward Training Trillion Parameter Models
        4908, -- 2101.06840 ZeRO-Offload: Democratizing Billion-Scale Model Training
        5476, -- 2104.07857 ZeRO-Infinity: Breaking the GPU Memory Wall for Extreme Scale Deep Learning
        5882, -- 2106.02679 Layered gradient accumulation and modular pipeline parallelism: fast and efficie
        6409, -- 2108.05818 PatrickStar: Parallel Training of Pre-trained Models via Chunk-based Memory Mana
        7074, -- 2110.14883 Colossal-AI: A Unified Deep Learning System For Large-Scale Parallel Training
        11300, -- 2211.05953 Breadth-First Pipeline Parallelism
        12851, -- 2302.02390 Quantized Distributed Training of Large Models with Convergence Guarantees
        14882, -- 2304.11277 PyTorch FSDP: Experiences on Scaling Fully Sharded Data Parallel
        17563, -- 2306.10209 ZeRO++: Extremely Efficient Collective Communication for Giant Model Training
        22838, -- 2311.00257 AMSP: Reducing Communication Overhead of ZeRO for Efficient LLM Training
        23013, -- 2311.03687 Dissecting the Runtime Performance of the Training, Fine-tuning, and Inference o
        26421, -- 2401.16265 CO2: Efficient Distributed Training with Full Communication-Computation Overlap
        32794, -- 2406.08334 ProTrain: Efficient LLM Training via Memory-Aware Techniques
        39489, -- 2411.00284 SimpleFSDP: Simpler Fully Sharded Data Parallel with torch.compile
        42497, -- 2501.02625 HALO: Hadamard-Assisted Lower-Precision Optimization for LLMs
        42603, -- 2501.04266 Scaling Large Language Model Training on Frontier with Low-Bandwidth Partitionin
        47380, -- 2504.05295 Dion: Distributed Orthonormalized Updates
        47403, -- 2504.05638 TAGC: Optimizing Gradient Communication in Distributed Transformer Training
        51037, -- 2506.10911 NoLoCo: No-all-reduce Low Communication Training Method for Large Models
        53342, -- 2510.05491 NorMuon: Making Muon more efficient and scalable
        55539, -- 2601.19362 Revisiting Parameter Server in LLM Post-Training
        55778, -- 2602.04816 Horizon-LM: A RAM-Centric Architecture for LLM Training
        56345, -- 2602.22437 veScale-FSDP: Flexible and High-Performance FSDP at Scale
        57280, -- 2604.05091 MegaTrain: Full Precision Training of 100B+ Parameter Large Language Models on a
        61119, -- 2602.06499 FCDP: Fully Cached Data Parallel for Communication-Avoiding Large-Scale Training
        62983, -- 2601.02311 Placement Semantics for Distributed Deep Learning: A Systematic Framework for An
        67229, -- 2510.00606 ElasWave: An Elastic-Native System for Scalable Hybrid-Parallel Training
        72550, -- 2505.23254 MemAscend: System Memory Optimization for SSD-Offloaded LLM Fine-Tuning
        73267, -- 2504.20437 GaLore 2: Large-Scale LLM Pre-Training by Gradient Low-Rank Projection
        74103, -- 2504.03662 Galvatron: Automatic Distributed Training for Large Transformer Models
        75627, -- 2412.01152 INTELLECT-1 Technical Report
        76885, -- 2406.18485 LoongTrain: Efficient Training of Long-Sequence LLMs with Head-Context   Paralle
        77843, -- 2402.03791 Adaptive Blockwise Task-interleaved Pipeline Parallelism
        86348, -- 2506.06472 Cost-Efficient LLM Training with Lifetime-Aware Tensor Offloading via GPUDirect
        92869, -- 2510.16981 MuonBP: Faster Muon via Block-Periodic Orthogonalization
        99721, -- 2605.00539 AGoQ: Activation and Gradient Quantization for Memory-Efficient Distributed Trai
        106449, -- 2511.09741 TawPipe: Topology-Aware Weight Pipeline Parallelism for Accelerating Long-Contex
        121997, -- 2609.14306 Flattening Every Memory Peak in Long-Context Mixture-of-Experts Training
        122513, -- 2609.34162 SlideDP: Scaling Host-Resident LLM Fine-Tuning Across Multiple GPUs
        125652  -- external PipeFSDP: Efficient Pipeline Parallel under Fully Sharded Data Parallel for Larg
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
        4342, -- 2010.06192 Revisiting BFloat16 Training
        4948, -- 2101.11075 Adaptivity without Compromise: A Momentumized, Adaptive, Dual Averaged Gradient
        5485, -- 2104.08200 IndoNLG: Benchmark and Resources for Evaluating Indonesian Natural Language Gene
        7450, -- 2112.04482 FLAVA: A Foundational Language And Vision Alignment Model
        8472, -- 2203.15556 Training Compute-Optimal Large Language Models
        8992, -- 2205.05198 Reducing Activation Recomputation in Large Transformer Models
        11282, -- 2211.05102 Efficiently Scaling Transformer Inference
        11667, -- 2211.15613 Frustratingly Easy Label Projection for Cross-lingual Transfer
        11850, -- 2212.03760 Pivotal Role of Language Modeling in Recommender Systems: Enriching Task-specifi
        13935, -- 2303.11331 EVA-02: A Visual Representation for Neon Genesis
        14309, -- 2303.17568 CodeGeeX: A Pre-Trained Model for Code Generation with Multilingual Benchmarking
        14349, -- 2303.18223 A Survey of Large Language Models
        14891, -- 2304.11414 Pipeline MoE: A Flexible MoE Implementation with Pipeline Parallelism
        15877, -- 2305.12720 llm-japanese-dataset v0: Construction of Japanese Chat Dataset for Large Languag
        16240, -- 2305.15348 READ: Recurrent Adaptation of Large Transformers
        16540, -- 2305.18513 SlimFit: Memory-Efficient Fine-Tuning of Transformer-based Models Using Training
        16618, -- 2305.19268 Intriguing Properties of Quantization at Scale
        17530, -- 2306.09782 Full Parameter Fine-tuning for Large Language Models with Limited Resources
        17650, -- 2306.11987 Training Transformers with 4-bit Integers
        17744, -- 2306.14096 Chinese Fine-Grained Financial Sentiment Analysis with Large Language Models
        18201, -- 2307.06435 A Comprehensive Overview of Large Language Models
        18491, -- 2307.11224 Jina Embeddings: A Novel Set of High-Performance Sentence Embedding Models
        18988, -- 2308.03303 LoRA-FA: Memory-efficient Low-rank Adaptation for Large Language Models Fine-tun
        19454, -- 2308.09895 Knowledge Transfer from High-Resource to Low-Resource Programming Languages for
        20012, -- 2309.00378 Long-Term Ad Memorability: Understanding & Generating Memorable Ads
        20193, -- 2309.03852 FLM-101B: An Open LLM and How to Train It with $100K Budget
        20598, -- 2309.10305 Baichuan 2: Open Large-scale Language Models
        20626, -- 2309.10706 OpenBA: An Open-sourced 15B Bilingual Asymmetric seq2seq Model Pre-trained from
        21310, -- 2310.01889 Ring Attention with Blockwise Transformers for Near-Infinite Context
        21471, -- 2310.03731 MathCoder: Seamless Code Integration in LLMs for Enhanced Mathematical Reasoning
        21525, -- 2310.04564 ReLU Strikes Back: Exploiting Activation Sparsity in Large Language Models
        21561, -- 2310.04963 LLM4VV: Developing LLM-Driven Testsuite for Compiler Validation
        21635, -- 2310.05694 A Survey of Large Language Models for Healthcare: from Data, Technology, and App
        21695, -- 2310.06266 CodeFuse-13B: A Pretrained Multi-lingual Code Large Language Model
        21733, -- 2310.06773 Uni3D: Exploring Unified 3D Representation at Scale
        21761, -- 2310.07147 QFT: Quantized Full-parameter Tuning of LLMs with Affordable Resources
        22029, -- 2310.10195 AdaLomo: Low-memory Optimization with Adaptive Learning Rate
        22046, -- 2310.10505 ReMax: A Simple, Effective, and Efficient Reinforcement Learning Method for Alig
        22060, -- 2310.10631 Llemma: An Open Language Model For Mathematics
        22130, -- 2310.11511 Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection
        23164, -- 2311.06025 ChiMed-GPT: A Chinese Medical Large Language Model with Full Training Regime and
        23343, -- 2311.08711 PLUG: Leveraging Pivot Language in Cross-Lingual Instruction Tuning
        24041, -- 2311.18702 CritiqueLLM: Towards an Informative Critique Generation Model for Evaluation of
        24356, -- 2312.03549 Holmes: Towards Distributed Training Across Clusters with Heterogeneous NIC Envi
        24493, -- 2312.04916 EE-LLM: Large-Scale Training and Inference of Early-Exit Large Language Models w
        24612, -- 2312.06647 4M: Massively Multimodal Masked Modeling
        24631, -- 2312.06720 Audio-Visual LLM for Video Understanding
        24640, -- 2312.06742 Honeybee: Locality-enhanced Projector for Multimodal LLM
        24995, -- 2312.12391 vTrain: A Simulation Framework for Evaluating Cost-effective and Compute-optimal
        25002, -- 2312.12450 Can It Edit? Evaluating the Ability of Large Language Models to Follow Code Edit
        25023, -- 2312.12705 Optimizing Distributed Training on Frontier for Large Language Models
        25263, -- 2312.16903 Spike No More: Stabilizing the Pre-training of Large Language Models
        25270, -- 2312.17055 Improving In-context Learning via Bidirectional Alignment
        25364, -- 2401.00625 Beyond Efficiency: A Systematic Survey of Resource-Efficient Large Language Mode
        25414, -- 2401.01335 Self-Play Fine-Tuning Converts Weak Language Models to Strong Language Models
        25466, -- 2401.02038 Understanding LLMs: A Comprehensive Overview from Training to Inference
        25711, -- 2401.06066 DeepSeekMoE: Towards Ultimate Expert Specialization in Mixture-of-Experts Langua
        25836, -- 2401.07950 SciInstruct: a Self-Reflective Instruction Annotated Dataset for Training Scient
        25913, -- 2401.08967 ReFT: Reasoning with Reinforced Fine-Tuning
        26042, -- 2401.10652 AutoChunk: Automated Activation Chunk for Memory-Efficient Long Sequence Inferen
        26337, -- 2401.14818 ChemDFM: A Large Language Foundation Model for Chemistry
        26354, -- 2401.15207 HiFT: A Hierarchical Full Parameter Fine-Tuning Strategy
        26358, -- 2401.15269 Improving Medical Reasoning through Retrieval and Self-Reflection with Retrieval
        26429, -- 2401.16349 ConFit: Improving Resume-Job Matching using Data Augmentation and Contrastive Le
        26455, -- 2401.16640 TeenyTinyLlama: open-source tiny language models trained in Brazilian Portuguese
        26597, -- 2402.00838 OLMo: Accelerating the Science of Language Models
        26643, -- 2402.01176 CorpusLM: Towards a Unified Language Model on Corpus for Knowledge-Intensive Tas
        26675, -- 2402.01613 Nomic Embed: Training a Reproducible Long Context Text Embedder
        26776, -- 2402.02544 LHRS-Bot: Empowering Remote Sensing with VGI-Enhanced Large Multimodal Language
        27080, -- 2402.05935 SPHINX-X: Scaling Data and Parameters for a Family of Multi-modal Large Language
        27111, -- 2402.06196 Large Language Models: A Survey
        27193, -- 2402.07625 Autonomous Data Selection with Zero-shot Generative Classifiers for Mathematical
        27478, -- 2402.11215 AdAdaGrad: Adaptive Batch Size Schemes for Adaptive Gradient Methods
        27507, -- 2402.11485 LEIA: Facilitating Cross-lingual Knowledge Transfer in Language Models with Enti
        27603, -- 2402.12343 Emulated Disalignment: Safety Alignment for Large Language Models May Backfire!
        27696, -- 2402.13253 BiMediX: Bilingual Medical Mixture of Experts LLM
        27725, -- 2402.13583 LongWanjuan: Towards Systematic Measurement for Long Text Quality
        27965, -- 2402.16347 CodeS: Towards Building Open-source Language Models for Text-to-SQL
        28114, -- 2402.18039 ResLoRA: Identity Residual Mapping in Low-Rank Adaption
        28341, -- 2403.01774 WebCiteS: Attributed Query-Focused Summarization on Chinese Web Search Results w
        28423, -- 2403.02969 Multi-modal Instruction Tuned LLMs with Fine-grained Visual Perception
        28461, -- 2403.03507 GaLore: Memory-Efficient LLM Training by Gradient Low-Rank Projection
        28506, -- 2403.04317 Online Adaptation of Language Models with a Memory of Amortized Contexts
        28510, -- 2403.04454 Low-Resource Court Judgment Summarization for Common Law Systems
        28801, -- 2403.08763 Simple and Scalable Strategies to Continually Pre-train Large Language Models
        28988, -- 2403.11207 MindEye2: Shared-Subject Models Enable fMRI-To-Image With 1 Hour of Data
        29124, -- 2403.12844 MELTing point: Mobile Evaluation of Language Transformers
        29234, -- 2403.14123 AI and Memory Wall
        29474, -- 2403.17688 Large Language Models Enhanced Collaborative Filtering
        29496, -- 2403.17889 Large scale paired antibody language models
        29501, -- 2403.17919 LISA: Layerwise Importance Sampling for Memory-Efficient Large Language Model Fi
        29900, -- 2404.02882 Linear Attention Sequence Parallelism
        29982, -- 2404.03887 SAAS: Solving Ability Amplification Strategy for Enhanced Mathematical Reasoning
        30052, -- 2404.05019 Shortcut-connected Expert Parallelism for Accelerating Mixture-of-Experts
        30123, -- 2404.06138 Cendol: Open Instruction-tuned Generative Large Language Models for Indonesian L
        30477, -- 2404.11581 E2ETune: End-to-End Knob Tuning via Fine-tuned Generative Language Model
        30704, -- 2404.15228 Re-Thinking Inverse Graphics With Large Language Models
        31121, -- 2405.04434 DeepSeek-V2: A Strong, Economical, and Efficient Mixture-of-Experts Language Mod
        31128, -- 2405.04620 Folded Context Condensation in Path Integral Formalism for Infinite Context Tran
        31181, -- 2405.06067 HMT: Hierarchical Memory Transformer for Long Context Language Processing
        31213, -- 2405.06932 Piccolo2: General Text Embedding with Multi-task Hybrid Loss Training
        31244, -- 2405.07719 USP: A Unified Sequence Parallelism Approach for Long Context Generative AI
        31297, -- 2405.08748 Hunyuan-DiT: A Powerful Multi-Resolution Diffusion Transformer with Fine-Grained
        31331, -- 2405.09673 LoRA Learns Less and Forgets Less
        31399, -- 2405.11143 OpenRLHF: An Easy-to-use, Scalable and High-performance RLHF Framework
        31468, -- 2405.12701 OLAPH: Improving Factuality in Biomedical Long-form Question Answering
        31486, -- 2405.13001 Large Language Models for Education: A Survey
        31558, -- 2405.14129 AlignGPT: Multi-modal Large Language Models with Adaptive Alignment Capability
        31629, -- 2405.14852 PV-Tuning: Beyond Straight-Through Estimation for Extreme LLM Compression
        31693, -- 2405.15525 Sparse Matrix in Large Language Model Fine-tuning
        31752, -- 2405.16287 LoGAH: Predicting 774-Million-Parameter Transformers using Graph HyperNetworks w
        31775, -- 2405.16552 SED: Self-Evaluation Decoding Enhances Large Language Models for Better Generati
        31779, -- 2405.16579 Automatically Generating Numerous Context-Driven SFT Data for LLMs across Divers
        31820, -- 2405.17057 ReflectionCoder: Learning from Reflection Sequence for Enhanced One-off Code Gen
        31825, -- 2405.17103 Empowering Character-level Text Infilling by Eliminating Sub-Tokens
        31906, -- 2405.18047 2BP: 2-Stage Backpropagation
        31911, -- 2405.18093 Pipette: Automatic Fine-grained Large Language Model Training Configurator for R
        31912, -- 2405.18111 ATM: Adversarial Tuning Multi-agent System Makes a Robust Retrieval-Augmented Ge
        32082, -- 2405.20279 CV-VAE: A Compatible Video VAE for Latent Generative Video Models
        32088, -- 2405.20314 S3D: A Simple and Cost-Effective Self-Speculative Decoding Scheme for Low-Memory
        32129, -- 2405.20853 MeshXL: Neural Coordinate Field for Generative 3D Foundation Models
        32329, -- 2406.02657 Block Transformer: Global-to-Local Language Modeling for Fast Inference
        32355, -- 2406.03008 DriVLMe: Enhancing LLM-based Autonomous Driving Agents with Embodied and Social
        32393, -- 2406.03686 BindGPT: A Scalable Framework for 3D Molecular Design via Language Modeling and
        32486, -- 2406.04594 Enhancing Large-Scale AI Training Efficiency: The C4 Solution for Real-Time Anom
        32631, -- 2406.06424 Margin-aware Preference Optimization for Aligning Diffusion Models without Refer
        32634, -- 2406.06469 Husky: A Unified, Open-Source Language Agent for Multi-Step Reasoning
        32646, -- 2406.06563 Skywork-MoE: A Deep Dive into Training Techniques for Mixture-of-Experts Languag
        32688, -- 2406.07168 Teaching Language Models to Self-Improve by Learning from Language Feedback
        32696, -- 2406.07249 Are Protein Language Models Compute Optimal?
        32822, -- 2406.08607 Reversing the Forget-Retain Objectives: An Efficient LLM Unlearning Framework fr
        33008, -- 2406.10707 DataStates-LLM: Lazy Asynchronous Checkpointing for Large Language Models
        33087, -- 2406.11256 Dynamic Data Mixing Maximizes Instruction Tuning for Mixture-of-Experts
        33096, -- 2406.11357 Refiner: Restructure Retrieval Content Efficiently to Advance Question-Answering
        33200, -- 2406.12050 Learn Beyond The Answer: Training Language Models with Reflection for Mathematic
        33359, -- 2406.13893 Open Generative Large Language Models for Galician
        33374, -- 2406.14088 ReaL: Efficient RLHF Training of Large Language Models with Parameter Reallocati
        33558, -- 2406.16282 Reducing Fine-Tuning Memory Overhead by Approximate and Memory-Sharing Backpropa
        33601, -- 2406.16793 Adam-mini: Use Fewer Learning Rates To Gain More
        33610, -- 2406.16852 Long Context Transfer from Language to Vision
        33670, -- 2406.17660 Grass: Compute Efficient Low-Memory LLM Training with Structured Sparse Gradient
        33749, -- 2406.18533 On Scaling Up 3D Gaussian Splatting Training
        33765, -- 2406.18790 MUMU: Bootstrapping Multimodal Image Generation from Text-to-Image Data
        34062, -- 2407.02552 RLHF Can Speak Many Languages: Unlocking Multilingual Preference Optimization fo
        34158, -- 2407.03963 LLM-jp: A Cross-organizational Project for the Research and Development of Fully
        34276, -- 2407.05563 LLMBox: A Comprehensive Library for Large Language Models
        34336, -- 2407.06204 A Survey on Mixture of Experts
        34392, -- 2407.07080 Adapting LLMs to Hebrew: Unveiling DictaLM 2.0 with Enhanced Vocabulary and Inst
        34420, -- 2407.07523 SHERL: Synthesizing High Accuracy and Efficient Memory for Resource-Limited Tran
        34443, -- 2407.07860 Controlling Space and Time with Diffusion Models
        34509, -- 2407.08699 Mitigating Catastrophic Forgetting in Language Transfer via Model Merging
        34671, -- 2407.10855 Weighted Grouped Query Attention in Transformers
        34697, -- 2407.11007 Panacea: A foundation model for clinical trial search, summarization, design, an
        34801, -- 2407.12327 Spectra: Surprising Effectiveness of Pretraining Ternary Language Models at Scal
        34869, -- 2407.12943 Halu-J: Critique-Based Hallucination Judge
        34923, -- 2407.13690 DART-Math: Difficulty-Aware Rejection Tuning for Mathematical Problem-Solving
        35105, -- 2407.16382 TookaBERT: A Step Forward for Persian NLU
        35153, -- 2407.17331 Multi-label Cluster Discrimination for Visual Representation Learning
        35165, -- 2407.17465 u-$μ$P: The Unit-Scaled Maximal Update Parametrization
        35280, -- 2407.19669 mGTE: Generalized Long-Context Text Representation and Reranking Models for Mult
        35305, -- 2407.20143 ByteCheckpoint: A Unified Checkpointing System for Large Foundation Model Develo
        35338, -- 2407.20743 Meltemi: The first open Large Language Model for Greek
        35455, -- 2408.00761 Tamper-Resistant Safeguards for Open-Weight LLMs
        35521, -- 2408.02006 LLaSA: Large Language and E-Commerce Shopping Assistant
        35535, -- 2408.02239 BOTS-LM: Training Large Language Models for Setswana
        35756, -- 2408.06273 FuxiTranyu: A Multilingual Large Language Model Trained with Balanced Data
        35823, -- 2408.07246 ChemVLM: Exploring the Power of Multimodal Large Language Models in Chemistry Ar
        35969, -- 2408.10013 SSDTrain: An Activation Offloading Framework to SSDs for Faster Large Language M
        35978, -- 2408.10188 LongVILA: Scaling Long-Context Visual Language Models for Long Videos
        36008, -- 2408.10681 HMoE: Heterogeneous Mixture of Experts for Language Modeling
        36170, -- 2408.12902 IAA: Inner-Adaptor Architecture Empowers Frozen Large Language Model with Multim
        36172, -- 2408.12928 ParGo: Bridging Vision-Language with Partial and Global Views
        36229, -- 2408.14158 Fire-Flyer AI-HPC: A Cost-Effective Software-Hardware Co-Design for Deep Learnin
        36271, -- 2408.14874 Inverse-Q*: Token Level Reinforcement Learning for Aligning Large Language Model
        36316, -- 2408.15710 Conan-embedding: General Text Embedding with More and Better Negative Samples
        36323, -- 2408.15793 Language Adaptation on a Tight Academic Compute Budget: Tokenizer Swapping Works
        36535, -- 2409.01990 Designing Large Foundation Models for Efficient Training and Inference: A Survey
        36554, -- 2409.02231 SmileyLlama: Modifying Large Language Models for Directed Chemical Space Explora
        36645, -- 2409.04183 GALLa: Graph Aligned Large Language Models for Improved Source Code Understandin
        36651, -- 2409.04267 An overview of domain-specific foundation model: key technologies, applications
        36662, -- 2409.04585 CubicML: Automated ML for Large ML Systems Co-design with ML Prediction of Perfo
        36669, -- 2409.04833 Achieving Peak Performance for Large Language Models: A Systematic Review
        36680, -- 2409.05152 OneGen: Efficient One-Pass Unified Generation and Retrieval for LLMs
        36745, -- 2409.06679 E2LLM: Encoder Elongated Large Language Models for Long-Context Understanding an
        36782, -- 2409.07447 StereoCrafter: Diffusion-based Generation of Long and High-fidelity Stereoscopic
        36786, -- 2409.07486 MarS: a Financial Market Simulation Engine Powered by Generative Foundation Mode
        36834, -- 2409.08523 Eir: Thai Medical Large Language Models
        37088, -- 2409.12903 Scaling Smart: Accelerating Large Language Model Pre-training with Small Model I
        37109, -- 2409.13198 Exploring Scaling Laws for Local SGD in Large Language Model Training
        37188, -- 2409.14674 RACER: Rich Language-Guided Failure Recovery Policies for Imitation Learning
        37220, -- 2409.15241 Domino: Eliminating Communication in LLM Training via Generic Tensor Slicing and
        37385, -- 2409.18003 Enhancing Tourism Recommender Systems for Sustainable City Trips Using Retrieval
        37463, -- 2409.19256 HybridFlow: A Flexible and Efficient RLHF Framework
        37655, -- 2410.01490 Extending Context Window of Large Language Models from a Distributional Perspect
        37824, -- 2410.02907 NNetscape Navigator: Complex Demonstrations for Web Agents Without a Demonstrato
        37869, -- 2410.03439 ToolGen: Unified Tool Retrieval and Calling via Generation
        37898, -- 2410.03742 Beyond Scalar Reward Model: Learning Generative Judge from Preference Data
        38017, -- 2410.05261 TextHawk2: A Large Vision-Language Model Excels in Bilingual OCR and Grounding w
        38087, -- 2410.05993 Aria: An Open Multimodal Native Mixture-of-Experts Model
        38126, -- 2410.06511 TorchTitan: One-stop PyTorch native solution for production ready LLM pre-traini
        38162, -- 2410.07002 CursorCore: Assist Programming through Aligning Anything
        38169, -- 2410.07064 Data Selection via Optimal Control for Language Models
        38192, -- 2410.07170 Parameter Efficient Fine-tuning via Explained Variance Adaptation
        38234, -- 2410.07830 NusaMT-7B: Machine Translation for Low-Resource Indonesian Languages with Large
        38239, -- 2410.07919 InstructBioMol: Advancing Biomolecule Understanding and Design Following Human I
        38309, -- 2410.08791 Superpipeline: A Universal Approach for Reducing GPU Memory Usage in Large Model
        38820, -- 2410.14655 Bridging the Training-Inference Gap in LLMs by Leveraging Self-Generated Tokens
        38915, -- 2410.16029 Natural GaLore: Accelerating GaLore for memory-efficient LLM Training and Fine-t
        38936, -- 2410.16235 ToW: Thoughts of Words Improve Reasoning in Large Language Models
        38944, -- 2410.16261 Mini-InternVL: A Flexible-Transfer Pocket Multimodal Model with 5% Parameters an
        39008, -- 2410.17215 MiniPLM: Knowledge Distillation for Pre-Training Language Models
        39054, -- 2410.17891 Scaling Diffusion Language Models via Adaptation from Autoregressive Models
        39058, -- 2410.17954 ExpertFlow: Optimized Expert Activation and Token Allocation for Efficient Mixtu
        39060, -- 2410.18027 Cross-lingual Transfer of Reward Models in Multilingual Alignment
        39085, -- 2410.18252 Asynchronous RLHF: Faster and More Efficient Off-Policy RL for Language Models
        39210, -- 2410.20011 A Survey of Small Language Models
        39246, -- 2410.20650 NeuZip: Memory-Efficient Training and Inference with Dynamic Compression of Neur
        39248, -- 2410.20672 Relaxed Recursive Transformers: Effective Parameter Sharing with Layer-wise LoRA
        39257, -- 2410.20777 KD-LoRA: A Hybrid Approach to Efficient Fine-Tuning with LoRA and Knowledge Dist
        39296, -- 2410.21316 Deep Optimizer States: Towards Scalable Training of Transformer Models Using Int
        39446, -- 2410.23933 Language Models can Self-Lengthen to Generate Long Texts
        39464, -- 2410.24198 SelfCodeAlign: Self-Alignment for Code Generation
        39533, -- 2411.00816 CycleResearcher: Improving Automated Research via Automated Review
        39569, -- 2411.01493 Sample-Efficient Alignment for LLMs
        39633, -- 2411.02571 MM-Embed: Universal Multimodal Retrieval with Multimodal LLMs
        39786, -- 2411.05288 Balancing Pipeline Parallelism with Vocabulary Parallelism
        39838, -- 2411.06272 Golden Touchstone: A Comprehensive Bilingual Benchmark for Evaluating Financial
        39874, -- 2411.07120 Lean and Mean Adaptive Optimization via Subset-Norm and Subspace-Momentum with C
        39929, -- 2411.07837 FRUGAL: Memory-Efficient Optimization by Reducing State Overhead for Scalable Tr
        39985, -- 2411.09009 Cut Your Losses in Large-Vocabulary Language Models
        40112, -- 2411.11505 LaVin-DiT: Large Vision Diffusion Transformer
        40124, -- 2411.11770 CNMBERT: A Model for Converting Hanyu Pinyin Abbreviations to Chinese Characters
        40126, -- 2411.11808 Character-level Tokenizations as Powerful Inductive Biases for RNA Foundational
        40166, -- 2411.12537 Unlocking State-Tracking in Linear RNNs Through Negative Eigenvalues
        40257, -- 2411.14279 Looking Beyond Text: Reducing Language bias in Large Vision-Language Models via
        40327, -- 2411.15124 Tulu 3: Pushing Frontiers in Open Language Model Post-Training
        40362, -- 2411.15488 Automatic Evaluation for Text-to-image Generation: Task-decomposed Framework, Di
        40411, -- 2411.16173 SALOVA: Segment-Augmented Long Video Assistant for Targeted Retrieval and Routin
        40428, -- 2411.16365 Multi-modal Retrieval Augmented Multi-modal Generation: A Benchmark, Evaluate Me
        40673, -- 2411.19378 Libra: Leveraging Temporal Images for Biomedical Radiology Analysis
        40729, -- 2412.00071 COAP: Memory-Efficient Training with Correlation-Aware Gradient Projection
        40840, -- 2412.01523 FlexSP: Accelerating Large Language Model Training via Flexible Sequence Paralle
        40894, -- 2412.02252 Compressing KV Cache for Long-Context LLM Inference with Inter-Layer Attention S
        41076, -- 2412.04454 Aguvis: Unified Pure Vision Agents for Autonomous GUI Interaction
        41130, -- 2412.04954 Gla-AI4BioMed at RRG24: Visual Instruction-tuned Adaptation for Radiology Report
        41233, -- 2412.06484 Small Languages, Big Models: A Study of Continual Training on Languages of Norwa
        41309, -- 2412.07612 ViewDelta: Text-Prompted Change Detection in Unaligned Images
        41438, -- 2412.09094 Filter-then-Generate: Large Language Models with Structure-Text Adapter for Know
        41458, -- 2412.09428 Multimodal Music Generation with Explicit Bridges and Retrieval Augmentation
        41678, -- 2412.11948 OpenReviewer: A Specialized Large Language Model for Generating Critical Scienti
        41797, -- 2412.13375 Extending LLMs to New Languages: A Case Study of Llama and Persian Adaptation
        41833, -- 2412.13922 Pipeline Analysis for Developing Instruct LLMs in Low-Resource Languages: A Case
        41851, -- 2412.14164 MetaMorph: Multimodal Understanding and Generation via Instruction Tuning
        41861, -- 2412.14219 A Survey on Inference Optimization Techniques for Mixture of Experts Models
        41891, -- 2412.14711 ReMoE: Fully Differentiable Mixture-of-Experts with ReLU Routing
        41913, -- 2412.15118 Reasoning Through Execution: Unifying Process and Outcome Rewards for Code Gener
        41993, -- 2412.16112 CLEAR: Conv-Like Linearization Revs Pre-Trained Diffusion Transformers Up
        42211, -- 2412.19191 Biology Instructions: A Dataset and Benchmark for Multi-Omics Sequence Understan
        42349, -- 2501.00365 Low-Rank Adaptation for Foundation Models: A Comprehensive Review
        42368, -- 2501.00654 ICONS: Influence Consensus for Vision-Language Data Selection
        42485, -- 2501.02448 Understand, Solve and Translate: Bridging the Multilingual Mathematical Reasonin
        42617, -- 2501.04575 InfiGUIAgent: A Multimodal Generalist GUI Agent with Native Reasoning and Reflec
        42748, -- 2501.06589 Ladder-residual: parallelism-aware architecture for accelerating large model inf
        42815, -- 2501.07783 Parameter-Inverted Image Pyramid Networks for Visual Perception and Multimodal U
        42974, -- 2501.10326 Large language models for automated scholarly paper review: A survey
        43007, -- 2501.11110 Chain-of-Reasoning: Towards Unified Mathematical Reasoning in Large Language Mod
        43044, -- 2501.11847 A Survey on Memory-Efficient Large-Scale Model Training in AI for Science
        43053, -- 2501.12051 MedS$^3$: Towards Medical Small Language Models with Self-Evolved Slow Thinking
        43097, -- 2501.12766 NExtLong: Toward Effective Long-Context Training without Long Documents
        43174, -- 2501.13928 Fast3R: Towards 3D Reconstruction of 1000+ Images in One Forward Pass
        43302, -- 2501.16255 A foundation model for human-AI collaboration in medical literature mining
        43326, -- 2501.16698 3D-MoE: A Mixture-of-Experts Multi-modal LLM for 3D Vision and Pose Diffusion vi
        43427, -- 2501.18623 VLMaterial: Procedural Material Generation with Large Vision-Language Models
        43544, -- 2502.01074 Omni-Mol: Exploring Universal Convergent Space for Omni-Molecular Tasks
        43707, -- 2502.03387 LIMO: Less is More for Reasoning
        43792, -- 2502.04463 Training Language Models to Reason Efficiently
        44012, -- 2502.07286 Small Language Model Makes an Effective Long Text Extractor
        44135, -- 2502.09042 Typhoon T1: An Open Thai Reasoning Model
        44136, -- 2502.09056 Adapting Language-Specific LLMs to a Reasoning Model in One Day via Model Mergin
        44203, -- 2502.10248 Step-Video-T2V Technical Report: The Practice, Challenges, and Future of Video F
        44207, -- 2502.10297 DeltaProduct: Improving State-Tracking in Linear RNNs via Householder Products
        44223, -- 2502.10451 FlexControl: Computation-Aware ControlNet with Differentiable Router for Text-to
        44314, -- 2502.11330 System Message Generation for User Preferences using Open-Source Models
        44355, -- 2502.11651 MMXU: A Multi-Modal and Multi-X-ray Understanding Dataset for Disease Progressio
        44411, -- 2502.12085 APB: Accelerating Distributed Long-Context Inference by Passing Compressed Conte
        44432, -- 2502.12171 GoRA: Gradient-driven Adaptive Low Rank Adaptation
        44527, -- 2502.13145 Multimodal Mamba: Decoder-only Multimodal State Space Model via Quadratic to Lin
        44579, -- 2502.13685 MoM: Linear Sequence Modeling with Mixture-of-Memories
        44840, -- 2502.16457 Towards Fully-Automated Materials Discovery via Large-Scale Synthesis Dataset an
        44893, -- 2502.16961 UrduLLaMA 1.0: Dataset Curation, Preprocessing, and Evaluation in Low-Resource S
        44897, -- 2502.16982 Muon is Scalable for LLM Training
        44939, -- 2502.17407 Linguistic Generalizability of Test-Time Scaling in Mathematical Reasoning
        45102, -- 2502.19587 NeoBERT: A Next-Generation BERT
        45224, -- 2502.21231 ByteScale: Efficient Scaling of LLM Training with a 2048K Context Length on More
        45229, -- 2502.21309 FANformer: Improving Large Language Models Through Effective Periodicity Modelin
        45318, -- 2503.01328 PipeOffload: Improving Scalability of Pipeline Parallelism with Memory Optimizat
        45398, -- 2503.02240 OmniSQL: Synthesizing High-quality Text-to-SQL Data at Scale
        45416, -- 2503.02502 LADM: Long-context Training Data Selection with Attention-based Dependency Measu
        45437, -- 2503.02844 Beyond Cosine Decay: On the effectiveness of Infinite Learning Rate Schedule for
        45497, -- 2503.03656 Robust Learning of Diverse Code Edits
        45553, -- 2503.04625 START: Self-taught Reasoner with Tools
        45626, -- 2503.05592 R1-Searcher: Incentivizing the Search Capability in LLMs via Reinforcement Learn
        45663, -- 2503.06134 X2I: Seamless Integration of Multimodal Understanding into Diffusion Transformer
        45691, -- 2503.06433 Seesaw: High-throughput LLM Inference via Model Re-sharding
        45712, -- 2503.06594 Beyond Decoder-only: Large Language Models Can be Good Encoders for Machine Tran
        45731, -- 2503.06823 eMoE: Task-aware Memory Efficient Mixture-of-Experts-Based (MoE) Model Inference
        45891, -- 2503.08569 DeepReview: Improving LLM-based Paper Review with Human-like Deep Thinking Proce
        45991, -- 2503.09642 Open-Sora 2.0: Training a Commercial-Level Video Generation Model in $200k
        46002, -- 2503.09799 Communication-Efficient Language Model Training Scales Reliably and Robustly: Sc
        46158, -- 2503.11579 Vamba: Understanding Hour-Long Videos with Hybrid Mamba-Transformers
        46211, -- 2503.12649 FW-Merging: Scaling Model Merging with Frank-Wolfe Optimization
        46212, -- 2503.12668 ZO2: Scalable Zeroth-Order Fine-Tuning for Extremely Large Language Models with
        46275, -- 2503.13551 Towards Hierarchical Multi-Step Reward Models for Enhanced Reasoning in Large La
        46531, -- 2503.16980 Token Dynamics: Towards Efficient and Dynamic Video Token Representation for Vid
        46541, -- 2503.17126 Modifying Large Language Model Post-Training for Diverse Creative Writing
        46567, -- 2503.17539 Generating, Fast and Slow: Scalable Parallel Video Generation with Video Interfa
        46591, -- 2503.17963 Won: Establishing Best Practices for Korean Financial NLP
        46622, -- 2503.18352 Diffusion-4K: Ultra-High-Resolution Image Synthesis with Latent Diffusion Models
        46706, -- 2503.19356 Can Vision-Language Models Answer Face to Face Questions in the Real-World?
        46772, -- 2503.20212 Dolphin: A Large-Scale Automatic Speech Recognition Model for Eastern Languages
        46793, -- 2503.20491 VPO: Aligning Text-to-Video Generation Models with Prompt Optimization
        46897, -- 2503.21889 StarFlow: Generating Structured Workflow Outputs From Sketch Images
        46965, -- 2503.22931 Factored Agents: Decoupling In-Context Learning and Memorization for Robust Tool
        47002, -- 2503.23330 EagleVision: Object-level Attribute Multimodal LLM for Remote Sensing
        47029, -- 2503.23714 Building Instruction-Tuning Datasets from Human-Written Instructions with Open-W
        47082, -- 2504.00019 ObscuraCoder: Powering Efficient Code LM Pre-Training Via Obfuscation Grounding
        47106, -- 2504.00595 Open-Qwen2VL: Compute-Efficient Pre-Training of Fully-Open Multimodal LLMs on Ac
        47131, -- 2504.00993 MedReason: Eliciting Factual Medical Reasoning Steps in LLMs via Knowledge Graph
        47168, -- 2504.01792 UniViTAR: Unified Vision Transformer with Native Resolution
        47179, -- 2504.01903 STAR-1: Safer Alignment of Reasoning LLMs with 1K Data
        47243, -- 2504.02725 ERPO: Advancing Safety Alignment via Ex-Ante Reasoning Preference Optimization
        47288, -- 2504.03380 Online Difficulty Filtering for Reasoning Oriented Reinforcement Learning
        47328, -- 2504.04152 Rethinking Multilingual Continual Pretraining: Data Mixing for Adapting   LLMs A
        47433, -- 2504.06263 OmniSVG: A Unified Scalable Vector Graphics Generation Model
        47488, -- 2504.07491 Kimi-VL Technical Report
        47507, -- 2504.07866 Pangu Ultra: Pushing the Limits of Dense Large Language Models on Ascend NPUs
        47818, -- 2504.12526 MOM: Memory-Efficient Offloaded Mini-Sequence Inference for Long Context Languag
        47899, -- 2504.13630 Remedy: Learning Machine Translation Evaluation from Human Preferences with Rewa
        48011, -- 2504.15280 Seeing from Another Perspective: Evaluating Multi-View Understanding in MLLMs
        48326, -- 2505.01043 Low-Precision Training of Large Language Models: Methods, Challenges,   and Oppo
        48345, -- 2505.01583 TEMPURA: Temporal Event Masked Prediction and Understanding for Reasoning in Act
        48490, -- 2505.04519 Pangu Ultra MoE: How to Train Your Big MoE on Ascend NPUs
        48603, -- 2505.06685 Emotion-Qwen: Training Hybrid Experts for Unified Emotion and General Vision-Lan
        48783, -- 2505.10557 MathCoder-VL: Bridging Vision and Code for Enhanced Multimodal Mathematical Reas
        48788, -- 2505.10584 Aquarius: A Family of Industry-Level Video Generation Models for Marketing Scena
        48842, -- 2505.11170 Gaussian Weight Sampling for Scalable, Efficient and Stable Pseudo-Quantization
        48866, -- 2505.11432 MegaScale-MoE: Large-Scale Communication-Efficient Training of Mixture-of-Expert
        48874, -- 2505.11497 QVGen: Pushing the Limit of Quantized Video Generative Models
        48935, -- 2505.12224 RoboFAC: A Comprehensive Framework for Robotic Failure Analysis and Correction
        48946, -- 2505.12312 Visuospatial Cognitive Assistant
        48991, -- 2505.12717 ToTRL: Unlock LLM Tree-of-Thoughts Reasoning Potential through Puzzles Solving
        48992, -- 2505.12723 On-Policy Optimization with Group Equivalent Preference for Multi-Programming La
        49087, -- 2505.13718 Warm Up Before You Train: Unlocking General Reasoning in Resource-Constrained Se
        49112, -- 2505.13949 FlashThink: An Early Exit Method For Efficient Reasoning
        49147, -- 2505.14256 FuxiMT: Sparsifying Large Language Models for Chinese-Centric Multilingual Machi
        49177, -- 2505.14442 Creative Preference Optimization
        49274, -- 2505.15245 Towards Explainable Temporal Reasoning in Large Language Models: A Structure-Awa
        49366, -- 2505.16097 TrialPanorama: Database and Benchmark for Systematic Review and Design of Clinic
        49376, -- 2505.16186 SafeKey: Amplifying Aha-Moment Insights for Safety Reasoning
        49407, -- 2505.16421 WebAgent-R1: Training Web Agents via End-to-End Multi-Turn Reinforcement Learnin
        49468, -- 2505.16972 From Tens of Hours to Tens of Thousands: Scaling Back-Translation for Speech Rec
        49481, -- 2505.17005 R1-Searcher++: Incentivizing the Dynamic Knowledge Acquisition of LLMs via Reinf
        49500, -- 2505.17134 LongMagpie: A Self-synthesis Method for Generating Large-scale Long-context Inst
        49514, -- 2505.17387 WiNGPT-3.0 Technical Report
        49571, -- 2505.18092 QwenLong-CPRS: Towards $\infty$-LLMs with Dynamic Context Optimization
        49708, -- 2505.19236 Evaluating Text Creativity across Diverse Domains: A Dataset and Large Language
        49919, -- 2505.21062 Inverse Virtual Try-On: Generating Multi-Category Product-Style Images from Clot
        50062, -- 2505.22977 HyperMotion: DiT-Based Pose-Guided Human Image Animation of Complex Motions
        50168, -- 2505.23816 A Course Correction in Steerability Evaluation: Revealing Miscalibration and Sid
        50192, -- 2505.24034 LlamaRL: A Distributed Asynchronous Reinforcement Learning Framework for Efficie
        50217, -- 2505.24298 AReaL: A Large-Scale Asynchronous Reinforcement Learning System for Language Rea
        50235, -- 2505.24500 TimeHC-RL: Temporal-aware Hierarchical Cognitive Reinforcement Learning for Enha
        50297, -- 2506.00189 Control-R: Towards controllable test-time scaling
        50377, -- 2506.01331 Ultra-High-Resolution Image Synthesis: Data, Method and Evaluation
        50451, -- 2506.02444 SViMo: Synchronized Diffusion for Video and Motion Generation in Hand-object Int
        50481, -- 2506.02979 Towards a Japanese Full-duplex Spoken Dialogue System
        50487, -- 2506.03099 TalkingMachines: Real-Time Audio-Driven FaceTime-Style Video via Autoregressive
        50528, -- 2506.03614 VLMs Can Aggregate Scattered Training Patches
        50708, -- 2506.06122 Reinforcement Learning Optimization for Large-Scale Learning: An Efficient and U
        50775, -- 2506.07634 SongBloom: Coherent Song Generation via Interleaved Autoregressive Sketching and
        50801, -- 2506.07972 HeuriGym: An Agentic Benchmark for LLM-Crafted Heuristics in Combinatorial Optim
        50959, -- 2506.09958 Kvasir-VQA-x1: A Multimodal Dataset for Medical Reasoning and Robust MedVQA in G
        51090, -- 2506.12015 EMLoC: Emulator-based Memory-efficient Fine-tuning with LoRA Correction
        51164, -- 2506.13695 OneRec Technical Report
        51178, -- 2506.13793 Med-REFL: Medical Reasoning Enhancement via Self-Corrected Fine-grained Reflecti
        51188, -- 2506.13996 Arctic Long Sequence Training: Scalable And Efficient Training For Multi-Million
        51271, -- 2506.15681 GenRecal: Generation after Recalibration from Large to Small   Vision-Language M
        51471, -- 2506.20639 DiffuCoder: Understanding and Improving Masked Diffusion Models for Code Generat
        51502, -- 2506.21263 DiLoCoX: A Low-Communication Large-Scale Training Framework for Decentralized Cl
        51505, -- 2506.21285 Double-Checker: Enhancing Reasoning of Slow-Thinking LLMs via Self-Critical Fine
        51629, -- 2507.01949 Kwai Keye-VL Technical Report
        51674, -- 2507.03336 Disambiguation-Centric Finetuning Makes Enterprise Tool-Calling LLMs More Realis
        51733, -- 2507.05411 AXLearn: Modular Large Model Training on Heterogeneous Infrastructure
        51803, -- 2507.07129 Growing Transformers: Modular Composition and Layer-wise Expansion on a Frozen S
        51928, -- 2507.12455 Mitigating Object Hallucinations via Sentence-Level Early Intervention
        52023, -- 2507.16116 PUSA V1.0: Surpassing Wan-I2V with $500 Training Cost by Vectorized   Timestep A
        52052, -- 2507.18013 Technical Report of TeleChat2, TeleChat2.5 and T1
        52081, -- 2507.20527 SAND-Math: Using LLMs to Generate Novel, Difficult and Useful   Mathematics Ques
        52111, -- 2507.22607 VL-Cogito: Progressive Curriculum Reinforcement Learning for Advanced   Multimod
        52143, -- 2508.00454 Learning an Efficient Multi-Turn Dialogue Evaluator from Multiple Judges
        52191, -- 2508.02317 VeOmni: Scaling Any Modality Model Training with Model-Centric   Distributed Rec
        52246, -- 2508.04676 GeRe: Towards Efficient Anti-Forgetting in Continual Learning of LLM via   Gener
        52290, -- 2508.06813 Technical Report: Full-Stack Fine-Tuning for the Q Programming Language
        52377, -- 2508.10881 ToonComposer: Streamlining Cartoon Production with Generative   Post-Keyframing
        52469, -- 2508.15868 CARFT: Boosting LLM Reasoning via Contrastive Learning with Annotated   Chain-of
        52558, -- 2508.20404 AWorld: Orchestrating the Training Recipe for Agentic AI
        52840, -- 2509.13761 THOR: Tool-Integrated Hierarchical Optimization via RL for Mathematical   Reason
        52843, -- 2509.13683 Improving Context Fidelity via Native Retrieval-Augmented Reasoning
        52846, -- 2509.13523 AERIS: Argonne Earth Systems Model for Reliable and Skillful Predictions
        52927, -- 2509.14856 CodeFuse-CR-Bench: A Comprehensiveness-aware Benchmark for End-to-End   Code Rev
        53051, -- 2509.25760 TruthRL: Incentivizing Truthful LLMs via Reinforcement Learning
        53070, -- 2509.24207 Humanline: Online Alignment as Perceptual Loss
        53139, -- 2510.01149 ModernVBERT: Towards Smaller Visual Document Retrievers
        53149, -- 2510.02294 F2LLM Technical Report: Matching SOTA Embedding Performance with 6   Million Ope
        53202, -- 2510.03230 Improving GUI Grounding with Explicit Position-to-Coordinate Mapping
        53329, -- 2510.05862 Revisiting Long-context Modeling from Context Denoising Perspective
        53379, -- 2510.06915 LongRM: Revealing and Unlocking the Context Boundary of Reward Modeling
        53403, -- 2509.24797 Fidelity-Aware Data Composition for Robust Robot Generalization
        53409, -- 2510.04533 TAG:Tangential Amplifying Guidance for Hallucination-Resistant Diffusion   Sampl
        53441, -- 2510.08872 GTAlign: Game-Theoretic Alignment of LLM Assistants for Mutual Welfare
        53488, -- 2510.07731 oMeBench: Towards Robust Benchmarking of LLMs in Organic Mechanism   Elucidation
        53521, -- 2510.12709 SAIL-Embedding Technical Report: Omni-modal Embedding Foundation Model
        53556, -- 2510.13802 Trace Anything: Representing Any Video in 4D via Trajectory Fields
        53571, -- 2510.10921 FG-CLIP 2: A Bilingual Fine-grained Vision-Language Alignment Model
        53675, -- 2510.16449 TrajSelector: Harnessing Latent Representations for Efficient and   Effective Be
        53676, -- 2510.17354 Towards Mixed-Modal Retrieval for Universal Retrieval-Augmented   Generation
        53750, -- 2510.19307 Unified Reinforcement and Imitation Learning for Vision-Language Models
        53944, -- 2510.25771 Gaperon: A Peppered English-French Generative Language Model Suite
        53949, -- 2510.18672 Reasoning Language Model Inference Serving Unveiled: An Empirical Study
        54004, -- 2510.20150 Rank-GRPO: Training LLM-based Conversational Recommender Systems with   Reinforc
        54060, -- 2511.01450 Reg-DPO: SFT-Regularized Direct Preference Optimization with GT-Pair for   Impro
        54317, -- 2511.17127 Training Foundation Models on a Full-Stack AMD Platform: Compute, Networking, an
        54588, -- 2512.03052 LATTICE: Democratize High-Fidelity 3D Generation at Scale
        54642, -- 2512.06533 Beyond Token-level Supervision: Unlocking the Potential of Decoding-based Regres
        54751, -- 2512.13586 ReFusion: A Diffusion Large Language Model with Parallel Autoregressive Decoding
        54858, -- 2512.14080 SonicMoE: Accelerating MoE with IO and Tile-aware Optimizations
        54901, -- 2512.16793 PhysBrain: Human Egocentric Data as a Bridge from Vision Language Models to Phys
        55003, -- 2512.22238 Masking Teacher and Reinforcing Student for Distilling Vision-Language Models
        55015, -- 2512.22234 DiRL: An Efficient Post-Training Framework for Diffusion Language Models
        55086, -- 2601.02204 NextFlow: Unified Sequential Modeling Activates Multimodal Understanding and Gen
        55090, -- 2601.02358 VINO: A Unified Visual Generator with Interleaved OmniModal Context
        55566, -- 2601.18150 FP8-RL: A Practical and Stable Low-Precision Stack for LLM Reinforcement Learnin
        55756, -- 2602.04705 ERNIE 5.0 Technical Report
        55843, -- 2602.02016 DASH: Faster Shampoo via Batched Block Preconditioning and Efficient Inverse-Roo
        55865, -- 2602.06079 Canzona: A Unified, Asynchronous, and Load-Balanced Framework for Distributed Ma
        56081, -- 2602.11543 Pretraining A Large Language Model using Distributed GPUs: A Memory-Efficient De
        56091, -- 2602.12617 GeoAgent: Learning to Geolocate Everywhere with Reinforced Geographic Characteri
        56136, -- 2602.14060 LM-Lexicon: Improving Definition Modeling via Harmonizing Semantic Experts
        56155, -- 2602.15763 GLM-5: from Vibe Coding to Agentic Engineering
        56356, -- 2602.22661 dLLM: Simple Diffusion Language Modeling
        56373, -- 2602.22647 Vectorizing the Trie: Efficient Constrained Decoding for LLM-based Generative Re
        56395, -- 2602.21320 Tool-R0: Self-Evolving LLM Agents for Tool-Learning from Zero Data
        56399, -- 2603.02099 Recursive Think-Answer Process for LLMs and VLMs
        56440, -- 2603.01421 SciDER: Scientific Data-centric End-to-end Researcher
        56554, -- 2603.08706 Agentic Critical Training
        56837, -- 2603.11535 Expert Threshold Routing for Autoregressive Language Modeling with Dynamic Compu
        56942, -- 2603.22276 Scaling DoRA: High-Rank Adaptation via Factored Norms and Fused Kernels
        57059, -- 2603.24477 Composer 2 Technical Report
        57160, -- 2603.25406 MMaDA-VLA: Large Diffusion Vision-Language-Action Model with Unified Multi-Modal
        57164, -- 2604.00886 PixelPrune: Pixel-Level Adaptive Visual Token Reduction via Predictive Coding
        57172, -- 2603.26164 DataFlex: A Unified Framework for Data-Centric Dynamic Training of Large Languag
        57288, -- 2604.06168 Action Images: End-to-End Policy Learning via Multiview Video Generation
        57560, -- 2604.14568 Learning Adaptive Reasoning Paths for Efficient Visual Reasoning
        57810, -- 2604.27085 Efficient Training on Multiple Consumer GPUs with RoundPipe
        58136, -- 2604.15416 StoSignSGD: Unbiased Structural Stochasticity Fixes SignSGD for Training Large L
        58187, -- 2604.13538 Synthesizing Instruction-Tuning Datasets with Contrastive Decoding
        58295, -- 2512.08217 Correction of Decoupled Weight Decay
        58342, -- 2604.09494 RecaLLM: Addressing the Lost-in-Thought Phenomenon with Explicit In-Context Retr
        58401, -- 2603.20843 HiCI: Hierarchical Construction-Integration for Long-Context Attention
        58740, -- 2511.22715 ReAG: Reasoning-Augmented Generation for Knowledge-based Visual Question Answeri
        58853, -- 2603.22687 GeoTikzBridge: Advancing Multimodal Code Generation for Geometric Perception and
        59030, -- 2603.22607 Dress-ED: Instruction-Guided Editing for Virtual Try-On and Try-Off
        59259, -- 2603.16430 EngGPT2: Sovereign, Efficient and Open Intelligence
        59269, -- 2603.16256 When Thinking Hurts: Mitigating Visual Forgetting in Video Reasoning via Frame R
        59288, -- 2603.16428 An Efficient Heterogeneous Co-Design for Fine-Tuning on a Single GPU
        59305, -- 2603.15953 A Family of LLMs Liberated from Static Vocabularies
        59581, -- 2603.10408 Motion Forcing: A Decoupled Framework for Robust Video Generation in Motion Dyna
        59796, -- 2603.06049 Devil is in Narrow Policy: Unleashing Exploration in Driving VLA Models
        59861, -- 2603.04949 TimeWarp: Evaluating Web Agents by Revisiting the Past
        59940, -- 2603.03508 Raising Bars, Not Parameters: LilMoo Compact Language Model for Hindi
        59992, -- 2603.02885 MuxTune: Efficient Multi-Task LLM Fine-Tuning in Multi-Tenant Datacenters via Sp
        60104, -- 2602.00428 When Agents "Misremember" Collectively: Exploring the Mandela Effect in LLM-base
        60167, -- 2602.23784 TradeFM: A Generative Foundation Model for Trade-flow and Market Microstructure
        60203, -- 2602.23349 FlashOptim: Optimizers for Memory Efficient Training
        60437, -- 2602.18773 LAMMI-Pathology: A Tool-Centric Bottom-Up LVLM-Agent Framework for Molecularly I
        60532, -- 2602.16430 Designing Production-Scale OCR for India: Multilingual and Domain-Specific Syste
        60899, -- 2602.09934 VersaViT: Enhancing MLLM Vision Backbones via Task-Guided Optimization
        61219, -- 2602.05125 Rethinking Rubric Generation for Improving LLM Judge and Reward Modeling for Ope
        61520, -- 2602.01410 SNIP: An Adaptive Mixed Precision Framework for Subbyte Large Language Model Tra
        61556, -- 2602.01034 Discovering Process-Outcome Credit in Multi-Step LLM Reasoning
        61627, -- 2602.00570 GLAD: Generative Language-Assisted Visual Tracking for Low-Semantic Templates
        61713, -- 2601.22708 A Unified Study of LoRA Variants: Taxonomy, Review, Codebase, and Empirical Eval
        61773, -- 2601.22135 PI-Light: Physics-Inspired Diffusion for Full-Image Relighting
        61961, -- 2601.19739 TokenSeek: Memory Efficient Fine Tuning via Instance-Aware Token Ditching
        62164, -- 2601.16956 DataStates-LLM: Scalable Checkpointing for Transformer Models Using Composable S
        62197, -- 2601.15793 HumanLLM: Towards Personalized Understanding and Simulation of Human Nature
        62277, -- 2601.14440 VisTIRA: Closing the Image-Text Modality Gap in Visual Math Reasoning via Struct
        62453, -- 2601.10632 CoMoVi: Co-Generation of 3D Human Motions and Realistic Videos
        62522, -- 2601.09200 A.X K1 Technical Report
        62541, -- 2502.01930 Robust LLM Alignment via Distributionally Robust Direct Preference Optimization
        62946, -- 2601.02954 The World is Not Mono: Enabling Spatial Understanding in Large Audio-Language Mo
        63190, -- 2512.24157 Training Report of TeleChat3-MoE
        63360, -- 2512.20920 RevFFN: Memory-Efficient Full-Parameter Fine-Tuning of Mixture-of-Experts LLMs w
        63592, -- 2512.15885 Seeing Beyond Words: Self-Supervised Visual Learning for Multimodal Large Langua
        63926, -- 2512.08713 Automatic Essay Scoring and Feedback Generation in Basque Language Learning
        63931, -- 2512.08580 Mind to Hand: Purposeful Robotic Control via Embodied Reasoning
        64207, -- 2512.02787 Diagnose, Correct, and Learn from Manipulation Failures via Visual Symbols
        64479, -- 2511.21272 Co-Training Vision Language Models for Remote Sensing Multi-task Learning
        64517, -- 2511.20644 Vision-Language Memory for Spatial Reasoning
        64767, -- 2511.16665 Taming the Long-Tail: Efficient Reasoning RL Training with Adaptive Drafter
        64773, -- 2511.16600 You Only Forward Once: An Efficient Compositional Judging Paradigm
        64785, -- 2511.16216 FlipVQA-Miner: Cross-Page Visual Question-Answer Mining from Textbooks
        65061, -- 2511.10301 Rethinking Visual Information Processing in Multimodal LLMs
        65068, -- 2511.10254 Facial-R1: Aligning Reasoning and Recognition for Facial Emotion Analysis
        65262, -- 2511.06446 SR-KI: Scalable and Real-Time Knowledge Integration into LLMs via Supervised Att
        65308, -- 2511.05057 Role-SynthCLIP: A Role Play Driven Diverse Synthetic Data Approach
        65516, -- 2511.01014 IF-CRITIC: Towards a Fine-Grained LLM Critic for Instruction-Following Evaluatio
        66075, -- 2510.18830 MTraining: Distributed Dynamic Sparse Attention for Efficient Ultra-Long Context
        66537, -- 2510.11938 FlexPipe: Adapting Dynamic LLM Serving Through Inflight Pipeline Refactoring in
        66794, -- 2510.07356 ConCuR: Conciseness Makes State-of-the-Art Kernel Generation
        66833, -- 2510.06627 POME: Post Optimization Model Edit via Muon-style Projection
        66886, -- 2510.05827 VCoT-Grasp: Grasp Foundation Models with Visual Chain-of-Thought   Reasoning for
        67020, -- 2510.03515 RAPID: An Efficient Reinforcement Learning Algorithm for Small Language   Models
        67268, -- 2510.00206 LoRAFusion: Efficient LoRA Fine-Tuning for LLMs
        67372, -- 2509.25591 Building the EHR Foundation Model via Next Event Prediction
        67624, -- 2509.23106 Effective Quantization of Muon Optimizer States
        67738, -- 2509.21841 Zeppelin: Balancing Variable-length Workloads in Data Parallel Large   Model Tra
        67826, -- 2509.20883 RecIS: Sparse to Dense, A Unified Training Framework for Recommendation Models
        68002, -- 2509.17863 Expert-as-a-Service: Towards Efficient, Scalable, and Robust Large-scale   MoE S
        68063, -- 2509.16889 Can GRPO Boost Complex Multimodal Table Understanding?
        68133, -- 2509.15965 RLinf: Flexible and Efficient Large-scale Reinforcement Learning via   Macro-to-
        68247, -- 2509.14234 Compute as Teacher: Turning Inference Compute Into Reference-Free   Supervision
        68326, -- 2509.12892 Conan-Embedding-v2: Training an LLM from Scratch for Text Embeddings
        68642, -- 2509.06321 Text4Seg++: Advancing Image Segmentation via Generative Language   Modeling
        68678, -- 2509.05570 LESER: Learning to Expand via Search Engine-feedback Reinforcement in e-Commerce
        68685, -- 2509.05276 SpikingBrain Technical Report: Spiking Brain-inspired Large Models
        68705, -- 2509.04866 Memorization neq Understanding: Do Large Language Models Have the   Ability of S
        68793, -- 2509.03018 Mycroft: Tracing Dependencies in Collective Communication Towards   Reliable LLM
        68921, -- 2509.04484 The Good, the Bad and the Constructive: Automatically Measuring Peer   Review's
        69069, -- 2508.20181 Mitigating Hallucinations in Multimodal LLMs via Object-aware Preference Optimiz
        69123, -- 2508.19532 Alignment with Fill-In-the-Middle for Enhancing Code Generation
        69167, -- 2508.18701 Attention2Probability: Attention-Driven Terminology Probability   Estimation for
        69306, -- 2508.16514 FLAMES: Improving LLM Math Reasoning via a Fine-Grained Analysis of the   Data S
        69363, -- 2508.15495 SynthCoder: A Synthetical Strategy to Tune LLMs for Code Completion
        69397, -- 2508.15096 Nemotron-CC-Math: A 133 Billion-Token-Scale High Quality Math   Pretraining Data
        69408, -- 2508.14828 Long Chain-of-Thought Reasoning Across Languages
        69413, -- 2508.14951 Improving LLMs for Machine Translation Using Synthetic Preference Data
        69503, -- 2508.13382 Datarus-R1: An Adaptive Multi-Step Reasoning LLM for Automated Data   Analysis
        69989, -- 2508.06165 UR^2: Unify RAG and Reasoning through Reinforcement Learning
        70066, -- 2508.05076 MetaDiT: Enabling Fine-grained Constraints in High-degree-of Freedom Metasurface
        70634, -- 2507.20849 Latent Inter-User Difference Modeling for LLM Personalization
        70636, -- 2507.20783 On The Role of Pretrained Language Models in General-Purpose Text   Embeddings:
        70648, -- 2507.20534 Kimi K2: Open Agentic Intelligence
        70855, -- 2507.21138 TTS-1 Technical Report
        71000, -- 2507.14447 Routine: A Structural Planning Framework for LLM Agent System in   Enterprise
        71058, -- 2507.12646 Reconstruct, Inpaint, Finetune: Dynamic Novel-view Synthesis from   Monocular Vi
        71083, -- 2507.12144 FourCastNet 3: A geometric approach to probabilistic machine-learning   weather
        71182, -- 2507.10616 Scalpel vs. Hammer: GRPO Amplifies Existing Capabilities, SFT Replaces   Them
        71461, -- 2507.03211 DistZO2: High-Throughput and Memory-Efficient Zeroth-Order Fine-tuning   LLMs wi
        71518, -- 2507.01643 SAILViT: Towards Robust and Generalizable Visual Backbones for MLLMs via   Gradu
        71608, -- 2507.02964 Less Data, More Security: Advancing Cybersecurity LLMs Specialization   via Reso
        71637, -- 2506.23325 XY-Tokenizer: Mitigating the Semantic-Acoustic Conflict in Low-Bitrate   Speech
        71652, -- 2506.23102 MedRegion-CT: Region-Focused Multimodal LLM for Comprehensive 3D CT Report Gener
        71664, -- 2506.22950 Infinite Sampling: Efficient and Stable Grouped RL Training for Large   Language
        71904, -- 2506.15266 Thunder-DeID: Accurate and Efficient De-identification Framework for   Korean Co
        72034, -- 2506.10833 Evaluating Large Language Models on Non-Code Software Engineering Tasks
        72053, -- 2506.10315 PyLO: Towards Accessible Learned Optimizers in PyTorch
        72087, -- 2506.09349 DrVoice: Parallel Speech-Text Voice Conversation Model via Dual-Resolution Speec
        72204, -- 2506.06009 Unlocking Recursive Thinking of LLMs: Alignment via Refinement
        72270, -- 2506.17238 Training a Scientific Reasoning Model for Chemistry
        72356, -- 2506.02368 NextQuill: Causal Preference Modeling for Enhancing LLM Personalization
        72524, -- 2506.15702 Minifinetuning: Low-Data Generation Domain Adaptation through Corrective   Self-
        72572, -- 2505.22549 DES-LOC: Desynced Low Communication Adaptive Optimizers for Training   Foundatio
        72589, -- 2505.22156 InComeS: Integrating Compression and Selection Mechanisms into LLMs for   Effici
        72661, -- 2505.20993 Who Reasons in the Large Language Models?
        72689, -- 2505.20524 Towards Fully FP8 GEMM LLM Training at Scale
        72785, -- 2505.18071 Extended Inductive Reasoning for Personalized Preference Inference from Behavior
        72793, -- 2505.17967 SVD-Free Low-Rank Adaptive Gradient Optimization for Large Language   Models
        72837, -- 2505.17266 Select2Reason: Efficient Instruction-Tuning Data Selection for Long-CoT   Reason
        72936, -- 2505.14142 AudSemThinker: Enhancing Audio-Language Models through Reasoning over   Semantic
        72939, -- 2505.14065 Prime Collective Communications Library -- Technical Report
        73038, -- 2505.11166 SoLoPO: Unlocking Long-Context Capabilities in LLMs via Short-to-Long Preference
        73369, -- 2504.16832 GreenMind: A Next-Generation Vietnamese Large Language Model for   Structured an
        73426, -- 2504.14960 MoE Parallel Folding: Heterogeneous Parallelism Mappings for Efficient   Large-S
        73567, -- 2504.08862 RTLRepoCoder: Repository-Level RTL Code Completion through the   Combination of
        73805, -- 2503.23746 Short-video Propagation Influence Rating: A New Real-world Dataset and A New Lar
        73963, -- 2503.15463 From 1,000,000 Users to Every User: Scaling Up Personalized Preference for User-
        74106, -- 2503.10377 SPPO:Efficient Long-sequence LLM Training via Adaptive Sequence Pipeline   Paral
        74148, -- 2503.08662 Exploring the Word Sense Disambiguation Capabilities of Large Language   Models
        74306, -- 2503.02356 Efficient Long Context Fine-tuning with Chunk Flow
        74316, -- 2503.02103 Superficial Self-Improved Reasoners Benefit from Model Merging
        74348, -- 2503.01298 MINT: Multi-modal Chain of Thought in Unified Generative Models for   Enhanced I
        74394, -- 2503.00089 Protein Structure Tokenization: Benchmarking and New Recipe
        74515, -- 2502.16580 Can Indirect Prompt Injection Attacks Be Detected and Removed?
        74544, -- 2502.15218 ESPnet-SpeechLM: An Open Speech Language Model Toolkit
        74573, -- 2502.14932 Learning to Retrieve and Reason on Knowledge Graph through Active   Self-Reflect
        74635, -- 2502.12340 Understanding Silent Data Corruption in LLM Training
        74763, -- 2502.06742 Gradient Multi-Normalization for Stateless and Scalable LLM Training
        74766, -- 2502.06728 DeToNATION: Decoupled Torch Network-Aware Training on Interlinked Online Nodes
        74917, -- 2502.02581 Hecate: Unlocking Efficient Sparse Model Training via Fully Sharded   Sparse Dat
        75115, -- 2501.12670 Celo: Training Versatile Learned Optimizers on a Compute Diet
        75126, -- 2501.12079 Directional Diffusion-Style Code Editing Pre-training
        75280, -- 2501.03681 SLAM: Towards Efficient Multilingual Reasoning via Selective Language Alignment
        75371, -- 2412.17429 Condor: A Code Discriminator Integrating General Semantics with Code   Details
        75538, -- 2412.07210 EDiT: A Local-SGD-Based Efficient Distributed Training Method for Large Language
        75792, -- 2411.10548 BioNeMo Framework: a modular, high-performance library for AI model development
        75829, -- 2411.06655 Explore the Reasoning Capability of LLMs in the Chess Testbed
        75886, -- 2411.01075 Cephalo: Harnessing Heterogeneous GPU Clusters for Training Transformer   Models
        75912, -- 2410.23261 $100K or 100 Days: Trade-offs when Pre-Training with Academic Resources
        76243, -- 2409.19700 2D-TPE: Two-Dimensional Positional Encoding Enhances Table Understanding for Lar
        76806, -- 2407.04420 cosmosage: A Natural-Language Assistant for Cosmologists
        77103, -- 2406.06571 SUBLLM: A Novel Efficient Architecture with Token Sequence Subsampling   for LLM
        77114, -- 2406.06564 SwitchLoRA: Switched Low-Rank Adaptation Can Learn Full-Rank Information
        77644, -- 2403.08228 Empowering Robotics with Large Language Models: osmAG Map Comprehension   with L
        77718, -- 2403.01164 HeteGen: Heterogeneous Parallel Inference for Large Language Models on   Resourc
        77935, -- 2401.09670 DistServe: Disaggregating Prefill and Decoding for Goodput-optimized   Large Lan
        78087, -- 2312.10103 GSVA: Generalized Segmentation via Multimodal Large Language Models
        78356, -- 2310.12670 Reliable and Efficient In-Memory Fault Tolerance of Large Language Model   Pretr
        82852, -- 2605.00380 ResRL: Boosting LLM Reasoning via Negative Sample Projection Residual Reinforcem
        83004, -- 2605.10468 Can Muon Fine-tune Adam-Pretrained Models?
        83108, -- 2605.13779 MinT: Managed Infrastructure for Training and Serving Millions of LLMs
        83118, -- 2605.13757 FrameSkip: Learning from Fewer but More Informative Frames in VLA Training
        83228, -- 2605.09530 MemPrivacy: Privacy-Preserving Personalized Memory Management for Edge-Cloud Age
        83426, -- 2506.08123 QA-LIGN: Aligning LLMs through Constitutionally Decomposed QA
        83477, -- 2605.20164 Not Every Rubric Teaches Equally: Policy-Aware Rubric Rewards for RLVR
        83580, -- 2605.22355 TransitLM: A Large-Scale Dataset and Benchmark for Map-Free Transit Route Genera
        83858, -- 2605.25969 Triplet-Block Diffusion RWKV
        84286, -- 2511.23151 Learning to Refuse: Refusal-Aware Reinforcement Fine-Tuning for Hard-Irrelevant
        85025, -- 2603.21295 Text-Image Conditioned 3D Generation
        85047, -- 2603.22193 PAM: A Pose-Appearance-Motion Engine for Sim-to-Real HOI Video Generation
        85365, -- 2604.12391 Chain-of-Models Pre-Training: Rethinking Training Acceleration of Vision Foundat
        85389, -- 2604.15670 PixDLM: A Dual-Path Multimodal Language Model for UAV Reasoning Segmentation
        85706, -- 2506.05745 SPRINT: Enabling Interleaved Planning and Parallelized Execution in Reasoning Mo
        86041, -- 2502.01586 SubTrack++ : Gradient Subspace Tracking for Scalable LLM Training
        86109, -- 2509.15940 Efficient Pre-Training of LLMs via Topology-Aware Communication Alignment on Mor
        86126, -- 2505.19609 Skrull: Towards Efficient Long Context Fine-tuning through Dynamic Data Scheduli
        86234, -- 2406.02613 ACCO: Accumulate While You Communicate for Communication-Overlapped Sharded LLM
        86501, -- 2507.17511 Accelerating Parallel Diffusion Model Serving with Residual Compression
        86835, -- 2407.00611 StarTrail: Concentric Ring Parallelism for Efficient Near-Infinite-Context Trans
        87127, -- 2509.16421 Aha! - Predicting What Matters Next: Online Highlight Detection Without Looking
        87567, -- 2507.18569 Adversarial Distribution Matching for Diffusion Distillation Towards Efficient I
        87809, -- 2503.23905 Boosting MLLM Reasoning with Text-Debiased Hint-GRPO
        88579, -- 2505.00793 Scalable Meta-Learning via Mixed-Mode Differentiation
        88764, -- 2505.07271 On the Robustness of Reward Models for Language Model Alignment
        88841, -- 2506.03700 AdaDecode: Accelerating LLM Decoding with Adaptive Layer Parallelism
        89242, -- 2407.20761 OmniBal: Towards Fast Instruction-Tuning for Vision-Language Models via  Omniver
        89724, -- 2501.19358 The Energy Loss Phenomenon in RLHF: A New Perspective on Mitigating Reward Hacki
        91031, -- 2410.05021 DEPT: Decoupled Embeddings for Pre-training Language Models
        91054, -- 2407.07890 Training on the Test Task Confounds Evaluation and Emergence
        91668, -- 2405.19846 Quest: Query-centric Data Synthesis Approach for Long-context Scaling of Large L
        92085, -- 2407.09709 GOFA: A Generative One-For-All Model for Joint Graph Language Modeling
        92371, -- 2406.02052 PETRA: Parallel End-to-end Training with Reversible Architectures
        92808, -- 2604.27089 AutoSP: Unlocking Long-Context LLM Training Via Compiler-Based Sequence Parallel
        92977, -- 2507.04219 Model Collapse Is Not a Bug but a Feature in Machine Unlearning for LLMs
        93504, -- 2503.06790 GenDR: Lighten Generative Detail Restoration
        93517, -- 2512.23461 Eliminating Inductive Bias in Reward Models with Information-Theoretic Guidance
        93562, -- 2510.00578 Arbitrary Generative Video Interpolation
        93787, -- 2602.10630 Eliminating VAE for Fast and High-Resolution Generative Detail Restoration
        94251, -- 2510.13166 CoT-Evo: Evolutionary Distillation of Chain-of-Thought for Scientific Reasoning
        94340, -- 2502.00340 Unlocking Full Efficiency of Token Filtering in Large Language Model Training
        94410, -- 2602.02108 Out of the Memory Barrier: A Highly Memory-Efficient Training System for LLMs wi
        94623, -- 2509.25044 A Scalable Distributed Framework for Multimodal GigaVoxel Image Registration
        95074, -- 2606.06428 Reinforcement Learning Elicits Contextual Learning of Unseen Language Translatio
        98038, -- 2606.09516 SwiftVR: Real-Time One-Step Generative Video Restoration
        98200, -- 2606.12397 Redesign Mixture-of-Experts Routers with Manifold Power Iteration
        98207, -- 2606.07881 Breaking the Bubble: Asynchronous Pipeline Parallel Training with Bounded Weight
        98542, -- 2606.18231 Adaptive Volumetric Mechanical Property Fields Invariant to Resolution
        98817, -- 2606.21661 UnityShots: Memory-Driven Multi-Shot Audio-Video Generation with Boundary-Aware
        98861, -- 2606.16517 How Post-Training Shapes Biological Reasoning Models
        98962, -- 2606.30084 One Forward Beats Two: InnerZoom for Accurate and Efficient GUI Grounding
        98980, -- 2606.30634 One-Step Gradient Delay is Not a Barrier for Large-Scale Asynchronous Pipeline P
        99144, -- 2512.07112 FOAM: Blocked State Folding for Memory-Efficient LLM Training
        99176, -- 2605.09603 Edit-Based Refinement for Parallel Masked Diffusion Language Models
        99222, -- 2606.01967 Training Prompt Matters: State-Adaptive Optimization for Robust Fine-Tuning
        99312, -- 2602.03515 Mitigating Staleness in Asynchronous Pipeline Parallelism via Basis Rotation
        99377, -- 2606.09009 Scaling by Diversified Experience for Vision-Language-Action Models
        99890, -- 2605.01517 VAnim: Rendering-Aware Sparse State Modeling for Structure-Preserving Vector Ani
        99920, -- 2605.18404 JanusPipe: Efficient Pipeline Parallel Training for Machine Learning Interatomic
        100072, -- 2601.17261 AGZO: Activation-Guided Zeroth-Order Optimization for LLM Fine-Tuning
        100146, -- 2508.18376 Mining Tensor/Neuron-Level Sparsity to Maximize Mixture-of-Experts Potential in
        100172, -- 2602.18037 Gradient Regularization Mitigates Reward Hacking in Reinforcement Learning from
        100246, -- 2602.18700 Watermarking LLM Agent Trajectories
        100301, -- 2602.10217 Temper-Then-Tilt: Principled Unlearning for Generative Models through Tempering
        100428, -- 2605.21558 From Parameters to Data: A Task-Parameter-Guided Fine-Tuning Pipeline for Effici
        100758, -- 2605.17342 Transitivity Meets Cyclicity: Explicit Preference Decomposition for Dynamic Larg
        101211, -- 2602.12429 Stabilizing Native Low-Rank LLM Pretraining
        101279, -- 2605.29664 AMDP: Asynchronous Multi-Directional Pipeline Parallelism for Large-Scale Models
        101402, -- 2511.17826 Deterministic Inference across Tensor Parallel Sizes That Eliminates Training-In
        101457, -- 2606.01062 DAG-MoE: From Simple Mixture to Structural Aggregation in Mixture-of-Experts
        101526, -- 2605.29782 Hista and Numca: Estimate State Value Effectively for Large Language Model Reinf
        101888, -- 2605.15081 ML-Embed: Inclusive and Efficient Embeddings for a Multilingual World
        102287, -- 2605.23244 Convex Optimization for Alignment and Preference Learning on a Single GPU
        102409, -- 2605.30487 Configurable Reward Model for Balanced Safety Alignment
        103129, -- 2605.09922 Team-Based Self-Play With Dual Adaptive Weighting for Fine-Tuning LLMs
        103321, -- 2605.18083 A Data-Efficient Path to Multilingual LLMs: Language Expansion via Post-training
        103423, -- 2604.14261 ReviewGrounder: Improving Review Substantiveness with Rubric-Guided, Tool-Integr
        103526, -- 2604.10502 CHAIRO: Contextual Hierarchical Analogical Induction and Reasoning Optimization
        103535, -- 2604.08326 ProMedical: Hierarchical Fine-Grained Criteria Modeling for Medical LLM Alignmen
        103557, -- 2604.13592 Foresight Optimization for Strategic Reasoning in Large Language Models
        103604, -- 2507.09205 From Curated Data to Scalable Models: Continual Pre-training of Dense and MoE La
        103677, -- 2605.22567 LANG: Reinforcement Learning for Multilingual Reasoning with Language-Adaptive H
        103899, -- 2606.28321 StructSplat: Generalizable 3D Gaussian Splatting from Uncalibrated Sparse Views
        104007, -- 2607.12395 Ring-Zero: Scaling Zero RL to a Trillion Parameters for Emergent Reasoning
        104064, -- 2607.14952 LongStraw: Long-Context RL Beyond 2M Tokens under a Fixed GPU Budget
        104301, -- 2607.16051 Loop the Loopies!
        104389, -- 2607.16074 JoyNexus: Service-Oriented Multi-Tenant Post-Training for VLA Models
        104458, -- 2607.19058 Where Should Optimizer State Live? Tiered State Allocation for Memory-Efficient
        104584, -- 2607.24653 Kimi K3: Open Frontier Intelligence
        106310, -- 2603.01331 MetaState: Persistent Working Memory Enhances Reasoning in Discrete Diffusion La
        106352, -- 2604.00666 TRIMS: Trajectory-Ranked Instruction Masked Supervision for Diffusion Language M
        106376, -- 2602.21492 GradAlign: Gradient-Aligned Data Selection for LLM Reinforcement Learning
        106684, -- 2511.10011 Reinforce Trustworthiness in Multimodal Emotional Support System
        109280, -- 2608.14290 Intern-S2-Mobius: Foundation Model with Decoupled Knowledge and Reasoning
        109291, -- 2608.12209 Generation as Auxiliary Supervision: Enhancing Visual Understanding at Zero Infe
        109644, -- 2608.20958 TLive-Omni: An Omni-Modal Understanding Model for E-Commerce Live Streaming
        109699, -- 2608.20953 Quantization-Aware Healing: A Practical Recipe for Recovering Compressed, 4-Bit
        110020, -- 2509.16375 Whisper-UT: A Unified Translation Framework for Speech and Text
        110152, -- 2504.04653 LEO-MINI: An Efficient Multimodal Large Language Model using Conditional Token R
        110228, -- 2509.05657 LM-Searcher: Cross-domain Neural Architecture Search with LLMs via Unified Numer
        110818, -- 2510.25310 Parrot: A Training Pipeline Enhances Both Program CoT and Natural Language CoT f
        111702, -- 2506.17611 OpusLM: A Family of Open Unified Speech Language Models
        112804, -- 2407.05257 OvSW: Overcoming Silent Weights for Accurate Binary Neural Networks
        114019, -- 2609.08368 Miles v0.1: Production-Level Post-Training
        114054, -- 2609.05592 What Did I Just Say? Self-Listening for Full-Duplex Speech Models
        114104, -- 2609.06931 CARDEA: Auditable Reasoning Grounded in Spatial Evidence for End-to-End Coronary
        117326, -- 2503.18083 Unified Geometry and Color Compression Framework for Point Clouds via Generative
        118993, -- 2607.02497 Seek to Segment: Active Perception for Panoramic Referring Segmentation
        119292, -- 2606.24361 SignNet-1M: Large-Scale Multilingual Sign Language Video Dataset with Downstream
        119431, -- 2607.04559 QSVideo: Query-Conditioned Semantic Temporal Retrieval for Video Understanding
        120362, -- 2307.16375 UniAP: Unifying Inter- and Intra-Layer Automatic Parallelism by Mixed Integer Qu
        120735, -- 2512.21778 Scene-VLM: Multimodal Video Scene Segmentation via Vision-Language Models
        121987, -- 2609.18487 ActionPiece: Rethinking Action Tokenization for Autoregressive Vision-Language-A
        122125, -- 2609.23169 UltraTex: Unleashing 2K Multi-View Diffusion for 3D Texturing
        122360, -- 2609.34645 Nereus: Adaptive Parallelism for LLM Post-Training
        122787, -- 2610.06647 LoGRA: Scaling LLM Reinforcement Learning with Low-Rank Gradient Sketches
        122817, -- 2610.08430 NeMo-DCR: Bit-Exact Delta-Compressed Refit for Scalable Agentic RL at Trillion-P
        123544, -- 2610.22341 3DCodeVerse: Exploring 3D Worlds as Code
        123864, -- 2610.27628 PAR: Progress-Aligned Recurrence for Length Generalization in State Tracking
        124184, -- 2605.11215 ReCoVer: Resilient LLM Pre-Training System via Fault-Tolerant Collective and Ver
        124556, -- 2608.26495 Video-FLAIR: Not Whether to Reason, But How
        124898, -- 2608.01896 GeoCore-9B: Towards Geo-Aware Generative Foundation Models in Earth Observation
        125131, -- 2605.27678 Heterogeneous Parallelism for Multimodal Large Language Model Training
        125416, -- 2606.26466 Soft Token Alignment for Cross-Lingual Reasoning
        125866, -- 2605.21177 ChunkFT: Byte-Streamed Optimization for Memory-Efficient Full Fine-Tuning
        125887, -- 2605.25880 The Quantization Benefits of Residual-Free Transformers
        126042, -- external When Must AI Training Stage Checkpoints? A Distributional Model of Durability Bo
        126344, -- 2602.21788 Efficient Scaling of LLM Training with Flexible Context Parallelism
        126786, -- 2605.10741 AdaPaD: Adaptive Parallel Deflation for PEFT with Self-Correcting Rank Discovery
        126805, -- 2606.10078 Mult-DPO: Multinomial Direct Preference Optimization for Recommender Systems
        126952, -- 2605.31463 PithTrain: A Compact and Agent-Native MoE Training System
        127415, -- 2606.04737 Physics-Informed Video Generation via Mixture-of-Experts Latent Alignment
        127465, -- 2602.03802 Do We Need Asynchronous SGD? On the Near-Optimality of Synchronous Methods
        127881, -- 2604.26256 DORA: A Scalable Asynchronous Reinforcement Learning System for Language Model T
        128044, -- 2610.19423 Beyond the Trial-and-Error Loop: Hybrid Projection and Automated Tuning for Dist
        128367, -- 2606.02976 Memory Retrieval for Changing Preferences
        128547, -- 2610.01891 RipplePLM: Structural and Property Decoupling for Protein Mutation Effect Genera
        129544, -- 2607.00293 Rosetta: Composable Native Multimodal Pretraining
        129707, -- 2604.20933 IRIS: Interpolative Rényi Iterative Self-play for Large Language Model Fine-Tuni
        129793, -- external MICA: Activation Checkpointing for Double-Backward Training of Machine Learning
        131249, -- 2605.09146 Beyond Thinking: Imagining in 360$^\circ$ for Humanoid Visual Search
        131571, -- 2610.34186 HuGe: Scaling Humanoid Generalist Vision-Language-Action Models with Egocentric
        131598, -- 2610.39664 EditAgent: Rethinking Agentic Image Editing
        131605, -- 2610.21143 CoSTA: Compressed Speech Token Adaptation for Efficient Spoken Dialogue Models
        131624, -- 2610.38331 Multi-Token Prediction Done Right
        131816, -- 2611.04449 Near-Zero Token Embeddings Silently Stall Training in Gated Sequence Models
        131820  -- 2611.03233 Axion 1.0: Open Agent Foundation Models, Simplified
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
        908, -- 1710.03740 Mixed Precision Training
        1082, -- 1802.00930 Mixed Precision Training of Convolutional Neural Networks using Integer Operatio
        1943, -- 1904.01038 fairseq: A Fast, Extensible Toolkit for Sequence Modeling
        2156, -- 1905.12322 A Study of BFLOAT16 for Deep Learning Training
        2482, -- 1909.00204 NEZHA: Neural Contextualized Representation for Chinese Language Understanding
        2571, -- 1909.09577 NeMo: a toolkit for building AI applications using Neural Modules
        4352, -- 2010.07002 Fast meningioma segmentation in T1-weighted MRI volumes using a lightweight 3D d
        22672, -- 2310.18313 FP8-LM: Training FP8 Large Language Models
        25845, -- 2401.08105 Hardware Acceleration for Real-Time Wildfire Detection Onboard Drone Networks
        31094, -- 2405.03637 Collage: Light-Weight Low-Precision Strategy for LLM Training
        32163, -- 2406.00209 Mamba State-Space Models Are Lyapunov-Stable Learners
        36323, -- 2408.15793 Language Adaptation on a Tight Academic Compute Budget: Tokenizer Swapping Works
        36799, -- 2409.07853 Improve Machine Learning carbon footprint using Nvidia GPU and Mixed Precision t
        42092, -- 2412.17548 Resource-Aware Arabic LLM Creation: Model Adaptation, Integration, and Multi-Dom
        43044, -- 2501.11847 A Survey on Memory-Efficient Large-Scale Model Training in AI for Science
        43348, -- 2501.17116 Optimizing Large Language Model Training Using FP4 Quantization
        44334, -- 2502.11458 Towards Efficient Pre-training: Exploring FP4 Precision in Large Language Models
        45840, -- 2503.08040 Accurate INT8 Training Through Dynamic Block-Level Fallback
        48721, -- 2505.09343 Insights into DeepSeek-V3: Scaling Challenges and Reflections on Hardware for AI
        49214, -- 2505.14669 Quartet: Native FP4 Training Can Be Optimal for Large Language Models
        54437, -- 2511.19496 Xmodel-2.5: 1.3B Data-Efficient Reasoning SLM
        60105, -- 2509.24276 G-reasoner: Foundation Models for Unified Reasoning over Graph-structured Knowle
        60203, -- 2602.23349 FlashOptim: Optimizers for Memory Efficient Training
        61520, -- 2602.01410 SNIP: An Adaptive Mixed Precision Framework for Subbyte Large Language Model Tra
        64342, -- 2512.00829 Accelerating Bangla NLP Tasks with Automatic Mixed Precision: Resource-Efficient
        64397, -- 2511.23225 TWEO: Transformers Without Extreme Outliers Enables FP8 Training And Quantizatio
        74418, -- 2502.20586 Training LLMs with MXFP4
        78495, -- 2309.12381 Memory Efficient Mixed-Precision Optimizers
        101668, -- 2601.20782 Neural Quantum States in Mixed Precision
        131217  -- external Beyond 3 Million Tokens: A Multi-Modal Foundation Model for Full-Resolution Heli
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
        1312, -- 1806.00187 Scaling Neural Machine Translation
        1627, -- 1811.06965 GPipe: Efficient Training of Giant Neural Networks using Pipeline Parallelism
        1677, -- 1812.01187 Bag of Tricks for Image Classification with Convolutional Neural Networks
        1767, -- 1901.07441 PadChest: A large chest x-ray image dataset with multi-label annotated reports
        1865, -- 1903.00757 GraphVite: A High-Performance CPU-GPU Hybrid System for Node Embedding
        1935, -- 1904.00420 Single Path One-Shot Neural Architecture Search with Uniform Sampling
        2034, -- 1904.10509 Generating Long Sequences with Sparse Transformers
        2085, -- 1905.03696 HAWQ: Hessian AWare Quantization of Neural Networks with Mixed-Precision
        2144, -- 1905.11286 Stochastic Gradient Methods with Layer-wise Adaptive Moments for Training of Dee
        2273, -- 1906.07155 MMDetection: Open MMLab Detection Toolbox and Benchmark
        2369, -- 1907.11692 RoBERTa: A Robustly Optimized BERT Pretraining Approach
        2561, -- 1909.08053 Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parall
        2632, -- 1910.02054 ZeRO: Memory Optimizations Toward Training Trillion Parameter Models
        2780, -- 1911.02972 Blockwise Self-Attention for Long Document Understanding
        2792, -- 1911.03852 HAWQ-V2: Hessian Aware trace-Weighted Quantization of Neural Networks
        2806, -- 1911.05248 What Do Compressed Deep Neural Networks Forget?
        2856, -- 1911.10668 JParaCrawl: A Large Scale Web-Based English-Japanese Parallel Corpus
        2978, -- 2001.00281 ZeroQ: A Novel Zero Shot Quantization Framework
        3129, -- 2002.09219 Stochastic Latent Residual Video Prediction
        3375, -- 2004.08531 MatchboxNet: 1D Time-Channel Separable Convolutional Neural Network Architecture
        3388, -- 2004.09602 Integer Quantization for Deep Learning Inference: Principles and Empirical Evalu
        3434, -- 2004.13637 Recipes for building an open-domain chatbot
        3613, -- 2005.11401 Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
        3683, -- 2006.04768 Linformer: Self-Attention with Linear Complexity
        3700, -- 2006.06873 FastPitch: Parallel Text-to-speech with Pitch Prediction
        3738, -- 2006.09882 Unsupervised Learning of Visual Features by Contrasting Cluster Assignments
        3747, -- 2006.10369 Deep Encoder, Shallow Decoder: Reevaluating Non-autoregressive Machine Translati
        3757, -- 2006.10802 DS6, Deformation-aware Semi-supervised Learning: Application to Small Vessel Seg
        3839, -- 2007.00072 Data Movement Is All You Need: A Case Study on Optimizing Transformers
        4037, -- 2008.08345 Deep Volumetric Ambient Occlusion
        4154, -- 2009.07531 Simplified TinyBERT: Knowledge Distillation for Document Retrieval
        4325, -- 2010.05171 fairseq S2T: Fast Speech-to-Text Modeling with fairseq
        4342, -- 2010.06192 Revisiting BFloat16 Training
        4593, -- 2011.10680 HAWQV3: Dyadic Neural Network Quantization
        4709, -- 2012.05628 As Good as New. How to Successfully Recycle English GPT-2 to Make Models for Oth
        4840, -- 2101.00234 Subformer: Exploring Weight Sharing for Parameter Efficiency in Generative Trans
        4845, -- 2101.00408 End-to-End Training of Neural Retrievers for Open-Domain Question Answering
        4879, -- 2101.03961 Switch Transformers: Scaling to Trillion Parameter Models with Simple and Effici
        4933, -- 2101.09469 Training Multilingual Pre-trained Language Model with Byte-level Subwords
        4989, -- 2102.02779 Unifying Vision-and-Language Tasks via Text Generation
        5058, -- 2102.09206 Less is More: Pre-train a Strong Text Encoder for Dense Retrieval Using a Weak D
        5086, -- 2102.12092 Zero-Shot Text-to-Image Generation
        5104, -- 2102.13249 Chess as a Testbed for Language Model State Tracking
        5108, -- 2103.00020 Learning Transferable Visual Models From Natural Language Supervision
        5121, -- 2103.01006 GaNDLF: A Generally Nuanced Deep Learning Framework for Scalable End-to-End Clin
        5188, -- 2103.06877 Fast and Accurate Model Scaling
        5272, -- 2103.13630 A Survey of Quantization Methods for Efficient Neural Network Inference
        5287, -- 2103.14636 A Practical Survey on Faster and Lighter Transformers
        5294, -- 2103.15075 PENELOPIE: Enabling Open Information Extraction for the Greek Language through M
        5484, -- 2104.08189 TalkNet 2: Non-Autoregressive Depth-Wise Separable Convolutional Model for Speec
        5582, -- 2104.12665 Clean Images are Hard to Reblur: Exploiting the Ill-Posed Inverse Task for Dynam
        5702, -- 2105.05233 Diffusion Models Beat GANs on Image Synthesis
        5741, -- 2105.08049 SGD-QA: Fast Schema-Guided Dialogue State Tracking for Unseen Services
        5773, -- 2105.10762 AutoLRS: Automatic Learning-Rate Schedule by Bayesian Optimization on the Fly
        5804, -- 2105.14071 Classification of Brain Tumours in MR Images using Deep Spatiospatial Models
        5882, -- 2106.02679 Layered gradient accumulation and modular pipeline parallelism: fast and efficie
        5909, -- 2106.03847 GAN Cocktail: mixing GANs without dataset access
        5985, -- 2106.07139 Pre-Trained Models: Past, Present and Future
        6047, -- 2106.10161 Golos: Russian Dataset for Speech Research
        6050, -- 2106.10207 Distributed Deep Learning in Open Collaborations
        6061, -- 2106.10715 CPM-2: Large-scale Cost-effective Pre-trained Language Models
        6270, -- 2107.08369 Flood Segmentation on Sentinel-1 SAR Imagery with Semi-Supervised Learning
        6358, -- 2108.01547 EVA: An Open-Domain Chinese Dialogue System with Large-Scale Generative Pre-Trai
        6409, -- 2108.05818 PatrickStar: Parallel Training of Pre-trained Models via Chunk-based Memory Mana
        6474, -- 2108.10808 Greenformers: Improving Computation and Memory Efficiency in Transformer Models
        6489, -- 2108.11801 Unsupervised domain adaptation for clinician pose estimation and instance segmen
        6493, -- 2108.12009 EmoBERTa: Speaker-Aware Emotion Recognition in Conversation with RoBERTa
        6641, -- 2109.06912 fairseq S^2: A Scalable and Integrable Speech Synthesis Toolkit
        6659, -- 2109.07865 OMPQ: Orthogonal Mixed Precision Quantization
        6811, -- 2110.02861 8-bit Optimizers via Block-wise Quantization
        6831, -- 2110.03584 Mixer-TTS: non-autoregressive, fast and compact text-to-speech model conditioned
        6877, -- 2110.05679 Large Language Models Can Be Strong Differentially Private Learners
        6917, -- 2110.06864 ByteTrack: Multi-Object Tracking by Associating Every Detection Box
        6978, -- 2110.08429 TorchEsegeta: Framework for Interpretability and Explainability of Image-based D
        7002, -- 2110.09456 NormFormer: Improved Transformer Pretraining with Extra Normalization
        7079, -- 2110.15032 OneFlow: Redesign the Distributed Deep Learning Framework from Scratch
        7100, -- 2110.15943 MetaICL: Learning to Learn In Context
        7164, -- 2111.03452 Generalized Radiograph Representation Learning via Cross-supervision between Ima
        7214, -- 2111.07783 FILIP: Fine-grained Interactive Language-Image Pre-Training
        7276, -- 2111.11124 Mesa: A Memory-saving Training Framework for Transformers
        7284, -- 2111.11432 Florence: A New Foundation Model for Computer Vision
        7357, -- 2112.00065 Boosting EfficientNets Ensemble Performance via Pseudo-Labels and Synthetic Imag
        7575, -- 2112.10684 Efficient Large Scale Language Modeling with Mixtures of Experts
        7576, -- 2112.10741 GLIDE: Towards Photorealistic Image Generation and Editing with Text-Guided Diff
        7604, -- 2112.13443 Sinogram upsampling using Primal-Dual UNet for undersampled CT and radial MRI re
        7690, -- 2201.05120 SeamlessGAN: Self-Supervised Synthesis of Tileable Texture Maps
        7781, -- 2201.11113 Post-training Quantization for Neural Networks with Provable Guarantees
        7792, -- 2201.11990 Using DeepSpeed and Megatron to Train Megatron-Turing NLG 530B, A Large-Scale Ge
        7912, -- 2202.04350 pNLP-Mixer: an Efficient all-MLP Architecture for Language
        7925, -- 2202.05048 Quantune: Post-training Quantization of Convolutional Neural Networks using Extr
        8004, -- 2202.08906 ST-MoE: Designing Stable and Transferable Sparse Expert Models
        8165, -- 2203.03605 DINO: DETR with Improved DeNoising Anchor Boxes for End-to-End Object Detection
        8246, -- 2203.07303 All in One: Exploring Unified Video-Language Pre-training
        8446, -- 2203.14463 Large-scale Bilingual Language-Image Contrastive Learning
        8466, -- 2203.15331 CNN Filter DB: An Empirical Investigation of Trained Convolutional Filters
        8473, -- 2203.15565 Killing Two Birds with One Stone:Efficient and Robust Training of Face Recogniti
        8903, -- 2205.00823 CenterCLIP: Token Clustering for Efficient Text-Video Retrieval
        8907, -- 2205.01068 OPT: Open Pre-trained Transformer Language Models
        9022, -- 2205.06975 RiCS: A 2D Self-Occlusion Map for Harmonizing Volumetric Objects
        9377, -- 2206.02680 Separable Self-attention for Mobile Vision Transformers
        9524, -- 2206.08853 MineDojo: Building Open-Ended Embodied Agents with Internet-Scale Knowledge
        9538, -- 2206.09479 StudioGAN: A Taxonomy and Benchmark of GANs for Image Synthesis
        9573, -- 2206.10996 ProtoCLIP: Prototypical Contrastive Language Image Pretraining
        9581, -- 2206.11357 GACT: Activation Compressed Training for Generic Network Architectures
        9669, -- 2207.00449 Dissecting Self-Supervised Learning Methods for Surgical Computer Vision
        9851, -- 2207.10167 Liver Segmentation using Turbolift Learning for CT and Cone-beam C-arm Perfusion
        9935, -- 2207.14386 Efficient NLP Model Finetuning via Multistage Data Filtering
        10052, -- 2208.07339 LLM.int8(): 8-bit Matrix Multiplication for Transformers at Scale
        10139, -- 2208.12097 Training a T5 Using Lab-sized Resources
        10183, -- 2208.14839 QuantNAS for super resolution: searching for efficient quantization-friendly arc
        10189, -- 2209.00099 Efficient Methods for Natural Language Processing: A Survey
        10263, -- 2209.05433 FP8 Formats for Deep Learning
        10361, -- 2209.09815 Towards Fine-tuning Pre-trained Language Models with Integer Forward and Backwar
        10578, -- 2210.02414 GLM-130B: An Open Bilingual Pre-trained Model
        10614, -- 2210.03273 A Unified Encoder-Decoder Framework with Entity Memory
        10765, -- 2210.06640 Compute-Efficient Deep Learning: Algorithmic Trends and Opportunities
        10952, -- 2210.11948 lo-fi: distributed fine-tuning without communication
        11237, -- 2211.03256 On Web-based Visual Corpus Construction for Visual Document Understanding
        11281, -- 2211.05100 BLOOM: A 176B-Parameter Open-Access Multilingual Language Model
        11409, -- 2211.09703 EfficientTrain: Exploring Generalized Curriculum Learning for Training Visual Ba
        11495, -- 2211.11586 Random-LTD: Random and Layerwise Token Dropping Brings Efficient Training for La
        11679, -- 2211.15841 MegaBlocks: Efficient Sparse Training with Mixture-of-Experts
        11687, -- 2211.16056 NoisyQuant: Noisy Bias-Enhanced Post-Training Activation Quantization for Vision
        11729, -- 2211.17257 CREPE: Open-Domain Question Answering with False Presuppositions
        11820, -- 2212.02770 CSQ: Growing Mixed-Precision Quantization Scheme with Bi-level Continuous Sparsi
        11850, -- 2212.03760 Pivotal Role of Language Modeling in Recommender Systems: Enriching Task-specifi
        12031, -- 2212.08663 Randomized Quantization: A Generic Augmentation for Data Agnostic Self-supervise
        12199, -- 2212.12017 OPT-IML: Scaling Language Model Instruction Meta Learning through the Lens of Ge
        12222, -- 2212.12977 SMMix: Self-Motivated Image Mixing for Vision Transformers
        12243, -- 2212.14034 Cramming: Training a Language Model on a Single GPU in One Day
        12323, -- 2301.02280 Filtering, Distillation, and Hard Negatives for Vision-Language Pre-Training
        12345, -- 2301.03110 RobArch: Designing Robust Architectures against Adversarial Attacks
        12565, -- 2301.11360 The Power of Linear Combinations: Learning with Random Convolutions
        12588, -- 2301.11706 Input Perturbation Reduces Exposure Bias in Diffusion Models
        12600, -- 2301.11975 Byte Pair Encoding for Symbolic Music
        12604, -- 2301.12017 Understanding INT4 Quantization for Transformer Models: Latency Speedup, Composa
        12652, -- 2301.12686 GibbsDDRM: A Partially Collapsed Gibbs Sampler for Solving Blind Inverse Problem
        12978, -- 2302.04585 Liver Segmentation in Time-resolved C-arm CT Volumes Reconstructed from Dynamic
        13173, -- 2302.08958 Towards Unifying Medical Vision-and-Language Pre-training via Soft Prompts
        13387, -- 2302.14696 Dissolving Is Amplifying: Towards Fine-Grained Anomaly Detection
        13687, -- 2303.06753 Modular Quantization-Aware Training for 6D Object Pose Estimation
        13802, -- 2303.08970 Gated Compression Layers for Efficient Always-On Models
        13902, -- 2303.10845 PanGu-Σ: Towards Trillion Parameter Language Model with Sparse Heterogeneous Com
        13926, -- 2303.11257 Unit Scaling: Out-of-the-Box Low-Precision Training
        13948, -- 2303.11525 Sparse-IFT: Sparse Iso-FLOP Transformations for Maximizing Training Efficiency
        14177, -- 2303.15247 Zero-Shot Composed Image Retrieval with Textual Inversion
        14337, -- 2303.17951 FP8 versus INT8 for efficient deep learning inference
        14349, -- 2303.18223 A Survey of Large Language Models
        14375, -- 2304.00471 A Unified Compression Framework for Efficient Speech-Driven Talking-Face Generat
        14388, -- 2304.00869 GreekBART: The First Pretrained Greek Sequence-to-Sequence Model
        14394, -- 2304.00958 DrBERT: A Robust Pre-trained Model in French for Biomedical and Clinical domains
        14462, -- 2304.02034 Effective Theory of Transformers at Initialization
        14463, -- 2304.02051 Multimodal Garment Designer: Human-Centric Latent Diffusion Models for Fashion I
        14502, -- 2304.03208 Cerebras-GPT: Open Compute-Optimal Language Models Trained on the Cerebras Wafer
        14624, -- 2304.05405 Efficient Automation of Neural Network Design: A Survey on Differentiable Neural
        14676, -- 2304.06704 How Will It Drape Like? Capturing Fabric Mechanics from Depth Images
        14686, -- 2304.06745 End-to-end codesign of Hessian-aware quantized neural networks for FPGAs and ASI
        14699, -- 2304.06941 AUTOSPARSE: Towards Automated Sparse Training of Deep Neural Networks
        14782, -- 2304.09172 Hyperbolic Image-Text Representations
        14866, -- 2304.11029 CLaMP: Contrastive Language-Music Pre-training for Cross-Modal Symbolic Music In
        14882, -- 2304.11277 PyTorch FSDP: Experiences on Scaling Fully Sharded Data Parallel
        14957, -- 2304.13013 Stable and low-precision training for large-scale vision-language models
        15199, -- 2305.02463 Shap-E: Generating Conditional 3D Implicit Functions
        15211, -- 2305.02606 Re$^3$Dial: Retrieve, Reorganize and Rescale Dialogue Corpus for Long-Turn Open-
        15369, -- 2305.05379 TASTY: A Transformer based Approach to Space and Time complexity
        15468, -- 2305.07017 An Inverse Scaling Law for CLIP Training
        15475, -- 2305.07185 MEGABYTE: Predicting Million-byte Sequences with Multiscale Transformers
        15779, -- 2305.11624 Efficient ConvBN Blocks for Transfer Learning and Beyond
        15969, -- 2305.13627 InstructAlign: High-and-Low Resource Language Alignment via Continual Crosslingu
        16024, -- 2305.14014 CLIP4STR: A Simple Baseline for Scene Text Recognition with Pre-trained Vision-L
        16065, -- 2305.14321 ConGraT: Self-Supervised Contrastive Pretraining for Joint Graph and Text Embedd
        16154, -- 2305.14858 Pre-RMSNorm and Pre-CRMSNorm Transformers: Equivalent and Efficient Pre-LN Trans
        16397, -- 2305.17100 BiomedGPT: A Generalist Vision-Language Foundation Model for Diverse Biomedical
        16405, -- 2305.17190 Multiplication-Free Transformer Training via Piecewise Affine Operations
        16540, -- 2305.18513 SlimFit: Memory-Efficient Fine-Tuning of Transformer-based Models Using Training
        16618, -- 2305.19268 Intriguing Properties of Quantization at Scale
        16729, -- 2306.00323 Thought Cloning: Learning to Think while Acting by Imitating Human Thinking
        16746, -- 2306.00477 Make Pre-trained Model Reversible: From Parameter to Memory Efficient Fine-Tunin
        16774, -- 2306.00789 Improved Cross-Lingual Transfer Learning For Automatic Speech Translation
        16925, -- 2306.02272 OWQ: Outlier-Aware Weight Quantization for Efficient Fine-Tuning and Inference o
        17002, -- 2306.03208 NLU on Data Diets: Dynamic Data Subset Selection for NLP Classification Tasks
        17090, -- 2306.04235 MobileNMT: Enabling Translation in 15MB and 30ms
        17134, -- 2306.04879 Augmenting Hessians with Inter-Layer Dependencies for Mixed-Precision Post-Train
        17530, -- 2306.09782 Full Parameter Fine-tuning for Large Language Models with Limited Resources
        17650, -- 2306.11987 Training Transformers with 4-bit Integers
        17714, -- 2306.13474 Efficient Online Processing with Deep Neural Networks
        17779, -- 2306.14884 Learning to Modulate pre-trained Models in RL
        17848, -- 2306.16269 RSPrompter: Learning to Prompt for Remote Sensing Instance Segmentation based on
        18087, -- 2307.03712 INT-FP-QSim: Mixed Precision and Formats For Large Language Models and Vision Tr
        18093, -- 2307.03798 Fooling Contrastive Language-Image Pre-trained Models with CLIPMasterPrints
        18124, -- 2307.04535 QBitOpt: Fast and Accurate Bitwidth Reallocation during Training
        18178, -- 2307.05695 ReLoRA: High-Rank Training Through Low-Rank Updates
        18201, -- 2307.06435 A Comprehensive Overview of Large Language Models
        18203, -- 2307.06440 No Train No Gain: Revisiting Efficient Training Algorithms For Transformer-based
        18442, -- 2307.10554 EMQ: Evolving Training-free Proxies for Automated Mixed Precision Quantization
        18573, -- 2307.12659 A Model for Every User and Budget: Label-Free and Personalized Mixed-Precision Q
        18706, -- 2307.14995 TransNormerLLM: A Faster and Better Large Language Model with Improved TransNorm
        18981, -- 2308.03281 Towards General Text Embeddings with Multi-stage Contrastive Learning
        18984, -- 2308.03290 FLIQS: One-Shot Mixed-Precision Floating-Point and Integer Quantization Search
        19092, -- 2308.05022 Exploring Frequency-Inspired Optimization in Transformer for Efficient Single Im
        19259, -- 2308.07650 EQ-Net: Elastic Quantization Neural Networks
        19262, -- 2308.07662 Gradient-Based Post-Training Quantization: Challenging the Status Quo
        19631, -- 2308.11485 Composed Image Retrieval using Contrastive Learning and Task-oriented CLIP-based
        20011, -- 2309.00363 FederatedScope-LLM: A Comprehensive Package for Fine-tuning Large Language Model
        20101, -- 2309.01945 On-Chip Hardware-Aware Quantization for Mixed Precision Neural Networks
        20124, -- 2309.02373 nanoT5: A PyTorch Framework for Pre-training and Fine-tuning T5-style Models wit
        20460, -- 2309.08186 A Precision-Scalable RISC-V DNN Processor with On-Device Learning Capability at
        20635, -- 2309.10818 SlimPajama-DC: Understanding Data Combinations for LLM Training
        21086, -- 2309.17224 Training and inference of large language models using 8-bit floating point
        21146, -- 2310.00344 HarmonyDream: Task Harmonization Inside World Models
        21147, -- 2310.00367 AutomaTikZ: Text-Guided Synthesis of Scientific Vector Graphics with TikZ
        21761, -- 2310.07147 QFT: Quantized Full-parameter Tuning of LLMs with Affordable Resources
        21917, -- 2310.08659 LoftQ: LoRA-Fine-Tuning-Aware Quantization for Large Language Models
        22731, -- 2310.19102 Atom: Low-bit Quantization for Efficient and Accurate LLM Serving
        22784, -- 2310.19923 Jina Embeddings 2: 8192-Token General-Purpose Text Embeddings for Long Documents
        22997, -- 2311.03301 Ziya2: Data-centric Learning is All LLMs Need
        23164, -- 2311.06025 ChiMed-GPT: A Chinese Medical Large Language Model with Full Training Regime and
        23171, -- 2311.06214 Instant3D: Fast Text-to-3D with Sparse-View Generation and Large Reconstruction
        23284, -- 2311.08089 Improving In-context Learning of Multilingual Generative Language Models with Cr
        23351, -- 2311.08849 OFA: A Framework of Initializing Unseen Subword Embeddings for Efficient Large-s
        23851, -- 2311.16442 Fast and Efficient 2-bit LLM Inference on GPU: 2/4/16-bit in a Weight Matrix wit
        24126, -- 2312.00674 LightCLIP: Learning Multi-Level Interaction for Lightweight Vision-Language Mode
        24127, -- 2312.00678 The Efficiency Spectrum of Large Language Models: An Algorithmic Survey
        24147, -- 2312.00845 VMC: Video Motion Customization using Temporal Attention Adaption for Text-to-Vi
        24539, -- 2312.05516 Stateful Large Language Model Serving with Pensieve
        24598, -- 2312.06550 LLM360: Towards Fully Transparent Open-Source LLMs
        25297, -- 2312.17279 Stateful Conformer with Cache-based Inference for Streaming Automatic Speech Rec
        25364, -- 2401.00625 Beyond Efficiency: A Systematic Survey of Resource-Efficient Large Language Mode
        25466, -- 2401.02038 Understanding LLMs: A Comprehensive Overview from Training to Inference
        25568, -- 2401.03804 TeleChat Technical Report
        25573, -- 2401.03868 FlightLLM: Efficient Large Language Model Inference with a Complete Mapping Flow
        25696, -- 2401.05811 Tuning LLMs with Contrastive Alignment Instructions for Machine Translation in U
        25730, -- 2401.06199 xTrimoPGLM: Unified 100B-Scale Pre-trained Transformer for Deciphering the Langu
        25761, -- 2401.06620 TransliCo: A Contrastive Learning Framework to Address the Script Barrier in Mul
        25861, -- 2401.08406 RAG vs Fine-tuning: Pipelines, Tradeoffs, and a Case Study on Agriculture
        26013, -- 2401.10241 Zero Bubble Pipeline Parallelism
        26082, -- 2401.11243 LRP-QViT: Mixed-Precision Vision Transformer Quantization via Layer-wise Relevan
        26250, -- 2401.13714 Value-Driven Mixed-Precision Quantization for Patch-Based Inference on Microcont
        26342, -- 2401.14895 MPTQ-ViT: Mixed-Precision Post-Training Quantization for Vision Transformer
        26460, -- 2401.16677 T3: Transparent Tracking & Triggering for Fine-grained Overlap of Compute & Coll
        26597, -- 2402.00838 OLMo: Accelerating the Science of Language Models
        26675, -- 2402.01613 Nomic Embed: Training a Reproducible Long Context Text Embedder
        26839, -- 2402.03293 Flora: Low-Rank Adapters Are Secretly Gradient Compressors
        27370, -- 2402.10076 QUICK: Quantization-aware Interleaving and Conflict-free Kernel for efficient LL
        27466, -- 2402.11139 LiGNN: Graph Neural Networks at LinkedIn
        27493, -- 2402.11355 A Practical Method for Generating String Counterfactuals
        27751, -- 2402.13929 SDXL-Lightning: Progressive Adversarial Diffusion Distillation
        27818, -- 2402.14654 Multi-HMR: Multi-Person Whole-Body Human Mesh Recovery in a Single Shot
        27853, -- 2402.14866 APTQ: Attention-aware Post-Training Mixed-Precision Quantization for Large Langu
        27917, -- 2402.15627 MegaScale: Scaling Large Language Model Training to More Than 10,000 GPUs
        27985, -- 2402.16689 Adaptation of Biomedical and Clinical Pretrained Models to French Long Documents
        28121, -- 2402.18096 No Token Left Behind: Reliable KV Cache Compression via Importance-Aware Mixed P
        28313, -- 2403.01308 VBART: The Turkish LLM
        28341, -- 2403.01774 WebCiteS: Attributed Query-Focused Summarization on Chinese Web Search Results w
        28762, -- 2403.07979 Do Agents Dream of Electric Sheep?: Improving Generalization in Reinforcement Le
        29093, -- 2403.12422 Jetfire: Efficient and Accurate Transformer Pretraining with INT8 Data Flow and
        29140, -- 2403.12961 TexTile: A Differentiable Metric for Texture Tileability
        29184, -- 2403.13372 LlamaFactory: Unified Efficient Fine-Tuning of 100+ Language Models
        29234, -- 2403.14123 AI and Memory Wall
        29302, -- 2403.14828 Multimodal-Conditioned Latent Diffusion Models for Fashion Image Editing
        29662, -- 2403.20137 Accurate Block Quantization in LLMs with Outliers
        29695, -- 2404.00399 Aurora-M: Open Source Continual Pre-training for Multilingual Language and Code
        29886, -- 2404.02731 Event Camera Demosaicing via Swin Transformer and Pixel-focus Loss
        29896, -- 2404.02837 Cherry on Top: Parameter Heterogeneity and Quantization in Large Language Models
        30203, -- 2404.07236 Lightweight Deep Learning for Resource-Constrained Environments: A Survey
        30258, -- 2404.07999 A Multi-Level Framework for Accelerating Training Transformer Models
        30726, -- 2404.15653 CatLIP: CLIP-level Visual Recognition Accuracy with 2.7x Faster Pre-training on
        30938, -- 2404.19702 GS-LRM: Large Reconstruction Model for 3D Gaussian Splatting
        31118, -- 2405.04324 Granite Code Models: A Family of Open Foundation Models for Code Intelligence
        31176, -- 2405.05945 Lumina-T2X: Transforming Text into Any Modality, Resolution, and Duration via Fl
        31346, -- 2405.10004 ROCOv2: Radiology Objects in COntext Version 2, an Updated Multimodal Image Data
        31510, -- 2405.13389 HR-INR: Continuous Space-Time Video Super-Resolution via Event Camera
        31630, -- 2405.14854 TerDiT: Ternary Diffusion Models with Transformers
        31642, -- 2405.14917 SliM-LLM: Salience-Driven Mixed-Precision Quantization for Large Language Models
        31657, -- 2405.15110 CHARP: Conversation History AwaReness Probing for Knowledge-grounded Dialogue Sy
        31839, -- 2405.17381 Various Lengths, Constant Speed: Efficient Language Modeling with Lightning Atte
        31887, -- 2405.17873 MixDQ: Memory-Efficient Few-Step Text-to-Image Diffusion Models with Metric-Deco
        31940, -- 2405.18392 Scaling Laws and Compute-Optimal Training Beyond Fixed Training Durations
        32090, -- 2405.20320 Improving the Training of Rectified Flows
        32316, -- 2406.02540 ViDiT-Q: Efficient and Accurate Quantization of Diffusion Transformers for Image
        32500, -- 2406.04820 Navigating Efficiency in MobileViT through Gaussian Process on Global Architectu
        32794, -- 2406.08334 ProTrain: Efficient LLM Training via Memory-Aware Techniques
        32846, -- 2406.08903 Delta-CoMe: Training-Free Delta-Compression with Mixed-Precision for Large Langu
        33119, -- 2406.11592 ChildDiffusion: Unlocking the Potential of Generative AI and Controllable Augmen
        33249, -- 2406.12459 HumanSplat: Generalizable Single-Image Human Gaussian Splatting with Structure P
        33305, -- 2406.13149 High-Fidelity Facial Albedo Estimation via Texture Quantization
        33377, -- 2406.14130 ExVideo: Extending Video Diffusion Models via Parameter-Efficient Post-Tuning
        33558, -- 2406.16282 Reducing Fine-Tuning Memory Overhead by Approximate and Memory-Sharing Backpropa
        33669, -- 2406.17642 Banishing LLM Hallucinations Requires Rethinking Generalization
        33766, -- 2406.18820 Universal Checkpointing: Efficient and Flexible Checkpointing for Large Scale Di
        33836, -- 2406.19759 Breaking the Script Barrier in Multilingual Pre-Trained Language Models with Tra
        33874, -- 2407.00088 T-MAC: CPU Renaissance via Table Lookup for Low-Bit LLM Deployment on Edge
        33943, -- 2407.01102 BERGEN: A Benchmarking Library for Retrieval-Augmented Generation
        34420, -- 2407.07523 SHERL: Synthesizing High Accuracy and Efficient Memory for Resource-Limited Tran
        34441, -- 2407.07852 OpenDiLoCo: An Open-Source Framework for Globally Distributed Low-Communication
        34734, -- 2407.11511 Reasoning with Large Language Models, a Survey
        34786, -- 2407.12117 MEMO: Fine-grained Tensor Management For Ultra-long Context LLM Training
        34801, -- 2407.12327 Spectra: Surprising Effectiveness of Pretraining Ternary Language Models at Scal
        34827, -- 2407.12637 Toward INT4 Fixed-Point Training via Exploring Quantization Error for Gradients
        34923, -- 2407.13690 DART-Math: Difficulty-Aware Rejection Tuning for Mathematical Problem-Solving
        35153, -- 2407.17331 Multi-label Cluster Discrimination for Visual Representation Learning
        35154, -- 2407.17353 Scalify: scale propagation for efficient low-precision LLM training
        35165, -- 2407.17465 u-$μ$P: The Unit-Scaled Maximal Update Parametrization
        35242, -- 2407.18897 Small Molecule Optimization with Large Language Models
        35327, -- 2407.20581 Knesset-DictaBERT: A Hebrew Language Model for Parliamentary Proceedings
        35438, -- 2408.00655 SentenceVAE: Enable Next-sentence Prediction for Large Language Models with Fast
        35743, -- 2408.06003 LUT Tensor Core: A Software-Hardware Co-Design for LUT-Based Low-Bit LLM Inferen
        35891, -- 2408.08554 ABQ-LLM: Arbitrary-Bit Quantized Inference Acceleration for Large Language Model
        36088, -- 2408.11743 MARLIN: Mixed-Precision Auto-Regressive Parallel Inference on Large Language Mod
        36235, -- 2408.14267 1-Bit FQT: Pushing the Limit of Fully Quantized Training to 1-bit
        36248, -- 2408.14547 Revisiting Image Captioning Training Paradigm via Direct CLIP-based Optimization
        36294, -- 2408.15300 GIFT-SW: Gaussian noise Injected Fine-Tuning of Salient Weights for LLMs
        36535, -- 2409.01990 Designing Large Foundation Models for Efficient Training and Inference: A Survey
        36651, -- 2409.04267 An overview of domain-specific foundation model: key technologies, applications
        36669, -- 2409.04833 Achieving Peak Performance for Large Language Models: A Systematic Review
        37068, -- 2409.12452 Unlocking Reasoning Potential in Large Langauge Models by Scaling Code-form Plan
        37072, -- 2409.12517 Scaling FP8 training to trillion-token LLMs
        37300, -- 2409.16626 Ascend HiFloat8 Format for Deep Learning
        37341, -- 2409.17326 How Transliterations Improve Crosslingual Alignment
        37355, -- 2409.17533 CAMOT: Camera Angle-aware Multi-Object Tracking
        37583, -- 2410.00361 PclGPT: A Large Language Model for Patronizing and Condescending Language Detect
        38112, -- 2410.06270 MC-MoE: Mixture Compressor for Mixture-of-Experts LLMs Gains More
        38126, -- 2410.06511 TorchTitan: One-stop PyTorch native solution for production ready LLM pre-traini
        38146, -- 2410.06722 Scaling Laws for Mixed quantization in Large Language Models
        38171, -- 2410.07071 Retrieval-Augmented Decision Transformer: External Memory for In-context RL
        38192, -- 2410.07170 Parameter Efficient Fine-tuning via Explained Variance Adaptation
        38583, -- 2410.12168 COMET: Towards Partical W4A4KV4 LLMs Serving
        38689, -- 2410.13267 CLaMP 2: Multimodal Music Information Retrieval Across 101 Languages Using Large
        38871, -- 2410.15352 CompAct: Compressed Activations for Memory-Efficient LLM Training
        38938, -- 2410.16239 MoRE: Multi-Modal Contrastive Pre-training with Transformers on X-Rays, ECGs, an
        39016, -- 2410.17243 Breaking the Memory Barrier: Near Infinite Batch Size Scaling for Contrastive Lo
        39172, -- 2410.19313 COAT: Compressing Optimizer states and Activation for Memory-Efficient FP8 Train
        39210, -- 2410.20011 A Survey of Small Language Models
        39354, -- 2410.22391 A Large Recurrent Action Model: xLSTM enables Fast Inference for Robotics Tasks
        39485, -- 2411.00233 SambaMixer: State of Health Prediction of Li-ion Batteries using Mamba State Spa
        39489, -- 2411.00284 SimpleFSDP: Simpler Fully Sharded Data Parallel with torch.compile
        39696, -- 2411.04036 Stepping Forward on the Last Mile
        39702, -- 2411.04125 Community Forensics: Using Thousands of Generators to Train Fake Image Detectors
        39713, -- 2411.04330 Scaling Laws for Precision
        39830, -- 2411.06084 Optimizing Large Language Models through Quantization: A Comparative Analysis of
        39838, -- 2411.06272 Golden Touchstone: A Comprehensive Bilingual Benchmark for Evaluating Financial
        40061, -- 2411.10573 Hysteresis Activation Function for Efficient Inference
        40262, -- 2411.14384 Baking Gaussian Splatting into Diffusion Denoiser for Fast and Scalable Single-s
        40410, -- 2411.16158 MixPE: Quantization and Hardware Co-design for Efficient LLM Inference
        40633, -- 2411.18700 On the Effectiveness of Incremental Training of Large Language Models
        40729, -- 2412.00071 COAP: Memory-Efficient Training with Correlation-Aware Gradient Projection
        41003, -- 2412.03599 CPTQuant -- A Novel Mixed Precision Post-Training Quantization Techniques for La
        41085, -- 2412.04468 NVILA: Efficient Frontier Visual Language Models
        41179, -- 2412.05700 Temporally Compressed 3D Gaussian Splatting for Dynamic Scenes
        41471, -- 2412.09573 FreeSplatter: Pose-free Gaussian Splatting for Sparse-view 3D Reconstruction
        41636, -- 2412.11629 QPruner: Probabilistic Decision Quantization for Structured Pruning in Large Lan
        41696, -- 2412.12091 Wonderland: Navigating 3D Scenes from a Single Image
        41867, -- 2412.14363 ResQ: Mixed-Precision Quantization of Large Language Models with Low-Rank Residu
        41883, -- 2412.14590 MixLLM: LLM Quantization with Global Mixed-precision between Output-features and
        41886, -- 2412.14628 Qua$^2$SeDiMo: Quantifiable Quantization Sensitivity of Diffusion Models
        42349, -- 2501.00365 Low-Rank Adaptation for Foundation Models: A Comprehensive Review
        42497, -- 2501.02625 HALO: Hadamard-Assisted Lower-Precision Optimization for LLMs
        42612, -- 2501.04473 When LLMs Struggle: Reference-less Translation Evaluation for Low-resource Langu
        42748, -- 2501.06589 Ladder-residual: parallelism-aware architecture for accelerating large model inf
        42894, -- 2501.09194 Grounding Text-To-Image Diffusion Models For Controlled High-Quality Image Gener
        43110, -- 2501.12956 GANQ: GPU-Adaptive Non-Uniform Quantization for Large Language Models
        43402, -- 2501.18154 Mixed-Precision Graph Neural Quantization for Low Bit Large Language Models
        43555, -- 2502.01199 Nearly Lossless Adaptive Bit Switching
        43898, -- 2502.05967 $μ$nit Scaling: Simple and Scalable FP8 LLM Training
        44211, -- 2502.10362 CLaMP 3: Universal Music Information Retrieval Across Unaligned   Modalities and
        44356, -- 2502.11656 Uncovering the Impact of Chain-of-Thought Reasoning for Direct Preference Optimi
        44380, -- 2502.11880 Bitnet.cpp: Efficient Edge Inference for Ternary LLMs
        44432, -- 2502.12171 GoRA: Gradient-driven Adaptive Low Rank Adaptation
        44649, -- 2502.14462 Single-image Reflectance and Transmittance Estimation from Any Flatbed Scanner
        44731, -- 2502.15075 More for Keys, Less for Values: Adaptive KV Cache Quantization
        44840, -- 2502.16457 Towards Fully-Automated Materials Discovery via Large-Scale Synthesis Dataset an
        44903, -- 2502.17055 Stable-SPAM: How to Train in 4-Bit More Stably than 16-Bit Adam
        45474, -- 2503.03285 Enhancing Vietnamese VQA through Curriculum Learning on Raw and Augmented Text R
        46180, -- 2503.12127 Hyperbolic Safety-Aware Vision-Language Models
        46212, -- 2503.12668 ZO2: Scalable Zeroth-Order Fine-Tuning for Extremely Large Language Models with
        46275, -- 2503.13551 Towards Hierarchical Multi-Step Reward Models for Enhanced Reasoning in Large La
        46470, -- 2503.16257 Plug-and-Play 1.x-Bit KV Cache Quantization for Video Large Language Models
        46953, -- 2503.22698 Fragile Mastery: Are Domain-Specific Trade-Offs Undermining On-Device Language M
        47225, -- 2504.02438 Scaling Video-Language Models to 10K Frames via Hierarchical Differential Distil
        47505, -- 2504.07835 Pychop: Emulating Low-Precision Arithmetic in Numerical Methods and Neural Netwo
        48050, -- 2504.16026 Trends in AI Supercomputers
        48326, -- 2505.01043 Low-Precision Training of Large Language Models: Methods, Challenges,   and Oppo
        48647, -- 2505.07675 Simple Semi-supervised Knowledge Distillation from Vision-Language Models via $\
        49154, -- 2505.14302 Scaling Law for Quantization-Aware Training
        49746, -- 2505.19529 Small Language Models: Architectures, Techniques, Evaluation, Problems and Futur
        50515, -- 2506.03523 TokAlign: Efficient Vocabulary Adaptation via Token Alignment
        50887, -- 2506.08915 Inherently Faithful Attention Maps for Vision Transformers
        51203, -- 2506.14285 From What to Respond to When to Respond: Timely Response Generation for Open-dom
        51392, -- 2506.18890 4D-LRM: Large Space-Time Reconstruction Model From and To Any View at Any Time
        51539, -- 2506.21724 Asymmetric Dual Self-Distillation for 3D Self-Supervised Representation Learning
        52167, -- 2508.01630 OpenMed NER: Open-Source, Domain-Adapted State-of-the-Art Transformers   for Bio
        52846, -- 2509.13523 AERIS: Argonne Earth Systems Model for Reliable and Skillful Predictions
        53255, -- 2510.03434 Paris: A Decentralized Trained Open-Weight Diffusion Model
        53389, -- 2510.08008 Recycling Pretrained Checkpoints: Orthogonal Growth of   Mixture-of-Experts for
        53792, -- 2510.19944 Seed3D 1.0: From Images to High-Fidelity Simulation-Ready 3D Assets
        53889, -- 2510.21978 Beyond Reasoning Gains: Mitigating General Capabilities Forgetting in   Large Re
        53992, -- 2510.26788 Defeating the Training-Inference Mismatch via FP16
        54269, -- 2511.15038 Aligning Generative Music AI with Human Preferences: Methods and Challenges
        54438, -- 2511.16854 MRI Super-Resolution with Deep Learning: A Comprehensive Survey
        54472, -- 2512.01103 Learning Eigenstructures of Unstructured Data Manifolds
        54577, -- 2512.04746 SignRoundV2: Closing the Performance Gap in Extremely Low-Bit Post-Training Quan
        55048, -- 2512.24551 PhyGDPO: Physics-Aware Groupwise Direct Preference Optimization for Physically C
        55157, -- 2601.04890 Learnable Multipliers: Freeing the Scale of Language Model Matrix Layers
        55180, -- 2601.04575 Scaling Behavior Cloning Improves Causal Reasoning: An Open Model for Real-Time
        55599, -- 2601.22101 ECO: Quantized Training without Full-Precision Master Weights
        55865, -- 2602.06079 Canzona: A Unified, Asynchronous, and Load-Balanced Framework for Distributed Ma
        56075, -- 2602.11541 Budget-Constrained Agentic Large Language Models: Intention-Based Planning for C
        56081, -- 2602.11543 Pretraining A Large Language Model using Distributed GPUs: A Memory-Efficient De
        56255, -- 2602.20160 tttLRM: Test-Time Training for Long Context and Autoregressive 3D Reconstruction
        56844, -- 2603.17891 RAMP: Reinforcement Adaptive Mixed Precision Quantization for Efficient On Devic
        57016, -- 2603.18742 6Bit-Diffusion: Inference-Time Mixed-Precision Quantization for Video Diffusion
        57280, -- 2604.05091 MegaTrain: Full Precision Training of 100B+ Parameter Large Language Models on a
        57445, -- 2604.11152 SHARE: Social-Humanities AI for Research and Education
        57810, -- 2604.27085 Efficient Training on Multiple Consumer GPUs with RoundPipe
        57946, -- 2603.07819 Fusion Complexity Inversion: Why Simpler Cross View Modules Outperform SSMs and
        57981, -- 2604.20079 On the Quantization Robustness of Diffusion Language Models in Coding Benchmarks
        57983, -- 2604.19351 DASH-KV: Accelerating Long-Context LLM Inference via Asymmetric KV Cache Hashing
        58136, -- 2604.15416 StoSignSGD: Unbiased Structural Stochasticity Fixes SignSGD for Training Large L
        58263, -- 2604.11572 DA-PTQ: Drift-Aware Post-Training Quantization for Efficient Vision-Language-Act
        58369, -- 2604.18603 Dual Triangle Attention: Effective Bidirectional Attention Without Positional Em
        58595, -- 2604.02525 AdaHOP: Fast and Accurate Low-Precision Training via Outlier-Pattern-Aware Rotat
        58605, -- 2604.02149 AEGIS: Adversarial Entropy-Guided Immune System -- Thermodynamic State Space Mod
        59167, -- 2603.19172 DyMoE: Dynamic Expert Orchestration with Mixed-Precision Quantization for Effici
        59288, -- 2603.16428 An Efficient Heterogeneous Co-Design for Fine-Tuning on a Single GPU
        59305, -- 2603.15953 A Family of LLMs Liberated from Static Vocabularies
        59401, -- 2603.14360 M^2RNN: Non-Linear RNNs with Matrix-Valued States for Scalable Language Modeling
        59426, -- 2603.13972 FLUX: Data Worth Training On
        59795, -- 2603.06060 Limited-Precision Stochastic Rounding
        59868, -- 2603.08747 Diagnosing FP4 inference: a layer-wise and block-wise sensitivity analysis of NV
        60336, -- 2602.21371 Interleaved Head Attention
        60831, -- 2602.10959 Rotary Positional Embeddings as Phase Modulation: Theoretical Bounds on the RoPE
        61074, -- 2602.06932 When RL Meets Adaptive Speculative Training: A Unified Training-Serving System
        61288, -- 2602.04926 Pruning Minimal Reasoning Graphs for Efficient Retrieval-Augmented Generation
        61332, -- 2602.03537 MatGPTQ: Accurate and Efficient Post-Training Matryoshka Quantization
        61961, -- 2601.19739 TokenSeek: Memory Efficient Fine Tuning via Instance-Aware Token Ditching
        62164, -- 2601.16956 DataStates-LLM: Scalable Checkpointing for Transformer Models Using Composable S
        62617, -- 2601.07475 ARCQuant: Boosting NVFP4 Quantization with Augmented Residual Channels for LLMs
        62805, -- 2601.06199 FastSLM: Hierarchical Frame Q-Former for Effective Speech Modality Adaptation
        62983, -- 2601.02311 Placement Semantics for Distributed Deep Learning: A Systematic Framework for An
        63190, -- 2512.24157 Training Report of TeleChat3-MoE
        63329, -- 2512.21276 GriDiT: Factorized Grid-Based Diffusion for Efficient Long Image Sequence Genera
        63384, -- 2512.20563 LEAD: Minimizing Learner-Expert Asymmetry in End-to-End Driving
        63479, -- 2512.18318 Asynchronous Pipeline Parallelism for Real-Time Multilingual Lip Synchronization
        63988, -- 2512.07338 Generalized Referring Expression Segmentation on Aerial Photos
        64643, -- 2511.18674 Low-Rank GEMM: Efficient Matrix Multiplication via Low-Rank Approximation with F
        64704, -- 2511.18054 Blu-WERP (Web Extraction and Refinement Pipeline): A Scalable Pipeline for Prepr
        65189, -- 2511.07903 DynaQuant: Dynamic Mixed-Precision Quantization for Learned Image Compression
        65247, -- 2511.06694 ML-EcoLyzer: Quantifying the Environmental Cost of Machine Learning Inference Ac
        65361, -- 2511.04002 Memory- and Latency-Constrained Inference of Large Language Models via Adaptive
        65648, -- 2510.26104 OneTrans: Unified Feature Interaction and Sequence Modeling with One Transformer
        65772, -- 2510.23926 Improving the Straight-Through Estimator with Zeroth-Order Information
        66072, -- 2510.19006 XGen-Q: An Explainable Domain-Adaptive LLM Framework with Retrieval-Augmented Ge
        66195, -- 2510.16805 Mixed-Precision Quantization for Language Models: Techniques and Prospects
        66200, -- 2510.16774 Learning to play: A Multimodal Agent for 3D Game-Play
        66252, -- 2510.15530 VO-DP: Semantic-Geometric Adaptive Diffusion Policy for Vision-Only   Robotic Ma
        66525, -- 2510.10962 MC#: Mixture Compressor for Mixture-of-Experts Large Models
        66580, -- 2510.10248 Reasoning-Enhanced Large Language Models for Molecular Property Prediction
        66886, -- 2510.05827 VCoT-Grasp: Grasp Foundation Models with Visual Chain-of-Thought   Reasoning for
        66978, -- 2510.04202 Spectral Alignment as Predictor of Loss Explosion in Neural Network   Training
        67363, -- 2509.25689 Collaborative Compression for Large-Scale MoE Deployment on Edge
        67372, -- 2509.25591 Building the EHR Foundation Model via Next Event Prediction
        67518, -- 2410.09734 Gradient-Free Training of Quantized Neural Networks
        67545, -- 2509.23809 Tequila: Trapping-free Ternary Quantization for Large Language Models
        67639, -- 2509.22935 Compute-Optimal Quantization-Aware Training
        67665, -- 2509.22536 InfiR2: A Comprehensive FP8 Training Recipe for Reasoning-Enhanced   Language Mo
        67826, -- 2509.20883 RecIS: Sparse to Dense, A Unified Training Framework for Recommendation Models
        68009, -- 2509.17791 Elucidating the Design Space of FP4 training
        68055, -- 2509.16989 PTQTP: Post-Training Quantization to Trit-Planes for Large Language   Models
        68370, -- 2509.12019 AMQ: Enabling AutoML for Mixed-precision Weight-Only Quantization of   Large Lan
        69356, -- 2508.15601 Efficient Mixed-Precision Large Language Model Inference with TurboMind
        69518, -- 2508.13049 XR-NPE: High-Throughput Mixed-precision SIMD Neural Processing Engine   for Exte
        69792, -- 2508.09071 GeoVLA: Empowering 3D Representations in Vision-Language-Action Models
        70278, -- 2508.02322 CAMERA: Multi-Matrix Joint Compression for MoE Models via Micro-Expert   Redunda
        70319, -- 2508.01918 Quantum-RAG and PunGPT2: Advancing Low-Resource Language Generation and   Retrie
        71190, -- 2507.09616 MLoRQ: Bridging Low-Rank and Quantization for Transformer Compression
        71542, -- 2507.01154 FlashDP: Private Training Large Language Models with Efficient DP-SGD
        71761, -- 2506.19187 Prompt, Translate, Fine-Tune, Re-Initialize, or Instruction-Tune?   Adapting LLM
        71904, -- 2506.15266 Thunder-DeID: Accurate and Efficient De-identification Framework for   Korean Co
        72326, -- 2506.02939 QKV Projections Require a Fraction of Their Memory
        72550, -- 2505.23254 MemAscend: System Memory Optimization for SSD-Offloaded LLM Fine-Tuning
        72679, -- 2505.21567 EaqVLA: Encoding-aligned Quantization for Vision-Language-Action Models
        72889, -- 2505.15559 Moonbeam: A MIDI Foundation Model Using Both Absolute and Relative Music Attribu
        73130, -- 2505.05799 MxMoE: Mixed-precision Quantization for MoE with Accuracy and Performance Co-Des
        73241, -- 2504.21553 Precision Where It Matters: A Novel Spike Aware Mixed-Precision Quantization Str
        74119, -- 2503.10017 Speedy MASt3R
        74507, -- 2503.00022 KVCrush: Key value cache size-reduction using similarity in   head-behaviour
        74633, -- 2502.12346 QuZO: Quantized Zeroth-Order Fine-Tuning for Large Language Models
        74635, -- 2502.12340 Understanding Silent Data Corruption in LLM Training
        74719, -- 2502.08939 TokenSynth: A Token-based Neural Synthesizer for Instrument Cloning and   Text-t
        74868, -- 2502.04420 KVTuner: Sensitivity-Aware Layer-Wise Mixed-Precision KV Cache Quantization for
        74917, -- 2502.02581 Hecate: Unlocking Efficient Sparse Model Training via Fully Sharded   Sparse Dat
        75352, -- 2412.19351 ETTA: Elucidating the Design Space of Text-to-Audio Models
        75393, -- 2412.15832 AIFS-CRPS: Ensemble forecasting using a model trained with a loss   function bas
        75882, -- 2411.01433 HOBBIT: A Mixed Precision Expert Offloading System for Fast MoE   Inference
        75886, -- 2411.01075 Cephalo: Harnessing Heterogeneous GPU Clusters for Training Transformer   Models
        75912, -- 2410.23261 $100K or 100 Days: Trade-offs when Pre-Training with Academic Resources
        76928, -- 2406.14969 Uni-Mol2: Exploring Molecular Pretraining Model at Scale
        77024, -- 2406.08155 QuantMoE-Bench: Examining Post-Training Quantization for   Mixture-of-Experts
        77104, -- 2406.01465 AIFS -- ECMWF's data-driven forecasting system
        77300, -- 2405.06001 LLMC: Benchmarking Large Language Model Quantization with a Versatile Compressio
        77440, -- 2404.09216 DetCLIPv3: Towards Versatile Generative Open-vocabulary Object Detection
        77480, -- 2404.08001 Xiwu: A Basis Flexible and Learnable LLM for High Energy Physics
        77989, -- 2401.03755 Mixed Precision FGMRES-Based Iterative Refinement for Weighted Least Squares
        78187, -- 2311.17241 End-to-End Temporal Action Detection with 1B Parameters Across 1000 Frames
        78594, -- 2308.16258 Robust Principles: Architectural Design Principles for Adversarially   Robust CN
        78599, -- 2308.15762 Hanayo: Harnessing Wave-like Pipeline Parallelism for Enhanced Large   Model Tra
        78652, -- 2109.12894 Training Spiking Neural Networks Using Lessons From Deep Learning
        78971, -- 2305.17455 CrossGET: Cross-Guided Ensemble of Tokens for Accelerating   Vision-Language Tra
        79185, -- 2303.17561 SoftCLIP: Softer Cross-modal Alignment Makes CLIP Stronger
        79333, -- 2302.12510 DyBit: Dynamic Bit-Precision Numbers for Efficient Quantized Neural Network Infe
        79387, -- 2302.01382 Mixed Precision Post Training Quantization of Neural Networks with Sensitivity G
        79534, -- 2211.13929 XKD: Cross-modal Knowledge Distillation with Domain Alignment for Video Represen
        79873, -- 2206.13689 Tiny-Sepformer: A Tiny Time-Domain Transformer Network for Speech   Separation
        79923, -- 2206.02874 Dissecting Tensor Cores via Microbenchmarks: Latency, Throughput and   Numeric B
        79979, -- 2205.07134 ETAD: Training Action Detection End to End on a Laptop
        80028, -- 2204.14095 PyramidCLIP: Hierarchical Feature Alignment for Vision-language Model   Pretrain
        80745, -- 2104.15076 Climate Modelling in Low-Precision: Effects of both Deterministic &   Stochastic
        80886, -- 2102.05426 BRECQ: Pushing the Limit of Post-Training Quantization by Block Reconstruction
        80892, -- 2102.04159 Deep Residual Learning in Spiking Neural Networks
        80898, -- 2102.01963 Local Critic Training for Model-Parallel Learning of Deep Neural Networks
        81558, -- 1910.10261 QuartzNet: Deep Automatic Speech Recognition with 1D Time-Channel   Separable Co
        83726, -- 2605.27605 Laguna M.1/XS.2 Technical Report
        83744, -- 2605.23081 ThriftAttention: Selective Mixed Precision for Long-Context FP4 Attention
        83955, -- 2605.24786 CONF-KV: Confidence-Aware KV Cache Eviction with Mixed-Precision Storage for Lon
        84234, -- 2511.19221 Percept-WAM: Perception-Enhanced World-Awareness-Action Model for Robust End-to-
        84625, -- 2602.22625 DiffBMP: Differentiable Rendering with Bitmap Primitives
        85365, -- 2604.12391 Chain-of-Models Pre-Training: Rethinking Training Acceleration of Vision Foundat
        85650, -- 2605.30409 SANA-Streaming: Real-time Streaming Video Editing with Hybrid Diffusion Transfor
        86184, -- 2506.24125 FADRM: Fast and Accurate Data Residual Matching for Dataset Distillation
        86348, -- 2506.06472 Cost-Efficient LLM Training with Lifetime-Aware Tensor Offloading via GPUDirect
        86668, -- 2506.06470 SIGMA: Refining Large Language Model Reasoning via Sibling-Guided Monte Carlo Au
        87046, -- 2503.03961 A Little Depth Goes a Long Way: The Expressive Power of Log-Depth Transformers
        87471, -- 2508.00887 FRAM:  Frobenius-Regularized Assignment Matching with Mixed-Precision Computing
        87609, -- 2506.23674 Partial Forward Blocking: A Novel Data Pruning Paradigm for Lossless Training Ac
        87727, -- 2507.22349 MSQ: Memory-Efficient Bit Sparsification Quantization
        87827, -- 2503.10959 OuroMamba: A Data-Free Quantization Framework for Vision Mamba
        87856, -- 2505.00702 RayZer: A Self-supervised Large View Synthesis Model
        88518, -- 2410.13195 UniGS: Modeling Unitary 3D Gaussians for Novel View Synthesis from Sparse-view I
        88712, -- 2505.07715 Hybrid Spiking Vision Transformer for Object Detection with Event Cameras
        89054, -- 2507.05508 Beyond Communication Overhead: A Multilevel Monte Carlo Approach for Mitigating
        89161, -- 2412.04180 SKIM: Any-bit Quantization Pushing The Limits of Post-Training Quantization
        89228, -- 2502.20853 Oscillation-Reduced MXFP4 Training for Vision Transformers
        89761, -- 2505.04877 Learning from Loss Landscape: Generalizable Mixed-Precision Quantization via Ada
        92168, -- 2410.13461 Progressive Mixed-Precision Decoding for Efficient LLM Inference
        92331, -- 2502.11729 On Quantizing Neural Representation for Variable-Rate Video Coding
        92436, -- 2405.20935 Effective Interplay between Sparsity and Quantization: From Theory to Practice
        92652, -- 2604.06515 Efficient Quantization of Mixture-of-Experts with Theoretical Generalization Gua
        93283, -- 2510.26771 STaMP: Sequence Transformation and Mixed Precision for Low-Precision Activation
        93379, -- 2603.18426 Prune-then-Quantize or Quantize-then-Prune? Understanding the Impact of Compress
        93661, -- 2505.06653 Improving Block-Wise LLM Quantization by 4-bit Block-Wise Optimal Float (BOF4):
        94140, -- 2511.05811 MOSS: Efficient and Accurate FP8 LLM Training with Microscaling and Automatic Sc
        94222, -- 2505.18610 PM-KVQ: Progressive Mixed-precision KV Cache Quantization for Long-CoT LLMs
        94447, -- 2506.04398 Bridging the performance-gap between target-free and target-based reinforcement
        94517, -- 2508.02343 MicroMix: Efficient Mixed-Precision Quantization with Microscaling Formats for L
        94864, -- 2510.03274 Quant-dLLM: Post-Training Extreme Low-Bit Quantization for Diffusion Large Langu
        94924, -- 2509.22626 Learning Admissible Heuristics for A*:  Theory and Practice
        95130, -- 2605.31124 QVGGT: Post-Training Quantized Visual Geometry Grounded Transformer
        95493, -- external RoboPrec: Enabling Reliable Embedded Computing for Robotics by Providing Accurac
        97220, -- 2603.01850 Tiny-DroNeRF: Tiny Neural Radiance Fields Aboard Federated Learning-Enabled Nano
        97300, -- 2509.26581 Graphite: A GPU-Accelerated Mixed-Precision Graph Optimization Framework
        98055, -- 2606.08327 Chiaroscuro Attention: Spending Compute in the Dark
        98420, -- 2606.16993 DreamX-World 1.0: A General-Purpose Interactive World Model
        98684, -- 2606.20097 HydraHead: From Head-Level Functional Heterogeneity to Specialized Attention Hyb
        98902, -- 2304.04514 DetCLIPv2: Scalable Open-Vocabulary Object Detection Pre-training via Word-Regio
        99139, -- 2506.17768 Log-Normal Multiplicative Dynamics for Stable Low-Precision Deep Learning
        100097, -- 2606.13054 TWLA: Achieving Ternary Weights and Low-Bit Activations for LLMs via Post-Traini
        100310, -- 2510.27527 TetraJet-v2: Accurate NVFP4 Training for Large Language Models with Oscillation
        100322, -- 2604.03582 Simple yet Effective: Low-Rank Spatial Attention for Neural Operators
        100432, -- 2605.23078 GEMQ: Global Expert-Level Mixed-Precision Quantization for MoE LLMs
        100759, -- 2606.12913 Selecting Samples on Graphs: A Unified Dataset Pruning Framework for Lossless Tr
        100801, -- 2602.19017 Why ReLU? A Bit-Model Dichotomy for Deep Network Training
        101446, -- 2505.19342 ASTRA: Communication-Efficient Acceleration for Multi-Device Transformer Inferen
        101510, -- 2602.22268 AutoQRA: Joint Optimization of Mixed-Precision Quantization and Low-rank Adapter
        101849, -- 2602.00392 Localized, High-resolution Geographic Representations with Slepian Functions
        102312, -- 2606.08382 STAR-KV: Low-Rank KV Cache Compression via Soft Thresholding for Adaptive Rank C
        102883, -- 2512.19206 MixKVQ: Query-Aware Mixed-Precision KV Cache Quantization for Long-Context Reaso
        103526, -- 2604.10502 CHAIRO: Contextual Hierarchical Analogical Induction and Reasoning Optimization
        103608, -- 2604.05942 BOSCH: Black-Box Binary Optimization for Short-Context Attention-Head Selection
        103828, -- 2607.07964 KronQ: LLM Quantization via Kronecker-Factored Hessian
        103830, -- 2606.07383 RhinoVLA Technical Report
        104007, -- 2607.12395 Ring-Zero: Scaling Zero RL to a Trillion Parameters for Emergent Reasoning
        104458, -- 2607.19058 Where Should Optimizer State Live? Tiered State Allocation for Memory-Efficient
        104558, -- 2607.10495 NanoVSR: Towards Real-Time Video Super-Resolution on Edge Devices
        104725, -- 2306.09818 HiNeRV: Video Compression with Hierarchical Encoding-based Neural Representation
        106428, -- 2506.08018 KVmix: Gradient-Based Layer Importance-Aware Mixed-Precision Quantization for KV
        106603, -- 2508.09176 DQT: Dynamic Quantization Training via Dequantization-Free Nested Integer Arithm
        107513, -- 2511.06925 DTTNet: Improving Video Shadow Detection via Dark-Aware Guidance and Tokenized T
        107603, -- 2511.10004 LampQ: Towards Accurate Layer-wise Mixed Precision Quantization for Vision Trans
        107629, -- 2605.04058 MP-ISMoE: Mixed-Precision Interactive Side Mixture-of-Experts for Efficient Tran
        107750, -- 2508.04753 InfoQ: Mixed-Precision Quantization via Global Information Flow
        108008, -- 2602.12609 QuEPT: Quantized Elastic Precision Transformers with One-Shot Calibration for Mu
        108853, -- 2605.04062 EdgeRazor: A Lightweight Framework for Large Language Models via Mixed-Precision
        109652, -- 2608.17336 TileMix: Tile-Centric Mixed-Precision Attention for LLM Inference Acceleration
        110007, -- 2508.18387 Integral Transformer: Denoising Attention, Not Too Much Not Too Little
        110909, -- 2503.11023 Beyond A Single AI Cluster: A Survey of Decentralized LLM Training
        111344, -- 2506.22001 WTFormer: A Wavelet Conformer Network for MIMO Speech Enhancement with Spatial C
        111480, -- external Ultra-Low Bit Post-Training Quantization of Large Speech Models via K-Means Clus
        112463, -- 2305.15078 "UniINR: Event-guided Unified Rolling Shutter Correction, Deblurring, and Interp
        113371, -- 2407.05266 CLAMP-ViT: Contrastive Data-Free Learning for Adaptive Post-Training Quantizatio
        115544, -- 2404.00834 Towards Robust Event-guided Low-Light Image Enhancement: A Large-Scale Real-Worl
        116343, -- external JointSQ: Joint Sparsification-Quantization for Distributed Learning
        116534, -- 2403.05005 DITTO: Dual and Integrated Latent Topologies for Implicit 3D Reconstruction
        116605, -- 2401.04105 Dr2Net: Dynamic Reversible Dual-Residual Networks for Memory-Efficient Finetunin
        116978, -- 2401.01543 Retraining-Free Model Quantization via One-Shot Weight-Coupling Learning
        117104, -- 2311.18129 Mixed-Precision Quantization for Federated Learning on Resource-Constrained Hete
        117326, -- 2503.18083 Unified Geometry and Color Compression Framework for Point Clouds via Generative
        117617, -- 2604.01204 Neural Harmonic Textures for High-Quality Primitive Based Neural Reconstruction
        119392, -- 2607.02584 RotateAttention : RoPE-Aware Rotation and Range Rectification for INT4 Quantized
        119531, -- 2602.16249 AFFMAE: Scalable Vision Pre-Training for High-Resolution Microscopy Segmentation
        119698, -- 2605.29662 SAFE-Pruner: Semantic Attention–Guided Future-Aware Token Pruning for Efficient
        120362, -- 2307.16375 UniAP: Unifying Inter- and Intra-Layer Automatic Parallelism by Mixed Integer Qu
        121113, -- external Gradient Knows Best: Mixed-Precision Quantization via Gradient-Guided Bit Alloca
        122038, -- 2111.09957 Rethinking Dilated Convolution for Real-time Semantic Segmentation
        122286, -- 2609.36314 Fractional State Space Transition for Long Sequence Modeling
        122513, -- 2609.34162 SlideDP: Scaling Host-Resident LLM Fine-Tuning Across Multiple GPUs
        122612, -- 2609.39627 Introduction to Computer Vision
        122767, -- 2610.03978 Learning Latent Protein Languages for Autoregressive Generation
        123537, -- 2610.19605 PN-Mix: Pair-Norm Guided Mixed-Precision Key Cache Quantization for Efficient Lo
        123587, -- 2610.22276 MJev-Spatial: System One Spatial Intelligence via Native Attention Matching
        124690, -- external InQuant: In-Place Mixed-Precision KV Cache Quantization via Saliency-Aware Neigh
        125128, -- external BMAttn: Block-Aligned Mixed-Precision Attention Quantization for LLM Inference
        125817, -- 2606.00289 Inner Product Aware Quantization: Provably Fast, Accurate, and Adaptive Algorith
        126257, -- external Iterative ILP with Update-Size Control for Reducing Surrogate-Task Mismatch in B
        126321, -- 2605.17913 A Differentiable Interior-Point Method in Single Precision
        126619, -- 2605.17170 TriAxialKV: Toward Extreme Low-Precision KV-Cache Quantization for Agentic Infer
        127218, -- external AdaKVQ: Adaptive Mixed-Precision KV Cache Quantization For Efficient Reasoning M
        127633, -- 2601.21623 LAMP: Look-Ahead Mixed-Precision Inference of Large Language Models
        127865, -- 2605.24011 ActQuant: Sub-4-bit Action-Guided Quantization for Vision-Language-Action Models
        128470, -- 2606.04980 AlphaQ: Calibration-Free Bit Allocation for Mixture-of-Experts Quantization
        128498, -- 2510.04066 QuantDemoire: Quantization with Outlier Aware for Image Demoiréing
        128729, -- external KV Cache Compression via Attention Output Distortion Minimization
        129384, -- 2604.18117 LoRaQ: Optimized Low Rank Approximation for 4-bit Quantization
        129456, -- external ACQueReLlo: Alignment-Aware Constrained Quantization via Reinforcement Learning
        129472, -- 2606.23419 GRINQH: Graded Input-based Quantization Hierarchy for Efficient LLM Generation
        130597, -- 2602.10718 SnapMLA: Efficient Long-Context MLA Decoding via Hardware-Aware FP8 Quantized Pi
        130632, -- 2602.02400 An Empirical Study on Noisy Data and LLM Pretraining Loss Divergence
        130933, -- 2605.19403 TIDE: Asymmetric Neural Circuits for Stabilized Temporal Inhibitory-Excitatory D
        131098, -- 2605.16732 DiRotQ: Rotation-Aware Quantization for 4-bit Diffusion Transformers
        131148, -- 2609.32922 Precision As You Need: Stochastic Computing Is a Dense Adaptive Quantizer
        131155, -- 2602.17698 ScaleBITS: Scalable Bitwidth Search for Hardware-Aligned Mixed-Precision LLMs
        131247, -- 2602.10378 Flash-SD-KDE: Accelerating SD-KDE with Tensor Cores
        131605  -- 2610.21143 CoSTA: Compressed Speech Token Adaptation for Efficient Spoken Dialogue Models
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
        2561, -- 1909.08053 Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parall
        5408, -- 2104.04473 Efficient Large-Scale Language Model Training on GPU Clusters Using Megatron-LM
        5792, -- 2105.13120 Sequence Parallelism: Long Sequence Training from System Perspective
        7196, -- 2111.05972 Amazon SageMaker Model Parallelism: A General and Flexible Framework for Large M
        8992, -- 2205.05198 Reducing Activation Recomputation in Large Transformer Models
        10222, -- 2209.02341 EnergonAI: An Inference System for 10-100 Billion Parameter Transformer Models
        14891, -- 2304.11414 Pipeline MoE: A Flexible MoE Implementation with Pipeline Parallelism
        15954, -- 2305.13484 Flover: A Temporal Fusion Framework for Efficient Autoregressive Model Parallel
        22522, -- 2310.16355 RedCoast: A Lightweight Tool to Automate Distributed Training of LLMs on Any GPU
        22996, -- 2311.03285 S-LoRA: Serving Thousands of Concurrent LoRA Adapters
        25023, -- 2312.12705 Optimizing Distributed Training on Frontier for Large Language Models
        26460, -- 2401.16677 T3: Transparent Tracking & Triggering for Fine-grained Overlap of Compute & Coll
        26998, -- 2402.04925 TP-Aware Dequantization
        35847, -- 2408.07802 Kraken: Inherently Parallel Transformers For Efficient Multi-Device Inference
        36980, -- 2409.11155 ISO: Overlap of Computation and Communication within Seqenence For LLM Inference
        37594, -- 2410.00531 TPI-LLM: Serving 70B-scale LLMs Efficiently on Low-resource Edge Devices
        42748, -- 2501.06589 Ladder-residual: parallelism-aware architecture for accelerating large model inf
        43660, -- 2502.02493 EasySpec: Layer-Parallel Speculative Decoding for Efficient Multi-GPU Utilizatio
        45415, -- 2503.02495 Union of Experts: Adapting Hierarchical Routing to Equivalently Decomposed Trans
        45539, -- 2503.04398 Speculative MoE: Communication Efficient Parallel MoE Inference with Speculative
        52470, -- 2508.15881 TPLA: Tensor Parallel Latent Attention for Efficient Disaggregated   Prefill and
        55865, -- 2602.06079 Canzona: A Unified, Asynchronous, and Load-Balanced Framework for Distributed Ma
        56612, -- 2603.02188 Multi-Head Low-Rank Attention
        56798, -- 2603.15854 FlashSampling: Fast and Memory-Efficient Exact Sampling
        62983, -- 2601.02311 Placement Semantics for Distributed Deep Learning: A Systematic Framework for An
        65095, -- 2511.09557 LLM Inference Beyond a Single Node: From Bottlenecks to Mitigations with Fast Al
        73426, -- 2504.14960 MoE Parallel Folding: Heterogeneous Parallelism Mappings for Efficient   Large-S
        77222, -- 2405.14430 PipeFusion: Patch-level Pipeline Parallelism for Diffusion Transformers Inferenc
        83310, -- 2605.15250 GQLA: Group-Query Latent Attention for Hardware-Adaptive Large Language Model De
        86294, -- 2506.19645 Tensor-Parallelism with Partially Synchronized Activations
        89335, -- 2502.20727 SPD: Sync-Point Drop for Efficient Tensor Parallelism of Large Language Models
        92869, -- 2510.16981 MuonBP: Faster Muon via Block-Periodic Orthogonalization
        101402, -- 2511.17826 Deterministic Inference across Tensor Parallel Sizes That Eliminates Training-In
        122097, -- 2609.19169 SiliconBench: Speed, Memory, and Fidelity for LLM Serving on Unified-Memory Desk
        125629  -- external In STeP: Speculative Tensor Parallelism for Concurrent Heterogeneous Inference o
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
        20910, -- 2309.14509 DeepSpeed Ulysses: System Optimizations for Enabling Training of Extreme Long Se
        35978, -- 2408.10188 LongVILA: Scaling Long-Context Visual Language Models for Long Videos
        60159, -- 2603.10031 Architecture-Aware LLM Inference Optimization on AMD Instinct GPUs: A Comprehens
        82916, -- 2605.06221 UniPrefill: Universal Long-Context Prefill Acceleration via Block-wise Dynamic S
        83108, -- 2605.13779 MinT: Managed Infrastructure for Training and Serving Millions of LLMs
        112213, -- 2505.22313 Large-Area Fabrication-aware Computational Diffractive Optics
        122321, -- 2609.32712 MassAlloc Attention: Let Attention Allocate Its Own Compute
        122323, -- 2609.32704 CoWindow Attention: Full Causal Coverage Is a Collective Property
        126620  -- 2605.06113 Tackling the Data-Parallel Load Balancing Bottleneck in LLM Serving: Practical O
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
        1627, -- 1811.06965 GPipe: Efficient Training of Giant Neural Networks using Pipeline Parallelism
        2561, -- 1909.08053 Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parall
        3258, -- 2003.11666 Pipelined Backpropagation at Scale: Training Large Models without Batches
        5408, -- 2104.04473 Efficient Large-Scale Language Model Training on GPU Clusters Using Megatron-LM
        5578, -- 2104.12369 PanGu-$α$: Large-scale Autoregressive Pretrained Chinese Language Models with Au
        5882, -- 2106.02679 Layered gradient accumulation and modular pipeline parallelism: fast and efficie
        7079, -- 2110.15032 OneFlow: Redesign the Distributed Deep Learning Framework from Scratch
        7196, -- 2111.05972 Amazon SageMaker Model Parallelism: A General and Flexible Framework for Large M
        10222, -- 2209.02341 EnergonAI: An Inference System for 10-100 Billion Parameter Transformer Models
        11300, -- 2211.05953 Breadth-First Pipeline Parallelism
        14891, -- 2304.11414 Pipeline MoE: A Flexible MoE Implementation with Pipeline Parallelism
        19480, -- 2308.10087 GNNPipe: Scaling Deep GNN Training with Pipelined Model Parallelism
        19957, -- 2308.16369 SARATHI: Efficient LLM Inference by Piggybacking Decodes with Chunked Prefills
        23661, -- 2311.13381 Confidant: Customizing Transformer-based LLMs via Collaborative Edge Training
        23804, -- 2311.15786 YUAN 2.0: A Large Language Model with Localized Filtering-based Attention
        24356, -- 2312.03549 Holmes: Towards Distributed Training Across Clusters with Heterogeneous NIC Envi
        24493, -- 2312.04916 EE-LLM: Large-Scale Training and Inference of Early-Exit Large Language Models w
        25023, -- 2312.12705 Optimizing Distributed Training on Frontier for Large Language Models
        26013, -- 2401.10241 Zero Bubble Pipeline Parallelism
        28381, -- 2403.02310 Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve
        31244, -- 2405.07719 USP: A Unified Sequence Parallelism Approach for Long Context Generative AI
        31684, -- 2405.15362 Pipeline Parallelism with Controllable Memory
        31906, -- 2405.18047 2BP: 2-Stage Backpropagation
        34759, -- 2407.11798 PipeInfer: Accelerating LLM Inference using Asynchronous Pipelined Speculation
        37338, -- 2409.17264 Medha: Efficiently Serving Multi-Million Context Length LLM Inference Requests W
        37594, -- 2410.00531 TPI-LLM: Serving 70B-scale LLMs Efficiently on Low-resource Edge Devices
        39177, -- 2410.19367 BitPipe: Bidirectional Interleaved Pipeline Parallelism for Accelerating Large M
        39786, -- 2411.05288 Balancing Pipeline Parallelism with Vocabulary Parallelism
        45133, -- 2502.19913 SkipPipe: Partial and Reordered Pipelining Framework for Training LLMs in Hetero
        45318, -- 2503.01328 PipeOffload: Improving Scalability of Pipeline Parallelism with Memory Optimizat
        45691, -- 2503.06433 Seesaw: High-throughput LLM Inference via Model Re-sharding
        51502, -- 2506.21263 DiLoCoX: A Low-Communication Large-Scale Training Framework for Decentralized Cl
        52846, -- 2509.13523 AERIS: Argonne Earth Systems Model for Reliable and Skillful Predictions
        53708, -- 2510.18121 Efficient Long-context Language Model Training by Core Attention   Disaggregatio
        54563, -- 2512.04677 Live Avatar: Streaming Real-time Audio-Driven Avatar Generation with Infinite Le
        56338, -- 2602.21760 Accelerating Diffusion via Hybrid Data-Pipeline Parallelism Based on Conditional
        57380, -- 2604.02372 Backdoor Attacks on Decentralised Post-Training
        57810, -- 2604.27085 Efficient Training on Multiple Consumer GPUs with RoundPipe
        61461, -- 2602.01766 CoMeT: Collaborative Memory Transformer for Efficient Long Context Modeling
        62978, -- 2601.02360 Heterogeneous Low-Bandwidth Pre-Training of LLMs
        62983, -- 2601.02311 Placement Semantics for Distributed Deep Learning: A Systematic Framework for An
        72214, -- 2506.05806 LLIA -- Enabling Low-Latency Interactive Avatars: Real-Time Audio-Driven   Portr
        73426, -- 2504.14960 MoE Parallel Folding: Heterogeneous Parallelism Mappings for Efficient   Large-S
        74103, -- 2504.03662 Galvatron: Automatic Distributed Training for Large Transformer Models
        74106, -- 2503.10377 SPPO:Efficient Long-sequence LLM Training via Adaptive Sequence Pipeline   Paral
        74306, -- 2503.02356 Efficient Long Context Fine-tuning with Chunk Flow
        75874, -- 2411.01738 xDiT: an Inference Engine for Diffusion Transformers (DiTs) with Massive Paralle
        77222, -- 2405.14430 PipeFusion: Patch-level Pipeline Parallelism for Diffusion Transformers Inferenc
        77333, -- 2405.01248 DiffusionPipe: Training Large Diffusion Models with Efficient Pipelines
        77843, -- 2402.03791 Adaptive Blockwise Task-interleaved Pipeline Parallelism
        78599, -- 2308.15762 Hanayo: Harnessing Wave-like Pipeline Parallelism for Enhanced Large   Model Tra
        80881, -- 2102.07988 TeraPipe: Token-Level Pipeline Parallelism for Training Large-Scale Language Mod
        81993, -- 1806.03377 PipeDream: Fast and Efficient Pipeline Parallel DNN Training
        87513, -- 2605.30852 Speculative Pipeline Decoding: Higher-Accruacy and Zero-Bubble Speculation via P
        89243, -- 2505.01099 Nesterov Method for Asynchronous Pipeline Parallel Optimization
        90161, -- 2503.12053 Ferret: An Efficient Online Continual Learning Framework under Varying Memory Co
        98207, -- 2606.07881 Breaking the Bubble: Asynchronous Pipeline Parallel Training with Bounded Weight
        98980, -- 2606.30634 One-Step Gradient Delay is Not a Barrier for Large-Scale Asynchronous Pipeline P
        99312, -- 2602.03515 Mitigating Staleness in Asynchronous Pipeline Parallelism via Basis Rotation
        99920, -- 2605.18404 JanusPipe: Efficient Pipeline Parallel Training for Machine Learning Interatomic
        100093, -- 2503.11367 Efficient Distributed MLLM Training with Cornstarch
        101279, -- 2605.29664 AMDP: Asynchronous Multi-Directional Pipeline Parallelism for Large-Scale Models
        106449, -- 2511.09741 TawPipe: Topology-Aware Weight Pipeline Parallelism for Accelerating Long-Contex
        109388, -- 2608.14614 DumpsterCluster: From Dumpster Diving to Serving LLaMA-70B on $60 GPUs
        114021, -- 2609.07108 Online Draft Co-Training for Speculative Decoding in Large-Scale, Long-Context R
        122097, -- 2609.19169 SiliconBench: Speed, Memory, and Fidelity for LLM Serving on Unified-Memory Desk
        125652, -- external PipeFSDP: Efficient Pipeline Parallel under Fully Sharded Data Parallel for Larg
        126419, -- 2601.22442 AsyncMesh: Fully Asynchronous Optimization for Data and Pipeline Parallelism
        127192, -- external FRESCO: A Novel Consistency Control for Asynchronous Pipeline Parallel Training
        127368, -- external AsymPipe: Accelerating Large-scale DiTs Image Editing via Asymmetry-Aware Pipeli
        128133, -- external Clapping: Removing Per-sample Storage for Pipeline Parallel Learning with Commun
        128604, -- external Optimized Forward-Backward Rematerialization for Memory-Efficient Pipeline Paral
        130100  -- 2609.14339 Communication-Efficient LLM Adaptation over Decentralized GPU Meshes
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
        5792, -- 2105.13120 Sequence Parallelism: Long Sequence Training from System Perspective
        20910, -- 2309.14509 DeepSpeed Ulysses: System Optimizations for Enabling Training of Extreme Long Se
        35969, -- 2408.10013 SSDTrain: An Activation Offloading Framework to SSDs for Faster Large Language M
        43254, -- 2501.15383 Qwen2.5-1M Technical Report
        54200, -- 2511.11373 MarsRL: Advancing Multi-Agent Reasoning System via Reinforcement Learning with A
        62164, -- 2601.16956 DataStates-LLM: Scalable Checkpointing for Transformer Models Using Composable S
        63479, -- 2512.18318 Asynchronous Pipeline Parallelism for Real-Time Multilingual Lip Synchronization
        83400, -- 2605.17842 SNLP: Layer-Parallel Inference via Structured Newton Corrections
        92808, -- 2604.27089 AutoSP: Unlocking Long-Context LLM Training Via Compiler-Based Sequence Parallel
        98420, -- 2606.16993 DreamX-World 1.0: A General-Purpose Interactive World Model
        102426, -- 2604.24447 Characterizing Vision-Language-Action Models across XPUs: Constraints and Accele
        102882, -- 2604.07239 Efficient Learned Data Compression via Dual-Stream Feature Decoupling
        104037, -- 2607.15257 SearchOS-V1: Towards Robust Open-Domain Information-Seeking Agent Collaboration
        128884  -- 2610.14804 AgentWeave: Efficient Distributed Agent Serving via Flow Decomposition
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
        5792, -- 2105.13120 Sequence Parallelism: Long Sequence Training from System Perspective
        21310, -- 2310.01889 Ring Attention with Blockwise Transformers for Near-Infinite Context
        21430, -- 2310.03294 DISTFLASHATTN: Distributed Memory-efficient Attention for Long-context LLMs Trai
        23407, -- 2311.09431 Striped Attention: Faster Ring Attention for Causal Transformers
        27247, -- 2402.08268 World Model on Million-Length Video And Language With Blockwise RingAttention
        31244, -- 2405.07719 USP: A Unified Sequence Parallelism Approach for Long Context Generative AI
        35644, -- 2408.04093 Tree Attention: Topology-aware Decoding for Long-Context Attention on GPU cluste
        39577, -- 2411.01783 Context Parallelism for Scalable Million-Token Inference
        44033, -- 2502.07563 LASP-2: Rethinking Sequence Parallelism for Linear Attention and Its Hybrid
        56282, -- 2602.21196 Untied Ulysses: Memory-Efficient Context Parallelism via Headwise Chunking
        66075, -- 2510.18830 MTraining: Distributed Dynamic Sparse Attention for Efficient Ultra-Long Context
        75340, -- 2412.20501 TokenRing: An Efficient Parallelism Framework for Infinite-Context LLMs   via Bi
        76885, -- 2406.18485 LoongTrain: Efficient Training of Long-Sequence LLMs with Head-Context   Paralle
        114021, -- 2609.07108 Online Draft Co-Training for Speculative Decoding in Large-Scale, Long-Context R
        125574  -- external CHARM+: Cross-Hardware Attention with Re-Merge Multistream Mechanism
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
        21592, -- 2310.05209 Scaling Laws of RoPE-based Extrapolation
        24127, -- 2312.00678 The Efficiency Spectrum of Large Language Models: An Algorithmic Survey
        24607, -- 2312.06635 Gated Linear Attention Transformers with Hardware-Efficient Training
        24968, -- 2312.11897 Text-Conditioned Resampler For Long Form Video Understanding
        25165, -- 2312.15234 Towards Efficient Generative Large Language Model Serving: A Survey from Algorit
        25506, -- 2401.02669 Infinite-LLM: Efficient LLM Service for Long Context with DistAttention   and Di
        26748, -- 2402.02244 Beyond the Limits: A Survey of Techniques to Extend the Context Length in Large
        26784, -- 2402.02625 Enhancing Transformer RNNs with Multiple Temporal Perspectives
        27727, -- 2402.13598 User-LLM: Efficient LLM Contextualization with User Embeddings
        28663, -- 2403.06764 An Image is Worth 1/2 Tokens After Layer 2: Plug-and-Play Inference Acceleration
        29214, -- 2403.13802 ZigMa: A DiT-style Zigzag Mamba Diffusion Model
        29900, -- 2404.02882 Linear Attention Sequence Parallelism
        30160, -- 2404.06654 RULER: What's the Real Context Size of Your Long-Context Language Models?
        30187, -- 2404.07143 Leave No Context Behind: Efficient Infinite Context Transformers with Infini-att
        30308, -- 2404.08763 CATS: Contextually-Aware Thresholding for Sparsity in Large Language Models
        30309, -- 2404.08801 Megalodon: Efficient LLM Pretraining and Inference with Unlimited Context Length
        30902, -- 2404.18928 Stylus: Automatic Adapter Selection for Diffusion Models
        30952, -- 2405.00200 In-Context Learning with Long-Context Models: An In-Depth Exploration
        31034, -- 2405.01814 Efficient Heterogeneous Large Language Model Decoding with Model-Attention Disag
        31150, -- 2405.05254 You Only Cache Once: Decoder-Decoder Architectures for Language Models
        31176, -- 2405.05945 Lumina-T2X: Transforming Text into Any Modality, Resolution, and Duration via Fl
        31201, -- 2405.06640 Linearizing Large Language Models
        31373, -- 2405.10480 Lean Attention: Hardware-Aware Scalable Attention Mechanism for the Decode-Phase
        31399, -- 2405.11143 OpenRLHF: An Easy-to-use, Scalable and High-performance RLHF Framework
        31407, -- 2405.11299 The CAP Principle for LLM Serving: A Survey of Long-Context Large Language Model
        31509, -- 2405.13386 360Zhinao Technical Report
        31599, -- 2405.14591 Base of RoPE Bounds Context Length
        32147, -- 2405.21075 Video-MME: The First-Ever Comprehensive Evaluation Benchmark of Multi-modal LLMs
        32319, -- 2406.02547 Leveraging Visual Tokens for Extended Text Contexts in Multi-Modal Learning
        32601, -- 2406.06110 Recurrent Context Compression: Efficiently Expanding the Context Window of LLM
        32636, -- 2406.06484 Parallelizing Linear Transformers with the Delta Rule over Sequence Length
        32905, -- 2406.09415 An Image is Worth More Than 16x16 Patches: Exploring Transformers on Individual
        33410, -- 2406.14528 DeciMamba: Exploring the Length Extrapolation Potential of Mamba
        33610, -- 2406.16852 Long Context Transfer from Language to Vision
        33664, -- 2406.17588 LongIns: A Challenging Long-context Instruction-based Exam for LLMs
        33766, -- 2406.18820 Universal Checkpointing: Efficient and Flexible Checkpointing for Large Scale Di
        33873, -- 2407.00079 Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving
        33915, -- 2407.00783 Diffusion Models and Representation Learning: A Survey
        34059, -- 2407.02490 MInference 1.0: Accelerating Pre-filling for Long-Context LLMs via Dynamic Spars
        34230, -- 2407.04923 OmChat: A Recipe to Train Multimodal Language Models with Strong Long Context an
        34443, -- 2407.07860 Controlling Space and Time with Diffusion Models
        34500, -- 2407.08608 FlashAttention-3: Fast and Accurate Attention with Asynchrony and Low-precision
        34547, -- 2407.09111 Inference Optimization of Foundation Models on AI Accelerators
        34570, -- 2407.09450 Human-like Episodic Memory for Infinite Context LLMs
        34784, -- 2407.12077 GoldFinch: High Performance RWKV/Transformer Hybrid with Linear Pre-Fill and Ext
        34786, -- 2407.12117 MEMO: Fine-grained Tensor Management For Ultra-long Context LLM Training
        34928, -- 2407.13739 Scaling Granite Code Models to 128K Context
        35081, -- 2407.15892 Mini-Sequence Transformer: Optimizing Intermediate Memory for Long Sequences Tra
        35411, -- 2408.00167 Finch: Prompt-guided Key-Value Cache Compression
        35847, -- 2408.07802 Kraken: Inherently Parallel Transformers For Efficient Multi-Device Inference
        35978, -- 2408.10188 LongVILA: Scaling Long-Context Visual Language Models for Long Videos
        35979, -- 2408.10189 Transformers to SSMs: Distilling Quadratic Knowledge to Subquadratic Models
        36453, -- 2409.00509 LongRecipe: Recipe for Efficient Long Context Generalization in Large Language M
        36666, -- 2409.04774 Untie the Knots: An Efficient Data Augmentation Strategy for Long-Context Pre-Tr
        36778, -- 2409.07431 Synthetic continued pretraining
        36944, -- 2409.10516 RetrievalAttention: Accelerating Long-Context LLM Inference via Vector Retrieval
        37051, -- 2409.12181 A Controlled Study on Long Context Extension and Generalization in LLMs
        37338, -- 2409.17264 Medha: Efficiently Serving Multi-Million Context Length LLM Inference Requests W
        37431, -- 2409.18747 Cottention: Linear Transformers With Cosine Attention
        37752, -- 2410.02367 SageAttention: Accurate 8-Bit Attention for Plug-and-play Inference Acceleration
        37790, -- 2410.02703 Selective Attention Improves Transformer
        37938, -- 2410.04199 LongGenBench: Long-context Generation Benchmark
        37947, -- 2410.04343 Inference Scaling for Long-Context Retrieval Augmented Generation
        38126, -- 2410.06511 TorchTitan: One-stop PyTorch native solution for production ready LLM pre-traini
        38474, -- 2410.10819 DuoAttention: Efficient Long-Context LLM Inference with Retrieval and Streaming
        38742, -- 2410.13798 Learning Graph Quantized Tokenizers
        38876, -- 2410.15458 Allegro: Open the Black Box of Commercial-Level Video Generation Model
        39016, -- 2410.17243 Breaking the Memory Barrier: Near Infinite Batch Size Scaling for Contrastive Lo
        39126, -- 2410.18745 Why Does the Effective Context Length of LLMs Fall Short?
        39760, -- 2411.05000 Needle Threading: Can LLMs Follow Threads through Near-Million-Scale Haystacks?
        40212, -- 2411.13476 When Precision Meets Position: BFloat16 Breaks Down RoPE in Long-Context Trainin
        40405, -- 2411.16102 BlendServe: Optimizing Offline Inference for Auto-regressive Large Models with R
        40487, -- 2411.17116 Star Attention: Efficient LLM Inference over Long Sequences
        40840, -- 2412.01523 FlexSP: Accelerating Large Language Model Training via Flexible Sequence Paralle
        40934, -- 2412.02819 CNNSum: Exploring Long-Context Summarization with Large Language Models in Chine
        41004, -- 2412.03603 HunyuanVideo: A Systematic Framework For Large Video Generative Models
        41864, -- 2412.14294 TRecViT: A Recurrent Video Transformer
        42195, -- 2412.18860 Bootstrap Your Own Context Length
        42211, -- 2412.19191 Biology Instructions: A Dataset and Benchmark for Multi-Omics Sequence Understan
        42392, -- 2501.01005 FlashInfer: Efficient and Customizable Attention Engine for LLM Inference Servin
        42970, -- 2501.10187 Good things come in small packages: Should we build AI clusters with Lite-GPUs?
        43044, -- 2501.11847 A Survey on Memory-Efficient Large-Scale Model Training in AI for Science
        43074, -- 2501.12386 InternVideo2.5: Empowering Video MLLMs with Long and Rich Context Modeling
        43220, -- 2501.14808 HyGen: Efficient LLM Serving via Elastic Online-Offline Request Co-location
        43233, -- 2501.15089 LongReason: A Synthetic Long-Context Reasoning Benchmark via Context Expansion
        43437, -- 2501.18795 Rope to Nope and Back Again: A New Hybrid Attention Strategy
        43519, -- 2502.00791 Vision-centric Token Compression in Large Language Model
        43850, -- 2502.05177 Long-VITA: Scaling Large Multi-modal Models to 1 Million Tokens with Leading Sho
        43911, -- 2502.06155 Efficient-vDiT: Efficient Video Diffusion Transformers With Attention Tile
        43954, -- 2502.06766 Exploiting Sparsity for Long Context Inference: Million Token Contexts on Commod
        44035, -- 2502.07590 DSV: Exploiting Dynamic Sparsity to Accelerate Large-Scale Video DiT Training
        44203, -- 2502.10248 Step-Video-T2V Technical Report: The Practice, Challenges, and Future of Video F
        44701, -- 2502.14854 CLIPPER: Compression enables long-context synthetic data generation
        44807, -- 2502.15920 Self-Taught Agentic Long Context Understanding
        44991, -- 2502.18137 SpargeAttention: Accurate and Training-free Sparse Attention Accelerating Any Mo
        45001, -- 2502.18277 Self-Adjust Softmax
        45205, -- 2502.20766 FlexPrefill: A Context-Aware Sparse Attention Mechanism for Efficient Long-Seque
        45224, -- 2502.21231 ByteScale: Efficient Scaling of LLM Training with a 2048K Context Length on More
        45491, -- 2503.03588 PowerAttention: Exponentially Scaling of Receptive Fields for Effective Sparse A
        45620, -- 2503.05447 Linear-MoE: Linear Sequence Modeling Meets Mixture-of-Experts
        45691, -- 2503.06433 Seesaw: High-throughput LLM Inference via Model Re-sharding
        45827, -- 2503.07832 RefactorBench: Evaluating Stateful Reasoning in Language Agents Through Code
        45838, -- 2503.08026 In Prospect and Retrospect: Reflective Memory Management for Long-term Personali
        45991, -- 2503.09642 Open-Sora 2.0: Training a Commercial-Level Video Generation Model in $200k
        46237, -- 2503.12964 Training Video Foundation Models with NVIDIA NeMo
        46496, -- 2503.16428 XAttention: Block Sparse Attention with Antidiagonal Scoring
        46879, -- 2503.21772 LOCORE: Image Re-ranking with Long-Context Sequence Modeling
        46893, -- 2503.21839 M-DocSum: Do LVLMs Genuinely Comprehend Interleaved Image-Text in Document Summa
        47085, -- 2504.00072 Chapter-Llama: Efficient Chaptering in Hour-Long Videos with LLMs
        47204, -- 2504.02181 A Survey of Scaling in Large Language Model Reasoning
        47209, -- 2504.02259 Re-thinking Temporal Search for Long-Form Video Understanding
        47432, -- 2504.06261 Hogwild! Inference: Parallel LLM Generation via Concurrent Attention
        47488, -- 2504.07491 Kimi-VL Technical Report
        47984, -- 2504.14992 Efficient Pretraining Length Scaling
        48192, -- 2504.19720 Taming the Titans: A Survey of Efficient LLM Inference Serving
        48693, -- 2505.08651 Scaling Context, Not Parameters: Training a Compact 7B Language Model for Effici
        48866, -- 2505.11432 MegaScale-MoE: Large-Scale Communication-Efficient Training of Mixture-of-Expert
        48881, -- 2505.11594 SageAttention3: Microscaling FP4 Attention for Inference and An Exploration of 8
        49228, -- 2505.14741 Communication-Efficient Diffusion Denoising Parallelization via Reuse-then-Predi
        49400, -- 2505.16381 PaTH Attention: Position Encoding via Accumulating Householder Transformations
        49452, -- 2505.16864 Training-Free Efficient Video Generation via Dynamic Token Carving
        49747, -- 2505.19536 FlowCut: Rethinking Redundancy via Information Flow for Efficient Vision-Languag
        49920, -- 2505.21070 Minute-Long Videos with Dual Parallelisms
        50112, -- 2505.23520 AnchorAttention: Difference-Aware Sparse Attention with Stripe Granularity
        50444, -- 2506.02338 One Missing Piece for Open-Source Reasoning Models: A Dataset to   Mitigate Cold
        50579, -- 2506.04344 GEM: Empowering LLM for both Embedding Generation and Language Understanding
        50609, -- 2506.04761 Log-Linear Attention
        50634, -- 2506.05229 Diagonal Batching Unlocks Parallelism in Recurrent Memory Transformers for Long
        50652, -- 2506.05332 Unleashing Hour-Scale Video Training for Long Video-Language Understanding
        51037, -- 2506.10911 NoLoCo: No-all-reduce Low Communication Training Method for Large Models
        51188, -- 2506.13996 Arctic Long Sequence Training: Scalable And Efficient Training For Multi-Million
        51275, -- 2506.15745 InfiniPot-V: Memory-Constrained KV Cache Compression for Streaming Video Underst
        51616, -- 2507.01004 ZeCO: Zero Communication Overhead Sequence Parallelism for Linear   Attention
        51750, -- 2507.05934 BlueLM-2.5-3B Technical Report
        51822, -- 2507.07966 Scaling RL to Long Videos
        51826, -- 2507.07990 Multi-Granular Spatio-Temporal Token Merging for Training-Free   Acceleration of
        52052, -- 2507.18013 Technical Report of TeleChat2, TeleChat2.5 and T1
        52077, -- 2507.20198 When Tokens Talk Too Much: A Survey of Multimodal Long-Context Token   Compressi
        52846, -- 2509.13523 AERIS: Argonne Earth Systems Model for Reliable and Skillful Predictions
        53329, -- 2510.05862 Revisiting Long-context Modeling from Context Denoising Perspective
        53379, -- 2510.06915 LongRM: Revealing and Unlocking the Context Boundary of Reward Modeling
        53451, -- 2510.07151 ELMUR: External Layer Memory with Update/Rewrite for Long-Horizon RL
        53591, -- 2510.07414 Haystack Engineering: Context Engineering for Heterogeneous and Agentic   Long-C
        53628, -- 2510.13697 On Pretraining for Project-Level Code Completion
        53708, -- 2510.18121 Efficient Long-context Language Model Training by Core Attention   Disaggregatio
        53800, -- 2510.20668 From Masks to Worlds: A Hitchhiker's Guide to World Models
        53816, -- 2510.21270 Sparser Block-Sparse Attention via Token Permutation
        53850, -- 2510.22200 LongCat-Video Technical Report
        54317, -- 2511.17127 Training Foundation Models on a Full-Stack AMD Platform: Compute, Networking, an
        54384, -- 2511.20714 Inferix: A Block-Diffusion based Next-Generation Inference Engine for World Simu
        54392, -- 2511.20426 Block Cascading: Training Free Acceleration of Block-Causal Video Models
        54653, -- 2512.03704 DZ-TDPO: Non-Destructive Temporal Alignment for Mutable State Tracking in Long-C
        54758, -- 2512.12602 Error-Free Linear Attention is a Free Lunch: Exact Solution from Continuous-Time
        54862, -- 2512.16776 Kling-Omni Technical Report
        54954, -- 2512.16144 INTELLECT-3: Technical Report
        54984, -- 2512.15716 Spatia: Video Generation with Updatable Spatial Memory
        55756, -- 2602.04705 ERNIE 5.0 Technical Report
        56024, -- 2602.08030 Free(): Learning to Forget in Malloc-Only Reasoning Models
        56337, -- 2602.23361 VGG-T^3: Offline Feed-Forward 3D Reconstruction at Scale
        56623, -- 2603.08982 SVG-EAR: Parameter-Free Linear Compensation for Sparse Video Generation via Erro
        57059, -- 2603.24477 Composer 2 Technical Report
        57374, -- 2604.08644 EXAONE 4.5 Technical Report
        57410, -- 2604.10905 Audio Flamingo Next: Next-Generation Open Audio-Language Models for Speech, Soun
        58710, -- 2604.02371 Internalized Reasoning for Long-Context Visual Document Understanding
        59305, -- 2603.15953 A Family of LLMs Liberated from Static Vocabularies
        59361, -- 2603.14806 Fold-CP: A Context Parallelism Framework for Biomolecular Modeling
        59873, -- 2603.05353 InfoFlow KV: Information-Flow-Aware KV Recomputation for Long Context
        60591, -- 2602.15257 How to Train Your Long-Context Visual Document Model
        61324, -- 2602.03681 Neural Attention Search Linear: Towards Adaptive Token-Level Hybrid Attention Mo
        61400, -- 2602.02704 InfMem: Learning System-2 Memory Control for Long-Context Agent
        62902, -- 2601.03479 Efficient Sequential Recommendation for Long Term User Interest Via Personalizat
        63190, -- 2512.24157 Training Report of TeleChat3-MoE
        63229, -- 2512.23379 SoulX-FlashTalk: Real-Time Infinite Streaming of Audio-Driven Avatars via Self-C
        63398, -- 2512.20245 Memory as Resonance: A Biomimetic Architecture for Infinite Context Memory on Er
        63770, -- 2512.12167 Extending the Context of Pretrained LLMs by Dropping Their Positional Embeddings
        64995, -- 2511.11571 Optimizing Mixture of Block Attention
        65214, -- 2511.07399 StreamDiffusionV2: A Streaming System for Dynamic and Interactive Video Generati
        65536, -- 2511.00576 FlashEVA: Accelerating LLM inference via Efficient Attention
        66952, -- 2510.04476 Compressed Convolutional Attention: Efficient Attention in a Compressed   Latent
        67309, -- 2509.26182 Parallax: Efficient LLM Inference Service over Decentralized Environment
        67627, -- 2509.23040 Look Back to Reason Forward: Revisitable Memory for Long-Context LLM Agents
        67738, -- 2509.21841 Zeppelin: Balancing Variable-length Workloads in Data Parallel Large   Model Tra
        68465, -- 2509.10105 VARCO-VISION-2.0 Technical Report
        68967, -- 2509.00326 Chunked TabPFN: Exact Training-Free In-Context Learning for Long-Context   Tabul
        69221, -- 2508.17756 SuperGen: An Efficient Ultra-high-resolution Video Generation System   with Sket
        70714, -- 2507.19409 Modality Agnostic Efficient Long Range Encoder
        70981, -- 2507.14675 Docopilot: Improving Multimodal Models for Document-Level Understanding
        71223, -- 2507.09071 BlindSight: Harnessing Sparsity for Efficient VLMs
        72023, -- 2506.11440 AbsenceBench: Language Models Can't Tell What's Missing
        72133, -- 2506.07636 SWE-Dev: Building Software Engineering Agents with Training and   Inference Scal
        72581, -- 2505.22296 360-LLaMA-Factory: Plug & Play Sequence Parallelism for Long Post-Training
        73426, -- 2504.14960 MoE Parallel Folding: Heterogeneous Parallelism Mappings for Efficient   Large-S
        74106, -- 2503.10377 SPPO:Efficient Long-sequence LLM Training via Adaptive Sequence Pipeline   Paral
        74306, -- 2503.02356 Efficient Long Context Fine-tuning with Chunk Flow
        74711, -- 2502.09692 AB-UPT: Scaling Neural CFD Surrogates for High-Fidelity Automotive   Aerodynamic
        75695, -- 2411.17651 APEX: An Extensible and Dynamism-Aware Simulator for Automated Parallel   Execut
        75874, -- 2411.01738 xDiT: an Inference Engine for Diffusion Transformers (DiTs) with Massive Paralle
        77084, -- 2406.03243 Llumnix: Dynamic Scheduling for Large Language Model Serving
        77222, -- 2405.14430 PipeFusion: Patch-level Pipeline Parallelism for Diffusion Transformers Inferenc
        77938, -- 2401.09149 InternEvo: Efficient Long-sequence Large Language Model Training via   Hybrid Pa
        83142, -- 2605.10268 MemReread: Enhancing Agentic Long-Context Reasoning via Memory-Guided Rereading
        83180, -- 2605.06554 Long Context Pre-Training with Lighthouse Attention
        83366, -- 2605.18739 LongLive-2.0: An NVFP4 Parallel Infrastructure for Long Video Generation
        83379, -- 2605.14589 EndPrompt: Efficient Long-Context Extension via Terminal Anchoring
        83488, -- 2605.15514 RoPE Distinguishes Neither Positions Nor Tokens in Long Contexts, Provably
        83730, -- 2605.05066 The Impossibility Triangle of Long-Context Modeling
        83857, -- 2605.28691 OSP-Next: Efficient High-Quality Video Generation with Sparse Sequence Paralleli
        84263, -- 2511.21317 HTTM: Head-wise Temporal Token Merging for Faster VGGT
        86126, -- 2505.19609 Skrull: Towards Efficient Long Context Fine-tuning through Dynamic Data Scheduli
        86835, -- 2407.00611 StarTrail: Concentric Ring Parallelism for Efficient Near-Infinite-Context Trans
        87008, -- 2505.17083 Scale-invariant attention
        87943, -- 2501.02430 FOLDER: Accelerating Multi-Modal Large Language Models with Enhanced Performance
        88879, -- 2411.03493 LASER: Attention with Exponential Transformation
        89805, -- 2410.01651 Efficient Length-Generalizable Attention via Causal Retrieval for Long-Context L
        90281, -- 2503.13108 Lifting the Veil on Visual Information Flow in MLLMs: Unlocking Pathways to Fast
        91313, -- 2410.08368 ElasticTok: Adaptive Tokenization for Image and Video
        91541, -- 2407.00023 Preble: Efficient Distributed Prompt Scheduling for LLM Serving
        92712, -- 2601.21824 DASH: Deterministic Attention Scheduling for High-throughput Reproducible LLM Tr
        92787, -- 2506.16411 When Does Divide and Conquer Work for Long Context LLM? A Noise Decomposition Fr
        92808, -- 2604.27089 AutoSP: Unlocking Long-Context LLM Training Via Compiler-Based Sequence Parallel
        92900, -- 2511.05832 Hilbert-Guided Sparse Local Attention
        94410, -- 2602.02108 Out of the Memory Barrier: A Highly Memory-Efficient Training System for LLMs wi
        94623, -- 2509.25044 A Scalable Distributed Framework for Multimodal GigaVoxel Image Registration
        99534, -- 2603.06274 Stem: Rethinking Causal Information Flow in Sparse Attention
        99687, -- 2601.21461 $L^3$: Large Lookup Layers
        100093, -- 2503.11367 Efficient Distributed MLLM Training with Cornstarch
        101984, -- 2603.17484 Learning When to Attend: Conditional Memory Access for Long-Context LLMs
        102637, -- 2607.02980 Hierarchical Sparse Attention Done Right: Toward Infinite Context Modeling
        102713, -- 2607.07740 Jet-Long: Efficient Long-Context Extension with Dynamic Bifocal RoPE
        103679, -- 2601.11908 PPA-Plan: Proactive Pitfall Avoidance for Reliable Planning in Long-Context LLM
        104007, -- 2607.12395 Ring-Zero: Scaling Zero RL to a Trillion Parameters for Emergent Reasoning
        104064, -- 2607.14952 LongStraw: Long-Context RL Beyond 2M Tokens under a Fixed GPU Budget
        104306, -- 2607.16107 Audio-Visual Flamingo: Open Audio-Visual Intelligence for Long and Complex Video
        104488, -- 2607.16190 FVAttn: Adaptive Sparse Attention with Runtime Load Balancing for Video Generati
        104584, -- 2607.24653 Kimi K3: Open Frontier Intelligence
        108794, -- 2605.09932 FocuSFT: Bilevel Optimization for Dilution-Aware Long-Context Fine-Tuning
        109015, -- 2608.09119 Motif 3: Technical Report
        109799, -- 2608.26070 Prefix Sliding for efficient test-time scaling
        110284, -- 2509.24074 ResFormer: All-Time Reservoir Memory for Long Sequence Classification
        117718, -- 2604.05182 LSRM: High-Fidelity Object-Centric Reconstruction via Scaled Context Windows
        120721, -- external Polarization State Tracing for Reflection Removal and Color-Consistent Reconstru
        121997, -- 2609.14306 Flattening Every Memory Peak in Long-Context Mixture-of-Experts Training
        123560, -- 2610.22311 Velox: Spatial Memory Makes World Models Efficient
        123599, -- 2610.17901 FlashMask-3: Efficient and Expressive Mask-Aware Distributed Attention
        123606, -- 2610.21500 When the KV Cache Is Slower Than the GPU: Scaling Remote KV Tiers for Context-Pa
        123751, -- 2610.17644 DisaggKD: Efficient Knowledge Distillation through Teacher-Student Disaggregatio
        124067, -- 2610.30949 IQuest-Q1: Advancing Foundation Capabilities for Agentic CLI Systems
        124255, -- 2604.00004 LinearARD: Linear-Memory Attention Distillation for RoPE Restoration
        124517, -- 2609.24089 FlashBoB: I/O-Efficient Exact Backward-over-Backward for Softmax Attention
        125744, -- 2609.30682 Structure-Guided Masked Autoencoders for Ultra-High Resolution Scientific Image
        126344, -- 2602.21788 Efficient Scaling of LLM Training with Flexible Context Parallelism
        126952, -- 2605.31463 PithTrain: A Compact and Agent-Native MoE Training System
        128522, -- 2605.15422 DualKV: Shared-Prompt Flash Attention for Efficient RL Training with Large Rollo
        131624, -- 2610.38331 Multi-Token Prediction Done Right
        131757, -- 2611.00859 Wave Forcing: Towards Speed-of-Light Streaming Video Generation
        131820  -- 2611.03233 Axion 1.0: Open Agent Foundation Models, Simplified
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
        1318, -- 1806.01603 Layer rotation: a surprisingly powerful indicator of generalization in deep netw
        2402, -- 1908.03265 On the Variance of the Adaptive Learning Rate and Beyond
        3092, -- 2002.04745 On Layer Normalization in the Transformer Architecture
        6855, -- 2110.04369 A Loss Curvature Perspective on Training Instability in Deep Learning
        7340, -- 2111.14887 DAFormer: Improving Network Architectures and Training Strategies for Domain-Ada
        19024, -- 2308.04014 Continual Pre-Training of Large Language Models: How to (re)warm your model?
        21829, -- 2310.07831 Optimal Linear Decay Learning Rate Schedules and Further Refinements
        38980, -- 2410.16703 PLDR-LLM: Large Language Model from Power Law Decoder Representations
        41796, -- 2412.13337 Unveiling the Secret Recipe: A Guide For Supervised Fine-Tuning Small LLMs
        64089, -- 2512.11853 Evolving Deep Learning Optimizers
        85863, -- 2505.22014 Learning in Compact Spaces with Approximately Normalized Transformer
        92338, -- 2410.10986 What Does It Mean to Be a Transformer? Insights from a Theoretical Hessian Analy
        93047, -- 2510.19093 Weight Decay may matter more than µP for Learning Rate Transfer in Practice
        100029, -- 2510.03164 Why Do We Need Warm-up? A Theoretical Perspective
        123678, -- 2610.00673 Closing the Loop: Practical Training Recipes for Looped Language Models
        124533  -- 2602.05813 Where Does Warm-Up Come From? Adaptive Scheduling for Norm-Constrained Optimizer
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
        4991, -- 2102.02888 1-bit Adam: Communication Efficient Large-Scale Training with Adam's Convergence
        5337, -- 2103.17268 Fast Certified Robust Training with Short Warmup
        7884, -- 2202.02916 Dataset Condensation with Contrastive Signals
        16599, -- 2305.19059 Geometry-aware training of factorized layers in tensor Tucker format
        27242, -- 2402.08182 Variational Continual Test-Time Adaptation
        32453, -- 2406.04322 DIRECT-3D: Learning Direct Text-to-3D Generation on Massive Noisy 3D Data
        38595, -- 2410.12323 Reversal of Thought: Enhancing Large Language Models with Preference-Guided Reve
        38738, -- 2410.13782 DPLM-2: A Multimodal Diffusion Protein Language Model
        41333, -- 2412.07762 Efficient Online Reinforcement Learning Fine-Tuning Need Not Retain Offline Data
        45099, -- 2502.19557 Distill Not Only Data but Also Rewards: Can Smaller Language Models Surpass Larg
        49087, -- 2505.13718 Warm Up Before You Train: Unlocking General Reasoning in Resource-Constrained Se
        53601, -- 2510.13998 BitNet Distillation
        53948, -- 2510.22543 FAPO: Flawed-Aware Policy Optimization for Efficient and Reliable   Reasoning
        54935, -- 2512.17206 Reasoning Palette: Modulating Reasoning via Latent Contextualization for Control
        55997, -- 2602.11124 PhyCritic: Multimodal Critic Models for Physical AI
        56081, -- 2602.11543 Pretraining A Large Language Model using Distributed GPUs: A Memory-Efficient De
        56513, -- 2603.05369 Progressive Residual Warmup for Language Model Pretraining
        57861, -- 2605.01725 Motion-Aware Caching for Efficient Autoregressive Video Generation
        58695, -- 2603.29844 DIAL: Decoupling Intent and Action via Latent World Modeling for End-to-End VLA
        59652, -- 2603.09538 Towards Unified Multimodal Interleaved Generation via Group Relative Policy Opti
        60958, -- 2602.09023 TwinRL-VLA: Digital Twin-Driven Reinforcement Learning for Real-World Robotic Ma
        64901, -- 2511.13945 Can You Learn to See Without Images? Procedural Warm-Up for Vision Transformers
        65155, -- 2511.08480 Compression then Matching: An Efficient Pre-training Paradigm for Multimodal Emb
        65173, -- 2511.08185 Improving Long-Range Interactions in Graph Neural Simulators via Hamiltonian Dyn
        66135, -- 2510.18072 Fine-tuning Flow Matching Generative Models with Intermediate Feedback
        67775, -- 2509.21459 A State-of-the-Art SQL Reasoning Model using RLVR
        68393, -- 2509.11662 MindVL: Towards Efficient and Effective Training of Multimodal Large   Language
        68606, -- 2509.06948 Beyond Two-Stage Training: Cooperative SFT and RL for LLM Reasoning
        69249, -- 2508.17426 Modular MeanFlow: Towards Stable and Scalable One-Step Generative   Modeling
        72029, -- 2506.11300 Beyond Random Sampling: Efficient Language Model Pretraining via   Curriculum Le
        72304, -- 2506.03487 ProRank: Prompt Warmup via Reinforcement Learning for Small Language   Models Re
        72324, -- 2506.02975 HaploOmni: Unified Single Transformer for Multimodal Video Understanding   and G
        77515, -- 2404.01847 Accelerating Transformer Pre-training with 2:4 Sparsity
        86234, -- 2406.02613 ACCO: Accumulate While You Communicate for Communication-Overlapped Sharded LLM
        88381, -- 2503.05182 MGSR: 2D/3D Mutual-boosted Gaussian Splatting for High-fidelity Surface Reconstr
        92548, -- 2606.03972 AAD-1: Asymmetric Adversarial Distillation for One-Step Autoregressive Video Gen
        94674, -- 2602.03390 From Vicious to Virtuous Cycles: Synergistic Representation Learning for Unsuper
        100201, -- 2605.11836 More Edits, More Stable: Understanding the Lifelong Normalization in Sequential
        100723, -- 2606.14210 From Prompts to Responses: Dual-Sided Data Leakage and Defense in Split Large La
        100988, -- 2510.26433 Co-Evolving Latent Action World Models
        102799, -- 2410.04524 Toward Secure Tuning: Mitigating Security Risks from Instruction Fine-Tuning
        106714, -- 2508.13812 Timestep-Compressed Attack on Spiking Neural Networks Through Timestep-Level Bac
        106927, -- 2507.02227 PhysicsCorrect: A Training-Free Approach for Stable Neural PDE Simulations
        107703, -- 2601.10993 Memorize Early, Then Query: Inlier-Memorization-Guided Active Outlier Detection
        116423, -- external Global and Hierarchical Geometry Consistency Priors for Few-shot NeRFs in Indoor
        119383, -- 2607.00712 Towards Memory-Efficient Autoregressive Video Generation via Instance-Specific P
        119778, -- 2312.14474 MonoLSS: Learnable Sample Selection For Monocular 3D Detection
        126786, -- 2605.10741 AdaPaD: Adaptive Parallel Deflation for PEFT with Self-Correcting Rank Discovery
        127421, -- external Bridging Sequence and Structure with Unified Domain Adaptation for Drug-Target I
        127681, -- external Curvature-Guided Parameter Initialization for Multi-Task Learning
        129244, -- 2603.21465 DRTriton: Large-Scale Synthetic Data Driven Reinforcement Learning for Triton Ke
        129806, -- external Readiness-Aware Sample Selection for Noisy Labels with Class Imbalance
        130985, -- external AdERA: Adaptive Exponent Reuse for Lossless Allgather in Sharded MoE Training
        131058, -- external Tune-Up Open-Weight CLIP: Optimization Framework for Self-Supervised Fine-tuning
        131184, -- 2604.27077 Learning Rate Transfer in Normalized Transformers
        131472  -- 2610.33817 EnvLunch: The Environment as a Free Lunch for Learning to Interact
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
        3882, -- 2007.05929 Data-Efficient Reinforcement Learning with Self-Predictive Representations
        5034, -- 2102.06810 Understanding self-supervised Learning Dynamics without Contrastive Pairs
        11779, -- 2212.01322 MIC: Masked Image Consistency for Context-Enhanced Domain Adaptation
        12030, -- 2212.08653 Attentive Mask CLIP
        12086, -- 2212.09713 A Probabilistic Framework for Lifelong Test-Time Adaptation
        12990, -- 2302.04817 The Edge of Orthogonality: A Simple View of What Makes BYOL Tick
        15334, -- 2305.04769 BiRT: Bio-inspired Replay in Vision Transformers for Continual Learning
        17007, -- 2306.03241 Early Weight Averaging meets High Learning Rates for LLM Pre-training
        17873, -- 2306.16817 Improving Online Continual Learning Performance and Stability with Temporal Ense
        18469, -- 2307.10907 The Role of Entropy and Reconstruction in Multi-View Self-Supervised Learning
        18633, -- 2307.13813 How to Scale Your EMA
        18729, -- 2307.15254 Multiple Instance Learning Framework with Masked Hard Instance Mining for Whole
        19147, -- 2308.05991 Cyclic-Bootstrap Labeling for Weakly Supervised Object Detection
        22120, -- 2310.11428 Butterfly Effects of SGD Noise: Error Amplification in Behavior Cloning and Auto
        22278, -- 2310.13355 SILC: Improving Vision Language Pretraining with Self-Distillation
        23807, -- 2311.15830 A-JEPA: Joint-Embedding Predictive Architecture Can Listen
        24292, -- 2312.02696 Analyzing and Improving the Training Dynamics of Diffusion Models
        24701, -- 2312.07551 Language Model Alignment with Elastic Reset
        24970, -- 2312.11954 Adversarial AutoMixup
        27242, -- 2402.08182 Variational Continual Test-Time Adaptation
        27316, -- 2402.09240 Switch EMA: A Free Lunch for Better Flatness and Sharpness
        33597, -- 2406.16768 WARP: On the Benefits of Weight Averaged Rewarded Policies
        34036, -- 2407.02253 Parameter-Selective Continual Test-Time Adaptation
        34281, -- 2407.05623 Momentum Auxiliary Network for Supervised Local Learning
        38483, -- 2410.10868 Large Continual Instruction Assistant
        44620, -- 2502.14123 Understanding SGD with Exponential Moving Average: A Case Study in Linear Regres
        48085, -- 2504.16801 Decoupled Global-Local Alignment for Improving Compositional   Understanding
        50519, -- 2506.03538 Robust Neural Rendering in the Wild with Asymmetric Dual 3D Gaussian   Splatting
        52771, -- 2509.11526 Multiple Instance Learning Framework with Masked Hard Instance Mining   for Giga
        52822, -- 2509.20706 MI-Fuse: Label Fusion for Unsupervised Domain Adaptation with   Closed-Source La
        56719, -- 2603.12916 Surprised by Attention: Predictable Query Dynamics for Time Series Anomaly Detec
        56903, -- 2603.19714 LoopRPT: Reinforcement Pre-Training for Looped Language Models
        57312, -- 2604.07350 Fast Spatial Memory with Elastic Test-Time Training
        57563, -- 2604.12012 TIPSv2: Advancing Vision-Language Pretraining with Enhanced Patch-Text Alignment
        59058, -- 2603.21284 Sonny: Breaking the Compute Wall in Medium-Range Weather Forecasting
        59785, -- 2603.06167 A Semi-Supervised Framework for Breast Ultrasound Segmentation with Training-Fre
        62061, -- 2602.02522 IMU-1: Sample-Efficient Pre-training of Small Language Models
        65923, -- 2510.21250 Improved Training Technique for Shortcut Models
        67494, -- 2509.24317 Rethinking JEPA: Compute-Efficient Video SSL with Frozen Teachers
        68795, -- 2509.02982 StableSleep: Source-Free Test-Time Adaptation for Sleep Staging with   Lightweig
        69180, -- 2508.18751 Stabilizing Open-Set Test-Time Adaptation via Primary-Auxiliary Filtering and Kn
        70452, -- 2508.00180 EMA Without the Lag: Bias-Corrected Iterate Averaging Schemes
        72499, -- 2506.00288 Emergent Abilities of Large Language Models under Continued Pretraining   for La
        78310, -- 2310.18640 Switching Temporary Teachers for Semi-Supervised Semantic Segmentation
        82926, -- 2605.06597 UniSD: Towards a Unified Self-Distillation Framework for Large Language Models
        85204, -- 2603.29409 CLaD: Planning with Grounded Foresight via Cross-Modal Latent Dynamics
        85509, -- 2605.05027 Prompt-Anchored Vision-Text Distillation for Lifelong Person Re-identification
        88070, -- 2503.11078 Understanding Flatness in Generative Models: Its Role and Benefits
        90304, -- 2503.23220 Large Self-Supervised Models Bridge the Gap in Domain Adaptive Object Detection
        91193, -- 2503.15141 Object-Centric Pretraining via Target Encoder Bootstrapping
        93110, -- 2504.11699 HarmonyGNNs: Harmonizing Heterophily and Homophily in GNNs via Self-Supervised N
        93951, -- 2507.01028 Dual Perspectives on Non-Contrastive Self-Supervised Learning
        94838, -- 2506.18248 Improving Black-Box Generative Attacks via Generator Semantic Consistency
        96223, -- 2602.20923 ParkDiffusion++: Ego Intention Conditioned Joint Trajectory Prediction for Autom
        98361, -- external DVD-JEPA: A Minimal, Reproducible Joint-Embedding Predictive Architecture World
        98562, -- external CodeLeWM: A Reproducible, Claim-Gated Code World-Model Study with Negative Actio
        98656, -- 2208.05688 Semi-supervised Vision Transformers at Scale
        99970, -- 2605.29380 TRACER: Persistent Regularization for Robust Multimodal Finetuning
        102655, -- 2607.04044 SiamJEPA: On the Role of Siamese Student Encoders in JEPA
        104513, -- 2607.21556 Visual Contrastive Self-Distillation
        105052, -- external Contrastive Masked Video Modeling for Coronary Angiography Diagnosis
        105690, -- external SR-SAM: Subspace Regularization for Domain Generalization of Segment Anything Mo
        108337, -- 2511.18851 Robust Long-Term Test-Time Adaptation for 3D Human Pose Estimation Through Motio
        108632, -- 2608.01397 SG-WAM: Self-Guided World Modeling in Geometry-Aware Policy Space
        108760, -- 2605.02943 Healthcare AI GYM for Medical Agents
        108952, -- 2608.05774 SR-JEPA: Learning Predictive Latent State in 3D Scenes
        109713, -- 2608.24646 On-Policy Self-Distillation in Diffusion Models
        111395, -- external An Investigative Study on Recent Sharpness- and Flatness-Based Optimizers for En
        111589, -- external An Effective Anomalous Sound Detection Method Based on Global and Local Attribut
        112959, -- external Better Regression Makes Better Test-time Adaptive 3D Object Detection
        114255, -- 2605.04470 CRAFT: Counterfactual-to-Interactive Reinforcement Fine-Tuning for Driving Polic
        115957, -- 2402.19082 VideoMAC: Video Masked Autoencoders Meet ConvNets
        116096, -- 2403.09359 D3T: Distinctive Dual-Domain Teacher Zigzagging Across RGB-Thermal Gap for Domai
        116868, -- 2403.07705 Robust Synthetic-to-Real Transfer for Stereo Matching
        119062, -- 2605.06273 On-Orbit Real-Time Wildfire Detection Under On-Board Constraints
        122214, -- 2410.19560 Connecting Joint-Embedding Predictive Architecture with Contrastive Self-supervi
        122532, -- 2609.38854 Mitigating the Length-Scaling Tax with Online Distillation
        122623, -- 2610.02117 Where-OPD: Spatially Guided On-Policy Self-Distillation of MLLMs with Synthetic
        123056, -- 2610.12572 DiffusionART: Efficient, Stable and Scalable Reinforcement of Diffusion Models
        124241, -- external Beyond Stabilization: Dual-EMA Teachers for Global–Local Semantic Learning in Se
        124797, -- external Beyond Distribution Matching: Self-Supervised Representation Forcing for Few-Ste
        125177, -- external Watching Itself Watch: Self-Auditing Visual Reliance for Video Reasoning
        125560, -- 2606.25086 Training for the Model You Return: Improving Optimization for Iterate-Averaged L
        125829, -- 2605.06094 VISD: Enhancing Video Reasoning via Structured Self-Distillation
        126796, -- 2605.17429 Radial-Angular Geometry for Reliable Update Diagnosis in Noisy-Label Learning
        126938, -- 2605.27924 SIGMA: Semantic-Difference Instruction-Grounding Mask Annotator for Text-Driven
        128391, -- external Robust and Efficient Finetuning of Vision Foundation Models via Implicit Ensembl
        128620, -- external Improving Neural Processes in the Low-Data Regime via Context-Subset Training an
        129086, -- 2605.08577 Improving Generative Adversarial Networks with Self-Distillation
        130225, -- 2610.02344 Drive vs. Decay: On the Training Dynamics of Joint-Embedding Predictive Architec
        130722, -- external BLANP: Memory-Efficient Backpropagation-Free Local Training via Antithetic Node
        131603, -- 2610.39633 Intrinsic Distribution Matching
        131876, -- 2610.41104 MUON-RT Reusing the Teacher's Trajectory for Momentum-Free Muon for LLM Self-Dis
        132007  -- 2610.37115 Self-Regularized Flow Language Models
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
        1220, -- 1804.04235 Adafactor: Adaptive Learning Rates with Sublinear Memory Cost
        2023, -- 1904.09237 On the Convergence of Adam and Beyond
        2583, -- 1909.11015 diffGrad: An Optimization Method for Convolutional Neural Networks
        2733, -- 1910.12249 An Adaptive and Momental Bound Method for Stochastic Learning
        3644, -- 2006.00719 ADAHESSIAN: An Adaptive Second Order Optimizer for Machine Learning
        4354, -- 2010.07468 AdaBelief Optimizer: Adapting Stepsizes by the Belief in Observed Gradients
        12406, -- 2301.06052 T2M-GPT: Generating Human Motion from Textual Descriptions with Discrete Represe
        13407, -- 2303.00440 Extracting Motion and Appearance via Inter-Frame Attention for Efficient Video F
        14034, -- 2303.12965 Efficient Meshy Neural Fields for Animatable Human Avatars
        22588, -- 2310.17097 Navigating Data Heterogeneity in Federated Learning A Semi-Supervised Federated
        26810, -- 2402.02998 Careful with that Scalpel: Improving Gradient Surgery with an EMA
        28431, -- 2403.03095 Cross Pseudo-Labeling for Semi-Supervised Audio-Visual Source Localization
        28925, -- 2403.10395 Isotropic3D: Image-to-3D Generation Based on a Single CLIP Embedding
        28973, -- 2403.11047 From Pixels to Predictions: Spectrogram and Vision Transformer for Better Time S
        30309, -- 2404.08801 Megalodon: Efficient LLM Pretraining and Inference with Unlimited Context Length
        33169, -- 2406.11837 Scaling the Codebook Size of VQGAN to 100,000 with a Utilization Rate of 99%
        36598, -- 2409.03137 The AdEMAMix Optimizer: Better, Faster, Older
        37545, -- 2409.20325 Old Optimizer, New Norm: An Anthology
        40581, -- 2411.18180 DistinctAD: Distinctive Audio Description Generation in Contexts
        43018, -- 2501.11299 MIFNet: Learning Modality-Invariant Features for Generalizable Multimodal Image
        44271, -- 2502.11034 AdaGC: Improving Training Stability for Large Language Model Pretraining
        44808, -- 2502.15938 Straight to Zero: Why Linearly Decaying the Learning Rate to Zero Works Best for
        52282, -- 2508.06429 SPARSE Data, Rich Results: Few-Shot Semi-Supervised Learning via   Class-Conditi
        54541, -- 2512.03043 OneThinker: All-in-one Reasoning Model for Image and Video
        54566, -- 2512.04678 Reward Forcing: Efficient Streaming Video Generation with Rewarded Distribution
        55253, -- 2601.06463 Gecko: An Efficient Neural Architecture Inherently Processing Sequences with Arb
        55559, -- 2601.19280 Group Distributionally Robust Optimization-Driven Reinforcement Learning for LLM
        56461, -- 2603.00618 Multi-Domain Riemannian Graph Gluing for Building Graph Foundation Models
        56710, -- 2603.08127 EvoScientist: Towards Multi-Agent Evolving AI Scientists for End-to-End Scientif
        56837, -- 2603.11535 Expert Threshold Routing for Autoregressive Language Modeling with Dynamic Compu
        56995, -- 2603.22350 Session Risk Memory (SRM): Temporal Authorization for Deterministic Pre-Executio
        59283, -- 2603.16732 Confusion-Aware Spectral Regularizer for Long-Tailed Recognition
        59444, -- 2603.19312 LeWorldModel: Stable End-to-End Joint-Embedding Predictive Architecture from Pix
        60321, -- 2602.20846 Body-Reservoir Governance in Repeated Games: Embodied Decision-Making, Dynamic S
        60358, -- 2602.20360 Momentum Guidance: Plug-and-Play Guidance for Flow Models
        60410, -- 2602.19322 US-JEPA: A Joint Embedding Predictive Architecture for Medical Ultrasound
        60589, -- 2509.25380 Predicting Training Re-evaluation Curves Enables Effective Data Curriculums for
        60887, -- 2602.10204 Adaptive Optimization via Momentum on Variance-Normalized Gradients
        61503, -- 2602.01797 ORCH: many analyses, one merge-a deterministic multi-agent orchestrator for disc
        63159, -- 2601.00894 When to Ponder: Adaptive Compute Allocation for Code Generation via Test-Time Tr
        63846, -- 2512.10477 Symphony: A Heuristic Normalized Calibrated Advantage Actor and Critic Algorithm
        66415, -- 2510.12954 CADE 2.5 - ZeResFDG: Frequency-Decoupled, Rescaled and Zero-Projected   Guidance
        66666, -- 2510.09720 Preference-Aware Memory Update for Long-Term LLM Agents
        67254, -- 2510.00339 Navigating the Synchrony-Stability Frontier in Adaptive Chatbots
        68865, -- 2509.02627 A Two-Stage Strategy for Mitosis Detection Using Improved YOLO11x   Proposals an
        71643, -- 2506.23252 DGE-YOLO: Dual-Branch Gathering and Attention for Accurate UAV Object   Detectio
        76798, -- 2407.05203 Toward a Unified Metadata Schema for Ecological Momentary Assessment with Voice-
        77925, -- 2401.11124 Cross-Task Affinity Learning for Multitask Dense Scene Predictions
        79734, -- 2209.08490 EMA-VIO: Deep Visual-Inertial Odometry with External Memory Attention
        79814, -- 2208.00301 Towards Visualization of Time-Series Ecological Momentary Assessment (EMA) Data
        82871, -- 2605.06507 MARBLE: Multi-Aspect Reward Balance for Diffusion RL
        83464, -- 2605.09640 Overcoming Catastrophic Forgetting in Visual Continual Learning with Reinforceme
        84504, -- 2602.04268 KVSmooth: Mitigating Hallucination in Multi-modal Large Language Models through
        84927, -- 2603.15475 Seeing Beyond: Extrapolative Domain Adaptive Panoramic Segmentation
        85081, -- 2603.24139 Tutor-Student Reinforcement Learning: A Dynamic Curriculum for Robust Deepfake D
        85279, -- 2604.04681 Batch Loss Score for Dynamic Data Pruning
        86839, -- 2504.12463 Dense Backpropagation Improves Training for Sparse Mixture-of-Experts
        87391, -- 2505.13279 Event-Driven Dynamic Scene Depth Completion
        88457, -- 2508.05689 Boosting Adversarial Transferability via Residual Perturbation Attack
        88891, -- 2503.15200 Partially Observable Reinforcement Learning with Memory Traces
        89228, -- 2502.20853 Oscillation-Reduced MXFP4 Training for Vision Transformers
        89714, -- 2405.13698 How to set AdamW's weight decay as you scale model and dataset size
        90167, -- 2505.23068 URWKV: Unified RWKV Model with Multi-state Perspective for Low-light Image Resto
        90946, -- 2503.13016 Efficient Motion-Aware Video MLLM
        94044, -- 2605.08840 ReST-KV: Robust KV Cache Eviction with Layer-wise Output Reconstruction and Spat
        94755, -- 2602.24283 Taming Momentum: Rethinking Optimizer States Through Low-Rank Approximation
        94923, -- 2603.13792 IGU-LoRA: Adaptive Rank Allocation via Integrated Gradients and Uncertainty-Awar
        96554, -- external 3D Targeting of a Magnetic Particle in Blood Vessels Using Field-Free Points in
        97308, -- 2602.21589 SEF-MAP: Subspace-Decomposed Expert Fusion for Robust Multimodal HD Map Predicti
        97999, -- external SCADA (AutoSOTA)
        98032, -- external FOZO: Forward-Only Zeroth-Order Prompt Optimization for Test-Time Adaptation (Au
        98048, -- external ARC Is a Vision Problem! (AutoSOTA)
        98408, -- 2606.14732 Steady-Forcing: Balancing Spatial Persistence and Motion Continuity in Long-Hori
        98867, -- external NeuroFlow: EMA-Gated Temporal Sequence Compression in Vision Transformers
        99660, -- 2605.15403 $\phi$-Balancing for Mixture-of-Experts Training
        102093, -- 2603.20631 LassoFlexNet: a Flexible Neural Architecture for Tabular Data
        102793, -- 2507.06573 From Data-Centric to Sample-Centric: Enhancing LLM Reasoning via Progressive Opt
        103101, -- 2512.23025 LENS: LLM-Enabled Narrative Synthesis for Mental Health by Aligning Multimodal S
        103137, -- 2601.07483 FocalOrder: Focal Preference Optimization for Reading Order Detection
        103737, -- 2507.21420 ReGATE: Learning Faster and Better with Fewer Tokens in MLLMs
        103787, -- 2511.14017 From Narrow Unlearning to Emergent Misalignment in LLMs
        107819, -- 2508.16651 HiCL: Hippocampal-Inspired Continual Learning
        109303, -- 2608.07409 UniJEPA: A Unified Joint-Embedding Predictive Architecture for Task-Agnostic Vis
        111189, -- external Lexical stress affects lenition: The case of Italian palato-alveolar affricates
        111191, -- 2506.08981 FROST-EMA: Finnish and Russian Oral Speech Dataset of Electromagnetic Articulogr
        111305, -- 2510.00914 Reconstruction of the Complete Vocal Tract Contour Through Acoustic to Articulat
        111745, -- external Supralaryngeal Kinematics of Implosives in Central Vietnamese: An EMA Study
        111747, -- external Articulatory variations in Apical Vowels in Southwestern Mandarin
        114087, -- 2609.06490 OracleZoom: On-Policy Self-Distillation Inspired Reference-Constrained Recursive
        115900, -- 2403.12350 Friendly Sharpness-Aware Minimization
        117703, -- 2603.18493 FILT3R: Latent State Adaptive Kalman Filter for Streaming 3D Reconstruction
        118456, -- 2603.23086 Policy-Based Tuning of Autoregressive Image Models with Instance- and Distributi
        118552, -- 2607.09753 Unified Backbone Refinement for Diffusion Models via Internal-Latent Analysis
        119280, -- 2603.12513 MemRoPE: Training-Free Infinite Video Generation via Evolving Memory Tokens
        120767, -- external DREAM: Document Recognition with Explicit Adaptive Memory
        121103, -- 2601.07396 Forecast the Principal, Stabilize the Residual: Subspace-Aware Feature Caching f
        121801, -- external AdaPrior: Bayesian-Inspired Adaptive Prior Correction for Long-Tailed Continual
        123158, -- 2610.06226 LeAVJEPA: A Minimalist Architecture for Audio-Visual Self-Supervised Learning
        123171, -- 2610.07207 Distributionally Robust Mixture-of-Experts Training
        124498, -- 2609.35392 The Hidden Ratio in Adam: Stable Structure, Compression, and Sign Dynamics
        124774, -- external DeltaMomentum: A Key-Value based Anisotropic Momentum Update via Delta Rule
        124991, -- 2605.23200 Adaptive Mass-Segmented KV Compression for Long-Context Reasoning
        125144, -- external BReD: Block Replay Dithering for Stable Low-Bit EMA Optimizer States
        125387, -- external ADKV: A Low-Overhead Adaptive Delta Quantization for KV Cache in LLM Inference
        125417, -- external DACE RL for Compute Efficient Reinforcement Learning in Small Model Reasoning
        125676, -- external Learning-to-Memorize: Dynamic Context Management for Long-Horizon Autoregressive
        126043, -- external Perception for Action in Latent World Models
        126419, -- 2601.22442 AsyncMesh: Fully Asynchronous Optimization for Data and Pipeline Parallelism
        126982, -- 2605.08250 Why Do DiT Editors Drift? Plug-and-Play Low Frequency Alignment in VAE Latent Sp
        127666, -- external Dynamic Context Modeling for Longitudinal Mental Health Monitoring under Distrib
        127671, -- external When Alignment Fails: Stabilizing Cross-Dynamics RL with Prototype Trust Regions
        127721, -- external Scaling Arbitrary Architectures and Optimizers with Automatic Parameterization
        128296, -- external Matrix-Free Natural Gradient via Stochastic Truncated Metrics
        128925, -- external B2P-Corr: Batch-to-Population Gradient Estimators for Non-Decomposable Correlati
        131190  -- 2605.25395 EMA-Nesterov: Stabilizing Nesterov's Lookahead for Accelerated Deep Learning Opt
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
        337, -- 1603.06560 Hyperband: A Novel Bandit-Based Approach to Hyperparameter Optimization
        1349, -- 1806.07572 Neural Tangent Kernel: Convergence and Generalization in Neural Networks
        1720, -- 1812.09764 Neural Persistence: A Complexity Measure for Deep Neural Networks Using Algebrai
        2542, -- 1909.06035 DARTS+: Improved Differentiable Architecture Search with Early Stopping
        2832, -- 1911.08731 Distributionally Robust Neural Networks for Group Shifts: On the Importance of R
        8334, -- 2203.10036 On the Generalization Mystery in Deep Learning
        11844, -- 2212.03462 PADDLES: Phase-Amplitude Spectrum Disentangled Early Stopping for Learning with
        12579, -- 2301.11556 Conformal inference is (almost) free for neural networks trained with early stop
        13779, -- 2303.08433 The Benefits of Mixup for Feature Learning
        14489, -- 2304.02688 Going Further: Flatness at the Rescue of Early Stopping for Adversarial Example
        18085, -- 2307.03692 Becoming self-instruct: introducing early stopping criteria for minimal instruct
        21198, -- 2310.00894 JPEG Information Regularized Deep Image Prior for Denoising
        21956, -- 2310.09144 Goodhart's Law in Reinforcement Learning
        26376, -- 2401.15604 Neural Network-Based Score Estimation in Diffusion Models: Optimization and Gene
        29974, -- 2404.03784 Layerwise Early Stopping for Test Time Adaptation
        34788, -- 2407.12164 Subject-driven Text-to-Image Generation via Preference-based Reinforcement Learn
        43589, -- 2502.01636 Lifelong Knowledge Editing requires Better Regularization
        60060, -- 2509.25087 Scaling with Collapse: Efficient and Predictable Training of LLM Families
        65677, -- 2510.25480 Gradient-Weight Alignment as a Train-Time Proxy for Generalization in   Classifi
        68852, -- 2509.01842 GradES: Significantly Faster Training in Transformers with   Gradient-Based Earl
        71844, -- 2506.16840 FedFitTech: A Baseline in Federated Learning for Fitness Tracking
        77850, -- 2402.02513 Early stopping by correlating online indicators in neural networks
        78297, -- 2310.20447 Efficient Bayesian Learning Curve Extrapolation using Prior-Data Fitted   Networ
        79464, -- 2212.11481 A Mathematical Framework for Learning Probability Distributions
        80410, -- 2107.03633 Generalization Error of GAN from the Discriminator's Perspective
        80856, -- 2011.14269 Generalization and Memorization: The Bias Potential Model
        81448, -- 2002.06305 Fine-Tuning Pretrained Language Models: Weight Initializations, Data Orders, and
        82234, -- 1705.10823 Accelerating Neural Architecture Search using Performance Prediction
        86090, -- 2505.10880 Approximation and Generalization Abilities of Score-based Neural Network Generat
        87218, -- 2510.11824 Empirical Study on Robustness and Resilience in Cooperative Multi-Agent Reinforc
        87638, -- 2503.21410 Diffusion Image Prior
        88718, -- 2503.02877 Weak-to-Strong Generalization Even in Random Feature Networks, Provably
        88761, -- 2501.19158 A Theoretical Framework For Overfitting In Energy-based Modeling
        88805, -- 2502.13283 Benefits of Early Stopping in Gradient Descent for Overparameterized Logistic Re
        89614, -- 2505.18909 On the Role of Label Noise in the Feature Learning Process
        92446, -- 2502.07547 Instance-dependent Early Stopping
        93077, -- 2507.03756 Implicit Regularisation in Diffusion Models: An Algorithm-Dependent Generalisati
        93528, -- 2506.03337 Mitigating Non-IID Drift in Zeroth-Order Federated LLM Fine-Tuning with Transfer
        94554, -- 2603.02729 The Power of Small Initialization in Noisy Low-Tubal-Rank Tensor Recovery
        94955, -- 2510.08771 LinearSR: Unlocking Linear Attention for Stable and Efficient Image Super-Resolu
        99364, -- 2403.04545 Branch Scaling Manifests as Implicit Architectural Regularization for Improving
        101591, -- 2602.23039 Dynamics of neural scaling laws in random feature regression with powerlaw-distr
        101825, -- 2603.03469 Biased Generalization in Diffusion Models
        101985, -- 2506.14126 From Memorization to Parameter Interference: How Overtraining Experts Harms Mode
        103335, -- 2606.03073 Efficient Hyperparameter Optimization for LLM Reinforcement Learning
        126692, -- 2608.06250 Minimax Optimal Early-Stopped Gradient Descent for Gaussian Mixture Classificati
        127567, -- 2605.25299 A Principled Self-Referenced Early Stopping Approach for Deep Image Prior
        127720, -- 2604.18450 Random Matrix Theory of Early-Stopped Gradient Flow: A Transient BBP Scenario
        130303  -- external On Generalization in Bilevel Optimization with Overparameterized Models
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
        907, -- 1710.03667 High-dimensional dynamics of generalization error in neural networks
        1544, -- 1810.05749 Graph HyperNetworks for Neural Architecture Search
        3344, -- 2004.05884 Adversarial Weight Perturbation Helps Robust Generalization
        6889, -- 2110.06051 Efficient Neural Ranking using Forward Indexes
        8043, -- 2202.11558 Short-answer scoring with ensembles of pretrained language models
        9265, -- 2205.14865 Prompt-aligned Gradient for Prompt Tuning
        9752, -- 2207.05041 Parallel Bayesian Optimization of Agent-based Transportation Simulation
        10181, -- 2208.14614 Rethinking Conversational Recommendations: Is Decision Tree All You Need?
        10209, -- 2209.01275 Feature diversity in self-supervised learning
        11204, -- 2211.01916 Improved Analysis of Score-based Generative Modeling: User-Friendly Bounds under
        12524, -- 2301.10808 Graph Neural Tangent Kernel: Convergence on Large Graphs
        13427, -- 2303.00918 STUNT: Few-shot Tabular Learning with Self-generated Tasks from Unlabeled Tables
        13501, -- 2303.02732 Iterative Approximate Cross-Validation
        18993, -- 2308.03409 DiT: Efficient Vision Transformers with Dynamic Token Routing
        20013, -- 2309.00384 BatchPrompt: Accomplish more with less
        21293, -- 2310.01762 Sampling Multimodal Distributions with the Vanilla Score: Benefits of Data-Based
        23309, -- 2311.08360 The Transient Nature of Emergent In-Context Learning in Transformers
        23776, -- 2311.15436 Learning to Skip for Language Modeling
        24411, -- 2312.03951 Understanding the Role of Optimization in Double Descent
        25678, -- 2401.05605 Scaling Laws for Forgetting When Fine-Tuning Large Language Models
        26031, -- 2401.10480 Escape Sky-high Cost: Early-stopping Self-Consistency for Multi-step Reasoning
        26154, -- 2401.12253 Accelerating Sinkhorn Algorithm with Sparse Newton Iterations
        26602, -- 2402.00857 Early Time Classification with Accumulated Accuracy Gap Control
        31621, -- 2405.14800 Membership Inference on Text-to-Image Diffusion Models via Conditional Likelihoo
        32322, -- 2406.02550 Learning to grok: Emergence of in-context learning and skill composition in modu
        36193, -- 2408.13457 Make Every Penny Count: Difficulty-Adaptive Self-Consistency for Cost-Efficient
        36954, -- 2409.10644 Improving Multi-candidate Speculative Decoding
        39661, -- 2411.03284 SMoA: Improving Multi-agent Large Language Models with Sparse Mixture-of-Agents
        39767, -- 2411.05045 Performance-Guided LLM Knowledge Distillation for Efficient Text Classification
        45232, -- 2503.00031 Efficient Test-Time Scaling via Self-Calibration
        46954, -- 2503.22713 Chirp Localization via Fine-Tuned Transformer Model: A Proof-of-Concept Study
        48511, -- 2505.04881 ConCISE: Confidence-guided Compression in Step-by-step Efficient Reasoning
        49583, -- 2505.18149 First Finish Search: Efficient Test-Time Scaling in Large Language Models
        49846, -- 2505.20266 syftr: Pareto-Optimal Generative AI
        50076, -- 2505.23059 From Token to Action: State Machine Reasoning to Mitigate Overthinking in Inform
        50222, -- 2505.24362 Knowing Before Saying: LLM Representations Encode Information About Chain-of-Tho
        50975, -- 2506.09996 From Judgment to Interference: Early Stopping LLM Harmful Outputs via Streaming
        52069, -- 2507.19478 MMBench-GUI: Hierarchical Multi-Platform Evaluation Framework for GUI   Agents
        53295, -- 2510.06030 Adaptive Pruning for Increased Robustness and Reduced Computational   Overhead i
        53369, -- 2510.08308 First Try Matters: Revisiting the Role of Reflection in Reasoning Models
        53455, -- 2510.11052 Latent Refinement Decoding: Enhancing Diffusion-Based Language Models by   Refin
        53868, -- 2510.22010 FlowOpt: Fast Optimization Through Whole Flow Processes for   Training-Free Edit
        55524, -- 2601.17617 Agentic Search in the Wild: Intents and Trajectory Dynamics from 14M+ Real Searc
        55717, -- 2602.03845 Parallel-Probe: Towards Efficient Parallel Thinking via 2D Probing
        56738, -- 2603.12529 TERMINATOR: Learning Optimal Exit Points for Early Stopping in Chain-of-Thought
        57086, -- 2603.28696 AdaptToken: Entropy-based Adaptive Token Selection for MLLM Long Video Understan
        57365, -- 2602.06057 QEIL v2: Heterogeneous Computing for Edge Intelligence via Roofline-Derived Pare
        57700, -- 2604.21375 VLAA-GUI: Knowing When to Stop, Recover, and Search, A Modular Framework for GUI
        59046, -- 2603.21250 Graph of States: Solving Abductive Tasks with Large Language Models
        59912, -- 2603.03800 A Rubric-Supervised Critic from Sparse Real-World Outcomes
        60024, -- 2603.02293 The Malignant Tail: Spectral Segregation of Label Noise in Over-Parameterized Ne
        60253, -- 2602.22575 S2O: Early Stopping for Sparse Attention via Online Permutation
        60888, -- 2602.10117 Biases in the Blind Spot: Detecting What LLMs Fail to Mention
        61400, -- 2602.02704 InfMem: Learning System-2 Memory Control for Long-Context Agent
        61684, -- 2601.23155 SPICE: Submodular Penalized Information-Conflict Selection for Efficient Large L
        61958, -- 2601.19827 When Iterative RAG Beats Ideal Evidence: A Diagnostic Study in Scientific Multi-
        62138, -- 2601.16713 CER-HV: A CER-Based Human-in-the-Loop Framework for Cleaning Datasets Applied to
        63392, -- 2512.20362 CRAFT: Continuous Reasoning and Agentic Feedback Tuning for Multimodal Text-to-I
        65913, -- 2510.21366 BADiff: Bandwidth Adaptive Diffusion Model
        66292, -- 2510.14885 You May Speak Freely: Improving the Fine-Grained Visual Recognition Capabilities
        66597, -- 2510.10103 Stop When Enough: Adaptive Early-Stopping for Chain-of-Thought Reasoning
        66729, -- 2510.08146 Think Just Enough: Sequence-Level Entropy as a Confidence Signal for LLM   Reaso
        67384, -- 2509.25420 Adaptive Test-Time Reasoning via Reward-Guided Dual-Phase Search
        67941, -- 2509.19063 Beyond Backpropagation: Exploring Innovative Algorithms for   Energy-Efficient D
        68226, -- 2509.14547 (P)rior(D)yna(F)low: A Priori Dynamic Workflow Construction via   Multi-Agent Co
        68262, -- 2509.14004 Early Stopping Chain-of-thoughts in Large Language Models
        68341, -- 2509.12618 ActiveVLN: Towards Active Exploration via Multi-Turn RL in   Vision-and-Language
        69036, -- 2508.20816 Multi-Agent Penetration Testing AI for the Web
        69266, -- 2508.17291 Meta-R1: Empowering Large Reasoning Models with Metacognition
        69621, -- 2508.11428 ImagiDrive: A Unified Imagination-and-Planning Framework for Autonomous Driving
        72346, -- 2506.02536 Answer Convergence as a Signal for Early Stopping in Reasoning
        75840, -- 2411.04995 LoFi: Neural Local Fields for Scalable Image Reconstruction
        76491, -- 2408.17017 Reasoning Aware Self-Consistency: Leveraging Reasoning Paths for Efficient LLM S
        83867, -- 2605.27028 Less is More: Early Stopping Rollout for On-Policy Distillation
        86741, -- 2501.16226 The Effect of Optimal Self-Distillation in Noisy Gaussian Mixture Model
        86865, -- 2506.02318 Absorb and Converge: Provable Convergence Guarantee for Absorbing Discrete Diffu
        87309, -- 2506.12693 Zero-shot Denoising via Neural Compression: Theoretical and algorithmic framewor
        87502, -- 2605.29860 ESPO: Early-Stopping Proximal Policy Optimization
        88381, -- 2503.05182 MGSR: 2D/3D Mutual-boosted Gaussian Splatting for High-fidelity Surface Reconstr
        88851, -- 2506.19031 When Diffusion Models Memorize: Inductive Biases in Probability Flow of Minimum-
        90711, -- 2412.18219 Adapter Merging with Centroid Prototype Mapping for Scalable Class-Incremental L
        91412, -- 2410.02321 Convergence of Score-Based Discrete Diffusion Models: A Discrete-Time Analysis
        92547, -- 2606.01993 MMG2Skill: Can Agents Distill In-the-Wild Guides into Self-Evolving Skills?
        92572, -- 2606.03965 Agentic Chain-of-Thought Steering for Efficient and Controllable LLM Reasoning
        93970, -- 2603.00527 TP-Spikformer: Token Pruned Spiking Transformer
        94007, -- 2506.13772 MobiEdit: Resource-efficient Knowledge Editing for Personalized On-device LLMs
        94102, -- 2601.21494 THE PATH OF LEAST RESISTANCE: GUIDING LLM REASONING TRAJECTORIES WITH PREFIX CON
        94284, -- 2510.13972 Distributional Consistency Loss: Beyond Pointwise Data Terms in Inverse Problems
        94486, -- 2510.14543 Exploring Cross-Modal Flows for Few-Shot  Learning
        98069, -- external FORGE — Continual Learning for fMRI-Based Brain Disorder Diagnosis (AutoSOTA)
        98081, -- external Revisiting F‑measure Optimization in Multi‑Label Classification: A Sampling‑base
        98914, -- 2606.27771 NormGuard: Reward-Preserving Norm Constraints in Flow-Matching Reinforcement Lea
        99109, -- external Can Small Language Models Know What They Don’t Know?
        99495, -- 2605.19491 Thinking in Scales: Accelerating Gigapixel Pathology Image Analysis via  Adaptiv
        100161, -- 2605.13278 Proximal-Based Generative Modeling for Bayesian Inverse Problems
        100398, -- 2601.22409 Optimization,  Generalization and Differential Privacy Bounds for Gradient Desce
        100779, -- 2510.08409 Optimal Stopping in Latent Diffusion Models
        101216, -- 2509.21906 Error Analysis of Discrete Flow with Generator Matching
        101302, -- 2602.01476 Conformal Prediction for Early Stopping in Mixed Integer Optimization
        101331, -- 2602.13935 Statistical Early Stopping for Reasoning Models
        101542, -- 2603.20967 Hard labels sampled from sparse targets mislead rotation invariant algorithms
        101706, -- 2510.26277 Do LLMs Signal When They’re Right? Evidence from Neuron Agreement
        101709, -- 2606.15070 Stop When Further Reasoning Won’t Help: Attention-State Adaptive Generation in R
        101768, -- 2605.16567 Automatic Unsupervised Ensemble Outlier Model Selection
        102231, -- 2605.25592 Optimal Design for Multinomial Logit Model with Applications to Best Assortment
        102261, -- 2605.28678 DREAM-R: Multimodal Speculative Reasoning with RL-Based Refined Drafting, Precis
        102296, -- 2511.02130 Re-FORC: Adaptive Reward Prediction for Efficient Chain-of-Thought Reasoning
        106141, -- 2604.26355 Shorthand for Thought: Compressing LLM Reasoning via Entropy-Guided Supertokens
        106155, -- 2604.21057 TRACES: Tagging Reasoning Steps for Adaptive Cost-Efficient Early-Stopping
        106194, -- 2606.31484 Fork-think with Confidence
        106714, -- 2508.13812 Timestep-Compressed Attack on Spiking Neural Networks Through Timestep-Level Bac
        107330, -- 2510.22391 Top-Down Semantic Refinement for Image Captioning
        108849, -- 2601.16596 Attention-MoA: Enhancing Mixture-of-Agents via Inter-Agent Semantic Attention an
        109213, -- 2001.08856 Stochastic Optimization of Plain Convolutional Neural Networks with Simple metho
        109263, -- external ChimeraBoost
        109699, -- 2608.20953 Quantization-Aware Healing: A Practical Recipe for Recovering Compressed, 4-Bit
        109742, -- 2608.23670 Automata from Agent Traces: Failure and Next-Step Prediction
        112802, -- 2402.15429 ProTIP: Probabilistic Robustness Verification on Text-to-Image Diffusion Models
        114980, -- 2407.12780 Hallucination Index: An Image Quality Metric for Generative Reconstruction Model
        123830, -- 2610.25525 StopLoss: Teaching Agents to Predict Failure and Stop Early
        124437, -- 2605.19943 Probabilistic Tiny Recursive Model
        124695, -- 2410.05902 Mini-batch kernel $k$-means
        124759, -- 2605.16396 Beyond MMSE: Enhancing PnP Restoration with ProxiMAP
        125038, -- 2607.01571 Geometric Signatures of Reasoning: A Spectral Perspective on Task Hardness
        125106, -- 2606.13796 Recursively Trained Diffusion Models: Limiting Collapse Distribution and Spectra
        125525, -- 2605.25230 Boosting Inference with Guided Reasoning: Stochastic Exploration for Recursive M
        125633, -- external Backtracking with Linear-in-Depth Search-Space Growth: Width-Limited Tree Search
        125962, -- external StepBack: Step-Level Error-Localized Resampling for Efficient Test-Time Reasonin
        126147, -- 2602.02928 Distance Marching for Generative Modeling
        126821, -- external Calibrated Target Noise Recovers Curvature from the Gradients
        127008, -- 2605.05436 Estimating Implicit Regularization in Deep Learning
        128125, -- external Cross-Fitting for Neural Posterior Estimation
        129136, -- external DSSA: Dynamic Sparse Semantic Anchoring for Purifying Protective Perturbations a
        130008, -- external Sparse Updates Generalize Better Than Optimization: Stability Analysis for Rando
        130150, -- 2606.27694 Halt Fast! Early Stopping for Certified Robustness
        130166, -- external Latent Refinement Decoding: Enhancing Diffusion Language Models by Refining Beli
        130336, -- 2602.17608 Towards Anytime-Valid Statistical Watermarking
        131276  -- external Base Items Overfit, New Items Underfit: Hidden Cost of Joint Training in Increme
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
        420, -- 1606.08415 Gaussian Error Linear Units (GELUs)
        3096, -- 2002.05202 GLU Variants Improve Transformer
        4761, -- 2012.10495 ShineOn: Illuminating Design Choices for Practical Video-based Virtual Clothing
        4859, -- 2101.01321 I-BERT: Integer-only BERT Quantization
        8652, -- 2204.04676 Simple Baselines for Image Restoration
        9682, -- 2207.01405 I-ViT: Integer-only Quantization for Efficient Vision Transformer Inference
        11031, -- 2210.13452 MetaFormer Baselines for Vision
        11584, -- 2211.13402 MP-GELU Bayesian Neural Networks: Moment Propagation by GELU Nonlinearity
        11609, -- 2211.13955 MPCViT: Searching for Accurate and Efficient MPC-Friendly Vision Transformer wit
        15819, -- 2305.12073 GELU Activation Function in Deep Learning: A Comprehensive Mathematical Analysis
        16553, -- 2305.18691 Edge-MoE: Memory-Efficient Multi-Task Vision Transformer Architecture with Task-
        18565, -- 2307.12533 PUMA: Secure Inference of LLaMA-7B in Five Minutes
        21525, -- 2310.04564 ReLU Strikes Back: Exploiting Activation Sparsity in Large Language Models
        26642, -- 2402.01169 Faster Inference of Integer SWIN Transformer by Removing the GELU Activation
        26782, -- 2402.02593 Leveraging Continuously Differentiable Activation Functions for Learning in Quan
        27715, -- 2402.13516 ProSparse: Introducing and Enhancing Intrinsic Activation Sparsity within Large
        31479, -- 2405.12954 A Method on Searching Better Activation Functions
        32120, -- 2405.20768 Expanded Gating Ranges Improve Activation Functions
        32274, -- 2406.02021 MetaMixer Is All You Need
        33558, -- 2406.16282 Reducing Fine-Tuning Memory Overhead by Approximate and Memory-Sharing Backpropa
        34870, -- 2407.12951 AdaLog: Post-Training Quantization for Vision Transformers with Adaptive Logarit
        38372, -- 2410.09637 ReLU's Revival: On the Entropic Overload in Normalization-Free Large Language Mo
        38663, -- 2410.13060 AERO: Softmax-Only LLMs for Efficient Private Inference
        43900, -- 2502.06018 Kolmogorov-Arnold Fourier Networks
        47229, -- 2504.02508 APHQ-ViT: Post-Training Quantization with Average Perturbation Hessian Based Rec
        68456, -- 2509.10334 I-Segmenter: Integer-Only Vision Transformer for Efficient Semantic   Segmentati
        72498, -- 2506.00291 Improving Code Switching with Supervised Fine Tuning and GELU Adapters
        72531, -- 2505.23942 SG-Blend: Learning an Interpolation Between Improved Swish and GELU for Robust N
        87671, -- 2503.03088 AHCPTQ: Accurate and Hardware-Compatible Post-Training Quantization for Segment
        100688, -- 2605.29497 Convex Basins in Single-Index Model Loss Landscapes: Applications to Robust Reco
        125556  -- 2601.22307 Exact Gaussian Moment Matching for Residual Networks: a Second-Order Method
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
        2020, -- 1904.09077 Beto, Bentz, Becas: The Surprising Cross-Lingual Effectiveness of BERT
        2034, -- 1904.10509 Generating Long Sequences with Sparse Transformers
        2086, -- 1905.04226 Language Modeling with Deep Transformers
        2151, -- 1905.11946 EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks
        2366, -- 1907.10529 SpanBERT: Improving Pre-training by Representing and Predicting Spans
        2369, -- 1907.11692 RoBERTa: A Robustly Optimized BERT Pretraining Approach
        2412, -- 1908.04577 StructBERT: Incorporating Language Structures into Pre-training for Deep Languag
        2539, -- 1909.05855 Towards Scalable Multi-domain Conversational Agents: The Schema-Guided Dialogue
        2587, -- 1909.11299 Mixout: Effective Regularization to Finetune Large-scale Pretrained Language Mod
        2600, -- 1909.11942 ALBERT: A Lite BERT for Self-supervised Learning of Language Representations
        2735, -- 1910.12607 Generative Pre-Training for Speech with Autoregressive Predictive Coding
        2744, -- 1910.13461 BART: Denoising Sequence-to-Sequence Pre-training for Natural Language Generatio
        2834, -- 1911.09070 EfficientDet: Scalable and Efficient Object Detection
        2985, -- 2001.02811 Distributional Soft Actor-Critic: Off-Policy Reinforcement Learning for Addressi
        3087, -- 2002.04013 Towards Crowdsourced Training of Large Neural Networks using Decentralized Mixtu
        3303, -- 2004.02967 Evolving Normalization-Activation Layers
        3328, -- 2004.04487 Injecting Numerical Reasoning Skills into Language Models
        3388, -- 2004.09602 Integer Quantization for Deep Learning Inference: Principles and Empirical Evalu
        3449, -- 2004.14255 Efficient Document Re-Ranking for Transformers by Precomputing Term Representati
        3598, -- 2005.09561 Normalized Attention Without Probability Cage
        3773, -- 2006.11477 wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Representations
        3797, -- 2006.13979 Unsupervised Cross-lingual Representation Learning for Speech Recognition
        3849, -- 2007.00992 Rethinking Channel Dimensions for Efficient Model Design
        3991, -- 2008.02275 Aligning AI With Shared Human Values
        4199, -- 2009.11152 Hierarchical Pre-training for Sequence Labelling in Spoken Dialog
        4214, -- 2009.12677 KG-BART: Knowledge Graph-Augmented BART for Generative Commonsense Reasoning
        4244, -- 2010.01057 LUKE: Deep Contextualized Entity Representations with Entity-aware Self-attentio
        4377, -- 2010.09931 Smooth activations and reproducibility in deep networks
        4495, -- 2011.01513 CharBERT: Character-aware Pre-trained Language Model
        4637, -- 2011.14522 Feature Learning in Infinite-Width Neural Networks
        4646, -- 2012.00451 Just Ask: Learning to Answer Questions from Millions of Narrated Videos
        4706, -- 2012.05329 Know Your Limits: Uncertainty Estimation with ReLU Classifiers Fails at Reliable
        4755, -- 2012.09838 Transformer Interpretability Beyond Attention Visualization
        4782, -- 2012.12877 Training data-efficient image transformers & distillation through attention
        4820, -- 2012.15562 UNKs Everywhere: Adapting Multilingual Language Models to New Scripts
        4823, -- 2012.15674 ERNIE-M: Enhanced Multilingual Representation by Aligning Cross-lingual Semantic
        4923, -- 2101.08692 Characterizing signal propagation to close the performance gap in unnormalized R
        4955, -- 2101.11605 Bottleneck Transformers for Visual Recognition
        5022, -- 2102.06171 High-Performance Large-Scale Image Recognition Without Normalization
        5046, -- 2102.08380 Topological Obstructions to Autoencoding
        5084, -- 2102.11972 Do Transformer Modifications Transfer Across Implementations and Applications?
        5108, -- 2103.00020 Learning Transferable Visual Models From Natural Language Supervision
        5112, -- 2103.00112 Transformer in Transformer
        5143, -- 2103.03206 Perceiver: General Perception with Iterative Attention
        5163, -- 2103.05247 Pretrained Transformers as Universal Computation Engines
        5188, -- 2103.06877 Fast and Accurate Model Scaling
        5197, -- 2103.07762 OkwuGbé: End-to-End Speech Recognition for Fon and Igbo
        5229, -- 2103.10619 Scalable Vision Transformers with Hierarchical Pooling
        5259, -- 2103.12731 Scaling Local Self-Attention for Parameter Efficient Visual Backbones
        5269, -- 2103.13413 Vision Transformers for Dense Prediction
        5272, -- 2103.13630 A Survey of Quantization Methods for Efficient Neural Network Inference
        5306, -- 2103.15691 ViViT: A Video Vision Transformer
        5395, -- 2104.03602 SiT: Self-supervised vIsion Transformer
        5396, -- 2104.03642 CLIMAT: Clinically-Inspired Multi-Agent Transformers for Knee Osteoarthritis Tra
        5428, -- 2104.05845 Visual Goal-Step Inference using wikiHow
        5454, -- 2104.07012 Sparse Attention with Linear Units
        5458, -- 2104.07091 SummScreen: A Dataset for Abstractive Screenplay Summarization
        5562, -- 2104.11178 VATT: Transformers for Multimodal Self-Supervised Learning from Raw Video, Audio
        5563, -- 2104.11227 Multiscale Vision Transformers
        5638, -- 2105.01601 MLP-Mixer: An all-MLP Architecture for Vision
        5667, -- 2105.03404 ResMLP: Feedforward networks for image classification with data-efficient traini
        5732, -- 2105.07581 Vision Transformers are Robust Learners
        5741, -- 2105.08049 SGD-QA: Fast Schema-Guided Dialogue State Tracking for Unseen Services
        5742, -- 2105.08050 Pay Attention to MLPs
        5750, -- 2105.08582 Vision Transformer for Fast and Efficient Scene Text Recognition
        5808, -- 2105.14217 Less is More: Pay Less Attention in Vision Transformers
        5836, -- 2106.00666 You Only Look at One Sequence: Rethinking Transformer in Vision through Object D
        5856, -- 2106.01342 SAINT: Improved Neural Networks for Tabular Data via Row Attention and Contrasti
        5860, -- 2106.01548 When Vision Transformers Outperform ResNets without Pre-training or Strong Data
        5893, -- 2106.03106 Uformer: A General U-Shaped Transformer for Image Restoration
        5917, -- 2106.04489 Parameter-efficient Multi-task Fine-tuning for Transformers via Shared Hypernetw
        5920, -- 2106.04554 A Survey of Transformers
        5926, -- 2106.04647 Compacter: Efficient Low-Rank Hypercomplex Adapter Layers
        5928, -- 2106.04803 CoAtNet: Marrying Convolution and Attention for All Data Sizes
        5951, -- 2106.05784 Programming Puzzles
        5957, -- 2106.05974 Scaling Vision with Sparse Mixture of Experts
        6101, -- 2106.12607 Dealing with training and test segmentation mismatch: FBK@IWSLT2021
        6102, -- 2106.12620 IA-RED$^2$: Interpretability-Aware Redundancy Reduction for Vision Transformers
        6123, -- 2106.13797 PVT v2: Improved Baselines with Pyramid Vision Transformer
        6184, -- 2107.02137 ERNIE 3.0: Large-scale Knowledge Enhanced Pre-training for Language Understandin
        6256, -- 2107.07467 Only Train Once: A One-Shot Neural Network Training And Pruning Framework
        6275, -- 2107.08807 Simultaneous Speech Translation for Live Subtitling: from Delay to Display
        6303, -- 2107.11414 Brazilian Portuguese Speech Recognition Using Wav2vec 2.0
        6310, -- 2107.12342 Sisyphus: A Cautionary Tale of Using Low-Degree Polynomial Activations in Privac
        6317, -- 2107.12930 gaBERT -- an Irish Language Model
        6333, -- 2107.14795 Perceiver IO: A General Architecture for Structured Inputs & Outputs
        6395, -- 2108.04384 RaftMLP: How Much Can Be Done Without Attention and with Less Spatial Locality?
        6401, -- 2108.04927 Embodied BERT: A Transformer Model for Embodied, Language-guided Visual Task Com
        6517, -- 2108.13672 SANSformers: Self-Supervised Forecasting in Electronic Health Records with Atten
        6532, -- 2109.00642 Searching for Efficient Multi-Stage Vision Transformers
        6689, -- 2109.09701 BARTpho: Pre-trained Sequence-to-Sequence Models for Vietnamese
        6738, -- 2109.13210 SAU: Smooth activation function using convolution with approximate identities
        6745, -- 2109.13995 IGLU: Efficient GCN Training via Lazy Updates
        6748, -- 2109.14084 VideoCLIP: Contrastive Pre-training for Zero-shot Video-Text Understanding
        6754, -- 2109.14545 Activation Functions in Deep Learning: A Comprehensive Survey and Benchmark
        6788, -- 2110.01786 MoEfication: Transformer Feed-forward Layers are Mixtures of Experts
        6869, -- 2110.05006 Pre-trained Language Models in Biomedical Domain: A Systematic Survey
        6879, -- 2110.05781 BERTraffic: BERT-based Joint Speaker Role and Speaker Change Detection for Air T
        6927, -- 2110.07143 bert2BERT: Towards Reusable Pretrained Language Models
        6930, -- 2110.07181 Relation-aware Heterogeneous Graph for User Profiling
        7002, -- 2110.09456 NormFormer: Improved Transformer Pretraining with Extra Normalization
        7166, -- 2111.03600 Hybrid Spectrogram and Waveform Source Separation
        7188, -- 2111.05297 Sliced Recursive Transformer
        7258, -- 2111.09881 Restormer: Efficient Transformer for High-Resolution Image Restoration
        7276, -- 2111.11124 Mesa: A Memory-saving Training Framework for Transformers
        7281, -- 2111.11418 MetaFormer Is Actually What You Need for Vision
        7282, -- 2111.11429 Benchmarking Detection Transfer Learning with Vision Transformers
        7575, -- 2112.10684 Efficient Large Scale Language Modeling with Mixtures of Experts
        7610, -- 2112.13692 Augmenting Convolutional networks with attention-based aggregation
        7614, -- 2112.14397 EvoMoE: An Evolutional Mixture-of-Experts Training Framework via Dense-To-Sparse
        7668, -- 2201.02973 MAXIM: Multi-Axis MLP for Image Processing
        7673, -- 2201.03545 A ConvNet for the 2020s
        7758, -- 2201.09792 Patches Are All You Need?
        7912, -- 2202.04350 pNLP-Mixer: an Efficient all-MLP Architecture for Language
        7922, -- 2202.04774 SHAS: Approaching optimal Segmentation for End-to-End Speech Translation
        7976, -- 2202.07765 General-purpose, long-context autoregressive modeling with Perceiver AR
        7979, -- 2202.07800 Not All Patches are What You Need: Expediting Vision Transformers via Token Reor
        8004, -- 2202.08906 ST-MoE: Designing Stable and Transferable Sparse Expert Models
        8011, -- 2202.09368 Mixture-of-Experts with Expert Choice Routing
        8017, -- 2202.09729 It's Raw! Audio Generation with State-Space Models
        8018, -- 2202.09741 Visual Attention Network
        8023, -- 2202.10103 Robustness and Accuracy Could Be Reconcilable by (Proper) Definition
        8169, -- 2203.03691 HyperMixer: An MLP-based Low Cost Alternative to Transformers
        8215, -- 2203.06125 Protein Representation Learning by Geometric Structure Pretraining
        8229, -- 2203.06717 Scaling Up Your Kernels to 31x31: Revisiting Large Kernel Design in CNNs
        8257, -- 2203.07682 Enriched CNN-Transformer Feature Aggregation Networks for Super-Resolution
        8311, -- 2203.09183 RoMe: A Robust Metric for Evaluating Natural Language Generation
        8326, -- 2203.09795 Three things everyone should know about Vision Transformers
        8383, -- 2203.11926 Focal Modulation Networks
        8439, -- 2203.14343 Diagonal State Spaces are as Effective as Structured State Spaces
        8454, -- 2203.14680 Transformer Feed-Forward Layers Build Predictions by Promoting Concepts in the V
        8497, -- 2203.16527 Exploring Plain Vision Transformer Backbones for Object Detection
        8504, -- 2203.16822 How Does Pre-trained Wav2Vec 2.0 Perform on Domain Shifted ASR? An Extensive Ben
        8536, -- 2204.00673 Learnable latent embeddings for joint behavioral and neural analysis
        8547, -- 2204.01172 PERFECT: Prompt-free and Efficient Few-shot Learning with Language Models
        8560, -- 2204.01697 MaxViT: Multi-Axis Vision Transformer
        8595, -- 2204.02964 Unleashing Vanilla Vision Transformer with Masked Image Modeling for Object Dete
        8629, -- 2204.03883 Vision Transformers for Single Image Dehazing
        8630, -- 2204.03905 BioBART: Pretraining and Evaluation of A Biomedical Generative Language Model
        8722, -- 2204.07154 MiniViT: Compressing Vision Transformers with Weight Multiplexing
        8784, -- 2204.09149 DialoKG: Knowledge-Structure Aware Task-Oriented Dialogue Generation
        8840, -- 2204.11824 Semi-Parametric Neural Image Synthesis
        8882, -- 2204.14198 Flamingo: a Visual Language Model for Few-Shot Learning
        8928, -- 2205.01972 Sequencer: Deep LSTM for Image Classification
        8975, -- 2205.04437 Activating More Pixels in Image Super-Resolution Transformer
        8986, -- 2205.05019 Learning to Answer Visual Questions from Web Videos
        8989, -- 2205.05076 Reduce Information Loss in Transformers for Pluralistic Image Inpainting
        9012, -- 2205.06175 A Generalist Agent
        9137, -- 2205.11588 Simple Recurrence Improves Masked Language Models
        9206, -- 2205.13213 Fast Vision Transformers with HiLo Attention
        9210, -- 2205.13268 MemeTector: Enforcing deep focus for meme detection
        9219, -- 2205.13535 AdaptFormer: Adapting Vision Transformers for Scalable Visual Recognition
        9246, -- 2205.14304 Multimodal Fake News Detection via CLIP-Guided Learning
        9363, -- 2206.02096 PEER: A Comprehensive and Multi-Task Benchmark for Protein Sequence Understandin
        9413, -- 2206.04040 MobileOne: An Improved One millisecond Mobile Backbone
        9449, -- 2206.05836 GLIPv2: Unifying Localization and Vision-Language Understanding
        9536, -- 2206.09457 All you need is feedback: Communication with block attention feedback codes
        9550, -- 2206.09959 Global Context Vision Transformers
        9564, -- 2206.10589 EdgeNeXt: Efficiently Amalgamated CNN-Transformer Architecture for Mobile Vision
        9634, -- 2206.14331 Spherical Channels for Modeling Atomic Interactions
        9650, -- 2206.15369 No Reason for No Supervision: Improved Generalization in Supervised Models
        9696, -- 2207.02505 Pure Transformers are Powerful Graph Learners
        9702, -- 2207.02971 Branchformer: Parallel MLP-Attention Architectures to Capture Local and Global C
        9810, -- 2207.08082 CATRE: Iterative Point Clouds Alignment for Category-level Object Pose Refinemen
        9847, -- 2207.09966 Temporal and cross-modal attention for audio-visual zero-shot learning
        9866, -- 2207.10666 TinyViT: Fast Pretraining Distillation for Small Vision Transformers
        10011, -- 2208.04933 Simplified State Space Layers for Sequence Modeling
        10093, -- 2208.09846 A Contrastive Pre-training Approach to Learn Discriminative Autoencoder for Dens
        10142, -- 2208.12256 Masked Autoencoders Enable Efficient Knowledge Distillers
        10143, -- 2208.12266 Decoding speech perception from non-invasive brain recordings
        10146, -- 2208.12408 User-Controllable Latent Transformer for StyleGAN Image Layout Editing
        10187, -- 2208.15001 MotionDiffuse: Text-Driven Human Motion Generation with Diffusion Model
        10243, -- 2209.03895 IDIAPers @ Causal News Corpus 2022: Efficient Causal Relation Identification Thr
        10389, -- 2209.11448 Rethinking Performance Gains in Image Dehazing Networks
        10468, -- 2209.14988 DreamFusion: Text-to-3D using 2D Diffusion
        10490, -- 2209.15611 Protein structure generation via folding diffusion
        10494, -- 2210.00077 E-Branchformer: Branchformer with Enhanced merging for speech recognition
        10505, -- 2210.00313 CRISP: Curriculum based Sequential Neural Decoders for Polar Code Family
        10536, -- 2210.01351 Less is More: Task-aware Layer-wise Distillation for Language Model Compression
        10550, -- 2210.01820 MOAT: Alternating Mobile Convolution and Attention Brings Strong Vision Models
        10578, -- 2210.02414 GLM-130B: An Open Bilingual Pre-trained Model
        10599, -- 2210.03052 ByteTransformer: A High-Performance Transformer Boosted for Variable-Length Inpu
        10699, -- 2210.05287 Revisiting and Advancing Chinese Natural Language Understanding with Accelerated
        10735, -- 2210.05958 Bridging the Gap Between Vision Transformers and Convolutional Neural Networks o
        10825, -- 2210.08073 Eliciting Compatible Demonstrations for Multi-Human Imitation Learning
        10836, -- 2210.08457 Scratching Visual Transformer's Back with Uniform Attention
        10881, -- 2210.10048 AnalogVNN: A fully modular framework for modeling and optimizing photonic neural
        10893, -- 2210.10260 End-to-End Entity Detection with Proposer and Regressor
        10939, -- 2210.11633 Graphically Structured Diffusion Models
        11049, -- 2210.13889 Clinically-Inspired Multi-Agent Transformers for Disease Trajectory Forecasting
        11079, -- 2210.14793 M$^3$ViT: Mixture-of-Experts Vision Transformer for Efficient Multi-task Learnin
        11098, -- 2210.15424 What Language Model to Train if You Have One Million GPU Hours?
        11122, -- 2210.16264 Efficient Speech Translation with Dynamic Latent Perceivers
        11257, -- 2211.04054 ATCO2 corpus: A Large-Scale Dataset for Research on Automatic Speech Recognition
        11263, -- 2211.04236 Self-conditioned Embedding Diffusion for Text Generation
        11297, -- 2211.05778 InternImage: Exploring Large-Scale Vision Foundation Models with Deformable Conv
        11361, -- 2211.08253 HMOE: Hypernetwork-based Mixture of Experts for Domain Generalization
        11388, -- 2211.09085 Galactica: A Large Language Model for Science
        11404, -- 2211.09552 UniFormerV2: Spatiotemporal Learning by Arming Image ViTs with Video UniFormer
        11410, -- 2211.09707 Listen, Denoise, Action! Audio-Driven Motion Synthesis with Diffusion Models
        11412, -- 2211.09760 VeLO: Training Versatile Learned Optimizers by Scaling Up
        11413, -- 2211.09761 Efficient Transformers with Dynamic Token Pooling
        11452, -- 2211.10705 TORE: Token Reduction for Efficient Human Mesh Recovery with Transformer
        11573, -- 2211.13189 ASiT: Local-Global Audio Spectrogram vIsion Transformer for Event Classification
        11608, -- 2211.13916 Towards Good Practices for Missing Modality Robust Action Recognition
        11623, -- 2211.14308 WALDO: Future Video Synthesis using Object Layer Decomposition and Parametric Fl
        11627, -- 2211.14453 Transform Once: Efficient Operator Learning in Frequency Domain
        11634, -- 2211.14575 Efficient Video Prediction via Sparsely Conditioned Flow Matching
        11642, -- 2211.14730 A Time Series is Worth 64 Words: Long-term Forecasting with Transformers
        11644, -- 2211.14813 SegCLIP: Patch Aggregation with Learnable Centers for Open-Vocabulary Semantic S
        11671, -- 2211.15661 What learning algorithm is in-context learning? Investigations with linear model
        11687, -- 2211.16056 NoisyQuant: Noisy Bias-Enhanced Post-Training Activation Quantization for Vision
        11723, -- 2211.17192 Fast Inference from Transformers via Speculative Decoding
        11843, -- 2212.03434 Name Your Colour For the Task: Artificially Discover Colour Naming via Colour Qu
        11869, -- 2212.04356 Robust Speech Recognition via Large-Scale Weak Supervision
        11904, -- 2212.05199 MAGVIT: Masked Generative Video Transformer
        11975, -- 2212.07525 Efficient Self-supervised Learning with Contextualized Target Representations fo
        11985, -- 2212.07677 Transformers learn in-context by gradient descent
        12004, -- 2212.08057 Real-Time Neural Light Field on Mobile Devices
        12027, -- 2212.08641 GFPose: Learning 3D Human Pose Prior with Gradient Fields
        12070, -- 2212.09462 Latent Diffusion for Language Generation
        12084, -- 2212.09699 SegAugment: Maximizing the Utility of Speech Translation Data with Segmentation-
        12095, -- 2212.09748 Scalable Diffusion Models with Transformers
        12148, -- 2212.10544 Pretraining Without Attention
        12198, -- 2212.11972 Scalable Adaptive Computation for Iterative Generation
        12230, -- 2212.13350 A Generalization of ViT/MLP-Mixer to Graphs
        12288, -- 2301.01146 Rethinking Mobile Block for Efficient Attention-based Models
        12330, -- 2301.02555 "No, to the Right" -- Online Language Corrections for Robotic Manipulation via S
        12343, -- 2301.03046 STPrivacy: Spatio-Temporal Privacy-Preserving Action Recognition
        12345, -- 2301.03110 RobArch: Designing Robust Architectures against Adversarial Attacks
        12363, -- 2301.04104 Mastering Diverse Domains through World Models
        12387, -- 2301.05062 Tracr: Compiled Transformers as a Laboratory for Interpretability
        12416, -- 2301.06568 Ankh: Optimized Protein Language Model Unlocks General-Purpose Modelling
        12419, -- 2301.06719 FemtoDet: An Object Detection Baseline for Energy Versus Performance Tradeoffs
        12439, -- 2301.07608 Human-Timescale Adaptation in an Open-Ended Task Space
        12467, -- 2301.08965 Raw or Cooked? Object Detection on RAW Images
        12527, -- 2301.10857 Improving Graph Generation by Restricting Graph Bandwidth
        12564, -- 2301.11355 Rigid Body Flows for Sampling Molecular Crystal Structures
        12744, -- 2302.00341 Reverse Ordering Techniques for Attention-Based Channel Prediction
        12750, -- 2302.00456 Analyzing Feed-Forward Blocks in Transformers through the Lens of Attention Maps
        12839, -- 2302.02228 Counterfactual Identifiability of Bijective Causal Models
        12980, -- 2302.04638 Better Diffusion Models Further Improve Adversarial Training
        13000, -- 2302.04953 The Monge Gap: A Regularizer to Learn All Transport Maps
        13068, -- 2302.06594 Geometric Clifford Algebra Networks
        13218, -- 2302.10351 Variational Autoencoding Neural Operators
        13261, -- 2302.11640 A critical look at the evaluation of GNNs under heterophily: Are we really makin
        13263, -- 2302.11716 VRA: Variational Rectified Activation for Out-of-distribution Detection
        13307, -- 2302.12766 Language-Driven Representation Learning for Robotics
        13349, -- 2302.14045 Language Is Not All You Need: Aligning Perception with Language Models
        13368, -- 2302.14367 BrainBERT: Self-supervised representation learning for intracranial recordings
        13534, -- 2303.03667 Run, Don't Walk: Chasing Higher FLOPS for Faster Neural Networks
        13555, -- 2303.04185 Gradient-Free Structured Pruning with Unlabeled Data
        13626, -- 2303.05689 Inducing Neural Collapse to a Fixed Hierarchy-Aware Frame for Reducing Mistake S
        13697, -- 2303.06911 ViM: Vision Middleware for Unified Downstream Transferring
        13740, -- 2303.07726 Good Neighbors Are All You Need for Chinese Grapheme-to-Phoneme Conversion
        13782, -- 2303.08566 Sensitivity-Aware Visual Parameter-Efficient Fine-Tuning
        13796, -- 2303.08891 ViTO: Vision Transformer-Operator
        13845, -- 2303.09663 Efficient Computation Sharing for Multi-Task Visual Scene Understanding
        13858, -- 2303.09859 Trained on 100 million words and still in shape: BERT meets British National Cor
        13935, -- 2303.11331 EVA-02: A Visual Representation for Neon Genesis
        14038, -- 2303.13047 Towards Better Dynamic Graph Learning: New Architecture and Unified Library
        14132, -- 2303.14526 Selective Structured State-Spaces for Long-Form Video Understanding
        14175, -- 2303.15230 Troika: Multi-Path Cross-Modal Traction for Compositional Zero-Shot Learning
        14177, -- 2303.15247 Zero-Shot Composed Image Retrieval with Textual Inversion
        14272, -- 2303.16900 InceptionNeXt: When Inception Meets ConvNeXt
        14308, -- 2303.17564 BloombergGPT: A Large Language Model for Finance
        14309, -- 2303.17568 CodeGeeX: A Pre-Trained Model for Code Generation with Multilingual Benchmarking
        14349, -- 2303.18223 A Survey of Large Language Models
        14424, -- 2304.01483 Blockwise Compression of Transformer-based Models without Retraining
        14475, -- 2304.02472 Learning to Predict Short-Term Volatility with Order Flow Image Representation
        14487, -- 2304.02643 Segment Anything
        14507, -- 2304.03282 Visual Dependency Transformers: Dependency Tree Emerges from Reversed Attention
        14533, -- 2304.03768 SparseFormer: Sparse Visual Recognition via Limited Latent Tokens
        14711, -- 2304.07288 Cross-Entropy Loss Functions: Theoretical Analysis and Applications
        14722, -- 2304.07645 Magnitude Invariant Parametrizations Improve Hypernetwork Learning
        14779, -- 2304.09148 SAM Fails to Segment Anything? -- SAM-Adapter: Adapting SAM in Underperformed Sc
        14881, -- 2304.11267 Speed Is All You Need: On-Device Acceleration of Large Diffusion Models via GPU-
        15012, -- 2304.14118 Learning Neural PDE Solvers with Parameter-Guided Channel Attention
        15027, -- 2304.14369 Learning Neural Constitutive Laws From Motion Observations for Generalizable PDE
        15147, -- 2305.01610 Finding Neurons in a Haystack: Case Studies with Sparse Probing
        15150, -- 2305.01638 Sequence Modeling with Multiresolution Convolutional Memory
        15199, -- 2305.02463 Shap-E: Generating Conditional 3D Implicit Functions
        15212, -- 2305.02644 Neuralizer: General Neuroimage Analysis without Re-Training
        15261, -- 2305.03452 A technical note on bilinear layers for interpretability
        15344, -- 2305.04934 Generative Pretrained Autoregressive Transformer Graph Neural Network applied to
        15467, -- 2305.07016 A General-Purpose Multilingual Document Encoder
        15470, -- 2305.07027 EfficientViT: Memory Efficient Vision Transformer with Cascaded Group Attention
        15529, -- 2305.08067 Improving End-to-End SLU performance with Prosodic Attention and Distillation
        15560, -- 2305.08585 Toward Moiré-Free and Detail-Preserving Demosaicking
        15682, -- 2305.10512 IMAD: IMage-Augmented multi-modal Dialogue
        15696, -- 2305.10727 Boost Vision Transformer with GPU-Friendly Sparsity and Quantization
        15774, -- 2305.11579 Speech-Text Dialog Pre-training for Spoken Dialog Understanding with Explicit Cr
        15897, -- 2305.12972 VanillaNet: the Power of Minimalism in Deep Learning
        15905, -- 2305.13050 AudioToken: Adaptation of Text-Conditioned Diffusion Models for Audio-to-Image G
        15955, -- 2305.13501 LaDI-VTON: Latent Diffusion Textual-Inversion Enhanced Virtual Try-On
        15989, -- 2305.13731 Text Is All You Need: Learning Language Representations for Sequential Recommend
        16010, -- 2305.13905 EfficientSpeech: An On-Device Text to Speech Model
        16065, -- 2305.14321 ConGraT: Self-Supervised Contrastive Pretraining for Joint Graph and Text Embedd
        16099, -- 2305.14571 From Characters to Words: Hierarchical Pre-trained Language Model for Open-vocab
        16124, -- 2305.14720 BLIP-Diffusion: Pre-trained Subject Representation for Controllable Text-to-Imag
        16154, -- 2305.14858 Pre-RMSNorm and Pre-CRMSNorm Transformers: Equivalent and Efficient Pre-LN Trans
        16251, -- 2305.15408 Towards Revealing the Mystery behind Chain of Thought: A Theoretical Perspective
        16268, -- 2305.15719 Efficient Neural Music Generation
        16384, -- 2305.16999 Three Towers: Flexible Contrastive Learning with Pretrained Image Models
        16520, -- 2305.18415 Geometric Algebra Transformer
        16559, -- 2305.18703 Domain Specialization as the Key to Make Large Language Models Disruptive: A Com
        16574, -- 2305.18806 Prediction Error-based Classification for Class-Incremental Learning
        16584, -- 2305.18926 Document-Level Multi-Event Extraction with Event Proxy Nodes and Hausdorff Dista
        16618, -- 2305.19268 Intriguing Properties of Quantization at Scale
        16633, -- 2305.19466 The Impact of Positional Encoding on Length Generalization in Transformers
        16774, -- 2306.00789 Improved Cross-Lingual Transfer Learning For Automatic Speech Translation
        16800, -- 2306.00968 GRES: Generalized Referring Expression Segmentation
        16843, -- 2306.01327 Speech Translation with Foundation Models and Optimal Transport: UPC at IWSLT23
        16859, -- 2306.01545 PassGPT: Password Modeling and (Guided) Generation with Large Language Models
        16871, -- 2306.01705 The Information Pathways Hypothesis: Transformers are Dynamic Self-Ensembles
        16880, -- 2306.01736 DaTaSeg: Taming a Universal Multi-Dataset Multi-Task Segmentation Model
        17058, -- 2306.03838 Spherical Fourier Neural Operators: Learning Stable Dynamics on the Sphere
        17189, -- 2306.05426 SequenceMatch: Imitation Learning for Autoregressive Sequence Modelling with Bac
        17243, -- 2306.06189 FasterViT: Fast Vision Transformers with Hierarchical Attention
        17283, -- 2306.06842 AerialFormer: Multi-resolution Transformer for Aerial Image Segmentation
        17285, -- 2306.06849 Mitigating Transformer Overconfidence via Lipschitz Regularization
        17326, -- 2306.07349 ATT3D: Amortized Text-to-3D Object Synthesis
        17367, -- 2306.07892 Robustly Learning a Single Neuron via Sharpness
        17379, -- 2306.07957 Hidden Biases of End-to-End Driving Models
        17425, -- 2306.08625 RRSIS: Referring Remote Sensing Image Segmentation
        17574, -- 2306.10533 Point-Cloud Completion with Pretrained Text-to-image Diffusion Models
        17600, -- 2306.11147 CAT-Walk: Inductive Hypergraph Learning via Set Walks
        17625, -- 2306.11528 TransRef: Multi-Scale Reference Embedding Transformer for Reference-Guided Image
        17759, -- 2306.14393 Constraint-aware and Ranking-distilled Token Pruning for Efficient Transformer I
        17895, -- 2306.17115 Michelangelo: Conditional 3D Shape Generation based on Shape-Image-Text Aligned
        17905, -- 2306.17253 Towards Zero-Shot Scale-Aware Monocular Depth Estimation
        17969, -- 2307.01097 MVDiffusion: Enabling Holistic Multi-view Image Generation with Correspondence-A
        17975, -- 2307.01199 NeuBTF: Neural fields for BTF encoding and transfer
        17995, -- 2307.01759 Pretraining is All You Need: A Multi-Atlas Enhanced Transformer Framework for Au
        18016, -- 2307.02064 Facing Off World Model Backbones: RNNs, Transformers, and S4
        18189, -- 2307.06018 PolyLM: An Open Source Polyglot Large Language Model
        18201, -- 2307.06435 A Comprehensive Overview of Large Language Models
        18280, -- 2307.07982 A Survey of Techniques for Optimizing Transformer Inference
        18325, -- 2307.08621 Retentive Network: A Successor to Transformer for Large Language Models
        18356, -- 2307.09072 Real-time Inference and Extrapolation via a Diffusion-inspired Temporal Transfor
        18472, -- 2307.10936 PASTA: Pretrained Action-State Transformer Agents
        18506, -- 2307.11458 Strip-MLP: Efficient Token Interaction for Vision MLP
        18642, -- 2307.13933 AIDE: A Vision-Driven Multi-View, Multi-Modal, Multi-Tasking Dataset for Assisti
        18677, -- 2307.14403 Unsupervised Deep Learning-based Pansharpening with Jointly-Enhanced Spectral an
        18760, -- 2307.15988 RGB-D-Fusion: Image Conditioned Depth Diffusion of Humanoid Subjects
        18775, -- 2307.16372 LP-MusicCaps: LLM-Based Pseudo Music Captioning
        18781, -- 2307.16418 DRAW: Defending Camera-shooted RAW against Image Manipulation
        18852, -- 2308.01045 Dynamic Token Pruning in Plain Vision Transformers for Semantic Segmentation
        19132, -- 2308.05732 PDE-Refiner: Achieving Accurate Long Rollouts with Neural PDE Solvers
        19156, -- 2308.06103 Composable Function-preserving Expansions for Transformer Architectures
        19204, -- 2308.06744 Token-Scaled Logit Distillation for Ternary Weight Generative Language Models
        19222, -- 2308.07037 Bayesian Flow Networks
        19236, -- 2308.07251 Large-kernel Attention for Efficient and Robust Brain Lesion Segmentation
        19274, -- 2308.07787 DiffV2S: Diffusion-based Video-to-Speech Synthesis with Vision-guided Speaker Em
        19434, -- 2308.09710 SimDA: Simple Diffusion Adapter for Efficient Video Generation
        19443, -- 2308.09804 VL-PET: Vision-and-Language Parameter-Efficient Tuning via Granularity Control
        19455, -- 2308.09903 Scalable Video Object Segmentation with Simplified Framework
        19591, -- 2308.11093 Video OWL-ViT: Temporally-consistent open-world localization in video
        19602, -- 2308.11185 MEGA: Multimodal Alignment Aggregation and Distillation For Cinematic Video Segm
        19659, -- 2308.11796 Time Does Tell: Self-Supervised Time-Tuning of Dense Image Representations
        19706, -- 2308.12284 D4: Improving LLM Pretraining via Document De-Duplication and Diversification
        19829, -- 2308.14061 Hierarchical Contrastive Learning for Pattern-Generalizable Image Corruption Det
        19898, -- 2308.15090 Killing two birds with one stone: Can an audio captioning system also be used fo
        19993, -- 2308.16911 PointLLM: Empowering Large Language Models to Understand Point Clouds
        20052, -- 2309.01213 Implicit regularization of deep residual networks towards neural ODEs
        20153, -- 2309.03072 Character Queries: A Transformer-based Approach to On-Line Handwritten Character
        20206, -- 2309.03905 ImageBind-LLM: Multi-modality Instruction Tuning
        20274, -- 2309.05239 HAT: Hybrid Attention Transformer for Image Restoration
        20308, -- 2309.05858 Uncovering mesa-optimization algorithms in Transformers
        20326, -- 2309.06262 Modality Unifying Network for Visible-Infrared Person Re-Identification
        20343, -- 2309.06589 Do Generative Large Language Models need billions of parameters?
        20353, -- 2309.06721 Dynamic Spectrum Mixer for Visual Recognition
        20422, -- 2309.07778 Virchow: A Million-Slide Digital Pathology Foundation Model
        20474, -- 2309.08480 PoseFix: Correcting 3D Human Poses with Natural Language
        20485, -- 2309.08586 Replacing softmax with ReLU in Vision Transformers
        20606, -- 2309.10402 Minimum width for universal approximation using ReLU networks on compact domain
        20683, -- 2309.11419 KOSMOS-2.5: A Multimodal Literate Model
        20741, -- 2309.12303 PanoVOS: Bridging Non-panoramic and Panoramic Views with Transformer for Video S
        20846, -- 2309.13598 On the Posterior Distribution in Denoising: Application to Uncertainty Quantific
        20895, -- 2309.14322 Small-scale proxies for large-scale Transformer training instabilities
        20914, -- 2309.14568 Introducing DictaLM -- A Large Generative Language Model for Modern Hebrew
        21145, -- 2310.00311 Efficient Planning with Latent Diffusion
        21317, -- 2310.02012 Towards Training Without Depth Limits: Batch Normalization Without Gradient Expl
        21321, -- 2310.02066 De Novo Drug Design with Joint Transformers
        21403, -- 2310.03020 Consistent-1-to-3: Consistent Image to 3D View Synthesis via Geometry-aware Diff
        21404, -- 2310.03022 Decision ConvFormer: Local Filtering in MetaFormer is Sufficient for Decision Ma
        21425, -- 2310.03262 Predicting Emergent Abilities with Infinite Resolution Evaluation
        21495, -- 2310.04134 TiC: Exploring Vision Transformer in Convolution
        21527, -- 2310.04582 Universal Humanoid Motion Representations for Physics-Based Control
        21635, -- 2310.05694 A Survey of Large Language Models for Healthcare: from Data, Technology, and App
        21660, -- 2310.05884 A Meta-Learning Perspective on Transformers for Causal Language Modeling
        21695, -- 2310.06266 CodeFuse-13B: A Pretrained Multi-lingual Code Large Language Model
        21814, -- 2310.07707 MatFormer: Nested Transformer for Elastic Inference
        21929, -- 2310.08797 A Comparative Analysis of Task-Agnostic Distillation Methods for Compressing Tra
        22116, -- 2310.11366 Lie Group Decompositions for Equivariant Neural Networks
        22185, -- 2310.12190 DynamiCrafter: Animating Open-domain Images with Video Diffusion Priors
        22237, -- 2310.12973 Frozen Transformers in Language Models Are Effective Visual Encoder Layers
        22436, -- 2310.15294 Adaptive End-to-End Metric Learning for Zero-Shot Cross-Domain Slot Filling
        22575, -- 2310.16870 MACP: Efficient Model Adaptation for Cooperative Perception
        22703, -- 2310.18672 Maximum Independent Set: Self-Training through Dynamic Programming
        22787, -- 2310.20030 Scaling Riemannian Diffusion Models
        22814, -- 2310.20587 Unleashing the Power of Pre-trained Language Models for Offline Reinforcement Le
        22860, -- 2311.00556 ProBio: A Protocol-guided Multimodal Dataset for Molecular Biology Lab
        22893, -- 2311.01017 Copilot4D: Learning Unsupervised World Models for Autonomous Driving via Discret
        22903, -- 2311.01282 FlashDecoding++: Faster Large Language Model Inference on GPUs
        23219, -- 2311.07143 Learning Symmetrization for Equivariance with Orbit Distance Minimization
        23356, -- 2311.08891 AdapterShadow: Adapting Segment Anything Model for Shadow Detection
        23467, -- 2311.10122 Video-LLaVA: Learning United Visual Representation by Alignment Before Projectio
        23685, -- 2311.13668 MAIRA-1: A specialised large multimodal model for radiology report generation
        23806, -- 2311.15826 GeoChat: Grounded Large Vision-Language Model for Remote Sensing
        23927, -- 2311.17132 TransNeXt: Robust Foveal Visual Perception for Vision Transformers
        23954, -- 2311.17524 Improving Feature Stability during Upsampling -- Spectral Artifacts and the Impo
        23969, -- 2311.17717 Receler: Reliable Concept Erasing of Text-to-Image Diffusion Models via Lightwei
        23983, -- 2311.17901 SODA: Bottleneck Diffusion Models for Representation Learning
        23984, -- 2311.17910 HUGS: Human Gaussian Splats
        23993, -- 2311.17945 Contrastive Vision-Language Alignment Makes Efficient Instruction Learner
        24154, -- 2312.00869 Segment and Caption Anything
        24185, -- 2312.01415 Thermally Averaged Magnetic Anisotropy Tensors via Machine Learning Based on Gau
        24214, -- 2312.01998 Language-only Efficient Training of Zero-shot Composed Image Retrieval
        24215, -- 2312.01999 SRTransGAN: Image Super-Resolution using Transformer based Generative Adversaria
        24262, -- 2312.02310 VaQuitA: Enhancing Alignment in LLM-Assisted Video Understanding
        24292, -- 2312.02696 Analyzing and Improving the Training Dynamics of Diffusion Models
        24435, -- 2312.04433 DreamVideo: Composing Your Dream Videos with Customized Subject and Motion
        24461, -- 2312.04556 Large Language Models for Mathematicians
        24496, -- 2312.04962 Point2CAD: Reverse Engineering CAD Models from 3D Point Clouds
        24546, -- 2312.05614 Transformer as Linear Expansion of Learngene
        24581, -- 2312.06162 Textual Prompt Guided Image Restoration
        24612, -- 2312.06647 4M: Massively Multimodal Masked Modeling
        24662, -- 2312.07122 Neural Reasoning About Agents' Goals, Preferences, and Actions
        24713, -- 2312.07886 Modality Plug-and-Play: Elastic Modality Adaptation in Multimodal LLMs for Embod
        24874, -- 2312.10257 The Physics-Informed Neural Network Gravity Model: Generation III
        24927, -- 2312.11392 SCEdit: Efficient and Controllable Image Diffusion Generation via Skip Connectio
        25005, -- 2312.12462 Towards an end-to-end artificial intelligence driven global weather forecasting
        25296, -- 2312.17276 PanGu-$π$: Enhancing Language Model Architectures via Nonlinearity Compensation
        25401, -- 2401.01130 Joint Generative Modeling of Scene Graphs and Images via Diffusion Models
        25456, -- 2401.01967 A Mechanistic Understanding of Alignment Algorithms: A Case Study on DPO and Tox
        25554, -- 2401.03497 EAT: Self-Supervised Pre-Training with Efficient Audio Transformer
        25568, -- 2401.03804 TeleChat Technical Report
        25581, -- 2401.04044 FFSplit: Split Feed-Forward Network For Optimizing Accuracy-Efficiency Trade-off
        25591, -- 2401.04148 Online Test-Time Adaptation of Spatial-Temporal Traffic Flow Forecasting
        25599, -- 2401.04330 BD-MSA: Body decouple VHR Remote Sensing Image Change Detection method guided by
        25630, -- 2401.04722 U-Mamba: Enhancing Long-range Dependency for Biomedical Image Segmentation
        25687, -- 2401.05698 HiCMAE: Hierarchical Contrastive Masked Autoencoder for Self-Supervised Audio-Vi
        25703, -- 2401.05946 Learning Cognitive Maps from Transformer Representations for Efficient Planning
        25738, -- 2401.06387 Towards High-Quality and Efficient Speech Bandwidth Extension with Parallel Ampl
        25866, -- 2401.08426 GD doesn't make the cut: Three ways that non-differentiability affects neural ne
        25931, -- 2401.09192 Preparing Lessons for Progressive Training on Language Models
        26082, -- 2401.11243 LRP-QViT: Mixed-Precision Vision Transformer Quantization via Layer-wise Relevan
        26140, -- 2401.12181 Universal Neurons in GPT2 Language Models
        26212, -- 2401.13160 SpacTor-T5: Pre-training T5 Models with Span Corruption and Replaced Token Detec
        26223, -- 2401.13276 SCNet: Sparse Compression Network for Music Source Separation
        26248, -- 2401.13660 MambaByte: Token-free Selective State Space Model
        26260, -- 2401.13875 Is Temperature Sample Efficient for Softmax Gaussian Mixture of Experts?
        26402, -- 2401.15947 MoE-LLaVA: Mixture of Experts for Large Vision-Language Models
        26446, -- 2401.16456 SHViT: Single-Head Vision Transformer with Memory Efficient Macro Design
        26583, -- 2402.00712 ChaosBench: A Multi-Channel, Physics-Based Benchmark for Subseasonal-to-Seasonal
        26673, -- 2402.01591 BAT: Learning to Reason about Spatial Sounds with Large Language Models
        26716, -- 2402.01911 From PEFT to DEFT: Parameter Efficient Finetuning for Reducing Activation Densit
        26757, -- 2402.02339 Uncertainty-Aware Testing-Time Optimization for 3D Human Pose Estimation
        26765, -- 2402.02425 DeepLag: Discovering Deep Lagrangian Dynamics for Intuitive Fluid Prediction
        26793, -- 2402.02754 Focal Modulation Networks for Interpretable Sound Classification
        26812, -- 2402.03040 InteractiveVideo: User-Centric Controllable Video Generation with Synergistic Mu
        26833, -- 2402.03241 FROSTER: Frozen CLIP Is A Strong Teacher for Open-Vocabulary Action Recognition
        26892, -- 2402.03766 MobileVLM V2: Faster and Stronger Baseline for Vision Language Model
        26898, -- 2402.03804 ReLU$^2$ Wins: Discovering Efficient Activation Functions for Sparse LLMs
        26994, -- 2402.04882 LMUFormer: Low Complexity Yet Powerful Spiking Model With Legendre Memory Units
        27046, -- 2402.05591 SoftEDA: Rethinking Rule-Based Data Augmentation with Soft Labels
        27204, -- 2402.07757 Towards an Understanding of Stepwise Inference in Transformers: A Synthetic Grap
        27206, -- 2402.07792 Empowering Federated Learning for Massive Models with NVIDIA FLARE
        27214, -- 2402.07865 Prismatic VLMs: Investigating the Design Space of Visually-Conditioned Language
        27250, -- 2402.08324 Uncertainty Quantification via Stable Distribution Propagation
        27398, -- 2402.10422 Pushing the Limits of Zero-shot End-to-End Speech Translation
        27481, -- 2402.11248 CoLLaVO: Crayon Large Language and Vision mOdel
        27703, -- 2402.13352 KetGPT -- Dataset Augmentation of Quantum Circuits using Transformers
        27971, -- 2402.16438 Language-Specific Neurons: The Key to Multilingual Capabilities in Large Languag
        28073, -- 2402.17641 Variational Learning is Effective for Large Deep Networks
        28089, -- 2402.17766 ShapeLLM: Universal 3D Object Understanding for Embodied Interaction
        28187, -- 2402.19091 Leveraging Representations from Intermediate Encoder-blocks for Synthetic Image
        28201, -- 2402.19305 HyenaPixel: Global Image Context with Convolutions
        28208, -- 2402.19427 Griffin: Mixing Gated Linear Recurrences with Local Attention for Efficient Lang
        28267, -- 2403.00818 DenseMamba: State Space Models with Dense Hidden Connection for Efficient Large
        28485, -- 2403.03900 Mamba4Rec: Towards Efficient Sequential Recommendation with Selective State Spac
        28578, -- 2403.05297 PEEB: Part-based Image Classifiers with an Explainable and Editable Language Bot
        28604, -- 2403.05726 Augmentations vs Algorithms: What Works in Self-Supervised Learning
        28704, -- 2403.07282 Enhancing Transfer Learning with Flexible Nonparametric Posterior Sampling
        28719, -- 2403.07508 MoAI: Mixture of All Intelligence for Large Language and Vision Models
        28829, -- 2403.09073 Revealing the Parallel Multilingual Learning within Large Language Models
        28934, -- 2403.10516 FeatUp: A Model-Agnostic Framework for Features at Any Resolution
        29036, -- 2403.11791 PAON: A New Neuron Model using Padé Approximants
        29093, -- 2403.12422 Jetfire: Efficient and Accurate Transformer Pretraining with INT8 Data Flow and
        29095, -- 2403.12459 Non-negative Contrastive Learning
        29302, -- 2403.14828 Multimodal-Conditioned Latent Diffusion Models for Fashion Image Editing
        29392, -- 2403.16187 ALoRA: Allocating Low-Rank Adaptation for Fine-tuning Large Language Models
        29411, -- 2403.16516 Visually Guided Generative Text-Layout Pre-training for Document Intelligence
        29487, -- 2403.17823 Efficient Image Pre-Training with Siamese Cropped Masked Autoencoders
        29529, -- 2403.18257 Dual-path Mamba: Short and Long-term Bidirectional Selective Structured State Sp
        29614, -- 2403.19507 SineNet: Learning Temporal Dynamics in Time-Dependent Partial Differential Equat
        29645, -- 2403.19888 MambaMixer: Efficient Selective State Space Models with Dual Token and Channel S
        29653, -- 2403.19967 Rewrite the Stars
        29708, -- 2404.00498 94% on CIFAR-10 in 3.29 Seconds on a Single GPU
        29726, -- 2404.00656 WavLLM: Towards Robust and Adaptive Speech Large Language Model
        29782, -- 2404.01253 UniArk: Improving Generalisation and Consistency for Factual Knowledge Extractio
        29939, -- 2404.03482 AdaGlimpse: Active Visual Exploration with Arbitrary Glimpse Position and Scale
        30078, -- 2404.05559 TIM: A Time Interval Machine for Audio-Visual Action Recognition
        30079, -- 2404.05567 Dense Training, Sparse Inference: Rethinking Training of Mixture-of-Experts Lang
        30166, -- 2404.06773 Adapting LLaMA Decoder to Vision Transformer
        30418, -- 2404.10518 MobileNetV4 -- Universal Models for the Mobile Ecosystem
        30458, -- 2404.11201 Neuron Specialization: Leveraging intrinsic task modularity for multilingual mac
        30616, -- 2404.13604 CKGConv: General Graph Convolution with Continuous Kernels
        30781, -- 2404.16752 TokenHMR: Advancing Human Mesh Recovery with a Tokenized Pose Representation
        30823, -- 2404.17364 MV-VTON: Multi-View Virtual Try-On with Diffusion Models
        30948, -- 2405.00029 Automatic Creative Selection with Cross-Modal Matching
        30962, -- 2405.00314 Model Quantization and Hardware Acceleration for Vision Transformers: A Comprehe
        31041, -- 2405.01943 Dependency-Aware Semi-Structured Sparsity of GLU Variants in Large Language Mode
        31071, -- 2405.02951 iSEARLE: Improving Textual Inversion for Zero-Shot Composed Image Retrieval
        31265, -- 2405.07992 MambaOut: Do We Really Need Mamba for Vision?
        31340, -- 2405.09874 Dual3D: Efficient and Consistent Text-to-3D Generation with Dual-mode Multi-view
        31366, -- 2405.10315 TRANSIC: Sim-to-Real Policy Transfer by Learning from Online Correction
        31523, -- 2405.13632 Task agnostic continual learning with Pairwise layer architecture
        31533, -- 2405.13800 Dense Connector for MLLMs
        31562, -- 2405.14159 Super Tiny Language Models
        31610, -- 2405.14715 Towards Cross-modal Backward-compatible Representation Learning for Vision-Langu
        31625, -- 2405.14832 Direct3D: Scalable Image-to-3D Generation via 3D Latent Diffusion Transformer
        31689, -- 2405.15471 Emergence of a High-Dimensional Abstraction Phase in Language Transformers
        31695, -- 2405.15574 Meteor: Mamba-based Traversal of Rationale for Large Language and Vision Models
        31737, -- 2405.16009 Streaming Long Video Understanding with Large Language Models
        31778, -- 2405.16577 Reflected Flow Matching
        31791, -- 2405.16727 Disentangling and Integrating Relational and Sensory Information in Transformer
        32077, -- 2405.20233 Grokfast: Accelerated Grokking by Amplifying Slow Gradients
        32118, -- 2405.20684 Joint Embeddings for Graph Instruction Tuning
        32144, -- 2405.21063 Neural Network Verification with Branch-and-Bound for General Nonlinearities
        32245, -- 2406.01514 Decoupled Alignment for Robust Plug-and-Play Adaptation
        32295, -- 2406.02347 Flash Diffusion: Accelerating Any Conditional Diffusion Model for Few Steps Imag
        32305, -- 2406.02507 Guiding a Diffusion Model with a Bad Version of Itself
        32371, -- 2406.03345 Feature Contamination: Neural Networks Learn Uncorrelated Features and Fail to G
        32587, -- 2406.05955 Turbo Sparse: Achieving LLM SOTA Performance with Minimal Activated Parameters
        32611, -- 2406.06248 Compute Better Spent: Replacing Dense Layers with Structured Matrices
        32642, -- 2406.06527 IllumiNeRF: 3D Relighting Without Inverse Rendering
        32764, -- 2406.07887 An Empirical Study of Mamba-based Language Models
        32799, -- 2406.08394 VisionLLM v2: An End-to-End Generalist Multimodal Large Language Model for Hundr
        32906, -- 2406.09416 Alleviating Distortion in Image Generation via Multi-Resolution Diffusion Models
        33222, -- 2406.12246 TroL: Traversal of Layers for Large Language and Vision Models
        33279, -- 2406.12793 ChatGLM: A Family of Large Language Models from GLM-130B to GLM-4 All Tools
        33309, -- 2406.13181 The Impact of Auxiliary Patient Data on Automated Chest X-Ray Report Generation
        33319, -- 2406.13340 SD-Eval: A Benchmark Dataset for Spoken Dialogue Understanding Beyond Words
        33533, -- 2406.16004 RepNeXt: A Fast Multi-Scale CNN using Structural Reparameterization
        33551, -- 2406.16254 Confidence Regulation Neurons in Language Models
        33596, -- 2406.16758 Towards Fast Multilingual LLM Inference: Speculative Decoding and Specialized Dr
        33820, -- 2406.19435 A Sanity Check for AI-generated Image Detection
        33823, -- 2406.19486 LoPT: Low-Rank Prompt Tuning for Parameter Efficient Language Models
        34201, -- 2407.04513 LayerShuffle: Enhancing Robustness in Vision Transformers by Randomizing Layer E
        34212, -- 2407.04620 Learning to (Learn at Test Time): RNNs with Expressive Hidden States
        34251, -- 2407.05311 MMAD: Multi-label Micro-Action Detection in Videos
        34336, -- 2407.06204 A Survey on Mixture of Experts
        34397, -- 2407.07111 Diffusion Model-Based Video Editing: A Survey
        34411, -- 2407.07346 INSIGHT: Universal Neural Simulator for Analog Circuits Harnessing Autoregressiv
        34434, -- 2407.07787 Continuous Control with Coarse-to-fine Reinforcement Learning
        34435, -- 2407.07788 BiGym: A Demo-Driven Mobile Bi-Manual Manipulation Benchmark
        34458, -- 2407.08083 MambaVision: A Hybrid Mamba-Transformer Vision Backbone
        34497, -- 2407.08567 Adaptive Parametric Activation
        34578, -- 2407.09541 MATE: Meet At The Embedding -- Connecting Images with Long Texts
        34676, -- 2407.10918 PartImageNet++ Dataset: Scaling up Part-based Models for Robust Recognition
        34709, -- 2407.11211 Unconstrained Open Vocabulary Image Classification: Zero-Shot Transfer from Text
        34741, -- 2407.11569 SFPNet: Sparse Focal Point Network for Semantic Segmentation on General LiDAR Po
        34744, -- 2407.11633 Scaling Diffusion Transformers to 16 Billion Parameters
        34783, -- 2407.12069 One-Shot Unlearning of Personal Identities
        34841, -- 2407.12781 VD3D: Taming Large Video Diffusion Transformers for 3D Camera Control
        34934, -- 2407.13766 Visual Haystacks: A Vision-Centric Needle-In-A-Haystack Benchmark
        34935, -- 2407.13772 GroupMamba: Efficient Group-Based Visual State Space Model
        34998, -- 2407.14904 Large-vocabulary forensic pathological analyses via prototypical cross-modal con
        35004, -- 2407.14962 Recent Advances in Generative AI and Large Language Models: Current Status, Chal
        35038, -- 2407.15408 Chronologically Accurate Retrieval for Temporal Grounding of Motion-Language Mod
        35067, -- 2407.15811 Stretching Each Dollar: Diffusion Training from Scratch on a Micro-Budget
        35112, -- 2407.16556 DC is all you need: describing ReLU from a signal processing standpoint
        35206, -- 2407.18178 PianoMime: Learning a Generalist, Dexterous Piano Player from Internet Demonstra
        35225, -- 2407.18437 Mixed Non-linear Quantization for Vision Transformers
        35230, -- 2407.18496 Towards More Accurate Prediction of Human Empathy and Emotion in Text and Multi-
        35299, -- 2407.19985 Mixture of Nested Experts: Adaptive Processing of Visual Tokens
        35332, -- 2407.20635 Autonomous Improvement of Instruction Following Skills via Foundation Models
        35424, -- 2408.00386 What comes after transformers? -- A selective survey connecting ideas in deep le
        35434, -- 2408.00591 Regional quality estimation for echocardiography using deep learning
        35436, -- 2408.00620 Are Bigger Encoders Always Better in Vision Large Models?
        35578, -- 2408.02865 VisionUnite: A Vision-Language Foundation Model for Ophthalmology Enhanced with
        35617, -- 2408.03511 MoExtend: Tuning New Experts for Modality and Task Extension
        35775, -- 2408.06610 CROME: Cross-Modal Adapters for Efficient Multimodal LLM
        35826, -- 2408.07337 KIND: Knowledge Integration and Diversion for Training Decomposable Models
        35968, -- 2408.10007 P3P: Pseudo-3D Pre-training for Scaling 3D Voxel-based Masked Autoencoders
        36047, -- 2408.11054 Near, far: Patch-ordering enhances vision foundation models' scene understanding
        36379, -- 2408.16532 WavTokenizer: an Efficient Acoustic Discrete Codec Tokenizer for Audio Language
        36470, -- 2409.00750 MaskGCT: Zero-Shot Text-to-Speech with Masked Generative Codec Transformer
        36591, -- 2409.02958 Multi-Modal Adapter for Vision-Language Models
        36745, -- 2409.06679 E2LLM: Encoder Elongated Large Language Models for Long-Context Understanding an
        36925, -- 2409.10103 Self-Supervised Syllable Discovery Based on Speaker-Disentangled HuBERT
        36951, -- 2409.10594 Kolmogorov-Arnold Transformer
        36998, -- 2409.11321 SOAP: Improving and Stabilizing Shampoo using Adam
        37135, -- 2409.13689 Temporally Aligned Audio for Video with Autoregression
        37154, -- 2409.13882 Tabular Data Generation using Binary Diffusion
        37191, -- 2409.14713 Phantom of Latent for Large Language and Vision Models
        37573, -- 2410.00255 Robin3D: Improving 3D Large Language Model via Robust Instruction Tuning
        37620, -- 2410.01104 Softmax is not Enough (for Sharp Size Generalisation)
        37696, -- 2410.01806 Samba: Synchronized Set-of-Sequences Modeling for Multiple Object Tracking
        37711, -- 2410.02048 FeelAnyForce: Estimating Contact Force Feedback from Tactile Sensation for Visio
        37773, -- 2410.02550 NestedMorph: Enhancing Deformable Medical Image Registration with Nested Attenti
        37784, -- 2410.02675 FAN: Fourier Analysis Networks
        37805, -- 2410.02746 Contrastive Localized Language-Image Pre-Training
        37974, -- 2410.04733 Video Prediction Transformers without Recurrence or Convolution
        38106, -- 2410.06231 RelitLRM: Generative Relightable Radiance for Large Reconstruction Models
        38144, -- 2410.06682 Enhancing Multimodal LLM for Detailed and Accurate Video Captioning using Multi-
        38172, -- 2410.07073 Pixtral 12B
        38236, -- 2410.07864 RDT-1B: a Diffusion Foundation Model for Bimanual Manipulation
        38280, -- 2410.08208 SPA: 3D Spatial-Awareness Enables Effective Embodied Representation
        38441, -- 2410.10624 SensorLLM: Human-Intuitive Alignment of Multivariate Sensor Data with LLMs for A
        38459, -- 2410.10781 When Attention Sink Emerges in Language Models: An Empirical View
        38492, -- 2410.10989 Liger Kernel: Efficient Triton Kernels for LLM Training
        38507, -- 2410.11135 Mimetic Initialization Helps State Space Models Learn to Recall
        38733, -- 2410.13732 Reducing the Transformer Architecture to a Minimum
        38817, -- 2410.14633 Swiss Army Knife: Synergizing Biases in Knowledge from Vision Foundation Models
        39048, -- 2410.17779 ADEM-VL: Adaptive and Embedded Fusion for Efficient Vision-Language Tuning
        39172, -- 2410.19313 COAT: Compressing Optimizer states and Activation for Memory-Efficient FP8 Train
        39343, -- 2410.22313 Senna: Bridging Large Vision-Language Models and End-to-End Autonomous Driving
        39396, -- 2410.23168 TokenFormer: Rethinking Transformer Scaling with Tokenized Model Parameters
        39686, -- 2411.03884 Polynomial Composition Activations: Unleashing the Dynamics of Large Language Mo
        39752, -- 2411.04967 AsCAN: Asymmetric Convolution-Attention Networks for Efficient Recognition and G
        40097, -- 2411.11222 The Sound of Water: Inferring Physical Properties from Pouring Liquids
        40151, -- 2411.12155 Coarse-to-fine Q-Network with Action Sequence for Data-Efficient Robot Learning
        40336, -- 2411.15241 EfficientViM: Efficient Vision Mamba with Hidden State Mixer based State Space D
        40357, -- 2411.15453 Enhancing Instruction-Following Capability of Visual-Language Models by Reducing
        40500, -- 2411.17248 DiffSLT: Enhancing Diversity in Sign Language Translation via Diffusion Model
        40507, -- 2411.17385 DepthCues: Evaluating Monocular Depth Perception in Large Vision Models
        40626, -- 2411.18673 AC3D: Analyzing and Improving 3D Camera Control in Video Diffusion Transformers
        40678, -- 2411.19417 Any-Resolution AI-Generated Image Detection by Spectral Learning
        40801, -- 2412.01004 Adaptive Rank, Reduced Forgetting: Knowledge Retention in Continual Learning Vis
        40853, -- 2412.01789 From ChebNet to ChebGibbsNet
        40855, -- 2412.01801 SceneFactor: Factored Latent 3D Diffusion for Controllable 3D Scene Generation
        40862, -- 2412.01822 VLsI: Verbalized Layers-to-Interactions from Large to Small Vision Language Mode
        40875, -- 2412.02030 NitroFusion: High-Fidelity Single-Step Diffusion through Dynamic Adversarial Tra
        40936, -- 2412.02852 Effortless Efficiency: Low-Cost Pruning of Diffusion Models
        40971, -- 2412.03318 Domain-Agnostic Stroke Lesion Segmentation Using Physics-Constrained Synthetic D
        40996, -- 2412.03568 The Matrix: Infinite-Horizon World Generation with Real-Time Moving Control
        41098, -- 2412.04591 Aberration Correcting Vision Transformers for High-Fidelity Metalens Imaging
        41242, -- 2412.06674 EMOv2: Pushing 5M Vision Model Frontier
        41256, -- 2412.06781 Around the World in 80 Timesteps: A Generative Approach to Global Visual Geoloca
        41314, -- 2412.07679 RADIO Amplified: Improved Baselines for Agglomerative Vision Foundation Models
        41447, -- 2412.09278 Towards a Multimodal Large Language Model with Pixel-Level Insight for Biomedici
        41485, -- 2412.09613 PVC: Progressive Visual Token Compression for Unified Image and Video Processing
        41506, -- 2412.09818 MERaLiON-AudioLLM: Bridging Audio and Language with Large Language Models
        41592, -- 2412.10995 RapidNet: Multi-Level Dilated Convolution Based Mobile Backbone
        41795, -- 2412.13335 Experience of Training a 1.7B-Parameter LLaMa Model From Scratch
        41817, -- 2412.13663 Smarter, Better, Faster, Longer: A Modern Bidirectional Encoder for Fast, Memory
        41851, -- 2412.14164 MetaMorph: Multimodal Understanding and Generation via Instruction Tuning
        42033, -- 2412.16771 SilVar: Speech Driven Multimodal Model for Reasoning Visual Question Answering a
        42067, -- 2412.17239 Unity is Strength: Unifying Convolutional and Transformeral Features for Better
        42078, -- 2412.17323 xPatch: Dual-Stream Time Series Forecasting with Exponential Seasonal-Trend Deco
        42237, -- 2412.19628 RecConv: Efficient Recursive Convolutions for Multi-Frequency Representations
        42243, -- 2412.19712 From Elements to Design: A Layered Approach for Automatic Graphic Design Composi
        42371, -- 2501.00663 Titans: Learning to Memorize at Test Time
        42724, -- 2501.06230 BEN: Using Confidence-Guided Matting for Dichotomous Image Segmentation
        42986, -- 2501.10807 FlashSR: One-step Versatile Audio Super-resolution via Diffusion Distillation
        43077, -- 2501.12390 GPS as a Control Signal for Image Generation
        43112, -- 2501.12976 LiT: Delving into a Simplified Linear Diffusion Transformer for Image Generation
        43136, -- 2501.13428 Softplus Attention with Re-weighting Boosts Length Extrapolation in Large Langua
        43162, -- 2501.13787 Parameter-Efficient Fine-Tuning for Foundation Models
        43490, -- 2502.00288 Learning from Suboptimal Data in Continuous Control via Auto-Regressive Soft Q-N
        43522, -- 2502.00840 Activation Approximations Can Incur Safety Vulnerabilities Even in Aligned LLMs:
        43706, -- 2502.03382 High-Fidelity Simultaneous Speech-To-Speech Translation
        43726, -- 2502.03654 Gompertz Linear Units: Leveraging Asymmetry for Enhanced Learning Dynamics
        43877, -- 2502.05564 TabICL: A Tabular Foundation Model for In-Context Learning on Large Data
        44371, -- 2502.11775 video-SALMONN-o1: Reasoning-enhanced Audio-visual Large Language Model
        44780, -- 2502.15757 TLOB: A Novel Transformer Model with Dual Attention for Price Trend Prediction w
        44938, -- 2502.17391 The Empirical Impact of Reducing Symmetries on the Performance of Deep Ensembles
        44992, -- 2502.18143 LightFC-X: Lightweight Convolutional Tracker for RGB-X Tracking
        45110, -- 2502.19645 Fine-Tuning Vision-Language-Action Models: Optimizing Speed and Success
        45117, -- 2502.19732 Speculative Decoding and Beyond: An In-Depth Review of Techniques
        45218, -- 2502.21001 Towards Lossless Implicit Neural Representation via Bit Plane Decomposition
        45229, -- 2502.21309 FANformer: Improving Large Language Models Through Effective Periodicity Modelin
        45464, -- 2503.03148 Partial Convolution Meets Visual Attention
        45492, -- 2503.03594 Small but Mighty: Enhancing Time Series Forecasting with Lightweight LLMs
        45659, -- 2503.06112 AF-KAN: Activation Function-Based Kolmogorov-Arnold Networks for Efficient Repre
        46031, -- 2503.10287 MACS: Multi-source Audio-to-image Generation with Contextual Significance and Se
        46082, -- 2503.10636 The Curse of Conditions: Analyzing and Improving Optimal Transport for Condition
        46142, -- 2503.11341 Self-Supervised Pretraining for Fine-Grained Plankton Recognition
        46391, -- 2503.15338 Solla: Towards a Speech-Oriented LLM That Hears Acoustic Context
        47135, -- 2504.01014 AnimeGamer: Infinite Anime Life Simulation with Next Game State Prediction
        47195, -- 2504.02061 Aligned Better, Listen Better for Audio-Visual Large Language Models
        47381, -- 2504.05298 One-Minute Video Generation with Test-Time Training
        47441, -- 2504.06719 Masked Scene Modeling: Narrowing the Gap Between Supervised and Self-Supervised
        47594, -- 2504.09255 FVQ: A Large-Scale Dataset and A LMM-based Method for Face Video Quality Assessm
        47700, -- 2504.10686 The Tenth NTIRE 2025 Efficient Super-Resolution Challenge Report
        47721, -- 2504.11134 Visual Re-Ranking with Non-Visual Side Information
        47818, -- 2504.12526 MOM: Memory-Efficient Offloaded Mini-Sequence Inference for Long Context Languag
        47859, -- 2504.13112 Hadamard product in deep learning: Introduction, Advances and Challenges
        47874, -- 2504.13173 It's All Connected: A Journey Through Test-Time Memorization, Attentional Bias,
        47937, -- 2504.14379 The Geometry of Self-Verification in a Task-Specific Reasoning Model
        47988, -- 2504.15046 Text-to-Decision Agent: Learning Generalist Policies from Natural Language Super
        47990, -- 2504.15051 VeLU: Variance-enhanced Learning Unit for Deep Neural Networks
        48236, -- 2504.20859 X-Cross: Dynamic Integration of Language Models for Cross-Domain Sequential Reco
        48599, -- 2505.06633 Attention Is Not All You Need: The Importance of Feedforward Networks in Transfo
        48647, -- 2505.07675 Simple Semi-supervised Knowledge Distillation from Vision-Language Models via $\
        48710, -- 2505.08910 Behind Maya: Building a Multilingual Vision Language Model
        48856, -- 2505.11329 TokenWeave: Efficient Compute-Communication Overlap for Distributed LLM Inferenc
        49090, -- 2505.13755 Panda: A pretrained forecast model for universal representation of chaotic dynam
        49299, -- 2505.15441 Stronger ViTs With Octic Equivariance
        49456, -- 2505.16901 Code Graph Model (CGM): A Graph-Integrated Large Language Model for Repository-L
        49487, -- 2505.17020 CrossLMM: Decoupling Long Video Sequences from LMMs via Dual Cross-Attention Mec
        49730, -- 2505.19422 LlamaSeg: Image Segmentation via Autoregressive Mask Generation
        50049, -- 2505.22865 BinauralFlow: A Causal and Streamable Approach for High-Quality Binaural Speech
        50107, -- 2505.23458 Diffusion Guidance Is a Controllable Policy Improvement Operator
        50146, -- 2505.23735 ATLAS: Learning to Optimally Memorize the Context at Test Time
        50216, -- 2505.24293 Large Language Models are Locally Linear Mappings
        50427, -- 2506.02052 Protap: A Benchmark for Protein Modeling on Realistic Downstream Applications
        50652, -- 2506.05332 Unleashing Hour-Scale Video Training for Long Video-Language Understanding
        50667, -- 2506.05426 Mixture-of-Experts Meets In-Context Reinforcement Learning
        50691, -- 2506.05880 NILMFormer: Non-Intrusive Load Monitoring that Accounts for Non-Stationarity
        50748, -- 2506.07138 Learning Compact Vision Tokens for Efficient Large Multimodal Models
        50783, -- 2506.07744 Graph-Assisted Stitching for Offline Hierarchical Reinforcement Learning
        50821, -- 2506.08015 4DGT: Learning a 4D Gaussian Transformer Using Real-World Monocular Videos
        50863, -- 2506.08524 Teaching Physical Awareness to LLMs through Sounds
        50883, -- 2506.08887 DiscoVLA: Discrepancy Reduction in Vision, Language, and Alignment for Parameter
        50985, -- 2506.10178 Attention, Please! Revisiting Attentive Probing for Masked Image Modeling
        51066, -- 2506.11305 Don't Pay Attention
        51240, -- 2506.14767 A Variational Framework for Improving Naturalness in Generative Spoken Language
        51313, -- 2506.17090 Better Language Model Inversion by Compactly Representing Next-Token   Distribut
        51328, -- 2506.17323 I Know Which LLM Wrote Your Code Last Summer: LLM generated Code Stylometry for
        51351, -- 2506.17967 Adapting Vision-Language Models for Evaluating World Models
        51371, -- 2506.18463 DIP: Unsupervised Dense In-Context Post-training of Visual Representations
        51476, -- 2506.20701 Diffusion Tree Sampling: Scalable inference-time alignment of diffusion models
        51506, -- 2506.21298 Exploring Adapter Design Tradeoffs for Low Resource Music Generation
        51539, -- 2506.21724 Asymmetric Dual Self-Distillation for 3D Self-Supervised Representation Learning
        52057, -- 2507.18405 Iwin Transformer: Hierarchical Vision Transformer using Interleaved   Windows
        52120, -- 2507.23277 iLRM: An Iterative Large 3D Reconstruction Model
        52255, -- 2508.05257 MoBE: Mixture-of-Basis-Experts for Compressing MoE-based LLMs
        52392, -- 2508.11598 Representing Speech Through Autoregressive Prediction of Cochlear Tokens
        52400, -- 2508.12594 FLARE: Fast Low-rank Attention Routing Engine
        52569, -- 2508.21046 CogVLA: Cognition-Aligned Vision-Language-Action Model via   Instruction-Driven
        53255, -- 2510.03434 Paris: A Decentralized Trained Open-Weight Diffusion Model
        53263, -- 2510.04871 Less is More: Recursive Reasoning with Tiny Networks
        53290, -- 2510.06219 Human3R: Everyone Everywhere All at Once
        53399, -- 2510.07314 GyroSwin: 5D Surrogates for Gyrokinetic Plasma Turbulence Simulations
        53596, -- 2510.14979 From Pixels to Words -- Towards Native Vision-Language Primitives at   Scale
        54067, -- 2511.02818 Orion-MSP: Multi-Scale Sparse Attention for Tabular In-Context Learning
        54080, -- 2511.04670 Cambrian-S: Towards Spatial Supersensing in Video
        54465, -- 2512.01030 Lotus-2: Advancing Geometric Dense Prediction with Powerful Image Generative Mod
        54472, -- 2512.01103 Learning Eigenstructures of Unstructured Data Manifolds
        54633, -- 2512.07806 Multi-view Pyramid Transformer: Look Coarser to See Broader
        54779, -- 2512.13689 LitePT: Lighter Yet Stronger Point Transformer
        54904, -- 2512.17012 4D-RGPT: Toward Region-level 4D Understanding via Perceptual Distillation
        55051, -- 2512.24176 Guiding a Diffusion Transformer with the Internal Dynamics of Itself
        55205, -- 2601.02760 AnyDepth: Depth Estimation Made Easy
        55422, -- 2601.14750 Render-of-Thought: Rendering Textual Chain-of-Thought as Images for Visual Laten
        55748, -- 2602.01212 SimpleGPT: Improving GPT via A Simple Normalization Strategy
        55836, -- 2602.05393 Late-to-Early Training: LET LLMs Learn Earlier, So Faster and Better
        56229, -- 2602.17807 VidEoMT: Your ViT is Secretly Also a Video Segmentation Model
        56366, -- 2602.24281 Memory Caching: RNNs with Growing Memory
        56448, -- 2603.03163 Conditioned Activation Transport for T2I Safety Steering
        56509, -- 2603.05438 Planning in 8 Tokens: A Compact Discrete Tokenizer for Latent World Model
        56536, -- 2603.05280 Layer by layer, module by module: Choose both for optimal OOD probing of ViT
        56737, -- 2603.14610 Make it SING: Analyzing Semantic Invariants in Classifiers
        56792, -- 2603.16844 M^3: Dense Matching Meets Multi-View Foundation Models for Monocular Gaussian Sp
        56848, -- 2603.16653 HeBA: Heterogeneous Bottleneck Adapters for Robust Vision-Language Models
        56849, -- 2603.14706 AdapterTune: Zero-Initialized Low-Rank Adapters for Frozen Vision Transformers
        56868, -- 2603.19224 EffectErase: Joint Video Object Removal and Insertion for High-Quality Effect Er
        57016, -- 2603.18742 6Bit-Diffusion: Inference-Time Mixed-Precision Quantization for Video Diffusion
        57119, -- 2603.29029 MMFace-DiT: A Dual-Stream Diffusion Transformer for High-Fidelity Multimodal Fac
        57250, -- 2604.02073 PLUME: Latent Reasoning Based Universal Multimodal Embedding
        57314, -- 2604.06427 The Depth Ceiling: On the Limits of Large Language Models in Discovering Latent
        57438, -- 2604.11004 Panoptic Pairwise Distortion Graph
        57547, -- 2604.14430 Three-Phase Transformer
        57619, -- 2604.17388 Back to Repair: A Minimal Denoising Network\ for Time Series Anomaly Detection
        57911, -- 2604.22203 Advancing automatic speech recognition using feature fusion with self-supervised
        58012, -- 2604.18967 Toward Clinically Acceptable Chest X-ray Report Generation: A Qualitative Retros
        58136, -- 2604.15416 StoSignSGD: Unbiased Structural Stochasticity Fixes SignSGD for Training Large L
        58326, -- 2603.02123 Nano-EmoX: Unifying Multimodal Emotional Intelligence from Perception to Empathy
        58651, -- 2604.01279 Sven: Singular Value Descent as a Computationally Efficient Natural Gradient Met
        58806, -- 2603.27059 Towards Intrinsic-Aware Monocular 3D Object Detection
        58961, -- 2603.23669 Estimating Individual Tree Height and Species from UAV Imagery
        59162, -- 2603.19497 ICLAD: In-Context Learning for Unified Tabular Anomaly Detection Across Supervis
        59401, -- 2603.14360 M^2RNN: Non-Linear RNNs with Matrix-Valued States for Scalable Language Modeling
        59410, -- 2603.14075 Enhancing Mental Health Classification with Layer-Attentive Residuals and Contra
        59445, -- 2603.13552 Ghosts of Softmax: Complex Singularities That Limit Safe Step Sizes in Cross-Ent
        59533, -- 2603.11589 Toward Complex-Valued Neural Networks for Waveform Generation
        59792, -- 2603.06082 Offline Materials Optimization with CliqueFlowmer
        60093, -- 2603.00870 PPC-MT: Parallel Point Cloud Completion with Mamba-Transformer Hybrid Architectu
        60315, -- 2602.21035 Not Just What's There: Enabling CLIP to Comprehend Negated Visual Descriptions W
        60519, -- 2602.16711 TeCoNeRV: Leveraging Temporal Coherence for Compressible Neural Representations
        60742, -- 2602.12370 LLaMo: Scaling Pretrained Language Models for Unified Motion Understanding and G
        60823, -- 2602.11072 Simultaneous Speech-to-Speech Translation Without Aligned Data
        61013, -- 2602.08064 SiameseNorm: Breaking the Barrier to Reconciling Pre/Post-Norm
        61657, -- 2602.00378 Parametrization of subgrid scales in long-term simulations of the shallow-water
        61798, -- 2601.21866 MoHETS: Long-term Time Series Forecasting with Mixture-of-Heterogeneous-Experts
        62279, -- 2601.14246 Soft Tail-dropping for Adaptive Visual Tokenization
        62707, -- 2601.10740 Neuro-Symbolic Activation Discovery: Transferring Mathematical Structures from P
        62805, -- 2601.06199 FastSLM: Hierarchical Frame Q-Former for Effective Speech Modality Adaptation
        63208, -- 2512.23808 MiMo-Audio: Audio Language Models are Few-Shot Learners
        63297, -- 2512.21911 Accelerate Speculative Decoding with Sparse Computation in Verification
        63500, -- 2512.17851 InfSplign: Inference-Time Spatial Alignment of Text-to-Image Diffusion Models
        63592, -- 2512.15885 Seeing Beyond Words: Self-Supervised Visual Learning for Multimodal Large Langua
        63771, -- 2512.12135 BaRISTA: Brain Scale Informed Spatiotemporal Representation of Human Intracrania
        64063, -- 2512.05915 LDLT L-Lipschitz Network: Generalized Deep End-To-End Lipschitz Network Construc
        64102, -- 2512.04969 Rethinking the Use of Vision Transformers for AI-Generated Image Detection
        64184, -- 2512.03343 Idea-Gated Transformers: Enforcing Semantic Coherence via Differentiable Vocabul
        64397, -- 2511.23225 TWEO: Transformers Without Extreme Outliers Enables FP8 Training And Quantizatio
        64563, -- 2511.19963 MambaEye: A Size-Agnostic Visual Encoder with Causal Sequential Processing
        64815, -- 2511.15684 Walrus: A Cross-Domain Foundation Model for Continuum Dynamics
        65350, -- 2511.04161 Seeing Straight: Document Orientation Detection for Efficient OCR
        65590, -- 2510.27254 Languages are Modalities: Cross-Lingual Alignment via Encoder Injection
        65676, -- 2510.25502 TempoPFN: Synthetic Pre-training of Linear RNNs for Zero-shot Time   Series Fore
        65870, -- 2510.22257 LUNA: Efficient and Topology-Agnostic Foundation Model for EEG Signal   Analysis
        65901, -- 2510.21585 REVE: A Foundation Model for EEG -- Adapting to Any Setup with   Large-Scale Pre
        66336, -- 2510.14260 MatchAttention: Matching the Relative Positions for High-Resolution   Cross-View
        66394, -- 2510.13259 Hypernetworks for Perspectivist Adaptation
        66441, -- 2510.12327 Simple Projection Variants Improve ColBERT Performance
        66705, -- 2510.08470 Looking to Learn: Token-wise Dynamic Gating for Low-Resource   Vision-Language M
        66758, -- 2510.07730 DEAS: DEtached value learning with Action Sequence for Scalable Offline   RL
        66790, -- 2510.07191 Resolution scaling governs DINOv3 transfer performance in chest radiograph class
        67049, -- 2510.03370 InstructPLM-mu: 1-Hour Fine-Tuning of ESM2 Beats ESM3 in Protein   Mutation Pred
        67248, -- 2510.01370 SPUS: A Lightweight and Parameter-Efficient Foundation Model for PDEs
        67684, -- 2509.22358 Stochastic activations
        67717, -- 2509.21990 WAVE: Learning Unified & Versatile Audio-Visual Embeddings with   Multimodal LLM
        67908, -- 2509.19624 Raw-JPEG Adapter: Efficient Raw Image Compression with JPEG
        67958, -- 2509.18815 FlashGMM: Fast Gaussian Mixture Entropy Model for Learned Image   Compression
        68070, -- 2509.16767 DiffEye: Diffusion-Based Continuous Eye-Tracking Data Generation Conditioned on
        68302, -- 2509.13520 Learning Nonlinear Responses in PET Bottle Buckling with a Hybrid   DeepONet-Tra
        68313, -- 2509.13240 Don't Forget the Nonlinearity: Unlocking Activation Functions in   Efficient Fin
        68536, -- 2509.08502 Chirality in Action: Time-Aware Video Representation Learning by Latent   Straig
        68715, -- 2509.04669 VCMamba: Bridging Convolutions with Multi-Directional Mamba for   Efficient Visu
        68766, -- 2509.03594 The Optimiser Hidden in Plain Sight: Training with the Loss Landscape's   Induce
        68933, -- 2509.00679 Router Upcycling: Leveraging Mixture-of-Routers in Mixture-of-Experts Upcycling
        69251, -- 2508.17404 MoCo: Motion-Consistent Human Video Generation via Structure-Appearance   Decoup
        69524, -- 2508.12977 Dextr: Zero-Shot Neural Architecture Search with Singular Value Decomposition an
        69590, -- 2508.12081 VimoRAG: Video-based Retrieval-augmented 3D Motion Generation for Motion   Langu
        69755, -- 2508.09616 MInDI-3D: Iterative Deep Learning in 3D for Sparse-view Cone Beam Computed Tomog
        69948, -- 2508.06763 SafePLUG: Empowering Multimodal LLMs with Pixel-Level Insight and   Temporal Gro
        70096, -- 2508.04611 BridgeDepth: Bridging Monocular and Stereo Reasoning with Latent   Alignment
        70575, -- 2507.21977 Motion Matters: Motion-guided Modulation Network for Skeleton-based   Micro-Acti
        70982, -- 2507.14670 Gene-DML: Dual-Pathway Multi-Level Discrimination for Gene Expression Prediction
        70985, -- 2507.14613 Depthwise-Dilated Convolutional Adapters for Medical Object Tracking and   Segme
        71083, -- 2507.12144 FourCastNet 3: A geometric approach to probabilistic machine-learning   weather
        71107, -- 2507.11638 Interpretable Prediction of Lymph Node Metastasis in Rectal Cancer MRI   Using V
        71229, -- 2507.08761 Penalizing Infeasible Actions and Reward Scaling in Reinforcement   Learning wit
        71295, -- 2507.07101 Small Batch Size Training for Language Models: When Vanilla SGD Works,   and Why
        71502, -- 2507.01927 evMLP: An Efficient Event-Driven MLP Architecture for Vision
        71637, -- 2506.23325 XY-Tokenizer: Mitigating the Semantic-Acoustic Conflict in Low-Bitrate   Speech
        71645, -- 2506.23225 Masked Gated Linear Unit
        71873, -- 2506.15980 Advanced Sign Language Video Generation with Compressed and Quantized   Multi-Co
        72184, -- 2506.06644 Spark Transformer: Reactivating Sparsity in FFN and Attention
        72190, -- 2506.06440 Vid2Sim: Generalizable, Video-based Reconstruction of Appearance,   Geometry and
        72233, -- 2506.05515 Winner-takes-all for Multivariate Probabilistic Time Series Forecasting
        72253, -- 2506.04704 HoliSafe: Holistic Safety Benchmarking and Modeling with Safety Meta   Token for
        72599, -- 2505.21985 Reward-Independent Messaging for Decentralized Multi-Agent Reinforcement Learnin
        72613, -- 2505.21847 RePaViT: Scalable Vision Transformer Acceleration via Structural   Reparameteriz
        72795, -- 2505.17914 Flexible MOF Generation with Torsion-Aware Flow Matching
        72983, -- 2505.13539 EuLearn: A 3D database for learning Euler characteristics
        73037, -- 2505.11194 Prot2Text-V2: Protein Function Prediction with Multimodal Contrastive   Alignmen
        73074, -- 2505.09160 A Multi-Task Foundation Model for Wireless Channel Representation Using Contrast
        73288, -- 2504.19449 R-Sparse: Rank-Aware Activation Sparsity for Efficient LLM Inference
        73569, -- 2504.08328 Towards generalizable single-cell perturbation modeling via the   Conditional Mo
        73652, -- 2504.05657 Nes2Net: A Lightweight Nested Architecture for Foundation Model Driven Speech An
        73745, -- 2504.01445 Compositional-ARC: Assessing Systematic Generalization in Abstract Spatial Reaso
        73814, -- 2503.23447 CA^2ST: Cross-Attention in Audio, Space, and Time for Holistic Video Recognition
        73881, -- 2503.19331 ChA-MAEViT: Unifying Channel-Aware Masked Autoencoders and Multi-Channel   Visio
        73892, -- 2503.18944 DINO in the Room: Leveraging 2D Foundation Models for 3D Segmentation
        73981, -- 2503.14880 DPFlow: Adaptive Optical Flow Estimation with a Dual-Pyramid Framework
        74007, -- 2503.13956 Improving LLM Video Understanding with 16 Frames Per Second
        74140, -- 2503.14694 HaploVL: A Single-Transformer Baseline for Multi-Modal Understanding
        74155, -- 2503.08502 The Space Between: On Folding, Symmetries and Sampling
        74168, -- 2503.08154 S2A: A Unified Framework for Parameter and Memory Efficient Transfer   Learning
        74194, -- 2503.07029 Availability-aware Sensor Fusion via Unified Canonical Space
        74386, -- 2502.21279 L-Lipschitz Gershgorin ResNet Network
        74855, -- 2501.12983 LLM4WM: Adapting LLM for Wireless Multi-Tasking
        74941, -- 2502.01588 A Differentiable Alignment Framework for Sequence-to-Sequence Modeling via Optim
        75135, -- 2501.11755 A generalizable 3D framework and model for self-supervised learning in   medical
        75304, -- 2501.01855 UAV-DETR: Efficient End-to-End Object Detection for Unmanned Aerial Vehicle Imag
        75352, -- 2412.19351 ETTA: Elucidating the Design Space of Text-to-Audio Models
        75483, -- 2412.10338 XYScanNet: A State Space Model for Single Image Deblurring
        75638, -- 2412.00784 EDTformer: An Efficient Decoder Transformer for Visual Place Recognition
        75735, -- 2411.14684 Learning Modality-Aware Representations: Adaptive Group-wise Interaction Network
        75826, -- 2411.06807 Wavehax: Aliasing-Free Neural Waveform Synthesis Based on 2D Convolution   and H
        75845, -- 2411.04644 wav2sleep: A Unified Multi-Modal Approach to Sleep Stage Classification from Phy
        75849, -- 2411.04502 LESnets (Large-Eddy Simulation nets): Physics-informed neural operator   for lar
        75897, -- 2411.00178 Clinical Evaluation of Medical Image Synthesis: A Case Study in Wireless   Capsu
        75919, -- 2410.22421 Point cloud-based diffusion models for the Electron-Ion Collider
        75974, -- 2410.18077 ALTA: Compiler-Based Analysis of Transformers
        76032, -- 2410.12961 Super-resolving Real-world Image Illumination Enhancement: A New Dataset and A C
        76097, -- 2410.08243 Self-Attention Mechanism in Multimodal Context for Banking Transaction Flow
        76113, -- 2410.06820 Learning a Neural Solver for Parametric PDE to Enhance Physics-Informed   Method
        76144, -- 2410.04983 RoWeeder: Unsupervised Weed Mapping through Crop-Row Detection
        76148, -- 2410.05341 NeuroBOLT: Resting-state EEG-to-fMRI Synthesis with Multi-dimensional   Feature
        76350, -- 2409.12108 SPRMamba: Surgical Phase Recognition for Endoscopic Submucosal Dissection with M
        76402, -- 2409.08573 HTR-VT: Handwritten Text Recognition with Vision Transformer
        76451, -- 2409.03996 Goal-Reaching Policy Learning from Non-Expert Observations via Effective Subgoal
        76487, -- 2409.00346 SMAFormer: Synergistic Multi-Attention Transformer for Medical Image Segmentatio
        76680, -- 2407.18320 Solving physics-based initial value problems with unsupervised machine   learnin
        76823, -- 2407.01012 Swish-T : Enhancing Swish Activation with Tanh Bias for Improved Neural Network
        76901, -- 2406.17815 SUM: Saliency Unification through Mamba for Visual Attention Modeling
        77104, -- 2406.01465 AIFS -- ECMWF's data-driven forecasting system
        77111, -- 2406.01189 MultiMax: Sparse and Multi-Modal Attention Learning
        77371, -- 2404.15956 A Survey on Visual Mamba
        77448, -- 2404.07993 Connecting NeRFs, Images, and Text
        77542, -- 2404.00288 Seeing the Unseen: A Frequency Prompt Guided Transformer for Image Restoration
        77605, -- 2403.13430 MTP: Advancing Remote Sensing Foundation Model via Multi-Task Pretraining
        77606, -- 2406.17590 Multimodal Chaptering for Long-Form TV Newscast Video
        77880, -- 2401.16650 Augmenting Replay in World Models for Continual Reinforcement Learning
        78159, -- 2312.02067 Learning Feynman integrals from differential equations with neural   networks
        78160, -- 2312.01800 Collaborative Neural Painting
        78187, -- 2311.17241 End-to-End Temporal Action Detection with 1B Parameters Across 1000 Frames
        78378, -- 2310.09385 PIM-GPT: A Hybrid Process-in-Memory Accelerator for Autoregressive   Transformer
        78531, -- 2309.07615 Multilingual Audio Captioning using machine translated data
        78537, -- 2311.06253 Advancing Parsimonious Deep Learning Weather Prediction using the HEALPix Mesh
        78556, -- 2309.02612 Music Source Separation with Band-Split RoPE Transformer
        78579, -- 2309.00454 CoNeTTE: An efficient Audio Captioning system leveraging multiple   datasets wit
        78594, -- 2308.16258 Robust Principles: Architectural Design Principles for Adversarially   Robust CN
        78836, -- 2306.17525 MeLM, a generative pretrained language modeling framework that solves   forward
        78940, -- 2306.00830 Adapting a ConvNeXt model to audio classification on AudioSet
        79073, -- 2305.01482 Multitask learning in Audio Captioning: a sentence embedding regression   loss a
        79112, -- 2304.10593 DeepReShape: Redesigning Neural Networks for Efficient Private Inference
        79439, -- 2301.04944 ViTs for SITS: Vision Transformers for Satellite Image Time Series
        79569, -- 2211.08482 DyFraNet: Forecasting and Backcasting Dynamic Fracture Mechanics in   Space and
        79593, -- 2211.04071 Improving performance of real-time full-band blind packet-loss   concealment wit
        79644, -- 2210.11672 Stochastic Adaptive Activation Function
        79869, -- 2207.00499 MotionMixer: MLP-based 3D Human Body Pose Forecasting
        80006, -- 2112.10482 ScanQA: 3D Question Answering for Spatial Scene Understanding
        80064, -- 2204.06772 ViTOL: Vision Transformer for Weakly Supervised Object Localization
        80124, -- 2203.10705 Compression of Generative Pre-trained Language Models via Quantization
        80166, -- 2203.00960 Aggregated Pyramid Vision Transformer: Split-transform-merge Strategy for Image
        80262, -- 2201.04288 Multiview Transformers for Video Recognition
        80379, -- 2111.11187 PointMixer: MLP-Mixer for Point Cloud Understanding
        80476, -- 2110.02065 SDR: Efficient Neural Re-ranking using Succinct Document Representation
        80554, -- 2108.11116 TransFER: Learning Relation-aware Facial Expression Representations with Transfo
        81312, -- 2005.08314 TaBERT: Pretraining for Joint Understanding of Textual and Tabular Data
        81666, -- 1907.07561 Self-Attentive Hawkes Processes
        82952, -- 2605.08767 From Holo Pockets to Electron Density: GPT-style Drug Design with Density
        83004, -- 2605.10468 Can Muon Fine-tune Adam-Pretrained Models?
        83408, -- 2605.18549 Monitoring the Internal Monologue: Probe Trajectories Reveal Reasoning Dynamics
        83481, -- 2605.17659 Bug or Feature^2: Weight Drift, Activation Sparsity, and Spikes
        83972, -- 2409.19289 FINE: Factorizing Knowledge for Initialization of Variable-sized Diffusion Model
        84167, -- 2511.12834 SAGA: Source Attribution of Generative AI Videos
        84355, -- 2512.06332 CryoHype: Reconstructing a thousand cryo-EM structures with transformer-based hy
        84513, -- 2602.11673 RI-Mamba: Rotation-Invariant Mamba for Robust Text-to-Shape Retrieval
        84558, -- 2602.19585 Tri-Subspaces Disentanglement for Multimodal Sentiment Analysis
        84679, -- 2603.00920 Spectral Super-Resolution via Adversarial Unfolding and Data-Driven Spectrum Reg
        84706, -- 2603.02098 Efficient and High-Fidelity Omni Modality Retrieval
        84939, -- 2603.16641 FlowComposer: Composable Flows for Compositional Zero-Shot Learning
        84996, -- 2603.19918 Learning Like Humans: Analogical Concept Learning for Generalized Category Disco
        85088, -- 2603.24326 Boosting Document Parsing Efficiency and Performance with Coarse-to-Fine Visual
        85110, -- 2603.25159 A Semantically Disentangled Unified Model for Multi-category 3D Anomaly Detectio
        85139, -- 2603.26096 AcTTA: Rethinking Test-Time Adaptation via Dynamic Activation
        85369, -- 2604.12625 Neural Dynamic GI: Random-Access Neural Compression for Temporal Lightmaps in Dy
        85431, -- 2604.20286 MambaLiteUNet: Cross-Gated Adaptive Feature Fusion for Robust Skin Lesion Segmen
        85747, -- 2506.19865 Scalable and Cost-Efficient de Novo Template-Based Molecular Generation
        85770, -- 2505.22866 Scaling Offline RL via Efficient and Expressive Shortcut Models
        85857, -- 2505.15345 Hadamax Encoding: Elevating Performance in Model-Free Atari
        85901, -- 2505.20922 Revisiting Multi-Agent World Modeling from a Diffusion-Inspired Perspective
        85952, -- 2510.03276 QuadEnhancer: Leveraging Quadratic Transformations to Enhance Deep Neural Networ
        86093, -- 2507.04725 Consistent Supervised-Unsupervised Alignment for Generalized Category Discovery
        86131, -- 2505.22566 Universal Visuo-Tactile Video Understanding for Embodied Interaction
        86408, -- 2506.05259 Learning long range dependencies through time reversal symmetry breaking
        86457, -- 2506.15507 Over-squashing in Spatiotemporal Graph Neural Networks
        86518, -- 2505.21364 Towards Interpretability Without Sacrifice: Faithful Dense Layer Decomposition w
        86543, -- 2412.09059 Go With the Flow: Fast Diffusion for Gaussian Mixture Models
        86652, -- 2506.15544 Stable Gradients for Stable Learning at Scale in Deep Reinforcement Learning
        86991, -- 2505.14512 Just One Layer Norm Guarantees Stable Extrapolation
        87038, -- 2510.10790 BioOSS: A Bio-Inspired Oscillatory State System with Spatio-Temporal Dynamics
        87182, -- 2508.12511 Trust Region Constrained Measure Transport in Path Space for Stochastic Optimal
        87298, -- 2502.12627 DAMamba: Vision State Space Model with Dynamic Adaptive Scan
        87336, -- 2509.15328 Kuramoto Orientation Diffusion Models
        87442, -- 2404.13182 Spectral Convolutional Conditional Neural Processes
        87567, -- 2507.18569 Adversarial Distribution Matching for Diffusion Distillation Towards Efficient I
        87622, -- 2508.09000 UniConvNet: Expanding Effective Receptive Field while Maintaining Asymptotically
        87742, -- 2507.03257 LACONIC: A 3D Layout Adapter for Controllable Image Creation
        87802, -- 2507.07802 Synergistic Prompting for Robust Visual Recognition with Missing Modalities
        87968, -- 2509.19939 AJAHR: Amputated Joint Aware 3D Human Mesh Recovery
        88022, -- 2406.06465 AID: Adapting Image2Video Diffusion Models for Instruction-guided Video Predicti
        88037, -- 2505.02192 DualReal: Adaptive Joint Training for Lossless Identity-Motion Fusion in Video C
        88150, -- 2503.04151 Robust Multi-View Learning via Representation Fusion of Sample-Level Attention a
        88160, -- 2503.20174 Devil is in the Uniformity: Exploring Diverse Learners within Transformer for Im
        88163, -- 2506.08694 MoSiC: Optimal-Transport Motion Trajectory for Dense Self-Supervised Learning
        88262, -- 2506.22710 LightBSR: Towards Lightweight Blind Super-Resolution via Discriminative Implicit
        88292, -- 2508.09824 Reverse Convolution and Its Applications to Image Restoration
        88363, -- 2508.04122 Conditional Latent Diffusion Models for Zero-Shot Instance Segmentation
        88390, -- 2509.12482 Towards Foundational Models for Single-Chip Radar
        88397, -- 2507.20163 Player-Centric Multimodal Prompt Generation for Large Language Model Based Ident
        88436, -- 2503.17544 PRIMAL: Physically Reactive and Interactive Motor Model for Avatar Learning
        88509, -- 2503.02410 Neuroverse3D: Developing In-Context Learning Universal Model for Neuroimaging in
        88528, -- 2507.02119 Scaling Collapse Reveals Universal Dynamics in Compute-Optimally Trained Neural
        88713, -- 2505.20896 How Do Transformers Learn Variable Binding in Symbolic Programs?
        88724, -- 2501.02086 Instruction-Following Pruning for Large Language Models
        89099, -- 2502.07616 Tractable Transformers for Flexible Conditional Generation
        89113, -- 2502.16824 Posterior Inference with Diffusion Models for High-dimensional Black-box Optimiz
        89122, -- 2410.01706 Sable: a Performant, Efficient and Scalable Sequence Model for MARL
        89132, -- 2411.09858 One Leaf Reveals the Season: Occlusion-Based Contrastive Learning with Semantic-
        89174, -- 2504.19496 DISCO: learning to DISCover an evolution Operator for multi-physics-agnostic pre
        89390, -- 2410.02348 Simplicity Bias and Optimization Threshold in Two-Layer ReLU Networks
        89447, -- 2502.21274 BAnG: Bidirectional Anchored Generation for Conditional RNA Design
        89484, -- 2503.19300 UniMoMo: Unified Generative Modeling of 3D Molecules for De Novo Binder Design
        89887, -- 2505.12917 Temporal Query Network for Efficient Multivariate Time Series Forecasting
        89889, -- 2506.13120 Accelerating PDE-Constrained Optimization by the Derivative of Neural Operators
        90000, -- 2502.05169 Flopping for FLOPs: Leveraging Equivariance for Computational Efficiency
        90129, -- 2503.13836 SALAD: Skeleton-aware Latent Diffusion for Text-driven Motion Generation and Edi
        90166, -- 2501.13134 UniRestore: Unified Perceptual and Task-Oriented Image Restoration Model Using D
        90208, -- 2503.17093 ColabSfM: Collaborative Structure-from-Motion by Point Cloud Registration
        90227, -- 2406.17503 WAVE: Weight Templates for Adaptive Initialization of Variable-sized Models
        90234, -- 2501.09754 Lost in Translation, Found in Context: Sign Language Translation with Contextual
        90243, -- 2503.16930 Vision-Language Gradient Descent-driven All-in-One Deep Unfolding Networks
        90564, -- 2503.18123 End-to-End Implicit Neural Representations for Classification
        90578, -- 2412.12278 Towards a Universal Synthetic Video Detector: From Face or Background Manipulati
        90638, -- 2405.16414 Robust Message Embedding via Attention Flow-Based Steganography
        90730, -- 2501.08279 SmartEraser: Remove Anything from Images using Masked-Region Guidance
        90812, -- 2501.12381 Parallel Sequence Modeling via Generalized Spatial Propagation Network
        90827, -- 2504.16023 PointLoRA: Low-Rank Adaptation with Token Selection for Point Cloud Learning
        90836, -- 2310.11439 From Alexnet to Transformers: Measuring the Non-linearity of Deep Neural Network
        90876, -- 2504.05265 From Sparse Signal to Smooth Motion: Real-Time Motion Generation with Rolling Pr
        90904, -- 2503.10065 Do We Always Need the Simplicity Bias? Looking for Optimal Inductive Biases in t
        90973, -- 2503.10324 IDEA: Inverted Text with Cooperative Deformable Aggregation for Multi-modal Obje
        91035, -- 2411.12633 Instant Policy: In-Context Imitation Learning via Graph Diffusion
        91040, -- 2410.03943 Oscillatory State-Space Models
        91053, -- 2409.02313 On the Benefits of Memory for Modeling Time-Dependent PDEs
        91093, -- 2410.14673 Self-supervised contrastive learning performs non-linear system identification
        91138, -- 2503.00699 Parameter Expanded Stochastic Gradient Markov Chain Monte Carlo
        91143, -- 2503.18216 Adaptive Rank Allocation: Speeding Up Modern Transformers with RaNA Adapters
        91236, -- 2405.19237 ConceptPrune: Concept Editing in Diffusion Models via Skilled Neuron Pruning
        91483, -- 2406.15244 AdaGrad under Anisotropic Smoothness
        91645, -- 2410.17174 From Attention to Activation: Unraveling the Enigmas of Large Language Models
        91842, -- 2410.20092 OGBench: Benchmarking Offline Goal-Conditioned RL
        92003, -- 2408.08776 NEAR: A Training-Free Pre-Estimator of Machine Learning Model Performance
        92191, -- 2408.01536 Active Learning for Neural PDE Solvers
        92257, -- 2503.13926 Learning Shape-Independent Transformation via Spherical Representations for Cate
        92302, -- 2410.01990 Deep Learning Alternatives Of The Kolmogorov Superposition Theorem
        92368, -- 2410.07972 Learning Equivariant Non-Local Electron Density Functionals
        92379, -- 2406.00368 Learning Spatiotemporal Dynamical Systems from Point Process Observations
        92650, -- 2507.09768 Knowing When to Quit: Probabilistic Early Exits for Speech Separation Networks
        92684, -- 2505.05155 A Unified Federated Framework for Trajectory Data Preparation via LLMs
        92694, -- 2602.18117 Flow Matching with Injected Noise for Offline-to-Online Reinforcement Learning
        92713, -- 2509.24198 Negative Pre-activations Differentiate Syntax
        92751, -- 2604.17986 Latent Fourier Transform
        92815, -- 2510.07650 Value Flows
        92861, -- 2604.20627 Occupancy Reward Shaping: Improving Credit Assignment for Offline Goal-Condition
        93153, -- 2506.05233 MesaNet: Sequence Modeling by Locally Optimal Test-Time Training
        93179, -- 2603.23173 A Schrödinger Eigenfunction Method for Long-Horizon Stochastic Optimal Control
        93185, -- 2510.13704 Simplicial Embeddings Improve Sample Efficiency in Actor–Critic Agents
        93237, -- 2509.25913 Understanding the Mixture-of-Experts with Nadaraya-Watson Kernel
        93247, -- 2602.18015 Flow Actor-Critic for Offline Reinforcement Learning
        93293, -- 2510.12273 Multi-Action Self-Improvement For Neural Combinatorial Optimization
        93385, -- 2512.10683 Optimal transport unlocks end-to-end learning for single-molecule localization
        93431, -- 2509.06863 floq: Training Critics via Flow-Matching for Scaling Compute in Value-Based RL
        93458, -- 2510.09146 Score-Based Density Estimation from Pairwise Comparisons
        93486, -- 2503.22841 GmNet: Revisiting Gating Mechanisms From A Frequency View
        93498, -- 2506.08902 Intention-Conditioned Flow Occupancy Models
        94117, -- 2510.06714 Dual Goal Representations
        94138, -- 2510.22512 Transitive RL: Value Learning via Divide and Conquer
        94364, -- 2602.05051 ReFORM: Reflected Flows for On-support Offline RL via Noise Manipulation
        94449, -- 2510.19382 A Derandomization Framework for Structure Discovery: Applications in Neural Netw
        94524, -- 2512.08108 Scalable Offline Model-Based RL with Action Chunks
        94529, -- 2509.22562 Activation Function Design Sustains Plasticity in Continual Learning
        94586, -- 2506.01502 Learning of Population Dynamics: Inverse Optimization Meets JKO Scheme
        94664, -- 2603.28603 ELViS: Efficient Visual Similarity from Local Descriptors that Generalizes Acros
        94796, -- 2505.15504 Exploiting Low-Dimensional Manifold of Features for Few-Shot Whole Slide Image C
        94812, -- 2602.07415 Learning Molecular Chirality via Chiral Determinant Kernels
        95004, -- 2512.08914 SAQ: Stabilizer-Aware Quantum Error Correction Decoder
        95087, -- 2606.05979 World-Language-Action Model for Unified World Modeling, Language Reasoning, and
        95263, -- 2603.14974 Voronoi-Based Second-Order Descriptor with Whitened Metric in LiDAR Place Recogn
        95865, -- 2602.11656 SToRM: Supervised Token Reduction for Multi-Modal LLMs Toward Efficient End-To-E
        96160, -- 2603.06927 A Contrastive Few-Shot RGB-D Traversability Segmentation Framework for Indoor Ro
        96969, -- 2507.05695 Hybrid Diffusion Policies with Projective Geometric Algebra for Efficient Robot
        98011, -- 2606.08324 Set-Based Transformer for Atmospheric Compensation in Standoff LWIR Hyperspectra
        98016, -- 2606.09659 End-to-End Context Compression at Scale
        98437, -- 2606.16673 MMDiff: Extending Diffusion Transformers for Multi-Modal Generation
        98571, -- 2502.03227 Adversarial Dependence Minimization
        98625, -- 2310.02083 Point Neighborhood Embeddings
        98632, -- 2206.10555 LargeKernel3D: Scaling up Kernels in 3D Sparse CNNs
        99173, -- 2601.19694 Self-Supervised Weight Templates for Scalable Vision Model Initialization
        99186, -- 2605.24064 Generative Representation Learning on Hyper-relational Knowledge Graphs via Mask
        99195, -- 2603.23198 Sparser, Faster, Lighter Transformer Language Models
        99232, -- 2602.06154 MoSE: Mixture of Slimmable Experts for Efficient and Adaptive Language Models
        99414, -- 2605.01663 Towards Efficient and Expressive Offline RL via Flow-Anchored Noise-conditioned
        99477, -- 2601.22476 RulePlanner: All-in-One Reinforcement Learner for Unifying Design Rules in 3D Fl
        99543, -- 2605.24423 Benchmarking the Limits of In-Context Reinforcement Learning for Ad-Hoc Teamwork
        99605, -- 2605.29028 Return-to-Go Is More Than a Number: Q-Guided Alignment for Return-Conditioned Su
        99811, -- 2601.03019 DNACHUNKER: Learnable Tokenization for DNA Language Models
        99974, -- 2605.29983 Improving Adversarial Robustness of Attribution via Implicit Regularization
        100005, -- 2601.00242 Neural Minimum Weight Perfect Matching for Quantum Error Codes
        100155, -- 2605.24084 Verified SHAP: Provable Bounds for Exact Shapley Values of Neural Networks
        100176, -- 2602.14972 Use What You Know: Causal Foundation Models with Partial Graphs
        100197, -- 2601.21853 LEMUR: Learned Multi-Vector Retrieval
        100554, -- 2606.17816 Conservation Laws for Modern Neural Architectures
        100734, -- 2601.19597 The Geometric Mechanics of Contrastive Representation Learning: Alignment Potent
        100767, -- 2605.15603 Offline Reinforcement Learning with Universal Horizon Models
        100769, -- 2605.20609 Compositional Transduction with Latent Analogies for Offline Goal-Conditioned Re
        100843, -- 2505.20137 ePC: Fast and Deep Predictive Coding in Digital Simulation
        100870, -- 2605.25740 Latent Representation Alignment for Offline Goal-Conditioned Reinforcement Learn
        100910, -- 2602.04509 Model-Dowser: Data-Free Importance Probing to Mitigate Catastrophic Forgetting i
        100912, -- 2602.12390 Rational Neural Networks have Expressivity Advantages
        100914, -- 2602.15634 Beyond ReLU: Bifurcation, Oversmoothing, and Topological Priors
        101522, -- 2606.01172 Revisiting Neural Processes via Fourier Transform and Volterra Series
        101607, -- 2605.01702 Floating-Point Networks with Automatic Differentiation Can Represent Almost All
        101642, -- 2605.20839 Activation-Free Backbones for Image Recognition: Polynomial Alternatives within
        101675, -- 2507.07532 Neural Concept Verifier: Scaling Prover-Verifier Games via Concept Encodings
        101746, -- 2602.19799 Path-conditioned training: a principled way to rescale ReLU neural networks
        101868, -- 2605.08253 Path-Coupled Bellman Flows for Distributional Reinforcement Learning
        101914, -- 2508.11205 Meta-learning Structure-Preserving Dynamics
        102069, -- 2602.02853 Recurrent Equivariant Constraint Modulation: Learning Per-Layer Symmetry Relaxat
        102075, -- 2603.02462 Can Computational Reducibility Lead to Transferable Models for Graph Combinatori
        102127, -- 2506.09276 Learning the Minimum Action Distance
        102257, -- 2606.05602 Fix the Mind, Not the Move: Interpretable AI Assistance via Knowledge-Gap Locali
        102335, -- 2605.13435 Q-Flow: Stable and Expressive Reinforcement Learning with Flow-based Policy
        102539, -- 2602.07494 Hyperparameter Transfer Laws for Non-Recurrent Multi-Path Neural Networks
        102569, -- 2607.04064 Speaker-Disentangled Chunk-Wise Regression for Syllabic Tokenization
        102604, -- 2407.16232 Channel-Partitioned Windowed Attention And Frequency Learning for Single Image S
        102632, -- 2607.05803 Quantifying and Expanding the Theoretical Capacity of Late-Interaction Retrieval
        102697, -- 2311.05709 OmniVec: Learning robust representations with cross modal sharing
        102882, -- 2604.07239 Efficient Learned Data Compression via Dual-Stream Feature Decoupling
        103644, -- 2601.18006 PEAR: Pairwise Evaluation for Automatic Relative Scoring in Machine Translation
        103888, -- 2502.02538 Flow Q-Learning
        104085, -- 2209.11750 Transformer-based Models to Deal with Heterogeneous Environments in Human Activi
        104260, -- 2111.14813 TransWeather: Transformer-based Restoration of Images Degraded by Adverse Weathe
        104341, -- 2406.12384 VRSBench: A Versatile Vision-Language Benchmark Dataset for Remote Sensing Image
        104360, -- 2211.07273 MLIC: Multi-Reference Entropy Model for Learned Image Compression
        104413, -- 2607.17146 The Geometry of Semantic Space: A Continuous Geometric Framework for the Transfo
        105058, -- 2503.14655 Core-Periphery Principle Guided State Space Model for Functional Connectome Clas
        105671, -- 2404.17484 Sparse Reconstruction of Optical Doppler Tomography with Alternative State Space
        105728, -- 2501.02227 tCURLoRA: Tensor CUR Decomposition Based Low-Rank Parameter Adaptation and Its A
        105902, -- 2304.02216 Industrial Anomaly Detection with Domain Shift: A Real-world Dataset and Masked
        105952, -- 2607.12362 Implicit 4D Gaussian Splatting for Fast Motion with Large Inter-Frame Displaceme
        105990, -- 2606.00761 Confidence-Adaptive SwiGLU for Mixture-of-Experts
        106305, -- 2604.21632 To See the Unseen: on the Generalization Ability of Transformers in Symbolic Rea
        106579, -- 2510.20210 Enhancing Stability and Fidelity for Zero-Shot TTS with a Multi-Level Evaluator
        106664, -- 2511.17967 CADTrack: Learning Contextual Aggregation with Deformable Alignment for Robust R
        106776, -- 2504.07598 On Model and Data Scaling for Skeleton-based Self-Supervised Gait Recognition
        106806, -- 2512.20921 Self-supervised Multiplex Consensus Mamba for General Image Fusion
        106927, -- 2507.02227 PhysicsCorrect: A Training-Free Approach for Stable Neural PDE Simulations
        107362, -- 2410.13106 Cliqueformer: Model-Based Optimization with Structured Transformers
        107641, -- 2601.10001 DW-DGAT: Dynamically Weighted Dual Graph Attention Network for Neurodegenerative
        107922, -- 2511.09883 HCC-3D: Hierarchical Compensatory Compression for 98% 3D Token Reduction in Visi
        108043, -- 2603.10034 A Principle-Driven Adaptive Policy for Group Cognitive Stimulation Dialogue for
        108383, -- 2602.08564 M-Loss: Quantifying Model Merging Compatibility with Limited Unlabeled Data
        108692, -- 2605.27044 BatteryMFormer: Multi-level Learning for Battery Degradation Trajectory Forecast
        108810, -- 2605.19014 SAGA: A Sequence-Adaptive Generative Architecture for Multi-Horizon Probabilisti
        109202, -- 2109.15053 Fine-tuning wav2vec2 for speaker recognition
        109228, -- 2406.07456 fKAN: Fractional Kolmogorov-Arnold Networks with trainable Jacobi basis function
        109399, -- 2012.06185 Exploring wav2vec 2.0 on speaker verification and language identification
        109501, -- 2608.14929 Training Leaves Traces: Centered Residual Signatures for Language Model Lineage
        109903, -- 2411.04480 CFPNet: Improving Lightweight ToF Depth Completion via Cross-Zone Feature Propag
        110873, -- 2505.17701 COUNTDOWN: Contextually Sparse Activation Filtering Out Unnecessary Weights in D
        110996, -- 2410.19195 Label Set Optimization via Activation Distribution Kurtosis for Zero-Shot Classi
        111047, -- 2509.20734 Probability Distribution Collapse: A Critical Bottleneck to Compact Unsupervised
        111075, -- 2505.01475 CodeSSM: Towards State Space Models for Code Understanding
        111239, -- 2505.23379 Vision-Integrated High-Quality Neural Speech Coding
        111539, -- 2506.01455 Universal Preference-Score-based Pairwise Speech Quality Assessment
        111894, -- 2505.20868 Spotlight-TTS: Spotlighting the Style via Voiced-Aware Style Extraction and Styl
        112028, -- 2412.17778 From KAN to GR-KAN: Advancing Speech Enhancement with KAN-Based Methodology
        112150, -- 2507.02666 ASDA: Audio Spectrogram Differential Attention Mechanism for Self-Supervised Rep
        112722, -- 2312.14828 "Plan, Posture and Go: Towards Open-vocabulary Text-to-Motion Generation"
        112752, -- 2312.02819 Probabilistic Weather Forecasting with Deterministic Guidance-based Diffusion Mo
        113079, -- 2403.04697 AUFormer: Vision Transformers are Parameter-Efficient Facial Action Unit Detecto
        113127, -- 2211.13220 TetraDiffusion: Tetrahedral Diffusion Models for 3D Shape Generation
        113240, -- 2405.19882 PixOOD: Pixel-Level Out-of-Distribution Detection
        113245, -- 2407.07564 Trainable Highly-expressive Activation Functions
        113390, -- 2312.00826 DEVIAS: Learning Disentangled Video Representations of Action and Scene
        113428, -- 2409.06535 "PoseEmbroider: Towards a 3D, Visual, Semantic-aware Human Pose Representation"
        113485, -- 2407.19675 Semi-Supervised Teacher-Reference-Student Architecture for Action Quality Assess
        113517, -- 2409.20139 Characterizing Model Robustness via Natural Input Gradients
        113642, -- 2403.14270 Scene-Graph ViT: End-to-End Open-Vocabulary Visual Relationship Detection
        113644, -- 2408.02014 Unsupervised Representation Learning by Balanced Self Attention Matching
        113667, -- 2504.02797 Spline-based Transformers
        113670, -- 2406.10600 SparseRadNet: Sparse Perception Neural Network on Subsampled Radar Data
        114867, -- 2409.17055 DRIM: Learning Disentangled Representations from Incomplete Multimodal Healthcar
        115134, -- 2406.09696 MoME: Mixture of Multimodal Experts for Cancer Survival Prediction
        115252, -- 2403.10858 RetMIL: Retentive Multiple Instance Learning for Histopathological Whole Slide I
        115339, -- 2409.07564 TabMixer: Noninvasive Estimation of the Mean Pulmonary Artery Pressure via Imagi
        115385, -- 2409.08492 Tri-Plane Mamba: Efficiently Adapting Segment Anything Model for 3D Medical Imag
        115598, -- 2311.11860 LION: Empowering Multimodal Large Language Model with Dual-Level Visual Knowledg
        115613, -- 2404.04996 Fantastic Animals and Where to Find Them: Segment Any Marine Animal with Dual SA
        115677, -- 2403.19811 X-MIC: Cross-Modal Instance Conditioning for Egocentric Action Generalization
        115811, -- 2403.03890 Hierarchical Diffusion Policy for Kinematics-Aware Multi-Task Robotic Manipulati
        115859, -- 2403.02611 A Unified Framework for Microscopy Defocus Deblur with Multi-Pyramid Transformer
        116019, -- 2303.16198 Multi-modal Learning for Geospatial Vegetation Forecasting
        116043, -- 2312.02753 C3: High-Performance and Low-Complexity Neural Compression from a Single Image o
        116102, -- 2406.01334 HHMR: Holistic Hand Mesh Recovery by Enhancing the Multimodal Controllability of
        116179, -- 2406.06820 Adapters Strike Back
        116211, -- 2402.02887 Time- Memory- and Parameter-Efficient Visual Adaptation
        116268, -- 2404.04624 Bridging the Gap Between End-to-End and Two-Step Text Spotting
        116284, -- 2403.17936 ConvoFusion: Multi-Modal Conversational Diffusion for Co-Speech Gesture Synthesi
        116355, -- 2307.04760 Learning Spatial Features from Audio-Visual Correspondence in Egocentric Videos
        116481, -- 2311.03149 Asymmetric Masked Distillation for Pre-Training Small Foundation Models
        116483, -- 2404.10880 HumMUSS: Human Motion Understanding using State Space Models
        116509, -- 2404.09451 Contrastive Mean-Shift Learning for Generalized Category Discovery
        116526, -- 2403.16002 SDSTrack: Self-Distillation Symmetric Adapter Learning for Multi-Modal Visual Ob
        116802, -- 2402.18490 TAMM: TriAdapter Multi-Modal Learning for 3D Shape Understanding
        116929, -- 2403.11270 Bilateral Propagation Network for Depth Completion
        117029, -- 2402.11874 Language-guided Image Reflection Separation
        117077, -- 2507.13364 OmniVec2 - A Novel Transformer based Network for Large Scale Multimodal and Mult
        117172, -- 2304.12160 End-to-End Spatio-Temporal Action Localisation with Video Transformers
        117345, -- 2601.13126 A Streamlined Attention-based Network for Descriptor Extraction
        117731, -- 2606.14307 Pano3D: Unified 3D Reconstruction and Panoptic Segmentation
        118143, -- 2607.02593 Token-level Response-visual Attention Guidance for Multimodal LLMs Knowledge Dis
        118152, -- 2606.32040 FaceMoE: Mixture of Experts for Low-Resolution Face Recognition
        118307, -- 2606.30777 Unveiling Transferability in Trajectory Prediction via Latent Scene Embeddings
        118836, -- 2607.22087 FAIR: Feature-Augmented Implicit Regularization for AI-generated Fake Image Dete
        119010, -- 2607.10841 Align and Segment: Unsupervised Learning for Building Segmentation From Misalign
        119017, -- 2606.24375 MATCH: Flow Matching for Multi-View Anomaly Detection
        119144, -- 2607.29059 Learning from Adversity: Semantic-Aware Mask Refinement through Adversarial Pert
        119145, -- 2608.20884 Breaking High Confidence: Practical Face Impersonation under High-Security Thres
        119257, -- 2606.24072 Fabric Image Demoiréing Benchmark from Synthesis to Restoration
        119281, -- 2607.06438 WristMimic: Full-Body Humanoid Control with Wrist-Guided Manipulation
        119809, -- 2303.08096 MELON: NeRF with Unposed Images in SO(3)
        119948, -- 2405.14338 Mamba4D: Efficient 4D Point Cloud Video Understanding with Disentangled Spatial-
        120107, -- 2506.04453 Gradient Inversion Attacks on Parameter-Efficient Fine-Tuning
        120150, -- 2501.08837 MANTA: Diffusion Mamba for Efficient and Effective Stochastic Long-Term Dense Ac
        120178, -- 2505.22427 RC-AutoCalib: An End-to-End Radar-Camera Automatic Calibration Network
        120474, -- 2412.06243 U-Know-DiffPAN: An Uncertainty-aware Knowledge Distillation Diffusion Framework
        120678, -- 2603.28091 SHARP: Short-Window Streaming for Accurate and Robust Prediction in Motion Forec
        120747, -- 2405.18684 Learning Diffeomorphism for Medical Image Registration with Time-Embedded Archit
        121602, -- 2605.22997 Scene Reconstruction as Mapping Priors for 3D Detection
        121981, -- 2609.17488 LimiX-2: A Contextual Mechanism Network Towards General Structured-Data Intellig
        122469, -- 2609.38177 Imagine3D-LLM: Teaching MLLMs to Imagine 3D Scenes Before Answering
        122705, -- 2610.02840 PointWAM: 3D World Action Modeling for Dexterous Robotic Manipulation
        122941, -- 2610.03858 Retrieval-Centric Deep Learning in Growing Nonparametric Neural Networks
        123354, -- 2604.08649 PRAGMA: Revolut Foundation Model
        123407, -- 2610.11019 Mid-Training Language Models on Raw Video
        123497, -- 2610.20137 StreamErase: Towards Ultra-Fast Streaming Video Erasing
        123603, -- 2610.14232 Speech event detector: Timestamped detection of non-verbal vocalizations and bac
        123653, -- 2305.00603 Consolidator: Mergeable Adapter with Grouped Connections for Visual Adaptation
        123939, -- 2407.16126 MxT: Mamba x Transformer for Image Inpainting
        124195, -- 2606.21136 Horizon Adaptive Offline Policy Learning via Value Stitching
        124231, -- 2610.11376 CRISP: Fixing Flying Pixels in Latent LiDAR Generation via Diffusion Decoding
        124538, -- 2605.06258 The Weight Gram Matrix Captures Sequential Feature Linearization in Deep Network
        124696, -- external Activation Functions Shape Token Synchronization in Stochastic Transformer Dynam
        125218, -- 2610.12624 MemReg: Streaming Outdoor LiDAR Point Cloud Registration with Hybrid Memory Buff
        125259, -- 2603.14405 ES-Merging: Biological MLLM Merging via Embedding Space Signals
        125333, -- external A Revisit of Hamiltonian Monte Carlo Efficiency on Bayesian Neural Networks
        125530, -- 2605.05850 Align3D-AD: Cross-Modal Feature Alignment and Dual-Prompt Learning for Zero-shot
        125603, -- 2605.31547 The Dynamic-Probabilistic Consistency Gap in Chaotic Surrogate Modeling
        125712, -- external Revisiting the Adam–SGD Gap Beyond Single Factors
        126219, -- 2605.14276 Training-Free Generative Sampling via Moment-Matched Score Smoothing
        126258, -- external From Approximation to Computation: Universal Power of Deep Narrow Networks at Co
        127410, -- 2610.19559 Learning Visual Speech Representations via Cross-Modal Distillation and Joint Fa
        127812, -- 2605.31466 VolFill: Single-View Amodal 3D Scene Reconstruction with Volumetric Flow Matchin
        127938, -- 2607.18264 MUX: Continuous Reasoning via Multiplexed Tokens
        128252, -- 2609.32811 Progressive Risk Estimation for Accident Anticipation
        128267, -- 2605.05812 Long-Horizon Q-Learning: Accurate Value Learning via n-Step Inequalities
        128689, -- 2602.22586 TabDLM: Free-Form Tabular Data Generation via Joint Numerical–Language Diffusion
        129391, -- 2512.07128 MulCLIP: A Multi-level Alignment Framework for Enhancing Fine-grained Long-conte
        129603, -- 2606.05261 NIV: Neural Axis Variations for Variable Font Generation
        129626, -- 2610.11175 Higher-Order Action Supervision Makes A Strong Policy Class
        129705, -- 2507.00480 Posterior Inference in Latent Space for Scalable Constrained Black-box Optimizat
        129709, -- 2610.07899 Variance-Averse n-Step Offline Reinforcement Learning for Sparse Long-Horizon En
        130072, -- external Mixture of Activations: Token-Adaptive Mixing for Expressive Feedforward Layers
        130140, -- 2605.27408 Neural Quantum Spectral Operator Learning for Solving Partial Differential Equat
        130376, -- 2510.00563 Memory Determines Learning Direction: A Theory of Gradient-Based Optimization in
        130379, -- 2608.11937 Distillation of Foundation Models for Time-dependent PDEs
        130395, -- 2609.15883 Learning Multimodal One-step Flow Policy via Value-weighted Optimal Transport
        130428, -- 2605.12122 Disentangled Sparse Representations for Concept-Separated Diffusion Unlearning
        130962, -- 2607.03148 Rethinking Neural Nonlinearity as Gating
        131098, -- 2605.16732 DiRotQ: Rotation-Aware Quantization for 4-bit Diffusion Transformers
        131196  -- 2610.08989 LASER: Latent Space Adjoint Matching for Support Constrained Entropy Regularized
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
        918, -- 1710.05941 Searching for Activation Functions
        2445, -- 1908.08681 Mish: A Self Regularized Non-Monotonic Activation Function
        6754, -- 2109.14545 Activation Functions in Deep Learning: A Comprehensive Survey and Benchmark
        21525, -- 2310.04564 ReLU Strikes Back: Exploiting Activation Sparsity in Large Language Models
        22109, -- 2310.11230 Zipformer: A faster and better encoder for automatic speech recognition
        26782, -- 2402.02593 Leveraging Continuously Differentiable Activation Functions for Learning in Quan
        27715, -- 2402.13516 ProSparse: Introducing and Enhancing Intrinsic Activation Sparsity within Large
        32120, -- 2405.20768 Expanded Gating Ranges Improve Activation Functions
        33558, -- 2406.16282 Reducing Fine-Tuning Memory Overhead by Approximate and Memory-Sharing Backpropa
        38828, -- 2410.14687 BrainTransformers: SNN-LLM
        39607, -- 2411.02335 Sparsing Law: Towards Large Language Models with Greater Activation Sparsity
        63136, -- 2601.00922 MetaFormer-driven Encoding Network for Robust Medical Semantic Segmentation
        72531, -- 2505.23942 SG-Blend: Learning an Interpolation Between Improved Swish and GELU for Robust N
        74767, -- 2502.06924 XAMBA: Enabling Efficient State Space Models on Resource-Constrained Neural Proc
        76823, -- 2407.01012 Swish-T : Enhancing Swish Activation with Tanh Bias for Improved Neural Network
        79644, -- 2210.11672 Stochastic Adaptive Activation Function
        82276, -- 1702.03118 Sigmoid-Weighted Linear Units for Neural Network Function Approximation in Reinf
        83011, -- 2605.10933 DECO: Sparse Mixture-of-Experts with Dense-Comparable Performance on End-Side De
        94505, -- 2602.02988 NLI : Non-uniform Linear Interpolation Approximation of Nonlinear Operations for
        95300, -- external Task-Aware and Structure-Knowledge-Guided Quantization for End-To-End YOLO Objec
        98301, -- external Achieving Robust Out-of-Distribution Generalization in Peripheral Blood Smears v
        100688, -- 2605.29497 Convex Basins in Single-Index Model Loss Landscapes: Applications to Robust Reco
        113434, -- 2409.05414 CipherDM: Secure Three-Party Inference for Diffusion Model Sampling
        126739  -- external Capricorn: Highly Efficient and Secure Mixture of Experts Inference Framework
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
        4761, -- 2012.10495 ShineOn: Illuminating Design Choices for Practical Video-based Virtual Clothing
        4923, -- 2101.08692 Characterizing signal propagation to close the performance gap in unnormalized R
        11836, -- 2212.03246 MobileTL: On-device Transfer Learning with Inverted Residual Blocks
        20767, -- 2309.12792 DurIAN-E: Duration Informed Attention Network For Expressive Text-to-Speech Synt
        38694, -- 2410.13288 DurIAN-E 2: Duration Informed Attention Network with Adaptive Variational Autoen
        39686, -- 2411.03884 Polynomial Composition Activations: Unleashing the Dynamics of Large Language Mo
        43726, -- 2502.03654 Gompertz Linear Units: Leveraging Asymmetry for Enhanced Learning Dynamics
        47990, -- 2504.15051 VeLU: Variance-enhanced Learning Unit for Deep Neural Networks
        62707, -- 2601.10740 Neuro-Symbolic Activation Discovery: Transferring Mathematical Structures from P
        64569, -- 2511.19902 Zero-Knowledge Proof Based Verifiable Inference of Models
        71645, -- 2506.23225 Masked Gated Linear Unit
        83481, -- 2605.17659 Bug or Feature^2: Weight Drift, Activation Sparsity, and Spikes
        92713, -- 2509.24198 Negative Pre-activations Differentiate Syntax
        99630, -- 2605.17180 The Geometry of Projection Heads: Conditioning, Invariance, and Collapse
        100554, -- 2606.17816 Conservation Laws for Modern Neural Architectures
        100683, -- 2605.20289 Plug-and-Play Spiking Operators: Breaking the Nonlinearity Bottleneck in Spiking
        100912, -- 2602.12390 Rational Neural Networks have Expressivity Advantages
        101607, -- 2605.01702 Floating-Point Networks with Automatic Differentiation Can Represent Almost All
        105990, -- 2606.00761 Confidence-Adaptive SwiGLU for Mixture-of-Experts
        124696, -- external Activation Functions Shape Token Synchronization in Stochastic Transformer Dynam
        125333, -- external A Revisit of Hamiltonian Monte Carlo Efficiency on Bayesian Neural Networks
        126258, -- external From Approximation to Computation: Universal Power of Deep Narrow Networks at Co
        127869, -- external Cauchy Scientific Networks: Loss–Architecture Alignment and Its Limit
        130962, -- 2607.03148 Rethinking Neural Nonlinearity as Gating
        131816  -- 2611.04449 Near-Zero Token Embeddings Silently Stall Training in Gated Sequence Models
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
        1746, -- 1901.03353 RetinaMask: Learning to predict masks improves state-of-the-art single-shot dete
        3303, -- 2004.02967 Evolving Normalization-Activation Layers
        6540, -- 2109.01123 Benchmarking the Robustness of Instance Segmentation Models
        28294, -- 2403.01123 ELA: Efficient Local Attention for Deep Convolutional Neural Networks
        61971, -- 2601.19611 Explicit Multi-head Attention for Inter-head Interaction in Large Language Model
        81059, -- 2010.10241 BYOL works even without batch statistics
        120458, -- external Dynamic Group Normalization: Spatio-Temporal Adaptation to Evolving Data Statist
        124001, -- 1803.08494 Group Normalization
        124853, -- external Rotation-Invariant Vector Normalization for Molecular Force Learning
        124940, -- external UltraFlash: Accelerating Megapixel Visual Synthesis
        125890  -- 2609.08901 The BatchNorm Illusion: Diagnosing Normalization Artifacts in Machine Unlearning
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
        1568, -- 1810.11654 3D MRI brain tumor segmentation using autoencoder regularization
        1579, -- 1810.12890 DropBlock: A regularization method for convolutional networks
        1659, -- 1811.11718 Partial Convolution based Padding
        1665, -- 1811.12596 Parsing R-CNN for Instance-Level Human Analysis
        1722, -- 1812.09912 Image-to-Image Translation via Group-wise Deep Whitening-and-Coloring Transforma
        1742, -- 1901.02446 Panoptic Feature Pyramid Networks
        1779, -- 1901.09321 Fixup Initialization: Residual Learning Without Normalization
        1851, -- 1902.09843 Adaptive Gradient Methods with Dynamic Bound of Learning Rate
        1902, -- 1903.07291 Semantic Image Synthesis with Spatially-Adaptive Normalization
        1912, -- 1903.10520 Micro-Batch Training with Batch-Channel Normalization and Weight Standardization
        1948, -- 1904.01355 FCOS: Fully Convolutional One-Stage Object Detection
        1992, -- 1904.05862 wav2vec: Unsupervised Pre-training for Speech Recognition
        2029, -- 1904.09730 An Energy and GPU-Computation Efficient Backbone Network for Real-Time Object De
        2091, -- 1905.05172 PIFu: Pixel-Aligned Implicit Function for High-Resolution Clothed Human Digitiza
        2098, -- 1905.05894 Online Normalization for Training Neural Networks
        2166, -- 1905.13305 Countering Noisy Labels By Learning From Auxiliary Clean Labels
        2273, -- 1906.07155 MMDetection: Open MMLab Detection Toolbox and Benchmark
        2344, -- 1907.06571 Adversarial Video Generation on Complex Datasets
        2368, -- 1907.10830 U-GAT-IT: Unsupervised Generative Attentional Networks with Adaptive Layer-Insta
        2469, -- 1908.11025 Deep Floor Plan Recognition Using a Multi-Task Network with Room-Boundary-Guided
        2613, -- 1909.13231 Test-Time Training with Self-Supervision for Generalization under Distribution S
        2653, -- 1910.04076 FisheyeDistanceNet: Self-Supervised Scale-Aware Distance Estimation using Monocu
        2666, -- 1910.05453 vq-wav2vec: Self-Supervised Learning of Discrete Speech Representations
        2688, -- 1910.07467 Root Mean Square Layer Normalization
        2849, -- 1911.10127 BlendedMVS: A Large-scale Dataset for Generalized Multi-view Stereo Networks
        2852, -- 1911.10375 Region Normalization for Image Inpainting
        2902, -- 1912.02424 Bridging the Gap Between Anchor-based and Anchor-free Detection via Adaptive Tra
        2960, -- 1912.11370 Big Transfer (BiT): General Visual Representation Learning
        3143, -- 2002.11102 On Feature Normalization and Data Augmentation
        3162, -- 2003.00295 Adaptive Federated Optimization
        3228, -- 2003.07845 PowerNorm: Rethinking Batch Normalization in Transformers
        3258, -- 2003.11666 Pipelined Backpropagation at Scale: Training Large Models without Batches
        3285, -- 2004.00452 PIFuHD: Multi-Level Pixel-Aligned Implicit Function for High-Resolution 3D Human
        3351, -- 2004.06468 Self6D: Self-Supervised Monocular 6D Object Pose Estimation
        3598, -- 2005.09561 Normalized Attention Without Probability Cage
        3709, -- 2006.07733 Bootstrap your own latent: A new approach to self-supervised Learning
        3717, -- 2006.08217 AdamP: Slowing Down the Slowdown for Momentum Optimizers on Scale-invariant Weig
        3764, -- 2006.11239 Denoising Diffusion Probabilistic Models
        3836, -- 2006.16856 A Chain Graph Interpretation of Real-World Neural Networks
        3925, -- 2007.11622 TinyTL: Reduce Activations, Not Trainable Parameters for Efficient On-Device Lea
        4238, -- 2010.00578 Understanding Self-supervised Learning with Dual Deep Networks
        4408, -- 2010.11594 Two-Stream Consensus Network for Weakly-Supervised Temporal Action Localization
        4415, -- 2010.11929 An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale
        4541, -- 2011.05670 FPGA: Fast Patch-Free Global Learning Framework for Fully End-to-End Hyperspectr
        4636, -- 2011.14503 End-to-End Video Instance Segmentation with Transformers
        4785, -- 2012.13375 Global Context Networks
        4905, -- 2101.06545 VideoClick: Video Object Segmentation with a Single Click
        4906, -- 2101.06560 Adversarial Attacks On Multi-Agent Communication
        4923, -- 2101.08692 Characterizing signal propagation to close the performance gap in unnormalized R
        4955, -- 2101.11605 Bottleneck Transformers for Visual Recognition
        4968, -- 2102.00850 On Scaling Contrastive Representations for Low-Resource Speech Recognition
        5022, -- 2102.06171 High-Performance Large-Scale Image Recognition Without Normalization
        5035, -- 2102.06867 CPP-Net: Context-aware Polygon Proposal Network for Nucleus Segmentation
        5088, -- 2102.12145 GDRNPP: A Geometry-guided and Fully Learning-based Object Pose Estimator
        5184, -- 2103.06583 Preprint: Norm Loss: An efficient yet effective regularization method for deep n
        5318, -- 2103.16302 Rethinking Spatial Dimensions of Vision Transformers
        5536, -- 2104.09648 Memory Efficient 3D U-Net with Reversible Mobile Inverted Bottlenecks for Brain
        5581, -- 2104.12533 Visformer: The Vision-friendly Transformer
        5589, -- 2104.12928 If your data distribution shifts, use self-learning
        5644, -- 2105.02201 PD-GAN: Probabilistic Diverse GAN for Image Inpainting
        5697, -- 2105.04714 Sample and Computation Redistribution for Efficient Face Detection
        5702, -- 2105.05233 Diffusion Models Beat GANs on Image Synthesis
        5732, -- 2105.07581 Vision Transformers are Robust Learners
        5817, -- 2105.14739 Controllable Person Image Synthesis with Spatially-Adaptive Warped Normalization
        5942, -- 2106.05237 Knowledge distillation: A good teacher is patient and consistent
        6012, -- 2106.08519 Global Rhythm Style Transfer Without Text Transcriptions
        6035, -- 2106.09681 XCiT: Cross-Covariance Image Transformers
        6164, -- 2107.00420 CBNet: A Composite Backbone Network Architecture for Object Detection
        6193, -- 2107.03006 Structured Denoising Diffusion Models in Discrete State-Spaces
        6237, -- 2107.06278 Per-Pixel Classification is Not All You Need for Semantic Segmentation
        6266, -- 2107.07933 Panoptic Segmentation of Satellite Image Time Series with Convolutional Temporal
        6353, -- 2108.01285 Toward Spatially Unbiased Generative Models
        6373, -- 2108.02938 ILVR: Conditioning Method for Denoising Diffusion Probabilistic Models
        6489, -- 2108.11801 Unsupervised domain adaptation for clinician pose estimation and instance segmen
        6631, -- 2109.06474 Space Time Recurrent Memory Network
        6749, -- 2109.14119 Stochastic Training is Not Necessary for Generalization
        6795, -- 2110.02034 Dropout Q-Functions for Doubly Efficient Reinforcement Learning
        6809, -- 2110.02711 DiffusionCLIP: Text-Guided Diffusion Models for Robust Image Manipulation
        6995, -- 2110.08791 Taming Visually Guided Sound Generation
        7012, -- 2110.10640 OSS-Net: Memory Efficient High Resolution Semantic Segmentation of 3D Medical Da
        7037, -- 2110.12130 RCNet: Reverse Feature Pyramid and Cross-scale Shift Network for Object Detectio
        7051, -- 2110.13100 Parameter Prediction for Unseen Deep Architectures
        7259, -- 2111.09883 Swin Transformer V2: Scaling Up Capacity and Resolution
        7281, -- 2111.11418 MetaFormer Is Actually What You Need for Vision
        7282, -- 2111.11429 Benchmarking Detection Transfer Learning with Vision Transformers
        7288, -- 2111.11828 Variance Reduction in Deep Learning: More Momentum is All You Need
        7337, -- 2111.14821 End-to-End Referring Video Object Segmentation with Multimodal Transformers
        7397, -- 2112.01799 Global Context with Discrete Diffusion in Vector Quantised Modelling for Image G
        7502, -- 2112.07804 Tackling the Generative Learning Trilemma with Denoising Diffusion GANs
        7546, -- 2112.09081 CrossLoc: Scalable Aerial Localization Assisted by Multimodal Synthetic Data
        7554, -- 2112.09290 PeopleSansPeople: A Synthetic Data Generator for Human-Centric Computer Vision
        7635, -- 2201.00308 DiffuseVAE: Efficient, Controllable and High-Fidelity Generation from Low-Dimens
        7673, -- 2201.03545 A ConvNet for the 2020s
        7825, -- 2202.00275 Architecture Matters in Continual Learning
        8497, -- 2203.16527 Exploring Plain Vision Transformer Backbones for Object Detection
        8524, -- 2204.00227 Perception Prioritized Training of Diffusion Models
        8617, -- 2204.03638 Long Video Generation with Time-Agnostic VQGAN and Time-Sensitive Transformer
        8644, -- 2204.04545 Self-Labeling Refinement for Robust Representation Learning with Bootstrap Your
        8695, -- 2204.06107 Open-World Instance Segmentation: Exploiting Pseudo Ground Truth From Learned Pa
        9012, -- 2205.06175 A Generalist Agent
        9072, -- 2205.09853 MCVD: Masked Conditional Video Diffusion for Prediction, Generation, and Interpo
        9076, -- 2205.09991 Planning with Diffusion for Flexible Behavior Synthesis
        9508, -- 2206.08343 Realistic One-shot Mesh-based Head Avatars
        9628, -- 2206.14098 RevBiFPN: The Fully Reversible Bidirectional Feature Pyramid Network
        9668, -- 2207.00391 A Theoretical Analysis of the Learning Dynamics under Class Imbalance
        9810, -- 2207.08082 CATRE: Iterative Point Clouds Alignment for Category-level Object Pose Refinemen
        9817, -- 2207.08518 HiFormer: Hierarchical Multi-scale Representations Using Transformers for Medica
        9821, -- 2207.08869 FLAIR: Federated Learning Annotated Image Repository
        9855, -- 2207.10333 Jointly Predicting Emotion, Age, and Country Using Pre-Trained Acoustic Embeddin
        9918, -- 2207.13353 One-Trimap Video Matting
        9959, -- 2208.01313 Unified Normalization for Accelerating and Stabilizing Transformers
        10026, -- 2208.05830 Speech Enhancement and Dereverberation with Diffusion-based Generative Models
        10138, -- 2208.12086 A Study on Broadcast Networks for Music Genre Classification
        10253, -- 2209.04836 Git Re-Basin: Merging Models modulo Permutation Symmetries
        10337, -- 2209.09002 MoVQ: Modulating Quantized Vectors for High-Fidelity Image Generation
        10548, -- 2210.01781 COPILOT: Human-Environment Collision Prediction and Localization from Egocentric
        10621, -- 2210.03403 TAN Without a Burn: Scaling Laws of DP-SGD
        10765, -- 2210.06640 Compute-Efficient Deep Learning: Algorithmic Trends and Opportunities
        10849, -- 2210.08823 Scaling & Shifting Your Features: A New Baseline for Efficient Model Tuning
        10932, -- 2210.11407 Similarity of Neural Architectures using Adversarial Attack Transferability
        11209, -- 2211.02048 Efficient Spatially Sparse Inference for Conditional GANs and Diffusion Models
        11364, -- 2211.08332 Versatile Diffusion: Text, Images and Variations All in One Diffusion Model
        11420, -- 2211.09808 Uni-Perceiver v2: A Generalist Model for Large-Scale Vision and Vision-Language
        11559, -- 2211.12870 ActMAD: Activation Matching to Align Distributions for Test-Time-Training
        11668, -- 2211.15657 Is Conditional Generative Modeling all you need for Decision-Making?
        11836, -- 2212.03246 MobileTL: On-device Transfer Learning with Inverted Residual Blocks
        11860, -- 2212.04114 Group Generalized Mean Pooling for Vision Transformer
        11904, -- 2212.05199 MAGVIT: Masked Generative Video Transformer
        11909, -- 2212.05262 Position Embedding Needs an Independent Layer Normalization
        11988, -- 2212.07784 RTMDet: An Empirical Study of Designing Real-Time Object Detectors
        12027, -- 2212.08641 GFPose: Learning 3D Human Pose Prior with Gradient Fields
        12236, -- 2212.13771 Exploring Vision Transformers as Diffusion Learners
        12283, -- 2301.00808 ConvNeXt V2: Co-designing and Scaling ConvNets with Masked Autoencoders
        12485, -- 2301.09515 StyleGAN-T: Unlocking the Power of GANs for Fast Large-Scale Text-to-Image Synth
        12606, -- 2301.12048 Making Reconstruction-based Method Great Again for Video Anomaly Detection
        12616, -- 2301.12195 BAFFLE: A Baseline of Backpropagation-Free Federated Learning
        12825, -- 2302.01877 AdaptDiffuser: Diffusion Models as Adaptive Self-evolving Planners
        12952, -- 2302.04215 A Vector Quantized Approach for Text to Speech Synthesis on Real-World Spontaneo
        13001, -- 2302.04973 Invariant Slot Attention: Object Discovery with Slot-Centric Reference Frames
        13068, -- 2302.06594 Geometric Clifford Algebra Networks
        13221, -- 2302.10429 FedSpeed: Larger Local Interval, Less Communication Round, and Higher Generaliza
        13293, -- 2302.12400 Towards Stable Test-Time Adaptation in Dynamic Wild World
        13534, -- 2303.03667 Run, Don't Walk: Chasing Higher FLOPS for Faster Neural Networks
        13636, -- 2303.05916 GECCO: Geometrically-Conditioned Point Diffusion Models
        13720, -- 2303.07347 TriDet: Temporal Action Detection with Relative Boundary Modeling
        14120, -- 2303.14389 MDTv2: Masked Diffusion Transformer is a Strong Image Synthesizer
        14207, -- 2303.15693 Large-scale pretraining on pathological images for fine-tuning of small patholog
        14533, -- 2304.03768 SparseFormer: Sparse Visual Recognition via Limited Latent Tokens
        14704, -- 2304.07060 DCFace: Synthetic Face Generation with Dual Condition Diffusion Model
        14722, -- 2304.07645 Magnitude Invariant Parametrizations Improve Hypernetwork Learning
        14793, -- 2304.09479 DiFaReli++: Diffusion Face Relighting with Consistent Cast Shadows
        14881, -- 2304.11267 Speed Is All You Need: On-Device Acceleration of Large Diffusion Models via GPU-
        15503, -- 2305.07648 A Critical View of Vision-Based Long-Term Dynamics Prediction Under Environment
        15680, -- 2305.10474 Preserve Your Own Correlation: A Noise Prior for Video Diffusion Models
        15779, -- 2305.11624 Efficient ConvBN Blocks for Transfer Learning and Beyond
        15819, -- 2305.12073 GELU Activation Function in Deep Learning: A Comprehensive Mathematical Analysis
        16288, -- 2305.15912 Neural Characteristic Activation Analysis and Geometric Parameterization for ReL
        16321, -- 2305.16312 UMat: Uncertainty-Aware Single Image High Resolution Material Capture
        16671, -- 2305.19923 MetaDiffuser: Diffusion Model as Conditional Planner for Offline Meta-RL
        16885, -- 2306.01776 From Zero to Turbulence: Generative Modeling for 3D Flow Simulation
        17041, -- 2306.03536 On Pitfalls of Test-Time Adaptation
        17221, -- 2306.05879 FedWon: Triumphing Multi-domain Federated Learning Without Normalization
        17336, -- 2306.07473 3D molecule generation by denoising voxel grids
        17356, -- 2306.07744 Contrastive Learning-Based Audio to Lyrics Alignment for Multiple Languages
        17365, -- 2306.07881 Viewset Diffusion: (0-)Image-Conditioned 3D Generative Models from 2D Data
        17406, -- 2306.08276 TryOnDiffusion: A Tale of Two UNets
        17519, -- 2306.09595 Structured Cooperative Learning with Graphical Model Priors
        17546, -- 2306.10001 Group Orthogonalization Regularization For Vision Models Adaptation and Robustne
        17686, -- 2306.12873 FuXi: A cascade machine learning forecasting system for 15-day global weather fo
        17864, -- 2306.16645 Deep Equilibrium Multimodal Fusion
        17887, -- 2306.16993 Weight Compander: A Simple Weight Reparameterization for Regularization
        18250, -- 2307.07487 DreamTeacher: Pretraining Image Backbones with Deep Generative Models
        18319, -- 2307.08500 Cumulative Spatial Knowledge Distillation for Vision Transformers
        18325, -- 2307.08621 Retentive Network: A Successor to Transformer for Large Language Models
        18345, -- 2307.08927 Multi-Stage Cable Routing through Hierarchical Imitation Learning
        18633, -- 2307.13813 How to Scale Your EMA
        18760, -- 2307.15988 RGB-D-Fusion: Image Conditioned Depth Diffusion of Humanoid Subjects
        19132, -- 2308.05732 PDE-Refiner: Achieving Accurate Long Rollouts with Neural PDE Solvers
        19418, -- 2308.09565 Understanding the Role of Layer Normalization in Label-Skewed Federated Learning
        19813, -- 2308.13783 Generalized Lightness Adaptation with Channel Selective Normalization
        19951, -- 2308.16215 Deep Video Codec Control for Vision Models
        20077, -- 2309.01574 Object-Size-Driven Design of Convolutional Neural Networks: Virtual Axle Detecti
        20226, -- 2309.04422 Video Task Decathlon: Unifying Image and Video Tasks in Autonomous Driving
        20382, -- 2309.07200 Latent Representation and Simulation of Markov Processes via Time-Lagged Informa
        20804, -- 2309.13041 Robotic Offline RL from Internet Videos via Value-Function Pre-Training
        21067, -- 2309.17031 Scalable Multi-Temporal Remote Sensing Change Data Generation via Simulating Sto
        21145, -- 2310.00311 Efficient Planning with Latent Diffusion
        21760, -- 2310.07138 Denoising Task Routing for Diffusion Models
        21789, -- 2310.07402 NuTime: Numerically Multi-Scaled Embedding for Large-Scale Time-Series Pretraini
        21934, -- 2310.08855 Overcoming Recency Bias of Normalization Statistics in Continual Learning: Balan
        22127, -- 2310.11453 BitNet: Scaling 1-bit Transformers for Large Language Models
        22567, -- 2310.16825 CommonCanvas: An Open Diffusion Model Trained with Creative-Commons Images
        23666, -- 2311.13443 Guided Flows for Generative Modeling and Decision Making
        23843, -- 2311.16241 SemiVL: Semi-Supervised Semantic Segmentation with Vision-Language Guidance
        23983, -- 2311.17901 SODA: Bottleneck Diffusion Models for Representation Learning
        24017, -- 2311.18257 Diffusion Models Without Attention
        24060, -- 2311.18829 MicroCinema: A Divide-and-Conquer Approach for Text-to-Video Generation
        24233, -- 2312.02139 DiffiT: Diffusion Vision Transformers for Image Generation
        24352, -- 2312.03511 Kandinsky 3.0 Technical Report
        24443, -- 2312.04501 Graph Metanetworks for Processing Diverse Neural Architectures
        24678, -- 2312.07381 ScribblePrompt: Fast and Flexible Interactive Segmentation for Any Biomedical Im
        24929, -- 2312.11420 Tuning LayerNorm in Attention: Towards Efficient Multi-Modal LLM Finetuning
        25854, -- 2401.08328 Un-Mixing Test-Time Normalization Statistics: Combatting Label Temporal Correlat
        26246, -- 2401.13627 Scaling Up to Excellence: Practicing Model Scaling for Photo-Realistic Image Res
        26517, -- 2401.17593 Head and Neck Tumor Segmentation from [18F]F-FDG PET/CT Images Based on 3D Diffu
        26536, -- 2401.17948 HyperZ$\cdot$Z$\cdot$W Operator Connects Slow-Fast Networks for Full Context Int
        26812, -- 2402.03040 InteractiveVideo: User-Centric Controllable Video Generation with Synergistic Mu
        26867, -- 2402.03570 Diffusion World Model: Future Modeling Beyond Step-by-Step Rollout for Offline R
        26961, -- 2402.04553 Curvature-Informed SGD via General Purpose Lie-Group Preconditioners
        27751, -- 2402.13929 SDXL-Lightning: Progressive Adversarial Diffusion Distillation
        27885, -- 2402.15170 The Surprising Effectiveness of Skip-Tuning in Diffusion Sampling
        28217, -- 2402.19481 DistriFusion: Distributed Parallel Inference for High-Resolution Diffusion Model
        28465, -- 2403.03542 DPOT: Auto-Regressive Denoising Operator Transformer for Large-Scale PDE Pre-Tra
        28837, -- 2403.09192 PYRA: Parallel Yielding Re-Activation for Training-Inference Efficient Task Adap
        28990, -- 2403.11261 A Lie Group Approach to Riemannian Batch Normalization
        29101, -- 2403.12553 Pretraining Codomain Attention Neural Operators for Solving Multiphysics PDEs
        29113, -- 2403.12706 AnimateDiff-Lightning: Cross-Model Diffusion Distillation
        29252, -- 2403.14404 Physics-Informed Diffusion Models
        30017, -- 2404.04478 Diffusion-RWKV: Scaling RWKV-Like Architectures for Diffusion Models
        30106, -- 2404.05892 Eagle and Finch: RWKV with Matrix-Valued States and Dynamic Recurrence
        30309, -- 2404.08801 Megalodon: Efficient LLM Pretraining and Inference with Unlimited Context Length
        30547, -- 2404.12406 Lowering PyTorch's Memory Consumption for Selective Differentiation
        30896, -- 2404.18873 OpenStreetView-5M: The Many Roads to Global Visual Geolocation
        31150, -- 2405.05254 You Only Cache Once: Decoder-Decoder Architectures for Language Models
        31201, -- 2405.06640 Linearizing Large Language Models
        31265, -- 2405.07992 MambaOut: Do We Really Need Mamba for Vision?
        31340, -- 2405.09874 Dual3D: Efficient and Consistent Text-to-3D Generation with Dual-mode Multi-view
        31419, -- 2405.11582 SLAB: Efficient Transformers with Simplified Linear Attention and Progressive Re
        31455, -- 2405.12399 Diffusion for World Modeling: Visual Details Matter in Atari
        31588, -- 2405.14477 LiteVAE: Lightweight and Efficient Variational Autoencoders for Latent Diffusion
        32295, -- 2406.02347 Flash Diffusion: Accelerating Any Conditional Diffusion Model for Few Steps Imag
        32458, -- 2406.04330 Parameter-Inverted Image Pyramid Networks
        32487, -- 2406.04595 Pitch-Aware RNN-T for Mandarin Chinese Mispronunciation Detection and Diagnosis
        32523, -- 2406.05131 A Semi-Self-Supervised Approach for Dense-Pattern Video Object Segmentation
        33287, -- 2406.12837 LayerMerge: Neural Network Depth Compression through Layer Pruning and Merging
        33554, -- 2406.16260 Video-Infinity: Distributed Long Video Generation
        34102, -- 2407.03197 DyFADet: Dynamic Feature Aggregation for Temporal Action Detection
        34397, -- 2407.07111 Diffusion Model-Based Video Editing: A Survey
        34784, -- 2407.12077 GoldFinch: High Performance RWKV/Transformer Hybrid with Linear Pre-Fill and Ext
        35040, -- 2407.15420 Local All-Pair Correspondence for Point Tracking
        35086, -- 2407.16142 Diffusion Models as Optimizers for Efficient Planning in Offline RL
        35332, -- 2407.20635 Autonomous Improvement of Instruction Following Skills via Foundation Models
        35383, -- 2407.21686 Expressive Whole-Body 3D Gaussian Avatar
        35745, -- 2408.06070 ControlNeXt: Powerful and Efficient Control for Image and Video Generation
        35770, -- 2408.06481 UniT: Data Efficient Tactile Representation with Generalization to   Unseen Obje
        36408, -- 2408.17081 Stochastic Layer-Wise Shuffle: A Good Practice to Improve Vision Mamba Training
        36570, -- 2409.02529 Sample what you cant compress
        36951, -- 2409.10594 Kolmogorov-Arnold Transformer
        37281, -- 2409.16211 MaskBit: Embedding-free Image Generation via Bit Tokens
        37931, -- 2410.04081 Epsilon-VAE: Denoising as Visual Decoding
        38014, -- 2410.05258 Differential Transformer
        38420, -- 2410.10254 LoLCATs: On Low-Rank Linearizing of Large Language Models
        38746, -- 2410.13821 Artificial Kuramoto Oscillatory Neurons
        39705, -- 2411.04165 Bio-xLSTM: Generative modeling, representation and in-context learning of biolog
        40081, -- 2411.10948 Towards Accurate and Efficient Sub-8-Bit Integer Training
        40292, -- 2411.14762 Efficient Long Video Tokenization via Coordinate-based Patch Reconstruction
        40415, -- 2411.16199 VIRES: Video Instance Repainting via Sketch and Text Guided Generation
        40516, -- 2411.17459 WF-VAE: Enhancing Video VAE by Wavelet-Driven Energy Flow for Latent Video Diffu
        40606, -- 2411.18562 DexHandDiff: Interaction-aware Diffusion Planning for Adaptive Dexterous Manipul
        40875, -- 2412.02030 NitroFusion: High-Fidelity Single-Step Diffusion through Dynamic Adversarial Tra
        41687, -- 2412.11998 SAMIC: Segment Anything with In-Context Spatial Prompt Engineering
        41826, -- 2412.13795 Mix-LN: Unleashing the Power of Deeper Layers by Combining Pre-LN and Post-LN
        41997, -- 2412.16146 Mamba2D: A Natively Multi-Dimensional State-Space Model for Vision Tasks
        42815, -- 2501.07783 Parameter-Inverted Image Pyramid Networks for Visual Perception and Multimodal U
        42986, -- 2501.10807 FlashSR: One-step Versatile Audio Super-resolution via Diffusion Distillation
        43368, -- 2501.17486 DINT Transformer
        43726, -- 2502.03654 Gompertz Linear Units: Leveraging Asymmetry for Enhanced Learning Dynamics
        43860, -- 2502.05282 Homeomorphism Prior for False Positive and Negative Problem in Medical   Image D
        43887, -- 2502.05795 The Curse of Depth in Large Language Models
        44770, -- 2502.15612 LaTIM: Measuring Latent Token-to-Token Interactions in Mamba Models
        44854, -- 2502.16654 VPNeXt -- Rethinking Dense Decoding for Plain Vision Transformer
        45188, -- 2502.20396 Sim-to-Real Reinforcement Learning for Vision-Based Dexterous Manipulation on Hu
        46072, -- 2503.10622 Transformers without Normalization
        48520, -- 2505.05023 Split Matching for Inductive Zero-shot Semantic Segmentation
        48677, -- 2505.08175 Fast Text-to-Audio Generation with Adversarial Post-Training
        49186, -- 2505.14511 ReservoirTTA: Prolonged Test-time Adaptation for Evolving and Recurring Domains
        50049, -- 2505.22865 BinauralFlow: A Causal and Streamable Approach for High-Quality Binaural Speech
        50191, -- 2505.24025 DINO-R1: Incentivizing Reasoning Capability in Vision Foundation Models
        50642, -- 2506.05294 A Smooth Sea Never Made a Skilled $\texttt{SAILOR}$: Robust Imitation via Learni
        50789, -- 2506.07863 VIVAT: Virtuous Improving VAE Training through Artifact Mitigation
        51066, -- 2506.11305 Don't Pay Attention
        51516, -- 2506.21474 Logios : An open source Greek Polytonic Optical Character Recognition system
        51547, -- 2506.22049 GPAS: Accelerating Convergence of LLM Pretraining via   Gradient-Preserving Acti
        51767, -- 2507.06204 Differential Mamba
        52554, -- 2508.20085 HERMES: Human-to-Robot Embodied Learning from Multi-Source Motion Data   for Mob
        53225, -- 2510.04800 Hybrid Architectures for Language Models: Systematic Analysis and Design   Insig
        53266, -- 2510.05592 In-the-Flow Agentic System Optimization for Effective Planning and Tool   Use
        54195, -- 2511.11238 Virtual Width Networks
        54717, -- 2512.10938 Stronger Normalization-Free Transformers
        54771, -- 2512.12751 GenieDrive: Towards Physics-Aware Driving World Model with 4D Occupancy Guided V
        54790, -- 2512.08400 Towards Visual Re-Identification of Fish using Fine-Grained Classification for E
        55145, -- 2601.00423 E-GRPO: High Entropy Steps Drive Effective Reinforcement Learning for Flow Model
        55253, -- 2601.06463 Gecko: An Efficient Neural Architecture Inherently Processing Sequences with Arb
        55748, -- 2602.01212 SimpleGPT: Improving GPT via A Simple Normalization Strategy
        57353, -- 2604.07966 Lighting-grounded Video Generation with Renderer-based Agent Reasoning
        57358, -- 2601.20524 AnomalyVFM -- Transforming Vision Foundation Models into Zero-Shot Anomaly Detec
        58203, -- 2604.12918 Radar-Camera BEV Multi-Task Learning with Cross-Task Attention Bridge for Joint
        58320, -- 2604.10210 A3-FPN: Asymptotic Content-Aware Pyramid Attention Network for Dense Visual Pred
        58577, -- 2604.02795 Rubrics to Tokens: Bridging Response-level Rubrics and Token-level Rewards in In
        58802, -- 2603.27344 TerraSeg: Self-Supervised Ground Segmentation for Any LiDAR
        60632, -- 2602.14338 Train Less, Learn More: Adaptive Efficient Rollout Optimization for Group-Based
        60912, -- 2602.09617 AnyTouch 2: General Optical Tactile Representation Learning For Dynamic Tactile
        61230, -- 2602.04770 Generative Modeling via Drifting
        61339, -- 2602.03452 Beyond Variance: Prompt-Efficient RLVR via Rare-Event Amplification and Bidirect
        61778, -- 2601.22095 GeoNorm: Unify Pre-Norm and Post-Norm with Geodesic Optimization
        61798, -- 2601.21866 MoHETS: Long-term Time Series Forecasting with Mixture-of-Heterogeneous-Experts
        63289, -- 2512.22027 Patch-Discontinuity Mining for Generalized Deepfake Detection
        63755, -- 2512.12387 Anchoring Values in Temporal and Group Dimensions for Flow Matching Model Alignm
        65870, -- 2510.22257 LUNA: Efficient and Topology-Agnostic Foundation Model for EEG Signal   Analysis
        67711, -- 2509.22063 High-Quality Sound Separation Across Diverse Categories via   Visually-Guided Ge
        70710, -- 2507.19595 Efficient Attention Mechanisms for Large Language Models: A Survey
        71449, -- 2507.03393 Masked Temporal Interpolation Diffusion for Procedure Planning in   Instructiona
        71779, -- 2506.18640 Federated Loss Exploration for Improved Convergence on Non-IID Data
        72473, -- 2506.00660 Differential privacy for medical deep learning: methods, tradeoffs, and deployme
        72680, -- 2505.20704 Beyond Entropy: Region Confidence Proxy for Wild Test-Time Adaptation
        73119, -- 2505.06537 ProFashion: Prototype-guided Fashion Video Generation with Multiple Reference Im
        73416, -- 2504.15371 Event2Vec: Processing Neuromorphic Events Directly by Representations in Vector
        76037, -- 2410.14729 Is Less More? Exploring Token Condensation as Training-free Test-time   Adaptati
        76259, -- 2409.19078 Differential privacy enables fair and accurate AI-based analysis of speech disor
        77198, -- 2405.16141 AIGB: Generative Auto-bidding via Conditional Diffusion Modeling
        77616, -- 2309.08684 Music Source Separation Based on a Lightweight Deep Learning Framework (DTTNET:
        78415, -- 2310.03986 Robust Multimodal Learning with Missing Modalities via   Parameter-Efficient Ada
        79170, -- 2304.01171 Revisiting Context Aggregation for Image Matting
        79190, -- 2303.16102 KeyMatchNet: Zero-Shot Pose Estimation in 3D Point Clouds by Generalized Keypoin
        79219, -- 2303.11797 CAT-Seg: Cost Aggregation for Open-Vocabulary Semantic Segmentation
        79275, -- 2303.04137 Diffusion Policy: Visuomotor Policy Learning via Action Diffusion
        79385, -- 2302.01622 Private, fair and accurate: Training large-scale, privacy-preserving AI models i
        79488, -- 2212.08208 Location-aware Adaptive Normalization: A Deep Learning Approach For   Wildfire D
        79559, -- 2211.10515 Curiosity in Hindsight: Intrinsic Exploration in Stochastic Environments
        79644, -- 2210.11672 Stochastic Adaptive Activation Function
        79846, -- 2207.06343 TCT: Convexifying Federated Learning using Bootstrapped Neural Tangent Kernels
        79892, -- 2206.08332 BYOL-Explore: Exploration by Bootstrapped Prediction
        80203, -- 2202.07123 Rethinking Network Design and Local Geometry in Point Cloud: A Simple   Residual
        80330, -- 2112.04491 Improving Image Restoration by Revisiting Global Information Aggregation
        80558, -- 2108.10629 Improving Generalization of Batch Whitening by Convolutional Unit Optimization
        80639, -- 2106.14448 R-Drop: Regularized Dropout for Neural Networks
        80736, -- 2105.02716 Noether's Learning Dynamics: Role of Symmetry Breaking in Neural Networks
        80739, -- 2105.01595 Self-Improving Semantic Perception for Indoor Localisation
        80747, -- 2104.14374 Thermal Infrared Image Colorization for Nighttime Driving Scenes with Top-Down G
        80885, -- 2011.10798 A Better and Faster End-to-End Model for Streaming ASR
        80913, -- 2011.13183 TinaFace: Strong but Simple Baseline for Face Detection
        81049, -- 2010.12455 Primal-Dual Mesh Convolutional Neural Networks
        81221, -- 2007.05059 Learning Representations that Support Extrapolation
        81260, -- 2006.08656 Multiscale Deep Equilibrium Models
        81558, -- 1910.10261 QuartzNet: Deep Automatic Speech Recognition with 1D Time-Channel   Separable Co
        82039, -- 1804.07612 Revisiting Small Batch Training for Deep Neural Networks
        82879, -- 2605.06200 A^2TGPO: Agentic Turn-Group Policy Optimization with Adaptive Turn-level Clippin
        82939, -- 2605.06628 LiVeAction: a Lightweight, Versatile, and Asymmetric Neural Codec Design for Rea
        83514, -- 2605.19376 Generative Recursive Reasoning
        83716, -- 2111.15640 Diffusion Autoencoders: Toward a Meaningful and Decodable Representation
        85012, -- 2603.20782 MEMO: Human-like Crisp Edge Detection Using Masked Edge Prediction
        86347, -- 2510.06046 GLVD: Guided Learned Vertex Descent
        86643, -- 2509.13341 Imagined Autocurricula
        86925, -- 2506.04401 Normalize Filters! Classical Wisdom for Deep Vision
        86970, -- 2510.12238 A Gradient Guided Diffusion Framework for Chance Constrained Programming
        87216, -- 2505.19217 The Overthinker's DIET: Cutting Token Calories with DIfficulty-AwarE Training
        87336, -- 2509.15328 Kuramoto Orientation Diffusion Models
        87357, -- 2506.04641 Text-Aware Real-World Image Super-Resolution via Diffusion Model with Joint Segm
        87567, -- 2507.18569 Adversarial Distribution Matching for Diffusion Distillation Towards Efficient I
        87624, -- 2506.22908 Attention to the Burstiness in Visual Prompt Tuning!
        87630, -- 2503.16726 EDiT: Efficient Diffusion Transformers with Linear Compressed Attention
        87705, -- 2503.13217 Dense Policy: Bidirectional Autoregressive Learning of Actions
        88012, -- 2412.14371 SEREP: Semantic Facial Expression Representation for Robust In-the-Wild Capture
        88371, -- 2506.23516 FedWSQ: Efficient Federated Learning with Weight Standardization and Distributio
        88711, -- 2507.09031 Confounder-Free Continual Learning via Recursive Feature Normalization
        89122, -- 2410.01706 Sable: a Performant, Efficient and Scalable Sequence Model for MARL
        89160, -- 2505.21877 Hybrid Batch Normalisation: Resolving the Dilemma of Batch Normalisation in Fede
        89174, -- 2504.19496 DISCO: learning to DISCover an evolution Operator for multi-physics-agnostic pre
        89318, -- 2505.00685 On the Importance of Gaussianizing Representations
        89826, -- 2506.00432 Channel Normalization for Time Series Channel Identification
        89869, -- 2502.10691 Controlling Neural Collapse Enhances Out-of-Distribution Detection and Transfer
        90166, -- 2501.13134 UniRestore: Unified Perceptual and Task-Oriented Image Restoration Model Using D
        90374, -- 2505.02071 Hierarchical Compact Clustering Attention (COCA) for Unsupervised Object-Centric
        90616, -- 2504.00996 TurboFill: Adapting Few-step Text-to-image Model for Fast Image Inpainting
        90723, -- 2412.03752 Beyond Local Sharpness: Communication-Efficient Global Sharpness-aware Minimizat
        90852, -- 2411.15247 Reward Fine-Tuning Two-Step Diffusion Models via Learning Differentiable Latent-
        91672, -- 2502.21143 Variational Bayesian Pseudo-Coreset
        91872, -- 2311.17434 GSE: Group-wise Sparse and Explainable Adversarial Attacks
        92191, -- 2408.01536 Active Learning for Neural PDE Solvers
        92235, -- 2502.12976 Does Training with Synthetic Data Truly Protect Privacy?
        92393, -- 2503.02618 ZAPBench: A Benchmark for Whole-Brain Activity Prediction in Zebrafish
        92751, -- 2604.17986 Latent Fourier Transform
        94068, -- 2509.26337 FedMuon: Federated Learning with Bias-corrected LMO-based Optimization
        94420, -- 2602.08462 TriC-Motion: Tri-Domain Causal Modeling Grounded Text-to-Motion Generation
        94442, -- 2602.15776 GlobeDiff: State Diffusion Process for Partial Observability in Multi-Agent Syst
        95378, -- 2510.14612 Proprioceptive Image: An Image Representation of Proprioceptive Data from Quadru
        98212, -- 2606.12364 On Subquadratic Architectures: From Applications to Principles
        98350, -- 2404.16622 DAVE -- A Detect-and-Verify Paradigm for Low-Shot Counting
        98645, -- 2405.11770 Learning Spatial Similarity Distribution for Few-shot Object Counting
        98979, -- 2606.22749 RaysUp: Ultra-light Universal Feature Upsampling via Geometry-Aware Ray Represen
        99791, -- 2604.14669 Zeroth-Order Optimization at the Edge of Stability
        100435, -- 2512.08280 Model-Based Diffusion Sampling for Predictive Control in Offline Decision Making
        100578, -- 2605.15207 TeamTR: Trust-Region Fine-Tuning for Multi-Agent LLM Coordination
        100912, -- 2602.12390 Rational Neural Networks have Expressivity Advantages
        101355, -- 2604.16243 Find, Fix, Reason: Context Repair for Video Reasoning
        101594, -- 2606.03260 EqGINO: Equivariant Geometry-Informed Fourier Neural Operators for 3D PDEs
        101659, -- 2606.07950 The Easy, the Hard, and the Learnable: Confidence and Difficulty-Adaptive Policy
        101904, -- 2605.27541 SparseOpt: Addressing Normalization-induced Gradient Skew in Sparse Training
        102076, -- 2606.01908 Private and Stable Test-time Adaptation with Differential Privacy
        102446, -- 2602.21743 Enhancing Multi-Modal LLMs Reasoning via Difficulty-Aware Group Normalization
        103178, -- 2405.11597 Language Reconstruction with Brain Predictive Coding from fMRI Data
        103657, -- 2606.06058 MDP-GRPO: Stabilized Group Relative Policy Optimization for Multi-Constraint Ins
        103910, -- 1905.02693 3D Packing for Self-Supervised Monocular Depth Estimation
        104156, -- 2105.04668 HuMoR: 3D Human Motion Model for Robust Pose Estimation
        104190, -- 2211.12497 MagicPony: Learning Articulated 3D Animals in the Wild
        104257, -- 2105.06086 HINet: Half Instance Normalization Network for Image Restoration
        104340, -- 2006.09965 High-Fidelity Generative Image Compression
        104366, -- 2302.08899 QARV: Quantization-Aware ResNet VAE for Lossy Image Compression
        106927, -- 2507.02227 PhysicsCorrect: A Training-Free Approach for Stable Neural PDE Simulations
        107099, -- 2511.09100 FedPM: Federated Learning Using Second-order Optimization with Preconditioned Mi
        107610, -- 2506.11616 Wi-CBR: Salient-aware Adaptive WiFi Sensing for Cross-domain Behavior Recognitio
        108009, -- 2406.01987 Tackling Dual-stage Missing Modalities in Brain Tumor Segmentation via Robust Mo
        108024, -- 2601.12389 NADIR: Differential Attention Flow for Non-Autoregressive Transliteration in Ind
        108189, -- 2512.13014 JoDiffusion: Jointly Diffusing Image with Pixel-Level Annotations for Semantic S
        109202, -- 2109.15053 Fine-tuning wav2vec2 for speaker recognition
        109475, -- 2310.19583 GC-MVSNet: Multi-View, Multi-Scale, Geometrically-Consistent Multi-View Stereo
        109886, -- 2501.15722 INRet: A General Framework for Accurate Retrieval of INRs for Shapes
        110420, -- 2502.16565 The Hidden Strength of Disagreement: Unraveling the Consensus-Diversity Tradeoff
        111384, -- 2507.20926 End-to-End DOA-Guided Speech Extraction in Noisy Multi-Talker Scenarios
        112451, -- 2409.17221 Walker: Self-supervised Multiple Object Tracking by Walking on Temporal Object A
        112881, -- 2407.18821 Deep Companion Learning: Enhancing Generalization Through Historical Consistency
        112972, -- 2312.07051 Mask as Supervision: Leveraging Unified Mask Information for Unsupervised 3D Pos
        113127, -- 2211.13220 TetraDiffusion: Tetrahedral Diffusion Models for 3D Shape Generation
        113423, -- 2409.07808 FedHide: Federated Learning by Hiding in the Neighbors
        113483, -- 2407.15739 Diffusion for Out-of-Distribution Detection on Road Scenes and Beyond
        114255, -- 2605.04470 CRAFT: Counterfactual-to-Interactive Reinforcement Fine-Tuning for Driving Polic
        115067, -- 2407.05703 LGRNet: Local-Global Reciprocal Network for Uterine Fibroid Segmentation in Ultr
        115252, -- 2403.10858 RetMIL: Retentive Multiple Instance Learning for Histopathological Whole Slide I
        115368, -- 2409.18628 Towards Integrating Epistemic Uncertainty Estimation into the Radiotherapy Workf
        115593, -- 2402.17275 One-Shot Structure-Aware Stylized Image Synthesis
        115768, -- 2405.07933 Authentic Hand Avatar from a Phone Scan via Universal Hand Model
        115779, -- 2212.03185 Rethinking the Objectives of Vector-Quantized Tokenizers for Image Synthesis
        115795, -- 2404.10966 Domain-Specific Block Selection and Paired-View Pseudo-Labeling for Online Test-
        115887, -- 2312.06358 Intraoperative 2D/3D Image Registration via Differentiable X-ray Rendering
        116019, -- 2303.16198 Multi-modal Learning for Geospatial Vegetation Forecasting
        116090, -- 2312.11598 SkillDiffuser: Interpretable Hierarchical Planning via Skill Abstractions in Dif
        116121, -- 2403.08019 MRC-Net: 6-DoF Pose Estimation with MultiScale Residual Correlation
        116166, -- 2404.13103 ToNNO: Tomographic Reconstruction of a Neural Network's Output for Weakly Superv
        116376, -- 2403.00567 Flatten Long-Range Loss Landscapes for Cross-Domain Few-Shot Learning
        116694, -- 2404.00521 CHAIN: Enhancing Generalization in Data-Efficient GANs via lipsCHitz continuity
        116751, -- 2403.01753 Training-Free Pretrained Model Merging
        116777, -- 2404.02889 Steganographic Passport: An Owner and User Verifiable Credential for Deep Model
        116783, -- 2401.04928 Relaxed Contrastive Learning for Federated Learning
        116826, -- 2404.12383 G-HOP: Generative Hand-Object Prior for Interaction Reconstruction and Grasp Syn
        116835, -- 2403.17004 SD-DiT: Unleashing the Power of Self-supervised Discrimination in Diffusion Tran
        117020, -- 2402.17210 Purified and Unified Steganographic Network
        117023, -- 2311.14402 TEA: Test-time Energy Adaptation
        117069, -- 2405.17876 Decentralized Directed Collaboration for Personalized Federated Learning
        117884, -- 2603.16016 FlatLands: Generative Floormap Completion From a Single Egocentric View
        118159, -- 2606.28142 MixTTA: Low-Rank Cross-Channel Mixing for Reliable Test-Time Adaptation
        118331, -- 2608.03323 PolyLayout: Multi-room Manhattan Layout Estimation
        118452, -- 2607.00987 AVSR-Diff: Scale-Agnostic Diffusion Priors for Temporally Consistent Arbitrary-S
        119809, -- 2303.08096 MELON: NeRF with Unposed Images in SO(3)
        120474, -- 2412.06243 U-Know-DiffPAN: An Uncertainty-aware Knowledge Distillation Diffusion Framework
        120476, -- 2507.23569 Gaussian Splatting Feature Fields for (Privacy-Preserving) Visual Localization
        122775, -- 2605.16817 Adaptive Fused Prior Transfer for Controllable Generative Image Compression
        124231, -- 2610.11376 CRISP: Fixing Flying Pixels in Latent LiDAR Generation via Diffusion Decoding
        125216, -- 2609.34990 MaPP: A Unified Marginalized Posterior-Predictive Framework for Data-Efficient R
        126822, -- external RAHF: Reward-Amplified Human Feedback for Closed-Loop Policy Fine-Tuning
        126939, -- 2511.21075 Aligning LLMs with Biomedical Knowledge using Balanced Fine-Tuning
        127388, -- 2606.05800 SALT: When More Rollouts Don’t Help in Group-Based Policy Optimization and How t
        127862, -- 2606.02339 Entropy Minimization without Model Collapse: Mitigating Prediction Bias in Medic
        129021, -- external Grounding Agent Reasoning with Structured Process Supervision for Multi-turn Rei
        130673, -- 2605.30833 Your Teacher Can’t Help You Here: Combating Supervision Fidelity Decay in On-Pol
        132112  -- 2611.01729 ODE Policy: Robot Learning via Action Dynamics, Not Actions
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
        622, -- 1703.06868 Arbitrary Style Transfer in Real-time with Adaptive Instance Normalization
        716, -- 1705.06830 Exploring the structure of a real-time, arbitrary neural artistic stylization ne
        734, -- 1705.10041 Towards Metamerism via Foveated Style Transfer
        1404, -- 1807.09441 Two at Once: Enhancing Learning and Generalization Capacities via IBN-Net
        1722, -- 1812.09912 Image-to-Image Translation via Group-wise Deep Whitening-and-Coloring Transforma
        1991, -- 1904.05742 One-shot Voice Conversion by Separating Speaker and Content Representations with
        2368, -- 1907.10830 U-GAT-IT: Unsupervised Generative Attentional Networks with Adaptive Layer-Insta
        2680, -- 1910.06827 Learning Generalisable Omni-Scale Representations for Person Re-Identification
        3143, -- 2002.11102 On Feature Normalization and Data Augmentation
        3244, -- 2003.10685 Deep Line Art Video Colorization with a Few References
        4452, -- 2010.14022 ByteCover: Cover Song Identification via Multi-Loss Training
        4500, -- 2011.02242 BGGAN: Bokeh-Glass Generative Adversarial Network for Rendering Realistic Bokeh
        5070, -- 2102.10271 Meta-Learning Dynamics Forecasting Using Task Inference
        5189, -- 2103.06879 CoMoGAN: continuous model-guided image-to-image translation
        11272, -- 2211.04700 Noise Self-Regression: A New Learning Paradigm to Enhance Low-Light Images Witho
        11835, -- 2212.03241 PØDA: Prompt-driven Zero-shot Domain Adaptation
        12056, -- 2212.09247 ColoristaNet for Photorealistic Video Style Transfer
        20767, -- 2309.12792 DurIAN-E: Duration Informed Attention Network For Expressive Text-to-Speech Synt
        24786, -- 2312.09008 Style Injection in Diffusion: A Training-free Approach for Adapting Large-scale
        25974, -- 2401.09742 Image Translation as Diffusion Visual Programmers
        27066, -- 2402.05830 Sparse-VQ Transformer: An FFN-Free Framework with Vector Quantization for Enhanc
        37609, -- 2410.00900 OSSA: Unsupervised One-Shot Style Adaptation
        37641, -- 2410.01366 Harnessing the Latent Diffusion Model for Training-Free Image Style Transfer
        38694, -- 2410.13288 DurIAN-E 2: Duration Informed Attention Network with Adaptive Variational Autoen
        41386, -- 2412.08503 StyleStudio: Text-Driven Style Transfer with Selective Control of Style Elements
        45779, -- 2503.07307 AttenST: A Training-Free Attention-Driven Style Transfer Framework with Pre-Trai
        58203, -- 2604.12918 Radar-Camera BEV Multi-Task Learning with Cross-Task Attention Bridge for Joint
        63722, -- 2512.12963 SCAdapter: Content-Style Disentanglement for Diffusion Style Transfer
        63783, -- 2512.11763 Reducing Domain Gap with Diffusion-Based Domain Adaptation for Cell Counting
        79200, -- 2303.14613 GestureDiffuCLIP: Gesture Diffusion Model with CLIP Latents
        81175, -- 2008.04776 DTVNet+: A High-Resolution Scenic Dataset for Dynamic Time-lapse Video   Generat
        82365, -- 1607.08022 Instance Normalization: The Missing Ingredient for Fast Stylization
        84005, -- 2504.12606 Robo-SGG: Exploiting Layout-Oriented Normalization and Restitution Can Improve R
        85663, -- 2605.02772 Linearizing Vision Transformer with Test-Time Training
        93552, -- 2509.23597 Characteristic Root Analysis and Regularization for Linear Time Series Forecasti
        95299, -- external UM3D: Towards a Unified Multimodal 3D Shape Generation Model
        104257, -- 2105.06086 HINet: Half Instance Normalization Network for Image Restoration
        112991, -- 2407.04245 Every Pixel Has its Moments: Ultra-High-Resolution Unpaired Image-to-Image Trans
        113400, -- external Rethinking Normalization Layers for Domain Generalizable Person Re-identificatio
        119878, -- external LLM-driven Multimodal and Multi-Identity Listening Head Generation
        120847, -- 2412.13401 MR. Illuminate: Zero-Shot Low-Light Image Enhancement with Diffusion Prior
        121876, -- external Anatomical Domain Shifts: Test-time Heterogeneous Adaptation for 3D Human Pose P
        123100, -- external Enhancing stock price forecasting with a modular deep learning framework incorpo
        124680  -- 2605.00466 PAMod: Modeling Cyclical Shifts via Phase-Amplitude Modulation for Non-stationar
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
        512, -- 1611.07004 Image-to-Image Translation with Conditional Adversarial Networks
        517, -- 1611.07865 Controlling Perceptual Factors in Neural Style Transfer
        637, -- 1703.10593 Unpaired Image-to-Image Translation using Cycle-Consistent Adversarial Networks
        640, -- 1704.00028 Improved Training of Wasserstein GANs
        812, -- 1707.07012 Learning Transferable Architectures for Scalable Image Recognition
        888, -- 1709.07857 Using Simulation and Domain Adaptation to Improve Efficiency of Deep Robotic Gra
        983, -- 1711.09020 StarGAN: Unified Generative Adversarial Networks for Multi-Domain Image-to-Image
        998, -- 1711.11585 High-Resolution Image Synthesis and Semantic Manipulation with Conditional GANs
        1034, -- 1801.00055 Deformable GANs for Pose-based Human Image Generation
        1072, -- 1801.09392 Shift-Net: Image Inpainting via Deep Feature Rearrangement
        1425, -- 1808.01160 Efficient Purely Convolutional Text Encoding
        1516, -- 1809.10486 nnU-Net: Self-adapting Framework for U-Net-Based Medical Image Segmentation
        1659, -- 1811.11718 Partial Convolution based Padding
        1675, -- 1812.00568 Visual Foresight: Model-Based Deep Reinforcement Learning for Vision-Based Robot
        1779, -- 1901.09321 Fixup Initialization: Residual Learning Without Normalization
        1902, -- 1903.07291 Semantic Image Synthesis with Spatially-Adaptive Normalization
        1912, -- 1903.10520 Micro-Batch Training with Batch-Channel Normalization and Weight Standardization
        2098, -- 1905.05894 Online Normalization for Training Neural Networks
        2115, -- 1905.08233 Few-Shot Adversarial Learning of Realistic Neural Talking Head Models
        2166, -- 1905.13305 Countering Noisy Labels By Learning From Auxiliary Clean Labels
        2338, -- 1907.05600 Generative Modeling by Estimating Gradients of the Data Distribution
        2344, -- 1907.06571 Adversarial Video Generation on Complex Datasets
        2372, -- 1907.11922 MaskGAN: Towards Diverse and Interactive Facial Image Manipulation
        2449, -- 1908.08926 Efficient Deep Neural Networks
        2532, -- 1909.05379 Specifying Object Attributes and Relations in Interactive Scene Generation
        2662, -- 1910.04987 Artistic Glyph Image Synthesis via One-Stage Few-Shot Learning
        2678, -- 1910.06711 MelGAN: Generative Adversarial Networks for Conditional Waveform Synthesis
        2688, -- 1910.07467 Root Mean Square Layer Normalization
        2852, -- 1911.10375 Region Normalization for Image Inpainting
        2866, -- 1911.11763 SuperGlue: Learning Feature Matching with Graph Neural Networks
        2895, -- 1912.01865 StarGAN v2: Diverse Image Synthesis for Multiple Domains
        2960, -- 1912.11370 Big Transfer (BiT): General Visual Representation Learning
        2988, -- 2001.03024 DeeperForensics-1.0: A Large-Scale Dataset for Real-World Face Forgery Detection
        3228, -- 2003.07845 PowerNorm: Rethinking Batch Normalization in Transformers
        3303, -- 2004.02967 Evolving Normalization-Activation Layers
        3333, -- 2004.04727 3D Photography using Context-aware Layered Depth Inpainting
        3534, -- 2005.02706 Knee Injury Detection using MRI with Efficiently-Layered Network (ELNet)
        3598, -- 2005.09561 Normalized Attention Without Probability Cage
        3673, -- 2006.03997 MeshSDF: Differentiable Iso-Surface Extraction
        3684, -- 2006.05353 MeshWalker: Deep Mesh Understanding by Random Walks
        3717, -- 2006.08217 AdamP: Slowing Down the Slowdown for Momentum Optimizers on Scale-invariant Weig
        3858, -- 2007.02442 GRAF: Generative Radiance Fields for 3D-Aware Image Synthesis
        3904, -- 2007.08442 Kronecker Attention Networks
        3927, -- 2007.12072 TSIT: A Simple and Versatile Framework for Image-to-Image Translation
        4021, -- 2008.05865 DF-GAN: A Simple and Effective Baseline for Text-to-Image Synthesis
        4037, -- 2008.08345 Deep Volumetric Ambient Occlusion
        4055, -- 2008.10010 A Lip Sync Expert Is All You Need for Speech to Lip Generation In The Wild
        4602, -- 2011.11261 Hierarchically Decoupled Spatial-Temporal Contrast for Self-supervised Video Rep
        4626, -- 2011.13388 3DSNet: Unsupervised Shape-to-Shape 3D Style Transfer
        4653, -- 2012.01158 Single-Shot Freestyle Dance Reenactment
        4732, -- 2012.07287 Information-Theoretic Segmentation by Inpainting Error Maximization
        4891, -- 2101.04775 Towards Faster and Stabilized GAN Training for High-fidelity Few-shot Image Synt
        4923, -- 2101.08692 Characterizing signal propagation to close the performance gap in unnormalized R
        4951, -- 2101.11183 DeepOIS: Gyroscope-Guided Deep Optical Image Stabilizer Compensation
        5094, -- 2102.12593 AniGAN: Style-Guided Generative Adversarial Networks for Unsupervised Anime Face
        5303, -- 2103.15606 GNeRF: GAN-based Neural Radiance Field without Posed Camera
        5329, -- 2103.16874 VITON-HD: High-Resolution Virtual Try-On via Misalignment-Aware Normalization
        5425, -- 2104.05703 Adversarial Open Domain Adaptation for Sketch-to-Photo Synthesis
        5644, -- 2105.02201 PD-GAN: Probabilistic Diverse GAN for Image Inpainting
        5694, -- 2105.04619 Enhancing Photorealism Enhancement
        5817, -- 2105.14739 Controllable Person Image Synthesis with Spatially-Adaptive Warped Normalization
        5821, -- 2105.14995 Choose a Transformer: Fourier or Galerkin
        6082, -- 2106.11795 DeepMesh: Differentiable Iso-Surface Extraction
        6540, -- 2109.01123 Benchmarking the Robustness of Instance Segmentation Models
        6844, -- 2110.04065 Test-time Batch Statistics Calibration for Covariate Shift
        7259, -- 2111.09883 Swin Transformer V2: Scaling Up Capacity and Resolution
        7323, -- 2111.14093 Adaptive Reordering Sampler with Neurally Guided MAGSAC
        7332, -- 2111.14791 Self-Supervised Pre-Training of Swin Transformers for 3D Medical Image Analysis
        7445, -- 2112.04283 Adverse Weather Image Translation with Asymmetric and Uncertainty-aware GAN
        7578, -- 2112.10762 StyleSwin: Transformer-based GAN for High-resolution Image Generation
        7633, -- 2201.00112 SurfGen: Adversarial 3D Shape Synthesis with Explicit Surface Discriminators
        7643, -- 2201.01266 Swin UNETR: Swin Transformers for Semantic Segmentation of Brain Tumors in MRI I
        7673, -- 2201.03545 A ConvNet for the 2020s
        7690, -- 2201.05120 SeamlessGAN: Self-Supervised Synthesis of Tileable Texture Maps
        7894, -- 2202.03376 Message Passing Neural PDE Solvers
        7896, -- 2202.03555 data2vec: A General Framework for Self-supervised Learning in Speech, Vision and
        8292, -- 2203.08488 Pushing the limits of raw waveform speaker recognition
        8384, -- 2203.11932 Dataset Distillation by Matching Training Trajectories
        8542, -- 2204.01005 Frequency and Multi-Scale Selective Kernel Attention for Speaker Verification
        8549, -- 2204.01263 Direct Dense Pose Estimation
        8652, -- 2204.04676 Simple Baselines for Image Restoration
        8676, -- 2204.05426 ProtoTEx: Explaining Model Decisions with Prototype Tensors
        8817, -- 2204.10648 Exposure Correction Model to Enhance Image Quality
        9099, -- 2205.10643 Self-Supervised Speech Representation Learning: A Review
        9508, -- 2206.08343 Realistic One-shot Mesh-based Head Avatars
        9782, -- 2207.06324 PointNorm: Dual Normalization is All You Need for Point Cloud Analysis
        9833, -- 2207.09204 VoloGAN: Adversarial Domain Adaptation for Synthetic Depth Data
        9959, -- 2208.01313 Unified Normalization for Accelerating and Stabilizing Transformers
        10253, -- 2209.04836 Git Re-Basin: Merging Models modulo Permutation Symmetries
        10389, -- 2209.11448 Rethinking Performance Gains in Image Dehazing Networks
        10485, -- 2209.15430 Relative representations enable zero-shot latent space communication
        10701, -- 2210.05318 CASAPose: Class-Adaptive and Semantic-Aware Multi-Object Pose Estimation
        10853, -- 2210.08884 HyperDomainNet: Universal Domain Adaptation for Generative Adversarial Networks
        10967, -- 2210.12381 S2WAT: Image Style Transfer via Hierarchical Vision Transformer using Strips Win
        11209, -- 2211.02048 Efficient Spatially Sparse Inference for Conditional GANs and Diffusion Models
        11361, -- 2211.08253 HMOE: Hypernetwork-based Mixture of Experts for Domain Generalization
        11443, -- 2211.10586 Scaling Up Dataset Distillation to ImageNet-1K with Constant Memory
        11466, -- 2211.11082 DynIBaR: Neural Dynamic Image-Based Rendering
        11559, -- 2211.12870 ActMAD: Activation Matching to Align Distributions for Test-Time-Training
        11613, -- 2211.14058 Cross-Domain Ensemble Distillation for Domain Generalization
        11642, -- 2211.14730 A Time Series is Worth 64 Words: Long-term Forecasting with Transformers
        11969, -- 2212.07378 3DHumanGAN: 3D-Aware Human Image Generation with 3D Pose Mapping
        11975, -- 2212.07525 Efficient Self-supervised Learning with Contextualized Target Representations fo
        12277, -- 2301.00592 Edge Enhanced Image Style Transfer via Transformers
        12283, -- 2301.00808 ConvNeXt V2: Co-designing and Scaling ConvNets with Masked Autoencoders
        12345, -- 2301.03110 RobArch: Designing Robust Architectures against Adversarial Attacks
        12546, -- 2301.11189 Improving Statistical Fidelity for Neural Image Compression with Implicit Local
        13298, -- 2302.12444 On the Training Instability of Shuffling SGD with Batch Normalization
        13372, -- 2302.14416 DREAM: Efficient Dataset Distillation by Representative Matching
        13485, -- 2303.02328 Decompose, Adjust, Compose: Effective Normalization by Playing with Frequency fo
        13534, -- 2303.03667 Run, Don't Walk: Chasing Higher FLOPS for Faster Neural Networks
        13896, -- 2303.10598 StyleRF: Zero-shot 3D Style Transfer of Neural Radiance Fields
        14253, -- 2303.16565 PMAA: A Progressive Multi-scale Attention Autoencoder Model for High-performance
        14364, -- 2304.00212 Devil is in the Queries: Advancing Mask Transformers for Real-world Medical Imag
        14389, -- 2304.00898 Tunable Convolutions with Parametric Multi-Loss Optimization
        14568, -- 2304.04461 Modernizing Old Photos Using Multiple References via Photorealistic Style Transf
        14722, -- 2304.07645 Magnitude Invariant Parametrizations Improve Hypernetwork Learning
        14804, -- 2304.09790 AMT: All-Pairs Multi-Field Transforms for Efficient Frame Interpolation
        14906, -- 2304.11818 Master: Meta Style Transformer for Controllable Zero-Shot and Few-Shot Artistic
        15503, -- 2305.07648 A Critical View of Vision-Based Long-Term Dynamics Prediction Under Environment
        15979, -- 2305.13686 MP-SENet: A Speech Enhancement Model with Parallel Denoising of Magnitude and Ph
        16288, -- 2305.15912 Neural Characteristic Activation Analysis and Geometric Parameterization for ReL
        16443, -- 2305.17560 Scalable Transformer for PDE Surrogate Modeling
        16617, -- 2305.19245 AlteredAvatar: Stylizing Dynamic 3D Avatars with Fast Style Adaptation
        16740, -- 2306.00407 Towards Interactive Image Inpainting via Sketch Refinement
        17058, -- 2306.03838 Spherical Fourier Neural Operators: Learning Stable Dynamics on the Sphere
        17546, -- 2306.10001 Group Orthogonalization Regularization For Vision Models Adaptation and Robustne
        18560, -- 2307.12463 Rethinking Data Distillation: Do Not Overlook Calibration
        18716, -- 2307.15055 PointOdyssey: A Large-Scale Synthetic Dataset for Long-Term Point Tracking
        18720, -- 2307.15071 Writer adaptation for offline text recognition: An exploration of neural network
        18760, -- 2307.15988 RGB-D-Fusion: Image Conditioned Depth Diffusion of Humanoid Subjects
        18882, -- 2308.01536 MFIM: Megapixel Facial Identity Manipulation
        18941, -- 2308.02535 Learning to Generate Training Datasets for Robust Semantic Segmentation
        18998, -- 2308.03448 Make Explicit Calibration Implicit: Calibrate Denoiser Instead of the Noise Mode
        19322, -- 2308.08359 Membrane Potential Batch Normalization for Spiking Neural Networks
        19359, -- 2308.08926 Explicit Estimation of Magnitude and Phase Spectra in Parallel for High-Quality
        19418, -- 2308.09565 Understanding the Role of Layer Normalization in Label-Skewed Federated Learning
        19511, -- 2308.10297 DomainAdaptor: A Novel Approach to Test-time Adaptation
        19813, -- 2308.13783 Generalized Lightness Adaptation with Channel Selective Normalization
        20008, -- 2309.00255 SortedNet: A Scalable and Generalized Framework for Training Modular Deep Neural
        20623, -- 2309.10684 Locally Stylized Neural Radiance Fields
        20665, -- 2309.11139 More complex encoder is not all you need
        21067, -- 2309.17031 Scalable Multi-Temporal Remote Sensing Change Data Generation via Simulating Sto
        21123, -- 2310.00120 Multi-Grid Tensorized Fourier Neural Operator for High-Resolution PDEs
        21552, -- 2310.04901 WAIT: Feature Warping for Animation to Illustration video Translation using GANs
        21750, -- 2310.06982 Data Distillation Can Be Like Vodka: Distilling More Times For Better Quality
        21789, -- 2310.07402 NuTime: Numerically Multi-Scaled Embedding for Large-Scale Time-Series Pretraini
        21934, -- 2310.08855 Overcoming Recency Bias of Normalization Statistics in Continual Learning: Balan
        21977, -- 2310.09488 ARM: Refining Multivariate Forecasting with Adaptive Temporal-Contextual Learnin
        22469, -- 2310.15712 GNeSF: Generalizable Neural Semantic Fields
        22643, -- 2310.17880 Reconstructive Latent-Space Neural Radiance Fields for Efficient 3D Scene Repres
        22852, -- 2311.00455 Progressive Recurrent Network for Shadow Removal
        22857, -- 2311.00519 REBAR: Retrieval-Based Reconstruction for Time-series Contrastive Learning
        23749, -- 2311.14993 Coordinate-Aware Modulation for Neural Fields
        24678, -- 2312.07381 ScribblePrompt: Fast and Flexible Interactive Segmentation for Any Biomedical Im
        24929, -- 2312.11420 Tuning LayerNorm in Attention: Towards Efficient Multi-Modal LLM Finetuning
        25169, -- 2312.15297 Make Me a BNN: A Simple Strategy for Estimating Bayesian Uncertainty from Pre-tr
        25630, -- 2401.04722 U-Mamba: Enhancing Long-range Dependency for Biomedical Image Segmentation
        25854, -- 2401.08328 Un-Mixing Test-Time Normalization Statistics: Combatting Label Temporal Correlat
        26235, -- 2401.13505 Generative Human Motion Stylization in Latent Space
        26634, -- 2402.01134 DeepAAT: Deep Automated Aerial Triangulation for Fast UAV-based Mapping
        27964, -- 2402.16321 Self-Supervised Speech Quality Estimation and Enhancement Using Only Clean Speec
        28990, -- 2403.11261 A Lie Group Approach to Riemannian Batch Normalization
        29074, -- 2403.12040 Distilling Datasets Into Less Than One Image
        29101, -- 2403.12553 Pretraining Codomain Attention Neural Operators for Solving Multiphysics PDEs
        29876, -- 2404.02514 Freditor: High-Fidelity and Transferable NeRF Editing by Frequency Decomposition
        31210, -- 2405.06729 Fine-tuning Protein Language Models with Deep Mutational Scanning improves Varia
        31419, -- 2405.11582 SLAB: Efficient Transformers with Simplified Linear Attention and Progressive Re
        32623, -- 2406.06384 Generalizing to Unseen Domains in Diabetic Retinopathy with Disentangled Represe
        34397, -- 2407.07111 Diffusion Model-Based Video Editing: A Survey
        34962, -- 2407.14245 Dataset Distillation by Automatic Training Trajectories
        35040, -- 2407.15420 Local All-Pair Correspondence for Point Tracking
        35424, -- 2408.00386 What comes after transformers? -- A selective survey connecting ideas in deep le
        35739, -- 2408.05928 Adapting General Disentanglement-Based Speaker Anonymization for   Enhanced Emot
        36408, -- 2408.17081 Stochastic Layer-Wise Shuffle: A Good Practice to Improve Vision Mamba Training
        36634, -- 2409.03811 Parallel AutoRegressive Models for Multi-Agent Combinatorial Optimization
        37421, -- 2409.18479 CycleNet: Enhancing Time Series Forecasting through Modeling Periodic Patterns
        37784, -- 2410.02675 FAN: Fourier Analysis Networks
        39596, -- 2411.02256 Unified Speech Recognition: A Single Model for Auditory, Visual, and Audiovisual
        40081, -- 2411.10948 Towards Accurate and Efficient Sub-8-Bit Integer Training
        40273, -- 2411.14494 dc-GAN: Dual-Conditioned GAN for Face Demorphing From a Single Morph
        40971, -- 2412.03318 Domain-Agnostic Stroke Lesion Segmentation Using Physics-Constrained Synthetic D
        42724, -- 2501.06230 BEN: Using Confidence-Guided Matting for Dichotomous Image Segmentation
        43726, -- 2502.03654 Gompertz Linear Units: Leveraging Asymmetry for Enhanced Learning Dynamics
        46072, -- 2503.10622 Transformers without Normalization
        48225, -- 2504.20682 OG-HFYOLO :Orientation gradient guidance and heterogeneous feature fusion for de
        49511, -- 2505.17330 FS-DAG: Few Shot Domain Adapting Graph Networks for Visually Rich   Document Und
        50726, -- 2506.06454 LETS Forecast: Learning Embedology for Time Series Forecasting
        51050, -- 2506.10973 Principled Approaches for Extending Neural Architectures to Function Spaces for
        51240, -- 2506.14767 A Variational Framework for Improving Naturalness in Generative Spoken Language
        51751, -- 2507.05938 A Wireless Foundation Model for Multi-Task Prediction
        54484, -- 2512.01443 MEGConformer: Conformer-Based MEG Decoder for Robust Speech and Phoneme Classifi
        54717, -- 2512.10938 Stronger Normalization-Free Transformers
        54772, -- 2512.10794 What matters for Representation Alignment: Global Information or Spatial Structu
        55747, -- 2602.02914 FaceLinkGen: Rethinking Identity Leakage in Privacy-Preserving Face Recognition
        55748, -- 2602.01212 SimpleGPT: Improving GPT via A Simple Normalization Strategy
        57696, -- 2604.21689 StyleID: A Perception-Aware Dataset and Metric for Stylization-Agnostic Facial I
        59211, -- 2603.17403 Large-Scale 3D Ground-Motion Synthesis with Physics-Inspired Latent Operator Flo
        59238, -- 2603.17219 SA-CycleGAN-2.5D: Self-Attention CycleGAN with Tri-Planar Context for Multi-Site
        61778, -- 2601.22095 GeoNorm: Unify Pre-Norm and Post-Norm with Geodesic Optimization
        65348, -- 2511.04192 AStF: Motion Style Transfer via Adaptive Statistics Fusor
        67610, -- 2509.23238 WavJEPA: Semantic learning unlocks robust audio foundation models for   raw wave
        67690, -- 2509.22295 Aurora: Towards Universal Generative Multimodal Time Series Forecasting
        75845, -- 2411.04644 wav2sleep: A Unified Multi-Modal Approach to Sleep Stage Classification from Phy
        76039, -- 2410.12261 CATCH: Channel-Aware multivariate Time Series Anomaly Detection via   Frequency
        76350, -- 2409.12108 SPRMamba: Surgical Phase Recognition for Endoscopic Submucosal Dissection with M
        76728, -- 2407.13278 Deep Time Series Models: A Comprehensive Survey and Benchmark
        76932, -- 2406.14559 Disentangled Representation Learning for Environment-agnostic Speaker   Recognit
        78173, -- 2312.00276 Metalearning Continual Learning Algorithms
        78281, -- 2311.02062 GroomGen: A High-Quality Generative Hair Model Using Hierarchical Latent   Repre
        78957, -- 2305.18803 Koopa: Learning Non-stationary Time Series Dynamics with Koopman Predictors
        79488, -- 2212.08208 Location-aware Adaptive Normalization: A Deep Learning Approach For   Wildfire D
        79529, -- 2211.14830 Medical Image Segmentation Review: The success of U-Net
        79644, -- 2210.11672 Stochastic Adaptive Activation Function
        79820, -- 2207.13159 TINYCD: A (Not So) Deep Learning Model For Change Detection
        80330, -- 2112.04491 Improving Image Restoration by Revisiting Global Information Aggregation
        80341, -- 2112.02244 LAVT: Language-Aware Vision Transformer for Referring Image Segmentation
        80516, -- 2109.07547 RAFT-Stereo: Multilevel Recurrent Field Transforms for Stereo Matching
        80542, -- 2109.00983 Bilinear Input Normalization for Neural Networks in Financial Forecasting
        80558, -- 2108.10629 Improving Generalization of Batch Whitening by Convolutional Unit Optimization
        80775, -- 2104.07021 Dressing in Order: Recurrent Person Image Generation for Pose Transfer, Virtual
        81001, -- 2011.11731 HistoGAN: Controlling Colors of GAN-Generated and Real Images via Color Histogra
        81059, -- 2010.10241 BYOL works even without batch statistics
        81112, -- 2009.12798 AIM 2020: Scene Relighting and Illumination Estimation Challenge
        81179, -- 2008.03706 Block Shuffle: A Method for High-resolution Fast Style Transfer with   Limited M
        81402, -- 2003.11982 In defence of metric learning for speaker recognition
        81450, -- 2002.05873 Speech Enhancement using Self-Adaptation and Multi-Head Self-Attention
        81558, -- 1910.10261 QuartzNet: Deep Automatic Speech Recognition with 1D Time-Channel   Separable Co
        81737, -- 1905.01941 Few-Shot Adaptive Gaze Estimation
        81822, -- 1901.09482 Bridging the Gap Between Computational Photography and Visual Recognition
        81825, -- 1901.11390 MONet: Unsupervised Scene Decomposition and Representation
        81865, -- 1811.08839 fastMRI: An Open Dataset and Benchmarks for Accelerated MRI
        82056, -- 1804.01523 Stochastic Adversarial Video Prediction
        82144, -- 1711.07064 DeblurGAN: Blind Motion Deblurring Using Conditional Adversarial Networks
        86579, -- 2506.09024 DIsoN: Decentralized Isolation Networks for Out-of-Distribution Detection in Med
        86925, -- 2506.04401 Normalize Filters! Classical Wisdom for Deep Vision
        87201, -- 2505.18766 StyleGuard: Preventing Text-to-Image-Model-based Style Mimicry Attacks by Style
        87346, -- 2506.05310 Learning normalized image densities via dual score matching
        87393, -- 2510.13665 Axial Neural Networks for Dimension-Free Foundation Models
        88711, -- 2507.09031 Confounder-Free Continual Learning via Recursive Feature Normalization
        89318, -- 2505.00685 On the Importance of Gaussianizing Representations
        89383, -- 2411.08249 Retrieval Augmented Time Series Forecasting
        89826, -- 2506.00432 Channel Normalization for Time Series Channel Identification
        90171, -- 2406.19827 Towards Stable and Storage-efficient Dataset Distillation: Matching Convexified
        90693, -- 2503.18671 Structure-Aware Correspondence Learning for Relative Pose Estimation
        90789, -- 2503.21150 The Devil is in Low-Level Features for Cross-Domain Few-Shot Segmentation
        91625, -- 2406.02997 Residual Connections and Normalization Can Provably Prevent Oversmoothing in GNN
        91672, -- 2502.21143 Variational Bayesian Pseudo-Coreset
        91871, -- 2410.02094 Tracking objects that change in appearance with phase synchrony
        92058, -- 2412.09945 Going Beyond Feature Similarity: Effective Dataset distillation based on Class-a
        94076, -- 2503.04582 PSDNorm: Temporal Normalization for Deep Learning in Sleep Staging
        94334, -- 2603.08032 GCGNet: Graph-Consistent Generative Network for Time Series Forecasting with Exo
        94614, -- 2405.16730 ``Noisier'’ Noise Contrastive Estimation is (Almost) Maximum Likelihood
        94753, -- 2509.22307 Johnson-Lindenstrauss Lemma Guided Network for Efficient 3D Medical Segmentation
        101812, -- 2509.23413 URS: A Unified Neural Routing Solver for Cross-Problem Zero-Shot Generalization
        101865, -- 2605.08193 Normalization Equivariance for Arbitrary Backbones, with Application to Image De
        101939, -- 2605.30198 Active Continual Learning with Metaplastic Binary Bayesian Neural Networks
        104339, -- 1804.02958 Generative Adversarial Networks for Extreme Learned Image Compression
        104340, -- 2006.09965 High-Fidelity Generative Image Compression
        105194, -- 2506.22580 FedCLAM: Client Adaptive Momentum with Foreground Intensity Matching for Federat
        106844, -- 2511.06893 DeepBooTS: Dual-Stream Residual Boosting for Drift-Resilient Time-Series Forecas
        107820, -- 2512.02469 TGDD: Trajectory Guided Dataset Distillation with Balanced Distribution
        108181, -- 2601.10328 Meta Dynamic Graph for Traffic Flow Prediction
        108515, -- 2511.15016 CKDA: Cross-modality Knowledge Disentanglement and Alignment for Visible-Infrare
        109204, -- 2009.14153 Clova Baseline System for the VoxCeleb Speaker Recognition Challenge 2020
        109212, -- 2101.12491 Efficient-CapsNet: Capsule Network with Self-Attention Routing
        109890, -- 2502.20036 A2-GNN: Angle-Annular GNN for Visual Descriptor-Free Camera Relocalization
        111330, -- 2508.07219 ParaNoise-SV: Integrated Approach for Noise-Robust Speaker Verification with Par
        111403, -- 2506.02590 Synthetic Speech Source Tracing using Metric Learning
        111729, -- 2505.24450 SuPseudo: A Pseudo-supervised Learning Method for Neural Speech Enhancement in F
        111936, -- 2508.17868 FasterVoiceGrad: Faster One-step Diffusion-Based Voice Conversion with Adversari
        113142, -- 2407.07586 Simplifying Source-Free Domain Adaptation for Object Detection: Effective Self-T
        113469, -- 2308.14334 MetaWeather: Few-Shot Weather-Degraded Image Restoration
        113952, -- 2404.01946 Synthetic Data for Robust Stroke Segmentation
        114965, -- 2408.05502 GEM: Context-Aware Gaze EstiMation with Visual Search Behavior Matching for Ches
        115823, -- 2403.09124 Single Domain Generalization for Crowd Counting
        116694, -- 2404.00521 CHAIN: Enhancing Generalization in Data-Efficient GANs via lipsCHitz continuity
        116970, -- 2311.10696 Versatile Medical Image Segmentation Learned from Multi-Source Datasets via Mode
        117454, -- 2608.11546 Through Van Gogh’s Eyes: Global Style Transfer with Diffusion Model
        117657, -- 2606.24144 Geometry-Aware Style Transfer in 3D Gaussian Splatting
        117722, -- 2602.02232 LiFlow: Flow Matching for 3D LiDAR Scene Completion
        120176, -- 2503.09556 Electromyography-Informed Facial Expression Reconstruction for Physiological-Bas
        120231, -- 2503.19592 SACB-Net: Spatial-awareness Convolutions for Medical Image Registration
        120278, -- 2506.02396 Towards Explicit Geometry-Reflectance Collaboration for Generalized LiDAR Segmen
        123927, -- 2103.14031 High-Fidelity Pluralistic Image Completion with Transformers
        124001, -- 1803.08494 Group Normalization
        127470, -- 2609.39445 Raw-Routed Mixture of Adapters: A Causal Intervention for Routing Collapse in Ti
        130064, -- 2512.14253 FLAME: Flow Enhanced Legendre Memory Models for General Time Series Forecasting
        130411, -- 2605.24484 SPACE: Unifying Symmetric and Asymmetric Routing Problems for Generalist Neural
        131406, -- 2011.13005 PREDATOR: Registration of 3D Point Clouds with Low Overlap
        131451  -- 2005.12633 Long-Term Cloth-Changing Person Re-identification
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
