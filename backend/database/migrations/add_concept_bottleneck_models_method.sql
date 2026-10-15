-- Add Concept Bottleneck Models method, introduced in arXiv 2007.04612. The source paper
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
    'concept-bottleneck-models',
    'Concept Bottleneck Models',
    'Concept Bottleneck Models (CBM)',
    'Concept Bottleneck Models (CBMs) are interpretable predictors that first map the input to a set of human-specified concepts, such as "wing color" for birds or "bone spurs" for knee X-rays, and then predict the target label only from those concepts. Training uses concept annotations and can be independent, sequential or joint. Because the label depends on the input only through the concept layer, users can inspect the predicted concepts and intervene at test time by correcting them, which can substantially improve accuracy. On knee osteoarthritis grading and CUB bird classification, CBMs matched end-to-end models in accuracy while enabling these explanations and interventions. Later work extended them to label-free concepts derived from [CLIP](/methods/clip) or language models and to concept embeddings.',
    'concept bottleneck model, concept bottleneck',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2020,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2007.04612'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Concept Bottleneck Models',
    'https://github.com/yewsiang/ConceptBottleneck',
    NULL,
    '[Concept Bottleneck Models](/paper/2007.04612)'
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
WHERE slug = 'concept-bottleneck-models'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'concept-bottleneck-models'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
