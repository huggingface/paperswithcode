-- Skeleton-based Action Recognition task: subtask of action-recognition.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Skeleton-based Action Recognition',
    'skeleton-based-action-recognition',
    'Skeleton-based action recognition classifies human actions from sequences of 2D or 3D body-joint coordinates rather than raw RGB frames. Skeletons, captured by depth sensors or estimated with [Pose Estimation](/tasks/pose-estimation), are compact and robust to changes in appearance, lighting and background; models such as spatial-temporal graph convolutional networks treat joints as graph nodes connected across space and time. It is a subtask of [Action Recognition](/tasks/action-recognition), commonly evaluated on NTU RGB+D, NTU RGB+D 120 and Kinetics-Skeleton.',
    'skeleton-based action recognition, skeleton based action recognition, skeleton action recognition, skeleton-based human action recognition, skeleton-based activity recognition, 3d skeleton action recognition, NTU RGB+D',
    (SELECT area_id FROM tasks WHERE slug = 'action-recognition' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'action-recognition' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'action-recognition' LIMIT 1),
    true,
    NULL,
    '[Spatial Temporal Graph Convolutional Networks for Skeleton-Based Action Recognition](/paper/1801.07455)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
