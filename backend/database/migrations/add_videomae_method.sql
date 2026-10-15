-- Add VideoMAE method, sourced from arXiv 2203.12602.

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
    'videomae',
    'VideoMAE',
    'Video Masked Autoencoder (VideoMAE)',
    'VideoMAE extends the [masked autoencoder](/methods/masked-autoencoder) to [self-supervised](/methods/self-supervised-learning) video pre-training. Clips are split into space-time cubes, and tube masking hides the same spatial positions in every frame at an extremely high ratio of 90 to 95%, which prevents the model from copying content from neighbouring frames given the temporal redundancy of video. A vanilla [Vision Transformer](/methods/vision-transformer) encoder with joint space-time attention sees only the visible cubes, and a shallow decoder reconstructs the masked pixels. VideoMAE is data-efficient, training well on only 3k to 4k videos, and without extra data it reached 87.4% on Kinetics-400, 75.4% on Something-Something V2, 91.3% on UCF101 and 62.6% on HMDB51.',
    'VideoMAE',
    (
        SELECT id
        FROM areas
        WHERE name = 'Video'
        LIMIT 1
    ),
    2022,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2203.12602'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'VideoMAE: Masked Autoencoders are Data-Efficient Learners for Self-Supervised Video Pre-Training',
    'https://github.com/MCG-NJU/VideoMAE',
    NULL,
    '[VideoMAE: Masked Autoencoders are Data-Efficient Learners for Self-Supervised Video Pre-Training](/paper/2203.12602)'
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
WHERE slug = 'videomae'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'videomae'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
