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
    'Image Captioning',
    'image-captioning',
    'Image captioning generates a natural-language description of an image, from a single sentence summarizing the scene to dense, region-level or paragraph-length captions. Models pair a visual encoder with a language decoder, today usually a vision-language model, and are evaluated against human reference captions with metrics such as CIDEr, BLEU, METEOR, and SPICE on benchmarks like COCO Captions and NoCaps. It is a core part of [Image Understanding](/tasks/image-understanding) and supplies training data for [Image Generation](/tasks/image-generation).',
    'image captioning, image caption generation, caption generation, dense captioning, image description generation, image paragraph captioning, novel object captioning, zero-shot image captioning',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Show and Tell: A Neural Image Caption Generator](/paper/1411.4555)',
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
