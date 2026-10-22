-- Added 2026-10-21 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

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
    'Instance Segmentation',
    'instance-segmentation',
    'Instance segmentation detects every object in an image and outputs a pixel-accurate mask for each individual instance, so two people standing side by side get two separate masks. It combines [object detection](/tasks/object-detection) with semantic labelling, and sits between semantic and panoptic [image segmentation](/tasks/image-segmentation). Standard benchmarks are COCO, LVIS and Cityscapes, evaluated with mask average precision (AP).',
    'instance segmentation, instance-level segmentation, object instance segmentation, real-time instance segmentation, open-vocabulary instance segmentation, instance mask prediction, instance masks',
    (SELECT area_id FROM tasks WHERE slug = 'image-segmentation' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-segmentation' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'image-segmentation' LIMIT 1),
    NULL,
    '[Mask R-CNN](/paper/1703.06870)',
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
