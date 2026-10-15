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
    'Image-to-Image Translation',
    'image-to-image-translation',
    'Image-to-image translation maps an image from one domain to another while preserving its underlying structure, such as labels to photos, sketches to images, day to night, or one visual style to another. Methods learn from paired or unpaired data with conditional GANs, diffusion models, or flow-based models, and are evaluated with FID and task-specific fidelity measures. It is related to [Image Generation](/tasks/image-generation) and [Image Editing](/tasks/image-editing).',
    'image-to-image translation, image to image translation, unpaired image-to-image translation, unpaired image translation, multimodal image-to-image translation, conditional image translation, domain translation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Image-to-Image Translation with Conditional Adversarial Networks](/paper/1611.07004)',
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
