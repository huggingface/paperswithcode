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
    'Handwritten Text Recognition',
    'handwritten-text-recognition',
    'Handwritten text recognition transcribes handwriting in scanned or photographed documents into machine-readable text, at the level of words, lines, paragraphs, or full pages. Modern systems use CNN, recurrent, and Transformer encoder-decoders trained with CTC or attention, and are evaluated with character and word error rates on datasets such as IAM, RIMES, and READ. It is a subtask of [OCR](/tasks/ocr) related to [Scene Text Recognition](/tasks/scene-text-recognition) and [Document Understanding](/tasks/document-understanding).',
    'handwritten text recognition, handwriting recognition, HTR, handwritten character recognition, handwritten word recognition, handwritten document recognition, offline handwriting recognition, online handwriting recognition, handwritten OCR',
    (SELECT area_id FROM tasks WHERE slug = 'ocr' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'ocr' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'ocr' LIMIT 1),
    NULL,
    '[DAN: a Segmentation-free Document Attention Network for Handwritten Document Recognition](/paper/2203.12273)',
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
