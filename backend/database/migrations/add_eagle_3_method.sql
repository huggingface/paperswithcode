INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES (
    'eagle-3',
    'EAGLE-3',
    'EAGLE-3',
    'EAGLE-3 is a [speculative decoding](/methods/speculative-decoding) method that directly predicts draft tokens from a fusion of lower-, middle-, and upper-layer target-model features. Its training-time test procedure exposes the drafter to its own predictions during training, improving draft quality as training data scales.',
    'EAGLE-3, EAGLE 3, training-time test, multi-layer feature fusion, speculative decoding, draft model',
    (SELECT id FROM areas WHERE name IN ('Language', 'Natural Language Processing')
     ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END LIMIT 1),
    2025,
    (SELECT id FROM papers WHERE arxiv_id = '2503.01840'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'EAGLE-3: Scaling up Inference Acceleration of Large Language Models via Training-Time Test',
    'https://github.com/SafeAILab/EAGLE',
    NULL,
    'User-provided comparison graphic'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'eagle-3' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
