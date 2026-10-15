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
    'Hyperspectral Image Classification',
    'hyperspectral-image-classification',
    'Hyperspectral image classification assigns a land-cover or material label to each pixel of a hyperspectral image, which records hundreds of narrow spectral bands. Methods combine spectral and spatial cues with CNNs, Transformers, and graph networks and must cope with scarce labels and high dimensionality; results are reported as overall accuracy, average accuracy, and kappa on scenes such as Indian Pines, Pavia University, and Houston. It is related to [Remote Sensing](/tasks/remote-sensing) and [Earth Observation](/tasks/earth-observation).',
    'hyperspectral image classification, hyperspectral classification, hyperspectral imagery classification, hyperspectral pixel classification, HSI classification, spectral-spatial classification',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[SpectralFormer: Rethinking Hyperspectral Image Classification with Transformers](/paper/2107.02988)',
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
