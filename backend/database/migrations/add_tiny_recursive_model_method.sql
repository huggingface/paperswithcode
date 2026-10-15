-- Add Tiny Recursive Model method, introduced in arXiv 2510.04871. The source paper
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
    'tiny-recursive-model',
    'Tiny Recursive Model',
    'Tiny Recursive Model (TRM)',
    'The Tiny Recursive Model (TRM) solves hard puzzle-style reasoning tasks with a single very small network applied recursively. Given an embedded question, a current answer and a latent reasoning state, a two-layer network repeatedly updates the latent state several times and then refines the answer, and this full cycle is itself repeated with deep supervision, so a 7M-parameter model achieves a large effective depth. TRM simplifies the [Hierarchical Reasoning Model](/paper/2506.21734) by dropping its two networks at different frequencies, its fixed-point gradient approximation and its biological justification, and it generalizes better. With about 7M parameters it reached 45% test accuracy on ARC-AGI-1 and 8% on ARC-AGI-2, higher than many large language models with less than 0.01% of their parameters, and it improved on HRM on Sudoku-Extreme and Maze-Hard. It is an example of [latent reasoning](/methods/latent-reasoning) with weight-shared recurrence, related to [looped transformers](/methods/looped-transformer).',
    'tiny recursive model',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2510.04871'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Less is More: Recursive Reasoning with Tiny Networks',
    'https://github.com/SamsungSAILMontreal/TinyRecursiveModels',
    NULL,
    '[Less is More: Recursive Reasoning with Tiny Networks](/paper/2510.04871)'
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
WHERE slug = 'tiny-recursive-model'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'tiny-recursive-model'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
