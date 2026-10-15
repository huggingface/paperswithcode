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
    'Low-Light Image Enhancement',
    'low-light-image-enhancement',
    'Low-light image enhancement brightens images captured in poor illumination while suppressing noise, recovering color, and avoiding over-exposure. Methods range from Retinex-inspired decompositions and curve estimation to supervised, unsupervised, and diffusion-based restoration networks, and are evaluated with PSNR and SSIM on paired datasets such as LOL as well as no-reference quality metrics. It is a subtask of [Image Restoration](/tasks/image-restoration) related to [Image Denoising](/tasks/image-denoising).',
    'low-light image enhancement, low light image enhancement, low-light enhancement, LLIE, low-light image restoration, nighttime image enhancement, night image enhancement, underexposed image enhancement, retinex-based enhancement',
    (SELECT area_id FROM tasks WHERE slug = 'image-restoration' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-restoration' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'image-restoration' LIMIT 1),
    NULL,
    '[Zero-Reference Deep Curve Estimation for Low-Light Image Enhancement](/paper/2001.06826)',
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
