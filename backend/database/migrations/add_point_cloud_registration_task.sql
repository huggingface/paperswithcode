-- Added 2026-10-20 because production chat users looked it up with
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
    'Point Cloud Registration',
    'point-cloud-registration',
    'Point cloud registration estimates the rigid transformation (rotation and translation) that aligns two partially overlapping 3D scans of the same scene or object. Classic pipelines match hand-crafted descriptors such as FPFH, estimate a pose with [RANSAC](/methods/ransac) and refine it with [Iterative Closest Point](/methods/iterative-closest-point); learned methods predict correspondences or transformations end to end and handle low overlap. Benchmarks such as 3DMatch, 3DLoMatch and KITTI odometry report registration recall and rotation and translation errors. Registration underpins [3D reconstruction](/tasks/3d-reconstruction), SLAM, and LiDAR localization for [autonomous driving](/tasks/autonomous-driving).',
    'point cloud registration, point-cloud registration, point set registration, 3d point cloud registration, LiDAR scan matching, scan matching',
    (SELECT area_id FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    NULL,
    '[Geometric Transformer for Fast and Robust Point Cloud Registration](https://arxiv.org/abs/2202.06688)',
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
