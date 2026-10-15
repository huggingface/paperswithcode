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
    '6D Pose Estimation',
    '6d-pose-estimation',
    '6D pose estimation recovers the 3D rotation and 3D translation of an object relative to the camera from an RGB or RGB-D image. Methods range from instance-level models trained on known CAD models to category-level and model-free approaches that generalize to unseen objects, and are typically evaluated with ADD(-S) and BOP average recall on datasets such as LINEMOD, YCB-Video, and the BOP benchmark. It is a subtask of [Pose Estimation](/tasks/pose-estimation) and a key capability for [Robotics](/tasks/robotics) grasping and augmented reality.',
    '6D pose estimation, 6D object pose estimation, 6D object pose, 6-DoF object pose estimation, 6DoF object pose estimation, 6-DoF object pose, object pose estimation, category-level object pose estimation, instance-level object pose estimation, model-free object pose estimation',
    (SELECT area_id FROM tasks WHERE slug = 'pose-estimation' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'pose-estimation' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'pose-estimation' LIMIT 1),
    NULL,
    '[PoseCNN: A Convolutional Neural Network for 6D Object Pose Estimation in Cluttered Scenes](/paper/1711.00199)',
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
