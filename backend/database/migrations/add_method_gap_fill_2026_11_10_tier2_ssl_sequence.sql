-- Method gap fill (2026-11-10 audit), tier 2: self-supervised vision and
-- sequence-model / LLM-agent methods. All eleven have an introducing arXiv
-- paper, so source_paper_id is set and the source gets an Introduced banner:
-- MoCo 1911.05722, BYOL 2006.07733, SwAV 2006.09882, Barlow Twins 2103.03230,
-- ALiBi 2108.12409, YaRN 2309.00071, RWKV 2305.13048, RetNet 2307.08621,
-- S4 2111.00396, Self-Refine 2303.17651, Reflexion 2303.11366.
--
-- S4 shares its source paper with the broader state-space-models method
-- (which already used 2111.00396 as its source); s4 is the specific
-- architecture family and state-space-models is left unchanged.
--
-- Keywords avoid bare ambiguous forms: "MoCo" (MRI motion correction,
-- MoCoGAN, model correction), lowercase "yarn", "S4" (semi-supervised semantic
-- segmentation, CMB-S4, model sizes) and "Self-Refine" as a case-sensitive
-- substring (it would match "Self-Refinement"). Hero images are imported
-- separately with import_entity_image.py; credits are set below.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'moco', 'MoCo',
    'Momentum Contrast (MoCo)',
    'Momentum Contrast (MoCo) is a [self-supervised](/methods/self-supervised-learning) method for learning visual representations by [contrastive learning](/methods/contrastive-learning), framed as building a large and consistent dictionary for a lookup task. A query encoder embeds one augmented view of an image, and the matching key is another view of the same image; the keys of other images act as negatives in an InfoNCE loss. MoCo keeps those negatives in a queue of encoded keys from recent mini-batches, so the dictionary can be much larger than the batch, and encodes keys with a momentum encoder whose weights are an exponential moving average of the query encoder, which keeps queued keys consistent as training proceeds. With a ResNet-50, MoCo was competitive under linear evaluation on ImageNet and its representations transferred better than supervised ImageNet pre-training on several PASCAL VOC and COCO detection and segmentation tasks. [MoCo v2](/paper/2003.04297) added the MLP projection head and stronger augmentations from [SimCLR](/methods/simclr), and [MoCo v3](/paper/2104.02057) adapted the framework to [Vision Transformers](/methods/vision-transformer). The momentum-encoder idea reappears in [BYOL](/methods/byol) and [DINO](/methods/dino).',
    'momentum contrast, momentum contrastive learning, MoCo v2, MoCov2, MoCo-v2, MoCo v3, MoCov3, MoCo-v3',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2019,
    (SELECT id FROM papers WHERE arxiv_id = '1911.05722'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Momentum Contrast for Unsupervised Visual Representation Learning',
    'https://github.com/facebookresearch/moco/blob/main/moco/builder.py',
    NULL,
    '[Momentum Contrast for Unsupervised Visual Representation Learning](/paper/1911.05722)',
    'judge',
    ARRAY['Momentum Contrast']::text[]
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'byol', 'BYOL',
    'Bootstrap Your Own Latent (BYOL)',
    'Bootstrap Your Own Latent (BYOL) is a [self-supervised](/methods/self-supervised-learning) image representation learning method that needs no negative pairs. Two augmented views of an image pass through an online network and a target network. The online network, which adds a small predictor head, is trained to predict the target network''s projection of the other view, and the target network is not trained by gradients: its weights are an exponential moving average of the online weights, as in the momentum encoder of [MoCo](/methods/moco). This asymmetry, the predictor plus the stop-gradient on the target, avoids collapse to a constant representation even though nothing pushes different images apart. BYOL reached 74.3% top-1 ImageNet linear-evaluation accuracy with a ResNet-50 and 79.6% with a larger ResNet, and it was less sensitive to batch size and to the choice of augmentations than contrastive methods such as [SimCLR](/methods/simclr). It inspired other non-contrastive methods, including [SimSiam](/paper/2011.10566) and the self-distillation of [DINO](/methods/dino).',
    'BYOL, bootstrap your own latent',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2020,
    (SELECT id FROM papers WHERE arxiv_id = '2006.07733'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Bootstrap your own latent: A new approach to self-supervised Learning',
    'https://github.com/google-deepmind/deepmind-research/tree/master/byol',
    NULL,
    '[Bootstrap your own latent: A new approach to self-supervised Learning](/paper/2006.07733)',
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'swav', 'SwAV',
    'Swapping Assignments between Views (SwAV)',
    'Swapping Assignments between Views (SwAV) is a [self-supervised](/methods/self-supervised-learning) image representation learning method that contrasts cluster assignments instead of comparing features pairwise. Features of each augmented view are mapped onto a set of learnable prototype vectors, and a code (a soft cluster assignment) is computed online for every view with the Sinkhorn-Knopp algorithm under an equal-partition constraint that prevents collapse. The model is then trained on a swapped prediction problem: the code of one view is predicted from the features of another view of the same image. Because it needs no pairwise comparisons, SwAV works without a large memory bank or momentum encoder, unlike [MoCo](/methods/moco). The paper also introduced multi-crop augmentation, which mixes two standard-resolution crops with several small low-resolution crops at little extra cost. SwAV reached 75.3% top-1 ImageNet linear-evaluation accuracy with a ResNet-50 and, when fine-tuned, surpassed supervised pre-training on several transfer tasks. It sits between [contrastive learning](/methods/contrastive-learning) and clustering-based methods such as DeepCluster, and its multi-crop strategy was reused by [DINO](/methods/dino).',
    'SwAV, swapping assignments between views',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2020,
    (SELECT id FROM papers WHERE arxiv_id = '2006.09882'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Unsupervised Learning of Visual Features by Contrasting Cluster Assignments',
    'https://github.com/facebookresearch/swav/blob/main/main_swav.py',
    NULL,
    '[Unsupervised Learning of Visual Features by Contrasting Cluster Assignments](/paper/2006.09882)',
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'barlow-twins',
    'Barlow Twins',
    'Barlow Twins',
    'Barlow Twins is a [self-supervised](/methods/self-supervised-learning) representation learning method that avoids collapse by reducing redundancy between embedding dimensions, an idea named after the neuroscientist H. Barlow''s redundancy-reduction principle. Two distorted views of each image in a batch pass through the same encoder and projector, and the method computes the cross-correlation matrix between the two batches of embeddings along the feature dimension. Its loss pushes this matrix toward the identity: diagonal terms toward one, so the embedding is invariant to the distortions, and off-diagonal terms toward zero, so different dimensions carry non-redundant information. Unlike [MoCo](/methods/moco) or [SimCLR](/methods/simclr), it needs no negative pairs or large batches, and unlike [BYOL](/methods/byol) it needs no predictor network, momentum encoder or stop-gradient. Barlow Twins benefits from very high-dimensional projector outputs and reached 73.2% top-1 ImageNet linear-evaluation accuracy with a ResNet-50. It is closely related to [VICReg](/paper/2105.04906), which adds explicit variance and covariance terms, and is used beyond vision for audio, graphs, remote sensing and molecules.',
    'barlow twins',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2103.03230'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Barlow Twins: Self-Supervised Learning via Redundancy Reduction',
    'https://github.com/facebookresearch/barlowtwins/blob/main/main.py',
    NULL,
    '[Barlow Twins: Self-Supervised Learning via Redundancy Reduction](/paper/2103.03230)',
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'alibi', 'ALiBi',
    'Attention with Linear Biases (ALiBi)',
    'Attention with Linear Biases (ALiBi) is a position encoding method for [Transformers](/methods/transformer) that adds no position embeddings to the token embeddings. Instead, it adds a fixed, non-learned bias to each query-key attention score that decreases linearly with the distance between the two tokens, so nearby tokens are attended to more. Each [attention head](/methods/multi-head-attention) uses a different slope, taken from a geometric sequence, which gives heads different effective ranges. ALiBi was designed for length extrapolation: a 1.3B-parameter model trained on 1,024-token inputs matched the perplexity of a sinusoidal-position model trained on 2,048 tokens when evaluated on 2,048, while training 11% faster and using 11% less memory, and ALiBi models kept improving at inference lengths well beyond those seen in training. It was adopted by BLOOM, MPT, MosaicBERT and other models, and is a common baseline for long-context position schemes such as [RoPE](/methods/rope) and its extensions like [YaRN](/methods/yarn).',
    'ALiBi, attention with linear biases',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2108.12409'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Train Short, Test Long: Attention with Linear Biases Enables Input Length Extrapolation',
    'https://github.com/ofirpress/attention_with_linear_biases',
    NULL,
    '[Train Short, Test Long: Attention with Linear Biases Enables Input Length Extrapolation](/paper/2108.12409)',
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'yarn', 'YaRN',
    'Yet another RoPE extensioN (YaRN)',
    'YaRN (Yet another RoPE extensioN) is a compute-efficient method for extending the context window of large language models that use [Rotary Position Embedding (RoPE)](/methods/rope). It builds on [Position Interpolation](/paper/2306.15595) and NTK-aware scaling, which rescale RoPE so that longer sequences map into the position range seen in pre-training. YaRN''s NTK-by-parts interpolation treats RoPE dimensions differently by wavelength: high-frequency dimensions, which encode local order, are left unchanged, low-frequency dimensions are interpolated, and those in between are blended with a ramp. It also scales attention logits with a temperature that keeps attention entropy stable at longer lengths. After brief fine-tuning on long sequences, YaRN extended LLaMA 2 models to 64k and 128k-token contexts, needing about 10 times fewer tokens and 2.5 times fewer training steps than earlier methods, and it can also be applied without fine-tuning. YaRN is widely used to stretch the context of open-weight models such as Qwen and DeepSeek, and is often compared against [ALiBi](/methods/alibi).',
    'YaRN, yet another rope extension',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2309.00071'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'YaRN: Efficient Context Window Extension of Large Language Models',
    'https://github.com/jquesnelle/yarn',
    NULL,
    '[YaRN: Efficient Context Window Extension of Large Language Models](/paper/2309.00071)',
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'rwkv', 'RWKV',
    'Receptance Weighted Key Value (RWKV)',
    'RWKV (Receptance Weighted Key Value) is a sequence model architecture that combines the parallel training of [Transformers](/methods/transformer) with the constant-memory inference of [RNNs](/methods/rnn). Each block alternates a time-mixing sub-block, a form of [linear attention](/methods/linear-attention) in which a WKV operator aggregates past values weighted by keys and a learned per-channel exponential time decay and gated by a receptance vector, with a channel-mixing sub-block that plays the role of the feed-forward layer; token shift mixes each input with the previous token. Because the attention-like operator is linear in sequence length, RWKV can be trained like a Transformer over whole sequences and run as an RNN at inference, with constant time and memory per token. The original paper trained models up to 14B parameters, the largest dense RNNs at the time, and found them performing on par with similarly sized Transformers. Later versions add matrix-valued states and data-dependent decay ([Eagle and Finch](/paper/2404.05892)) and a generalized delta rule ([RWKV-7 "Goose"](/paper/2503.14456)). RWKV is often compared with [RetNet](/methods/retnet), [Mamba](/methods/mamba) and other recurrent alternatives to attention, and has been adapted to vision, speech and medical imaging.',
    'RWKV',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2305.13048'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'RWKV: Reinventing RNNs for the Transformer Era',
    'https://github.com/BlinkDL/RWKV-LM',
    NULL,
    '[RWKV: Reinventing RNNs for the Transformer Era](/paper/2305.13048)',
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'retnet', 'RetNet',
    'Retentive Network (RetNet)',
    'Retentive Network (RetNet) is a foundation architecture for large language models that replaces softmax attention with a retention mechanism. Retention is a form of [linear attention](/methods/linear-attention) with an explicit exponential decay: the contribution of a past token is multiplied by a fixed factor gamma for every step of distance, and positions are encoded with complex rotations in the style of xPos. The same computation can be written in three equivalent forms: a parallel form for training on GPUs, a recurrent form with constant memory and O(1) cost per generated token, and a chunkwise recurrent form for efficient long-sequence modeling. Multi-scale retention gives each head a different decay rate and adds GroupNorm and a swish gate. In the authors'' experiments RetNet matched [Transformers](/methods/transformer) on language modeling and began to outperform them above about 2B parameters, with much lower inference memory and latency. RetNet is closely related to [RWKV](/methods/rwkv), [S4](/methods/s4) and [Mamba](/methods/mamba), and its retention has been adapted to vision, as in RMT.',
    'RetNet, retentive network',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2307.08621'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Retentive Network: A Successor to Transformer for Large Language Models',
    'https://github.com/microsoft/torchscale/blob/main/torchscale/architecture/retnet.py',
    NULL,
    '[Retentive Network: A Successor to Transformer for Large Language Models](/paper/2307.08621)',
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    's4',
    'Structured State Space Sequence Model',
    'Structured State Space Sequence Model (S4)',
    'The Structured State Space sequence model (S4) is a deep sequence model built from linear [state space model](/methods/state-space-models) layers, designed to capture very long-range dependencies. Each layer maps an input signal through a continuous-time state space x''(t) = Ax(t) + Bu(t), y(t) = Cx(t) + Du(t), discretized for sequence data, and can be computed either as a recurrence or, during training, as a long global convolution. S4 initializes the state matrix A with HiPPO matrices, which let the state memorize history, and makes the computation tractable by parameterizing A as a normal plus low-rank matrix, so the convolution kernel can be evaluated with a Cauchy kernel in near-linear time. S4 set a new state of the art on the Long Range Arena benchmark, was the first model to solve its Path-X task with 16k-length inputs, and performed strongly on raw speech classification and image and language modeling. It started a family of structured SSMs, including diagonal variants ([DSS](/paper/2203.14343), [S4D](/paper/2206.11893)), [S5](/paper/2208.04933), and the selective SSM [Mamba](/methods/mamba), which adds input-dependent parameters. S4 is one specific architecture within the broader class of [state space models](/methods/state-space-models).',
    'structured state space sequence model, structured state-space sequence model, S4 model, S4 layer',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2111.00396'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Efficiently Modeling Long Sequences with Structured State Spaces',
    'https://github.com/state-spaces/s4',
    NULL,
    '[Efficiently Modeling Long Sequences with Structured State Spaces](/paper/2111.00396)',
    'judge',
    ARRAY['S4']::text[]
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'self-refine', 'Self-Refine', 'Self-Refine',
    'Self-Refine is an inference-time prompting method in which a single large language model improves its own output through iterative self-feedback. The model first generates an initial answer, then is prompted to give actionable feedback on that answer, and then to rewrite the answer using the feedback; the feedback and refine steps repeat until a stopping condition or an iteration limit is reached. Self-Refine needs no additional training, supervised data, separate reward model or [reinforcement learning](/methods/rlhf), only few-shot prompts for each step. Across seven tasks, from dialogue response generation and code optimization to math reasoning, outputs refined this way were preferred by humans and automatic metrics over one-step generation from the same GPT-3.5 and GPT-4 models, by about 20% absolute on average. Self-Refine is a standard baseline for self-correction and test-time compute methods, alongside [Self-Consistency](/methods/self-consistency) and [Chain-of-Thought](/methods/chain-of-thought-cot), and is related to [Reflexion](/methods/reflexion), which stores verbal feedback across agent trials.',
    'self-refine',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2303.17651'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Self-Refine: Iterative Refinement with Self-Feedback',
    'https://github.com/madaan/self-refine',
    NULL,
    '[Self-Refine: Iterative Refinement with Self-Feedback](/paper/2303.17651)',
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'reflexion', 'Reflexion', 'Reflexion',
    'Reflexion is a framework for reinforcing language [agents](/methods/agent) through linguistic feedback instead of weight updates. An Actor model generates actions or code, an Evaluator scores the resulting trajectory with a binary or scalar signal, such as unit-test results or task success, and a Self-Reflection model turns failures into short natural-language reflections on what went wrong. These reflections are stored in an episodic memory and added to the Actor''s context in later trials, so the agent improves over repeated attempts at the same task without fine-tuning. Reflexion can use the [ReAct](/methods/react) or [Chain-of-Thought](/methods/chain-of-thought-cot) formats as its Actor. It improved sequential decision-making on ALFWorld, question answering on HotpotQA, and code generation, where it reached 91% pass@1 on HumanEval compared with 80% for GPT-4 at the time. Reflexion is a common baseline for self-improving and memory-augmented agents and is related to [Self-Refine](/methods/self-refine), which iterates feedback within a single generation.',
    'Reflexion',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2303.11366'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Reflexion: Language Agents with Verbal Reinforcement Learning',
    'https://github.com/noahshinn/reflexion',
    NULL,
    '[Reflexion: Language Agents with Verbal Reinforcement Learning](/paper/2303.11366)',
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- Introduced banners: each source paper lists its method.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN ('moco', 'byol', 'swav', 'barlow-twins', 'alibi', 'yarn', 'rwkv', 'retnet', 's4', 'self-refine', 'reflexion') AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug IN ('moco', 'byol', 'swav', 'barlow-twins', 'alibi', 'yarn', 'rwkv', 'retnet', 's4', 'self-refine', 'reflexion') AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed paper links (2026-11-10). Candidates: local Semantic Scholar
-- citers of each source paper plus bounded title/abstract regex matches on the
-- method's names. Positives name the method in the title or abstract (use,
-- extend, analyze, survey or compare against it); citers that do not name it,
-- and regex hits that mean something else, become durable exclusions so the
-- keyword and reference backfills do not re-link them. Positive lists carry
-- arXiv id and title comments; exclusion lists are bare ids to keep the file
-- reviewable in size. Semantic Scholar returns at most 10,000 citations, so
-- the MoCo (16k) and BYOL (9.4k) citer sets were completed from OpenAlex.

-- moco: 46 links, 1961 exclusions. (1988 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE moco_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'moco'
  AND p.id IN (
        2812, 3198, 4364, 4576, 5135, 5183, 5343, 5378, 5691, 6374, 6583, 6739, 6916, 8805, 9567, 9669,
        11002, 11090, 11305, 11324, 12559, 14207, 17150, 17586, 19229, 19626, 21631, 29055, 30688, 45967, 47335, 52875,
        61257, 71624, 75132, 84677, 84913, 88155, 88295, 93522, 94511, 98379, 98570, 104056, 104084, 112918
  );

DELETE FROM paper_method_exclusions x
USING moco_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM moco_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM moco_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE moco_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'moco'
  AND p.id IN (
        1822, 2126, 2260, 2808, 2898, 2960, 3098, 3114, 3121, 3241, 3253, 3273,
        3279, 3321, 3401, 3435, 3516, 3603, 3616, 3655, 3670, 3675, 3691, 3697,
        3705, 3709, 3718, 3738, 3740, 3741, 3749, 3752, 3769, 3773, 3797, 3804,
        3819, 3820, 3842, 3845, 3873, 3882, 3885, 3896, 3942, 3960, 3983, 3994,
        4000, 4074, 4085, 4136, 4156, 4163, 4206, 4238, 4239, 4243, 4324, 4374,
        4410, 4411, 4415, 4450, 4462, 4465, 4470, 4476, 4481, 4544, 4558, 4587,
        4588, 4591, 4602, 4612, 4619, 4625, 4627, 4675, 4710, 4730, 4732, 4747,
        4753, 4767, 4770, 4780, 4787, 4813, 4816, 4891, 4909, 4919, 4923, 4955,
        4996, 5004, 5020, 5022, 5030, 5034, 5049, 5098, 5108, 5144, 5149, 5160,
        5172, 5186, 5188, 5213, 5235, 5255, 5261, 5285, 5314, 5320, 5336, 5395,
        5400, 5421, 5445, 5562, 5583, 5606, 5612, 5672, 5699, 5760, 5782, 5795,
        5856, 5860, 5880, 5908, 5938, 5943, 5947, 5985, 5989, 5990, 6003, 6075,
        6081, 6084, 6166, 6205, 6261, 6263, 6277, 6407, 6435, 6489, 6496, 6520,
        6539, 6541, 6640, 6736, 6748, 6750, 6811, 6817, 6860, 6861, 6888, 6908,
        6965, 7008, 7024, 7107, 7119, 7124, 7138, 7164, 7181, 7200, 7209, 7217,
        7218, 7241, 7260, 7262, 7314, 7321, 7332, 7335, 7347, 7386, 7475, 7479,
        7506, 7547, 7550, 7556, 7561, 7600, 7601, 7684, 7696, 7739, 7838, 7888,
        8027, 8128, 8176, 8187, 8188, 8201, 8203, 8216, 8226, 8237, 8260, 8268,
        8272, 8292, 8340, 8364, 8368, 8374, 8386, 8469, 8487, 8515, 8607, 8628,
        8656, 8695, 8720, 8733, 8777, 8972, 8996, 9028, 9031, 9099, 9147, 9149,
        9159, 9272, 9388, 9399, 9480, 9573, 9589, 9656, 9683, 9689, 9716, 9736,
        9746, 9762, 9764, 9766, 9832, 9848, 9872, 9879, 10043, 10072, 10142, 10209,
        10377, 10438, 10465, 10478, 10526, 10660, 10715, 10761, 10801, 10991, 11011, 11130,
        11154, 11159, 11186, 11255, 11256, 11277, 11392, 11419, 11434, 11444, 11458, 11500,
        11501, 11545, 11560, 11573, 11604, 11715, 11761, 11796, 11846, 11852, 11855, 11885,
        11923, 11944, 11951, 12030, 12126, 12255, 12267, 12281, 12297, 12308, 12312, 12321,
        12323, 12376, 12385, 12408, 12426, 12452, 12872, 12879, 12979, 13028, 13166, 13173,
        13178, 13186, 13374, 13387, 13389, 13449, 13471, 13478, 13479, 13490, 13519, 13521,
        13572, 13600, 13605, 13619, 13624, 13644, 13650, 13662, 13675, 13697, 13715, 13747,
        13799, 13808, 13816, 13828, 13845, 13854, 13859, 13868, 13873, 13886, 13894, 13910,
        13917, 13922, 13939, 13941, 13949, 13960, 13963, 13967, 13968, 13980, 13992, 14019,
        14067, 14068, 14070, 14072, 14077, 14117, 14132, 14152, 14171, 14191, 14193, 14232,
        14250, 14254, 14262, 14318, 14350, 14356, 14369, 14372, 14378, 14379, 14395, 14423,
        14425, 14434, 14480, 14508, 14570, 14576, 14584, 14636, 14640, 14659, 14663, 14669,
        14670, 14697, 14709, 14725, 14761, 14782, 14786, 14797, 14827, 14880, 14902, 14916,
        14934, 14949, 15004, 15022, 15078, 15094, 15097, 15115, 15120, 15160, 15273, 15321,
        15322, 15409, 15412, 15485, 15516, 15518, 15553, 15566, 15594, 15657, 15684, 15737,
        15810, 15900, 15951, 15993, 16266, 16289, 16302, 16342, 16359, 16384, 16428, 16458,
        16508, 16536, 16561, 16630, 16663, 16731, 16743, 16765, 16792, 16809, 16919, 16926,
        16937, 16945, 17020, 17021, 17062, 17092, 17145, 17154, 17163, 17165, 17180, 17182,
        17186, 17205, 17377, 17428, 17497, 17499, 17508, 17559, 17569, 17645, 17655, 17702,
        17706, 17713, 17749, 17754, 17763, 17796, 17800, 17830, 17832, 17881, 17903, 17909,
        17985, 18021, 18112, 18159, 18196, 18244, 18245, 18250, 18306, 18321, 18338, 18341,
        18353, 18367, 18396, 18403, 18469, 18482, 18498, 18509, 18520, 18545, 18552, 18569,
        18575, 18629, 18664, 18676, 18683, 18705, 18728, 18738, 18777, 18792, 18815, 18825,
        18838, 18853, 18856, 18861, 18865, 18948, 18962, 18983, 18989, 18998, 19012, 19023,
        19039, 19045, 19081, 19183, 19195, 19303, 19314, 19320, 19326, 19328, 19358, 19378,
        19379, 19382, 19414, 19415, 19455, 19464, 19474, 19487, 19495, 19582, 19587, 19590,
        19594, 19599, 19604, 19616, 19642, 19659, 19688, 19750, 19752, 19769, 19777, 19808,
        19829, 19852, 19863, 19865, 19871, 19877, 19895, 19911, 19917, 19972, 20055, 20057,
        20065, 20126, 20131, 20148, 20182, 20215, 20280, 20346, 20420, 20584, 20629, 20657,
        20748, 20839, 21034, 21038, 21041, 21065, 21129, 21236, 21243, 21270, 21406, 21566,
        21717, 21788, 21821, 21832, 21878, 21913, 21990, 22179, 22268, 22278, 22294, 22297,
        22339, 22371, 22398, 22506, 22609, 22727, 22733, 22822, 22857, 22861, 22922, 22927,
        22993, 23010, 23072, 23145, 23174, 23216, 23388, 23528, 23544, 23564, 23571, 23732,
        23760, 23913, 23932, 23978, 23982, 23983, 23993, 24052, 24064, 24100, 24102, 24108,
        24130, 24161, 24212, 24220, 24237, 24240, 24306, 24375, 24446, 24573, 24632, 24674,
        24717, 24789, 24836, 24858, 24860, 24862, 24868, 24886, 24906, 24982, 25058, 25076,
        25104, 25162, 25290, 25326, 25331, 25335, 25343, 25439, 25462, 25503, 25554, 25647,
        25732, 25761, 25820, 25863, 25874, 25926, 25935, 26020, 26030, 26046, 26089, 26304,
        26308, 26309, 26400, 26462, 26766, 26787, 26875, 26900, 26976, 27026, 27029, 27188,
        27243, 27316, 27331, 27519, 27547, 27583, 27651, 27676, 27687, 27798, 27835, 28044,
        28130, 28177, 28242, 28248, 28301, 28348, 28465, 28487, 28575, 28585, 28591, 28621,
        28630, 28934, 29000, 29017, 29094, 29095, 29284, 29310, 29487, 29623, 29675, 29723,
        29789, 29819, 29850, 29938, 30053, 30238, 30278, 30288, 30321, 30431, 30442, 30461,
        30463, 30485, 30502, 30510, 30541, 30551, 30572, 30628, 30653, 30727, 30748, 30833,
        30862, 30867, 30935, 31002, 31133, 31148, 31209, 31213, 31300, 31307, 31348, 31472,
        31484, 31656, 31700, 31805, 31821, 31872, 31901, 32030, 32104, 32178, 32204, 32545,
        32559, 32568, 32733, 32813, 32843, 32877, 32902, 32905, 32926, 33487, 33597, 33611,
        33672, 33701, 33915, 34114, 34123, 34125, 34281, 34283, 34297, 34333, 34371, 34398,
        34420, 34437, 34497, 34541, 34627, 34713, 34716, 34876, 34900, 34969, 34985, 34998,
        35043, 35153, 35176, 35313, 35339, 35423, 35424, 35453, 35472, 35478, 35511, 35519,
        35730, 35860, 35886, 35935, 35943, 36058, 36147, 36184, 36228, 36272, 36307, 36405,
        36630, 37056, 37058, 37260, 37288, 37342, 37364, 37373, 37397, 37465, 37513, 37515,
        37523, 37554, 37575, 37661, 37902, 37988, 38156, 38191, 38280, 38396, 38425, 38470,
        38512, 38585, 38610, 38773, 38799, 38808, 38810, 38824, 38834, 38904, 38938, 38967,
        39016, 39080, 39103, 39179, 39266, 39327, 39589, 39733, 40015, 40229, 40321, 40423,
        40432, 40518, 40615, 40617, 40645, 40690, 40725, 40802, 40900, 40902, 41027, 41099,
        41133, 41199, 41336, 41558, 41660, 41687, 41690, 41754, 41844, 42014, 42209, 42217,
        42280, 42471, 42509, 42534, 42590, 42591, 42622, 42649, 42676, 42908, 42924, 43077,
        43120, 43645, 43735, 43860, 43977, 44089, 44116, 44214, 44367, 44455, 44511, 44592,
        44745, 44748, 44772, 44818, 44952, 45109, 45252, 45414, 45607, 45662, 45722, 45742,
        45773, 45810, 45930, 46045, 46057, 46142, 46227, 46291, 46403, 46497, 46566, 46672,
        46748, 46849, 47068, 47137, 47151, 47168, 47185, 47195, 47345, 47441, 47525, 47606,
        47657, 47679, 47681, 47947, 48082, 48332, 48395, 48417, 48436, 48473, 48525, 48709,
        48880, 48908, 48961, 49053, 49275, 49277, 49431, 49441, 49614, 49704, 49709, 49939,
        49963, 49977, 50046, 50073, 50242, 50344, 50519, 50524, 50529, 50664, 50667, 50819,
        50870, 50951, 50958, 51139, 51146, 51371, 51539, 51553, 51771, 51783, 51824, 51841,
        51886, 51981, 51994, 52019, 52043, 52092, 52127, 52307, 52605, 52754, 52860, 53105,
        53171, 53355, 53443, 53453, 53502, 53505, 53568, 53585, 53648, 53679, 53835, 53961,
        53991, 54156, 54194, 54252, 54496, 54644, 54722, 54850, 54865, 54905, 54974, 55055,
        55447, 55545, 55561, 55967, 56316, 56364, 56421, 56637, 56833, 56841, 56920, 56929,
        56996, 57043, 57095, 57096, 57131, 57532, 57563, 57677, 57818, 57905, 57934, 58471,
        58976, 59074, 59320, 59510, 59744, 59996, 60378, 60410, 60500, 60511, 60519, 60615,
        60953, 61225, 61317, 61328, 61370, 61611, 61685, 61845, 61982, 62072, 62139, 62195,
        62295, 62374, 62410, 62461, 62730, 62933, 63309, 63502, 63560, 63611, 63621, 63788,
        63811, 63832, 63927, 63995, 64073, 64100, 64216, 64227, 64229, 64298, 64460, 64493,
        64702, 64706, 64714, 64731, 64792, 64928, 64965, 65155, 65175, 65184, 65588, 65590,
        65591, 65760, 65794, 65892, 66091, 66223, 66297, 66326, 66790, 66875, 66902, 66933,
        67006, 67128, 67205, 67490, 67771, 67818, 67897, 68006, 68023, 68253, 68276, 68339,
        68377, 68495, 68558, 68611, 68774, 68984, 69189, 69251, 69340, 69406, 69565, 69589,
        69667, 69935, 70054, 70107, 70199, 70292, 70312, 70698, 70744, 70820, 70837, 70856,
        70945, 71157, 71297, 71307, 71436, 71715, 71754, 71812, 71949, 72006, 72008, 72095,
        72986, 73185, 73197, 73265, 73280, 73296, 73303, 73325, 73482, 73520, 73561, 73644,
        73656, 73725, 73734, 73851, 73860, 73882, 74096, 74196, 74661, 74708, 74805, 74849,
        74903, 75084, 75095, 75101, 75102, 75119, 75528, 75590, 75812, 75844, 75873, 76006,
        76008, 76039, 76049, 76050, 76141, 76203, 76226, 76468, 76493, 76507, 76580, 76599,
        76631, 76675, 76728, 76754, 77027, 77091, 77160, 77250, 77432, 77448, 77452, 77605,
        77618, 77702, 77857, 78003, 78038, 78107, 78139, 78371, 78384, 78485, 78646, 78781,
        78860, 78886, 78914, 78917, 78931, 78941, 78996, 79001, 79015, 79139, 79233, 79275,
        79323, 79421, 79459, 79509, 79539, 79553, 79582, 79641, 79756, 79836, 79895, 80008,
        80123, 80124, 80125, 80139, 80144, 80184, 80338, 80341, 80347, 80362, 80405, 80416,
        80464, 80490, 80493, 80499, 80620, 80661, 80689, 80693, 80724, 80799, 80828, 80871,
        80878, 80969, 80976, 81041, 81059, 81258, 81261, 82951, 83144, 83576, 83661, 83716,
        84053, 84070, 84140, 84182, 84195, 84199, 84249, 84430, 84442, 84595, 84714, 84741,
        84744, 84748, 84805, 84806, 84894, 84900, 85013, 85038, 85168, 85283, 85412, 85505,
        85585, 85633, 85719, 85765, 85955, 85986, 86005, 86037, 86046, 86118, 86128, 86150,
        86208, 86219, 86286, 86357, 86460, 86511, 86644, 86799, 86829, 87094, 87113, 87200,
        87261, 87274, 87278, 87470, 87624, 87652, 87716, 87731, 87736, 87737, 87749, 87753,
        87807, 87810, 87849, 87857, 87895, 87935, 87945, 87976, 87990, 88000, 88047, 88055,
        88121, 88150, 88195, 88222, 88262, 88266, 88333, 88346, 88392, 88444, 88465, 88491,
        88634, 88880, 89411, 89564, 90081, 90085, 90090, 90173, 90213, 90215, 90238, 90318,
        90373, 90380, 90401, 90411, 90436, 90534, 90548, 90589, 90634, 90707, 90772, 90836,
        90882, 90934, 90957, 90967, 90978, 90983, 90986, 91115, 91193, 91267, 91296, 91347,
        91391, 91569, 91636, 91664, 91674, 91707, 91766, 91800, 91811, 91860, 91899, 91939,
        91945, 91947, 91985, 92060, 92073, 92147, 92166, 92243, 92425, 92443, 92844, 93088,
        93193, 93208, 93275, 93355, 93449, 93498, 93772, 93887, 93889, 93951, 94049, 94115,
        94279, 94357, 94476, 94485, 94531, 94546, 94674, 94750, 94800, 94851, 94931, 94956,
        95008, 95018, 95048, 95400, 95465, 95798, 96533, 96735, 97892, 98031, 98205, 98255,
        98339, 98453, 98608, 98612, 98619, 98633, 98655, 98657, 98693, 98733, 98783, 99025,
        99088, 99630, 99639, 99970, 100566, 100641, 100684, 100861, 100924, 101276, 101324, 101376,
        101382, 101391, 102574, 103858, 103893, 103935, 104071, 104105, 104133, 104263, 104496, 104523,
        104913, 104943, 105008, 105143, 105152, 105189, 105240, 105266, 105641, 105692, 105714, 105736,
        105752, 105784, 105837, 106002, 106485, 106558, 106590, 106657, 106690, 106717, 106774, 106879,
        106972, 107019, 107075, 107125, 107137, 107147, 107150, 107310, 107384, 107439, 107451, 107582,
        107621, 107758, 107841, 107937, 107960, 108070, 108113, 108230, 108247, 108335, 108357, 108446,
        108495, 108622, 108743, 108773, 109304, 109313, 109335, 109421, 109424, 110790, 110795, 111039,
        111329, 111451, 111756, 112360, 112365, 112403, 112445, 112457, 112468, 112477, 112498, 112521,
        112527, 112530, 112539, 112568, 112584, 112624, 112627, 112676, 112708, 112718, 112726, 112761,
        112776, 112798, 112822, 112833, 112847, 112870, 112881, 112883, 112893, 112899, 112906, 112912,
        112922, 112931, 112938, 112962, 112969, 112999, 113034, 113035, 113044, 113049, 113052, 113059,
        113068, 113072, 113080, 113088, 113117, 113118, 113126, 113133, 113143, 113157, 113177, 113185,
        113208, 113214, 113227, 113242, 113247, 113281, 113287, 113323, 113345, 113399, 113424, 113425,
        113432, 113498, 113543, 113567, 113581, 113598, 113612, 113639, 113644, 113678, 113679, 113695,
        113706, 113718, 113951, 114318, 114368, 114411, 114441, 114446, 114926, 115003, 115010, 115079,
        115097, 115131, 115137, 115147, 115162, 115195, 115289, 115303, 115315, 115343, 115350, 115400,
        115426, 115441, 115464, 115470, 115508, 115514, 115519, 115530, 115540, 115616, 115627, 115713,
        115726, 115727, 115779, 115800, 115809, 115855, 115861, 115886, 115932, 115937, 115957, 115972,
        116001, 116081, 116088, 116089, 116097, 116126, 116139, 116166, 116176, 116215, 116218, 116258,
        116285, 116313, 116322, 116327, 116333, 116342, 116348, 116349, 116354, 116386, 116403, 116408,
        116426, 116427, 116459, 116475, 116481, 116542, 116556, 116571, 116584, 116600, 116628, 116635,
        116649, 116666, 116688, 116690, 116722, 116739, 116756, 116783, 116797, 116802, 116808, 116822,
        116835, 116848, 116868, 116903, 116922, 116954, 116960, 116974, 117003, 117034, 117081, 117086,
        117110, 117188, 117211, 117219, 117411, 117438, 117833, 117919, 117927, 117984, 118122, 118125,
        118145, 118168, 118179, 118285, 118308, 118327, 118513, 118517, 118641, 118764, 118907, 118910,
        118914, 118922, 118932, 118942, 118946, 119013, 119047, 119066, 119071, 119106, 119144, 119282,
        119375, 119415, 119425, 119531, 119562, 119617, 119750, 119758, 119772, 119793, 119800, 119837,
        119898, 120006, 120014, 120018, 120051, 120094, 120097, 120159, 120182, 120224, 120239, 120257,
        120305, 120337, 120348, 120368, 120394, 120410, 120448, 120512, 120524, 120581, 120592, 120594,
        120950, 121391, 121592, 121922, 122214, 122217, 122218, 122283, 122510, 122551, 122828, 123045,
        123140, 123383, 123653, 123918, 124027, 124320, 124433, 124891, 125622, 125744, 125916, 125990,
        126253, 126343, 126573, 126796, 126921, 126936, 127142, 127211, 127801, 127983, 128168, 128623,
        128774, 129616, 130272, 130302, 130369, 130428, 130771, 131296, 131520, 131610, 131632, 131669,
        131751, 131856, 131935, 131974, 132007
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the MoCo source or matches its name without naming, using or comparing MoCo'
FROM moco_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING moco_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING moco_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- byol: 33 links, 1295 exclusions. (1322 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE byol_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'byol'
  AND p.id IN (
        3709, 5034, 5135, 5186, 5691, 8237, 8609, 8644, 9393, 9593, 9716, 12990, 14207, 18469, 18633, 35837,
        47335, 71810, 74362, 76468, 79559, 79892, 81059, 84913, 91714, 93126, 95798, 98570, 98657, 101803, 110314, 111157,
        130302
  );

DELETE FROM paper_method_exclusions x
USING byol_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM byol_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM byol_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE byol_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'byol'
  AND p.id IN (
        3241, 3697, 3718, 3741, 3882, 3885, 3978, 4000, 4074, 4206, 4238, 4239,
        4243, 4324, 4374, 4411, 4466, 4470, 4576, 4587, 4588, 4591, 4612, 4625,
        4627, 4710, 4732, 4767, 4923, 4955, 5004, 5020, 5030, 5098, 5099, 5108,
        5144, 5183, 5213, 5235, 5255, 5261, 5320, 5336, 5378, 5395, 5562, 5606,
        5612, 5672, 5699, 5795, 5856, 5880, 5908, 5921, 5938, 5942, 5990, 6003,
        6051, 6084, 6190, 6263, 6374, 6435, 6496, 6520, 6539, 6587, 6640, 6739,
        6750, 6817, 6861, 6868, 6869, 6871, 6888, 6908, 6916, 7001, 7022, 7024,
        7026, 7107, 7119, 7124, 7200, 7209, 7216, 7218, 7235, 7260, 7347, 7378,
        7385, 7519, 7547, 7550, 7561, 7600, 7632, 7739, 7759, 7782, 7838, 7881,
        7888, 7889, 7896, 7905, 7910, 7990, 8027, 8111, 8152, 8175, 8188, 8226,
        8272, 8292, 8359, 8366, 8368, 8370, 8374, 8404, 8444, 8446, 8487, 8558,
        8619, 8628, 8640, 8720, 8802, 8805, 8816, 8940, 9049, 9084, 9099, 9110,
        9130, 9159, 9235, 9253, 9272, 9278, 9317, 9347, 9388, 9392, 9441, 9491,
        9556, 9567, 9573, 9577, 9650, 9669, 9671, 9683, 9746, 9762, 9764, 9766,
        9774, 9786, 9806, 9809, 9832, 9848, 9872, 9977, 10072, 10132, 10176, 10244,
        10287, 10340, 10377, 10387, 10399, 10431, 10520, 10555, 10589, 10591, 10715, 10739,
        10801, 10814, 10880, 10906, 10907, 10911, 10932, 10991, 11002, 11090, 11130, 11154,
        11159, 11186, 11232, 11239, 11255, 11256, 11305, 11324, 11355, 11392, 11419, 11434,
        11444, 11501, 11506, 11545, 11564, 11573, 11647, 11659, 11695, 11715, 11761, 11812,
        11830, 11840, 11851, 11852, 11885, 11923, 11944, 11951, 11956, 11975, 12018, 12030,
        12031, 12047, 12048, 12175, 12229, 12246, 12256, 12283, 12297, 12301, 12304, 12308,
        12312, 12356, 12385, 12452, 12483, 12559, 12616, 12618, 12847, 12849, 12850, 12875,
        12891, 12914, 12945, 12971, 13028, 13074, 13094, 13175, 13178, 13204, 13215, 13216,
        13225, 13273, 13350, 13387, 13449, 13478, 13519, 13572, 13624, 13644, 13646, 13701,
        13816, 13828, 13854, 13910, 13917, 13939, 13963, 13990, 14007, 14019, 14068, 14132,
        14152, 14191, 14232, 14254, 14288, 14397, 14419, 14423, 14438, 14508, 14549, 14570,
        14576, 14601, 14640, 14669, 14697, 14709, 14725, 14761, 14786, 14902, 14916, 15004,
        15076, 15078, 15094, 15097, 15243, 15321, 15553, 15566, 15645, 15657, 15684, 15810,
        15827, 15993, 16074, 16266, 16289, 16339, 16342, 16359, 16384, 16391, 16495, 16518,
        16530, 16631, 16663, 16731, 16752, 16792, 16809, 16832, 16919, 16949, 16950, 17020,
        17031, 17062, 17063, 17068, 17085, 17119, 17150, 17154, 17165, 17182, 17186, 17205,
        17377, 17420, 17505, 17508, 17509, 17569, 17586, 17618, 17645, 17647, 17706, 17713,
        17717, 17796, 17800, 17830, 17832, 17873, 18159, 18245, 18250, 18272, 18316, 18321,
        18335, 18341, 18482, 18545, 18552, 18569, 18575, 18643, 18777, 18815, 18825, 18838,
        18856, 18865, 18880, 18983, 18989, 19039, 19086, 19183, 19195, 19314, 19320, 19358,
        19379, 19382, 19464, 19474, 19570, 19594, 19616, 19626, 19632, 19642, 19751, 19752,
        19871, 19895, 19917, 19918, 20057, 20126, 20131, 20182, 20200, 20215, 20240, 20280,
        20393, 20748, 20773, 20822, 20870, 20889, 20993, 21195, 21243, 21631, 21692, 21717,
        21788, 21789, 21793, 21821, 21832, 22120, 22268, 22278, 22294, 22324, 22371, 22398,
        22438, 22568, 22609, 22708, 22748, 22793, 22822, 22861, 22993, 23010, 23145, 23659,
        23833, 23983, 23989, 24018, 24100, 24141, 24157, 24161, 24212, 24220, 24240, 24403,
        24412, 24446, 24531, 24763, 24812, 24856, 24858, 24870, 25076, 25162, 25290, 25326,
        25343, 25383, 25399, 25554, 25703, 25732, 25874, 25905, 25935, 26030, 26053, 26060,
        26304, 26400, 26599, 26636, 26755, 26766, 26787, 26875, 27029, 27109, 27316, 27331,
        27547, 27583, 27602, 27798, 27833, 27976, 27999, 28044, 28242, 28248, 28301, 28391,
        28426, 28591, 28604, 28630, 28656, 28737, 29000, 29055, 29094, 29310, 29332, 29487,
        29623, 29714, 29724, 29938, 30070, 30238, 30278, 30283, 30442, 30485, 30655, 30727,
        30765, 30833, 30867, 31148, 31300, 31656, 31700, 31805, 31901, 31947, 31991, 32172,
        32204, 32344, 32445, 32504, 32559, 32669, 32877, 33014, 33033, 33246, 33597, 33672,
        33915, 34123, 34125, 34189, 34283, 34297, 34371, 34409, 34426, 34488, 34607, 34675,
        34728, 34826, 34876, 34985, 35068, 35072, 35125, 35133, 35175, 35176, 35313, 35339,
        35424, 35449, 35472, 35511, 35555, 35770, 35860, 35886, 35929, 36025, 36047, 36058,
        36184, 36272, 36280, 36405, 36630, 36911, 36925, 37056, 37058, 37373, 37397, 37425,
        37513, 37554, 37725, 37902, 38137, 38191, 38319, 38392, 38396, 38425, 38509, 38610,
        38799, 38808, 38824, 38967, 39080, 39596, 39610, 39993, 40038, 40264, 40321, 40393,
        40617, 40627, 40857, 40984, 41027, 41151, 41472, 41481, 41588, 41641, 41690, 41754,
        41844, 42014, 42209, 42649, 42676, 43155, 43252, 43296, 43331, 43860, 43977, 44214,
        44430, 44592, 44745, 44952, 45108, 45109, 45197, 45804, 45829, 46103, 46142, 46400,
        46403, 46497, 46566, 46623, 46748, 47132, 47137, 47168, 47185, 47292, 48056, 48313,
        48417, 48436, 48795, 48822, 48880, 49704, 50132, 50344, 50567, 50951, 50967, 50985,
        51139, 51371, 51539, 51771, 51783, 51841, 51981, 52019, 52092, 52605, 52679, 52860,
        52875, 53171, 53453, 53568, 53648, 54156, 54252, 54496, 54644, 54654, 54655, 54722,
        54865, 54871, 54905, 55432, 55545, 55554, 55614, 55653, 56417, 56429, 56441, 56719,
        56833, 56841, 57043, 57096, 57423, 57498, 57532, 57563, 57677, 57709, 57743, 57905,
        57934, 58019, 58471, 58619, 59058, 59510, 59744, 59768, 59996, 60378, 60519, 60615,
        61142, 61159, 61225, 61328, 61370, 61516, 61611, 61665, 61845, 62447, 63079, 63395,
        63611, 63651, 63788, 63927, 64227, 64298, 64348, 64493, 64596, 64678, 64702, 64731,
        64928, 65205, 65428, 65642, 65659, 65794, 65847, 65890, 65933, 66223, 66790, 66933,
        67215, 67380, 67415, 67494, 67610, 67670, 67771, 68006, 68023, 68495, 68611, 68628,
        68918, 68984, 69340, 69589, 69650, 69935, 70312, 70342, 70428, 70452, 70845, 70945,
        71297, 71436, 71441, 71583, 71715, 71732, 72078, 72095, 72276, 72940, 72986, 73028,
        73073, 73185, 73840, 73881, 74096, 74295, 74675, 74838, 74919, 75135, 75161, 76064,
        76141, 76203, 76507, 76580, 76599, 76648, 76754, 76792, 76970, 76987, 77038, 77091,
        77147, 77160, 77452, 77605, 77640, 77670, 77702, 77779, 77883, 77892, 78003, 78107,
        78117, 78144, 78384, 78470, 78521, 78638, 78700, 78781, 78860, 78914, 78917, 78975,
        79001, 79037, 79192, 79354, 79464, 79509, 79534, 79539, 79553, 79626, 79687, 79756,
        79794, 79836, 79877, 79895, 80025, 80124, 80144, 80281, 80311, 80338, 80347, 80362,
        80367, 80416, 80423, 80620, 80661, 80693, 80724, 80750, 80799, 80871, 80878, 80883,
        82925, 83259, 83576, 83692, 83716, 83942, 84182, 84527, 84741, 84744, 84805, 85013,
        85127, 85204, 85283, 85316, 85345, 85412, 85466, 85505, 85765, 85807, 86005, 86078,
        86150, 86511, 86809, 86955, 86985, 87056, 87200, 87274, 87454, 87494, 87652, 87736,
        87749, 87753, 87810, 87832, 87895, 88010, 88150, 88163, 88193, 88195, 88202, 88222,
        88302, 88333, 88465, 88491, 88634, 88783, 88880, 88998, 89046, 89139, 89356, 89411,
        89426, 89550, 89564, 89580, 89695, 89716, 89869, 89954, 90173, 90176, 90215, 90343,
        90393, 90434, 90436, 90439, 90575, 90707, 90731, 90772, 90952, 91193, 91296, 91359,
        91391, 91417, 91493, 91569, 91585, 91610, 91636, 91860, 91947, 91985, 92060, 92166,
        92478, 92492, 92706, 92815, 93003, 93088, 93110, 93275, 93498, 93522, 93821, 93889,
        93951, 94092, 94357, 94362, 94476, 94489, 94562, 94629, 94660, 94674, 94750, 94800,
        94838, 94931, 95014, 95048, 95065, 95400, 97341, 98031, 98205, 98371, 98453, 98571,
        98608, 98656, 98838, 98864, 99067, 99088, 99331, 99444, 99446, 99630, 99639, 99733,
        99970, 100026, 100111, 100425, 100475, 100525, 100560, 100641, 100684, 100732, 100861, 100962,
        100982, 101028, 101074, 101134, 101314, 101324, 101549, 101628, 101870, 102259, 102549, 102569,
        102655, 102698, 103858, 103935, 104056, 104071, 104084, 104313, 104496, 104523, 105231, 105438,
        105498, 105736, 106657, 106677, 106690, 107075, 107103, 107519, 107758, 108495, 108550, 108632,
        108743, 108773, 109303, 109304, 109313, 109335, 109424, 109486, 109506, 109848, 111756, 111775,
        111777, 112224, 112399, 112451, 112457, 112460, 112498, 112624, 112627, 112761, 112798, 112801,
        112822, 112847, 112881, 112883, 112918, 112922, 112924, 112962, 112984, 113035, 113048, 113049,
        113059, 113064, 113066, 113152, 113177, 113189, 113214, 113242, 113287, 113307, 113375, 113399,
        113402, 113415, 113464, 113488, 113498, 113581, 113593, 113598, 113612, 113644, 113680, 113695,
        113718, 113951, 114003, 114446, 114993, 115003, 115052, 115102, 115155, 115156, 115201, 115315,
        115426, 115441, 115616, 115660, 115663, 115727, 115804, 115957, 116001, 116215, 116386, 116475,
        116481, 116584, 116631, 116635, 116649, 116735, 116797, 116808, 116835, 116848, 116924, 116942,
        116960, 116982, 117110, 117211, 117231, 117927, 117953, 118243, 118791, 118942, 119047, 119066,
        119106, 119282, 119415, 119425, 119531, 119758, 119819, 120239, 120248, 120257, 120337, 120695,
        120729, 120843, 121391, 121592, 121647, 121922, 121972, 122214, 122429, 122522, 122746, 122929,
        123140, 123141, 123158, 123383, 123408, 124178, 124495, 124630, 124963, 125699, 126264, 126956,
        127568, 127983, 128168, 128785, 128798, 129053, 129086, 129667, 130272, 130369, 130387, 130412,
        130711, 130771, 130922, 131084, 131234, 131376, 131505, 131632, 131669, 131876, 131974
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the BYOL source or matches its name without naming, using or comparing BYOL'
FROM byol_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING byol_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING byol_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- swav: 13 links, 787 exclusions. (799 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE swav_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'swav'
  AND p.id IN (
        3738, 5135, 6050, 6739, 8359, 9520, 9538, 9669, 11796, 18469, 91860, 98657, 114926
  );

DELETE FROM paper_method_exclusions x
USING swav_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM swav_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM swav_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE swav_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'swav'
  AND p.id IN (
        3516, 3697, 3718, 3885, 4000, 4074, 4238, 4243, 4247, 4324, 4481, 4588,
        4591, 4612, 4625, 4710, 4767, 4996, 5004, 5020, 5030, 5034, 5144, 5188,
        5235, 5320, 5336, 5378, 5395, 5450, 5562, 5583, 5606, 5612, 5672, 5699,
        5880, 5947, 5990, 6003, 6084, 6263, 6374, 6520, 6539, 6549, 6605, 6750,
        6861, 6871, 6888, 6916, 7001, 7073, 7125, 7209, 7216, 7218, 7283, 7347,
        7385, 7420, 7456, 7475, 7519, 7547, 7550, 7739, 7888, 7896, 7990, 8027,
        8188, 8213, 8237, 8268, 8374, 8404, 8444, 8446, 8469, 8487, 8515, 8529,
        8628, 8644, 8720, 8725, 8986, 9028, 9099, 9235, 9253, 9272, 9278, 9285,
        9347, 9441, 9491, 9567, 9573, 9635, 9637, 9650, 9716, 9766, 9786, 9806,
        9809, 9816, 9848, 9872, 9877, 10197, 10209, 10244, 10377, 10387, 10399, 10431,
        10438, 10520, 10583, 10591, 10695, 10739, 10761, 10814, 10848, 10911, 10991, 11002,
        11090, 11130, 11154, 11305, 11324, 11359, 11392, 11434, 11501, 11545, 11852, 11885,
        11944, 11968, 11975, 12099, 12283, 12297, 12304, 12308, 12312, 12331, 12356, 12385,
        12452, 12546, 12559, 12618, 12875, 12891, 13019, 13215, 13216, 13292, 13387, 13478,
        13519, 13569, 13572, 13610, 13611, 13624, 13646, 13816, 13828, 13845, 13899, 13917,
        13949, 13990, 14019, 14068, 14072, 14077, 14132, 14191, 14193, 14232, 14276, 14288,
        14299, 14318, 14350, 14369, 14419, 14423, 14425, 14508, 14576, 14636, 14640, 14669,
        14709, 14786, 14824, 14857, 14880, 14899, 14916, 15016, 15075, 15097, 15115, 15321,
        15566, 15576, 15637, 15810, 16239, 16258, 16289, 16359, 16495, 16646, 16950, 17119,
        17186, 17205, 17384, 17505, 17559, 17586, 17645, 17796, 17800, 17832, 18159, 18245,
        18250, 18335, 18396, 18413, 18482, 18501, 18545, 18552, 18575, 18577, 18633, 18683,
        18767, 18825, 18865, 18983, 19086, 19183, 19195, 19208, 19314, 19320, 19379, 19464,
        19582, 19594, 19642, 19659, 19688, 19761, 19808, 19871, 19877, 19895, 20057, 20065,
        20126, 20182, 20240, 20280, 20422, 20646, 20784, 20913, 21034, 21146, 21195, 21605,
        21631, 21797, 21832, 21911, 22026, 22143, 22278, 22294, 22609, 23010, 23145, 23174,
        23216, 23308, 23364, 23512, 23807, 23954, 23983, 23989, 24018, 24161, 24240, 24412,
        24446, 24749, 24858, 24870, 24886, 24934, 24991, 25027, 25076, 25234, 25290, 25326,
        25335, 25383, 25713, 25820, 25874, 25937, 26030, 26053, 26257, 26304, 26462, 26766,
        26787, 26875, 27029, 27188, 27519, 27547, 28044, 28130, 28248, 28279, 28301, 28503,
        28591, 28604, 28642, 28865, 28882, 28897, 28988, 29055, 29094, 29526, 29598, 29811,
        29938, 30196, 30236, 30278, 30283, 30364, 30703, 30727, 30833, 30867, 30927, 31187,
        31656, 31672, 31700, 32145, 32877, 33197, 34398, 34607, 34728, 34764, 34816, 34826,
        34985, 34998, 35043, 35153, 35175, 35176, 35309, 35313, 35317, 35423, 35449, 35472,
        35493, 35860, 35886, 35943, 36047, 36058, 36138, 36184, 36228, 36280, 36405, 36737,
        37513, 37554, 37636, 37988, 38396, 38799, 38806, 38808, 38824, 39080, 39875, 40000,
        40264, 40321, 40393, 40423, 40615, 40617, 40857, 41215, 42014, 42649, 42676, 43155,
        44116, 44214, 44367, 44592, 44745, 45252, 45306, 45378, 45662, 45722, 45742, 46291,
        46403, 46497, 46731, 47185, 47307, 47335, 48056, 48417, 48436, 48704, 48822, 49186,
        49275, 49963, 50951, 51371, 51539, 51771, 51783, 51981, 52074, 52307, 52606, 52679,
        52860, 53679, 53835, 54045, 54094, 54252, 54722, 54850, 55314, 55432, 55613, 55653,
        56441, 56841, 56920, 56996, 57043, 57096, 57532, 58335, 58976, 59744, 60143, 60354,
        60835, 61370, 61665, 63250, 63927, 64298, 64557, 64666, 64678, 64731, 65642, 65794,
        65836, 65892, 66052, 66790, 67187, 67205, 68006, 68495, 68611, 69177, 69866, 69935,
        70312, 70945, 71297, 71715, 73197, 73280, 73561, 73644, 74096, 74258, 74353, 74774,
        75119, 75135, 75414, 75493, 75528, 75671, 75869, 76139, 76203, 76351, 76468, 76754,
        76929, 76987, 77091, 77443, 77651, 77702, 77892, 78038, 78107, 78166, 78259, 78384,
        78396, 78646, 78917, 79001, 79037, 79139, 79192, 79233, 79467, 79509, 79831, 79838,
        79895, 80025, 80106, 80144, 80338, 80347, 80416, 80490, 80564, 80620, 80661, 80693,
        80799, 80871, 81059, 83576, 83942, 84212, 84741, 84797, 84865, 84878, 85013, 85168,
        85505, 85643, 86150, 86357, 86511, 86844, 87200, 87274, 87652, 87736, 87749, 87895,
        88055, 88163, 88195, 88222, 88307, 88333, 88346, 88360, 88491, 88783, 88880, 89139,
        89359, 89491, 89733, 89954, 90060, 90145, 90173, 90176, 90215, 90372, 90401, 90548,
        90550, 90624, 90707, 90836, 90955, 91296, 91324, 91569, 91585, 91636, 91811, 91939,
        91985, 92162, 92281, 92320, 92969, 93275, 93446, 93447, 93522, 93600, 93713, 93889,
        94092, 94282, 94357, 94660, 94674, 94800, 94931, 95798, 96118, 96621, 97341, 97679,
        98031, 98453, 98570, 98608, 98650, 98733, 99006, 99546, 99630, 100732, 100806, 101074,
        101306, 102476, 102549, 103858, 103935, 103937, 104056, 104496, 105175, 105504, 105684, 106658,
        106690, 106776, 106861, 106932, 107032, 107823, 108291, 108495, 109472, 111756, 112134, 112360,
        112504, 112521, 112801, 112870, 112883, 112899, 112924, 112962, 113059, 113066, 113110, 113117,
        113146, 113152, 113177, 113189, 113208, 113287, 113307, 113415, 113424, 113540, 113581, 113644,
        113658, 113718, 114386, 114446, 115003, 115616, 115727, 115779, 115827, 115875, 115942, 115957,
        116001, 116097, 116139, 116215, 116243, 116475, 116479, 116558, 116631, 116635, 116649, 116797,
        116835, 117003, 117046, 117084, 117110, 117231, 117415, 117784, 117830, 117927, 118240, 118764,
        118942, 119047, 119106, 119758, 119772, 120094, 120248, 120257, 120299, 120337, 120410, 120472,
        120512, 120578, 120729, 121102, 121391, 121592, 121922, 122214, 123140, 123158, 123910, 126956,
        127189, 127211, 128168, 128785, 130182, 130369, 131974
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the SwAV source or matches its name without naming, using or comparing SwAV'
FROM swav_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING swav_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING swav_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- barlow-twins: 16 links, 413 exclusions. (427 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE barlow_twins_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'barlow-twins'
  AND p.id IN (
        5144, 9567, 13828, 14191, 21631, 24240, 25610, 35402, 68611, 84047, 84913, 93275, 93522, 97638, 102706, 113350
  );

DELETE FROM paper_method_exclusions x
USING barlow_twins_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM barlow_twins_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM barlow_twins_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE barlow_twins_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'barlow-twins'
  AND p.id IN (
        4074, 4710, 5098, 5606, 5672, 5699, 5880, 6539, 6888, 6916, 7000, 7001,
        7119, 7124, 7209, 7218, 7347, 7519, 7561, 7764, 7888, 7905, 7910, 7990,
        8027, 8152, 8188, 8225, 8374, 8380, 8529, 8720, 8805, 8884, 9028, 9235,
        9272, 9278, 9650, 9716, 9766, 9774, 9786, 9806, 10387, 10520, 10563, 10589,
        10591, 10814, 11130, 11136, 11154, 11305, 11324, 11419, 11476, 11486, 11553, 11564,
        11573, 11695, 11796, 11852, 11881, 11885, 11944, 12031, 12290, 12312, 12356, 12452,
        12598, 12618, 12847, 12891, 12914, 12990, 13178, 13216, 13273, 13350, 13519, 13744,
        13747, 13899, 13917, 13990, 14152, 14178, 14419, 14438, 14669, 14725, 14786, 14916,
        15092, 15115, 15270, 15485, 15566, 15657, 15810, 16359, 16773, 16949, 17068, 17154,
        17205, 17505, 17595, 17645, 18159, 18245, 18335, 18469, 18552, 18575, 18609, 18767,
        18815, 18838, 18959, 19320, 19379, 19626, 19721, 19824, 20073, 20280, 20526, 20877,
        21065, 21206, 21717, 21821, 22748, 22993, 23010, 23031, 23308, 23420, 23512, 23659,
        23989, 24100, 24412, 24446, 24531, 25383, 25874, 25905, 26030, 26095, 26545, 26766,
        27316, 27491, 27562, 28242, 28248, 28301, 28604, 28656, 28909, 29000, 29055, 29094,
        30238, 30703, 30727, 30833, 31148, 31656, 31700, 31805, 32670, 33014, 33187, 34297,
        34426, 35175, 35176, 35423, 35424, 35449, 35667, 35848, 35886, 36058, 36274, 36405,
        37058, 37260, 37674, 37725, 37902, 37988, 39080, 39313, 39610, 40302, 40321, 41151,
        41588, 42649, 43301, 45888, 46142, 46403, 46451, 47335, 48429, 48436, 48822, 49151,
        50951, 51539, 55432, 56429, 56944, 57709, 57934, 58619, 59812, 59848, 60378, 60953,
        61328, 61370, 61516, 61845, 62844, 65205, 65794, 65847, 65890, 65933, 66746, 67187,
        67494, 68006, 68495, 68628, 69935, 69987, 71441, 72078, 72095, 72495, 72986, 73185,
        74675, 74849, 74903, 75590, 76401, 76813, 77091, 77147, 77659, 77883, 77892, 78117,
        78396, 78781, 78917, 79001, 79070, 79588, 79836, 79877, 80620, 80693, 80810, 80871,
        84527, 84556, 85013, 85505, 86005, 86150, 86357, 86425, 86776, 86809, 86828, 87200,
        87274, 87736, 88039, 88333, 88491, 88552, 88783, 88880, 88998, 89550, 89580, 89716,
        89733, 89954, 90060, 90439, 90707, 90952, 91115, 91272, 91391, 91408, 91636, 91981,
        93059, 93447, 93821, 93889, 93951, 94115, 94357, 94476, 94664, 94800, 95014, 95798,
        96652, 98453, 98570, 98571, 99190, 99630, 99639, 99737, 100425, 100641, 100684, 100780,
        101266, 101324, 101549, 101570, 101803, 101870, 102007, 102106, 102124, 102142, 102655, 103954,
        104071, 104099, 104112, 104121, 104496, 105438, 105595, 106690, 107078, 107253, 108773, 108949,
        109304, 109486, 109848, 111777, 112450, 112530, 112801, 112883, 112963, 113110, 113152, 113177,
        113307, 113415, 113581, 113644, 113718, 113951, 114386, 114446, 115059, 115349, 115508, 115727,
        115855, 116238, 116401, 117230, 117867, 117927, 119047, 119106, 120014, 121391, 121922, 122014,
        122247, 122522, 122822, 122929, 123140, 123141, 123158, 124176, 125699, 126253, 126264, 127451,
        130228, 130302, 130369, 130711, 131672
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the Barlow Twins source or matches its name without naming, using or comparing Barlow Twins'
FROM barlow_twins_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING barlow_twins_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING barlow_twins_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- alibi: 21 links, 619 exclusions. (636 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE alibi_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'alibi'
  AND p.id IN (
        6499, 16633, 20697, 22248, 22861, 25310, 32990, 36075, 39097, 42109, 45843, 50045, 51139, 54645, 58448, 74468,
        74927, 108680, 124464, 126960, 129369
  );

DELETE FROM paper_method_exclusions x
USING alibi_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM alibi_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM alibi_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE alibi_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'alibi'
  AND p.id IN (
        5541, 5803, 6171, 7166, 7466, 7508, 7583, 7672, 8269, 8499, 8575, 8882,
        9000, 9074, 9212, 9227, 9691, 9750, 9845, 10003, 10189, 10375, 10578, 10618,
        10765, 11098, 11102, 11281, 11388, 11410, 11495, 11948, 11975, 12033, 12073, 12152,
        12156, 12263, 12285, 12489, 12890, 12952, 13039, 13175, 13291, 13307, 13916, 13946,
        14308, 14349, 14502, 14973, 15100, 15816, 15904, 15941, 15976, 16013, 16142, 16225,
        16251, 16317, 16331, 16366, 16374, 16550, 16618, 16684, 16794, 16818, 16820, 16871,
        17118, 17136, 17241, 17306, 17424, 17455, 17791, 17805, 17810, 17819, 18067, 18189,
        18201, 18415, 18484, 18610, 18706, 18838, 18858, 19227, 19577, 19748, 19864, 19943,
        19945, 19997, 20124, 20164, 20173, 20498, 20598, 20602, 20605, 20635, 20670, 20693,
        20742, 20998, 21113, 21167, 21179, 21258, 21352, 21406, 21458, 21548, 21565, 21570,
        21571, 21592, 21635, 21744, 21846, 21903, 22063, 22374, 22492, 22521, 22532, 22736,
        22784, 22866, 22978, 22994, 23102, 23140, 23142, 23283, 23346, 23382, 23593, 23609,
        23646, 23736, 24127, 24143, 24297, 24397, 24494, 24607, 24672, 24679, 24754, 24756,
        25139, 25165, 25199, 25315, 25354, 25411, 25466, 25520, 25568, 25624, 25639, 25673,
        25717, 25788, 25791, 25793, 25802, 25831, 25832, 26093, 26319, 26341, 26348, 26438,
        26618, 26748, 26971, 26973, 27015, 27111, 27326, 27342, 27375, 27380, 27430, 27518,
        27577, 27707, 27722, 27740, 27910, 27967, 27979, 28020, 28030, 28061, 28077, 28087,
        28221, 28476, 28539, 28597, 28824, 28860, 29119, 29156, 29838, 29851, 29957, 29994,
        30152, 30160, 30170, 30187, 30347, 30520, 30742, 30791, 31192, 31329, 31407, 31549,
        31652, 31783, 31839, 31844, 31871, 31891, 31970, 32072, 32187, 32278, 32293, 32297,
        32313, 32334, 32381, 32533, 32633, 32680, 32729, 32730, 32731, 32852, 32962, 33164,
        33279, 33341, 33377, 33410, 33483, 33534, 33652, 33664, 33766, 34041, 34057, 34059,
        34098, 34115, 34570, 34786, 34853, 35013, 35040, 35080, 35280, 35360, 35487, 35547,
        35720, 35725, 35889, 36155, 36325, 36399, 36453, 36520, 36651, 36665, 36742, 36745,
        36795, 36931, 37051, 37273, 37419, 37655, 37733, 37783, 37795, 37807, 37857, 37896,
        37903, 37938, 37947, 37981, 38102, 38134, 38154, 38168, 38401, 38459, 39108, 39126,
        39173, 39467, 39679, 39822, 40093, 40207, 40512, 41167, 41285, 41465, 41487, 41936,
        42004, 42214, 42370, 42374, 42392, 42579, 42783, 42974, 43437, 43482, 43483, 43584,
        43716, 43869, 44203, 44701, 44803, 44808, 45302, 45389, 45455, 45513, 45561, 46701,
        46990, 47345, 48312, 48314, 48348, 48352, 48359, 48463, 48654, 48763, 48957, 49089,
        49304, 49305, 49400, 49472, 49505, 49793, 49972, 50432, 50493, 50536, 51214, 51240,
        51777, 51961, 52216, 52539, 52816, 53154, 53225, 53633, 53673, 53786, 53800, 53816,
        53959, 54190, 54358, 54359, 54625, 54819, 54852, 54911, 55092, 55154, 55349, 55984,
        56024, 56231, 56252, 56297, 56538, 56685, 57025, 58401, 58402, 58515, 58844, 59054,
        59246, 59725, 59734, 60060, 60365, 60589, 60652, 60698, 60831, 61300, 61400, 61402,
        61519, 61663, 62224, 62230, 62401, 62620, 62636, 62941, 63249, 63552, 63681, 63770,
        64022, 64185, 64555, 64727, 65592, 66038, 66270, 66442, 67164, 67477, 67953, 68047,
        68186, 68202, 68256, 68340, 68360, 68687, 68693, 68736, 69291, 69350, 69651, 69951,
        70094, 70258, 70377, 70514, 70636, 70981, 71070, 71104, 71398, 71427, 71476, 71998,
        72023, 72096, 72152, 72195, 72293, 72715, 72730, 73001, 73370, 73416, 73473, 73641,
        73898, 74622, 74918, 74942, 76219, 76243, 76619, 76988, 77073, 77890, 79000, 83123,
        83155, 83346, 83488, 83648, 84209, 85115, 85367, 86026, 86320, 86515, 86558, 86693,
        86769, 86770, 86878, 87008, 87203, 87429, 88783, 88804, 88817, 88892, 88938, 89515,
        89518, 89709, 89805, 90828, 90951, 91031, 91159, 91356, 91422, 91512, 91671, 92145,
        92187, 92295, 92900, 92985, 93237, 93344, 93696, 94146, 94485, 94560, 94594, 94722,
        94819, 94852, 98055, 99167, 99282, 99908, 99910, 100328, 101177, 101562, 101606, 101826,
        101885, 101902, 101978, 102186, 102321, 102713, 102771, 102819, 102904, 103060, 103364, 103771,
        104413, 105850, 105937, 107538, 107952, 108147, 108394, 108548, 108794, 108958, 109652, 109994,
        110281, 110416, 110637, 110799, 110916, 111075, 111803, 112807, 113667, 113968, 116124, 116261,
        117257, 117716, 117750, 119414, 119634, 122108, 122240, 122345, 122451, 122690, 122701, 122955,
        123531, 123835, 124017, 124214, 124431, 125980, 126687, 127024, 127627, 128685, 129241, 129246,
        129488, 129975, 130794, 131106, 131570, 131855, 132000
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the ALiBi source or matches its name without naming, using or comparing ALiBi'
FROM alibi_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING alibi_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING alibi_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- yarn: 14 links, 489 exclusions. (498 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE yarn_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'yarn'
  AND p.id IN (
        19997, 25793, 28221, 38691, 48957, 54323, 66270, 68186, 68693, 73307, 85645, 92725, 94594, 109685
  );

DELETE FROM paper_method_exclusions x
USING yarn_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM yarn_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM yarn_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE yarn_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'yarn'
  AND p.id IN (
        14739, 14987, 18201, 18484, 20605, 20742, 20910, 20998, 21039, 21113, 21167, 21258,
        21592, 21744, 22060, 22061, 22248, 22423, 22532, 22866, 22994, 23593, 24680, 24756,
        24779, 25269, 25411, 25551, 25568, 25641, 25827, 25860, 26543, 26675, 26701, 26748,
        26908, 26971, 27015, 27326, 27520, 27609, 27742, 27766, 27771, 27967, 28065, 28349,
        28407, 28539, 29437, 29851, 30143, 30160, 30187, 30249, 30309, 30410, 30493, 30511,
        30791, 31103, 31121, 31150, 31176, 31181, 31201, 31503, 31504, 31599, 31678, 31783,
        31797, 31844, 31871, 31891, 32190, 32231, 32297, 32533, 32686, 32731, 32935, 32959,
        33153, 33183, 33226, 33410, 33417, 33443, 33483, 33487, 33555, 33610, 33720, 33732,
        33753, 33984, 34059, 34225, 34500, 34570, 34654, 34774, 34973, 35013, 35547, 35644,
        35743, 35810, 36075, 36089, 36273, 36289, 36399, 36453, 36530, 36666, 36745, 37054,
        37100, 37280, 37464, 37530, 37538, 37724, 37783, 37789, 37795, 37947, 38001, 38085,
        38180, 38401, 38420, 38768, 38893, 38905, 39108, 39173, 39878, 40181, 40212, 40231,
        40337, 41115, 41150, 41285, 41340, 41487, 41574, 41814, 42004, 42109, 42195, 42221,
        42374, 42476, 42563, 42669, 42934, 43097, 43233, 43254, 43437, 43618, 43674, 43846,
        43850, 44182, 44277, 44332, 44385, 44494, 44598, 44670, 44701, 44803, 44858, 44880,
        44943, 45050, 45102, 45145, 45169, 45205, 45302, 45535, 45843, 46003, 46397, 46701,
        47209, 47427, 47432, 47568, 48053, 48589, 48725, 49098, 49400, 49500, 49571, 49741,
        49776, 49948, 49990, 50206, 50352, 50366, 50493, 50563, 50791, 51046, 51072, 51139,
        51214, 51275, 51641, 51750, 51777, 51898, 52071, 52212, 52215, 52245, 52303, 52467,
        52534, 52816, 52863, 53027, 53134, 53204, 53224, 53329, 53379, 53385, 53413, 53516,
        53591, 53628, 53673, 53714, 53746, 53786, 53806, 53816, 53959, 53972, 53996, 54016,
        54317, 54359, 54457, 54543, 54571, 54625, 54645, 54653, 54804, 54805, 54939, 54971,
        55101, 55222, 55226, 55253, 55269, 55469, 55572, 55579, 55581, 55644, 55657, 55718,
        55805, 55884, 55953, 56004, 56024, 56025, 56029, 56068, 56265, 56355, 56409, 56440,
        56730, 57051, 57237, 57286, 57338, 57496, 57547, 57791, 58164, 58342, 58369, 58402,
        58515, 58621, 58928, 59193, 59197, 59259, 60013, 60101, 60246, 60460, 60581, 60652,
        60831, 60995, 61199, 61292, 61400, 61762, 62167, 62620, 62968, 63180, 63201, 63444,
        63681, 63770, 63904, 64232, 64727, 64999, 65592, 65695, 65815, 65852, 65869, 66075,
        66442, 66821, 67467, 67523, 67627, 67692, 67851, 68340, 68431, 68465, 68687, 68803,
        69004, 69209, 69349, 69386, 69958, 70648, 71130, 71160, 71405, 71476, 71812, 73038,
        73116, 73370, 73658, 73898, 75042, 75122, 76063, 76614, 77001, 77513, 83111, 83117,
        83142, 83300, 83379, 83488, 83513, 83591, 83608, 83726, 83730, 83768, 84954, 85164,
        85367, 85664, 85934, 86245, 86298, 86558, 86693, 86744, 86781, 87008, 87258, 87507,
        88695, 88843, 89518, 89805, 89824, 90594, 91422, 91470, 91575, 91668, 91738, 92787,
        92933, 93533, 94146, 94410, 94560, 94604, 94685, 94722, 94819, 94852, 95093, 98016,
        98420, 98807, 98810, 99033, 99077, 99431, 99641, 99757, 99910, 100298, 100328, 100724,
        101308, 101562, 101693, 101885, 101984, 102320, 102331, 102637, 102713, 102819, 102986, 103825,
        104413, 104584, 104738, 107512, 107862, 107945, 108794, 108958, 110011, 110916, 111054, 111088,
        113947, 114096, 114175, 117716, 119280, 121349, 121993, 122258, 122321, 122323, 122488, 122701,
        122842, 123022, 123266, 123428, 123475, 123531, 123618, 124255, 124342, 124634, 125176, 125356,
        125523, 125741, 125891, 129488, 129918, 130040, 130259, 131855, 132058
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the YaRN source or matches its name without naming, using or comparing YaRN'
FROM yarn_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING yarn_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING yarn_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- rwkv: 76 links, 489 exclusions. (535 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE rwkv_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rwkv'
  AND p.id IN (
        13338, 15904, 17159, 26784, 27085, 28164, 28380, 30017, 30106, 30112, 31201, 31770, 32673, 33809, 34266, 34703,
        34784, 35210, 36192, 36442, 36546, 37527, 38032, 38134, 38180, 39410, 40166, 41583, 41900, 43270, 44207, 45661,
        46339, 47282, 47541, 47934, 48261, 48427, 48654, 50141, 51130, 58038, 61575, 66674, 70756, 72925, 73298, 73669,
        75193, 76452, 83858, 84001, 85381, 89558, 90167, 90821, 91356, 91667, 96155, 100332, 105809, 107293, 107564, 108183,
        108519, 108806, 111811, 117978, 119435, 125244, 125328, 126436, 127867, 128837, 130896, 131792
  );

DELETE FROM paper_method_exclusions x
USING rwkv_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rwkv_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM rwkv_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE rwkv_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rwkv'
  AND p.id IN (
        12243, 14349, 14868, 16794, 17744, 17862, 18173, 18325, 18418, 18531, 18706, 19227,
        19496, 19836, 20089, 20157, 20368, 20383, 20397, 20670, 20693, 20847, 21022, 21072,
        22470, 22768, 22943, 23104, 23185, 23720, 24017, 24028, 24127, 24135, 24143, 24494,
        24607, 24792, 24952, 25107, 25165, 25269, 25296, 25364, 25366, 25466, 25624, 25717,
        25761, 25843, 25999, 26201, 26379, 26455, 26591, 26618, 26693, 26701, 26748, 26795,
        26898, 26932, 26994, 27111, 27329, 27425, 27438, 27517, 27740, 27861, 27917, 28183,
        28208, 28267, 28328, 28476, 28689, 28750, 28787, 28841, 28874, 28987, 29124, 29295,
        29333, 29649, 29658, 29851, 29900, 30099, 30160, 30214, 30239, 30309, 30335, 30647,
        30753, 30791, 31180, 31181, 31192, 31265, 31288, 31364, 31375, 31387, 31524, 31545,
        31599, 31618, 31643, 31715, 31776, 31790, 31839, 31949, 32129, 32136, 32143, 32311,
        32445, 32475, 32601, 32636, 32733, 32743, 32843, 32959, 33191, 33221, 33410, 33458,
        33496, 33544, 33575, 33594, 33607, 33873, 33947, 33962, 33987, 33990, 34059, 34212,
        34225, 34267, 34286, 34322, 34500, 34811, 34917, 34961, 35050, 35080, 35182, 35186,
        35194, 35424, 35858, 35878, 35979, 36126, 36289, 36398, 36411, 36691, 36703, 37259,
        37594, 37628, 37783, 37795, 37908, 37938, 37947, 38052, 38261, 38327, 38420, 38558,
        38658, 38684, 38691, 38755, 39014, 39155, 39193, 39210, 39225, 39235, 39396, 39546,
        39612, 39667, 39977, 40093, 40231, 40316, 40378, 40512, 40554, 40674, 40695, 40786,
        41140, 41231, 41242, 41543, 41991, 42004, 42370, 42371, 42374, 42592, 42603, 42635,
        42669, 42784, 42822, 42974, 43031, 43112, 43233, 43315, 43729, 43904, 44033, 44228,
        44283, 44463, 44474, 44527, 44534, 44911, 44942, 45178, 45205, 45332, 45491, 45566,
        45620, 45817, 46003, 46171, 46266, 46459, 46681, 46879, 46964, 46975, 47348, 47404,
        47568, 47677, 47844, 47874, 48121, 48352, 48897, 49098, 49134, 49691, 49746, 49893,
        49894, 50146, 50204, 50616, 50634, 50884, 50897, 51066, 51156, 51316, 51326, 51341,
        51586, 51638, 51641, 51767, 51777, 51779, 51844, 51856, 52077, 52991, 53320, 53451,
        53998, 54288, 54423, 54441, 54734, 54753, 54911, 55076, 55080, 55223, 55253, 56068,
        56151, 56187, 56253, 56268, 56366, 56732, 57166, 57186, 57659, 58134, 58164, 58377,
        58456, 58639, 58998, 59127, 59401, 59504, 59888, 60204, 60246, 60460, 61304, 61324,
        61551, 61763, 62375, 62620, 63065, 63247, 63398, 63965, 64053, 64678, 65252, 65417,
        65462, 65536, 65592, 65676, 65955, 66619, 66819, 67126, 67546, 67627, 68340, 68703,
        70101, 70710, 70751, 70794, 70874, 71208, 71237, 71405, 71476, 72023, 72229, 72575,
        72660, 73288, 73370, 73416, 73608, 73723, 73767, 73812, 74055, 74110, 74128, 74207,
        74468, 74968, 75350, 75778, 76294, 76757, 77103, 77371, 77441, 77670, 78268, 78613,
        78617, 79447, 80788, 83167, 83579, 83648, 83730, 84497, 84980, 86019, 86250, 86515,
        86770, 86922, 87429, 88210, 88225, 88234, 88367, 88647, 89131, 90549, 90713, 90722,
        91053, 91209, 91709, 91910, 92109, 92495, 92565, 93020, 93097, 93153, 93352, 93507,
        94119, 94132, 94213, 94218, 94267, 94485, 94722, 94753, 96283, 98699, 98807, 98936,
        99077, 99534, 100244, 102367, 102381, 102407, 103201, 105928, 106012, 107249, 107794, 107945,
        108955, 109187, 109592, 109709, 110011, 110282, 110916, 111713, 113748, 113788, 113865, 114111,
        118984, 119002, 119534, 119676, 119969, 120008, 121988, 122132, 122508, 122647, 122700, 122709,
        122818, 123521, 123996, 124259, 124517, 124922, 125297, 125695, 125980, 126188, 127021, 128047,
        128083, 128827, 129260, 130549, 130569, 130649, 131751, 131816, 131958
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the RWKV source or matches its name without naming, using or comparing RWKV'
FROM rwkv_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING rwkv_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING rwkv_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- retnet: 17 links, 387 exclusions. (402 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE retnet_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'retnet'
  AND p.id IN (
        18325, 20281, 20693, 22938, 24607, 25382, 27053, 27085, 28267, 34267, 35210, 58448, 61464, 71974, 85030, 89122,
        112807
  );

DELETE FROM paper_method_exclusions x
USING retnet_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM retnet_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM retnet_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE retnet_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'retnet'
  AND p.id IN (
        14349, 14868, 18484, 18531, 18629, 19957, 20089, 20444, 21402, 21744, 21846, 22127,
        22768, 22943, 23720, 24135, 24143, 24402, 25165, 25296, 25585, 25624, 25717, 25843,
        25947, 25999, 26201, 26618, 26701, 26748, 26932, 27033, 27220, 27329, 27375, 27917,
        28065, 28155, 28183, 28208, 28328, 28380, 28381, 28689, 28750, 28874, 29333, 29476,
        29649, 29883, 29900, 30106, 30160, 30239, 30647, 30687, 31150, 31192, 31201, 31288,
        31545, 31618, 31715, 31770, 31776, 31790, 31842, 31949, 32136, 32143, 32278, 32475,
        32601, 32636, 32729, 32843, 33221, 33458, 33594, 33987, 34059, 34225, 34275, 34322,
        34500, 34608, 34784, 34961, 35194, 35424, 35547, 35644, 35979, 36126, 36289, 36766,
        37458, 37464, 37628, 37783, 37908, 38134, 38180, 38327, 38420, 38691, 39008, 39114,
        39410, 39546, 39612, 40231, 40316, 40674, 40695, 41231, 41543, 41603, 41719, 41891,
        41900, 41991, 42370, 42371, 42592, 42737, 43295, 43582, 43639, 44033, 44207, 44343,
        44534, 44579, 44911, 45011, 45205, 45224, 45332, 45389, 45488, 45491, 45620, 46059,
        46190, 46266, 46270, 46459, 46681, 46858, 46964, 47220, 47345, 47404, 47541, 47859,
        47874, 48352, 48427, 49098, 49741, 49894, 50146, 50179, 50609, 50634, 50884, 51066,
        51156, 51496, 51616, 51766, 51779, 51784, 52077, 52991, 52997, 53079, 53164, 53320,
        53326, 53744, 53800, 53959, 53998, 54423, 54441, 54687, 54734, 54758, 54911, 55076,
        55223, 55595, 55705, 56178, 56187, 56213, 56255, 56268, 56337, 56366, 56514, 56585,
        56612, 56613, 56646, 56730, 56732, 57153, 57286, 58515, 59313, 59401, 59504, 59739,
        60460, 61324, 61429, 61461, 61541, 61719, 63065, 63398, 63858, 63904, 63965, 64185,
        64495, 64727, 65252, 65417, 65462, 65536, 65723, 65955, 66298, 66619, 66819, 66952,
        67164, 67245, 67546, 67978, 68443, 68685, 68736, 68759, 69346, 69838, 70229, 70710,
        70874, 71405, 71476, 71875, 72229, 72575, 72670, 73116, 73216, 73298, 73416, 73812,
        73954, 73996, 74102, 74110, 74468, 74524, 74539, 74968, 75122, 75350, 75712, 76116,
        77371, 77670, 78441, 78613, 82916, 82940, 83167, 83180, 83300, 83579, 83730, 83960,
        85650, 86000, 86250, 86515, 86770, 86867, 87413, 88225, 88367, 88639, 88647, 89085,
        89131, 89720, 89824, 90713, 90722, 90734, 91709, 91910, 92109, 92495, 92565, 92959,
        93020, 93152, 93153, 93222, 93507, 93679, 94000, 94132, 94485, 94722, 96283, 98496,
        98699, 98936, 99168, 99817, 99940, 101440, 101562, 101567, 101652, 102218, 102381, 102544,
        103201, 105913, 105928, 105937, 105957, 106012, 107249, 108433, 108806, 108955, 109134, 109187,
        109532, 110282, 113748, 113788, 113865, 115252, 116483, 117802, 120008, 122121, 122286, 122508,
        122647, 122661, 122700, 122887, 122919, 122955, 123521, 123968, 123996, 124662, 125297, 125695,
        125980, 126188, 126660, 127627, 128047, 128499, 128719, 128827, 129260, 130549, 130569, 131032,
        131751, 131958, 132014
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the RetNet source or matches its name without naming, using or comparing RetNet'
FROM retnet_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING retnet_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING retnet_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- s4: 45 links, 977 exclusions. (998 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE s4_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 's4'
  AND p.id IN (
        7110, 8017, 8439, 9590, 9594, 9626, 10011, 10867, 12216, 13546, 13671, 14132, 14453, 17158, 18016, 18531,
        21282, 21394, 22765, 22938, 27387, 28183, 29333, 29398, 30753, 31183, 37751, 46133, 46681, 72802, 73132, 86066,
        87330, 87434, 88914, 91053, 91347, 91500, 92516, 92519, 92520, 99279, 128091, 128670, 129975
  );

DELETE FROM paper_method_exclusions x
USING s4_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM s4_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM s4_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE s4_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 's4'
  AND p.id IN (
        4143, 6016, 7976, 9166, 9239, 9767, 9808, 9845, 9947, 10189, 10201, 10375,
        10562, 10565, 10573, 10677, 10712, 10818, 11281, 12148, 12244, 12393, 12518, 12556,
        12661, 12999, 13048, 13073, 13140, 13158, 13231, 13665, 13833, 14472, 14868, 15150,
        15475, 15824, 15904, 15956, 16033, 16340, 16356, 16612, 16624, 16639, 16884, 17270,
        17424, 17502, 17507, 17513, 17604, 17647, 17828, 17880, 17928, 18037, 18067, 18325,
        18396, 18511, 18706, 19132, 20089, 20391, 20397, 20447, 20736, 20847, 20998, 21022,
        21085, 21404, 21846, 22180, 22200, 22443, 22470, 22711, 22768, 22796, 22960, 23160,
        23347, 23537, 23593, 23720, 24017, 24127, 24143, 24177, 24382, 24494, 24545, 24596,
        24607, 24642, 24792, 24919, 24952, 25063, 25165, 25269, 25285, 25585, 25630, 25843,
        25947, 25999, 26201, 26248, 26285, 26376, 26446, 26517, 26536, 26591, 26618, 26701,
        26748, 26770, 26784, 26842, 26932, 26947, 26971, 26994, 27048, 27073, 27085, 27111,
        27161, 27272, 27438, 27608, 27918, 27927, 28030, 28065, 28154, 28155, 28208, 28219,
        28238, 28259, 28267, 28328, 28335, 28353, 28380, 28449, 28453, 28485, 28502, 28607,
        28668, 28689, 28705, 28717, 28731, 28787, 28850, 28860, 28874, 28899, 28984, 29200,
        29214, 29264, 29476, 29490, 29498, 29529, 29563, 29632, 29644, 29645, 29900, 29934,
        29939, 29959, 30002, 30017, 30098, 30106, 30158, 30160, 30234, 30239, 30309, 30313,
        30335, 30373, 30456, 30647, 30692, 30854, 30906, 31035, 31078, 31201, 31265, 31288,
        31364, 31387, 31429, 31465, 31524, 31563, 31595, 31618, 31715, 31730, 31770, 31790,
        31839, 31842, 31860, 31949, 32035, 32038, 32136, 32163, 32221, 32237, 32278, 32299,
        32370, 32445, 32451, 32470, 32475, 32533, 32576, 32636, 32729, 32730, 32731, 32733,
        32743, 32764, 32783, 32959, 33289, 33410, 33544, 33588, 33594, 33809, 34033, 34040,
        34059, 34172, 34212, 34225, 34322, 34359, 34404, 34490, 34547, 34561, 34586, 34608,
        34628, 34694, 34801, 34811, 34935, 34961, 35235, 35292, 35312, 35424, 35481, 35498,
        35512, 35561, 35562, 35759, 35816, 35858, 35860, 35932, 35963, 35979, 35996, 36028,
        36148, 36177, 36204, 36282, 36289, 36408, 36450, 36535, 36546, 36554, 36609, 36677,
        36778, 36831, 36867, 37024, 37211, 37431, 37444, 37520, 37628, 37696, 37790, 37851,
        37863, 37903, 37908, 37938, 37947, 38056, 38134, 38318, 38327, 38420, 38422, 38507,
        38558, 38598, 38631, 38643, 38684, 38831, 38856, 38983, 39114, 39235, 39354, 39434,
        39485, 39705, 39706, 39977, 39985, 40022, 40048, 40093, 40147, 40166, 40231, 40336,
        40378, 40394, 40655, 40775, 40786, 41231, 41234, 41487, 41508, 41523, 41543, 41864,
        41900, 41988, 41991, 41997, 42004, 42109, 42181, 42218, 42237, 42261, 42370, 42371,
        42569, 42715, 43143, 43305, 43437, 43595, 43639, 43729, 43808, 43936, 44057, 44063,
        44201, 44207, 44230, 44250, 44579, 44586, 44789, 44911, 45011, 45178, 45205, 45299,
        45327, 45348, 45389, 45425, 45566, 45620, 45625, 45827, 45984, 46010, 46158, 46171,
        46270, 46438, 46495, 46556, 46820, 46829, 46838, 46858, 46893, 46964, 46980, 47220,
        47233, 47276, 47292, 47323, 47399, 47404, 47541, 47677, 47874, 47893, 48053, 48283,
        48300, 48654, 48667, 48690, 48859, 48915, 48982, 49090, 49244, 49453, 49590, 49604,
        49691, 49894, 50609, 50634, 50653, 50920, 51002, 51066, 51156, 51612, 51641, 51732,
        51767, 51820, 51844, 51934, 52129, 52481, 52539, 52598, 53225, 53227, 53328, 53358,
        53451, 53959, 53998, 54548, 54758, 55092, 55253, 55905, 56197, 56213, 56219, 56231,
        56255, 56268, 56337, 56540, 56607, 56612, 56613, 56958, 57135, 57724, 58639, 58998,
        59313, 59401, 59436, 59504, 59547, 59627, 59663, 59739, 59828, 59908, 59946, 60093,
        60473, 60841, 61667, 61744, 61763, 61808, 62042, 62375, 62620, 63065, 63383, 63398,
        63622, 63965, 64004, 64298, 64488, 64495, 64678, 64727, 64809, 65023, 65140, 65276,
        65438, 65601, 65723, 65908, 65922, 65955, 66090, 66128, 66298, 66588, 66819, 66952,
        67164, 67187, 67201, 67224, 67245, 67369, 67493, 67627, 67784, 67846, 68013, 68367,
        68462, 68736, 68759, 68909, 68934, 69039, 69307, 69346, 69568, 69733, 69765, 69838,
        69845, 69868, 69876, 70046, 70259, 70284, 70289, 70710, 70874, 70899, 70946, 71067,
        71405, 71476, 71573, 71595, 71639, 71874, 71899, 72138, 72229, 72432, 72573, 72816,
        72971, 73038, 73040, 73184, 73250, 73612, 73658, 73685, 73939, 74010, 74055, 74102,
        74226, 74390, 74524, 74570, 74651, 74767, 74942, 74946, 75001, 75122, 75483, 75555,
        75620, 75703, 75778, 75825, 75974, 76162, 76220, 76294, 76350, 76413, 76421, 76465,
        76497, 76565, 76575, 76728, 76901, 76919, 76957, 77059, 77074, 77290, 77456, 77544,
        77841, 77852, 78268, 78732, 79126, 79214, 79266, 79639, 80171, 80788, 82918, 82940,
        83256, 83400, 83579, 83730, 83901, 83903, 83905, 83960, 84016, 84519, 84677, 84760,
        84973, 85086, 85127, 85229, 85277, 85319, 85370, 85733, 85749, 85821, 85864, 86250,
        86408, 86450, 86515, 86599, 86612, 86631, 86770, 86880, 86934, 87083, 87164, 87175,
        87188, 87203, 87239, 87244, 87283, 87298, 87545, 87600, 87642, 87818, 87891, 87912,
        87924, 87966, 87972, 88094, 88103, 88118, 88225, 88285, 88367, 88373, 88412, 88569,
        88607, 88892, 89085, 89129, 89238, 89621, 89625, 89855, 89971, 90048, 90072, 90083,
        90119, 90122, 90164, 90225, 90248, 90288, 90315, 90377, 90397, 90433, 90470, 90549,
        90584, 90611, 90718, 90722, 90783, 90892, 90991, 91034, 91040, 91043, 91057, 91064,
        91078, 91093, 91210, 91307, 91356, 91373, 91404, 91454, 91537, 91548, 91661, 91709,
        91834, 91871, 91952, 92109, 92112, 92115, 92146, 92169, 92384, 92411, 92495, 92517,
        92518, 92565, 92584, 92743, 92818, 92917, 93020, 93070, 93119, 93153, 93222, 93247,
        93507, 93679, 93825, 93971, 94033, 94077, 94163, 94298, 94300, 94326, 94360, 94475,
        94861, 94977, 95000, 95297, 95916, 96268, 96324, 96477, 96724, 97033, 97646, 98016,
        98055, 98212, 98877, 98936, 99063, 99168, 99392, 99402, 99738, 99907, 100047, 100244,
        100263, 100332, 100851, 101053, 101105, 101339, 101374, 101529, 101562, 101692, 101797, 101981,
        102111, 102181, 102197, 102352, 102367, 102381, 102407, 102544, 103942, 104083, 104191, 104430,
        105226, 105376, 105671, 105707, 105928, 105966, 106012, 106131, 106677, 106839, 106887, 107110,
        107467, 107525, 107554, 107758, 107768, 108091, 108163, 108166, 108627, 108755, 108890, 108955,
        109187, 109421, 109431, 109562, 109709, 109799, 110069, 110084, 110282, 111603, 111713, 111780,
        112037, 112280, 113748, 113865, 113995, 114016, 114065, 114423, 114886, 115073, 115177, 115287,
        116132, 116290, 116483, 116795, 117408, 117699, 117781, 118111, 118282, 118354, 118473, 118804,
        118831, 118883, 119016, 119150, 119252, 119429, 119435, 119534, 119948, 120008, 120094, 120150,
        120335, 120367, 120397, 120523, 120619, 121659, 122053, 122286, 122320, 122508, 122919, 123457,
        123888, 123917, 123939, 124324, 124703, 124778, 124922, 125297, 125436, 125693, 125846, 125941,
        125980, 125983, 126126, 126246, 126397, 126543, 126660, 126663, 126974, 127286, 127480, 127589,
        127597, 127627, 127835, 128047, 128143, 128456, 128786, 128827, 129047, 129148, 129260, 129278,
        129556, 129974, 130187, 130272, 130307, 130376, 130549, 130569, 130634, 130727, 131034, 131246,
        131394, 131539, 131640, 131846, 131958
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the Structured State Space Sequence Model source or matches its name without naming, using or comparing Structured State Space Sequence Model'
FROM s4_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING s4_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING s4_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- self-refine: 30 links, 1742 exclusions. (1758 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE self_refine_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-refine'
  AND p.id IN (
        14322, 15765, 25460, 27886, 29558, 30966, 32706, 34978, 37048, 37821, 38719, 40377, 42388, 42415, 44690, 47774,
        47973, 49120, 52638, 52855, 54422, 55331, 64205, 65749, 68327, 72081, 72882, 76958, 94876, 110594
  );

DELETE FROM paper_method_exclusions x
USING self_refine_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM self_refine_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM self_refine_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE self_refine_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-refine'
  AND p.id IN (
        10633, 12076, 13181, 13936, 14301, 14448, 14505, 14606, 14743, 14812, 14897, 14954,
        14956, 15023, 15090, 15104, 15201, 15225, 15463, 15577, 15612, 15650, 15659, 15685,
        15736, 15776, 15788, 15841, 15900, 15957, 16007, 16059, 16067, 16068, 16070, 16080,
        16090, 16098, 16150, 16179, 16181, 16200, 16204, 16223, 16253, 16399, 16535, 16550,
        16603, 16640, 16700, 16729, 17017, 17061, 17108, 17456, 17482, 17539, 17668, 17708,
        17718, 18155, 18369, 18417, 18617, 18727, 18864, 18886, 18918, 18972, 19046, 19061,
        19071, 19143, 19164, 19169, 19227, 19265, 19271, 19286, 19346, 19431, 19575, 19624,
        19810, 19930, 19945, 19964, 20009, 20130, 20140, 20144, 20170, 20212, 20357, 20403,
        20426, 20458, 20484, 20562, 20624, 20625, 20688, 20707, 20794, 20809, 20814, 20826,
        20829, 20848, 20912, 20963, 21055, 21082, 21094, 21105, 21138, 21162, 21172, 21199,
        21235, 21267, 21298, 21315, 21325, 21328, 21336, 21337, 21378, 21414, 21467, 21477,
        21489, 21508, 21544, 21554, 21560, 21572, 21589, 21630, 21663, 21677, 21697, 21712,
        21796, 21805, 21854, 21900, 21902, 21921, 21944, 21954, 22017, 22023, 22027, 22130,
        22182, 22198, 22222, 22234, 22251, 22275, 22288, 22326, 22417, 22426, 22471, 22553,
        22647, 22699, 22770, 22828, 22839, 22929, 22991, 23048, 23054, 23120, 23146, 23152,
        23203, 23215, 23224, 23230, 23251, 23279, 23288, 23325, 23350, 23403, 23415, 23425,
        23428, 23543, 23554, 23649, 23723, 23835, 23999, 24048, 24132, 24136, 24201, 24207,
        24211, 24248, 24320, 24385, 24514, 24580, 24704, 24808, 24849, 24880, 24952, 25017,
        25036, 25064, 25133, 25142, 25319, 25410, 25458, 25471, 25498, 25527, 25550, 25613,
        25622, 25653, 25657, 25679, 25694, 25706, 25714, 25716, 25807, 25811, 25841, 25848,
        25867, 25940, 26038, 26091, 26198, 26216, 26258, 26295, 26637, 26666, 26697, 26764,
        26777, 26783, 26789, 26831, 26871, 26879, 26882, 26978, 27031, 27125, 27165, 27227,
        27284, 27421, 27444, 27445, 27467, 27482, 27527, 27625, 27673, 27681, 27692, 27724,
        27735, 27753, 27819, 27841, 27877, 27908, 27928, 28011, 28040, 28070, 28138, 28165,
        28194, 28500, 28533, 28684, 28761, 28783, 28789, 28817, 28833, 28875, 28954, 28976,
        28994, 29088, 29167, 29242, 29297, 29309, 29312, 29583, 29651, 29659, 29747, 29861,
        29950, 30009, 30074, 30105, 30111, 30225, 30330, 30400, 30443, 30470, 30486, 30492,
        30523, 30524, 30560, 30571, 30597, 30654, 30678, 30691, 30697, 30728, 30777, 30811,
        30874, 31058, 31109, 31131, 31205, 31407, 31487, 31582, 31596, 31613, 31686, 31726,
        31754, 31816, 31820, 31905, 31923, 32023, 32063, 32087, 32138, 32167, 32186, 32187,
        32218, 32243, 32259, 32271, 32428, 32474, 32488, 32498, 32561, 32634, 32650, 32659,
        32687, 32688, 32690, 32724, 32793, 32808, 32834, 32978, 33002, 33044, 33052, 33072,
        33091, 33139, 33200, 33227, 33268, 33327, 33382, 33489, 33505, 33568, 33607, 33653,
        33748, 33889, 33990, 33993, 34048, 34101, 34221, 34307, 34442, 34534, 34549, 34611,
        34658, 34734, 34735, 34771, 34871, 34893, 34948, 35032, 35208, 35222, 35281, 35394,
        35409, 35499, 35501, 35517, 35531, 35582, 35638, 35805, 35883, 35961, 35989, 36091,
        36121, 36125, 36218, 36363, 36366, 36506, 36513, 36525, 36592, 36858, 36883, 36891,
        36900, 36920, 37078, 37089, 37163, 37166, 37174, 37249, 37292, 37333, 37449, 37646,
        37664, 37775, 37797, 37829, 37844, 37864, 37877, 37884, 37915, 37925, 37954, 38036,
        38047, 38049, 38062, 38121, 38132, 38141, 38158, 38159, 38173, 38255, 38258, 38275,
        38325, 38331, 38457, 38495, 38595, 38600, 38617, 38650, 38653, 38686, 38705, 38736,
        38739, 38757, 38795, 38843, 38923, 38969, 39139, 39146, 39153, 39157, 39208, 39282,
        39359, 39439, 39440, 39454, 39506, 39519, 39529, 39537, 39543, 39582, 39595, 39682,
        39712, 39730, 39765, 39959, 39968, 39979, 40111, 40164, 40218, 40265, 40275, 40308,
        40445, 40522, 40583, 40685, 40718, 40782, 40885, 40912, 40916, 40919, 40943, 41001,
        41209, 41212, 41381, 41390, 41435, 41596, 41600, 41612, 41614, 41793, 41896, 41962,
        42038, 42058, 42200, 42227, 42242, 42248, 42272, 42278, 42303, 42333, 42446, 42466,
        42489, 42545, 42608, 42625, 42647, 42819, 42827, 42902, 42951, 42962, 43024, 43038,
        43047, 43065, 43206, 43225, 43241, 43244, 43339, 43347, 43374, 43436, 43470, 43513,
        43518, 43584, 43586, 43606, 43635, 43663, 43666, 43715, 43718, 43735, 43736, 43751,
        43772, 43798, 43879, 43958, 44002, 44071, 44084, 44098, 44130, 44143, 44160, 44186,
        44259, 44279, 44280, 44373, 44397, 44434, 44450, 44462, 44473, 44482, 44495, 44544,
        44549, 44643, 44665, 44674, 44714, 44717, 44790, 44849, 44861, 44942, 44966, 44973,
        44974, 44978, 45007, 45029, 45070, 45074, 45081, 45104, 45182, 45231, 45232, 45287,
        45382, 45386, 45439, 45443, 45461, 45465, 45499, 45518, 45540, 45559, 45615, 45701,
        45792, 45891, 45894, 45906, 45973, 46021, 46022, 46107, 46117, 46120, 46186, 46209,
        46232, 46327, 46336, 46348, 46444, 46445, 46467, 46609, 46665, 46670, 46675, 46685,
        46836, 46845, 46851, 46943, 46956, 46987, 47019, 47062, 47073, 47088, 47105, 47124,
        47154, 47182, 47204, 47296, 47312, 47324, 47334, 47376, 47391, 47459, 47489, 47517,
        47612, 47630, 47711, 47713, 47849, 47857, 47885, 47895, 47912, 47964, 48002, 48004,
        48061, 48064, 48073, 48258, 48268, 48316, 48350, 48406, 48466, 48521, 48592, 48703,
        48734, 48761, 48766, 48777, 48781, 48837, 48868, 48872, 48907, 48916, 48942, 49116,
        49130, 49247, 49262, 49280, 49350, 49373, 49388, 49459, 49470, 49476, 49577, 49598,
        49607, 49623, 49630, 49634, 49649, 49733, 49753, 49798, 49893, 49922, 49970, 50010,
        50027, 50044, 50056, 50059, 50077, 50118, 50133, 50273, 50347, 50400, 50593, 50594,
        50595, 50601, 50628, 50646, 50661, 50673, 50700, 50855, 50897, 50905, 50907, 51006,
        51056, 51087, 51178, 51265, 51277, 51278, 51279, 51333, 51396, 51403, 51425, 51431,
        51505, 51564, 51659, 51715, 51809, 51909, 51982, 51984, 52064, 52076, 52089, 52150,
        52187, 52196, 52245, 52266, 52332, 52340, 52409, 52420, 52480, 52674, 52749, 52891,
        53015, 53035, 53071, 53122, 53143, 53161, 53177, 53205, 53236, 53246, 53283, 53344,
        53352, 53353, 53356, 53370, 53421, 53430, 53477, 53525, 53559, 53590, 53655, 53664,
        53666, 53686, 53805, 53859, 53888, 54010, 54073, 54109, 54128, 54142, 54163, 54186,
        54220, 54226, 54246, 54325, 54326, 54429, 54611, 54613, 54629, 54638, 54725, 54831,
        54853, 55140, 55175, 55179, 55192, 55212, 55219, 55286, 55296, 55357, 55386, 55395,
        55403, 55494, 55533, 55554, 55556, 55639, 55782, 55792, 55811, 55830, 55880, 55907,
        55915, 55935, 55964, 55970, 55987, 56029, 56051, 56118, 56128, 56154, 56157, 56236,
        56258, 56273, 56278, 56281, 56289, 56334, 56350, 56399, 56440, 56470, 56600, 56604,
        56627, 56632, 56670, 56707, 56708, 56776, 56804, 56894, 56906, 56940, 56941, 57004,
        57038, 57081, 57103, 57132, 57161, 57178, 57211, 57221, 57224, 57245, 57252, 57276,
        57338, 57346, 57409, 57484, 57506, 57530, 57591, 57607, 57632, 57700, 57748, 57758,
        57775, 57866, 57913, 57928, 57959, 57965, 57998, 58044, 58087, 58142, 58224, 58226,
        58269, 58311, 58376, 58405, 58423, 58510, 58547, 58625, 58649, 58671, 58697, 58739,
        58748, 58906, 58950, 59033, 59158, 59175, 59217, 59230, 59324, 59347, 59364, 59384,
        59564, 59625, 59713, 59743, 59745, 59763, 59824, 59920, 59971, 59996, 60017, 60038,
        60202, 60241, 60292, 60347, 60444, 60450, 60525, 60534, 60545, 60550, 60561, 60611,
        60735, 60788, 60799, 60878, 60947, 60968, 60999, 61264, 61269, 61296, 61321, 61388,
        61403, 61404, 61427, 61436, 61569, 61587, 61698, 61707, 61817, 61854, 61855, 61856,
        61867, 61901, 61937, 61940, 62053, 62169, 62226, 62238, 62260, 62315, 62331, 62376,
        62397, 62405, 62423, 62430, 62527, 62590, 62616, 62638, 62675, 62710, 62750, 62825,
        62901, 62932, 62944, 63047, 63086, 63122, 63197, 63221, 63244, 63347, 63366, 63473,
        63700, 63792, 63847, 63975, 63978, 63984, 64131, 64147, 64199, 64374, 64389, 64395,
        64433, 64445, 64553, 64594, 64708, 64804, 64840, 64875, 64933, 65090, 65185, 65287,
        65357, 65418, 65427, 65660, 65752, 65857, 65947, 66003, 66095, 66164, 66171, 66217,
        66266, 66325, 66347, 66490, 66596, 66616, 66644, 66878, 66965, 66967, 67113, 67133,
        67377, 67402, 67441, 67448, 67478, 67517, 67569, 67611, 67645, 67736, 67754, 67843,
        67855, 67857, 67944, 68226, 68263, 68335, 68383, 68722, 68749, 68781, 68982, 69112,
        69368, 69396, 69500, 69532, 69533, 69638, 69642, 69684, 69685, 69888, 69994, 70008,
        70126, 70151, 70179, 70423, 70464, 70500, 70567, 70637, 70829, 70927, 71159, 71180,
        71227, 71299, 71355, 71630, 71654, 71824, 71946, 71977, 72146, 72178, 72210, 72227,
        72252, 72308, 72340, 72411, 72423, 72459, 72539, 72551, 72605, 72633, 72656, 72690,
        72753, 72847, 72860, 72884, 72888, 72912, 73003, 73105, 73306, 73354, 73384, 73420,
        73460, 73543, 73623, 73802, 73863, 74073, 74087, 74254, 74269, 74343, 74434, 74644,
        74726, 74764, 74825, 74888, 75133, 75261, 75372, 75388, 75432, 75499, 75726, 75842,
        75927, 75964, 76049, 76074, 76095, 76283, 76519, 76553, 77079, 77159, 77188, 77208,
        77307, 77313, 77409, 77472, 77513, 77741, 77755, 77900, 78598, 79260, 82833, 82859,
        82866, 82970, 82971, 82999, 83001, 83131, 83151, 83176, 83243, 83245, 83249, 83254,
        83291, 83444, 83478, 83596, 83682, 83693, 83701, 83803, 83810, 83846, 83945, 84092,
        84125, 84675, 85312, 85323, 85656, 85661, 85662, 85682, 85736, 85770, 85780, 85879,
        86010, 86038, 86098, 86175, 86405, 86456, 86601, 86668, 86697, 86702, 86923, 86939,
        87233, 87369, 87388, 87392, 87486, 87504, 88580, 88677, 88793, 89066, 89086, 89329,
        89332, 89377, 89639, 89643, 89672, 89730, 89863, 89900, 89965, 90378, 90518, 90933,
        91080, 91086, 91112, 91158, 91173, 91183, 91306, 91346, 91380, 91396, 91490, 91535,
        91814, 92113, 92180, 92182, 92457, 92462, 92479, 92524, 92537, 92547, 92597, 92643,
        92709, 92822, 93292, 93295, 93305, 93408, 93413, 93422, 93505, 93630, 93643, 93673,
        93687, 93797, 93894, 93921, 93935, 94058, 94125, 94233, 94235, 94425, 94537, 94538,
        94668, 94930, 94965, 95020, 95071, 95097, 96340, 96834, 97242, 97572, 97954, 97965,
        97968, 98114, 98137, 98234, 98393, 98537, 98541, 98582, 98689, 98767, 98784, 98799,
        98808, 98839, 98930, 98952, 98991, 99014, 99031, 99091, 99176, 99214, 99311, 99381,
        99409, 99457, 99531, 99621, 99875, 100124, 100173, 100284, 100367, 100534, 100536, 100642,
        100721, 100748, 100773, 100962, 101022, 101061, 101173, 101176, 101186, 101191, 101214, 101398,
        101427, 101490, 101650, 101689, 101799, 101913, 101952, 102029, 102047, 102051, 102096, 102144,
        102172, 102183, 102202, 102355, 102368, 102560, 102572, 102625, 102656, 102676, 102778, 102811,
        102879, 102910, 103000, 103012, 103028, 103070, 103177, 103251, 103279, 103346, 103357, 103378,
        103399, 103406, 103474, 103583, 103665, 103681, 103775, 103809, 103956, 104017, 104034, 104226,
        104305, 104317, 104318, 104382, 104456, 104575, 105948, 105999, 106046, 106047, 106048, 106057,
        106081, 106194, 106306, 106318, 106329, 106340, 106388, 106399, 106540, 106689, 106789, 106865,
        107027, 107141, 107163, 107418, 107953, 107977, 108015, 108073, 108149, 108384, 108494, 108513,
        108536, 108553, 108657, 108697, 108721, 108724, 108740, 108745, 108757, 108772, 108809, 108835,
        108891, 108947, 109024, 109095, 109100, 109128, 109135, 109499, 109503, 109521, 109531, 109533,
        109561, 109564, 109647, 109648, 109715, 109716, 109753, 109819, 109845, 109943, 109951, 109952,
        109988, 110022, 110051, 110057, 110061, 110100, 110158, 110183, 110271, 110298, 110336, 110338,
        110359, 110372, 110413, 110502, 110533, 110605, 110633, 110868, 110915, 111026, 111090, 113264,
        113750, 113759, 113805, 113823, 113849, 113868, 113983, 113998, 114071, 114089, 114138, 114185,
        114222, 115709, 117281, 117432, 117641, 118176, 118530, 118625, 118707, 118852, 119351, 119442,
        119495, 119598, 119675, 121644, 121770, 121977, 122031, 122076, 122094, 122199, 122244, 122279,
        122280, 122326, 122328, 122343, 122354, 122385, 122406, 122412, 122425, 122480, 122488, 122550,
        122570, 122605, 122648, 122650, 122686, 122699, 122718, 122765, 122797, 122877, 122891, 122903,
        122906, 122907, 122932, 122933, 122934, 123004, 123008, 123013, 123154, 123198, 123221, 123237,
        123240, 123281, 123289, 123442, 123554, 123571, 123623, 123708, 123715, 123726, 123750, 123758,
        123774, 123784, 123811, 123873, 123946, 123954, 123960, 123982, 124040, 124088, 124842, 124950,
        124957, 125175, 125231, 125361, 125470, 125584, 125852, 125873, 125910, 126037, 126221, 126236,
        126911, 127071, 127078, 127090, 127129, 127596, 127606, 127647, 128050, 128210, 128397, 128455,
        128476, 128718, 128789, 128971, 129020, 129036, 129357, 129393, 129420, 129715, 129868, 129954,
        130039, 130125, 130356, 130440, 130574, 131086, 131134, 131161, 131175, 131268, 131306, 131359,
        131376, 131387, 131388, 131440, 131594, 131631, 131642, 131774, 131784, 131832, 131878, 131904,
        131910, 131981
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the Self-Refine source or matches its name without naming, using or comparing Self-Refine'
FROM self_refine_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING self_refine_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING self_refine_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- reflexion: 23 links, 2057 exclusions. (2068 local citers from Semantic Scholar + OpenAlex.)
CREATE TEMP TABLE reflexion_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'reflexion'
  AND p.id IN (
        13936, 16424, 22023, 25694, 27302, 27598, 27928, 28994, 31661, 49268, 51180, 51333, 57928, 63088, 63366, 72882,
        76308, 85550, 98025, 99030, 103036, 106673, 109380
  );

DELETE FROM paper_method_exclusions x
USING reflexion_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM reflexion_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM reflexion_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

CREATE TEMP TABLE reflexion_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'reflexion'
  AND p.id IN (
        10633, 12076, 12807, 13175, 14301, 14327, 14376, 14448, 14606, 14954, 14956, 15104,
        15146, 15442, 15776, 15788, 15933, 15957, 16068, 16070, 16098, 16118, 16166, 16181,
        16204, 16223, 16225, 16237, 16253, 16350, 16479, 16503, 16535, 16603, 16729, 17061,
        17268, 17302, 17311, 17370, 17456, 17668, 17708, 17821, 17939, 18155, 18192, 18201,
        18348, 18417, 18802, 18864, 18886, 18918, 18961, 18972, 19007, 19046, 19143, 19165,
        19170, 19271, 19306, 19346, 19431, 19491, 19575, 19617, 19624, 19693, 19854, 19964,
        20013, 20130, 20170, 20221, 20234, 20426, 20458, 20488, 20591, 20624, 20625, 20687,
        20743, 20777, 20794, 20983, 20985, 21081, 21082, 21093, 21094, 21101, 21105, 21199,
        21235, 21267, 21298, 21350, 21432, 21467, 21469, 21489, 21508, 21544, 21560, 21572,
        21644, 21665, 21697, 21722, 21734, 21740, 21751, 21796, 21799, 21805, 21854, 21876,
        21898, 21900, 21910, 21921, 21944, 21954, 22017, 22195, 22198, 22228, 22251, 22264,
        22275, 22288, 22368, 22385, 22418, 22471, 22486, 22496, 22528, 22699, 22717, 22770,
        22774, 22913, 22929, 22937, 22991, 23048, 23059, 23144, 23146, 23152, 23203, 23224,
        23230, 23251, 23257, 23272, 23288, 23325, 23328, 23373, 23454, 23523, 23530, 23551,
        23746, 23874, 24048, 24186, 24207, 24343, 24397, 24436, 24492, 24514, 24704, 24781,
        24848, 24952, 24958, 24971, 25002, 25036, 25041, 25142, 25209, 25268, 25314, 25319,
        25458, 25527, 25550, 25562, 25622, 25653, 25679, 25807, 25836, 25839, 25860, 25867,
        25940, 26038, 26198, 26199, 26216, 26258, 26295, 26494, 26579, 26629, 26633, 26637,
        26662, 26677, 26681, 26732, 26763, 26789, 26798, 26831, 26869, 26871, 26879, 26978,
        27012, 27059, 27111, 27125, 27136, 27165, 27184, 27201, 27217, 27224, 27261, 27284,
        27340, 27369, 27378, 27391, 27455, 27471, 27477, 27518, 27527, 27682, 27716, 27753,
        27822, 27839, 27908, 27912, 27961, 27997, 28165, 28170, 28209, 28285, 28310, 28428,
        28429, 28433, 28538, 28581, 28631, 28761, 28768, 28817, 28833, 28875, 28935, 28954,
        28999, 29126, 29211, 29242, 29335, 29437, 29500, 29558, 29583, 29589, 29830, 29950,
        29968, 30009, 30012, 30111, 30150, 30212, 30330, 30400, 30443, 30470, 30478, 30505,
        30569, 30571, 30654, 30718, 30777, 30840, 30852, 30869, 31072, 31097, 31110, 31205,
        31311, 31371, 31407, 31411, 31427, 31546, 31553, 31567, 31574, 31596, 31613, 31678,
        31686, 31726, 31747, 31754, 31765, 31779, 31816, 31820, 31899, 31923, 31993, 32014,
        32044, 32063, 32166, 32187, 32255, 32271, 32392, 32401, 32498, 32561, 32634, 32645,
        32668, 32687, 32700, 32724, 32793, 32834, 33072, 33092, 33128, 33240, 33280, 33317,
        33382, 33388, 33423, 33505, 33526, 33568, 33771, 33877, 33878, 33971, 33977, 33990,
        33993, 34193, 34362, 34387, 34393, 34503, 34529, 34535, 34611, 34656, 34683, 34731,
        34734, 34843, 34871, 34875, 34978, 35130, 35208, 35234, 35252, 35391, 35457, 35496,
        35531, 35550, 35556, 35582, 35650, 35798, 35812, 35846, 35883, 35904, 35948, 35961,
        36070, 36091, 36125, 36366, 36432, 36455, 36525, 36552, 36601, 36611, 36626, 36675,
        36780, 36858, 36883, 36891, 36900, 36991, 37018, 37060, 37064, 37068, 37089, 37208,
        37227, 37290, 37333, 37347, 37366, 37562, 37629, 37645, 37646, 37648, 37657, 37712,
        37721, 37787, 37815, 37821, 37823, 37824, 37830, 37869, 37886, 37969, 38008, 38034,
        38036, 38060, 38062, 38108, 38162, 38209, 38225, 38253, 38255, 38258, 38265, 38275,
        38286, 38325, 38340, 38378, 38457, 38556, 38600, 38601, 38616, 38651, 38680, 38686,
        38705, 38748, 38782, 38787, 38843, 38860, 38923, 38955, 38982, 39004, 39032, 39146,
        39207, 39208, 39237, 39253, 39326, 39355, 39440, 39505, 39533, 39545, 39576, 39595,
        39712, 39723, 39765, 39923, 39926, 39959, 40164, 40218, 40255, 40275, 40308, 40502,
        40522, 40811, 40916, 40994, 41001, 41390, 41499, 41526, 41599, 41793, 41807, 41823,
        41913, 41948, 42048, 42097, 42245, 42266, 42305, 42350, 42446, 42466, 42489, 42544,
        42608, 42615, 42617, 42731, 42791, 42806, 42816, 42900, 42909, 43024, 43038, 43047,
        43065, 43241, 43374, 43436, 43473, 43487, 43505, 43514, 43576, 43586, 43606, 43663,
        43666, 43670, 43687, 43715, 43718, 43751, 43814, 43818, 43823, 43878, 43976, 43993,
        43998, 44048, 44071, 44075, 44198, 44200, 44249, 44279, 44342, 44417, 44453, 44482,
        44605, 44653, 44665, 44690, 44743, 44861, 44950, 45029, 45050, 45074, 45077, 45104,
        45180, 45182, 45257, 45287, 45443, 45522, 45540, 45571, 45641, 45711, 45716, 45827,
        45887, 45894, 46023, 46075, 46107, 46120, 46193, 46272, 46306, 46380, 46425, 46439,
        46448, 46467, 46487, 46511, 46609, 46639, 46646, 46665, 46680, 46685, 46696, 46783,
        46851, 46935, 46956, 46987, 47019, 47073, 47088, 47119, 47150, 47204, 47241, 47289,
        47295, 47299, 47334, 47337, 47353, 47391, 47431, 47446, 47460, 47517, 47569, 47589,
        47630, 47730, 47760, 47785, 47845, 47912, 47967, 47973, 48002, 48038, 48058, 48060,
        48061, 48081, 48183, 48195, 48204, 48246, 48282, 48292, 48294, 48406, 48420, 48461,
        48491, 48518, 48622, 48734, 48776, 48781, 48819, 48844, 48896, 48898, 48916, 48966,
        49049, 49077, 49097, 49127, 49247, 49262, 49280, 49356, 49388, 49470, 49476, 49482,
        49537, 49577, 49579, 49592, 49607, 49649, 49733, 49744, 49753, 49770, 49785, 49922,
        49944, 50010, 50044, 50059, 50142, 50258, 50373, 50450, 50480, 50556, 50577, 50595,
        50600, 50654, 50725, 50728, 50735, 50753, 50782, 50862, 50893, 50905, 50945, 50995,
        51001, 51006, 51045, 51054, 51070, 51098, 51136, 51274, 51277, 51278, 51364, 51418,
        51425, 51505, 51590, 51659, 51781, 51834, 51982, 51984, 52029, 52215, 52242, 52245,
        52389, 52403, 52420, 52444, 52461, 52474, 52524, 52597, 52635, 52661, 52689, 52726,
        52735, 52817, 52980, 53015, 53029, 53047, 53080, 53081, 53088, 53106, 53120, 53122,
        53161, 53177, 53218, 53224, 53236, 53246, 53283, 53292, 53308, 53344, 53356, 53370,
        53380, 53421, 53427, 53477, 53500, 53525, 53538, 53560, 53589, 53591, 53611, 53690,
        53694, 53733, 53741, 53771, 53859, 53881, 53888, 53947, 53963, 54047, 54073, 54123,
        54128, 54144, 54149, 54163, 54227, 54331, 54341, 54408, 54441, 54473, 54564, 54611,
        54616, 54629, 54695, 54853, 54918, 54931, 54988, 55014, 55023, 55069, 55137, 55175,
        55179, 55192, 55212, 55262, 55286, 55296, 55320, 55410, 55419, 55429, 55474, 55554,
        55556, 55610, 55620, 55639, 55734, 55735, 55807, 55811, 55824, 55830, 55855, 55872,
        55907, 55915, 55926, 55935, 55950, 55956, 55970, 55977, 56029, 56043, 56069, 56118,
        56147, 56154, 56156, 56217, 56258, 56273, 56276, 56278, 56281, 56289, 56333, 56334,
        56377, 56399, 56423, 56432, 56442, 56469, 56484, 56515, 56549, 56554, 56600, 56604,
        56627, 56632, 56638, 56647, 56670, 56707, 56708, 56710, 56711, 56779, 56784, 56816,
        56821, 56866, 56894, 56906, 56940, 56941, 57009, 57042, 57052, 57055, 57073, 57081,
        57103, 57161, 57167, 57175, 57178, 57211, 57240, 57245, 57252, 57276, 57302, 57304,
        57331, 57344, 57346, 57363, 57409, 57492, 57494, 57506, 57530, 57569, 57579, 57586,
        57593, 57607, 57623, 57642, 57686, 57700, 57706, 57726, 57740, 57758, 57797, 57922,
        57924, 57955, 57959, 57965, 57993, 57998, 58026, 58142, 58224, 58226, 58244, 58305,
        58311, 58330, 58338, 58365, 58376, 58387, 58398, 58423, 58504, 58622, 58625, 58628,
        58671, 58739, 58748, 58929, 58950, 59091, 59103, 59217, 59302, 59324, 59328, 59364,
        59499, 59564, 59620, 59625, 59653, 59723, 59735, 59737, 59748, 59753, 59824, 59920,
        59987, 60019, 60038, 60078, 60086, 60174, 60199, 60212, 60227, 60230, 60307, 60313,
        60320, 60450, 60477, 60525, 60534, 60540, 60561, 60602, 60611, 60667, 60671, 60687,
        60799, 60860, 60873, 60877, 60881, 60905, 60922, 60927, 60954, 61033, 61049, 61104,
        61141, 61177, 61203, 61207, 61247, 61269, 61296, 61380, 61406, 61427, 61453, 61457,
        61480, 61504, 61528, 61569, 61579, 61587, 61707, 61749, 61750, 61760, 61765, 61771,
        61788, 61799, 61817, 61831, 61848, 61854, 61855, 61865, 61866, 61867, 61901, 61940,
        62005, 62038, 62053, 62268, 62269, 62331, 62371, 62376, 62423, 62494, 62590, 62643,
        62655, 62661, 62710, 62750, 62757, 62779, 62803, 62889, 62901, 62916, 62925, 62962,
        63030, 63122, 63125, 63195, 63197, 63221, 63328, 63334, 63347, 63399, 63411, 63566,
        63589, 63676, 63792, 63826, 63864, 63964, 64199, 64220, 64240, 64344, 64374, 64386,
        64389, 64395, 64427, 64445, 64509, 64531, 64564, 64594, 64819, 64875, 64899, 64900,
        64946, 65104, 65122, 65185, 65210, 65287, 65330, 65399, 65489, 65499, 65509, 65730,
        65748, 65749, 65752, 65777, 65782, 65784, 65785, 65900, 65903, 65947, 66003, 66005,
        66137, 66147, 66155, 66164, 66171, 66182, 66199, 66217, 66223, 66247, 66250, 66266,
        66327, 66444, 66453, 66520, 66532, 66557, 66633, 66644, 66700, 66709, 66822, 66824,
        66847, 66862, 66878, 66944, 66946, 66965, 66967, 66993, 67021, 67113, 67133, 67231,
        67256, 67353, 67384, 67397, 67448, 67509, 67536, 67586, 67615, 67645, 67729, 67736,
        67791, 67849, 67857, 67865, 67872, 67993, 68164, 68226, 68236, 68335, 68371, 68451,
        68573, 68598, 68722, 68749, 68767, 68802, 68900, 68925, 68928, 68970, 69004, 69092,
        69208, 69379, 69500, 69638, 69684, 69711, 69715, 69902, 70151, 70179, 70234, 70298,
        70300, 70371, 70420, 70423, 70441, 70459, 70500, 70672, 70677, 70727, 70811, 70829,
        70852, 70986, 71070, 71139, 71169, 71180, 71234, 71456, 71473, 71553, 71630, 71650,
        71986, 72178, 72201, 72252, 72281, 72308, 72337, 72340, 72411, 72416, 72575, 72656,
        72804, 72806, 72812, 72847, 72903, 72908, 72912, 72920, 72998, 73041, 73105, 73199,
        73283, 73306, 73316, 73384, 73394, 73499, 73689, 73802, 73900, 73914, 74087, 74124,
        74154, 74254, 74269, 74276, 74327, 74392, 74434, 74644, 74726, 74825, 74827, 74906,
        74939, 74983, 75052, 75070, 75133, 75199, 75261, 75372, 75441, 75545, 75553, 75726,
        75782, 75921, 75962, 76010, 76081, 76154, 76190, 76519, 76611, 76700, 77034, 77042,
        77131, 77188, 77208, 77313, 77399, 77513, 77525, 77594, 77819, 77900, 78204, 78238,
        78395, 82833, 82859, 82866, 82877, 82919, 82938, 82971, 82983, 82999, 83001, 83002,
        83131, 83134, 83138, 83151, 83175, 83176, 83205, 83208, 83229, 83243, 83245, 83249,
        83254, 83280, 83291, 83301, 83306, 83365, 83368, 83388, 83390, 83433, 83444, 83450,
        83456, 83466, 83534, 83596, 83682, 83693, 83701, 83753, 83754, 83763, 83792, 83809,
        83810, 83819, 83821, 83846, 83883, 83945, 83954, 84411, 84451, 84675, 84870, 85154,
        85312, 85661, 85662, 85679, 85682, 85889, 85961, 86049, 86098, 86303, 86405, 86806,
        86837, 86923, 86939, 86951, 87105, 87233, 87287, 87320, 87369, 87404, 87487, 87500,
        87512, 88594, 88793, 89066, 89086, 89194, 89196, 89329, 89639, 89766, 89851, 89922,
        90814, 91086, 91173, 91175, 91293, 91295, 91326, 91380, 91386, 91396, 91535, 91658,
        91677, 91767, 91814, 91925, 92130, 92457, 92462, 92545, 92547, 92566, 92578, 92617,
        92670, 92822, 92948, 93041, 93204, 93211, 93231, 93305, 93408, 93488, 93550, 93629,
        93643, 93680, 93687, 93810, 93870, 93885, 93908, 93921, 93946, 94005, 94058, 94125,
        94233, 94265, 94414, 94538, 94556, 94609, 94668, 94695, 94749, 94930, 94965, 95010,
        95020, 95097, 95106, 96340, 96627, 97242, 97453, 97572, 97655, 97656, 97954, 97965,
        97982, 98040, 98053, 98087, 98137, 98189, 98233, 98234, 98325, 98430, 98458, 98537,
        98541, 98565, 98576, 98683, 98689, 98690, 98706, 98718, 98767, 98798, 98799, 98801,
        98807, 98839, 98932, 98942, 98943, 98952, 98974, 99014, 99031, 99065, 99087, 99091,
        99098, 99117, 99135, 99154, 99176, 99214, 99311, 99409, 99518, 99591, 99621, 99718,
        99859, 99875, 99926, 99977, 100009, 100242, 100284, 100356, 100367, 100407, 100420, 100433,
        100534, 100649, 100694, 100785, 100877, 100898, 101022, 101117, 101119, 101141, 101176, 101191,
        101250, 101427, 101484, 101490, 101525, 101574, 101891, 101958, 102047, 102051, 102169, 102172,
        102183, 102195, 102202, 102224, 102291, 102305, 102355, 102358, 102411, 102429, 102431, 102471,
        102509, 102523, 102560, 102566, 102568, 102572, 102625, 102626, 102693, 102722, 102754, 102879,
        102941, 103000, 103062, 103070, 103268, 103406, 103583, 103809, 103956, 104008, 104017, 104024,
        104034, 104037, 104305, 104317, 104382, 104388, 104398, 104447, 104507, 104525, 104527, 104575,
        104744, 105875, 105883, 105932, 105948, 106045, 106046, 106047, 106048, 106057, 106164, 106178,
        106220, 106270, 106276, 106284, 106300, 106326, 106340, 106388, 106399, 106763, 106802, 106990,
        107716, 108015, 108614, 108657, 108697, 108721, 108724, 108733, 108745, 108757, 108770, 108772,
        108785, 108796, 108807, 108809, 108835, 108841, 108888, 108891, 108924, 108939, 108947, 109018,
        109065, 109069, 109073, 109100, 109109, 109120, 109128, 109133, 109135, 109138, 109277, 109444,
        109461, 109496, 109503, 109510, 109521, 109533, 109561, 109563, 109564, 109585, 109628, 109647,
        109648, 109650, 109655, 109711, 109715, 109716, 109741, 109742, 109753, 109757, 109819, 109823,
        109845, 110051, 110089, 110232, 110334, 110605, 110801, 110823, 111040, 111118, 111123, 112308,
        113264, 113735, 113750, 113759, 113809, 113823, 113864, 113868, 113897, 113899, 113953, 114030,
        114070, 114071, 114089, 114099, 114138, 114185, 114193, 114213, 114220, 114222, 114227, 114228,
        115709, 117641, 117780, 118009, 118011, 118120, 118176, 118625, 118632, 118707, 119432, 119442,
        119486, 119495, 119597, 119633, 120256, 121770, 121946, 121953, 121958, 121973, 121977, 121985,
        121986, 122031, 122068, 122074, 122094, 122137, 122154, 122167, 122171, 122174, 122192, 122199,
        122272, 122279, 122280, 122326, 122327, 122343, 122364, 122385, 122396, 122412, 122425, 122459,
        122465, 122480, 122483, 122488, 122498, 122531, 122553, 122570, 122621, 122630, 122644, 122648,
        122686, 122699, 122707, 122710, 122724, 122725, 122730, 122734, 122737, 122748, 122759, 122765,
        122786, 122794, 122799, 122823, 122832, 122875, 122877, 122891, 122902, 122903, 122906, 122907,
        122910, 122932, 122933, 122934, 122944, 122958, 122962, 122964, 122996, 123004, 123006, 123008,
        123013, 123039, 123049, 123059, 123144, 123154, 123198, 123221, 123233, 123237, 123240, 123244,
        123254, 123281, 123289, 123292, 123364, 123411, 123435, 123442, 123448, 123469, 123512, 123523,
        123543, 123564, 123566, 123571, 123575, 123578, 123623, 123685, 123690, 123691, 123698, 123708,
        123715, 123755, 123758, 123773, 123776, 123784, 123811, 123873, 123874, 123888, 123896, 123941,
        123946, 123960, 123962, 123970, 123977, 123981, 123982, 123998, 124041, 124083, 124088, 124208,
        124344, 124366, 124935, 124950, 124957, 125136, 125175, 125191, 125231, 125266, 125273, 125366,
        125457, 125469, 125474, 125667, 125852, 125900, 125910, 125954, 125987, 125999, 126037, 126069,
        126221, 126688, 126699, 126749, 126793, 126800, 126803, 126933, 127071, 127090, 127096, 127129,
        127596, 127606, 127647, 127809, 128050, 128119, 128210, 128274, 128539, 128559, 128661, 128718,
        128789, 128811, 128971, 129011, 129020, 129092, 129111, 129155, 129393, 129420, 129434, 129440,
        129476, 129868, 129942, 129954, 130108, 130125, 130267, 130440, 130475, 130515, 130574, 130582,
        130981, 131018, 131086, 131091, 131134, 131306, 131310, 131376, 131382, 131387, 131440, 131467,
        131471, 131473, 131492, 131501, 131506, 131540, 131541, 131597, 131642, 131645, 131655, 131667,
        131713, 131754, 131763, 131774, 131784, 131812, 131829, 131831, 131832, 131878, 131897, 131904,
        131910, 131945, 131981, 132090, 132114
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the Reflexion source or matches its name without naming, using or comparing Reflexion'
FROM reflexion_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING reflexion_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING reflexion_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
