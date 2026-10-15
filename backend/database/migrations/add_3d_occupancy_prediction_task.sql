-- 3D Occupancy Prediction task: subtask of 3d-understanding.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    '3D Occupancy Prediction',
    '3d-occupancy-prediction',
    '3D occupancy prediction estimates, for every voxel in the 3D space around a sensor rig, whether it is occupied and, in semantic occupancy prediction, which class occupies it, typically from surround-view cameras, LiDAR or both. Compared with the bounding boxes of [3D Object Detection](/tasks/3d-object-detection), a dense occupancy grid captures arbitrary shapes, unknown objects and free space, which makes it a key perception output for [Autonomous Driving](/tasks/autonomous-driving) and embodied agents. Benchmarks include Occ3D-nuScenes, Occ3D-Waymo, OpenOccupancy and SemanticKITTI semantic scene completion, scored with voxel mIoU or ray-based RayIoU. Related tasks include [3D semantic segmentation](/tasks/3d-semantic-segmentation) and [3D understanding](/tasks/3d-understanding).',
    '3d occupancy prediction, 3d semantic occupancy prediction, semantic occupancy prediction, occupancy prediction, 3d occupancy forecasting, occupancy forecasting, 3d semantic occupancy, semantic scene completion',
    (SELECT area_id FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = '3d-understanding' LIMIT 1),
    true,
    NULL,
    '[Occ3D: A Large-Scale 3D Occupancy Prediction Benchmark for Autonomous Driving](/paper/2304.14365)',
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
