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
    'Crowd Counting',
    'crowd-counting',
    'Crowd counting estimates the number of people in an image or video of a crowd, often by regressing a density map whose integral gives the count or by localizing individual heads. Dense, occluded, and perspective-distorted scenes make it challenging, and methods are evaluated with MAE and MSE on ShanghaiTech, UCF-QNRF, JHU-Crowd++, and NWPU-Crowd. It is a subtask of [Object Counting](/tasks/object-counting).',
    'crowd counting, crowd density estimation, dense crowd counting, crowd localization, people counting, crowd counting and localization',
    (SELECT area_id FROM tasks WHERE slug = 'object-counting' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'object-counting' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'object-counting' LIMIT 1),
    NULL,
    '[CSRNet: Dilated Convolutional Neural Networks for Understanding the Highly Congested Scenes](/paper/1802.10062)',
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
