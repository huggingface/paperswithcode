INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    level,
    parent_id,
    image_url,
    image_credit,
    useful_leaderboards
)
VALUES (
    'Few-Shot Object Detection',
    'few-shot-object-detection',
    'Few-shot object detection learns to localize and classify novel object categories from only a handful of annotated examples per class, typically after training on abundant base classes. Approaches include fine-tuning, meta-learning, and transfer from large pretrained or open-vocabulary detectors, and results are reported as novel-class AP on PASCAL VOC and COCO splits with 1 to 30 shots. It is a subtask of [Object Detection](/tasks/object-detection).',
    'few-shot object detection, few shot object detection, FSOD, few-shot detection, low-shot object detection, incremental few-shot object detection, generalized few-shot object detection',
    (SELECT area_id FROM tasks WHERE slug = 'object-detection' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'object-detection' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'object-detection' LIMIT 1),
    NULL,
    '[Frustratingly Simple Few-Shot Object Detection](/paper/2003.06957)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
