INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES (
    'medusa',
    'Medusa',
    'Medusa',
    'Medusa accelerates large language model inference by adding lightweight decoding heads that predict several future tokens in parallel. It organizes those predictions into candidate continuations that the target model verifies together with tree-based attention, avoiding a separate [speculative decoding](/methods/speculative-decoding) draft model.',
    'Medusa, multiple decoding heads, tree attention, speculative decoding, LLM inference acceleration',
    (SELECT id FROM areas WHERE name IN ('Language', 'Natural Language Processing')
     ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END LIMIT 1),
    2024,
    (SELECT id FROM papers WHERE arxiv_id = '2401.10774'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Medusa: Simple LLM Inference Acceleration Framework with Multiple Decoding Heads',
    'https://github.com/FasterDecoding/Medusa',
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
WHERE slug = 'medusa' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
