-- Document Image Rectification task: subtask of document-understanding.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Document Image Rectification',
    'document-image-rectification',
    'Document image rectification, also called document dewarping, removes geometric distortions such as curls, folds, perspective and page curvature from photos of documents taken with phone cameras, producing a flat, scanner-like image. Models typically predict a dense backward mapping or a control-point grid that unwarps the input, sometimes followed by illumination correction. Rectification substantially improves downstream [OCR](/tasks/ocr) and [Document Layout Analysis](/tasks/document-layout-analysis). Methods are evaluated on the DocUNet benchmark and DIR300 using MS-SSIM, local distortion (LD), and OCR edit distance or character error rate.',
    'document image rectification, document rectification, document dewarping, document image dewarping, document unwarping, document image unwarping, document geometric correction',
    (SELECT area_id FROM tasks WHERE slug = 'document-understanding' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'document-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'document-understanding' LIMIT 1),
    true,
    NULL,
    '[DocTr: Document Image Transformer for Geometric Unwarping and Illumination Correction](https://arxiv.org/abs/2110.12942)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
