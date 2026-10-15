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
    'Image Retrieval',
    'image-retrieval',
    'Image retrieval ranks a database of images by relevance to a query, which may be an image, a sketch, text, or an image plus a modification text. Content-based and instance-level retrieval find images of the same object or landmark using global and local descriptors with re-ranking, and are evaluated with mAP and Recall@K on benchmarks such as Revisited Oxford and Paris and Google Landmarks. It is closely related to [Visual Place Recognition](/tasks/visual-place-recognition) and [Embedding Models](/tasks/embedding-models).',
    'image retrieval, content-based image retrieval, CBIR, instance retrieval, instance-level image retrieval, landmark retrieval, sketch-based image retrieval, composed image retrieval, image search',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Revisiting Oxford and Paris: Large-Scale Image Retrieval Benchmarking](/paper/1803.11285)',
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
