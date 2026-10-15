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
    'Depth Completion',
    'depth-completion',
    'Depth completion predicts a dense depth map from sparse depth measurements, typically from LiDAR or a low-resolution depth sensor, usually guided by an aligned RGB image. It underpins perception for autonomous driving and robotics and is evaluated with RMSE and MAE on KITTI depth completion and NYU-Depth v2. It is a subtask of [Depth Estimation](/tasks/depth-estimation).',
    'depth completion, sparse depth completion, LiDAR depth completion, guided depth completion, image-guided depth completion, depth densification, sparse-to-dense depth',
    (SELECT area_id FROM tasks WHERE slug = 'depth-estimation' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'depth-estimation' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'depth-estimation' LIMIT 1),
    NULL,
    '[Sparse-to-Dense: Depth Prediction from Sparse Depth Samples and a Single Image](/paper/1709.07492)',
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
