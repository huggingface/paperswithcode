-- Added 2026-10-21 because production chat users looked it up with
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
    'Style Transfer',
    'style-transfer',
    'Style transfer renders a content image in the artistic style of a reference image, such as a painting, while preserving the content''s structure. Neural style transfer matches Gram-matrix statistics of CNN features, and later work adds feed-forward networks, arbitrary-style models based on adaptive instance normalization, photorealistic and video variants, and diffusion-based stylization. It is a classic [image generation](/tasks/image-generation) problem, closely related to [image-to-image translation](/tasks/image-to-image-translation).',
    'neural style transfer, image style transfer, artistic style transfer, arbitrary style transfer, photorealistic style transfer, video style transfer, painterly style transfer, style transfer for images, fast style transfer, universal style transfer, diffusion style transfer',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[A Neural Algorithm of Artistic Style](/paper/1508.06576)',
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
