-- Add AdEMAMix method, introduced in arXiv 2409.03137. The source paper
-- gets the source evidence row (Introduced banner); citers are linked by
-- link_papers_by_source_citations.py and the hourly reference backfill.

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'ademamix',
    'AdEMAMix',
    'AdEMAMix',
    'AdEMAMix is a modification of the [Adam](/methods/adam) optimizer that keeps a mixture of two exponential moving averages (EMAs) of past gradients instead of one. A fast EMA, as in Adam, reacts to recent gradients, while a second, very slow EMA (decay close to 0.9999) retains information from gradients tens of thousands of steps old; the update adds the slow momentum, scaled by a coefficient, to the fast one, and warm-up schedulers for the slow decay and its coefficient keep early training stable. The paper shows that old gradients remain useful for long training runs: a 1.3B-parameter language model trained with AdEMAMix on 101B tokens performed comparably to an [AdamW](/methods/adamw) model trained on 197B tokens, and models trained with AdEMAMix also forget the training data more slowly.',
    'AdEMAMix',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2024,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2409.03137'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'The AdEMAMix Optimizer: Better, Faster, Older',
    'https://github.com/apple/ml-ademamix',
    NULL,
    '[The AdEMAMix Optimizer: Better, Faster, Older](/paper/2409.03137)'
)
ON CONFLICT (slug) DO UPDATE
SET
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
SELECT source_paper_id, id
FROM methods
WHERE slug = 'ademamix'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'ademamix'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
