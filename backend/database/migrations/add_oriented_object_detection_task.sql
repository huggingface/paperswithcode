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
    'Oriented Object Detection',
    'oriented-object-detection',
    'Oriented object detection localizes objects with rotated bounding boxes that follow each object''s orientation instead of axis-aligned boxes. It is essential for densely packed, arbitrarily rotated objects in aerial and satellite imagery, scene text, and industrial inspection, and is commonly evaluated with mAP on DOTA, DIOR-R, and HRSC2016. It is a subtask of [Object Detection](/tasks/object-detection) closely tied to [Remote Sensing](/tasks/remote-sensing).',
    'oriented object detection, rotated object detection, arbitrary-oriented object detection, oriented bounding box detection, rotated bounding box, oriented bounding boxes, object detection in aerial images, aerial object detection',
    (SELECT area_id FROM tasks WHERE slug = 'object-detection' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'object-detection' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'object-detection' LIMIT 1),
    NULL,
    '[DOTA: A Large-scale Dataset for Object Detection in Aerial Images](/paper/1711.10398)',
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
