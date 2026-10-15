-- Add Dataset Distillation method, introduced in arXiv 1811.10959. The source paper
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
    'dataset-distillation',
    'Dataset Distillation',
    'Dataset Distillation',
    'Dataset distillation synthesizes a very small set of training examples such that a model trained only on them performs close to one trained on the full dataset. Instead of compressing the model, as [knowledge distillation](/methods/knowledge-distillation) does, it compresses the data: the synthetic images, and optionally the learning rates, are optimized by backpropagating through a few unrolled gradient-descent steps of the learner. The original paper distilled the 60,000 MNIST training images into 10 synthetic images (one per class) that reach close to original accuracy in a few steps from a fixed initialization. Later methods such as gradient matching (dataset condensation), distribution matching and training-trajectory matching scaled the idea to larger datasets and random initializations, with applications to continual learning, neural architecture search, privacy and efficient training.',
    'dataset distillation, dataset condensation',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1811.10959'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Dataset Distillation',
    'https://github.com/SsnL/dataset-distillation',
    NULL,
    '[Dataset Distillation](/paper/1811.10959)'
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
WHERE slug = 'dataset-distillation'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'dataset-distillation'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
