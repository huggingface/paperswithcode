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
    'Scene Text Detection',
    'scene-text-detection',
    'Scene text detection localizes text instances in natural images, including horizontal, multi-oriented, curved, and arbitrarily shaped text, as quadrilaterals or polygons. It is the first stage of reading text in the wild, followed by [Scene Text Recognition](/tasks/scene-text-recognition), and end-to-end text spotting combines both. Methods adapt [Object Detection](/tasks/object-detection) and segmentation and are evaluated with precision, recall, and H-mean on ICDAR 2015, Total-Text, and CTW1500.',
    'scene text detection, text detection in natural images, text detection in the wild, arbitrary-shaped text detection, arbitrary-shape text detection, curved text detection, multi-oriented text detection, scene text spotting, end-to-end text spotting',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Character Region Awareness for Text Detection](/paper/1904.01941)',
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
