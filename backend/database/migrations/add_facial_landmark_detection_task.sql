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
    'Facial Landmark Detection',
    'facial-landmark-detection',
    'Facial landmark detection, also called face alignment, localizes a fixed set of semantic keypoints on a face image, such as the eye corners, nose tip, mouth contour and jawline (typically 68 or 98 points). Methods regress coordinates directly or predict per-landmark heatmaps, and must stay robust to large pose, occlusion, expression and blur. Results are reported as normalized mean error (NME), failure rate and AUC on 300W, WFLW, COFW and AFLW. Landmarks feed [face recognition](/tasks/face-recognition), [head pose estimation](/tasks/head-pose-estimation), expression analysis, face editing and talking-head generation.',
    'facial landmark detection, face landmark detection, facial landmark localization, facial landmark localisation, face landmark localization, facial keypoint detection, face keypoint detection, face alignment',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Look at Boundary: A Boundary-Aware Face Alignment Algorithm](https://arxiv.org/abs/1805.10483)',
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
