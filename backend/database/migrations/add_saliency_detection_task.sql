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
    'Saliency Detection',
    'saliency-detection',
    'Saliency detection identifies the most visually distinctive regions of an image. Salient object detection segments the objects that draw attention as a pixel-wise mask, including RGB-D, video, and co-salient variants, while saliency prediction estimates human eye-fixation maps. Results are reported with MAE, F-measure, S-measure, and E-measure on benchmarks such as DUTS, DUT-OMRON, and ECSSD. It is related to [Image Segmentation](/tasks/image-segmentation) and [Camouflaged Object Detection](/tasks/camouflaged-object-detection).',
    'saliency detection, salient object detection, salient object segmentation, RGB-D salient object detection, co-salient object detection, video salient object detection, saliency prediction, visual saliency prediction, eye fixation prediction',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[U2-Net: Going Deeper with Nested U-Structure for Salient Object Detection](/paper/2005.09007)',
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
