-- Add DDSP method, introduced in arXiv 2001.04643. The source paper
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
    'ddsp',
    'DDSP',
    'Differentiable Digital Signal Processing (DDSP)',
    'Differentiable Digital Signal Processing (DDSP) builds audio generators from classic signal-processing components, such as a harmonic additive synthesizer, filtered noise and a convolutional reverb, implemented as differentiable modules so they can be trained end to end with neural networks. An encoder extracts interpretable controls, such as fundamental frequency and loudness, and a decoder predicts the time-varying harmonic amplitudes and noise filter coefficients; training uses a multi-scale spectral loss instead of sample-level autoregression. Because the oscillators impose a strong inductive bias, DDSP models synthesize high-fidelity monophonic audio with far fewer parameters and less data than autoregressive models such as [WaveNet](/methods/wavenet), and they support independent control of pitch and loudness, timbre transfer and dereverberation.',
    'DDSP, differentiable digital signal processing',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2020,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2001.04643'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'DDSP: Differentiable Digital Signal Processing',
    'https://github.com/magenta/ddsp',
    NULL,
    '[DDSP: Differentiable Digital Signal Processing](/paper/2001.04643)'
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
WHERE slug = 'ddsp'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'ddsp'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
