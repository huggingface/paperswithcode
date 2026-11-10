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
    'squeeze-and-excitation',
    'Squeeze-and-Excitation',
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
    image_url = EXCLUDED.image_url,
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
    image_url = EXCLUDED.image_url,
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'vgg',
    'VGG',
    'VGGNet',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'inception',
    'Inception',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'densenet',
    'DenseNet',
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
    image_url = EXCLUDED.image_url,
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'mixup',
    'Mixup',
    'mixup',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'randaugment',
    'RandAugment',
    'RandAugment',
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
    image_url = EXCLUDED.image_url,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES (
    'cross-attention',
    'Cross-Attention',
    'Cross-Attention',
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
    image_url = EXCLUDED.image_url,
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
        873, -- 1709.01507 Squeeze-and-Excitation Networks
        928, -- 1710.08092 VGGFace2: A dataset for recognising faces across pose and age
        940, -- 1710.10451 Sample-level CNN Architectures for Music Auto-tagging Using Raw Waveforms
        1026, -- 1712.07628 Improving Generalization Performance by Switching from Adam to SGD
        1139, -- 1803.02579 Concurrent Spatial and Channel Squeeze & Excitation in Fully Convolutional
        1404, -- 1807.09441 Two at Once: Enhancing Learning and Generalization Capacities via IBN-Net
        1450, -- 1808.08127 Recalibrating Fully Convolutional Networks with Spatial and Channel 'Squeez
        1574, -- 1810.12348 Gather-Excite: Exploiting Feature Context in Convolutional Neural Networks
        1761, -- 1901.06543 MOROCO: The Moldavian and Romanian Dialectal Corpus
        1980, -- 1904.04402 Towards Universal Object Detection by Domain Attention
        2045, -- 1904.11492 GCNet: Non-local Networks Meet Squeeze-Excitation Networks and Beyond
        2332, -- 1907.05006 Two-stream Spatiotemporal Feature for Video QA Task
        2645, -- 1910.03151 ECA-Net: Efficient Channel Attention for Deep Convolutional Neural Networks
        4774, -- 2012.11879 FcaNet: Frequency Channel Attention Networks
        4854, -- 2101.00590 RegNet: Self-Regulated Network for Image Classification
        5153, -- 2103.04098 WebFace260M: A Benchmark Unveiling the Power of Million-Scale Deep Face Rec
        5373, -- 2104.01721 Citrinet: Closing the Gap between Non-Autoregressive and Autoregressive End
        6555, -- 2109.02613 Class Semantics-based Attention for Action Detection
        6857, -- 2110.04410 TitaNet: Neural Model for speaker representation with 1D Depth-wise separab
        9267, -- 2205.14879 Easter2.0: Improving convolutional models for handwritten text recognition
        10370, -- 2209.10250 Query-Guided Networks for Few-shot Fine-grained Classification and Person S
        12329, -- 2301.02494 Adaptive Pattern Extraction Multi-Task Learning for Multi-Step Conversion E
        12530, -- 2301.10906 Facial Expression Recognition using Squeeze and Excitation-powered Swin Tra
        19148, -- 2308.05996 Deep Task-specific Bottom Representation Network for Multi-Task Recommendat
        21746, -- 2310.06848 DeepTriNet: A Tri-Level Attention Based DeepLabv3+ Architecture for Semanti
        23498, -- 2311.10807 SENetV2: Aggregated dense layer for channelwise and global representations
        32177, -- 2406.00409 Arabic Handwritten Text for Person Biometric Identification: A Deep Learnin
        36945, -- 2409.10545 ResEmoteNet: Bridging Accuracy and Loss Reduction in Facial Emotion Recogni
        47998, -- 2504.15159 Acquire and then Adapt: Squeezing out Text-to-Image Model for Image Restora
        49709, -- 2505.19242 Deformable Attentive Visual Enhancement for Referring Segmentation Using Vi
        58053, -- 2604.17688 Dual-stream Spatio-Temporal GCN-Transformer Network for 3D Human Pose Estim
        65788, -- 2510.23559 KongNet: A Multi-headed Deep Learning Model for Detection and Classificatio
        68629, -- 2509.06548 Signal-Based Malware Classification Using 1D CNNs
        71568, -- 2507.00511 Medical Image Segmentation Using Advanced Unet: VMSE-Unet and VM-Unet CBAM+
        75359, -- 2412.18524 HTR-JAND: Handwritten Text Recognition with Joint Attention Network and Kno
        78594, -- 2308.16258 Robust Principles: Architectural Design Principles for Adversarially Robust
        79546, -- 2211.12565 A Novel Center-based Deep Contrastive Metric Learning Method for the Detect
        79869, -- 2207.00499 MotionMixer: MLP-based 3D Human Body Pose Forecasting
        80848, -- 2103.02907 Coordinate Attention for Efficient Mobile Network Design
        81318, -- 2005.07143 ECAPA-TDNN: Emphasized Channel Attention, Propagation and Aggregation in TD
        82116, -- 1801.04503 Multivariate LSTM-FCNs for Time Series Classification
        104076, -- 2505.19369 SETransformer: A Hybrid Attention-Based Architecture for Robust Human Activ
        104654, -- external Deep6DHead: A 6D Head Pose Estimation Method Based on Deep Feature Enhancem
        104671, -- external Full-Range Head Pose Estimation Algorithm Based on an Improved 6D RepNet
        105560, -- 2506.15258 Privacy Preserving Chest X-ray Classification in Latent Space with Homomorp
        105809, -- 2507.11415 U-RWKV: Lightweight medical image segmentation with direction-adaptive RWKV
        109400, -- 2210.15781 A Compact End-to-End Model with Local and Global Context for Spoken Languag
        111776, -- external Boundary-Conscious Pruning: Hard Set-Aware Model Compression for Efficient
        114385, -- 2407.14564 APS-USCT: Ultrasound Computed Tomography on Sparse Data via AI-Physic Syner
        115260  -- external SAM Guided Task-Specific Enhanced Nuclei Segmentation in Digital Pathology
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
        2845, -- 1911.09723 Fast Sparse ConvNets
        15979, -- 2305.13686 MP-SENet: A Speech Enhancement Model with Parallel Denoising of Magnitude a
        19359, -- 2308.08926 Explicit Estimation of Magnitude and Phase Spectra in Parallel for High-Qua
        42716, -- 2501.06146 xLSTM-SENet: xLSTM for Single-Channel Speech Enhancement
        44498, -- 2502.12990 Artificial Intelligence-derived Vascular Age from Photoplethysmography: A N
        52872, -- 2509.06482 FSG-Net: Frequency-Spatial Synergistic Gated Network for High-Resolution Re
        52891, -- 2509.18091 OnePiece: Bringing Context Engineering and Reasoning to Industrial Cascade
        53065, -- 2509.23610 Efficient Audio-Visual Speech Separation with Discrete Lip Semantics and Mu
        53700, -- 2510.15527 Balanced Multi-Task Attention for Satellite Image Classification: A Systema
        53758, -- 2510.18313 OmniNWM: Omniscient Driving Navigation World Models
        54438, -- 2511.16854 MRI Super-Resolution with Deep Learning: A Comprehensive Survey
        54703, -- 2512.05402 Smart Timing for Mining: A Deep Learning Framework for Bitcoin Hardware ROI
        54791, -- 2512.09069 KD-OCT: Efficient Knowledge Distillation for Clinical-Grade Retinal OCT Cla
        55017, -- 2512.23273 YOLO-Master: MOE-Accelerated with Specialized Transformers for Enhanced Rea
        56219, -- 2602.16915 StereoAdapter-2: Globally Structure-Consistent Underwater Stereo Depth Esti
        58216, -- 2604.12525 CoD-Lite: Real-Time Diffusion-Based Generative Image Compression
        58316, -- 2604.10359 Multinex: Lightweight Low-light Image Enhancement via Multi-prior Retinex
        58968, -- 2603.23390 Harnessing Lightweight Transformer with Contextual Synergic Enhancement for
        59430, -- 2603.13941 Bidirectional Cross-Attention Fusion of High-Res RGB and Low-Res HSI for Mu
        59781, -- 2603.06210 VG3S: Visual Geometry Grounded Gaussian Splatting for Semantic Occupancy Pr
        60010, -- 2603.02181 Leveraging Model Soups to Classify Intangible Cultural Heritage Images from
        60204, -- 2603.00175 Self-Attention And Beyond the Infinite: Towards Linear Transformers with In
        60876, -- 2602.07815 Out of the box age estimation through facial imagery: A Comprehensive Bench
        62913, -- 2601.03431 WeedRepFormer: Reparameterizable Vision Transformers for Real-Time Waterhem
        62953, -- 2601.02783 EarthVL: A Progressive Earth Vision-Language Understanding and Generation F
        62989, -- 2601.02264 POSEIDON: Physics-Optimized Seismic Energy Inference and Detection Operatin
        63671, -- 2512.22156 A Robust framework for sound event localization and detection on real recor
        64063, -- 2512.05915 LDLT L-Lipschitz Network: Generalized Deep End-To-End Lipschitz Network Con
        64163, -- 2512.03751 Research on Brain Tumor Classification Method Based on Improved ResNet34 Ne
        64250, -- 2512.02005 Learning Visual Affordance from Audio
        64365, -- 2512.00422 PhysGen: Physically Grounded 3D Shape Generation for Industrial Design
        64718, -- 2511.17747 AEGIS: Preserving privacy of 3D Facial Avatars with Adversarial Perturbatio
        64895, -- 2511.14111 CascadedViT: Cascaded Chunk-FeedForward and Cascaded Group Attention Vision
        65073, -- 2511.10107 RobIA: Robust Instance-aware Continual Test-time Adaptation for Deep Stereo
        65583, -- 2510.27326 MeisenMeister: A Simple Two Stage Pipeline for Breast Cancer Classification
        65601, -- 2510.27155 AFM-Net: Advanced Fusing Hierarchical CNN Visual Priors with Global Sequenc
        65848, -- 2510.22622 DeepfakeBench-MM: A Comprehensive Benchmark for Multimodal Deepfake Detecti
        66000, -- 2510.20092 Attentive Convolution: Unifying the Expressivity of Self-Attention with Con
        66190, -- 2510.16854 ArmFormer: Lightweight Transformer Architecture for Real-Time Multi-Class W
        66705, -- 2510.08470 Looking to Learn: Token-wise Dynamic Gating for Low-Resource Vision-Languag
        66954, -- 2510.04472 SPEGNet: Synergistic Perception-Guided Network for Camouflaged Object Detec
        67753, -- 2509.22909 TY-RIST: Tactical YOLO Tricks for Real-time Infrared Small Target Detection
        67974, -- 2509.18493 MK-UNet: Multi-kernel Lightweight CNN for Medical Image Segmentation
        68008, -- 2509.17792 Degradation-Aware All-in-One Image Restoration via Latent Prior Encoding
        68286, -- 2509.13753 ST-LINK: Spatially-Aware Large Language Models for Spatio-Temporal Forecast
        68474, -- 2509.10005 TUNI: Real-time RGB-T Semantic Segmentation with Unified Multi-Modal Featur
        68521, -- 2509.08779 ADHDeepNet From Raw EEG to Diagnosis: Improving ADHD Diagnosis through Temp
        68795, -- 2509.02982 StableSleep: Source-Free Test-Time Adaptation for Sleep Staging with Lightw
        69090, -- 2508.19850 Image Quality Assessment for Machines: Paradigm, Large-scale Database, and
        69133, -- 2508.19236 MemoryVLA: Perceptual-Cognitive Memory in Vision-Language-Action Models for
        69276, -- 2508.17148 Geolocation-Aware Robust Spoken Language Identification
        69374, -- 2508.15326 Exploring Scaling Laws of CTR Model for Online Performance Improvement
        69375, -- 2508.15316 CUPE: Contextless Universal Phoneme Encoder for Language-Agnostic Speech Pr
        82861, -- 2605.01234 TT4D: A Pipeline and Dataset for Table Tennis 4D Reconstruction From Monocu
        82939, -- 2605.06628 LiVeAction: a Lightweight, Versatile, and Asymmetric Neural Codec Design fo
        84312, -- 2512.02369 SAGE: Style-Adaptive Generalization for Privacy-Constrained Semantic Segmen
        84705, -- 2603.01708 WhisperNet: A Scalable Solution for Bandwidth-Efficient Collaboration
        84980, -- 2603.19567 Efficiency Follows Global-Local Decoupling
        84988, -- 2603.19718 BALM: A Model-Agnostic Framework for Balanced Multimodal Learning under Imb
        85342, -- 2604.10485 UDAPose: Unsupervised Domain Adaptation for Low-Light Human Pose Estimation
        85355, -- 2604.11355 LEADER: Learning Reliable Local-to-Global Correspondences for LiDAR Relocal
        86386, -- 2509.23373 Graph Your Own Prompt
        87290, -- 2509.16875 Towards Interpretable and Efficient Attention: Compressing All by Contracti
        90221, -- 2504.05499 Few-shot Personalized Scanpath Prediction
        92695, -- 2605.19091 Chessformer: A Unified Architecture for Chess Modeling
        94207, -- 2511.02880 Nef-Net v2: Adapting Electrocardio Panorama in the wild
        95948, -- 2511.21203 Transformer Driven Visual Servoing for Fabric Texture Matching Using Dual-A
        96813, -- 2510.00681 Adaptive Event Stream Slicing for Open-Vocabulary Event-Based Object Detect
        99392, -- 2601.01285 S2M-Net: Spectral-Spatial Mixing with Morphology-Aware Adaptive Loss for Me
        100704, -- 2602.20351 BiRQA: Bidirectional Robust Quality Assessment for Images
        100803, -- 2601.09776 TimeSAE: Causal Sparse Decoding for Faithful Explanations of Black-Box Time
        101642, -- 2605.20839 Activation-Free Backbones for Image Recognition: Polynomial Alternatives wi
        101813, -- 2602.22810 Multi-agent imitation learning with function approximation: linear Markov g
        102381, -- 2602.04170 Partial Ring Scan: Revisiting Scan Order in Vision State Space Models
        102679, -- 2607.07608 Dual Latent Memory in Vision-Language-Action Models for Robotic Manipulatio
        104289, -- 2509.02349 AudioCodecBench: A Comprehensive Benchmark for Audio Codec Evaluation
        104729, -- 2607.23373 UltraViT: Latency-Optimized On-device Vision Encoder for Large Vision-Langu
        106787, -- 2602.13168 Realistic Face Reconstruction from Facial Embeddings via Diffusion Models
        106836, -- 2512.15221 SLCFormer: Spectral-Local Context Transformer with Physics-Grounded Flare S
        106906, -- 2512.13734 Plug-and-Play Parameter-Efficient Tuning of Embeddings for Federated Recomm
        106999, -- 2512.02447 Temporal Dynamics Enhancer for Directly Trained Spiking Object Detectors
        107293, -- 2603.19606 Beyond Quadratic: Linear-Time Change Detection with RWKV
        107648, -- 2511.13063 FGNet: Leveraging Feature-Guided Attention to Refine SAM2 for 3D EM Neuron
        107767, -- 2603.12587 MRGeo: Robust Cross-View Geo-Localization of Corrupted Images via Spatial a
        108418, -- 2512.23473 SC-Net: Robust Correspondence Learning via Spatial and Cross-Channel Contex
        111546, -- external Exploiting Bispectral Features for Single-Channel Speech Enhancement
        112028, -- 2412.17778 From KAN to GR-KAN: Advancing Speech Enhancement with KAN-Based Methodology
        112030, -- external Mamba-based Hybrid Model for Speech Enhancement
        114111, -- 2609.11156 UniH^3: Unifying Hierarchical Homogeneity and Heterogeneity for All-in-One
        117408, -- 2603.28503 Bridging the Geometry Mismatch: Frequency-Aware Anisotropic Serialization f
        117697, -- 2511.23191 GeoWorld: Providing Full-frame Geometry Features to Facilitate 3D Scene Gen
        117781, -- 2606.24479 MambaRaw: Selective State Space Modeling for Efficient 4K RAW Image Reconst
        117862, -- 2607.08771 ZipDepth: Bringing Lightweight Zero-Shot Monocular Depth Anywhere, on Any D
        117995, -- 2608.20639 MV2GF: Multi-view Pedestrian Detection with a Visual Geometric Foundation M
        118516, -- 2607.10627 Spectral Consistent Flow for One-step 3D Medical Image Translation
        118937, -- 2606.21108 SARIF: Segment Anything for Robust Image Forensics
        119064, -- 2607.19000 Learning Semantic-Robust Change Detection via Semantic-Invariant Self-Disti
        119122, -- 2608.11815 Learning with Bilevel-Minimax Optimization for Efficient and Reliable Trans
        119254, -- 2603.27531 OmniColor: A Unified Framework for Multi-modal Lineart Colorization
        119411, -- 2603.10417 Frames2Residual: Spatiotemporal Decoupling for Self-Supervised Video Denois
        122440, -- 2609.28327 LightMIS: Ultra-Lightweight Medical Image Segmentation Without a Stage-Wise
        123357, -- 2604.26353 GateMOT: Q-Gated Attention for Dense Object Tracking
        123967, -- 2610.21114 Spectral-Spatial Interpretation
        124875, -- 2605.23878 LaMo: Self-Supervised Latent Motion Priors for Physical Realism in Video Ge
        125462, -- 2512.08040 Lost in Translation, Found in Embeddings: Sign Language Translation and Ali
        127630, -- 2610.01069 Overcoming Kernel Redundancy for Scaling Logic Gate Networks
        128199, -- 2602.13444 FlowHOI: Flow-based Semantics-Grounded Generation of Hand-Object Interactio
        129271, -- 2604.02564 Why Invariance is Not Enough for Biomedical Domain Generalization and How t
        130228, -- 2609.39701 Values as Style: Disentangling Values from Semantics with One-Way Mixing fo
        130263, -- 2609.38991 Anchoring Adversarial Trajectories to Data Manifolds: A Bilevel Transfer Op
        130549  -- 2607.19378 Native Multi-Dimensional Subquadratic Operators via Input Dependent Long Co
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
        275, -- 1511.07122 Multi-Scale Context Aggregation by Dilated Convolutions
        389, -- 1606.00915 DeepLab: Semantic Image Segmentation with Deep Convolutional Nets, Atrous C
        767, -- 1706.05587 Rethinking Atrous Convolution for Semantic Image Segmentation
        937, -- 1710.10361 Deep Residual Learning for Small-Footprint Keyword Spotting
        1091, -- 1802.02611 Encoder-Decoder with Atrous Separable Convolution for Semantic Image Segmen
        1429, -- 1808.03833 Self-Supervised Model Adaptation for Multimodal Semantic Segmentation
        1473, -- 1809.00646 Detail Preserving Depth Estimation from a Single Image Using Attention Guid
        1503, -- 1809.07454 Conv-TasNet: Surpassing Ideal Time-Frequency Magnitude Masking for Speech S
        1637, -- 1811.08305 IVD-Net: Intervertebral disc localization and segmentation in MRI with a mu
        1826, -- 1902.06634 Contextual Encoder-Decoder Network for Visual Saliency Prediction
        1925, -- 1903.11816 FastFCN: Rethinking Dilated Convolution in the Backbone for Semantic Segmen
        2075, -- 1905.02244 Searching for MobileNetV3
        2122, -- 1905.09010 PEPSI++: Fast and Lightweight Network for Image Inpainting
        2565, -- 1909.08599 Feature Pyramid Encoding Network for Real-time Semantic Segmentation
        3211, -- 2003.05586 Encoder-Decoder Based Convolutional Neural Network with Multi-Scale-Aware M
        3212, -- 2003.05586 Encoder-Decoder Based Convolutional Neural Networks with Multi-Scale-Aware
        3324, -- 2004.04371 MDCNN-SID: Multi-scale Dilated Convolution Network for Singer Identificatio
        3390, -- 2004.09832 MixNet: Multi-modality Mix Network for Brain Segmentation
        3419, -- 2004.12450 Semi-Supervised Neural System for Tagging, Parsing and Lematization
        3658, -- 2006.02334 DetectoRS: Detecting Objects with Recursive Feature Pyramid and Switchable
        4255, -- 2010.01733 D3Net: Densely connected multidilated DenseNet for music source separation
        4605, -- 2011.11961 MODNet: Real-Time Trimap-Free Portrait Matting via Objective Decomposition
        4789, -- 2012.13587 Inception Convolution with Efficient Dilation Search
        5423, -- 2104.05557 SC-GlowTTS: an Efficient Zero-Shot Multi-Speaker Text-To-Speech Model
        5705, -- 2105.05409 A Large-Scale Benchmark for Food Image Segmentation
        6372, -- 2108.02927 DOLG: Single-Stage Image Retrieval with Deep Orthogonal Fusion of Local and
        6773, -- 2110.00745 End-to-End Complex-Valued Multidilated Convolutional Neural Network for Joi
        7296, -- 2111.12374 MM-Pyramid: Multimodal Pyramid Attentional Network for Audio-Visual Event L
        7431, -- 2112.03740 Dilated convolution with learnable spacings
        11575, -- 2211.13202 Lite-Mono: A Lightweight CNN and Transformer Architecture for Self-Supervis
        11890, -- 2212.04761 Leveraging Spatio-Temporal Dependency for Skeleton-Based Action Recognition
        12526, -- 2301.10846 Optimal decision making in robotic assembly and other trial-and-error tasks
        13648, -- 2303.06146 StyleGANEX: StyleGAN-Based Manipulation Beyond Cropped Aligned Faces
        15150, -- 2305.01638 Sequence Modeling with Multiresolution Convolutional Memory
        16781, -- 2306.00817 Dilated Convolution with Learnable Spacings: beyond bilinear interpolation
        17283, -- 2306.06842 AerialFormer: Multi-resolution Transformer for Aerial Image Segmentation
        17914, -- 2306.17670 Learning Delays in Spiking Neural Networks using Dilated Convolutions with
        19929, -- 2308.15777 DeFTAN-II: Efficient Multichannel Speech Enhancement with Subgroup Processi
        20304, -- 2309.05780 LUNet: Deep Learning for the Segmentation of Arterioles and Venules in High
        24545, -- 2312.05605 TCNCA: Temporal Convolution Network with Chunked Attention for Scalable Seq
        25993, -- 2401.10032 FreGrad: Lightweight and Fast Frequency-aware Diffusion Vocoder
        26577, -- 2402.00637 Fisheye Camera and Ultrasonic Sensor Fusion For Near-Field Obstacle Percept
        28583, -- 2403.05369 Frequency-Adaptive Dilated Convolution for Semantic Segmentation
        35591, -- 2408.03164 Dilated Convolution with Learnable Spacings makes visual models more aligne
        35766, -- 2408.06383 Dilated Convolution with Learnable Spacings
        36035, -- 2408.11001 MegaFusion: Extend Diffusion Models towards Higher-resolution Image Generat
        38856, -- 2410.15091 Spatial-Mamba: Effective Visual State Space Models via Structure-Aware Stat
        39000, -- 2410.17144 YOLO-TS: Real-Time Traffic Sign Detection with Enhanced Accuracy Using Opti
        41592, -- 2412.10995 RapidNet: Multi-Level Dilated Convolution Based Mobile Backbone
        43011, -- 2501.11196 Enhancing Brain Tumor Segmentation Using Channel Attention and Transfer lea
        52730, -- 2509.09114 Modality Alignment with Multi-scale Bilateral Attention for Multimodal Reco
        62913, -- 2601.03431 WeedRepFormer: Reparameterizable Vision Transformers for Real-Time Waterhem
        65195, -- 2511.10680 LAD-BNet: Lag-Aware Dual-Branch Networks for Real-Time Energy Forecasting o
        65285, -- 2511.05803 MACMD: Multi-dilated Contextual Attention and Channel Mixer Decoding for Me
        69401, -- 2508.15057 GasTwinFormer: A Hybrid Vision Transformer for Livestock Methane Emission S
        69912, -- 2508.07300 BEVANet: Bilateral Efficient Visual Attention Network for Real-Time Semanti
        70985, -- 2507.14613 Depthwise-Dilated Convolutional Adapters for Medical Object Tracking and Se
        71870, -- 2506.16073 TD3Net: A Temporal Densely Connected Multi-Dilated Convolutional Network fo
        72004, -- 2506.11860 MindGrab for BrainChop: Fast and Accurate Skull Stripping for Command Line
        75229, -- 2501.06139 SkyReconNet: A Cross-Resolution Contextual Integration Framework for Inpain
        75760, -- 2003.03653 SalsaNext: Fast, Uncertainty-aware Semantic Segmentation of LiDAR Point Clo
        78728, -- 2307.14179 Resolution-Aware Design of Atrous Rates for Semantic Segmentation Networks
        79404, -- 2301.12730 General Covariance Data Augmentation for Neural PDE Solvers
        79546, -- 2211.12565 A Novel Center-based Deep Contrastive Metric Learning Method for the Detect
        80167, -- 2203.00931 MuSE-SVS: Multi-Singer Emotional Singing Voice Synthesizer that Controls Em
        80438, -- 2103.13279 FakeMix Augmentation Improves Transparent Object Detection
        80909, -- 2101.10030 Weakly-supervised Video Anomaly Detection with Robust Temporal Feature Magn
        82017, -- 1805.04902 LMNet: Real-time Multiclass Object Detection on CPU using 3D LiDAR
        82036, -- 1804.07821 An Aggregated Multicolumn Dilated Convolution Network for Perspective-Free
        82080, -- 1802.10062 CSRNet: Dilated Convolutional Neural Networks for Understanding the Highly
        82218, -- 1706.07162 A Wavenet for Speech Denoising
        82271, -- 1702.08502 Understanding Convolution for Semantic Segmentation
        84112, -- 2509.24850 PHASE-Net: Physics-Grounded Harmonic Attention System for Efficient Remote
        92145, -- 2502.18538 Revisiting Convolution Architecture in the Realm of DNA Foundation Models
        96345, -- external Attention-Based Markerless Pose Estimation of the Assistant-Port Trocar in
        98335, -- 2403.16958 TwinLiteNet+: An Enhanced Multi-Task Segmentation Model for Autonomous Driv
        104250, -- 1609.07769 Deep Joint Rain Detection and Removal from a Single Image
        105122, -- external DPGS-Net: Dual Prior-Guided Cross-Domain Adaptive Framework for Ultrasound
        105145, -- external EfficientMedNeXt: Multi-Receptive Dilated Convolutions for Medical Image Se
        105282, -- external Hybrid Graph Mamba: Unlocking Non-Euclidean Potential for Accurate Polyp Se
        109562, -- 2608.15767 TinyCast: Probabilistic Zero-Shot Forecasting with Computed Periodicity
        114098, -- 2202.10108 ViTAEv2: Vision Transformer Advanced by Exploring Inductive Bias for Image
        114143, -- 2106.03348 ViTAE: Vision Transformer Advanced by Exploring Intrinsic Inductive Bias
        115199, -- 2406.14052 Perspective+ Unet: Enhancing Segmentation with Bi-Path Fusion and Efficient
        120335, -- 2505.12685 Mamba-Adaptor: State Space Model Adaptor for Visual Recognition
        120481, -- external Hierarchical Adaptive Filtering Network for Text Image Specular Highlight R
        120519, -- external ACL: Activating Capability of Linear Attention for Image Restoration
        121535, -- external DetectSCI: Toward Object-Guided ROI Reconstruction for High-Resolution Vide
        122038  -- 2111.09957 Rethinking Dilated Convolution for Real-time Semantic Segmentation
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
        4830, -- 2012.15840 Rethinking Semantic Segmentation from a Sequence-to-Sequence Perspective wi
        5576, -- 2104.12137 A Novel Transformer Based Semantic Segmentation Scheme for Fine-Resolution
        7637, -- 2201.00462 D-Former: A U-shaped Dilated Transformer for 3D Medical Image Segmentation
        9506, -- 2206.08236 Simple and Efficient Architectures for Semantic Segmentation
        11410, -- 2211.09707 Listen, Denoise, Action! Audio-Driven Motion Synthesis with Diffusion Model
        116811  -- 2403.06258 Poly Kernel Inception Network for Remote Sensing Detection
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
        538, -- 1612.03144 Feature Pyramid Networks for Object Detection
        1742, -- 1901.02446 Panoptic Feature Pyramid Networks
        1963, -- 1904.02701 Libra R-CNN: Towards Balanced Learning for Object Detection
        2819, -- 1911.06667 CenterMask : Real-Time Anchor-Free Instance Segmentation
        2834, -- 1911.09070 EfficientDet: Scalable and Efficient Object Detection
        2902, -- 1912.02424 Bridging the Gap Between Anchor-based and Anchor-free Detection via Adaptiv
        2918, -- 1912.05027 SpineNet: Learning Scale-Permuted Backbone for Recognition and Localization
        3303, -- 2004.02967 Evolving Normalization-Activation Layers
        3671, -- 2006.03677 Visual Transformers: Token-based Image Representation and Processing for Co
        4588, -- 2011.10043 Propagate Yourself: Exploring Pixel-Level Consistency for Unsupervised Visu
        4612, -- 2011.12450 Sparse R-CNN: End-to-End Object Detection with Learnable Proposals
        4727, -- 2012.06785 DETR for Crowd Pedestrian Detection
        5071, -- 2102.10287 Deep Structured Feature Networks for Table Detection and Tabular Data Extra
        5551, -- 2104.10442 Fourier Contour Embedding for Arbitrary-Shaped Text Detection
        5880, -- 2106.02637 Aligning Pretraining for Detection via Object-Level Contrastive Learning
        7037, -- 2110.12130 RCNet: Reverse Feature Pyramid and Cross-scale Shift Network for Object Det
        7274, -- 2111.11057 Learning to Aggregate Multi-Scale Context for Instance Segmentation in Remo
        8497, -- 2203.16527 Exploring Plain Vision Transformer Backbones for Object Detection
        8595, -- 2204.02964 Unleashing Vanilla Vision Transformer with Masked Image Modeling for Object
        9059, -- 2205.09613 Integrally Migrating Pre-trained Transformer Encoder-decoders for Visual Ob
        9391, -- 2206.03001 PP-OCRv3: More Attempts for the Improvement of Ultra Lightweight OCR System
        9628, -- 2206.14098 RevBiFPN: The Fully Reversible Bidirectional Feature Pyramid Network
        10893, -- 2210.10260 End-to-End Entity Detection with Proposer and Regressor
        10920, -- 2210.11078 Large-batch Optimization for Dense Visual Predictions
        11154, -- 2211.00218 Pixel-Wise Contrastive Distillation
        11661, -- 2211.15444 DAMO-YOLO : A Report on Real-Time Object Detection Design
        19144, -- 2308.05967 YOLOrtho - A Unified Framework for Teeth Enumeration and Dental Disease De
        19391, -- 2308.09314 Retro-FPN: Retrospective Feature Pyramid Network for Point Cloud Semantic S
        19538, -- 2308.10481 ADNet: Lane Shape Prediction via Anchor Decomposition
        20679, -- 2309.11331 Gold-YOLO: Efficient Object Detector via Gather-and-Distribute Mechanism
        20757, -- 2309.12585 BGF-YOLO: Enhanced YOLOv8 with Multiscale Attentional Feature Fusion for Br
        21445, -- 2310.03456 Multi-Resolution Audio-Visual Feature Fusion for Temporal Action Localizati
        25392, -- 2401.00926 Accurate Leukocyte Detection Based on Deformable-DETR and Multi-Level Featu
        28207, -- 2402.19422 PEM: Prototype-based Efficient MaskFormer for Image Segmentation
        30770, -- 2404.16573 Multi-Scale Representations by Varying Window Attention for Semantic Segmen
        32568, -- 2406.05755 A DeNoising FPN With Transformer R-CNN for Tiny Object Detection
        34501, -- 2407.08634 RTMW: Real-Time Multi-Person 2D and 3D Whole-body Pose Estimation
        36329, -- 2408.15857 What is YOLOv8: An In-Depth Exploration of the Internal Features of the Nex
        42740, -- 2501.06441 CPDR: Towards Highly-Efficient Salient Object Detection via Crossed Post-de
        43643, -- 2502.02257 UNIP: Rethinking Pre-trained Attention Patterns for Infrared Semantic Segme
        43809, -- 2502.04656 MHAF-YOLO: Multi-Branch Heterogeneous Auxiliary Fusion YOLO for accurate ob
        48513, -- 2505.04915 GlyphMastero: A Glyph Encoder for High-Fidelity Scene Text Editing
        58320, -- 2604.10210 A3-FPN: Asymptotic Content-Aware Pyramid Attention Network for Dense Visual
        61554, -- 2602.01055 Baseline Method of the Foundation Model Challenge for Ultrasound Image Anal
        78031, -- 2312.17163 FENet: Focusing Enhanced Network for Lane Detection
        79082, -- 2305.04743 MARS: Mask Attention Refinement with Sequential Quadtree Nodes for Car Dama
        79366, -- 2302.06414 LAPTNet-FPN: Multi-scale LiDAR-aided Projective Transform Network for Real
        79733, -- 2209.08575 SegNeXt: Rethinking Convolutional Attention Design for Semantic Segmentatio
        81493, -- 1810.05952 Comparison-Based Convolutional Neural Networks for Cervical Cell/Clumps Det
        84080, -- 2508.06878 Seeing Through the Noise: Improving Infrared Small Target Detection and Seg
        85019, -- 2603.21069 NoOVD: Novel Category Discovery and Embedding for Open-Vocabulary Object De
        105213, -- external FPN-in-FPN: A Nested Multi-Scale Aggregation Network for Polyp Segmentation
        105460, -- external Multi-scale Attention-based Multiple Instance Learning for Breast Cancer Di
        108684, -- 2605.26095 Pixel-Level Pavement Distress Assessment Using Instance Segmentation
        108744, -- 2602.00168 YOLOE-26: Integrating YOLO26 with YOLOE for Real-Time Open-Vocabulary Insta
        109472, -- 2208.02541 MVSFormer: Multi-View Stereo by Learning Robust Image Features and Temperat
        113995, -- 2511.01315 MVSMamba: Multi-View Stereo with State Space Model
        114325, -- external A Hybrid CNN-Transformer Feature Pyramid Network for Granular Abdominal Aor
        114975, -- external Gradient Guided Co-Retention Feature Pyramid Network for LDCT Image Denoisi
        116579  -- 2401.13856 LAA-Net: Localized Artifact Attention Network for Quality-Agnostic and Gene
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
        26410, -- 2401.16102 Flexible Parallel Neural Network Architecture Model for Early Prediction of
        54558, -- 2512.04025 PSA: Pyramid Sparse Attention for Efficient Video Understanding and Generat
        58006, -- 2604.19233 Adaptive Slicing-Assisted Hyper Inference for Enhanced Small Object Detecti
        58203, -- 2604.12918 Radar-Camera BEV Multi-Task Learning with Cross-Task Attention Bridge for J
        83236, -- 2605.10780 Beyond the Last Layer: Multi-Layer Representation Fusion for Visual Tokeniz
        83464, -- 2605.09640 Overcoming Catastrophic Forgetting in Visual Continual Learning with Reinfo
        85420, -- 2604.18867 Hierarchically Robust Zero-shot Vision-language Models
        85468, -- 2604.26820 Bridge: Basis-Driven Causal Inference Marries VFMs for Domain Generalizatio
        85631, -- 2605.30561 VLM3: Vision Language Models Are Native 3D Learners
        87522, -- 2605.31597 SOCO: Benchmarking Semantic Object Correspondence in Vision Foundation Mode
        88608, -- 2502.00563 Complex Wavelet Mutual Information Loss: A Multi-Scale Loss Function for Se
        95702, -- 2605.20822 TERDNet: Transformer Encoder-Recurrent Decoder Network for Scene Change Det
        98530, -- 2606.14024 ViT-Up: Faithful Feature Upsampling for Vision Transformers
        99272, -- 2605.07607 FS-I2P: A Hierarchical Focus–Sweep Registration Network with Dynamically Al
        99282, -- 2606.14251 HiST: A Hierarchical Sparse Transformer for Cross-Modal Spatial Transcripto
        102352, -- 2605.21308 Deformba: Vision State Space Model with Adaptive State Fusion
        103153, -- 2604.18145 Region-Grounded Report Generation for 3D Medical Imaging: A Fine-Grained Da
        108832, -- 2607.08449 Predicting Viticulture Potential through an Ensemble of U-Net and a Geospat
        109846, -- 2608.23943 Luce: Relightable Gaussians for 3D Asset Generation
        117727, -- 2607.06176 Revisiting Scene Graph Generation from the Perspective of Detector-Conditio
        117731, -- 2606.14307 Pano3D: Unified 3D Reconstruction and Panoptic Segmentation
        117967, -- 2607.04587 RAF: Reliability-Aware Fusion of Camera, LiDAR, and 4D RADAR for Robust 3D
        117979, -- 2606.21216 A scalar per patch from pre-trained ViTs enables fast moving navigation in
        117995, -- 2608.20639 MV2GF: Multi-view Pedestrian Detection with a Visual Geometric Foundation M
        118089, -- 2606.31172 HSDF-Lane: Height-Aligned Signed Distance Field with Semantic Lane Prior fo
        119005, -- 2607.27585 ZMIS-SAM: Segment Anything Model Enhanced With Wavelet Transform For Zoopla
        119555, -- 2606.27372 DnA: Denoising Attention for Visual Tasks
        121072, -- 2604.24119 TopoHR: Hierarchical Centerline Representation for Cyclic Topology Reasonin
        121403, -- 2605.29505 ESAM++: Efficient Online 3D Perception on the Edge
        121650, -- external Seeing Through Blur: Tackling Defocus in Spike-Based Imaging
        122440, -- 2609.28327 LightMIS: Ultra-Lightweight Medical Image Segmentation Without a Stage-Wise
        123869, -- 2610.19419 WinARDet: Compressed Window Auto-Regression for Long-Horizon Vision-Languag
        124943, -- 2609.15221 MAST: Label-Efficient, Robust, and Generalizable Sound Detection for Biodiv
        125880, -- 2610.09118 TopoCurve: Geometry-Aware Topology Reasoning via Bézier Curves in Autonomou
        126297, -- 2606.15486 ST-DiffEye: Diffusion-based Continuous Gaze Generation via Joint Scanpath-T
        127780, -- 2605.07693 Toward Better Geometric Representations for Molecule Generative Models
        128436  -- 2609.38864 AdaOcc: Adaptive 3D Occupancy Prediction for Embodied Tasks
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
        108, -- 1409.1556 Very Deep Convolutional Networks for Large-Scale Image Recognition
        121, -- 1411.4038 Fully Convolutional Networks for Semantic Segmentation
        181, -- 1504.08083 Fast R-CNN
        195, -- 1506.01497 Faster R-CNN: Towards Real-Time Object Detection with Region Proposal Netwo
        289, -- 1512.03385 Deep Residual Learning for Image Recognition
        442, -- 1608.04337 Design of Efficient Convolutional Layers using Single Intra-channel Convolu
        446, -- 1608.06037 Lets keep it simple, Using simple architectures to outperform deeper and mo
        527, -- 1611.10012 Speed/accuracy trade-offs for modern convolutional object detectors
        734, -- 1705.10041 Towards Metamerism via Foveated Style Transfer
        802, -- 1707.06168 Channel Pruning for Accelerating Very Deep Neural Networks
        837, -- 1708.02901 Transitive Invariance for Self-supervised Visual Representation Learning
        1028, -- 1712.08268 Beyond saliency: understanding convolutional neural networks from saliency
        1050, -- 1801.03924 The Unreasonable Effectiveness of Deep Features as a Perceptual Metric
        1082, -- 1802.00930 Mixed Precision Training of Convolutional Neural Networks using Integer Ope
        1094, -- 1802.03494 AMC: AutoML for Model Compression and Acceleration on Mobile Devices
        1140, -- 1803.02758 RTSeg: Real-time Semantic Segmentation Comparative Study
        1409, -- 1807.10589 Diverse feature visualizations reveal invariances in early layers of deep n
        1428, -- 1808.03570 Densely Connected Convolutional Networks for Speech Recognition
        1908, -- 1903.09760 Photorealistic Style Transfer via Wavelet Transforms
        2064, -- 1905.01278 Unsupervised Pre-Training of Image Features on Non-Curated Data
        2116, -- 1905.08318 DeepCABAC: Context-adaptive binary arithmetic coding for deep neural networ
        2440, -- 1908.07919 Deep High-Resolution Representation Learning for Visual Recognition
        2488, -- 1909.00948 HarDNet: A Low Memory Traffic Network
        2667, -- 1910.05653 Model Fusion via Optimal Transport
        3167, -- 2003.00883 Adversarial Perturbations Prevail in the Y-Channel of the YCbCr Color Space
        3210, -- 2003.05431 Building and Interpreting Deep Similarity Models
        3236, -- 2003.10120 Efficient Crowd Counting via Structured Knowledge Transfer
        3270, -- 2003.13503 Diagnosis of Breast Cancer Based on Modern Mammography using Hybrid Transfe
        3297, -- 2004.02229 FALCON: Honest-Majority Maliciously Secure Framework for Private Deep Learn
        3426, -- 2004.13075 A scalable and efficient convolutional neural network accelerator using HLS
        3728, -- 2006.09092 Learning Rates as a Function of Batch Size: A Random Matrix Theory Approach
        4318, -- 2010.04936 An Empirical Study on Detecting COVID-19 in Chest X-ray Images Using Deep L
        4480, -- 2011.00241 Methods for Pruning Deep Neural Networks
        4639, -- 2011.14871 ViDi: Descriptive Visual Data Clustering as Radiologist Assistant in COVID-
        4865, -- 2101.02115 Adversarial Robustness by Design through Analog Computing and Synthetic Gra
        4875, -- 2101.03697 RepVGG: Making VGG-style ConvNets Great Again
        4928, -- 2101.09192 Gravity Optimizer: a Kinematic Approach on Optimization in Deep Learning
        5021, -- 2102.05950 Adversarially robust deepfake media detection using fused convolutional neu
        5289, -- 2103.14749 Pervasive Label Errors in Test Sets Destabilize Machine Learning Benchmarks
        5888, -- 2106.02914 Feature Flow Regularization: Improving Structured Sparsity in Deep Neural N
        6256, -- 2107.07467 Only Train Once: A One-Shot Neural Network Training And Pruning Framework
        6886, -- 2110.05929 One Timestep is All You Need: Training Spiking Neural Networks with Ultra L
        6970, -- 2110.08232 Fire Together Wire Together: A Dynamic Pruning Approach with Self-Supervise
        7211, -- 2111.07180 Explainable Semantic Space by Grounding Language to Vision with Cross-Modal
        7321, -- 2111.13924 A Practical Contrastive Learning Framework for Single-Image Super-Resolutio
        8025, -- 2202.10177 Cell nuclei classification in histopathological images using hybrid OLConvN
        8970, -- 2205.03635 Ultrafast Image Categorization in Biology and Neural Models
        9081, -- 2205.10268 B-cos Networks: Alignment is All We Need for Interpretability
        9122, -- 2205.11108 Paddy Doctor: A Visual Image Dataset for Automated Paddy Disease Classifica
        9335, -- 2206.01186 ORC: Network Group-based Knowledge Distillation using Online Role Change
        9375, -- 2206.02454 What do CNNs Learn in the First Layer and Why? A Linear Systems Perspective
        9723, -- 2207.03881 The Power of Transfer Learning in Agricultural Applications: AgriNet
        10075, -- 2208.08503 Learning with Local Gradients at the Edge
        11365, -- 2211.08339 Pruning Very Deep Neural Network Channels for Efficient Inference
        11638, -- 2211.14651 SliceMatch: Geometry-guided Aggregation for Cross-View Pose Estimation
        11708, -- 2211.16667 Dynamic Sparse Training via Balancing the Exploration-Exploitation Trade-of
        11935, -- 2212.06145 AP: Selective Activation for De-sparsifying Pruned Neural Networks
        13364, -- 2302.14325 BEVPlace: Learning LiDAR-based Place Recognition using Bird's Eye View Imag
        13560, -- 2303.04278 CUDA: Convolution-based Unlearnable Datasets
        13692, -- 2303.06862 OTOV2: Automatic, Generic, User-Friendly
        15675, -- 2305.10438 IMAGINATOR: Pre-Trained Image+Text Joint Embeddings using Word-Level Ground
        15714, -- 2305.10964 Learning Activation Functions for Sparse Neural Networks
        17147, -- 2306.05021 Mixed-TD: Efficient Neural Network Accelerator with Layer-Specific Tensor D
        17174, -- 2306.05358 Trustworthy Sensor Fusion against Inaudible Command Attacks in Advanced Dri
        17751, -- 2306.14169 A Web-based Mpox Skin Lesion Detection System Using State-of-the-art Deep L
        18205, -- 2307.06496 Microbial Genetic Algorithm-based Black-box Attack against Interpretable De
        19529, -- 2308.10438 Efficient Joint Optimization of Layer-Adaptive Weight Pruning in Deep Neura
        19715, -- 2308.12439 BaDExpert: Extracting Backdoor Functionality for Accurate Backdoor Input De
        23244, -- 2311.07475 Masked Face Dataset Generation and Masked Face Recognition
        28516, -- 2403.04523 T-TAME: Trainable Attention Mechanism for Explaining Convolutional Networks
        28742, -- 2403.07807 StyleGaussian: Instant 3D Style Transfer with Gaussian Splatting
        28962, -- 2403.10912 Automatic location detection based on deep learning
        30001, -- 2404.04245 Evaluating Adversarial Robustness: A Comparison Of FGSM, Carlini-Wagner Att
        30845, -- 2404.17768 Changing the Training Data Distribution to Reduce Simplicity Bias Improves
        33919, -- 2407.00818 Image Classification for Snow Detection to Improve Pedestrian Safety
        34606, -- 2407.09919 Arbitrary-Scale Video Super-Resolution with Structural and Textural Priors
        35397, -- 2408.00002 Transfer Learning for Wildlife Classification: Evaluating YOLOv8 against De
        36165, -- 2408.12837 Underwater SONAR Image Classification and Analysis using LIME-based Explain
        36235, -- 2408.14267 1-Bit FQT: Pushing the Limit of Fully Quantized Training to 1-bit
        36555, -- 2409.02241 What Makes a Face Look like a Hat: Decoupling Low-level and High-level Visu
        37017, -- 2409.11644 Few-Shot Learning Approach on Tuberculosis Classification Based on Chest X-
        38078, -- 2410.05871 A second-order-like optimizer with adaptive gradient scaling for deep learn
        38117, -- 2410.06373 Unveiling the Backbone-Optimizer Coupling Bias in Visual Representation Lea
        39164, -- 2410.19151 CapsuleNet: A Deep Learning Model To Classify GI Diseases Using EfficientNe
        39231, -- 2410.20352 An approach to hummed-tune and song sequences matching
        40220, -- 2411.13548 HF-Diff: High-Frequency Perceptual Loss and Distribution Matching for One-S
        44980, -- 2502.17941 Optimal Brain Apoptosis
        47990, -- 2504.15051 VeLU: Variance-enhanced Learning Unit for Deep Neural Networks
        50241, -- 2505.24558 Optimal Weighted Convolution for Classification and Denosing
        59414, -- 2603.13931 True 4-Bit Quantized Convolutional Neural Network Training on CPU: Achievin
        61650, -- 2507.22832 Pulling Back the Curtain on Deep Networks
        63476, -- 2512.18453 NOVA: Discovering Well-Conditioned Winograd Transforms through Numerical Op
        64015, -- 2512.07010 Always Keep Your Promises: DynamicLRP, A Model-Agnostic Solution To Layer-W
        65243, -- 2511.06769 RRTS Dataset: A Benchmark Colonoscopy Dataset from Resource-Limited Setting
        65744, -- 2510.24231 Benchmarking Microsaccade Recognition with Event Cameras: A Novel Dataset a
        69066, -- 2508.20230 Coresets from Trajectories: Selecting Data via Correlation of Loss Differen
        71627, -- 2506.23482 MTADiffusion: Mask Text Alignment Diffusion Model for Object Inpainting
        72768, -- 2506.12041 Meta Pruning via Graph Metanetworks : A Meta Learning Framework for Network
        75458, -- 2412.11702 Flex-PE: Flexible and SIMD Multi-Precision Processing Element for AI Worklo
        75661, -- 2412.00143 Is Oracle Pruning the True Oracle?
        76001, -- 2410.15602 P-YOLOv8: Efficient and Accurate Real-Time Detection of Distracted Driving
        76811, -- 2407.03486 Celeb-FBI: A Benchmark Dataset on Human Full Body Images and Age, Gender, H
        77224, -- 2405.14311 Deep Learning Fusion For Effective Malware Detection: Leveraging Visual Fea
        78329, -- 2310.16273 Deep Learning for Plant Identification and Disease Classification from Leaf
        78901, -- 2306.06101 Prodigy: An Expeditiously Adaptive Parameter-Free Learner
        78969, -- 2305.17473 A Comprehensive Overview and Comparative Analysis on Deep Learning Models:
        79158, -- 2304.03509 Local Rose Breeds Detection System Using Transfer Learning Techniques
        80137, -- 2203.07772 Fast Autofocusing using Tiny Transformer Networks for Digital Holographic M
        80284, -- 2112.13553 Classification of Histopathology Images of Lung Cancer Using Convolutional
        80285, -- 2112.13544 FitAct: Error Resilient Deep Neural Networks via Fine-Grained Post-Trainabl
        80731, -- 2105.03588 Facial Emotion Recognition: State of the Art Performance on FER2013
        81515, -- 1912.00941 FT-ClipAct: Resilience Analysis of Deep Neural Networks and Improving their
        81589, -- 1909.11870 Classification of Histopathological Biopsy Images Using Ensemble of Deep Le
        81651, -- 1908.01477 GDRQ: Group-based Distribution Reshaping for Quantization
        82070, -- 1803.10615 SqueezeNext: Hardware-Aware Neural Network Design
        82195, -- 1708.03979 SSH: Single Stage Headless Face Detector
        82228, -- 1706.02737 Advances in Joint CTC-Attention based End-to-End Speech Recognition with a
        82390, -- 1605.06211 Fully Convolutional Networks for Semantic Segmentation
        82422, -- 1602.08124 vDNN: Virtualized Deep Neural Networks for Scalable, Memory-Efficient Neura
        82460, -- 1511.00561 SegNet: A Deep Convolutional Encoder-Decoder Architecture for Image Segment
        83326, -- 1609.09430 CNN Architectures for Large-Scale Audio Classification
        84469, -- 2601.07700 Hidden Monotonicity: Explaining Deep Neural Networks via their DC Decomposi
        85445, -- 2604.22045 H-Sets: Hessian-Guided Discovery of Set-Level Feature Interactions in Image
        87011, -- 2504.02298 SPACE: SPike-Aware Consistency Enhancement for Test-Time Adaptation in Spik
        88334, -- 2508.17817 TemCoCo: Temporally Consistent Multi-modal Video Fusion with Visual-Semanti
        89146, -- 2505.05143 Sparse Training from Random Initialization: Aligning Lottery Ticket Masks u
        89919, -- 2405.15006 A Rescaling-Invariant Lipschitz Bound Based on Path-Metrics for Modern ReLU
        91310, -- 2501.10202 Provably Safeguarding a Classifier from OOD and Adversarial Samples
        91855, -- 2307.05772 Random-Set Neural Networks
        92150, -- 2202.03482 Navigating Neural Space: Revisiting Concept Activation Vectors to Overcome
        96433, -- external Neuromorphic Event Camera-Based Object Recognition and Grasping Position De
        97979, -- 2606.04767 Measuring Model Robustness via Fisher Information: Spectral Bounds, Theoret
        99295, -- 2507.00037 Model Fusion via Retrofitting
        99878, -- 2601.19717 DiffStyle3D: Consistent 3D Gaussian Stylization via Attention Optimization
        100971, -- 2505.02604 Connecting Independently Trained Modes via Layer-Wise Connectivity
        101822, -- 2511.17380 Non-Parametric Probabilistic Robustness: A Conservative Risk Estimator unde
        106499, -- 2508.08136 FantasyStyle: Controllable Stylized Distillation for 3D Gaussian Splatting
        106714, -- 2508.13812 Timestep-Compressed Attack on Spiking Neural Networks Through Timestep-Leve
        108668, -- 1812.08685 DeepFakes: a New Threat to Face Recognition? Assessment and Detection
        109191, -- 2005.03215 AutoSpeech: Neural Architecture Search for Speaker Recognition
        109217, -- 2007.03347 SpinalNet: Deep Neural Network with Gradual Input
        109232, -- 1509.06569 Tensorizing Neural Networks
        113013, -- 2112.13064 CatchBackdoor: Backdoor Detection via Critical Trojan Neural Path Fuzzing
        119137, -- 2606.31695 Intrinsically Stable Spiking Neural Networks: Overcoming the Performance Ba
        121822, -- external Making the Classification Explanation Faithful to the Confidence Score
        122821, -- 2610.05967 JLD: Perceptual Distance Through A Jacobian Lens
        124071, -- 1506.02626 Learning both Weights and Connections for Efficient Neural Networks
        126051, -- 2606.03584 Training a Predictive Coding Network on ImageNet using Equilibrium Propagat
        129583, -- external Cannistraci-Hebb Channel-wise Dynamic Sparse Training of Convolutional Neur
        130029  -- external Beyond FLOPs: Train-Full, Deploy-Partial Multi-Exit Inference via Selective
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
        11232, -- 2211.03019 Hear The Flow: Optical Flow-Based Self-Supervised Visual Sound Source Local
        51074, -- 2506.11543 FIMA-Q: Post-Training Quantization for Vision Transformers by Fisher Inform
        51117, -- 2506.12623 MS4UI: A Dataset for Multi-modal Summarization of User Interface Instructio
        51132, -- 2506.13045 A Comprehensive Survey on Continual Learning in Generative Models
        51381, -- 2506.18792 ViDAR: Video Diffusion-Aware 4D Reconstruction From Monocular Inputs
        51888, -- 2507.10999 SpaRTAN: Spatial Reinforcement Token-based Aggregation Network for Visual R
        51892, -- 2507.11137 Hashed Watermark as a Filter: Defeating Forging and Overwriting Attacks in
        51977, -- 2507.14102 UGPL: Uncertainty-Guided Progressive Learning for Evidence-Based Classifica
        52118, -- 2507.23257 Efficient Machine Unlearning via Influence Approximation
        52120, -- 2507.23277 iLRM: An Iterative Large 3D Reconstruction Model
        52127, -- 2507.23436 Beyond Linear Bottlenecks: Spline-Based Knowledge Distillation for Cultural
        52274, -- 2508.05813 Optimization-Free Style Transfer for 3D Gaussian Splats
        52368, -- 2508.10637 Processing and acquisition traces in visual encoders: What does CLIP know a
        52406, -- 2508.12811 Next Visual Granularity Generation
        52486, -- 2508.17061 REGEN: Real-Time Photorealism Enhancement in Games via a Dual-Stage Generat
        52580, -- 2508.21172 Deep Residual Echo State Networks: exploring residual orthogonal connection
        52605, -- 2509.01250 Towards More Diverse and Challenging Pre-training for Point Cloud Learning:
        52730, -- 2509.09114 Modality Alignment with Multi-scale Bilateral Attention for Multimodal Reco
        52821, -- 2509.20878 The Unanticipated Asymmetry Between Perceptual Optimization and Assessment
        52881, -- 2509.15123 RGB-Only Supervised Camera Parameter Optimization in Dynamic Scenes
        52939, -- 2509.19296 Lyra: Generative 3D Scene Reconstruction via Video Diffusion Model Self-Dis
        53096, -- 2509.22889 Convolutional Set Transformer
        53214, -- 2510.00658 Align Your Tangent: Training Better Consistency Models via Manifold-Aligned
        53449, -- 2510.07656 MONKEY: Masking ON KEY-Value Activation Adapter for Personalization
        54045, -- 2510.25976 Brain-IT: Image Reconstruction from fMRI via Brain-Interaction Transformer
        54185, -- 2511.09715 SliderEdit: Continuous Image Editing with Fine-Grained Instruction Control
        54212, -- 2511.13720 Back to Basics: Let Denoising Generative Models Denoise
        54401, -- 2511.17918 Frequency-Adaptive Sharpness Regularization for Improving 3D Gaussian Splat
        54438, -- 2511.16854 MRI Super-Resolution with Deep Learning: A Comprehensive Survey
        54491, -- 2511.22609 MG-Nav: Dual-Scale Visual Navigation via Sparse Spatial Memory
        54525, -- 2512.02942 Benchmarking Scientific Understanding and Reasoning for Video Generation us
        54590, -- 2512.04844 Mitigating Catastrophic Forgetting in Target Language Adaptation of LLMs vi
        54632, -- 2512.07833 Relational Visual Similarity
        54633, -- 2512.07806 Multi-view Pyramid Transformer: Look Coarser to See Broader
        54772, -- 2512.10794 What matters for Representation Alignment: Global Information or Spatial St
        54779, -- 2512.13689 LitePT: Lighter Yet Stronger Point Transformer
        54791, -- 2512.09069 KD-OCT: Efficient Knowledge Distillation for Clinical-Grade Retinal OCT Cla
        54850, -- 2512.15715 In Pursuit of Pixel Supervision for Visual Pre-training
        54895, -- 2512.10953 Bidirectional Normalizing Flow: From Data to Noise and Back
        55116, -- 2601.02785 DreamStyle: A Unified Framework for Video Stylization
        55594, -- 2601.22158 One-step Latent-free Image Generation with Pixel Mean Flows
        55820, -- 2601.21296 Grounding and Enhancing Informativeness and Utility in Dataset Distillation
        56255, -- 2602.20160 tttLRM: Test-Time Training for Long Context and Autoregressive 3D Reconstru
        56731, -- 2603.15619 Mixture-of-Depths Attention
        56737, -- 2603.14610 Make it SING: Analyzing Semantic Invariants in Classifiers
        56929, -- 2603.22057 SpatialBoost: Enhancing Visual Representation through Language-Guided Reaso
        56961, -- 2603.19456 In-the-Wild Camouflage Attack on Vehicle Detectors through Controllable Ima
        57137, -- 2603.22794 It Takes Two: A Duet of Periodicity and Directionality for Burst Flicker Re
        57152, -- 2603.26661 GaussianGPT: Towards Autoregressive 3D Gaussian Scene Generation
        57329, -- 2603.26657 Tunable Soft Equivariance with Guarantees
        57335, -- 2604.08364 MegaStyle: Constructing Diverse and Scalable Style Dataset via Consistent T
        57841, -- 2605.00503 End-to-End Autoregressive Image Generation with 1D Semantic Tokenizer
        57947, -- 2508.11354 FunduSegmenter: Leveraging the RETFound Foundation Model for Joint Optic Di
        58215, -- 2604.12575 StructDiff: A Structure-Preserving and Spatially Controllable Diffusion Mod
        58476, -- 2509.08289 Dual-Thresholded Heatmap-Guided Proposal Clustering and Negative Certainty
        58930, -- 2603.24117 Combi-CAM: A Novel Multi-Layer Approach for Explainable Image Geolocalizati
        59016, -- 2603.22153 Beyond Matching to Tiles: Bridging Unaligned Aerial and Satellite Views for
        59090, -- 2603.20186 Improving Image-to-Image Translation via a Rectified Flow Reformulation
        59262, -- 2603.16423 SF-Mamba: Rethinking State Space Model for Vision
        59565, -- 2603.10834 On the Reliability of Cue Conflict and Beyond
        59655, -- 2603.09149 RTFDNet: Fusion-Decoupling for Robust RGB-T Segmentation
        59739, -- 2603.18031 InfoMamba: An Attention-Free Hybrid Mamba-Transformer Model
        59782, -- 2603.06200 Adaptive Language-Aware Image Reflection Removal Network
        59791, -- 2603.06120 Dynamic Momentum Recalibration in Online Gradient Learning
        59807, -- 2603.05971 Towards High-resolution and Disentangled Reference-based Sketch Colorizatio
        59832, -- 2603.06324 The Art That Poses Back: Assessing AI Pastiches after Contemporary Artworks
        60027, -- 2603.01944 MobileMold: A Smartphone-Based Microscopy Dataset for Food Mold Detection
        60031, -- 2603.01879 Diagnosing Generalization Failures from Representational Geometry Markers
        60203, -- 2602.23349 FlashOptim: Optimizers for Memory Efficient Training
        60356, -- 2602.20417 gQIR: Generative Quanta Image Reconstruction
        60876, -- 2602.07815 Out of the box age estimation through facial imagery: A Comprehensive Bench
        61011, -- 2602.08071 ViT-5: Vision Transformers for The Mid-2020s
        61235, -- 2602.04699 Annotation Free Spacecraft Detection and Segmentation using Vision Language
        61346, -- 2602.03377 SEW: Strengthening Robustness of Black-box DNN Watermarking via Specificity
        61363, -- 2602.03123 Beyond Cropping and Rotation: Automated Evolution of Powerful Task-Specific
        61370, -- 2602.03039 HP-GAN: Harnessing pretrained networks for GAN improvement with FakeTwins a
        61840, -- 2601.21367 Hebbian Learning with Global Direction
        61924, -- 2602.00130 On the Relationship Between Representation Geometry and Generalization in D
        62097, -- 2601.17468 ReflexSplit: Single Image Reflection Separation via Layer Fusion-Separation
        62142, -- 2601.16645 Edge-Aware Image Manipulation via Diffusion Models with a Novel Structure-P
        62588, -- 2601.08025 Where to Split? A Pareto-Front Analysis of DNN Partitioning for Edge Infere
        62770, -- 2601.05127 LooseRoPE: Content-aware Attention Manipulation for Semantic Harmonization
        62884, -- 2601.03665 PhysVideoGenerator: Towards Physically Aware Video Generation via Latent Ph
        63010, -- 2601.01992 API: Empowering Generalizable Real-World Image Dehazing via Adaptive Patch
        63150, -- 2601.00090 It's Never Too Late: Noise Optimization for Collapse Recovery in Trained Di
        63315, -- 2512.21543 CEMG: Collaborative-Enhanced Multimodal Generative Recommendation
        63319, -- 2512.21513 MuS-Polar3D: A Benchmark Dataset for Computational Polarimetric 3D Imaging
        63340, -- 2512.21099 TexAvatars : Hybrid Texel-3D Representations for Stable Rigging of Photorea
        63845, -- 2512.10498 Robust Shape from Focus via Multiscale Directional Dilated Laplacian and Re
        64002, -- 2512.07142 Winning the Lottery by Preserving Network Training Dynamics with Concrete T
        64082, -- 2512.05494 Decoding with Structured Awareness: Integrating Directional, Frequency-Spat
        64266, -- 2512.01773 IGen: Scalable Data Generation for Robot Learning from Open-World Images
        64498, -- 2511.20986 Inversion-Free Style Transfer with Dual Rectified Flows
        64522, -- 2511.20620 Wanderland: Geometrically Grounded Simulation for Open-World Embodied AI
        64534, -- 2511.20422 VibraVerse: A Large-Scale Geometry-Acoustics Alignment Dataset for Physical
        64608, -- 2511.19566 ModHiFi: Identifying High Fidelity predictive components for Model Modifica
        64775, -- 2511.16588 Formal Abductive Latent Explanations for Prototype-Based Networks
        64877, -- 2511.14477 2D Gaussians Spatial Transport for Point-supervised Density Regression
        64884, -- 2511.14391 Enhancing LLM-based Autonomous Driving with Modular Traffic Light and Sign
        64912, -- 2511.13478 Semantic Document Derendering: SVG Reconstruction via Vision-Language Model
        65004, -- 2511.13767 Dynamic Temperature Scheduler for Knowledge Distillation
        65134, -- 2511.08897 Improving VisNet for Object Recognition
        65318, -- 2510.22990 USF-MAE: Ultrasound Self-Supervised Foundation Model with Masked Autoencodi
        65340, -- 2511.04394 DORAEMON: A Unified Library for Visual Object Modeling and Representation L
        65353, -- 2511.04123 Text to Sketch Generation with Multi-Styles
        65585, -- 2511.00123 Integrating ConvNeXt and Vision Transformers for Enhancing Facial Age Estim
        65638, -- 2510.26186 ConceptScope: Characterizing Dataset Bias via Disentangled Visual Concepts
        66000, -- 2510.20092 Attentive Convolution: Unifying the Expressivity of Self-Attention with Con
        66190, -- 2510.16854 ArmFormer: Lightweight Transformer Architecture for Real-Time Multi-Class W
        66460, -- 2510.12099 G4Splat: Geometry-Guided Gaussian Splatting with Generative Prior
        66606, -- 2510.09995 FlareX: A Physics-Informed Dataset for Lens Flare Removal via 2D Synthesis
        66692, -- 2510.08575 ReSplat: Learning Recurrent Gaussian Splats
        66928, -- 2510.04988 Adaptive Memory Momentum via a Model-Based Framework for Deep Learning Opti
        67067, -- 2510.03376 Visual Language Model as a Judge for Object Detection in Industrial Diagram
        67424, -- 2509.24979 Wan-Alpha: High-Quality Text-to-Video Generation with Alpha Channel
        67469, -- 2509.24526 CMT: Mid-Training for Efficient Learning of Consistency, Mean Flow, and Flo
        67608, -- 2509.23253 Training Deep Normalization-Free Spiking Neural Networks with Lateral Inhib
        67649, -- 2509.22836 Seeing Isn't Believing: Context-Aware Adversarial Patch Synthesis via Condi
        67724, -- 2509.21927 SingRef6D: Monocular Novel Object Pose Estimation with a Single RGB Referen
        68059, -- 2509.16959 Graph Coloring for Multi-Task Learning
        68310, -- 2509.13262 Post-Hoc Split-Point Self-Consistency Verification for Efficient, Unified Q
        68311, -- 2509.13255 ResidualViT for Efficient Temporally Dense Video Encoding
        68324, -- 2509.12931 4DRadar-GS: Self-Supervised Dynamic Driving Scene Reconstruction with 4D Ra
        68391, -- 2509.21339 Cross-Modal Retrieval with Cauchy-Schwarz Divergence
        68503, -- 2509.09143 Objectness Similarity: Capturing Object-Level Fidelity in 3D Scene Evaluati
        68516, -- 2509.08959 CoSwin: Convolution Enhanced Hierarchical Shifted Window Attention For Smal
        68604, -- 2509.06956 H_{2}OT: Hierarchical Hourglass Tokenizer for Efficient Video Pose Transfor
        68641, -- 2509.06331 Quantitative Currency Evaluation in Low-Resource Settings through Pattern A
        68694, -- 2509.05131 A Scalable Attention-Based Approach for Image-to-3D Texture Mapping
        68715, -- 2509.04669 VCMamba: Bridging Convolutions with Multi-Directional Mamba for Efficient V
        68731, -- 2509.04244 Integrating Pruning with Quantization for Efficient Deep Neural Networks Co
        69023, -- 2508.20987 Webly-Supervised Image Manipulation Localization via Category-Aware Auto-An
        69090, -- 2508.19850 Image Quality Assessment for Machines: Paradigm, Large-scale Database, and
        69155, -- 2508.18903 Distance-informed Neural Processes
        69211, -- 2508.17885 ISALux: Illumination and Segmentation Aware Transformer Employing Mixture o
        69235, -- 2508.17608 ChartMaster: Advancing Chart-to-Code Generation with Real-World Charts and
        69278, -- 2508.17107 SugarcaneShuffleNet: A Very Fast, Lightweight Convolutional Neural Network
        69332, -- 2508.16148 Hierarchical Vision-Language Reasoning for Multimodal Multiple-Choice Quest
        69387, -- 2508.15189 SurgWound-Bench: A Benchmark for Surgical Wound Diagnosis
        69427, -- 2508.14486 WeedSense: Multi-Task Learning for Weed Segmentation, Height Estimation, an
        69738, -- 2508.09802 MUJICA: Reforming SISR Models for PBR Material Super-Resolution via Cross-M
        69814, -- 2508.08700 Subjective and Objective Quality Assessment of Banding Artifacts on Compres
        69828, -- 2508.08605 SelfHVD: Self-Supervised Handheld Video Deblurring for Mobile Phones
        69842, -- 2508.08254 Learning an Implicit Physics Model for Image-based Fluid Simulation
        69876, -- 2508.07797 Power Battery Detection
        69899, -- 2508.07537 Enhanced Generative Structure Prior for Chinese Text Image Super-resolution
        69920, -- 2508.07229 How Does a Deep Neural Network Look at Lexical Stress?
        70017, -- 2508.05903 Robust Image Stitching with Optimal Plane
        70107, -- 2508.04539 TopKD: Top-scaled Knowledge Distillation
        70199, -- 2508.03402 SCFlow: Implicitly Learning Style and Content Disentanglement with Flow Mod
        70228, -- 2508.03091 T2UE: Generating Unlearnable Examples from Text Descriptions
        70475, -- 2507.23597 MoGA: 3D Generative Avatar Prior for Monocular Gaussian Avatar Reconstructi
        70508, -- 2507.23267 Your Spending Needs Attention: Modeling Financial Habits with Transformers
        70511, -- 2507.23143 X-NeMo: Expressive Neural Motion Reenactment via Disentangled Latent Attent
        70524, -- 2507.22802 Advancing Fetal Ultrasound Image Quality Assessment in Low-Resource Setting
        70611, -- 2507.21412 Cascading and Proxy Membership Inference Attacks
        70622, -- 2507.21311 VoluMe - Authentic 3D Video Calls from Live Gaussian Splat Prediction
        70683, -- 2507.20016 FedSWA: Improving Generalization in Federated Learning with Highly Heteroge
        70871, -- 2507.16624 A2Mamba: Attention-augmented State Space Models for Visual Recognition
        70887, -- 2507.16406 Sparse-View 3D Reconstruction: Recent Advances and Open Challenges
        71050, -- 2507.12758 HairShifter: Consistent and High-Fidelity Video Hair Transfer via Anchor-Gu
        71091, -- 2507.11893 Spatial Frequency Modulation for Semantic Segmentation
        71163, -- 2507.09984 Latent Diffusion Models with Masked AutoEncoders
        71249, -- 2507.08330 Interpretability-Aware Pruning for Efficient Medical Image Analysis
        71424, -- 2507.04017 Habitat Classification from Ground-Level Imagery Using Deep Neural Networks
        71434, -- 2507.03868 From Query to Explanation: Uni-RAG for Multi-Modal Retrieval-Augmented Lear
        71475, -- 2507.02803 HyperGaussians: High-Dimensional Gaussian Splatting for High-Fidelity Anima
        71502, -- 2507.01927 evMLP: An Efficient Event-Driven MLP Architecture for Vision
        71715, -- 2506.21046 Boosting Generative Adversarial Transferability with Self-supervised Vision
        71742, -- 2506.19676 A Survey of LLM-Driven AI Agent Communication: Protocols, Security Risks, a
        71799, -- 2506.18070 Training-free Test-time Improvement for Explainable Medical Image Classific
        71807, -- 2506.17896 EgoWorld: Translating Exocentric View to Egocentric View using Rich Exocent
        71826, -- 2506.17455 AQUA20: A Benchmark Dataset for Underwater Species Classification under Cha
        71919, -- 2506.15742 FLUX.1 Kontext: Flow Matching for In-Context Image Generation and Editing i
        71939, -- 2506.13972 Membership Inference Attacks as Privacy Tools: Reliability, Disparity and E
        71948, -- 2506.13558 X-Scene: Large-Scale Driving Scene Generation with High Fidelity and Flexib
        72143, -- 2508.00834 Team PA-VCG's Solution for Competition on Understanding Chinese College Ent
        72170, -- 2506.07055 A Layered Self-Supervised Knowledge Distillation Framework for Efficient Mu
        82847, -- 2605.05204 D-OPSD: On-Policy Self-Distillation for Continuously Tuning Step-Distilled
        82944, -- 2605.06380 Empirical Evidence for Simply Connected Decision Regions in Image Classifie
        83592, -- 2605.22809 Sensor2Sensor: Cross-Embodiment Sensor Conversion for Autonomous Driving
        83649, -- 2505.01237 CAV-MAE Sync: Improving Contrastive Audio-Visual Mask Autoencoders via Fine
        83659, -- 2512.19777 Learned Digital Codes for Over-the-Air Computation in Federated Edge Learni
        83661, -- 2605.15195 VGGT-$\Omega$
        83708, -- 2605.19354 Next-Acceleration-Scale Prediction for Autoregressive MRI Reconstruction
        83769, -- 2605.25191 Injecting Image Guidance into Text-Conditioned Diffusion Models at Inferenc
        83891, -- 2605.26368 Unified Panoramic Geometry Estimation via Multi-View Foundation Models
        84046, -- 2506.18496 Distilling Balanced Knowledge from a Biased Teacher
        84077, -- 2508.05135 HFedATM: Hierarchical Federated Domain Generalization via Optimal Transport
        84119, -- 2510.03101 AdaBet: Gradient-free Layer Selection for Efficient Training of Deep Neural
        84196, -- 2511.16957 MatPedia: A Universal Generative Foundation for High-Fidelity Material Synt
        84259, -- 2511.21136 Efficient Training for Human Video Generation with Entropy-Guided Prioritiz
        84356, -- 2512.06358 Rectifying Latent Space for Generative Single-Image Reflection Removal
        84407, -- 2512.15524 DeX-Portrait: Disentangled and Expressive Portrait Animation via Explicit a
        84457, -- 2601.02730 HOLO: Homography-Guided Pose Estimator Network for Fine-Grained Visual Loca
        84514, -- 2602.12640 ImageRAGTurbo: Towards One-step Text-to-Image Generation with Retrieval-Aug
        84569, -- 2602.20068 The Invisible Gorilla Effect in Out-of-distribution Detection
        84615, -- 2602.22096 WeatherCity: Urban Scene Reconstruction with Controllable Multi-Weather Tra
        84826, -- 2603.09408 Reviving ConvNeXt for Efficient Convolutional Diffusion Models
        84886, -- 2603.12918 VIRD: View-Invariant Representation through Dual-Axis Transformation for Cr
        84905, -- 2603.14176 BluRef: Unsupervised Image Deblurring with Dense-Matching References
        84959, -- 2603.17779 CrowdGaussian: Reconstructing High-Fidelity 3D Gaussians for Human Crowd fr
        84980, -- 2603.19567 Efficiency Follows Global-Local Decoupling
        85175, -- 2603.27542 MV-RoMa: From Pairwise Matching into Multi-View Track Reconstruction
        85192, -- 2603.28605 Unsafe2Safe: Controllable Image Anonymization for Downstream Utility
        85255, -- 2604.02946 Learning from Synthetic Data via Provenance-Based Input Gradient Guidance
        85261, -- 2604.03454 RDFace: A Benchmark Dataset for Rare Disease Facial Image Analysis under Ex
        85283, -- 2604.05039 ID-Sim: An Identity-Focused Similarity Metric
        85298, -- 2604.06631 Submodel Extraction for Efficient and Personalized Federated Learning via O
        85305, -- 2604.07795 Image-Guided Geometric Stylization of 3D Meshes
        85313, -- 2604.08048 Guiding a Diffusion Model by Swapping Its Tokens
        85321, -- 2604.08627 Evidential Transformation Network: Turning Pretrained Models into Evidentia
        85360, -- 2604.12159 VidTAG: Temporally Aligned Video to GPS Geolocalization with Denoising Sequ
        85442, -- 2604.21631 DualSplat: Robust 3D Gaussian Splatting via Pseudo-Mask Bootstrapping from
        85473, -- 2604.27596 SECOS: Semantic Capture for Rigorous Classification in Open-World Semi-Supe
        85502, -- 2605.03877 DMGD: Train-Free Dataset Distillation with Semantic-Distribution Matching i
        85505, -- 2605.04527 Velox: Learning Representations of 4D Geometry and Appearance
        85540, -- 2605.10349 Portable Active Learning for Object Detection
        85712, -- 2509.16902 FedEL: Federated Elastic Learning for Heterogeneous Devices
        85781, -- 2509.23871 Taught Well Learned Ill: Towards Distillation-conditional Backdoor Attack
        85807, -- 2507.00583 AI-Generated Video Detection via Perceptual Straightening
        85843, -- 2507.08956 Beyond Scores: Proximal Diffusion Models
        85864, -- 2510.13245 CymbaDiff: Structured Spatial Diffusion for Sketch-based 3D Semantic Urban
        85987, -- 2506.14562 AlphaDecay: Module-wise Weight Decay for Heavy-Tailed Balancing in LLMs
        86022, -- 2509.20177 Generative Model Inversion Through the Lens of the Manifold Hypothesis
        86037, -- 2510.08836 Long-Tailed Recognition via Information-Preservable Two-Stage Learning
        86096, -- 2510.07823 Enhancing Visual Prompting through Expanded Transformation Space and Overfi
        86366, -- 2506.10980 InstaInpaint: Instant 3D-Scene Inpainting with Masked Large Reconstruction
        86487, -- 2509.11711 The Quest for Universal Master Key Filters in DS-CNNs
        86818, -- 2510.13451 Toward Efficient Inference Attacks: Shadow Model Sharing via Mixture-of-Exp
        86828, -- 2509.16391 CoUn: Empowering Machine Unlearning via Contrastive Learning
        86854, -- 2510.09210 Provable Watermarking for Data Poisoning Attacks
        87122, -- 2506.07687 Rao-Blackwellised Reparameterisation Gradients
        87244, -- 2509.22813 TRUST: Test-Time Refinement using Uncertainty-Guided SSM Traverses
        87411, -- 2507.12837 Understanding the Evolution of the Neural Tangent Kernel at the Edge of Sta
        87477, -- 2510.04838 Beyond Random: Automatic Inner-loop Optimization in Dataset Distillation
        87561, -- 2507.12022 Dataset Ownership Verification for Pre-trained Masked Models
        87594, -- 2507.01390 FixTalk: Taming Identity Leakage for High-Quality Talking Head Generation i
        87612, -- 2507.05728 Asynchronous Event Error-Minimizing Noise for Safeguarding Event Dataset
        87622, -- 2508.09000 UniConvNet: Expanding Effective Receptive Field while Maintaining Asymptoti
        87662, -- 2507.15911 Local Dense Logit Relations for Enhanced Knowledge Distillation
        87690, -- 2508.07066 Membership Inference Attacks with False Discovery Rate Control
        87750, -- 2509.13922 Towards Robust Defense against Customization via Protective Perturbation Re
        87780, -- 2507.03539 CLOT: Closed Loop Optimal Transport for Unsupervised Action Segmentation
        87826, -- 2506.21037 Reinforcement Learning-Guided Data Selection via Redundancy Assessment
        87880, -- 2507.12135 Learning Pixel-adaptive Multi-layer Perceptrons for Real-time Image Enhance
        87915, -- 2506.21249 Temporal Rate Reduction Clustering for Human Motion Segmentation
        87937, -- 2509.07917 Object-level Correlation for Few-Shot Segmentation
        87967, -- 2507.22000 Staining and Locking Computer Vision Models Without Retraining
        87977, -- 2508.08556 Unlocking the Potential of Diffusion Priors in Blind Face Restoration
        87986, -- 2507.07485 Resolving Token-Space Gradient Conflicts: Token Space Manipulation for Tran
        88025, -- 2509.07662 EDFFDNet: Towards Accurate and Efficient Unsupervised Multi-Grid Image Regi
        88039, -- 2507.21844 Cross-Architecture Distillation Made Simple with Redundancy Suppression
        88148, -- 2507.06856 IAP: Invisible Adversarial Patch Attack through Perceptibility-Aware Locali
        88170, -- 2508.08237 VGGSounder: Audio-Visual Evaluations for Foundation Models
        88195, -- 2507.11985 Unsupervised Part Discovery via Descriptor-Based Masked Image Restoration w
        88230, -- 2507.17221 Dataset Distillation as Data Compression: A Rate-Utility Perspective
        88238, -- 2507.17748 Large Learning Rates Simultaneously Achieve Robustness to Spurious Correlat
        88276, -- 2507.14807 Seeing Through Deepfakes: A Human-Inspired Framework for Multi-Face Detecti
        88371, -- 2506.23516 FedWSQ: Efficient Federated Learning with Weight Standardization and Distri
        88421, -- 2509.18190 HazeFlow: Revisit Haze Physical Model as ODE and Non-Homogeneous Haze Gener
        88457, -- 2508.05689 Boosting Adversarial Transferability via Residual Perturbation Attack
        88489, -- 2506.23518 WAVE: Warp-Based View Guidance for Consistent Novel View Synthesis Using a
        88510, -- 2506.21835 ProSAM: Enhancing the Robustness of SAM-based Visual Reference Segmentation
        88929, -- 2506.15499 Pixel-level Certified Explanations via Randomized Smoothing
        88983, -- 2506.07467 Circumventing Backdoor Space via Weight Symmetry
        89734, -- 2506.16753 Off-Policy Actor-Critic for Adversarial Observation Robustness: Virtual Alt
        89929, -- 2506.09376 Revisiting Diffusion Models: From Generative Pre-training to One-Step Gener
        89945, -- 2507.04119 When Data-Free Knowledge Distillation Meets Non-Transferable Teacher: Escap
        92504, -- 2605.17131 A Systematic Survey on Deep Learning Architectures for Point Cloud Classifi
        92638, -- 2510.19675 Study of Training Dynamics for Memory-Constrained Fine-Tuning
        92646, -- 2512.15934 In Context Semi-Supervised Learning
        92656, -- 2508.11659 Toward Practical Equilibrium Propagation: Brain-inspired Recurrent Neural N
        92970, -- 2510.14231 When Flatness Does (Not) Guarantee Adversarial Robustness
        93245, -- 2507.02965 Concept-based Adversarial Attack: a Probabilistic Perspective
        93409, -- 2510.12228 Readout Representation: Redefining Neural Codes by Input Recovery
        93444, -- 2601.18678 Counterfactual Explanations on Robust Perceptual Geodesics
        93549, -- 2603.10048 Revisiting Sharpness-Aware Minimization: A More Faithful and Effective Impl
        93739, -- 2602.11339 Exploring Real-Time Super-Resolution: Benchmarking and Fine-Tuning for Stre
        93979, -- 2507.17725 On the Interaction of Compressibility and Adversarial Robustness
        94027, -- 2602.01864 Trust but Verify: Adaptive Conditioning for Reference-Based Diffusion Super
        94057, -- 2508.12132 TriQDef: Disrupting Semantic and Gradient Alignment to Prevent Adversarial
        94128, -- 2602.19498 Softmax is not Enough (for Adaptive Conformal Classification)
        94143, -- 2603.03973 Dual-Solver: A Generalized ODE Solver for Diffusion Models with Dual Predic
        94210, -- 2507.15748 CHROMA: Consistent Harmonization of Multi-View Appearance via Bilateral Gri
        94264, -- 2509.26364 Data-to-Energy Stochastic Dynamics
        94279, -- 2605.10009 Hystar: Hypernetwork-driven Style-adaptive Retrieval via Dynamic SVD Modula
        94328, -- 2512.03844 CoDA: From Text-to-Image Diffusion Models to Training-Free Dataset Distilla
        94384, -- 2601.19967 Perturbation-Induced Linearization: Constructing Unlearnable Data with Sole
        94481, -- 2601.18650 FaLW: A Forgetting-aware Loss Reweighting for Long-tailed Unlearning
        94690, -- 2603.04731 When Priors Backfire: On the Vulnerability of Unlearnable Examples to Pretr
        94903, -- 2603.03725 Why Do Unlearnable Examples Work: A Novel Perspective of Mutual Information
        94980, -- 2509.22992 T-TAMER: Provably Taming Trade-offs in ML Serving
        94982, -- 2601.18513 LipNeXt: Scaling up Lipschitz-based Certified Robustness to Billion-paramet
        95465, -- 2510.14117 ViTacGen: Robotic Pushing with Vision-To-Touch Generation
        96755, -- 2509.14565 DiffVL: Diffusion-Based Visual Localization on 2D Maps Via BEV-Conditioned
        96820, -- 2603.04050 HE-VPR: Height Estimation Enabled Aerial Visual Place Recognition against S
        98038, -- 2606.09516 SwiftVR: Real-Time One-Step Generative Video Restoration
        98539, -- 2606.19195 Moebius: 0.2B Lightweight Image Inpainting Framework with 10B-Level Perform
        99187, -- 2605.23323 Efficient Learned Image Compression without Entropy Coding
        99267, -- 2601.22787 Float8@2bits: Entropy Coding Enables Data-Free Model Compression
        99320, -- 2605.24906 Where Detectors Fail: Probing Generative Space for Generalizable AI-Generat
        99473, -- 2606.26719 FUSE: Full‑spectrum Unlearnable Examples via Spectral Equalization
        99623, -- 2605.00600 Possibilistic Predictive Uncertainty for Deep Learning
        99653, -- 2605.07724 Curated Synthetic Data Doesn’t Have to Collapse: A Theoretical Study of Gen
        99795, -- 2512.08129 Improving the Sensitivity of Backdoor Detectors via Class Subspace Orthogon
        99805, -- 2605.15520 On the Fragility of Data Attribution When Learning Is Distributed
        99818, -- 2605.09983 Frequency Matching in Spiking Neural Networks for mmWave Sensing
        99865, -- 2506.15412 Partitioning for Intrinsic Model Inversion Resistance in Collaborative Infe
        99975, -- 2508.06092 Q-CLIP: Unleashing the Power of Vision-Language Models for Video Quality As
        100341, -- 2605.25616 Courtroom Analogy: New Perspective on Uncertainty-Aware Classification
        100409, -- 2601.16880 Theory of Minimal Weight Perturbations in Deep Networks and its Application
        100546, -- 2509.25606 Effective Model Pruning : Measuring the Redundancy of Model Components
        100579, -- 2602.00827 Over-Alignment vs Over-Fitting: The Role of Feature Learning Strength in Ge
        100613, -- 2605.17827 Content-Style Identification via Differential Independence
        100698, -- 2512.05372 Breaking the Capacity Bottleneck in Model-Heterogeneous Federated Learning
        100738, -- 2605.22350 Partial Fusion of Neural Networks: Efficient Tradeoffs Between Ensembles an
        100789, -- 2506.23800 Towards the Training of Deeper Predictive Coding Neural Networks
        101153, -- 2602.20419 CREDIT: Certified Ownership Verification of Deep Neural Networks Against Mo
        101172, -- 2603.09787 What is Missing? Explaining Neurons Activated by Absent Concepts
        101310, -- 2605.02167 Manifold-Aligned Guided Integrated Gradients for Reliable Feature Attributi
        101322, -- 2602.12932 TFTF: Training-Free Targeted Flow for Conditional Sampling
        101349, -- 2602.21321 Dynamic Symmetric Point Tracking: Tackling Non-ideal Reference in Analog In
        101448, -- 2603.05002 Non-Euclidean Gradient Descent Operates at the Edge of Stability
        101507, -- 2605.00185 Fair Dataset Distillation via Cross-Group Barycenter Alignment
        101638, -- 2606.07172 Textual Supervision Enhances Geospatial Representations in Vision-Language
        101674, -- 2507.01966 Alignment between Brains and AI: Evidence for Convergent Evolution across M
        101746, -- 2602.19799 Path-conditioned training: a principled way to rescale ReLU neural networks
        101767, -- 2602.16449 GICDM: Mitigating Hubness for Reliable Distance-Based Generative Model Eval
        101792, -- 2510.06028 Generalization of Gibbs and Langevin Monte Carlo Algorithms in the Interpol
        101858, -- 2602.02157 Efficient Neural Controlled Differential Equations via Attentive Kernel Smo
        101939, -- 2605.30198 Active Continual Learning with Metaplastic Binary Bayesian Neural Networks
        102007, -- 2601.21683 Can local learning match self-supervised backpropagation?
        102227, -- 2510.23476 Human-AI Collaborative Uncertainty Quantification
        102313, -- 2510.04500 Expand Neurons, Not Parameters
        102344, -- 2606.20076 Variable-Length Tokenization via Learnable Global Merging for Diffusion Tra
        102381, -- 2602.04170 Partial Ring Scan: Revisiting Scan Order in Vision State Space Models
        102395, -- 2603.07587 3DGS-HPC: Distractor-free 3D Gaussian Splatting with Hybrid Patch-wise Clas
        102585, -- 2607.03524 Perceptual Flow Matching for Few-Step Generative Modeling
        102639, -- 2607.03819 CGGS: Consistency-Augmented Geometric Gaussian Splatting for Ego-centric 3D
        102792, -- 2604.10442 ReContraster: Making Your Posters Stand Out with Regional Contrast
        103337, -- 2601.16231 SoundBreak: A Systematic Study of Audio-Only Adversarial Attacks on Trimoda
        103341, -- 2509.23714 Collaboration of Fusion and Independence: Hypercomplex-driven Robust Multi-
        104842, -- 2506.22899 Neural Cellular Automata: From Cells to Pixels
        104868, -- 2601.16096 Neural Particle Automata: Learning Self-Organizing Particle Dynamics
        105208, -- 2507.10869 Focus on Texture: Rethinking Pre-training in Masked Autoencoders for Medica
        105273, -- 2509.24177 High-Order Progressive Trajectory Matching for Medical Image Dataset Distil
        105304, -- 2506.17787 Incorporating Rather Than Eliminating: Achieving Fairness for Skin Disease
        105400, -- 2507.19004 MedIQA: A Scalable Foundation Model for Prompt-Driven Medical Image Quality
        105560, -- 2506.15258 Privacy Preserving Chest X-ray Classification in Latent Space with Homomorp
        106443, -- 2511.13356 Enhancing All-to-X Backdoor Attacks with Optimized Target Class Mapping
        106495, -- 2511.12199 MPD-SGR: Robust Spiking Neural Networks with Membrane Potential Distributio
        106498, -- 2511.08937 Boosting Adversarial Transferability via Ensemble Non-Attention
        106515, -- 2603.13346 Post Training Quantization for Efficient Dataset Condensation
        106527, -- 2508.19243 Style4D-Bench: A Benchmark Suite for 4D Stylization
        106557, -- 2511.12066 DCA-LUT: Deep Chromatic Alignment with 5D LUT for Purple Fringing Removal
        106650, -- 2511.07210 Breaking the Stealth-Potency Trade-off in Clean-Image Backdoors with Genera
        106675, -- 2508.01335 StyleSentinel: Reliable Artistic Copyright Verification via Stylistic Finge
        106712, -- 2511.22906 See, Rank, and Filter: Important Word-Aware Clip Filtering via Scene Unders
        106722, -- 2511.10942 Heterogeneous Complementary Distillation
        106836, -- 2512.15221 SLCFormer: Spectral-Local Context Transformer with Physics-Grounded Flare S
        106873, -- 2511.11240 HealSplit: Towards Self-Healing Through Adversarial Distillation in Split F
        106922, -- 2511.08263 ImageBindDC: Compressing Multi-modal Data with ImageBind-based Condensation
        107067, -- 2602.06363 Robust Pedestrian Detection with Uncertain Modality
        107070, -- 2512.10600 Authority Backdoor: A Certifiable Backdoor Mechanism for Authoring DNNs
        107071, -- 2511.15029 Computer Vision Modeling of the Development of Geometric and Numerical Conc
        107076, -- 2508.03373 Diffusion Once and Done: Degradation-Aware LoRA for All-in-One Image Restor
        107109, -- 2601.13371 Spherical Geometry Diffusion: Generating High-quality 3D Face Geometry via
        107120, -- 2511.05968 DiA-gnostic VLVAE: Disentangled Alignment-Constrained Vision Language Varia
        107167, -- 2511.12742 Stabilizing Self-Consuming Diffusion Models with Latent Space Filtering
        107249, -- 2601.08602 WaveFormer: Frequency-Time Decoupled Vision Modeling with Wave Equation
        107318, -- 2511.09736 Data Heterogeneity and Forgotten Labels in Split Federated Learning
        107403, -- 2511.07958 Burst Image Quality Assessment: A New Benchmark and Unified Framework for M
        107407, -- 2511.09828 SMoFi: Step-wise Momentum Fusion for Split Federated Learning on Heterogene
        107485, -- 2511.07947 Class-feature Watermark: A Resilient Black-box Watermark Against Model Extr
        107556, -- 2601.00322 Depth-Synergized Mamba Meets Memory Experts for All-Day Image Reflection Se
        107564, -- 2511.06717 MRT: Learning Compact Representations with Mixed RWKV-Transformer for Extre
        107641, -- 2601.10001 DW-DGAT: Dynamically Weighted Dual Graph Attention Network for Neurodegener
        107652, -- 2511.10423 Enhanced Privacy Leakage from Noise-Perturbed Gradients via Gradient-Guided
        107665, -- 2511.08369 Text-based Aerial-Ground Person Retrieval
        107666, -- 2603.00542 Adaptive Dynamic Dehazing via Instruction-Driven and Task-Feedback Closed-L
        107705, -- 2511.08640 Predict and Resist: Long-Term Accident Anticipation Under Sensor Noise
        107878, -- 2511.13766 Credal Ensemble Distillation for Uncertainty Quantification
        108162, -- 2512.24064 Neighbor-aware Instance Refining with Noisy Labels for Cross-Modal Retrieva
        108188, -- 2511.06764 CAST-LUT: Tokenizer-Guided HSV Look-Up Tables for Purple Flare Removal
        108288, -- 2511.20218 Text-guided Controllable Diffusion for Realistic Camouflage Images Generati
        108290, -- 2512.06345 CLUENet: Cluster Attention Makes Neural Networks Have Eyes
        108422, -- 2603.12773 Empowering Semantic-Sensitive Underwater Image Enhancement with VLM
        108452, -- 2508.07710 Training-Free ANN-to-SNN Conversion for High-Performance Spiking Transforme
        108492, -- 2511.12939 Semi-Supervised High Dynamic Range Image Reconstructing via Bi-Level Uncert
        108743, -- 2608.03410 Earth Embeddings
        108992, -- 2605.14641 How to Evaluate and Refine your CAM
        110393, -- 2511.00280 Calibration Across Layers: Understanding Calibration Evolution in LLMs
        112313, -- 2509.25001 LVT: Large-Scale Scene Reconstruction via Local View Transformers
        112981, -- 2509.20091 Unleashing the Potential of the Semantic Latent Space in Diffusion Models f
        113939, -- 2609.01072 Let Confidence Change, Not the Prediction: Prediction-Preserving Repair for
        117259, -- 2509.02141 GRMM: Real-Time High-Fidelity Gaussian Morphable Head Model with Learned Re
        117437, -- 2606.22314 Diffusion Integrated Gradients: Controllable Path Generation for Flexible F
        117491, -- 2606.29333 HiReFF: High-Resolution Feedforward Human Reconstruction from Uncalibrated
        117500, -- 2607.00525 SPECSIA: Stylization Dataset for Novel-View Enhancement in Drawing-based 3D
        117576, -- 2606.26754 Capacity-Controlled Multi-View Stylization of 3D Gaussian Splatting
        117657, -- 2606.24144 Geometry-Aware Style Transfer in 3D Gaussian Splatting
        117716, -- 2511.19778 Phase-Aligned RoPE for Mixed-Resolution Diffusion Transformer
        118396, -- 2607.22924 Layering Virtual Try-On
        118533, -- 2511.21415 DiverseVAR: Balancing Diversity and Quality of Next-Scale Visual Autoregres
        118558, -- 2608.10544 Flow Straight to Reality: Perceptually Consistent Flow Matching for Efficie
        118615, -- 2607.03899 DICT: Data Injection and Contrastive Trajectory Refinement for Conditional
        118770, -- 2607.02886 SPLIT: Training-Free AI-Generated and Partially Edited Video Detection via
        118876, -- 2607.04984 Virtual Category-Guided Continual Generalized Category Discovery
        119025, -- 2606.31373 Domain Adaptive Object Detection via Dual-Stream Bilevel-Cycle Optimization
        119074, -- 2603.08374 This Looks Distinctly Like That: Grounding Interpretable Recognition in Sti
        119099, -- 2602.04677 REDistill: Robust Estimator Distillation for Balancing Robustness and Effic
        119168, -- 2604.17211 EmbodiedHead: Real-Time Listening and Speaking Avatar for Conversational Ag
        119542, -- 2608.18734 CL4D: Contrastive Language–4D Pretraining for Vision-Language Reasoning in
        119550, -- 2608.22665 Hyperbolic Hierarchical Clustering for Visual Representation Learning
        119567, -- 2607.09503 What VGGT Knows About Overlap: Probing Geometric Foundation Models for Co-V
        120002, -- 2511.07974 Towards Fine-Grained Interpretability: Counterfactual Explanations for Misc
        120394, -- 2507.06928 Adaptive Part Learning for Fine-Grained Generalized Category Discovery: A P
        121075, -- 2511.19995 CREward: A Type-Specific Creativity Reward Model
        121275, -- 2512.03336 Single-Round Scalable Analytic Federated Learning
        122101, -- 2609.22966 Transferring the Intelligence of VLMs to Robotic Control
        123021, -- 2511.12046 BackWeak: Backdooring Knowledge Distillation Simply with Weak Triggers and
        123125, -- 2610.11751 Dino Forcing Flow Models: Do not denoise what you can predict
        123382, -- 2610.14726 LightVAE: Towards Compact and Efficient Video Autoencoders
        123550, -- 2610.20111 RepForcing: Representation-Space Initialization for Autoregressive Video Di
        124176, -- 2609.38487 Multidimensional Observer Model and Perceptual Dimensions of Human Image Qu
        124769, -- 2604.06689 Generative Cross-Entropy: A Strictly Proper Loss for Data-Efficient Classif
        124890, -- 2609.22789 PixelART: Image-to-Layer Decomposition without Latents or Text-to-Image Pre
        124918, -- 2510.05416 Correlating Cross-Iteration Noise for DP-SGD using Model Curvature
        124939, -- 2610.12842 Neural networks are more modular than single neurons suggest
        124973, -- 2602.19274 DD-CAM: Minimal Sufficient Explanations for Vision Models Using Delta Debug
        125295, -- 2603.13652 Causal Attribution via Activation Patching
        125376, -- 2609.37243 Codebook-Guided Cross-Modal Knowledge Distillation for Structurally Heterog
        125743, -- 2610.13687 X-AVDD: Cross-Attentive Audio-Visual Dataset Distillation
        125914, -- 2606.29322 SP-CACW: Convergence-Aware Client Weighting for Selfish Personalized Learni
        126120, -- 2605.19458 Implicit Bias of Mirror Flow in Homogeneous Neural Networks: Sparse and Den
        126757, -- 2605.05871 Retain-Neutral Surrogates for Min-Max Unlearning
        127025, -- 2609.38136 CLeaR: A Unified Framework for Resolving the Leakage–Degradation Dilemma in
        127643, -- 2510.19773 Estimating Model-Level Membership Inference Vulnerability Without Reference
        127760, -- 2609.31996 Can Circuit Alignment Predict OOD Generalization?
        128510, -- 2610.10396 Gaussian Density Splatting Network
        128599, -- 2609.30478 The Shape of Events: Edge-Based Inductive Biases via Cross-Domain Distillat
        128843, -- 2610.16892 Barycentric Guidance: Turning Foundation Image Editors into Continuous Affe
        128937, -- 2609.14802 From Matrix Inversion to Constraints: Provably Tighter Confidence Regions f
        129158, -- 2602.16596 Sequential Membership Inference Attacks
        129175, -- 2606.17342 Learning a Maximum Entropy Model for Visual Textures using Diffusion
        129366, -- 2605.06152 Grokking or Glitching? How Low-Precision Drives Slingshot Loss Spikes
        130254, -- 2602.06208 Emergent Low-Rank Training Dynamics in MLPs with Smooth Activations
        130366, -- 2604.21909 Directional Confusions Reveal Divergent Inductive Biases Through Rate-Disto
        130442, -- 2605.13148 Understanding Generalization through Decision Pattern Shift
        130498, -- 2609.33969 Gaussian Splatting-based Volumetric Video Compression with Sparse 4D Anchor
        130499, -- 2607.18237 The Many Senses of Visual Similarity: A Text-Prompted Image Perceptual Metr
        130778, -- 2610.16762 Towards Complementary Keypoint Detection via Mixture of Detectors
        130794, -- 2606.31585 DPPE: Rethinking Camera-Based Positional Encoding for Scaling Multi-View Tr
        131141, -- 2608.10372 Invertible Logits Transformation for Accuracy-Preserving Post-Hoc Uncertain
        131598  -- 2610.39664 EditAgent: Rethinking Agentic Image Editing
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
        111, -- 1409.4842 Going Deeper with Convolutions
        121, -- 1411.4038 Fully Convolutional Networks for Semantic Segmentation
        194, -- 1506.01186 Cyclical Learning Rates for Training Neural Networks
        221, -- 1508.00092 Land Use Classification in Remote Sensing Images by Convolutional Neural Ne
        268, -- 1511.06422 All you need is a good init
        317, -- 1602.07261 Inception-v4, Inception-ResNet and the Impact of Residual Connections on Le
        478, -- 1610.02357 Xception: Deep Learning with Depthwise Separable Convolutions
        724, -- 1705.07878 TernGrad: Ternary Gradients to Reduce Communication in Distributed Deep Lea
        918, -- 1710.05941 Searching for Activation Functions
        1082, -- 1802.00930 Mixed Precision Training of Convolutional Neural Networks using Integer Ope
        1332, -- 1806.04510 Dank Learning: Generating Memes Using Deep Neural Networks
        1658, -- 1811.11553 Strike (with) a Pose: Neural Networks Are Easily Fooled by Strange Poses of
        1987, -- 1904.05059 C3AE: Exploring the Limits of Compact Model for Age Estimation
        2085, -- 1905.03696 HAWQ: Hessian AWare Quantization of Neural Networks with Mixed-Precision
        2406, -- 1908.03826 DeblurGAN-v2: Deblurring (Orders-of-Magnitude) Faster and Better
        2501, -- 1909.01955 Dense Extreme Inception Network: Towards a Robust CNN Model for Edge Detect
        2670, -- 1910.06180 KonIQ-10k: An ecologically valid database for deep learning of blind image
        2978, -- 2001.00281 ZeroQ: A Novel Zero Shot Quantization Framework
        3364, -- 2004.07317 An Evaluation of DNN Architectures for Page Segmentation of Historical News
        3659, -- 2006.02570 Exploration of Interpretability Techniques for Deep COVID-19 Classification
        3732, -- 2006.09373 The shape and simplicity biases of adversarially robust ImageNet-trained CN
        3925, -- 2007.11622 TinyTL: Reduce Activations, Not Trainable Parameters for Efficient On-Devic
        3949, -- 2007.14895 Reliable Tuberculosis Detection using Chest X-ray with Deep Learning, Segme
        4593, -- 2011.10680 HAWQV3: Dyadic Neural Network Quantization
        5021, -- 2102.05950 Adversarially robust deepfake media detection using fused convolutional neu
        5199, -- 2103.07905 Bangla Handwritten Digit Recognition and Generation
        5635, -- 2105.01147 Sketches image analysis: Web image search engine usingLSH index and DNN Inc
        5714, -- 2105.06060 House Price Prediction using Satellite Imagery
        7405, -- 2112.02250 Dense Extreme Inception Network for Edge Detection
        8025, -- 2202.10177 Cell nuclei classification in histopathological images using hybrid OLConvN
        9081, -- 2205.10268 B-cos Networks: Alignment is All We Need for Interpretability
        9723, -- 2207.03881 The Power of Transfer Learning in Agricultural Applications: AgriNet
        11511, -- 2211.11936 One Eye is All You Need: Lightweight Ensembles for Gaze Estimation with Sin
        13367, -- 2302.14354 Deep Learning for Identifying Iran's Cultural Heritage Buildings in Need of
        17751, -- 2306.14169 A Web-based Mpox Skin Lesion Detection System Using State-of-the-art Deep L
        23244, -- 2311.07475 Masked Face Dataset Generation and Masked Face Recognition
        35990, -- 2408.10414 Towards Automation of Human Stage of Decay Identification: An Artificial In
        36165, -- 2408.12837 Underwater SONAR Image Classification and Analysis using LIME-based Explain
        42878, -- 2501.08912 Empowering Agricultural Insights: RiceLeafBD - A Novel Dataset and Optimal
        43102, -- 2501.12844 GAMED-Snake: Gradient-aware Adaptive Momentum Evolution Deep Snake Model fo
        43191, -- 2501.14279 Deep Learning-Powered Classification of Thoracic Diseases in Chest X-Rays
        61786, -- 2601.21979 Investigation into using stochastic embedding representations for evaluatin
        64163, -- 2512.03751 Research on Brain Tumor Classification Method Based on Improved ResNet34 Ne
        65243, -- 2511.06769 RRTS Dataset: A Benchmark Colonoscopy Dataset from Resource-Limited Setting
        66990, -- 2510.04044 Quantization Range Estimation for Convolutional Neural Networks
        72497, -- 2506.05377 An Independent Discriminant Network Towards Identification of Counterfeit I
        74037, -- 2503.13560 MSWAL: 3D Multi-class Segmentation of Whole Abdominal Lesions Dataset
        74924, -- 2502.02096 Dual-Flow: Transferable Multi-Target, Instance-Agnostic Attacks via In-the-
        78329, -- 2310.16273 Deep Learning for Plant Identification and Disease Classification from Leaf
        78503, -- 2309.11202 Using Artificial Intelligence for the Automation of Knitting Patterns
        78969, -- 2305.17473 A Comprehensive Overview and Comparative Analysis on Deep Learning Models:
        79158, -- 2304.03509 Local Rose Breeds Detection System Using Transfer Learning Techniques
        82339, -- 1610.01644 Understanding intermediate layers using linear classifier probes
        82390, -- 1605.06211 Fully Convolutional Networks for Semantic Segmentation
        82422, -- 1602.08124 vDNN: Virtualized Deep Neural Networks for Scalable, Memory-Efficient Neura
        91855, -- 2307.05772 Random-Set Neural Networks
        96433, -- external Neuromorphic Event Camera-Based Object Recognition and Grasping Position De
        104270, -- external Automated Cervical Cancer Detection Using Feature-Fused Deep CNNs and Ensem
        105677, -- external Spatial Prior-Guided Boundary and Region-Aware 2D Lesion Segmentation in Ne
        109223, -- 2207.09531 LR-Net: A Block-based Convolutional Neural Network for Low-Resolution Image
        114871, -- external Dual-Modality Watershed Fusion Network for Thyroid Nodule Classification of
        116811, -- 2403.06258 Poly Kernel Inception Network for Remote Sensing Detection
        117451, -- 2603.16341 PKINet-v2: Towards Powerful and Efficient Poly-Kernel Remote Sensing Object
        124629  -- external SCHTs: A Semi-Structured Dynamic Sparse Training Framework for Hardware-Eff
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
        151, -- 1502.01852 Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNe
        3189, -- 2003.03256 Traffic Signs Detection and Recognition System using Deep Learning
        9538, -- 2206.09479 StudioGAN: A Taxonomy and Benchmark of GANs for Image Synthesis
        17119, -- 2306.04675 Exposing flaws of generative model evaluation metrics and their unfair trea
        25959, -- 2401.09603 Rethinking FID: Towards a Better Evaluation Metric for Image Generation
        51892, -- 2507.11137 Hashed Watermark as a Filter: Defeating Forging and Overwriting Attacks in
        53211, -- 2510.02730 Dale meets Langevin: A Multiplicative Denoising Diffusion Model
        53343, -- 2510.04999 Bridging Text and Video Generation: A Survey
        54398, -- 2511.18452 NAF: Zero-Shot Feature Upsampling via Neighborhood Attention Filtering
        54436, -- 2511.22265 FedRE: A Representation Entanglement Framework for Model-Heterogeneous Fede
        54790, -- 2512.08400 Towards Visual Re-Identification of Fish using Fine-Grained Classification
        55133, -- 2512.23950 U-Net-Like Spiking Neural Networks for Single Image Dehazing
        56731, -- 2603.15619 Mixture-of-Depths Attention
        56885, -- 2603.13395 COT-FM: Cluster-wise Optimal Transport Flow Matching
        56929, -- 2603.22057 SpatialBoost: Enhancing Visual Representation through Language-Guided Reaso
        57329, -- 2603.26657 Tunable Soft Equivariance with Guarantees
        58295, -- 2512.08217 Correction of Decoupled Weight Decay
        58580, -- 2604.02719 MOMO: Mars Orbital Model Foundation Model for Mars Orbital Applications
        59768, -- 2603.06507 Self-Supervised Flow Matching for Scalable Multi-Modal Synthesis
        60074, -- 2603.01169 TripleSumm: Adaptive Triple-Modality Fusion for Video Summarization
        60206, -- 2602.23300 A Mixture-of-Experts Model for Multimodal Emotion Recognition in Conversati
        61179, -- 2602.05375 Erase at the Core: Representation Unlearning for Machine Unlearning
        61565, -- 2602.00989 Optimal Decision-Making Based on Prediction Sets
        62620, -- 2601.07372 Conditional Memory via Scalable Lookup: A New Axis of Sparsity for Large La
        64082, -- 2512.05494 Decoding with Structured Awareness: Integrating Directional, Frequency-Spat
        65143, -- 2511.08704 Rethinking generative image pretraining: How far are we from scaling up nex
        66000, -- 2510.20092 Attentive Convolution: Unifying the Expressivity of Self-Attention with Con
        66707, -- 2510.08458 SummDiff: Generative Modeling of Video Summarization with Diffusion
        67506, -- 2509.24218 Conda: Column-Normalized Adam for Training Large Language Models Faster
        68211, -- 2509.14769 Frame Sampling Strategies Matter: A Benchmark for small vision language mod
        69014, -- 2508.21197 GCAV: A Global Concept Activation Vector Framework for Cross-Layer Consiste
        69051, -- 2508.20449 A Spatial-Frequency Aware Multi-Scale Fusion Network for Real-Time Deepfake
        69278, -- 2508.17107 SugarcaneShuffleNet: A Very Fast, Lightweight Convolutional Neural Network
        69427, -- 2508.14486 WeedSense: Multi-Task Learning for Weed Segmentation, Height Estimation, an
        69524, -- 2508.12977 Dextr: Zero-Shot Neural Architecture Search with Singular Value Decompositi
        70208, -- 2508.03300 Zero Shot Domain Adaptive Semantic Segmentation by Synthetic Data Generatio
        70228, -- 2508.03091 T2UE: Generating Unlearnable Examples from Text Descriptions
        70573, -- 2507.21989 Benchmarking Filtered Approximate Nearest Neighbor Search Algorithms on Tra
        70971, -- 2507.14797 Distilling Parallel Gradients for Fast ODE Solvers of Diffusion Models
        73902, -- 2503.18420 Panorama Generation From NFoV Image Done Right
        82944, -- 2605.06380 Empirical Evidence for Simply Connected Decision Regions in Image Classifie
        84826, -- 2603.09408 Reviving ConvNeXt for Efficient Convolutional Diffusion Models
        84980, -- 2603.19567 Efficiency Follows Global-Local Decoupling
        85473, -- 2604.27596 SECOS: Semantic Capture for Rigorous Classification in Open-World Semi-Supe
        85797, -- 2506.23075 CSBrain: A Cross-scale Spatiotemporal Brain Foundation Model for EEG Decodi
        86218, -- 2509.25278 MAESTRO : Adaptive Sparse Attention and Robust Learning for Multimodal Dyna
        86386, -- 2509.23373 Graph Your Own Prompt
        87559, -- 2507.03504 Information-Bottleneck Driven Binary Neural Network for Change Detection
        87622, -- 2508.09000 UniConvNet: Expanding Effective Receptive Field while Maintaining Asymptoti
        87624, -- 2506.22908 Attention to the Burstiness in Visual Prompt Tuning!
        92504, -- 2605.17131 A Systematic Survey on Deep Learning Architectures for Point Cloud Classifi
        93004, -- 2509.26544 Bayesian Influence Functions for Hessian-Free Data Attribution
        93600, -- 2602.22555 Autoregressive Visual Decoding from EEG Signals
        94171, -- 2510.06448 How NOT to benchmark your SITE metric: Beyond Static Leaderboards and Towar
        94282, -- 2510.22335 Moving Beyond Diffusion: Hierarchy-to-Hierarchy Autoregression for fMRI-to-
        94565, -- 2602.10847 Enhancing Multivariate Time Series Forecasting with Global Temporal Retriev
        94690, -- 2603.04731 When Priors Backfire: On the Vulnerability of Unlearnable Examples to Pretr
        98656, -- 2208.05688 Semi-supervised Vision Transformers at Scale
        99573, -- 2606.05883 Geometry-Aware Dataset Condensation for Diffusion Model Training
        99972, -- 2509.24798 Causal-Adapter: Taming Text-to-Image Diffusion for Faithful Counterfactual
        100181, -- 2603.06660 Approximate Nearest Neighbor Search for Modern AI: A Projection-Augmented G
        100684, -- 2606.09718 Evaluating the Representation Space of Diffusion Models via Self-Supervised
        100835, -- 2506.22726 XTransfer: Modality-Agnostic Few-Shot Model Transfer for Human Sensing at t
        101153, -- 2602.20419 CREDIT: Certified Ownership Verification of Deep Neural Networks Against Mo
        101288, -- 2602.08267 Inverting Data Transformations via Diffusion Sampling
        101310, -- 2605.02167 Manifold-Aligned Guided Integrated Gradients for Reliable Feature Attributi
        101663, -- 2605.13475 FedHPro: Federated Hyper-Prototype Learning via Gradient Matching
        101746, -- 2602.19799 Path-conditioned training: a principled way to rescale ReLU neural networks
        101901, -- 2509.21379 SAEmnesia: Erasing Concepts in Diffusion Models with Supervised Sparse Auto
        101979, -- 2509.24058 On the Variability of Concept Activation Vectors
        102121, -- 2606.05551 Conformal Risk-Averse Decision Making with Action Conditional Guarantee
        102381, -- 2602.04170 Partial Ring Scan: Revisiting Scan Order in Vision State Space Models
        104490, -- 2607.20379 Train the Model, Not the Reader: Decodability Supervision for Verifiable Ac
        104558, -- 2607.10495 NanoVSR: Towards Real-Time Video Super-Resolution on Edge Devices
        105274, -- 2508.16140 High-Precision Mixed Feature Fusion Network Using Hypergraph Computation fo
        107249, -- 2601.08602 WaveFormer: Frequency-Time Decoupled Vision Modeling with Wave Equation
        107339, -- 2512.18722 Generating Risky Samples with Conformity Constraints via Diffusion Models
        108020, -- 2507.04327 Communication-Efficient Heterogeneous Federated Learning with Sparse Protot
        108326, -- 2510.27486 FedAdamW: A Communication-Efficient Optimizer with Convergence and Generali
        108743, -- 2608.03410 Earth Embeddings
        109082, -- 2608.11205 AdvFD: Boosting Visual Generation via Adversarial Fr'echet Distance Loss
        112147, -- 2508.02801 Adaptive Knowledge Distillation for Device-Directed Speech Detection
        117437, -- 2606.22314 Diffusion Integrated Gradients: Controllable Path Generation for Flexible F
        117788, -- 2606.26716 Dual-Prior Guided Null-Space Learning with Mixture-of-Splines for Arbitrary
        118164, -- 2606.27729 Learning 1-Bit LiDAR-based Localization with Auxiliary Objective
        118391, -- 2511.17089 Spanning Tree Autoregressive Visual Generation
        118923, -- 2509.14001 MOCHA: Multi-modal Objects-aware Cross-arcHitecture Alignment
        119558, -- 2607.06918 LoCA: Spatially-Aware Low-Rank Convolutional Adaptation of Vision Foundatio
        122381, -- 2606.29521 Not All Objectives Are Born Equal: Priority-Constrained Descent for Hierarc
        125125, -- 2606.08672 Learning to Solve Generative ODEs Beyond the Linear Span
        125164, -- 2608.07199 Flow-Corrected Shape Optimization: Taming Manifold Drift in High-Dimensiona
        127112, -- 2605.06479 Risk-Controlled Post-Processing of Decision Policies
        128888, -- 2608.04084 SpecDrop: Parameter-Free Category-Conditioned Routing for Modular Specializ
        129138, -- 2605.06304 A multi-scale information geometry reveals the structure of mutual informat
        129803, -- 2601.22204 FedAdaVR: Adaptive Variance Reduction for Robust Federated Learning under L
        130309, -- 2605.19247 Structuring Open-Ended NAS: Semi-Automated Design Knowledge Structuring wit
        130366, -- 2604.21909 Directional Confusions Reveal Divergent Inductive Biases Through Rate-Disto
        130442  -- 2605.13148 Understanding Generalization through Decision Pattern Shift
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
        194, -- 1506.01186 Cyclical Learning Rates for Training Neural Networks
        448, -- 1608.06993 Densely Connected Convolutional Networks
        751, -- 1706.02690 Enhancing The Reliability of Out-of-distribution Image Detection in Neural
        782, -- 1706.09588 Multi-scale Multi-band DenseNets for Audio Source Separation
        788, -- 1707.01629 Dual Path Networks
        799, -- 1707.04873 Efficient Architecture Search by Network Transformation
        850, -- 1708.05344 SMASH: One-Shot Model Architecture Search through HyperNetworks
        859, -- 1708.07120 Super-Convergence: Very Fast Training of Neural Networks Using Large Learni
        1023, -- 1712.06957 MURA: Large Dataset for Abnormality Detection in Musculoskeletal Radiograph
        1026, -- 1712.07628 Improving Generalization Performance by Switching from Adam to SGD
        1054, -- 1801.05134 Understanding the Disharmony between Dropout and Batch Normalization by Var
        1139, -- 1803.02579 Concurrent Spatial and Channel Squeeze & Excitation in Fully Convolutional
        1154, -- 1803.05407 Averaging Weights Leads to Wider Optima and Better Generalization
        1273, -- 1805.04770 Born Again Neural Networks
        1301, -- 1805.10766 Improving the Resolution of CNN Feature Maps Efficiently with Multisampling
        1404, -- 1807.09441 Two at Once: Enhancing Learning and Generalization Capacities via IBN-Net
        1428, -- 1808.03570 Densely Connected Convolutional Networks for Speech Recognition
        1570, -- 1810.11875 Automatically Evolving CNN Architectures Based on Blocks
        1637, -- 1811.08305 IVD-Net: Intervertebral disc localization and segmentation in MRI with a mu
        1932, -- 1903.12519 A Provable Defense for Deep Residual Networks
        2029, -- 1904.09730 An Energy and GPU-Computation Efficient Backbone Network for Real-Time Obje
        2042, -- 1904.11486 Making Convolutional Networks Shift-Invariant Again
        2354, -- 1907.07174 Natural Adversarial Examples
        2488, -- 1909.00948 HarDNet: A Low Memory Traffic Network
        2624, -- 1910.00694 RITnet: Real-time Semantic Segmentation of the Eye for Gaze Tracking
        2733, -- 1910.12249 An Adaptive and Momental Bound Method for Stochastic Learning
        2868, -- 1911.11929 CSPNet: A New Backbone that can Enhance Learning Capability of CNN
        3084, -- 2002.03629 Accelerating Feedforward Computation via Parallel Nonlinear Equation Solvin
        3156, -- 2002.12920 Automatic Perturbation Analysis for Scalable Certified Robustness and Beyon
        3167, -- 2003.00883 Adversarial Perturbations Prevail in the Y-Channel of the YCbCr Color Space
        3659, -- 2006.02570 Exploration of Interpretability Techniques for Deep COVID-19 Classification
        3949, -- 2007.14895 Reliable Tuberculosis Detection using Chest X-ray with Deep Learning, Segme
        4255, -- 2010.01733 D3Net: Densely connected multidilated DenseNet for music source separation
        4480, -- 2011.00241 Methods for Pruning Deep Neural Networks
        4599, -- 2011.11186 Cancer image classification based on DenseNet model
        4899, -- 2101.05442 Automated Model Design and Benchmarking of 3D Deep Learning Models for COVI
        5164, -- 2103.05285 3D-QCNet - A Pipeline for Automated Artifact Detection in Diffusion MRI im
        6153, -- 2106.15828 Semantic Segmentation of Periocular Near-Infra-Red Eye Images Under Alcohol
        6773, -- 2110.00745 End-to-End Complex-Valued Multidilated Convolutional Neural Network for Joi
        8025, -- 2202.10177 Cell nuclei classification in histopathological images using hybrid OLConvN
        8502, -- 2203.16708 Task Adaptive Parameter Sharing for Multi-Task Learning
        9081, -- 2205.10268 B-cos Networks: Alignment is All We Need for Interpretability
        11002, -- 2210.12843 Delving into Masked Autoencoders for Multi-Label Thorax Disease Classificat
        12665, -- 2301.12900 DepGraph: Towards Any Structural Pruning
        13560, -- 2303.04278 CUDA: Convolution-based Unlearnable Datasets
        13692, -- 2303.06862 OTOV2: Automatic, Generic, User-Friendly
        15422, -- 2305.06244 Explainable Knowledge Distillation for On-device Chest X-Ray Classification
        17751, -- 2306.14169 A Web-based Mpox Skin Lesion Detection System Using State-of-the-art Deep L
        18015, -- 2307.02055 Adversarial Attacks on Image Classification Models: FGSM and Patch Attacks
        18205, -- 2307.06496 Microbial Genetic Algorithm-based Black-box Attack against Interpretable De
        18339, -- 2307.08771 UPSCALE: Unconstrained Channel Pruning
        19529, -- 2308.10438 Efficient Joint Optimization of Layer-Adaptive Weight Pruning in Deep Neura
        19787, -- 2308.13373 Enhanced Mortality Prediction In Patients With Subarachnoid Haemorrhage Usi
        24942, -- 2312.11510 QuadAttack: A Quadratic Programming Approach to Ordered Top-K Attacks
        27371, -- 2402.10100 Tuning In: Analysis of Audio Classifier Performance in Clinical Settings wi
        28620, -- 2403.06075 Multisize Dataset Condensation
        29620, -- 2403.19588 DenseNets Reloaded: Paradigm Shift Beyond ResNets and ViTs
        30001, -- 2404.04245 Evaluating Adversarial Robustness: A Comparison Of FGSM, Carlini-Wagner Att
        30845, -- 2404.17768 Changing the Training Data Distribution to Reduce Simplicity Bias Improves
        33389, -- 2406.14287 Segmentation of Non-Small Cell Lung Carcinomas: Introducing DRU-Net and Mul
        34625, -- 2407.10179 CLIP-Guided Generative Networks for Transferable Targeted Adversarial Attac
        35397, -- 2408.00002 Transfer Learning for Wildlife Classification: Evaluating YOLOv8 against De
        36165, -- 2408.12837 Underwater SONAR Image Classification and Analysis using LIME-based Explain
        38078, -- 2410.05871 A second-order-like optimizer with adaptive gradient scaling for deep learn
        44850, -- 2502.16622 Diagnosing COVID-19 Severity from Chest X-Ray Images Using ViT and CNN Arch
        47990, -- 2504.15051 VeLU: Variance-enhanced Learning Unit for Deep Neural Networks
        48100, -- 2504.17160 OUI Need to Talk About Weight Decay: A New Perspective on Overfitting Detec
        50706, -- 2506.06099 DermaCon-IN: A Multi-concept Annotated Dermatological Image Dataset of Indi
        52094, -- 2507.21364 Evaluating Deep Learning Models for African Wildlife Image Classification:
        60010, -- 2603.02181 Leveraging Model Soups to Classify Intangible Cultural Heritage Images from
        62355, -- 2601.12826 Seeing Isn't Always Believing: Analysis of Grad-CAM Faithfulness and Locali
        65033, -- 2511.11030 Algorithms Trained on Normal Chest X-rays Can Predict Health Insurance Type
        67649, -- 2509.22836 Seeing Isn't Believing: Context-Aware Adversarial Patch Synthesis via Condi
        69066, -- 2508.20230 Coresets from Trajectories: Selecting Data via Correlation of Loss Differen
        72672, -- 2505.21574 Do We Need All the Synthetic Data? Towards Targeted Synthetic Image Augment
        73323, -- 2504.18268 Towards a deep learning approach for classifying treatment response in glio
        73739, -- 2504.01608 The Mini-SiTian Array: real-bogus classification using deep learning
        78969, -- 2305.17473 A Comprehensive Overview and Comparative Analysis on Deep Learning Models:
        80284, -- 2112.13553 Classification of Histopathology Images of Lung Cancer Using Convolutional
        80550, -- 2108.12604 New Pruning Method Based on DenseNet Network for Image Classification
        80917, -- 2101.07903 Fine-Tuning and Training of DenseNet for Histopathology Image Representatio
        81383, -- 2004.02396 A Learning Framework for n-bit Quantized Neural Networks toward FPGAs
        81589, -- 1909.11870 Classification of Histopathological Biopsy Images Using Ensemble of Deep Le
        81765, -- 1904.04862 SWNet: Small-World Neural Networks and Rapid Convergence
        81766, -- 1904.01569 Exploring Randomly Wired Neural Networks for Image Recognition
        82023, -- 1805.02410 MMDenseLSTM: An efficient combination of convolutional and recurrent neural
        82083, -- 1802.07412 Density-aware Single Image De-raining using a Multi-stream Dense Network
        85445, -- 2604.22045 H-Sets: Hessian-Guided Discovery of Set-Level Feature Interactions in Image
        94386, -- 2509.03472 DPQuant: Efficient and Private Model Training via Dynamic Quantization Sche
        96433, -- external Neuromorphic Event Camera-Based Object Recognition and Grasping Position De
        97979, -- 2606.04767 Measuring Model Robustness via Fisher Information: Spectral Bounds, Theoret
        98301, -- external Achieving Robust Out-of-Distribution Generalization in Peripheral Blood Sme
        105473, -- external Mutual Information Regularization for Fairness-aware Deep Imaging Represent
        109219, -- 2105.09008 A Novel lightweight Convolutional Neural Network, ExquisiteNetV2
        111546, -- external Exploiting Bispectral Features for Single-Channel Speech Enhancement
        115013, -- external Improved Classification Learning from Highly Imbalanced Multi-Label Dataset
        115371, -- external Towards Rapid Mycetoma Species Diagnosis: A Deep Learning Approach for Stai
        124736, -- 2512.01675 GRASP: Guided Residual Adapters with Sample-wise Partitioning
        125294, -- 2512.24162 Deep Probabilistic Supervision for Image Classification
        129740  -- 2610.21743 Pairwise AUC Optimization Needs Corrective Power: A Unified View
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
        83, -- 1404.1869 DenseNet: Implementing Efficient ConvNet Descriptor Pyramids
        48433, -- 2505.03097 Not All Parameters Matter: Masking Diffusion Models for Enhancing Generatio
        48507, -- 2505.04769 Vision-Language-Action Models: Concepts, Progress, Applications and Challen
        48778, -- 2505.10496 CheXGenBench: A Unified Benchmark For Fidelity, Privacy and Utility of Synt
        48843, -- 2505.11196 DiCo: Revitalizing ConvNets for Scalable and Efficient Diffusion Modeling
        49002, -- 2505.12844 AGI-Elo: How Far Are We From Mastering A Task?
        49096, -- 2505.13817 InstanceBEV: Unifying Instance and BEV Representation for Global Modeling
        49159, -- 2505.14340 Plane Geometry Problem Solving with Multi-modal Reasoning: A Survey
        49894, -- 2505.20698 Sparsified State-Space Models are Efficient Highway Networks
        50159, -- 2505.23763 Sketch Down the FLOPs: Towards Efficient Networks for Human Sketch
        51911, -- 2507.11540 Towards Depth Foundation Model: Recent Trends in Vision-Based Depth Estimat
        51916, -- 2507.11936 A Survey of Deep Learning for Geometry Problem Solving
        51977, -- 2507.14102 UGPL: Uncertainty-Guided Progressive Learning for Evidence-Based Classifica
        52072, -- 2507.19804 ForCenNet: Foreground-Centric Network for Document Image Rectification
        54195, -- 2511.11238 Virtual Width Networks
        54438, -- 2511.16854 MRI Super-Resolution with Deep Learning: A Comprehensive Survey
        54651, -- 2512.06558 Embodied Referring Expression Comprehension in Human-Robot Interaction
        54791, -- 2512.09069 KD-OCT: Efficient Knowledge Distillation for Clinical-Grade Retinal OCT Cla
        55042, -- 2512.24880 mHC: Manifold-Constrained Hyper-Connections
        56364, -- 2602.24012 InfoNCE Induces Gaussian Distribution
        56730, -- 2603.15031 Attention Residuals
        56731, -- 2603.15619 Mixture-of-Depths Attention
        56737, -- 2603.14610 Make it SING: Analyzing Semantic Invariants in Classifiers
        59012, -- 2603.22387 Efficient Universal Perception Encoder
        59415, -- 2603.16934 AgriChat: A Multimodal Large Language Model for Agriculture Image Understan
        59416, -- 2603.13878 Step-CoT: Stepwise Visual Chain-of-Thought for Medical Visual Question Answ
        59739, -- 2603.18031 InfoMamba: An Attention-Free Hybrid Mamba-Transformer Model
        59791, -- 2603.06120 Dynamic Momentum Recalibration in Online Gradient Learning
        60020, -- 2603.02294 Loss Design and Architecture Selection for Long-Tailed Multi-Label Chest X-
        60027, -- 2603.01944 MobileMold: A Smartphone-Based Microscopy Dataset for Food Mold Detection
        60031, -- 2603.01879 Diagnosing Generalization Failures from Representational Geometry Markers
        60465, -- 2602.17929 ZACH-ViT: Regime-Dependent Inductive Bias in Compact Vision Transformers fo
        60681, -- 2602.13662 LeafNet: A Large-Scale Dataset and Comprehensive Benchmark for Foundational
        61011, -- 2602.08071 ViT-5: Vision Transformers for The Mid-2020s
        61013, -- 2602.08064 SiameseNorm: Breaking the Barrier to Reconciling Pre/Post-Norm
        61828, -- 2601.21582 Depth-Recurrent Attention Mixtures: Giving Latent Reasoning the Attention i
        61924, -- 2602.00130 On the Relationship Between Representation Geometry and Generalization in D
        62442, -- 2601.10945 PatientVLM Meets DocVLM: Pre-Consultation Dialogue Between Vision-Language
        62729, -- 2601.05732 mHC-lite: You Don't Need 20 Sinkhorn-Knopp Iterations
        63992, -- 2512.07251 See More, Change Less: Anatomy-Aware Diffusion for Contrast Enhancement
        65182, -- 2511.07983 ChexFract: From General to Specialized - Enhancing Fracture Description Ge
        65285, -- 2511.05803 MACMD: Multi-dilated Contextual Attention and Channel Mixer Decoding for Me
        65428, -- 2511.02404 Purrturbed but Stable: Human-Cat Invariant Representations Across CNNs, ViT
        65519, -- 2511.00981 VesSAM: Efficient Multi-Prompting for Segmenting Complex Vessel
        65547, -- 2511.00456 Weakly Supervised Pneumonia Localization from Chest X-Rays Using Deep Neura
        66000, -- 2510.20092 Attentive Convolution: Unifying the Expressivity of Self-Attention with Con
        66001, -- 2510.20968 Neural Mutual Information Estimation with Vector Copulas
        67682, -- 2509.22365 HierLight-YOLO: A Hierarchical and Lightweight Object Detection Network for
        68046, -- 2509.17100 The SAGES Critical View of Safety Challenge: A Global Benchmark for AI-Assi
        68516, -- 2509.08959 CoSwin: Convolution Enhanced Hierarchical Shifted Window Attention For Smal
        69738, -- 2508.09802 MUJICA: Reforming SISR Models for PBR Material Super-Resolution via Cross-M
        69814, -- 2508.08700 Subjective and Objective Quality Assessment of Banding Artifacts on Compres
        70071, -- 2508.05059 Learning from Oblivion: Predicting Knowledge Overflowed Weights via Retrodi
        70228, -- 2508.03091 T2UE: Generating Unlearnable Examples from Text Descriptions
        70524, -- 2507.22802 Advancing Fetal Ultrasound Image Quality Assessment in Low-Resource Setting
        70549, -- 2508.00922 CaliMatch: Adaptive Calibration for Improving Safe Semi-supervised Learning
        70566, -- 2507.22057 MetaLab: Few-Shot Game Changer for Image Recognition
        70611, -- 2507.21412 Cascading and Proxy Membership Inference Attacks
        70658, -- 2507.20418 Can Foundation Models Predict Fitness for Duty?
        70856, -- 2507.17779 CM-UNet: A Self-Supervised Learning-Based Model for Coronary Artery Segment
        70871, -- 2507.16624 A2Mamba: Attention-augmented State Space Models for Visual Recognition
        70982, -- 2507.14670 Gene-DML: Dual-Pathway Multi-Level Discrimination for Gene Expression Predi
        71147, -- 2507.10225 Synthesizing Near-Boundary OOD Samples for Out-of-Distribution Detection
        71502, -- 2507.01927 evMLP: An Efficient Event-Driven MLP Architecture for Vision
        71538, -- 2507.01254 Robust Brain Tumor Segmentation with Incomplete MRI Modalities Using Hölder
        71583, -- 2507.00474 ADAptation: Reconstruction-based Unsupervised Active Learning for Breast Ul
        71715, -- 2506.21046 Boosting Generative Adversarial Transferability with Self-supervised Vision
        71721, -- 2506.20877 THIRDEYE: Cue-Aware Monocular Depth Estimation via Brain-Inspired Multi-Sta
        71826, -- 2506.17455 AQUA20: A Benchmark Dataset for Underwater Species Classification under Cha
        71870, -- 2506.16073 TD3Net: A Temporal Densely Connected Multi-Dilated Convolutional Network fo
        71875, -- 2506.15940 Polyline Path Masked Attention for Vision Transformer
        72018, -- 2506.11515 Manager: Aggregating Insights from Unimodal Experts in Two-Tower VLMs and M
        72132, -- 2506.07637 HieraEdgeNet: A Multi-Scale Edge-Enhanced Framework for Automated Pollen Re
        72534, -- 2505.23675 ImmunoDiff: A Diffusion Model for Immunotherapy Response Prediction in Lung
        72676, -- 2505.20782 Towards Cross-Domain Multi-Targeted Adversarial Attacks
        72740, -- 2505.19195 CardioCoT: Hierarchical Reasoning for Multimodal Survival Analysis
        72797, -- 2505.17807 Temporal Consistency Constrained Transferable Adversarial Attacks with Back
        72968, -- 2505.12734 SounDiT: Geo-Contextual Soundscape-to-Landscape Generation
        73095, -- 2505.07654 Breast Cancer Classification in Deep Ultraviolet Fluorescence Images Using
        73099, -- 2505.07540 SynID: Passport Synthetic Dataset for Presentation Attack Detection
        73175, -- 2505.03519 Revisiting Model Inversion Evaluation: From Misleading Standards to Reliabl
        73219, -- 2505.01050 Transferable Adversarial Attacks on Black-Box Vision-Language Models
        73270, -- 2504.20405 SCOPE-MRI: Bankart Lesion Detection as a Case Study in Data Curation and De
        81991, -- 1806.04074 Semantically Selective Augmentation for Deep Compact Person Re-Identificati
        82944, -- 2605.06380 Empirical Evidence for Simply Connected Decision Regions in Image Classifie
        83463, -- 2605.18855 Delta Attention Residuals
        83683, -- 2605.20708 Rethinking Cross-Layer Information Routing in Diffusion Transformers
        84022, -- 2505.21147 Semi-Supervised Conformal Prediction With Unlabeled Nonconformity Score
        84306, -- 2512.01643 ViT$^3$: Unlocking Test-Time Training in Vision
        84392, -- 2512.12887 Revisiting 2D Foundation Models for Scalable 3D Medical Image Classificatio
        84604, -- 2602.21754 LiREC-Net: A Target-Free and Learning-Based Network for LiDAR, RGB, and Eve
        84826, -- 2603.09408 Reviving ConvNeXt for Efficient Convolutional Diffusion Models
        84912, -- 2603.14644 LUMINA: A Multi-Vendor Mammography Benchmark with Energy Harmonization Prot
        84988, -- 2603.19718 BALM: A Model-Agnostic Framework for Balanced Multimodal Learning under Imb
        84991, -- 2603.19766 Adapting a Pre-trained Single-Cell Foundation Model to Spatial Gene Express
        85261, -- 2604.03454 RDFace: A Benchmark Dataset for Rare Disease Facial Image Analysis under Ex
        85364, -- 2604.12356 OmniFood8K: Single-Image Nutrition Estimation via Hierarchical Frequency-Al
        85628, -- 2509.09242 CoAtNeXt:An Attention-Enhanced ConvNeXtV2-Transformer Hybrid Model for Gast
        85756, -- 2508.09560 WeatherPrompt: Multi-modality Representation Learning for All-Weather Drone
        85987, -- 2506.14562 AlphaDecay: Module-wise Weight Decay for Heavy-Tailed Balancing in LLMs
        86022, -- 2509.20177 Generative Model Inversion Through the Lens of the Manifold Hypothesis
        86184, -- 2506.24125 FADRM: Fast and Accurate Data Residual Matching for Dataset Distillation
        86336, -- 2506.08365 AlphaFold Database Debiasing for Robust Inverse Folding
        86380, -- 2506.09714 Auto-Compressing Networks
        86386, -- 2509.23373 Graph Your Own Prompt
        86469, -- 2507.08721 Monitoring Risks in Test-Time Adaptation
        86487, -- 2509.11711 The Quest for Universal Master Key Filters in DS-CNNs
        86652, -- 2506.15544 Stable Gradients for Stable Learning at Scale in Deep Reinforcement Learnin
        86739, -- 2506.04432 KOALA++: Efficient Kalman-Based Optimization of Neural Networks with Gradie
        86851, -- 2506.01511 Enhancing Diffusion-based Unrestricted Adversarial Attacks via Adversary Pr
        86854, -- 2510.09210 Provable Watermarking for Data Poisoning Attacks
        87244, -- 2509.22813 TRUST: Test-Time Refinement using Uncertainty-Guided SSM Traverses
        87260, -- 2510.02302 Knowledge Distillation Detection for Open-weights Models
        87358, -- 2506.05801 Neural Collapse in Cumulative Link Models for Ordinal Regression: An Analys
        87612, -- 2507.05728 Asynchronous Event Error-Minimizing Noise for Safeguarding Event Dataset
        87632, -- 2509.07879 Active Membership Inference Test (aMINT): Enhancing Model Auditability with
        87826, -- 2506.21037 Reinforcement Learning-Guided Data Selection via Redundancy Assessment
        88292, -- 2508.09824 Reverse Convolution and Its Applications to Image Restoration
        88300, -- 2508.21695 Activation Subspaces for Out-of-Distribution Detection
        88387, -- 2507.06651 Diff2I2P: Differentiable Image-to-Point Cloud Registration with Diffusion P
        88457, -- 2508.05689 Boosting Adversarial Transferability via Residual Perturbation Attack
        88563, -- 2505.22356 Suitability Filter: A Statistical Framework for Classifier Evaluation in Re
        88612, -- 2505.21363 Subgroups Matter for Robust Bias Mitigation
        88632, -- 2506.06853 Curvature Enhanced Data Augmentation for Regression
        88665, -- 2505.23681 Understanding Mode Connectivity via Parameter Space Symmetry
        89131, -- 2506.22696 Residual Matrix Transformers: Scaling the Size of the Residual Stream
        89207, -- 2505.05813 BCE vs. CE in Deep Feature Learning
        89299, -- 2506.06599 Direct Prediction Set Minimization via Bilevel Conformal Classifier Trainin
        89419, -- 2505.17883 FastCAV: Efficient Computation of Concept Activation Vectors for Explaining
        89453, -- 2506.14329 Adjustment for Confounding using Pre-Trained Representations
        89618, -- 2505.18568 Learning without Isolation: Pathway Protection for Continual Learning
        90067, -- 2505.01267 Diffusion-based Adversarial Purification from the Perspective of the Freque
        90581, -- 2505.08255 Where the Devil Hides: Deepfake Detectors Can No Longer Be Trusted
        92655, -- 2603.00629 Adapt Data to Model: Adaptive Transformation Optimization for Domain-shared
        92970, -- 2510.14231 When Flatness Does (Not) Guarantee Adversarial Robustness
        93245, -- 2507.02965 Concept-based Adversarial Attack: a Probabilistic Perspective
        93521, -- 2506.19558 Consistency-Driven Calibration and Matching for Few-Shot Class Incremental
        93549, -- 2603.10048 Revisiting Sharpness-Aware Minimization: A More Faithful and Effective Impl
        93577, -- 2505.23866 Towards Understanding The Calibration Benefits of Sharpness-Aware Minimizat
        93615, -- 2505.23933 BIRD: Behavior Induction via Representation-structure Distillation
        93700, -- 2509.23487 Temporal Generalization: A Reality Check
        94057, -- 2508.12132 TriQDef: Disrupting Semantic and Gradient Alignment to Prevent Adversarial
        94123, -- 2512.05931 On the Bayes Inconsistency of Disagreement Discrepancy Surrogates
        94126, -- 2510.07739 MeSH: Memory-as-State-Highways for Recursive Transformers
        94171, -- 2510.06448 How NOT to benchmark your SITE metric: Beyond Static Leaderboards and Towar
        94272, -- 2512.03870 Reconstructing KV Caches with Cross-Layer Fusion for Enhanced Transformers
        94322, -- 2509.25678 Massively Multimodal Foundation Models: A Framework for Capturing Interacti
        94384, -- 2601.19967 Perturbation-Induced Linearization: Constructing Unlearnable Data with Sole
        94690, -- 2603.04731 When Priors Backfire: On the Vulnerability of Unlearnable Examples to Pretr
        94838, -- 2506.18248 Improving Black-Box Generative Attacks via Generator Semantic Consistency
        94903, -- 2603.03725 Why Do Unlearnable Examples Work: A Novel Perspective of Mutual Information
        95920, -- 2510.01665 Non-Rigid Structure-From-Motion Via Differential Geometry with Recoverable
        97830, -- 2601.17550 AsterNav: Autonomous Aerial Robot Navigation in Darkness Using Passive Comp
        98144, -- 2606.11131 UniPET: a universal network for high-quality PET image denoising across var
        99373, -- 2602.06862 Parameters as Experts: Adapting Vision Models with Dynamic Parameter Routin
        99473, -- 2606.26719 FUSE: Full‑spectrum Unlearnable Examples via Spectral Equalization
        99609, -- 2605.17118 Differentiable Optimization Layers for Guaranteed Fairness in Deep Learning
        99723, -- 2506.23492 Sample Margin-Aware Recalibration of Temperature Scaling
        99971, -- 2605.29836 CB-SLICE: Concept-Based Interpretable Error Slice Discovery
        100429, -- 2601.21568 Bridging Functional and Representational Similarity via Usable Information
        100558, -- 2511.20934 Guaranteed Optimal Compositional Explanations for Neurons
        100594, -- 2601.02998 Multi-Distribution Robust Conformal Prediction
        100632, -- 2605.21552 Expectation Consistency Loss: Rethink Confidence Calibration under Covariat
        100971, -- 2505.02604 Connecting Independently Trained Modes via Layer-Wise Connectivity
        101153, -- 2602.20419 CREDIT: Certified Ownership Verification of Deep Neural Networks Against Mo
        101155, -- 2606.13587 Towards Effective Waste Segmentation for Automated Waste Recycling in Clutt
        101268, -- 2602.01733 Improving Backward Conformal Prediction via Non-Conformity Score Transforma
        101322, -- 2602.12932 TFTF: Training-Free Targeted Flow for Conditional Sampling
        101642, -- 2605.20839 Activation-Free Backbones for Image Recognition: Polynomial Alternatives wi
        101774, -- 2606.10612 GaussTrace: Provenance Analysis of 3D Gaussian Splatting Models with Eviden
        101916, -- 2506.00175 Who Gets Credit or Blame? Attributing Accountability in Modern AI Systems
        102381, -- 2602.04170 Partial Ring Scan: Revisiting Scan Order in Vision State Space Models
        104300, -- 2607.14530 xHC: Expanded Hyper-Connections
        105024, -- 2507.07721 Clinical Prior-Guided Tumor Generation for Breast Ultrasound with Cross Dom
        105208, -- 2507.10869 Focus on Texture: Rethinking Pre-training in Masked Autoencoders for Medica
        105315, -- 2607.03203 Inter-class separability loss for weakly supervised mutually exclusive mult
        105581, -- 2508.21154 RadGS-Reg: Registering Spine CT with Biplanar X-rays via Joint 3D Radiative
        105785, -- 2506.23538 Uncertainty-aware Diffusion and Reinforcement Learning for Joint Plane Loca
        105813, -- 2506.23641 VAP-Diffusion: Enriching Descriptions with MLLMs for Enhanced Medical Image
        105867, -- 2607.25108 OPERA: Offline Policy-guided Expert Routing and Adaptation for Universal Bi
        105954, -- 2607.27230 Multi-Head Attention Residuals
        106498, -- 2511.08937 Boosting Adversarial Transferability via Ensemble Non-Attention
        107057, -- 2511.17685 Dual-Path Knowledge-Augmented Contrastive Alignment Network for Spatially R
        107249, -- 2601.08602 WaveFormer: Frequency-Time Decoupled Vision Modeling with Wave Equation
        107339, -- 2512.18722 Generating Risky Samples with Conformity Constraints via Diffusion Models
        107388, -- 2511.17861 Cost-Sensitive Conformal Training with Provably Controllable Learning Bound
        107407, -- 2511.09828 SMoFi: Step-wise Momentum Fusion for Split Federated Learning on Heterogene
        107473, -- 2505.24592 A Flat Minima Perspective on Understanding Augmentations and Model Robustne
        107655, -- 2511.12044 FedSDA: Federated Stain Distribution Alignment for Non-IID Histopathologica
        107820, -- 2512.02469 TGDD: Trajectory Guided Dataset Distillation with Balanced Distribution
        107956, -- 2511.07032 Fair Bayesian Data Selection via Generalized Discrepancy Measures
        108065, -- 2603.07195 Shaping Parameter Contribution Patterns for Out-of-Distribution Detection
        108290, -- 2512.06345 CLUENet: Cluster Attention Makes Neural Networks Have Eyes
        109280, -- 2608.14290 Intern-S2-Mobius: Foundation Model with Decoupled Knowledge and Reasoning
        111061, -- 2511.07897 Data Descriptions from Large Language Models with Influence Estimation
        112020, -- 2507.12723 Cross-Modal Watermarking for Authentic Audio Recovery and Tamper Localizati
        113806, -- 2608.30320 On the Design of Qwen3.8-Next Architecture: Evaluation, Efficiency, and Tra
        113939, -- 2609.01072 Let Confidence Change, Not the Prediction: Prediction-Preserving Repair for
        117807, -- 2505.19120 Freqformer: Image-Demoiréing Transformer via Effective Frequency Decomposit
        118186, -- 2606.29952 Exploiting Local Flatness for Efficient Out-of-Distribution Detection
        118232, -- 2607.00916 Condensing Large-Scale Datasets Directly with Minimal Information Loss
        119074, -- 2603.08374 This Looks Distinctly Like That: Grounding Interpretable Recognition in Sti
        119282, -- 2607.09193 YeTI: You Only Need Two Noisy Images for Real-World sRGB Noise Generation
        120335, -- 2505.12685 Mamba-Adaptor: State Space Model Adaptor for Visual Recognition
        122333, -- 2609.32534 DepthBench: Measuring How Residual Connections Enable More Computational De
        122351, -- 2609.33203 Structured Residual Connectivity Matters for Diffusion Transformers
        122381, -- 2606.29521 Not All Objectives Are Born Equal: Priority-Constrained Descent for Hierarc
        122759, -- 2610.02480 MEA: A Reward-Driven Multi-Agent System for Faithful Model Explanations
        122820, -- 2610.04605 ConEx: Human-Interpretable Saliency Maps via Concept-Aware Attribution
        122955, -- 2610.11570 Scaling to Tens of Thousands of Test-Time Iterations with Loop-Native Atten
        123021, -- 2511.12046 BackWeak: Backdooring Knowledge Distillation Simply with Weak Triggers and
        123187, -- 2610.13630 Multi-Stream Attention Residuals
        123721, -- 2610.19625 DAGFormer: Global Topology Prediction for Transformer Cross-Layer Connectio
        124953, -- 2609.38625 Interpretable but Fragile? Robustness of Concept Bottlenecks under Geometri
        125185, -- 2605.07270 $\texttt{bispectrum}$: Selective $G$-Bispectra Made Practical
        125295, -- 2603.13652 Causal Attribution via Activation Patching
        125408, -- 2602.09009 ANCRe: Adaptive Neural Connection Reassignment for Efficient Depth Scaling
        125409, -- 2610.18658 BridgeTwist: Twisting Schrödinger Bridges for Training-Free Conditional Sam
        125853, -- 2605.22432 AMUSE: Anytime Muon with Stable Gradient Evaluation
        127529, -- 2605.16208 A Scalable Nonparametric Continuous-Time Survival Model through Numerical Q
        127643, -- 2510.19773 Estimating Model-Level Membership Inference Vulnerability Without Reference
        130263, -- 2609.38991 Anchoring Adversarial Trajectories to Data Manifolds: A Bilevel Transfer Op
        130713, -- 2607.29621 CENDRe: Concept Extraction with Natural Domain Representations
        131141, -- 2608.10372 Invertible Logits Transformation for Accuracy-Preserving Post-Hoc Uncertain
        132002  -- 2610.41711 Hierarchical Residuals: A Minimalist Decoupling of Residual Width from Comp
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
        931, -- 1710.09412 mixup: Beyond Empirical Risk Minimization
        1336, -- 1806.05236 Manifold Mixup: Better Representations by Interpolating Hidden States
        1485, -- 1809.02499 MixUp as Locally Linear Out-Of-Manifold Regularization
        2040, -- 1904.11238 Unsupervised Label Noise Modeling and Loss Correction
        2399, -- 1908.02983 Pseudo-Labeling and Confirmation Bias in Deep Semi-Supervised Learning
        3151, -- 2002.12047 FMix: Enhancing Mixed Sample Data Augmentation
        3181, -- 2003.02484 Adversarial Vertex Mixup: Toward Better Adversarially Robust Generalization
        4146, -- 2009.06962 Puzzle Mix: Exploiting Saliency and Local Statistics for Optimal Mixup
        4167, -- 2009.08453 MEAL V2: Boosting Vanilla ResNet-50 to 80%+ Top-1 Accuracy on ImageNet with
        4332, -- 2010.05549 Improving Low Resource Code-switched ASR using Augmented Code-switched TTS
        4680, -- 2012.03358 Select, Label, and Mix: Learning Discriminative Invariant Feature Represent
        4912, -- 2101.07589 Hyperspectral Image Super-Resolution with Spectral Mixup and Heterogeneous
        4992, -- 2102.03065 Co-Mixup: Saliency Guided Joint Mixup with Supermodular Diversity
        5044, -- 2102.08183 Comparison of semi-supervised deep learning algorithms for audio classifica
        5261, -- 2103.13027 AutoMix: Unveiling the Power of Mixup for Stronger Classifiers
        5298, -- 2103.15375 AlignMixup: Improving Representations By Interpolating Aligned Features
        5898, -- 2106.03374 RegMix: Data Mixing Augmentation for Regression
        5933, -- 2106.04990 It Takes Two to Tango: Mixup for Deep Metric Learning
        7019, -- 2110.11144 RCT: Random Consistency Training for Semi-supervised Sound Event Detection
        7255, -- 2111.09833 TransMix: Attend to Mix for Vision Transformers
        7347, -- 2111.15454 Boosting Discriminative Visual Representation Learning with Scenario-Agnost
        8176, -- 2203.03897 Geodesic Multi-Modal Mixup for Robust Fine-Tuning
        8353, -- 2203.10761 Harnessing Hard Mixed Samples with Decoupled Regularizer
        8832, -- 2204.11406 Robust Self-Augmentation for Named Entity Recognition with Meta Reweighting
        9011, -- 2205.06153 TreeMix: Compositional Constituency-based Data Augmentation for Natural Lan
        9089, -- 2205.10450 Temporally Precise Action Spotting in Soccer Videos Using Dense Detection A
        9320, -- 2206.00832 Fast Benchmarking of Accuracy vs. Training Time with Cyclic Learning Rates
        9466, -- 2206.06640 Confidence Score for Source-Free Unsupervised Domain Adaptation
        9497, -- 2206.08009 Balancing Discriminability and Transferability for Source-Free Domain Adapt
        9638, -- 2206.14502 RegMixup: Mixup as a Regularizer Can Surprisingly Improve Accuracy and Out
        10254, -- 2209.04851 OpenMixup: Open Mixup Toolbox and Benchmark for Visual Representation Learn
        10728, -- 2210.05775 C-Mixup: Improving Generalization in Regression
        11032, -- 2210.13512 Provably Learning Diverse Features in Multi-View Data with Midpoint Mixup
        11218, -- 2211.02291 SelecMix: Debiased Learning by Contradicting-pair Sampling
        11254, -- 2211.03946 Understanding the Role of Mixup in Knowledge Distillation: An Empirical Stu
        12381, -- 2301.04805 DEA-Net: Single image dehazing based on detail-enhanced convolution and con
        13145, -- 2302.08229 Improving Spoken Language Identification with Map-Mix
        13498, -- 2303.02577 Effectiveness of Data Augmentation for Parameter Efficient Tuning with Limi
        13593, -- 2303.05068 Toward Unsupervised Realistic Visual Question Answering
        13608, -- 2303.05309 MixSpeech: Cross-Modality Self-Learning with Audio-Visual Stream Mixup for
        13747, -- 2303.07864 DualMix: Unleashing the Potential of Data Augmentation for Online Class-Inc
        13779, -- 2303.08433 The Benefits of Mixup for Feature Learning
        13818, -- 2303.09219 MixCycle: Mixup Assisted Semi-Supervised 3D Single Object Tracking with Cyc
        14787, -- 2304.09402 MixPro: Simple yet Effective Data Augmentation for Prompt-based Learning
        15961, -- 2305.13547 Self-Evolution Learning for Mixup: Enhance Data Augmentation on Few-Shot Te
        16281, -- 2305.15816 DDDM-VC: Decoupled Denoising Diffusion Models with Disentangled Representat
        16364, -- 2305.16817 Selective Mixup Helps with Distribution Shifts, But Not (Only) because of M
        16653, -- 2305.19730 Data Representations' Study of Latent Image Manifolds
        16725, -- 2306.00267 Provable Benefit of Mixup for Finding Optimal Decision Boundaries
        16768, -- 2306.00740 On the Limitations of Temperature Scaling for Distributions with Overlaps
        17149, -- 2306.05043 Non-autoregressive Conditional Diffusion Models for Time Series Prediction
        17278, -- 2306.06788 Graph Mixup with Soft Alignments
        18560, -- 2307.12463 Rethinking Data Distillation: Do Not Overlook Calibration
        18884, -- 2308.01546 MusicLDM: Enhancing Novelty in Text-to-Music Generation Using Beat-Synchron
        19677, -- 2308.11990 RankMixup: Ranking-Based Mixup Training for Network Calibration
        20661, -- 2309.11104 AttentionMix: Data augmentation method that relies on BERT attention mechan
        21041, -- 2309.16633 Mixup Your Own Pairs
        23352, -- 2311.08851 Data Augmentations in Deep Weight Spaces
        24671, -- 2312.07266 ProxyDet: Synthesizing Proxy Novel Classes via Classwise Mixup for Open-Voc
        24970, -- 2312.11954 Adversarial AutoMixup
        26768, -- 2402.02464 A Graph is Worth $K$ Words: Euclideanizing Graph using Pure Transformer
        26821, -- 2402.03124 Towards Eliminating Hard Label Constraints in Gradient Inversion Attacks
        26999, -- 2402.04929 Source-Free Domain Adaptation with Diffusion-Guided Source Data Generation
        27106, -- 2402.06171 Pushing Boundaries: Mixup's Influence on Neural Collapse
        27286, -- 2402.08777 DNABERT-S: Pioneering Species Differentiation with Species-Aware DNA Embedd
        27648, -- 2402.12844 ICON: Improving Inter-Report Consistency in Radiology Report Generation via
        28909, -- 2403.10153 Improving Medical Multi-modal Contrastive Learning with Expert Annotations
        29116, -- 2403.12729 Posterior Uncertainty Quantification in Neural Networks using Data Augmenta
        29357, -- 2403.15512 Enhancing Effectiveness and Robustness in a Low-Resource Regime via Decisio
        29531, -- 2403.18301 Selective Mixup Fine-Tuning for Optimizing Non-Decomposable Objectives
        30459, -- 2404.11202 GhostNetV3: Exploring the Training Strategies for Compact Models
        33512, -- 2406.15723 Acoustic Feature Mixup for Balanced Multi-aspect Pronunciation Assessment
        34437, -- 2407.07805 SUMix: Mixup with Semantic and Uncertain Information
        36684, -- 2409.05202 A Survey on Mixup Augmentations and Beyond
        37372, -- 2409.17777 Harnessing Shared Relations via Multimodal Mixup Contrastive Learning for M
        38009, -- 2410.05248 SFTMix: Elevating Language Model Instruction Tuning with Mixup Recipe
        39288, -- 2410.21269 OmniSep: Unified Omni-Modality Sound Separation with Query-Mixup
        42270, -- 2412.20211 Generative Regression Based Watch Time Prediction for Short-Video Recommend
        48164, -- 2504.18983 MediAug: Exploring Visual Augmentation in Medical Imaging
        49559, -- 2505.17871 BLAST: Balanced Sampling Time Series Corpus for Universal Forecasting Model
        50942, -- 2506.09736 Vision Matters: Simple Visual Perturbations Can Boost Multimodal Math Reaso
        51417, -- 2506.19585 SMARTIES: Spectrum-Aware Multi-Sensor Auto-Encoder for Remote Sensing Image
        53852, -- 2510.23479 MergeMix: A Unified Augmentation Paradigm for Visual and Multi-Modal Unders
        59769, -- 2603.06492 NOBLE: Accelerating Transformers with Nonlinear Low-Rank Branches
        60198, -- 2410.10922 Towards Privacy-Guaranteed Label Unlearning in Vertical Federated Learning:
        64074, -- 2512.05663 LeAD-M3D: Leveraging Asymmetric Distillation for Real-time Monocular 3D Det
        64910, -- 2511.13541 Graph Out-of-Distribution Detection via Test-Time Calibration with Dual Dyn
        67995, -- 2509.17971 Intra-Cluster Mixup: An Effective Data Augmentation Technique for Complemen
        68417, -- 2509.11265 SelectMix: Enhancing Label Noise Robustness through Targeted Sample Mixing
        72116, -- 2506.08255 SHIELD: Secure Hypernetworks for Incremental Expansion Learning Defense
        72797, -- 2505.17807 Temporal Consistency Constrained Transferable Adversarial Attacks with Back
        73858, -- 2503.20823 Playing the Fool: Jailbreaking LLMs and Multimodal LLMs with Out-of-Distrib
        75325, -- 2501.00437 Unleashing Text-to-Image Diffusion Prior for Zero-Shot Image Captioning
        77658, -- 2403.07113 Class Imbalance in Object Detection: An Experimental Diagnosis and Study of
        78449, -- 2309.17352 Improving Audio Captioning Models with Fine-grained Audio Features, Text Em
        79209, -- 2303.14254 Towards Diverse and Coherent Augmentation for Time-Series Forecasting
        79351, -- 2302.09292 FrAug: Frequency Domain Augmentation for Time Series Forecasting
        80862, -- 2102.12664 MixSpeech: Data Augmentation for Low-resource Automatic Speech Recognition
        84334, -- 2512.03932 Beyond the Ground Truth: Enhanced Supervision for Image Restoration
        84729, -- 2603.03726 QD-PCQA: Quality-Aware Domain Adaptation for Point Cloud Quality Assessment
        84841, -- 2603.10526 Sparse Task Vector Mixup with Hypernetworks for Efficient Knowledge Transfe
        85383, -- 2604.14710 G-MIXER: Geodesic Mixup-based Implicit Semantic Expansion and Explicit Sema
        86141, -- 2506.04206 A Few Moments Please: Scalable Graphon Learning via Moment Matching
        87679, -- 2510.10584 Equipping Vision Foundation Model with Mixture of Experts for Out-of-Distri
        90412, -- 2503.21140 Recurrent Feature Mining and Keypoint Mixup Padding for Category-Agnostic P
        90500, -- 2411.15553 Improving Transferable Targeted Attacks with Feature Tuning Mixup
        90562, -- 2505.09615 UWAV: Uncertainty-weighted Weakly-supervised Audio-Visual Video Parsing
        90721, -- 2503.22984 Optimal Transport-Guided Source-Free Adaptation for Face Anti-Spoofing
        91400, -- 2311.01434 Tailoring Mixup to Data for Calibration
        91681, -- 2502.10288 Adversarial Mixup Unlearning
        91844, -- 2402.06855 For Better or For Worse? Learning Minimum Variance Features With Label Augm
        95052, -- 2602.05380 SAIL: Self-Amplified Iterative Learning for Diffusion Model Alignment with
        97999, -- external SCADA (AutoSOTA)
        98078, -- external Few-for-Many Personalized Federated Learning (FedFewS) (AutoSOTA)
        98656, -- 2208.05688 Semi-supervised Vision Transformers at Scale
        99095, -- 2607.02271 AGVBench: A Reliability-Oriented Benchmark of Data Augmentation for Vein Re
        100289, -- 2605.16793 PULSE: Generative Phase Evolution for Non-Stationary Time Series Forecastin
        102065, -- 2510.03690 From Moments to Models: Graphon-Mixture Learning for Mixup and Contrastive
        105074, -- external CurConMix: A Curriculum Contrastive Learning Framework for Enhancing Surgic
        105169, -- 2509.15608 Enhancing WSI-Based Survival Analysis with Report-Auxiliary Self-Distillati
        106356, -- 2510.20449 LM-mixup: Text Data Augmentation via Language Model based Mixup
        107664, -- 2511.06854 Beyond Observations: Reconstruction Error-Guided Irregularly Sampled Time S
        108144, -- 2507.19031 ProGMLP: A Progressive Framework for GNN-to-MLP Knowledge Distillation with
        109424, -- 2104.09367 Contrastive Learning for Compact Single Image Dehazing
        109683, -- external Asymmetric cross-modal attention network with multimodal augmented mixup fo
        111133, -- external CMSP-ST: Cross-modal Mixup with Speech Purification for End-to-End Speech T
        111953, -- 2506.09556 Medusa: A Multimodal Deep Fusion Multi-Stage Training Framework for Speech
        112527, -- 2407.16802 Distribution-Aware Robust Learning from Long-Tailed Data with Noisy Labels
        113026, -- 2407.12431 GLARE: Low Light Image Enhancement via Generative Latent Feature based Code
        113053, -- external Semantic-guided Robustness Tuning for Few-Shot Transfer Across Extreme Doma
        113581, -- 2407.12188 CroMo-Mixup: Augmenting Cross-Model Representations for Continual Self-Supe
        113586, -- 2407.10052 Augmented Neural Fine-tuning for Efficient Backdoor Purification
        114365, -- external Algorithmic Fairness in Lesion Classification by Mitigating Class Imbalance
        114439, -- external Class-aware Mutual Mixup with Triple Alignments for Semi-Supervised Cross-d
        115133, -- 2406.13237 ModelMix: A New Model-Mixup Strategy to Minimize Vicinal Risk across Tasks
        115642, -- 2403.19600 Enhance Image Classification via Inter-Class Image Mixup with Diffusion Mod
        115937, -- 2404.08951 Constructing and Exploring Intermediate Domains in Mixed Domain Semi-superv
        116034, -- external Robust Image Denoising through Adversarial Frequency Mixup
        116397, -- external Discriminative Pattern Calibration Mechanism for Source-Free Domain Adaptat
        116756, -- external Fine-grained Prototypical Voting with Heterogeneous Mixup for Semi-supervis
        117203, -- 2311.17597 Continual Self-supervised Learning: Towards Universal Multi-modal Medical D
        118140, -- external S2-FracMix: Self-Saliency Fractal Mixup
        119778, -- 2312.14474 MonoLSS: Learnable Sample Selection For Monocular 3D Detection
        120184, -- 2509.22412 FreqDebias: Towards Generalizable Deepfake Detection via Consistency-Driven
        120301, -- external Generative Hard Example Augmentation for Semantic Point Cloud Segmentation
        121519, -- external Dual-Level Hypergraph Generation for Addressing Feature Scarcity in Whole-S
        123079, -- 2201.04368 Preventing Manifold Intrusion with Locality: Local Mixup
        127195  -- external Does Mixed Label Imbalance Matter to Minority Collapse in Imbalanced Learni
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
        4112, -- 2009.02792 Overview and Evaluation of Sound Event Localization and Detection in DCASE
        4243, -- 2010.01028 Hard Negative Mixing for Contrastive Learning
        4252, -- 2010.01412 Sharpness-Aware Minimization for Efficiently Improving Generalization
        4317, -- 2010.04925 Regularizing Neural Networks via Adversarial Model Perturbation
        4358, -- 2010.07835 Fine-Tuning Pre-trained Language Model with Weak Supervision: A Contrastive
        4585, -- 2011.09899 MixMix: All You Need for Data-Free Compression Are Feature and Data Mixing
        4589, -- 2011.10082 Hybrid Consistency Training with Prototype Adaptation for Few-Shot Learning
        4668, -- 2012.02577 Critical Evaluation of Deep Neural Networks for Wrist Fracture Detection
        4672, -- 2012.02909 What Makes a "Good" Data Augmentation in Knowledge Distillation - A Statis
        4683, -- 2012.03457 VideoMix: Rethinking Data Augmentation for Video Classification
        4703, -- 2012.04846 SnapMix: Semantically Proportional Mixing for Augmenting Fine-grained Data
        4710, -- 2012.05649 Concept Generalization in Visual Representation Learning
        4730, -- 2012.07177 Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segment
        4742, -- 2012.08054 Image Inpainting Guided by Coherence Priors of Semantics and Textures
        4763, -- 2012.11101 ResizeMix: Mixing Data with Preserved Object Information and True Labels
        4782, -- 2012.12877 Training data-efficient image transformers & distillation through attention
        4875, -- 2101.03697 RepVGG: Making VGG-style ConvNets Great Again
        4893, -- 2101.04898 Unlearnable Examples: Making Personal Data Unexploitable
        4894, -- 2101.05022 Re-labeling ImageNet: from Single to Multi-Labels, from Global to Localized
        4907, -- 2101.06639 Removing Undesirable Feature Contributions Using Out-of-Distribution Data
        4920, -- 2101.08596 LEAF: A Learnable Frontend for Audio Classification
        4923, -- 2101.08692 Characterizing signal propagation to close the performance gap in unnormali
        4959, -- 2101.11986 Tokens-to-Token ViT: Training Vision Transformers from Scratch on ImageNet
        4972, -- 2102.01243 PSLA: Improving Audio Tagging with Pretraining, Sampling, Labeling, and Agg
        4996, -- 2102.03334 ViLT: Vision-and-Language Transformer Without Convolution or Region Supervi
        5022, -- 2102.06171 High-Performance Large-Scale Image Recognition Without Normalization
        5030, -- 2102.06605 Unleashing the Power of Contrastive Self-Supervised Visual Models via Contr
        5076, -- 2102.10882 Conditional Positional Encodings for Vision Transformers
        5081, -- 2102.11646 HardCoRe-NAS: Hard Constrained diffeRentiable Neural Architecture Search
        5084, -- 2102.11972 Do Transformer Modifications Transfer Across Implementations and Applicatio
        5087, -- 2102.12122 Pyramid Vision Transformer: A Versatile Backbone for Dense Prediction witho
        5112, -- 2103.00112 Transformer in Transformer
        5129, -- 2103.01534 Towards Efficiently Diversifying Dialogue Generation via Embedding Augmenta
        5186, -- 2103.06695 BYOL for Audio: Self-Supervised Learning for General-Purpose Audio Represen
        5188, -- 2103.06877 Fast and Accurate Model Scaling
        5196, -- 2103.07579 Revisiting ResNets: Improved Training and Scaling Strategies
        5234, -- 2103.10919 Robustness via Cross-Domain Ensembles
        5238, -- 2103.11285 Geo-Spatiotemporal Features and Shape-Based Prior Knowledge for Fine-graine
        5283, -- 2103.14453 Data Augmentation in Natural Language Processing: A Novel Text Generation A
        5291, -- 2103.14899 CrossViT: Cross-Attention Multi-Scale Vision Transformer for Image Classifi
        5306, -- 2103.15691 ViViT: A Video Vision Transformer
        5341, -- 2104.00298 EfficientNetV2: Smaller Models and Faster Training
        5395, -- 2104.03602 SiT: Self-supervised vIsion Transformer
        5400, -- 2104.04015 CutPaste: Self-Supervised Learning for Anomaly Detection and Localization
        5426, -- 2104.05704 Escaping the Big Data Paradigm with Compact Transformers
        5438, -- 2104.06399 Co-Scale Conv-Attentional Image Transformers
        5444, -- 2104.06609 Representative Forgery Mining for Fake Face Detection
        5523, -- 2104.08826 GPT3Mix: Leveraging Large-scale Language Models for Text Augmentation
        5560, -- 2104.10972 ImageNet-21K Pretraining for the Masses
        5562, -- 2104.11178 VATT: Transformers for Multimodal Self-Supervised Learning from Raw Video,
        5563, -- 2104.11227 Multiscale Vision Transformers
        5581, -- 2104.12533 Visformer: The Vision-friendly Transformer
        5597, -- 2104.13497 ConTNet: Why not use convolution and transformer at the same time?
        5638, -- 2105.01601 MLP-Mixer: An all-MLP Architecture for Vision
        5642, -- 2105.01883 RepMLP: Re-parameterizing Convolutions into Fully-connected Layers for Imag
        5658, -- 2105.03075 A Survey of Data Augmentation Approaches for NLP
        5667, -- 2105.03404 ResMLP: Feedforward networks for image classification with data-efficient t
        5680, -- 2105.04070 Robust Training Using Natural Transformation
        5788, -- 2105.12723 Nested Hierarchical Transformer: Towards Accurate, Data-Efficient and Inter
        5809, -- 2105.14275 Greedy Bayesian Posterior Approximation with Deep Ensembles
        5829, -- 2106.00168 Rethinking Pseudo Labels for Semi-Supervised Object Detection
        5836, -- 2106.00666 You Only Look at One Sequence: Rethinking Transformer in Vision through Obj
        5856, -- 2106.01342 SAINT: Improved Neural Networks for Tabular Data via Row Attention and Cont
        5860, -- 2106.01548 When Vision Transformers Outperform ResNets without Pre-training or Strong
        5881, -- 2106.02654 Churn Reduction via Distillation
        5883, -- 2106.02695 Meta-Learning with Fewer Tasks through Task Interpolation
        5910, -- 2106.03917 Mixture Outlier Exposure: Towards Out-of-Distribution Detection in Fine-gra
        5928, -- 2106.04803 CoAtNet: Marrying Convolution and Attention for All Data Sizes
        5929, -- 2106.04823 Taxonomy of Machine Learning Safety: A Survey and Primer
        5942, -- 2106.05237 Knowledge distillation: A good teacher is patient and consistent
        5943, -- 2106.05319 Stein Latent Optimization for Generative Adversarial Networks
        5947, -- 2106.05682 DASO: Distribution-Aware Semantics-Oriented Pseudo-label for Imbalanced Sem
        5955, -- 2106.05945 Does Knowledge Distillation Really Work?
        5991, -- 2106.07499 An Empirical Survey of Data Augmentation for Limited Data Learning in NLP
        6018, -- 2106.08962 Efficient Deep Learning: A Survey on Making Deep Learning Models Smaller, F
        6051, -- 2106.10270 How to train your ViT? Data, Augmentation, and Regularization in Vision Tra
        6063, -- 2106.10866 Customizing Graph Neural Networks using Path Reweighting
        6112, -- 2106.13112 VOLO: Vision Outlooker for Visual Recognition
        6123, -- 2106.13797 PVT v2: Improved Baselines with Pyramid Vision Transformer
        6156, -- 2106.15941 Augmented Shortcuts for Vision Transformers
        6162, -- 2107.00135 Attention Bottlenecks for Multimodal Fusion
        6184, -- 2107.02137 ERNIE 3.0: Large-scale Knowledge Enhanced Pre-training for Language Underst
        6271, -- 2107.08430 YOLOX: Exceeding YOLO Series in 2021
        6293, -- 2107.10471 Improving Polyphonic Sound Event Detection on Multichannel Recordings with
        6307, -- 2107.11817 Go Wider Instead of Deeper
        6329, -- 2107.14222 Rethinking and Improving Relative Position Encoding for Vision Transformer
        6333, -- 2107.14795 Perceiver IO: A General Architecture for Structured Inputs & Outputs
        6334, -- 2108.00154 CrossFormer: A Versatile Vision Transformer Hinging on Cross-scale Attentio
        6374, -- 2108.02982 Improving Contrastive Learning by Visualizing Feature Transformation
        6395, -- 2108.04384 RaftMLP: How Much Can Be Done Without Attention and with Less Spatial Local
        6424, -- 2108.06552 Continual Semi-Supervised Learning through Contrastive Interpolation Consis
        6428, -- 2108.06949 Data Augmentation for Scene Text Recognition
        6532, -- 2109.00642 Searching for Efficient Multi-Stage Vision Transformers
        6704, -- 2109.11105 Distiller: A Systematic Study of Model Distillation Methods in Natural Lang
        6738, -- 2109.13210 SAU: Smooth activation function using convolution with approximate identiti
        6769, -- 2110.00476 ResNet strikes back: An improved training procedure in timm
        6791, -- 2110.01852 Data Augmentation Approaches in Natural Language Processing: A Survey
        6799, -- 2110.02178 MobileViT: Light-weight, General-purpose, and Mobile-friendly Vision Transf
        6800, -- 2110.02210 Mix3D: Out-of-Context Data Augmentation for 3D Scenes
        6855, -- 2110.04369 A Loss Curvature Perspective on Training Instability in Deep Learning
        6870, -- 2110.05069 Efficient Training of Audio Transformers with Patchout
        6908, -- 2110.06537 Well-classified Examples are Underestimated in Classification with Deep Neu
        6917, -- 2110.06864 ByteTrack: Multi-Object Tracking by Associating Every Detection Box
        6949, -- 2110.07719 Certified Patch Robustness via Smoothed Vision Transformers
        6996, -- 2110.08890 Network Augmentation for Tiny Deep Learning
        7081, -- 2110.15128 Contrast and Mix: Temporal Contrastive Video Domain Adaptation with Backgro
        7200, -- 2111.06377 Masked Autoencoders Are Scalable Vision Learners
        7259, -- 2111.09883 Swin Transformer V2: Scaling Up Capacity and Resolution
        7260, -- 2111.09886 SimMIM: A Simple Framework for Masked Image Modeling
        7271, -- 2111.10734 Deep Probability Estimation
        7281, -- 2111.11418 MetaFormer Is Actually What You Need for Vision
        7288, -- 2111.11828 Variance Reduction in Deep Learning: More Momentum is All You Need
        7311, -- 2111.13353 Contrastive Vicinal Space for Unsupervised Domain Adaptation
        7343, -- 2111.15185 SamplingAug: On the Importance of Patch Sampling Augmentation for Single Im
        7344, -- 2111.15242 ConDA: Unsupervised Domain Adaptation for LiDAR Segmentation via Regularize
        7387, -- 2112.01522 Uni-Perceiver: Pre-training Unified Architecture for Generic Perception for
        7388, -- 2112.01526 MViTv2: Improved Multiscale Vision Transformers for Classification and Dete
        7515, -- 2112.08313 Measure and Improve Robustness in NLP Models: A Survey
        7550, -- 2112.09133 Masked Feature Prediction for Self-Supervised Visual Pre-Training
        7556, -- 2112.09331 Contrastive Vision-Language Pre-training with Limited Resources
        7605, -- 2112.13492 Vision Transformer for Small-Size Datasets
        7610, -- 2112.13692 Augmenting Convolutional networks with attention-based aggregation
        7668, -- 2201.02973 MAXIM: Multi-Axis MLP for Image Processing
        7673, -- 2201.03545 A ConvNet for the 2020s
        7739, -- 2201.08371 Revisiting Weakly Supervised Pre-Training of Visual Perception Models
        7740, -- 2201.08377 Omnivore: A Single Model for Many Visual Modalities
        7752, -- 2201.09450 UniFormer: Unifying Convolution and Self-attention for Visual Recognition
        7756, -- 2201.09699 EASY: Ensemble Augmented-Shot Y-shaped Learning: State-Of-The-Art Few-Shot
        7758, -- 2201.09792 Patches Are All You Need?
        7777, -- 2201.10890 One Student Knows All Experts Know: From Sparse to Dense
        7839, -- 2202.00796 On Balancing Bias and Variance in Unsupervised Multi-Source-Free Domain Ada
        7841, -- 2202.00874 HTS-AT: A Hierarchical Token-Semantic Audio Transformer for Sound Classific
        7874, -- 2202.02626 Layer-wise Regularized Adversarial Training using Layers Sustainability Ana
        7884, -- 2202.02916 Dataset Condensation with Contrastive Signals
        7888, -- 2202.03026 Context Autoencoder for Self-Supervised Representation Learning
        7889, -- 2202.03052 OFA: Unifying Architectures, Tasks, and Modalities Through a Simple Sequenc
        7895, -- 2202.03377 Benchmarking and Analyzing Point Cloud Classification under Corruptions
        7949, -- 2202.06510 Mixing and Shifting: Exploiting Global and Local Dependencies in Vision MLP
        7956, -- 2202.06709 How Do Vision Transformers Work?
        8010, -- 2202.09318 DataMUX: Data Multiplexing for Neural Networks
        8018, -- 2202.09741 Visual Attention Network
        8027, -- 2202.10261 A Self-Supervised Descriptor for Image Copy Detection
        8049, -- 2202.11921 Auto-scaling Vision Transformers without Training
        8079, -- 2202.13469 UCTopic: Unsupervised Contrastive Learning for Phrase Representations and T
        8127, -- 2203.01441 3D Common Corruptions and Data Augmentation
        8128, -- 2203.01522 BatchFormer: Learning to Explore Sample Relationships for Robust Representa
        8168, -- 2203.03689 WaveMix: Resource-efficient Token Mixing for Images
        8200, -- 2203.05482 Model soups: averaging weights of multiple fine-tuned models improves accur
        8229, -- 2203.06717 Scaling Up Your Kernels to 31x31: Revisiting Large Kernel Design in CNNs
        8258, -- 2203.07687 Compressing Sentence Representation for Semantic Retrieval via Homomorphic
        8261, -- 2203.07735 Augmenting Document Representations for Dense Retrieval with Interpolation
        8262, -- 2203.07740 Exact Feature Distribution Matching for Arbitrary Style Transfer and Domain
        8318, -- 2203.09391 When Chosen Wisely, More Data Is What You Need: A Universal Sample-Efficien
        8383, -- 2203.11926 Focal Modulation Networks
        8401, -- 2203.12602 VideoMAE: Masked Autoencoders are Data-Efficient Learners for Self-Supervis
        8558, -- 2204.01678 MultiMAE: Multi-modal Multi-task Masked Autoencoders
        8560, -- 2204.01697 MaxViT: Multi-Axis Vision Transformer
        8608, -- 2204.03359 ECCV Caption: Correcting False Negatives by Collecting Machine-and-Human-ve
        8609, -- 2204.03421 Self-supervised learning for robust voice cloning
        8612, -- 2204.03475 Solving ImageNet: a Unified Scheme for Training any Backbone to Top Results
        8614, -- 2204.03511 Interval Bound Interpolation for Few-shot Learning with Few Tasks
        8651, -- 2204.04662 FOSTER: Feature Boosting and Compression for Class-Incremental Learning
        8719, -- 2204.07118 DeiT III: Revenge of the ViT
        8720, -- 2204.07141 Masked Siamese Networks for Label-Efficient Learning
        8721, -- 2204.07143 Neighborhood Attention Transformer
        8722, -- 2204.07154 MiniViT: Compressing Vision Transformers with Weight Multiplexing
        8747, -- 2204.07832 A Contrastive Cross-Channel Data Augmentation Framework for Aspect-based Se
        8752, -- 2204.08040 NICO++: Towards Better Benchmarking for Domain Generalization
        8767, -- 2204.08446 VSA: Learning Varied-Size Window Attention in Vision Transformers
        8904, -- 2205.00841 GPUNet: Searching the Deployable Convolution Neural Networks for GPUs
        8912, -- 2205.01308 Contrastive Learning for Prompt-Based Few-Shot Language Learners
        8919, -- 2205.01580 Better plain ViT baselines for ImageNet-1k
        8928, -- 2205.01972 Sequencer: Deep LSTM for Image Classification
        8959, -- 2205.03154 Investigating and Explaining the Frequency Bias in Image Classification
        9049, -- 2205.09113 Masked Autoencoders As Spatiotemporal Learners
        9219, -- 2205.13535 AdaptFormer: Adapting Vision Transformers for Scalable Visual Recognition
        9235, -- 2205.13943 Architecture-Agnostic Masked Image Modeling - From ViT back to CNN
        9244, -- 2205.14230 Semi-supervised Semantics-guided Adversarial Training for Trajectory Predic
        9252, -- 2205.14375 WaveMix: A Resource-efficient Neural Network for Image Analysis
        9253, -- 2205.14443 A Closer Look at Self-Supervised Lightweight Vision Transformers
        9272, -- 2205.14986 GMML is All you Need
        9305, -- 2206.00051 Learning Instance-Specific Augmentations by Capturing Local Invariances
        9335, -- 2206.01186 ORC: Network Group-based Knowledge Distillation using Online Role Change
        9377, -- 2206.02680 Separable Self-attention for Mobile Vision Transformers
        9426, -- 2206.04656 Simple Cues Lead to a Strong Multi-Object Tracker
        9427, -- 2206.04658 BigVGAN: A Universal Neural Vocoder with Large-Scale Training
        9429, -- 2206.04664 On Data Scaling in Masked Image Modeling
        9491, -- 2206.07706 Masked Frequency Modeling for Self-Supervised Visual Pre-Training
        9494, -- 2206.07846 Action Spotting using Dense Detection Anchors Revisited: Submission to the
        9616, -- 2206.13140 Compressing Features for Learning with Noisy Labels
        9622, -- 2206.13476 Impact of Acoustic Event Tagging on Scene Classification in a Multi-Task Le
        9628, -- 2206.14098 RevBiFPN: The Fully Reversible Bidirectional Feature Pyramid Network
        9659, -- 2207.00026 LaserMix for Semi-Supervised LiDAR Semantic Segmentation
        9708, -- 2207.03341 Softmax-free Linear Transformers
        9785, -- 2207.06405 Masked Autoencoders that Listen
        9804, -- 2207.07611 Position Prediction as an Effective Pretraining Strategy
        9813, -- 2207.08185 Mind the Gap: Polishing Pseudo labels for Accurate Semi-supervised Object D
        9848, -- 2207.10023 Tailoring Self-Supervision for Supervised Learning
        9866, -- 2207.10666 TinyViT: Fast Pretraining Distillation for Small Vision Transformers
        9971, -- 2208.02080 A Feature-space Multimodal Data Augmentation Technique for Text-video Retri
        9972, -- 2208.02169 SpanDrop: Simple and Effective Counterfactual Learning for Long Sequences
        10041, -- 2208.06677 Adan: Adaptive Nesterov Momentum Algorithm for Faster Optimizing Deep Model
        10049, -- 2208.07204 USB: A Unified Semi-supervised Learning Benchmark for Classification
        10056, -- 2208.07407 SemAug: Semantically Meaningful Image Augmentations for Object Detection Th
        10092, -- 2208.09833 Label-Noise Learning with Intrinsically Long-Tailed Data
        10097, -- 2208.10169 Multi-Granularity Distillation Scheme Towards Lightweight Semi-Supervised S
        10171, -- 2208.14071 Deep Open-Set Recognition for Silicon Wafer Production Monitoring
        10195, -- 2209.00613 ID and OOD Performance Are Sometimes Inversely Correlated on Real-world Dat
        10228, -- 2209.02976 YOLOv6: A Single-Stage Object Detection Framework for Industrial Applicatio
        10244, -- 2209.03917 Exploring Target Representations for Masked Autoencoders
        10255, -- 2209.04861 Inverse Image Frequency for Long-tailed Image Recognition
        10267, -- 2209.05723 A Capsule Network for Hierarchical Multi-Label Image Classification
        10340, -- 2209.09203 Look where you look! Saliency-guided Q-networks for generalization in visua
        10366, -- 2209.10015 Metadata Archaeology: Unearthing Data Subsets by Leveraging Training Dynami
        10375, -- 2209.10655 Mega: Moving Average Equipped Gated Attention
        10469, -- 2209.15001 Dilated Neighborhood Attention Transformer
        10529, -- 2210.01213 Robust Active Distillation
        10550, -- 2210.01820 MOAT: Alternating Mobile Convolution and Attention Brings Strong Vision Mod
        10555, -- 2210.01891 Adaptively Weighted Data Augmentation Consistency Regularization for Robust
        10711, -- 2210.05497 Improving Sharpness-Aware Minimization with Fisher Mask for Better Generali
        10715, -- 2210.05557 OPERA: Omni-Supervised Representation Learning with Hierarchical Supervisio
        10734, -- 2210.05938 Robust Models are less Over-Confident
        10735, -- 2210.05958 Bridging the Gap Between Vision Transformers and Convolutional Neural Netwo
        10740, -- 2210.06096 Masked Motion Encoding for Self-Supervised Video Representation Learning
        10760, -- 2210.06455 Token-Label Alignment for Vision Transformers
        10765, -- 2210.06640 Compute-Efficient Deep Learning: Algorithmic Trends and Opportunities
        10801, -- 2210.07346 An Embarrassingly Simple Backdoor Attack on Self-supervised Learning
        10822, -- 2210.07839 Contrastive Audio-Visual Masked Autoencoder
        10836, -- 2210.08457 Scratching Visual Transformer's Back with Uniform Attention
        10863, -- 2210.09184 Packed-Ensembles for Efficient Uncertainty Estimation
        10882, -- 2210.10090 How to Boost Face Recognition with StyleGAN?
        10886, -- 2210.10175 Intra-Source Style Augmentation for Improved Domain Generalization
        10930, -- 2210.11328 Play It Back: Iterative Attention for Audio Recognition
        10932, -- 2210.11407 Similarity of Neural Architectures using Adversarial Attack Transferability
        10944, -- 2210.11768 Augmentation with Projection: Towards an Effective and Efficient Data Augme
        10991, -- 2210.12681 Rethinking Rotation in Self-Supervised Contrastive Learning: Adaptive Posit
        11002, -- 2210.12843 Delving into Masked Autoencoders for Multi-Label Thorax Disease Classificat
        11031, -- 2210.13452 MetaFormer Baselines for Vision
        11239, -- 2211.03295 MogaNet: Multi-order Gated Aggregation Network
        11268, -- 2211.04533 Harmonizing the object recognition strategies of deep neural networks with
        11298, -- 2211.05781 Demystify Transformers & Convolutions in Modern Image Deep Networks
        11327, -- 2211.07157 ParCNetV2: Oversized Kernel with Enhanced Attention
        11343, -- 2211.07636 EVA: Exploring the Limits of Masked Visual Representation Learning at Scale
        11361, -- 2211.08253 HMOE: Hypernetwork-based Mixture of Experts for Domain Generalization
        11392, -- 2211.09117 MAGE: MAsked Generative Encoder to Unify Representation Learning and Image
        11393, -- 2211.09119 Token Turing Machines
        11404, -- 2211.09552 UniFormerV2: Spatiotemporal Learning by Arming Image ViTs with Video UniFor
        11409, -- 2211.09703 EfficientTrain: Exploring Generalized Curriculum Learning for Training Visu
        11416, -- 2211.09788 DiffusionDet: Diffusion Model for Object Detection
        11419, -- 2211.09807 Towards All-in-one Pre-training via Maximizing Multi-modal Mutual Informati
        11433, -- 2211.10330 GENIUS: Sketch-based Language Model Pre-training via Extreme and Selective
        11458, -- 2211.10955 When Noisy Labels Meet Long Tail Dilemmas: A Representation Calibration Met
        11470, -- 2211.11167 Vision Transformer with Super Token Sampling
        11481, -- 2211.11317 DeSTSeg: Segmentation Guided Denoising Student-Teacher for Anomaly Detectio
        11502, -- 2211.11733 Teaching Structured Vision&Language Concepts to Vision&Language Models
        11507, -- 2211.11753 SplitNet: Learnable Clean-Noisy Label Splitting for Learning with Noisy Lab
        11561, -- 2211.12883 Mitigating and Evaluating Static Bias of Action Representations in the Back
        11610, -- 2211.13956 Learning General Audio Representations with Large-Scale Training of Patchou
        11611, -- 2211.13976 Expanding Small-Scale Datasets with Guided Imagination
        11613, -- 2211.14058 Cross-Domain Ensemble Distillation for Domain Generalization
        11661, -- 2211.15444 DAMO-YOLO : A Report on Real-Time Object Detection Design
        11668, -- 2211.15657 Is Conditional Generative Modeling all you need for Decision-Making?
        11700, -- 2211.16412 Procedural Image Programs for Representation Learning
        11741, -- 2212.00465 FoPro: Few-Shot Guided Robust Webly-Supervised Prototypical Learning
        11756, -- 2212.00776 ResFormer: Scaling ViTs with Multi-Resolution Training
        11761, -- 2212.00794 Scaling Language-Image Pre-training via Masking
        11769, -- 2212.00979 PASTA: Proportional Amplitude Spectrum Training Augmentation for Syn-to-Rea
        11790, -- 2212.01674 CrossSplit: Mitigating Label Noise Memorization through Data Splitting
        11821, -- 2212.02773 DiffusionInst: Diffusion Model for Instance Segmentation
        11829, -- 2212.03131 Explainability as statistical inference
        11832, -- 2212.03229 Rethinking Video ViTs: Sparse Video Tubes for Joint Image and Video Learnin
        11833, -- 2212.03237 RANA: Relightable Articulated Neural Avatars
        11844, -- 2212.03462 PADDLES: Phase-Amplitude Spectrum Disentangled Early Stopping for Learning
        11852, -- 2212.03862 Teaching Matters: Investigating the Role of Supervision in Vision Transform
        11892, -- 2212.04825 A Whac-A-Mole Dilemma: Shortcuts Come in Multiples Where Mitigating One Amp
        11923, -- 2212.05922 Audiovisual Masked Autoencoders
        11934, -- 2212.06138 CLIP Itself is a Strong Fine-tuner: Achieving 85.7% and 88.0% Top-1 Accurac
        11988, -- 2212.07784 RTMDet: An Empirical Study of Designing Real-Time Object Detectors
        12029, -- 2212.08649 Better May Not Be Fairer: A Study on Subgroup Discrepancy in Image Classifi
        12031, -- 2212.08663 Randomized Quantization: A Generic Augmentation for Data Agnostic Self-supe
        12047, -- 2212.09058 BEATs: Audio Pre-Training with Acoustic Tokenizers
        12222, -- 2212.12977 SMMix: Self-Motivated Image Mixing for Vision Transformers
        12230, -- 2212.13350 A Generalization of ViT/MLP-Mixer to Graphs
        12238, -- 2212.13847 Heterogeneous Graph Contrastive Learning with Meta-path Contexts and Adapti
        12264, -- 2301.00006 Recovering Top-Two Answers and Confusion Probability in Multi-Choice Crowds
        12283, -- 2301.00808 ConvNeXt V2: Co-designing and Scaling ConvNets with Masked Autoencoders
        12288, -- 2301.01146 Rethinking Mobile Block for Efficient Attention-based Models
        12291, -- 2301.01217 Unlearnable Clusters: Towards Label-agnostic Unlearnable Examples
        12297, -- 2301.01380 Ego-Only: Egocentric Action Detection without Exocentric Transferring
        12338, -- 2301.02819 ExcelFormer: A neural network surpassing GBDTs on tabular data
        12419, -- 2301.06719 FemtoDet: An Object Detection Baseline for Energy Versus Performance Tradeo
        12452, -- 2301.08243 Self-Supervised Learning from Images with a Joint-Embedding Predictive Arch
        12488, -- 2301.09595 Zorro: the masked multimodal transformer
        12588, -- 2301.11706 Input Perturbation Reduces Exposure Bias in Diffusion Models
        12608, -- 2301.12077 ALIM: Adjusting Label Importance Mechanism for Noisy Partial Label Learning
        12683, -- 2301.13195 Adaptive Computation with Elastic Input Sequence
        12690, -- 2301.13293 Overcoming Simplicity Bias in Deep Networks using a Feature Sieve
        12752, -- 2302.00487 A Comprehensive Survey of Continual Learning: Theory, Method and Applicatio
        12758, -- 2302.00704 Pathologies of Predictive Diversity in Deep Ensembles
        12787, -- 2302.01327 Dual PatchNorm
        12835, -- 2302.02092 Interpolation for Robust Learning: Data Augmentation on Wasserstein Geodesi
        12837, -- 2302.02210 Oscillation-free Quantization for Low-bit Vision Transformers
        12860, -- 2302.02503 Leaving Reality to Imagination: Robust Classification via Generated Dataset
        12869, -- 2302.02605 Toward Large Kernel Models
        12971, -- 2302.04476 Towards Geospatial Foundation Models via Continual Pretraining
        13007, -- 2302.05118 Beyond In-Domain Scenarios: Robust Density-Aware Calibration
        13030, -- 2302.05666 Jaccard Metric Losses: Optimizing the Jaccard Index with Soft Labels
        13093, -- 2302.06992 Hard-aware Instance Adaptive Self-training for Unsupervised Cross-domain Se
        13095, -- 2302.07011 A Modern Look at the Relationship between Sharpness and Generalization
        13132, -- 2302.07994 À-la-carte Prompt Tuning (APT): Combining Distinct Data Via Composable Prom
        13231, -- 2302.10866 Hyena Hierarchy: Towards Larger Convolutional Language Models
        13268, -- 2302.11861 Out-of-Domain Robustness via Targeted Augmentations
        13270, -- 2302.12028 Novel Class Discovery: an Introduction and Key Concepts
        13297, -- 2302.12441 MUX-PLMs: Data Multiplexing for High-throughput Language Models
        13298, -- 2302.12444 On the Training Instability of Shuffling SGD with Batch Normalization
        13299, -- 2302.12453 Inducing Neural Collapse in Deep Long-tailed Learning
        13452, -- 2303.01500 Dropout Reduces Underfitting
        13455, -- 2303.01559 Improving GAN Training via Feature Space Shrinkage
        13514, -- 2303.03108 Gradient Norm Aware Minimization Seeks First-Order Flatness and Improves Ge
        13534, -- 2303.03667 Run, Don't Walk: Chasing Higher FLOPS for Faster Neural Networks
        13560, -- 2303.04278 CUDA: Convolution-based Unlearnable Datasets
        13585, -- 2303.04947 InfoBatch: Lossless Training Speed Up by Unbiased Dynamic Data Pruning
        13605, -- 2303.05251 Masked Image Modeling with Local Multi-Scale Reconstruction
        13706, -- 2303.07123 Modality-Agnostic Debiasing for Single Domain Generalization
        13794, -- 2303.08810 BiFormer: Vision Transformer with Bi-Level Routing Attention
        13803, -- 2303.08983 Reinforce Data, Multiply Impact: Improved Model Accuracy and Robustness wit
        13816, -- 2303.09165 A New Benchmark: On the Utility of Synthetic Data with Blender for Bare Sup
        13854, -- 2303.09769 Denoising Diffusion Autoencoders are Unified Self-supervised Learners
        13875, -- 2303.10158 Data-centric Artificial Intelligence: A Survey
        13885, -- 2303.10451 Augmenting and Aligning Snippets for Few-Shot Video Domain Adaptation
        13935, -- 2303.11331 EVA-02: A Visual Representation for Neon Genesis
        13960, -- 2303.11637 Equiangular Basis Vectors
        13961, -- 2303.11643 Manipulating Transfer Learning for Property Inference
        13980, -- 2303.12001 ViC-MAE: Self-Supervised Representation Learning from Images and Video with
        13999, -- 2303.12314 Self-supervised Meta-Prompt Learning with Meta-Gradient Regularization for
        14019, -- 2303.12670 Correlational Image Modeling for Self-Supervised Visual Pre-Training
        14068, -- 2303.13496 The effectiveness of MAE pre-pretraining for billion-scale pretraining
        14154, -- 2303.14817 Frame Flexible Network
        14172, -- 2303.15105 Vision Transformer with Quadrangle Attention
        14196, -- 2303.15446 SwiftFormer: Efficient Additive Attention for Transformer-based Real-time M
        14212, -- 2303.15833 Complementary Domain Adaptation and Generalization for Unsupervised Continu
        14233, -- 2303.16203 Your Diffusion Model is Secretly a Zero-Shot Classifier
        14243, -- 2303.16390 Are Data-driven Explanations Robust against Out-of-distribution Data?
        14262, -- 2303.16727 VideoMAE V2: Scaling Video Masked Autoencoders with Dual Masking
        14272, -- 2303.16900 InceptionNeXt: When Inception Meets ConvNeXt
        14288, -- 2303.17152 Mixed Autoencoder for Self-supervised Visual Representation Learning
        14315, -- 2303.17595 Neglected Free Lunch - Learning Image Classifiers Using Annotation Byprodu
        14318, -- 2303.17602 Beyond Appearance: a Semantic Controllable Self-Supervised Learning Framewo
        14328, -- 2303.17764 Towards Adversarially Robust Continual Learning
        14369, -- 2304.00387 HaLP: Hallucinating Latent Positives for Skeleton-based Self-Supervised Lea
        14421, -- 2304.01464 Hierarchical Supervision and Shuffle Data Augmentation for 3D Semi-Supervis
        14462, -- 2304.02034 Effective Theory of Transformers at Initialization
        14472, -- 2304.02330 SMPConv: Self-moving Point Representations for Continuous Convolution
        14508, -- 2304.03283 Diffusion Models as Masked Autoencoders
        14510, -- 2304.03294 What makes a good data augmentation for few-shot unsupervised image anomaly
        14618, -- 2304.05350 Astroformer: More Data Might not be all you need for Classification
        14632, -- 2304.05659 RIFormer: Keep Your Vision Backbone Effective While Removing Token Mixer
        14640, -- 2304.05919 Hard Patches Mining for Masked Image Modeling
        14657, -- 2304.06244 Computationally-Efficient Neural Image Compression with Shallow Decoders
        14831, -- 2304.10253 Image retrieval outperforms diffusion models on data augmentation
        14880, -- 2304.11263 Benchmarking Low-Shot Robustness to Natural Distribution Shifts
        14899, -- 2304.11705 Walking Your LiDOG: A Journey Through Multiple Domains for LiDAR Semantic S
        14912, -- 2304.12043 MixPro: Data Augmentation with MaskMix and Progressive Attention Labeling f
        14916, -- 2304.12210 A Cookbook of Self-Supervised Learning
        14933, -- 2304.12520 Hint-Aug: Drawing Hints from Foundation Vision Transformers Towards Boosted
        15091, -- 2305.00650 Discover and Cure: Concept-aware Mitigation of Spurious Correlation
        15093, -- 2305.00673 Bidirectional Copy-Paste for Semi-Supervised Medical Image Segmentation
        15094, -- 2305.00729 What Do Self-Supervised Vision Transformers Learn?
        15185, -- 2305.02299 Dynamic Sparse Training with Structured Sparsity
        15470, -- 2305.07027 EfficientViT: Memory Efficient Vision Transformer with Cascaded Group Atten
        15513, -- 2305.07828 Description and Discussion on DCASE 2023 Challenge Task 2: First-Shot Unsup
        15598, -- 2305.09160 SUG: Single-dataset Unified Generalization for 3D Point Cloud Classificatio
        15602, -- 2305.09235 Synthetic data, real errors: how (not) to publish and use synthetic data
        15646, -- 2305.10018 Transfer Learning for Fine-grained Classification Using Semi-supervised Lea
        15894, -- 2305.12961 Enhanced Meta Label Correction for Coping with Label Corruption
        15897, -- 2305.12972 VanillaNet: the Power of Minimalism in Deep Learning
        15935, -- 2305.13284 Target-Aware Generative Augmentations for Single-Shot Adaptation
        16114, -- 2305.14663 You Are What You Annotate: Towards Better Models through Annotator Represen
        16115, -- 2305.14669 NegVSR: Augmenting Negatives for Generalized Noise Modeling in Real-World V
        16162, -- 2305.14890 HARD: Hard Augmentations for Robust Distillation
        16482, -- 2305.18171 Improved Probabilistic Image-Text Representations
        16483, -- 2305.18183 On Counterfactual Data Augmentation Under Confounding
        16495, -- 2305.18274 Reconstructing the Mind's Eye: fMRI-to-Image with Contrastive Learning and
        16632, -- 2305.19458 A Unified Audio-Visual Learning Framework for Localization, Separation, and
        16721, -- 2306.00238 Bytes Are All You Need: Transformers Operating Directly On File Bytes
        16812, -- 2306.00989 Hiera: A Hierarchical Vision Transformer without the Bells-and-Whistles
        16832, -- 2306.01222 Scaling Up Semi-supervised Learning with Unconstrained Unlabelled Data
        16875, -- 2306.01710 A Data-Driven Measure of Relative Uncertainty for Misclassification Detecti
        16880, -- 2306.01736 DaTaSeg: Taming a Universal Multi-Dataset Multi-Task Segmentation Model
        17004, -- 2306.03221 Structural Re-weighting Improves Graph Domain Adaptation
        17041, -- 2306.03536 On Pitfalls of Test-Time Adaptation
        17082, -- 2306.04140 Increasing Diversity While Maintaining Accuracy: Text Data Generation with
        17085, -- 2306.04186 Self-supervised Audio Teacher-Student Transformer for Both Clip-level and F
        17130, -- 2306.04822 Optimizing ViViT Training: Time and Memory Reduction for Action Recognition
        17138, -- 2306.04911 Test-Time Style Shifting: Handling Arbitrary Styles in Domain Generalizatio
        17270, -- 2306.06635 2-D SSM: A General Spatial Layer for Visual Transformers
        17290, -- 2306.06881 Unmasking Deepfakes: Masked Autoencoding Spatiotemporal Transformers for En
        17309, -- 2306.07197 AROID: Improving Adversarial Robustness Through Online Instance-Wise Data A
        17319, -- 2306.07282 Waffling around for Performance: Visual Classification with Random Words an
        17394, -- 2306.08103 Generating Images with 3D Annotations Using Diffusion Models
        17437, -- 2306.08713 What can a cook in Italy teach a mechanic in India? Action Recognition Gene
        17468, -- 2306.09158 Feed Two Birds with One Scone: Exploiting Wild Data for Both Out-of-Distrib
        17607, -- 2306.11248 Dynamic Perceiver for Efficient Visual Recognition
        17614, -- 2306.11304 Traversing Between Modes in Function Space for Fast Ensembling
        17669, -- 2306.12517 FFCV: Accelerating Training by Removing Data Bottlenecks
        17691, -- 2306.12929 Quantizable Transformers: Removing Outliers by Helping Attention Heads Do N
        17702, -- 2306.13092 Squeeze, Recover and Relabel: Dataset Condensation at ImageNet Scale From A
        17717, -- 2306.13575 Scaling MLPs: A Tale of Inductive Bias
        17763, -- 2306.14525 ParameterNet: Parameters Are All You Need
        17836, -- 2306.16016 Positive Label Is All You Need for Multi-Label Classification
        17882, -- 2306.16927 End-to-end Autonomous Driving: Challenges and Frontiers
        17903, -- 2306.17203 Diff-Foley: Synchronized Video-to-Audio Synthesis with Latent Diffusion Mod
        17925, -- 2306.17848 Hardwiring ViT Patch Selectivity into CNNs using Patch Mixing
        17953, -- 2307.00648 Intra- & Extra-Source Exemplar-Based Style Synthesis for Improved Domain Ge
        18013, -- 2307.02047 CAME: Confidence-guided Adaptive Memory Efficient Optimization
        18142, -- 2307.04942 Benchmarking Algorithms for Federated Domain Generalization
        18219, -- 2307.06948 Self-regulating Prompts: Foundational Model Adaptation without Forgetting
        18251, -- 2307.07494 TALL: Thumbnail Layout for Deepfake Video Detection
        18319, -- 2307.08500 Cumulative Spatial Knowledge Distillation for Vision Transformers
        18323, -- 2307.08579 Scale-Aware Modulation Meet Transformer
        18368, -- 2307.09283 RepViT: Revisiting Mobile CNN From ViT Perspective
        18508, -- 2307.11469 Distribution Shift Matters for Knowledge Distillation with Webly Collected
        18527, -- 2307.11823 HybridAugment++: Unified Frequency Spectra Perturbations for Model Robustne
        18534, -- 2307.11978 Why Is Prompt Tuning for Vision-Language Models Robust to Noisy Labels?
        18545, -- 2307.12168 Hallucination Improves the Performance of Unsupervised Visual Representatio
        18558, -- 2307.12427 Augmented Box Replay: Overcoming Foreground Shift for Incremental Object De
        18568, -- 2307.12576 Self-refining of Pseudo Labels for Music Source Separation with Noisy Label
        18577, -- 2307.12730 COCO-O: A Benchmark for Object Detectors under Natural Distribution Shifts
        18620, -- 2307.13539 Model Calibration in Dense Classification with Adaptive Label Perturbation
        18684, -- 2307.14611 TextManiA: Enriching Visual Feature by Text-driven Manifold Augmentation
        18718, -- 2307.15061 The RoboDepth Challenge: Methods and Advancements Towards Robust Depth Esti
        18821, -- 2308.00261 Improving Pixel-based MIM by Reducing Wasted Modeling Capability
        18825, -- 2308.00301 Online Prototype Learning for Online Continual Learning
        18831, -- 2308.00376 Deep Image Harmonization with Learnable Augmentation
        18835, -- 2308.00442 FLatten Transformer: Vision Transformer using Focused Linear Attention
        18851, -- 2308.01042 WCCNet: Wavelet-integrated CNN with Crossmodal Rearranging Fusion for Fast
        18856, -- 2308.01194 Improving Generalization in Visual Reinforcement Learning via Conflict-awar
        18941, -- 2308.02535 Learning to Generate Training Datasets for Robust Semantic Segmentation
        18993, -- 2308.03409 DiT: Efficient Vision Transformers with Dynamic Token Routing
        19025, -- 2308.04016 Hierarchical Visual Primitive Experts for Compositional Zero-Shot Learning
        19057, -- 2308.04549 Prune Spatio-temporal Tokens by Semantic-aware Temporal Accumulation
        19066, -- 2308.04657 Which Tokens to Use? Investigating Token Reduction in Vision Transformers
        19117, -- 2308.05480 YOLO-MS: Rethinking Multi-Scale Representation Learning for Real-time Objec
        19140, -- 2308.05911 Collaborative Tracking Learning for Frame-Rate-Insensitive Multi-Object Tra
        19195, -- 2308.06692 SimMatchV2: Semi-Supervised Learning with Graph Consistency
        19199, -- 2308.06712 Compositional Feature Augmentation for Unbiased Scene Graph Generation
        19257, -- 2308.07645 Steering Language Generation: Harnessing Contrastive Expert Guidance and Ne
        19277, -- 2308.07815 ImbSAM: A Closer Look at Sharpness-Aware Minimization in Class-Imbalanced R
        19281, -- 2308.07893 Memory-and-Anticipation Transformer for Online Action Understanding
        19349, -- 2308.08822 MixBag: Bag-Level Data Augmentation for Learning from Label Proportions
        19466, -- 2308.09965 Anomaly-Aware Semantic Segmentation via Style-Aligned OoD Augmentation
        19488, -- 2308.10133 TransFace: Calibrating Transformer Training for Face Recognition from a Dat
        19556, -- 2308.10632 Foundation Model-oriented Robustness: Robust Image Model Evaluation with Pr
        19637, -- 2308.11568 SPANet: Frequency-balancing Token Mixer using Spectral Pooling Aggregation
        19657, -- 2308.11778 Understanding Hessian Alignment for Domain Generalization
        19759, -- 2308.12982 A Survey of AI Music Generation Tools and Models
        19763, -- 2308.13111 Bayesian Low-rank Adaptation for Large Language Models
        19828, -- 2308.14024 Balanced Representation Learning for Long-tailed Skeleton-based Action Reco
        19898, -- 2308.15090 Killing two birds with one stone: Can an audio captioning system also be us
        19916, -- 2308.15466 Input margins can predict generalization too
        19928, -- 2308.15711 Optimizing Factual Accuracy in Text Generation through Dynamic Knowledge Se
        20026, -- 2309.00770 Bias and Fairness in Large Language Models: A Survey
        20057, -- 2309.01270 COMEDIAN: Self-Supervised Learning and Knowledge Distillation for Action Sp
        20067, -- 2309.01430 DAT++: Spatially Dynamic Vision Transformer with Deformable Attention
        20182, -- 2309.03576 DropPos: Pre-Training Vision Transformers by Reconstructing Dropped Positio
        20183, -- 2309.03598 Enhancing Sample Utilization through Sample Adaptive Augmentation in Semi-S
        20241, -- 2309.04747 When to Learn What: Model-Adaptive Data Augmentation Curriculum
        20281, -- 2309.05375 Toward a Deeper Understanding: RetNet Viewed through Convolution
        20346, -- 2309.06651 ConR: Contrastive Regularizer for Deep Imbalanced Regression
        20380, -- 2309.07159 A Strong and Simple Deep Learning Baseline for BCI MI Decoding
        20405, -- 2309.07499 Efficiently Robustify Pre-trained Models
        20432, -- 2309.07911 Disentangling Spatial and Temporal Learning for Efficient Image-to-Video Tr
        20453, -- 2309.08153 Fine-tune the pretrained ATST model for sound event detection
        20505, -- 2309.08787 Beyond Labels: Leveraging Deep Learning and LLMs for Content Metadata
        20512, -- 2309.08838 AOSR-Net: All-in-One Sandstorm Removal Network
        20628, -- 2309.10713 Interpret Vision Transformers as ConvNets with Dynamic Convolutions
        20679, -- 2309.11331 Gold-YOLO: Efficient Object Detector via Gather-and-Distribute Mechanism
        20686, -- 2309.11446 Weight Averaging Improves Knowledge Distillation under Domain Shift
        20693, -- 2309.11523 RMT: Retentive Networks Meet Vision Transformers
        20797, -- 2309.13016 Understanding Deep Gradient Leakage via Inversion Influence Functions
        20822, -- 2309.13258 Order-preserving Consistency Regularization for Domain Adaptation and Gener
        20831, -- 2309.13353 Beyond Grids: Exploring Elastic Input Sampling for Vision Transformers
        20981, -- 2309.15762 Rapid Network Adaptation: Learning to Adapt Neural Networks Using Test-Time
        20993, -- 2309.15938 Exploring Self-Supervised Contrastive Learning of Spatial Sound Event Repre
        21060, -- 2309.16921 YOLOR-Based Multi-Task Learning
        21087, -- 2309.17230 Spurious Feature Diversification Improves Out-of-distribution Generalizatio
        21117, -- 2310.00035 LoRA ensembles for large language model fine-tuning
        21129, -- 2310.00165 SCoRe: Submodular Combinatorial Representation Learning
        21195, -- 2310.00847 Can Pre-trained Networks Detect Familiar Out-of-Distribution Data?
        21265, -- 2310.01542 Fusing Models with Complementary Expertise
        21372, -- 2310.02642 GET: Group Event Transformer for Event-Based Vision
        21485, -- 2310.03937 Diffusion Models as Masked Audio-Video Learners
        21539, -- 2310.04722 A Holistic Evaluation of Piano Sound Quality
        21605, -- 2310.05348 Continuous Invariance Learning
        21916, -- 2310.08598 Domain Generalization for Medical Image Analysis: A Review
        21932, -- 2310.08847 On the Over-Memorization During Natural, Robust and Catastrophic Overfittin
        22336, -- 2310.14192 PromptMix: A Class Boundary Augmentation Method for Large Language Model Di
        22369, -- 2310.14577 DeCrisisMB: Debiased Semi-Supervised Learning for Crisis Tweet Classificati
        22370, -- 2310.14583 JointMatch: A Unified Approach for Diverse and Collaborative Pseudo-Labelin
        22373, -- 2310.14627 CrisisMatch: Semi-Supervised Few-Shot Learning for Fine-Grained Disaster Tw
        22533, -- 2310.16483 Gramian Attention Heads are Strong yet Efficient Vision Learners
        22701, -- 2310.18653 Feature Guided Masked Autoencoder for Self-supervised Learning in Remote Se
        22733, -- 2310.19168 BirdSAT: Cross-View Contrastive Masked Autoencoders for Bird Species Classi
        22775, -- 2310.19795 SimMMDG: A Simple and Effective Framework for Multi-modal Domain Generaliza
        22912, -- 2311.01441 Distilling Out-of-Distribution Robustness from Vision-Language Foundation M
        22927, -- 2311.01723 Towards Calibrated Robust Fine-Tuning of Vision-Language Models
        23106, -- 2311.05014 Interpreting Pretrained Language Models via Concept Bottlenecks
        23141, -- 2311.05613 Window Attention is Bugged: How not to Interpolate Position Embeddings
        23147, -- 2311.05698 Mirasol3B: A Multimodal Autoregressive model for time-aligned and contextua
        23299, -- 2311.08298 A Survey of Confidence Estimation and Calibration in Large Language Models
        23521, -- 2311.11278 Transcending Forgery Specificity with Latent Space Augmentation for General
        23927, -- 2311.17132 TransNeXt: Robust Foveal Visual Perception for Vision Transformers
        24027, -- 2311.18508 DifAugGAN: A Practical Diffusion-style Data Augmentation for GAN-based Sing
        24058, -- 2311.18823 Initializing Models with Larger Ones
        24130, -- 2312.00718 Removing Biases from Molecular Representations via Information Maximization
        24240, -- 2312.02151 Guarding Barlow Twins Against Overfitting with Mixed Samples
        24306, -- 2312.02923 MoSA: Mixture of Sparse Adapters for Visual Efficient Tuning
        24456, -- 2312.04548 Multiview Aerial Visual Recognition (MAVREC): Can Multi-view Improve Aerial
        24612, -- 2312.06647 4M: Massively Multimodal Masked Modeling
        24686, -- 2312.07439 BIRB: A Generalization Benchmark for Information Retrieval in Bioacoustics
        24765, -- 2312.08846 TiMix: Text-aware Image Mixing for Effective Vision-Language Pre-training
        24772, -- 2312.08874 Agent Attention: On the Integration of Softmax and Linear Attention
        24835, -- 2312.09578 Self-Supervised Learning for Anomalous Sound Detection
        24856, -- 2312.10105 SeiT++: Masked Token Modeling Improves Storage-efficient Training
        24860, -- 2312.10144 Data-Efficient Multimodal Fusion on a Single GPU
        24867, -- 2312.10193 Adaptive Computation Modules: Granular Conditional Computation For Efficien
        25076, -- 2312.13714 Bootstrap Masked Visual Modeling via Hard Patches Mining
        25111, -- 2312.14216 DreamDistribution: Learning Prompt Distribution for Diverse In-distribution
        25169, -- 2312.15297 Make Me a BNN: A Simple Strategy for Estimating Bayesian Uncertainty from P
        25309, -- 2312.17473 FerKD: Surgical Label Adaptation for Efficient Distillation
        25326, -- 2312.17742 Learning Vision from Models Rivals Learning Vision from Data
        25444, -- 2401.01830 Iterative Mask Filling: An Effective Text Augmentation Method Using Masked
        25448, -- 2401.01862 A Vision Check-up for Language Models
        25462, -- 2401.02020 Spikformer V2: Join the High Accuracy Club on ImageNet with an SNN Ticket
        25554, -- 2401.03497 EAT: Self-Supervised Pre-Training with Efficient Audio Transformer
        25570, -- 2401.03844 Fully Attentional Networks with Self-emerging Token Labeling
        25787, -- 2401.06913 Microphone Conversion: Mitigating Device Variability in Sound Event Classif
        25874, -- 2401.08541 Scalable Pre-training of Large Autoregressive Image Models
        25998, -- 2401.10150 Motion-Zero: Zero-Shot Moving Object Control Framework for Diffusion-Based
        26304, -- 2401.14391 Rethinking Patch Dependence for Masked Autoencoders
        26308, -- 2401.14404 Deconstructing Denoising Diffusion Models for Self-Supervised Learning
        26339, -- 2401.14846 Understanding Domain Generalization: A Noise Robustness Perspective
        26440, -- 2401.16438 Do deep neural networks utilize the weight space efficiently?
        26446, -- 2401.16456 SHViT: Single-Head Vision Transformer with Memory Efficient Macro Design
        26470, -- 2401.16803 PBSCR: The Piano Bootleg Score Composer Recognition Dataset
        26540, -- 2401.17992 Multilinear Operator Networks
        26578, -- 2402.00645 Spectrally Transformed Kernel Regression
        26732, -- 2402.02047 Calibration and Correctness of Language Models for Code
        26820, -- 2402.03119 Good Teachers Explain: Explanation-Enhanced Knowledge Distillation
        27045, -- 2402.05584 AutoAugment Is What You Need: Enhancing Rule-based Augmentation Methods in
        27085, -- 2402.05964 A Survey on Transformer Compression
        27205, -- 2402.07785 HYPO: Hyperspherical Out-of-Distribution Generalization
        27308, -- 2402.09141 Advancing NLP Models with Strategic Text Augmentation: A Comprehensive Stud
        27316, -- 2402.09240 Switch EMA: A Free Lunch for Better Flatness and Sharpness
        27346, -- 2402.09748 Model Compression and Efficient Inference for Large Language Models: A Surv
        27519, -- 2402.11566 Boosting Semi-Supervised 2D Human Pose Estimation by Revisiting Data Augmen
        27833, -- 2402.14789 Self-Guided Masked Autoencoders for Domain-Agnostic Self-Supervised Learnin
        28044, -- 2402.17300 VoCo: A Simple-yet-Effective Volume Contrastive Learning Framework for 3D M
        28201, -- 2402.19305 HyenaPixel: Global Image Context with Convolutions
        28219, -- 2403.00025 On the Challenges and Opportunities in Generative AI
        28244, -- 2403.00522 VisionLLaMA: A Unified LLaMA Backbone for Vision Tasks
        28503, -- 2403.04272 Active Generalized Category Discovery
        28630, -- 2403.06213 $V_kD:$ Improving Knowledge Distillation using Orthogonal Projections
        28680, -- 2403.06925 Simplicity Bias of Transformers to Learn Low Sensitivity Functions
        28707, -- 2403.07329 Unknown Domain Inconsistency Minimization for Domain Generalization
        28806, -- 2403.08819 Thermometer: Towards Universal Calibration for Large Language Models
        28844, -- 2403.09274 EventRPG: Event Data Augmentation with Relevance Propagation Guidance
        28899, -- 2403.09977 EfficientVMamba: Atrous Selective Scan for Light Weight Visual Mamba
        28901, -- 2403.10030 Multi-criteria Token Fusion with One-step-ahead Attention for Efficient Vis
        28924, -- 2403.10380 BirdSet: A Large-Scale Dataset for Audio Classification in Avian Bioacousti
        28930, -- 2403.10476 Approximate Nullspace Augmented Finetuning for Robust Vision Transformers
        28961, -- 2403.10911 Efficient Diffusion-Driven Corruption Editor for Test-Time Adaptation
        29053, -- 2403.11999 HIRI-ViT: Scaling Vision Transformer with High Resolution Inputs
        29112, -- 2403.12687 Audio-Visual Compound Expression Recognition Method based on Late Modality
        29293, -- 2403.14715 Towards Understanding Why Label Smoothing Degrades Selective Classification
        29300, -- 2403.14790 Latent Diffusion Models for Attribute-Preserving Image Anonymization
        29312, -- 2403.15042 LLM2LLM: Boosting LLMs with Novel Iterative Data Enhancement
        29372, -- 2403.15835 Once for Both: Single Stage of Importance and Sparsity Search for Vision Tr
        29400, -- 2403.16365 Generating Potent Poisons and Backdoors from Scratch with Guided Diffusion
        29476, -- 2403.17695 PlainMamba: Improving Non-Hierarchical Mamba in Visual Recognition
        29537, -- 2403.18361 ViTAR: Vision Transformer with Any Resolution
        29616, -- 2403.19522 Model Stock: All we need is just a few fine-tuned models
        29620, -- 2403.19588 DenseNets Reloaded: Paradigm Shift Beyond ResNets and ViTs
        29645, -- 2403.19888 MambaMixer: Efficient Selective State Space Models with Dual Token and Chan
        29653, -- 2403.19967 Rewrite the Stars
        29655, -- 2403.20012 Colorful Cutout: Enhancing Image Data Augmentation with Curriculum Learning
        29700, -- 2404.00438 Communication Efficient Distributed Training with Distributed Lion
        29725, -- 2404.00648 SpiralMLP: A Lightweight Vision MLP Architecture
        29878, -- 2404.02544 Semi-Supervised Unconstrained Head Pose Estimation in the Wild
        29904, -- 2404.02900 DeiT-LT Distillation Strikes Back for Vision Transformer Training on Long-T
        30166, -- 2404.06773 Adapting LLaMA Decoder to Vision Transformer
        30230, -- 2404.07773 ConsistencyDet: A Few-step Denoising Framework for Object Detection Using t
        30418, -- 2404.10518 MobileNetV4 - Universal Models for the Mobile Ecosystem
        30619, -- 2404.13648 Data-independent Module-aware Pruning for Hierarchical Vision Transformers
        30845, -- 2404.17768 Changing the Training Data Distribution to Reduce Simplicity Bias Improves
        30927, -- 2404.19438 Neuro-Vision to Language: Enhancing Brain Recording-based Visual Reconstruc
        31055, -- 2405.02296 Möbius Transform for Mitigating Perspective Distortions in Representation L
        31058, -- 2405.02363 LLM as Dataset Analyst: Subpopulation Structure Discovery with Large Langua
        31265, -- 2405.07992 MambaOut: Do We Really Need Mamba for Vision?
        31322, -- 2405.09487 Color Space Learning for Cross-Color Person Re-Identification
        31480, -- 2405.12969 Can We Treat Noisy Labels as Accurate?
        31549, -- 2405.13985 LookHere: Vision Transformers with Directed Attention Generalize and Extrap
        31585, -- 2405.14458 YOLOv10: Real-Time End-to-End Object Detection
        31672, -- 2405.15239 Brain3D: Generating 3D Objects from fMRI
        31756, -- 2405.16339 BOLD: Boolean Logic Deep Learning
        31791, -- 2405.16727 Disentangling and Integrating Relational and Sensory Information in Transfo
        31840, -- 2405.17382 ReMoDetect: Reward Models Recognize Aligned LLM's Generations
        31848, -- 2405.17419 MultiOOD: Scaling Out-of-Distribution Detection for Multiple Modalities
        31919, -- 2405.18148 Learning to Detour: Shortcut Mitigating Augmentation for Weakly Supervised
        31927, -- 2405.18240 MSPE: Multi-Scale Patch Embedding Prompts Vision Transformers to Any Resolu
        32275, -- 2406.02032 M2D-CLAP: Masked Modeling Duo Meets CLAP for Learning General-purpose Audio
        32371, -- 2406.03345 Feature Contamination: Neural Networks Learn Uncorrelated Features and Fail
        32379, -- 2406.03459 LW-DETR: A Transformer Replacement to YOLO for Real-Time Detection
        32430, -- 2406.04221 Matching Anything by Segmenting Anything
        32445, -- 2406.04303 Vision-LSTM: xLSTM as Generic Vision Backbone
        32466, -- 2406.04370 Large Language Model Confidence Estimation via Black-Box Access
        32623, -- 2406.06384 Generalizing to Unseen Domains in Diabetic Retinopathy with Disentangled Re
        32791, -- 2406.08249 Dataset Enhancement with Instance-Level Augmentations
        32899, -- 2406.09406 4M-21: An Any-to-Any Vision Model for Tens of Tasks and Modalities
        32905, -- 2406.09415 An Image is Worth More Than 16x16 Patches: Exploring Transformers on Indivi
        33011, -- 2406.10724 Beyond the Visible: Jointly Attending to Spectral and Spatial Dimensions wi
        33148, -- 2406.11739 V3Det Challenge 2024 on Vast Vocabulary and Open Vocabulary Object Detectio
        33376, -- 2406.14129 Towards Event-oriented Long Video Understanding
        33660, -- 2406.17536 MedMNIST-C: Comprehensive benchmark and improved classifier robustness by s
        34149, -- 2407.03893 Do Generalised Classifiers really work on Human Drawn Sketches?
        34223, -- 2407.04797 Revealing the Utilized Rank of Subspaces of Learning in Neural Networks
        34269, -- 2407.05528 An accurate detection is not all you need to combat label noise in web-nois
        34410, -- 2407.07341 A Guide To Effectively Leveraging LLMs for Low-Resource Text Summarization:
        34426, -- 2407.07582 TIP: Tabular-Image Pre-training for Multimodal Classification with Incomple
        34497, -- 2407.08567 Adaptive Parametric Activation
        34533, -- 2407.08966 LAPT: Label-driven Automated Prompt Tuning for OOD Detection with Vision-La
        34674, -- 2407.10910 DataDream: Few-shot Guided Dataset Generation
        34728, -- 2407.11401 EndoFinder: Online Image Retrieval for Explainable Colorectal Polyp Diagnos
        34828, -- 2407.12665 Beyond Next Token Prediction: Patch-Level Training for Large Language Model
        34874, -- 2407.12997 Multi-Iteration Multi-Stage Fine-Tuning of Transformers for Sound Event Det
        34987, -- 2407.14726 MetaAug: Meta-Data Augmentation for Post-Training Quantization
        35043, -- 2407.15447 SIGMA:Sinkhorn-Guided Masked Video Modeling
        35243, -- 2407.18899 Learn from the Learnt: Source-Free Active Domain Adaptation via Contrastive
        35654, -- 2408.04224 Cross-View Meets Diffusion: Aerial Image Synthesis with Geometry and Text G
        35716, -- 2408.05446 Ensemble everything everywhere: Multi-scale aggregation for adversarial rob
        35790, -- 2408.06779 ED$^4$: Explicit Data-level Debiasing for Deepfake Detection
        35802, -- 2408.06927 Breaking Class Barriers: Efficient Dataset Distillation via Inter-Class Fea
        35848, -- 2408.07832 LADDER: Language Driven Slice Discovery and Error Rectification
        35870, -- 2408.08201 Heavy Labels Out! Dataset Distillation with Label Space Lightening
        36030, -- 2408.10940 A Closer Look at Data Augmentation Strategies for Finetuning-Based Low/Few-
        36071, -- 2408.11338 Automatic Dataset Construction (ADC): Sample Collection, Data Curation, and
        36184, -- 2408.13351 SeA: Semantic Adversarial Augmentation for Last Layer Features from Unsuper
        36227, -- 2408.14080 SONICS: Synthetic Or Not - Identifying Counterfeit Songs
        36360, -- 2408.16266 Inversion Circle Interpolation: Diffusion-based Image Augmentation for Data
        36408, -- 2408.17081 Stochastic Layer-Wise Shuffle: A Good Practice to Improve Vision Mamba Trai
        36598, -- 2409.03137 The AdEMAMix Optimizer: Better, Faster, Older
        36878, -- 2409.09305 The T05 System for The VoiceMOS Challenge 2024: Transfer Learning from Deep
        36898, -- 2409.09546 Effective Pre-Training of Audio Transformers for Sound Event Detection
        36951, -- 2409.10594 Kolmogorov-Arnold Transformer
        37112, -- 2409.13213 MalMixer: Few-Shot Malware Classification with Retrieval-Augmented Semi-Sup
        37438, -- 2409.18877 UniEmoX: Cross-modal Semantic-Guided Large-Scale Pretraining for Universal
        37503, -- 2409.19774 Crafting Distribution Shifts for Validation and Training in Single Source D
        37902, -- 2410.03755 Denoising with a Joint-Embedding Predictive Architecture
        38117, -- 2410.06373 Unveiling the Backbone-Optimizer Coupling Bias in Visual Representation Lea
        38335, -- 2410.09101 Data Taggants: Dataset Ownership Verification via Harmless Targeted Data Po
        38502, -- 2410.11087 Locality Alignment Improves Vision-Language Models
        38565, -- 2410.11842 MoH: Multi-Head Attention as Mixture-of-Head Attention
        38671, -- 2410.13136 Unlocking the Capabilities of Masked Generative Models for Image Synthesis
        39087, -- 2410.18322 Unified Microphone Conversion: Many-to-Many Device Mapping via Feature-wise
        39136, -- 2410.18857 Probabilistic Language-Image Pre-Training
        39139, -- 2410.18889 Are LLMs Better than Reported? Detecting Label Errors and Mitigating Their
        39324, -- 2410.21897 Semi-Supervised Self-Learning Enhanced Music Emotion Recognition
        39455, -- 2410.24116 AIDOVECL: AI-generated Dataset of Outpainted Vehicles for Eye-level Classif
        39752, -- 2411.04967 AsCAN: Asymmetric Convolution-Attention Networks for Efficient Recognition
        39843, -- 2411.06399 PSELDNets: Pre-trained Neural Networks on Large-scale Synthetic Datasets fo
        39916, -- 2411.07635 Breaking the Low-Rank Dilemma of Linear Attention
        40015, -- 2411.09702 On the Surprising Effectiveness of Attention Transfer for Vision Transforme
        40251, -- 2411.14201 Regional Attention for Shadow Removal
        40336, -- 2411.15241 EfficientViM: Efficient Vision Mamba with Hidden State Mixer based State Sp
        40394, -- 2411.15941 MobileMamba: Lightweight Multi-Receptive Visual Mamba Network
        40797, -- 2412.00927 VISTA: Enhancing Long-Duration and High-Resolution Video Understanding by V
        40800, -- 2412.00965 Token Cropr: Faster ViTs for Quite a Few Tasks
        40869, -- 2412.01876 Understanding Bias in Large-Scale Visual Datasets
        40902, -- 2412.02366 GenMix: Effective Data Augmentation with Generative Diffusion Model Image E
        41044, -- 2412.04234 DEIM: DETR with Improved Matching for Fast Convergence
        41238, -- 2412.06590 Bridging the Divide: Reconsidering Softmax and Linear Attention
        41242, -- 2412.06674 EMOv2: Pushing 5M Vision Model Frontier
        41258, -- 2412.06787 [MASK] is All You Need
        41592, -- 2412.10995 RapidNet: Multi-Level Dilated Convolution Based Mobile Backbone
        41997, -- 2412.16146 Mamba2D: A Natively Multi-Dimensional State-Space Model for Vision Tasks
        42229, -- 2412.19531 Is Your Text-to-Image Model Robust to Caption Noise?
        42635, -- 2501.04765 TREAD: Token Routing for Efficient Architecture-agnostic Diffusion Training
        42666, -- 2501.05272 Solving the Catastrophic Forgetting Problem in Generalized Category Discove
        43726, -- 2502.03654 Gompertz Linear Units: Leveraging Asymmetry for Enhanced Learning Dynamics
        44058, -- 2502.07837 RoboBERT: An End-to-end Multimodal Robotic Manipulation Model
        44458, -- 2502.12524 YOLOv12: Attention-Centric Real-Time Object Detectors
        44965, -- 2502.17771 Sample Selection via Contrastive Fragmentation for Noisy Label Regression
        45237, -- 2503.00147 Precise Event Spotting in Sports Videos: Solving Long-Range Dependency and
        45554, -- 2503.04626 IDInit: A Universal and Stable Initialization Method for Neural Network Tra
        45958, -- 2503.09399 ForAug: Recombining Foregrounds and Backgrounds to Improve Vision Transform
        46394, -- 2503.15417 Temporal Regularization Makes Your Video Generator Stronger
        46465, -- 2503.16212 MathFusion: Enhancing Mathematic Problem-solving of LLM through Instruction
        46475, -- 2503.16311 Structured-Noise Masked Modeling for Video, Audio and Beyond
        46617, -- 2503.18267 Enhancing Dataset Distillation via Non-Critical Region Refinement
        46985, -- 2503.23135 LSNet: See Large, Focus Small
        47051, -- 2503.24057 AMMSM: Adaptive Motion Magnification and Sparse Mamba for Micro-Expression
        47103, -- 2504.00527 SMILE: Infusing Spatial and Motion Semantics in Masked Video Learning
        47113, -- 2504.00711 GraphMaster: Automated Graph Synthesis via LLM Agents in Data-Limited Envir
        47383, -- 2504.05301 S^4M: Boosting Semi-Supervised Instance Segmentation with SAM
        47505, -- 2504.07835 Pychop: Emulating Low-Precision Arithmetic in Numerical Methods and Neural
        47770, -- 2504.11749 SkeletonX: Data-Efficient Skeleton-based Action Recognition via Cross-sampl
        47842, -- 2504.12880 Can Masked Autoencoders Also Listen to Birds?
        48019, -- 2504.15404 Context Aware Grounded Teacher for Source Free Object Detection
        48473, -- 2505.03991 Action Spotting and Precise Event Detection in Sports: Datasets, Methods, a
        48557, -- 2505.05741 Dome-DETR: DETR with Density-Oriented Feature-Query Manipulation for Effici
        49095, -- 2505.13813 FlashKAT: Understanding and Addressing Performance Bottlenecks in the Kolmo
        49474, -- 2505.16985 Extremely Simple Multimodal Outlier Synthesis for Out-of-Distribution Detec
        49691, -- 2505.19147 Shifting AI Efficiency From Model-Centric to Data-Centric Compression
        50099, -- 2505.23325 Dimension-Reduction Attack! Video Generative Models are Experts on Controll
        50210, -- 2505.24216 Shuffle PatchMix Augmentation with Confidence-Margin Weighted Pseudo-Labels
        50440, -- 2506.02294 Improving Knowledge Distillation Under Unknown Covariate Shift Through Conf
        50738, -- 2506.06905 Meta-Adaptive Prompt Distillation for Few-Shot Visual Question Answering
        51469, -- 2506.20609 Deciphering GunType Hierarchy through Acoustic Analysis of Gunshot Recordin
        51950, -- 2507.13089 GLAD: Generalizable Tuning for Vision-Language Models
        52159, -- 2508.01226 CM$^3$: Calibrating Multimodal Recommendation
        52755, -- 2509.09926 LoFT: Parameter-Efficient Fine-Tuning for Long-tailed Semi-Supervised Learn
        52910, -- 2509.15709 Understanding Embedding Scaling in Collaborative Filtering
        52981, -- 2509.20787 Real-Time Object Detection Meets DINOv3
        53214, -- 2510.00658 Align Your Tangent: Training Better Consistency Models via Manifold-Aligned
        53403, -- 2509.24797 Fidelity-Aware Data Composition for Robust Robot Generalization
        53507, -- 2510.12798 Detect Anything via Next Point Prediction
        53519, -- 2510.12225 HoneyBee: Data Recipes for Vision-Language Reasoners
        54008, -- 2510.24078 Beyond Objects: Contextual Synthetic Data Generation for Fine-Grained Class
        54436, -- 2511.22265 FedRE: A Representation Entanglement Framework for Model-Heterogeneous Fede
        54717, -- 2512.10938 Stronger Normalization-Free Transformers
        54865, -- 2512.16922 Next-Embedding Prediction Makes Strong Vision Learners
        55051, -- 2512.24176 Guiding a Diffusion Transformer with the Internal Dynamics of Itself
        56441, -- 2603.02667 DREAM: Where Visual Understanding Meets Text-to-Image Generation
        56496, -- 2603.04892 Locality-Attending Vision Transformer
        56687, -- 2602.24181 A Mixed Diet Makes DINO An Omnivorous Vision Encoder
        57249, -- 2604.03993 Can LLMs Learn to Reason Robustly under Noisy Supervision?
        58295, -- 2512.08217 Correction of Decoupled Weight Decay
        58772, -- 2603.28315 Prototype-Enhanced Multi-View Learning for Thyroid Nodule Ultrasound Classi
        59146, -- 2603.18739 EdgeCrafter: Compact ViTs for Edge Dense Prediction via Task-Specialized Di
        60010, -- 2603.02181 Leveraging Model Soups to Classify Intangible Cultural Heritage Images from
        60275, -- 2602.22073 AdaSpot: Spend Resolution Where It Matters for Precise Event Spotting
        61363, -- 2602.03123 Beyond Cropping and Rotation: Automated Evolution of Powerful Task-Specific
        61370, -- 2602.03039 HP-GAN: Harnessing pretrained networks for GAN improvement with FakeTwins a
        61492, -- 2602.03879 TruKAN: Towards More Efficient Kolmogorov-Arnold Networks Using Truncated P
        61519, -- 2602.01418 Where to Attend: A Principled Vision-Centric Position Encoding with Parabol
        61827, -- 2601.21612 Representation-Regularized Convolutional Audio Transformer for Audio Unders
        62177, -- 2602.00084 Why LoRA Resists Label Noise: A Theoretical Framework for Noise-Robust Para
        62374, -- 2507.16559 Comparative validation of surgical phase recognition, instrument keypoint e
        64493, -- 2511.21032 A Probabilistic Framework for Temporal Distribution Generalization in Indus
        64563, -- 2511.19963 MambaEye: A Size-Agnostic Visual Encoder with Causal Sequential Processing
        64649, -- 2511.19718 Rethinking Vision Transformer Depth via Structural Reparameterization
        64895, -- 2511.14111 CascadedViT: Cascaded Chunk-FeedForward and Cascaded Group Attention Vision
        65112, -- 2511.11698 Moirai 2.0: When Less Is More for Time Series Forecasting
        65315, -- 2511.04914 MERaLiON-SER: Robust Speech Emotion Recognition Model for English and SEA L
        65340, -- 2511.04394 DORAEMON: A Unified Library for Visual Object Modeling and Representation L
        65659, -- 2510.25955 SPEAR: A Unified SSL Framework for Learning Speech and Audio Representation
        65677, -- 2510.25480 Gradient-Weight Alignment as a Train-Time Proxy for Generalization in Class
        65901, -- 2510.21585 REVE: A Foundation Model for EEG - Adapting to Any Setup with Large-Scale
        68474, -- 2509.10005 TUNI: Real-time RGB-T Semantic Segmentation with Unified Multi-Modal Featur
        68516, -- 2509.08959 CoSwin: Convolution Enhanced Hierarchical Shifted Window Attention For Smal
        68872, -- 2509.01439 SoccerHigh: A Benchmark Dataset for Automatic Soccer Video Summarization
        68947, -- 2509.00549 A Modality-agnostic Multi-task Foundation Model for Human Brain Imaging
        68986, -- 2508.21712 FLORA: Efficient Synthetic Data Generation for Object Detection in Low-Data
        69421, -- 2508.14588 Controllable Latent Space Augmentation for Digital Pathology
        69616, -- 2508.11464 Data-Driven Deepfake Image Detection Method - The 2024 Global Deepfake Ima
        69759, -- 2508.09550 Exploring the Equivalence of Closed-Set Generative and Real Data Augmentati
        69996, -- 2508.06098 MeanAudio: Fast and Faithful Text-to-Audio Generation with Mean Flows
        70138, -- 2508.04143 Multilingual Source Tracing of Speech Deepfakes: A First Benchmark
        70228, -- 2508.03091 T2UE: Generating Unlearnable Examples from Text Descriptions
        70379, -- 2508.01148 DisTaC: Conditioning Task Vectors via Distillation for Robust Model Merging
        70525, -- 2508.06517 Frequency Prior Guided Matching: A Data Augmentation Approach for Generaliz
        70714, -- 2507.19409 Modality Agnostic Efficient Long Range Encoder
        71124, -- 2507.11040 Combining Transformers and CNNs for Efficient Object Detection in High-Reso
        71682, -- 2506.22389 Towards Distributed Neural Architectures
        71870, -- 2506.16073 TD3Net: A Temporal Densely Connected Multi-Dilated Convolutional Network fo
        71875, -- 2506.15940 Polyline Path Masked Attention for Vision Transformer
        71913, -- 2506.15051 Sequential Policy Gradient for Adaptive Hyperparameter Optimization
        72515, -- 2505.24361 Revisiting Cross-Modal Knowledge Distillation: A Disentanglement Approach f
        72672, -- 2505.21574 Do We Need All the Synthetic Data? Towards Targeted Synthetic Image Augment
        72767, -- 2505.18608 Spiking Neural Networks Need High Frequency Information
        73281, -- 2504.19742 EcoWikiRS: Learning Ecological Representation of Satellite Images from Weak
        73478, -- 2504.12088 AttentionDrop: A Novel Regularization Method for Transformer Models
        73541, -- 2504.09491 DropoutGS: Dropping Out Gaussians for Better Sparse-view Rendering
        73592, -- 2412.11943 autrainer: A Modular and Extensible Deep Learning Toolkit for Computer Audi
        73594, -- 2504.07288 MDIT: A Model-free Data Interpolation Method for Diverse Instruction Tuning
        73814, -- 2503.23447 CA^2ST: Cross-Attention in Audio, Space, and Time for Holistic Video Recogn
        73865, -- 2503.19916 EventFly: Event Camera Perception from Ground to the Sky
        73937, -- 2503.16975 EasyRobust: A Comprehensive and Easy-to-use Toolkit for Robust and Generali
        74018, -- 2503.13743 MonoCT: Overcoming Monocular 3D Detection Domain Shift with Consistent Teac
        74313, -- 2503.02138 Elliptic Loss Regularization
        74717, -- 2502.08960 A Comprehensive Survey on Imbalanced Data Learning
        74777, -- 2502.06434 Rethinking Large-scale Dataset Compression: Shifting Focus From Labels to I
        74785, -- 2502.06209 Enhancing Cost Efficiency in Active Learning with Candidate Set Query
        75304, -- 2501.01855 UAV-DETR: Efficient End-to-End Object Detection for Unmanned Aerial Vehicle
        75493, -- 2412.09758 Toward Foundation Model for Multivariate Wearable Sensing of Physiological
        75712, -- 2411.16170 CARE Transformer: Mobile-Friendly Linear Visual Transformer via Decoupled D
        75880, -- 2411.01494 Finding NeMo: Negative-mined Mosaic Augmentation for Referring Image Segmen
        75928, -- 2411.02592 Decoupled Data Augmentation for Improving Image Classification
        76136, -- 2410.05500 Residual Kolmogorov-Arnold Network for Enhanced Deep Learning
        76209, -- 2410.01638 Data Extrapolation for Text-to-image Generation on Small Datasets
        76520, -- 2408.13920 Wav2Small: Distilling Wav2Vec2 to 72K parameters for Low-Resource Speech em
        76679, -- 2408.05337 VACoDe: Visual Augmented Contrastive Decoding
        76902, -- 2406.17254 Scalp Diagnostic System With Label-Free Segmentation and Training-Free Imag
        76931, -- 2406.14850 DExter: Learning and Controlling Performance Expression with Diffusion Mode
        76953, -- 2406.12471 Fighting Randomness with Randomness: Mitigating Optimisation Instability of
        77051, -- 2406.05850 Scaling Graph Convolutions for Mobile Vision
        77191, -- 2306.01743 Unicode Normalization and Grapheme Parsing of Indic Languages
        77303, -- 2405.05258 Multi-Modal Data-Efficient 3D Scene Understanding for Autonomous Driving
        77482, -- 2312.07526 RTMO: Towards High-Performance One-Stage Real-Time Multi-Person Pose Estima
        77575, -- 2403.16913 New Intent Discovery with Attracting and Dispersing Prototype
        78027, -- 2312.17526 Noise-free Optimization in Early Training Steps for Image Super-Resolution
        78310, -- 2310.18640 Switching Temporary Teachers for Semi-Supervised Semantic Segmentation
        78335, -- 2310.15648 Dynamic Convolutional Neural Networks as Efficient Pre-trained Audio Models
        78371, -- 2310.09761 CAPro: Webly Supervised Learning with Cross-Modality Aligned Prototypes
        78455, -- 2309.16418 Efficient Supervised Training of Audio Transformers for Music Representatio
        78531, -- 2309.07615 Multilingual Audio Captioning using machine translated data
        78579, -- 2309.00454 CoNeTTE: An efficient Audio Captioning system leveraging multiple datasets
        78618, -- 2308.11957 CED: Consistent ensemble distillation for audio tagging
        78755, -- 2307.07837 Can Pre-Trained Text-to-Image Models Generate Visual Goals for Reinforcemen
        78861, -- 2306.14132 DiffMix: Diffusion Model-based Data Synthesis for Nuclei Segmentation and C
        78940, -- 2306.00830 Adapting a ConvNeXt model to audio classification on AudioSet
        78993, -- 2305.14851 Sharpness-Aware Data Poisoning Attack
        79015, -- 2305.12715 Imprecise Label Learning: A Unified Framework for Learning with Various Imp
        79073, -- 2305.01482 Multitask learning in Audio Captioning: a sentence embedding regression los
        79077, -- 2305.01134 PGrad: Learning Principal Gradients For Domain Generalization
        79084, -- 2304.14636 PreNAS: Preferred One-Shot Learning Towards Efficient Neural Architecture S
        79256, -- 2303.07626 CAT: Causal Audio Transformer for Audio Classification
        79474, -- 2212.10766 Class Prototype-based Cleaner for Label Noise Learning
        79534, -- 2211.13929 XKD: Cross-modal Knowledge Distillation with Domain Alignment for Video Rep
        79550, -- 2211.12080 Robust Training for Speaker Verification against Noisy Labels
        79600, -- 2211.02733 GLOBEM Dataset: Multi-Year Datasets for Longitudinal Human Behavior Modelin
        79614, -- 2211.00453 The Perils of Learning From Unlabeled Data: Backdoor Attacks on Semi-superv
        79626, -- 2210.14493 AVES: Animal Vocalization Encoder based on Self-Supervision
        79636, -- 2210.13067 10 hours data is all you need
        79639, -- 2210.12300 BEANS: The Benchmark of Animal Sounds
        79695, -- 2210.01189 Rank-N-Contrast: Learning Continuous Representations for Regression
        79743, -- 2209.06589 Towards Better Generalization with Flexible Representation of Multi-Module
        79776, -- 2208.11434 YOLOPv2: Better, Faster, Stronger for Panoptic Driving Perception
        79791, -- 2208.05573 Data Augmentation for Improving Emotion Recognition in Software Engineering
        80040, -- 2204.11205 EPiDA: An Easy Plug-in Data Augmentation Framework for High Performance Tex
        80063, -- 2204.06812 Learning to Generalize to More: Continuous Semantic Augmentation for Neural
        80067, -- 2204.06355 Local Feature Swapping for Generalization in Reinforcement Learning
        80144, -- 2203.06915 SimMatch: Semi-supervised Learning with Similarity Matching
        80223, -- 2202.02200 Learning with Neighbor Consistency for Noisy Labels
        80262, -- 2201.04288 Multiview Transformers for Video Recognition
        80356, -- 2111.15121 Pyramid Adversarial Training Improves ViT Performance
        80367, -- 2111.12993 PolyViT: Co-training Vision Transformers on Images, Videos and Audio
        80382, -- 2111.10493 Discrete Representations Strengthen Vision Transformer Robustness
        80404, -- 2111.04433 RawBoost: A Raw Data Boosting and Augmentation Method applied to Automatic
        80419, -- 2102.08604 SWAD: Domain Generalization by Seeking Flat Minima
        80438, -- 2103.13279 FakeMix Augmentation Improves Transparent Object Detection
        80682, -- 2104.10858 All Tokens Matter: Token Labeling for Training Better Vision Transformers
        80871, -- 2102.10106 Mine Your Own vieW: Self-Supervised Learning Through Across-Sample Predicti
        80876, -- 2102.09554 Delving into Deep Imbalanced Regression
        80878, -- 2102.09480 Unbiased Teacher for Semi-Supervised Object Detection
        80976, -- 2012.04462 Multi-Objective Interpolation Training for Robustness to Label Noise
        82831, -- 2605.01711 Linear-Time Global Visual Modeling without Explicit Attention
        83973, -- 2410.07547 Rethinking SNN Online Training and Deployment: Gradient-Coherent Learning v
        84070, -- 2508.03081 Contrastive Cross-Bag Augmentation for Multiple Instance Learning-based Who
        84306, -- 2512.01643 ViT$^3$: Unlocking Test-Time Training in Vision
        84356, -- 2512.06358 Rectifying Latent Space for Generative Single-Image Reflection Removal
        84470, -- 2601.08617 SoC: Semantic Orthogonal Calibration for Test-Time Prompt Tuning
        84575, -- 2602.20412 SimLBR: Learning to Detect Fake Images by Learning to Detect Real Images
        84664, -- 2603.00486 Random Wins All: Rethinking Grouping Strategies for Vision Tokens
        84708, -- 2603.02200 Adaptive Confidence Regularization for Multimodal Failure Detection
        84888, -- 2603.12997 Deconstructing the Failure of Ideal Noise Correction: A Three-Pillar Diagno
        85142, -- 2603.26179 Consistency Beyond Contrast: Enhancing Open-Vocabulary Object Detection Rob
        85190, -- 2603.28182 A Closer Look at Cross-Domain Few-Shot Object Detection: Fine-Tuning Matter
        85255, -- 2604.02946 Learning from Synthetic Data via Provenance-Based Input Gradient Guidance
        85261, -- 2604.03454 RDFace: A Benchmark Dataset for Rare Disease Facial Image Analysis under Ex
        85412, -- 2604.17914 Beyond Binary Contrast: Modeling Continuous Skeleton Action Spaces with Tra
        85439, -- 2604.21330 Teacher-Guided Routing for Sparse Vision Mixture-of-Experts
        85618, -- 2201.13192 Uncertainty-aware Pseudo-label Selection for Positive-Unlabeled Learning
        85690, -- 2504.16109 Representation Learning for Tabular Data: A Comprehensive Survey
        85820, -- 2505.23663 AMBER: Adaptive Mesh Generation by Iterative Mesh Resolution Prediction
        85859, -- 2502.09564 Diffusing DeBias: Synthetic Bias Amplification for Model Debiasing
        85873, -- 2506.04906 TRACE: Contrastive learning for multi-trial time series data in neuroscienc
        85955, -- 2505.00812 Handling Label Noise via Instance-Level Difficulty Modeling and Dynamic Opt
        86039, -- 2506.23863 Puzzles: Unbounded Video-Depth Augmentation for Scalable End-to-End 3D Reco
        86487, -- 2509.11711 The Quest for Universal Master Key Filters in DS-CNNs
        86533, -- 2503.11544 AugGen: Synthetic Augmentation Can Improve Discriminative Models
        86588, -- 2506.16802 Seeing What Matters: Generalizable AI-generated Video Detection with Forens
        86640, -- 2505.16705 An Analysis of Concept Bottleneck Models: Measuring, Understanding, and Mit
        86852, -- 2501.01015 Boosting Adversarial Transferability with Spatial Adversarial Alignment
        87092, -- 2509.15693 SceneForge: Enhancing 3D-text alignment with Structured Scene Compositions
        87200, -- 2506.07413 Variational Supervised Contrastive Learning
        87219, -- 2509.25831 MIDAS: Misalignment-based Data Augmentation Strategy for Imbalanced Multimo
        87243, -- 2510.15194 Salient Concept-Aware Generative Data Augmentation
        87260, -- 2510.02302 Knowledge Distillation Detection for Open-weights Models
        87298, -- 2502.12627 DAMamba: Vision State Space Model with Dynamic Adaptive Scan
        87392, -- 2502.07503 Recursive Inference Scaling: A Winning Path to Scalable Inference in Langua
        87541, -- 2503.13236 Gradient Extrapolation for Debiased Representation Learning
        87622, -- 2508.09000 UniConvNet: Expanding Effective Receptive Field while Maintaining Asymptoti
        87643, -- 2507.03304 Bridging Domain Generalization to Multimodal Domain Generalization via Unif
        87648, -- 2408.06569 Social Debiasing for Fair Multi-modal LLMs
        87666, -- 2508.02186 Failure Cases Are Better Learned But Boundary Says Sorry: Facilitating Smoo
        87828, -- 2412.01787 Pretrained Reversible Generation as Unsupervised Visual Representation Lear
        87909, -- 2509.05975 ConstStyle: Robust Domain Generalization with Unified Style Transformation
        88015, -- 2508.07759 Correspondence as Video: Test-Time Adaption on SAM2 for Reference Segmentat
        88092, -- 2501.01184 Vulnerability-Aware Spatio-Temporal Learning for Generalizable Deepfake Vid
        88133, -- 2508.01074 Evading Data Provenance in Deep Neural Networks
        88146, -- 2508.19581 Guiding Noisy Label Conditional Diffusion Models with Score-based Discrimin
        88468, -- 2506.21198 Unlocking Constraints: Source-Free Occlusion-Aware Seamless Segmentation
        88632, -- 2506.06853 Curvature Enhanced Data Augmentation for Regression
        88699, -- 2505.01997 Restoring Calibration for Aligned Large Language Models: A Calibration-Awar
        88751, -- 2502.02921 Robust Reward Alignment via Hypothesis Space Batch Cutting
        88788, -- 2411.12665 Regression for the Mean: Auto-Evaluation and Inference with Few Labels thro
        88876, -- 2505.24048 NeuronTune: Towards Self-Guided Spurious Bias Mitigation
        89076, -- 2505.11882 GenZSL: Generative Zero-Shot Learning Via Inductive Variational Autoencoder
        89136, -- 2503.15748 PARQ: Piecewise-Affine Regularized Quantization
        89144, -- 2505.19659 LangDAug: Langevin Data Augmentation for Multi-Source Domain Generalization
        89207, -- 2505.05813 BCE vs. CE in Deep Feature Learning
        89220, -- 2412.11044 Understanding and Mitigating Memorization in Diffusion Models for Tabular D
        89245, -- 2505.11370 Understanding Nonlinear Implicit Bias via Region Counts in Input Space
        89318, -- 2505.00685 On the Importance of Gaussianizing Representations
        89356, -- 2504.08010 Self-Bootstrapping for Versatile Test-Time Adaptation
        89418, -- 2505.24190 Provably Improving Generalization of Few-shot models with Synthetic Data
        89503, -- 2504.13548 Beyond One-Hot Labels: Semantic Mixing for Model Calibration
        89572, -- 2410.14667 SGD Jittering: A Training Strategy for Robust and Accurate Model-Based Arch
        89708, -- 2507.00440 A Recipe for Causal Graph Regression: Confounding Effects Revisited
        89823, -- 2506.17718 Learning Time-Aware Causal Representation for Model Generalization in Evolv
        89832, -- 2502.08512 Measuring Diversity in Synthetic Datasets
        90089, -- 2412.17671 A Bias-Free Training Paradigm for More General AI-generated Image Detection
        90121, -- 2503.17984 Taste More, Taste Better: Diverse Data and Strong Model Boost Semi-Supervis
        90158, -- 2402.06289 FedMIA: An Effective Membership Inference Attack Exploiting "All for One" P
        90186, -- 2411.12817 What Makes a Good Dataset for Knowledge Distillation?
        90290, -- 2408.11280 Exploring Scene Affinity for Semi-Supervised LiDAR Semantic Segmentation
        90296, -- 2503.00286 A Unified Framework for Heterogeneous Semi-supervised Learning
        90304, -- 2503.23220 Large Self-Supervised Models Bridge the Gap in Domain Adaptive Object Detec
        90331, -- 2406.11148 Few-Shot Recognition via Stage-Wise Retrieval-Augmented Finetuning
        90378, -- 2412.13573 Seeking Consistent Flat Minima for Better Domain Generalization via Refinin
        90425, -- 2504.08710 Hypergraph Vision Transformers: Images are More than Nodes, More than Edges
        90459, -- 2306.09363 A Simple Data Augmentation for Feature Distribution Skewed Federated Learni
        90588, -- 2406.05704 Hierarchical Features Matter: A Deep Exploration of Progressive Parameteriz
        90662, -- 2503.14867 DVHGNN: Multi-Scale Dilated Vision HGNN for Efficient Vision Recognition
        90794, -- 2504.10007 Balancing Two Classifiers via A Simplex ETF Structure for Model Calibration
        90871, -- 2410.15980 Learning from Neighbors: Category Extrapolation for Long-Tail Learning
        90992, -- 2411.16788 TIDE: Training Locally Interpretable Domain Generalization Models Enables T
        91013, -- 2412.20047 SimLTD: Simple Supervised and Semi-Supervised Long-Tailed Object Detection
        91088, -- 2403.08632 A Decade's Battle on Dataset Bias: Are We There Yet?
        91261, -- 2410.03030 Dynamic Sparse Training versus Dense Training: The Unexpected Winner in Ima
        91361, -- 2410.07081 JPEG Inspired Deep Learning
        91569, -- 2409.10362 Frequency-Guided Masking for Enhanced Vision Self-Supervised Learning
        91605, -- 2502.00156 ALBAR: Adversarial Learning approach to mitigate Biases in Action Recogniti
        91892, -- 2405.13922 Towards Certification of Uncertainty Calibration under Adversarial Attacks
        91898, -- 2409.05800 Input Space Mode Connectivity in Deep Neural Networks
        91899, -- 2407.10366 Accessing Vision Foundation Models via ImageNet-1K
        91934, -- 2409.02772 Unifying Causal Representation Learning with the Invariance Principle
        91939, -- 2405.16124 Unsupervised Meta-Learning via In-Context Learning
        91948, -- 2410.07577 3D Vision-Language Gaussian Splatting
        91974, -- 2406.15020 A3D: Does Diffusion Dream about 3D Alignment?
        92060, -- 2502.19718 Learning Mask Invariant Mutual Information for Masked Image Modeling
        92099, -- 2502.01688 BrainOOD: Out-of-distribution Generalizable Brain Network Analysis
        92141, -- 2503.00884 Re-Evaluating the Impact of Unseen-Class Unlabeled Data on Semi-Supervised
        92243, -- 2408.04591 HiLo: A Learning Framework for Generalized Category Discovery Robust to Dom
        92255, -- 2311.05589 A Coefficient Makes SVRG Effective
        92519, -- 2210.06583 S4ND: Modeling Images and Videos as Multidimensional Signals Using State Sp
        92576, -- 2606.00558 Semi-Supervised Noise Adaptation: Transferring Knowledge from Noise Domain
        92947, -- 2510.18120 Generalization Below the Edge of Stability: The Role of Data Geometry
        93100, -- 2505.21813 Optimizing Data Augmentation through Bayesian Model Selection
        93186, -- 2509.07103 Lookup multivariate Kolmogorov-Arnold Networks
        93192, -- 2509.24886 Adaptive Canonicalization with Application to Invariant Anisotropic Geometr
        93234, -- 2604.18367 EAST: Early Action Prediction Sampling Strategy with Token Masking
        93424, -- 2510.07758 Rényi Sharpness: A Novel Sharpness that Strongly Correlates with Generaliza
        93433, -- 2410.00718 Pseudo-Non-Linear Data Augmentation: A Constrained Energy Minimization View
        93459, -- 2510.22835 Clustering by Denoising: Latent plug-and-play diffusion for single-cell emb
        93577, -- 2505.23866 Towards Understanding The Calibration Benefits of Sharpness-Aware Minimizat
        93779, -- 2602.03895 Benchmarking Bias Mitigation Toward Fairness Without Harm from Vision to LV
        93873, -- 2505.18137 Boosting Open Set Recognition Performance through Modulated Representation
        94010, -- 2509.21385 Debugging Concept Bottleneck Models through Removal and Retraining
        94227, -- 2602.23777 Reasoning-Driven Multimodal LLM for Domain Generalization
        94632, -- 2510.18229 Unbiased Object Detection Beyond Frequency with Visually Prompted Image Syn
        94690, -- 2603.04731 When Priors Backfire: On the Vulnerability of Unlearnable Examples to Pretr
        94903, -- 2603.03725 Why Do Unlearnable Examples Work: A Novel Perspective of Mutual Information
        95047, -- 2511.04401 Spurious Correlation-Aware Embedding Regularization for Worst-Group Robustn
        98570, -- 2602.05845 Self-Supervised Learning with a Multi-Task Latent Space Objective
        98657, -- 2104.13963 Semi-Supervised Learning of Visual Features by Non-Parametrically Predictin
        98729, -- 2606.16246 Demystifying Training-Time Augmentation for Data-Constrained Language Model
        98827, -- 2606.20196 Distill Once, Adapt Life-Long: Exploring Dataset Distillation for Continual
        99088, -- 2607.02508 From SRA to Self-Flow: Data Augmentation or Self-Supervision?
        99295, -- 2507.00037 Model Fusion via Retrofitting
        99446, -- 2605.14231 AudioMosaic: Contrastive Masked Audio Representation Learning
        99786, -- 2605.25771 MDGMIX: Boundary-Aware Subgraph Mixing for Multi-Domain Graph Pre-Training
        99945, -- 2605.29823 Quantifying and Optimizing Simplicity via Polynomial Representations
        99974, -- 2605.29983 Improving Adversarial Robustness of Attribution via Implicit Regularization
        100106, -- 2506.08297 SEMA: a Scalable and Efficient Mamba like Attention via Token Localization
        100232, -- 2605.10315 Active Tabular Augmentation via Policy-Guided Diffusion Inpainting
        100335, -- 2605.31324 Inconsistency-Aware Minimization: Improving Generalization with Unlabeled D
        100341, -- 2605.25616 Courtroom Analogy: New Perspective on Uncertainty-Aware Classification
        100348, -- 2603.29183 IMPACT: Influence Modeling for Open-Set Time Series Anomaly Detection
        101230, -- 2606.11236 A$^2$SG: Adaptive and Asymmetric Surrogate Gradients for Training Deep Spik
        101268, -- 2602.01733 Improving Backward Conformal Prediction via Non-Conformity Score Transforma
        101350, -- 2606.26037 FedReLa: Imbalanced Federated Learning via Re-Labeling
        101400, -- 2510.07345 Mitigating Surgical Data Imbalance with Dual-Prediction Video Diffusion Mod
        101477, -- 2605.00591 Intrinsic Gradient Suppression for Label-Noise Prompt Tuning in Vision–Lang
        102381, -- 2602.04170 Partial Ring Scan: Revisiting Scan Order in Vision State Space Models
        102513, -- 2508.21495 Rethinking Calibration for Early-Exit Neural Networks
        102606, -- 2208.11247 SwinFIR: Revisiting the SwinIR with Fast Fourier Convolution and Improved T
        102692, -- 2211.04772 Efficient Large-scale Audio Tagging via Transformer-to-CNN Knowledge Distil
        102721, -- 2601.16211 Why Can't I Open My Drawer? Mitigating Object-Driven Shortcuts in Zero-Shot
        103860, -- 2606.22112 Accurate identification and measurement of the precipitate area by two-stag
        104496, -- 2607.09785 Lifelong Representations: A Survey on Continual Self-Supervised Learning fo
        104588, -- 2607.23687 GNM Head: A Generative aNthropometric Model of the human head
        105715, -- 2411.04493 Synergy-Guided Regional Supervision of Pseudo Labels for Semi-Supervised Me
        106209, -- 2602.22734 Asymmetric Idiosyncrasies in Multimodal Models
        106419, -- 2511.18858 Rethinking Long-tailed Dataset Distillation: A Uni-Level Framework with Unb
        106728, -- 2512.21542 Vision Transformers Are Circulant Attention Learners
        106816, -- 2512.07234 Dropout Prompt Learning: Towards Robust and Adaptive Vision-Language Models
        106957, -- 2511.21500 Lost in Time? A Meta-Learning Framework for Time-Shift-Tolerant Physiologic
        107275, -- 2511.16629 Stabilizing Policy Gradient Methods via Reward Profiling
        107339, -- 2512.18722 Generating Risky Samples with Conformity Constraints via Diffusion Models
        107390, -- 2511.20258 Modality-Balanced Collaborative Distillation for Multi-Modal Domain General
        107402, -- 2411.18860 Improving Batch Normalization with Test-Time Adaptation for Robust Object D
        107473, -- 2505.24592 A Flat Minima Perspective on Understanding Augmentations and Model Robustne
        107499, -- 2512.10573 Is the Information Bottleneck Robust Enough? Towards Label-Noise Resistant
        107574, -- 2511.09319 DualFete: Revisiting Teacher-Student Interactions from a Feedback Perspecti
        107949, -- 2501.19032 Error Slice Discovery via Manifold Compactness
        108160, -- 2407.19203 Clean-Label Physical Backdoor Attacks with Data Distillation
        108273, -- 2511.09791 PANDA – Patch and Distribution-Aware Augmentation for Long-Tailed Exemplar-
        108433, -- 2508.09525 Learning Spatial Decay for Vision Transformers
        108930, -- 2608.05424 Invisible Shortcuts: Why Vision Encoders Know Your Camera
        109410, -- 2606.22416 Gen2Balance: Generative Balancing for Long-Tailed Video Action Recognition
        109539, -- 2608.19863 Listening Forward: Next Patch Embedding Prediction Enables Scalable Audio L
        109562, -- 2608.15767 TinyCast: Probabilistic Zero-Shot Forecasting with Computed Periodicity
        110732, -- 2505.10481 Logos as a Well-Tempered Pre-train for Sign Language Recognition
        110971, -- 2509.16516 LLM-Guided Co-Training for Text Classification
        111312, -- 2506.10698 Disentangling Dual-Encoder Masked Autoencoder for Respiratory Sound Classif
        111461, -- 2506.02621 Cross-attention and Self-attention for Audio-visual Speaker Diarization in
        111520, -- 2505.23619 Few-Shot Speech Deepfake Detection Adaptation with Gaussian Processes
        112407, -- 2305.19486 Instance-dependent Noisy-label Learning with Graphical Model Based Noise-ra
        112457, -- 2408.01946 Masked Angle-Aware Autoencoder for Remote Sensing Images
        112487, -- 2409.06665 Data Collection-free Masked Video Modeling
        112539, -- 2408.00677 Scaling Backwards: Minimal Synthetic Pre-training?
        112548, -- 2408.12614 Image-Feature Weak-to-Strong Consistency: An Enhanced Paradigm for Semi-Sup
        112756, -- 2407.04616 Isomorphic Pruning for Vision Models
        112881, -- 2407.18821 Deep Companion Learning: Enhancing Generalization Through Historical Consis
        112883, -- 2408.16965 Contrastive Learning with Synthetic Positives
        112957, -- 2404.05667 AlignZeg: Mitigating Objective Misalignment for Zero-shot Semantic Segmenta
        112984, -- 2312.05286 Bridging Synthetic and Real Worlds for Pre-training Scene Text Detectors
        113146, -- 2306.04621 Flexible Distribution Alignment: Towards Long-tailed Semi-supervised Learni
        113149, -- 2407.05848 Wavelet Convolutions for Large Receptive Fields
        113152, -- 2403.06289 Understanding and Mitigating Human-Labelling Errors in Supervised Contrasti
        113181, -- 2407.07003 Learning to Complement and to Defer to Multiple Users
        113182, -- 2403.17726 Tiny Models are the Computational Saver for Large Models
        113227, -- 2407.01518 Towards Multimodal Open-Set Domain Generalization and Adaptation through Se
        113276, -- 2311.18495 Improving Adversarial Transferability via Model Alignment
        113281, -- 2407.07673 Towards Adaptive Pseudo-label Learning for Semi-Supervised Temporal Action
        113347, -- 2409.06290 EntAugment: Entropy-Driven Adaptive Data Augmentation Framework for Image C
        113358, -- 2407.12568 Echoes of the Past: Boosting Long-tail Recognition via Reflective Learning
        113384, -- 2408.08149 Unsupervised Variational Translator for Bridging Image Restoration and High
        113390, -- 2312.00826 DEVIAS: Learning Disentangled Video Representations of Action and Scene
        113409, -- 2407.03886 DSMix: Distortion-Induced Saliency Map Based Pre-training for No-Reference
        113425, -- 2407.01930 Self-Cooperation Knowledge Distillation for Novel Class Discovery
        113507, -- 2407.04036 Beyond Pixels: Semi-Supervised Semantic Segmentation with a Multi-scale Pat
        113509, -- 2407.02403 Face Reconstruction Transfer Attack as Out-of-Distribution Generalization
        113510, -- 2407.12630 Weighting Pseudo-Labels via High-Activation Feature Index Similarity and Ob
        113517, -- 2409.20139 Characterizing Model Robustness via Natural Input Gradients
        113612, -- 2409.08509 Exploiting Supervised Poison Vulnerability to Strengthen Self-Supervised De
        114484, -- 2602.03555 Cut to the Mix: Simple Data Augmentation Outperforms Elaborate Ones in Limi
        114839, -- 2406.17173 Diff3Dformer: Leveraging Slice Sequence Diffusion for Enhanced 3D CT Classi
        114933, -- 2407.08822 FedMedICL: Towards Holistic Evaluation of Distribution Shifts in Federated
        115136, -- 2403.11689 MoreStyle: Relax Low-frequency Constraint of Fourier-based Image Reconstruc
        115298, -- external SIX-Net: Spatial-context Information miX-up for Electrode Landmark Detectio
        115444, -- 2312.07067 Focus on Hiders: Exploring Hidden Threats for Enhancing Adversarial Trainin
        115457, -- 2403.19278 CAT: Exploiting Inter-Class Dynamics for Domain Adaptive Object Detection
        115464, -- 2403.06946 Split to Merge: Unifying Separated Modalities for Unsupervised Domain Adapt
        115486, -- 2405.14881 DiffuseMix: Label-Preserving Data Augmentation with Diffusion Models
        115492, -- 2404.01828 Defense without Forgetting: Continual Adversarial Defense with Anisotropic
        115555, -- 2405.19899 Open-Set Domain Adaptation for Semantic Segmentation
        115627, -- 2305.15253 Rethinking the Evaluation Protocol of Domain Generalization
        115663, -- 2303.09373 MAPSeg: Unified Unsupervised Domain Adaptation for Heterogeneous Medical Im
        115688, -- 2403.07589 PeLK: Parameter-efficient Large Kernel ConvNets with Peripheral Convolution
        115690, -- 2403.04303 LORS: Low-rank Residual Structure for Parameter-Efficient Network Stacking
        115727, -- 2307.08919 Systematic Comparison of Semi-supervised and Self-supervised Learning for M
        115739, -- 2404.00909 Learning by Correction: Efficient Tuning Task for Zero-Shot Generative Visi
        115741, -- 2403.00543 SURE: SUrvey REcipes for building reliable and robust deep networks
        115750, -- 2401.04727 Revisiting Adversarial Training at Scale
        115860, -- 2403.10519 Frozen Feature Augmentation for Few-Shot Image Classification
        115865, -- 2403.10073 Revisiting Adversarial Training Under Long-Tailed Distributions
        115874, -- 2402.18919 Decompose-and-Compose: A Compositional Approach to Mitigating Spurious Corr
        115878, -- 2404.01179 BEM: Balanced and Entropy-based Mix for Long-Tailed Semi-Supervised Learnin
        115882, -- 2404.03924 Learning Correlation Structures for Vision Transformers
        115912, -- 2405.19902 Learning Discriminative Dynamics with Label Corruption for Noisy Label Dete
        115929, -- 2403.19232 AZ-NAS: Assembling Zero-Cost Proxies for Network Architecture Search
        115933, -- 2404.01692 Beyond Image Super-Resolution for Image Recognition with Task-Driven Percep
        115940, -- 2403.09101 Soften to Defend: Towards Adversarial Robustness via Self-Guided Label Refi
        116168, -- 2403.06676 CAM Back Again: Large Kernel CNNs from a Weakly Supervised Object Localizat
        116179, -- 2406.06820 Adapters Strike Back
        116193, -- 2202.04291 L2B: Learning to Bootstrap Robust Models for Combating Label Noise
        116223, -- 2403.12033 HiKER-SGG: Hierarchical Knowledge Enhanced Robust Scene Graph Generation
        116349, -- 2401.04716 Low-Resource Vision Challenges for Foundation Models
        116457, -- 2403.19539 De-confounded Data-free Knowledge Distillation for Handling Distribution Sh
        116481, -- 2311.03149 Asymmetric Masked Distillation for Pre-Training Small Foundation Models
        116603, -- 2403.11674 Towards Generalizing to Unseen Domains with Few Labels
        116607, -- 2403.05854 LTGC: Long-tail Recognition via Leveraging LLMs-driven Generated Content
        116638, -- 2405.14136 Efficient Multitask Dense Predictor via Binarization
        116644, -- 2404.00851 Prompt Learning via Meta-Regularization
        116667, -- 2311.18695 Seg2Reg: Differentiable 2D Segmentation to 1D Regression Rendering for 360
        116749, -- 2403.01944 Fourier-basis Functions to Bridge Augmentation Gap: Rethinking Frequency Au
        116758, -- 2403.18092 OCAI: Improving Optical Flow Estimation by Occlusion and Consistency Aware
        116808, -- 2408.10798 Universal Novelty Detection Through Adaptive Contrastive Learning
        116874, -- 2311.16081 ViT-Lens: Towards Omni-modal Representations
        117060, -- 2303.10365 CroSel: Cross Selection of Confident Pseudo Labels for Partial-Label Learni
        117086, -- 2402.18133 Classes Are Not Equal: An Empirical Study on Image Recognition Fairness
        117138, -- 2403.01773 Improving Out-of-Distribution Generalization in Graphs via Hierarchical Sem
        117202, -- 2403.17409 Neural Clustering based Visual Representation Learning
        117204, -- 2404.01819 Sparse Semi-DETR: Sparse Learnable Queries for Semi-Supervised Object Detec
        117211, -- 2303.17783 Uncertainty-Aware Source-Free Adaptive Image Super-Resolution with Wavelet
        117242, -- 2404.19250 Enhancing Intrinsic Features for Debiasing via Investigating Class-Discerni
        117744, -- 2507.07814 Pay Attention to Attention Distribution: A New Local Lipschitz Bound for Tr
        118627, -- 2606.31225 A First Exploration of Neuromorphic OT-CFM for Multi-Speaker VSR
        118907, -- 2608.20710 Geometric Regularization for Long-Tailed Semi-Supervised Learning via Gauss
        119091, -- 2607.22931 Spectral-Aware Analytic Class-Incremental Learning for Long-Tailed Distribu
        119137, -- 2606.31695 Intrinsically Stable Spiking Neural Networks: Overcoming the Performance Ba
        119151, -- 2608.04442 Robustness Emerges Early in Training Dynamics, but Is Not Preserved
        119292, -- 2606.24361 SignNet-1M: Large-Scale Multilingual Sign Language Video Dataset with Downs
        119550, -- 2608.22665 Hyperbolic Hierarchical Clustering for Visual Representation Learning
        120128, -- 2505.21591 Pioneering 4-Bit FP Quantization for Diffusion Models: Mixup-Sign Quantizat
        120153, -- 2506.15720 Tripartite Weight-Space Ensemble for Few-Shot Class-Incremental Learning
        120397, -- 2412.12423 GG-SSMs: Graph-Generating State Space Models
        120495, -- 2503.22163 T-CIL: Temperature Scaling using Adversarial Perturbation for Calibration i
        121647, -- 2511.20263 Advancing Image Classification with Discrete Diffusion Classification Model
        121972, -- 2404.06095 Masked Modeling Duo: Towards a Universal Audio Pre-training Framework
        122749, -- 2610.04128 What Gradients Add to Text Leakage in Split Language Models, Counted per To
        123217, -- 2308.12113 Advancements in Point Cloud Data Augmentation for Deep Learning: A Survey
        123487, -- 2210.00266 Long-Tailed Class Incremental Learning
        123649, -- 2312.07856 DTL: Disentangled Transfer Learning for Visual Recognition
        123651, -- 2310.06234 Efficient Adaptation of Large Vision Transformer via Adapter Re-Composing
        124769, -- 2604.06689 Generative Cross-Entropy: A Strictly Proper Loss for Data-Efficient Classif
        125294, -- 2512.24162 Deep Probabilistic Supervision for Image Classification
        125997, -- 2610.09609 Decoupled Optimization for Teacher-Student Semi-Supervised Learning via a P
        127502, -- 2605.06809 LookWhen? Fast Video Recognition by Learning When, Where, and What to Compu
        127584, -- 2602.02015 Robust Domain Generalization under Divergent Marginal and Conditional Distr
        128599, -- 2609.30478 The Shape of Events: Edge-Based Inductive Biases via Cross-Domain Distillat
        128607, -- 2602.02358 Transfer Learning Through Conditional Quantile Matching
        129271, -- 2604.02564 Why Invariance is Not Enough for Biomedical Domain Generalization and How t
        129536, -- 2602.06924 Rank-Constrained Adaptation for Reliable Real-World Performance
        131358  -- 2608.25710 Difficulty-Aware Sample Allocation for Adaptive Data Augmentation in Semant
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
        2050, -- 1904.12848 Unsupervised Data Augmentation for Consistency Training
        2618, -- 1909.13719 RandAugment: Practical automated data augmentation with a reduced search sp
        2800, -- 1911.04252 Self-training with Noisy Student improves ImageNet classification
        6428, -- 2108.06949 Data Augmentation for Scene Text Recognition
        80821  -- 2103.10158 TrivialAugment: Tuning-free Yet State-of-the-Art Data Augmentation
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
        2260, -- 1906.05849 Contrastive Multiview Coding
        2843, -- 1911.09665 Adversarial Examples Improve Image Recognition
        2906, -- 1912.02781 AugMix: A Simple Data Processing Method to Improve Robustness and Uncertain
        3143, -- 2002.11102 On Feature Normalization and Data Augmentation
        3191, -- 2003.03384 AutoML-Zero: Evolving Machine Learning Algorithms From Scratch
        3303, -- 2004.02967 Evolving Normalization-Activation Layers
        3321, -- 2004.04136 CURL: Contrastive Unsupervised Representations for Reinforcement Learning
        3401, -- 2004.11362 Supervised Contrastive Learning
        3616, -- 2005.12320 SCAN: Learning to Classify Images without Labels
        3698, -- 2006.06676 Training Generative Adversarial Networks with Limited Data
        3709, -- 2006.07733 Bootstrap your own latent: A new approach to self-supervised Learning
        3738, -- 2006.09882 Unsupervised Learning of Visual Features by Contrasting Cluster Assignments
        4000, -- 2008.03800 Spatiotemporal Contrastive Video Representation Learning
        4167, -- 2009.08453 MEAL V2: Boosting Vanilla ResNet-50 to 80%+ Top-1 Accuracy on ImageNet with
        4463, -- 2010.14819 Model Rubik's Cube: Twisting Resolution, Depth and Width for TinyNets
        4589, -- 2011.10082 Hybrid Consistency Training with Prototype Adaptation for Few-Shot Learning
        4730, -- 2012.07177 Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segment
        4763, -- 2012.11101 ResizeMix: Mixing Data with Preserved Object Information and True Labels
        4782, -- 2012.12877 Training data-efficient image transformers & distillation through attention
        4894, -- 2101.05022 Re-labeling ImageNet: from Single to Multi-Labels, from Global to Localized
        4923, -- 2101.08692 Characterizing signal propagation to close the performance gap in unnormali
        4955, -- 2101.11605 Bottleneck Transformers for Visual Recognition
        4996, -- 2102.03334 ViLT: Vision-and-Language Transformer Without Convolution or Region Supervi
        5022, -- 2102.06171 High-Performance Large-Scale Image Recognition Without Normalization
        5052, -- 2102.08602 LambdaNetworks: Modeling Long-Range Interactions Without Attention
        5076, -- 2102.10882 Conditional Positional Encodings for Vision Transformers
        5112, -- 2103.00112 Transformer in Transformer
        5143, -- 2103.03206 Perceiver: General Perception with Iterative Attention
        5196, -- 2103.07579 Revisiting ResNets: Improved Training and Scaling Strategies
        5261, -- 2103.13027 AutoMix: Unveiling the Power of Mixup for Stronger Classifiers
        5278, -- 2103.14006 Designing a Practical Degradation Model for Deep Blind Image Super-Resoluti
        5279, -- 2103.14030 Swin Transformer: Hierarchical Vision Transformer using Shifted Windows
        5291, -- 2103.14899 CrossViT: Cross-Attention Multi-Scale Vision Transformer for Image Classifi
        5306, -- 2103.15691 ViViT: A Video Vision Transformer
        5332, -- 2103.17239 Going deeper with Image Transformers
        5341, -- 2104.00298 EfficientNetV2: Smaller Models and Faster Training
        5343, -- 2104.00323 Jigsaw Clustering for Unsupervised Visual Representation Learning
        5426, -- 2104.05704 Escaping the Big Data Paradigm with Compact Transformers
        5560, -- 2104.10972 ImageNet-21K Pretraining for the Masses
        5563, -- 2104.11227 Multiscale Vision Transformers
        5581, -- 2104.12533 Visformer: The Vision-friendly Transformer
        5638, -- 2105.01601 MLP-Mixer: An all-MLP Architecture for Vision
        5658, -- 2105.03075 A Survey of Data Augmentation Approaches for NLP
        5667, -- 2105.03404 ResMLP: Feedforward networks for image classification with data-efficient t
        5732, -- 2105.07581 Vision Transformers are Robust Learners
        5750, -- 2105.08582 Vision Transformer for Fast and Efficient Scene Text Recognition
        5788, -- 2105.12723 Nested Hierarchical Transformer: Towards Accurate, Data-Efficient and Inter
        5829, -- 2106.00168 Rethinking Pseudo Labels for Semi-Supervised Object Detection
        5836, -- 2106.00666 You Only Look at One Sequence: Rethinking Transformer in Vision through Obj
        5860, -- 2106.01548 When Vision Transformers Outperform ResNets without Pre-training or Strong
        5898, -- 2106.03374 RegMix: Data Mixing Augmentation for Regression
        5928, -- 2106.04803 CoAtNet: Marrying Convolution and Attention for All Data Sizes
        5929, -- 2106.04823 Taxonomy of Machine Learning Safety: A Survey and Primer
        5947, -- 2106.05682 DASO: Distribution-Aware Semantics-Oriented Pseudo-label for Imbalanced Sem
        5957, -- 2106.05974 Scaling Vision with Sparse Mixture of Experts
        6018, -- 2106.08962 Efficient Deep Learning: A Survey on Making Deep Learning Models Smaller, F
        6035, -- 2106.09681 XCiT: Cross-Covariance Image Transformers
        6051, -- 2106.10270 How to train your ViT? Data, Augmentation, and Regularization in Vision Tra
        6112, -- 2106.13112 VOLO: Vision Outlooker for Visual Recognition
        6114, -- 2106.13230 Video Swin Transformer
        6156, -- 2106.15941 Augmented Shortcuts for Vision Transformers
        6168, -- 2107.00652 CSWin Transformer: A General Vision Transformer Backbone with Cross-Shaped
        6261, -- 2107.07651 Align before Fuse: Vision and Language Representation Learning with Momentu
        6277, -- 2107.09249 Self-Supervised Aggregation of Diverse Experts for Test-Agnostic Long-Taile
        6307, -- 2107.11817 Go Wider Instead of Deeper
        6333, -- 2107.14795 Perceiver IO: A General Architecture for Structured Inputs & Outputs
        6334, -- 2108.00154 CrossFormer: A Versatile Vision Transformer Hinging on Cross-scale Attentio
        6395, -- 2108.04384 RaftMLP: How Much Can Be Done Without Attention and with Less Spatial Local
        6439, -- 2108.07610 DRAEM - A discriminatively trained reconstruction embedding for surface an
        6489, -- 2108.11801 Unsupervised domain adaptation for clinician pose estimation and instance s
        6695, -- 2109.10282 TrOCR: Transformer-based Optical Character Recognition with Pre-trained Mod
        6769, -- 2110.00476 ResNet strikes back: An improved training procedure in timm
        6860, -- 2110.04596 Deep Long-Tailed Learning: A Survey
        6896, -- 2110.06207 Open-Set Recognition: a Good Closed-Set Classifier is All You Need?
        6908, -- 2110.06537 Well-classified Examples are Underestimated in Classification with Deep Neu
        6947, -- 2110.07641 Non-deep Networks
        6996, -- 2110.08890 Network Augmentation for Tiny Deep Learning
        7019, -- 2110.11144 RCT: Random Consistency Training for Semi-supervised Sound Event Detection
        7149, -- 2111.02358 VLMo: Unified Vision-Language Pre-Training with Mixture-of-Modality-Experts
        7154, -- 2111.02549 VORTEX: Physics-Driven Data Augmentations Using Consistency Training for Ro
        7170, -- 2111.03861 What augmentations are sensitive to hyper-parameters and why?
        7200, -- 2111.06377 Masked Autoencoders Are Scalable Vision Learners
        7221, -- 2111.08165 RapidRead: Global Deployment of State-of-the-art Radiology AI for a Large V
        7255, -- 2111.09833 TransMix: Attend to Mix for Vision Transformers
        7259, -- 2111.09883 Swin Transformer V2: Scaling Up Capacity and Resolution
        7260, -- 2111.09886 SimMIM: A Simple Framework for Masked Image Modeling
        7281, -- 2111.11418 MetaFormer Is Actually What You Need for Vision
        7311, -- 2111.13353 Contrastive Vicinal Space for Unsupervised Domain Adaptation
        7387, -- 2112.01522 Uni-Perceiver: Pre-training Unified Architecture for Generic Perception for
        7388, -- 2112.01526 MViTv2: Improved Multiscale Vision Transformers for Classification and Dete
        7456, -- 2112.05090 Extending the WILDS Benchmark for Unsupervised Adaptation
        7537, -- 2112.08723 Distilled Dual-Encoder Model for Vision-Language Understanding
        7550, -- 2112.09133 Masked Feature Prediction for Self-Supervised Visual Pre-Training
        7552, -- 2112.09245 Automated Deep Learning: Neural Architecture Search Is Not the End
        7562, -- 2112.09583 Align and Prompt: Video-and-Language Pre-training with Entity Prompts
        7572, -- 2112.10510 Transformers Can Do Bayesian Inference
        7605, -- 2112.13492 Vision Transformer for Small-Size Datasets
        7610, -- 2112.13692 Augmenting Convolutional networks with attention-based aggregation
        7673, -- 2201.03545 A ConvNet for the 2020s
        7740, -- 2201.08377 Omnivore: A Single Model for Many Visual Modalities
        7758, -- 2201.09792 Patches Are All You Need?
        7777, -- 2201.10890 One Student Knows All Experts Know: From Sparse to Dense
        7881, -- 2202.02794 Active Learning on a Budget: Opposite Strategies Suit High and Low Budgets
        7889, -- 2202.03052 OFA: Unifying Architectures, Tasks, and Modalities Through a Simple Sequenc
        7909, -- 2202.04200 MaskGIT: Masked Generative Image Transformer
        7949, -- 2202.06510 Mixing and Shifting: Exploiting Global and Local Dependencies in Vision MLP
        7956, -- 2202.06709 How Do Vision Transformers Work?
        8049, -- 2202.11921 Auto-scaling Vision Transformers without Training
        8168, -- 2203.03689 WaveMix: Resource-efficient Token Mixing for Images
        8200, -- 2203.05482 Model soups: averaging weights of multiple fine-tuned models improves accur
        8229, -- 2203.06717 Scaling Up Your Kernels to 31x31: Revisiting Large Kernel Design in CNNs
        8383, -- 2203.11926 Focal Modulation Networks
        8401, -- 2203.12602 VideoMAE: Masked Autoencoders are Data-Efficient Learners for Self-Supervis
        8438, -- 2203.14316 MutexMatch: Semi-Supervised Learning with Mutex-Based Consistency Regulariz
        8519, -- 2203.17269 A Closer Look at Rehearsal-Free Continual Learning
        8560, -- 2204.01697 MaxViT: Multi-Axis Vision Transformer
        8608, -- 2204.03359 ECCV Caption: Correcting False Negatives by Collecting Machine-and-Human-ve
        8612, -- 2204.03475 Solving ImageNet: a Unified Scheme for Training any Backbone to Top Results
        8719, -- 2204.07118 DeiT III: Revenge of the ViT
        8721, -- 2204.07143 Neighborhood Attention Transformer
        8722, -- 2204.07154 MiniViT: Compressing Vision Transformers with Weight Multiplexing
        8858, -- 2204.12743 Self-Supervised Text Erasing with Controllable Image Synthesis
        8928, -- 2205.01972 Sequencer: Deep LSTM for Image Classification
        9049, -- 2205.09113 Masked Autoencoders As Spatiotemporal Learners
        9093, -- 2205.10505 A Study on Transformer Configuration and Training Objective
        9126, -- 2205.11320 Active Learning Through a Covering Lens
        9147, -- 2205.12005 mPLUG: Effective and Efficient Vision-Language Learning by Cross-modal Skip
        9235, -- 2205.13943 Architecture-Agnostic Masked Image Modeling - From ViT back to CNN
        9252, -- 2205.14375 WaveMix: A Resource-efficient Neural Network for Image Analysis
        9253, -- 2205.14443 A Closer Look at Self-Supervised Lightweight Vision Transformers
        9305, -- 2206.00051 Learning Instance-Specific Augmentations by Capturing Local Invariances
        9328, -- 2206.01009 Unified Recurrence Modeling for Video Action Anticipation
        9377, -- 2206.02680 Separable Self-attention for Mobile Vision Transformers
        9429, -- 2206.04664 On Data Scaling in Masked Image Modeling
        9456, -- 2206.06336 Language Models are General-Purpose Interfaces
        9485, -- 2206.07643 Coarse-to-Fine Vision-Language Pre-training with Fusion in the Backbone
        9491, -- 2206.07706 Masked Frequency Modeling for Self-Supervised Visual Pre-Training
        9517, -- 2206.08657 BridgeTower: Building Bridges Between Encoders in Vision-Language Represent
        9564, -- 2206.10589 EdgeNeXt: Efficiently Amalgamated CNN-Transformer Architecture for Mobile V
        9628, -- 2206.14098 RevBiFPN: The Fully Reversible Bidirectional Feature Pyramid Network
        9669, -- 2207.00449 Dissecting Self-Supervised Learning Methods for Surgical Computer Vision
        9794, -- 2207.06966 Scene Text Recognition with Permuted Autoregressive Sequence Models
        9804, -- 2207.07611 Position Prediction as an Effective Pretraining Strategy
        9813, -- 2207.08185 Mind the Gap: Polishing Pseudo labels for Accurate Semi-supervised Object D
        9824, -- 2207.09067 Time Is MattEr: Temporal Self-supervision for Video Transformers
        9840, -- 2207.09639 DC-BENCH: Dataset Condensation Benchmark
        9848, -- 2207.10023 Tailoring Self-Supervision for Supervised Learning
        9866, -- 2207.10666 TinyViT: Fast Pretraining Distillation for Small Vision Transformers
        9931, -- 2207.14284 HorNet: Efficient High-Order Spatial Interactions with Recursive Gated Conv
        10007, -- 2208.04619 RDA: Reciprocal Distribution Alignment for Robust Semi-supervised Learning
        10041, -- 2208.06677 Adan: Adaptive Nesterov Momentum Algorithm for Faster Optimizing Deep Model
        10049, -- 2208.07204 USB: A Unified Semi-supervised Learning Benchmark for Classification
        10056, -- 2208.07407 SemAug: Semantically Meaningful Image Augmentations for Object Detection Th
        10152, -- 2208.12856 Local Context-Aware Active Domain Adaptation
        10237, -- 2209.03592 Multi-Granularity Prediction for Scene Text Recognition
        10244, -- 2209.03917 Exploring Target Representations for Masked Autoencoders
        10255, -- 2209.04861 Inverse Image Frequency for Long-tailed Image Recognition
        10375, -- 2209.10655 Mega: Moving Average Equipped Gated Attention
        10469, -- 2209.15001 Dilated Neighborhood Attention Transformer
        10471, -- 2209.15031 Automatic Data Augmentation via Invariance-Constrained Learning
        10550, -- 2210.01820 MOAT: Alternating Mobile Convolution and Attention Brings Strong Vision Mod
        10728, -- 2210.05775 C-Mixup: Improving Generalization in Regression
        10740, -- 2210.06096 Masked Motion Encoding for Self-Supervised Video Representation Learning
        10765, -- 2210.06640 Compute-Efficient Deep Learning: Algorithmic Trends and Opportunities
        10831, -- 2210.08363 Data-Efficient Augmentation for Training Neural Networks
        10863, -- 2210.09184 Packed-Ensembles for Efficient Uncertainty Estimation
        11031, -- 2210.13452 MetaFormer Baselines for Vision
        11158, -- 2211.00262 Training Vision-Language Models with Less Bimodal Supervision
        11239, -- 2211.03295 MogaNet: Multi-order Gated Aggregation Network
        11298, -- 2211.05781 Demystify Transformers & Convolutions in Modern Image Deep Networks
        11343, -- 2211.07636 EVA: Exploring the Limits of Masked Visual Representation Learning at Scale
        11392, -- 2211.09117 MAGE: MAsked Generative Encoder to Unify Representation Learning and Image
        11393, -- 2211.09119 Token Turing Machines
        11404, -- 2211.09552 UniFormerV2: Spatiotemporal Learning by Arming Image ViTs with Video UniFor
        11409, -- 2211.09703 EfficientTrain: Exploring Generalized Curriculum Learning for Training Visu
        11443, -- 2211.10586 Scaling Up Dataset Distillation to ImageNet-1K with Constant Memory
        11447, -- 2211.10636 EVEREST: Efficient Masked Video Autoencoder by Removing Redundant Spatiotem
        11470, -- 2211.11167 Vision Transformer with Super Token Sampling
        11502, -- 2211.11733 Teaching Structured Vision&Language Concepts to Vision&Language Models
        11507, -- 2211.11753 SplitNet: Learnable Clean-Noisy Label Splitting for Learning with Noisy Lab
        11512, -- 2211.11950 UpCycling: Semi-supervised 3D Object Detection without Sharing Raw-level Un
        11574, -- 2211.13194 Indian Commercial Truck License Plate Detection and Recognition for Weighbr
        11611, -- 2211.13976 Expanding Small-Scale Datasets with Guided Imagination
        11613, -- 2211.14058 Cross-Domain Ensemble Distillation for Domain Generalization
        11637, -- 2211.14646 Towards Improved Input Masking for Convolutional Neural Networks
        11756, -- 2212.00776 ResFormer: Scaling ViTs with Multi-Resolution Training
        11761, -- 2212.00794 Scaling Language-Image Pre-training via Masking
        11769, -- 2212.00979 PASTA: Proportional Amplitude Spectrum Training Augmentation for Syn-to-Rea
        11832, -- 2212.03229 Rethinking Video ViTs: Sparse Video Tubes for Joint Image and Video Learnin
        11852, -- 2212.03862 Teaching Matters: Investigating the Role of Supervision in Vision Transform
        11893, -- 2212.04871 Spurious Features Everywhere - Large-Scale Detection of Harmful Spurious F
        11934, -- 2212.06138 CLIP Itself is a Strong Fine-tuner: Achieving 85.7% and 88.0% Top-1 Accurac
        12029, -- 2212.08649 Better May Not Be Fairer: A Study on Subgroup Discrepancy in Image Classifi
        12091, -- 2212.09737 Position-guided Text Prompt for Vision-Language Pre-training
        12154, -- 2212.10556 Unleashing the Power of Visual Prompting At the Pixel Level
        12222, -- 2212.12977 SMMix: Self-Motivated Image Mixing for Vision Transformers
        12230, -- 2212.13350 A Generalization of ViT/MLP-Mixer to Graphs
        12231, -- 2212.13420 Self Meta Pseudo Labels: Meta Pseudo Labels Without The Teacher
        12283, -- 2301.00808 ConvNeXt V2: Co-designing and Scaling ConvNets with Masked Autoencoders
        12288, -- 2301.01146 Rethinking Mobile Block for Efficient Attention-based Models
        12297, -- 2301.01380 Ego-Only: Egocentric Action Detection without Exocentric Transferring
        12615, -- 2301.12187 Efficient Latency-Aware CNN Depth Compression via Two-Stage Dynamic Program
        12639, -- 2301.12549 Unlocking Deterministic Robustness Certification on ImageNet
        12683, -- 2301.13195 Adaptive Computation with Elastic Input Sequence
        12711, -- 2301.13741 UPop: Unified and Progressive Pruning for Compressing Vision-Language Trans
        12785, -- 2302.01316 Are Diffusion Models Vulnerable to Membership Inference Attacks?
        12787, -- 2302.01327 Dual PatchNorm
        12860, -- 2302.02503 Leaving Reality to Imagination: Robust Classification via Generated Dataset
        12980, -- 2302.04638 Better Diffusion Models Further Improve Adversarial Training
        13093, -- 2302.06992 Hard-aware Instance Adaptive Self-training for Unsupervised Cross-domain Se
        13095, -- 2302.07011 A Modern Look at the Relationship between Sharpness and Generalization
        13129, -- 2302.07944 Effective Data Augmentation With Diffusion Models
        13132, -- 2302.07994 À-la-carte Prompt Tuning (APT): Combining Distinct Data Via Composable Prom
        13231, -- 2302.10866 Hyena Hierarchy: Towards Larger Convolutional Language Models
        13268, -- 2302.11861 Out-of-Domain Robustness via Targeted Augmentations
        13299, -- 2302.12453 Inducing Neural Collapse in Deep Long-tailed Learning
        13325, -- 2302.13334 Knowledge Restore and Transfer for Multi-label Class-Incremental Learning
        13452, -- 2303.01500 Dropout Reduces Underfitting
        13493, -- 2303.02506 Prismer: A Vision-Language Model with Multi-Task Experts
        13514, -- 2303.03108 Gradient Norm Aware Minimization Seeks First-Order Flatness and Improves Ge
        13534, -- 2303.03667 Run, Don't Walk: Chasing Higher FLOPS for Faster Neural Networks
        13605, -- 2303.05251 Masked Image Modeling with Local Multi-Scale Reconstruction
        13794, -- 2303.08810 BiFormer: Vision Transformer with Bi-Level Routing Attention
        13803, -- 2303.08983 Reinforce Data, Multiply Impact: Improved Model Accuracy and Robustness wit
        13860, -- 2303.09870 TeSLA: Test-Time Self-Learning With Automatic Adversarial Augmentation
        13885, -- 2303.10451 Augmenting and Aligning Snippets for Few-Shot Video Domain Adaptation
        13918, -- 2303.11114 SeiT: Storage-Efficient Vision Training with Tokens Using 1% of Pixel Stora
        13935, -- 2303.11331 EVA-02: A Visual Representation for Neon Genesis
        13980, -- 2303.12001 ViC-MAE: Self-Supervised Representation Learning from Images and Video with
        14019, -- 2303.12670 Correlational Image Modeling for Self-Supervised Visual Pre-Training
        14068, -- 2303.13496 The effectiveness of MAE pre-pretraining for billion-scale pretraining
        14196, -- 2303.15446 SwiftFormer: Efficient Additive Attention for Transformer-based Real-time M
        14222, -- 2303.16058 Unmasked Teacher: Towards Training-Efficient Video Foundation Models
        14233, -- 2303.16203 Your Diffusion Model is Secretly a Zero-Shot Classifier
        14262, -- 2303.16727 VideoMAE V2: Scaling Video Masked Autoencoders with Dual Masking
        14272, -- 2303.16900 InceptionNeXt: When Inception Meets ConvNeXt
        14296, -- 2303.17376 A Study of Autoregressive Decoders for Multi-Tasking in Computer Vision
        14381, -- 2304.00719 Multi-Modal Representation Learning with Text-Driven Soft Masks
        14414, -- 2304.01279 Long-Tailed Visual Recognition via Self-Heterogeneous Integration with Know
        14462, -- 2304.02034 Effective Theory of Transformers at Initialization
        14472, -- 2304.02330 SMPConv: Self-moving Point Representations for Continuous Convolution
        14508, -- 2304.03283 Diffusion Models as Masked Autoencoders
        14528, -- 2304.03709 Meta-causal Learning for Single Domain Generalization
        14618, -- 2304.05350 Astroformer: More Data Might not be all you need for Classification
        14632, -- 2304.05659 RIFormer: Keep Your Vision Backbone Effective While Removing Token Mixer
        14640, -- 2304.05919 Hard Patches Mining for Masked Image Modeling
        14724, -- 2304.07750 GeoMultiTaskNet: remote sensing unsupervised domain adaptation using geogra
        14761, -- 2304.08821 TTIDA: Controllable Generative Data Augmentation via Text-to-Text and Text-
        14831, -- 2304.10253 Image retrieval outperforms diffusion models on data augmentation
        14863, -- 2304.10970 Can GPT-4 Perform Neural Architecture Search?
        14880, -- 2304.11263 Benchmarking Low-Shot Robustness to Natural Distribution Shifts
        14933, -- 2304.12520 Hint-Aug: Drawing Hints from Foundation Vision Transformers Towards Boosted
        15004, -- 2304.13995 Rotation and Translation Invariant Representation Learning with Implicit Ne
        15094, -- 2305.00729 What Do Self-Supervised Vision Transformers Learn?
        15120, -- 2305.01160 Long-Tailed Recognition by Mutual Information Maximization between Latent F
        15185, -- 2305.02299 Dynamic Sparse Training with Structured Sparsity
        15386, -- 2305.05665 ImageBind: One Embedding Space To Bind Them All
        15792, -- 2305.11772 Neural Foundations of Mental Simulation: Future Prediction of Latent Repres
        15897, -- 2305.12972 VanillaNet: the Power of Minimalism in Deep Learning
        16024, -- 2305.14014 CLIP4STR: A Simple Baseline for Scene Text Recognition with Pre-trained Vis
        16162, -- 2305.14890 HARD: Hard Augmentations for Robust Distillation
        16693, -- 2305.20087 Too Large; Data Reduction for Vision-Language Pre-Training
        16706, -- 2306.00103 ManagerTower: Aggregating the Insights of Uni-Modal Experts for Vision-Lang
        16721, -- 2306.00238 Bytes Are All You Need: Transformers Operating Directly On File Bytes
        16812, -- 2306.00989 Hiera: A Hierarchical Vision Transformer without the Bells-and-Whistles
        16827, -- 2306.01195 Consistency-guided Prompt Learning for Vision-Language Models
        16832, -- 2306.01222 Scaling Up Semi-supervised Learning with Unconstrained Unlabelled Data
        16850, -- 2306.01436 Multi-Objective Population Based Training
        17130, -- 2306.04822 Optimizing ViViT Training: Time and Memory Reduction for Action Recognition
        17270, -- 2306.06635 2-D SSM: A General Spatial Layer for Visual Transformers
        17287, -- 2306.06852 Rethink DARTS Search Space and Renovate a New Benchmark
        17309, -- 2306.07197 AROID: Improving Adversarial Robustness Through Online Instance-Wise Data A
        17394, -- 2306.08103 Generating Images with 3D Annotations Using Diffusion Models
        17483, -- 2306.09301 OpenOOD v1.5: Enhanced Benchmark for Out-of-Distribution Detection
        17607, -- 2306.11248 Dynamic Perceiver for Efficient Visual Recognition
        17691, -- 2306.12929 Quantizable Transformers: Removing Outliers by Helping Attention Heads Do N
        17763, -- 2306.14525 ParameterNet: Parameters Are All You Need
        17919, -- 2306.17778 Look, Remember and Reason: Grounded reasoning in videos with language model
        18063, -- 2307.03135 Distilling Large Vision-Language Model with Out-of-Distribution Generalizab
        18219, -- 2307.06948 Self-regulating Prompts: Foundational Model Adaptation without Forgetting
        18320, -- 2307.08504 BUS:Efficient and Effective Vision-language Pre-training with Bottom-Up Pat
        18323, -- 2307.08579 Scale-Aware Modulation Meet Transformer
        18343, -- 2307.08809 Local or Global: Selective Knowledge Assimilation for Federated Learning wi
        18345, -- 2307.08927 Multi-Stage Cable Routing through Hierarchical Imitation Learning
        18413, -- 2307.10062 Unsupervised Accuracy Estimation of Deep Visual Models using Domain-Adaptiv
        18668, -- 2307.14334 Towards Generalist Biomedical AI
        18684, -- 2307.14611 TextManiA: Enriching Visual Feature by Text-driven Manifold Augmentation
        18835, -- 2308.00442 FLatten Transformer: Vision Transformer using Focused Linear Attention
        19057, -- 2308.04549 Prune Spatio-temporal Tokens by Semantic-aware Temporal Accumulation
        19066, -- 2308.04657 Which Tokens to Use? Investigating Token Reduction in Vision Transformers
        19090, -- 2308.04995 IDiff-Face: Synthetic-based Face Recognition through Fizzy Identity-Conditi
        19173, -- 2308.06453 Multi-Label Knowledge Distillation
        19349, -- 2308.08822 MixBag: Bag-Level Data Augmentation for Learning from Label Proportions
        19389, -- 2308.09306 DiffDis: Empowering Generative Diffusion Model with Cross-Modal Discriminat
        19458, -- 2308.09922 MDCS: More Diverse Experts with Consistency Self-distillation for Long-tail
        19488, -- 2308.10133 TransFace: Calibrating Transformer Training for Face Recognition from a Dat
        19510, -- 2308.10285 DomainDrop: Suppressing Domain-Sensitive Channels for Domain Generalization
        19586, -- 2308.11062 UnLoc: A Unified Framework for Video Localization Tasks
        19633, -- 2308.11509 SwinFace: A Multi-task Transformer for Face Recognition, Expression Recogni
        19637, -- 2308.11568 SPANet: Frequency-balancing Token Mixer using Spectral Pooling Aggregation
        19689, -- 2308.12064 SILT: Shadow-aware Iterative Label Tuning for Learning to Detect Shadows fr
        19751, -- 2308.12960 Towards Realistic Zero-Shot Classification via Self Structural Semantic Ali
        19939, -- 2308.15996 DTrOCR: Decoder-only Transformer for Optical Character Recognition
        20067, -- 2309.01430 DAT++: Spatially Dynamic Vision Transformer with Deformable Attention
        20182, -- 2309.03576 DropPos: Pre-Training Vision Transformers by Reconstructing Dropped Positio
        20183, -- 2309.03598 Enhancing Sample Utilization through Sample Adaptive Augmentation in Semi-S
        20241, -- 2309.04747 When to Learn What: Model-Adaptive Data Augmentation Curriculum
        20281, -- 2309.05375 Toward a Deeper Understanding: RetNet Viewed through Convolution
        20432, -- 2309.07911 Disentangling Spatial and Temporal Learning for Efficient Image-to-Video Tr
        20520, -- 2309.08928 In-Style: Bridging Text and Uncurated Videos with Style Transfer for Text-V
        20628, -- 2309.10713 Interpret Vision Transformers as ConvNets with Dynamic Convolutions
        20693, -- 2309.11523 RMT: Retentive Networks Meet Vision Transformers
        20700, -- 2309.11593 Sentence Attention Blocks for Answer Grounding
        20768, -- 2309.12814 Domain Adaptive Few-Shot Open-Set Learning
        20954, -- 2309.15251 VPA: Fully Test-Time Visual Prompt Adaptation
        20995, -- 2309.15991 Targeted Image Data Augmentation Increases Basic Skills Captioning Robustne
        21120, -- 2310.00093 DataDAM: Efficient Dataset Distillation with Attention Matching
        21195, -- 2310.00847 Can Pre-trained Networks Detect Familiar Out-of-Distribution Data?
        21236, -- 2310.01324 ZeroI2V: Zero-Cost Adaptation of Pre-trained Transformers from Image to Vid
        21797, -- 2310.07510 Heuristic Vision Pre-Training with Self-Supervised and Supervised Multi-Tas
        21932, -- 2310.08847 On the Over-Memorization During Natural, Robust and Catastrophic Overfittin
        22733, -- 2310.19168 BirdSAT: Cross-View Contrastive Masked Autoencoders for Bird Species Classi
        22783, -- 2310.19909 Battle of the Backbones: A Large-Scale Comparison of Pretrained Models acro
        22912, -- 2311.01441 Distilling Out-of-Distribution Robustness from Vision-Language Foundation M
        23141, -- 2311.05613 Window Attention is Bugged: How not to Interpolate Position Embeddings
        23750, -- 2311.15022 Occlusion Sensitivity Analysis with Augmentation Subspace Perturbation in D
        23908, -- 2311.17049 MobileCLIP: Fast Image-Text Models through Multi-Modal Reinforced Training
        23927, -- 2311.17132 TransNeXt: Robust Foveal Visual Perception for Vision Transformers
        23983, -- 2311.17901 SODA: Bottleneck Diffusion Models for Representation Learning
        24050, -- 2311.18765 MLLMs-Augmented Visual-Language Representation Learning
        24058, -- 2311.18823 Initializing Models with Larger Ones
        24064, -- 2311.18838 Dataset Distillation via Curriculum Data Synthesis in Large Data Era
        24153, -- 2312.00863 EfficientSAM: Leveraged Masked Image Pretraining for Efficient Segment Anyt
        24220, -- 2312.02021 Strong but simple: A Baseline for Domain Generalized Dense Perception by CL
        24328, -- 2312.03046 Diversified in-domain synthesis with efficient fine-tuning for few-shot cla
        24468, -- 2312.04567 Scaling Laws of Synthetic Images for Model Training ... for Now
        24575, -- 2312.06106 AUGCAL: Improving Sim2Real Adaptation by Uncertainty Calibration on Augment
        24612, -- 2312.06647 4M: Massively Multimodal Masked Modeling
        24772, -- 2312.08874 Agent Attention: On the Integration of Softmax and Linear Attention
        24856, -- 2312.10105 SeiT++: Masked Token Modeling Improves Storage-efficient Training
        24893, -- 2312.10613 p-Laplacian Adaptation for Generative Pre-trained Vision-Language Models
        24970, -- 2312.11954 Adversarial AutoMixup
        24982, -- 2312.12237 Roll With the Punches: Expansion and Shrinkage of Soft Label Selection for
        25169, -- 2312.15297 Make Me a BNN: A Simple Strategy for Estimating Bayesian Uncertainty from P
        25326, -- 2312.17742 Learning Vision from Models Rivals Learning Vision from Data
        25462, -- 2401.02020 Spikformer V2: Join the High Accuracy Club on ImageNet with an SNN Ticket
        25570, -- 2401.03844 Fully Attentional Networks with Self-emerging Token Labeling
        26304, -- 2401.14391 Rethinking Patch Dependence for Masked Autoencoders
        26308, -- 2401.14404 Deconstructing Denoising Diffusion Models for Self-Supervised Learning
        26432, -- 2401.16380 Rephrasing the Web: A Recipe for Compute and Data-Efficient Language Modeli
        26578, -- 2402.00645 Spectrally Transformed Kernel Regression
        26766, -- 2402.02444 BECLR: Batch Enhanced Contrastive Few-Shot Learning
        26820, -- 2402.03119 Good Teachers Explain: Explanation-Enhanced Knowledge Distillation
        27029, -- 2402.05382 Task-customized Masked AutoEncoder via Mixture of Cluster-conditional Exper
        27229, -- 2402.08017 Lumos : Empowering Multimodal LLMs with Scene Text Recognition
        27253, -- 2402.08345 Conditional Information Gain Trellis
        27316, -- 2402.09240 Switch EMA: A Free Lunch for Better Flatness and Sharpness
        27519, -- 2402.11566 Boosting Semi-Supervised 2D Human Pose Estimation by Revisiting Data Augmen
        27814, -- 2402.14579 Text Role Classification in Scientific Charts Using Multimodal Transformers
        27833, -- 2402.14789 Self-Guided Masked Autoencoders for Domain-Agnostic Self-Supervised Learnin
        28201, -- 2402.19305 HyenaPixel: Global Image Context with Convolutions
        28242, -- 2403.00504 Learning and Leveraging World Models in Visual Representation Learning
        28244, -- 2403.00522 VisionLLaMA: A Unified LLaMA Backbone for Vision Tasks
        28251, -- 2403.00691 Tri-Modal Motion Retrieval by Learning a Joint Embedding Space
        28431, -- 2403.03095 Cross Pseudo-Labeling for Semi-Supervised Audio-Visual Source Localization
        28437, -- 2403.03145 Dual Mean-Teacher: An Unbiased Semi-Supervised Framework for Audio-Visual S
        28591, -- 2403.05490 Poly-View Contrastive Learning
        28594, -- 2403.05523 Beyond Finite Data: Towards Data-free Out-of-distribution Generalization vi
        28710, -- 2403.07366 Entropy is not Enough for Test-Time Adaptation: From the Perspective of Dis
        28865, -- 2403.09500 Faceptor: A Generalist Model for Face Perception
        28899, -- 2403.09977 EfficientVMamba: Atrous Selective Scan for Light Weight Visual Mamba
        28930, -- 2403.10476 Approximate Nullspace Augmented Finetuning for Robust Vision Transformers
        29038, -- 2403.11808 Dynamic Tuning Towards Parameter and Inference Efficiency for ViT Adaptatio
        29053, -- 2403.11999 HIRI-ViT: Scaling Vision Transformer with High Resolution Inputs
        29303, -- 2403.14852 KeyPoint Relative Position Encoding for Face Recognition
        29476, -- 2403.17695 PlainMamba: Improving Non-Hierarchical Mamba in Visual Recognition
        29537, -- 2403.18361 ViTAR: Vision Transformer with Any Resolution
        29616, -- 2403.19522 Model Stock: All we need is just a few fine-tuned models
        29620, -- 2403.19588 DenseNets Reloaded: Paradigm Shift Beyond ResNets and ViTs
        29645, -- 2403.19888 MambaMixer: Efficient Selective State Space Models with Dual Token and Chan
        29725, -- 2404.00648 SpiralMLP: A Lightweight Vision MLP Architecture
        29850, -- 2404.02041 SelfPose3d: Self-Supervised Multi-Person Multi-View 3d Pose Estimation
        30078, -- 2404.05559 TIM: A Time Interval Machine for Audio-Visual Action Recognition
        30166, -- 2404.06773 Adapting LLaMA Decoder to Vision Transformer
        30267, -- 2404.08197 Scaling (Down) CLIP: A Comprehensive Analysis of Data, Architecture, and Tr
        30418, -- 2404.10518 MobileNetV4 - Universal Models for the Mobile Ecosystem
        30459, -- 2404.11202 GhostNetV3: Exploring the Training Strategies for Compact Models
        30564, -- 2404.12608 Auto-Formula: Recommend Formulas in Spreadsheets using Contrastive Learning
        31055, -- 2405.02296 Möbius Transform for Mitigating Perspective Distortions in Representation L
        31058, -- 2405.02363 LLM as Dataset Analyst: Subpopulation Structure Discovery with Large Langua
        31226, -- 2405.07364 BoQ: A Place is Worth a Bag of Learnable Queries
        31265, -- 2405.07992 MambaOut: Do We Really Need Mamba for Vision?
        31475, -- 2405.12847 A Dataset and Baselines for Measuring and Predicting the Music Piece Memora
        31549, -- 2405.13985 LookHere: Vision Transformers with Directed Attention Generalize and Extrap
        31927, -- 2405.18240 MSPE: Multi-Scale Patch Embedding Prompts Vision Transformers to Any Resolu
        32339, -- 2406.02862 Rethinking Guidance Information to Utilize Unlabeled Samples:A Label Encodi
        32899, -- 2406.09406 4M-21: An Any-to-Any Vision Model for Tens of Tasks and Modalities
        32905, -- 2406.09415 An Image is Worth More Than 16x16 Patches: Exploring Transformers on Indivi
        33248, -- 2406.12452 Insect Identification in the Wild: The AMI Dataset
        33422, -- 2406.14568 Policy Gradient-Driven Noise Mask
        33660, -- 2406.17536 MedMNIST-C: Comprehensive benchmark and improved classifier robustness by s
        34269, -- 2407.05528 An accurate detection is not all you need to combat label noise in web-nois
        34437, -- 2407.07805 SUMix: Mixup with Semantic and Uncertain Information
        34466, -- 2407.08209 Enriching Information and Preserving Semantic Consistency in Expanding Curv
        34490, -- 2407.08476 VideoMamba: Spatio-Temporal Selective State Space Model
        34987, -- 2407.14726 MetaAug: Meta-Data Augmentation for Post-Training Quantization
        35043, -- 2407.15447 SIGMA:Sinkhorn-Guided Masked Video Modeling
        35422, -- 2408.00350 A Simple Background Augmentation Method for Object Detection with Diffusion
        35478, -- 2408.01099 Contribution-based Low-Rank Adaptation with Pre-training Model for Real Ima
        35629, -- 2408.03703 CAS-ViT: Convolutional Additive Self-attention Vision Transformers for Effi
        35910, -- 2408.08855 DPA: Dual Prototypes Alignment for Unsupervised Adaptation of Vision-Langua
        36030, -- 2408.10940 A Closer Look at Data Augmentation Strategies for Finetuning-Based Low/Few-
        36199, -- 2408.13632 FungiTastic: A multi-modal dataset and benchmark for image categorization
        36405, -- 2408.17059 A Survey of the Self Supervised Learning Mechanisms for Vision Transformers
        36408, -- 2408.17081 Stochastic Layer-Wise Shuffle: A Good Practice to Improve Vision Mamba Trai
        36800, -- 2409.07940 Control+Shift: Generating Controllable Distribution Shifts
        36951, -- 2409.10594 Kolmogorov-Arnold Transformer
        37321, -- 2409.16949 DALDA: Data Augmentation Leveraging Diffusion Model and LLM with Adaptive G
        37372, -- 2409.17777 Harnessing Shared Relations via Multimodal Mixup Contrastive Learning for M
        38050, -- 2410.05583 NegMerge: Consensual Weight Negation for Strong Machine Unlearning
        38117, -- 2410.06373 Unveiling the Backbone-Optimizer Coupling Bias in Visual Representation Lea
        38377, -- 2410.09704 EchoPrime: A Multi-Video View-Informed Vision-Language Model for Comprehens
        38565, -- 2410.11842 MoH: Multi-Head Attention as Mixture-of-Head Attention
        38799, -- 2410.14379 AnomalyNCD: Towards Novel Anomaly Class Discovery in Industrial Scenarios
        38806, -- 2410.14470 How Do Training Methods Influence the Utilization of Vision Models?
        39437, -- 2410.23831 FRoundation: Are Foundation Models Ready for Face Recognition?
        39702, -- 2411.04125 Community Forensics: Using Thousands of Generators to Train Fake Image Dete
        39752, -- 2411.04967 AsCAN: Asymmetric Convolution-Attention Networks for Efficient Recognition
        39779, -- 2411.05222 Don't Look Twice: Faster Video Transformers with Run-Length Tokenization
        39916, -- 2411.07635 Breaking the Low-Rank Dilemma of Linear Attention
        40015, -- 2411.09702 On the Surprising Effectiveness of Attention Transfer for Vision Transforme
        40394, -- 2411.15941 MobileMamba: Lightweight Multi-Receptive Visual Mamba Network
        40649, -- 2411.19067 MaskRIS: Semantic Distortion-aware Data Augmentation for Referring Image Se
        40800, -- 2412.00965 Token Cropr: Faster ViTs for Quite a Few Tasks
        40869, -- 2412.01876 Understanding Bias in Large-Scale Visual Datasets
        40902, -- 2412.02366 GenMix: Effective Data Augmentation with Generative Diffusion Model Image E
        40937, -- 2412.02890 EvRT-DETR: Latent Space Adaptation of Image Detectors for Event-based Visio
        41238, -- 2412.06590 Bridging the Divide: Reconsidering Softmax and Linear Attention
        41592, -- 2412.10995 RapidNet: Multi-Level Dilated Convolution Based Mobile Backbone
        41955, -- 2412.15358 Dataset Augmentation by Mixing Visual Concepts
        41997, -- 2412.16146 Mamba2D: A Natively Multi-Dimensional State-Space Model for Vision Tasks
        42413, -- 2501.01245 SeFAR: Semi-supervised Fine-grained Action Recognition with Temporal Pertur
        42908, -- 2501.09436 Scaling up self-supervised learning for improved surgical foundation models
        42924, -- 2501.09705 Practical Continual Forgetting for Pre-trained Vision Models
        42956, -- 2501.10040 LWGANet: A Lightweight Group Attention Backbone for Remote Sensing Visual T
        43726, -- 2502.03654 Gompertz Linear Units: Leveraging Asymmetry for Enhanced Learning Dynamics
        43841, -- 2502.05153 Hummingbird: High Fidelity Image Generation via Multimodal Context Alignmen
        44924, -- 2502.17237 MegaLoc: One Retrieval to Place Them All
        45408, -- 2503.02393 Vision-Language Model IP Protection via Prompt-based Learning
        45662, -- 2503.06132 USP: Unified Self-Supervised Pretraining for Image Generation and Understan
        45958, -- 2503.09399 ForAug: Recombining Foregrounds and Backgrounds to Improve Vision Transform
        46072, -- 2503.10622 Transformers without Normalization
        46320, -- 2503.14237 Make Your Training Flexible: Towards Deployment-Efficient Video Models
        46462, -- 2503.16184 Accurate Scene Text Recognition with Efficient Model Scaling and Cloze Self
        46475, -- 2503.16311 Structured-Noise Masked Modeling for Video, Audio and Beyond
        46623, -- 2503.18371 Do Your Best and Get Enough Rest for Continual Learning
        46985, -- 2503.23135 LSNet: See Large, Focus Small
        47103, -- 2504.00527 SMILE: Infusing Spatial and Motion Semantics in Masked Video Learning
        47152, -- 2504.01395 From Easy to Hard: Building a Shortcut for Differentially Private Image Syn
        47383, -- 2504.05301 S^4M: Boosting Semi-Supervised Instance Segmentation with SAM
        47505, -- 2504.07835 Pychop: Emulating Low-Precision Arithmetic in Numerical Methods and Neural
        48765, -- 2505.10251 SRT-H: A Hierarchical Framework for Autonomous Surgery via Language Conditi
        49095, -- 2505.13813 FlashKAT: Understanding and Addressing Performance Bottlenecks in the Kolmo
        49275, -- 2505.15248 VET-DINO: Learning Anatomical Understanding Through Multi-View Distillation
        50229, -- 2505.24443 Diversify and Conquer: Open-set Disagreement for Robust Semi-supervised Lea
        50808, -- 2506.07998 Generative Modeling of Weights: Generalization or Memorization?
        51002, -- 2506.10390 DART: Differentiable Dynamic Adaptive Region Tokenizer for Vision Transform
        51197, -- 2506.14202 DiffusionBlocks: Blockwise Training for Generative Models via Score-Based D
        53773, -- 2510.18091 Accelerating Vision Transformers with Adaptive Patch Sizes
        53852, -- 2510.23479 MergeMix: A Unified Augmentation Paradigm for Visual and Multi-Modal Unders
        54456, -- 2512.01342 InternVideo-Next: Towards General Video Foundation Models without Video-Tex
        54865, -- 2512.16922 Next-Embedding Prediction Makes Strong Vision Learners
        56057, -- 2602.09021 χ_{0}: Resource-Aware Robust Manipulation via Taming Distributional Inconsi
        56441, -- 2603.02667 DREAM: Where Visual Understanding Meets Text-to-Image Generation
        56496, -- 2603.04892 Locality-Attending Vision Transformer
        58295, -- 2512.08217 Correction of Decoupled Weight Decay
        59262, -- 2603.16423 SF-Mamba: Rethinking State Space Model for Vision
        59565, -- 2603.10834 On the Reliability of Cue Conflict and Beyond
        60027, -- 2603.01944 MobileMold: A Smartphone-Based Microscopy Dataset for Food Mold Detection
        61102, -- 2602.06450 What Is Wrong with Synthetic Data for Scene Text Recognition? A Strong Synt
        61363, -- 2602.03123 Beyond Cropping and Rotation: Automated Evolution of Powerful Task-Specific
        61370, -- 2602.03039 HP-GAN: Harnessing pretrained networks for GAN improvement with FakeTwins a
        61519, -- 2602.01418 Where to Attend: A Principled Vision-Centric Position Encoding with Parabol
        62374, -- 2507.16559 Comparative validation of surgical phase recognition, instrument keypoint e
        64074, -- 2512.05663 LeAD-M3D: Leveraging Asymmetric Distillation for Real-time Monocular 3D Det
        64649, -- 2511.19718 Rethinking Vision Transformer Depth via Structural Reparameterization
        65089, -- 2511.11725 Do Blind Spots Matter for Word-Referent Mapping? A Computational Study with
        65677, -- 2510.25480 Gradient-Weight Alignment as a Train-Time Proxy for Generalization in Class
        67364, -- 2509.25682 OmniDFA: A Unified Framework for Open Set Synthesis Image Detection and Few
        67995, -- 2509.17971 Intra-Cluster Mixup: An Effective Data Augmentation Technique for Complemen
        68140, -- 2509.15861 ToFU: Transforming How Federated Learning Systems Forget User Data
        68516, -- 2509.08959 CoSwin: Convolution Enhanced Hierarchical Shifted Window Attention For Smal
        68715, -- 2509.04669 VCMamba: Bridging Convolutions with Multi-Directional Mamba for Efficient V
        68865, -- 2509.02627 A Two-Stage Strategy for Mitosis Detection Using Improved YOLO11x Proposals
        70250, -- 2508.02671 Raw Data Matters: Enhancing Prompt Tuning by Internal Augmentation on Visio
        70505, -- 2507.23188 Multi-Modal Motion Retrieval by Learning a Fine-Grained Joint Embedding Spa
        70549, -- 2508.00922 CaliMatch: Adaptive Calibration for Improving Safe Semi-supervised Learning
        70714, -- 2507.19409 Modality Agnostic Efficient Long Range Encoder
        70778, -- 2507.18323 SemiSegECG: A Multi-Dataset Benchmark for Semi-Supervised Semantic Segmenta
        70913, -- 2507.15857 Diffusion Beats Autoregressive in Data-Constrained Settings
        71875, -- 2506.15940 Polyline Path Masked Attention for Vision Transformer
        71913, -- 2506.15051 Sequential Policy Gradient for Adaptive Hyperparameter Optimization
        72018, -- 2506.11515 Manager: Aggregating Insights from Unimodal Experts in Two-Tower VLMs and M
        72335, -- 2506.02803 SemVink: Advancing VLMs' Semantic Understanding of Optical Illusions via Vi
        72767, -- 2505.18608 Spiking Neural Networks Need High Frequency Information
        73335, -- 2504.18072 A Model Zoo on Phase Transitions in Neural Networks
        73814, -- 2503.23447 CA^2ST: Cross-Attention in Audio, Space, and Time for Holistic Video Recogn
        73858, -- 2503.20823 Playing the Fool: Jailbreaking LLMs and Multimodal LLMs with Out-of-Distrib
        73937, -- 2503.16975 EasyRobust: A Comprehensive and Easy-to-use Toolkit for Robust and Generali
        73956, -- 2503.15986 SpiLiFormer: Enhancing Spiking Transformers with Lateral Inhibition
        74034, -- 2503.12947 DivCon-NeRF: Diverse and Consistent Ray Augmentation for Few-Shot NeRF
        74317, -- 2503.02101 Generalized Diffusion Detector: Mining Robust Features from Diffusion Model
        74903, -- 2502.02977 Efficiently Disentangling CLIP for Multi-Object Perception
        75028, -- 2501.18921 Full-scale Representation Guided Network for Retinal Vessel Segmentation
        75115, -- 2501.12670 Celo: Training Versatile Learned Optimizers on a Compute Diet
        75712, -- 2411.16170 CARE Transformer: Mobile-Friendly Linear Visual Transformer via Decoupled D
        75928, -- 2411.02592 Decoupled Data Augmentation for Improving Image Classification
        76136, -- 2410.05500 Residual Kolmogorov-Arnold Network for Enhanced Deep Learning
        77001, -- 2406.10322 LieRE: Lie Rotational Positional Encodings
        77051, -- 2406.05850 Scaling Graph Convolutions for Mobile Vision
        77605, -- 2403.13430 MTP: Advancing Remote Sensing Foundation Model via Multi-Task Pretraining
        78917, -- 2306.04175 ScoreCL: Augmentation-Adaptive Contrastive Learning via Score-Matching Func
        78971, -- 2305.17455 CrossGET: Cross-Guided Ensemble of Tokens for Accelerating Vision-Language
        79015, -- 2305.12715 Imprecise Label Learning: A Unified Framework for Learning with Various Imp
        79084, -- 2304.14636 PreNAS: Preferred One-Shot Learning Towards Efficient Neural Architecture S
        79534, -- 2211.13929 XKD: Cross-modal Knowledge Distillation with Domain Alignment for Video Rep
        79539, -- 2211.13466 Hierarchical Consistent Contrastive Learning for Skeleton-Based Action Reco
        79614, -- 2211.00453 The Perils of Learning From Unlabeled Data: Backdoor Attacks on Semi-superv
        79836, -- 2207.09176 Self-Supervision Can Be a Good Few-Shot Learner
        80184, -- 2202.10401 Vision-Language Pre-Training with Triple Contrastive Learning
        80219, -- 2202.03775 Addressing Data Scarcity in Multimodal User State Recognition by Combining
        80262, -- 2201.04288 Multiview Transformers for Video Recognition
        80356, -- 2111.15121 Pyramid Adversarial Training Improves ViT Performance
        80382, -- 2111.10493 Discrete Representations Strengthen Vision Transformer Robustness
        80425, -- 2110.13740 DP-SSL: Towards Robust Semi-supervised Learning with A Few Labeled Samples
        80682, -- 2104.10858 All Tokens Matter: Token Labeling for Training Better Vision Transformers
        81443, -- 2002.09564 Towards Robust and Reproducible Active Learning Using Neural Networks
        82831, -- 2605.01711 Linear-Time Global Visual Modeling without Explicit Attention
        84306, -- 2512.01643 ViT$^3$: Unlocking Test-Time Training in Vision
        84634, -- 2602.22917 Towards Multimodal Domain Generalization with Few Labels
        84664, -- 2603.00486 Random Wins All: Rethinking Grouping Strategies for Vision Tokens
        84748, -- 2603.04825 Mitigating Instance Entanglement in Instance-Dependent Partial Label Learni
        84753, -- 2603.04896 Authorize-on-Demand: Dynamic Authorization with Legality-Aware Intellectual
        85339, -- 2604.09989 FlowPalm: Optical Flow Driven Non-Rigid Deformation for Geometrically Diver
        85439, -- 2604.21330 Teacher-Guided Routing for Sparse Vision Mixture-of-Experts
        86096, -- 2510.07823 Enhancing Visual Prompting through Expanded Transformation Space and Overfi
        86487, -- 2509.11711 The Quest for Universal Master Key Filters in DS-CNNs
        86659, -- 2510.15783 ReCon: Region-Controllable Data Augmentation with Rectification and Alignme
        86744, -- 2505.20535 Rotary Masked Autoencoders are Versatile Learners
        86829, -- 2505.18051 LookWhere? Efficient Visual Recognition by Learning Where to Look and What
        86919, -- 2505.18636 Asymmetric Duos: Sidekicks Improve Uncertainty
        86925, -- 2506.04401 Normalize Filters! Classical Wisdom for Deep Vision
        87200, -- 2506.07413 Variational Supervised Contrastive Learning
        87243, -- 2510.15194 Salient Concept-Aware Generative Data Augmentation
        87298, -- 2502.12627 DAMamba: Vision State Space Model with Dynamic Adaptive Scan
        87381, -- 2505.19985 Structured Initialization for Vision Transformers
        87464, -- 2510.11133 Test-Time Adaptation by Causal Trimming
        87622, -- 2508.09000 UniConvNet: Expanding Effective Receptive Field while Maintaining Asymptoti
        87654, -- 2411.08224 Joint Diffusion Models in Continual Learning
        87772, -- 2507.04302 Adversarial Data Augmentation for Single Domain Generalization via Lyapunov
        88094, -- 2507.01384 MUG: Pseudo Labeling Augmented Audio-Visual Mamba Network for Audio-Visual
        88202, -- 2503.06916 You Are Your Own Best Teacher: Achieving Centralized-level Performance in F
        88229, -- 2505.15123 Seeing the Trees for the Forest: Rethinking Weakly-Supervised Medical Visua
        88304, -- 2506.21042 Boosting Domain Generalized and Adaptive Detection with Diffusion Models: F
        88356, -- 2507.10578 When and Where do Data Poisons Attack Textual Inversion?
        88463, -- 2502.20760 VRM: Knowledge Distillation via Virtual Relation Matching
        89136, -- 2503.15748 PARQ: Piecewise-Affine Regularized Quantization
        89282, -- 2406.01425 Adaptive Sensitivity Analysis for Robust Augmentation against Natural Corru
        89449, -- 2410.03039 Leveraging Model Guidance to Extract Training Data from Personalized Diffus
        89667, -- 2502.01980 Generative Data Mining with Longtail-Guided Diffusion
        89901, -- 2504.12883 Mirror, Mirror of the Flow: How Does Regularization Shape Implicit Bias?
        90186, -- 2411.12817 What Makes a Good Dataset for Knowledge Distillation?
        90218, -- 2411.19946 DELT: A Simple Diversity-driven EarlyLate Training for Dataset Distillation
        90425, -- 2504.08710 Hypergraph Vision Transformers: Images are More than Nodes, More than Edges
        90439, -- 2505.12745 PEER Pressure: Model-to-Model Regularization for Single Source Domain Gener
        90448, -- 2503.13227 Mind the Gap: Confidence Discrepancy Can Guide Federated Semi-Supervised Le
        90570, -- 2504.09990 Correlative and Discriminative Label Grouping for Multi-Label Visual Prompt
        90662, -- 2503.14867 DVHGNN: Multi-Scale Dilated Vision HGNN for Efficient Vision Recognition
        90871, -- 2410.15980 Learning from Neighbors: Category Extrapolation for Long-Tail Learning
        90925, -- 2411.10364 Forming Auxiliary High-confident Instance-level Loss to Promote Learning fr
        90992, -- 2411.16788 TIDE: Training Locally Interpretable Domain Generalization Models Enables T
        91079, -- 2410.11206 Towards Understanding Why FixMatch Generalizes Better Than Supervised Learn
        91088, -- 2403.08632 A Decade's Battle on Dataset Bias: Are We There Yet?
        91569, -- 2409.10362 Frequency-Guided Masking for Enhanced Vision Self-Supervised Learning
        91812, -- 2503.06461 Long-tailed Adversarial Training with Self-Distillation
        91844, -- 2402.06855 For Better or For Worse? Learning Minimum Variance Features With Label Augm
        92060, -- 2502.19718 Learning Mask Invariant Mutual Information for Masked Image Modeling
        92245, -- 2411.00121 I Can Hear You: Selective Robust Training for Deepfake Audio Detection
        92255, -- 2311.05589 A Coefficient Makes SVRG Effective
        92344, -- 2410.15143 Budgeted Online Continual Learning by Adaptive Layer Freezing and Frequency
        92519, -- 2210.06583 S4ND: Modeling Images and Videos as Multidimensional Signals Using State Sp
        92576, -- 2606.00558 Semi-Supervised Noise Adaptation: Transferring Knowledge from Noise Domain
        93100, -- 2505.21813 Optimizing Data Augmentation through Bayesian Model Selection
        93186, -- 2509.07103 Lookup multivariate Kolmogorov-Arnold Networks
        93424, -- 2510.07758 Rényi Sharpness: A Novel Sharpness that Strongly Correlates with Generaliza
        93779, -- 2602.03895 Benchmarking Bias Mitigation Toward Fairness Without Harm from Vision to LV
        94511, -- 2602.00205 Reducing Class-Wise Performance Disparity via Margin Regularization
        95027, -- 2509.20284 Biologically Plausible Learning via Bidirectional Spike-Based Distillation
        97172, -- 2503.24298 Order Matters: On Parameter-Efficient Image-To-Video Probing for Recognizin
        98656, -- 2208.05688 Semi-supervised Vision Transformers at Scale
        98670, -- 2606.12036 Vision Transformers for Face Recognition Need More Registers
        98729, -- 2606.16246 Demystifying Training-Time Augmentation for Data-Constrained Language Model
        99095, -- 2607.02271 AGVBench: A Reliability-Oriented Benchmark of Data Augmentation for Vein Re
        99527, -- 2605.23254 CARE: Class-Adaptive Expert Consensus for Reliable Learning with Long-Taile
        100106, -- 2506.08297 SEMA: a Scalable and Efficient Mamba like Attention via Token Localization
        100232, -- 2605.10315 Active Tabular Augmentation via Policy-Guided Diffusion Inpainting
        100712, -- 2412.00452 Learning Locally, Revising Globally: Global Reviser for Federated Learning
        101092, -- 2511.09190 Iterated Population Based Training with Task-Agnostic Restarts
        101230, -- 2606.11236 A$^2$SG: Adaptive and Asymmetric Surrogate Gradients for Training Deep Spik
        101291, -- 2509.20939 Unlocking Noise-Resistant Vision: Key Architectural Secrets for Robust Mode
        105459, -- 2507.05007 Multi-modal Representations for Fine-grained Multi-label Critical View of S
        105908, -- 2407.09359 A Unified Anomaly Synthesis Strategy with Gradient Ascent for Industrial An
        106628, -- 2601.05855 Bidirectional Channel-selective Semantic Interaction for Semi-Supervised Me
        106728, -- 2512.21542 Vision Transformers Are Circulant Attention Learners
        106829, -- 2511.12321 Learning Time in Static Classifiers
        107473, -- 2505.24592 A Flat Minima Perspective on Understanding Augmentations and Model Robustne
        107506, -- 2511.20225 DiCaP: Distribution-Calibrated Pseudo-labeling for Semi-Supervised Multi-La
        107574, -- 2511.09319 DualFete: Revisiting Teacher-Student Interactions from a Feedback Perspecti
        108364, -- 2511.12547 HiGFA: Hierarchical Guidance for Fine-grained Data Augmentation with Diffus
        108433, -- 2508.09525 Learning Spatial Decay for Vision Transformers
        108930, -- 2608.05424 Invisible Shortcuts: Why Vision Encoders Know Your Camera
        109217, -- 2007.03347 SpinalNet: Deep Neural Network with Gradual Input
        109313, -- 2608.14144 Self-Supervised Visual On-Policy Distillation
        110439, -- 2510.09822 Task-Aware Resolution Optimization for Visual Large Language Models
        112416, -- 2311.17325 Alternate Diverse Teaching for Semi-supervised Medical Image Segmentation
        112457, -- 2408.01946 Masked Angle-Aware Autoencoder for Remote Sensing Images
        112487, -- 2409.06665 Data Collection-free Masked Video Modeling
        112527, -- 2407.16802 Distribution-Aware Robust Learning from Long-Tailed Data with Noisy Labels
        112548, -- 2408.12614 Image-Feature Weak-to-Strong Consistency: An Enhanced Paradigm for Semi-Sup
        112707, -- 2409.04820 FreeAugment: Data Augmentation Search Across All Degrees of Freedom
        112756, -- 2407.04616 Isomorphic Pruning for Vision Models
        112910, -- 2406.02774 Diffusion-Refined VQA Annotations for Semi-Supervised Gaze Following
        113114, -- 2407.18624 Dual-Decoupling Learning and Metric-Adaptive Thresholding for Semi-Supervis
        113117, -- 2407.05246 Deep Online Probability Aggregation Clustering
        113149, -- 2407.05848 Wavelet Convolutions for Large Receptive Fields
        113261, -- 2407.11735 ProSub: Probabilistic Open-Set Semi-Supervised Learning with Subspace-Based
        113276, -- 2311.18495 Improving Adversarial Transferability via Model Alignment
        113336, -- 2407.03641 Learning Scalable Model Soup on a Single GPU: An Efficient Subspace Trainin
        113347, -- 2409.06290 EntAugment: Entropy-Driven Adaptive Data Augmentation Framework for Image C
        113358, -- 2407.12568 Echoes of the Past: Boosting Long-tail Recognition via Reflective Learning
        113444, -- 2407.08245 Feature Diversification and Adaptation for Federated Domain Generalization
        113517, -- 2409.20139 Characterizing Model Robustness via Natural Input Gradients
        113586, -- 2407.10052 Augmented Neural Fine-tuning for Efficient Backdoor Purification
        113612, -- 2409.08509 Exploiting Supervised Poison Vulnerability to Strengthen Self-Supervised De
        114310, -- 2409.16702 3DDX: Bone Surface Reconstruction from a Single Standard-Geometry Radiograp
        114944, -- 2403.13341 FissionFusion: Fast Geometric Generation and Hierarchical Souping for Medic
        115470, -- 2304.05600 Looking Similar Sounding Different: Leveraging Counterfactual Cross-Modal P
        115486, -- 2405.14881 DiffuseMix: Label-Preserving Data Augmentation with Diffusion Models
        115688, -- 2403.07589 PeLK: Parameter-efficient Large Kernel ConvNets with Peripheral Convolution
        115727, -- 2307.08919 Systematic Comparison of Semi-supervised and Self-supervised Learning for M
        115732, -- 2312.00600 Improving Plasticity in Online Continual Learning via Collaborative Learnin
        115739, -- 2404.00909 Learning by Correction: Efficient Tuning Task for Zero-Shot Generative Visi
        115750, -- 2401.04727 Revisiting Adversarial Training at Scale
        115804, -- 2403.11184 DuPL: Dual Student with Trustworthy Progressive Learning for Robust Weakly
        115860, -- 2403.10519 Frozen Feature Augmentation for Few-Shot Image Classification
        115865, -- 2403.10073 Revisiting Adversarial Training Under Long-Tailed Distributions
        115878, -- 2404.01179 BEM: Balanced and Entropy-based Mix for Long-Tailed Semi-Supervised Learnin
        115966, -- 2312.06420 Localization Is All You Evaluate: Data Leakage in Online Mapping Datasets a
        116031, -- 2311.16833 1-Lipschitz Layers Compared: Memory Speed and Certifiable Robustness
        116168, -- 2403.06676 CAM Back Again: Large Kernel CNNs from a Weakly Supervised Object Localizat
        116179, -- 2406.06820 Adapters Strike Back
        116206, -- 2403.11162 CGI-DM: Digital Copyright Authentication for Diffusion Models via Contrasti
        116328, -- 2403.15605 Efficiently Assemble Normalization Layers and Regularization for Federated
        116453, -- 2305.16316 Making Vision Transformers Truly Shift-Equivariant
        116481, -- 2311.03149 Asymmetric Masked Distillation for Pre-Training Small Foundation Models
        116488, -- 2403.10391 CDMAD: Class-Distribution-Mismatch-Aware Debiasing for Class-Imbalanced Sem
        116616, -- 2312.02914 Unsupervised Video Domain Adaptation with Masked Pre-Training and Collabora
        116667, -- 2311.18695 Seg2Reg: Differentiable 2D Segmentation to 1D Regression Rendering for 360
        116683, -- 2403.02899 Domain-Agnostic Mutual Prompting for Unsupervised Domain Adaptation
        116699, -- 2403.15194 Your Image is My Video: Reshaping the Receptive Field via Image-To-Video Di
        116749, -- 2403.01944 Fourier-basis Functions to Bridge Augmentation Gap: Rethinking Frequency Au
        116844, -- 2403.18550 OrCo: Towards Better Generalization via Orthogonality and Contrast for Few-
        116861, -- 2403.18360 Learning CNN on ViT: A Hybrid Model to Explicitly Class-specific Boundaries
        116874, -- 2311.16081 ViT-Lens: Towards Omni-modal Representations
        117086, -- 2402.18133 Classes Are Not Equal: An Empirical Study on Image Recognition Fairness
        117106, -- 2403.02991 MADTP: Multimodal Alignment-Guided Dynamic Token Pruning for Accelerating V
        117145, -- 2404.01976 Joint-Task Regularization for Partially Labeled Multi-Task Learning
        117172, -- 2304.12160 End-to-End Spatio-Temporal Action Localisation with Video Transformers
        117173, -- 2403.06247 Text-Guided Variational Image Generation for Industrial Anomaly Detection a
        118907, -- 2608.20710 Geometric Regularization for Long-Tailed Semi-Supervised Learning via Gauss
        119292, -- 2606.24361 SignNet-1M: Large-Scale Multilingual Sign Language Video Dataset with Downs
        119550, -- 2608.22665 Hyperbolic Hierarchical Clustering for Visual Representation Learning
        120057, -- 2503.18312 Diff-Palm: Realistic Palmprint Generation with Polynomial Creases and Intra
        120153, -- 2506.15720 Tripartite Weight-Space Ensemble for Few-Shot Class-Incremental Learning
        120397, -- 2412.12423 GG-SSMs: Graph-Generating State Space Models
        121647, -- 2511.20263 Advancing Image Classification with Discrete Diffusion Classification Model
        122038, -- 2111.09957 Rethinking Dilated Convolution for Real-time Semantic Segmentation
        123076, -- 2007.15161 Rethinking Recurrent Neural Networks and Other Improvements for Image Class
        124769, -- 2604.06689 Generative Cross-Entropy: A Strictly Proper Loss for Data-Efficient Classif
        125997, -- 2610.09609 Decoupled Optimization for Teacher-Student Semi-Supervised Learning via a P
        126788, -- 2609.04698 LookThere! Sparse Vision by Reinforced Selection
        128599, -- 2609.30478 The Shape of Events: Edge-Based Inductive Biases via Cross-Domain Distillat
        129649, -- 2610.04457 RPFQ-ViT: Rotated Phase-Frame Quantization for Extremely Low-Bit Weights in
        129667, -- 2603.24275 Language-Assisted Image Clustering Guided by Discriminative Relational Sign
        131358, -- 2608.25710 Difficulty-Aware Sample Allocation for Adaptive Data Augmentation in Semant
        132073  -- 2001.07685 FixMatch: Simplifying Semi-Supervised Learning with Consistency and Confide
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
        177, -- 1504.02531 HEp-2 Cell Image Classification with Deep Convolutional Neural Networks
        184, -- 1505.04597 U-Net: Convolutional Networks for Biomedical Image Segmentation
        349, -- 1604.00790 Image Captioning with Deep Bidirectional LSTMs
        411, -- 1606.06472 DeepWriter: A Multi-Stream Deep CNN for Text-independent Writer Identificat
        413, -- 1606.06650 3D U-Net: Learning Dense Volumetric Segmentation from Sparse Annotation
        520, -- 1611.08663 Multi-Task Zero-Shot Action Recognition with Prioritised Data Augmentation
        742, -- 1706.02047 Stacked Convolutional and Recurrent Neural Networks for Bird Audio Detectio
        843, -- 1708.04552 Improved Regularization of Convolutional Neural Networks with Cutout
        848, -- 1708.04896 Random Erasing Data Augmentation
        1014, -- 1712.04621 The Effectiveness of Data Augmentation in Image Classification using Deep L
        1181, -- 1803.09655 BAGAN: Data Augmentation with Balancing GAN
        1231, -- 1804.06876 Gender Bias in Coreference Resolution: Evaluation and Debiasing Methods
        1283, -- 1805.05838 Gradient-Leaks: Understanding and Controlling Deanonymization in Federated
        1298, -- 1805.09501 AutoAugment: Learning Augmentation Policies from Data
        1301, -- 1805.10766 Improving the Resolution of CNN Feature Maps Efficiently with Multisampling
        1445, -- 1808.07231 Reducing Gender Bias in Abusive Language Detection
        1485, -- 1809.02499 MixUp as Locally Linear Out-Of-Manifold Regularization
        1679, -- 1812.01278 Singing Voice Separation Using a Deep Convolutional Neural Network Trained
        1793, -- 1901.11196 EDA: Easy Data Augmentation Techniques for Boosting Performance on Text Cla
        1794, -- 1901.11369 Cross-modality (CT-MRI) prior augmented deep learning for robust lung tumor
        1828, -- 1902.06818 Data augmentation for low resource sentiment analysis using generative adve
        1850, -- 1902.09811 LaSO: Label-Set Operations networks for multi-label few-shot learning
        1880, -- 1903.03088 Self-Tuning Networks: Bilevel Optimization of Hyperparameters using Structu
        2016, -- 1904.08779 SpecAugment: A Simple Data Augmentation Method for Automatic Speech Recogni
        2027, -- 1904.09679 Investigating Prior Knowledge for Challenging Chinese Machine Reading Compr
        2050, -- 1904.12848 Unsupervised Data Augmentation for Consistency Training
        2051, -- 1904.13132 A critical analysis of self-supervision, or what we can learn from a single
        2065, -- 1905.01492 SoilingNet: Soiling Detection on Automotive Surround-View Cameras
        2191, -- 1906.00910 Learning Representations by Maximizing Mutual Information Across Views
        2244, -- 1906.04571 Counterfactual Data Augmentation for Mitigating Gender Stereotypes in Langu
        2305, -- 1907.00494 The University of Sydney's Machine Translation System for WMT19
        2354, -- 1907.07174 Natural Adversarial Examples
        2445, -- 1908.08681 Mish: A Self Regularized Non-Monotonic Activation Function
        2486, -- 1909.00871 It's All in the Name: Mitigating Gender Bias with Name-Based Counterfactual
        2526, -- 1909.04696 Sunny and Dark Outside?! Improving Answer Consistency in VQA through Entail
        2618, -- 1909.13719 RandAugment: Practical automated data augmentation with a reduced search sp
        2697, -- 1910.08772 MonaLog: a Lightweight System for Natural Language Inference Based on Monot
        2772, -- 1911.02590 Optimizing Millions of Hyperparameters by Implicit Differentiation
        2783, -- 1911.03118 Not Enough Data? Deep Learning to the Rescue!
        2800, -- 1911.04252 Self-training with Noisy Student improves ImageNet classification
        2854, -- 1911.10484 Task-Oriented Dialog Systems that Consider Multiple Appropriate Responses u
        2878, -- 1911.13254 Music Source Separation in the Waveform Domain
        2957, -- 1912.11035 CNN-generated images are surprisingly easy to spot... for now
        2994, -- 2001.04086 GridMask Data Augmentation
        3023, -- 2001.08604 Variational Hierarchical Dialog Autoencoder for Dialog State Tracking Data
        3030, -- 2001.09598 FakeLocator: Robust Localization of GAN-Based Face Manipulations
        3066, -- 2002.01359 Schema-Guided Dialogue State Tracking Task at DSTC8
        3098, -- 2002.05709 A Simple Framework for Contrastive Learning of Visual Representations
        3143, -- 2002.11102 On Feature Normalization and Data Augmentation
        3151, -- 2002.12047 FMix: Enhancing Mixed Sample Data Augmentation
        3172, -- 2003.01473 XGPT: Cross-modal Generative Pre-Training for Image Captioning
        3179, -- 2003.02245 Data Augmentation using Pre-trained Transformer Models
        3181, -- 2003.02484 Adversarial Vertex Mixup: Toward Better Adversarially Robust Generalization
        3198, -- 2003.04297 Improved Baselines with Momentum Contrastive Learning
        3266, -- 2003.13048 Attentive CutMix: An Enhanced Data Augmentation Approach for Deep Learning
        3286, -- 2004.00584 Deep Entity Matching with Pre-Trained Language Models
        3328, -- 2004.04487 Injecting Numerical Reasoning Skills into Language Models
        3375, -- 2004.08531 MatchboxNet: 1D Time-Channel Separable Convolutional Neural Network Archite
        3379, -- 2004.09015 Incorporating External Knowledge through Pre-training for Natural Language
        3396, -- 2004.10934 YOLOv4: Optimal Speed and Accuracy of Object Detection
        3401, -- 2004.11362 Supervised Contrastive Learning
        3435, -- 2004.13649 Image Augmentation Is All You Need: Regularizing Deep Reinforcement Learnin
        3447, -- 2004.14200 Syntax-aware Data Augmentation for Neural Machine Translation
        3472, -- 2004.14874 Progressive Transformers for End-to-End Sign Language Production
        3522, -- 2005.01854 Data Augmentation for Hypernymy Detection
        3585, -- 2005.08072 Speech Recognition and Multi-Speaker Diarization of Long Conversations
        3738, -- 2006.09882 Unsupervised Learning of Visual Features by Contrasting Cluster Assignments
        3749, -- 2006.10511 Contrastive learning of global and local features for medical image segment
        3786, -- 2006.12847 Real Time Speech Enhancement in the Waveform Domain
        3828, -- 2006.16241 The Many Faces of Robustness: A Critical Analysis of Out-of-Distribution Ge
        3882, -- 2007.05929 Data-Efficient Reinforcement Learning with Self-Predictive Representations
        3931, -- 2007.12865 Self-supervised Learning for Large-scale Item Recommendations
        3949, -- 2007.14895 Reliable Tuberculosis Detection using Chest X-ray with Deep Learning, Segme
        3974, -- 2008.00702 Multimodal Semi-supervised Learning Framework for Punctuation Prediction in
        4000, -- 2008.03800 Spatiotemporal Contrastive Video Representation Learning
        4015, -- 2008.05348 Approaching Neural Chinese Word Segmentation as a Low-Resource Machine Tran
        4112, -- 2009.02792 Overview and Evaluation of Sound Event Localization and Detection in DCASE
        4153, -- 2009.07378 BOP Challenge 2020 on 6D Object Localization
        4156, -- 2009.07724 SelfAugment: Automatic Augmentation Policies for Self-Supervised Learning
        4237, -- 2010.00571 Understanding tables with intermediate pre-training
        4238, -- 2010.00578 Understanding Self-supervised Learning with Dual Deep Networks
        4243, -- 2010.01028 Hard Negative Mixing for Contrastive Learning
        4256, -- 2010.01764 How Effective is Task-Agnostic Data Augmentation for Pretrained Transformer
        4332, -- 2010.05549 Improving Low Resource Code-switched ASR using Augmented Code-switched TTS
        4362, -- 2010.08191 RocketQA: An Optimized Training Approach to Dense Passage Retrieval for Ope
        4363, -- 2010.08240 Augmented SBERT: Data Augmentation Method for Improving Bi-Encoders for Pai
        4469, -- 2010.15411 Conversation Graph: Data Augmentation, Training and Evaluation for Non-Dete
        4470, -- 2010.15464 Pretext-Contrastive Learning: Toward Good Practices in Self-supervised Vide
        4504, -- 2011.02686 Investigating Societal Biases in a Poetry Composition System
        4506, -- 2011.02821 Data Augmentation and Terminology Integration for Domain-Specific Sinhala-E
        4528, -- 2011.04184 Text Classification through Glyph-aware Disentangled Character Embedding an
        4584, -- 2011.09832 Differentiable Data Augmentation with Kornia
        4589, -- 2011.10082 Hybrid Consistency Training with Prototype Adaptation for Few-Shot Learning
        4599, -- 2011.11186 Cancer image classification based on DenseNet model
        4619, -- 2011.13046 Can Temporal Information Help with Contrastive Self-Supervised Learning?
        4627, -- 2011.13389 Generalization in Reinforcement Learning by Soft Data Augmentation
        4672, -- 2012.02909 What Makes a "Good" Data Augmentation in Knowledge Distillation - A Statis
        4683, -- 2012.03457 VideoMix: Rethinking Data Augmentation for Video Classification
        4726, -- 2012.06734 PoP-Net: Pose over Parts Network for Multi-Person 3D Pose Estimation from a
        4730, -- 2012.07177 Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segment
        4763, -- 2012.11101 ResizeMix: Mixing Data with Preserved Object Information and True Labels
        4809, -- 2012.15262 Robustness Testing of Language Understanding in Task-Oriented Dialog
        4888, -- 2101.04530 Data augmentation and feature selection for automatic model recommendation
        4907, -- 2101.06639 Removing Undesirable Feature Contributions Using Out-of-Distribution Data
        4912, -- 2101.07589 Hyperspectral Image Super-Resolution with Spectral Mixup and Heterogeneous
        4930, -- 2101.09433 A Pressure Ulcer Care System For Remote Medical Assistance: Residual U-Net
        4972, -- 2102.01243 PSLA: Improving Audio Tagging with Pretraining, Sampling, Labeling, and Agg
        5022, -- 2102.06171 High-Performance Large-Scale Image Recognition Without Normalization
        5044, -- 2102.08183 Comparison of semi-supervised deep learning algorithms for audio classifica
        5085, -- 2102.12060 Teach Me to Explain: A Review of Datasets for Explainable Natural Language
        5121, -- 2103.01006 GaNDLF: A Generally Nuanced Deep Learning Framework for Scalable End-to-End
        5127, -- 2103.01458 Diffusion Probabilistic Models for 3D Point Cloud Generation
        5186, -- 2103.06695 BYOL for Audio: Self-Supervised Learning for General-Purpose Audio Represen
        5213, -- 2103.09410 Contrastive Learning of Musical Representations
        5241, -- 2103.11471 Conditional Generative Adversarial Networks for Speed Control in Trajectory
        5283, -- 2103.14453 Data Augmentation in Natural Language Processing: A Novel Text Generation A
        5285, -- 2103.14542 Unsupervised Document Embedding via Contrastive Augmentation
        5298, -- 2103.15375 AlignMixup: Improving Representations By Interpolating Aligned Features
        5341, -- 2104.00298 EfficientNetV2: Smaller Models and Faster Training
        5400, -- 2104.04015 CutPaste: Self-Supervised Learning for Anomaly Detection and Localization
        5444, -- 2104.06609 Representative Forgery Mining for Fake Face Detection
        5488, -- 2104.08244 Open data for Moroccan license plates for OCR applications : data collectio
        5522, -- 2104.08821 SimCSE: Simple Contrastive Learning of Sentence Embeddings
        5523, -- 2104.08826 GPT3Mix: Leveraging Large-scale Language Models for Text Augmentation
        5597, -- 2104.13497 ConTNet: Why not use convolution and transformer at the same time?
        5613, -- 2104.14690 Entailment as Few-Shot Learner
        5658, -- 2105.03075 A Survey of Data Augmentation Approaches for NLP
        5664, -- 2105.03323 TITAN: T Cell Receptor Specificity Prediction with Bimodal Attention Networ
        5667, -- 2105.03404 ResMLP: Feedforward networks for image classification with data-efficient t
        5680, -- 2105.04070 Robust Training Using Natural Transformation
        5750, -- 2105.08582 Vision Transformer for Fast and Efficient Scene Text Recognition
        5760, -- 2105.09501 Contrastive Learning for Many-to-many Multilingual Neural Machine Translati
        5798, -- 2105.13650 Data Augmentation for Text Generation Without Any Augmented Data
        5831, -- 2106.00221 Concurrent Adversarial Learning for Large-Batch Training
        5860, -- 2106.01548 When Vision Transformers Outperform ResNets without Pre-training or Strong
        5898, -- 2106.03374 RegMix: Data Mixing Augmentation for Regression
        5912, -- 2106.04016 Disfl-QA: A Benchmark Dataset for Understanding Disfluencies in Question An
        5919, -- 2106.04531 RobustNav: Towards Benchmarking Robustness in Embodied Navigation
        5933, -- 2106.04990 It Takes Two to Tango: Mixup for Deep Metric Learning
        5989, -- 2106.07345 Self-Guided Contrastive Learning for BERT Sentence Representations
        5991, -- 2106.07499 An Empirical Survey of Data Augmentation for Limited Data Learning in NLP
        6014, -- 2106.08601 Self-Supervised GANs with Label Augmentation
        6023, -- 2106.09296 Voice2Series: Reprogramming Acoustic Models for Time Series Classification
        6051, -- 2106.10270 How to train your ViT? Data, Augmentation, and Regularization in Vision Tra
        6144, -- 2106.15231 Exploring the Efficacy of Automatically Generated Counterfactuals for Senti
        6145, -- 2106.15282 Cascaded Diffusion Models for High Fidelity Image Generation
        6147, -- 2106.15320 ScanBank: A Benchmark Dataset for Figure Extraction from Scanned Electronic
        6166, -- 2107.00644 Stabilizing Deep Q-Learning with ConvNets and Vision Transformers under Dat
        6220, -- 2107.05295 DaCy: A Unified Framework for Danish NLP
        6247, -- 2107.07150 Tailor: Generating and Perturbing Text with Semantic Controls
        6281, -- 2107.09645 Mastering Visual Continuous Control: Improved Data-Augmented Reinforcement
        6293, -- 2107.10471 Improving Polyphonic Sound Event Detection on Multichannel Recordings with
        6352, -- 2108.01280 A Study of Multilingual End-to-End Speech Recognition for Kazakh, Russian,
        6374, -- 2108.02982 Improving Contrastive Learning by Visualizing Feature Transformation
        6428, -- 2108.06949 Data Augmentation for Scene Text Recognition
        6468, -- 2108.10248 Influence-guided Data Augmentation for Neural Tensor Completion
        6472, -- 2108.10510 Contrastive Learning of User Behavior Sequence for Context-Aware Document R
        6520, -- 2108.13939 ScatSimCLR: self-supervised contrastive learning with pretext task regulari
        6572, -- 2109.03856 Local Augmentation for Graph Neural Networks
        6583, -- 2109.04380 ESimCSE: Enhanced Sample Building Method for Contrastive Learning of Unsupe
        6669, -- 2109.08535 Simple Entity-Centric Questions Challenge Dense Retrievers
        6688, -- 2109.09667 On Generalization in Coreference Resolution
        6704, -- 2109.11105 Distiller: A Systematic Study of Model Distillation Methods in Natural Lang
        6759, -- 2109.15107 CrossAug: A Contrastive Data Augmentation Method for Debiasing Fact Verific
        6761, -- 2109.15222 Natural Synthetic Anomalies for Self-Supervised Anomaly Detection and Local
        6769, -- 2110.00476 ResNet strikes back: An improved training procedure in timm
        6791, -- 2110.01852 Data Augmentation Approaches in Natural Language Processing: A Survey
        6800, -- 2110.02210 Mix3D: Out-of-Context Data Augmentation for 3D Scenes
        6878, -- 2110.05752 UniSpeech-SAT: Universal Speech Representation Learning with Speaker Aware
        6883, -- 2110.05892 Investigation on Data Adaptation Techniques for Neural Named Entity Recogni
        6915, -- 2110.06800 SGD-X: A Benchmark for Robust Generalization in Schema-Guided Dialogue Syst
        6936, -- 2110.07367 RocketQAv2: A Joint Training Method for Dense Passage Retrieval and Passage
        6983, -- 2110.08527 An Empirical Survey of the Effectiveness of Debiasing Techniques for Pre-tr
        6996, -- 2110.08890 Network Augmentation for Tiny Deep Learning
        7019, -- 2110.11144 RCT: Random Consistency Training for Semi-supervised Sound Event Detection
        7119, -- 2111.00743 Towards the Generalization of Contrastive Self-Supervised Learning
        7138, -- 2111.01754 Meta-Learning to Improve Pre-Training
        7154, -- 2111.02549 VORTEX: Physics-Driven Data Augmentations Using Consistency Training for Ro
        7168, -- 2111.03789 Generation of microbial colonies dataset with deep learning style transfer
        7202, -- 2111.06474 AnswerSumm: A Manually-Curated Dataset and Pipeline for Answer Summarizatio
        7215, -- 2111.07793 Analysis of Data Augmentation Methods for Low-Resource Maltese ASR
        7238, -- 2111.09064 Guiding Generative Language Models for Data Augmentation in Few-Shot Text C
        7288, -- 2111.11828 Variance Reduction in Deep Learning: More Momentum is All You Need
        7343, -- 2111.15185 SamplingAug: On the Importance of Patch Sampling Augmentation for Single Im
        7411, -- 2112.02520 Neural Photometry-guided Visual Attribute Transfer
        7413, -- 2112.02721 NL-Augmenter: A Framework for Task-Sensitive Natural Language Augmentation
        7452, -- 2112.04764 3D-VField: Adversarial Augmentation of Point Clouds for Domain Generalizati
        7542, -- 2112.08844 Adapting Document-Grounded Dialog Systems to Spoken Conversations using Dat
        7561, -- 2112.09581 Watermarking Images in Self-Supervised Latent Spaces
        7569, -- 2112.10006 Zero-shot and Few-shot Learning with Knowledge Graphs: A Comprehensive Surv
        7589, -- 2112.11916 ALP: Data Augmentation using Lexicalized PCFGs for Few-Shot Text Classifica
        7669, -- 2201.03210 Model-Based Image Signal Processors via Learnable Dictionaries
        7809, -- 2201.12961 Plug-In Inversion: Model-Agnostic Inversion for Vision with Data Augmentati
        7926, -- 2202.05144 InPars: Data Augmentation for Information Retrieval using Large Language Mo
        7938, -- 2202.05690 HaT5: Hate Language Identification using Text-to-Text Transfer Transformer
        8056, -- 2202.12233 Automatic speaker verification spoofing and deepfake detection using wav2ve
        8072, -- 2202.13084 Visual Speech Recognition for Multiple Languages in the Wild
        8086, -- 2202.13588 Using Multi-scale SwinTransformer-HTC with Data augmentation in CoNIC Chall
        8107, -- 2203.00357 MERIt: Meta-Path Guided Contrastive Learning for Logical Reasoning
        8127, -- 2203.01441 3D Common Corruptions and Data Augmentation
        8164, -- 2203.03580 The Unsurprising Effectiveness of Pre-Trained Vision Models for Control
        8289, -- 2203.08445 Structurally Diverse Sampling for Sample-Efficient Training and Comprehensi
        8307, -- 2203.09116 MotionAug: Augmentation with Physical Correction for Human Motion Predictio
        8318, -- 2203.09391 When Chosen Wisely, More Data Is What You Need: A Universal Sample-Efficien
        8353, -- 2203.10761 Harnessing Hard Mixed Samples with Decoupled Regularizer
        8431, -- 2203.14145 Reverse Engineering of Imperceptible Adversarial Image Perturbations
        8533, -- 2204.00618 ASR data augmentation in low-resource settings using cross-lingual multi-sp
        8572, -- 2204.02285 SwapMix: Diagnosing and Regularizing the Over-Reliance on Visual Context in
        8596, -- 2204.02967 Enhanced Direct Speech-to-Speech Translation Using Self-supervised Pre-trai
        8607, -- 2204.03293 CoCoSoDa: Effective Contrastive Learning for Code Search
        8624, -- 2204.03776 TorMentor: Deterministic dynamic-path, data augmentations with fractals
        8628, -- 2204.03865 Frequency Selective Augmentation for Video Representation Learning
        8677, -- 2204.05488 Overlapping Word Removal is All You Need: Revisiting Data Imbalance in Hope
        8719, -- 2204.07118 DeiT III: Revenge of the ViT
        8747, -- 2204.07832 A Contrastive Cross-Channel Data Augmentation Framework for Aspect-based Se
        8749, -- 2204.07837 BLISS: Robust Sequence-to-Sequence Learning via Self-Supervised Input Repre
        8792, -- 2204.09598 Build a Robust QA System with Transformer-based Mixture of Experts
        8887, -- 2205.00029 Self-Aware Feedback-Based Self-Learning in Large-Scale Conversational AI
        8919, -- 2205.01580 Better plain ViT baselines for ImageNet-1k
        9011, -- 2205.06153 TreeMix: Compositional Constituency-based Data Augmentation for Natural Lan
        9054, -- 2205.09314 Target-Guided Dialogue Response Generation Using Commonsense and Data Augme
        9089, -- 2205.10450 Temporally Precise Action Spotting in Soccer Videos Using Dense Detection A
        9110, -- 2205.10803 GraphMAE: Self-Supervised Masked Graph Autoencoders
        9128, -- 2205.11413 QASem Parsing: Text-to-text Modeling of QA-based Semantics
        9248, -- 2205.14311 MolScribe: Robust Molecular Structure Recognition with Image-To-Graph Gener
        9265, -- 2205.14865 Prompt-aligned Gradient for Prompt Tuning
        9267, -- 2205.14879 Easter2.0: Improving convolutional models for handwritten text recognition
        9272, -- 2205.14986 GMML is All you Need
        9274, -- 2205.15060 Duplex Conversation: Towards Human-like Interaction in Spoken Dialogue Syst
        9284, -- 2205.15439 StyleTTS: A Style-Based Generative Model for Natural and Diverse Text-to-Sp
        9293, -- 2205.15677 Augmentation-Aware Self-Supervision for Data-Efficient GAN Training
        9312, -- 2206.00274 Point-Teaching: Weakly Semi-Supervised Object Detection with Point Annotati
        9347, -- 2206.01646 Integrating Prior Knowledge in Contrastive Learning with Kernel
        9391, -- 2206.03001 PP-OCRv3: More Attempts for the Improvement of Ultra Lightweight OCR System
        9625, -- 2206.13654 Wav2Vec-Aug: Improved self-supervised training with limited data
        9650, -- 2206.15369 No Reason for No Supervision: Improved Generalization in Supervised Models
        9729, -- 2207.04129 How many perturbations break this model? Evaluating robustness beyond adver
        9758, -- 2207.05223 Bootstrapping a User-Centered Task-Oriented Dialogue System
        9766, -- 2207.05506 Label-Efficient Self-Supervised Speaker Verification With Information Maxim
        9831, -- 2207.09150 On the Usability of Transformers-based models for a French Question-Answeri
        9840, -- 2207.09639 DC-BENCH: Dataset Condensation Benchmark
        9880, -- 2207.11363 Knowledge-Grounded Conversational Data Augmentation with Generative Convers
        9911, -- 2207.13085 Group DETR: Fast DETR Training with Group-Wise One-to-Many Assignment
        9930, -- 2207.14255 Efficient Training of Language Models to Fill in the Middle
        9958, -- 2208.01307 Multilingual Coreference Resolution in Multiparty Dialogue
        9960, -- 2208.01368 PyABSA: A Modularized Framework for Reproducible Aspect-based Sentiment Ana
        9971, -- 2208.02080 A Feature-space Multimodal Data Augmentation Technique for Text-video Retri
        9972, -- 2208.02169 SpanDrop: Simple and Effective Counterfactual Learning for Long Sequences
        9975, -- 2208.02724 Disentangled Representation Learning for RF Fingerprint Extraction under Un
        10029, -- 2208.05909 Domain-Specific Text Generation for Machine Translation
        10043, -- 2208.06956 ARIEL: Adversarial Graph Contrastive Learning
        10044, -- 2208.06957 Syntax-driven Data Augmentation for Named Entity Recognition
        10056, -- 2208.07407 SemAug: Semantically Meaningful Image Augmentations for Object Detection Th
        10073, -- 2208.08408 Summarizing Patients Problems from Hospital Progress Notes Using Pre-traine
        10114, -- 2208.10967 The Value of Out-of-Distribution Data
        10120, -- 2208.11210 Data augmentation on graphs for table type classification
        10179, -- 2208.14558 Augraphy: A Data Augmentation Library for Document Images
        10236, -- 2209.03561 Video Vision Transformers for Violence Detection
        10256, -- 2209.04951 Improving Keyphrase Extraction with Data Augmentation and Information Filte
        10350, -- 2209.09444 Vega-MT: The JD Explore Academy Translation System for WMT22
        10471, -- 2209.15031 Automatic Data Augmentation via Invariance-Constrained Learning
        10506, -- 2210.00320 MALM: Mixing Augmented Language Modeling for Zero-Shot Machine Translation
        10555, -- 2210.01891 Adaptively Weighted Data Augmentation Consistency Regularization for Robust
        10576, -- 2210.02410 The Vendi Score: A Diversity Evaluation Metric for Machine Learning
        10611, -- 2210.03180 A ResNet is All You Need? Modeling A Strong Baseline for Detecting Referabl
        10621, -- 2210.03403 TAN Without a Burn: Scaling Laws of DP-SGD
        10653, -- 2210.04185 Controllable Dialogue Simulation with In-Context Learning
        10831, -- 2210.08363 Data-Efficient Augmentation for Training Neural Networks
        10909, -- 2210.10678 Towards Realistic Low-resource Relation Extraction: A Benchmark with Empiri
        10935, -- 2210.11435 Learning and Retrieval from Prior Data for Skill-based Imitation Learning
        10944, -- 2210.11768 Augmentation with Projection: Towards an Effective and Efficient Data Augme
        10979, -- 2210.12540 EntityCS: Improving Zero-Shot Cross-lingual Transfer with Entity-Centric Co
        10991, -- 2210.12681 Rethinking Rotation in Self-Supervised Contrastive Learning: Adaptive Posit
        10998, -- 2210.12809 Data Augmentation for Automated Essay Scoring using Transformer Models
        11032, -- 2210.13512 Provably Learning Diverse Features in Multi-View Data with Midpoint Mixup
        11097, -- 2210.15418 FreeVC: Towards High-Quality Text-Free One-Shot Voice Conversion
        11174, -- 2211.00768 Why is Winoground Hard? Investigating Failures in Visuolinguistic Compositi
        11178, -- 2211.00923 SpeechBlender: Speech Augmentation Framework for Mispronunciation Data Gene
        11186, -- 2211.01246 data2vec-aqc: Search for the right Teaching Assistant in the Teacher-Studen
        11254, -- 2211.03946 Understanding the Role of Mixup in Knowledge Distillation: An Empirical Stu
        11305, -- 2211.06012 Masked Contrastive Representation Learning
        11337, -- 2211.07514 CST5: Data Augmentation for Code-Switched Semantic Parsing
        11381, -- 2211.08850 Consecutive Question Generation via Dynamic Multitask Learning
        11409, -- 2211.09703 EfficientTrain: Exploring Generalized Curriculum Learning for Training Visu
        11427, -- 2211.10147 FiE: Building a Global Probability Space by Leveraging Early Fusion in Enco
        11433, -- 2211.10330 GENIUS: Sketch-based Language Model Pre-training via Extreme and Selective
        11476, -- 2211.11262 Boosting Novel Category Discovery Over Domains with Soft Contrastive Learni
        11532, -- 2211.12491 ModelDiff: A Framework for Comparing Learning Algorithms
        11546, -- 2211.12737 RoentGen: Vision-Language Foundation Model for Chest X-ray Generation
        11560, -- 2211.12878 Mitigating Data Sparsity for Short Text Topic Modeling by Topic-Semantic Co
        11608, -- 2211.13916 Towards Good Practices for Missing Modality Robust Action Recognition
        11637, -- 2211.14646 Towards Improved Input Masking for Convolutional Neural Networks
        11766, -- 2212.00932 ObjectStitch: Generative Object Compositing
        11920, -- 2212.05749 On Pre-Training for Visuo-Motor Control: Revisiting a Learning-from-Scratch
        11980, -- 2212.07588 DeepJoin: Joinable Table Discovery with Pre-trained Language Models
        11998, -- 2212.08011 Multi-VALUE: A Framework for Cross-Dialectal English NLP
        12029, -- 2212.08649 Better May Not Be Fairer: A Study on Subgroup Discrepancy in Image Classifi
        12031, -- 2212.08663 Randomized Quantization: A Generic Augmentation for Data Agnostic Self-supe
        12038, -- 2212.08841 AugTriever: Unsupervised Dense Retrieval and Domain Adaptation by Scalable
        12043, -- 2212.08992 PoE: a Panel of Experts for Generalized Automatic Dialogue Assessment
        12084, -- 2212.09699 SegAugment: Maximizing the Utility of Speech Translation Data with Segmenta
        12145, -- 2212.10534 DISCO: Distilling Counterfactuals with Large Language Models
        12175, -- 2212.10806 MaskingDepth: Masked Consistency Regularization for Semi-supervised Monocul
        12284, -- 2301.00810 SIRL: Similarity-based Implicit Representation Learning
        12308, -- 2301.01928 Event Camera Data Pre-training
        12338, -- 2301.02819 ExcelFormer: A neural network surpassing GBDTs on tabular data
        12452, -- 2301.08243 Self-Supervised Learning from Images with a Joint-Embedding Predictive Arch
        12456, -- 2301.08556 NeRF in the Palm of Your Hand: Corrective Augmentation for Robotics via Nov
        12517, -- 2301.10527 Cross-lingual Argument Mining in the Medical Domain
        12673, -- 2301.13104 Equivariant Differentially Private Deep Learning: Why DP-SGD Needs Sparser
        12835, -- 2302.02092 Interpolation for Robust Learning: Data Augmentation on Wasserstein Geodesi
        12875, -- 2302.02774 The SSL Interplay: Augmentations, Inductive Bias, and Generalization
        12917, -- 2302.03499 Exploring Data Augmentation for Code Generation Tasks
        12975, -- 2302.04555 Data Augmentation for Robust Character Detection in Fantasy Novels
        13004, -- 2302.05096 Selective In-Context Data Augmentation for Intent Detection using Pointwise
        13038, -- 2302.05865 Flag Aggregator: Scalable Distributed Training under Failures and Augmented
        13109, -- 2302.07452 How to Train Your DRAGON: Diverse Augmentation Towards Generalizable Dense
        13126, -- 2302.07867 Learning Performance-Improving Code Edits
        13129, -- 2302.07944 Effective Data Augmentation With Diffusion Models
        13142, -- 2302.08191 LightGCL: Simple Yet Effective Graph Contrastive Learning for Recommendatio
        13145, -- 2302.08229 Improving Spoken Language Identification with Map-Mix
        13215, -- 2302.10258 Neural Algorithmic Reasoning with Causal Regularisation
        13268, -- 2302.11861 Out-of-Domain Robustness via Targeted Augmentations
        13273, -- 2302.12091 Random Teachers are Good Teachers
        13317, -- 2302.13007 AugGPT: Leveraging ChatGPT for Text Data Augmentation
        13392, -- 2302.14785 Joint Representations of Text and Knowledge Graphs for Retrieval and Evalua
        13420, -- 2303.00848 Understanding Diffusion Objectives as the ELBO with Simple Data Augmentatio
        13458, -- 2303.01580 Mixture of Soft Prompts for Controllable Data Generation
        13498, -- 2303.02577 Effectiveness of Data Augmentation for Parameter Efficient Tuning with Limi
        13560, -- 2303.04278 CUDA: Convolution-based Unlearnable Datasets
        13613, -- 2303.05367 Rethinking Range View Representation for LiDAR Segmentation
        13706, -- 2303.07123 Modality-Agnostic Debiasing for Single Domain Generalization
        13747, -- 2303.07864 DualMix: Unleashing the Potential of Data Augmentation for Online Class-Inc
        13769, -- 2303.08231 Rotation-Invariant Transformer for Point Cloud Matching
        13779, -- 2303.08433 The Benefits of Mixup for Feature Learning
        13803, -- 2303.08983 Reinforce Data, Multiply Impact: Improved Model Accuracy and Robustness wit
        13818, -- 2303.09219 MixCycle: Mixup Assisted Semi-Supervised 3D Single Object Tracking with Cyc
        13928, -- 2303.11305 SVDiff: Compact Parameter Space for Diffusion Fine-Tuning
        14178, -- 2303.15256 Active Self-Supervised Learning: A Few Low-Cost Relationships Are All You N
        14179, -- 2303.15265 Bilex Rx: Lexical Data Augmentation for Massively Multilingual Machine Tran
        14257, -- 2303.16621 AraSpot: Arabic Spoken Command Spotting
        14288, -- 2303.17152 Mixed Autoencoder for Self-supervised Visual Representation Learning
        14362, -- 2304.00176 Improving extreme weather events detection with light-weight neural network
        14369, -- 2304.00387 HaLP: Hallucinating Latent Positives for Skeleton-based Self-Supervised Lea
        14381, -- 2304.00719 Multi-Modal Representation Learning with Text-Driven Soft Masks
        14421, -- 2304.01464 Hierarchical Supervision and Shuffle Data Augmentation for 3D Semi-Supervis
        14449, -- 2304.01910 On the Variance of Neural Network Training with respect to Test Sets and Di
        14510, -- 2304.03294 What makes a good data augmentation for few-shot unsupervised image anomaly
        14523, -- 2304.03543 HyperTab: Hypernetwork Approach for Deep Learning on Small Tabular Datasets
        14532, -- 2304.03763 Clutter Detection and Removal in 3D Scenes with View-Consistent Inpainting
        14583, -- 2304.04703 Transfer Learning for Low-Resource Sentiment Analysis
        14618, -- 2304.05350 Astroformer: More Data Might not be all you need for Classification
        14676, -- 2304.06704 How Will It Drape Like? Capturing Fabric Mechanics from Depth Images
        14707, -- 2304.07101 Task-oriented Document-Grounded Dialog Systems by HLTPR@RWTH for DSTC9 and
        14725, -- 2304.07763 Meta-optimized Contrastive Learning for Sequential Recommendation
        14761, -- 2304.08821 TTIDA: Controllable Generative Data Augmentation via Text-to-Text and Text-
        14787, -- 2304.09402 MixPro: Simple yet Effective Data Augmentation for Prompt-based Learning
        14831, -- 2304.10253 Image retrieval outperforms diffusion models on data augmentation
        14866, -- 2304.11029 CLaMP: Contrastive Language-Music Pre-training for Cross-Modal Symbolic Mus
        14912, -- 2304.12043 MixPro: Data Augmentation with MaskMix and Progressive Attention Labeling f
        14933, -- 2304.12520 Hint-Aug: Drawing Hints from Foundation Vision Transformers Towards Boosted
        15053, -- 2304.14795 Semi-Supervised RF Fingerprinting with Consistency-Based Regularization
        15157, -- 2305.01711 Don't Stop Pretraining? Make Prompt-based Fine-tuning Powerful Learner
        15160, -- 2305.01918 Improving Contrastive Learning of Sentence Embeddings from AI Feedback
        15189, -- 2305.02317 Visual Chain of Thought: Bridging Logical Gaps with Multimodal Infillings
        15284, -- 2305.03935 Improved Techniques for Maximum Likelihood Estimation for Diffusion ODEs
        15370, -- 2305.05383 Code Execution with Pre-trained Language Models
        15473, -- 2305.07157 Exploring Zero and Few-shot Techniques for Intent Classification
        15511, -- 2305.07804 Improving Small Language Models on PubMedQA via Generative Data Augmentatio
        15547, -- 2305.08302 t-RAIN: Robust generalization under weather-aliasing label shift attacks
        15564, -- 2305.08636 AdamR at SemEval-2023 Task 10: Solving the Class Imbalance Problem in Sexis
        15566, -- 2305.08675 Improved baselines for vision-language pre-training
        15722, -- 2305.11080 Inspecting the Geographical Representativeness of Images from Text-to-Image
        15867, -- 2305.12599 Abstract Meaning Representation-Based Logic-Driven Data Augmentation for Lo
        15935, -- 2305.13284 Target-Aware Generative Augmentations for Single-Shot Adaptation
        15961, -- 2305.13547 Self-Evolution Learning for Mixup: Enhance Data Augmentation on Few-Shot Te
        15987, -- 2305.13725 Conversational Recommendation as Retrieval: A Simple, Strong Baseline
        16058, -- 2305.14288 LLM-powered Data Augmentation for Enhanced Cross-lingual Performance
        16082, -- 2305.14441 Exploring Contrast Consistency of Open-Domain Question Answering Systems on
        16162, -- 2305.14890 HARD: Hard Augmentations for Robust Distillation
        16289, -- 2305.15924 Sample and Predict Your Latent: Modality-free Sequential Disentanglement vi
        16339, -- 2305.16536 Which Features are Learnt by Contrastive Learning? On the Role of Simplicit
        16349, -- 2305.16651 TADA: Task-Agnostic Dialect Adapters for English
        16480, -- 2305.18169 LM-CPPF: Paraphrasing-Guided Data Augmentation for Contrastive Prompt-Based
        16482, -- 2305.18171 Improved Probabilistic Image-Text Representations
        16483, -- 2305.18183 On Counterfactual Data Augmentation Under Confounding
        16655, -- 2305.19759 Simple yet Effective Code-Switching Language Identification with Multitask
        16668, -- 2305.19915 Source Code Data Augmentation for Deep Learning: A Survey
        16675, -- 2305.19937 Breast Cancer Detection and Diagnosis: A comparative study of state-of-the-
        16694, -- 2305.20088 Improving CLIP Training with Language Rewrites
        16725, -- 2306.00267 Provable Benefit of Mixup for Finding Optimal Decision Boundaries
        16767, -- 2306.00739 SQL-PaLM: Improved Large Language Model Adaptation for Text-to-SQL (extende
        16768, -- 2306.00740 On the Limitations of Temperature Scaling for Distributions with Overlaps
        16773, -- 2306.00788 Understanding Augmentation-based Self-Supervised Representation Learning vi
        16847, -- 2306.01386 ChatGPT for Zero-shot Dialogue State Tracking: A Solution or an Opportunity
        16929, -- 2306.02330 Graph Transformer for Recommendation
        16955, -- 2306.02732 Conformal Prediction with Missing Values
        16965, -- 2306.02842 Improving Conversational Recommendation Systems via Counterfactual Data Sim
        17085, -- 2306.04186 Self-supervised Audio Teacher-Student Transformer for Both Clip-level and F
        17278, -- 2306.06788 Graph Mixup with Soft Alignments
        17309, -- 2306.07197 AROID: Improving Adversarial Robustness Through Online Instance-Wise Data A
        17351, -- 2306.07664 Rethink the Effectiveness of Text Data Augmentation: An Empirical Analysis
        17357, -- 2306.07758 Generated Graph Detection
        17420, -- 2306.08537 VIBR: Learning View-Invariant Value Functions for Robust Visual Control
        17631, -- 2306.11646 Recent Advances in Direct Speech-to-text Translation
        17734, -- 2306.13924 Structuring Representation Geometry with Rotationally Equivariant Contrasti
        17751, -- 2306.14169 A Web-based Mpox Skin Lesion Detection System Using State-of-the-art Deep L
        17762, -- 2306.14517 Cross-Lingual Cross-Age Group Adaptation for Low-Resource Elderly Speech Em
        17870, -- 2306.16770 DialoGPS: Dialogue Path Sampling in Continuous Semantic Space for Data Augm
        17898, -- 2306.17154 Generate Anything Anywhere in Any Scene
        17925, -- 2306.17848 Hardwiring ViT Patch Selectivity into CNNs using Patch Mixing
        17986, -- 2307.01426 DeepfakeBench: A Comprehensive Benchmark of Deepfake Detection
        18110, -- 2307.04096 Optimal Transport Posterior Alignment for Cross-lingual Semantic Parsing
        18233, -- 2307.07099 Controllable Data Augmentation for Few-Shot Text Mining with Chain-of-Thoug
        18308, -- 2307.08357 Self-supervised Monocular Depth Estimation: Let's Talk About The Weather
        18384, -- 2307.09520 Adversarial Bayesian Augmentation for Single-Source Domain Generalization
        18406, -- 2307.09829 What do neural networks learn in image classification? A frequency shortcut
        18510, -- 2307.11477 SA-BEV: Generating Semantic-Aware Bird's-Eye-View Feature for Multi-view 3D
        18527, -- 2307.11823 HybridAugment++: Unified Frequency Spectra Perturbations for Model Robustne
        18614, -- 2307.13424 Holistic Exploration on Universal Decompositional Semantic Parsing: Archite
        18644, -- 2307.13974 Tracking Anything in High Quality
        18688, -- 2307.14710 Pre-training Vision Transformers with Very Limited Synthesized Images
        18881, -- 2308.01526 Data Augmentation for Human Behavior Analysis in Multi-Person Conversations
        18884, -- 2308.01546 MusicLDM: Enhancing Novelty in Text-to-Music Generation Using Beat-Synchron
        19129, -- 2308.05697 SSLRec: A Self-Supervised Learning Framework for Recommendation
        19132, -- 2308.05732 PDE-Refiner: Achieving Accurate Long Rollouts with Neural PDE Solvers
        19150, -- 2308.06038 Diverse Data Augmentation with Diffusions for Effective Test-time Prompt Tu
        19349, -- 2308.08822 MixBag: Bag-Level Data Augmentation for Learning from Label Proportions
        19399, -- 2308.09368 A tailored Handwritten-Text-Recognition System for Medieval Latin
        19466, -- 2308.09965 Anomaly-Aware Semantic Segmentation via Style-Aligned OoD Augmentation
        19483, -- 2308.10103 ASPIRE: Language-Guided Data Augmentation for Improving Robustness Against
        19488, -- 2308.10133 TransFace: Calibrating Transformer Training for Face Recognition from a Dat
        19495, -- 2308.10155 Unilaterally Aggregated Contrastive Learning with Hierarchical Augmentation
        19689, -- 2308.12064 SILT: Shadow-aware Iterative Label Tuning for Learning to Detect Shadows fr
        19812, -- 2308.13769 Bengali Document Layout Analysis with Detectron2
        20032, -- 2309.00844 Domain Generalization via Balancing Training Difficulty and Model Capabilit
        20200, -- 2309.03893 DiffusionEngine: Diffusion Model is Scalable Data Engine for Object Detecti
        20241, -- 2309.04747 When to Learn What: Model-Adaptive Data Augmentation Curriculum
        20251, -- 2309.04862 Distributional Data Augmentation Methods for Low Resource Language
        20331, -- 2309.06358 Generative Data Augmentation using LLMs improves Distributional Robustness
        20466, -- 2309.08345 Data Distribution Bottlenecks in Grounding Language Models to Knowledge Bas
        20497, -- 2309.08644 Towards Robust and Smooth 3D Multi-Person Pose Estimation from Monocular Vi
        20516, -- 2309.08876 Decoder-only Architecture for Speech Recognition with CTC Prompts and Text
        20534, -- 2309.09276 MVP: Meta Visual Prompt Tuning for Few-Shot Remote Sensing Image Scene Clas
        20608, -- 2309.10431 Sample-adaptive Augmentation for Point Cloud Recognition Against Real-world
        20661, -- 2309.11104 AttentionMix: Data augmentation method that relies on BERT attention mechan
        20739, -- 2309.12288 The Reversal Curse: LLMs trained on "A is B" fail to learn "B is A"
        20805, -- 2309.13042 MosaicFusion: Diffusion Models as Data Augmenters for Large Vocabulary Inst
        20822, -- 2309.13258 Order-preserving Consistency Regularization for Domain Adaptation and Gener
        20823, -- 2309.13259 EMelodyGen: Emotion-Conditioned Melody Generation in ABC Notation with the
        20838, -- 2309.13504 Attention Is All You Need For Blind Room Volume Estimation
        20869, -- 2309.13942 Speed Co-Augmentation for Unsupervised Audio-Visual Pre-training
        20993, -- 2309.15938 Exploring Self-Supervised Contrastive Learning of Spatial Sound Event Repre
        20995, -- 2309.15991 Targeted Image Data Augmentation Increases Basic Skills Captioning Robustne
        21016, -- 2309.16275 UPB @ ACTI: Detecting Conspiracies using fine tuned Sentence Transformers
        21335, -- 2310.02219 What do we learn from a large-scale study of pre-trained visual representat
        21625, -- 2310.05506 MuggleMath: Assessing the Impact of Query and Response Augmentation on Math
        21626, -- 2310.05512 UAVs and Neural Networks for search and rescue missions
        21716, -- 2310.06504 Revisit Input Perturbation Problems for LLMs: A Unified Robustness Evaluati
        21717, -- 2310.06511 Self-Supervised Dataset Distillation for Transfer Learning
        21791, -- 2310.07418 Revisiting Plasticity in Visual Reinforcement Learning: Data, Modules and T
        21821, -- 2310.07756 Self-supervised Representation Learning From Random Data Projectors
        21996, -- 2310.09739 AugUndo: Scaling Up Augmentations for Monocular Depth Completion and Estima
        22189, -- 2310.12321 A Survey of GPT-3 Family Large Language Models Including ChatGPT and GPT-4
        22249, -- 2310.13023 GraphGPT: Graph Instruction Tuning for Large Language Models
        22336, -- 2310.14192 PromptMix: A Class Boundary Augmentation Method for Large Language Model Di
        22339, -- 2310.14318 Intent Contrastive Learning with Cross Subsequences for Sequential Recommen
        22359, -- 2310.14508 EXPLAIN, EDIT, GENERATE: Rationale-Sensitive Counterfactual Data Augmentati
        22407, -- 2310.15010 Statistical Depth for Ranking and Characterizing Transformer-Based Text Emb
        22478, -- 2310.15799 DALE: Generative Data Augmentation for Low-Resource Legal NLP
        22626, -- 2310.17653 Fantastic Gains and Where to Find Them: On the Existence and Prospect of Ge
        22639, -- 2310.17786 Understanding when Dynamics-Invariant Data Augmentations Benefit Model-Free
        22655, -- 2310.18021 FormalGeo: An Extensible Formalized Framework for Olympiad Geometric Proble
        22667, -- 2310.18247 Guided Data Augmentation for Offline Reinforcement Learning and Imitation L
        22723, -- 2310.19019 TeacherLM: Teaching to Fish Rather Than Giving the Fish, Language Modeling
        22746, -- 2310.19403 A Lightweight Method to Generate Unanswerable Questions in English
        22901, -- 2311.01270 People Make Better Edits: Measuring the Efficacy of LLM-Generated Counterfa
        22912, -- 2311.01441 Distilling Out-of-Distribution Robustness from Vision-Language Foundation M
        22932, -- 2311.01811 DiffDub: Person-generic Visual Dubbing Using Inpainting Renderer with Diffu
        22974, -- 2311.02849 Co-training and Co-distillation for Quality Improvement and Compression of
        23007, -- 2311.03510 Spoken Dialogue System for Medical Prescription Acquisition on Smartphone:
        23010, -- 2311.03629 Random Field Augmentations for Self-Supervised Representation Learning
        23166, -- 2311.06102 Making LLMs Worth Every Penny: Resource-Limited Text Classification in Bank
        23244, -- 2311.07475 Masked Face Dataset Generation and Masked Face Recognition
        23307, -- 2311.08355 Mustango: Toward Controllable Text-to-Music Generation
        23352, -- 2311.08851 Data Augmentations in Deep Weight Spaces
        23526, -- 2311.11331 Portuguese FAQ for Financial Services
        23553, -- 2311.11821 Cross-View Graph Consistency Learning for Invariant Graph Representations
        23592, -- 2311.12345 Stable Diffusion For Aerial Object Detection
        23657, -- 2311.13261 Immunohistochemistry guided segmentation of benign epithelial cells, in sit
        23685, -- 2311.13668 MAIRA-1: A specialised large multimodal model for radiology report generati
        23743, -- 2311.14836 Custom Data Augmentation for low resource ASR using Bark and Retrieval-Base
        23767, -- 2311.15260 NeuRAD: Neural Rendering for Autonomous Driving
        23793, -- 2311.15648 Reinforcement Learning from Diffusion Feedback: Q* for Image Search
        23973, -- 2311.17786 DSS: Synthesizing long Digital Ink using Data augmentation, Style encoding
        24027, -- 2311.18508 DifAugGAN: A Practical Diffusion-style Data Augmentation for GAN-based Sing
        24064, -- 2311.18838 Dataset Distillation via Curriculum Data Synthesis in Large Data Era
        24103, -- 2312.00358 Impact of Data Augmentation on QCNNs
        24299, -- 2312.02803 Leveraging Domain Adaptation and Data Augmentation to Improve Qur'anic IR i
        24518, -- 2312.05277 3D Copy-Paste: Physically Plausible Object Insertion for Monocular 3D Detec
        24637, -- 2312.06736 SqueezeSAM: User friendly mobile interactive segmentation
        24765, -- 2312.08846 TiMix: Text-aware Image Mixing for Effective Vision-Language Pre-training
        24843, -- 2312.09897 A Novel Dataset for Financial Education Text Simplification in Spanish
        24856, -- 2312.10105 SeiT++: Masked Token Modeling Improves Storage-efficient Training
        24870, -- 2312.10217 T-MAE: Temporal Masked Autoencoders for Point Cloud Representation Learning
        24911, -- 2312.10998 ID-Blau: Image Deblurring by Implicit Diffusion-based reBLurring AUgmentati
        24921, -- 2312.11276 Compositional Generalization for Multi-label Text Classification: A Data-Au
        24940, -- 2312.11503 Speech and Text-Based Emotion Recognizer
        25024, -- 2312.12716 BloomVQA: Assessing Hierarchical Multi-modal Comprehension
        25083, -- 2312.13834 Fairy: Fast Parallelized Instruction-Guided Video-to-Video Synthesis
        25262, -- 2312.16890 DiffKG: Knowledge Graph Diffusion Model for Recommendation
        25309, -- 2312.17473 FerKD: Surgical Label Adaptation for Efficient Distillation
        25312, -- 2312.17503 HiBid: A Cross-Channel Constrained Bidding System with Budget Allocation by
        25444, -- 2401.01830 Iterative Mask Filling: An Effective Text Augmentation Method Using Masked
        25445, -- 2401.01843 Investigating Semi-Supervised Learning Algorithms in Text Datasets
        25553, -- 2401.03473 ICMC-ASR: The ICASSP 2024 In-Car Multi-Channel Automatic Speech Recognition
        25603, -- 2401.04348 LAMPAT: Low-Rank Adaption for Multilingual Paraphrasing Using Adversarial T
        25617, -- 2401.04560 Phase-shifted remote photoplethysmography for estimating heart rate and blo
        25784, -- 2401.06853 Large Language Models Can Learn Temporal Reasoning
        25830, -- 2401.07867 Authorship Obfuscation in Multilingual Machine-Generated Text Detection
        25926, -- 2401.09109 Trapped in texture bias? A large scale comparison of deep instance segmenta
        26022, -- 2401.10407 Learning High-Quality and General-Purpose Phrase Representations
        26060, -- 2401.10891 Depth Anything: Unleashing the Power of Large-Scale Unlabeled Data
        26080, -- 2401.11237 Closing the Gap between TD Learning and Supervised Learning - A Generalisa
        26327, -- 2401.14559 Language Modelling Approaches to Adaptive Machine Translation
        26429, -- 2401.16349 ConFit: Improving Resume-Job Matching using Data Augmentation and Contrasti
        26509, -- 2401.17509 Anything in Any Scene: Photorealistic Video Object Insertion
        26670, -- 2402.01542 Learning Collective Variables with Synthetic Data Augmentation through Phys
        26720, -- 2402.01939 A Morphologically-Aware Dictionary-based Data Augmentation Technique for Ma
        26951, -- 2402.04408 Detection Transformer for Teeth Detection, Segmentation, and Numbering in O
        26967, -- 2402.04588 UltraLink: An Open-Source Knowledge-Enhanced Multilingual Supervised Fine-t
        26993, -- 2402.04858 CodeIt: Self-Improving Language Models with Prioritized Hindsight Replay
        27045, -- 2402.05584 AutoAugment Is What You Need: Enhancing Rule-based Augmentation Methods in
        27046, -- 2402.05591 SoftEDA: Rethinking Rule-Based Data Augmentation with Soft Labels
        27106, -- 2402.06171 Pushing Boundaries: Mixup's Influence on Neural Collapse
        27118, -- 2402.06332 InternLM-Math: Open Math Large Language Models Toward Verifiable Reasoning
        27139, -- 2402.06766 Evaluation Metrics for Text Data Augmentation in NLP
        27270, -- 2402.08666 Improving Generalization in Semantic Parsing by Increasing Natural Language
        27276, -- 2402.08692 Inference Stage Denoising for Undersampled MRI Reconstruction
        27372, -- 2402.10110 Selective Reflection-Tuning: Student-Selected Data Recycling for LLM Instru
        27401, -- 2402.10434 Parametric Augmentation for Time Series Contrastive Learning
        27493, -- 2402.11355 A Practical Method for Generating String Counterfactuals
        27507, -- 2402.11485 LEIA: Facilitating Cross-lingual Knowledge Transfer in Language Models with
        27519, -- 2402.11566 Boosting Semi-Supervised 2D Human Pose Estimation by Revisiting Data Augmen
        27541, -- 2402.11764 ChatGPT Based Data Augmentation for Improved Parameter-Efficient Debiasing
        27546, -- 2402.11815 HU at SemEval-2024 Task 8A: Can Contrastive Learning Learn Embeddings to De
        27583, -- 2402.12181 Revisiting Data Augmentation in Deep Reinforcement Learning
        27667, -- 2402.13013 Code Needs Comments: Enhancing Code LLMs with Comment Augmentation
        27673, -- 2402.13116 A Survey on Knowledge Distillation of Large Language Models
        27697, -- 2402.13254 CounterCurate: Enhancing Physical and Semantic Visio-Linguistic Composition
        27710, -- 2402.13482 Retrieval-Augmented Data Augmentation for Low-Resource Domain Tasks
        27813, -- 2402.14568 LLM-DA: Data Augmentation via Large Language Models for Few-Shot Named Enti
        27814, -- 2402.14579 Text Role Classification in Scientific Charts Using Multimodal Transformers
        27835, -- 2402.14795 CyberDemo: Augmenting Simulated Human Demonstration for Real-World Dexterou
        27852, -- 2402.14865 Dynamic Evaluation of Large Language Models by Meta Probing Agents
        27965, -- 2402.16347 CodeS: Towards Building Open-source Language Models for Text-to-SQL
        28012, -- 2402.16910 NeSy is alive and well: A LLM-driven symbolic approach for better code comm
        28184, -- 2402.19059 WHU-Synthetic: A Synthetic Perception Dataset for 3-D Multitask Model Resea
        28293, -- 2403.01121 OpenGraph: Towards Open Graph Foundation Models
        28320, -- 2403.01432 Fine Tuning vs. Retrieval Augmented Generation for Less Popular Knowledge
        28368, -- 2403.02178 Masked Thought: Simply Masking Partial Reasoning Steps Can Improve Mathemat
        28412, -- 2403.02738 Causal Prompting: Debiasing Large Language Model Prompting based on Front-D
        28424, -- 2403.02990 Data Augmentation using Large Language Models: Data Perspectives, Learning
        28484, -- 2403.03894 IRCoder: Intermediate Representations Make Language Models Robust Multiling
        28510, -- 2403.04454 Low-Resource Court Judgment Summarization for Common Law Systems
        28554, -- 2403.04993 PromptIQA: Boosting the Performance and Generalization for No-Reference Ima
        28604, -- 2403.05726 Augmentations vs Algorithms: What Works in Self-Supervised Learning
        28641, -- 2403.06354 Amharic LLaMA and LLaVA: Multimodal LLMs for Low Resource Languages
        28758, -- 2403.07955 Towards Faithful Explanations: Boosting Rationalization with Shortcuts Disc
        28834, -- 2403.09159 Basque and Spanish Counter Narrative Generation: Data Creation and Evaluati
        28844, -- 2403.09274 EventRPG: Event Data Augmentation with Relevance Propagation Guidance
        28956, -- 2403.10834 SF(DA)$^2$: Source-free Domain Adaptation Through the Lens of Data Augmenta
        28961, -- 2403.10911 Efficient Diffusion-Driven Corruption Editor for Test-Time Adaptation
        28982, -- 2403.11124 Scaling Data Diversity for Fine-Tuning Language Models in Human Alignment
        29000, -- 2403.11391 Investigating the Benefits of Projection Head for Representation Learning
        29055, -- 2403.12003 GenView: Enhancing View Quality with Pretrained Generative Model for Self-S
        29094, -- 2403.12448 Do Generated Data Always Help Contrastive Learning?
        29116, -- 2403.12729 Posterior Uncertainty Quantification in Neural Networks using Data Augmenta
        29140, -- 2403.12961 TexTile: A Differentiable Metric for Texture Tileability
        29148, -- 2403.13031 RigorLLM: Resilient Guardrails for Large Language Models against Undesired
        29312, -- 2403.15042 LLM2LLM: Boosting LLMs with Novel Iterative Data Enhancement
        29357, -- 2403.15512 Enhancing Effectiveness and Robustness in a Low-Resource Regime via Decisio
        29389, -- 2403.16092 Are NeRFs ready for autonomous driving? Towards closing the real-to-simulat
        29579, -- 2403.19031 Evaluating Large Language Models for Health-Related Text Classification Tas
        29655, -- 2403.20012 Colorful Cutout: Enhancing Image Data Augmentation with Curriculum Learning
        29657, -- 2403.20015 Adverb Is the Key: Simple Text Data Augmentation with Adverb Deletion
        29698, -- 2404.00415 CoDa: Constrained Generation based Data Augmentation for Low-Resource NLP
        29760, -- 2404.01019 Source-Aware Training Enables Knowledge Attribution in Language Models
        29806, -- 2404.01430 Position-Aware Parameter Efficient Fine-Tuning Approach for Reducing Positi
        30000, -- 2404.04243 Identity Decoupling for Multi-Subject Personalization of Text-to-Image Mode
        30179, -- 2404.07031 ORacle: Large Vision-Language Models for Knowledge-Guided Holistic OR Domai
        30188, -- 2404.07153 Lost in Translation: Modern Neural Networks Still Struggle With Small Reali
        30228, -- 2404.07765 AnnoCTR: A Dataset for Detecting and Linking Entities, Tactics, and Techniq
        30236, -- 2404.07850 MindBridge: A Cross-Subject Brain Decoding Framework
        30267, -- 2404.08197 Scaling (Down) CLIP: A Comprehensive Analysis of Data, Architecture, and Tr
        30279, -- 2404.08368 Automatic Speech Recognition Advancements for Indigenous Languages of the A
        30291, -- 2404.08582 FashionFail: Addressing Failure Cases in Fashion Object Detection and Segme
        30338, -- 2404.09290 RoofDiffusion: Constructing Roofs from Severely Corrupted Point Data via Di
        30375, -- 2404.09736 FSRT: Facial Scene Representation Transformer for Face Reenactment from Fac
        30394, -- 2404.10096 Vision Augmentation Prediction Autoencoder with Attention Design (VAPAAD)
        30459, -- 2404.11202 GhostNetV3: Exploring the Training Strategies for Compact Models
        30803, -- 2404.16944 Constellation Dataset: Benchmarking High-Altitude Object Detection for an U
        30804, -- 2404.16972 CriSp: Leveraging Tread Depth Maps for Enhanced Crime-Scene Shoeprint Match
        30838, -- 2404.17642 Empowering Large Language Models for Textual Data Augmentation
        30845, -- 2404.17768 Changing the Training Data Distribution to Reduce Simplicity Bias Improves
        30949, -- 2405.00134 Transforming Dutch: Debiasing Dutch Coreference Resolution Systems for Non-
        31024, -- 2405.01567 CodeFort: Robust Training for Code Generation Models
        31160, -- 2405.05524 Universal Adversarial Perturbations for Vision-Language Pre-trained Models
        31236, -- 2405.07551 MuMath-Code: Combining Tool-Use Large Language Models with Multi-perspectiv
        31267, -- 2405.08029 PHUDGE: Phi-3 as Scalable Judge
        31308, -- 2405.09153 Adapting Abstract Meaning Representation Parsing to the Clinical Narrative
        31324, -- 2405.09507 QueryNER: Segmentation of E-commerce Queries
        31326, -- 2405.09559 KID-PPG: Knowledge Informed Deep Learning for Extracting Heart Rate from a
        31354, -- 2405.10185 DiverGen: Improving Instance Segmentation by Learning Wider Data Distributi
        31506, -- 2405.13326 Mosaic-IT: Free Compositional Data Augmentation Improves Instruction Tuning
        31585, -- 2405.14458 YOLOv10: Real-Time End-to-End Object Detection
        31621, -- 2405.14800 Membership Inference on Text-to-Image Diffusion Models via Conditional Like
        31889, -- 2405.17893 Arithmetic Reasoning with LLM: Prolog Generation & Permutation
        31965, -- 2405.18654 Data-augmented phrase-level alignment for mitigating object hallucination
        32204, -- 2406.00907 DDA: Dimensionality Driven Augmentation Search for Contrastive Learning in
        32239, -- 2406.01441 LexMatcher: Dictionary-centric Data Collection for LLM-based Machine Transl
        32308, -- 2406.02517 Deterministic Reversible Data Augmentation for Neural Machine Translation
        32791, -- 2406.08249 Dataset Enhancement with Instance-Level Augmentations
        32842, -- 2406.08860 Plan, Generate and Complicate: Improving Low-resource Dialogue State Tracki
        32877, -- 2406.09294 You Don't Need Domain-Specific Data Augmentations When Scaling Self-Supervi
        32939, -- 2406.09881 A Unified Data Augmentation Framework for Low-Resource Multi-Domain Dialogu
        32957, -- 2406.10126 Training-free Camera Control for Video Generation
        33002, -- 2406.10593 QDA-SQL: Questions Enhanced Dialogue Augmentation for Multi-Turn Text-to-SQ
        33200, -- 2406.12050 Learn Beyond The Answer: Training Language Models with Reflection for Mathe
        33248, -- 2406.12452 Insect Identification in the Wild: The AMI Dataset
        33290, -- 2406.12849 Depth Anywhere: Enhancing 360 Monocular Depth Estimation via Perspective Di
        33433, -- 2406.14693 Voice Disorder Analysis: a Transformer-based Approach
        33435, -- 2406.14709 Factual Dialogue Summarization via Learning from Large Language Models
        33591, -- 2406.16714 AutoDetect: Towards a Unified Framework for Automated Weakness Detection in
        33625, -- 2406.17148 MixTex: Unambiguous Recognition Should Not Rely Solely on Real Data
        33646, -- 2406.17363 Leveraging Synthetic Audio Data for End-to-End Low-Resource Speech Translat
        33660, -- 2406.17536 MedMNIST-C: Comprehensive benchmark and improved classifier robustness by s
        33760, -- 2406.18665 RouteLLM: Learning to Route LLMs with Preference Data
        33780, -- 2406.18966 UniGen: A Unified Framework for Textual Dataset Generation Using Large Lang
        34068, -- 2407.02685 Open Panoramic Segmentation
        34110, -- 2407.03251 ACTRESS: Active Retraining for Semi-supervised Visual Grounding
        34162, -- 2407.04020 LLMAEL: Large Language Models are Good Context Augmenters for Entity Linkin
        34243, -- 2407.05175 TopoLedgerBERT: Topological Learning of Ledger Description Embeddings using
        34263, -- 2407.05449 SmurfCat at PAN 2024 TextDetox: Alignment of Multilingual Transformers for
        34288, -- 2407.05700 InverseCoder: Self-improving Instruction-Tuned Code LLMs with Inverse-Instr
        34303, -- 2407.05975 LLaMAX: Scaling Linguistic Horizons of LLM by Enhancing Translation Capabil
        34406, -- 2407.07295 Deformation-Recovery Diffusion Model (DRDM): Instance Deformation for Image
        34410, -- 2407.07341 A Guide To Effectively Leveraging LLMs for Low-Resource Text Summarization:
        34416, -- 2407.07464 Video-to-Audio Generation with Hidden Alignment
        34428, -- 2407.07667 VEnhancer: Generative Space-Time Enhancement for Video Generation
        34437, -- 2407.07805 SUMix: Mixup with Semantic and Uncertain Information
        34530, -- 2407.08944 Bora: Biomedical Generalist Video Generation Model
        34954, -- 2407.14126 Mono-ViFI: A Unified Learning Framework for Self-supervised Single- and Mul
        34987, -- 2407.14726 MetaAug: Meta-Data Augmentation for Post-Training Quantization
        35005, -- 2407.14972 ARoFace: Alignment Robustness to Improve Low-Quality Face Recognition
        35039, -- 2407.15415 LLaST: Improved End-to-end Speech Translation System Leveraged by Large Lan
        35046, -- 2407.15498 Refining Corpora from a Model Calibration Perspective for Chinese Spelling
        35148, -- 2407.17140 RT-DETRv2: Improved Baseline with Bag-of-Freebies for Real-Time Detection T
        35422, -- 2408.00350 A Simple Background Augmentation Method for Object Detection with Diffusion
        35654, -- 2408.04224 Cross-View Meets Diffusion: Aerial Image Synthesis with Geometry and Text G
        35789, -- 2408.06741 Improving Synthetic Image Detection Towards Generalization: An Image Transf
        35828, -- 2408.07414 WavLM model ensemble for audio deepfake detection
        35945, -- 2408.09490 Leveraging Invariant Principle for Heterophilic Graph Structure Distributio
        36018, -- 2408.10775 Generative AI in Industrial Machine Vision - A Review
        36030, -- 2408.10940 A Closer Look at Data Augmentation Strategies for Finetuning-Based Low/Few-
        36250, -- 2408.14584 DIAGen: Diverse Image Augmentation with Generative Models
        36360, -- 2408.16266 Inversion Circle Interpolation: Diffusion-based Image Augmentation for Data
        36482, -- 2409.00951 Semantically Controllable Augmentations for Generalizable Robot Learning
        36623, -- 2409.03685 View-Invariant Policy Learning via Zero-Shot Novel View Synthesis
        36666, -- 2409.04774 Untie the Knots: An Efficient Data Augmentation Strategy for Long-Context P
        36676, -- 2409.05032 Exploring WavLM Back-ends for Speech Spoofing and Deepfake Detection
        36684, -- 2409.05202 A Survey on Mixup Augmentations and Beyond
        36719, -- 2409.06183 EDADepth: Enhanced Data Augmentation for Monocular Depth Estimation
        36778, -- 2409.07431 Synthetic continued pretraining
        36800, -- 2409.07940 Control+Shift: Generating Controllable Distribution Shifts
        36898, -- 2409.09546 Effective Pre-Training of Audio Transformers for Sound Event Detection
        36925, -- 2409.10103 Self-Supervised Syllable Discovery Based on Speaker-Disentangled HuBERT
        37086, -- 2409.12887 Enhancing Unsupervised Sentence Embeddings via Knowledge-Driven Data Augmen
        37105, -- 2409.13156 RRM: Robust Reward Model Training Mitigates Reward Hacking
        37112, -- 2409.13213 MalMixer: Few-Shot Malware Classification with Retrieval-Augmented Semi-Sup
        37155, -- 2409.13884 A Multi-LLM Debiasing Framework
        37183, -- 2409.14495 Thought-Path Contrastive Learning via Premise-Oriented Data Augmentation fo
        37260, -- 2409.15803 3D-JEPA: A Joint Embedding Predictive Architecture for 3D Self-Supervised R
        37288, -- 2409.16288 Self-Supervised Any-Point Tracking by Contrastive Random Walks
        37312, -- 2409.16730 Non-stationary BERT: Exploring Augmented IMU Data For Robust Human Activity
        37321, -- 2409.16949 DALDA: Data Augmentation Leveraging Diffusion Model and LLM with Adaptive G
        37342, -- 2409.17363 Improving satellite imagery segmentation using multiple Sentinel-2 revisits
        37580, -- 2410.00337 SyntheOcc: Synthesize Geometric-Controlled Street View Images through 3D Se
        37592, -- 2410.00513 Cross-lingual Back-Parsing: Utterance Synthesis from Meaning Representation
        37657, -- 2410.01504 PersonaMath: Enhancing Math Reasoning through Persona-Driven Data Augmentat
        37660, -- 2410.01524 HarmAug: Effective Data Augmentation for Knowledge Distillation of Safety G
        37714, -- 2410.02056 Synthio: Augmenting Small-Scale Audio Classification Datasets with Syntheti
        37747, -- 2410.02319 QDGset: A Large Scale Grasping Dataset Generated with Quality-Diversity
        37852, -- 2410.03176 Investigating and Mitigating Object Hallucinations in Pretrained Vision-Lan
        37988, -- 2410.05016 T-JEPA: Augmentation-Free Self-Supervised Learning for Tabular Data
        38198, -- 2410.07230 RFBoost: Understanding and Boosting Deep WiFi Sensing via Physical Data Aug
        38235, -- 2410.07838 Minority-Focused Text-to-Image Generation via Prompt Optimization
        38531, -- 2410.11446 AIC CTU system at AVeriTeC: Re-framing automated fact-checking as a simple
        38567, -- 2410.11871 TinyClick: Single-Turn Agent for Empowering GUI Automation
        38626, -- 2410.12750 Comparative Analysis of Extrinsic Factors for NER in French
        38651, -- 2410.12896 A Survey on Data Synthesis and Augmentation for Large Language Models
        38725, -- 2410.13674 Diffusion Curriculum: Synthetic-to-Real Generative Curriculum Learning via
        38899, -- 2410.15804 Deep Learning and Data Augmentation for Detecting Self-Admitted Technical D
        38936, -- 2410.16235 ToW: Thoughts of Words Improve Reasoning in Large Language Models
        38968, -- 2410.16523 Efficient Neural Network Training via Subset Pretraining
        39003, -- 2410.17161 Interchangeable Token Embeddings for Extendable Vocabulary and Alpha-Equiva
        39098, -- 2410.18444 Evaluating and Improving Automatic Speech Recognition Systems for Korean Me
        39164, -- 2410.19151 CapsuleNet: A Deep Learning Model To Classify GI Diseases Using EfficientNe
        39168, -- 2410.19193 Enriching GNNs with Text Contextual Representations for Detecting Disinform
        39186, -- 2410.19553 On Occlusions in Video Action Detection: Benchmark Datasets And Training Re
        39218, -- 2410.20158 Your Image is Secretly the Last Frame of a Pseudo Video
        39243, -- 2410.20533 Guiding Through Complexity: What Makes Good Supervision for Hard Reasoning
        39279, -- 2410.21200 BongLLaMA: LLaMA for Bangla Language
        39375, -- 2410.22857 DAVINCI: A Single-Stage Architecture for Constrained CAD Sketch Inference
        39442, -- 2410.23893 DiffBatt: A Diffusion Model for Battery Degradation Prediction and Synthesi
        39727, -- 2411.04588 Tibyan Corpus: Balanced and Comprehensive Error Coverage Corpus Using ChatG
        39763, -- 2411.05005 Diff-2-in-1: Bridging Generation and Dense Perception with Diffusion Models
        39822, -- 2411.05928 Reducing Distraction in Long-Context Language Models by Focused Learning
        40137, -- 2411.11927 FLAME: Frozen Large Language Models Enable Data-Efficient Language-Image Pr
        40143, -- 2411.12044 ITACLIP: Boosting Training-Free Semantic Segmentation with Image, Text, and
        40200, -- 2411.13159 Hard-Synth: Synthesizing Diverse Hard Samples for ASR using Zero-Shot TTS a
        40209, -- 2411.13405 On the Way to LLM Personalization: Learning to Remember User Conversations
        40363, -- 2411.15497 AeroGen: Enhancing Remote Sensing Object Detection with Diffusion-Driven Da
        40439, -- 2411.16567 Enhancing Few-Shot Learning with Integrated Data and GAN Model Approaches
        40561, -- 2411.17870 Breast Tumor Classification Using EfficientNet Deep Learning Model
        40573, -- 2411.18104 Training and Evaluating Language Models with Template-based Data Generation
        40649, -- 2411.19067 MaskRIS: Semantic Distortion-aware Data Augmentation for Referring Image Se
        40666, -- 2411.19292 UrbanCAD: Towards Highly Controllable and Photorealistic 3D Vehicles for Ur
        40718, -- 2411.19865 Reverse Thinking Makes LLMs Stronger Reasoners
        40727, -- 2411.19951 T2Vid: Translating Long Text into Multi-Image is the Catalyst for Video-LLM
        40751, -- 2412.00319 Improving speaker verification robustness with synthetic emotional utteranc
        40752, -- 2412.00324 Table Integration in Data Lakes Unleashed: Pairwise Integrability Judgment,
        40895, -- 2412.02254 ProbPose: A Probabilistic Approach to 2D Human Pose Estimation
        40902, -- 2412.02366 GenMix: Effective Data Augmentation with Generative Diffusion Model Image E
        40917, -- 2412.02676 Planning-Guided Diffusion Policy Learning for Generalizable Contact-Rich Bi
        40984, -- 2412.03512 Distillation of Diffusion Features for Semantic Correspondence
        41036, -- 2412.04110 Enhancing Mathematical Reasoning in LLMs with Background Operators
        41044, -- 2412.04234 DEIM: DETR with Improved Matching for Fast Convergence
        41058, -- 2412.04351 BhashaVerse : Translation Ecosystem for Indian Subcontinent Languages
        41125, -- 2412.04871 Building a Family of Data Augmentation Models for Low-cost LLM Fine-tuning
        41289, -- 2412.07199 A Parametric Approach to Adversarial Augmentation for Cross-Domain Iris Pre
        41446, -- 2412.09263 First Train to Generate, then Generate to Train: UnitedSynT5 for Few-Shot N
        41660, -- 2412.11812 CLDA-YOLO: Visual Contrastive Learning Based Domain Adaptive YOLO Detector
        41733, -- 2412.12609 MultiLingPoT: Enhancing Mathematical Reasoning with Multilingual Program Fi
        41767, -- 2412.13059 3D MedDiffusion: A 3D Medical Diffusion Model for Controllable and High-qua
        41802, -- 2412.13464 GenX: Mastering Code and Test Generation with Execution Feedback
        41840, -- 2412.14054 Digestion Algorithm in Hierarchical Symbolic Forests: A Fast Text Normaliza
        41871, -- 2412.14422 Enhancing Diffusion Models for High-Quality Image Generation
        42046, -- 2412.16926 Revisiting In-Context Learning with Long Context Language Models
        42080, -- 2412.17395 WarriorCoder: Learning from Expert Battles to Augment Code Large Language M
        42177, -- 2412.18565 3DEnhancer: Consistent Multi-View Diffusion for 3D Enhancement
        42353, -- 2501.00425 Whisper Turns Stronger: Augmenting Wav2Vec 2.0 for Superior ASR in Low-Reso
        42373, -- 2501.00691 Labels Generated by Large Language Model Helps Measuring People's Empathy i
        42428, -- 2501.01421 R-SCoRe: Revisiting Scene Coordinate Regression for Robust Large-Scale Visu
        42486, -- 2501.02464 Depth Any Camera: Zero-Shot Metric Depth Estimation from Any Camera
        42705, -- 2501.05932 DiffuSETS: 12-lead ECG Generation Conditioned on Clinical Text Reports and
        42759, -- 2501.06746 Diversified Augmentation with Domain Adaptation for Debiased Video Temporal
        42916, -- 2501.09565 A New Teacher-Reviewer-Student Framework for Semi-supervised 2D Human Pose
        43411, -- 2501.18369 A Cartesian Encoding Graph Neural Network for Crystal Structures Property P
        43431, -- 2501.18648 Image, Text, and Speech Data Augmentation using Multimodal LLMs for Deep Le
        43443, -- 2501.18845 Text Data Augmentation for Large Language Models: A Comprehensive Survey of
        43642, -- 2502.02249 Conversation AI Dialog for Medicare powered by Finetuning and Retrieval Aug
        43755, -- 2502.04235 Reformulation for Pretraining Data Augmentation
        43778, -- 2502.04378 DILLEMA: Diffusion and Large Language Models for Multi-Modal Augmentation
        43794, -- 2502.04475 Augmented Conditioning Is Enough For Effective Training Image Generation
        43933, -- 2502.06516 Boost-and-Skip: A Simple Guidance-Free Diffusion for Minority Generation
        44058, -- 2502.07837 RoboBERT: An End-to-end Multimodal Robotic Manipulation Model
        44195, -- 2502.10097 Causal Information Prioritization for Efficient Reinforcement Learning
        44299, -- 2502.11190 ReLearn: Unlearning via Learning for Large Language Models
        44307, -- 2502.11262 Generating Skyline Datasets for Data Science Models
        44378, -- 2502.11862 Understanding In-Context Machine Translation for Low-Resource Languages: A
        44386, -- 2502.11901 Building A Proof-Oriented Programmer That Is 64% Better Than GPT-4o Under D
        44401, -- 2502.12050 SpeechT: Findings of the First Mentorship in Speech Translation
        44745, -- 2502.15251 SiMHand: Mining Similar Hands for Large-Scale 3D Hand Pose Pre-training
        44947, -- 2502.17435 GCC: Generative Color Constancy via Diffusing a Color Checker
        44962, -- 2502.17709 Contrastive Visual Data Augmentation
        44968, -- 2502.17800 Your Language Model May Think Too Rigidly: Achieving Reasoning Consistency
        45115, -- 2502.19712 Teaching Dense Retrieval Models to Specialize with Listwise Distillation an
        45319, -- 2503.01334 Composed Multi-modal Retrieval: A Survey of Approaches and Applications
        45479, -- 2503.03365 TopoMortar: A dataset to evaluate image segmentation methods focused on top
        45581, -- 2503.04930 HILGEN: Hierarchically-Informed Data Generation for Biomedical NER Using Kn
        45958, -- 2503.09399 ForAug: Recombining Foregrounds and Backgrounds to Improve Vision Transform
        46267, -- 2503.13434 BlobCtrl: A Unified and Flexible Framework for Element-level Image Generati
        46275, -- 2503.13551 Towards Hierarchical Multi-Step Reward Models for Enhanced Reasoning in Lar
        46403, -- 2503.15485 TULIP: Towards Unified Language-Image Pretraining
        46465, -- 2503.16212 MathFusion: Enhancing Mathematic Problem-solving of LLM through Instruction
        46566, -- 2503.17538 A Statistical Theory of Contrastive Learning via Approximate Sufficient Sta
        46569, -- 2503.17577 Measuring the Robustness of Audio Deepfake Detectors
        47181, -- 2504.01928 Is the Reversal Curse a Binding Problem? Uncovering Limitations of Transfor
        47237, -- 2504.02604 LinTO Audio and Textual Datasets to Train and Evaluate Automatic Speech Rec
        47340, -- 2504.04517 Enhance Then Search: An Augmentation-Search Strategy with Foundation Models
        47383, -- 2504.05301 S^4M: Boosting Semi-Supervised Instance Segmentation with SAM
        47444, -- 2504.06801 MonoPlace3D: Learning 3D-Aware Object Placement for 3D Monocular Detection
        47522, -- 2504.07959 CCMNet: Leveraging Calibrated Color Correction Matrices for Cross-Camera Co
        47590, -- 2504.09182 seg2med: a bridge from artificial anatomy to multimodal medical images
        47611, -- 2504.09555 Mitigating Long-tail Distribution in Oracle Bone Inscriptions: Dataset, Mod
        47696, -- 2504.10647 Improving In-Context Learning with Reasoning Distillation
        47750, -- 2504.11457 Aligning Generative Denoising with Discriminative Objectives Unleashes Diff
        47826, -- 2504.12609 Crossing the Human-Robot Embodiment Gap with Sim-to-Real RL using One Human
        47850, -- 2504.13055 NoisyRollout: Reinforcing Visual Reasoning with Data Augmentation
        48164, -- 2504.18983 MediAug: Exploring Visual Augmentation in Medical Imaging
        48209, -- 2504.20117 ResearchCodeAgent: An LLM Multi-Agent System for Automated Codification of
        48218, -- 2504.20484 Enhancing LLM Language Adaption through Cross-lingual In-Context Pre-traini
        48227, -- 2504.20703 BrightCookies at SemEval-2025 Task 9: Exploring Data Augmentation for Food
        48230, -- 2504.20752 Grokking in the Wild: Data Augmentation for Real-World Multi-Hop Reasoning
        48370, -- 2505.02094 SkillMimic-V2: Learning Robust and Generalizable Interaction Skills from Sp
        48401, -- 2505.02518 Bemba Speech Translation: Exploring a Low-Resource African Language
        48436, -- 2505.03176 seq-JEPA: Autoregressive Predictive Learning of Invariant-Equivariant World
        48663, -- 2505.07859 Boosting Performance on ARC is a Matter of Perspective
        48828, -- 2505.11049 GuardReasoner-VL: Safeguarding VLMs via Reinforced Reasoning
        48948, -- 2505.12335 Is Artificial Intelligence Generated Image Detection a Solved Problem?
        49115, -- 2505.13972 Truth or Twist? Optimal Model Selection for Reliable Label Flipping Evaluat
        49649, -- 2505.18759 The Quest for Efficient Reasoning: A Data-Centric Benchmark to CoT Distilla
        49664, -- 2505.18917 Behavior Injection: Preparing Language Models for Reinforcement Learning
        49802, -- 2505.20046 REARANK: Reasoning Re-ranking Agent via Reinforcement Learning
        50208, -- 2505.24200 Improving Multilingual Speech Models on ML-SUPERB 2.0: Fine-tuning with Dat
        50257, -- 2505.24718 Reinforcing Video Reasoning with Focused Thinking
        50403, -- 2506.01801 OmniV2V: Versatile Video Generation and Editing via Dynamic Content Manipul
        50440, -- 2506.02294 Improving Knowledge Distillation Under Unknown Covariate Shift Through Conf
        50625, -- 2506.05127 PixCell: A generative foundation model for digital histopathology images
        50764, -- 2506.07464 DeepVideo-R1: Video Reinforcement Fine-Tuning via Difficulty-aware Regressi
        50808, -- 2506.07998 Generative Modeling of Weights: Generalization or Memorization?
        50891, -- 2506.08949 SSS: Semi-Supervised SAM-2 with Efficient Prompting for Medical Imaging Seg
        50910, -- 2506.09161 An Explainable Deep Learning Framework for Brain Stroke and Tumor Progressi
        51004, -- 2506.10401 HPCTransCompile: An AI Compiler Generated Dataset for High-Performance CUDA
        51015, -- 2506.10568 DreamActor-H1: High-Fidelity Human-Product Demonstration Video Generation v
        51041, -- 2506.10943 Self-Adapting Language Models
        51135, -- 2506.13123 SAGDA: Open-Source Synthetic Agriculture Data for Africa
        51372, -- 2506.18527 Auto-Regressively Generating Multi-View Consistent Images
        51465, -- 2506.20525 Industrial Energy Disaggregation with Digital Twin-generated Dataset and Ef
        51495, -- 2506.21107 Unlasting: Unpaired Single-Cell Multi-Perturbation Estimation by Dual Condi
        51559, -- 2506.22753 Degradation-Modeled Multipath Diffusion for Tunable Metalens Photography
        51583, -- 2506.23664 Diffusion Model-based Data Augmentation Method for Fetal Head Ultrasound Se
        51624, -- 2507.01738 DeRIS: Decoupling Perception and Cognition for Enhanced Referring Image Seg
        51849, -- 2507.08794 One Token to Fool LLM-as-a-Judge
        52086, -- 2507.20976 Adapting Vehicle Detectors for Aerial Imagery to Unseen Domains with Weak S
        52281, -- 2508.06426 Shortcut Learning in Generalist Robot Policies: The Role of Dataset Diversi
        52373, -- 2508.10860 From Black Box to Transparency: Enhancing Automated Interpreting Assessment
        53241, -- 2510.00732 EvolProver: Advancing Automated Theorem Proving by Evolving Formalized Prob
        53293, -- 2510.05122 CARE: Cognitive-reasoning Augmented Reinforcement for Emotional Support Con
        53402, -- 2509.26633 OmniRetarget: Interaction-Preserving Data Generation for Humanoid Whole-Bod
        53403, -- 2509.24797 Fidelity-Aware Data Composition for Robust Robot Generalization
        53479, -- 2510.07841 Self-Improving LLM Agents at Test-Time
        53762, -- 2510.19316 KORE: Enhancing Knowledge Injection for Large Multimodal Models via Knowled
        53863, -- 2510.16320 Scaling Laws for Deepfake Detection
        54271, -- 2511.13001 Medal S: Spatio-Textual Prompt Model for Medical Segmentation
        54475, -- 2512.01481 ChronosObserver: Taming 4D World with Hyperspace Diffusion Sampling
        54926, -- 2512.17040 Infinite-Homography as Robust Conditioning for Camera-Controlled Video Gene
        54931, -- 2512.19682 GenEnv: Difficulty-Aligned Co-Evolution Between LLM Agents and Environment
        55448, -- 2601.15892 Stable-DiffCoder: Pushing the Frontier of Code Diffusion Large Language Mod
        55601, -- 2601.21996 Mechanistic Data Attribution: Tracing the Training Origins of Interpretable
        55818, -- 2602.06035 InterPrior: Scaling Generative Control for Physics-Based Human-Object Inter
        56494, -- 2603.04791 Timer-S1: A Billion-Scale Time Series Foundation Model with Serial Scaling
        56578, -- 2603.07066 MedSteer: Counterfactual Endoscopic Synthesis via Training-Free Activation
        58064, -- 2604.17451 SegTTA: Training-Free Test-Time Augmentation for Zero-Shot Medical Imaging
        58118, -- 2604.15857 AHS: Adaptive Head Synthesis via Synthetic Data Augmentations
        58138, -- 2604.15281 R3D: Revisiting 3D Policy Learning
        58275, -- 2604.11269 Speaker Attributed Automatic Speech Recognition Using Speech Aware LLMS
        58352, -- 2604.09067 Temporal Patch Shuffle (TPS): Leveraging Patch-Level Shuffling to Boost Gen
        58784, -- 2603.07554 Nwāchā Munā: A Devanagari Speech Corpus and Proximal Transfer Benchmark for
        58799, -- 2509.17057 RoboManipBaselines: A Unified Framework for Imitation Learning in Robotic M
        58808, -- 2604.16394 A Reference Architecture for Agentic Hybrid Retrieval in Dataset Search
        58813, -- 2603.27101 PRUE: A Practical Recipe for Field Boundary Segmentation at Scale
        58873, -- 2603.25489 Translation Asymmetry in LLMs as a Data Augmentation Factor: A Case Study f
        59303, -- 2603.15988 Something from Nothing: Data Augmentation for Robust Severity Level Estimat
        59427, -- 2603.13967 EchoLVFM: One-Step Video Generation via Latent Flow Matching for Echocardio
        59502, -- 2603.12451 Overcoming the Modality Gap in Context-Aided Forecasting
        59588, -- 2603.20255 Abjad-Kids: An Arabic Speech Classification Dataset for Primary Education
        59703, -- 2603.08260 Seed2Scale: A Self-Evolving Data Engine for Embodied AI via Small to Large
        59779, -- 2603.06256 GazeMoE: Perception of Gaze Target with Mixture-of-Experts
        59869, -- 2603.06704 On the Generalization Capacities of MLLMs for Spatial Intelligence
        60090, -- 2603.00918 Improving Text-to-Image Generation with Intrinsic Self-Confidence Rewards
        60125, -- 2603.13292 Pragma-VL: Towards a Pragmatic Arbitration of Safety and Helpfulness in MLL
        60473, -- 2602.17634 Reverso: Efficient Time Series Foundation Models for Zero-shot Forecasting
        60565, -- 2602.15755 RaCo: Ranking and Covariance for Practical Learned Keypoints
        60923, -- 2603.08720 AnalogToBi: Device-Level Analog Circuit Topology Generation via Bipartite G
        61057, -- 2602.07457 Pull Requests as a Training Signal for Repo-Level Code Editing
        61273, -- 2602.09042 The SJTU X-LANCE Lab System for MSR Challenge 2025
        61363, -- 2602.03123 Beyond Cropping and Rotation: Automated Evolution of Powerful Task-Specific
        61405, -- 2602.02473 HumanX: Toward Agile and Generalizable Humanoid Interaction Skills from Hum
        61580, -- 2509.24739 Toward a Vision-Language Foundation Model for Medical Data: Multimodal Data
        61791, -- 2601.21925 Localizing Speech Deepfakes Beyond Transitions via Segment-Aware Learning
        62092, -- 2601.17586 Stylizing ViT: Anatomy-Preserving Instance Style Transfer for Domain Genera
        62158, -- 2602.13217 VeRA: Verified Reasoning Data Augmentation at Scale
        62187, -- 2601.16113 synthocr-gen: A synthetic ocr dataset generator for low-resource languages-
        62282, -- 2601.14228 Attention-Based Offline Reinforcement Learning and Clustering for Interpret
        62450, -- 2601.10679 Are Your Reasoning Models Reasoning or Guessing? A Mechanistic Analysis of
        62683, -- 2601.06802 Doing More with Less: Data Augmentation for Sudanese Dialect Automatic Spee
        62895, -- 2601.03558 Artificial Intelligence and Skills: Evidence from Contrastive Learning in O
        63010, -- 2601.01992 API: Empowering Generalizable Real-World Image Dehazing via Adaptive Patch
        63083, -- 2601.01088 600k-ks-ocr: a large-scale synthetic dataset for optical character recognit
        63104, -- 2601.00675 RoboReward: General-Purpose Vision-Language Reward Models for Robotics
        63639, -- 2512.14689 CHIP: Adaptive Compliance for Humanoid Control through Hindsight Perturbati
        63723, -- 2512.14754 Revisiting the Reliability of Language Models in Instruction-Following
        63780, -- 2512.15769 Data-Chain Backdoor: Do You Trust Diffusion Models as Generative Data Suppl
        63997, -- 2512.07209 Coherent Audio-Visual Editing via Conditional Audio Generation Following Vi
        64030, -- 2512.06757 XM-ALIGN: Unified Cross-Modal Embedding Alignment for Face-Voice Associatio
        64049, -- 2512.06337 DaGRPO: Rectifying Gradient Conflict in Reasoning via Distinctiveness-Aware
        64150, -- 2512.04084 SimFlow: Simplified and End-to-End Training of Latent Normalizing Flows
        64178, -- 2512.03463 Text-Printed Image: Bridging the Image-Text Modality Gap for Text-centric T
        64230, -- 2512.02361 VACoT: Rethinking Visual Data Augmentation with VLMs
        64256, -- 2512.01895 StyleYourSmile: Cross-Domain Face Retargeting Without Paired Multi-Style Da
        64357, -- 2512.00563 Explainable Multi-Modal Deep Learning for Automatic Detection of Lung Disea
        64493, -- 2511.21032 A Probabilistic Framework for Temporal Distribution Generalization in Indus
        64558, -- 2511.20006 BERT-APC: A Reference-free Framework for Automatic Pitch Correction via Mus
        64661, -- 2511.18578 Re(Visiting) Time Series Foundation Models in Finance
        64796, -- 2511.16711 Motion Transfer-Enhanced StyleGAN for Generating Diverse Macaque Facial Exp
        64904, -- 2511.13715 Segment Anything Across Shots: A Method and Benchmark
        64929, -- 2511.13052 Learning from the Undesirable: Robust Adaptation of Language Models without
        65074, -- 2511.10090 ELYADATA & LIA at NADI 2025: ASR and ADI Subtasks
        65179, -- 2511.08065 I2E: Real-Time Image-to-Event Conversion for High-Performance Spiking Neura
        65327, -- 2511.04623 PromptSep: Generative Audio Separation via Multimodal Prompting
        65528, -- 2511.00801 Med-Banana-50K: A Cross-modality Large-Scale Dataset for Text-guided Medica
        65701, -- 2510.25128 An Analysis of Causal Effect Estimation using Outcome Invariant Data Augmen
        65812, -- 2510.23141 Treble10: A high-quality dataset for far-field speech recognition, dereverb
        65847, -- 2510.22655 Learning Without Augmenting: Unsupervised Time Series Representation Learni
        66131, -- 2510.18143 Learning from Generalization Patterns: An Evaluation-Driven Approach to Enh
        66218, -- 2510.16549 ReviewGuard: Enhancing Deficient Peer Review Detection via LLM-Driven Data
        66352, -- 2510.13979 Do Slides Help? Multi-modal Context for Automatic Transcription of Conferen
        66970, -- 2510.04333 RAP: 3D Rasterization Augmented End-to-End Planning
        67019, -- 2510.03568 How We Won BraTS-SSA 2025: Brain Tumor Segmentation in the Sub-Saharan Afri
        67285, -- 2509.26580 Source Separation for A Cappella Music
        67721, -- 2509.21946 Debiasing Large Language Models in Thai Political Stance Detection via Coun
        67759, -- 2510.00027 Learning Inter-Atomic Potentials without Explicit Equivariance
        67995, -- 2509.17971 Intra-Cluster Mixup: An Effective Data Augmentation Technique for Complemen
        68080, -- 2509.16673 MedCutMix: A Data-Centric Approach to Improve Radiology Vision-Language Pre
        68104, -- 2509.16442 Evaluating the Effectiveness and Scalability of LLM-Based Data Augmentation
        68177, -- 2509.15373 Frustratingly Easy Data Augmentation for Low-Resource ASR
        68193, -- 2509.15045 Synthetic-to-Real Object Detection using YOLOv11 and Domain Randomization S
        68443, -- 2509.10841 Point-Plane Projections for Accurate LiDAR Semantic Segmentation in Small D
        68521, -- 2509.08779 ADHDeepNet From Raw EEG to Diagnosis: Improving ADHD Diagnosis through Temp
        68628, -- 2509.06550 Contrastive Self-Supervised Network Intrusion Detection using Augmented Neg
        68648, -- 2509.06246 Exploring Light-Weight Object Recognition for Real-Time Document Detection
        68762, -- 2509.03636 CausalARC: Abstract Reasoning with Causal World Models
        68808, -- 2509.02550 PalmX 2025: The First Shared Task on Benchmarking LLMs on Arabic and Islami
        68815, -- 2509.02450 EmoPerso: Enhancing Personality Detection with Self-Supervised Emotion-Awar
        68988, -- 2509.04471 MOSAIC: A Multilingual, Taxonomy-Agnostic, and Computationally Efficient Ap
        69247, -- 2508.17444 MahaParaphrase: A Marathi Paraphrase Detection Corpus and BERT-based Models
        69325, -- 2508.16239 UniEM-3M: A Universal Electron Micrograph Dataset for Microstructural Segme
        69388, -- 2508.15180 PuzzleClone: An SMT-Powered Framework for Synthesizing Verifiable Data
        69585, -- 2508.12213 Towards Generalizable Human Activity Recognition: A Survey
        69606, -- 2508.11808 Labels or Input? Rethinking Augmentation in Multimodal Hate Detection
        69616, -- 2508.11464 Data-Driven Deepfake Image Detection Method - The 2024 Global Deepfake Ima
        69759, -- 2508.09550 Exploring the Equivalence of Closed-Set Generative and Real Data Augmentati
        69763, -- 2508.09494 Learning Facts at Scale with Active Reading
        69862, -- 2508.07926 Score Augmentation for Diffusion Models
        70013, -- 2508.05941 Latent Policy Barrier: Learning Robust Visuomotor Policies by Staying In-Di
        70021, -- 2508.05772 MAISI-v2: Accelerated 3D High-Resolution Medical Image Synthesis with Recti
        70108, -- 2508.09168 SVGen: Interpretable Vector Graphics Generation with Large Language Models
        70161, -- 2508.04001 ConvMix: A Mixed-Criteria Data Augmentation Framework for Conversational De
        70177, -- 2508.03690 Veila: Panoramic LiDAR Generation from a Monocular RGB Image
        70447, -- 2508.00438 Diffusion-Based User-Guided Data Augmentation for Coronary Stenosis Detecti
        70448, -- 2507.19673 SynPAIN: A Synthetic Dataset of Pain and Non-Pain Facial Expressions
        70525, -- 2508.06517 Frequency Prior Guided Matching: A Data Augmentation Approach for Generaliz
        70543, -- 2508.05657 Beyond Single Labels: Improving Conversational Recommendation through LLM-P
        70651, -- 2507.20506 An Improved YOLOv8 Approach for Small Target Detection of Rice Spikelet Flo
        70770, -- 2507.18448 Restoring Rhythm: Punctuation Restoration Using Transformer Models for Bang
        70913, -- 2507.15857 Diffusion Beats Autoregressive in Data-Constrained Settings
        71053, -- 2507.12698 Pixel Perfect MegaMed: A Megapixel-Scale Vision-Language Foundation Model f
        71188, -- 2507.09619 Generate Aligned Anomaly: Region-Guided Few-Shot Anomaly Image-Mask Pair Sy
        71342, -- 2507.05764 PSAT: Pediatric Segmentation Approaches via Adult Augmentations and Transfe
        71557, -- 2507.00802 TRACE: Temporally Reliable Anatomically-Conditioned 3D CT Generation with E
        71657, -- 2506.23038 Inpainting is All You Need: A Diffusion-based Augmentation Method for Semi-
        71723, -- 2506.20817 RAG-VisualRec: An Open Resource for Vision- and Text-Enhanced Retrieval-Aug
        72212, -- 2506.05872 Domain-RAG: Retrieval-Guided Compositional Image Generation for Cross-Domai
        72224, -- 2411.08638 Graph Neural Network Generalization with Gaussian Mixture Model Based Augme
        72267, -- 2506.04367 Fine-Tuning Video Transformers for Word-Level Bangla Sign Language: A Compa
        72297, -- 2506.03593 Is linguistically-motivated data augmentation worth it?
        72457, -- 2506.00795 Bridging Supervised and Temporal Difference Learning with Q-Conditioned Max
        72477, -- 2506.00633 Text-to-CT Generation via 3D Latent Diffusion Model with Contrastive Vision
        72515, -- 2505.24361 Revisiting Cross-Modal Knowledge Distillation: A Disentanglement Approach f
        72725, -- 2505.19616 Diagnosing and Mitigating Modality Interference in Multimodal Large Languag
        72749, -- 2505.18956 How Do Images Align and Complement LiDAR? Towards a Harmonized Multi-modal
        72818, -- 2505.17529 Do You Keep an Eye on What I Ask? Mitigating Multimodal Hallucination via A
        72874, -- 2506.11049 15,500 Seconds: Lean UAV Classification Using EfficientNet and Lightweight
        72900, -- 2505.15255 Boosting Large Language Models for Mental Manipulation Detection via Data A
        72986, -- 2505.12477 Joint Embedding vs Reconstruction: Provable Benefits of Latent Space Predic
        73009, -- 2505.11920 H2R: A Human-to-Robot Data Augmentation for Robot Pre-training from Videos
        73044, -- 2505.10993 Content Generation Models in Computational Pathology: A Comprehensive Surve
        73163, -- 2505.04656 MeshGen: Generating PBR Textured Mesh with Render-Enhanced Auto-Encoder and
        73265, -- 2504.20498 Style-Adaptive Detection Transformer for Single-Source Domain Generalized O
        73268, -- 2504.20426 RV-Syn: Rational and Verifiable Mathematical Reasoning Data Synthesis based
        73274, -- 2504.19981 Accurate and Diverse LLM Mathematical Reasoning via Automated PRM-Guided GF
        73464, -- 2504.13175 Novel Demonstration Generation with Gaussian Splatting Enables Robust One-S
        73510, -- 2504.10485 Decoupled Diffusion Sparks Adaptive Scene Generation
        73534, -- 2504.09645 Myanmar XNLI: Building a Dataset and Exploring Low-resource Approaches to N
        73585, -- 2504.07606 Heart Failure Prediction using Modal Decomposition and Masked Autoencoders
        73601, -- 2504.06915 An Analysis of Temporal Dropout in Earth Observation Time Series for Regres
        73644, -- 2504.05849 On the Importance of Conditioning for Privacy-Preserving Data Augmentation
        73726, -- 2504.02293 State-of-the-Art Translation of Text-to-Gloss using mBART : A case study of
        73782, -- 2504.00339 VNJPTranslate: A comprehensive pipeline for Vietnamese-Japanese translation
        73897, -- 2503.18738 RoboEngine: Plug-and-Play Robot Data Augmentation with Semantic Robot Segme
        73898, -- 2503.18719 Boosting Resolution Generalization of Diffusion Transformers with Randomize
        73974, -- 2503.15044 SPADE: Systematic Prompt Framework for Automated Dialogue Expansion in Mach
        74222, -- 2503.05916 SAS: Segment Anything Small for Ultrasound - A Non-Generative Data Augment
        74562, -- 2502.14795 Humanoid-VLA: Towards Universal Humanoid Control with Visual Integration
        74677, -- 2502.10663 REAL: Realism Evaluation of Text-to-Image Generation Models for Effective D
        74831, -- 2502.05378 NextBestPath: Efficient 3D Mapping of Unseen Environments
        74895, -- 2502.03238 Long-tailed Medical Diagnosis with Relation-aware Representation Learning a
        75134, -- 2501.11759 Poison-RAG: Adversarial Data Poisoning Attacks on Retrieval-Augmented Gener
        75663, -- 2412.00138 Adversarial Exploitation of Data Diversity Improves Visual Localization
        75863, -- 2411.02733 DDFAV: Remote Sensing Large Vision Language Models Dataset and Evaluation B
        75880, -- 2411.01494 Finding NeMo: Negative-mined Mosaic Augmentation for Referring Image Segmen
        75928, -- 2411.02592 Decoupled Data Augmentation for Improving Image Classification
        76111, -- 2410.06944 CSSL: Contrastive Self-Supervised Learning for Dependency Parsing on Relati
        76203, -- 2410.13867 Self-Supervised Pre-Training with Joint-Embedding Predictive Architecture B
        76209, -- 2410.01638 Data Extrapolation for Text-to-image Generation on Small Datasets
        76288, -- 2409.16461 Strategies for Improving NL-to-FOL Translation with LLMs: Data Generation,
        76296, -- 2409.16118 TabEBM: A Tabular Data Augmentation Method with Distinct Class-Specific Ene
        76314, -- 2409.14878 InterMind: A Doctor-Patient-Family Interactive Depression Assessment System
        76341, -- 2409.12470 HSIGene: A Foundation Model For Hyperspectral Image Generation
        76482, -- 2409.01219 A Review of Image Retrieval Techniques: Data Augmentation and Adversarial L
        76507, -- 2409.07462 S-MolSearch: 3D Semi-supervised Contrastive Learning for Bioactive Molecule
        76558, -- 2408.10658 Learning Instruction-Guided Manipulation Affordance via Large Models for Em
        76561, -- 2408.10951 Wave-Mask/Mix: Exploring Wavelet-Based Augmentations for Time Series Foreca
        76692, -- 2407.16842 Adapting Image-based RL Policies via Predicted Rewards
        76754, -- 2407.10935 STARS: Self-supervised Tuning for 3D Action Recognition in Skeleton Sequenc
        76786, -- 2403.11202 Data is all you need: Finetuning LLMs for Chip Design via an Automated desi
        76953, -- 2406.12471 Fighting Randomness with Randomness: Mitigating Optimisation Instability of
        76995, -- 2406.11903 A Survey of Large Language Models for Financial Applications: Progress, Pro
        77059, -- 2406.05427 Decision Mamba: A Multi-Grained State Space Model with Self-Evolution Regul
        77193, -- 2405.16456 Dominant Shuffle: A Simple Yet Powerful Data Augmentation for Time-series P
        77214, -- 2405.14870 An Empirical Study of Training State-of-the-Art LiDAR Segmentation Models
        77536, -- 2404.00681 CoUDA: Coherence Evaluation via Unified Data Augmentation
        77557, -- 2403.16385 Synthesize Step-by-Step: Tools, Templates and LLMs as Data Generators for R
        77588, -- 2403.15553 Efficiently Estimating Mutual Information Between Attributes Across Tables
        77658, -- 2403.07113 Class Imbalance in Object Detection: An Experimental Diagnosis and Study of
        77659, -- 2403.07066 Re-Simulation-based Self-Supervised Learning for Pre-Training Foundation Mo
        77922, -- 2401.11487 Towards Better Inclusivity: A Diverse Tweet Corpus of English Varieties
        78059, -- 2312.14188 Enhancing Neural Theorem Proving through Data Augmentation and Dynamic Samp
        78128, -- 2312.05933 Temporal Supervised Contrastive Learning for Modeling Patient Risk Progress
        78131, -- 2312.05790 SimPSI: A Simple Strategy to Preserve Spectral Information in Time Series D
        78354, -- 2310.12972 CCIL: Continuity-based Data Augmentation for Corrective Imitation Learning
        78449, -- 2309.17352 Improving Audio Captioning Models with Fine-grained Audio Features, Text Em
        78503, -- 2309.11202 Using Artificial Intelligence for the Automation of Knitting Patterns
        78624, -- 2308.11084 PMVC: Data Augmentation-Based Prosody Modeling for Expressive Voice Convers
        78785, -- 2304.04000 SimbaML: Connecting Mechanistic Models and Machine Learning with Augmented
        78791, -- 2302.10433 On discrete symmetries of robotics systems: A group-theoretic and data-driv
        78954, -- 2305.18977 Cross Encoding as Augmentation: Towards Effective Educational Text Classifi
        78968, -- 2305.17476 Toward Understanding Generative Data Augmentation
        78982, -- 2305.16430 Too Few Bug Reports? Exploring Data Augmentation for Improved Changeset-bas
        79086, -- 2304.14334 ZeroShotDataAug: Generating and Augmenting Training Data with ChatGPT
        79209, -- 2303.14254 Towards Diverse and Coherent Augmentation for Time-Series Forecasting
        79230, -- 2303.10340 3D Data Augmentation for Driving Scenes on Camera
        79342, -- 2302.11097 A Multi-Modal Neural Geometric Solver with Textual Clauses Parsed from Diag
        79351, -- 2302.09292 FrAug: Frequency Domain Augmentation for Time Series Forecasting
        79373, -- 2302.03379 Data augmentation for machine learning of chemical process flowsheets
        79390, -- 2302.00884 Exploring Invariant Representation for Visible-Infrared Person Re-Identific
        79404, -- 2301.12730 General Covariance Data Augmentation for Neural PDE Solvers
        79421, -- 2301.09072 ContraBERT: Enhancing Code Pre-trained Models via Contrastive Learning
        79641, -- 2210.12285 Exploring Representation-Level Augmentation for Code Search
        79670, -- 2206.04670 PointNeXt: Revisiting PointNet++ with Improved Training and Scaling Strateg
        79700, -- 2210.00716 rPPG-Toolbox: Deep Remote PPG Toolbox
        79790, -- 2208.05810 Towards Sequence-Level Training for Visual Tracking
        79791, -- 2208.05573 Data Augmentation for Improving Emotion Recognition in Software Engineering
        79878, -- 2206.07117 TriHorn-Net: A Model for Accurate Depth-Based 3D Hand Pose Estimation
        79959, -- 2205.11824 TDASS: Target Domain Adaptation Speech Synthesis Framework for Multi-speake
        79992, -- 2205.05474 DeepFilterNet2: Towards Real-Time Speech Enhancement on Embedded Devices fo
        80040, -- 2204.11205 EPiDA: An Easy Plug-in Data Augmentation Framework for High Performance Tex
        80063, -- 2204.06812 Learning to Generalize to More: Continuous Semantic Augmentation for Neural
        80068, -- 2204.06309 Call-sign recognition and understanding for noisy air-traffic transcripts u
        80108, -- 2204.05132 A Spiking Neural Network based on Neural Manifold for Augmenting Intracorti
        80220, -- 2202.03047 Data set creation and empirical analysis for detecting signs of depression
        80270, -- 2201.01857 Multi-Grid Redundant Bounding Box Annotation for Accurate Object Detection
        80356, -- 2111.15121 Pyramid Adversarial Training Improves ViT Performance
        80419, -- 2102.08604 SWAD: Domain Generalization by Seeking Flat Minima
        80423, -- 2110.15288 Hyper-Representations: Self-Supervised Representation Learning on Neural Ne
        80438, -- 2103.13279 FakeMix Augmentation Improves Transparent Object Detection
        80525, -- 2109.05712 Contrastive Learning for Context-aware Neural Machine TranslationUsing Core
        80712, -- 2105.09880 DeepDarts: Modeling Keypoints as Objects for Automatic Scorekeeping in Dart
        80724, -- 2105.06323 Bootstrapping User and Item Representations for One-Class Collaborative Fil
        80761, -- 2104.11641 Social Influence Prediction with Train and Test Time Augmentation for Graph
        80821, -- 2103.10158 TrivialAugment: Tuning-free Yet State-of-the-Art Data Augmentation
        80862, -- 2102.12664 MixSpeech: Data Augmentation for Low-resource Automatic Speech Recognition
        80913, -- 2011.13183 TinaFace: Strong but Simple Baseline for Face Detection
        80948, -- 2012.12741 Exploring Data Augmentation for Multi-Modality 3D Object Detection
        80988, -- 2012.01321 Red Blood Cell Segmentation with Overlapping Cell Separation and Classifica
        81096, -- 2010.01724 TextAttack: Lessons learned in designing Python frameworks for NLP
        81180, -- 2008.03616 Variable frame rate-based data augmentation to handle speaking-style variab
        81208, -- 2007.07966 An Ensemble of Convolutional Neural Networks for Audio Classification
        81225, -- 2005.10052 Lung Segmentation from Chest X-rays using Variational Data Imputation
        81243, -- 2006.14619 Recurrent Quantum Neural Networks
        81280, -- 2006.02954 Handling missing data in model-based clustering
        81374, -- 2004.05328 DeepSentiPers: Novel Deep Learning Models Trained Over Proposed Augmented P
        81589, -- 1909.11870 Classification of Histopathological Biopsy Images Using Ensemble of Deep Le
        81694, -- 1906.06423 Fixing the train-test resolution discrepancy
        81753, -- 1904.09229 XLSor: A Robust and Accurate Lung Segmentor on Chest X-Rays Using Criss-Cro
        81772, -- 1904.02285 HoloDetect: Few-Shot Learning for Error Detection
        81869, -- 1811.06669 AclNet: efficient end-to-end audio classification CNN
        81991, -- 1806.04074 Semantically Selective Augmentation for Deep Compact Person Re-Identificati
        82077, -- 1803.01199 Chest X-Ray Analysis of Tuberculosis by Deep Learning with Segmentation and
        82357, -- 1608.04363 Deep Convolutional Neural Networks and Data Augmentation for Environmental
        82997, -- 2605.09262 Reinforcing Multimodal Reasoning Against Visual Degradation
        83531, -- 2605.16787 The Unlearnability Phenomenon in RLVR for Language Models
        83650, -- external ImageNet Classification with Deep Convolutional Neural Networks
        83664, -- 2605.08214 Bangla-WhisperDiar: Fine-Tuning Whisper and PyAnnote for Bangla Long-Form S
        84238, -- 2511.19394 BackSplit: The Importance of Sub-dividing the Background in Biomedical Lesi
        84283, -- 2511.22950 RobotSeg: A Model and Dataset for Segmenting Robots in Image and Video
        84394, -- 2512.13093 PvP: Data-Efficient Humanoid Robot Learning with Proprioceptive-Privileged
        84551, -- 2602.19385 Adaptive Data Augmentation with Multi-armed Bandit: Sample-Efficient Embedd
        84623, -- 2602.22549 DrivePTS: A Progressive Learning Framework with Textual and Structural Enha
        84758, -- 2603.05042 CoIn3D: Revisiting Configuration-Invariant Multi-Camera 3D Object Detection
        85098, -- 2603.24934 CVA: Context-aware Video-text Alignment for Video Temporal Grounding
        85379, -- 2604.14259 Continual Learning for fMRI-Based Brain Disorder Diagnosis via Functional C
        85631, -- 2605.30561 VLM3: Vision Language Models Are Native 3D Learners
        85707, -- 2506.02689 MASTER: Enhancing Large Language Model via Multi-Agent Simulated Teaching
        85805, -- 2507.07348 Zero-Shot Context Generalization in Reinforcement Learning from Few Trainin
        85820, -- 2505.23663 AMBER: Adaptive Mesh Generation by Iterative Mesh Resolution Prediction
        85873, -- 2506.04906 TRACE: Contrastive learning for multi-trial time series data in neuroscienc
        85949, -- 2510.08177 Long-tailed Recognition with Model Rebalancing
        85958, -- 2506.03089 Explicitly Modeling Subcortical Vision with a Neuro-Inspired Front-End Impr
        85984, -- 2503.13497 Is Limited Participant Diversity Impeding EEG-based Machine Learning?
        85993, -- 2506.15691 What Do Latent Action Models Actually Learn?
        85996, -- 2505.22643 Spiral: Semantic-Aware Progressive LiDAR Scene Generation
        86039, -- 2506.23863 Puzzles: Unbounded Video-Depth Augmentation for Scalable End-to-End 3D Reco
        86096, -- 2510.07823 Enhancing Visual Prompting through Expanded Transformation Space and Overfi
        86111, -- 2505.20280 Lorentz Local Canonicalization: How to make any Network Lorentz-Equivariant
        86141, -- 2506.04206 A Few Moments Please: Scalable Graphon Learning via Moment Matching
        86194, -- 2506.02350 Truth over Tricks: Measuring and Mitigating Shortcut Learning in Misinforma
        86272, -- 2506.01728 Principled data augmentation for learning to solve quadratic programming pr
        86288, -- 2502.09890 Rao-Blackwell Gradient Estimators for Equivariant Denoising Diffusion
        86410, -- 2509.23829 DexFlyWheel: A Scalable and Self-improving Data Generation Framework for De
        86550, -- 2510.03608 Diffusion-Classifier Synergy: Reward-Aligned Learning via Mutual Boosting L
        86588, -- 2506.16802 Seeing What Matters: Generalizable AI-generated Video Detection with Forens
        86659, -- 2510.15783 ReCon: Region-Controllable Data Augmentation with Rectification and Alignme
        86665, -- 2506.12323 Doctor Approved: Generating Medically Accurate Skin Disease Images through
        86852, -- 2501.01015 Boosting Adversarial Transferability with Spatial Adversarial Alignment
        86917, -- 2510.05527 Transfer Learning on Edge Connecting Probability Estimation Under Graphon M
        87066, -- 2510.02731 Hybrid-Collaborative Augmentation and Contrastive Sample Adaptive-Different
        87131, -- 2507.06450 A Semantic Parsing Framework for End-to-End Time Normalization
        87190, -- 2510.02119 Non-Asymptotic Analysis Of Data Augmentation For Precision Matrix Estimatio
        87219, -- 2509.25831 MIDAS: Misalignment-based Data Augmentation Strategy for Imbalanced Multimo
        87243, -- 2510.15194 Salient Concept-Aware Generative Data Augmentation
        87386, -- 2509.26074 Limited Preference Data? Learning Better Reward Model with Latent Space Syn
        87416, -- 2503.05919 From Style to Facts: Mapping the Boundaries of Knowledge Injection with Fin
        87464, -- 2510.11133 Test-Time Adaptation by Causal Trimming
        87772, -- 2507.04302 Adversarial Data Augmentation for Single Domain Generalization via Lyapunov
        87824, -- 2412.11284 Learning Normal Flow Directly From Events
        87871, -- 2509.16968 Penalizing Boundary Activation for Object Completeness in Diffusion Models
        87918, -- 2507.09896 Measuring the Impact of Rotation Equivariance on Aerial Object Detection
        87991, -- 2508.11185 CHARM3R: Towards Unseen Camera Height Robust Monocular 3D Detector
        88120, -- 2503.13025 PoseSyn: Synthesizing Diverse 3D Pose Data from In-the-Wild 2D Data
        88124, -- 2503.08510 External Knowledge Injection for CLIP-Based Class-Incremental Learning
        88164, -- 2505.04963 ViCTr: Vital Consistency Transfer for Pathology Aware Image Synthesis
        88301, -- 2509.05543 DuoCLR: Dual-Surrogate Contrastive Learning for Skeleton-based Human Action
        88333, -- 2503.06361 Adversarial Robustness of Discriminative Self-Supervised Learning in Vision
        88417, -- 2507.12001 AU-Blendshape for Fine-grained Stylized 3D Facial Expression Manipulation
        88511, -- 2506.23440 PathDiff: Histopathology Image Synthesis with Unpaired Text and Mask Condit
        88632, -- 2506.06853 Curvature Enhanced Data Augmentation for Regression
        88695, -- 2505.00626 The Illusion of Role Separation: Hidden Shortcuts in LLM Role Learning (and
        88823, -- 2410.14038 Sliding Puzzles Gym: A Scalable Benchmark for State Representation in Visua
        88868, -- 2506.05513 Geometric and Physical Constraints Synergistically Enhance Neural PDE Surro
        88960, -- 2406.06504 Equivariant Neural Tangent Kernels
        88979, -- 2505.21317 A Cross Modal Knowledge Distillation & Data Augmentation Recipe for Improvi
        89046, -- 2507.04283 Clustering via Self-Supervised Diffusion
        89049, -- 2505.20840 Aggregation Buffer: Revisiting DropEdge with a New Parameter Block
        89052, -- 2505.16734 Maximum Total Correlation Reinforcement Learning
        89132, -- 2411.09858 One Leaf Reveals the Season: Occlusion-Based Contrastive Learning with Sema
        89144, -- 2505.19659 LangDAug: Langevin Data Augmentation for Multi-Source Domain Generalization
        89175, -- 2410.07441 Zero Shot Generalization of Vision-Based RL Without Data Augmentation
        89220, -- 2412.11044 Understanding and Mitigating Memorization in Diffusion Models for Tabular D
        89282, -- 2406.01425 Adaptive Sensitivity Analysis for Robust Augmentation against Natural Corru
        89415, -- 2501.18901 Lightspeed Geometric Dataset Distance via Sliced Optimal Transport
        89503, -- 2504.13548 Beyond One-Hot Labels: Semantic Mixing for Model Calibration
        89550, -- 2505.22196 An Augmentation-Aware Theory for Self-Supervised Contrastive Learning
        89730, -- 2503.02445 BRIDGE: Bootstrapping Text to Control Time-Series Generation via Multi-Agen
        89918, -- 2505.17072 Safety Alignment Can Be Not Superficial With Explicit Safety Signals
        89999, -- 2502.02410 Privacy Amplification by Structured Subsampling for Deep Differentially Pri
        90031, -- 2502.19758 Learning with Exact Invariances in Polynomial Time
        90121, -- 2503.17984 Taste More, Taste Better: Diverse Data and Strong Model Boost Semi-Supervis
        90198, -- 2504.09623 Ges3ViG : Incorporating Pointing Gestures into Language-Based 3D Visual Gro
        90229, -- 2503.21991 BOOTPLACE: Bootstrapped Object Placement with Detection Transformers
        90290, -- 2408.11280 Exploring Scene Affinity for Semi-Supervised LiDAR Semantic Segmentation
        90333, -- 2505.19799 A Regularization-Guided Equivariant Approach for Image Restoration
        90392, -- 2501.04666 Enhancing Virtual Try-On with Synthetic Pairs and Error-Aware Noise Schedul
        90439, -- 2505.12745 PEER Pressure: Model-to-Model Regularization for Single Source Domain Gener
        90459, -- 2306.09363 A Simple Data Augmentation for Feature Distribution Skewed Federated Learni
        90659, -- 2503.20724 Dynamic Motion Blending for Versatile Motion Editing
        90760, -- 2503.12539 BFANet: Revisiting 3D Semantic Segmentation with Boundary Feature Analysis
        90980, -- 2505.17721 SeaLion: Semantic Part-Aware Latent Point Diffusion Models for 3D Generatio
        91008, -- 2503.00359 Solving Instance Detection from an Open-World Perspective
        91219, -- 2410.06262 SymDiff: Equivariant Diffusion via Stochastic Symmetrisation
        91334, -- 2408.06321 EqNIO: Subequivariant Neural Inertial Odometry
        91400, -- 2311.01434 Tailoring Mixup to Data for Calibration
        91707, -- 2502.18195 Multi-Perspective Data Augmentation for Few-shot Object Detection
        91749, -- 2502.03201 SpaceGNN: Multi-Space Graph Neural Network for Node Anomaly Detection with
        91844, -- 2402.06855 For Better or For Worse? Learning Minimum Variance Features With Label Augm
        91939, -- 2405.16124 Unsupervised Meta-Learning via In-Context Learning
        92267, -- 2410.04472 Collapsed Language Models Promote Fairness
        92353, -- 2410.21526 Not All LLM-Generated Data Are Equal: Rethinking Data Weighting in Text Cla
        92661, -- 2503.11339 Contextual Similarity Distillation: Ensemble Uncertainties with a Single Mo
        92973, -- 2506.05339 Flattery, Fluff, and Fog: Diagnosing and Mitigating Idiosyncratic Biases in
        93100, -- 2505.21813 Optimizing Data Augmentation through Bayesian Model Selection
        93192, -- 2509.24886 Adaptive Canonicalization with Application to Invariant Anisotropic Geometr
        93275, -- 2603.18202 R2-Dreamer: Redundancy-Reduced World Models without Decoders or Augmentatio
        93285, -- 2512.06987 OXtal: An All-Atom Diffusion Model for Organic Crystal Structure Prediction
        93353, -- 2506.16404 Generating Directed Graphs with Dual Attention and Asymmetric Encoding
        93433, -- 2410.00718 Pseudo-Non-Linear Data Augmentation: A Constrained Energy Minimization View
        93494, -- 2510.01349 To Augment or Not to Augment? Diagnosing Distributional Symmetry Breaking
        93779, -- 2602.03895 Benchmarking Bias Mitigation Toward Fairness Without Harm from Vision to LV
        93975, -- 2509.19743 Rectified Decoupled Dataset Distillation: A Closer Look for Fair and Compre
        94067, -- 2510.04686 How does the optimizer implicitly bias the model merging loss landscape?
        94110, -- 2603.03323 Discern Truth from Falsehood: Reducing Over-Refusal via Contrastive Refinem
        94141, -- 2507.09061 Action Chunking and Data Augmentation Yield Exponential Improvements in Beh
        94212, -- 2508.02758 CTBench: Cryptocurrency Time Series Generation Benchmark
        94316, -- 2602.15155 Refine Now, Query Fast: A Decoupled Refinement Paradigm for Implicit Neural
        94937, -- 2603.18891 PromptHub: Enhancing Multi-Prompt Visual In-Context Learning with Locality-
        95095, -- 2606.06155 AffordanceVLA: A Vision-Language-Action Model Empowering Action Generation
        95141, -- external Intelligent Coarse Dropout and Anti-ICD: Saliency-Guided Masking Augmentati
        95722, -- external A Data-Driven Approach for Control and Stabilization of a Single Actuator M
        95878, -- 2503.05997 Learning to Drive by Imitating Surrounding Vehicles
        96114, -- 2509.19454 ROPA: Synthetic Robot Pose Generation for RGB-D Bimanual Data Augmentation
        96184, -- external PDLNet: Learning Point Cloud Distortion for Unsupervised Cross-Domain Point
        96212, -- external LangEditor: Natural Language-Driven 4D Editing for Improved Controllability
        96267, -- external Unsupervised Domain Adaptation for Robust Imitation Learning under Visual P
        96342, -- 2511.02239 LACY: A Vision-Language Model-Based Language-Action Cycle for Self-Improvin
        96633, -- external EDAIL: Adversarial Imitation Learning Via Exploration-Driven Data Augmentat
        96671, -- external Learning to Annotate Delayed and False AEB Events: A Practical System for E
        96809, -- 2512.23147 GeoTeacher: Geometry-Guided Semi-Supervised 3D Object Detection
        97008, -- 2502.15679 BOSS: Benchmark for Observation Space Shift in Long-Horizon Task
        97163, -- 2505.18899 Beyond Domain Randomization: Event-Inspired Perception for Visually Robust
        97343, -- 2502.11375 Robot Deformable Object Manipulation Via NMPC-Generated Demonstrations in D
        97525, -- external Point Cloud Segmentation for Autonomous Clip Positioning in Laparoscopic Ch
        97530, -- 2603.10451 FAR-Dex: Few-Shot Data Augmentation and Adaptive Residual Policy Refinement
        97546, -- 2511.16494 Physics-Informed Machine Learning for Efficient Sim-To-Real Data Augmentati
        98211, -- 2601.05212 FlowLet: Conditional 3D Brain MRI Synthesis using Wavelet Flow Matching
        98362, -- 2606.08670 WaveDiT: Distribution-Aware Wavelet Flow Matching for Efficient 3D Brain MR
        98576, -- 2606.17053 Context-Aware RL for Agentic and Multimodal LLMs
        98729, -- 2606.16246 Demystifying Training-Time Augmentation for Data-Constrained Language Model
        99005, -- 2606.31029 TerraDiT-Ω: Unified Spatial Control for Satellite Image Synthesis with Any
        99088, -- 2607.02508 From SRA to Self-Flow: Data Augmentation or Self-Supervision?
        99095, -- 2607.02271 AGVBench: A Reliability-Oriented Benchmark of Data Augmentation for Vein Re
        99123, -- 2602.02978 Geometric Coherence Learning for Structuring Value Functions in Plain MDPs
        99135, -- 2603.27448 GIFT: Bootstrapping Image-to-CAD Program Synthesis via Geometric Feedback
        99328, -- 2603.22213 SPA: A Simple but Tough-to-Beat Baseline for Knowledge Injection
        99444, -- 2408.09929 Data Augmentation of Contrastive Learning is Estimating Positive-incentive
        99485, -- 2409.06282 ReAugment: Targeted Few-Shot Time Series Augmentation via Model Zoo-Guided
        99892, -- 2506.05762 BiTrajDiff: Bidirectional Trajectory Generation with Diffusion Models for O
        100043, -- 2508.12176 Scalable RF Simulation in Generative 4D Worlds
        100073, -- 2507.15356 RAD: Retrieval High-quality Demonstrations to Enhance Decision-making
        100209, -- 2509.21530 Expert-guided Clinical Text Augmentation via Query-Based Model Collaboratio
        100404, -- 2605.21241 Divide and Contrast: Learning Robust Temporal Features without Augmentation
        100442, -- 2602.00822 Safety-Efficacy Trade Off: Robustness against Data-Poisoning
        100654, -- 2605.02757 Seeing Realism from Simulation: Efficient Video Transfer for Vision-Languag
        100972, -- 2506.10226 ScoreMix: Synthetic Data Generation by Score Composition in Diffusion Model
        101031, -- 2605.13401 Trajectory-Level Data Augmentation for Offline Reinforcement Learning
        101398, -- 2603.19294 Maximizing Mutual Information Between Prompt and Response Improves LLM Perf
        101409, -- 2505.17786 Supervised Graph Contrastive Learning for Gene Regulatory Networks
        101683, -- 2512.19602 No Data? No Problem: Robust Vision-Tabular Learning with Missing Values
        101877, -- 2603.02193 Symbol-Equivariant Recurrent Reasoning Models
        101969, -- 2605.11134 Spurious Correlation Learning in Preference Optimization: Mechanisms, Conse
        102065, -- 2510.03690 From Moments to Models: Graphon-Mixture Learning for Mixup and Contrastive
        102409, -- 2605.30487 Configurable Reward Model for Balanced Safety Alignment
        102504, -- 2605.22484 Supervised Classification Heads as Semantic Prototypes: Unlocking Vision-La
        102606, -- 2208.11247 SwinFIR: Revisiting the SwinIR with Fast Fourier Convolution and Improved T
        102698, -- 2403.09502 EquiAV: Leveraging Equivariance for Audio-Visual Contrastive Learning
        102750, -- 2601.00263 Parallel Universes, Parallel Languages: A Comprehensive Study on LLM-based
        102793, -- 2507.06573 From Data-Centric to Sample-Centric: Enhancing LLM Reasoning via Progressiv
        102995, -- 2508.07642 Breaking Down and Building Up: Mixture of Skill-Based Vision-and-Language N
        103132, -- 2511.01526 Difficulty-Controllable Cloze Question Distractor Generation
        103387, -- 2502.04419 Understanding and Mitigating Bias Inheritance in LLM-based Data Augmentatio
        103403, -- 2510.10182 A Survey of Inductive Reasoning for Large Language Models
        103724, -- 2605.10627 Interpretable Coreference Resolution Evaluation Using Explicit Semantics
        103731, -- 2605.12242 Mind the Pause: Disfluency-Aware Objective Tuning for Multilingual Speech C
        103804, -- 2604.10150 Learning from Emptiness: De-biasing Listwise Rerankers with Content-Agnosti
        103893, -- 2006.12862 Automatic Data Augmentation for Generalization in Deep Reinforcement Learni
        103935, -- 2402.11523 Neighborhood-Enhanced Supervised Contrastive Learning for Collaborative Fil
        104082, -- 2503.17978 PIM: Physics-Informed Multi-task Pre-training for Improving Inertial Sensor
        104084, -- 2109.02054 Sensor Data Augmentation by Resampling for Contrastive Learning in Human Ac
        104100, -- 2505.10312 SOS: A Shuffle Order Strategy for Data Augmentation in Industrial Human Act
        104119, -- 2411.14070 Towards Adaptive Asynchronous Federated Learning for Human Activity Recogni
        104162, -- 2105.02465 PoseAug: A Differentiable Pose Augmentation Framework for 3D Human Pose Est
        104164, -- 1607.02046 MoCap-guided Data Augmentation for 3D Pose Estimation in the Wild
        104177, -- 2006.07778 Cascaded deep monocular 3D human pose estimation with evolutionary training
        104236, -- 2211.06018 MDFlow: Unsupervised Optical Flow Learning by Reliable Mutual Knowledge Dis
        104614, -- 2407.05357 On the power of data augmentation for head pose estimation
        104630, -- 2408.01566 Full-range Head Pose Geometric Data Augmentations
        104754, -- 2606.18243 MOCHI: Motion Enhancement of Collaborative Human-object Interactions
        104757, -- 2605.21766 BodyReLux: Temporally Consistent Full-Body Video Relighting
        104916, -- external Accurate Boundary Alignment and Realism Enhancement for Colonoscopic Polyp
        104918, -- external ADA: An Adaptive Augmentation Framework for Single-Source Domain Generaliza
        104923, -- external Adaptive Adversarial Data Augmentation with Trajectory Constraint for Alzhe
        105002, -- 2509.05754 CardiacFlow: 3D+t Four-Chamber Cardiac Shape Completion and Generation via
        105006, -- 2505.22489 Cascaded 3D Diffusion Models for Whole-body 3D 18-F FDG PET/CT synthesis fr
        105054, -- external Controllable Image Synthesis Workflow for Enhancing Cervical Cell Detection
        105085, -- external DCT-Net: Dual-branch CT Reconstruction from Orthogonal X-rays with Diffusio
        105184, -- 2508.05465 F2PASeg: Feature Fusion for Pituitary Anatomy Segmentation in Endoscopic Su
        105209, -- external FOCUS: Feature Replay with Optimized Channel-Consistent Dropout for U-Net S
        105369, -- 2508.03752 M3HL: Mutual Mask Mix with High-Low Level Feature Consistency for Semi-Supe
        105391, -- 2507.00377 MedDiff-FT: Data-Efficient Diffusion Model Fine-tuning with Structural Guid
        105430, -- external MorphoBoost: Morphology-Driven Boundary Enhancement Model for Accurate Segm
        105509, -- 2507.14833 Paired Image Generation with Diffusion-Guided Diffusion Models
        105599, -- external Region-Based Text-Consistent Augmentation for Multimodal Medical Segmentati
        105612, -- 2508.21254 Reverse Imaging for Wide-spectrum Generalization of Cardiac MRI Segmentatio
        105619, -- 2506.21151 Robust Deep Learning for Myocardial Scar Segmentation in Cardiac MRI with N
        105620, -- 2509.12062 Robust Fetal Pose Estimation across Gestational Ages via Cross-Population A
        105723, -- external T2WI-BCMIC: Non-Fat Saturated T2-Weighted Imaging Dataset for Bladder Cance
        105726, -- 2506.18134 Targeted False Positive Synthesis via Detector-guided Adversarial Diffusion
        105791, -- external UniMRG: Refining Medical Semantic Understanding Across Modalities via LLM-O
        105831, -- 2504.21771 WASABI: A Metric for Evaluating Morphometric Plausibility of Synthetic Brai
        105939, -- 2607.05850 Breaking Spurious Correlations via Generative Randomization and Cross-Varia
        106176, -- 2603.18534 Data-efficient pre-training by scaling synthetic megadocs
        106356, -- 2510.20449 LM-mixup: Text Data Augmentation via Language Model based Mixup
        106389, -- 2604.01430 Improving Latent Generalization Using Test-time Compute
        106445, -- 2601.21551 Note2Chat: Improving LLMs for Multi-Turn Clinical History Taking Using Medi
        106540, -- 2511.08455 Bot Meets Shortcut: How Can LLMs Aid in Handling Unknown Invariance OOD Sce
        106660, -- 2512.12964 BLADE: A Behavior-Level Data Augmentation Framework with Dual Fusion Modeli
        106819, -- 2511.08967 AuthSig: Safeguarding Scanned Signatures Against Unauthorized Reuse in Pape
        106827, -- 2601.14258 SOSControl: Enhancing Human Motion Generation Through Saliency-Aware Symbol
        107069, -- 2508.15791 InteChar: A Unified Oracle Bone Character List for Ancient Chinese Language
        107124, -- 2601.07139 AdaField: Generalizable Surface Pressure Modeling with Physics-Informed Pre
        107254, -- 2603.16662 Spectral Property-Driven Data Augmentation for Hyperspectral Single-Source
        107292, -- 2604.08550 Unbiased Rectification for Sequential Recommender Systems Under Fake Orders
        107340, -- 2506.14418 Compositional Attribute Imbalance in Vision Datasets
        107473, -- 2505.24592 A Flat Minima Perspective on Understanding Augmentations and Model Robustne
        107515, -- 2511.07051 Improving Deepfake Detection with Reinforcement Learning-Based Adaptive Dat
        107548, -- 2508.03692 LiDARCrafter: Dynamic 4D World Modeling from LiDAR Sequences
        107614, -- 2511.12573 Mitigating Length Bias in RLHF Through a Causal Lens
        107827, -- 2511.10481 Panda: Test-Time Adaptation with Negative Data Augmentation
        107875, -- 2511.12301 Rethinking Bias in Generative Data Augmentation for Medical AI: A Frequency
        108057, -- 2508.11695 RefAdGen: High-Fidelity Advertising Image Generation
        108134, -- 2511.09909 Simulating Distribution Dynamics: Liquid Temporal Feature Evolution for Sin
        108172, -- 2508.01766 VPN: Visual Prompt Navigation
        108322, -- 2511.14396 Continuous Vision-Language-Action Co-Learning with Semantic-Physical Alignm
        108364, -- 2511.12547 HiGFA: Hierarchical Guidance for Fine-grained Data Augmentation with Diffus
        108400, -- 2511.12075 Treatment Stitching with Schrödinger Bridge for Enhancing Offline Reinforce
        108423, -- 2511.12151 FIA-Edit: Frequency-Interactive Attention for Efficient and High-Fidelity I
        108495, -- 2511.20997 FANoise: Singular Value-Adaptive Noise Modulation for Robust Multimodal Rep
        108510, -- 2512.19024 IndoorUAV: Benchmarking Vision-Language UAV Navigation in Continuous Indoor
        108525, -- 2411.15206 Conditional Distribution Learning for Graph Classification
        108839, -- 2607.13927 Cyclone: Diffusion Model for Cycle-Consistent Weather Editing from Unpaired
        109154, -- 2608.11951 TailBooster: A Dual-Layer Generative Framework for Extreme Value Augmentati
        109212, -- 2101.12491 Efficient-CapsNet: Capsule Network with Self-Attention Routing
        109213, -- 2001.08856 Stochastic Optimization of Plain Convolutional Neural Networks with Simple
        109683, -- external Asymmetric cross-modal attention network with multimodal augmented mixup fo
        109980, -- 2511.18934 Skeletons Matter: Dynamic Data Augmentation for Text-to-Query
        110035, -- external A Comprehensive Literary Chinese Reading Comprehension Dataset with an Evid
        110064, -- external DASA-Trans-STM: Adaptive Efficient Transformer for Short Text Matching usin
        110075, -- external Co-Evolving LLMs and Embedding Models via Density-Guided Preference Optimiz
        110106, -- external LLM-Driven Implicit Target Augmentation and Fine-Grained Contextual Modelin
        110251, -- 2508.21083 CoBA: Counterbias Text Augmentation for Mitigating Various Spurious Correla
        110370, -- 2508.14723 Transplant Then Regenerate: A New Paradigm for Text Data Augmentation
        110457, -- 2502.11066 CARMA: Enhanced Compositionality in LLMs via Advanced Regularisation and Mu
        110560, -- 2511.06268 LLM-Driven Completeness and Consistency Evaluation for Cultural Heritage Da
        110650, -- 2602.17366 RPDR: A Round-trip Prediction-Based Data Augmentation Framework for Long-Ta
        110693, -- 2508.20567 KCS: Diversify Multi-hop Question Generation with Knowledge Composition Sam
        110830, -- 2502.19907 Order Doesn’t Matter, But Reasoning Does: Training LLMs with Order-Centric
        110902, -- external Evolving Chinese Spelling Correction with Corrector-Verifier Collaboration
        110920, -- 2505.14272 Data-Efficient Hate Speech Detection via Cross-Lingual Nearest Neighbor Ret
        110937, -- 2508.17057 GRAID: Synthetic Data Generation with Geometric Constraints and Multi-Agent
        111094, -- external Moral Framing in Politics (MFiP): A new resource and models for moral frami
        111219, -- 2509.14677 SpeechMLC: Speech Multi-label Classification
        111228, -- 2506.04711 LLM-based phoneme-to-grapheme for phoneme-based speech recognition
        111329, -- 2505.14561 SSPS: Self-Supervised Positive Sampling for Robust Self-Supervised Speaker
        111380, -- 2506.09315 Alzheimer’s Dementia Detection Using Perplexity from Paired Large Language
        111459, -- 2505.24446 Pseudo Labels-based Neural Speech Enhancement for the AVSR Task in the MISP
        111517, -- external Dysarthric Speech Recognition Using Curriculum Learning and Multi-stream Ar
        111611, -- external Data Augmentation using Speech Synthesis for Speaker-Independent Dysarthria
        111612, -- 2508.05102 Fairness in Dysarthric Speech Synthesis: Understanding Intrinsic Bias in Dy
        111618, -- 2507.03641 Improving Low-Resource Dialect Classification Using Retrieval-based Voice C
        111627, -- external On Enhancing the Performance of Children's ASR Task in Limited Data Scenari
        111706, -- external Pathology-Aware Speech Encoding and Data Augmentation for Dysarthric Speech
        111709, -- external Fine-tuning Parakeet-TDT for Dysarthric Speech Recognition in the Speech Ac
        111734, -- external EmbedAug: An Augmentation Scheme for End-to-End Automatic Speech Recognitio
        111816, -- 2506.14973 Thinking in Directivity: Speech Large Language Model for Multi-Talker Direc
        111924, -- external Extending the Fongbe to French Speech Translation Corpus: resources, models
        111945, -- 2505.22133 Developing a Top-tier Framework in Naturalistic Conditions Challenge for Ca
        111999, -- 2509.01399 CabinSep: IR-Augmented Mask-Based MVDR for Real-Time In-car Speech Separati
        112017, -- external Bidirectional Spoken-Written Text Conversion with Large Language Models
        112140, -- external A Simple-Yet-Effective Data Augmentation Method for Speaker Identification
        112416, -- 2311.17325 Alternate Diverse Teaching for Semi-supervised Medical Image Segmentation
        112556, -- 2407.02286 Rethinking Data Augmentation for Robust LiDAR Semantic Segmentation in Adve
        112624, -- 2311.16445 CLAP: Isolating Content from Style through Contrastive Learning with Augmen
        112666, -- 2411.02149 Improving Domain Generalization in Self-Supervised Monocular Depth Estimati
        112694, -- 2409.10473 MacDiff: Unified Skeleton Modeling with Masked Conditional Diffusion
        112707, -- 2409.04820 FreeAugment: Data Augmentation Search Across All Degrees of Freedom
        112788, -- 2409.14101 PoseAugment: Generative Human Pose Data Augmentation with Physical Plausibi
        112808, -- 2408.07486 OMR: Occlusion-Aware Memory-Based Refinement for Video Lane Detection
        113083, -- 2312.04763 Enhancing Recipe Retrieval with Foundation Models: A Data Augmentation Pers
        113316, -- 2311.10845 Domain Generalization of 3D Object Detection by Density-Resampling
        113347, -- 2409.06290 EntAugment: Entropy-Driven Adaptive Data Augmentation Framework for Image C
        113409, -- 2407.03886 DSMix: Distortion-Induced Saliency Map Based Pre-training for No-Reference
        113551, -- 2409.07307 Data Augmentation via Latent Diffusion for Saliency Prediction
        113567, -- external Ex2Eg-MAE: A Framework for Adaptation of Exocentric Video Masked Autoencode
        113586, -- 2407.10052 Augmented Neural Fine-tuning for Efficient Backdoor Purification
        113681, -- external Benchmarking the Robustness of Cross-view Geo-localization Models
        113684, -- 2407.15328 Iterative Ensemble Training with Anti-Gradient Control for Mitigating Memor
        113996, -- 2608.24263 Real-World Knowledge-Guided Change Data Synthesis for Remote Sensing
        114276, -- 2601.01762 AlignDrive: Aligned Lateral-Longitudinal Planning for End-to-End Autonomous
        114315, -- 2403.08979 7T MRI Synthesization from 3T Acquisitions
        114352, -- external Adapting Pre-trained Generative Model to Medical Image for Data Augmentatio
        114365, -- external Algorithmic Fairness in Lesion Classification by Mitigating Class Imbalance
        114416, -- external Cache-Driven Spatial Test-Time Adaptation for Cross-Modality Medical Image
        114424, -- 2407.08648 CAR-MFL: Cross-Modal Augmentation by Retrieval for Multimodal Federated Lea
        114461, -- 2407.14426 Controllable and Efficient Multi-Class Pathology Nuclei Data Augmentation u
        114484, -- 2602.03555 Cut to the Mix: Simple Data Augmentation Outperforms Elaborate Ones in Limi
        114486, -- external Data Augmentation with Multi-armed Bandit on Image Deformations Improves Fl
        114487, -- 2407.13896 Data-Algorithm-Architecture Co-Optimization for Fair Neural Networks on Ski
        114492, -- external Death by Retrospective Undersampling - Caveats and Solutions for Learning-B
        114846, -- 2407.05428 Diffusion as Sound Propagation: Physics-inspired Model for Ultrasound Image
        114859, -- external Diversified and Structure-realistic Fundus Image Synthesis for Diabetic Ret
        114889, -- 2403.11050 Endora: Video Generation Models as Endoscopy Simulators
        114901, -- external Enhancing New Multiple Sclerosis Lesion Segmentation via Self-supervised Pr
        114926, -- 2311.13717 Feature Extraction for Generative Medical Imaging Evaluation: New Evidence
        114968, -- 2311.12316 Generating Progressive Images from Pathological Transitions via Diffusion M
        115007, -- external IHRRB-DINO: Identifying High-Risk Regions of Breast Masses in Mammogram Ima
        115052, -- 2404.07091 LaTiM: Longitudinal representation learning in continuous-time models to pr
        115105, -- 2409.04768 Medical Image Segmentation via Single-Source Domain Generalization with Ran
        115136, -- 2403.11689 MoreStyle: Relax Low-frequency Constraint of Fourier-based Image Reconstruc
        115279, -- 2407.02900 Self-supervised Vision Transformer are Scalable Generative Models for Domai
        115286, -- external SHAN: Shape Guided Network for Thyroid Nodule Ultrasound Cross-Domain Segme
        115312, -- external Spatio-temporal Contrast Network for Data-efficient Learning of Coronary Ar
        115337, -- 2404.16421 SynCellFactory: Generative Data Augmentation for Cell Tracking
        115378, -- 2408.03035 Training-Free Condition Video Diffusion Models for single frame Spatial-Sem
        115389, -- 2503.14966 Ultrasound Image-to-Video Synthesis via Latent Dynamic Diffusion Models
        115390, -- external Uncertainty-aware Diffusion-based Adversarial Attack for Realistic Colonosc
        115391, -- external Uncertainty-aware meta-weighted optimization framework for domain-generaliz
        115413, -- external VideoCutMix: Temporal Segmentation of Surgical Videos in Scarce Data Scenar
        115486, -- 2405.14881 DiffuseMix: Label-Preserving Data Augmentation with Diffusion Models
        115490, -- external Bi-level Learning of Task-Specific Decoders for Joint Registration and One-
        115642, -- 2403.19600 Enhance Image Classification via Inter-Class Image Mixup with Diffusion Mod
        115682, -- 2403.04258 Depth-aware Test-Time Training for Zero-shot Video Object Segmentation
        115860, -- 2403.10519 Frozen Feature Augmentation for Few-Shot Image Classification
        115865, -- 2403.10073 Revisiting Adversarial Training Under Long-Tailed Distributions
        115946, -- 2405.05256 THRONE: An Object-based Hallucination Benchmark for the Free-form Generatio
        115958, -- 2402.18146 3DSFLabelling: Boosting 3D Scene Flow Estimation by Pseudo Auto-labelling
        116168, -- 2403.06676 CAM Back Again: Large Kernel CNNs from a Weakly Supervised Object Localizat
        116218, -- 2403.06758 EarthLoc: Astronaut Photography Localization by Indexing Earth from Space
        116271, -- 2404.04960 PairAug: What Can Augmented Image-Text Pairs Do for Radiology?
        116275, -- 2312.13746 Video Recognition in Portrait Mode
        116317, -- 2403.13304 DetDiffusion: Synergizing Generative and Perceptive Models for Enhanced Dat
        116405, -- external SNIDA: Unlocking Few-Shot Object Detection with Non-linear Semantic Decoupl
        116418, -- 2402.17562 An Empirical Study of the Generalization Ability of Lidar 3D Object Detecto
        116420, -- external Generating Handwritten Mathematical Expressions From Symbol Graphs: An End-
        116584, -- 2405.15225 Unbiased Faster R-CNN for Single-source Domain Generalized Object Detection
        116657, -- external Domain Gap Embeddings for Generative Dataset Augmentation
        116666, -- 2403.04700 Delving into the Trajectory Long-tail Distribution for Muti-object Tracking
        116699, -- 2403.15194 Your Image is My Video: Reshaping the Receptive Field via Image-To-Video Di
        116749, -- 2403.01944 Fourier-basis Functions to Bridge Augmentation Gap: Rethinking Frequency Au
        116758, -- 2403.18092 OCAI: Improving Optical Flow Estimation by Occlusion and Consistency Aware
        116849, -- external Logarithmic Lenses: Exploring Log RGB Data for Image Classification
        116942, -- 2312.00598 Learning from One Continuous Video Stream
        117003, -- external Self-Supervised Representation Learning from Arbitrary Scenarios
        117086, -- 2402.18133 Classes Are Not Equal: An Empirical Study on Image Recognition Fairness
        117116, -- 2403.16605 SatSynth: Augmenting Image-Mask Pairs through Diffusion Models for Aerial S
        117154, -- external Exact Fusion via Feature Distribution Matching for Few-shot Image Generatio
        117158, -- 2402.18206 Balancing Act: Distribution-Guided Debiasing in Diffusion Models
        117270, -- external Structure-grounded Training Strategies Aid Generalization in Stereo Matchin
        117342, -- 2603.09681 Improving 3D Foot Motion Reconstruction in Markerless Monocular Human Motio
        117411, -- 2606.19938 Triangular Consistency as a Universal Constraint for Learning Optical Flow
        117520, -- 2607.07187 EditVerse3D: High-Quality 3D Object Editing with Region-Aware Learning
        117570, -- 2509.21263 Towards Geometry-Grounded Dense Semantic Matching with VGGT Priors
        117739, -- 2607.23096 SHReg: Strictly Rotation-Equivariant Point Cloud Registration via Spherical
        117761, -- 2607.15806 HybridSim: A Physics–Learning Hybrid Digital Twin for mmWave Human Sensing
        117771, -- 2606.08336 Synesthesia via Direct Latent Augmentation: Bypassing the Decode-Encode Loo
        118032, -- 2511.21256 LaGen: Towards Autoregressive LiDAR Scene Generation
        118048, -- 2607.19036 CoGoal3D: Collaborative 3D Object Detection with 3D-Aware Fusion and Refine
        118571, -- external From Noise to Events: Conditional Diffusion for Event Data Augmentation
        118861, -- 2608.04394 Free-Lunch Augmentation by Revisiting Diffusion-Based Data Generation for C
        119010, -- 2607.10841 Align and Segment: Unsupervised Learning for Building Segmentation From Mis
        119063, -- 2607.02718 Diagnosing Aerial-View Object Detectors with Foundational Image Generative
        119068, -- external Making Partial-Label Datasets Easier: A Simple Yet Highly Effective Data Au
        119186, -- 2606.31088 Towards Flexible, Natural, Efficient Interaction for Conversational Talking
        119192, -- 2606.20110 FrozenDrive: Zero-Shot Text-Guided Driving Scene Generation and Data Augmen
        119460, -- external LogFA: Efficient Feature-Space Data Augmentation for Egocentric Temporal Ac
        119469, -- 2607.01743 InterCMDM: Block-Causal Diffusion for Autoregressive Human Interaction Gene
        119738, -- 2212.06244 PathFusion: Path-Consistent Lidar-Camera Deep Feature Fusion
        119765, -- 2311.13152 Test-Time Augmentation for 3D Point Cloud Classification and Segmentation
        119778, -- 2312.14474 MonoLSS: Learnable Sample Selection For Monocular 3D Detection
        119847, -- external Gain from Neighbors: Boosting Model Robustness in the Wild via Adversarial
        119883, -- external Improving the Training of Data-Efficient GANs via Quality Aware Dynamic Dis
        119905, -- external BWFormer: Building Wireframe Reconstruction from Airborne LiDAR Point Cloud
        119913, -- external ADD: Attribution-Driven Data Augmentation Framework for Boosting Image Supe
        119953, -- external SEC-Prompt:SEmantic Complementary Prompting for Few-Shot Class-Incremental
        119964, -- external Adversarial Domain Prompt Tuning and Generation for Single Domain Generaliz
        120046, -- 2408.06047 BooW-VTON: Boosting In-the-Wild Virtual Try-On via Mask-Free Pseudo Data Tr
        120197, -- 2507.02687 APT: Adaptive Personalized Training for Diffusion Models with Limited Data
        120365, -- external MODA: Motion-Drift Augmentation for Inertial Human Motion Analysis
        120427, -- 2506.11036 Human-centered Interactive Learning via MLLMs for Text-to-Image Person Re-i
        120591, -- external Chat-based Person Retrieval via Dialogue-Refined Cross-Modal Alignment
        120597, -- external iG-6DoF: Model-free 6DoF Pose Estimation for Unseen Object via Iterative 3D
        120817, -- external FBTA: Enabling Single-GPU End-to-End Gigapixel WSI Classification with Feat
        120858, -- external OntoAug: Rethinking Generative Data Augmentation via Ontology Guidance
        121118, -- external Hyperbolic Defect Feature Synthesis for Few-Shot Defect Classification
        121285, -- external MatchMask: Mask-Centric Generative Data Augmentation for Label-Scarce Seman
        121318, -- 2604.18107 Test-Time Perturbation Tuning with Delayed Feedback for Vision-Language-Act
        121430, -- external LiDAR-to-4DRadar Diffusion Bridge via Cross-Modal Alignment and Translation
        121553, -- external Generalizable Co-Salient Object Detection via Mixed Content-Style Modulatio
        121723, -- external COPE: Consistent Occlusion and Prompt Enhancement Network for Occluded Pers
        121869, -- external Efficient Weighted Sampling via Score-based Generative Models
        122727, -- 2610.06184 Arm-wise Compositional Generalization in Dual-Arm Vision-Language-Action Mo
        123217, -- 2308.12113 Advancements in Point Cloud Data Augmentation for Deep Learning: A Survey
        123355, -- 2604.19196 Benchmarking Vision Foundation Models for Domain-Generalizable Face Anti-Sp
        124118, -- 1907.07484 Benchmarking Robustness in Object Detection: Autonomous Driving when Winter
        124225, -- external LOCO: Local Light-Aware Object Compositing with Spatially Varying Illuminat
        124393, -- external HELICS: Biobank-scale Conditional Synthetic Genome Generation via Latent Fl
        124394, -- external Target-Aware Nuisance Shaping for Object Detection
        124495, -- 2610.09048 Towards Financial World Modeling
        125208, -- 2606.06345 Boosting Brain-to-Image Decoding with TRIBE v2 Data Augmentation
        125672, -- external Return to Basics: Very Simple Graph Contrastive Learning via Noise Cancella
        125856, -- external WorldComposer: Generative High-Fidelity Simulation with Digital Cousins for
        126360, -- external Mixture of Attribute-Aware Attention Experts for Fine-grained E-Commerce Co
        126362, -- external FracTS: Hierarchical and Autoregressive Time Series Generation
        126380, -- external TreemapMix: Dirichlet-Controlled Multi-Image Augmentation for Probability a
        126404, -- external Rethinking CT Synthesis through Semantics-Structure Alignment
        126717, -- external MCAS: Signal-Processing-Based Multi-View Contrastive Learning for Acoustic
        127372, -- external MIRAGE: Duality-Inspired MILP Augmentation for Representation Learning
        127444, -- 2605.15306 How Data Augmentation Shapes Neural Representations
        127624, -- external Scaling Causal Reasoning with Increasingly Complex Causal Simulators
        127767, -- external Dialect ASR based on Multi-View Pseudo-Parallel Augmentation and Noise-Robu
        127851, -- external Skipping Domain Shifts: Domain Memory Retention Enhanced Hyperspectral Sing
        128098, -- 2607.04574 A Few Teacher Steps Go a Long Way: Cost-Efficient On-Policy Data Augmentati
        128159, -- 2605.10290 Characterizing the Generalization Error of Random Feature Regression with A
        128192, -- external MASTARS: Multi-Agent Sequential Trajectory Augmentation with Return-Conditi
        128222, -- external Stein Transport for Generative Modeling
        128607, -- 2602.02358 Transfer Learning Through Conditional Quantile Matching
        128689, -- 2602.22586 TabDLM: Free-Form Tabular Data Generation via Joint Numerical–Language Diff
        129194, -- external Winning the Symmetry Lottery: Learning Invariance from Data Augmentations w
        129264, -- 2603.05228 The Geometric Inductive Bias of Grokking: Bypassing Phase Transitions via A
        129474, -- external Beyond Imputation: Mask-Adaptive Conformal Prediction via Tree Embeddings o
        129493, -- 2606.20118 Pose6DAug: Physically Plausible Multi-View Object Swapping for Robot Data A
        129546, -- 2605.04911 Breaking the Quality–Privacy Tradeoff in Tabular Data Generation via In-Con
        130204, -- external VLM$^3$: Vision Language Models Are Native 3D Learners
        130425, -- 2610.04953 EDISCO: Equivariant Discrete Diffusion for Euclidean Combinatorial Optimiza
        130459, -- 2609.37331 OFBD: Object-Focused Background Debiasing for Long-Tailed Learning
        130624, -- external Bridging Diffusion and Autoregression for Flexible Time Series Synthesis
        130730, -- external Causal Gradient Steering: Exposing Shortcut Gradients by Destroying Causal
        130984, -- external Generation-for-Understanding with Structured Action Scripts for Embodied Mu
        131232, -- 2601.19040 OATS: Online Data Augmentation for Time Series Foundation Models
        131358, -- 2608.25710 Difficulty-Aware Sample Allocation for Adaptive Data Augmentation in Semant
        131952  -- 2611.07613 Towards Real-Time Full-Waveform LiDAR Transformers via Intensity-Guided Tok
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
        7110, -- 2111.00396 Efficiently Modeling Long Sequences with Structured State Spaces
        33672, -- 2406.17688 Unified Auto-Encoding with Masked Diffusion
        34297, -- 2407.05862 Bringing Masked Autoencoders Explicit Contrastive Properties for Point Clou
        35319, -- 2407.20372 A Model Generalization Study in Localizing Indoor Cows with COw LOcalizatio
        45109, -- 2502.19642 cMIM: A Contrastive Mutual Information Framework for Unified Generative and
        52062, -- 2507.18565 Deep Learning-Based Age Estimation and Gender Deep Learning-Based Age Estim
        83988, -- 2503.08703 SDTrack: A Baseline for Event-based Tracking via Spiking Neural Networks
        85190, -- 2603.28182 A Closer Look at Cross-Domain Few-Shot Object Detection: Fine-Tuning Matter
        88763, -- 2506.14587 SCISSOR: Mitigating Semantic Bias through Cluster-Aware Siamese Networks fo
        91463, -- 2405.17816 Pursuing Feature Separation based on Neural Collapse for Out-of-Distributio
        91813, -- 2312.03286 Indirect Gradient Matching for Adversarial Robust Distillation
        107663, -- 2512.06811 RMAdapter: Reconstruction-based Multi-Modal Adapter for Vision-Language Mod
        112777, -- external Enhancing Optimization Robustness in 1-bit Neural Networks through Stochast
        117801, -- 2606.11500 FlexiBrain: Resolution-Agnostic Voxel-Level Encoding for Native fMRI
        120695, -- 2605.25012 Learning from Semantic Dictionaries: Discriminative Codebook Contrastive Le
        125567, -- external Noise-Regularized Training for Learned Image Compression
        127065  -- external Uncertainty-Aware Fuzzy Graph Contrastive Learning
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
        1660, -- 1811.11721 CCNet: Criss-Cross Attention for Semantic Segmentation
        2418, -- 1908.05161 Scalable Attentive Sentence-Pair Modeling via Distilled Sentence Embedding
        3086, -- 2002.03932 Pre-training Tasks for Embedding-based Large-scale Retrieval
        4210, -- 2009.12539 Topic-Aware Multi-turn Dialogue Modeling
        4272, -- 2010.02591 Scene Graph Modification Based on Natural Language Commands
        4489, -- 2011.00770 Context-Aware Cross-Attention for Non-Autoregressive Translation
        4729, -- 2012.07162 Mask-Align: Self-Supervised Neural Word Alignment
        4754, -- 2012.09793 SceneFormer: Indoor Scene Generation with Transformers
        5020, -- 2102.05918 Scaling Up Visual and Vision-Language Representation Learning With Noisy Te
        5173, -- 2103.06104 U-Net Transformer: Self and Cross Attention for Medical Image Segmentation
        5291, -- 2103.14899 CrossViT: Cross-Attention Multi-Scale Vision Transformer for Image Classifi
        5352, -- 2104.00680 LoFTR: Detector-Free Local Feature Matching with Transformers
        5454, -- 2104.07012 Sparse Attention with Linear Units
        5519, -- 2104.08771 Cross-Attention is All You Need: Adapting Pretrained Transformers for Machi
        6153, -- 2106.15828 Semantic Segmentation of Periocular Near-Infra-Red Eye Images Under Alcohol
        6419, -- 2108.06152 Conditional DETR for Fast Training Convergence
        6464, -- 2108.09591 Multimodal Breast Lesion Classification Using Cross-Attention Deep Networks
        6642, -- 2109.07043 Attention Is Indeed All You Need: Semantically Attention-Guided Decoding fo
        6903, -- 2110.06306 Fine-grained style control in Transformer-based Text-to-speech Synthesis
        6921, -- 2110.06920 Semantics-aware Attention Improves Neural Machine Translation
        7389, -- 2112.01527 Masked-attention Mask Transformer for Universal Image Segmentation
        7448, -- 2112.04426 Improving language models by retrieving from trillions of tokens
        7577, -- 2112.10752 High-Resolution Image Synthesis with Latent Diffusion Models
        7668, -- 2201.02973 MAXIM: Multi-Axis MLP for Image Processing
        7780, -- 2201.11037 RTNet: Relation Transformer Network for Diabetic Retinopathy Multi-lesion S
        7976, -- 2202.07765 General-purpose, long-context autoregressive modeling with Perceiver AR
        8001, -- 2202.08791 cosFormer: Rethinking Softmax in Attention
        8151, -- 2203.02912 Graph Neural Network Enhanced Language Models for Efficient Multilingual Te
        8269, -- 2203.07852 Block-Recurrent Transformers
        8381, -- 2203.11725 Unsupervised Anomaly Detection in Medical Images with a Memory-augmented Mu
        8734, -- 2204.07496 Improving Passage Retrieval with Zero-Shot Question Generation
        8774, -- 2204.08714 NAFSSR: Stereo Image Super-Resolution Using NAFNet
        8925, -- 2205.01917 CoCa: Contrastive Captioners are Image-Text Foundation Models
        8932, -- 2205.02151 Dual Cross-Attention Learning for Fine-Grained Visual Categorization and Ob
        8975, -- 2205.04437 Activating More Pixels in Image Super-Resolution Transformer
        9075, -- 2205.09965 Few-Shot Font Generation by Learning Fine-Grained Local Styles
        9485, -- 2206.07643 Coarse-to-Fine Vision-Language Pre-training with Fusion in the Backbone
        9548, -- 2206.09818 SSM-DTA: Breaking the Barriers of Data Scarcity in Drug-Target Affinity Pre
        9697, -- 2207.02522 The Role of Complex NLP in Transformers for Text Ranking?
        9727, -- 2207.04044 kMaX-DeepLab: k-means Mask Transformer
        9759, -- 2207.05273 Cross-Architecture Knowledge Distillation
        9847, -- 2207.09966 Temporal and cross-modal attention for audio-visual zero-shot learning
        9922, -- 2207.13820 Cross-Attention of Disentangled Modalities for 3D Human Mesh Recovery with
        9946, -- 2208.00712 Cross Attention Based Style Distribution for Controllable Person Image Synt
        9963, -- 2208.01626 Prompt-to-Prompt Image Editing with Cross Attention Control
        10010, -- 2208.04921 TSRFormer: Table Structure Recognition with Transformers
        10013, -- 2208.05225 How Effective is Byte Pair Encoding for Out-Of-Vocabulary Words in Neural M
        10072, -- 2208.08340 Dual Modality Prompt Tuning for Vision-Language Pre-Trained Model
        10151, -- 2208.12801 VMFormer: End-to-End Video Matting with Transformer
        10359, -- 2209.09735 Relaxed Attention for Transformer Models
        10502, -- 2210.00255 Cascaded Multi-Modal Mixing Transformers for Alzheimer's Disease Classifica
        10682, -- 2210.04885 What the DAAM: Interpreting Stable Diffusion Using Cross Attention
        10697, -- 2210.05261 Once is Enough: A Light-Weight Cross-Attention for Fast Sentence Pair Model
        10739, -- 2210.06044 Multi-Granularity Cross-modal Alignment for Generalized Medical Visual Repr
        10818, -- 2210.07661 CAB: Comprehensive Attention Benchmarking on Long Sequence Modeling
        11267, -- 2211.04346 Cross-Attention is all you need: Real-Time Streaming Transformers for Perso
        11299, -- 2211.05783 Unifying Flow, Stereo and Depth Estimation
        11328, -- 2211.07198 Fcaformer: Forward Cross Attention in Hybrid Vision Transformer
        11374, -- 2211.08553 Hybrid Transformers for Music Source Separation
        11537, -- 2211.12542 CASSPR: Cross Attention Single Scan Place Recognition
        11544, -- 2211.12677 Word-Level Representation From Bytes For Language Modeling
        11876, -- 2212.04493 SDFusion: Multimodal 3D Shape Completion, Reconstruction, and Generation
        11896, -- 2212.05032 Training-Free Structured Diffusion Guidance for Compositional Text-to-Image
        11915, -- 2212.05638 Cross-Modal Learning with 3D Deformable Attention for Action Recognition
        12088, -- 2212.09724 A Retrieve-and-Read Framework for Knowledge Graph Link Prediction
        12191, -- 2212.11613 DDColor: Towards Photo-Realistic Image Colorization via Dual Decoders
        12198, -- 2212.11972 Scalable Adaptive Computation for Iterative Generation
        12325, -- 2301.02364 Object as Query: Lifting any 2D Object Detector to 3D Detection
        12432, -- 2301.07464 CLIPTER: Looking at the Bigger Picture in Scene Text Recognition
        12567, -- 2301.11445 3DShape2VecSet: A 3D Shape Representation for Neural Fields and Generative
        12613, -- 2301.12149 POSTER++: A simpler and stronger facial expression recognition network
        12649, -- 2301.12652 REPLUG: Retrieval-Augmented Black-Box Language Models
        12685, -- 2301.13197 Unlocking Slot Attention by Changing Optimal Transport Costs
        12722, -- 2301.13826 Attend-and-Excite: Attention-Based Semantic Guidance for Text-to-Image Diff
        12847, -- 2302.02318 Contrast with Reconstruct: Contrastive 3D Representation Learning Guided by
        12889, -- 2302.03027 Zero-shot Image-to-Image Translation
        13320, -- 2302.13153 Directed Diffusion: Direct Control of Object Placement through Attention Gu
        13325, -- 2302.13334 Knowledge Restore and Transfer for Multi-label Class-Incremental Learning
        13336, -- 2302.13848 ELITE: Encoding Visual Concepts into Textual Embeddings for Customized Text
        13430, -- 2303.00941 ParaFormer: Parallel Attention Transformer for Efficient Feature Matching
        13479, -- 2303.02153 Unleashing Text-to-Image Diffusion Models for Visual Perception
        13489, -- 2303.02483 FAME-ViL: Multi-Tasking Vision-Language Model for Heterogeneous Fashion Tas
        13559, -- 2303.04249 Where We Are and What We're Looking At: Query Based Worldwide Image Geo-loc
        13578, -- 2303.04761 Video-P2P: Video Editing with Cross-attention Control
        13664, -- 2303.06341 The NPU-ASLP System for Audio-Visual Speech Recognition in MISP 2022 Challe
        13666, -- 2303.06373 Recursive Generalization Transformer for Image Super-Resolution
        13759, -- 2303.08084 Editing Implicit Assumptions in Text-to-Image Diffusion Models
        13829, -- 2303.09429 Data Roaming and Quality Assessment for Composed Image Retrieval
        13836, -- 2303.09535 FateZero: Fusing Attentions for Zero-shot Text-based Video Editing
        13909, -- 2303.10975 VIMI: Vehicle-Infrastructure Multi-view Intermediate Fusion for Camera-base
        13929, -- 2303.11306 Localizing Object-level Shape Variations with Text-to-Image Diffusion Model
        13962, -- 2303.11681 DiffuMask: Synthesizing Images with Pixel-level Annotations for Semantic Se
        13984, -- 2303.12048 Vox-E: Text-guided Voxel Editing of 3D Objects
        14019, -- 2303.12670 Correlational Image Modeling for Self-Supervised Visual Pre-Training
        14079, -- 2303.13731 How Does Attention Work in Vision Transformers? A Visual Analytics Attempt
        14142, -- 2303.14651 You Only Segment Once: Towards Real-Time Panoptic Segmentation
        14202, -- 2303.15649 StyleDiffusion: Prompt-Embedding Inversion for Text-Based Editing
        14480, -- 2304.02556 Detecting and Grounding Multi-Modal Media Manipulation
        14538, -- 2304.03869 Harnessing the Spatial-Temporal Attention of Diffusion Models for High-Fide
        14573, -- 2304.04546 Kinship Representation Learning with Face Componential Relation
        14669, -- 2304.06461 Multi-Mode Online Knowledge Distillation for Self-Supervised Visual Represe
        14683, -- 2304.06718 Segment Everything Everywhere All at Once
        14732, -- 2304.07957 A Question-Answering Approach to Key Value Pair Extraction from Form-like D
        14747, -- 2304.08465 MasaCtrl: Tuning-Free Mutual Self-Attention Control for Consistent Image Sy
        14919, -- 2304.12294 Explicit Correspondence Matching for Generalizable Neural Radiance Fields
        15134, -- 2305.01486 ARBEx: Attentive Feature Extraction with Reliability Balancing for Robust F
        15148, -- 2305.01625 Unlimiformer: Long-Range Transformers with Unlimited Length Input
        15153, -- 2305.01644 Key-Locked Rank One Editing for Text-to-Image Personalization
        15177, -- 2305.02187 CLUSTSEG: Clustering for Universal Segmentation
        15336, -- 2305.04790 MultiModal-GPT: A Vision and Language Model for Dialogue with Humans
        15672, -- 2305.10431 FastComposer: Tuning-Free Multi-Subject Image Generation with Localized Att
        15694, -- 2305.10722 Discffusion: Discriminative Diffusion Models as Few-shot Vision and Languag
        15696, -- 2305.10727 Boost Vision Transformer with GPU-Friendly Sparsity and Quantization
        15709, -- 2305.10874 Swap Attention in Spatiotemporal Diffusions for Text-to-Video Generation
        15873, -- 2305.12689 FIT: Far-reaching Interleaved Transformers
        16268, -- 2305.15719 Efficient Neural Music Generation
        16274, -- 2305.15775 Concept-Centric Transformers: Enhancing Model Interpretability through Obje
        16320, -- 2305.16311 Break-A-Scene: Extracting Multiple Concepts from a Single Image
        16334, -- 2305.16406 Context-aware attention layers coupled with optimal transport domain adapta
        16498, -- 2305.18286 Photoswap: Personalized Subject Swapping in Images
        16621, -- 2305.19327 Cones 2: Customizable Image Synthesis with Multiple Subjects
        16684, -- 2305.20019 Monotonic Location Attention for Length Generalization
        16922, -- 2306.02236 Detector Guidance for Multi-Object Text-to-Image Generation
        16946, -- 2306.02561 LLM-Blender: Ensembling Large Language Models with Pairwise Ranking and Gen
        17190, -- 2306.05427 Grounded Text-to-Image Synthesis with Attention Refocusing
        17406, -- 2306.08276 TryOnDiffusion: A Tale of Two UNets
        17448, -- 2306.08877 Linguistic Binding in Diffusion Models: Enhancing Attribute Correspondence
        17607, -- 2306.11248 Dynamic Perceiver for Efficient Visual Recognition
        17725, -- 2306.13754 Zero-shot spatial layout conditioning for text-to-image diffusion models
        17757, -- 2306.14313 A Closer Look at Geometric Temporal Dynamics for Face Anti-Spoofing
        17765, -- 2306.14544 A-STAR: Test-time Attention Segregation and Retention for Text-to-image Syn
        17877, -- 2306.16894 PFB-Diff: Progressive Feature Blending Diffusion for Text-driven Image Edit
        17903, -- 2306.17203 Diff-Foley: Synchronized Video-to-Audio Synthesis with Latent Diffusion Mod
        18006, -- 2307.01952 SDXL: Improving Latent Diffusion Models for High-Resolution Image Synthesis
        18180, -- 2307.05799 3D Medical Image Segmentation based on multi-scale MPU-Net
        18402, -- 2307.09787 DVPT: Dynamic Visual Prompt Tuning of Large Pre-trained Models for Medical
        18467, -- 2307.10864 Divide & Bind Your Attention for Improved Generative Semantic Nursing
        18606, -- 2307.13254 Conditional Cross Attention Network for Multi-Space Embedding without Entan
        18670, -- 2307.14336 MAMo: Leveraging Memory and Attention for Monocular Video Depth Estimation
        18705, -- 2307.14971 Take-A-Photo: 3D-to-2D Generative Pre-training of Point Cloud Models
        18779, -- 2307.16395 Bridging the Gap: Exploring the Capabilities of Bridge-Architectures for Co
        18902, -- 2308.01904 DETR Doesn't Need Multi-Scale or Locality Design
        19060, -- 2308.04583 LATR: 3D Lane Detection from Monocular Images with Transformer
        19127, -- 2308.05667 2D3D-MATR: 2D-3D Matching Transformer for Detection-free Registration betwe
        19161, -- 2308.06202 Exploring Predicate Visual Context in Detecting Human-Object Interactions
        19200, -- 2308.06721 IP-Adapter: Text Compatible Image Prompt Adapter for Text-to-Image Diffusio
        19234, -- 2308.07228 RestoreFormer++: Towards Real-World Blind Face Restoration from Undegraded
        19384, -- 2308.09294 Self-Calibrated Cross Attention Network for Few-Shot Segmentation
        19391, -- 2308.09314 Retro-FPN: Retrospective Feature Pyramid Network for Point Cloud Semantic S
        19402, -- 2308.09386 DReg-NeRF: Deep Registration for Neural Radiance Fields
        19547, -- 2308.10570 Self-Feedback DETR for Temporal Action Detection
        19606, -- 2308.11206 DiffCloth: Diffusion Based Garment Synthesis and Manipulation via Structura
        19696, -- 2308.12191 Sign Language Translation with Iterative Prototype
        19861, -- 2308.14469 Pixel-Aware Stable Diffusion for Realistic Image Super-resolution and Perso
        19928, -- 2308.15711 Optimizing Factual Accuracy in Text Generation through Dynamic Knowledge Se
        19929, -- 2308.15777 DeFTAN-II: Efficient Multichannel Speech Enhancement with Subgroup Processi
        20031, -- 2309.00827 Few shot font generation via transferring similarity guided global style an
        20083, -- 2309.01692 Mask-Attention-Free Transformer for 3D Instance Segmentation
        20088, -- 2309.01770 StyleAdapter: A Unified Stylized Image Generation Model
        20113, -- 2309.02119 Hierarchical Masked 3D Diffusion Model for Video Outpainting
        20181, -- 2309.03550 Text2Control3D: Controllable 3D Avatar Generation in Neural Radiance Fields
        20264, -- 2309.05098 3D Implicit Transporter for Temporally Consistent Keypoint Discovery
        20274, -- 2309.05239 HAT: Hybrid Attention Transformer for Image Restoration
        20443, -- 2309.07986 Viewpoint Textual Inversion: Discovering Scene Representations and 3D View
        20504, -- 2309.08773 Enhance audio generation controllability through representation similarity
        20740, -- 2309.12302 Text-Guided Vector Graphics Customization
        20805, -- 2309.13042 MosaicFusion: Diffusion Models as Data Augmenters for Large Vocabulary Inst
        20939, -- 2309.15082 RPEFlow: Multimodal Fusion of RGB-PointCloud-Event for Joint Optical Flow a
        20978, -- 2309.15664 Dynamic Prompt Learning: Addressing Cross-Attention Leakage for Text-Based
        21102, -- 2309.17388 Tree Cross Attention
        21115, -- 2310.00031 Text-image Alignment for Diffusion-based Perception
        21150, -- 2310.00426 PixArt-$α$: Fast Training of Diffusion Transformer for Photorealistic Text-
        21207, -- 2310.01018 Controlling Vision-Language Models for Multi-Task Image Restoration
        21216, -- 2310.01107 Ground-A-Video: Zero-shot Grounded Video Editing using Text-to-image Diffus
        21445, -- 2310.03456 Multi-Resolution Audio-Visual Feature Fusion for Temporal Action Localizati
        21675, -- 2310.06008 CoBEVFusion: Cooperative Perception with LiDAR-Camera Bird's-Eye View Fusio
        21743, -- 2310.06838 AutoAD II: The Sequel - Who, When, and What in Movie Audio Description
        21911, -- 2310.08584 Is ImageNet worth 1 video? Learning strong image encoders from 1 long unlab
        22219, -- 2310.12817 2D-3D Interlaced Transformer for Point Cloud Segmentation with Scene-Level
        22400, -- 2310.14926 Reference-based Restoration of Digitized Analog Videotapes
        22846, -- 2311.00353 LatentWarp: Consistent Diffusion Latents for Zero-Shot Video-to-Video Trans
        22932, -- 2311.01811 DiffDub: Person-generic Visual Dubbing Using Inpainting Renderer with Diffu
        23042, -- 2311.04157 A Simple Interpretable Transformer for Fine-Grained Image Classification an
        23321, -- 2311.08403 Instant3D: Instant Text-to-3D Generation
        23546, -- 2311.11697 Cut-and-Paste: Subject-Driven Video Editing with Attention Control
        23925, -- 2311.17126 Reason out Your Layout: Evoking the Layout Master from Large Language Model
        23938, -- 2311.17261 SceneTex: High-Quality Texture Synthesis for Indoor Scenes via Diffusion Pr
        24036, -- 2311.18635 DiffusionAvatars: Deferred Diffusion for High-fidelity 3D Head Avatars
        24105, -- 2312.00372 Event-driven Real-time Retrieval in Web Search
        24125, -- 2312.00662 Nonparametric Variational Regularisation of Pretrained Transformers
        24205, -- 2312.01725 StableVITON: Learning Semantic Correspondence with Latent Diffusion Model f
        24258, -- 2312.02252 StoryGPT-V: Large Language Models as Consistent Story Visualizers
        24305, -- 2312.02919 Fine-grained Controllable Video Generation via Object Appearance and Contex
        24357, -- 2312.03556 Personalized Face Inpainting with Diffusion Models by Parallel Visual Atten
        24430, -- 2312.04364 DemoCaricature: Democratising Caricature Generation with a Rough Sketch
        24590, -- 2312.06354 PortraitBooth: A Versatile Portrait Model for Fast Identity-preserved Perso
        24627, -- 2312.06704 SIFU: Side-view Conditioned Implicit Function for Real-world Usable Clothed
        24673, -- 2312.07315 NVS-Adapter: Plug-and-Play Novel View Synthesis from a Single Image
        24719, -- 2312.07937 BOTH2Hands: Inferring 3D Hands from Both Text Prompts and Body Dynamics
        24748, -- 2312.08568 NViST: In the Wild New View Synthesis from a Single Image with Transformers
        24755, -- 2312.08676 SEF-VC: Speaker Embedding Free Zero-Shot Voice Conversion with Cross Attent
        24768, -- 2312.08866 MCANet: Medical Image Segmentation with Multi-Scale Cross-Axis Attention
        24775, -- 2312.08887 SpeedUpNet: A Plug-and-Play Adapter Network for Accelerating Text-to-Image
        24786, -- 2312.09008 Style Injection in Diffusion: A Training-free Approach for Adapting Large-s
        24816, -- 2312.09256 LIME: Localized Image Editing via Attention Regularization in Diffusion Mod
        24857, -- 2312.10113 Focus on Your Instruction: Fine-grained and Multi-instruction Image Editing
        24870, -- 2312.10217 T-MAE: Temporal Masked Autoencoders for Point Cloud Representation Learning
        24872, -- 2312.10251 Advancing Surgical VQA with Scene Graph Knowledge
        24928, -- 2312.11396 MAG-Edit: Localized Image Editing in Complex Scenarios via Mask-Based Atten
        24968, -- 2312.11897 Text-Conditioned Resampler For Long Form Video Understanding
        24981, -- 2312.12232 Brush Your Text: Synthesize Any Scene Text on Images via Diffusion Model
        25005, -- 2312.12462 Towards an end-to-end artificial intelligence driven global weather forecas
        25018, -- 2312.12635 RealCraft: Attention Control as A Tool for Zero-Shot Consistent Video Editi
        25060, -- 2312.13314 Unlocking Pre-trained Image Backbones for Semantic Image Synthesis
        25075, -- 2312.13691 DreamTuner: Single Image is Enough for Subject-Driven Generation
        25251, -- 2312.16693 I2V-Adapter: A General Image-to-Video Adapter for Diffusion Models
        25357, -- 2401.00536 A Multi-Task, Multi-Modal Approach for Predicting Categorical and Dimension
        25394, -- 2401.01044 Auffusion: Leveraging the Power of Diffusion and Large Language Models for
        25398, -- 2401.01099 Efficient Parallel Audio Generation using Group Masked Language Modeling
        25443, -- 2401.01827 Moonshot: Towards Controllable Video Generation and Editing with Multimodal
        25492, -- 2401.02412 LLM Augmented LLMs: Expanding Capabilities through Composition
        25548, -- 2401.03424 MLCA-AVSR: Multi-Layer Cross Attention Fusion based Audio-Visual Speech Rec
        25640, -- 2401.04868 Real-time and Continuous Turn-taking Prediction Using Voice Activity Projec
        25782, -- 2401.06829 Cross-Attention Watermarking of Large Language Models
        25925, -- 2401.09084 UniVG: Towards UNIfied-modal Video Generation
        26304, -- 2401.14391 Rethinking Patch Dependence for Masked Autoencoders
        26347, -- 2401.15030 On the generalization capacity of neural networks during generic multimodal
        26412, -- 2401.16157 Spatial-Aware Latent Initialization for Controllable Image Generation
        26448, -- 2401.16465 DressCode: Autoregressively Sewing and Generating Garments from Text Guidan
        26773, -- 2402.02518 Unifying Generation and Prediction on Graphs with Latent Graph Diffusion
        26826, -- 2402.03162 Direct-a-Video: Customized Video Generation with User-Directed Camera Movem
        26878, -- 2402.03658 Sentiment-enhanced Graph-based Sarcasm Explanation in Dialogue
        27021, -- 2402.05195 $λ$-ECLIPSE: Multi-Concept Personalized Text-to-Image Diffusion Models by L
        27042, -- 2402.05546 Offline Actor-Critic Reinforcement Learning Scales to Large Models
        27327, -- 2402.09378 MobileSpeech: A Fast and High-Fidelity Framework for Mobile Zero-Shot Text-
        27363, -- 2402.09966 Textual Localization: Decomposing Multi-concept Images for Subject-Driven T
        27434, -- 2402.10717 BioFusionNet: Deep Learning-Based Survival Risk Stratification in ER+ Breas
        27543, -- 2402.11788 MM-SurvNet: Deep Learning-Based Survival Risk Stratification in Breast Canc
        27548, -- 2402.11819 Head-wise Shareable Attention for Large Language Models
        27727, -- 2402.13598 User-LLM: Efficient LLM Contextualization with User Embeddings
        27818, -- 2402.14654 Multi-HMR: Multi-Person Whole-Body Human Mesh Recovery in a Single Shot
        27909, -- 2402.15509 Seamless Human Motion Composition with Blended Positional Encodings
        27979, -- 2402.16617 Long-Context Language Modeling with Parallel Context Encoding
        28076, -- 2402.17678 CAD-SIGNet: CAD Language Inference from Point Clouds using Layer-wise Sketc
        28110, -- 2402.18011 Representing 3D sparse map points and lines for camera relocalization
        28185, -- 2402.19072 TimeXer: Empowering Transformers for Time Series Forecasting with Exogenous
        28207, -- 2402.19422 PEM: Prototype-based Efficient MaskFormer for Image Segmentation
        28239, -- 2403.00437 LoMOE: Localized Multi-Object Editing via Multi-Diffusion
        28241, -- 2403.00483 RealCustom: Narrowing Real Text Word for Real-Time Open-Domain Text-to-Imag
        28291, -- 2403.01108 Face Swap via Diffusion Model
        28325, -- 2403.01487 InfiMM-HD: A Leap Forward in High-Resolution Multimodal Understanding
        28546, -- 2403.04880 An Item is Worth a Prompt: Versatile Image Editing with Disentangled Contro
        28563, -- 2403.05053 PrimeComposer: Faster Progressively Combined Diffusion for Image Compositio
        28570, -- 2403.05139 Improving Diffusion Models for Authentic Virtual Try-on in the Wild
        28625, -- 2403.06135 MACE: Mass Concept Erasure in Diffusion Models
        28644, -- 2403.06381 Enhancing Semantic Fidelity in Text-to-Image Synthesis: Attention Regulatio
        28650, -- 2403.06487 Multilingual Turn-taking Prediction Using Voice Activity Projection
        28669, -- 2403.06801 CT2Rep: Automated Radiology Report Generation for 3D Medical Imaging
        28682, -- 2403.06951 DEADiff: An Efficient Stylization Diffusion Model with Disentangled Represe
        28724, -- 2403.07564 RSBuilding: Towards General Remote Sensing Image Building Extraction and Ch
        28738, -- 2403.07764 Stable-Makeup: When Real-World Makeup Transfer Meets Diffusion Model
        28981, -- 2403.11120 Unifying Feature and Cost Aggregation with Transformers for Semantic and Vi
        29023, -- 2403.11627 LoRA-Composer: Leveraging Low-Rank Adaptation for Multi-Concept Customizati
        29035, -- 2403.11781 Infinite-ID: Identity-preserved Personalization via ID-semantics Decoupling
        29096, -- 2403.12468 CrossTune: Black-Box Few-Shot Classification with Label Enhancement
        29134, -- 2403.12943 Vid2Robot: End-to-end Video-conditioned Policy Learning with Cross-Attentio
        29190, -- 2403.13524 Compress3D: a Compressed Latent Space for 3D Generation from a Single Image
        29197, -- 2403.13570 Portrait4D-v2: Pseudo Multi-View Data Creates Better 4D Head Synthesizer
        29198, -- 2403.13589 ReGround: Improving Textual and Spatial Grounding at No Cost
        29302, -- 2403.14828 Multimodal-Conditioned Latent Diffusion Models for Fashion Image Editing
        29315, -- 2403.15059 MM-Diff: High-Fidelity Image Personalization via Multi-Modal Condition Inte
        29477, -- 2403.17712 Invisible Gas Detection: An RGB-Thermal Cross Attention Network and A New B
        29549, -- 2403.18551 Attention Calibration for Disentangled Text-to-Image Personalization
        29767, -- 2404.01089 Texture-Preserving Diffusion Models for High-Fidelity Virtual Try-On
        29790, -- 2404.01294 CosmicMan: A Text-to-Image Foundation Model for Humans
        29848, -- 2404.02022 Improving Retrieval Augmented Open-Domain Question-Answering with Vectorize
        29888, -- 2404.02747 Faster Diffusion via Temporal Attention Decomposition
        29901, -- 2404.02883 On the Scalability of Diffusion-based Text-to-Image Generation
        30030, -- 2404.04650 InitNO: Boosting Text-to-Image Diffusion Models via Initial Noise Optimizat
        30036, -- 2404.04828 Strictly-ID-Preserved and Controllable Accessory Advertising Image Generati
        30068, -- 2404.05384 Rethinking the Spatial Inconsistency in Classifier-Free Diffusion Guidance
        30232, -- 2404.07821 Sparse Laneformer
        30333, -- 2404.09158 StreakNet-Arch: An Anti-scattering Network-based Architecture for Underwate
        30336, -- 2404.09204 TextHawk: Exploring Efficient Fine-Grained Perception of Multimodal Large L
        30487, -- 2404.11824 TextCenGen: Attention-Guided Text-Centric Background Adaptation for Text-to
        30565, -- 2404.12628 Efficient infusion of self-supervised representations in Automatic Speech R
        30621, -- 2404.13679 GScream: Learning 3D Geometry and Feature Consistent Gaussian Splatting for
        30629, -- 2404.13873 Texture, Shape and Order Matter: A New Transformer Design for Sequential De
        30630, -- 2404.13899 Towards Better Text-to-Image Generation Alignment via Attention Modulation
        30646, -- 2404.14239 MultiBooth: Towards Generating All Your Concepts in an Image from Text
        30653, -- 2404.14381 TAVGBench: Benchmarking Text to Audible-Video Generation
        30716, -- 2404.15420 XC-Cache: Cross-Attending to Cached Context for Efficient LLM Inference
        30925, -- 2404.19427 InstantFamily: Masked Attention for Zero-shot Multi-ID Image Generation
        31150, -- 2405.05254 You Only Cache Once: Decoder-Decoder Architectures for Language Models
        31169, -- 2405.05806 MasterWeaver: Taming Editability and Face Identity for Personalized Text-to
        31226, -- 2405.07364 BoQ: A Place is Worth a Bag of Learnable Queries
        31274, -- 2405.08246 Compositional Text-to-Image Generation with Dense Blob Representations
        31483, -- 2405.12978 Personalized Residuals for Concept-Driven Text-to-Image Generation
        31607, -- 2405.14701 DreamText: High Fidelity Scene Text Synthesis
        31767, -- 2405.16444 CacheBlend: Fast Large Language Model Serving for RAG with Cached Knowledge
        31783, -- 2405.16635 Compressing Lengthy Context With UltraGist
        31845, -- 2405.17401 RB-Modulation: Training-Free Personalization of Diffusion Models using Stoc
        31892, -- 2405.17927 The Evolution of Multimodal Model Architectures
        31896, -- 2405.17965 AttenCraft: Attention-guided Disentanglement of Multiple Concepts for Text-
        31901, -- 2405.17995 DMT-JEPA: Discriminative Masked Targets for Joint-Embedding Predictive Arch
        31966, -- 2405.18669 Zipper: A Multi-Tower Decoder Architecture for Fusing Modalities
        32234, -- 2406.01388 AutoStudio: Crafting Consistent Subjects in Multi-turn Interactive Image Ge
        32248, -- 2406.01555 FIRM: Flexible Interactive Reflection reMoval
        32285, -- 2406.02184 GraVITON: Graph based garment warping with attention guided inversion for V
        32294, -- 2406.02345 Progressive Confident Masking Attention Network for Audio-Visual Segmentati
        32315, -- 2406.02539 Parrot: Multilingual Visual Instruction Tuning
        32475, -- 2406.04467 Small-E: Small Language Model with Linear Attention for Efficient Speech Sy
        32514, -- 2406.05000 AttnDreamBooth: Towards Text-Aligned Personalized Text-to-Image Generation
        32691, -- 2406.07209 MS-Diffusion: Multi-subject Zero-shot Image Personalization with Layout Gui
        32847, -- 2406.08907 Dual Attribute-Spatial Relation Alignment for 3D Visual Grounding
        32950, -- 2406.10052 Simul-Whisper: Attention-Guided Streaming Whisper with Truncation Detection
        32952, -- 2406.10082 Whisper-Flamingo: Integrating Visual Features into Whisper for Audio-Visual
        33020, -- 2406.10797 STAR: Scale-wise Text-to-image generation via Auto-Regressive representatio
        33214, -- 2406.12179 The Wisdom of a Crowd of Brains: A Universal Brain Encoder
        33305, -- 2406.13149 High-Fidelity Facial Albedo Estimation via Texture Quantization
        33337, -- 2406.13618 In-Context Former: Lightning-fast Compressing Context for Large Language Mo
        33350, -- 2406.13735 StableSemantics: A Synthetic Language-Vision Dataset of Semantic Representa
        33378, -- 2406.14177 SimulSeamless: FBK at IWSLT 2024 Simultaneous Speech Translation
        33402, -- 2406.14481 Revealing Vision-Language Integration in the Brain with Multimodal Networks
        33517, -- 2406.15752 TacoLM: GaTed Attention Equipped Codec Language Model are Efficient Zero-Sh
        33564, -- 2406.16320 What Do VLMs NOTICE? A Mechanistic Interpretability Pipeline for Gaussian-N
        33683, -- 2406.17758 MotionBooth: Motion-Aware Customized Text-to-Video Generation
        33975, -- 2407.01494 FoleyCrafter: Bring Silent Videos to Life with Lifelike and Synchronized So
        34035, -- 2407.02252 GlyphDraw2: Automatic Generation of Complex Glyph Posters with Diffusion Mo
        34045, -- 2407.02371 OpenVid-1M: A Large-Scale High-Quality Dataset for Text-to-video Generation
        34184, -- 2407.04215 T2IShield: Defending Against Backdoors on Text-to-Image Diffusion Models
        34213, -- 2407.04621 OneRestore: A Universal Restoration Framework for Composite Degradation
        34377, -- 2407.06938 RodinHD: High-Fidelity 3D Avatar Generation with Diffusion Models
        34598, -- 2407.09842 Eliminating Feature Ambiguity for Few-Shot Segmentation
        34606, -- 2407.09919 Arbitrary-Scale Video Super-Resolution with Structural and Textural Priors
        34679, -- 2407.10937 IDOL: Unified Dual-Modal Latent Diffusion for Human-Centric Joint Video-Dep
        34799, -- 2407.12317 Out of Length Text Recognition with Sub-String Matching
        34809, -- 2407.12383 Reliable and Efficient Concept Erasure of Text-to-Image Diffusion Models
        34833, -- 2407.12705 IMAGDressing-v1: Customizable Virtual Dressing
        34838, -- 2407.12753 LookupViT: Compressing visual information to a limited number of tokens
        34960, -- 2407.14177 EVLM: An Efficient Vision-Language Model for Visual Understanding
        35078, -- 2407.15886 CatVTON: Concatenation Is All You Need for Virtual Try-On with Diffusion Mo
        35178, -- 2407.17678 S2-Attention: Hardware-Aware Context Sharding Among Attention Heads
        35429, -- 2408.00458 Reenact Anything: Semantic Video Motion Transfer Using Motion-Textual Inver
        35512, -- 2408.01708 AVESFormer: Efficient Transformer Design for Real-Time Audio-Visual Segment
        35523, -- 2408.02049 3D Single-object Tracking in Point Clouds with High Temporal Variation
        35623, -- 2408.03551 VPOcc: Exploiting Vanishing Point for Monocular 3D Semantic Occupancy Predi
        35869, -- 2408.08189 FancyVideo: Towards Dynamic and Consistent Video Generation via Cross-frame
        35974, -- 2408.10119 Factorized-Dreamer: Training A High-Quality Video Generator with Limited an
        36092, -- 2408.11795 EE-MLLM: A Data-Efficient and Compute-Efficient Multimodal Large Language M
        36135, -- 2408.12340 VTON-HandFit: Virtual Try-on for Arbitrary Hand Pose Guided by Hand Priors
        36224, -- 2408.14023 Video-CCAM: Enhancing Video-Language Understanding with Causal Cross-Attent
        36312, -- 2408.15660 Merging and Splitting Diffusion Paths for Semantically Coherent Panoramas
        36335, -- 2408.15966 More Text, Less Point: Towards 3D Data-Efficient Point-Language Understandi
        36356, -- 2408.16232 Enhancing Conditional Image Generation with Explainable Latent Space Manipu
        36373, -- 2408.16450 What to Preserve and What to Transfer: Faithful, Identity-Preserving Diffus
        36382, -- 2408.16589 CrisperWhisper: Accurate Timestamps on Verbatim Speech Transcriptions
        36444, -- 2409.00313 Training-Free Sketch-Guided Diffusion with Latent Optimization
        36486, -- 2409.01086 DPDEdit: Detail-Preserved Diffusion Models for Multimodal Fashion Image Edi
        36499, -- 2409.01327 SPDiffusion: Semantic Protection Diffusion for Multi-concept Text-to-image
        36578, -- 2409.02727 Pooling And Attention: What Are Effective Designs For LLM-Based Embedding M
        36604, -- 2409.03270 SVP: Style-Enhanced Vivid Portrait Talking Head Diffusion Model
        36619, -- 2409.03514 Blended Latent Diffusion under Attention Control for Real-World Video Editi
        36638, -- 2409.04005 Qihoo-T2X: An Efficient Proxy-Tokenized Diffusion Transformer for Text-to-A
        36670, -- 2409.04847 Rethinking The Training And Evaluation of Rich-Context Layout-to-Image Gene
        36690, -- 2409.05379 PersonaTalk: Bring Attention to Your Persona in Visual Dubbing
        36833, -- 2409.08520 GroundingBooth: Grounding Text-to-Image Customization
        36869, -- 2409.09177 Transformer with Controlled Attention for Synchronous Motion Captioning
        37006, -- 2409.11402 NVLM: Open Frontier-Class Multimodal LLMs
        37077, -- 2409.12576 StoryMaker: Towards Holistic Consistent Characters in Text-to-image Generat
        37310, -- 2409.16706 Pix2Next: Leveraging Vision Foundation Models for RGB to NIR Image Translat
        37316, -- 2409.16850 Robust Scene Change Detection Using Visual Foundation Models and Cross-Atte
        37359, -- 2409.17550 A Simple but Strong Baseline for Sounding Video Generation: Effective Adapt
        37382, -- 2409.17920 Resolving Multi-Condition Confusion for Finetuning-Free Personalized Image
        37455, -- 2409.19111 Fusion is all you need: Face Fusion for Customized Identity-Preserving Imag
        37953, -- 2410.04439 Empowering Backbone Models for Visual Text Generation with Input Granularit
        38110, -- 2410.06244 Story-Adapter: A Training-free Iterative Framework for Long Story Visualiza
        38338, -- 2410.09140 RealEra: Semantic-level Concept Erasure via Neighbor-Concept Mining
        38438, -- 2410.10496 Vision-guided and Mask-enhanced Adaptive Denoising for Prompt-based Image E
        38527, -- 2410.11417 VidCompress: Memory-Enhanced Temporal Compression for Video Understanding i
        38981, -- 2410.16719 Progressive Compositionality In Text-to-Image Generative Models
        39048, -- 2410.17779 ADEM-VL: Adaptive and Embedded Fusion for Efficient Vision-Language Tuning
        39094, -- 2410.18410 FreCaS: Efficient Higher-Resolution Image Generation via Frequency-aware Ca
        39109, -- 2410.18537 Beyond Color and Lines: Zero-Shot Style-Specific Image Variations with Coor
        39151, -- 2410.18977 Pay Attention and Move Better: Harnessing Attention for Interactive Motion
        39173, -- 2410.19318 Two are better than one: Context window extension with multi-grained self-i
        39334, -- 2410.22179 Robust and Unbounded Length Generalization in Autoregressive Transformer-Ba
        39498, -- 2411.00399 StyleTex: Style Image-Guided Texture Generation for 3D Models
        39539, -- 2411.00871 LLaMo: Large Language Model-based Molecular Graph Assistant
        39706, -- 2411.04168 DiMSUM: Diffusion Mamba - A Scalable and Unified Spatial-Frequency Method
        39821, -- 2411.05927 Moving Off-the-Grid: Scene-Grounded Video Representations
        39853, -- 2411.06558 Region-Aware Text-to-Image Generation via Hard Binding and Soft Refinement
        39862, -- 2411.06786 ScaleKD: Strong Vision Transformers Could Be Excellent Teachers
        39868, -- 2411.06971 MapSAM: Adapting Segment Anything Model for Automated Feature Detection in
        39879, -- 2411.07132 Token Merging for Training-Free Semantic Binding in Text-to-Image Synthesis
        39950, -- 2411.08307 PerceiverS: A Multi-Scale Perceiver with Effective Segmentation for Long-Te
        39998, -- 2411.09249 Enhancing Financial Domain Adaptation of Language Models via Model Augmenta
        40023, -- 2411.10033 GSEditPro: 3D Gaussian Splatting Editing with Attention-based Progressive L
        40054, -- 2411.10495 Boundary Attention Constrained Zero-Shot Layout-To-Image Generation
        40314, -- 2411.15034 HeadRouter: A Training-free Image Editing Framework for MM-DiTs by Adaptive
        40339, -- 2411.15252 LocRef-Diffusion:Tuning-Free Layout and Appearance-Guided Generation
        40343, -- 2411.15277 Foundation Cures Personalization: Recovering Facial Personalized Models' Pr
        40367, -- 2411.15542 Hierarchical Cross-Attention Network for Virtual Try-On
        40526, -- 2411.17592 VideoDirector: Precise Video Editing via Text-to-Video Models
        40623, -- 2411.18666 3D Scene Graph Guided Vision-Language Pre-training
        40624, -- 2411.18671 TAPTRv3: Spatial and Temporal Context Foster Robust Tracking of Any Point i
        40648, -- 2411.19050 I Dream My Painting: Connecting MLLMs and Diffusion Models via Prompt Gener
        40675, -- 2411.19390 DreamBlend: Advancing Personalized Fine-tuning of Text-to-Image Diffusion M
        40701, -- 2411.19652 Uniform Attention Maps: Boosting Image Fidelity in Reconstruction and Editi
        40710, -- 2411.19774 PerLA: Perceptive 3D Language Assistant
        40747, -- 2412.00177 LumiNet: Latent Intrinsics Meets Diffusion Models for Indoor Scene Relighti
        40824, -- 2412.01316 Long Video Diffusion Generation with Segmented Cross-Attention and Content-
        40857, -- 2412.01814 COSMOS: Cross-Modality Self-Distillation for Vision Language Pre-training
        40873, -- 2412.01986 HybridMQA: Exploring Geometry-Texture Interactions for Colored Mesh Quality
        40892, -- 2412.02237 Cross-Attention Head Position Patterns Can Align with Human Visual Concepts
        40898, -- 2412.02287 Viewpoint Consistency in 3D Generation via Attention and CLIP Guidance
        40920, -- 2412.02687 SNOOPI: Supercharged One-step Diffusion Distillation with Proper Guidance
        40923, -- 2412.02693 Diffusion-based Visual Anagram as Multi-task Learning
        41061, -- 2412.04380 EmbodiedOcc: Embodied 3D Occupancy Prediction for Vision-based Online Scene
        41098, -- 2412.04591 Aberration Correcting Vision Transformers for High-Fidelity Metalens Imagin
        41110, -- 2412.04715 Addressing Attribute Leakages in Diffusion-based Image Editing without Trai
        41150, -- 2412.05263 Mind the Time: Temporally-Controlled Multi-Event Video Generation
        41154, -- 2412.05275 MotionFlow: Attention-Driven Motion Transfer in Video Diffusion Models
        41263, -- 2412.06849 GL-Fusion: Rethinking the Combination of Graph Neural Network and Large Lan
        41308, -- 2412.07589 DiffSensei: Bridging Multi-Modal LLMs and Diffusion Models for Customized M
        41328, -- 2412.07754 PortraitTalk: Towards Customizable One-Shot Audio-to-Talking Face Generatio
        41524, -- 2412.10028 Mr. DETR: Instructive Multi-Route Training for Detection Transformers
        41539, -- 2412.10292 Prompt-Guided Mask Proposal for Two-Stage Open-Vocabulary Segmentation
        41640, -- 2412.11668 Online Writer Retrieval with Chinese Handwritten Phrases: A Synergistic Tem
        41649, -- 2412.11710 Re-Attentional Controllable Video Diffusion Editing
        41707, -- 2412.12225 DLF: Disentangled-Language-Focused Multimodal Sentiment Analysis
        41709, -- 2412.12242 OmniPrism: Learning Disentangled Visual Concept for Image Generation
        41714, -- 2412.12391 Efficient Scaling of Diffusion Transformers for Text-to-Image Generation
        41755, -- 2412.12906 CATSplat: Context-Aware Transformer with Spatial Guidance for Generalizable
        41805, -- 2412.13486 T$^3$-S2S: Training-free Triplet Tuning for Sketch to Scene Generation
        42120, -- 2412.17808 Dora: Sampling and Benchmarking for 3D Shape Variational Auto-Encoders
        42201, -- 2412.18928 UNIC-Adapter: Unified Image-instruction Adapter with Multi-modal Transforme
        42257, -- 2412.19978 MAKIMA: Tuning-free Multi-Attribute Open-domain Video Editing via Mask-Guid
        42296, -- 2412.20800 VMix: Improving Text-to-Image Diffusion Model with Cross-Attention Mixing C
        42382, -- 2501.00823 Decoupling Knowledge and Reasoning in Transformers: A Modular Architecture
        42423, -- 2501.01347 AdaptVC: High Quality Voice Conversion with Adaptive Learning
        42426, -- 2501.01407 Nested Attention: Semantic-aware Attention Values for Concept Personalizati
        42430, -- 2501.01424 Object-level Visual Prompts for Compositional Image Generation
        42531, -- 2501.03059 Through-The-Mask: Mask-based Motion Trajectories for Image-to-Video Generat
        42604, -- 2501.04304 DGQ: Distribution-Aware Group Quantization for Text-to-Image Diffusion Mode
        42701, -- 2501.05823 PersonaHOI: Effortlessly Improving Personalized Face with Human-Object Inte
        42707, -- 2501.05961 Swin-X2S: Reconstructing 3D Shape from 2D Biplanar X-ray with Swin Transfor
        42721, -- 2501.06187 Multi-subject Open-set Personalization in Video Generation
        42753, -- 2501.06655 Personalized Preference Fine-tuning of Diffusion Models
        42964, -- 2501.10075 Robust Change Captioning in Remote Sensing: SECOND-CC Dataset and MModalCC
        43102, -- 2501.12844 GAMED-Snake: Gradient-aware Adaptive Momentum Evolution Deep Snake Model fo
        43147, -- 2501.13554 One-Prompt-One-Story: Free-Lunch Consistent Text-to-Image Generation Using
        43152, -- 2501.13652 LVPruning: An Effective yet Simple Language-Guided Vision Token Pruning App
        43652, -- 2502.02458 SAISA: Towards Multimodal Large Language Models with Both Training and Infe
        43653, -- 2502.02463 Distribution Transformers: Fast Approximate Bayesian Inference With On-The-
        43766, -- 2502.04320 ConceptAttention: Diffusion Transformers Learn Highly Interpretable Feature
        43903, -- 2502.06049 LM2: Large Memory Models
        43983, -- 2502.06902 Emergence of Episodic Memory in Transformers: Characterizing Changes in Tem
        44030, -- 2502.07531 VidCRAFT3: Camera, Object, and Lighting Control for Image-to-Video Generati
        44035, -- 2502.07590 DSV: Exploiting Dynamic Sparsity to Accelerate Large-Scale Video DiT Traini
        44081, -- 2502.08213 LLM Modules: Knowledge Transfer from a Large to a Small Model using Enhance
        44087, -- 2502.08285 Fully-Geometric Cross-Attention for Point Cloud Registration
        44217, -- 2502.10392 Text-guided Sparse Voxel Pruning for Efficient 3D Visual Grounding
        44612, -- 2502.13995 FantasyID: Face Knowledge Enhanced ID-Preserving Video Generation
        44625, -- 2502.14195 Bridging Text and Vision: A Multi-View Text-Vision Registration Approach fo
        44740, -- 2502.15199 UrbanSAM: Learning Invariance-Inspired Adapters for Segment Anything Models
        44857, -- 2502.16680 AeroReformer: Aerial Referring Transformer for UAV-based Referring Image Se
        44927, -- 2502.17258 VideoGrain: Modulating Space-Time Attention for Multi-grained Video Editing
        44992, -- 2502.18143 LightFC-X: Lightweight Convolutional Tracker for RGB-X Tracking
        45112, -- 2502.19673 SubZero: Composing Subject, Style, and Action via Zero-Shot Personalization
        45136, -- 2502.19937 Image Referenced Sketch Colorization Based on Animation Creation Workflow
        45159, -- 2502.20220 Avat3r: Large Animatable Gaussian Reconstruction Model for High-fidelity 3D
        45340, -- 2503.01634 M-SCAN: A Multistage Framework for Lumbar Spinal Canal Stenosis Grading Usi
        45343, -- 2503.01682 GRNFormer: A Biologically-Guided Framework for Integrating Gene Regulatory
        45680, -- 2503.06307 ACAM-KD: Adaptive and Cooperative Attention Masking for Knowledge Distillat
        45689, -- 2503.06397 Removing Averaging: Personalized Lip-Sync Driven Characters Based on Identi
        45736, -- 2503.06896 CATANet: Efficient Content-Aware Token Aggregation for Lightweight Image Su
        45771, -- 2503.07232 Boosting Diffusion-Based Text Image Super-Resolution Model Towards Generali
        45779, -- 2503.07307 AttenST: A Training-Free Attention-Driven Style Transfer Framework with Pre
        45787, -- 2503.07389 TRCE: Towards Reliable Malicious Concept Erasure in Text-to-Image Diffusion
        45821, -- 2503.07677 PLADIS: Pushing the Limits of Attention in Diffusion Models at Inference Ti
        46017, -- 2503.10080 Bayesian Prompt Flow Learning for Zero-Shot Anomaly Detection
        46080, -- 2503.10634 V2Edit: Versatile Video Diffusion Editor for Videos and 3D Scenes
        46174, -- 2503.11937 Att-Adapter: A Robust and Precise Domain-Specific Multi-Attributes T2I Diff
        46190, -- 2503.12355 Atlas: Multi-Scale Attention Improves Long Context Image Modeling
        46294, -- 2503.13946 Is Discretization Fusion All You Need for Collaborative Perception?
        46353, -- 2503.14505 MusicInfuser: Making Video Diffusion Listen and Dance
        46455, -- 2503.16106 OSLoPrompt: Bridging Low-Supervision Challenges and Open-Set Domain General
        46462, -- 2503.16184 Accurate Scene Text Recognition with Efficient Model Scaling and Cloze Self
        46567, -- 2503.17539 Generating, Fast and Slow: Scalable Parallel Video Generation with Video In
        46607, -- 2503.18073 PanopticSplatting: End-to-End Panoptic Gaussian Splatting
        46629, -- 2503.18430 CQ-DINO: Mitigating Gradient Dilution via Category Queries for Vast Vocabul
        46679, -- 2503.18950 Target-Aware Video Diffusion Models
        46698, -- 2503.19285 No Black Box Anymore: Demystifying Clinical Predictive Modeling with Tempor
        46739, -- 2503.19839 FireEdit: Fine-grained Instruction-based Image Editing via Region-aware Vis
        46791, -- 2503.20429 Latent Beam Diffusion Models for Decoding Image Sequences
        46801, -- 2503.20672 BizGen: Advancing Article-level Visual Text Rendering for Infographics Gene
        46855, -- 2503.21541 LOCATEdit: Graph Laplacian Optimized Cross Attention for Localized Text-Gui
        46953, -- 2503.22698 Fragile Mastery: Are Domain-Specific Trade-Offs Undermining On-Device Langu
        46982, -- 2503.23108 SupertonicTTS: Towards Highly Scalable and Efficient Text-to-Speech System
        47104, -- 2504.00557 Efficient LLaMA-3.2-Vision by Trimming Cross-attended Visual Features
        47116, -- 2504.00784 CellVTA: Enhancing Vision Foundation Models for Accurate Cell Segmentation
        47132, -- 2504.00999 MergeVQ: A Unified Framework for Visual Generation and Representation with
        47268, -- 2504.03135 Hierarchical Modeling for Medical Visual Question Answering with Cross-Atte
        47356, -- 2504.04842 FantasyTalking: Realistic Talking Portrait Generation via Coherent Motion S
        47400, -- 2504.05594 Tuning-Free Image Editing with Fidelity and Editability via Unified Latent
        47443, -- 2504.06752 Compass Control: Multi Object Orientation Control for Text-to-Image Generat
        47449, -- 2504.06895 ColorizeDiffusion v2: Enhancing Reference-based Sketch Colorization Through
        47483, -- 2504.07416 RadZero: Similarity-Based Cross-Attention for Explainable Vision-Language A
        47782, -- 2504.12048 Modular-Cam: Modular Dynamic Camera-view Video Generation with LLM
        47783, -- 2504.12080 DC-SAM: In-Context Segment Anything in Images and Videos via Dual Consisten
        47920, -- 2504.14032 LoftUp: Learning a Coordinate-Based Feature Upsampler for Vision Foundation
        47934, -- 2504.14260 Cross-attention for State-based model RWKV-7
        48327, -- 2505.01079 Improving Editability in Image Generation with Layer-wise Memory
        48328, -- 2505.01104 VSC: Visual Search Compositional Text-to-Image Diffusion Model
        48372, -- 2505.02138 Efficient Multivariate Time Series Forecasting via Calibrated Language Mode
        48489, -- 2505.04512 HunyuanCustom: A Multimodal-Driven Architecture for Customized Video Genera
        48551, -- 2505.05568 Griffin: Towards a Graph-Centric Relational Database Foundation Model
        48694, -- 2505.08665 SkillFormer: Unified Multi-View Video Understanding for Proficiency Estimat
        48890, -- 2505.11739 ZeroTuning: Unlocking the Initial Token's Power to Enhance Large Language M
        48953, -- 2505.12359 STAR: Stage-Wise Attention-Guided Token Reduction for Efficient Large Visio
        49017, -- 2505.12998 A Skull-Adaptive Framework for AI-Based 3D Transcranial Focused Ultrasound
        49099, -- 2505.13856 SuperMapNet for Long-Range and High-Accuracy Vectorized HD Map Construction
        49471, -- 2505.16976 Creatively Upscaling Images with Global-Regional Priors
        49487, -- 2505.17020 CrossLMM: Decoupling Long Video Sequences from LMMs via Dual Cross-Attentio
        49700, -- 2505.19201 DREAM: Drafting with Refined Target Features and Entropy-Adaptive Cross-Att
        49822, -- 2505.20156 HunyuanVideo-Avatar: High-Fidelity Audio-Driven Human Animation for Multipl
        49912, -- 2505.20914 Geometry-Editable and Appearance-Preserving Object Compositon
        49963, -- 2505.21549 Distill CLIP (DCLIP): Enhancing Image-Text Retrieval via Cross-Modal Transf
        50082, -- 2505.23119 TextSR: Diffusion Super-Resolution with Multilingual OCR Guidance
        50145, -- 2505.23734 ZPressor: Bottleneck-Aware Compression for Scalable Feed-Forward 3DGS
        50253, -- 2505.24705 RT-X Net: RGB-Thermal cross attention network for Low-Light Image Enhanceme
        50279, -- 2505.24873 MiniMax-Remover: Taming Bad Noise Helps Video Object Removal
        50380, -- 2506.01365 Attention Is Not Always the Answer: Optimizing Voice Activity Detection wit
        50407, -- 2506.01850 MoDA: Modulation Adapter for Fine-Grained Visual Grounding in Instructional
        50428, -- 2506.02083 LASPA: Language Agnostic Speaker Disentanglement with Prefix-Tuned Cross-At
        50876, -- 2506.08797 HunyuanVideo-HOMA: Generic Human-Object Interaction in Multimodal Driven Hu
        50985, -- 2506.10178 Attention, Please! Revisiting Attentive Probing for Masked Image Modeling
        51015, -- 2506.10568 DreamActor-H1: High-Fidelity Human-Product Demonstration Video Generation v
        51137, -- 2506.13166 GreedyPrune: Retenting Critical Visual Token Set for Large Vision Language
        51153, -- 2506.13465 SA-LUT: Spatial Adaptive 4D Look-Up Table for Photorealistic Style Transfer
        51303, -- 2506.16656 Mesh-Informed Neural Operator : A Transformer Generative Approach
        51306, -- 2506.16784 TextBraTS: Text-Guided Volumetric Brain Tumor Segmentation with Innovative
        51379, -- 2506.18729 MuseControlLite: Multifunctional Music Generation with Lightweight Conditio
        51484, -- 2506.20875 3DGH: 3D Head Generation with Composable Hair and Face
        51573, -- 2506.23121 CRISP-SAM2: SAM2 with Cross-Modal Interaction and Semantic Prompting for Mu
        51606, -- 2507.00505 LLaVA-SP: Enhancing Visual Representation with Visual Spatial Tokens for ML
        51704, -- 2507.04584 S$^2$Edit: Text-Guided Image Editing with Precise Semantic and Spatial Cont
        51948, -- 2507.12956 FantasyPortrait: Enhancing Multi-Character Portrait Animation with Expressi
        52122, -- 2507.23313 The Cow of Rembrandt - Analyzing Artistic Prompt Interpretation in Text-to-
        52156, -- 2508.01151 Personalized Safety Alignment for Text-to-Image Diffusion Models
        52322, -- 2508.08248 StableAvatar: Infinite-Length Audio-Driven Avatar Video Generation
        52596, -- 2509.00578 C-DiffDet+: Fusing Global Scene Context with Generative Denoising for High-
        52723, -- 2509.08519 HuMo: Human-Centric Video Generation via Collaborative Multi-Modal Conditio
        52758, -- 2509.10058 Color Me Correctly: Bridging Perceptual Color Spaces and Text Embeddings fo
        52879, -- 2509.15496 Lynx: Towards High-Fidelity Personalized Video Generation
        52909, -- 2509.18010 Cross-Attention is Half Explanation in Speech-to-Text Models
        52984, -- 2509.22650 RefAM: Attention Magnets for Zero-Shot Referral Segmentation
        52985, -- 2509.22244 FlashEdit: Decoupling Speed, Structure, and Semantics for Precise Image Edi
        53148, -- 2510.01284 Ovi: Twin Backbone Cross-Modal Fusion for Audio-Video Generation
        53195, -- 2510.02410 OpenTSLM: Time-Series Language Models for Reasoning over Multivariate Medic
        53399, -- 2510.07314 GyroSwin: 5D Surrogates for Gyrokinetic Plasma Turbulence Simulations
        53451, -- 2510.07151 ELMUR: External Layer Memory with Update/Rewrite for Long-Horizon RL
        53784, -- 2510.20822 HoloCine: Holistic Generation of Cinematic Multi-Shot Long Video Narratives
        53829, -- 2510.21581 Foley Control: Aligning a Frozen Latent Text-to-Audio Model to Video
        54065, -- 2511.03334 UniAVGen: Unified Audio and Video Generation with Asymmetric Cross-Modal In
        54313, -- 2511.17199 VLA-4D: Embedding 4D Awareness into Vision-Language-Action Models for Spati
        54315, -- 2511.15299 Taming Generative Synthetic Data for X-ray Prohibited Item Detection
        54520, -- 2512.01540 FlashVGGT: Efficient and Scalable Visual Geometry Transformers with Compres
        54686, -- 2512.09824 Composing Concepts from Images and Videos via Concept-prompt Binding
        54702, -- 2512.07222 Pay Less Attention to Function Words for Free Robustness of Vision-Language
        54870, -- 2512.16625 DeContext as Defense: Safe Image Editing in Diffusion Transformers
        54939, -- 2512.19535 CASA: Cross-Attention via Self-Attention for Efficient Vision-Language Fusi
        54955, -- 2512.21332 C2LLM Technical Report: A New Frontier in Code Retrieval via Adaptive Cross
        55013, -- 2512.23541 Act2Goal: From World Model To General Goal-conditioned Policy
        55082, -- 2601.00204 MorphAny3D: Unleashing the Power of Structured Latent in 3D Morphing
        55108, -- 2512.22877 M-ErasureBench: A Comprehensive Multimodal Evaluation Benchmark for Concept
        55110, -- 2601.03233 LTX-2: Efficient Joint Audio-Visual Foundation Model
        55195, -- 2601.04720 Qwen3-VL-Embedding and Qwen3-VL-Reranker: A Unified Framework for State-of-
        55415, -- 2601.11898 RemoteVAR: Autoregressive Visual Modeling for Remote Sensing Change Detecti
        55561, -- 2601.17950 UPLiFT: Efficient Pixel-Dense Feature Upsampling with Local Attenders
        55565, -- 2601.19194 SE-DiCoW: Self-Enrolled Diarization-Conditioned Whisper
        55642, -- 2601.22666 ExpAlign: Expectation-Guided Vision-Language Alignment for Open-Vocabulary
        55673, -- 2602.01801 Fast Autoregressive Video Diffusion and World Models with Temporal Cache Co
        55710, -- 2602.03796 3D-Aware Implicit Motion Control for View-Adaptive Human Video Generation
        56196, -- 2602.14514 Efficient Text-Guided Convolutional Adapter for the Diffusion Model
        56523, -- 2603.05888 PixARMesh: Autoregressive Mesh-Native Single-View Scene Reconstruction
        56578, -- 2603.07066 MedSteer: Counterfactual Endoscopic Synthesis via Training-Free Activation
        56656, -- 2603.12245 One Model, Many Budgets: Elastic Latent Interfaces for Diffusion Transforme
        56796, -- 2603.14152 SK-Adapter: Skeleton-Based Structural Control for Native 3D Generation
        56871, -- 2603.16924 SimulU: Training-free Policy for Long-form Simultaneous Speech-to-Speech Tr
        56892, -- 2603.20192 LumosX: Relate Any Identities with Their Attributes for Personalized Video
        56924, -- 2603.21986 Speed by Simplicity: A Single-Stream Architecture for Fast Audio-Video Gene
        56962, -- 2603.18911 Progressive Training for Explainable Citation-Grounded Dialogue: Reducing H
        56979, -- 2603.22570 CanViT: Toward Active-Vision Foundation Models
        56987, -- 2603.23495 VISion On Request: Enhanced VLLM efficiency with sparse, dynamically select
        57176, -- 2604.02327 Steerable Visual Representations
        57198, -- 2604.01760 T5Gemma-TTS Technical Report
        57231, -- 2604.03231 CoME-VL: Scaling Complementary Multi-Encoder Vision-Language Learning
        57253, -- 2604.01043 ONE-SHOT: Compositional Human-Environment Video Synthesis via Spatial-Decou
        57333, -- 2604.08546 When Numbers Speak: Aligning Textual Numerals and Visual Instances in Text-
        57414, -- 2604.10030 Prompt Relay: Inference-Time Temporal Control for Multi-Event Video Generat
        57525, -- 2604.14125 HiVLA: A Visual-Grounded-Centric Hierarchical Embodied Manipulation System
        57556, -- 2604.16503 Motif-Video 2B: Technical Report
        57864, -- 2605.01229 Attention Sinks in Massively Multilingual Neural Machine Translation:Discov
        57911, -- 2604.22203 Advancing automatic speech recognition using feature fusion with self-super
        57954, -- 2604.21052 StyleVAR: Controllable Image Style Transfer via Visual Autoregressive Model
        58015, -- 2604.18933 Gated Memory Policy
        58062, -- 2604.22826 Shape: A Self-Supervised 3D Geometry Foundation Model for Industrial CAD An
        58159, -- 2604.14591 Prompt-Guided Image Editing with Masked Logit Nudging in Visual Autoregress
        58176, -- 2604.13906 Blind Bitstream-corrupted Video Recovery via Metadata-guided Diffusion Mode
        58253, -- 2604.11854 MVAdapt: Zero-Shot Multi-Vehicle Adaptation for End-to-End Autonomous Drivi
        58402, -- 2603.04759 Stacked from One: Multi-Scale Self-Injection for Context Window Extension
        58467, -- 2604.04576 PR-IQA: Partial-Reference Image Quality Assessment for Diffusion-Based Nove
        58500, -- 2604.04797 Multi-Modal Sensor Fusion using Hybrid Attention for Autonomous Driving
        58535, -- 2604.04972 RCP: Representation Consistency Pruner for Mitigating Distribution Shift in
        58592, -- 2604.02583 FusionBERT: Multi-View Image-3D Retrieval via Cross-Attention Visual Fusion
        58613, -- 2604.01766 FSKD: Monocular Forest Structure Inference via LiDAR-to-RGBI Knowledge Dist
        58717, -- 2604.00086 Hierarchical Pre-Training of Vision Encoders with Large Language Models
        58726, -- 2603.29414 Native-Domain Cross-Attention for Camera-LiDAR Extrinsic Calibration Under
        58789, -- 2603.27500 Streamlined Open-Vocabulary Human-Object Interaction Detection
        58826, -- 2603.26285 PhysVid: Physics Aware Local Conditioning for Generative Video Models
        58844, -- 2603.26515 JAL-Turn: Joint Acoustic-Linguistic Modeling for Real-Time and Robust Turn-
        58970, -- 2603.23308 Curriculum-Driven 3D CT Report Generation via Language-Free Visual Grafting
        59168, -- 2603.19100 LuMamba: Latent Unified Mamba for Electrode Topology-Invariant and Efficien
        59228, -- 2603.17427 ECHO: Towards Emotionally Appropriate and Contextually Aware Interactive He
        59257, -- 2603.16576 REFORGE: Multi-modal Attacks Reveal Vulnerable Concept Unlearning in Image
        59413, -- 2603.13943 Sat-JEPA-Diff: Bridging Self-Supervised Learning and Generative Diffusion f
        59419, -- 2603.13779 AD-Copilot: A Vision-Language Assistant for Industrial Anomaly Detection vi
        59430, -- 2603.13941 Bidirectional Cross-Attention Fusion of High-Res RGB and Low-Res HSI for Mu
        59643, -- 2603.09079 GST-VLA: Structured Gaussian Spatial Tokens for 3D Depth-Aware Vision-Langu
        59647, -- 2603.10210 Delta-K: Boosting Multi-Instance Generation via Cross-Attention Augmentatio
        59669, -- 2603.08483 X-AVDT: Audio-Visual Cross-Attention for Robust Deepfake Detection
        59733, -- 2603.07476 EVLF: Early Vision-Language Fusion for Generative Dataset Distillation
        59775, -- 2603.06386 REACT++: Efficient Cross-Attention for Real-Time Scene Graph Generation
        59822, -- 2603.05845 Cog2Gen3D: Sculpturing 3D Semantic-Geometric Cognition for 3D Generation
        59915, -- 2603.03744 DAGE: Dual-Stream Architecture for Efficient and Fine-Grained Geometry Esti
        59916, -- 2603.03739 PROSPECT: Unified Streaming Vision-Language Navigation via Semantic-Spatia
        60143, -- 2509.23566 Towards Interpretable Visual Decoding with Attention to Brain Representatio
        60168, -- 2602.23783 Diffusion Probe: Generated Image Result Prediction Using CNN Probes
        60222, -- 2602.22949 OpenFS: Multi-Hand-Capable Fingerspelling Recognition with Implicit Signing
        60295, -- 2602.21503 AHAN: Asymmetric Hierarchical Attention Network for Identical Twin Face Ver
        60351, -- 2602.00795 DVLA-RL: Dual-Level Vision-Language Alignment with Reinforcement Learning G
        60400, -- 2602.19870 ApET: Approximation-Error Guided Token Compression for Efficient VLMs
        60555, -- 2602.16188 Deep TPC: Temporal-Prior Conditioning for Time Series Forecasting
        61020, -- 2602.07993 MCIE: Multimodal LLM-Driven Complex Instruction Image Editing with Spatial
        61042, -- 2602.07574 ViCA: Efficient Multimodal LLMs with Vision-Only Cross-Attention
        61101, -- 2602.06452 Exploring Specular Reflection Inconsistency for Generalizable Face Forgery
        61134, -- 2602.06037 Thinking with Geometry: Active Geometry Integration for Spatial Reasoning
        61166, -- 2602.05513 DECO: Decoupled Multimodal Diffusion Transformer for Bimanual Dexterous Man
        61199, -- 2602.05853 RRAttention: Dynamic Block Sparse Attention via Per-Head Round-Robin Shifts
        61205, -- 2602.05590 EgoPoseVR: Spatiotemporal Multi-Modal Reasoning for Egocentric Full-Body Po
        61357, -- 2602.03220 PokeFusion Attention: Enhancing Reference-Free Style-Conditioned Generation
        61531, -- 2602.01306 DeCorStory: Gram-Schmidt Prompt Embedding Decorrelation for Consistent Stor
        61571, -- 2602.00946 ConsensusDrop: Fusing Visual and Cross-Modal Saliency for Efficient Vision
        61590, -- 2602.00839 TransNormal: Dense Visual Semantics for Diffusion-based Transparent Object
        61798, -- 2601.21866 MoHETS: Long-term Time Series Forecasting with Mixture-of-Heterogeneous-Exp
        61920, -- 2601.20891 ATTNSOM: Learning Cross-Isoform Attention for Cytochrome P450 Site-of-Metab
        62092, -- 2601.17586 Stylizing ViT: Anatomy-Preserving Instance Style Transfer for Domain Genera
        62223, -- 2601.15392 GeMM-GAN: A Multimodal Generative Model Conditioned on Histopathology Image
        62326, -- 2512.19546 ActAvatar: Temporally-Aware Precise Action Control for Talking Avatars
        62358, -- 2601.12804 SL-CBM: Enhancing Concept Bottleneck Models with Semantic Locality for Bett
        62379, -- 2601.12530 XRefine: Attention-Guided Keypoint Match Refinement
        62421, -- 2601.11310 Context-Aware Semantic Segmentation via Stage-Wise Attention
        62453, -- 2601.10632 CoMoVi: Co-Generation of 3D Human Motions and Realistic Videos
        62586, -- 2601.08078 Exploiting DINOv3-Based Self-Supervised Features for Robust Few-Shot Medica
        62709, -- 2601.06391 Object-WIPER : Training-Free Object and Associated Effect Removal in Videos
        62884, -- 2601.03665 PhysVideoGenerator: Towards Physically Aware Video Generation via Latent Ph
        62890, -- 2601.03613 PhysicsFormer: An Efficient and Fast Attention-Based Physics Informed Neura
        63057, -- 2601.01461 Bridging the gap: A comparative exploration of Speech-LLM and end-to-end ar
        63219, -- 2512.23537 AnyMS: Bottom-up Attention Decoupling for Layout-guided and Training-free M
        63365, -- 2512.20399 GeoTransolver: Learning Physics on Irregular Domains Using Multi-scale Geom
        63441, -- 2512.22217 VLM-PAR: A Vision Language Model for Pedestrian Attribute Recognition
        63466, -- 2512.18772 In-Context Audio Control of Video Diffusion Transformers
        63500, -- 2512.17851 InfSplign: Inference-Time Spatial Alignment of Text-to-Image Diffusion Mode
        63618, -- 2512.22166 AudioGAN: A Compact and Efficient Framework for Real-Time High-Fidelity Tex
        63636, -- 2512.14856 T5Gemma 2: Seeing, Reading, and Understanding Longer
        63738, -- 2512.12678 β-CLIP: Text-Conditioned Contrastive Learning for Multi-Granular Vision-Lan
        63785, -- 2512.11715 EditMGT: Unleashing Potentials of Masked Generative Transformers in Image E
        63809, -- 2512.10957 SceneMaker: Open-set 3D Scene Generation with Decoupled De-occlusion and Po
        63955, -- 2512.04734 MT-Depth: Multi-task Instance feature analysis for the Depth Completion
        64048, -- 2512.06368 HuPrior3R: Incorporating Human Priors for Better 3D Dynamic Reconstruction
        64149, -- 2512.04085 Unique Lives, Shared World: Learning from Single-Life Videos
        64156, -- 2512.03964 Training for Identity, Inference for Controllability: A Unified Approach to
        64216, -- 2512.02650 Hear What Matters! Text-conditioned Selective Video-to-Audio Generation
        64297, -- 2512.01334 AlignVid: Training-Free Attention Scaling for Semantic Fidelity in Text-Gui
        64438, -- 2511.22167 IMTalker: Efficient Audio-driven Talking Face Generation with Implicit Moti
        64451, -- 2511.21945 AmodalGen3D: Generative Amodal 3D Object Reconstruction from Sparse Unposed
        64494, -- 2511.21024 CameraMaster: Unified Camera Semantic-Parameter Control for Photography Ret
        64633, -- 2511.18810 MergeVLA: Cross-Skill Model Merging Toward a Generalist Vision-Language-Act
        64721, -- 2511.17501 Native 3D Editing with Full Attention
        64739, -- 2511.17185 PostCam: Camera-Controllable Novel-View Video Generation with Query-Shared
        64866, -- 2511.14712 FreeSwim: Revisiting Sliding-Window Attention Mechanisms for Training-Free
        64989, -- 2511.11910 Seeing the Forest and the Trees: Query-Aware Tokenizer for Long-Video Multi
        65020, -- 2511.11239 Beyond Flatlands: Unlocking Spatial Intelligence by Decoupling 3D Reasoning
        65023, -- 2511.11177 Viper-F1: Fast and Fine-Grained Multimodal Understanding with Cross-Modal S
        65124, -- 2511.09090 Diff-V2M: A Hierarchical Conditional Diffusion Model with Explicit Rhythmic
        65409, -- 2511.02986 Scalable Single-Cell Gene Expression Generation with Latent Diffusion Model
        65519, -- 2511.00981 VesSAM: Efficient Multi-Prompting for Segmenting Complex Vessel
        65791, -- 2510.23515 FreeFuse: Multi-Subject LoRA Fusion via Auto Masking at Test Time
        65870, -- 2510.22257 LUNA: Efficient and Topology-Agnostic Foundation Model for EEG Signal Analy
        66252, -- 2510.15530 VO-DP: Semantic-Geometric Adaptive Diffusion Policy for Vision-Only Robotic
        66336, -- 2510.14260 MatchAttention: Matching the Relative Positions for High-Resolution Cross-V
        66413, -- 2510.12974 Scope: Selective Cross-modal Orchestration of Visual Perception Experts
        66559, -- 2510.10560 BitMar: Low-Bit Multimodal Fusion with Episodic Memory for Edge Devices
        66716, -- 2510.08316 Unlocking 3D Affordance Segmentation with 2D Semantic Knowledge
        66885, -- 2510.05828 StereoSync: Spatially-Aware Stereo Audio Generation from Video
        66940, -- 2510.04706 ID-Consistent, Precise Expression Generation with Blendshape-Guided Diffusi
        67017, -- 2509.25622 Layer-wise dynamic rank for compressing large language models
        67043, -- 2510.02912 Don't Just Chase "Highlighted Tokens" in MLLMs: Revisiting Visual Holistic
        67193, -- 2510.00974 JEPA-T: Joint-Embedding Predictive Architecture with Text Fusion for Image
        67216, -- 2510.00726 CroSTAta: Cross-State Transition Attention Transformer for Robotic Manipula
        67227, -- 2510.00621 FAME: Adaptive Functional Attention with Expert Routing for Function-on-Fun
        67293, -- 2509.26455 Stylos: Multi-View 3D Stylization with Single-Forward Gaussian Splatting
        67313, -- 2509.26157 EntroPE: Entropy-Guided Dynamic Patch Encoder for Time Series Forecasting
        67315, -- 2509.26127 EchoGen: Generating Visual Echoes in Any Scene via Feed-Forward Subject-Dri
        67480, -- 2509.24391 UniFlow-Audio: Unified Flow Matching for Audio Generation from Omni-Modalit
        67544, -- 2509.23828 Uni4D-LLM: A Unified SpatioTemporal-Aware VLM for 4D Understanding and Gene
        67637, -- 2509.22950 Twin Peaks: Dual-Head Architecture for Structure-Free Prediction of Protein
        67656, -- 2509.22627 CCNeXt: An Effective Self-Supervised Stereo Depth Estimation Approach
        67756, -- 2509.21670 MORPH: Shape-agnostic PDE Foundation Models
        67793, -- 2509.21164 Mixture of Thoughts: Learning to Aggregate What Experts Think, Not Just Wha
        67824, -- 2509.20891 AIBA: Attention-based Instrument Band Alignment for Text-to-Audio Diffusion
        67936, -- 2510.05106 Rule Encoding and Compliance in Large Language Models: An Information-Theor
        68080, -- 2509.16673 MedCutMix: A Data-Centric Approach to Improve Radiology Vision-Language Pre
        68125, -- 2509.16098 SegDINO3D: 3D Instance Segmentation Empowered by Both Image-Level and Objec
        68166, -- 2509.15874 ENSAM: an efficient foundation model for interactive segmentation of 3D med
        68179, -- 2509.15357 MaskAttn-SDXL: Controllable Region-Level Text-To-Image Generation
        68367, -- 2509.12069 U-Mamba2: Scaling State Space Models for Dental Anatomy Segmentation in CBC
        68431, -- 2509.11084 Length-Aware Rotary Position Embedding for Text-Speech Alignment
        68460, -- 2509.10250 GAMMA: Generalizable Alignment via Multi-task and Manipulation-Augmented Tr
        68495, -- 2509.09429 Semantic Concentration for Self-Supervised Dense Representations Learning
        68579, -- 2509.07526 Competitive Audio-Language Models with Data-Efficient Single-Stage Training
        68655, -- 2509.06068 Home-made Diffusion Model from Scratch to Hatch
        68815, -- 2509.02450 EmoPerso: Enhancing Personality Detection with Self-Supervised Emotion-Awar
        68851, -- 2504.20860 FedMVP: Federated Multimodal Visual Prompt Tuning for Vision-Language Model
        68936, -- 2509.00664 Fusion to Enhance: Fusion Visual Encoder to Enhance Multimodal Language Mod
        69051, -- 2508.20449 A Spatial-Frequency Aware Multi-Scale Fusion Network for Real-Time Deepfake
        69089, -- 2508.19852 Ego-centric Predictive Model Conditioned on Hand Trajectories
        69128, -- 2508.19428 Heterogeneous LLM Methods for Ontology Learning (Few-Shot Prompting, Ensemb
        69167, -- 2508.18701 Attention2Probability: Attention-Driven Terminology Probability Estimation
        69243, -- 2508.17497 Multimodal Representation Learning Conditioned on Semantic Relations
        69292, -- 2508.16930 HunyuanVideo-Foley: Multimodal Diffusion with Representation Alignment for
        69428, -- 2508.14483 Vivid-VR: Distilling Concepts from Text-to-Video Diffusion Transformer for
        69431, -- 2508.14440 MUSE: Multi-Subject Unified Synthesis via Explicit Layout Semantic Expansio
        69438, -- 2508.18235 Sealing The Backdoor: Unlearning Adversarial Text Triggers In Diffusion Mod
        69448, -- 2508.14039 Beyond Simple Edits: Composed Video Retrieval with Dense Modifications
        69567, -- 2508.12415 TiP4GEN: Text to Immersive Panorama 4D Scene Generation
        69610, -- 2508.11565 INFNet: A Task-aware Information Flow Network for Large-Scale Recommendatio
        69699, -- 2508.10264 MRFD: Multi-Region Fusion Decoding with Self-Consistency for Mitigating Hal
        69830, -- 2508.10931 VSF: Simple, Efficient, and Effective Negative Guidance in Few-Step Image G
        69901, -- 2508.07519 Exploring Multimodal Diffusion Transformers for Enhanced Prompt-based Image
        69929, -- 2508.07048 Whisfusion: Parallel ASR Decoding via a Diffusion Transformer
        70469, -- 2508.00945 Optimizing Vision-Language Consistency via Cross-Layer Regional Attention A
        70511, -- 2507.23143 X-NeMo: Expressive Neural Motion Reenactment via Disentangled Latent Attent
        70514, -- 2507.23083 Context-aware Rotary Position Embedding
        70605, -- 2508.06511 DiTalker: A Unified DiT-based Framework for High-Quality and Speaking Style
        70618, -- 2507.21391 Multimodal LLMs as Customized Reward Models for Text-to-Image Generation
        70659, -- 2507.20417 Two Views, One Truth: Spectral and Self-Supervised Features Fusion for Robu
        70809, -- 2507.17853 Detail++: Training-Free Detail Enhancer for Text-to-Image Diffusion Models
        70839, -- 2507.17312 CasP: Improving Semi-Dense Feature Matching Pipeline Leveraging Cascaded Co
        70871, -- 2507.16624 A2Mamba: Attention-augmented State Space Models for Visual Recognition
        70948, -- 2507.15272 A2TTS: TTS for Low Resource Indian Languages
        71076, -- 2507.12236 Generate to Ground: Multimodal Text Conditioning Boosts Phrase Grounding in
        71146, -- 2507.10293 Show and Polish: Reference-Guided Identity Preservation in Face Video Resto
        71166, -- 2507.09904 ASTAR-NTU solution to AudioMOS Challenge 2025 Track1
        71193, -- 2507.09574 MENTOR: Efficient Multimodal-Conditioned Tuning for Autoregressive Vision G
        71433, -- 2507.03905 EchoMimicV3: 1.3B Parameters are All You Need for Unified Multi-Modal and M
        71491, -- 2507.02268 Cross-domain Hyperspectral Image Classification based on Bi-directional Dom
        71740, -- 2506.19816 CronusVLA: Transferring Latent Motion Across Time for Multi-Frame Predictio
        71786, -- 2506.18438 CPAM: Context-Preserving Adaptive Manipulation for Zero-Shot Real Image Edi
        71949, -- 2506.13553 RelTopo: Multi-Level Relational Modeling for Driving Scene Topology Reasoni
        71960, -- 2506.13298 Fair Generation without Unfair Distortions: Debiasing Text-to-Image Generat
        72055, -- 2506.10142 Rethinking Brain Tumor Segmentation from the Frequency Domain Perspective
        72191, -- 2506.06281 TerraFM: A Scalable Foundation Model for Unified Multisensor Earth Observat
        72280, -- 2506.04013 Towards Better Disentanglement in Non-Autoregressive Zero-Shot Expressive V
        72523, -- 2505.24181 SCOUT: Teaching Pre-trained Language Models to Enhance Reasoning via Flow C
        72589, -- 2505.22156 InComeS: Integrating Compression and Selection Mechanisms into LLMs for Eff
        72789, -- 2505.17994 Segment Anyword: Mask Prompt Inversion for Open-Set Grounded Segmentation
        72943, -- 2505.13930 BiCrossMamba-ST: Speech Deepfake Detection with Bidirectional Mamba Spectro
        73264, -- 2504.20518 Dynamic Attention Analysis for Backdoor Detection in Text-to-Image Diffusio
        73296, -- 2504.19223 CARL: Camera-Agnostic Representation Learning for Spectral Image Analysis
        73395, -- 2504.15888 MS-Occ: Multi-Stage LiDAR-Camera Fusion for 3D Semantic Occupancy Predictio
        73424, -- 2504.15032 DyST-XL: Dynamic Layout Planning and Content Control for Compositional Text
        73475, -- 2504.12451 One Model to Rig Them All: Diverse Skeleton Rigging with UniRig
        73595, -- 2504.07198 Face-LLaVA: Facial Expression and Attribute Understanding through Instructi
        73602, -- 2504.06897 MedSegFactory: Text-Guided Generation of Medical Image-Mask Pairs
        73781, -- 2504.00463 Exploring the Collaborative Advantage of Low-level Information on Generaliz
        73814, -- 2503.23447 CA^2ST: Cross-Attention in Audio, Space, and Time for Holistic Video Recogn
        73922, -- 2503.17724 Trigger without Trace: Towards Stealthy Backdoor Attack on Text-to-Image Di
        74010, -- 2503.13858 MamBEV: Enabling State Space Models to Learn Birds-Eye-View Representations
        74012, -- 2503.13794 LED: LLM Enhanced Open-Vocabulary Object Detection without Human Curated Da
        74016, -- 2503.13769 Continual Unlearning for Foundational Text-to-Image Models without Generali
        74021, -- 2503.13439 Amodal3R: Amodal 3D Reconstruction from Occluded 2D Images
        74101, -- 2503.10845 Panopticon: Advancing Any-Sensor Foundation Models for Earth Observation
        74162, -- 2503.08336 Talk2PC: Enhancing 3D Visual Grounding through LiDAR and Radar Point Clouds
        74194, -- 2503.07029 Availability-aware Sensor Fusion via Unified Canonical Space
        74199, -- 2503.06898 Illuminating Darkness: Learning to Enhance Low-light Images In-the-Wild
        74395, -- 2502.21120 SEE: See Everything Every Time - Adaptive Brightness Adjustment for Broad
        74749, -- 2502.07711 RenderBox: Expressive Performance Rendering with Text Control
        74762, -- 2502.06785 DeepCrossAttention: Supercharging Transformer Residual Connections
        74970, -- 2502.00937 ModServe: Modality- and Stage-Aware Resource Disaggregation for Scalable Mu
        74998, -- 2502.00528 Vision-Language Modeling in PET/CT for Visual Grounding of Positive Finding
        75308, -- 2501.01406 nnY-Net: Swin-NeXt with Cross-Attention for 3D Medical Images Segmentation
        75375, -- 2412.17241 QTSeg: A Query Token-Based Dual-Mix Attention Framework with Multi-Level Fe
        75444, -- 2412.12760 CAMEL: Cross-Attention Enhanced Mixture-of-Experts and Language Bias for Co
        75445, -- 2412.12718 ASAP: Advancing Semantic Alignment Promotes Multi-Modal Manipulation Detect
        75554, -- 2412.18614 Investigating Acoustic-Textual Emotional Inconsistency Information for Auto
        75610, -- 2407.14108 GaussianBeV: 3D Gaussian Representation meets Perception Models for BeV Seg
        75825, -- 2411.06968 Mamba-based Decoder-Only Approach with Bidirectional Speech Modeling for Sp
        76088, -- 2410.08626 Small Tunes Transformer: Exploring Macro & Micro-Level Hierarchies for Skel
        76152, -- 2410.04172 DB-SAM: Delving into High Quality Universal Medical Image Segmentation
        76220, -- 2410.00767 Zero-Shot Text-to-Speech from Continuous Text Streams
        76715, -- 2407.14812 GaitMA: Pose-guided Multi-modal Feature Fusion for Gait Recognition
        76735, -- 2407.12331 I2AM: Interpreting Image-to-Image Latent Diffusion Models via Bi-Attributio
        76850, -- 2407.01074 Multimodal Conditional 3D Face Geometry Generation
        76893, -- 2406.17957 Improving Robustness of LLM-based Speech Synthesis by Learning Monotonic Al
        77048, -- 2402.18115 UniVS: Unified and Universal Video Segmentation with Prompts as Queries
        77230, -- 2405.13949 PitVQA: Image-grounded Text Embedding LLM for Visual Question Answering in
        77283, -- 2405.07435 An Efficient Multimodal Learning Framework to Comprehend Consumer Preferenc
        77321, -- 2405.03144 PTQ4SAM: Post-Training Quantization for Segment Anything
        77405, -- 2404.12920 Zero-Shot Medical Phrase Grounding with Off-the-shelf Diffusion Models
        77451, -- 2404.07949 Taming Stable Diffusion for Text to 360° Panorama Image Generation
        77569, -- 2403.18271 Unleashing the Potential of SAM for Medical Adaptation via Hierarchical Dec
        77830, -- 2402.05809 You Only Need One Color Space: An Efficient Network for Low-light Image Enh
        78062, -- 2312.12222 EarthVQA: Towards Queryable Earth via Relational Reasoning-Based Remote Sen
        78067, -- 2312.12463 Open Vocabulary Semantic Scene Sketch Understanding
        78554, -- 2309.02773 Diffusion Model is Secretly a Training-free Open Vocabulary Semantic Segmen
        78923, -- 2306.03177 DeepVQE: Real Time Deep Voice Quality Enhancement for Joint Acoustic Echo C
        78939, -- 2306.00914 Conditioning Diffusion Models via Attributes and Semantic Masks for Face Ge
        78956, -- 2305.18832 ReTR: Modeling Rendering Via Transformer for Generalizable Neural Surface R
        78991, -- 2305.15084 Audio-Visual Dataset and Method for Anomaly Detection in Traffic Videos
        79009, -- 2305.13058 Retrieval-augmented Multi-label Text Classification
        79329, -- 2302.13523 VE-KWS: Visual Modality Enhanced End-to-End Keyword Spotting
        79388, -- 2302.01342 Curriculum-Guided Abstractive Summarization
        79553, -- 2211.11448 Delving StyleGAN Inversion for Image Editing: A Foundation Latent Space Vie
        79664, -- 2210.11415 Multi-Head Cross-Attentional PPG and Motion Signal Fusion for Heart Rate Es
        79714, -- 2209.13959 Dynamic MDETR: A Dynamic Multimodal Transformer Decoder for Visual Groundin
        79747, -- 2209.05588 CenterFormer: Center-based Transformer for 3D Object Detection
        80089, -- 2203.17270 BEVFormer: Learning Bird's-Eye-View Representation from Multi-Camera Images
        80380, -- 2111.11011 CDistNet: Perceiving Multi-Domain Character Distance for Robust Text Recogn
        81753, -- 1904.09229 XLSor: A Robust and Accurate Lung Segmentor on Chest X-Rays Using Criss-Cro
        83152, -- 2605.12556 M2Retinexformer: Multi-Modal Retinexformer for Low-Light Image Enhancement
        83187, -- 2605.13169 PanoWorld: Towards Spatial Supersensing in 360^circ Panorama World
        83289, -- 2605.15256 ReactiveGWM: Steering NPC in Reactive Game World Models
        83399, -- 2605.18601 Incantation: Natural Language as the Action Interface for Multi-Entity Vide
        83618, -- 2605.22641 More Context, Larger Models, or Moral Knowledge? A Systematic Study of Schw
        83687, -- 2605.18018 See What I Mean: Aligning Vision and Language Representations for Video Fin
        83699, -- 2605.19282 Rethinking Muon Beyond Pretraining: Spectral Failures and High-Pass Remedie
        83769, -- 2605.25191 Injecting Image Guidance into Text-Conditioned Diffusion Models at Inferenc
        83918, -- 2605.30263 minWM: A Full-Stack Open-Source Framework for Real-Time Interactive Video W
        84117, -- 2510.01448 GeoSURGE: Geo-localization using Semantic Fusion with Hierarchy of Geograph
        84118, -- 2510.02226 TempoControl: Temporal Attention Guidance for Text-to-Video Models
        84129, -- 2510.15104 TGT: Text-Grounded Trajectories for Locally Controlled Video Generation
        84172, -- 2511.13175 HDW-SR: High-Frequency Guided Diffusion Model based on Wavelet Decompositio
        84223, -- 2511.18801 PartDiffuser: Part-wise 3D Mesh Generation via Discrete Diffusion
        84226, -- 2511.18900 MatMart: Material Reconstruction of 3D Objects via Diffusion
        84290, -- 2512.00075 Adapter Shield: A Unified Framework with Built-in Authentication for Preven
        84293, -- 2512.00300 TGSFormer: Scalable Temporal Gaussian Splatting for Embodied Semantic Scene
        84383, -- 2512.11141 Learning complete and explainable visual representations from itemized text
        84407, -- 2512.15524 DeX-Portrait: Disentangled and Expressive Portrait Animation via Explicit a
        84464, -- 2601.06338 Circuit Mechanisms for Spatial Relation Generation in Diffusion Transformer
        84514, -- 2602.12640 ImageRAGTurbo: Towards One-step Text-to-Image Generation with Retrieval-Aug
        84558, -- 2602.19585 Tri-Subspaces Disentanglement for Multimodal Sentiment Analysis
        84573, -- 2602.20223 MultiModalPFN: Extending Prior-Data Fitted Networks for Multimodal Tabular
        84693, -- 2603.01284 FoSS: Modeling Long-Range Dependencies and Multimodal Uncertainty in Trajec
        84703, -- 2603.01688 CoopDiff: A Diffusion-Guided Approach for Cooperation under Corruptions
        84775, -- 2603.06178 Making Training-Free Diffusion Segmentors Scale with the Generative Power
        84792, -- 2603.07430 Disentangled Textual Priors for Diffusion-based Image Super-Resolution
        84807, -- 2603.07918 Enhancing Unregistered Hyperspectral Image Super-Resolution via Unmixing-ba
        84808, -- 2603.07952 VisualAD: Language-Free Zero-Shot Anomaly Detection via Vision Transformer
        84817, -- 2603.08674 Talking Together: Synthesizing Co-Located 3D Conversations from Audio
        84880, -- 2603.12764 SAVA-X: Ego-to-Exo Imitation Error Detection via Scene-Adaptive View Alignm
        84882, -- 2603.12845 Multimodal Protein Language Models for Enzyme Kinetic Parameters: From Subs
        84892, -- 2603.13352 Local Precise Refinement: A Dual-Gated Mixture-of-Experts for Enhancing Fou
        84898, -- 2603.13787 Advancing Cancer Prognosis with Hierarchical Fusion of Genomic, Proteomic a
        84913, -- 2603.14647 TopoCL: Topological Contrastive Learning for Medical Imaging
        84916, -- 2603.14741 PHAC: Promptable Human Amodal Completion
        84964, -- 2603.18093 One-to-More: High-Fidelity Training-Free Anomaly Generation with Attention
        84977, -- 2603.19121 CustomTex: High-fidelity Indoor Scene Texturing via Multi-Reference Customi
        85010, -- 2603.20741 CTCal: Rethinking Text-to-Image Diffusion Models via Cross-Timestep Self-Ca
        85011, -- 2603.20755 Memory-Efficient Fine-Tuning Diffusion Transformers via Dynamic Patch Sampl
        85032, -- 2603.21660 OmniFM: Toward Modality-Robust and Task-Agnostic Federated Learning for Het
        85062, -- 2603.23194 PhysSkin: Real-Time and Generalizable Physics-Based Animation via Self-Supe
        85098, -- 2603.24934 CVA: Context-aware Video-text Alignment for Video Temporal Grounding
        85156, -- 2603.26938 From 3D Pose to Prose: Biomechanics-Grounded Vision-Language Coaching
        85175, -- 2603.27542 MV-RoMa: From Pairwise Matching into Multi-View Track Reconstruction
        85204, -- 2603.29409 CLaD: Planning with Grounded Foresight via Cross-Modal Latent Dynamics
        85271, -- 2604.04348 OmniSonic: Towards Universal and Holistic Audio Generation from Video and T
        85342, -- 2604.10485 UDAPose: Unsupervised Domain Adaptation for Low-Light Human Pose Estimation
        85363, -- 2604.12309 Towards Realistic and Consistent Orbital Video Generation via 3D Foundation
        85384, -- 2604.14925 Improving Sparse Autoencoder with Dynamic Attention
        85527, -- 2605.07552 VIMCAN: Visual-Inertial 3D Human Pose Estimation with Hybrid Mamba-Cross-At
        85538, -- 2605.10130 Thermal-Det: Language-Guided Cross-Modal Distillation for Open-Vocabulary T
        85570, -- 2605.16901 CAR-SAM: Cross-Attention Reconstruction for Post-Training Quantization of t
        85603, -- external Llama 3.2: Revolutionizing edge AI and vision with open, customizable model
        85994, -- 2504.19901 Attention Mechanism, Max-Affine Partition, and Universal Approximation
        86047, -- 2505.18153 REN: Fast and Efficient Region Encodings from Patch-Based Image Encoders
        86170, -- 2507.05427 OpenWorldSAM: Extending SAM2 for Universal Image Segmentation with Language
        86178, -- 2506.05768 AANet: Virtual Screening under Structural Uncertainty via Alignment and Agg
        86187, -- 2505.17645 HoloLLM: Multisensory Foundation Model for Language-Grounded Human Sensing
        86536, -- 2508.10133 MANGO: Multimodal Attention-based Normalizing Flow Approach to Fusion Learn
        86539, -- 2505.19261 Enhancing Text-to-Image Diffusion Transformer via Split-Text Conditioning
        86631, -- 2506.05320 Generalizable, real-time neural decoding with hybrid state-space models
        86659, -- 2510.15783 ReCon: Region-Controllable Data Augmentation with Rectification and Alignme
        86719, -- 2505.19408 Future Link Prediction Without Memory or Aggregation
        86803, -- 2505.18190 PhySense: Sensor Placement Optimization for Accurate Physics Sensing
        86824, -- 2509.25863 MAPLE: Multi-scale Attribute-enhanced Prompt Learning for Few-shot Whole Sl
        86880, -- 2506.09417 ODG: Occupancy Prediction Using Dual Gaussians
        87158, -- 2505.19516 DiffE2E: Rethinking End-to-End Driving with a Hybrid Action Diffusion and S
        87426, -- 2506.12025 Unsupervised Learning for Optimal Transport plan prediction between unbalan
        87476, -- 2411.06780 SynCL: A Synergistic Training Strategy with Instance-Aware Contrastive Lear
        87531, -- 2606.01336 LongAttnComp: Cross-Family Context Compression for Long-Context Reasoning
        87549, -- 2507.20721 AIComposer: Any Style and Content Image Composition via Feature Integration
        87557, -- 2507.19770 MoFRR: Mixture of Diffusion Models for Face Retouching Restoration
        87596, -- 2408.14961 CVPT: Cross Visual Prompt Tuning
        87702, -- 2503.06683 Dynamic Dictionary Learning for Remote Sensing Image Segmentation
        87758, -- 2508.03102 Causal Disentanglement and Cross-Modal Alignment for Enhanced Few-Shot Lear
        87780, -- 2507.03539 CLOT: Closed Loop Optimal Transport for Unsupervised Action Segmentation
        87820, -- 2503.03501 CarGait: Cross-Attention based Re-ranking for Gait recognition
        87853, -- 2507.07620 ViLU: Learning Vision-Language Uncertainties for Failure Prediction
        87892, -- 2412.02545 ShadowHack: Hacking Shadows via Luminance-Color Divide and Conquer
        87902, -- 2411.10715 EVT: Efficient View Transformation for Multi-Modal 3D Object Detection
        87956, -- 2412.16563 SemTalk: Holistic Co-speech Motion Generation with Frame-level Semantic Emp
        88027, -- 2504.10434 Anchor Token Matching: Implicit Structure Locking for Training-free AR Imag
        88147, -- 2507.17377 A Conditional Probability Framework for Compositional Zero-shot Learning
        88153, -- 2507.04961 InterGSEdit: Interactive 3D Gaussian Splatting Editing with 3D Geometry-Con
        88156, -- 2507.07568 Learnable Retrieval Enhanced Visual-Text Alignment and Fusion for Radiology
        88183, -- 2502.09660 Towards Fine-grained Interactive Segmentation in Images and Videos
        88254, -- 2504.07836 AerialVG: A Challenging Benchmark for Aerial Visual Grounding by Exploring
        88348, -- 2510.04668 ConceptSplit: Decoupled Multi-Concept Personalization of Diffusion Models v
        88361, -- 2505.04864 Auto-Regressive Transformation for Image Alignment
        88396, -- 2505.23186 HiGarment: Cross-modal Harmony Based Diffusion Model for Flat Sketch to Rea
        88398, -- 2507.16240 Scale Your Instructions: Enhance the Instruction-Following Fidelity of Unif
        88399, -- 2508.10407 Translation of Text Embedding via Delta Vector to Suppress Strongly Entangl
        88453, -- 2508.10896 ESSENTIAL: Episodic and Semantic Memory Integration for Video Class-Increme
        88487, -- 2503.06934 LLaFEA: Frame-Event Complementary Fusion for Fine-Grained Spatiotemporal Un
        88518, -- 2410.13195 UniGS: Modeling Unitary 3D Gaussians for Novel View Synthesis from Sparse-v
        89065, -- 2410.02483 Event-Customized Image Generation
        89439, -- 2405.17248 On Understanding Attention-Based In-Context Learning for Categorical Data
        89768, -- 2505.17649 Instruct2See: Learning to Remove Any Obstructions Across Distributions
        89805, -- 2410.01651 Efficient Length-Generalizable Attention via Causal Retrieval for Long-Cont
        89849, -- 2504.12262 SCENT: Robust Spatiotemporal Learning for Continuous Scientific Data via Sc
        89935, -- 2502.04230 XAttnMark: Learning Robust Audio Watermarking with Cross-Attention
        90108, -- 2503.17752 HiLoTs: High-Low Temporal Sensitive Representation Learning for Semi-Superv
        90129, -- 2503.13836 SALAD: Skeleton-aware Latent Diffusion for Text-driven Motion Generation an
        90137, -- 2411.18936 Self-Cross Diffusion Guidance for Text-to-Image Synthesis of Similar Subjec
        90189, -- 2412.06143 Precise, Fast, and Low-cost Concept Erasure in Value Space: Orthogonal Comp
        90215, -- 2412.09072 Cross-View Completion Models are Zero-shot Correspondence Estimators
        90274, -- 2505.05505 Apply Hierarchical-Chain-of-Generation to Complex Attributes Text-to-3D Gen
        90292, -- 2503.18933 SyncVP: Joint Diffusion for Synchronous Multi-Modal Video Prediction
        90332, -- 2412.01244 Concept Replacer: Replacing Sensitive Concepts in Diffusion Models via Prec
        90389, -- 2505.05711 DiGIT: Multi-Dilated Gated Encoder and Central-Adjacent Region Integrated D
        90394, -- 2309.12862 Associative Transformer
        90412, -- 2503.21140 Recurrent Feature Mining and Keypoint Mixup Padding for Category-Agnostic P
        90466, -- 2502.20625 T2ICount: Enhancing Cross-modal Understanding for Zero-Shot Counting
        90511, -- 2411.15236 Text Embedding is Not All You Need: Attention Control for Text-to-Image Sem
        90605, -- 2412.14706 EnergyMoGen: Compositional Human Motion Generation with Energy-Based Diffus
        90724, -- 2411.15556 ReWind: Understanding Long Videos with Instructed Learnable Memory
        90910, -- 2504.00496 Learned Image Compression with Dictionary-based Entropy Model
        90922, -- 2503.02009 Morpheus: Text-Driven 3D Gaussian Splat Shape and Color Stylization
        90923, -- 2504.05046 MotionPRO: Exploring the Role of Pressure in Human MoCap and Beyond
        90927, -- 2503.22138 Enhancing Dance-to-Music Generation via Negative Conditioning Latent Diffus
        90932, -- 2503.17675 Towards Transformer-Based Aligned Generation with Self-Coherence Guidance
        91157, -- 2503.10081 AdvPaint: Protecting Images from Inpainting Manipulation via Adversarial At
        91341, -- 2405.13998 CViT: Continuous Vision Transformer for Operator Learning
        91432, -- 2406.05753 Grounding Continuous Representations in Geometry: Equivariant Neural Fields
        91460, -- 2405.01033 CrossMPT: Cross-attention Message-passing Transformer for Error Correcting
        91834, -- 2408.09730 Fragment and Geometry Aware Tokenization of Molecules for Structure-Based D
        92054, -- 2412.01197 InstantSwap: Fast Customized Concept Swapping across Sharp Shape Difference
        92063, -- 2503.07656 DriveTransformer: Unified Transformer for Scalable End-to-End Autonomous Dr
        92087, -- 2501.15878 Slot-Guided Adaptation of Pre-trained Diffusion Models for Object-Centric L
        92173, -- 2407.07760 Learning Spatial-Semantic Features for Robust Video Object Segmentation
        92336, -- 2410.21665 Exploring Local Memorization in Diffusion Models via Bright Ending Attentio
        92455, -- 2505.12587 CMLFormer: A Dual Decoder Transformer with Switching Point Learning for Cod
        92562, -- 2606.04688 MeshWeaver: Sparse-Voxel-Guided Surface Weaving for Autoregressive Mesh Gen
        93335, -- 2510.11750 PRISM: Enhancing PRotein Inverse Folding through Fine- Grained Retrieval on
        93484, -- 2510.24093 OmniText: A Training-Free Generalist for Controllable Text-Image Manipulati
        93720, -- 2603.25734 Unleashing Guidance Without Classifiers for Human-Object Interaction Animat
        93735, -- 2604.03092 Flash-Mono: Feed-Forward Accelerated Gaussian Splatting Monocular SLAM
        93871, -- 2505.18047 RestoreVAR: Visual Autoregressive Generation for All-in-One Image Restorati
        94004, -- 2507.03197 Quantifying Cross-Attention Interaction in Transformers for Interpreting TC
        94163, -- 2602.01435 BioTamperNet: Affinity-Guided State-Space Model Detecting Tampered Biomedic
        94257, -- 2503.09630 CASteer: Cross-Attention Steering for Controllable Concept Erasure
        94304, -- 2510.27391 Modality Alignment across Trees on Heterogeneous Hyperbolic Manifolds
        94552, -- 2602.09534 AUHead: Realistic Emotional Talking Head Generation via Action Units Contro
        94566, -- 2602.06478 Efficient-LVSM: Faster, Cheaper, and Better Large View Synthesis Model via
        94633, -- 2602.04292 Event-T2M: Event-level Conditioning for Complex Text-to-Motion Synthesis
        94639, -- 2510.20707 Mixing Importance with Diversity: Joint Optimization for KV Cache Compressi
        94707, -- 2602.22785 SceneTransporter: Optimal Transport-Guided Compositional Latent Diffusion f
        94812, -- 2602.07415 Learning Molecular Chirality via Chiral Determinant Kernels
        94821, -- 2508.00719 DAMR: Efficient and Adaptive Context-Aware Knowledge Graph Question Answeri
        94986, -- 2505.18612 Mod-Adapter: Tuning-Free and Versatile Multi-concept Personalization via Mo
        95212, -- 2508.01167 T2S: Tokenized Skill Scaling for Lifelong Imitation Learning
        95236, -- 2605.24394 RoboHitch: Learning Visual Affordance from Disordered Keypoints for Hitch K
        95339, -- 2602.08962 Modeling 3D Pedestrian-Vehicle Interactions for Vehicle-Conditioned Pose Fo
        95356, -- 2602.08006 ForecastOcc: Vision-Based Semantic Occupancy Forecasting
        95856, -- external TinyVPR: Distilling Correct and Confusing Knowledge for Lightweight Visual
        96083, -- 2605.02762 Unified Map Prior Encoder for Mapping and Planning
        96115, -- 2503.19713 Semi-SMD: Semi-Supervised Metric Depth Estimation Via Surrounding Cameras f
        96345, -- external Attention-Based Markerless Pose Estimation of the Assistant-Port Trocar in
        96629, -- external DPWM: Autonomous Exploration Via Diffusion-Based Map Prediction Guided Plan
        96676, -- external Probability-Driven Gating for Resilient Multi-Modal Tracking in Robotic Sys
        96790, -- external Lightweight Guidance Sampling and Deep Refinement Reconstruction Network fo
        96971, -- 2603.01953 Closed-Loop Action Chunks with Dynamic Corrections for Training-Free Diffus
        97508, -- 2509.09747 D-CAT: Decoupled Cross-Attention Knowledge Transfer between Sensor Modaliti
        97519, -- external Real-Time BEVFormer: Fast Transformer-Based BEV Perception Network on Edge
        97529, -- 2602.13689 Symmetry-Aware Fusion of Vision and Tactile Sensing Via Bilateral Force Pri
        97689, -- 2603.02532 EIMC: Efficient Instance-Aware Multi-Modal Collaborative Perception
        97691, -- 2509.19047 ManipForce: Force-Guided Policy Learning with Frequency-Aware Representatio
        98065, -- 2606.05011 CIPER: A Unified Framework for Cross-view Image-retrieval and Pose-estimati
        98071, -- external GoCA: Making Training-Free Diffusion Segmentors Scale with the Generative P
        98278, -- 2211.15766 Superpoint Transformer for 3D Scene Instance Segmentation
        98427, -- 2606.06302 Tangram: Unlocking Non-Uniform KV Cache Compression for Efficient Multi-tur
        98535, -- 2606.15514 Reinforcement Learning-Guided Retrieval with Soft Fusion for Robust Multimo
        98676, -- 2606.22807 KaLM-Reranker-V1: Fast but Not Late Interaction for Compressed Document Rer
        98877, -- 2412.11023 Exploring Enhanced Contextual Information for Video-Level Object Tracking
        98901, -- 2511.13204 RefineVAD: Semantic-Guided Feature Recalibration for Weakly Supervised Vide
        98905, -- 2507.02985 Gated Recursive Fusion: A Stateful Approach to Scalable Multimodal Transfor
        98979, -- 2606.22749 RaysUp: Ultra-light Universal Feature Upsampling via Geometry-Aware Ray Rep
        99162, -- 2505.12408 ViEEG: Hierarchical Visual Neural Representation for EEG Brain Decoding
        99597, -- 2509.00787 Image-to-Brain Signal Generation for Visual Prosthesis with CLIP Guided Mul
        99624, -- 2511.21325 SONAR: Spectral‑Contrastive Audio Residuals for Generalizable Deepfake Dete
        99686, -- 2602.02780 Scaling-Aware Adapter for Structure-Grounded LLM Reasoning
        99704, -- 2605.01542 Mesh Based Simulations with Spatial and Temporal awareness
        99726, -- 2508.04228 LayerT2V: A Unified Multi-Layer Video Generation Framework
        99911, -- 2605.00130 Learning Fingerprints for Medical Time Series with Redundancy-Constrained I
        99932, -- 2602.08585 Predicting Future Utility: Global Combinatorial Optimization for Task-Agnos
        99991, -- 2605.10203 Polyphonia: Zero-Shot Timbre Transfer in Polyphonic Music with Acoustic-Inf
        100068, -- 2602.02579 ProphetKV: User-Query-Driven Selective Recomputation for Efficient KV Cache
        100089, -- 2509.21003 Query-Based Asymmetric Modeling with Decoupled Input–Output Rates for Speec
        100111, -- 2605.03245 Text-Conditional JEPA for Learning Semantically Rich Visual Representations
        100306, -- 2605.14664 MiVE: Multiscale Vision-language features for reference-guided video Editin
        100390, -- 2602.04898 Semantic-level Backdoor Attack against Text-to-Image Diffusion Models
        100526, -- 2606.09250 LiteVSR: Lightweight Adaptation of Frozen Diffusion Transformers for Video
        100745, -- 2604.09429 Rays as Pixels: Learning A Joint Distribution of Video and Camera Trajector
        101410, -- 2601.04509 A General Neural Backbone for Mixed-Integer Linear Optimization via Dual At
        101550, -- 2602.00265 World-Shaper: A Unified Framework for 360° Panoramic Editing
        101683, -- 2512.19602 No Data? No Problem: Robust Vision-Tabular Learning with Missing Values
        101816, -- 2603.00133 You Don’t Need All That Attention: Surgical Memorization Mitigation in Text
        102327, -- 2606.01041 ExpWeaver: LLM Agents Learn from Experience via Latent RAG
        102352, -- 2605.21308 Deformba: Vision State Space Model with Adaptive State Fusion
        102418, -- 2602.21716 TranX-Adapter: Bridging Artifacts and Semantics within MLLMs for Robust AI-
        102498, -- 2606.14351 ForceForget: Reinforcement Concept Removal for Enhancing Safety in Text-to-
        102665, -- 2305.00163 Enhancing Video Super-Resolution via Implicit Resampling-based Alignment
        102705, -- 2607.06309 Token-Based Dual-view Fusion and Adaptation of Large Vision Models for Brea
        103491, -- 2602.15846 Gated Tree Cross-Attention for Checkpoint-Compatible Syntax Injection in De
        103936, -- 2204.06519 CARCA: Context and Attribute-Aware Next-Item Recommendation via Cross-Atten
        103971, -- 2208.00438 Toward Understanding WordArt: Corner-Guided Transformer for Scene Text Reco
        104469, -- 2607.18934 Transcription Policy as a Latent Variable: Activating Controllable Verbatim
        104537, -- external SAM-I2V++: Efficiently Upgrading SAM for Promptable Video Segmentation
        104600, -- 2603.16551 CompDiff: Hierarchical Compositional Diffusion for Fair and Zero-Shot Inter
        104935, -- external Alzheimer’s Disease Recognition Based on Adaptive Graph Normalization Flow
        104942, -- 2508.07788 Anatomy-Aware Low-Dose CT Denoising via Pretrained Vision Models and Semant
        104963, -- external Background-Invariant Independence-Guided Multi-head Attention Network for S
        104985, -- external BrainAlign: EEG-Vision Alignment via Frequency-Aware Temporal Encoder and D
        104986, -- external Brain-Environment Cross-Attention (BECA) Meta-Matching: A New Perspective o
        105008, -- external CAUDA-MI: Cross Attention-Guided Unsupervised Domain Adaptation with Mutual
        105032, -- 2502.20509 CoCa-CXR: Contrastive Captioners Learn Strong Temporal Structures for Chest
        105129, -- external Dual-Stream Multi-Band Fusion Network for Dynamic Functional Connectivity A
        105152, -- 2505.09435 Endo-CLIP: Progressive Self-Supervised Pre-training on Raw Colonoscopy Reco
        105175, -- 2507.19621 Exemplar Med-DETR: Toward Generalized and Robust Lesion Detection in Mammog
        105253, -- external HAGE: Hierarchical Alignment Gene-Enhanced Pathology Representation Learnin
        105257, -- external HARM3-Fusion: Hierarchical Attentional Representation Learning of Multi-Mod
        105258, -- 2505.17311 Harnessing EHRs for Diffusion-based Anomaly Detection on Chest X-rays
        105283, -- external Hybrid Local-Window-Attention–Assisted U-Net Model for Multimodal Medical-I
        105306, -- external Inferring Super-Resolved Gene Expression by Integrating Histology Images an
        105341, -- 2508.18303 Learning Explainable Imaging-Genetics Associations Related to a Neurologica
        105347, -- external Lesion-centered vision transformer for stroke outcome prediction from image
        105364, -- external Longitudinal MRI-Clinical Multimodal Fusion for pCR Prediction in Breast Ca
        105374, -- external MAK-GAN: Multi-level Adaptive Convolutional Kernels for Asymmetric Multi-mo
        105407, -- external Mesh4D: A Motion-Aware Multi-View Variational Autoencoder for 3D+t Mesh Rec
        105425, -- external MoDiff: A Morphology-Emphasized Diffusion Model for Ambiguous Medical Image
        105463, -- external Multi-Spatial Granger Causality Features Fusion Network for Alzheimer’s Dis
        105517, -- 2503.08346 Pathology-Aware Adaptive Watermarking for Text-Driven Medical Image Synthes
        105615, -- external Revisiting Masked Image Modeling with Standardized Color Space for Domain G
        105664, -- 2508.04205 Small Lesions-aware Bidirectional Multimodal Multiscale Fusion Network for
        105676, -- external Spatial Aggregation for Semi-supervised Active Learning in 3D Medical Image
        105679, -- 2506.23827 Spatially Gene Expression Prediction using Dual-Scale Contrastive Learning
        105826, -- external ViTexNet: Vision-Text Guided Dynamic Convolution Network for Medical Image
        105870, -- 2606.05711 Beyond tokens: a unified framework for latent communication in LLM-based mu
        106310, -- 2603.01331 MetaState: Persistent Working Memory Enhances Reasoning in Discrete Diffusi
        106451, -- 2411.03709 AutoGameUI: Constructing High-Fidelity GameUI via Multimodal Correspondence
        106453, -- 2508.14443 Reconstruction Using the Invisible: Intuition from NIR and Metadata for Enh
        106458, -- 2511.12969 HiFusion: Hierarchical Intra-Spot Alignment and Regional Context Fusion for
        106573, -- 2511.12259 A Disease-Aware Dual-Stage Framework for Chest X-ray Report Generation
        106715, -- 2512.10376 RaLiFlow: Scene Flow Estimation with 4D Radar and LiDAR Point Clouds
        106837, -- 2504.19567 GenPTW: Latent Image Watermarking for Provenance Tracing and Tamper Localiz
        106839, -- 2512.15261 MMMamba: A Versatile Cross-Modal in Context Fusion Framework for Pan-Sharpe
        106901, -- 2603.06186 SpaCRD: Multimodal Deep Fusion of Histology and Spatial Transcriptomics for
        107018, -- 2509.09232 Medverse: A Universal Model for Full-Resolution 3D Medical Image Segmentati
        107062, -- 2511.12590 Fine-Grained Representation for Lane Topology Reasoning
        107182, -- 2512.22741 A Text-Routed Sparse Mixture-of-Experts Model with Explanation and Temporal
        107263, -- 2503.06515 SAQ-SAM: Semantically-Aligned Quantization for Segment Anything Model
        107307, -- 2511.08238 Remodeling Semantic Relationships in Vision-Language Fine-Tuning
        107316, -- 2511.09585 Video Echoed in Music: Semantic, Temporal, and Rhythmic Alignment for Video
        107335, -- 2512.07345 Debiasing Diffusion Priors via 3D Attention for Consistent Gaussian Splatti
        107346, -- 2603.14189 Walking Further: Semantic-Aware Multimodal Gait Recognition Under Long-Rang
        107439, -- 2511.11700 EPSegFZ: Efficient Point Cloud Semantic Segmentation for Few- and Zero-Shot
        107448, -- 2508.08334 HSA-Net: Hierarchical and Structure-Aware Framework for Efficient and Scala
        107453, -- 2511.15066 BokehFlow: Depth-Free Controllable Bokeh Rendering via Flow Matching
        107456, -- 2506.23205 BridgeShape: Latent Diffusion Schrödinger Bridge for 3D Shape Completion
        107502, -- 2509.18711 RSVG-ZeroOV: Exploring a Training-Free Framework for Zero-Shot Open-Vocabul
        107562, -- 2603.09287 Exploring Modality-Aware Fusion and Decoupled Temporal Propagation for Mult
        107578, -- 2601.13715 MVGD-Net: A Novel Motion-aware Video Glass Surface Detection Method
        107584, -- 2511.08252 Melodia: Training-Free Music Editing Guided by Attention Probing in Diffusi
        107651, -- 2512.02780 Rethinking Surgical Smoke: A Smoke-Type-Aware Laparoscopic Video Desmoking
        107662, -- 2511.12462 Redundancy-optimized Multi-head Attention Networks for Multi-view Multi-lab
        107783, -- 2511.17806 Indoor Multi-View Radar Object Detection via 3D Bounding Box Diffusion
        107872, -- 2511.11031 Accelerating Controllable Generation via Hybrid-grained Cache
        107934, -- 2511.10935 CAT-Net: A Cross-Attention Tone Network for Cross-Subject EEG-EMG Fusion To
        107973, -- 2511.09352 Spatio-Temporal Context Learning with Temporal Difference Convolution for M
        107994, -- 2511.17555 Speech Recognition Model Improves Text-to-Speech Synthesis Using Fine-Grain
        108093, -- 2508.11661 Sparse Attention Across Multiple-Context KV Cache
        108301, -- 2511.13125 Region-Point Joint Representation for Effective Trajectory Similarity Learn
        108322, -- 2511.14396 Continuous Vision-Language-Action Co-Learning with Semantic-Physical Alignm
        108422, -- 2603.12773 Empowering Semantic-Sensitive Underwater Image Enhancement with VLM
        108423, -- 2511.12151 FIA-Edit: Frequency-Interactive Attention for Efficient and High-Fidelity I
        108430, -- 2511.17604 BrainHGT: A Hierarchical Graph Transformer for Interpretable Brain Network
        108655, -- 2608.02738 Knowledge-Geometry Decoupling: Refreshable Pretrained Transfer for Streamin
        108726, -- 2608.05070 HelloWorld: Enabling Socially Interactive Characters in Video World Models
        108817, -- 2607.00861 TrajLoc: Trajectory-Attention Localization for Multi-Object Motion Control
        109324, -- 2103.15436 Transformer Tracking
        109354, -- 2310.07781 3D TransUNet: Advancing Medical Image Segmentation through Vision Transform
        109405, -- 2608.15045 MOSS-VL Technical Report
        109580, -- 2608.20910 InfinityEdit: Infinite Video Editing with a Lightweight Edit-Ignition Adapt
        109872, -- 2411.11214 DeforHMR: Vision Transformer with Deformable Cross-Attention for 3D Human M
        110077, -- 2508.21098 TrInk: Ink Generation with Transformer Network
        110094, -- 2508.17690 Text Meets Topology: Rethinking Out-of-distribution Detection in Text-Rich
        110931, -- external Cross-MoE: An Efficient Temporal Prediction Framework Integrating Textual M
        111071, -- external FillerSpeech: Towards Human-Like Text-to-Speech Synthesis with Filler Inser
        111159, -- 2505.22045 Mitigating Audiovisual Mismatch in Visual-Guide Audio Captioning
        111219, -- 2509.14677 SpeechMLC: Speech Multi-label Classification
        111268, -- external CAGCRN: Real-Time Speech Enhancement with a Lightweight Model for Joint Aco
        111355, -- 2508.05978 DAFMSVC: One-Shot Singing Voice Conversion with Dual Attention Mechanism an
        111409, -- 2506.11090 End-to-End Diarization utilizing Attractor Deep Clustering
        111461, -- 2506.02621 Cross-attention and Self-attention for Audio-visual Speaker Diarization in
        111487, -- 2506.01148 Towards Fusion of Neural Audio Codec-based Representations with Spectral fo
        111564, -- 2505.20961 Efficient and Microphone-Fault-Tolerant 3D Sound Source Localization
        111600, -- external CAMER: Contribution-Aware Multimodal Emotion Recognition
        111674, -- external A Joint Network for Singing Melody Extraction from Polyphonic Music with At
        111712, -- external Spot and Merge: A Hybrid Context Biasing Approach for Rare Word and Out of
        111714, -- external Improving Cross-Attention based on Positional Alignment during Inference fo
        111869, -- external FoleyMaster: High-Quality Video-to-Audio Synthesis via MLLM-Augmented Promp
        111887, -- external Multimodal Emotion Diarization: Frame-Wise Integration of Text and Audio Re
        111890, -- external Pitch Contour Model (PCM) with Transformer Cross-Attention for Speech Emoti
        111897, -- external DiffEmotionVC: A Dual-Granularity Disentangled Diffusion Framework for Any-
        111993, -- external Visually-Adaptive Guided Robust Speech Recognition with Parameter-Efficient
        112001, -- external Cross-Attention-Based Target Sound Extraction by Fully Leveraging Enrollmen
        112015, -- external Multilingual Speech Assessment Using Cross-Attention and Multitask Learning
        112081, -- external EAA: Emotion-Aware Audio Large Language Models with Dual Cross-Attention an
        112125, -- 2505.19448 Beyond Manual Transcripts: The Potential of Automated Speech Recognition Er
        112138, -- external EmoSpeechAuth: Emotion-Aware Speaker Verification
        112406, -- external Align before Collaborate: Mitigating Feature Misalignment for Robust Multi-
        112462, -- external Elegantly Written: Disentangling Writer and Character Styles for Enhancing
        112468, -- 2403.11107 Self-supervised co-salient object detection via feature correspondences at
        112474, -- 2404.14409 CrossScore: A Multi-View Approach to Image Evaluation and Scoring
        112483, -- 2407.05358 CPM: Class-conditional Prompting Machine for Audio-visual Segmentation
        112508, -- external SpatialFormer: Towards Generalizable Vision Transformers with Explicit Spat
        112535, -- external Attention Decomposition for Cross-Domain Semantic Segmentation
        112552, -- external Point-supervised Panoptic Segmentation via Estimating Pseudo Labels from Le
        112668, -- external AugDETR: Improving Multi-scale Learning for Detection Transformer
        112672, -- external 4Diff: 3D-Aware Diffusion Model for Third-to-First Viewpoint Translation
        112723, -- 2403.00326 DAMSDet: Dynamic Adaptive Multispectral Detection Transformer with Competit
        112799, -- 2407.14709 ∞-Brush: Controllable Large Image Synthesis with Diffusion Models in Infini
        112850, -- 2403.11868 View-Consistent 3D Editing with Gaussian Splatting
        112868, -- 2311.17057 ReMoS: 3D Motion-Conditioned Reaction Synthesis for Two-Person Interactions
        112893, -- 2407.03575 DGR-MIL: Exploring Diverse Global Representation in Multiple Instance Learn
        112922, -- 2308.06739 Free-ATM: Harnessing Free Attention Masks for Representation Learning on Di
        112930, -- external SemReg: Semantics Constrained Point Cloud Registration
        112937, -- external Three Things We Need to Know About Transferring Stable Diffusion to Visual
        113011, -- 2306.14408 Text-Anchored Score Composition: Tackling Condition Misalignment in Text-to
        113041, -- external Diffusion-Guided Weakly Supervised Semantic Segmentation
        113120, -- 2407.05352 Exploring Phrase-Level Grounding with Text-to-Image Diffusion Model
        113190, -- 2404.05979 StoryImager: A Unified and Efficient Framework for Coherent Story Visualiza
        113294, -- 2411.06344 CityGuessr: City-Level Video Geo-Localization on a Global Scale
        113302, -- 2407.01851 Meerkat: Audio-Visual Large Language Model for Grounding in Space and Time
        113318, -- external MRSP: Learn Multi-Representations of Single Primitive for Compositional Zer
        113366, -- 2407.20928 UniProcessor: A Text-induced Unified Low-level Image Processor
        113438, -- 2407.13095 Audio-visual Generalized Zero-shot Learning the Easy Way
        113493, -- external KeypointDETR: An End-to-End 3D Keypoint Detector
        113520, -- 2408.00372 Few-shot Defect Image Generation based on Consistency Modeling
        113533, -- 2403.11052 Unveiling and Mitigating Memorization in Text-to-image Diffusion Models thr
        113551, -- 2409.07307 Data Augmentation via Latent Diffusion for Saliency Prediction
        113726, -- 2606.21165 OmniV2X: A Generative Foundation Planner for Efficient End-to-End Cooperati
        113781, -- external Anima 3.8B
        113842, -- 2608.29974 SpanCalib-VLM: Calibrated Hallucination Span Detection in Vision-Language M
        113878, -- 2607.12993 X-Lens: Real-Time Metric Depth Estimation with Heterogeneous Cameras
        113930, -- 2609.03430 Random Attention: Rethinking KV Cache Eviction for Efficient Reasoning
        113982, -- 2609.03586 The Attention Triangle in Audio-Video Models
        114049, -- 2609.07414 RelightFormer: Feed-forward Generative Transformer for Multiview Object Rel
        114175, -- 2609.13141 SAS: Simple Attention Sparsification via End-to-End Optimization of Context
        114286, -- external Selective Temporal Fusion using Recurrent Attention for End-to-End Autonomo
        114327, -- external A Multi-Information Dual-Layer Cross-Attention Model for Esophageal Fistula
        114344, -- external ABP: Asymmetric Bilateral Prompting for Text-guided Medical Image Segmentat
        114390, -- external Attention-Enhanced Fusion of Structural and Functional MRI for Analyzing HI
        114475, -- 2404.12973 Cross-modal Diffusion Modelling for Super-resolved Spatial Transcriptomics
        114491, -- external DCrownFormer: Morphology-aware Point-to-Mesh Generation Transformer for Den
        114870, -- external DTCA: Dual-Branch Transformer with Cross-Attention for EEG and Eye Movement
        114899, -- 2407.05323 Enhancing Label-efficient Medical Image Segmentation with Text-guided Diffu
        114914, -- external Explanation-driven Cyclic Learning for High-Quality Brain MRI Reconstructio
        114927, -- 2406.14014 Feature Fusion Based on Mutual-Cross-Attention Mechanism for EEG Emotion Re
        114988, -- external HF-ResDiff: High-Frequency-guided Residual Diffusion for Multi-dose PET Rec
        115046, -- external Label-guided Teacher for Surgical Phase Recognition via Knowledge Distillat
        115079, -- external LOMIA-T: A Transformer-based LOngitudinal Medical Image Analysis framework
        115140, -- external MuGI: Multi-Granularity Interactions of Heterogeneous Biomedical Data for S
        115141, -- external Multi-category Graph Reasoning for Multi-modal Brain Tumor Segmentation
        115143, -- external Multi-disease Detection in Retinal Images Guided by Disease Causal Estimati
        115152, -- external Multi-modality 3D CNN Transformer for Assisting Clinical Decision in Intrac
        115260, -- external SAM Guided Task-Specific Enhanced Nuclei Segmentation in Digital Pathology
        115335, -- 2407.08948 Symmetry Awareness Encoded Deep Learning Framework for Brain Imaging Analys
        115408, -- external VDPF: Enhancing DVT Staging Performance Using a Global-Local Feature Fusion
        115415, -- external Visual-Textual Matching Attention for Lesion Segmentation in Chest Images
        115451, -- 2311.16491 Z*: Zero-shot Style Transfer via Attention Reweighting
        115469, -- 2405.11913 Diff-BGM: A Diffusion Model for Video Background Music Generation
        115556, -- external H-ViT: A Hierarchical Vision Transformer for Deformable Image Registration
        115558, -- external Probing Synergistic High-Order Interaction in Infrared and Visible Image Fu
        115574, -- external Estimating Extreme 3D Image Rotations using Cascaded Attention
        115602, -- external Implicit Motion Function
        115652, -- 2403.17000 Learning Spatial Adaptation and Temporal Coherence in Diffusion Models for
        115655, -- 2405.08909 ADA-Track: End-to-End Multi-Camera 3D Multi-Object Tracking with Alternatin
        115670, -- external Learning Degradation-unaware Representation with Prior-based Latent Transfo
        115703, -- 2311.17083 CLiC: Concept Learning in Context
        115736, -- 2406.11820 Composing Object Relations and Attributes for Image-Text Matching
        115744, -- 2403.15330 Selectively Informative Description can Reduce Undesired Embedding Entangle
        115752, -- 2306.08736 LoSh: Long-Short Text Joint Prediction Network for Referring Video Object S
        115803, -- 2404.07610 Do You Remember? Dense Video Captioning with Cross-Modal Memory Retrieval
        115884, -- external RepKPU: Point Cloud Upsampling with Kernel Point Representation and Deforma
        115919, -- 2406.04032 Zero-Painter: Training-Free Layout Control for Text-to-Image Synthesis
        115924, -- external Boosting Spike Camera Image Reconstruction from a Perspective of Dealing wi
        115956, -- 2404.11291 Closely Interactive Human Reconstruction with Proxemics and Physics-Guided
        115961, -- 2403.19501 RELI11D: A Comprehensive Multimodal Human Motion Dataset and Method
        115965, -- 2311.17095 Emergent Open-Vocabulary Semantic Segmentation from Off-the-shelf Vision-La
        115967, -- external MPOD123: One Image to 3D Content Generation Using Mask-enhanced Progressive
        115969, -- 2403.16440 RCBEVDet: Radar-camera Fusion in Bird's Eye View for 3D Object Detection
        116028, -- 2403.01818 AllSpark: Reborn Labeled Features from Unlabeled in Transformer for Semi-Su
        116047, -- external Discovering Syntactic Interaction Clues for Human-Object Interaction Detect
        116049, -- external FACT: Frame-Action Cross-Attention Temporal Modeling for Efficient Action S
        116126, -- 2312.06716 Deciphering 'What' and 'Where' Visual Pathways from Spectral Clustering of
        116155, -- 2404.15081 Perturbing Attention Gives You More Bang for the Buck: Subtle Imaging Pertu
        116231, -- 2312.08985 OMG: Towards Open-vocabulary Motion Generation via Mixture of Controllers
        116259, -- 2311.13250 FedHCA2: Towards Hetero-Client Federated Multi-Task Learning
        116301, -- 2403.16131 Salience DETR: Enhancing Detection Transformer with Hierarchical Salience F
        116313, -- 2404.01156 SyncMask: Synchronized Attentional Masking for Fashion-centric Vision-Langu
        116326, -- external Bilateral Adaptation for Human-Object Interaction Detection with Occlusion-
        116374, -- 2312.00065 Unsupervised Keypoints from Pretrained Diffusion Models
        116381, -- 2402.19387 SeD: Semantic-Aware Discriminator for Image Super-Resolution
        116382, -- 2312.00825 SocialCounterfactuals: Probing and Mitigating Intersectional Social Biases
        116518, -- 2311.11016 SNI-SLAM: Semantic Neural Implicit SLAM
        116565, -- 2403.04321 Discriminative Probing and Tuning for Text-to-Image Generation
        116586, -- external EASE-DETR: Easing the Competition among Object Queries
        116604, -- 2403.03431 Towards Understanding Cross and Self-Attention in Stable Diffusion for Text
        116683, -- 2403.02899 Domain-Agnostic Mutual Prompting for Unsupervised Domain Adaptation
        116696, -- 2406.06264 DualAD: Disentangling the Dynamic and Static World for End-to-End Driving
        116725, -- 2402.17417 CARZero: Cross-Attention Alignment for Radiology Zero-Shot Classification
        116883, -- external Neural Exposure Fusion for High-Dynamic Range Object Detection
        116887, -- 2311.16097 CG-HOI: Contact-Guided 3D Human-Object Interaction Generation
        116915, -- 2403.05239 Towards Effective Usage of Human-Centric Priors in Diffusion Models for Tex
        116925, -- external Distraction is All You Need: Memory-Efficient Image Immunization against Di
        116997, -- external Hybrid Proposal Refiner: Revisiting DETR Series from the Faster R-CNN Persp
        117016, -- 2305.11577 LeftRefill: Filling Right Canvas based on Left Reference through Generalize
        117028, -- 2406.03902 C^2RV: Cross-Regional and Cross-View Learning for Sparse-View CBCT Reconstr
        117029, -- 2402.11874 Language-guided Image Reflection Separation
        117077, -- 2507.13364 OmniVec2 - A Novel Transformer based Network for Large Scale Multimodal and
        117189, -- 2308.12831 EFormer: Enhanced Transformer towards Semantic-Contour Features of Foregrou
        117256, -- 2507.01667 What does really matter in image goal navigation?
        117262, -- 2508.14278 GALA: Guided Attention with Language Alignment for Open Vocabulary Gaussian
        117278, -- external Enhancing 3D Object Tracking via Dual-Context Propagation and Temporal Cont
        117293, -- 2511.04864 Self-Supervised Implicit Attention Priors for Point Cloud Reconstruction
        117309, -- 2508.18597 SemLayoutDiff: Semantic Layout Generation with Diffusion Model for Indoor S
        117334, -- 2501.08329 Predicting 4D Hand Trajectory from Monocular Videos
        117404, -- 2607.01370 MapDreamer: Aerial Imagery Conditioned Latent Diffusion For Lane Level Map
        117538, -- 2607.05347 WildSplat: Feedforward Gaussian Splatting from Unposed In-the-Wild Images
        117712, -- external OCA: ODE-Driven Cross-Attention for Image-to-Point-Cloud Registration
        117713, -- 2607.02486 GeoMix: Descriptor-Free Visual Localization via Global Context and Multi-De
        117720, -- 2603.22851 UniQueR: Unified Query-based Feedforward 3D Reconstruction
        117734, -- 2509.13907 White Aggregation and Restoration for Few-shot 3D Point Cloud Semantic Segm
        117820, -- 2606.21910 Fidelity- and Perception-Aware Local Implicit Attention for Arbitrary-Scale
        117826, -- 2608.05626 Dual-Output Multi-Exposure HDR Reconstruction via SDR Fusion and Gain Map I
        117954, -- 2607.11205 Parallax Portrait Matting
        118016, -- 2607.01938 PhysMani: Physics-principled 3D World Model for Dynamic Object Manipulation
        118300, -- 2608.10684 Embedding Rotation Invariance for Provable Multi-Oriented Scene Text Recogn
        118305, -- 2607.03038 OmniDS: Dual-Stream Context Fusion for Omnidirectional Depth from Fisheye C
        118330, -- 2607.03990 InSpace: Structure-Aware 3D Indoor Scene Generation from a Single 360° Imag
        118359, -- 2603.12937 SGMatch: Semantic-Guided Non-Rigid Shape Matching with Flow Regularization
        118373, -- external FairSteer: Cross-Attention Steering Towards a Fairer Text-Guided Image Gene
        118388, -- 2603.25711 Seeing to Ground: Visual Attention for Hallucination-Resilient MDLLMs
        118399, -- 2607.23492 To Erase, or Not to Erase: Robust Training-Free Concept Erasure with Preser
        118437, -- 2603.08020 VSDiffusion: Taming Ill-Posed Shadow Generation via Visibility-Constrained
        118459, -- 2606.25578 H-Adapter: Pose-Robust Hairstyle Transfer via Attention-Derived, Source-Ali
        118519, -- 2607.19886 MTVDiff: Multimodal Conditional Latent Diffusion for Enhanced Thermal-to-Vi
        118556, -- 2603.12575 AccelAes: Accelerating Diffusion Transformers for Training-Free Aesthetic-E
        118691, -- 2608.15708 What You Ask is What You Ground: Bridging Question Intent to Temporal Evide
        118698, -- 2606.31054 ADAPT: Attention Dynamics Alignment with Preference Tuning for Faithful MLL
        118797, -- 2606.26812 Multi-modality Image Fusion under Adverse Weather: Mask-Guided Feature Rest
        118869, -- 2607.05955 NegROI: Click-Centric Uncertainty-Guided Refinement with Scene-Conditioned
        118931, -- 2606.25962 A Benchmark for Heterogeneous Stereo Deblurring with Physically- and Epipol
        118935, -- 2505.20935 ISAC: Training-Free Instance-to-Semantic Attention Control for Multi-Instan
        119018, -- 2606.31367 Evidence Triangulation for Multimodal Fact-Checking in the Wild
        119035, -- 2606.21956 Denoising-Enhanced Coarse-to-Fine Infrared Small Target Detection with Atte
        119193, -- external A Dual-Transformer Architecture with Cross-Attention for Multi-Camera View
        119348, -- 2606.30598 Towards in-the-wild Egocentric 3D Hand-Object Pose Estimation
        119350, -- 2607.03825 Q-TriM: Question-Guided Tri-Modal Attention for Audio–Visual Question Answe
        119366, -- 2607.06405 Precise Video-to-Audio Generation with Cross-Modal Alignment in Latent Spac
        119425, -- 2512.20117 Delayed Bidirectional Alignment via Disentangled Audio Semantics for Audio-
        119438, -- 2605.08729 Unison: Harmonizing Motion, Speech, and Sound for Human-Centric Audio-Video
        119515, -- 2607.23271 What CLIP Knows but Cannot Say: Recovering Negation from Frozen Intermediat
        119856, -- 2508.02004 Devil is in the Detail: Towards Injecting Fine Details of Image Prompt in I
        119920, -- external CLIP is Almost All You Need: Towards Parameter-Efficient Scene Text Retriev
        119936, -- external Scaling up Image Segmentation across Data and Tasks
        119944, -- external Beyond Image Classification: A Video Benchmark and Dual-Branch Hybrid Discr
        119986, -- external Wavelet and Prototype Augmented Query-based Transformer for Pixel-level Sur
        119987, -- 2510.08791 Alignment, Mining and Fusion: Representation Alignment with Hard Negative M
        120071, -- external Motions as Queries: One-Stage Multi-Person Holistic Human Motion Capture
        120120, -- external M3amba: Memory Mamba is All You Need for Whole Slide Image Classification
        120123, -- 2503.15197 Detect-and-Guide: Self-regulation of Diffusion Models for Safe Text-to-Imag
        120178, -- 2505.22427 RC-AutoCalib: An End-to-End Radar-Camera Automatic Calibration Network
        120197, -- 2507.02687 APT: Adaptive Personalized Training for Diffusion Models with Limited Data
        120225, -- external Illumination Spectrum Estimation for Multispectral Images via Surface Refle
        120333, -- external Sound Bridge: Associating Egocentric and Exocentric Videos via Audio Cues
        120377, -- external FIFA: Fine-grained Inter-frame Attention for Driver's Video Gaze Estimation
        120447, -- external LP-Diff: Towards Improved Restoration of Real-World Degraded License Plate
        120471, -- 2503.09491 DAMM-Diffusion: Learning Divergence-Aware Multi-Modal Diffusion Model for N
        120680, -- external Tackling Alignment Ambiguity in Person Retrieval through Conversational Att
        120734, -- external EG-3DVG: Expression and Geometry Aware Grounding Decoder for 3D Visual Grou
        120799, -- external LiteSense: Lifting Lightweight ToF with RGB for High-Resolution Metric Dept
        120842, -- external Resolving the Stability-Plasticity Dilemma in Reinforcement Learning via Co
        120989, -- external CompetitorFormer: Mitigating Query Conflicts for 3D Instance Segmentation v
        121073, -- external Language Does Matter for Cross-Domain Few-Shot Visual Feature Enhancement
        121083, -- external CaricHarmony: Contrastive Diffusion Paths for Identity-Preserving Caricatur
        121092, -- external Seeing Both Sides: Towards Bidirectional Semantic Alignment for Open-Vocabu
        121095, -- external Decoding 3D Perception via BrainSSD: Synergistic Fusion of EEG Representati
        121123, -- external RAG-TP: A General Framework for Vehicle Trajectory Prediction via Retrieval
        121131, -- external GenErase: Generalizable and Semantically-Aware Concept Erasure in Diffusion
        121132, -- external RawMetaDiff: Unlocking Extreme Darkness from Dual-Exposure RAW with Meta-Gu
        121229, -- 2512.13465 PoseAnything: General Pose-guided Video Generation with Part-aware Temporal
        121238, -- external Simple-ViLMedSAM: Simple Text Prompts Meet Vision-Language Models for Medic
        121268, -- external UniGeoRS: A Unified Benchmark for Tri-view Geo-Localization
        121285, -- external MatchMask: Mask-Centric Generative Data Augmentation for Label-Scarce Seman
        121294, -- external Learning to Diversify and Focus: A Reinforcement Framework for Open-Vocabul
        121312, -- 2605.08808 Curvature-Aware Captioning: Leveraging Geodesic Attention for 3D Scene Unde
        121441, -- external HierUQ: Hierarchical Uncertainty Quantification with Adaptive Granularity R
        121460, -- external Mixture-of-Experts based Feature Decoupling for Open Vocabulary Scene Graph
        121479, -- external MambaSIC: Mamba-based Stereo Image Compression with Bi-directional Multi-re
        121503, -- external VLM4RSDet: Collaborative Optimization with Vision-Language Model for Enhanc
        121545, -- external MedFG-VQA: Low-Frequency Memory and Graph Attention for Lightweight Medical
        121553, -- external Generalizable Co-Salient Object Detection via Mixed Content-Style Modulatio
        121566, -- external Adaptive Anisotropic Gaussian Splatting for Multi-contrast MRI Arbitrary-Sc
        121585, -- 2512.13840 MoLingo: Motion-Language Alignment for Text-to-Human Motion Generation
        121636, -- external A Cross-view Fusion Framework for Robust 6-DoF Grasp Pose Estimation
        121681, -- external SynthRGB-T: Language-Vision Guided Image Translation for Diversity Synthesi
        121686, -- external SO(3)-Equivariant ViT-Adapter for Data-Efficient Zero-Shot Sim-to-Real Indo
        121732, -- external VDFE: Difference-Aware 3D Scene Editing with Non-Intrusive Video Diffusion
        121776, -- external BrepVGAE: Variational Graph Autoencoder with Unified Latent Representation
        121799, -- external NEAF: Natural Image Editing with Attention Fusion for Generalizable Test-ti
        121837, -- external MOFA-VTON: More Fashion Possibilities with Fine-Grained Adaptations in Virt
        121840, -- external HumanNOVA: Photorealistic, Universal and Rapid 3D Human Avatar Modeling fro
        121886, -- external NS-Diff: Fluid Navier-Stokes Guided Video Diffusion via Reinforcement Learn
        121909, -- 2511.19024 Life-IQA: Boosting Blind Image Quality Assessment through GCN-enhanced Laye
        122102, -- 2609.23658 Why Do Video Diffusion Models Violate Physics? Unveiling the Flaws in Atten
        122178, -- 2609.27901 All modalities are equal, but video is more equal: Closing the Cross-Attent
        122555, -- 2609.37200 Adaptive Reward Routing: Dynamic Multi-Reward Optimization for Joint Audio-
        122683, -- 2610.03695 Language Models that Play Chess and Explain Their Moves
        122709, -- 2610.05416 Prism: Dynamic Sparse Attention for Native 2K Joint Video-Audio Generation
        122714, -- 2610.05608 Kandinsky 6.0 Video: Foundation Models for Synchronized Video and Audio Gen
        122916, -- 2610.04722 NAMVIS: Next-Scale Autoregressive Multi-View Image Synthesis
        123148, -- 2606.26493 Nemotron-Labs-TwoTower: Diffusion Language Modeling with Pretrained Autoreg
        123427, -- 2610.02638 Batched Speech Decisions Without Decoding: Single-Token Supervision Lets a
        123605, -- 2610.22371 Gen4P: Video Generators are 4D Perceivers
        123702, -- 2610.21467 DuET: Note-Frame Dual Encoding for Piano Performance-to-Score Transcription
        123706, -- 2610.14746 BridgeWAM: Bridging Video and Action Experts via Latent Bridge Queries
        123891, -- 2610.28632 Joints, Camera, Action! Co-Generating 3D Motion and Video for Arbitrary Rig
        123973, -- 2409.13568 Tackling fluffy clouds: robust agricultural field boundary delineation from
        124033, -- 2610.25100 Deep Fusion Memory: A Chunk-Level Parametric Memory for Large Language Mode
        124070, -- 2610.22951 MambaAct: Efficient Mamba Action Experts for Flow-Matching Vision-Language-
        124132, -- external GRNAgent: A Multimodal Graph Reasoning Agent for Gene Regulatory Network In
        124203, -- external FoundSurface: Feedforward Ray-Based 3D Scene Surface Reconstruction from Un
        124253, -- 2608.13938 CoANeRV: Coordinate-Aware Token-Space Neural Video Representation
        124284, -- external $\text{PartConcepts}$: A Unified Mechanism for Fine-Grained Part Localizati
        124363, -- external STParOpt: An End-to-End Framework for Execution-Aware Parallelism Inference
        124375, -- 2610.03068 Where to Look Is Not How to Fix: Pre-Denoising Diagnostics and Modality-Dep
        124421, -- external Remembering What Matters: From Markovian to Subtask-Causal Memory in VLA Po
        124490, -- 2610.16330 BAT3R: Robust Online 3D Reconstruction with Bayesian Adaptive State Updates
        124663, -- external CondenseVLA: Learnable History Condensation for Efficient Multi-Frame VLA
        124773, -- external Learning Neuronal Wiring Rules from Morphological Token Sequences
        124904, -- external SAX: Advancing Video Diffusion Models for Sequential Action Execution
        124931, -- external eSAM: Editing SAM3 Attention for Training-Free Referring Segmentation
        125063, -- 2604.18215 Memorize When Needed: Decoupled Memory Control for Spatially Consistent Lon
        125180, -- 2610.11105 TKCAM: Text and Keyframe to Camera Trajectory Generation
        125341, -- external Full-Duplex Speech-Motion Model for Dyadic Interaction
        125486, -- 2605.29850 MIRAGE: Adaptive Multimodal Gating for Whole-Brain fMRI Encoding
        125634, -- 2605.06127 Continuous Expert Assembly: Instance-Conditioned Low-Rank Residuals for All
        125732, -- external Tokenization and Architecture Jointly Allocate Component Roles in Time Seri
        125737, -- 2605.21061 Grounding Driving VLA via Inverse Kinematics
        125743, -- 2610.13687 X-AVDD: Cross-Attentive Audio-Visual Dataset Distillation
        125819, -- 2609.36429 Towards Scalable Context-Aware Single-Cell Spatial Transcriptomics Predicti
        125880, -- 2610.09118 TopoCurve: Geometry-Aware Topology Reasoning via Bézier Curves in Autonomou
        125956, -- external OpticalRAG: Pixel-Space Compression for Token-Efficient Retrieval-Augmented
        126177, -- 2605.19532 Boosting Text-to-Image Diffusion Models via Core Token Attention-Based Seed
        126194, -- 2605.25195 Baton: Explicit Semantic Blueprints for Joint Video-Audio Generation
        126196, -- external StableAvatar: Ultra-Long Audio-Driven Avatar Video Generation
        126199, -- external Training-Free 3D Editing via Feature-Divergence Localization and Trajectory
        126283, -- external Cross-Attentive Bayesian Low-Rank Adaptation for Multimodal Uncertainty Est
        126374, -- external Unbounded Streaming Text-To-Speech with Prefixed Sliding Window Attention
        126635, -- external Directional Noise Conditioning for Diffusion Models
        126817, -- 2606.29845 Bricker to BRACE: A Bracket Exposure RAW Dataset and Restoration Model for
        126917, -- 2605.09701 DriveFuture: Future-Aware Latent World Models for Autonomous Driving
        127085, -- external Learning Preference Representations for Preference-Conditioned Image Genera
        127160, -- external HandXFM: Semantic-Structural Distillation for Hand Radiograph Foundation Mo
        127165, -- external WovenAnchor Matcher: Specialized Intra- and Inter-Image Context Modeling fo
        127236, -- external Programmatic Reasoning with Structural Schema: A Unified Framework for Mult
        127258, -- 2610.05587 Generating the Wild: Individual-Consistent Image-to-Video Generation for Wi
        127290, -- external 3D Consistency Tokens
        127335, -- external MENDR: Manifold-Embedded Neural Data Representations for Channel-Agnostic E
        127337, -- external Beyond Feature Disruption: Boundary-Diverting Unlearnable Examples against
        127399, -- 2607.01128 GAIA: Geometry-Adaptive Operator Learning for Forward and Inverse Problems
        127462, -- external Scaling Neural Motor Decoding via Decoupled Behavioral Pretraining
        127551, -- 2608.01298 UDT: Reconciling U-Nets and Diffusion Transformers with Data-Adaptive Token
        127607, -- external Scaling Optimization-Oriented Hypernetworks for Implicit Neural Representat
        127622, -- external Attention-based Routing for Interpretable Multimodal Brain Encoding
        127755, -- external Iris: Empowering Video MLLMs with High-Frequency Pose Priors via Spatiotemp
        127782, -- 2609.24298 KV-COBRA: KV Cache Compression via Co-Optimized Bit-Rank Allocation
        127801, -- 2509.24302 LEAF: Language-EEG Aligned Foundation Model for Brain-Computer Interfaces
        128072, -- external Beyond Real or Fake: A Dual-Channel Authenticity and Reasoning Protocol for
        128077, -- external FreeOcc: Decoupling Ego-Motion for Efficient 4D Occupancy Forecasting via C
        128379, -- external In-Context Learning for Remote Sensing Vision: A Semantic-Aware Rotation-Ro
        128547, -- 2610.01891 RipplePLM: Structural and Property Decoupling for Protein Mutation Effect G
        128751, -- external MemPilot: Learning Transferable Latent Memory Mechanisms for LLM Reasoning
        128824, -- external SOLA: A Structured Operator Library for Attention in Pretrained Vision Tran
        128855, -- 2609.35704 DynaTokens: Teaching Dynamics to Camera-Controlled Video Models at Test Tim
        128996, -- 2607.02148 SAMoR: Motion Modelling for Articulated Objects of Any Skeleton and Topolog
        129418, -- external SafePro: Generation of Safe and Functional Proteins via Cross-Task Conflict
        129761, -- 2605.10079 SocialDirector: Training-Free Social Interaction Control for Multi-Person V
        129769, -- external Attention Heads are Complementary Visual Units: Mitigating Hallucinations i
        129848, -- external Pathway-Aligned Regulator Tokens for Interpretable Spatial Gene Expression
        129894, -- external Diff-Kalman: Difference-Driven Learning for Structure-Preserving Kalman Fil
        130074, -- external Overcoming Attention Distraction: Training-Free Latent Communication for Mu
        130097, -- 2605.11015 DCVD: Dual-Channel Cross-Modal Fusion for Joint Vulnerability Detection and
        130142, -- 2610.13334 PDE-PFN: Prior-Data Fitted Neural PDE Solver
        130580, -- 2610.17233 Beyond Sparse Captions: Aligning Slide-Level Text and Patch-Level Vision in
        130605, -- external Direct Conditioning of Audio Diffusion Transformers on fMRI Reveals Cortica
        130861, -- 2609.30667 StarWM: Self-Supervised Trained Attention Routing for Robust World Models
        130975, -- external Cross-Distribution Generalization in Longitudinal Behavioral Data Through F
        130997, -- 2606.13768 CineOrchestra: Unified Entity-Centric Conditioning for Cinematic Video Gene
        131075, -- external When, Where, What: Structural Guarantees for Travel Time Prediction on Temp
        131093, -- 2608.11676 XBRIDGE: Entity-Grounded Latent Bridge for Heterogeneous LLM Communication
        131096, -- external Localizing and Repairing Sparse-Prompt Failure in SAM Decoders via Box-to-P
        131168, -- 2607.01108 NPUsper: Eliminating Redundant Computation for Real-Time Whisper on Mobile
        131193, -- external KerONet: A Single Softmax Readout Suffices for Physics-Informed Operator Le
        131213, -- external DOME: Drift-Adaptive On-Policy Motion Erasure in Video Diffusion Transforme
        131989  -- 2611.09055 OmniLatent: Unified Latent for 3D Part Modeling
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
        29237, -- 2403.14183 OTSeg: Multi-prompt Sinkhorn Attention for Zero-Shot Semantic Segmentation
        41072, -- 2412.04448 MEMO: Memory-Guided Diffusion for Expressive Talking Video Generation
        41931, -- 2412.15213 Flowing from Words to Pixels: A Framework for Cross-Modality Evolution
        67423, -- 2509.24980 SDPose: Exploiting Diffusion Priors for Out-of-Domain and Robust Pose Estim
        84381, -- 2512.10943 AlcheMinT: Fine-grained Temporal Control for Multi-Reference Consistent Vid
        85536, -- 2605.09622 Any2Any 3D Diffusion Models with Knowledge Transfer: A Radiotherapy Plannin
        90692, -- 2503.10149 Unlocking Generalization Power in LiDAR Point Cloud Registration
        116982, -- 2404.00973 Language-aware Visual Semantic Distillation for Video Question Answering
        117683  -- 2607.24436 MSVS-VAE: Multi-Scale Anchored VecSet for High-Fidelity 3D Reconstruction
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
