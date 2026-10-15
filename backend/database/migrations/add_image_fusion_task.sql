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
    'Image Fusion',
    'image-fusion',
    'Image fusion combines complementary information from several source images of the same scene into a single, more informative image. Common settings are infrared and visible fusion, multi-focus and multi-exposure fusion, medical fusion of modalities such as MRI, CT, and PET, and pansharpening of satellite imagery. Methods use autoencoders, GANs, Transformers, and diffusion models and are evaluated with metrics such as entropy, SSIM, mutual information, and VIF. It is related to [Medical Imaging](/tasks/medical-imaging) and [Remote Sensing](/tasks/remote-sensing).',
    'image fusion, infrared and visible image fusion, infrared-visible image fusion, visible and infrared image fusion, multi-focus image fusion, multi-exposure image fusion, medical image fusion, multi-modality image fusion, multimodal image fusion, pansharpening, pan-sharpening',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[CDDFuse: Correlation-Driven Dual-Branch Feature Decomposition for Multi-Modality Image Fusion](/paper/2211.14461)',
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
