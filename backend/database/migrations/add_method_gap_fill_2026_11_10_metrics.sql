-- Method gap fill (2026-11-10 audit): nine evaluation metrics, alongside the
-- existing BLEU, ROUGE, FID and Pass@1 metric methods.
--
-- LPIPS (1801.03924), BERTScore (1904.09675) and CIDEr (1411.5726) have arXiv
-- introducing papers, so they get source_paper_id and an "Introduced" banner.
-- Perplexity, PSNR, SSIM, IoU, mAP and Elo predate arXiv or have no single
-- introducing paper: source_paper_id stays NULL and source_url points to the
-- canonical reference (a DOI where one exists).
--
-- Keywords follow BLEU and FID: the unambiguous metric acronym (case-sensitive
-- in the keyword backfill because it is capitalised) plus the exact long form.
-- Ordinary-word collisions are avoided: Elo is only matched as "Elo rating",
-- "Elo score" or "Elo-based", and mAP only in that capitalisation (never
-- "map"). Perplexity also names a search company, so those abstracts are
-- excluded and abstract linking is judged.
--
-- Paper links: every local paper whose title/abstract names the metric
-- (keyword-matcher candidates, reviewed for other senses) gets 'manual'
-- evidence. For the three sourced metrics, local citers of the source paper
-- whose title/abstract does not name the metric become durable exclusions so
-- the hourly reference backfill does not link every paper that merely cites
-- the source. Hero images were imported separately with
-- import_entity_image.py; this file records their credits.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES
(
    'perplexity',
    'Perplexity',
    'Perplexity (PPL)',
    'Perplexity (PPL) measures how well a probabilistic language model predicts a held-out text. It is the exponentiated average negative log-likelihood per token, PPL = exp(−(1/N) Σ log p(xᵢ | x₍<ᵢ₎)), so it equals the exponential of the [Cross-Entropy (CE)](/methods/cross-entropy-ce) loss and can be read as the effective number of equally likely choices the model faces at each step; lower is better. Introduced by Jelinek, Mercer, Bahl and Baker (1977) to quantify the difficulty of speech recognition tasks, it became the standard intrinsic metric for n-gram, recurrent and [Transformer](/methods/transformer) language models and the quantity behind neural scaling laws. Because it depends on the tokenizer and vocabulary, perplexities are only comparable for the same tokenization, which is why bits-per-byte or bits-per-character are used across tokenizers. Beyond evaluation of [Large language models (LLMs)](/methods/large-language-model-llm), perplexity is used to filter and select pretraining data, to detect machine-generated text, membership and benchmark contamination, to measure quantization and pruning damage, and as "generative perplexity" for diffusion language models; its weak correlation with long-context and downstream ability is a recurring research topic.',
    'perplexity',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    1977,
    NULL,
    'https://doi.org/10.1121/1.2016299',
    'Perplexity — a Measure of the Difficulty of Speech Recognition Tasks (Jelinek et al., 1977)',
    NULL,
    NULL,
    'judge',
    ARRAY[]::text[]
),
(
    'psnr',
    'PSNR',
    'Peak Signal-to-Noise Ratio (PSNR)',
    'Peak Signal-to-Noise Ratio (PSNR) is a full-reference fidelity metric that compares a reconstructed signal with its reference. For images it is PSNR = 10 · log₁₀(MAX² / MSE), where MAX is the largest possible pixel value (255 for 8-bit images) and MSE is the mean squared error between the two images, so it is reported in decibels and higher is better. Because it depends only on the pixel-wise error, PSNR is cheap, differentiable and easy to compare, and it has been the default metric for image and video compression, denoising, deblurring, super-resolution, inpainting, MRI reconstruction and novel view synthesis with NeRF and 3D Gaussian splatting. Its weak correlation with perceived quality (blurry outputs that minimise MSE score well, while sharp but slightly misaligned outputs score poorly) motivated structural and learned metrics such as [SSIM](/methods/ssim) and [LPIPS](/methods/lpips), and most papers now report all three together.',
    'PSNR, peak signal-to-noise ratio, peak signal to noise ratio',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1049/el:20080522',
    'Scope of Validity of PSNR in Image/Video Quality Assessment (Huynh-Thu & Ghanbari, 2008)',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
),
(
    'ssim',
    'SSIM',
    'Structural Similarity Index Measure (SSIM)',
    'The Structural Similarity Index Measure (SSIM), introduced by Wang, Bovik, Sheikh and Simoncelli (2004), is a full-reference image quality metric that compares local patterns of pixel intensities rather than absolute errors. Within a sliding (usually Gaussian) window it combines a luminance term from the local means, a contrast term from the local standard deviations and a structure term from their correlation into SSIM(x, y) = ((2μₓμᵧ + C₁)(2σₓᵧ + C₂)) / ((μₓ² + μᵧ² + C₁)(σₓ² + σᵧ² + C₂)), and averages the resulting map over the image; values lie in [−1, 1] with 1 for identical images. SSIM tracks human judgments better than [PSNR](/methods/psnr) and is differentiable, so it serves both as an evaluation metric and as a training loss for image restoration, super-resolution, compression, medical image reconstruction and novel view synthesis (3D Gaussian splatting optimises an L1 + D-SSIM loss). Multi-scale SSIM (MS-SSIM) evaluates it over several resolutions. Learned metrics such as [LPIPS](/methods/lpips) were later shown to match perceptual judgments more closely.',
    'SSIM, structural similarity index, structural similarity index measure',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2004,
    NULL,
    'https://doi.org/10.1109/TIP.2003.819861',
    'Image Quality Assessment: From Error Visibility to Structural Similarity (Wang et al., 2004)',
    NULL,
    NULL,
    'always',
    ARRAY['Structural Similarity Index (SSIM)']
),
(
    'lpips',
    'LPIPS',
    'Learned Perceptual Image Patch Similarity (LPIPS)',
    'Learned Perceptual Image Patch Similarity (LPIPS), introduced in [The Unreasonable Effectiveness of Deep Features as a Perceptual Metric](/paper/1801.03924) (Zhang et al., 2018), measures the perceptual distance between two images with deep network features. Both images are passed through a pretrained backbone such as [AlexNet](/methods/alexnet), [VGG](/methods/vgg) or SqueezeNet; activations from several layers are unit-normalised in the channel dimension, scaled channel-wise by learned weights, and their squared differences are averaged spatially and summed over layers; lower means more similar. The weights are calibrated on the Berkeley-Adobe Perceptual Patch Similarity (BAPPS) dataset of human two-alternative forced-choice judgments, and the paper shows that deep features from supervised, self-supervised and even unsupervised networks agree with human perception far better than [PSNR](/methods/psnr) or [SSIM](/methods/ssim). LPIPS is now reported next to PSNR and SSIM for super-resolution, image restoration, generative editing, inversion and novel view synthesis, is used as a perceptual training loss, and measures sample diversity in image-to-image translation; dataset-level realism is instead measured with [Fréchet Inception Distance (FID)](/methods/frechet-inception-distance-fid).',
    'LPIPS, learned perceptual image patch similarity',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2018,
    (SELECT id FROM papers WHERE arxiv_id = '1801.03924'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'The Unreasonable Effectiveness of Deep Features as a Perceptual Metric',
    'https://github.com/richzhang/PerceptualSimilarity',
    NULL,
    'always',
    ARRAY[]::text[]
),
(
    'intersection-over-union-iou',
    'Intersection over Union',
    'Intersection over Union (IoU)',
    'Intersection over Union (IoU), also known as the Jaccard index after Paul Jaccard (1901), measures the overlap between two sets as the size of their intersection divided by the size of their union, |A ∩ B| / |A ∪ B|, from 0 for disjoint sets to 1 for identical ones. In computer vision it compares predicted and ground-truth bounding boxes or masks: detection benchmarks such as PASCAL VOC and COCO count a prediction as correct when its IoU with a ground-truth object exceeds a threshold (0.5, or 0.5 to 0.95 in steps of 0.05), which makes IoU the basis of [Mean Average Precision (mAP)](/methods/mean-average-precision-map), and semantic segmentation reports the mean IoU (mIoU) over classes. IoU also drives [Non Maximum Suppression (NMS)](/methods/non-maximum-suppression-nms) and anchor assignment in detectors such as [Faster R-CNN](/methods/faster-r-cnn), and is optimised directly through IoU-based box regression losses (GIoU, DIoU, CIoU) and the closely related [Dice Loss](/methods/dice-loss) for masks. Variants include temporal IoU for video localization, 3D and rotated IoU for LiDAR and aerial detection, and Jaccard similarity of token or n-gram sets for near-duplicate text detection.',
    'IoU, intersection over union, intersection-over-union, jaccard index, jaccard similarity',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1111/j.1469-8137.1912.tb05611.x',
    'The Distribution of the Flora in the Alpine Zone (Jaccard, 1912)',
    NULL,
    NULL,
    'always',
    ARRAY['Jaccard Index']
),
(
    'mean-average-precision-map',
    'Mean Average Precision',
    'Mean Average Precision (mAP)',
    'Mean Average Precision (mAP) summarises a ranked list of predictions in one number by averaging, over classes or queries, the average precision (AP): the area under the precision–recall curve obtained by sweeping the confidence threshold. In object detection a predicted box is a true positive when its [Intersection over Union (IoU)](/methods/intersection-over-union-iou) with an unmatched ground-truth box exceeds a threshold. The PASCAL VOC challenge popularised AP at IoU 0.5 (mAP@50, first with 11-point interpolation), and [Microsoft COCO](/paper/1405.0312) made AP averaged over IoU thresholds 0.5 to 0.95 (mAP@[.5:.95]) the primary metric, with size-specific variants (APₛ, APₘ, APₗ). Detectors from [R-CNN](/methods/r-cnn) and [Faster R-CNN](/methods/faster-r-cnn) to [YOLO](/methods/yolo) and DETR are ranked by it, as are instance segmentation (mask AP), 3D detection in autonomous driving (nuScenes mAP and NDS, Waymo mAPH), keypoint detection, temporal action localization, multi-label classification, and information retrieval, re-identification and image retrieval, where mAP averages AP over queries and is often reported with Recall@k or Rank-1 accuracy.',
    'mAP, mean average precision',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1007/s11263-009-0275-4',
    'The PASCAL Visual Object Classes (VOC) Challenge (Everingham et al., 2010)',
    NULL,
    NULL,
    'judge',
    ARRAY[]::text[]
),
(
    'bertscore',
    'BERTScore',
    'BERTScore',
    'BERTScore, introduced in [BERTScore: Evaluating Text Generation with BERT](/paper/1904.09675) (Zhang et al., 2019), is a reference-based metric for generated text that compares contextual token embeddings instead of surface n-grams. Candidate and reference are encoded with a pretrained model such as [BERT](/methods/bert) or RoBERTa; each token is greedily matched to its most cosine-similar token in the other sentence, and the matched similarities give precision, recall and their F1, optionally weighted by inverse document frequency and rescaled against a baseline for readability. Because embeddings capture paraphrases and context, BERTScore correlates better with human judgments than [BLEU](/methods/bleu) and [ROUGE](/methods/rouge) on machine translation and image captioning and is robust on adversarial paraphrase detection. It is widely reported for summarization, translation, dialogue, captioning, question answering and clinical report generation, and has domain variants such as CodeBERTScore for code.',
    'BERTScore, BERTscore',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2019,
    (SELECT id FROM papers WHERE arxiv_id = '1904.09675'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'BERTScore: Evaluating Text Generation with BERT',
    'https://github.com/Tiiiger/bert_score',
    NULL,
    'always',
    ARRAY[]::text[]
),
(
    'cider',
    'CIDEr',
    'Consensus-based Image Description Evaluation (CIDEr)',
    'CIDEr (Consensus-based Image Description Evaluation), introduced in [CIDEr: Consensus-based Image Description Evaluation](/paper/1411.5726) (Vedantam, Zitnick and Parikh, 2015), scores a generated caption by how well it agrees with the consensus of many human reference captions. Captions are stemmed and represented as TF-IDF weighted n-gram vectors (n = 1 to 4), so n-grams frequent across all images get little weight; the score averages the cosine similarity between the candidate and each reference over n-gram orders. The authors also collected the PASCAL-50S and ABSTRACT-50S datasets with 50 references per image and showed that CIDEr matches human consensus better than [BLEU](/methods/bleu), [ROUGE](/methods/rouge) and METEOR. The CIDEr-D variant, which adds a length penalty and clips n-gram counts to resist gaming, is the official metric of the MS COCO captioning server, and CIDEr is the reward optimised by self-critical sequence training. It remains the headline metric for image and video captioning (COCO, NoCaps, MSR-VTT) in vision-language model papers, usually alongside SPICE and [BERTScore](/methods/bertscore).',
    'CIDEr, consensus-based image description evaluation',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2015,
    (SELECT id FROM papers WHERE arxiv_id = '1411.5726'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'CIDEr: Consensus-based Image Description Evaluation',
    'https://github.com/tylin/coco-caption',
    NULL,
    'always',
    ARRAY['CIDEr-D']
),
(
    'elo-rating',
    'Elo Rating',
    'Elo Rating',
    'The Elo rating system, devised by physicist Arpad Elo for chess and described in his 1978 book The Rating of Chessplayers, Past and Present, ranks players from pairwise game outcomes. Each player has a rating R, the expected score of A against B is E_A = 1 / (1 + 10^((R_B − R_A)/400)), and after each game the ratings move by K · (S_A − E_A), where S_A is the actual result; a 400-point gap means 10-to-1 expected odds. In machine learning, Elo ratings rank game-playing agents in self-play (AlphaGo, AlphaZero and multi-agent league training) and, since [Chatbot Arena](/paper/2403.04132), language and image generation models from crowdsourced pairwise human votes. Because online Elo updates depend on the order of comparisons, arena leaderboards fit the equivalent Bradley–Terry model by maximum likelihood with bootstrap confidence intervals, the same pairwise preference model that underlies [Reward model](/methods/reward-model) training in [RLHF](/methods/rlhf) and [Direct Preference Optimization (DPO)](/methods/direct-preference-optimization-dpo). Elo-style ratings are also produced from [LLM-as-a-judge](/methods/llm-as-a-judge) comparisons, as in [MT-Bench](/paper/2306.05685), and their sensitivity to ties, intransitivity and vote manipulation is an active research topic.',
    'Elo rating, Elo score, Elo-based',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://en.wikipedia.org/wiki/Elo_rating_system',
    'Elo rating system (Wikipedia)',
    NULL,
    NULL,
    'always',
    ARRAY['Elo Score']
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

-- Introduced banners for the three sourced metrics.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN ('lpips', 'bertscore', 'cider') AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug IN ('lpips', 'bertscore', 'cider') AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed paper links (2026-11-10). Candidates: every local latest-version
-- paper whose title/abstract matches the keyword matcher with the keywords
-- above (bare capitalised acronyms are case-sensitive). Reviewed for other
-- senses: Perplexity the company/product, and mAP inside other names; IoU,
-- PSNR, SSIM, LPIPS, CIDEr and BERTScore substrings were all metric variants
-- (mIoU, GIoU, MS-SSIM, CIDEr-D, CodeBERTScore). For the three sourced metrics,
-- local citers of the source paper (Semantic Scholar plus OpenAlex, which the
-- hourly reference backfill uses) that do not name the metric are excluded.

-- perplexity: 832 links (title/abstract names the metric).
CREATE TEMP TABLE ppl_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'perplexity'
  AND p.id IN (
    60, -- 1312.3005 One Billion Word Benchmark for Measuring Progress in Statistical Language Modeli
    85, -- 1404.3377 A Generalized Language Model as the Combination of Skipped n-grams and Modified
    306, -- 1602.02410 Exploring the Limits of Language Modeling
    336, -- 1603.06155 A Persona-Based Neural Conversation Model
    445, -- 1608.05859 Using the Output Embedding to Improve Language Models
    463, -- 1609.07843 Pointer Sentinel Mixture Models
    495, -- 1611.01578 Neural Architecture Search with Reinforcement Learning
    833, -- 1708.02182 Regularizing and Optimizing LSTM Language Models
    1000, -- 1712.00489 Visual Features for Context-Aware Speech Recognition
    1076, -- 1801.10198 Generating Wikipedia by Summarizing Long Sequences
    1332, -- 1806.04510 Dank Learning: Generating Memes Using Deep Neural Networks
    1535, -- 1810.03947 textTOvec: Deep Contextualized Neural Autoregressive Topic Models of Language wi
    1744, -- 1901.02860 Transformer-XL: Attentive Language Models Beyond a Fixed-Length Context
    1769, -- 1901.08149 TransferTransfo: A Transfer Learning Approach for Neural Network Based Conversat
    1799, -- 1902.00098 The Second Conversational Intelligence Challenge (ConvAI2)
    2200, -- 1906.01702 Improving Neural Language Models by Segmenting, Attending, and Predicting the Fu
    2523, -- 1909.04164 Knowledge Enhanced Contextual Word Representations
    2561, -- 1909.08053 Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parall
    2871, -- 1911.12385 DeFINE: DEep Factorized INput Token Embeddings for Neural Sequence Modeling
    3035, -- 2001.09977 Towards a Human-like Open-Domain Chatbot
    3214, -- 2003.05997 Efficient Content-Based Sparse Attention with Routing Transformers
    3405, -- 2004.11714 Residual Energy-Based Models for Text Generation
    3448, -- 2004.14253 GePpeTto Carves Italian into a Language Model
    3485, -- 2005.00175 Selecting Informative Contexts Improves Language Model Finetuning
    3584, -- 2005.08025 IntelliCode Compose: Code Generation Using Transformer
    3951, -- 2007.14966 Mirostat: A Neural Text Decoding Algorithm that Directly Controls Perplexity
    4126, -- 2009.04534 Pay Attention when Required
    4147, -- 2009.06978 Dialogue Response Ranking Training with Large-Scale Human Feedback Data
    4383, -- 2010.10150 Local Knowledge Powered Conversational Agents
    4818, -- 2012.15520 AraGPT2: Pre-Trained Transformer for Arabic Language Generation
    4824, -- 2012.15688 ERNIE-Doc: A Retrospective Long-Document Modeling Transformer
    4828, -- 2012.15832 Shortformer: Better Language Modeling using Shorter Inputs
    5118, -- 2103.00751 Long Document Summarization in a Low Resource Setting using Pretrained Language
    5742, -- 2105.08050 Pay Attention to MLPs
    5827, -- 2106.00085 Language Model Evaluation Beyond Perplexity
    5858, -- 2106.01451 Attention-based Contextual Language Model Adaptation for Speech Recognition
    6404, -- 2108.05036 DEMix Layers: Disentangling Domains for Modular Language Modeling
    6499, -- 2108.12409 Train Short, Test Long: Attention with Linear Biases Enables Input Length Extrap
    6538, -- 2109.01078 Skim-Attention: Learning to Focus via Document Layout
    6681, -- 2109.09115 Do Long-Range Language Models Actually Use Long-Range Context?
    6900, -- 2110.06273 Småprat: DialoGPT for Natural Language Generation of Swedish Dialogue by Transfe
    7002, -- 2110.09456 NormFormer: Improved Transformer Pretraining with Extra Normalization
    7085, -- 2110.15343 Scatterbrain: Unifying Sparse and Low-rank Attention Approximation
    7670, -- 2201.03327 Latency Adjustable Transformer Encoder for Language Understanding
    7801, -- 2201.12431 Neuro-Symbolic Language Modeling with Automaton-augmented Retrieval
    7837, -- 2202.00666 Locally Typical Sampling
    7908, -- 2202.04173 Exploring the Limits of Domain-Adaptive Training for Detoxifying Large-Scale Lan
    8232, -- 2203.06850 Efficient Language Modeling with Sparse all-MLP
    8269, -- 2203.07852 Block-Recurrent Transformers
    8414, -- 2203.13344 Linking Emergent and Natural Languages via Corpus Transfer
    8737, -- 2204.07580 mGPT: Few-Shot Learners Go Multilingual
    8755, -- 2204.08083 AfriWOZ: Corpus for Exploiting Cross-Lingual Transferability for Generation of D
    9239, -- 2205.14135 FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness
    9370, -- 2206.02369 Learning to Break the Loop: Analyzing and Mitigating Repetitions for Neural Text
    9543, -- 2206.09557 LUT-GEMM: Quantized Matrix Multiplication based on LUTs for Efficient Inference
    9789, -- 2207.06814 BERTIN: Efficient Pre-Training of a Spanish Language Model using Perplexity Samp
    9930, -- 2207.14255 Efficient Training of Language Models to Fill in the Middle
    10941, -- 2210.11689 SLING: Sino Linguistic Evaluation of Large Language Models
    11059, -- 2210.14199 Same Pre-training Loss, Better Downstream: Implicit Bias Matters for Language Mo
    11091, -- 2210.15191 Truncation Sampling as Language Model Desmoothing
    11426, -- 2211.10086 Metadata Might Make Language Models Better
    11478, -- 2211.11300 Multi-Level Knowledge Distillation for Out-of-Distribution Detection in Text
    11648, -- 2211.15029 DiffusionBERT: Improving Generative Masked Language Models with Diffusion Models
    12133, -- 2212.10440 Perplexed by Quality: A Perplexity-based Method for Adult and Harmful Content De
    12244, -- 2212.14052 Hungry Hungry Hippos: Towards Language Modeling with State Space Models
    12279, -- 2301.00774 SparseGPT: Massive Language Models Can Be Accurately Pruned in One-Shot
    12954, -- 2302.04237 Black Box Adversarial Prompting for Foundation Models
    14256, -- 2303.16618 Reference-less Analysis of Context Specificity in Translation with Personalised
    14687, -- 2304.06762 Shall We Pretrain Autoregressive Language Models with Retrieval? A Comprehensive
    14813, -- 2304.09848 Evaluating Verifiability in Generative Search Engines
    14868, -- 2304.11062 Scaling Transformer to 1M tokens and beyond with RMT
    14888, -- 2304.11389 Transformer-Based Language Model Surprisal Predicts Human Reading Times Best wit
    15671, -- 2305.10429 DoReMi: Optimizing Data Mixtures Speeds Up Language Model Pretraining
    15790, -- 2305.11759 Controlling the Extraction of Memorized Data from Large Language Models via Prom
    16020, -- 2305.13999 Towards A Unified View of Sparse Feed-Forward Network in Pretraining Large Langu
    16073, -- 2305.14342 Sophia: A Scalable Stochastic Second-order Optimizer for Language Model Pre-trai
    16107, -- 2305.14625 KNN-LM Does Not Improve Open-ended Text Generation
    16142, -- 2305.14788 Adapting Language Models to Compress Contexts
    16217, -- 2305.15183 Are Pre-trained Language Models Useful for Model Ensemble in Chinese Grammatical
    16327, -- 2305.16349 Lexinvariant Language Models
    16412, -- 2305.17266 Honey, I Shrunk the Language: Language Model Behavior at Reduced Scale
    16516, -- 2305.18403 LoRAPrune: Structured Pruning Meets Low-Rank Parameter-Efficient Fine-Tuning
    16736, -- 2306.00374 CFL: Causally Fair Language Models Through Token-level Attribute Controlled Gene
    16825, -- 2306.01160 Faster Causal Attention Over Large Sequences Through Sparse Flash Attention
    16988, -- 2306.03078 SpQR: A Sparse-Quantized Representation for Near-Lossless LLM Weight Compression
    17347, -- 2306.07629 SqueezeLLM: Dense-and-Sparse Quantization
    17513, -- 2306.09539 Block-State Transformers
    17710, -- 2306.13421 Retrieval-Pretrained Transformer: Long-range Language Modeling with Self-retriev
    17908, -- 2306.17439 Provable Robust Watermarking for AI-Generated Text
    18041, -- 2307.02599 Evade ChatGPT Detectors via A Single Space
    18213, -- 2307.06908 Generating Benchmarks for Factuality Evaluation of Language Models
    18365, -- 2307.09255 Text vectorization via transformer-based language models and n-gram perplexities
    18743, -- 2307.15504 Exploring Format Consistency for Instruction Tuning
    19024, -- 2308.04014 Continual Pre-Training of Large Language Models: How to (re)warm your model?
    19204, -- 2308.06744 Token-Scaled Logit Distillation for Ternary Weight Generative Language Models
    19408, -- 2308.09440 Scope is all you need: Transforming LLMs for HPC Code
    19577, -- 2308.10882 Giraffe: Adventures in Expanding Context Lengths in LLMs
    19943, -- 2308.16137 LM-Infinite: Zero-Shot Extreme Length Generalization for Large Language Models
    20018, -- 2309.00614 Baseline Defenses for Adversarial Attacks Against Aligned Language Models
    20097, -- 2309.01885 QuantEase: Optimization-based Quantization for Language Models
    20231, -- 2309.04564 When Less is More: Investigating Data Pruning for Pretraining LLMs at Scale
    20318, -- 2309.06126 AstroLLaMA: Towards Specialized Foundation Models in Astronomy
    20645, -- 2309.10966 MBR and QE Finetuning: Training-time Distillation of the Best and Most Expensive
    20670, -- 2309.11197 The Languini Kitchen: Enabling Language Modelling Research at Different Scales o
    20875, -- 2309.14021 LORD: Low Rank Decomposition Of Monolingual Code LLMs For One-Shot Compression
    21208, -- 2310.01041 Language Model Decoding as Direct Metrics Optimization
    21247, -- 2310.01382 Compressing LLMs: The Truth is Rarely Pure and Never Simple
    21295, -- 2310.01777 SEA: Sparse Linear Attention with Estimated Attention Mask
    21518, -- 2310.04451 AutoDAN: Generating Stealthy Jailbreak Prompts on Aligned Large Language Models
    21657, -- 2310.05869 HyperAttention: Long-context Attention in Near-Linear Time
    21816, -- 2310.07713 InstructRetro: Instruction Tuning post Retrieval-Augmented Pretraining
    21939, -- 2310.08915 Dynamic Sparse No Training: Training-Free Fine-tuning for Sparse LLMs
    22006, -- 2310.09930 FiLM: Fill-in Language Models for Any-Order Generation
    22180, -- 2310.12109 Monarch Mixer: A Simple Sub-Quadratic GEMM-Based Architecture
    22374, -- 2310.14633 Extending Input Contexts of Language Models through Training on Segmented Sequen
    22419, -- 2310.15140 AutoDAN: Interpretable Gradient-Based Adversarial Attacks on Large Language Mode
    22444, -- 2310.15393 DoGE: Domain Reweighting with Generalization Estimation
    22571, -- 2310.16834 Discrete Diffusion Modeling by Estimating the Ratios of the Data Distribution
    22620, -- 2310.17630 InstOptima: Evolutionary Multi-objective Instruction Optimization via Large Lang
    22919, -- 2311.01544 Divergent Token Metrics: Measuring degradation to prune away LLM components -- a
    22941, -- 2311.01967 The language of prompting: What linguistic properties make a prompt successful?
    23092, -- 2311.04879 LongQLoRA: Efficient and Effective Method to Extend Context Length of Large Lang
    23160, -- 2311.05908 FlashFFTConv: Efficient Convolutions for Long Sequences with Tensor Cores
    23305, -- 2311.08349 AI-generated text boundary detection with RoFT
    23426, -- 2311.09615 On Retrieval Augmentation and the Limitations of Language Model Training
    23646, -- 2311.13133 LIMIT: Less Is More for Instruction Tuning Across Evaluation Paradigms
    24269, -- 2312.02406 Efficient Online Data Mixing For Language Model Pre-Training
    24494, -- 2312.04927 Zoology: Measuring and Improving Recall in Efficient Language Models
    24577, -- 2312.06122 GTA: Gated Toxicity Avoidance for LM Performance Preservation
    24607, -- 2312.06635 Gated Linear Attention Transformers with Hardware-Efficient Training
    24723, -- 2312.07987 SwitchHead: Accelerating Transformers with Mixture-of-Experts Attention
    24818, -- 2312.09300 Self-Evaluation Improves Selective Generation in Large Language Models
    24876, -- 2312.10302 One-Shot Learning as Instruction Data Prospector for Large Language Models
    24889, -- 2312.10523 Paloma: A Benchmark for Evaluating Language Model Fit
    25061, -- 2312.13322 MonoCoder: Domain-Specific Code Language Model for HPC Codes and Tasks
    25927, -- 2401.09135 Asynchronous Local-SGD Training for Language Modeling
    26058, -- 2401.10862 Pruning for Protection: Increasing Jailbreak Resistance in Aligned LLMs Without
    26093, -- 2401.11504 With Greater Text Comes Greater Necessity: Inference-Time Training Helps Long Te
    26123, -- 2401.12005 ALMs: Authorial Language Models for Authorship Attribution
    26187, -- 2401.12819 Dynamic Layer Tying for Parameter-Efficient Transformers
    26201, -- 2401.12973 In-Context Language Learning: Architectures and Algorithms
    26432, -- 2401.16380 Rephrasing the Web: A Recipe for Compute and Data-Efficient Language Modeling
    26502, -- 2401.17377 Infini-gram: Scaling Unbounded n-gram Language Models to a Trillion Tokens
    26508, -- 2401.17505 Arrows of Time for Large Language Models
    26547, -- 2401.18079 KVQuant: Towards 10 Million Context Length LLM Inference with KV Cache Quantizat
    26707, -- 2402.01825 Fractal Patterns May Illuminate the Success of Next-Token Prediction
    26783, -- 2402.02622 DenseFormer: Enhancing Information Flow in Transformers via Depth Weighted Avera
    26843, -- 2402.03303 Nevermind: Instruction Override and Moderation in Large Language Models
    26913, -- 2402.03988 REBORN: Reinforcement-Learned Boundary Segmentation with Iterative Training for
    26940, -- 2402.04291 BiLLM: Pushing the Limit of Post-Training Quantization for LLMs
    26947, -- 2402.04347 The Hedgehog & the Porcupine: Expressive Linear Attentions with Softmax Mimicry
    27001, -- 2402.05000 Pedagogical Alignment of Large Language Models
    27301, -- 2402.09025 SLEB: Streamlining LLMs through Redundancy Verification and Elimination of Trans
    27324, -- 2402.09363 Copyright Traps for Large Language Models
    27339, -- 2402.09656 The Butterfly Effect of Model Editing: Few Edits Can Trigger Large Language Mode
    27344, -- 2402.09739 QuRating: Selecting High-Quality Data for Training Language Models
    27347, -- 2402.09759 Efficient Language Adaptive Pre-training: Extending State-of-the-Art Large Langu
    27479, -- 2402.11218 Controlled Text Generation for Large Language Model with Dynamic Attribute Graph
    27565, -- 2402.11960 DB-LLM: Accurate Dual-Binarization for Efficient LLMs
    27582, -- 2402.12170 Where is the answer? Investigating Positional Bias in Language Model Knowledge E
    27650, -- 2402.12847 Instruction-tuned Language Models are Better Knowledge Learners
    27707, -- 2402.13449 CAMELoT: Towards Large Language Models with Training-Free Consolidated Associati
    27853, -- 2402.14866 APTQ: Attention-aware Post-Training Mixed-Precision Quantization for Large Langu
    27910, -- 2402.15514 Large Scale Generative AI Text Applied to Sports and Music
    27989, -- 2402.16775 A Comprehensive Evaluation of Quantization Strategies for Large Language Models
    28088, -- 2402.17764 The Era of 1-bit LLMs: All Large Language Models are in 1.58 Bits
    28164, -- 2402.18668 Simple linear attention language models balance the recall-throughput tradeoff
    28787, -- 2403.08540 Language models scale reliably with over-training and on downstream tasks
    28875, -- 2403.09629 Quiet-STaR: Language Models Can Teach Themselves to Think Before Speaking
    28946, -- 2403.10691 MYTE: Morphology-Driven Byte Encoding for Better and Fairer Multilingual Languag
    29100, -- 2403.12544 AffineQuant: Affine Transformation Quantization for Large Language Models
    29268, -- 2403.14551 Lexicon-Level Contrastive Visual-Grounding Improves Language Modeling
    29314, -- 2403.15049 Continual Vision-and-Language Navigation
    29347, -- 2403.15450 Loops On Retrieval Augmented Generation (LoRAG)
    29368, -- 2403.15740 Protecting Copyrighted Material with Unique Identifiers in Large Language Model
    29369, -- 2403.15747 CodeShell Technical Report
    29701, -- 2404.00456 QuaRot: Outlier-Free 4-Bit Inference in Rotated LLMs
    29760, -- 2404.01019 Source-Aware Training Enables Knowledge Attribution in Language Models
    29851, -- 2404.02060 Long-context LLMs Struggle with Long In-context Learning
    29896, -- 2404.02837 Cherry on Top: Parameter Heterogeneity and Quantization in Large Language Models
    29957, -- 2404.03626 Training LLMs over Neurally Compressed Text
    30112, -- 2404.05971 Does Transformer Interpretability Transfer to RNNs?
    30372, -- 2404.09695 LoRAP: Transformer Sub-Layers Deserve Differentiated Structured Compression for
    30656, -- 2404.14395 PARAMANU-GANITA: Language Model with Mathematical Capabilities
    30702, -- 2404.15196 Setting up the Data Printer with Improved English to Ukrainian Machine Translati
    30893, -- 2404.18824 Benchmarking Benchmark Leakage in Large Language Models
    31108, -- 2405.04065 FlashBack:Efficient Retrieval-Augmented Language Modeling for Long Context Infer
    31183, -- 2405.06147 State-Free Inference of State-Space Models: The Transfer Function Approach
    31288, -- 2405.08553 Improving Transformers with Dynamically Composable Multi-Head Attention
    31642, -- 2405.14917 SliM-LLM: Salience-Driven Mixed-Precision Quantization for Large Language Models
    31690, -- 2405.15481 Sparse Spectral Training and Inference on Euclidean and Hyperbolic Neural Networ
    31825, -- 2405.17103 Empowering Character-level Text Infilling by Eliminating Sub-Tokens
    31891, -- 2405.17915 Long Context is Not Long at All: A Prospector of Long-Dependency Data for Large
    31970, -- 2405.18719 Contextual Position Encoding: Learning to Count What's Important
    32112, -- 2405.20541 Perplexed by Perplexity: Perplexity-Based Data Pruning With Small Reference Mode
    32227, -- 2406.01288 Improved Few-Shot Jailbreaking Can Circumvent Aligned Language Models and Their
    32329, -- 2406.02657 Block Transformer: Global-to-Local Language Modeling for Fast Inference
    32386, -- 2406.03589 Ranking Manipulation for Conversational Search Engines
    32398, -- 2406.03736 Your Absorbing Discrete Diffusion Secretly Models the Conditional Distributions
    32457, -- 2406.04329 Simplified and Generalized Masked Diffusion for Discrete Data
    32562, -- 2406.05678 SinkLoRA: Enhanced Efficiency and Chat Capabilities for Long-Context Large Langu
    32589, -- 2406.05981 ShiftAddLLM: Accelerating Pretrained LLMs via Post-Training Multiplication-Less
    32636, -- 2406.06484 Parallelizing Linear Transformers with the Delta Rule over Sequence Length
    32689, -- 2406.07177 TernaryLLM: Ternarized Large Language Model
    32696, -- 2406.07249 Are Protein Language Models Compute Optimal?
    32705, -- 2406.07368 When Linear Attention Meets Autoregressive Decoding: Towards More Effective and
    32729, -- 2406.07522 Samba: Simple Hybrid State Space Models for Efficient Unlimited Context Language
    32730, -- 2406.07524 Simple and Effective Masked Diffusion Language Models
    32755, -- 2406.07831 ALPS: Improved Optimization for Highly Sparse One-Shot Pruning for Large Languag
    33003, -- 2406.10594 BlockPruner: Fine-grained Pruning for Large Language Models
    33066, -- 2406.11190 Aligning Large Language Models from Self-Reference AI Feedback with one General
    33191, -- 2406.12018 CItruS: Chunked Instruction-aware State Eviction for Long Sequence Modeling
    34212, -- 2407.04620 Learning to (Learn at Test Time): RNNs with Expressive Hidden States
    34220, -- 2407.04752 SpikeLLM: Scaling up Spiking Neural Network to Large Language Models via Salienc
    34266, -- 2407.05483 Just read twice: closing the recall gap for recurrent language models
    34368, -- 2407.06654 SoftDedup: an Efficient Data Reweighting Method for Speeding Up Language Model P
    34395, -- 2407.07093 FBI-LLM: Scaling Up Fully Binarized LLMs from Scratch via Autoregressive Distill
    34593, -- 2407.09816 MaskMoE: Boosting Token-Level Learning via Routing Mask in Mixture-of-Experts
    34596, -- 2407.09835 Investigating Low-Rank Training in Transformer Language Models: Efficiency and S
    35054, -- 2407.15595 Discrete Flow Matching
    35327, -- 2407.20581 Knesset-DictaBERT: A Hebrew Language Model for Parliamentary Proceedings
    35328, -- 2407.20584 Pruning Large Language Models with Semi-Structural Adaptive Sparse Training
    35360, -- 2407.21118 Palu: Compressing KV-Cache with Low-Rank Projection
    35438, -- 2408.00655 SentenceVAE: Enable Next-sentence Prediction for Large Language Models with Fast
    35545, -- 2408.02416 Why Are My Prompts Leaked? Unraveling Prompt Extraction Threats in Customized La
    35561, -- 2408.02600 BioMamba: A Pre-trained Biomedical Language Representation Model Leveraging Mamb
    35653, -- 2408.04220 Diffusion Guided Language Modeling
    35816, -- 2408.07092 Post-Training Sparse Attention with Double Sparsity
    35847, -- 2408.07802 Kraken: Inherently Parallel Transformers For Efficient Multi-Device Inference
    35874, -- 2408.08274 BAM! Just Like That: Simple and Efficient Parameter Upcycling for Mixture of Exp
    35891, -- 2408.08554 ABQ-LLM: Arbitrary-Bit Quantized Inference Acceleration for Large Language Model
    35992, -- 2408.10441 Goldfish: Monolingual Language Models for 350 Languages
    36166, -- 2408.12857 Memory-Efficient LLM Training with Online Subspace Descent
    36222, -- 2408.13987 Focused Large Language Models are Stable Many-Shot Learners
    36249, -- 2408.14572 CURLoRA: Stable LLM Continual Fine-Tuning and Catastrophic Forgetting Mitigation
    36588, -- 2409.02908 Masked Diffusion Models are Secretly Time-Agnostic Masked Models and Exploit Ina
    36668, -- 2409.04828 POINTS: Improving Your Vision-language Model with Affordable Strategies
    36703, -- 2409.05816 Improving Pretraining Data Using Perplexity Correlations
    36791, -- 2409.07615 MOSAIC: Multiple Observers Spotting AI Content, a Robust Approach to Machine-Gen
    36797, -- 2409.07787 Stable Language Model Pre-training by Reducing Embedding Variability
    36976, -- 2409.11055 Exploring the Trade-Offs: Quantization Methods, Task Difficulty, and Model Size
    36986, -- 2409.11233 Evaluating the Impact of Compression Techniques on Task-Specific Performance of
    37051, -- 2409.12181 A Controlled Study on Long Context Extension and Generalization in LLMs
    37327, -- 2409.17066 VPTQ: Extreme Low-bit Vector Post-Training Quantization for Large Language Model
    37352, -- 2409.17481 MaskLLM: Learnable Semi-Structured Sparsity for Large Language Models
    37546, -- 2409.20361 Rotated Runtime Smooth: Training-Free Activation Smoother for accurate INT4 infe
    37727, -- 2410.02163 Adversarial Decoding: Generating Readable Documents for Adversarial Objectives
    37783, -- 2410.02660 How to Train Long-Context Language Models (Effectively)
    37790, -- 2410.02703 Selective Attention Improves Transformer
    38111, -- 2410.06264 Think While You Generate: Discrete Diffusion with Planned Denoising
    38146, -- 2410.06722 Scaling Laws for Mixed quantization in Large Language Models
    38190, -- 2410.07167 Deciphering Cross-Modal Alignment in Large Vision-Language Models with Modality
    38212, -- 2410.07505 CrossQuant: A Post-Training Quantization Method with Smaller Quantization Kernel
    38372, -- 2410.09637 ReLU's Revival: On the Entropic Overload in Normalization-Free Large Language Mo
    38478, -- 2410.10848 Crafting Narrative Closures: Zero-Shot Learning with SSM Mamba for Short Story E
    38535, -- 2410.11462 Mitigating Frequency Bias and Anisotropy in Language Model Pre-Training with Syn
    38586, -- 2410.12187 DAQ: Density-Aware Post-Training Weight-Only Quantization For LLMs
    38635, -- 2410.12788 Meta-Chunking: Learning Text Segmentation and Semantic Completion via Logical Pe
    38691, -- 2410.13276 SeerAttention: Learning Intrinsic Sparse Attention in Your LLMs
    38830, -- 2410.14713 QuAILoRA: Quantization-Aware Initialization for LoRA
    38892, -- 2410.15661 Scalable Data Ablation Approximations for Language Models through Modular Traini
    38915, -- 2410.16029 Natural GaLore: Accelerating GaLore for memory-efficient LLM Training and Fine-t
    38919, -- 2410.16077 CartesianMoE: Boosting Knowledge Sharing among Experts via Cartesian Product Rou
    39076, -- 2410.18160 Future Token Prediction -- Causal Language Modelling with Per-Token Semantic Sta
    39302, -- 2410.21357 Energy-Based Diffusion Language Models for Text Generation
    39522, -- 2411.00743 Decoding Dark Matter: Specialized Sparse Autoencoders for Interpreting Rare Conc
    39761, -- 2411.05001 Analyzing The Language of Visual Tokens
    39803, -- 2411.05735 Aioli: A Unified Optimization Framework for Language Model Data Mixing
    39874, -- 2411.07120 Lean and Mean Adaptive Optimization via Subset-Norm and Subspace-Momentum with C
    39888, -- 2411.07191 The Super Weight in Large Language Models
    40121, -- 2411.11745 BitMoD: Bit-serial Mixture-of-Datatype LLM Acceleration
    40260, -- 2411.14343 UnifiedCrawl: Aggregated Common Crawl for Affordable Adaptation of LLMs on Low-R
    40276, -- 2411.14507 FuseGPT: Learnable Layers Fusion of Generative Pre-trained Transformers
    40512, -- 2411.17426 CLOVER: Cross-Layer Orthogonal Vectors Pruning and Fine-Tuning
    40524, -- 2411.17525 Pushing the Limits of Large Language Model Quantization via the Linearity Theore
    40537, -- 2411.17685 Attamba: Attending To Multi-Token States
    40912, -- 2412.02626 Time-Reversal Provides Unsupervised Feedback to LLMs
    41009, -- 2412.03679 Evaluating Language Models as Synthetic Data Generators
    41389, -- 2412.08521 EMS: Adaptive Evict-then-Merge Strategy for Head-wise KV Cache Compression Based
    41621, -- 2412.11449 Whisper-GPT: A Hybrid Representation Audio Large Language Model
    41663, -- 2412.11834 Wonderful Matrices: Combining for a More Efficient and Effective Foundation Mode
    41867, -- 2412.14363 ResQ: Mixed-Precision Quantization of Large Language Models with Low-Rank Residu
    42112, -- 2412.17747 Deliberation in Latent Space via Differentiable Cache Augmentation
    42482, -- 2501.02406 Zero-Shot Statistical Tests for LLM-Generated Text Detection using Finite Sample
    42537, -- 2501.03152 The Scaling Law for LoRA Base on Mutual Information Upper Bound
    42584, -- 2501.03940 Not all tokens are created equal: Perplexity Attention Weighted Networks for AI
    42737, -- 2501.06425 Tensor Product Attention Is All You Need
    42768, -- 2501.06848 A General Framework for Inference-time Scaling and Steering of Diffusion Models
    43046, -- 2501.11873 Demons in the Detail: On Implementing Load Balancing Loss for Training Specializ
    43110, -- 2501.12956 GANQ: GPU-Adaptive Non-Uniform Quantization for Large Language Models
    43194, -- 2501.14315 Mitigating Forgetting in LLM Fine-Tuning via Low-Perplexity Token Learning
    43309, -- 2501.16383 RotateKV: Accurate and Robust 2-Bit KV Cache Quantization for LLMs via Outlier-A
    43377, -- 2501.17771 2SSP: A Two-Stage Framework for Structured Pruning of LLMs
    43480, -- 2501.19392 Cache Me If You Must: Adaptive Key-Value Quantization for Large Language Models
    43506, -- 2502.00511 Bridging Internal Probability and Self-Consistency for Effective and Efficient L
    43578, -- 2502.01567 Scalable Language Models with Posterior Inference of Latent Thought Vectors
    43642, -- 2502.02249 Conversation AI Dialog for Medicare powered by Finetuning and Retrieval Augmente
    43706, -- 2502.03382 High-Fidelity Simultaneous Speech-To-Speech Translation
    44096, -- 2502.08524 LLM Pretraining with Continuous Concepts
    44169, -- 2502.09622 Theoretical Benefit and Limitation of Diffusion Language Model
    44243, -- 2502.10699 Exploring Synaptic Resonance in Large Language Models: A Novel Approach to Conte
    44271, -- 2502.11034 AdaGC: Improving Training Stability for Large Language Model Pretraining
    44372, -- 2502.11779 Efficient Response Generation Method Selection for Fine-Tuning Large Language Mo
    44408, -- 2502.12081 Unhackable Temporal Rewarding for Scalable Video MLLMs
    44490, -- 2502.12928 Finedeep: Mitigating Sparse Activation in Dense LLMs via Multi-Layer Fine-Graine
    44903, -- 2502.17055 Stable-SPAM: How to Train in 4-Bit More Stably than 16-Bit Adam
    44922, -- 2502.17206 Neural Attention: A Novel Mechanism for Enhanced Expressive Power in Transformer
    44955, -- 2502.17535 The Lottery LLM Hypothesis, Rethinking What Abilities Should LLM Compression Pre
    44960, -- 2502.17607 Synthetic Text Generation for Training Large Language Models via Gradient Matchi
    45074, -- 2502.19279 CritiQ: Mining Data Quality Criteria from Human Preferences
    45083, -- 2502.19363 DataMan: Data Manager for Pre-training Large Language Models
    45084, -- 2502.19385 HDEE: Heterogeneous Domain Expert Ensemble
    45133, -- 2502.19913 SkipPipe: Partial and Reordered Pipelining Framework for Training LLMs in Hetero
    45145, -- 2502.20082 LongRoPE2: Near-Lossless LLM Context Window Scaling
    45162, -- 2502.20245 From Retrieval to Generation: Comparing Different Approaches
    45282, -- 2503.00812 Toward Stable and Consistent Evaluation Results: A New Methodology for Base Mode
    45328, -- 2503.01483 KurTail : Kurtosis-based LLM Quantization
    45333, -- 2503.01506 SampleMix: A Sample-wise Pre-training Data Mixing Strategey by Coordinating Data
    45363, -- 2503.01836 CrowdSelect: Synthetic Instruction Data Selection with Multi-LLM Wisdom
    45376, -- 2503.01901 Identifying Sensitive Weights via Post-quantization Integral
    45433, -- 2503.02812 Q-Filters: Leveraging QK Geometry for Efficient KV Cache Compression
    45731, -- 2503.06823 eMoE: Task-aware Memory Efficient Mixture-of-Experts-Based (MoE) Model Inference
    45799, -- 2503.07518 TokenButler: Token Importance is Predictable
    45820, -- 2503.07639 Mixture of Experts Made Intrinsically Interpretable
    45843, -- 2503.08067 Context-aware Biases for Length Extrapolation
    45886, -- 2503.08524 Position-Aware Depth Decay Decoding ($D^3$): Boosting Large Language Model Infer
    45908, -- 2503.08684 Perplexity Trap: PLM-Based Retrievers Overrate Low Perplexity Documents
    46926, -- 2503.22329 A Refined Analysis of Massive Activations in LLMs
    46953, -- 2503.22698 Fragile Mastery: Are Domain-Specific Trade-Offs Undermining On-Device Language M
    46980, -- 2503.23104 Fast Training of Recurrent Neural Networks with Stationary State Feedbacks
    47111, -- 2504.00695 ToReMi: Topic-Aware Data Reweighting for Dynamic Pre-Training Data Selection
    47404, -- 2504.05646 Lattice: Learning to Efficiently Compress the Memory
    47910, -- 2504.13837 Does Reinforcement Learning Really Incentivize Reasoning Capacity in LLMs Beyond
    48285, -- 2505.00033 From Attention to Atoms: Spectral Dictionary Learning for Fast, Interpretable La
    48287, -- 2505.00065 ConSens: Assessing context grounding in open-book question answering
    48300, -- 2505.00315 Mixture of Sparse Attention: Content-Based Learnable Sparse Attention via Expert
    48748, -- 2505.09738 Achieving Tokenizer Flexibility in Language Models through Heuristic Adaptation
    48762, -- 2505.10202 VQ-Logits: Compressing the Output Bottleneck of Large Language Models via Vector
    48763, -- 2505.10222 ComplexFormer: Disruptively Advancing Transformer Inference Ability via Head-Spe
    48957, -- 2505.12423 PSC: Extending Context Window of Large Language Models via Phase Shift Calibrati
    49098, -- 2505.13840 EfficientLLM: Efficiency in Large Language Models
    49176, -- 2505.14438 S2SBench: A Benchmark for Quantifying Intelligence Degradation in Speech-to-Spee
    49181, -- 2505.14464 Not All Correct Answers Are Equal: Why Your Distillation Source Matters
    49304, -- 2505.15548 Short-Range Dependency Effects on Transformer Instability and a Decomposed Atten
    49357, -- 2505.16014 Ranking Free RAG: Replacing Re-ranking with Selection in RAG for Sensitive Domai
    49612, -- 2505.18456 Anchored Diffusion Language Model
    49616, -- 2505.18495 Beyond Masked and Unmasked: Discrete Diffusion Models via Partial Masking
    49699, -- 2505.19187 LIMOPro: Reasoning Refinement for Efficient and Effective Test-time Scaling
    49733, -- 2505.19433 Can Compressed LLMs Truly Act? An Empirical Evaluation of Agentic Capabilities i
    49783, -- 2505.19893 ESLM: Risk-Averse Selective Language Modeling for Efficient Pretraining
    49881, -- 2505.20438 HAMburger: Accelerating LLM Inference via Token Smashing
    50045, -- 2505.22842 Bayesian Attention Mechanism: A Probabilistic Framework for Positional Encoding
    50054, -- 2505.22922 Scalable Parameter and Memory Efficient Pretraining for LLM: Recent Algorithmic
    50166, -- 2505.23807 DLP: Dynamic Layerwise Pruning in Large Language Models
    50267, -- 2505.24842 Cascading Adversarial Bias from Injection to Distillation in Language Models
    50414, -- 2506.01928 Esoteric Language Models
    50436, -- 2506.02204 BehaviorBox: Automated Discovery of Fine-Grained Performance Differences Between
    50515, -- 2506.03523 TokAlign: Efficient Vocabulary Adaptation via Token Alignment
    50719, -- 2506.06280 Eigenspectrum Analysis of Neural Networks without Aspect Ratio Bias
    51034, -- 2506.10892 The Diffusion Duality
    51139, -- 2506.13277 SeqPE: Transformer with Sequential Position Encoding
    51214, -- 2506.14429 LongLLaDA: Unlocking Long Context Capabilities in Diffusion LLMs
    51230, -- 2506.14681 Massive Supervised Fine-tuning Experiments Reveal How Data, Layer, and Training
    51668, -- 2507.03038 Cautious Next Token Prediction
    51875, -- 2507.10524 Mixture-of-Recursions: Learning Dynamic Recursive Depths for Adaptive Token-Leve
    52110, -- 2507.22565 Efficient Differentially Private Fine-Tuning of LLMs via Reinforcement Learning
    52182, -- 2508.02124 Trainable Dynamic Mask Sparse Attention
    52277, -- 2508.05988 Pruning the Unsurprising: Efficient Code Reasoning via First-Token Surprisal
    52331, -- 2508.08938 DeCRED: Decoder-Centric Regularization for Encoder-Decoder Based Speech Recognit
    52361, -- 2508.10395 XQuant: Breaking the Memory Wall for LLM Inference with KV Cache Rematerializati
    52598, -- 2509.00605 Gated Associative Memory: A Parallel O(N) Architecture for Efficient Sequence Mo
    52707, -- 2509.07301 Causal Attention with Lookahead Keys
    52747, -- 2509.09675 CDE: Curiosity-Driven Exploration for Efficient Reinforcement Learning in Large
    52798, -- 2509.21117 TrustJudge: Inconsistencies of LLM-as-a-Judge and How to Alleviate Them
    52967, -- 2509.22075 COSPADI: Compressing LLMs via Calibration-Guided Sparse Dictionary Learning
    53102, -- 2509.22944 SINQ: Sinkhorn-Normalized Quantization for Calibration-Free Low-Precision LLM We
    53133, -- 2510.00446 LongCodeZip: Compress Long Context for Code Language Models
    53442, -- 2510.05528 ARMOR: High-Performance Semi-Structured Pruning via Adaptive Matrix Factorizatio
    53642, -- 2510.15444 A Theoretical Study on Bridging Internal Probability and Self-Consistency for LL
    53785, -- 2510.19304 Loopholing Discrete Diffusion: Deterministic Bypass of the Sampling Wall
    53806, -- 2510.18413 Adamas: Hadamard Sparse Attention for Efficient Long-Context Inference
    54653, -- 2512.03704 DZ-TDPO: Non-Destructive Temporal Alignment for Mutable State Tracking in Long-C
    54758, -- 2512.12602 Error-Free Linear Attention is a Free Lunch: Exact Solution from Continuous-Time
    54944, -- 2512.19399 Brain-Grounded Axes for Reading and Steering LLM States
    55080, -- 2601.00671 Fast-weight Product Key Memory
    55259, -- 2601.06329 On the Fallacy of Global Token Perplexity in Spoken Language Model Evaluation
    55379, -- 2601.11061 Spurious Rewards Paradox: Mechanistically Understanding How RLVR Activates Memor
    55480, -- 2601.16018 Mecellem Models: Turkish Models Trained from Scratch and Continually Pre-trained
    55513, -- 2601.13599 Diffusion In Diffusion: Reclaiming Global Coherence in Semi-Autoregressive Diffu
    55534, -- 2601.19895 Post-LayerNorm Is Back: Stable, ExpressivE, and Deep
    55538, -- 2601.19375 Selective Steering: Norm-Preserving Control Through Discriminative Layer Selecti
    55650, -- 2601.15394 Memorization Dynamics in Knowledge Distillation for Language Models
    55787, -- 2602.03979 Likelihood-Based Reward Designs for General LLM Reasoning
    55843, -- 2602.02016 DASH: Faster Shampoo via Batched Block Preconditioning and Efficient Inverse-Roo
    55866, -- 2602.05281 Back to Basics: Revisiting Exploration in Reinforcement Learning for LLM Reasoni
    56116, -- 2602.07298 Principled Synthetic Data Enables the First Scaling Laws for LLMs in Recommendat
    56162, -- 2602.15322 On Surprising Effectiveness of Masking Updates in Adaptive Optimizers
    56218, -- 2602.10377 Hardware Co-Design Scaling Laws via Roofline Modelling for On-Device LLMs
    56234, -- 2602.17186 Selective Training for Large Vision Language Models via Visual Information Gain
    56283, -- 2602.21185 The Diffusion Duality, Chapter II: Ψ-Samplers and Efficient Curriculum
    56612, -- 2603.02188 Multi-Head Low-Rank Attention
    56731, -- 2603.15619 Mixture-of-Depths Attention
    56815, -- 2603.16077 MDM-Prime-v2: Binary Encoding and Index Shuffling Enable Scaling of Diffusion La
    56844, -- 2603.17891 RAMP: Reinforcement Adaptive Mixed Precision Quantization for Efficient On Devic
    57172, -- 2603.26164 DataFlex: A Unified Framework for Data-Centric Dynamic Training of Large Languag
    57397, -- 2604.08118 Initialisation Determines the Basin: Efficient Codebook Optimisation for Extreme
    57422, -- 2604.02340 Not All Denoising Steps Are Equal: Model Scheduling for Faster Masked Diffusion
    57425, -- 2604.10688 SCOPE: Signal-Calibrated On-Policy Distillation Enhancement with Dual-Path Adapt
    57473, -- 2604.12946 Parcae: Scaling Laws For Stable Looped Language Models
    57499, -- 2604.11748 LangFlow: Continuous Diffusion Rivals Discrete in Language Modeling
    57547, -- 2604.14430 Three-Phase Transformer
    57574, -- 2604.13902 DiPO: Disentangled Perplexity Policy Optimization for Fine-grained Exploration-E
    58048, -- 2604.17852 LLM-Codec: Neural Audio Codec Meets Language Model Objectives
    58170, -- 2604.14419 Equifinality in Mixture of Experts: Routing Topology Does Not Determine Language
    58189, -- 2604.13488 Towards Scalable Lightweight GUI Agents via Multi-role Orchestration
    58213, -- 2604.12632 Calibration-Aware Policy Optimization for Reasoning LLMs
    58329, -- 2604.15356 Sequential KV Cache Compression via Probabilistic Language Tries: Beyond the Per
    58400, -- 2604.07663 SAGE: Sign-Adaptive Gradient for Memory-Efficient LLM Optimization
    58508, -- 2604.04461 DP-OPD: Differentially Private On-Policy Distillation for Language Models
    58515, -- 2604.01178 Screening Is Enough
    58530, -- 2604.00733 Spectral Compact Training: Pre-Training Large Language Models via Permanent Trun
    58559, -- 2604.03190 Gradient Boosting within a Single Attention Layer
    58639, -- 2604.14191 Attention to Mamba: A Recipe for Cross-Architecture Distillation
    58707, -- 2604.14180 Internal Knowledge Without External Expression: Probing the Generalization Bound
    58731, -- 2603.29221 SiPaKosa: A Comprehensive Corpus of Canonical and Classical Buddhist Texts in Si
    58735, -- 2603.27914 ITQ3_S: High-Fidelity 3-bit LLM Inference via Interleaved Ternary Quantization w
    58755, -- 2603.29078 PolarQuant: Optimal Gaussian Weight Quantization via Hadamard Rotation for LLM C
    58791, -- 2603.27467 TurboAngle: Near-Lossless KV Cache Compression via Uniform Angle Quantization
    58843, -- 2603.26556 When Perplexity Lies: Generation-Focused Distillation of Hybrid Sequence Models
    58902, -- 2603.25385 GlowQ: Group-Shared LOw-Rank Approximation for Quantized LLMs
    58980, -- 2603.22755 KALAVAI: Predicting When Independent Specialist Fusion Works -- A Quantitative M
    59028, -- 2603.21475 Unified-MAS: Universally Generating Domain-Specific Nodes for Empowering Automat
    59085, -- 2601.14958 Script Sensitivity: Benchmarking Language Models on Unicode, Romanized and Mixed
    59204, -- 2603.17522 Detecting the Machine: A Comprehensive Benchmark of AI-Generated Text Detectors
    59273, -- 2603.16105 Frequency Matters: Fast Model-Agnostic Data Curation for Pruning and Quantizatio
    59313, -- 2603.15569 Mamba-3: Improved Sequence Modeling using State Space Principles
    59336, -- 2603.14923 Directional Routing in Transformers
    59401, -- 2603.14360 M^2RNN: Non-Linear RNNs with Matrix-Valued States for Scalable Language Modeling
    59441, -- 2509.22947 Induction Signatures Are Not Enough: A Matched-Compute Study of Load-Bearing Str
    59489, -- 2603.11139 H2LooP Spark Preview: Continual Pretraining of Large Language Models for Low-Lev
    59574, -- 2603.16920 Synthetic Data Domain Adaptation for ASR via LLM-based Text and Phonetic Respell
    59864, -- 2603.04854 SinhaLegal: A Benchmark Corpus for Information Extraction and Analysis in Sinhal
    59891, -- 2603.04355 Efficient Refusal Ablation in LLM through Optimal Transport
    60003, -- 2509.18577 Prior-based Noisy Text Data Filtering: Fast and Strong Alternative For Perplexit
    60167, -- 2602.23784 TradeFM: A Generative Foundation Model for Trade-flow and Market Microstructure
    60447, -- 2602.18628 Non-Interfering Weight Fields: Treating Model Parameters as a Continuously Exten
    60578, -- 2603.04428 Agent Memory Below the Prompt: Persistent Q4 KV Cache for Multi-Agent LLM Infere
    60598, -- 2602.15014 Scaling Beyond Masked Diffusion Language Models
    60970, -- 2602.08858 FlattenGPT: Depth Compression for Transformer with Layer Flattening
    61053, -- 2602.07374 TernaryLM: Memory-Efficient Language Modeling via Native 1-Bit Quantization with
    61185, -- 2602.05269 Hybrid Gated Flow (HGF): Stabilizing 1.58-bit LLMs via Selective Low-Rank Correc
    61699, -- 2601.22887 MoVE: Mixture of Value Embeddings -- A New Axis for Scaling Parametric Memory in
    62008, -- 2601.19174 SHIELD: An Auto-Healing Agentic Defense Framework for LLM Resource Exhaustion At
    62274, -- 2601.11791 Beyond Tokens: Concept-Level Training Objectives for LLMs
    62312, -- 2601.13580 Neural Organ Transplantation (NOT): Checkpoint-Based Modular Adaptation for Tran
    62585, -- 2601.16224 Limits of n-gram Style Control for LLMs via Logit-Space Injection
    62617, -- 2601.07475 ARCQuant: Boosting NVFP4 Quantization with Augmented Residual Channels for LLMs
    62669, -- 2601.14277 Which Quantization Should I Use? A Unified Evaluation of llama.cpp Quantization
    62815, -- 2601.04534 BanglaLorica: Design and Evaluation of a Robust Watermarking Algorithm for Large
    63132, -- 2601.00376 In Line with Context: Repository-Level Code Generation via Context Inlining
    63141, -- 2601.00264 S1-MMAlign: A Large-Scale, Multi-Disciplinary Dataset for Scientific Figure-Text
    63159, -- 2601.00894 When to Ponder: Adaptive Compute Allocation for Code Generation via Test-Time Tr
    63537, -- 2512.01037 When Safety Blocks Sense: Measuring Semantic Confusion in LLM Refusals
    63747, -- 2512.12537 NagaNLP: Bootstrapping NLP for Low-Resource Nagamese Creole with Human-in-the-Lo
    64106, -- 2512.04838 DAMASHA: Detecting AI in Mixed Adversarial Texts via Segmentation with Human-int
    64184, -- 2512.03343 Idea-Gated Transformers: Enforcing Semantic Coherence via Differentiable Vocabul
    64544, -- 2511.20224 DUO-TOK: Dual-Track Semantic Music Tokenizer for Vocal-Accompaniment Generation
    65041, -- 2507.11017 First-Order Error Matters: Accurate Compensation for Quantized Large Language Mo
    65059, -- 2511.10338 BhashaKritika: Building Synthetic Pretraining Data at Scale for Indic Languages
    65190, -- 2511.07842 Alignment-Aware Quantization for LLM Safety
    65378, -- 2511.03559 AILA--First Experiments with Localist Language Models
    65440, -- 2511.05560 Sample-Efficient Language Modeling with Linear Attention and Lightweight Enhance
    65561, -- 2511.00203 Diffusion LLMs are Natural Adversaries for any LLM
    65565, -- 2510.27641 SpecAttn: Speculating Sparse Attention
    65625, -- 2510.26847 Broken-Token: Filtering Obfuscated Prompts by Counting Characters-Per-Token
    65741, -- 2510.24256 From Memorization to Reasoning in the Spectrum of Loss Curvature
    65772, -- 2510.23926 Improving the Straight-Through Estimator with Zeroth-Order Information
    65908, -- 2510.21450 ParaRNN: Unlocking Parallel Training of Nonlinear RNNs for Large Language Models
    65920, -- 2510.21258 Correlation Dimension of Auto-Regressive Large Language Models
    66039, -- 2510.19482 ELUTQ: Efficient LUT-Aware Quantization for Deploying Large Language Models on E
    66072, -- 2510.19006 XGen-Q: An Explainable Domain-Adaptive LLM Framework with Retrieval-Augmented Ge
    66103, -- 2510.18439 Grounding or Guessing? Visual Signals for Detecting Hallucinations in Sign Langu
    66195, -- 2510.16805 Mixed-Precision Quantization for Language Models: Techniques and Prospects
    66785, -- 2510.07227 Where to Begin: Efficient Pretraining via Subnetwork Selection and Distillation
    66867, -- 2510.06108 Influence Functions for Efficient Data Selection in Reasoning
    66911, -- 2510.05361 MT-DAO: Multi-Timescale Distributed Adaptive Optimizers with Local Updates
    67017, -- 2509.25622 Layer-wise dynamic rank for compressing large language models
    67265, -- 2510.00219 Thoughtbubbles: an Unsupervised Method for Parallel Thinking in Latent Space
    67326, -- 2509.25996 CAST: Continuous and Differentiable Semi-Structured Sparsity-Aware Training for
    67417, -- 2509.25035 Ultra-Fast Language Generation via Discrete Diffusion Divergence Instruct
    67432, -- 2509.24930 How Well Do LLMs Imitate Human Writing Style?
    67477, -- 2509.24406 Muon: Training and Trade-offs with Latent Attention and MoE
    67847, -- 2509.20624 FS-DFM: Fast and Accurate Long Text Generation with Few-Step Diffusion Language
    68128, -- 2509.16060 SABER: Uncovering Vulnerabilities in Safety Alignment via Cross-Layer Residual C
    68247, -- 2509.14234 Compute as Teacher: Turning Inference Compute Into Reference-Free Supervision
    68340, -- 2509.12635 Positional Encoding via Token-Aware Phase Attention
    68682, -- 2509.05489 Self-Aligned Reward: Towards Effective and Efficient Reasoners
    68687, -- 2509.05218 HoPE: Hyperbolic Rotary Positional Encoding for Stable Long-Range Dependency Mod
    68693, -- 2509.10534 Decoupling the "What" and "Where" With Polar Coordinate Positional Embeddings
    68755, -- 2509.05362 AI-in-the-Loop: Privacy Preserving Real-Time Scam Detection and Conversational S
    68895, -- 2509.01092 REFRAG: Rethinking RAG based Decoding
    68902, -- 2509.01025 Any-Order Flexible Length Masked Diffusion
    68906, -- 2509.00973 Clone What You Can't Steal: Black-Box LLM Replication via Logit Leakage and Dist
    69184, -- 2508.18547 How do Humans and LLMs Process Confusing Code?
    69275, -- 2504.19793 Prompt Injection Attack to Tool Selection in LLM Agents
    69386, -- 2508.15190 SemToken: Semantic-Aware Tokenization for Efficient Long-Context Language Modeli
    69398, -- 2508.15094 Evaluating Sparse Autoencoders for Monosemantic Representation
    69508, -- 2508.13144 Signal and Noise: A Framework for Reducing Uncertainty in Language Model Evaluat
    69559, -- 2508.12491 Cost-Aware Contrastive Routing for LLMs
    69730, -- 2508.09874 Memory Decoder: A Pretrained, Plug-and-Play Memory for Large Language Models
    70101, -- 2508.04581 Share Your Attention: Transformer Weight Sharing via Matrix-based Dictionary Lea
    70120, -- 2508.04405 FlexQ: Efficient Post-training INT6 Quantization for LLM Serving via Algorithm-S
    70207, -- 2508.03332 Exploring Layer-wise Information Effectiveness for Post-Training Quantization in
    70282, -- 2508.02260 Decomposing the Entropy-Performance Exchange: The Missing Keys to Unlocking Effe
    70319, -- 2508.01918 Quantum-RAG and PunGPT2: Advancing Low-Resource Language Generation and Retrieva
    70324, -- 2508.01832 MLP Memory: Language Modeling with Retriever-pretrained External Memory
    70514, -- 2507.23083 Context-aware Rotary Position Embedding
    71175, -- 2507.10475 Can You Detect the Difference?
    71237, -- 2507.08567 AbbIE: Autoregressive Block-Based Iterative Encoder for Efficient Sequence Model
    71507, -- 2507.01844 Low-Perplexity LLM-Generated Sequences and Where To Find Them
    71533, -- 2507.01327 Reasoner for Real-World Event Detection: Scaling Reinforcement Learning via Adap
    71534, -- 2507.01299 La RoSA: Enhancing LLM Efficiency via Layerwise Rotated Sparse Activation
    71617, -- 2506.23670 Efficient Interleaved Speech Modeling through Knowledge Distillation
    71681, -- 2506.22396 QuickSilver -- Speeding up LLM Inference through Dynamic Token Halting, KV Skipp
    71824, -- 2410.21819 Self-Preference Bias in LLM-as-a-Judge
    71849, -- 2506.16659 A Minimalist Optimizer Design for LLM Pretraining
    71893, -- 2506.15553 Approximating Language Model Training Data from Weights
    72128, -- 2506.11117 ScIRGen: Synthesize Realistic and Large-Scale RAG Dataset for Scientific Researc
    72221, -- 2506.05664 BAQ: Efficient Bit Allocation Quantization for Large Language Models
    72326, -- 2506.02939 QKV Projections Require a Fraction of Their Memory
    72499, -- 2506.00288 Emergent Abilities of Large Language Models under Continued Pretraining for Lang
    72604, -- 2505.21941 Test-Time Scaling with Repeated Sampling Improves Multilingual Text Generation
    72687, -- 2505.20633 Test-Time Learning for Large Language Models
    72753, -- 2505.18883 Partition Generative Modeling: Masked Modeling Without Masks
    72760, -- 2506.12044 Why Do Some Inputs Break Low-Bit LLM Quantization?
    72851, -- 2505.16888 SPECTRE: Conditional System Prompt Poisoning to Hijack LLMs
    72910, -- 2506.11035 Tversky Neural Networks: Psychologically Plausible Deep Learning with Differenti
    73130, -- 2505.05799 MxMoE: Mixed-precision Quantization for MoE with Accuracy and Performance Co-Des
    73209, -- 2505.01731 Efficient Shapley Value-based Non-Uniform Pruning of Large Language Models
    73241, -- 2504.21553 Precision Where It Matters: A Novel Spike Aware Mixed-Precision Quantization Str
    73275, -- 2504.19898 GenCLS++: Pushing the Boundaries of Generative Classification in LLMs Through Co
    73404, -- 2504.15544 llm-jp-modernbert: A ModernBERT Model Trained on a Large-Scale Japanese Corpus w
    73461, -- 2504.13275 ChartQA-X: Generating Explanations for Visual Chart Reasoning
    73627, -- 2504.06416 Unifying Autoregressive and Diffusion-Based Sequence Generation
    73641, -- 2504.06323 Mosaic: Composite Projection Pruning for Resource-efficient LLMs
    73666, -- 2504.05180 BRIDGES: Bridging Graph Modality and Large Language Models within EDA Tasks
    74128, -- 2504.03661 MILLION: Mastering Long-Context LLM Inference Via Outlier-Immunized KV Product Q
    74208, -- 2503.06518 Towards Superior Quantization Accuracy: A Layer-sensitive Approach
    74243, -- 2503.04992 Wanda++: Pruning Large Language Models via Regional Gradients
    74260, -- 2503.04377 How can representation dimension dominate structurally pruned LLMs?
    74337, -- 2503.01478 SePer: Measure Retrieval Utility Through The Lens Of Semantic Perplexity Reducti
    74536, -- 2502.15487 ExpliCa: Evaluating Explicit Causal Reasoning in Large Language Models
    74657, -- 2502.11493 DAST: Context-Aware Compression in LLMs via Dynamic Allocation of Soft Tokens
    74658, -- 2502.11466 GiFT: Gibbs Fine-Tuning for Code Generation
    74680, -- 2410.06040 QERA: an Analytical Framework for Quantization Error Reconstruction
    74762, -- 2502.06785 DeepCrossAttention: Supercharging Transformer Residual Connections
    74768, -- 2502.06666 Automatic Evaluation of Healthcare LLMs Beyond Question-Answering
    75438, -- 2412.13148 SWAN: SGD with Normalization and Whitening Enables Stateless LLM Training
    75896, -- 2411.00300 Rationale-Guided Retrieval Augmented Generation for Medical Question Answering
    75983, -- 2410.16735 Token-Level Guided Discrete Diffusion for Membrane Protein Design
    76030, -- 2406.00800 MagR: Weight Magnitude Reduction for Enhancing Post-Training Quantization
    76614, -- 2408.03675 NACL: A General and Effective KV Cache Eviction Framework for LLMs at Inference
    76674, -- 2407.19487 RLCoder: Reinforcement Learning for Repository-Level Code Completion
    76791, -- 2407.06324 B'MOJO: Hybrid State Space Realizations of Foundation Models with Eidetic and Fa
    76839, -- 2407.12824 Whispering Experts: Neural Interventions for Toxicity Mitigation in Language Mod
    77114, -- 2406.06564 SwitchLoRA: Switched Low-Rank Adaptation Can Learn Full-Rank Information
    77510, -- 2404.02138 Topic-Based Watermarks for Large Language Models
    77765, -- 2402.16006 ASETF: A Novel Method for Jailbreak Attack on LLMs through Translate Suffix Embe
    78244, -- 2311.09325 Temperature-scaling surprisal estimates improve fit to human reading times -- bu
    78276, -- 2308.14132 Detecting Language Model Attacks with Perplexity
    78408, -- 2310.05175 Outlier Weighed Layerwise Sparsity (OWL): A Missing Secret Sauce for Pruning LLM
    81591, -- 1908.04319 Neural Text Generation with Unlikelihood Training
    81595, -- 1909.10642 Data Ordering Patterns for Neural Machine Translation: An Empirical Study
    82839, -- 2605.03849 Stream-R1: Reliability-Perplexity Aware Reward Distillation for Streaming Video
    82873, -- 2605.05566 Nonsense Helps: Prompt Space Perturbation Broadens Reasoning Exploration
    82881, -- 2605.06665 UniPool: A Globally Shared Expert Pool for Mixture-of-Experts
    83163, -- 2605.13301 Achieving Gold-Medal-Level Olympiad Reasoning via Simple and Unified Scaling
    83262, -- 2605.12466 Solve the Loop: Attractor Models for Language and Reasoning
    83284, -- 2605.02290 Distilling Long-CoT Reasoning through Collaborative Step-wise Multi-Teacher Deco
    83400, -- 2605.17842 SNLP: Layer-Parallel Inference via Structured Newton Corrections
    83463, -- 2605.18855 Delta Attention Residuals
    83538, -- 2605.19008 Learn-by-Wire Training Control Governance: Bounded Autonomous Training Under Str
    83614, -- 2605.21803 Same Architecture, Different Capacity: Optimizer-Induced Spectral Scaling Laws
    83735, -- 2605.22984 Test-Time Training Undermines Safety Guardrails
    83955, -- 2605.24786 CONF-KV: Confidence-Aware KV Cache Eviction with Mixed-Precision Storage for Lon
    83960, -- 2605.29157 Parallax: Parameterized Local Linear Attention for Language Modeling
    85732, -- 2410.17770 Small Singular Values Matter: A Random Matrix Analysis of Transformer Models
    85987, -- 2506.14562 AlphaDecay: Module-wise Weight Decay for Heavy-Tailed Balancing in LLMs
    86097, -- 2505.23049 DenoiseRotator: Enhance Pruning Robustness for LLMs via Importance Concentration
    86222, -- 2510.01240 RSAVQ: Riemannian Sensitivity-Aware Vector Quantization for Large Language Model
    86435, -- 2509.17371 SilentStriker: Toward Stealthy Bit-Flip Attacks on Large Language Models
    87177, -- 2502.14828 Fundamental Limitations in Defending LLM Finetuning APIs
    87239, -- 2506.18145 Routing Mamba: Scaling State Space Models with Mixture-of-Experts Projection
    88674, -- 2505.02344 An End-to-End Model for Logits-Based Large Language Models Watermarking
    88701, -- 2506.21602 BiMark: Unbiased Multilayer Watermarking for Large Language Models
    88720, -- 2502.09720 NestQuant: nested lattice quantization for matrix products and LLMs
    88928, -- 2505.24844 Chameleon: A Flexible Data-mixing Framework for Language Model Pretraining and F
    89158, -- 2507.03865 OrthoRank: Token Selection via Sink Token Orthogonality for Efficient LLM infere
    89161, -- 2412.04180 SKIM: Any-bit Quantization Pushing The Limits of Post-Training Quantization
    89489, -- 2501.19090 Pivoting Factorization: A Compact Meta Low-Rank Representation of Sparsity for E
    90075, -- 2502.14770 Determining Layer-wise Sparsity for Large Language Models Through a Theoretical
    91031, -- 2410.05021 DEPT: Decoupled Embeddings for Pre-training Language Models
    91143, -- 2503.18216 Adaptive Rank Allocation: Speeding Up Modern Transformers with RaNA Adapters
    91211, -- 2410.16208 Compute-Constrained Data Selection
    91422, -- 2410.23771 What is Wrong with Perplexity for Long-context Language Modeling?
    91468, -- 2406.17808 Training Free Exponential Context Extension via Cascading KV Cache
    91592, -- 2410.03735 Task-Adaptive Pretrained Language Models via Clustered-Importance Sampling
    91645, -- 2410.17174 From Attention to Activation: Unraveling the Enigmas of Large Language Models
    91653, -- 2502.00883 SimPER: A Minimalist Approach to Preference Alignment without Hyperparameters
    91779, -- 2411.06090 Concept Bottleneck Language Models For Protein Design
    91868, -- 2407.09722 Optimized Multi-Token Joint Decoding With Auxiliary Model for LLM Inference
    92165, -- 2410.10880 Fine-tuning can Help Detect Pretraining Data from Large Language Models
    92254, -- 2502.14816 Dynamic Low-Rank Sparse Adaptation for Large Language Models
    92295, -- 2410.03529 No Need to Talk: Asynchronous Mixture of Language Models
    92713, -- 2509.24198 Negative Pre-activations Differentiate Syntax
    92986, -- 2506.24106 On the Predictive Power of Representation Dispersion in Language Models
    93090, -- 2602.11871 DMAP: A Distribution Map for Text
    93153, -- 2506.05233 MesaNet: Sequence Modeling by Locally Optimal Test-Time Training
    93173, -- 2510.17206 Soft-Masked Diffusion Language Models
    93335, -- 2510.11750 PRISM: Enhancing PRotein Inverse Folding through Fine- Grained Retrieval on Stru
    93362, -- 2411.16821 Logit‑KL Flow Matching: Non‑Autoregressive Text Generation via Sampling‑Hybrid I
    93661, -- 2505.06653 Improving Block-Wise LLM Quantization by 4-bit Block-Wise Optimal Float (BOF4):
    93710, -- 2509.23488 Mapping Overlaps in Benchmarks through Perplexity in the Wild
    93853, -- 2507.04531 DP-Fusion: Token-Level Differentially Private Inference for Large Language Model
    94031, -- 2601.05144 Distilling the Thought, Watermarking the Answer: A Principle Semantic Guided Wat
    94119, -- 2602.07804 Pruning as a Cooperative Game: Surrogate-Assisted Layer Contribution Estimation
    94142, -- 2510.07782 RCPU: Rotation-Constrained Error Compensation for Structured Pruning of Large La
    94198, -- 2603.22216 Gumbel Distillation for Parallel Text Generation
    94272, -- 2512.03870 Reconstructing KV Caches with Cross-Layer Fusion for Enhanced Transformers
    94560, -- 2506.16640 Long-Context Generalization with Sparse Attention
    94598, -- 2510.10238 The Achilles’ Heel of LLMs: How Altering a Handful of Neurons Can Cripple Langua
    94691, -- 2603.01599 Boosting Entropy with Bell Box Quantization
    94852, -- 2603.17946 CARE: Covariance-Aware and Rank-Enhanced Decomposition for Enabling Multi-Head L
    94884, -- 2510.01650 The Unseen Frontier: Pushing the Limits of LLM Sparsity with Surrogate-Free ADMM
    94984, -- 2603.19688 Demystifying Supervision Data Generalization in Multimodal LMs
    94987, -- 2507.05195 Train-before-Test Harmonizes Language Model Rankings
    97932, -- 2508.15828 Z-Pruner: Post-Training Pruning of Large Language Models for Efficiency without
    97938, -- external Releasing Persimmon-8B
    97973, -- 2606.01838 LayerRoute: Input-Conditioned Adaptive Layer Skipping via LoRA Fine-Tuning for A
    98105, -- 2606.07098 SigmaScale: LLM Compression with SVD-based Low-Rank Decomposition and Learned Sc
    98177, -- external The Scaling Hypothesis Is Language-Contingent: Evidence from Cross-Linguistic Tr
    98178, -- external English Considered Harmful: How Morphological Poverty Pollutes Language Model Tr
    98207, -- 2606.07881 Breaking the Bubble: Asynchronous Pipeline Parallel Training with Bounded Weight
    98699, -- 2606.23670 Tapered Language Models
    98730, -- 2505.23878 AC-ODM: Actor--Critic Online Data Mixing for Sample-Efficient LLM Pretraining
    98761, -- 2606.24133 Holistic Data Scheduler for LLM Pre-training via Multi-Objective Reinforcement L
    98778, -- external SLM FRIDGE -ICED Model: Cross-Dimensional Manifold Projection via Quantum-Inspir
    98872, -- 1607.03827 The KIT Motion-Language Dataset
    98982, -- 2606.19317 Explaining Attention with Program Synthesis
    99066, -- 2603.02227 Routing Absorption in Sparse Attention: Why Random Gates Are Hard to Beat
    99530, -- 2606.04032 Do Transformers Need Three Projections? Systematic Study of QKV Variants
    99667, -- 2510.20280 Context-level Language Modeling by Learning Predictive Context Embeddings
    99929, -- 2601.22450 Tuning the Implicit Regularizer of Masked Diffusion Language Models: Enhancing G
    100298, -- 2601.20255 HE-SNR: Uncovering Latent Logic via Entropy for Guiding Mid-Training on SWE-benc
    100309, -- 2602.12468 Continuous Diffusion Models Can Obey Formal Syntax
    100327, -- 2602.02001 Preserve-Then-Quantize: Balancing Rank Budgets for Quantization Error Reconstruc
    100533, -- 2512.08724 Exposing Hidden Biases in Text-to-Image Models via Automated Prompt Search
    100737, -- 2505.16831 Unlearning Isn't Deletion: Investigating Reversibility of Machine Unlearning in
    100793, -- 2508.06249 In-Training Defenses Against Emergent Misalignment in Language Models
    100836, -- 2411.00759 Minibatch Optimal Transport and Perplexity Bound Estimation in Discrete Flow Mat
    100885, -- 2603.03326 Controllable and Explainable Personality Sliders for LLMs at Inference Time
    100890, -- 2604.23712 OptProver: Bridging Olympiad and Optimization through Continual Training in Form
    101107, -- 2505.12942 A3: an Analytical Low-Rank Approximation Framework for Attention
    101286, -- 2602.11408 GHOST: Unmasking Phantom States in Mamba2 via Grouped Hidden-state Output-aware
    101407, -- 2606.14122 Beyond Perplexity: UTF-8 Validity in Byte-aware Language Models
    101454, -- 2506.19935 Any-Order GPT as Masked Diffusion Model: Decoupling Formulation and Architecture
    101493, -- 2602.19619 Is Your Diffusion Sampler Actually Correct? A Sampler-Centric Evaluation of Disc
    101698, -- 2602.15563 1-Bit Wonder: Improving QAT Performance in the Low-Bit Regime through K-Means Qu
    101779, -- 2605.19966 Detecting Fluent Optimization-Based Adversarial Prompts via Sequential Entropy C
    101834, -- 2605.12906 Data Difficulty and the Generalization–Extrapolation Tradeoff in LLM Fine-Tuning
    102032, -- 2602.09316 Effective MoE-based LLM Compression by Exploiting Heterogeneous Inter-Group Expe
    102155, -- 2606.15531 Greedy Coordinate Diffusion: Effective and Semantically Coherent Adversarial Att
    102219, -- 2601.22347 Pushing the Limits of Block Rotations in Post-Training Quantization
    102288, -- 2604.05324 A Theoretical Framework for Statistical Evaluability of Generative Models
    102332, -- 2606.12411 Context-Driven Incremental Compression for Multi-Turn Dialogue Generation
    102713, -- 2607.07740 Jet-Long: Efficient Long-Context Extension with Dynamic Bifocal RoPE
    102949, -- 2604.19398 GRASPrune: Global Gating for Budgeted Structured Pruning of Large Language Model
    103142, -- 2605.00422 BWLA: Breaking the Barrier of W1AX Post-Training Quantization for LLMs
    103201, -- 2510.26083 Nirvana: A Specialized Generalist Model With Task-Aware Memory Mechanism
    103202, -- 2512.21515 Perplexity-Aware Data Scaling Law: Perplexity Landscapes Predict Performance for
    103254, -- 2508.03058 VRPO: Rethinking Value Modeling for Robust RL under Noisy Supervision in LLM Pos
    103302, -- 2601.04261 Inhibitory Attacks on Backdoor-based Fingerprinting for Large Language Models
    103380, -- 2604.18663 Beyond Explicit Refusals: Soft-Failure Attacks on Retrieval-Augmented Generation
    103400, -- 2605.15562 GiLT: Augmenting Transformer Language Models with Dependency Graphs
    103502, -- 2510.18030 From Local to Global: Revisiting Structured Pruning Paradigms for Large Language
    103738, -- 2510.07239 Red-Bandit: Test-Time Adaptation for LLM Red-Teaming via Bandit-Guided LoRA Expe
    103828, -- 2607.07964 KronQ: LLM Quantization via Kronecker-Factored Hessian
    104010, -- 2607.13124 ShortOPD: Recovering Pruned LLMs with Short-to-Long On-Policy Distillation
    104214, -- 2512.22671 Fragile Knowledge, Robust Instruction-Following: The Width Pruning Dichotomy in
    104289, -- 2509.02349 AudioCodecBench: A Comprehensive Benchmark for Audio Codec Evaluation
    104458, -- 2607.19058 Where Should Optimizer State Live? Tiered State Allocation for Memory-Efficient
    105855, -- 2605.07924 Trajectory as the Teacher: Few-Step Discrete Flow Matching via Energy-Navigated
    105859, -- 2607.24176 Where Quality Breaks in Compressed Short-Text Generation: Staged Bottleneck Loca
    106128, -- 2603.18297 Path-Constrained Mixture-of-Experts
    106292, -- 2605.01647 Beyond Perplexity: Character Distribution Signatures and the MDTA Benchmark for
    106320, -- 2603.25450 Cross-Model Disagreement as a Label-Free Correctness Signal
    106368, -- 2605.11222 ADMM-Q: An Improved Hessian-based Weight Quantizer for Post-Training Quantizatio
    107774, -- 2511.10303 Rectify Evaluation Preference: Improving LLMs’ Critique on Math Reasoning via Pe
    108712, -- 2608.02703 ARCHead: Activation-Metric Residual Correction for Large Language Model Output H
    108775, -- 2605.09015 LLiMba: Sardinian on a Single GPU -- Adapting a 3B Language Model to a Vanishing
    108858, -- 2607.19033 Content is What Remains: Invariant Speech Tokenization from Parallel Utterances
    109066, -- 2608.06111 Beyond Sequence Order: Syntax-Informed Positional Embeddings for Transformers
    109112, -- 2608.10615 Simplex Relaxation for Discrete Diffusion
    109375, -- 2608.06947 When Context Bites: Detecting RAG Poisoning via Document-Level Attention Collaps
    109519, -- 2608.17183 Benchmarking the Benchmarks: Evaluating Automated Safety Benchmarks for Small La
    109948, -- 2507.13490 Revisiting LLM Value Probing Strategies: Are They Robust and Expressive?
    110031, -- 2506.08410 Large Language Models Have Intrinsic Meta-Cognition, but Need a Good Lens
    110154, -- 2409.13745 Context-Aware Membership Inference Attacks against Pre-trained Large Language Mo
    110245, -- external PORTS: Preference-Optimized Retrievers for Tool Selection with Large Language Mo
    110255, -- external Bit-Flip Error Resilience in LLMs: A Comprehensive Analysis and Defense Framewor
    110287, -- external Collaborative Beam Search: Enhancing LLM Reasoning via Collective Consensus
    110318, -- 2509.22144 From Long to Lean: Performance-aware and Adaptive Chain-of-Thought Compression v
    110448, -- 2510.04286 SliceMoE: Routing Embedding Slices Instead of Tokens for Fine-Grained and Balanc
    110682, -- 2506.13541 Mixture of Weight-shared Heterogeneous Group Attention Experts for Dynamic Token
    110816, -- 2505.14309 Studying the Role of Input-Neighbor Overlap in Retrieval-Augmented Language Mode
    110949, -- 2508.19432 Quantized but Deceptive? A Multi-Dimensional Truthfulness Evaluation of Quantize
    111069, -- 2509.16564 MPCG: Multi-Round Persona-Conditioned Generation for Modeling the Evolution of M
    111167, -- external Analysis of Semantic and Acoustic Token Variability Across Speech, Music, and Au
    111380, -- 2506.09315 Alzheimer’s Dementia Detection Using Perplexity from Paired Large Language Model
    113189, -- 2402.17891 Weakly Supervised Co-training with Swapping Assignments for Semantic Segmentatio
    113912, -- 2609.02496 Debias-SparseGPT: Bias-Aware Pruning for Large Language Models
    113922, -- 2609.04098 Why Gated DeltaNet Survives 4-Bit Quantization: NVFP4 W4A4 for the Recurrent Hal
    114016, -- 2609.07816 Kalman Delta Networks: Uncertainty-aware Associative Memory
    114292, -- 2609.15504 How Lossless Is Lossless Speculative Decoding? The Role of Numerical Precision i
    119664, -- 2603.06302 DEX-AR: A Dynamic Explainability Method for Autoregressive Vision-Language Model
    122307, -- 2609.32429 PrismQuant: Optimal Null-Space Rotations for Grouped Quantizers
    122321, -- 2609.32712 MassAlloc Attention: Let Attention Allocate Its Own Compute
    122323, -- 2609.32704 CoWindow Attention: Full Causal Coverage Is a Collective Property
    122387, -- 2609.33586 Approximating Softmax in Pretrained LLMs: Model Sensitivity and Kernel Accelerat
    122467, -- 2609.38121 WUSH-KV: KV Cache Quantization with Data-Adaptive Transforms
    122557, -- 2610.02193 Hierarchical Continuous Diffusion Language Models
    122660, -- 2610.01153 Looping Beyond Twice: A Scalable Recipe for Looped Mixture-of-Experts
    122715, -- 2610.06833 Towards Looped Models Done Right, Part II: Rethinking at Fixed Points
    122732, -- 2610.06648 Representation-Space MMD for Diffusion Language Models
    122767, -- 2610.03978 Learning Latent Protein Languages for Autoregressive Generation
    122847, -- 2609.40127 Learning Functional Subspaces for Neural Network Compression
    123419, -- 2610.14162 Next-Concept Modeling: Fast, Parallel Coarse-to-Fine Text Generation
    123721, -- 2610.19625 DAGFormer: Global Topology Prediction for Transformer Cross-Layer Connections
    123835, -- 2610.22714 First Passage Attention
    123904, -- 2610.08738 Denoising Hierarchical Representations: Joint Continuous Diffusion for Language
    124012, -- 2610.30066 Looped Uniform Diffusion Language Models
    124150, -- external Unifying Sparsity and Discreteness: One-Shot Pruning for Quantized LLMs via Disc
    124373, -- 2601.22040 Leviathan: Decoupling Input and Output Representations in Language Models
    124629, -- external SCHTs: A Semi-Structured Dynamic Sparse Training Framework for Hardware-Efficien
    124900, -- external EIPO: Efficient Inter-Step Parallel Optimization
    124977, -- external Efficient and Simple Data Mixing All The Time
    125033, -- external FAUST: Federated Asynchronous Update with Staggered Timescales for Low-Communica
    125152, -- external Dancing in Fetters: Pareto-Optimal On-Device LLMs under Hardware Constraints
    125261, -- external TOM-Pruning: Target-aware Output Manifold for LLM Pruning
    125268, -- 2605.08755 LAQuant: A Simple Overhead-free Large Reasoning Model Quantization by Layer-wise
    125287, -- external Next-Token Prediction Enables Scalable Learning of Sleep Physiology
    125475, -- external DictLLM: Post-training Compression of Large Language Model with Dictionary Kerne
    125600, -- external Route-Consistent Adaptation for Stable Quantization of Mixture-of-Experts Models
    125647, -- external Teaching VLMs What to Say, Not How to Reason: Rethinking Counterfactual Reasonin
    125649, -- 2605.15491 Ghosted Layers: Unconstrained Activation Alignment for Recovering Layer-Pruned L
    125700, -- 2605.12476 Routers Learn the Geometry of Their Experts: Geometric Coupling in Sparse Mixtur
    125733, -- 2606.09864 Alignment Collapse Under KV Cache Quantization: Diagnosis and Mitigation
    125824, -- 2605.10793 ConQuR: Corner Aligned Activation Quantization via Optimized Rotations for LLMs
    126056, -- 2510.23891 PRO: Enabling Precise and Robust Text Watermark for Open-Source LLMs
    126145, -- external NorSA: Accelerating LLM Decoding via Normalized Sparse Activation
    126429, -- external LoopPrune: Evolutionary Module Selection with Iterative Execution for Efficient
    126592, -- external Know What You Need: Efficient Activation Checkpointing
    126613, -- external SpectralKV: Redundancy-Aware KV Cache Compression via Spectral Coreset Selection
    126830, -- external LAPrune: Logits-Aligned Scoring Proxy for KV Pruning via Vector Quantization
    126840, -- external Generation-Drift-Guided Block Pruning for Large Language Models
    126847, -- 2610.15159 Beyond Adjacent Layers: Graph-Guided Layer Fusion for Compressing Large Language
    126907, -- 2608.03648 Group Perspective Matters: Regulating Debate Relationships Can Mitigate Blind Co
    127114, -- external Block-OBS-GS: Exact Per-Block Joint Brain Surgery with Gauss–Seidel Refinement f
    127296, -- external Fine-tuning Does Not Reach All: Uneven Safety and Knowledge Dynamics in Language
    127534, -- 2510.13879 Catch Your Breath: Adaptive Computation for Self-Paced Sequence Production
    127546, -- 2602.07235 ArcMark: Distortion-Free Multi-Byte LLM Watermark via Optimal Transport
    127676, -- external Hyperbolic Language Models: From Zipf to Compute-Optimal Scaling
    127685, -- external FlashFFN: Multi-Head Decomposition Enables I/O-Aware Feed-Forward Network
    127745, -- 2605.07193 Coupling Models for One-Step Discrete Generation
    127782, -- 2609.24298 KV-COBRA: KV Cache Compression via Co-Optimized Bit-Rank Allocation
    127849, -- 2604.15694 Neural Continuous-Time Markov Chain: Discrete Diffusion via Decoupled Jump Timin
    127860, -- external Fault Tolerance in Transformers Favors Output Alignment over Hidden-State Consis
    127863, -- external MixNLQ: An Effective Post-Training Nonlinear Low-Bit Quantization Method for Lar
    127905, -- external Adaptive Fine-Tuning Scheduler for Multi-Tenant Edge LLM via Convergence-Aware B
    128111, -- 2506.24056 Logit-Gap Steering: A Forward-Pass Diagnostic for Alignment Robustness
    128112, -- 2512.17375 AdvJudge-Zero: Binary Decision Flips in LLM-as-a-Judge via Adversarial Control T
    128255, -- external A Unified Audio Language Model with Text-Aligned Factorized Audio Tokenization
    128461, -- external Rethinking Knowledge Distillation for Diffusion Language Models
    128562, -- 2603.10302 How to make the most of your masked language model for protein engineering
    128676, -- external SignRot: LLM Quantization with Massive Outlier-Aware Sign-Adjusted Rotation
    128781, -- external Empowering Masked Diffusion Models to Self-Correct with Leave-One-Out Transforme
    128846, -- 2605.31215 Fixed-Point Masked Generative Modeling
    128881, -- external How Does Pruning Change Decisions in Large Language Models?
    128912, -- 2605.13190 N-vium: Mixture-of-Exits Transformer for Accelerated Exact Generation
    128943, -- 2605.28264 Entropy Distribution as a Fingerprint for Hallucinations in Generative Models
    129114, -- external GEM: Interpretable Language Models via Geometric Embedding Alignment
    129232, -- external Towards Closing the Autoregressive Gap in Language Modeling via Entropy-Gated Co
    129405, -- 2604.01025 Fast and Accurate Probing of In-Training LLMs' Downstream Performances
    129545, -- external TRACE: Data-Free Text Reconstruction Attacks against Approximate Unlearning in L
    129582, -- external Tree Rotary Positional Encoding for Extreme Length Extrapolation from Scratch
    129961, -- 2609.11687 Structured Transforms for Low-Overhead Quantization of Language Models
    130129, -- external Towards Optimal Pre-training Data Mixtures for Empowering Reinforcement Learning
    130265, -- 2602.05902 CoreQ: Learning-Free Mismatch Correction and Successive Rounding for Quantizatio
    130714, -- external STAC-R: Subspace-Tracked Activation Compression with Residuals
    130760, -- external Taking Low-Rank LLM Compression a Step Further: A Global Perspective with Fused
    130972, -- 2501.04052 RaZeR: Pushing the Limits of NVFP4 Quantization with Redundant Zero Remapping
    131019, -- external MIRROR: Manifold Ideal Reference ReconstructOR for AI-Generated Image Detection
    131034, -- 2605.05971 Training Transformers for KV-Cache Compressibility
    131051, -- external MPQ: A Message-Passing View of Post-Training Quantization
    131181, -- external When Safety Becomes An Outlier: Understanding the Retention of LLM Safety Behavi
    131258, -- 2605.17887 Attention Sinks and Outliers in Attention Residuals
    131276, -- external Base Items Overfit, New Items Underfit: Hidden Cost of Joint Training in Increme
    131427, -- 2305.15004 LLMDet: A Third Party Large Language Models Generated Text Detection Tool
    131465, -- 2610.34886 ThinkBit: Search Codewords, Recalibrate Scales, Select by Reasoning
    131624, -- 2610.38331 Multi-Token Prediction Done Right
    131636, -- 2610.31633 BeNice! Closing Looping's Inference-Memory Gap via KV-Sharing
    131661, -- 2610.02383 The Surprising Effectiveness of Shared Memory in Looped Transformers
    131764, -- 2610.41574 BYOD: Build Your Own DLM - Efficient Autoregressive-to-Diffusion Language Model
    131791, -- 2610.32878 Advancing SVD-based LLM Compression via Layer-Wise Error Model Search
    131816, -- 2611.04449 Near-Zero Token Embeddings Silently Stall Training in Gated Sequence Models
    131958, -- 2611.08376 Muir: Linear Attention with Sensitivity-Allocated Gating and Matched-Filter Read
    132006, -- 2608.23551 ConvergeFlow: Language Flow with Provable Convergence to Token Embeddings
    132008, -- 2610.22330 Designing Transformers for Continuous Diffusion Language Models
    132009, -- 2610.33811 Rectified Language Flow
    132014, -- 2608.01240 DeltaFlow: Noise-Adaptive Bidirectional Gated Delta Networks for Embedded Langua
    132016, -- 2606.08810 Continuous Language Diffusion as a Decoder-Interface Problem
    132019, -- 2610.12898 Rethinking the Roles of Diffusion and Decoding: Predictive-State Flows for Paral
    132025, -- 2605.11125 Language Modeling with Hyperspherical Flows
    132034, -- 2605.07013 CoBit: Language Modeling with Bitstream Diffusion
    132041, -- 2610.12879 One-Step Text Generation by Seq-Drifting
    132044, -- 2609.40235 Distribution Matching Distillation for Continuous Diffusion Language Models
    132053, -- 2607.00588 A Dominant Self-Conditioning Direction Drives Repetition in Unconditional Contin
    132054, -- 2608.22244 Improving Few-Step Language Flows with Untied Self-Conditioning
    132058, -- 2610.42084 RangeSWA: Training-Free Length Extrapolation for Continuous Diffusion Language M
    132064, -- 2606.08417 Hacking Generative Perplexity: Why Unconditional Text Evaluation Needs New Metri
    132065, -- 2604.02718 Generative Frontiers: Why Evaluation Matters for Diffusion Language Models
    132066 -- 2610.06513 SOL: Measuring Gaps between Text Distributions by Double Sliced Wasserstein Metr
  );

DELETE FROM paper_method_exclusions x
USING ppl_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ppl_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ppl_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- perplexity: 21 reviewed negatives (other senses).
CREATE TEMP TABLE ppl_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'perplexity'
  AND p.id IN (
    21424, -- 2310.03214 FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation
    23360, -- 2311.09000 Factcheck-Bench: Fine-Grained Evaluation Benchmark for Automatic Fact-checkers
    35310, -- 2407.20183 MindSearch: Mimicking Human Minds Elicits Deep AI Searcher
    37096, -- 2409.12959 MMSearch: Benchmarking the Potential of Large Models as Multi-modal Search Engin
    39348, -- 2410.22349 Search Engines in an AI Era: The False Promise of Factual and Verifiable Source-
    39654, -- 2411.02959 HtmlRAG: HTML is Better Than Plain Text for Modeling Retrieved Knowledge in RAG
    40131, -- 2411.11908 LLM4DS: Evaluating Large Language Models for Data Science Code Generation
    46771, -- 2503.20201 Open Deep Search: Democratizing Search with Open-source Reasoning Agents
    51115, -- 2506.12594 A Comprehensive Survey of Deep Research: Systems, Methodologies, and Application
    60780, -- 2602.11685 DRACO: a Cross-Domain Benchmark for Deep Research Accuracy, Completeness, and Ob
    61889, -- 2601.20843 Deep Researcher with Sequential Plan Reflection and Candidates Crossover (Deep R
    63501, -- 2512.17843 ShareChat: A Dataset of Chatbot Conversations in the Wild
    66358, -- 2510.13749 Assessing Web Search Credibility and Response Groundedness in Chat Assistants
    68849, -- 2509.04499 DeepTRACE: Auditing Deep Research AI Systems for Tracking Reliability Across Cit
    77326, -- 2405.02228 Attribution in Scientific Literature: New Benchmark and Methods
    91745, -- 2406.18382 Adversarial Search Engine Optimization for Large Language Models
    106146, -- 2604.02623 Poison Once, Exploit Forever: Environment-Injected Memory Poisoning Attacks on W
    108882, -- 2606.18285 RELIANCE: Curating and Evaluating Reproductive Health Information on Social Medi
    114094, -- 2609.05463 A Three-Layer Caching Architecture for Low-Latency LLM Web Search on Commodity C
    123483, -- 2610.17016 ProbabilityBench: Model Evaluation and Calibration with Exact Ground-Truth Uncer
    123865 -- 2610.28522 DecisionPivot: A Diagnostic Benchmark for Decision Models in LLM Systems
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'metrics curation 2026-11-10: Perplexity names the search company/product, not the language-model metric'
FROM ppl_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ppl_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ppl_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- psnr: 553 links (title/abstract names the metric).
CREATE TEMP TABLE psnr_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'psnr'
  AND p.id IN (
    37, -- 1307.1166 A Novel Robust Method to Add Watermarks to Bitmap Images by Fading Technique
    1050, -- 1801.03924 The Unreasonable Effectiveness of Deep Features as a Perceptual Metric
    1504, -- 1809.07517 The 2018 PIRM Challenge on Perceptual Image Super-resolution
    2122, -- 1905.09010 PEPSI++: Fast and Lightweight Network for Image Inpainting
    3762, -- 2006.11161 iSeeBetter: Spatio-Temporal Video Super Resolution using Recurrent-Generative Ba
    3763, -- 2006.11161 iSeeBetter: Spatio-temporal video super-resolution using recurrent generative ba
    4529, -- 2011.04212 PAMS: Quantized Super-Resolution via Parameterized Max Scale
    4613, -- 2011.12490 DeRF: Decomposed Radiance Fields
    5431, -- 2104.06083 Spatiotemporal Entropy Model is All You Need for Learned Video Compression
    5557, -- 2104.10781 NTIRE 2021 Challenge on Quality Enhancement of Compressed Video: Methods and Res
    5765, -- 2105.09750 Anchor-based Plain Net for Mobile Image Super-Resolution
    6315, -- 2107.12898 StarEnhancer: Learning Real-Time and Style-Aware Image Enhancement
    7251, -- 2111.09733 Perceiving and Modeling Density is All You Need for Image Dehazing
    7660, -- 2201.02625 FlexHDR: Modelling Alignment and Exposure Uncertainties for Flexible HDR Imaging
    8218, -- 2203.06304 MISF: Multi-level Interactive Siamese Filtering for High-Fidelity Image Inpainti
    8516, -- 2203.17261 R2L: Distilling Neural Radiance Field to Neural Light Field for Efficient Novel
    8629, -- 2204.03883 Vision Transformers for Single Image Dehazing
    8652, -- 2204.04676 Simple Baselines for Image Restoration
    9024, -- 2205.07162 GLaMa: Joint Spatial and Frequency Loss for General Image Inpainting
    9136, -- 2205.11521 From Hours to Seconds: Towards 100x Faster Quantitative Phase Imaging via Differ
    9143, -- 2205.11823 Thunder: Thumbnail based Fast Lightweight Image Denoising Network
    9260, -- 2205.14756 EfficientViT: Multi-Scale Linear Attention for High-Resolution Dense Prediction
    10156, -- 2208.13029 Multi-Outputs Is All You Need For Deblur
    10183, -- 2208.14839 QuantNAS for super resolution: searching for efficient quantization-friendly arc
    10349, -- 2209.09422 Bit Allocation using Optimization
    10714, -- 2210.05553 Evaluating Unsupervised Denoising Requires Unsupervised Metrics
    11159, -- 2211.00288 Self-supervised Character-to-Character Distillation for Text Recognition
    11510, -- 2211.11827 High-Perceptual Quality JPEG Decoding via Posterior Sampling
    11732, -- 2212.00190 Mixed Neural Voxels for Fast Multi-view Video Synthesis
    12004, -- 2212.08057 Real-Time Neural Light Field on Mobile Devices
    12258, -- 2212.14593 NIRVANA: Neural Implicit Representations of Videos with Adaptive Networks and Au
    12381, -- 2301.04805 DEA-Net: Single image dehazing based on detail-enhanced convolution and content-
    12546, -- 2301.11189 Improving Statistical Fidelity for Neural Image Compression with Implicit Local
    13776, -- 2303.08331 Towards High-Quality and Efficient Video Super-Resolution via Spatial-Temporal D
    13850, -- 2303.09735 SRFormerV2: Taking a Closer Look at Permuted Self-Attention for Image Super-Reso
    14345, -- 2303.18125 Towards Nonlinear-Motion-Aware and Occlusion-Robust Rolling Shutter Correction
    14484, -- 2304.02633 HNeRV: A Hybrid Neural Representation for Videos
    14545, -- 2304.04012 Progressive Volume Distillation with Active Learning for Efficient NeRF Architec
    14770, -- 2304.08971 SurfelNeRF: Neural Surfel Radiance Fields for Online Photorealistic Reconstructi
    15784, -- 2305.11676 Learning Global-aware Kernel for Image Harmonization
    17176, -- 2306.05382 Image Blending Algorithm with Automatic Mask Generation
    17230, -- 2306.06044 GANeRF: Leveraging Discriminators to Optimize Neural Radiance Fields
    17616, -- 2306.11316 Unfolding Framework with Prior of Convolution-Transformer Mixture and Uncertaint
    19303, -- 2308.08137 SYENet: A Simple Yet Effective Network for Multiple Low-Level Vision Tasks with
    19486, -- 2308.10122 HollowNeRF: Pruning Hashgrid-Based NeRFs with Trainable Collision Mitigation
    19549, -- 2308.10584 RADIANCE: Radio-Frequency Adversarial Deep-learning Inference for Automated Netw
    19915, -- 2308.15461 Canonical Factors for Hybrid Neural Fields
    19946, -- 2308.16154 MMVP: Motion-Matrix-based Video Prediction
    20063, -- 2309.01377 Memory augment is All You Need for image restoration
    20202, -- 2309.03897 ProPainter: Improving Propagation and Transformer for Video Inpainting
    20367, -- 2309.06978 Differentiable JPEG: The Devil is in the Details
    20802, -- 2309.13038 Privacy Assessment on Reconstructed Images: Are Existing Evaluation Metrics Fait
    22946, -- 2311.02077 EmerNeRF: Emergent Spatial-Temporal Scene Decomposition via Self-Supervision
    23641, -- 2311.13073 FusionFrames: Efficient Architectural Aspects for Text-to-Video Generation Pipel
    23918, -- 2311.17094 In Search of a Data Transformation That Accelerates Neural Field Training
    23922, -- 2311.17113 Human Gaussian Splatting: Real-time Rendering of Animatable Avatars
    24215, -- 2312.01999 SRTransGAN: Image Super-Resolution using Transformer based Generative Adversaria
    24634, -- 2312.06725 EpiDiff: Enhancing Multi-View Synthesis via Localized Epipolar-Constrained Diffu
    24727, -- 2312.08136 ProNeRF: Learning Efficient Projection-Aware Ray Sampling for Fine-Grained Impli
    24829, -- 2312.09496 Image Deblurring using GAN
    24965, -- 2312.11841 MixRT: Mixed Neural Representations For Real-Time NeRF Rendering
    25043, -- 2312.13150 Splatter Image: Ultra-Fast Single-View 3D Reconstruction
    25700, -- 2401.05907 Efficient Image Deblurring Networks based on Diffusion Models
    25798, -- 2401.07049 Quantum Denoising Diffusion Models
    25837, -- 2401.07957 Machine Perceptual Quality: Evaluating the Impact of Severe Lossy Compression on
    26177, -- 2401.12561 EndoGaussian: Real-time Gaussian Splatting for Dynamic Endoscopic Scene Reconstr
    26390, -- 2401.15841 2L3: Lifting Imperfect Generated 2D Images into Accurate 3D
    27145, -- 2402.06854 Gyroscope-Assisted Motion Deblurring Network
    27816, -- 2402.14650 GaussianPro: 3D Gaussian Splatting with Progressive Propagation
    28026, -- 2402.17133 SAM-DiffSR: Structure-Modulated Diffusion Model for Image Super-Resolution
    28056, -- 2402.17414 Neural Video Compression with Feature Modulation
    28247, -- 2403.00628 Region-Adaptive Transform with Segmentation Prior for Image Compression
    28622, -- 2403.06092 Is Vanilla MLP in Neural Radiance Field Enough for Few-shot View Synthesis?
    29039, -- 2403.11821 A Survey on Quality Metrics for Text-to-Image Generation
    29261, -- 2403.14471 S2LIC: Learned Image Compression with the SwinV2 Block, Adaptive Channel-wise an
    29446, -- 2403.17006 Invertible Diffusion Models for Compressed Sensing
    29600, -- 2403.19319 Mesh2NeRF: Direct Mesh Supervision for Neural Radiance Field Representation and
    30404, -- 2404.10239 Diffusion assisted image reconstruction in optoacoustic tomography
    30985, -- 2405.00676 Spectrally Pruned Gaussian Fields with Neural Compensation
    31588, -- 2405.14477 LiteVAE: Lightweight and Efficient Variational Autoencoders for Latent Diffusion
    32008, -- 2405.19331 NPGA: Neural Parametric Gaussian Avatars
    32210, -- 2406.01003 Uni-ISP: Unifying the Learning of ISPs from Multiple Cameras
    32557, -- 2406.05649 GTR: Improving Large 3D Reconstruction Models through Geometry and Texture Refin
    32713, -- 2406.07435 Beware of Aliases -- Signal Preservation is Crucial for Robust Image Restoration
    33571, -- 2406.16359 Improving Generative Adversarial Networks for Video Super-Resolution
    33749, -- 2406.18533 On Scaling Up 3D Gaussian Splatting Training
    34317, -- 2407.06095 Accelerating Diffusion for SAR-to-Optical Image Translation via Adversarial Cons
    34391, -- 2407.07078 MoSt-DSA: Modeling Motion and Structural Interactions for Direct Multi-Frame Int
    34648, -- 2407.10632 Bidirectional Stereo Image Compression with Cross-Dimensional Entropy Model
    34798, -- 2407.12306 Splatfacto-W: A Nerfstudio Implementation of Gaussian Splatting for Unconstraine
    35368, -- 2407.21448 Accelerating Image Super-Resolution Networks with Pixel-Level Classification
    36268, -- 2408.14837 Diffusion Models Are Real-Time Game Engines
    36406, -- 2408.17060 Efficient Image Restoration through Low-Rank Adaptation and Stable Diffusion XL
    36692, -- 2409.05399 Sequential Posterior Sampling with Diffusion Models
    36882, -- 2409.09323 Implicit Neural Representations with Fourier Kolmogorov-Arnold Networks
    36995, -- 2409.11307 GS-Net: Generalizable Plug-and-Play 3D Gaussian Splatting Module
    37574, -- 2410.00262 ImmersePro: End-to-End Stereo Video Synthesis Via Implicit Disparity Learning
    37586, -- 2410.00418 Posterior-Mean Rectified Flow: Towards Minimum MSE Photo-Realistic Image Restora
    37643, -- 2410.01411 CSIM: A Copula-based similarity index sensitive to local changes for Image quali
    37986, -- 2410.04974 6DGS: Enhanced Direction-Aware Gaussian Splatting for Volumetric Rendering
    37995, -- 2410.05097 DreamSat: Towards a General 3D Model for Novel View Synthesis of Space Objects
    38321, -- 2410.08941 MeshGS: Adaptive Mesh-Aligned Gaussian Splatting for High-Quality Rendering
    38951, -- 2410.16290 A Unified Model for Compressed Sensing MRI Across Undersampling Patterns
    39015, -- 2410.17242 LVSM: A Large View Synthesis Model with Minimal 3D Inductive Bias
    39441, -- 2410.23891 AllClear: A Comprehensive Dataset and Benchmark for Cloud Removal in Satellite I
    40163, -- 2411.12450 Frequency-Aware Guidance for Blind Image Restoration via Diffusion Models
    40262, -- 2411.14384 Baking Gaussian Splatting into Diffusion Denoiser for Fast and Scalable Single-s
    40305, -- 2411.14974 3D Convex Splatting: Radiance Field Rendering with 3D Smooth Convexes
    40312, -- 2411.15028 FloAt: Flow Warping of Self-Attention for Clothing Animation Generation
    40342, -- 2411.15269 MambaIRv2: Attentive State Space Restoration
    40516, -- 2411.17459 WF-VAE: Enhancing Video VAE by Wavelet-Driven Energy Flow for Latent Video Diffu
    40785, -- 2412.00773 DIVD: Deblurring with Improved Video Diffusion Model
    40905, -- 2412.02493 RelayGS: Reconstructing Dynamic Scenes with Large-Scale and Complex Motions via
    41013, -- 2412.03748 HIIF: Hierarchical Encoding based Implicit Image Function for Continuous Super-r
    41496, -- 2412.09648 DSplats: 3D Generation by Denoising Splats-Based Multiview Diffusion Models
    41768, -- 2412.13061 VidTok: A Versatile and Open-Source Video Tokenizer
    41970, -- 2412.15550 EGSRAL: An Enhanced 3D Gaussian Splatting based Renderer with Automated Labeling
    42105, -- 2412.17726 VidTwin: Video VAE with Decoupled Structure and Dynamics
    42233, -- 2412.19584 DAS3R: Dynamics-Aware Gaussian Splatting for Static Scene Reconstruction
    42252, -- 2412.19841 FlameGS: Reconstruct flame light field via Gaussian Splatting
    43001, -- 2501.11043 BF-STVSR: B-Splines and Fourier-Best Friends for High Fidelity Spatial-Temporal
    43093, -- 2501.12637 DWTNeRF: Boosting Few-shot Neural Radiance Fields via Discrete Wavelet Transform
    44142, -- 2502.09164 E-MD3C: Taming Masked Diffusion Transformers for Efficient Zero-Shot Object Cust
    45335, -- 2503.01565 AutoLUT: LUT-Based Image Super-Resolution with Automatic Sampling and Adaptive R
    45724, -- 2503.06740 D3DR: Lighting-Aware Object Insertion in Gaussian Splatting
    45736, -- 2503.06896 CATANet: Efficient Content-Aware Token Aggregation for Lightweight Image Super-R
    46283, -- 2503.13745 FedVSR: Towards Model-Agnostic Federated Learning in Video Super-Resolution
    46420, -- 2503.15671 CHROME: Clothed Human Reconstruction with Occlusion-Resilience and Multiview-Con
    46853, -- 2503.21507 F-INR: Functional Tensor Decomposition for Implicit Neural Representations
    46883, -- 2503.21779 X$^{2}$-Gaussian: 4D Radiative Gaussian Splatting for Continuous-time Tomographi
    47293, -- 2504.03536 HumanDreamer-X: Photorealistic Single-image Human Avatars Reconstruction via Gau
    47586, -- 2504.09048 BlockGaussian: Efficient Large-Scale Scene Novel View Synthesis via Adaptive Blo
    47587, -- 2504.09069 UniFlowRestore: A General Video Restoration Framework via Flow Matching and Prom
    47700, -- 2504.10686 The Tenth NTIRE 2025 Efficient Super-Resolution Challenge Report
    47728, -- 2504.11271 Distillation-Supervised Convolutional Low-Rank Adaptation for Efficient Image Su
    47894, -- 2504.13519 Filter2Noise: Interpretable Self-Supervised Single-Image Denoising for Low-Dose
    48319, -- 2505.00687 GuideSR: Rethinking Guidance for One-Step High-Fidelity Diffusion-Based Super-Re
    48591, -- 2505.06502 PC-SRGAN: Physically Consistent Super-Resolution Generative Adversarial Network
    49319, -- 2505.15737 RUSplatting: Robust 3D Gaussian Splatting for Sparse-View Underwater Scene Recon
    49660, -- 2505.18875 Sparse VideoGen2: Accelerate Video Generation with Sparse Attention via Semantic
    50225, -- 2505.24421 pyMEAL: A Multi-Encoder Augmentation-Aware Learning for Robust and Generalizable
    50241, -- 2505.24558 Optimal Weighted Convolution for Classification and Denosing
    50482, -- 2506.03065 Sparse-vDiT: Unleashing the Power of Sparse Attention to Accelerate Video Diffus
    50490, -- 2506.03119 Controllable Human-centric Keyframe Interpolation with Generative Prior
    50789, -- 2506.07863 VIVAT: Virtuous Improving VAE Training through Artifact Mitigation
    50904, -- 2506.09045 MagCache: Fast Video Generation with Magnitude-Aware Cache
    51420, -- 2506.19656 Video Compression for Spatiotemporal Earth System Data
    51801, -- 2507.07105 4KAgent: Agentic Any Image to 4K Super-Resolution
    51829, -- 2507.07997 MGVQ: Could VQ-VAE Beat VAE? A Generalizable Tokenizer with Multi-group Quantiza
    51830, -- 2507.07997 MGVQ: Could VQ-VAE Beat VAE? A Generalizable Tokenizer with Multi-group Quantiza
    52519, -- 2508.18271 ObjFiller-3D: Consistent Multi-view 3D Inpainting via Video Diffusion Models
    52849, -- 2509.11114 WildSmoke: Ready-to-Use Dynamic 3D Smoke Assets from a Single Video in the Wild
    52858, -- 2509.14476 AToken: A Unified Tokenizer for Vision
    53390, -- 2509.24817 UP2You: Fast Reconstruction of Yourself from Unconstrained Photo Collections
    53568, -- 2510.13282 Universal Image Restoration Pre-training via Masked Degradation Classification
    53667, -- 2510.15264 DriveGen3D: Boosting Feed-Forward Driving Scene Generation with Efficient Video
    54637, -- 2511.23469 Visual Generation Tuning
    54737, -- 2512.06818 MeshSplatting: Differentiable Rendering with Opaque Meshes
    55045, -- 2512.25073 GaMO: Geometry-aware Multi-view Diffusion Outpainting for Sparse-View 3D Reconst
    55074, -- 2601.00796 AdaGaR: Adaptive Gabor Representation for Dynamic Scene Reconstruction
    55577, -- 2601.22046 PLANING: A Loosely Coupled Triangle-Gaussian Framework for Streaming 3D Reconstr
    55629, -- 2601.22904 DINO-SAE: DINO Spherical Autoencoder for High-Fidelity Image Reconstruction and
    55747, -- 2602.02914 FaceLinkGen: Rethinking Identity Leakage in Privacy-Preserving Face Recognition
    56201, -- 2602.17270 Unified Latents (UL): How to train your latents
    56528, -- 2603.05940 SLER-IR: Spherical Layer-wise Expert Routing for All-in-One Image Restoration
    56560, -- 2603.06449 CaTok: Taming Mean Flows for One-Dimensional Causal Image Tokenization
    56623, -- 2603.08982 SVG-EAR: Parameter-Free Linear Compensation for Sparse Video Generation via Erro
    56747, -- 2603.15555 Learning Latent Proxies for Controllable Single-Image Relighting
    56792, -- 2603.16844 M^3: Dense Matching Meets Multi-View Foundation Models for Monocular Gaussian Sp
    57011, -- 2603.20176 LagerNVS: Latent Geometry for Fully Neural Real-time Novel View Synthesis
    57478, -- 2604.12152 Domain-Specific Latent Representations Improve the Fidelity of Diffusion-Based M
    57503, -- 2604.07882 ReconPhys: Reconstruct Appearance and Physical Attributes from Single Video
    57717, -- 2604.21518 DiffNR: Diffusion-Enhanced Neural Representation Optimization for Sparse-View 3D
    57850, -- 2604.21984 Soft Anisotropic Diagrams for Differentiable Image Representation
    58101, -- 2604.16606 SafeLM: Unified Privacy-Aware Optimization for Trustworthy Federated Large Langu
    58324, -- 2604.09999 GIF: A Conditional Multimodal Generative Framework for IR Drop Imaging in Chip L
    58334, -- 2604.09835 F3G-Avatar : Face Focused Full-body Gaussian Avatar
    58412, -- 2604.07329 Distilling Photon-Counting CT into Routine Chest CT through Clinically Validated
    58558, -- 2604.03198 The Eleventh NTIRE 2026 Efficient Super-Resolution Challenge Report
    58790, -- 2603.27469 KV Cache Quantization for Self-Forcing Video Generation: A 33-Method Empirical S
    58858, -- 2506.06909 Gaussian Mapping for Evolving Scenes
    58916, -- 2601.03824 IDESplat: Iterative Depth Probability Estimation for Generalizable 3D Gaussian S
    59005, -- 2508.03643 Uni3R: Unified 3D Reconstruction and Semantic Understanding via Generalizable Ga
    59039, -- 2603.21615 AdaEdit: Adaptive Temporal and Channel Modulation for Flow-Based Image Editing
    59772, -- 2603.06454 Training Flow Matching: The Role of Weighting and Parameterization
    60254, -- 2602.22571 GIFSplat: Generative Prior-Guided Iterative Feed-Forward 3D Gaussian Splatting f
    60330, -- 2602.20497 LESA: Learnable Stage-Aware Predictors for Diffusion Model Acceleration
    60519, -- 2602.16711 TeCoNeRV: Leveraging Temporal Coherence for Compressible Neural Representations
    60649, -- 2602.14068 CoCoEdit: Content-Consistent Image Editing via Region Regularized Reinforcement
    61260, -- 2602.04317 JOintGS: Joint Optimization of Cameras, Bodies and 3D Gaussians for In-the-Wild
    61680, -- 2602.00221 Benchmarking Vanilla GAN, DCGAN, and WGAN Architectures for MRI Reconstruction:
    62637, -- 2601.07219 VENUS: Visual Editing with Noise Inversion Using Scene Graphs
    62915, -- 2601.03391 Edit2Restore:Few-Shot Image Restoration via Parameter-Efficient Adaptation of Pr
    63294, -- 2512.21975 RT-Focuser: A Real-Time Lightweight Model for Edge-side Image Deblurring
    63345, -- 2512.21040 A Large-Depth-Range Layer-Based Hologram Dataset for Machine Learning-Based 3D C
    63534, -- 2512.17137 SDUM: A Scalable Deep Unrolled Model for Universal MRI Reconstruction
    63729, -- 2512.12790 L-STEC: Learned Video Compression with Long-term Spatio-Temporal Enhanced Contex
    63992, -- 2512.07251 See More, Change Less: Anatomy-Aware Diffusion for Contrast Enhancement
    64110, -- 2512.04786 LaFiTe: A Generative Latent Field for 3D Native Texturing
    64237, -- 2512.02273 Progressive Image Restoration via Text-Conditioned Video Generation
    64289, -- 2512.01390 FRAMER: Frequency-Aligned Self-Distillation with Adaptive Modulation Leveraging
    64346, -- 2512.00752 Charts Are Not Images: On the Challenges of Scientific Chart Editing
    64525, -- 2511.20565 DINO-Tok: Adapting DINO for Visual Tokenizers
    64640, -- 2511.18706 CoD: A Diffusion Foundation Model for Image Compression
    64718, -- 2511.17747 AEGIS: Preserving privacy of 3D Facial Avatars with Adversarial Perturbations
    64850, -- 2511.15496 Evaluating Low-Light Image Enhancement Across Multiple Intensity Levels
    65266, -- 2511.06244 Physics-Informed Image Restoration via Progressive PDE Integration
    65304, -- 2511.05152 Splatography: Sparse multi-view dynamic Gaussian Splatting for filmmaking challe
    65473, -- 2511.01620 Learned Adaptive Kernels for High-Fidelity Image Downscaling
    65956, -- 2510.20776 CUPID: Pose-Grounded Generative 3D Reconstruction from a Single Image
    66856, -- 2510.06335 Conditional Denoising Diffusion Model-Based Robust MR Image Reconstruction from
    67527, -- 2509.24022 R^3: Reconstruction, Raw, and Rain: Deraining Directly in the Bayer Domain
    68008, -- 2509.17792 Degradation-Aware All-in-One Image Restoration via Latent Prior Encoding
    68114, -- 2509.16336 Neural Atlas Graphs for Dynamic Scene Decomposition and Editing
    68567, -- 2509.07782 RayGaussX: Accelerating Gaussian-Based Ray Marching for Real-Time and High-Quali
    68923, -- 2509.00800 SWAGSplatting: Semantic-guided Water-scene Augmented Gaussian Splatting
    69168, -- 2508.18696 ColorGS: High-fidelity Surgical Scene Reconstruction with Colored Gaussian Splat
    69483, -- 2508.14797 MF-LPR^2: Multi-Frame License Plate Image Restoration and Recognition using Opti
    69732, -- 2508.09857 OneVAE: Joint Discrete and Continuous Optimization Helps Discrete Video VAE Trai
    69738, -- 2508.09802 MUJICA: Reforming SISR Models for PBR Material Super-Resolution via Cross-Map At
    69755, -- 2508.09616 MInDI-3D: Iterative Deep Learning in 3D for Sparse-view Cone Beam Computed Tomog
    69800, -- 2508.08978 TaoCache: Structure-Maintained Video Generation Acceleration
    69877, -- 2508.07769 Dream4D: Lifting Camera-Controlled I2V towards Spatiotemporally Consistent 4D Ge
    70043, -- 2508.05343 3DGabSplat: 3D Gabor Splatting for Frequency-adaptive Radiance Field Rendering
    70262, -- 2508.02493 Low-Frequency First: Eliminating Floating Artifacts in 3D Gaussian Splatting
    70302, -- 2508.02072 HyTIP: Hybrid Temporal Information Propagation for Masked Conditional Residual V
    70507, -- 2507.23704 Enhanced Velocity Field Modeling for Gaussian Video Reconstruction
    70556, -- 2507.22304 Invisible Injections: Exploiting Vision-Language Models Through Steganographic P
    70756, -- 2507.18594 DRWKV: Focusing on Object Edges for Low-Light Image Enhancement
    71221, -- 2507.09308 AlphaVAE: Unified End-to-End RGBA Image Reconstruction and Generation with Alpha
    71263, -- 2507.07878 Single-Step Latent Diffusion for Underwater Image Restoration
    71469, -- 2507.02860 Less is Enough: Training-Free Video Diffusion Acceleration via Runtime-Adaptive
    72006, -- 2506.11777 Self-supervised Learning of Echocardiographic Video Representations via Online C
    72380, -- 2506.02093 Are Pixel-Wise Metrics Reliable for Sparse-View Computed Tomography Reconstructi
    73326, -- 2504.18251 Adaptive Weight Modified Riesz Mean Filter For High-Density Salt and Pepper Nois
    73379, -- 2504.16557 Beyond Anonymization: Object Scrubbing for Privacy-Preserving 2D and 3D Vision T
    73445, -- 2504.14238 Single Document Image Highlight Removal via A Large-Scale Real-World Dataset and
    73555, -- 2504.09097 BIGS: Bimanual Category-agnostic Interaction Reconstruction from Monocular Video
    73576, -- 2504.08125 Gen3DEval: Using vLLMs for Automatic Evaluation of Generated 3D Objects
    73593, -- 2411.06019 GaussianSpa: An "Optimizing-Sparsifying" Simplification Framework for Compact an
    74165, -- 2503.08217 S3R-GS: Streamlining the Pipeline for Large-Scale Street Scene Reconstruction
    74178, -- 2503.07946 7DGS: Unified Spatial-Temporal-Angular Gaussian Splatting
    74199, -- 2503.06898 Illuminating Darkness: Learning to Enhance Low-light Images In-the-Wild
    74400, -- 2502.20927 Goal-Oriented Semantic Communication for Wireless Video Transmission via Generat
    75110, -- 2501.13045 Sketch and Patch: Efficient 3D Gaussian Representation for Man-Made Scenes
    75246, -- 2501.05242 SEGS-SLAM: Structure-enhanced 3D Gaussian Splatting SLAM with Appearance Embeddi
    75319, -- 2501.00602 STORM: Spatio-Temporal Reconstruction Model for Large-Scale Outdoor Scenes
    75585, -- 2412.04459 Sparse Voxels Rasterization: Real-time High-fidelity Radiance Field Rendering
    75706, -- 2411.16816 SplatAD: Real-Time Lidar and Camera Rendering with 3D Gaussian Splatting for Aut
    75772, -- 2411.07795 InvisMark: Invisible and Robust Watermarking for AI-generated Image Provenance
    76404, -- 2409.08510 CasDyF-Net: Image Dehazing via Cascaded Dynamic Filters
    76568, -- 2408.09674 Implicit Grid Convolution for Multi-Scale Image Super-Resolution
    76569, -- 2408.10283 Perception-based multiplicative noise removal using SDEs
    77390, -- 2404.14533 SwinFuSR: an image fusion-inspired model for RGB-guided thermal image super-reso
    77402, -- 2404.13018 A New Multi-Picture Architecture for Learned Video Deinterlacing and Demosaicing
    77422, -- 2404.11273 Training Transformer Models by Wavelet Losses Improves Quantitative and Visual P
    77672, -- 2403.05628 AMUSE: Adaptive Multi-Segment Encoding for Dataset Watermarking
    79154, -- 2304.03895 MCDIP-ADMM: Overcoming Overfitting in DIP-based CT reconstruction
    79635, -- 2210.13445 Monocular Dynamic View Synthesis: A Reality Check
    80130, -- 2203.09388 A Text Attention Network for Spatial Deformation Robust Scene Text Image Super-r
    80577, -- 2108.05251 Improving Single-Image Defocus Deblurring: How Dual-Pixel Images Help Through Mu
    80751, -- 2104.13371 BasicVSR++: Improving Video Super-Resolution with Enhanced Propagation and Align
    80858, -- 2103.01114 Deep Perceptual Image Quality Assessment for Compression
    81118, -- 2009.11380 Combining Weighted Total Variation and Deep Image Prior for natural and medical
    81132, -- 2009.06943 AIM 2020 Challenge on Efficient Super-Resolution: Methods and Results
    82105, -- 1802.01436 Variational image compression with a scale hyperprior
    83303, -- 2605.15320 FFAvatar: Few-Shot, Feed-Forward, and Generalizable Avatar Reconstruction
    83619, -- 2605.22777 DecQ: Detail-Condensing Queries for Enhanced Reconstruction and Generation in Re
    83831, -- 2605.15042 EverAnimate: Minute-Scale Human Animation via Latent Flow Restoration
    84133, -- 2510.18362 FeatureFool: Zero-Query Fooling of Video Models via Feature Map
    84193, -- 2511.16928 Rethinking Diffusion Model-Based Video Super-Resolution: Leveraging Dense Guidan
    84350, -- 2512.05859 Edit-aware RAW reconstruction
    84453, -- 2601.00285 SV-GS: Sparse View 4D Reconstruction with Skeleton-Driven Gaussian Splatting
    84675, -- 2603.00805 NERFIFY: A Multi-Agent Framework for Turning NeRF Papers into Code
    84678, -- 2603.00906 ShiftLUT: Spatial Shift Enhanced Look-Up Tables for Efficient Image Restoration
    84679, -- 2603.00920 Spectral Super-Resolution via Adversarial Unfolding and Data-Driven Spectrum Reg
    84755, -- 2603.04975 BiEvLight: Bi-level Learning of Task-Aware Event Refinement for Low-Light Image
    84801, -- 2603.07694 Compressed-Domain-Aware Online Video Super-Resolution
    84819, -- 2603.08809 Where, What, Why: Toward Explainable 3D-GS Watermarking
    84864, -- 2603.11680 UCAN: Unified Convolutional Attention Network for Expansive Receptive Fields in
    84902, -- 2603.14001 PhyGaP: Physically-Grounded Gaussians with Polarization Cues
    85026, -- 2603.21356 FluidGaussian: Propagating Simulation-Based Uncertainty Toward Functionally-Inte
    85057, -- 2603.22893 SLARM: Streaming and Language-Aligned Reconstruction Model for Dynamic Scenes
    85164, -- 2603.27209 LightMover: Generative Light Movement with Color and Intensity Controls
    85184, -- 2603.28020 Physically Inspired Gaussian Splatting for HDR Novel View Synthesis
    85240, -- 2604.01884 GS^2: Graph-based Spatial Distribution Optimization for Compact 3D Gaussian Spla
    85343, -- 2604.10512 FreeScale: Scaling 3D Scenes via Certainty-Aware Free-View Generation
    85400, -- 2604.16540 PoInit-of-View: Poisoning Initialization of Views Transfers Across Multiple 3D R
    85464, -- 2604.26365 Beyond Fixed Formulas: Data-Driven Linear Predictor for Efficient Diffusion Mode
    85480, -- 2605.00498 GOR-IS: 3D Gaussian Object Removal In the Intrinsic Space
    85598, -- 2605.22186 Event-Illumination Collaborative Low-light Image Enhancement with a High-resolut
    85730, -- 2510.15736 Fix False Transparency by Noise Guided Splatting
    87035, -- 2412.01463 Learning Differential Pyramid Representation for Tone Mapping
    87101, -- 2506.09534 Gaussian Herding across Pens: An Optimal Transport Perspective on Global Gaussia
    87629, -- 2502.12545 IM360: Large-scale Indoor Mapping with 360 Cameras
    87847, -- 2506.01379 RadarSplat: Radar Gaussian Splatting for High-Fidelity Data Synthesis and 3D Rec
    88025, -- 2509.07662 EDFFDNet: Towards Accurate and Efficient Unsupervised Multi-Grid Image Registrat
    88059, -- 2506.23854 HiNeuS: High-fidelity Neural Surface Mitigating Low-texture and Reflective Ambig
    88103, -- 2503.06671 Emulating Self-attention with Convolution for Efficient Image Super-Resolution
    88221, -- 2510.10993 Perspective-aware 3D Gaussian Inpainting with Multi-view Consistency
    88242, -- 2506.21171 Uncover Treasures in DCT: Advancing JPEG Quality Enhancement by Exploiting Laten
    88462, -- 2411.08508 BillBoard Splatting (BBSplat): Learnable Textured Primitives for Novel View Synt
    88502, -- 2508.03118 H3R: Hybrid Multi-view Correspondence for Generalizable 3D Reconstruction
    88517, -- 2503.07856 Blind Video Super-Resolution based on Implicit Kernels
    88518, -- 2410.13195 UniGS: Modeling Unitary 3D Gaussians for Novel View Synthesis from Sparse-view I
    90104, -- 2503.15931 DnLUT: Ultra-Efficient Color Image Denoising via Channel-Aware Lookup Tables
    90126, -- 2411.09911 DiffFNO: Diffusion Fourier Neural Operator
    90138, -- 2505.00045 Noise Modeling in One Hour: Minimizing Preparation Efforts for Self-supervised L
    90152, -- 2412.01615 OmniGuard: Hybrid Manipulation Localization via Augmented Versatile Deep Image W
    90255, -- 2412.10084 ProbeSDF: Light Field Probes For Neural Surface Reconstruction
    90303, -- 2412.01553 SfM-Free 3D Gaussian Splatting via Hierarchical Training
    90566, -- 2412.20522 MaskGaussian: Adaptive 3D Gaussian Representation from Probabilistic Masks
    90599, -- 2412.14166 MegaSynth: Scaling Up 3D Scene Reconstruction with Synthesized Data
    90615, -- 2505.19793 Depth-Guided Bundle Sampling for Efficient Generalizable Neural Radiance Field R
    90739, -- 2412.06295 See Further When Clear: Curriculum Consistency Model
    90912, -- 2404.16323 LeanGaussian: Breaking Pixel or Point Cloud Correspondence in Modeling 3D Gaussi
    90929, -- 2312.02971 Image Reconstruction from Readout-Multiplexed Single-Photon Detector Arrays
    90949, -- 2503.20297 Traversing Distortion-Perception Tradeoff using a Single Score-Based Generative
    92542, -- 2606.05102 ZipSplat: Fewer Gaussians, Better Splats
    92612, -- 2505.11640 COSMO-INR: Complex Sinusoidal Modulation for Implicit Neural Representations
    92657, -- 2603.01591 FAST‑DIPS: Adjoint‑Free Analytic Steps and Hard‑Constrained Likelihood Correctio
    94207, -- 2511.02880 Nef-Net v2: Adapting Electrocardio Panorama in the wild
    94284, -- 2510.13972 Distributional Consistency Loss: Beyond Pointwise Data Terms in Inverse Problems
    94566, -- 2602.06478 Efficient-LVSM: Faster, Cheaper, and Better Large View Synthesis Model via Decou
    94584, -- 2511.06424 Turbo-DDCM: Fast and Flexible Zero-Shot Diffusion-Based Image Compression
    94801, -- 2510.03191 PQGAN: Product-Quantised Image Representation for High-Quality Image Synthesis
    94944, -- 2509.23681 QuantSparse: Comprehensively Compressing Video Diffusion Transformer with Model
    95406, -- external Spectral Security Imaging System (SSIS): Optical Authenticity for Hyperspectral
    95667, -- 2505.22335 UP-SLAM: Adaptively Structured Gaussian SLAM with Uncertainty Prediction in Dyna
    96031, -- 2603.12647 LR-SGS: Robust LiDAR-Reflectance-Guided Salient Gaussian Splatting for Self-Driv
    96122, -- 2411.15468 SplatSDF: Boosting SDF-NeRF Via Architecture-Level Fusion with Gaussian Splats
    96389, -- 2409.18122 RT-GuIDE: Real-Time Gaussian Splatting for Information-Driven Exploration
    96807, -- external GARO: Geometry-Aware Redundancy Optimization for Real-Time and High-Fidelity Dyn
    96914, -- 2504.00159 SonarSplat: Novel View Synthesis of Imaging Sonar Via Gaussian Splatting
    97033, -- 2504.17401 StereoMamba: Real-Time and Robust Intraoperative Stereo Disparity Estimation Via
    97161, -- 2506.14135 GAF: Gaussian Action Field As a 4D Representation for Dynamic World Modeling in
    97888, -- 2509.11116 SVR-GS: Spatially Variant Regularization for Probabilistic Masks in 3D Gaussian
    98028, -- external GFRRN: Explore the Gaps in Single Image Reflection Removal (AutoSOTA)
    98030, -- external PhyGaP: Physically-Grounded Gaussians with Polarization Cues (AutoSOTA)
    98033, -- external Content-Aware Frequency Encoding for Implicit Neural Representations with Fourie
    98052, -- external FastGS: Training 3D Gaussian Splatting in 100 Seconds — A Technical Report on Au
    98057, -- external ChordEdit: One-Step Low-Energy Transport for Image Editing (AutoSOTA)
    98074, -- external Statistical Characteristic-Guided Denoising for Rapid High-Resolution Transmissi
    98083, -- external Reparameterized Tensor Ring Functional Decomposition for Multi-Dimensional Data
    98100, -- external Speeding Up the Learning of 3D Gaussians with Much Shorter Gaussian Lists (AutoS
    98342, -- 1901.07261 Fast, Accurate and Lightweight Super-Resolution with Neural Architecture Search
    98558, -- 2604.13416 DF3DV-1K: A Large-Scale Dataset and Benchmark for Distractor-Free Novel View Syn
    98604, -- 2606.17480 GeneralVLA-2: Geometry-Aware Reconstruction and Governed Memory for Robot Planni
    98606, -- 2606.15659 SpatialAvatar-0: High-Quality 4D Head Avatar with Multi-Stage Reconstruction
    99212, -- 2512.14366 Optimizing Rank for High-Fidelity Implicit Neural Representations
    99664, -- 2603.18636 Attention Sparsity is Input-Stable: Training-Free Sparse Attention for Video Gen
    99699, -- 2601.10334 An analytic theory of convolutional neural network inverse problems solvers
    100040, -- 2602.22428 Calibrated Test-Time Guidance for Bayesian Inference
    100098, -- 2508.12094 Error Propagation Mechanisms and Compensation Strategies for Quantized Diffusion
    102430, -- 2605.27990 Geometry-Correct Diffusion Posterior Sampling with Denoiser-Pullback Curvature G
    102606, -- 2208.11247 SwinFIR: Revisiting the SwinIR with Fast Fourier Convolution and Improved Traini
    102675, -- 2401.06312 Video Super-Resolution Transformer with Masked Inter&Intra-Frame Attention
    103899, -- 2606.28321 StructSplat: Generalizable 3D Gaussian Splatting from Uncalibrated Sparse Views
    103915, -- 2501.11508 See In Detail: Enhancing Sparse-view 3D Gaussian Splatting with Local Depth and
    103916, -- 2605.06876 AdpSplit: Error-Driven Adaptive Splitting for Faster Geometry Discovery in 3D Ga
    104257, -- 2105.06086 HINet: Half Instance Normalization Network for Image Restoration
    104335, -- 1809.02736 Joint Autoregressive and Hierarchical Priors for Learned Image Compression
    104336, -- 2001.01568 Learned Image Compression with Discretized Gaussian Mixture Likelihoods and Atte
    104347, -- 1809.10452 Context-adaptive Entropy Model for End-to-end Optimized Image Compression
    104352, -- 1910.06244 Neural Image Compression via Non-Local Attention Optimization and Improved Conte
    104359, -- 2011.09704 Causal Contextual Prediction for Learned Image Compression
    104360, -- 2211.07273 MLIC: Multi-Reference Entropy Model for Learned Image Compression
    104363, -- 2307.15421 MLIC++: Linear Complexity Multi-Reference Entropy Modeling for Learned Image Com
    104368, -- 2107.06463 Learned Image Compression with Gaussian-Laplacian-Logistic Mixture Model and Con
    104510, -- 2607.21580 GraphVid: Interactive Graph-Controllable Video Generation
    104558, -- 2607.10495 NanoVSR: Towards Real-Time Video Super-Resolution on Edge Devices
    104720, -- 2302.14402 Neural Video Compression with Diverse Contexts
    104725, -- 2306.09818 HiNeRV: Video Compression with Hierarchical Encoding-based Neural Representation
    104978, -- external BME2: A Plug-and-Play Bridge-Based Module for Misalignment Estimation and Elimin
    105003, -- external CardioInterp: Generative Modeling for Cardiovascular OCT Interpolation with Anat
    105009, -- external Causality-driven Spatio-temporal Generator for Multi-phase Contrast-enhanced CT
    105028, -- 2507.06647 ClipGS: Clippable Gaussian Splatting for Interactive Cinematic Visualization of
    105049, -- 2509.06592 Contrastive Anatomy-Contrast Disentanglement: A Domain-General MRI Harmonization
    105069, -- 2508.10313 Cross-view Generalized Diffusion Model for Sparse-view CT Reconstruction
    105081, -- external D4Recon: Dual-stage Deformation and Dual-scale Depth Guidance for Endoscopic Rec
    105160, -- external EndoPlanar: Deformable Planar-based Gaussian Splatting for Surgical Scene Recons
    105200, -- 2508.10617 FIND-Net – Fourier-Integrated Network with Dictionary Kernels for Metal Artifact
    105317, -- external Intra- and Cross-View Enhancement for OCTA Imaging
    105656, -- external SFPFR: Self-supervised Facial Paralysis Face Reconstruction Under Few Views
    105833, -- external Wavelet-driven Decoupling and Physics-informed Mapping Network for Accelerated M
    105952, -- 2607.12362 Implicit 4D Gaussian Splatting for Fast Motion with Large Inter-Frame Displaceme
    106013, -- external Spectral and Spatial Graph Learning for Multispectral Solar Image Compression
    106604, -- 2511.13113 Semantics and Content Matter: Towards Multi-Prior Hierarchical Mamba for Image D
    106630, -- 2511.06046 StreamSTGS: Streaming Spatial and Temporal Gaussian Grids for Real-Time Free-Vie
    106833, -- 2601.10373 Towards Efficient Low-rate Image Compression with Frequency-aware Diffusion Prio
    106884, -- 2508.02051 HCF: Hierarchical Cascade Framework for Distributed Multi-Stage Image Compressio
    107226, -- 2506.05011 UAV4D: Dynamic Neural Rendering of Human-Centric UAV Imagery Using Gaussian Spla
    107403, -- 2511.07958 Burst Image Quality Assessment: A New Benchmark and Unified Framework for Multip
    107496, -- 2601.13758 GOMPSNR: Reflourish the Signal-to-Noise Ratio Metric for Audio Generation Tasks
    107498, -- 2511.17993 SD-PSFNet: Sequential and Dynamic Point Spread Function Network for Image Derain
    107528, -- 2511.06172 MambaOVSR: Multiscale Fusion with Global Motion Modeling for Chinese Opera Video
    107749, -- 2507.18034 Removing Box-Free Watermarks for Image-to-Image Models via Query-Based Reverse E
    107794, -- 2512.21710 RAPTOR: Real-Time High-Resolution UAV Video Prediction with Efficient Video Atte
    108184, -- 2508.16467 Arbitrary-Scale 3D Gaussian Super-Resolution
    108286, -- 2409.07417 Self-Supervised One-Step Diffusion Refinement for Snapshot Compressive Imaging
    108352, -- 2504.14975 CyC3D: Fine-grained Controllable 3D Generation via Cycle Consistency Regularizat
    108420, -- 2511.22262 Can Protective Watermarking Safeguard the Copyright of 3D Gaussian Splatting?
    108484, -- 2505.23134 Zero-to-Hero: Empowering Video Appearance Transfer with Zero-Shot Initialization
    108609, -- 2111.15483 ST-MFNet: A Spatio-Temporal Multi-Flow Network for Frame Interpolation
    108817, -- 2607.00861 TrajLoc: Trajectory-Attention Localization for Multi-Object Motion Control
    108945, -- 2608.05798 KVAE: Family of Tokenizers for Multimodal Generative Models
    109413, -- 1911.07559 FFA-Net: Feature Fusion Attention Network for Single Image Dehazing
    109416, -- 1804.05091 I-HAZE: a dehazing benchmark with real hazy and haze-free indoor images
    109417, -- 1804.05101 O-HAZE: a dehazing benchmark with real hazy and haze-free outdoor images
    109422, -- 2305.17654 MixDehazeNet : Mix Structure Block For Image Dehazing Network
    112425, -- 2312.09063 Image Demoireing in RAW and sRGB Domains
    112440, -- 2409.01641 Unveiling Advanced Frequency Disentanglement Paradigm for Low-Light Image Enhanc
    112499, -- 2403.11909 RoGUENeRF: A Robust Geometry-Consistent Universal Enhancer for NeRF
    112506, -- 2408.10739 TrackNeRF: Bundle Adjusting NeRF from Sparse and Noisy Views via Feature Tracks
    112717, -- 2409.08042 Thermal3D-GS: Physics-induced 3D Gaussians for Thermal Infrared Novel-view Synth
    112843, -- external Plug-and-Play Learned Proximal Trajectory for 3D Sparse-View X-Ray Computed Tomo
    112858, -- 2408.03193 Efficient NeRF Optimization - Not All Samples Remain Equally Hard
    112908, -- 2404.09571 MTKD: Multi-Teacher Knowledge Distillation for Image Super-Resolution
    113116, -- 2407.15355 Attention Beats Linear for Fast Implicit Neural Representation Generation
    113355, -- 2409.13431 Leveraging Text Localization for Scene Text Removal via Text-aware Masked Image
    113374, -- 2407.02813 Data Overfitting for On-Device Super-Resolution with Dynamic Algorithm and Compi
    113381, -- external Dual-Rain: Video Rain Removal using Assertive and Gentle Teachers
    113439, -- external Learning Equilibrium Transformation for Gamut Expansion and Color Restoration
    113486, -- 2505.00335 Efficient Neural Video Representation with Temporally Coherent Modulation
    113508, -- 2407.03239 Solving the inverse problem of microscopy deconvolution with a residual Beylkin-
    113571, -- 2403.14772 Improving Robustness to Model Inversion Attacks via Sparse Coding Architectures
    113660, -- 2508.20709 Learned Rate Control for Frame-Level Adaptive Neural Video Compression via Dynam
    113950, -- 2608.07713 Tokenizer Generator Coupling in Medical Image Generation
    113951, -- 2501.12057 Unified 3D MRI Representations via Sequence-Invariant Contrastive Learning
    114192, -- 2609.08230 ActionSplice: In-Flight Action Editing for Interactive World Models
    114207, -- 2609.12036 Pelican-Sim 1.0: A General World Model Simulator for Embodied Intelligence
    114433, -- external Center-to-Edge Denoising Diffusion Probabilistic Models with Cross-domain Attent
    114464, -- external Convolutional Implicit Neural Representation of pathology whole-slide images
    114828, -- 2405.17835 Deform3DGS: Flexible Deformation for Fast Surgical Scene Reconstruction with Gau
    114831, -- 2407.02675 Depth-Aware Endoscopic Video Inpainting
    114957, -- 2408.15217 Fundus2Video: Cross-Modal Angiography Video Generation from Static Fundus Photog
    114960, -- 2404.06128 Gaussian Pancakes: Geometrically-Regularized 3D Gaussian Splatting for Realistic
    115010, -- 2407.02974 IM-MoCo: Self-supervised MRI Motion Correction using Motion-Guided Implicit Neur
    115015, -- 2409.12539 Improving cone-beam CT Image Quality with Knowledge Distillation-Enhanced Diffus
    115094, -- external Masked Residual Diffusion Probabilistic Model with Regional Asymmetry Prior for
    115168, -- external No-New-Denoiser: A Critical Analysis of Diffusion Models for Medical Image Denoi
    115234, -- 2407.14846 Realistic Surgical Image Dataset Generation Based On 3D Gaussian Splatting
    115329, -- external Super-Field MRI Synthesis for Infant Brains Enhanced by Dual Channel Latent Diff
    115404, -- 2406.03413 UnWave-Net: Unrolled Wavelet Network for Compton Tomography Image Reconstruction
    115611, -- external Combining Frame and GOP Embeddings for Neural Video Representation
    115830, -- 2403.17638 Learning with Unreliability: Fast Few-shot Voxel Radiance Fields with Relative G
    116079, -- external Empowering Resampling Operation for Ultra-High-Definition Image Enhancement with
    116194, -- 2311.17977 GaussianShader: 3D Gaussian Splatting with Shading Functions for Reflective Surf
    116429, -- external EVS-assisted Joint Deblurring Rolling-Shutter Correction and Video Frame Interpo
    116474, -- 2402.17483 AlignMiF: Geometry-Aligned Multimodal Implicit Field for LiDAR-Camera Joint Synt
    116523, -- 2403.15679 DS-NeRV: Implicit Neural Video Representation with Decomposed Static and Dynamic
    116606, -- 2404.08921 PNeRV: Enhancing Spatial Consistency via Pyramidal Neural Representation for Vid
    116744, -- 2402.18102 Passive Snapshot Coded Aperture Dual-Pixel RGB-D Imaging
    116834, -- 2311.16728 Photo-SLAM: Real-time Simultaneous Localization and Photorealistic Mapping for M
    116860, -- 2402.17951 QN-Mixer: A Quasi-Newton MLP-Mixer Model for Sparse-View CT Reconstruction
    116888, -- 2406.09135 AdaRevD: Adaptive Patch Exiting Reversible Decoder Pushes the Limit of Image Deb
    116990, -- 2312.12274 Intrinsic Image Diffusion for Indoor Single-view Material Estimation
    117087, -- 2311.17089 Multi-Scale 3D Gaussian Splatting for Anti-Aliased Rendering
    117333, -- external Learning Compact 3D Gaussians via Feed-Forward Point Fusion
    117353, -- 2412.13897 Data-Efficient Inference of Neural Fluid Fields via SciML Foundation Model
    117359, -- external Towards Enhanced Sparse-View Tomographic Reconstruction Using 3D Gaussian Splatt
    117374, -- external GRADRobot: Geometry-Aware Rendering with Articulation and Diffusion for Robot Mo
    117424, -- 2605.11913 Vector Scaffolding: Inter-Scale Orchestration for Differentiable Image Vectoriza
    117468, -- 2511.15022 Complex-Valued 2D Gaussian Representation for Computer-Generated Holography
    117470, -- 2504.13207 BEV-GS: Feed-forward Gaussian Splatting in Bird’s-Eye-View for Road Reconstructi
    117488, -- 2608.20803 CubicSplat: Differentiable Vector Graphics via Error-Bounded Forward Relaxation
    117544, -- 2607.10792 MAC-Splat: Multi-Attribute Consistency for High-Fidelity Sparse-View Reconstruct
    117718, -- 2604.05182 LSRM: High-Fidelity Object-Centric Reconstruction via Scaled Context Windows
    117781, -- 2606.24479 MambaRaw: Selective State Space Modeling for Efficient 4K RAW Image Reconstructi
    117829, -- 2512.12236 Resolution-Agnostic Neural Operators for Multi-Rate Sparse-View CT
    117905, -- 2607.23341 Stabilizing Deep Reconstruction Operators with Contractive Anchoring
    117936, -- 2607.16320 The Devil Is in the Dark Pixels: Toward Brightness Bias-Robust Denoising
    118543, -- 2605.22011 Rethinking Token Reduction for Diffusion Models via Output-Similarity-Awareness
    118608, -- 2607.02643 BiSLW: Bi-Spectral Latent Watermarking for Generative Diffusion Models
    119231, -- 2607.19100 FlexiAvatar: Unified 3D Gaussian Human Avatars Under Arbitrary Body Visibility
    119394, -- 2608.02990 EmbodiedVAE: Disentangled Video VAE for Efficient and Controllable Embodied Mani
    119478, -- 2603.07192 FastSTAR: Spatiotemporal Token Pruning for Efficient Autoregressive Video Synthe
    119846, -- external TopNet: Transformer-Efficient Occupancy Prediction Network for Octree-Structured
    119861, -- external Perceptual Video Compression with Neural Wrapping
    119976, -- external LC-Mamba: Local and Continuous Mamba with Shifted Windows for Frame Interpolatio
    120119, -- 2503.12535 SPC-GS: Gaussian Splatting with Semantic-Prompt Consistency for Indoor Open-Worl
    120154, -- 2504.00219 LITA-GS: Illumination-Agnostic Novel View Synthesis via Reference-Free 3D Gaussi
    120317, -- 2504.06815 SVG-IR: Spatially-Varying Gaussian Splatting for Inverse Rendering
    120355, -- 2412.09723 MAC-Ego3D: Multi-Agent Gaussian Consensus for Real-Time Collaborative Ego-Motion
    120428, -- external Exposure-slot: Exposure-centric Representations Learning with Slot-in-Slot Atten
    120626, -- external Learned Binocular-Encoding Optics for RGBD Imaging Using Joint Stereo and Focus
    120721, -- external Polarization State Tracing for Reflection Removal and Color-Consistent Reconstru
    120943, -- external Retrieve-to-Restore: Efficient All-in-One Image Restoration with a Retrieval-Bas
    120951, -- external 3D Gaussian Splatting from Unposed Spike Stream
    120961, -- external Perceptual Neural Video Compression with Color Separation and Rank Chain
    120963, -- external FlashDecoder: Real-Time Latent-to-Pixel Streaming Decoder with Transformers
    121113, -- external Gradient Knows Best: Mixed-Precision Quantization via Gradient-Guided Bit Alloca
    121140, -- external RAPID: Reusing Attention Sparsity with Inter-step Adaptation for Efficient Video
    121165, -- external Degradation-Consistent Test-Time Adaptation for All-in-One Image Restoration
    121476, -- external AeroGS: Scale-Aware Gaussian Splatting for Pose-Free Dynamic UAV Scene Reconstru
    121531, -- external iSplat: Iterative Learning for Fine-Grained Gaussian Splatting
    121557, -- external Similarity-Consistent Likelihood Diffusion enables Hidden Person Detection from
    121630, -- external FastGaMer: Efficient GainMap Learning for Practical Inverse Tone Mapping
    121751, -- 2602.20328 GSNR: Graph Smooth Null-Space Representation for Inverse Problems
    122089, -- 2609.20633 Refinement Is Inherently Editable: Training-Free Prompt-to-Prompt Image Editing
    122365, -- 2609.35734 GeoVerse: World-Consistent Novel View Synthesis in Geometric Latent Space
    122422, -- 2609.31620 FuseReg: Regularizing Layer Fusion Mitigates the Reconstruction-Generation Gap i
    122463, -- 2609.39222 DC-SAE: Deep Compression Semantic Autoencoder for Faster Diffusion Convergence
    122565, -- 2610.00483 PixelDense: Dense Prediction as Representation Alignment for Pixel Diffusion
    122587, -- 2610.02201 SILSA: Sliding-Window Slice Latents for Topology-Preserving High-Resolution 3D G
    122755, -- 2610.05739 HLA-WM: Hybrid Linear Attention for Long-Horizon Video World Models
    122775, -- 2605.16817 Adaptive Fused Prior Transfer for Controllable Generative Image Compression
    122916, -- 2610.04722 NAMVIS: Next-Scale Autoregressive Multi-View Image Synthesis
    122947, -- 2610.12229 VibeEdit: Image Editing with Canvas Instructions
    123019, -- 2111.11745 Intriguing Findings of Frequency Selection for Image Deblurring
    123020, -- 2407.16993 LoFormer: Local Frequency Transformer for Image Deblurring
    123198, -- 2610.09116 SPLATIFY: Reproduce, Discover, Innovate! From Papers and Ideas to Trainable 3DGS
    123382, -- 2610.14726 LightVAE: Towards Compact and Efficient Video Autoencoders
    123593, -- 2610.06598 SimForcing: Distilling Simulation Motion Priors into Real-Domain Robot World Mod
    123966, -- 2610.29441 Sparsity Should Be ALLOTted by Output: Training-Free Allocation of Block-Sparse
    124069, -- 2610.30468 SplatLab: Autonomous Scientific Discovery for 3DGS Research
    124074, -- 1904.06457 YouTube UGC Dataset for Video Compression Research
    124277, -- 2605.08298 What Cohort INRs Encode, and Where to Freeze Them
    124850, -- external Deformable 2D Gaussian Splatting
    124908, -- external Rate-Constrained Edge Metadata for Sender–Receiver Generative Video Super-Resolu
    125026, -- 2603.12873 TRACE: Structure-Aware Character Encoding for Robust and Generalizable Document
    125074, -- 2609.30258 Temporal Gradient Inversion for Private Trajectory Reconstruction in Embodied Re
    125114, -- external Magnetic Resonance Unpaired Image Translation with Pseudometric Schrödinger Brid
    125163, -- external DSAD: Dynamic Soft Anisotropic Diagrams for Reduced-Order Video Representation
    125532, -- external UltraVoxelGS: Voxel-First Feed-Forward Gaussian Splatting for 3D Ultrasound Reco
    125805, -- external Stroke-Audited Quadratic Bezier Splatting with Structural Initialization for Eff
    125949, -- external Robust Reversible Recovery for Adversarially Protected JPEG Images
    126377, -- external T$^2$-Splat: Adaptive Topology Mesh Splatting with Texture Residuals
    126899, -- 2605.07910 One World, Dual Timeline: Decoupled Spatio-Temporal Gaussian Scene Graph for 4D
    127368, -- external AsymPipe: Accelerating Large-scale DiTs Image Editing via Asymmetry-Aware Pipeli
    128586, -- external Who Wrote This Paper? Autonomous Scientific Discovery for 3DGS Research
    128891, -- 2609.36433 RA-CFGCache: From Branch-Level Criteria to Guided-Risk Control under Classifier-
    128902, -- external RigPAPR: Rig-Based Animation of Static Neural Point Clouds from a Single-View Vi
    129306, -- external NIKA: Efficient Neural Video Representation via Structured Latent Diversity
    129515, -- external Anatomy-Preserving Unpaired Medical Image Translation via Shared Latent Anchorin
    129516, -- external Seeing but Not Detecting: Privacy-Preserving Scene Text Attack via Hybrid Advers
    129576, -- external Tethered Predictive-Inertial Proposals with Objective Verification for Diffusion
    129665, -- 2610.11302 iCATS: Fast Video Generation via Interaction-Aware Sparse Attention and Timestep
    130257, -- external Generative Structure from Motion with Native 3D Diffusion
    130258, -- 2606.04457 Imagine Before You Draw: Visual Prompt Engineering for Image Generation
    130308, -- external Phase-DGS: Phase-Guided Dynamic Gaussian Splatting from Unsynchronized Multi-vie
    130324, -- 2605.25563 CodecSplat: Ultra-Compact Latent Coding for Feed-Forward 3D Gaussian Splatting
    130591, -- external DTGS: Physics-Embedded Dynamic Thermal 3D Reconstruction with Gaussian Splatting
    131010, -- external Beyond Unit-Circle Eigenvalues: Invariant Bases for Stable State Space Dynamics
    131077, -- external Coarse-to-Fine 3D MRI Reconstruction via Resolution-Agnostic Neural Operators
    131088, -- external Diffeomoprhism-Informed 3D Gaussian Splattings via Screen-Space Optimal Transpor
    131098, -- 2605.16732 DiRotQ: Rotation-Aware Quantization for 4-bit Diffusion Transformers
    131203, -- 2605.20479 Oracle Supervision Transfers for Hyperparameter Prediction in Model-Based Image
    131220, -- 2605.21611 UniVL: Unified Vision-Language Embedding for Spatially Grounded Contextual Image
    131619, -- 2106.07286 TimeLens: Event-based Video Frame Interpolation
    131623, -- 2610.39663 AB-Attention: Accurate Block Attention for Accelerating Video Diffusion Transfor
    131900, -- 2611.06042 UniRestorer++: Scalable Universal Image Restoration with Multi-Granularity Degra
    131901 -- 2611.05593 GaussianRenderFormer: Transformer-based Rendering of 3D Gaussian Splats
  );

DELETE FROM paper_method_exclusions x
USING psnr_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM psnr_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM psnr_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- ssim: 275 links (title/abstract names the metric).
CREATE TEMP TABLE ssim_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ssim'
  AND p.id IN (
    37, -- 1307.1166 A Novel Robust Method to Add Watermarks to Bitmap Images by Fading Technique
    267, -- 1511.06409 Learning to Generate Images with Perceptual Similarity Metrics
    1050, -- 1801.03924 The Unreasonable Effectiveness of Deep Features as a Perceptual Metric
    2122, -- 1905.09010 PEPSI++: Fast and Lightweight Network for Image Inpainting
    3762, -- 2006.11161 iSeeBetter: Spatio-Temporal Video Super Resolution using Recurrent-Generative Ba
    3763, -- 2006.11161 iSeeBetter: Spatio-temporal video super-resolution using recurrent generative ba
    4550, -- 2011.07017 NightVision: Generating Nighttime Satellite Imagery from Infra-Red Observations
    4592, -- 2011.10654 Upgraded W-Net with Attention Gates and its Application in Unsupervised 3D Liver
    4722, -- 2012.06318 Results of the 2020 fastMRI Challenge for Machine Learning MR Image Reconstructi
    4985, -- 2102.02711 Fine-tuning deep learning model parameters for improved super-resolution of dyna
    5097, -- 2102.12898 ShuffleUNet: Super resolution of diffusion-weighted MRIs using deep learning
    5210, -- 2103.09203 ReconResNet: Regularised Residual Learning for MR Image Reconstruction of Unders
    5431, -- 2104.06083 Spatiotemporal Entropy Model is All You Need for Learned Video Compression
    6242, -- 2107.06831 Parallel and High-Fidelity Text-to-Lip Generation
    6315, -- 2107.12898 StarEnhancer: Learning Real-Time and Style-Aware Image Enhancement
    7604, -- 2112.13443 Sinogram upsampling using Primal-Dual UNet for undersampled CT and radial MRI re
    7931, -- 2202.05355 DDoS-UNet: Incorporating temporal information using Dynamic Dual-channel UNet fo
    8218, -- 2203.06304 MISF: Multi-level Interactive Siamese Filtering for High-Fidelity Image Inpainti
    9024, -- 2205.07162 GLaMa: Joint Spatial and Frequency Loss for General Image Inpainting
    9136, -- 2205.11521 From Hours to Seconds: Towards 100x Faster Quantitative Phase Imaging via Differ
    9143, -- 2205.11823 Thunder: Thumbnail based Fast Lightweight Image Denoising Network
    9469, -- 2206.06725 Automated SSIM Regression for Detection and Quantification of Motion Artefacts i
    11159, -- 2211.00288 Self-supervised Character-to-Character Distillation for Text Recognition
    11372, -- 2211.08540 VGFlow: Visibility guided Flow Network for Human Reposing
    11510, -- 2211.11827 High-Perceptual Quality JPEG Decoding via Posterior Sampling
    12546, -- 2301.11189 Improving Statistical Fidelity for Neural Image Compression with Implicit Local
    15783, -- 2305.11675 Cinematic Mindscapes: High-quality Video Reconstruction from Brain Activity
    17176, -- 2306.05382 Image Blending Algorithm with Automatic Mask Generation
    18172, -- 2307.05616 Image Reconstruction using Enhanced Vision Transformer
    19189, -- 2308.06603 LadleNet: A Two-Stage UNet for Infrared Image to Visible Image Translation Guide
    19549, -- 2308.10584 RADIANCE: Radio-Frequency Adversarial Deep-learning Inference for Automated Netw
    19806, -- 2308.13672 Fusion of Infrared and Visible Images based on Spatial-Channel Attentional Mecha
    19940, -- 2308.16082 SignDiff: Diffusion Model for American Sign Language Production
    20063, -- 2309.01377 Memory augment is All You Need for image restoration
    20802, -- 2309.13038 Privacy Assessment on Reconstructed Images: Are Existing Evaluation Metrics Fait
    21671, -- 2310.05986 The Unreasonable Effectiveness of Linear Prediction as a Perceptual Metric
    22702, -- 2310.18660 Foundation Models for Generalist Geospatial Artificial Intelligence
    23641, -- 2311.13073 FusionFrames: Efficient Architectural Aspects for Text-to-Video Generation Pipel
    24215, -- 2312.01999 SRTransGAN: Image Super-Resolution using Transformer based Generative Adversaria
    24263, -- 2312.02344 STEREOFOG -- Computational DeFogging via Image-to-Image Translation on a real-wo
    24634, -- 2312.06725 EpiDiff: Enhancing Multi-View Synthesis via Localized Epipolar-Constrained Diffu
    24829, -- 2312.09496 Image Deblurring using GAN
    25798, -- 2401.07049 Quantum Denoising Diffusion Models
    25837, -- 2401.07957 Machine Perceptual Quality: Evaluating the Impact of Severe Lossy Compression on
    26665, -- 2402.01516 Cross-view Masked Diffusion Transformers for Person Image Synthesis
    26672, -- 2402.01590 NeuroCine: Decoding Vivid Video Sequences from Human Brain Activties
    28182, -- 2402.19043 WDM: 3D Wavelet Diffusion Models for High-Resolution Medical Image Synthesis
    29039, -- 2403.11821 A Survey on Quality Metrics for Text-to-Image Generation
    29261, -- 2403.14471 S2LIC: Learned Image Compression with the SwinV2 Block, Adaptive Channel-wise an
    29677, -- 2403.20309 InstantSplat: Sparse-view SfM-free Gaussian Splatting in Seconds
    30253, -- 2404.07987 ControlNet++: Improving Conditional Controls with Efficient Consistency Feedback
    31588, -- 2405.14477 LiteVAE: Lightweight and Efficient Variational Autoencoders for Latent Diffusion
    33571, -- 2406.16359 Improving Generative Adversarial Networks for Video Super-Resolution
    34317, -- 2407.06095 Accelerating Diffusion for SAR-to-Optical Image Translation via Adversarial Cons
    34391, -- 2407.07078 MoSt-DSA: Modeling Motion and Structural Interactions for Direct Multi-Frame Int
    34489, -- 2407.08466 Global Spatial-Temporal Information-based Residual ConvLSTM for Video Space-Time
    34648, -- 2407.10632 Bidirectional Stereo Image Compression with Cross-Dimensional Entropy Model
    35057, -- 2407.15642 Cinemo: Consistent and Controllable Image Animation with Motion Diffusion Models
    36406, -- 2408.17060 Efficient Image Restoration through Low-Rank Adaptation and Stable Diffusion XL
    36882, -- 2409.09323 Implicit Neural Representations with Fourier Kolmogorov-Arnold Networks
    37574, -- 2410.00262 ImmersePro: End-to-End Stereo Video Synthesis Via Implicit Disparity Learning
    37586, -- 2410.00418 Posterior-Mean Rectified Flow: Towards Minimum MSE Photo-Realistic Image Restora
    37600, -- 2410.00731 Improved Generation of Synthetic Imaging Data Using Feature-Aligned Diffusion
    37643, -- 2410.01411 CSIM: A Copula-based similarity index sensitive to local changes for Image quali
    37773, -- 2410.02550 NestedMorph: Enhancing Deformable Medical Image Registration with Nested Attenti
    37995, -- 2410.05097 DreamSat: Towards a General 3D Model for Novel View Synthesis of Space Objects
    38951, -- 2410.16290 A Unified Model for Compressed Sensing MRI Across Undersampling Patterns
    39091, -- 2410.18362 WAFFLE: Finetuning Multi-Modal Model for Automated Front-End Development
    39181, -- 2410.19452 NeuroClips: Towards High-fidelity and Smooth fMRI-to-Video Reconstruction
    39357, -- 2410.22456 Image2Struct: Benchmarking Structure Extraction for Vision-Language Models
    40312, -- 2411.15028 FloAt: Flow Warping of Self-Attention for Clothing Animation Generation
    41496, -- 2412.09648 DSplats: 3D Generation by Denoising Splats-Based Multiview Diffusion Models
    41768, -- 2412.13061 VidTok: A Versatile and Open-Source Video Tokenizer
    42252, -- 2412.19841 FlameGS: Reconstruct flame light field via Gaussian Splatting
    42526, -- 2501.02992 GLFC: Unified Global-Local Feature and Contrast Learning with Mamba-Enhanced UNe
    43001, -- 2501.11043 BF-STVSR: B-Splines and Fourier-Best Friends for High Fidelity Spatial-Temporal
    43093, -- 2501.12637 DWTNeRF: Boosting Few-shot Neural Radiance Fields via Discrete Wavelet Transform
    44142, -- 2502.09164 E-MD3C: Taming Masked Diffusion Transformers for Efficient Zero-Shot Object Cust
    45689, -- 2503.06397 Removing Averaging: Personalized Lip-Sync Driven Characters Based on Identity Ad
    45724, -- 2503.06740 D3DR: Lighting-Aware Object Insertion in Gaussian Splatting
    47350, -- 2504.04722 TactileNet: Bridging the Accessibility Gap with AI-Generated Tactile Graphics fo
    47561, -- 2504.08635 Latent Diffusion Autoencoders: Toward Efficient and Meaningful Unsupervised Repr
    47587, -- 2504.09069 UniFlowRestore: A General Video Restoration Framework via Flow Matching and Prom
    47590, -- 2504.09182 seg2med: a bridge from artificial anatomy to multimodal medical images
    47728, -- 2504.11271 Distillation-Supervised Convolutional Low-Rank Adaptation for Efficient Image Su
    48319, -- 2505.00687 GuideSR: Rethinking Guidance for One-Step High-Fidelity Diffusion-Based Super-Re
    48591, -- 2505.06502 PC-SRGAN: Physically Consistent Super-Resolution Generative Adversarial Network
    48827, -- 2505.11034 CleanPatrick: A Benchmark for Image Data Cleaning
    49690, -- 2505.19138 Veta-GS: View-dependent deformable 3D Gaussian Splatting for thermal infrared No
    50225, -- 2505.24421 pyMEAL: A Multi-Encoder Augmentation-Aware Learning for Robust and Generalizable
    50355, -- 2506.01004 Motion-Aware Concept Alignment for Consistent Video Editing
    50789, -- 2506.07863 VIVAT: Virtuous Improving VAE Training through Artifact Mitigation
    50904, -- 2506.09045 MagCache: Fast Video Generation with Magnitude-Aware Cache
    52285, -- 2508.06485 WGAST: Weakly-Supervised Generative Network for Daily 10 m Land Surface Temperat
    53667, -- 2510.15264 DriveGen3D: Boosting Feed-Forward Driving Scene Generation with Efficient Video
    55074, -- 2601.00796 AdaGaR: Adaptive Gabor Representation for Dynamic Scene Reconstruction
    55747, -- 2602.02914 FaceLinkGen: Rethinking Identity Leakage in Privacy-Preserving Face Recognition
    55956, -- 2602.09084 Agent Banana: High-Fidelity Image Editing with Agentic Thinking and Tooling
    56528, -- 2603.05940 SLER-IR: Spherical Layer-wise Expert Routing for All-in-One Image Restoration
    56560, -- 2603.06449 CaTok: Taming Mean Flows for One-Dimensional Causal Image Tokenization
    57954, -- 2604.21052 StyleVAR: Controllable Image Style Transfer via Visual Autoregressive Modeling
    58324, -- 2604.09999 GIF: A Conditional Multimodal Generative Framework for IR Drop Imaging in Chip L
    58334, -- 2604.09835 F3G-Avatar : Face Focused Full-body Gaussian Avatar
    58412, -- 2604.07329 Distilling Photon-Counting CT into Routine Chest CT through Clinically Validated
    58790, -- 2603.27469 KV Cache Quantization for Self-Forcing Video Generation: A 33-Method Empirical S
    58870, -- 2603.25685 Persistent Robot World Models: Stabilizing Multi-Step Rollouts via Reinforcement
    59039, -- 2603.21615 AdaEdit: Adaptive Temporal and Channel Modulation for Flow-Based Image Editing
    59413, -- 2603.13943 Sat-JEPA-Diff: Bridging Self-Supervised Learning and Generative Diffusion for Re
    59730, -- 2603.07551 Targeted Speaker Poisoning Framework in Zero-Shot Text-to-Speech
    60409, -- 2602.19348 MultiDiffSense: Diffusion-Based Multi-Modal Visuo-Tactile Image Generation Condi
    60649, -- 2602.14068 CoCoEdit: Content-Consistent Image Editing via Region Regularized Reinforcement
    61680, -- 2602.00221 Benchmarking Vanilla GAN, DCGAN, and WGAN Architectures for MRI Reconstruction:
    61710, -- 2601.22725 OpenVTON-Bench: A Large-Scale High-Resolution Benchmark for Controllable Virtual
    62637, -- 2601.07219 VENUS: Visual Editing with Noise Inversion Using Scene Graphs
    62915, -- 2601.03391 Edit2Restore:Few-Shot Image Restoration via Parameter-Efficient Adaptation of Pr
    63325, -- 2512.21402 Understanding Virality: A Rubric based Vision-Language Model Framework for Short
    63345, -- 2512.21040 A Large-Depth-Range Layer-Based Hologram Dataset for Machine Learning-Based 3D C
    63729, -- 2512.12790 L-STEC: Learned Video Compression with Long-term Spatio-Temporal Enhanced Contex
    63992, -- 2512.07251 See More, Change Less: Anatomy-Aware Diffusion for Contrast Enhancement
    64165, -- 2512.03701 Structured Uncertainty Similarity Score (SUSS): Learning a Probabilistic, Interp
    64237, -- 2512.02273 Progressive Image Restoration via Text-Conditioned Video Generation
    64289, -- 2512.01390 FRAMER: Frequency-Aligned Self-Distillation with Adaptive Modulation Leveraging
    64346, -- 2512.00752 Charts Are Not Images: On the Challenges of Scientific Chart Editing
    64636, -- 2511.18775 Rethinking Garment Conditioning in Diffusion-based Virtual Try-On
    64718, -- 2511.17747 AEGIS: Preserving privacy of 3D Facial Avatars with Adversarial Perturbations
    65118, -- 2511.09180 FSampler: Training Free Acceleration of Diffusion Sampling via Epsilon Extrapola
    65266, -- 2511.06244 Physics-Informed Image Restoration via Progressive PDE Integration
    65473, -- 2511.01620 Learned Adaptive Kernels for High-Fidelity Image Downscaling
    66856, -- 2510.06335 Conditional Denoising Diffusion Model-Based Robust MR Image Reconstruction from
    67527, -- 2509.24022 R^3: Reconstruction, Raw, and Rain: Deraining Directly in the Bayer Domain
    68022, -- 2509.17589 Table2LaTeX-RL: High-Fidelity LaTeX Code Generation from Table Images via Reinfo
    68091, -- 2509.16582 A Novel Metric for Detecting Memorization in Generative Models for Brain MRI Syn
    68595, -- 2509.07252 GCond: Gradient Conflict Resolution via Accumulation-based Stabilization for Lar
    69168, -- 2508.18696 ColorGS: High-fidelity Surgical Scene Reconstruction with Colored Gaussian Splat
    69483, -- 2508.14797 MF-LPR^2: Multi-Frame License Plate Image Restoration and Recognition using Opti
    69738, -- 2508.09802 MUJICA: Reforming SISR Models for PBR Material Super-Resolution via Cross-Map At
    69800, -- 2508.08978 TaoCache: Structure-Maintained Video Generation Acceleration
    69877, -- 2508.07769 Dream4D: Lifting Camera-Controlled I2V towards Spatiotemporally Consistent 4D Ge
    70271, -- 2508.02363 Transport-Guided Rectified Flow Inversion: Improved Image Editing Using Optimal
    70302, -- 2508.02072 HyTIP: Hybrid Temporal Information Propagation for Masked Conditional Residual V
    70397, -- 2508.00756 LeakyCLIP: Extracting Training Data from CLIP
    70556, -- 2507.22304 Invisible Injections: Exploiting Vision-Language Models Through Steganographic P
    70756, -- 2507.18594 DRWKV: Focusing on Object Edges for Low-Light Image Enhancement
    71221, -- 2507.09308 AlphaVAE: Unified End-to-End RGBA Image Reconstruction and Generation with Alpha
    72380, -- 2506.02093 Are Pixel-Wise Metrics Reliable for Sparse-View Computed Tomography Reconstructi
    73326, -- 2504.18251 Adaptive Weight Modified Riesz Mean Filter For High-Density Salt and Pepper Nois
    73379, -- 2504.16557 Beyond Anonymization: Object Scrubbing for Privacy-Preserving 2D and 3D Vision T
    73555, -- 2504.09097 BIGS: Bimanual Category-agnostic Interaction Reconstruction from Monocular Video
    74165, -- 2503.08217 S3R-GS: Streamlining the Pipeline for Large-Scale Street Scene Reconstruction
    75110, -- 2501.13045 Sketch and Patch: Efficient 3D Gaussian Representation for Man-Made Scenes
    75229, -- 2501.06139 SkyReconNet: A Cross-Resolution Contextual Integration Framework for Inpainting
    75660, -- 2411.19442 MCUCoder: Adaptive Bitrate Learned Video Compression for IoT Devices
    75772, -- 2411.07795 InvisMark: Invisible and Robust Watermarking for AI-generated Image Provenance
    76009, -- 2410.14966 Attack as Defense: Run-time Backdoor Implantation for Image Content Protection
    76569, -- 2408.10283 Perception-based multiplicative noise removal using SDEs
    77253, -- 2405.11494 Automated Coastline Extraction Using Edge Detection Algorithms
    77390, -- 2404.14533 SwinFuSR: an image fusion-inspired model for RGB-guided thermal image super-reso
    77402, -- 2404.13018 A New Multi-Picture Architecture for Learned Video Deinterlacing and Demosaicing
    77501, -- 2404.02702 PSCodec: A Series of High-Fidelity Low-bitrate Neural Speech Codecs Leveraging P
    77964, -- 2401.06367 Enhancing a Convolutional Autoencoder with a Quantum Approximate Optimization Al
    78717, -- 2307.15388 An Empirical Study of Large-Scale Data-Driven Full Waveform Inversion
    79376, -- 2302.02887 UVDoc: Neural Grid-based Document Unwarping
    80130, -- 2203.09388 A Text Attention Network for Spatial Deformation Robust Scene Text Image Super-r
    80858, -- 2103.01114 Deep Perceptual Image Quality Assessment for Compression
    81118, -- 2009.11380 Combining Weighted Total Variation and Deep Image Prior for natural and medical
    81244, -- 2006.13846 Understanding SSIM
    82105, -- 1802.01436 Variational image compression with a scale hyperprior
    83831, -- 2605.15042 EverAnimate: Minute-Scale Human Animation via Latent Flow Restoration
    84083, -- 2508.13309 DASH: A Meta-Attack Framework for Synthesizing Effective and Stealthy Adversaria
    84133, -- 2510.18362 FeatureFool: Zero-Query Fooling of Video Models via Feature Map
    84675, -- 2603.00805 NERFIFY: A Multi-Agent Framework for Turning NeRF Papers into Code
    84679, -- 2603.00920 Spectral Super-Resolution via Adversarial Unfolding and Data-Driven Spectrum Reg
    84755, -- 2603.04975 BiEvLight: Bi-level Learning of Task-Aware Event Refinement for Low-Light Image
    85400, -- 2604.16540 PoInit-of-View: Poisoning Initialization of Views Transfers Across Multiple 3D R
    85598, -- 2605.22186 Event-Illumination Collaborative Low-light Image Enhancement with a High-resolut
    86248, -- 2506.04283 SSIMBaD: Sigma Scaling with SSIM-Guided Balanced Diffusion for AnimeFace Coloriz
    87101, -- 2506.09534 Gaussian Herding across Pens: An Optimal Transport Perspective on Global Gaussia
    87847, -- 2506.01379 RadarSplat: Radar Gaussian Splatting for High-Fidelity Data Synthesis and 3D Rec
    90144, -- 2412.05848 MotionStone: Decoupled Motion Intensity Modulation with Diffusion Transformer fo
    90920, -- 2412.03378 Volumetrically Consistent 3D Gaussian Rasterization
    92657, -- 2603.01591 FAST‑DIPS: Adjoint‑Free Analytic Steps and Hard‑Constrained Likelihood Correctio
    94238, -- 2505.05643 UltraGauss: Ultrafast Gaussian Reconstruction of 3D Ultrasound Volumes
    95406, -- external Spectral Security Imaging System (SSIS): Optical Authenticity for Hyperspectral
    96863, -- external Robustness of Panoptic Segmentation for Degraded Automotive Cameras Data (I)
    97033, -- 2504.17401 StereoMamba: Real-Time and Robust Intraoperative Stereo Disparity Estimation Via
    97080, -- 2604.12837 GGD-SLAM: Monocular 3DGS SLAM Powered by Generalizable Motion Model for Dynamic
    97161, -- 2506.14135 GAF: Gaussian Action Field As a 4D Representation for Dynamic World Modeling in
    97546, -- 2511.16494 Physics-Informed Machine Learning for Efficient Sim-To-Real Data Augmentation in
    98030, -- external PhyGaP: Physically-Grounded Gaussians with Polarization Cues (AutoSOTA)
    98052, -- external FastGS: Training 3D Gaussian Splatting in 100 Seconds — A Technical Report on Au
    98073, -- external Mobile-VTON: High-Fidelity On-Device Virtual Try-On (AutoSOTA)
    98074, -- external Statistical Characteristic-Guided Denoising for Rapid High-Resolution Transmissi
    98083, -- external Reparameterized Tensor Ring Functional Decomposition for Multi-Dimensional Data
    98100, -- external Speeding Up the Learning of 3D Gaussians with Much Shorter Gaussian Lists (AutoS
    98246, -- 2606.08063 Robust-U1: Can MLLMs Self-Recover Corrupted Visual Content for Robust Understand
    98604, -- 2606.17480 GeneralVLA-2: Geometry-Aware Reconstruction and Governed Memory for Robot Planni
    99983, -- 2601.11440 GenDA: Generative Data Assimilation on Complex Urban Areas via Classifier-Free D
    102058, -- 2601.21664 SENDAI: A Hierarchical Sparse-measurement, EfficieNt Data AssImilation Framework
    102430, -- 2605.27990 Geometry-Correct Diffusion Posterior Sampling with Denoiser-Pullback Curvature G
    104334, -- 1611.01704 End-to-end Optimized Image Compression
    104335, -- 1809.02736 Joint Autoregressive and Hierarchical Priors for Learned Image Compression
    104336, -- 2001.01568 Learned Image Compression with Discretized Gaussian Mixture Likelihoods and Atte
    104345, -- 1801.04260 Conditional Probability Models for Deep Image Compression
    104347, -- 1809.10452 Context-adaptive Entropy Model for End-to-end Optimized Image Compression
    104348, -- 1703.10553 Learning Convolutional Networks for Content-weighted Image Compression
    104350, -- 1703.10114 Improved Lossy Image Compression with Priming and Spatially Adaptive Bit Rates f
    104352, -- 1910.06244 Neural Image Compression via Non-Local Attention Optimization and Improved Conte
    104359, -- 2011.09704 Causal Contextual Prediction for Learned Image Compression
    104368, -- 2107.06463 Learned Image Compression with Gaussian-Laplacian-Logistic Mixture Model and Con
    104510, -- 2607.21580 GraphVid: Interactive Graph-Controllable Video Generation
    105003, -- external CardioInterp: Generative Modeling for Cardiovascular OCT Interpolation with Anat
    105009, -- external Causality-driven Spatio-temporal Generator for Multi-phase Contrast-enhanced CT
    105069, -- 2508.10313 Cross-view Generalized Diffusion Model for Sparse-view CT Reconstruction
    105081, -- external D4Recon: Dual-stage Deformation and Dual-scale Depth Guidance for Endoscopic Rec
    105200, -- 2508.10617 FIND-Net – Fourier-Integrated Network with Dictionary Kernels for Metal Artifact
    105207, -- external FMM-Diff: A Feature Mapping and Merging Diffusion Model for MRI Generation with
    105284, -- external Hybrid State-Space Models and Denoising Training for Unpaired Medical Image Synt
    105512, -- 2507.18112 Parameter-Efficient Fine-Tuning of 3D DDPM for MRI Image Generation Using Tensor
    105833, -- external Wavelet-driven Decoupling and Physics-informed Mapping Network for Accelerated M
    105952, -- 2607.12362 Implicit 4D Gaussian Splatting for Fast Motion with Large Inter-Frame Displaceme
    106013, -- external Spectral and Spatial Graph Learning for Multispectral Solar Image Compression
    107490, -- 2508.11409 RMFAT: Recurrent Multi-scale Feature Atmospheric Turbulence Mitigator
    107498, -- 2511.17993 SD-PSFNet: Sequential and Dynamic Point Spread Function Network for Image Derain
    107794, -- 2512.21710 RAPTOR: Real-Time High-Resolution UAV Video Prediction with Efficient Video Atte
    107865, -- 2505.04116 RFNNS: Robust Fixed Neural Network Steganography with Universal Text-to-Image Mo
    108113, -- 2511.13399 TripleFDS: Triple Feature Disentanglement and Synthesis for Scene Text Editing
    108521, -- 2603.16747 Semi-supervised Latent Disentangled Diffusion Model for Textile Pattern Generati
    109416, -- 1804.05091 I-HAZE: a dehazing benchmark with real hazy and haze-free indoor images
    109417, -- 1804.05101 O-HAZE: a dehazing benchmark with real hazy and haze-free outdoor images
    112425, -- 2312.09063 Image Demoireing in RAW and sRGB Domains
    112474, -- 2404.14409 CrossScore: A Multi-View Approach to Image Evaluation and Scoring
    113508, -- 2407.03239 Solving the inverse problem of microscopy deconvolution with a residual Beylkin-
    113571, -- 2403.14772 Improving Robustness to Model Inversion Attacks via Sparse Coding Architectures
    114192, -- 2609.08230 ActionSplice: In-Flight Action Editing for Interactive World Models
    114385, -- 2407.14564 APS-USCT: Ultrasound Computed Tomography on Sparse Data via AI-Physic Synergy
    114421, -- external Cardiac Physiology Knowledge-driven Diffusion Model for Contrast-free Synthesis
    114433, -- external Center-to-Edge Denoising Diffusion Probabilistic Models with Cross-domain Attent
    114911, -- 2409.08463 Evaluating the Quality of Brain MRI Generators
    114960, -- 2404.06128 Gaussian Pancakes: Geometrically-Regularized 3D Gaussian Splatting for Realistic
    115010, -- 2407.02974 IM-MoCo: Self-supervised MRI Motion Correction using Motion-Guided Implicit Neur
    115015, -- 2409.12539 Improving cone-beam CT Image Quality with Knowledge Distillation-Enhanced Diffus
    115094, -- external Masked Residual Diffusion Probabilistic Model with Regional Asymmetry Prior for
    115139, -- external mQSM: Multitask Learning-based Quantitative Susceptibility Mapping for Iron Anal
    115404, -- 2406.03413 UnWave-Net: Unrolled Wavelet Network for Compton Tomography Image Reconstruction
    116606, -- 2404.08921 PNeRV: Enhancing Spatial Consistency via Pyramidal Neural Representation for Vid
    116860, -- 2402.17951 QN-Mixer: A Quasi-Newton MLP-Mixer Model for Sparse-View CT Reconstruction
    117096, -- 2406.04961 Multiplane Prior Guided Few-Shot Aerial Scene Rendering
    117359, -- external Towards Enhanced Sparse-View Tomographic Reconstruction Using 3D Gaussian Splatt
    117426, -- 2606.31050 Learning Video Dynamics with Predictive Differentiable Rendering
    117526, -- 2606.29794 UniTriSplat: A Unified 3D Gaussian Splatting Framework with Uniform Spherical Ra
    117615, -- 2603.24725 Confidence-Based Mesh Extraction from 3D Gaussians
    117754, -- 2606.27576 DeLux: Cross-Modal Local Artifact Restoration in Video Using Neuromorphic Data
    118542, -- 2608.14046 Source-Agnostic Image Translation Based on Latent Aware Adaptive Masking
    119861, -- external Perceptual Video Compression with Neural Wrapping
    120154, -- 2504.00219 LITA-GS: Illumination-Agnostic Novel View Synthesis via Reference-Free 3D Gaussi
    120193, -- 2412.00505 Good, Cheap, and Fast: Overfitted Image Compression with Wasserstein Distortion
    120795, -- 2511.02777 PercHead: Perceptual Head Model for Single-Image 3D Head Reconstruction & Editin
    121140, -- external RAPID: Reusing Attention Sparsity with Inter-step Adaptation for Efficient Video
    122032, -- 2609.05661 Srijika: OpenType-Layout-Reusing Font Restyling for Nine Indic Scripts
    122089, -- 2609.20633 Refinement Is Inherently Editable: Training-Free Prompt-to-Prompt Image Editing
    122193, -- 2609.30077 Rate-distortion optimization for full-reference image quality metrics via stocha
    122775, -- 2605.16817 Adaptive Fused Prior Transfer for Controllable Generative Image Compression
    122916, -- 2610.04722 NAMVIS: Next-Scale Autoregressive Multi-View Image Synthesis
    122917, -- 2408.01199 Pre-processing and quality control of large clinical CT head datasets for intrac
    123593, -- 2610.06598 SimForcing: Distilling Simulation Motion Priors into Real-Domain Robot World Mod
    124251, -- external IRCasDiff: Two-Stage Cascaded Diffusion for Compound Infrared Face Reconstructio
    124850, -- external Deformable 2D Gaussian Splatting
    124908, -- external Rate-Constrained Edge Metadata for Sender–Receiver Generative Video Super-Resolu
    125114, -- external Magnetic Resonance Unpaired Image Translation with Pseudometric Schrödinger Brid
    125138, -- 2608.23014 AnaDiffusion: Anatomically Compositional Latent Diffusion for Controllable 3D Br
    125532, -- external UltraVoxelGS: Voxel-First Feed-Forward Gaussian Splatting for 3D Ultrasound Reco
    126753, -- 2609.37875 Co-PiLOT: Constrained Physics-Informed Latent Optimization for Target-Driven Inv
    128167, -- 2605.03821 RoboAlign-R1: Distilled Multimodal Reward Alignment for Robot Video World Models
    129515, -- external Anatomy-Preserving Unpaired Medical Image Translation via Shared Latent Anchorin
    131088 -- external Diffeomoprhism-Informed 3D Gaussian Splattings via Screen-Space Optimal Transpor
  );

DELETE FROM paper_method_exclusions x
USING ssim_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ssim_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ssim_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- lpips: 196 links (title/abstract names the metric; plus the source paper).
CREATE TEMP TABLE lpips_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lpips'
  AND p.id IN (
    1050, -- 1801.03924 The Unreasonable Effectiveness of Deep Features as a Perceptual Metric
    5582, -- 2104.12665 Clean Images are Hard to Reblur: Exploiting the Ill-Posed Inverse Task for Dynam
    6315, -- 2107.12898 StarEnhancer: Learning Real-Time and Style-Aware Image Enhancement
    8218, -- 2203.06304 MISF: Multi-level Interactive Siamese Filtering for High-Fidelity Image Inpainti
    9024, -- 2205.07162 GLaMa: Joint Spatial and Frequency Loss for General Image Inpainting
    9662, -- 2207.00050 Semantic Image Synthesis via Diffusion Models
    9919, -- 2207.13686 Shift-tolerant Perceptual Similarity Metric
    11372, -- 2211.08540 VGFlow: Visibility guided Flow Network for Human Reposing
    14918, -- 2304.12281 HOSNeRF: Dynamic Human-Object-Scene Neural Radiance Fields from a Single Video
    15575, -- 2305.08840 Attacking Perceptual Similarity Metrics
    17230, -- 2306.06044 GANeRF: Leveraging Discriminators to Optimize Neural Radiance Fields
    18548, -- 2307.12217 LoLep: Single-View View Synthesis with Locally-Learned Planes and Self-Attention
    20443, -- 2309.07986 Viewpoint Textual Inversion: Discovering Scene Representations and 3D View Contr
    21671, -- 2310.05986 The Unreasonable Effectiveness of Linear Prediction as a Perceptual Metric
    22335, -- 2310.14189 Improved Techniques for Training Consistency Models
    22653, -- 2310.17994 ZeroNVS: Zero-Shot 360-Degree View Synthesis from a Single Image
    23641, -- 2311.13073 FusionFrames: Efficient Architectural Aspects for Text-to-Video Generation Pipel
    24218, -- 2312.02015 ColonNeRF: High-Fidelity Neural Reconstruction of Long Colonoscopy
    24634, -- 2312.06725 EpiDiff: Enhancing Multi-View Synthesis via Localized Epipolar-Constrained Diffu
    25043, -- 2312.13150 Splatter Image: Ultra-Fast Single-View 3D Reconstruction
    25493, -- 2401.02414 Bring Metric Functions into Diffusion Models
    26665, -- 2402.01516 Cross-view Masked Diffusion Transformers for Person Image Synthesis
    28785, -- 2403.08453 Better Fit: Accommodate Variations in Clothing Types for Virtual Try-on
    29389, -- 2403.16092 Are NeRFs ready for autonomous driving? Towards closing the real-to-simulation g
    29697, -- 2404.00412 SVGCraft: Beyond Single Object Text-to-SVG Synthesis with Comprehensive Canvas L
    30350, -- 2404.09512 Magic Clothing: Controllable Garment-Driven Image Synthesis
    31179, -- 2405.05967 Distilling Diffusion Models into Conditional GANs
    31588, -- 2405.14477 LiteVAE: Lightweight and Efficient Variational Autoencoders for Latent Diffusion
    32059, -- 2405.20032 Promptus: Can Prompts Streaming Replace Video Streaming with Stable Diffusion
    32090, -- 2405.20320 Improving the Training of Rectified Flows
    33523, -- 2406.15811 PointDreamer: Zero-shot 3D Textured Mesh Reconstruction from Colored Point Cloud
    34052, -- 2407.02445 Meta 3D AssetGen: Text-to-Mesh Generation with High-Quality Geometry, Texture, a
    34996, -- 2407.14880 A New Dataset and Framework for Real-World Blurred Images Super-Resolution
    36406, -- 2408.17060 Efficient Image Restoration through Low-Rank Adaptation and Stable Diffusion XL
    37995, -- 2410.05097 DreamSat: Towards a General 3D Model for Novel View Synthesis of Space Objects
    38847, -- 2410.14987 SeaS: Few-shot Industrial Anomaly Image Generation with Separation and Sharing F
    39357, -- 2410.22456 Image2Struct: Benchmarking Structure Extraction for Vision-Language Models
    40220, -- 2411.13548 HF-Diff: High-Frequency Perceptual Loss and Distribution Matching for One-Step D
    40305, -- 2411.14974 3D Convex Splatting: Radiance Field Rendering with 3D Smooth Convexes
    40312, -- 2411.15028 FloAt: Flow Warping of Self-Attention for Clothing Animation Generation
    40516, -- 2411.17459 WF-VAE: Enhancing Video VAE by Wavelet-Driven Energy Flow for Latent Video Diffu
    41127, -- 2412.04887 Momentum-GS: Momentum Gaussian Self-Distillation for High-Quality Large Scene Re
    41496, -- 2412.09648 DSplats: 3D Generation by Denoising Splats-Based Multiview Diffusion Models
    41514, -- 2412.09910 Prompt2Perturb (P2P): Text-Guided Diffusion-Based Adversarial Attacks on Breast
    41768, -- 2412.13061 VidTok: A Versatile and Open-Source Video Tokenizer
    42281, -- 2412.20422 Bringing Objects to Life: 4D generation from 3D objects
    42493, -- 2501.02527 Vision-Driven Prompt Optimization for Large Language Models in Multimodal Genera
    43093, -- 2501.12637 DWTNeRF: Boosting Few-shot Neural Radiance Fields via Discrete Wavelet Transform
    43622, -- 2502.01993 One Diffusion Step to Real-World Super-Resolution via Flow Trajectory Distillati
    44142, -- 2502.09164 E-MD3C: Taming Masked Diffusion Transformers for Efficient Zero-Shot Object Cust
    45501, -- 2503.03708 Rethinking Video Tokenization: A Conditioned Diffusion-based Approach
    46205, -- 2503.12552 MTGS: Multi-Traversal Gaussian Splatting
    46482, -- 2503.16396 SV4D 2.0: Enhancing Spatio-Temporal Consistency in Multi-View Video Diffusion fo
    46777, -- 2503.20268 EGVD: Event-Guided Video Diffusion Model for Physically Realistic Large-Motion F
    46835, -- 2503.21246 DynamiCtrl: Rethinking the Basic Structure and the Role of Text for High-quality
    47091, -- 2504.00387 Scene4U: Hierarchical Layered 3D Scene Reconstruction from Single Panoramic Imag
    48319, -- 2505.00687 GuideSR: Rethinking Guidance for One-Step High-Fidelity Diffusion-Based Super-Re
    49354, -- 2505.16001 Image-to-Image Translation with Diffusion Transformers and CLIP-Based Image Cond
    50355, -- 2506.01004 Motion-Aware Concept Alignment for Consistent Video Editing
    50490, -- 2506.03119 Controllable Human-centric Keyframe Interpolation with Generative Prior
    50904, -- 2506.09045 MagCache: Fast Video Generation with Magnitude-Aware Cache
    51153, -- 2506.13465 SA-LUT: Spatial Adaptive 4D Look-Up Table for Photorealistic Style Transfer
    52519, -- 2508.18271 ObjFiller-3D: Consistent Multi-view 3D Inpainting via Video Diffusion Models
    53214, -- 2510.00658 Align Your Tangent: Training Better Consistency Models via Manifold-Aligned Tang
    53390, -- 2509.24817 UP2You: Fast Reconstruction of Yourself from Unconstrained Photo Collections
    54301, -- 2511.17344 Loomis Painter: Reconstructing the Painting Process
    54632, -- 2512.07833 Relational Visual Similarity
    54748, -- 2512.10685 Sharp Monocular View Synthesis in Less Than a Second
    55009, -- 2512.23709 Stream-DiffVSR: Low-Latency Streamable Video Super-Resolution via Auto-Regressiv
    55045, -- 2512.25073 GaMO: Geometry-aware Multi-view Diffusion Outpainting for Sparse-View 3D Reconst
    55074, -- 2601.00796 AdaGaR: Adaptive Gabor Representation for Dynamic Scene Reconstruction
    55666, -- 2602.02493 PixelGen: Pixel Diffusion Beats Latent Diffusion with Perceptual Loss
    55956, -- 2602.09084 Agent Banana: High-Fidelity Image Editing with Agentic Thinking and Tooling
    57954, -- 2604.21052 StyleVAR: Controllable Image Style Transfer via Visual Autoregressive Modeling
    58334, -- 2604.09835 F3G-Avatar : Face Focused Full-body Gaussian Avatar
    58790, -- 2603.27469 KV Cache Quantization for Self-Forcing Video Generation: A 33-Method Empirical S
    58870, -- 2603.25685 Persistent Robot World Models: Stabilizing Multi-Step Rollouts via Reinforcement
    59039, -- 2603.21615 AdaEdit: Adaptive Temporal and Channel Modulation for Flow-Based Image Editing
    60414, -- 2602.19254 RegionRoute: Regional Style Transfer with Diffusion Model
    62230, -- 2601.15275 RayRoPE: Projective Ray Positional Encoding for Multi-view Attention
    62637, -- 2601.07219 VENUS: Visual Editing with Noise Inversion Using Scene Graphs
    64165, -- 2512.03701 Structured Uncertainty Similarity Score (SUSS): Learning a Probabilistic, Interp
    64237, -- 2512.02273 Progressive Image Restoration via Text-Conditioned Video Generation
    64289, -- 2512.01390 FRAMER: Frequency-Aligned Self-Distillation with Adaptive Modulation Leveraging
    64636, -- 2511.18775 Rethinking Garment Conditioning in Diffusion-based Virtual Try-On
    64912, -- 2511.13478 Semantic Document Derendering: SVG Reconstruction via Vision-Language Modeling
    65233, -- 2511.06953 GFix: Perceptually Enhanced Gaussian Splatting Video Compression
    65610, -- 2511.00107 AI Powered High Quality Text to Video Generation with Enhanced Temporal Consiste
    65645, -- 2511.00090 LeMiCa: Lexicographic Minimax Path Caching for Efficient Diffusion-Based Video G
    66608, -- 2510.09987 Generative Latent Video Compression
    66856, -- 2510.06335 Conditional Denoising Diffusion Model-Based Robust MR Image Reconstruction from
    67283, -- 2509.26621 HART: Human Aligned Reconstruction Transformer
    68491, -- 2509.09488 Prompt Pirates Need a Map: Stealing Seeds helps Stealing Prompts
    69483, -- 2508.14797 MF-LPR^2: Multi-Frame License Plate Image Restoration and Recognition using Opti
    69738, -- 2508.09802 MUJICA: Reforming SISR Models for PBR Material Super-Resolution via Cross-Map At
    69800, -- 2508.08978 TaoCache: Structure-Maintained Video Generation Acceleration
    70271, -- 2508.02363 Transport-Guided Rectified Flow Inversion: Improved Image Editing Using Optimal
    70853, -- 2507.17135 SADA: Stability-guided Adaptive Diffusion Acceleration
    71958, -- 2506.13355 DicFace: Dirichlet-Constrained Variational Codebook Learning for Temporally Cohe
    73087, -- 2505.08281 Ultra Lowrate Image Compression with Semantic Residual Coding and Compression-aw
    73379, -- 2504.16557 Beyond Anonymization: Object Scrubbing for Privacy-Preserving 2D and 3D Vision T
    73511, -- 2504.10567 H3AE: High Compression, High Speed, and High Quality AutoEncoder for Video Diffu
    73555, -- 2504.09097 BIGS: Bimanual Category-agnostic Interaction Reconstruction from Monocular Video
    73693, -- 2504.04340 AnomalyHybrid: A Domain-agnostic Generative Framework for General Anomaly Detect
    74359, -- 2503.00853 MTReD: 3D Reconstruction Dataset for Fly-over Videos of Maritime Domain
    75110, -- 2501.13045 Sketch and Patch: Efficient 3D Gaussian Representation for Man-Made Scenes
    75608, -- 2412.03017 Pixel-level and Semantic-level Adjustable Super-resolution: A Dual-LoRA Approach
    75755, -- 2411.13033 LMM-driven Semantic Image-Text Coding for Ultra Low-bitrate Learned Image Compre
    76569, -- 2408.10283 Perception-based multiplicative noise removal using SDEs
    83769, -- 2605.25191 Injecting Image Guidance into Text-Conditioned Diffusion Models at Inference
    83831, -- 2605.15042 EverAnimate: Minute-Scale Human Animation via Latent Flow Restoration
    84083, -- 2508.13309 DASH: A Meta-Attack Framework for Synthesizing Effective and Stealthy Adversaria
    84193, -- 2511.16928 Rethinking Diffusion Model-Based Video Super-Resolution: Leveraging Dense Guidan
    84925, -- 2603.15302 Generative Video Compression with One-Dimensional Latent Representation
    85188, -- 2603.28152 ObjectMorpher: 3D-Aware Image Editing via Deformable 3DGS
    85220, -- 2604.00530 AceTone: Bridging Words and Colors for Conditional Image Grading
    85344, -- 2604.10546 Differentiable Vector Quantization for Rate-Distortion Optimization of Generativ
    85480, -- 2605.00498 GOR-IS: 3D Gaussian Object Removal In the Intrinsic Space
    87101, -- 2506.09534 Gaussian Herding across Pens: An Optimal Transport Perspective on Global Gaussia
    87549, -- 2507.20721 AIComposer: Any Style and Content Image Composition via Feature Integration
    87695, -- 2503.01428 DLF: Extreme Image Compression with Dual-generative Latent Fusion
    89757, -- 2506.09416 Noise Conditional Variational Score Distillation
    90114, -- 2503.15831 EDEN: Enhanced Diffusion for High-quality Large-motion Video Frame Interpolation
    90920, -- 2412.03378 Volumetrically Consistent 3D Gaussian Rasterization
    92657, -- 2603.01591 FAST‑DIPS: Adjoint‑Free Analytic Steps and Hard‑Constrained Likelihood Correctio
    94558, -- 2602.11845 WorldTree: Towards 4D Dynamic Worlds from Monocular Video using Tree-Chains
    94801, -- 2510.03191 PQGAN: Product-Quantised Image Representation for High-Quality Image Synthesis
    96920, -- external High-Quality Sparse-View Gaussian Splatting without Ground-Truth Camera Poses
    97161, -- 2506.14135 GAF: Gaussian Action Field As a 4D Representation for Dynamic World Modeling in
    98030, -- external PhyGaP: Physically-Grounded Gaussians with Polarization Cues (AutoSOTA)
    98052, -- external FastGS: Training 3D Gaussian Splatting in 100 Seconds — A Technical Report on Au
    98072, -- external HiDRA: Hierarchical Degradation Representation and Adaptation with Generative Pr
    98073, -- external Mobile-VTON: High-Fidelity On-Device Virtual Try-On (AutoSOTA)
    98100, -- external Speeding Up the Learning of 3D Gaussians with Much Shorter Gaussian Lists (AutoS
    98558, -- 2604.13416 DF3DV-1K: A Large-Scale Dataset and Benchmark for Distractor-Free Novel View Syn
    98604, -- 2606.17480 GeneralVLA-2: Geometry-Aware Reconstruction and Governed Memory for Robot Planni
    99187, -- 2605.23323 Efficient Learned Image Compression without Entropy Coding
    102247, -- 2605.05331 ViTok-v2: Scaling Native Resolution Autoencoders to 5 Billion Parameters
    102430, -- 2605.27990 Geometry-Correct Diffusion Posterior Sampling with Denoiser-Pullback Curvature G
    103337, -- 2601.16231 SoundBreak: A Systematic Study of Audio-Only Adversarial Attacks on Trimodal Mod
    105081, -- external D4Recon: Dual-stage Deformation and Dual-scale Depth Guidance for Endoscopic Rec
    105578, -- external R2B-WFC Ultrasound Reconstruction: Wavelet Fourier Convolution-based Reconstruct
    106636, -- 2603.16362 D3-RSMDE: 40× Faster and High-Fidelity Remote Sensing Monocular Depth Estimation
    106833, -- 2601.10373 Towards Efficient Low-rate Image Compression with Frequency-aware Diffusion Prio
    107533, -- 2511.19169 Test-Time Preference Optimization for Image Restoration
    107794, -- 2512.21710 RAPTOR: Real-Time High-Resolution UAV Video Prediction with Efficient Video Atte
    107865, -- 2505.04116 RFNNS: Robust Fixed Neural Network Steganography with Universal Text-to-Image Mo
    108454, -- 2412.04826 Pushing Rendering Boundaries: Hard Gaussian Splatting
    108693, -- 2605.25940 How Accurate are Video Quality Models for Diffusion-Based Video Super-Resolution
    108945, -- 2608.05798 KVAE: Family of Tokenizers for Multimodal Generative Models
    109406, -- external The Drift Kernel: Why Diffusion Models Change Even When Told Not To
    109523, -- 2608.14022 ForgeWM: Progressive Causal Training for Few-Step Action-Conditioned Video World
    109849, -- 2607.15585 SPEED: One-Step Pixel Diffusion for High-quality Video Frame Interpolation
    113486, -- 2505.00335 Efficient Neural Video Representation with Temporally Coherent Modulation
    114192, -- 2609.08230 ActionSplice: In-Flight Action Editing for Interactive World Models
    115015, -- 2409.12539 Improving cone-beam CT Image Quality with Knowledge Distillation-Enhanced Diffus
    115094, -- external Masked Residual Diffusion Probabilistic Model with Regional Asymmetry Prior for
    116429, -- external EVS-assisted Joint Deblurring Rolling-Shutter Correction and Video Frame Interpo
    116606, -- 2404.08921 PNeRV: Enhancing Spatial Consistency via Pyramidal Neural Representation for Vid
    117096, -- 2406.04961 Multiplane Prior Guided Few-Shot Aerial Scene Rendering
    117117, -- 2403.19517 XScale-NVS: Cross-Scale Novel View Synthesis with Hash Featurized Manifold
    117265, -- 2512.07381 Tesselation GS: Neural Mesh Gaussians for Robust Monocular Reconstruction of Dyn
    117544, -- 2607.10792 MAC-Splat: Multi-Attribute Consistency for High-Fidelity Sparse-View Reconstruct
    117549, -- 2603.23297 Drop-In Perceptual Optimization for 3D Gaussian Splatting
    117718, -- 2604.05182 LSRM: High-Fidelity Object-Centric Reconstruction via Scaled Context Windows
    118493, -- 2603.15129 Next-Frame Decoding for Ultra-Low-Bitrate Image Compression with Video Diffusion
    118542, -- 2608.14046 Source-Agnostic Image Translation Based on Latent Aware Adaptive Masking
    118614, -- 2606.29198 DTI: Dynamic Trajectory Initialization for Generative Face Video Super-Resolutio
    119858, -- 2412.11365 BiM-VFI: Bidirectional Motion Field-Guided Frame Interpolation for Video with No
    120193, -- 2412.00505 Good, Cheap, and Fast: Overfitted Image Compression with Wasserstein Distortion
    120755, -- 2605.23381 VDE: Training-Free Accelerating Rectified Flow Model via Velocity Decomposition
    120795, -- 2511.02777 PercHead: Perceptual Head Model for Single-Image 3D Head Reconstruction & Editin
    120927, -- 2604.10994 LumiMotion: Improving Gaussian Relighting with Scene Dynamics
    120961, -- external Perceptual Neural Video Compression with Color Separation and Rank Chain
    121140, -- external RAPID: Reusing Attention Sparsity with Inter-step Adaptation for Efficient Video
    121149, -- external More Natural, More Real: Object-aware Gaussian Splatting for 3D Visual Decoding
    121332, -- external LogCD: Local-to-global Consistency Distillation for Few-step Image Generation
    121476, -- external AeroGS: Scale-Aware Gaussian Splatting for Pose-Free Dynamic UAV Scene Reconstru
    122089, -- 2609.20633 Refinement Is Inherently Editable: Training-Free Prompt-to-Prompt Image Editing
    122193, -- 2609.30077 Rate-distortion optimization for full-reference image quality metrics via stocha
    122821, -- 2610.05967 JLD: Perceptual Distance Through A Jacobian Lens
    122916, -- 2610.04722 NAMVIS: Next-Scale Autoregressive Multi-View Image Synthesis
    123382, -- 2610.14726 LightVAE: Towards Compact and Efficient Video Autoencoders
    123561, -- 2610.20341 InfiniSplat v2: Analyzing and Improving Feed-Forward 3DGS from Any Views
    123593, -- 2610.06598 SimForcing: Distilling Simulation Motion Priors into Real-Domain Robot World Mod
    123770, -- 2610.26081 DeOverlay: A Benchmark and Source-Anchored Flow for Video Overlay Removal
    124044, -- 2610.31474 Skeleton-Grounded Latent Action Model for Robot World Models
    124427, -- external RoboExo: Structure-Guided Wrist-to-Exocentric Video Generation for Scalable Robo
    124850, -- external Deformable 2D Gaussian Splatting
    127394, -- external Identifying and Mitigating Diversity Collapse in Zero-Shot Personalization with
    128167, -- 2605.03821 RoboAlign-R1: Distilled Multimodal Reward Alignment for Robot Video World Models
    128546, -- external GeoRad-3D: Factorized Geometry Transport and Residual Radiometry for 3D Radar No
    129191, -- external Shaping Useful Noise: Energy Distributions Predict Visual Pretraining Quality
    129564, -- 2603.26571 GVCC: Zero-Shot Video Compression via Codebook-Driven Stochastic Rectified Flow
    130278, -- external PerQ: Inverse Generative Modeling for Neural Image Compression via Quantization
    131563 -- 2106.13228 HyperNeRF: A Higher-Dimensional Representation for Topologically Varying Neural
  );

DELETE FROM paper_method_exclusions x
USING lpips_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM lpips_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM lpips_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- lpips: 2224 reviewed negatives (local citers of the source that do not name the metric).
CREATE TEMP TABLE lpips_citers_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lpips'
  AND p.id IN (
    879, -- 1709.05424 NIMA: Neural Image Assessment
    981, -- 1711.08590 Contextual-based Image Inpainting: Infer, Match, and Translate
    1147, -- 1803.04626 Maintaining Natural Image Statistics with the Contextual Loss
    1266, -- 1805.03356 SPG-Net: Segmentation Prediction and Guidance Network for Image Inpainting
    1393, -- 1807.04742 Visual Reinforcement Learning with Imagined Goals
    1448, -- 1808.07371 Everybody Dance Now
    1504, -- 1809.07517 The 2018 PIRM Challenge on Perceptual Image Super-resolution
    1630, -- 1811.07104 On Hallucinating Context and Background Pixels from a Face Mask using Multi-scal
    1643, -- 1811.09393 Learning Temporal Coherence via Self-Supervision for GAN-based Video Generation
    1657, -- 1811.11459 Coordinate-based Texture Inpainting for Pose-Guided Image Generation
    1682, -- 1812.01717 Towards Accurate Generative Models of Video: A New Metric & Challenges
    1692, -- 1812.03910 Self-Contained Stylization via Steganography for Reverse and Serial Style Transf
    1697, -- 1812.04948 A Style-Based Generator Architecture for Generative Adversarial Networks
    1733, -- 1901.00212 EdgeConnect: Generative Image Inpainting with Adversarial Edge Learning
    1747, -- 1901.03396 Detecting Overfitting of Deep Generative Networks via Latent Recovery
    1758, -- 1901.05945 Foreground-aware Image Inpainting
    1812, -- 1902.03129 Towards Automatic Concept-based Explanations
    1829, -- 1902.06838 SC-FEGAN: Face Editing Generative Adversarial Network with User's Sketch and Col
    1933, -- 1903.12530 Photo-Realistic Monocular Gaze Redirection Using Generative Adversarial Networks
    1997, -- 1904.06726 VORNet: Spatio-temporally Consistent Video Inpainting for Object Removal
    1999, -- 1904.06991 Improved Precision and Recall Metric for Assessing Generative Models
    2032, -- 1904.10247 Free-form Video Inpainting with 3D Gated Convolution and Temporal PatchGAN
    2042, -- 1904.11486 Making Convolutional Networks Shift-Invariant Again
    2068, -- 1905.01723 Few-Shot Unsupervised Image-to-Image Translation
    2139, -- 1905.10854 Let's Agree to Agree: Neural Networks Share Classification Order on Real Dataset
    2309, -- 1907.01131 Learnable Gated Temporal Shift Module for Deep Video Inpainting
    2354, -- 1907.07174 Natural Adversarial Examples
    2532, -- 1909.05379 Specifying Object Attributes and Relations in Interactive Scene Generation
    2560, -- 1909.07957 An Internal Learning Approach to Video Inpainting
    2595, -- 1909.11856 Lightweight Image Super-Resolution with Information Multi-distillation Network
    2655, -- 1910.04256 Explaining image classifiers by removing input features using generative models
    2660, -- 1910.04760 A cost-effective method for improving and re-purposing large, pre-trained GANs b
    2877, -- 1911.13175 CURL: Neural Curve Layers for Global Image Enhancement
    2895, -- 1912.01865 StarGAN v2: Diverse Image Synthesis for Multiple Domains
    2916, -- 1912.04958 Analyzing and Improving the Image Quality of StyleGAN
    2925, -- 1912.06112 Unified Generative Adversarial Networks for Controllable Image-to-Image Translat
    2932, -- 1912.07116 Image Processing Using Multi-Code GAN Prior
    2976, -- 2001.00127 Reinforcement Learning with Goal-Distance Gradient
    3000, -- 2001.04642 Seeing the World in a Bag of Chips
    3121, -- 2002.08822 Automatic Shortcut Removal for Self-Supervised Representation Learning
    3129, -- 2002.09219 Stochastic Latent Residual Video Prediction
    3132, -- 2002.09797 Reliable Fidelity and Diversity Metrics for Generative Models
    3234, -- 2003.08934 NeRF: Representing Scenes as Neural Radiance Fields for View Synthesis
    3254, -- 2003.11571 Learning Layout and Style Reconfigurable GANs for Controllable Image Synthesis
    3315, -- 2004.03677 Semantic Image Manipulation Using Scene Graphs
    3333, -- 2004.04727 3D Photography using Context-aware Layered Depth Inpainting
    3351, -- 2004.06468 Self6D: Self-Supervised Monocular 6D Object Pose Estimation
    3384, -- 2004.09484 Bringing Old Photos Back to Life
    3524, -- 2005.01996 NTIRE 2020 Challenge on Real-World Image Super-Resolution: Methods and Results
    3657, -- 2006.02333 Scene relighting with illumination estimation in the latent space on an encoder-
    3755, -- 2006.10728 Diverse Image Generation via Self-Conditioned GANs
    3828, -- 2006.16241 The Many Faces of Robustness: A Critical Analysis of Out-of-Distribution General
    3916, -- 2007.10247 Learning Joint Spatial-Temporal Transformations for Video Inpainting
    3959, -- 2007.15646 Rewriting a Deep Generative Model
    3960, -- 2007.15651 Contrastive Learning for Unpaired Image-to-Image Translation
    3970, -- 2008.00418 Blind Face Restoration via Deep Multi-scale Component Dictionaries
    4100, -- 2009.01371 Real Image Super Resolution Via Heterogeneous Model Ensemble using GP-NAS
    4149, -- 2009.07047 Old Photo Restoration via Deep Latent Space Translation
    4196, -- 2009.10939 Scene Graph to Image Generation with Contextualized Object Layout Refinement
    4313, -- 2010.04595 GRF: Learning a General Radiance Field for 3D Representation and Rendering
    4322, -- 2010.05099 Diagnosing and Preventing Instabilities in Recurrent Video Processing
    4355, -- 2010.07492 NeRF++: Analyzing and Improving Neural Radiance Fields
    4400, -- 2010.11113 One Model to Reconstruct Them All: A Novel Way to Use the Stochastic Noise in St
    4575, -- 2011.09127 3D-FRONT: 3D Furnished Rooms with layOuts and semaNTics
    4613, -- 2011.12490 DeRF: Decomposed Radiance Fields
    4614, -- 2011.12799 StyleSpace Analysis: Disentangled Controls for StyleGAN Image Generation
    4617, -- 2011.12948 Nerfies: Deformable Neural Radiance Fields
    4625, -- 2011.13377 How Well Do Self-Supervised Models Transfer?
    4640, -- 2011.15126 One-Shot Free-View Neural Talking-Head Synthesis for Video Conferencing
    4653, -- 2012.01158 Single-Shot Freestyle Dance Reenactment
    4664, -- 2012.02190 pixelNeRF: Neural Radiance Fields from One or Few Images
    4679, -- 2012.03308 TediGAN: Text-Guided Diverse Face Image Generation and Manipulation
    4756, -- 2012.09841 Taming Transformers for High-Resolution Image Synthesis
    4761, -- 2012.10495 ShineOn: Illuminating Design Choices for Practical Video-based Virtual Clothing
    4883, -- 2101.04061 Towards Real-World Blind Face Restoration with Generative Facial Prior
    4891, -- 2101.04775 Towards Faster and Stabilized GAN Training for High-fidelity Few-shot Image Synt
    4898, -- 2101.05278 GAN Inversion: A Survey
    4987, -- 2102.02754 Only a Matter of Style: Age Transformation Using a Style-Based Regression Model
    5055, -- 2102.08860 ShaRF: Shape-conditioned Radiance Fields from a Single View
    5168, -- 2103.05606 NeX: Real-time View Synthesis with Neural Basis Expansion
    5189, -- 2103.06879 CoMoGAN: continuous model-guided image-to-image translation
    5215, -- 2103.09504 PredRNN: A Recurrent Neural Network for Spatiotemporal Predictive Learning
    5222, -- 2103.10022 Generating Diverse Structure for Image Inpainting With Hierarchical VQ-VAE
    5226, -- 2103.10380 FastNeRF: High-Fidelity Neural Rendering at 200FPS
    5274, -- 2103.13744 KiloNeRF: Speeding up Neural Radiance Fields with Thousands of Tiny MLPs
    5303, -- 2103.15606 GNeRF: GAN-based Neural Radiance Field without Posed Camera
    5310, -- 2103.15982 TransFill: Reference-guided Image Inpainting by Merging Multiple Color and Spati
    5329, -- 2103.16874 VITON-HD: High-Resolution Virtual Try-On via Misalignment-Aware Normalization
    5351, -- 2104.00677 Putting NeRF on a Diet: Semantically Consistent Few-Shot View Synthesis
    5355, -- 2104.00887 Multiple Heads are Better than One: Few-shot Font Generation with Multiple Local
    5366, -- 2104.01431 Aggregated Contextual Transformations for High-Resolution Image Inpainting
    5417, -- 2104.04785 Generating Physically-Consistent Satellite Imagery for Climate Visualizations
    5527, -- 2104.09068 Image Inpainting with External-internal Learning and Monochromic Bottleneck
    5557, -- 2104.10781 NTIRE 2021 Challenge on Quality Enhancement of Compressed Video: Methods and Res
    5569, -- 2104.11599 Region-Adaptive Deformable Network for Image Quality Assessment
    5615, -- 2104.14852 NTIRE 2021 Challenge on Video Super-Resolution
    5694, -- 2105.04619 Enhancing Photorealism Enhancement
    5704, -- 2105.05332 The DEVIL is in the Details: A Diagnostic Evaluation Benchmark for Video Inpaint
    5715, -- 2105.06070 GAN Prior Embedded Network for Blind Face Restoration in the Wild
    5817, -- 2105.14739 Controllable Person Image Synthesis with Spatially-Adaptive Warped Normalization
    5859, -- 2106.01505 Barbershop: GAN-based Image Compositing using Segmentation Masks
    5949, -- 2106.05744 Pivotal Tuning for Latent-based Editing of Real Images
    5974, -- 2106.06561 GANs N' Roses: Stable, Controllable, Diverse Image to Image Translation (works f
    5979, -- 2106.06927 Inverting Adversarially Robust Networks for Image Synthesis
    6119, -- 2106.13629 Animatable Neural Radiance Fields from Monocular RGB Videos
    6191, -- 2107.02791 Depth-supervised NeRF: Fewer Views and Faster Training for Free
    6256, -- 2107.07467 Only Train Once: A One-Shot Neural Network Training And Pruning Framework
    6344, -- 2108.00946 StyleGAN-NADA: CLIP-Guided Domain Adaptation of Image Generators
    6412, -- 2108.05892 PixelSynth: Generating a 3D-Consistent Experience from a Single Image
    6486, -- 2108.11684 Disentangled Generative Models for Robust Prediction of System Dynamics
    6605, -- 2109.05070 Instance-Conditioned GAN
    6740, -- 2109.13410 KITTI-360: A Novel Dataset and Benchmarks for Urban Scene Understanding in 2D an
    6809, -- 2110.02711 DiffusionCLIP: Text-Guided Diffusion Models for Robust Image Manipulation
    6995, -- 2110.08791 Taming Visually Guided Sound Generation
    7031, -- 2110.11728 BlendGAN: Implicitly GAN Blending for Arbitrary Stylized Face Generation
    7122, -- 2111.00772 AdaPool: Exponential Adaptive Pooling for Information-Retaining Downsampling
    7135, -- 2111.01619 StyleGAN of All Trades: Image Manipulation with Only Pretrained StyleGAN
    7162, -- 2111.03201 Compressing Sensor Data for Remote Assistance of Autonomous Vehicles using Deep
    7265, -- 2111.10337 Advancing High-Resolution Video-Language Representation with Large-Scale Video T
    7279, -- 2111.11215 Direct Voxel Grid Optimization: Super-fast Convergence for Radiance Fields Recon
    7321, -- 2111.13924 A Practical Contrastive Learning Framework for Single-Image Super-Resolution
    7334, -- 2111.14818 Blended Diffusion for Text-driven Editing of Natural Images
    7353, -- 2111.15666 HyperStyle: StyleGAN Inversion with HyperNetworks for Real Image Editing
    7362, -- 2112.00384 Exploration into Translation-Equivariant Image Quantization
    7368, -- 2112.00724 RegNeRF: Regularizing Neural Radiance Fields for View Synthesis from Sparse Inpu
    7397, -- 2112.01799 Global Context with Discrete Diffusion in Vector Quantised Modelling for Image G
    7411, -- 2112.02520 Neural Photometry-guided Visual Attribute Transfer
    7433, -- 2112.03842 A Survey on Intrinsic Images: Delving Deep Into Lambert and Beyond
    7474, -- 2112.05744 More Control for Free! Image Synthesis with Semantic Diffusion Guidance
    7577, -- 2112.10752 High-Resolution Image Synthesis with Latent Diffusion Models
    7587, -- 2112.11641 JoJoGAN: One Shot Face Stylization
    7607, -- 2112.13592 Multimodal Image Synthesis and Editing: The Generative AI Era
    7690, -- 2201.05120 SeamlessGAN: Self-Supervised Synthesis of Tileable Texture Maps
    7743, -- 2201.08663 Fast Differentiable Matrix Square Root
    7761, -- 2201.09865 RePaint: Inpainting using Denoising Diffusion Probabilistic Models
    7820, -- 2201.13433 Third Time's the Charm? Image and Video Editing with StyleGAN3
    7823, -- 2202.00181 CLA-NeRF: Category-Level Articulated Neural Radiance Field
    7909, -- 2202.04200 MaskGIT: Masked Generative Image Transformer
    7940, -- 2202.05822 CLIPasso: Semantically-Aware Object Sketching
    8047, -- 2202.11777 Art Creation with Multi-Conditional StyleGANs
    8055, -- 2202.12211 Self-Distilled StyleGAN: Towards Generation from Internet Photos
    8115, -- 2203.00867 Incremental Transformer Structure Enhanced Image Inpainting with Masking Positio
    8124, -- 2203.01296 Half Wavelet Attention on M-Net+ for Low-Light Image Enhancement
    8159, -- 2203.03396 Screentone-Preserved Manga Retargeting
    8185, -- 2203.04564 Region-Aware Face Swapping
    8245, -- 2203.07293 InsetGAN for Full-Body Image Generation
    8340, -- 2203.10339 Occlusion-Aware Self-Supervised Monocular 6D Object Pose Estimation
    8355, -- 2203.10821 Sem2NeRF: Converting Single-View Semantic Masks to Neural Radiance Fields
    8409, -- 2203.13131 Make-A-Scene: Scene-Based Text-to-Image Generation with Human Priors
    8443, -- 2203.14402 UV Volumes for Real-time Rendering of Editable Free-view Human Performance
    8448, -- 2203.14512 Expressive Talking Head Video Encoding in StyleGAN2 Latent-Space
    8465, -- 2203.15270 MAT: Mask-Aware Transformer for Large Hole Image Inpainting
    8469, -- 2203.15375 A Style-aware Discriminator for Controllable Image Translation
    8516, -- 2203.17261 R2L: Distilling Neural Radiance Field to Neural Light Field for Efficient Novel
    8518, -- 2203.17266 TransEditor: Transformer-Based Dual-Space GAN for Highly Controllable Facial Edi
    8524, -- 2204.00227 Perception Prioritized Training of Diffusion Models
    8617, -- 2204.03638 Long Video Generation with Time-Agnostic VQGAN and Time-Sensitive Transformer
    8634, -- 2204.04210 Dancing under the stars: video denoising in starlight
    8733, -- 2204.07486 Patch-wise Contrastive Style Learning for Instagram Filter Removal
    8810, -- 2204.10549 JIFF: Jointly-aligned Implicit Face Function for High Quality Single View Clothe
    8989, -- 2205.05076 Reduce Information Loss in Transformers for Pluralistic Image Inpainting
    9001, -- 2205.05810 Performing Video Frame Prediction of Microbial Growth with a Recurrent Neural Ne
    9302, -- 2205.15996 Text2Human: Text-Driven Controllable Human Image Generation
    9384, -- 2206.02779 Blended Latent Diffusion
    9408, -- 2206.03753 Task Agnostic Restoration of Natural Video Dynamics
    9460, -- 2206.06481 RigNeRF: Fully Controllable Neural 3D Portraits
    9523, -- 2206.08823 Language with Vision: a Study on Grounded Word and Sentence Embeddings
    9530, -- 2206.09027 Landscape Learning for Neural Network Inversion
    9538, -- 2206.09479 StudioGAN: A Taxonomy and Benchmark of GANs for Image Synthesis
    9630, -- 2206.14180 High-Resolution Virtual Try-On with Misalignment and Occlusion-Handled Condition
    9746, -- 2207.04808 CCPL: Contrastive Coherence Preserving Loss for Versatile Style Transfer
    9761, -- 2207.05300 SD-GAN: Semantic Decomposition for Face Image Synthesis with Discrete Attribute
    9763, -- 2207.05378 Collaborative Neural Rendering using Anime Character Sheets
    9790, -- 2207.06831 iColoriT: Towards Propagating Local Hint to the Right Region in Interactive Colo
    9846, -- 2207.09935 Towards Efficient and Scale-Robust Ultra-High-Definition Image Demoireing
    9864, -- 2207.10564 Unsupervised Night Image Enhancement: When Layer Decomposition Meets Light-Effec
    9939, -- 2207.14606 WISE: Whitebox Image Stylization by Example-based Learning
    9941, -- 2208.00277 MobileNeRF: Exploiting the Polygon Rasterization Pipeline for Efficient Neural F
    9946, -- 2208.00712 Cross Attention Based Style Distribution for Controllable Person Image Synthesis
    9992, -- 2208.03382 Keys to Better Image Inpainting: Structure and Texture Go Hand in Hand
    10042, -- 2208.06768 Flow-Guided Transformer for Video Inpainting
    10060, -- 2208.07765 Style Your Hair: Latent Optimization for Pose-Invariant Hairstyle Transfer via L
    10140, -- 2208.12242 DreamBooth: Fine Tuning Text-to-Image Diffusion Models for Subject-Driven Genera
    10146, -- 2208.12408 User-Controllable Latent Transformer for StyleGAN Image Layout Editing
    10184, -- 2208.14851 Dual-Space NeRF: Learning Animatable Avatars and Scene Lighting in Separate Spac
    10291, -- 2209.07162 Brain Imaging Generation with Latent Diffusion Models
    10419, -- 2209.13032 Totems: Physical Objects for Verifying Visual Integrity
    10507, -- 2210.00379 NeRF: Neural Radiance Field in 3D Vision, A Comprehensive Review
    10512, -- 2210.00647 IntrinsicNeRF: Learning Intrinsic Neural Radiance Fields for Editable Novel View
    10554, -- 2210.01887 Collecting The Puzzle Pieces: Disentangled Self-Driven Human Pose Transfer by Pe
    10742, -- 2210.06108 Reconstructing Personalized Semantic Facial NeRF Models From Monocular Video
    10866, -- 2210.09276 Imagic: Text-Based Real Image Editing with Diffusion Models
    10882, -- 2210.10090 How to Boost Face Recognition with StyleGAN?
    10886, -- 2210.10175 Intra-Source Style Augmentation for Improved Domain Generalization
    10901, -- 2210.10473 FaceDancer: Pose- and Occlusion-Aware High Fidelity Face Swapping
    10926, -- 2210.11248 OCR-VQGAN: Taming Text-within-Image Generation
    10934, -- 2210.11427 DiffEdit: Diffusion-based semantic image editing with mask guidance
    11112, -- 2210.15796 Layout Aware Inpainting for Automated Furniture Removal in Indoor Scenes
    11209, -- 2211.02048 Efficient Spatially Sparse Inference for Conditional GANs and Diffusion Models
    11341, -- 2211.07600 Latent-NeRF for Shape-Guided Generation of 3D Shapes and Textures
    11430, -- 2211.10157 UMFuse: Unified Multi View Fusion for Human Editing applications
    11466, -- 2211.11082 DynIBaR: Neural Dynamic Image-Based Rendering
    11491, -- 2211.11505 Local-to-Global Registration for Bundle-Adjusting Neural Radiance Fields
    11509, -- 2211.11825 Multi-Directional Subspace Editing in Style-Space
    11517, -- 2211.12131 DiffDreamer: Towards Consistent Unsupervised Single-view Scene Extrapolation wit
    11521, -- 2211.12254 SPIn-NeRF: Multiview Segmentation and Perceptual Inpainting with Neural Radiance
    11526, -- 2211.12347 The Euclidean Space is Evil: Hyperbolic Attribute Editing for Few-shot Image Gen
    11527, -- 2211.12352 GlowGAN: Unsupervised Learning of HDR Images from LDR Images in the Wild
    11528, -- 2211.12380 OCTET: Object-aware Counterfactual Explanations
    11529, -- 2211.12446 EDICT: Exact Diffusion Inversion via Coupled Transformations
    11534, -- 2211.12499 Instant Volumetric Head Avatars
    11536, -- 2211.12509 SimVPv2: Towards Simple yet Powerful Spatiotemporal Predictive Learning
    11556, -- 2211.12853 BAD-NeRF: Bundle Adjusted Deblur Neural Radiance Fields
    11605, -- 2211.13874 FFHQ-UV: Normalized Facial UV-Texture Dataset for 3D Face Reconstruction
    11622, -- 2211.14306 RUST: Latent Neural Scene Representations from Unposed Imagery
    11623, -- 2211.14308 WALDO: Future Video Synthesis using Object Layer Decomposition and Parametric Fl
    11643, -- 2211.14758 VideoReTalking: Audio-based Lip Synchronization for Talking Head Video Editing I
    11732, -- 2212.00190 Mixed Neural Voxels for Fast Multi-view Video Synthesis
    11760, -- 2212.00793 Unite and Conquer: Plug & Play Multi-Modal Synthesis using Diffusion Models
    11789, -- 2212.01602 StegaNeRF: Embedding Invisible Information within Neural Radiance Fields
    11794, -- 2212.01789 Multiscale Structure Guided Diffusion for Image Deblurring
    11806, -- 2212.02469 One-shot Implicit Animatable Avatars with Model-based Priors
    11811, -- 2212.02501 SceneRF: Self-Supervised Monocular 3D Scene Reconstruction with Radiance Fields
    11833, -- 2212.03237 RANA: Relightable Articulated Neural Avatars
    11837, -- 2212.03267 NeRDi: Single-View NeRF Synthesis with Language-Guided Diffusion as General Imag
    11859, -- 2212.04105 All-to-key Attention for Arbitrary Style Transfer
    11866, -- 2212.04247 EditableNeRF: Editing Topologically Varying Neural Radiance Fields by Key Points
    11874, -- 2212.04488 Multi-Concept Customization of Text-to-Image Diffusion
    11875, -- 2212.04489 SINE: SINgle Image Editing with Text-to-Image Diffusion Models
    11883, -- 2212.04655 MIMO Is All You Need : A Strong Multi-In-Multi-Out Baseline for Video Prediction
    11886, -- 2212.04705 Physics-based Indirect Illumination for Inverse Rendering
    11893, -- 2212.04871 Spurious Features Everywhere -- Large-Scale Detection of Harmful Spurious Featur
    11904, -- 2212.05199 MAGVIT: Masked Generative Video Transformer
    11922, -- 2212.05895 Diff-Font: Diffusion Model for Robust One-Shot Font Generation
    11946, -- 2212.06512 DifFace: Blind Face Restoration with Diffused Error Contraction
    11971, -- 2212.07388 NoPe-NeRF: Optimising Neural Radiance Field with No Pose Prior
    11974, -- 2212.07501 Diffusion Probabilistic Models beat GANs on Medical Images
    12004, -- 2212.08057 Real-Time Neural Light Field on Mobile Devices
    12060, -- 2212.09262 Out-of-domain GAN inversion via Invertibility Decomposition for Photo-Realistic
    12197, -- 2212.11966 Removing Objects From Neural Radiance Fields
    12224, -- 2212.13056 MonoNeRF: Learning a Generalizable Dynamic Radiance Field from Monocular Videos
    12250, -- 2212.14359 StyleRes: Transforming the Residuals for Real Image Editing with StyleGAN
    12275, -- 2301.00553 Lightweight Image Inpainting by Stripe Window Transformer with Joint Attention t
    12392, -- 2301.05225 Domain Expansion of Image Generators
    12410, -- 2301.06281 DPE: Disentanglement of Pose and Expression for General Video Portrait Editing
    12420, -- 2301.06782 A Large-Scale Outdoor Multi-modal Dataset and Benchmark for Novel View Synthesis
    12435, -- 2301.07525 OmniObject3D: Large-Vocabulary 3D Object Dataset for Realistic Perception, Recon
    12448, -- 2301.08153 SwiftAvatar: Efficient Auto-Creation of Parameterized Stylized Character on Arbi
    12490, -- 2301.09632 HexPlane: A Fast Representation for Dynamic Scenes
    12491, -- 2301.09637 InfiniCity: Infinite-Scale City Synthesis
    12889, -- 2302.03027 Zero-shot Image-to-Image Translation
    13015, -- 2302.05361 Leveraging Inpainting for Single-Image Shadow Removal
    13021, -- 2302.05496 MaskSketch: Unpaired Structure-guided Masked Image Generation
    13072, -- 2302.06608 3D-aware Blending with Generative NeRFs
    13082, -- 2302.06826 DiffFashion: Reference-based Fashion Design with Structure-aware Transfer by Dif
    13116, -- 2302.07685 Video Probabilistic Diffusion Models in Projected Latent Space
    13154, -- 2302.08504 PersonNeRF: Personalized Reconstruction from Photo Collections
    13155, -- 2302.08509 3D-aware Conditional Image Synthesis
    13182, -- 2302.09311 Temporal Interpolation Is All You Need for Dynamic Neural Radiance Fields
    13238, -- 2302.10980 MultiRobustBench: Benchmarking Robustness Against Multiple Attacks
    13535, -- 2303.03684 MOSO: Decomposing MOtion, Scene and Object for Video Prediction
    13578, -- 2303.04761 Video-P2P: Video Editing with Cross-attention Control
    13609, -- 2303.05312 3D Video Loops from Asynchronous Input
    13622, -- 2303.05511 Scaling up GANs for Text-to-Image Synthesis
    13629, -- 2303.05724 3D Cinemagraphy from a Single Image
    13696, -- 2303.06885 DR2: Diffusion-based Robust Degradation Remover for Blind Face Restoration
    13698, -- 2303.06919 NeRFLiX: High-Quality Neural View Synthesis by Learning a Degradation-Driven Int
    13700, -- 2303.07012 AGTGAN: Unpaired Image Translation for Photographic Ancient Character Generation
    13766, -- 2303.08138 Diversity-Aware Meta Visual Prompting
    13789, -- 2303.08717 Re-ReND: Real-time Rendering of NeRFs across Devices
    13808, -- 2303.09036 Mimic3D: Thriving 3D-Aware GANs via 3D-to-2D Imitation
    13824, -- 2303.09375 DINAR: Diffusion Inpainting of Neural Textures for One-Shot Human Avatars
    13832, -- 2303.09472 DiffIR: Efficient Diffusion Model for Image Restoration
    13836, -- 2303.09535 FateZero: Fusing Attentions for Zero-shot Text-based Video Editing
    13856, -- 2303.09826 Learning Data-Driven Vector-Quantized Degradation Model for Animation Video Supe
    13896, -- 2303.10598 StyleRF: Zero-shot 3D Style Transfer of Neural Radiance Fields
    13928, -- 2303.11305 SVDiff: Compact Parameter Space for Diffusion Fine-Tuning
    13929, -- 2303.11306 Localizing Object-level Shape Variations with Text-to-Image Diffusion Models
    13933, -- 2303.11328 Zero-1-to-3: Zero-shot One Image to 3D Object
    13978, -- 2303.11963 NEMTO: Neural Environment Matting for Novel View and Relighting Synthesis of Tra
    14000, -- 2303.12326 Make Encoder Great Again in 3D GAN Inversion through Geometry and Occlusion-Awar
    14002, -- 2303.12343 LD-ZNet: A Latent Diffusion Approach for Text-Based Image Segmentation
    14028, -- 2303.12789 Instruct-NeRF2NeRF: Editing 3D Scenes with Instructions
    14029, -- 2303.12791 SHERF: Generalizable Human NeRF from a Single Image
    14036, -- 2303.13014 Semantic Ray: Learning a Generalizable Semantic Field with Cross-Reprojection At
    14037, -- 2303.13022 ENVIDR: Implicit Differentiable Renderer with Neural Environment Lighting
    14039, -- 2303.13071 PanoHead: Geometry-Aware 3D Full-Head Synthesis in 360$^{\circ}$
    14045, -- 2303.13132 Masked Image Training for Generalizable Deep Image Denoising
    14082, -- 2303.13791 Progressively Optimized Local Radiance Fields for Robust View Synthesis
    14090, -- 2303.13900 A Three-Player GAN for Super-Resolution in Magnetic Resonance Imaging
    14093, -- 2303.13953 AssetField: Assets Mining and Reconfiguration in Ground Feature Plane Representa
    14107, -- 2303.14184 Make-It-3D: High-Fidelity 3D Creation from A Single Image with Diffusion Prior
    14124, -- 2303.14435 NeRF-DS: Neural Radiance Fields for Dynamic Specular Objects
    14134, -- 2303.14536 SUDS: Scalable Urban Dynamic Scenes
    14137, -- 2303.14587 PAniC-3D: Stylized Single-view 3D Reconstruction from Portraits of Anime Charact
    14144, -- 2303.14672 Sat2Density: Faithful Density Learning from Satellite-Ground Image Pairs
    14169, -- 2303.15065 Single-subject Multi-contrast MRI Super-resolution via Implicit Neural Represent
    14190, -- 2303.15435 The Stable Signature: Rooting Watermarks in Latent Diffusion Models
    14202, -- 2303.15649 StyleDiffusion: Prompt-Embedding Inversion for Text-Based Editing
    14230, -- 2303.16196 SparseNeRF: Distilling Depth Ranking for Few-shot Novel View Synthesis
    14232, -- 2303.16201 ASIC: Aligning Sparse in-the-wild Image Collections
    14255, -- 2303.16617 NeFII: Inverse Rendering for Reflectance Decomposition with Near-Field Indirect
    14295, -- 2303.17368 SynBody: Synthetic Dataset with Layered Human Models for 3D Human Perception and
    14302, -- 2303.17546 PAIR-Diffusion: A Comprehensive Multimodal Object-Level Image Editor
    14304, -- 2303.17550 DAE-Talker: High Fidelity Speech-Driven Talking Face Generation with Diffusion A
    14310, -- 2303.17569 Iterative Prompt Learning for Unsupervised Backlit Image Enhancement
    14325, -- 2303.17712 S-VolSDF: Sparse Multi-View Stereo Regularization of Neural Implicit Surfaces
    14331, -- 2303.17806 Neural Microfacet Fields for Inverse Rendering
    14372, -- 2304.00451 Re-IQA: Unsupervised Learning for Image Quality Assessment in the Wild
    14384, -- 2304.00782 NeMF: Inverse Volume Rendering with Neural Microflake Field
    14389, -- 2304.00898 Tunable Convolutions with Parametric Multi-Loss Optimization
    14404, -- 2304.01194 Burstormer: Burst Image Restoration and Enhancement Transformer
    14420, -- 2304.01436 Learning Personalized High Quality Volumetric Head Avatars from Monocular RGB Vi
    14436, -- 2304.01686 HyperCUT: Video Sequence from a Single Blurry Image using Unsupervised Ordering
    14456, -- 2304.02001 MonoHuman: Animatable Human Neural Field from Monocular Video
    14460, -- 2304.02013 NPC: Neural Point Characters from Video
    14467, -- 2304.02163 GINA-3D: Learning to Generate Implicit Neural Assets in the Wild
    14481, -- 2304.02602 Generative Novel View Synthesis with 3D-Aware Diffusion Models
    14508, -- 2304.03283 Diffusion Models as Masked Autoencoders
    14514, -- 2304.03400 RoSteALS: Robust Steganography using Autoencoder Latent Space
    14545, -- 2304.04012 Progressive Volume Distillation with Active Learning for Efficient NeRF Architec
    14557, -- 2304.04278 Point-SLAM: Dense Neural Point Cloud-based SLAM
    14568, -- 2304.04461 Modernizing Old Photos Using Multiple References via Photorealistic Style Transf
    14635, -- 2304.05868 Mesh2Tex: Generating Mesh Textures from Image Queries
    14646, -- 2304.06025 DreamPose: Fashion Image-to-Video Synthesis via Stable Diffusion
    14653, -- 2304.06140 An Edit Friendly DDPM Noise Space: Inversion and Manipulations
    14657, -- 2304.06244 Computationally-Efficient Neural Image Compression with Shallow Decoders
    14660, -- 2304.06287 NeRFVS: Neural Radiance Fields for Free View Synthesis via Geometry Scaffolds
    14675, -- 2304.06700 Control3Diff: Learning Controllable 3D Diffusion Models from Single-view Images
    14676, -- 2304.06704 How Will It Drape Like? Capturing Fabric Mechanics from Depth Images
    14680, -- 2304.06714 Single-Stage Diffusion NeRF: A Unified Approach to 3D Generation and Reconstruct
    14706, -- 2304.07090 Delta Denoising Score
    14759, -- 2304.08757 NeAI: A Pre-convoluted Representation for Plug-and-Play Neural Ambient Illuminat
    14764, -- 2304.08870 UPGPT: Universal Diffusion Model for Person Image Generation, Editing and Pose T
    14770, -- 2304.08971 SurfelNeRF: Neural Surfel Radiance Fields for Online Photorealistic Reconstructi
    14793, -- 2304.09479 DiFaReli++: Diffusion Face Relighting with Consistent Cast Shadows
    14801, -- 2304.09677 Reference-guided Controllable Inpainting of Neural Radiance Fields
    14822, -- 2304.09987 Tetra-NeRF: Representing Neural Radiance Fields Using Tetrahedra
    14824, -- 2304.10036 Visual DNA: Representing and Comparing Images using Distributions of Neuron Acti
    14826, -- 2304.10075 Multiscale Representation for Real-Time Anti-Aliasing Neural Rendering
    14827, -- 2304.10131 Learning Bottleneck Concepts in Image Classification
    14884, -- 2304.11335 Two Birds, One Stone: A Unified Framework for Joint Learning of Image and Video
    14919, -- 2304.12294 Explicit Correspondence Matching for Generalizable Neural Radiance Fields
    14984, -- 2304.13681 Ray Conditioning: Trading Photo-consistency for Photo-realism in Multi-view Imag
    15030, -- 2304.14401 ActorsNeRF: Animatable Few-shot Human Rendering with Generalizable NeRFs
    15082, -- 2305.00434 EVREAL: Towards a Comprehensive Benchmark and Analysis Suite for Event-based Vid
    15088, -- 2305.00521 StyleLipSync: Style-based Personalized Lip-sync Video Generation
    15234, -- 2305.03027 NeRSemble: Multi-view Radiance Field Reconstruction of Human Heads
    15237, -- 2305.03043 Single-Shot Implicit Morphable Faces with Consistent Texture Parameterization
    15241, -- 2305.03051 Controllable Visual-Tactile Synthesis
    15282, -- 2305.03892 DocDiff: Document Enhancement via Residual Diffusion Models
    15306, -- 2305.04268 Multi-Space Neural Radiance Fields
    15316, -- 2305.04441 Prompt Tuning Inversion for Text-Driven Image Editing Using Diffusion Models
    15335, -- 2305.04789 AvatarReX: Real-time Expressive Full-body Avatars
    15342, -- 2305.04923 Learning to Evaluate the Artness of AI-generated Images
    15401, -- 2305.05992 MMoT: Mixture-of-Modality-Tokens Transformer for Composed Multimodal Conditional
    15432, -- 2305.06356 HumanRF: High-Fidelity Neural Radiance Fields for Humans in Motion
    15466, -- 2305.07015 Exploiting Diffusion Prior for Real-World Image Super-Resolution
    15494, -- 2305.07514 BlendFields: Few-Shot Example-Driven Facial Modeling
    15534, -- 2305.08192 Diffusion Models for Imperceptible and Transferable Adversarial Attack
    15544, -- 2305.08293 Identity-Preserving Talking Face Generation with Landmark and Appearance Priors
    15616, -- 2305.09641 FitMe: Deep Photorealistic 3D Morphable Model Avatars
    15715, -- 2305.10973 Drag Your GAN: Interactive Point-based Manipulation on the Generative Image Mani
    15767, -- 2305.11520 LaCon: Late-Constraint Diffusion for Steerable Guided Image Synthesis
    15775, -- 2305.11588 Text2NeRF: Text-Driven 3D Scene Generation with Neural Radiance Fields
    15955, -- 2305.13501 LaDI-VTON: Latent Diffusion Textual-Inversion Enhanced Virtual Try-On
    16321, -- 2305.16312 UMat: Uncertainty-Aware Single Image High Resolution Material Capture
    16363, -- 2305.16807 Negative-prompt Inversion: Fast Image Inversion for Editing with Text-guided Dif
    16600, -- 2305.19066 Nested Diffusion Processes for Anytime Image Generation
    16663, -- 2305.19862 Self-supervised Learning to Bring Dual Reversed Rolling Shutter Images Alive
    16795, -- 2306.00950 Differential Diffusion: Giving Each Pixel Its Strength
    16845, -- 2306.01344 Adjustable Visual Appearance for Generalizable Novel View Synthesis
    17181, -- 2306.05410 LU-NeRF: Scene and Pose Estimation by Synchronizing Local Unposed NeRFs
    17254, -- 2306.06362 Aria Digital Twin: A New Benchmark Dataset for Egocentric 3D Machine Perception
    17262, -- 2306.06513 Learning Image-Adaptive Codebooks for Class-Agnostic Image Restoration
    17365, -- 2306.07881 Viewset Diffusion: (0-)Image-Conditioned 3D Generative Models from 2D Data
    17498, -- 2306.09346 Rosetta Neurons: Mining the Common Units in a Model Zoo
    17681, -- 2306.12760 Blended-NeRF: Zero-Shot Object Generation and Blending in Existing Neural Radian
    17749, -- 2306.14153 DomainStudio: Fine-Tuning Diffusion Models for Domain-Driven Image Generation us
    17760, -- 2306.14435 DragDiffusion: Harnessing Diffusion Models for Interactive Point-based Image Edi
    17798, -- 2306.15242 SPDER: Semiperiodic Damping-Enabled Object Representation
    17916, -- 2306.17723 FlipNeRF: Flipped Reflection Rays for Few-shot Novel View Synthesis
    17927, -- 2307.00040 DisCo: Disentangled Control for Realistic Human Dance Generation
    17953, -- 2307.00648 Intra- & Extra-Source Exemplar-Based Style Synthesis for Improved Domain General
    17975, -- 2307.01199 NeuBTF: Neural fields for BTF encoding and transfer
    18070, -- 2307.03190 Text-Guided Synthesis of Eulerian Cinemagraphs
    18103, -- 2307.03992 Stimulating Diffusion Model for Image Denoising via Adaptive Embedding and Ensem
    18129, -- 2307.04684 FreeDrag: Feature Dragging for Reliable Point-based Image Editing
    18146, -- 2307.05000 Neural Point-based Volumetric Avatar: Surface-guided Neural Points for Efficient
    18151, -- 2307.05134 TIAM -- A Metric for Evaluating Alignment in Text-to-Image Generation
    18166, -- 2307.05468 My3DGen: A Scalable Personalized 3D Generative Model
    18261, -- 2307.07754 Bidirectionally Deformable Motion Modulation For Video-based Human Pose Transfer
    18285, -- 2307.08093 Cross-Ray Neural Radiance Fields for Novel-view Synthesis from Unconstrained Ima
    18300, -- 2307.08265 Extreme Image Compression using Fine-tuned VQGANs
    18313, -- 2307.08397 CLIP-Guided StyleGAN Inversion for Text-Driven Real Image Editing
    18350, -- 2307.08996 Towards Authentic Face Restoration with Iterative Diffusion Models and Beyond
    18373, -- 2307.09323 Efficient Region-Aware Neural Radiance Fields for High-Fidelity Talking Portrait
    18458, -- 2307.10776 Urban Radiance Field Representation with Deformable Neural Mesh Primitives
    18466, -- 2307.10854 BlendFace: Re-designing Identity Encoders for Face-Swapping
    18497, -- 2307.11335 Tri-MipRF: Tri-Mip Representation for Efficient Anti-Aliasing Neural Radiance Fi
    18505, -- 2307.11418 FaceCLIPNeRF: Text-driven 3D Face Manipulation using Deformable Neural Radiance
    18513, -- 2307.11526 CopyRNeRF: Protecting the CopyRight of Neural Radiance Fields
    18538, -- 2307.12027 On the Effectiveness of Spectral Discriminators for Perceptual Quality Improveme
    18553, -- 2307.12291 TransHuman: A Transformer-based Human Representation for Generalizable Neural Hu
    18561, -- 2307.12493 TF-ICON: Diffusion-Based Training-Free Cross-Domain Image Composition
    18659, -- 2307.14127 Creative Birds: Self-Supervised Single-View 3D Style Transfer
    18709, -- 2307.15033 Diverse Inpainting and Editing with GAN Inversion
    18717, -- 2307.15058 MARS: An Instance-aware, Modular and Realistic Simulator for Autonomous Driving
    18722, -- 2307.15139 Online Clustered Codebook
    18732, -- 2307.15333 Dynamic PlenOctree for Adaptive Sampling Refinement in Explicit NeRF
    18882, -- 2308.01536 MFIM: Megapixel Facial Identity Manipulation
    18901, -- 2308.01898 UniSim: A Neural Closed-Loop Sensor Simulator
    18964, -- 2308.03060 TOPIQ: A Top-down Approach from Semantics to Distortions for Image Quality Asses
    18977, -- 2308.03262 A Benchmark for Chinese-English Scene Text Image Super-resolution
    18980, -- 2308.03280 Mirror-NeRF: Learning Neural Radiance Fields for Mirrors with Whitted-Style Ray
    19011, -- 2308.03757 3D Motion Magnification: Visualizing Subtle Motions with Time Varying Radiance F
    19036, -- 2308.04163 Under-Display Camera Image Restoration with Scattering Effect
    19062, -- 2308.04622 Rendering Humans from Object-Occluded Monocular Videos
    19069, -- 2308.04699 GIFD: A Generative Gradient Inversion Method with Feature Domain Optimization
    19080, -- 2308.04826 WaveNeRF: Wavelet-based Generalizable Neural Radiance Fields
    19154, -- 2308.06097 RIGID: Recurrent GAN Inversion and Editing of Real Face Videos
    19155, -- 2308.06101 Taming the Power of Diffusion Models for High-Quality Virtual Try-On with Appear
    19234, -- 2308.07228 RestoreFormer++: Towards Real-World Blind Face Restoration from Undegraded Key-V
    19284, -- 2308.07903 Relightable and Animatable Neural Avatar from Sparse-View Video
    19296, -- 2308.08011 Shortcut-V2V: Compression Framework for Video-to-Video Translation based on Temp
    19413, -- 2308.09519 Leveraging Intrinsic Properties for Non-Rigid Garment Alignment
    19436, -- 2308.09712 HumanLiff: Layer-wise 3D Human Generation with Diffusion Model
    19437, -- 2308.09713 Dynamic 3D Gaussians: Tracking by Persistent Dynamic View Synthesis
    19438, -- 2308.09716 Diff2Lip: Audio Conditioned Diffusion Models for Lip-Synchronization
    19439, -- 2308.09717 Smoothness Similarity Regularization for Few-Shot GAN Adaptation
    19486, -- 2308.10122 HollowNeRF: Pruning Hashgrid-Based NeRFs with Trainable Collision Mitigation
    19520, -- 2308.10337 Strata-NeRF : Neural Radiance Fields for Stratified Scenes
    19539, -- 2308.10490 Texture Generation on 3D Meshes with Point-UV Diffusion
    19545, -- 2308.10554 Improving Diversity in Zero-Shot GAN Adaptation with Semantic Variations
    19658, -- 2308.11793 Enhancing NeRF akin to Enhancing LLMs: Generalizable NeRF Transformer with Mixtu
    19671, -- 2308.11917 LFS-GAN: Lifelong Few-Shot Image Generation
    19731, -- 2308.12605 APLA: Additional Perturbation for Latent Noise with Adversarial Training Enables
    19743, -- 2308.12866 ToonTalker: Cross-Domain Face Reenactment
    19758, -- 2308.12968 Scenimefy: Learning to Craft Anime Scene via Semi-Supervised Image-to-Image Tran
    19768, -- 2308.13164 Diff-Retinex: Rethinking Low-light Image Enhancement with A Generative Diffusion
    19789, -- 2308.13404 Relighting Neural Radiance Fields with Shadow and Highlight Hints
    19804, -- 2308.13628 HiFiHR: Enhancing 3D Hand Reconstruction from a Single Image via High-Fidelity T
    19809, -- 2308.13712 Residual Denoising Diffusion Models
    19815, -- 2308.13798 DM-VTON: Distilled Mobile Real-time Virtual Try-On
    19821, -- 2308.13888 Neural Implicit Morphing of Face Images
    19831, -- 2308.14078 Sparse3D: Distilling Multiview-Consistent Diffusion for Object Reconstruction fr
    19878, -- 2308.14761 Unified Concept Editing in Diffusion Models
    19946, -- 2308.16154 MMVP: Motion-Matrix-based Video Prediction
    19968, -- 2308.16582 Any-Size-Diffusion: Toward Efficient Text-Driven Synthesis for Any-Size HD Image
    19996, -- 2309.00066 SoDaCam: Software-defined Cameras via Single-Photon Imaging
    20003, -- 2309.00216 Human-Inspired Facial Sketch Synthesis with Dynamic Adaptation
    20031, -- 2309.00827 Few shot font generation via transferring similarity guided global style and qua
    20084, -- 2309.01700 ControlMat: A Controlled Generative Approach to Material Capture
    20106, -- 2309.02020 RawHDR: High Dynamic Range Image Reconstruction from a Single Raw Image
    20113, -- 2309.02119 Hierarchical Masked 3D Diffusion Model for Video Outpainting
    20132, -- 2309.02434 ReliTalk: Relightable Talking Portrait Generation from a Single Video
    20179, -- 2309.03504 Stroke-based Neural Painting and Stylization with Dynamically Predicted Painting
    20191, -- 2309.03809 SimNP: Learning Self-Similarity Priors Between Neural Points
    20204, -- 2309.03900 Learning Continuous Exposure Value Representations for Single-Image HDR Reconstr
    20225, -- 2309.04410 DeformToon3D: Deformable 3D Toonification from Neural Radiance Fields
    20245, -- 2309.04800 VeRi3D: Generative Vertex-based Radiance Fields for 3D Controllable Human Image
    20247, -- 2309.04814 Speech2Lip: High-fidelity Speech to Lip Generation by Learning from a Short Vide
    20253, -- 2309.04907 Effective Real Image Editing with Accelerated Iterative Diffusion Inversion
    20263, -- 2309.05073 FreeMan: Towards Benchmarking 3D Human Pose Estimation under Real-World Conditio
    20274, -- 2309.05239 HAT: Hybrid Attention Transformer for Image Restoration
    20329, -- 2309.06323 SAMPLING: Scene-adaptive Hierarchical Multiplane Images Representation for Novel
    20358, -- 2309.06802 Dynamic NeRFs for Soccer Scenes
    20451, -- 2309.08113 MetaF2N: Blind Image Super-Resolution by Learning Efficient Model Adaptation fro
    20471, -- 2309.08416 Deformable Neural Radiance Fields using RGB and Event Cameras
    20490, -- 2309.08596 Robust e-NeRF: NeRF from Sparse & Noisy Events under Non-Uniform Motion
    20596, -- 2309.10279 360$^\circ$ Reconstruction From a Single Image Using Space Carved Outpainting
    20674, -- 2309.11258 TwinTex: Geometry-aware Texture Generation for Abstracted 3D Architectural Model
    20702, -- 2309.11661 Neural Image Compression Using Masked Sparse Visual Representation
    20892, -- 2309.14291 Tiled Multiplane Images for Practical 3D Photography
    20991, -- 2309.15889 High Perceptual Quality Wireless Image Delivery with Denoising Diffusion Models
    21046, -- 2309.16668 RealFill: Reference-Driven Generation for Authentic Image Completion
    21090, -- 2309.17261 Consistent123: One Image to Highly Consistent 3D Asset Using Case-Aware Diffusio
    21133, -- 2310.00224 Steered Diffusion: A Generalized Framework for Plug-and-Play Conditional Image S
    21500, -- 2310.04311 Distributed Deep Joint Source-Channel Coding with Decoder-Only Side Information
    21698, -- 2310.06275 High-Fidelity 3D Head Avatars Reconstruction through Spatially-Varying Expressio
    21726, -- 2310.06744 HiFi-123: Towards High-fidelity One Image to 3D Content Generation
    21895, -- 2310.08528 4D Gaussian Splatting for Real-Time Dynamic Scene Rendering
    21966, -- 2310.09285 SAIR: Learning Semantic-aware Implicit Representation
    21975, -- 2310.09484 Fast-DiM: Towards Fast Diffusion Morphs
    22034, -- 2310.10343 ConsistNet: Enforcing 3D Consistency for Multi-view Images Diffusion
    22056, -- 2310.10624 DynVideo-E: Harnessing Dynamic NeRF for Large-Scale Motion- and View-Change Huma
    22123, -- 2310.11448 4K4D: Real-Time 4D View Synthesis at 4K Resolution
    22314, -- 2310.13828 Nightshade: Prompt-Specific Poisoning Attacks on Text-to-Image Generative Models
    22400, -- 2310.14926 Reference-based Restoration of Digitized Analog Videotapes
    22406, -- 2310.15008 Wonder3D: Single Image to 3D using Cross-Domain Diffusion
    22504, -- 2310.16167 iNVS: Repurposing Diffusion Inpainters for Novel View Synthesis
    22569, -- 2310.16831 PERF: Panoramic Neural Radiance Field from a Single Panorama
    22738, -- 2310.19288 EDiffSR: An Efficient Diffusion Probabilistic Model for Remote Sensing Image Sup
    22826, -- 2310.20710 FPO++: Efficient Encoding and Rendering of Dynamic Neural Radiance Fields by Ana
    22932, -- 2311.01811 DiffDub: Person-generic Visual Dubbing Using Inpainting Renderer with Diffusion
    22988, -- 2311.03124 TAMPAR: Visual Tampering Detection for Parcel Logistics in Postal Supply Chains
    23061, -- 2311.04261 Restoration of Analog Videos Using Swin-UNet
    23062, -- 2311.04263 Perceptual Quality Improvement in Videoconferencing using Keyframes-based GAN
    23138, -- 2311.05607 Real-Time Neural Rasterization for Large Scenes
    23187, -- 2311.06443 CVTHead: One-shot Controllable Head Avatar with Vertex-feature Transformer
    23282, -- 2311.08007 Clearer Frames, Anytime: Resolving Velocity Ambiguity in Video Frame Interpolati
    23330, -- 2311.08581 Drivable 3D Gaussian Avatars
    23391, -- 2311.09221 Single-Image 3D Human Digitization with Shape-Guided Diffusion
    23496, -- 2311.10794 Text-to-Sticker: Style Tailoring Latent Diffusion Models for Human Expression
    23547, -- 2311.11700 GS-SLAM: Dense Visual SLAM with 3D Gaussian Splatting
    23559, -- 2311.11863 GP-NeRF: Generalized Perception NeRF for Context-Aware 3D Scene Understanding
    23571, -- 2311.12050 3D-GOI: 3D GAN Omni-Inversion for Multifaceted and Multi-object Editing
    23616, -- 2311.12775 SuGaR: Surface-Aligned Gaussian Splatting for Efficient 3D Mesh Reconstruction a
    23647, -- 2311.13134 Lightweight High-Speed Photography Built on Coded Exposure and Implicit Neural R
    23679, -- 2311.13602 Retrieval-Augmented Layout Transformer for Content-Aware Layout Generation
    23692, -- 2311.13831 Posterior Distillation Sampling
    23767, -- 2311.15260 NeuRAD: Neural Rendering for Autonomous Driving
    23778, -- 2311.15445 FLAIR: A Conditional Diffusion Framework with Applications to Face Video Restora
    23815, -- 2311.15908 Enhancing Perceptual Quality in Video Super-Resolution through Temporally-Consis
    23855, -- 2311.16473 GS-IR: 3D Gaussian Splatting for Inverse Rendering
    23859, -- 2311.16498 MagicAnimate: Temporally Consistent Human Image Animation using Diffusion Model
    23867, -- 2311.16518 SeeSR: Towards Semantics-Aware Real-World Image Super-Resolution
    23876, -- 2311.16737 Point'n Move: Interactive Scene Object Manipulation on Gaussian Splatting Radian
    23892, -- 2311.16933 SparseCtrl: Adding Sparse Controls to Text-to-Video Diffusion Models
    23894, -- 2311.16961 HumanRef: Single Image to 3D Human Generation via Reference-Guided Diffusion
    23911, -- 2311.17060 Material Palette: Extraction of Materials from a Single Image
    23922, -- 2311.17113 Human Gaussian Splatting: Real-time Rendering of Animatable Avatars
    23923, -- 2311.17117 Animate Anyone: Consistent and Controllable Image-to-Video Synthesis for Charact
    23959, -- 2311.17590 SyncTalk: The Devil is in the Synchronization for Talking Head Synthesis
    23963, -- 2311.17634 Erasing the Ephemeral: Joint Camera Refinement and Transient Object Removal for
    24035, -- 2311.18610 DiffCAD: Weakly-Supervised Probabilistic CAD Model Retrieval and Alignment from
    24036, -- 2311.18635 DiffusionAvatars: Deferred Diffusion for High-fidelity 3D Head Avatars
    24045, -- 2311.18729 Portrait4D: Learning One-Shot 4D Head Avatar Synthesis using Synthetic Data
    24059, -- 2311.18828 One-step Diffusion with Distribution Matching Distillation
    24061, -- 2311.18830 MotionEditor: Editing Video Motion via Content-Aware Diffusion
    24079, -- 2312.00109 Scaffold-GS: Structured 3D Gaussians for View-Adaptive Rendering
    24089, -- 2312.00210 DREAM: Diffusion Rectification and Estimation-Adaptive Models
    24150, -- 2312.00853 Motion-Guided Latent Diffusion for Temporally Consistent Real-world Video Super-
    24159, -- 2312.00944 Enhancing Diffusion Models with 3D Perspective Geometry Constraints
    24172, -- 2312.01196 Neural Parametric Gaussians for Monocular Non-Rigid Object Reconstruction
    24198, -- 2312.01671 Multimodality-guided Image Style Transfer using Cross-modal GAN Inversion
    24205, -- 2312.01725 StableVITON: Learning Semantic Correspondence with Latent Diffusion Model for Vi
    24223, -- 2312.02069 GaussianAvatars: Photorealistic Head Avatars with Rigged 3D Gaussians
    24231, -- 2312.02134 GaussianAvatar: Towards Realistic Human Avatar Modeling from a Single Video via
    24232, -- 2312.02135 Fast View Synthesis of Casual Videos with Soup-of-Planes
    24241, -- 2312.02155 GPS-Gaussian: Generalizable Pixel-wise 3D Gaussian Splatting for Real-time Human
    24250, -- 2312.02214 FlashAvatar: High-fidelity Head Avatar with Efficient Gaussian Embedding
    24265, -- 2312.02350 Instant Uncertainty Calibration of NeRFs Using a Meta-Calibrator
    24302, -- 2312.02902 HeadGaS: Real-Time Animatable Head Avatars via 3D Gaussian Splatting
    24314, -- 2312.02970 Alchemist: Parametric Control of Material Properties with Diffusion Models
    24318, -- 2312.02981 ReconFusion: 3D Reconstruction with Diffusion Priors
    24336, -- 2312.03160 HybridNeRF: Efficient Neural Rendering via Adaptive Volumetric Surfaces
    24360, -- 2312.03594 A Task is Worth One Word: Learning with Task Prompts for High-Quality Versatile
    24363, -- 2312.03611 DreamComposer: Controllable 3D Object Generation via Multi-View Conditions
    24376, -- 2312.03704 Relightable Gaussian Codec Avatars
    24400, -- 2312.03849 LEGO: Learning EGOcentric Action Frame Generation via Visual Instruction Tuning
    24431, -- 2312.04369 SingingHead: A Large-scale 4D Dataset for Singing Head Animation
    24433, -- 2312.04410 Smooth Diffusion: Crafting Smooth Latent Spaces in Diffusion Models
    24437, -- 2312.04461 PhotoMaker: Customizing Realistic Human Photos via Stacked ID Embedding
    24458, -- 2312.04551 Free3D: Consistent Novel View Synthesis without 3D Representation
    24463, -- 2312.04560 NeRFiller: Completing Scenes via Generative 3D Inpainting
    24472, -- 2312.04651 VOODOO 3D: Volumetric Portrait Disentanglement for One-Shot 3D Head Reenactment
    24486, -- 2312.04831 Towards Enhanced Image Inpainting: Mitigating Unwanted Object Insertion and Pres
    24489, -- 2312.04875 MVDD: Multi-View Depth Diffusion Models
    24490, -- 2312.04884 UDiffText: A Unified Framework for High-quality Text Synthesis in Arbitrary Imag
    24498, -- 2312.04965 Inversion-Free Image Editing with Natural Language
    24529, -- 2312.05390 NoiseCLR: A Contrastive Learning Approach for Unsupervised Discovery of Interpre
    24534, -- 2312.05476 Exploring the Naturalness of AI-Generated Images
    24547, -- 2312.05616 Iterative Token Evaluation and Refinement for Real-World Super-Resolution
    24558, -- 2312.05748 IL-NeRF: Incremental Learning for Neural Radiance Fields with Camera Pose Alignm
    24567, -- 2312.05941 ASH: Animatable Gaussian Splats for Efficient and Photoreal Human Rendering
    24601, -- 2312.06573 ControlNet-XS: Rethinking the Control of Text-to-Image Diffusion Models as Feedb
    24609, -- 2312.06640 Upscale-A-Video: Temporal-Consistent Diffusion Model for Real-World Video Super-
    24620, -- 2312.06662 Photorealistic Video Generation with Diffusion Models
    24645, -- 2312.06886 Relightful Harmonization: Lighting-aware Portrait Background Replacement
    24683, -- 2312.07409 DiffMorpher: Unleashing the Capability of Diffusion Models for Image Morphing
    24688, -- 2312.07485 MinD-3D: Reconstruct High-quality 3D objects in Human Brain
    24696, -- 2312.07536 FreeControl: Training-Free Spatial Control of Any Text-to-Image Diffusion Model
    24725, -- 2312.08056 Knowledge-Aware Artifact Image Synthesis with LLM-Enhanced Prompting and Multi-S
    24727, -- 2312.08136 ProNeRF: Learning Efficient Projection-Aware Ray Sampling for Fine-Grained Impli
    24748, -- 2312.08568 NViST: In the Wild New View Synthesis from a Single Image with Transformers
    24773, -- 2312.08882 Neural Video Fields Editing
    24777, -- 2312.08892 VaLID: Variable-Length Input Diffusion for Novel View Synthesis
    24785, -- 2312.08962 Depicting Beyond Scores: Advancing Image Quality Assessment through Multi-modal
    24786, -- 2312.09008 Style Injection in Diffusion: A Training-free Approach for Adapting Large-scale
    24797, -- 2312.09147 Triplane Meets Gaussian Splatting: Fast and Generalizable Single-View 3D Reconst
    24812, -- 2312.09249 ZeroRF: Fast Sparse View 360° Reconstruction with Zero Pretraining
    24866, -- 2312.10191 Tell Me What You See: Text-Guided Real-World Image Denoising
    24932, -- 2312.11458 GauFRe: Gaussian Deformation Fields for Real-time Dynamic Novel View Synthesis
    24933, -- 2312.11459 VolumeDiffusion: Flexible Text-to-3D Generation with Efficient Volumetric Encode
    24948, -- 2312.11535 Customize-It-3D: High-Quality 3D Creation from A Single Image Using Subject-Spec
    24949, -- 2312.11537 FastSR-NeRF: Improving NeRF Efficiency on Consumer Devices with A Simple Super-R
    24954, -- 2312.11595 SPIRE: Semantic Prompt-Driven Image Restoration
    24976, -- 2312.12142 FontDiffuser: One-Shot Font Generation via Denoising Diffusion with Multi-Scale
    25034, -- 2312.12877 Relightable and Animatable Neural Avatars from Videos
    25037, -- 2312.13016 DiffPortrait3D: Controllable Diffusion for Zero-Shot Portrait View Synthesis
    25060, -- 2312.13314 Unlocking Pre-trained Image Backbones for Semantic Image Synthesis
    25090, -- 2312.13980 Carve3D: Improving Multi-view Reconstruction Consistency for Diffusion Models wi
    25125, -- 2312.14389 StyleRetoucher: Generalized Portrait Image Retouching with GAN Priors
    25145, -- 2312.14937 SC-GS: Sparse-Controlled Gaussian Splatting for Editable Dynamic Scenes
    25195, -- 2312.15736 Towards Real-World Blind Face Restoration with Generative Diffusion Prior
    25201, -- 2312.15861 Towards Squeezing-Averse Virtual Try-On via Sequential Deformation
    25211, -- 2312.15980 HarmonyView: Harmonizing Consistency and Diversity in One-Image-to-3D
    25242, -- 2312.16457 City-on-Web: Real-time Neural Rendering of Large-scale Scenes on the Web
    25255, -- 2312.16794 ZONE: Zero-Shot Instruction-Guided Local Editing
    25256, -- 2312.16812 Spacetime Gaussian Feature Splatting for Real-Time Dynamic View Synthesis
    25384, -- 2401.00877 Improving the Stability and Efficiency of Diffusion Models for Content Consisten
    25415, -- 2401.01339 Street Gaussians: Modeling Dynamic Urban Scenes with Gaussian Splatting
    25448, -- 2401.01862 A Vision Check-up for Language Models
    25545, -- 2401.03395 Deep Learning-based Image and Video Inpainting: A Survey
    25567, -- 2401.03788 Low-light Image Enhancement via CLIP-Fourier Guided Wavelet Diffusion
    25574, -- 2401.03890 A Survey on 3D Gaussian Splatting
    25631, -- 2401.04728 Morphable Diffusion: 3D-Consistent Diffusion for Single-image Avatar Creation
    25654, -- 2401.05293 Score Distillation Sampling with Learned Manifold Corrective
    25658, -- 2401.05334 URHand: Universal Relightable Hands
    25707, -- 2401.06003 TRIPS: Trilinear Point Splatting for Real-Time Radiance Field Rendering
    25823, -- 2401.07709 Towards Efficient Diffusion-Based Image Editing with Instant Attention Masks
    25911, -- 2401.08937 ICON: Incremental CONfidence for Joint Pose and Radiance Field Optimization
    25944, -- 2401.09386 Tri$^{2}$-plane: Thinking Head Avatar via Feature Pyramid
    25963, -- 2401.09624 MITS-GAN: Safeguarding Medical Imaging from Tampering with Generative Adversaria
    26000, -- 2401.10171 SHINOBI: Shape and Illumination using Neural Object Decomposition via BRDF Optim
    26035, -- 2401.10526 On mitigating stability-plasticity dilemma in CLIP-guided image morphing via geo
    26052, -- 2401.10786 Sat2Scene: 3D Urban Scene Generation from Satellite Images with Diffusion
    26069, -- 2401.11078 UltrAvatar: A Realistic Animatable 3D Avatar Diffusion Model with Authenticity G
    26081, -- 2401.11239 Product-Level Try-on: Characteristics-preserving Try-on with Realistic Clothes S
    26092, -- 2401.11485 ColorVideoVDP: A visual difference predictor for image, video and display distor
    26305, -- 2401.14398 pix2gestalt: Amodal Segmentation by Synthesizing Wholes
    26405, -- 2401.15975 StableIdentity: Inserting Anybody into Anywhere at First Sight
    26496, -- 2401.17258 You Only Need One Step: Fast Super-Resolution with Stable Diffusion via Scale Di
    26595, -- 2402.00827 GaussianStyle: Gaussian Head Avatar via StyleGAN
    26908, -- 2402.03908 EscherNet: A Generative Model for Scalable View Synthesis
    26966, -- 2402.04584 Troublemaker Learning for Low-Light Image Enhancement
    27005, -- 2402.05054 LGM: Large Multi-View Gaussian Model for High-Resolution 3D Content Creation
    27023, -- 2402.05235 SPAD : Spatially Aware Multiview Diffusers
    27162, -- 2402.07116 Q-Bench+: A Benchmark for Multi-modal Foundation Models on Low-level Vision from
    27325, -- 2402.09368 Magic-Me: Identity-Specific Video Customized Diffusion
    27389, -- 2402.10259 GaussianObject: High-Quality 3D Object Reconstruction from Four Views with Gauss
    27563, -- 2402.11929 DiLightNet: Fine-grained Lighting Control for Diffusion-based Image Generation
    27636, -- 2402.12712 MVDiffusion++: A Dense High-resolution Multi-view Diffusion Model for Single or
    27698, -- 2402.13255 How NeRFs and 3D Gaussian Splatting are Reshaping SLAM: a Survey
    27779, -- 2402.14253 MVD$^2$: Efficient Multiview 3D Reconstruction for Multiview Diffusion
    27832, -- 2402.14780 Customize-A-Video: One-Shot Motion Customization of Text-to-Video Diffusion Mode
    27981, -- 2402.16641 Towards Open-ended Visual Quality Comparison
    28037, -- 2402.17214 CharacterGen: Efficient 3D Character Generation from Single Images with Multi-Vi
    28067, -- 2402.17525 Diffusion Model-Based Image Editing: A Survey
    28118, -- 2402.18078 Coarse-to-Fine Latent Diffusion for Pose-Guided Person Image Synthesis
    28176, -- 2402.18842 ViewFusion: Towards Multi-View Consistency via Interpolated Denoising
    28180, -- 2402.18969 OHTA: One-shot Hand Avatar via Data-driven Implicit Priors
    28216, -- 2402.19479 Panda-70M: Captioning 70M Videos with Multiple Cross-Modality Teachers
    28217, -- 2402.19481 DistriFusion: Distributed Parallel Inference for High-Resolution Diffusion Model
    28239, -- 2403.00437 LoMOE: Localized Multi-Object Editing via Multi-Diffusion
    28318, -- 2403.01422 MovieLLM: Enhancing Long Video Understanding with AI-Generated Movies
    28345, -- 2403.01807 ViewDiff: 3D-Consistent Image Generation with Text-to-Image Models
    28554, -- 2403.04993 PromptIQA: Boosting the Performance and Generalization for No-Reference Image Qu
    28561, -- 2403.05034 CRM: Single Image to 3D Textured Mesh with Convolutional Reconstruction Model
    28562, -- 2403.05049 XPSR: Cross-modal Priors for Diffusion-based Image Super-Resolution
    28563, -- 2403.05053 PrimeComposer: Faster Progressively Combined Diffusion for Image Composition wit
    28566, -- 2403.05087 SplattingAvatar: Realistic Real-Time Human Avatars with Mesh-Embedded Gaussian S
    28570, -- 2403.05139 Improving Diffusion Models for Authentic Virtual Try-on in the Wild
    28622, -- 2403.06092 Is Vanilla MLP in Neural Radiance Field Enough for Few-shot View Synthesis?
    28640, -- 2403.06351 Put Myself in Your Shoes: Lifting the Egocentric Perspective from Exocentric Vid
    28644, -- 2403.06381 Enhancing Semantic Fidelity in Text-to-Image Synthesis: Attention Regulation in
    28661, -- 2403.06738 V3D: Video Diffusion Models are Effective 3D Generators
    28688, -- 2403.06976 BrushNet: A Plug-and-Play Image Inpainting Model with Decomposed Dual-Branch Dif
    28706, -- 2403.07319 Efficient Diffusion Model for Image Restoration by Residual Shifting
    28711, -- 2403.07371 Time-Efficient and Identity-Consistent Virtual Try-On Using A Variant of Altered
    28772, -- 2403.08266 Sketch2Manga: Shaded Manga Screening from Sketch with Diffusion Models
    28786, -- 2403.08460 Towards Dense and Accurate Radar Perception Via Efficient Cross-Modal Diffusion
    28857, -- 2403.09419 RoDUS: Robust Decomposition of Static and Dynamic Elements in Urban Scenes
    28859, -- 2403.09468 Eta Inversion: Designing an Optimal Eta Function for Diffusion-based Real Image
    28881, -- 2403.09638 SCP-Diff: Spatial-Categorical Joint Prior for Diffusion Based Semantic Image Syn
    28914, -- 2403.10255 Arbitrary-Scale Image Generation and Upsampling using Latent Diffusion Model and
    28958, -- 2403.10854 A Comprehensive Study of Multimodal Large Language Models for Image Quality Asse
    28961, -- 2403.10911 Efficient Diffusion-Driven Corruption Editor for Test-Time Adaptation
    28975, -- 2403.11056 Analytic-Splatting: Anti-Aliased 3D Gaussian Splatting via Analytic Integration
    29003, -- 2403.11415 DreamSampler: Unifying Diffusion Sampling and Score Distillation for Image Manip
    29008, -- 2403.11447 Motion-aware 3D Gaussian Splatting for Efficient Dynamic Scene Reconstruction
    29019, -- 2403.11589 UV Gaussians: Joint Learning of Mesh Deformation and Gaussian Textures for Human
    29024, -- 2403.11641 Arc2Face: A Foundation Model for ID-Consistent Human Faces
    29036, -- 2403.11791 PAON: A New Neuron Model using Padé Approximants
    29056, -- 2403.12008 SV3D: Novel Multi-view Synthesis and 3D Generation from a Single Image using Lat
    29062, -- 2403.12019 LN3Diff: Scalable Latent Neural Fields Diffusion for Speedy 3D Generation
    29070, -- 2403.12034 VFusion3D: Learning Scalable 3D Generative Models from Video Diffusion Models
    29109, -- 2403.12658 Tuning-Free Image Customization with Image and Text Guidance
    29114, -- 2403.12722 HUGS: Holistic Urban 3D Scene Understanding via Gaussian Splatting
    29130, -- 2403.12906 TexDreamer: Towards Zero-Shot High-Fidelity 3D Human Texture Generation
    29133, -- 2403.12933 Zero-Reference Low-Light Enhancement via Physical Quadruple Priors
    29140, -- 2403.12961 TexTile: A Differentiable Metric for Texture Tileability
    29197, -- 2403.13570 Portrait4D-v2: Pseudo Multi-View Data Creates Better 4D Head Synthesizer
    29205, -- 2403.13745 Be-Your-Outpainter: Mastering Video Outpainting through Input-Specific Adaptatio
    29238, -- 2403.14186 StyleCineGAN: Landscape Cinemagraph Generation using a Pre-trained StyleGAN
    29270, -- 2403.14554 Gaussian Frosting: Editable Complex Radiance Fields with Real-Time Rendering
    29275, -- 2403.14602 ReNoise: Real Image Inversion Through Iterative Noising
    29285, -- 2403.14627 MVSplat: Efficient 3D Gaussian Splatting from Sparse Multi-View Images
    29299, -- 2403.14781 Champ: Controllable and Consistent Human Image Animation with 3D Parametric Guid
    29319, -- 2403.15124 EndoGSLAM: Real-Time Dense Reconstruction and Tracking in Endoscopic Surgeries u
    29321, -- 2403.15139 Deep Generative Model based Rate-Distortion for Image Downscaling Assessment
    29324, -- 2403.15245 Reasoning-Enhanced Object-Centric Learning for Videos
    29338, -- 2403.15382 DragAPart: Learning a Part-Level Motion Prior for Articulated Objects
    29364, -- 2403.15704 Gaussian in the Wild: 3D Gaussian Splatting for Unconstrained Image Collections
    29388, -- 2403.16080 PKU-DyMVHumans: A Multi-View Video Benchmark for High-Fidelity Dynamic Human Mod
    29396, -- 2403.16292 latentSplat: Autoencoding Variational Gaussians for Fast Generalizable 3D Recons
    29446, -- 2403.17006 Invertible Diffusion Models for Compressed Sensing
    29451, -- 2403.17103 Animal Avatars: Reconstructing Animatable 3D Animals from Casual Videos
    29463, -- 2403.17377 Self-Rectifying Diffusion Sampling with Perturbed-Attention Guidance
    29568, -- 2403.18816 Garment3DGen: 3D Garment Stylization and Texture Generation
    29569, -- 2403.18818 ObjectDrop: Bootstrapping Counterfactuals for Photorealistic Object Removal and
    29570, -- 2403.18820 MetaCap: Meta-learning Priors from Multi-View Imagery for Sparse-view Human Perf
    29592, -- 2403.19163 D'OH: Decoder-Only Random Hypernetworks for Implicit Neural Representations
    29627, -- 2403.19645 GANTASTIC: GAN-based Transfer of Interpretable Directions for Disentangled Image
    29689, -- 2404.00301 Monocular Identity-Conditioned Facial Reflectance Reconstruction
    29738, -- 2404.00777 Privacy-preserving Optics for Enhancing Protection in Face De-identification
    29770, -- 2404.01133 CityGaussian: Real-time High-quality Large-Scale Scene Rendering with Gaussians
    29774, -- 2404.01203 Video Interpolation with Diffusion Models
    29788, -- 2404.01291 Evaluating Text-to-Visual Generation with Image-to-Text Generation
    29813, -- 2404.01543 Efficient 3D Implicit Head Avatar with Mesh-anchored Hash Table Blendshapes
    29819, -- 2404.01647 EDTalk: Efficient Disentanglement for Emotional Talking Head Synthesis
    29840, -- 2404.01889 RAVE: Residual Vector Embedding for CLIP-Guided Backlit Image Enhancement
    29876, -- 2404.02514 Freditor: High-Fidelity and Transferable NeRF Editing by Frequency Decomposition
    29955, -- 2404.03620 LCM-Lookahead for Encoder-based Text-to-Image Personalization
    29964, -- 2404.03656 MVD-Fusion: Single-view 3D via Depth-consistent Multi-view Generation
    29972, -- 2404.03736 SC4D: Sparse-Controlled Video-to-4D Generation and Motion Transfer
    29987, -- 2404.04037 InstructHumans: Editing Animated 3D Human Textures with Instructions
    30011, -- 2404.04421 PhysAvatar: Learning the Physics of Dressed 3D Avatars from Visual Observations
    30021, -- 2404.04526 DATENeRF: Depth-Aware Text-based Editing of NeRFs
    30065, -- 2404.05331 Mask-ControlNet: Higher-Quality Image Generation with An Additional Mask Prompt
    30117, -- 2404.06025 Greedy-DiM: Greedy Algorithms for Unreasonably Effective Face Morphs
    30119, -- 2404.06091 Hash3D: Training-free Acceleration for 3D Generation
    30120, -- 2404.06109 Revising Densification in Gaussian Splatting
    30131, -- 2404.06251 ColorMNet: A Memory-based Deep Spatial-Temporal Feature Propagation Network for
    30145, -- 2404.06425 ZeST: Zero-Shot Material Transfer from a Single Image
    30153, -- 2404.06493 Flying with Photons: Rendering Novel Views of Propagating Light
    30162, -- 2404.06666 SafeGen: Mitigating Sexually Explicit Content Generation in Text-to-Image Models
    30194, -- 2404.07199 RealmDreamer: Text-Driven 3D Scene Generation with Inpainting and Depth Diffusio
    30204, -- 2404.07336 PEAVS: Perceptual Evaluation of Audio-Visual Synchrony Grounded in Viewers' Opin
    30256, -- 2404.07991 GoMAvatar: Efficient Animatable Human Modeling from Monocular Video Using Gaussi
    30268, -- 2404.08252 MonoPatchNeRF: Improving Neural Radiance Fields with Patch-based Monocular Guida
    30276, -- 2404.08341 Counterfactual Explanations for Face Forgery Detection via Adversarial Removal o
    30344, -- 2404.09458 CompGS: Efficient 3D Scene Representation via Compressed Gaussian Splatting
    30380, -- 2404.09833 Video2Game: Real-time, Interactive, Realistic and Browser-Compatible Environment
    30392, -- 2404.09995 Taming Latent Diffusion Model for Neural Radiance Field Inpainting
    30411, -- 2404.10312 OmniSSR: Zero-shot Omnidirectional Image Super-Resolution using Stable Diffusion
    30453, -- 2404.11104 Object Remover Performance Evaluation Methods using Class-wise Object Removal Im
    30475, -- 2404.11565 MoA: Mixture-of-Attention for Subject-Context Disentanglement in Personalized Im
    30481, -- 2404.11614 Dynamic Typography: Bringing Text to Life via Video Diffusion Prior
    30491, -- 2404.11889 Multi-view X-ray Image Synthesis with Multiple Domain Disentanglement from CT Sc
    30543, -- 2404.12388 VideoGigaGAN: Towards Detail-rich Video Super-Resolution
    30552, -- 2404.12488 Global Counterfactual Directions
    30621, -- 2404.13679 GScream: Learning 3D Geometry and Feature Consistent Gaussian Splatting for Obje
    30710, -- 2404.15264 TalkingGaussian: Structure-Persistent 3D Talking Head Synthesis via Gaussian Spl
    30729, -- 2404.15677 CharacterFactory: Sampling Consistent Characters with GANs for Diffusion Models
    30832, -- 2404.17571 Tunnel Try-on: Excavating Spatial-temporal Tunnels for High-quality Virtual Try-
    30911, -- 2404.19149 SAGS: Structure-Aware 3D Gaussian Splatting
    30924, -- 2404.19398 3D Gaussian Blendshapes for Head Avatar Animation
    30938, -- 2404.19702 GS-LRM: Large Reconstruction Model for 3D Gaussian Splatting
    30947, -- 2404.19760 Lightplane: Highly-Scalable Components for Neural 3D Fields
    30961, -- 2405.00313 Streamlining Image Editing with Layered Diffusion Brushes
    31073, -- 2405.02962 VectorPainter: Advanced Stylized Vector Graphics Synthesis Using Stroke-Style Pr
    31076, -- 2405.03121 AniTalker: Animate Vivid and Diverse Talking Faces through Identity-Decoupled Fa
    31163, -- 2405.05588 Model Inversion Robustness: Can Transfer Learning Help?
    31165, -- 2405.05663 RPBG: Towards Robust Neural Point-based Graphics in the Wild
    31178, -- 2405.05953 Frame Interpolation with Consecutive Brownian Bridge Diffusion
    31221, -- 2405.07319 LayGA: Layered Gaussian Avatars for Animatable Clothing Transfer
    31256, -- 2405.07913 CTRLorALTer: Conditional LoRAdapter for Efficient 0-Shot Control & Altering of T
    31360, -- 2405.10272 Faces that Speak: Jointly Synthesising Talking Face and Speech from Text
    31481, -- 2405.12970 Face Adapter for Pre-Trained Diffusion Models with Fine-Grained ID and Attribute
    31510, -- 2405.13389 HR-INR: Continuous Space-Time Video Super-Resolution via Event Camera
    31587, -- 2405.14475 MagicDrive3D: Controllable 3D Generation for Any-View Rendering in Street Scenes
    31607, -- 2405.14701 DreamText: High Fidelity Scene Text Synthesis
    31628, -- 2405.14847 Neural Directional Encoding for Efficient and Accurate View-Dependent Appearance
    31638, -- 2405.14871 NeRF-Casting: Improved View-Dependent Appearance with Consistent Reflections
    31716, -- 2405.15734 LM4LV: A Frozen Large Language Model for Low-level Vision Tasks
    31801, -- 2405.16817 Controlling Rate, Distortion, and Realism: Towards a Single Comprehensive Neural
    31894, -- 2405.17933 ToonCrafter: Generative Cartoon Interpolation
    31946, -- 2405.18416 3D StreetUnveiler with Semantic-Aware 2DGS
    31950, -- 2405.18426 GFlow: Recovering 4D World from Monocular Video
    31969, -- 2405.18715 NeRF On-the-go: Exploiting Uncertainty for Distractor-free NeRFs in the Wild
    31975, -- 2405.18842 Descriptive Image Quality Assessment in the Wild
    32008, -- 2405.19331 NPGA: Neural Parametric Gaussian Avatars
    32075, -- 2405.20222 MOFA-Video: Controllable Image Animation via Generative Motion Field Adaptions i
    32076, -- 2405.20224 EvaGaussians: Event Stream Assisted Gaussian Splatting from Blurry Images
    32080, -- 2405.20271 ETHER: Efficient Finetuning of Large-Scale Models with Hyperplane Reflections
    32093, -- 2405.20327 GECO: Generative Image-to-3D within a SECOnd
    32214, -- 2406.01020 ATTIQA: Generalizable Image Quality Feature Extractor using Attribute-aware Pret
    32268, -- 2406.01900 Follow-Your-Emoji: Fine-Controllable and Expressive Freestyle Portrait Animation
    32603, -- 2406.06133 ExtraNeRF: Visibility-Aware View Extrapolation of Neural Radiance Fields with Di
    32811, -- 2406.08475 Human-3Diffusion: Realistic Avatar Creation via Explicit 3D Consistent Diffusion
    32885, -- 2406.09356 CMC-Bench: Towards a New Paradigm of Visual Signal Compression
    33004, -- 2406.10601 The Devil is in the Details: StyleFeatureEditor for Detail-Rich StyleGAN Inversi
    33161, -- 2406.11819 MegaScenes: Scene-Level View Synthesis at Scale
    33300, -- 2406.13099 Sampling 3D Gaussian Scenes in Seconds with Latent Diffusion Models
    33448, -- 2406.14806 Relighting Scenes with Object Insertions in Neural Radiance Fields
    33486, -- 2406.15331 Masked Extended Attention for Zero-Shot Virtual Try-On In The Wild
    33667, -- 2406.17636 Aligning Diffusion Models with Noise-Conditioned Perception
    33751, -- 2406.18544 GS-ROR$^2$: Bidirectional-guided 3DGS and SDF for Reflective Object Relighting a
    33983, -- 2407.01521 Improving Diffusion Inverse Problem Solving with Decoupled Noise Annealing
    33994, -- 2407.01790 Label-free Neural Semantic Image Synthesis
    33997, -- 2407.01866 Image-GS: Content-Adaptive Image Representation via 2D Gaussians
    34147, -- 2407.03857 PFGS: High Fidelity Point Cloud Rendering via Feature Splatting
    34253, -- 2407.05324 PICA: Physics-Integrated Clothed Avatar
    34270, -- 2407.05530 This&That: Language-Gesture Controlled Video Generation for Robot Planning
    34278, -- 2407.05577 Audio-driven High-resolution Seamless Talking Head Video Editing via StyleGAN
    34342, -- 2407.06315 Shedding More Light on Robust Classifiers under the lens of Energy-based Models
    34347, -- 2407.06397 RRM: Relightable assets using Radiance guided Material extraction
    34377, -- 2407.06938 RodinHD: High-Fidelity 3D Avatar Generation with Diffusion Models
    34405, -- 2407.07284 MIGS: Multi-Identity Gaussian Splatting via Tensor Decomposition
    34457, -- 2407.08061 Geospecific View Generation -- Geometry-Context Aware High-resolution Ground Vie
    34482, -- 2407.08414 MeshAvatar: Learning High-quality Triangular Human Avatars from Multi-view Video
    34484, -- 2407.08418 PredBench: Benchmarking Spatio-Temporal Prediction across Diverse Disciplines
    34528, -- 2407.08939 LightenDiffusion: Unsupervised Low-Light Image Enhancement with Latent-Retinex D
    34536, -- 2407.09012 TCAN: Animating Human Images with Temporally Consistent Pose Guidance using Diff
    34558, -- 2407.09299 PID: Physics-Informed Diffusion Model for Infrared Image Generation
    34579, -- 2407.09549 How Stable is Stable Diffusion under Recursive InPainting (RIP)?
    34584, -- 2407.09679 Physics-Informed Learning of Characteristic Trajectories for Smoke Reconstructio
    34604, -- 2407.09892 NamedCurves: Learned Image Enhancement via Color Naming
    34633, -- 2407.10330 Tree-D Fusion: Simulation-Ready Tree Dataset from Single Images with Diffusion P
    34646, -- 2407.10625 WildVidFit: Video Virtual Try-On in the Wild via Image-Based Controlled Diffusio
    34649, -- 2407.10636 Temporal Residual Guided Diffusion Framework for Event-Driven Video Reconstructi
    34657, -- 2407.10707 Interactive Rendering of Relightable and Animatable Gaussian Avatars
    34719, -- 2407.11294 COHO: Context-Sensitive City-Scale Hierarchical Urban Layout Generation
    34739, -- 2407.11555 Self-Guided Generation of Minority Samples Using Diffusion Models
    34809, -- 2407.12383 Reliable and Efficient Concept Erasure of Text-to-Image Diffusion Models
    34835, -- 2407.12718 SlimFlow: Training Smaller One-Step Diffusion Models with Rectified Flow
    34840, -- 2407.12777 Generalizable Human Gaussians for Sparse View Synthesis
    34868, -- 2407.12939 GenRC: Generative 3D Room Completion from Sparse Image Collections
    34884, -- 2407.13132 LSD3K: A Benchmark for Smoke Removal from Laparoscopic Surgery Images
    34931, -- 2407.13759 Streetscapes: Large-scale Consistent Street View Generation Using Autoregressive
    34945, -- 2407.13987 RealViformer: Investigating Attention for Real-World Video Super-Resolution
    35015, -- 2407.15187 HoloDreamer: Holistic 3D Panoramic World Generation from Text Descriptions
    35042, -- 2407.15446 Text2Place: Affordance-aware Text Guided Human Placement
    35075, -- 2407.15842 DiffArtist: Towards Structure and Appearance Controllable Image Stylization
    35077, -- 2407.15848 BoostMVSNeRFs: Boosting MVS-based NeRFs to Generalizable View Synthesis in Large
    35085, -- 2407.16125 Diffusion Prior-Based Amortized Variational Inference for Noisy Inverse Problems
    35188, -- 2407.17850 FlexiEdit: Frequency-Aware Latent Refinement for Enhanced Non-Rigid Editing
    35213, -- 2407.18247 RegionDrag: Fast Region-Based Image Editing with Diffusion Models
    35272, -- 2407.19542 UniVoxel: Fast Inverse Rendering by Unified Voxelization of Scene Representation
    35352, -- 2407.21032 Safeguard Text-to-Image Diffusion Models with Human Feedback Inversion
    35353, -- 2407.21047 PAV: Personalized Head Avatar from Unstructured Video Collection
    35383, -- 2407.21686 Expressive Whole-Body 3D Gaussian Avatar
    35419, -- 2408.00296 Head360: Learning a Parametric 3D Full-Head for Free-View Synthesis in 360°
    35420, -- 2408.00297 EmoTalk3D: High-Fidelity Free-View Synthesis of Emotional 3D Talking Head
    35437, -- 2408.00653 SF3D: Stable Fast 3D Mesh Reconstruction with UV-unwrapping and Illumination Dis
    35448, -- 2408.00735 TurboEdit: Text-Based Image Editing Using Few-Step Diffusion Models
    35627, -- 2408.03637 TALE: Training-free Cross-domain Image Composition via Adaptive Latent Manipulat
    35639, -- 2408.03923 Fast Sprite Decomposition from Animated Graphics
    35654, -- 2408.04224 Cross-View Meets Diffusion: Aerial Image Synthesis with Geometry and Text Guidan
    35674, -- 2408.04631 Puppet-Master: Scaling Interactive Video Generation as a Motion Prior for Part-L
    35719, -- 2408.05492 ZePo: Zero-Shot Portrait Stylization with Faster Sampling
    35733, -- 2408.05868 LaWa: Using Latent Space for In-Generation Image Watermarking
    35784, -- 2408.06697 SlotLifter: Slot-guided Feature Lifting for Learning Object-centric Radiance Fie
    35834, -- 2408.07476 One Step Diffusion-based Super-Resolution with Time-Aware Distillation
    35839, -- 2408.07541 DifuzCam: Replacing Camera Lens with a Mask and a Diffusion Model
    35871, -- 2408.08206 WaterSplatting: Fast Underwater 3D Scene Reconstruction Using Gaussian Splatting
    35877, -- 2408.08332 TurboEdit: Instant text-based image editing
    35939, -- 2408.09348 Hyperstroke: A Novel High-quality Stroke Representation for Assistive Artistic D
    35940, -- 2408.09384 FD2Talk: Towards Generalized Talking Head Generation with Facial Decoupled Diffu
    35957, -- 2408.09702 Photorealistic Object Insertion with Diffusion-Guided Inverse Rendering
    35976, -- 2408.10154 LoopSplat: Loop Closure by Registering 3D Gaussian Splats
    35999, -- 2408.10588 DEGAS: Detailed Expressions on Full-Body Gaussian Avatars
    36029, -- 2408.10935 Large Point-to-Gaussian Model for Image-to-3D Generation
    36169, -- 2408.12894 FLoD: Integrating Flexible Level of Detail into 3D Gaussian Splatting for Custom
    36181, -- 2408.13252 LayerPano3D: Layered 3D Panorama for Hyper-Immersive Scene Generation
    36190, -- 2408.13413 TVG: A Training-free Transition Video Generation Method with Diffusion Models
    36312, -- 2408.15660 Merging and Splitting Diffusion Paths for Semantically Coherent Panoramas
    36392, -- 2408.16767 ReconX: Reconstruct Any Scene from Sparse Views with Video Diffusion Model
    36498, -- 2409.01322 Guide-and-Rescale: Self-Guidance Mechanism for Effective Tuning-Free Real Image
    36573, -- 2409.02657 PoseTalk: Text-and-Audio-based Pose Control and Motion Refinement for One-Shot T
    36574, -- 2409.02683 Rethinking HTG Evaluation: Bridging Generation and Recognition
    36617, -- 2409.03487 ScreenMark: Watermarking Arbitrary Visual Content on Screen
    36647, -- 2409.04196 GST: Precise 3D Human Body from a Single Image with Gaussian Splatting Transform
    36690, -- 2409.05379 PersonaTalk: Bring Attention to Your Persona in Visual Dubbing
    36717, -- 2409.06065 DiffusionPen: Towards Controlling the Style of Handwritten Text Generation
    36727, -- 2409.06355 DiffQRCoder: Diffusion-based Aesthetic QR Code Generation with Scanning Robustne
    36731, -- 2409.06481 NeIn: Telling What You Don't Want
    36784, -- 2409.07452 Hi3D: Pursuing High-Resolution Image-to-3D Generation with Video Diffusion Model
    36806, -- 2409.08077 Diffusion-Based Image-to-Image Translation by Noise Correction via Prompt Interp
    36808, -- 2409.08189 Gaussian Garments: Reconstructing Simulation-Ready Clothing with Photorealistic
    36817, -- 2409.08258 Improving Virtual Try-On with Garment-focused Diffusion Models
    36819, -- 2409.08270 FlashSplat: 2D to 3D Gaussian Splatting Segmentation Solved Optimally
    36853, -- 2409.08857 InstantDrag: Improving Interactivity in Drag-based Image Editing
    36856, -- 2409.08947 A Diffusion Approach to Radiance Field Relighting using Multi-Illumination Synth
    36901, -- 2409.09593 One-Shot Learning for Pose-Guided Person Image Synthesis in the Wild
    36902, -- 2409.09610 TextureDiffusion: Target Prompt Disentangled Editing for Various Texture Transfe
    36927, -- 2409.10141 PSHuman: Photorealistic Single-view Human Reconstruction using Cross-Scale Diffu
    36995, -- 2409.11307 GS-Net: Generalizable Plug-and-Play 3D Gaussian Splatting Module
    36997, -- 2409.11315 MinD-3D++: Advancing fMRI-Based 3D Reconstruction with High-Quality Textured Mes
    37057, -- 2409.12193 Vista3D: Unravel the 3D Darkside of a Single Image
    37087, -- 2409.12892 3DGS-LM: Faster Gaussian-Splatting Optimization with Levenberg-Marquardt
    37128, -- 2409.13591 Portrait Video Editing Empowered by Multimodal Generative Priors
    37189, -- 2409.14677 Reflecting Reality: Enabling Diffusion Models to Produce Faithful Mirror Reflect
    37212, -- 2409.15041 AIM 2024 Sparse Neural Rendering Challenge: Dataset and Benchmark
    37224, -- 2409.15269 ReLoo: Reconstructing Humans Dressed in Loose Garments from Monocular Video in t
    37277, -- 2409.16160 MIMO: Controllable Character Video Synthesis with Spatial Decomposed Modeling
    37305, -- 2409.16666 TalkinNeRF: Animatable Neural Fields for Full-Body Talking Humans
    37310, -- 2409.16706 Pix2Next: Leveraging Vision Foundation Models for RGB to NIR Image Translation
    37321, -- 2409.16949 DALDA: Data Augmentation Leveraging Diffusion Model and LLM with Adaptive Guidan
    37348, -- 2409.17439 Rejection Sampling IMLE: Designing Priors for Better Few-Shot Image Synthesis
    37384, -- 2409.17988 Deblur e-NeRF: NeRF from Motion-Blurred Events under High-speed or Low-light Con
    37437, -- 2409.18869 Emu3: Next-Token Prediction is All You Need
    37470, -- 2409.19405 G3R: Gradient Guided Generalizable Reconstruction
    37496, -- 2409.19702 RNG: Relightable Neural Gaussians
    37521, -- 2409.19946 Illustrious: an Open Advanced Illustration Model
    37534, -- 2409.20140 RISE-SDF: a Relightable Information-Shared Signed Distance Field for Glossy Obje
    37535, -- 2409.20175 Ensemble Kalman Diffusion Guidance: A Derivative-free Method for Inverse Problem
    37556, -- 2409.20556 Inverse Painting: Reconstructing The Painting Process
    37666, -- 2410.01591 Imaging foundation model for universal enhancement of non-ideal measurement CT
    37767, -- 2410.02491 Lightweight Diffusion Models for Resource-Constrained Semantic Communication
    37779, -- 2410.02640 RDEIC: Accelerating Diffusion-Based Extreme Image Compression with Relay Residua
    38044, -- 2410.05525 Generative Portrait Shadow Removal
    38244, -- 2410.08017 Fast Feedforward 3D Gaussian Splatting Compression
    38267, -- 2410.08168 ZeroComp: Zero-shot Object Compositing from Image Intrinsics via Diffusion
    38321, -- 2410.08941 MeshGS: Adaptive Mesh-Aligned Gaussian Splatting for High-Quality Rendering
    38367, -- 2410.09566 Bridging Text and Image for Artist Style Transfer via Contrastive Learning
    38387, -- 2410.09802 EBDM: Exemplar-guided Image Translation with Brownian-bridge Diffusion Models
    38415, -- 2410.10207 MagicEraser: Erasing Any Objects via Semantics-Aware Control
    38456, -- 2410.10745 FlexGen: Flexible Multi-View Generation from Text and Image Inputs
    38524, -- 2410.11374 Preserve or Modify? Context-Aware Evaluation for Balancing Preservation and Modi
    38528, -- 2410.11419 GS^3: Efficient Relighting with Triple Gaussian Splatting
    38560, -- 2410.11815 SGEdit: Bridging LLM with Text2Image Generative Model for Scene Graph-based Imag
    38612, -- 2410.12501 DH-VTON: Deep Text-Driven Virtual Try-On via Hybrid Attention Learning
    38744, -- 2410.13807 ConsisSR: Delving Deep into Consistency in Diffusion-based Image Super-Resolutio
    38751, -- 2410.13832 VidPanos: Generative Panoramic Videos from Casual Panning Videos
    38760, -- 2410.13861 PUMA: Empowering Unified MLLM with Multi-granular Visual Generation
    38761, -- 2410.13862 DepthSplat: Connecting Gaussian Splatting and Depth
    38785, -- 2410.14170 Personalized Image Generation with Large Multimodal Models
    38808, -- 2410.14524 Less is More: Selective Reduction of CT Data for Self-Supervised Pre-Training of
    38891, -- 2410.15636 LucidFusion: Generating 3D Gaussians with Arbitrary Unposed Images
    38984, -- 2410.16770 The Scene Language: Representing Scenes with Programs, Words, and Embeddings
    39090, -- 2410.18355 Real-time 3D-aware Portrait Video Relighting
    39214, -- 2410.20084 UniVST: A Unified Framework for Training-free Localized Video Style Transfer
    39525, -- 2411.00762 Face Anonymization Made Simple
    39693, -- 2411.03982 ReEdit: Multimodal Exemplar-Based Image Editing with Diffusion Models
    39753, -- 2411.04983 DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning
    39855, -- 2411.06602 Adaptive and Temporally Consistent Gaussian Surfels for Multi-view Dynamic Recon
    39924, -- 2411.07765 Novel View Synthesis with Pixel-Space Diffusion Models
    39965, -- 2411.08656 MikuDance: Animating Character Art with Mixed Motion Dynamics
    40006, -- 2411.09539 A Practical Guide to Fine-tuning Language Models with Limited Data
    40057, -- 2411.10510 SmoothCache: A Universal Inference Acceleration Technique for Diffusion Transfor
    40060, -- 2411.10546 The Oxford Spires Dataset: Benchmarking Large-Scale LiDAR-Visual Localisation, R
    40080, -- 2411.10947 Direct and Explicit 3D Generation from a Single Image
    40112, -- 2411.11505 LaVin-DiT: Large Vision Diffusion Transformer
    40153, -- 2411.12197 MTFusion: Reconstructing Any 3D Object from Single Image Using Multi-word Textua
    40163, -- 2411.12450 Frequency-Aware Guidance for Blind Image Restoration via Diffusion Models
    40201, -- 2411.13209 Comparative Analysis of Audio Feature Extraction for Real-Time Talking Portrait
    40215, -- 2411.13503 VBench++: Comprehensive and Versatile Benchmark Suite for Video Generative Model
    40223, -- 2411.13552 REDUCIO! Generating 1024$\times$1024 Video within 16 Seconds using Extremely Com
    40273, -- 2411.14494 dc-GAN: Dual-Conditioned GAN for Face Demorphing From a Single Morph
    40279, -- 2411.14521 MyTimeMachine: Personalized Facial Age Transformation
    40290, -- 2411.14740 TEXGen: a Generative Diffusion Model for Mesh Textures
    40314, -- 2411.15034 HeadRouter: A Training-free Image Editing Framework for MM-DiTs by Adaptively Ro
    40321, -- 2411.15106 About Time: Advances, Challenges, and Outlooks of Action Understanding
    40367, -- 2411.15542 Hierarchical Cross-Attention Network for Virtual Try-On
    40372, -- 2411.15604 FATE: Full-head Gaussian Avatar with Textural Editing from Monocular Video
    40412, -- 2411.16180 Event-boosted Deformable 3D Gaussians for Dynamic Scene Reconstruction
    40413, -- 2411.16185 Fancy123: One Image to High-Quality 3D Mesh Generation via Plug-and-Play Deforma
    40452, -- 2411.16720 Importance-Based Token Merging for Efficient Image and Video Generation
    40479, -- 2411.16969 ZoomLDM: Latent Diffusion Model for multi-scale image generation
    40490, -- 2411.17163 OSDFace: One-Step Diffusion Model for Face Restoration
    40494, -- 2411.17190 SelfSplat: Pose-Free and 3D Prior-Free Generalizable 3D Gaussian Splatting
    40520, -- 2411.17489 Puzzle Similarity: A Perceptually-guided Cross-Reference Metric for Artifact Det
    40529, -- 2411.17616 Towards Stabilized and Efficient Diffusion Transformers through Long-Skip-Connec
    40542, -- 2411.17696 ScribbleLight: Single Image Indoor Relighting with Scribbles
    40546, -- 2411.17762 MUSE-VL: Modeling Unified VLM through Semantic Discrete Encoding
    40586, -- 2411.18263 TSD-SR: One-Step Diffusion with Target Score Distillation for Real-World Image S
    40630, -- 2411.18677 MatchDiffusion: Training-free Generation of Match-cuts
    40638, -- 2411.18824 FaithDiff: Unleashing Diffusion Priors for Faithful Image Super-resolution
    40648, -- 2411.19050 I Dream My Painting: Connecting MLLMs and Diffusion Models via Prompt Generation
    40653, -- 2411.19108 Timestep Embedding Tells: It's Time to Cache for Video Diffusion Model
    40663, -- 2411.19278 OMNI-DC: Highly Robust Depth Completion with Multiresolution Depth Integration
    40666, -- 2411.19292 UrbanCAD: Towards Highly Controllable and Photorealistic 3D Vehicles for Urban S
    40690, -- 2411.19528 RAGDiffusion: Faithful Cloth Generation via External Knowledge Assimilation
    40701, -- 2411.19652 Uniform Attention Maps: Boosting Image Fidelity in Reconstruction and Editing
    40747, -- 2412.00177 LumiNet: Latent Intrinsics Meets Diffusion Models for Indoor Scene Relighting
    40807, -- 2412.01064 FLOAT: Generative Motion Latent Flow Matching for Audio-driven Talking Portrait
    40837, -- 2412.01506 Structured 3D Latents for Scalable and Versatile 3D Generation
    40850, -- 2412.01718 HUGSIM: A Real-Time, Photo-Realistic and Closed-Loop Simulator for Autonomous Dr
    40873, -- 2412.01986 HybridMQA: Exploring Geometry-Texture Interactions for Colored Mesh Quality Asse
    40900, -- 2412.02322 Controlling the Latent Diffusion Model for Generative Image Shadow Removal via R
    40922, -- 2412.02692 Taming Scalable Visual Tokenizer for Autoregressive Image Generation
    40945, -- 2412.03021 PEMF-VVTO: Point-Enhanced Video Virtual Try-on via Mask-free Paradigm
    40971, -- 2412.03318 Domain-Agnostic Stroke Lesion Segmentation Using Physics-Constrained Synthetic D
    41110, -- 2412.04715 Addressing Attribute Leakages in Diffusion-based Image Editing without Training
    41119, -- 2412.04827 PanoDreamer: Optimization-Based Single Image to 360 3D Scene With Diffusion
    41149, -- 2412.05256 Extrapolated Urban View Synthesis Benchmark
    41156, -- 2412.05279 Perturb-and-Revise: Flexible 3D Editing with Generative Trajectories
    41294, -- 2412.07293 EventSplat: 3D Gaussian Splatting from Moving Event Cameras for Real-time Render
    41297, -- 2412.07333 Fusion Embedding for Pose-Guided Person Image Synthesis with Diffusion Model
    41301, -- 2412.07371 PRM: Photometric Stereo based Large Reconstruction Model
    41312, -- 2412.07660 Proc-GS: Procedural Building Generation for City Assembly with 3D Gaussians
    41391, -- 2412.08573 TryOffAnyone: Tiled Cloth Generation from a Dressed Person
    41401, -- 2412.08629 FlowEdit: Inversion-Free Text-Based Editing Using Pre-Trained Flow Models
    41406, -- 2412.08641 3D Mesh Editing using Masked LRMs
    41431, -- 2412.09013 Arbitrary-steps Image Super-resolution via Diffusion Inversion
    41456, -- 2412.09405 Learned Compression for Compressed Learning
    41475, -- 2412.09593 Neural LightRig: Unlocking Accurate Object Normal and Material Estimation with M
    41482, -- 2412.09608 Representing Long Volumetric Video with Temporal Gaussian Hierarchy
    41542, -- 2412.10316 BrushEdit: All-In-One Image Inpainting and Editing
    41653, -- 2412.11755 Generative Inbetweening through Frame-wise Conditions-Driven Video Generation
    41697, -- 2412.12093 CAP4D: Creating Animatable 4D Portrait Avatars with Morphable Multi-View Diffusi
    41755, -- 2412.12906 CATSplat: Context-Aware Transformer with Spatial Guidance for Generalizable 3D G
    41801, -- 2412.13443 DarkIR: Robust Low-Light Image Restoration
    41904, -- 2412.14963 IDOL: Instant Photorealistic 3D Human Creation from a Single Image
    41980, -- 2412.15670 BS-LDM: Effective Bone Suppression in High-Resolution Chest X-Ray Images with Co
    42050, -- 2412.16978 PromptDresser: Improving the Quality and Controllability of Virtual Try-On via G
    42055, -- 2412.17042 Adapting Image-to-Video Diffusion Models for Large-Motion Frame Interpolation
    42122, -- 2412.17812 FaceLift: Single Image to 3D Head with View Generation and GS-LRM
    42177, -- 2412.18565 3DEnhancer: Consistent Multi-View Diffusion for 3D Enhancement
    42184, -- 2412.18608 PartGen: Part-level 3D Generation and Reconstruction with Multi-View Diffusion M
    42196, -- 2412.18862 WeatherGS: 3D Scene Reconstruction in Adverse Weather Conditions via Gaussian Sp
    42223, -- 2412.19505 DrivingWorld: Constructing World Model for Autonomous Driving via Video GPT
    42260, -- 2412.20062 MADiff: Text-Guided Fashion Image Editing with Mask Prediction and Attention-Enh
    42308, -- 2412.21042 Visual Style Prompt Learning Using Diffusion Models for Blind Face Restoration
    42319, -- 2412.21206 PERSE: Personalized 3D Generative Avatars from A Single Portrait
    42375, -- 2501.00740 RORem: Training a Robust Object Remover with Human-in-the-Loop
    42381, -- 2501.00816 MixSA: Training-free Reference-based Sketch Extraction via Mixture-of-Self-Atten
    42421, -- 2501.01320 SeedVR: Seeding Infinity in Diffusion Transformer Towards Generic Video Restorat
    42425, -- 2501.01392 ProjectedEx: Enhancing Generation in Explainable AI for Prostate Cancer
    42430, -- 2501.01424 Object-level Visual Prompts for Compositional Image Generation
    42439, -- 2501.01633 ACE: Anti-Editing Concept Erasure in Text-to-Image Models
    42517, -- 2501.02913 Pointmap-Conditioned Diffusion for Consistent Novel View Synthesis
    42523, -- 2501.02976 STAR: Spatial-Temporal Augmentation with Text-to-Video Models for Real-World Vid
    42534, -- 2501.03120 CAT: Content-Adaptive Image Tokenization
    42575, -- 2501.03847 Diffusion as Shader: 3D-aware Video Diffusion for Versatile Video Generation Con
    42609, -- 2501.04374 Instructive3D: Editing Large Reconstruction Models with Text Instructions
    42618, -- 2501.04586 Identity-Preserving Video Dubbing Using Motion Warping
    42627, -- 2501.04689 SPAR3D: Stable Point-Aware Reconstruction of 3D Objects from Single Images
    42636, -- 2501.04782 GaussianVideo: Efficient Video Representation via Hierarchical Gaussian Splattin
    42693, -- 2501.05710 EmotiCrafter: Text-to-Emotional-Image Generation based on Valence-Arousal Model
    42709, -- 2501.06006 CamCtrl3D: Single-Image Scene Exploration with Precise 3D Camera Control
    42739, -- 2501.06438 Qffusion: Controllable Portrait Video Editing via Quadrant-Grid Attention Learni
    42766, -- 2501.06838 Generalized and Efficient 2D Gaussian Splatting for Arbitrary-scale Super-Resolu
    42781, -- 2501.07104 RMAvatar: Photorealistic Human Avatar Reconstruction from Monocular Video Based
    42812, -- 2501.07730 Democratizing Text-to-Image Masked Generative Models with Compact Text-Aware One
    42840, -- 2501.08295 LayerAnimate: Layer-specific Control for Animation
    42870, -- 2501.08727 Transformed Low-rank Adaptation via Tensor Decomposition and Its Applications to
    42875, -- 2501.08819 Boosting Diffusion Guidance via Learning Degradation-Aware Models for Blind Supe
    42888, -- 2501.09038 Do generative video models understand physical principles?
    42932, -- 2501.09756 SynthLight: Portrait Relighting with Diffusion Model by Learning to Re-render Sy
    42967, -- 2501.10110 DiffVSR: Enhancing Real-World Video Super-Resolution with Diffusion Models for A
    43005, -- 2501.11102 RDG-GS: Relative Depth Guidance with Gaussian Splatting for Real-time Sparse-Vie
    43030, -- 2501.11561 Teaching Large Language Models to Regress Accurate Image Quality Scores using Sc
    43100, -- 2501.12832 FDG-Diff: Frequency-Domain-Guided Diffusion Framework for Compressed Hazy Image
    43289, -- 2501.15891 Any2AnyTryon: Leveraging Adaptive Position Embeddings for Versatile Virtual Clot
    43329, -- 2501.16757 ITVTON:Virtual Try-On Diffusion Transformer Model Based on Integrated Image and
    43425, -- 2501.18590 DiffusionRenderer: Neural Inverse and Forward Rendering with Video Diffusion Mod
    43461, -- 2501.19088 JGHand: Joint-Driven Animatable Hand Avater via 3D Gaussian Splatting
    43534, -- 2502.00992 FCBoost-Net: A Generative Network for Synthesizing Multiple Collocated Outfits v
    43604, -- 2502.01784 VILP: Imitation Learning with Latent Video Planning
    43607, -- 2502.01846 UVGS: Reimagining Unstructured 3D Gaussian Splatting using UV Mapping
    43644, -- 2502.02283 GP-GS: Gaussian Processes for Enhanced Gaussian Splatting
    43782, -- 2502.04393 UniCP: A Unified Caching and Pruning Framework for Efficient Video Generation
    43849, -- 2502.05176 AuraFusion360: Augmented Unseen Region Alignment for Reference-based 360° Unboun
    43909, -- 2502.06145 Animate Anyone 2: High-Fidelity Character Image Animation with Environment Affor
    43984, -- 2502.06957 GAS: Generative Avatar Synthesis from a Single Image
    44011, -- 2502.07278 Articulate That Object Part (ATOP): 3D Part Articulation from Text and Motion Pe
    44046, -- 2502.07685 Matrix3D: Large Photogrammetry Model All-in-One
    44054, -- 2502.07784 MatSwap: Light-aware material transfers in images
    44067, -- 2502.07945 SurGrID: Controllable Surgical Simulation via Scene Graph to Image Diffusion
    44175, -- 2502.09655 Bidirectional Diffusion Bridge Models
    44181, -- 2502.09873 Compression-Aware One-Step Diffusion Model for JPEG Artifact Removal
    44385, -- 2502.11897 DLFR-VAE: Dynamic Latent Frame Rate VAE for Video Generation
    44649, -- 2502.14462 Single-image Reflectance and Transmittance Estimation from Any Flatbed Scanner
    44837, -- 2502.16421 High-resolution Rainy Image Synthesis: Learning from Rendering
    44890, -- 2502.16943 MAD-AD: Masked Diffusion for Unsupervised Brain Anomaly Detection
    44936, -- 2502.17363 KV-Edit: Training-Free Image Editing for Precise Background Preservation
    44941, -- 2502.17414 X-Dancer: Expressive Music to Human Dance Video Generation
    45016, -- 2502.18417 GHOST 2.0: generative high-fidelity one shot transfer of heads
    45092, -- 2502.19441 AniGaussian: Animatable Gaussian Avatar with Pose-guided Deformation
    45159, -- 2502.20220 Avat3r: Large Animatable Gaussian Reconstruction Model for High-fidelity 3D Head
    45298, -- 2503.01107 VideoHandles: Editing 3D Object Compositions in Videos Using Video Generative Pr
    45325, -- 2503.01425 MeshPad: Interactive Sketch-Conditioned Artist-Designed Mesh Generation and Edit
    45413, -- 2503.02452 2DGS-Avatar: Animatable High-fidelity Clothed Avatar via 2D Gaussian Splatting
    45563, -- 2503.04720 FluidNexus: 3D Fluid Reconstruction and Prediction from a Single Video
    45628, -- 2503.05638 TrajectoryCrafter: Redirecting Camera Trajectory for Monocular Videos via Diffus
    45629, -- 2503.05639 VideoPainter: Any-length Video Inpainting and Editing with Plug-and-Play Context
    45669, -- 2503.06179 ForestSplats: Deformable transient field for Gaussian Splatting in the Wild
    45672, -- 2503.06235 StreamGS: Online Generalizable Gaussian Splatting Reconstruction for Unposed Ima
    45738, -- 2503.06923 From Reusing to Forecasting: Accelerating Diffusion Models with TaylorSeers
    45771, -- 2503.07232 Boosting Diffusion-Based Text Image Super-Resolution Model Towards Generalized R
    45802, -- 2503.07535 LBM: Latent Bridge Matching for Fast Image-to-Image Translation
    45813, -- 2503.07601 Balanced Image Stylization with Style Matching Score
    45844, -- 2503.08071 GigaSLAM: Large-Scale Monocular SLAM with Hierarchical Gaussian Splats
    45856, -- 2503.08224 HRAvatar: High-Quality and Relightable Gaussian Head Avatar
    45875, -- 2503.08434 Bokeh Diffusion: Defocus Blur Control in Text-to-Image Diffusion Models
    45904, -- 2503.08677 OmniPaint: Mastering Object-Oriented Editing via Disentangled Insertion-Removal
    45905, -- 2503.08678 GarmentCrafter: Progressive Novel View Synthesis for Single-View 3D Garment Reco
    45990, -- 2503.09641 SANA-Sprint: One-Step Diffusion with Continuous-Time Consistency Distillation
    45994, -- 2503.09669 Silent Branding Attack: Trigger-free Data Poisoning Attack on Text-to-Image Diff
    46026, -- 2503.10259 KVQ: Boosting Video Quality Assessment via Saliency-guided Local Perception
    46108, -- 2503.10860 RI3D: Few-Shot Gaussian Splatting With Repair and Inpainting Diffusion Priors
    46119, -- 2503.11073 Perceive, Understand and Restore: Real-World Image Super-Resolution with Autoreg
    46132, -- 2503.11221 Toward Generalized Image Quality Assessment: Relaxing the Perfect Reference Qual
    46152, -- 2503.11514 Exploring the Vulnerabilities of Federated Learning: A Deep Dive into Gradient I
    46159, -- 2503.11591 Pathology Image Compression with Pre-trained Autoencoders
    46206, -- 2503.12553 Niagara: Normal-Integrated Geometric Affine Field for Scene Reconstruction from
    46267, -- 2503.13434 BlobCtrl: A Unified and Flexible Framework for Element-level Image Generation an
    46281, -- 2503.13684 FiVE: A Fine-grained Video Editing Benchmark for Evaluating Emerging Diffusion a
    46326, -- 2503.14325 LeanVAE: An Ultra-Efficient Reconstruction VAE for Video Diffusion Models
    46338, -- 2503.14445 Bolt3D: Generating 3D Scenes in Seconds
    46345, -- 2503.14489 Stable Virtual Camera: Generative View Synthesis with Diffusion Models
    46412, -- 2503.15617 CAM-Seg: A Continuous-valued Embedding Approach for Semantic Image Generation
    46420, -- 2503.15671 CHROME: Clothed Human Reconstruction with Occlusion-Resilience and Multiview-Con
    46429, -- 2503.15855 VideoRFSplat: Direct Scene-Level Text-to-3D Gaussian Splatting Generation with F
    46490, -- 2503.16420 SynCity: Training-Free Generation of 3D Worlds
    46579, -- 2503.17760 CODA: Repurposing Continuous VAEs for Discrete Tokenization
    46585, -- 2503.17856 ClaraVid: A Holistic Scene Reconstruction Benchmark From Aerial Perspective With
    46594, -- 2503.17973 PhysTwin: Physics-Informed Reconstruction and Simulation of Deformable Objects f
    46677, -- 2503.18945 Aether: Geometric-Aware Unified World Modeling
    46712, -- 2503.19480 GenHancer: Imperfect Generative Models are Secretly Strong Vision-Centric Enhanc
    46776, -- 2503.20240 Unconditional Priors Matter! Improving Conditional Generation of Fine-Tuned Diff
    46785, -- 2503.20318 EditCLIP: Representation Learning for Image Editing
    46787, -- 2503.20349 Consistency Trajectory Matching for One-Step Generative Super-Resolution
    46812, -- 2503.20785 Free4D: Tuning-free 4D Scene Generation with Spatial-Temporal Consistency
    46830, -- 2503.21172 Model as a Game: On Numerical and Spatial Consistency for Generative Games
    46855, -- 2503.21541 LOCATEdit: Graph Laplacian Optimized Cross Attention for Localized Text-Guided I
    47009, -- 2503.23368 Towards Physically Plausible Video Generation via VLM Planning
    47023, -- 2503.23580 DiT4SR: Taming Diffusion Transformer for Real-World Image Super-Resolution
    47060, -- 2503.24210 DiET-GS: Diffusion Prior and Event Stream-Assisted Motion Deblurring 3D Gaussian
    47130, -- 2504.00983 WorldScore: A Unified Evaluation Benchmark for World Generation
    47145, -- 2504.01218 Prompting Forgetting: Unlearning in GANs via Textual Guidance
    47161, -- 2504.01647 FlowR: Flowing from Sparse to Dense 3D Reconstructions
    47190, -- 2504.02007 OccludeNeRF: Geometric-aware 3D Scene Inpainting with Collaborative Score Distil
    47239, -- 2504.02612 Fine-Tuning Visual Autoregressive Models for Subject-Driven Generation
    47269, -- 2504.03140 Model Reveals What to Cache: Profiling-Based Feature Reuse for Video Diffusion M
    47316, -- 2504.03886 WildGS-SLAM: Monocular Gaussian Splatting SLAM in Dynamic Environments
    47322, -- 2504.04010 DiTaiListener: Controllable High Fidelity Listener Video Generation with Diffusi
    47484, -- 2504.07426 Conditional Data Synthesis Augmentation
    47544, -- 2504.08348 Geometric Consistency Refinement for Single Image Novel View Synthesis via Test-
    47571, -- 2504.08736 GigaTok: Scaling Visual Tokenizers to 3 Billion Parameters for Autoregressive Im
    47611, -- 2504.09555 Mitigating Long-tail Distribution in Oracle Bone Inscriptions: Dataset, Model, a
    47636, -- 2504.09887 Enhanced Semantic Extraction and Guidance for UGC Image Super Resolution
    47644, -- 2504.10001 GaussVideoDreamer: 3D Scene Generation with Video Diffusion and Inconsistency-Aw
    47702, -- 2504.10716 SpinMeRound: Consistent Multi-View Identity Generation Using Diffusion Models
    47707, -- 2504.10822 IlluSign: Illustrating Sign Language Videos by Leveraging the Attention Mechanis
    47718, -- 2504.11092 Vivid4D: Improving 4D Reconstruction from Monocular Video by Video Inpainting
    47796, -- 2504.12273 Beyond Reconstruction: A Physics Based Neural Deferred Shader for Photo-realisti
    47843, -- 2504.12900 FashionDPO:Fine-tune Fashion Outfit Generation Model using Direct Preference Opt
    47856, -- 2504.13078 Enhancing Person-to-Person Virtual Try-On with Multi-Garment Virtual Try-Off
    47862, -- 2504.13129 Science-T2I: Addressing Scientific Illusions in Image Synthesis
    47868, -- 2504.13157 AerialMegaDepth: Learning Aerial-Ground Reconstruction and View Synthesis
    47875, -- 2504.13176 IMAGGarment-1: Fine-Grained Garment Generation for Controllable Fashion Design
    47892, -- 2504.13490 Early Timestep Zero-Shot Candidate Selection for Instruction-Guided Image Editin
    47999, -- 2504.15179 FaceCraft4D: Animated 3D Facial Avatar Generation from a Single Image
    48009, -- 2504.15278 DRAWER: Digital Reconstruction and Articulation With Environment Realism
    48108, -- 2504.17414 3DV-TON: Textured 3D-Guided Consistent Video Try-on via Diffusion Models
    48168, -- 2504.19077 Learning to Drive from a World Model
    48356, -- 2505.01742 Easz: An Agile Transformer-based Image Compression Framework for Resource-constr
    48364, -- 2505.02005 Learning Heterogeneous Mixture of Scene Experts for Large-scale Neural Radiance
    48378, -- 2505.02178 Sparfels: Fast Reconstruction from Sparse Unposed Imagery
    48444, -- 2505.03351 GUAVA: Generalizable Upper Body 3D Gaussian Avatar
    48455, -- 2505.03623 Bounding Box-Guided Diffusion for Synthesizing Industrial Images and Segmentatio
    48479, -- 2505.04320 Multi-turn Consistent Image Editing
    48513, -- 2505.04915 GlyphMastero: A Glyph Encoder for High-Fidelity Scene Text Editing
    48519, -- 2505.05022 SOAP: Style-Omniscient Animatable Portraits
    48575, -- 2505.06176 MonetGPT: Solving Puzzles Enhances MLLMs' Image Retouching Skills
    48587, -- 2505.06393 Toward Advancing License Plate Super-Resolution in Real-World Scenarios: A Datas
    48591, -- 2505.06502 PC-SRGAN: Physically Consistent Super-Resolution Generative Adversarial Network
    48678, -- 2505.08239 ACT-R: Adaptive Camera Trajectories for Single View 3D Reconstruction
    48773, -- 2505.10420 Learned Lightweight Smartphone ISP with Unpaired Data
    48787, -- 2505.10566 3D-Fixup: Advancing Photo Editing with 3D Priors
    49138, -- 2505.14204 Beginning with You: Perceptual-Initialization Improves Vision-Language Represent
    49269, -- 2505.15185 MonoSplat: Generalizable 3D Gaussian Splatting from Monocular Depth Foundation M
    49281, -- 2505.15282 Exploring In-Image Machine Translation with Real-World Background
    49375, -- 2505.16181 Understanding Generative AI Capabilities in Everyday Image Editing Tasks
    49471, -- 2505.16976 Creatively Upscaling Images with Global-Regional Priors
    49582, -- 2505.18142 TokBench: Evaluating Your Visual Tokenizer before Visual Generation
    49690, -- 2505.19138 Veta-GS: View-dependent deformable 3D Gaussian Splatting for thermal infrared No
    49827, -- 2505.20171 Long-Context State-Space Video World Models
    49984, -- 2505.21925 RenderFormer: Transformer-based Neural Rendering of Triangle Meshes with Global
    50140, -- 2505.23716 AnySplat: Feed-forward 3D Gaussian Splatting from Unconstrained Views
    50299, -- 2506.00227 Ctrl-Crash: Controllable Diffusion for Realistic Car Crashes
    50496, -- 2506.03139 SVGenius: Benchmarking LLMs in SVG Understanding, Editing and Generation
    50513, -- 2506.03478 Facial Appearance Capture at Home with Patch-Level Reflectance Prior
    50525, -- 2506.03594 SplArt: Articulation Estimation and Part-Level Reconstruction with 3D Gaussian S
    50656, -- 2506.05338 Defurnishing with X-Ray Vision: Joint Removal of Furniture from Panoramas and Me
    50789, -- 2506.07863 VIVAT: Virtuous Improving VAE Training through Artifact Mitigation
    50795, -- 2506.07932 Squeeze3D: Your 3D Generation Model is Secretly an Extreme Neural Compressor
    50828, -- 2506.08071 CuRe: Cultural Gaps in the Long Tail of Text-to-Image Systems
    50974, -- 2506.09995 PlayerOne: Egocentric World Simulator
    51372, -- 2506.18527 Auto-Regressively Generating Multi-View Consistent Images
    51398, -- 2506.18903 VMem: Consistent Interactive Video Scene Generation with Surfel-Indexed View Mem
    51491, -- 2506.21022 Instella-T2I: Pushing the Limits of 1D Discrete Latent Space Image Generation
    51559, -- 2506.22753 Degradation-Modeled Multipath Diffusion for Tunable Metalens Photography
    51620, -- 2507.01608 Perception-Oriented Latent Coding for High-Performance Compressed Domain Semanti
    51631, -- 2507.01953 FreeMorph: Tuning-Free Generalized Image Morphing with Diffusion Model
    51712, -- 2507.04947 DC-AR: Efficient Masked Autoregressive Image Generation with Deep Compression Hy
    51714, -- 2507.04984 TLB-VFI: Temporal-Aware Latent Brownian Bridge Diffusion for Video Frame Interpo
    51720, -- 2507.05163 4DSloMo: 4D Reconstruction for High Speed Scene with Asynchronous Capture
    51746, -- 2507.05763 DreamArt: Generating Interactable Articulated Objects from a Single Image
    51807, -- 2507.07202 A Survey on Long-Video Storytelling Generation: Architectures, Consistency, and
    51873, -- 2507.10437 4D-Animal: Freely Reconstructing Animatable 3D Animals from Videos
    51903, -- 2507.11465 Elevating 3D Models: High-Quality Texture and Geometry Refinement from a Low-Qua
    52008, -- 2507.15629 Gaussian Splatting with Discretized SDF for Relightable Assets
    52125, -- 2507.23374 NeRF Is a Valuable Assistant for 3D Gaussian Splatting
    52135, -- 2507.23785 Gaussian Variation Field Diffusion for High-fidelity Video-to-4D Synthesis
    52149, -- 2508.00823 IGL-Nav: Incremental 3D Gaussian Localization for Image-goal Navigation
    52274, -- 2508.05813 Optimization-Free Style Transfer for 3D Gaussian Splats
    52355, -- 2508.09983 Story2Board: A Training-Free Approach for Expressive Storyboard Generation
    52384, -- 2508.11203 StyleMM: Stylized 3D Morphable Face Model via Text-Driven Aligned Image Translat
    52413, -- 2508.13104 Precise Action-to-Video Generation Through Visual Action Prompts
    52436, -- 2508.14041 LongSplat: Robust Unposed 3D Gaussian Splatting for Casual Long Videos
    52447, -- 2508.14892 Snap-Snap: Taking Two Images to Reconstruct 3D Human Gaussians in Milliseconds
    52465, -- 2508.15769 SceneGen: Single-Image 3D Scene Generation in One Feedforward Pass
    52540, -- 2508.19247 VoxHammer: Training-Free Precise and Coherent 3D Editing in Native 3D Space
    52620, -- 2509.01984 Discrete Noise Inversion for Next-scale Autoregressive Text-based Image Editing
    52662, -- 2509.04582 Inpaint4Drag: Repurposing Inpainting Models for Drag-Based Image Editing via Bid
    52761, -- 2509.10441 InfGen: A Resolution-Agnostic Paradigm for Scalable Image Synthesis
    52894, -- 2509.17985 VideoFrom3D: 3D Scene Video Generation via Complementary Image and Video Diffusi
    52936, -- 2509.19297 VolSplat: Rethinking Feed-Forward 3D Gaussian Splatting with Voxel-Aligned Predi
    53245, -- 2510.05081 SAEdit: Token-level control for continuous image editing via Sparse AutoEncoder
    53300, -- 2510.06596 SDQM: Synthetic Data Quality Metric for Object Detection Dataset Evaluation
    53398, -- 2510.08271 SViM3D: Stable Video Material Diffusion for Single Image 3D Generation
    53524, -- 2510.12777 What If : Understanding Motion Through Sparse Interactions
    53647, -- 2510.15869 Skyfall-GS: Synthesizing Immersive 3D Urban Scenes from Satellite Imagery
    53649, -- 2510.15868 LightsOut: Diffusion-based Outpainting for Enhanced Lens Flare Removal
    53915, -- 2508.07766 UniSVG: A Unified Dataset for Vector Graphic Understanding and Generation with M
    54131, -- 2511.07409 DIMO: Diverse 3D Motion Generation for Arbitrary Objects
    54159, -- 2511.08633 Time-to-Move: Training-Free Motion Controlled Video Generation via Dual-Clock De
    54399, -- 2511.18005 RAISECity: A Multimodal Agent Framework for Reality-Aligned 3D World Generation
    54401, -- 2511.17918 Frequency-Adaptive Sharpness Regularization for Improving 3D Gaussian Splatting
    54513, -- 2512.01989 PAI-Bench: A Comprehensive Benchmark For Physical AI
    54525, -- 2512.02942 Benchmarking Scientific Understanding and Reasoning for Video Generation using V
    54597, -- 2512.01803 Generative Action Tell-Tales: Assessing Human Motion in Synthesized Videos
    54672, -- 2512.07197 SUCCESS-GS: Survey of Compactness and Compression for Efficient Static and Dynam
    54752, -- 2512.13687 Towards Scalable Pre-training of Visual Tokenizers for Generation
    54809, -- 2512.14284 SS4D: Native 4D Generative Model via Structured Spacetime Latents
    54926, -- 2512.17040 Infinite-Homography as Robust Conditioning for Camera-Controlled Video Generatio
    55133, -- 2512.23950 U-Net-Like Spiking Neural Networks for Single Image Dehazing
    55432, -- 2601.14256 Implicit Neural Representation Facilitates Unified Universal Vision Encoding
    55458, -- 2601.16192 360Anything: Geometry-Free Lifting of Images and Videos to 360°
    55625, -- 2601.21716 DreamActor-M2: Universal Character Image Animation via Spatiotemporal In-Context
    55801, -- 2602.04271 SkeletonGaussian: Editable 4D Generation through Gaussian Skeletonization
    55838, -- 2602.05871 Pathwise Test-Time Correction for Autoregressive Long Video Generation
    56208, -- 2602.17365 Computer-Using World Model
    56225, -- 2602.15727 Spanning the Visual Analogy Space with a Weight Basis of LoRAs
    56545, -- 2603.08703 HiAR: Efficient Autoregressive Long Video Generation via Hierarchical Denoising
    56578, -- 2603.07066 MedSteer: Counterfactual Endoscopic Synthesis via Training-Free Activation Steer
    56587, -- 2603.03143 Geometry-Guided Reinforcement Learning for Multi-view Consistent 3D Scene Editin
    56706, -- 2603.07815 HybridStitch: Pixel and Timestep Level Model Stitching for Diffusion Acceleratio
    56728, -- 2603.15583 Grounding World Simulation Models in a Real-World Metropolis
    56791, -- 2603.16864 SparkVSR: Interactive Video Super-Resolution via Sparse Keyframe Propagation
    56808, -- 2603.16099 OneWorld: Taming Scene Generation with 3D Unified Representation Autoencoder
    56878, -- 2603.19234 Matryoshka Gaussian Splatting
    56909, -- 2603.19500 Teaching an Agent to Sketch One Part at a Time
    56929, -- 2603.22057 SpatialBoost: Enhancing Visual Representation through Language-Guided Reasoning
    56949, -- 2603.22286 WorldCache: Content-Aware Caching for Accelerated Video World Models
    57006, -- 2603.21618 4DGS360: 360° Gaussian Reconstruction of Dynamic Objects from a Single Video
    57032, -- 2603.14366 Representation Alignment for Just Image Transformers is not Easier than You Thin
    57182, -- 2604.02296 VOID: Video Object and Interaction Deletion
    57204, -- 2604.02330 ActionParty: Multi-Subject Action Binding in Generative Video Games
    57312, -- 2604.07350 Fast Spatial Memory with Elastic Test-Time Training
    57347, -- 2604.08526 FIT: A Large-Scale Dataset for Fit-Aware Virtual Try-On
    57423, -- 2604.10333 Zero-shot World Models Are Developmentally Efficient Learners
    57424, -- 2604.11521 Continuous Adversarial Flow Models
    57533, -- 2604.14914 Beyond Prompts: Unconditional 3D Inversion for Out-of-Distribution Shapes
    57698, -- 2604.21931 Seeing Fast and Slow: Learning the Flow of Time in Videos
    57876, -- 2604.23584 Identity-Decoupled Anonymization for Visual Evidence in Multi-modal Retrieval-Au
    58159, -- 2604.14591 Prompt-Guided Image Editing with Masked Logit Nudging in Visual Autoregressive M
    58176, -- 2604.13906 Blind Bitstream-corrupted Video Recovery via Metadata-guided Diffusion Model
    58195, -- 2410.05882 Frame forecasting in cine MRI using the PCA respiratory motion model: comparing
    58215, -- 2604.12575 StructDiff: A Structure-Preserving and Spatially Controllable Diffusion Model fo
    58507, -- 2604.04487 Training-Free Image Editing with Visual Context Integration and Concept Alignmen
    58705, -- 2603.29139 SciVisAgentBench: A Benchmark for Evaluating Scientific Data Analysis and Visual
    58771, -- 2603.28322 SFDemorpher: Generalizable Face Demorphing for Operational Morphing Attack Detec
    58828, -- 2603.26193 MemCam: Memory-Augmented Camera Control for Consistent Video Generation
    58881, -- 2603.25265 ViewSplat: View-Adaptive Dynamic Gaussian Splatting for Feed-Forward Synthesis
    58907, -- 2603.25129 AirSplat: Alignment and Rating for Robust Feed-Forward 3D Gaussian Splatting
    58928, -- 2603.24270 ScrollScape: Unlocking 32K Image Generation With Video Diffusion Priors
    58982, -- 2603.22677 MuQ-Eval: An Open-Source Per-Sample Quality Metric for AI Music Generation Evalu
    59030, -- 2603.22607 Dress-ED: Instruction-Guided Editing for Virtual Try-On and Try-Off
    59090, -- 2603.20186 Improving Image-to-Image Translation via a Rectified Flow Reformulation
    59100, -- 2603.19607 Physion-Eval: Evaluating Physical Realism in Generated Video via Human Reasoning
    59133, -- 2603.19036 FUMO: Prior-Modulated Diffusion for Single Image Reflection Removal
    59238, -- 2603.17219 SA-CycleGAN-2.5D: Self-Attention CycleGAN with Tri-Planar Context for Multi-Site
    59337, -- 2603.14916 EditHF-1M: A Million-Scale Rich Human Preference Feedback for Image Editing
    59427, -- 2603.13967 EchoLVFM: One-Step Video Generation via Latent Flow Matching for Echocardiogram
    59442, -- 2603.13615 Egocentric World Model for Photorealistic Hand-Object Interaction Synthesis
    59465, -- 2603.12716 UNIStainNet: Foundation-Model-Guided Virtual Staining of H&E to IHC
    59481, -- 2603.12811 OARS: Process-Aware Online Alignment for Generative Real-World Image Super-Resol
    59899, -- 2603.04223 Semi-Supervised Generative Learning via Latent Space Distribution Matching
    59958, -- 2603.02985 The Dresden Dataset for 4D Reconstruction of Non-Rigid Abdominal Surgical Scenes
    60057, -- 2602.23697 Towards Source-Aware Object Swapping with Initial Noise Perturbation
    60087, -- 2603.00947 Mobile-VTON: High-Fidelity On-Device Virtual Try-On
    60214, -- 2602.23169 Learning Continuous Wasserstein Barycenter Space for Generalized All-in-One Imag
    60221, -- 2602.22960 UCM: Unifying Camera Control and Memory with Time-aware Positional Encoding Warp
    60265, -- 2602.22197 Off-The-Shelf Image-to-Image Models Are All You Need To Defeat Image Protection
    60549, -- 2602.16950 HS-3D-NeRF: 3D Surface and Hyperspectral Reconstruction From Stationary Hyperspe
    60686, -- 2602.13818 VAR-3D: View-aware Auto-Regressive Model for Text-to-3D Generation via a 3D Toke
    60747, -- 2602.12271 MonarchRT: Efficient Attention for Real-Time Video Generation
    60779, -- 2602.11693 OMEGA-Avatar: One-shot Modeling of 360° Gaussian Avatars
    61225, -- 2602.04873 Laminating Representation Autoencoders for Efficient Diffusion
    61686, -- 2601.23065 EAG-PT: Emission-Aware Gaussians and Path Tracing for Indoor Scene Reconstructio
    61887, -- 2601.20857 FreeFix: Boosting 3D Gaussian Splatting via Fine-Tuning-Free Diffusion Models
    61960, -- 2601.19750 Benchmarking Multimodal Large Language Models for Missing Modality Completion in
    62077, -- 2601.17717 The LLM Data Auditor: A Metric-oriented Survey on Quality and Trustworthiness in
    62092, -- 2601.17586 Stylizing ViT: Anatomy-Preserving Instance Style Transfer for Domain Generalizat
    62142, -- 2601.16645 Edge-Aware Image Manipulation via Diffusion Models with a Novel Structure-Preser
    62227, -- 2601.15284 Walk through Paintings: Egocentric World Models from Internet Priors
    62279, -- 2601.14246 Soft Tail-dropping for Adaptive Visual Tokenization
    62770, -- 2601.05127 LooseRoPE: Content-aware Attention Manipulation for Semantic Harmonization
    62884, -- 2601.03665 PhysVideoGenerator: Towards Physically Aware Video Generation via Latent Physics
    63199, -- 2512.24016 FitControler: Toward Fit-Aware Virtual Try-On
    63225, -- 2512.23437 RealX3D: A Physically-Degraded 3D Benchmark for Multi-view Visual Restoration an
    63420, -- 2512.19817 Generating the Past, Present and Future from a Motion-Blurred Image
    63556, -- 2512.16743 TreeNet: A Light Weight Model for Low Bitrate Image Compression
    63722, -- 2512.12963 SCAdapter: Content-Style Disentanglement for Diffusion Style Transfer
    63840, -- 2512.10572 DeMapGS: Simultaneous Mesh Deformation and Surface Attribute Mapping via Gaussia
    64095, -- 2512.05209 DEAR: Dataset for Evaluating the Aesthetics of RenderingDEAR: Dataset for Evalua
    64107, -- 2512.04830 FreeGen: Feed-Forward Reconstruction-Generation Co-Training for Free-Viewpoint D
    64150, -- 2512.04084 SimFlow: Simplified and End-to-End Training of Latent Normalizing Flows
    64154, -- 2512.03981 DirectDrag: High-Fidelity, Mask-Free, Prompt-Free Drag-based Image Editing via R
    64267, -- 2512.01755 FreqEdit: Preserving High-Frequency Features for Robust Multi-Turn Image Editing
    64302, -- 2512.01296 EGG-Fusion: Efficient 3D Reconstruction with Geometry-aware Gaussian Surfel on t
    64377, -- 2512.05134 InvarDiff: Cross-Scale Invariance Caching for Accelerated Diffusion Models
    64451, -- 2511.21945 AmodalGen3D: Generative Amodal 3D Object Reconstruction from Sparse Unposed View
    64713, -- 2511.17839 Show Me: Unifying Instructional Image and Video Generation with Diffusion Models
    64796, -- 2511.16711 Motion Transfer-Enhanced StyleGAN for Generating Diverse Macaque Facial Expressi
    64906, -- 2511.13649 Distribution Matching Distillation Meets Reinforcement Learning
    65181, -- 2511.07987 CSF-Net: Context-Semantic Fusion Network for Large Mask Inpainting
    65199, -- 2511.07732 ViPRA: Video Prediction for Robot Actions
    65242, -- 2511.06830 MUGSQA: Novel Multi-Uncertainty-Based Gaussian Splatting Quality Assessment Meth
    65253, -- 2511.06765 Robust and High-Fidelity 3D Gaussian Splatting: Fusing Pose Priors and Geometry
    65281, -- 2511.05865 CGCE: Classifier-Guided Concept Erasure in Generative Models
    65294, -- 2511.05403 PALM: A Dataset and Baseline for Learning Multi-subject Hand Prior
    65463, -- 2511.01767 Wonder3D++: Cross-domain Diffusion for High-fidelity 3D Generation from a Single
    66170, -- 2510.17330 CharDiff: A Diffusion Model with Character-Level Guidance for License Plate Imag
    66370, -- 2510.13587 HRM^2Avatar: High-Fidelity Real-Time Mobile Avatars from Monocular Phone Scans
    66696, -- 2510.08561 MultiCOIN: Multi-Modal COntrollable Video INbetweening
    66820, -- 2510.06827 StyleKeeper: Prevent Content Leakage using Negative Visual Query Guidance
    66929, -- 2510.04961 SSDD: Single-Step Diffusion Decoder for Efficient Image Tokenization
    67039, -- 2510.08587 EGSTalker: Real-Time Audio-Driven Talking Head Generation with Efficient Gaussia
    67081, -- 2510.02514 Learning a distance measure from the information-estimation geometry of data
    67394, -- 2509.25183 PAD3R: Pose-Aware Dynamic 3D Reconstruction from Casual Videos
    67697, -- 2509.22222 Rigidity-Aware 3D Gaussian Deformation from a Single Image
    67785, -- 2509.21259 Semantic Edge-Cloud Communication for Real-Time Urban Traffic Surveillance with
    67882, -- 2509.19965 SynchroRaMa : Lip-Synchronized and Emotion-Aware Talking Face Generation via Mul
    67917, -- 2509.20400 SeHDR: Single-Exposure HDR Novel View Synthesis via 3D Gaussian Bracketing
    67940, -- 2509.19080 World4RL: Diffusion World Models for Policy Refinement with Reinforcement Learni
    67956, -- 2509.18831 Text Slider: Efficient and Plug-and-Play Continuous Concept Control for Image/Vi
    68019, -- 2509.17654 Clothing agnostic Pre-inpainting Virtual Try-ON
    68085, -- 2509.16630 Follow-Your-Emoji-Faster: Towards Efficient, Fine-Controllable, and Expressive F
    68282, -- 2509.13768 Generative Image Coding with Diffusion Prior
    68416, -- 2509.11273 Synthetic Dataset Evaluation Based on Generalized Cross Validation
    68683, -- 2509.05441 Missing Fine Details in Images: Last Seen in High Frequencies
    68694, -- 2509.05131 A Scalable Attention-Based Approach for Image-to-3D Texture Mapping
    68700, -- 2509.05394 Reverse Browser: Vector-Image-to-Code Generator
    68752, -- 2509.03883 Human Motion Video Generation: A Survey
    68850, -- 2508.18071 EventTracer: Fast Path Tracing-based Event Stream Rendering
    68856, -- 2509.05342 Delta Velocity Rectified Flow for Text-to-Image Editing
    68873, -- 2509.01411 MILO: A Lightweight Perceptual Quality Metric for Image and Latent-Space Optimiz
    68923, -- 2509.00800 SWAGSplatting: Semantic-guided Water-scene Augmented Gaussian Splatting
    68960, -- 2509.00403 DevilSight: Augmenting Monocular Human Avatar Reconstruction through a Virtual P
    69046, -- 2508.20505 Describe, Don't Dictate: Semantic Image Editing with Natural Language Intent
    69048, -- 2508.20471 Realistic and Controllable 3D Gaussian-Guided Object Editing for Driving Video G
    69224, -- 2508.17712 NGD: Neural Gradient Based Deformation for Monocular Garment Reconstruction
    69470, -- 2508.13776 Comparing Conditional Diffusion Models for Synthesizing Contrast-Enhanced Breast
    69516, -- 2508.13065 Odo: Depth-Guided Diffusion for Identity-Preserving Body Reshaping
    69587, -- 2508.12131 DualFit: A Two-Stage Virtual Try-On via Warping and Synthesis
    69608, -- 2508.11603 CoreEditor: Correspondence-constrained Diffusion for Consistent 3D Editing
    69814, -- 2508.08700 Subjective and Objective Quality Assessment of Banding Artifacts on Compressed V
    69834, -- 2508.08498 CObL: Toward Zero-Shot Ordinal Layering without User Prompting
    69841, -- 2508.08384 Spatiotemporally Consistent Indoor Lighting Estimation with Diffusion Priors
    69842, -- 2508.08254 Learning an Implicit Physics Model for Image-based Fluid Simulation
    69879, -- 2508.07760 Sea-Undistort: A Dataset for Through-Water Image Restoration in High Resolution
    69899, -- 2508.07537 Enhanced Generative Structure Prior for Chinese Text Image Super-resolution
    69901, -- 2508.07519 Exploring Multimodal Diffusion Transformers for Enhanced Prompt-based Image Edit
    69967, -- 2508.06392 FVGen: Accelerating Novel-View Synthesis with Adversarial Video Diffusion Distil
    70149, -- 2508.04090 Bridging Diffusion Models and 3D Representations: A 3D Consistent Super-Resoluti
    70192, -- 2508.03497 EditGarment: An Instruction-Based Garment Editing Dataset Constructed with Autom
    70219, -- 2508.03180 Duplex-GS: Proxy-Guided Weighted Blending for Real-Time Order-Independent Gaussi
    70285, -- 2508.02240 Forecasting When to Forecast: Accelerating Diffusion Models with Confidence-Gate
    70376, -- 2508.01171 No Pose at All: Self-Supervised Pose-Free 3D Gaussian Splatting from Sparse View
    70381, -- 2508.01098 Trans-Adapter: A Plug-and-Play Framework for Transparent Image Inpainting
    70426, -- 2508.00413 DC-AE 1.5: Accelerating Diffusion Model Convergence with Structured Latent Space
    70486, -- 2508.03735 StorySync: Training-Free Subject Consistency in Text-to-Image Generation via Reg
    70620, -- 2507.21371 Top2Pano: Learning to Generate Indoor Panoramas from Top-Down View
    70670, -- 2507.20291 Fine-structure Preserved Real-world Image Super-resolution via Transfer VAE Trai
    70838, -- 2507.17332 PARTE: Part-Guided Texturing for 3D Human Reconstruction from a Single Image
    70907, -- 2507.16010 FW-VTON: Flattening-and-Warping for Person-to-Person Virtual Try-on
    70911, -- 2507.15979 Dream, Lift, Animate: From Single Images to Animatable Gaussian Avatars
    70956, -- 2507.15037 OmniVTON: Training-Free Universal Virtual Try-On
    70997, -- 2507.14501 Advances in Feed-Forward 3D Reconstruction and View Synthesis: A Survey
    71045, -- 2507.12796 DeQA-Doc: Adapting DeQA-Score to Document Image Quality Assessment
    71056, -- 2507.12667 VolSegGS: Segmentation and Tracking in Dynamic Volumetric Scenes via Deformable
    71107, -- 2507.11638 Interpretable Prediction of Lymph Node Metastasis in Rectal Cancer MRI Using Var
    71163, -- 2507.09984 Latent Diffusion Models with Masked AutoEncoders
    71216, -- 2507.09168 Stable Score Distillation
    71288, -- 2507.07317 ADIEE: Automatic Dataset Creation and Scorer for Instruction-Guided Image Editin
    71370, -- 2507.05148 SV-DRR: High-Fidelity Novel View X-Ray Synthesis Using Diffusion Model
    71522, -- 2507.01496 ReFlex: Text-Guided Editing of Real Images in Rectified Flow via Mid-Step Featur
    71574, -- 2507.00429 DiGA3D: Coarse-to-Fine Diffusional Propagation of Geometry and Appearance for Ve
    71627, -- 2506.23482 MTADiffusion: Mask Text Alignment Diffusion Model for Object Inpainting
    71638, -- 2506.23295 DiffFit: Disentangled Garment Warping and Texture Refinement for Virtual Try-On
    71715, -- 2506.21046 Boosting Generative Adversarial Transferability with Self-supervised Vision Tran
    71735, -- 2506.21629 ICP-3DGS: SfM-free 3D Gaussian Splatting for Large-scale Unbounded Scenes
    71848, -- 2506.16679 How to Train your Text-to-Image Model: Evaluating Design Choices for Synthetic T
    71858, -- 2506.16572 Single-step Diffusion for Image Compression at Ultra-Low Bitrates
    71960, -- 2506.13298 Fair Generation without Unfair Distortions: Debiasing Text-to-Image Generation w
    72008, -- 2506.11764 DiffFuSR: Super-Resolution of all Sentinel-2 Multispectral Bands using Diffusion
    72044, -- 2506.10507 Edit360: 2D Image Edits to 3D Assets from Any Angle
    72126, -- 2506.07698 NOVA3D: Normal Aligned Video Diffusion Model for Single Image to 3D Generation
    72315, -- 2506.03118 HumanRAM: Feed-forward Human Reconstruction and Animation Model using Transforme
    72319, -- 2506.03082 SG2VID: Scene Graphs Enable Fine-Grained Control for Video Synthesis
    72376, -- 2506.01921 MedEBench: Revisiting Text-instructed Image Editing on Medical Domain
    72377, -- 2506.02095 Cycle Consistency as Reward: Learning Image-Text Alignment without Human Prefere
    72624, -- 2505.21502 Generalizable and Relightable Gaussian Splatting for Human Novel View Synthesis
    72686, -- 2505.20626 ConsiStyle: Style Diversity in Training-Free Consistent T2I Generation
    72754, -- 2505.21545 Corruption-Aware Training of Latent Video Diffusion Models for Robust Text-to-Vi
    72845, -- 2505.17001 Seeing through Satellite Images at Street Views
    73005, -- 2505.11992 SpatialCrafter: Unleashing the Imagination of Video Diffusion Models for Scene R
    73008, -- 2505.11934 iSegMan: Interactive Segment-and-Manipulate 3D Gaussians
    73073, -- 2505.09166 An Exploration of Default Images in Text-to-Image Generation
    73203, -- 2505.01934 GauS-SLAM: Dense RGB-D SLAM with Gaussian Surfels
    73271, -- 2504.20222 FreBIS: Frequency-Based Stratification for Neural Implicit Surface Representatio
    73299, -- 2504.19165 IM-Portrait: Learning 3D-aware Video Diffusion for Photorealistic Talking Heads
    73359, -- 2504.17825 Dual Prompting Image Restoration with Diffusion Transformers
    73422, -- 2504.15054 Structure-guided Diffusion Transformer for Low-Light Image Enhancement
    73536, -- 2504.09588 TextSplat: Text-Guided Semantic Fusion for Generalizable Gaussian Splatting
    73541, -- 2504.09491 DropoutGS: Dropping Out Gaussians for Better Sparse-view Rendering
    73576, -- 2504.08125 Gen3DEval: Using vLLMs for Automatic Evaluation of Generated 3D Objects
    73604, -- 2504.06861 EIDT-V: Exploiting Intersections in Diffusion Trajectories for Model-Agnostic, Z
    73625, -- 2504.07144 GIGA: Generalizable Sparse Image-driven Gaussian Humans
    73827, -- 2503.22796 DiTFastAttnV2: Head-wise Attention Compression for Multi-Modality Diffusion Tran
    73876, -- 2503.19452 SparseGS-W: Sparse-View 3D Gaussian Splatting in the Wild with Generative Priors
    73894, -- 2503.19011 RomanTex: Decoupling 3D-aware Rotary Positional Embedded Multi-Attention Network
    74025, -- 2503.13272 Generative Gaussian Splatting: Generating 3D Scenes with Video Diffusion Priors
    74028, -- 2503.13176 DeGauss: Dynamic-Static Decomposition with Gaussian Splatting for Distractor-fre
    74071, -- 2503.12049 TACO: Taming Diffusion for in-the-wild Video Amodal Completion
    74145, -- 2503.09631 V2M4: 4D Mesh Animation Reconstruction from a Single Monocular Video
    74165, -- 2503.08217 S3R-GS: Streamlining the Pipeline for Large-Scale Street Scene Reconstruction
    74170, -- 2503.08136 FlowDPS: Flow-Driven Posterior Sampling for Inverse Problems
    74178, -- 2503.07946 7DGS: Unified Spatial-Temporal-Angular Gaussian Splatting
    74215, -- 2403.07588 Visual Privacy Auditing with Diffusion Models
    74397, -- 2502.21079 Training-free and Adaptive Sparse Attention for Efficient Long Video Generation
    74426, -- 2502.20376 Tight Inversion: Image-Conditioned Inversion for Real Image Editing
    74478, -- 2502.18219 Synthesizing Consistent Novel Views via 3D Epipolar Attention without Re-Trainin
    74863, -- 2502.04318 sshELF: Single-Shot Hierarchical Extrapolation of Latent Features for 3D Reconst
    74961, -- 2502.01102 Towards Robust and Generalizable Lensless Imaging with Modular Learned Reconstru
    75019, -- 2502.00173 Lifting by Gaussians: A Simple, Fast and Flexible Method for 3D Instance Segment
    75109, -- 2501.13087 Orchid: Image Latent Diffusion for Joint Appearance and Geometry Generation
    75124, -- 2501.12255 HAC++: Towards 100X Compression of 3D Gaussian Splatting
    75215, -- 2501.06927 CULTURE3D: A Large-Scale and Diverse Dataset of Cultural Landmarks and Terrains
    75246, -- 2501.05242 SEGS-SLAM: Structure-enhanced 3D Gaussian Splatting SLAM with Appearance Embeddi
    75289, -- 2501.02725 Advances in Artificial Intelligence: A Review for the Creative Industries
    75405, -- 2412.15215 EnvGS: Modeling View-Dependent Appearance with Environment Gaussian
    75457, -- 2412.11762 GS-ProCams: Gaussian Splatting-based Projector-Camera Systems
    75470, -- 2412.11224 GenLit: Reformulating Single-Image Relighting as Video Generation
    75523, -- 2412.08210 Unicorn: Unified Neural Image Compression with One Number Reconstruction
    75579, -- 2412.04852 SleeperMark: Towards Robust Watermark against Fine-Tuning Text-to-image Diffusio
    75585, -- 2412.04459 Sparse Voxels Rasterization: Real-time High-fidelity Radiance Field Rendering
    75592, -- 2412.04130 Deep priors for satellite image restoration with accurate uncertainties
    75594, -- 2412.04037 INFP: Audio-Driven Interactive Head Generation in Dyadic Conversations
    75644, -- 2412.00397 DreamDance: Animating Human Images by Enriching 3D Geometry Cues from 2D Poses
    75696, -- 2411.17513 Human Vision Constrained Super-Resolution
    75706, -- 2411.16816 SplatAD: Real-Time Lidar and Camera Rendering with 3D Gaussian Splatting for Aut
    75772, -- 2411.07795 InvisMark: Invisible and Robust Watermarking for AI-generated Image Provenance
    75843, -- 2411.04810 GANESH: Generalizable NeRF for Lensless Imaging
    76006, -- 2410.15067 A Survey on All-in-One Image Restoration: Taxonomy, Evaluation and Future Trends
    76019, -- 2410.13613 MEGA: Memory-Efficient 4D Gaussian Splatting for Dynamic Scenes
    76224, -- 2410.12822 AVID: Adapting Video Diffusion Models to World Models
    76228, -- 2410.00381 Downscaling Extreme Precipitation with Wasserstein Regularized Diffusion
    76334, -- 2407.08165 Explicit-NeRF-QA: A Quality Assessment Database for Explicit NeRF Model Compress
    76421, -- 2409.07040 Retinex-RAWMamba: Bridging Demosaicing and Denoising for Low-Light RAW Image Enh
    76556, -- 2408.10901 A Gray-box Attack against Latent Diffusion Model-based Image Editing by Posterio
    76753, -- 2407.11419 TeethDreamer: 3D Teeth Reconstruction from Five Intra-oral Photographs
    76785, -- 2407.07302 Pairwise Distance Distillation for Unsupervised Real-World Image Super-Resolutio
    76817, -- 2407.02945 VEGS: View Extrapolation of Urban Scenes in 3D Gaussian Splatting using Learned
    76850, -- 2407.01074 Multimodal Conditional 3D Face Geometry Generation
    76887, -- 2406.18361 Stable Diffusion Segmentation for Biomedical Images with Single-step Reverse Pro
    76902, -- 2406.17254 Scalp Diagnostic System With Label-Free Segmentation and Training-Free Image Tra
    76922, -- 2406.15643 Taming 3DGS: High-Quality Radiance Fields with Limited Resources
    76980, -- 2406.11138 Diffusion Models in Low-Level Vision: A Survey
    77164, -- 2405.18525 REPARO: Compositional 3D Assets Generation with Differentiable 3D Layout Alignme
    77219, -- 2405.14580 LDM: Large Tensorial SDF Model for Textured Mesh Generation
    77351, -- 2404.18820 Towards Extreme Image Compression with Latent Feature Guidance and Diffusion Pri
    77374, -- 2404.15692 Deep Learning for Accelerated and Robust MRI Reconstruction: a Review
    77561, -- 2403.18730 Towards Image Ambient Lighting Normalization
    77573, -- 2403.17094 SynFog: A Photo-realistic Synthetic Fog Dataset based on End-to-end Imaging Simu
    77601, -- 2403.13890 Towards Learning Contrast Kinetics with Multi-Condition Latent Diffusion Models
    77611, -- 2403.12852 Generative Enhancement for 3D Medical Images
    77788, -- 2402.12886 Real-time High-resolution View Synthesis of Complex Scenes with Explicit 3D Visi
    77834, -- 2402.05350 Descanning: From Scanned to the Original Images with a Color Correction Diffusio
    77949, -- 2401.08053 SCoFT: Self-Contrastive Fine-Tuning for Equitable Image Generation
    78027, -- 2312.17526 Noise-free Optimization in Early Training Steps for Image Super-Resolution
    78164, -- 2312.01632 GaussianHead: High-fidelity Head Avatars with Learnable Gaussian Derivation
    78179, -- 2311.18259 Ego-Exo4D: Understanding Skilled Human Activity from First- and Third-Person Per
    78181, -- 2311.17744 Variational Bayes image restoration with compressive autoencoders
    78220, -- 2311.12897 An Efficient 3D Gaussian Representation for Monocular/Multi-view Dynamic Scenes
    78611, -- 2308.12902 CDAN: Convolutional dense attention-guided network for low-light image enhanceme
    78637, -- 2308.09388 Diffusion Models for Image Restoration and Enhancement: A Comprehensive Survey
    78915, -- 2306.04236 Flare7K++: Mixing Synthetic and Real Datasets for Nighttime Flare Removal and Be
    78917, -- 2306.04175 ScoreCL: Augmentation-Adaptive Contrastive Learning via Score-Matching Function
    78939, -- 2306.00914 Conditioning Diffusion Models via Attributes and Semantic Masks for Face Generat
    79138, -- 2304.06019 Generating Aligned Pseudo-Supervision from Non-Aligned Data for Image Restoratio
    79186, -- 2303.11162 Picture that Sketch: Photorealistic Image Generation from Abstract Sketches
    79226, -- 2303.10894 M^{2}SNet: Multi-scale in Multi-scale Subtraction Network for Medical Image Segm
    79321, -- 2302.14736 TextIR: A Simple Framework for Text-based Editable Image Restoration
    79356, -- 2302.07672 LiveHand: Real-time and Photorealistic Neural Hand Rendering
    79399, -- 2301.13402 ReGANIE: Rectifying GAN Inversion Errors for Accurate Real Image Editing
    79467, -- 2212.12645 HandsOff: Labeled Dataset Generation With No Additional Human Annotations
    79510, -- 2212.01567 AdaCM: Adaptive ColorMLP for Real-Time Universal Photo-realistic Style Transfer
    79553, -- 2211.11448 Delving StyleGAN Inversion for Image Editing: A Foundation Latent Space Viewpoin
    79690, -- 2210.01879 A Perceptual Quality Metric for Video Frame Interpolation
    79716, -- 2109.10737 DyStyle: Dynamic Neural Network for Multi-Attribute-Conditioned Style Editing
    79731, -- 2209.08814 T2V-DDPM: Thermal to Visible Face Translation using Denoising Diffusion Probabil
    79853, -- 2207.04904 Going the Extra Mile in Face Image Quality Assessment: A Novel Database and Mode
    80134, -- 2203.09195 Details or Artifacts: A Locally Discriminative Learning Approach to Realistic Im
    80136, -- 2203.07967 Intrinsic Neural Fields: Learning Functions on Manifolds
    80208, -- 2202.06358 Do Inpainting Yourself: Generative Facial Inpainting Guided by Exemplars
    80215, -- 2202.04879 PVSeRF: Joint Pixel-, Voxel- and Surface-Aligned Radiance Field for Single-Image
    80330, -- 2112.04491 Improving Image Restoration by Revisiting Global Information Aggregation
    80344, -- 2112.01516 Ownership and Creativity in Generative Models
    80345, -- 2112.01455 Zero-Shot Text-Guided Object Generation with Dream Fields
    80387, -- 2111.08960 Compositional Transformers for Scene Generation
    80449, -- 2110.06635 ADOP: Approximate Differentiable One-Pixel Point Rendering
    80499, -- 2109.10595 Live Speech Portraits: Real-Time Photorealistic Talking-Head Animation
    80540, -- 2109.00512 Common Objects in 3D: Large-Scale Learning and Evaluation of Real-life 3D Catego
    80703, -- 2105.14951 SNIPS: Solving Noisy Inverse Problems Stochastically
    80714, -- 2105.08935 DeepFaceEditing: Deep Face Generation and Editing with Disentangled Geometry and
    80768, -- 2104.09556 Removing Diffraction Image Artifacts in Under-Display Camera via Dynamic Skip Co
    80858, -- 2103.01114 Deep Perceptual Image Quality Assessment for Compression
    80866, -- 2102.12037 Conditional Image Generation by Conditioning Variational Auto-Encoders
    80877, -- 2102.09532 Clockwork Variational Autoencoders
    80910, -- 2101.09552 Stochastic Image Denoising by Sampling from the Posterior Distribution
    80947, -- 2012.13253 Soft-IntroVAE: Analyzing and Improving the Introspective Variational Autoencoder
    81002, -- 2011.11201 Modular Action Concept Grounding in Semantic Video Prediction
    81086, -- 2010.04092 Knowledge-Enriched Distributional Model Inversion Attacks
    81112, -- 2009.12798 AIM 2020: Scene Relighting and Illumination Estimation Challenge
    81229, -- 2007.01289 Image Shape Manipulation from a Single Augmented Training Sample
    81267, -- 2006.06494 Anti-Transfer Learning for Task Invariance in Convolutional Neural Networks for
    81510, -- 1912.02279 Angular Visual Hardness
    81822, -- 1901.09482 Bridging the Gap Between Computational Photography and Visual Recognition
    82008, -- 1805.09817 Stereo Magnification: Learning View Synthesis using Multiplane Images
    83199, -- 2605.14984 Sat3DGen: Comprehensive Street-Level 3D Scene Generation from Single Satellite I
    83317, -- 2605.10302 Follow the Mean: Reference-Guided Flow Matching
    83541, -- 2605.21431 iTryOn: Mastering Interactive Video Virtual Try-On with Spatial-Semantic Guidanc
    83605, -- 2605.13163 LoREnc: Low-Rank Encryption for Securing Foundation Models and LoRA Adapters
    83716, -- 2111.15640 Diffusion Autoencoders: Toward a Meaningful and Decodable Representation
    85670, -- 2605.31535 RayDer: Scalable Self-Supervised Novel View Synthesis from Real-World Video
    85689, -- 2603.07543 CONSTANT: Towards High-Quality One-Shot Handwriting Generation with Patch Contra
    85735, -- 2501.19182 A compressive-expressive communication framework for compositional representatio
    86706, -- 2405.20559 Information-Driven Design of Imaging Systems
    87551, -- 2503.18438 ReconDreamer++: Harmonizing Generative and Reconstructive Models for Driving Sce
    87562, -- 2412.07494 ResGS: Residual Densification of 3D Gaussian for Efficient Detail Recovery
    87567, -- 2507.18569 Adversarial Distribution Matching for Diffusion Distillation Towards Efficient I
    87569, -- 2507.22459 Exploiting Diffusion Prior for Task-driven Image Restoration
    87580, -- 2505.23044 SpatialSplat: Efficient Semantic 3D from Sparse Unposed Images
    87588, -- 2507.04692 Structure-Guided Diffusion Models for High-Fidelity Portrait Shadow Removal
    87589, -- 2508.20136 Global Motion Corresponder for 3D Point-Based Scene Interpolation under Large Mo
    87594, -- 2507.01390 FixTalk: Taming Identity Leakage for High-Quality Talking Head Generation in Ext
    87606, -- 2507.10218 Straighten Viscous Rectified Flow via Noise Optimization
    87629, -- 2502.12545 IM360: Large-scale Indoor Mapping with 360 Cameras
    87633, -- 2503.06903 When Lighting Deceives: Exposing Vision-Language Models' Illumination Vulnerabil
    87634, -- 2510.00778 DIA: The Adversarial Exposure of Deterministic Inversion in Diffusion Models
    87646, -- 2507.13797 DynFaceRestore: Balancing Fidelity and Quality in Diffusion-Guided Blind Face Re
    87668, -- 2412.12765 Monocular Facial Appearance Capture in the Wild
    87672, -- 2509.16822 Looking in the Mirror: A Faithful Counterfactual Explanation Method for Interpre
    87675, -- 2505.04813 WIR3D: Visually-Informed and Geometry-Aware 3D Shape Abstraction
    87684, -- 2504.20042 CompleteMe: Reference-based Human Image Completion
    87686, -- 2502.05130 Latent Swap Joint Diffusion for 2D Long-Form Latent Generation
    87696, -- 2411.15867 PanoLlama: Generating Endless and Coherent Panoramas with Next-Token-Prediction
    87708, -- 2506.21132 Learning to See in the Extremely Dark
    87750, -- 2509.13922 Towards Robust Defense against Customization via Protective Perturbation Resista
    87779, -- 2504.04126 Multi-identity Human Image Animation with Structural Video Diffusion
    87798, -- 2503.11056 Flow to the Mode: Mode-Seeking Diffusion Autoencoders for State-of-the-Art Image
    87803, -- 2508.04297 MuGS: Multi-Baseline Generalizable Gaussian Splatting Reconstruction
    87806, -- 2504.07940 Beyond the Frame: Generating 360deg Panoramic Videos from Perspective Videos
    87808, -- 2507.00648 UMDATrack: Unified Multi-Domain Adaptive Tracking Under Adverse Weather Conditio
    87816, -- 2408.09151 Timestep-Aware Diffusion Model for Extreme Image Rescaling
    87831, -- 2504.07949 InteractAvatar: Modeling Hand-Face Interaction in Photorealistic Avatars with De
    87842, -- 2412.09607 Spectral Image Tokenizer
    87845, -- 2412.14580 DiffSim: Taming Diffusion Models for Evaluating Visual Similarity
    87872, -- 2507.12933 DMQ: Dissecting Outliers of Diffusion Models for Post-Training Quantization
    87878, -- 2507.20148 GT-Mean Loss: A Simple Yet Effective Solution for Brightness Mismatch in Low-Lig
    87880, -- 2507.12135 Learning Pixel-adaptive Multi-layer Perceptrons for Real-time Image Enhancement
    87890, -- 2411.17784 HypDAE: Hyperbolic Diffusion Autoencoders for Hierarchical Few-shot Image Genera
    87897, -- 2503.17262 Unsupervised Joint Learning of Optical Flow and Intensity with Event Cameras
    87905, -- 2405.17158 PatchScaler: An Efficient Patch-Independent Diffusion Model for Image Super-Reso
    87939, -- 2412.16919 TAR3D: Creating High-Quality 3D Assets via Next-Part Prediction
    87942, -- 2508.06301 FedMeNF: Privacy-Preserving Federated Meta-Learning for Neural Fields
    87973, -- 2406.01593 MaGS: Reconstructing and Simulating Dynamic 3D Objects with Mesh-adsorbed Gaussi
    87977, -- 2508.08556 Unlocking the Potential of Diffusion Priors in Blind Face Restoration
    87995, -- 2508.16121 Lightweight and Fast Real-time Image Enhancement via Decomposition of the Spatia
    87996, -- 2411.14937 Geminio: Language-Guided Gradient Inversion Attacks in Federated Learning
    87999, -- 2505.12860 Towards a Universal Image Degradation Model via Content-Degradation Disentanglem
    88011, -- 2506.01923 TaxaDiffusion: Progressively Trained Diffusion Model for Fine-Grained Species Ge
    88027, -- 2504.10434 Anchor Token Matching: Implicit Structure Locking for Training-free AR Image Edi
    88043, -- 2503.24366 StochasticSplats: Stochastic Rasterization for Sorting-Free 3D Gaussian Splattin
    88046, -- 2412.00623 A Lesson in Splats: Teacher-Guided Diffusion for 3D Gaussian Splats Generation w
    88090, -- 2411.16768 Sequential Gaussian Avatars with Hierarchical Motion Context
    88103, -- 2503.06671 Emulating Self-attention with Convolution for Efficient Image Super-Resolution
    88105, -- 2510.01669 UniVerse: Unleashing the Scene Prior of Video Diffusion Models for Robust Radian
    88108, -- 2507.18060 BokehDiff: Neural Lens Blur with One-Step Diffusion
    88123, -- 2503.18678 NullSwap: Proactive Identity Cloaking Against Deepfake Face Swapping
    88129, -- 2508.00548 Video Color Grading via Look-Up Table Generation
    88131, -- 2502.01181 BVINet: Unlocking Blind Video Inpainting with Zero Annotations
    88148, -- 2507.06856 IAP: Invisible Adversarial Patch Attack through Perceptibility-Aware Localizatio
    88169, -- 2506.21513 GGTalker: Talking Head Systhesis with Generalizable Gaussian Priors and Identity
    88184, -- 2508.06033 InstantEdit: Text-Guided Few-Step Image Editing with Piecewise Rectified Flow
    88196, -- 2503.23897 Training-Free Text-Guided Image Editing with Visual Autoregressive Model
    88210, -- 2503.19604 GIViC: Generative Implicit Video Compression
    88221, -- 2510.10993 Perspective-aware 3D Gaussian Inpainting with Multi-view Consistency
    88248, -- 2501.11746 SILO: Solving Inverse Problems with Latent Operators
    88253, -- 2508.16212 OmniCache: A Trajectory-Oriented Global Perspective on Training-Free Cache Reuse
    88256, -- 2507.17613 InvRGB+L: Inverse Rendering of Complex Scenes with Unified Color and LiDAR Refle
    88267, -- 2507.04408 A View-consistent Sampling Method for Regularized Training of Neural Radiance Fi
    88281, -- 2508.17600 GWM: Towards Scalable Gaussian World Models for Robotic Manipulation
    88284, -- 2507.19141 DASH: 4D Hash Encoding with Self-Supervised Decomposition for Real-Time Dynamic
    88313, -- 2501.05442 Progressive Growing of Video Tokenizers for Temporally Compact Latent Spaces
    88316, -- 2506.23618 TurboVSR: Fantastic Video Upscalers and Where to Find Them
    88334, -- 2508.17817 TemCoCo: Temporally Consistent Multi-modal Video Fusion with Visual-Semantic Col
    88340, -- 2506.16827 Beyond Blur: A Fluid Perspective on Generative Diffusion Models
    88341, -- 2507.02691 CanonSwap: High-Fidelity and Consistent Video Face Swapping via Canonical Space
    88350, -- 2506.10962 SpectralAR: Spectral Autoregressive Visual Generation
    88351, -- 2507.09524 When Schrodinger Bridge Meets Real-World Image Dehazing with Unpaired Training
    88365, -- 2508.09949 Stable Diffusion Models are Secretly Good at Visual In-Context Learning
    88366, -- 2509.10678 T2Bs: Text-to-Character Blendshapes via Video Generation
    88377, -- 2507.18155 GeoAvatar: Adaptive Geometrical Gaussian Splatting for 3D Head Avatar
    88389, -- 2508.00398 Occlusion-robust Stylization for Drawing-based 3D Animation
    88391, -- 2506.21977 StableCodec: Taming One-Step Diffusion for Extreme Image Compression
    88394, -- 2507.18758 Learning Efficient and Generalizable Human Representation with Human Gaussian Mo
    88396, -- 2505.23186 HiGarment: Cross-modal Harmony Based Diffusion Model for Flat Sketch to Realisti
    88421, -- 2509.18190 HazeFlow: Revisit Haze Physical Model as ODE and Non-Homogeneous Haze Generation
    88428, -- 2410.17422 Multimodal LLM Guided Exploration and Active Mapping using Fisher Information
    88430, -- 2412.19089 Humans as a Calibration Pattern: Dynamic 3D Scene Reconstruction from Unsynchron
    88452, -- 2504.16606 HUG: Hierarchical Urban Gaussian Splatting with Block-Based Reconstruction for L
    88456, -- 2508.20080 Seam360GS: Seamless 360deg Gaussian Splatting from Real-World Omnidirectional Im
    88462, -- 2411.08508 BillBoard Splatting (BBSplat): Learnable Textured Primitives for Novel View Synt
    88474, -- 2508.09262 Harnessing Input-Adaptive Inference for Efficient VLN
    88486, -- 2503.15742 Uncertainty-Aware Diffusion-Guided Refinement of 3D Scenes
    88496, -- 2412.03934 InfiniCube: Unbounded and Controllable Dynamic 3D Driving Scene Generation with
    88497, -- 2508.02168 After the Party: Navigating the Mapping From Color to Ambient Lighting
    88498, -- 2510.05660 Teleportraits: Training-Free People Insertion into Any Scene
    88501, -- 2412.09774 A Differentiable Wave Optics Model for End-to-End Computational Imaging System O
    88502, -- 2508.03118 H3R: Hybrid Multi-view Correspondence for Generalizable 3D Reconstruction
    88513, -- 2508.09973 PERSONA: Personalized Whole-Body 3D Avatar with Pose-Driven Deformations from a
    88518, -- 2410.13195 UniGS: Modeling Unitary 3D Gaussians for Novel View Synthesis from Sparse-view I
    88922, -- 2502.04248 Adapting to Evolving Adversaries with Regularized Continual Robust Training
    90118, -- 2503.18459 Hiding Images in Diffusion Models by Editing Learned Score Functions
    90157, -- 2505.06068 Noise-Consistent Siamese-Diffusion for Medical Image Synthesis and Segmentation
    90173, -- 2405.14672 Invisible Backdoor Attack against Self-supervised Learning
    90191, -- 2503.16065 Shining Yourself: High-Fidelity Ornaments Virtual Try-on with Diffusion Model
    90249, -- 2503.00861 Zero-Shot Head Swapping in Real-World Scenarios
    90258, -- 2405.12661 EmoEdit: Evoking Emotions through Image Manipulation
    90262, -- 2504.19819 Joint Optimization of Neural Radiance Fields and Continuous Camera Motion from a
    90263, -- 2412.15867 IRGS: Inter-Reflective Gaussian Splatting with 2D Gaussian Ray Tracing
    90301, -- 2412.13183 Real-time Free-view Human Rendering from Sparse-view RGB Videos using Double Unp
    90316, -- 2503.10148 3D Student Splatting and Scooping
    90320, -- 2412.10153 EVOS: Efficient Implicit Neural Training via EVOlutionary Selector
    90361, -- 2504.06210 HiMoR: Monocular Deformable Gaussian Reconstruction with Hierarchical Motion Rep
    90382, -- 2412.16939 Image Quality Assessment: Investigating Causal Perceptual Effects with Abductive
    90449, -- 2408.17064 Instant Adversarial Purification with Adversarial Consistency Distillation
    90457, -- 2502.20387 InsTaG: Learning Personalized 3D Talking Head from Few-Second Video
    90501, -- 2503.16964 DroneSplat: 3D Gaussian Splatting for Robust 3D Reconstruction from In-the-Wild
    90522, -- 2505.16980 Pursuing Temporal-Consistent Video Virtual Try-On via Dynamic Pose Interaction
    90528, -- 2412.03103 MultiGO: Towards Multi-level Geometry Learning for Monocular 3D Textured Human R
    90559, -- 2503.21816 EVPGS: Enhanced View Prior Guidance for Splatting-based Extrapolated View Synthe
    90566, -- 2412.20522 MaskGaussian: Adaptive 3D Gaussian Representation from Probabilistic Masks
    90573, -- 2312.06085 SFDM: Robust Decomposition of Geometry and Reflectance for Realistic Face Render
    90633, -- 2503.10078 Image Quality Assessment: From Human to Machine Preference
    90638, -- 2405.16414 Robust Message Embedding via Attention Flow-Based Steganography
    90687, -- 2503.15975 Acc3D: Accelerating Single Image to 3D Diffusion Models via Edge Consistency Gui
    90715, -- 2503.21931 Locally Orderless Images for Optimization in Differentiable Rendering
    90717, -- 2412.00518 Instant3dit: Multiview Inpainting for Fast Editing of 3D Objects
    90735, -- 2309.03904 Exploring Sparse MoE in GANs for Text-conditioned Image Synthesis
    90740, -- 2411.17106 PassionSR: Post-Training Quantization with Adaptive Scale in One-Step Diffusion
    90777, -- 2503.19357 Correcting Deviations from Normality: A Reformulated Diffusion Model for Multi-C
    90822, -- 2504.12909 Real-time High-fidelity Gaussian Human Avatars with Position-based Interpolation
    90927, -- 2503.22138 Enhancing Dance-to-Music Generation via Negative Conditioning Latent Diffusion M
    90938, -- 2412.11520 EditSplat: Multi-View Fusion and Attention-Guided Optimization for View-Consiste
    90940, -- 2503.04314 S2Gaussian: Sparse-View Super-Resolution 3D Gaussian Splatting
    91014, -- 2501.05763 StarGen: A Spatiotemporal Autoregression Framework with Video Diffusion Model fo
    92416, -- 2501.05803 Test-time Alignment of Diffusion Models without Reward Over-optimization
    92583, -- 2603.13201 Neuron-Aware Data Selection in Instruction Tuning for Large Language Models
    93067, -- 2603.10281 Taming Score-Based Denoisers in ADMM: A Convergent Plug-and-Play Framework
    93820, -- 2509.12821 A Statistical Benchmark for Diffusion-Posterior-Sampling Algorithms
    94217, -- 2604.16919 Noise-Adaptive Diffusion Sampling for Inverse Problems Without Task-Specific Tun
    94362, -- 2505.13289 RECON: Robust symmetry discovery via Explicit Canonical Orientation Normalizatio
    95152, -- 2409.14103 ExFMan: Rendering 3D Dynamic Humans with Hybrid Monocular Blurry Frames and Even
    95465, -- 2510.14117 ViTacGen: Robotic Pushing with Vision-To-Touch Generation
    95587, -- 2409.20435 A Photorealistic Dataset and Vision-Based Algorithm for Anomaly Detection During
    96031, -- 2603.12647 LR-SGS: Robust LiDAR-Reflectance-Guided Salient Gaussian Splatting for Self-Driv
    96389, -- 2409.18122 RT-GuIDE: Real-Time Gaussian Splatting for Information-Driven Exploration
    96442, -- 2505.10075 FlowDreamer: A RGB-D World Model with Flow-Based Motion Representations for Robo
    97442, -- 2506.12251 Efficient Multi-Camera Tokenization with Triplanes for End-To-End Driving
    97466, -- 2404.06727 Bayesian NeRF: Quantifying Uncertainty with Volume Density for Neural Implicit F
    97489, -- 2604.02996 Rendering Multi-Human and Multi-Object with 3D Gaussian Splatting
    98480, -- 2606.16767 Text-Vision Co-Instructed Image Editing
    98539, -- 2606.19195 Moebius: 0.2B Lightweight Image Inpainting Framework with 10B-Level Performance
    98929, -- 2606.27537 MemoBench: Benchmarking World Modeling in Dynamically Changing Environments
    98993, -- 2606.29308 MirrorPPR: Exemplar-Based Portrait Photo Retouching
    98999, -- 2606.30811 AVTok: 1D Unified Tokenization for Holistic Audio-Video Generation
    99005, -- 2606.31029 TerraDiT-Ω: Unified Spatial Control for Satellite Image Synthesis with Any Geosp
    99069, -- 2008.01928 Component Divide-and-Conquer for Real-World Image Super-Resolution
    99111, -- 2607.01803 PixGS: Pixel-Space Diffusion for Direct 3D Gaussian Splat Generation
    102598, -- 2203.12575 NeuMan: Neural Human Radiance Field from a Single Video
    102602, -- 2607.05392 SynCity 3000: Bootstrapping Scene-Scale 3D Diffusion
    102611, -- 2602.23890 DACESR: Degradation-Aware Conditional Embedding for Real-World Image Super-Resol
    102615, -- 2507.20590 Harnessing Diffusion-Yielded Score Priors for Image Restoration
    102616, -- 2311.14760 SinSR: Diffusion-Based Image Super-Resolution in a Single Step
    102682, -- 2607.06838 WildCity: A Real-World City-Scale Testbed for Rendering, Simulation, and Spatial
    103868, -- 2607.09125 4D Human-Scene Reconstruction from Low-Overlap Captures
    103895, -- 2111.12077 Mip-NeRF 360: Unbounded Anti-Aliased Neural Radiance Fields
    103896, -- 2012.09855 Infinite Nature: Perpetual View Generation of Natural Scenes from a Single Image
    103899, -- 2606.28321 StructSplat: Generalizable 3D Gaussian Splatting from Uncalibrated Sparse Views
    103907, -- 1905.00889 Local Light Field Fusion: Practical View Synthesis with Prescriptive Sampling Gu
    103912, -- 2405.12110 CoR-GS: Sparse-View 3D Gaussian Splatting via Co-Regularization
    103913, -- 2403.06912 DNGaussian: Optimizing Sparse-View 3D Gaussian Radiance Fields with Global-Local
    103915, -- 2501.11508 See In Detail: Enhancing Sparse-view 3D Gaussian Splatting with Local Depth and
    104013, -- 2607.12000 MetaView: Monocular Novel View Synthesis with Scale-Aware Implicit Geometry Prio
    104186, -- 1908.07201 Three-D Safari: Learning to Estimate Zebra Pose, Shape, and Texture from Images
    104261, -- 2403.11157 Selective Hourglass Mapping for Universal Image Restoration Based on Diffusion M
    104262, -- 2310.10123 AutoDIR: Automatic All-in-One Image Restoration with Latent Diffusion
    104340, -- 2006.09965 High-Fidelity Generative Image Compression
    104344, -- 2007.08739 Channel-wise Autoregressive Entropy Models for Learned Image Compression
    104358, -- 2002.03711 Learning End-to-End Lossy Image Compression: A Benchmark
    104516, -- 2607.21485 Recurrent Sinusoidal INRs for Efficient High-Fidelity Representation
    104558, -- 2607.10495 NanoVSR: Towards Real-Time Video Super-Resolution on Edge Devices
    104578, -- 2607.23855 OmniVAE: An Audio-Video VAE with Cross-Modal Alignment for Joint Generation
    104589, -- 2607.22148 dRAE: Representation Autoencoder with Hyper-Spherical Codes
    104744, -- 2607.25565 ReDesign: Recovering Editable Design Structures from Images via Agentic Decompos
    104751, -- 2605.28401 EgoRelight: Egocentric Human Capture and Illumination Recovery for Relightable a
    104752, -- 2606.06498 Semantic-Structural Alignment for Generative Pictorial Charts
    104757, -- 2605.21766 BodyReLux: Temporally Consistent Full-Body Video Relighting
    104759, -- 2604.19976 Lucky High Dynamic Range Smartphone Imaging
    104762, -- 2605.05636 Learning a Delighting Prior for Facial Appearance Capture in the Wild
    104770, -- 2602.08642 Forget Superresolution, Sample Adaptively (when Path Tracing)
    104798, -- 2603.00492 ArtiFixer: Enhancing and Extending 3D Reconstruction with Auto-Regressive Diffus
    104801, -- 2606.23270 BoxCtrl: 3D-Aware Visual Prompting for Geometric Image Editing
    104809, -- 2601.19843 Graphical X Splatting (GraphiXS): A Graphical Model for 4D Gaussian Splatting un
    104811, -- 2605.23178 Composing People Together: Iterative Pose-Image Generation for Multi-Person Inte
    104814, -- 2510.18189 A Generalizable Light Transport 3D Embedding for Global Illumination
    104817, -- 2605.06408 Scalable GPU Construction of 3D Voronoi and Power Diagrams
    104819, -- 2605.09279 CAGS: Color-Adaptive Volumetric Video Streaming with Dynamic 3D Gaussian Splatti
    104827, -- 2605.03359 Mix3R: Mixing Feed-forward Reconstruction and Generative 3D Priors for Joint Mul
    104832, -- 2606.14988 Toward Richer Material Generation via Procedural Data Enhancement
    104835, -- 2606.21270 Non-line-of-sight imaging with arbitrary relay surface geometries via 3D Gaussia
    104839, -- 2605.05664 Sparse-to-Complete: From Sparse Image Captures to Complete 3D Scenes
    104840, -- 2602.05676 ShapeUP: Scalable Image-Conditioned 3D Editing
    104842, -- 2506.22899 Neural Cellular Automata: From Cells to Pixels
    104854, -- 2605.00548 Colorful-Noise: Training-Free Low-Frequency Noise Manipulation for Color-Based C
    104871, -- 2604.28016 Faster 3D Gaussian Splatting Convergence via Structure-Aware Densification
    104874, -- 2605.04509 CoherentRaster: Efficient 3D Gaussian Splatting for Light Field Displays
    104879, -- 2605.09299 LagrangianSplats: Divergence-Free Transport of Gaussian Primitives for Fluid Rec
    104942, -- 2508.07788 Anatomy-Aware Low-Dose CT Denoising via Pretrained Vision Models and Semantic-Gu
    105107, -- 2503.01352 Diffusion-based Virtual Staining from Polarimetric Mueller Matrix Imaging
    105156, -- 2507.17388 EndoGen: Conditional Autoregressive Endoscopic Video Generation
    105206, -- 2510.02970 Flip Distribution Alignment VAE for Multi-Phase MRI Synthesis
    105618, -- 2503.15784 RL4Med-DDPO: Reinforcement Learning for Controlled Guidance Towards Diverse Medi
    105724, -- 2503.01075 Tackling Hallucination from Conditional Models for Medical Image Reconstruction
    105903, -- 2305.15956 Anomaly Detection with Conditioned Denoising Diffusion Models
    108609, -- 2111.15483 ST-MFNet: A Spatio-Temporal Multi-Flow Network for Frame Interpolation
    108621, -- 2003.05534 Softmax Splatting for Video Frame Interpolation
    108670, -- 2608.01127 MiniWorld: Democratizing the Training of Video World Models from Scratch
    108753, -- 2411.18966 SVGS: Enhancing Gaussian Splatting Using Primitives with Spatially Varying Color
    108821, -- 2606.31018 WarpI2I: Image Warping for Image-to-Image Translation
    109065, -- 2608.06751 Beyond Starry Night: Shortcut-Aware Control-State Planning for Artist-Grounded T
    109636, -- 2608.18077 Hydra-0: Action Flow for Generalist World Modeling and Control
    109853, -- 2410.16395 Joker: Conditional 3D Head Synthesis with Extreme Facial Expressions
    109854, -- 2303.18193 GVP: Generative Volumetric Primitives
    109856, -- 2305.14831 OD-NeRF: Efficient Training of On-the-Fly Dynamic Neural Radiance Fields
    109866, -- 2404.09531 Oblique-MERF: Revisiting and Improving MERF for Oblique Photography
    109868, -- 2408.06286 Mipmap-GS: Let Gaussians Deform with Scale-Specific Mipmap for Anti-Aliasing Ren
    109875, -- 2409.11536 Obfuscation Based Privacy Preserving Representations Are Recoverable Using Neigh
    109876, -- 2409.06104 LSE-NeRF: Learning Sensor Modeling Errors for Deblured Neural Radiance Fields wi
    109899, -- 2406.19811 EgoGaussian: Dynamic Scene Understanding from Egocentric Video with 3D Gaussian
    109907, -- 2412.03315 Geometry-Guided Cross-View Diffusion for One-to-Many Cross-View Image Synthesis
    109916, -- 2406.04343 Flash3D: Feed-Forward Generalisable 3D Scene Reconstruction from a Single Image
    109918, -- 2502.10827 E-3DGS: Event-Based Novel View Rendering of Large-Scale Scenes Using 3D Gaussian
    112184, -- 2509.18497 Differentiable Light Transport with Gaussian Surfels via Adapted Radiosity for E
    112200, -- 2505.18805 Auto Hair Card Extraction for Smooth Hair with Differentiable Rendering
    112219, -- 2511.21697 Detail Enhanced Gaussian Splatting for Large-Scale Volumetric Capture
    112223, -- 2509.18948 One-shot Embroidery Customization via Contrastive LoRA Modulation
    112227, -- 2509.01837 PractiLight: Practical Light Control Using Foundational Diffusion Models
    112241, -- 2510.02617 Input-Aware Sparse Attention for Real-Time Co-Speech Video Generation
    112275, -- 2409.12771 Spectral-GS: Taming 3D Gaussian Splatting with Spectral Entropy
    112281, -- 2604.02586 TrackerSplat: Exploiting Point Tracking for Fast and Robust Dynamic 3D Gaussians
    112289, -- 2510.08394 Spectral Prefiltering of Neural Fields
    112313, -- 2509.25001 LVT: Large-Scale Scene Reconstruction via Local View Transformers
    112316, -- 2509.26599 DiffCamera: Arbitrary Refocusing on Images
    112317, -- 2512.20479 UTDesign: A Unified Framework for Stylized Text Editing and Generation in Graphi
    112319, -- 2506.19139 SOF: Sorted Opacity Fields for Fast Unbounded Surface Reconstruction
    112334, -- 2505.23740 LayerPeeler: Autoregressive Peeling for Layer-wise Image Vectorization
    112346, -- 2509.19979 CamPVG: Camera-Controlled Panoramic Video Generation with Epipolar-Aware Diffusi
    112349, -- 2509.18924 Audio Driven Universal Gaussian Head Avatars
    112364, -- 2510.05532 Teamwork: Collaborative Diffusion with Low-rank Coordination and Adaptation
    112414, -- 2407.05586 Dynamic Neural Radiance Field From Defocused Monocular Video
    112425, -- 2312.09063 Image Demoireing in RAW and sRGB Domains
    112463, -- 2305.15078 "UniINR: Event-guided Unified Rolling Shutter Correction, Deblurring, and Interp
    112467, -- 2407.10833 MoE-DiffIR: Task-customized Diffusion Priors for Universal Compressed Image Rest
    112472, -- 2407.13390 GeometrySticker: Enabling Ownership Claim of Recolorized Neural Radiance Fields
    112474, -- 2404.14409 CrossScore: A Multi-View Approach to Image Evaluation and Scoring
    112477, -- 2410.07901 Semi-Supervised Video Desnowing Network via Temporal Decoupling Experts and Dist
    112480, -- 2408.09347 S^3D-NeRF: Single-Shot Speech-Driven Neural Radiance Field for High Fidelity Tal
    112488, -- 2407.07735 Protecting NeRFs' Copyright via Plug-And-Play Watermarking Base Model
    112499, -- 2403.11909 RoGUENeRF: A Robust Geometry-Consistent Universal Enhancer for NeRF
    112505, -- 2410.17752 AdaDiffSR: Adaptive Region-aware Dynamic acceleration Diffusion Model for Real-W
    112506, -- 2408.10739 TrackNeRF: Bundle Adjusting NeRF from Sparse and Noisy Views via Feature Tracks
    112532, -- 2407.08221 GAURA: Generalizable Approach for Unified Restoration and Rendering of Arbitrary
    112537, -- 2401.10227 A Simple Latent Diffusion Approach for Panoptic Segmentation and Mask Inpainting
    112545, -- 2404.03613 Per-Gaussian Embedding-Based Deformation for Deformable 3D Gaussian Splatting
    112546, -- 2409.09605 DreamMover: Leveraging the Prior of Diffusion Models for Image Interpolation wit
    112557, -- 2305.15171 Diffusion-Generated Pseudo-Observations for High-Quality Sparse-View Reconstruct
    112570, -- 2402.00752 On the Error Analysis of 3D Gaussian Splatting and an Optimal Projection Strateg
    112578, -- 2405.12218 MVSGaussian: Fast Generalizable Gaussian Splatting Reconstruction from Multi-Vie
    112601, -- 2403.15530 Pixel-GS Density Control with Pixel-aware Gradient for 3D Gaussian Splatting
    112709, -- 2407.11347 I2-SLAM: Inverting Imaging Process for Robust Photorealistic Dense SLAM
    112712, -- 2408.02157 PanoFree: Tuning-Free Holistic Multi-view Image Generation with Cross-view Self-
    112741, -- 2406.00609 SuperGaussian: Repurposing Video Models for 3D Super Resolution
    112743, -- 2407.13592 MeshFeat: Multi-Resolution Features for Neural Fields on Meshes
    112744, -- 2409.09969 2S-ODIS: Two-Stage Omni-Directional Image Synthesis by Geometric Distortion Corr
    112763, -- 2408.07147 Controlling the World by Sleight of Hand
    112782, -- 2407.02174 BeNeRF:Neural Radiance Fields from a Single Blurry Image and Event Stream
    112797, -- 2311.02573 Group Testing for Accurate and Efficient Range-Based Near Neighbor Search for Pl
    112820, -- 2409.09756 MesonGS: Post-training Compression of 3D Gaussians via Efficient Attribute Trans
    112842, -- 2309.03244 EGIC: Enhanced Low-Bit-Rate Generative Image Compression Guided by Semantic Segm
    112850, -- 2403.11868 View-Consistent 3D Editing with Gaussian Splatting
    112853, -- 2403.10119 URS-NeRF: Unordered Rolling Shutter Bundle Adjustment for Neural Radiance Fields
    112862, -- 2407.08127 Prediction Exposes Your Face: Black-box Model Inversion via Prediction Alignment
    112863, -- 2409.18953 UniCal: Unified Neural Sensor Calibration
    112890, -- 2312.02362 "PointNeRF++: A multi-scale, point-based Neural Radiance Field"
    112911, -- 2311.18815 IMMA: Immunizing text-to-image Models against Malicious Adaptation
    112912, -- 2407.11962 Motion-Oriented Compositional Neural Radiance Fields for Monocular Dynamic Human
    112920, -- 2311.08843 Personalized Video Relighting With an At-Home Light Stage
    112927, -- 2401.07487 Robo-ABC: Affordance Generalization Beyond Categories via Semantic Correspondenc
    112951, -- 2312.14134 Diffusion Reward: Learning Rewards via Conditional Video Diffusion
    112960, -- 2410.19483 Content-Aware Radiance Fields: Aligning Model Complexity with Scene Intricacy Th
    112987, -- 2407.13185 KFD-NeRF: Rethinking Dynamic NeRF with Kalman Filter
    113001, -- 2407.15111 D4-VTON: Dynamic Semantics Disentangling for Differential Diffusion based Virtua
    113004, -- 2403.10004 ST-LDM: A Universal Framework for Text-Grounded Object Generation in Real Images
    113005, -- 2407.10267 RS-NeRF: Neural Radiance Fields from Rolling Shutter Images
    113017, -- 2409.14316 MVPGS: Excavating Multi-view Priors for Gaussian Splatting from Sparse Input Vie
    113026, -- 2407.12431 GLARE: Low Light Image Enhancement via Generative Latent Feature based Codebook
    113029, -- 2407.12676 CoSIGN: Few-Step Guidance of ConSIstency Model to Solve General INverse Problems
    113049, -- 2409.11718 Free-VSC: Free Semantics from Visual Foundation Models for Unsupervised Video Se
    113054, -- 2407.18500 Revisit Event Generation Model: Self-Supervised Learning of Event-to-Video Recon
    113060, -- 2403.19160 Within the Dynamic Context: Inertia-aware 3D Human Modeling with Pose Sequence
    113071, -- 2404.04908 Dual-Camera Smooth Zoom on Mobile Phones
    113092, -- 2402.14000 Real-time 3D-aware Portrait Editing from a Single Image
    113093, -- 2404.01241 StructLDM: Structured Latent Diffusion for 3D Human Generation
    113103, -- 2306.09124 DIFFender: Diffusion-Based Adversarial Defense against Patch Attacks
    113104, -- 2402.13729 Hybrid Video Diffusion Models with 2D Triplane and 3D Wavelet Representation
    113111, -- 2403.05808 Adaptive Multi-modal Fusion of Spatially Variant Kernel Refinement with Diffusio
    113130, -- 2407.10181 Multiscale Sliced Wasserstein Distances as Perceptual Color Difference Measures
    113166, -- 2410.00672 GMT: Enhancing Generalizable Neural Rendering via Geometry-Driven Multi-Referenc
    113232, -- 2404.10681 StyleCity: Large-Scale 3D Urban Scenes Stylization
    113234, -- 2312.11587 Relightable Neural Actor with Intrinsic Decomposition and Pose Control
    113244, -- 2405.18527 Task-Driven Uncertainty Quantification in Inverse Problems via Conformal Predict
    113254, -- 2404.11593 IntrinsicAnything: Learning Diffusion Priors for Inverse Rendering Under Unknown
    113259, -- 2408.05533 UAV First-Person Viewers Are Radiance Field Learners
    113263, -- 2312.06285 Compensation Sampling for Improved Convergence in Diffusion Models
    113269, -- 2408.13922 COMPOSE: Comprehensive Portrait Shadow Editing
    113299, -- 2402.17986 PolyOculus: Simultaneous Multi-view Image-based Novel View Synthesis
    113300, -- 2403.13206 Depth-guided NeRF Training via Earth Mover’s Distance
    113344, -- 2410.17839 Few-shot NeRF by Adaptive Rendering Loss Regularization
    113365, -- 2404.03654 RaFE: Generative Radiance Fields Restoration
    113366, -- 2407.20928 UniProcessor: A Text-induced Unified Low-level Image Processor
    113409, -- 2407.03886 DSMix: Distortion-Induced Saliency Map Based Pre-training for No-Reference Image
    113423, -- 2409.07808 FedHide: Federated Learning by Hiding in the Neighbors
    113481, -- 2404.18929 DGE: Direct Gaussian 3D Editing by Consistent Multi-view Editing
    113506, -- 2404.05680 SphereHead: Stable 3D Full-head Synthesis with Spherical Tri-plane Representatio
    113526, -- 2407.21450 Forecasting Future Videos from Novel Views via Disentangled 3D Scene Representat
    113534, -- 2409.16709 Pose Guided Fine-Grained Sign Language Video Generation
    113540, -- 2403.05352 Enhancing Plausibility Evaluation for Generated Designs with Denoising Autoencod
    113548, -- 2407.08256 Adaptive Compressed Sensing with Diffusion-Based Posterior Sampling
    113579, -- 2407.18207 Geometry Fidelity for Spherical Images
    113623, -- 2407.10389 Boost Your NeRF: A Model-Agnostic Mixture of Experts Framework for High Quality
    113625, -- 2408.16235 LMT-GP: Combined Latent Mean-Teacher and Gaussian Process for Semi-supervised Lo
    113635, -- 2407.07249 Few-Shot Image Generation by Conditional Relaxing Diffusion Inversion
    113662, -- 2312.14579 Synthesizing Environment-Specific People in Photographs
    113712, -- 2312.08744 GOEmbed: Gradient Origin Embeddings for Representation Agnostic 3D Feature Learn
    113746, -- 2608.26794 Ring Forcing: Towards Precise Long-Term Memory for Autoregressive Video Diffusio
    114061, -- 2609.05738 RenderFormer-V2: Neural Rendering with Heterogeneous Scene Primitives
    114103, -- 2609.11929 SenseNova-U1.5: Towards Native Unified Visual Intelligence
    114287, -- 2609.15863 LynnReal-Omni: Native multi-modal Video Generation for Agentic Visual Workflows
    114374, -- 2407.03018 An Organism Starts with a Single Pix-Cell: A Neural Cellular Diffusion for High-
    114846, -- 2407.05428 Diffusion as Sound Propagation: Physics-inspired Model for Ultrasound Image Gene
    114847, -- 2403.08464 Diffusion Models with Implicit Guidance for Medical Anomaly Detection
    114878, -- 2406.00808 EchoNet-Synthetic: Privacy-preserving Video Generation for Safe Medical Data Sha
    114952, -- 2407.02918 Free-SurGS: SfM-Free 3D Gaussian Splatting for Surgical Scene Reconstruction
    114957, -- 2408.15217 Fundus2Video: Cross-Modal Angiography Video Generation from Static Fundus Photog
    114960, -- 2404.06128 Gaussian Pancakes: Geometrically-Regularized 3D Gaussian Splatting for Realistic
    115027, -- 2406.08282 Interpretable Representation Learning of Cardiac MRI via Attribute Regularizatio
    115167, -- 2407.02911 Non-Adversarial Learning: Vector-Quantized Common Latent Space for Multi-Sequenc
    115238, -- 2408.08616 Reference-free Axial Super-resolution of 3D Microscopy Images using Implicit Neu
    115295, -- 2404.17357 Simultaneous Tri-Modal Medical Image Fusion and Super-Resolution using Condition
    115418, -- 2410.00184 Volumetric Conditional Score-based Residual Diffusion Model for PET/MR Denoising
    115497, -- 2404.04878 CycleINR: Cycle Implicit Neural Representation for Arbitrary-Scale Volumetric Su
    115533, -- 2404.00676 OmniLocalRF: Omnidirectional Local Radiance Fields from Dynamic Videos
    115579, -- 2405.02066 WateRF: Robust Watermarks in Radiance Fields for Protection of Copyrights
    115589, -- 2403.08436 PFStorer: Personalized Face Restoration and Super-Resolution
    115593, -- 2402.17275 One-Shot Structure-Aware Stylized Image Synthesis
    115597, -- 2312.09250 Single Mesh Diffusion Models with Field Latents for Texture Generation
    115607, -- 2406.18524 MultiDiff: Consistent Novel View Synthesis from a Single Image
    115608, -- 2302.04871 In-N-Out: Faithful 3D GAN Inversion with Volumetric Decomposition for Face Editi
    115633, -- 2403.17188 LOTUS: Evasive and Resilient Backdoor Attacks through Sub-Partitioning
    115652, -- 2403.17000 Learning Spatial Adaptation and Temporal Coherence in Diffusion Models for Video
    115665, -- 2403.02265 DaReNeRF: Direction-aware Representation for Dynamic Scenes
    115693, -- 2312.15540 Amodal Completion via Progressive Mixed Context Diffusion
    115711, -- 2403.00939 G3DR: Generative 3D Reconstruction in ImageNet
    115726, -- 2403.07347 Frequency Decoupling for Motion Magnification via Multi-Level Isomorphic Archite
    115762, -- 2307.16897 DiVa-360: The Dynamic Visual Dataset for Immersive Neural Fields
    115768, -- 2405.07933 Authentic Hand Avatar from a Phone Scan via Universal Hand Model
    115779, -- 2212.03185 Rethinking the Objectives of Vector-Quantized Tokenizers for Image Synthesis
    115783, -- 2311.17119 Continuous Pose for Monocular Cameras in Neural Implicit Representation
    115797, -- 2303.13514 SAOR: Single-View Articulated Object Reconstruction
    115838, -- 2403.06205 S-DyRF: Reference-Based Stylized Radiance Fields for Dynamic Scenes
    115842, -- 2403.02981 Doubly Abductive Counterfactual Inference for Text-based Image Editing
    115859, -- 2403.02611 A Unified Framework for Microscopy Defocus Deblur with Multi-Pyramid Transformer
    115870, -- 2403.20018 SCINeRF: Neural Radiance Fields from a Snapshot Compressive Image
    115898, -- 2312.02190 Diffusion Handles Enabling 3D Edits for Diffusion Models by Lifting Activations
    115918, -- 2312.14985 UniHuman: A Unified Model For Editing Human Images in the Wild
    115931, -- 2406.04155 Improving Physics-Augmented Continuum Neural Radiance Field-Based Geometry-Agnos
    115933, -- 2404.01692 Beyond Image Super-Resolution for Image Recognition with Task-Driven Perceptual
    115984, -- 2404.01464 Data-Efficient Unsupervised Interpolation Without Any Intermediate Frame for 4D
    115988, -- 2403.19780 Mitigating Motion Blur in Neural Radiance Fields with Events and Frames
    116004, -- 2402.17200 Enhancing Quality of Compressed Images by Mitigating Enhancement Bias Towards Co
    116039, -- 2402.19215 Training Generative Image Super-Resolution Models by Wavelet-Domain Losses Enabl
    116041, -- 2403.08262 BiTT: Bi-directional Texture Reconstruction of Interacting Two Hands from a Sing
    116056, -- 2404.11884 Seeing Motion at Nighttime with an Event Camera
    116114, -- 2403.17537 NeRF-HuGS: Improved Neural Radiance Fields in Non-static Scenes Using Heuristics
    116143, -- 2312.00084 Can Protective Perturbation Safeguard Personal Data from Being Exploited by Stab
    116146, -- 2402.17364 Learning Dynamic Tetrahedra for High-Quality Talking Head Synthesis
    116150, -- 2404.06270 3D Geometry-Aware Deformable Gaussian Splatting for Dynamic View Synthesis
    116156, -- 2312.06739 SmartEdit: Exploring Complex Instruction-based Image Editing with Multimodal Lar
    116157, -- 2403.17502 SeNM-VAE: Semi-Supervised Noise Modeling with Hierarchical Variational Autoencod
    116161, -- 2404.00874 DiSR-NeRF: Diffusion-Guided View-Consistent Super-Resolution NeRF
    116194, -- 2311.17977 GaussianShader: 3D Gaussian Splatting with Shading Functions for Reflective Surf
    116216, -- 2312.04529 Diffusion Reflectance Map: Single-Image Stochastic Inverse Rendering of Illumina
    116220, -- 2404.04808 MemFlow: Optical Flow Estimation and Prediction with Memory
    116227, -- 2403.00459 Deformable One-shot Face Stylization via DINO Semantic Guidance
    116247, -- 2311.15672 HAVE-FUN: Human Avatar Reconstruction from Few-Shot Unconstrained Images
    116305, -- 2404.02742 LiDAR4D: Dynamic Neural Fields for Novel Space-time View LiDAR Synthesis
    116319, -- 2404.06692 Perception-Oriented Video Frame Interpolation via Asymmetric Blending
    116350, -- 2401.12592 RGBD Objects in the Wild: Scaling Real-World 3D Object Learning from RGB-D Video
    116353, -- 2403.02601 Low-Res Leads the Way: Improving Generalization for Super-Resolution by Self-Sup
    116360, -- 2404.00931 GOV-NeSF: Generalizable Open-Vocabulary Neural Semantic Fields
    116368, -- 2404.00485 DiffHuman: Probabilistic Photorealistic 3D Reconstruction of Humans
    116379, -- 2312.08886 Diffusion-based Blind Text Image Super-Resolution
    116390, -- 2406.10543 NeRFDeformer: NeRF Transformation from a Single View via 3D Scene Flows
    116448, -- 2312.07423 Holoported Characters: Real-time Free-viewpoint Rendering of Humans from Sparse
    116454, -- 2403.11222 SpikeNeRF: Learning Neural Radiance Fields from Continuous Spike Stream
    116463, -- 2405.04115 A Stealthy Wrongdoer: Feature-Oriented Reconstruction Attack against Split Learn
    116464, -- 2405.09882 DiffAM: Diffusion-based Adversarial Makeup Transfer for Facial Privacy Protectio
    116469, -- 2403.11397 Defense Against Adversarial Attacks on No-Reference Image Quality Models with Gr
    116472, -- 2312.12416 Prompting Hard or Hardly Prompting: Prompt Inversion for Text-to-Image Diffusion
    116474, -- 2402.17483 AlignMiF: Geometry-Aligned Multimodal Implicit Field for LiDAR-Camera Joint Synt
    116487, -- 2404.01050 Drag Your Noise: Interactive Point-based Editing via Diffusion Semantic Propagat
    116496, -- 2402.17065 Taming the Tail in Class-Conditional GANs: Knowledge Sharing via Unconditional T
    116505, -- 2406.09794 SuperSVG: Superpixel-based Scalable Vector Graphics Synthesis
    116510, -- 2403.12760 WaveFace: Authentic Face Restoration with Efficient Frequency Recovery
    116550, -- 2403.18186 Don't Look into the Dark: Latent Codes for Pluralistic Image Inpainting
    116560, -- 2404.12391 On the Content Bias in Frechet Video Distance
    116564, -- 2406.07480 Image Neural Field Diffusion Models
    116566, -- 2312.02221 Slice3D: Multi-Slice Occlusion-Revealing Single View 3D Reconstruction
    116581, -- 2404.05063 AUEditNet: Dual-Branch Facial Action Unit Intensity Manipulation with Implicit D
    116601, -- 2403.10103 DyBluRF: Dynamic Neural Radiance Fields from Blurry Monocular Video
    116602, -- 2401.02436 Compressed 3D Gaussian Splatting for Accelerated Novel View Synthesis
    116608, -- 2404.05661 Automatic Controllable Colorization via Imagination
    116621, -- 2406.05533 PAPR in Motion: Seamless Point-level 3D Scene Interpolation
    116695, -- 2312.03442 High-Quality Facial Geometry and Appearance Capture at Home
    116715, -- 2404.15882 Unexplored Faces of Robustness and Out-of-Distribution: Covariate Shifts in Envi
    116718, -- 2403.09632 Holo-Relighting: Controllable Volumetric Portrait Relighting from a Single Image
    116729, -- 2312.02232 HumanNeRF-SE: A Simple yet Effective Approach to Animate HumanNeRF with Diverse
    116744, -- 2402.18102 Passive Snapshot Coded Aperture Dual-Pixel RGB-D Imaging
    116758, -- 2403.18092 OCAI: Improving Optical Flow Estimation by Occlusion and Consistency Aware Inter
    116759, -- 2402.18929 Navigating Beyond Dropout: An Intriguing Solution towards Generalizable Image Su
    116775, -- 2405.04356 Diffusion-driven GAN Inversion for Multi-Modal Face Image Generation
    116780, -- 2406.06948 Neural Visibility Field for Uncertainty-Driven Active Mapping
    116786, -- 2312.05664 CoGS: Controllable Gaussian Splatting
    116804, -- 2405.09879 Generative Unlearning for Any Identity
    116807, -- 2403.16258 Laplacian-guided Entropy Model in Neural Codec with Blur-dissipated Synthesis
    116834, -- 2311.16728 Photo-SLAM: Real-time Simultaneous Localization and Photorealistic Mapping for M
    116850, -- 2401.17879 AEROBLADE: Training-Free Detection of Latent Diffusion Images Using Autoencoder
    116892, -- 2308.06699 Neural Super-Resolution for Real-time Rendering with Radiance Demodulation
    116910, -- 2404.00524 TexVocab: Texture Vocabulary-conditioned Human Avatars
    116963, -- 2403.10988 Boosting Flow-based Generative Super-Resolution Models via Learned Prior
    116981, -- 2402.18192 Misalignment-Robust Frequency Distribution Loss for Image Transformation
    116996, -- 2311.07044 L0-Sampler: An L0 Model Guided Volume Sampling for NeRF
    117027, -- 2404.14410 Guess The Unseen: Dynamic 3D Scene Reconstruction from Partial 2D Glimpses
    117032, -- 2404.03652 The More You See in 2D the More You Perceive in 3D
    117051, -- 2402.09944 Loopy-SLAM: Dense Neural SLAM with Loop Closures
    117091, -- 2404.00168 Multi-Level Neural Scene Graphs for Dynamic Urban Environments
    117095, -- 2403.16885 CVT-xRF: Contrastive In-Voxel Transformer for 3D Consistent Radiance Fields from
    117097, -- 2405.10037 Bilateral Event Mining and Complementary for Event Stream Super-Resolution
    117107, -- 2404.07474 G-NeRF: Geometry-enhanced Novel View Synthesis from Single-View Images
    117109, -- 2404.06350 Rolling Shutter Correction with Intermediate Distortion Flow Estimation
    117125, -- 2403.06375 FlowVQTalker: High-Quality Emotional Talking Face Generation through Normalizing
    117130, -- 2312.08071 Novel View Synthesis with View-Dependent Effects from a Single Image
    117170, -- 2404.01998 Specularity Factorization for Low-Light Enhancement
    117193, -- 2404.02788 GenN2N: Generative NeRF2NeRF Translation
    117195, -- 2405.14934 Universal Robustness via Median Randomized Smoothing for Real-World Super-Resolu
    117208, -- 2312.00075 Accelerating Neural Field Training via Soft Mining
    117211, -- 2303.17783 Uncertainty-Aware Source-Free Adaptive Image Super-Resolution with Wavelet Augme
    117212, -- 2406.03723 Gear-NeRF: Free-Viewpoint Rendering and Tracking with Motion-aware Spatio-Tempor
    117234, -- 2401.04608 EmoGen: Emotional Image Content Generation with Text-to-Image Diffusion Models
    117240, -- 2403.17460 Building Bridges across Spatial and Temporal Resolutions: Reference-Based Super-
    117255, -- 2501.01949 VideoLifter: Lifting Videos to 3D with Fast Hierarchical Stereo Alignment
    117273, -- 2601.12285 LegacyAvatars: Volumetric Face Avatars For Traditional Graphics Pipelines
    117274, -- 2505.10827 NeuSEditor: From Multi-View Images to Text-Guided Neural Surface Edits
    117275, -- 2603.04290 Gaussian Wardrobe: Compositional 3D Gaussian Avatars for Free-Form Virtual Try-o
    117284, -- 2505.16565 M2SVid: End-to-End Inpainting and Refinement for Monocular-to-Stereo Video Conve
    117289, -- 2506.06645 Parametric Gaussian Human Model: Generalizable Prior for Efficient and Realistic
    117294, -- 2511.12675 Appreciate the View: A Task-Aware Evaluation Framework for Novel View Synthesis
    117295, -- 2509.04145 Hyper Diffusion Avatars: Dynamic Human Avatar Generation using Network Weight Sp
    117305, -- 2504.12905 Matrix-free Second-order Optimization of Gaussian Splats with Residual Sampling
    117317, -- 2509.17329 SmokeSeer: 3D Gaussian Splatting for Smoke Removal and Scene Reconstruction
    117336, -- 2412.05771 Prism: Semi-Supervised Multi-View Stereo with Monocular Structure Priors
    117338, -- 2512.22771 Next Best View Selections for Semantic and Dynamic 3D Gaussian Splatting
    117353, -- 2412.13897 Data-Efficient Inference of Neural Fluid Fields via SciML Foundation Model
    117356, -- 2511.06810 ConeGS: Error-Guided Densification Using Pixel Cones for Improved Reconstruction
    117357, -- 2506.13348 TextureSplat: Per-Primitive Texture Mapping for Reflective Gaussian Splatting
    117360, -- 2602.06122 From Blurry to Believable: Enhancing Low-quality Talking Heads with 3D Generativ
    117371, -- 2512.15632 Towards Physically-Based Sky-Modeling For Image Based Lighting
    117375, -- 2606.31764 NURBS Splatting: A Unified Differentiable Rendering Framework for Vector Graphic
    117393, -- 2608.21893 A Scalable Vector Graphics Latent Space
    117405, -- 2607.22674 Text-based Tactile Graphics Generation for the Visually Impaired
    117410, -- 2605.18115 WinTok: A Win-Win Hybrid Tokenizer via Decomposing Visual Understanding and Gene
    117413, -- 2606.32036 PointSplat: Compact Gaussian Splatting via Human-Centric Prediction
    117414, -- 2608.20759 DiGS-Avatar: Single-Image Animatable 3D Human Reconstruction via UV-Space Diffus
    117424, -- 2605.11913 Vector Scaffolding: Inter-Scale Orchestration for Differentiable Image Vectoriza
    117430, -- 2604.20730 Render-in-the-Loop: Vector Graphics Generation via Visual Self-Feedback
    117438, -- 2606.31513 PRISM: Latent Composition Consistency for Single-Image Reflection Removal
    117446, -- 2606.31065 Diffusion-Based Material Regularization for Physics-Based Inverse Rendering
    117447, -- 2608.18215 LumiTokens: 3D Relighting via Token-Space Lighting Transformation
    117468, -- 2511.15022 Complex-Valued 2D Gaussian Representation for Computer-Generated Holography
    117478, -- 2607.20813 SubSplat: High-Resolution Pixel-aligned 3DGS via Sub-pixel Gaussian Reparameteri
    117482, -- 2512.05354 SplatPainter: Interactive Authoring of 3D Gaussians from 2D Edits via Test-Time
    117487, -- 2607.02712 Global Pose Control for Generative View Synthesis in Normalized Object Coordinat
    117488, -- 2608.20803 CubicSplat: Differentiable Vector Graphics via Error-Bounded Forward Relaxation
    117490, -- 2503.14736 HandSCS: Structural Coordinate Space for Animatable Hand Gaussian Splatting
    117500, -- 2607.00525 SPECSIA: Stylization Dataset for Novel-View Enhancement in Drawing-based 3D Anim
    117519, -- 2606.29379 DR-GS: Physically-Based Deformable and Relightable 2D Gaussians
    117520, -- 2607.07187 EditVerse3D: High-Quality 3D Object Editing with Region-Aware Learning
    117523, -- 2603.19834 Fourier Splatting: Generalized Fourier encoded primitives for scalable radiance
    117526, -- 2606.29794 UniTriSplat: A Unified 3D Gaussian Splatting Framework with Uniform Spherical Ra
    117527, -- 2608.21828 Towards Alias-Free 4D Gaussian Representations with Motion-Aware Filtering
    117545, -- 2607.29284 FillGS: Filling Observation Gaps in 4D Gaussian Splatting via Viewpoint-Time Sel
    117550, -- 2604.08500 Novel View Synthesis as Video Completion
    117555, -- 2608.23549 FixAnything: 3D-Consistent Rendering Refinement via Video Generative Priors
    117557, -- 2606.27584 CoIn: Comprehensive 2D-3D Inpainting with Gaussian Splatting Guidance
    117567, -- 2607.04256 AdaptiveSplat: Texture Aware Controllable 3D Gaussian Allocation for Feed-Forwar
    117568, -- 2607.00885 Improving Sparse-View 3DGS Generalization via Flat Minima Optimization
    117574, -- 2603.29192 Efficient Camera Pose Augmentation for View Generalization in Robotic Policy Lea
    117575, -- 2606.29782 Graph-GSReg: Leveraging 3D Scene Graphs for Gaussian Splatting Registration
    117577, -- 2603.11298 InstantHDR: Single-forward Gaussian Splatting for High Dynamic Range 3D Reconstr
    117580, -- 2512.16893 Instant Expressive Gaussian Head Avatars at Over 100 FPS
    117583, -- 2607.04661 Targeted Structure Completion for Sparse-View 3D Reconstruction in Autonomous Dr
    117588, -- 2603.24994 Relaxed Rigidity with Ray-based Grouping for Dynamic Gaussian Splatting
    117594, -- 2606.23212 Temporally Aware Densification for Dynamic 3D Gaussian Splatting
    117595, -- 2601.12770 One-Shot Feed-Forward 360° Animatable Avatar via Inpainted UV-Space Gaussian Mod
    117603, -- 2604.14302 Geometrically Consistent Multi-View Scene Generation from Freehand Sketches
    117605, -- 2606.30545 StereoGS: Sparse-View 3D Gaussian Splatting via Stereo Priors
    117609, -- 2603.21695 RefracGS: Novel View Synthesis Through Refractive Water Surfaces with 3D Gaussia
    117626, -- 2608.22344 Fast and Compact 3D Gaussian Splatting with Polarized Opacity Prior
    117635, -- 2608.26948 KISS-GS: 3D Gaussian Splatting Compression Kept Simple
    117640, -- 2605.04035 Large-Scale High-Quality 3D Gaussian Head Reconstruction from Multi-View Capture
    117644, -- 2604.02867 HairOrbit: Multi-view Aware 3D Hair Modeling from Single Portraits
    117646, -- 2512.17541 FLEG: Feed-Forward Language Embedded Gaussian Splatting from Any Views via Compa
    117648, -- 2606.24206 Inclusive Interactive Collisions for Multi-View Consistent Compositional 3D Gene
    117654, -- 2603.08997 SkipGS: Post-Densification Backward Skipping for Efficient 3DGS Training
    117657, -- 2606.24144 Geometry-Aware Style Transfer in 3D Gaussian Splatting
    117697, -- 2511.23191 GeoWorld: Providing Full-frame Geometry Features to Facilitate 3D Scene Generati
    117714, -- 2512.01204 TabletopGen: Tabletop Scene Generation and Interactive Simulation for Robotic Ma
    117715, -- 2603.07144 CanoVerse: 3D Object Scalable Canonicalization and Dataset for Generation and Po
    117720, -- 2603.22851 UniQueR: Unified Query-based Feedforward 3D Reconstruction
    117773, -- 2603.23071 PolarAPP: Beyond Polarization Demosaicking for Polarimetric Applications
    117794, -- 2607.18763 Posterior Samplings are Missing Modalities Generators for Medical Image Translat
    117806, -- 2606.26609 LogicIR: Logic Gate Networks for Image Restoration
    117813, -- 2511.18037 Hybrid Event–Frame Sensors: Modeling, Calibration, and Simulation
    117820, -- 2606.21910 Fidelity- and Perception-Aware Local Implicit Attention for Arbitrary-Scale Imag
    117826, -- 2608.05626 Dual-Output Multi-Exposure HDR Reconstruction via SDR Fusion and Gain Map Invers
    117890, -- 2603.19547 SeeClear: Reliable Transparent Object Depth Estimation via Generative Opacificat
    117898, -- 2603.06275 Spectral and Trajectory Regularization for Diffusion Transformer Super-Resolutio
    117900, -- 2603.14023 High-speed Imaging through Turbulence with Event-based Light Fields
    117926, -- 2603.23647 λSplit: Self-Supervised Content-Aware Spectral Unmixing for Fluorescence Microsc
    117932, -- 2606.26769 ResilPhase: Plug-and-Play Phase Mapping and Noise-Resilient Macro-Trajectory Ext
    117935, -- 2511.19985 SONIC: Spectral Optimization of Noise for Inpainting with Consistency
    117963, -- 2604.16993 Rule-VLN: Bridging Perception and Compliance via Semantic Reasoning and Geometri
    117969, -- 2606.32028 DVG-WM: Disentangled Video Generation Enables Efficient Embodied World Model for
    117977, -- 2606.31918 DriveWeaver: Point-Conditioned Video Inpainting for Controllable Vehicle Inserti
    118026, -- 2510.08713 Towards Unified World Models for Visual Navigation via Memory-Augmented Planning
    118035, -- 2603.09241 RAE-NWM: Navigation World Model in Dense Visual Representation Space
    118045, -- 2606.24101 NavWM: A Unified Navigation World Model for Foresight-Driven Planning
    118070, -- 2602.02002 UniDriveDreamer: A Single-Stage Multimodal World Model for Autonomous Driving
    118103, -- 2608.26190 Predicting Consequences and Reinforcing Navigation Policies with Latent World Mo
    118114, -- 2607.04484 TrustCLIP: Learning Private Visual Features via Adversarial Reconstruction
    118136, -- 2607.14595 MagicPrompt: Ultra-Lightweight Prompt Tuning for Video Generation
    118386, -- 2602.03342 Tiled Prompts: Overcoming Prompt Misguidance in Image and Video Super-Resolution
    118392, -- 2607.02421 Wavelet-Guided Semantic Signal Compensation for Inversion-Free Image Editing
    118396, -- 2607.22924 Layering Virtual Try-On
    118409, -- 2606.25907 In-context Region-based Drag: Drag Any Region to Any Shape
    118410, -- 2606.30849 SyncCache: Exploiting Asymmetric Dynamics for Fast Audio-Driven Portrait Animati
    118413, -- 2607.14976 From Draft to Draft-Free: One-Step Video Object Removal via Privileged Distillat
    118414, -- 2607.03770 Self-Improving Diffusion Classifiers with Minority Preference Optimization
    118416, -- 2607.10800 h-Flow: Flexible Flow-based Image Editing via Doob's h-Transform
    118417, -- 2606.31323 Accelerated Likelihood Maximization for Diffusion-based Versatile Content Genera
    118422, -- 2603.08090 DSH-Bench: A Difficulty- and Scenario-Aware Benchmark with Hierarchical Subject
    118435, -- 2603.24198 RefReward-SR: LR-Conditioned Reward Modeling for Preference-Aligned Super-Resolu
    118439, -- 2607.12539 DiTailed: Ensuring Visual Object Consistency in Text-Image-to-Image Flow Matchin
    118440, -- 2607.06440 PIPBench: A Profile-Inclusive Framework for Personalized Image Generation Evalua
    118443, -- 2606.31026 OTCache: Optimal Transport for Geometry-Aware Caching in Diffusion Models
    118445, -- 2607.22231 TRaM-VSR: Importance-Aware Token Routing and Merging for One-Step Diffusion Vide
    118446, -- 2606.28094 OSOR: One-Step Diffusion Inpainting for Effect-Aware Object Removal
    118452, -- 2607.00987 AVSR-Diff: Scale-Agnostic Diffusion Priors for Temporally Consistent Arbitrary-S
    118456, -- 2603.23086 Policy-Based Tuning of Autoregressive Image Models with Instance- and Distributi
    118465, -- 2606.29319 FDM-MFVT: Few-step Sampling Diffusion Model for Mask-Free Virtual Try-On
    118477, -- 2603.29697 FED-Bench: A Cross-Granular Benchmark for Disentangled Evaluation of Facial Expr
    118479, -- 2607.01499 Anti-Prompt: Image Protection against Text-Guided Image-to-Video Generation
    118480, -- 2607.19923 WearWow: Native 2K Multi-Garment Virtual Try-On via Adaptive Token Packing and P
    118481, -- 2606.31089 Anchoring on Reality: Breaking the Pseudo-Target Ceiling in Makeup Transfer
    118484, -- 2604.27958 TripVVT: A Large-Scale Triplet Dataset and a Coarse-Mask Baseline for In-the-Wil
    118490, -- 2602.14679 Universal Image Immunization against Diffusion-based Image Editing via Semantic
    118504, -- 2604.04646 Training-Free Refinement of Flow Matching with Divergence-based Sampling
    118506, -- 2607.26647 Anchoring and Steering Diffusion: Enhancing the Faithfulness of Text-to-Image Ge
    118511, -- 2603.22027 Tuning Real-World Image Restoration at Inference: A Test-Time Scaling Paradigm f
    118524, -- 2606.16188 TEASR: Training-Efficient Any-Step Diffusion Transformer for Real-World Image Su
    118527, -- 2606.28745 FreqOrtho-SR: Frequency-Guided Orthogonal Expert Learning for Real-World Image S
    118533, -- 2511.21415 DiverseVAR: Balancing Diversity and Quality of Next-Scale Visual Autoregressive
    118534, -- 2606.28785 Stochastic Optimal Control Sampling for Diffusion Inverse Problems
    118536, -- 2606.28417 DiffRGD: An Inference-Time Diffusion Guidance Through Riemannian Gradient Descen
    118543, -- 2605.22011 Rethinking Token Reduction for Diffusion Models via Output-Similarity-Awareness
    118544, -- 2510.05509 Be Tangential to Manifold: Discovering Riemannian Metric for Diffusion Models
    118558, -- 2608.10544 Flow Straight to Reality: Perceptually Consistent Flow Matching for Efficient Im
    118562, -- 2605.17980 Learning to Balance: Decoupled Siamese Diffusion Transformer for Reference-Based
    118575, -- 2607.01748 RTE-FM-Dehazer: Radiative Transfer Equation Inspired Flow Matching for Real-Worl
    118578, -- 2603.18466 Recolour What Matters: Region-Aware Colour Editing via Token-Level Diffusion
    118584, -- 2607.07119 ColorFM: An Optimization-to-Learning Framework for Color Transfer via Flow Match
    118590, -- 2607.04677 AnyStyle: A Single LoRA is Sufficient for Image-Guided Style Transfer
    118599, -- 2607.06609 D2PO: Optimizing Diffusion Samplers via Dynamic Preference
    118618, -- 2511.17038 DAPS++: Rethinking Diffusion Inverse Problems with Decoupled Posterior Annealing
    118620, -- 2604.19238 Allo{SR}2: Rectifying One-Step Super-Resolution to Stay Real via Allomorphic Gen
    118677, -- 2608.12262 Diagram-MMU: A Multi-Modal Benchmark for Scientific Diagrams
    118712, -- 2604.19193 How Far Are Video Models from True Multimodal Reasoning?
    118742, -- 2512.05635 Experts-Guided Unbalanced Optimal Transport for ISP Learning from Unpaired and/o
    118754, -- 2608.01977 SVGEval: A Vision-Grounded Framework for Perceptual-Quality Benchmarking and Eva
    118836, -- 2607.22087 FAIR: Feature-Augmented Implicit Regularization for AI-generated Fake Image Dete
    118893, -- 2606.29286 ASTAD: Asymmetric Style Transfer for Synthetic-to-Real Adaptation in Autonomous
    119059, -- 2603.16446 Unified Removal of Raindrops and Reflections: A New Benchmark and A Novel Pipeli
    119100, -- 2606.26763 Calibrated Harmonic Overlaid Implicit Neural Representations for Multi-Dimension
    119116, -- 2608.20748 Generating Multi-view Adversarial Examples for Visual Geometry Grounded Transfor
    119127, -- 2607.03277 Defending from GeoLocalization through Adversarial Road Trips
    119168, -- 2604.17211 EmbodiedHead: Real-Time Listening and Speaking Avatar for Conversational Agents
    119176, -- 2607.24591 CameraAnything: Refilming Videos with Arbitrary Camera Control
    119194, -- 2608.10500 DSAR: Dual-Stream Autoregressive Modeling of Temporal Cloth Dynamics for Photore
    119195, -- 2608.20107 BeyondMasks: Evaluating Causal and Physical Consistency in Video Object Removal
    119204, -- 2606.22718 Generative Relightable Avatars
    119205, -- 2603.24969 PASDiff: Physics-Aware Semantic Guidance for Joint Real-world Low-Light Face Enh
    119214, -- 2607.11199 DynEval: Holistic Evaluations of T2I Generative Models in the Wild
    119217, -- 2606.24336 TIGER: Taming Identity, Geometry, and Generative Priors for High-Quality Face Vi
    119231, -- 2607.19100 FlexiAvatar: Unified 3D Gaussian Human Avatars Under Arbitrary Body Visibility
    119237, -- 2607.08086 GRE-Diff: Gaussian Room Embeddings for Structured Layout Diffusion
    119257, -- 2606.24072 Fabric Image Demoiréing Benchmark from Synthesis to Restoration
    119267, -- 2512.17143 Pro-Pose: Unpaired Full-Body Portrait Synthesis via Canonical UV Maps
    119285, -- 2603.17546 ProGVC: Progressive-based Generative Video Compression via Auto-Regressive Conte
    119286, -- 2602.11117 HairWeaver: Few-Shot Photorealistic Hair Motion Synthesis with Sim-to-Real Guide
    119291, -- 2509.21541 ControlHair: Synergizing Physics Simulator and Video Diffusion for Controllable
    119295, -- 2606.31209 Long-term Traffic Simulation via Structured Autoregressive Modeling
    119308, -- 2603.17975 AHOY! Animatable Humans under Occlusion from YouTube Videos with Gaussian Splatt
    119320, -- 2607.16280 3D FaceShell: Attribute Transfer in 3D Face Avatars as a VLM Defense Mechanism
    119325, -- 2607.23861 Head Avatars with Dynamic Explicit Hair
    119328, -- 2511.14540 Interaction-Aware 4D Gaussian Splatting for Dynamic Hand-Object Interaction Reco
    119330, -- 2608.22102 Learning Implicit Constitutive Laws for Dynamic 3D Gaussian Splatting from Monoc
    119372, -- 2605.01896 Divide and Conquer: Decoupled Representation Alignment for Multimodal World Mode
    119382, -- 2607.02799 Conversational Human Audio-visual Talking Dialogue Generation
    119394, -- 2608.02990 EmbodiedVAE: Disentangled Video VAE for Efficient and Controllable Embodied Mani
    119398, -- 2606.01399 PAI-Studio: Cinematic Video Background Replacement with Camera-Aware Motion
    119410, -- 2511.12940 Recurrent Autoregressive Diffusion: Global Memory Meets Local Attention
    119454, -- 2509.17773 LoT-Pass: Long-term-robust Image Watermarking for Image to Video Generation
    119457, -- 2512.04483 DeRA: Decoupled Representation Alignment for Video Tokenization
    119478, -- 2603.07192 FastSTAR: Spatiotemporal Token Pruning for Efficient Autoregressive Video Synthe
    119493, -- 2606.28971 Self-Evolving Agentic Image Restoration via Deliberate Planning and Intuitive Ex
    119546, -- 2606.26615 TaskTok: Delving into Task Tokens for Task-driven Image Restoration
    119710, -- 2212.07275 PhoMoH: Implicit Photorealistic 3D Models of Human Heads
    119737, -- 2312.00532 DeepDR: Deep Structure-Aware RGB-D Inpainting for Diminished Reality
    119742, -- 2402.05532 NCRF: Neural Contact Radiance Fields for Free-Viewpoint Rendering of Hand-Object
    119745, -- 2403.19985 Stable Surface Regularization for Fast Few-Shot NeRF
    119752, -- 2401.06052 Fast High Dynamic Range Radiance Fields for Dynamic Scenes
    119761, -- 2401.09126 Objects With Lighting: A Real-World Dataset for Evaluating Reconstruction and Re
    119770, -- 2401.00405 Generalizing Single-View 3D Shape Retrieval to Occlusions and Unseen Objects
    119809, -- 2303.08096 MELON: NeRF with Unposed Images in SO(3)
    119812, -- 2403.14412 CombiNeRF: A Combination of Regularization Techniques for Few-Shot Neural Radian
    120046, -- 2408.06047 BooW-VTON: Boosting In-the-Wild Virtual Try-On via Mask-Free Pseudo Data Trainin
    120077, -- 2411.16785 MAGiC-SLAM: Multi-Agent Gaussian Globally Consistent SLAM
    120107, -- 2506.04453 Gradient Inversion Attacks on Parameter-Efficient Fine-Tuning
    120116, -- 2604.23010 GenAssets: Generating in-the-wild 3D Assets in Latent Space
    120186, -- 2406.02720 3D-HGS: 3D Half-Gaussian Splatting
    120277, -- 2506.05934 FADE: Frequency-Aware Diffusion Model Factorization for Video Editing
    120299, -- 2407.17929 GLASS: Guided Latent Slot Diffusion for Object-Centric Learning
    120309, -- 2501.00637 Flash-Split: 2D Reflection Removal with Flash Cues and Latent Diffusion Separati
    120313, -- 2412.01745 Horizon-GS: Unified 3D Gaussian Splatting for Large-Scale Aerial-to-Ground Scene
    120317, -- 2504.06815 SVG-IR: Spatially-Varying Gaussian Splatting for Inverse Rendering
    120540, -- 2506.16961 Reversing Flow for Image Restoration
    120604, -- 2411.17221 AIGV-Assessor: Benchmarking and Evaluating the Perceptual Quality of Text-to-Vid
    120607, -- 2506.16960 Visual-Instructed Degradation Diffusion for All-in-One Image Restoration
    120847, -- 2412.13401 MR. Illuminate: Zero-Shot Low-Light Image Enhancement with Diffusion Prior
    122594, -- 2609.34621 Does Native 3D Texture Generation Necessarily Require 3D Assets for Training?
    122775, -- 2605.16817 Adaptive Fused Prior Transfer for Controllable Generative Image Compression
    122900, -- 2610.10497 QuadTok: Quadtree Visual Tokenizer for Autoregressive Image Generation
    122968, -- 2610.06801 MC-Sparse: Deconstructing and Closing the Dense-Sparse Attention Gap in Diffusio
    123042, -- 2610.13947 Towards Physically Grounded Articulated 3D Assets: A Multi-Agent Pipeline and Be
    123180, -- 2610.11215 GATOR: Generative and Agentic 3D Object Reconstruction From Casual Images
    123318, -- 2103.13415 Mip-NeRF: A Multiscale Representation for Anti-Aliasing Neural Radiance Fields
    123320, -- 2104.06405 BARF: Bundle-Adjusting Neural Radiance Fields
    123392, -- 2610.12843 APEX: Asynchronous Prefix Denoising for Extreme Compression
    123408, -- 2604.01973 NearID: Identity Representation Learning via Near-identity Distractors
    123413, -- 2610.16759 Image Tokenizers Should Be Trained Between Images
    123601, -- 2610.22352 SUPRA-TEX: 3D Generation with Super-Aligned Texture
    123602, -- 2610.21095 Can World and Action Modeling Benefit Each Other under Unified Causal Training?
    123663, -- 2103.02597 Neural 3D Video Synthesis from Multi-view Video
    123924, -- 2203.11947 CM-GAN: Image Inpainting with Cascaded Modulation GAN and Object-Aware Training
    123927, -- 2103.14031 High-Fidelity Pluralistic Image Completion with Transformers
    123928, -- 2104.00845 Bridging Global Context Interactions for High-Fidelity Image Completion
    123930, -- 2307.00407 WavePaint: Resource-efficient Token-mixer for Self-supervised Inpainting
    123932, -- 2211.03700 Image Completion with Heterogeneously Filtered Spectral Hints
    123934, -- 2012.04567 Bayesian Image Reconstruction using Deep Generative Models
    123989, -- 2007.12142 PIPAL: a Large-Scale Image Quality Assessment Dataset for Perceptual Image Resto
    124081, -- 2402.00525 StopThePop: Sorted Gaussian Splatting for View-Consistent Real-time Rendering
    126607, -- 2607.03875 MACRO: Training-free Multi-plane Attention for Closeup Render Optimization
    127667, -- 2605.11508 LiBrA-Net: Lie-Algebraic Bilateral Affine Fields for Real-Time 4K Video Dehazing
    128266, -- 2605.19060 LiFT: Lifted Inter-slice Feature Trajectories for 3D Image Generation from 2D Ge
    130127, -- 2603.07357 Tunable Latent Generative Priors for Compressed Sensing and Inverse Problems
    131090, -- 2608.14070 InstructVVT: Instruction-Driven Video Virtual Try-On without Auxiliary Spatial P
    131327, -- 2305.17398 NeRO: Neural Geometry and BRDF Reconstruction of Reflective Objects from Multivi
    131522, -- 2205.14929 Neural Volumetric Object Selection
    131527, -- 2011.13961 D-NeRF: Neural Radiance Fields for Dynamic Scenes
    131619, -- 2106.07286 TimeLens: Event-based Video Frame Interpolation
    131626, -- 2610.40453 PhysInsert: Physically Plausible Object Insertion with Geometric Priors and Bidi
    131811 -- 2611.04870 PrimeSim: A Generalist World Model Simulator from Large-Scale Cross-Embodiment D
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'metrics curation 2026-11-10: cites the source paper but the title/abstract does not name the metric'
FROM lpips_citers_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING lpips_citers_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING lpips_citers_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- intersection-over-union-iou: 1001 links (title/abstract names the metric).
CREATE TEMP TABLE iou_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'intersection-over-union-iou'
  AND p.id IN (
    1003, -- 1712.00726 Cascade R-CNN: Delving into High Quality Object Detection
    1279, -- 1805.05239 The Effects of Image Pre- and Post-Processing, Wavelet Decomposition, and Local
    1404, -- 1807.09441 Two at Once: Enhancing Learning and Generalization Capacities via IBN-Net
    1407, -- 1807.10165 UNet++: A Nested U-Net Architecture for Medical Image Segmentation
    1660, -- 1811.11721 CCNet: Criss-Cross Attention for Semantic Segmentation
    1662, -- 1811.12296 Face Detection in the Operating Room: Comparison of State-of-the-art Methods and
    1846, -- 1902.09630 Generalized Intersection over Union: A Metric and A Loss for Bounding Box Regres
    1925, -- 1903.11816 FastFCN: Rethinking Dilated Convolution in the Backbone for Semantic Segmentatio
    1963, -- 1904.02701 Libra R-CNN: Towards Balanced Learning for Object Detection
    2352, -- 1907.06881 Cascade RetinaNet: Maintaining Consistency for Single-Stage Object Detection
    2565, -- 1909.08599 Feature Pyramid Encoding Network for Real-time Semantic Segmentation
    2823, -- 1911.07067 ResUNet++: An Advanced Architecture for Medical Image Segmentation
    2827, -- 1911.08287 Distance-IoU Loss: Faster and Better Learning for Bounding Box Regression
    3180, -- 2003.02437 Drone-based RGB-Infrared Cross-Modality Vehicle Detection via Uncertainty-Aware
    3396, -- 2004.10934 YOLOv4: Optimal Speed and Accuracy of Object Detection
    3527, -- 2005.02264 LandCover.ai: Dataset for Automatic Mapping of Buildings, Woodlands, Water and R
    3671, -- 2006.03677 Visual Transformers: Token-based Image Representation and Processing for Compute
    3772, -- 2006.11436 BEV-Seg: Bird's Eye View Semantic Segmentation Using Geometry and Semantic Point
    4016, -- 2008.05359 LogoDet-3K: A Large-Scale Image Dataset for Logo Detection
    4064, -- 2008.10831 CDeC-Net: Composite Deformable Cascade Network for Table Detection in Document I
    4249, -- 2010.01191 Semantic MapNet: Building Allocentric Semantic Maps and Representations from Ego
    4576, -- 2011.09157 Dense Contrastive Learning for Self-Supervised Visual Pre-Training
    4588, -- 2011.10043 Propagate Yourself: Exploring Pixel-Level Consistency for Unsupervised Visual Re
    4750, -- 2012.09164 Point Transformer
    4830, -- 2012.15840 Rethinking Semantic Segmentation from a Sequence-to-Sequence Perspective with Tr
    4890, -- 2101.04704 Boundary-Aware Segmentation Network for Mobile and Web Applications
    4904, -- 2101.06085 Deep Dual-resolution Networks for Real-time and Accurate Semantic Segmentation o
    4930, -- 2101.09433 A Pressure Ulcer Care System For Remote Medical Assistance: Residual U-Net with
    5053, -- 2102.08643 Temporal Memory Attention for Video Semantic Segmentation
    5155, -- 2103.04233 GANav: Efficient Terrain Segmentation for Robot Navigation in Unstructured Outdo
    5175, -- 2103.06255 Involution: Inverting the Inherence of Convolution for Visual Recognition
    5269, -- 2103.13413 Vision Transformers for Dense Prediction
    5279, -- 2103.14030 Swin Transformer: Hierarchical Vision Transformer using Shifted Windows
    5642, -- 2105.01883 RepMLP: Re-parameterizing Convolutions into Fully-connected Layers for Image Rec
    5826, -- 2105.15203 SegFormer: Simple and Efficient Design for Semantic Segmentation with Transforme
    6038, -- 2106.09748 DeepLab2: A TensorFlow Library for Deep Labeling
    6112, -- 2106.13112 VOLO: Vision Outlooker for Visual Recognition
    6150, -- 2106.15338 Probabilistic Attention for Interactive Segmentation
    6153, -- 2106.15828 Semantic Segmentation of Periocular Near-Infra-Red Eye Images Under Alcohol Effe
    6168, -- 2107.00652 CSWin Transformer: A General Vision Transformer Backbone with Cross-Shaped Windo
    6237, -- 2107.06278 Per-Pixel Classification is Not All You Need for Semantic Segmentation
    6270, -- 2107.08369 Flood Segmentation on Sentinel-1 SAR Imagery with Semi-Supervised Learning
    6800, -- 2110.02210 Mix3D: Out-of-Context Data Augmentation for 3D Scenes
    7004, -- 2110.09619 Further Generalizations of the Jaccard Index
    7121, -- 2111.00770 Dense Prediction with Attentive Feature Aggregation
    7228, -- 2111.08430 Code-free development and deployment of deep segmentation models for digital pat
    7261, -- 2111.10007 FBNetV5: Neural Architecture Search for Multiple Tasks in One Run
    7340, -- 2111.14887 DAFormer: Improving Network Architectures and Training Strategies for Domain-Ada
    7389, -- 2112.01527 Masked-attention Mask Transformer for Universal Image Segmentation
    7653, -- 2201.02107 HyperionSolarNet: Solar Panel Detection from Aerial Images
    7752, -- 2201.09450 UniFormer: Unifying Convolution and Self-attention for Visual Recognition
    8018, -- 2202.09741 Visual Attention Network
    8036, -- 2202.11094 GroupViT: Semantic Segmentation Emerges from Text Supervision
    8039, -- 2202.11221 Arbitrary Shape Text Detection using Transformers
    8042, -- 2202.11539 Self-Supervised Transformers for Unsupervised Object Discovery using Normalized
    8099, -- 2202.14030 Learning Semantic Segmentation from Multiple Datasets with Label Shifts
    8229, -- 2203.06717 Scaling Up Your Kernels to 31x31: Revisiting Large Kernel Design in CNNs
    8302, -- 2203.09035 HybridNets: End-to-End Perception Network
    8383, -- 2203.11926 Focal Modulation Networks
    8650, -- 2204.04654 Fashionformer: A simple, Effective and Unified Baseline for Human Fashion Segmen
    8721, -- 2204.07143 Neighborhood Attention Transformer
    8750, -- 2204.07962 An Extendable, Efficient and Effective Transformer-based Object Detector
    8765, -- 2204.08399 Unsupervised Contrastive Domain Adaptation for Semantic Segmentation
    8794, -- 2204.09636 Residual Mixture of Experts
    8818, -- 2204.10688 Spatiality-guided Transformer for 3D Dense Captioning on Point Clouds
    8864, -- 2204.13132 HRDA: Context-Aware High-Resolution Domain-Adaptive Semantic Segmentation
    9220, -- 2205.13542 BEVFusion: Multi-Task Multi-Sensor Fusion with Unified Bird's-Eye View Represent
    9383, -- 2206.02777 Mask DINO: Towards A Unified Transformer-based Framework for Object Detection an
    9589, -- 2206.11892 DDPM-CD: Denoising Diffusion Probabilistic Models as Feature Extractors for Chan
    9605, -- 2206.12571 CV 3315 Is All You Need : Semantic Segmentation Competition
    9701, -- 2207.02756 STVGFormer: Spatio-Temporal Video Grounding with Static-Dynamic Cross-Modal Unde
    9727, -- 2207.04044 kMaX-DeepLab: k-means Mask Transformer
    9765, -- 2207.05501 Next-ViT: Next Generation Vision Transformer for Efficient Deployment in Realist
    9899, -- 2207.12576 WinoGAViL: Gamified Association Benchmark to Challenge Vision-and-Language Model
    9902, -- 2207.12691 CENet: Toward Concise and Efficient LiDAR Semantic Segmentation for Autonomous D
    10037, -- 2208.06366 BEiT v2: Masked Image Modeling with Vector-Quantized Visual Tokenizers
    10132, -- 2208.11821 Refine and Represent: Region-to-Object Representation Learning
    10214, -- 2209.01589 Consistent-Teacher: Towards Reducing Inconsistent Pseudo-targets in Semi-supervi
    10372, -- 2209.10471 Sample, Crop, Track: Self-Supervised Mobile 3D Object Detection for Urban Drivin
    10469, -- 2209.15001 Dilated Neighborhood Attention Transformer
    10520, -- 2210.00923 Masked Supervised Learning for Semantic Segmentation
    10550, -- 2210.01820 MOAT: Alternating Mobile Convolution and Attention Brings Strong Vision Models
    10652, -- 2210.04150 Open-Vocabulary Semantic Segmentation with Mask-adapted CLIP
    10686, -- 2210.05063 Improving Dense Contrastive Learning with Dense Negative Pairs
    10886, -- 2210.10175 Intra-Source Style Augmentation for Improved Domain Generalization
    10906, -- 2210.10615 A Unified View of Masked Image Modeling
    11297, -- 2211.05778 InternImage: Exploring Large-Scale Vision Foundation Models with Deformable Conv
    11512, -- 2211.11950 UpCycling: Semi-supervised 3D Object Detection without Sharing Raw-level Unlabel
    11522, -- 2211.12268 Out-of-Candidate Rectification for Weakly Supervised Semantic Segmentation
    11545, -- 2211.12735 Fast-iTPN: Integrally Pre-Trained Transformer Pyramid Network with Token Migrati
    11644, -- 2211.14813 SegCLIP: Patch Aggregation with Learnable Centers for Open-Vocabulary Semantic S
    11694, -- 2211.16312 PLA: Language-Driven Open-Vocabulary 3D Scene Understanding
    11779, -- 2212.01322 MIC: Masked Image Consistency for Context-Enhanced Domain Adaptation
    11864, -- 2212.04245 Domain generalization of 3D semantic segmentation in autonomous driving
    11933, -- 2212.06137 NMS Strikes Back
    12194, -- 2212.11696 Reversible Column Networks
    12255, -- 2212.14532 Scale-MAE: A Scale-Aware Masked Autoencoder for Multiscale Geospatial Representa
    12385, -- 2301.04926 CLIP2Scene: Towards Label-efficient 3D Scene Understanding by CLIP
    13030, -- 2302.05666 Jaccard Metric Losses: Optimizing the Jaccard Index with Soft Labels
    13389, -- 2302.14746 Mask3D: Pre-training 2D Vision Transformers by Learning Masked 3D Priors
    13432, -- 2303.00971 Disentangling Orthogonal Planes for Indoor Panoramic Room Layout Estimation with
    13479, -- 2303.02153 Unleashing Text-to-Image Diffusion Models for Visual Perception
    13508, -- 2303.02936 UniHCP: A Unified Model for Human-Centric Perceptions
    13580, -- 2303.04803 Open-Vocabulary Panoptic Segmentation with Text-to-Image Diffusion Models
    13589, -- 2303.04995 Text-Visual Prompting for Efficient 2D Temporal Video Grounding
    13640, -- 2303.05970 Exploring Recurrent Long-term Temporal Fusion for Multi-view 3D Perception
    13742, -- 2303.07806 USAGE: A Unified Seed Area Generation Paradigm for Weakly Supervised Semantic Se
    13812, -- 2303.09083 Focus on Your Target: A Dual Teacher-Student Framework for Domain-adaptive Seman
    13922, -- 2303.11203 Less is More: Reducing Task and Model Complexity for 3D Point Cloud Semantic Seg
    13951, -- 2303.11546 Texture Learning Domain Randomization for Domain Generalized Segmentation
    13962, -- 2303.11681 DiffuMask: Synthesizing Images with Pixel-level Annotations for Semantic Segment
    14024, -- 2303.12766 Spherical Transformer for LiDAR-based 3D Recognition
    14207, -- 2303.15693 Large-scale pretraining on pathological images for fine-tuning of small patholog
    14288, -- 2303.17152 Mixed Autoencoder for Self-supervised Visual Representation Learning
    14294, -- 2303.17225 FreeSeg: Unified, Universal and Open-Vocabulary Image Segmentation
    14307, -- 2303.17559 DDP: Diffusion Model for Dense Visual Prediction
    14334, -- 2303.17859 MapFormer: Boosting Change Detection by Using Pre-change Information
    14362, -- 2304.00176 Improving extreme weather events detection with light-weight neural networks
    14584, -- 2304.04704 Prompt Pre-Training with Twenty-Thousand Classes for Open-Vocabulary Visual Reco
    14595, -- 2304.04909 SATR: Zero-Shot Semantic Segmentation of 3D Shapes
    14608, -- 2304.05152 PP-MobileSeg: Explore the Fast and Accurate Semantic Segmentation Model on Mobil
    14696, -- 2304.06906 Swin3D: A Pretrained Transformer Backbone for 3D Indoor Scene Understanding
    14724, -- 2304.07750 GeoMultiTaskNet: remote sensing unsupervised domain adaptation using geographica
    14768, -- 2304.08965 PointDC:Unsupervised Semantic Segmentation of 3D Point Clouds via Cross-modal Di
    14789, -- 2304.09427 Boosting Semantic Segmentation with Semantic Boundaries
    14806, -- 2304.09801 MetaBEV: Solving Sensor Failures for BEV Detection and Map Segmentation
    14830, -- 2304.10179 SCoDA: Domain Adaptive Shape Completion for Real Scans
    14899, -- 2304.11705 Walking Your LiDOG: A Journey Through Multiple Domains for LiDAR Semantic Segmen
    15155, -- 2305.01698 DeepAqua: Self-Supervised Semantic Segmentation of Wetland Surface Water Extent
    15557, -- 2305.08462 Not All Pixels Are Equal: Learning Pixel Hardness for Semantic Segmentation
    15943, -- 2305.13310 Matcher: Segment Anything with One Shot Using All-Purpose Feature Matching
    16109, -- 2305.14637 Learning UI-to-Code Reverse Generator Using Visual Critic Without Rendering
    16880, -- 2306.01736 DaTaSeg: Taming a Universal Multi-Dataset Multi-Task Segmentation Model
    17093, -- 2306.04300 CorrMatch: Label Propagation via Correlation Matching for Semi-Supervised Semant
    17163, -- 2306.05238 SparseTrack: Multi-Object Tracking by Performing Scene Decomposition based on Ps
    17389, -- 2306.08045 Efficient 3D Semantic Segmentation with Superpoint Transformer
    17499, -- 2306.09347 Segment Any Point Cloud Sequences by Distilling Vision Foundation Models
    17692, -- 2306.12941 Towards Reliable Evaluation and Fast Training of Robust Semantic Segmentation Mo
    17725, -- 2306.13754 Zero-shot spatial layout conditioning for text-to-image diffusion models
    17847, -- 2306.16252 Land Cover Segmentation with Sparse Annotations from Sentinel-2 Imagery
    17953, -- 2307.00648 Intra- & Extra-Source Exemplar-Based Style Synthesis for Improved Domain General
    18043, -- 2307.02682 Zero-Shot Dense Video Captioning by Jointly Optimizing Text and Moment
    18267, -- 2307.07887 Handwritten and Printed Text Segmentation: A Signature Case Study
    18323, -- 2307.08579 Scale-Aware Modulation Meet Transformer
    18461, -- 2307.10782 See More and Know More: Zero-shot Point Cloud Segmentation via Multi-modal Visua
    18478, -- 2307.11035 Cascade-DETR: Delving into High-Quality Universal Object Detection
    18519, -- 2307.11654 FEDD -- Fair, Efficient, and Diverse Diffusion-based Lesion Segmentation and Mal
    18537, -- 2307.12018 GEM: Boost Simple Network for Glass Surface Segmentation via Vision Foundation M
    18683, -- 2307.14605 Clustering based Point Cloud Representation Learning for 3D Analysis
    18790, -- 2307.16617 FULLER: Unified Multi-modality Multi-task 3D Perception via Multi-level Gradient
    18861, -- 2308.01251 A Multi-Source Data Fusion-based Semantic Segmentation Model for Relic Landslide
    18906, -- 2308.01944 Dynamic Token-Pass Transformers for Semantic Segmentation
    18915, -- 2308.02097 Multi-interactive Feature Learning and a Full-time Multi-modality Benchmark for
    18933, -- 2308.02487 Convolutions Die Hard: Open-Vocabulary Segmentation with Single Frozen Convoluti
    19003, -- 2308.03594 FeatEnHancer: Enhancing Hierarchical Features for Object Detection and Beyond Un
    19039, -- 2308.04206 Exploring Transformers for Open-world Instance Segmentation
    19081, -- 2308.04829 MixReorg: Cross-Modal Mixed Patch Reorganization is a Good Mask Learner for Open
    19212, -- 2308.06879 Towards Open-Set Test-Time Adaptation Utilizing the Wisdom of Crowds in Entropy
    19268, -- 2308.07732 UniTR: A Unified and Efficient Multi-Modal Transformer for Bird's-Eye-View Repre
    19382, -- 2308.09281 Diverse Cotraining Makes Strong Semi-Supervised Segmentor
    19384, -- 2308.09294 Self-Calibrated Cross Attention Network for Few-Shot Segmentation
    19538, -- 2308.10481 ADNet: Lane Shape Prediction via Anchor Decomposition
    19634, -- 2308.11513 TrackFlow: Multi-Object Tracking with Normalizing Flows
    19665, -- 2308.11880 SUMMIT: Source-Free Adaptation of Uni-Modal Models to Multi-Modal Targets
    19699, -- 2308.12216 SG-Former: Self-guided Transformer with Evolving Token Reallocation
    19848, -- 2308.14286 Bridging Cross-task Protocol Inconsistency for Distillation in Dense Object Dete
    20015, -- 2309.00460 dacl10k: Benchmark for Semantic Bridge Damage Segmentation
    20067, -- 2309.01430 DAT++: Spatially Dynamic Vision Transformer with Deformable Attention
    20270, -- 2309.05192 Towards Viewpoint Robustness in Bird's Eye View Segmentation
    20353, -- 2309.06721 Dynamic Spectrum Mixer for Visual Recognition
    20590, -- 2309.10217 An Empirical Study of Attention Networks for Semantic Segmentation
    20693, -- 2309.11523 RMT: Retentive Networks Meet Vision Transformers
    20867, -- 2309.13881 Skip-Connected Neural Networks with Layout Graphs for Floor Plan Auto-Generation
    21032, -- 2309.16511 Toloka Visual Question Answering Benchmark
    21275, -- 2310.01641 You Only Look at Once for Real-time and Generic Multi-Task
    21746, -- 2310.06848 DeepTriNet: A Tri-Level Attention Based DeepLabv3+ Architecture for Semantic Seg
    21797, -- 2310.07510 Heuristic Vision Pre-Training with Self-Supervised and Supervised Multi-Task Lea
    21878, -- 2310.08370 UniPAD: A Universal Pre-training Paradigm for Autonomous Driving
    21923, -- 2310.08745 AcTExplore: Active Tactile Exploration of Unknown Objects
    21933, -- 2310.08854 Rank-DETR for High Quality Object Detection
    22140, -- 2310.11622 High-Resolution Building and Road Detection from Sentinel-2
    22438, -- 2310.15308 SAM-CLIP: Merging Vision Foundation Models towards Semantic and Spatial Understa
    23004, -- 2311.03355 SegGen: Supercharging Segmentation Models with Text2Mask and Mask2Img Synthesis
    23210, -- 2311.06956 SegReg: Segmenting OARs by Registering MR Images and CT Annotations
    23715, -- 2311.14405 OneFormer3D: One Transformer for Unified Point Cloud Segmentation
    23789, -- 2311.15599 UniRepLKNet: A Universal Perception Large-Kernel ConvNet for Audio, Video, Point
    23843, -- 2311.16241 SemiVL: Semi-Supervised Semantic Segmentation with Vision-Language Guidance
    23927, -- 2311.17132 TransNeXt: Robust Foveal Visual Perception for Vision Transformers
    24220, -- 2312.02021 Strong but simple: A Baseline for Domain Generalized Dense Perception by CLIP-ba
    24221, -- 2312.02051 TimeChat: A Time-sensitive Multimodal Large Language Model for Long Video Unders
    24414, -- 2312.04016 PartDistill: 3D Shape Part Segmentation by Vision-Language Model Distillation
    24423, -- 2312.04265 Stronger, Fewer, & Superior: Harnessing Vision Foundation Models for Domain Gene
    24442, -- 2312.04484 FRNet: Frustum-Range Networks for Scalable LiDAR Segmentation
    24596, -- 2312.06462 Cooperation Does Matter: Exploring Multi-Order Bilateral Relations for Audio-Vis
    24618, -- 2312.06660 EdgeSAM: Prompt-In-the-Loop Distillation for On-Device Deployment of SAM
    24691, -- 2312.07509 PEEKABOO: Interactive Video Generation via Masked-Diffusion
    24706, -- 2312.07661 CLIP as RNN: Segment Countless Visual Concepts without Training Endeavor
    24746, -- 2312.08548 EVP: Enhanced Visual Perception using Inverse Multi-Attentive Feature Refinement
    24859, -- 2312.10136 Gradient-based Parameter Selection for Efficient Fine-Tuning
    25096, -- 2312.14074 LiDAR-LLM: Exploring the Potential of Large Language Models for 3D LiDAR Underst
    25157, -- 2312.15084 Automated forest inventory: analysis of high-density airborne LiDAR point clouds
    25255, -- 2312.16794 ZONE: Zero-Shot Instruction-Guided Local Editing
    25326, -- 2312.17742 Learning Vision from Models Rivals Learning Vision from Data
    25401, -- 2401.01130 Joint Generative Modeling of Scene Graphs and Images via Diffusion Models
    25900, -- 2401.08815 Adversarial Supervision Makes Layout-to-Image Diffusion Models Thrive
    26087, -- 2401.11358 ANNA: A Deep Learning Based Dataset in Heterogeneous Traffic for Autonomous Vehi
    26112, -- 2401.11835 Unveiling the Human-like Similarities of Automatic Facial Expression Recognition
    26172, -- 2401.12513 Detecting and recognizing characters in Greek papyri with YOLOv8, DeiT and SimCL
    26317, -- 2401.14486 CloudTracks: A Dataset for Localizing Ship Tracks in Satellite Images of Clouds
    26352, -- 2401.15175 Kitchen Food Waste Image Segmentation and Classification for Compost Nutrients E
    26478, -- 2401.17023 MF-MOS: A Motion-Focused Model for Moving Object Segmentation
    26545, -- 2401.18064 Neural Locality Sensitive Hashing for Entity Blocking
    26646, -- 2402.01220 Delving into Decision-based Black-box Attacks on Semantic Segmentation
    26808, -- 2402.02985 Applying Unsupervised Semantic Segmentation to High-Resolution UAV Imagery for E
    26838, -- 2402.03290 InstanceDiffusion: Instance-level Control for Image Generation
    26977, -- 2402.04648 OV-NeRF: Open-vocabulary Neural Radiance Fields with Vision and Language Foundat
    27195, -- 2402.07633 Complete Instances Mining for Weakly Supervised Instance Segmentation
    28259, -- 2403.00762 Point Cloud Mamba: Point Cloud Learning via State Space Model
    28437, -- 2403.03145 Dual Mean-Teacher: An Unbiased Semi-Supervised Framework for Audio-Visual Source
    28586, -- 2403.05433 Part-aware Personalized Segment Anything Model for Patient-Specific Segmentation
    28714, -- 2403.07392 ViT-CoMer: Vision Transformer with Convolutional Multi-scale Feature Interaction
    28735, -- 2403.07746 Unleashing HyDRa: Hybrid Fusion, Depth Consistency and Radar for Unified 3D Perc
    29215, -- 2403.13803 Bounding Box Stability against Feature Dropout Reflects Detector Generalization
    29244, -- 2403.14291 Open-Vocabulary Attention Maps with Token Optimization for Semantic Segmentation
    29247, -- 2403.14354 LDTR: Transformer-based Lane Detection with Anchor-chain Representation
    29461, -- 2403.17369 CoDA: Instructive Chain-of-Domain Adaptation with Severity-Aware Visual Prompt T
    29477, -- 2403.17712 Invisible Gas Detection: An RGB-Thermal Cross Attention Network and A New Benchm
    29580, -- 2403.19046 LITA: Language Instructed Temporal-Localization Assistant
    29621, -- 2403.19589 TOD3Cap: Towards 3D Dense Captioning in Outdoor Scenes
    29652, -- 2403.19963 Efficient Modulation for Vision Networks
    29765, -- 2404.01065 T-Mamba: Frequency-Enhanced Gated Long-Range Dependency for Tooth 3D CBCT Segmen
    29899, -- 2404.02877 FlightScope: An Experimental Comparative Review of Aircraft Detection Algorithms
    29962, -- 2404.03650 OpenNeRF: Open Set 3D Neural Scene Segmentation with Pixel-Wise Features and Ren
    30157, -- 2404.06542 Training-Free Open-Vocabulary Segmentation with Offline Diffusion-Augmented Prot
    30253, -- 2404.07987 ControlNet++: Improving Conditional Controls with Efficient Consistency Feedback
    30312, -- 2404.08817 Revisiting Code Similarity Evaluation with Abstract Syntax Tree Edit Distance
    30437, -- 2404.10841 Gasformer: A Transformer-based Architecture for Segmenting Methane Emissions fro
    30529, -- 2404.12330 A Perspective on Deep Vision Performance with Standard Image and Video Codecs
    30770, -- 2404.16573 Multi-Scale Representations by Varying Window Attention for Semantic Segmentatio
    31133, -- 2405.04788 SemiCD-VL: Visual-Language Model Guidance Makes Better Semi-supervised Change De
    31300, -- 2405.08911 CLIP with Quality Captions: A Strong Pretraining for Vision Tasks
    31563, -- 2405.14174 Multi-Scale VMamba: Hierarchy in Hierarchy Visual State Space Model
    31586, -- 2405.14467 Segformer++: Efficient Token-Merging Strategies for High-Resolution Semantic Seg
    31800, -- 2405.16815 Image-level Regression for Uncertainty-aware Retinal Image Segmentation
    32183, -- 2406.00492 A Deep Learning Model for Coronary Artery Segmentation and Quantitative Stenosis
    33219, -- 2406.12225 The Solution for CVPR2024 Foundational Few-Shot Object Detection Challenge
    33299, -- 2406.13092 Multilingual Synopses of Movie Narratives: A Dataset for Vision-Language Story U
    34031, -- 2407.02182 Occlusion-Aware Seamless Segmentation
    34068, -- 2407.02685 Open Panoramic Segmentation
    34187, -- 2407.04249 FeatureSORT: Essential Features for Effective Tracking
    34257, -- 2407.05363 Multi-branch Collaborative Learning Network for 3D Visual Grounding
    34365, -- 2407.06597 TVR-Ranking: A Dataset for Ranked Video Moment Retrieval with Imprecise Queries
    34541, -- 2407.09033 Textual Query-Driven Mask Transformer for Domain Generalized Segmentation
    34597, -- 2407.09838 Background Adaptation with Residual Modeling for Exemplar-Free Class-Incremental
    34622, -- 2407.10159 RAPiD-Seg: Range-Aware Pointwise Distance Distribution Networks for 3D LiDAR Seg
    34723, -- 2407.11351 Learning Modality-agnostic Representation for Semantic Segmentation from Any Mod
    34829, -- 2407.12667 SG-NeRF: Neural Surface Reconstruction with Scene Graph Optimization
    34876, -- 2407.13036 ColorMAE: Exploring data-independent masking strategies in Masked AutoEncoders
    35152, -- 2407.17261 Embedding-Free Transformer with Inference Spatial Reduction for Efficient Semant
    35387, -- 2407.21721 Open-Vocabulary Audio-Visual Semantic Segmentation
    35450, -- 2408.00744 Collaborative Vision-Text Representation Optimizing for Open-Vocabulary Segmenta
    35623, -- 2408.03551 VPOcc: Exploiting Vanishing Point for Monocular 3D Semantic Occupancy Prediction
    35727, -- 2408.05692 A Novel Momentum-Based Deep Learning Techniques for Medical Image Classification
    35748, -- 2408.06110 RISurConv: Rotation Invariant Surface Attention-Augmented Convolutions for 3D Po
    35809, -- 2408.07040 KAN You See It? KANs and Sentinel for Effective and Explainable Crop Field Segme
    35963, -- 2408.09859 OccMamba: Semantic Occupancy Prediction with State Space Models
    35975, -- 2408.10123 Learning Precise Affordances from Egocentric Videos for Robotic Manipulation
    36021, -- 2408.10843 Detecting Wildfires on UAVs with Real-time Segmentation Trained by Larger Teache
    36147, -- 2408.12569 Sapiens: Foundation for Human Vision Models
    36539, -- 2409.02045 AllWeatherNet:Unified Image Enhancement for Autonomous Driving under Adverse Wea
    36733, -- 2409.06490 UAVDB: Trajectory-Guided Adaptable Bounding Boxes for UAV Detection
    36882, -- 2409.09323 Implicit Neural Representations with Fourier Kolmogorov-Arnold Networks
    36918, -- 2409.10016 AceParse: A Comprehensive Dataset with Diverse Structured Texts for Academic Lit
    36934, -- 2409.10262 Hydra-SGG: Hybrid Relation Assignment for One-stage Scene Graph Generation
    37325, -- 2409.17049 ControlCity: A Multimodal Diffusion Model Based Approach for Accurate Geospatial
    37527, -- 2409.19987 OccRWKV: Rethinking Efficient 3D Semantic Occupancy Prediction with Linear Compl
    37651, -- 2410.01473 SinkSAM: A Monocular Depth-Guided SAM Framework for Automatic Sinkhole Segmentat
    37748, -- 2410.02323 RESSCAL3D++: Joint Acquisition and Semantic Segmentation of 3D Point Clouds
    37761, -- 2410.02458 MedVisionLlama: Leveraging Pre-Trained Large Language Model Layers to Enhance Me
    37874, -- 2410.03478 VEDIT: Latent Prediction Architecture For Procedural Video Representation Learni
    38248, -- 2410.08049 Scaling Up Your Kernels: Large Kernel Design in ConvNets towards Universal Repre
    38430, -- 2410.10429 DOME: Taming Diffusion Model into High-Fidelity Controllable Occupancy World Mod
    38512, -- 2410.11187 Multiview Scene Graph
    38580, -- 2410.12075 WeatherDG: LLM-assisted Diffusion Model for Procedural Weather Generation in Dom
    38703, -- 2410.13383 Railway LiDAR semantic segmentation based on intelligent semi-automated data ann
    38714, -- 2410.13571 DriveDreamer4D: World Models Are Effective Data Machines for 4D Driving Scene Re
    38847, -- 2410.14987 SeaS: Few-shot Industrial Anomaly Image Generation with Separation and Sharing F
    39069, -- 2410.18084 DynamicCity: Large-Scale 4D Occupancy Generation from Dynamic Scenes
    39142, -- 2410.18923 SegLLM: Multi-round Reasoning Segmentation
    39456, -- 2410.24139 COSNet: A Novel Semantic Segmentation Network using Enhanced Boundaries in Clutt
    39922, -- 2411.07725 ALOcc: Adaptive Lifting-based 3D Semantic Occupancy and Cost Volume-based Flow P
    39993, -- 2411.09219 Harnessing Vision Foundation Models for High-Performance, Training-Free Open Voc
    40028, -- 2411.10086 CorrCLIP: Reconstructing Correlations in CLIP with Off-the-Shelf Foundation Mode
    40044, -- 2411.10332 Number it: Temporal Grounding Videos like Flipping Manga
    40100, -- 2411.11285 Zero-Shot Automatic Annotation and Instance Segmentation using LLM-Generated Dat
    40222, -- 2411.13550 Find Any Part in 3D
    40237, -- 2411.13836 CLIPer: Hierarchically Improving Spatial Representation of CLIP for Open-Vocabul
    40480, -- 2411.17000 SatVision-TOA: A Geospatial Foundation Model for Coarse-Resolution All-Sky Remot
    40775, -- 2412.00626 MambaNUT: Nighttime UAV Tracking via Mamba-based Adaptive Curriculum Learning
    40800, -- 2412.00965 Token Cropr: Faster ViTs for Quite a Few Tasks
    41026, -- 2412.03911 Multi-View Pose-Agnostic Change Localization with Zero Labels
    41094, -- 2412.04533 Mask-Adapter: The Devil is in the Masks for Open-Vocabulary Segmentation
    41415, -- 2412.08774 ProtoOcc: Accurate, Efficient 3D Occupancy Prediction Using Dual Branch Encoder-
    41549, -- 2412.10373 GaussianWorld: Gaussian World Model for Streaming 3D Occupancy Prediction
    41666, -- 2412.11890 SegMAN: Omni-scale Context Modeling with State Space Models and Local Attention
    41787, -- 2412.13193 GaussTR: Foundation Model-Aligned Gaussian Transformer for Self-Supervised 3D Sp
    42815, -- 2501.07783 Parameter-Inverted Image Pyramid Networks for Visual Perception and Multimodal U
    43468, -- 2501.19255 ContextFormer: Redefining Efficiency in Semantic Segmentation
    43643, -- 2502.02257 UNIP: Rethinking Pre-trained Attention Patterns for Infrared Semantic Segmentati
    43690, -- 2502.02955 ReachAgent: Enhancing Mobile Agent via Page Reaching and Operation
    43986, -- 2502.06997 Conditional diffusion model with spatial attention and latent embedding for medi
    44116, -- 2502.08769 Cluster and Predict Latents Patches for Improved Masked Image Modeling
    44573, -- 2502.13622 REFIND: Retrieval-Augmented Factuality Hallucination Detection in Large Language
    44736, -- 2502.15152 Confidence-Weighted Boundary-Aware Learning for Semi-Supervised Semantic Segment
    44798, -- 2502.15854 Enhancing Domain-Specific Retrieval-Augmented Generation: Synthetic Data Generat
    44801, -- 2502.15885 DOEI: Dual Optimization of Embedding Information for Attention-Enhanced Class Ac
    44854, -- 2502.16654 VPNeXt -- Rethinking Dense Decoding for Plain Vision Transformer
    45146, -- 2502.20087 OverLoCK: An Overview-first-Look-Closely-next ConvNet with Context-Mixing Dynami
    45299, -- 2503.01113 SCSegamba: Lightweight Structure-Aware Vision Mamba for Crack Segmentation in St
    45320, -- 2503.01342 UFO: A Unified Approach to Fine-grained Visual Perception via Open-ended Languag
    45358, -- 2503.01785 Visual-RFT: Visual Reinforcement Fine-Tuning
    45447, -- 2503.02910 LangGas: Introducing Language in Selective Zero-Shot Background Subtraction for
    45500, -- 2503.03689 DualDiff+: Dual-Branch Diffusion for High-Fidelity Video Generation with Reward
    45680, -- 2503.06307 ACAM-KD: Adaptive and Cooperative Attention Masking for Knowledge Distillation
    45829, -- 2503.07890 Can Generative Geospatial Diffusion Models Excel as Discriminative Geospatial Fo
    45882, -- 2503.08505 CFNet: Optimizing Remote Sensing Change Detection through Content-Aware Enhancem
    46063, -- 2503.10596 GroundingSuite: Measuring Complex Multi-Granular Pixel Grounding
    46387, -- 2503.15264 LEGION: Learning to Ground and Explain for Synthetic Image Detection
    46484, -- 2503.16399 SA-Occ: Satellite-Assisted 3D Occupancy Prediction in Real World
    46631, -- 2503.18445 Benchmarking Multi-modal Semantic Segmentation under Sensor Failures: Missing an
    46672, -- 2503.18931 CoMP: Continual Multimodal Pre-training for Vision Foundation Models
    46724, -- 2503.19653 OpenSDI: Spotting Diffusion-Generated Images in the Open World
    46740, -- 2503.19846 Attention IoU: Examining Biases in CelebA using Attention Maps
    46920, -- 2503.22262 Mono2Stereo: A Benchmark and Empirical Study for Stereo Conversion
    47155, -- 2504.01407 TimeSearch: Hierarchical Video Search with Spotlight and Reflection for Human-li
    47276, -- 2504.03193 Mamba as a Bridge: Where Vision Foundation Models Meet Vision Language Models fo
    47428, -- 2504.06220 Earth-Adapter: Bridge the Geospatial Domain Gaps with Mixture of Frequency Adapt
    47608, -- 2504.09518 3D CoCa: Contrastive Learners are 3D Captioners
    47783, -- 2504.12080 DC-SAM: In-Context Segment Anything in Images and Videos via Dual Consistency
    47844, -- 2504.12959 Rethinking Temporal Fusion with a Unified Gradient Descent View for 3D Semantic
    47943, -- 2504.14467 LGD: Leveraging Generative Descriptions for Zero-Shot Referring Image Segmentati
    48032, -- 2504.15681 Vidi: Large Multimodal Models for Video Understanding and Editing
    48337, -- 2505.01448 OpenAVS: Training-Free Open-Vocabulary Audio Visual Segmentation with Foundation
    48416, -- 2505.02829 LISAT: Language-Instructed Segmentation Assistant for Satellite Imagery
    49551, -- 2505.17769 Inference-Time Decomposition of Activations (ITDA): A Scalable Approach to Inter
    49578, -- 2505.18129 One RL to See Them All: Visual Triple Unified Reinforcement Learning
    49638, -- 2505.18660 So-Fake: Benchmarking and Explaining Social Media Image Forgery Detection
    49730, -- 2505.19422 LlamaSeg: Image Segmentation via Autoregressive Mask Generation
    49749, -- 2505.19569 What You Perceive Is What You Conceive: A Cognition-Inspired Framework for Open
    49774, -- 2505.19795 The Missing Point in Vision Transformers for Universal Image Segmentation
    50203, -- 2505.24164 Mixed-R1: Unified Reward Perspective For Reasoning Capability in Multimodal Larg
    50747, -- 2506.07080 FLAIR-HUB: Large-scale Multimodal Dataset for Land Cover and Crop Mapping
    51382, -- 2506.18807 PicoSAM2: Low-Latency Segmentation In-Sensor for Edge Vision Applications
    51557, -- 2506.22624 Seg-R1: Segmentation Can Be Surprisingly Simple with Reinforcement Learning
    51591, -- 2506.24039 Foundation Models for Zero-Shot Segmentation of Scientific Images without AI-Rea
    51772, -- 2507.06231 RSRefSeg 2: Decoupling Referring Remote Sensing Image Segmentation with Foundati
    51862, -- 2507.09144 $I^{2}$-World: Intra-Inter Tokenization for Efficient Dynamic 4D Scene Forecasti
    52051, -- 2507.17957 AFRDA: Attentive Feature Refinement for Domain Adaptive Semantic Segmentation
    52687, -- 2509.06784 P3-SAM: Native 3D Part Segmentation
    53423, -- 2510.04759 Progressive Gaussian Transformer with Anisotropy-aware Sampling for Open Vocabul
    53499, -- 2510.06582 Through the Perspective of LiDAR: A Feature-Enriched and Uncertainty-Aware Annot
    53581, -- 2510.13714 Dedelayed: Deleting remote inference delay via on-device correction
    53835, -- 2510.23607 Concerto: Joint 2D-3D Self-Supervised Learning Emerges Spatial Representations
    54230, -- 2511.13714 UnSAMv2: Self-Supervised Learning Enables Segment Anything at Any Granularity
    54655, -- 2512.06032 The SAM2-to-SAM3 Gap in the Segment Anything Model Family: Why Prompt-Based Expe
    54764, -- 2512.12799 DrivePI: Spatial-aware 4D MLLM for Unified Autonomous Driving Understanding, Per
    54771, -- 2512.12751 GenieDrive: Towards Physics-Aware Driving World Model with 4D Occupancy Guided V
    55106, -- 2601.02315 Prithvi-Complimentary Adaptive Fusion Encoder (CAFE): unlocking full-potential f
    55258, -- 2601.06496 3D CoCa v2: Contrastive Learners with Test-Time Search for Generalizable Spatial
    55270, -- 2601.08831 3AM: Segment Anything with Geometric Consistency in Videos
    55399, -- 2601.14251 LightOnOCR: A 1B End-to-End Multilingual Vision-Language Model for State-of-the-
    55537, -- 2601.19228 Towards Pixel-Level VLM Perception via Simple Points Prediction
    55653, -- 2601.22108 Value-Based Pre-Training with Downstream Feedback
    55739, -- 2602.01753 ObjEmbed: Towards Universal Multimodal Object Embeddings
    56415, -- 2603.01576 Cryo-Bench: Benchmarking Foundation Models for Cryosphere Applications
    56456, -- 2602.23496 SGDC: Structurally-Guided Dynamic Convolution for Medical Image Segmentation
    56929, -- 2603.22057 SpatialBoost: Enhancing Visual Representation through Language-Guided Reasoning
    56951, -- 2603.18795 Perceptio: Perception Enhanced Vision Language Models via Spatial Token Generati
    56979, -- 2603.22570 CanViT: Toward Active-Vision Foundation Models
    57018, -- 2603.23478 UniFunc3D: Unified Active Spatial-Temporal Grounding for 3D Functionality Segmen
    57093, -- 2603.28458 HISA: Efficient Hierarchical Indexing for Fine-Grained Sparse Attention
    57096, -- 2603.28480 INSID3: Training-Free In-Context Segmentation with DINOv3
    57289, -- 2604.05081 MedGemma 1.5 Technical Report
    57515, -- 2604.14147 ROSE: Retrieval-Oriented Segmentation Enhancement
    57620, -- 2604.17454 HSG: Hyperbolic Scene Graph
    57743, -- 2604.21681 Sapiens2
    57769, -- 2604.25256 AutoResearchBench: Benchmarking AI Agents on Complex Scientific Literature Disco
    57935, -- 2604.21321 FryNet: Dual-Stream Adversarial Fusion for Non-Destructive Frying Oil Oxidation
    58006, -- 2604.19233 Adaptive Slicing-Assisted Hyper Inference for Enhanced Small Object Detection in
    58030, -- 2604.18573 T-REN: Learning Text-Aligned Region Tokens Improves Dense Vision-Language Alignm
    58064, -- 2604.17451 SegTTA: Training-Free Test-Time Augmentation for Zero-Shot Medical Imaging Segme
    58185, -- 2604.13593 AVID: A Benchmark for Omni-Modal Audio-Visual Inconsistency Understanding via Ag
    58203, -- 2604.12918 Radar-Camera BEV Multi-Task Learning with Cross-Task Attention Bridge for Joint
    58293, -- 2601.09211 Affostruction: 3D Affordance Grounding with Generative Reconstruction
    58320, -- 2604.10210 A3-FPN: Asymptotic Content-Aware Pyramid Attention Network for Dense Visual Pred
    58356, -- 2604.08956 Low-Data Supervised Adaptation Outperforms Prompting for Cloud Segmentation Unde
    58455, -- 2604.05718 MPM: Mutual Pair Merging for Efficient Vision Transformers
    58586, -- 2604.02593 Moondream Segmentation: From Words to Masks
    58602, -- 2604.02252 SPAR: Single-Pass Any-Resolution ViT for Open-vocabulary Segmentation
    58608, -- 2604.02032 IndoorCrowd: A Multi-Scene Dataset for Human Detection, Segmentation, and Tracki
    58613, -- 2604.01766 FSKD: Monocular Forest Structure Inference via LiDAR-to-RGBI Knowledge Distillat
    58676, -- 2604.00609 TALENT: Target-aware Efficient Tuning for Referring Image Segmentation
    58701, -- 2603.29245 Monocular Building Height Estimation from PhiSat-2 Imagery: Dataset and Method
    58775, -- 2603.28120 MedLoc-R1: Performance-Aware Curriculum Reward Scheduling for GRPO-Based Medical
    58813, -- 2603.27101 PRUE: A Practical Recipe for Field Boundary Segmentation at Scale
    58836, -- 2604.09648 TRACE: Thermal Recognition Attentive-Framework for CO2 Emissions from Livestock
    58997, -- 2603.22872 ForeSea: AI Forensic Search with Multi-modal Queries for Video Surveillance
    59000, -- 2603.22841 UAV-DETR: DETR for Anti-Drone Target Detection
    59005, -- 2508.03643 Uni3R: Unified 3D Reconstruction and Semantic Understanding via Generalizable Ga
    59008, -- 2603.22518 High Resolution Flood Extent Detection Using Deep Learning with Random Forest De
    59118, -- 2603.19538 MoCA3D: Monocular 3D Bounding Box Prediction in the Image Plane
    59140, -- 2603.18892 MultihopSpatial: Multi-hop Compositional Spatial Reasoning Benchmark for Vision-
    59241, -- 2603.17056 DesertFormer: Transformer-Based Semantic Segmentation for Off-Road Desert Terrai
    59367, -- 2603.12718 The COTe score: A decomposable framework for evaluating Document Layout Analysis
    59430, -- 2603.13941 Bidirectional Cross-Attention Fusion of High-Res RGB and Low-Res HSI for Multimo
    59482, -- 2603.12759 SAP: Segment Any 4K Panorama
    59781, -- 2603.06210 VG3S: Visual Geometry Grounded Gaussian Splatting for Semantic Occupancy Predict
    60635, -- 2602.14276 Moving Beyond Sparse Grounding with Complete Screen Parsing Supervision
    60776, -- 2602.11730 STVG-R1: Incentivizing Instance-Level Reasoning and Grounding in Videos via Rein
    60976, -- 2602.08784 GaussianCaR: Gaussian Splatting for Efficient Camera-Radar Fusion
    61034, -- 2602.13287 COOPERTRIM: Adaptive Data Selection for Uncertainty-Aware Cooperative Perception
    61066, -- 2602.06965 MedMO: Grounding and Understanding Multimodal Large Language Model for Medical I
    61094, -- 2602.06507 FloorplanVLM: A Vision-Language Model for Floorplan Vectorization
    61482, -- 2602.01599 The Multiple Ticket Hypothesis: Random Sparse Subnetworks Suffice for RLVR
    61572, -- 2602.07017 XAI-CLIP: ROI-Guided Perturbation Framework for Explainable Medical Image Segmen
    61633, -- 2602.00484 GTATrack: Winner Solution to SoccerTrack 2025 with Deep-EIoU and Global Tracklet
    61984, -- 2601.19287 Understanding Dominant Themes in Reviewing Agentic AI-authored Code
    62348, -- 2601.13052 GridNet-HD: A High-Resolution Multi-Modal Dataset for LiDAR-Image Fusion on Powe
    62421, -- 2601.11310 Context-Aware Semantic Segmentation via Stage-Wise Attention
    62568, -- 2601.08205 FUME: Fused Unified Multi-Gas Emission Network for Livestock Rumen Acidosis Dete
    62719, -- 2601.05937 Performance of a Deep Learning-Based Segmentation Model for Pancreatic Tumors on
    62823, -- 2601.04497 Vision-Language Agents for Interactive Forest Change Analysis
    62913, -- 2601.03431 WeedRepFormer: Reparameterizable Vision Transformers for Real-Time Waterhemp Seg
    63056, -- 2601.01483 Unified Generation and Self-Verification for Vision-Language Models via Advantag
    63240, -- 2601.06067 HyperTopo-Adapters: Geometry- and Topology-Aware Segmentation of Leaf Lesions on
    63606, -- 2512.15512 VAAS: Vision-Attention Anomaly Scoring for Image Manipulation Detection in Digit
    63903, -- 2512.09251 GLACIA: Instance-Aware Positional Reasoning for Glacial Lake Segmentation via Mu
    63949, -- 2512.11884 Generalization vs. Specialization: Evaluating Segment Anything Model (SAM3) Zero
    64074, -- 2512.05663 LeAD-M3D: Leveraging Asymmetric Distillation for Real-time Monocular 3D Detectio
    64213, -- 2512.02660 Spatially-Grounded Document Retrieval via Patch-to-Region Relevance Propagation
    64430, -- 2511.22354 LLM-Based Generalizable Hierarchical Task Planning and Execution for Heterogeneo
    64436, -- 2511.22172 Guiding the Inner Eye: A Framework for Hierarchical and Flexible Visual Grounded
    64471, -- 2511.21375 Thinking With Bounding Boxes: Enhancing Spatio-Temporal Video Grounding via Rein
    64587, -- 2511.19704 RADSeg: Unleashing Parameter and Compute Efficient Zero-Shot Open-Vocabulary Seg
    64628, -- 2511.19529 Vidi2: Large Multimodal Models for Video Understanding and Creation
    64641, -- 2511.18680 Inverse Rendering for High-Genus Surface Meshes from Multi-View Images
    64697, -- 2511.18192 ARIAL: An Agentic Framework for Document VQA with Precise Answer Localization
    64898, -- 2511.14019 RISE: Single Static Radar-based Indoor Scene Understanding
    65197, -- 2511.11659 A Method for Identifying Farmland System Habitat Types Based on the Dynamic-Weig
    65260, -- 2511.06456 EIDSeg: A Pixel-Level Semantic Segmentation Dataset for Post-Earthquake Damage A
    65447, -- 2511.02064 MCHex: Marching Cubes Based Adaptive Hexahedral Mesh Generation with Guaranteed
    65452, -- 2511.01990 Assessing the value of Geo-Foundational Models for Flood Inundation Mapping: Ben
    65519, -- 2511.00981 VesSAM: Efficient Multi-Prompting for Segmenting Complex Vessel
    65657, -- 2510.25990 Fine-tuning Segment Anything for Real-Time Tumor Tracking in Cine-MRI
    65678, -- 2511.00073 Habitat and Land Cover Change Detection in Alpine Protected Areas: A Comparison
    65798, -- 2510.23444 FRBNet: Revisiting Low-Light Vision through Frequency-Domain Radial Basis Networ
    66190, -- 2510.16854 ArmFormer: Lightweight Transformer Architecture for Real-Time Multi-Class Weapon
    66224, -- 2510.21782 Promptable Fire Segmentation: Unleashing SAM2's Potential for Real-Time Mobile D
    66261, -- 2510.15362 RankSEG-RMA: An Efficient Segmentation Algorithm via Reciprocal Moment Approxima
    66538, -- 2510.11567 A Framework for Low-Effort Training Data Generation for Urban Semantic Segmentat
    66893, -- 2510.05617 InstaGeo: Compute-Efficient Geospatial Machine Learning from Data to Deployment
    67242, -- 2510.00416 Domain-Specialized Interactive Segmentation Framework for Meningioma Radiotherap
    67753, -- 2509.22909 TY-RIST: Tactical YOLO Tricks for Real-time Infrared Small Target Detection
    67778, -- 2509.21310 SAGE: A Realistic Benchmark for Semantic Understanding
    67824, -- 2509.20891 AIBA: Attention-based Instrument Band Alignment for Text-to-Audio Diffusion
    68315, -- 2509.19345 SCORE: A Semantic Evaluation Framework for Generative Document Parsing
    68337, -- 2509.12710 RIS-FUSION: Rethinking Text-Driven Infrared and Visible Image Fusion from the Pe
    68362, -- 2509.12125 RailSafeNet: Visual Scene Understanding for Tram Safety
    68388, -- 2509.11727 Microsurgical Instrument Segmentation for Robot-Assisted Surgery
    68483, -- 2509.09572 PeftCD: Leveraging Vision Foundation Models with Parameter-Efficient Fine-Tuning
    68565, -- 2509.07825 Point Linguist Model: Segment Any Object via Bridged Large 3D-Language Model
    68566, -- 2509.07795 Enhanced SegNet with Integrated Grad-CAM for Interpretable Retinal Layer Segment
    68715, -- 2509.04669 VCMamba: Bridging Convolutions with Multi-Directional Mamba for Efficient Visual
    68735, -- 2509.04180 VisioFirm: Cross-Platform AI-assisted Annotation Tool for Computer Vision
    69023, -- 2508.20987 Webly-Supervised Image Manipulation Localization via Category-Aware Auto-Annotat
    69401, -- 2508.15057 GasTwinFormer: A Hybrid Vision Transformer for Livestock Methane Emission Segmen
    69405, -- 2508.14965 You Only Pose Once: A Minimalist's Detection Transformer for Monocular RGB Categ
    69427, -- 2508.14486 WeedSense: Multi-Task Learning for Weed Segmentation, Height Estimation, and Gro
    69446, -- 2508.14153 LENS: Learning to Segment Anything with Unified Reinforced Reasoning
    69474, -- 2508.13669 DeH4R: A Decoupled and Hybrid Method for Road Network Graph Extraction
    69810, -- 2508.08811 Revisiting Efficient Semantic Segmentation: Learning Offsets for Better Spatial
    69848, -- 2508.08219 SAGOnline: Segment Any Gaussians Online
    69912, -- 2508.07300 BEVANet: Bilateral Efficient Visual Attention Network for Real-Time Semantic Seg
    70154, -- 2508.04061 TNet: Terrace Convolutional Decoder Network for Remote Sensing Image Semantic Se
    70292, -- 2508.02172 GaussianCross: Cross-modal Self-supervised 3D Representation Learning via Gaussi
    70444, -- 2508.00259 PointGauss: Point Cloud-Guided Multi-Object Segmentation for Gaussian Splatting
    70584, -- 2507.21888 CAPE: A CLIP-Aware Pointing Ensemble of Complementary Heatmap Cues for Embodied
    70595, -- 2507.21745 Few-Shot Vision-Language Reasoning for Satellite Imagery via Verifiable Rewards
    70632, -- 2507.20894 Online hierarchical partitioning of the output space in extreme multi-label data
    70871, -- 2507.16624 A2Mamba: Attention-augmented State Space Models for Visual Recognition
    71076, -- 2507.12236 Generate to Ground: Multimodal Text Conditioning Boosts Phrase Grounding in Medi
    71108, -- 2507.11523 Precision Spatio-Temporal Feature Fusion for Robust Remote Sensing Change Detect
    71324, -- 2507.06400 When Trackers Date Fish: A Benchmark and Framework for Underwater Multiple Fish
    71352, -- 2507.05673 R-VLM: Region-Aware Vision Language Model for Precise GUI Grounding
    71451, -- 2507.03302 Leveraging Out-of-Distribution Unlabeled Images: Semi-Supervised Semantic Segmen
    71568, -- 2507.00511 Medical Image Segmentation Using Advanced Unet: VMSE-Unet and VM-Unet CBAM+
    71696, -- 2506.22032 Partial CLIP is Enough: Chimera-Seg for Zero-shot Semantic Segmentation
    71874, -- 2506.15976 LBMamba: Locally Bi-directional Mamba
    71875, -- 2506.15940 Polyline Path Masked Attention for Vision Transformer
    72065, -- 2506.09782 Q-SAM2: Accurate Quantization for Segment Anything Model 2
    72157, -- 2506.07304 FANVID: A Benchmark for Face and License Plate Recognition in Low-Resolution Vid
    72303, -- 2506.04277 RSVP: Reasoning Segmentation via Visual Prompting and Multi-modal Chain-of-Thoug
    72316, -- 2506.03237 UniSite: The First Cross-Structure Dataset and Learning Framework for End-to-End
    72376, -- 2506.01921 MedEBench: Revisiting Text-instructed Image Editing on Medical Domain
    72468, -- 2506.00711 QoQ-Med: Building Multimodal Clinical Foundation Models with Domain-Aware GRPO T
    72678, -- 2505.20759 PARTONOMY: Large Multimodal Models with Part-Level Visual Understanding
    72789, -- 2505.17994 Segment Anyword: Mask Prompt Inversion for Open-Set Grounded Segmentation
    72857, -- 2505.16540 TextureSAM: Towards a Texture Aware Foundation Model for Segmentation
    72875, -- 2506.11048 I Can't Believe It's Not Real: CV-MuSeNet: Complex-Valued Multi-Signal Segmentat
    73328, -- 2504.18190 What is the Added Value of UDA in the VFM Era?
    73395, -- 2504.15888 MS-Occ: Multi-Stage LiDAR-Camera Fusion for 3D Semantic Occupancy Prediction
    73487, -- 2504.11637 DamageCAT: A Deep Learning Transformer Framework for Typology-Based Post-Disaste
    73731, -- 2504.01957 Toward Real-world BEV Perception: Depth Uncertainty Estimation via Gaussian Spla
    74194, -- 2503.07029 Availability-aware Sensor Fusion via Unified Canonical Space
    74247, -- 2503.04698 DEAL-YOLO: Drone-based Efficient Animal Localization using YOLO
    74332, -- 2503.01601 Evaluating Stenosis Detection with Grounding DINO, YOLO, and DINO-DETR
    74432, -- 2502.20041 3D-AffordanceLLM: Harnessing Large Language Models for Open-Vocabulary Affordanc
    74628, -- 2502.12449 YUNet: Improved YOLOv11 Network for Skyline Detection
    74981, -- 2502.00719 Vision and Language Reference Prompt into SAM for Few-shot Segmentation
    75146, -- 2501.11288 PD-SORT: Occlusion-Robust Multi-Object Tracking Using Pseudo-Depth Cues
    75406, -- 2412.15209 PRIMA: Multi-Image Vision-Language Models for Reasoning Segmentation
    75557, -- 2412.13179 A Pipeline and NIR-Enhanced Dataset for Parking Lot Segmentation
    75722, -- 2411.15923 Deep Learning for automated multi-scale functional field boundaries extraction u
    75760, -- 2003.03653 SalsaNext: Fast, Uncertainty-aware Semantic Segmentation of LiDAR Point Clouds f
    75993, -- 2410.19846 YOLO11 and Vision Transformers based 3D Pose Estimation of Immature Green Fruits
    76026, -- 2410.13294 LESS: Label-Efficient and Single-Stage Referring 3D Segmentation
    76770, -- 2407.08526 BLOS-BEV: Navigation Map Enhanced Lane Segmentation Network, Beyond Line of Sigh
    76840, -- 2407.02077 Hierarchical Temporal Context Learning for Camera-based Semantic Scene Completio
    76874, -- 2406.19655 Basketball-SORT: An Association Method for Complex Multi-object Occlusion Proble
    77051, -- 2406.05850 Scaling Graph Convolutions for Mobile Vision
    77074, -- 2406.04207 CDMamba: Incorporating Local Clues into Mamba for Remote Sensing Image Binary Ch
    77376, -- 2404.16882 ThermoPore: Predicting Part Porosity Based on Thermal Images Using Deep Learning
    77393, -- 2404.13921 NeRF-DetS: Enhanced Adaptive Spatial-wise Sampling and View-wise Fusion Strategi
    77405, -- 2404.12920 Zero-Shot Medical Phrase Grounding with Off-the-shelf Diffusion Models
    77606, -- 2406.17590 Multimodal Chaptering for Long-Form TV Newscast Video
    77665, -- 2401.17828 Leveraging Swin Transformer for Local-to-Global Weakly Supervised Semantic Segme
    78031, -- 2312.17163 FENet: Focusing Enhanced Network for Lane Detection
    78032, -- 2312.17118 Fully Sparse 3D Occupancy Prediction
    78205, -- 2311.14146 Class Balanced Dynamic Acquisition for Domain Adaptive Semantic Segmentation usi
    78225, -- 2311.11319 GeoSAM: Fine-tuning SAM with Multi-Modal Prompts for Mobility Infrastructure Seg
    78539, -- 2309.05186 HiLM-D: Enhancing MLLMs with Multi-Scale High-Resolution Details for Autonomous
    78583, -- 2309.00348 MuraNet: Multi-task Floor Plan Recognition with Relation Attention
    78615, -- 2308.12469 Diffuse, Attend, and Segment: Unsupervised Zero-Shot Segmentation using Stable D
    78864, -- 2306.13074 Iterative Scale-Up ExpansionIoU and Deep Features Association for Multi-Object T
    79037, -- 2305.08808 GeoMAE: Masked Geometric Target Prediction for Self-supervised Point Cloud Pre-T
    79118, -- 2304.10439 A Study on Reproducibility and Replicability of Table Structure Recognition Meth
    79532, -- 2211.14053 Re^2TAL: Rewiring Pretrained Video Backbones for Reversible Temporal Action Loca
    79538, -- 2211.14317 Hard to Track Objects with Irregular Motions and Similar Appearances? Make It Ea
    79554, -- 2211.11131 Doubly Contrastive End-to-End Semantic Segmentation for Autonomous Driving under
    79670, -- 2206.04670 PointNeXt: Revisiting PointNet++ with Improved Training and Scaling Strategies
    79733, -- 2209.08575 SegNeXt: Rethinking Convolutional Attention Design for Semantic Segmentation
    79738, -- 2209.07828 Weakly Supervised Semantic Segmentation via Progressive Patch Learning
    79820, -- 2207.13159 TINYCD: A (Not So) Deep Learning Model For Change Detection
    79895, -- 2206.07990 Patch-level Representation Learning for Self-supervised Vision Transformers
    79910, -- 2206.04584 Efficient and Robust 2D-to-BEV Representation Learning via Geometry-guided Kerne
    79991, -- 2205.05740 Surface Representation for Point Clouds
    80070, -- 2204.05525 TopFormer: Token Pyramid Transformer for Mobile Semantic Segmentation
    80347, -- 2112.01071 Extract Free Dense Labels from CLIP
    80634, -- 2106.15361 Quantifying urban streetscapes with deep learning: focus on aesthetic evaluation
    80752, -- 2104.13188 Rethinking BiSeNet For Real-time Semantic Segmentation
    80802, -- 2103.16562 Boundary IoU: Improving Object-Centric Image Segmentation Evaluation
    80828, -- 2103.05950 FSCE: Few-Shot Object Detection via Contrastive Proposal Encoding
    80965, -- 2012.07261 OCTA-500: A Retinal Dataset for Optical Coherence Tomography Angiography Study
    81349, -- 2004.13316 SCRDet++: Detecting Small, Cluttered and Rotated Objects via Instance-Level Feat
    81385, -- 2004.02147 BiSeNet V2: Bilateral Network with Guided Aggregation for Real-time Semantic Seg
    81777, -- 1904.00853 Precise Detection in Densely Packed Scenes
    83479, -- 2605.18101 SENSE: Satellite-based ENergy Synthesis for Sustainable Environment
    83691, -- 2605.17448 Self-Improving CAD Generation Agents with Finite Element Analysis as Feedback
    83795, -- 2605.27365 LocateAnything: Fast and High-Quality Vision-Language Grounding with Parallel Bo
    84015, -- 2505.17476 The Coherence Trap: When MLLM-Crafted Narratives Exploit Manipulated Visual Cont
    84034, -- 2506.07847 F2Net: A Frequency-Fused Network for Ultra-High Resolution Remote Sensing Segmen
    84145, -- 2511.02607 UniChange: Unifying Change Detection with Multimodal Large Language Model
    84147, -- 2511.03571 OneOcc: Semantic Occupancy Prediction for Legged Robots with a Single Panoramic
    84153, -- 2511.07923 Exploring the Underwater World Segmentation without Extra Training
    84194, -- 2511.16937 OmniGround: A Comprehensive Spatio-Temporal Grounding Benchmark for Real-World C
    84200, -- 2511.17221 QueryOcc: Query-based Self-Supervision for 3D Semantic Occupancy
    84234, -- 2511.19221 Percept-WAM: Perception-Enhanced World-Awareness-Action Model for Robust End-to-
    84257, -- 2511.21113 FaithFusion: Harmonizing Reconstruction and Generation via Pixel-wise Informatio
    84286, -- 2511.23151 Learning to Refuse: Refusal-Aware Reinforcement Fine-Tuning for Hard-Irrelevant
    84329, -- 2512.03345 HalluGen: Synthesizing Realistic and Controllable Hallucinations for Evaluating
    84371, -- 2512.09201 Residual Primitive Fitting of 3D Shapes with SuperFrusta
    84382, -- 2512.11099 VGent: Visual Grounding via Modular Design for Disentangling Reasoning and Predi
    84488, -- 2601.15408 CURE: Curriculum-guided Multi-task Training for Reliable Anatomy Grounded Report
    84492, -- 2601.16788 REL-SF4PASS: Panoramic Semantic Segmentation with REL Depth Representation and S
    84524, -- 2602.18842 Detecting AI-Generated Forgeries via Iterative Manifold Deviation Amplification
    84537, -- 2602.19063 Direction-aware 3D Large Multimodal Models
    84597, -- 2602.21552 Generalizing Visual Geometry Priors to Sparse Gaussian Occupancy Prediction
    84629, -- 2602.22667 Monocular Open Vocabulary Occupancy Prediction for Indoor Scenes
    84742, -- 2603.04002 Discriminative Perception via Anchored Description for Reasoning Segmentation
    84874, -- 2603.12382 SPARROW: Learning Spatial Precision and Temporal Referential Consistency in Pixe
    84880, -- 2603.12764 SAVA-X: Ego-to-Exo Imitation Error Detection via Scene-Adaptive View Alignment a
    84900, -- 2603.13912 Towards Stable Self-Supervised Object Representations in Unconstrained Egocentri
    84993, -- 2603.19776 ReManNet: A Riemannian Manifold Network for Monocular 3D Lane Detection
    85057, -- 2603.22893 SLARM: Streaming and Language-Aligned Reconstruction Model for Dynamic Scenes
    85109, -- 2603.25131 Denoise and Align: Towards Source-Free UDA for Robust Panoramic Semantic Segment
    85226, -- 2604.01081 ProOOD: Prototype-Guided Out-of-Distribution 3D Occupancy Prediction
    85244, -- 2604.02093 GroundVTS: Visual Token Sampling in Multimodal Large Language Models for Video T
    85282, -- 2604.04933 PointTPA: Dynamic Network Parameter Adaptation for 3D Scene Understanding
    85294, -- 2604.05780 Sparsity-Aware Voxel Attention and Foreground Modulation for 3D Semantic Scene C
    85375, -- 2604.13596 VGGT-Segmentor: Geometry-Enhanced Cross-View Segmentation
    85382, -- 2604.14706 NG-GS: NeRF-guided 3D Gaussian Splatting Segmentation
    85431, -- 2604.20286 MambaLiteUNet: Cross-Gated Adaptive Feature Fusion for Robust Skin Lesion Segmen
    85542, -- 2605.11520 PointGS: Semantic-Consistent Unsupervised 3D Point Cloud Segmentation with 3D Ga
    85585, -- 2605.19340 Selective, Regularized, and Calibrated: Harnessing Vision Foundation Models for
    85588, -- 2605.19622 UniRefiner: Teaching Pre-trained ViTs to Self-Dispose Dross via Contrastive Regi
    85633, -- 2204.07761 Language-Grounded Indoor 3D Semantic Segmentation in the Wild
    85734, -- 2502.17821 CAML: Collaborative Auxiliary Modality Learning for Multi-Agent Systems
    86153, -- 2502.14520 Learning Temporal 3D Semantic Scene Completion via Optical Flow Guidance
    86163, -- 2509.17847 Semantic and Visual Crop-Guided Diffusion Models for Heterogeneous Tissue Synthe
    86258, -- 2509.16588 SQS: Enhancing Sparse Perception Models via Query-based Splatting in Autonomous
    86465, -- 2506.13260 COME: Adding Scene-Centric Forecasting Control to Occupancy World Model
    87384, -- 2505.21381 ZigzagPointMamba: Spatial-Semantic Mamba for Point Cloud Understanding
    87515, -- 2606.02551 AFUN: Towards an Affordance Foundation Model for Functionality Understanding
    87540, -- 2507.16337 One Polyp Identifies All: One-Shot Polyp Segmentation with SAM via Cascaded Prio
    87551, -- 2503.18438 ReconDreamer++: Harmonizing Generative and Reconstructive Models for Driving Sce
    87650, -- 2508.15439 Aligning Moments in Time using Video Queries
    87843, -- 2508.04705 Occupancy Learning with Spatiotemporal Memory
    87865, -- 2507.01630 Prompt Guidance and Human Proximal Perception for HOT Prediction with Regional J
    88000, -- 2503.07167 Temporal Overlapping Prediction: A Self-supervised Pre-training Method for LiDAR
    88112, -- 2507.08555 Disentangling Instance and Scene Contexts for 3D Semantic Scene Completion
    88260, -- 2504.10117 AGO: Adaptive Grounding for Open World 3D Occupancy Prediction
    88298, -- 2503.08010 SKALD: Learning-Based Shot Assembly for Coherent Multi-Shot Video Creation
    88365, -- 2508.09949 Stable Diffusion Models are Secretly Good at Visual In-Context Learning
    88519, -- 2412.11540 SP2T: Sparse Proxy Attention for Dual-stream Point Transformer
    88889, -- 2502.10875 A Geometric Approach to Personalized Recommendation with Set-Theoretic Constrain
    89093, -- 2506.22769 Learning Efficient Robotic Garment Manipulation with Standardization
    89930, -- 2505.14100 Unlocking the Power of SAM 2 for Few-Shot Segmentation
    89961, -- 2505.24746 Tackling View-Dependent Semantics in 3D Language Gaussian Splatting
    90019, -- 2506.07376 Adapter Naturally Serves as Decoupler for Cross-Domain Few-Shot Semantic Segment
    90106, -- 2411.16129 Three Cars Approaching within 100m! Enhancing Distant Geometry by Tri-Axis Voxel
    90157, -- 2505.06068 Noise-Consistent Siamese-Diffusion for Medical Image Synthesis and Segmentation
    90192, -- 2503.21854 Foveated Instance Segmentation
    90267, -- 2503.15910 No Thing, Nothing: Highlighting Safety-Critical Classes for Robust LiDAR Semanti
    90377, -- 2412.00678 2DMamba: Efficient State Space Model for Image Representation with Applications
    90607, -- 2412.06647 Object Detection using Event Camera: A MoE Heat Conduction based Detector and A
    90608, -- 2504.19749 STCOcc: Sparse Spatial-Temporal Cascade Renovation for 3D Occupancy and Scene Fl
    90661, -- 2411.14169 Spatiotemporal Decoupling for Efficient Vision-Based Occupancy Forecasting
    90724, -- 2411.15556 ReWind: Understanding Long Videos with Instructed Learnable Memory
    90760, -- 2503.12539 BFANet: Revisiting 3D Semantic Segmentation with Boundary Feature Analysis
    90789, -- 2503.21150 The Devil is in Low-Level Features for Cross-Domain Few-Shot Segmentation
    90823, -- 2411.19548 ReconDreamer: Crafting World Models for Driving Scene Reconstruction via Online
    92068, -- 2502.06756 SAMRefiner: Taming Segment Anything Model for Universal Mask Refinement
    92180, -- 2408.08862 Visual Agents as Fast and Slow Thinkers
    92185, -- 2410.12214 Order-aware Interactive Segmentation
    94057, -- 2508.12132 TriQDef: Disrupting Semantic and Gradient Alignment to Prevent Adversarial Patch
    94191, -- 2506.05473 S2GO: Streaming Sparse Gaussian Occupancy
    94278, -- 2603.21115 LiFR-Seg: Anytime High-Frame-Rate Segmentation via Event-Guided Propagation
    94562, -- 2602.08626 Revisiting [CLS] and Patch Token Interaction in Vision Transformers
    94838, -- 2506.18248 Improving Black-Box Generative Attacks via Generator Semantic Consistency
    94873, -- 2605.16903 WOW-Seg: A Word-free Open World Segmentation Model
    95136, -- 2012.02206 Scan2Cap: Context-aware Dense Captioning in RGB-D Scans
    95209, -- 2507.06971 Hallucinating 360°: Panoramic Street-View Generation Via Local Scenes Diffusion
    95281, -- external From Dream to Action: Hierarchical Policy Learning with 3D World Imagination for
    95300, -- external Task-Aware and Structure-Knowledge-Guided Quantization for End-To-End YOLO Objec
    95389, -- 2512.05988 VG3T: Visual Geometry Grounded Gaussian Transformer
    95401, -- 2603.14738 Efficient Event Camera Volume System
    95550, -- external Vision-Guided Robotic Grinding with Deep Learning-Based Bead Segmentation and Di
    95694, -- external MotionNet-PGA: MotionNet with Polar-Guided Attention for Moving Object Segmentat
    95705, -- external X-MOS: A Heterogeneous Cross-LiDAR Generalization Framework for Moving Object Se
    95714, -- 2503.21767 Semantically Consistent Language Gaussian Splatting for 3D Point-Level Open-Voca
    95801, -- 2510.09035 Exploring Single Domain Generalization of LiDAR-Based Semantic Segmentation unde
    95828, -- external DropClick: Semi-Automated One-Click Segmentation for Agricultural Robotic Data
    95839, -- external Visual Grounding Via Heterogeneous Representation Learning and Hierarchical Reas
    95840, -- 2511.01250 Source-Only Cross-Weather LiDAR Via Geometry-Aware Point Drop
    96098, -- external AI-Driven Landing Zone Detection Module for Vertical Take-Off and Landing Vehicl
    96128, -- external An Automatic LiDAR-Camera Extrinsic Calibration Method for Sparse Point Clouds U
    96160, -- 2603.06927 A Contrastive Few-Shot RGB-D Traversability Segmentation Framework for Indoor Ro
    96184, -- external PDLNet: Learning Point Cloud Distortion for Unsupervised Cross-Domain Point Clou
    96200, -- external Tool-Grasp: A 6-DoF Functional Grasping Framework for General-Purpose Hand Tools
    96323, -- 2505.12693 TACOcc: Target-Adaptive Cross-Modal Fusion with Sequential Volume Rendering for
    96433, -- external Neuromorphic Event Camera-Based Object Recognition and Grasping Position Detecti
    96508, -- 2603.21134 Anatomical Prior-Driven Framework for Autonomous Robotic Cardiac Ultrasound Stan
    96673, -- external FALCO: Foundation Model Guided Active Learning for Cost-Effective Off-Road Frees
    96962, -- 2603.07060 GuideTWSI: A Diverse Tactile Walking Surface Indicator Dataset from Synthetic an
    97052, -- 2509.17107 CoBEVMoE: Heterogeneity-Aware Feature Fusion with Dynamic Mixture-Of-Experts for
    97224, -- 2603.07454 SLNet: A Super-Lightweight Geometry-Adaptive Network for 3D Point Cloud Recognit
    97227, -- 2508.09599 BridgeTA: Bridging the Representation Gap in Knowledge Distillation Via Teacher
    97265, -- external Robust 3D Multi-Object Tracking for Autonomous Driving with Adaptive LiDAR-Visua
    97335, -- 2407.18038 TiCoSS: Tightening the Coupling between Semantic Segmentation and Stereo Matchin
    97403, -- external From Simulation to Deployment: Curriculum-Based Domain Adaptation for Semantic S
    97514, -- external Towards Efficient Semi-Supervised Semantic Segmentation for Solid-State LiDAR Po
    97558, -- external HINT-3D: Human-In-The-Loop Interactive Test-Time Adaptation for 3D Segmentation
    97660, -- 2412.14579 GSRender: Deduplicated Occupancy Estimation Via Weakly Supervised 3D Gaussian Sp
    97703, -- 2511.17777 See, Plan, Cut: MPC-Based Autonomous Volumetric Robotic Laser Surgery with OCT G
    97937, -- external Beyond Euclidean Gossip: KL-Barycentric Consensus on Heterogeneous and Imbalance
    98003, -- external REALM (AutoSOTA)
    98058, -- external Generalizable Knowledge Distillation from Vision Foundation Models for Semantic
    98061, -- external KaLOS finds Consensus: A Meta-Algorithm for Evaluating Inter-Annotator Agreement
    98071, -- external GoCA: Making Training-Free Diffusion Segmentors Scale with the Generative Power
    98074, -- external Statistical Characteristic-Guided Denoising for Rapid High-Resolution Transmissi
    98075, -- external SAMTok: Representing Any Mask with Two Words (AutoSOTA)
    98086, -- 2606.08132 Phase Marginalization for Patch-Grid Instability in Vision Transformers
    98090, -- external Beyond Euclidean Gossip: KL-Barycentric Consensus on Heterogeneous and Imbalance
    98093, -- external ACPV-Net: All-Class Polygonal Vectorization for Seamless Vector Map Generation f
    98255, -- 2506.23323 FA-Seg: A Fast and Accurate Diffusion-Based Method for Open-Vocabulary Segmentat
    98282, -- 2408.15254 vFusedSeg3D: 3rd Place Solution for 2024 Waymo Open Dataset Challenge in Semanti
    98335, -- 2403.16958 TwinLiteNet+: An Enhanced Multi-Task Segmentation Model for Autonomous Driving
    98437, -- 2606.16673 MMDiff: Extending Diffusion Transformers for Multi-Modal Generation
    98530, -- 2606.14024 ViT-Up: Faithful Feature Upsampling for Vision Transformers
    98609, -- 2301.01100 Understanding Imbalanced Semantic Segmentation Through Neural Collapse
    98614, -- 2203.14662 MaskGroup: Hierarchical Point Grouping and Masking for 3D Instance Segmentation
    98616, -- 2004.01658 PointGroup: Dual-Set Point Grouping for 3D Instance Segmentation
    98624, -- 2403.11691 TTT-KD: Test-Time Training for 3D Semantic Segmentation through Knowledge Distil
    98629, -- 2107.13824 VMNet: Voxel-Mesh Network for Geodesic-Aware 3D Semantic Segmentation
    98632, -- 2206.10555 LargeKernel3D: Scaling up Kernels in 3D Sparse CNNs
    98633, -- 2203.05272 Contrastive Boundary Learning for Point Cloud Segmentation
    98642, -- 2403.14418 OA-CNNs: Omni-Adaptive Sparse CNNs for 3D Semantic Segmentation
    98643, -- 2305.03045 OctFormer: Octree-based Transformers for 3D Point Clouds
    98797, -- 2408.13003 BoostTrack++: using tracklet information to detect more objects in multiple obje
    98982, -- 2606.19317 Explaining Attention with Program Synthesis
    99135, -- 2603.27448 GIFT: Bootstrapping Image-to-CAD Program Synthesis via Geometric Feedback
    99175, -- 2605.08805 LightAVSeg: Lightweight Audio-Visual Segmentation
    99236, -- 2512.24023 RSAgent: Learning to Reason and Act via Multi-Turn Tool Invocations for Text-Gui
    99385, -- 2605.12325 VIP: Visual-guided Prompt Evolution for Efficient Dense Vision-Language Inferenc
    99665, -- 2604.20395 SpaCeFormer: Fast Proposal-Free Open-Vocabulary 3D Instance Segmentation
    100121, -- 2605.10603 Segment Anything with Robust Uncertainty-Accuracy Correlation
    100187, -- 2603.04976 3D-RFT: Reinforcement Fine-Tuning for Video-based 3D Scene Understanding
    100332, -- 2605.14926 SCRWKV: Ultra-Compact Structure-Calibrated Vision-RWKV for Topological Crack Seg
    100393, -- 2606.08980 EPS3D: End-to-End Feed-Forward 3D Panoptic Segmentation
    100815, -- 2606.08436 CACR: Reinforcing Temporal Answer Grounding in Instructional Video via Candidate
    101254, -- 2605.14742 EARL: Towards a Unified Analysis-Guided Reinforcement Learning Framework for Ego
    101272, -- 2605.07379 RELO: Reinforcement Learning to Localize for Visual Object Tracking
    101520, -- 2512.14099 ViewMask-1-to-3: Multi-View Consistent Image Generation via Multimodal Discrete
    101573, -- 2502.02763 Looking Locally: Object-Centric Vision Transformers as Foundation Models for Eff
    101933, -- 2510.04022 Video-in-the-Loop: Span-Grounded Long Video QA with Interleaved Reasoning
    102387, -- 2605.01171 CADFit: Precise Mesh-to-CAD Program Generation with Hybrid Optimization
    102580, -- 2607.03068 PixCon: Clean-Positive Contrastive Learning for Foundation-Model Semi-Supervised
    103170, -- 2604.18562 AnchorSeg: Language Grounded Query Banks for Reasoning Segmentation
    103190, -- 2604.28177 AEGIS: A Holistic Benchmark for Evaluating Forensic Analysis of AI-Generated Aca
    103384, -- 2412.19685 Generating Attribution Reports for Manipulated Facial Images: A Dataset and Base
    103483, -- 2602.17696 Can LLM Safety Be Ensured by Constraining Parameter Regions?
    104321, -- 2110.01931 Anchor-free Oriented Proposal Generator for Object Detection
    104323, -- 2206.13996 Detecting tiny objects in aerial images: A normalized Wasserstein distance and a
    104404, -- 2607.17423 TimeLens2: Generalist Video Temporal Grounding with Multimodal LLMs
    104428, -- 2508.07388 Invert4TVG: A Temporal Video Grounding Framework with Inversion Tasks Preserving
    104929, -- 2507.23652 Adaptively Distilled ControlNet: Accelerated Training and Superior Sampling for
    105073, -- external CT-Based Hippocampus Segmentation with Dual-Decoder Network (HDD-Net)
    105161, -- external Endoscopic Artifact Inpainting for Improved Endoscopic Image Segmentation
    105172, -- external ESPNet: Edge-Aware Feature Shrinkage Pyramid for Polyp Segmentation
    105380, -- external MARSeg: Enhancing Medical Image Segmentation with MAR and Adaptive Feature Fusio
    105434, -- 2403.10039 Motion-Boundary-Driven Unsupervised Surgical Instrument Segmentation in Low-Qual
    105503, -- 2503.21054 Operating Room Workflow Analysis via Reasoning Segmentation over Digital Twins
    105530, -- 2507.18958 PerioDet: Large-Scale Panoramic Radiograph Benchmark for Clinical-Oriented Apica
    105796, -- external Unleashing the Power of LLMs for Medical Video Answer Localization
    105826, -- external ViTexNet: Vision-Text Guided Dynamic Convolution Network for Medical Image Segme
    105842, -- external You Can Detect It: Fetal Biometric Estimation Using Ellipse Detection
    105981, -- 2606.00188 PaintBench: Deterministic Evaluation of Precise Visual Editing
    106465, -- 2509.12040 Exploring Efficient Open-Vocabulary Segmentation in the Remote Sensing
    106475, -- 2512.11557 3DTeethSAM: Taming SAM2 for 3D Teeth Segmentation
    106711, -- 2504.16443 Marginalized Generalized IoU (MGIoU): A Unified Objective Function for Optimizin
    106733, -- 2511.06857 Ambiguity-aware Truncated Flow Matching for Ambiguous Medical Image Segmentation
    106735, -- 2511.05853 Point Cloud Segmentation of Integrated Circuits Package Substrates Surface Defec
    107007, -- 2511.12003 Look as You Think: Unifying Reasoning and Visual Evidence Attribution for Verifi
    107133, -- 2512.16567 Causal-Tune: Mining Causal Factors from Vision Foundation Models for Domain Gene
    107201, -- 2511.08186 Pixel-level Quality Assessment for Oriented Object Detection
    107252, -- 2508.13601 Unleashing Semantic and Geometric Priors for 3D Scene Completion
    107259, -- 2511.08251 LayerEdit: Disentangled Multi-Object Editing via Conflict-Aware Multi-Layer Lear
    107293, -- 2603.19606 Beyond Quadratic: Linear-Time Change Detection with RWKV
    107557, -- 2603.06321 P-SLCR: Unsupervised Point Cloud Semantic Segmentation via Prototypes Structure
    107636, -- 2511.13924 Start Small, Think Big: Curriculum-based Relative Policy Optimization for Visual
    107735, -- 2601.01746 Point-SRA: Self-Representation Alignment for 3D Representation Learning
    107830, -- 2511.22948 Do We Need Perfect Data? Leveraging Noise for Domain Generalized Segmentation
    108110, -- 2508.10936 Vision-Only Gaussian Splatting for Collaborative Semantic Occupancy Prediction
    108167, -- 2502.12604 S2C: A Noise-Resistant Difference Learning Framework for Unsupervised Change Det
    108190, -- 2512.01701 SSR: Semantic and Spatial Rectification for CLIP-based Weakly Supervised Segment
    108224, -- 2508.02261 SplatSSC: Decoupled Depth-Guided Gaussian Splatting for Semantic Scene Completio
    108358, -- 2512.22612 Enhancing Noise Resilience in Face Clustering via Sparse Differential Transforme
    108367, -- 2511.13031 Towards 3D Object-Centric Feature Learning for Semantic Scene Completion
    108431, -- 2603.01524 Better Matching, Less Forgetting: A Quality-Guided Matcher for Transformer-based
    108514, -- 2503.18947 Tuning-Free Amodal Segmentation via the Occlusion-Free Bias of Inpainting Models
    108648, -- 2608.03971 UniWorld-Design: From Pixel Generation to Layer-Native Design
    108739, -- 2603.22229 Benchmarking Deep Learning Models for Aerial LiDAR Point Cloud Semantic Segmenta
    108804, -- 2605.11680 ShapeCodeBench: A Renewable Benchmark for Perception-to-Program Reconstruction o
    108827, -- 2604.24311 BIMStruct3D: A Fully Automated Hybrid Learning Scan-to-BIM Pipeline with Integra
    109079, -- 2608.03216 iFAN: Inference-Aware Learning for Plain Mask Transformers
    109141, -- 2608.12773 CW-BASS v2: Saturation-Aware Pseudo-Label Selection for Semi-Supervised Segmenta
    109321, -- 2312.08952 UCMCTrack: Multi-Object Tracking with Uniform Camera Motion Compensation
    109723, -- 2608.20492 Annotations as Rollouts: Efficient and Scalable Reinforcement Learning for Video
    112421, -- 2401.05906 PartSTAD: 2D-to-3D Part Segmentation Task Adaptation
    112473, -- 2404.14715 FineMatch: Aspect-based Fine-grained Image and Text Mismatch Detection and Corre
    112475, -- 2407.08126 Label-anticipated Event Disentanglement for Audio-Visual Video Parsing
    112501, -- external Boosting 3D Single Object Tracking with 2D Matching Distillation and 3D Pre-trai
    112556, -- 2407.02286 Rethinking Data Augmentation for Robust LiDAR Semantic Segmentation in Adverse W
    112608, -- 2404.15014 OccGen: Generative Multi-modal 3D Occupancy Prediction for Autonomous Driving
    112620, -- 2407.17786 Topology-Preserving Downsampling of Binary Images
    112627, -- 2312.01597 SCLIP: Rethinking Self-Attention for Dense Vision-Language Inference
    112639, -- 2308.10421 UniM2AE: Multi-modal Masked Autoencoders with Unified 3D Representation for 3D P
    112754, -- 2411.02858 OLAF: A Plug-and-Play Framework for Enhanced Multi-object Multi-part Scene Parsi
    112932, -- external AlignDiff: Aligning Diffusion Models for General Few-Shot Segmentation
    112957, -- 2404.05667 AlignZeg: Mitigating Objective Misalignment for Zero-shot Semantic Segmentation
    112980, -- 2303.08815 Lane Graph as Path: Continuity-preserving Path-wise Modeling for Online Lane Gra
    112986, -- 2407.02389 SAFARI: Adaptive Sequence Transformer for Weakly Supervised Referring Expression
    113091, -- 2310.16305 Dolfin: Diffusion Layout Transformers without Autoencoder
    113106, -- 2405.06228 Context-Guided Spatial Feature Reconstruction for Efficient Semantic Segmentatio
    113136, -- 2407.12294 VEON: Vocabulary-Enhanced Occupancy Prediction
    113154, -- 2407.12387 HGL: Hierarchical Geometry Learning for Test-time Adaptation in 3D Point Cloud S
    113157, -- 2407.10200 Shape2Scene: 3D Scene Representation Learning Through Pre-training on Shape Data
    113189, -- 2402.17891 Weakly Supervised Co-training with Swapping Assignments for Semantic Segmentatio
    113352, -- external GTMS: A Gradient-driven Tree-guided Mask-free Referring Image Segmentation Metho
    113354, -- 2409.01353 From Pixels to Objects: A Hierarchical Approach for Part and Object Segmentation
    113371, -- 2407.05266 CLAMP-ViT: Contrastive Data-Free Learning for Adaptive Post-Training Quantizatio
    113380, -- 2408.04883 ProxyCLIP: Proxy Attention Improves CLIP for Open-Vocabulary Segmentation
    113397, -- 2407.11344 Centering the Value of Every Modality: Towards Efficient and Resilient Modality-
    113489, -- external Open-Vocabulary RGB-Thermal Semantic Segmentation
    113648, -- 2407.11382 "Segment, Lift and Fit: Automatic 3D Shape Labeling from 2D Prompts"
    113669, -- 2407.15648 TreeSBA: Tree-Transformer for Self-Supervised Sequential Brick Assembly
    113703, -- 2407.11224 Distributed Semantic Segmentation with Efficient Joint Source and Task Decoding
    113790, -- 2608.26737 Generative Semantic Scene Completion
    113842, -- 2608.29974 SpanCalib-VLM: Calibrated Hallucination Span Detection in Vision-Language Models
    113949, -- 2605.00876 GAZE: Grounded Agentic Zero-shot Evaluation with Viewer-Level Tools and Literatu
    114388, -- 2407.00718 ASPS: Augmented Segment Anything Model for Polyp Segmentation
    114832, -- 2406.17858 Depth-Driven Geometric Prompt Learning for Laparoscopic Liver Landmark Detection
    114834, -- 2306.00499 DeSAM: Decoupled Segment Anything Model for Generalizable Medical Image Segmenta
    114866, -- external DPMNet: Dual-Path MLP-based Network for Aneurysm Image Segmentation
    115011, -- external Immune-guided AI for Reproducible Regions of Interest Selection in Multiplex Imm
    115227, -- 2411.03725 PX2Tooth: Reconstructing the 3D Point Cloud Teeth from a Single Panoramic X-ray
    115260, -- external SAM Guided Task-Specific Enhanced Nuclei Segmentation in Digital Pathology
    115307, -- external Spatial Context Awareness in Surgery through Sound Source Localization
    115320, -- external STAN-LOC: Visual Query-based Video Clip Localization for Fetal Ultrasound Sweep
    115357, -- external TinyU-Net: Lighter yet Better U-Net with Cascaded Multi-Receptive Fields
    115364, -- external Towards a Deeper insight into Face Detection in Neonatal wards
    115411, -- external Vessel-aware aneurysm detection using multi-scale deformable 3D attention
    115445, -- 2403.16370 GoodSAM: Bridging Domain and Capacity Gaps via Segment Anything Model for Distor
    115474, -- 2312.04089 Open-Vocabulary Segmentation with Semantic-Assisted Calibration
    115496, -- 2404.11998 Curriculum Point Prompting for Weakly-Supervised Referring Image Segmentation
    115532, -- 2401.00901 VideoGrounding-DINO: Towards Open-Vocabulary Spatio-Temporal Video Grounding
    115564, -- external Endow SAM with Keen Eyes: Temporal-spatial Prompt Learning for Video Camouflaged
    115721, -- external Hierarchical Intra-modal Correlation Learning for Label-free 3D Semantic Segment
    115846, -- 2401.01578 Context-Guided Spatio-Temporal Video Grounding
    115954, -- 2404.09993 No More Ambiguity in 360deg Room Layout via Bi-Layout Estimation
    115957, -- 2402.19082 VideoMAC: Video Masked Autoencoders Meet ConvNets
    115965, -- 2311.17095 Emergent Open-Vocabulary Semantic Segmentation from Off-the-shelf Vision-Languag
    116002, -- 2311.15537 SED: A Simple Encoder-Decoder for Open-Vocabulary Semantic Segmentation
    116025, -- 2312.09788 Collaborating Foundation Models for Domain Generalized Semantic Segmentation
    116226, -- 2305.10061 Rethinking Boundary Discontinuity Problem for Oriented Object Detection
    116243, -- 2405.05259 OpenESS: Event-based Semantic Scene Understanding with Open Vocabularies
    116253, -- 2404.04050 No Time to Train: Empowering Non-Parametric Networks for Few-shot 3D Scene Segme
    116267, -- 2405.04390 DriveWorld: 4D Pre-trained Scene Understanding via World Models for Autonomous D
    116310, -- 2404.01409 OVFoodSeg: Elevating Open-Vocabulary Food Image Segmentation via Image-Informed
    116424, -- 2311.12079 FreeKD: Knowledge Distillation via Semantic Frequency Prompt
    116435, -- 2310.00132 QDFormer: Towards Robust Audiovisual Segmentation in Complex Environments with Q
    116476, -- 2403.16788 HPL-ESS: Hybrid Pseudo-Labeling for Unsupervised Event-based Semantic Segmentati
    116497, -- 2405.01538 Multi-Space Alignments Towards Universal LiDAR Segmentation
    116522, -- 2405.07201 Building a Strong Pre-Training Baseline for Universal 3D Large-Scale Perception
    116533, -- 2406.09936 ALGM: Adaptive Local-then-Global Token Merging for Efficient Semantic Segmentati
    116539, -- 2403.18469 Density-guided Translator Boosts Synthetic-to-Real Unsupervised Domain Adaptive
    116571, -- 2404.00262 Image-to-Image Matching via Foundation Models: A New Perspective for Open-Vocabu
    116610, -- 2311.14960 Point Cloud Pre-training with Diffusion Models
    116979, -- 2310.08471 WinSyn: : A High Resolution Testbed for Synthetic Data
    117050, -- 2306.15670 Symphonize 3D Semantic Scene Completion with Contextual Instance Queries
    117057, -- 2311.16516 Segment Every Out-of-Distribution Object
    117159, -- external Viewpoint-Aware Visual Grounding in 3D Scenes
    117192, -- external Realigning Confidence with Temporal Saliency Information for Point-Level Weakly-
    117229, -- 2403.19366 Infrared Small Target Detection with Scale and Location Sensitivity
    117406, -- 2606.31533 MV-GEL: Language-Driven Multi-View Geometric Entity Localization on Meshes
    117408, -- 2603.28503 Bridging the Geometry Mismatch: Frequency-Aware Anisotropic Serialization for Th
    117443, -- 2606.31201 ExPLoRe: Expert Patch-Level Loss Routing for Multi-Objective Masked Image Modeli
    117604, -- 2606.24353 Open-Vocabulary BEV Segmentation with 3D-Aware Geometric Constraints
    117763, -- 2606.23486 From Reconstruction to Decision: A Post-Encoder Plug-in Adapter for Curvilinear
    117811, -- 2607.17693 Memory-Supported Synergistic Adaptation for Training-Free Test-Time Medical Imag
    117868, -- 2606.24935 SEMIR: Topology-Preserving Graph Minors for Thin-Structure Segmentation
    117885, -- 2607.03247 Learning to Suppress SPAD-based LiDAR Flare
    117957, -- 2511.16049 LiSTAR: Ray-Centric World Models for 4D LiDAR Sequences in Autonomous Driving
    118031, -- 2608.15279 Geometry-Aware Spatio-Temporal Context Modeling for 4D Occupancy Forecasting
    118046, -- 2607.17479 TraversRL: Traversable Pedestrian Pathway Generation With Reinforcement Learning
    118111, -- 2608.16338 SIGMA-Lane: Scale-pyramId Gated MAmba for Temporally Consistent Video Lane Detec
    118124, -- 2608.11285 SegPAR: Class-Centric Decision-Based Sparse Attack for Semantic Segmentation
    118182, -- 2510.00458 VLOD-TTA: Test-Time Adaptation of Vision-Language Object Detectors
    118344, -- 2603.03043 IoUCert: Robustness Verification for Anchor-based Object Detectors
    118709, -- 2608.26856 From Reasoning to Pixels: Grounded Medical Multimodal LLMs for VQA and Segmentat
    118732, -- 2603.05663 Keeping the Evidence Chain: Semantic Evidence Allocation for Training-Free Token
    118815, -- 2607.04779 DGSeg: Dynamic Gating of Semantic-Spatial Guided Predictions for Reasoning Segme
    118847, -- 2606.31609 Learning Structurally Consistent Representations for Multi-View Radar Semantic S
    118997, -- 2503.22087 Streaming Dense Voxel Representations for 3D Occupancy Prediction
    119003, -- external Per‑Object IoU Forecasting for Deadline‑Aware Real‑Time Embedded Detection Contr
    119040, -- 2606.22378 Following the Flow: Advection-Consistent Modeling for Event-based Small Object D
    119050, -- 2607.02018 UnderOneFacade: Worldwide Facade Semantic Segmentation Benchmark Dataset
    119107, -- 2606.09536 Adversarial Attack and Disturbance Detection by Hadamard-Coded Output Representa
    119122, -- 2608.11815 Learning with Bilevel-Minimax Optimization for Efficient and Reliable Transfer A
    119354, -- 2607.00672 DART: Difficulty-Adaptive Routing for Zero-Shot Video Temporal Grounding
    119543, -- 2509.23098 Blind to Position, Biased in Language: Probing Mid-Layer Representational Bias i
    119681, -- 2601.13633 EGM: Efficient Visual Grounding Language Models
    119701, -- 2603.22279 3D-Layout-R1: Structured Reasoning for Language-Instructed Spatial Editing
    119805, -- 2403.04562 Out of the Room: Generalizing Event-Based Dynamic Motion Segmentation for Comple
    119836, -- external DeepLA-Net: Very Deep Local Aggregation Networks for Point Cloud Analysis
    119948, -- 2405.14338 Mamba4D: Efficient 4D Point Cloud Video Understanding with Disentangled Spatial-
    120033, -- external WISNet: Pseudo Label Generation on Unbalanced and Patch Annotated Waste Images
    120040, -- external OralXrays-9: Towards Hospital-Scale Panoramic X-ray Anomaly Detection via Person
    120119, -- 2503.12535 SPC-GS: Gaussian Splatting with Semantic-Prompt Consistency for Indoor Open-Worl
    120131, -- external Generative Map Priors for Collaborative BEV Semantic Segmentation
    120248, -- 2408.02245 Multi-Modal Contrastive Masked Autoencoders: A Two-Stage Progressive Pre-trainin
    120449, -- 2505.13788 Ground-V: Teaching VLMs to Ground Complex Instructions in Pixels
    120482, -- external Improving Semi-Supervised Semantic Segmentation with Sliced-Wasserstein Feature
    120527, -- external Efficient Decoupled Feature 3D Gaussian Splatting via Hierarchical Compression
    120542, -- 2503.12006 ROS-SAM: High-Quality Interactive Segmentation for Remote Sensing Moving Object
    120594, -- external Self-Supervised Cross-View Correspondence with Predictive Cycle Consistency
    120650, -- 2603.01007 Dr.Occ: Depth- and Region-Guided 3D Occupancy from Surround-View Cameras for Aut
    120656, -- external Boundary-Responsive Differentiable Gating for Superpixel-Based Segmentation
    120665, -- 2505.12861 Towards Robust Multi-Modal Semantic Segmentation with Teacher-Student Framework
    120748, -- 2604.05621 FUN REC * Reconstructing Functional 3D Scenes from Egocentric Interaction Videos
    120837, -- 2605.23113 Inconsistency-aware Multimodal Schrodinger Bridge for Deepfake Localization
    120857, -- external Learning and Aligning Click-Aware Shape Prior for Interactive Amodal Instance Se
    120903, -- external TimeBridge: Self-Supervised Video Representation Learning via Start-End Joint Em
    120990, -- external Hilbert Curve-Based Attention Enabling Topology-Preserving Image Tensor Represen
    121066, -- 2605.20576 Dynamics: Language-Based Representation for Inferring Rigid-Body Dynamics From V
    121077, -- external PromptMoE: A Segmentation Refinement Framework Leveraging Mixture of Experts for
    121161, -- external Structure-Aware Representation Distillation for Tiny-Dense Object Segmentation
    121191, -- external YOLO-ULM: Ultra-Lightweight Models for Real-Time Object Detection
    121203, -- external Geometry-Aware Cross-Modal Graph Alignment for Referring Segmentation in 3D Gaus
    121285, -- external MatchMask: Mask-Centric Generative Data Augmentation for Label-Scarce Semantic S
    121302, -- external SkySense-VITA: Towards Universal In-context Segmentation of Multi-modal Remote S
    121309, -- external SegGBC: Justifiable Coarse-to-Fine Granular-Ball Computing for Enhancing Cluster
    121359, -- external Visual Grounding for Object Questions
    121399, -- 2602.23575 CycleBEV: Regularizing View Transformation Networks via View Cycle Consistency f
    121409, -- external Learning Spatial-Temporal Consistency for 3D Semantic Scene Completion
    121466, -- 2512.08912 LiDAS: Lighting-driven Dynamic Active Sensing for Nighttime Perception
    121568, -- external PMRNet: Physics-informed Multi-scale Refinement Network for Medical Image Segmen
    121711, -- external Revisiting the Necessity of Full Accuracy: Weakly Supervised Object-Level Offset
    121728, -- external SAMosaic3D: Modular Scene Assembly for Real-Time 3D Segment Anything
    121764, -- external RMAE-ProGRess: Advancing Semantic Segmentation in Unstructured Environments
    121824, -- external S2C2Seg: Semantic-Spatial Consistency and Category Optimization for Open-Vocabul
    122119, -- 2609.23796 Mira-Scene: Pixel-Aligned Layouts for Generative 3D Scene
    122262, -- 2609.38059 WorldLine: Action-Driven Visual Simulation for Robotic Manipulation
    122440, -- 2609.28327 LightMIS: Ultra-Lightweight Medical Image Segmentation Without a Stage-Wise Deco
    122564, -- 2610.02160 4Director: Controlling Video World Models with Rigid 3D Geometry
    122768, -- 2610.05790 FairRSFM: A Biome-Aware Benchmark and Debiasing Framework for Remote Sensing Fou
    122879, -- 2610.00994 VIEScore2: Unified Image Evaluation with Spatially Grounded Explanations
    122909, -- 2610.03799 StepCAD: Mesh-to-CAD Code Generation via LLM Policy and Geometry-Guided Search
    123070, -- 2610.10288 TouchScale: 500 Hours of Human Vision and Touch for Visual-Tactile Learning
    123157, -- 2608.03391 TimeRLM: Recursive Language Models Enable Precise Anomaly Localization in Long-C
    123195, -- 2609.39600 GroundAnything: Reconciling Parallel Decoding with Precise Visual Grounding at F
    123276, -- 2610.18615 VideoJev: System One Model for Video Understanding and Interaction
    123286, -- 2610.18356 Urbex: Agentic Spatial Grounding for City-Scale 3D Scenes
    123637, -- 1709.03410 One-Shot Learning for Semantic Segmentation
    123660, -- 2303.15743 HS-Pose: Hybrid Scope Feature Extraction for Category-level Object Pose Estimati
    123741, -- 2610.23279 Xiaomi-Lens-0 Technical Report
    123743, -- 2610.22306 ARC-SORT: Adaptive, Robust, Compensated Multi-Object Tracking with Interacting M
    123869, -- 2610.19419 WinARDet: Compressed Window Auto-Regression for Long-Horizon Vision-Language Gro
    123895, -- 2610.22444 Event-STVG: Spatio-Temporal Video Grounding for Long-Form Event Reasoning
    123921, -- 2211.09074 Where a Strong Backbone Meets Strong Features -- ActionFormer for Ego4D Moment Q
    124000, -- 2610.26659 SpatialScout: Can VLM Agents Actively Explore and Map 3D Scenes?
    124031, -- 2610.30340 Foundation4D: Towards a unified perception and reconstruction model for autonomo
    124038, -- 2610.28889 Policy-Mask: Budget-Aware Adaptation of Diffusion Features to Discriminative Tas
    124147, -- external Cross-Foundation Complementary Learning Systems for Continual Test-Time Adaptati
    124222, -- external Foveal-Mamba: Inside-Out Ring Scanning with Recurrent Offset Prediction for Visu
    124443, -- external DAGA: Dynamic Attention-Guided Adaptation for Self-Supervised Vision Transformer
    124452, -- 2606.10594 Segment and Select: Vision-Language Segmentation in 3D Scenarios
    124475, -- 2605.29858 Masked Diffusion Vision-Language Models for Temporal Action Localization
    124560, -- 2609.40317 GLARE: Generating Listening Heads with Appropriate REactions
    124655, -- 2607.16189 Searching Videos as Trees: Self-Correcting Agents for Grounded Long Video QA
    124860, -- external FuseAdapt: Adaptation-Space Fusion for Multi-Modal Semantic Segmentation with Mi
    124973, -- 2602.19274 DD-CAM: Minimal Sufficient Explanations for Vision Models Using Delta Debugging
    125244, -- external Prism: Harmonizing Missing Modalities via Implicit Structural Alignment on Light
    125402, -- external MatCurvs: Article Real-Coordinate Curve Extraction for Agent-Ready Materials Rea
    125597, -- external ClusterSplat: Semantic Cluster Selection for 3D Visual Grounding in Gaussian Spl
    125681, -- external WaveMamba: Wave-Inspired Cross-Modal Fusion for Robust event-image Semantic Segm
    125725, -- external Beyond Hard Negatives: Grounded Positive Supervision for Compositional CLIP
    125938, -- external Uncertainty as an Underconstrained Axis in Lossy Compression
    125981, -- external Beyond Pixel-wise Supervision: Local Structure Regularization for Semantic Segme
    126037, -- 2610.10044 CANDO: Cooperative Agentic Network for Layout Design Optimization
    126407, -- external StainNFT: Curriculum-Gated Multi-Reward Post-Training for Pathology-Faithful Vir
    126923, -- external Post-Processing Guarantees for Classification under Linear-Fractional Performanc
    126938, -- 2605.27924 SIGMA: Semantic-Difference Instruction-Grounding Mask Annotator for Text-Driven
    126976, -- 2605.20110 SetCon: Towards Open-Ended Referring Segmentation via Set-Level Concept Predicti
    127017, -- 2605.11723 CaC: Advancing Video Reward Models via Hierarchical Spatiotemporal Concentrating
    127100, -- external LayoutBridge: Anisotropic Brownian Bridges for Public Indoor Floorplan Generatio
    127211, -- 2606.14701 RATS! Patches Talk Through Registers: Emergent Parts in Register Attention Trans
    127460, -- external Reasoning-based Spatial Prior (RSP): Learning Spatial Priors from Multimodal LLM
    127498, -- external Online Maximization of Non-Decomposable Test and Population Utilities
    127512, -- external MSR-3D: Multi-Mode Semantic Representation for Open-Vocabulary 3D Scene Understa
    127711, -- 2609.39265 Universal Cross-Prompt Adversarial Attacks on Promptable Concept Segmentation
    128077, -- external FreeOcc: Decoupling Ego-Motion for Efficient 4D Occupancy Forecasting via Contin
    128271, -- 2608.29081 AdapToPASS: Ambiguity-aware Adaptive Spherical Transformer for Panoramic Semanti
    128303, -- external $\mathbf{D^{3}S^{2}}$: Diffusion-Guided Dataset Distillation for Semantic Segmen
    128331, -- external DASM: Dynamic Autoregressive Subgraph Mining via Two-Stage Policy Alignment
    128748, -- 2610.02019 Controllable Multi-label Video Safety Detection via Adaptive Tversky Policy Opti
    128970, -- external See to Believe: Segmentation by Reasoning with Visual Evidence
    129004, -- 2605.15923 Invaria: Learning Scale and Density Invariance in Point Clouds via Next-Resoluti
    129429, -- external LaSA-Net: A Language-Guided Network for Outdoor Generalized 3D Referring Express
    129461, -- 2609.38930 On the Relaxation of Conditional Independence Assumption for Image Segmentation
    129710, -- external DriftWeight: Repulsive Drift in Mean-Flow Space for Neural Network Weight Genera
    129800, -- 2609.28684 M-plicits: Neural Implicit Surfaces via Nested Multiscale Residuals
    130069, -- 2603.24713 Lookalike3D: Seeing Double in 3D
    130076, -- 2610.16177 DIGS: Distribution-Informed Gaussian Splatting for Training-Free Open-Vocabulary
    130349, -- 2610.20881 Pixels to Tokens: Token Space Efficient Active Learning for Low-Budget Semantic
    130373, -- external SPEXT: A Decoupled Multi-Spectral Foundation Model for Earth Observation and Vis
    130377, -- external Hierarchical Cross-Class Part Alignment for Prototypical Part Networks via Hyper
    130417, -- 2605.08172 Augmented Equivariant Mesh Networks for Anatomical Segmentation
    130550, -- external Open-Vocabulary 3D Part Segmentation with Semantic Propagation Hawkes Process
    130586, -- external ChiP-STAR: Spatial-Topological Attention for Pre-trained Generative Chip Routing
    130730, -- external Causal Gradient Steering: Exposing Shortcut Gradients by Destroying Causal Signa
    130751, -- external Progressive Signal Calibration for Medical Image Segmentation: Diagnosing and Co
    131082, -- external Relational Feature Distillation for Lightweight 3D Point Cloud Segmentation
    131303, -- 2610.29552 Generalized CycleGRPO for Fine-Grained Multimodal Understanding and Grounding
    131333, -- 2508.09796 MeMoSORT: Memory-Assisted Filtering and Motion-Adaptive Association Metric for M
    131335, -- 2606.13033 Selective Mask Propagation for Multi-Object Tracking
    131358, -- 2608.25710 Difficulty-Aware Sample Allocation for Adaptive Data Augmentation in Semantic Se
    131450, -- 2610.35450 OBB-PBD: Extending Parallel Box Decoding to Oriented Bounding Boxes for Referrin
    131459, -- 2610.28490 Learning from Automatic 3D Gaussian Splatting Edits for Online Bayesian Scene Ch
    131720, -- 2610.29409 LLMSeg: Training-Free Text-Prompted Image Segmentation with B-Splines
    131780 -- 2611.02897 PhotoGuider: Composition-Aware Cropping and 360^{circ} View Framing with Explain
  );

DELETE FROM paper_method_exclusions x
USING iou_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM iou_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM iou_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- mean-average-precision-map: 706 links (title/abstract names the metric).
CREATE TEMP TABLE map_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mean-average-precision-map'
  AND p.id IN (
    54, -- 1311.2524 Rich feature hierarchies for accurate object detection and semantic segmentation
    181, -- 1504.08083 Fast R-CNN
    201, -- 1506.02640 You Only Look Once: Unified, Real-Time Object Detection
    284, -- 1512.02325 SSD: Single Shot MultiBox Detector
    554, -- 1612.08242 YOLO9000: Better, Faster, Stronger
    667, -- 1704.04503 Soft-NMS -- Improving Object Detection With One Line of Code
    729, -- 1705.08421 AVA: A Video Dataset of Spatio-temporally Localized Atomic Visual Actions
    812, -- 1707.07012 Learning Transferable Architectures for Scalable Image Recognition
    837, -- 1708.02901 Transitive Invariance for Self-supervised Visual Representation Learning
    1056, -- 1801.05918 Extend the shallow part of Single Shot MultiBox Detector via Convolutional Neura
    1083, -- 1802.00977 Pose Flow: Efficient Online Pose Tracking
    1096, -- 1802.03750 FD-MobileNet: Improved MobileNet with a Fast Downsampling Strategy
    1168, -- 1803.07728 Unsupervised Representation Learning by Predicting Image Rotations
    1210, -- 1804.02767 YOLOv3: An Incremental Improvement
    1413, -- 1807.11626 MnasNet: Platform-Aware Neural Architecture Search for Mobile
    1546, -- 1810.06470 Unsupervised Deep Features for Remote Sensing Image Matching via Discriminator N
    1671, -- 1812.00324 CrowdPose: Efficient Crowded Scenes Pose Estimation and A New Benchmark
    1708, -- 1812.07003 3D-SIS: 3D Semantic Instance Segmentation of RGB-D Scans
    1746, -- 1901.03353 RetinaMask: Learning to predict masks improves state-of-the-art single-shot dete
    1864, -- 1903.00621 Feature Selective Anchor-Free Module for Single-Shot Object Detection
    1962, -- 1904.02689 YOLACT: Real-time Instance Segmentation
    2408, -- 1908.04067 Explicit Shape Encoding for Real-Time Instance Segmentation
    2618, -- 1909.13719 RandAugment: Practical automated data augmentation with a reduced search space
    2912, -- 1912.03538 Context R-CNN: Long Term Temporal Context for Per-Camera Object Detection
    2927, -- 1912.06218 YOLACT++: Better Real-time Instance Segmentation
    3461, -- 2004.14525 MobileDets: Searching for Object Detection Architectures for Mobile Accelerators
    3655, -- 2006.02049 FBNetV3: Joint Architecture-Recipe Search using Predictor Pretraining
    3912, -- 2007.09397 Weakly Supervised Instance Segmentation by Learning Annotation Consistent Instan
    4225, -- 2009.14119 Asymmetric Loss For Multi-Label Classification
    4588, -- 2011.10043 Propagate Yourself: Exploring Pixel-Level Consistency for Unsupervised Visual Re
    4674, -- 2012.02994 Attention-Driven Dynamic Graph Convolutional Network for Multi-Label Image Recog
    4701, -- 2012.04689 A Dataset and Application for Facial Recognition of Individual Gorillas in Zoo E
    4716, -- 2012.06060 Spatially Conditioned Graphs for Detecting Human-Object Interactions
    4972, -- 2102.01243 PSLA: Improving Audio Tagging with Pretraining, Sampling, Labeling, and Aggregat
    5040, -- 2102.07831 NeuralNDCG: Direct Optimisation of a Ranking Metric via Differentiable Relaxatio
    5140, -- 2103.02340 General Instance Distillation for Object Detection
    5375, -- 2104.01778 AST: Audio Spectrogram Transformer
    5562, -- 2104.11178 VATT: Transformers for Multimodal Self-Supervised Learning from Raw Video, Audio
    5571, -- 2104.11896 M3DeTR: Multi-representation, Multi-scale, Mutual-relation 3D Object Detection w
    5599, -- 2104.13582 [Re] Don't Judge an Object by Its Context: Learning to Overcome Contextual Bias
    5635, -- 2105.01147 Sketches image analysis: Web image search engine usingLSH index and DNN Inceptio
    6019, -- 2106.09018 End-to-End Semi-Supervised Object Detection with Soft Teacher
    6107, -- 2106.12930 VinDr-SpineXR: A deep learning framework for spinal lesions detection and classi
    6329, -- 2107.14222 Rethinking and Improving Relative Position Encoding for Vision Transformer
    6555, -- 2109.02613 Class Semantics-based Attention for Action Detection
    7001, -- 2110.09455 TLDR: Twin Learning for Dimensionality Reduction
    7042, -- 2110.12370 Team Enigma at ArgMining-EMNLP 2021: Leveraging Pre-trained Language Models for
    7086, -- 2110.15352 MCUNetV2: Memory-Efficient Patch-based Inference for Tiny Deep Learning
    7168, -- 2111.03789 Generation of microbial colonies dataset with deep learning style transfer
    7175, -- 2111.04204 Natural Adversarial Objects
    7261, -- 2111.10007 FBNetV5: Neural Architecture Search for Multiple Tasks in One Run
    7284, -- 2111.11432 Florence: A New Foundation Model for Computer Vision
    7337, -- 2111.14821 End-to-End Referring Video Object Segmentation with Multimodal Transformers
    7550, -- 2112.09133 Masked Feature Prediction for Self-Supervised Visual Pre-Training
    7638, -- 2201.00487 Language as Queries for Referring Video Object Segmentation
    7658, -- 2201.02605 Detecting Twenty-thousand Classes using Image-level Supervision
    7682, -- 2201.04388 OCSampler: Compressing Videos to One Clip with Single-step Sampling
    7685, -- 2201.04620 SparseDet: Improving Sparsely Annotated Object Detection with Pseudo-positive Mi
    7873, -- 2202.02524 PrivPAS: A real time Privacy-Preserving AI System and applied ethics
    8049, -- 2202.11921 Auto-scaling Vision Transformers without Training
    8135, -- 2203.01929 CenterSnap: Single-Shot Multi-Object 3D Shape Reconstruction and Categorical 6D
    8179, -- 2203.04251 End-to-End Semi-Supervised Learning for Video Action Detection
    8204, -- 2203.05625 PETR: Position Embedding Transformation for Multi-View 3D Object Detection
    8302, -- 2203.09035 HybridNets: End-to-End Perception Network
    8383, -- 2203.11926 Focal Modulation Networks
    8436, -- 2203.14215 Knowledge Mining with Scene Text for Fine-Grained Recognition
    8486, -- 2203.16220 Target-aware Dual Adversarial Learning and a Multi-scenario Multi-Modality Bench
    8562, -- 2204.01719 RestoreX-AI: A Contrastive Approach towards Guiding Image Restoration via Explai
    8608, -- 2204.03359 ECCV Caption: Correcting False Negatives by Collecting Machine-and-Human-verifie
    8721, -- 2204.07143 Neighborhood Attention Transformer
    8911, -- 2205.01271 Lite Pose: Efficient Architecture Design for 2D Human Pose Estimation
    8932, -- 2205.02151 Dual Cross-Attention Learning for Fine-Grained Visual Categorization and Object
    9121, -- 2205.11098 PointDistiller: Structured Knowledge Distillation Towards Efficient and Compact
    9220, -- 2205.13542 BEVFusion: Multi-Task Multi-Sensor Fusion with Unified Bird's-Eye View Represent
    9329, -- 2206.01062 DocLayNet: A Large Human-Annotated Dataset for Document-Layout Analysis
    9494, -- 2206.07846 Action Spotting using Dense Detection Anchors Revisited: Submission to the Socce
    9527, -- 2206.08920 VectorMapNet: End-to-end Vectorized HD Map Learning
    9529, -- 2206.08977 BN-HTRd: A Benchmark Dataset for Document Level Offline Bangla Handwritten Text
    9671, -- 2207.00531 Masked Autoencoder for Self-Supervised Pre-training on Lidar Point Clouds
    9686, -- 2207.01614 Beyond mAP: Towards better evaluation of instance segmentation
    9765, -- 2207.05501 Next-ViT: Next Generation Vision Transformer for Efficient Deployment in Realist
    9874, -- 2207.11209 Divide and Conquer: 3D Point Cloud Instance Segmentation With Point-Wise Binariz
    9920, -- 2207.13691 ShAPO: Implicit Representations for Multi-Object Shape, Appearance, and Pose Opt
    9997, -- 2208.03987 Advancing Plain Vision Transformer Towards Remote Sensing Foundation Model
    10056, -- 2208.07407 SemAug: Semantically Meaningful Image Augmentations for Object Detection Through
    10157, -- 2208.13040 YOLOX-PAI: An Improved YOLOX, Stronger and Faster than YOLOv6
    10210, -- 2209.01335 Neural Approaches to Multilingual Information Retrieval
    10214, -- 2209.01589 Consistent-Teacher: Towards Reducing Inconsistent Pseudo-targets in Semi-supervi
    10215, -- 2209.01620 MAFormer: A Transformer Network with Multi-scale Attention Fusion for Visual Rec
    10604, -- 2210.03105 Mask3D: Mask Transformer for 3D Semantic Instance Segmentation
    10656, -- 2210.04264 CAGroup3D: Class-Aware Grouping for 3D Object Detection on Point Clouds
    10686, -- 2210.05063 Improving Dense Contrastive Learning with Dense Negative Pairs
    10870, -- 2210.09461 Token Merging: Your ViT But Faster
    10920, -- 2210.11078 Large-batch Optimization for Dense Visual Predictions
    11247, -- 2211.03679 Body Part-Based Representation Learning for Occluded Person Re-Identification
    11297, -- 2211.05778 InternImage: Exploring Large-Scale Vision Foundation Models with Deformable Conv
    11326, -- 2211.07091 BiViT: Extremely Compressed Binary Vision Transformer
    11429, -- 2211.10156 DETRDistill: A Universal Knowledge Distillation Framework for DETR-families
    11589, -- 2211.13523 Roboflow 100: A Rich, Multi-Domain Object Detection Benchmark
    11641, -- 2211.14710 3DPPE: 3D Point Positional Encoding for Multi-Camera 3D Object Detection Transfo
    11661, -- 2211.15444 DAMO-YOLO : A Report on Real-Time Object Detection Design
    11735, -- 2212.00280 GRiT: A Generative Region-to-text Transformer for Object Understanding
    11786, -- 2212.01424 PROB: Probabilistic Objectness for Open World Object Detection
    11933, -- 2212.06137 NMS Strikes Back
    12047, -- 2212.09058 BEATs: Audio Pre-Training with Acoustic Tokenizers
    12282, -- 2301.00805 Betrayed by Captions: Joint Caption Grounding and Generation for Open Vocabulary
    12451, -- 2301.08237 LoCoNet: Long-Short Context Network for Active Speaker Detection
    12480, -- 2301.09268 PCBDet: An Efficient Deep Neural Network Object Detection Architecture for Autom
    12653, -- 2301.12689 Edge-guided Multi-domain RGB-to-TIR image Translation for Training Vision Tasks
    12762, -- 2302.00837 SHINE: Deep Learning-Based Accessible Parking Management System
    12899, -- 2302.03162 Protecting Language Generation Models via Invisible Watermarking
    13193, -- 2302.09569 SEMI-PointRend: Improved Semiconductor Wafer Defect Classification and Segmentat
    13491, -- 2303.02489 CapDet: Unifying Dense Captioning and Open-World Detection Pretraining
    13508, -- 2303.02936 UniHCP: A Unified Model for Human-Centric Perceptions
    13532, -- 2303.03595 LoGoNet: Towards Accurate 3D Object Detection with Local-to-Global Cross-Modal F
    13566, -- 2303.04439 A Light Weight Model for Active Speaker Detection
    13634, -- 2303.05892 Object-Aware Distillation Pyramid for Open-Vocabulary Object Detection
    13640, -- 2303.05970 Exploring Recurrent Long-term Temporal Fusion for Multi-view 3D Perception
    13642, -- 2303.06015 Dynamic Y-KD: A Hybrid Approach to Continual Instance Segmentation
    13720, -- 2303.07347 TriDet: Temporal Action Detection with Relative Boundary Modeling
    13745, -- 2303.07820 Adaptive Rotated Convolution for Rotated Object Detection
    13774, -- 2303.08316 MSF: Motion-guided Sequential Fusion for Efficient 3D Object Detection from Poin
    13790, -- 2303.08747 Cascaded Zoom-in Detector for High Resolution Aerial Images
    13803, -- 2303.08983 Reinforce Data, Multiply Impact: Improved Model Accuracy and Robustness with Dat
    13804, -- 2303.08998 Unified Visual Relationship Detection with Vision and Language Models
    13806, -- 2303.09030 Large Selective Kernel Network for Remote Sensing Object Detection
    13968, -- 2303.11855 CLIP-ReIdent: Contrastive Training for Player Re-Identification
    13975, -- 2303.11926 Exploring Object-Centric Temporal Modeling for Efficient Multi-View 3D Object De
    14024, -- 2303.12766 Spherical Transformer for LiDAR-based 3D Recognition
    14072, -- 2303.13510 MV-JAR: Masked Voxel Jigsaw and Reconstruction for LiDAR-Based Self-Supervised P
    14170, -- 2303.15083 UniDistill: A Universal Cross-Modality Knowledge Distillation Framework for 3D O
    14210, -- 2303.15782 CARTO: Category and Joint Agnostic Reconstruction of ARTiculated Objects
    14294, -- 2303.17225 FreeSeg: Unified, Universal and Open-Vocabulary Image Segmentation
    14377, -- 2304.00670 CRN: Camera Radar Net for Accurate, Robust, Efficient 3D Perception
    14396, -- 2304.00967 Temporal Enhanced Training of Multi-view 3D Object Detector via Historical Objec
    14453, -- 2304.01974 Dialogue-Contextualized Re-ranking for Medical History-Taking
    14496, -- 2304.02934 Boundary-Denoising for Video Activity Localization
    14500, -- 2304.03105 Geometric-aware Pretraining for Vision-centric 3D Object Detection
    14550, -- 2304.04179 Sparse Dense Fusion for 3D Object Detection
    14561, -- 2304.04385 On Robustness in Multimodal Learning
    14696, -- 2304.06906 Swin3D: A Pretrained Transformer Backbone for 3D Indoor Scene Understanding
    14745, -- 2304.08451 Efficient Video Action Detection with Token Dropout and Context Refinement
    14792, -- 2304.09469 Baybayin Character Instance Detection
    14959, -- 2304.13031 DQS3D: Densely-matched Quantization-aware Semi-supervised 3D Detection
    15045, -- 2304.14614 Fusion is Not Enough: Single Modal Attacks on Fusion Models for 3D Object Detect
    15381, -- 2305.05586 RLocator: Reinforcement Learning for Bug Localization
    15495, -- 2305.07528 WEDGE: A multi-weather autonomous driving dataset built from generative vision-l
    15512, -- 2305.07825 Student Classroom Behavior Detection based on YOLOv7-BRA and Multi-Model Fusion
    15641, -- 2305.09972 Real-Time Flying Object Detection with YOLOv8
    15738, -- 2305.11173 Going Denser with Open-Vocabulary Part Segmentation
    15739, -- 2305.11175 VisionLLM: Large Language Model is also an Open-Ended Decoder for Vision-Centric
    16266, -- 2305.15701 Action Sensitivity Learning for Temporal Action Localization
    16731, -- 2306.00349 CALICO: Self-Supervised Camera-LiDAR Contrastive Pre-training for BEV Perception
    17133, -- 2306.04849 ScaleDet: A Scalable Multi-Dataset Object Detector
    17226, -- 2306.06023 DetZero: Rethinking Offboard 3D Object Detection with Long-term Sequential Point
    17353, -- 2306.07703 E2E-LOAD: End-to-End Long-form Online Action Detection
    17377, -- 2306.07952 MOFI: Learning Image Representations from Noisy Entity Annotated Images
    17419, -- 2306.08528 Predict to Detect: Prediction-guided 3D Object Detection using Sequential Images
    17738, -- 2306.14035 Thinking Like an Annotator: Generation of Dataset Labeling Instructions
    17907, -- 2306.17404 QuAVF: Quality-aware Audio-Visual Fusion for Ego4D Talking to Me Challenge
    18276, -- 2307.07944 Revisiting Domain-Adaptive 3D Object Detection by Reliable, Diverse and Class-ba
    18323, -- 2307.08579 Scale-Aware Modulation Meet Transformer
    18478, -- 2307.11035 Cascade-DETR: Delving into High-Quality Universal Object Detection
    18482, -- 2307.11077 AlignDet: Aligning Pre-training and Fine-tuning in Object Detection
    18591, -- 2307.12972 DFA3D: 3D Deformable Attention For 2D-to-3D Feature Lifting
    18683, -- 2307.14605 Clustering based Point Cloud Representation Learning for 3D Analysis
    18685, -- 2307.14620 NeRF-Det: Learning Geometry-Aware Volumetric Representation for Multi-View 3D Ob
    18744, -- 2307.15516 YOLOv8 for Defect Inspection of Hexagonal Directed Self-Assembly Patterns: A Dat
    18790, -- 2307.16617 FULLER: Unified Multi-modality Multi-task 3D Perception via Multi-level Gradient
    18881, -- 2308.01526 Data Augmentation for Human Behavior Analysis in Multi-Person Conversations
    18902, -- 2308.01904 DETR Doesn't Need Multi-Scale or Locality Design
    18989, -- 2308.03322 Part-Aware Transformer for Generalizable Person Re-identification
    19003, -- 2308.03594 FeatEnHancer: Enhancing Hierarchical Features for Object Detection and Beyond Un
    19059, -- 2308.04556 FocalFormer3D : Focusing on Hard Instance for 3D Object Detection
    19075, -- 2308.04770 Objects do not disappear: Video object detection by single-frame object location
    19104, -- 2308.05359 Pseudo-label Alignment for Semi-supervised Instance Segmentation
    19269, -- 2308.07737 Identity-Consistent Aggregation for Video Object Detection
    19309, -- 2308.08182 Unsupervised Domain Adaptive Detection with Network Stability Analysis
    19323, -- 2308.08370 Agglomerative Transformer for Human-Object Interaction Detection
    19396, -- 2308.09351 RLIPv2: Fast Scaling of Relational Language-Image Pre-training
    19417, -- 2308.09564 Deep Equilibrium Object Detection
    19514, -- 2308.10308 Representation Disparity-aware Distillation for 3D Object Detection
    19604, -- 2308.11194 ViLLA: Fine-Grained Vision-Language Representation Learning from Real-World Data
    19699, -- 2308.12216 SG-Former: Self-guided Transformer with Evolving Token Reallocation
    19869, -- 2308.14659 RESTORE: Graph Embedding Assessment Through Reconstruction
    19963, -- 2308.16477 PivotNet: Vectorized Pivot Learning for End-to-end HD Map Construction
    19967, -- 2308.16551 Object Detection for Caries or Pit and Fissure Sealing Requirement in Children's
    20067, -- 2309.01430 DAT++: Spatially Dynamic Vision Transformer with Deformable Attention
    20200, -- 2309.03893 DiffusionEngine: Diffusion Model is Scalable Data Engine for Object Detection
    20374, -- 2309.07084 SupFusion: Supervised LiDAR-Camera Fusion for 3D Object Detection
    20536, -- 2309.09297 Chasing Day and Night: Towards Robust and Efficient All-Day Object Detection Gui
    20757, -- 2309.12585 BGF-YOLO: Enhanced YOLOv8 with Multiscale Attentional Feature Fusion for Brain T
    20784, -- 2309.12969 Detect Everything with Few Examples
    21078, -- 2309.17134 Promoting Generalized Cross-lingual Question Answering in Few-resource Scenarios
    21275, -- 2310.01641 You Only Look at Once for Real-time and Generic Multi-Task
    21392, -- 2310.02960 CoDA: Collaborative Novel Box Discovery and Cross-modal Alignment for Open-vocab
    22012, -- 2310.10038 Smart City Transportation: Deep Learning Ensemble Approach for Traffic Accident
    22390, -- 2310.14817 Text2Topic: Multi-Label Text Classification System for Efficient Topic Detection
    22429, -- 2310.15200 Open-Set Image Tagging with Multi-Grained Text Supervision
    22822, -- 2310.20695 HAP: Structure-Aware Masked Image Modeling for Human-Centric Perception
    22907, -- 2311.01373 Recognize Any Regions
    23003, -- 2311.03354 CoVLM: Composing Visual Entities and Relationships in Large Language Models Via
    23141, -- 2311.05613 Window Attention is Bugged: How not to Interpolate Position Embeddings
    23574, -- 2311.12068 Enhancing Novel Object Detection via Cooperative Foundational Models
    23715, -- 2311.14405 OneFormer3D: One Transformer for Unified Point Cloud Segmentation
    23927, -- 2311.17132 TransNeXt: Robust Foveal Visual Perception for Vision Transformers
    24446, -- 2312.04519 Bootstrapping Autonomous Driving Radars with Self-Supervised Learning
    24557, -- 2312.05745 Open World Object Detection in the Era of Foundation Models
    25218, -- 2312.16108 LaneSegNet: Map Learning with Lane Segment Perception for Autonomous Driving
    25391, -- 2401.00912 ScatterFormer: Efficient Voxel Transformer with Scattered Linear Attention
    25970, -- 2401.09709 P2Seg: Pointly-supervised Segmentation via Mutual Distillation
    25973, -- 2401.09732 Instance Brownian Bridge as Texts for Open-vocabulary Video Instance Segmentatio
    25984, -- 2401.09923 MAMBA: Multi-level Aggregation via Memory Bank for Video Object Detection
    26172, -- 2401.12513 Detecting and recognizing characters in Greek papyri with YOLOv8, DeiT and SimCL
    26874, -- 2402.03634 Ray Denoising: Depth-aware Hard Negative Sampling for Multi-view 3D Object Detec
    26951, -- 2402.04408 Detection Transformer for Teeth Detection, Segmentation, and Numbering in Oral R
    26963, -- 2402.04555 FM-Fusion: Instance-aware Semantic Mapping Boosted by Vision-Language Foundation
    28585, -- 2403.05419 Rethinking Transformers Pre-training for Multi-Spectral Satellite Imagery
    28950, -- 2403.10722 Cannabis Seed Variant Detection using Faster R-CNN
    29215, -- 2403.13803 Bounding Box Stability against Feature Dropout Reflects Detector Generalization
    29329, -- 2403.15313 CR3DT: Camera-RADAR Fusion for 3D Detection and Tracking
    29379, -- 2403.15951 MapTracker: Tracking with Strided Memory Fusion for Consistent Vector HD Mapping
    29648, -- 2403.19926 Video-Based Human Pose Regression via Decoupled Space-Time Aggregation
    29730, -- 2404.00679 Weak-to-Strong 3D Object Detection with X-Ray Distillation
    29810, -- 2404.01501 MosquitoFusion: A Multiclass Dataset for Real-Time Detection of Mosquitoes, Swar
    29899, -- 2404.02877 FlightScope: An Experimental Comparative Review of Aircraft Detection Algorithms
    29940, -- 2404.03507 DQ-DETR: DETR with Dynamic Query for Tiny Object Detection
    30352, -- 2404.09530 RanLayNet: A Dataset for Document Layout Detection used for Domain Adaptation an
    30803, -- 2404.16944 Constellation Dataset: Benchmarking High-Altitude Object Detection for an Urban
    31116, -- 2405.04305 A New Dataset and Comparative Study for Aphid Cluster Detection and Segmentation
    31563, -- 2405.14174 Multi-Scale VMamba: Hierarchy in Hierarchy Visual State Space Model
    31665, -- 2405.15199 ODGEN: Domain-specific Object Detection Data Generation with Diffusion Models
    32104, -- 2405.20462 Multi-Label Guided Soft Contrastive Learning for Efficient Earth Observation Pre
    32320, -- 2406.02548 Open-YOLO 3D: Towards Fast and Accurate Open-Vocabulary 3D Instance Segmentation
    32399, -- 2406.03747 Instance Segmentation and Teeth Classification in Panoramic X-rays
    32576, -- 2406.05835 Mamba YOLO: A Simple Baseline for Object Detection with State Space Model
    32756, -- 2406.07833 Sense Less, Generate More: Pre-training LiDAR Perception with Masked Autoencoder
    32788, -- 2406.08226 DistilDoc: Knowledge Distillation for Visually-Rich Document Applications
    32921, -- 2406.09647 OpenAnimalTracks: A Dataset for Animal Track Recognition
    32932, -- 2406.09788 OpenCapBench: A Benchmark to Bridge Pose Estimation and Biomechanics
    33219, -- 2406.12225 The Solution for CVPR2024 Foundational Few-Shot Object Detection Challenge
    33383, -- 2406.14239 LeYOLO, New Scalable and Efficient CNN Architecture for Object Detection
    34031, -- 2407.02182 Occlusion-Aware Seamless Segmentation
    34063, -- 2407.02585 Novel Human Machine Interface via Robust Hand Gesture Recognition System using C
    34066, -- 2407.02665 SMILe: Leveraging Submodular Mutual Information For Robust Few-Shot Object Detec
    34172, -- 2407.04082 DASS: Distilled Audio State Space Models Are Stronger and More Duration-Scalable
    34188, -- 2407.04287 MARS: Paying more attention to visual attributes for text-based person search
    34415, -- 2407.07427 Unified Embedding Alignment for Open-Vocabulary Video Instance Segmentation
    34501, -- 2407.08634 RTMW: Real-Time Multi-Person 2D and 3D Whole-body Pose Estimation
    34615, -- 2407.10083 Plain-Det: A Plain Multi-Dataset Object Detector
    34661, -- 2407.10753 OPEN: Object-wise Position Embedding for Multi-view 3D Object Detection
    34781, -- 2407.12040 Comprehensive Performance Evaluation of YOLO11, YOLOv10, YOLOv9 and YOLOv8 on De
    34907, -- 2407.13517 Mask2Map: Vectorized HD Map Construction Using Bird's Eye View Segmentation Mask
    35179, -- 2407.17722 Text-Driven Neural Collaborative Filtering Model for Paper Source Tracing
    35442, -- 2408.00701 Joint Neural Networks for One-shot Object Recognition and Detection
    35502, -- 2408.01471 Enhancing Online Road Network Perception and Reasoning with Standard Definition
    35686, -- 2408.04745 AI for operational methane emitter monitoring from space
    35792, -- 2408.06803 Integrating Saliency Ranking and Reinforcement Learning for Enhanced Object Dete
    36147, -- 2408.12569 Sapiens: Foundation for Human Vision Models
    36349, -- 2408.16123 ChartEye: A Deep Learning Framework for Chart Information Extraction
    36440, -- 2409.00204 MedDet: Generative Adversarial Distillation for Efficient Cervical Disc Herniati
    36649, -- 2409.04234 UniDet3D: Multi-dataset Indoor 3D Object Detection
    37425, -- 2409.18569 Cross-video Identity Correlating for Person Re-identification Pre-training
    37436, -- 2409.18866 MCUBench: A Benchmark of Tiny Object Detectors on MCUs
    37671, -- 2410.01647 3DGS-DET: Empower 3D Gaussian Splatting with Boundary Guidance and Box-Focused S
    38347, -- 2410.09324 Token Pruning using a Lightweight Background Aware Vision Transformer
    39044, -- 2410.17725 YOLOv11: An Overview of the Key Architectural Enhancements
    39423, -- 2410.23608 Context-Aware Token Selection and Packing for Enhanced Vision Transformer
    39628, -- 2411.02537 INQUIRE: A Natural World Text-to-Image Retrieval Benchmark
    40042, -- 2411.10316 M3TR: A Generalist Model for Real-World HD Map Completion
    40044, -- 2411.10332 Number it: Temporal Grounding Videos like Flipping Manga
    40100, -- 2411.11285 Zero-Shot Automatic Annotation and Instance Segmentation using LLM-Generated Dat
    40322, -- 2411.15110 A Real-Time DETR Approach to Bangladesh Road Object Detection for Autonomous Veh
    40363, -- 2411.15497 AeroGen: Enhancing Remote Sensing Object Detection with Diffusion-Driven Data Ge
    40566, -- 2411.17991 VideoLLM Knows When to Speak: Enhancing Time-Sensitive Video Comprehension with
    40937, -- 2412.02890 EvRT-DETR: Latent Space Adaptation of Image Detectors for Event-based Vision
    41242, -- 2412.06674 EMOv2: Pushing 5M Vision Model Frontier
    41679, -- 2412.11949 Coconut Palm Tree Counting on Drone Images with Deep Object Detection and Synthe
    42192, -- 2412.18806 FOR: Finetuning for Object Level Open Vocabulary Image Retrieval
    42480, -- 2501.02376 Origin Identification for Text-Guided Image-to-Image Diffusion Models
    42570, -- 2501.03767 AutoFish: Dataset and Benchmark for Fine-grained Analysis of Fish
    42573, -- 2501.03836 SCC-YOLO: An Improved Object Detector for Assisting in Brain Tumor Diagnosis
    42599, -- 2501.04206 GRAPHITE: Graph-Based Interpretable Tissue Examination for Enhanced Explainabili
    42645, -- 2501.04950 MORDA: A Synthetic Dataset to Facilitate Adaptation of Object Detectors to Unsee
    43613, -- 2502.01896 INTACT: Inducing Noise Tolerance through Adversarial Curriculum Training for LiD
    43662, -- 2502.02501 Graph-based Document Structure Analysis
    44006, -- 2502.07223 Graph RAG-Tool Fusion
    44458, -- 2502.12524 YOLOv12: Attention-Centric Real-Time Object Detectors
    44616, -- 2502.14063 PedDet: Adaptive Spectral Optimization for Multimodal Pedestrian Detection
    45222, -- 2502.21201 The PanAf-FGBG Dataset: Understanding the Impact of Backgrounds in Wildlife Beha
    45233, -- 2503.00057 Improved YOLOv12 with LLM-Generated Synthetic Data for Enhanced Apple Detection
    45288, -- 2503.00938 From Poses to Identity: Training-Free Person Re-Identification via Feature Centr
    45320, -- 2503.01342 UFO: A Unified Approach to Fine-grained Visual Perception via Open-ended Languag
    45500, -- 2503.03689 DualDiff+: Dual-Branch Diffusion for High-Fidelity Video Generation with Reward
    45579, -- 2503.04918 Fine-Tuning Florence2 for Enhanced Object Detection in Un-constructed Environmen
    45680, -- 2503.06307 ACAM-KD: Adaptive and Cooperative Attention Masking for Knowledge Distillation
    46441, -- 2503.15969 Beyond the Visible: Multispectral Vision-Language Learning for Earth Observation
    46536, -- 2503.17071 Superpowering Open-Vocabulary Object Detectors for X-ray Vision
    46544, -- 2503.17213 PP-DocLayout: A Unified Document Layout Detection Model to Accelerate Large-Scal
    46725, -- 2503.19658 BiblioPage: A Dataset of Scanned Title Pages for Bibliographic Metadata Extracti
    46731, -- 2503.19740 Surg-3M: A Dataset and Foundation Model for Perception in Surgical Settings
    46983, -- 2503.23109 Uncertainty-Instructed Structure Injection for Generalizable HD Map Construction
    47232, -- 2504.02534 Delineate Anything: Resolution-Agnostic Field Boundary Delineation on Satellite
    47479, -- 2504.07252 Few-Shot Adaptation of Grounding DINO for Agricultural Domain
    47858, -- 2504.13099 RF-DETR Object Detection vs YOLOv12 : A Study of Transformer-based and CNN-based
    47891, -- 2504.13469 HMPE:HeatMap Embedding for Efficient Transformer-Based Small Object Detection
    48035, -- 2504.15728 SAGA: Semantic-Aware Gray color Augmentation for Visible-to-Thermal Domain Adapt
    48074, -- 2504.16419 PixelWeb: The First Web GUI Dataset with Pixel-Wise Labels
    48197, -- 2504.19856 Efficient Domain-adaptive Continual Pretraining for the Process Industry in the
    48814, -- 2505.10931 M4-SAR: A Multi-Resolution, Multi-Polarization, Multi-Scene, Multi-Source Datase
    49099, -- 2505.13856 SuperMapNet for Long-Range and High-Accuracy Vectorized HD Map Construction
    49749, -- 2505.19569 What You Perceive Is What You Conceive: A Cognition-Inspired Framework for Open
    50418, -- 2506.01942 OD3: Optimization-free Dataset Distillation for Object Detection
    51018, -- 2506.10601 Semantic-decoupled Spatial Partition Guided Point-supervised Oriented Object Det
    51228, -- 2506.14629 VisText-Mosquito: A Multimodal Dataset and Benchmark for AI-Based Mosquito Breed
    51343, -- 2506.17733 YOLOv13: Real-Time Object Detection with Hypergraph-Enhanced Adaptive Visual Per
    51382, -- 2506.18807 PicoSAM2: Low-Latency Segmentation In-Sensor for Edge Vision Applications
    51454, -- 2506.20326 From Codicology to Code: A Comparative Study of Transformer and YOLO-based Detec
    51469, -- 2506.20609 Deciphering GunType Hierarchy through Acoustic Analysis of Gunshot Recordings
    51518, -- 2506.21484 TITAN: Query-Token based Domain Adaptive Adversarial Learning
    52547, -- 2508.19600 Quantization Robustness to Input Degradations for Object Detection
    52893, -- 2509.18056 TempSamp-R1: Effective Temporal Sampling with Reinforcement Fine-Tuning for Vide
    53300, -- 2510.06596 SDQM: Synthetic Data Quality Metric for Object Detection Dataset Evaluation
    54005, -- 2510.27224 Mask-to-Height: A YOLOv11-Based Architecture for Joint Building Instance Segment
    54189, -- 2505.20612 Roboflow100-VL: A Multi-Domain Object Detection Benchmark for Vision-Language Mo
    54283, -- 2511.16528 TurkColBERT: A Benchmark of Dense and Late-Interaction Models for Turkish Inform
    54315, -- 2511.15299 Taming Generative Synthetic Data for X-ray Prohibited Item Detection
    54485, -- 2512.00639 Doppler-Enhanced Deep Learning: Improving Thyroid Nodule Segmentation with YOLOv
    54790, -- 2512.08400 Towards Visual Re-Identification of Fish using Fine-Grained Classification for E
    55017, -- 2512.23273 YOLO-Master: MOE-Accelerated with Specialized Transformers for Enhanced Real-tim
    55255, -- 2601.05747 FlyPose: Towards Robust Human Pose Estimation From Aerial Views
    56385, -- 2603.00912 VGGT-Det: Mining VGGT Internal Priors for Sensor-Geometry-Free Multi-View Indoor
    56482, -- 2603.02924 HDINO: A Concise and Efficient Open-Vocabulary Detector
    56841, -- 2603.14482 V-JEPA 2.1: Unlocking Dense Features in Video Self-Supervised Learning
    57743, -- 2604.21681 Sapiens2
    58081, -- 2604.18632 StomaD2: An All-in-One System for Intelligent Stomatal Phenotype Analysis via Di
    58175, -- 2604.13939 A Multi-Stage Optimization Pipeline for Bethesda Cell Detection in Pap Smear Cyt
    58478, -- 2604.06245 CraterBench-R: Instance-Level Crater Retrieval for Planetary Scale
    58480, -- 2604.05212 Boxer: Robust Lifting of Open-World 2D Bounding Boxes to 3D
    59000, -- 2603.22841 UAV-DETR: DETR for Anti-Drone Target Detection
    59003, -- 2602.23029 WISER: Wider Search, Deeper Thinking, and Adaptive Fusion for Training-Free Zero
    59111, -- 2603.20034 CoverageBench: Evaluating Information Coverage across Tasks and Domains
    59181, -- 2506.02914 Auto-Annotation with Expert-Crafted Guidelines: A Study through 3D LiDAR Detecti
    59229, -- 2603.17357 WebPII: Benchmarking Visual PII Detection for Computer-Use Agents
    59367, -- 2603.12718 The COTe score: A decomposable framework for evaluating Document Layout Analysis
    59534, -- 2603.11557 TornadoNet: Real-Time Building Damage Detection with Ordinal Supervision
    59637, -- 2603.09245 Towards Instance Segmentation with Polygon Detection Transformers
    60020, -- 2603.02294 Loss Design and Architecture Selection for Long-Tailed Multi-Label Chest X-Ray C
    60043, -- 2603.01593 PPEDCRF: Privacy-Preserving Enhanced Dynamic CRF for Location-Privacy Protection
    60275, -- 2602.22073 AdaSpot: Spend Resolution Where It Matters for Precise Event Spotting
    60339, -- 2602.21141 SynthRender and IRIS: Open-Source Framework and Dataset for Bidirectional Sim-Re
    60693, -- 2602.13440 Learning on the Fly: Replay-Based Continual Object Perception for Indoor Drones
    60694, -- 2602.13430 Handling Supervision Scarcity in Chest X-ray Classification: Long-Tailed and Zer
    60827, -- 2602.11007 LaSSM: Efficient Semantic-Spatial Query Decoding via Local Aggregation and State
    60982, -- 2602.08629 CauScale: Neural Causal Discovery at Scale
    61155, -- 2602.05730 Depth as Prior Knowledge for Object Detection
    61159, -- 2602.05638 UniSurg: A Video-Native Foundation Model for Universal Understanding of Surgical
    61206, -- 2602.05557 PIRATR: Parametric Object Inference for Robotic Applications with Transformers i
    62760, -- 2601.05364 STResNet & STYOLO : A New Family of Compact Classification and Object Detection
    63481, -- 2512.18291 Pyramidal Adaptive Cross-Gating for Multimodal Detection
    63900, -- 2512.15742 SHARe-KAN: Holographic Vector Quantization for Memory-Bound Inference
    64007, -- 2512.07078 DFIR-DETR: Frequency Domain Enhancement and Dynamic Feature Aggregation for Cros
    64697, -- 2511.18192 ARIAL: An Agentic Framework for Document VQA with Precise Answer Localization
    64769, -- 2511.16654 Comparison of Text-Based and Image-Based Retrieval in Multimodal Retrieval Augme
    64913, -- 2511.13417 Delineate Anything Flow: Fast, Country-Level Field Boundary Detection from Any S
    64922, -- 2511.13208 End-to-End Multi-Person Pose Estimation with Pose-Aware Video Transformer
    65420, -- 2511.02563 The Urban Vision Hackathon Dataset and Models: Towards Image Annotations and Acc
    65489, -- 2511.01386 RAGSmith: A Framework for Finding the Optimal Composition of Retrieval-Augmented
    65798, -- 2510.23444 FRBNet: Revisiting Low-Light Vision through Frequency-Domain Radial Basis Networ
    66099, -- 2510.18513 DWaste: Greener AI for Waste Sorting using Mobile and Edge Devices
    66938, -- 2510.04739 ExposureEngine: Oriented Logo Detection and Sponsor Visibility Analytics in Spor
    67168, -- 2510.01362 EvoStruggle: A Dataset Capturing the Evolution of Struggle across Activities and
    67463, -- 2509.24595 Comprehensive Benchmarking of YOLOv11 Architectures for Scalable and Granular Pe
    67753, -- 2509.22909 TY-RIST: Tactical YOLO Tricks for Real-time Infrared Small Target Detection
    68098, -- 2509.16500 RLGF: Reinforcement Learning with Geometric Feedback for Autonomous Driving Vide
    68125, -- 2509.16098 SegDINO3D: 3D Instance Segmentation Empowered by Both Image-Level and Object-Lev
    68193, -- 2509.15045 Synthetic-to-Real Object Detection using YOLOv11 and Domain Randomization Strate
    68356, -- 2509.12193 Domain-Adaptive Pretraining Improves Primate Behavior Recognition
    68362, -- 2509.12125 RailSafeNet: Visual Scene Understanding for Tram Safety
    68389, -- 2509.11720 Advanced Layout Analysis Models for Docling
    68761, -- 2509.03704 QuantV2X: A Fully Quantized Multi-Agent System for Cooperative Perception
    68986, -- 2508.21712 FLORA: Efficient Synthetic Data Generation for Object Detection in Low-Data Regi
    69099, -- 2508.19762 BuzzSet v1.0: A Dataset for Pollinator Detection in Field Conditions
    69162, -- 2508.18799 Robust and Label-Efficient Deep Waste Detection
    69687, -- 2508.10360 A dataset and model for recognition of audiologically relevant environments for
    70086, -- 2508.04683 Query Attribute Modeling: Improving search relevance with Semantic Search and Me
    70103, -- 2508.04572 Knowledge to Sight: Reasoning over Visual Attributes via Knowledge Decomposition
    70157, -- 2508.04036 CORE-ReID V2: Advancing the Domain Adaptation for Object Re-Identification with
    70230, -- 2508.03064 CORE-ReID: Comprehensive Optimization and Refinement through Ensemble fusion in
    70312, -- 2508.01966 Self-Supervised YOLO: Leveraging Contrastive Learning for Label-Efficient Object
    70402, -- 2508.00701 D3: Training-Free AI-Generated Video Detection Using Second-Order Features
    70493, -- 2507.23325 FASTopoWM: Fast-Slow Lane Segment Topology Reasoning with Latent World Models
    70584, -- 2507.21888 CAPE: A CLIP-Aware Pointing Ensemble of Complementary Heatmap Cues for Embodied
    70621, -- 2507.21358 Collaborative Perceiver: Elevating Vision-based 3D Object Detection via Local De
    70651, -- 2507.20506 An Improved YOLOv8 Approach for Small Target Detection of Rice Spikelet Flowerin
    70808, -- 2507.17859 FishDet-M: A Unified Large-Scale Benchmark for Robust Fish Detection and CLIP-Gu
    70830, -- 2507.17508 Illicit object detection in X-ray imaging using deep learning techniques: A comp
    70925, -- 2507.15542 HOLa: Zero-Shot HOI Detection with Low-Rank Decomposed VLM Feature Adaptation
    71504, -- 2507.01912 3D Reconstruction and Information Fusion between Dormant and Canopy Seasons in C
    71563, -- 2507.00709 TopoStreamer: Temporal Lane Segment Topology Reasoning in Autonomous Driving
    71924, -- 2506.14696 YOLOv11-RGBT: Towards a Comprehensive Single-Stage Multispectral Object Detectio
    72132, -- 2506.07637 HieraEdgeNet: A Multi-Scale Edge-Enhanced Framework for Automated Pollen Recogni
    72241, -- 2506.05274 From Play to Replay: Composed Video Retrieval for Temporally Fine-Grained Videos
    72303, -- 2506.04277 RSVP: Reasoning Segmentation via Visual Prompting and Multi-modal Chain-of-Thoug
    72500, -- 2506.00249 MIR: Methodology Inspiration Retrieval for Scientific Research Problems
    73075, -- 2505.22677 Using Cross-Domain Detection Loss to Infer Multi-Scale Information for Improved
    73479, -- 2504.12021 Action Anticipation from SoccerNet Football Video Broadcasts
    73707, -- 2504.03868 Control Map Distribution using Map Query Bank for Online Map Generation
    73721, -- 2504.02558 Rip Current Segmentation: A Novel Benchmark and YOLOv8 Baseline Results
    73825, -- 2503.22965 Pallet Detection And Localisation From Synthetic Data
    74009, -- 2503.13903 TGBFormer: Transformer-GraphFormer Blender Network for Video Object Detection
    74038, -- 2503.12852 ACT360: An Efficient 360-Degree Action Detection and Summarization Framework for
    74150, -- 2503.08639 GBlobs: Explicit Local Structure via Gaussian Blobs for Improved Cross-Domain Li
    74199, -- 2503.06898 Illuminating Darkness: Learning to Enhance Low-light Images In-the-Wild
    74317, -- 2503.02101 Generalized Diffusion Detector: Mining Robust Features from Diffusion Models for
    74465, -- 2502.18871 Inscanner: Dual-Phase Detection and Classification of Auxiliary Insulation Using
    74564, -- 2502.14740 YOLOv12: A Breakdown of the Key Architectural Features
    74589, -- 2502.13764 An Overall Real-Time Mechanism for Classification and Quality Evaluation of Rice
    74793, -- 2502.07821 Amnesia as a Catalyst for Enhancing Black Box Pixel Attacks in Image Classificat
    75128, -- 2501.11899 LASER: Lip Landmark Assisted Speaker Detection for Robustness
    75427, -- 2412.13834 Maybe you are looking for CroQS: Cross-modal Query Suggestion for Text-to-Image
    75519, -- 2412.08464 CC-Diff: Enhancing Contextual Coherence in Remote Sensing Image Synthesis
    75674, -- 2411.18871 Comprehensive Performance Evaluation of YOLOv11, YOLOv10, YOLOv9, YOLOv8 and YOL
    75676, -- 2411.19071 Dynamic Attention and Bi-directional Fusion for Safety Helmet Wearing Detection
    75993, -- 2410.19846 YOLO11 and Vision Transformers based 3D Pose Estimation of Immature Green Fruits
    76205, -- 2410.01250 High and Low Resolution Tradeoffs in Roadside Multimodal Sensing
    76382, -- 2409.09877 REG: Refined Generalized Focal Loss for Road Asset Detection on Thai Highways Us
    76470, -- 2409.02546 Real-Time Dynamic Scale-Aware Fusion Detection Network: Take Road Damage Detecti
    76934, -- 2406.14341 HoTPP Benchmark: Are We Good at the Long Horizon Events Forecasting?
    77170, -- 2405.17913 OV-DQUO: Open-Vocabulary DETR with Denoising Text Query Training and Open-World
    77173, -- 2405.17698 BaboonLand Dataset: Tracking Primates in the Wild and Automating Behaviour Recog
    77266, -- 2405.10053 SHiNe: Semantic Hierarchy Nexus for Open-vocabulary Object Detection
    77324, -- 2405.02811 PVTransformer: Point-to-Voxel Transformer for Scalable 3D Object Detection
    77393, -- 2404.13921 NeRF-DetS: Enhanced Adaptive Spatial-wise Sampling and View-wise Fusion Strategi
    77445, -- 2404.08937 ChimpVLM: Ethogram-Enhanced Chimpanzee Behaviour Recognition
    77528, -- 2404.00876 MGMap: Mask-Guided Learning for Online Vectorized HD Map Construction
    77596, -- 2403.14442 RoDLA: Benchmarking the Robustness of Document Layout Analysis Models
    77658, -- 2403.07113 Class Imbalance in Object Detection: An Experimental Diagnosis and Study of Miti
    77665, -- 2401.17828 Leveraging Swin Transformer for Local-to-Global Weakly Supervised Semantic Segme
    78187, -- 2311.17241 End-to-End Temporal Action Detection with 1B Parameters Across 1000 Frames
    78542, -- 2309.04675 BiLMa: Bidirectional Local-Matching for Text-based Person Re-identification
    78618, -- 2308.11957 CED: Consistent ensemble distillation for audio tagging
    78749, -- 2307.09183 Pixel-wise Graph Attention Networks for Person Re-identification
    79037, -- 2305.08808 GeoMAE: Masked Geometric Target Prediction for Self-supervised Point Cloud Pre-T
    79346, -- 2302.10174 Towards Universal Fake Image Detectors that Generalize Across Generative Models
    79532, -- 2211.14053 Re^2TAL: Rewiring Pretrained Video Backbones for Reversible Temporal Action Loca
    79547, -- 2211.12334 A Graph-Based Method for Soccer Action Spotting Using Unsupervised Player Classi
    79674, -- 2210.05391 PP-StructureV2: A Stronger Document Analysis System
    79747, -- 2209.05588 CenterFormer: Center-based Transformer for 3D Object Detection
    79979, -- 2205.07134 ETAD: Training Action Detection End to End on a Laptop
    79991, -- 2205.05740 Surface Representation for Point Clouds
    80048, -- 2204.09931 Learning to Purification for Unsupervised Person Re-identification
    80296, -- 2112.11790 BEVDet: High-performance Multi-camera 3D Object Detection in Bird-Eye-View
    80878, -- 2102.09480 Unbiased Teacher for Semi-Supervised Object Detection
    80890, -- 2102.04411 Traceability Transformed: Generating more Accurate Links with Pre-Trained BERT M
    81493, -- 1810.05952 Comparison-Based Convolutional Neural Networks for Cervical Cell/Clumps Detectio
    81494, -- 1912.10211 PANNs: Large-Scale Pretrained Audio Neural Networks for Audio Pattern Recognitio
    81810, -- 1902.06197 Online PCB Defect Detector On A New PCB Defect Dataset
    82040, -- 1804.06882 Pelee: A Real-Time Object Detection System on Mobile Devices
    83221, -- 2606.03748 Ultralytics YOLO26: Unified Real-Time End-to-End Vision Models
    83727, -- 2605.25979 LLaVA-OneVision-2: Towards Next-Generation Perceptual Intelligence
    84015, -- 2505.17476 The Coherence Trap: When MLLM-Crafted Narratives Exploit Manipulated Visual Cont
    84062, -- 2507.16861 Look Before You Fuse: 2D-Guided Cross-Modal Alignment for Robust 3D Detection
    84234, -- 2511.19221 Percept-WAM: Perception-Enhanced World-Awareness-Action Model for Robust End-to-
    84646, -- 2602.23790 Fourier Angle Alignment for Oriented Object Detection in Remote Sensing
    84745, -- 2603.04598 PinPoint: Evaluation of Composed Image Retrieval with Explicit Negatives, Multi-
    84770, -- 2603.05929 Beyond Static Frames: Temporal Aggregate-and-Restore Vision Transformer for Huma
    84785, -- 2603.06917 PaQ-DETR: Learning Pattern and Quality-Aware Dynamic Queries for Object Detectio
    85111, -- 2603.25165 Towards Foundation Models for 3D Scene Understanding: Instance-Aware Self-Superv
    85244, -- 2604.02093 GroundVTS: Visual Token Sampling in Multimodal Large Language Models for Video T
    85406, -- 2604.17135 OptiMVMap: Offline Vectorized Map Construction via Optimal Multi-vehicle Perspec
    85537, -- 2605.09802 CrossVL: Complexity-Aware Feature Routing and Paired Curriculum for Cross-View V
    85570, -- 2605.16901 CAR-SAM: Cross-Attention Reconstruction for Post-Training Quantization of the Se
    85577, -- 2605.18192 View-Aware Semantic Alignment for Aerial-Ground Person Re-Identification
    86612, -- 2405.12179 PLEIADES: Building Temporal Kernels with Orthogonal Polynomials
    86654, -- 2505.16524 CodeMerge: Codebook-Guided Model Merging for Robust Test-Time Adaptation in Auto
    86667, -- 2506.08997 SDTagNet: Leveraging Text-Annotated Navigation Maps for Online HD Map Constructi
    87127, -- 2509.16421 Aha! - Predicting What Matters Next: Online Highlight Detection Without Looking
    87590, -- 2507.19239 CoopTrack: Exploring End-to-End Learning for Efficient Cooperative Sequential Pe
    87601, -- 2507.21489 Describe, Adapt and Combine: Empowering CLIP Encoders for Open-set 3D Object Ret
    87671, -- 2503.03088 AHCPTQ: Accurate and Hardware-Compatible Post-Training Quantization for Segment
    87940, -- 2507.04587 CVFusion: Cross-View Fusion of 4D Radar and Camera for 3D Object Detection
    87976, -- 2508.13995 Self-Supervised Sparse Sensor Fusion for Long Range Perception
    88001, -- 2509.00760 No More Sibling Rivalry: Debiasing Human-Object Interaction Detection
    88372, -- 2509.18733 Knowledge Transfer from Interaction Learning
    88375, -- 2506.23565 OcRFDet: Object-Centric Radiance Fields for Multi-View 3D Object Detection in Au
    88414, -- 2507.18173 WaveMamba: Wavelet-Driven Mamba Fusion for RGB-Infrared Object Detection
    88439, -- 2508.07089 ForeSight: Multi-View Streaming Joint Object Detection and Trajectory Forecastin
    88468, -- 2506.21198 Unlocking Constraints: Source-Free Occlusion-Aware Seamless Segmentation
    90156, -- 2502.16911 SPARC: Score Prompting and Adaptive Fusion for Zero-Shot Multi-Label Recognition
    90387, -- 2412.12725 RaCFormer: Towards High-Quality 3D Object Detection via Query-based Radar-Camera
    90445, -- 2409.18733 Search and Detect: Training-Free Long Tail Object Detection via Web-Image Retrie
    90498, -- 2503.12009 UniMamba: Unified Spatial-Channel Representation Learning with Group-Efficient M
    90552, -- 2502.19694 BEVDiffuser: Plug-and-Play Diffusion Model for BEV Denoising with Ground-Truth G
    90877, -- 2411.16752 Imagine and Seek: Improving Composed Image Retrieval with an Imagined Proxy
    90891, -- 2503.08422 JiSAM: Alleviate Labeling Burden and Corner Case Problems in Autonomous Driving
    91801, -- 2410.07733 MGMapNet: Multi-Granularity Representation Learning for End-to-End Vectorized HD
    92442, -- 2501.15326 Recognize Any Surgical Object: Unleashing the Power of Weakly-Supervised Data
    92755, -- 2503.16251 RESFL: An Uncertainty-Aware Framework for Responsible Federated Learning by Bala
    93522, -- 2603.06693 Soft Equivariance Regularization for Invariant Self-Supervised Learning
    94021, -- 2508.10801 Object Fidelity Diffusion for Remote Sensing Image Generation
    94430, -- 2602.19874 BigMaQ: A Big Macaque Motion and Animation Dataset Bridging Image and 3D Pose Re
    94485, -- 2505.11165 Maximizing Asynchronicity in Event-based Neural Networks
    94632, -- 2510.18229 Unbiased Object Detection Beyond Frequency with Visually Prompted Image Synthesi
    94727, -- 2509.23541 OVSeg3R: Learn Open-vocabulary Instance Segmentation from 2D via 3D Reconstructi
    94988, -- 2510.10660 Stability Under Scrutiny: Benchmarking Representation Paradigms for Online HD Ma
    95250, -- 2603.09695 DRIFT: Dual-Representation Inter-Fusion Transformer for Automated Driving Percep
    95387, -- 2411.12452 GaussianPretrain: A Simple Unified 3D Gaussian Representation for Visual Pre-Tra
    95646, -- external Knowledge-Guided Graph Convolutional Network for Multi-Label Image Classificatio
    96083, -- 2605.02762 Unified Map Prior Encoder for Mapping and Planning
    96398, -- 2504.09103 IMPACT: Behavioral Intention-Aware Multimodal Trajectory Prediction with Adaptiv
    96508, -- 2603.21134 Anatomical Prior-Driven Framework for Autonomous Robotic Cardiac Ultrasound Stan
    96516, -- external Class-Aware Queries for Robust Multi-View 3D Object Detection
    96563, -- external OWOD-FSL: Open-World Object Detection Via Few-Shot Learning and Dynamic Prototyp
    96910, -- external RefDiffMap: Diffusion-Guided Progressive Refinement for Vectorized HD Map Constr
    97087, -- external Toward Robust Collaborative Perception under Adverse Weather Conditions Via Dual
    97129, -- external Re-MAE: Rethinking Masked Autoencoders towards Geometry-Aware Self-Supervised Li
    97308, -- 2602.21589 SEF-MAP: Subspace-Decomposed Expert Fusion for Robust Multimodal HD Map Predicti
    97787, -- external AttBEV: Enhancing Multi-Modal 3D Object Detection with CBAM Attention in BEVFusi
    98077, -- external IsoCLIP: Decomposing CLIP Projectors for Efficient Intra-modal Alignment — A Tec
    98180, -- 2601.11508 ReScene4D: Temporally Consistent Semantic Instance Segmentation of Evolving Indo
    98278, -- 2211.15766 Superpoint Transformer for 3D Scene Instance Segmentation
    98360, -- 2111.12933 ML-Decoder: Scalable and Versatile Classification Head
    98613, -- 2108.07478 Instance Segmentation in 3D Scenes using Semantic Superpoint Tree Networks
    98614, -- 2203.14662 MaskGroup: Hierarchical Point Grouping and Masking for 3D Instance Segmentation
    98615, -- 1912.00145 Point Cloud Instance Segmentation using Probabilistic Embeddings
    98616, -- 2004.01658 PointGroup: Dual-Set Point Grouping for 3D Instance Segmentation
    98770, -- 2306.13526 Bridging the Performance Gap between DETR and R-CNN for Graphical Object Detecti
    98772, -- 2308.02051 A Graphical Approach to Document Layout Analysis
    98864, -- 2606.25225 MJEPA: A Simple and Scalable Joint-Embedding Predictive Architecture for Audio-V
    99018, -- 2606.29667 Unlocking the Visual Record of Materials Science: A Large-Scale Multimodal Datas
    99341, -- 2602.15720 ToaSt: Token Channel Selection and Structured Pruning for Efficient ViT
    99502, -- 2606.20044 FUSE: Frequency-domain Unification and Spectral Energy Alignment for Multi-modal
    99665, -- 2604.20395 SpaCeFormer: Fast Proposal-Free Open-Vocabulary 3D Instance Segmentation
    99777, -- 2606.12925 Multi-Label Test-Time Adaptation with Bayesian Conditional Priors
    99864, -- 2605.25821 [CLS] is Not Enough: Multi-Label Recognition via Patch-Level Inference and Adapt
    101214, -- 2511.22521 DocVAL: Validated Chain-of-Thought Distillation for Grounded Document VQA
    101234, -- 2510.06969 Learning Global Representation from Queries for Vectorized HD Map Construction
    101577, -- 2604.24972 Dynamic Decision Learning: Test-Time Evolution for Abnormality Grounding in Rare
    102692, -- 2211.04772 Efficient Large-scale Audio Tagging via Transformer-to-CNN Knowledge Distillatio
    102957, -- 2601.21078 Towards Mitigating Modality Bias in Vision-Language Models for Temporal Action L
    103841, -- 2607.07673 MedPMC: A Systematic Framework for Scaling High-Fidelity Medical Multimodal Data
    103851, -- 2112.00322 FCAF3D: Fully Convolutional Anchor-Free 3D Object Detection
    104097, -- 2506.12561 Parkinson's Disease Freezing of Gait (FoG) Symptom Detection Using Machine Learn
    104321, -- 2110.01931 Anchor-free Oriented Proposal Generator for Object Detection
    104460, -- 2607.19069 Delineate Anything v2: A Global Foundation Model for Field Delineation
    105175, -- 2507.19621 Exemplar Med-DETR: Toward Generalized and Robust Lesion Detection in Mammogram I
    105308, -- 2508.08069 Information Bottleneck-based Causal Attention for Multi-label Medical Image Reco
    105417, -- 2507.00670 Mind the Detail: Uncovering Clinically Relevant Image Details in Accelerated MRI
    105459, -- 2507.05007 Multi-modal Representations for Fine-grained Multi-label Critical View of Safety
    105545, -- external PolarDETR: Enhancing Interpretability in Multi-modal Methods for Jawbone Lesion
    105665, -- external Smarter Self-Distillation: Optimizing the Teacher for Surgical Video Application
    106023, -- 2607.28996 SULAND v2: A Refined RGB Dataset and Deep Learning Object Detection Benchmark fo
    106477, -- 2512.05698 OWL: Unsupervised 3D Object Detection by Occupancy Guided Warm-up and Large Mode
    106842, -- 2501.03775 Strip R-CNN: Large Strip Convolution for Remote Sensing Object Detection
    106918, -- 2601.00584 GranAlign: Granularity-Aware Alignment Framework for Zero-shot Video Moment Retr
    106998, -- 2511.12004 ComLQ: Benchmarking Complex Logical Queries in Information Retrieval
    106999, -- 2512.02447 Temporal Dynamics Enhancer for Directly Trained Spiking Object Detectors
    107107, -- 2512.08247 Distilling Future Temporal Knowledge with Masked Feature Reconstruction for 3D O
    107263, -- 2503.06515 SAQ-SAM: Semantically-Aligned Quantization for Segment Anything Model
    107321, -- 2511.15379 Zero-Shot Open-Vocabulary Human Motion Grounding with Test-Time Training
    107455, -- 2511.12941 GUIDE: Gaussian Unified Instance Detection for Enhanced Obstacle Perception in A
    107636, -- 2511.13924 Start Small, Think Big: Curriculum-based Relative Policy Optimization for Visual
    107649, -- 2512.23635 Rethinking the Spatio-Temporal Alignment of End-to-End 3D Perception
    107681, -- 2511.19919 HybriDLA: Hybrid Generation for Document Layout Analysis
    107736, -- 2602.15383 Bridging Day and Night: Target-Class Hallucination Suppression in Unpaired Image
    107770, -- 2511.18075 VK-Det: Visual Knowledge Guided Prototype Learning for Open-Vocabulary Aerial Ob
    108961, -- 2608.07051 YOLO-PEFT: Parameter-Efficient Fine-Tuning on YOLO Family
    108978, -- external Object Detection with LightlyTrain
    110459, -- 2508.20417 KG-CQR: Leveraging Structured Relation Representations in Knowledge Graphs for C
    112150, -- 2507.02666 ASDA: Audio Spectrogram Differential Attention Mechanism for Self-Supervised Rep
    112395, -- 2407.11682 MapDistill: Boosting Efficient Camera-based HD Map Construction via Camera-LiDAR
    112421, -- 2401.05906 PartSTAD: 2D-to-3D Part Segmentation Task Adaptation
    112651, -- 2406.01194 AFF-ttention! Affordances and Attention models for Short-Term Object Interaction
    112702, -- 2403.11848 GraphBEV: Towards Robust BEV Feature Alignment for Multi-Modal 3D Object Detecti
    112794, -- 2407.20708 Integer-Valued Training and Spike-driven Inference Spiking Neural Network for Hi
    112861, -- external Revisiting Domain-Adaptive Object Detection in Adverse Weather by the Generation
    113045, -- 2312.03341 Online Vectorized HD Map Construction using Geometry
    113058, -- external Multi-scale Cross Distillation for Object Detection in Aerial Images
    113069, -- 2407.04305 Towards Stable 3D Object Detection
    113175, -- 2407.10164 LabelDistill: Label-guided Cross-modal Knowledge Distillation for Camera-based 3
    113202, -- 2402.17430 Leveraging Enhanced Queries of Point Sets for Vectorized Map Construction
    113249, -- 2403.12574 EAS-SNN: End-to-End Adaptive Sampling and Representation for Event-based Detecti
    113251, -- 2409.05564 LEROjD: Lidar Extended Radar-Only Object Detection
    113256, -- 2407.12702 TransCAD: A Hierarchical Transformer for CAD Sequence Inference from Point Cloud
    113309, -- external CARB-Net: Camera-Assisted Radar-Based Network for Vulnerable Road User Detection
    113371, -- 2407.05266 CLAMP-ViT: Contrastive Data-Free Learning for Adaptive Post-Training Quantizatio
    113437, -- external A Unified Image Compression Method for Human Perception and Multiple Vision Task
    113446, -- external RecurrentBEV: A Long-term Temporal Fusion Framework for Multi-view 3D Detection
    113567, -- external Ex2Eg-MAE: A Framework for Adaptation of Exocentric Video Masked Autoencoders fo
    113639, -- external Distilling Knowledge from Large-Scale Image Models for Object Detection
    113645, -- 2403.05402 DualBEV: Unifying Dual View Transformation with Probabilistic Correspondences
    113679, -- 2311.11646 Toward Open Vocabulary Aerial Object Detection with CLIP-Activated Student-Teach
    113802, -- 2608.30821 Lucida: Parse, Generate, and Place for Composable Real-to-Sim Scene Modeling
    113949, -- 2605.00876 GAZE: Grounded Agentic Zero-shot Evaluation with Viewer-Level Tools and Literatu
    114006, -- 2511.13344 YOLO Meets Mixture-of-Experts: Adaptive Expert Routing for Robust Object Detecti
    114204, -- 2609.12078 Feature Recovery for Object Understanding After Irreversible Fire Damage
    114248, -- 2508.10567 SpaRC-AD: A Baseline for Radar-Camera Fusion in End-to-End Autonomous Driving
    114940, -- 2407.07633 Few-Shot Domain Adaptive Object Detection for Microscopic Images
    115011, -- external Immune-guided AI for Reproducible Regions of Interest Selection in Multiplex Imm
    115145, -- external Multilevel Causality Learning for Multi-label Gastric Atrophy Diagnosis
    115222, -- external Prompting Vision-Language Models for Dental Notation Aware Abnormality Detection
    115243, -- external Representation Learning with a Transformer-Based Detection Model for Localized C
    115457, -- 2403.19278 CAT: Exploiting Inter-Class Dynamics for Domain Adaptive Object Detection
    115638, -- 2403.02769 HUNTER: Unsupervised Human-centric 3D Detection via Transferring Knowledge from
    115708, -- 2403.08919 CLIP-BEVFormer: Enhancing Multi-View Image-Based BEV Detector with Ground Truth
    115767, -- 2404.03518 SDPose: Tokenized Pose Estimation via Circulation-Guide Self-Distillation
    115790, -- 2404.00653 Dual DETRs for Multi-Label Temporal Action Detection
    115839, -- 2312.08875 What How and When Should Object Detectors Update in Continually Changing Test Do
    115914, -- 2411.02220 SIRA: Scalable Inter-frame Relation and Association for Radar Perception
    115966, -- 2312.06420 Localization Is All You Evaluate: Data Leakage in Online Mapping Datasets and Ho
    115993, -- external Distribution-aware Knowledge Prototyping for Non-exemplar Lifelong Person Re-ide
    116036, -- external A-Teacher: Asymmetric Network for 3D Semi-Supervised Object Detection
    116132, -- 2402.15584 State Space Models for Event Cameras
    116160, -- 2312.03799 Low-power Continuous Remote Behavioral Localization with Event Cameras
    116267, -- 2405.04390 DriveWorld: 4D Pre-trained Scene Understanding via World Models for Autonomous D
    116306, -- 2311.17902 Language-conditioned Detection Transformer
    116318, -- 2411.00340 GAFusion: Adaptive Fusing LiDAR and Camera with Multiple Guidance for 3D Object
    116441, -- 2306.07520 Instruct-ReID: A Multi-purpose Person Re-identification Task with Instructions
    116461, -- 2311.17286 LEOD: Label-Efficient Object Detection for Event Cameras
    116516, -- 2403.05817 SAFDNet: A Simple and Effective Network for Fully Sparse 3D Object Detection
    116522, -- 2405.07201 Building a Strong Pre-Training Baseline for Universal 3D Large-Scale Perception
    116541, -- external WildlifeMapper: Aerial Image Analysis for Multi-Species Detection and Identifica
    116584, -- 2405.15225 Unbiased Faster R-CNN for Single-source Domain Generalized Object Detection
    116593, -- 2403.01316 TUMTraf V2X Cooperative Perception Dataset
    116623, -- 2403.08639 HIMap: HybrId Representation Learning for End-to-end Vectorized HD Map Construct
    116755, -- external Prompt3D: Random Prompt Assisted Weakly-Supervised 3D Object Detection
    116771, -- 2403.05061 RadarDistill: Boosting Radar-based Object Detection Performance via Knowledge Di
    116865, -- external Scene-adaptive and Region-aware Multi-modal Prompt for Open Vocabulary Object De
    116885, -- 2403.15192 SFOD: Spiking Fusion Object Detector
    116893, -- 2403.06093 Enhancing 3D Object Detection with 2D Detection-Guided Query Anchors
    117041, -- 2312.01897 Adapting Short-Term Transformers for Action Detection in Untrimmed Videos
    117063, -- 2312.17686 Multiscale Vision Transformers Meet Bipartite Matching for Efficient Single-stag
    117103, -- external CaKDP: Category-aware Knowledge Distillation and Pruning Framework for Lightweig
    117112, -- 2404.15010 X-3D: Explicit 3D Structure Modeling for Point Cloud Recognition
    117139, -- 2403.04198 CN-RMA: Combined Network with Ray Marching Aggregation for 3D Indoor Object Dete
    117160, -- 2403.14513 View-decoupled Transformer for Person Re-identification under Aerial-ground Came
    117194, -- 2402.18975 Theoretically Achieving Continuous Representation of Oriented Bounding Boxes
    117719, -- 2606.31096 Horizon3D: Sparse Radar-Camera Fusion for Long-Range 3D Perception in Autonomous
    117947, -- 2605.12218 Learning Ego-Centric BEV Representations from a Perspective-Privileged View: Cro
    117994, -- 2606.31127 SkillSpotter: Pose-Aware Multi-View Skilled Action Detection and Grading in Ego-
    118013, -- 2607.01827 C2E: Boosting Ego-Only 3D Object Detection via Multi-Teacher Contrastive Knowled
    118101, -- 2607.12419 DeGuNet: Depth-Guided Ultra-Compact Backbones for Efficient LiDAR-Camera 3D Dete
    118104, -- 2607.09138 BeyondSight: Object Permanence for End-to-End Autonomous Driving
    118156, -- 2608.25653 Towards Purified Multi-Label Test-Time Adaptation of Vision-Language Models
    118196, -- 2607.02074 Comprehensive Robustness Analysis of LiDAR-based 3D Object Detection in Autonomo
    118226, -- 2607.17340 Orthogonal Knowledge Refreshing for Domain-Incremental Object Detection
    118822, -- 2603.23455 DetPO: In-Context Learning with Multi-Modal LLMs for Few-Shot Object Detection
    118866, -- 2608.13045 P²Fusion: Prompt-based Progressive Infrared-Visible Image Fusion via Dual-Prior
    118948, -- 2606.31834 Real-Time Source-Free Object Detection
    119002, -- 2603.06228 Low-latency Event-based Object Detection with Spatially-Sparse Linear Attention
    119738, -- 2212.06244 PathFusion: Path-Consistent Lidar-Camera Deep Feature Fusion
    119849, -- external Brain-Inspired Spiking Neural Networks for Energy-Efficient Object Detection
    119874, -- external Towards Universal AI-Generated Image Detection by Variational Information Bottle
    119892, -- 2505.01008 Where's the Liability in the Generative Era? Recovery-based Black-Box Detection
    119894, -- external OW-OVD: Unified Open World and Open Vocabulary Object Detection
    119920, -- external CLIP is Almost All You Need: Towards Parameter-Efficient Scene Text Retrieval wi
    120468, -- external Minimizing Labeled, Maximizing Unlabeled: An Image-Driven Approach for Video Ins
    120818, -- external Prompt-Free Unknown Label Generation for Open World Detection in Remote Sensing
    120848, -- 2603.02363 Beyond Caption-Based Queries in Video Moment Retrieval
    120865, -- external STUR3D: Spatio-Temporal Unified Representation Learning for 3D Object Detection
    120933, -- external SRA-Det: Learning Omni-Grained Open-Vocabulary Detection Beyond Category Names
    121191, -- external YOLO-ULM: Ultra-Lightweight Models for Real-Time Object Detection
    121216, -- external Spike-driven Discrete Aggregation for Event-based Object Detection
    121466, -- 2512.08912 LiDAS: Lighting-driven Dynamic Active Sensing for Nighttime Perception
    121503, -- external VLM4RSDet: Collaborative Optimization with Vision-Language Model for Enhancing R
    121589, -- external VRCLIP: Multimodal Canonical Correlation Alignment for CLIP-Driven Vision-Radio
    121592, -- 2512.20409 DETACH : Decomposed Spatio-Temporal Alignment for Exocentric Video and Ambient S
    121649, -- external AntiStyler: Defending Object Detection Models Against Adversarial Patch Attacks
    121723, -- external COPE: Consistent Occlusion and Prompt Enhancement Network for Occluded Person Re
    121870, -- external Rotation Invariant and Symmetry Aware Pixel Difference Network for Remote Sensin
    122127, -- 2609.20869 TAPe+ML: A Compact Structured Representation for Multi-Task Computer Vision
    123107, -- external Vision Meets Language: A RAG-Augmented YOLOv8 Framework for Coffee Disease Diagn
    123158, -- 2610.06226 LeAVJEPA: A Minimalist Architecture for Audio-Visual Self-Supervised Learning
    123325, -- 2108.05699 Oriented R-CNN for Object Detection
    123420, -- 2609.37631 Procedural Core: A Compact Recurrent Initialization for Vision Transformers
    123737, -- 2305.08719 M$^{6}$Doc: A Large-Scale Multi-Format, Multi-Type, Multi-Layout, Multi-Language
    123921, -- 2211.09074 Where a Strong Backbone Meets Strong Features -- ActionFormer for Ego4D Moment Q
    123990, -- external Discovering Human Interactions With Large-Vocabulary Objects via Query and Multi
    124031, -- 2610.30340 Foundation4D: Towards a unified perception and reconstruction model for autonomo
    124238, -- 2510.06512 LogSTOP: Temporal Scores over Prediction Sequences for Matching and Retrieval
    124298, -- external Attribution-Guided Shared-Private Decoupling for Noise-Reduced Audio-Visual Repr
    124394, -- external Target-Aware Nuisance Shaping for Object Detection
    124529, -- external ProAlign: Progressive Positional and Prototype-Guided Alignment for Aerial-Groun
    124933, -- external Feature Recovery for Object Understanding Under Physical Transformation
    124943, -- 2609.15221 MAST: Label-Efficient, Robust, and Generalizable Sound Detection for Biodiversit
    125389, -- external Training-Free Open World Object Detection
    125920, -- 2506.03173 Geometry-Centered 3D Latent World Models for Growing Surfaces
    125922, -- external HypMoE-ReID: Hyperspherical Mixture-of-Experts for Large Scale Person Re-Identif
    126116, -- 2605.10496 M$^2$E-UAV: A Benchmark and Analysis for Onboard Motion-on-Motion Event-Based Ti
    126777, -- external Correspondence Pruning by Iterative Structural Rectification
    126848, -- external The road reaches every place, the short cut only one: Self-Adversarial Shortcut
    127554, -- external Learning Joint Semantic-Geometric Uncertainty for Structured Prediction with Clo
    127578, -- external EviAttr-OW: Evidential Attribute Reasoning for Open World Object Detection
    127761, -- external ReVMap: Vectorized Global Mapping via Connectivity-Aware Local Map Fusion
    128664, -- external Dynamic Physical Adversarial LED Patterns via Reinforcement Learning
    129445, -- external LoCo: Selective Local Competition for Discriminative Open-Vocabulary Multi-Label
    130369, -- 2605.26900 SPHERE-JEPA: Spherical Prediction with Homogeneous Embeddings
    130373, -- external SPEXT: A Decoupled Multi-Spectral Foundation Model for Earth Observation and Vis
    130579, -- external MLLM Makes Strong Backbone for Multi-Modal Object Detection
    130617, -- external SkillCIR: Intent-Guided Skill Composition for Training-Free Composed Image Retri
    130709, -- external SING-CH: Task-Scale-Agnostic Lifelong Cross-Modal Hashing on Statistical Manifol
    130883, -- 2610.07326 Localize Any Object in X-Ray Security Scans without Human Annotation
    130999, -- external LCD$^3$: Layout-Conditioned Diffusion for Dataset Distillation in Object Detecti
    131082, -- external Relational Feature Distillation for Lightweight 3D Point Cloud Segmentation
    131532 -- external AG-ReID.v2: Bridging Aerial and Ground Views for Person Re-Identification
  );

DELETE FROM paper_method_exclusions x
USING map_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM map_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM map_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- mean-average-precision-map: 2 reviewed negatives (other senses).
CREATE TEMP TABLE map_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mean-average-precision-map'
  AND p.id IN (
    52521, -- 2508.18579 DrugReasoner: Interpretable Drug Approval Prediction with a Reasoning-augmented
    94569 -- 2510.10231 Semantic Visual Anomaly Detection and Reasoning in AI-Generated Images
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'metrics curation 2026-11-10: mAP only appears inside another name (ChemAP model, SemAP metric)'
FROM map_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING map_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING map_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- bertscore: 86 links (title/abstract names the metric; plus the source paper).
CREATE TEMP TABLE bertscore_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bertscore'
  AND p.id IN (
    2025, -- 1904.09675 BERTScore: Evaluating Text Generation with BERT
    4319, -- 2010.04989 Zero-Shot Translation Quality Estimation with Explicit Cross-Lingual Patterns
    5258, -- 2103.12693 QuestEval: Summarization Asks for Fact-based Evaluation
    5467, -- 2104.07560 Rethinking Automatic Evaluation in Sentence Simplification
    6129, -- 2106.14019 UMIC: An Unreferenced Metric for Image Captioning via Contrastive Learning
    6494, -- 2108.12026 Semantic-Based Self-Critical Training For Question Generation
    6988, -- 2110.08559 FrugalScore: Learning Cheaper, Lighter and Faster Evaluation Metricsfor Automati
    10073, -- 2208.08408 Summarizing Patients Problems from Hospital Progress Notes Using Pre-trained Seq
    10240, -- 2209.03791 Applying Transformer-based Text Summarization for Keyphrase Generation
    11193, -- 2211.01482 RQUGE: Reference-Free Metric for Evaluating Question Generation by Answering the
    12103, -- 2212.10013 DocAsRef: An Empirical Study on Repurposing Reference-Based Summary Quality Metr
    13022, -- 2302.05527 CodeBERTScore: Evaluating Code Generation with Pretrained Models of Code
    15638, -- 2305.09898 Balancing Lexical and Semantic Quality in Abstractive Summarization
    16090, -- 2305.14483 Language Model Self-improvement by Reinforcement Learning Contemplation
    16165, -- 2305.14907 Coverage-based Example Selection for In-Context Learning
    18968, -- 2308.03131 Towards Multiple References Era -- Addressing Data Leakage and Limited Reference
    20816, -- 2309.13202 Investigating Large Language Models and Control Mechanisms to Improve Text Reada
    21382, -- 2310.02790 Low Resource Summarization using Pre-trained Language Models
    21688, -- 2310.06201 Compressing Context to Enhance Inference Efficiency of Large Language Models
    25471, -- 2401.02132 DCR-Consistency: Divide-Conquer-Reasoning for Consistency Evaluation and Improve
    27470, -- 2402.11161 PEDANTS: Cheap but Effective and Interpretable Answer Equivalence
    29923, -- 2404.03278 Evaluating Document Simplification: On the Importance of Separately Assessing Si
    31040, -- 2405.01930 OARelatedWork: A Large-Scale Dataset of Related Work Sections with Full-texts fr
    31751, -- 2405.16284 Generating clickbait spoilers with an ensemble of large language models
    33784, -- 2406.19071 EmPO: Emotion Grounding for Empathetic Response Generation through Preference Op
    35907, -- 2408.08805 CIKMar: A Dual-Encoder Approach to Prompt-Based Reranking in Educational Dialogu
    36952, -- 2409.10640 Exploring Fine-tuned Generative Models for Keyphrase Selection: A Case Study for
    38002, -- 2410.05193 RevisEval: Improving LLM-as-a-Judge via Response-Adapted References
    38080, -- 2410.05903 Automatic Summarization of Long Documents
    38494, -- 2410.11001 Graph of Records: Boosting Retrieval Augmented Generation for Long-context Summa
    39655, -- 2411.03012 Leveraging Large Language Models in Code Question Answering: Baselines and Issue
    42210, -- 2412.19168 GFG -- Gender-Fair Generation: A CALAMITA Challenge
    42745, -- 2501.06521 Fine-tuning Large Language Models for Improving Factuality in Legal Question Ans
    42872, -- 2501.08769 Enhanced Large Language Models for Effective Screening of Depression and Anxiety
    42951, -- 2501.09993 Agent-as-Judge for Factual Summarization of Long Narratives
    43069, -- 2501.12356 Vision-Language Models for Automated Chest X-ray Interpretation: Leveraging ViT
    43256, -- 2501.15398 How Green are Neural Language Models? Analyzing Energy Consumption in Text Summa
    45670, -- 2503.06204 CUPCase: Clinically Uncommon Patient Cases and Diagnoses Dataset
    47637, -- 2504.09895 Learning from Reference Answers: Versatile Language Model Alignment without Bina
    49778, -- 2505.19819 FinLoRA: Benchmarking LoRA Methods for Fine-Tuning LLMs on Financial Datasets
    51228, -- 2506.14629 VisText-Mosquito: A Multimodal Dataset and Benchmark for AI-Based Mosquito Breed
    51251, -- 2506.15068 Semantically-Aware Rewards for Open-Ended R1 Training in Free-Form Generation
    51667, -- 2507.03033 Preserving Privacy, Increasing Accessibility, and Reducing Cost: An On-Device Ar
    52951, -- 2509.18030 RadEval: A framework for radiology text evaluation
    56962, -- 2603.18911 Progressive Training for Explainable Citation-Grounded Dialogue: Reducing Halluc
    58258, -- 2604.11687 Please Make it Sound like Human: Encoder-Decoder vs. Decoder-Only Transformers f
    59756, -- 2603.07091 Exploring the Reasoning Depth of Small Language Models in Software Architecture:
    60302, -- 2602.22261 Sustainable LLM Inference using Context-Aware Model Switching
    62287, -- 2601.14157 ConceptCaps -- a Distilled Concept Dataset for Interpretability in Music Models
    62392, -- 2602.11165 Assessing LLM Reliability on Temporally Recent Open-Domain Questions
    63027, -- 2601.01785 SRAS: A Lightweight Reinforcement Learning-based Document Selector for Edge-Nati
    63183, -- 2512.24366 On the Factual Consistency of Text-based Explainable Recommendation Models
    65548, -- 2511.00450 SmartDoc: A Context-Aware Agentic Method Comment Generation Plugin
    65742, -- 2510.24251 GRAPHIA: Harnessing Social Graph Data to Enhance LLM-Based Social Simulation
    66159, -- 2510.17532 OncoReason: Structuring Clinical Reasoning in LLMs for Robust and Interpretable
    66389, -- 2510.13312 ChatR1: Reinforcement Learning for Conversational Reasoning and Retrieval Augmen
    67776, -- 2509.21451 VideoJudge: Bootstrapping Enables Scalable Supervision of MLLM-as-a-Judge for Vi
    68334, -- 2509.14275 FedMentor: Domain-Aware Differential Privacy for Heterogeneous Federated LLMs in
    68513, -- 2509.09014 COCO-Urdu: A Large-Scale Urdu Image-Caption Dataset with Multimodal Quality Esti
    69488, -- 2508.13525 Saudi-Dialect-ALLaM: LoRA Fine-Tuning for Dialectal Arabic Generation
    69745, -- 2508.15797 Benchmarking the Medical Understanding and Reasoning of Large Language Models in
    70012, -- 2508.05953 SCALEFeedback: A Large-Scale Dataset of Synthetic Computer Science Assignments f
    71019, -- 2507.13737 DailyLLM: Context-Aware Activity Log Generation Using Multi-Modal Sensors and LL
    71371, -- 2507.05123 An Evaluation of Large Language Models on Text Summarization Tasks Using Prompt
    71483, -- 2507.02424 CyberRAG: An Agentic RAG cyber attack classification and reporting tool
    72251, -- 2506.04772 Identifying Reliable Evaluation Metrics for Scientific Text Revision
    72502, -- 2506.00200 Structuring Radiology Reports: Challenging LLMs with Lightweight Models
    72750, -- 2505.18928 Toward Human Centered Interactive Clinical Question Answering System
    74572, -- 2502.14338 English Please: Evaluating Machine Translation with Large Language Models for Mu
    75002, -- 2502.00448 HERA: Improving Long Document Summarization using Large Language Models with Con
    78275, -- 2311.03696 Bilingual Corpus Mining and Multistage Fine-Tuning for Improving Machine Transla
    80054, -- 2204.09292 Towards Arabic Sentence Simplification via Classification and Generative Approac
    81060, -- 2010.10042 Improving Factual Completeness and Consistency of Image-to-Text Radiology Report
    84777, -- 2603.06213 Cut to the Chase: Training-free Multimodal Summarization via Chain-of-Events
    93344, -- 2509.20900 Learning to Summarize by Learning to Quiz: Adversarial Agentic Collaboration for
    94898, -- 2509.21493 Sci2Pol: Evaluating and Fine-tuning LLMs on Scientific-to-Policy Brief Generatio
    98108, -- 2606.00440 SDR: Set-Distance Rewards for Radiology Report Generation
    98286, -- 2606.00467 On the Limits of LLM Adaptability: Impact of Model-Internalized Priors on Annota
    103229, -- 2604.24089 BiMol-Diff: A Unified Diffusion Framework for Molecular Generation and Captionin
    103282, -- 2508.16771 EyeMulator: Improving Code Language Models by Mimicking Human Visual Attention
    103551, -- 2601.19350 Cross-Examination Framework: A Task-Agnostic Diagnostic for Information Fidelity
    111039, -- 2410.12400 QUIDS: Query Intent Description for Exploratory Search via Dual Space Modeling
    119415, -- 2603.18453 Learning Consistent Temporal Grounding between Related Tasks in Sports Coaching
    122186, -- 2609.25187 X-Planner: Event-Structured Task Planning for Embodied Intelligence
    123529, -- 2610.18762 Looking Complete Is Not Being Grounded: Evaluating LLM Sitreps Against Human-Aut
    126537 -- external Neuro-KE: Knowledge-Guided Interfaces for Semantically Grounded EEG Foundation M
  );

DELETE FROM paper_method_exclusions x
USING bertscore_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM bertscore_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM bertscore_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- bertscore: 2047 reviewed negatives (local citers of the source that do not name the metric).
CREATE TEMP TABLE bertscore_citers_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bertscore'
  AND p.id IN (
    2421, -- 1908.05739 Abductive Commonsense Reasoning
    2463, -- 1908.10084 Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks
    2483, -- 1909.00277 Cosmos QA: Machine Reading Comprehension with Contextual Commonsense Reasoning
    2509, -- 1909.02622 MoverScore: Text Generation Evaluating with Contextualized Embeddings and Earth
    2754, -- 1910.14659 Masked Language Model Scoring
    2790, -- 1911.03705 CommonGen: A Constrained Text Generation Challenge for Generative Commonsense Re
    2879, -- 1912.00342 Machines Getting with the Program: Understanding Intent Arguments of Non-Canonic
    3133, -- 2002.09836 Fill in the BLANC: Human-free quality estimation of document summaries
    3143, -- 2002.11102 On Feature Normalization and Data Augmentation
    3331, -- 2004.04696 BLEURT: Learning Robust Metrics for Text Generation
    3346, -- 2004.06063 BLEU might be Guilty but References are not Innocent
    3465, -- 2004.14667 NUBIA: NeUral Based Interchangeability Assessor for Text Generation
    3487, -- 2005.00192 KPQA: A Metric for Generative Question Answering Using Keyphrase Weights
    3493, -- 2005.00456 USR: An Unsupervised and Reference Free Evaluation Metric for Dialog Generation
    3506, -- 2005.00771 ProtoQA: A Question Answering Dataset for Prototypical Common-Sense Reasoning
    3529, -- 2005.02324 Neural CRF Model for Sentence Alignment in Text Simplification
    3545, -- 2005.03754 FEQA: A Question Answering Evaluation Framework for Faithfulness Assessment in A
    3689, -- 2006.05621 Understanding Points of Correspondence between Sentences for Abstractive Summari
    3693, -- 2006.05987 Revisiting Few-sample BERT Fine-tuning
    3863, -- 2007.02871 DART: Open-Domain Structured Data Record to Text Generation
    3929, -- 2007.12626 SummEval: Re-evaluating Summarization Evaluation
    4076, -- 2008.12009 A Survey of Evaluation Metrics Used for NLG Systems
    4094, -- 2009.00590 Summary-Source Proposition-level Alignment: Task, Datasets and Supervised Baseli
    4147, -- 2009.06978 Dialogue Response Ranking Training with Large-Scale Human Feedback Data
    4173, -- 2009.09025 COMET: A Neural Framework for MT Evaluation
    4209, -- 2009.12506 Learning to Plan and Realize Separately for Open-Ended Dialogue Systems
    4290, -- 2010.03205 Like hiking? You probably enjoy nature: Persona-grounded Dialog with Commonsense
    4295, -- 2010.03636 MOCHA: A Dataset for Training and Evaluating Generative Reading Comprehension Me
    4300, -- 2010.03726 Learning to Fuse Sentences with Transformers for Summarization
    4359, -- 2010.07999 What is More Likely to Happen Next? Video-and-Language Future Event Prediction
    4424, -- 2010.12321 BARThez: a Skilled Pretrained French Sequence-to-Sequence Model
    4427, -- 2010.12688 Knowledge Graph Based Synthetic Corpus Generation for Knowledge-Enhanced Languag
    4436, -- 2010.12826 Text Editing by Command
    4471, -- 2010.15535 Unbabel's Participation in the WMT20 Metrics Shared Task
    4483, -- 2011.00519 CHIME: Cross-passage Hierarchical Memory Network for Generative Review Question
    4485, -- 2011.00620 Social Chemistry 101: Learning to Reason about Social and Moral Norms
    4487, -- 2011.00679 Liputan6: A Large-scale Indonesian Dataset for Text Summarization
    4502, -- 2011.02593 Detecting Hallucinated Content in Conditional Neural Sequence Generation
    4596, -- 2011.10819 Evaluating Semantic Accuracy of Data-to-Text Generation with Natural Language In
    4695, -- 2012.04281 CTRLsum: Towards Generic Controllable Text Summarization
    4764, -- 2012.11157 Narrative Incoherence Detection
    4835, -- 2101.00190 Prefix-Tuning: Optimizing Continuous Prompts for Generation
    4918, -- 2101.08382 ParaSCI: A Large Scientific Paraphrase Dataset for Longer Paraphrase Generation
    4953, -- 2101.11272 VisualMRC: Machine Reading Comprehension on Document Images
    4974, -- 2102.01454 MAUVE: Measuring the Gap Between Neural Text and Human Text using Divergence Fro
    4977, -- 2102.01672 The GEM Benchmark: Natural Language Generation, its Evaluation and Metrics
    5090, -- 2102.12206 PADA: Example-based Prompt Learning for on-the-fly Adaptation to Unseen Domains
    5141, -- 2103.02548 NaturalConv: A Chinese Dialogue Dataset Towards Multi-turn Topic-driven Conversa
    5440, -- 2104.06486 MS2: Multi-Document Summarization of Medical Studies
    5466, -- 2104.07555 Data-QuestEval: A Referenceless Metric for Data-to-Text Semantic Evaluation
    5471, -- 2104.07605 SummVis: Interactive Visual Analysis of Models, Data, and Evaluation for Text Su
    5485, -- 2104.08200 IndoNLG: Benchmark and Resources for Evaluating Indonesian Natural Language Gene
    5486, -- 2104.08202 $Q^{2}$: Evaluating Factual Consistency in Knowledge-Grounded Dialogues via Ques
    5492, -- 2104.08296 Learning to Reason for Text Generation from Scientific Tables
    5511, -- 2104.08718 CLIPScore: A Reference-free Evaluation Metric for Image Captioning
    5661, -- 2105.03279 Generating abstractive summaries of Lithuanian news articles using a transformer
    5739, -- 2105.08021 Stage-wise Fine-tuning for Graph-to-Text Generation
    5744, -- 2105.08209 BookSum: A Collection of Datasets for Long-form Narrative Summarization
    5755, -- 2105.08920 OpenMEVA: A Benchmark for Evaluating Open-ended Story Generation Metrics
    5834, -- 2106.00507 Towards Quantifiable Dialogue Coherence Evaluation
    5844, -- 2106.00920 DialoGraph: Incorporating Interpretable Strategy-Graph Networks into Negotiation
    5866, -- 2106.01890 SimCLS: A Simple Framework for Contrastive Learning of Abstractive Summarization
    5944, -- 2106.05546 Progressive Multi-Granularity Training for Non-Autoregressive Translation
    5960, -- 2106.06052 Dynaboard: An Evaluation-As-A-Service Platform for Holistic Next-Generation Benc
    5980, -- 2106.06937 Common Sense Beyond English: Evaluating and Improving Multilingual Language Mode
    6009, -- 2106.08364 Unsupervised Enrichment of Persona-grounded Dialog with Background Stories
    6044, -- 2106.10084 Subjective Bias in Abstractive Summarization
    6080, -- 2106.11520 BARTScore: Evaluating Generated Text as Text Generation
    6202, -- 2107.03760 HinGE: A Dataset for Generation and Evaluation of Code-Mixed Hinglish Text
    6355, -- 2108.01369 How to Evaluate Your Dialogue Models: A Review of Approaches
    6406, -- 2108.05289 Icelandic Parallel Abstracts Corpus
    6418, -- 2108.06130 Semantic Answer Similarity for Evaluating Question Answering Models
    6500, -- 2108.12560 QACE: Asking Questions to Evaluate an Image Caption
    6503, -- 2108.12738 SummerTime: Text Summarization Toolkit for Non-experts
    6524, -- 2109.00087 It's not Rocket Science : Interpreting Figurative Language in Narratives
    6591, -- 2109.04593 A Large-Scale Study of Machine Translation in the Turkic Languages
    6602, -- 2109.05006 BiSECT: Learning to Split and Rephrase Sentences with Bitexts
    6609, -- 2109.05160 StreamHover: Livestream Transcript Summarization and Annotation
    6625, -- 2109.06352 Uncertainty-Aware Machine Translation Evaluation
    6626, -- 2109.06379 Compression, Transduction, and Creation: A Unified Framework for Evaluating Natu
    6629, -- 2109.06427 Commonsense-Focused Dialogues for Response Generation: An Empirical Study
    6639, -- 2109.06822 LM-Critic: Language Models for Unsupervised Grammatical Error Correction
    6701, -- 2109.10862 Recursively Summarizing Books with Human Feedback
    6852, -- 2110.04292 Toward a Visual Concept Vocabulary for GAN Latent Space
    6869, -- 2110.05006 Pre-trained Language Models in Biomedical Domain: A Systematic Survey
    6899, -- 2110.06263 Speech Summarization using Restricted Self-Attention
    6905, -- 2110.06341 Learning Compact Metrics for MT
    6928, -- 2110.07166 CaPE: Contrastive Parameter Ensembling for Reducing Hallucination in Abstractive
    6939, -- 2110.07520 Comparative Opinion Summarization via Collaborative Decoding
    6963, -- 2110.08175 MixQG: Neural Question Generation with Mixed Answer Types
    7114, -- 2111.00539 Template Filling for Controllable Commonsense Reasoning
    7144, -- 2111.02110 Automatic Evaluation and Moderation of Open-domain Dialogue Systems
    7159, -- 2111.02840 Adversarial GLUE: A Multi-Task Benchmark for Robustness Evaluation of Language M
    7515, -- 2112.08313 Measure and Improve Robustness in NLP Models: A Survey
    7522, -- 2112.08542 QAFactEval: Improved QA-Based Factual Consistency Evaluation for Summarization
    7530, -- 2112.08619 Call for Customized Conversation: Customized Conversation Grounding Persona and
    7541, -- 2112.08804 CrossSum: Beyond English-Centric Cross-Lingual Summarization for 1,500+ Language
    7570, -- 2112.10322 Article Reranking by Memory-Enhanced Key Sentence Matching for Detecting Previou
    7695, -- 2201.05337 A Survey of Controllable Text Generation using Transformer-based Pre-trained Lan
    7729, -- 2201.07520 CM3: A Causal Masked Multimodal Model of the Internet
    7782, -- 2201.11114 Natural Language Descriptions of Deep Visual Features
    7784, -- 2201.11176 DiscoScore: Evaluating Text Generation with BERT and Discourse Coherence
    7898, -- 2202.03629 Survey of Hallucination in Natural Language Generation
    7901, -- 2202.03799 What are the best systems? New perspectives on NLP Benchmarking
    7937, -- 2202.05599 ClidSum: A Benchmark Dataset for Cross-Lingual Dialogue Summarization
    7951, -- 2202.06633 FlowEval: A Consensus-Based Dialogue Evaluation Framework Using Segment Act Flow
    7962, -- 2202.06935 Repairing the Cracked Foundation: A Survey of Obstacles in Evaluation Practices
    7974, -- 2202.07654 Tomayto, Tomahto. Beyond Token-level Answer Equivalence for Question Answering E
    7994, -- 2202.08479 On the Evaluation Metrics for Paraphrase Generation
    8046, -- 2202.11705 COLD Decoding: Energy-based Constrained Text Generation with Langevin Dynamics
    8075, -- 2202.13196 Toward Interpretable Semantic Textual Similarity via Optimal Transport-based Con
    8084, -- 2202.13581 'Tis but Thy Name: Semantic Question Answering Evaluation with 11M Names for 1M
    8170, -- 2203.03759 IT5: Text-to-text Pretraining for Italian Language Understanding and Generation
    8171, -- 2203.03802 Understanding Iterative Revision from Human-Written Text
    8243, -- 2203.07264 Show Me More Details: Discovering Hierarchies of Procedures from Semi-structured
    8244, -- 2203.07285 Diversifying Content Generation for Commonsense Reasoning with Mixture of Knowle
    8290, -- 2203.08480 E-KAR: A Benchmark for Rationalizing Natural Language Analogical Reasoning
    8311, -- 2203.09183 RoMe: A Robust Metric for Evaluating Natural Language Generation
    8333, -- 2203.10012 Report from the NSF Future Directions Workshop on Automatic Evaluation of Dialog
    8371, -- 2203.11370 Language modeling via stochastic processes
    8433, -- 2203.14187 Educational Question Generation of Children Storybooks via Question Type Distrib
    8479, -- 2203.15827 LinkBERT: Pretraining Language Models with Document Links
    8503, -- 2203.16804 BRIO: Bringing Order to Abstractive Summarization
    8594, -- 2204.02952 Inducing Positive Perspectives with Text Reframing
    8630, -- 2204.03905 BioBART: Pretraining and Evaluation of A Biomedical Generative Language Model
    8656, -- 2204.04813 Explanation Graph Generation via Pre-trained Language Models: An Empirical Study
    8662, -- 2204.04991 TRUE: Re-evaluating Factual Consistency Evaluation
    8707, -- 2204.06546 Disentangling Uncertainty in Machine Translation Evaluation
    8775, -- 2204.08776 IndicXNLI: Evaluating Multilingual Inference for Indian Languages
    8801, -- 2204.10290 Learning to Revise References for Faithful Summarization
    8819, -- 2204.10703 Persona-Guided Planning for Controlling the Protagonist's Persona in Story Gener
    8820, -- 2204.10757 FaithDial: A Faithful Benchmark for Information-Seeking Dialogue
    8838, -- 2204.11817 Translation between Molecules and Natural Language
    8862, -- 2204.12951 An End-to-End Dialogue Summarization System for Sales Calls
    8897, -- 2205.00379 The Cross-lingual Conversation Summarization Challenge
    8906, -- 2205.00978 Quality-Aware Decoding for Neural Machine Translation
    9002, -- 2205.05812 Open Vocabulary Extreme Classification Using Generative Models
    9014, -- 2205.06207 CiteSum: Citation Text-guided Scientific Extreme Summarization and Domain Adapta
    9021, -- 2205.06938 Generating Literal and Implied Subquestions to Fact-check Complex Claims
    9039, -- 2205.08478 An Evaluation Framework for Legal Document Summarization
    9054, -- 2205.09314 Target-Guided Dialogue Response Generation Using Commonsense and Data Augmentati
    9100, -- 2205.10646 Context Matters for Image Descriptions for Accessibility: Challenges for Referen
    9109, -- 2205.10782 Instruction Induction: From Few Examples to Natural Language Task Descriptions
    9131, -- 2205.11465 SQuALITY: Building a Long-Document Summarization Dataset the Hard Way
    9161, -- 2205.12393 Fine-tuned Language Models are Continual Learners
    9171, -- 2205.12548 RLPrompt: Optimizing Discrete Text Prompts with Reinforcement Learning
    9193, -- 2205.12854 Understanding Factual Errors in Summarization: Errors, Summarizers, Datasets, Er
    9203, -- 2205.13115 Fine-grained Image Captioning with CLIP Reward
    9255, -- 2205.14690 CoNT: Contrastive Neural Text Generation
    9258, -- 2205.14727 CPED: A Large-Scale Chinese Personalized and Emotional Dialogue Dataset for Conv
    9389, -- 2206.02928 Neuro-Symbolic Procedural Planning with Commonsense Prompting
    9401, -- 2206.03333 Assessing Project-Level Fine-Tuning of ML4SE Models
    9416, -- 2206.04105 Words are all you need? Language as an approximation for human similarity judgme
    9519, -- 2206.08713 Evaluating the Impact of Source Code Parsers on ML4SE Models
    9547, -- 2206.09676 Studying the role of named entities for content preservation in text style trans
    9571, -- 2206.10883 Multi-LexSum: Real-World Summaries of Civil Rights Lawsuits at Multiple Granular
    9580, -- 2206.11309 GODEL: Large-Scale Pre-Training for Goal-Directed Dialog
    9707, -- 2207.03240 CoQAR: Question Rewriting on CoQA
    9779, -- 2207.06130 Fuse It More Deeply! A Variational Transformer with Layer-Wise Latent Variable I
    9880, -- 2207.11363 Knowledge-Grounded Conversational Data Augmentation with Generative Conversation
    9983, -- 2208.03133 Out of the BLEU: how should we assess quality of the Code Generation models?
    9996, -- 2208.03898 DialogSum Challenge: Results of the Dialogue Summarization Shared Task
    9999, -- 2208.04163 Abstractive Meeting Summarization: A Survey
    10009, -- 2208.04826 Compositional Evaluation on Japanese Textual Entailment and Similarity
    10015, -- 2208.05309 Looking for a Needle in a Haystack: A Comprehensive Study of Hallucinations in N
    10128, -- 2208.11646 Of Human Criteria and Automatic Metrics: A Benchmark of the Evaluation of Story
    10159, -- 2208.13078 MDIA: A Benchmark for Multilingual Dialogue Generation in 46 Languages
    10160, -- 2208.13265 Podcast Summary Assessment: A Resource for Evaluating Summary Assessment Methods
    10192, -- 2209.00465 On Grounded Planning for Embodied Tasks with Language Models
    10204, -- 2209.00930 Mind the Gap! Injecting Commonsense Knowledge for Abstractive Dialogue Summariza
    10220, -- 2209.01835 Multi-Figurative Language Generation
    10223, -- 2209.02427 Multi-Modal Experience Inspired AI Creation
    10296, -- 2209.07351 Rethinking Round-Trip Translation for Machine Translation Evaluation
    10319, -- 2209.08163 Belief Revision based Caption Re-ranker with Visual Semantic Information
    10358, -- 2209.09593 EffEval: A Comprehensive Evaluation of Efficiency for MT Evaluation Metrics
    10411, -- 2209.12356 News Summarization and Evaluation in the Era of GPT-3
    10421, -- 2209.13101 WikiDes: A Wikipedia-Based Dataset for Generating Short Descriptions from Paragr
    10426, -- 2209.13331 EditEval: An Instruction-Based Benchmark for Text Improvements
    10448, -- 2209.14500 Bidirectional Language Models Are Also Few-shot Learners
    10479, -- 2209.15301 Medical Question Understanding and Answering with Knowledge Grounding and Semant
    10492, -- 2210.00045 Calibrating Sequence likelihood Improves Conditional Language Generation
    10531, -- 2210.01241 Is Reinforcement Learning (Not) for Natural Language Processing: Benchmarks, Bas
    10614, -- 2210.03273 A Unified Encoder-Decoder Framework with Entity Memory
    10628, -- 2210.03568 How Large Language Models are Transforming Machine-Paraphrased Plagiarism
    10650, -- 2210.03992 Generative Language Models for Paragraph-Level Question Generation
    10679, -- 2210.04829 Hierarchical3D Adapters for Long Video-to-text Summarization
    10685, -- 2210.05035 Not All Errors are Equal: Learning Text Generation Metrics using Stratified Erro
    10688, -- 2210.05109 BanglaParaphrase: A High-Quality Bangla Paraphrase Dataset
    10780, -- 2210.06996 DICTDIS: Dictionary Constrained Disambiguation for Improved NMT
    10786, -- 2210.07128 Language Models of Code are Few-Shot Commonsense Learners
    10791, -- 2210.07197 Towards a Unified Multi-Dimensional Evaluator for Text Generation
    10821, -- 2210.07777 LEATHER: A Framework for Learning to Generate Human-like Text in Dialogue
    10835, -- 2210.08444 Model Criticism for Long-Form Text Generation
    10851, -- 2210.08859 Social Biases in Automatic Evaluation Metrics for NLG
    10855, -- 2210.08933 DiffuSeq: Sequence to Sequence Text Generation with Diffusion Models
    10896, -- 2210.10332 Revision Transformers: Instructing Language Models to Change their Values
    10957, -- 2210.12152 WikiWhy: Answering and Explaining Cause-and-Effect Questions
    10974, -- 2210.12467 ECTSum: A New Benchmark Dataset For Bullet Point Summarization of Long Earnings
    10999, -- 2210.12813 TAPE: Assessing Few-shot Russian Language Understanding
    11003, -- 2210.12865 Knowledge Transfer from Answer Ranking to Answer Generation
    11056, -- 2210.14140 Contrastive Search Is What You Need For Neural Text Generation
    11071, -- 2210.14667 A Bilingual Parallel Corpus with Discourse Annotations
    11109, -- 2210.15615 ACES: Translation Accuracy Challenge Sets for Evaluating Machine Translation Met
    11124, -- 2210.16407 Just-DREAM-about-it: Figurative Language Understanding with DREAM-FLUTE
    11128, -- 2210.16732 How Far are We from Robust Long Abstractive Summarization?
    11143, -- 2210.17418 Controllable Factuality in Document-Grounded Dialog Systems Using a Noisy Channe
    11157, -- 2211.00255 CARE: Causality Reasoning for Empathetic Responses by Conditional Graph Generati
    11342, -- 2211.07634 Follow the Wisdom of the Crowd: Effective Text Generation via Minimum Bayes Risk
    11366, -- 2211.08387 AutoTemplate: A Simple Recipe for Lexically Constrained Text Generation
    11379, -- 2211.08723 Noisy Pairing and Partial Supervision for Stylized Opinion Summarization
    11384, -- 2211.08983 Is my automatic audio captioning system so bad? spider-max: a metric to consider
    11515, -- 2211.12118 HaRiM$^+$: Evaluating Summary Quality with Hallucination Risk
    11546, -- 2211.12737 RoentGen: Vision-Language Foundation Model for Chest X-ray Generation
    11554, -- 2211.12835 Automatic Generation of Socratic Subquestions for Teaching Math Word Problems
    11606, -- 2211.13892 Complementary Explanations for Effective In-Context Learning
    11720, -- 2211.17135 BudgetLongformer: Can we Cheaply Pretrain a SotA Legal Language Model From Scrat
    11733, -- 2212.00193 Distilling Reasoning Capabilities into Smaller Language Models
    11957, -- 2212.06909 Imagen Editor and EditBench: Advancing and Evaluating Text-Guided Image Inpainti
    11993, -- 2212.07919 ROSCOE: A Suite of Metrics for Scoring Step-by-Step Reasoning
    11997, -- 2212.07981 Revisiting the Gold Standard: Grounding Summarization Evaluation with Robust Hum
    12036, -- 2212.08775 RISE: Leveraging Retrieval Techniques for Summarization Evaluation
    12070, -- 2212.09462 Latent Diffusion for Language Generation
    12083, -- 2212.09689 Unnatural Instructions: Tuning Language Models with (Almost) No Human Labor
    12092, -- 2212.09739 LENS: A Learnable Evaluation Metric for Text Simplification
    12093, -- 2212.09741 One Embedder, Any Task: Instruction-Finetuned Text Embeddings
    12108, -- 2212.10057 WeCheck: Strong Factual Consistency Checker via Weakly Supervised Learning
    12125, -- 2212.10325 SeqDiffuSeq: Text Diffusion with Encoder-Decoder Transformers
    12129, -- 2212.10409 ClarifyDelphi: Reinforced Clarification Questions with Defeasibility Rewards for
    12135, -- 2212.10449 Socratic Pretraining: Question-Driven Pretraining for Controllable Summarization
    12144, -- 2212.10525 SLUE Phase-2: A Benchmark Suite of Diverse Spoken Language Understanding Tasks
    12147, -- 2212.10543 Detoxifying Text with MaRCo: Controllable Revision with Experts and Anti-Experts
    12160, -- 2212.10618 Ontologically Faithful Generation of Non-Player Character Dialogues
    12257, -- 2212.14578 MAUVE Scores for Generative Models: Theory and Practice
    12328, -- 2301.02401 You Truly Understand What I Need: Intellectual and Friendly Dialogue Agents grou
    12354, -- 2301.03403 A comprehensive review of automatic text summarization techniques: method, data,
    12427, -- 2301.07095 On the State of German (Abstractive) Text Summarization
    12464, -- 2301.08784 Visual Semantic Relatedness Dataset for Image Captioning
    12469, -- 2301.09017 Transfer Knowledge from Natural Language to Electrocardiography: Can We Detect C
    12492, -- 2301.09790 The Next Chapter: A Study of Large Language Models in Storytelling
    12623, -- 2301.12307 MQAG: Multiple-choice Question Answering and Generation for Assessing Informatio
    12725, -- 2301.13848 Benchmarking Large Language Models for News Summarization
    12770, -- 2302.00954 Curriculum-guided Abstractive Summarization for Mental Health Online Posts
    12899, -- 2302.03162 Protecting Language Generation Models via Invisible Watermarking
    12935, -- 2302.03848 Controlling Personality Style in Dialogue with Zero-Shot Prompt-Based Learning
    12946, -- 2302.04023 A Multitask, Multilingual, Multimodal Evaluation of ChatGPT on Reasoning, Halluc
    12950, -- 2302.04166 GPTScore: Evaluate as You Desire
    13024, -- 2302.05574 NapSS: Paragraph-level Medical Text Simplification via Narrative Prompting and S
    13158, -- 2302.08575 Foundation Models for Natural Language Processing -- Pre-trained Language Models
    13175, -- 2302.09051 Complex QA and language models hybrid architectures, Survey
    13254, -- 2302.11520 Guiding Large Language Models via Directional Stimulus Prompting
    13308, -- 2302.12813 Check Your Facts and Try Again: Improving Large Language Models with External Kn
    13358, -- 2302.14229 Zero-Shot Cross-Lingual Summarization via Large Language Models
    13392, -- 2302.14785 Joint Representations of Text and Knowledge Graphs for Retrieval and Evaluation
    13549, -- 2303.04048 Is ChatGPT a Good NLG Evaluator? A Preliminary Study
    13946, -- 2303.11504 Language Model Behavior: A Comprehensive Survey
    13986, -- 2303.12060 VideoXum: Cross-modal Visual and Textural Summarization of Videos
    14052, -- 2303.13310 SwissBERT: The Multilingual Language Model for Switzerland
    14098, -- 2303.14070 ChatDoctor: A Medical Chat Model Fine-Tuned on a Large Language Model Meta-AI (L
    14188, -- 2303.15422 KPEval: Towards Fine-Grained Semantic-Based Keyphrase Evaluation
    14198, -- 2303.15621 ChatGPT as a Factual Inconsistency Evaluator for Text Summarization
    14244, -- 2303.16406 Hierarchical Video-Moment Retrieval and Step-Captioning
    14260, -- 2303.16634 G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment
    14271, -- 2303.16899 AutoAD: Movie Description in Context
    14282, -- 2303.17071 DERA: Enhancing Large Language Model Completions with Dialog-Enabled Resolving A
    14382, -- 2304.00723 Exploring the Use of Large Language Models for Reference-Free Text Quality Evalu
    14388, -- 2304.00869 GreekBART: The First Pretrained Greek Sequence-to-Sequence Model
    14418, -- 2304.01412 The StatCan Dialogue Dataset: Retrieving Data Tables through Conversations with
    14447, -- 2304.01894 San-BERT: Extractive Summarization for Sanskrit Documents using BERT and it's va
    14512, -- 2304.03347 Towards Interpretable Mental Health Analysis with Large Language Models
    14521, -- 2304.03512 Hierarchical Catalogue Generation for Literature Review: A Benchmark
    14560, -- 2304.04370 OpenAGI: When LLM Meets Domain Experts
    14693, -- 2304.06815 Automatic Semantic Augmentation of Language Model Prompts (for Code Summarizatio
    14707, -- 2304.07101 Task-oriented Document-Grounded Dialog Systems by HLTPR@RWTH for DSTC9 and DSTC1
    14781, -- 2304.09161 Perspectives on Large Language Models for Relevance Judgment
    14813, -- 2304.09848 Evaluating Verifiability in Generative Search Engines
    14836, -- 2304.10417 SINC: Spatial Composition of 3D Human Motions for Simultaneous Action Generation
    14889, -- 2304.11406 LaMP: When Large Language Models Meet Personalization
    14913, -- 2304.12102 Unlocking Context Constraints of LLMs: Enhancing Context Efficiency of LLMs with
    14932, -- 2304.12519 GlyphDiffusion: Text Generation as Image Generation
    14955, -- 2304.13005 Evaluating Inter-Bilingual Semantic Parsing for Indian Languages
    15009, -- 2304.14104 Learning Human-Human Interactions in Images from Weak Textual Supervision
    15085, -- 2305.00450 SMILE: Single-turn to Multi-turn Inclusive Language Expansion via ChatGPT for Me
    15104, -- 2305.00955 Bridging the Gap: A Survey on Integrating (Human) Feedback for Natural Language
    15118, -- 2305.01146 RadAdapt: Radiology Report Summarization via Lightweight Domain Adaptation of La
    15135, -- 2305.01498 Summarizing Multiple Documents with Conversational Structure for Meta-Review Gen
    15139, -- 2305.01528 FIREBALL: A Dataset of Dungeons and Dragons Actual-Play with Structured Game Sta
    15148, -- 2305.01625 Unlimiformer: Long-Range Transformers with Unlimited Length Input
    15154, -- 2305.01645 Distill or Annotate? Cost-Efficient Fine-Tuning of Compact Models
    15266, -- 2305.03514 Can Large Language Models Transform Computational Social Science?
    15363, -- 2305.05252 Distilling Script Knowledge from Large Language Models for Constrained Language
    15375, -- 2305.05471 Beyond Good Intentions: Reporting the Research Landscape of NLP for Social Good
    15414, -- 2305.06156 The Vault: A Comprehensive Multilingual Dataset for Advancing Code Understanding
    15427, -- 2305.06311 Automatic Evaluation of Attribution by Large Language Models
    15449, -- 2305.06575 Chain-of-Dictionary Prompting Elicits Translation in Large Language Models
    15502, -- 2305.07615 What are the Desired Characteristics of Calibration Sets? Identifying Correlates
    15510, -- 2305.07797 ACCENT: An Automatic Event Commonsense Evaluation Metric for Open-Domain Dialogu
    15535, -- 2305.08200 A Cognitive Stimulation Dialogue System with Multi-source Knowledge Fusion for E
    15542, -- 2305.08285 Parameter-Efficient Fine-Tuning with Layer Pruning on Free-Text Sequence-to-Sequ
    15552, -- 2305.08379 TESS: Text-to-Text Self-Conditioned Simplex Diffusion
    15577, -- 2305.08844 RL4F: Generating Natural Language Feedback with Reinforcement Learning for Repai
    15587, -- 2305.08982 Helping the Helper: Supporting Peer Counselors via AI-Empowered Practice and Fee
    15601, -- 2305.09220 Towards Unifying Multi-Lingual and Cross-Lingual Summarization
    15636, -- 2305.09863 Explaining black box text modules in natural language with language models
    15663, -- 2305.10387 Elaborative Simplification as Implicit Questions Under Discussion
    15675, -- 2305.10438 IMAGINATOR: Pre-Trained Image+Text Joint Embeddings using Word-Level Grounding o
    15713, -- 2305.10930 On the Off-Target Problem of Zero-Shot Multilingual Neural Machine Translation
    15728, -- 2305.11142 Discourse Centric Evaluation of Machine Translation with a Densely Annotated Par
    15735, -- 2305.11170 Efficient Prompting via Dynamic In-Context Learning
    15766, -- 2305.11517 DiffuSIA: A Spiral Interaction Architecture for Encoder-Decoder Text Diffusion
    15770, -- 2305.11541 Empower Large Language Model to Perform Better on Industrial Domain-Specific Que
    15789, -- 2305.11747 HaluEval: A Large-Scale Hallucination Evaluation Benchmark for Large Language Mo
    15804, -- 2305.11862 Reducing Sequence Length by Predicting Edit Operations with Large Language Model
    15829, -- 2305.12140 Movie101: A New Movie Understanding Benchmark
    15881, -- 2305.12759 Kanbun-LM: Reading and Translating Classical Chinese in Japanese Methods by Lang
    15923, -- 2305.13194 SEAHORSE: A Multilingual, Multifaceted Dataset for Summarization Evaluation
    15926, -- 2305.13235 SPARSEFIT: Few-shot Prompting with Sparse Fine-tuning for Jointly Generating Pre
    15939, -- 2305.13301 Training Diffusion Models with Reinforcement Learning
    15940, -- 2305.13303 Towards Unsupervised Recognition of Token-level Semantic Differences in Related
    15956, -- 2305.13504 Neural Machine Translation for Code Generation
    15968, -- 2305.13626 Prompting and Evaluating Large Language Models for Proactive Dialogues: Clarific
    15982, -- 2305.13703 MemeCap: A Dataset for Captioning and Interpreting Memes
    15983, -- 2305.13711 LLM-Eval: Unified Multi-Dimensional Automatic Evaluation for Open-Domain Convers
    16009, -- 2305.13903 Let's Think Frame by Frame with VIP: A Video Infilling and Prediction Dataset fo
    16051, -- 2305.14239 On Learning to Summarize with Large Language Models as References
    16053, -- 2305.14251 FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text
    16055, -- 2305.14259 SciMON: Scientific Inspiration Machines Optimized for Novelty
    16056, -- 2305.14282 INSTRUCTSCORE: Explainable Text Generation Evaluation with Finegrained Feedback
    16060, -- 2305.14303 QTSumm: Query-Focused Summarization over Tabular Data
    16072, -- 2305.14336 Schema-Driven Information Extraction from Heterogeneous Tables
    16084, -- 2305.14458 Dancing Between Success and Failure: Edit-level Simplification Evaluation using
    16094, -- 2305.14536 MathDial: A Dialogue Tutoring Dataset with Rich Pedagogical Properties Grounded
    16119, -- 2305.14702 DecipherPref: Analyzing Influential Factors in Human Preference Judgments via GP
    16150, -- 2305.14835 SummIt: Iterative Text Summarization via ChatGPT
    16157, -- 2305.14869 CAR: Conceptualization-Augmented Reasoner for Zero-Shot Commonsense Question Ans
    16201, -- 2305.15067 Not All Metrics Are Guilty: Improving NLG Evaluation by Diversifying References
    16208, -- 2305.15080 Visually-Situated Natural Language Understanding with Contrastive Reading Model
    16238, -- 2305.15344 Learning Answer Generation using Supervision from Automatic Question Answering E
    16284, -- 2305.15852 Self-contradictory Hallucinations of Large Language Models: Evaluation, Detectio
    16314, -- 2305.16259 Neural Natural Language Processing for Long Texts: A Survey on Classification an
    16347, -- 2305.16635 Impossible Distillation: from Low-Quality Model to High-Quality Dataset & Model
    16355, -- 2305.16739 AlignScore: Evaluating Factual Consistency with a Unified Alignment Function
    16358, -- 2305.16784 Incorporating Distributions of Discourse Structure for Long Document Abstractive
    16371, -- 2305.16895 UMSE: Unified Multi-scenario Summarization Evaluation
    16381, -- 2305.16967 Evaluating Open-Domain Dialogues in Latent Space with Next Sentence Prediction a
    16432, -- 2305.17497 FACTUAL: A Benchmark for Faithful and Consistent Textual Scene Graph Parsing
    16436, -- 2305.17529 MeetingBank: A Benchmark Dataset for Meeting Summarization
    16460, -- 2305.17779 Generating EDU Extracts for Plan-Guided Summary Re-Ranking
    16467, -- 2305.17926 Large Language Models are not Fair Evaluators
    16585, -- 2305.18939 DEPLAIN: A German Parallel Corpus with Intralingual Translations into Plain Lang
    16613, -- 2305.19213 The Magic of IF: Investigating Causal Reasoning Abilities in Large Language Mode
    16634, -- 2305.19472 PlaSma: Making Small Language Models Better Procedural Knowledge Models for (Cou
    16714, -- 2306.00168 Measuring the Robustness of NLP Models to Domain Shifts
    16739, -- 2306.00398 Preference-grounded Token-level Guidance for Language Model Fine-tuning
    16763, -- 2306.00652 Explanation Graph Generation via Generative Pre-training over Synthetic Graphs
    16860, -- 2306.01549 Evaluating Machine Translation Quality with Conformal Predictive Distributions
    16901, -- 2306.01941 AI Transparency in the Age of LLMs: A Human-Centered Research Roadmap
    16908, -- 2306.01985 COBRA Frames: Contextual Reasoning about Effects and Harms of Offensive Statemen
    16913, -- 2306.02022 ACI-BENCH: a Novel Ambient Clinical Intelligence Dataset for Benchmarking Automa
    16942, -- 2306.02531 PLANNER: Generating Diversified Paragraph via Latent Language Diffusion Model
    16946, -- 2306.02561 LLM-Blender: Ensembling Large Language Models with Pairwise Ranking and Generati
    16996, -- 2306.03100 Rethinking Model Evaluation as Narrowing the Socio-Technical Gap
    17079, -- 2306.04116 Unbalanced Optimal Transport for Unbalanced Word Alignment
    17084, -- 2306.04181 Benchmarking Foundation Models with Language-Model-as-an-Examiner
    17087, -- 2306.04216 MMSum: A Dataset for Multimodal Summarization and Thumbnail Generation of Videos
    17095, -- 2306.04334 Echoes from Alexandria: A Large Resource for Multilingual Book Summarization
    17097, -- 2306.04347 World Models for Math Story Problems
    17152, -- 2306.05087 PandaLM: An Automatic Evaluation Benchmark for LLM Instruction Tuning Optimizati
    17193, -- 2306.05443 PIXIU: A Large Language Model, Instruction Data and Evaluation Benchmark for Fin
    17228, -- 2306.06029 HiTZ@Antidote: Argumentation-driven Explainable Artificial Intelligence for Digi
    17368, -- 2306.07906 WebGLM: Towards An Efficient Web-Enhanced Question Answering System with Human P
    17459, -- 2306.09030 DiPlomat: A Dialogue Dataset for Situated Pragmatic Reasoning
    17528, -- 2306.09712 Semi-Offline Reinforcement Learning for Optimized Text Generation
    17545, -- 2306.09996 Investigating Prompting Techniques for Zero- and Few-Shot Visual Question Answer
    17572, -- 2306.10452 MISMATCH: Fine-grained Evaluation of Machine-generated Text with Mismatch Error
    17575, -- 2306.10543 UniMC: A Unified Framework for Long-Term Memory Conversation via Relevance Repre
    17601, -- 2306.11167 Large Language Models are Fixated by Red Herrings: Exploring Creative Problem So
    17640, -- 2306.11816 Learning to Generate Better Than Your LLM
    17773, -- 2306.14795 MotionGPT: Human Motion as a Foreign Language
    17865, -- 2306.16650 Multi-source Semantic Graph-based Multimodal Sarcasm Explanation Generation
    17884, -- 2306.16931 UMASS_BioNLP at MEDIQA-Chat 2023: Can LLMs generate high-quality synthetic note-
    17965, -- 2307.00963 Challenges in Domain-Specific Abstractive Summarization and How to Overcome them
    18046, -- 2307.02762 PRD: Peer Rank and Discussion Improve Large Language Model based Evaluations
    18048, -- 2307.02768 Training Models to Generate, Recognize, and Reframe Unhelpful Thoughts
    18061, -- 2307.03109 A Survey on Evaluation of Large Language Models
    18106, -- 2307.04018 Revisiting Cross-Lingual Summarization: A Corpus-based Study and A New Benchmark
    18241, -- 2307.07255 Dialogue Agents 101: A Beginner's Guide to Critical Ingredients for Designing Ef
    18268, -- 2307.07889 LLM Comparative Assessment: Zero-shot NLG Evaluation through Pairwise Comparison
    18294, -- 2307.08217 BASS: Block-wise Adaptation for Speech Summarization
    18312, -- 2307.08393 On the application of Large Language Models for language teaching and assessment
    18398, -- 2307.09758 Longitudinal Data and a Semantic Similarity Reward for Chest X-Ray Report Genera
    18418, -- 2307.10169 Challenges and Applications of Large Language Models
    18645, -- 2307.13989 This is not correct! Negation-aware Evaluation of Language Generation Systems
    18673, -- 2307.14367 Prot2Text: Multimodal Protein's Function Generation with GNNs and Transformers
    18723, -- 2307.15189 Med-Flamingo: a Multimodal Medical Few-shot Learner
    18775, -- 2307.16372 LP-MusicCaps: LLM-Based Pseudo Music Captioning
    18808, -- 2307.16877 Evaluating Correctness and Faithfulness of Instruction-Following Models for Ques
    18809, -- 2307.16883 HAGRID: A Human-LLM Collaborative Dataset for Generative Information-Seeking wit
    18813, -- 2308.00073 Trustworthiness of Children Stories Generated by Large Language Models
    18814, -- 2308.00085 Reasoning before Responding: Integrating Commonsense-based Causality Explanation
    18883, -- 2308.01544 Multimodal Neurons in Pretrained Text-Only Transformers
    18898, -- 2308.01862 Wider and Deeper LLM Networks are Fairer LLM Evaluators
    18932, -- 2308.02463 Towards Generalist Foundation Model for Radiology by Leveraging Web-scale 2D&3D
    18944, -- 2308.02570 Learning Implicit Entity-object Relations by Bidirectional Generative Alignment
    18972, -- 2308.03188 Automatically Correcting Large Language Models: Surveying the landscape of diver
    19084, -- 2308.04913 LLaMA-E: Empowering E-commerce Authoring with Object-Interleaved Instruction Fol
    19177, -- 2308.06502 Three Ways of Using Large Language Models to Evaluate Chat
    19188, -- 2308.06595 VisIT-Bench: A Benchmark for Vision-Language Instruction Following Inspired by R
    19232, -- 2308.07201 ChatEval: Towards Better LLM-based Evaluators through Multi-Agent Debate
    19313, -- 2308.08239 MemoChat: Tuning LLMs to Use Memos for Consistent Long-Range Open-Domain Convers
    19318, -- 2308.08295 CMD: a framework for Context-aware Model self-Detoxification
    19441, -- 2308.09729 MindMap: Knowledge Graph Prompting Sparks Graph of Thoughts in Large Language Mo
    19525, -- 2308.10397 FairMonitor: A Four-Stage Automatic Framework for Detecting Stereotypes and Bias
    19613, -- 2308.11276 Music Understanding LLaMA: Advancing Text-to-Music Generation with Question Answ
    19656, -- 2308.11764 Halo: Estimation and Reduction of Hallucinations in Open-Source Weak Large Langu
    19681, -- 2308.12030 Prompt-Based Length Controlled Generation with Reinforcement Learning
    19703, -- 2308.12261 Prompt2Model: Generating Deployable Models from Natural Language Instructions
    19713, -- 2308.12383 With a Little Help from your own Past: Prototypical Memory Networks for Image Ca
    19719, -- 2308.12488 GPTEval: A Survey on Assessments of ChatGPT and GPT-4
    19722, -- 2308.12539 CALM : A Multi-task Benchmark for Comprehensive Assessment of Language Model Bia
    19751, -- 2308.12960 Towards Realistic Zero-Shot Classification via Self Structural Semantic Alignmen
    19834, -- 2308.14089 MedAlign: A Clinician-Generated Dataset for Instruction Following with Electroni
    19955, -- 2308.16349 Affective Visual Dialog: A Large-Scale Benchmark for Emotional Reasoning Based o
    19978, -- 2308.16753 Context Aware Query Rewriting for Text Rankers using LLM
    20035, -- 2309.00916 BLSP: Bootstrapping Language-Speech Pre-training via Behavior Alignment of Conti
    20051, -- 2309.01157 Large Language Models for Generative Recommendation: A Survey and Visionary Disc
    20053, -- 2309.01219 Siren's Song in the AI Ocean: A Survey on Hallucination in Large Language Models
    20080, -- 2309.01617 DeViL: Decoding Vision features into Language
    20091, -- 2309.01809 Are Emergent Abilities in Large Language Models just In-Context Learning?
    20140, -- 2309.02654 Zero-Resource Hallucination Prevention for Large Language Models
    20271, -- 2309.05196 Does Writing with Language Models Reduce Content Diversity?
    20285, -- 2309.05447 DoG-Instruct: Towards Premium Instruction-Tuning Data via Text-Grounded Instruct
    20391, -- 2309.07382 Less is More for Long Document Summary Evaluation by LLMs
    20400, -- 2309.07430 Adapted Large Language Models Can Outperform Medical Experts in Clinical Text Su
    20454, -- 2309.08156 RADE: Reference-Assisted Dialogue Evaluation for Open-Domain Dialogue
    20462, -- 2309.08210 Investigating Answerability of LLMs for Long-Form Question Answering
    20496, -- 2309.08637 TextBind: Multi-turn Interleaved Multimodal Instruction-following in the Wild
    20503, -- 2309.08730 MusiLingo: Bridging Music and Text with Pre-trained Language Models for Music Ca
    20581, -- 2309.10066 Automatic Personalized Impression Generation for PET Reports Using Large Languag
    20610, -- 2309.10447 Toward Unified Controllable Text Generation via Regular Expression Instruction
    20641, -- 2309.10931 A Family of Pretrained Transformer Language Models for Russian
    20685, -- 2309.11439 Controlled Generation with Prompt Insertion for Natural Language Explanations in
    20723, -- 2309.12030 Striking Gold in Advertising: Standardization and Exploration of Ad Text Generat
    20735, -- 2309.12250 SQUARE: Automatic Question Answering Evaluation using Multiple Positive and Nega
    20759, -- 2309.12616 Unlocking Model Insights: A Dataset for Automated Model Card Generation
    20794, -- 2309.13007 ReConcile: Round-Table Conference Improves Reasoning via Consensus among Diverse
    20814, -- 2309.13182 Effective Distillation of Table-based Reasoning Ability from LLMs
    20826, -- 2309.13308 Calibrating LLM-Based Evaluator
    20922, -- 2309.14681 Are Human-generated Demonstrations Necessary for In-context Learning?
    20952, -- 2309.15217 RAGAS: Automated Evaluation of Retrieval Augmented Generation
    20982, -- 2309.15789 Large Language Model Routing with Benchmark Datasets
    21002, -- 2309.16090 TPE: Towards Better Compositional Reasoning over Conceptual Tools with Multi-per
    21066, -- 2309.17012 Benchmarking Cognitive Biases in Large Language Models as Evaluators
    21183, -- 2310.00752 TIGERScore: Towards Building Explainable Metric for All Text Generation Tasks
    21184, -- 2310.00754 Analyzing and Mitigating Object Hallucination in Large Vision-Language Models
    21212, -- 2310.01074 Back to the Future: Towards Explainable Temporal Reasoning with Large Language M
    21259, -- 2310.01432 Split and Merge: Aligning Position Biases in LLM-based Evaluators
    21265, -- 2310.01542 Fusing Models with Complementary Expertise
    21269, -- 2310.01568 Defending Against Authorship Identification Attacks
    21327, -- 2310.02118 TWIZ-v2: The Wizard of Multimodal Conversational-Stimulus
    21365, -- 2310.02567 Improving Automatic VQA Evaluation Using Large Language Models
    21487, -- 2310.03951 Chain of Natural Language Inference for Reducing Large Language Model Ungrounded
    21505, -- 2310.04363 Amortizing intractable inference in large language models
    21517, -- 2310.04445 LoFT: Local Proxy Fine-tuning For Improving Transferability Of Adversarial Attac
    21521, -- 2310.04484 Ada-Instruct: Adapting Instruction Generators for Complex Reasoning
    21562, -- 2310.04965 MULTISCRIPT: Multimodal Script Learning for Supporting Open Domain Everyday Task
    21597, -- 2310.05294 Hi Guys or Hi Folks? Benchmarking Gender-Neutral Machine Translation with the Ge
    21601, -- 2310.05317 Task-Adaptive Tokenization: Enhancing Long-Form Text Generation Efficacy in Ment
    21620, -- 2310.05470 Generative Judge for Evaluating Alignment
    21632, -- 2310.05657 A Closer Look into Automatic Evaluation Using Large Language Models
    21641, -- 2310.05736 LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Model
    21699, -- 2310.06282 MuseChat: A Conversational Music Recommendation System for Videos
    21715, -- 2310.06498 A New Benchmark and Reverse Validation Method for Passage-level Hallucination De
    21743, -- 2310.06838 AutoAD II: The Sequel -- Who, When, and What in Movie Audio Description
    21799, -- 2310.07521 Survey on Factuality in Large Language Models: Knowledge, Retrieval and Domain-S
    21848, -- 2310.08072 Training Generative Question-Answering on Synthetic Data Obtained from an Instru
    21856, -- 2310.08130 Fine-grained Conversational Decoding via Isotropic and Proximal Search
    21857, -- 2310.08152 Context Compression for Auto-regressive Transformers with Sentinel Tokens
    21891, -- 2310.08491 Prometheus: Inducing Fine-grained Evaluation Capability in Language Models
    22046, -- 2310.10505 ReMax: A Simple, Effective, and Efficient Reinforcement Learning Method for Alig
    22055, -- 2310.10623 Generating Summaries with Controllable Readability Levels
    22081, -- 2310.10707 Demonstrations Are All You Need: Advancing Offensive Content Paraphrasing using
    22099, -- 2310.10981 Instructive Dialogue Summarization with Query Aggregations
    22115, -- 2310.11324 Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design o
    22166, -- 2310.11976 InfoDiffusion: Information Entropy Aware Diffusion Process for Non-Autoregressiv
    22180, -- 2310.12109 Monarch Mixer: A Simple Sub-Quadratic GEMM-Based Architecture
    22181, -- 2310.12127 A Tale of Pronouns: Interpretability Informs Gender Bias Mitigation for Fairer I
    22182, -- 2310.12128 DiagrammerGPT: Generating Open-Domain, Open-Platform Diagrams via LLM Planning
    22197, -- 2310.12418 The Shifted and The Overlooked: A Task-oriented Investigation of User-GPT Intera
    22236, -- 2310.12971 CLAIR: Evaluating Image Captions with Large Language Models
    22257, -- 2310.13132 Better to Ask in English: Cross-Lingual Evaluation of Large Language Models for
    22261, -- 2310.13189 Fast and Accurate Factual Inconsistency Detection Over Long Documents
    22281, -- 2310.13385 Tuna: Instruction Tuning using Feedback from Large Language Models
    22287, -- 2310.13512 Improving Question Generation with Multi-level Content Planning
    22302, -- 2310.13682 Optimizing Retrieval-augmented Reader Models via Token Elimination
    22329, -- 2310.14053 Beyond Accuracy: Evaluating Self-Consistency of Code Large Language Models with
    22331, -- 2310.14103 Revisiting Instruction Fine-tuned Model Evaluation to Guide Industrial Applicati
    22346, -- 2310.14414 Vision Language Models in Autonomous Driving: A Survey and Outlook
    22350, -- 2310.14424 Which Prompts Make The Difference? Data Prioritization For Efficient Human LLM E
    22382, -- 2310.14735 Unleashing the potential of prompt engineering for large language models
    22394, -- 2310.14863 Paraphrase Types for Generation and Detection
    22412, -- 2310.15077 'Don't Get Too Technical with Me': A Discourse Structure-Based Framework for Sci
    22445, -- 2310.15405 GPT-4 as an Effective Zero-Shot Evaluator for Scientific Figure Captions
    22476, -- 2310.15773 BLESS: Benchmarking Large Language Models on Sentence Simplification
    22507, -- 2310.16197 Background Summarization of Event Timelines
    22531, -- 2310.16446 Diversity Enhanced Narrative Question Generation for Storybooks
    22556, -- 2310.16746 HANSEN: Human and AI Spoken Text Benchmark for Authorship Analysis
    22621, -- 2310.17631 JudgeLM: Fine-tuned Large Language Models are Scalable Judges
    22634, -- 2310.17743 StyleBART: Decorate Pretrained Model with Style Adapters for Unsupervised Stylis
    22648, -- 2310.17924 SOUL: Towards Sentiment and Opinion Understanding of Language
    22659, -- 2310.18119 Towards a Unified Conversational Recommendation System: Multi-task Learning via
    22674, -- 2310.18336 AITA Generating Moral Judgements of the Crowd with Reasoning
    22680, -- 2310.18344 Chainpoll: A high efficacy method for LLM hallucination detection
    22698, -- 2310.18600 MILDSum: A Novel Benchmark Dataset for Multilingual Summarization of Indian Lega
    22712, -- 2310.18794 Sequence-Level Certainty Reduces Hallucination In Knowledge-Grounded Dialogue Ge
    22767, -- 2310.19727 Generating Medical Prescriptions with Conditional Transformer
    22788, -- 2310.20072 Automatic Evaluation of Generative Models with Instruction Tuning
    22795, -- 2310.20195 Generating Continuations in Multilingual Idiomatic Contexts
    22928, -- 2311.01751 EmojiLM: Modeling the New Emoji Language
    22954, -- 2311.02271 FaMeSumm: Investigating and Improving Faithfulness of Medical Summarization
    23029, -- 2311.03998 Exploring Jiu-Jitsu Argumentation for Writing Peer Review Rebuttals
    23104, -- 2311.04939 LooGLE: Can Long-Context Language Models Understand Long Contexts?
    23115, -- 2311.05112 A Survey of Large Language Models in Medicine: Progress, Application, and Challe
    23189, -- 2311.06503 Knowledgeable Preference Alignment for LLMs in Domain-specific Question Answerin
    23197, -- 2311.06668 In-context Vectors: Making In Context Learning More Effective and Controllable T
    23218, -- 2311.07138 WaterBench: Towards Holistic Evaluation of Watermarks for Large Language Models
    23239, -- 2311.07453 ChartCheck: Explainable Fact-Checking over Real-World Chart Images
    23243, -- 2311.07469 InCA: Rethinking In-Car Conversational System Assessment Leveraging Large Langua
    23249, -- 2311.07556 Using Natural Language Explanations to Improve Robustness of In-context Learning
    23268, -- 2311.07767 GreekT5: A Series of Greek Sequence-to-Sequence Models for News Summarization
    23272, -- 2311.07850 Bring Your Own KG: Self-Supervised Program Synthesis for Zero-Shot KGQA
    23280, -- 2311.07978 How good are Large Language Models on African Languages?
    23299, -- 2311.08298 A Survey of Confidence Estimation and Calibration in Large Language Models
    23300, -- 2311.08303 Extrinsically-Focused Evaluation of Omissions in Medical Summarization
    23316, -- 2311.08389 PSST: A Benchmark for Evaluation-driven Text Public-Speaking Style Transfer
    23323, -- 2311.08469 UNcommonsense Reasoning: Abductive Reasoning about Uncommon Situations
    23331, -- 2311.08588 CodeScope: An Execution-based Multilingual Multitask Multidimensional Benchmark
    23377, -- 2311.09180 Pearl: Personalizing Large Language Model Writing Assistants with Generation-Cal
    23380, -- 2311.09188 Towards Verifiable Text Generation with Symbolic References
    23383, -- 2311.09204 Fusion-Eval: Integrating Assistant Evaluators with LLMs
    23424, -- 2311.09606 GistScore: Learning Better Representations for In-Context Example Selection with
    23447, -- 2311.09799 How Far Can We Extract Diverse Perspectives from Large Language Models?
    23455, -- 2311.09836 PELMS: Pre-training for Effective Low-Shot Multi-Document Summarization
    23460, -- 2311.10057 The Song Describer Dataset: a Corpus of Audio Captions for Music-and-Language Ev
    23578, -- 2311.12131 Human Learning by Model Feedback: The Dynamics of Iterative Prompting with Midjo
    23621, -- 2311.12803 On Copyright Risks of Text-to-Image Diffusion Models
    23639, -- 2311.13061 Attribution and Alignment: Effects of Local Context Repetition on Utterance Prod
    23709, -- 2311.14199 A Systematic Review of Deep Learning-based Research on Radiology Report Generati
    23770, -- 2311.15296 UHGEval: Benchmarking the Hallucination of Chinese Large Language Models via Unc
    23784, -- 2311.15562 Fully Authentic Visual Question Answering Dataset from Online Communities
    23905, -- 2311.17041 Eliciting In-Context Learning in Vision-Language Models for Videos Through Curat
    23943, -- 2311.17311 Universal Self-Consistency for Large Language Model Generation
    24040, -- 2311.18681 RaDialog: A Large Vision-Language Model for Radiology Report Generation and Conv
    24047, -- 2311.18743 AlignBench: Benchmarking Chinese Alignment of Large Language Models
    24049, -- 2311.18760 TaskBench: Benchmarking Large Language Models for Task Automation
    24165, -- 2312.01032 Harnessing the Power of Prompt-based Techniques for Generating School-Level Ques
    24234, -- 2312.02142 Object Recognition as Next Token Prediction
    24273, -- 2312.02436 MUFFIN: Curating Multi-Faceted Instructions for Improving Instruction-Following
    24365, -- 2312.03631 Mitigating Open-Vocabulary Caption Hallucinations
    24387, -- 2312.03766 Mismatch Quest: Visual and Textual Feedback for Image-Text Misalignment
    24455, -- 2312.04547 Digital Life Project: Autonomous 3D Characters with Social Intelligence
    24506, -- 2312.05180 PathFinder: Guided Search over Multi-Step Reasoning Paths
    24613, -- 2312.06648 Dense X Retrieval: What Retrieval Granularity Should We Use?
    24633, -- 2312.06722 EgoPlan-Bench: Benchmarking Multimodal Large Language Models for Human-Level Pla
    24841, -- 2312.09818 SMILE: Multimodal Dataset for Understanding Laughter in Video with Language Mode
    24849, -- 2312.10007 Faithful Persona-based Conversational Dataset Generation with Large Language Mod
    24865, -- 2312.10171 Pipeline and Dataset Generation for Automated Fact-checking in Almost Any Langua
    24880, -- 2312.10355 CoAScore: Chain-of-Aspects Prompting for NLG Evaluation
    24898, -- 2312.10700 Cross-Domain Robustness of Transformer-based Keyphrase Generation
    24950, -- 2312.11541 CLIPSyntel: CLIP and LLM Synergy for Multimodal Question Summarization in Health
    25096, -- 2312.14074 LiDAR-LLM: Exploring the Potential of Large Language Models for 3D LiDAR Underst
    25121, -- 2312.14335 Context-aware Decoding Reduces Hallucination in Query-focused Summarization
    25192, -- 2312.15713 PersianLLaMA: Towards Building First Persian Large Language Model
    25353, -- 2401.00437 BatchEval: Towards Human-like Text Evaluation
    25427, -- 2401.01596 MedSumm: A Multimodal Approach to Summarizing Code-Mixed Hindi-English Clinical
    25466, -- 2401.02038 Understanding LLMs: A Comprehensive Overview from Training to Inference
    25496, -- 2401.02417 Task Oriented Dialogue as a Catalyst for Self-Supervised Automatic Speech Recogn
    25498, -- 2401.02458 Data-Centric Foundation Models in Computational Healthcare: A Survey
    25522, -- 2401.02987 Has Your Pretrained Model Improved? A Multi-head Posterior Based Approach
    25537, -- 2401.03205 The Dawn After the Dark: An Empirical Study on Factuality Hallucination in Large
    25543, -- 2401.03374 LLM-Powered Code Vulnerability Repair with Reinforcement Learning and Semantic R
    25603, -- 2401.04348 LAMPAT: Low-Rank Adaption for Multilingual Paraphrasing Using Adversarial Traini
    25613, -- 2401.04518 The Critique of Critique
    25614, -- 2401.04522 LUNA: A Framework for Language Understanding and Naturalness Assessment
    25665, -- 2401.05399 Automated Assessment of Students' Code Comprehension using LLMs
    25693, -- 2401.05777 How Proficient Are Large Language Models in Formal Languages? An In-Depth Insigh
    25756, -- 2401.06568 Lost in the Source Language: How Large Language Models Evaluate the Quality of M
    25764, -- 2401.06688 Don't Rank, Combine! Combining Machine Translation Hypotheses Using Quality Esti
    25773, -- 2401.06775 Large language models in healthcare and medical domain: A review
    25794, -- 2401.07031 Code Security Vulnerability Repair Using Reinforcement Learning with Large Langu
    25801, -- 2401.07103 Leveraging Large Language Models for NLG Evaluation: Advances and Challenges
    25806, -- 2401.07286 CANDLE: Iterative Conceptualization and Instantiation Distillation from Large La
    25830, -- 2401.07867 Authorship Obfuscation in Multilingual Machine-Generated Text Detection
    25876, -- 2401.08559 Multi-Track Timeline Control for Text-Driven 3D Human Motion Generation
    25936, -- 2401.09248 Learning from Implicit User Feedback, Emotions and Demographic Information in Ta
    26117, -- 2401.11911 Blinded by Generated Contexts: How Language Models Merge Generated and Retrieved
    26182, -- 2401.12671 Context Matters: Pushing the Boundaries of Open-Ended Answer Generation with Gra
    26213, -- 2401.13170 CFMatch: Aligning Automated Answer Equivalence Evaluation with Expert Judgments
    26227, -- 2401.13311 ConTextual: Evaluating Context-Sensitive Text-Rich Visual Reasoning in Large Mul
    26287, -- 2401.14194 Parameter-Efficient Conversational Recommender System as a Language Processing T
    26299, -- 2401.14360 A Comparative Analysis of Noise Reduction Methods in Sentiment Analysis on Noisy
    26302, -- 2401.14367 Genie: Achieving Human Parity in Content-Grounded Datasets Generation
    26306, -- 2401.14400 Modular Adaptation of Multilingual Encoders to Written Swiss German Dialect
    26340, -- 2401.14869 F-Eval: Assessing Fundamental Abilities with Refined Evaluation Methods
    26348, -- 2401.15042 PROXYQA: An Alternative Framework for Evaluating Long-Form Text Generation with
    26349, -- 2401.15043 Health Text Simplification: An Annotated Corpus for Digestive Cancer Education a
    26358, -- 2401.15269 Improving Medical Reasoning through Retrieval and Self-Reflection with Retrieval
    26373, -- 2401.15471 ConvoSense: Overcoming Monotonous Commonsense Inferences for Conversational AI
    26374, -- 2401.15496 Baichuan2-Sum: Instruction Finetune Baichuan2-7B Model for Dialogue Summarizatio
    26379, -- 2401.15641 PRE: A Peer Review Based Large Language Model Evaluator
    26424, -- 2401.16313 Machine Translation Meta Evaluation through Translation Accuracy Challenge Sets
    26483, -- 2401.17072 SemScore: Automated Evaluation of Instruction-Tuned LLMs based on Semantic Textu
    26503, -- 2401.17390 Customizing Language Model Responses with Contrastive In-Context Learning
    26506, -- 2401.17461 Synthetic Dialogue Dataset Generation using LLM Agents
    26535, -- 2401.17919 LOCOST: State-Space Models for Long Document Abstractive Summarization
    26622, -- 2402.01053 Plan-Grounded Large Language Models for Dual Goal Conversational Settings
    26663, -- 2402.01495 A Comparative Analysis of Conversational Large Language Models in Knowledge-Base
    26669, -- 2402.01535 An Empirical Analysis of Diversity in Argument Summarization
    26680, -- 2402.01679 STICKERCONV: Generating Multimodal Empathetic Responses from Scratch
    26689, -- 2402.01717 From RAG to QA-RAG: Integrating Generative AI for Pharmaceutical Regulatory Comp
    26693, -- 2402.01735 VIALM: A Survey and Benchmark of Visually Impaired Assistance with Large Models
    26878, -- 2402.03658 Sentiment-enhanced Graph-based Sarcasm Explanation in Dialogue
    27040, -- 2402.05512 GPTs Are Multilingual Annotators for Sequence Generation Tasks
    27172, -- 2402.07270 Open-ended VQA benchmarking of Vision-Language models by exploiting Classificati
    27266, -- 2402.08638 SemRel2024: A Collection of Semantic Textual Relatedness Datasets for 13 Languag
    27273, -- 2402.08679 COLD-Attack: Jailbreaking LLMs with Stealthiness and Controllability
    27278, -- 2402.08699 Unsupervised Evaluation of Code LLMs with Round-Trip Correctness
    27291, -- 2402.08831 eCeLLM: Generalizing Large Language Models for E-commerce from Large-scale, High
    27321, -- 2402.09334 AuditLLM: A Tool for Auditing Large Language Models Using Multiprobe Approach
    27322, -- 2402.09346 LLMAuditor: A Framework for Auditing Large Language Models Using Human-in-the-Lo
    27424, -- 2402.10643 `Keep it Together': Enforcing Cohesion in Extractive Summaries by Simulating Hum
    27427, -- 2402.10669 Humans or LLMs as the Judge? A Study on Judgement Biases
    27444, -- 2402.10886 Reviewer2: Optimizing Review Generation Through Prompt Generation
    27474, -- 2402.11176 KnowTuning: Knowledge-aware Fine-tuning for Large Language Models
    27505, -- 2402.11456 FactPICO: Factuality Evaluation for Plain Language Summarization of Medical Evid
    27525, -- 2402.11638 Stumbling Blocks: Stress Testing the Robustness of Machine-Generated Text Detect
    27554, -- 2402.11882 NOTE: Notable generation Of patient Text summaries through Efficient approach ba
    27571, -- 2402.12030 Towards Cross-Tokenizer Distillation: the Universal Logit Distillation Loss for
    27623, -- 2402.12556 IMBUE: Improving Interpersonal Effectiveness through Simulation and Just-in-time
    27631, -- 2402.12659 FinBen: A Holistic Financial Benchmark for Large Language Models
    27640, -- 2402.12749 Me LLaMA: Foundation Large Language Models for Medical Applications
    27643, -- 2402.12786 Advancing Large Language Models to Capture Varied Speaking Styles and Respond Pr
    27692, -- 2402.13249 TofuEval: Evaluating Hallucinations of LLMs on Topic-Focused Dialogue Summarizat
    27726, -- 2402.13587 A Multimodal In-Context Tuning Approach for E-Commerce Product Description Gener
    27733, -- 2402.13636 A Unified Framework and Dataset for Assessing Societal Bias in Vision-Language M
    27755, -- 2402.13963 Towards Building Multilingual Language Model for Medicine
    27761, -- 2402.14016 Is LLM-as-a-Judge Robust? Investigating Universal Adversarial Attacks on Zero-sh
    27771, -- 2402.14154 MM-Soc: Benchmarking Multimodal Large Language Models in Social Media Platforms
    27802, -- 2402.14488 Does the Generator Mind its Contexts? An Analysis of Generative Model Faithfulne
    27812, -- 2402.14558 LLMs with Industrial Lens: Deciphering the Challenges and Prospects -- A Survey
    27851, -- 2402.14860 Ranking Large Language Models without Ground Truth
    27872, -- 2402.15043 KIEval: A Knowledge-grounded Interactive Evaluation Framework for Large Language
    27933, -- 2402.15861 MATHWELL: Generating Educational Math Word Problems Using Teacher Annotations
    27986, -- 2402.16694 HumanEval-XL: A Multilingual Code Generation Benchmark for Cross-lingual Natural
    27996, -- 2402.16822 Rainbow Teaming: Open-Ended Generation of Diverse Adversarial Prompts
    28069, -- 2402.17553 OmniACT: A Dataset and Benchmark for Enabling Multimodal Generalist Autonomous A
    28074, -- 2402.17645 SongComposer: A Large Language Model for Lyric and Melody Generation in Song Com
    28084, -- 2402.17753 Evaluating Very Long-Term Conversational Memory of LLM Agents
    28117, -- 2402.18060 Benchmarking Large Language Models on Answering and Explaining Challenging Medic
    28119, -- 2402.18091 Polos: Multimodal Metric Learning from Human Feedback for Image Captioning
    28156, -- 2402.18540 Keeping LLMs Aligned After Fine-tuning: The Crucial Role of Prompt Templates
    28216, -- 2402.19479 Panda-70M: Captioning 70M Videos with Multiple Cross-Modality Teachers
    28231, -- 2403.00231 Multimodal ArXiv: A Dataset for Improving Scientific Comprehension of Large Visi
    28288, -- 2403.01061 Reading Subtext: Evaluating Large Language Models on Short Story Summarization w
    28312, -- 2403.01306 ICC: Quantifying Image Caption Concreteness for Multimodal Dataset Curation
    28376, -- 2403.02270 FENICE: Factuality Evaluation of summarization based on Natural language Inferen
    28377, -- 2403.02271 RIFF: Learning to Rephrase Inputs for Few-shot Fine-tuning of Language Models
    28424, -- 2403.02990 Data Augmentation using Large Language Models: Data Perspectives, Learning Parad
    28451, -- 2403.03307 Book2Dial: Generating Teacher-Student Interactions from Textbooks for Cost-Effec
    28463, -- 2403.03521 BiVert: Bidirectional Vocabulary Evaluation using Relations for Machine Translat
    28482, -- 2403.03888 FaaF: Facts as a Function for the evaluation of generated text
    28505, -- 2403.04314 Can Your Model Tell a Negation from an Implicature? Unravelling Challenges With
    28553, -- 2403.04945 MEIT: Multi-Modal Electrocardiogram Instruction Tuning on Large Language Models
    28579, -- 2403.05303 ACLSum: A New Dataset for Aspect-based Summarization of Scientific Publications
    28603, -- 2403.05720 A Dataset and Benchmark for Hospital Course Summarization with Adapted Large Lan
    28613, -- 2403.05881 KG-Rank: Enhancing Large Language Models for Medical QA with Knowledge Graphs an
    28637, -- 2403.06326 From Instructions to Constraints: Language Model Alignment with Automatic Constr
    28659, -- 2403.06728 Large Model driven Radiology Report Generation with Clinical Quality Reinforceme
    28713, -- 2403.07384 SmallToLarge (S2L): Scalable Data Selection for Fine-tuning Large Language Model
    28740, -- 2403.07794 Fine-tuning Large Language Models with Sequential Instructions
    28885, -- 2403.09713 A Hybrid Intelligence Method for Argument Mining
    28909, -- 2403.10153 Improving Medical Multi-modal Contrastive Learning with Expert Annotations
    28940, -- 2403.10575 Exploring Language Model's Code Generation Ability with Auxiliary Functions
    29039, -- 2403.11821 A Survey on Quality Metrics for Text-to-Image Generation
    29066, -- 2403.12027 From Pixels to Insights: A Survey on Automatic Chart Understanding in the Era of
    29086, -- 2403.12339 Entity6K: A Large Open-Domain Evaluation Dataset for Real-World Entity Recogniti
    29157, -- 2403.13169 Wav2Gloss: Generating Interlinear Glossed Text from Speech
    29236, -- 2403.14168 M$^3$AV: A Multimodal, Multigenre, and Multipurpose Audio-Visual Academic Lectur
    29239, -- 2403.14221 Improving the Robustness of Large Language Models via Consistency Alignment
    29256, -- 2403.14459 Multi-Level Explanations for Generative Language Models
    29334, -- 2403.15362 CoLLEGe: Concept Embedding Generation for Large Language Models
    29383, -- 2403.16008 CBT-LLM: A Chinese Large Language Model for Cognitive Behavioral Therapy-based M
    29434, -- 2403.16950 Aligning with Human Judgement: The Role of Pairwise Preference in Large Language
    29437, -- 2403.16971 AIOS: LLM Agent Operating System
    29472, -- 2403.17661 Language Models for Text Classification: Is In-Context Learning Enough?
    29481, -- 2403.17768 SciNews: From Scholarly Complexities to Public Narratives -- A Dataset for Scien
    29561, -- 2403.18771 CheckEval: Robust Evaluation Framework using Large Language Model via Checklist
    29575, -- 2403.18938 Reshaping Free-Text Radiology Notes Into Structured Reports With Generative Tran
    29624, -- 2403.19603 Semantic Map-based Generation of Navigation Instructions
    29646, -- 2403.19889 Towards a Robust Retrieval-Based Summarization System
    29693, -- 2404.00376 Small Language Models Learn Enhanced Reasoning Skills from Medical Textbooks
    29715, -- 2404.00578 M3D: Advancing 3D Medical Image Analysis with Multi-Modal Large Language Models
    29726, -- 2404.00656 WavLLM: Towards Robust and Adaptive Speech Large Language Model
    29752, -- 2404.00929 A Survey on Multilingual Large Language Models: Corpora, Alignment, and Bias
    29769, -- 2404.01129 Emphasising Structured Information: Integrating Abstract Meaning Representation
    29875, -- 2404.02512 Towards Large Language Model driven Reference-less Translation Evaluation for En
    29882, -- 2404.02657 Rethinking Kullback-Leibler Divergence in Knowledge Distillation for Large Langu
    29905, -- 2404.02904 ALOHa: A New Measure for Hallucination in Captioning Models
    29911, -- 2404.03022 BCAmirs at SemEval-2024 Task 4: Beyond Words: A Multimodal and Multilingual Expl
    29943, -- 2404.03555 From News to Summaries: Building a Hungarian Corpus for Extractive and Abstracti
    29945, -- 2404.03561 Select and Summarize: Scene Saliency for Movie Script Summarization
    29967, -- 2404.03673 RL for Consistency Models: Faster Reward Guided Text-to-Image Generation
    30016, -- 2404.04475 Length-Controlled AlpacaEval: A Simple Way to Debias Automatic Evaluators
    30045, -- 2404.04925 Multilingual Large Language Model: A Survey of Resources, Taxonomy and Frontiers
    30116, -- 2404.06003 FreeEval: A Modular Framework for Trustworthy and Efficient Evaluation of Large
    30211, -- 2404.07470 Scalable Language Model with Generalized Continual Learning
    30240, -- 2404.07917 DesignQA: A Multimodal Benchmark for Evaluating Large Language Models' Understan
    30259, -- 2404.08008 Sample-Efficient Human Evaluation of Large Language Models via Maximum Discrepan
    30271, -- 2404.08262 Pretraining and Updates of Domain-Specific LLM: A Case Study in the Japanese Bus
    30325, -- 2404.09002 WikiSplit++: Easy Data Refinement for Split and Rephrase
    30369, -- 2404.09682 Multi-News+: Cost-efficient Dataset Cleansing via LLM-based Data Annotation
    30409, -- 2404.10306 Balancing Speciality and Versatility: a Coarse to Fine Framework for Supervised
    30417, -- 2404.10513 CoTAR: Chain-of-Thought Attribution Reasoning with Multi-level Granularity
    30430, -- 2404.10719 Is DPO Superior to PPO for LLM Alignment? A Comprehensive Study
    30432, -- 2404.10763 LaDiC: Are Diffusion Models Really Inferior to Autoregressive Counterparts for I
    30505, -- 2404.12045 RAM: Towards an Ever-Improving Memory System by Learning from Communications
    30533, -- 2404.12353 V2Xum-LLM: Cross-Modal Video Summarization with Temporal Prompt Instruction Tuni
    30535, -- 2404.12365 When LLMs are Unfit Use FastFit: Fast and Effective Text Classification with Man
    30637, -- 2404.13968 Protecting Your LLMs with Information Bottleneck
    30644, -- 2404.14215 Text-Tuple-Table: Towards Information Integration in Text-to-Table Generation vi
    30663, -- 2404.14412 AutoAD III: The Prequel -- Back to the Pixels
    30687, -- 2404.14851 From Matching to Generation: A Survey on Generative Information Retrieval
    30712, -- 2404.15269 Aligning LLM Agents by Learning Latent Preference from User Edits
    30716, -- 2404.15420 XC-Cache: Cross-Attending to Cached Context for Efficient LLM Inference
    30739, -- 2404.15909 Learning Long-form Video Prior via Generative Pre-Training
    30848, -- 2404.17778 MRScore: Evaluating Radiology Report Generation with LLM-based Reward System
    30852, -- 2404.17833 Testing and Understanding Erroneous Planning in LLM Agents through Synthesized U
    30903, -- 2404.18930 Hallucination of Multimodal Large Language Models: A Survey
    30913, -- 2404.19175 Game-MUG: Multimodal Oriented Game Situation Understanding and Commentary Genera
    30952, -- 2405.00200 In-Context Learning with Long-Context Models: An In-Depth Exploration
    30982, -- 2405.00657 RST-LoRA: A Discourse-Aware Low-Rank Adaptation for Long Document Abstractive Su
    31016, -- 2405.01474 Understanding Figurative Meaning through Explainable Visual Entailment
    31022, -- 2405.01535 Prometheus 2: An Open Source Language Model Specialized in Evaluating Other Lang
    31033, -- 2405.01790 Understanding Position Bias Effects on Fairness in Social Multi-Document Summari
    31065, -- 2405.02793 ImageInWords: Unlocking Hyper-Detailed Image Descriptions
    31070, -- 2405.02861 Revisiting a Pain in the Neck: Semantic Phrase Processing Benchmark for Language
    31093, -- 2405.03595 GREEN: Generative Radiology Report Evaluation and Error Notation
    31113, -- 2405.04286 Who Wrote This? The Key to Zero-Shot LLM-Generated Text Detection Is GECScore
    31186, -- 2405.06258 Automatic Generation of Model and Data Cards: A Step Towards Responsible AI
    31224, -- 2405.07348 MedConceptsQA: Open Source Medical Concepts QA Benchmark
    31225, -- 2405.07354 SoccerNet-Echoes: A Soccer Game Audio Commentary Dataset
    31228, -- 2405.07437 Evaluation of Retrieval-Augmented Generation: A Survey
    31267, -- 2405.08029 PHUDGE: Phi-3 as Scalable Judge
    31286, -- 2405.08477 Enhancing Gender-Inclusive Machine Translation with Neomorphemes and Large Langu
    31299, -- 2405.08813 CinePile: A Long Video Question Answering Dataset and Benchmark
    31346, -- 2405.10004 ROCOv2: Radiology Objects in COntext Version 2, an Updated Multimodal Image Data
    31357, -- 2405.10243 DocuMint: Docstring Generation for Python using Small Language Models
    31377, -- 2405.10542 Benchmarking Large Language Models on CFLUE -- A Chinese Financial Language Unde
    31468, -- 2405.12701 OLAPH: Improving Factuality in Biomedical Long-form Question Answering
    31657, -- 2405.15110 CHARP: Conversation History AwaReness Probing for Knowledge-grounded Dialogue Sy
    31699, -- 2405.15604 Text Generation: A Systematic Literature Review of Tasks, Evaluation, and Challe
    31722, -- 2405.15766 Enhancing Adverse Drug Event Detection with Multimodal Dataset: Corpus Creation
    31733, -- 2405.15924 SLIDE: A Framework Integrating Small and Large Language Models for Open-Domain D
    31764, -- 2405.16433 CPsyCoun: A Report-based Multi-turn Dialogue Reconstruction and Evaluation Frame
    31779, -- 2405.16579 Automatically Generating Numerous Context-Driven SFT Data for LLMs across Divers
    31987, -- 2405.19088 Cracking the Code of Juxtaposition: Can AI Models Understand the Humorous Contra
    32089, -- 2405.20315 ANAH: Analytical Annotation of Hallucinations in Large Language Models
    32119, -- 2405.20708 FinGen: A Dataset for Argument Generation in Finance
    32131, -- 2405.20947 OR-Bench: An Over-Refusal Benchmark for Large Language Models
    32218, -- 2406.01171 Two Tales of Persona in LLMs: A Survey of Role-Playing and Personalization
    32355, -- 2406.03008 DriVLMe: Enhancing LLM-based Autonomous Driving Agents with Embodied and Social
    32373, -- 2406.03363 LLM-based Rewriting of Inappropriate Argumentation using Reinforcement Learning
    32382, -- 2406.03486 BIPED: Pedagogically Informed Tutoring System for ESL Education
    32409, -- 2406.03893 How Good is Zero-Shot MT Evaluation for Low Resource Indian Languages?
    32485, -- 2406.04568 StackSight: Unveiling WebAssembly through Large Language Models and Neurosymboli
    32491, -- 2406.04625 Key-Element-Informed sLLM Tuning for Document Summarization
    32536, -- 2406.05344 MemeGuard: An LLM and VLM-based Framework for Advancing Content Moderation via M
    32545, -- 2406.05491 One Perturbation is Enough: On Generating Universal Adversarial Perturbations ag
    32565, -- 2406.05707 QGEval: Benchmarking Multi-dimensional Evaluation for Question Generation
    32570, -- 2406.05761 The BiGGen Bench: A Principled Benchmark for Fine-grained Evaluation of Language
    32618, -- 2406.06331 MedExQA: Medical Question Answering Benchmark with Multiple Explanations
    32619, -- 2406.06357 MASSW: A New Dataset and Benchmark Tasks for AI-Assisted Scientific Workflows
    32638, -- 2406.06512 Merlin: A Vision Language Foundation Model for 3D Computed Tomography
    32682, -- 2406.07070 HalluDial: A Large-Scale Benchmark for Automatic Dialogue-Level Hallucination Ev
    32718, -- 2406.07457 Estimating the Hallucination Rate of Generative AI
    32753, -- 2406.07815 Are Large Language Models Good Statisticians?
    32768, -- 2406.07933 Large Language Model Unlearning via Embedding-Corrupted Prompts
    32770, -- 2406.07969 LibriTTS-P: A Corpus with Speaking Style and Speaker Identity Prompts for Text-t
    32777, -- 2406.08074 A Concept-Based Explainability Framework for Large Multimodal Models
    32942, -- 2406.09905 Nymeria: A Massive Collection of Multimodal Egocentric Daily Motion in the Wild
    32966, -- 2406.10209 Be like a Goldfish, Don't Memorize! Mitigating Memorization in Generative LLMs
    32991, -- 2406.10421 SciEx: Benchmarking Large Language Models on Scientific Exams with Human Expert
    33021, -- 2406.10802 KGPA: Robustness Evaluation for Large Language Models via Cross-Domain Knowledge
    33026, -- 2406.10834 Exposing the Achilles' Heel: Evaluating LLMs Ability to Handle Mistakes in Mathe
    33044, -- 2406.10996 Towards Lifelong Dialogue Agents via Timeline-based Memory Management
    33076, -- 2406.11217 WeatherQA: Can Multimodal Language Models Reason about Severe Weather?
    33078, -- 2406.11228 ComperDial: Commonsense Persona-grounded Dialogue Dataset and Benchmark
    33092, -- 2406.11289 A Systematic Survey of Text Summarization: From Statistical Methods to Large Lan
    33097, -- 2406.11370 Fairer Preferences Elicit Improved Human-Aligned Large Language Model Judgments
    33099, -- 2406.11402 Are Small Language Models Ready to Compete with Large Language Models for Practi
    33107, -- 2406.11451 CoMT: Chain-of-Medical-Thought Reduces Hallucination in Medical Report Generatio
    33116, -- 2406.11565 Extrinsic Evaluation of Cultural Competence in Large Language Models
    33253, -- 2406.12549 MultiSocial: Multilingual Benchmark of Machine-Generated Text Detection of Socia
    33269, -- 2406.12707 Talk With Human-like Agents: Empathetic Dialogue Through Perceptible Acoustic Re
    33270, -- 2406.12708 AgentReview: Exploring Peer Review Dynamics with LLM Agents
    33319, -- 2406.13340 SD-Eval: A Benchmark Dataset for Spoken Dialogue Understanding Beyond Words
    33418, -- 2406.14553 xCOMET-lite: Bridging the Gap Between Efficiency and Quality in Learned MT Evalu
    33434, -- 2406.14703 Do LLMs Have Distinct and Consistent Personality? TRAIT: Personality Testset des
    33521, -- 2406.15796 Unveiling Entity-Level Unlearning for Large Language Models: A Comprehensive Ana
    33550, -- 2406.16253 LLMs Assist NLP Researchers: Critique Paper (Meta-)Reviewing
    33572, -- 2406.16377 On the Transformations across Reward Model, Parameter Update, and In-Context Pro
    33608, -- 2406.16845 RaTEScore: A Metric for Radiology Report Generation
    33609, -- 2406.16851 Losing Visual Needles in Image Haystacks: Vision Language Models are Easily Dist
    33659, -- 2406.17535 Disce aut Deficere: Evaluating LLMs Proficiency on the INVALSI Italian Benchmark
    33685, -- 2406.17761 CaLMQA: Exploring culturally specific long-form question answering across 23 lan
    33697, -- 2406.17967 Unmasking the Imposters: How Censorship and Domain Adaptation Affect the Detecti
    33714, -- 2406.18120 ArzEn-LLM: Code-Switched Egyptian Arabic-English Translation and Speech Recognit
    33736, -- 2406.18365 Themis: A Reference-free NLG Evaluation Language Model with Flexibility and Inte
    33821, -- 2406.19465 Can Large Language Models Generate High-quality Patent Claims?
    33878, -- 2407.00121 Granite-Function Calling Model: Introducing Function Calling Abilities via Multi
    33898, -- 2407.00453 PerSEval: Assessing Personalization in Text Summarizers
    33923, -- 2407.00902 From Introspection to Best Practices: Principled Analysis of Demonstrations in M
    33961, -- 2407.01384 Free-text Rationale Generation under Readability Level Control
    34013, -- 2407.02005 An End-to-End Speech Summarization Using Large Language Model
    34019, -- 2407.02056 Integrate the Essence and Eliminate the Dross: Fine-Grained Self-Consistency for
    34034, -- 2407.02233 Synthetic Multimodal Question Generation
    34041, -- 2407.02328 Efficient Sparse Attention needs Adaptive Token Release
    34070, -- 2407.02736 MentalAgora: A Gateway to Advanced Personalized Care in Mental Health through Mu
    34083, -- 2407.02994 MedPix 2.0: A Comprehensive Multimodal Biomedical Data set for Advanced AI Appli
    34085, -- 2407.03000 VIVA: A Benchmark for Vision-Grounded Decision-Making with Human Values
    34122, -- 2407.03418 HEMM: Holistic Evaluation of Multimodal Foundation Models
    34144, -- 2407.03791 M5 -- A Diverse Benchmark to Assess the Performance of Large Multimodal Models A
    34148, -- 2407.03861 TartuNLP @ AXOLOTL-24: Leveraging Classifier Output for New Sense Detection in L
    34168, -- 2407.04069 A Systematic Survey and Critical Review on Evaluating Large Language Models: Cha
    34206, -- 2407.04559 Not (yet) the whole story: Evaluating Visual Storytelling Requires More than Mea
    34217, -- 2407.04693 ANAH-v2: Scaling Analytical Hallucination Annotation of Large Language Models
    34229, -- 2407.04903 MMSci: A Dataset for Graduate-Level Multi-Discipline Multimodal Scientific Under
    34245, -- 2407.05183 FlowLearn: Evaluating Large Vision-Language Models on Flowchart Understanding
    34268, -- 2407.05502 Faux Polyglot: A Study on Information Disparity in Multilingual Large Language M
    34290, -- 2407.05721 PsycoLLM: Enhancing LLM for Psychological Understanding and Evaluation
    34301, -- 2407.05925 Towards Optimizing and Evaluating a Retrieval Augmented QA Chatbot using LLMs wi
    34315, -- 2407.06089 Merge, Ensemble, and Cooperate! A Survey on Collaborative Strategies in the Era
    34327, -- 2407.06172 On Speeding Up Language Model Evaluation
    34348, -- 2407.06423 InsightBench: Evaluating Business Analytics Agents Through Multi-Step Insight Ge
    34388, -- 2407.07071 Lookback Lens: Detecting and Mitigating Contextual Hallucinations in Large Langu
    34410, -- 2407.07341 A Guide To Effectively Leveraging LLMs for Low-Resource Text Summarization: Data
    34481, -- 2407.08410 Specialist vision-language models for clinical ophthalmology
    34549, -- 2407.09136 Stepwise Verification and Remediation of Student Reasoning Errors with Large Lan
    34566, -- 2407.09413 SPIQA: A Dataset for Multimodal Question Answering on Scientific Papers
    34569, -- 2407.09435 MUSCLE: A Model Update Strategy for Compatible LLM Evolution
    34594, -- 2407.09823 NativQA: Multilingual Culturally-Aligned Natural Query for LLMs
    34663, -- 2407.10793 GraphEval: A Knowledge-Graph Based LLM Hallucination Evaluation Framework
    34666, -- 2407.10817 Foundational Autoraters: Taming Large Language Models for Better Automatic Evalu
    34692, -- 2407.10994 Panza: Design and Analysis of a Fully-Local Personalized Text Writing Assistant
    34743, -- 2407.11591 AdaptEval: Evaluating Large Language Models on Domain Adaptation for Text Summar
    34771, -- 2407.11930 Localizing and Mitigating Errors in Long-form Question Answering
    34787, -- 2407.12126 LLMs-in-the-loop Part-1: Expert Small AI Models for Bio-Medical Text Translation
    34846, -- 2407.12818 "I understand why I got this grade": Automatic Short Answer Grading with Feedbac
    34847, -- 2407.12821 AutoFlow: Automated Workflow Generation for Large Language Model Agents
    34853, -- 2407.12857 Automated Peer Reviewing in Paper SEA: Standardization, Evaluation, and Analysis
    34859, -- 2407.12873 Evaluation of RAG Metrics for Question Answering in the Telecom Domain
    34913, -- 2407.13561 Research on Tibetan Tourism Viewpoints information generation system based on LL
    35032, -- 2407.15366 Walking in Others' Shoes: How Perspective-Taking Guides Large Language Models in
    35059, -- 2407.15694 Counter Turing Test ($CT^2$): Investigating AI-Generated Text Detection for Hind
    35082, -- 2407.16073 KaPQA: Knowledge-Augmented Product Question-Answering
    35092, -- 2407.16216 A Comprehensive Survey of LLM Alignment Techniques: RLHF, RLAIF, PPO, DPO and Mo
    35109, -- 2407.16434 Enhancing LLM's Cognition via Structurization
    35128, -- 2407.16724 Structure-aware Domain Knowledge Injection for Large Language Models
    35143, -- 2407.17022 Can Language Models Evaluate Human Written Text? Case Study on Korean Student Wr
    35192, -- 2407.17940 Positive Text Reframing under Multi-strategy Optimization
    35247, -- 2407.18908 Wolf: Captioning Everything with a World Summarization Framework
    35268, -- 2407.19474 Visual Riddles: a Commonsense and World Knowledge Challenge for Large Vision and
    35287, -- 2407.19795 VolDoGer: LLM-assisted Datasets for Domain Generalization in Vision-Language Tas
    35318, -- 2407.20341 BRIDGE: Bridging Gaps in Image Captioning Evaluation with Stronger Visual Cues
    35346, -- 2407.20962 MMTrail: A Multimodal Trailer Video Dataset with Language and Music Descriptions
    35354, -- 2407.21054 Sentiment Reasoning for Healthcare
    35388, -- 2407.21757 Learning Video Context as Interleaved Multimodal Sequences
    35415, -- 2408.00205 Sentence-wise Speech Summarization: Task, Datasets, and End-to-End Modeling with
    35500, -- 2408.01453 Reporting and Analysing the Environmental Impact of Language Models on the Examp
    35513, -- 2408.01723 A Novel Evaluation Framework for Image2Text Generation
    35524, -- 2408.02056 MedSyn: LLM-based Synthetic Medical Text Generation Framework
    35526, -- 2408.02085 Unleashing the Power of Data Tsunami: A Comprehensive Survey on Data Assessment
    35557, -- 2408.02545 RAG Foundry: A Framework for Enhancing LLMs for Retrieval Augmented Generation
    35559, -- 2408.02584 Leveraging the Power of LLMs: A Fine-Tuning Approach for High-Quality Aspect-Bas
    35630, -- 2408.03762 'Finance Wizard' at the FinLLM Challenge Task: Financial Text Summarization
    35645, -- 2408.04114 Zero-shot Factual Consistency Evaluation Across Domains
    35653, -- 2408.04220 Diffusion Guided Language Modeling
    35736, -- 2408.05906 AdTEC: A Unified Benchmark for Evaluating Text Quality in Search Engine Advertis
    35758, -- 2408.06281 MovieSum: An Abstractive Summarization Dataset for Movie Screenplays
    35773, -- 2408.06518 Does Liking Yellow Imply Driving a School Bus? Semantic Leakage in Language Mode
    35824, -- 2408.07277 Speech vs. Transcript: Does It Matter for Human Annotators in Speech Summarizati
    35859, -- 2408.08067 RAGChecker: A Fine-grained Framework for Diagnosing Retrieval-Augmented Generati
    35880, -- 2408.08396 Level Up Your Tutorials: VLMs for Game Tutorials Quality Assessment
    35889, -- 2408.08506 Ex3: Automatic Novel Writing by Extracting, Excelsior and Expanding
    35930, -- 2408.09169 Automatic Metrics in Natural Language Generation: A Survey of Current Evaluation
    35933, -- 2408.09235 Reference-Guided Verdict: LLMs-as-Judges in Automatic Evaluation of Free-Form Te
    35937, -- 2408.09330 Fostering Natural Conversation in Large Language Models with NICO: a Natural Int
    36007, -- 2408.10652 Vocabulary-Free 3D Instance Segmentation with Vision and Language Assistant
    36048, -- 2408.11081 What can Large Language Models Capture about Code Functional Equivalence?
    36073, -- 2408.11363 ProteinGPT: Multimodal LLM for Protein Property Prediction and Structure Underst
    36104, -- 2408.11849 Style-Talker: Finetuning Audio Language Model and Style-Based Text-to-Speech Mod
    36112, -- 2408.11965 CT-AGRG: Automated Abnormality-Guided Report Generation from 3D Chest CT Volumes
    36117, -- 2408.12095 uMedSum: A Unified Framework for Advancing Medical Abstractive Summarization
    36133, -- 2408.12325 Improving Factuality in Large Language Models via Decoding-Time Hallucinatory an
    36254, -- 2408.14622 What Makes a Good Story and How Can We Measure It? A Comprehensive Survey of Sto
    36347, -- 2408.16098 Structured Event Reasoning with Large Language Models
    36359, -- 2408.16264 LoraMap: Harnessing the Power of LoRA Connections
    36389, -- 2408.16756 How Well Do LLMs Handle Cantonese? Benchmarking Cantonese Capabilities of Large
    36477, -- 2409.00919 MMT-BERT: Chord-aware Symbolic Music Generation Based on Multitrack Music Transf
    36504, -- 2409.01369 Imitating Language via Scalable Inverse Reinforcement Learning
    36516, -- 2409.01584 Towards Cross-Lingual Explanation of Artwork in Large-scale Vision Language Mode
    36547, -- 2409.02098 CRAFT Your Dataset: Task-Specific Synthetic Dataset Generation Through Corpus Re
    36553, -- 2409.02228 Unforgettable Generalization in Language Models
    36667, -- 2409.04787 Selective Self-Rehearsal: A Fine-Tuning Approach to Improve Generalization in La
    36686, -- 2409.05314 Tele-LLMs: A Series of Specialized Large Language Models for Telecommunications
    36698, -- 2409.05677 RIRAG: Regulatory Information Retrieval and Answer Generation
    36700, -- 2409.05732 Towards Democratizing Multilingual Large Language Models For Medicine Through A
    36720, -- 2409.06185 Can Large Language Models Unlock Novel Scientific Research Ideas?
    36755, -- 2409.06857 What is the Role of Small Models in the LLM Era: A Survey
    36764, -- 2409.07088 Ontology-Free General-Domain Knowledge Graph-to-Text Generation Dataset Synthesi
    36776, -- 2409.07394 AdaCAD: Adaptively Decoding to Balance Conflicts between Contextual and Parametr
    36778, -- 2409.07431 Synthetic continued pretraining
    36811, -- 2409.08202 What Makes a Maze Look Like a Maze?
    36847, -- 2409.08788 Electrocardiogram Report Generation and Question Answering via Retrieval-Augment
    36876, -- 2409.09269 Guiding Vision-Language Model Selection for Visual Question-Answering Across Tas
    36910, -- 2409.09844 A Benchmark Dataset with Larger Context for Non-Factoid Question Answering over
    37099, -- 2409.12962 CLAIR-A: Leveraging Large Language Models to Judge Audio Captions
    37104, -- 2409.13093 Guided Profile Generation Improves Personalization with LLMs
    37108, -- 2409.13191 Diabetica: Adapting Large Language Model to Enhance Multiple Medical Tasks in Di
    37117, -- 2409.13321 SLaVA-CXR: Small Language and Vision Assistant for Chest X-ray Report Automation
    37129, -- 2409.13592 YesBut: A High-Quality Annotated Multimodal Dataset for evaluating Satire Compre
    37167, -- 2409.14083 SURf: Teaching Large Vision-Language Models to Selectively Utilize Retrieved Inf
    37171, -- 2409.14192 Knowledge in Triples for LLMs: Enhancing Table QA Accuracy with Semantic Extract
    37238, -- 2409.15380 Kalahi: A handcrafted, grassroots cultural LLM evaluation suite for Filipino
    37246, -- 2409.15515 Learning When to Retrieve, What to Rewrite, and How to Respond in Conversational
    37379, -- 2409.17892 EMMA-500: Enhancing Massively Multilingual Adaptation of Large Language Models
    37380, -- 2409.17912 Atlas-Chat: Adapting Large Language Models for Low-Resource Moroccan Arabic Dial
    37385, -- 2409.18003 Enhancing Tourism Recommender Systems for Sustainable City Trips Using Retrieval
    37418, -- 2409.18446 Exploring Language Model Generalization in Low-Resource Extractive QA
    37432, -- 2409.18786 A Survey on the Honesty of Large Language Models
    37450, -- 2409.19020 DiaSynth: Synthetic Dialogue Generation Framework for Low Resource Dialogue Appl
    37457, -- 2409.19149 Multimodal Pragmatic Jailbreak on Text-to-image Models
    37462, -- 2409.19255 DENEB: A Hallucination-Robust Automatic Evaluation Metric for Image Captioning
    37532, -- 2409.20075 BSharedRAG: Backbone Shared Retrieval-Augmented Generation for the E-commerce Do
    37569, -- 2410.00201 DreamStruct: Understanding Slides and User Interfaces via Synthetic Data Generat
    37598, -- 2410.00683 Efficient Technical Term Translation: A Knowledge Distillation Approach for Pare
    37613, -- 2410.01023 Can visual language models resolve textual ambiguity with visual cues? Let visua
    37625, -- 2410.01162 Frozen Large Language Models Can Perceive Paralinguistic Aspects of Speech
    37730, -- 2410.02184 CodeJudge: Evaluating Code Generation with Large Language Models
    37755, -- 2410.02381 MetaMetrics: Calibrating Metrics For Generation Tasks Using Human Preferences
    37823, -- 2410.02902 Better Instruction-Following Through Minimum Bayes Risk
    37834, -- 2410.03051 AuroraCap: Efficient, Performant Video Detailed Captioning and a New Benchmark
    37861, -- 2410.03264 Enriching Music Descriptions with a Finetuned-LLM and Metadata for Text-to-Music
    37879, -- 2410.03537 Ward: Provable RAG Dataset Inference via LLM Watermarks
    37880, -- 2410.03553 Structure-Enhanced Protein Instruction Tuning: Towards General-Purpose Protein U
    37927, -- 2410.04064 Text2Chart31: Instruction Tuning for Chart Generation with Automatic Feedback
    37932, -- 2410.04087 GlobeSumm: A Challenging Benchmark Towards Unifying Multi-lingual, Cross-lingual
    37996, -- 2410.05102 SparsePO: Controlling Preference Alignment of LLMs via Sparse Token Masks
    37997, -- 2410.05160 VLM2Vec: Training Vision-Language Models for Massive Multimodal Embedding Tasks
    38121, -- 2410.06458 LLM Self-Correction with DeCRIM: Decompose, Critique, and Refine for Enhanced Fo
    38163, -- 2410.07009 Pap2Pat: Towards Automated Paper-to-Patent Drafting using Chunk-based Outline-gu
    38164, -- 2410.07025 Preference Fine-Tuning for Factuality in Chest X-Ray Interpretation Models Witho
    38174, -- 2410.07093 LaMP: Language-Motion Pretraining for Motion Generation, Retrieval, and Captioni
    38213, -- 2410.07507 Thought2Text: Text Generation from EEG Signal using Large Language Models (LLMs)
    38373, -- 2410.09644 Adapters for Altering LLM Vocabularies: What Languages Benefit the Most?
    38412, -- 2410.10139 MMIE: Massive Multimodal Interleaved Comprehension Benchmark for Large Vision-La
    38432, -- 2410.10450 KBLaM: Knowledge Base augmented Language Model
    38478, -- 2410.10848 Crafting Narrative Closures: Zero-Shot Learning with SSM Mamba for Short Story E
    38482, -- 2410.10866 CodeUnlearn: Amortized Zero-Shot Machine Unlearning in Language Models Using Dis
    38579, -- 2410.12046 Towards Realistic Evaluation of Commit Message Generation by Matching Online and
    38589, -- 2410.12222 On A Scale From 1 to 5: Quantifying Hallucination in Faithfulness Evaluation
    38605, -- 2410.12405 ProSA: Assessing and Understanding the Prompt Sensitivity of LLMs
    38623, -- 2410.12705 WorldCuisines: A Massive-Scale Benchmark for Multilingual and Multicultural Visu
    38662, -- 2410.13037 LFOSum: Summarizing Long-form Opinions with Large Language Models
    38665, -- 2410.13070 Is Semantic Chunking Worth the Computational Cost?
    38668, -- 2410.13098 A Little Human Data Goes A Long Way
    38669, -- 2410.13116 Learning to Summarize from LLM-generated Feedback
    38688, -- 2410.13248 Disentangling Likes and Dislikes in Personalized Generative Explainable Recommen
    38693, -- 2410.13287 An Online Learning Approach to Prompt-based Selection of Generative Models
    38707, -- 2410.13456 Unlocking Legal Knowledge: A Multilingual Dataset for Judicial Summarization in
    38805, -- 2410.14464 Electrocardiogram-Language Model for Few-Shot Question Answering with Meta Learn
    38853, -- 2410.15037 mHumanEval -- A Multilingual Benchmark to Evaluate Large Language Models for Cod
    38864, -- 2410.15226 On the Diversity of Synthetic Data and its Impact on Training Large Language Mod
    38880, -- 2410.15490 Dynamic Intelligence Assessment: Benchmarking LLMs on the Road to AGI with a Foc
    38884, -- 2410.15553 Multi-IF: Benchmarking LLMs on Multi-Turn and Multilingual Instructions Followin
    38908, -- 2410.15956 Do Large Language Models Have an English Accent? Evaluating and Improving the Na
    38925, -- 2410.16148 PODTILE: Facilitating Podcast Episode Browsing with Auto-generated Chapters
    38979, -- 2410.16701 ClimaQA: An Automated Evaluation Framework for Climate Foundation Models
    39045, -- 2410.17728 Dialectal and Low-Resource Machine Translation for Aromanian
    39046, -- 2410.17736 MojoBench: Language Modeling and Benchmarks for Mojo
    39076, -- 2410.18160 Future Token Prediction -- Causal Language Modelling with Per-Token Semantic Sta
    39100, -- 2410.18460 Beyond Multiple-Choice Accuracy: Real-World Challenges of Implementing Large Lan
    39117, -- 2410.18603 AgentStore: Scalable Integration of Heterogeneous Agents As Specialized Generali
    39135, -- 2410.18856 Demystifying Large Language Models for Medicine: A Primer
    39137, -- 2410.18860 DeCoRe: Decoding by Contrasting Retrieval Heads to Mitigate Hallucinations
    39146, -- 2410.18963 OSCAR: Operating System Control via State-Aware Reasoning and Re-Planning
    39162, -- 2410.19133 Hybrid Preferences: Learning to Route Instances for Human vs. AI Feedback
    39204, -- 2410.19884 A Survey of AI-Generated Video Evaluation
    39239, -- 2410.20482 What Factors Affect Multi-Modal In-Context Learning? An In-Depth Exploration
    39249, -- 2410.20682 SHARE: Shared Memory-Aware Open-Domain Long-Term Dialogue Dataset Constructed fr
    39251, -- 2410.20745 Shopping MMLU: A Massive Multi-Task Online Shopping Benchmark for Large Language
    39320, -- 2410.21747 MotionGPT-2: A General-Purpose Motion-Language Model for Motion Generation and U
    39350, -- 2410.22360 ArxivDIGESTables: Synthesizing Scientific Literature into Tables using Language
    39355, -- 2410.22394 AAAR-1.0: Assessing AI's Potential to Assist Research
    39356, -- 2410.22446 Do Large Language Models Align with Core Mental Health Counseling Competencies?
    39381, -- 2410.22932 Multi-Agent Large Language Models for Conversational Task-Solving
    39397, -- 2410.23180 ReasoningRec: Bridging Personalized Recommendations and Human-Interpretable Expl
    39431, -- 2410.23746 DetectRL: Benchmarking LLM-Generated Text Detection in Real-World Scenarios
    39473, -- 2411.00027 Personalization of Large Language Models: A Survey
    39611, -- 2411.02355 "Give Me BF16 or Give Me Death"? Accuracy-Performance Trade-Offs in LLM Quantiza
    39695, -- 2411.04032 Beemo: Benchmark of Expert-edited Machine-generated Outputs
    39697, -- 2411.04075 M3SciQA: A Multi-Modal Multi-Document Scientific QA Benchmark for Evaluating Fou
    39720, -- 2411.04424 Bayesian Calibration of Win Rate Estimation with LLM Evaluators
    39727, -- 2411.04588 Tibyan Corpus: Balanced and Comprehensive Error Coverage Corpus Using ChatGPT fo
    39738, -- 2411.04825 VTechAGP: An Academic-to-General-Audience Text Paraphrase Dataset and Benchmark
    39787, -- 2411.05338 SciDQA: A Deep Reading Comprehension Dataset over Scientific Papers
    39802, -- 2411.05679 Tell What You Hear From What You See -- Video to Audio Generation Through Text
    39944, -- 2411.08147 Large Language Models Can Self-Improve in Long-context Reasoning
    39986, -- 2411.09018 Bridging the Visual Gap: Fine-Tuning Multimodal Models with Knowledge-Adapted Ca
    40030, -- 2411.10129 Prompting and Fine-tuning Large Language Models for Automated Code Review Commen
    40159, -- 2411.12287 CUE-M: Contextual Understanding and Enhanced Search with Multimodal Large Langua
    40164, -- 2411.12460 Guide-to-Explain for Controllable Summarization
    40194, -- 2411.13100 Song Form-aware Full-Song Text-to-Lyrics Generation with Multi-Level Granularity
    40210, -- 2411.13425 Watermark under Fire: A Robustness Evaluation of LLM Watermarking
    40213, -- 2411.13477 PatentEdits: Framing Patent Novelty as Textual Entailment
    40225, -- 2411.13577 WavChat: A Survey of Spoken Dialogue Models
    40246, -- 2411.14137 Visual Contexts Clarify Ambiguous Expressions: A Benchmark Dataset
    40326, -- 2411.15122 ReXrank: A Public Leaderboard for AI-Powered Radiology Report Generation
    40376, -- 2411.15640 AfriMed-QA: A Pan-African, Multi-Specialty, Medical Question-Answering Benchmark
    40442, -- 2411.16594 From Generation to Judgment: Opportunities and Challenges of LLM-as-a-judge
    40460, -- 2411.16778 GEMeX: A Large-Scale, Groundable, and Explainable Medical VQA Benchmark for Ches
    40491, -- 2411.17176 ChatGen: Automatic Text-to-Image Generation From FreeStyle Chatting
    40493, -- 2411.17188 Interleaved Scene Graphs for Interleaved Text-and-Image Generation Assessment
    40500, -- 2411.17248 DiffSLT: Enhancing Diversity in Sign Language Translation via Diffusion Model
    40509, -- 2411.17388 Can LLMs be Good Graph Judge for Knowledge Graph Construction?
    40581, -- 2411.18180 DistinctAD: Distinctive Audio Description Generation in Contexts
    40670, -- 2411.19325 GEOBench-VLM: Benchmarking Vision-Language Models for Geospatial Tasks
    40673, -- 2411.19378 Libra: Leveraging Temporal Images for Biomedical Radiology Analysis
    40703, -- 2411.19655 Truth or Mirage? Towards End-to-End Factuality Evaluation with LLM-Oasis
    40826, -- 2412.01340 A 2-step Framework for Automated Literary Translation Evaluation: Its Promises a
    40934, -- 2412.02819 CNNSum: Exploring Long-Context Summarization with Large Language Models in Chine
    40938, -- 2412.02904 Enhancing Trust in Large Language Models with Uncertainty-Aware Fine-Tuning
    41045, -- 2412.04244 GigaHands: A Massive Annotated Dataset of Bimanual Hand Activities
    41130, -- 2412.04954 Gla-AI4BioMed at RRG24: Visual Instruction-tuned Adaptation for Radiology Report
    41172, -- 2412.05563 A Survey on Uncertainty Quantification of Large Language Models: Taxonomy, Open
    41296, -- 2412.07320 CoMA: Compositional Human Motion Generation with Multi-modal Agents
    41318, -- 2412.07704 GEXIA: Granularity Expansion and Iterative Approximation for Scalable Multi-grai
    41373, -- 2412.08389 SweetieChat: A Strategy-Enhanced Role-playing Framework for Diverse Scenarios Ha
    41501, -- 2412.09754 ViCaS: A Dataset for Combining Holistic and Pixel-level Video Understanding usin
    41528, -- 2412.10121 Familiarity: Better Evaluation of Zero-Shot Named Entity Recognition by Quantify
    41538, -- 2412.10271 Benchmarking Linguistic Diversity of Large Language Models
    41555, -- 2412.10424 LLM-as-an-Interviewer: Beyond Static Testing Through Dynamic LLM Evaluation
    41564, -- 2412.10523 The Language of Motion: Unifying Verbal and Non-verbal Language of 3D Human Moti
    41586, -- 2412.10906 SusGen-GPT: A Data-Centric LLM for Financial NLP and Sustainability Report Gener
    41596, -- 2412.11063 LAW: Legal Agentic Workflows for Custody and Fund Services Contracts
    41606, -- 2412.11250 Beyond Discrete Personas: Personality Modeling Through Journal Intensive Convers
    41654, -- 2412.11757 SCITAT: A Question Answering Benchmark for Scientific Tables and Text Covering D
    41655, -- 2412.11763 QUENCH: Measuring the gap between Indic and Non-Indic Contextual General Reasoni
    41675, -- 2412.11937 Precise Length Control in Large Language Models
    41691, -- 2412.12040 How Private are Language Models in Abstractive Summarization?
    41711, -- 2412.12318 Graph-Guided Textual Explanation Generation Framework
    41712, -- 2412.12322 RAG Playground: A Framework for Systematic Evaluation of Retrieval Strategies an
    41738, -- 2412.12674 Train More Parameters But Mind Their Placement: Insights into Language Adaptatio
    41773, -- 2412.13110 Improving Explainability of Sentence-level Metrics via Edit-level Attribution fo
    41814, -- 2412.13626 LIFT: Improving Long Context Understanding Through Long Input Fine-Tuning
    41848, -- 2412.14140 GLIDER: Grading LLM Interactions and Decisions using Explainable Ranking
    41868, -- 2412.14373 ECG-Byte: A Tokenizer for End-to-End Generative Electrocardiogram Language Model
    41913, -- 2412.15118 Reasoning Through Execution: Unifying Process and Outcome Rewards for Code Gener
    41967, -- 2412.15524 HREF: Human Response-Guided Evaluation of Instruction Following in Language Mode
    41975, -- 2412.15605 Don't Do RAG: When Cache-Augmented Generation is All You Need for Knowledge Task
    42077, -- 2412.17321 Assessing Human Editing Effort on LLM-Generated Texts via Compression-Based Edit
    42129, -- 2412.17910 A Novel Approach to Balance Convenience and Nutrition in Meals With Long-Term Gr
    42130, -- 2412.17933 BenCzechMark : A Czech-centric Multitask and Multimetric Benchmark for Large Lan
    42189, -- 2412.18675 TAB: Transformer Attention Bottlenecks enable User Intervention and Debugging in
    42215, -- 2412.19260 MEDEC: A Benchmark for Medical Error Detection and Correction in Clinical Notes
    42226, -- 2412.19512 Safeguard Fine-Tuned LLMs Through Pre- and Post-Tuning Model Merging
    42264, -- 2412.20127 M-MAD: Multidimensional Multi-Agent Debate Framework for Fine-grained Machine Tr
    42327, -- 2501.00097 CaseSumm: A Large-Scale Dataset for Long-Context Summarization from U.S. Supreme
    42398, -- 2501.01059 Dynamic Attention-Guided Context Decoding for Mitigating Context Faithfulness Ha
    42506, -- 2501.02702 QuIM-RAG: Advancing Retrieval-Augmented Generation with Inverted Question Matchi
    42561, -- 2501.03545 Beyond Factual Accuracy: Evaluating Coverage of Diverse Factual Information in L
    42703, -- 2501.05874 VideoRAG: Retrieval-Augmented Generation over Video Corpus
    42810, -- 2501.07718 Benchmarking Abstractive Summarisation: A Dataset of Human-authored Summaries of
    42835, -- 2501.08243 Engineering LLM Powered Multi-agent Framework for Autonomous CloudOps
    42869, -- 2501.08716 The Inherent Limits of Pretrained LLMs: The Unexpected Convergence of Instructio
    42935, -- 2501.09768 Can Large Language Models Predict the Outcome of Judicial Decisions?
    42975, -- 2501.10483 ArxEval: Evaluating Retrieval and Generation in Language Models for Scientific L
    43090, -- 2501.12619 Distillation Quantification for Large Language Models
    43128, -- 2501.13299 Hypothesis Generation for Materials Discovery and Design Using Goal-Driven and C
    43148, -- 2501.13567 K-COMP: Retrieval-Augmented Medical Domain Question Answering With Knowledge-Inj
    43234, -- 2501.15090 Speech Translation Refinement using Large Language Models
    43281, -- 2501.15688 Transformer-Based Multimodal Knowledge Graph Completion with Link-Aware Contexts
    43401, -- 2501.18128 Unraveling the Capabilities of Language Models in News Summarization
    43404, -- 2501.18251 How to Select Datapoints for Efficient Human Evaluation of NLG Models?
    43408, -- 2501.18324 A Video-grounded Dialogue Dataset and Metric for Event-driven Activities
    43467, -- 2501.19201 Efficient Reasoning with Hidden Thinking
    43508, -- 2502.00577 Understanding Multimodal LLMs Under Distribution Shifts: An Information-Theoreti
    43573, -- 2502.01534 Preference Leakage: A Contamination Problem in LLM-as-a-judge
    43595, -- 2502.01673 Multilingual State Space Models for Structured Question Answering in Indic Langu
    43596, -- 2502.01697 BARE: Leveraging Base Language Models for Few-Shot Synthetic Data Generation
    43642, -- 2502.02249 Conversation AI Dialog for Medicare powered by Finetuning and Retrieval Augmente
    43685, -- 2502.02904 ScholaWrite: A Dataset of End-to-End Scholarly Writing Process
    43750, -- 2502.04176 MRAMG-Bench: A Comprehensive Benchmark for Advancing Multimodal Retrieval-Augmen
    43789, -- 2502.04413 MedRAG: Enhancing Retrieval-augmented Generation with Knowledge Graph-Elicited R
    43791, -- 2502.04424 EmoBench-M: Benchmarking Emotional Intelligence for Multimodal Large Language Mo
    43878, -- 2502.05589 On Memory Construction and Retrieval for Personalized Conversational Agents
    43881, -- 2502.05628 AnyEdit: Edit Any Knowledge Encoded in Language Models
    43910, -- 2502.06147 LegalViz: Legal Text Visualization by Text To Diagram Generation
    44001, -- 2502.07188 A Large-Scale Benchmark for Vietnamese Sentence Paraphrases
    44024, -- 2502.07461 JamendoMaxCaps: A Large Scale Music-caption Dataset with Imputed Metadata
    44082, -- 2502.08226 TRISHUL: Towards Region Identification and Screen Hierarchy Understanding for La
    44086, -- 2502.08279 What Is That Talk About? A Video-to-Text Summarization Dataset for Scientific Pr
    44114, -- 2502.08745 IHEval: Evaluating Language Models on Following the Instruction Hierarchy
    44123, -- 2502.08826 Ask in Any Modality: A Comprehensive Survey on Multimodal Retrieval-Augmented Ge
    44145, -- 2502.09284 SparQLe: Speech Queries to Text Translation Through LLMs
    44231, -- 2502.10563 Accelerating Unbiased LLM Evaluation via Synthetic Feedback
    44236, -- 2502.10636 USER-VLM 360: Personalized Vision Language Models with User-aware Tuning for Soc
    44281, -- 2502.11115 Are Generative Models Underconfident? An Embarrassingly Simple Quality Estimatio
    44296, -- 2502.11177 The Mirage of Model Editing: Revisiting Evaluation in the Wild
    44298, -- 2502.11187 TituLLMs: A Family of Bangla LLMs with Comprehensive Benchmarking
    44306, -- 2502.11246 MemeSense: An Adaptive In-Context Framework for Social Commonsense Driven Meme M
    44322, -- 2502.11387 RoleMRC: A Fine-Grained Composite Benchmark for Role-Playing and Instruction-Fol
    44374, -- 2502.11824 M-ABSA: A Multilingual Dataset for Aspect-Based Sentiment Analysis
    44428, -- 2502.12150 Idiosyncrasies in Large Language Models
    44468, -- 2502.12623 DeepResonance: Enhancing Multimodal Music Understanding via Music-centric Multi-
    44488, -- 2502.12923 On-Device LLMs for Home Assistant: Dual Role in Intent Detection and Response Ge
    44489, -- 2502.12927 SEFL: Harnessing Large Language Model Agents to Improve Educational Feedback Sys
    44505, -- 2502.13034 Natural Language Generation from Visual Sequences: Challenges and Future Directi
    44576, -- 2502.13647 Instruction Tuning on Public Government and Cultural Data for Low-Resource Langu
    44617, -- 2502.14083 Are Rules Meant to be Broken? Understanding Multilingual Moral Reasoning as a Co
    44670, -- 2502.14644 LIFT: Improving Long Context Understanding of Large Language Models through Long
    44679, -- 2502.14748 Large Language Models Struggle to Describe the Haystack without Human Help: Huma
    44706, -- 2502.14865 Time Travel: A Comprehensive Benchmark to Evaluate LMMs on Historical and Cultur
    44727, -- 2502.15022 A Meta-Evaluation of Style and Attribute Transfer Metrics
    44838, -- 2502.16427 Fine-Grained Video Captioning through Scene Graph Consolidation
    44840, -- 2502.16457 Towards Fully-Automated Materials Discovery via Large-Scale Synthesis Dataset an
    44860, -- 2502.16704 Code Summarization Beyond Function Level
    44889, -- 2502.16942 NUTSHELL: A Dataset for Abstract Generation from Scientific Talks
    44898, -- 2502.16989 All-in-one: Understanding and Generation in Multimodal Reasoning with the MAIA B
    44931, -- 2502.17297 Benchmarking Retrieval-Augmented Generation in Multi-Modal Contexts
    44956, -- 2502.17540 PosterSum: A Multimodal Benchmark for Scientific Poster Summarization
    45055, -- 2502.18940 MathTutorBench: A Benchmark for Measuring Open-ended Pedagogical Capabilities of
    45164, -- 2502.20258 LLM as a Broken Telephone: Iterative Generation Distorts Information
    45217, -- 2502.20973 Arabizi vs LLMs: Can the Genie Understand the Language of Aladdin?
    45303, -- 2503.01155 Nature-Inspired Population-Based Evolution of Large Language Models
    45322, -- 2503.01372 SwiLTra-Bench: The Swiss Legal Translation Benchmark
    45444, -- 2503.02879 Wikipedia in the Era of LLMs: Evolution and Risks
    45569, -- 2503.04789 Ext2Gen: Alignment through Unified Extraction and Generation for Robust Retrieva
    45595, -- 2503.05142 RocketEval: Efficient Automated LLM Evaluation via Grading Checklist
    45600, -- 2503.05179 Sketch-of-Thought: Efficient LLM Reasoning with Adaptive Cognitive-Inspired Sket
    45611, -- 2503.05328 Dynamic Knowledge Integration for Evidence-Driven Counter-Argument Generation wi
    45616, -- 2503.05347 GEMA-Score: Granular Explainable Multi-Agent Score for Radiology Report Evaluati
    45660, -- 2503.06119 Unlocking Pretrained LLMs for Motion-Related Multimodal Generation: A Fine-Tunin
    45838, -- 2503.08026 In Prospect and Retrospect: Reflective Memory Management for Long-term Personali
    45922, -- 2503.08890 PlainQAFact: Automatic Factuality Evaluation Metric for Biomedical Plain Languag
    46115, -- 2503.10997 RONA: Pragmatically Diverse Image Captioning with Coherence Relations
    46260, -- 2503.13369 Sightation Counts: Leveraging Sighted User Feedback in Building a BLV-aligned Da
    46274, -- 2503.13517 CURIE: Evaluating LLMs On Multitask Scientific Long Context Understanding and Re
    46355, -- 2503.14604 Image Captioning Evaluation in the Age of Multimodal LLMs: Challenges and Future
    46360, -- 2503.14756 SceneEval: Evaluating Semantic Coherence in Text-Conditioned 3D Indoor Scene Syn
    46413, -- 2503.15620 Does Context Matter? ContextualJudgeBench for Evaluating LLM-based Judges in Con
    46424, -- 2503.15718 Am I eligible? Natural Language Inference for Clinical Trial Patient Recruitment
    46432, -- 2503.15879 Typed-RAG: Type-aware Multi-Aspect Decomposition for Non-Factoid Question Answer
    46458, -- 2503.16161 Towards Lighter and Robust Evaluation for Retrieval Augmented Generation
    46503, -- 2503.16545 EmpathyAgent: Can Embodied Agents Conduct Empathetic Actions?
    46584, -- 2503.17827 4D-Bench: Benchmarking Multi-modal Large Language Models for 4D Object Understan
    46706, -- 2503.19356 Can Vision-Language Models Answer Face to Face Questions in the Real-World?
    46819, -- 2503.20990 FinAudio: A Benchmark for Audio Large Language Models in Financial Applications
    46899, -- 2503.21910 JEEM: Vision-Language Understanding in Four Arabic Dialects
    46943, -- 2503.22625 Challenges and Paths Towards AI for Software Engineering
    46991, -- 2503.23204 The Challenge of Achieving Attributability in Multilingual Table-to-Text Generat
    47004, -- 2503.23339 A Scalable Framework for Evaluating Health Language Models
    47075, -- 2503.24379 Any2Caption:Interpreting Any Condition to Caption for Controllable Video Generat
    47114, -- 2504.00752 LLMs4SchemaDiscovery: A Human-in-the-Loop Workflow for Scientific Schema Mining
    47128, -- 2504.00939 WikiVideo: Article Generation from Multiple Videos
    47142, -- 2504.01196 $μ$KE: Matryoshka Unstructured Knowledge Editing of Large Language Models
    47226, -- 2504.02478 MG-MotionLLM: A Unified Framework for Motion Comprehension and Generation across
    47277, -- 2504.03197 Explain with Visual Keypoints Like a Real Mentor! A Benchmark for Multimodal Sol
    47291, -- 2504.03486 Structured Legal Document Generation in India: A Model-Agnostic Wrapper Approach
    47375, -- 2504.05220 Leveraging LLMs for Utility-Focused Annotation: Reducing Manual Effort for Retri
    47386, -- 2504.05305 URECA: Unique Region Caption Anything
    47470, -- 2504.07104 Relevance Isn't All You Need: Scaling RAG Systems With Inference-Time Compute Vi
    47501, -- 2504.07803 A System for Comprehensive Assessment of RAG Frameworks
    47531, -- 2504.07989 Regional Tiny Stories: Using Small Models to Compare Language Learning and Token
    47537, -- 2504.08120 DeepSeek vs. o3-mini: How Well can Reasoning LLMs Evaluate MT and Summarization?
    47614, -- 2504.09593 ControlNET: A Firewall for RAG-based LLM System
    47788, -- 2504.12157 FocusedAD: Character-centric Movie Audio Description
    47901, -- 2504.13677 Revisiting Uncertainty Quantification Evaluation in Language Models: Spurious In
    47962, -- 2504.14738 PROMPTEVALS: A Dataset of Assertions and Guardrails for Custom Production Large
    47966, -- 2504.14772 Knowledge Distillation and Dataset Distillation of Large Language Models: Emergi
    47975, -- 2504.14891 Retrieval Augmented Generation Evaluation in the Era of Large Language Models: A
    48014, -- 2504.15330 Med-CoDE: Medical Critique based Disagreement Evaluation Framework
    48029, -- 2504.15610 A LoRA-Based Approach to Fine-Tuning LLMs for Educational Guidance in Resource-C
    48055, -- 2504.16060 Vision-Language Models Are Not Pragmatically Competent in Referring Expression G
    48176, -- 2504.19254 Uncertainty Quantification for Language Models: A Suite of Black-Box, White-Box,
    48184, -- 2504.19467 BRIDGE: Benchmarking Large Language Models for Understanding Real-world Clinical
    48210, -- 2504.20119 Can LLMs Be Trusted for Evaluating RAG Systems? A Survey of Methods and Datasets
    48212, -- 2504.20168 MICE for CATs: Model-Internal Confidence Estimation for Calibrating Agents with
    48229, -- 2504.20734 UniversalRAG: Retrieval-Augmented Generation over Corpora of Diverse Modalities
    48243, -- 2504.20996 X-Fusion: Introducing New Modality to Frozen Large Language Models
    48249, -- 2504.21117 Beyond One-Size-Fits-All: Inversion Learning for Highly Effective NLG Evaluation
    48283, -- 2505.00019 An Empirical Study on Prompt Compression for Large Language Models
    48287, -- 2505.00065 ConSens: Assessing context grounding in open-book question answering
    48295, -- 2505.00254 Empowering Agentic Video Analytics Systems with Video Language Models
    48341, -- 2505.01481 VideoHallu: Evaluating and Mitigating Multi-modal Hallucinations on Synthetic Vi
    48414, -- 2505.02820 AutoLibra: Agent Metric Induction from Open-Ended Feedback
    48422, -- 2505.02872 Decoding Open-Ended Information Seeking Goals from Eye Movements in Reading
    48448, -- 2505.03427 MedArabiQ: Benchmarking Large Language Models on Arabic Medical Tasks
    48521, -- 2505.05026 G-FOCUS: Towards a Robust Method for Assessing UI Design Persuasiveness
    48582, -- 2505.06296 Q-Heart: ECG Question Answering via Knowledge-Informed Multimodal LLMs
    48623, -- 2505.07233 DynamicRAG: Leveraging Outputs of Large Language Model as Feedback for Dynamic R
    48830, -- 2505.11080 BLEUBERI: BLEU is a surprisingly effective reward for instruction following
    48832, -- 2505.11095 Towards Better Evaluation for Generated Patent Claims
    48875, -- 2505.11545 TARGET: Benchmarking Table Retrieval for Generative Tasks
    48934, -- 2505.12215 GMSA: Enhancing Context Compression via Group Merging and Layer Semantic Alignme
    49005, -- 2505.12864 LEXam: Benchmarking Legal Reasoning on 340 Law Exams
    49013, -- 2505.12950 GuRE:Generative Query REwriter for Legal Passage Retrieval
    49023, -- 2505.13036 KIT's Offline Speech Translation and Instruction Following Submission for IWSLT
    49084, -- 2505.13559 CS-Sum: A Benchmark for Code-Switching Dialogue Summarization and the Limits of
    49094, -- 2505.13778 CoIn: Counting the Invisible Reasoning Tokens in Commercial Opaque LLM APIs
    49145, -- 2505.14244 TransBench: Benchmarking Machine Translation for Industrial-Scale Applications
    49152, -- 2505.14279 YESciEval: Robust LLM-as-a-Judge for Scientific Question Answering
    49165, -- 2505.14376 AutoRev: Automatic Peer Review System for Academic Research Papers
    49180, -- 2505.14462 RAVENEA: A Benchmark for Multimodal Retrieval-Augmented Visual Culture Understan
    49256, -- 2505.15065 The Pursuit of Empathy: Evaluating Small Language Models for PTSD Dialogue Suppo
    49313, -- 2505.15695 Can Large Language Models be Effective Online Opinion Miners?
    49349, -- 2505.15957 Towards Holistic Evaluation of Large Audio-Language Models: A Comprehensive Surv
    49369, -- 2505.16134 Position of Uncertainty: A Cross-Linguistic Study of Positional Bias in Large La
    49381, -- 2505.16222 Don't Judge Code by Its Cover: Exploring Biases in LLM Judges for Code Evaluatio
    49421, -- 2505.16566 ScholarBench: A Bilingual Benchmark for Abstraction, Comprehension, and Reasonin
    49475, -- 2505.16986 T1: A Tool-Oriented Conversational Dataset for Multi-Turn Agentic Planning
    49488, -- 2505.17021 ARB: A Comprehensive Arabic Multimodal Reasoning Benchmark
    49495, -- 2505.17104 P2P: Automated Paper-to-Poster Generation and Fine-Grained Benchmark
    49530, -- 2505.17558 Teaching with Lies: Curriculum DPO on Synthetic Negatives for Hallucination Dete
    49585, -- 2505.18152 Fann or Flop: A Multigenre, Multiera Benchmark for Arabic Poetry Understanding i
    49591, -- 2505.18207 BAGELS: Benchmarking the Automated Generation and Extraction of Limitations from
    49642, -- 2505.18700 GRE Suite: Geo-localization Inference via Fine-Tuned Vision-Language Models and
    49659, -- 2505.18853 Smoothie: Smoothing Diffusion on Token Embeddings for Text Generation
    49695, -- 2505.19163 SpokenNativQA: Multilingual Everyday Spoken Queries for LLMs
    49728, -- 2505.19388 gec-metrics: A Unified Library for Grammatical Error Correction Evaluation
    49786, -- 2505.19912 APE: A Data-Centric Benchmark for Efficient LLM Adaptation in Text Summarization
    49814, -- 2505.20124 TUNA: Comprehensive Fine-grained Temporal Understanding Evaluation on Dense Dyna
    49825, -- 2505.20163 Exploring Generative Error Correction for Dysarthric Speech Recognition
    49930, -- 2505.21190 Lunguage: A Benchmark for Structured and Sequential Chest X-ray Interpretation
    49973, -- 2505.21724 OmniResponse: Online Multimodal Conversational Response Generation in Dyadic Int
    50010, -- 2505.22338 Text2Grad: Reinforcement Learning from Natural Language Feedback
    50142, -- 2505.23722 Label-Guided In-Context Learning for Named Entity Recognition
    50232, -- 2505.24456 CaMMT: Benchmarking Culturally Aware Multimodal Machine Translation
    50246, -- 2505.24621 Benchmarking Large Language Models for Cryptanalysis and Mismatched-Generalizati
    50305, -- 2506.00381 Neuro2Semantic: A Transfer Learning Framework for Semantic Reconstruction of Con
    50316, -- 2506.00469 Massively Multilingual Adaptation of Large Language Models Using Bilingual Trans
    50323, -- 2506.00551 AnnaAgent: Dynamic Evolution Agent System with Multi-Session Memory for Realisti
    50349, -- 2506.00979 IVY-FAKE: A Unified Explainable Framework and Benchmark for Image and Video AIGC
    50371, -- 2506.01265 Beyond In-Context Learning: Aligning Long-form Generation of Large Language Mode
    50397, -- 2506.01668 Small Stickers, Big Meanings: A Multilingual Sticker Semantic Understanding Data
    50458, -- 2506.02515 FinChain: A Symbolic Benchmark for Verifiable Chain-of-Thought Financial Reasoni
    50506, -- 2506.03238 Rethinking Whole-Body CT Image Interpretation: An Abnormality-Centric Approach
    50548, -- 2506.04020 QQSUM: A Novel Task and Model of Quantitative Query-Focused Summarization for Re
    50588, -- 2506.04557 SSA-COMET: Do LLMs Outperform Learned Metrics in Evaluating MT for Under-Resourc
    50679, -- 2506.05606 OPeRA: A Dataset of Observation, Persona, Rationale, and Action for Evaluating L
    50681, -- 2506.05673 Peer-Ranked Precision: Creating a Foundational Dataset for Fine-Tuning Vision Mo
    50686, -- 2506.05766 BioMol-MQA: A Multi-Modal Question Answering Dataset For LLM Reasoning Over Bio-
    50699, -- 2506.06006 Bootstrapping World Models from Dynamics Models in Multimodal Foundation Models
    50729, -- 2506.06561 LaMP-Cap: Personalized Figure Caption Generation With Multimodal Figure Profiles
    50959, -- 2506.09958 Kvasir-VQA-x1: A Multimodal Dataset for Medical Reasoning and Robust MedVQA in G
    50993, -- 2506.10328 Towards Scalable SOAP Note Generation: A Weakly Supervised Multimodal Framework
    51013, -- 2506.10521 Scientists' First Exam: Probing Cognitive Abilities of MLLM via Perception, Unde
    51038, -- 2506.10912 Breaking Bad Molecules: Are MLLMs Ready for Structure-Level Molecular Detoxifica
    51099, -- 2506.12285 CMI-Bench: A Comprehensive Benchmark for Evaluating Music Instruction Following
    51105, -- 2506.12450 Language Surgery in Multilingual Large Language Models
    51191, -- 2506.14028 MultiFinBen: A Multilingual, Multimodal, and Difficulty-Aware Benchmark for Fina
    51203, -- 2506.14285 From What to Respond to When to Respond: Timely Response Generation for Open-dom
    51252, -- 2506.15154 SonicVerse: Multi-Task Learning for Music Feature-Informed Captioning
    51279, -- 2506.15925 Reranking-based Generation for Unbiased Perspective Summarization
    51310, -- 2506.16962 Enhancing Step-by-Step and Verifiable Medical Reasoning in MLLMs
    51329, -- 2506.17335 LMR-BENCH: Evaluating LLM Agent's Ability on Reproducing Language Modeling Resea
    51368, -- 2506.18369 RePIC: Reinforced Post-Training for Personalizing Multi-Modal Language Models
    51404, -- 2506.19028 Quantifying Fairness in LLMs Beyond Tokens: A Semantic and Statistical Perspecti
    51452, -- 2506.20274 Enterprise Large Language Model Evaluation Benchmark
    51482, -- 2506.20803 The Ideation-Execution Gap: Execution Outcomes of LLM-Generated versus Human Res
    51498, -- 2506.21170 Compressed and Smooth Latent Space for Text Diffusion Modeling
    51601, -- 2507.00316 $μ^2$Tokenizer: Differentiable Multi-Scale Multi-Modal Tokenizer for Radiology R
    51640, -- 2507.02221 GDC Cohort Copilot: An AI Copilot for Curating Cohorts from the Genomic Data Com
    51680, -- 2507.03637 Large Language Models for Combinatorial Optimization: A Systematic Review
    51894, -- 2507.11288 Opus: A Prompt Intention Framework for Complex Workflow Generation
    52070, -- 2507.19634 MCIF: Multimodal Crosslingual Instruction-Following Benchmark from Scientific Ta
    52075, -- 2507.20152 Goal Alignment in LLM-Based User Simulators for Conversational AI
    52143, -- 2508.00454 Learning an Efficient Multi-Turn Dialogue Evaluator from Multiple Judges
    52205, -- 2508.03164 ChartCap: Mitigating Hallucination of Dense Chart Captioning
    52228, -- 2508.03990 Are Today's LLMs Ready to Explain Well-Being Concepts?
    52240, -- 2508.04423 Evaluating, Synthesizing, and Enhancing for Customer Support Conversation
    52348, -- 2508.09776 Can LLM-Generated Textual Explanations Enhance Model Classification Performance?
    52373, -- 2508.10860 From Black Box to Transparency: Enhancing Automated Interpreting Assessment with
    52455, -- 2508.15361 A Survey on Large Language Model Benchmarks
    52489, -- 2508.17234 ClaimGen-CN: A Large-scale Chinese Dataset for Legal Claim Generation
    52507, -- 2508.17973 German4All -- A Dataset and Model for Readability-Controlled Paraphrasing in Ger
    52549, -- 2508.19813 T2R-bench: A Benchmark for Generating Article-Level Reports from Real World Indu
    52647, -- 2509.03867 Drivel-ology: Challenging LLMs with Interpreting Nonsense with Depth
    52718, -- 2509.08031 AU-Harness: An Open-Source Toolkit for Holistic Evaluation of Audio LLMs
    52851, -- 2509.14180 Synthesizing Behaviorally-Grounded Reasoning Chains: A Data-Generation Framework
    53147, -- 2510.02190 A Rigorous Benchmark with Multidimensional Evaluation for Deep Research Agents:
    53156, -- 2510.00428 Automated Structured Radiology Report Generation with Rich Clinical Context
    53170, -- 2510.01143 Generalized Parallel Scaling with Interdependent Generations
    53213, -- 2510.02571 How Confident are Video Models? Empowering Video Models to Express their Uncerta
    53274, -- 2509.23379 CCD: Mitigating Hallucinations in Radiology MLLMs via Clinical Contrastive Decod
    53293, -- 2510.05122 CARE: Cognitive-reasoning Augmented Reinforcement for Emotional Support Conversa
    53491, -- 2510.10681 RePro: Training Language Models to Faithfully Recycle the Web for Pretraining
    53497, -- 2510.09474 Multimodal Policy Internalization for Conversational Agents
    53504, -- 2510.09116 DITING: A Multi-Agent Evaluation Framework for Benchmarking Web Novel Translatio
    53557, -- 2510.04767 ParallelBench: Understanding the Trade-offs of Parallel Decoding in Diffusion LL
    53582, -- 2510.13586 Deflanderization for Game Dialogue: Balancing Character Authenticity with Task E
    53697, -- 2510.14605 Knowledge-based Visual Question Answer with Multimodal Processing, Retrieval and
    53736, -- 2510.15600 Unleashing Scientific Reasoning for Bio-experimental Protocol Generation via Str
    53776, -- 2510.18279 Text or Pixels? It Takes Half: On the Token Efficiency of Visual Text Inputs in
    53781, -- 2510.19600 Human-Agent Collaborative Paper-to-Page Crafting for Under $0.1
    53910, -- 2510.23828 Beyond Understanding: Evaluating the Pragmatic Gap in LLMs' Cultural Processing
    53915, -- 2508.07766 UniSVG: A Unified Dataset for Vector Graphic Understanding and Generation with M
    54087, -- 2511.03295 How to Evaluate Speech Translation with Source-Aware Neural MT Metrics
    54104, -- 2511.05369 Dense Motion Captioning
    54265, -- 2511.14349 ARC-Chapter: Structuring Hour-Long Videos into Navigable Chapters and Hierarchic
    54380, -- 2511.18659 CLaRa: Bridging Retrieval and Generation with Continuous Latent Reasoning
    54461, -- 2512.01420 PromptBridge: Cross-Model Prompt Transfer for Large Language Models
    54653, -- 2512.03704 DZ-TDPO: Non-Destructive Temporal Alignment for Mutable State Tracking in Long-C
    54677, -- 2512.04763 MemLoRA: Distilling Expert Adapters for On-Device Memory Systems
    54695, -- 2512.08296 Towards a Science of Scaling Agent Systems
    54846, -- 2512.15713 DiffusionVL: Translating Any Autoregressive Models into Diffusion Vision Languag
    54892, -- 2512.15907 TabReX : Tabular Referenceless eXplainable Evaluation
    54995, -- 2512.21643 Omni-Weather: Unified Multimodal Foundation Model for Weather Generation and Und
    55057, -- 2512.22905 JavisGPT: A Unified Multi-modal LLM for Sounding-Video Comprehension and Generat
    55285, -- 2601.07632 GeoMotionGPT: Geometry-Aligned Motion Understanding with Large Language Models
    55501, -- 2601.18744 TSRBench: A Comprehensive Multi-task Multi-modal Time Series Reasoning Benchmark
    55515, -- 2601.17277 PingPong: A Natural Benchmark for Multi-Turn Code-Switching Dialogues
    55703, -- 2601.22588 Rethinking LLM-as-a-Judge: Representation-as-a-Judge with Small Language Models
    55802, -- 2602.03955 AgentArk: Distilling Multi-Agent Intelligence into a Single LLM Agent
    55942, -- 2602.07054 AVERE: Improving Audiovisual Emotion Reasoning with Preference Optimization
    56042, -- 2602.08934 StealthRL: Reinforcement Learning Paraphrase Attacks for Multi-Detector Evasion
    56136, -- 2602.14060 LM-Lexicon: Improving Definition Modeling via Harmonizing Semantic Experts
    56152, -- 2602.13294 VisPhyWorld: Probing Physical Reasoning via Code-Driven Video Reconstruction
    56221, -- 2602.16802 References Improve LLM Alignment in Non-Verifiable Domains
    56370, -- 2602.21317 Shared Nature, Unique Nurture: PRISM for Pluralistic Reasoning via In-context St
    56372, -- 2602.23047 CL4SE: A Context Learning Benchmark For Software Engineering Tasks
    56409, -- 2602.23952 CC-VQA: Conflict- and Correlation-Aware Method for Mitigating Knowledge Conflict
    56598, -- 2603.09881 Do What I Say: A Spoken Prompt Dataset for Instruction-Following
    56674, -- 2603.11665 Multi-Task Reinforcement Learning for Enhanced Multimodal LLM-as-a-Judge
    56715, -- 2603.12935 Can Fairness Be Prompted? Prompt-Based Debiasing Strategies in High-Stakes Recom
    56770, -- 2603.13962 sebis at ArchEHR-QA 2026: How Much Can You Do Locally? Evaluating Grounded EHR Q
    57236, -- 2603.28301 LIBERO-Para: A Diagnostic Benchmark and Metrics for Paraphrase Robustness in VLA
    57454, -- 2604.09497 BERT-as-a-Judge: A Robust Alternative to Lexical Methods for Efficient Reference
    57535, -- 2604.14572 Don't Retrieve, Navigate: Distilling Enterprise Knowledge into Navigable Agent S
    57590, -- 2604.13313 Concrete Jungle: Towards Concreteness Paved Contrastive Negative Mining for Comp
    57605, -- 2604.06505 MedConclusion: A Benchmark for Biomedical Conclusion Generation from Structured
    57608, -- 2604.17972 Modeling Multiple Support Strategies within a Single Turn for Emotional Support
    57710, -- 2604.21668 Encoder-Free Human Motion Understanding via Structured Motion Descriptions
    57713, -- 2506.17001 PersonalAI: A Systematic Comparison of Knowledge Graph Storage and Retrieval App
    57972, -- 2604.20382 Graph2Counsel: Clinically Grounded Synthetic Counseling Dialogue Generation from
    58012, -- 2604.18967 Toward Clinically Acceptable Chest X-ray Report Generation: A Qualitative Retros
    58055, -- 2601.14944 The GDN-CC Dataset: Automatic Corpus Clarification for AI-enhanced Democratic Ci
    58124, -- 2604.15671 Long-Term Memory for VLA-based Agents in Open-World Task Execution
    58125, -- 2604.15597 LLMs Corrupt Your Documents When You Delegate
    58186, -- 2604.13552 Training-Free Test-Time Contrastive Learning for Large Language Models
    58223, -- 2604.12377 SCRIPT: A Subcharacter Compositional Representation Injection Module for Korean
    58242, -- 2604.11742 Discourse Diversity in Multi-Turn Empathic Dialogue
    58355, -- 2604.08991 PinpointQA: A Dataset and Benchmark for Small Object-Centric Spatial Understandi
    58389, -- 2604.08115 Revise: A Framework for Revising OCRed text in Practical Information Systems wit
    58453, -- 2604.05738 MedLayBench-V: A Large-Scale Benchmark for Expert-Lay Semantic Alignment in Medi
    58487, -- 2604.05083 Beyond LLM-as-a-Judge: Deterministic Metrics for Multilingual Generative Text Ev
    58575, -- 2604.02804 PaveBench: A Versatile Benchmark for Pavement Distress Perception and Interactiv
    58638, -- 2604.00493 A Reasoning-Enabled Vision-Language Foundation Model for Chest X-ray Interpretat
    58697, -- 2603.29630 BigEarthNet.txt: A Large-Scale Multi-Sensor Image-Text Dataset and Benchmark for
    58741, -- 2511.08917 "It's trained by non-disabled people": Evaluating How Image Quality Affects Prod
    58769, -- 2603.28363 SEA: Evaluating Sketch Abstraction Efficiency via Element-level Commonsense Visu
    58833, -- 2603.26049 Seeing Like Radiologists: Context- and Gaze-Guided Vision-Language Pretraining f
    58922, -- 2603.24690 UniICL: Systematizing Unified Multimodal In-context Learning through a Capabilit
    59050, -- 2603.21165 Many Dialects, Many Languages, One Cultural Lens: Evaluating Multilingual VLMs f
    59060, -- 2603.21174 Explainable Semantic Textual Similarity via Dissimilar Span Detection
    59270, -- 2603.16131 SciZoom: A Large-scale Benchmark for Hierarchical Scientific Summarization acros
    59341, -- 2603.14782 Information Asymmetry across Language Varieties: A Case Study on Cantonese-Manda
    59381, -- 2603.14497 WorldVLM: Combining World Model Forecasting and Vision-Language Reasoning
    59415, -- 2603.16934 AgriChat: A Multimodal Large Language Model for Agriculture Image Understanding
    59507, -- 2603.12248 Matching Features, Not Tokens: Energy-Based Fine-Tuning of Language Models
    59630, -- 2603.09452 CyberThreat-Eval: Can Large Language Models Automate Real-World Threat Research?
    59701, -- 2603.08282 Using Multimodal and Language-Agnostic Sentence Embeddings for Abstractive Summa
    59751, -- 2603.23529 Konkani LLM: Multi-Script Instruction Tuning and Evaluation for a Low-Resource I
    59765, -- 2603.06905 MedInjection-FR: Exploring the Role of Native, Synthetic, and Translated Data in
    59843, -- 2510.18077 Chain-of-Thought Reasoning Improves Context-Aware Translation with Large Languag
    59844, -- 2506.15751 Sysformer: Safeguarding Frozen Large Language Models with Adaptive System Prompt
    59981, -- 2603.02655 Real-Time Generation of Game Video Commentary with Multimodal LLMs: Pause-Aware
    60071, -- 2603.01225 Can Thinking Models Think to Detect Hateful Memes?
    60147, -- 2603.00355 StethoLM: Audio Language Model for Cardiopulmonary Analysis Across Clinical Task
    60209, -- 2602.23228 MovieTeller: Tool-augmented Movie Synopsis with ID Consistent Progressive Abstra
    60225, -- 2602.22843 A data- and compute-efficient chest X-ray foundation model beyond aggressive sca
    60249, -- 2602.23199 SC-Arena: A Natural Language Benchmark for Single-Cell Reasoning with Knowledge-
    60334, -- 2602.22253 AR&D: A Framework for Retrieving and Describing Concepts for Interpreting AudioL
    60504, -- 2602.14879 CT-Bench: A Benchmark for Multimodal Lesion Understanding in Computed Tomography
    60546, -- 2602.16110 OmniCT: Towards a Unified Slice-Volume LVLM for Comprehensive CT Analysis
    60586, -- 2602.16006 BTReport: A Framework for Brain Tumor Radiology Report Generation with Clinicall
    60707, -- 2602.12989 Evaluating the Homogeneity of Keyphrase Prediction Models
    60724, -- 2602.12639 CLASE: A Hybrid Method for Chinese Legalese Stylistic Evaluation
    60742, -- 2602.12370 LLaMo: Scaling Pretrained Language Models for Unified Motion Understanding and G
    60816, -- 2602.11354 ReplicatorBench: Benchmarking LLM Agents for Replicability in Social and Behavio
    60932, -- 2602.09383 BiasScope: Towards Automated Detection of Bias in LLM-as-a-Judge Evaluation
    60962, -- 2602.08979 Beyond Transcripts: A Renewed Perspective on Audio Chaptering
    61431, -- 2602.02136 Mitigating Safety Tax via Distribution-Grounded Refinement in Large Reasoning Mo
    61472, -- 2602.01685 Semantic-aware Wasserstein Policy Regularization for Large Language Model Alignm
    61500, -- 2602.01885 ES-MemEval: Benchmarking Conversational Agents on Personalized Long-Term Emotion
    61578, -- 2602.01200 Med3D-R1: Incentivizing Clinical Reasoning in 3D Medical Vision-Language Models
    61580, -- 2509.24739 Toward a Vision-Language Foundation Model for Medical Data: Multimodal Dataset a
    61609, -- 2602.00665 Can Small Language Models Handle Context-Summarized Multi-Turn Customer-Service
    61654, -- 2602.00393 Brazilian Portuguese Image Captioning with Transformers: A Study on Cross-Native
    61666, -- 2602.00296 RAGRouter-Bench: A Dataset and Benchmark for Adaptive RAG Routing
    61795, -- 2601.21895 Learn-to-Distance: Distance Learning for Detecting LLM-Generated Text
    61826, -- 2601.21617 PathReasoner-R1: Instilling Structured Reasoning into Pathology Vision-Language
    61858, -- 2601.22208 Stalled, Biased, and Confused: Uncovering Reasoning Failures in LLMs for Cloud-B
    61876, -- 2601.20090 Should I Have Expressed a Different Intent? Counterfactual Generation for LLM-Ba
    61930, -- 2601.20148 LogSieve: Task-Aware CI Log Reduction for Sustainable LLM-Based Analysis
    61960, -- 2601.19750 Benchmarking Multimodal Large Language Models for Missing Modality Completion in
    62013, -- 2601.10246 coTherapist: A Behavior-Aligned Small Language Model to Support Mental Healthcar
    62122, -- 2601.17151 Scaling medical imaging report generation with multimodal reinforcement learning
    62215, -- 2601.11595 Enhancing Model Context Protocol (MCP) with Context-Aware Server Collaboration
    62238, -- 2601.15161 Automated Rubrics for Reliable Evaluation of Medical Dialogue Systems
    62249, -- 2601.14862 Strategic Doctrine Language Models (sdLM): A Learning-System Framework for Doctr
    62261, -- 2601.14637 Forest-Chat: Adapting Vision-Language Agents for Interactive Forest Change Analy
    62289, -- 2601.14123 A Systematic Analysis of Chunking Strategies for Reliable Question Answering
    62319, -- 2601.13729 On Temperature-Constrained Non-Deterministic Machine Translation: Potential and
    62357, -- 2601.12805 SciHorizon-GENE: Benchmarking LLM for Life Sciences Inference from Gene Knowledg
    62380, -- 2601.12494 Harmonizing the Arabic Audio Space with Data Scheduling
    62458, -- 2601.10406 ErrEval: Error-Aware Evaluation for Question Generation through Explicit Diagnos
    62478, -- 2601.10020 EHRNavigator: A Multi-Agent System for Patient-Level Clinical Question Answering
    62490, -- 2601.09879 MedVL-SAM2: A unified 3D medical vision-language model for multimodal reasoning
    62567, -- 2601.08209 Generation-Augmented Generation: A Plug-and-Play Framework for Private Knowledge
    62614, -- 2601.07507 High-Rank Structured Modulation for Parameter-Efficient Fine-Tuning
    62631, -- 2601.07274 Towards Comprehensive Semantic Speech Embeddings for Chinese Dialects
    62682, -- 2601.06818 AgentHallu: Benchmarking Automated Hallucination Attribution of LLM-based Agents
    62725, -- 2601.05794 Simplify-This: A Comparative Analysis of Prompt-Based and Fine-Tuned LLMs
    62845, -- 2601.04377 Disco-RAG: Discourse-Aware Retrieval-Augmented Generation
    62912, -- 2601.03468 Understanding Reward Hacking in Text-to-Image Reinforcement Learning
    62930, -- 2601.03136 Limited Linguistic Diversity in Embodied AI Datasets
    62952, -- 2601.06157 ECLIPTICA -- A Framework for Switchable LLM Alignment via CITA - Contrastive Ins
    62954, -- 2601.02771 AbductiveMLLM: Boosting Visual Abductive Reasoning Within MLLMs
    62975, -- 2601.02536 MovieRecapsQA: A Multimodal Open-Ended Video Question-Answering Benchmark
    63019, -- 2601.01842 Towards Automated Lexicography: Generating and Evaluating Definitions for Learne
    63087, -- 2601.16218 M3Kang: Evaluating Multilingual Multimodal Mathematical Reasoning in Vision-Lang
    63124, -- 2601.00566 Low Rank Comes with Low Security: Gradient Assembly Poisoning Attacks against Di
    63147, -- 2601.00156 Focal-RegionFace: Generating Fine-Grained Multi-attribute Descriptions for Arbit
    63239, -- 2512.23206 Not too long do read: Evaluating LLM-generated extreme scientific summaries
    63320, -- 2512.21482 LogicLens: Visual-Logical Co-Reasoning for Text-Centric Forgery Analysis
    63471, -- 2512.18601 On Finding Inconsistencies in Documents
    63588, -- 2512.15943 Small Language Models for Efficient Agentic Tool Calling: Outperforming Large Mo
    63590, -- 2512.15925 Social Story Frames: Contextual Reasoning about Narrative Intent and Reception
    63625, -- 2512.15068 The Semantic Illusion: Certified Limits of Embedding-Based Hallucination Detecti
    63734, -- 2512.12756 FysicsWorld: A Unified Full-Modality Benchmark for Any-to-Any Understanding, Gen
    63830, -- 2512.10730 IRG-MotionLLM: Interleaving Motion Generation, Assessment and Refinement for Tex
    64040, -- 2512.06581 MedGRPO: Multi-Task Reinforcement Learning for Heterogeneous Medical Video Under
    64075, -- 2512.05658 Grounded Multilingual Medical Reasoning for Question Answering with Large Langua
    64311, -- 2512.01183 TempPerturb-Eval: On the Joint Effects of Internal Temperature and External Pert
    64369, -- 2512.00367 Breaking It Down: Domain-Aware Semantic Segmentation for Retrieval Augmented Gen
    64396, -- 2511.23253 AgriCoT: A Chain-of-Thought Benchmark for Evaluating Reasoning in Vision-Languag
    64501, -- 2511.20965 TrafficLens: Multi-Camera Traffic Video Analysis Using LLMs
    64838, -- 2511.15755 Multi-Agent LLM Orchestration Achieves Deterministic, High-Quality Decision Supp
    64871, -- 2511.14567 SweeperBot: Making 3D Browsing Accessible through View Analysis and Visual Quest
    65079, -- 2511.10002 PustakAI: Curriculum-Aligned and Interactive Textbooks Using Large Language Mode
    65085, -- 2511.09914 OIDA-QA: A Multimodal Benchmark for Analyzing the Opioid Industry Documents Arch
    65101, -- 2511.09483 CrochetBench: Can Vision-Language Models Move from Describing to Doing in Croche
    65165, -- 2511.08247 ParliaBench: An Evaluation and Benchmarking Framework for LLM-Generated Parliame
    65198, -- 2511.07744 VectorSynth: Fine-Grained Satellite Image Synthesis with Structured Semantics
    65215, -- 2511.07397 ConvFill: Model Collaboration for Responsive Conversational Voice Agents
    65219, -- 2511.07322 FinRpt: Dataset, Evaluation System and LLM-based Multi-agent Framework for Equit
    65256, -- 2511.06571 Rep2Text: Decoding Full Text from a Single LLM Token Representation
    65306, -- 2511.05124 QuAnTS: Question Answering on Time Series
    65314, -- 2511.04934 Leak@k: Unlearning Does Not Make LLMs Forget Under Probabilistic Decoding
    65330, -- 2511.04560 BanglaMedQA and BanglaMMedBench: Evaluating Retrieval-Augmented Generation Strat
    65401, -- 2511.03128 From Insight to Exploit: Leveraging LLM Collaboration for Adaptive Adversarial T
    65524, -- 2511.00846 OmniBrainBench: A Comprehensive Multimodal Benchmark for Brain Imaging Analysis
    65808, -- 2510.24792 PISA-Bench: The PISA Index as a Multilingual and Multimodal Metric for the Evalu
    65841, -- 2510.22758 EchoMind: An Interrelated Multi-level Benchmark for Evaluating Empathetic Speech
    65879, -- 2510.24774 PANORAMA: A Dataset and Benchmarks Capturing Decision Trails and Rationales in P
    65904, -- 2510.21537 Excision Score: Evaluating Edits with Surgical Precision
    65915, -- 2510.21360 A Diagnostic Benchmark for Sweden-Related Factual Knowledge
    65920, -- 2510.21258 Correlation Dimension of Auto-Regressive Large Language Models
    65999, -- 2510.20093 StableSketcher: Enhancing Diffusion Model for Pixel-based Sketch Generation via
    66172, -- 2510.17281 MemoryBench: A Benchmark for Memory and Continual Learning in LLM Systems
    66203, -- 2510.16724 A Comprehensive Survey on Reinforcement Learning-based Agentic Search: Foundatio
    66307, -- 2510.14664 SpeechLLM-as-Judges: Towards General and Interpretable Speech Quality Evaluation
    66344, -- 2508.03550 Beyond the Surface: Enhancing LLM-as-a-Judge Alignment with Human via Internal R
    66375, -- 2510.13494 LiteraryQA: Towards Effective Evaluation of Long-document Narrative QA
    66481, -- 2510.11639 OneRec-Think: In-Text Reasoning for Generative Recommendation
    66482, -- 2510.11599 SemCSE-Multi: Multifaceted and Decodable Embeddings for Aspect-Specific and Inte
    66526, -- 2510.10961 KOTOX: A Korean Toxic Dataset for Deobfuscation and Detoxification
    66616, -- 2510.09915 Enhancing Faithfulness in Abstractive Summarization via Span-Level Fine-Tuning
    66645, -- 2510.09243 CrisiText: A dataset of warning messages for LLM training in emergency communica
    66745, -- 2510.07877 Ready to Translate, Not to Represent? Bias and Performance Gaps in Multilingual
    66802, -- 2510.07061 Revisiting Metric Reliability for Fine-grained Evaluation of Machine Translation
    66809, -- 2510.06965 EDUMATH: Generating Standards-aligned Educational Math Word Problems
    66853, -- 2510.06371 EverydayMMQA: A Multilingual and Multimodal Framework for Culturally Grounded Sp
    66926, -- 2510.05026 A Set of Quebec-French Corpus of Regional Expressions and Terms
    66948, -- 2510.04504 Asynchronous Denoising Diffusion Models for Aligning Text-to-Image Generation
    66967, -- 2510.06265 Large Language Models Hallucination: A Comprehensive Survey
    67009, -- 2510.03696 Mind the Goal: Data-Efficient Goal-Oriented Evaluation of Conversational Agents
    67125, -- 2510.01792 Comparison of Unsupervised Metrics for Evaluating Judicial Decision Extraction
    67146, -- 2510.01582 ImageNet-Think-250K: A Large-Scale Synthetic Dataset for Multimodal Reasoning fo
    67177, -- 2510.01146 mR3: Multilingual Rubric-Agnostic Reward Reasoning Models
    67220, -- 2510.00691 Inclusive Easy-to-Read Generation for Individuals with Cognitive Impairments
    67302, -- 2509.26302 QUARTZ : QA-based Unsupervised Abstractive Refinement for Task-oriented Dialogue
    67303, -- 2509.26278 ProfVLM: A Lightweight Video-Language Model for Multi-View Proficiency Estimatio
    67310, -- 2509.26181 Explaining novel senses using definition generation with open language models
    67312, -- 2509.26165 Human-MME: A Holistic Evaluation Benchmark for Human-Centric Multimodal Large La
    67341, -- 2509.25851 MuSLR: Multimodal Symbolic Logical Reasoning
    67354, -- 2509.25773 v-HUB: A Benchmark for Video Humor Understanding from Vision and Sound
    67366, -- 2509.25671 The Flaw of Averages: Quantifying Uniformity of Performance on Benchmarks
    67435, -- 2509.24908 BOE-XSUM: Extreme Summarization in Clear Language of Spanish Legal Decrees and N
    67443, -- 2509.24832 SemShareKV: Efficient KVCache Sharing for Semantically Similar Prompts via Token
    67631, -- 2502.13838 Generative Video Semantic Communication via Multimodal Semantic Fusion with Larg
    67654, -- 2509.22812 EditGRPO: Reinforcement Learning with Post -Rollout Edits for Clinically Accurat
    67783, -- 2509.21269 LLMTrace: A Corpus for Classification and Fine-Grained Localization of AI-Writte
    67834, -- 2509.20823 CaTS-Bench: Can Language Models Describe Numeric Time Series?
    67892, -- 2509.22715 TRUEBench: Can LLM Response Meet Real-world Constraints as Productivity Assistan
    67910, -- 2509.19580 LLMs4All: A Review on Large Language Models for Research and Applications in Aca
    67938, -- 2509.19088 Digital Twins as Funhouse Mirrors: Five Key Distortions
    67965, -- 2509.18658 Analyzing Uncertainty of LLM-as-a-Judge: Interval Evaluations with Conformal Pre
    68054, -- 2509.16990 Advancing Speech Understanding in Speech-Aware Language Models with GRPO
    68075, -- 2509.16720 Time to Revist Exact Match
    68086, -- 2509.16628 Enhancing Scientific Visual Question Answering via Vision-Caption aware Supervis
    68093, -- 2509.16538 Advancing Reference-free Evaluation of Video Captions with Factual Analysis
    68115, -- 2509.16326 HARE: an entity and relation centric evaluation framework for histopathology rep
    68248, -- 2509.14230 NIRVANA: Structured pruning reimagined for large language models compression
    68303, -- 2509.13480 Gender-Neutral Rewriting in Italian: Models, Approaches, and Trade-offs
    68311, -- 2509.13255 ResidualViT for Efficient Temporally Dense Video Encoding
    68376, -- 2509.11860 MOOM: Maintenance, Organization and Optimization of Memory in Ultra-Long Role-Pl
    68390, -- 2509.11698 CoachMe: Decoding Sport Elements with a Reference-Based Coaching Instruction Gen
    68479, -- 2509.09651 Retrieval-Augmented Generation for Reliable Interpretation of Radio Regulations
    68508, -- 2509.09101 TigerCoder: A Novel Suite of LLMs for Code Generation in Bangla
    68533, -- 2509.09731 Benchmarking Vision-Language Models on Chinese Ancient Documents: From OCR to Kn
    68637, -- 2509.06401 Do LLMs exhibit the same commonsense capabilities across languages?
    68684, -- 2509.05440 Direct-Scoring NLG Evaluators Can Use Pairwise Comparisons Too
    68734, -- 2509.04183 MAGneT: Coordinated Multi-Agent Generation of Synthetic Multi-Turn Mental Health
    68755, -- 2509.05362 AI-in-the-Loop: Privacy Preserving Real-Time Scam Detection and Conversational S
    68785, -- 2509.03234 TeRA: Vector-based Random Tensor Network for High-Rank Adaptation of Large Langu
    68897, -- 2509.01053 A Dynamic Fusion Model for Consistent Crisis Response
    68921, -- 2509.04484 The Good, the Bad and the Constructive: Automatically Measuring Peer Review's Ut
    68969, -- 2509.00285 OpinioRAG: Towards Generating User-Centric Opinion Highlights from Large-scale O
    68974, -- 2509.04472 RECAP: REwriting Conversations for Intent Understanding in Agentic Planning
    69031, -- 2508.20867 MSRS: Evaluating Multi-Source Retrieval-Augmented Generation
    69062, -- 2508.20312 ELIXIR: Efficient and LIghtweight model for eXplaIning Recommendations
    69102, -- 2508.19724 NLKI: A lightweight Natural Language Knowledge Integration Framework for Improvi
    69173, -- 2508.18646 Beyond Benchmark: LLMs Evaluation with an Anthropomorphic and Value-oriented Roa
    69191, -- 2508.18260 MIRAGE: Scaling Test-Time Inference with Parallel Graph-Retrieval-Augmented Reas
    69247, -- 2508.17444 MahaParaphrase: A Marathi Paraphrase Detection Corpus and BERT-based Models
    69272, -- 2508.17184 Towards Alignment-Centric Paradigm: A Survey of Instruction Tuning in Large Lang
    69277, -- 2508.17117 PlantVillageVQA: A Visual Question Answering Dataset for Benchmarking Vision-Lan
    69311, -- 2508.16431 Cetvel: A Unified Benchmark for Evaluating Language Understanding, Generation an
    69371, -- 2508.15396 Attribution, Citation, and Quotation: A Survey of Evidence-based Text Generation
    69387, -- 2508.15189 SurgWound-Bench: A Benchmark for Surgical Wound Diagnosis
    69392, -- 2508.07592 IBPS: Indian Bail Prediction System
    69424, -- 2508.15851 DocHop-QA: Towards Multi-Hop Reasoning over Multimodal Document Collections
    69467, -- 2508.13816 The illusion of a perfect metric: Why evaluating AI's words is harder than it lo
    69525, -- 2508.12957 Breaking Reward Collapse: Adaptive Reinforcement for Open-ended Medical Reasonin
    69559, -- 2508.12491 Cost-Aware Contrastive Routing for LLMs
    69578, -- 2508.12291 RadarQA: Multi-modal Quality Analysis of Weather Radar Forecasts
    69589, -- 2508.12108 VELVET-Med: Vision and Efficient Language Pre-training for Volumetric Imaging Ta
    69592, -- 2508.12026 Bongard-RWR+: Real-World Representations of Fine-Grained Concepts in Bongard Pro
    69600, -- 2508.15813 SCOPE: A Generative Approach for LLM Prompt Compression
    69644, -- 2508.11011 Are Large Pre-trained Vision Language Models Effective Construction Safety Inspe
    69681, -- 2508.10421 Evaluating LLMs on Chinese Idiom Translation
    69710, -- 2508.10161 LaajMeter: A Framework for LaaJ Evaluation
    69766, -- 2508.09442 Shadow in the Cache: Unveiling and Mitigating Privacy Risks of KV-cache in LLM I
    69797, -- 2508.09240 NEFMind: Parameter-Efficient Fine-Tuning of Open-Source LLMs for Telecom APIs Au
    69948, -- 2508.06763 SafePLUG: Empowering Multimodal LLMs with Pixel-Level Insight and Temporal Groun
    69950, -- 2504.05228 NoveltyBench: Evaluating Language Models for Humanlike Diversity
    69974, -- 2508.06328 M2IO-R1: An Efficient RL-Enhanced Reasoning Framework for Multimodal Retrieval A
    70073, -- 2508.05019 Skin-SOAP: A Weakly Supervised Framework for Generating Structured SOAP Notes
    70200, -- 2508.03399 ReDSM5: A Reddit Dataset for DSM-5 Depression Detection
    70249, -- 2508.02808 Clinically Grounded Agent-based Report Evaluation: An Interpretable Metric for R
    70290, -- 2508.02184 CAAD: Context-Aware Adaptive Decoding for Truthful Text Generation
    70297, -- 2508.08287 Sacred or Synthetic? Evaluating LLM Reliability and Abstention for Religious Que
    70352, -- 2508.01491 The Homogenizing Effect of Large Language Models on Human Expression and Thought
    70360, -- 2508.01401 MedSynth: Realistic, Synthetic Medical Dialogue-Note Pairs
    70528, -- 2507.22752 CUS-QA: Local-Knowledge-Oriented Open-Ended Question Answering Dataset
    70529, -- 2507.22744 Reducing Hallucinations in Summarization via Reinforcement Learning with Entity
    70568, -- 2507.22047 The Interspeech 2025 Speech Accessibility Project Challenge
    70590, -- 2507.21815 HRIPBench: Benchmarking LLMs in Harm Reduction Information Provision to Support
    70630, -- 2507.20917 MediQAl: A French Medical Question Answering Dataset for Knowledge and Reasoning
    70634, -- 2507.20849 Latent Inter-User Difference Modeling for LLM Personalization
    70664, -- 2507.21188 Embeddings to Diagnosis: Latent Fragility under Agentic Perturbations in Clinica
    70669, -- 2507.20301 Advancing Dialectal Arabic to Modern Standard Arabic Machine Translation
    70684, -- 2507.19995 VLQA: The First Comprehensive, Large, and High-Quality Vietnamese Dataset for Le
    71040, -- 2507.12911 LaViPlan : Language-Guided Visual Path Planning with RLVR
    71141, -- 2507.10419 Multiple Choice Learning of Low Rank Adapters for Language Modeling
    71187, -- 2507.09638 Can Group Relative Policy Optimization Improve Thai Legal Reasoning and Question
    71215, -- 2507.09188 Retrieval-Augmented Recommendation Explanation Generation with Hierarchical Aggr
    71334, -- 2507.06090 Nyay-Darpan: Enhancing Decision Making Through Summarization and Case Retrieval
    71383, -- 2507.04815 From Vision To Language through Graph of Events in Space and Time: An Explainabl
    71459, -- 2507.03617 EMERGE: A Benchmark for Updating Knowledge Graphs with Emerging Textual Knowledg
    71460, -- 2507.03224 RCA Copilot: Transforming Network Data into Actionable Insights via Large Langua
    71465, -- 2507.03152 Expert-level validation of AI-generated medical text with scalable language mode
    71496, -- 2507.02145 Reasoning or Not? A Comprehensive Evaluation of Reasoning LLMs for Dialogue Summ
    71537, -- 2507.01255 AIGVE-MACS: Unified Multi-Aspect Commenting and Scoring Model for AI-Generated V
    71597, -- 2506.24086 MotionGPT3: Human Motion as a Second Modality
    71660, -- 2507.02948 DriveMRP: Enhancing Vision-Language Models with Synthetic Motion Data for Motion
    71731, -- 2506.20100 MIRAGE: A Benchmark for Multimodal Information-Seeking and Reasoning in Agricult
    71773, -- 2506.18819 RWESummary: A Framework and Test for Choosing Large Language Models to Summarize
    71867, -- 2506.21601 Hierarchical Patch Compression for ColPali: Efficient Multi-Vector Document Retr
    71946, -- 2506.13639 An Empirical Study of LLM-as-a-Judge: How Design Choices Impact Evaluation Relia
    72061, -- 2506.11155 Evaluating Multimodal Large Language Models on Video Captioning via Monte Carlo
    72070, -- 2506.09672 Is Fine-Tuning an Effective Solution? Reassessing Knowledge Editing for Unstruct
    72074, -- 2506.11147 3D-RAD: A Comprehensive 3D Radiology Med-VQA Dataset with Multi-Temporal Analysi
    72112, -- 2506.08364 Structure-Augmented Reasoning Generation
    72121, -- 2506.07851 Learning to Focus: Causal Attention Distillation via Gradient-Guided Token Pruni
    72148, -- 2506.07424 Plug-in and Fine-tuning: Bridging the Gap between Small Language Models and Larg
    72305, -- 2506.03800 STELLA: Towards Protein Function Prediction with Multimodal LLMs Integrating Seq
    72320, -- 2506.03067 EDITOR: Effective and Interpretable Prompt Inversion for Text-to-Image Diffusion
    72334, -- 2506.02845 Go Beyond Earth: Understanding Human Actions and Scenes in Microgravity Environm
    72344, -- 2506.02544 CoRe-MMRAG: Cross-Source Knowledge Reconciliation for Multimodal RAG
    72351, -- 2506.02461 XToM: Exploring the Multilingual Theory of Mind for Large Language Models
    72356, -- 2506.02368 NextQuill: Causal Preference Modeling for Enhancing LLM Personalization
    72377, -- 2506.02095 Cycle Consistency as Reward: Learning Image-Text Alignment without Human Prefere
    72444, -- 2506.00958 Speaking Beyond Language: A Large-Scale Multimodal Dataset for Learning Nonverba
    72454, -- 2506.00815 Chandomitra: Towards Generating Structured Sanskrit Poetry from Natural Language
    72482, -- 2506.00448 Fact-Controlled Diagnosis of Hallucinations in Medical Text Summarization
    72501, -- 2506.00245 Beyond Semantic Entropy: Boosting LLM Uncertainty Quantification with Pairwise S
    72505, -- 2505.24826 LegalEval-Q: A New Benchmark for The Quality Evaluation of LLM-Generated Legal T
    72520, -- 2505.24223 Automated Structured Radiology Report Generation
    72528, -- 2505.24063 TCM-Ladder: A Benchmark for Multimodal Question Answering on Traditional Chinese
    72538, -- 2505.23628 AutoSchemaKG: Autonomous Knowledge Graph Construction through Dynamic Schema Ind
    72563, -- 2505.23174 Map&Make: Schema Guided Text to Table Generation
    72580, -- 2505.22304 CADReview: Automatically Reviewing CAD Programs with Error Detection and Correct
    72671, -- 2505.20826 AdParaphrase v2.0: Generating Attractive Ad Texts Using a Preference-Annotated P
    72687, -- 2505.20633 Test-Time Learning for Large Language Models
    72727, -- 2505.19538 DoctorRAG: Medical RAG Fusing Knowledge with Patient Analogy through Textual Gra
    72748, -- 2505.20346 PDFBench: A Benchmark for De novo Protein Design from Function
    72828, -- 2505.17433 MemeReaCon: Probing Contextual Meme Understanding in Large Vision-Language Model
    72830, -- 2505.17406 Misaligning Reasoning with Answers -- A Framework for Assessing LLM CoT Robustne
    73016, -- 2505.11838 RVTBench: A Benchmark for Visual Reasoning Tasks
    73037, -- 2505.11194 Prot2Text-V2: Protein Function Prediction with Multimodal Contrastive Alignment
    73070, -- 2505.11541 MorphMark: Flexible Adaptive Watermarking for Large Language Models
    73100, -- 2505.07453 How well do LLMs reason over tabular data, really?
    73151, -- 2505.04680 Retrieval Augmented Generation Evaluation for Health Documents
    73165, -- 2505.04016 SLOT: Structuring the Output of Large Language Models
    73205, -- 2505.01862 ReLI: A Language-Agnostic Approach to Human-Robot Interaction
    73215, -- 2505.01199 CaReAQA: A Cardiac and Respiratory Audio Question Answering Model for Open-Ended
    73308, -- 2504.18838 Toward Generalizable Evaluation in the LLM Era: A Survey Beyond Benchmarks
    73431, -- 2502.06193 Can LLMs Replace Human Evaluators? An Empirical Study of LLM-as-a-Judge in Softw
    73455, -- 2504.13615 Long-context Non-factoid Question Answering in Indic Languages
    73573, -- 2504.08207 DRAFT-ing Architectural Design Decisions using LLMs
    73579, -- 2504.08024 Summarizing Speech: A Comprehensive Survey
    73777, -- 2504.02867 Multi-Agent LLM Judge: automatic personalized LLM judge design for evaluating na
    73920, -- 2503.17783 Energy-Aware LLMs: A step towards sustainable AI for downstream applications
    73934, -- 2503.17039 Summarization Metrics for Spanish and Basque: Do Automatic Scores and LLM-Judges
    74035, -- 2503.12908 HICD: Hallucination-Inducing via Attention Dispersion for Contrastive Decoding t
    74073, -- 2503.12029 Is Multi-Agent Debate (MAD) the Silver Bullet? An Empirical Analysis of MAD in C
    74148, -- 2503.08662 Exploring the Word Sense Disambiguation Capabilities of Large Language Models
    74174, -- 2503.08057 Odysseus Navigates the Sirens' Song: Dynamic Focus Decoding for Factual and Dive
    74319, -- 2503.02034 Abn-BLIP: Abnormality-aligned Bootstrapping Language-Image Pre-training for Pulm
    74337, -- 2503.01478 SePer: Measure Retrieval Utility Through The Lens Of Semantic Perplexity Reducti
    74352, -- 2503.01385 Q-NL Verifier: Leveraging Synthetic Data for Robust Knowledge Graph Question Ans
    74377, -- 2503.00231 Jawaher: A Multidialectal Dataset of Arabic Proverbs for LLM Benchmarking
    74517, -- 2502.16550 PropXplain: Can LLMs Enable Explainable Propaganda Detection?
    74540, -- 2504.05317 On Synthesizing Data for Context Attribution in Question Answering
    74601, -- 2502.13031 HPSS: Heuristic Prompting Strategy Search for LLM Evaluators
    74620, -- 2502.12586 G-Refer: Graph Retrieval-Augmented Large Language Model for Explainable Recommen
    74631, -- 2502.12375 UltraGen: Extremely Fine-grained Controllable Generation via Attribute Reconstru
    74649, -- 2502.11721 Enhancing Recommendation Explanations through User-Centric Refinement
    74662, -- 2502.11371 RAG vs. GraphRAG: A Systematic Evaluation and Key Insights
    74683, -- 2502.10374 Robustness tests for biomedical foundation models should tailor to specification
    74725, -- 2502.09670 The Science of Evaluating Foundation Models
    74841, -- 2502.05087 Mitigating Unintended Memorization with LoRA in Federated Learning for LLMs
    74891, -- 2502.03333 RadVLM: A Multitask Conversational Vision-Language Model for Radiology
    75080, -- 2501.15595 SedarEval: Automated Evaluation using Self-Adaptive Rubrics
    75179, -- 2501.09367 PICE: A Semantic-Driven Progressive Inference System for LLM Serving in Cloud-Ed
    75189, -- 2501.08613 Assessing the Sensitivity and Alignment of FOL Closeness Metrics
    75350, -- 2412.19442 A Survey on Large Language Model Acceleration based on KV Cache Management
    75439, -- 2412.13091 LMUnit: Fine-grained Evaluation with Natural Language Unit Tests
    75561, -- 2405.15329 DnA-Eval: Enhancing Large Language Model Evaluation through Decomposition and Ag
    75572, -- 2412.06827 Enhancing LLMs for Physics Problem-Solving using Reinforcement Learning with Hum
    75575, -- 2412.05184 QueEn: A Large Language Model for Quechua-English Translation
    75702, -- 2407.05399 IL-TUR: Benchmark for Indian Legal Text Understanding and Reasoning
    75841, -- 2411.04981 Enhancing Reverse Engineering: Investigating and Benchmarking Large Language Mod
    75896, -- 2411.00300 Rationale-Guided Retrieval Augmented Generation for Medical Question Answering
    75900, -- 2411.02429 IdeaBench: Benchmarking Large Language Models for Research Idea Generation
    75959, -- 2410.19198 MAP: Multi-Human-Value Alignment Palette
    75970, -- 2410.19109 RSA-Control: A Pragmatics-Grounded Lightweight Controllable Text Generation Fram
    75985, -- 2410.16623 MotionGlot: A Multi-Embodied Motion Generation Model
    76002, -- 2410.15504 FlexDoc: Flexible Document Adaptation through Optimizing both Content and Layout
    76005, -- 2410.15393 CalibraEval: Calibrating Prediction Distribution to Mitigate Selection Bias in L
    76008, -- 2410.14991 ChitroJera: A Regionally Relevant Visual Question Answering Dataset for Bangla
    76167, -- 2410.03198 PersoBench: Benchmarking Personalized Response Generation in Large Language Mode
    76189, -- 2410.01945 LFQA-E: Carefully Benchmarking Long-form QA Evaluation
    76454, -- 2409.15316 Towards Social AI: A Survey on Understanding Social Interactions
    76776, -- 2407.08101 What to Say and When to Say it: Live Fitness Coaching as a Testbed for Situated
    76810, -- 2407.04121 Hallucination Detection: Robustly Discerning Reliable Answers in Large Language
    76908, -- 2406.16739 Agent-Driven Automatic Software Improvement
    76983, -- 2406.11097 InstructCMP: Length Control in Sentence Compression through Instruction-based La
    77129, -- 2406.00258 Artemis: Towards Referential Understanding in Complex Videos
    77159, -- 2405.18915 Towards Better Chain-of-Thought: A Reflection on Effectiveness and Faithfulness
    77212, -- 2405.09935 DEBATE: Devil's Advocate-Based Assessment and Text Evaluation
    77264, -- 2405.10255 When LLMs step into the 3D World: A Survey and Meta-Analysis of 3D Tasks via Mul
    77359, -- 2404.18031 Quality Estimation with k-nearest Neighbors and Automatic Evaluation for Model-s
    77401, -- 2404.13370 Movie101v2: Improved Movie Narration Benchmark
    77431, -- 2404.09982 Memory Sharing for Large Language Model based Agents
    77449, -- 2404.08031 Latent Guard: a Safety Framework for Text-to-image Generation
    77510, -- 2404.02138 Topic-Based Watermarks for Large Language Models
    77564, -- 2403.18572 ACES: Evaluating Automated Audio Captioning Models on the Semantics of Sounds
    77603, -- 2403.13681 Ayn: A Tiny yet Competitive Indian Legal Language Model Pretrained from Scratch
    77716, -- 2403.14666 SyllabusQA: A Course Logistics Question Answering Dataset
    77767, -- 2402.15754 HD-Eval: Aligning Large Language Model Evaluators Through Hierarchical Criteria
    77768, -- 2402.15422 A Data-Centric Approach To Generate Faithful and High Quality Patient Summaries
    77772, -- 2402.14531 Should We Respect LLMs? A Cross-Lingual Study on the Influence of Prompt Politen
    77908, -- 2401.13307 ChatterBox: Multi-round Multimodal Referring and Grounding
    77945, -- 2401.08358 Hallucination Detection and Hallucination Mitigation: An Investigation
    77961, -- 2401.06945 Knowledge-Centric Templatic Views of Documents
    77968, -- 2401.05949 Universal Vulnerabilities in Large Language Models: Backdoor Attacks for In-cont
    78116, -- 2312.07398 LLMEval: A Preliminary Study on How to Evaluate Large Language Models
    78127, -- 2312.05979 NovaCOMET: Open Commonsense Foundation Models with Symbolic Knowledge Distillati
    78348, -- 2310.13345 An LLM can Fool Itself: A Prompt-Based Adversarial Attack
    78394, -- 2310.07170 PHALM: Building a Knowledge Graph from Scratch by Prompting Humans and a Languag
    78405, -- 2310.05793 DiffuSeq-v2: Bridging Discrete and Continuous Text Spaces for Accelerated Seq2Se
    78628, -- 2308.10526 UbiPhysio: Support Daily Functioning, Fitness, and Rehabilitation with Action Un
    78655, -- 2308.05696 A Preliminary Study of the Intrinsic Relationship between Complexity and Alignme
    78978, -- 2305.16626 Evaluation of Question Generation Needs More References
    79016, -- 2305.12532 Multilingual Simplification of Medical Texts
    79032, -- 2305.10307 FACE: Evaluating Natural Language Generation with Fourier Analysis of Cross-Entr
    79159, -- 2304.03216 On the Pareto Front of Multilingual Neural Machine Translation
    79203, -- 2303.14576 Automatic Generation of Multiple-Choice Questions
    79422, -- 2301.09043 CodeScore: Evaluating Code Generation by Learning Code Execution
    79486, -- 2212.08785 Importance of Synthesizing High-quality Data for Text-to-SQL Parsing
    79551, -- 2211.11902 Evaluating the Knowledge Dependency of Questions
    79686, -- 2210.03256 Not another Negation Benchmark: The NaN-NLI Test Suite for Sub-clausal Negation
    79951, -- 2205.12487 End-to-End Multimodal Fact-Checking and Explanation Generation: A Challenging Da
    79990, -- 2205.05805 SubER: A Metric for Automatic Evaluation of Subtitle Quality
    80313, -- 2010.05953 COMET-ATOMIC 2020: On Symbolic and Neural Commonsense Knowledge Graphs
    80333, -- 2112.03572 Question Answering Survey: Directions, Challenges, Datasets, Evaluation Matrices
    80646, -- 2106.12978 Unsupervised Topic Segmentation of Meetings with BERT Embeddings
    80688, -- 2106.03706 A Comprehensive Assessment of Dialog Evaluation Metrics
    80796, -- 2104.00369 FeTaQA: Free-form Table Question Answering
    81046, -- 2010.12885 Unsupervised Paraphrasing with Pretrained Language Models
    81328, -- 2005.07493 History for Visual Dialog: Do we really need it?
    81663, -- 1907.09358 Trends in Integration of Vision and Language Research: A Survey of Tasks, Datase
    82870, -- 2605.04523 RaguTeam at SemEval-2026 Task 8: Meno and Friends in a Judge-Orchestrated LLM En
    82915, -- 2605.07748 TextLDM: Language Modeling with Continuous Latent Diffusion
    83140, -- 2605.12925 AgentLens: Revealing The Lucky Pass Problem in SWE-Agent Evaluation
    83146, -- 2605.13481 PersonalAI 2.0: Enhancing knowledge graph traversal/retrieval with planning mech
    83368, -- 2605.18661 AI for Auto-Research: Roadmap & User Guide
    83534, -- 2605.21463 Mem-π: Adaptive Memory through Learning When and What to Generate
    83709, -- 2604.24052 QEVA: A Reference-Free Evaluation Metric for Narrative Video Summarization with
    83813, -- 2605.26045 Confidence and Calibration of Activation Oracles for Reliable Interpretation of
    83827, -- 2503.08600 NSF-SciFy: Mining the NSF Awards Database for Scientific Claims
    83880, -- 2605.27908 ESC-Skills: Discovering and Self-Evolving Skills for Emotional Support Conversat
    84041, -- 2506.13130 ZINA: Multimodal Fine-grained Hallucination Detection and Editing
    84092, -- 2508.21451 MM-SeR: Multimodal Self-Refinement for Lightweight Image Captioning
    84115, -- 2510.00430 PromptLoop: Plug-and-Play Prompt Refinement via Latent Feedback for Diffusion Mo
    84143, -- 2510.27680 PETAR: Localized Findings Generation with Mask-Aware Vision-Language Modeling fo
    84186, -- 2511.15316 What Your Features Reveal: Data-Efficient Black-Box Feature Inversion Attack for
    84268, -- 2511.21732 HUMORCHAIN: Theory-Guided Multi-Stage Reasoning for Interpretable Multimodal Hum
    84284, -- 2511.23055 MindPower: Enabling Theory-of-Mind Reasoning in VLM-based Embodied Agents
    84754, -- 2603.04908 AdaIAT: Adaptively Increasing Attention to Generated Text to Alleviate Hallucina
    85027, -- 2603.21484 Which Concepts to Forget and How to Refuse? Decomposing Concepts for Continual U
    85156, -- 2603.26938 From 3D Pose to Prose: Biomechanics-Grounded Vision-Language Coaching
    85315, -- 2604.08125 PolySLGen: Online Multimodal Speaking-Listening Reaction Generation in Polyadic
    86471, -- 2502.19110 Conformal Linguistic Calibration: Trading-off between Factuality and Specificity
    86601, -- 2510.10487 Towards Self-Refinement of Vision-Language Models with Triangular Consistency
    86909, -- 2410.01508 Disentangling Latent Shifts of In-Context Learning with Weak Supervision
    87339, -- 2506.10364 Can We Infer Confidential Properties of Training Data from LLMs?
    87603, -- 2507.19850 FineMotion: A Dataset and Benchmark with both Spatial and Temporal Annotation fo
    88323, -- 2412.19920 Not all Views are Created Equal: Analyzing Viewpoint Instabilities in Vision Fou
    88342, -- 2509.12145 Open-ended Hierarchical Streaming Video Understanding with Vision Language Model
    88585, -- 2506.07947 Statistical Hypothesis Testing for Auditing Robustness in Language Models
    88662, -- 2506.07440 Federated In-Context Learning: Iterative Refinement for Improved Answer Quality
    88664, -- 2507.10539 Graph World Model
    88701, -- 2506.21602 BiMark: Unbiased Multilayer Watermarking for Large Language Models
    88755, -- 2502.01179 Joint Localization and Activation Editing for Low-Resource Fine-Tuning
    88801, -- 2412.08559 Underestimated Privacy Risks for Minority Populations in Large Language Model Un
    89099, -- 2502.07616 Tractable Transformers for Flexible Conditional Generation
    89154, -- 2506.05502 StealthInk: A Multi-bit and Stealthy Watermark for Large Language Models
    89170, -- 2412.06461 Ranked from Within: Ranking Large Multimodal Models Without Labels
    89263, -- 2410.10112 Can We Predict Performance of Large Models across Vision-Language Tasks?
    89821, -- 2502.19255 Can RLHF be More Efficient with Imperfect Reward Models? A Policy Coverage Persp
    90312, -- 2504.21435 SeriesBench: A Benchmark for Narrative-Driven Drama Series Understanding
    90446, -- 2409.18127 EgoLM: Multi-Modal Language Model of Egocentric Motions
    90619, -- 2412.03178 Towards Understanding and Quantifying Uncertainty for Text-to-Image Generation
    90694, -- 2403.12922 Contextual AD Narration with Interleaved Multimodal Sequence
    90804, -- 2504.08449 Ego4o: Egocentric Human Motion Capture and Understanding from Multi-Modal Input
    90852, -- 2411.15247 Reward Fine-Tuning Two-Step Diffusion Models via Learning Differentiable Latent-
    91117, -- 2410.08474 SPORTU: A Comprehensive Sports Understanding Benchmark for Multimodal Large Lang
    91136, -- 2406.04046 ActionReasoningBench: Reasoning about Actions with and without Ramification Cons
    91171, -- 2402.17840 Follow My Instruction and Spill the Beans: Scalable Data Extraction from Retriev
    91185, -- 2410.19230 Humanizing the Machine: Proxy Attacks to Mislead LLM Detectors
    91229, -- 2411.07127 Benchmarking LLMs' Judgments with No Gold Standard
    91380, -- 2410.02603 Agents' Room: Narrative Generation through Multi-step Collaboration
    91570, -- 2407.14985 Generalization v.s. Memorization: Tracing Language Models’ Capabilities Back to
    91968, -- 2502.21290 Contextualizing biological perturbation experiments through language
    92142, -- 2410.10135 FormalAlign: Automated Alignment Evaluation for Autoformalization
    92182, -- 2410.08437 AutoEval: Autonomous Evaluation of LLMs for Truth Maintenance and Reasoning Task
    92203, -- 2503.05318 Uncertainty-Aware Decoding with Minimum Bayes Risk
    92268, -- 2503.13500 Long-horizon Visual Instruction Generation with Logic and Attribute Self-reflect
    92419, -- 2411.05172 ImpScore: A Learnable Metric For Quantifying The Implicitness Level of Sentences
    92480, -- 2606.02754 Ψ-Bench: Evaluating Persona-Sensitive Influencing in Persuasive Dialogues
    92633, -- 2603.02787 Rethinking Code Similarity for Automated Algorithm Design with LLMs
    92806, -- 2507.03373 TSM-Bench: Detecting LLM-Generated Text in Real-World Wikipedia Editing Practice
    92848, -- 2604.07569 Learning is Forgetting; LLM Training As Lossy Compression
    93214, -- 2503.02623 Rewarding Doubt: A Reinforcement Learning Approach to Calibrated Confidence Expr
    93281, -- 2509.22258 Beyond Classification Accuracy: Neural-MedBench and the Need for Deeper Reasonin
    93360, -- 2505.17779 U2-BENCH: Benchmarking Large Vision-Language Models on Ultrasound Understanding
    93362, -- 2411.16821 Logit‑KL Flow Matching: Non‑Autoregressive Text Generation via Sampling‑Hybrid I
    93454, -- 2505.11839 On the Eligibility of LLMs for Counterfactual Reasoning: A Decompositional Study
    93455, -- 2502.09667 Summaries as Centroids for Interpretable and Scalable Text Clustering
    93502, -- 2601.19503 GradPruner: Gradient-guided Layer Pruning Enabling Efficient Fine-Tuning and Inf
    93530, -- 2505.13531 AdAEM: An Adaptively and Automated Extensible Measurement of LLMs' Value Differe
    93607, -- 2506.14003 Unlearning Isn't Invisible: Detecting Unlearning Traces in LLMs from Model Outpu
    93700, -- 2509.23487 Temporal Generalization: A Reality Check
    93719, -- 2511.05784 DRAGON: Guard LLM Unlearning in Context via Negative Detection and Reasoning
    93841, -- 2510.10467 AnyBCQ: Hardware Efficient Flexible Binary-Coded Quantization for Multi-Precisio
    93859, -- 2510.02279 Addressing Pitfalls in the Evaluation of Uncertainty Estimation Methods for Natu
    94031, -- 2601.05144 Distilling the Thought, Watermarking the Answer: A Principle Semantic Guided Wat
    94136, -- 2602.15669 PERSONA: Dynamic and Compositional Inference-Time Personality Control via Activa
    94281, -- 2510.14459 Holdout-Loss-Based Data Selection for LLM Finetuning via In-Context Learning
    94411, -- 2510.19208 DiSRouter: Distributed Self-Routing for LLM Selections
    94487, -- 2511.19473 WavefrontDiffusion: Dynamic Decoding Schedule for Improved Reasoning
    94496, -- 2509.25774 PCPO: Proportionate Credit Policy Optimization for Preference Alignment of Image
    94551, -- 2602.04755 When Silence Is Golden: Can LLMs Learn to Abstain in Temporal QA and Beyond?
    94569, -- 2510.10231 Semantic Visual Anomaly Detection and Reasoning in AI-Generated Images
    94585, -- 2507.03267 GDGB: A Benchmark for Generative Dynamic Text-Attributed Graph Learning
    94597, -- 2509.25178 GHOST: Hallucination-Inducing Image Generation for Multimodal LLMs
    94655, -- 2509.24048 Analyzing and Evaluating Unbiased Language Model Watermark
    94681, -- 2509.24043 An Ensemble Framework for Unbiased Language Model Watermarking
    94877, -- 2601.20447 Assembling the Mind's Mosaic: Towards EEG Semantic Intent Decoding
    97223, -- 2506.20097 PSALM-V: Automating Symbolic Planning in Interactive Visual Environments with La
    97981, -- 2605.29430 Towards Human-Like Interactive Speech Recognition With Agentic Correction and Se
    98024, -- 2606.08481 PIPE-Cypher: Automatic Enterprise Benchmark Generation for Text-to-Cypher System
    98661, -- 2606.18381 SproutRAG: Attention-Guided Tree Search with Progressive Embeddings for Long-Doc
    98662, -- 2606.18508 MCompassRAG: Topic Metadata as a Semantic Compass for Paragraph-Level Retrieval
    98807, -- 2606.24937 The Hitchhiker's Guide to Agentic AI: From Foundations to Systems
    99006, -- 2606.30319 BrainJanus: A Unified Model for Understanding and Generation across Brain, Visio
    99035, -- 2606.31292 AtomiMed: Hierarchical Atomic Fact-Checking for Universal Clinical-Aware Medical
    99092, -- 2606.31825 Breaking Failure Cascades: Step-Aware Reinforcement Learning for Medical Multimo
    99110, -- 2310.02977 T$^3$Bench: Benchmarking Current Progress in Text-to-3D Generation
    99381, -- 2602.05353 AgentXRay: White-Boxing Agentic Systems via Workflow Reconstruction
    99403, -- 2606.12716 Does AI Reviewer See the Full Picture? Attacking and Defending Multimodal Peer R
    99498, -- 2512.16904 How Good is Post-Hoc Watermarking With Language Model Rephrasing?
    99520, -- 2605.08116 The Safety-Aware Denoiser for Text Diffusion Models
    99740, -- 2605.00939 From Flat Facts to Sharp Hallucinations: Detecting Stubborn Errors via Gradient
    100723, -- 2606.14210 From Prompts to Responses: Dual-Sided Data Leakage and Defense in Split Large La
    100727, -- 2605.05407 PRISM: Perception Reasoning Interleaved for Sequential Decision Making.
    101138, -- 2606.10194 MMClima: A Framework for Multimodal Climate Science Data and Evaluation
    101159, -- 2605.09995 Annotations Mitigate Post-Training Mode Collapse
    101244, -- 2602.17149 TimeOmni-VL: Unified Models for Time Series Understanding and Generation
    101307, -- 2509.23571 Benchmarking LLM-Assisted Blue Teaming via Standardized Threat Hunting
    101428, -- 2605.00348 Block-wise Codeword Embedding for Reliable Multi-bit Text Watermarking
    101570, -- 2603.10351 Mitigating Translationese Bias in Multilingual LLM-as-a-Judge via Disentangled I
    101700, -- 2602.16610 Who can we trust? LLM-as-a-jury for Comparative Assessment
    101820, -- 2605.20291 Weasel: Out-of-Domain Generalization for Web Agents via Importance-Diversity Dat
    102160, -- 2606.07822 The ACUTE Protocol: Operationalizing Language Model Activations for Better Calib
    102507, -- 2601.22752 OSNIP: Balancing the Privacy-Utility-Efficiency Trilemma in LLM Inference via Ob
    102593, -- 2606.28393 Transition-Aware best-of-N sampling for Longitudinal Chest X-ray Reports
    102745, -- 2605.28836 No Reader Left Behind: Multi-Agent Summaries Everyone Can Understand
    102758, -- 2510.07858 Augur: Modeling Covariate Causal Associations in Time Series via Large Language
    102763, -- 2604.09066 Anchored Sliding Window: Toward Robust and Imperceptible Linguistic Steganograph
    102768, -- 2601.01530 EmoHarbor: Evaluating Personalized Emotional Support by Simulating the User’s In
    102776, -- 2504.21228 CachePrune: Teaching LLMs What Not to Follow via KV-Cache Editing
    102797, -- 2507.21934 Culinary Crossroads: A RAG Framework for Enhancing Diversity in Cross-Cultural R
    102808, -- 2604.05318 DIA-HARM: Dialectal Disparities in Harmful Content Detection Across 50 English D
    102822, -- 2604.27550 APPSI-139: A Parallel Corpus of English Application Privacy Policy Summarization
    102843, -- 2601.04932 GenProve: Learning to Generate Text with Fine-Grained Provenance
    102848, -- 2505.20740 MSEarth: A Multimodal Benchmark for Earth Science Phenomenon Discovery with MLLM
    102888, -- 2507.19081 Arg-LLaDA: Argument Summarization via Large Language Diffusion Models and Suffic
    102906, -- 2604.10717 Detecting RAG Extraction Attack via Dual-Path Runtime Integrity Game
    102944, -- 2604.21255 When Agents Look the Same: Quantifying Distillation-Induced Similarity in Tool-U
    103022, -- 2604.10520 ReFEree: Reference-Free and Fine-Grained Method for Evaluating Factual Consisten
    103030, -- 2604.05242 XMark: Reliable Multi-Bit Watermarking for LLM-Generated Texts
    103093, -- 2604.10470 From Query to Counsel: Structured Reasoning with a Multi-Agent Framework and Dat
    103100, -- 2507.21028 Multi-Agent-as-Judge: Aligning LLM-Agent-Based Automated Evaluation with Multi-D
    103101, -- 2512.23025 LENS: LLM-Enabled Narrative Synthesis for Mental Health by Aligning Multimodal S
    103128, -- 2509.26435 Adaptive Planning for Multi-Attribute Controllable Summarization with Monte Carl
    103161, -- 2605.26362 Why LLMs Hallucinate on Structured Knowledge: A Mechanistic Analysis of Reasonin
    103178, -- 2405.11597 Language Reconstruction with Brain Predictive Coding from fMRI Data
    103231, -- 2605.02916 From Synthesis to Clinical Assistance: A Strategy-Aware Agent Framework for Auti
    103246, -- 2604.05302 Right at My Level: A Unified Multilingual Framework for Proficiency-Aware Text S
    103249, -- 2509.00783 LegalChainReasoner: Grounding Criminal Judicial Opinion Generation via Structure
    103343, -- 2605.31136 Multilingual and Cross-Lingual Citation Needed Detection on Wikipedia for Lower-
    103372, -- 2604.24690 Can LLMs Act as Historians? Evaluating Historical Research Capabilities of LLMs
    103418, -- 2605.29712 Teaching Language Models to Check Grounded Claim Factuality with Human Test-Taki
    103439, -- 2604.27924 Can AI Be a Good Peer Reviewer? A Survey of Peer Review Process, Evaluation, and
    103440, -- 2510.14944 MetaBench: A Multi-task Benchmark for Assessing LLMs in Metabolomics
    103464, -- 2601.05184 Observations and Remedies for Large Language Model Bias in Self-Consuming Perfor
    103489, -- 2604.06711 Specializing Large Models for Oracle Bone Script Interpretation via Component-Gr
    103493, -- 2505.12808 Decentralized Arena: Towards Democratic and Scalable Automatic Evaluation of Lan
    103511, -- 2505.19667 LeCoDe: A Benchmark Dataset for Interactive Legal Consultation Dialogue Evaluati
    103533, -- 2601.16225 ES4R: Speech Encoding Based on Prepositive Affective Modeling for Empathetic Res
    103537, -- 2604.13598 Enhancing Reinforcement Learning for Radiology Report Generation with Evidence-a
    103548, -- 2604.21420 FairQE: Multi-Agent Framework for Mitigating Gender Bias in Translation Quality
    103554, -- 2604.08948 TaxPraBen: A Scalable Benchmark for Structured Evaluation of LLMs in Chinese Rea
    103566, -- 2604.12770 Teaching LLMs Human-Like Editing of Inappropriate Argumentation via Reinforcemen
    103644, -- 2601.18006 PEAR: Pairwise Evaluation for Automatic Relative Scoring in Machine Translation
    103646, -- 2504.07174 HypoEval: Hypothesis-Guided Evaluation for Natural Language Generation
    103680, -- 2601.19637 RATE: Reviewer Profiling and Annotation-free Training for Expertise Ranking in P
    103682, -- 2604.24001 CT-FineBench: A Diagnostic Fidelity Benchmark for Fine-Grained Evaluation of CT
    103704, -- 2605.17379 Learning Faster with Better Tokens: Parameter-Efficient Vocabulary Adaptation fo
    103714, -- 2505.21226 Why Do More Experts Fail? A Theoretical Analysis of Model Merging
    103716, -- 2604.06173 Evaluating Structure-Aware Retrieval and Safety in Statute-Centric Legal QA
    103717, -- 2604.18354 PRISMA: Preference-Reinforced Self-Training Approach for Interpretable Emotional
    103750, -- 2604.27398 Why Mean Pooling Works: Quantifying Second-Order Collapse in Text Embeddings
    104465, -- 2607.19011 Computational Humor with Multimodal LLMs: Methods, Datasets, Evaluation, and Cha
    105579, -- 2501.07525 RadAlign: Advancing Radiology Report Generation with Vision-Language Concept Ali
    105859, -- 2607.24176 Where Quality Breaks in Compressed Short-Text Generation: Staged Bottleneck Loca
    106110, -- 2605.17849 Generating Pretraining Tokens from Organic Data for Data-Bound Scaling
    106148, -- 2510.03527 Sample, Align, Synthesize: Graph-Based Response Synthesis with ConGrs
    106172, -- 2604.11628 Back to Basics: Let Conversational Agents Remember with Just Retrieval and Gener
    106370, -- 2605.02782 When Audio-Language Models Fail to Leverage Multimodal Context for Dysarthric Sp
    106629, -- 2512.21582 LLM-Free Image Captioning Evaluation in Reference-Flexible Settings
    106934, -- 2511.07498 Focusing on Language: Revealing and Exploiting Language Attention Heads in Multi
    107077, -- 2508.03127 Landsat30-AU: A Vision-Language Dataset for Australian Landsat Imagery
    107117, -- 2511.08916 HalluClean: A Unified Framework to Combat Hallucinations in LLMs
    107127, -- 2509.06586 Simulating Dispute Mediation with LLM-Based Agents for Legal Research
    107162, -- 2511.16985 ARQUSUMM: Argument-aware Quantitative Summarization of Online Conversations
    107174, -- 2411.17130 TechCoach: Towards Technical-Point-Aware Descriptive Action Coaching
    107212, -- 2511.16245 GazeInterpreter: Parsing Eye Gaze to Generate Eye-Body-Coordinated Narrations
    107217, -- 2511.09854 TermGPT: Multi-Level Contrastive Fine-Tuning for Terminology Adaptation in Legal
    107266, -- 2410.12265 Auto-PRE: An Automatic and Cost-Efficient Peer-Review Framework for Language Gen
    107470, -- 2511.17582 GateRA: Token-aware Modulation for Parameter-Efficient Fine-tuning
    107622, -- 2512.15614 Behavior Tokens Speak Louder: Disentangled Explainable Recommendation with Behav
    107639, -- 2512.14420 DISCODE: Distribution-Aware Score Decoder for Robust Automatic Evaluation of Ima
    107668, -- 2512.18554 Enhancing Medical Large Vision-Language Models via Alignment Distillation
    107793, -- 2504.09862 RadarLLM: Empowering Large Language Models to Understand Human Motion from Milli
    107851, -- 2512.21871 Bridging the Copyright Gap: Do Large Vision-Language Models Recognize and Respec
    107867, -- 2601.12126 UniMo: Unified Motion Generation and Understanding with Chain of Thought
    107873, -- 2411.17301 ReFINE: A Reward-Based Framework for Interpretable and Nuanced Evaluation of Rad
    108043, -- 2603.10034 A Principle-Driven Adaptive Policy for Group Cognitive Stimulation Dialogue for
    108221, -- 2512.00582 SatireDecoder: Visual Cascaded Decoupling for Enhancing Satirical Image Comprehe
    108225, -- 2410.09908 Beyond Adapter Retrieval: Latent Geometry-Preserving Composition via Sparse Task
    108527, -- 2503.19361 ImageSet2Text: Describing Sets of Images Through Text
    108663, -- 2608.03700 When Agents Learn to Be You: Benchmarking Privacy Leakage, Impersonation Risk, a
    108664, -- 2608.02218 PosterMELD: Multi-Agent Paper-to-Poster Generation for Controllable Design Diver
    108710, -- 2608.03756 LegalPincite: Multi-level Legal Information Retrieval Dataset
    108764, -- 2605.06105 Shallow Prefill, Deep Decoding: Efficient Long-Context Inference via Layer-Asymm
    108801, -- 2604.27695 EviMem: Evidence-Gap-Driven Iterative Retrieval for Long-Term Conversational Mem
    108910, -- 2512.12042 Benchmarking Contextual Understanding for In-Car Conversational Systems
    109008, -- 2608.04302 CLIP-CC-Bench: Evaluating Paragraph-Level Video Descriptions in Video-Language M
    109367, -- 2608.15984 A Plug-and-Play 2D Motion Interface for Real-World Motion Language Models
    109428, -- 2608.15869 Beyond Visual CoT: Internalized Visual Thinking for Proactive Video Reasoning
    109678, -- 2303.05977 Open-Ended Medical Visual Question Answering Through Prefix Tuning of Language M
    109813, -- 2608.23172 CaRGo-T: Causal Reasoning Graph-of-Thought improves Multimodal Humor Comprehensi
    109946, -- 2508.16870 JUDGEBERT: Assessing Legal Meaning Preservation Between Sentences
    110136, -- 2508.17670 CoCoA: Confidence- and Context-Aware Adaptive Decoding for Resolving Knowledge C
    110185, -- 2509.26011 RAGferee: Building Contextual Reward Models for Retrieval-Augmented Generation
    110276, -- 2509.01395 LLMs cannot spot math errors, even when allowed to peek into the solution
    110278, -- 2505.15792 Long-Form Information Alignment Evaluation Beyond Atomic Facts
    110301, -- 2509.20691 RedHerring Attack: Testing the Reliability of Attack Detection
    110304, -- 2510.00662 Facilitating Cognitive Accessibility with LLMs: A Multi-Task Approach to Easy-to
    110305, -- 2510.00280 ReEvalMed: Rethinking Medical Report Evaluation by Aligning Metrics with Real-Wo
    110348, -- 2505.19715 Graceful Forgetting in Generative Language Models
    110370, -- 2508.14723 Transplant Then Regenerate: A New Paradigm for Text Data Augmentation
    110372, -- 2509.18536 CCQA: Generating Question from Solution Can Improve Inference-Time Reasoning in
    110403, -- 2505.14195 Unraveling Interwoven Roles of Large Language Models in Authorship Privacy: Obfu
    110405, -- 2510.09332 FLRC: Fine-grained Low-Rank Compressor for Efficient LLM Inference
    110435, -- 2506.07642 TreeReview: A Dynamic Tree of Questions Framework for Deep and Efficient LLM-bas
    110466, -- 2502.10961 Graders Should Cheat: Privileged Information Enables Expert-Level Automated Eval
    110483, -- 2510.00567 Are Large Language Models Chronically Online Surfers? A Dataset for Chinese Inte
    110511, -- 2508.17610 Less Is More? Examining Fairness in Pruned Large Language Models for Summarising
    110528, -- 2509.24792 Evaluating Spatiotemporal Consistency in Automatically Generated Sewing Instruct
    110532, -- 2507.02353 OMS: On-the-fly, Multi-Objective, Self-Reflective Ad Keyword Generation via LLM
    110578, -- 2509.12451 Topic Coverage-based Demonstration Retrieval for In-Context Learning
    110579, -- 2505.16232 MuseScorer: Idea Originality Scoring At Scale
    110606, -- 2510.07892 Metric Calculating Benchmark: Code-Verifiable Complicate Instruction Following B
    110705, -- 2506.08700 ClimateViz: A Benchmark for Statistical Reasoning and Fact Verification on Scien
    110726, -- 2508.19221 Evaluating the Evaluators: Are readability metrics good measures of readability?
    110734, -- 2508.19578 Towards a Holistic and Automated Evaluation Framework for Multi-Level Comprehens
    110746, -- 2509.17921 Improving Zero-shot Sentence Decontextualisation with Content Selection and Plan
    110752, -- 2505.22430 RAG-Zeval: Enhancing RAG Responses Evaluator through End-to-End Reasoning and Ra
    110755, -- 2507.05129 SMART: Simulated Students Aligned with Item Response Theory for Question Difficu
    110771, -- 2507.05137 Interpretable Mnemonic Generation for Kanji Learning via Expectation-Maximizatio
    110852, -- 2509.12371 Morables: A Benchmark for Assessing Abstract Moral Reasoning in LLMs with Fables
    110857, -- 2502.10388 Aspect-Oriented Summarization for Psychiatric Short-Term Readmission Prediction
    110885, -- 2510.18288 BrailleLLM: Braille Instruction Tuning with Large Language Models for Braille Do
    110886, -- 2603.07294 MAviS: A Multimodal Conversational Assistant For Avian Species
    110893, -- 2509.16722 A Multi-Level Benchmark for Causal Language Understanding in Social Media Discou
    110906, -- 2505.05423 LiTransProQA: An LLM-based Literary Translation Evaluation Metric with Professio
    110942, -- 2510.17263 TaxoAlign: Scholarly Taxonomy Generation Using Language Models
    110955, -- 2505.23799 Estimating LLM Consistency: A User Baseline vs Surrogate Metrics
    110960, -- 2505.19345 PatentScore: Multi-dimensional Evaluation of LLM-Generated Patent Claims
    110962, -- 2502.02787 SimMark: A Robust Sentence-Level Similarity-Based Watermarking Algorithm for Lar
    110995, -- 2510.20700 Structure-Conditional Minimum Bayes Risk Decoding
    111004, -- 2502.14791 Rapid Word Learning Through Meta In-Context Learning
    111040, -- 2502.16923 A Systematic Survey of Automatic Prompt Optimization Techniques
    111045, -- 2402.17008 Benchmarking LLMs on Semantic Overlap Summarization
    111056, -- 2509.12677 Case-Based Decision-Theoretic Decoding with Quality Memories
    111076, -- 2510.17389 EduAdapt: A Question Answer Benchmark Dataset for Evaluating Grade-Level Adaptab
    111082, -- 2509.23395 Liaozhai through the Looking-Glass: On Paratextual Explicitation of Culture-Boun
    111096, -- 2509.24120 EduVidQA: Generating and Evaluating Long-form Answers to Student Questions based
    111097, -- 2508.08285 The Illusion of Progress: Re-evaluating Hallucination Detection in LLMs
    111119, -- 2509.10935 Introducing Spotlight: A Novel Approach for Generating Captivating Key Informati
    111120, -- 2503.00847 Argument Summarization and its Evaluation in the Era of Large Language Models
    111179, -- 2409.10883 Comparison-Based Automatic Evaluation for Meeting Summarization
    111705, -- 2505.20477 Robust fine-tuning of speech recognition models via model merging: application t
    111707, -- 2505.12991 Personalized Fine-Tuning with Controllable Synthetic Speech from LLM-Generated T
    112131, -- 2506.16528 Aligning ASR Evaluation with Human and LLM Judgments: Intelligibility Metrics Us
    112133, -- 2507.16456 An approach to measuring the performance of Automatic Speech Recognition(ASR) mo
    112473, -- 2404.14715 FineMatch: Aspect-based Fine-grained Image and Text Mismatch Detection and Corre
    112692, -- 2404.01700 MotionChain: Conversational Motion Controllers via Multimodal Prompts
    113789, -- 2510.08630 ExPO-HM: Learning to Explain-then-Detect for Hateful Meme Detection
    114104, -- 2609.06931 CARDEA: Auditable Reasoning Grounded in Spatial Evidence for End-to-End Coronary
    115039, -- 2409.05370 KARGEN: Knowledge-enhanced Automated Radiology Report Generation Using Large Lan
    115640, -- 2311.17435 MM-Narrator: Narrating Long-form Videos with Multimodal In-Context Learning
    115689, -- 2405.09713 SOK-Bench: A Situated Video Reasoning Benchmark with Aligned Open-World Knowledg
    115700, -- 2406.09489 Language-driven Grasp Detection
    115888, -- 2405.11483 MICap: A Unified Model for Identity-Aware Movie Descriptions
    116048, -- 2312.16051 Inter-X: Towards Versatile Human-Human Interaction Analysis
    116472, -- 2312.12416 Prompting Hard or Hardly Prompting: Prompt Inversion for Text-to-Image Diffusion
    116529, -- 2311.16468 AvatarGPT: All-in-One Framework for Motion Understanding Planning Generation and
    117762, -- 2606.28164 EchoSonar-R: A Multi-View Reasoning-Enabled Model for Disease Classification and
    117803, -- 2607.06909 Seeing What Matters: Lesion-Aware High-Resolution Patch Discovery and Fusion for
    118652, -- 2607.00159 Identifying and Resolving Pitfalls of Knowledge-Based VQA Benchmarks: Auditing,
    119214, -- 2607.11199 DynEval: Holistic Evaluations of T2I Generative Models in the Wild
    119542, -- 2608.18734 CL4D: Contrastive Language–4D Pretraining for Vision-Language Reasoning in Dynam
    119586, -- 2606.25445 C3-Bench: A Context-Aware Change Captioning Benchmark
    119697, -- 2607.01086 LongVQUBench: Benchmarking Long-Term Video Quality Understanding of Vision-Langu
    120141, -- 2504.05457 Taxonomy-Aware Evaluation of Vision-Language Models
    122009, -- 2609.15740 A Language-Guided Multimodal Foundation Model for Zero-Shot and Multi-Task Brain
    122034, -- 2609.19879 VākQA: A Benchmark and Evaluation Study for Telugu Spoken Factoid Question Answe
    122614, -- 2610.01428 Generalization Is Stability, Not Accuracy: Multi-Axis Evaluation of LLMs
    122852, -- 2610.08244 Sensor-Language-Action Models
    123047, -- 2610.09788 Judging in Latent Space: Efficient Generative Reward Modeling via Semantics-Pres
    123222, -- 2610.12998 Evaluating LLM Creativity through Long-Tail Performance
    123619, -- 2610.20461 Equal CER, Unequal Damage: Severity-Weighted Character Error Rate for OCR
    124619, -- 2609.27233 Distilling Sequential Computation in Transformer Language Models
    125867, -- 2605.21147 SMoA: Spectrum Modulation Adapter for Parameter-Efficient Fine-Tuning
    126047, -- 2607.08257 MentalHospital: A Virtual Environment for Evaluating Psychiatric Clinical Encoun
    126886, -- 2605.23605 DiLaDiff: Distilled Latent-augmented Diffusion for Language Modeling
    128045, -- 2604.27914 Geometry-Calibrated Conformal Abstention for Language Models
    128394, -- 2512.22545 Self-Rewarded Multimodal Coherent Reasoning Across Diverse Visual Domains
    128417, -- 2605.11601 DiffScore: Text Evaluation Beyond Autoregressive Likelihood
    128456, -- 2609.37601 SENSE: Semantic Neural Speech Synthesis from Brain Dynamics via Spatial Graph En
    128559, -- 2602.04071 Agentic AI-Empowered Dynamic Survey Framework
    129017, -- 2609.35695 Rethinking Personalized Generation: Test-time Alignment via Factorized Ranking M
    129142, -- 2608.05341 Positive-Unlabeled Preference Optimization For Chest X-ray Report Generation
    129485, -- 2605.24371 SliceWorld: A Predictive and Controllable World-State Model for CT Report Genera
    129568, -- 2608.22758 XTC: Head-Aware Sampling by Excluding Top Choices
    130145, -- 2602.09789 When Less is More: The LLM Scaling Paradox in Context Compression
    130228, -- 2609.39701 Values as Style: Disentangling Values from Semantics with One-Way Mixing for Low
    130285, -- 2610.20335 Read, Parse, Describe: Unified Document Parsing with Visual Element Description
    131225, -- 2609.35407 BiMoGen: Bidirectional Motion-Text Generation via Unified Masked Discrete Diffus
    131426, -- 1911.00650 Automatic Detection of Generated Text is Easiest when Humans are Fooled
    131445, -- 2610.21561 DialFork: Going Beyond Factuality to Evaluate Procedural Hallucination in Conver
    131931, -- 2611.03743 EvoMemState: Evolving Memory State for Personal Agents
    132011, -- 2402.19097 TEncDM: Understanding the Properties of the Diffusion Model in the Space of Lang
    132037, -- 2403.16995 Language Rectified Flow: Advancing Diffusion Language Generation with Probabilis
    132038, -- 2506.00290 DLM-One: Diffusion Language Models for One-Step Sequence Generation
    132039, -- 2605.20199 FlowLM: Few-Step Language Modeling via Diffusion-to-Flow Adaptation
    132045, -- 2604.05551 FastDiSS: Few-step Match Many-step Diffusion Language Model on Sequence-to-Seque
    132057, -- 2604.02028 Why Gaussian Diffusion Models Fail on Discrete Data and How to Prevent It?
    132066 -- 2610.06513 SOL: Measuring Gaps between Text Distributions by Double Sliced Wasserstein Metr
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'metrics curation 2026-11-10: cites the source paper but the title/abstract does not name the metric'
FROM bertscore_citers_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING bertscore_citers_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING bertscore_citers_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- cider: 97 links (title/abstract names the metric; plus the source paper).
CREATE TEMP TABLE cider_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'cider'
  AND p.id IN (
    176, -- 1504.00325 Microsoft COCO Captions: Data Collection and Evaluation Server
    816, -- 1707.07998 Bottom-Up and Top-Down Attention for Image Captioning and Visual Question Answer
    2015, -- 1904.08608 Learning to Collocate Neural Modules for Image Captioning
    3147, -- 2002.11701 CLARA: Clinical Report Auto-completion
    4686, -- 2012.03662 Confidence-aware Non-repetitive Multimodal Transformers for TextCaps
    5511, -- 2104.08718 CLIPScore: A Reference-free Evaluation Metric for Image Captioning
    6476, -- 2108.10904 SimVLM: Simple Visual Language Model Pretraining with Weak Supervision
    6910, -- 2110.06615 CLIP4Caption: CLIP for Video Caption
    7299, -- 2111.12476 Hierarchical Modular Network for Video Captioning
    7794, -- 2201.12086 BLIP: Bootstrapping Language-Image Pre-training for Unified Vision-Language Unde
    8818, -- 2204.10688 Spatiality-guided Transformer for 3D Dense Captioning on Point Clouds
    9203, -- 2205.13115 Fine-grained Image Captioning with CLIP Reward
    9238, -- 2205.14100 GIT: A Generative Image-to-text Transformer for Vision and Language
    10410, -- 2209.12343 Paraphrasing Is All You Need for Novel Object Captioning
    10535, -- 2210.01338 Learning to Collocate Visual-Linguistic Neural Modules for Image Captioning
    11384, -- 2211.08983 Is my automatic audio captioning system so bad? spider-max: a metric to consider
    11400, -- 2211.09427 Feedback is Needed for Retakes: An Explainable Poor Image Notification Framework
    11499, -- 2211.11694 Exploring Discrete Diffusion Models for Image Captioning
    11539, -- 2211.12561 Retrieval-Augmented Multimodal Language Modeling
    11938, -- 2212.06250 ScanEnts3D: Exploiting Phrase-to-3D-Object Correspondences for Improved Visio-Li
    12041, -- 2212.08985 Efficient Image Captioning for Edge Devices
    12091, -- 2212.09737 Position-guided Text Prompt for Vision-Language Pre-training
    12431, -- 2301.07389 Towards Models that Can See and Read
    12571, -- 2301.11507 Semi-Parametric Video-Grounded Text Generation
    12747, -- 2302.00402 mPLUG-2: A Modularized Multi-modal Foundation Model Across Text, Image and Video
    14065, -- 2303.13455 CoBIT: A Contrastive Bi-directional Image-Text Generation Model
    16145, -- 2305.14800 Exploring Diverse In-Context Configurations for Image Captioning
    17100, -- 2306.04362 Youku-mPLUG: A 10 Million Large-scale Chinese Video-Language Dataset for Pre-tra
    17478, -- 2306.09265 LVLM-eHub: A Comprehensive Evaluation Benchmark for Large Vision-Language Models
    18429, -- 2307.10350 Improving Multimodal Datasets with Image Captioning
    18798, -- 2307.16686 Guiding Image Captioning Models Toward More Specific Captions
    18990, -- 2308.03349 SciGraphQA: A Large-Scale Synthetic Multi-Turn Question-Answering Dataset for Sc
    19321, -- 2308.08325 Visually-Aware Context Modeling for News Image Captioning
    19713, -- 2308.12383 With a Little Help from your own Past: Prototypical Memory Networks for Image Ca
    19773, -- 2308.13218 MultiCapCLIP: Auto-Encoding Prompts for Zero-Shot Multilingual Visual Captioning
    21566, -- 2310.04991 Video-Teller: Enhancing Cross-Modal Generation with Fusion and Decoupling
    22812, -- 2310.20550 CapsFusion: Rethinking Image-Text Data at Scale
    24221, -- 2312.02051 TimeChat: A Time-sensitive Multimodal Large Language Model for Long Video Unders
    24483, -- 2312.04793 User-Aware Prefix-Tuning is a Good Learner for Personalized Image Captioning
    24796, -- 2312.09128 Tokenize Anything via Prompting
    25098, -- 2312.14115 LingoQA: Visual Question Answering for Autonomous Driving
    25844, -- 2401.08100 KTVIC: A Vietnamese Image Captioning Dataset on the Life Domain
    28119, -- 2402.18091 Polos: Multimodal Metric Learning from Human Feedback for Image Captioning
    29641, -- 2403.19838 Multi-Frame, Lightweight & Efficient Vision-Language Models for Question Answeri
    30432, -- 2404.10763 LaDiC: Are Diffusion Models Really Inferior to Autoregressive Counterparts for I
    30570, -- 2404.12739 The Solution for the CVPR2024 NICE Image Captioning Challenge
    31000, -- 2405.00983 LLM-AD: Large Language Model based Audio Description System
    31056, -- 2405.02305 Inserting Faces inside Captions: Image Captioning with Attention Guided Merging
    33789, -- 2406.19150 RAVEN: Multitask Retrieval Augmented Vision-Language Learning
    33814, -- 2406.19388 Taming Data and Transformers for Audio Generation
    34282, -- 2407.05645 OneDiff: A Generalist Model for Image Difference Captioning
    35318, -- 2407.20341 BRIDGE: Bridging Gaps in Image Captioning Evaluation with Stronger Visual Cues
    35513, -- 2408.01723 A Novel Evaluation Framework for Image2Text Generation
    36754, -- 2409.06851 LIME: Less Is More for MLLM Evaluation
    37834, -- 2410.03051 AuroraCap: Efficient, Performant Video Detailed Captioning and a New Benchmark
    40566, -- 2411.17991 VideoLLM Knows When to Speak: Enhancing Time-Sensitive Video Comprehension with
    40645, -- 2411.18953 AudioSetCaps: An Enriched Audio-Caption Dataset using Automated Generation Pipel
    42493, -- 2501.02527 Vision-Driven Prompt Optimization for Large Language Models in Multimodal Genera
    42964, -- 2501.10075 Robust Change Captioning in Remote Sensing: SECOND-CC Dataset and MModalCC Frame
    43166, -- 2501.13893 Pix2Cap-COCO: Advancing Visual Comprehension via Pixel-Level Captioning
    43217, -- 2501.14729 HERMES: A Unified Self-Driving World Model for Simultaneous 3D Scene Understandi
    47608, -- 2504.09518 3D CoCa: Contrastive Learners are 3D Captioners
    49448, -- 2505.16839 LaViDa: A Large Diffusion Language Model for Multimodal Understanding
    55169, -- 2601.05172 CoV: Chain-of-View Prompting for Spatial Reasoning
    55258, -- 2601.06496 3D CoCa v2: Contrastive Learners with Test-Time Search for Generalizable Spatial
    57710, -- 2604.21668 Encoder-Free Human Motion Understanding via Structured Motion Descriptions
    59602, -- 2603.09689 AutoViVQA: A Large-Scale Automatically Constructed Dataset for Vietnamese Visual
    66069, -- 2510.19060 PoSh: Using Scene Graphs To Guide LLMs-as-a-Judge For Detailed Image Description
    66604, -- 2510.10022 Q-Adapter: Visual Query Adapter for Extracting Textually-related Features in Vid
    69760, -- 2508.09547 GoViG: Goal-Conditioned Visual Navigation Instruction Generation
    73807, -- 2503.23679 The Devil is in the Distributions: Explicit Modeling of Scene Content is Key in
    77868, -- 2401.17910 ControlCap: Controllable Region-level Captioning
    78531, -- 2309.07615 Multilingual Audio Captioning using machine translated data
    78860, -- 2306.14259 Improving Reference-based Distinctive Image Captioning with Contrastive Rewards
    79829, -- 2207.11118 Rethinking the Reference-based Distinctive Image Captioning
    81060, -- 2010.10042 Improving Factual Completeness and Consistency of Image-to-Text Radiology Report
    81920, -- 1809.07041 Exploring Visual Relationship for Image Captioning
    84777, -- 2603.06213 Cut to the Chase: Training-free Multimodal Summarization via Chain-of-Events
    85658, -- 2605.31029 PEEK: Picking Essential frames via Efficient Knowledge distillation
    90390, -- 2411.16932 Seq2Time: Sequential Knowledge Transfer for Video LLM Temporal Grounding
    91546, -- 2406.06499 NarrativeBridge: Enhancing Video Captioning with Causal-Temporal Narrative
    103384, -- 2412.19685 Generating Attribution Reports for Manipulated Facial Images: A Dataset and Base
    106705, -- 2511.21002 Knowledge Completes the Vision: A Multimodal Entity-aware Retrieval-Augmented Ge
    108359, -- 2506.04743 SRD: Reinforcement-Learned Semantic Perturbation for Backdoor Defense in VLMs
    112700, -- 2312.03661 Reason2Drive: Towards Interpretable and Chain-based Reasoning for Autonomous Dri
    112975, -- 2405.11442 Unifying 3D Vision-Language Understanding via Promptable Queries
    115240, -- external Region-Specific Retrieval Augmentation for Longitudinal Visual Question Answerin
    115545, -- 2404.00913 LLaMA-Excitor: General Instruction Tuning via Indirect Feature Interaction
    115561, -- external Towards Better Vision-Inspired Vision-Language Models
    115598, -- 2311.11860 LION: Empowering Multimodal Large Language Model with Dual-Level Visual Knowledg
    118633, -- 2606.27373 Paying More Attention to Visual Tokens in Self-Evolving Large Multimodal Models
    120693, -- external Dynamics-Aware Preference Optimization for Vision-Language Models
    120914, -- external mVLM: A Vision Language Model for mNPUs
    121760, -- external SAT-RRG: LLM-Guided Self-Adaptive Training for Radiology Report Generation with
    121979, -- 2609.16591 FLAT: Resampling Image and Text into 1D Flexible-Length Aligned Transmodal Token
    131672, -- 2610.39302 Proving and Improving the Platonic Representation Hypothesis with JEPAs
    132128 -- 1411.5726 CIDEr: Consensus-based Image Description Evaluation
  );

DELETE FROM paper_method_exclusions x
USING cider_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM cider_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM cider_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- cider: 530 reviewed negatives (local citers of the source that do not name the metric).
CREATE TEMP TABLE cider_citers_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'cider'
  AND p.id IN (
    124, -- 1411.4555 Show and Tell: A Neural Image Caption Generator
    132, -- 1412.2306 Deep Visual-Semantic Alignments for Generating Image Descriptions
    182, -- 1505.00468 VQA: Visual Question Answering
    1121, -- 1802.08129 Multimodal Explanations: Justifying Decisions and Pointing to the Evidence
    2665, -- 1910.05298 Neural Generation for Czech: Data and Baselines
    6366, -- 2108.02365 Hybrid Reasoning Network for Video-based Commonsense Captioning
    8046, -- 2202.11705 COLD Decoding: Energy-based Constrained Text Generation with Langevin Dynamics
    17209, -- 2306.05696 Embodied Executable Policy Learning with Language-based Scene Summarization
    22131, -- 2310.11513 GenEval: An Object-Focused Framework for Evaluating Text-to-Image Alignment
    24016, -- 2311.18248 mPLUG-PaperOwl: Scientific Diagram Analysis with the Multimodal Large Language M
    28008, -- 2402.16846 GROUNDHOG: Grounding Large Language Models to Holistic Segmentation
    28189, -- 2402.19119 VIXEN: Visual Text Comparison Network for Image Difference Captioning
    28216, -- 2402.19479 Panda-70M: Captioning 70M Videos with Multiple Cross-Modality Teachers
    28237, -- 2403.00425 HALC: Object Hallucination Reduction via Adaptive Focal-Contrast Decoding
    28382, -- 2403.02330 RegionGPT: Towards Region Understanding Vision Language Model
    28423, -- 2403.02969 Multi-modal Instruction Tuned LLMs with Fine-grained Visual Perception
    28519, -- 2403.04593 Embodied Understanding of Driving Scenarios
    28522, -- 2403.04640 CAT: Enhancing Multimodal Large Language Model to Answer Questions in Dynamic Au
    28553, -- 2403.04945 MEIT: Multi-Modal Electrocardiogram Instruction Tuning on Large Language Models
    28559, -- 2403.05021 Beyond MOT: Semantic Multi-Object Tracking
    28660, -- 2403.06735 Enhancing Image Caption Generation Using Reinforcement Learning with Human Feedb
    28663, -- 2403.06764 An Image is Worth 1/2 Tokens After Layer 2: Plug-and-Play Inference Acceleration
    28737, -- 2403.07750 Synth$^2$: Boosting Visual-Language Models with Synthetic Captions and Image Emb
    28831, -- 2403.09113 AutoLoRA: Automatically Tuning Matrix Ranks in Low-Rank Adaptation Based on Meta
    28870, -- 2403.09611 MM1: Methods, Analysis & Insights from Multimodal LLM Pre-training
    28874, -- 2403.09626 Video Mamba Suite: State Space Model as a Versatile Alternative for Video Unders
    28931, -- 2403.10492 Mitigating Dialogue Hallucination for Large Vision Language Models via Adversari
    28989, -- 2403.11236 ChartThinker: A Contextual Chain-of-Thought Approach to Optimized Chart Summariz
    28993, -- 2403.11299 SQ-LLaVA: Self-Questioning for Large Vision-Language Assistant
    29039, -- 2403.11821 A Survey on Quality Metrics for Text-to-Image Generation
    29066, -- 2403.12027 From Pixels to Insights: A Survey on Automatic Chart Understanding in the Era of
    29413, -- 2403.16558 Elysium: Exploring Object-level Perception in Videos via MLLM
    29556, -- 2403.18715 Mitigating Hallucinations in Large Vision-Language Models with Instruction Contr
    29621, -- 2403.19589 TOD3Cap: Towards 3D Dense Captioning in Outdoor Scenes
    29623, -- 2403.19596 LocCa: Visual Pretraining with Location-aware Captioners
    29624, -- 2403.19603 Semantic Map-based Generation of Navigation Instructions
    29628, -- 2403.19646 Change-Agent: Towards Interactive Comprehensive Remote Sensing Change Interpreta
    29697, -- 2404.00412 SVGCraft: Beyond Single Object Text-to-SVG Synthesis with Comprehensive Canvas L
    29792, -- 2404.01297 Streaming Dense Video Captioning
    29889, -- 2404.02755 DIBS: Enhancing Dense Video Captioning with Unlabeled Videos via Pseudo Boundary
    30098, -- 2404.05726 MA-LMM: Memory-Augmented Large Multimodal Model for Long-Term Video Understandin
    30196, -- 2404.07202 UMBRAE: Unified Multimodal Brain Decoding
    30197, -- 2404.07204 BRAVE: Broadening the visual encoding of vision-language models
    30220, -- 2404.07616 Audio Dialogues: Dialogues dataset for audio and music understanding
    30233, -- 2404.07824 Heron-Bench: A Benchmark for Evaluating Vision Language Models in Japanese
    30364, -- 2404.09632 Bridging Vision and Language Spaces with Assignment Prediction
    30421, -- 2404.10595 Automated Evaluation of Large Vision-Language Models on Self-driving Corner Case
    30663, -- 2404.14412 AutoAD III: The Prequel -- Back to the Pixels
    30732, -- 2404.15736 What Makes Multimodal In-Context Learning Work?
    30757, -- 2404.16222 Step Differences in Instructional Video
    30829, -- 2404.17534 Exploring the Distinctiveness and Fidelity of the Descriptions Generated by Larg
    30848, -- 2404.17778 MRScore: Evaluating Radiology Report Generation with LLM-based Reward System
    30943, -- 2404.19753 DOCCI: Descriptions of Connected and Contrasting Images
    31021, -- 2405.01533 OmniDrive: A Holistic Vision-Language Dataset for Autonomous Driving with Counte
    31065, -- 2405.02793 ImageInWords: Unlocking Hyper-Detailed Image Descriptions
    31296, -- 2405.08720 The Lost Melody: Empirical Observations on Text-to-Video Generation From A Story
    31299, -- 2405.08813 CinePile: A Long Video Question Answering Dataset and Benchmark
    31339, -- 2405.09818 Chameleon: Mixed-Modal Early-Fusion Foundation Models
    31363, -- 2405.10311 UniRAG: Universal Retrieval Augmentation for Large Vision Language Models
    31670, -- 2405.15232 DEEM: Diffusion Models Serve as the Eyes of Large Language Models for Image Perc
    31699, -- 2405.15604 Text Generation: A Systematic Literature Review of Tasks, Evaluation, and Challe
    31750, -- 2405.16273 M$^3$GPT: An Advanced Multimodal, Multitask Framework for Motion Comprehension a
    31812, -- 2405.16919 VoCoT: Unleashing Visually Grounded Multi-Step Reasoning in Large Multi-Modal Mo
    31886, -- 2405.17871 Seeing the Image: Prioritizing Visual Correlation by Contrastive Alignment
    31988, -- 2405.19092 Benchmarking and Improving Detail Image Caption
    32208, -- 2406.00977 Dragonfly: Multi-Resolution Zoom-In Encoding Enhances Vision-Language Models
    32283, -- 2406.02120 Diver: Large Language Model Decoding with Span-Level Mutual Information Verifica
    32290, -- 2406.02265 Understanding Retrieval Robustness for Retrieval-Augmented Image Captioning
    32355, -- 2406.03008 DriVLMe: Enhancing LLM-based Autonomous Driving Agents with Embodied and Social
    32545, -- 2406.05491 One Perturbation is Enough: On Generating Universal Adversarial Perturbations ag
    32594, -- 2406.06040 Vript: A Video Is Worth Thousands of Words
    32736, -- 2406.07544 Situational Awareness Matters in 3D Vision Language Reasoning
    32754, -- 2406.07822 Tell Me What's Next: Textual Foresight for Generic UI Representations
    32804, -- 2406.08418 OmniCorpus: A Unified Multimodal Corpus of 10 Billion-Level Images Interleaved w
    32831, -- 2406.08707 mOSCAR: A Large-scale Multilingual and Multimodal Document-level Corpus
    32942, -- 2406.09905 Nymeria: A Massive Collection of Multimodal Egocentric Daily Motion in the Wild
    32956, -- 2406.10118 SEACrowd: A Multilingual Multimodal Data Hub and Benchmark Suite for Southeast A
    33055, -- 2406.11069 WildVision: Evaluating Vision-Language Models in the Wild with Human Preferences
    33250, -- 2406.12479 RS-GPT4V: A Unified Multimodal Instruction-Following Dataset for Remote Sensing
    33309, -- 2406.13181 The Impact of Auxiliary Patient Data on Automated Chest X-Ray Report Generation
    33350, -- 2406.13735 StableSemantics: A Synthetic Language-Vision Dataset of Semantic Representations
    33358, -- 2406.13892 Adaptable Logical Control for Large Language Models
    33725, -- 2406.18227 GUIDE: A Guideline-Guided Dataset for Instructional Video Comprehension
    33747, -- 2406.18530 MatchTime: Towards Automatic Soccer Game Commentary Generation
    33908, -- 2407.00634 Tarsier: Recipes for Training and Evaluating Large Video Description Models
    33923, -- 2407.00902 From Introspection to Best Practices: Principled Analysis of Demonstrations in M
    34144, -- 2407.03791 M5 -- A Diverse Benchmark to Assess the Performance of Large Multimodal Models A
    34206, -- 2407.04559 Not (yet) the whole story: Evaluating Visual Storytelling Requires More than Mea
    34566, -- 2407.09413 SPIQA: A Dataset for Multimodal Question Answering on Scientific Papers
    34730, -- 2407.11449 Controllable Contextualized Image Captioning: Directing the Visual Narrative thr
    34735, -- 2407.11522 FIRE: A Dataset for Feedback Integration and Refinement Evaluation of Multimodal
    35058, -- 2407.15680 HaloQuest: A Visual Hallucination Dataset for Advancing Multimodal Reasoning
    35147, -- 2407.17060 High Efficiency Image Compression for Large Visual-Language Models
    35346, -- 2407.20962 MMTrail: A Multimodal Trailer Video Dataset with Language and Music Descriptions
    35376, -- 2407.21534 ControlMLLM: Training-Free Visual Prompt Learning for Multimodal Large Language
    35388, -- 2407.21757 Learning Video Context as Interleaved Multimodal Sequences
    35451, -- 2408.00754 Coarse Correspondences Boost Spatial-Temporal Reasoning in Multimodal Language M
    35573, -- 2408.02788 GazeXplain: Learning to Predict Natural Language Explanations of Visual Scanpath
    35671, -- 2408.04594 Img-Diff: Contrastive Data Synthesis for Multimodal Large Language Models
    35781, -- 2408.06662 Bi-directional Contextual Attention for 3D Dense Captioning
    35824, -- 2408.07277 Speech vs. Transcript: Does It Matter for Human Annotators in Speech Summarizati
    35930, -- 2408.09169 Automatic Metrics in Natural Language Generation: A Survey of Current Evaluation
    36035, -- 2408.11001 MegaFusion: Extend Diffusion Models towards Higher-resolution Image Generation w
    36040, -- 2408.11039 Transfusion: Predict the Next Token and Diffuse Images with One Multi-Modal Mode
    36248, -- 2408.14547 Revisiting Image Captioning Training Paradigm via Direct CLIP-based Optimization
    36254, -- 2408.14622 What Makes a Good Story and How Can We Measure It? A Comprehensive Survey of Sto
    36395, -- 2408.16809 See or Guess: Counterfactually Regularized Image Captioning
    36397, -- 2408.16889 LLaVA-Chef: A Multi-modal Generative Model for Food Recipes
    36507, -- 2409.01437 Kvasir-VQA: A Text-Image Pair GI Tract Dataset
    36594, -- 2409.03025 No Detail Left Behind: Revisiting Self-Retrieval for Fine-Grained Image Captioni
    36630, -- 2409.03757 Lexicon3D: Probing Visual Foundation Models for Complex 3D Scene Understanding
    36654, -- 2409.04388 Question-Answering Dense Video Events
    36725, -- 2409.06299 Enhancing Long Video Understanding via Hierarchical Event-Based Memory
    36769, -- 2409.07239 PiTe: Pixel-Temporal Alignment for Large Video-Language Model
    36888, -- 2409.09401 Towards Diverse and Efficient Audio Captioning via Diffusion Models
    36911, -- 2409.09866 S2Cap: A Benchmark and a Baseline for Singing Style Captioning
    36955, -- 2409.10695 Playground v3: Improving Text-to-Image Alignment with Deep-Fusion Large Language
    37099, -- 2409.12962 CLAIR-A: Leveraging Large Language Models to Judge Audio Captions
    37203, -- 2409.14846 A-VL: Adaptive Attention for Large Vision-Language Models
    37368, -- 2409.17692 MIO: A Foundation Model on Multimodal Tokens
    37395, -- 2409.18111 E.T. Bench: Towards Open-Ended Event-Level Video-Language Understanding
    37461, -- 2409.19232 TrojVLM: Backdoor Attack Against Vision Language Models
    37462, -- 2409.19255 DENEB: A Hallucination-Robust Automatic Evaluation Metric for Image Captioning
    37483, -- 2409.19532 Video DataFlywheel: Resolving the Impossible Data Trinity in Video-Language Unde
    37755, -- 2410.02381 MetaMetrics: Calibrating Metrics For Generation Tasks Using Human Preferences
    38042, -- 2410.05474 R-Bench: Are your Large Multimodal Model Robust to Real-world Corruptions?
    38058, -- 2410.05643 TRACE: Temporal Grounding Video LLM via Causal Event Modeling
    38093, -- 2410.06126 $X^2$-DFD: A framework for eXplainable and eXtendable Deepfake Detection
    38230, -- 2410.07752 TVBench: Redesigning Video-Language Evaluation
    38364, -- 2410.09503 SLAM-AAC: Enhancing Audio Captioning with Paraphrasing Augmentation and CLAP-Ref
    38370, -- 2410.09604 EmbodiedCity: A Benchmark Platform for Embodied Agent in Real-world City Environ
    38448, -- 2410.10676 Both Ears Wide Open: Towards Language-Driven Spatial Audio Generation
    38473, -- 2410.10818 TemporalBench: Benchmarking Fine-grained Temporal Understanding for Multimodal V
    38878, -- 2410.15461 EVA: An Embodied World Model for Future Video Anticipation
    38944, -- 2410.16261 Mini-InternVL: A Flexible-Transfer Pocket Multimodal Model with 5% Parameters an
    39088, -- 2410.18325 AVHBench: A Cross-Modal Hallucination Benchmark for Audio-Visual Large Language
    39204, -- 2410.19884 A Survey of AI-Generated Video Evaluation
    39239, -- 2410.20482 What Factors Affect Multi-Modal In-Context Learning? An In-Depth Exploration
    39320, -- 2410.21747 MotionGPT-2: A General-Purpose Motion-Language Model for Motion Generation and U
    39343, -- 2410.22313 Senna: Bridging Large Vision-Language Models and End-to-End Autonomous Driving
    39427, -- 2410.23687 Adversarial Attacks of Vision Tasks in the Past 10 Years: A Survey
    39756, -- 2411.04996 Mixture-of-Transformers: A Sparse and Scalable Architecture for Multi-Modal Foun
    39802, -- 2411.05679 Tell What You Hear From What You See -- Video to Audio Generation Through Text
    39873, -- 2411.07076 StoryTeller: Improving Long Video Description through Global Audio-Visual Charac
    39897, -- 2411.07265 ViTOC: Vision Transformer and Object-aware Captioner
    40122, -- 2411.11758 The Power of Many: Multi-Agent Multimodal Models for Cultural Image Captioning
    40132, -- 2411.11909 SymDPO: Boosting In-Context Learning of Large Multimodal Models with Symbol Demo
    40152, -- 2411.12195 A Survey of Medical Vision-and-Language Applications and Their Techniques
    40408, -- 2411.16156 VideoOrion: Tokenizing Object Dynamics in Videos
    40489, -- 2411.17125 DOGE: Towards Versatile Visual Document Grounding and Referring
    40581, -- 2411.18180 DistinctAD: Distinctive Audio Description Generation in Contexts
    40627, -- 2411.18674 Active Data Curation Effectively Distills Large-Scale Multimodal Models
    40709, -- 2411.19772 LongVALE: Vision-Audio-Language-Event Benchmark Towards Time-Aware Omni-Modal Pe
    40710, -- 2411.19774 PerLA: Perceptive 3D Language Assistant
    40759, -- 2412.00493 Video-3D LLM: Learning Position-Aware Video Representation for 3D Scene Understa
    40814, -- 2412.01169 OmniFlow: Any-to-Any Generation with Multi-Modal Rectified Flows
    40823, -- 2412.01292 LSceneLLM: Enhancing Large 3D Scene Understanding Using Adaptive Visual Preferen
    40860, -- 2412.01820 Towards Universal Soccer Video Understanding
    41296, -- 2412.07320 CoMA: Compositional Human Motion Generation with Multi-modal Agents
    41381, -- 2412.08467 Bootstrapping Language-Guided Navigation Learning with Self-Refining Data Flywhe
    41463, -- 2412.09501 Lyra: An Efficient and Speech-Centric Framework for Omni-Cognition
    41501, -- 2412.09754 ViCaS: A Dataset for Combining Holistic and Pixel-level Video Understanding usin
    41523, -- 2412.10002 NowYouSee Me: Context-Aware Automatic Audio Description
    41921, -- 2412.15188 LMFusion: Adapting Pretrained Language Models for Multimodal Generation
    41931, -- 2412.15213 Flowing from Words to Pixels: A Framework for Cross-Modality Evolution
    42167, -- 2412.18450 3DGraphLLM: Combining Semantic Graphs and Large Language Models for 3D Scene Und
    42189, -- 2412.18675 TAB: Transformer Attention Bottlenecks enable User Intervention and Debugging in
    42354, -- 2501.00513 CaReBench: A Fine-Grained Benchmark for Video Captioning and Retrieval
    42364, -- 2501.00599 VideoRefer Suite: Advancing Spatial-Temporal Object Understanding with Video LLM
    42496, -- 2501.02584 Efficient Architectures for High Resolution Vision-Language Models
    42589, -- 2501.04003 Are VLMs Ready for Autonomous Driving? An Empirical Study from the Reliability,
    42761, -- 2501.06761 VidChain: Chain-of-Tasks with Metric-based Direct Preference Optimization for De
    42764, -- 2501.06828 GeoPix: Multi-Modal Large Language Model for Pixel-level Image Understanding in
    42846, -- 2501.08326 Omni-RGPT: Unifying Image and Video Region-level Understanding via Token Marks
    42910, -- 2501.09446 Double Visual Defense: Adversarial Pre-training and Instruction Tuning for Impro
    42915, -- 2501.09555 Text-driven Adaptation of Foundation Models for Few-shot Surgical Workflow Analy
    42992, -- 2501.10967 Advancing General Multimodal Capability of Vision-language Models with Pyramid-d
    43326, -- 2501.16698 3D-MoE: A Mixture-of-Experts Multi-modal LLM for 3D Vision and Pose Diffusion vi
    43671, -- 2502.02589 COCONut-PanCap: Joint Panoptic Segmentation and Grounded Captions for Fine-Grain
    43941, -- 2502.06600 Evaluation of Multilingual Image Captioning: How far can we get with CLIP models
    44086, -- 2502.08279 What Is That Talk About? A Video-to-Text Summarization Dataset for Scientific Pr
    44123, -- 2502.08826 Ask in Any Modality: A Comprehensive Survey on Multimodal Retrieval-Augmented Ge
    44455, -- 2502.12513 RealSyn: An Effective and Scalable Multimodal Interleaved Document Transformatio
    44505, -- 2502.13034 Natural Language Generation from Visual Sequences: Challenges and Future Directi
    44593, -- 2502.13898 GroundCap: A Visually Grounded Image Captioning Dataset
    44716, -- 2502.14914 What Is a Good Caption? A Comprehensive Visual Caption Benchmark for Evaluating
    44754, -- 2502.15393 LongCaptioning: Unlocking the Power of Long Caption Generation in Large Multimod
    44898, -- 2502.16989 All-in-one: Understanding and Generation in Multimodal Reasoning with the MAIA B
    44931, -- 2502.17297 Benchmarking Retrieval-Augmented Generation in Multi-Modal Contexts
    45231, -- 2502.21321 LLM Post-Training: A Deep Dive into Reasoning Large Language Models
    45392, -- 2503.02175 DivPrune: Diversity-based Visual Token Pruning for Large Multimodal Models
    45474, -- 2503.03285 Enhancing Vietnamese VQA through Curriculum Learning on Raw and Augmented Text R
    45495, -- 2503.03651 DoraCycle: Domain-Oriented Adaptation of Unified Generative Model in Multimodal
    45678, -- 2503.06271 SplatTalk: 3D VQA with Gaussian Splatting
    45818, -- 2503.07608 AlphaDrive: Unleashing the Power of VLMs in Autonomous Driving via Reinforcement
    45831, -- 2503.07906 Painting with Words: Elevating Detailed Image Captioning with Benchmark and Alig
    45889, -- 2503.08540 Mellow: a small audio language model for reasoning
    45966, -- 2503.09443 Florenz: Scaling Laws for Systematic Generalization in Vision-Language Models
    45985, -- 2503.09594 SimLingo: Vision-Only Closed-Loop Autonomous Driving with Language-Action Alignm
    46103, -- 2503.10772 FlowTok: Flowing Seamlessly Across Text and Image Tokens
    46104, -- 2503.10781 Large-scale Pre-training for Grounded Video Caption Generation
    46122, -- 2503.11093 OmniDiff: A Comprehensive Benchmark for Fine-grained Image Difference Captioning
    46148, -- 2503.11481 T2I-FineEval: Fine-Grained Compositional Metric for Text-to-Image Evaluation
    46188, -- 2503.12329 CapArena: Benchmarking and Analyzing Detailed Image Captioning in the LLM Era
    46260, -- 2503.13369 Sightation Counts: Leveraging Sighted User Feedback in Building a BLV-aligned Da
    46355, -- 2503.14604 Image Captioning Evaluation in the Age of Multimodal LLMs: Challenges and Future
    46360, -- 2503.14756 SceneEval: Evaluating Semantic Coherence in Text-Conditioned 3D Indoor Scene Syn
    46391, -- 2503.15338 Solla: Towards a Speech-Oriented LLM That Hears Acoustic Context
    46416, -- 2503.15633 Vision-Speech Models: Teaching Speech Models to Converse about Images
    46470, -- 2503.16257 Plug-and-Play 1.x-Bit KV Cache Quantization for Video Large Language Models
    46584, -- 2503.17827 4D-Bench: Benchmarking Multi-modal Large Language Models for 4D Object Understan
    46769, -- 2503.20188 Rethinking Vision-Language Model in Face Forensics: Multi-Modal Interpretable Fo
    46899, -- 2503.21910 JEEM: Vision-Language Understanding in Four Arabic Dialects
    47085, -- 2504.00072 Chapter-Llama: Efficient Chaptering in Hour-Long Videos with LLMs
    47280, -- 2504.03254 SARLANG-1M: A Benchmark for Vision-Language Modeling in SAR Image Understanding
    47386, -- 2504.05305 URECA: Unique Region Caption Anything
    47552, -- 2504.08531 Embodied Image Captioning: Self-supervised Learning Agents for Spatially Coheren
    47637, -- 2504.09895 Learning from Reference Answers: Versatile Language Model Alignment without Bina
    47680, -- 2504.10465 Pixel-SAIL: Single Transformer For Pixel-Grounded Understanding
    47744, -- 2504.11441 TADACap: Time-series Adaptive Domain-Aware Captioning
    48045, -- 2504.15921 ViSMaP: Unsupervised Hour-long Video Summarisation by Meta-Prompting
    48055, -- 2504.16060 Vision-Language Models Are Not Pragmatically Competent in Referring Expression G
    48057, -- 2504.16072 Describe Anything: Detailed Localized Image and Video Captioning
    48190, -- 2504.19627 VCM: Vision Concept Modeling Based on Implicit Contrastive Learning with Vision-
    48416, -- 2505.02829 LISAT: Language-Instructed Segmentation Assistant for Satellite Imagery
    48698, -- 2505.08725 Extending Large Vision-Language Model for Diverse Interactive Tasks in Autonomou
    49180, -- 2505.14462 RAVENEA: A Benchmark for Multimodal Retrieval-Augmented Visual Culture Understan
    49203, -- 2505.14629 KERL: Knowledge-Enhanced Personalized Recipe Recommendation using Large Language
    49458, -- 2505.16916 Backdoor Cleaning without External Guidance in MLLM Fine-tuning
    49519, -- 2505.17423 VIBE: Video-to-Text Information Bottleneck Evaluation for TL;DR
    49548, -- 2505.17726 Slot-MLLM: Object-Centric Visual Tokenization for Multimodal LLM
    49814, -- 2505.20124 TUNA: Comprehensive Fine-grained Temporal Understanding Evaluation on Dense Dyna
    50019, -- 2505.22613 RICO: Improving Accuracy and Completeness in Image Recaptioning via Visual Recon
    50645, -- 2506.05302 Perceive Anything: Recognize, Explain, Caption, and Segment Anything in Images a
    50744, -- 2506.07044 Lingshu: A Generalist Foundation Model for Unified Multimodal Medical Understand
    51368, -- 2506.18369 RePIC: Reinforced Post-Training for Personalizing Multi-Modal Language Models
    51802, -- 2507.07106 Towards Multimodal Understanding via Stable Diffusion as a Task-Aware Feature Ex
    51942, -- 2507.12841 AnyCap Project: A Unified Framework, Dataset, and Benchmark for Controllable Omn
    51980, -- 2507.14129 OpenBEATs: A Fully Open-Source General-Purpose Audio Encoder
    52128, -- 2507.23478 3D-R1: Enhancing Reasoning in 3D VLMs for Unified Scene Understanding
    52160, -- 2508.01242 MeshLLM: Empowering Large Language Models to Progressively Understand and Genera
    52776, -- 2509.11986 Lost in Embeddings: Information Loss in Vision-Language Models
    52951, -- 2509.18030 RadEval: A framework for radiology text evaluation
    53438, -- 2510.02898 One Patch to Caption Them All: A Unified Zero-Shot Captioning Framework
    53541, -- 2510.11330 Diffusion-Link: Diffusion Probabilistic Model for Bridging the Audio-Text Modali
    53847, -- 2510.23603 PixelRefer: A Unified Framework for Spatio-Temporal Object Referring with Arbitr
    54104, -- 2511.05369 Dense Motion Captioning
    54136, -- 2511.07299 VADER: Towards Causal Video Anomaly Understanding with Relation-Aware Large Lang
    54257, -- 2511.14086 Error-Driven Scene Editing for 3D Grounding in Large Language Models
    54415, -- 2511.21025 CaptionQA: Is Your Caption as Useful as the Image Itself?
    54474, -- 2512.01830 OpenREAD: Reinforced Open-Ended Reasoing for End-to-End Autonomous Driving with
    54828, -- 2512.10945 MeViS: A Multi-Modal Dataset for Referring Motion Expression Video Segmentation
    55163, -- 2512.21815 Few Tokens Matter: Entropy Guided Attacks on Vision-Language Models
    55285, -- 2601.07632 GeoMotionGPT: Geometry-Aligned Motion Understanding with Large Language Models
    56660, -- 2603.09160 RubiCap: Rubric-Guided Reinforcement Learning for Dense Image Captioning
    56876, -- 2603.18002 Loc3R-VLM: Language-based Localization and 3D Reasoning with Vision-Language Mod
    57208, -- 2603.24257 Memory-Augmented Vision-Language Agents for Persistent and Semantically Consiste
    57377, -- 2604.09450 ECHO: Efficient Chest X-ray Report Generation with One-step Block Diffusion
    58389, -- 2604.08115 Revise: A Framework for Revising OCRed text in Practical Information Systems wit
    58664, -- 2604.00912 ProCap: Projection-Aware Captioning for Spatial Augmented Reality
    58741, -- 2511.08917 "It's trained by non-disabled people": Evaluating How Image Quality Affects Prod
    58898, -- 2603.25533 BFMD: A Full-Match Badminton Dense Dataset for Dense Shot Captioning
    59182, -- 2603.18282 CycleCap: Improving VLMs Captioning Performance via Self-Supervised Cycle Consis
    59808, -- 2603.05969 Imagine How To Change: Explicit Procedure Modeling for Change Captioning
    59829, -- 2603.06576 BEVLM: Distilling Semantic Knowledge from LLMs into Bird's-Eye View Representati
    60182, -- 2602.23588 Hyperdimensional Cross-Modal Alignment of Frozen Language and Image Models for E
    60564, -- 2602.15766 TAC: Timestamped Audio Captioning
    60673, -- 2602.13758 OmniScience: A Large-scale Multi-modal Dataset for Scientific Image Understandin
    60742, -- 2602.12370 LLaMo: Scaling Pretrained Language Models for Unified Motion Understanding and G
    61042, -- 2602.07574 ViCA: Efficient Multimodal LLMs with Vision-Only Cross-Attention
    61168, -- 2602.05496 XEmoGPT: An Explainable Multimodal Emotion Recognition Framework with Cue-Level
    61654, -- 2602.00393 Brazilian Portuguese Image Captioning with Transformers: A Study on Cross-Native
    61827, -- 2601.21612 Representation-Regularized Convolutional Audio Transformer for Audio Understandi
    62073, -- 2601.17818 ViTCoP: Accelerating Large Vision-Language Models via Visual and Textual Semanti
    62261, -- 2601.14637 Forest-Chat: Adapting Vision-Language Agents for Interactive Forest Change Analy
    62490, -- 2601.09879 MedVL-SAM2: A unified 3D medical vision-language model for multimodal reasoning
    62508, -- 2601.09385 SLAM-LLM: A Modular, Open-Source Multimodal Large Language Model Framework and B
    62619, -- 2601.07375 GROKE: Vision-Free Navigation Instruction Evaluation via Graph Reasoning on Open
    62681, -- 2601.06843 Speak While Watching: Unleashing TRUE Real-Time Video Understanding Capability o
    62823, -- 2601.04497 Vision-Language Agents for Interactive Forest Change Analysis
    63241, -- 2512.23180 GaussianDWM: 3D Gaussian Driving World Model for Unified Scene Understanding and
    63335, -- 2512.21150 ORCA: Object Recognition and Comprehension for Archiving Marine Species
    63820, -- 2512.11016 SoccerMaster: A Vision Foundation Model for Soccer Understanding
    63830, -- 2512.10730 IRG-MotionLLM: Interleaving Motion Generation, Assessment and Refinement for Tex
    63880, -- 2512.09841 ChronusOmni: Improving Time Awareness of Omni Large Language Models
    63950, -- 2512.08135 CVP: Central-Peripheral Vision-Inspired Multimodal Model for Spatial Reasoning
    64040, -- 2512.06581 MedGRPO: Multi-Task Reinforcement Learning for Heterogeneous Medical Video Under
    64623, -- 2511.18921 BackdoorVLM: A Benchmark for Backdoor Attacks on Vision-Language Models
    65454, -- 2511.01831 Dynamic Routing Between Experts: A Data-Efficient Approach to Continual Learning
    65497, -- 2511.01299 Towards General Auditory Intelligence: Large Multimodal Models for Machine Liste
    65520, -- 2511.00962 A Unified Reasoning Framework for Holistic Zero-Shot Video Anomaly Analysis
    65651, -- 2511.00088 Alpamayo-R1: Bridging Reasoning and Action Prediction for Generalizable Autonomo
    65906, -- 2510.21518 Head Pursuit: Probing Attention Specialization in Multimodal Transformers
    66110, -- 2510.18337 MoTVLA: A Vision-Language-Action Model with Unified Fast-Slow Reasoning
    66307, -- 2510.14664 SpeechLLM-as-Judges: Towards General and Interpretable Speech Quality Evaluation
    66424, -- 2510.12720 Omni-Captioner: Data Pipeline, Models, and Benchmark for Omni Detailed Perceptio
    66549, -- 2510.10671 Image-to-Video Transfer Learning based on Image-Language Foundation Models: A Co
    66609, -- 2512.05119 RAG-IGBench: Innovative Evaluation for RAG-based Interleaved Generation in Open-
    67223, -- 2510.00647 MCM-DPO: Multifaceted Cross-Modal Direct Preference Optimization for Alt-text Ge
    67565, -- 2509.23673 RCI: A Score for Evaluating Global and Local Reasoning in Multimodal Benchmarks
    67937, -- 2509.19090 Citrus-V: Advancing Medical Foundation Models with Unified Medical Image Groundi
    68074, -- 2509.16721 Text-Scene: A Scene-to-Language Parsing Framework for 3D Scene Understanding
    68093, -- 2509.16538 Advancing Reference-free Evaluation of Video Captions with Factual Analysis
    68311, -- 2509.13255 ResidualViT for Efficient Temporally Dense Video Encoding
    68455, -- 2509.10345 Towards Understanding Visual Grounding in Visual Language Models
    68719, -- 2509.04606 Sample-efficient Integration of New Modalities into Large Language Models
    68750, -- 2509.03897 SPECS: Specificity-Enhanced CLIP-Score for Long Image Caption Evaluation
    69581, -- 2508.12263 Region-Level Context-Aware Multimodal Understanding
    69644, -- 2508.11011 Are Large Pre-trained Vision Language Models Effective Construction Safety Inspe
    69994, -- 2508.06125 SC-Captioner: Improving Image Captioning with Self-Correction by Reinforcement L
    70055, -- 2508.10922 A Survey on Video Temporal Grounding with Multimodal Large Language Model
    70083, -- 2508.04852 VER-Bench: Evaluating MLLMs on Reasoning with Fine-Grained Visual Evidence
    70333, -- 2508.01699 TimeExpert: An Expert-Guided Video LLM for Video Temporal Grounding
    70484, -- 2507.23511 MECAT: A Multi-Experts Constructed Benchmark for Fine-Grained Audio Understandin
    70554, -- 2507.22346 DeltaVLM: Interactive Remote Sensing Image Change Analysis via Instruction-guide
    70708, -- 2507.19599 Object-centric Video Question Answering with Visual Grounding and Referring
    70751, -- 2507.18788 When Better Eyes Lead to Blindness: A Diagnostic Study of the Information Bottle
    70755, -- 2507.18616 SynC: Synthetic Image Caption Dataset Refinement with One-to-many Mapping for Ze
    70867, -- 2507.16704 Screen2AX: Vision-Based Approach for Automatic macOS Accessibility Generation
    70879, -- 2507.16524 Spatial 3D-LLM: Exploring Spatial Awareness in 3D Vision-Language Models
    70978, -- 2507.14743 InterAct-Video: Reasoning-Rich Video QA for Urban Traffic
    71141, -- 2507.10419 Multiple Choice Learning of Low Rank Adapters for Language Modeling
    71207, -- 2507.09313 ProactiveBench: A Comprehensive Benchmark Evaluating Proactive Interactions in V
    71383, -- 2507.04815 From Vision To Language through Graph of Events in Space and Time: An Explainabl
    71477, -- 2507.02664 AIGI-Holmes: Towards Explainable and Generalizable AI-Generated Image Detection
    71554, -- 2507.00886 GaussianVLM: Scene-centric 3D Vision-Language Models using Language-aligned Gaus
    71597, -- 2506.24086 MotionGPT3: Human Motion as a Second Modality
    71772, -- 2506.18862 TAMMs: Temporal-Aware Multimodal Model for Satellite Image Change Understanding
    71891, -- 2506.15583 DiscoSG: Towards Discourse-Level Text Scene Graph Parsing through Iterative Grap
    71946, -- 2506.13639 An Empirical Study of LLM-as-a-Judge: How Design Choices Impact Evaluation Relia
    72192, -- 2506.06277 ExAct: A Video-Language Benchmark for Expert Action Analysis
    72334, -- 2506.02845 Go Beyond Earth: Understanding Human Actions and Scenes in Microgravity Environm
    72377, -- 2506.02095 Cycle Consistency as Reward: Learning Image-Text Alignment without Human Prefere
    72782, -- 2505.18110 Watch and Listen: Understanding Audio-Visual-Speech Moments with Multimodal LLM
    72931, -- 2505.14361 Vision-Language Modeling Meets Remote Sensing: Models, Datasets and Perspectives
    73016, -- 2505.11838 RVTBench: A Benchmark for Visual Reasoning Tasks
    73461, -- 2504.13275 ChartQA-X: Generating Explanations for Visual Chart Reasoning
    73579, -- 2504.08024 Summarizing Speech: A Comprehensive Survey
    73614, -- 2504.06666 Patch Matters: Training-free Fine-grained Image Caption Enhancement via Local Pe
    73734, -- 2504.01901 Ross3D: Reconstructive Visual Instruction Tuning with 3D-Awareness
    73933, -- 2503.17044 ExCap3D: Expressive 3D Scene Understanding via Object Captioning with Varying De
    73934, -- 2503.17039 Summarization Metrics for Spanish and Basque: Do Automatic Scores and LLM-Judges
    74026, -- 2506.12103 The Amazon Nova Family of Models: Technical Report and Model Card
    74152, -- 2503.08585 HierarQ: Task-Aware Hierarchical Q-Former for Enhanced Video Understanding
    74692, -- 2502.10118 Image Embedding Sampling Method for Diverse Captioning
    74933, -- 2502.06806 Logits are All We Need to Adapt Closed Models
    75261, -- 2501.04568 Feedback-Driven Vision-Language Alignment with Minimal Human Supervision
    75325, -- 2501.00437 Unleashing Text-to-Image Diffusion Prior for Zero-Shot Image Captioning
    75380, -- 2412.17007 Where am I? Cross-View Geo-localization with Natural Language Descriptions
    75419, -- 2412.14643 RefHCM: A Unified Model for Referring Perceptions in Human-Centric Scenarios
    75756, -- 2411.12980 LaVida Drive: Vision-Text Interaction VLM for Autonomous Driving with Token Sele
    75763, -- 2411.12593 AdaCM^2: On Understanding Extremely Long-Term Video with Adaptive Cross-Modality
    75863, -- 2411.02733 DDFAV: Remote Sensing Large Vision Language Models Dataset and Evaluation Benchm
    75985, -- 2410.16623 MotionGlot: A Multi-Embodied Motion Generation Model
    76267, -- 2405.17461 EMR-Merging: Tuning-Free High-Performance Model Merging
    76270, -- 2409.18060 Inferring Alt-text For UI Icons With Large Language Models During App Developmen
    76276, -- 2409.18046 IFCap: Image-like Retrieval and Frequency-based Entity Filtering for Zero-shot C
    76330, -- 2409.13501 HUT: A More Computation Efficient Fine-Tuning Method With Hadamard Updated Trans
    76387, -- 2409.09575 Traffic Scene Generation from Natural Language Description for Autonomous Vehicl
    76472, -- 2409.02074 RACONTEUR: A Knowledgeable, Insightful, and Portable LLM-Powered Shell Command E
    76475, -- 2409.07482 VSLLaVA: a pipeline of large multimodal foundation model for industrial vibratio
    76784, -- 2407.07433 Controllable Navigation Instruction Generation with Chain of Thought Prompting
    76842, -- 2407.01976 A Bounding Box is Worth One Token: Interleaving Layout and Text in a Large Langu
    76942, -- 2406.13424 Towards a multimodal framework for remote sensing image change retrieval and cap
    77044, -- 2406.06295 Zero-Shot Audio Captioning Using Soft and Hard Prompts
    77129, -- 2406.00258 Artemis: Towards Referential Understanding in Complex Videos
    77130, -- 2406.00257 Are Large Vision Language Models up to the Challenge of Chart Comprehension and
    77401, -- 2404.13370 Movie101v2: Improved Movie Narration Benchmark
    77583, -- 2403.16167 ESREAL: Exploiting Semantic Reconstruction to Mitigate Hallucinations in Vision-
    77685, -- 2403.03715 MeaCap: Memory-Augmented Zero-shot Image Captioning
    77695, -- 2403.02910 ImgTrojan: Jailbreaking Vision-Language Models with ONE Image
    78940, -- 2306.00830 Adapting a ConvNeXt model to audio classification on AudioSet
    82843, -- 2604.28196 HERMES++: Toward a Unified Driving World Model for 3D Scene Understanding and Ge
    82953, -- 2605.07394 BalCapRL: A Balanced Framework for RL-Based MLLM Image Captioning
    83679, -- 2604.07965 DSCA: Dynamic Subspace Concept Alignment for Lifelong VLM Editing
    83709, -- 2604.24052 QEVA: A Reference-Free Evaluation Metric for Narrative Video Summarization with
    83974, -- 2411.10639 MTA: Multimodal Task Alignment for BEV Perception and Captioning
    84092, -- 2508.21451 MM-SeR: Multimodal Self-Refinement for Lightweight Image Captioning
    84143, -- 2510.27680 PETAR: Localized Findings Generation with Mask-Aware Vision-Language Modeling fo
    84261, -- 2511.21191 Scenes as Tokens: Multi-Scale Normal Distributions Transform Tokenizer for Gener
    84314, -- 2512.02487 Masking Matters: Unlocking the Spatial Reasoning Capabilities of LLMs for 3D Sce
    84411, -- 2512.16250 AMusE: Audio-Visual Benchmark and Alignment Framework for Agentic Multi-Speaker
    84552, -- 2602.19418 PA-Attack: Guiding Gray-Box Attacks on LVLM Vision Encoders with Prototypes and
    84562, -- 2602.19668 Personalized Longitudinal Medical Report Generation via Temporally-Aware Federat
    84633, -- 2602.22868 Rejection Mixing: Fast Semantic Propagation of Mask Tokens for Efficient DLLM In
    84640, -- 2602.23153 Efficient Encoder-Free Fourier-based 3D Large Multimodal Model
    84763, -- 2603.05437 SAIL: Similarity-Aware Guidance and Inter-Caption Augmentation-based Learning fo
    84853, -- 2603.11439 Stay in your Lane: Role Specific Queries with Overlap Suppression Loss for Dense
    84854, -- 2603.11460 Follow the Saliency: Supervised Saliency for Retrieval-augmented Dense Video Cap
    84879, -- 2603.12760 HiFICL: High-Fidelity In-Context Learning for Multimodal Tasks
    85192, -- 2603.28605 Unsafe2Safe: Controllable Image Anonymization for Downstream Utility
    85280, -- 2604.04857 The Blind Spot of Adaptation: Quantifying and Mitigating Forgetting in Fine-tune
    85415, -- 2604.18260 Geometry-Guided 3D Visual Token Pruning for Video-Language Models
    85560, -- 2605.14938 Octopus: History-Free Gradient Orthogonalization for Continual Learning in Multi
    85989, -- 2412.06646 The Narrow Gate: Localized Image-Text Communication in Vision-Language Models
    86682, -- 2505.16334 Panoptic Captioning: Seeking An Equivalency Bridge for Image and Text
    86711, -- 2412.01930 PROFIT: A Specialized Optimizer for Deep Fine Tuning
    87012, -- 2502.05435 Unbiased Sliced Wasserstein Kernels for High-Quality Audio Captioning
    87112, -- 2503.22215 Learning to Instruct for Visual Instruction Tuning
    87508, -- 2605.29588 Brain-IT-VQA: From Brain Signals to Answers
    87566, -- 2503.10663 Optimal Transport for Brain-Image Alignment: Unveiling Redundancy and Synergy in
    87628, -- 2411.13076 Hints of Prompt: Enhancing Visual Representation for Multimodal LLMs in Autonomo
    87867, -- 2507.06072 MCAM: Multimodal Causal Analysis Model for Ego-Vehicle-Level Driving Video Under
    87898, -- 2508.07312 MobileViCLIP: An Efficient Video-Text Model for Mobile Devices
    87980, -- 2503.10079 Information Density Principle for MLLM Benchmarks
    88061, -- 2507.01409 CaptionSmiths: Flexibly Controlling Language Pattern in Image Captioning
    88074, -- 2503.19755 ORION: A Holistic End-to-End Autonomous Driving Framework by Vision-Language Ins
    88154, -- 2503.21505 Fine-Grained Evaluation of Large Vision-Language Models in Autonomous Driving
    88274, -- 2503.23219 AURELIA: Test-time Reasoning Distillation in Audio-Visual LLMs
    88342, -- 2509.12145 Open-ended Hierarchical Streaming Video Understanding with Vision Language Model
    88397, -- 2507.20163 Player-Centric Multimodal Prompt Generation for Large Language Model Based Ident
    88454, -- 2505.15755 Exploring The Visual Feature Space for Multimodal Neural Decoding
    89597, -- 2407.18941 LEMoN: Label Error Detection using Multimodal Neighbors
    90110, -- 2502.18290 Stealthy Backdoor Attack in Self-Supervised Learning Vision Encoders for Large V
    90151, -- 2503.01725 HarmonySet: A Comprehensive Dataset for Understanding Video-Music Semantic Align
    90168, -- 2406.18844 Revisiting Backdoor Attacks against Large Vision-Language Models from Domain Shi
    90234, -- 2501.09754 Lost in Translation, Found in Context: Sign Language Translation with Contextual
    90281, -- 2503.13108 Lifting the Veil on Visual Information Flow in MLLMs: Unlocking Pathways to Fast
    90314, -- 2407.03314 BACON: Improving Clarity of Image Captions via Bag-of-Concept Graphs
    90386, -- 2411.08753 Which Viewpoint Shows it Best? Language for Weakly Supervising View Selection in
    90410, -- 2503.23024 Empowering Large Language Models with 3D Situation Awareness
    90460, -- 2412.08614 Benchmarking Large Vision-Language Models via Directed Scene Graph for Comprehen
    90633, -- 2503.10078 Image Quality Assessment: From Human to Machine Preference
    90694, -- 2403.12922 Contextual AD Narration with Interleaved Multimodal Sequence
    90705, -- 2504.01472 ANNEXE: Unified Analyzing, Answering, and Pixel Grounding for Egocentric Interac
    90727, -- 2411.15231 IterIS: Iterative Inference-Solving Alignment for LoRA Merging
    90788, -- 2503.17417 Generative Modeling of Class Probability for Multi-Modal Representation Learning
    91222, -- 2503.05977 Is Your Video Language Model a Reliable Judge?
    91884, -- 2410.01264 Backdooring Vision-Language Models with Out-Of-Distribution Data
    92344, -- 2410.15143 Budgeted Online Continual Learning by Adaptive Layer Freezing and Frequency-base
    92492, -- 2606.04433 Stateful Visual Encoders for Vision-Language Models
    93190, -- 2504.01735 AdPO: Enhancing the Adversarial Robustness of Large Vision-Language Models with
    93430, -- 2505.23209 Navigating the Accuracy-Size Trade-Off with Flexible Model Merging
    94464, -- 2603.05867 TumorChain: Interleaved Multimodal Chain-of-Thought Reasoning for Traceable Clin
    94713, -- 2512.15420 FlowBind: Efficient Any-to-Any Generation with Bidirectional Flows
    94732, -- 2601.22570 Leveraging Data to Say No: Memory Augmented Plug-and-Play Selective Prediction
    94895, -- 2507.18578 Wide-In, Narrow-Out: Revokable Decoding for Efficient and Effective DLLMs
    95039, -- 2505.17440 VEAttack: Downstream-agnostic Vision Encoder Attack against Large Vision Languag
    95608, -- 2501.17022 Mobile Manipulation Instruction Generation from Multiple Images with Automatic M
    95923, -- 2502.14917 Sce2DriveX: A Generalized MLLM Framework for Scene-To-Drive Learning
    96211, -- 2605.16892 DriveSafe: A Framework for Risk Detection and Safety Suggestions in Driving Scen
    99035, -- 2606.31292 AtomiMed: Hierarchical Atomic Fact-Checking for Universal Clinical-Aware Medical
    102297, -- 2507.05258 Spatio-Temporal LLM: Reasoning about Environments and Actions
    102994, -- 2604.05887 HybridKV: Hybrid KV Cache Compression for Efficient Multimodal Large Language Mo
    103363, -- 2604.17407 Think before Go: Hierarchical Reasoning for Image-goal Navigation
    103966, -- 2508.21809 VoCap: Video Object Captioning and Segmentation from Any Prompt
    104341, -- 2406.12384 VRSBench: A Versatile Vision-Language Benchmark Dataset for Remote Sensing Image
    105772, -- 2408.12141 TRRG: Towards Truthful Radiology Report Generation With Cross-modal Disease Clue
    106479, -- 2601.17258 FineVAU: A Novel Human-Aligned Benchmark for Fine-Grained Video Anomaly Understa
    106573, -- 2511.12259 A Disease-Aware Dual-Stage Framework for Chest X-ray Report Generation
    106629, -- 2512.21582 LLM-Free Image Captioning Evaluation in Reference-Flexible Settings
    106637, -- 2511.22903 Leveraging Textual Compositional Reasoning for Robust Change Captioning
    106734, -- 2511.17053 OmniPT: Unleashing the Potential of Large Vision Language Models for Pedestrian
    106815, -- 2505.04201 STOLA: Self-Adaptive Touch-Language Framework for Tactile Commonsense Reasoning
    106920, -- 2511.10134 Explicit Temporal-Semantic Modeling for Dense Video Captioning via Context-Aware
    107174, -- 2411.17130 TechCoach: Towards Technical-Point-Aware Descriptive Action Coaching
    107307, -- 2511.08238 Remodeling Semantic Relationships in Vision-Language Fine-Tuning
    107559, -- 2505.23484 VCapsBench: A Large-scale Fine-grained Benchmark for Video Caption Quality Evalu
    107639, -- 2512.14420 DISCODE: Distribution-Aware Score Decoder for Robust Automatic Evaluation of Ima
    107793, -- 2504.09862 RadarLLM: Empowering Large Language Models to Understand Human Motion from Milli
    107832, -- 2511.08909 Negative Entity Suppression for Zero-Shot Captioning with Synthetic Images
    107873, -- 2411.17301 ReFINE: A Reward-Based Framework for Interpretable and Nuanced Evaluation of Rad
    108351, -- 2511.08977 Efficient and Effective In-context Demonstration Selection with Coreset
    108451, -- 2511.18286 RoadSceneVQA: Benchmarking Visual Question Answering in Roadside Perception Syst
    108527, -- 2503.19361 ImageSet2Text: Describing Sets of Images Through Text
    108649, -- 2608.02589 CAPEval: A Decoupled Caption Evaluation across Understanding and Generation
    108683, -- 2605.20278 ClaimDiff-RL: Fine-Grained Caption Reinforcement Learning through Visual Claim C
    109008, -- 2608.04302 CLIP-CC-Bench: Evaluating Paragraph-Level Video Descriptions in Video-Language M
    109367, -- 2608.15984 A Plug-and-Play 2D Motion Interface for Real-World Motion Language Models
    109911, -- 2405.17427 Reason3D: Searching and Reasoning 3D Segmentation via Large Language Model
    109965, -- 2505.17098 TACO: Enhancing Multimodal In-context Learning via Task Mapping-Guided Sequence
    109977, -- 2510.24134 VC4VG: Optimizing Video Captions for Text-to-Video Generation
    110110, -- 2411.17771 Diagram-Driven Course Questions Generation
    110201, -- 2509.25818 VELA: An LLM-Hybrid-as-a-Judge Approach for Evaluating Long Image Captions
    110347, -- 2503.07663 Merge then Realign: Simple and Effective Modality-Incremental Continual Learning
    110606, -- 2510.07892 Metric Calculating Benchmark: Code-Verifiable Complicate Instruction Following B
    110707, -- 2510.00808 What You See is What You Ask: Evaluating Audio Descriptions
    110781, -- 2509.04602 Sali4Vid: Saliency-Aware Video Reweighting and Adaptive Caption Retrieval for De
    111045, -- 2402.17008 Benchmarking LLMs on Semantic Overlap Summarization
    111158, -- 2505.13062 Hearing from Silence: Reasoning Audio Descriptions from Silent Videos via Vision
    111159, -- 2505.22045 Mitigating Audiovisual Mismatch in Visual-Guide Audio Captioning
    111595, -- 2410.10913 Enhancing Retrieval-Augmented Audio Captioning with Generation-Assisted Multimod
    111680, -- 2506.00800 CLAP-ART: Automated Audio Captioning with Semantic-rich Audio Representation Tok
    112596, -- 2403.11835 Agent3D-Zero: An Agent for Zero-shot 3D Understanding
    112641, -- 2407.15087 Navigation Instruction Generation with BEV Perception and Large Language Models
    112692, -- 2404.01700 MotionChain: Conversational Motion Controllers via Multimodal Prompts
    112958, -- 2407.14474 Learning with Counterfactual Explanations for Radiology Report Generation
    112963, -- 2407.11683 Distractors-Immune Representation Learning with Cross-modal Contrastive Regulari
    113198, -- 2407.02218 Multi-Modal Video Dialog State Tracking in the Wild
    113201, -- 2403.12445 Boosting Transferability in Vision-Language Attacks via Diversification along th
    113302, -- 2407.01851 Meerkat: Audio-Visual Large Language Model for Grounding in Space and Time
    113324, -- 2408.02272 COM Kitchens: An Unedited Overhead-view Procedural Videos Dataset a Vision-Langu
    113357, -- 2407.11393 CIC-BART-SSA: : Controllable Image Captioning with Structured Semantic Augmentat
    113803, -- 2608.29335 GenFirst: Generation Before Reconstruction for Stable End-to-End Latent Generati
    114038, -- 2609.08345 CoVeR: Coverage-Based Token Pruning for Multi-View 3D Reasoning in VLMs
    114039, -- 2609.07941 ReactVAU: A Slow-Fast Decoupled Framework for Streaming Video Anomaly Understand
    115039, -- 2409.05370 KARGEN: Knowledge-enhanced Automated Radiology Report Generation Using Large Lan
    115803, -- 2404.07610 Do You Remember? Dense Video Captioning with Cross-Modal Memory Retrieval
    115888, -- 2405.11483 MICap: A Unified Model for Identity-Aware Movie Descriptions
    116512, -- 2403.13263 SC-Tune: Unleashing Self-Consistent Referential Comprehension in Large Vision La
    116904, -- 2404.14471 Narrative Action Evaluation with Prompt-Guided Multimodal Interaction
    116946, -- 2404.05621 MULTIFLOW: Shifting Towards Task-Agnostic Vision-Language Pruning
    117002, -- 2406.06730 TRINS: Towards Multimodal Language Models that Can Read
    117092, -- 2404.03242 Would Deep Generative Models Amplify Bias in Future Models?
    118154, -- 2608.06901 Prune Once: Retraining-Free Task-Agnostic Pruning for Vision-Language Models
    119214, -- 2607.11199 DynEval: Holistic Evaluations of T2I Generative Models in the Wild
    119423, -- 2607.11798 StoryTeller: Training-Free Narrative Grounding for Long-Form Audio Description
    119484, -- 2604.14129 Don't Let the Video Speak: Audio-Contrastive Preference Optimization for Audio-v
    119586, -- 2606.25445 C3-Bench: A Context-Aware Change Captioning Benchmark
    119623, -- 2607.23917 Gaze-to-text Generation: Beyond Categorical Decoding of Human Attention
    119696, -- 2506.16112 AutoV: Loss-Oriented Ranking for Visual Prompt Retrieval in LVLMs
    119957, -- 2410.00379 CXPMRG-Bench: Pre-training and Benchmarking for X-ray Medical Report Generation
    120141, -- 2504.05457 Taxonomy-Aware Evaluation of Vision-Language Models
    120381, -- 2503.02063 V^2Dial: Unification of Video and Visual Dialog via Multimodal Experts
    120404, -- 2412.06171 Holmes-VAU: Towards Long-term Video Anomaly Understanding at Any Granularity
    121312, -- 2605.08808 Curvature-Aware Captioning: Leveraging Geodesic Attention for 3D Scene Understan
    121895, -- 2507.04678 ChangeBridge: Spatiotemporal Image Generation with Multimodal Controls for Remot
    122469, -- 2609.38177 Imagine3D-LLM: Teaching MLLMs to Imagine 3D Scenes Before Answering
    122590, -- 2609.40362 Multimodal Flow: Unified Flow Modeling of Language and Vision in Embedding Space
    122973, -- 2610.12458 OmniCapBench: A Deep-Structured Evaluation Framework for Fine-Grained Audio-Visu
    123403, -- 2610.16135 Omni-Modal LLMs Know More Than They Say
    123480, -- 2610.17771 Many Right Answers, One Training Example: Removing Responder Noise from GRPO for
    123509, -- 2610.18598 Rethinking Projector Training in Multimodal LLMs
    125462, -- 2512.08040 Lost in Translation, Found in Embeddings: Sign Language Translation and Alignmen
    126778, -- 2605.13803 EvoGround: Self-Evolving Video Agents for Video Temporal Grounding
    127346, -- 2606.16408 MUNI: Multimodal Unified Latent Diffusion for Coherent Any-to-Any Generation
    127488, -- 2610.21588 Hear, Localize, and Reason: Spatially Aware Scene Understanding for Audio-visual
    128507, -- 2610.12673 MindVLM: Neural-Grounded Visual Captioning via Subject-Aware Semantic Evidence S
    128598, -- 2605.15325 COPRA: Conditional Parameter Adaptation with Reinforcement Learning for Video An
    131225 -- 2609.35407 BiMoGen: Bidirectional Motion-Text Generation via Unified Masked Discrete Diffus
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'metrics curation 2026-11-10: cites the source paper but the title/abstract does not name the metric'
FROM cider_citers_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING cider_citers_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING cider_citers_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- elo-rating: 36 links (title/abstract names the metric).
CREATE TEMP TABLE elo_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'elo-rating'
  AND p.id IN (
    18055, -- 2307.03025 Style Over Substance: Evaluation Biases for Large Language Models
    21866, -- 2310.08235 GROOT: Learning to Follow Instructions by Watching Gameplay Videos
    23941, -- 2311.17295 Elo Uncovered: Robustness and Best Practices in Language Model Evaluation
    25587, -- 2401.04092 GPT-4V(ision) is a Human-Aligned Evaluator for Text-to-3D Generation
    28750, -- 2403.07872 Rethinking Generative Large Language Model Evaluation for Semantic Comprehension
    30259, -- 2404.08008 Sample-Efficient Human Evaluation of Large Language Models via Maximum Discrepan
    32473, -- 2406.04460 Evaluating the Smooth Control of Attribute Intensity in Text Generation with LLM
    32497, -- 2406.04770 WildBench: Benchmarking LLMs with Challenging Tasks from Real Users in the Wild
    33444, -- 2406.14783 Evaluating RAG-Fusion with RAGElo: an Automated Elo-based Framework
    40763, -- 2412.00539 TextClass Benchmark: A Continuous Elo Rating of LLMs in Social Sciences
    42414, -- 2501.01257 CodeElo: Benchmarking Competition-level Code Generation of LLMs with Human-compa
    43550, -- 2502.01126 Language Models Prefer What They Know: Relative Confidence Estimation via Confid
    45155, -- 2502.20170 Re-evaluating Open-ended Evaluation of Large Language Models
    47423, -- 2504.06148 V-MAGE: A Game Evaluation Framework for Assessing Vision-Centric Capabilities in
    47646, -- 2504.10045 CHARM: Calibrating Reward Models With Chatbot Arena Scores
    52638, -- 2509.02722 Planning with Reasoning using Vision Language World Model
    53174, -- 2510.02306 Drawing Conclusions from Draws: Rethinking Preference Semantics in Arena-Style L
    53415, -- 2510.08697 BigCodeArena: Unveiling More Reliable Human Preferences in Code Generation via E
    60951, -- 2601.07651 Active Evaluation of General Agents: Problem Definition and Comparison of Baseli
    64806, -- 2511.15958 JudgeBoard: Benchmarking and Enhancing Small Language Models for Reasoning Evalu
    70446, -- 2508.02725 Forecasting NCAA Basketball Outcomes with Deep Learning: A Comparative Study of
    78420, -- 2310.03354 Fictitious Cross-Play: Learning Global Nash Equilibrium in Mixed Cooperative-Com
    81599, -- 1909.09849 Multiagent Evaluation under Incomplete Information
    87076, -- 2504.18530 Scaling Laws For Scalable Oversight
    89575, -- 2501.17858 Improving Your Model Ranking on Chatbot Arena by Vote Rigging
    93859, -- 2510.02279 Addressing Pitfalls in the Evaluation of Uncertainty Estimation Methods for Natu
    98913, -- 2606.27608 Qwen-Image-2.0-RL Technical Report
    102411, -- 2606.08656 From Player to Master: Enhancing Test-Time Learning of LLM Agents via Reinforcem
    108309, -- 2508.09724 UDA: Unsupervised Debiasing Alignment for Pair-wise LLM-as-a-Judge
    108633, -- 2206.12301 On the Limitations of Elo: Real-World Games, are Transitive, not Additive
    110941, -- 2509.23510 Model Consistency as a Cheap yet Predictive Proxy for LLM Elo Scores
    114222, -- 2609.15309 When Agents Slow Down: Understanding LLM Agents' Test-Time Strategies via Elo-pe
    120193, -- 2412.00505 Good, Cheap, and Fast: Overfitted Image Compression with Wasserstein Distortion
    122175, -- 2609.24308 HappyWorld-Bench
    122969, -- 2610.02967 Post-Training Frontier Text-to-Image Models by Composing Preference and Rubric R
    130750 -- 2606.13221 From Uncertain Judgments to Calibrated Rankings: Conformal Elo Estimation for LL
  );

DELETE FROM paper_method_exclusions x
USING elo_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM elo_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM elo_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Method image credits (figures imported with import_entity_image.py).
-- PSNR, mAP and Perplexity have no image: no suitable openly licensed figure.
UPDATE methods SET image_credit = '[The Unreasonable Effectiveness of Deep Features as a Perceptual Metric](/paper/1801.03924)' WHERE slug = 'lpips';
UPDATE methods SET image_credit = '[BERTScore: Evaluating Text Generation with BERT](/paper/1904.09675)' WHERE slug = 'bertscore';
UPDATE methods SET image_credit = '[CIDEr: Consensus-based Image Description Evaluation](/paper/1411.5726)' WHERE slug = 'cider';
UPDATE methods SET image_credit = '[Intersection over Union - visual equation](https://commons.wikimedia.org/wiki/File:Intersection_over_Union_-_visual_equation.png), Adrian Rosebrock, CC BY-SA 4.0' WHERE slug = 'intersection-over-union-iou';
UPDATE methods SET image_credit = '[MSE, SSIM, CWSSIM comparison 8 images](https://commons.wikimedia.org/wiki/File:MSE,_SSIM,_CWSSIM_comparison_8_images.jpg), Francis roxas, CC BY-SA 4.0' WHERE slug = 'ssim';
UPDATE methods SET image_credit = '[Elo rating graph](https://commons.wikimedia.org/wiki/File:Elo_rating_graph.svg), Cmglee, CC BY-SA 3.0' WHERE slug = 'elo-rating';
