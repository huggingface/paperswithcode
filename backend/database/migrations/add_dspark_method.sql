INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES (
    'dspark',
    'DSpark',
    'DSpark',
    'DSpark combines block-parallel diffusion drafting with a lightweight sequential module so draft tokens retain intra-block dependencies. Its confidence-scheduled verification adapts the verified prefix length to predicted survival probabilities and serving load, reducing wasted target-model work in high-concurrency [speculative decoding](/methods/speculative-decoding).',
    'DSpark, confidence-scheduled speculative decoding, semi-autoregressive generation, parallel drafting, diffusion language model',
    (SELECT id FROM areas WHERE name IN ('Language', 'Natural Language Processing')
     ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END LIMIT 1),
    2026,
    (SELECT id FROM papers WHERE arxiv_id = '2607.05147'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'DSpark: Confidence-Scheduled Speculative Decoding with Semi-Autoregressive Generation',
    NULL,
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
WHERE slug = 'dspark' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
