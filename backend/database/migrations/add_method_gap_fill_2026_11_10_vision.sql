-- Method gap fill (2026-11-10 audit), group B: vision architectures,
-- augmentation and attention. Squeeze-and-Excitation (1709.01507), Feature
-- Pyramid Network (1612.03144), VGG (1409.1556), Inception/GoogLeNet
-- (1409.4842), DenseNet (1608.06993), mixup (1710.09412) and RandAugment
-- (1909.13719) have introducing papers. Dilated convolution (the wavelet
-- "algorithme a trous", then DeepLab 1412.7062 before Yu & Koltun 1511.07122),
-- data augmentation and cross-attention have contested origins, so they keep
-- source_paper_id NULL with a canonical reference in source_url (see
-- add_neural_architecture_search_method.sql).
--
-- Keywords tag papers through the daily keyword backfill. Case-sensitive
-- keywords match as substrings, so bare "VGG" (VGGT, VGGSound, VGGFace),
-- "Inception" (Frechet Inception Distance, Inception Score), "SE", "FPN" and
-- "ASPP" stay out of keywords; lowercase long forms match on word boundaries.
-- Hero images are imported separately with import_entity_image.py.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'squeeze-and-excitation', 'Squeeze-and-Excitation',
    'Squeeze-and-Excitation Network (SENet)',
    'Squeeze-and-Excitation (SE) is a channel attention block for convolutional networks. It "squeezes" each feature map into a channel descriptor with [global average pooling](/methods/global-average-pooling), passes the descriptor through a small bottleneck of two fully connected layers ending in a sigmoid (the "excitation"), and rescales every channel of the input by the resulting weight, so the network learns which channels to emphasize for each input at very little extra cost. [Hu et al.](/paper/1709.01507) inserted SE blocks into [ResNet](/methods/resnet), ResNeXt and Inception models; the resulting SENets won the ILSVRC 2017 classification challenge with a 2.25% top-5 error. SE blocks became a standard component of efficient backbones such as [MobileNet](/methods/mobilenet)V3 and [EfficientNet](/methods/efficientnet), and inspired later channel and spatial attention modules such as [CBAM](/paper/1807.06521).',
    'squeeze-and-excitation, squeeze and excitation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2017,
    (SELECT id FROM papers WHERE arxiv_id = '1709.01507'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Squeeze-and-Excitation Networks',
    'https://github.com/hujie-frank/SENet',
    NULL,
    'always',
    ARRAY['SENet', 'SE block']
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'dilated-convolution',
    'Dilated Convolution',
    'Dilated Convolution (Atrous Convolution)',
    'A dilated, or atrous, [convolution](/methods/convolution) spaces the taps of its kernel apart by a dilation rate, so a 3×3 kernel with rate 2 covers a 5×5 window while keeping nine weights. Stacking convolutions with exponentially growing dilation rates enlarges the receptive field exponentially without pooling, striding or extra parameters, which preserves spatial resolution for dense prediction. The idea comes from the *algorithme à trous* for wavelet transforms (Holschneider et al., 1989). [DeepLab](/paper/1412.7062) brought atrous convolution to semantic segmentation, and [Yu and Koltun](/paper/1511.07122) named dilated convolutions and used them for multi-scale context aggregation; [DeepLabv2](/paper/1606.00915) combined several rates in atrous spatial pyramid pooling (ASPP), refined in [DeepLabv3](/paper/1706.05587). Dilated causal convolutions are the backbone of [WaveNet](/methods/wavenet) and [temporal convolutional networks](/methods/temporal-convolutional-network), and dilation is used throughout segmentation, detection, audio and time-series models.',
    'dilated convolution, atrous convolution, atrous spatial pyramid pooling',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    NULL,
    NULL,
    'https://arxiv.org/abs/1603.07285',
    'A guide to convolution arithmetic for deep learning',
    NULL,
    NULL,
    'always',
    ARRAY['Atrous Convolution']
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'feature-pyramid-network',
    'Feature Pyramid Network',
    'Feature Pyramid Network (FPN)',
    'A Feature Pyramid Network (FPN) builds a multi-scale feature pyramid with strong semantics at every level from a single-scale input image. It takes the feature maps of a backbone such as [ResNet](/methods/resnet) at several stages, then runs a top-down pathway that upsamples the coarse, semantically strong maps and merges them through lateral [1x1 convolutions](/methods/1x1-convolution) with the higher-resolution maps beneath, so each level can predict objects of its own size. [Lin et al.](/paper/1612.03144) showed that adding FPN to [Faster R-CNN](/methods/faster-r-cnn) gave state-of-the-art single-model results on COCO detection at little extra cost. FPN became the standard neck of detectors and segmenters such as [Mask R-CNN](/methods/mask-r-cnn) and [RetinaNet](/paper/1708.02002), and inspired variants such as PANet, NAS-FPN and BiFPN.',
    'feature pyramid network',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2016,
    (SELECT id FROM papers WHERE arxiv_id = '1612.03144'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Feature Pyramid Networks for Object Detection',
    'https://github.com/facebookresearch/detectron2/blob/main/detectron2/modeling/backbone/fpn.py',
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'vgg', 'VGG', 'VGGNet',
    'VGG is a family of deep [convolutional networks](/methods/cnn) from the Visual Geometry Group at Oxford that showed depth is key to accuracy in image recognition. [Simonyan and Zisserman](/paper/1409.1556) built networks of 11 to 19 weight layers entirely from stacked 3×3 [convolutions](/methods/convolution) with stride 1, interleaved with 2×2 [max pooling](/methods/max-pooling) and followed by three fully connected layers; two stacked 3×3 layers cover a 5×5 receptive field with fewer parameters and an extra non-linearity. The 16- and 19-layer models (VGG-16 and VGG-19) placed first in localization and second in classification at ILSVRC 2014. Their simple, uniform design made VGG a standard backbone for detection, segmentation and style transfer, and its pretrained features are still widely used in perceptual losses, although [ResNet](/methods/resnet) and later architectures with far fewer parameters have replaced it as a classifier.',
    'vggnet, vgg-net, vgg-16, vgg16, vgg-19, vgg19',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2014,
    (SELECT id FROM papers WHERE arxiv_id = '1409.1556'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Very Deep Convolutional Networks for Large-Scale Image Recognition',
    'https://github.com/pytorch/vision/blob/main/torchvision/models/vgg.py',
    NULL,
    'judge',
    ARRAY['VGGNet', 'VGG-16', 'VGG-19']
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'inception', 'Inception',
    'Inception (GoogLeNet)',
    'Inception is a family of [convolutional network](/methods/cnn) architectures built from Inception modules, which run 1×1, 3×3 and 5×5 [convolutions](/methods/convolution) and a pooling branch in parallel and concatenate their outputs, using [1x1 convolutions](/methods/1x1-convolution) to reduce channels before the expensive branches. This lets the network capture several spatial scales at once while keeping computation in check. [Szegedy et al.](/paper/1409.4842) introduced it with GoogLeNet, a 22-layer network that won the ILSVRC 2014 classification challenge with 6.67% top-5 error using about 12 times fewer parameters than AlexNet. Later versions factorized convolutions and added [batch normalization](/methods/batch-normalization) and label smoothing ([Inception-v3](/paper/1512.00567)), and combined Inception modules with residual connections ([Inception-v4 and Inception-ResNet](/paper/1602.07261)). An ImageNet-trained Inception-v3 is the feature extractor behind the Inception Score and the [Fréchet Inception Distance](/methods/frechet-inception-distance-fid).',
    'googlenet, inception module, inception architecture, inception network, inception-resnet',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2014,
    (SELECT id FROM papers WHERE arxiv_id = '1409.4842'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Going Deeper with Convolutions',
    'https://github.com/pytorch/vision/blob/main/torchvision/models/googlenet.py',
    NULL,
    'judge',
    ARRAY['GoogLeNet', 'Inception-v3', 'Inception-v4']
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'densenet', 'DenseNet',
    'DenseNet (Densely Connected Convolutional Network)',
    'DenseNet is a [convolutional network](/methods/cnn) architecture in which every layer of a dense block receives the concatenated feature maps of all preceding layers and passes its own maps to all later ones, giving L(L+1)/2 direct connections in an L-layer block. [Huang et al.](/paper/1608.06993) showed that this dense connectivity strengthens feature propagation and reuse, eases vanishing gradients and lets each layer add only a few channels (the growth rate), so DenseNets match or beat [ResNet](/methods/resnet) on CIFAR, SVHN and ImageNet with substantially fewer parameters and less computation. Dense blocks are separated by transition layers with [batch normalization](/methods/batch-normalization), [1x1 convolutions](/methods/1x1-convolution) and pooling. Where ResNet adds features through [skip connections](/methods/skip-connection), DenseNet concatenates them; DenseNet-121 and its variants remain common backbones in medical imaging and dense prediction.',
    'densenet, densely connected convolutional network',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2016,
    (SELECT id FROM papers WHERE arxiv_id = '1608.06993'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Densely Connected Convolutional Networks',
    'https://github.com/liuzhuang13/DenseNet',
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'data-augmentation',
    'Data Augmentation',
    'Data Augmentation',
    'Data augmentation enlarges and diversifies a training set by applying label-preserving transformations to existing examples, which acts as a regularizer, reduces overfitting and builds invariances into a model. For images this includes random crops, flips, rotations, scaling, color jitter and noise; for text, synonym replacement, back-translation and paraphrasing; and for audio, time stretching, pitch shifts and SpecAugment-style masking. Mixed-sample methods such as [mixup](/methods/mixup), [Cutout](/methods/cutout) and [CutMix](/methods/cutmix) blend or erase parts of examples, and policy-search methods such as [AutoAugment](/paper/1805.09501) and [RandAugment](/methods/randaugment) choose which transformations to apply. Augmentation has been part of training neural networks for decades and was central to successes such as [AlexNet](/methods/alexnet); it also supplies the views compared in [contrastive](/methods/contrastive-learning) and [self-supervised learning](/methods/self-supervised-learning), and generative models are increasingly used to synthesize additional training data.',
    'data augmentation',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1186/s40537-019-0197-0',
    'A survey on Image Data Augmentation for Deep Learning',
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'mixup', 'Mixup', 'mixup',
    'Mixup is a [data augmentation](/methods/data-augmentation) and regularization method that trains a network on convex combinations of pairs of examples and their labels: given two inputs and their one-hot labels, it forms λ·x₁ + (1−λ)·x₂ and λ·y₁ + (1−λ)·y₂ with λ drawn from a Beta(α, α) distribution. [Zhang et al.](/paper/1710.09412) introduced it as an alternative to [empirical risk minimization](/methods/empirical-risk-minimization) that encourages the model to behave linearly between training examples, and showed that it improves generalization on ImageNet, CIFAR, speech and tabular data, reduces memorization of corrupted labels, increases robustness to adversarial examples and stabilizes GAN training. Mixup also tends to improve calibration. Variants include Manifold Mixup, which mixes hidden representations, and [CutMix](/methods/cutmix), which pastes image patches instead of blending whole images; mixup is a standard component of modern image-classification training recipes alongside [RandAugment](/methods/randaugment) and [label smoothing](/methods/label-smoothing).',
    'mixup',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2017,
    (SELECT id FROM papers WHERE arxiv_id = '1710.09412'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'mixup: Beyond Empirical Risk Minimization',
    'https://github.com/facebookresearch/mixup-cifar10',
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'randaugment', 'RandAugment', 'RandAugment',
    'RandAugment is an automated [data augmentation](/methods/data-augmentation) method that replaces learned augmentation policies with two interpretable hyperparameters: for each training image it applies N transformations chosen uniformly at random from a fixed list of about 14 operations (rotation, shear, translation, color, contrast, posterize, solarize and others), all at a shared magnitude M. [Cubuk et al.](/paper/1909.13719) showed that this tiny search space, tuned with a simple grid search, matches or beats [AutoAugment](/paper/1805.09501) and Population Based Augmentation, which need an expensive separate search on a proxy task, and that the best magnitude grows with model and dataset size. RandAugment improved [EfficientNet](/methods/efficientnet) ImageNet accuracy and COCO detection, and is a default augmentation in training recipes for [vision transformers](/methods/vision-transformer) and modern convolutional networks, often combined with [mixup](/methods/mixup) and [CutMix](/methods/cutmix).',
    'randaugment',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2019,
    (SELECT id FROM papers WHERE arxiv_id = '1909.13719'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'RandAugment: Practical automated data augmentation with a reduced search space',
    'https://github.com/tensorflow/tpu/blob/master/models/official/efficientnet/autoaugment.py',
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

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'cross-attention', 'Cross-Attention', 'Cross-Attention',
    'Cross-attention is an [attention](/methods/attention) mechanism in which the queries come from one sequence or modality and the keys and values from another, so each element of the first attends over the second and gathers the information it needs. In the encoder-decoder [Transformer](/paper/1706.03762), every decoder layer has a cross-attention (encoder-decoder attention) sublayer that lets target tokens attend over the encoded source, as decoder states attend over encoder states in earlier [additive attention](/methods/additive-attention) for neural machine translation. Unlike self-attention, its cost scales with the product of the two sequence lengths. Cross-attention is the standard way to condition one stream on another: text conditioning in [latent diffusion](/paper/2112.10752) and [Stable Diffusion](/methods/stable-diffusion), visual tokens in vision-language models such as Flamingo, object queries over image features in [DETR](/methods/detr), and compact latent arrays that read large inputs in the [Perceiver](/paper/2103.03206). It is usually implemented as [multi-head attention](/methods/multi-head-attention).',
    'cross-attention, cross attention',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://lilianweng.github.io/posts/2018-06-24-attention/',
    'Attention? Attention! (Lilian Weng)',
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

-- Introduced banners for the methods with a source paper.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN ('squeeze-and-excitation', 'feature-pyramid-network', 'vgg', 'inception', 'densenet', 'mixup', 'randaugment')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug IN ('squeeze-and-excitation', 'feature-pyramid-network', 'vgg', 'inception', 'densenet', 'mixup', 'randaugment')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed paper links (2026-11-10). Candidates: local Semantic Scholar citers
-- of each source paper (link_papers_by_source_citations.py) plus bounded
-- title/abstract regex matches. Positives name and use, extend, analyze or
-- compare against the method in their title or abstract; citers that do not
-- name it, and reviewed passing mentions, become durable exclusions so the
-- keyword and reference backfills do not re-link them. VGG candidates skip
-- VGGT, VGGSound, VGGFace and VGGish mentions; data augmentation and
-- cross-attention keep every exact-phrase match except reviewed passing
-- mentions ("without data augmentation", "avoids cross-attention").

-- squeeze-and-excitation: 50 links, 111 exclusions.
CREATE TEMP TABLE se_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'squeeze-and-excitation'
  AND p.id IN (
        873, 928, 940, 1026, 1139, 1404, 1450, 1574, 1761, 1980, 2045, 2332, 2645, 4774, 4854, 5153,
        5373, 6555, 6857, 9267, 10370, 12329, 12530, 19148, 21746, 23498, 32177, 36945, 47998, 49709, 58053, 65788,
        68629, 71568, 75359, 78594, 79546, 79869, 80848, 81318, 82116, 104076, 104654, 104671, 105560, 105809, 109400, 111776,
        114385, 115260
  );

DELETE FROM paper_method_exclusions x
USING se_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM se_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM se_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE se_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'squeeze-and-excitation'
  AND p.id IN (
        2845, 15979, 19359, 42716, 44498, 52872, 52891, 53065, 53700, 53758, 54438, 54703, 54791, 55017, 56219, 58216,
        58316, 58968, 59430, 59781, 60010, 60204, 60876, 62913, 62953, 62989, 63671, 64063, 64163, 64250, 64365, 64718,
        64895, 65073, 65583, 65601, 65848, 66000, 66190, 66705, 66954, 67753, 67974, 68008, 68286, 68474, 68521, 68795,
        69090, 69133, 69276, 69374, 69375, 82861, 82939, 84312, 84705, 84980, 84988, 85342, 85355, 86386, 87290, 90221,
        92695, 94207, 95948, 96813, 99392, 100704, 100803, 101642, 101813, 102381, 102679, 104289, 104729, 106787, 106836, 106906,
        106999, 107293, 107648, 107767, 108418, 111546, 112028, 112030, 114111, 117408, 117697, 117781, 117862, 117995, 118516, 118937,
        119064, 119122, 119254, 119411, 122440, 123357, 123967, 124875, 125462, 127630, 128199, 129271, 130228, 130263, 130549
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use Squeeze-and-Excitation (citation-only or passing mention)'
FROM se_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING se_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING se_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- dilated-convolution: 89 links, 6 exclusions.
CREATE TEMP TABLE dilated_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dilated-convolution'
  AND p.id IN (
        275, 389, 767, 937, 1091, 1429, 1473, 1503, 1637, 1826, 1925, 2075, 2122, 2565, 3211, 3212,
        3324, 3390, 3419, 3658, 4255, 4605, 4789, 5423, 5705, 6372, 6773, 7296, 7431, 11575, 11890, 12526,
        13648, 15150, 16781, 17283, 17914, 19929, 20304, 24545, 25993, 26577, 28583, 35591, 35766, 36035, 38856, 39000,
        41592, 43011, 52730, 62913, 65195, 65285, 69401, 69912, 70985, 71870, 72004, 75229, 75760, 78728, 79404, 79546,
        80167, 80438, 80909, 82017, 82036, 82080, 82218, 82271, 84112, 92145, 96345, 98335, 104250, 105122, 105145, 105282,
        109562, 114098, 114143, 115199, 120335, 120481, 120519, 121535, 122038
  );

DELETE FROM paper_method_exclusions x
USING dilated_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dilated_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM dilated_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE dilated_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dilated-convolution'
  AND p.id IN (
        4830, 5576, 7637, 9506, 11410, 116811
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use dilated convolution (citation-only or passing mention)'
FROM dilated_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING dilated_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING dilated_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- feature-pyramid-network: 60 links, 37 exclusions.
CREATE TEMP TABLE fpn_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'feature-pyramid-network'
  AND p.id IN (
        538, 1742, 1963, 2819, 2834, 2902, 2918, 3303, 3671, 4588, 4612, 4727, 5071, 5551, 5880, 7037,
        7274, 8497, 8595, 9059, 9391, 9628, 10893, 10920, 11154, 11661, 19144, 19391, 19538, 20679, 20757, 21445,
        25392, 28207, 30770, 32568, 34501, 36329, 42740, 43643, 43809, 48513, 58320, 61554, 78031, 79082, 79366, 79733,
        81493, 84080, 85019, 105213, 105460, 108684, 108744, 109472, 113995, 114325, 114975, 116579
  );

DELETE FROM paper_method_exclusions x
USING fpn_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM fpn_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM fpn_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE fpn_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'feature-pyramid-network'
  AND p.id IN (
        26410, 54558, 58006, 58203, 83236, 83464, 85420, 85468, 85631, 87522, 88608, 95702, 98530, 99272, 99282, 102352,
        103153, 108832, 109846, 117727, 117731, 117967, 117979, 117995, 118089, 119005, 119555, 121072, 121403, 121650, 122440, 123869,
        124943, 125880, 126297, 127780, 128436
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use Feature Pyramid Networks (citation-only or passing mention)'
FROM fpn_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING fpn_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING fpn_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- vgg: 150 links, 456 exclusions.
CREATE TEMP TABLE vgg_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'vgg'
  AND p.id IN (
        108, 121, 181, 195, 289, 442, 446, 527, 734, 802, 837, 1028, 1050, 1082, 1094, 1140,
        1409, 1428, 1908, 2064, 2116, 2440, 2488, 2667, 3167, 3210, 3236, 3270, 3297, 3426, 3728, 4318,
        4480, 4639, 4865, 4875, 4928, 5021, 5289, 5888, 6256, 6886, 6970, 7211, 7321, 8025, 8970, 9081,
        9122, 9335, 9375, 9723, 10075, 11365, 11638, 11708, 11935, 13364, 13560, 13692, 15675, 15714, 17147, 17174,
        17751, 18205, 19529, 19715, 23244, 28516, 28742, 28962, 30001, 30845, 33919, 34606, 35397, 36165, 36235, 36555,
        37017, 38078, 38117, 39164, 39231, 40220, 44980, 47990, 50241, 59414, 61650, 63476, 64015, 65243, 65744, 69066,
        71627, 72768, 75458, 75661, 76001, 76811, 77224, 78329, 78901, 78969, 79158, 80137, 80284, 80285, 80731, 81515,
        81589, 81651, 82070, 82195, 82228, 82390, 82422, 82460, 83326, 84469, 85445, 87011, 88334, 89146, 89919, 91310,
        91855, 92150, 96433, 97979, 99295, 99878, 100971, 101822, 106499, 106714, 108668, 109191, 109217, 109232, 113013, 119137,
        121822, 122821, 124071, 126051, 129583, 130029
  );

DELETE FROM paper_method_exclusions x
USING vgg_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM vgg_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM vgg_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE vgg_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'vgg'
  AND p.id IN (
        11232, 51074, 51117, 51132, 51381, 51888, 51892, 51977, 52118, 52120, 52127, 52274, 52368, 52406, 52486, 52580,
        52605, 52730, 52821, 52881, 52939, 53096, 53214, 53449, 54045, 54185, 54212, 54401, 54438, 54491, 54525, 54590,
        54632, 54633, 54772, 54779, 54791, 54850, 54895, 55116, 55594, 55820, 56255, 56731, 56737, 56929, 56961, 57137,
        57152, 57329, 57335, 57841, 57947, 58215, 58476, 58930, 59016, 59090, 59262, 59565, 59655, 59739, 59782, 59791,
        59807, 59832, 60027, 60031, 60203, 60356, 60876, 61011, 61235, 61346, 61363, 61370, 61840, 61924, 62097, 62142,
        62588, 62770, 62884, 63010, 63150, 63315, 63319, 63340, 63845, 64002, 64082, 64266, 64498, 64522, 64534, 64608,
        64775, 64877, 64884, 64912, 65004, 65134, 65318, 65340, 65353, 65585, 65638, 66000, 66190, 66460, 66606, 66692,
        66928, 67067, 67424, 67469, 67608, 67649, 67724, 68059, 68310, 68311, 68324, 68391, 68503, 68516, 68604, 68641,
        68694, 68715, 68731, 69023, 69090, 69155, 69211, 69235, 69278, 69332, 69387, 69427, 69738, 69814, 69828, 69842,
        69876, 69899, 69920, 70017, 70107, 70199, 70228, 70475, 70508, 70511, 70524, 70611, 70622, 70683, 70871, 70887,
        71050, 71091, 71163, 71249, 71424, 71434, 71475, 71502, 71715, 71742, 71799, 71807, 71826, 71919, 71939, 71948,
        72143, 72170, 82847, 82944, 83592, 83649, 83659, 83661, 83708, 83769, 83891, 84046, 84077, 84119, 84196, 84259,
        84356, 84407, 84457, 84514, 84569, 84615, 84826, 84886, 84905, 84959, 84980, 85175, 85192, 85255, 85261, 85283,
        85298, 85305, 85313, 85321, 85360, 85442, 85473, 85502, 85505, 85540, 85712, 85781, 85807, 85843, 85864, 85987,
        86022, 86037, 86096, 86366, 86487, 86818, 86828, 86854, 87122, 87244, 87411, 87477, 87561, 87594, 87612, 87622,
        87662, 87690, 87750, 87780, 87826, 87880, 87915, 87937, 87967, 87977, 87986, 88025, 88039, 88148, 88170, 88195,
        88230, 88238, 88276, 88371, 88421, 88457, 88489, 88510, 88929, 88983, 89734, 89929, 89945, 92504, 92638, 92646,
        92656, 92970, 93245, 93409, 93444, 93549, 93739, 93979, 94027, 94057, 94128, 94143, 94210, 94264, 94279, 94328,
        94384, 94481, 94690, 94903, 94980, 94982, 95465, 96755, 96820, 98038, 98539, 99187, 99267, 99320, 99473, 99623,
        99653, 99795, 99805, 99818, 99865, 99975, 100341, 100409, 100546, 100579, 100613, 100698, 100738, 100789, 101153, 101172,
        101310, 101322, 101349, 101448, 101507, 101638, 101674, 101746, 101767, 101792, 101858, 101939, 102007, 102227, 102313, 102344,
        102381, 102395, 102585, 102639, 102792, 103337, 103341, 104842, 104868, 105208, 105273, 105304, 105400, 105560, 106443, 106495,
        106498, 106515, 106527, 106557, 106650, 106675, 106712, 106722, 106836, 106873, 106922, 107067, 107070, 107071, 107076, 107109,
        107120, 107167, 107249, 107318, 107403, 107407, 107485, 107556, 107564, 107641, 107652, 107665, 107666, 107705, 107878, 108162,
        108188, 108288, 108290, 108422, 108452, 108492, 108743, 108992, 110393, 112313, 112981, 113939, 117259, 117437, 117491, 117500,
        117576, 117657, 117716, 118396, 118533, 118558, 118615, 118770, 118876, 119025, 119074, 119099, 119168, 119542, 119550, 119567,
        120002, 120394, 121075, 121275, 122101, 123021, 123125, 123382, 123550, 124176, 124769, 124890, 124918, 124939, 124973, 125295,
        125376, 125743, 125914, 126120, 126757, 127025, 127643, 127760, 128510, 128599, 128843, 128937, 129158, 129175, 129366, 130254,
        130366, 130442, 130498, 130499, 130778, 130794, 131141, 131598
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use VGG (citation-only or passing mention)'
FROM vgg_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING vgg_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING vgg_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- inception: 64 links, 98 exclusions.
CREATE TEMP TABLE inception_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'inception'
  AND p.id IN (
        111, 121, 194, 221, 268, 317, 478, 724, 918, 1082, 1332, 1658, 1987, 2085, 2406, 2501,
        2670, 2978, 3364, 3659, 3732, 3925, 3949, 4593, 5021, 5199, 5635, 5714, 7405, 8025, 9081, 9723,
        11511, 13367, 17751, 23244, 35990, 36165, 42878, 43102, 43191, 61786, 64163, 65243, 66990, 72497, 74037, 74924,
        78329, 78503, 78969, 79158, 82339, 82390, 82422, 91855, 96433, 104270, 105677, 109223, 114871, 116811, 117451, 124629
  );

DELETE FROM paper_method_exclusions x
USING inception_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM inception_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM inception_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE inception_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'inception'
  AND p.id IN (
        151, 3189, 9538, 17119, 25959, 51892, 53211, 53343, 54398, 54436, 54790, 55133, 56731, 56885, 56929, 57329,
        58295, 58580, 59768, 60074, 60206, 61179, 61565, 62620, 64082, 65143, 66000, 66707, 67506, 68211, 69014, 69051,
        69278, 69427, 69524, 70208, 70228, 70573, 70971, 73902, 82944, 84826, 84980, 85473, 85797, 86218, 86386, 87559,
        87622, 87624, 92504, 93004, 93600, 94171, 94282, 94565, 94690, 98656, 99573, 99972, 100181, 100684, 100835, 101153,
        101288, 101310, 101663, 101746, 101901, 101979, 102121, 102381, 104490, 104558, 105274, 107249, 107339, 108020, 108326, 108743,
        109082, 112147, 117437, 117788, 118164, 118391, 118923, 119558, 122381, 125125, 125164, 127112, 128888, 129138, 129803, 130309,
        130366, 130442
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use Inception/GoogLeNet (citation-only or passing mention)'
FROM inception_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING inception_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING inception_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- densenet: 100 links, 225 exclusions.
CREATE TEMP TABLE densenet_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'densenet'
  AND p.id IN (
        194, 448, 751, 782, 788, 799, 850, 859, 1023, 1026, 1054, 1139, 1154, 1273, 1301, 1404,
        1428, 1570, 1637, 1932, 2029, 2042, 2354, 2488, 2624, 2733, 2868, 3084, 3156, 3167, 3659, 3949,
        4255, 4480, 4599, 4899, 5164, 6153, 6773, 8025, 8502, 9081, 11002, 12665, 13560, 13692, 15422, 17751,
        18015, 18205, 18339, 19529, 19787, 24942, 27371, 28620, 29620, 30001, 30845, 33389, 34625, 35397, 36165, 38078,
        44850, 47990, 48100, 50706, 52094, 60010, 62355, 65033, 67649, 69066, 72672, 73323, 73739, 78969, 80284, 80550,
        80917, 81383, 81589, 81765, 81766, 82023, 82083, 85445, 94386, 96433, 97979, 98301, 105473, 109219, 111546, 115013,
        115371, 124736, 125294, 129740
  );

DELETE FROM paper_method_exclusions x
USING densenet_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM densenet_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM densenet_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE densenet_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'densenet'
  AND p.id IN (
        83, 48433, 48507, 48778, 48843, 49002, 49096, 49159, 49894, 50159, 51911, 51916, 51977, 52072, 54195, 54438,
        54651, 54791, 55042, 56364, 56730, 56731, 56737, 59012, 59415, 59416, 59739, 59791, 60020, 60027, 60031, 60465,
        60681, 61011, 61013, 61828, 61924, 62442, 62729, 63992, 65182, 65285, 65428, 65519, 65547, 66000, 66001, 67682,
        68046, 68516, 69738, 69814, 70071, 70228, 70524, 70549, 70566, 70611, 70658, 70856, 70871, 70982, 71147, 71502,
        71538, 71583, 71715, 71721, 71826, 71870, 71875, 72018, 72132, 72534, 72676, 72740, 72797, 72968, 73095, 73099,
        73175, 73219, 73270, 81991, 82944, 83463, 83683, 84022, 84306, 84392, 84604, 84826, 84912, 84988, 84991, 85261,
        85364, 85628, 85756, 85987, 86022, 86184, 86336, 86380, 86386, 86469, 86487, 86652, 86739, 86851, 86854, 87244,
        87260, 87358, 87612, 87632, 87826, 88292, 88300, 88387, 88457, 88563, 88612, 88632, 88665, 89131, 89207, 89299,
        89419, 89453, 89618, 90067, 90581, 92655, 92970, 93245, 93521, 93549, 93577, 93615, 93700, 94057, 94123, 94126,
        94171, 94272, 94322, 94384, 94690, 94838, 94903, 95920, 97830, 98144, 99373, 99473, 99609, 99723, 99971, 100429,
        100558, 100594, 100632, 100971, 101153, 101155, 101268, 101322, 101642, 101774, 101916, 102381, 104300, 105024, 105208, 105315,
        105581, 105785, 105813, 105867, 105954, 106498, 107057, 107249, 107339, 107388, 107407, 107473, 107655, 107820, 107956, 108065,
        108290, 109280, 111061, 112020, 113806, 113939, 117807, 118186, 118232, 119074, 119282, 120335, 122333, 122351, 122381, 122759,
        122820, 122955, 123021, 123187, 123721, 124953, 125185, 125295, 125408, 125409, 125853, 127529, 127643, 130263, 130713, 131141,
        132002
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use DenseNet (citation-only or passing mention)'
FROM densenet_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING densenet_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING densenet_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- mixup: 148 links, 1138 exclusions.
CREATE TEMP TABLE mixup_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mixup'
  AND p.id IN (
        931, 1336, 1485, 2040, 2399, 3151, 3181, 4146, 4167, 4332, 4680, 4912, 4992, 5044, 5261, 5298,
        5898, 5933, 7019, 7255, 7347, 8176, 8353, 8832, 9011, 9089, 9320, 9466, 9497, 9638, 10254, 10728,
        11032, 11218, 11254, 12381, 13145, 13498, 13593, 13608, 13747, 13779, 13818, 14787, 15961, 16281, 16364, 16653,
        16725, 16768, 17149, 17278, 18560, 18884, 19677, 20661, 21041, 23352, 24671, 24970, 26768, 26821, 26999, 27106,
        27286, 27648, 28909, 29116, 29357, 29531, 30459, 33512, 34437, 36684, 37372, 38009, 39288, 42270, 48164, 49559,
        50942, 51417, 53852, 59769, 60198, 64074, 64910, 67995, 68417, 72116, 72797, 73858, 75325, 77658, 78449, 79209,
        79351, 80862, 84334, 84729, 84841, 85383, 86141, 87679, 90412, 90500, 90562, 90721, 91400, 91681, 91844, 95052,
        97999, 98078, 98656, 99095, 100289, 102065, 105074, 105169, 106356, 107664, 108144, 109424, 109683, 111133, 111953, 112527,
        113026, 113053, 113581, 113586, 114365, 114439, 115133, 115642, 115937, 116034, 116397, 116756, 117203, 118140, 119778, 120184,
        120301, 121519, 123079, 127195
  );

DELETE FROM paper_method_exclusions x
USING mixup_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mixup_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM mixup_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE mixup_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mixup'
  AND p.id IN (
        4112, 4243, 4252, 4317, 4358, 4585, 4589, 4668, 4672, 4683, 4703, 4710, 4730, 4742, 4763, 4782,
        4875, 4893, 4894, 4907, 4920, 4923, 4959, 4972, 4996, 5022, 5030, 5076, 5081, 5084, 5087, 5112,
        5129, 5186, 5188, 5196, 5234, 5238, 5283, 5291, 5306, 5341, 5395, 5400, 5426, 5438, 5444, 5523,
        5560, 5562, 5563, 5581, 5597, 5638, 5642, 5658, 5667, 5680, 5788, 5809, 5829, 5836, 5856, 5860,
        5881, 5883, 5910, 5928, 5929, 5942, 5943, 5947, 5955, 5991, 6018, 6051, 6063, 6112, 6123, 6156,
        6162, 6184, 6271, 6293, 6307, 6329, 6333, 6334, 6374, 6395, 6424, 6428, 6532, 6704, 6738, 6769,
        6791, 6799, 6800, 6855, 6870, 6908, 6917, 6949, 6996, 7081, 7200, 7259, 7260, 7271, 7281, 7288,
        7311, 7343, 7344, 7387, 7388, 7515, 7550, 7556, 7605, 7610, 7668, 7673, 7739, 7740, 7752, 7756,
        7758, 7777, 7839, 7841, 7874, 7884, 7888, 7889, 7895, 7949, 7956, 8010, 8018, 8027, 8049, 8079,
        8127, 8128, 8168, 8200, 8229, 8258, 8261, 8262, 8318, 8383, 8401, 8558, 8560, 8608, 8609, 8612,
        8614, 8651, 8719, 8720, 8721, 8722, 8747, 8752, 8767, 8904, 8912, 8919, 8928, 8959, 9049, 9219,
        9235, 9244, 9252, 9253, 9272, 9305, 9335, 9377, 9426, 9427, 9429, 9491, 9494, 9616, 9622, 9628,
        9659, 9708, 9785, 9804, 9813, 9848, 9866, 9971, 9972, 10041, 10049, 10056, 10092, 10097, 10171, 10195,
        10228, 10244, 10255, 10267, 10340, 10366, 10375, 10469, 10529, 10550, 10555, 10711, 10715, 10734, 10735, 10740,
        10760, 10765, 10801, 10822, 10836, 10863, 10882, 10886, 10930, 10932, 10944, 10991, 11002, 11031, 11239, 11268,
        11298, 11327, 11343, 11361, 11392, 11393, 11404, 11409, 11416, 11419, 11433, 11458, 11470, 11481, 11502, 11507,
        11561, 11610, 11611, 11613, 11661, 11668, 11700, 11741, 11756, 11761, 11769, 11790, 11821, 11829, 11832, 11833,
        11844, 11852, 11892, 11923, 11934, 11988, 12029, 12031, 12047, 12222, 12230, 12238, 12264, 12283, 12288, 12291,
        12297, 12338, 12419, 12452, 12488, 12588, 12608, 12683, 12690, 12752, 12758, 12787, 12835, 12837, 12860, 12869,
        12971, 13007, 13030, 13093, 13095, 13132, 13231, 13268, 13270, 13297, 13298, 13299, 13452, 13455, 13514, 13534,
        13560, 13585, 13605, 13706, 13794, 13803, 13816, 13854, 13875, 13885, 13935, 13960, 13961, 13980, 13999, 14019,
        14068, 14154, 14172, 14196, 14212, 14233, 14243, 14262, 14272, 14288, 14315, 14318, 14328, 14369, 14421, 14462,
        14472, 14508, 14510, 14618, 14632, 14640, 14657, 14831, 14880, 14899, 14912, 14916, 14933, 15091, 15093, 15094,
        15185, 15470, 15513, 15598, 15602, 15646, 15894, 15897, 15935, 16114, 16115, 16162, 16482, 16483, 16495, 16632,
        16721, 16812, 16832, 16875, 16880, 17004, 17041, 17082, 17085, 17130, 17138, 17270, 17290, 17309, 17319, 17394,
        17437, 17468, 17607, 17614, 17669, 17691, 17702, 17717, 17763, 17836, 17882, 17903, 17925, 17953, 18013, 18142,
        18219, 18251, 18319, 18323, 18368, 18508, 18527, 18534, 18545, 18558, 18568, 18577, 18620, 18684, 18718, 18821,
        18825, 18831, 18835, 18851, 18856, 18941, 18993, 19025, 19057, 19066, 19117, 19140, 19195, 19199, 19257, 19277,
        19281, 19349, 19466, 19488, 19556, 19637, 19657, 19759, 19763, 19828, 19898, 19916, 19928, 20026, 20057, 20067,
        20182, 20183, 20241, 20281, 20346, 20380, 20405, 20432, 20453, 20505, 20512, 20628, 20679, 20686, 20693, 20797,
        20822, 20831, 20981, 20993, 21060, 21087, 21117, 21129, 21195, 21265, 21372, 21485, 21539, 21605, 21916, 21932,
        22336, 22369, 22370, 22373, 22533, 22701, 22733, 22775, 22912, 22927, 23106, 23141, 23147, 23299, 23521, 23927,
        24027, 24058, 24130, 24240, 24306, 24456, 24612, 24686, 24765, 24772, 24835, 24856, 24860, 24867, 25076, 25111,
        25169, 25309, 25326, 25444, 25448, 25462, 25554, 25570, 25787, 25874, 25998, 26304, 26308, 26339, 26440, 26446,
        26470, 26540, 26578, 26732, 26820, 27045, 27085, 27205, 27308, 27316, 27346, 27519, 27833, 28044, 28201, 28219,
        28244, 28503, 28630, 28680, 28707, 28806, 28844, 28899, 28901, 28924, 28930, 28961, 29053, 29112, 29293, 29300,
        29312, 29372, 29400, 29476, 29537, 29616, 29620, 29645, 29653, 29655, 29700, 29725, 29878, 29904, 30166, 30230,
        30418, 30619, 30845, 30927, 31055, 31058, 31265, 31322, 31480, 31549, 31585, 31672, 31756, 31791, 31840, 31848,
        31919, 31927, 32275, 32371, 32379, 32430, 32445, 32466, 32623, 32791, 32899, 32905, 33011, 33148, 33376, 33660,
        34149, 34223, 34269, 34410, 34426, 34497, 34533, 34674, 34728, 34828, 34874, 34987, 35043, 35243, 35654, 35716,
        35790, 35802, 35848, 35870, 36030, 36071, 36184, 36227, 36360, 36408, 36598, 36878, 36898, 36951, 37112, 37438,
        37503, 37902, 38117, 38335, 38502, 38565, 38671, 39087, 39136, 39139, 39324, 39455, 39752, 39843, 39916, 40015,
        40251, 40336, 40394, 40797, 40800, 40869, 40902, 41044, 41238, 41242, 41258, 41592, 41997, 42229, 42635, 42666,
        43726, 44058, 44458, 44965, 45237, 45554, 45958, 46394, 46465, 46475, 46617, 46985, 47051, 47103, 47113, 47383,
        47505, 47770, 47842, 48019, 48473, 48557, 49095, 49474, 49691, 50099, 50210, 50440, 50738, 51469, 51950, 52159,
        52755, 52910, 52981, 53214, 53403, 53507, 53519, 54008, 54436, 54717, 54865, 55051, 56441, 56496, 56687, 57249,
        58295, 58772, 59146, 60010, 60275, 61363, 61370, 61492, 61519, 61827, 62177, 62374, 64493, 64563, 64649, 64895,
        65112, 65315, 65340, 65659, 65677, 65901, 68474, 68516, 68872, 68947, 68986, 69421, 69616, 69759, 69996, 70138,
        70228, 70379, 70525, 70714, 71124, 71682, 71870, 71875, 71913, 72515, 72672, 72767, 73281, 73478, 73541, 73592,
        73594, 73814, 73865, 73937, 74018, 74313, 74717, 74777, 74785, 75304, 75493, 75712, 75880, 75928, 76136, 76209,
        76520, 76679, 76902, 76931, 76953, 77051, 77191, 77303, 77482, 77575, 78027, 78310, 78335, 78371, 78455, 78531,
        78579, 78618, 78755, 78861, 78940, 78993, 79015, 79073, 79077, 79084, 79256, 79474, 79534, 79550, 79600, 79614,
        79626, 79636, 79639, 79695, 79743, 79776, 79791, 80040, 80063, 80067, 80144, 80223, 80262, 80356, 80367, 80382,
        80404, 80419, 80438, 80682, 80871, 80876, 80878, 80976, 82831, 83973, 84070, 84306, 84356, 84470, 84575, 84664,
        84708, 84888, 85142, 85190, 85255, 85261, 85412, 85439, 85618, 85690, 85820, 85859, 85873, 85955, 86039, 86487,
        86533, 86588, 86640, 86852, 87092, 87200, 87219, 87243, 87260, 87298, 87392, 87541, 87622, 87643, 87648, 87666,
        87828, 87909, 88015, 88092, 88133, 88146, 88468, 88632, 88699, 88751, 88788, 88876, 89076, 89136, 89144, 89207,
        89220, 89245, 89318, 89356, 89418, 89503, 89572, 89708, 89823, 89832, 90089, 90121, 90158, 90186, 90290, 90296,
        90304, 90331, 90378, 90425, 90459, 90588, 90662, 90794, 90871, 90992, 91013, 91088, 91261, 91361, 91569, 91605,
        91892, 91898, 91899, 91934, 91939, 91948, 91974, 92060, 92099, 92141, 92243, 92255, 92519, 92576, 92947, 93100,
        93186, 93192, 93234, 93424, 93433, 93459, 93577, 93779, 93873, 94010, 94227, 94632, 94690, 94903, 95047, 98570,
        98657, 98729, 98827, 99088, 99295, 99446, 99786, 99945, 99974, 100106, 100232, 100335, 100341, 100348, 101230, 101268,
        101350, 101400, 101477, 102381, 102513, 102606, 102692, 102721, 103860, 104496, 104588, 105715, 106209, 106419, 106728, 106816,
        106957, 107275, 107339, 107390, 107402, 107473, 107499, 107574, 107949, 108160, 108273, 108433, 108930, 109410, 109539, 109562,
        110732, 110971, 111312, 111461, 111520, 112407, 112457, 112487, 112539, 112548, 112756, 112881, 112883, 112957, 112984, 113146,
        113149, 113152, 113181, 113182, 113227, 113276, 113281, 113347, 113358, 113384, 113390, 113409, 113425, 113507, 113509, 113510,
        113517, 113612, 114484, 114839, 114933, 115136, 115298, 115444, 115457, 115464, 115486, 115492, 115555, 115627, 115663, 115688,
        115690, 115727, 115739, 115741, 115750, 115860, 115865, 115874, 115878, 115882, 115912, 115929, 115933, 115940, 116168, 116179,
        116193, 116223, 116349, 116457, 116481, 116603, 116607, 116638, 116644, 116667, 116749, 116758, 116808, 116874, 117060, 117086,
        117138, 117202, 117204, 117211, 117242, 117744, 118627, 118907, 119091, 119137, 119151, 119292, 119550, 120128, 120153, 120397,
        120495, 121647, 121972, 122749, 123217, 123487, 123649, 123651, 124769, 125294, 125997, 127502, 127584, 128599, 128607, 129271,
        129536, 131358
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use mixup (citation-only or passing mention)'
FROM mixup_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING mixup_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING mixup_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- randaugment: 5 links, 696 exclusions.
CREATE TEMP TABLE randaugment_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'randaugment'
  AND p.id IN (
        2050, 2618, 2800, 6428, 80821
  );

DELETE FROM paper_method_exclusions x
USING randaugment_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM randaugment_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM randaugment_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE randaugment_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'randaugment'
  AND p.id IN (
        2260, 2843, 2906, 3143, 3191, 3303, 3321, 3401, 3616, 3698, 3709, 3738, 4000, 4167, 4463, 4589,
        4730, 4763, 4782, 4894, 4923, 4955, 4996, 5022, 5052, 5076, 5112, 5143, 5196, 5261, 5278, 5279,
        5291, 5306, 5332, 5341, 5343, 5426, 5560, 5563, 5581, 5638, 5658, 5667, 5732, 5750, 5788, 5829,
        5836, 5860, 5898, 5928, 5929, 5947, 5957, 6018, 6035, 6051, 6112, 6114, 6156, 6168, 6261, 6277,
        6307, 6333, 6334, 6395, 6439, 6489, 6695, 6769, 6860, 6896, 6908, 6947, 6996, 7019, 7149, 7154,
        7170, 7200, 7221, 7255, 7259, 7260, 7281, 7311, 7387, 7388, 7456, 7537, 7550, 7552, 7562, 7572,
        7605, 7610, 7673, 7740, 7758, 7777, 7881, 7889, 7909, 7949, 7956, 8049, 8168, 8200, 8229, 8383,
        8401, 8438, 8519, 8560, 8608, 8612, 8719, 8721, 8722, 8858, 8928, 9049, 9093, 9126, 9147, 9235,
        9252, 9253, 9305, 9328, 9377, 9429, 9456, 9485, 9491, 9517, 9564, 9628, 9669, 9794, 9804, 9813,
        9824, 9840, 9848, 9866, 9931, 10007, 10041, 10049, 10056, 10152, 10237, 10244, 10255, 10375, 10469, 10471,
        10550, 10728, 10740, 10765, 10831, 10863, 11031, 11158, 11239, 11298, 11343, 11392, 11393, 11404, 11409, 11443,
        11447, 11470, 11502, 11507, 11512, 11574, 11611, 11613, 11637, 11756, 11761, 11769, 11832, 11852, 11893, 11934,
        12029, 12091, 12154, 12222, 12230, 12231, 12283, 12288, 12297, 12615, 12639, 12683, 12711, 12785, 12787, 12860,
        12980, 13093, 13095, 13129, 13132, 13231, 13268, 13299, 13325, 13452, 13493, 13514, 13534, 13605, 13794, 13803,
        13860, 13885, 13918, 13935, 13980, 14019, 14068, 14196, 14222, 14233, 14262, 14272, 14296, 14381, 14414, 14462,
        14472, 14508, 14528, 14618, 14632, 14640, 14724, 14761, 14831, 14863, 14880, 14933, 15004, 15094, 15120, 15185,
        15386, 15792, 15897, 16024, 16162, 16693, 16706, 16721, 16812, 16827, 16832, 16850, 17130, 17270, 17287, 17309,
        17394, 17483, 17607, 17691, 17763, 17919, 18063, 18219, 18320, 18323, 18343, 18345, 18413, 18668, 18684, 18835,
        19057, 19066, 19090, 19173, 19349, 19389, 19458, 19488, 19510, 19586, 19633, 19637, 19689, 19751, 19939, 20067,
        20182, 20183, 20241, 20281, 20432, 20520, 20628, 20693, 20700, 20768, 20954, 20995, 21120, 21195, 21236, 21797,
        21932, 22733, 22783, 22912, 23141, 23750, 23908, 23927, 23983, 24050, 24058, 24064, 24153, 24220, 24328, 24468,
        24575, 24612, 24772, 24856, 24893, 24970, 24982, 25169, 25326, 25462, 25570, 26304, 26308, 26432, 26578, 26766,
        26820, 27029, 27229, 27253, 27316, 27519, 27814, 27833, 28201, 28242, 28244, 28251, 28431, 28437, 28591, 28594,
        28710, 28865, 28899, 28930, 29038, 29053, 29303, 29476, 29537, 29616, 29620, 29645, 29725, 29850, 30078, 30166,
        30267, 30418, 30459, 30564, 31055, 31058, 31226, 31265, 31475, 31549, 31927, 32339, 32899, 32905, 33248, 33422,
        33660, 34269, 34437, 34466, 34490, 34987, 35043, 35422, 35478, 35629, 35910, 36030, 36199, 36405, 36408, 36800,
        36951, 37321, 37372, 38050, 38117, 38377, 38565, 38799, 38806, 39437, 39702, 39752, 39779, 39916, 40015, 40394,
        40649, 40800, 40869, 40902, 40937, 41238, 41592, 41955, 41997, 42413, 42908, 42924, 42956, 43726, 43841, 44924,
        45408, 45662, 45958, 46072, 46320, 46462, 46475, 46623, 46985, 47103, 47152, 47383, 47505, 48765, 49095, 49275,
        50229, 50808, 51002, 51197, 53773, 53852, 54456, 54865, 56057, 56441, 56496, 58295, 59262, 59565, 60027, 61102,
        61363, 61370, 61519, 62374, 64074, 64649, 65089, 65677, 67364, 67995, 68140, 68516, 68715, 68865, 70250, 70505,
        70549, 70714, 70778, 70913, 71875, 71913, 72018, 72335, 72767, 73335, 73814, 73858, 73937, 73956, 74034, 74317,
        74903, 75028, 75115, 75712, 75928, 76136, 77001, 77051, 77605, 78917, 78971, 79015, 79084, 79534, 79539, 79614,
        79836, 80184, 80219, 80262, 80356, 80382, 80425, 80682, 81443, 82831, 84306, 84634, 84664, 84748, 84753, 85339,
        85439, 86096, 86487, 86659, 86744, 86829, 86919, 86925, 87200, 87243, 87298, 87381, 87464, 87622, 87654, 87772,
        88094, 88202, 88229, 88304, 88356, 88463, 89136, 89282, 89449, 89667, 89901, 90186, 90218, 90425, 90439, 90448,
        90570, 90662, 90871, 90925, 90992, 91079, 91088, 91569, 91812, 91844, 92060, 92245, 92255, 92344, 92519, 92576,
        93100, 93186, 93424, 93779, 94511, 95027, 97172, 98656, 98670, 98729, 99095, 99527, 100106, 100232, 100712, 101092,
        101230, 101291, 105459, 105908, 106628, 106728, 106829, 107473, 107506, 107574, 108364, 108433, 108930, 109217, 109313, 110439,
        112416, 112457, 112487, 112527, 112548, 112707, 112756, 112910, 113114, 113117, 113149, 113261, 113276, 113336, 113347, 113358,
        113444, 113517, 113586, 113612, 114310, 114944, 115470, 115486, 115688, 115727, 115732, 115739, 115750, 115804, 115860, 115865,
        115878, 115966, 116031, 116168, 116179, 116206, 116328, 116453, 116481, 116488, 116616, 116667, 116683, 116699, 116749, 116844,
        116861, 116874, 117086, 117106, 117145, 117172, 117173, 118907, 119292, 119550, 120057, 120153, 120397, 121647, 122038, 123076,
        124769, 125997, 126788, 128599, 129649, 129667, 131358, 132073
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use RandAugment (citation-only or passing mention)'
FROM randaugment_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING randaugment_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING randaugment_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- data-augmentation: 1531 links, 17 exclusions.
CREATE TEMP TABLE data_augmentation_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'data-augmentation'
  AND p.id IN (
        177, 184, 349, 411, 413, 520, 742, 843, 848, 1014, 1181, 1231, 1283, 1298, 1301, 1445,
        1485, 1679, 1793, 1794, 1828, 1850, 1880, 2016, 2027, 2050, 2051, 2065, 2191, 2244, 2305, 2354,
        2445, 2486, 2526, 2618, 2697, 2772, 2783, 2800, 2854, 2878, 2957, 2994, 3023, 3030, 3066, 3098,
        3143, 3151, 3172, 3179, 3181, 3198, 3266, 3286, 3328, 3375, 3379, 3396, 3401, 3435, 3447, 3472,
        3522, 3585, 3738, 3749, 3786, 3828, 3882, 3931, 3949, 3974, 4000, 4015, 4112, 4153, 4156, 4237,
        4238, 4243, 4256, 4332, 4362, 4363, 4469, 4470, 4504, 4506, 4528, 4584, 4589, 4599, 4619, 4627,
        4672, 4683, 4726, 4730, 4763, 4809, 4888, 4907, 4912, 4930, 4972, 5022, 5044, 5085, 5121, 5127,
        5186, 5213, 5241, 5283, 5285, 5298, 5341, 5400, 5444, 5488, 5522, 5523, 5597, 5613, 5658, 5664,
        5667, 5680, 5750, 5760, 5798, 5831, 5860, 5898, 5912, 5919, 5933, 5989, 5991, 6014, 6023, 6051,
        6144, 6145, 6147, 6166, 6220, 6247, 6281, 6293, 6352, 6374, 6428, 6468, 6472, 6520, 6572, 6583,
        6669, 6688, 6704, 6759, 6761, 6769, 6791, 6800, 6878, 6883, 6915, 6936, 6983, 6996, 7019, 7119,
        7138, 7154, 7168, 7202, 7215, 7238, 7288, 7343, 7411, 7413, 7452, 7542, 7561, 7569, 7589, 7669,
        7809, 7926, 7938, 8056, 8072, 8086, 8107, 8127, 8164, 8289, 8307, 8318, 8353, 8431, 8533, 8572,
        8596, 8607, 8624, 8628, 8677, 8719, 8747, 8749, 8792, 8887, 8919, 9011, 9054, 9089, 9110, 9128,
        9248, 9265, 9267, 9272, 9274, 9284, 9293, 9312, 9347, 9391, 9625, 9650, 9729, 9758, 9766, 9831,
        9840, 9880, 9911, 9930, 9958, 9960, 9971, 9972, 9975, 10029, 10043, 10044, 10056, 10073, 10114, 10120,
        10179, 10236, 10256, 10350, 10471, 10506, 10555, 10576, 10611, 10621, 10653, 10831, 10909, 10935, 10944, 10979,
        10991, 10998, 11032, 11097, 11174, 11178, 11186, 11254, 11305, 11337, 11381, 11409, 11427, 11433, 11476, 11532,
        11546, 11560, 11608, 11637, 11766, 11920, 11980, 11998, 12029, 12031, 12038, 12043, 12084, 12145, 12175, 12284,
        12308, 12338, 12452, 12456, 12517, 12673, 12835, 12875, 12917, 12975, 13004, 13038, 13109, 13126, 13129, 13142,
        13145, 13215, 13268, 13273, 13317, 13392, 13420, 13458, 13498, 13560, 13613, 13706, 13747, 13769, 13779, 13803,
        13818, 13928, 14178, 14179, 14257, 14288, 14362, 14369, 14381, 14421, 14449, 14510, 14523, 14532, 14583, 14618,
        14676, 14707, 14725, 14761, 14787, 14831, 14866, 14912, 14933, 15053, 15157, 15160, 15189, 15284, 15370, 15473,
        15511, 15547, 15564, 15566, 15722, 15867, 15935, 15961, 15987, 16058, 16082, 16162, 16289, 16339, 16349, 16480,
        16482, 16483, 16655, 16668, 16675, 16694, 16725, 16767, 16768, 16773, 16847, 16929, 16955, 16965, 17085, 17278,
        17309, 17351, 17357, 17420, 17631, 17734, 17751, 17762, 17870, 17898, 17925, 17986, 18110, 18233, 18308, 18384,
        18406, 18510, 18527, 18614, 18644, 18688, 18881, 18884, 19129, 19132, 19150, 19349, 19399, 19466, 19483, 19488,
        19495, 19689, 19812, 20032, 20200, 20241, 20251, 20331, 20466, 20497, 20516, 20534, 20608, 20661, 20739, 20805,
        20822, 20823, 20838, 20869, 20993, 20995, 21016, 21335, 21625, 21626, 21716, 21717, 21791, 21821, 21996, 22189,
        22249, 22336, 22339, 22359, 22407, 22478, 22626, 22639, 22655, 22667, 22723, 22746, 22901, 22912, 22932, 22974,
        23007, 23010, 23166, 23244, 23307, 23352, 23526, 23553, 23592, 23657, 23685, 23743, 23767, 23793, 23973, 24027,
        24064, 24103, 24299, 24518, 24637, 24765, 24843, 24856, 24870, 24911, 24921, 24940, 25024, 25083, 25262, 25309,
        25312, 25444, 25445, 25553, 25603, 25617, 25784, 25830, 25926, 26022, 26060, 26080, 26327, 26429, 26509, 26670,
        26720, 26951, 26967, 26993, 27045, 27046, 27106, 27118, 27139, 27270, 27276, 27372, 27401, 27493, 27507, 27519,
        27541, 27546, 27583, 27667, 27673, 27697, 27710, 27813, 27814, 27835, 27852, 27965, 28012, 28184, 28293, 28320,
        28368, 28412, 28424, 28484, 28510, 28554, 28604, 28641, 28758, 28834, 28844, 28956, 28961, 28982, 29000, 29055,
        29094, 29116, 29140, 29148, 29312, 29357, 29389, 29579, 29655, 29657, 29698, 29760, 29806, 30000, 30179, 30188,
        30228, 30236, 30267, 30279, 30291, 30338, 30375, 30394, 30459, 30803, 30804, 30838, 30845, 30949, 31024, 31160,
        31236, 31267, 31308, 31324, 31326, 31354, 31506, 31585, 31621, 31889, 31965, 32204, 32239, 32308, 32791, 32842,
        32877, 32939, 32957, 33002, 33200, 33248, 33290, 33433, 33435, 33591, 33625, 33646, 33660, 33760, 33780, 34068,
        34110, 34162, 34243, 34263, 34288, 34303, 34406, 34410, 34416, 34428, 34437, 34530, 34954, 34987, 35005, 35039,
        35046, 35148, 35422, 35654, 35789, 35828, 35945, 36018, 36030, 36250, 36360, 36482, 36623, 36666, 36676, 36684,
        36719, 36778, 36800, 36898, 36925, 37086, 37105, 37112, 37155, 37183, 37260, 37288, 37312, 37321, 37342, 37580,
        37592, 37657, 37660, 37714, 37747, 37852, 37988, 38198, 38235, 38531, 38567, 38626, 38651, 38725, 38899, 38936,
        38968, 39003, 39098, 39164, 39168, 39186, 39218, 39243, 39279, 39375, 39442, 39727, 39763, 39822, 40137, 40143,
        40200, 40209, 40363, 40439, 40561, 40573, 40649, 40666, 40718, 40727, 40751, 40752, 40895, 40902, 40917, 40984,
        41036, 41044, 41058, 41125, 41289, 41446, 41660, 41733, 41767, 41802, 41840, 41871, 42046, 42080, 42177, 42353,
        42373, 42428, 42486, 42705, 42759, 42916, 43411, 43431, 43443, 43642, 43755, 43778, 43794, 43933, 44058, 44195,
        44299, 44307, 44378, 44386, 44401, 44745, 44947, 44962, 44968, 45115, 45319, 45479, 45581, 45958, 46267, 46275,
        46403, 46465, 46566, 46569, 47181, 47237, 47340, 47383, 47444, 47522, 47590, 47611, 47696, 47750, 47826, 47850,
        48164, 48209, 48218, 48227, 48230, 48370, 48401, 48436, 48663, 48828, 48948, 49115, 49649, 49664, 49802, 50208,
        50257, 50403, 50440, 50625, 50764, 50808, 50891, 50910, 51004, 51015, 51041, 51135, 51372, 51465, 51495, 51559,
        51583, 51624, 51849, 52086, 52281, 52373, 53241, 53293, 53402, 53403, 53479, 53762, 53863, 54271, 54475, 54926,
        54931, 55448, 55601, 55818, 56494, 56578, 58064, 58118, 58138, 58275, 58352, 58784, 58799, 58808, 58813, 58873,
        59303, 59427, 59502, 59588, 59703, 59779, 59869, 60090, 60125, 60473, 60565, 60923, 61057, 61273, 61363, 61405,
        61580, 61791, 62092, 62158, 62187, 62282, 62450, 62683, 62895, 63010, 63083, 63104, 63639, 63723, 63780, 63997,
        64030, 64049, 64150, 64178, 64230, 64256, 64357, 64493, 64558, 64661, 64796, 64904, 64929, 65074, 65179, 65327,
        65528, 65701, 65812, 65847, 66131, 66218, 66352, 66970, 67019, 67285, 67721, 67759, 67995, 68080, 68104, 68177,
        68193, 68443, 68521, 68628, 68648, 68762, 68808, 68815, 68988, 69247, 69325, 69388, 69585, 69606, 69616, 69759,
        69763, 69862, 70013, 70021, 70108, 70161, 70177, 70447, 70448, 70525, 70543, 70651, 70770, 70913, 71053, 71188,
        71342, 71557, 71657, 71723, 72212, 72224, 72267, 72297, 72457, 72477, 72515, 72725, 72749, 72818, 72874, 72900,
        72986, 73009, 73044, 73163, 73265, 73268, 73274, 73464, 73510, 73534, 73585, 73601, 73644, 73726, 73782, 73897,
        73898, 73974, 74222, 74562, 74677, 74831, 74895, 75134, 75663, 75863, 75880, 75928, 76111, 76203, 76209, 76288,
        76296, 76314, 76341, 76482, 76507, 76558, 76561, 76692, 76754, 76786, 76953, 76995, 77059, 77193, 77214, 77536,
        77557, 77588, 77658, 77659, 77922, 78059, 78128, 78131, 78354, 78449, 78503, 78624, 78785, 78791, 78954, 78968,
        78982, 79086, 79209, 79230, 79342, 79351, 79373, 79390, 79404, 79421, 79641, 79670, 79700, 79790, 79791, 79878,
        79959, 79992, 80040, 80063, 80068, 80108, 80220, 80270, 80356, 80419, 80423, 80438, 80525, 80712, 80724, 80761,
        80821, 80862, 80913, 80948, 80988, 81096, 81180, 81208, 81225, 81243, 81280, 81374, 81589, 81694, 81753, 81772,
        81869, 81991, 82077, 82357, 82997, 83531, 83650, 83664, 84238, 84283, 84394, 84551, 84623, 84758, 85098, 85379,
        85631, 85707, 85805, 85820, 85873, 85949, 85958, 85984, 85993, 85996, 86039, 86096, 86111, 86141, 86194, 86272,
        86288, 86410, 86550, 86588, 86659, 86665, 86852, 86917, 87066, 87131, 87190, 87219, 87243, 87386, 87416, 87464,
        87772, 87824, 87871, 87918, 87991, 88120, 88124, 88164, 88301, 88333, 88417, 88511, 88632, 88695, 88823, 88868,
        88960, 88979, 89046, 89049, 89052, 89132, 89144, 89175, 89220, 89282, 89415, 89503, 89550, 89730, 89918, 89999,
        90031, 90121, 90198, 90229, 90290, 90333, 90392, 90439, 90459, 90659, 90760, 90980, 91008, 91219, 91334, 91400,
        91707, 91749, 91844, 91939, 92267, 92353, 92661, 92973, 93100, 93192, 93275, 93285, 93353, 93433, 93494, 93779,
        93975, 94067, 94110, 94141, 94212, 94316, 94937, 95095, 95141, 95722, 95878, 96114, 96184, 96212, 96267, 96342,
        96633, 96671, 96809, 97008, 97163, 97343, 97525, 97530, 97546, 98211, 98362, 98576, 98729, 99005, 99088, 99095,
        99123, 99135, 99328, 99444, 99485, 99892, 100043, 100073, 100209, 100404, 100442, 100654, 100972, 101031, 101398, 101409,
        101683, 101877, 101969, 102065, 102409, 102504, 102606, 102698, 102750, 102793, 102995, 103132, 103387, 103403, 103724, 103731,
        103804, 103893, 103935, 104082, 104084, 104100, 104119, 104162, 104164, 104177, 104236, 104614, 104630, 104754, 104757, 104916,
        104918, 104923, 105002, 105006, 105054, 105085, 105184, 105209, 105369, 105391, 105430, 105509, 105599, 105612, 105619, 105620,
        105723, 105726, 105791, 105831, 105939, 106176, 106356, 106389, 106445, 106540, 106660, 106819, 106827, 107069, 107124, 107254,
        107292, 107340, 107473, 107515, 107548, 107614, 107827, 107875, 108057, 108134, 108172, 108322, 108364, 108400, 108423, 108495,
        108510, 108525, 108839, 109154, 109212, 109213, 109683, 109980, 110035, 110064, 110075, 110106, 110251, 110370, 110457, 110560,
        110650, 110693, 110830, 110902, 110920, 110937, 111094, 111219, 111228, 111329, 111380, 111459, 111517, 111611, 111612, 111618,
        111627, 111706, 111709, 111734, 111816, 111924, 111945, 111999, 112017, 112140, 112416, 112556, 112624, 112666, 112694, 112707,
        112788, 112808, 113083, 113316, 113347, 113409, 113551, 113567, 113586, 113681, 113684, 113996, 114276, 114315, 114352, 114365,
        114416, 114424, 114461, 114484, 114486, 114487, 114492, 114846, 114859, 114889, 114901, 114926, 114968, 115007, 115052, 115105,
        115136, 115279, 115286, 115312, 115337, 115378, 115389, 115390, 115391, 115413, 115486, 115490, 115642, 115682, 115860, 115865,
        115946, 115958, 116168, 116218, 116271, 116275, 116317, 116405, 116418, 116420, 116584, 116657, 116666, 116699, 116749, 116758,
        116849, 116942, 117003, 117086, 117116, 117154, 117158, 117270, 117342, 117411, 117520, 117570, 117739, 117761, 117771, 118032,
        118048, 118571, 118861, 119010, 119063, 119068, 119186, 119192, 119460, 119469, 119738, 119765, 119778, 119847, 119883, 119905,
        119913, 119953, 119964, 120046, 120197, 120365, 120427, 120591, 120597, 120817, 120858, 121118, 121285, 121318, 121430, 121553,
        121723, 121869, 122727, 123217, 123355, 124118, 124225, 124393, 124394, 124495, 125208, 125672, 125856, 126360, 126362, 126380,
        126404, 126717, 127372, 127444, 127624, 127767, 127851, 128098, 128159, 128192, 128222, 128607, 128689, 129194, 129264, 129474,
        129493, 129546, 130204, 130425, 130459, 130624, 130730, 130984, 131232, 131358, 131952
  );

DELETE FROM paper_method_exclusions x
USING data_augmentation_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM data_augmentation_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM data_augmentation_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE data_augmentation_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'data-augmentation'
  AND p.id IN (
        7110, 33672, 34297, 35319, 45109, 52062, 83988, 85190, 88763, 91463, 91813, 107663, 112777, 117801, 120695, 125567,
        127065
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use data augmentation (citation-only or passing mention)'
FROM data_augmentation_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING data_augmentation_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING data_augmentation_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- cross-attention: 1451 links, 9 exclusions.
CREATE TEMP TABLE cross_attention_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'cross-attention'
  AND p.id IN (
        1660, 2418, 3086, 4210, 4272, 4489, 4729, 4754, 5020, 5173, 5291, 5352, 5454, 5519, 6153, 6419,
        6464, 6642, 6903, 6921, 7389, 7448, 7577, 7668, 7780, 7976, 8001, 8151, 8269, 8381, 8734, 8774,
        8925, 8932, 8975, 9075, 9485, 9548, 9697, 9727, 9759, 9847, 9922, 9946, 9963, 10010, 10013, 10072,
        10151, 10359, 10502, 10682, 10697, 10739, 10818, 11267, 11299, 11328, 11374, 11537, 11544, 11876, 11896, 11915,
        12088, 12191, 12198, 12325, 12432, 12567, 12613, 12649, 12685, 12722, 12847, 12889, 13320, 13325, 13336, 13430,
        13479, 13489, 13559, 13578, 13664, 13666, 13759, 13829, 13836, 13909, 13929, 13962, 13984, 14019, 14079, 14142,
        14202, 14480, 14538, 14573, 14669, 14683, 14732, 14747, 14919, 15134, 15148, 15153, 15177, 15336, 15672, 15694,
        15696, 15709, 15873, 16268, 16274, 16320, 16334, 16498, 16621, 16684, 16922, 16946, 17190, 17406, 17448, 17607,
        17725, 17757, 17765, 17877, 17903, 18006, 18180, 18402, 18467, 18606, 18670, 18705, 18779, 18902, 19060, 19127,
        19161, 19200, 19234, 19384, 19391, 19402, 19547, 19606, 19696, 19861, 19928, 19929, 20031, 20083, 20088, 20113,
        20181, 20264, 20274, 20443, 20504, 20740, 20805, 20939, 20978, 21102, 21115, 21150, 21207, 21216, 21445, 21675,
        21743, 21911, 22219, 22400, 22846, 22932, 23042, 23321, 23546, 23925, 23938, 24036, 24105, 24125, 24205, 24258,
        24305, 24357, 24430, 24590, 24627, 24673, 24719, 24748, 24755, 24768, 24775, 24786, 24816, 24857, 24870, 24872,
        24928, 24968, 24981, 25005, 25018, 25060, 25075, 25251, 25357, 25394, 25398, 25443, 25492, 25548, 25640, 25782,
        25925, 26304, 26347, 26412, 26448, 26773, 26826, 26878, 27021, 27042, 27327, 27363, 27434, 27543, 27548, 27727,
        27818, 27909, 27979, 28076, 28110, 28185, 28207, 28239, 28241, 28291, 28325, 28546, 28563, 28570, 28625, 28644,
        28650, 28669, 28682, 28724, 28738, 28981, 29023, 29035, 29096, 29134, 29190, 29197, 29198, 29302, 29315, 29477,
        29549, 29767, 29790, 29848, 29888, 29901, 30030, 30036, 30068, 30232, 30333, 30336, 30487, 30565, 30621, 30629,
        30630, 30646, 30653, 30716, 30925, 31150, 31169, 31226, 31274, 31483, 31607, 31767, 31783, 31845, 31892, 31896,
        31901, 31966, 32234, 32248, 32285, 32294, 32315, 32475, 32514, 32691, 32847, 32950, 32952, 33020, 33214, 33305,
        33337, 33350, 33378, 33402, 33517, 33564, 33683, 33975, 34035, 34045, 34184, 34213, 34377, 34598, 34606, 34679,
        34799, 34809, 34833, 34838, 34960, 35078, 35178, 35429, 35512, 35523, 35623, 35869, 35974, 36092, 36135, 36224,
        36312, 36335, 36356, 36373, 36382, 36444, 36486, 36499, 36578, 36604, 36619, 36638, 36670, 36690, 36833, 36869,
        37006, 37077, 37310, 37316, 37359, 37382, 37455, 37953, 38110, 38338, 38438, 38527, 38981, 39048, 39094, 39109,
        39151, 39173, 39334, 39498, 39539, 39706, 39821, 39853, 39862, 39868, 39879, 39950, 39998, 40023, 40054, 40314,
        40339, 40343, 40367, 40526, 40623, 40624, 40648, 40675, 40701, 40710, 40747, 40824, 40857, 40873, 40892, 40898,
        40920, 40923, 41061, 41098, 41110, 41150, 41154, 41263, 41308, 41328, 41524, 41539, 41640, 41649, 41707, 41709,
        41714, 41755, 41805, 42120, 42201, 42257, 42296, 42382, 42423, 42426, 42430, 42531, 42604, 42701, 42707, 42721,
        42753, 42964, 43102, 43147, 43152, 43652, 43653, 43766, 43903, 43983, 44030, 44035, 44081, 44087, 44217, 44612,
        44625, 44740, 44857, 44927, 44992, 45112, 45136, 45159, 45340, 45343, 45680, 45689, 45736, 45771, 45779, 45787,
        45821, 46017, 46080, 46174, 46190, 46294, 46353, 46455, 46462, 46567, 46607, 46629, 46679, 46698, 46739, 46791,
        46801, 46855, 46953, 46982, 47104, 47116, 47132, 47268, 47356, 47400, 47443, 47449, 47483, 47782, 47783, 47920,
        47934, 48327, 48328, 48372, 48489, 48551, 48694, 48890, 48953, 49017, 49099, 49471, 49487, 49700, 49822, 49912,
        49963, 50082, 50145, 50253, 50279, 50380, 50407, 50428, 50876, 50985, 51015, 51137, 51153, 51303, 51306, 51379,
        51484, 51573, 51606, 51704, 51948, 52122, 52156, 52322, 52596, 52723, 52758, 52879, 52909, 52984, 52985, 53148,
        53195, 53399, 53451, 53784, 53829, 54065, 54313, 54315, 54520, 54686, 54702, 54870, 54939, 54955, 55013, 55082,
        55108, 55110, 55195, 55415, 55561, 55565, 55642, 55673, 55710, 56196, 56523, 56578, 56656, 56796, 56871, 56892,
        56924, 56962, 56979, 56987, 57176, 57198, 57231, 57253, 57333, 57414, 57525, 57556, 57864, 57911, 57954, 58015,
        58062, 58159, 58176, 58253, 58402, 58467, 58500, 58535, 58592, 58613, 58717, 58726, 58789, 58826, 58844, 58970,
        59168, 59228, 59257, 59413, 59419, 59430, 59643, 59647, 59669, 59733, 59775, 59822, 59915, 59916, 60143, 60168,
        60222, 60295, 60351, 60400, 60555, 61020, 61042, 61101, 61134, 61166, 61199, 61205, 61357, 61531, 61571, 61590,
        61798, 61920, 62092, 62223, 62326, 62358, 62379, 62421, 62453, 62586, 62709, 62884, 62890, 63057, 63219, 63365,
        63441, 63466, 63500, 63618, 63636, 63738, 63785, 63809, 63955, 64048, 64149, 64156, 64216, 64297, 64438, 64451,
        64494, 64633, 64721, 64739, 64866, 64989, 65020, 65023, 65124, 65409, 65519, 65791, 65870, 66252, 66336, 66413,
        66559, 66716, 66885, 66940, 67017, 67043, 67193, 67216, 67227, 67293, 67313, 67315, 67480, 67544, 67637, 67656,
        67756, 67793, 67824, 67936, 68080, 68125, 68166, 68179, 68367, 68431, 68460, 68495, 68579, 68655, 68815, 68851,
        68936, 69051, 69089, 69128, 69167, 69243, 69292, 69428, 69431, 69438, 69448, 69567, 69610, 69699, 69830, 69901,
        69929, 70469, 70511, 70514, 70605, 70618, 70659, 70809, 70839, 70871, 70948, 71076, 71146, 71166, 71193, 71433,
        71491, 71740, 71786, 71949, 71960, 72055, 72191, 72280, 72523, 72589, 72789, 72943, 73264, 73296, 73395, 73424,
        73475, 73595, 73602, 73781, 73814, 73922, 74010, 74012, 74016, 74021, 74101, 74162, 74194, 74199, 74395, 74749,
        74762, 74970, 74998, 75308, 75375, 75444, 75445, 75554, 75610, 75825, 76088, 76152, 76220, 76715, 76735, 76850,
        76893, 77048, 77230, 77283, 77321, 77405, 77451, 77569, 77830, 78062, 78067, 78554, 78923, 78939, 78956, 78991,
        79009, 79329, 79388, 79553, 79664, 79714, 79747, 80089, 80380, 81753, 83152, 83187, 83289, 83399, 83618, 83687,
        83699, 83769, 83918, 84117, 84118, 84129, 84172, 84223, 84226, 84290, 84293, 84383, 84407, 84464, 84514, 84558,
        84573, 84693, 84703, 84775, 84792, 84807, 84808, 84817, 84880, 84882, 84892, 84898, 84913, 84916, 84964, 84977,
        85010, 85011, 85032, 85062, 85098, 85156, 85175, 85204, 85271, 85342, 85363, 85384, 85527, 85538, 85570, 85603,
        85994, 86047, 86170, 86178, 86187, 86536, 86539, 86631, 86659, 86719, 86803, 86824, 86880, 87158, 87426, 87476,
        87531, 87549, 87557, 87596, 87702, 87758, 87780, 87820, 87853, 87892, 87902, 87956, 88027, 88147, 88153, 88156,
        88183, 88254, 88348, 88361, 88396, 88398, 88399, 88453, 88487, 88518, 89065, 89439, 89768, 89805, 89849, 89935,
        90108, 90129, 90137, 90189, 90215, 90274, 90292, 90332, 90389, 90394, 90412, 90466, 90511, 90605, 90724, 90910,
        90922, 90923, 90927, 90932, 91157, 91341, 91432, 91460, 91834, 92054, 92063, 92087, 92173, 92336, 92455, 92562,
        93335, 93484, 93720, 93735, 93871, 94004, 94163, 94257, 94304, 94552, 94566, 94633, 94639, 94707, 94812, 94821,
        94986, 95212, 95236, 95339, 95356, 95856, 96083, 96115, 96345, 96629, 96676, 96790, 96971, 97508, 97519, 97529,
        97689, 97691, 98065, 98071, 98278, 98427, 98535, 98676, 98877, 98901, 98905, 98979, 99162, 99597, 99624, 99686,
        99704, 99726, 99911, 99932, 99991, 100068, 100089, 100111, 100306, 100390, 100526, 100745, 101410, 101550, 101683, 101816,
        102327, 102352, 102418, 102498, 102665, 102705, 103491, 103936, 103971, 104469, 104537, 104600, 104935, 104942, 104963, 104985,
        104986, 105008, 105032, 105129, 105152, 105175, 105253, 105257, 105258, 105283, 105306, 105341, 105347, 105364, 105374, 105407,
        105425, 105463, 105517, 105615, 105664, 105676, 105679, 105826, 105870, 106310, 106451, 106453, 106458, 106573, 106715, 106837,
        106839, 106901, 107018, 107062, 107182, 107263, 107307, 107316, 107335, 107346, 107439, 107448, 107453, 107456, 107502, 107562,
        107578, 107584, 107651, 107662, 107783, 107872, 107934, 107973, 107994, 108093, 108301, 108322, 108422, 108423, 108430, 108655,
        108726, 108817, 109324, 109354, 109405, 109580, 109872, 110077, 110094, 110931, 111071, 111159, 111219, 111268, 111355, 111409,
        111461, 111487, 111564, 111600, 111674, 111712, 111714, 111869, 111887, 111890, 111897, 111993, 112001, 112015, 112081, 112125,
        112138, 112406, 112462, 112468, 112474, 112483, 112508, 112535, 112552, 112668, 112672, 112723, 112799, 112850, 112868, 112893,
        112922, 112930, 112937, 113011, 113041, 113120, 113190, 113294, 113302, 113318, 113366, 113438, 113493, 113520, 113533, 113551,
        113726, 113781, 113842, 113878, 113930, 113982, 114049, 114175, 114286, 114327, 114344, 114390, 114475, 114491, 114870, 114899,
        114914, 114927, 114988, 115046, 115079, 115140, 115141, 115143, 115152, 115260, 115335, 115408, 115415, 115451, 115469, 115556,
        115558, 115574, 115602, 115652, 115655, 115670, 115703, 115736, 115744, 115752, 115803, 115884, 115919, 115924, 115956, 115961,
        115965, 115967, 115969, 116028, 116047, 116049, 116126, 116155, 116231, 116259, 116301, 116313, 116326, 116374, 116381, 116382,
        116518, 116565, 116586, 116604, 116683, 116696, 116725, 116883, 116887, 116915, 116925, 116997, 117016, 117028, 117029, 117077,
        117189, 117256, 117262, 117278, 117293, 117309, 117334, 117404, 117538, 117712, 117713, 117720, 117734, 117820, 117826, 117954,
        118016, 118300, 118305, 118330, 118359, 118373, 118388, 118399, 118437, 118459, 118519, 118556, 118691, 118698, 118797, 118869,
        118931, 118935, 119018, 119035, 119193, 119348, 119350, 119366, 119425, 119438, 119515, 119856, 119920, 119936, 119944, 119986,
        119987, 120071, 120120, 120123, 120178, 120197, 120225, 120333, 120377, 120447, 120471, 120680, 120734, 120799, 120842, 120989,
        121073, 121083, 121092, 121095, 121123, 121131, 121132, 121229, 121238, 121268, 121285, 121294, 121312, 121441, 121460, 121479,
        121503, 121545, 121553, 121566, 121585, 121636, 121681, 121686, 121732, 121776, 121799, 121837, 121840, 121886, 121909, 122102,
        122178, 122555, 122683, 122709, 122714, 122916, 123148, 123427, 123605, 123702, 123706, 123891, 123973, 124033, 124070, 124132,
        124203, 124253, 124284, 124363, 124375, 124421, 124490, 124663, 124773, 124904, 124931, 125063, 125180, 125341, 125486, 125634,
        125732, 125737, 125743, 125819, 125880, 125956, 126177, 126194, 126196, 126199, 126283, 126374, 126635, 126817, 126917, 127085,
        127160, 127165, 127236, 127258, 127290, 127335, 127337, 127399, 127462, 127551, 127607, 127622, 127755, 127782, 127801, 128072,
        128077, 128379, 128547, 128751, 128824, 128855, 128996, 129418, 129761, 129769, 129848, 129894, 130074, 130097, 130142, 130580,
        130605, 130861, 130975, 130997, 131075, 131093, 131096, 131168, 131193, 131213, 131989
  );

DELETE FROM paper_method_exclusions x
USING cross_attention_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM cross_attention_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM cross_attention_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
CREATE TEMP TABLE cross_attention_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'cross-attention'
  AND p.id IN (
        29237, 41072, 41931, 67423, 84381, 85536, 90692, 116982, 117683
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: does not name or use cross-attention (citation-only or passing mention)'
FROM cross_attention_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING cross_attention_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING cross_attention_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- Hero image credits (images imported with import_entity_image.py).
UPDATE methods SET image_credit = '[Squeeze-and-Excitation Networks](/paper/1709.01507)' WHERE slug = 'squeeze-and-excitation';
UPDATE methods SET image_credit = '[Multi-Scale Context Aggregation by Dilated Convolutions](/paper/1511.07122)' WHERE slug = 'dilated-convolution';
UPDATE methods SET image_credit = '[Feature Pyramid Networks for Object Detection](/paper/1612.03144)' WHERE slug = 'feature-pyramid-network';
UPDATE methods SET image_credit = '[VGG module architecture](https://commons.wikimedia.org/wiki/File:VGG_module_architecture.svg), Aston Zhang, Zachary C. Lipton, Mu Li and Alexander J. Smola (Dive into Deep Learning), CC BY-SA 4.0' WHERE slug = 'vgg';
UPDATE methods SET image_credit = '[Going Deeper with Convolutions](/paper/1409.4842)' WHERE slug = 'inception';
UPDATE methods SET image_credit = '[Densely Connected Convolutional Networks](/paper/1608.06993)' WHERE slug = 'densenet';
UPDATE methods SET image_credit = '[AutoAugment: Learning Augmentation Policies from Data](/paper/1805.09501)' WHERE slug = 'data-augmentation';
UPDATE methods SET image_credit = '[mixup: Beyond Empirical Risk Minimization](/paper/1710.09412)' WHERE slug = 'mixup';
UPDATE methods SET image_credit = '[RandAugment: Practical automated data augmentation with a reduced search space](/paper/1909.13719)' WHERE slug = 'randaugment';
UPDATE methods SET image_credit = '[High-Resolution Image Synthesis with Latent Diffusion Models](/paper/2112.10752)' WHERE slug = 'cross-attention';
