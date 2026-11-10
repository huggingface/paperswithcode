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
    'perplexity', 'Perplexity',
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
    'psnr', 'PSNR',
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
    'ssim', 'SSIM',
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
    'lpips', 'LPIPS',
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
    'bertscore', 'BERTScore', 'BERTScore',
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
    'cider', 'CIDEr',
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
    60, 85, 306, 336, 445, 463, 495, 833, 1000, 1076, 1332, 1535, 1744, 1769, 1799, 2200,
    2523, 2561, 2871, 3035, 3214, 3405, 3448, 3485, 3584, 3951, 4126, 4147, 4383, 4818, 4824, 4828,
    5118, 5742, 5827, 5858, 6404, 6499, 6538, 6681, 6900, 7002, 7085, 7670, 7801, 7837, 7908, 8232,
    8269, 8414, 8737, 8755, 9239, 9370, 9543, 9789, 9930, 10941, 11059, 11091, 11426, 11478, 11648, 12133,
    12244, 12279, 12954, 14256, 14687, 14813, 14868, 14888, 15671, 15790, 16020, 16073, 16107, 16142, 16217, 16327,
    16412, 16516, 16736, 16825, 16988, 17347, 17513, 17710, 17908, 18041, 18213, 18365, 18743, 19024, 19204, 19408,
    19577, 19943, 20018, 20097, 20231, 20318, 20645, 20670, 20875, 21208, 21247, 21295, 21518, 21657, 21816, 21939,
    22006, 22180, 22374, 22419, 22444, 22571, 22620, 22919, 22941, 23092, 23160, 23305, 23426, 23646, 24269, 24494,
    24577, 24607, 24723, 24818, 24876, 24889, 25061, 25927, 26058, 26093, 26123, 26187, 26201, 26432, 26502, 26508,
    26547, 26707, 26783, 26843, 26913, 26940, 26947, 27001, 27301, 27324, 27339, 27344, 27347, 27479, 27565, 27582,
    27650, 27707, 27853, 27910, 27989, 28088, 28164, 28787, 28875, 28946, 29100, 29268, 29314, 29347, 29368, 29369,
    29701, 29760, 29851, 29896, 29957, 30112, 30372, 30656, 30702, 30893, 31108, 31183, 31288, 31642, 31690, 31825,
    31891, 31970, 32112, 32227, 32329, 32386, 32398, 32457, 32562, 32589, 32636, 32689, 32696, 32705, 32729, 32730,
    32755, 33003, 33066, 33191, 34212, 34220, 34266, 34368, 34395, 34593, 34596, 35054, 35327, 35328, 35360, 35438,
    35545, 35561, 35653, 35816, 35847, 35874, 35891, 35992, 36166, 36222, 36249, 36588, 36668, 36703, 36791, 36797,
    36976, 36986, 37051, 37327, 37352, 37546, 37727, 37783, 37790, 38111, 38146, 38190, 38212, 38372, 38478, 38535,
    38586, 38635, 38691, 38830, 38892, 38915, 38919, 39076, 39302, 39522, 39761, 39803, 39874, 39888, 40121, 40260,
    40276, 40512, 40524, 40537, 40912, 41009, 41389, 41621, 41663, 41867, 42112, 42482, 42537, 42584, 42737, 42768,
    43046, 43110, 43194, 43309, 43377, 43480, 43506, 43578, 43642, 43706, 44096, 44169, 44243, 44271, 44372, 44408,
    44490, 44903, 44922, 44955, 44960, 45074, 45083, 45084, 45133, 45145, 45162, 45282, 45328, 45333, 45363, 45376,
    45433, 45731, 45799, 45820, 45843, 45886, 45908, 46926, 46953, 46980, 47111, 47404, 47910, 48285, 48287, 48300,
    48748, 48762, 48763, 48957, 49098, 49176, 49181, 49304, 49357, 49612, 49616, 49699, 49733, 49783, 49881, 50045,
    50054, 50166, 50267, 50414, 50436, 50515, 50719, 51034, 51139, 51214, 51230, 51668, 51875, 52110, 52182, 52277,
    52331, 52361, 52598, 52707, 52747, 52798, 52967, 53102, 53133, 53442, 53642, 53785, 53806, 54653, 54758, 54944,
    55080, 55259, 55379, 55480, 55513, 55534, 55538, 55650, 55787, 55843, 55866, 56116, 56162, 56218, 56234, 56283,
    56612, 56731, 56815, 56844, 57172, 57397, 57422, 57425, 57473, 57499, 57547, 57574, 58048, 58170, 58189, 58213,
    58329, 58400, 58508, 58515, 58530, 58559, 58639, 58707, 58731, 58735, 58755, 58791, 58843, 58902, 58980, 59028,
    59085, 59204, 59273, 59313, 59336, 59401, 59441, 59489, 59574, 59864, 59891, 60003, 60167, 60447, 60578, 60598,
    60970, 61053, 61185, 61699, 62008, 62274, 62312, 62585, 62617, 62669, 62815, 63132, 63141, 63159, 63537, 63747,
    64106, 64184, 64544, 65041, 65059, 65190, 65378, 65440, 65561, 65565, 65625, 65741, 65772, 65908, 65920, 66039,
    66072, 66103, 66195, 66785, 66867, 66911, 67017, 67265, 67326, 67417, 67432, 67477, 67847, 68128, 68247, 68340,
    68682, 68687, 68693, 68755, 68895, 68902, 68906, 69184, 69275, 69386, 69398, 69508, 69559, 69730, 70101, 70120,
    70207, 70282, 70319, 70324, 70514, 71175, 71237, 71507, 71533, 71534, 71617, 71681, 71824, 71849, 71893, 72128,
    72221, 72326, 72499, 72604, 72687, 72753, 72760, 72851, 72910, 73130, 73209, 73241, 73275, 73404, 73461, 73627,
    73641, 73666, 74128, 74208, 74243, 74260, 74337, 74536, 74657, 74658, 74680, 74762, 74768, 75438, 75896, 75983,
    76030, 76614, 76674, 76791, 76839, 77114, 77510, 77765, 78244, 78276, 78408, 81591, 81595, 82839, 82873, 82881,
    83163, 83262, 83284, 83400, 83463, 83538, 83614, 83735, 83955, 83960, 85732, 85987, 86097, 86222, 86435, 87177,
    87239, 88674, 88701, 88720, 88928, 89158, 89161, 89489, 90075, 91031, 91143, 91211, 91422, 91468, 91592, 91645,
    91653, 91779, 91868, 92165, 92254, 92295, 92713, 92986, 93090, 93153, 93173, 93335, 93362, 93661, 93710, 93853,
    94031, 94119, 94142, 94198, 94272, 94560, 94598, 94691, 94852, 94884, 94984, 94987, 97932, 97938, 97973, 98105,
    98177, 98178, 98207, 98699, 98730, 98761, 98778, 98872, 98982, 99066, 99530, 99667, 99929, 100298, 100309, 100327,
    100533, 100737, 100793, 100836, 100885, 100890, 101107, 101286, 101407, 101454, 101493, 101698, 101779, 101834, 102032, 102155,
    102219, 102288, 102332, 102713, 102949, 103142, 103201, 103202, 103254, 103302, 103380, 103400, 103502, 103738, 103828, 104010,
    104214, 104289, 104458, 105855, 105859, 106128, 106292, 106320, 106368, 107774, 108712, 108775, 108858, 109066, 109112, 109375,
    109519, 109948, 110031, 110154, 110245, 110255, 110287, 110318, 110448, 110682, 110816, 110949, 111069, 111167, 111380, 113189,
    113912, 113922, 114016, 114292, 119664, 122307, 122321, 122323, 122387, 122467, 122557, 122660, 122715, 122732, 122767, 122847,
    123419, 123721, 123835, 123904, 124012, 124150, 124373, 124629, 124900, 124977, 125033, 125152, 125261, 125268, 125287, 125475,
    125600, 125647, 125649, 125700, 125733, 125824, 126056, 126145, 126429, 126592, 126613, 126830, 126840, 126847, 126907, 127114,
    127296, 127534, 127546, 127676, 127685, 127745, 127782, 127849, 127860, 127863, 127905, 128111, 128112, 128255, 128461, 128562,
    128676, 128781, 128846, 128881, 128912, 128943, 129114, 129232, 129405, 129545, 129582, 129961, 130129, 130265, 130714, 130760,
    130972, 131019, 131034, 131051, 131181, 131258, 131276, 131427, 131465, 131624, 131636, 131661, 131764, 131791, 131816, 131958,
    132006, 132008, 132009, 132014, 132016, 132019, 132025, 132034, 132041, 132044, 132053, 132054, 132058, 132064, 132065, 132066
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
    21424, 23360, 35310, 37096, 39348, 39654, 40131, 46771, 51115, 60780, 61889, 63501, 66358, 68849, 77326, 91745,
    106146, 108882, 114094, 123483, 123865
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
    37, 1050, 1504, 2122, 3762, 3763, 4529, 4613, 5431, 5557, 5765, 6315, 7251, 7660, 8218, 8516,
    8629, 8652, 9024, 9136, 9143, 9260, 10156, 10183, 10349, 10714, 11159, 11510, 11732, 12004, 12258, 12381,
    12546, 13776, 13850, 14345, 14484, 14545, 14770, 15784, 17176, 17230, 17616, 19303, 19486, 19549, 19915, 19946,
    20063, 20202, 20367, 20802, 22946, 23641, 23918, 23922, 24215, 24634, 24727, 24829, 24965, 25043, 25700, 25798,
    25837, 26177, 26390, 27145, 27816, 28026, 28056, 28247, 28622, 29039, 29261, 29446, 29600, 30404, 30985, 31588,
    32008, 32210, 32557, 32713, 33571, 33749, 34317, 34391, 34648, 34798, 35368, 36268, 36406, 36692, 36882, 36995,
    37574, 37586, 37643, 37986, 37995, 38321, 38951, 39015, 39441, 40163, 40262, 40305, 40312, 40342, 40516, 40785,
    40905, 41013, 41496, 41768, 41970, 42105, 42233, 42252, 43001, 43093, 44142, 45335, 45724, 45736, 46283, 46420,
    46853, 46883, 47293, 47586, 47587, 47700, 47728, 47894, 48319, 48591, 49319, 49660, 50225, 50241, 50482, 50490,
    50789, 50904, 51420, 51801, 51829, 51830, 52519, 52849, 52858, 53390, 53568, 53667, 54637, 54737, 55045, 55074,
    55577, 55629, 55747, 56201, 56528, 56560, 56623, 56747, 56792, 57011, 57478, 57503, 57717, 57850, 58101, 58324,
    58334, 58412, 58558, 58790, 58858, 58916, 59005, 59039, 59772, 60254, 60330, 60519, 60649, 61260, 61680, 62637,
    62915, 63294, 63345, 63534, 63729, 63992, 64110, 64237, 64289, 64346, 64525, 64640, 64718, 64850, 65266, 65304,
    65473, 65956, 66856, 67527, 68008, 68114, 68567, 68923, 69168, 69483, 69732, 69738, 69755, 69800, 69877, 70043,
    70262, 70302, 70507, 70556, 70756, 71221, 71263, 71469, 72006, 72380, 73326, 73379, 73445, 73555, 73576, 73593,
    74165, 74178, 74199, 74400, 75110, 75246, 75319, 75585, 75706, 75772, 76404, 76568, 76569, 77390, 77402, 77422,
    77672, 79154, 79635, 80130, 80577, 80751, 80858, 81118, 81132, 82105, 83303, 83619, 83831, 84133, 84193, 84350,
    84453, 84675, 84678, 84679, 84755, 84801, 84819, 84864, 84902, 85026, 85057, 85164, 85184, 85240, 85343, 85400,
    85464, 85480, 85598, 85730, 87035, 87101, 87629, 87847, 88025, 88059, 88103, 88221, 88242, 88462, 88502, 88517,
    88518, 90104, 90126, 90138, 90152, 90255, 90303, 90566, 90599, 90615, 90739, 90912, 90929, 90949, 92542, 92612,
    92657, 94207, 94284, 94566, 94584, 94801, 94944, 95406, 95667, 96031, 96122, 96389, 96807, 96914, 97033, 97161,
    97888, 98028, 98030, 98033, 98052, 98057, 98074, 98083, 98100, 98342, 98558, 98604, 98606, 99212, 99664, 99699,
    100040, 100098, 102430, 102606, 102675, 103899, 103915, 103916, 104257, 104335, 104336, 104347, 104352, 104359, 104360, 104363,
    104368, 104510, 104558, 104720, 104725, 104978, 105003, 105009, 105028, 105049, 105069, 105081, 105160, 105200, 105317, 105656,
    105833, 105952, 106013, 106604, 106630, 106833, 106884, 107226, 107403, 107496, 107498, 107528, 107749, 107794, 108184, 108286,
    108352, 108420, 108484, 108609, 108817, 108945, 109413, 109416, 109417, 109422, 112425, 112440, 112499, 112506, 112717, 112843,
    112858, 112908, 113116, 113355, 113374, 113381, 113439, 113486, 113508, 113571, 113660, 113950, 113951, 114192, 114207, 114433,
    114464, 114828, 114831, 114957, 114960, 115010, 115015, 115094, 115168, 115234, 115329, 115404, 115611, 115830, 116079, 116194,
    116429, 116474, 116523, 116606, 116744, 116834, 116860, 116888, 116990, 117087, 117333, 117353, 117359, 117374, 117424, 117468,
    117470, 117488, 117544, 117718, 117781, 117829, 117905, 117936, 118543, 118608, 119231, 119394, 119478, 119846, 119861, 119976,
    120119, 120154, 120317, 120355, 120428, 120626, 120721, 120943, 120951, 120961, 120963, 121113, 121140, 121165, 121476, 121531,
    121557, 121630, 121751, 122089, 122365, 122422, 122463, 122565, 122587, 122755, 122775, 122916, 122947, 123019, 123020, 123198,
    123382, 123593, 123966, 124069, 124074, 124277, 124850, 124908, 125026, 125074, 125114, 125163, 125532, 125805, 125949, 126377,
    126899, 127368, 128586, 128891, 128902, 129306, 129515, 129516, 129576, 129665, 130257, 130258, 130308, 130324, 130591, 131010,
    131077, 131088, 131098, 131203, 131220, 131619, 131623, 131900, 131901
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
    37, 267, 1050, 2122, 3762, 3763, 4550, 4592, 4722, 4985, 5097, 5210, 5431, 6242, 6315, 7604,
    7931, 8218, 9024, 9136, 9143, 9469, 11159, 11372, 11510, 12546, 15783, 17176, 18172, 19189, 19549, 19806,
    19940, 20063, 20802, 21671, 22702, 23641, 24215, 24263, 24634, 24829, 25798, 25837, 26665, 26672, 28182, 29039,
    29261, 29677, 30253, 31588, 33571, 34317, 34391, 34489, 34648, 35057, 36406, 36882, 37574, 37586, 37600, 37643,
    37773, 37995, 38951, 39091, 39181, 39357, 40312, 41496, 41768, 42252, 42526, 43001, 43093, 44142, 45689, 45724,
    47350, 47561, 47587, 47590, 47728, 48319, 48591, 48827, 49690, 50225, 50355, 50789, 50904, 52285, 53667, 55074,
    55747, 55956, 56528, 56560, 57954, 58324, 58334, 58412, 58790, 58870, 59039, 59413, 59730, 60409, 60649, 61680,
    61710, 62637, 62915, 63325, 63345, 63729, 63992, 64165, 64237, 64289, 64346, 64636, 64718, 65118, 65266, 65473,
    66856, 67527, 68022, 68091, 68595, 69168, 69483, 69738, 69800, 69877, 70271, 70302, 70397, 70556, 70756, 71221,
    72380, 73326, 73379, 73555, 74165, 75110, 75229, 75660, 75772, 76009, 76569, 77253, 77390, 77402, 77501, 77964,
    78717, 79376, 80130, 80858, 81118, 81244, 82105, 83831, 84083, 84133, 84675, 84679, 84755, 85400, 85598, 86248,
    87101, 87847, 90144, 90920, 92657, 94238, 95406, 96863, 97033, 97080, 97161, 97546, 98030, 98052, 98073, 98074,
    98083, 98100, 98246, 98604, 99983, 102058, 102430, 104334, 104335, 104336, 104345, 104347, 104348, 104350, 104352, 104359,
    104368, 104510, 105003, 105009, 105069, 105081, 105200, 105207, 105284, 105512, 105833, 105952, 106013, 107490, 107498, 107794,
    107865, 108113, 108521, 109416, 109417, 112425, 112474, 113508, 113571, 114192, 114385, 114421, 114433, 114911, 114960, 115010,
    115015, 115094, 115139, 115404, 116606, 116860, 117096, 117359, 117426, 117526, 117615, 117754, 118542, 119861, 120154, 120193,
    120795, 121140, 122032, 122089, 122193, 122775, 122916, 122917, 123593, 124251, 124850, 124908, 125114, 125138, 125532, 126753,
    128167, 129515, 131088
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
    1050, 5582, 6315, 8218, 9024, 9662, 9919, 11372, 14918, 15575, 17230, 18548, 20443, 21671, 22335, 22653,
    23641, 24218, 24634, 25043, 25493, 26665, 28785, 29389, 29697, 30350, 31179, 31588, 32059, 32090, 33523, 34052,
    34996, 36406, 37995, 38847, 39357, 40220, 40305, 40312, 40516, 41127, 41496, 41514, 41768, 42281, 42493, 43093,
    43622, 44142, 45501, 46205, 46482, 46777, 46835, 47091, 48319, 49354, 50355, 50490, 50904, 51153, 52519, 53214,
    53390, 54301, 54632, 54748, 55009, 55045, 55074, 55666, 55956, 57954, 58334, 58790, 58870, 59039, 60414, 62230,
    62637, 64165, 64237, 64289, 64636, 64912, 65233, 65610, 65645, 66608, 66856, 67283, 68491, 69483, 69738, 69800,
    70271, 70853, 71958, 73087, 73379, 73511, 73555, 73693, 74359, 75110, 75608, 75755, 76569, 83769, 83831, 84083,
    84193, 84925, 85188, 85220, 85344, 85480, 87101, 87549, 87695, 89757, 90114, 90920, 92657, 94558, 94801, 96920,
    97161, 98030, 98052, 98072, 98073, 98100, 98558, 98604, 99187, 102247, 102430, 103337, 105081, 105578, 106636, 106833,
    107533, 107794, 107865, 108454, 108693, 108945, 109406, 109523, 109849, 113486, 114192, 115015, 115094, 116429, 116606, 117096,
    117117, 117265, 117544, 117549, 117718, 118493, 118542, 118614, 119858, 120193, 120755, 120795, 120927, 120961, 121140, 121149,
    121332, 121476, 122089, 122193, 122821, 122916, 123382, 123561, 123593, 123770, 124044, 124427, 124850, 127394, 128167, 128546,
    129191, 129564, 130278, 131563
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
    879, 981, 1147, 1266, 1393, 1448, 1504, 1630, 1643, 1657, 1682, 1692, 1697, 1733, 1747, 1758,
    1812, 1829, 1933, 1997, 1999, 2032, 2042, 2068, 2139, 2309, 2354, 2532, 2560, 2595, 2655, 2660,
    2877, 2895, 2916, 2925, 2932, 2976, 3000, 3121, 3129, 3132, 3234, 3254, 3315, 3333, 3351, 3384,
    3524, 3657, 3755, 3828, 3916, 3959, 3960, 3970, 4100, 4149, 4196, 4313, 4322, 4355, 4400, 4575,
    4613, 4614, 4617, 4625, 4640, 4653, 4664, 4679, 4756, 4761, 4883, 4891, 4898, 4987, 5055, 5168,
    5189, 5215, 5222, 5226, 5274, 5303, 5310, 5329, 5351, 5355, 5366, 5417, 5527, 5557, 5569, 5615,
    5694, 5704, 5715, 5817, 5859, 5949, 5974, 5979, 6119, 6191, 6256, 6344, 6412, 6486, 6605, 6740,
    6809, 6995, 7031, 7122, 7135, 7162, 7265, 7279, 7321, 7334, 7353, 7362, 7368, 7397, 7411, 7433,
    7474, 7577, 7587, 7607, 7690, 7743, 7761, 7820, 7823, 7909, 7940, 8047, 8055, 8115, 8124, 8159,
    8185, 8245, 8340, 8355, 8409, 8443, 8448, 8465, 8469, 8516, 8518, 8524, 8617, 8634, 8733, 8810,
    8989, 9001, 9302, 9384, 9408, 9460, 9523, 9530, 9538, 9630, 9746, 9761, 9763, 9790, 9846, 9864,
    9939, 9941, 9946, 9992, 10042, 10060, 10140, 10146, 10184, 10291, 10419, 10507, 10512, 10554, 10742, 10866,
    10882, 10886, 10901, 10926, 10934, 11112, 11209, 11341, 11430, 11466, 11491, 11509, 11517, 11521, 11526, 11527,
    11528, 11529, 11534, 11536, 11556, 11605, 11622, 11623, 11643, 11732, 11760, 11789, 11794, 11806, 11811, 11833,
    11837, 11859, 11866, 11874, 11875, 11883, 11886, 11893, 11904, 11922, 11946, 11971, 11974, 12004, 12060, 12197,
    12224, 12250, 12275, 12392, 12410, 12420, 12435, 12448, 12490, 12491, 12889, 13015, 13021, 13072, 13082, 13116,
    13154, 13155, 13182, 13238, 13535, 13578, 13609, 13622, 13629, 13696, 13698, 13700, 13766, 13789, 13808, 13824,
    13832, 13836, 13856, 13896, 13928, 13929, 13933, 13978, 14000, 14002, 14028, 14029, 14036, 14037, 14039, 14045,
    14082, 14090, 14093, 14107, 14124, 14134, 14137, 14144, 14169, 14190, 14202, 14230, 14232, 14255, 14295, 14302,
    14304, 14310, 14325, 14331, 14372, 14384, 14389, 14404, 14420, 14436, 14456, 14460, 14467, 14481, 14508, 14514,
    14545, 14557, 14568, 14635, 14646, 14653, 14657, 14660, 14675, 14676, 14680, 14706, 14759, 14764, 14770, 14793,
    14801, 14822, 14824, 14826, 14827, 14884, 14919, 14984, 15030, 15082, 15088, 15234, 15237, 15241, 15282, 15306,
    15316, 15335, 15342, 15401, 15432, 15466, 15494, 15534, 15544, 15616, 15715, 15767, 15775, 15955, 16321, 16363,
    16600, 16663, 16795, 16845, 17181, 17254, 17262, 17365, 17498, 17681, 17749, 17760, 17798, 17916, 17927, 17953,
    17975, 18070, 18103, 18129, 18146, 18151, 18166, 18261, 18285, 18300, 18313, 18350, 18373, 18458, 18466, 18497,
    18505, 18513, 18538, 18553, 18561, 18659, 18709, 18717, 18722, 18732, 18882, 18901, 18964, 18977, 18980, 19011,
    19036, 19062, 19069, 19080, 19154, 19155, 19234, 19284, 19296, 19413, 19436, 19437, 19438, 19439, 19486, 19520,
    19539, 19545, 19658, 19671, 19731, 19743, 19758, 19768, 19789, 19804, 19809, 19815, 19821, 19831, 19878, 19946,
    19968, 19996, 20003, 20031, 20084, 20106, 20113, 20132, 20179, 20191, 20204, 20225, 20245, 20247, 20253, 20263,
    20274, 20329, 20358, 20451, 20471, 20490, 20596, 20674, 20702, 20892, 20991, 21046, 21090, 21133, 21500, 21698,
    21726, 21895, 21966, 21975, 22034, 22056, 22123, 22314, 22400, 22406, 22504, 22569, 22738, 22826, 22932, 22988,
    23061, 23062, 23138, 23187, 23282, 23330, 23391, 23496, 23547, 23559, 23571, 23616, 23647, 23679, 23692, 23767,
    23778, 23815, 23855, 23859, 23867, 23876, 23892, 23894, 23911, 23922, 23923, 23959, 23963, 24035, 24036, 24045,
    24059, 24061, 24079, 24089, 24150, 24159, 24172, 24198, 24205, 24223, 24231, 24232, 24241, 24250, 24265, 24302,
    24314, 24318, 24336, 24360, 24363, 24376, 24400, 24431, 24433, 24437, 24458, 24463, 24472, 24486, 24489, 24490,
    24498, 24529, 24534, 24547, 24558, 24567, 24601, 24609, 24620, 24645, 24683, 24688, 24696, 24725, 24727, 24748,
    24773, 24777, 24785, 24786, 24797, 24812, 24866, 24932, 24933, 24948, 24949, 24954, 24976, 25034, 25037, 25060,
    25090, 25125, 25145, 25195, 25201, 25211, 25242, 25255, 25256, 25384, 25415, 25448, 25545, 25567, 25574, 25631,
    25654, 25658, 25707, 25823, 25911, 25944, 25963, 26000, 26035, 26052, 26069, 26081, 26092, 26305, 26405, 26496,
    26595, 26908, 26966, 27005, 27023, 27162, 27325, 27389, 27563, 27636, 27698, 27779, 27832, 27981, 28037, 28067,
    28118, 28176, 28180, 28216, 28217, 28239, 28318, 28345, 28554, 28561, 28562, 28563, 28566, 28570, 28622, 28640,
    28644, 28661, 28688, 28706, 28711, 28772, 28786, 28857, 28859, 28881, 28914, 28958, 28961, 28975, 29003, 29008,
    29019, 29024, 29036, 29056, 29062, 29070, 29109, 29114, 29130, 29133, 29140, 29197, 29205, 29238, 29270, 29275,
    29285, 29299, 29319, 29321, 29324, 29338, 29364, 29388, 29396, 29446, 29451, 29463, 29568, 29569, 29570, 29592,
    29627, 29689, 29738, 29770, 29774, 29788, 29813, 29819, 29840, 29876, 29955, 29964, 29972, 29987, 30011, 30021,
    30065, 30117, 30119, 30120, 30131, 30145, 30153, 30162, 30194, 30204, 30256, 30268, 30276, 30344, 30380, 30392,
    30411, 30453, 30475, 30481, 30491, 30543, 30552, 30621, 30710, 30729, 30832, 30911, 30924, 30938, 30947, 30961,
    31073, 31076, 31163, 31165, 31178, 31221, 31256, 31360, 31481, 31510, 31587, 31607, 31628, 31638, 31716, 31801,
    31894, 31946, 31950, 31969, 31975, 32008, 32075, 32076, 32080, 32093, 32214, 32268, 32603, 32811, 32885, 33004,
    33161, 33300, 33448, 33486, 33667, 33751, 33983, 33994, 33997, 34147, 34253, 34270, 34278, 34342, 34347, 34377,
    34405, 34457, 34482, 34484, 34528, 34536, 34558, 34579, 34584, 34604, 34633, 34646, 34649, 34657, 34719, 34739,
    34809, 34835, 34840, 34868, 34884, 34931, 34945, 35015, 35042, 35075, 35077, 35085, 35188, 35213, 35272, 35352,
    35353, 35383, 35419, 35420, 35437, 35448, 35627, 35639, 35654, 35674, 35719, 35733, 35784, 35834, 35839, 35871,
    35877, 35939, 35940, 35957, 35976, 35999, 36029, 36169, 36181, 36190, 36312, 36392, 36498, 36573, 36574, 36617,
    36647, 36690, 36717, 36727, 36731, 36784, 36806, 36808, 36817, 36819, 36853, 36856, 36901, 36902, 36927, 36995,
    36997, 37057, 37087, 37128, 37189, 37212, 37224, 37277, 37305, 37310, 37321, 37348, 37384, 37437, 37470, 37496,
    37521, 37534, 37535, 37556, 37666, 37767, 37779, 38044, 38244, 38267, 38321, 38367, 38387, 38415, 38456, 38524,
    38528, 38560, 38612, 38744, 38751, 38760, 38761, 38785, 38808, 38891, 38984, 39090, 39214, 39525, 39693, 39753,
    39855, 39924, 39965, 40006, 40057, 40060, 40080, 40112, 40153, 40163, 40201, 40215, 40223, 40273, 40279, 40290,
    40314, 40321, 40367, 40372, 40412, 40413, 40452, 40479, 40490, 40494, 40520, 40529, 40542, 40546, 40586, 40630,
    40638, 40648, 40653, 40663, 40666, 40690, 40701, 40747, 40807, 40837, 40850, 40873, 40900, 40922, 40945, 40971,
    41110, 41119, 41149, 41156, 41294, 41297, 41301, 41312, 41391, 41401, 41406, 41431, 41456, 41475, 41482, 41542,
    41653, 41697, 41755, 41801, 41904, 41980, 42050, 42055, 42122, 42177, 42184, 42196, 42223, 42260, 42308, 42319,
    42375, 42381, 42421, 42425, 42430, 42439, 42517, 42523, 42534, 42575, 42609, 42618, 42627, 42636, 42693, 42709,
    42739, 42766, 42781, 42812, 42840, 42870, 42875, 42888, 42932, 42967, 43005, 43030, 43100, 43289, 43329, 43425,
    43461, 43534, 43604, 43607, 43644, 43782, 43849, 43909, 43984, 44011, 44046, 44054, 44067, 44175, 44181, 44385,
    44649, 44837, 44890, 44936, 44941, 45016, 45092, 45159, 45298, 45325, 45413, 45563, 45628, 45629, 45669, 45672,
    45738, 45771, 45802, 45813, 45844, 45856, 45875, 45904, 45905, 45990, 45994, 46026, 46108, 46119, 46132, 46152,
    46159, 46206, 46267, 46281, 46326, 46338, 46345, 46412, 46420, 46429, 46490, 46579, 46585, 46594, 46677, 46712,
    46776, 46785, 46787, 46812, 46830, 46855, 47009, 47023, 47060, 47130, 47145, 47161, 47190, 47239, 47269, 47316,
    47322, 47484, 47544, 47571, 47611, 47636, 47644, 47702, 47707, 47718, 47796, 47843, 47856, 47862, 47868, 47875,
    47892, 47999, 48009, 48108, 48168, 48356, 48364, 48378, 48444, 48455, 48479, 48513, 48519, 48575, 48587, 48591,
    48678, 48773, 48787, 49138, 49269, 49281, 49375, 49471, 49582, 49690, 49827, 49984, 50140, 50299, 50496, 50513,
    50525, 50656, 50789, 50795, 50828, 50974, 51372, 51398, 51491, 51559, 51620, 51631, 51712, 51714, 51720, 51746,
    51807, 51873, 51903, 52008, 52125, 52135, 52149, 52274, 52355, 52384, 52413, 52436, 52447, 52465, 52540, 52620,
    52662, 52761, 52894, 52936, 53245, 53300, 53398, 53524, 53647, 53649, 53915, 54131, 54159, 54399, 54401, 54513,
    54525, 54597, 54672, 54752, 54809, 54926, 55133, 55432, 55458, 55625, 55801, 55838, 56208, 56225, 56545, 56578,
    56587, 56706, 56728, 56791, 56808, 56878, 56909, 56929, 56949, 57006, 57032, 57182, 57204, 57312, 57347, 57423,
    57424, 57533, 57698, 57876, 58159, 58176, 58195, 58215, 58507, 58705, 58771, 58828, 58881, 58907, 58928, 58982,
    59030, 59090, 59100, 59133, 59238, 59337, 59427, 59442, 59465, 59481, 59899, 59958, 60057, 60087, 60214, 60221,
    60265, 60549, 60686, 60747, 60779, 61225, 61686, 61887, 61960, 62077, 62092, 62142, 62227, 62279, 62770, 62884,
    63199, 63225, 63420, 63556, 63722, 63840, 64095, 64107, 64150, 64154, 64267, 64302, 64377, 64451, 64713, 64796,
    64906, 65181, 65199, 65242, 65253, 65281, 65294, 65463, 66170, 66370, 66696, 66820, 66929, 67039, 67081, 67394,
    67697, 67785, 67882, 67917, 67940, 67956, 68019, 68085, 68282, 68416, 68683, 68694, 68700, 68752, 68850, 68856,
    68873, 68923, 68960, 69046, 69048, 69224, 69470, 69516, 69587, 69608, 69814, 69834, 69841, 69842, 69879, 69899,
    69901, 69967, 70149, 70192, 70219, 70285, 70376, 70381, 70426, 70486, 70620, 70670, 70838, 70907, 70911, 70956,
    70997, 71045, 71056, 71107, 71163, 71216, 71288, 71370, 71522, 71574, 71627, 71638, 71715, 71735, 71848, 71858,
    71960, 72008, 72044, 72126, 72315, 72319, 72376, 72377, 72624, 72686, 72754, 72845, 73005, 73008, 73073, 73203,
    73271, 73299, 73359, 73422, 73536, 73541, 73576, 73604, 73625, 73827, 73876, 73894, 74025, 74028, 74071, 74145,
    74165, 74170, 74178, 74215, 74397, 74426, 74478, 74863, 74961, 75019, 75109, 75124, 75215, 75246, 75289, 75405,
    75457, 75470, 75523, 75579, 75585, 75592, 75594, 75644, 75696, 75706, 75772, 75843, 76006, 76019, 76224, 76228,
    76334, 76421, 76556, 76753, 76785, 76817, 76850, 76887, 76902, 76922, 76980, 77164, 77219, 77351, 77374, 77561,
    77573, 77601, 77611, 77788, 77834, 77949, 78027, 78164, 78179, 78181, 78220, 78611, 78637, 78915, 78917, 78939,
    79138, 79186, 79226, 79321, 79356, 79399, 79467, 79510, 79553, 79690, 79716, 79731, 79853, 80134, 80136, 80208,
    80215, 80330, 80344, 80345, 80387, 80449, 80499, 80540, 80703, 80714, 80768, 80858, 80866, 80877, 80910, 80947,
    81002, 81086, 81112, 81229, 81267, 81510, 81822, 82008, 83199, 83317, 83541, 83605, 83716, 85670, 85689, 85735,
    86706, 87551, 87562, 87567, 87569, 87580, 87588, 87589, 87594, 87606, 87629, 87633, 87634, 87646, 87668, 87672,
    87675, 87684, 87686, 87696, 87708, 87750, 87779, 87798, 87803, 87806, 87808, 87816, 87831, 87842, 87845, 87872,
    87878, 87880, 87890, 87897, 87905, 87939, 87942, 87973, 87977, 87995, 87996, 87999, 88011, 88027, 88043, 88046,
    88090, 88103, 88105, 88108, 88123, 88129, 88131, 88148, 88169, 88184, 88196, 88210, 88221, 88248, 88253, 88256,
    88267, 88281, 88284, 88313, 88316, 88334, 88340, 88341, 88350, 88351, 88365, 88366, 88377, 88389, 88391, 88394,
    88396, 88421, 88428, 88430, 88452, 88456, 88462, 88474, 88486, 88496, 88497, 88498, 88501, 88502, 88513, 88518,
    88922, 90118, 90157, 90173, 90191, 90249, 90258, 90262, 90263, 90301, 90316, 90320, 90361, 90382, 90449, 90457,
    90501, 90522, 90528, 90559, 90566, 90573, 90633, 90638, 90687, 90715, 90717, 90735, 90740, 90777, 90822, 90927,
    90938, 90940, 91014, 92416, 92583, 93067, 93820, 94217, 94362, 95152, 95465, 95587, 96031, 96389, 96442, 97442,
    97466, 97489, 98480, 98539, 98929, 98993, 98999, 99005, 99069, 99111, 102598, 102602, 102611, 102615, 102616, 102682,
    103868, 103895, 103896, 103899, 103907, 103912, 103913, 103915, 104013, 104186, 104261, 104262, 104340, 104344, 104358, 104516,
    104558, 104578, 104589, 104744, 104751, 104752, 104757, 104759, 104762, 104770, 104798, 104801, 104809, 104811, 104814, 104817,
    104819, 104827, 104832, 104835, 104839, 104840, 104842, 104854, 104871, 104874, 104879, 104942, 105107, 105156, 105206, 105618,
    105724, 105903, 108609, 108621, 108670, 108753, 108821, 109065, 109636, 109853, 109854, 109856, 109866, 109868, 109875, 109876,
    109899, 109907, 109916, 109918, 112184, 112200, 112219, 112223, 112227, 112241, 112275, 112281, 112289, 112313, 112316, 112317,
    112319, 112334, 112346, 112349, 112364, 112414, 112425, 112463, 112467, 112472, 112474, 112477, 112480, 112488, 112499, 112505,
    112506, 112532, 112537, 112545, 112546, 112557, 112570, 112578, 112601, 112709, 112712, 112741, 112743, 112744, 112763, 112782,
    112797, 112820, 112842, 112850, 112853, 112862, 112863, 112890, 112911, 112912, 112920, 112927, 112951, 112960, 112987, 113001,
    113004, 113005, 113017, 113026, 113029, 113049, 113054, 113060, 113071, 113092, 113093, 113103, 113104, 113111, 113130, 113166,
    113232, 113234, 113244, 113254, 113259, 113263, 113269, 113299, 113300, 113344, 113365, 113366, 113409, 113423, 113481, 113506,
    113526, 113534, 113540, 113548, 113579, 113623, 113625, 113635, 113662, 113712, 113746, 114061, 114103, 114287, 114374, 114846,
    114847, 114878, 114952, 114957, 114960, 115027, 115167, 115238, 115295, 115418, 115497, 115533, 115579, 115589, 115593, 115597,
    115607, 115608, 115633, 115652, 115665, 115693, 115711, 115726, 115762, 115768, 115779, 115783, 115797, 115838, 115842, 115859,
    115870, 115898, 115918, 115931, 115933, 115984, 115988, 116004, 116039, 116041, 116056, 116114, 116143, 116146, 116150, 116156,
    116157, 116161, 116194, 116216, 116220, 116227, 116247, 116305, 116319, 116350, 116353, 116360, 116368, 116379, 116390, 116448,
    116454, 116463, 116464, 116469, 116472, 116474, 116487, 116496, 116505, 116510, 116550, 116560, 116564, 116566, 116581, 116601,
    116602, 116608, 116621, 116695, 116715, 116718, 116729, 116744, 116758, 116759, 116775, 116780, 116786, 116804, 116807, 116834,
    116850, 116892, 116910, 116963, 116981, 116996, 117027, 117032, 117051, 117091, 117095, 117097, 117107, 117109, 117125, 117130,
    117170, 117193, 117195, 117208, 117211, 117212, 117234, 117240, 117255, 117273, 117274, 117275, 117284, 117289, 117294, 117295,
    117305, 117317, 117336, 117338, 117353, 117356, 117357, 117360, 117371, 117375, 117393, 117405, 117410, 117413, 117414, 117424,
    117430, 117438, 117446, 117447, 117468, 117478, 117482, 117487, 117488, 117490, 117500, 117519, 117520, 117523, 117526, 117527,
    117545, 117550, 117555, 117557, 117567, 117568, 117574, 117575, 117577, 117580, 117583, 117588, 117594, 117595, 117603, 117605,
    117609, 117626, 117635, 117640, 117644, 117646, 117648, 117654, 117657, 117697, 117714, 117715, 117720, 117773, 117794, 117806,
    117813, 117820, 117826, 117890, 117898, 117900, 117926, 117932, 117935, 117963, 117969, 117977, 118026, 118035, 118045, 118070,
    118103, 118114, 118136, 118386, 118392, 118396, 118409, 118410, 118413, 118414, 118416, 118417, 118422, 118435, 118439, 118440,
    118443, 118445, 118446, 118452, 118456, 118465, 118477, 118479, 118480, 118481, 118484, 118490, 118504, 118506, 118511, 118524,
    118527, 118533, 118534, 118536, 118543, 118544, 118558, 118562, 118575, 118578, 118584, 118590, 118599, 118618, 118620, 118677,
    118712, 118742, 118754, 118836, 118893, 119059, 119100, 119116, 119127, 119168, 119176, 119194, 119195, 119204, 119205, 119214,
    119217, 119231, 119237, 119257, 119267, 119285, 119286, 119291, 119295, 119308, 119320, 119325, 119328, 119330, 119372, 119382,
    119394, 119398, 119410, 119454, 119457, 119478, 119493, 119546, 119710, 119737, 119742, 119745, 119752, 119761, 119770, 119809,
    119812, 120046, 120077, 120107, 120116, 120186, 120277, 120299, 120309, 120313, 120317, 120540, 120604, 120607, 120847, 122594,
    122775, 122900, 122968, 123042, 123180, 123318, 123320, 123392, 123408, 123413, 123601, 123602, 123663, 123924, 123927, 123928,
    123930, 123932, 123934, 123989, 124081, 126607, 127667, 128266, 130127, 131090, 131327, 131522, 131527, 131619, 131626, 131811
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
    1003, 1279, 1404, 1407, 1660, 1662, 1846, 1925, 1963, 2352, 2565, 2823, 2827, 3180, 3396, 3527,
    3671, 3772, 4016, 4064, 4249, 4576, 4588, 4750, 4830, 4890, 4904, 4930, 5053, 5155, 5175, 5269,
    5279, 5642, 5826, 6038, 6112, 6150, 6153, 6168, 6237, 6270, 6800, 7004, 7121, 7228, 7261, 7340,
    7389, 7653, 7752, 8018, 8036, 8039, 8042, 8099, 8229, 8302, 8383, 8650, 8721, 8750, 8765, 8794,
    8818, 8864, 9220, 9383, 9589, 9605, 9701, 9727, 9765, 9899, 9902, 10037, 10132, 10214, 10372, 10469,
    10520, 10550, 10652, 10686, 10886, 10906, 11297, 11512, 11522, 11545, 11644, 11694, 11779, 11864, 11933, 12194,
    12255, 12385, 13030, 13389, 13432, 13479, 13508, 13580, 13589, 13640, 13742, 13812, 13922, 13951, 13962, 14024,
    14207, 14288, 14294, 14307, 14334, 14362, 14584, 14595, 14608, 14696, 14724, 14768, 14789, 14806, 14830, 14899,
    15155, 15557, 15943, 16109, 16880, 17093, 17163, 17389, 17499, 17692, 17725, 17847, 17953, 18043, 18267, 18323,
    18461, 18478, 18519, 18537, 18683, 18790, 18861, 18906, 18915, 18933, 19003, 19039, 19081, 19212, 19268, 19382,
    19384, 19538, 19634, 19665, 19699, 19848, 20015, 20067, 20270, 20353, 20590, 20693, 20867, 21032, 21275, 21746,
    21797, 21878, 21923, 21933, 22140, 22438, 23004, 23210, 23715, 23789, 23843, 23927, 24220, 24221, 24414, 24423,
    24442, 24596, 24618, 24691, 24706, 24746, 24859, 25096, 25157, 25255, 25326, 25401, 25900, 26087, 26112, 26172,
    26317, 26352, 26478, 26545, 26646, 26808, 26838, 26977, 27195, 28259, 28437, 28586, 28714, 28735, 29215, 29244,
    29247, 29461, 29477, 29580, 29621, 29652, 29765, 29899, 29962, 30157, 30253, 30312, 30437, 30529, 30770, 31133,
    31300, 31563, 31586, 31800, 32183, 33219, 33299, 34031, 34068, 34187, 34257, 34365, 34541, 34597, 34622, 34723,
    34829, 34876, 35152, 35387, 35450, 35623, 35727, 35748, 35809, 35963, 35975, 36021, 36147, 36539, 36733, 36882,
    36918, 36934, 37325, 37527, 37651, 37748, 37761, 37874, 38248, 38430, 38512, 38580, 38703, 38714, 38847, 39069,
    39142, 39456, 39922, 39993, 40028, 40044, 40100, 40222, 40237, 40480, 40775, 40800, 41026, 41094, 41415, 41549,
    41666, 41787, 42815, 43468, 43643, 43690, 43986, 44116, 44573, 44736, 44798, 44801, 44854, 45146, 45299, 45320,
    45358, 45447, 45500, 45680, 45829, 45882, 46063, 46387, 46484, 46631, 46672, 46724, 46740, 46920, 47155, 47276,
    47428, 47608, 47783, 47844, 47943, 48032, 48337, 48416, 49551, 49578, 49638, 49730, 49749, 49774, 50203, 50747,
    51382, 51557, 51591, 51772, 51862, 52051, 52687, 53423, 53499, 53581, 53835, 54230, 54655, 54764, 54771, 55106,
    55258, 55270, 55399, 55537, 55653, 55739, 56415, 56456, 56929, 56951, 56979, 57018, 57093, 57096, 57289, 57515,
    57620, 57743, 57769, 57935, 58006, 58030, 58064, 58185, 58203, 58293, 58320, 58356, 58455, 58586, 58602, 58608,
    58613, 58676, 58701, 58775, 58813, 58836, 58997, 59000, 59005, 59008, 59118, 59140, 59241, 59367, 59430, 59482,
    59781, 60635, 60776, 60976, 61034, 61066, 61094, 61482, 61572, 61633, 61984, 62348, 62421, 62568, 62719, 62823,
    62913, 63056, 63240, 63606, 63903, 63949, 64074, 64213, 64430, 64436, 64471, 64587, 64628, 64641, 64697, 64898,
    65197, 65260, 65447, 65452, 65519, 65657, 65678, 65798, 66190, 66224, 66261, 66538, 66893, 67242, 67753, 67778,
    67824, 68315, 68337, 68362, 68388, 68483, 68565, 68566, 68715, 68735, 69023, 69401, 69405, 69427, 69446, 69474,
    69810, 69848, 69912, 70154, 70292, 70444, 70584, 70595, 70632, 70871, 71076, 71108, 71324, 71352, 71451, 71568,
    71696, 71874, 71875, 72065, 72157, 72303, 72316, 72376, 72468, 72678, 72789, 72857, 72875, 73328, 73395, 73487,
    73731, 74194, 74247, 74332, 74432, 74628, 74981, 75146, 75406, 75557, 75722, 75760, 75993, 76026, 76770, 76840,
    76874, 77051, 77074, 77376, 77393, 77405, 77606, 77665, 78031, 78032, 78205, 78225, 78539, 78583, 78615, 78864,
    79037, 79118, 79532, 79538, 79554, 79670, 79733, 79738, 79820, 79895, 79910, 79991, 80070, 80347, 80634, 80752,
    80802, 80828, 80965, 81349, 81385, 81777, 83479, 83691, 83795, 84015, 84034, 84145, 84147, 84153, 84194, 84200,
    84234, 84257, 84286, 84329, 84371, 84382, 84488, 84492, 84524, 84537, 84597, 84629, 84742, 84874, 84880, 84900,
    84993, 85057, 85109, 85226, 85244, 85282, 85294, 85375, 85382, 85431, 85542, 85585, 85588, 85633, 85734, 86153,
    86163, 86258, 86465, 87384, 87515, 87540, 87551, 87650, 87843, 87865, 88000, 88112, 88260, 88298, 88365, 88519,
    88889, 89093, 89930, 89961, 90019, 90106, 90157, 90192, 90267, 90377, 90607, 90608, 90661, 90724, 90760, 90789,
    90823, 92068, 92180, 92185, 94057, 94191, 94278, 94562, 94838, 94873, 95136, 95209, 95281, 95300, 95389, 95401,
    95550, 95694, 95705, 95714, 95801, 95828, 95839, 95840, 96098, 96128, 96160, 96184, 96200, 96323, 96433, 96508,
    96673, 96962, 97052, 97224, 97227, 97265, 97335, 97403, 97514, 97558, 97660, 97703, 97937, 98003, 98058, 98061,
    98071, 98074, 98075, 98086, 98090, 98093, 98255, 98282, 98335, 98437, 98530, 98609, 98614, 98616, 98624, 98629,
    98632, 98633, 98642, 98643, 98797, 98982, 99135, 99175, 99236, 99385, 99665, 100121, 100187, 100332, 100393, 100815,
    101254, 101272, 101520, 101573, 101933, 102387, 102580, 103170, 103190, 103384, 103483, 104321, 104323, 104404, 104428, 104929,
    105073, 105161, 105172, 105380, 105434, 105503, 105530, 105796, 105826, 105842, 105981, 106465, 106475, 106711, 106733, 106735,
    107007, 107133, 107201, 107252, 107259, 107293, 107557, 107636, 107735, 107830, 108110, 108167, 108190, 108224, 108358, 108367,
    108431, 108514, 108648, 108739, 108804, 108827, 109079, 109141, 109321, 109723, 112421, 112473, 112475, 112501, 112556, 112608,
    112620, 112627, 112639, 112754, 112932, 112957, 112980, 112986, 113091, 113106, 113136, 113154, 113157, 113189, 113352, 113354,
    113371, 113380, 113397, 113489, 113648, 113669, 113703, 113790, 113842, 113949, 114388, 114832, 114834, 114866, 115011, 115227,
    115260, 115307, 115320, 115357, 115364, 115411, 115445, 115474, 115496, 115532, 115564, 115721, 115846, 115954, 115957, 115965,
    116002, 116025, 116226, 116243, 116253, 116267, 116310, 116424, 116435, 116476, 116497, 116522, 116533, 116539, 116571, 116610,
    116979, 117050, 117057, 117159, 117192, 117229, 117406, 117408, 117443, 117604, 117763, 117811, 117868, 117885, 117957, 118031,
    118046, 118111, 118124, 118182, 118344, 118709, 118732, 118815, 118847, 118997, 119003, 119040, 119050, 119107, 119122, 119354,
    119543, 119681, 119701, 119805, 119836, 119948, 120033, 120040, 120119, 120131, 120248, 120449, 120482, 120527, 120542, 120594,
    120650, 120656, 120665, 120748, 120837, 120857, 120903, 120990, 121066, 121077, 121161, 121191, 121203, 121285, 121302, 121309,
    121359, 121399, 121409, 121466, 121568, 121711, 121728, 121764, 121824, 122119, 122262, 122440, 122564, 122768, 122879, 122909,
    123070, 123157, 123195, 123276, 123286, 123637, 123660, 123741, 123743, 123869, 123895, 123921, 124000, 124031, 124038, 124147,
    124222, 124443, 124452, 124475, 124560, 124655, 124860, 124973, 125244, 125402, 125597, 125681, 125725, 125938, 125981, 126037,
    126407, 126923, 126938, 126976, 127017, 127100, 127211, 127460, 127498, 127512, 127711, 128077, 128271, 128303, 128331, 128748,
    128970, 129004, 129429, 129461, 129710, 129800, 130069, 130076, 130349, 130373, 130377, 130417, 130550, 130586, 130730, 130751,
    131082, 131303, 131333, 131335, 131358, 131450, 131459, 131720, 131780
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
    54, 181, 201, 284, 554, 667, 729, 812, 837, 1056, 1083, 1096, 1168, 1210, 1413, 1546,
    1671, 1708, 1746, 1864, 1962, 2408, 2618, 2912, 2927, 3461, 3655, 3912, 4225, 4588, 4674, 4701,
    4716, 4972, 5040, 5140, 5375, 5562, 5571, 5599, 5635, 6019, 6107, 6329, 6555, 7001, 7042, 7086,
    7168, 7175, 7261, 7284, 7337, 7550, 7638, 7658, 7682, 7685, 7873, 8049, 8135, 8179, 8204, 8302,
    8383, 8436, 8486, 8562, 8608, 8721, 8911, 8932, 9121, 9220, 9329, 9494, 9527, 9529, 9671, 9686,
    9765, 9874, 9920, 9997, 10056, 10157, 10210, 10214, 10215, 10604, 10656, 10686, 10870, 10920, 11247, 11297,
    11326, 11429, 11589, 11641, 11661, 11735, 11786, 11933, 12047, 12282, 12451, 12480, 12653, 12762, 12899, 13193,
    13491, 13508, 13532, 13566, 13634, 13640, 13642, 13720, 13745, 13774, 13790, 13803, 13804, 13806, 13968, 13975,
    14024, 14072, 14170, 14210, 14294, 14377, 14396, 14453, 14496, 14500, 14550, 14561, 14696, 14745, 14792, 14959,
    15045, 15381, 15495, 15512, 15641, 15738, 15739, 16266, 16731, 17133, 17226, 17353, 17377, 17419, 17738, 17907,
    18276, 18323, 18478, 18482, 18591, 18683, 18685, 18744, 18790, 18881, 18902, 18989, 19003, 19059, 19075, 19104,
    19269, 19309, 19323, 19396, 19417, 19514, 19604, 19699, 19869, 19963, 19967, 20067, 20200, 20374, 20536, 20757,
    20784, 21078, 21275, 21392, 22012, 22390, 22429, 22822, 22907, 23003, 23141, 23574, 23715, 23927, 24446, 24557,
    25218, 25391, 25970, 25973, 25984, 26172, 26874, 26951, 26963, 28585, 28950, 29215, 29329, 29379, 29648, 29730,
    29810, 29899, 29940, 30352, 30803, 31116, 31563, 31665, 32104, 32320, 32399, 32576, 32756, 32788, 32921, 32932,
    33219, 33383, 34031, 34063, 34066, 34172, 34188, 34415, 34501, 34615, 34661, 34781, 34907, 35179, 35442, 35502,
    35686, 35792, 36147, 36349, 36440, 36649, 37425, 37436, 37671, 38347, 39044, 39423, 39628, 40042, 40044, 40100,
    40322, 40363, 40566, 40937, 41242, 41679, 42192, 42480, 42570, 42573, 42599, 42645, 43613, 43662, 44006, 44458,
    44616, 45222, 45233, 45288, 45320, 45500, 45579, 45680, 46441, 46536, 46544, 46725, 46731, 46983, 47232, 47479,
    47858, 47891, 48035, 48074, 48197, 48814, 49099, 49749, 50418, 51018, 51228, 51343, 51382, 51454, 51469, 51518,
    52547, 52893, 53300, 54005, 54189, 54283, 54315, 54485, 54790, 55017, 55255, 56385, 56482, 56841, 57743, 58081,
    58175, 58478, 58480, 59000, 59003, 59111, 59181, 59229, 59367, 59534, 59637, 60020, 60043, 60275, 60339, 60693,
    60694, 60827, 60982, 61155, 61159, 61206, 62760, 63481, 63900, 64007, 64697, 64769, 64913, 64922, 65420, 65489,
    65798, 66099, 66938, 67168, 67463, 67753, 68098, 68125, 68193, 68356, 68362, 68389, 68761, 68986, 69099, 69162,
    69687, 70086, 70103, 70157, 70230, 70312, 70402, 70493, 70584, 70621, 70651, 70808, 70830, 70925, 71504, 71563,
    71924, 72132, 72241, 72303, 72500, 73075, 73479, 73707, 73721, 73825, 74009, 74038, 74150, 74199, 74317, 74465,
    74564, 74589, 74793, 75128, 75427, 75519, 75674, 75676, 75993, 76205, 76382, 76470, 76934, 77170, 77173, 77266,
    77324, 77393, 77445, 77528, 77596, 77658, 77665, 78187, 78542, 78618, 78749, 79037, 79346, 79532, 79547, 79674,
    79747, 79979, 79991, 80048, 80296, 80878, 80890, 81493, 81494, 81810, 82040, 83221, 83727, 84015, 84062, 84234,
    84646, 84745, 84770, 84785, 85111, 85244, 85406, 85537, 85570, 85577, 86612, 86654, 86667, 87127, 87590, 87601,
    87671, 87940, 87976, 88001, 88372, 88375, 88414, 88439, 88468, 90156, 90387, 90445, 90498, 90552, 90877, 90891,
    91801, 92442, 92755, 93522, 94021, 94430, 94485, 94632, 94727, 94988, 95250, 95387, 95646, 96083, 96398, 96508,
    96516, 96563, 96910, 97087, 97129, 97308, 97787, 98077, 98180, 98278, 98360, 98613, 98614, 98615, 98616, 98770,
    98772, 98864, 99018, 99341, 99502, 99665, 99777, 99864, 101214, 101234, 101577, 102692, 102957, 103841, 103851, 104097,
    104321, 104460, 105175, 105308, 105417, 105459, 105545, 105665, 106023, 106477, 106842, 106918, 106998, 106999, 107107, 107263,
    107321, 107455, 107636, 107649, 107681, 107736, 107770, 108961, 108978, 110459, 112150, 112395, 112421, 112651, 112702, 112794,
    112861, 113045, 113058, 113069, 113175, 113202, 113249, 113251, 113256, 113309, 113371, 113437, 113446, 113567, 113639, 113645,
    113679, 113802, 113949, 114006, 114204, 114248, 114940, 115011, 115145, 115222, 115243, 115457, 115638, 115708, 115767, 115790,
    115839, 115914, 115966, 115993, 116036, 116132, 116160, 116267, 116306, 116318, 116441, 116461, 116516, 116522, 116541, 116584,
    116593, 116623, 116755, 116771, 116865, 116885, 116893, 117041, 117063, 117103, 117112, 117139, 117160, 117194, 117719, 117947,
    117994, 118013, 118101, 118104, 118156, 118196, 118226, 118822, 118866, 118948, 119002, 119738, 119849, 119874, 119892, 119894,
    119920, 120468, 120818, 120848, 120865, 120933, 121191, 121216, 121466, 121503, 121589, 121592, 121649, 121723, 121870, 122127,
    123107, 123158, 123325, 123420, 123737, 123921, 123990, 124031, 124238, 124298, 124394, 124529, 124933, 124943, 125389, 125920,
    125922, 126116, 126777, 126848, 127554, 127578, 127761, 128664, 129445, 130369, 130373, 130579, 130617, 130709, 130883, 130999,
    131082, 131532
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
    52521, 94569
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
    2025, 4319, 5258, 5467, 6129, 6494, 6988, 10073, 10240, 11193, 12103, 13022, 15638, 16090, 16165, 18968,
    20816, 21382, 21688, 25471, 27470, 29923, 31040, 31751, 33784, 35907, 36952, 38002, 38080, 38494, 39655, 42210,
    42745, 42872, 42951, 43069, 43256, 45670, 47637, 49778, 51228, 51251, 51667, 52951, 56962, 58258, 59756, 60302,
    62287, 62392, 63027, 63183, 65548, 65742, 66159, 66389, 67776, 68334, 68513, 69488, 69745, 70012, 71019, 71371,
    71483, 72251, 72502, 72750, 74572, 75002, 78275, 80054, 81060, 84777, 93344, 94898, 98108, 98286, 103229, 103282,
    103551, 111039, 119415, 122186, 123529, 126537
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
    2421, 2463, 2483, 2509, 2754, 2790, 2879, 3133, 3143, 3331, 3346, 3465, 3487, 3493, 3506, 3529,
    3545, 3689, 3693, 3863, 3929, 4076, 4094, 4147, 4173, 4209, 4290, 4295, 4300, 4359, 4424, 4427,
    4436, 4471, 4483, 4485, 4487, 4502, 4596, 4695, 4764, 4835, 4918, 4953, 4974, 4977, 5090, 5141,
    5440, 5466, 5471, 5485, 5486, 5492, 5511, 5661, 5739, 5744, 5755, 5834, 5844, 5866, 5944, 5960,
    5980, 6009, 6044, 6080, 6202, 6355, 6406, 6418, 6500, 6503, 6524, 6591, 6602, 6609, 6625, 6626,
    6629, 6639, 6701, 6852, 6869, 6899, 6905, 6928, 6939, 6963, 7114, 7144, 7159, 7515, 7522, 7530,
    7541, 7570, 7695, 7729, 7782, 7784, 7898, 7901, 7937, 7951, 7962, 7974, 7994, 8046, 8075, 8084,
    8170, 8171, 8243, 8244, 8290, 8311, 8333, 8371, 8433, 8479, 8503, 8594, 8630, 8656, 8662, 8707,
    8775, 8801, 8819, 8820, 8838, 8862, 8897, 8906, 9002, 9014, 9021, 9039, 9054, 9100, 9109, 9131,
    9161, 9171, 9193, 9203, 9255, 9258, 9389, 9401, 9416, 9519, 9547, 9571, 9580, 9707, 9779, 9880,
    9983, 9996, 9999, 10009, 10015, 10128, 10159, 10160, 10192, 10204, 10220, 10223, 10296, 10319, 10358, 10411,
    10421, 10426, 10448, 10479, 10492, 10531, 10614, 10628, 10650, 10679, 10685, 10688, 10780, 10786, 10791, 10821,
    10835, 10851, 10855, 10896, 10957, 10974, 10999, 11003, 11056, 11071, 11109, 11124, 11128, 11143, 11157, 11342,
    11366, 11379, 11384, 11515, 11546, 11554, 11606, 11720, 11733, 11957, 11993, 11997, 12036, 12070, 12083, 12092,
    12093, 12108, 12125, 12129, 12135, 12144, 12147, 12160, 12257, 12328, 12354, 12427, 12464, 12469, 12492, 12623,
    12725, 12770, 12899, 12935, 12946, 12950, 13024, 13158, 13175, 13254, 13308, 13358, 13392, 13549, 13946, 13986,
    14052, 14098, 14188, 14198, 14244, 14260, 14271, 14282, 14382, 14388, 14418, 14447, 14512, 14521, 14560, 14693,
    14707, 14781, 14813, 14836, 14889, 14913, 14932, 14955, 15009, 15085, 15104, 15118, 15135, 15139, 15148, 15154,
    15266, 15363, 15375, 15414, 15427, 15449, 15502, 15510, 15535, 15542, 15552, 15577, 15587, 15601, 15636, 15663,
    15675, 15713, 15728, 15735, 15766, 15770, 15789, 15804, 15829, 15881, 15923, 15926, 15939, 15940, 15956, 15968,
    15982, 15983, 16009, 16051, 16053, 16055, 16056, 16060, 16072, 16084, 16094, 16119, 16150, 16157, 16201, 16208,
    16238, 16284, 16314, 16347, 16355, 16358, 16371, 16381, 16432, 16436, 16460, 16467, 16585, 16613, 16634, 16714,
    16739, 16763, 16860, 16901, 16908, 16913, 16942, 16946, 16996, 17079, 17084, 17087, 17095, 17097, 17152, 17193,
    17228, 17368, 17459, 17528, 17545, 17572, 17575, 17601, 17640, 17773, 17865, 17884, 17965, 18046, 18048, 18061,
    18106, 18241, 18268, 18294, 18312, 18398, 18418, 18645, 18673, 18723, 18775, 18808, 18809, 18813, 18814, 18883,
    18898, 18932, 18944, 18972, 19084, 19177, 19188, 19232, 19313, 19318, 19441, 19525, 19613, 19656, 19681, 19703,
    19713, 19719, 19722, 19751, 19834, 19955, 19978, 20035, 20051, 20053, 20080, 20091, 20140, 20271, 20285, 20391,
    20400, 20454, 20462, 20496, 20503, 20581, 20610, 20641, 20685, 20723, 20735, 20759, 20794, 20814, 20826, 20922,
    20952, 20982, 21002, 21066, 21183, 21184, 21212, 21259, 21265, 21269, 21327, 21365, 21487, 21505, 21517, 21521,
    21562, 21597, 21601, 21620, 21632, 21641, 21699, 21715, 21743, 21799, 21848, 21856, 21857, 21891, 22046, 22055,
    22081, 22099, 22115, 22166, 22180, 22181, 22182, 22197, 22236, 22257, 22261, 22281, 22287, 22302, 22329, 22331,
    22346, 22350, 22382, 22394, 22412, 22445, 22476, 22507, 22531, 22556, 22621, 22634, 22648, 22659, 22674, 22680,
    22698, 22712, 22767, 22788, 22795, 22928, 22954, 23029, 23104, 23115, 23189, 23197, 23218, 23239, 23243, 23249,
    23268, 23272, 23280, 23299, 23300, 23316, 23323, 23331, 23377, 23380, 23383, 23424, 23447, 23455, 23460, 23578,
    23621, 23639, 23709, 23770, 23784, 23905, 23943, 24040, 24047, 24049, 24165, 24234, 24273, 24365, 24387, 24455,
    24506, 24613, 24633, 24841, 24849, 24865, 24880, 24898, 24950, 25096, 25121, 25192, 25353, 25427, 25466, 25496,
    25498, 25522, 25537, 25543, 25603, 25613, 25614, 25665, 25693, 25756, 25764, 25773, 25794, 25801, 25806, 25830,
    25876, 25936, 26117, 26182, 26213, 26227, 26287, 26299, 26302, 26306, 26340, 26348, 26349, 26358, 26373, 26374,
    26379, 26424, 26483, 26503, 26506, 26535, 26622, 26663, 26669, 26680, 26689, 26693, 26878, 27040, 27172, 27266,
    27273, 27278, 27291, 27321, 27322, 27424, 27427, 27444, 27474, 27505, 27525, 27554, 27571, 27623, 27631, 27640,
    27643, 27692, 27726, 27733, 27755, 27761, 27771, 27802, 27812, 27851, 27872, 27933, 27986, 27996, 28069, 28074,
    28084, 28117, 28119, 28156, 28216, 28231, 28288, 28312, 28376, 28377, 28424, 28451, 28463, 28482, 28505, 28553,
    28579, 28603, 28613, 28637, 28659, 28713, 28740, 28885, 28909, 28940, 29039, 29066, 29086, 29157, 29236, 29239,
    29256, 29334, 29383, 29434, 29437, 29472, 29481, 29561, 29575, 29624, 29646, 29693, 29715, 29726, 29752, 29769,
    29875, 29882, 29905, 29911, 29943, 29945, 29967, 30016, 30045, 30116, 30211, 30240, 30259, 30271, 30325, 30369,
    30409, 30417, 30430, 30432, 30505, 30533, 30535, 30637, 30644, 30663, 30687, 30712, 30716, 30739, 30848, 30852,
    30903, 30913, 30952, 30982, 31016, 31022, 31033, 31065, 31070, 31093, 31113, 31186, 31224, 31225, 31228, 31267,
    31286, 31299, 31346, 31357, 31377, 31468, 31657, 31699, 31722, 31733, 31764, 31779, 31987, 32089, 32119, 32131,
    32218, 32355, 32373, 32382, 32409, 32485, 32491, 32536, 32545, 32565, 32570, 32618, 32619, 32638, 32682, 32718,
    32753, 32768, 32770, 32777, 32942, 32966, 32991, 33021, 33026, 33044, 33076, 33078, 33092, 33097, 33099, 33107,
    33116, 33253, 33269, 33270, 33319, 33418, 33434, 33521, 33550, 33572, 33608, 33609, 33659, 33685, 33697, 33714,
    33736, 33821, 33878, 33898, 33923, 33961, 34013, 34019, 34034, 34041, 34070, 34083, 34085, 34122, 34144, 34148,
    34168, 34206, 34217, 34229, 34245, 34268, 34290, 34301, 34315, 34327, 34348, 34388, 34410, 34481, 34549, 34566,
    34569, 34594, 34663, 34666, 34692, 34743, 34771, 34787, 34846, 34847, 34853, 34859, 34913, 35032, 35059, 35082,
    35092, 35109, 35128, 35143, 35192, 35247, 35268, 35287, 35318, 35346, 35354, 35388, 35415, 35500, 35513, 35524,
    35526, 35557, 35559, 35630, 35645, 35653, 35736, 35758, 35773, 35824, 35859, 35880, 35889, 35930, 35933, 35937,
    36007, 36048, 36073, 36104, 36112, 36117, 36133, 36254, 36347, 36359, 36389, 36477, 36504, 36516, 36547, 36553,
    36667, 36686, 36698, 36700, 36720, 36755, 36764, 36776, 36778, 36811, 36847, 36876, 36910, 37099, 37104, 37108,
    37117, 37129, 37167, 37171, 37238, 37246, 37379, 37380, 37385, 37418, 37432, 37450, 37457, 37462, 37532, 37569,
    37598, 37613, 37625, 37730, 37755, 37823, 37834, 37861, 37879, 37880, 37927, 37932, 37996, 37997, 38121, 38163,
    38164, 38174, 38213, 38373, 38412, 38432, 38478, 38482, 38579, 38589, 38605, 38623, 38662, 38665, 38668, 38669,
    38688, 38693, 38707, 38805, 38853, 38864, 38880, 38884, 38908, 38925, 38979, 39045, 39046, 39076, 39100, 39117,
    39135, 39137, 39146, 39162, 39204, 39239, 39249, 39251, 39320, 39350, 39355, 39356, 39381, 39397, 39431, 39473,
    39611, 39695, 39697, 39720, 39727, 39738, 39787, 39802, 39944, 39986, 40030, 40159, 40164, 40194, 40210, 40213,
    40225, 40246, 40326, 40376, 40442, 40460, 40491, 40493, 40500, 40509, 40581, 40670, 40673, 40703, 40826, 40934,
    40938, 41045, 41130, 41172, 41296, 41318, 41373, 41501, 41528, 41538, 41555, 41564, 41586, 41596, 41606, 41654,
    41655, 41675, 41691, 41711, 41712, 41738, 41773, 41814, 41848, 41868, 41913, 41967, 41975, 42077, 42129, 42130,
    42189, 42215, 42226, 42264, 42327, 42398, 42506, 42561, 42703, 42810, 42835, 42869, 42935, 42975, 43090, 43128,
    43148, 43234, 43281, 43401, 43404, 43408, 43467, 43508, 43573, 43595, 43596, 43642, 43685, 43750, 43789, 43791,
    43878, 43881, 43910, 44001, 44024, 44082, 44086, 44114, 44123, 44145, 44231, 44236, 44281, 44296, 44298, 44306,
    44322, 44374, 44428, 44468, 44488, 44489, 44505, 44576, 44617, 44670, 44679, 44706, 44727, 44838, 44840, 44860,
    44889, 44898, 44931, 44956, 45055, 45164, 45217, 45303, 45322, 45444, 45569, 45595, 45600, 45611, 45616, 45660,
    45838, 45922, 46115, 46260, 46274, 46355, 46360, 46413, 46424, 46432, 46458, 46503, 46584, 46706, 46819, 46899,
    46943, 46991, 47004, 47075, 47114, 47128, 47142, 47226, 47277, 47291, 47375, 47386, 47470, 47501, 47531, 47537,
    47614, 47788, 47901, 47962, 47966, 47975, 48014, 48029, 48055, 48176, 48184, 48210, 48212, 48229, 48243, 48249,
    48283, 48287, 48295, 48341, 48414, 48422, 48448, 48521, 48582, 48623, 48830, 48832, 48875, 48934, 49005, 49013,
    49023, 49084, 49094, 49145, 49152, 49165, 49180, 49256, 49313, 49349, 49369, 49381, 49421, 49475, 49488, 49495,
    49530, 49585, 49591, 49642, 49659, 49695, 49728, 49786, 49814, 49825, 49930, 49973, 50010, 50142, 50232, 50246,
    50305, 50316, 50323, 50349, 50371, 50397, 50458, 50506, 50548, 50588, 50679, 50681, 50686, 50699, 50729, 50959,
    50993, 51013, 51038, 51099, 51105, 51191, 51203, 51252, 51279, 51310, 51329, 51368, 51404, 51452, 51482, 51498,
    51601, 51640, 51680, 51894, 52070, 52075, 52143, 52205, 52228, 52240, 52348, 52373, 52455, 52489, 52507, 52549,
    52647, 52718, 52851, 53147, 53156, 53170, 53213, 53274, 53293, 53491, 53497, 53504, 53557, 53582, 53697, 53736,
    53776, 53781, 53910, 53915, 54087, 54104, 54265, 54380, 54461, 54653, 54677, 54695, 54846, 54892, 54995, 55057,
    55285, 55501, 55515, 55703, 55802, 55942, 56042, 56136, 56152, 56221, 56370, 56372, 56409, 56598, 56674, 56715,
    56770, 57236, 57454, 57535, 57590, 57605, 57608, 57710, 57713, 57972, 58012, 58055, 58124, 58125, 58186, 58223,
    58242, 58355, 58389, 58453, 58487, 58575, 58638, 58697, 58741, 58769, 58833, 58922, 59050, 59060, 59270, 59341,
    59381, 59415, 59507, 59630, 59701, 59751, 59765, 59843, 59844, 59981, 60071, 60147, 60209, 60225, 60249, 60334,
    60504, 60546, 60586, 60707, 60724, 60742, 60816, 60932, 60962, 61431, 61472, 61500, 61578, 61580, 61609, 61654,
    61666, 61795, 61826, 61858, 61876, 61930, 61960, 62013, 62122, 62215, 62238, 62249, 62261, 62289, 62319, 62357,
    62380, 62458, 62478, 62490, 62567, 62614, 62631, 62682, 62725, 62845, 62912, 62930, 62952, 62954, 62975, 63019,
    63087, 63124, 63147, 63239, 63320, 63471, 63588, 63590, 63625, 63734, 63830, 64040, 64075, 64311, 64369, 64396,
    64501, 64838, 64871, 65079, 65085, 65101, 65165, 65198, 65215, 65219, 65256, 65306, 65314, 65330, 65401, 65524,
    65808, 65841, 65879, 65904, 65915, 65920, 65999, 66172, 66203, 66307, 66344, 66375, 66481, 66482, 66526, 66616,
    66645, 66745, 66802, 66809, 66853, 66926, 66948, 66967, 67009, 67125, 67146, 67177, 67220, 67302, 67303, 67310,
    67312, 67341, 67354, 67366, 67435, 67443, 67631, 67654, 67783, 67834, 67892, 67910, 67938, 67965, 68054, 68075,
    68086, 68093, 68115, 68248, 68303, 68311, 68376, 68390, 68479, 68508, 68533, 68637, 68684, 68734, 68755, 68785,
    68897, 68921, 68969, 68974, 69031, 69062, 69102, 69173, 69191, 69247, 69272, 69277, 69311, 69371, 69387, 69392,
    69424, 69467, 69525, 69559, 69578, 69589, 69592, 69600, 69644, 69681, 69710, 69766, 69797, 69948, 69950, 69974,
    70073, 70200, 70249, 70290, 70297, 70352, 70360, 70528, 70529, 70568, 70590, 70630, 70634, 70664, 70669, 70684,
    71040, 71141, 71187, 71215, 71334, 71383, 71459, 71460, 71465, 71496, 71537, 71597, 71660, 71731, 71773, 71867,
    71946, 72061, 72070, 72074, 72112, 72121, 72148, 72305, 72320, 72334, 72344, 72351, 72356, 72377, 72444, 72454,
    72482, 72501, 72505, 72520, 72528, 72538, 72563, 72580, 72671, 72687, 72727, 72748, 72828, 72830, 73016, 73037,
    73070, 73100, 73151, 73165, 73205, 73215, 73308, 73431, 73455, 73573, 73579, 73777, 73920, 73934, 74035, 74073,
    74148, 74174, 74319, 74337, 74352, 74377, 74517, 74540, 74601, 74620, 74631, 74649, 74662, 74683, 74725, 74841,
    74891, 75080, 75179, 75189, 75350, 75439, 75561, 75572, 75575, 75702, 75841, 75896, 75900, 75959, 75970, 75985,
    76002, 76005, 76008, 76167, 76189, 76454, 76776, 76810, 76908, 76983, 77129, 77159, 77212, 77264, 77359, 77401,
    77431, 77449, 77510, 77564, 77603, 77716, 77767, 77768, 77772, 77908, 77945, 77961, 77968, 78116, 78127, 78348,
    78394, 78405, 78628, 78655, 78978, 79016, 79032, 79159, 79203, 79422, 79486, 79551, 79686, 79951, 79990, 80313,
    80333, 80646, 80688, 80796, 81046, 81328, 81663, 82870, 82915, 83140, 83146, 83368, 83534, 83709, 83813, 83827,
    83880, 84041, 84092, 84115, 84143, 84186, 84268, 84284, 84754, 85027, 85156, 85315, 86471, 86601, 86909, 87339,
    87603, 88323, 88342, 88585, 88662, 88664, 88701, 88755, 88801, 89099, 89154, 89170, 89263, 89821, 90312, 90446,
    90619, 90694, 90804, 90852, 91117, 91136, 91171, 91185, 91229, 91380, 91570, 91968, 92142, 92182, 92203, 92268,
    92419, 92480, 92633, 92806, 92848, 93214, 93281, 93360, 93362, 93454, 93455, 93502, 93530, 93607, 93700, 93719,
    93841, 93859, 94031, 94136, 94281, 94411, 94487, 94496, 94551, 94569, 94585, 94597, 94655, 94681, 94877, 97223,
    97981, 98024, 98661, 98662, 98807, 99006, 99035, 99092, 99110, 99381, 99403, 99498, 99520, 99740, 100723, 100727,
    101138, 101159, 101244, 101307, 101428, 101570, 101700, 101820, 102160, 102507, 102593, 102745, 102758, 102763, 102768, 102776,
    102797, 102808, 102822, 102843, 102848, 102888, 102906, 102944, 103022, 103030, 103093, 103100, 103101, 103128, 103161, 103178,
    103231, 103246, 103249, 103343, 103372, 103418, 103439, 103440, 103464, 103489, 103493, 103511, 103533, 103537, 103548, 103554,
    103566, 103644, 103646, 103680, 103682, 103704, 103714, 103716, 103717, 103750, 104465, 105579, 105859, 106110, 106148, 106172,
    106370, 106629, 106934, 107077, 107117, 107127, 107162, 107174, 107212, 107217, 107266, 107470, 107622, 107639, 107668, 107793,
    107851, 107867, 107873, 108043, 108221, 108225, 108527, 108663, 108664, 108710, 108764, 108801, 108910, 109008, 109367, 109428,
    109678, 109813, 109946, 110136, 110185, 110276, 110278, 110301, 110304, 110305, 110348, 110370, 110372, 110403, 110405, 110435,
    110466, 110483, 110511, 110528, 110532, 110578, 110579, 110606, 110705, 110726, 110734, 110746, 110752, 110755, 110771, 110852,
    110857, 110885, 110886, 110893, 110906, 110942, 110955, 110960, 110962, 110995, 111004, 111040, 111045, 111056, 111076, 111082,
    111096, 111097, 111119, 111120, 111179, 111705, 111707, 112131, 112133, 112473, 112692, 113789, 114104, 115039, 115640, 115689,
    115700, 115888, 116048, 116472, 116529, 117762, 117803, 118652, 119214, 119542, 119586, 119697, 120141, 122009, 122034, 122614,
    122852, 123047, 123222, 123619, 124619, 125867, 126047, 126886, 128045, 128394, 128417, 128456, 128559, 129017, 129142, 129485,
    129568, 130145, 130228, 130285, 131225, 131426, 131445, 131931, 132011, 132037, 132038, 132039, 132045, 132057, 132066
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
    176, 816, 2015, 3147, 4686, 5511, 6476, 6910, 7299, 7794, 8818, 9203, 9238, 10410, 10535, 11384,
    11400, 11499, 11539, 11938, 12041, 12091, 12431, 12571, 12747, 14065, 16145, 17100, 17478, 18429, 18798, 18990,
    19321, 19713, 19773, 21566, 22812, 24221, 24483, 24796, 25098, 25844, 28119, 29641, 30432, 30570, 31000, 31056,
    33789, 33814, 34282, 35318, 35513, 36754, 37834, 40566, 40645, 42493, 42964, 43166, 43217, 47608, 49448, 55169,
    55258, 57710, 59602, 66069, 66604, 69760, 73807, 77868, 78531, 78860, 79829, 81060, 81920, 84777, 85658, 90390,
    91546, 103384, 106705, 108359, 112700, 112975, 115240, 115545, 115561, 115598, 118633, 120693, 120914, 121760, 121979, 131672,
    132128
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
    124, 132, 182, 1121, 2665, 6366, 8046, 17209, 22131, 24016, 28008, 28189, 28216, 28237, 28382, 28423,
    28519, 28522, 28553, 28559, 28660, 28663, 28737, 28831, 28870, 28874, 28931, 28989, 28993, 29039, 29066, 29413,
    29556, 29621, 29623, 29624, 29628, 29697, 29792, 29889, 30098, 30196, 30197, 30220, 30233, 30364, 30421, 30663,
    30732, 30757, 30829, 30848, 30943, 31021, 31065, 31296, 31299, 31339, 31363, 31670, 31699, 31750, 31812, 31886,
    31988, 32208, 32283, 32290, 32355, 32545, 32594, 32736, 32754, 32804, 32831, 32942, 32956, 33055, 33250, 33309,
    33350, 33358, 33725, 33747, 33908, 33923, 34144, 34206, 34566, 34730, 34735, 35058, 35147, 35346, 35376, 35388,
    35451, 35573, 35671, 35781, 35824, 35930, 36035, 36040, 36248, 36254, 36395, 36397, 36507, 36594, 36630, 36654,
    36725, 36769, 36888, 36911, 36955, 37099, 37203, 37368, 37395, 37461, 37462, 37483, 37755, 38042, 38058, 38093,
    38230, 38364, 38370, 38448, 38473, 38878, 38944, 39088, 39204, 39239, 39320, 39343, 39427, 39756, 39802, 39873,
    39897, 40122, 40132, 40152, 40408, 40489, 40581, 40627, 40709, 40710, 40759, 40814, 40823, 40860, 41296, 41381,
    41463, 41501, 41523, 41921, 41931, 42167, 42189, 42354, 42364, 42496, 42589, 42761, 42764, 42846, 42910, 42915,
    42992, 43326, 43671, 43941, 44086, 44123, 44455, 44505, 44593, 44716, 44754, 44898, 44931, 45231, 45392, 45474,
    45495, 45678, 45818, 45831, 45889, 45966, 45985, 46103, 46104, 46122, 46148, 46188, 46260, 46355, 46360, 46391,
    46416, 46470, 46584, 46769, 46899, 47085, 47280, 47386, 47552, 47637, 47680, 47744, 48045, 48055, 48057, 48190,
    48416, 48698, 49180, 49203, 49458, 49519, 49548, 49814, 50019, 50645, 50744, 51368, 51802, 51942, 51980, 52128,
    52160, 52776, 52951, 53438, 53541, 53847, 54104, 54136, 54257, 54415, 54474, 54828, 55163, 55285, 56660, 56876,
    57208, 57377, 58389, 58664, 58741, 58898, 59182, 59808, 59829, 60182, 60564, 60673, 60742, 61042, 61168, 61654,
    61827, 62073, 62261, 62490, 62508, 62619, 62681, 62823, 63241, 63335, 63820, 63830, 63880, 63950, 64040, 64623,
    65454, 65497, 65520, 65651, 65906, 66110, 66307, 66424, 66549, 66609, 67223, 67565, 67937, 68074, 68093, 68311,
    68455, 68719, 68750, 69581, 69644, 69994, 70055, 70083, 70333, 70484, 70554, 70708, 70751, 70755, 70867, 70879,
    70978, 71141, 71207, 71383, 71477, 71554, 71597, 71772, 71891, 71946, 72192, 72334, 72377, 72782, 72931, 73016,
    73461, 73579, 73614, 73734, 73933, 73934, 74026, 74152, 74692, 74933, 75261, 75325, 75380, 75419, 75756, 75763,
    75863, 75985, 76267, 76270, 76276, 76330, 76387, 76472, 76475, 76784, 76842, 76942, 77044, 77129, 77130, 77401,
    77583, 77685, 77695, 78940, 82843, 82953, 83679, 83709, 83974, 84092, 84143, 84261, 84314, 84411, 84552, 84562,
    84633, 84640, 84763, 84853, 84854, 84879, 85192, 85280, 85415, 85560, 85989, 86682, 86711, 87012, 87112, 87508,
    87566, 87628, 87867, 87898, 87980, 88061, 88074, 88154, 88274, 88342, 88397, 88454, 89597, 90110, 90151, 90168,
    90234, 90281, 90314, 90386, 90410, 90460, 90633, 90694, 90705, 90727, 90788, 91222, 91884, 92344, 92492, 93190,
    93430, 94464, 94713, 94732, 94895, 95039, 95608, 95923, 96211, 99035, 102297, 102994, 103363, 103966, 104341, 105772,
    106479, 106573, 106629, 106637, 106734, 106815, 106920, 107174, 107307, 107559, 107639, 107793, 107832, 107873, 108351, 108451,
    108527, 108649, 108683, 109008, 109367, 109911, 109965, 109977, 110110, 110201, 110347, 110606, 110707, 110781, 111045, 111158,
    111159, 111595, 111680, 112596, 112641, 112692, 112958, 112963, 113198, 113201, 113302, 113324, 113357, 113803, 114038, 114039,
    115039, 115803, 115888, 116512, 116904, 116946, 117002, 117092, 118154, 119214, 119423, 119484, 119586, 119623, 119696, 119957,
    120141, 120381, 120404, 121312, 121895, 122469, 122590, 122973, 123403, 123480, 123509, 125462, 126778, 127346, 127488, 128507,
    128598, 131225
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
    18055, 21866, 23941, 25587, 28750, 30259, 32473, 32497, 33444, 40763, 42414, 43550, 45155, 47423, 47646, 52638,
    53174, 53415, 60951, 64806, 70446, 78420, 81599, 87076, 89575, 93859, 98913, 102411, 108309, 108633, 110941, 114222,
    120193, 122175, 122969, 130750
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
