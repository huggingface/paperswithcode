-- Chat lookup-miss taxonomy gap fill (2026-11-11 audit): tasks.
-- Hero images are imported separately with import_entity_image.py.

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Few-Shot Image Classification',
    'few-shot-image-classification',
    'Few-shot image classification recognizes new image categories from only a handful of labeled examples per class, typically evaluated in N-way K-shot episodes. Approaches include metric learning (prototypical and matching networks), meta-learning of fast-adapting initializations, transductive inference, and, more recently, adapting large pretrained vision or vision-language backbones with prompts or lightweight heads. Common benchmarks are miniImageNet, tieredImageNet, CIFAR-FS, and Meta-Dataset. Related: [Image Classification](/tasks/image-classification), [Few-Shot Object Detection](/tasks/few-shot-object-detection), [Few-Shot Segmentation](/tasks/few-shot-segmentation).',
    'few-shot image classification, few-shot image recognition, few-shot visual recognition, few-shot visual classification, few-shot classification of images, cross-domain few-shot classification, cross-domain few-shot learning',
    (SELECT area_id FROM tasks WHERE slug = 'image-classification'),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-classification'),
    (SELECT id FROM tasks WHERE slug = 'image-classification')
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Long-Tailed Recognition',
    'long-tailed-recognition',
    'Long-tailed recognition trains classifiers on data where a few head classes have many examples and most tail classes have very few, then evaluates on a balanced test set. Methods re-sample or re-weight the training data, adjust logits or margins by class frequency, decouple representation and classifier learning, or combine experts and pretrained models to recover tail-class accuracy. Standard benchmarks are ImageNet-LT, CIFAR-100-LT, iNaturalist, and Places-LT. Related: [Image Classification](/tasks/image-classification).',
    'long-tailed recognition, long-tailed visual recognition, long-tailed image classification, long-tailed classification, long-tail recognition, long-tail classification, long-tailed learning, imbalanced image classification',
    (SELECT area_id FROM tasks WHERE slug = 'image-classification'),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-classification'),
    (SELECT id FROM tasks WHERE slug = 'image-classification')
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Label Distribution Learning',
    'label-distribution-learning',
    'Label distribution learning (LDL) assigns each instance a distribution over labels that describes how much each label applies, rather than a single label or a binary label set. It suits ambiguous targets such as facial age, emotion intensity, and crowd opinions. Methods learn to predict the full distribution with KL-divergence or similar losses, and label enhancement recovers distributions from ordinary logical labels. Related: [Multi-Label Image Classification](/tasks/multi-label-image-classification).',
    'label distribution learning, label distribution prediction, deep label distribution learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Line Segment Detection',
    'line-segment-detection',
    'Line segment detection finds straight line segments in an image and returns their endpoints. Classic detectors group image gradients, while learned methods predict junctions and line attraction fields or regress segments directly with transformers. Wireframe parsing extends the output to a graph of junctions and lines, which supports 3D reconstruction, SLAM, and camera calibration in man-made scenes. Common benchmarks are Wireframe and YorkUrban. Related: [Object Detection](/tasks/object-detection), [Camera Pose Estimation](/tasks/camera-pose-estimation).',
    'line segment detection, line segment detector, wireframe parsing, wireframe detection, line detection and description, junction and line detection',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Gesture Recognition',
    'gesture-recognition',
    'Gesture recognition classifies hand or body gestures from images, video, depth, skeleton, or wearable-sensor signals. Static recognition labels a single hand pose, while dynamic recognition detects and classifies gestures over time in continuous streams, often under tight latency limits for human-computer interaction, automotive, and AR/VR interfaces. Benchmarks include Jester, EgoGesture, NVGesture, and IPN Hand. Related: [Action Recognition](/tasks/action-recognition), [Sign Language Recognition](/tasks/sign-language-recognition), [Pose Estimation](/tasks/pose-estimation).',
    'gesture recognition, hand gesture recognition, dynamic gesture recognition, dynamic hand gesture recognition, static gesture recognition, gesture classification, hand gesture classification',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Watermark Removal',
    'watermark-removal',
    'Watermark removal erases a watermark from an image while preserving its content. For visible watermarks, such as semi-transparent logos or text, models locate the mark and reconstruct the pixels beneath it. For invisible watermarks embedded by image generators or provenance schemes, removal attacks such as regeneration, purification, or adversarial perturbation test how robust the watermark is, which drives the design of watermarks that survive them. Related: [Image Restoration](/tasks/image-restoration), [Image Inpainting](/tasks/image-inpainting), [Image Forgery Detection](/tasks/image-forgery-detection).',
    'watermark removal, visible watermark removal, image watermark removal, blind watermark removal, watermark removal attack',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Animal Re-Identification',
    'animal-re-identification',
    'Animal re-identification recognizes the same individual animal across images or videos taken at different times or by different cameras, from features such as coat patterns, fins, faces, or body shape. It supports wildlife population monitoring, behavior studies, and livestock management, where labeled identities are few and new individuals appear constantly. Methods adapt metric learning from person re-identification and increasingly use foundation-model features shared across species. Related: [Person Re-Identification](/tasks/person-re-identification).',
    'animal re-identification, animal reidentification, animal re-id, wildlife re-identification, individual animal identification, animal individual identification, cattle re-identification',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Motion Magnification',
    'motion-magnification',
    'Motion magnification amplifies tiny, often invisible motions in a video, such as a pulse, breathing, or structural vibration, so they become visible while the rest of the scene stays intact. Eulerian methods filter pixel or phase variations over time in selected frequency bands, while learned methods train networks to magnify motion with fewer artifacts and less noise. Applications include non-contact vital-sign sensing and structural health monitoring. Related: [Video Editing](/tasks/video-editing), [Video Understanding](/tasks/video-understanding).',
    'motion magnification, video motion magnification, Eulerian video magnification, video magnification, phase-based motion magnification, learning-based motion magnification',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

-- "face tracking" lookups resolve to object tracking.
UPDATE tasks
SET keywords = keywords || ', face tracking',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'object-tracking'
  AND keywords NOT ILIKE '%face tracking%';
