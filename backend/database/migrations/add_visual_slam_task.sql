INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Visual SLAM',
    'visual-slam',
    'Visual simultaneous localization and mapping (SLAM) tracks a camera''s trajectory through a video while building a map of the scene it moves through. Inputs are monocular, stereo or RGB-D frames, sometimes with inertial measurements; outputs are per-frame camera poses and a sparse, dense or Gaussian-splat map. The field spans classic feature-based and direct systems, learned visual odometry, dense and neural SLAM, and streaming feed-forward reconstruction models that predict poses for long videos. Systems are usually compared by absolute trajectory error (ATE) on sequences such as TUM RGB-D, 7-Scenes, EuRoC and KITTI Odometry. Related: [Camera Pose Estimation](/tasks/camera-pose-estimation) and [3D Reconstruction](/tasks/3d-reconstruction).',
    'visual slam, visual simultaneous localization and mapping, visual simultaneous localisation and mapping, monocular slam, rgb-d slam, stereo slam, dense slam, neural slam, gaussian splatting slam, visual odometry, monocular visual odometry, visual-inertial odometry, VIO, visual-inertial slam, streaming 3d reconstruction, long-sequence 3d reconstruction, absolute trajectory error',
    (SELECT area_id FROM tasks WHERE slug = 'camera-pose-estimation' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'camera-pose-estimation' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'camera-pose-estimation' LIMIT 1),
    NULL,
    '[MASt3R-SLAM: Real-Time Dense SLAM with 3D Reconstruction Priors](/paper/2412.12392)',
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
