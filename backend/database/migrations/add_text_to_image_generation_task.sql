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
    'Text-to-Image Generation',
    'text-to-image-generation',
    'Text-to-image generation synthesizes an image that matches a natural-language prompt. Modern systems are mostly diffusion or flow models conditioned on a text encoder, often trained in a compressed latent space, and they are evaluated on prompt faithfulness, compositional accuracy and aesthetic quality. It is the most prominent conditional form of [image generation](/tasks/image-generation), with related [image editing](/tasks/image-editing) and [video generation](/tasks/video-generation) variants.',
    'text-to-image generation, text-to-image synthesis, text-to-image, text to image, text-to-image diffusion, text-to-image model, text-guided image generation, text-conditioned image generation, T2I generation, prompt-to-image',
    (SELECT area_id FROM tasks WHERE slug = 'image-generation' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-generation' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'image-generation' LIMIT 1),
    NULL,
    '[High-Resolution Image Synthesis with Latent Diffusion Models](/paper/2112.10752)',
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
