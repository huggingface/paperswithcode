-- Add the GPT-6 Astra model-family method, sourced from OpenAI's release page
-- (external paper 114045). Idempotent: re-running refreshes the metadata.
INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES (
    'gpt-6-astra',
    'GPT-6 Astra',
    'GPT-6 Astra',
    'GPT-6 Astra is OpenAI''s general-purpose frontier model released in September 2026, the successor to [GPT-5](/methods/gpt-5) in its series of generative pre-trained [Transformer](/methods/transformer) foundation models. The release targets computer use, professional workflows, software engineering, scientific reasoning, and cybersecurity, with improvements in long-running task execution, context management, and alignment with user intent. Although the launch did not mention robotics, Astra has quickly been used to control robots in two ways: directly as a robot policy that outputs actions from camera observations, and as an agent that plans, writes code, and calls tools or lower-level policies.',
    'GPT-6 Astra, GPT-6, GPT6, Astra',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2026,
    (SELECT id FROM papers WHERE id = 114045 AND source = 'external'),
    NULL,
    'GPT-6 Astra: A new generation of intelligence',
    NULL,
    '/api/thumbnails/custom/paper_114045_source_art_fa07671f40bf.jpg?fit=fit9',
    '[GPT-6 Astra: A new generation of intelligence](/paper/114045)'
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
WHERE slug = 'gpt-6-astra' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
