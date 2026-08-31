INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES (
    'dflash',
    'DFlash',
    'DFlash',
    'DFlash is a [speculative decoding](/methods/speculative-decoding) framework that uses a lightweight block diffusion model to draft multiple tokens in parallel in a single forward pass. It conditions the diffusion drafter on context features from the target model to improve proposal quality and acceptance rates.',
    'DFlash, block diffusion, flash speculative decoding, parallel drafting, diffusion language model',
    (SELECT id FROM areas WHERE name IN ('Language', 'Natural Language Processing')
     ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END LIMIT 1),
    2026,
    (SELECT id FROM papers WHERE arxiv_id = '2602.06036'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'DFlash: Block Diffusion for Flash Speculative Decoding',
    'https://github.com/z-lab/dflash',
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
WHERE slug = 'dflash' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
