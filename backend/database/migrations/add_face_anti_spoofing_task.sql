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
    'Face Anti-Spoofing',
    'face-anti-spoofing',
    'Face anti-spoofing, also called face presentation attack detection, decides whether a face shown to a camera is live or a spoof such as a printed photo, a screen replay, or a 3D mask. It protects [Face Recognition](/tasks/face-recognition) systems and is evaluated with APCER, BPCER, ACER, HTER, and AUC under intra- and cross-dataset protocols on benchmarks such as OULU-NPU, SiW, CASIA-SURF, and CelebA-Spoof. It is related to [Deepfake Detection](/tasks/deepfake-detection).',
    'face anti-spoofing, face anti spoofing, face antispoofing, face presentation attack detection, presentation attack detection, face liveness detection, liveness detection, face spoofing detection, face spoof detection',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Searching Central Difference Convolutional Networks for Face Anti-Spoofing](/paper/2003.04092)',
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
