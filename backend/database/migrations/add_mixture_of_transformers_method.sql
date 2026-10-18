-- Add Mixture-of-Transformers, introduced in arXiv 2411.04996.
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog. The source paper gets the source evidence row (Introduced banner).

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
    'mixture-of-transformers',
    'Mixture-of-Transformers',
    'Mixture-of-Transformers (MoT)',
    'Mixture-of-Transformers (MoT) is a sparse multi-modal [Transformer](/methods/transformer) architecture from Meta that cuts the pre-training cost of foundation models handling text, images and speech. Each modality gets its own non-embedding parameters (feed-forward networks, attention projection matrices and layer normalization), while global self-attention still runs over the full interleaved sequence. Each token is therefore processed by its modality''s weights but attends to all tokens. Unlike [Mixture-of-Experts](/methods/mixture-of-experts), routing is deterministic by modality rather than learned. In the Chameleon 7B setting for autoregressive text-and-image generation, MoT matches the dense baseline using only 55.8% of the FLOPs, and with speech added it reaches comparable speech performance with 37.2% of the FLOPs. In the Transfusion setting, which mixes autoregressive text and [diffusion](/methods/diffusion) image objectives, a 7B MoT matches dense image quality with one third of the FLOPs. MoT-style modality-specific towers have since been widely adopted in unified multimodal models and vision-language-action models.',
    'mixture-of-transformers, mixture of transformers, mixture-of-transformer, mixture of transformer',
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
        WHERE arxiv_id = '2411.04996'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Mixture-of-Transformers: A Sparse and Scalable Architecture for Multi-Modal Foundation Models',
    'https://github.com/facebookresearch/Mixture-of-Transformers',
    NULL,
    '[Mixture-of-Transformers: A Sparse and Scalable Architecture for Multi-Modal Foundation Models](/paper/2411.04996)'
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
SELECT source_paper_id, id FROM methods
WHERE slug = 'mixture-of-transformers' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'mixture-of-transformers' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 89 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE mixture_of_transformers_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mixture-of-transformers'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        39346, 41921, 48544, 48754, 49221, 52004, 52700, 52874, 52982, 53278, 53513, 53596,
        53749, 54270, 54276, 54391, 54443, 54526, 55095, 55113, 56050, 56102, 56161, 56388,
        56421, 56544, 57044, 57406, 57407, 57734, 57770, 59638, 60257, 60499, 60851, 62089,
        63228, 63830, 65298, 66361, 66551, 66841, 66929, 69852, 70025, 71597, 72281, 74834,
        75027, 82924, 82943, 83227, 83247, 84401, 85123, 85456, 86680, 94610, 95087, 98159,
        98256, 98320, 98363, 98414, 98762, 98918, 98956, 104049, 104307, 104827, 108545, 108660,
        108720, 113850, 114103, 114150, 114259, 122119, 122411, 122652, 122667, 122674, 122702, 122896,
        123117, 123138, 123223, 123271, 123602
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'mixture-of-transformers citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM mixture_of_transformers_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING mixture_of_transformers_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 28 local citers name the method in title or abstract.
CREATE TEMP TABLE mixture_of_transformers_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mixture-of-transformers'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        52702, 53810, 54576, 55384, 55623, 56759, 57184, 57332, 60314, 61806, 63717, 66110,
        66381, 67149, 67924, 74348, 95095, 98736, 104219, 104512, 105994, 106025, 109291, 109579,
        118177, 118648, 121875, 122551
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mixture_of_transformers_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM mixture_of_transformers_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 47 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE mixture_of_transformers_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mixture-of-transformers'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        43305, 52702, 53810, 54576, 55028, 55384, 55471, 55623, 56759, 56828, 57184, 57332,
        58278, 59234, 60314, 60742, 61806, 62763, 62980, 63717, 64529, 66110, 66381, 67149,
        67924, 74348, 92531, 95095, 98736, 99040, 104012, 104219, 104512, 105912, 105994, 106025,
        109047, 109291, 109579, 109619, 118177, 118648, 121875, 122315, 122427, 122551, 122717
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mixture_of_transformers_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM mixture_of_transformers_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
